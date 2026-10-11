"""Verify the Linux game binary's shared-library closure.

The Linux client statically links raylib, libwebsockets, and OpenSSL
(vendor/*/PROVENANCE.md), so its only runtime sonames are the base system
ones every distro and the Steam Linux Runtime provide. A new NEEDED entry
means a dependency leaked back in (the 2026-10-11 Steam Deck launch failure
was libssl.so.3), so the Steam depot, CI, and public release lanes fail here
instead of shipping it.

usage: python3 tools/verify_linux_binary.py [path/to/archrogue]
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ALLOWED_NEEDED = {
    "libX11.so.6",
    "libm.so.6",
    "libc.so.6",
    "ld-linux-x86-64.so.2",
}


def needed(path: Path) -> list[str]:
    output = subprocess.run(
        ["readelf", "-d", str(path)], check=True, capture_output=True, text=True
    ).stdout
    return re.findall(r"\(NEEDED\)\s+Shared library: \[([^\]]+)\]", output)


def main(argv: list[str]) -> int:
    path = Path(argv[1] if len(argv) > 1 else "build/archrogue")
    if not path.is_file():
        raise SystemExit(f"{path}: not found; build it first")
    libs = needed(path)
    unexpected = sorted(set(libs) - ALLOWED_NEEDED)
    if unexpected:
        raise SystemExit(
            f"{path} depends on shared libraries outside the base-system allowlist: "
            f"{unexpected} (allowed: {sorted(ALLOWED_NEEDED)})"
        )
    forbidden = sorted(
        set(
            re.findall(
                r"__isoc23_[A-Za-z0-9_]+",
                subprocess.run(
                    ["nm", "-D", "--undefined-only", str(path)],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout,
            )
        )
    )
    if forbidden:
        raise SystemExit(f"{path} imports glibc C23-only symbols: {forbidden}")
    print(f"Linux binary verified: NEEDED {libs}, no __isoc23 imports")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
