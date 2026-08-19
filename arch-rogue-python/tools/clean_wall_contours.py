#!/usr/bin/env python3
"""Remove near-black exterior contours from high-resolution wall/door sprites.

The generated world masters have exterior outlines containing opaque, nearly
black pixels that become conspicuous when Pygame uses nearest-neighbour
scaling.  This tool recolours only the dark contour connected to transparency;
alpha and interior artwork are left unchanged.

Run without ``--output-dir`` to update the repository assets in place.  Use an
output directory first when reviewing a new set of source masters:

    python3 tools/clean_wall_contours.py --output-dir /tmp/contour-preview
"""

from __future__ import annotations

import argparse
from collections import deque
from pathlib import Path
from statistics import median
from typing import Iterable

from PIL import Image


WALL_FILENAMES = (
    "wall_401.png",
    "wall_bar_left.png",
    "wall_bar_right.png",
    "wall_garden_left.png",
    "wall_garden_right.png",
    "wall_lossless_soul_left.png",
    "wall_lossless_soul_right.png",
    "wall_quest_room_left.png",
    "wall_quest_room_right.png",
)
DOOR_FILENAMES = (
    "door_closed_left.png",
    "door_closed_right.png",
    "door_open_left.png",
    "door_open_right.png",
)
WORLD_CONTOUR_FILENAMES = (*WALL_FILENAMES, *DOOR_FILENAMES)

NEIGHBOURS_4 = ((-1, 0), (1, 0), (0, -1), (0, 1))
NEIGHBOURS_8 = (
    (-1, -1),
    (0, -1),
    (1, -1),
    (-1, 0),
    (1, 0),
    (-1, 1),
    (0, 1),
    (1, 1),
)


def luminance(rgb: tuple[int, int, int]) -> float:
    """Return perceptual sRGB luminance on the 0..255 scale."""

    red, green, blue = rgb
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _alpha_distance(
    pixels,
    width: int,
    height: int,
    *,
    max_distance: int,
) -> tuple[list[list[int]], list[tuple[int, int]]]:
    """Return inward Manhattan distance and the opaque exterior boundary."""

    distances = [[0] * width for _ in range(height)]
    boundary: list[tuple[int, int]] = []
    pending: deque[tuple[int, int]] = deque()

    for y in range(height):
        for x in range(width):
            if pixels[x, y][3] == 0:
                continue
            if any(
                not (0 <= x + dx < width and 0 <= y + dy < height)
                or pixels[x + dx, y + dy][3] == 0
                for dx, dy in NEIGHBOURS_4
            ):
                distances[y][x] = 1
                boundary.append((x, y))
                pending.append((x, y))

    while pending:
        x, y = pending.popleft()
        next_distance = distances[y][x] + 1
        if next_distance > max_distance:
            continue
        for dx, dy in NEIGHBOURS_4:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            if pixels[nx, ny][3] == 0 or distances[ny][nx]:
                continue
            distances[ny][nx] = next_distance
            pending.append((nx, ny))

    return distances, boundary


def _connected_dark_contour(
    pixels,
    width: int,
    height: int,
    distances: list[list[int]],
    boundary: Iterable[tuple[int, int]],
    *,
    band_width: int,
    dark_luma: float,
) -> set[tuple[int, int]]:
    """Find dark pixels in the contour band connected to the exterior edge."""

    candidates: set[tuple[int, int]] = {
        (x, y)
        for x, y in boundary
        if luminance(pixels[x, y][:3]) < dark_luma
    }
    pending = deque(candidates)

    while pending:
        x, y = pending.popleft()
        for dx, dy in NEIGHBOURS_8:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            if (
                (nx, ny) in candidates
                or distances[ny][nx] == 0
                or distances[ny][nx] > band_width
            ):
                continue
            if luminance(pixels[nx, ny][:3]) >= dark_luma:
                continue
            candidates.add((nx, ny))
            pending.append((nx, ny))

    return candidates


def _inward_colour(
    pixels,
    width: int,
    height: int,
    distances: list[list[int]],
    contour: set[tuple[int, int]],
    x: int,
    y: int,
    *,
    dark_luma: float,
    search_radius: int,
) -> tuple[int, int, int]:
    """Sample a robust local material colour from pixels inward of the edge."""

    current_distance = distances[y][x]
    donors: list[tuple[int, int, int]] = []

    for radius in range(1, search_radius + 1):
        left = max(0, x - radius)
        right = min(width - 1, x + radius)
        top = max(0, y - radius)
        bottom = min(height - 1, y + radius)

        for nx in range(left, right + 1):
            for ny in (top, bottom):
                if max(abs(nx - x), abs(ny - y)) != radius:
                    continue
                _append_donor(
                    donors,
                    pixels,
                    distances,
                    contour,
                    nx,
                    ny,
                    current_distance,
                    dark_luma,
                )
        for ny in range(top + 1, bottom):
            for nx in (left, right):
                if max(abs(nx - x), abs(ny - y)) != radius:
                    continue
                _append_donor(
                    donors,
                    pixels,
                    distances,
                    contour,
                    nx,
                    ny,
                    current_distance,
                    dark_luma,
                )

        # Several nearby samples avoid inheriting a single crack or highlight.
        if len(donors) >= 8:
            break

    if not donors:
        raise RuntimeError(f"No inward colour donor found for contour pixel {(x, y)}")

    nearest = donors[:16]
    return tuple(
        round(median(sample[channel] for sample in nearest))
        for channel in range(3)
    )


