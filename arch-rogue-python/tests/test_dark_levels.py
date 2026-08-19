from __future__ import annotations

import os
import random
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame

from arch_rogue.constants import (
    DARK_LEVEL_LIGHT_RADIUS,
    DUNGEON_DEPTH,
)
from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game
from arch_rogue.models import Tile
from arch_rogue.run_flow import RunFlowMixin


class _DarkScheduleHarness(RunFlowMixin):
    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)


class DarkLevelTests(unittest.TestCase):
    def make_game(self, tmpdir: str, seed: int = 2404) -> Game:
        game = Game(
            screen_size=(820, 540),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.meta_progress = game.default_meta_progress()
        game.run_history = []
        game.rng.seed(seed)
        game.restart(ARCHETYPES[0])
        if game.story_intro_pending:
            self.assertTrue(game.choose_story_relic_path(0))
        game.active_cutscene = None
        return game

    def test_dark_floor_schedule_keeps_early_depths_light(self) -> None:
        dark_rolls = 0
        eligible_rolls = 0
        for seed in range(1_000):
            light_depths = _DarkScheduleHarness(seed).light_depths_for_run()
            self.assertTrue(set(range(1, 5)).issubset(light_depths))
            for depth in range(5, DUNGEON_DEPTH + 1):
                eligible_rolls += 1
                dark_rolls += depth not in light_depths

        ratio = dark_rolls / eligible_rolls
        self.assertGreater(ratio, 0.45)
        self.assertLess(ratio, 0.55)

    def test_floor_plan_darkness_metadata_matches_schedule(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, seed=2411)
            for plan in game.floor_plan:
                if plan.depth < 5:
                    self.assertFalse(plan.dark)
                if plan.dark:
                    self.assertGreaterEqual(plan.depth, 5)
                    self.assertIn("darkness", plan.risk_tags)
                    self.assertIn("dark level", plan.preview)
                else:
                    self.assertNotIn("darkness", plan.risk_tags)
                    self.assertNotIn("dark level", plan.preview)

    def test_darkness_toggle_roundtrips_through_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, seed=2411)
            game.current_depth = 2
            self.assertFalse(game.is_current_floor_dark())
            pygame.event.post(
                pygame.event.Event(
                    pygame.KEYDOWN,
                    key=pygame.K_d,
                    mod=pygame.KMOD_CTRL | pygame.KMOD_SHIFT,
                )
            )
            game.handle_events()
            self.assertTrue(game.is_current_floor_dark())
            saved_dark = game.is_current_floor_dark()
            self.assertTrue(game.save_run())

            loaded = Game(
                screen_size=(820, 540),
                headless=True,
                save_path=Path(tmpdir) / "run.json",
            )
            loaded.options_path = Path(tmpdir) / "options.json"
            loaded.meta_progress = loaded.default_meta_progress()
            loaded.run_history = []
            self.assertTrue(loaded.load_run(), loaded.last_load_error)
            self.assertEqual(loaded.current_depth, 2)
            self.assertEqual(loaded.is_current_floor_dark(), saved_dark)

    def test_dark_visibility_enemy_navigation_and_wall_hiding(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, seed=2421)
            try:
                # Dark visibility limits player sight but not enemy navigation.
                game.set_current_floor_dark(True)
                self.assertTrue(
                    game.can_see_world_position(game.player.x, game.player.y)
                )
                self.assertFalse(
                    game.can_see_world_position(
                        game.player.x + DARK_LEVEL_LIGHT_RADIUS + 1.2,
                        game.player.y,
                    )
                )
                self.assertGreater(
                    game.tile_visibility_alpha(int(game.player.x), int(game.player.y)),
                    0,
                )
                self.assertEqual(
                    game.tile_visibility_alpha(
                        int(game.player.x + DARK_LEVEL_LIGHT_RADIUS + 3),
                        int(game.player.y),
                    ),
                    0,
                )

                room = max(
                    game.dungeon.rooms,
                    key=lambda candidate: max(candidate.w, candidate.h),
                )
                if room.w >= room.h:
                    game.player.x = room.x + 1.5
                    game.player.y = room.y + room.h / 2
                    enemy_x = room.x + room.w - 1.5
                    enemy_y = game.player.y
                else:
                    game.player.x = room.x + room.w / 2
                    game.player.y = room.y + 1.5
                    enemy_x = game.player.x
                    enemy_y = room.y + room.h - 1.5

                enemy = game.enemies[0]
                enemy.x = enemy_x
                enemy.y = enemy_y
                enemy.aggro_range = 20.0
                enemy.attack_range = 0.25
                enemy.speed = 2.0
                game.enemies = [enemy]
                before_distance = game.light_distance_to_player(enemy.x, enemy.y)
                self.assertGreater(before_distance, DARK_LEVEL_LIGHT_RADIUS)
                self.assertFalse(game.can_see_world_position(enemy.x, enemy.y))
                game.update_enemies(0.25)
                after_distance = game.light_distance_to_player(enemy.x, enemy.y)
                self.assertLess(after_distance, before_distance)
                self.assertTrue(enemy.moving)

                game.draw()

                # Monsters behind walls are hidden in both light and dark modes.
                for x, column in enumerate(game.dungeon.tiles):
                    for y in range(len(column)):
                        game.dungeon.tiles[x][y] = Tile.FLOOR
                game.dungeon.tiles[4][2] = Tile.WALL
                game.player.x = 2.5
                game.player.y = 2.5
                enemy.x = 6.5
                enemy.y = 2.5
                game.enemies = [enemy]
                game.items = []
                game.traps = []
                game.shrines = []
                game.secrets = []
                game.story_guests = []
                game.projectiles = []
                game.slashes = []
                game.impact_effects = []
                game.floaters = []

                drawn: list[str] = []
                game.draw_enemy = lambda hidden_enemy: drawn.append(hidden_enemy.name)  # type: ignore[method-assign]

                for dark in (False, True):
                    game.set_current_floor_dark(dark)
                    drawn.clear()
                    game.draw_world_objects()
                    self.assertEqual(drawn, [])
                    self.assertFalse(game.has_line_of_sight_to_player(enemy.x, enemy.y))

                    enemy.x = 3.5
                    drawn.clear()
                    game.draw_world_objects()
                    self.assertEqual(drawn, [enemy.name])
                    self.assertTrue(game.has_line_of_sight_to_player(enemy.x, enemy.y))

                    enemy.x = 6.5
            finally:
                pass

    def test_stationary_reveal_pass_is_cached_and_invalidates_safely(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, seed=2441)
            game.set_current_floor_dark(False)
            game.revealed_tiles = set()
            game.update_revealed_tiles()

            first_state = game._last_reveal_state
            first_tiles = set(game.revealed_tiles)
            game.update_revealed_tiles()
            self.assertIs(game._last_reveal_state, first_state)
            self.assertEqual(game.revealed_tiles, first_tiles)

            # External/test tooling may clear the set in place. The central-tile
            # guard must detect that even though set identity and position match.
            game.revealed_tiles.clear()
            game.update_revealed_tiles()
            self.assertGreater(len(game.revealed_tiles), 0)
            self.assertIsNot(game._last_reveal_state, first_state)

            moved_state = game._last_reveal_state
            game.player.x += 0.125
            game.update_revealed_tiles()
            self.assertIsNot(game._last_reveal_state, moved_state)

            retained_tiles = game.revealed_tiles
            game.set_current_floor_dark(True)
            game._last_reveal_state = (
                retained_tiles,
                game.current_depth - 1,
                game.player.x,
                game.player.y,
            )
            game.update_revealed_tiles()
            self.assertIsNone(game._last_reveal_state)

    def test_revealed_tiles_roundtrip_through_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, seed=2451)
            try:
                game.set_current_floor_dark(False)
                game.player.x = 2.5
                game.player.y = 2.5
                game.revealed_tiles = set()
                game.update_revealed_tiles()
                before = set(game.revealed_tiles)
                self.assertGreater(len(before), 0)
                self.assertTrue(game.save_run())

                loaded = Game(
                    screen_size=(820, 540),
                    headless=True,
                    save_path=Path(tmpdir) / "run.json",
                )
                loaded.options_path = Path(tmpdir) / "options.json"
                loaded.meta_progress = loaded.default_meta_progress()
                loaded.run_history = []
                self.assertTrue(loaded.load_run(), loaded.last_load_error)
                self.assertEqual(loaded.revealed_tiles, before)
            finally:
                pass


if __name__ == "__main__":
    unittest.main()
