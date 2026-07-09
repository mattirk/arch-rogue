# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
#
# AI Provenance & Liability Notice:
# This repository contains code generated, assisted, or refactored by Artificial
# Intelligence models. Provided strictly "AS IS" under Apache 2.0 with no warranty
# of clean IP provenance or non-infringement; downstream users assume all legal
# and financial risk and should perform their own compliance audits.
#
# Milestone 3.17 — Rogue Ambush Bell.
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game
from arch_rogue.models import AmbushBell, Enemy, Tile


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


def _open_patch(game: Game, x: float, y: float, radius: int = 7) -> None:
    cx = int(x)
    cy = int(y)
    for tx in range(max(1, cx - radius), min(len(game.dungeon.tiles) - 1, cx + radius + 1)):
        column = game.dungeon.tiles[tx]
        for ty in range(max(1, cy - radius), min(len(column) - 1, cy + radius + 1)):
            column[ty] = Tile.FLOOR


class AmbushBell317Tests(unittest.TestCase):
    def make_game(self, tmpdir: str, archetype_index: int = 1, seed: int = 3170) -> Game:
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

    def test_rogue_slot_3_dispatch_spends_budget_and_replaces_one_bell(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=1)
            self.assertEqual(game.skill_names()[2], "Ambush Bell")
            self.assertEqual(game.slot_3_skill_kind(), "ambush_bell")
            slots = game.hud_action_slots()
            self.assertEqual(slots[2]["kind"], "ambush_bell")
            self.assertEqual(slots[2]["label"], "Ambush Bell")
            self.assertEqual(slots[2]["cost"], game.nova_mana_cost())
            self.assertEqual(slots[2]["cooldown"], game.nova_cooldown())

            game.player.nova_timer = 0.0
            game.player.mana = game.player.max_mana
            game.player.facing_x = 1.0
            game.player.facing_y = 0.0
            before_mana = game.player.mana
            game.player_cast_slot_3()

            self.assertEqual(len(game.ambush_bells), 1)
            first = game.ambush_bells[0]
            self.assertIsInstance(first, AmbushBell)
            self.assertLess(game.player.mana, before_mana)
            self.assertGreater(game.player.nova_timer, 0.0)
            self.assertGreater(game.player_status("smoke"), 0.0)
            self.assertNotIn("ambush_bells", game.serialize_run_state())

            game.player.nova_timer = 0.0
            game.player.mana = game.player.max_mana
            game.player.facing_x = 0.0
            game.player.facing_y = 1.0
            game.player_cast_slot_3()
            self.assertEqual(len(game.ambush_bells), 1)
            replacement = game.ambush_bells[0]
            self.assertIsNot(replacement, first)
            self.assertNotAlmostEqual(replacement.y, first.y, places=2)

    def test_arming_delay_then_trigger_detonates_and_applies_venom(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=1)
            game.player.skill_upgrades.append("rogue_venom")
            game.player.nova_timer = 0.0
            game.player.mana = game.player.max_mana
            game.player.facing_x = 1.0
            game.player.facing_y = 0.0
            game.player_cast_ambush_bell()
            bell = game.ambush_bells[0]

            enemy = _make_enemy(bell.x, bell.y, hp=999)
            game.enemies = [enemy]
            game.update_ambush_bells(game.ambush_bell_arm_time() * 0.45)
            self.assertEqual(len(game.ambush_bells), 1)
            self.assertEqual(enemy.hp, enemy.max_hp)

            game.update_ambush_bells(game.ambush_bell_arm_time())
            self.assertEqual(game.ambush_bells, [])
            self.assertLess(enemy.hp, enemy.max_hp)
            self.assertIn("poisoned", enemy.statuses)

    def test_expiry_splashes_nearby_enemy_without_trigger_radius(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=1)
            game.player.nova_timer = 0.0
            game.player.mana = game.player.max_mana
            game.player.facing_x = 1.0
            game.player.facing_y = 0.0
            game.player_cast_ambush_bell()
            bell = game.ambush_bells[0]
            bell.arm_timer = 0.0
            bell.armed_announced = True

            enemy = _make_enemy(bell.x + bell.trigger_radius + 0.35, bell.y, hp=220)
            game.enemies = [enemy]
            game.update_ambush_bells(bell.lifetime + 0.1)

            self.assertEqual(game.ambush_bells, [])
            self.assertLess(enemy.hp, enemy.max_hp)

    def test_lure_biases_enemy_toward_bell_not_player(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=1)
            px, py = game.player.x, game.player.y
            _open_patch(game, px + 4.0, py)
            enemy = _make_enemy(px + 2.0, py, hp=220)
            bell = AmbushBell(
                x=px + 4.0,
                y=py,
                lifetime=5.0,
                arm_timer=0.0,
                lure_radius=6.0,
                trigger_radius=0.20,
                damage_radius=1.5,
                primary_damage=30,
                splash_damage=12,
                max_lifetime=5.0,
                max_arm_timer=0.0,
                armed_announced=True,
            )
            game.enemies = [enemy]
            game.ambush_bells = [bell]

            start_x = enemy.x
            game.update_enemies(0.20)

            self.assertGreater(enemy.x, start_x)
            self.assertEqual(enemy.telegraph, "lured")

    def test_acolyte_and_other_classes_keep_their_slot_3_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            acolyte = self.make_game(tmpdir, archetype_index=3)
            self.assertEqual(acolyte.slot_3_skill_kind(), "spirit_call")
            acolyte.player.nova_timer = 0.0
            acolyte.player.mana = acolyte.player.max_mana
            acolyte.player_cast_slot_3()
            self.assertEqual(len(acolyte.familiars), 1)
            self.assertEqual(getattr(acolyte, "ambush_bells", []), [])

        with tempfile.TemporaryDirectory() as tmpdir:
            arcanist = self.make_game(tmpdir, archetype_index=2)
            self.assertEqual(arcanist.slot_3_skill_kind(), "nova")
            enemy = _make_enemy(arcanist.player.x + 1.0, arcanist.player.y, hp=220)
            arcanist.enemies = [enemy]
            arcanist.player.nova_timer = 0.0
            arcanist.player.mana = arcanist.player.max_mana
            arcanist.player_cast_slot_3()
            self.assertEqual(getattr(arcanist, "ambush_bells", []), [])
            self.assertEqual(arcanist.familiars, [])
            self.assertLess(enemy.hp, enemy.max_hp)

    def test_floor_descent_death_and_restore_clear_active_bells(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=1)
            game.player.nova_timer = 0.0
            game.player.mana = game.player.max_mana
            game.player_cast_ambush_bell()
            self.assertEqual(len(game.ambush_bells), 1)

            data = game.serialize_run_state()
            loaded = Game(
                screen_size=(960, 600),
                headless=True,
                save_path=Path(tmpdir) / "restore.json",
            )
            loaded.options_path = Path(tmpdir) / "restore-options.json"
            loaded.restore_run_state(data)
            self.assertEqual(getattr(loaded, "ambush_bells", []), [])

            game.descend_to_next_depth()
            self.assertEqual(game.ambush_bells, [])

            game.player.nova_timer = 0.0
            game.player.mana = game.player.max_mana
            game.player_cast_ambush_bell()
            self.assertEqual(len(game.ambush_bells), 1)
            game.story_intro_pending = False
            game.active_cutscene = None
            game.state = "playing"
            game.player.hp = 0
            game.update(0.016)
            self.assertEqual(game.ambush_bells, [])


if __name__ == "__main__":
    unittest.main()
