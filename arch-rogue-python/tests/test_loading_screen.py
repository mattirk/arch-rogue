"""The loading screen shown over floor generation and the sprite prewarm."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame

from arch_rogue.game import Game
from arch_rogue.loading import LOGO_DIAMOND_RECT


def make_game(tmpdir: str) -> Game:
    game = Game(
        screen_size=(1100, 620),
        headless=True,
        save_path=Path(tmpdir) / "run.json",
    )
    game.options_path = Path(tmpdir) / "options.json"
    return game


class LoadingScreenTests(unittest.TestCase):
    def test_context_manager_sets_and_clears_the_active_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            self.assertFalse(game.loading_screen_active())
            with game.loading_screen("Descending..."):
                self.assertTrue(game.loading_screen_active())
                game.loading_tick(0.5)
            self.assertFalse(game.loading_screen_active())

    def test_nested_loading_screens_keep_the_outer_label(self) -> None:
        # A descent saves mid-transition; the inner block must not tear down
        # the outer screen when it exits.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            with game.loading_screen("Outer"):
                with game.loading_screen("Inner"):
                    self.assertEqual(game._loading_screen_label, "Outer")
                self.assertTrue(game.loading_screen_active())
            self.assertFalse(game.loading_screen_active())

    def test_tick_outside_a_loading_screen_is_a_no_op(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.loading_tick(0.5)  # must not raise or draw

    def test_diamond_frames_load_from_the_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            frames = game._loading_diamond_frames()
            self.assertEqual(len(frames), 16)
            # Every frame covers the logo's diamond footprint (72x74 canvas
            # centered on the 70x74 source rect).
            for frame in frames:
                self.assertEqual(frame.get_size(), (72, 74))
            # Frame 0 is the logo's own diamond: identical pixels inside the
            # rect once blitted back (spot-check the gem pixel).
            logo = game.ui_assets.source("menu.logo.title")
            self.assertIsNotNone(logo)
            center = LOGO_DIAMOND_RECT.center
            gem_logo = logo.get_at(center)
            gem_frame = frames[0].get_at(
                (center[0] - 265, center[1] - LOGO_DIAMOND_RECT.y)
            )
            self.assertEqual(tuple(gem_logo), tuple(gem_frame))

    def test_restart_runs_under_the_loading_screen_and_reports_progress(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.eager_tile_prewarm = True  # headless default is off
            seen: list[float | None] = []
            original_tick = game.loading_tick

            def spy(progress: float | None = None) -> None:
                seen.append(progress)
                original_tick(progress)

            game.loading_tick = spy  # type: ignore[method-assign]
            game.restart()
            self.assertFalse(game.loading_screen_active())
            self.assertEqual(game.state, "playing")
            # The prewarm reported monotonically increasing progress ending at 1.
            fractions = [p for p in seen if p is not None]
            self.assertTrue(fractions)
            self.assertEqual(fractions, sorted(fractions))
            self.assertAlmostEqual(fractions[-1], 1.0)


if __name__ == "__main__":
    unittest.main()


class TitleLogoSpinTests(unittest.TestCase):
    """5.0: the title menu spins the logo's relic diamond on desktop."""

    def test_compose_frame_zero_is_pixel_identical_to_the_static_logo(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            source = game.ui_assets.source("menu.logo.title")
            composed = game.compose_spinning_logo(0)
            self.assertIsNotNone(source)
            self.assertIsNotNone(composed)
            self.assertEqual(
                pygame.image.tobytes(composed, "RGBA"),
                pygame.image.tobytes(source, "RGBA"),
            )

    def test_title_menu_repaints_the_spin_on_desktop_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.state = "title"
            game.ui_elapsed = 0.0
            game.draw()
            first = pygame.image.tobytes(game.screen, "RGBA")
            first_index = game.spinning_logo_frame_index()

            # One spin frame later (8 fps) the retained-frame signature must
            # tick and the composed logo must change on screen.
            game.ui_elapsed += 1.0 / 8.0 + 0.01
            self.assertNotEqual(
                game.spinning_logo_frame_index(), first_index
            )
            game.draw()
            second = pygame.image.tobytes(game.screen, "RGBA")
            self.assertNotEqual(first, second)

            # Mobile keeps the draw-once static menu: the signature pins the
            # spin term to -1 so ui_elapsed cannot dirty the retained frame.
            game.mobile_mode = True
            signature_a = game._static_menu_signature()
            game.ui_elapsed += 1.0 / 8.0 + 0.01
            signature_b = game._static_menu_signature()
            game.mobile_mode = False
            self.assertEqual(signature_a, signature_b)
