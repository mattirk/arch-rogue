#!/usr/bin/env python3
"""Replace block-upscaled world-sprite edges with native 512 px contours.

The authored wall, door, and generic-floor families deliberately share alpha
masks within each structural family.  Those masks were inherited from 64 px
sources, however, so diagonal perimeter steps are 8x8 blocks.  At maximum zoom
they become conspicuous sawteeth.  The original floor shell is also too tall
for its runtime canvas.

This tool applies a named canonical geometry profile with one-pixel native
diagonals.  Existing opaque pixels are byte-for-byte preserved wherever the old
and new masks overlap, except for profile-specific bright or near-black fringe
repair at the new exterior edge.  Small wedges exposed between old steps are
filled from the nearest existing material pixel; no generative repainting or
interior resampling is involved.

Previewing is the default and requires an explicit output directory:

    python3 tools/refine_world_silhouettes.py --profile wall \
        --output-dir /tmp/arch-rogue-wall-contour-preview

Repository assets can only be replaced with the explicit ``--in-place`` flag.
"""

from __future__ import annotations

import argparse
import hashlib
import math
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from statistics import median

from PIL import Image, ImageDraw

try:
    from .clean_wall_contours import clean_wall as clean_dark_contour
except ImportError:  # Direct execution adds tools/ rather than the repo root.
    from clean_wall_contours import clean_wall as clean_dark_contour


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

FLOOR_FILENAMES = (
    "floor.png",
    "floor_002.png",
    "floor_003.png",
    "floor_004.png",
)

GUIDING_OVERLAY_FILENAMES = tuple(
    f"guiding_overlay_{index:03d}.png" for index in range(1, 9)
)

MASTER_SIZE = (512, 512)

# These vertices preserve the original extrema, 40 px north plateau, vertical
# face extents, 32 px south plateau, and source anchor.  Only the 8x8 staircase
# quantisation between them changes.
WALL_CONTOUR = (
    (240, 56),
    (279, 56),
    (455, 144),
    (455, 199),
    (447, 200),
    (447, 391),
    (271, 479),
    (240, 479),
    (72, 391),
    (72, 200),
    (64, 199),
    (64, 144),
)

# A full-width 2:1 top diamond and 30 px material side.  Its 286 px bounding
# height fits every zoom-bucket floor canvas at width-derived scale; the old
# 320 px-tall shell was instead height-clamped at all four buckets.
FLOOR_CONTOUR = (
    (256, 192),
    (511, 319),
    (511, 349),
    (256, 477),
    (0, 349),
    (0, 319),
)


@dataclass(frozen=True)
class ContourProfile:
    name: str
    filenames: tuple[str, ...]
    vertices: tuple[tuple[int, int], ...]
    repair_bright_fringe: bool = False
    repair_dark_contour: bool = False
    clipped_overlays: tuple[str, ...] = ()


PROFILES = {
    "wall": ContourProfile(
        "wall",
        WALL_FILENAMES,
        WALL_CONTOUR,
        repair_bright_fringe=True,
    ),
    "door": ContourProfile(
        "door",
        DOOR_FILENAMES,
        WALL_CONTOUR,
        repair_bright_fringe=True,
        repair_dark_contour=True,
    ),
    "floor": ContourProfile(
        "floor",
        FLOOR_FILENAMES,
        FLOOR_CONTOUR,
        clipped_overlays=GUIDING_OVERLAY_FILENAMES,
    ),
}

NEIGHBOURS_4 = ((-1, 0), (1, 0), (0, -1), (0, 1))


def canonical_mask(profile: ContourProfile) -> Image.Image:
    """Return one profile's binary 512 px silhouette."""

    mask = Image.new("L", MASTER_SIZE)
    ImageDraw.Draw(mask).polygon(profile.vertices, fill=255)
    return mask


