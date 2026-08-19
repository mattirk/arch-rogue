from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from arch_rogue.game import ARCHETYPES, Game
from arch_rogue.models import Enemy, Projectile, Shopkeeper


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

    def assert_overlay_freezes_actor_clocks(
        self, game: Game, overlay_attribute: str
    ) -> None:
        game.active_cutscene = None
        enemy = Enemy(
            name="Clock Test Enemy",
            kind="stalker",
            x=game.player.x + 4.0,
            y=game.player.y,
            max_hp=50,
            hp=50,
            speed=2.5,
            damage=12,
            xp=5,
            attack_range=1.4,
            attack_cooldown=0.5,
        )
        game.enemies.append(enemy)
        game.player.moving = True
        game.player.anim_time = 0.75
        enemy.moving = True
        enemy.anim_time = 1.25
        game.set_player_action_visual("cast", 0.6)
        game.player_action_elapsed = 0.15
        game.player_hit_flash = 0.4
        game.enemy_hit_flashes[id(enemy)] = 0.35

        actor_clocks_before = (
            game.player.anim_time,
            enemy.anim_time,
            game.player_action_ttl,
            game.player_action_elapsed,
            game.player_action_duration,
            game.player_hit_flash,
            game.enemy_hit_flashes[id(enemy)],
        )
        elapsed_before = game.elapsed
        npc_animation_before = game.friendly_npc_dance_progress()

        setattr(game, overlay_attribute, True)
        game.update(0.1)

        self.assertEqual(
            (
                game.player.anim_time,
                enemy.anim_time,
                game.player_action_ttl,
                game.player_action_elapsed,
                game.player_action_duration,
                game.player_hit_flash,
                game.enemy_hit_flashes[id(enemy)],
            ),
            actor_clocks_before,
        )
        self.assertAlmostEqual(game.elapsed, elapsed_before + 0.1)
        self.assertNotEqual(game.friendly_npc_dance_progress(), npc_animation_before)

    def test_inventory_overlay_freezes_actor_animation_and_action_clocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assert_overlay_freezes_actor_clocks(
                self.make_game(tmpdir), "inventory_open"
            )

    def test_character_overlay_freezes_actor_animation_and_action_clocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assert_overlay_freezes_actor_clocks(
                self.make_game(tmpdir), "character_menu_open"
            )

    def test_shop_overlay_freezes_actor_animation_and_action_clocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assert_overlay_freezes_actor_clocks(
                self.make_game(tmpdir), "shop_open"
            )

    def test_shop_pauses_and_then_resumes_simulation(self) -> None:
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
            shopkeeper = Shopkeeper(
                x=game.player.x + 1.0,
                y=game.player.y,
                name="Test Merchant",
                role="general",
            )
            game.shopkeepers.append(shopkeeper)
            game.shop_open = True
            game.active_shopkeeper = shopkeeper
            start_hp = game.player.hp
            start_player = (game.player.x, game.player.y)
            start_enemy = (enemy.x, enemy.y)

            for _ in range(20):
                game.update(0.05)

            self.assertEqual(game.player.hp, start_hp)
            self.assertEqual((game.player.x, game.player.y), start_player)
            self.assertEqual((enemy.x, enemy.y), start_enemy)

            game.close_shop()
            for _ in range(60):
                game.update(0.05)
                if game.player.hp < start_hp:
                    break

            self.assertLess(game.player.hp, start_hp)

    def test_inventory_pauses_and_then_resumes_simulation(self) -> None:
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
            projectile = Projectile(
                x=game.player.x - 5.0,
                y=game.player.y,
                vx=20.0,
                vy=0.0,
                damage=5,
                owner="enemy",
                color=(255, 80, 80),
            )
            game.enemies.append(enemy)
            game.projectiles.append(projectile)
            start_hp = game.player.hp
            start_player = (game.player.x, game.player.y)
            start_enemy = (enemy.x, enemy.y)
            start_projectile_x = projectile.x

            game.inventory_open = True
            for _ in range(20):
                game.update(0.05)

            self.assertEqual(game.player.hp, start_hp)
            self.assertEqual((game.player.x, game.player.y), start_player)
            self.assertEqual((enemy.x, enemy.y), start_enemy)
            self.assertAlmostEqual(projectile.x, start_projectile_x)

            game.inventory_open = False
            for _ in range(60):
                game.update(0.05)
                if game.player.hp < start_hp:
                    break

            self.assertLess(game.player.hp, start_hp)


if __name__ == "__main__":
    unittest.main()
