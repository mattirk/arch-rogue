from __future__ import annotations

import asyncio
import os
import socket
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))  # so `web` (namespace package) imports
sys.path.insert(0, str(REPO / "src"))  # so `arch_rogue` imports

import web.build as web_build  # noqa: E402
import web.main as web_main  # noqa: E402
import web.server as web_server  # noqa: E402
import web.vendor_runtime as vendor_runtime  # noqa: E402


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class WebServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "index.html").write_text("<h1>arch-rogue web</h1>", encoding="utf-8")
        (root / "app.wasm").write_bytes(b"\0asm\1\0\0\0")
        (root / "app.js").write_text("console.log('hi')", encoding="utf-8")
        self.port = _free_port()
        self.server = web_server.serve(
            root, host="127.0.0.1", port=self.port, coep="credentialless"
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.tmp.cleanup()

    def _get(self, path: str) -> tuple[int, dict[str, str], bytes]:
        url = f"http://127.0.0.1:{self.port}{path}"
        req = urllib.request.Request(url, headers={"Accept": "*/*"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return (
                resp.status,
                {k.lower(): v for k, v in resp.headers.items()},
                resp.read(),
            )

    def test_serves_index_html(self) -> None:
        status, _headers, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"arch-rogue web", body)

    def test_wasm_served_as_application_wasm(self) -> None:
        status, headers, _body = self._get("/app.wasm")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("content-type"), "application/wasm")

    def test_js_mime_is_javascript(self) -> None:
        _status, headers, _body = self._get("/app.js")
        self.assertEqual(headers.get("content-type"), "application/javascript")

    def test_cross_origin_isolation_headers_present(self) -> None:
        _status, headers, _body = self._get("/")
        self.assertEqual(headers.get("cross-origin-opener-policy"), "same-origin")
        self.assertEqual(headers.get("cross-origin-embedder-policy"), "credentialless")
        self.assertEqual(headers.get("cross-origin-resource-policy"), "same-origin")

    def test_require_corp_emits_require_corp(self) -> None:
        port = _free_port()
        root = Path(self.tmp.name)
        server = web_server.serve(
            root, host="127.0.0.1", port=port, coep="require-corp"
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{port}/"
            with urllib.request.urlopen(url, timeout=5) as resp:
                headers = {k.lower(): v for k, v in resp.headers.items()}
            self.assertEqual(
                headers.get("cross-origin-embedder-policy"), "require-corp"
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_no_isolation_omits_coep(self) -> None:
        # Spin a second server with COEP off (empty string) on a different port.
        port = _free_port()
        root = Path(self.tmp.name)
        server = web_server.serve(root, host="127.0.0.1", port=port, coep="")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{port}/"
            with urllib.request.urlopen(url, timeout=5) as resp:
                headers = {k.lower(): v for k, v in resp.headers.items()}
            self.assertEqual(headers.get("cross-origin-opener-policy"), "same-origin")
            self.assertIsNone(headers.get("cross-origin-embedder-policy"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_invalid_coep_raises(self) -> None:
        with self.assertRaises(ValueError):
            web_server.serve(
                Path(self.tmp.name), host="127.0.0.1", port=_free_port(), coep="bogus"
            )


class WebDriverTests(unittest.TestCase):
    def test_writable_home_is_writable(self) -> None:
        home = web_main._writable_home()
        self.assertTrue(home.exists())
        probe = home / ".arch_rogue_web_probe"
        probe.write_text("ok", encoding="utf-8")
        self.assertEqual(probe.read_text(encoding="utf-8"), "ok")
        probe.unlink()

    def test_make_game_headless_constructs_and_disables_fullscreen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # Redirect save/options into the temp dir so the test never touches
            # a real home directory.
            prev_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            try:
                game = web_main.make_game(headless=True)
            finally:
                if prev_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = prev_home
            try:
                self.assertFalse(game.fullscreen)
                self.assertEqual(game.screen.get_size(), (2560, 1440))
            finally:
                import pygame

                pygame.quit()

    def test_run_frame_advances_one_tick(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prev_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            try:
                game = web_main.make_game(headless=True)
            finally:
                if prev_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = prev_home
            try:
                self.assertEqual(game.state, "title")
                asyncio.run(web_main.run_frame(game))
                # A frame should not have crashed or changed out of title state
                # without input.
                self.assertEqual(game.state, "title")
            finally:
                import pygame

                pygame.quit()


class VendorRuntimeTests(unittest.TestCase):
    def test_local_path_mirrors_cdn_layout(self) -> None:
        self.assertEqual(
            vendor_runtime._local_path("/cdn/0.9.3/pythons.js", Path("/tmp/v")),
            Path("/tmp/v/cdn/0.9.3/pythons.js"),
        )
        self.assertEqual(
            vendor_runtime._local_path("/cdn/vt/xterm.js", Path("/tmp/v")),
            Path("/tmp/v/cdn/vt/xterm.js"),
        )

    def test_stub_files_are_created_empty_without_network(self) -> None:
        # Stubs must not touch the network; use an unreachable base to prove it.
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            vendor_runtime.vendor_runtime(
                dest,
                base="http://127.0.0.1:1/invalid",
                files=[
                    ("/cdn/0.9.3/browserfs.min.js", True),
                    ("/cdn/0.9.3/pygbag0.9.3.js", True),
                ],
            )
            self.assertEqual((dest / "cdn/0.9.3/browserfs.min.js").read_bytes(), b"")
            self.assertEqual((dest / "cdn/0.9.3/pygbag0.9.3.js").read_bytes(), b"")

    def test_force_redownloads_stub(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            vendor_runtime.vendor_runtime(
                dest, base="http://127.0.0.1:1/invalid", files=[("/cdn/x.js", True)]
            )
            self.assertTrue((dest / "cdn/x.js").exists())
            # re-run without force: still exists, still empty
            vendor_runtime.vendor_runtime(
                dest, base="http://127.0.0.1:1/invalid", files=[("/cdn/x.js", True)]
            )
            self.assertEqual((dest / "cdn/x.js").read_bytes(), b"")

    def test_vendored_runtime_manifest_is_complete(self) -> None:
        # If the runtime was vendored (build.py runs vendor_runtime), assert
        # every non-stub manifest file is present and non-empty. This guards
        # the "no 404s / fully self-contained" property without needing network
        # at test time (it only asserts when the vendor dir already exists).
        vendor_root = REPO / "web" / "vendor"
        if not (vendor_root / "cdn" / "0.9.3" / "cpython312" / "main.wasm").exists():
            self.skipTest("vendored runtime not present (run web/build.py once)")
        for cdn_path, is_stub in vendor_runtime.RUNTIME_FILES:
            local = vendor_root / cdn_path.lstrip("/")
            self.assertTrue(local.exists(), f"missing vendored file {cdn_path}")
            if not is_stub:
                self.assertGreater(local.stat().st_size, 0, f"empty {cdn_path}")


class BuildStagingTests(unittest.TestCase):
    def test_rewrite_index_html_replaces_remote_cdn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            (dist / "index.html").write_text(
                'src="https://pygame-web.github.io/cdn/0.9.3/pythons.js"\n'
                'src="https://pygame-web.github.io/cdn/0.9.3//browserfs.min.js"',
                encoding="utf-8",
            )
            count = web_build.rewrite_index_html_local(dist)
            self.assertEqual(count, 2)
            out = (dist / "index.html").read_text(encoding="utf-8")
            self.assertNotIn("pygame-web.github.io", out)
            self.assertIn("/cdn/0.9.3/pythons.js", out)
            self.assertIn("/cdn/0.9.3//browserfs.min.js", out)

    def test_rewrite_returns_zero_when_no_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(web_build.rewrite_index_html_local(Path(tmp)), 0)

    def test_merge_vendor_runtime_copies_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            vendor = Path(tmp) / "vendor" / "cdn"
            (vendor / "0.9.3" / "cpython312").mkdir(parents=True)
            (vendor / "0.9.3" / "cpython312" / "main.wasm").write_bytes(b"WASM")
            (vendor / "vt").mkdir(parents=True)
            (vendor / "vt" / "xterm.js").write_text("x", encoding="utf-8")
            self.assertTrue(web_build.merge_vendor_runtime(dist, vendor))
            self.assertEqual(
                (dist / "cdn" / "0.9.3" / "cpython312" / "main.wasm").read_bytes(),
                b"WASM",
            )
            self.assertTrue((dist / "cdn" / "vt" / "xterm.js").exists())

    def test_merge_vendor_returns_false_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(
                web_build.merge_vendor_runtime(Path(tmp), Path(tmp) / "nope")
            )

    def test_pygbag_ini_excludes_bloat(self) -> None:
        # The repo pygbag.ini must ignore the dirs that would bloat the tarball.
        ini = (REPO / "pygbag.ini").read_text(encoding="utf-8")
        for needle in ("/.venv", "/web", "/tests"):
            self.assertIn(needle, ini)

            # placeholder marker
            self.assertIn(needle, ini)


class WebDriverPathBootstrapTests(unittest.TestCase):
    def test_resolve_src_paths_finds_src_next_to_main(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "assets" / "src" / "arch_rogue").mkdir(parents=True)
            main = tmp / "assets" / "main.py"
            main.write_text("", encoding="utf-8")
            paths = web_main.resolve_src_paths(main, tmp / "assets", [Path("/nope")])
            self.assertEqual(paths, [(tmp / "assets" / "src").resolve()])

    def test_resolve_src_paths_falls_back_to_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "src").mkdir(parents=True)
            paths = web_main.resolve_src_paths(None, tmp, [])
            self.assertEqual(paths, [(tmp / "src").resolve()])

    def test_resolve_src_paths_dedupes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "assets" / "src").mkdir(parents=True)
            main = tmp / "assets" / "main.py"
            main.write_text("", encoding="utf-8")
            paths = web_main.resolve_src_paths(
                main, tmp / "assets", [Path("/nonexistent")]
            )
            self.assertEqual(len(paths), 1)

    def test_built_main_py_has_bootstrap_and_package(self) -> None:
        import tarfile

        tarball = REPO / "web" / "dist" / "arch-rogue.tar.gz"
        if not tarball.is_file():
            self.skipTest("web/dist not built (run python web/build.py)")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            with tarfile.open(tarball, "r:gz") as tf:
                tf.extractall(tmp)
            main = tmp / "assets" / "main.py"
            self.assertTrue(main.is_file())
            text = main.read_text(encoding="utf-8")
            self.assertIn("_bootstrap_arch_rogue_path", text)
            self.assertIn("resolve_src_paths", text)
            self.assertTrue(
                (tmp / "assets" / "src" / "arch_rogue" / "__init__.py").is_file()
            )


class BrowserResizeTests(unittest.TestCase):
    def _make_headless(self, tmp: str, size: tuple[int, int] = (2560, 1440)) -> object:
        prev = os.environ.get("HOME")
        os.environ["HOME"] = tmp
        try:
            return web_main.make_game(headless=True, screen_size=size)
        finally:
            if prev is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = prev

    def test_browser_window_size_none_off_browser(self) -> None:
        self.assertIsNone(web_main.browser_window_size())

    def test_maybe_resize_noop_without_browser(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            game = self._make_headless(tmp)
            try:
                before = game.screen.get_size()
                self.assertFalse(web_main.maybe_resize_to_browser(game))
                self.assertEqual(game.screen.get_size(), before)
            finally:
                import pygame

                pygame.quit()

    def test_maybe_resize_resizes_to_provider_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            game = self._make_headless(tmp, (2560, 1440))
            try:
                changed = web_main.maybe_resize_to_browser(
                    game, size_provider=lambda: (640, 480), notify=False
                )
                self.assertTrue(changed)
                self.assertEqual(game.screen.get_size(), (640, 480))
                self.assertEqual(game.windowed_size, (640, 480))
            finally:
                import pygame

                pygame.quit()

    def test_maybe_resize_skips_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            game = self._make_headless(tmp, (800, 600))
            try:
                self.assertFalse(
                    web_main.maybe_resize_to_browser(
                        game, size_provider=lambda: (800, 600), notify=False
                    )
                )
                self.assertEqual(game.screen.get_size(), (800, 600))
            finally:
                import pygame

                pygame.quit()

    def test_maybe_resize_rejects_too_small(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            game = self._make_headless(tmp, (2560, 1440))
            try:
                self.assertFalse(
                    web_main.maybe_resize_to_browser(
                        game, size_provider=lambda: (100, 100), notify=False
                    )
                )
                self.assertEqual(game.screen.get_size(), (2560, 1440))
            finally:
                import pygame

                pygame.quit()

    def test_make_game_uses_explicit_screen_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            game = self._make_headless(tmp, (1024, 768))
            try:
                self.assertEqual(game.screen.get_size(), (1024, 768))
            finally:
                import pygame

                pygame.quit()


if __name__ == "__main__":
    unittest.main()
