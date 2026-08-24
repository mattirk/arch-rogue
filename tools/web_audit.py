#!/usr/bin/env python3
"""Strict audit of the built web distribution.

Enforced contracts (from web/toolchain.properties and AGENTS.md):
  * declared initial-download budget — index.html + runtime js + wasm + core
    .data + packs.json, measured on Brotli sizes when .br siblings exist;
  * pinned Emscripten heap — the wasm memory section must declare exactly
    INITIAL_MEMORY with growth disabled (min == max), and the runtime js must
    not contain memory-growth support;
  * no ASYNCIFY in the production runtime;
  * content addressing — hashed filenames must match file digests, the html
    file manifest must resolve, and packs.json entries must match the pack
    blobs byte-for-byte;
  * no runtime CDN dependency — no absolute-URL fetches in html/js.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
CORE_SFX_BANKS = {
    "ui_navigate", "ui_confirm", "ui_back", "ui_reject", "ui_equip", "ui_purchase",
    "run_start", "level_up", "victory", "story_consequence", "relic_recovered",
    "epilogue_bell", "player_hurt_light", "player_hurt_heavy", "player_death",
    "melee_swing_arcanist", "dash_cloth_light", "warden_guard_bolt", "arcane_cast",
    "shadow_cast", "impact_generic",
    "item_pickup_common", "enemy_attack_light", "boss_engage", "door_open",
    "trap_spike", "shrine_mending", "step_boot_grass", "potion_drink",
}

failures: list[str] = []


def fail(message: str) -> None:
    failures.append(message)
    print(f"web-audit: FAIL {message}")


def note(message: str) -> None:
    print(f"web-audit: {message}")


def read_properties(path: Path) -> dict[str, str]:
    properties: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        properties[key.strip()] = value.strip()
    return properties


def wire_size(path: Path) -> tuple[int, bool]:
    """Bytes on the wire: the .br sibling when present, else the raw file."""
    brotli = path.with_name(path.name + ".br")
    if brotli.is_file():
        return brotli.stat().st_size, True
    return path.stat().st_size, False


def parse_arpack_index(data: bytes) -> list[dict[str, Any]]:
    if not data.startswith(b"ARPACK1\n") or len(data) < 12:
        raise ValueError("bad magic/header")
    index_length = int.from_bytes(data[8:12], "little")
    index_end = 12 + index_length
    if index_end > len(data):
        raise ValueError("index exceeds payload")
    index = json.loads(data[12:index_end])
    if not isinstance(index, list):
        raise ValueError("index is not an array")
    for entry in index:
        if not isinstance(entry, dict) or not {"path", "offset", "size"} <= entry.keys():
            raise ValueError("index entry metadata is incomplete")
        if not isinstance(entry["path"], str) or not entry["path"].startswith("/assets/"):
            raise ValueError("index entry path is invalid")
        if not isinstance(entry["offset"], int) or not isinstance(entry["size"], int):
            raise ValueError("index entry range is invalid")
        if entry["offset"] < 0 or entry["size"] < 0 or index_end + entry["offset"] + entry["size"] > len(data):
            raise ValueError("index entry exceeds payload")
    return index


def parse_wasm_memory_limits(wasm: bytes) -> tuple[int, int | None]:
    """Return (initial_pages, max_pages_or_None) from the memory section."""
    if wasm[:4] != b"\0asm":
        raise ValueError("not a wasm binary")

    offset = 8

    def read_leb() -> int:
        nonlocal offset
        result = 0
        shift = 0
        while True:
            byte = wasm[offset]
            offset += 1
            result |= (byte & 0x7F) << shift
            if not byte & 0x80:
                return result
            shift += 7

    while offset < len(wasm):
        section_id = wasm[offset]
        offset += 1
        size = read_leb()
        body_end = offset + size
        if section_id == 5:  # memory section
            count = read_leb()
            if count < 1:
                raise ValueError("empty memory section")
            flags = read_leb()
            initial = read_leb()
            maximum = read_leb() if flags & 0x1 else None
            return initial, maximum
        if section_id == 2:  # import section may import memory instead
            count = read_leb()
            for _ in range(count):
                module_len = read_leb(); offset += module_len
                name_len = read_leb(); offset += name_len
                kind = wasm[offset]; offset += 1
                if kind == 0x00:  # function
                    read_leb()
                elif kind == 0x01:  # table
                    offset += 1
                    flags = read_leb(); read_leb()
                    if flags & 0x1:
                        read_leb()
                elif kind == 0x02:  # memory
                    flags = read_leb()
                    initial = read_leb()
                    maximum = read_leb() if flags & 0x1 else None
                    return initial, maximum
                elif kind == 0x03:  # global
                    offset += 2
        offset = body_end
    raise ValueError("no memory section found")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", default="build/web/dist")
    args = parser.parse_args()

    properties = read_properties(REPO_ROOT / "web" / "toolchain.properties")
    budget = int(properties["WEB_INITIAL_DOWNLOAD_BUDGET_BYTES"])
    initial_memory = int(properties["WEB_INITIAL_MEMORY_BYTES"])
    allow_growth = properties.get("WEB_ALLOW_MEMORY_GROWTH", "0") == "1"

    dist = Path(args.dist)
    index_html = dist / "index.html"
    if not index_html.is_file():
        fail(f"missing {index_html}")
        return finish()
    html = index_html.read_text()

    # --- resolve the content-addressed runtime files ---------------------
    manifest_match = re.search(r"window\.AR_FILE_MANIFEST\s*=\s*(\{[^<]*?\});", html)
    if not manifest_match:
        fail("index.html does not declare AR_FILE_MANIFEST")
        return finish()
    file_manifest = json.loads(manifest_match.group(1))

    script_match = re.search(r'src=["\']?([^"\' >]+\.js)', html)
    if not script_match:
        fail("index.html has no runtime script reference")
        return finish()
    js_name = script_match.group(1)
    js_path = dist / js_name
    if not js_path.is_file():
        fail(f"runtime script {js_name} referenced by index.html is missing")
        return finish()

    initial_files = {"index.html": index_html, js_name: js_path}
    for logical, hashed in file_manifest.items():
        initial_files[hashed] = dist / hashed
        if not (dist / hashed).is_file():
            fail(f"AR_FILE_MANIFEST maps {logical} to missing file {hashed}")
    packs_json = dist / "packs.json"
    if packs_json.is_file():
        initial_files["packs.json"] = packs_json
    else:
        fail("missing packs.json")

    # --- content addressing ----------------------------------------------
    for name, path in initial_files.items():
        if name in ("index.html", "packs.json") or not path.is_file():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        match = re.search(r"-([0-9a-f]{12})\.", name)
        if not match:
            fail(f"{name} is not content-addressed")
        elif match.group(1) != digest[:12]:
            fail(f"{name} digest prefix mismatch ({digest[:12]})")

    # --- packs -------------------------------------------------------------
    if packs_json.is_file():
        packs = json.loads(packs_json.read_text())
        if packs.get("schema") != 2 or not packs.get("packs"):
            fail("packs.json schema/content invalid")
        elif set(packs.get("core_sfx_banks", [])) != CORE_SFX_BANKS:
            fail("packs.json core_sfx_banks metadata differs from the required staged set")
        else:
            sfx_manifest = json.loads((REPO_ROOT / "assets" / "audio" / "sfx" / "manifest.json").read_text())
            canonical_banks = sfx_manifest["banks"]
            bank_owners: dict[str, list[str]] = {}
            bank_paths: dict[str, list[str]] = {}
            all_pack_paths: set[str] = set()
            for name, info in sorted(packs["packs"].items()):
                actors = info.get("actors")
                sfx_banks = info.get("sfx_banks")
                if not isinstance(actors, list) or not all(isinstance(actor, str) and actor for actor in actors):
                    fail(f"pack {name} has invalid/missing actors metadata")
                    actors = []
                if not isinstance(sfx_banks, list) or not all(isinstance(bank, str) and bank for bank in sfx_banks):
                    fail(f"pack {name} has invalid/missing sfx_banks metadata")
                    sfx_banks = []
                if not actors and not sfx_banks:
                    fail(f"pack {name} lists neither actors nor SFX banks")
                blob = dist / info["url"]
                if not blob.is_file():
                    fail(f"pack blob missing: {info['url']}")
                    continue
                data = blob.read_bytes()
                if len(data) != info["bytes"]:
                    fail(f"pack {name} size mismatch")
                if hashlib.sha256(data).hexdigest() != info["sha256"]:
                    fail(f"pack {name} digest mismatch")
                try:
                    index = parse_arpack_index(data)
                except (ValueError, json.JSONDecodeError) as error:
                    fail(f"pack {name} index invalid: {error}")
                    continue
                if len(index) != info.get("files"):
                    fail(f"pack {name} file count metadata mismatch")
                paths = [entry["path"] for entry in index]
                duplicate_paths = all_pack_paths.intersection(paths)
                if duplicate_paths:
                    fail(f"pack {name} duplicates paths from another pack: {sorted(duplicate_paths)}")
                all_pack_paths.update(paths)
                for actor in actors:
                    prefix = f"/assets/actors/{actor}/"
                    if not any(path.startswith(prefix) for path in paths):
                        fail(f"pack {name} actor metadata has no files: {actor}")
                for bank in sfx_banks:
                    metadata = canonical_banks.get(bank)
                    if not isinstance(metadata, dict):
                        fail(f"pack {name} references unknown SFX bank {bank}")
                        metadata = {"files": []}
                    canonical_paths = {
                        f"/assets/audio/sfx/{entry['file']}"
                        for entry in metadata["files"]
                    }
                    matches = [path for path in paths if path in canonical_paths]
                    bank_owners.setdefault(bank, []).append(name)
                    bank_paths.setdefault(bank, []).extend(matches)

            if set(bank_owners) != set(canonical_banks):
                fail("pack SFX metadata does not cover every canonical bank")
            for bank, metadata in canonical_banks.items():
                owners = bank_owners.get(bank, [])
                canonical_files = {
                    f"/assets/audio/sfx/{entry['file']}"
                    for entry in metadata["files"]
                }
                expected_files = set(canonical_files)
                if bank in CORE_SFX_BANKS:
                    if owners != ["sfx-world"]:
                        fail(f"core SFX bank {bank} must upgrade only from sfx-world")
                    staged = min(metadata["files"], key=lambda entry: entry["byte_size"])["file"]
                    expected_files.remove(f"/assets/audio/sfx/{staged}")
                elif len(owners) != 1:
                    fail(f"non-core SFX bank {bank} must belong to exactly one pack")
                actual_files = set(bank_paths.get(bank, []))
                if actual_files != expected_files:
                    fail(f"pack variants for {bank} differ from canonical upgrade set")
            lazy_total = sum(info["bytes"] for info in packs["packs"].values())
            note(f"lazy packs: {len(packs['packs'])} totalling {lazy_total/1e6:.1f} MB (excluded from budget)")

    # --- initial-download budget ------------------------------------------
    total_wire = 0
    any_brotli = False
    for name, path in sorted(initial_files.items()):
        if not path.is_file():
            continue
        size, compressed = wire_size(path)
        any_brotli = any_brotli or compressed
        total_wire += size
        note(f"initial: {name} {size/1e6:.2f} MB {'(br)' if compressed else '(raw)'}")
    note(f"initial-download total {total_wire/1e6:.2f} MB vs budget {budget/1e6:.2f} MB")
    if total_wire > budget:
        fail(f"initial download {total_wire} bytes exceeds declared budget {budget}")
    if not any_brotli:
        note("warning: no .br siblings found; budget measured on raw sizes")

    # --- heap pin -----------------------------------------------------------
    wasm_files = [path for name, path in initial_files.items() if name.endswith(".wasm")]
    if not wasm_files:
        fail("no wasm file in the initial set")
    else:
        wasm = wasm_files[0].read_bytes()
        try:
            initial_pages, max_pages = parse_wasm_memory_limits(wasm)
            expected_pages = initial_memory // 65536
            if initial_pages != expected_pages:
                fail(f"wasm initial memory {initial_pages} pages != pinned {expected_pages}")
            if allow_growth:
                fail("toolchain contract must keep ALLOW_MEMORY_GROWTH=0")
            if max_pages != expected_pages:
                fail(f"wasm max memory {max_pages} pages != pinned {expected_pages} (growth must be disabled)")
            note(f"heap pin ok: {initial_pages} pages ({initial_pages*64//1024} MiB), growth disabled")
        except ValueError as error:
            fail(f"wasm memory parse failed: {error}")

    # --- runtime js contracts ----------------------------------------------
    if js_path.is_file():
        js = js_path.read_text(errors="replace")
        if "Asyncify" in js:
            fail("runtime js contains ASYNCIFY support")
        if "growMemory" in js:
            fail("runtime js contains memory growth support")
        for pattern in (r'fetch\(\s*["\']https?://', r'src\s*=\s*["\']https?://', r'new\s+URL\(\s*["\']https?://'):
            if re.search(pattern, js) or re.search(pattern, html):
                fail(f"absolute-URL runtime reference matches {pattern}")
        note("runtime js contracts ok (no ASYNCIFY, no growth, no CDN fetches)")

    return finish()


def finish() -> int:
    if failures:
        print(f"web-audit: {len(failures)} failure(s)")
        return 1
    print("web-audit: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
