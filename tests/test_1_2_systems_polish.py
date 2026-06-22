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

import pygame

import arch_rogue
from arch_rogue.content import RARITY_PROFILES, SECRET_HINTS, SHRINE_HINTS, TRAP_HINTS
from arch_rogue.game import ARCHETYPES, Game
from arch_rogue.models import Item, SecretCache, Shrine, Trap


class SystemsPolish12Tests(unittest.TestCase):
    def tearDown(self) -> None:
        pygame.quit()

    def make_game(self, tmpdir: str, seed: int = 1202) -> Game:
        game = Game(
            screen_size=(760, 520),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.rng.seed(seed)
        game.restart(ARCHETYPES[1])
        return game

    def test_1_2_metadata_content_profiles_and_save_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                self.assertEqual(arch_rogue.__version__, "2.0.0")
                self.assertIn("Cursed", RARITY_PROFILES)
                self.assertIn("Twilight Shrine", SHRINE_HINTS)
                self.assertIn("Moonlit Bargain", SECRET_HINTS)
                self.assertIn("Rune Trap", TRAP_HINTS)

                self.assertTrue(game.save_run())
                saved = json.loads(game.save_path.read_text(encoding="utf-8"))
                self.assertEqual(saved["version"], 4)
                self.assertEqual(saved["release"], "2.0.0")
            finally:
                pygame.quit()

    def test_contextual_interaction_hints_explain_events_and_loot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                game.items.clear()
                game.shrines.clear()
                game.secrets.clear()
                game.traps.clear()
                px, py = game.player.x, game.player.y

                item = Item(
                    "Cursed Test Blade",
                    "weapon",
                    power=10,
                    rarity="Cursed",
                    cursed=True,
                    x=px,
                    y=py,
                )
                game.items.append(item)
                hint = game.current_interaction_hint()
                self.assertIsNotNone(hint)
                assert hint is not None
                self.assertEqual(hint[0], "E")
                self.assertIn("Pick up", hint[1])
                self.assertIn("cursed", hint[2])

                game.items.clear()
                game.shrines.append(Shrine(px, py, "Twilight Shrine"))
                hint = game.current_interaction_hint()
                self.assertIsNotNone(hint)
                assert hint is not None
                self.assertIn("Trades blood", hint[2])

                game.shrines.clear()
                game.secrets.append(
                    SecretCache(px, py, "Moonlit Bargain", revealed=True)
                )
                hint = game.current_interaction_hint()
                self.assertIsNotNone(hint)
                assert hint is not None
                self.assertIn("Costs blood", hint[2])

                game.secrets.clear()
                game.traps.append(Trap(px + 0.8, py, "Rune Trap", 13))
                hint = game.current_interaction_hint()
                self.assertIsNotNone(hint)
                assert hint is not None
                self.assertEqual(hint[0], "!")
                self.assertIn("Arcane", hint[2])
            finally:
                pygame.quit()

    def test_visual_effects_damage_flash_and_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                game.enemies.clear()
                game.traps.clear()
                game.projectiles.clear()
                game.player.hp = game.player.max_hp

                amount = game.take_player_damage(12, source="trap")
                self.assertGreater(amount, 0)
                self.assertGreater(game.screen_flash_ttl, 0)
                self.assertTrue(game.impact_effects)

                for _ in range(20):
                    game.update(0.05)
                self.assertEqual(game.impact_effects, [])
                self.assertEqual(game.screen_flash_ttl, 0.0)
            finally:
                pygame.quit()

    def test_inventory_summaries_skill_upgrades_and_compact_ui_render(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                blade = Item("Readable Blade", "weapon", power=12, rarity="Rare")
                potion = Item("Minor Healing Potion", "potion", heal=35)
                unknown = Item(
                    "Mystery Mail",
                    "armor",
                    defense=4,
                    rarity="Magic",
                    unidentified=True,
                )
                game.player.inventory = [blade, potion, unknown]
                game.player.hp = max(1, game.player.max_hp - 20)

                self.assertIn("damage vs equipped", game.item_decision_summary(blade))
                self.assertIn("missing", game.item_decision_summary(potion))
                self.assertIn("Unknown stats", game.item_decision_summary(unknown))

                self.assertTrue(game.grant_skill_upgrade(reason="test"))
                upgrades = game.acquired_skill_upgrades()
                self.assertTrue(upgrades)
                self.assertIsInstance(upgrades[-1][0], str)

                game.inventory_open = True
                game.draw_inventory()
                game.draw_help_overlay()
                game.state = "title"
                game.draw_title_menu()
                game.state = "options"
                game.draw_options_menu()
            finally:
                pygame.quit()

    def test_loads_older_compatible_save_without_visual_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                old_save = game.serialize_run_state()
                old_save["version"] = 1
                old_save["release"] = "1.0.0"
                old_save["player"].pop("skill_upgrades", None)
                old_save["run_stats"].pop("upgrades_chosen", None)
                game.save_path.write_text(json.dumps(old_save), encoding="utf-8")

                loaded = Game(
                    screen_size=(760, 520),
                    headless=True,
                    save_path=game.save_path,
                )
                self.assertTrue(loaded.load_run(), loaded.last_load_error)
                self.assertEqual(loaded.state, "playing")
                self.assertEqual(loaded.impact_effects, [])
                self.assertEqual(loaded.screen_flash_ttl, 0.0)
            finally:
                pygame.quit()


if __name__ == "__main__":
    unittest.main()
