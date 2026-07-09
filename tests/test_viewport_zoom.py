from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame

from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game


class ViewportZoomTests(unittest.TestCase):
    def make_game(self, tmpdir: str, seed: int = 1) -> Game:
        game = Game(
            screen_size=(960, 540),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.rng.seed(seed)
        game.restart(ARCHETYPES[0])
        if game.story_intro_pending:
            self.assertTrue(game.choose_story_relic_path(0))
        game.active_cutscene = None
        game.snap_camera_to_player()
        return game

    def test_default_zoom_is_max_zoom_in(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.assertAlmostEqual(game.view_zoom, game.VIEW_ZOOM_MAX)

    def test_adjust_view_zoom_clamps_and_steps(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.view_zoom = 1.0
            game.adjust_view_zoom(1.0)
            self.assertGreater(game.view_zoom, 1.0)
            game.adjust_view_zoom(-1.0)
            self.assertAlmostEqual(game.view_zoom, 1.0, places=6)
            # Clamp to max.
            game.view_zoom = game.VIEW_ZOOM_MAX
            game.adjust_view_zoom(5.0)
            self.assertAlmostEqual(game.view_zoom, game.VIEW_ZOOM_MAX)
            # Clamp to min.
            game.view_zoom = game.VIEW_ZOOM_MIN
            game.adjust_view_zoom(-5.0)
            self.assertAlmostEqual(game.view_zoom, game.VIEW_ZOOM_MIN)

    def test_ctrl_scroll_wheel_changes_zoom(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            pygame.key.set_mods(pygame.KMOD_CTRL)
            try:
                pygame.event.post(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=1))
                game.handle_events()
                self.assertGreater(game.view_zoom, 1.0)
                zoom_in = game.view_zoom
                pygame.event.post(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=-1))
                game.handle_events()
                self.assertLess(game.view_zoom, zoom_in)
            finally:
                pygame.key.set_mods(0)

    def test_scroll_without_ctrl_does_not_zoom(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            before = game.view_zoom
            pygame.key.set_mods(0)
            pygame.event.post(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=1))
            game.handle_events()
            self.assertEqual(game.view_zoom, before)

    def test_screen_to_world_inverts_zoomed_projection(self) -> None:
        import math
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            rw, rh = game.screen.get_size()
            cam_x, cam_y = game.camera_iso()
            for zoom in (0.7, 1.0, 1.4):
                game.view_zoom = zoom
                # Forward: world -> iso -> layer (size screen/zoom) -> real pixel.
                for wx, wy in ((game.player.x, game.player.y), (game.player.x + 3, game.player.y - 2)):
                    iso_x = (wx - wy) * 64 * 5 / 2
                    iso_y = (wx + wy) * 32 * 5 / 2
                    layer_w = rw / zoom
                    layer_h = rh / zoom
                    real_x = (iso_x - cam_x + layer_w * 0.5) * zoom
                    real_y = (iso_y - cam_y + layer_h * 0.48) * zoom
                    bx, by = game.screen_to_world(int(real_x), int(real_y))
                    self.assertAlmostEqual(bx, wx, delta=0.25)
                    self.assertAlmostEqual(by, wy, delta=0.25)

    def test_draw_runs_at_nonnative_zoom(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.view_zoom = 1.3
            game.draw()  # should not raise; composites world layer.
            game.view_zoom = 0.75
            game.draw()


if __name__ == "__main__":
    unittest.main()