#!/usr/bin/env python3
"""Verify the self-contained MX-story art pack and strict manifest.

The authored PNGs are committed under ``assets/story``. This tool never reads
legacy assets or contacts a network service: it validates the finished pack and
its content hashes. ``--write-manifest`` updates hashes after an intentional
canonical-art change.

Usage:
    python tools/verify_story_assets.py
    python tools/verify_story_assets.py --write-manifest
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError

AR_ROOT = Path(__file__).resolve().parent.parent
ASSET_ROOT = AR_ROOT / "assets" / "story"
MANIFEST_PATH = ASSET_ROOT / "manifest.json"
MANIFEST_FORMAT = 1
EXPECTED_ASSET_COUNT = 81
SAFE_FILE_RE = re.compile(r"^[a-z0-9_.-]+(?:/[a-z0-9_.-]+)*\.png$")


@dataclass(frozen=True)
class AssetSpec:
    key: str
    file: str
    usage: str


OMENS = (
    "crypt_of_ash",
    "fungal_catacombs",
    "violet_reliquary",
    "sunken_bastion",
    "frozen_ossuary",
    "obsidian_foundry",
    "moonlit_aquifer",
    "thornbound_vault",
)
GUEST_ROLES = (
    "oathless_knight",
    "grave_witch",
    "drowned_heir",
    "ash_pilgrim",
    "mirror_scribe",
    "antlered_hunter",
    "mortuary_broker",
    "lost_cartographer",
    "bone_mender",
    "furnace_heretic",
)
ENDINGS = {
    "warden": ("the_held_door", "the_fair_scale", "no_more_doors"),
    "rogue": ("the_emptied_market", "the_honest_purchase", "the_standing_debt"),
    "arcanist": ("the_answered_proof", "the_restored_name", "the_standing_argument"),
    "acolyte": ("the_true_funeral", "the_returned_confession", "the_broken_bell"),
    "ranger": ("the_hunt_without_arrows", "the_next_white_thing", "the_old_way"),
}
RELICS = (
    "asterion_nail",
    "mire_saints_bell",
    "lantern_of_unburied_roads",
    "crown_of_antlers_and_teeth",
    "mirror_psalter",
    "cinder_key_of_khar",
    "wormscript_map",
    "vessel_of_last_rain",
    "oath_eaters_chain",
    "heartseed_reliquary",
)
PORTRAITS = {
    "oathless_knight": ("ser_caldus", "dame_vey", "rook_of_voss"),
    "grave_witch": ("mother_hush", "edda_crowmilk", "vespera_thorne"),
    "drowned_heir": ("prince_nerian", "lysa_underwave", "blue_lipped_child"),
    "ash_pilgrim": ("harl_the_sooted", "sister_kharra", "old_ember_jesk"),
    "mirror_scribe": ("tallow_quill", "iosef_of_the_glass", "nim_rue"),
    "antlered_hunter": ("mael_whitehorn", "quiet_hart", "sable_of_the_moon_hunt"),
    "mortuary_broker": ("coin_eye_pell", "madam_nacre", "voss_factor_ilm"),
    "lost_cartographer": ("ammar_without_roads", "fen_chalkhand", "sella_of_the_fold"),
    "bone_mender": ("saint_not_yet", "mara_sutured", "kell_of_white_thread"),
    "furnace_heretic": ("brass_thumb_oren", "malk_the_quenched", "devra_cogprayer"),
}
CHOICES = (
    "aid",
    "bargain",
    "defy",
    "page",
    "soul_preserve",
    "soul_release",
    "soul_refuse",
)


def asset_specs() -> tuple[AssetSpec, ...]:
    specs: list[AssetSpec] = []
    specs.extend(
        AssetSpec(f"story.omen.{slug}", f"backdrops/omens/{slug}.png", "backdrop")
        for slug in OMENS
    )
    specs.extend(
        AssetSpec(f"story.guest.{role}", f"backdrops/guests/{role}.png", "backdrop")
        for role in GUEST_ROLES
    )
    for archetype, endings in ENDINGS.items():
        specs.extend(
            AssetSpec(
                f"story.ending.{archetype}.{ending}",
                f"backdrops/endings/{archetype}/{ending}.png",
                "backdrop",
            )
            for ending in endings
        )
    specs.extend(
        AssetSpec(f"story.relic.{slug}", f"icons/relics/{slug}.png", "icon")
        for slug in RELICS
    )
    for role, portraits in PORTRAITS.items():
        specs.extend(
            AssetSpec(
                f"story.portrait.{role}.{portrait}",
                f"portraits/{role}/{portrait}.png",
                "portrait",
            )
            for portrait in portraits
        )
    specs.append(AssetSpec("stage.backdrop.lossless_soul", "backdrops/lossless_soul.png", "backdrop"))
    specs.extend(
        AssetSpec(f"cutscene.choice.icon.{choice}", f"icons/choices/{choice}.png", "icon")
        for choice in CHOICES
    )
    return tuple(specs)


def validate_registry(specs: tuple[AssetSpec, ...]) -> None:
    if len(specs) != EXPECTED_ASSET_COUNT:
        raise SystemExit(f"registry has {len(specs)} assets, expected {EXPECTED_ASSET_COUNT}")
    keys = [spec.key for spec in specs]
    files = [spec.file for spec in specs]
    if len(set(keys)) != len(keys):
        raise SystemExit("registry contains duplicate semantic keys")
    if len(set(files)) != len(files):
        raise SystemExit("registry contains duplicate file paths")
    for spec in specs:
        if not spec.key or not SAFE_FILE_RE.fullmatch(spec.file) or ".." in spec.file:
            raise SystemExit(f"unsafe registry row: {spec}")
    counts = {usage: sum(spec.usage == usage for spec in specs) for usage in ("backdrop", "icon", "portrait")}
    if counts != {"backdrop": 34, "icon": 17, "portrait": 30}:
        raise SystemExit(f"unexpected usage inventory: {counts}")


def validate_dimensions(spec: AssetSpec, size: tuple[int, int]) -> None:
    width, height = size
    if spec.usage == "icon":
        if size != (32, 32):
            raise SystemExit(f"{spec.file}: icon is {width}x{height}, expected 32x32")
        return
    if spec.usage == "portrait":
        if not (48 <= width <= 256 and 64 <= height <= 256 and 0.45 <= width / height <= 1.2):
            raise SystemExit(f"{spec.file}: unreasonable portrait dimensions {width}x{height}")
        return
    if size != (640, 360):
        raise SystemExit(f"{spec.file}: backdrop is {width}x{height}, expected 640x360")


def validate_backdrop_pixels(spec: AssetSpec, image: Image.Image) -> None:
    rgba = image.convert("RGBA")
    if rgba.getchannel("A").getextrema() != (255, 255):
        raise SystemExit(f"{spec.file}: backdrop must be fully opaque")

    width, height = rgba.size
    data = rgba.tobytes()

    def is_white(x: int, y: int) -> bool:
        offset = (y * width + x) * 4
        return data[offset] >= 240 and data[offset + 1] >= 240 and data[offset + 2] >= 240

    edge_white = {
        "top": sum(is_white(x, 0) for x in range(width)) / width,
        "bottom": sum(is_white(x, height - 1) for x in range(width)) / width,
        "left": sum(is_white(0, y) for y in range(height)) / height,
        "right": sum(is_white(width - 1, y) for y in range(height)) / height,
    }
    for edge, white_fraction in edge_white.items():
        if white_fraction >= 0.8:
            raise SystemExit(f"{spec.file}: backdrop has a white {edge} border")


def validate_png(spec: AssetSpec) -> str:
    path = ASSET_ROOT / spec.file
    if not path.is_file() or path.is_symlink():
        raise SystemExit(f"missing regular PNG: {spec.file}")
    try:
        with Image.open(path) as image:
            if image.format != "PNG":
                raise SystemExit(f"{spec.file}: expected PNG, decoded {image.format}")
            size = image.size
            image.verify()
        validate_dimensions(spec, size)
        if spec.usage == "backdrop":
            with Image.open(path) as image:
                validate_backdrop_pixels(spec, image)
    except (OSError, UnidentifiedImageError) as error:
        raise SystemExit(f"{spec.file}: unreadable PNG: {error}") from error
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_payload(specs: tuple[AssetSpec, ...]) -> dict[str, object]:
    entries: dict[str, dict[str, str]] = {}
    for spec in specs:
        entries[spec.key] = {"file": spec.file, "sha256": validate_png(spec)}
    return {
        "format_version": MANIFEST_FORMAT,
        "asset_count": EXPECTED_ASSET_COUNT,
        "assets": entries,
    }


def encoded_manifest(payload: dict[str, object]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def validate_png_inventory(specs: tuple[AssetSpec, ...]) -> None:
    expected = {spec.file for spec in specs}
    actual = {path.relative_to(ASSET_ROOT).as_posix() for path in ASSET_ROOT.rglob("*.png")}
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        details = []
        if missing:
            details.append(f"missing={missing}")
        if extra:
            details.append(f"extra={extra}")
        raise SystemExit("story PNG inventory mismatch: " + "; ".join(details))


def validate_manifest_shape(data: object, specs: tuple[AssetSpec, ...]) -> None:
    if not isinstance(data, dict) or set(data) != {"format_version", "asset_count", "assets"}:
        raise SystemExit("manifest root must contain exactly format_version, asset_count, and assets")
    if data["format_version"] != MANIFEST_FORMAT or data["asset_count"] != EXPECTED_ASSET_COUNT:
        raise SystemExit("manifest format_version or asset_count is invalid")
    assets = data["assets"]
    if not isinstance(assets, dict) or set(assets) != {spec.key for spec in specs}:
        raise SystemExit("manifest semantic keys do not exactly match the story-art registry")
    for spec in specs:
        entry = assets[spec.key]
        if not isinstance(entry, dict) or set(entry) != {"file", "sha256"}:
            raise SystemExit(f"{spec.key}: manifest entry must contain exactly file and sha256")
        if entry["file"] != spec.file or not isinstance(entry["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
            raise SystemExit(f"{spec.key}: manifest path or sha256 syntax is invalid")


def verify_manifest(expected: dict[str, object], specs: tuple[AssetSpec, ...]) -> None:
    if not MANIFEST_PATH.is_file():
        raise SystemExit(f"missing manifest: {MANIFEST_PATH.relative_to(AR_ROOT)}")
    raw = MANIFEST_PATH.read_bytes()
    try:
        decoded = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SystemExit(f"manifest is not strict UTF-8 JSON: {error}") from error
    validate_manifest_shape(decoded, specs)
    canonical = encoded_manifest(expected)
    if raw != canonical:
        raise SystemExit("manifest is stale or not canonically encoded; run with --write-manifest")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-manifest",
        action="store_true",
        help="replace manifest.json with canonical paths and current PNG hashes",
    )
    args = parser.parse_args()

    specs = asset_specs()
    validate_registry(specs)
    validate_png_inventory(specs)
    expected = manifest_payload(specs)
    if args.write_manifest:
        MANIFEST_PATH.write_bytes(encoded_manifest(expected))
        print(f"wrote {MANIFEST_PATH.relative_to(AR_ROOT)}")
    verify_manifest(expected, specs)
    print("verified 81 MX-story assets: 34 backdrops, 30 portraits, 17 icons")


if __name__ == "__main__":
    main()
