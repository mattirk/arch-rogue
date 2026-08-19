from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_default_zoom_by_graphics_tier_on_desktop(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            # Desktop on the HD tier starts roughly two zoom notches in from
            # the widest view (4.9.23), snapped exactly onto the smallest
            # world render bucket (4.9.24): the zero-residual default renders
            # the world straight into the display with no oversized layer or
            # full-frame composite scale. Modern and Legacy keep the widest
            # view; mobile keeps native scale. This is a desktop (non-mobile)
            # fixture, and HD is the default tier.
            self.assertFalse(game.mobile_mode)
            self.assertAlmostEqual(
                game.view_zoom, game.WORLD_RENDER_SCALE_BUCKETS[0]
            )
            game.graphics_tier = "modern"
            self.assertAlmostEqual(game.default_view_zoom(), game.VIEW_ZOOM_MIN)
            game.graphics_tier = "legacy"
            self.assertAlmostEqual(game.default_view_zoom(), game.VIEW_ZOOM_MIN)

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
            game.view_zoom = 1.0
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
            # The ceiling render bucket makes every residual composite an
            # identity/downscale, so the display is always the smaller target
            # and owns the lighting pass.
            for zv in (
                game.VIEW_ZOOM_MIN,
                0.8,
                1.0,
                1.3,
                game.VIEW_ZOOM_MAX,
            ):
                game.view_zoom = zv
                game.draw()
                self.assertTrue(game._shade_post_composite, zv)

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
            # Maximum zoom is an identity render at the native 1.6 bucket, so
            # lighting remains display-sized and no smaller layer is involved.
            game.view_zoom = game.VIEW_ZOOM_MAX
            game.draw()
            buf = game._light_buffer_surface
            self.assertIsNotNone(buf)
            self.assertEqual(buf.get_size(),
                             (rw // LIGHT_BUFFER_SCALE,
                              rh // LIGHT_BUFFER_SCALE))

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

    def test_world_layer_composite_uses_pixel_art_scaling(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            layer = pygame.Surface((7, 5))
            for y in range(layer.get_height()):
                for x in range(layer.get_width()):
                    layer.set_at((x, y), (x * 31, y * 47, (x + y) * 19))
            expected = pygame.transform.scale(layer, (23, 17))
            actual = pygame.Surface(expected.get_size())
            with patch.object(
                pygame.transform,
                "smoothscale",
                wraps=pygame.transform.smoothscale,
            ) as smoothscale:
                game._composite_world_layer(layer, actual)
            smoothscale.assert_not_called()
            self.assertEqual(
                pygame.image.tobytes(actual, "RGB"),
                pygame.image.tobytes(expected, "RGB"),
            )

    def test_story_intro_skips_opaque_world_and_hud_underdraw(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.story_intro_pending = True
            with (
                patch.object(game, "story_intro_lines", return_value=["Omen"]),
                patch.object(game, "_render_world_view") as render_world,
                patch.object(game, "draw_ui") as draw_ui,
                patch.object(game, "draw_story_intro_overlay") as draw_intro,
            ):
                game.draw()
            render_world.assert_not_called()
            draw_ui.assert_not_called()
            draw_intro.assert_called_once_with()

    def test_story_intro_opaque_backdrop_uses_direct_target_fill(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            game = Game(
                screen_size=(960, 540),
                headless=True,
                save_path=Path(tmpdir) / "run.json",
            )
            game.rng.seed(1771)
            game.restart(ARCHETYPES[0])
            self.assertTrue(game.story_intro_pending)
            game.screen.fill((255, 0, 255))
            with patch.object(
                pygame, "Surface", wraps=pygame.Surface
            ) as make_surface:
                game.draw_story_intro_overlay()
            full_screen_alpha_allocations = [
                call
                for call in make_surface.call_args_list
                if call.args
                and tuple(call.args[0]) == game.screen.get_size()
                and len(call.args) > 1
                and call.args[1] == pygame.SRCALPHA
            ]
            self.assertEqual(full_screen_alpha_allocations, [])
            self.assertEqual(game.screen.get_at((0, 0))[:3], (0, 0, 0))

    def test_paused_inventory_reuses_world_and_hud_until_state_changes(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.inventory_open = True
            with (
                patch.object(
                    game, "_render_world_view", wraps=game._render_world_view
                ) as render_world,
                patch.object(game, "draw_ui", wraps=game.draw_ui) as draw_ui,
                patch.object(
                    game, "draw_inventory", wraps=game.draw_inventory
                ) as draw_inventory,
            ):
                game.draw()
                game.draw()
                self.assertEqual(render_world.call_count, 1)
                self.assertEqual(draw_ui.call_count, 1)
                self.assertEqual(draw_inventory.call_count, 2)

                # Inventory/equipment actions can change underlying HUD stats.
                # The signature must reject the old retained scene in that case.
                game.player.hp -= 1
                game.draw()
                self.assertEqual(render_world.call_count, 2)
                self.assertEqual(draw_ui.call_count, 2)

    def test_desktop_help_keeps_live_world_rendering(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.show_help = True
            with patch.object(game, "_render_world_view") as render_world:
                game.draw()
                game.draw()
            self.assertEqual(render_world.call_count, 2)


if __name__ == "__main__":
    unittest.main()
