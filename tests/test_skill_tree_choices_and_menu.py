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
    SKILL_NODES,
    SKILL_UPGRADES,
    migrate_skill_keys,
    skill_branches_for_archetype,
    skill_node_by_key,
    skill_nodes_for_archetype,
    skill_tree_max_tier,
)
from arch_rogue.game import Game


class SkillTree32Tests(unittest.TestCase):
    def tearDown(self) -> None:
        pass

    def make_game(
        self, tmpdir: str, archetype_index: int = 0, seed: int = 3201
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

    # --- Content table shape -------------------------------------------------

    def test_skill_tree_content_table_shape(self) -> None:
        # Every archetype has a 5-tier, >=2-branch tree with sane prerequisites.
        for archetype in ARCHETYPES:
            nodes = skill_nodes_for_archetype(archetype.name)
            self.assertGreaterEqual(
                len(nodes), 10, f"{archetype.name} should have >=10 nodes"
            )
            self.assertEqual(
                {node.tier for node in nodes},
                set(range(1, 6)),
                f"{archetype.name} must cover tiers 1..5",
            )
            self.assertEqual(skill_tree_max_tier(archetype.name), 5)
            branches = skill_branches_for_archetype(archetype.name)
            self.assertGreaterEqual(
                len(branches), 2, f"{archetype.name} needs >=2 branches"
            )
            # Tier 1 nodes are open (no prerequisites); higher tiers require
            # an earlier-tier prerequisite of the same branch.
            for node in nodes:
                if node.tier == 1:
                    self.assertEqual(
                        node.prerequisites,
                        (),
                        f"{node.key} tier-1 nodes must be open",
                    )
                else:
                    self.assertTrue(
                        node.prerequisites,
                        f"{node.key} tier-{node.tier} must require something",
                    )
                    for prereq_key in node.prerequisites:
                        prereq = skill_node_by_key(prereq_key)
                        self.assertIsNotNone(prereq)
                        assert prereq is not None
                        self.assertEqual(prereq.archetype, archetype.name)
                        self.assertLess(prereq.tier, node.tier)

        # SKILL_UPGRADES is derived 1:1 from SKILL_NODES and every key resolves.
        node_keys = {node.key for node in SKILL_NODES}
        upgrade_keys = {upgrade.key for upgrade in SKILL_UPGRADES}
        self.assertEqual(node_keys, upgrade_keys)
        for node in SKILL_NODES:
            self.assertIs(skill_node_by_key(node.key), node)

    # --- Combat grant logic --------------------------------------------------

    def test_skill_choice_prerequisites_and_rejection_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)  # Warden
            try:
                # Milestone 3.3: choosing nodes now spends skill points, so
                # bank enough points to exercise the tree.
                game.player.skill_points = 10
                # Initially only tier-1 nodes are available.
                available = game.available_skill_choices()
                self.assertTrue(available)
                self.assertTrue(all(node.tier == 1 for node in available))

                # Rogue node cannot be chosen by a Warden.
                self.assertFalse(game.choose_skill_upgrade("rogue_precision"))
                self.assertNotIn("rogue_precision", game.player.skill_upgrades)

                # Acquire a tier-1 Bulwark node; its tier-2 child unlocks.
                self.assertTrue(game.choose_skill_upgrade("warden_bulwark"))
                # Duplicate acquisition is rejected.
                self.assertFalse(game.choose_skill_upgrade("warden_bulwark"))

                available = game.available_skill_choices()
                keys = {node.key for node in available}
                self.assertIn("warden_aegis", keys)
                # The other tier-1 node is still available.
                self.assertIn("warden_riposte", keys)
                # Tier-2 Riposte child stays locked (its parent unchosen).
                self.assertNotIn("warden_counter", keys)

                # Trying to skip ahead fails.
                self.assertFalse(game.choose_skill_upgrade("warden_bulwark_ward"))
                self.assertFalse(game.choose_skill_upgrade("warden_iron_vow"))
            finally:
                pass

    def test_grant_skill_upgrade_picks_available_and_fails_when_exhausted(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=2, seed=3222)  # Arcanist
            try:
                # Grant several upgrades; each must be a currently-available node.
                for _ in range(4):
                    before = set(game.player.skill_upgrades)
                    self.assertTrue(game.grant_skill_upgrade(reason="test"))
                    added = set(game.player.skill_upgrades) - before
                    self.assertEqual(len(added), 1)
                    new_key = next(iter(added))
                    node = skill_node_by_key(new_key)
                    self.assertIsNotNone(node)
                    assert node is not None
                    self.assertEqual(node.archetype, "Arcanist")
                    # The granted node must have had its prerequisites met.
                    for prereq in node.prerequisites:
                        self.assertIn(prereq, game.player.skill_upgrades)

                # Restart as Warden, force-acquire every node, then confirm
                # grant returns False once the tree is exhausted.
                game.rng.seed(3233)
                game.restart(ARCHETYPES[0])
                if game.story_intro_pending:
                    self.assertTrue(game.choose_story_relic_path(0))
                game.active_cutscene = None
                warden_nodes = skill_nodes_for_archetype("Warden")
                # Acquire in tier order so prerequisites hold.
                for node in sorted(warden_nodes, key=lambda n: n.tier):
                    game.player.skill_upgrades.append(node.key)
                self.assertFalse(game.grant_skill_upgrade(reason="test"))
            finally:
                pass

    def test_choose_skill_upgrade_applies_stat_bonuses(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            try:
                game.player.skill_points = 1
                node = skill_node_by_key("warden_bulwark")
                assert node is not None
                before_hp = game.player.max_hp
                before_armor = game.player.armor_bonus
                game.choose_skill_upgrade("warden_bulwark")
                self.assertEqual(game.player.max_hp, before_hp + node.max_hp_bonus)
                self.assertEqual(
                    game.player.armor_bonus, before_armor + node.armor_bonus
                )
            finally:
                pass

    # --- Save compatibility ---------------------------------------------------

    def test_migrate_skill_keys_drops_unknown_and_dedupes(self) -> None:
        self.assertEqual(migrate_skill_keys(["warden_bulwark"]), ["warden_bulwark"])
        self.assertEqual(migrate_skill_keys(["does_not_exist"]), [])
        self.assertEqual(
            migrate_skill_keys(["warden_bulwark", "warden_bulwark"]),
            ["warden_bulwark"],
        )

    def test_save_restore_preserves_progress_and_drops_unknown_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=1, seed=3241)  # Rogue
            try:
                game.player.skill_points = 2
                game.choose_skill_upgrade("rogue_precision")
                game.choose_skill_upgrade("rogue_venom")
                self.assertEqual(
                    game.player.skill_upgrades,
                    ["rogue_precision", "rogue_venom"],
                )
                # Skill points are spent on save.
                self.assertEqual(game.player.skill_points, 0)
                game.save_run()

                game2 = Game(
                    screen_size=(960, 600),
                    headless=True,
                    save_path=Path(tmpdir) / "run.json",
                )
                game2.options_path = Path(tmpdir) / "options.json"
                game2.rng.seed(9999)
                self.assertTrue(game2.load_run())
                self.assertEqual(
                    game2.player.skill_upgrades,
                    ["rogue_precision", "rogue_venom"],
                )
                # Tree state is consistent after restore.
                self.assertEqual(
                    game2.skill_node_state(skill_node_by_key("rogue_precision")),
                    "chosen",
                )
                self.assertEqual(
                    game2.skill_node_state(skill_node_by_key("rogue_executioner")),
                    "available",
                )

                # Inject an obsolete/unknown key into the restored run, re-save,
                # and reload to confirm migration drops it without breaking play.
                game2.player.skill_upgrades.append("obsolete_node_key")
                game2.save_run()

                game3 = Game(
                    screen_size=(960, 600),
                    headless=True,
                    save_path=Path(tmpdir) / "run.json",
                )
                game3.options_path = Path(tmpdir) / "options.json"
                game3.rng.seed(7777)
                self.assertTrue(game3.load_run())
                self.assertEqual(
                    game3.player.skill_upgrades,
                    ["rogue_precision", "rogue_venom"],
                )
                # The run is still playable and the tree offers valid choices.
                self.assertTrue(game3.available_skill_choices())
            finally:
                pass

    # --- Character menu tabs --------------------------------------------------

    def test_character_menu_tabs_toggle_and_render(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=3, seed=3271)  # Acolyte
            try:
                self.assertEqual(game.character_menu_tab, "overview")
                # Toggle open, then switch tabs via Tab key.
                game.character_menu_open = True
                pygame.event.post(
                    pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB, mod=0)
                )
                game.handle_events()
                self.assertEqual(game.character_menu_tab, "skill_tree")
                pygame.event.post(
                    pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB, mod=0)
                )
                game.handle_events()
                self.assertEqual(game.character_menu_tab, "overview")
                # Direct arrow keys also switch.
                pygame.event.post(
                    pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHT, mod=0)
                )
                game.handle_events()
                self.assertEqual(game.character_menu_tab, "skill_tree")
                pygame.event.post(
                    pygame.event.Event(pygame.KEYDOWN, key=pygame.K_LEFT, mod=0)
                )
                game.handle_events()
                self.assertEqual(game.character_menu_tab, "overview")
                # Number keys switch too.
                pygame.event.post(
                    pygame.event.Event(pygame.KEYDOWN, key=pygame.K_2, mod=0)
                )
                game.handle_events()
                self.assertEqual(game.character_menu_tab, "skill_tree")

                # Render overview tab.
                game.character_menu_tab = "overview"
                game.draw_character_menu()
                # Render skill tree tab with some acquired nodes.
                game.character_menu_tab = "skill_tree"
                game.player.skill_points = 2
                game.choose_skill_upgrade("acolyte_sanguine")
                game.choose_skill_upgrade("acolyte_gravebind")
                game.draw_character_menu()
                # Compact screen size should still render without error.
                compact = Game(
                    screen_size=(640, 360),
                    headless=True,
                    save_path=Path(tmpdir) / "run2.json",
                )
                compact.options_path = Path(tmpdir) / "options2.json"
                compact.rng.seed(3272)
                compact.restart(ARCHETYPES[4])  # Ranger
                if compact.story_intro_pending:
                    self.assertTrue(compact.choose_story_relic_path(0))
                compact.active_cutscene = None
                compact.character_menu_open = True
                compact.character_menu_tab = "skill_tree"
                compact.draw_character_menu()
            finally:
                pass

    def test_skill_node_state_reports_chosen_available_locked(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0, seed=3281)
            try:
                game.player.skill_points = 1
                bulwark = skill_node_by_key("warden_bulwark")
                aegis = skill_node_by_key("warden_aegis")
                iron_vow = skill_node_by_key("warden_iron_vow")
                self.assertEqual(game.skill_node_state(bulwark), "available")
                self.assertEqual(game.skill_node_state(aegis), "locked")
                self.assertEqual(game.skill_node_state(iron_vow), "locked")
                game.choose_skill_upgrade("warden_bulwark")
                self.assertEqual(game.skill_node_state(bulwark), "chosen")
                self.assertEqual(game.skill_node_state(aegis), "available")
                self.assertEqual(game.skill_node_state(iron_vow), "locked")
            finally:
                pass


if __name__ == "__main__":
    unittest.main()
