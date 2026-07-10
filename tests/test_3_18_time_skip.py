# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
#
# AI Provenance & Liability Notice:
# This repository contains code generated, assisted, or refactored by Artificial
# Intelligence models. Provided strictly "AS IS" under Apache 2.0 with no warranty
# of clean IP provenance or non-infringement; downstream users assume all legal
# and financial risk and should perform their own compliance audits.
#
# Milestone 3.18 — Warden Time Skip (class-skill enemy-only slow).
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from arch_rogue import __version__
from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game
from arch_rogue.models import Enemy, Item, Tile


def _make_enemy(x: float, y: float, hp: int = 220, kind: str = "melee") -> Enemy:
    return Enemy(
        "Test Dummy",
        kind,
        x,
        y,
        hp,
        hp,
        2.4,
        6,
        12,
        0.85 if kind == "melee" else 5.0,
        1.0,
    )


def _open_patch(game: Game, x: float, y: float, radius: int = 8) -> None:
    cx = int(x)
    cy = int(y)
    for tx in range(max(1, cx - radius), min(len(game.dungeon.tiles) - 1, cx + radius + 1)):
        column = game.dungeon.tiles[tx]
        for ty in range(max(1, cy - radius), min(len(column) - 1, cy + radius + 1)):
            column[ty] = Tile.FLOOR


