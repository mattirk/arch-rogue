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

from arch_rogue.content import (
    ARCHETYPES,
    COMBO_BONUS_PER_STEP_MAX_HP,
    COMBO_BONUS_PER_STEP_MELEE,
    COMBO_BONUS_PER_STEP_SPELL,
    COMPLETED_PATH_BONUS_MAX_HP,
    COMPLETED_PATH_BONUS_MELEE,
    COMPLETED_PATH_BONUS_SPELL,
    combo_bonus,
    combo_bonus_steps,
    completed_path_bonus,
    disciplines_for_archetype,
)
from arch_rogue.game import Game


class SkillPointProgression33Tests(unittest.TestCase):
    def tearDown(self) -> None:
        pass

    def make_game(
        self, tmpdir: str, archetype_index: int = 0, seed: int = 3301
    ) -> Game:
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

    # --- Skill point earning ------------------------------------------------

    def test_skill_point_earning(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            try:
                # Players start a run with zero banked skill points.
                self.assertEqual(game.player.skill_points, 0)
                # Force a level-up by feeding enough XP. gain_xp returns True
                # when a level boundary is crossed and awards exactly one point.
                before_level = game.player.level
                before_points = game.player.skill_points
                leveled = game.player.gain_xp(game.player.next_xp + 1)
                self.assertTrue(leveled)
                self.assertEqual(game.player.level, before_level + 1)
                self.assertEqual(game.player.skill_points, before_points + 1)
                # Explicit grants award points and surface a floater.
                before = game.player.skill_points
                before_floaters = len(game.floaters)
                game.grant_skill_point(amount=2, reason="test reward")
                self.assertEqual(game.player.skill_points, before + 2)
                self.assertEqual(len(game.floaters), before_floaters + 1)
                # Zero/negative grants are no-ops.
                game.grant_skill_point(amount=0)
                self.assertEqual(game.player.skill_points, before + 2)
                game.grant_skill_point(amount=-3)
                self.assertEqual(game.player.skill_points, before + 2)
            finally:
                pass

    # --- Skill point spending -----------------------------------------------

    def test_choose_discipline_spending_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            try:
                # No points banked — the choice is rejected without spending.
                self.assertEqual(game.player.skill_points, 0)
                self.assertFalse(game.choose_discipline("warden_bulwark"))
                self.assertEqual(game.player.skill_points, 0)
                self.assertNotIn("warden_bulwark", game.player.skill_upgrades)
                # Bank one point: the first valid spend succeeds.
                game.player.skill_points = 1
                self.assertTrue(game.choose_discipline("warden_bulwark"))
                self.assertEqual(game.player.skill_points, 0)
                self.assertIn("warden_bulwark", game.player.skill_upgrades)
                # A second spend fails (no points left) even if the node is
                # valid — the spender never goes negative.
                self.assertFalse(game.choose_discipline("warden_riposte"))
                self.assertEqual(game.player.skill_points, 0)
                self.assertNotIn("warden_riposte", game.player.skill_upgrades)
            finally:
                pass

    # --- Combo bonus scaling -------------------------------------------------

    def test_combo_bonus_scaling_and_completed_path_bonus(self) -> None:
        from arch_rogue.content import discipline_paths_for_archetype

        warden_nodes = disciplines_for_archetype("Warden")
        paths = discipline_paths_for_archetype("Warden")
        # The Warden discipline tree exposes four distinct paths.
        self.assertGreaterEqual(len(paths), 4)
        branch_keys = [{n.key for n in warden_nodes if n.path == b} for b in paths]
        # combo_bonus_steps table for 0..4 completed paths.
        self.assertEqual(combo_bonus_steps(0), 0)
        self.assertEqual(combo_bonus_steps(1), 0)
        self.assertEqual(combo_bonus_steps(2), 1)
        self.assertEqual(combo_bonus_steps(3), 2)
        self.assertEqual(combo_bonus_steps(4), 3)
        # Loop over 0..4 completed paths and check both the depth-only
        # completed_path_bonus and the depth+breadth combo_bonus, plus the
        # breadth delta separating the two layers.
        for c in range(0, 5):
            keys: set[str] = set()
            for i in range(c):
                keys |= branch_keys[i]
            steps = max(0, c - 1)
            depth_melee, depth_spell, depth_hp = completed_path_bonus(keys, "Warden")
            self.assertEqual(depth_melee, c * COMPLETED_PATH_BONUS_MELEE)
            self.assertEqual(depth_spell, c * COMPLETED_PATH_BONUS_SPELL)
            self.assertEqual(depth_hp, c * COMPLETED_PATH_BONUS_MAX_HP)
            melee, spell, hp = combo_bonus(keys, "Warden")
            self.assertEqual(
                melee,
                c * COMPLETED_PATH_BONUS_MELEE + steps * COMBO_BONUS_PER_STEP_MELEE,
            )
            self.assertEqual(
                spell,
                c * COMPLETED_PATH_BONUS_SPELL + steps * COMBO_BONUS_PER_STEP_SPELL,
            )
            self.assertEqual(
                hp,
                c * COMPLETED_PATH_BONUS_MAX_HP + steps * COMBO_BONUS_PER_STEP_MAX_HP,
            )
            # combo_bonus - completed_path_bonus isolates the breadth layer.
            self.assertEqual(melee - depth_melee, steps * COMBO_BONUS_PER_STEP_MELEE)
            self.assertEqual(spell - depth_spell, steps * COMBO_BONUS_PER_STEP_SPELL)
            self.assertEqual(hp - depth_hp, steps * COMBO_BONUS_PER_STEP_MAX_HP)

    def test_combo_bonus_applied_and_save_consistent_on_full_tree(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            try:
                # Bank enough points to buy two Warden paths (Milestone 3.7 limit).
                game.player.skill_points = 100
                warden_nodes = sorted(
                    disciplines_for_archetype("Warden"), key=lambda n: n.degree
                )
                # Milestone 3.7: commit to at most two paths (Bulwark + Riposte).
                warden_nodes = [
                    n for n in warden_nodes if n.path in ("Bulwark", "Riposte")
                ]
                before_melee = game.player.melee_bonus
                before_spell = game.player.spell_bonus
                before_hp = game.player.max_hp
                for node in warden_nodes:
                    self.assertTrue(game.choose_discipline(node.key))
                # Two completed paths: 2 depth steps plus 1 combo step.
                expected_bonus_melee = (
                    2 * COMPLETED_PATH_BONUS_MELEE + 1 * COMBO_BONUS_PER_STEP_MELEE
                )
                expected_bonus_spell = (
                    2 * COMPLETED_PATH_BONUS_SPELL + 1 * COMBO_BONUS_PER_STEP_SPELL
                )
                expected_bonus_hp = (
                    2 * COMPLETED_PATH_BONUS_MAX_HP + 1 * COMBO_BONUS_PER_STEP_MAX_HP
                )
                self.assertEqual(
                    game.player.melee_bonus,
                    before_melee
                    + sum(n.melee_bonus for n in warden_nodes)
                    + expected_bonus_melee,
                )
                self.assertEqual(
                    game.player.spell_bonus,
                    before_spell
                    + sum(n.spell_bonus for n in warden_nodes)
                    + expected_bonus_spell,
                )
                self.assertEqual(
                    game.player.max_hp,
                    before_hp
                    + sum(n.max_hp_bonus for n in warden_nodes)
                    + expected_bonus_hp,
                )
                # combo_state reports the live combined bonus.
                _, c_melee, c_spell, c_hp = game.combo_state()
                self.assertEqual(c_melee, expected_bonus_melee)
                self.assertEqual(c_spell, expected_bonus_spell)
                self.assertEqual(c_hp, expected_bonus_hp)
                game.save_run()

                game2 = Game(
                    screen_size=(960, 600),
                    headless=True,
                    save_path=Path(tmpdir) / "run.json",
                )
                game2.options_path = Path(tmpdir) / "options.json"
                game2.rng.seed(4242)
                self.assertTrue(game2.load_run())
                # Combo baseline reflects the completed paths after restore.
                _, c2_melee, c2_spell, c2_hp = game2.combo_state()
                self.assertEqual(c2_melee, expected_bonus_melee)
                self.assertEqual(c2_spell, expected_bonus_spell)
                self.assertEqual(c2_hp, expected_bonus_hp)
                # The combo bonus is not double-applied on restore: the stored
                # stat totals already include it, and the baseline matches.
                self.assertEqual(
                    getattr(game2.player, "_combo_applied", (0, 0, 0)),
                    (c2_melee, c2_spell, c2_hp),
                )
            finally:
                pass

    # --- Save migration -----------------------------------------------------

    def test_save_and_restore_preserves_skill_points_and_migrates_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            try:
                game.player.skill_points = 5
                game.choose_discipline("warden_bulwark")
                game.choose_discipline("warden_riposte")
                # 3 points remain banked.
                self.assertEqual(game.player.skill_points, 3)
                save_path = Path(tmpdir) / "run.json"
                game.save_run()

                # Case 1: a normal restore preserves banked points, acquired
                # upgrades, and the combo baseline (seeded so future picks only
                # apply a delta).
                game2 = Game(
                    screen_size=(960, 600),
                    headless=True,
                    save_path=save_path,
                )
                game2.options_path = Path(tmpdir) / "options.json"
                game2.rng.seed(9999)
                self.assertTrue(game2.load_run())
                self.assertEqual(game2.player.skill_points, 3)
                self.assertEqual(
                    game2.player.skill_upgrades,
                    ["warden_bulwark", "warden_riposte"],
                )
                self.assertEqual(
                    getattr(game2.player, "_combo_applied", None), (0, 0, 0)
                )

                # Case 2: a pre-3.3 save stripped of skill_points migrates to
                # zero (no free windfall) while preserving acquired nodes.
                data = json.loads(save_path.read_text())
                data["player"].pop("skill_points", None)
                save_path.write_text(json.dumps(data))

                game3 = Game(
                    screen_size=(960, 600),
                    headless=True,
                    save_path=save_path,
                )
                game3.options_path = Path(tmpdir) / "options.json"
                game3.rng.seed(7777)
                self.assertTrue(game3.load_run())
                self.assertEqual(game3.player.skill_points, 0)
                self.assertIn("warden_bulwark", game3.player.skill_upgrades)
            finally:
                pass
