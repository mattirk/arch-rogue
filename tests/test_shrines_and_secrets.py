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
from arch_rogue.models import SecretCache, Shrine


class ShrineAndSecretTests(unittest.TestCase):
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

    def test_new_shrine_and_secret_effects(self) -> None:
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

        finally:
            pass


if __name__ == "__main__":
    unittest.main()
