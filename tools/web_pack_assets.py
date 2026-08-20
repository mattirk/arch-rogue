#!/usr/bin/env python3
"""Split assets/ into the web core payload and lazily fetched packs.

Core staging (everything not packed) ships inside the Emscripten preload
.data and counts against the declared initial-download budget. Packs are
content-addressed single-blob files fetched on demand at run start and
written into MEMFS; every pack lists the actor names it completes so the
wasm side can re-resolve just those sprites on arrival.

Pack blob format: b"ARPACK1\n" + u32le index length + UTF-8 JSON index
[{"path", "offset", "size"}] + concatenated file bytes. Offsets are relative
to the end of the index.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ASSETS_ROOT = REPO_ROOT / "assets"

MAGIC = b"ARPACK1\n"

ARCHETYPES = ["warden", "rogue", "arcanist", "acolyte", "ranger"]
SOCIAL_ACTORS = ["bar_dancer", "garden_frog", "lossless_soul", "shopkeeper", "story_guest"]
BOSS_ACTORS = [
    "ash_gallows_knight",
    "gate_tyrant",
    "mycelial_matron",
    "rime_chanter",
    "voidbound_rune_sentinel",
]

# Kept in the core payload even inside packed actor directories: the Select
# carousel needs every archetype preview at boot.
CORE_KEEP_FILENAMES = {"preview_idle.png"}


def pack_definitions() -> dict[str, list[str]]:
    packs: dict[str, list[str]] = {}
    for name in ARCHETYPES:
        packs[f"archetype-{name}"] = [name]
    packs["social"] = SOCIAL_ACTORS
    packs["bosses"] = BOSS_ACTORS
    return packs


def actor_pack_files(actor: str) -> list[Path]:
    directory = ASSETS_ROOT / "actors" / actor
    if not directory.is_dir():
        raise SystemExit(f"web-pack: missing actor directory: {directory}")
    files = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        if path.name in CORE_KEEP_FILENAMES:
            continue
        files.append(path)
    if not files:
        raise SystemExit(f"web-pack: actor directory has no packable files: {directory}")
    return files


def build_pack(name: str, actors: list[str], output_dir: Path) -> dict:
    entries = []
    blob = bytearray()
    for actor in actors:
        for path in actor_pack_files(actor):
            data = path.read_bytes()
            relative = path.relative_to(REPO_ROOT).as_posix()
            entries.append({
                "path": f"/{relative}",
                "offset": len(blob),
                "size": len(data),
            })
            blob.extend(data)
    index = json.dumps(entries, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload = MAGIC + struct.pack("<I", len(index)) + index + bytes(blob)
    digest = hashlib.sha256(payload).hexdigest()
    filename = f"{name}.{digest[:12]}.arpack"
    (output_dir / filename).write_bytes(payload)
    return {
        "url": f"packs/{filename}",
        "bytes": len(payload),
        "sha256": digest,
        "actors": actors,
        "files": len(entries),
    }


def stage_core(staging: Path) -> tuple[int, int]:
    if staging.exists():
        shutil.rmtree(staging)
    packed_dirs = {
        ASSETS_ROOT / "actors" / actor
        for actors in pack_definitions().values()
        for actor in actors
    }
    total_bytes = 0
    total_files = 0
    for path in sorted(ASSETS_ROOT.rglob("*")):
        if not path.is_file():
            continue
        if path.is_symlink():
            raise SystemExit(f"web-pack: refusing symlink in assets: {path}")
        in_packed_dir = any(parent in packed_dirs for parent in path.parents)
        if in_packed_dir and path.name not in CORE_KEEP_FILENAMES:
            continue
        destination = staging / path.relative_to(ASSETS_ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        total_bytes += path.stat().st_size
        total_files += 1
    return total_bytes, total_files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staging", required=True, help="core asset staging directory")
    parser.add_argument("--packs", required=True, help="pack output directory")
    parser.add_argument("--manifest", required=True, help="packs.json output path")
    args = parser.parse_args()

    staging = Path(args.staging)
    packs_dir = Path(args.packs)
    if packs_dir.exists():
        shutil.rmtree(packs_dir)
    packs_dir.mkdir(parents=True, exist_ok=True)

    core_bytes, core_files = stage_core(staging)

    manifest: dict = {"schema": 1, "packs": {}}
    packed_bytes = 0
    for name, actors in sorted(pack_definitions().items()):
        info = build_pack(name, actors, packs_dir)
        manifest["packs"][name] = info
        packed_bytes += info["bytes"]

    manifest_path = Path(args.manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    print(
        f"web-pack: core {core_files} files {core_bytes/1e6:.1f} MB; "
        f"{len(manifest['packs'])} packs {packed_bytes/1e6:.1f} MB"
    )
    for name, info in sorted(manifest["packs"].items()):
        print(f"web-pack:   {name}: {info['bytes']/1e6:.1f} MB, {info['files']} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