class TimeSkip318Tests(unittest.TestCase):
    def make_game(self, tmpdir: str, archetype_index: int = 0, seed: int = 3180) -> Game:
        game = Game(
            screen_size=(960, 600),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.ui_scale = 1
        game.rebuild_fonts()
        game.rng.seed(seed)
        game.restart(ARCHETYPES[archetype_index])
        if game.story_intro_pending:
            self.assertTrue(game.choose_story_relic_path(0))
        game.active_cutscene = None
        _open_patch(game, game.player.x, game.player.y)
        game.enemies = []
        game.projectiles = []
        game.traps = []
        return game

    # --- class-skill swap ----------------------------------------------

    def test_version_bumped(self) -> None:
        self.assertEqual(__version__, "3.19.1")

    def test_warden_class_skill_is_time_skip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            self.assertEqual(game.player.class_name, "Warden")
            self.assertEqual(game.skill_names()[2], "Time Skip")
            self.assertEqual(game.class_skill_kind(), "time_skip")
            slots = game.hud_action_slots()
            self.assertEqual(slots[2]["kind"], "time_skip")
            self.assertEqual(slots[2]["icon"], "time_skip")
            self.assertEqual(slots[2]["label"], "Time Skip")
            self.assertEqual(slots[2]["cost"], game.class_skill_mana_cost())
            self.assertEqual(slots[2]["cooldown"], game.class_skill_cooldown())

    def test_non_warden_classes_keep_nova(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            arcanist = self.make_game(tmpdir, archetype_index=2)
            self.assertEqual(arcanist.player.class_name, "Arcanist")
            self.assertEqual(arcanist.class_skill_kind(), "nova")
            self.assertEqual(arcanist.skill_names()[2], "Frost Nova")

    # --- cast behavior -------------------------------------------------

    def test_cast_spends_budget_and_opens_slow_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            enemy = _make_enemy(game.player.x + 3.0, game.player.y)
            game.enemies = [enemy]
            enemy_hp_before = enemy.hp

            game.player.class_skill_timer = 0.0
            game.player.mana = game.player.max_mana
            before_mana = game.player.mana
            game.player_cast_class_skill()

            # Class-skill budget spent, slow window opened, no enemy damage.
            self.assertLess(game.player.mana, before_mana)
            self.assertGreater(game.player.class_skill_timer, 0.0)
            self.assertAlmostEqual(
                game.player.time_skip_timer, game.time_skip_duration(), places=4
            )
            self.assertEqual(enemy.hp, enemy_hp_before)
            # Time Skip is transient and never serialized.
            self.assertNotIn("time_skip_timer", game.serialize_run_state())

    def test_cast_blocked_by_cooldown_and_mana(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            game.player.class_skill_timer = 1.0
            game.player.mana = game.player.max_mana
            game.player_cast_class_skill()
            self.assertEqual(game.player.time_skip_timer, 0.0)

            game.player.class_skill_timer = 0.0
            game.player.mana = 0
            game.player_cast_class_skill()
            self.assertEqual(game.player.time_skip_timer, 0.0)

    # --- enemy slow ----------------------------------------------------

    def test_enemies_move_slower_while_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            # Place a melee enemy inside aggro range but outside melee range so
            # it pursues the player without attacking.
            enemy = _make_enemy(game.player.x + 5.0, game.player.y)
            enemy.attack_timer = 5.0  # prevent attacks during the step
            game.enemies = [enemy]

            # Control step: normal time.
            start_x = enemy.x
            game.update_enemies(0.5)
            normal_step = abs(enemy.x - start_x)
            self.assertGreater(normal_step, 0.0)

            # Reset position and run the same step under Time Skip.
            enemy.x = start_x
            enemy.attack_timer = 5.0
            game.player.time_skip_timer = game.time_skip_duration()
            game.update_enemies(0.5)
            slowed_step = abs(enemy.x - start_x)

            self.assertLess(slowed_step, normal_step)
            # ~40% speed: the slowed step should be noticeably below the normal
            # one and roughly proportional to the time-skip factor.
            self.assertLess(slowed_step, normal_step * 0.6)

    def test_enemy_attack_cadence_slows_while_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            enemy = _make_enemy(game.player.x + 5.0, game.player.y)
            game.enemies = [enemy]

            # Normal time: attack_timer ticks down by dt.
            enemy.attack_timer = 1.0
            game.update_enemies(0.5)
            self.assertAlmostEqual(enemy.attack_timer, 0.5, places=4)

            # Under Time Skip: attack_timer ticks down by dt * 0.4.
            enemy.attack_timer = 1.0
            game.player.time_skip_timer = game.time_skip_duration()
            game.update_enemies(0.5)
            self.assertAlmostEqual(enemy.attack_timer, 0.8, places=4)

    def test_player_unaffected_by_own_time_skip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            game.player.time_skip_timer = game.time_skip_duration()
            game.player.melee_timer = 0.5
            game.player.dash_timer = 0.5
            game.player.bolt_timer = 0.5
            game.player.class_skill_timer = 0.5
            game.update_player(0.5)
            # Player timers tick at full dt, not the slowed enemy rate.
            self.assertAlmostEqual(game.player.melee_timer, 0.0, places=4)
            self.assertAlmostEqual(game.player.dash_timer, 0.0, places=4)
            self.assertAlmostEqual(game.player.bolt_timer, 0.0, places=4)
            self.assertAlmostEqual(game.player.class_skill_timer, 0.0, places=4)
            # The slow window itself still counts down for the player.
            self.assertLess(game.player.time_skip_timer, game.time_skip_duration())

    def test_time_skip_expires_and_enemies_resume_normal_speed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            self.assertEqual(game.enemy_time_scale(), 1.0)
            game.player.time_skip_timer = 1.0
            self.assertAlmostEqual(game.enemy_time_scale(), game.time_skip_factor())
            # Tick the player timer down to expiry.
            game.update_player(1.0)
            self.assertEqual(game.player.time_skip_timer, 0.0)
            self.assertEqual(game.enemy_time_scale(), 1.0)

    # --- Time Discipline Path (3.18.1) -----------------------------

    def test_duration_scales_along_time_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            base = game.time_skip_duration()
            self.assertAlmostEqual(base, 3.0, places=4)

            # Degree 1 Temporal Sigil.
            game.player.skill_upgrades.append("warden_ward")
            self.assertAlmostEqual(game.time_skip_duration(), 3.5, places=4)

            # Degree 2 Time Skip node.
            game.player.skill_upgrades.append("warden_bulwark_wave")
            self.assertAlmostEqual(game.time_skip_duration(), 4.5, places=4)

    def test_t1_temporal_sigil_discounts_class_skill_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            base_cost = game.class_skill_mana_cost()
            base_cooldown = game.class_skill_cooldown()
            game.player.skill_upgrades.append("warden_ward")
            self.assertLess(game.class_skill_mana_cost(), base_cost)
            self.assertLess(game.class_skill_cooldown(), base_cooldown)

    def test_t3_stutter_step_deepens_the_slow(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            self.assertAlmostEqual(game.time_skip_factor(), 0.4, places=4)
            game.player.skill_upgrades.append("warden_stone_aegis")
            self.assertAlmostEqual(game.time_skip_factor(), 0.3, places=4)
            # The deeper factor flows through enemy_time_scale while active.
            game.player.time_skip_timer = 1.0
            self.assertAlmostEqual(game.enemy_time_scale(), 0.3, places=4)

    def test_t2_time_skip_node_staggers_foes_in_cast_ring(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            game.player.skill_upgrades.append("warden_bulwark_wave")
            inside = _make_enemy(game.player.x + 2.0, game.player.y)
            outside = _make_enemy(game.player.x + 5.0, game.player.y)
            game.enemies = [inside, outside]
            inside_hp = inside.hp
            outside_hp = outside.hp

            game.player.class_skill_timer = 0.0
            game.player.mana = game.player.max_mana
            game.player_cast_class_skill()

            # Inside the ring: stunned, attack stalled, no damage dealt.
            self.assertGreater(inside.statuses.get("stunned", 0.0), 0.0)
            self.assertGreaterEqual(inside.attack_timer, 0.45)
            self.assertEqual(inside.hp, inside_hp)
            # Outside the ring: untouched.
            self.assertEqual(outside.hp, outside_hp)
            self.assertEqual(outside.statuses.get("stunned", 0.0), 0.0)

    def test_t4_temporal_aegis_reduces_incoming_damage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            game.player.skill_upgrades.append("warden_unyielding")
            attacker = _make_enemy(game.player.x + 1.0, game.player.y)
            game.enemies = [attacker]

            # Without Time Skip active: baseline damage.
            game.player.hp = game.player.max_hp
            base = game.take_player_damage(20, source="melee", attacker=attacker)
            self.assertGreater(base, 0)

            # With Time Skip active: the Temporal Aegis ward reduces damage.
            game.player.hp = game.player.max_hp
            game.player.time_skip_timer = game.time_skip_duration()
            warded = game.take_player_damage(20, source="melee", attacker=attacker)
            self.assertLess(warded, base)

    def test_t5_eternal_moment_refunds_cooldown_on_kill(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            game.player.skill_upgrades.append("warden_eternal_wall")
            # A wounded enemy the Warden will kill.
            enemy = _make_enemy(game.player.x + 1.0, game.player.y, hp=2)
            game.enemies = [enemy]

            # Start a Time Skip window and set a nonzero slot cooldown.
            game.player.time_skip_timer = game.time_skip_duration()
            game.player.class_skill_timer = game.class_skill_cooldown()
            before = game.player.class_skill_timer
            # Kill the enemy directly; kill_enemy applies the refund.
            enemy.hp = 1
            game.damage_enemy(enemy, 5, knockback_from=(0.0, 0.0))
            self.assertEqual(game.enemies, [])
            self.assertLess(game.player.class_skill_timer, before)

    def test_t5_refund_only_while_time_skip_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            game.player.skill_upgrades.append("warden_eternal_wall")
            enemy = _make_enemy(game.player.x + 1.0, game.player.y, hp=2)
            game.enemies = [enemy]
            game.player.class_skill_timer = game.class_skill_cooldown()
            before = game.player.class_skill_timer
            # No Time Skip window: no refund.
            enemy.hp = 1
            game.damage_enemy(enemy, 5, knockback_from=(0.0, 0.0))
            self.assertEqual(game.enemies, [])
            self.assertAlmostEqual(game.player.class_skill_timer, before, places=4)

    def test_equipment_bonus_recognizes_time_skip_and_legacy_nova(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            # No class-skill gear: no bonus.
            self.assertFalse(game.equipment_class_skill_bonus())

            # New Time Skip wording on future gear.
            game.player.equipment["weapon"] = Item(
                name="Chrono Aegis", slot="weapon", skill_bonus="Time Skip"
            )
            self.assertTrue(game.equipment_class_skill_bonus())
            self.assertTrue(game.equipment_class_skill_bonus("Time Skip"))

            # A Time Skip duration affix both counts as a class-skill bonus and
            # extends the slow window.
            game.player.equipment["weapon"] = Item(
                name="Chrono Duration", slot="weapon", skill_bonus="Time Skip duration"
            )
            self.assertTrue(game.equipment_class_skill_bonus("Time Skip duration"))
            self.assertAlmostEqual(game.time_skip_duration(), 3.0 + 0.5, places=4)

            # Legacy Nova gear on an older Warden save still applies its
            # class-skill budget (and Nova-radius wording still resolves).
            game.player.equipment["weapon"] = Item(
                name="Old Bulwark", slot="weapon", skill_bonus="Nova"
            )
            self.assertTrue(game.equipment_class_skill_bonus())
            game.player.equipment["weapon"] = Item(
                name="Old Bulwark Radius", slot="weapon", skill_bonus="Nova radius"
            )
            self.assertTrue(game.equipment_class_skill_bonus("Nova radius"))

            # Time Skip wording does not leak to non-Warden classes.
            arcanist = self.make_game(tmpdir, archetype_index=2)
            arcanist.player.equipment["weapon"] = Item(
                name="Chrono Aegis", slot="weapon", skill_bonus="Time Skip"
            )
            self.assertFalse(arcanist.equipment_class_skill_bonus())

    # --- save round-trip & render -------------------------------------

    def test_save_round_trip_resets_transient_timer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            game.player.time_skip_timer = 2.5
            data = game.serialize_run_state()
            self.assertEqual(data["release"], "3.19.1")
            self.assertNotIn("time_skip_timer", data)

            loaded = Game(
                screen_size=(960, 600),
                headless=True,
                save_path=Path(tmpdir) / "restore.json",
            )
            loaded.options_path = Path(tmpdir) / "restore-opt.json"
            loaded.restore_run_state(data)
            self.assertEqual(loaded.player.class_name, "Warden")
            self.assertEqual(loaded.player.time_skip_timer, 0.0)
            self.assertEqual(loaded.class_skill_kind(), "time_skip")

    def test_full_frame_render_with_active_time_skip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)
            game.enemies = [_make_enemy(game.player.x + 3.0, game.player.y)]
            game.player.class_skill_timer = 0.0
            game.player.mana = game.player.max_mana
            game.player_cast_class_skill()
            self.assertGreater(game.player.time_skip_timer, 0.0)
            # A full frame render with the slow window active must not raise;
            # the clock glyph draws alongside the rest of the HUD action bar.
            game.draw()


if __name__ == "__main__":
    unittest.main()