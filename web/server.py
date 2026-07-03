"""Static HTTP server that hosts the pygbag-built Arch Rogue web build.

Pyodide/pygbag builds rely on `SharedArrayBuffer` for their threaded runtime,
which browsers only expose to documents served with cross-origin isolation
headers:

  Cross-Origin-Opener-Policy: same-origin
  Cross-Origin-Embedder-Policy: credentialless   (or require-corp)

The COEP policy is important. `require-corp` is the stricter original form and
*blocks* any cross-origin subresource that does not itself send
`Cross-Origin-Resource-Policy: cross-origin` — this is what produces the
"cross-origin request blocked" error when a pygbag build pulls the Pyodide
runtime, fonts, or assets from a CDN. `credentialless` still grants the same
cross-origin isolation (so `SharedArrayBuffer` is available) but permits
cross-origin resources without requiring them to opt in, so it is the
sensible default for hosting a pygbag build. Pass `--coep require-corp` for the
strict form if every asset is vendored same-origin.

This server sets those headers on every response, plus correct MIME types for
`.wasm`, `.js`, `.data`, and other Pyodide asset types that the stdlib
`mimetypes` map gets wrong.

Usage::

    python web/server.py                     # serves web/dist on :8000
    python web/server.py --directory web/dist --port 8000
    python web/server.py --coep require-corp  # strict COEP (same-origin assets only)
    python web/server.py --no-isolation       # disable COOP/COEP (not recommended)
"""

from __future__ import annotations

import argparse
import functools
import http.server
import socketserver
import sys
from pathlib import Path

# MIME types the stdlib map either misclassifies or returns as a generic
# octet-stream; Pyodide will refuse to instantiate `.wasm` unless it is served
# as `application/wasm`.
EXTRA_MIME: dict[str, str] = {
    ".wasm": "application/wasm",
    ".js": "application/javascript",
    ".mjs": "application/javascript",
    ".data": "application/octet-stream",
    ".symbols": "application/octet-stream",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".css": "text/css",
    ".html": "text/html; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
}


# Valid COEP policies. "" means emit no COEP header (cross-origin isolation
# is then NOT active and Pyodide's SharedArrayBuffer will be unavailable).
COEP_POLICIES = ("credentialless", "require-corp", "")


def make_handler(coep: str):
    """Build a request handler class with the desired isolation headers.

    `coep` is one of `COEP_POLICIES`. `credentialless` (the default) grants
    cross-origin isolation while allowing cross-origin resources that have not
    opted into CORP — this is what fixes the cross-origin-request error on
    pygbag builds that fetch the Pyodide runtime from a CDN.
    """

    class _WebHostHandler(http.server.SimpleHTTPRequestHandler):
        def end_headers(self) -> None:
            # COOP is always emitted; it is harmless and is half of what the
            # browser needs to grant SharedArrayBuffer.
            self.send_header("Cross-Origin-Opener-Policy", "same-origin")
            if coep:
                self.send_header("Cross-Origin-Embedder-Policy", coep)
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            # Pyodide asset URLs are content-hashed, but during development a
            # no-cache policy avoids serving a stale build after `pygbag`.
            self.send_header("Cache-Control", "no-cache")
            super().end_headers()

        def guess_type(self, path: str) -> str:
            suffix = Path(path).suffix.lower()
            if suffix in EXTRA_MIME:
                return EXTRA_MIME[suffix]
            return super().guess_type(path) or "application/octet-stream"

    return _WebHostHandler


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve(
    directory: Path,
    host: str = "127.0.0.1",
    port: int = 8000,
    coep: str = "credentialless",
) -> ThreadingHTTPServer:
    """Start serving `directory` and return the (now-running) server.

    `coep` selects the Cross-Origin-Embedder-Policy value (see `COEP_POLICIES`).
    The default ``"credentialless"`` keeps cross-origin isolation (so Pyodide
    gets SharedArrayBuffer) while not blocking cross-origin resources, which is
    what fixes the cross-origin-request error on CDN-backed pygbag builds.

    The caller is responsible for `serve_forever()` / `shutdown()`.
    """
    if coep not in COEP_POLICIES:
        raise ValueError(f"invalid coep {coep!r}; expected one of {COEP_POLICIES}")
    directory = Path(directory).resolve()
    handler_cls = make_handler(coep)
    handler = functools.partial(handler_cls, directory=str(directory))
    server = ThreadingHTTPServer((host, port), handler)
    return server


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Host the Arch Rogue pygbag web build.",
    )
    parser.add_argument(
        "--directory",
        default=str(Path(__file__).resolve().parent / "dist"),
        help="Root directory to serve (default: web/dist).",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host.")
    parser.add_argument("--port", type=int, default=8000, help="Bind port.")
    parser.add_argument(
        "--coep",
        default="credentialless",
        choices=list(COEP_POLICIES),
        help=(
            "Cross-Origin-Embedder-Policy value. 'credentialless' (default) keeps "
            "isolation while allowing cross-origin resources and fixes the "
            "cross-origin-request error on CDN-backed pygbag builds. Use "
            "'require-corp' only if every asset is vendored same-origin. Empty "
            "string disables COEP (Pyodide SharedArrayBuffer will break)."
        ),
    )
    args = parser.parse_args()

    directory = Path(args.directory)
    if not directory.is_dir():
        print(
            f"Serve directory not found: {directory}\n"
            "Build the site first with:  python web/build.py\n"
            "Or pass --directory to an existing pygbag build.",
            file=sys.stderr,
        )
        return 2

    server = serve(
        directory,
        host=args.host,
        port=args.port,
        coep=args.coep,
    )
    root = f"http://{args.host}:{args.port}/"
    print(f"Serving {directory} at {root}")
    coep_label = args.coep or "(off)"
    print(f"Cross-origin isolation: COOP=same-origin, COEP={coep_label}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