def _append_donor(
    donors: list[tuple[int, int, int]],
    pixels,
    distances: list[list[int]],
    contour: set[tuple[int, int]],
    x: int,
    y: int,
    current_distance: int,
    dark_luma: float,
) -> None:
    if (x, y) in contour or pixels[x, y][3] == 0:
        return
    if distances[y][x] <= current_distance:
        return
    red, green, blue, _alpha = pixels[x, y]
    if luminance((red, green, blue)) < dark_luma:
        return
    donors.append((red, green, blue))


def _ao_colour(
    material_rgb: tuple[int, int, int],
    inward_distance: int,
    *,
    minimum_luma: float,
) -> tuple[int, int, int]:
    """Darken the material colour while keeping the contour visibly coloured."""

    material_luma = luminance(material_rgb)
    ao_factor = min(0.80, 0.58 + 0.03 * (inward_distance - 1))
    target_luma = max(minimum_luma, material_luma * ao_factor)
    scale = target_luma / material_luma
    result = tuple(min(255, round(channel * scale)) for channel in material_rgb)

    # Rounding may land just below the threshold.  Lift all channels equally so
    # a second run is a no-op and no near-black contact pixel survives.
    while luminance(result) < minimum_luma:
        result = tuple(min(255, channel + 1) for channel in result)
    return result


def clean_wall(
    source: Path,
    destination: Path,
    *,
    band_width: int,
    dark_luma: float,
) -> tuple[int, int, int]:
    """Clean one world sprite and return changed/before-dark/after-dark counts."""

    with Image.open(source) as opened:
        image = opened.convert("RGBA")
    before = image.copy()
    pixels = image.load()
    width, height = image.size

    distances, boundary = _alpha_distance(
        pixels,
        width,
        height,
        max_distance=band_width * 4,
    )
    contour = _connected_dark_contour(
        pixels,
        width,
        height,
        distances,
        boundary,
        band_width=band_width,
        dark_luma=dark_luma,
    )

    replacements: dict[tuple[int, int], tuple[int, int, int]] = {}
    for x, y in sorted(contour, key=lambda point: (point[1], point[0])):
        material_rgb = _inward_colour(
            pixels,
            width,
            height,
            distances,
            contour,
            x,
            y,
            dark_luma=dark_luma,
            search_radius=band_width * 3,
        )
        replacements[x, y] = _ao_colour(
            material_rgb,
            distances[y][x],
            minimum_luma=dark_luma,
        )

    for (x, y), rgb in replacements.items():
        pixels[x, y] = (*rgb, pixels[x, y][3])

    if image.getchannel("A").tobytes() != before.getchannel("A").tobytes():
        raise AssertionError(f"Alpha changed while cleaning {source}")

    before_pixels = before.load()
    boundary_dark_before = sum(
        luminance(before_pixels[x, y][:3]) < dark_luma for x, y in boundary
    )
    boundary_dark_after = sum(
        luminance(pixels[x, y][:3]) < dark_luma for x, y in boundary
    )
    if boundary_dark_after:
        raise AssertionError(
            f"{source}: {boundary_dark_after} near-black boundary pixels remain"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="PNG", optimize=True)
    return len(replacements), boundary_dark_before, boundary_dark_after


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    default_asset_dir = repo_root / "src/arch_rogue/assets/sprites/world/hd"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-dir", type=Path, default=default_asset_dir)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Write cleaned copies here instead of replacing repository assets.",
    )
    parser.add_argument("--band-width", type=int, default=8)
    parser.add_argument("--dark-luma", type=float, default=48.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.band_width < 1:
        raise SystemExit("--band-width must be at least 1")
    if not 1 <= args.dark_luma <= 254:
        raise SystemExit("--dark-luma must be between 1 and 254")

    asset_dir = args.asset_dir.resolve()
    output_dir = args.output_dir.resolve() if args.output_dir else asset_dir
    for filename in WORLD_CONTOUR_FILENAMES:
        source = asset_dir / filename
        if not source.is_file():
            raise SystemExit(f"Missing required world sprite: {source}")
        changed, before_dark, after_dark = clean_wall(
            source,
            output_dir / filename,
            band_width=args.band_width,
            dark_luma=args.dark_luma,
        )
        print(
            f"{filename}: changed={changed}, "
            f"boundary_dark={before_dark}->{after_dark}"
        )


if __name__ == "__main__":
    main()
