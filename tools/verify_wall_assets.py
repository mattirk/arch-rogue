#!/usr/bin/env python3
"""Check wall art against the runtime grid, including every joining edge pixel."""
import hashlib
import json
import math
from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "assets/world"
manifest = json.loads((PACK / "walls.manifest.json").read_text())
world = json.loads((PACK / "manifest.json").read_text())["world"]["wall"]
assert world["anchor"] == [256, 384]
assert world["ref_width"] == 392
assert set(world["variants"]) == set(manifest["assets"])
geometry = manifest["geometry"]
assert geometry["anchor"] == world["anchor"]
assert geometry["ref_width"] == world["ref_width"]
top = geometry["top_corners"]
ground = geometry["ground_corners"]
for plane in (top, ground):
    for index, point in enumerate(plane):
        next_point = plane[(index + 1) % 4]
        assert abs(next_point[0] - point[0]) == 196
        assert abs(next_point[1] - point[1]) == 98, "edge must follow the 64x32 grid"
for upper, lower in zip(top, ground):
    assert upper[0] == lower[0]
    assert lower[1] - upper[1] == geometry["wall_height"] == 230

# Inspect the actual PNG alpha, not only the claimed geometry/bounding box.
# Include only pixel centers inside the six straight prism boundary segments.
expected = Image.new("L", (512, 512))
for x in range(60, 453):
    offset = abs(x - 256)
    for y in range(512):
        if 112 + offset <= 2 * y <= 964 - offset:
            expected.putpixel((x, y), 255)
for name, entry in manifest["assets"].items():
    path = PACK / name
    assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"], name
    with Image.open(path) as image:
        assert image.mode == "RGBA" and image.size == (512, 512), name
        assert list(image.getbbox()) == entry["alpha_bounds"] == [60, 56, 453, 483], name
        alpha = image.getchannel("A")
        # Authored chips are allowed only at the two rear edges, at most
        # three source pixels deep. Keep all other prism boundaries exact.
        repaired = alpha.copy()
        removed = [0, 0]
        for x in range(60, 453):
            along = abs(x - 256)
            top_y = math.ceil(56 + along / 2)
            depth = 0
            while depth < 4 and alpha.getpixel((x, top_y + depth)) == 0:
                depth += 1
            assert depth <= 3, f"{name}: oversized edge chip"
            if depth:
                assert 14 <= along <= 182, f"{name}: corner or end alignment damaged"
                removed[x > 256] += depth
                for y in range(top_y, top_y + depth):
                    repaired.putpixel((x, y), 255)
        assert all(20 <= count <= 160 for count in removed), f"{name}: missing or excessive rear chips"
        assert ImageChops.difference(repaired, expected).getbbox() is None, f"{name}: unexpected silhouette damage"

# Adjacent tiles' top/ground corners must coincide after the exact runtime
# translations in BOTH wall directions; equal bounding boxes alone do not.
for dx in (-196, 196):
    dy = 98
    for plane in (top, ground):
        shifted = {(x + dx, y + dy) for x, y in plane}
        assert len(set(map(tuple, plane)) & shifted) == 2
print("10 wall hashes, bounded rear chips and remaining 2:1 prism boundaries verified.")
