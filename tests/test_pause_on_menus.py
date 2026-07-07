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

from arch_rogue.game import ARCHETYPES, Game
from arch_rogue.models import Enemy, Projectile


class PauseOnMenuTests(unittest.TestCase):
    def make_game(self, tmpdir: str, seed: int = 1305) -> Game:
        game = Game(
            screen_size=(760, 520),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.rng.seed(seed)
        game.restart(ARCHETYPES[0])
        if game.story_intro_pending:
            game.choose_story_relic_path(0)
        return game

    def test_inventory_open_freezes_player_and_enemies(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.active_cutscene = None
            # Place an enemy right next to the player and give it a short
            # attack timer so a running update would damage the player.
            enemy = Enemy(
                name="Test Stalker",
                kind="stalker",
                x=game.player.x + 1.0,
                y=game.player.y,
                max_hp=50,
                hp=50,
                speed=2.0,
                damage=10,
                xp=5,
                attack_range=1.5,
                attack_cooldown=0.1,
                attack_timer=0.0,
                aggro_range=10.0,
                damage_type="physical",
            )
            game.enemies.append(enemy)

            start_hp = game.player.hp
            start_x = game.player.x
            start_y = game.player.y

            game.inventory_open = True
            # Simulate several frames of updates while the inventory is open.
            for _ in range(20):
                game.update(0.05)

            self.assertTrue(game.inventory_open)
            self.assertEqual(game.player.hp, start_hp)
            self.assertAlmostEqual(game.player.x, start_x)
            self.assertAlmostEqual(game.player.y, start_y)
            # The enemy should not have moved toward the player while paused.
            self.assertAlmostEqual(enemy.x, game.player.x + 1.0)

    def test_projectiles_freeze_while_inventory_open(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.active_cutscene = None
            # A fast enemy projectile aimed past the player.
            proj = Projectile(
                x=game.player.x - 5.0,
                y=game.player.y,
                vx=20.0,
                vy=0.0,
                damage=5,
                owner="enemy",
                color=(255, 80, 80),
            )
            game.projectiles.append(proj)
            start_x = proj.x

            game.inventory_open = True
            for _ in range(10):
                game.update(0.05)

            self.assertAlmostEqual(proj.x, start_x)
            self.assertEqual(game.player.hp, game.player.max_hp)

    def test_resumes_after_menu_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.active_cutscene = None
            enemy = Enemy(
                name="Test Stalker",
                kind="stalker",
                x=game.player.x + 0.8,
                y=game.player.y,
                max_hp=50,
                hp=50,
                speed=2.5,
                damage=12,
                xp=5,
                attack_range=1.4,
                attack_cooldown=0.05,
                attack_timer=0.0,
                aggro_range=12.0,
                damage_type="physical",
            )
            game.enemies.append(enemy)

            game.inventory_open = True
            for _ in range(10):
                game.update(0.05)
            # Sanity: still full hp while paused.
            self.assertEqual(game.player.hp, game.player.max_hp)

            game.inventory_open = False
            # Now updates should resume and the enemy should land a hit.
            for _ in range(60):
                game.update(0.05)
                if game.player.hp < game.player.max_hp:
                    break

            self.assertLess(game.player.hp, game.player.max_hp)


if __name__ == "__main__":
    unittest.main()
