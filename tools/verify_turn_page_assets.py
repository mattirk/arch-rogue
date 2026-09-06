#!/usr/bin/env python3
"""Verify the native HD PixelLab art and shared-texture animation contract."""
import hashlib
import json
from pathlib import Path
import struct
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "assets/world/turn_page"
manifest = json.loads((PACK / "manifest.json").read_text())
world = json.loads((ROOT / "assets/world/manifest.json").read_text())["world"]
floors = ["floor.png", "floor_ink_spill.png", "floor_ink_smear.png",
          "floor_glyph_serpent.png", "floor_glyph_key.png", "floor_glyph_moon.png"]
names = {*floors, "ink.png"}
assert manifest["format_version"] == 4
assert manifest["floor_variants"] == floors
assert manifest["variant_policy"] == {
    "selection": "seeded_per_page_without_replacement",
    "special_variant_counts": [3, 3, 3, 3, 3], "plain_count": 85,
    "seed_salt": "0x696e6b5f73746f6e", "route_dependent": False,
}
assert set(manifest["files"]) == names
assert {path.name for path in PACK.glob("*.png")} == names, "stale tile/frame assets"
for name, entry in manifest["files"].items():
    data = (PACK / name).read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", name
    assert list(struct.unpack(">II", data[16:24])) == entry["size"] == [512, 512], name
    assert data[24:26] == bytes([8, 6]), "native RGBA8 transparency required"
    assert hashlib.sha256(data).hexdigest() == entry["sha256"], name
    assert entry["generator"] == ("PixelLab Create Image Pro" if name == "ink.png" else "PixelLab Inpaint")
    assert entry["job_id"], name
    assert entry["prompt"], name
floor = manifest["files"]["floor.png"]
reference = manifest["geometry_reference"]
assert reference["file"] == "assets/world/lossless_soul_floor.png"
assert reference["world_key"] == "lossless_soul_floor"
assert hashlib.sha256((ROOT / reference["file"]).read_bytes()).hexdigest() == reference["sha256"]
assert reference["top_face_corners"] == [[256, 176], [512, 304], [256, 432], [0, 304]]
assert reference["side_depth"] == 80
assert floor["top_face_size"] == [512, 256]
mist = world[reference["world_key"]]
assert floor["anchor"] == mist["anchor"] == [256, 320], "floor anchors must match"
assert floor["ref_width"] == mist["ref_width"] == 512, "floor dimensions must match"
for name in floors:
    entry = manifest["files"][name]
    for key in ("anchor", "ref_width", "top_face_size"):
        assert entry[key] == floor[key], f"{name}: inconsistent slab geometry"
    with Image.open(PACK / name) as image:
        assert image.getbbox() == (0, 176, 512, 512), f"{name}: slab silhouette bounds changed"
    if name != "floor.png":
        assert entry["base_file"] == "floor.png" and entry["base_sha256"] == floor["sha256"]
        assert entry["edit_mask"]["shape"] == "ellipse"
    # Historical references are provenance only. Never load the archived tree.
    if name.startswith("floor_glyph_"):
        assert entry["legacy_art_reference"]["usage"] == "historical visual reference only"
keys = {"turn_page_hidden": floors, "turn_page_safe": ["ink.png"]}
assert {key for key in world if key.startswith("turn_page_")} == {*keys, "turn_page_parchment", "turn_page_void_glyph", "turn_page_ink_wisp"}
for key, files in keys.items():
    entry = world[key]
    assert entry["variants"] == [f"turn_page/{name}" for name in files]
    assert entry["anchor"] == manifest["files"][files[0]]["anchor"]
    assert entry["ref_width"] == manifest["files"][files[0]]["ref_width"]
    assert entry["frames"] == [] and entry["fps"] == 0 and not entry["ping_pong"]
assert manifest["animation"] == {
    "mode": "textured_fragments", "source": "selected_floor_variant", "pieces": 8,
    "duration_seconds": 0.9, "clock": "interpolated_simulation", "loop": False,
}
def verify_transparent_pack(directory, names):
    pack = json.loads((directory / "manifest.json").read_text())
    assert pack["format_version"] == 1
    assert set(pack["files"]) == set(names)
    assert {path.name for path in directory.glob("*.png")} == set(names)
    for name in names:
        entry = pack["files"][name]
        data = (directory / name).read_bytes()
        assert data[:8] == b"\x89PNG\r\n\x1a\n"
        assert list(struct.unpack(">II", data[16:24])) == entry["size"] == [256, 256]
        assert data[24:26] == bytes([8, 6]), "void art needs native RGBA8 transparency"
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]
        assert entry["generator"] and entry["job_id"] and entry["prompt"]
        with Image.open(directory / name) as image:
            alpha = image.getchannel("A")
            assert list(alpha.getbbox()) == entry["alpha_bounds"]
            assert alpha.getextrema() == (0, 255), "reject empty sprites or baked backgrounds"
            assert all(alpha.getpixel(point) == 0 for point in [(0, 0), (255, 0), (0, 255), (255, 255)])


scraps = [f"parchment_{index:02d}.png" for index in range(1, 4)]
verify_transparent_pack(PACK / "void", scraps)
entry = world["turn_page_parchment"]
assert entry["variants"] == [f"turn_page/void/{name}" for name in scraps]
assert entry["anchor"] == [128, 128] and entry["ref_width"] == 256
assert entry["frames"] == [] and entry["fps"] == 0 and not entry["ping_pong"]
glyphs = ["glyph_serpent.png", "glyph_key.png", "glyph_moon.png"]
verify_transparent_pack(PACK / "traces", [*glyphs, "ink_wisp.png"])
for key, names in {"turn_page_void_glyph": glyphs, "turn_page_ink_wisp": ["ink_wisp.png"]}.items():
    entry = world[key]
    assert entry["variants"] == [f"turn_page/traces/{name}" for name in names]
    assert entry["anchor"] == [128, 128] and entry["ref_width"] == 256
    assert entry["frames"] == [] and entry["fps"] == 0 and not entry["ping_pong"]
print("Turn the Page: floor geometry, variants, route ink, fragment animation, parchment and void traces verified with source hashes and transparency")
