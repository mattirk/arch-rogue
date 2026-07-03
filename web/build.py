"""Build orchestrator that packages Arch Rogue for the web via pygbag.

pygbag (https://pypi.org/project/pygbag/) is the pygame community's official
tool for shipping pygame games to the browser: it builds the project wheel,
installs it into a Pyodide (CPython-on-WASM) environment, and emits a static
site (index.html + JS/WASM/data assets) that `web/server.py` can host.

pygbag expects the app entry as `main.py` at the app root and builds the
importable package from the `pyproject.toml` it finds there. Our package is
installed from the repo-root `pyproject.toml`, so this script temporarily
drops the driver (`web/main.py`) at the repo root as `main.py` for the
duration of the build, runs `pygbag --build`, stages the produced site into
`web/dist/`, and removes the temporary entry in a `finally` block.

Usage::

    python web/build.py                 # build into web/dist, then serve it
    python web/build.py --no-serve       # build only
    python web/build.py --port 8000      # serve on a custom port

Prerequisites::

    python -m pip install pygbag
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WEB_DIR = REPO / "web"
DRIVER = WEB_DIR / "main.py"
APP_ENTRY = REPO / "main.py"  # the temp entry pygbag needs at the app root
DEFAULT_DIST = WEB_DIR / "dist"
VENDOR_DIR = WEB_DIR / "vendor"
VENDOR_CDN = VENDOR_DIR / "cdn"  # mirrors the CDN host path layout
PYGBAG_OUT_CANDIDATES = (REPO / "build" / "web", REPO / "dist")

# The remote CDN pygbag bakes into index.html, and the local same-origin path we
# rewrite it to so the build runs fully vendored (no cross-origin requests).
REMOTE_CDN = "https://pygame-web.github.io/cdn/0.9.3/"
LOCAL_CDN = "/cdn/0.9.3/"

# web/ has no __init__.py; import the vendor module directly off the web dir.
sys.path.insert(0, str(WEB_DIR))
import vendor_runtime  # noqa: E402


def find_pygbag() -> list[str] | None:
    """Return a pygbag invocation (module or console script), or None."""
    try:
        import pygbag  # noqa: F401

        return [sys.executable, "-m", "pygbag"]
    except ImportError:
        pass
    bin_path = shutil.which("pygbag")
    if bin_path:
        return [bin_path]
    return None


def locate_build_output(start: Path) -> Path | None:
    """Find the directory pygbag produced (contains index.html)."""
    if not start.exists():
        return None
    if (start / "index.html").is_file():
        return start
    # pygbag has shipped output under different sub-paths across versions;
    # search a couple of levels rather than hard-coding one.
    for index in start.rglob("index.html"):
        return index.parent
    return None


def rewrite_index_html_local(
    dist: Path,
    remote: str = REMOTE_CDN,
    local: str = LOCAL_CDN,
) -> int:
    """Rewrite the remote CDN references in dist/index.html to the local
    same-origin path. Returns the number of references rewritten."""
    index_html = Path(dist) / "index.html"
    if not index_html.is_file():
        return 0
    text = index_html.read_text(encoding="utf-8")
    count = text.count(remote)
    if count:
        index_html.write_text(text.replace(remote, local), encoding="utf-8")
    return count


def merge_vendor_runtime(dist: Path, vendor_cdn: Path = VENDOR_CDN) -> bool:
    """Merge the vendored runtime tree into dist/cdn so /cdn/... is same-origin.

    Returns True if a merge happened.
    """
    vendor_cdn = Path(vendor_cdn)
    if not vendor_cdn.is_dir():
        return False
    shutil.copytree(vendor_cdn, Path(dist) / "cdn", dirs_exist_ok=True)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dist", default=str(DEFAULT_DIST), help="Stage site here.")
    parser.add_argument(
        "--no-serve", action="store_true", help="Build only; don't serve."
    )
    parser.add_argument("--host", default="127.0.0.1", help="Serve host.")
    parser.add_argument("--port", type=int, default=8000, help="Serve port.")
    parser.add_argument(
        "--coep",
        default="credentialless",
        choices=["credentialless", "require-corp", ""],
        help=(
            "Cross-Origin-Embedder-Policy for the host. 'credentialless' (default) "
            "keeps isolation while allowing cross-origin resources. With the "
            "vendored runtime everything is same-origin, so any value works."
        ),
    )
    parser.add_argument(
        "--no-vendor",
        action="store_true",
        help="Skip fetching/merging the vendored pygbag runtime (advanced).",
    )
    parser.add_argument(
        "--force-vendor",
        action="store_true",
        help="Re-download the vendored runtime even if already present.",
    )
    args = parser.parse_args()

    pygbag_cmd = find_pygbag()
    if pygbag_cmd is None:
        print(
            "pygbag was not found. Install it with:\n    python -m pip install pygbag",
            file=sys.stderr,
        )
        return 1

    if not args.no_vendor:
        if not (VENDOR_CDN / "0.9.3" / "cpython312" / "main.wasm").exists():
            print("Vendoring pygbag runtime (one-time download, ~21 MB)...")
        vendor_runtime.vendor_runtime(VENDOR_DIR, force=args.force_vendor)

    if APP_ENTRY.exists():
        print(
            f"Refusing to overwrite an existing {APP_ENTRY}.\n"
            "Remove it or build from a clean checkout.",
            file=sys.stderr,
        )
        return 1

    dist = Path(args.dist)
    build_cmd = pygbag_cmd + ["--build", str(REPO)]

    created_entry = False
    try:
        APP_ENTRY.write_text(DRIVER.read_text(encoding="utf-8"), encoding="utf-8")
        created_entry = True
        print("Running:", " ".join(build_cmd))
        rc = subprocess.call(build_cmd, cwd=str(REPO))
        if rc != 0:
            print("pygbag build failed.", file=sys.stderr)
            return rc

        produced = None
        for candidate in PYGBAG_OUT_CANDIDATES:
            produced = locate_build_output(candidate)
            if produced:
                break
        if produced is None:
            produced = locate_build_output(REPO / "build") or locate_build_output(REPO)
        if produced is None:
            print(
                "Could not locate the pygbag output (no index.html found under "
                f"{REPO / 'build'}).",
                file=sys.stderr,
            )
            return 1

        if dist.exists():
            shutil.rmtree(dist)
        shutil.copytree(produced, dist)
        print(f"Build staged at {dist}")

        # Rewrite the remote CDN references in index.html to the local
        # same-origin vendored path so the browser loads pythons.js, the
        # CPython runtime, terminals, and assets from our server instead of
        # the remote CDN (eliminating cross-origin requests entirely).
        count = rewrite_index_html_local(dist)
        if count:
            print(f"Rewrote {count} CDN reference(s) to local {LOCAL_CDN}")

        # Merge the vendored runtime tree into the site so /cdn/0.9.3/...
        # resolves same-origin. dirs_exist_ok merges into any existing cdn/.
        if not args.no_vendor and merge_vendor_runtime(dist):
            print(f"Merged vendored runtime into {dist / 'cdn'}")
    finally:
        if created_entry:
            try:
                APP_ENTRY.unlink()
            except OSError:
                pass

    if args.no_serve:
        return 0

    server_cmd = [
        sys.executable,
        str(WEB_DIR / "server.py"),
        "--directory",
        str(dist),
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--coep",
        args.coep,
    ]
    print("Hosting:", " ".join(server_cmd))
    return subprocess.call(server_cmd)


if __name__ == "__main__":
    raise SystemExit(main())
