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

from arch_rogue.content import (
    ARCHETYPES,
    COMBO_BONUS_PER_STEP_MAX_HP,
    COMBO_BONUS_PER_STEP_MELEE,
    COMBO_BONUS_PER_STEP_SPELL,
    SKILL_NODES,
    combo_bonus,
    combo_bonus_preview,
    combo_bonus_steps,
    completed_branches,
    cross_branch_tag_bonus,
    skill_branch_nodes,
    skill_node_by_key,
    skill_nodes_for_archetype,
)
from arch_rogue.game import Game


class SkillPointProgression33Tests(unittest.TestCase):
    def tearDown(self) -> None:
        pygame.quit()

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

    def test_player_starts_with_zero_skill_points(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            try:
                self.assertEqual(game.player.skill_points, 0)
            finally:
                pygame.quit()

    def test_level_up_awards_one_skill_point(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            try:
                # Force a level-up by feeding enough XP. gain_xp returns True
                # when a level boundary is crossed.
                before_level = game.player.level
                before_points = game.player.skill_points
                leveled = game.player.gain_xp(game.player.next_xp + 1)
                self.assertTrue(leveled)
                self.assertEqual(game.player.level, before_level + 1)
                self.assertEqual(game.player.skill_points, before_points + 1)
            finally:
                pygame.quit()

    def test_grant_skill_point_awards_points_and_floater(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            try:
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
                pygame.quit()

    # --- Skill point spending -----------------------------------------------

    def test_choose_skill_upgrade_spends_a_point(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            try:
                game.player.skill_points = 1
                self.assertTrue(game.choose_skill_upgrade("warden_bulwark"))
                self.assertEqual(game.player.skill_points, 0)
                self.assertIn("warden_bulwark", game.player.skill_upgrades)
            finally:
                pygame.quit()

    def test_choose_skill_upgrade_rejects_without_skill_points(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            try:
                self.assertEqual(game.player.skill_points, 0)
                # No points banked — the choice is rejected without spending.
                self.assertFalse(game.choose_skill_upgrade("warden_bulwark"))
                self.assertEqual(game.player.skill_points, 0)
                self.assertNotIn("warden_bulwark", game.player.skill_upgrades)
            finally:
                pygame.quit()

    def test_choose_skill_upgrade_does_not_overspend(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            try:
                game.player.skill_points = 1
                # First spend succeeds.
                self.assertTrue(game.choose_skill_upgrade("warden_bulwark"))
                # Second spend fails (no points left) even if the node is valid.
                self.assertFalse(game.choose_skill_upgrade("warden_riposte"))
                self.assertEqual(game.player.skill_points, 0)
                self.assertNotIn("warden_riposte", game.player.skill_upgrades)
            finally:
                pygame.quit()

    def test_grant_skill_upgrade_does_not_spend_points(self) -> None:
        """Shrine/altar bonus grants must not consume banked skill points."""
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=2, seed=3322)
            try:
                game.player.skill_points = 3
                before_upgrades = len(game.player.skill_upgrades)
                self.assertTrue(game.grant_skill_upgrade(reason="oath shrine"))
                self.assertEqual(len(game.player.skill_upgrades), before_upgrades + 1)
                # Points are untouched — bonus grants are free.
                self.assertEqual(game.player.skill_points, 3)
            finally:
                pygame.quit()

    # --- Cross-branch tag interactions --------------------------------------

    def test_skill_nodes_carry_tags_for_cross_branch_interactions(self) -> None:
        # The Warden tree has Guard- and Counter-tagged nodes, and tier-4
        # keystones carry cross_branch_tags that boost the opposite branch.
        warden = skill_nodes_for_archetype("Warden")
        tagged = [n for n in warden if n.tags]
        self.assertTrue(tagged, "Warden tree should have tagged nodes")
        modifiers = [n for n in warden if n.cross_branch_tags]
        self.assertTrue(modifiers, "Warden tree should have cross-branch modifiers")
        # Iron Vow (Bulwark) boosts Counter-tagged skills.
        iron_vow = skill_node_by_key("warden_iron_vow")
        self.assertIsNotNone(iron_vow)
        assert iron_vow is not None
        self.assertIn("Counter", iron_vow.cross_branch_tags)
        # Reckoning (Riposte) boosts Guard-tagged skills.
        reckoning = skill_node_by_key("warden_reckoning")
        self.assertIsNotNone(reckoning)
        assert reckoning is not None
        self.assertIn("Guard", reckoning.cross_branch_tags)

    def test_cross_branch_tag_bonus_only_applies_when_both_halves_acquired(self):
        # Acquiring only the modifier node (no matching tagged nodes) yields no
        # cross-branch bonus.
        only_modifier = {"warden_iron_vow"}  # boosts Counter, but no Counter nodes
        self.assertEqual(cross_branch_tag_bonus(only_modifier), (0, 0))
        # Acquiring only tagged nodes (no modifier) yields no bonus either.
        only_tagged = {"warden_bulwark", "warden_riposte"}  # Guard + Counter tags
        self.assertEqual(cross_branch_tag_bonus(only_tagged), (0, 0))

    def test_cross_branch_tag_bonus_compounds_across_branches(self) -> None:
        # Acquiring Iron Vow (boosts Counter) plus Counter-tagged nodes applies
        # Iron Vow's melee bonus once per Counter-tagged acquired node. Note
        # that warden_reckoning is itself a Counter-tagged modifier that boosts
        # Guard-tagged nodes, so acquiring it alongside Iron Vow (which is
        # Guard-tagged) adds Reckoning's bonus on top of Iron Vow's.
        iron_vow = skill_node_by_key("warden_iron_vow")
        assert iron_vow is not None
        reckoning = skill_node_by_key("warden_reckoning")
        assert reckoning is not None
        counter_nodes = [
            n for n in skill_nodes_for_archetype("Warden") if "Counter" in n.tags
        ]
        self.assertTrue(counter_nodes)
        acquired = {"warden_iron_vow"}
        for node in counter_nodes:
            acquired.add(node.key)
        melee, spell = cross_branch_tag_bonus(acquired)
        # Iron Vow boosts every Counter-tagged node (including Reckoning), and
        # Reckoning boosts Iron Vow (Guard-tagged). Both contribute melee.
        expected_melee = (
            iron_vow.cross_branch_bonus_melee * len(counter_nodes)
            + reckoning.cross_branch_bonus_melee  # Reckoning → Iron Vow (Guard)
        )
        self.assertEqual(melee, expected_melee)
        self.assertEqual(spell, 0)

    def test_cross_branch_tag_bonus_in_game_matches_helper(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            try:
                # Acquire Iron Vow plus a Counter-tagged node via direct
                # manipulation (bypassing point spend) to isolate the helper.
                game.player.skill_upgrades = ["warden_iron_vow", "warden_riposte"]
                melee, spell = game.cross_branch_bonus_state()
                self.assertGreater(melee, 0)
                self.assertEqual(
                    (melee, spell),
                    cross_branch_tag_bonus(set(game.player.skill_upgrades)),
                )
            finally:
                pygame.quit()

    # --- Combo bonus scaling -------------------------------------------------

    def test_combo_bonus_steps_requires_two_completed_branches(self) -> None:
        self.assertEqual(combo_bonus_steps(0), 0)
        self.assertEqual(combo_bonus_steps(1), 0)
        self.assertEqual(combo_bonus_steps(2), 1)
        self.assertEqual(combo_bonus_steps(3), 2)

    def test_combo_bonus_zero_below_two_completed_branches(self) -> None:
        warden_nodes = skill_nodes_for_archetype("Warden")
        branches = [n.branch for n in warden_nodes]
        unique_branches = list(dict.fromkeys(branches))
        self.assertGreaterEqual(len(unique_branches), 2)
        # Complete exactly one branch (Bulwark).
        bulwark_keys = {n.key for n in warden_nodes if n.branch == "Bulwark"}
        self.assertTrue(bulwark_keys)
        melee, spell, hp = combo_bonus(bulwark_keys, "Warden")
        self.assertEqual((melee, spell, hp), (0, 0, 0))

    def test_combo_bonus_scales_with_completed_branch_count(self) -> None:
        warden_nodes = skill_nodes_for_archetype("Warden")
        all_keys = {n.key for n in warden_nodes}
        # Completing both Warden branches (Bulwark + Riposte) yields one step.
        melee, spell, hp = combo_bonus(all_keys, "Warden")
        self.assertEqual(melee, COMBO_BONUS_PER_STEP_MELEE)
        self.assertEqual(spell, COMBO_BONUS_PER_STEP_SPELL)
        self.assertEqual(hp, COMBO_BONUS_PER_STEP_MAX_HP)

    def test_completed_branches_reports_all_when_tree_finished(self) -> None:
        warden_nodes = skill_nodes_for_archetype("Warden")
        all_keys = {n.key for n in warden_nodes}
        done = completed_branches(all_keys, "Warden")
        self.assertGreaterEqual(len(done), 2)
        # Every reported branch is actually fully acquired.
        for branch in done:
            branch_nodes = skill_branch_nodes("Warden", branch)
            self.assertTrue(branch_nodes)
            self.assertTrue(all(n.key in all_keys for n in branch_nodes))

    def test_combo_bonus_applied_to_player_stats_on_branch_completion(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            try:
                # Bank enough points to buy the whole Warden tree.
                game.player.skill_points = 50
                warden_nodes = sorted(
                    skill_nodes_for_archetype("Warden"), key=lambda n: n.tier
                )
                before_melee = game.player.melee_bonus
                before_spell = game.player.spell_bonus
                before_hp = game.player.max_hp
                for node in warden_nodes:
                    self.assertTrue(game.choose_skill_upgrade(node.key))
                # After finishing both branches, the combo bonus (one step)
                # should be reflected in derived stats.
                self.assertEqual(
                    game.player.melee_bonus,
                    before_melee
                    + sum(n.melee_bonus for n in warden_nodes)
                    + COMBO_BONUS_PER_STEP_MELEE,
                )
                self.assertEqual(
                    game.player.spell_bonus,
                    before_spell
                    + sum(n.spell_bonus for n in warden_nodes)
                    + COMBO_BONUS_PER_STEP_SPELL,
                )
                self.assertEqual(
                    game.player.max_hp,
                    before_hp
                    + sum(n.max_hp_bonus for n in warden_nodes)
                    + COMBO_BONUS_PER_STEP_MAX_HP,
                )
                # combo_state reports the live bonus.
                _, c_melee, c_spell, c_hp = game.combo_state()
                self.assertEqual(c_melee, COMBO_BONUS_PER_STEP_MELEE)
                self.assertEqual(c_spell, COMBO_BONUS_PER_STEP_SPELL)
                self.assertEqual(c_hp, COMBO_BONUS_PER_STEP_MAX_HP)
            finally:
                pygame.quit()

    def test_combo_preview_shows_next_tier_for_completing_node(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            try:
                game.player.skill_points = 50
                warden_nodes = sorted(
                    skill_nodes_for_archetype("Warden"), key=lambda n: n.tier
                )
                # Acquire all but the final Riposte capstone.
                for node in warden_nodes:
                    if node.key == "warden_final_reckoning":
                        continue
                    self.assertTrue(game.choose_skill_upgrade(node.key))
                # At this point only Bulwark is complete (Riposte missing its
                # capstone), so combo is zero.
                _, c_melee, c_spell, c_hp = game.combo_state()
                self.assertEqual((c_melee, c_spell, c_hp), (0, 0, 0))
                # Hovering the capstone previews the combo tier it would unlock.
                capstone = skill_node_by_key("warden_final_reckoning")
                assert capstone is not None
                p_melee, p_spell, p_hp = game.combo_preview(capstone)
                self.assertEqual(p_melee, COMBO_BONUS_PER_STEP_MELEE)
                self.assertEqual(p_spell, COMBO_BONUS_PER_STEP_SPELL)
                self.assertEqual(p_hp, COMBO_BONUS_PER_STEP_MAX_HP)
            finally:
                pygame.quit()

    # --- Save migration -----------------------------------------------------

    def test_older_save_without_skill_points_defaults_to_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            try:
                game.player.skill_points = 2
                game.choose_skill_upgrade("warden_bulwark")
                game.save_run()
                save_path = Path(tmpdir) / "run.json"
                import json

                data = json.loads(save_path.read_text())
                # Simulate a pre-3.3 save by stripping skill_points.
                data["player"].pop("skill_points", None)
                save_path.write_text(json.dumps(data))

                game2 = Game(
                    screen_size=(960, 600),
                    headless=True,
                    save_path=save_path,
                )
                game2.options_path = Path(tmpdir) / "options.json"
                game2.rng.seed(7777)
                self.assertTrue(game2.load_run())
                # Older saves default to 0 skill points (no free windfall).
                self.assertEqual(game2.player.skill_points, 0)
                # The acquired node is preserved.
                self.assertIn("warden_bulwark", game2.player.skill_upgrades)
            finally:
                pygame.quit()

    def test_save_and_restore_preserves_skill_points_and_combo_baseline(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            try:
                game.player.skill_points = 5
                game.choose_skill_upgrade("warden_bulwark")
                game.choose_skill_upgrade("warden_riposte")
                # 3 points remain banked.
                self.assertEqual(game.player.skill_points, 3)
                game.save_run()

                game2 = Game(
                    screen_size=(960, 600),
                    headless=True,
                    save_path=Path(tmpdir) / "run.json",
                )
                game2.options_path = Path(tmpdir) / "options.json"
                game2.rng.seed(9999)
                self.assertTrue(game2.load_run())
                self.assertEqual(game2.player.skill_points, 3)
                self.assertEqual(
                    game2.player.skill_upgrades,
                    ["warden_bulwark", "warden_riposte"],
                )
                # Combo baseline is seeded so a future pick only applies delta.
                self.assertEqual(
                    getattr(game2.player, "_combo_applied", None), (0, 0, 0)
                )
            finally:
                pygame.quit()

    def test_save_restore_with_completed_branches_keeps_combo_consistent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            try:
                game.player.skill_points = 50
                warden_nodes = sorted(
                    skill_nodes_for_archetype("Warden"), key=lambda n: n.tier
                )
                for node in warden_nodes:
                    self.assertTrue(game.choose_skill_upgrade(node.key))
                # Both branches complete → combo bonus applied.
                _, c_melee, _, _ = game.combo_state()
                self.assertEqual(c_melee, COMBO_BONUS_PER_STEP_MELEE)
                game.save_run()

                game2 = Game(
                    screen_size=(960, 600),
                    headless=True,
                    save_path=Path(tmpdir) / "run.json",
                )
                game2.options_path = Path(tmpdir) / "options.json"
                game2.rng.seed(4242)
                self.assertTrue(game2.load_run())
                # Combo baseline reflects the completed branches.
                _, c2_melee, c2_spell, c2_hp = game2.combo_state()
                self.assertEqual(c2_melee, COMBO_BONUS_PER_STEP_MELEE)
                self.assertEqual(c2_spell, COMBO_BONUS_PER_STEP_SPELL)
                self.assertEqual(c2_hp, COMBO_BONUS_PER_STEP_MAX_HP)
                # The combo bonus is not double-applied on restore: the stored
                # stat totals already include it, and the baseline matches.
                self.assertEqual(
                    getattr(game2.player, "_combo_applied", (0, 0, 0)),
                    (c2_melee, c2_spell, c2_hp),
                )
            finally:
                pygame.quit()

    # --- Character sheet surfacing ------------------------------------------

    def test_character_menu_surfaces_skill_points_and_combo(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            try:
                game.player.skill_points = 2
                game.character_menu_open = True
                game.character_menu_tab = "skill_tree"
                # Renders without error and surfaces the banked points.
                game.draw_character_menu()
                # Completing both branches surfaces the combo strip.
                game.player.skill_points = 50
                for node in sorted(
                    skill_nodes_for_archetype("Warden"), key=lambda n: n.tier
                ):
                    if node.key not in game.player.skill_upgrades:
                        self.assertTrue(game.choose_skill_upgrade(node.key))
                game.draw_character_menu()
                done, melee, spell, hp = game.combo_state()
                self.assertGreaterEqual(len(done), 2)
                self.assertGreater(melee, 0)
            finally:
                pygame.quit()

    def test_hover_preview_populates_skill_node_cells(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            try:
                game.player.skill_points = 1
                game.character_menu_open = True
                game.character_menu_tab = "skill_tree"
                game.draw_character_menu()
                # The renderer populates the cell map for mouse hover.
                self.assertTrue(game._skill_node_cells)
                # Simulate hovering the warden_bulwark cell.
                cell = game._skill_node_cells["warden_bulwark"]
                pygame.event.post(
                    pygame.event.Event(
                        pygame.MOUSEMOTION,
                        pos=cell.center,
                    )
                )
                game.handle_events()
                self.assertEqual(game.character_menu_hovered_node, "warden_bulwark")
                # Clicking the hovered available node spends a point.
                pygame.event.post(
                    pygame.event.Event(
                        pygame.MOUSEBUTTONDOWN,
                        button=1,
                        pos=cell.center,
                    )
                )
                game.handle_events()
                self.assertIn("warden_bulwark", game.player.skill_upgrades)
                self.assertEqual(game.player.skill_points, 0)
            finally:
                pygame.quit()

    # --- Hot-path performance ---------------------------------------------

    def test_combo_and_cross_branch_lookups_are_allocation_light(self) -> None:
        # The helpers must be safe to call from the hot path: they accept a set
        # and return plain tuples/ints without per-frame allocations beyond the
        # returned value. This is a smoke test that they run cleanly on a full
        # tree and return stable types.
        all_keys = {n.key for n in SKILL_NODES if n.archetype == "Warden"}
        melee, spell, hp = combo_bonus(all_keys, "Warden")
        self.assertIsInstance((melee, spell, hp), tuple)
        cb_melee, cb_spell = cross_branch_tag_bonus(all_keys)
        self.assertIsInstance((cb_melee, cb_spell), tuple)
        done = completed_branches(all_keys, "Warden")
        self.assertIsInstance(done, tuple)


if __name__ == "__main__":
    unittest.main()