def _ring_points(
    x: int,
    y: int,
    radius: int,
    width: int,
    height: int,
):
    """Yield one square search ring without duplicating its corners."""

    left = max(0, x - radius)
    right = min(width - 1, x + radius)
    top = max(0, y - radius)
    bottom = min(height - 1, y + radius)
    for nx in range(left, right + 1):
        yield nx, top
        if bottom != top:
            yield nx, bottom
    for ny in range(top + 1, bottom):
        yield left, ny
        if right != left:
            yield right, ny


def _nearest_material(
    pixels,
    old_alpha,
    x: int,
    y: int,
    width: int,
    height: int,
    *,
    max_radius: int = 24,
) -> tuple[int, int, int]:
    """Return a robust colour from the closest old opaque edge pixels."""

    candidates: list[tuple[int, int, int, int, int]] = []
    for radius in range(1, max_radius + 1):
        for nx, ny in _ring_points(x, y, radius, width, height):
            if old_alpha[nx, ny] == 0:
                continue
            distance_sq = (nx - x) ** 2 + (ny - y) ** 2
            red, green, blue, _alpha = pixels[nx, ny]
            candidates.append((distance_sq, red, green, blue, 255))
        if len(candidates) >= 8:
            # A small nearest-neighbour median is robust against isolated
            # cracks and generator-bright fringe pixels.  It still samples
            # only the local face material (the largest added wedge is 14 px).
            nearest = sorted(candidates)[:16]
            result = tuple(
                round(median(pixel[channel] for pixel in nearest))
                for channel in range(1, 4)
            )
            # Newly synthesized perimeter material must not introduce another
            # near-black fringe. Median rounding can undershoot the threshold
            # by a fraction, so retain the contour-cleaning invariant here.
            while _luminance(result) < 48:
                result = tuple(min(255, channel + 1) for channel in result)
            return result
    raise RuntimeError(
        f"No opaque world material near new contour pixel {(x, y)}"
    )


def _luminance(rgb: tuple[int, int, int]) -> float:
    red, green, blue = rgb
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _alpha_distance(
    pixels,
    width: int,
    height: int,
    *,
    max_distance: int,
) -> list[list[int]]:
    """Return inward Manhattan distance from the current alpha boundary."""

    distances = [[0] * width for _ in range(height)]
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
    return distances


def _repair_bright_neutral_fringe(image: Image.Image) -> int:
    """Replace generator-white edge flecks without touching authored motifs."""

    source = image.copy()
    source_pixels = source.load()
    output_pixels = image.load()
    width, height = image.size
    distances = _alpha_distance(
        source_pixels,
        width,
        height,
        max_distance=24,
    )

    def is_fringe(rgb: tuple[int, int, int]) -> bool:
        return _luminance(rgb) > 190 and max(rgb) - min(rgb) < 32

    fringe = {
        (x, y)
        for y in range(height)
        for x in range(width)
        if 0 < distances[y][x] <= 3
        and is_fringe(source_pixels[x, y][:3])
    }

    for x, y in fringe:
        donors: list[tuple[int, int, int, int]] = []
        for radius in range(1, 25):
            for nx, ny in _ring_points(x, y, radius, width, height):
                if (
                    source_pixels[nx, ny][3] == 0
                    or (nx, ny) in fringe
                    or distances[ny][nx] <= distances[y][x]
                    or is_fringe(source_pixels[nx, ny][:3])
                ):
                    continue
                red, green, blue, _alpha = source_pixels[nx, ny]
                distance_sq = (nx - x) ** 2 + (ny - y) ** 2
                donors.append((distance_sq, red, green, blue))
            if len(donors) >= 8:
                break
        if not donors:
            raise RuntimeError(f"No inward material donor for fringe pixel {(x, y)}")
        nearest = sorted(donors)[:16]
        rgb = tuple(
            round(median(pixel[channel] for pixel in nearest))
            for channel in range(1, 4)
        )
        output_pixels[x, y] = (*rgb, 255)
    return len(fringe)


