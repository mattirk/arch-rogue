#!/usr/bin/env python3
"""Verify approved basic floor sprites and every interchangeable joining edge."""

import hashlib
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "assets/world"
NAMES = ["floor.png"] + [f"floor_{index:03d}.png" for index in range(2, 9)]
SIZE = (512, 512)
ANCHOR = [256, 320]
TOP_CORNERS = [[256, 192], [512, 320], [256, 448], [0, 320]]
ALPHA_BOUNDS = [0, 192, 512, 478]
COLLAR = 12


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"floor-assets: {message}")


def read_manifest(name: str) -> dict:
    try:
        result = json.loads((PACK / name).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise SystemExit(f"floor-assets: cannot read {name}: {error}") from error
    require(isinstance(result, dict), f"{name}: expected a JSON object")
    return result


def main() -> None:
    manifest = read_manifest("floors.manifest.json")
    entries = manifest.get("assets")
    require(isinstance(entries, dict) and set(entries) == set(NAMES),
            "manifest must contain exactly floor.png and floor_002.png through floor_008.png")
    geometry = manifest.get("geometry", {})
    require(geometry.get("anchor") == ANCHOR, "floor anchor must remain [256, 320]")
    require(geometry.get("ref_width") == 512, "floor reference width must remain 512")
    require(geometry.get("top_corners") == TOP_CORNERS,
            "walking plane must retain the canonical 512x256 diamond")
    require(geometry.get("top_plane") == [256, 256], "source plane must remain 256x256")
    require(geometry.get("shared_collar_px") == COLLAR, "shared texture collar must remain 12px")
    require(manifest.get("continuity", {}).get("directed_pair_count") == 128
            and manifest.get("continuity", {}).get("axes") == 2,
            "continuity contract must cover 64 ordered pairs along both axes")

    world = read_manifest("manifest.json").get("world", {})
    for key in ("floor", "guiding_floor"):
        entry = world.get(key, {})
        require(entry.get("variants") == NAMES, f"world.{key}: incorrect ordered floor variants")
        require(entry.get("anchor") == ANCHOR and entry.get("ref_width") == 512,
                f"world.{key}: geometry differs from the canonical walking plane")
        require(entry.get("frames") == [], f"world.{key}: basic floors must use static variants")
    for key, entry in world.items():
        if key not in ("floor", "guiding_floor"):
            references = entry.get("variants", []) + entry.get("frames", [])
            require(not set(NAMES).intersection(references),
                    f"world.{key}: basic floors must not replace special-room artwork")

    # Check the geometric join under the actual native-grid translations.
    corners = set(map(tuple, TOP_CORNERS))
    for dx in (-256, 256):
        shifted = {(x + dx, y + 128) for x, y in corners}
        require(len(corners & shifted) == 2, "neighboring 2:1 walking planes do not align")

    # Inverse projection of the final PNG, in doubled source-plane coordinates:
    # u = y - 192 + (x - 256)/2; v = y - 192 - (x - 256)/2.
    # Sampling the runtime PNG is authoritative; no review/build files are read.
    top_pixels = []
    collar_pixels = []
    for y in range(192, 449):
        for x in range(512):
            u2, v2 = 2 * y + x - 640, 2 * y - x - 128
            if 0 <= u2 <= 512 and 0 <= v2 <= 512:
                top_pixels.append((x, y))
                u, v = round(u2 / 2) % 256, round(v2 / 2) % 256
                if u < COLLAR or v < COLLAR or u >= 256 - COLLAR or v >= 256 - COLLAR:
                    collar_pixels.append((x, y))

    sprites = {}
    common_collar = None
    alpha_digest = None
    for name in NAMES:
        entry = entries[name]
        path = PACK / name
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            with Image.open(path) as source:
                require(source.mode == "RGBA" and source.size == SIZE,
                        f"{name}: expected a 512x512 RGBA PNG")
                sprite = source.copy()
        except OSError as error:
            raise SystemExit(f"floor-assets: cannot read {name}: {error}") from error
        require(digest == entry.get("sha256"), f"{name}: SHA-256 differs from the manifest")
        require(digest == entry.get("approved_source_sha256"),
                f"{name}: bytes differ from the approved source")
        require((entry.get("width"), entry.get("height")) == SIZE,
                f"{name}: manifest dimensions are incorrect")
        alpha = sprite.getchannel("A")
        require(list(alpha.getbbox() or ()) == entry.get("alpha_bounds") == ALPHA_BOUNDS,
                f"{name}: actual alpha bounds differ from the approved silhouette")
        actual_alpha = hashlib.sha256(alpha.tobytes()).hexdigest()
        require(actual_alpha == geometry.get("alpha_sha256"),
                f"{name}: actual alpha differs from the approved silhouette checksum")
        if alpha_digest is not None:
            require(actual_alpha == alpha_digest, f"{name}: variant silhouettes differ")
        alpha_digest = actual_alpha
        pixels = sprite.load()
        for point in top_pixels:
            require(pixels[point][3] == 255, f"{name}: walking plane is not opaque at {point}")
        collar = [pixels[point] for point in collar_pixels]
        if common_collar is not None:
            require(collar == common_collar, f"{name}: shared 12px texture collar differs")
        common_collar = collar
        sprites[name] = sprite

    # The right corner is x=512, just outside the PNG. The 127 interior integer
    # points along each 2:1 edge are present on BOTH neighbors. Compare actual
    # RGBA values for every ordered pair, including a variant beside itself.
    comparisons = 0
    for name_a, sprite_a in sprites.items():
        for name_b, sprite_b in sprites.items():
            a, b = sprite_a.load(), sprite_b.load()
            for k in range(2, 256, 2):
                require(a[512 - k, 320 + k // 2] == b[256 - k, 192 + k // 2],
                        f"{name_a} -> {name_b}: southeast/northwest seam differs at sample {k}")
                require(a[k, 320 + k // 2] == b[256 + k, 192 + k // 2],
                        f"{name_a} -> {name_b}: southwest/northeast seam differs at sample {k}")
            comparisons += 2
    print(f"8 approved floor hashes, opaque 2:1 planes, shared 12px collars and {comparisons} directed joins verified.")


if __name__ == "__main__":
    main()
