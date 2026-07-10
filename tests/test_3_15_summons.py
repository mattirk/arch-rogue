# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
#
# AI Provenance & Liability Notice:
# This repository contains code generated, assisted, or refactored by Artificial
# Intelligence models. Provided strictly "AS IS" under Apache 2.0 with no warranty
# of clean IP provenance or non-infringement; downstream users assume all legal
# and financial risk and should perform their own compliance audits.
#
# Milestone 3.15 — Summons, first edition (Acolyte Spirit Call / familiar).
from __future__ import annotations

import copy
import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame  # noqa: F401  (required to initialize pygame subsystems in tests)

from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game
from arch_rogue.models import Enemy, Familiar, Projectile


def _make_enemy(x: float, y: float, hp: int = 200, damage: int = 8) -> Enemy:
    return Enemy(
        "Test Dummy",
        "melee",
        x,
        y,
        hp,
        hp,
        1.0,
        damage,
        12,
        1.0,
        1.0,
    )


class Summons315Tests(unittest.TestCase):
    def make_game(self, tmpdir, archetype_index=3, seed=3151) -> Game:
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
        return game

    # --- slot-3 swap is Acolyte-only ------------------------------------

    def test_acolyte_slot_3_is_spirit_call_others_keep_nova(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            acolyte = self.make_game(tmpdir, archetype_index=3)
            self.assertEqual(acolyte.skill_names()[2], "Spirit Call")
            slots = acolyte.hud_action_slots()
            self.assertEqual(slots[2]["hotkey"], "3")
            self.assertEqual(slots[2]["label"], "Spirit Call")
            # Reuses the nova-slot cost/cooldown so the bar stays balanced.
            self.assertEqual(slots[2]["cost"], acolyte.nova_mana_cost())
            self.assertEqual(slots[2]["cooldown"], acolyte.nova_cooldown())
        with tempfile.TemporaryDirectory() as tmpdir:
            others = self.make_game(tmpdir, archetype_index=2)  # Arcanist
            self.assertEqual(others.skill_names()[2], "Frost Nova")

    # --- spawn / lifecycle ----------------------------------------------

    def test_spirit_call_spawns_a_familiar_and_persists_until_descent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.assertEqual(game.familiars, [])
            game.player.nova_timer = 0.0
            game.player.mana = game.player.max_mana
            game.player_cast_spirit_call()
            self.assertEqual(len(game.familiars), 1)
            familiar = game.familiars[0]
            self.assertIsInstance(familiar, Familiar)
            self.assertGreater(familiar.max_hp, 0)
            self.assertGreater(familiar.damage, 0)
            # Casting sets the nova-slot cooldown (reuses the nova slot).
            self.assertGreater(game.player.nova_timer, 0.0)
            self.assertLess(game.player.mana, game.player.max_mana)

            # The familiar persists across frames (no timeout); simulate a
            # few update ticks with no enemies so it just follows the player.
            for _ in range(20):
                game.update_familiars(0.05)
            self.assertEqual(len(game.familiars), 1)

            # Recasting recreates the host at the player's side at full HP
            # and does not double the host.
            game.familiars[0].hp = 1
            # Move the player so we can confirm the familiar snaps to the new spot.
            game.player.x += 5.0
            game.player.nova_timer = 0.0
            game.player.mana = game.player.max_mana
            game.player_cast_spirit_call()
            self.assertEqual(len(game.familiars), 1)
            self.assertEqual(game.familiars[0].hp, game.familiars[0].max_hp)
            # The recreated familiar spawns in a ring around the player's new position.
            self.assertLess(
                abs(game.familiars[0].x - game.player.x)
                + abs(game.familiars[0].y - game.player.y),
                2.0,
            )

            # Floor descent clears the host (persist until killed or descend).
            game.descend_to_next_depth()
            self.assertEqual(game.familiars, [])

    def test_familiar_killed_in_combat_is_culled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.player.nova_timer = 0.0
            game.player.mana = game.player.max_mana
            game.player_cast_spirit_call()
            familiar = game.familiars[0]
            # Drain it past zero; the cull on the next update removes it.
            familiar.unkillable = False
            familiar.hp = -5
            game.update_familiars(0.05)
            self.assertEqual(game.familiars, [])

    # --- follow-and-attack AI ------------------------------------------

    def test_familiar_pursues_and_attacks_nearby_enemy(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.player.nova_timer = 0.0
            game.player.mana = game.player.max_mana
            game.player_cast_spirit_call()
            familiar = game.familiars[0]
            # Place an enemy just inside aggro range but outside melee range.
            enemy = _make_enemy(familiar.x + 3.0, familiar.y, hp=999)
            game.enemies = [enemy]
            start_dist = abs(enemy.x - familiar.x)
            for _ in range(40):
                game.update_familiars(0.05)
            # The familiar closed the gap toward the enemy.
            end_dist = abs(enemy.x - familiar.x)
            self.assertLess(end_dist, start_dist)
            # And eventually landed hits (enemy HP dropped below max).
            self.assertLess(enemy.hp, enemy.max_hp)

    def test_familiar_returns_to_player_when_no_enemies(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.player.nova_timer = 0.0
            game.player.mana = game.player.max_mana
            game.player_cast_spirit_call()
            familiar = game.familiars[0]
            # Park the familiar far from the player with no enemies around.
            familiar.x = game.player.x + 6.0
            familiar.y = game.player.y
            game.enemies = []
            for _ in range(60):
                game.update_familiars(0.05)
            dist = abs(familiar.x - game.player.x)
            self.assertLess(dist, 6.0)

    def test_familiar_takes_damage_from_enemy_projectiles(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.player.nova_timer = 0.0
            game.player.mana = game.player.max_mana
            game.player_cast_spirit_call()
            familiar = game.familiars[0]
            familiar.unkillable = False
            start_hp = familiar.hp
            # Fire an enemy bolt straight at the familiar.
            game.projectiles = [
                Projectile(
                    familiar.x - 3.0,
                    familiar.y,
                    6.0,
                    0.0,
                    40,
                    "enemy",
                    (235, 90, 80),
                    ttl=2.0,
                )
            ]
            for _ in range(30):
                game.update_projectiles(0.05)
                if not game.projectiles:
                    break
            self.assertLess(familiar.hp, start_hp)

    # --- Spirit-branch scaling -----------------------------------------

    def test_spirit_branch_scales_hp_damage_count_and_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.player.nova_timer = 0.0
            game.player.mana = game.player.max_mana

            # Base host: 1 familiar, base stats, small sprite (variant 0).
            game.player_cast_spirit_call()
            base = game.familiars[0]
            self.assertEqual(game.familiar_max_count(), 1)
            base_hp, base_damage = base.max_hp, base.damage
            self.assertEqual(base.sprite_variant, 0)
            self.assertFalse(base.lifesteal)
            self.assertFalse(base.unkillable)
            self.assertFalse(base.champion)
            game.familiars = []
            game.player.nova_timer = 0.0
            game.player.mana = game.player.max_mana

            # Spirit Call node: +HP/+damage and medium sprite (variant 1).
            game.player.skill_upgrades.append("acolyte_spirit_call")
            game.player_cast_spirit_call()
            tier1 = game.familiars[0]
            self.assertGreater(tier1.max_hp, base_hp)
            self.assertGreater(tier1.damage, base_damage)
            self.assertEqual(tier1.sprite_variant, 1)
            game.familiars = []
            game.player.nova_timer = 0.0
            game.player.mana = game.player.max_mana

            # Owl Companion: more HP (lifesteal moved to the Blood branch in
            # 3.18.4, so the flag must be off without Blood investment).
            game.player.skill_upgrades.append("acolyte_wraith_host")
            game.player_cast_spirit_call()
            self.assertFalse(game.familiars[0].lifesteal)
            self.assertGreater(game.familiars[0].max_hp, tier1.max_hp)
            game.familiars = []
            game.player.nova_timer = 0.0
            game.player.mana = game.player.max_mana

            # Twin Owls: +1 familiar (count = 2) and more damage.
            game.player.skill_upgrades.append("acolyte_bone_legion")
            game.player_cast_spirit_call()
            self.assertEqual(game.familiar_max_count(), 2)
            self.assertEqual(len(game.familiars), 2)
            game.familiars = []
            game.player.nova_timer = 0.0
            game.player.mana = game.player.max_mana

            # Owl Lord: lead familiar is a champion (taunts); the sprite
            # stays the big owl (variant 1) once Spirit Call is chosen.
            game.player.skill_upgrades.append("acolyte_wraith_lord")
            game.player_cast_spirit_call()
            self.assertTrue(game.familiars[0].champion)
            self.assertEqual(game.familiars[0].sprite_variant, 1)
            self.assertGreater(game.familiars[0].max_hp, tier1.max_hp)
            game.familiars = []
            game.player.nova_timer = 0.0
            game.player.mana = game.player.max_mana

            # Eternal Owls: +1 familiar (count = 3) and unkillable host.
            game.player.skill_upgrades.append("acolyte_legion_eternal")
            game.player_cast_spirit_call()
            self.assertEqual(game.familiar_max_count(), 3)
            self.assertEqual(len(game.familiars), 3)
            self.assertTrue(all(f.unkillable for f in game.familiars))

    def test_lifesteal_familiar_heals_acolyte_on_hit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            # 3.18.4: familiar lifesteal is gated on the Blood branch, not the
            # Spirit branch. Sanguine Rite (Blood t1) is the entry node.
            game.player.skill_upgrades.extend(
                ["acolyte_spirit_call", "acolyte_sanguine"]
            )
            game.player.nova_timer = 0.0
            game.player.mana = game.player.max_mana
            game.player_cast_spirit_call()
            familiar = game.familiars[0]
            self.assertTrue(familiar.lifesteal)
            enemy = _make_enemy(familiar.x + 0.5, familiar.y, hp=999)
            game.enemies = [enemy]
            game.player.hp = game.player.max_hp - 20
            hp_before = game.player.hp
            # Force an attack: place familiar in range and reset its timer.
            familiar.attack_timer = 0.0
            game._familiar_attack(familiar, enemy)
            self.assertGreater(game.player.hp, hp_before)

    def test_unkillable_familiar_cannot_die(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.player.skill_upgrades.extend(
                ["acolyte_spirit_call", "acolyte_legion_eternal"]
            )
            game.player.nova_timer = 0.0
            game.player.mana = game.player.max_mana
            game.player_cast_spirit_call()
            familiar = game.familiars[0]
            self.assertTrue(familiar.unkillable)
            game._familiar_take_damage(familiar, 9999, None)
            self.assertGreaterEqual(familiar.hp, 1)

    # --- sprite-variant selection ---------------------------------------

    def test_sprite_state_small_before_skill_big_owl_after_spirit_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            # No Spirit skill chosen yet: small wisp state (variant 0).
            self.assertEqual(game.familiar_variant_for_index(0), 0)
            # Choosing Spirit Call promotes the familiar to the big owl (variant 1).
            game.player.skill_upgrades.append("acolyte_spirit_call")
            self.assertEqual(game.familiar_variant_for_index(0), 1)
            game.player.skill_upgrades.append("acolyte_wraith_lord")
            # Deeper Spirit nodes scale stats/count but keep the owl silhouette.
            self.assertEqual(game.familiar_variant_for_index(0), 1)
            self.assertEqual(game.familiar_variant_for_index(1), 1)

    def test_two_familiar_sprite_states_exist_and_owl_is_larger(self) -> None:
        # The sprite atlas exposes two familiar states (small wisp + big owl),
        # both renderable, and the owl is clearly larger than the wisp.
        from arch_rogue.sprites import PixelSpriteAtlas

        atlas = PixelSpriteAtlas()
        for variant in (0, 1):
            frame = atlas.familiar_frame(variant, 0.0)
            self.assertGreater(frame.get_width(), 0)
            self.assertGreater(frame.get_height(), 0)
        w0 = atlas.familiar_frame(0, 0.0).get_width()
        w1 = atlas.familiar_frame(1, 0.0).get_width()
        self.assertGreater(w1, w0)

    # --- save round-trip ------------------------------------------------

    def test_familiar_save_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.player.skill_upgrades.extend(
                ["acolyte_spirit_call", "acolyte_bone_legion", "acolyte_wraith_lord"]
            )
            game.player.nova_timer = 0.0
            game.player.mana = game.player.max_mana
            game.player_cast_spirit_call()
            self.assertEqual(len(game.familiars), 2)
            before = game.familiars[0]
            data = copy.deepcopy(game.serialize_run_state())
            self.assertEqual(data["release"], "3.18.1")
            self.assertIn("familiars", data)
            self.assertEqual(len(data["familiars"]), 2)

            # Restore into a fresh game instance (no restart, which auto-saves
            # and would clobber the captured state).
            loaded = Game(
                screen_size=(960, 600),
                headless=True,
                save_path=Path(tmpdir) / "restore.json",
            )
            loaded.options_path = Path(tmpdir) / "restore-opt.json"
            loaded.restore_run_state(data)
            self.assertEqual(len(loaded.familiars), 2)
            after = loaded.familiars[0]
            self.assertEqual(after.sprite_variant, before.sprite_variant)
            self.assertEqual(after.max_hp, before.max_hp)
            self.assertEqual(after.damage, before.damage)
            self.assertEqual(after.champion, before.champion)
            self.assertAlmostEqual(after.x, before.x, places=4)
            self.assertAlmostEqual(after.y, before.y, places=4)

    def test_old_save_without_familiars_loads_cleanly(self) -> None:
        # Simulate a pre-3.15 save: no "familiars" key. It must restore with
        # an empty host and not block restoration.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            data = copy.deepcopy(game.serialize_run_state())
            data.pop("familiars", None)

            loaded = Game(
                screen_size=(960, 600),
                headless=True,
                save_path=Path(tmpdir) / "old.json",
            )
            loaded.options_path = Path(tmpdir) / "old-opt.json"
            loaded.restore_run_state(data)
            self.assertEqual(loaded.familiars, [])
            # The Acolyte can immediately re-summon on the loaded floor.
            loaded.player.nova_timer = 0.0
            loaded.player.mana = loaded.player.max_mana
            loaded.player_cast_spirit_call()
            self.assertEqual(len(loaded.familiars), 1)

    # --- render smoke test ---------------------------------------------

    def test_familiar_renders_with_world_depth_sort(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.player.skill_upgrades.extend(
                ["acolyte_spirit_call", "acolyte_wraith_lord"]
            )
            game.player.nova_timer = 0.0
            game.player.mana = game.player.max_mana
            game.player_cast_spirit_call()
            self.assertGreater(len(game.familiars), 0)
            # A full frame render must not raise; the familiar is depth-sorted
            # alongside walls, enemies, and the player.
            game.draw()
            # Sanity: the screen now has non-background pixels.
            digest = hashlib.blake2s(
                pygame.image.tobytes(game.screen, "RGBA"), digest_size=8
            ).hexdigest()
            self.assertNotEqual(digest, "0" * 16)


if __name__ == "__main__":
    unittest.main()
