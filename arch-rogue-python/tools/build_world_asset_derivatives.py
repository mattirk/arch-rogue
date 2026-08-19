#!/usr/bin/env python3
"""Build deterministic derivatives for authored world sprites.

PixelLab supplies the high-resolution authored masters.  This helper keeps
animation families compact and mechanically aligned:

* extract the existing guidance rune into transparent overlay frames, and
* lock a PixelLab stair-geometry repair to the upper stairwell interior,
* build and normalize a PixelLab redraw of the stair's northern exterior rim,
* constrain a PixelLab stair-lighting edit to the stairwell interior, and
* interpolate a native-resolution stair glow endpoint into a pulse sequence.

The script never generates artwork.  Geometry and rim edits are accepted only
through explicit masks; every frozen pixel and the canonical alpha silhouette
remain locked to the existing authored master.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageChops, ImageDraw, ImageFilter


RGBA = tuple[int, int, int, int]
STAIR_REAR_FLOOR_OFFSETS = ((-256, -112), (0, -240), (256, -112))
STAIR_REAR_FLOOR_PAINTER_ORDER = (1, 0, 2)


def _rgba(path: Path) -> Image.Image:
    image = Image.open(path).convert("RGBA")
    if image.size != (512, 512):
        raise ValueError(f"{path}: expected 512x512, got {image.size}")
    return image


def floor_surface_mask(reference: Image.Image) -> Image.Image:
    """Return the locked top-face mask used for PixelLab floor inpainting."""

    seed_values: list[int] = []
    for red, green, blue, alpha in reference.getdata():
        is_top_stone = (
            alpha
            and green >= red - 24
            and green >= blue + 8
            and red + green + blue > 120
        )
        seed_values.append(255 if is_top_stone else 0)
    seed = Image.new("L", reference.size)
    seed.putdata(seed_values)
    seed = seed.filter(ImageFilter.MaxFilter(15))

    diamond = Image.new("L", reference.size)
    ImageDraw.Draw(diamond).polygon(
        ((256, 198), (500, 320), (256, 442), (12, 320)), fill=255
    )
    mask = ImageChops.multiply(seed, diamond)
    return mask.point(lambda value: 255 if value else 0)


def normalize_floor_master(
    reference_path: Path, generated_path: Path, output_path: Path
) -> None:
    """Lock a masked PixelLab edit to the canonical floor alpha and exterior."""

    reference = _rgba(reference_path)
    generated = _rgba(generated_path)
    mask = list(floor_surface_mask(reference).getdata())

    output_pixels: list[RGBA] = []
    for canonical, edited, editable in zip(
        reference.getdata(), generated.getdata(), mask, strict=True
    ):
        if not canonical[3]:
            output_pixels.append((0, 0, 0, 0))
        elif not editable or not edited[3]:
            output_pixels.append(canonical)
        else:
            output_pixels.append(
                (edited[0], edited[1], edited[2], canonical[3])
            )

    output = Image.new("RGBA", reference.size)
    output.putdata(output_pixels)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output.save(output_path, optimize=True)


def _guide_overlay(base: Image.Image, guided: Image.Image) -> Image.Image:
    """Recover a sparse alpha overlay that recreates the authored gold rune."""

    base_pixels: list[RGBA] = list(base.getdata())
    guided_pixels: list[RGBA] = list(guided.getdata())

    # Warm, bright changes identify the rune itself.  Dilating that seed by
    # three pixels retains its dark carved rim without importing unrelated
    # full-floor colour drift from the old complete animation frames.
    seed_values: list[int] = []
    for before, after in zip(base_pixels, guided_pixels, strict=True):
        if not before[3]:
            seed_values.append(0)
            continue
        delta = max(abs(after[index] - before[index]) for index in range(3))
        red_gain = after[0] - before[0]
        green_gain = after[1] - before[1]
        blue_gain = after[2] - before[2]
        warm = after[0] - after[2] >= 12 and after[1] - after[2] >= 5
        gain = red_gain + green_gain * 0.7 - blue_gain * 0.15
        seed_values.append(255 if delta >= 4 and warm and gain >= 5 else 0)

    seed = Image.new("L", base.size)
    seed.putdata(seed_values)
    support = list(seed.filter(ImageFilter.MaxFilter(7)).getdata())

    overlay_pixels: list[RGBA] = []
    for before, after, supported in zip(
        base_pixels, guided_pixels, support, strict=True
    ):
        difference = max(abs(after[index] - before[index]) for index in range(3))
        if not supported or not before[3] or difference < 2:
            overlay_pixels.append((0, 0, 0, 0))
            continue

        # Choose the minimum legal opacity that can reconstruct ``after`` over
        # ``before``.  This retains the new floor's texture beneath faint rune
        # frames while exactly preserving strong authored highlights.
        alpha = 0.0
        for base_channel, guided_channel in zip(
            before[:3], after[:3], strict=True
        ):
            if guided_channel > base_channel and base_channel < 255:
                alpha = max(
                    alpha,
                    (guided_channel - base_channel) / (255 - base_channel),
                )
            elif guided_channel < base_channel and base_channel > 0:
                alpha = max(
                    alpha,
                    (base_channel - guided_channel) / base_channel,
                )
        alpha = min(1.0, max(alpha, 0.08))
        overlay_rgb = []
        for base_channel, guided_channel in zip(
            before[:3], after[:3], strict=True
        ):
            channel = round(
                (guided_channel - base_channel * (1.0 - alpha)) / alpha
            )
            overlay_rgb.append(max(0, min(255, channel)))
        overlay_pixels.append(
            (*overlay_rgb, round(alpha * 255))  # type: ignore[arg-type]
        )

    overlay = Image.new("RGBA", base.size)
    overlay.putdata(overlay_pixels)
    return overlay


def extract_guidance(
    base_path: Path, guided_paths: Iterable[Path], output_dir: Path
) -> None:
    base = _rgba(base_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    for index, guided_path in enumerate(guided_paths, 1):
        guided = _rgba(guided_path)
        if guided.getchannel("A").tobytes() != base.getchannel("A").tobytes():
            raise ValueError(f"{guided_path}: alpha mask differs from {base_path}")
        overlay = _guide_overlay(base, guided)
        overlay.save(output_dir / f"guiding_overlay_{index:03}.png", optimize=True)


def build_stair_frames(
    base_path: Path, endpoint_path: Path, output_dir: Path
) -> None:
    base = _rgba(base_path)
    endpoint = _rgba(endpoint_path)
    base_alpha = base.getchannel("A")
    endpoint_alpha = endpoint.getchannel("A")
    if endpoint_alpha.tobytes() != base_alpha.tobytes():
        raise ValueError("stair glow endpoint must use the base stair alpha mask")

    base_pixels: list[RGBA] = list(base.getdata())
    endpoint_pixels: list[RGBA] = list(endpoint.getdata())
    strengths = (0.06, 0.16, 0.30, 0.48, 0.68, 0.86, 1.0)
    output_dir.mkdir(parents=True, exist_ok=True)
    for index, strength in enumerate(strengths, 1):
        frame_pixels: list[RGBA] = []
        for before, after in zip(base_pixels, endpoint_pixels, strict=True):
            if not before[3]:
                frame_pixels.append((0, 0, 0, 0))
                continue
            frame_pixels.append(
                (
                    round(before[0] + (after[0] - before[0]) * strength),
                    round(before[1] + (after[1] - before[1]) * strength),
                    round(before[2] + (after[2] - before[2]) * strength),
                    before[3],
                )
            )
        frame = Image.new("RGBA", base.size)
        frame.putdata(frame_pixels)
        frame.save(output_dir / f"stairs_{index:03}.png", optimize=True)


def stair_entry_geometry_mask(reference: Image.Image) -> Image.Image:
    """Return the upper-well region where the stair run may meet the rim."""

    mask = Image.new("L", reference.size)
    ImageDraw.Draw(mask).polygon(
        (
            (204, 140),
            (326, 136),
            (391, 173),
            (409, 230),
            (383, 286),
            (288, 300),
            (210, 247),
            (184, 190),
        ),
        fill=255,
    )
    return mask


def normalize_stair_geometry(
    base_path: Path,
    endpoint_path: Path,
    generated_path: Path,
    output_base_path: Path,
    output_endpoint_path: Path,
) -> None:
    """Lock a PixelLab tread repair and carry the existing glow onto it.

    PixelLab edits only the missing upper tread run.  The old base supplies the
    canonical alpha and every pixel outside :func:`stair_entry_geometry_mask`.
    Within the mask, the low-frequency difference between the old base and glow
    endpoint is transferred to the corrected masonry.  Blurring that difference
    prevents old wall joints from ghosting across the new treads while retaining
    the authored radial violet illumination.
    """

    base = _rgba(base_path)
    endpoint = _rgba(endpoint_path)
    generated = _rgba(generated_path)
    base_alpha = base.getchannel("A")
    if endpoint.getchannel("A").tobytes() != base_alpha.tobytes():
        raise ValueError("stair glow endpoint must use the base stair alpha mask")

    editable = list(stair_entry_geometry_mask(base).getdata())
    blurred_base = base.filter(ImageFilter.GaussianBlur(7))
    blurred_endpoint = endpoint.filter(ImageFilter.GaussianBlur(7))

    corrected_pixels: list[RGBA] = []
    corrected_endpoint_pixels: list[RGBA] = []
    for canonical, old_glow, edited, amount, low_base, low_glow in zip(
        base.getdata(),
        endpoint.getdata(),
        generated.getdata(),
        editable,
        blurred_base.getdata(),
        blurred_endpoint.getdata(),
        strict=True,
    ):
        if not canonical[3]:
            corrected = (0, 0, 0, 0)
        elif amount and edited[3]:
            corrected = (edited[0], edited[1], edited[2], canonical[3])
        else:
            corrected = canonical
        corrected_pixels.append(corrected)

        if not canonical[3]:
            corrected_endpoint_pixels.append((0, 0, 0, 0))
        elif amount:
            corrected_endpoint_pixels.append(
                (
                    max(0, min(255, corrected[0] + low_glow[0] - low_base[0])),
                    max(0, min(255, corrected[1] + low_glow[1] - low_base[1])),
                    max(0, min(255, corrected[2] + low_glow[2] - low_base[2])),
                    canonical[3],
                )
            )
        else:
            corrected_endpoint_pixels.append(old_glow)

    corrected_base = Image.new("RGBA", base.size)
    corrected_base.putdata(corrected_pixels)
    corrected_endpoint = Image.new("RGBA", base.size)
    corrected_endpoint.putdata(corrected_endpoint_pixels)
    output_base_path.parent.mkdir(parents=True, exist_ok=True)
    output_endpoint_path.parent.mkdir(parents=True, exist_ok=True)
    corrected_base.save(output_base_path, optimize=True)
    corrected_endpoint.save(output_endpoint_path, optimize=True)


def _shifted_alpha(image: Image.Image, offset: tuple[int, int]) -> Image.Image:
    shifted = Image.new("L", image.size)
    shifted.paste(image.getchannel("A"), offset)
    return shifted


def stair_rear_rim_mask(
    reference: Image.Image,
    floor_references: Iterable[Image.Image],
    animation_frames: Iterable[Image.Image],
    band_width: int = 20,
) -> Image.Image:
    """Return the static outer-rim band backed by the N/NW/NE floor tiles.

    The authored stair circle reaches into the three tiles behind it rather
    than meeting only the floor slab under the stair coordinate.  The mask
    therefore uses those neighbors' exact projected alpha coverage.  It admits
    only the requested outer source-pixel band of the stair silhouette and
    excludes a four-pixel guard around every animated glow delta.
    """

    if not 1 <= band_width <= 20:
        raise ValueError("stair rear-rim band width must be between 1 and 20")

    alpha = reference.getchannel("A").point(lambda value: 255 if value else 0)
    inner = alpha.filter(ImageFilter.MinFilter(band_width * 2 + 1))
    outer_band = ImageChops.subtract(alpha, inner)

    floor_union = Image.new("L", reference.size)
    floors = list(floor_references)
    if len(floors) != len(STAIR_REAR_FLOOR_OFFSETS):
        raise ValueError("stair rear-rim context requires NW, N, and NE floors")
    for floor, offset in zip(floors, STAIR_REAR_FLOOR_OFFSETS, strict=True):
        floor_union = ImageChops.lighter(
            floor_union,
            _shifted_alpha(floor, offset),
        )

    animation_delta = Image.new("L", reference.size)
    reference_pixels: list[RGBA] = list(reference.getdata())
    for frame in animation_frames:
        frame_pixels: list[RGBA] = list(frame.getdata())
        changed = Image.new("L", reference.size)
        changed.putdata(
            [
                255 if before != after else 0
                for before, after in zip(
                    reference_pixels,
                    frame_pixels,
                    strict=True,
                )
            ]
        )
        animation_delta = ImageChops.lighter(animation_delta, changed)
    animation_guard = animation_delta.filter(ImageFilter.MaxFilter(9))

    editable = ImageChops.multiply(outer_band, floor_union)
    editable = ImageChops.subtract(editable, animation_guard)
    return editable.point(lambda value: 255 if value else 0)


def build_stair_rear_rim_input(
    reference_path: Path,
    floor_paths: Iterable[Path],
    frame_paths: Iterable[Path],
    output_context_path: Path,
    output_mask_path: Path,
    band_width: int = 20,
) -> None:
    """Build the repo-only PixelLab context and exact northern-rim edit mask."""

    reference = _rgba(reference_path)
    floors = [_rgba(path) for path in floor_paths]
    frames = [_rgba(path) for path in frame_paths]
    mask = stair_rear_rim_mask(reference, floors, frames, band_width)

    context = Image.new("RGBA", reference.size)
    # Runtime paints the northern diagonal first, then its northwest and
    # northeast neighbors.  Preserve that overlap order in PixelLab's context.
    for index in STAIR_REAR_FLOOR_PAINTER_ORDER:
        floor = floors[index]
        offset = STAIR_REAR_FLOOR_OFFSETS[index]
        context.alpha_composite(floor, dest=offset)
    context.alpha_composite(reference)

    output_context_path.parent.mkdir(parents=True, exist_ok=True)
    output_mask_path.parent.mkdir(parents=True, exist_ok=True)
    context.save(output_context_path, optimize=True)
    mask.save(output_mask_path, optimize=True)


def normalize_stair_rear_rim(
    reference_path: Path,
    floor_paths: Iterable[Path],
    frame_paths: Iterable[Path],
    generated_path: Path,
    output_dir: Path,
    generated_weight: float = 1.0,
    band_width: int = 20,
) -> None:
    """Apply one masked rear-rim redraw identically to all animation frames."""

    if not 0.0 <= generated_weight <= 1.0:
        raise ValueError("generated weight must be between 0 and 1")

    reference = _rgba(reference_path)
    floors = [_rgba(path) for path in floor_paths]
    frames = [_rgba(path) for path in frame_paths]
    generated = _rgba(generated_path)
    mask = list(
        stair_rear_rim_mask(
            reference,
            floors,
            frames,
            band_width,
        ).getdata()
    )
    canonical_alpha = reference.getchannel("A").tobytes()
    if any(frame.getchannel("A").tobytes() != canonical_alpha for frame in frames):
        raise ValueError("all stair animation frames must use the base alpha mask")

    reference_pixels: list[RGBA] = list(reference.getdata())
    generated_pixels: list[RGBA] = list(generated.getdata())
    replacement: list[RGBA] = []
    for canonical, edited, editable in zip(
        reference_pixels,
        generated_pixels,
        mask,
        strict=True,
    ):
        if not canonical[3]:
            replacement.append((0, 0, 0, 0))
        elif editable and edited[3]:
            replacement.append(
                (
                    round(
                        canonical[0]
                        + (edited[0] - canonical[0]) * generated_weight
                    ),
                    round(
                        canonical[1]
                        + (edited[1] - canonical[1]) * generated_weight
                    ),
                    round(
                        canonical[2]
                        + (edited[2] - canonical[2]) * generated_weight
                    ),
                    canonical[3],
                )
            )
        else:
            replacement.append(canonical)

    output_dir.mkdir(parents=True, exist_ok=True)
    all_frames = [reference, *frames]
    for index, frame in enumerate(all_frames):
        output_pixels: list[RGBA] = []
        for original, edited, editable in zip(
            frame.getdata(),
            replacement,
            mask,
            strict=True,
        ):
            if not original[3]:
                output_pixels.append((0, 0, 0, 0))
            elif editable:
                output_pixels.append(edited)
            else:
                output_pixels.append(original)
        output = Image.new("RGBA", reference.size)
        output.putdata(output_pixels)
        name = "stairs.png" if index == 0 else f"stairs_{index:03}.png"
        output.save(output_dir / name, optimize=True)


def normalize_stair_endpoint(
    base_path: Path, generated_path: Path, output_path: Path
) -> None:
    """Keep a PixelLab lighting edit inside the well and lock its geometry.

    The authored master has a broad outer rim that must continue to match the
    surrounding floor.  A softly feathered ellipse admits the generated violet
    light on the inner wall, steps, and shaft while restoring that rim from the
    base.  The canonical binary alpha mask is always copied verbatim.
    """

    base = _rgba(base_path)
    generated = _rgba(generated_path)
    light_region = Image.new("L", base.size)
    ImageDraw.Draw(light_region).ellipse((70, 130, 442, 400), fill=255)
    light_region = light_region.filter(ImageFilter.GaussianBlur(6))

    output_pixels: list[RGBA] = []
    for canonical, edited, amount in zip(
        base.getdata(),
        generated.getdata(),
        light_region.getdata(),
        strict=True,
    ):
        if not canonical[3]:
            output_pixels.append((0, 0, 0, 0))
            continue
        mix = amount / 255.0
        output_pixels.append(
            (
                round(canonical[0] + (edited[0] - canonical[0]) * mix),
                round(canonical[1] + (edited[1] - canonical[1]) * mix),
                round(canonical[2] + (edited[2] - canonical[2]) * mix),
                canonical[3],
            )
        )

    output = Image.new("RGBA", base.size)
    output.putdata(output_pixels)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output.save(output_path, optimize=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    guidance = subparsers.add_parser(
        "guidance", help="extract transparent rune overlays"
    )
    guidance.add_argument("--base", type=Path, required=True)
    guidance.add_argument("--guided", type=Path, nargs="+", required=True)
    guidance.add_argument("--output-dir", type=Path, required=True)

    stairs = subparsers.add_parser(
        "stairs", help="interpolate a native-resolution glow endpoint"
    )
    stairs.add_argument("--base", type=Path, required=True)
    stairs.add_argument("--endpoint", type=Path, required=True)
    stairs.add_argument("--output-dir", type=Path, required=True)

    stair_geometry = subparsers.add_parser(
        "stair-geometry",
        help="lock an upper-tread repair and transfer the existing glow",
    )
    stair_geometry.add_argument("--base", type=Path, required=True)
    stair_geometry.add_argument("--endpoint", type=Path, required=True)
    stair_geometry.add_argument("--generated", type=Path, required=True)
    stair_geometry.add_argument("--output-base", type=Path, required=True)
    stair_geometry.add_argument("--output-endpoint", type=Path, required=True)

    stair_endpoint = subparsers.add_parser(
        "stair-endpoint",
        help="lock a PixelLab stair-lighting edit to the stairwell interior",
    )
    stair_endpoint.add_argument("--base", type=Path, required=True)
    stair_endpoint.add_argument("--generated", type=Path, required=True)
    stair_endpoint.add_argument("--output", type=Path, required=True)

    stair_rim_input = subparsers.add_parser(
        "stair-rim-input",
        help="build a PixelLab context and static N/NW/NE stair-rim mask",
    )
    stair_rim_input.add_argument("--reference", type=Path, required=True)
    stair_rim_input.add_argument("--floors", type=Path, nargs=3, required=True)
    stair_rim_input.add_argument("--frames", type=Path, nargs=7, required=True)
    stair_rim_input.add_argument("--output-context", type=Path, required=True)
    stair_rim_input.add_argument("--output-mask", type=Path, required=True)
    stair_rim_input.add_argument("--band-width", type=int, default=20)

    stair_rim = subparsers.add_parser(
        "stair-rim",
        help="lock a PixelLab redraw to the static N/NW/NE stair rim",
    )
    stair_rim.add_argument("--reference", type=Path, required=True)
    stair_rim.add_argument("--floors", type=Path, nargs=3, required=True)
    stair_rim.add_argument("--frames", type=Path, nargs=7, required=True)
    stair_rim.add_argument("--generated", type=Path, required=True)
    stair_rim.add_argument("--output-dir", type=Path, required=True)
    stair_rim.add_argument("--generated-weight", type=float, default=1.0)
    stair_rim.add_argument("--band-width", type=int, default=20)

    floor = subparsers.add_parser(
        "floor", help="normalize a masked floor edit to the canonical shell"
    )
    floor.add_argument("--reference", type=Path, required=True)
    floor.add_argument("--generated", type=Path, required=True)
    floor.add_argument("--output", type=Path, required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command == "guidance":
        extract_guidance(args.base, args.guided, args.output_dir)
    elif args.command == "stairs":
        build_stair_frames(args.base, args.endpoint, args.output_dir)
    elif args.command == "stair-geometry":
        normalize_stair_geometry(
            args.base,
            args.endpoint,
            args.generated,
            args.output_base,
            args.output_endpoint,
        )
    elif args.command == "stair-endpoint":
        normalize_stair_endpoint(args.base, args.generated, args.output)
    elif args.command == "stair-rim-input":
        build_stair_rear_rim_input(
            args.reference,
            args.floors,
            args.frames,
            args.output_context,
            args.output_mask,
            args.band_width,
        )
    elif args.command == "stair-rim":
        normalize_stair_rear_rim(
            args.reference,
            args.floors,
            args.frames,
            args.generated,
            args.output_dir,
            args.generated_weight,
            args.band_width,
        )
    elif args.command == "floor":
        normalize_floor_master(args.reference, args.generated, args.output)


if __name__ == "__main__":
    main()
