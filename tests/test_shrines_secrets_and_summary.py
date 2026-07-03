from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


from arch_rogue.game import (
    ARCHETYPES,
    ARMOR_DEFINITIONS,
    DUNGEON_THEMES,
    ENEMY_DEFINITIONS,
    RUN_MODIFIERS,
    SECRET_TYPES,
    SHRINE_TYPES,
    WEAPON_DEFINITIONS,
    Game,
)
from arch_rogue.models import Item, Projectile, RunStats, SecretCache, Shrine, Trap


class Rc2ContentUxTests(unittest.TestCase):
    def make_game(self, seed: int = 4321) -> Game:
        game = Game(screen_size=(960, 540), headless=True)
        game.rng.seed(seed)
        game.restart(ARCHETYPES[0])
        return game

    def tearDown(self) -> None:
        pass

    def test_expanded_content_tables_are_valid(self) -> None:
        self.assertGreaterEqual(len(DUNGEON_THEMES), 5)
        self.assertGreaterEqual(len(RUN_MODIFIERS), 6)
        self.assertIn("Haste Shrine", SHRINE_TYPES)
        self.assertIn("Fortune Shrine", SHRINE_TYPES)
        self.assertIn("Sealed Armory", SECRET_TYPES)
        self.assertIn(
            "Grave Archer", {definition.name for definition in ENEMY_DEFINITIONS}
        )
        self.assertGreaterEqual(len(WEAPON_DEFINITIONS), 5)
        self.assertGreaterEqual(len(ARMOR_DEFINITIONS), 5)

        for definition in ENEMY_DEFINITIONS:
            self.assertGreater(definition.max_hp, 0)
            self.assertGreater(definition.weight, 0)
            self.assertIn(definition.kind, {"melee", "ranged"})

    def test_new_shrine_and_secret_effects_then_summary_render(self) -> None:
        game = self.make_game()
        try:
            # --- new shrine effects update stats and rewards ---
            base_speed = game.player.speed
            haste = Shrine(game.player.x, game.player.y, "Haste Shrine")
            game.activate_shrine(haste)
            self.assertTrue(haste.used)
            self.assertEqual(game.run_stats.shrines_used, 1)
            self.assertGreater(game.player.speed, base_speed)
            self.assertEqual(game.player.dash_timer, 0.0)

            item_count = len(game.items)
            fortune = Shrine(game.player.x, game.player.y, "Fortune Shrine")
            game.activate_shrine(fortune)
            self.assertTrue(fortune.used)
            self.assertEqual(game.run_stats.shrines_used, 2)
            self.assertGreaterEqual(len(game.items), item_count + 2)

            # --- sealed armory secret drops equipment and updates stats ---
            game.items.clear()
            secret = SecretCache(
                game.player.x, game.player.y, "Sealed Armory", revealed=True
            )
            game.open_secret(secret)
            self.assertTrue(secret.opened)
            self.assertEqual(game.run_stats.secrets_opened, 1)
            self.assertGreaterEqual(len(game.items), 2)
            self.assertTrue(
                all(item.slot in {"weapon", "armor"} for item in game.items)
            )

            # --- run summary and help overlay are renderable ---
            game.elapsed = 125.0
            game.run_stats = RunStats(
                kills=7,
                loot_picked_up=3,
                potions_used=2,
                shrines_used=1,
                secrets_opened=1,
                traps_triggered=1,
                damage_taken=42,
                boss_killed=True,
            )
            summary = game.run_summary_lines()
            self.assertIn("Time 02:05", summary[0])
            self.assertIn("Boss defeated", summary[1])
            self.assertIn("Loot 3", summary[2])
            self.assertIn("Traps triggered 1", summary[3])

            game.player.moving = True
            game.player.move_x = 1.0
            game.player.move_y = 0.0
            game.player.anim_time = 0.4
            if game.enemies:
                game.enemies[0].moving = True
                game.enemies[0].move_x = -1.0
                game.enemies[0].move_y = 0.25
                game.enemies[0].facing_x = -1.0
                game.enemies[0].anim_time = 0.35
            game.items.append(
                Item(
                    "Render Unique",
                    "weapon",
                    power=1,
                    rarity="Unique",
                    x=game.player.x + 0.5,
                    y=game.player.y,
                )
            )
            game.traps.append(
                Trap(game.player.x + 0.8, game.player.y, "Poison Needle", 1)
            )
            game.shrines.append(
                Shrine(game.player.x, game.player.y + 0.8, "Haste Shrine")
            )
            game.projectiles.append(
                Projectile(
                    game.player.x, game.player.y, 3.0, 1.0, 1, "player", (70, 165, 255)
                )
            )
            game.slashes.append((game.player.x, game.player.y, 0.12, 1.0, 0.0))
            game.draw_help_overlay()
            game.show_help = True
            game.draw()
        finally:
            pass


if __name__ == "__main__":
    unittest.main()
