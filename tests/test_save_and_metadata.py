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
                self.assertEqual(arch_rogue.__version__, "4.7.0")
                self.assertIn("Cursed", RARITY_PROFILES)
                self.assertIn("Twilight Shrine", SHRINE_HINTS)
                self.assertIn("Moonlit Bargain", SECRET_HINTS)
                self.assertIn("Rune Trap", TRAP_HINTS)

                self.assertTrue(game.save_run())
                saved = json.loads(game.save_path.read_text(encoding="utf-8"))
                self.assertEqual(saved["version"], 5)
                self.assertEqual(saved["release"], "4.7.0")
            finally:
                pass

    def test_pre_455_save_on_stairs_restores_to_adjacent_walkable_tile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            save_path = Path(tmpdir) / "run.json"
            game = Game(screen_size=(960, 540), headless=True, save_path=save_path)
            game.rng.seed(455)
            game.restart(ARCHETYPES[0])
            if game.story_intro_pending:
                self.assertTrue(game.choose_story_relic_path(0))
            stairs = game.dungeon.stairs
            game.player.x, game.player.y = stairs[0] + 0.5, stairs[1] + 0.5
            self.assertTrue(game.save_run())

            loaded = Game(screen_size=(960, 540), headless=True, save_path=save_path)
            loaded.rng.seed(455)
            self.assertTrue(loaded.load_run())
            self.assertNotEqual(
                (int(loaded.player.x), int(loaded.player.y)),
                loaded.dungeon.stairs,
            )
            self.assertFalse(
                loaded.dungeon.blocked_for_radius(
                    loaded.player.x,
                    loaded.player.y,
                    0.27,
                    block_stairs=True,
                )
            )

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

    def test_restored_enemy_color_is_hashable_tuple(self) -> None:
        # Regression: enemies are serialized via __dict__, so the color tuple
        # becomes a JSON list on disk. Restoring via Enemy(**enemy) used to keep
        # that list, which crashed draw_impact's overlay cache (the cache key is a
        # tuple containing color, and a list makes it unhashable). The restore
        # path must normalize color back to a tuple.
        from arch_rogue.models import Enemy

        with tempfile.TemporaryDirectory() as tmpdir:
            save_path = Path(tmpdir) / "run.json"
            game = Game(screen_size=(960, 540), headless=True, save_path=save_path)
            try:
                game.rng.seed(2026)
                game.restart(ARCHETYPES[2])
                # Force at least one enemy into the run so the save has a color
                # field to round-trip. restart() leaves enemies empty until the
                # floor is populated, so append one directly.
                game.enemies.append(
                    Enemy(
                        "Cultist",
                        "caster",
                        4.5,
                        4.5,
                        18,
                        18,
                        2.4,
                        6,
                        7,
                        5.0,
                        1.2,
                        color=(160, 70, 200),
                    )
                )
                for enemy in game.enemies:
                    self.assertIsInstance(enemy.color, tuple)
                self.assertTrue(game.save_run())

                loaded = Game(
                    screen_size=(960, 540), headless=True, save_path=save_path
                )
                self.assertTrue(loaded.load_run())
                self.assertTrue(loaded.enemies, "restored run should have enemies")
                for enemy in loaded.enemies:
                    self.assertIsInstance(
                        enemy.color,
                        tuple,
                        "restored enemy.color must be a tuple, not a list",
                    )
                    # The exact failure mode of the crash: hashing a tuple that
                    # contains enemy.color must succeed.
                    hash(("death", 0, 0, 0, enemy.color))
            finally:
                pass

    def test_add_impact_normalizes_list_color(self) -> None:
        # Defensive: add_impact is called from many code paths. If any caller
        # passes a list color, the ImpactEffect must still get a tuple so the
        # draw_impact overlay cache key stays hashable.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = Game(
                screen_size=(960, 540), headless=True, save_path=Path(tmpdir) / "run.json"
            )
            try:
                game.rng.seed(2026)
                game.restart(ARCHETYPES[2])
                game.add_impact(0.0, 0.0, [255, 90, 70], ttl=0.3, kind="burst")
                self.assertEqual(len(game.impact_effects), 1)
                effect = game.impact_effects[0]
                self.assertIsInstance(effect.color, tuple)
                # The draw_impact overlay cache builds a tuple key containing
                # effect.color; that key must be hashable.
                hash((effect.kind, effect.archetype, 0, 0, 0, effect.color))
            finally:
                pass


if __name__ == "__main__":
    unittest.main()