def refine_sprite(
    source: Path,
    destination: Path,
    target_mask: Image.Image,
    *,
    repair_bright_fringe: bool = False,
) -> dict[str, int | str]:
    """Write one refined sprite and return geometry-preservation metrics."""

    with Image.open(source) as opened:
        image = opened.convert("RGBA")
    if image.size != MASTER_SIZE:
        raise ValueError(f"{source} is {image.size}, expected {MASTER_SIZE}")

    old_alpha_image = image.getchannel("A")
    if set(old_alpha_image.getdata()) - {0, 255}:
        raise ValueError(f"{source} does not use a binary alpha mask")

    new_alpha_image = target_mask
    old_alpha = old_alpha_image.load()
    new_alpha = new_alpha_image.load()
    pixels = image.load()
    width, height = image.size
    before_rgba = image.tobytes()

    added: list[tuple[int, int]] = []
    removed: list[tuple[int, int]] = []
    for y in range(height):
        for x in range(width):
            was_opaque = old_alpha[x, y] != 0
            is_opaque = new_alpha[x, y] != 0
            if is_opaque and not was_opaque:
                added.append((x, y))
            elif was_opaque and not is_opaque:
                removed.append((x, y))

    for x, y in added:
        material = _nearest_material(
            pixels, old_alpha, x, y, width, height
        )
        pixels[x, y] = (*material, 255)
    for x, y in removed:
        red, green, blue, _alpha = pixels[x, y]
        pixels[x, y] = (red, green, blue, 0)

    # Pixels common to both masks contain the exact original RGBA bytes.
    after_rgba = image.tobytes()
    changed_inside = 0
    for y in range(height):
        for x in range(width):
            if old_alpha[x, y] and new_alpha[x, y]:
                offset = (y * width + x) * 4
                if before_rgba[offset : offset + 4] != after_rgba[offset : offset + 4]:
                    changed_inside += 1
    if changed_inside:
        raise AssertionError(f"{source}: changed {changed_inside} shared pixels")
    if image.getchannel("A").tobytes() != new_alpha_image.tobytes():
        raise AssertionError(f"{source}: output alpha differs from canonical mask")

    fringe_repaired = (
        _repair_bright_neutral_fringe(image)
        if repair_bright_fringe
        else 0
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="PNG", optimize=True)
    return {
        "added": len(added),
        "removed": len(removed),
        "preserved": sum(
            bool(old_alpha[x, y] and new_alpha[x, y])
            for y in range(height)
            for x in range(width)
        ),
        "bright_fringe_repaired": fringe_repaired,
        "alpha_sha256": hashlib.sha256(new_alpha_image.tobytes()).hexdigest(),
    }


def clip_overlay(
    source: Path,
    destination: Path,
    target_mask: Image.Image,
) -> int:
    """Clip a sparse material overlay to its refined base silhouette."""

    with Image.open(source) as opened:
        image = opened.convert("RGBA")
    if image.size != MASTER_SIZE:
        raise ValueError(f"{source} is {image.size}, expected {MASTER_SIZE}")
    alpha = image.getchannel("A")
    alpha_pixels = list(alpha.getdata())
    mask_pixels = list(target_mask.getdata())
    clipped_pixels = [
        value if mask else 0
        for value, mask in zip(alpha_pixels, mask_pixels, strict=True)
    ]
    removed = sum(
        before != after
        for before, after in zip(alpha_pixels, clipped_pixels, strict=True)
    )
    clipped_alpha = Image.new("L", MASTER_SIZE)
    clipped_alpha.putdata(clipped_pixels)
    image.putalpha(clipped_alpha)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="PNG", optimize=True)
    return removed


def _row_extent(mask: Image.Image, y: int) -> tuple[int, int]:
    pixels = mask.load()
    opaque = [x for x in range(mask.width) if pixels[x, y]]
    if not opaque:
        raise ValueError(f"No opaque pixels on contour row {y}")
    return opaque[0], opaque[-1]


