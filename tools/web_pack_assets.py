#!/usr/bin/env python3
"""Split assets/ into the web core payload and lazily fetched packs.

Core staging (everything not packed) ships inside the Emscripten preload
.data and counts against the declared initial-download budget. Packs are
content-addressed single-blob files fetched on demand and written into MEMFS;
each manifest entry lists the actor textures and semantic SFX banks that wasm
must adopt after all of that pack's files are resident.

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
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
ASSETS_ROOT = REPO_ROOT / "assets"
SFX_ROOT = ASSETS_ROOT / "audio" / "sfx"
SFX_MANIFEST = SFX_ROOT / "manifest.json"

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

# The boot/UI set and one semantic fallback for every lazy SFX family. Web
# stages one authored PCM variant of each bank at 24 kHz stereo so the set is
# immediately playable without carrying every variation/sample in the initial
# payload; manifest.json always remains there too. Canonical assets, native
# builds, and every lazy packed WAV remain authored 48 kHz stereo.
CORE_SFX_BANKS = {
    "ui_navigate", "ui_confirm", "ui_back", "ui_reject", "ui_equip", "ui_purchase",
    "run_start", "level_up", "victory", "story_consequence", "relic_recovered",
    "epilogue_bell", "player_hurt_light", "player_hurt_heavy", "player_death",
    "melee_swing_arcanist", "dash_cloth_light", "warden_guard_bolt", "arcane_cast",
    "shadow_cast", "impact_generic",
    "item_pickup_common", "enemy_attack_light", "boss_engage", "door_open",
    "trap_spike", "shrine_mending", "step_boot_grass", "potion_drink",
}

ARCHETYPE_SFX_BANKS = {
    "warden": ["melee_swing_warden", "dash_armored", "shield_block", "warden_time_skip"],
    "rogue": ["melee_swing_rogue", "rogue_bell_cast", "rogue_bell_detonate", "rogue_stealth"],
    "arcanist": ["dash_arcane", "fire_cast", "frost_cast", "arcanist_nova"],
    "acolyte": ["melee_swing_acolyte", "dash_occult", "acolyte_spirit_call"],
    "ranger": [
        "melee_swing_ranger", "bow_release_light", "bow_release_heavy", "arrow_volley",
        "physical_throw", "ranger_beast_summon", "ranger_beast_command",
    ],
}

BOSS_SFX_BANKS = [
    "boss_defeat", "ash_gallows_cleave", "ash_gallows_nova", "mycelial_spore_volley",
    "rime_frost_fan", "void_arcane_lance", "gate_tyrant_strike", "gate_tyrant_volley",
    "boss_gate_close", "boss_gate_open",
]

# Kept in the core payload even inside packed actor directories: the Select
# carousel needs every archetype preview at boot.
CORE_KEEP_FILENAMES = {"preview_idle.png"}


def sfx_manifest_banks() -> dict[str, dict[str, Any]]:
    manifest = json.loads(SFX_MANIFEST.read_text())
    banks = manifest.get("banks")
    if not isinstance(banks, dict) or not banks:
        raise SystemExit(f"web-pack: invalid SFX manifest banks: {SFX_MANIFEST}")
    return banks


def pack_definitions(sfx_banks: dict[str, dict[str, Any]]) -> dict[str, dict[str, list[str]]]:
    packs: dict[str, dict[str, list[str]]] = {}
    assigned = set(CORE_SFX_BANKS)
    for actor in ARCHETYPES:
        banks = ARCHETYPE_SFX_BANKS[actor]
        packs[f"archetype-{actor}"] = {"actors": [actor], "sfx_banks": banks}
        assigned.update(banks)
    packs["social"] = {"actors": SOCIAL_ACTORS, "sfx_banks": ["bar_toast"]}
    assigned.add("bar_toast")
    packs["bosses"] = {"actors": BOSS_ACTORS, "sfx_banks": BOSS_SFX_BANKS}
    assigned.update(BOSS_SFX_BANKS)

    known = set(sfx_banks)
    unknown = assigned - known
    if unknown:
        raise SystemExit(f"web-pack: assigned unknown SFX banks: {', '.join(sorted(unknown))}")
    packs["sfx-world"] = {
        "actors": [],
        "sfx_banks": sorted((known - assigned) | CORE_SFX_BANKS),
    }

    memberships: dict[str, list[str]] = {bank: [] for bank in known}
    for name, definition in packs.items():
        for bank in definition["sfx_banks"]:
            if bank not in known:
                raise SystemExit(f"web-pack: pack {name} references unknown SFX bank {bank}")
            memberships[bank].append(name)
    for bank, owners in memberships.items():
        expected = ["sfx-world"] if bank in CORE_SFX_BANKS else None
        if expected is not None and owners != expected:
            raise SystemExit(f"web-pack: core SFX bank {bank} must upgrade only from sfx-world")
        if expected is None and len(owners) != 1:
            raise SystemExit(f"web-pack: non-core SFX bank {bank} must belong to exactly one pack")
    return packs


def actor_pack_files(actor: str) -> list[Path]:
    directory = ASSETS_ROOT / "actors" / actor
    if not directory.is_dir():
        raise SystemExit(f"web-pack: missing actor directory: {directory}")
    files = [
        path for path in sorted(directory.rglob("*"))
        if path.is_file() and path.name not in CORE_KEEP_FILENAMES
    ]
    if not files:
        raise SystemExit(f"web-pack: actor directory has no packable files: {directory}")
    return files


def sfx_bank_files(bank: str, metadata: dict[str, Any]) -> list[Path]:
    files = metadata.get("files")
    if not isinstance(files, list) or not files:
        raise SystemExit(f"web-pack: SFX bank {bank} has no manifest files")
    paths = []
    for entry in files:
        filename = entry.get("file") if isinstance(entry, dict) else None
        path = SFX_ROOT / filename if isinstance(filename, str) else None
        if path is None or not path.is_file():
            raise SystemExit(f"web-pack: SFX bank {bank} references missing file {filename}")
        paths.append(path)
    return paths


def core_sfx_paths(sfx_banks: dict[str, dict[str, Any]]) -> dict[str, Path]:
    return {
        bank: min(sfx_bank_files(bank, sfx_banks[bank]), key=lambda path: path.stat().st_size)
        for bank in CORE_SFX_BANKS
    }


def compact_core_sfx_wav(path: Path) -> bytes:
    """Downsample a staged 48 kHz stereo PCM WAV to 24 kHz, preserving duration."""
    data = path.read_bytes()
    if (
        len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE"
        or data[12:16] != b"fmt " or data[36:40] != b"data"
    ):
        raise SystemExit(f"web-pack: core SFX has an unsupported WAV layout: {path}")
    audio_format, channels = struct.unpack_from("<HH", data, 20)
    sample_rate = struct.unpack_from("<I", data, 24)[0]
    block_align, bits = struct.unpack_from("<HH", data, 32)
    if audio_format != 1 or channels != 2 or sample_rate != 48000 or block_align != 4 or bits != 16:
        raise SystemExit(f"web-pack: core SFX is not 48 kHz stereo PCM16: {path}")
    pcm_size = struct.unpack_from("<I", data, 40)[0]
    pcm = data[44:44 + pcm_size]
    if len(pcm) != pcm_size or pcm_size % 4 != 0:
        raise SystemExit(f"web-pack: malformed core SFX PCM payload: {path}")
    compact_pcm = b"".join(pcm[offset:offset + 4] for offset in range(0, len(pcm), 8))
    compact = bytearray(data[:44])
    compact.extend(compact_pcm)
    struct.pack_into("<I", compact, 4, len(compact) - 8)
    struct.pack_into("<I", compact, 24, 24000)
    struct.pack_into("<I", compact, 28, 24000 * 4)
    struct.pack_into("<I", compact, 40, len(compact_pcm))
    return bytes(compact)


def build_pack(
    name: str,
    definition: dict[str, list[str]],
    sfx_banks: dict[str, dict[str, Any]],
    staged_core_sfx: dict[str, Path],
    output_dir: Path,
) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    blob = bytearray()
    files: list[Path] = []
    for actor in definition["actors"]:
        files.extend(actor_pack_files(actor))
    for bank in definition["sfx_banks"]:
        staged_path = staged_core_sfx.get(bank)
        files.extend(path for path in sfx_bank_files(bank, sfx_banks[bank]) if path != staged_path)
    if not files:
        raise SystemExit(f"web-pack: pack {name} has no files")

    for path in files:
        data = path.read_bytes()
        relative = path.relative_to(REPO_ROOT).as_posix()
        entries.append({"path": f"/{relative}", "offset": len(blob), "size": len(data)})
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
        "actors": definition["actors"],
        "sfx_banks": definition["sfx_banks"],
        "files": len(entries),
    }


def stage_core(
    staging: Path,
    definitions: dict[str, dict[str, list[str]]],
    sfx_banks: dict[str, dict[str, Any]],
    staged_core_sfx: dict[str, Path],
) -> tuple[int, int]:
    if staging.exists():
        shutil.rmtree(staging)
    packed_actor_dirs = {
        ASSETS_ROOT / "actors" / actor
        for definition in definitions.values()
        for actor in definition["actors"]
    }
    core_sfx_files = set(staged_core_sfx.values())
    packed_sfx_files = {
        path
        for definition in definitions.values()
        for bank in definition["sfx_banks"]
        for path in sfx_bank_files(bank, sfx_banks[bank])
        if path != staged_core_sfx.get(bank)
    }
    all_sfx_files = {
        path
        for bank, metadata in sfx_banks.items()
        for path in sfx_bank_files(bank, metadata)
    }
    total_bytes = 0
    total_files = 0
    for path in sorted(ASSETS_ROOT.rglob("*")):
        if not path.is_file():
            continue
        if path.is_symlink():
            raise SystemExit(f"web-pack: refusing symlink in assets: {path}")
        in_packed_actor_dir = any(parent in packed_actor_dirs for parent in path.parents)
        if in_packed_actor_dir and path.name not in CORE_KEEP_FILENAMES:
            continue
        if path in packed_sfx_files:
            continue
        if path in all_sfx_files and path not in core_sfx_files:
            continue
        destination = staging / path.relative_to(ASSETS_ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if path in core_sfx_files:
            staged_data = compact_core_sfx_wav(path)
            destination.write_bytes(staged_data)
            total_bytes += len(staged_data)
        else:
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

    sfx_banks = sfx_manifest_banks()
    definitions = pack_definitions(sfx_banks)
    staged_core_sfx = core_sfx_paths(sfx_banks)
    staging = Path(args.staging)
    packs_dir = Path(args.packs)
    if packs_dir.exists():
        shutil.rmtree(packs_dir)
    packs_dir.mkdir(parents=True, exist_ok=True)

    core_bytes, core_files = stage_core(staging, definitions, sfx_banks, staged_core_sfx)
    manifest: dict[str, Any] = {
        "schema": 2,
        "core_sfx_banks": sorted(CORE_SFX_BANKS),
        "packs": {},
    }
    packed_bytes = 0
    for name, definition in sorted(definitions.items()):
        info = build_pack(name, definition, sfx_banks, staged_core_sfx, packs_dir)
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
        print(
            f"web-pack:   {name}: {info['bytes']/1e6:.1f} MB, {info['files']} files, "
            f"{len(info['actors'])} actors, {len(info['sfx_banks'])} SFX banks"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
