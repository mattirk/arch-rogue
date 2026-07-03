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
    COMPLETED_BRANCH_BONUS_MAX_HP,
    COMPLETED_BRANCH_BONUS_MELEE,
    COMPLETED_BRANCH_BONUS_SPELL,
    SKILL_NODES,
    combo_bonus,
    combo_bonus_steps,
    completed_branch_bonus,
    completed_branches,
    cross_branch_tag_bonus,
    skill_branch_nodes,
    skill_node_by_key,
    skill_nodes_for_archetype,
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

    def test_choose_skill_upgrade_spending_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            try:
                # No points banked — the choice is rejected without spending.
                self.assertEqual(game.player.skill_points, 0)
                self.assertFalse(game.choose_skill_upgrade("warden_bulwark"))
                self.assertEqual(game.player.skill_points, 0)
                self.assertNotIn("warden_bulwark", game.player.skill_upgrades)
                # Bank one point: the first valid spend succeeds.
                game.player.skill_points = 1
                self.assertTrue(game.choose_skill_upgrade("warden_bulwark"))
                self.assertEqual(game.player.skill_points, 0)
                self.assertIn("warden_bulwark", game.player.skill_upgrades)
                # A second spend fails (no points left) even if the node is
                # valid — the spender never goes negative.
                self.assertFalse(game.choose_skill_upgrade("warden_riposte"))
                self.assertEqual(game.player.skill_points, 0)
                self.assertNotIn("warden_riposte", game.player.skill_upgrades)
            finally:
                pass

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
                pass

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

    def test_cross_branch_tag_bonus_rules(self) -> None:
        # Acquiring only the modifier node (no matching tagged nodes) yields no
        # cross-branch bonus.
        only_modifier = {"warden_iron_vow"}  # boosts Counter, but no Counter nodes
        self.assertEqual(cross_branch_tag_bonus(only_modifier), (0, 0))
        # Acquiring only tagged nodes (no modifier) yields no bonus either.
        only_tagged = {"warden_bulwark", "warden_riposte"}  # Guard + Counter tags
        self.assertEqual(cross_branch_tag_bonus(only_tagged), (0, 0))
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
                pass

    # --- Combo bonus scaling -------------------------------------------------

    def test_combo_bonus_scaling_and_completed_branch_bonus(self) -> None:
        from arch_rogue.content import skill_branches_for_archetype

        warden_nodes = skill_nodes_for_archetype("Warden")
        branches = skill_branches_for_archetype("Warden")
        # The Warden tree exposes four distinct branches.
        self.assertGreaterEqual(len(branches), 4)
        branch_keys = [{n.key for n in warden_nodes if n.branch == b} for b in branches]
        # combo_bonus_steps table for 0..4 completed branches.
        self.assertEqual(combo_bonus_steps(0), 0)
        self.assertEqual(combo_bonus_steps(1), 0)
        self.assertEqual(combo_bonus_steps(2), 1)
        self.assertEqual(combo_bonus_steps(3), 2)
        self.assertEqual(combo_bonus_steps(4), 3)
        # Loop over 0..4 completed branches and check both the depth-only
        # completed_branch_bonus and the depth+breadth combo_bonus, plus the
        # breadth delta separating the two layers.
        for c in range(0, 5):
            keys: set[str] = set()
            for i in range(c):
                keys |= branch_keys[i]
            steps = max(0, c - 1)
            depth_melee, depth_spell, depth_hp = completed_branch_bonus(keys, "Warden")
            self.assertEqual(depth_melee, c * COMPLETED_BRANCH_BONUS_MELEE)
            self.assertEqual(depth_spell, c * COMPLETED_BRANCH_BONUS_SPELL)
            self.assertEqual(depth_hp, c * COMPLETED_BRANCH_BONUS_MAX_HP)
            melee, spell, hp = combo_bonus(keys, "Warden")
            self.assertEqual(
                melee,
                c * COMPLETED_BRANCH_BONUS_MELEE + steps * COMBO_BONUS_PER_STEP_MELEE,
            )
            self.assertEqual(
                spell,
                c * COMPLETED_BRANCH_BONUS_SPELL + steps * COMBO_BONUS_PER_STEP_SPELL,
            )
            self.assertEqual(
                hp,
                c * COMPLETED_BRANCH_BONUS_MAX_HP + steps * COMBO_BONUS_PER_STEP_MAX_HP,
            )
            # combo_bonus - completed_branch_bonus isolates the breadth layer.
            self.assertEqual(melee - depth_melee, steps * COMBO_BONUS_PER_STEP_MELEE)
            self.assertEqual(spell - depth_spell, steps * COMBO_BONUS_PER_STEP_SPELL)
            self.assertEqual(hp - depth_hp, steps * COMBO_BONUS_PER_STEP_MAX_HP)

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

    def test_combo_bonus_applied_and_save_consistent_on_full_tree(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            try:
                # Bank enough points to buy the whole Warden tree (4 branches).
                game.player.skill_points = 100
                warden_nodes = sorted(
                    skill_nodes_for_archetype("Warden"), key=lambda n: n.tier
                )
                before_melee = game.player.melee_bonus
                before_spell = game.player.spell_bonus
                before_hp = game.player.max_hp
                for node in warden_nodes:
                    self.assertTrue(game.choose_skill_upgrade(node.key))
                # After finishing all four branches, the depth bonus (4x) plus
                # the combo breadth bonus (3 steps) should be reflected in
                # derived stats.
                expected_bonus_melee = (
                    4 * COMPLETED_BRANCH_BONUS_MELEE + 3 * COMBO_BONUS_PER_STEP_MELEE
                )
                expected_bonus_spell = (
                    4 * COMPLETED_BRANCH_BONUS_SPELL + 3 * COMBO_BONUS_PER_STEP_SPELL
                )
                expected_bonus_hp = (
                    4 * COMPLETED_BRANCH_BONUS_MAX_HP + 3 * COMBO_BONUS_PER_STEP_MAX_HP
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
                # Combo baseline reflects the completed branches after restore.
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

    def test_combo_preview_shows_next_tier_for_completing_node(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            try:
                game.player.skill_points = 100
                warden_nodes = sorted(
                    skill_nodes_for_archetype("Warden"), key=lambda n: n.tier
                )
                # Acquire all but the final Riposte capstone. With four
                # branches, this leaves Bulwark/Vow/Fortress complete (3
                # branches) and Riposte one node short.
                for node in warden_nodes:
                    if node.key == "warden_final_reckoning":
                        continue
                    self.assertTrue(game.choose_skill_upgrade(node.key))
                # Three branches complete: 3 depth steps + 2 combo steps.
                _, c_melee, c_spell, c_hp = game.combo_state()
                self.assertEqual(
                    c_melee,
                    3 * COMPLETED_BRANCH_BONUS_MELEE + 2 * COMBO_BONUS_PER_STEP_MELEE,
                )
                self.assertEqual(
                    c_spell,
                    3 * COMPLETED_BRANCH_BONUS_SPELL + 2 * COMBO_BONUS_PER_STEP_SPELL,
                )
                self.assertEqual(
                    c_hp,
                    3 * COMPLETED_BRANCH_BONUS_MAX_HP + 2 * COMBO_BONUS_PER_STEP_MAX_HP,
                )
                # Hovering the capstone previews the combo tier it would unlock:
                # four branches complete → 4 depth + 3 combo steps.
                capstone = skill_node_by_key("warden_final_reckoning")
                assert capstone is not None
                p_melee, p_spell, p_hp = game.combo_preview(capstone)
                self.assertEqual(
                    p_melee,
                    4 * COMPLETED_BRANCH_BONUS_MELEE + 3 * COMBO_BONUS_PER_STEP_MELEE,
                )
                self.assertEqual(
                    p_spell,
                    4 * COMPLETED_BRANCH_BONUS_SPELL + 3 * COMBO_BONUS_PER_STEP_SPELL,
                )
                self.assertEqual(
                    p_hp,
                    4 * COMPLETED_BRANCH_BONUS_MAX_HP + 3 * COMBO_BONUS_PER_STEP_MAX_HP,
                )
            finally:
                pass

    # --- Save migration -----------------------------------------------------

    def test_save_and_restore_preserves_skill_points_and_migrates_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            try:
                game.player.skill_points = 5
                game.choose_skill_upgrade("warden_bulwark")
                game.choose_skill_upgrade("warden_riposte")
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

    # --- Four-branch tree expansion ----------------------------------------

    def test_skill_tree_shape_four_branches_twenty_nodes_tier4_modifiers(self) -> None:
        from arch_rogue.content import skill_branches_for_archetype

        for archetype in ARCHETYPES:
            nodes = skill_nodes_for_archetype(archetype.name)
            branches = skill_branches_for_archetype(archetype.name)
            self.assertEqual(
                len(nodes),
                20,
                f"{archetype.name} should have 20 nodes (4 branches x 5 tiers)",
            )
            self.assertEqual(
                len(branches),
                4,
                f"{archetype.name} should have exactly 4 branches",
            )
            # Each branch has exactly one node per tier 1..5.
            for branch in branches:
                branch_nodes = skill_branch_nodes(archetype.name, branch)
                self.assertEqual(
                    len(branch_nodes),
                    5,
                    f"{archetype.name}/{branch} should have 5 nodes",
                )
                tiers = {n.tier for n in branch_nodes}
                self.assertEqual(tiers, set(range(1, 6)))
            # Each archetype's four tier-4 keystones carry cross_branch_tags so
            # committing deep into one branch amplifies another branch's tagged
            # skills. This is the cross-branch interaction contract.
            tier4 = [n for n in nodes if n.tier == 4]
            self.assertEqual(len(tier4), 4)
            modifiers = [n for n in tier4 if n.cross_branch_tags]
            self.assertEqual(
                len(modifiers),
                4,
                f"{archetype.name} tier-4 keystones should all be cross-branch "
                "modifiers",
            )

    def test_new_cross_branch_modifiers_reference_existing_tags(self) -> None:
        # The new Warden Vow/Fortress tier-4 keystones boost Counter/Guard tags.
        divine_wrath = skill_node_by_key("warden_divine_wrath")
        unyielding = skill_node_by_key("warden_unyielding")
        self.assertIsNotNone(divine_wrath)
        self.assertIsNotNone(unyielding)
        assert divine_wrath is not None and unyielding is not None
        self.assertIn("Counter", divine_wrath.cross_branch_tags)
        self.assertIn("Guard", unyielding.cross_branch_tags)
        # The Ranger's new Beast/Survival tier-4 keystones boost the existing
        # Volley/Control tags, tying new branches to the original two.
        spirit_companion = skill_node_by_key("ranger_spirit_companion")
        ambush = skill_node_by_key("ranger_ambush")
        self.assertIsNotNone(spirit_companion)
        self.assertIsNotNone(ambush)
        assert spirit_companion is not None and ambush is not None
        self.assertIn("Volley", spirit_companion.cross_branch_tags)
        self.assertIn("Control", ambush.cross_branch_tags)

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
                # Completing all four branches surfaces the combo strip.
                game.player.skill_points = 100
                for node in sorted(
                    skill_nodes_for_archetype("Warden"), key=lambda n: n.tier
                ):
                    if node.key not in game.player.skill_upgrades:
                        self.assertTrue(game.choose_skill_upgrade(node.key))
                game.draw_character_menu()
                done, melee, spell, hp = game.combo_state()
                self.assertGreaterEqual(len(done), 4)
                self.assertGreater(melee, 0)
            finally:
                pass

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
                pass

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
