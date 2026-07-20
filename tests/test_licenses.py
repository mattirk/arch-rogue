# SPDX-License-Identifier: Apache-2.0
"""Tests for the 4.3.17 WS-G in-app Open Source Licenses surface."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame  # noqa: E402

from arch_rogue import licenses  # noqa: E402
from arch_rogue.content import ARCHETYPES  # noqa: E402
from arch_rogue.game import Game  # noqa: E402


def make_game(tmpdir: str) -> Game:
    game = Game(
        screen_size=(960, 540),
        headless=True,
        save_path=Path(tmpdir) / "run.json",
    )
    game.options_path = Path(tmpdir) / "options.json"
    game.rng.seed(2323)
    game.restart(ARCHETYPES[0])
    return game


class LicenseLoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        licenses.clear_cache()

    def test_license_text_is_apache_2(self) -> None:
        text = licenses.license_text()
        self.assertTrue(text)
        self.assertIn("Apache License", text)
        self.assertIn("Version 2.0", text)

    def test_pygame_lgpl_text_is_bundled(self) -> None:
        text = licenses.pygame_lgpl_text()
        self.assertIn("GNU LESSER GENERAL PUBLIC LICENSE", text)
        self.assertIn("Version 2.1", text)

    def test_notice_lists_every_bundled_third_party_library(self) -> None:
        notice = licenses.notice_text()
        self.assertTrue(notice)
        # Every library enumerated in the WS-G spec must appear.
        for needle in (
            "pygame-ce",
            "SDL2",
            "SDL2_image",
            "SDL2_mixer",
            "SDL2_ttf",
            "libpng",
            "libjpeg",
            "zlib",
            "Freetype",
            "Python",
            "PyJNIus",
            "OpenSSL",
            "libffi",
            "SQLite",
            "setuptools",
            "six",
            "libwebp",
            "HarfBuzz",
            "dr_libs",
        ):
            self.assertIn(needle, notice, f"NOTICE missing {needle!r}")
        # Critical copyleft disclosure must be accurate and accompanied by
        # the full license text in the bundle.
        self.assertIn("LGPL-2.1-or-later", notice)
        self.assertIn("Freetype License", notice)
        self.assertIn("FTL", notice)

    def test_notice_documents_build_tool_exclusion_and_gpl_guard(self) -> None:
        notice = licenses.notice_text()
        self.assertIn("buildozer", notice)
        self.assertIn("python-for-android", notice)
        self.assertIn("libmad", notice)

    def test_notice_surfaces_ai_provenance(self) -> None:
        notice = licenses.notice_text()
        self.assertIn("AI Provenance", notice)

    def test_ai_provenance_text_is_standalone_summary(self) -> None:
        text = licenses.ai_provenance_text()
        self.assertIn("AI Provenance", text)
        self.assertIn("AS IS", text)

    def test_license_bundle_available(self) -> None:
        self.assertTrue(licenses.license_bundle_available())


class AboutScreenLicensesTests(unittest.TestCase):
    def test_about_screen_surfaces_licenses_and_publishes_scroll(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.state = "about"
            game.licenses_scroll = 0
            # The renderer publishes _licenses_scroll_max / _visible_lines.
            game.ui_elapsed += 1.0 / 60.0
            game.draw()
            self.assertGreater(
                int(getattr(game, "_licenses_scroll_max", 0)),
                0,
                "About screen did not surface enough license text to overflow",
            )
            self.assertGreater(
                int(getattr(game, "_licenses_visible_lines", 0)), 0
            )

    def test_scroll_licenses_clamps_to_range(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.state = "about"
            game.draw()
            maximum = int(getattr(game, "_licenses_scroll_max", 0))
            self.assertGreater(maximum, 0)
            game.scroll_licenses(1000)
            self.assertEqual(game.licenses_scroll, maximum)
            game.scroll_licenses(-1000)
            self.assertEqual(game.licenses_scroll, 0)

    def test_about_scroll_input_advances_and_enter_returns_to_title(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.state = "about"
            game.draw()
            start = game.licenses_scroll
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
            game.handle_events()
            self.assertGreater(game.licenses_scroll, start)
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
            game.handle_events()
            self.assertEqual(game.state, "title")


if __name__ == "__main__":
    unittest.main()