def wall_contour_metrics(mask: Image.Image) -> dict[str, float | int]:
    """Measure diagonal blockiness and deviation from the intended shell."""

    samples: list[float] = []
    runs: list[int] = []
    for side in (0, 1):
        previous: int | None = None
        run = 0
        for y in range(56, 145):
            edge = _row_extent(mask, y)[side]
            expected = (
                240 - 2 * (y - 56)
                if side == 0
                else 279 + 2 * (y - 56)
            )
            samples.append(abs(edge - expected))
            if edge == previous:
                run += 1
            else:
                if run:
                    runs.append(run)
                previous = edge
                run = 1
        runs.append(run)

    # The south taper intentionally has slightly different left/right slopes
    # so it lands on the original 32 px plateau without shifting the anchor.
    for side, start, end in ((0, 72, 240), (1, 447, 271)):
        previous = None
        run = 0
        for y in range(391, 480):
            edge = _row_extent(mask, y)[side]
            amount = (y - 391) / (479 - 391)
            expected = start + (end - start) * amount
            samples.append(abs(edge - expected))
            if edge == previous:
                run += 1
            else:
                if run:
                    runs.append(run)
                previous = edge
                run = 1
        runs.append(run)

    return {
        "opaque_pixels": sum(alpha != 0 for alpha in mask.getdata()),
        "max_diagonal_plateau_rows": max(runs),
        "edge_fit_rms_px": math.sqrt(
            sum(error * error for error in samples) / len(samples)
        ),
        "edge_fit_max_px": max(samples),
    }


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    default_asset_dir = repo_root / "src/arch_rogue/assets/sprites/world/hd"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-dir", type=Path, default=default_asset_dir)
    parser.add_argument(
        "--profile",
        choices=tuple(PROFILES),
        default="wall",
        help="Canonical silhouette and active asset family to process.",
    )
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument("--output-dir", type=Path)
    destination.add_argument("--in-place", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    profile = PROFILES[args.profile]
    asset_dir = args.asset_dir.resolve()
    output_dir = asset_dir if args.in_place else args.output_dir.resolve()

    first_source = asset_dir / profile.filenames[0]
    with Image.open(first_source) as opened:
        old_mask = opened.convert("RGBA").getchannel("A")
    expected_old_alpha = old_mask.tobytes()
    target_mask = canonical_mask(profile)
    if profile.vertices == WALL_CONTOUR:
        print(f"before: {wall_contour_metrics(old_mask)}")
        print(f"after:  {wall_contour_metrics(target_mask)}")
    else:
        old_opaque = sum(alpha != 0 for alpha in old_mask.getdata())
        new_opaque = sum(alpha != 0 for alpha in target_mask.getdata())
        print(
            f"before: bbox={old_mask.getbbox()}, opaque_pixels={old_opaque}"
        )
        print(
            f"after:  bbox={target_mask.getbbox()}, opaque_pixels={new_opaque}"
        )

    for filename in profile.filenames:
        source = asset_dir / filename
        if not source.is_file():
            raise SystemExit(
                f"Missing required {profile.name} sprite: {source}"
            )
        with Image.open(source) as opened:
            source_alpha = opened.convert("RGBA").getchannel("A").tobytes()
        if source_alpha != expected_old_alpha:
            raise SystemExit(
                f"{profile.name.title()} alpha masks differ at {source}"
            )
        metrics = refine_sprite(
            source,
            output_dir / filename,
            target_mask,
            repair_bright_fringe=profile.repair_bright_fringe,
        )
        if profile.repair_dark_contour:
            changed, before_dark, after_dark = clean_dark_contour(
                output_dir / filename,
                output_dir / filename,
                band_width=8,
                dark_luma=48,
            )
            metrics["dark_contour_repaired"] = changed
            metrics["boundary_dark_before"] = before_dark
            metrics["boundary_dark_after"] = after_dark
        print(f"{filename}: {metrics}")

    for filename in profile.clipped_overlays:
        source = asset_dir / filename
        if not source.is_file():
            raise SystemExit(f"Missing required overlay sprite: {source}")
        removed = clip_overlay(source, output_dir / filename, target_mask)
        print(f"{filename}: clipped_alpha_pixels={removed}")


if __name__ == "__main__":
    main()
