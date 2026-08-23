"""Verify the pinned glibc-2.35-compatible Linux raylib archive."""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINUX_VENDOR = ROOT / "vendor" / "raylib" / "linux"
ARCHIVE = LINUX_VENDOR / "libraylib.a"
CHECKSUMS = LINUX_VENDOR / "SHA256SUMS"
PROVENANCE = LINUX_VENDOR / "PROVENANCE.md"
TOOLCHAIN = ROOT / "toolchain.properties"
EXPECTED_MEMBERS = [
    "rcore.o",
    "rshapes.o",
    "rtextures.o",
    "rtext.o",
    "rglfw.o",
    "rmodels.o",
    "raudio.o",
]


def tool_output(*command: str) -> str:
    try:
        result: subprocess.CompletedProcess[str] = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as error:
        raise SystemExit(f"required archive tool is missing: {command[0]}") from error
    except subprocess.CalledProcessError as error:
        raise SystemExit(
            f"{' '.join(command)} failed with exit code {error.returncode}"
        ) from error
    return result.stdout


def main() -> int:
    properties = {}
    for line in TOOLCHAIN.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            properties[key] = value
    for name in ("ODIN_VERSION", "RAYLIB_VERSION"):
        if not properties.get(name):
            raise SystemExit(f"{name} is missing from {TOOLCHAIN}")

    provenance = PROVENANCE.read_text(encoding="utf-8")
    if f"odin-lang/Odin@{properties['ODIN_VERSION']}" not in provenance:
        raise SystemExit("Linux raylib provenance does not match pinned Odin version")
    if f"raylib {properties['RAYLIB_VERSION']}" not in provenance:
        raise SystemExit("Linux raylib provenance does not match pinned raylib version")

    checksum_fields = CHECKSUMS.read_text(encoding="utf-8").strip().split()
    if len(checksum_fields) != 2 or checksum_fields[1] != "libraylib.a":
        raise SystemExit("Linux raylib SHA256SUMS must contain exactly libraylib.a")
    expected_digest = checksum_fields[0]
    if re.fullmatch(r"[0-9a-f]{64}", expected_digest) is None:
        raise SystemExit("Linux raylib checksum is not one lowercase SHA-256 digest")

    actual_digest = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    if actual_digest != expected_digest:
        raise SystemExit(
            f"Linux raylib checksum mismatch: expected {expected_digest}, got {actual_digest}"
        )

    members = tool_output("ar", "t", str(ARCHIVE)).splitlines()
    if members != EXPECTED_MEMBERS:
        raise SystemExit(
            f"Linux raylib member set differs: expected={EXPECTED_MEMBERS} actual={members}"
        )

    undefined_symbols = tool_output("nm", "-u", str(ARCHIVE))
    forbidden = sorted(set(re.findall(r"__isoc23_[A-Za-z0-9_]+", undefined_symbols)))
    if forbidden:
        raise SystemExit(f"Linux raylib retains glibc C23-only imports: {forbidden}")

    print(
        f"Linux raylib archive verified: {len(members)} members, "
        + f"sha256={actual_digest}, no __isoc23 imports"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
