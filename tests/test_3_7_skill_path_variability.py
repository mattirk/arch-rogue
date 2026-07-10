from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame  # noqa: F401  (required to initialize pygame subsystems in tests)

from arch_rogue.content import (
    ARCHETYPES,
    discipline_by_key,
)
from arch_rogue.game import Game
from arch_rogue.models import Enemy


def _make_enemy(x: float, y: float, hp: int = 200) -> Enemy:
    return Enemy(
        "Test Dummy",
        "melee",
        x,
        y,
        hp,
        hp,
        1.0,
        6,
        12,
        1.0,
        1.0,
    )


class SkillPathVariability37Tests(unittest.TestCase):
    def make_game(self, tmpdir, archetype_index=0, seed=3701) -> Game:
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

    # --- choose_discipline enforces the two-path limit ---------------

    def test_choose_discipline_enforces_two_path_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            try:
                game.player.skill_points = 10

                # Commit to Bulwark and Riposte (two degree-1 entries).
                self.assertTrue(game.choose_discipline("warden_bulwark"))
                self.assertTrue(game.choose_discipline("warden_riposte"))

                # Degree-1 entries of the other two paths must be rejected.
                self.assertFalse(game.choose_discipline("warden_smite"))
                self.assertFalse(game.choose_discipline("warden_ward"))

                # available_disciplines excludes Vow/Fortress degree-1 nodes
                # but still offers deeper nodes in committed paths.
                choices = game.available_disciplines()
                choice_keys = {node.key for node in choices}
                self.assertNotIn("warden_smite", choice_keys)
                self.assertNotIn("warden_ward", choice_keys)
                self.assertIn("warden_aegis", choice_keys)  # Bulwark Degree 2
                self.assertIn("warden_counter", choice_keys)  # Riposte Degree 2
            finally:
                pass

    # --- discipline_state distinguishes path_locked vs locked ----------

    def test_discipline_state_reports_path_locked(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            try:
                game.player.skill_points = 10

                smite = discipline_by_key("warden_smite")
                self.assertIsNotNone(smite)
                # Before any commitment Vow Degree 1 is simply available.
                self.assertEqual(game.discipline_state(smite), "available")

                # A prereq-locked node (Bulwark Degree 2 before Bulwark Degree 1) is "locked".
                aegis = discipline_by_key("warden_aegis")
                self.assertIsNotNone(aegis)
                self.assertEqual(game.discipline_state(aegis), "locked")

                # Commit to two paths -> Vow becomes path_locked.
                self.assertTrue(game.choose_discipline("warden_bulwark"))
                self.assertTrue(game.choose_discipline("warden_riposte"))
                self.assertEqual(game.discipline_state(smite), "path_locked")
            finally:
                pass

    # --- Arc Bolt fan + pierce + homing progression ----------------------

    def test_arc_bolt_multi_shot_with_splinter_and_pierce_homing_progression(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=2)
            try:
                # splinter Degree 1 -> 2 bolts (one extra shard)
                game.player.skill_upgrades.append("arcanist_splinter")
                game.projectiles.clear()
                game.player.mana = game.player.max_mana
                game.player.bolt_timer = 0.0
                game.player.facing_x = 1.0
                game.player.facing_y = 0.0
                game.player_cast_bolt()
                self.assertEqual(len(game.projectiles), 2)
                self.assertTrue(all(p.pierce == 0 for p in game.projectiles))

                # + overload Degree 2 -> 3 bolts (split on impact) and pierce 1
                game.player.skill_upgrades.append("arcanist_overload")
                game.projectiles.clear()
                game.player.bolt_timer = 0.0
                game.player.mana = game.player.max_mana
                game.player_cast_bolt()
                self.assertEqual(len(game.projectiles), 3)
                self.assertTrue(all(p.pierce == 1 for p in game.projectiles))

                # + pierce Degree 3 -> pierce ramps to 2 (bolt count unchanged)
                game.player.skill_upgrades.append("arcanist_pierce")
                game.projectiles.clear()
                game.player.bolt_timer = 0.0
                game.player.mana = game.player.max_mana
                game.player_cast_bolt()
                self.assertEqual(len(game.projectiles), 3)
                self.assertTrue(all(p.pierce == 2 for p in game.projectiles))

                # + arc tyrant capstone -> homing
                game.player.skill_upgrades.append("arcanist_arc_tyrant")
                game.projectiles.clear()
                game.player.bolt_timer = 0.0
                game.player.mana = game.player.max_mana
                game.player_cast_bolt()
                self.assertTrue(all(p.homing > 0.0 for p in game.projectiles))
                self.assertAlmostEqual(game.projectiles[0].homing, 0.85, places=2)
            finally:
                pass

        # overload alone (prereqs bypassed via direct append) -> 3 bolts, pierce 1.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=2)
            try:
                game.player.skill_upgrades.append("arcanist_overload")
                game.projectiles.clear()
                game.player.mana = game.player.max_mana
                game.player.bolt_timer = 0.0
                game.player.facing_x = 1.0
                game.player.facing_y = 0.0
                game.player_cast_bolt()
                # Overload splits the bolt into a 3-shot fan and grants pierce 1
                # even without splinter (prereqs bypassed via direct append).
                self.assertEqual(len(game.projectiles), 3)
                self.assertTrue(all(p.pierce == 1 for p in game.projectiles))
            finally:
                pass

    # --- Warden Shield Bash: gradual cleave ramp (1/2/3 foes) -----------

    def test_warden_melee_single_target_without_bulwark(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            try:
                px, py = game.player.x, game.player.y
                game.player.facing_x = 1.0
                game.player.facing_y = 0.0
                near = _make_enemy(px + 0.6, py, hp=200)
                far = _make_enemy(px + 1.0, py, hp=200)
                game.enemies = [near, far]

                # Both enemies are inside the melee arc.
                arc = game.enemies_in_melee_arc()
                self.assertEqual(len(arc), 2)
                self.assertIn(near, arc)
                self.assertIn(far, arc)

                # Base Shield Bash only hits one foe.
                game.player.melee_timer = 0.0
                game.player.stamina = game.player.max_stamina
                game.player_melee_attack()
                self.assertLess(near.hp, 200)
                self.assertEqual(far.hp, 200)

                # Bulwark Degree 1 unlocks the cleave arc -> both foes hit.
                game.player.skill_upgrades.append("warden_bulwark")
                near.hp = 200
                far.hp = 200
                game.player.melee_timer = 0.0
                game.player.stamina = game.player.max_stamina
                game.player_melee_attack()
                self.assertLess(near.hp, 200)
                self.assertLess(far.hp, 200)

                # Aegis Degree 2 widens the cleave arc to 3 foes; add a third enemy.
                game.player.skill_upgrades.append("warden_aegis")
                third = _make_enemy(px + 1.4, py, hp=200)
                game.enemies = [near, far, third]
                near.hp = 200
                far.hp = 200
                third.hp = 200
                # The third enemy is within the extended reach (1.55 + 0.28).
                self.assertIn(third, game.enemies_in_melee_arc())
                game.player.melee_timer = 0.0
                game.player.stamina = game.player.max_stamina
                game.player_melee_attack()
                self.assertLess(near.hp, 200)
                self.assertLess(far.hp, 200)
                self.assertLess(third.hp, 200)
            finally:
                pass

    # --- Acolyte lifesteal gated behind Sanguine (melee + spell) -------

    def test_acolyte_lifesteal_gated_behind_sanguine(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=3)
            try:
                px, py = game.player.x, game.player.y
                enemy = _make_enemy(px + 0.8, py, hp=9999)
                game.enemies = [enemy]
                game.player.facing_x = 1.0
                game.player.facing_y = 0.0

                # Helper ramps one step per Blood degree; base leech is 0.
                self.assertEqual(game._acolyte_melee_leech(), 0)
                self.assertEqual(game._acolyte_spell_leech(), 0)

                # --- Melee: no sanguine -> no leech ---
                game.player.hp = game.player.max_hp - 20
                hp_before = game.player.hp
                game.player.melee_timer = 0.0
                game.player.stamina = game.player.max_stamina
                game.player_melee_attack()
                self.assertEqual(game.player.hp, hp_before)

                # --- Melee: with sanguine -> leech applies (degree 1 = 2) ---
                game.player.skill_upgrades.append("acolyte_sanguine")
                self.assertEqual(game._acolyte_melee_leech(), 2)
                game.player.hp = game.player.max_hp - 20
                hp_before = game.player.hp
                game.player.melee_timer = 0.0
                game.player.stamina = game.player.max_stamina
                game.player_melee_attack()
                self.assertGreater(game.player.hp, hp_before)

                # --- Nova: no sanguine -> no leech ---
                game.player.skill_upgrades.remove("acolyte_sanguine")
                self.assertEqual(game._acolyte_spell_leech(), 0)
                enemy2 = _make_enemy(px + 1.0, py, hp=9999)
                game.enemies = [enemy2]
                game.player.hp = game.player.max_hp - 20
                hp_before = game.player.hp
                game.player.class_skill_timer = 0.0
                game.player.mana = game.player.max_mana
                game.player_cast_nova()
                self.assertEqual(game.player.hp, hp_before)

                # --- Nova: with sanguine -> leech applies (degree 1 = 3) ---
                game.player.skill_upgrades.append("acolyte_sanguine")
                self.assertEqual(game._acolyte_spell_leech(), 3)
                enemy3 = _make_enemy(px + 1.0, py, hp=9999)
                game.enemies = [enemy3]
                game.player.hp = game.player.max_hp - 20
                hp_before = game.player.hp
                game.player.class_skill_timer = 0.0
                game.player.mana = game.player.max_mana
                game.player_cast_nova()
                self.assertGreater(game.player.hp, hp_before)

                # --- Blood Pact Degree 3 ramps melee leech to 4 (gradual degree step) ---
                game.player.skill_upgrades.append("acolyte_blood_pact")
                self.assertEqual(game._acolyte_melee_leech(), 4)
                self.assertEqual(game._acolyte_spell_leech(), 5)
            finally:
                pass


if __name__ == "__main__":
    unittest.main()
