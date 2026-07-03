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
    MAX_COMMITTED_BRANCHES,
    branch_progress,
    committed_branches,
    is_branch_locked,
    skill_branches_for_archetype,
    skill_node_by_key,
    skill_nodes_for_archetype,
)
from arch_rogue.game import Game
from arch_rogue.models import Enemy, Projectile


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

    # --- 1. Commitment-limit constant ---------------------------------------

    def test_max_committed_branches_constant(self) -> None:
        self.assertEqual(MAX_COMMITTED_BRANCHES, 2)

    # --- 2. Pure helper math -------------------------------------------------

    def test_committed_branches_and_is_branch_locked_helpers(self) -> None:
        archetype = "Warden"
        branches = skill_branches_for_archetype(archetype)
        self.assertGreaterEqual(len(branches), 4)

        # Empty acquired set: nothing committed, nothing locked.
        empty: set[str] = set()
        self.assertEqual(committed_branches(empty, archetype), ())
        for branch in branches:
            self.assertFalse(is_branch_locked(empty, archetype, branch))

        # One committed branch: only that branch committed, none locked.
        one = {"warden_bulwark"}
        self.assertEqual(committed_branches(one, archetype), ("Bulwark",))
        for branch in branches:
            self.assertFalse(is_branch_locked(one, archetype, branch))

        # Two committed branches: the others become locked.
        two = {"warden_bulwark", "warden_riposte"}
        self.assertEqual(committed_branches(two, archetype), ("Bulwark", "Riposte"))
        for branch in branches:
            expected_locked = branch not in ("Bulwark", "Riposte")
            self.assertEqual(
                is_branch_locked(two, archetype, branch),
                expected_locked,
                f"branch {branch} lock mismatch",
            )

    # --- 3. choose_skill_upgrade enforces the two-branch limit ---------------

    def test_choose_skill_upgrade_enforces_two_branch_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            try:
                game.player.skill_points = 10

                # Commit to Bulwark and Riposte (two tier-1 entries).
                self.assertTrue(game.choose_skill_upgrade("warden_bulwark"))
                self.assertTrue(game.choose_skill_upgrade("warden_riposte"))

                # Tier-1 entries of the other two branches must be rejected.
                self.assertFalse(game.choose_skill_upgrade("warden_smite"))
                self.assertFalse(game.choose_skill_upgrade("warden_ward"))

                # available_skill_choices excludes Vow/Fortress tier-1 nodes
                # but still offers deeper nodes in committed branches.
                choices = game.available_skill_choices()
                choice_keys = {node.key for node in choices}
                self.assertNotIn("warden_smite", choice_keys)
                self.assertNotIn("warden_ward", choice_keys)
                self.assertIn("warden_aegis", choice_keys)  # Bulwark t2
                self.assertIn("warden_counter", choice_keys)  # Riposte t2
            finally:
                pass

    # --- 4. skill_node_state distinguishes branch_locked vs locked ----------

    def test_skill_node_state_reports_branch_locked(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            try:
                game.player.skill_points = 10

                smite = skill_node_by_key("warden_smite")
                self.assertIsNotNone(smite)
                # Before any commitment Vow t1 is simply available.
                self.assertEqual(game.skill_node_state(smite), "available")

                # A prereq-locked node (Bulwark t2 before Bulwark t1) is "locked".
                aegis = skill_node_by_key("warden_aegis")
                self.assertIsNotNone(aegis)
                self.assertEqual(game.skill_node_state(aegis), "locked")

                # Commit to two branches -> Vow becomes branch_locked.
                self.assertTrue(game.choose_skill_upgrade("warden_bulwark"))
                self.assertTrue(game.choose_skill_upgrade("warden_riposte"))
                self.assertEqual(game.skill_node_state(smite), "branch_locked")
            finally:
                pass

    # --- 5. Already-committed branches keep progressing ---------------------

    def test_already_committed_branches_keep_progressing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            try:
                game.player.skill_points = 10

                # Commit to Bulwark (t1) and Vow (t1) = two commitments.
                self.assertTrue(game.choose_skill_upgrade("warden_bulwark"))
                self.assertTrue(game.choose_skill_upgrade("warden_smite"))

                # Riposte/Fortress tier-1 nodes are now locked out.
                self.assertFalse(game.choose_skill_upgrade("warden_riposte"))
                self.assertFalse(game.choose_skill_upgrade("warden_ward"))

                # But deeper nodes in committed branches are still choosable.
                self.assertTrue(game.choose_skill_upgrade("warden_aegis"))  # Bulwark t2
                self.assertTrue(game.choose_skill_upgrade("warden_judgment"))  # Vow t2
            finally:
                pass

    # --- 6. Arc Bolt is a single shot without the Bolt branch ----------------

    def test_arc_bolt_single_shot_without_bolt_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=2)
            try:
                game.projectiles.clear()
                game.player.mana = game.player.max_mana
                game.player.bolt_timer = 0.0
                game.player.facing_x = 1.0
                game.player.facing_y = 0.0

                game.player_cast_bolt()

                self.assertEqual(len(game.projectiles), 1)
                bolt = game.projectiles[0]
                self.assertEqual(bolt.pierce, 0)
                self.assertEqual(bolt.homing, 0.0)
            finally:
                pass

    # --- 7. Arc Bolt fan + pierce + homing progression ----------------------

    def test_arc_bolt_multi_shot_with_splinter_and_pierce_homing_progression(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=2)
            try:
                # splinter t1 -> 2 bolts (one extra shard)
                game.player.skill_upgrades.append("arcanist_splinter")
                game.projectiles.clear()
                game.player.mana = game.player.max_mana
                game.player.bolt_timer = 0.0
                game.player.facing_x = 1.0
                game.player.facing_y = 0.0
                game.player_cast_bolt()
                self.assertEqual(len(game.projectiles), 2)
                self.assertTrue(all(p.pierce == 0 for p in game.projectiles))

                # + overload t2 -> 3 bolts (split on impact) and pierce 1
                game.player.skill_upgrades.append("arcanist_overload")
                game.projectiles.clear()
                game.player.bolt_timer = 0.0
                game.player.mana = game.player.max_mana
                game.player_cast_bolt()
                self.assertEqual(len(game.projectiles), 3)
                self.assertTrue(all(p.pierce == 1 for p in game.projectiles))

                # + pierce t3 -> pierce ramps to 2 (bolt count unchanged)
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

    # --- 8. Ranger Multishot: gradual arrow ramp + homing capstone ----------

    def test_ranger_multishot_single_arrow_without_volley(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=4)
            try:
                game.projectiles.clear()
                game.player.mana = game.player.max_mana
                game.player.bolt_timer = 0.0
                game.player.facing_x = 1.0
                game.player.facing_y = 0.0
                game.player_cast_bolt()
                self.assertEqual(len(game.projectiles), 1)

                # volley t1 -> 3-arrow fan
                game.player.skill_upgrades.append("ranger_volley")
                game.projectiles.clear()
                game.player.bolt_timer = 0.0
                game.player.mana = game.player.max_mana
                game.player_cast_bolt()
                self.assertEqual(len(game.projectiles), 3)
                self.assertTrue(all(p.pierce == 0 for p in game.projectiles))

                # rapid t2 -> 4 arrows
                game.player.skill_upgrades.append("ranger_rapid")
                game.projectiles.clear()
                game.player.bolt_timer = 0.0
                game.player.mana = game.player.max_mana
                game.player_cast_bolt()
                self.assertEqual(len(game.projectiles), 4)

                # storm volley t4 -> 5-arrow storm cone
                game.player.skill_upgrades.append("ranger_storm_volley")
                game.projectiles.clear()
                game.player.bolt_timer = 0.0
                game.player.mana = game.player.max_mana
                game.player_cast_bolt()
                self.assertEqual(len(game.projectiles), 5)

                # piercing volley t3 grants pierce=1 (count unchanged)
                game.player.skill_upgrades.append("ranger_piercing_volley")
                game.projectiles.clear()
                game.player.bolt_timer = 0.0
                game.player.mana = game.player.max_mana
                game.player_cast_bolt()
                self.assertEqual(len(game.projectiles), 5)
                self.assertTrue(all(p.pierce == 1 for p in game.projectiles))

                # sky quiver capstone -> homing (count unchanged)
                game.player.skill_upgrades.append("ranger_sky_quiver")
                game.projectiles.clear()
                game.player.bolt_timer = 0.0
                game.player.mana = game.player.max_mana
                game.player_cast_bolt()
                self.assertEqual(len(game.projectiles), 5)
                self.assertTrue(all(p.homing > 0.0 for p in game.projectiles))
            finally:
                pass

    # --- 9. Piercing projectiles survive the first hit ----------------------

    def test_projectile_pierce_passes_through_enemies(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=2)
            try:
                px, py = game.player.x, game.player.y
                # Enemy placed just ahead on the projectile's path.
                enemy = _make_enemy(px + 0.3, py, hp=200)
                game.enemies = [enemy]

                # A pierce=1 projectile should survive hitting one foe and
                # have its pierce decremented to 0 (still kept this frame).
                pierce_proj = Projectile(
                    px,
                    py,
                    9.0,
                    0.0,
                    20,
                    "player",
                    (255, 255, 255),
                    pierce=1,
                    ttl=1.6,
                )
                game.projectiles = [pierce_proj]
                game.update_projectiles(0.01)
                self.assertTrue(any(p is pierce_proj for p in game.projectiles))
                self.assertEqual(pierce_proj.pierce, 0)
                self.assertIn(id(enemy), pierce_proj.hit_enemies)
                self.assertLess(enemy.hp, 200)

                # A pierce=0 projectile that hits a foe is removed.
                enemy2 = _make_enemy(px + 0.3, py, hp=200)
                game.enemies = [enemy2]
                normal_proj = Projectile(
                    px,
                    py,
                    9.0,
                    0.0,
                    20,
                    "player",
                    (255, 255, 255),
                    pierce=0,
                    ttl=1.6,
                )
                game.projectiles = [normal_proj]
                game.update_projectiles(0.01)
                self.assertFalse(any(p is normal_proj for p in game.projectiles))
                self.assertLess(enemy2.hp, 200)
            finally:
                pass

    # --- 10. Warden Shield Bash: gradual cleave ramp (1/2/3 foes) -----------

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

                # Bulwark t1 unlocks the cleave arc -> both foes hit.
                game.player.skill_upgrades.append("warden_bulwark")
                near.hp = 200
                far.hp = 200
                game.player.melee_timer = 0.0
                game.player.stamina = game.player.max_stamina
                game.player_melee_attack()
                self.assertLess(near.hp, 200)
                self.assertLess(far.hp, 200)

                # Aegis t2 widens the cleave arc to 3 foes; add a third enemy.
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

    # --- 11. Rogue crits are gated behind the Precision branch --------------

    def test_rogue_crit_gated_behind_precision(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=1, seed=3701)
            try:
                px, py = game.player.x, game.player.y
                enemy = _make_enemy(px + 0.8, py, hp=9999)
                game.enemies = [enemy]
                game.player.facing_x = 1.0
                game.player.facing_y = 0.0

                # Without rogue_precision crit_chance is 0.0 -> never crits.
                # Reset the enemy position each iteration because melee knocks
                # foes back and would eventually push it out of range.
                for _ in range(50):
                    enemy.x = px + 0.8
                    enemy.y = py
                    game.player.melee_timer = 0.0
                    game.player.stamina = game.player.max_stamina
                    game.player_melee_attack()
                self.assertFalse(
                    any(f.text == "Critical" for f in game.floaters),
                    "base Rogue should never crit without Precision branch",
                )

                # With rogue_precision crit_chance is 0.15 -> some crits appear.
                game.player.skill_upgrades.append("rogue_precision")
                game.floaters.clear()
                for _ in range(100):
                    enemy.x = px + 0.8
                    enemy.y = py
                    game.player.melee_timer = 0.0
                    game.player.stamina = game.player.max_stamina
                    game.player_melee_attack()
                self.assertTrue(
                    any(f.text == "Critical" for f in game.floaters),
                    "Rogue with Precision should crit within 100 attacks",
                )
            finally:
                pass

    # --- 12. Acolyte lifesteal gated behind Sanguine (melee + nova) ---------

    def test_acolyte_lifesteal_gated_behind_sanguine(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=3)
            try:
                px, py = game.player.x, game.player.y
                enemy = _make_enemy(px + 0.8, py, hp=9999)
                game.enemies = [enemy]
                game.player.facing_x = 1.0
                game.player.facing_y = 0.0

                # Helper ramps one step per Blood tier; base leech is 0.
                self.assertEqual(game._acolyte_melee_leech(), 0)
                self.assertEqual(game._acolyte_nova_leech(), 0)

                # --- Melee: no sanguine -> no leech ---
                game.player.hp = game.player.max_hp - 20
                hp_before = game.player.hp
                game.player.melee_timer = 0.0
                game.player.stamina = game.player.max_stamina
                game.player_melee_attack()
                self.assertEqual(game.player.hp, hp_before)

                # --- Melee: with sanguine -> leech applies (tier 1 = 2) ---
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
                self.assertEqual(game._acolyte_nova_leech(), 0)
                enemy2 = _make_enemy(px + 1.0, py, hp=9999)
                game.enemies = [enemy2]
                game.player.hp = game.player.max_hp - 20
                hp_before = game.player.hp
                game.player.nova_timer = 0.0
                game.player.mana = game.player.max_mana
                game.player_cast_nova()
                self.assertEqual(game.player.hp, hp_before)

                # --- Nova: with sanguine -> leech applies (tier 1 = 3) ---
                game.player.skill_upgrades.append("acolyte_sanguine")
                self.assertEqual(game._acolyte_nova_leech(), 3)
                enemy3 = _make_enemy(px + 1.0, py, hp=9999)
                game.enemies = [enemy3]
                game.player.hp = game.player.max_hp - 20
                hp_before = game.player.hp
                game.player.nova_timer = 0.0
                game.player.mana = game.player.max_mana
                game.player_cast_nova()
                self.assertGreater(game.player.hp, hp_before)

                # --- Blood Pact t3 ramps melee leech to 4 (gradual tier step) ---
                game.player.skill_upgrades.append("acolyte_blood_pact")
                self.assertEqual(game._acolyte_melee_leech(), 4)
                self.assertEqual(game._acolyte_nova_leech(), 5)
            finally:
                pass

    # --- 13. Arcanist Frost Nova radius ramps per Nova tier -----------------

    def test_arcanist_nova_radius_gated_behind_focus(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=2)
            try:
                px, py = game.player.x, game.player.y
                # Distance ~2.6: outside base radius (2.45) but inside the
                # focus-expanded radius (2.70).
                enemy = _make_enemy(px + 2.6, py, hp=9999)
                game.enemies = [enemy]

                # Without arcanist_focus the nova does not reach the enemy.
                game.player.nova_timer = 0.0
                game.player.mana = game.player.max_mana
                game.player_cast_nova()
                self.assertEqual(enemy.hp, 9999)

                # With arcanist_focus the radius grows and the enemy is hit.
                game.player.skill_upgrades.append("arcanist_focus")
                enemy.hp = 9999
                game.player.nova_timer = 0.0
                game.player.mana = game.player.max_mana
                game.player_cast_nova()
                self.assertLess(enemy.hp, 9999)

                # Permafrost t2 extends the radius further (2.45 + 0.45 = 2.90).
                # An enemy at 2.8 is outside the focus-only radius (2.70) but
                # inside the permafrost radius (2.90), locking the tier step.
                enemy_far = _make_enemy(px + 2.8, py, hp=9999)
                game.enemies = [enemy_far]
                # With only focus, the far enemy is out of reach.
                game.player.nova_timer = 0.0
                game.player.mana = game.player.max_mana
                game.player_cast_nova()
                self.assertEqual(enemy_far.hp, 9999)

                game.player.skill_upgrades.append("arcanist_permafrost")
                enemy_far.hp = 9999
                game.player.nova_timer = 0.0
                game.player.mana = game.player.max_mana
                game.player_cast_nova()
                self.assertLess(enemy_far.hp, 9999)
            finally:
                pass


if __name__ == "__main__":
    unittest.main()
