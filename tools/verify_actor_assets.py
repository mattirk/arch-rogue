#!/usr/bin/env python3
"""Verify the self-contained native-resolution Odin actor pack."""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from typing import TypeAlias, cast

ROOT = Path(__file__).resolve().parents[1]
ACTOR_DIR = ROOT / "assets" / "actors"
MANIFEST = ACTOR_DIR / "manifest.json"
DIRECTION_ROWS = 8
JsonValue: TypeAlias = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]


def png_size(data: bytes) -> tuple[int, int]:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ValueError("not a canonical PNG")
    return struct.unpack(">II", data[16:24])


def main() -> int:
    manifest = cast(dict[str, JsonValue], json.loads(MANIFEST.read_text(encoding="utf-8")))
    if manifest.get("format") != 2 or manifest.get("native_cells") is not True:
        raise SystemExit("actor manifest is not a format-2 native-resolution pack")

    actors_value = manifest.get("actors")
    if not isinstance(actors_value, dict) or not actors_value:
        raise SystemExit("actor manifest has no actors")
    actors = cast(dict[str, dict[str, JsonValue]], actors_value)

    total_pixels = 0
    for name, actor in actors.items():
        cell = actor.get("cell")
        source_canvas = actor.get("source_canvas")
        if not isinstance(cell, int) or cell <= 0:
            raise SystemExit(f"{name}: missing native cell")
        if source_canvas != [cell, cell]:
            raise SystemExit(
                f"{name}: source canvas {source_canvas} was resampled to cell {cell}"
            )
        canvas_world = actor.get("canvas_world")
        if not isinstance(canvas_world, (int, float)) or canvas_world <= 0:
            raise SystemExit(f"{name}: invalid world canvas")

        clips_value = actor.get("clips")
        if not isinstance(clips_value, dict) or not clips_value:
            raise SystemExit(f"{name}: no clips")
        clips = cast(dict[str, dict[str, JsonValue]], clips_value)
        expected_files: set[str] = set()
        for clip_name, clip in clips.items():
            frames = clip.get("frames")
            rows = clip.get("rows")
            expected_rows = 1 if clip_name == "preview_idle" else DIRECTION_ROWS
            if not isinstance(frames, int) or frames <= 0:
                raise SystemExit(f"{name}/{clip_name}: invalid frame count")
            if not isinstance(rows, int) or rows != expected_rows:
                raise SystemExit(
                    f"{name}/{clip_name}: {rows} rows, expected {expected_rows}"
                )

            file_name = f"{clip_name}.png"
            expected_files.add(file_name)
            path = ACTOR_DIR / name / file_name
            data = path.read_bytes()
            size = png_size(data)
            expected_size = (frames * cell, rows * cell)
            if size != expected_size:
                raise SystemExit(
                    f"{name}/{file_name}: size {size}, expected {expected_size}"
                )
            digest = hashlib.sha256(data).hexdigest()
            if digest != clip.get("sha256"):
                raise SystemExit(f"{name}/{file_name}: SHA-256 mismatch")
            total_pixels += size[0] * size[1]

        actor_path = ACTOR_DIR / name
        actual_files = {path.name for path in actor_path.glob("*.png")}
        if actual_files != expected_files:
            raise SystemExit(f"{name}: sheet set differs: expected={sorted(expected_files)} actual={sorted(actual_files)}")

    mib = total_pixels * 4 / (1024 * 1024)
    sheet_count = sum(len(cast(dict[str, JsonValue], actor["clips"])) for actor in actors.values())
    print(f"Native actor assets verified: {len(actors)} actors, {sheet_count} sheets, {mib:.1f} MiB decoded RGBA")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
