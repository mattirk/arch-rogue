from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from arch_rogue.combat.damage import DamageContext

from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game
from arch_rogue.models import Enemy, Item


class DamageContextAndPlayerResistanceTests(unittest.TestCase):
    def make_game(
        self, tmpdir: str, archetype_index: int = 0, seed: int = 2202
    ) -> Game:
        game = Game(
            screen_size=(820, 540),
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

    def _make_enemy(self, game: Game, hp: int = 100) -> Enemy:
        return Enemy(
            "Target",
            "melee",
            game.player.x + 1.0,
            game.player.y,
            hp,
            hp,
            1.0,
            5,
            1,
            0.8,
            1.0,
        )

    # ------------------------------------------------------------------
    # #1 DamageContext
    # ------------------------------------------------------------------
    def test_damage_context_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            enemy = self._make_enemy(game)
            ctx = DamageContext(target=enemy, amount=10)
            self.assertIs(ctx.target, enemy)
            self.assertEqual(ctx.amount, 10)
            self.assertEqual(ctx.damage_type, "physical")
            self.assertEqual(ctx.knockback_from, (0.0, 0.0))
            self.assertEqual(ctx.status_effect, "")
            self.assertEqual(ctx.status_duration, 0.0)
            self.assertEqual(ctx.source, "")
            self.assertFalse(ctx.is_crit)
            # frozen
            with self.assertRaises(Exception):
                ctx.amount = 5  # type: ignore[misc]



    def test_damage_context_source_and_crit_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            enemy = self._make_enemy(game)
            ctx = DamageContext(
                target=enemy, amount=5, damage_type="holy", source="counter",
                is_crit=True, knockback_from=(0.0, 1.0),
            )
            self.assertEqual(ctx.source, "counter")
            self.assertTrue(ctx.is_crit)
            self.assertEqual(ctx.damage_type, "holy")

    # ------------------------------------------------------------------
    # #2 Unified player resistance table
    # ------------------------------------------------------------------


    def test_player_typed_resistance_no_armor_is_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.player.equipment = {slot: None for slot in game.player.equipment}
            for dt in ("physical", "fire", "frost", "arcane", "shadow", "poison", "holy"):
                self.assertEqual(game.player_typed_resistance(dt), 0.0, dt)

    def test_player_typed_resistance_armor_defense_and_typed_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.player.equipment = {slot: None for slot in game.player.equipment}
            game.player.equipment["armor"] = Item(
                "Frost Mail", "armor", defense=10, damage_type="frost"
            )
            # defense 10 * 0.006 = 0.06; frost-typed match +0.08 -> 0.14 vs frost
            self.assertAlmostEqual(game.player_typed_resistance("frost"), 0.14)
            # non-matching type: only the defense contribution
            self.assertAlmostEqual(game.player_typed_resistance("fire"), 0.06)

    def test_player_typed_resistance_affix_table_branches_on_damage_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.player.equipment = {slot: None for slot in game.player.equipment}
            game.player.equipment["armor"] = Item(
                "Warded Plate", "armor", defense=0, affixes=["Grounded", "Sealed"]
            )
            self.assertAlmostEqual(game.player_typed_resistance("arcane"), 0.12)
            self.assertAlmostEqual(game.player_typed_resistance("shadow"), 0.10)
            self.assertAlmostEqual(game.player_typed_resistance("poison"), 0.10)
            # affix does not apply to unrelated damage types
            self.assertAlmostEqual(game.player_typed_resistance("fire"), 0.0)

    def test_player_typed_resistance_unique_and_status_and_temporal_aegis(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)  # Warden
            game.player.equipment = {slot: None for slot in game.player.equipment}
            game.player.equipment["armor"] = Item("Cloak", "armor", defense=0, damage_type="")
            game.player.equipment["weapon"] = Item(
                "Glacial Blade", "weapon", power=1, unique_effect="glacial ward"
            )
            # glacial ward -> +0.15 vs frost only
            self.assertAlmostEqual(game.player_typed_resistance("frost"), 0.15)
            self.assertAlmostEqual(game.player_typed_resistance("fire"), 0.0)

            # aegis status -> all-types +0.24
            game.set_player_status("aegis", 1.0)
            self.assertAlmostEqual(game.player_typed_resistance("fire"), 0.24)
            self.assertAlmostEqual(game.player_typed_resistance("frost"), 0.15 + 0.24)

            # Warden Temporal Aegis: time_skip active + warden_unyielding -> +0.20
            game.player.skill_upgrades.append("warden_unyielding")
            game.player.time_skip_timer = 2.0
            self.assertAlmostEqual(
                game.player_typed_resistance("physical"), 0.24 + 0.20
            )

    def test_take_player_damage_uses_typed_resistance_for_reduction(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.player.equipment = {slot: None for slot in game.player.equipment}
            game.player.equipment["armor"] = Item(
                "Frost Mail", "armor", defense=10, damage_type="frost"
            )
            game.player.hp = game.player.max_hp
            attacker = self._make_enemy(game)
            # Same raw hit, two damage types. Frost is resisted (typed match +
            # defense); physical is only the defense contribution. Frost taken
            # must be strictly less than physical taken.
            physical_taken = game.take_player_damage(
                30, source="melee", damage_type="physical", attacker=attacker
            )
            game.player.hp = game.player.max_hp
            frost_taken = game.take_player_damage(
                30, source="melee", damage_type="frost", attacker=attacker
            )
            self.assertLess(frost_taken, physical_taken)


if __name__ == "__main__":
    unittest.main()