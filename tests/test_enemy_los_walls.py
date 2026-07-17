from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame  # noqa: F401  (required to initialize pygame subsystems in tests)

from arch_rogue.content import ARCHETYPES
from arch_rogue.dungeon import MAP_H, MAP_W
from arch_rogue.game import Game
from arch_rogue.models import Enemy, Tile


def _make_melee_enemy(x: float, y: float, attack_range: float = 4.0) -> Enemy:
    return Enemy(
        "Test Dummy",
        "melee",
        x,
        y,
        200,
        200,
        1.0,
        6,
        12,
        attack_range,
        1.0,
    )


class EnemyLineOfSightTests(unittest.TestCase):
    def make_game(self, tmpdir, archetype_index=0, seed=4242) -> Game:
        game = Game(
            screen_size=(960, 600),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.rng.seed(seed)
        game.restart(ARCHETYPES[archetype_index])
        if game.story_intro_pending:
            self.assertTrue(game.choose_story_relic_path(0))
        game.active_cutscene = None
        return game

    def test_dungeon_line_of_sight_blocked_and_clear(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            dungeon = game.dungeon
            cx, cy = int(game.player.x), int(game.player.y)
            self.assertGreater(MAP_W - cx, 6)
            # Player and target sit on floor with two wall tiles between them.
            dungeon.tiles[cx][cy] = Tile.FLOOR
            dungeon.tiles[cx + 3][cy] = Tile.FLOOR
            dungeon.tiles[cx + 1][cy] = Tile.WALL
            dungeon.tiles[cx + 2][cy] = Tile.WALL
            x0, y0 = cx + 0.5, cy + 0.5
            x1, y1 = cx + 3.5, cy + 0.5
            self.assertFalse(dungeon.line_of_sight(x0, y0, x1, y1))
            dungeon.tiles[cx + 1][cy] = Tile.FLOOR
            dungeon.tiles[cx + 2][cy] = Tile.FLOOR
            self.assertTrue(dungeon.line_of_sight(x0, y0, x1, y1))

    def test_dungeon_line_of_sight_blocks_closed_diagonal_corner(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            dungeon = game.dungeon
            cx, cy = int(game.player.x), int(game.player.y)
            self.assertGreater(MAP_W - cx, 3)
            self.assertGreater(MAP_H - cy, 3)
            dungeon.tiles[cx][cy] = Tile.FLOOR
            dungeon.tiles[cx + 1][cy + 1] = Tile.FLOOR
            dungeon.tiles[cx + 1][cy] = Tile.WALL
            dungeon.tiles[cx][cy + 1] = Tile.WALL
            start = (cx + 0.5, cy + 0.5)
            target = (cx + 1.5, cy + 1.5)

            self.assertFalse(dungeon.line_of_sight(*start, *target))

            dungeon.tiles[cx + 1][cy] = Tile.FLOOR
            self.assertTrue(dungeon.line_of_sight(*start, *target))

    def test_enemy_cannot_melee_through_wall(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            dungeon = game.dungeon
            cx, cy = int(game.player.x), int(game.player.y)
            self.assertGreater(MAP_W - cx, 6)
            game.player.x = cx + 0.5
            game.player.y = cy + 0.5
            dungeon.tiles[cx][cy] = Tile.FLOOR
            dungeon.tiles[cx + 3][cy] = Tile.FLOOR
            dungeon.tiles[cx + 1][cy] = Tile.WALL
            dungeon.tiles[cx + 2][cy] = Tile.WALL
            enemy = _make_melee_enemy(cx + 3.5, cy + 0.5, attack_range=4.0)
            enemy.attack_timer = 0.0
            game.enemies = [enemy]

            hp_before = game.player.hp
            # Distance ~3 <= attack_range, so without a LOS check the enemy
            # would melee the player this frame. The wall must block it.
            game.update_enemies(0.1)
            self.assertEqual(game.player.hp, hp_before)
            self.assertEqual(enemy.attack_timer, 0.0)

            # Clear the wall -> LOS restored -> the enemy now lands its hit.
            dungeon.tiles[cx + 1][cy] = Tile.FLOOR
            dungeon.tiles[cx + 2][cy] = Tile.FLOOR
            enemy.attack_timer = 0.0
            game.update_enemies(0.1)
            self.assertLess(game.player.hp, hp_before)

    def test_enemy_cannot_melee_through_closed_diagonal_corner(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            dungeon = game.dungeon
            cx, cy = int(game.player.x), int(game.player.y)
            game.player.x, game.player.y = cx + 0.5, cy + 0.5
            dungeon.tiles[cx][cy] = Tile.FLOOR
            dungeon.tiles[cx + 1][cy + 1] = Tile.FLOOR
            dungeon.tiles[cx + 1][cy] = Tile.WALL
            dungeon.tiles[cx][cy + 1] = Tile.WALL
            enemy = _make_melee_enemy(cx + 1.5, cy + 1.5, attack_range=2.0)
            enemy.speed = 0.0
            game.enemies = [enemy]

            hp_before = game.player.hp
            game.update_enemies(0.1)
            self.assertEqual(game.player.hp, hp_before)
            self.assertEqual(enemy.attack_timer, 0.0)

            dungeon.tiles[cx + 1][cy] = Tile.FLOOR
            game.update_enemies(0.1)
            self.assertLess(game.player.hp, hp_before)

    def test_enemy_los_runs_only_when_an_attack_is_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            enemy = _make_melee_enemy(
                game.player.x + 1.0,
                game.player.y,
                attack_range=1.5,
            )
            enemy.aggro_range = 20.0
            enemy.speed = 0.0
            game.enemies = [enemy]

            with patch.object(game.dungeon, "line_of_sight", return_value=True) as los:
                enemy.attack_timer = 0.8
                game.update_enemies(0.1)
                los.assert_not_called()

                enemy.x = game.player.x + 4.0
                enemy.attack_timer = 0.0
                game.update_enemies(0.1)
                los.assert_not_called()

                enemy.x = game.player.x + 1.0
                enemy.attack_timer = 0.0
                game.update_enemies(0.1)
                los.assert_called_once()
                self.assertGreater(enemy.attack_timer, 0.0)


if __name__ == "__main__":
    unittest.main()
