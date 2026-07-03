"""Vendor the entire pygbag/pygame-web runtime locally.

pygbag's default build boots the browser app from a remote CDN
(``https://pygame-web.github.io/cdn/<version>/``): ``pythons.js`` (the bootstrap),
the CPython/Pyodide interpreter (``cpython<ver>/main.js`` + ``main.data`` +
``main.wasm``), the terminal modules (``vt.js``/``vtx.js`` + xterm under
``vt/``), and a few static assets. Depending on a remote CDN is what produced
the cross-origin-request errors, so this module downloads the whole runtime
tree into ``web/vendor/cdn/...`` (mirroring the CDN path layout) so the build
can be made fully same-origin.

Two references in pygbag's template (``browserfs.min.js`` and
``pygbag<version>.js``) 404 even on the official CDN — they are dead script
tags and BrowserFS is not used by the tarball-based app flow, so we emit empty
local stubs to silence those 404s.

Usage::

    python web/vendor_runtime.py            # download into web/vendor
    python web/vendor_runtime.py --force     # re-download even if present
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

DEFAULT_CDN = "https://pygame-web.github.io"
VENDOR_ROOT = Path(__file__).resolve().parent / "vendor"

# (path under the CDN host, is_stub).  Stubs are written locally as empty files
# because the CDN does not host them (dead template references).
RUNTIME_FILES: list[tuple[str, bool]] = [
    ("/cdn/0.9.3/pythons.js", False),
    ("/cdn/0.9.3/empty.html", False),
    ("/cdn/0.9.3/empty.ogg", False),
    ("/cdn/0.9.3/cpythonrc.py", False),
    ("/cdn/0.9.3/cpython312/main.js", False),
    ("/cdn/0.9.3/cpython312/main.data", False),
    ("/cdn/0.9.3/cpython312/main.wasm", False),
    ("/cdn/vt.js", False),
    ("/cdn/vtx.js", False),
    ("/cdn/vt/xterm.js", False),
    ("/cdn/vt/xterm.css", False),
    ("/cdn/vt/xterm-addon-image.js", False),
    ("/cdn/lib/index.html", False),
    # Dead template references that 404 on the official CDN; provide empty
    # stubs so the <script> tags resolve instead of producing console 404s.
    ("/cdn/0.9.3/browserfs.min.js", True),
    ("/cdn/0.9.3/pygbag0.9.3.js", True),
]


def _local_path(cdn_path: str, dest: Path) -> Path:
    # Mirror the CDN path (which always starts with /cdn/) under dest/cdn/.
    rel = cdn_path.lstrip("/")
    return dest / rel


def _download(cdn_path: str, base: str, dest_file: Path) -> int:
    url = base + cdn_path
    dest_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest_file.with_suffix(dest_file.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "arch-rogue-vendor/1.0"})
    with urllib.request.urlopen(req, timeout=180) as resp, open(tmp, "wb") as out:
        expected = resp.headers.get("content-length")
        total = 0
        while True:
            chunk = resp.read(1 << 18)
            if not chunk:
                break
            out.write(chunk)
            total += len(chunk)
    if expected is not None and int(expected) != total:
        raise OSError(f"size mismatch for {url}: got {total}, expected {expected}")
    tmp.replace(dest_file)
    return total


def vendor_runtime(
    dest: Path = VENDOR_ROOT,
    base: str = DEFAULT_CDN,
    force: bool = False,
    files: list[tuple[str, bool]] | None = None,
) -> list[Path]:
    """Download/stage the runtime tree into ``dest`` and return written paths."""
    dest = Path(dest)
    manifest = files if files is not None else RUNTIME_FILES
    written: list[Path] = []
    for cdn_path, is_stub in manifest:
        local = _local_path(cdn_path, dest)
        if is_stub:
            if force or not local.exists():
                local.parent.mkdir(parents=True, exist_ok=True)
                local.write_bytes(b"")
                print(f"stub  {cdn_path}")
            written.append(local)
            continue
        if local.exists() and not force:
            print(f"skip  {cdn_path}  ({local.stat().st_size}b)")
            written.append(local)
            continue
        size = _download(cdn_path, base, local)
        print(f"got   {cdn_path}  {size}b")
        written.append(local)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dest", default=str(VENDOR_ROOT), help="Vendor root dir.")
    parser.add_argument("--base", default=DEFAULT_CDN, help="CDN origin.")
    parser.add_argument(
        "--force", action="store_true", help="Re-download existing files."
    )
    args = parser.parse_args()
    try:
        vendor_runtime(Path(args.dest), args.base, args.force)
    except Exception as e:  # noqa: BLE001
        print(f"vendor failed: {e}", file=sys.stderr)
        return 1
    print(f"\nVendored runtime staged at {args.dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
