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

    def test_default_zoom_is_native_scale(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.assertAlmostEqual(game.view_zoom, 1.0)

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



    def test_world_to_display_matches_screen_at_unit_zoom(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.view_zoom = 1.0
            for wx, wy in ((game.player.x, game.player.y),
                           (game.player.x + 2, game.player.y - 1)):
                self.assertEqual(game.world_to_display(wx, wy),
                                 game.world_to_screen(wx, wy))

    def test_world_to_display_scales_with_zoom(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            cam_x, cam_y = game.camera_iso()
            iso_x = (game.player.x - game.player.y) * 64 * 5 / 2
            iso_y = (game.player.x + game.player.y) * 32 * 5 / 2
            rw, rh = game.screen.get_size()
            for zoom in (0.65, 0.8, 1.0, 1.3, 1.6):
                game.view_zoom = zoom
                dx, dy = game.world_to_display(game.player.x, game.player.y)
                expected_x = int((iso_x - cam_x) * zoom + rw * 0.5)
                expected_y = int((iso_y - cam_y) * zoom + rh * 0.48)
                self.assertAlmostEqual(dx, expected_x, delta=1)
                self.assertAlmostEqual(dy, expected_y, delta=1)

    def test_shade_post_composite_flag_direction(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game._lighting_enabled = True
            # Zoomed out / native: shade the display after the composite.
            for zv in (game.VIEW_ZOOM_MIN, 0.8, 1.0):
                game.view_zoom = zv
                game.draw()
                self.assertTrue(game._shade_post_composite, zv)
            # Zoomed in: shade the (smaller) world layer before the composite.
            for zv in (1.3, game.VIEW_ZOOM_MAX):
                game.view_zoom = zv
                game.draw()
                self.assertFalse(game._shade_post_composite, zv)

    def test_lighting_buffer_targets_smaller_surface(self) -> None:
        import tempfile

        from arch_rogue.constants import LIGHT_BUFFER_SCALE

        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game._lighting_enabled = True
            rw, rh = game.screen.get_size()
            # Zoomed out: lighting runs post-composite on the display, so the
            # half-res light buffer matches the display, not the larger layer.
            game.view_zoom = game.VIEW_ZOOM_MIN
            game.draw()
            buf = game._light_buffer_surface
            self.assertIsNotNone(buf)
            self.assertEqual(buf.get_size(),
                             (rw // LIGHT_BUFFER_SCALE, rh // LIGHT_BUFFER_SCALE))
            # Zoomed in: lighting runs pre-composite on the (smaller) layer, so
            # the buffer matches the layer, not the larger display.
            game.view_zoom = game.VIEW_ZOOM_MAX
            game.draw()
            buf = game._light_buffer_surface
            self.assertIsNotNone(buf)
            layer_w = int(round(rw / game.VIEW_ZOOM_MAX))
            layer_h = int(round(rh / game.VIEW_ZOOM_MAX))
            self.assertEqual(buf.get_size(),
                             (layer_w // LIGHT_BUFFER_SCALE,
                              layer_h // LIGHT_BUFFER_SCALE))

    def test_lighting_applied_at_max_zoom_out(self) -> None:
        # Sanity: at max zoom-out the lighting multiply still shades world
        # pixels (the post-composite pass runs and darkens the display).
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game._lighting_enabled = True
            game.view_zoom = game.VIEW_ZOOM_MIN
            game.draw()
            # Compare the light buffer itself rather than one world pixel: asset
            # sprites can place a deliberately dark contact shadow exactly at the
            # player's projected origin even though the lantern is bright there.
            from arch_rogue.constants import LIGHT_BUFFER_SCALE

            sx, sy = game.world_to_display(game.player.x, game.player.y)
            buffer = game._light_buffer_surface
            bx = max(0, min(buffer.get_width() - 1, sx // LIGHT_BUFFER_SCALE))
            by = max(0, min(buffer.get_height() - 1, sy // LIGHT_BUFFER_SCALE))
            near = max(
                sum(buffer.get_at((x, y))[:3])
                for x in range(max(0, bx - 2), min(buffer.get_width(), bx + 3))
                for y in range(max(0, by - 2), min(buffer.get_height(), by + 3))
            )
            corner = sum(buffer.get_at((2, 2))[:3])
            self.assertGreater(near, corner)


if __name__ == "__main__":
    unittest.main()