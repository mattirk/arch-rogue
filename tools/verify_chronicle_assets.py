#!/usr/bin/env python3
"""Verify the exact PixelLab-authored MX-save Chronicle UI pack."""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "assets" / "ui" / "chronicle"
MANIFEST = ASSET_DIR / "manifest.json"


def png_size(data: bytes) -> tuple[int, int]:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ValueError("not a canonical PNG")
    return struct.unpack(">II", data[16:24])


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise SystemExit("unsupported Chronicle manifest schema")
    entries = manifest.get("assets", [])
    expected = {entry["file"] for entry in entries}
    actual = {path.name for path in ASSET_DIR.glob("*.png")}
    if actual != expected:
        raise SystemExit(f"Chronicle asset set differs: expected={sorted(expected)} actual={sorted(actual)}")
    keys: set[str] = set()
    for entry in entries:
        key = entry["key"]
        if key in keys:
            raise SystemExit(f"duplicate Chronicle key: {key}")
        keys.add(key)
        path = ASSET_DIR / entry["file"]
        data = path.read_bytes()
        size = png_size(data)
        expected_size = (entry["width"], entry["height"])
        if size != expected_size:
            raise SystemExit(f"{path.name}: size {size}, expected {expected_size}")
        digest = hashlib.sha256(data).hexdigest()
        if digest != entry["sha256"]:
            raise SystemExit(f"{path.name}: sha256 {digest}, expected {entry['sha256']}")
    print(f"Chronicle UI assets verified: {len(entries)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
