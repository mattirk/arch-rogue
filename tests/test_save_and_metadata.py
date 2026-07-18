from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import arch_rogue
from arch_rogue.content import RARITY_PROFILES, SECRET_HINTS, SHRINE_HINTS, TRAP_HINTS
from arch_rogue.game import ARCHETYPES, Game
from arch_rogue.models import Item


class SaveAndMetadataTests(unittest.TestCase):
    def tearDown(self) -> None:
        pass

    def test_metadata_content_profiles_and_save_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = Game(
                screen_size=(760, 520),
                headless=True,
                save_path=Path(tmpdir) / "run.json",
            )
            game.options_path = Path(tmpdir) / "options.json"
            game.rng.seed(1202)
            game.restart(ARCHETYPES[1])
            if game.story_intro_pending:
                self.assertTrue(game.choose_story_relic_path(0))
            try:
                self.assertEqual(arch_rogue.__version__, "4.2.3")
                self.assertIn("Cursed", RARITY_PROFILES)
                self.assertIn("Twilight Shrine", SHRINE_HINTS)
                self.assertIn("Moonlit Bargain", SECRET_HINTS)
                self.assertIn("Rune Trap", TRAP_HINTS)

                self.assertTrue(game.save_run())
                saved = json.loads(game.save_path.read_text(encoding="utf-8"))
                self.assertEqual(saved["version"], 5)
                self.assertEqual(saved["release"], "4.2.3")
            finally:
                pass

    def test_run_state_save_and_resume_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            save_path = Path(tmpdir) / "run.json"
            game = Game(screen_size=(960, 540), headless=True, save_path=save_path)
            try:
                game.rng.seed(2026)
                game.restart(ARCHETYPES[2])
                game.current_depth = 4
                game.elapsed = 73.5
                game.player.hp = 41
                game.player.mana = 12
                game.player.inventory.append(
                    Item(
                        "Beta Blade",
                        "weapon",
                        power=11,
                        rarity="Rare",
                        affixes=["Cruel", "of Force"],
                        unidentified=True,
                    )
                )
                game.player.equipment["armor"] = Item(
                    "Beta Mail", "armor", defense=5, rarity="Magic"
                )
                self.assertTrue(game.save_run())

                loaded = Game(
                    screen_size=(960, 540), headless=True, save_path=save_path
                )
                loaded.rng.seed(2026)
                self.assertTrue(loaded.load_run())

                self.assertEqual(loaded.state, "playing")
                self.assertEqual(loaded.current_depth, 4)
                self.assertEqual(loaded.player.class_name, "Arcanist")
                self.assertEqual(loaded.player.hp, 41)
                self.assertEqual(int(loaded.player.mana), 12)
                self.assertEqual(loaded.player.inventory[0].name, "Beta Blade")
                self.assertTrue(loaded.player.inventory[0].unidentified)
                armor = loaded.player.equipment["armor"]
                self.assertIsNotNone(armor)
                assert armor is not None
                self.assertEqual(armor.name, "Beta Mail")
                self.assertTrue(
                    loaded.dungeon.is_floor(loaded.player.x, loaded.player.y)
                )
            finally:
                pass


if __name__ == "__main__":
    unittest.main()
