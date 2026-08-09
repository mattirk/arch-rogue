from __future__ import annotations

import math
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame

from arch_rogue.constants import (
    GRAPHICS_TIER_HD,
    GRAPHICS_TIER_LEGACY,
    GRAPHICS_TIER_MODERN,
    HD_FOG_REVEAL_FALLOFF_SPAN,
    HD_FOG_REVEAL_FALLOFF_START,
)
from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game
from arch_rogue.models import Tile
from arch_rogue.rendering.fog import _U_OFFSET


def field_value(distance: float) -> float:
    return max(
        0.0,
        min(
            1.0,
            (distance - HD_FOG_REVEAL_FALLOFF_START) / HD_FOG_REVEAL_FALLOFF_SPAN,
        ),
    )


class SmoothFogTests(unittest.TestCase):
    """4.10.1 — HD smooth fog-of-war edge (rendering/fog.py)."""

    def make_game(
        self,
        tmpdir: str,
        seed: int = 4102,
        size: tuple[int, int] = (960, 540),
    ) -> Game:
        game = Game(
            screen_size=size,
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.rng.seed(seed)
        game.restart(ARCHETYPES[0])
        if game.story_intro_pending:
            self.assertTrue(game.choose_story_relic_path(0))
        game.active_cutscene = None
        game.set_current_floor_dark(False)
        game.graphics_tier = GRAPHICS_TIER_HD
        return game

    def settle(self, game: Game) -> None:
        """Sync the field and drain the reveal easing to its targets."""

        game._fog_field_sync()
        game.ui_elapsed = float(getattr(game, "ui_elapsed", 0.0)) + 5.0
        game._fog_advance_easing()

    def stamp_buffer(self, game: Game, scale: int = 2) -> pygame.Surface:
        width, height = game.screen.get_size()
        buffer = pygame.Surface(
            (width // scale, height // scale), pygame.SRCALPHA
        )
        game._frame_cache = {}
        game._stamp_ambient(buffer, scale)
        return buffer

    def test_field_values_follow_distance_to_unrevealed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.revealed_tiles = {
                (x, y) for x in range(10, 21) for y in range(10, 21)
            }
            self.settle(game)
            field = game._fog_field
            self.assertEqual(set(field), game.revealed_tiles)
            # Interior: nothing unrevealed within the falloff reach.
            self.assertEqual(field[(15, 15)], 1.0)
            # Edge center: nearest unrevealed is orthogonal at distance 1.
            self.assertAlmostEqual(field[(10, 15)], field_value(1.0))
            # One tile in: nearest unrevealed at distance 2.
            self.assertAlmostEqual(field[(11, 15)], field_value(2.0))
            # Rectangle corner: its orthogonal neighbors are unrevealed too,
            # so the corner still measures distance 1.
            self.assertAlmostEqual(field[(10, 10)], field_value(1.0))
            # Two tiles in: ramp already complete.
            self.assertEqual(field[(12, 15)], 1.0)
            # Diagonal-only exposure: carve one unrevealed notch at (9, 9)
            # out of an extended rectangle; (10, 10) then measures sqrt(2).
            game.revealed_tiles = {
                (x, y) for x in range(9, 21) for y in range(9, 21)
            } - {(9, 9)}
            self.settle(game)
            self.assertAlmostEqual(
                game._fog_field[(10, 10)], field_value(math.sqrt(2))
            )

    def test_incremental_updates_match_full_recompute(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            rng = game.rng
            revealed = {(30, 30)}
            game.revealed_tiles = revealed
            self.settle(game)
            for _step in range(40):
                x = 25 + rng.randrange(12)
                y = 25 + rng.randrange(12)
                revealed.add((x, y))
                if rng.random() < 0.3:
                    continue  # batch several tiles into one sync
                self.settle(game)
            self.settle(game)
            expected = {
                tile: game._fog_tile_target(tile, revealed)
                for tile in revealed
            }
            self.assertEqual(game._fog_field, expected)
            # The lattice mirrors the settled field: tile sites carry the tile
            # value, corner sites the average of their four tiles.
            lattice = game._fog_lattice
            for (x, y), value in expected.items():
                site = lattice.get_at((x - y + _U_OFFSET, x + y))
                self.assertEqual(site[0], int(value * 255.0 + 0.5))
            probe_x, probe_y = 30, 30
            corner = lattice.get_at((probe_x - probe_y + _U_OFFSET + 1, probe_x + probe_y))
            total = sum(
                expected.get(tile, 0.0)
                for tile in (
                    (probe_x, probe_y),
                    (probe_x + 1, probe_y),
                    (probe_x + 1, probe_y - 1),
                    (probe_x, probe_y - 1),
                )
            )
            self.assertEqual(corner[0], int(total * 63.75 + 0.5))

    def test_new_set_object_rebuilds_and_old_tiles_drop(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.revealed_tiles = {(40, 40), (40, 41)}
            self.settle(game)
            self.assertIn((40, 40), game._fog_field)
            game.revealed_tiles = {(12, 12)}
            self.settle(game)
            self.assertEqual(set(game._fog_field), {(12, 12)})

    def test_stamp_alignment_matches_projection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            tx, ty = int(game.player.x), int(game.player.y)
            game.revealed_tiles = {(tx, ty)}
            game.snap_camera_to_player()
            self.settle(game)
            scale = 2
            buffer = self.stamp_buffer(game, scale)
            sx, sy = game.world_to_display(tx + 0.5, ty + 0.5)
            bx, by = sx // scale, sy // scale
            center_value = buffer.get_at((bx, by))[0]
            width, height = buffer.get_size()
            peak = max(
                buffer.get_at((x, y))[0]
                for x in range(0, width, 4)
                for y in range(0, height, 4)
            )
            self.assertGreater(center_value, 0)
            self.assertGreaterEqual(center_value, int(peak * 0.9))
            # Two tiles away along +x the lone tile's stamp has decayed to
            # nearly nothing; a misaligned mask would put the peak here.
            far_x, far_y = game.world_to_display(tx + 2.5, ty + 0.5)
            far_value = buffer.get_at((far_x // scale, far_y // scale))[0]
            self.assertLess(far_value, center_value * 0.35)

    def reveal_small_blob(self, game: Game) -> None:
        # A radius-~2.2 blob keeps the frontier well inside the 960x540 test
        # view (the real sight disc is wider than this buffer).
        px, py = int(game.player.x), int(game.player.y)
        game.revealed_tiles = {
            (px + dx, py + dy)
            for dx in range(-3, 4)
            for dy in range(-3, 4)
            if dx * dx + dy * dy <= 5
        }

    def test_frontier_gradient_is_pixel_smooth_on_hd(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            # A wide canvas: the blob spans +/- ~3.2 u-units (the u axis
            # stretches tile distance by sqrt(2)) and the fade band another
            # unit, all of which must fit inside the buffer row.
            game = self.make_game(tmpdir, size=(1600, 900))
            self.reveal_small_blob(game)
            game.snap_camera_to_player()
            self.settle(game)
            scale = 2
            buffer = self.stamp_buffer(game, scale)
            px, py = game.player.x, game.player.y
            sx, sy = game.world_to_display(px, py)
            row_y = min(max(sy // scale, 0), buffer.get_height() - 1)
            values = [
                buffer.get_at((x, row_y))[0]
                for x in range(0, buffer.get_width())
            ]
            interior = max(values)
            self.assertGreater(interior, 40)
            self.assertEqual(min(values), 0)
            steps = [
                abs(second - first)
                for first, second in zip(values, values[1:])
            ]
            # A hard tile edge would step by the full ambient level between
            # adjacent buffer pixels; the field must never exceed a small
            # fraction of it.
            self.assertLessEqual(max(steps), max(6, interior // 4))

    def test_modern_keeps_hard_rect_ambient(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, size=(1600, 900))
            game.graphics_tier = GRAPHICS_TIER_MODERN
            self.reveal_small_blob(game)
            game.snap_camera_to_player()
            self.assertFalse(game._smooth_fog_reveal_active())
            scale = 2
            buffer = self.stamp_buffer(game, scale)
            sx, sy = game.world_to_display(game.player.x, game.player.y)
            row_y = min(max(sy // scale, 0), buffer.get_height() - 1)
            values = [
                buffer.get_at((x, row_y))[0]
                for x in range(0, buffer.get_width())
            ]
            interior = max(values)
            self.assertGreater(interior, 40)
            steps = [
                abs(second - first)
                for first, second in zip(values, values[1:])
            ]
            # The rect path switches from full ambient to black between two
            # adjacent buffer pixels somewhere on this row.
            self.assertGreaterEqual(max(steps), interior)

    def test_smooth_fog_gating(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.assertTrue(game._smooth_fog_reveal_active())
            for tier in (GRAPHICS_TIER_MODERN, GRAPHICS_TIER_LEGACY):
                game.graphics_tier = tier
                self.assertFalse(game._smooth_fog_reveal_active())
            game.graphics_tier = GRAPHICS_TIER_HD
            game.mobile_mode = True
            self.assertFalse(game._smooth_fog_reveal_active())
            game.mobile_mode = False
            game._lighting_enabled = False
            self.assertFalse(game._smooth_fog_reveal_active())
            game._lighting_enabled = True
            game.set_current_floor_dark(True)
            self.assertFalse(game._smooth_fog_reveal_active())

    def test_wall_fog_edge_bypassed_when_smooth_fog_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            x, y = int(game.player.x), int(game.player.y)
            game.dungeon.tiles[x][y] = Tile.WALL
            game.dungeon.tiles[x - 1][y] = Tile.WALL
            game.dungeon.tiles[x][y - 1] = Tile.WALL
            game.revealed_tiles = {(x, y)}
            game._frame_dark = False
            game._frame_smooth_fog = False
            self.assertNotEqual(game._wall_fog_edge(x, y), 0)
            game._frame_smooth_fog = True
            self.assertEqual(game._wall_fog_edge(x, y), 0)

    def test_draw_margin_extends_cull_without_visible_leak(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, size=(1600, 900))
            px, py = int(game.player.x), int(game.player.y)
            self.reveal_small_blob(game)
            game.snap_camera_to_player()
            self.settle(game)

            # The frontier along +x sits at distance 2 (dx*dx <= 5); the
            # ground margin is exactly one ring beyond it.
            dark, tiles, *_rest = game._visibility_scan_params()
            self.assertFalse(dark)
            self.assertTrue(game.revealed_tiles.issubset(tiles))
            self.assertIn((px + 3, py), tiles)
            self.assertNotIn((px + 4, py), tiles)  # ring 2: pitch black
            self.assertNotIn((px + 9, py), tiles)

            # Margin tiles render under an essentially black mask: no
            # unexplored terrain becomes visible before the fog lifts.
            buffer = self.stamp_buffer(game)
            mx, my = game.world_to_display(px + 4.5, py + 0.5)
            margin_value = buffer.get_at((mx // 2, my // 2))[0]
            self.assertLessEqual(margin_value, 4)

            # Modern keeps the strict revealed cull.
            game.graphics_tier = GRAPHICS_TIER_MODERN
            _dark, strict, *_rest = game._visibility_scan_params()
            self.assertEqual(strict, game.revealed_tiles)
            self.assertNotIn((px + 4, py), strict)
            game.graphics_tier = GRAPHICS_TIER_HD

            # The margin follows the frontier as it advances.
            game.revealed_tiles.add((px + 3, py))
            self.settle(game)
            _dark, tiles, *_rest = game._visibility_scan_params()
            self.assertIn((px + 4, py), tiles)

    def test_south_frontier_prisms_draw_early(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            px, py = int(game.player.x), int(game.player.y)
            # A wall two diagonal steps south of revealed terrain holds its
            # prism over that terrain's screen area: it must draw early, or
            # its top pops in under a bright mask the frame it is revealed.
            game.dungeon.tiles[px][py] = Tile.FLOOR
            game.dungeon.tiles[px + 2][py + 2] = Tile.WALL
            game.dungeon.tiles[px + 1][py + 1] = Tile.FLOOR
            game.dungeon.tiles[px + 4][py + 4] = Tile.WALL
            game.revealed_tiles = {(px, py)}
            self.settle(game)
            # Rock-on-rock stays strictly gated: a wall revealed over rock
            # cannot produce a visible swap, so it seeds no early prisms.
            game2_revealed = {(px + 10, py + 10)}
            game.dungeon.tiles[px + 10][py + 10] = Tile.WALL
            game.dungeon.tiles[px + 12][py + 12] = Tile.WALL
            game.revealed_tiles = game.revealed_tiles | game2_revealed
            self.settle(game)
            self.assertNotIn((px + 12, py + 12), game._fog_prism_tiles)
            prisms = game._fog_prism_tiles
            self.assertIn((px + 2, py + 2), prisms)
            # Beyond the prism's screen reach: stays strictly gated.
            self.assertNotIn((px + 4, py + 4), prisms)
            # Ground tiles never join the early-prism set.
            self.assertNotIn((px + 1, py + 1), prisms)

    def test_floor_entry_bloom_eases_from_black(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.reset_revealed_tiles()
            game.ui_elapsed = 8.0
            game.update_revealed_tiles()
            game._fog_field_sync()
            game._fog_advance_easing()
            player_tile = (int(game.player.x), int(game.player.y))
            self.assertIn(player_tile, game._fog_ease)
            lattice = game._fog_lattice
            px, py = player_tile
            site = (px - py + _U_OFFSET, px + py)
            self.assertEqual(lattice.get_at(site)[0], 0)
            game.ui_elapsed = 8.1
            game._fog_advance_easing()
            mid = lattice.get_at(site)[0]
            self.assertGreater(mid, 0)
            self.assertLess(mid, 255)
            game.ui_elapsed = 13.0
            game._fog_advance_easing()
            self.assertEqual(lattice.get_at(site)[0], 255)
            self.assertEqual(game._fog_ease, {})

    def test_large_rebuild_skips_bloom(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.revealed_tiles = {
                (x, y) for x in range(5, 25) for y in range(5, 25)
            }
            game._fog_field_sync()
            self.assertEqual(game._fog_ease, {})
            lattice = game._fog_lattice
            self.assertEqual(lattice.get_at((15 - 15 + _U_OFFSET, 30))[0], 255)


if __name__ == "__main__":
    unittest.main()
