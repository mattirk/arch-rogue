#!/usr/bin/env python3
"""Local static server for the built web distribution.

Serves build/web/dist with production-shaped semantics: correct MIME types,
precompressed .br siblings when the client accepts Brotli, immutable caching
for content-addressed files, and no-cache for the mutable entry points
(index.html, packs.json). No cross-origin isolation headers are required —
web persistence deliberately avoids Wasm threads and SharedArrayBuffer.
"""

from __future__ import annotations

import argparse
import http.server
import socketserver
import sys
from pathlib import Path

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".wasm": "application/wasm",
    ".data": "application/octet-stream",
    ".arpack": "application/octet-stream",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
}

MUTABLE_FILES = {"/", "/index.html", "/packs.json"}


class WebDistHandler(http.server.SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):  # noqa: A002 - stdlib signature
        sys.stderr.write("web-serve: %s\n" % (format % args))

    def end_headers(self):
        # Headers are written in send_head for the compressed path.
        super().end_headers()

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/__report":
            self.send_error(404, "File not found")
            return
        length = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        print(f"web-serve-report: {body}", flush=True)
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def send_head(self):
        path = self.translate_path(self.path)
        file_path = Path(path)
        if file_path.is_dir():
            file_path = file_path / "index.html"
        suffix = file_path.suffix
        content_type = MIME_TYPES.get(suffix, "application/octet-stream")

        accepts_brotli = "br" in self.headers.get("Accept-Encoding", "")
        brotli_path = file_path.with_name(file_path.name + ".br")
        serve_path = file_path
        encoding = None
        if accepts_brotli and brotli_path.is_file():
            serve_path = brotli_path
            encoding = "br"

        if not serve_path.is_file():
            self.send_error(404, "File not found")
            return None

        try:
            handle = serve_path.open("rb")
        except OSError:
            self.send_error(404, "File not found")
            return None

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(serve_path.stat().st_size))
        if encoding:
            self.send_header("Content-Encoding", encoding)
            self.send_header("Vary", "Accept-Encoding")
        request_path = self.path.split("?", 1)[0]
        if request_path in MUTABLE_FILES:
            self.send_header("Cache-Control", "no-cache")
        else:
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        self.end_headers()
        return handle


class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="build/web/dist")
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not (root / "index.html").is_file():
        print(f"web-serve: no index.html under {root}; run ./build.sh web-build first", file=sys.stderr)
        return 1

    handler = type("Handler", (WebDistHandler,), {"directory": str(root)})

    def handler_factory(*handler_args, **handler_kwargs):
        return handler(*handler_args, directory=str(root), **handler_kwargs)

    with ThreadingServer((args.bind, args.port), handler_factory) as server:
        print(f"web-serve: http://{args.bind}:{args.port}/ (root {root})")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
