# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
#
# AI Provenance & Liability Notice:
# This repository contains code generated, assisted, or refactored by Artificial
# Intelligence models. Provided strictly "AS IS" under Apache 2.0 with no warranty
# of clean IP provenance or non-infringement; downstream users assume all legal
# and financial risk and should perform their own compliance audits.
#
# Familiar coverage: Acolyte Spirit Call and 4.1.21 Ranger Spirit Beast.
from __future__ import annotations

import copy
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame  # noqa: F401  (required to initialize pygame subsystems in tests)

from arch_rogue.constants import WALK_ANIM_RUNTIME_SCALE_FLOOR
from arch_rogue.content import ARCHETYPES, UNIQUE_ITEM_DEFINITIONS
from arch_rogue.dungeon import MAP_H, MAP_W
from arch_rogue.game import Game
from arch_rogue.models import Enemy, Familiar, Item, Projectile, Tile


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


class FamiliarTests(unittest.TestCase):
    def make_game(self, tmpdir, archetype_index=3, seed=3151) -> Game:
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

    # --- familiar class skills -----------------------------------------------

    def test_acolyte_class_skill_is_spirit_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            acolyte = self.make_game(tmpdir, archetype_index=3)
            self.assertEqual(acolyte.skill_names()[2], "Spirit Call")
            slots = acolyte.hud_action_slots()
            self.assertEqual(slots[2]["hotkey"], "3")
            self.assertEqual(slots[2]["label"], "Spirit Call")
            self.assertEqual(slots[2]["cost"], acolyte.class_skill_mana_cost())
            self.assertEqual(slots[2]["cooldown"], acolyte.class_skill_cooldown())

    def test_ranger_class_skill_is_spirit_beast(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ranger = self.make_game(tmpdir, archetype_index=4)
            self.assertEqual(ranger.skill_names()[2], "Spirit Beast")
            self.assertEqual(ranger.class_skill_kind(), "spirit_beast")
            slots = ranger.hud_action_slots()
            self.assertEqual(slots[2]["kind"], "spirit_beast")
            self.assertEqual(slots[2]["icon"], "spirit_beast")
            self.assertEqual(slots[2]["label"], "Spirit Beast")
            self.assertEqual(slots[2]["cost"], ranger.player.max_mana * 0.5)
            self.assertEqual(slots[2]["cooldown"], 60.0)

            ranger.player.class_skill_timer = 0.0
            ranger.player.mana = ranger.player.max_mana
            ranger.player_cast_class_skill()
            self.assertEqual(len(ranger.familiars), 1)
            self.assertEqual(ranger.familiars[0].kind, "spirit_beast")
            command_slot = ranger.hud_action_slots()[2]
            self.assertEqual(command_slot["cost"], 0)
            self.assertEqual(ranger.hud_action_slot_status(command_slot), "RETURN")
            self.assertTrue(ranger.hud_action_slot_ready(command_slot))

    def test_spirit_beast_equipment_bonus_refreshes_active_beast(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ranger = self.make_game(tmpdir, archetype_index=4)
            ranger.player.mana = ranger.player.max_mana
            ranger.player_cast_class_skill()
            beast = ranger.familiars[0]
            self.assertEqual((beast.max_hp, beast.damage), (60, 12))

            definition = next(
                item
                for item in UNIQUE_ITEM_DEFINITIONS
                if item.name == "Beastlord Harness"
            )
            self.assertEqual(definition.skill_bonus, "Spirit Beast bond")
            harness = ranger._make_unique_from_definition(
                definition, ranger.player.x, ranger.player.y
            )
            harness.unidentified = False
            ranger.player.inventory.append(harness)
            ranger.use_inventory_slot(len(ranger.player.inventory) - 1)

            self.assertTrue(ranger.equipment_class_skill_bonus())
            self.assertTrue(
                ranger.equipment_class_skill_bonus("Spirit Beast bond")
            )
            self.assertIs(ranger.familiars[0], beast)
            self.assertEqual((beast.max_hp, beast.damage), (72, 14))
            self.assertEqual(ranger.class_skill_mana_cost(), 24.0)
            self.assertEqual(ranger.class_skill_cooldown(), 60.0)

    # --- spawn / lifecycle ----------------------------------------------

    def test_spirit_beast_summons_and_persists_until_descent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=4)
            game.player.class_skill_timer = 0.0
            game.player.mana = game.player.max_mana
            starting_mana = game.player.mana
            game.player_cast_class_skill()

            self.assertEqual(len(game.familiars), 1)
            beast = game.familiars[0]
            self.assertEqual(beast.kind, "spirit_beast")
            self.assertEqual(beast.sprite_variant, 2)
            self.assertEqual(beast.command_mode, "attack")
            self.assertEqual(beast.max_hp, 60)
            self.assertEqual(beast.damage, 12)
            self.assertEqual(game.player.class_skill_timer, 60.0)
            self.assertEqual(game.player.mana, starting_mana * 0.5)
            self.assertTrue(
                any(
                    effect.kind == "spirit_beast_call"
                    for effect in game.impact_effects
                )
            )
            self.assertFalse(
                any(
                    effect.kind == "cast" and effect.archetype == "Ranger"
                    for effect in game.impact_effects
                )
            )
            game.draw()

            # A living beast is command-only even after replacement cooldown ends:
            # it is never recreated or healed, and its commands are free.
            beast.hp = 1
            game.player.class_skill_timer = 0.0
            game.player.mana = game.player.max_mana
            mana_before = game.player.mana
            game.player_cast_class_skill()
            self.assertIs(game.familiars[0], beast)
            self.assertEqual(beast.hp, 1)
            self.assertEqual(beast.command_mode, "follow")
            self.assertEqual(game.player.mana, mana_before)
            self.assertEqual(game.player.class_skill_timer, 0.0)

            game.descend_to_next_depth()
            self.assertEqual(game.familiars, [])

    def test_spirit_beast_replacement_waits_for_death_and_cooldown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=4)
            game.player.mana = game.player.max_mana
            game.player_cast_class_skill()
            dead_beast = game.familiars[0]
            dead_beast.hp = 0
            game.player.mana = game.player.max_mana
            game.player.mastery_tokens = 1
            self.assertTrue(game.choose_discipline("ranger_beast_bond"))
            self.assertEqual(dead_beast.hp, 0)
            self.assertIsNone(game.active_spirit_beast())

            game.player_cast_class_skill()
            self.assertIsNone(game.active_spirit_beast())
            self.assertIn(dead_beast, game.familiars)
            self.assertEqual(game.player.mana, game.player.max_mana)

            game.player.class_skill_timer = 0.0
            game.player_cast_class_skill()
            self.assertEqual(len(game.familiars), 1)
            self.assertIsNot(game.familiars[0], dead_beast)
            self.assertTrue(game.familiars[0].alive)
            self.assertEqual(game.player.class_skill_timer, 60.0)
            self.assertEqual(game.player.mana, game.player.max_mana * 0.5)

    def test_spirit_beast_spawn_uses_clear_line_connected_space(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=4)
            cx, cy = int(game.player.x), int(game.player.y)
            self.assertGreater(cx, 3)
            self.assertGreater(cy, 3)
            self.assertLess(cx, MAP_W - 4)
            self.assertLess(cy, MAP_H - 4)
            game.player.x = cx + 0.5
            game.player.y = cy + 0.5

            # Build a one-tile horizontal corridor. The preferred diagonal spawn
            # is a wall, so the summon must select another clear candidate.
            for tx in range(cx - 3, cx + 4):
                for ty in range(cy - 3, cy + 4):
                    game.dungeon.tiles[tx][ty] = Tile.WALL
                game.dungeon.tiles[tx][cy] = Tile.FLOOR

            game.player.mana = game.player.max_mana
            game.player_cast_class_skill()
            beast = game.active_spirit_beast()
            self.assertIsNotNone(beast)
            assert beast is not None
            self.assertFalse(
                game.dungeon.blocked_for_radius(
                    beast.x, beast.y, game.SPIRIT_BEAST_COLLISION_RADIUS
                )
            )
            self.assertTrue(
                game.dungeon.line_of_sight(
                    game.player.x, game.player.y, beast.x, beast.y
                )
            )
            self.assertGreaterEqual(
                (beast.x - game.player.x) ** 2 + (beast.y - game.player.y) ** 2,
                0.45**2,
            )

    def test_spirit_beast_does_not_summon_or_spend_inside_blocked_space(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=4)
            cx, cy = int(game.player.x), int(game.player.y)
            game.player.x = cx + 0.5
            game.player.y = cy + 0.5
            for tx in range(cx - 3, cx + 4):
                for ty in range(cy - 3, cy + 4):
                    game.dungeon.tiles[tx][ty] = Tile.WALL
            game.dungeon.tiles[cx][cy] = Tile.FLOOR
            game.player.mana = game.player.max_mana
            mana_before = game.player.mana

            game.player_cast_class_skill()

            self.assertIsNone(game.active_spirit_beast())
            self.assertEqual(game.player.mana, mana_before)
            self.assertEqual(game.player.class_skill_timer, 0.0)

    def test_spirit_beast_casts_alternate_return_and_nearest_attack(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=4)
            game.player.mana = game.player.max_mana
            game.player_cast_class_skill()
            beast = game.familiars[0]
            px, py = game.player.x, game.player.y
            cx, cy = int(px), int(py)
            for tx in range(cx - 1, cx + 6):
                for ty in range(cy - 1, cy + 2):
                    game.dungeon.tiles[tx][ty] = Tile.FLOOR
            beast.x, beast.y = px + 3.0, py
            near = _make_enemy(px + 3.6, py, hp=300)
            far = _make_enemy(px + 5.0, py, hp=300)
            game.enemies = [far, near]
            mana_before = game.player.mana
            timer_before = game.player.class_skill_timer

            # First press after summoning recalls the same living beast. It ignores
            # an adjacent enemy while closing to the tighter return distance.
            distance_before = abs(beast.x - px)
            game.player_cast_class_skill()
            self.assertEqual(beast.command_mode, "follow")
            self.assertEqual(game.spirit_beast_next_command(), "ATTACK")
            self.assertEqual(game.player.mana, mana_before)
            self.assertEqual(game.player.class_skill_timer, timer_before)
            game.update_familiars(0.1)
            self.assertLess(abs(beast.x - px), distance_before)
            self.assertEqual(near.hp, near.max_hp)
            self.assertEqual(far.hp, far.max_hp)
            # Commands remain available with no mana. The next free press releases
            # attack mode and nearest-visible logic selects the closer target.
            game.player.mana = 0.0
            command_slot = game.hud_action_slots()[2]
            self.assertEqual(command_slot["cost"], 0)
            self.assertEqual(game.hud_action_slot_status(command_slot), "ATTACK")
            self.assertTrue(game.hud_action_slot_ready(command_slot))
            game.player_cast_class_skill()
            self.assertEqual(beast.command_mode, "attack")
            self.assertEqual(game.spirit_beast_next_command(), "RETURN")
            beast.attack_timer = 0.0
            game.update_familiars(0.01)
            self.assertLess(near.hp, near.max_hp)
            self.assertEqual(far.hp, far.max_hp)
            self.assertEqual(game.player.mana, 0.0)
            self.assertEqual(game.player.class_skill_timer, timer_before)

    def test_ranger_can_pet_nearby_spirit_beast_with_two_second_cooldown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=4)
            game.player.mana = game.player.max_mana
            game.player_cast_class_skill()
            beast = game.familiars[0]
            beast.x = game.player.x + 0.8
            beast.y = game.player.y
            beast.hp = beast.max_hp - 3
            beast.command_mode = "follow"
            game.items.clear()
            game.shrines.clear()
            game.secrets.clear()
            game.shopkeepers.clear()
            game.story_guests.clear()
            mana_before = game.player.mana
            class_timer_before = game.player.class_skill_timer

            # Petting is now advertised as a first-class interact action
            # (tappable on mobile), so the contextual hint surfaces it.
            hint = game.current_interaction_hint()
            self.assertEqual(hint[1] if hint else "", "Pet Spirit Beast")
            indicator_rect = pygame.Rect(100, 100, 100, 100)
            self.assertTrue(
                game.draw_spirit_beast_pet_indicator(beast, indicator_rect)
            )
            game.items.append(
                Item(
                    "Test Tonic",
                    "potion",
                    x=game.player.x,
                    y=game.player.y,
                )
            )
            self.assertFalse(
                game.draw_spirit_beast_pet_indicator(beast, indicator_rect)
            )
            game.items.clear()
            self.assertTrue(
                game.draw_spirit_beast_pet_indicator(beast, indicator_rect)
            )

            game.interact()

            self.assertEqual(beast.hp, beast.max_hp - 1)
            self.assertEqual(game.SPIRIT_BEAST_PET_HEAL, 2)
            self.assertEqual(beast.pet_cooldown, 2.0)
            self.assertEqual(beast.pet_anim_timer, 0.8)
            self.assertEqual(beast.attack_anim_timer, 0.0)
            self.assertEqual(game.floaters[-1].text, "+2")
            self.assertFalse(
                game.draw_spirit_beast_pet_indicator(beast, indicator_rect)
            )
            self.assertEqual(game.player_visual_state(game.player), "pet")
            self.assertEqual(beast.command_mode, "follow")
            self.assertIs(game.familiars[0], beast)
            self.assertEqual(game.player.mana, mana_before)
            self.assertEqual(game.player.class_skill_timer, class_timer_before)
            self.assertAlmostEqual(game.player.facing_x, 1.0)
            self.assertAlmostEqual(beast.facing_x, -1.0)

            # Repeated interaction during the lockout cannot heal or restart clips.
            game.interact()
            self.assertEqual(beast.hp, beast.max_hp - 1)
            self.assertEqual(beast.pet_cooldown, 2.0)
            self.assertEqual(beast.pet_anim_timer, 0.8)
            self.assertIsNone(game.nearby_pettable_spirit_beast())

            game.update_familiars(1.99)
            self.assertGreater(beast.pet_cooldown, 0.0)
            game.update_familiars(0.01)
            self.assertEqual(beast.pet_cooldown, 0.0)
            self.assertIs(game.nearby_pettable_spirit_beast(), beast)
            self.assertTrue(
                game.draw_spirit_beast_pet_indicator(beast, indicator_rect)
            )
            game.interact()
            self.assertEqual(beast.hp, beast.max_hp)

            # Full-health affection is still allowed and remains clamped.
            game.update_familiars(2.0)
            game.interact()
            self.assertEqual(beast.hp, beast.max_hp)
            self.assertEqual(beast.pet_cooldown, 2.0)
            self.assertEqual(game.floaters[-1].text, "+2")

    def test_petting_bonus_doubles_per_beast_discipline_degree(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=4)
            self.assertEqual(game.spirit_beast_pet_heal(), 2)

            game.player.skill_upgrades.append("ranger_beast_bond")
            self.assertEqual(game.spirit_beast_pet_heal(), 4)

            game.player.skill_upgrades.append("ranger_pack_tactics")
            self.assertEqual(game.spirit_beast_pet_heal(), 8)

            game.player.skill_upgrades.append("ranger_alpha")
            self.assertEqual(game.spirit_beast_pet_heal(), 16)

            game.player.skill_upgrades.append("ranger_spirit_companion")
            self.assertEqual(game.spirit_beast_pet_heal(), 32)

            game.player.skill_upgrades.append("ranger_primal_lord")
            self.assertEqual(game.spirit_beast_pet_heal(), 64)

            # Non-Beast disciplines do not inflate the petting bonus.
            game.player.skill_upgrades.append("ranger_survival")
            game.player.skill_upgrades.append("ranger_camouflage")
            self.assertEqual(game.spirit_beast_pet_heal(), 64)

            # An actual pet at degree 5 heals 64 and the floater reflects it.
            game.player.mana = game.player.max_mana
            game.player.class_skill_timer = 0.0
            game.player_cast_spirit_beast()
            beast = game.familiars[0]
            beast.hp = 1
            beast.x = game.player.x + 0.8
            beast.y = game.player.y
            beast.pet_cooldown = 0.0
            game.items.clear()
            game.shrines.clear()
            game.secrets.clear()
            game.shopkeepers.clear()
            game.story_guests.clear()
            game.interact()
            self.assertEqual(beast.hp, 1 + 64)
            self.assertEqual(game.floaters[-1].text, "+64")

    def test_only_ranger_can_pet_a_living_spirit_beast_in_range(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            acolyte = self.make_game(tmpdir, archetype_index=3)
            beast = Familiar(
                x=acolyte.player.x + 0.8,
                y=acolyte.player.y,
                max_hp=60,
                hp=59,
                damage=12,
                speed=3.55,
                attack_range=1.25,
                attack_cooldown=0.86,
                sprite_variant=2,
                kind="spirit_beast",
            )
            acolyte.familiars = [beast]
            self.assertIsNone(acolyte.nearby_pettable_spirit_beast())
            self.assertFalse(acolyte.pet_spirit_beast(beast))
            self.assertEqual(beast.hp, 59)
            self.assertEqual(beast.pet_cooldown, 0.0)

            acolyte.player.class_name = "Ranger"
            beast.hp = 0
            self.assertIsNone(acolyte.nearby_pettable_spirit_beast())
            self.assertFalse(acolyte.pet_spirit_beast(beast))
            beast.hp = 59
            beast.x = acolyte.player.x + acolyte.SPIRIT_BEAST_PET_RANGE
            self.assertIsNone(acolyte.nearby_pettable_spirit_beast())
            self.assertFalse(acolyte.pet_spirit_beast(beast))

    def test_pet_animation_suppresses_spirit_beast_ai_and_drives_render_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=4)
            game.player.mana = game.player.max_mana
            game.player_cast_class_skill()
            beast = game.familiars[0]
            beast.x = game.player.x + 0.8
            beast.y = game.player.y
            enemy = _make_enemy(beast.x + 0.4, beast.y, hp=200)
            game.enemies = [enemy]
            self.assertTrue(game.pet_spirit_beast(beast))

            observed: list[dict[str, object]] = []
            familiar_visual = game.sprites.familiar_visual

            def record_visual(variant: int, clip_time: float, **kwargs):
                observed.append(kwargs)
                return familiar_visual(variant, clip_time, **kwargs)

            game.sprites.familiar_visual = record_visual  # type: ignore[method-assign]
            try:
                game.draw_familiar(beast)
            finally:
                game.sprites.familiar_visual = familiar_visual  # type: ignore[method-assign]

            self.assertEqual(len(observed), 1)
            self.assertTrue(observed[0]["petting"])
            self.assertFalse(observed[0]["attacking"])
            self.assertEqual(observed[0]["pet_progress"], 0.0)

            game.update_familiars(0.79)
            self.assertEqual(enemy.hp, enemy.max_hp)
            self.assertFalse(beast.moving)
            self.assertGreater(beast.pet_anim_timer, 0.0)
            game.update_familiars(0.02)
            self.assertLess(enemy.hp, enemy.max_hp)
            self.assertEqual(beast.pet_anim_timer, 0.0)

    def test_spirit_call_spawns_a_familiar_and_persists_until_descent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.assertEqual(game.familiars, [])
            game.player.class_skill_timer = 0.0
            game.player.mana = game.player.max_mana
            game.player_cast_spirit_call()
            self.assertEqual(len(game.familiars), 1)
            familiar = game.familiars[0]
            self.assertIsInstance(familiar, Familiar)
            self.assertGreater(familiar.max_hp, 0)
            self.assertGreater(familiar.damage, 0)
            # Casting sets the class-skill cooldown.
            self.assertGreater(game.player.class_skill_timer, 0.0)
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
            game.player.class_skill_timer = 0.0
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
            game.player.class_skill_timer = 0.0
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
            game.player.class_skill_timer = 0.0
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
            game.player.class_skill_timer = 0.0
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

    def test_spirit_beast_tracks_slow_player_without_stop_start_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=4)
            game.player.class_skill_timer = 0.0
            game.player.mana = game.player.max_mana
            game.player_cast_class_skill()
            beast = game.familiars[0]
            game.enemies = []

            game.player.x = float(int(game.player.x)) + 0.5
            game.player.y = float(int(game.player.y)) + 0.5
            cx, cy = int(game.player.x), int(game.player.y)
            for tx in range(cx - 3, cx + 2):
                for ty in range(cy - 1, cy + 2):
                    game.dungeon.tiles[tx][ty] = Tile.FLOOR
            beast.x = game.player.x - game.SPIRIT_BEAST_FOLLOW_DISTANCE
            beast.y = game.player.y
            beast.anim_time = 0.0

            slow_step = 0.02
            for _ in range(6):
                game.player.x += slow_step
                before_x = beast.x
                game.update_familiars(0.05)
                self.assertTrue(beast.moving)
                self.assertAlmostEqual(beast.x - before_x, slow_step, places=5)

            self.assertAlmostEqual(
                beast.anim_time,
                6 * 0.05 * WALK_ANIM_RUNTIME_SCALE_FLOOR,
                places=5,
            )

    def test_familiar_takes_damage_from_enemy_projectiles(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.player.class_skill_timer = 0.0
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

    def test_familiar_cannot_perceive_or_attack_through_walls(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=4)
            game.player.class_skill_timer = 0.0
            game.player.mana = game.player.max_mana
            game.player_cast_class_skill()
            beast = game.familiars[0]
            dungeon = game.dungeon
            cx, cy = int(game.player.x), int(game.player.y)
            self.assertGreater(MAP_W - cx, 6)
            beast.x, beast.y = cx + 0.5, cy + 0.5
            beast.attack_range = 4.0
            dungeon.tiles[cx][cy] = Tile.FLOOR
            dungeon.tiles[cx + 3][cy] = Tile.FLOOR
            dungeon.tiles[cx + 1][cy] = Tile.WALL
            dungeon.tiles[cx + 2][cy] = Tile.WALL
            enemy = _make_enemy(cx + 3.5, cy + 0.5, hp=200)
            game.enemies = [enemy]

            game.update_familiars(0.1)
            self.assertEqual(enemy.hp, enemy.max_hp)
            self.assertEqual(beast.attack_timer, 0.0)

            dungeon.tiles[cx + 1][cy] = Tile.FLOOR
            dungeon.tiles[cx + 2][cy] = Tile.FLOOR
            game.update_familiars(0.1)
            self.assertLess(enemy.hp, enemy.max_hp)
            self.assertGreater(beast.attack_timer, 0.0)
            self.assertGreater(beast.attack_anim_timer, 0.0)

    def test_familiar_cannot_attack_through_closed_diagonal_corner(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=4)
            game.player.class_skill_timer = 0.0
            game.player.mana = game.player.max_mana
            game.player_cast_class_skill()
            beast = game.familiars[0]
            dungeon = game.dungeon
            cx, cy = int(game.player.x), int(game.player.y)
            self.assertGreater(MAP_W - cx, 3)
            self.assertGreater(MAP_H - cy, 3)
            beast.x, beast.y = cx + 0.5, cy + 0.5
            beast.attack_range = 2.0
            dungeon.tiles[cx][cy] = Tile.FLOOR
            dungeon.tiles[cx + 1][cy + 1] = Tile.FLOOR
            dungeon.tiles[cx + 1][cy] = Tile.WALL
            dungeon.tiles[cx][cy + 1] = Tile.WALL
            enemy = _make_enemy(cx + 1.5, cy + 1.5, hp=200)
            game.enemies = [enemy]

            game.update_familiars(0.1)
            self.assertEqual(enemy.hp, enemy.max_hp)
            self.assertEqual(beast.attack_timer, 0.0)

            dungeon.tiles[cx + 1][cy] = Tile.FLOOR
            game.update_familiars(0.1)
            self.assertLess(enemy.hp, enemy.max_hp)

    def test_acolyte_spirit_familiar_cannot_perceive_or_attack_through_walls(self) -> None:
        # 4.2 verification: the Acolyte's Spirit Call familiar also runs through
        # the shared ``update_familiars`` LOS check, so it cannot see or bite
        # enemies through dungeon walls. This is the same contract as the
        # Ranger Spirit Beast wall test above, exercised on the Acolyte's owl.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=3)
            game.player.class_skill_timer = 0.0
            game.player.mana = game.player.max_mana
            game.player_cast_spirit_call()
            familiar = game.familiars[0]
            dungeon = game.dungeon
            cx, cy = int(game.player.x), int(game.player.y)
            self.assertGreater(MAP_W - cx, 6)
            familiar.x, familiar.y = cx + 0.5, cy + 0.5
            familiar.attack_range = 4.0
            dungeon.tiles[cx][cy] = Tile.FLOOR
            dungeon.tiles[cx + 3][cy] = Tile.FLOOR
            dungeon.tiles[cx + 1][cy] = Tile.WALL
            dungeon.tiles[cx + 2][cy] = Tile.WALL
            enemy = _make_enemy(cx + 3.5, cy + 0.5, hp=200)
            game.enemies = [enemy]

            game.update_familiars(0.1)
            self.assertEqual(enemy.hp, enemy.max_hp)
            self.assertEqual(familiar.attack_timer, 0.0)

            # Clearing the walls restores perception and the familiar bites.
            dungeon.tiles[cx + 1][cy] = Tile.FLOOR
            dungeon.tiles[cx + 2][cy] = Tile.FLOOR
            game.update_familiars(0.1)
            self.assertLess(enemy.hp, enemy.max_hp)
            self.assertGreater(familiar.attack_timer, 0.0)

    # --- discipline scaling -----------------------------------------

    def test_ranger_beast_path_scales_and_refreshes_active_beast(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=4)
            self.assertEqual(game.spirit_beast_stats(), (60, 12, 3.55, 0.86))
            game.player.class_skill_timer = 0.0
            game.player.mana = game.player.max_mana
            game.player_cast_class_skill()
            beast = game.familiars[0]
            game.player.mastery_tokens = 5

            expected = (
                ("ranger_beast_bond", (74, 14, 3.55, 0.86)),
                ("ranger_pack_tactics", (82, 16, 3.55, 0.78)),
                ("ranger_alpha", (100, 19, 3.70, 0.78)),
                ("ranger_spirit_companion", (114, 22, 3.80, 0.73)),
                ("ranger_primal_lord", (138, 26, 3.90, 0.66)),
            )
            for key, stats in expected:
                with self.subTest(discipline=key):
                    previous_max_hp = beast.max_hp
                    self.assertTrue(game.choose_discipline(key))
                    actual = game.spirit_beast_stats()
                    self.assertEqual(actual[:2], stats[:2])
                    self.assertAlmostEqual(actual[2], stats[2], places=4)
                    self.assertAlmostEqual(actual[3], stats[3], places=4)
                    self.assertEqual(beast.max_hp, stats[0])
                    self.assertGreater(beast.max_hp, previous_max_hp)
                    self.assertEqual(beast.damage, stats[1])
                    self.assertAlmostEqual(beast.speed, stats[2], places=4)
                    self.assertAlmostEqual(beast.attack_cooldown, stats[3], places=4)
            self.assertTrue(beast.champion)
            self.assertEqual(game.familiar_damage_type(beast), "arcane")

    def test_spirit_beast_combat_bonuses_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=4)
            game.player.skill_upgrades.extend(
                [
                    "ranger_beast_bond",
                    "ranger_pack_tactics",
                    "ranger_alpha",
                    "ranger_spirit_companion",
                    "ranger_primal_lord",
                ]
            )
            game.player.class_skill_timer = 0.0
            game.player.mana = game.player.max_mana
            game.player_cast_class_skill()
            beast = game.familiars[0]
            enemy = _make_enemy(beast.x + 0.5, beast.y, hp=1000)
            enemy.elite_modifier = "Runed"
            enemy.statuses["snared"] = 1.0
            game.enemies = [enemy]
            start_x = enemy.x

            game._familiar_attack(beast, enemy)

            self.assertLessEqual(enemy.hp, 1000 - beast.damage)
            self.assertGreater(enemy.x, start_x)
            self.assertGreater(beast.attack_anim_timer, 0.0)

    def test_spirit_branch_scales_hp_damage_count_and_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.player.class_skill_timer = 0.0
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
            game.player.class_skill_timer = 0.0
            game.player.mana = game.player.max_mana

            # Spirit Call node: +HP/+damage and medium sprite (variant 1).
            game.player.skill_upgrades.append("acolyte_spirit_call")
            game.player_cast_spirit_call()
            tier1 = game.familiars[0]
            self.assertGreater(tier1.max_hp, base_hp)
            self.assertGreater(tier1.damage, base_damage)
            self.assertEqual(tier1.sprite_variant, 1)
            game.familiars = []
            game.player.class_skill_timer = 0.0
            game.player.mana = game.player.max_mana

            # Owl Companion: more HP (lifesteal moved to the Blood path in
            # 3.18.4, so the flag must be off without Blood investment).
            game.player.skill_upgrades.append("acolyte_wraith_host")
            game.player_cast_spirit_call()
            self.assertFalse(game.familiars[0].lifesteal)
            self.assertGreater(game.familiars[0].max_hp, tier1.max_hp)
            game.familiars = []
            game.player.class_skill_timer = 0.0
            game.player.mana = game.player.max_mana

            # Twin Owls: +1 familiar (count = 2) and more damage.
            game.player.skill_upgrades.append("acolyte_bone_legion")
            game.player_cast_spirit_call()
            self.assertEqual(game.familiar_max_count(), 2)
            self.assertEqual(len(game.familiars), 2)
            self.assertTrue(all(f.sprite_variant == 1 for f in game.familiars))
            game.familiars = []
            game.player.class_skill_timer = 0.0
            game.player.mana = game.player.max_mana

            # Owl Lord: lead familiar is a champion (taunts); the sprite
            # stays the big owl (variant 1) once Spirit Call is chosen.
            game.player.skill_upgrades.append("acolyte_wraith_lord")
            game.player_cast_spirit_call()
            self.assertTrue(game.familiars[0].champion)
            self.assertEqual(game.familiars[0].sprite_variant, 1)
            self.assertGreater(game.familiars[0].max_hp, tier1.max_hp)
            game.familiars = []
            game.player.class_skill_timer = 0.0
            game.player.mana = game.player.max_mana

            # Eternal Owls: +1 familiar (count = 3) and unkillable host.
            game.player.skill_upgrades.append("acolyte_legion_eternal")
            game.player_cast_spirit_call()
            self.assertEqual(game.familiar_max_count(), 3)
            self.assertEqual(len(game.familiars), 3)
            self.assertTrue(all(f.sprite_variant == 1 for f in game.familiars))
            self.assertTrue(all(f.unkillable for f in game.familiars))

    def test_lifesteal_familiar_heals_acolyte_on_hit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            # 3.18.4: familiar lifesteal is gated on the Blood path, not the
            # Spirit path. Sanguine Rite (Blood Degree 1) is the entry node.
            game.player.skill_upgrades.extend(
                ["acolyte_spirit_call", "acolyte_sanguine"]
            )
            game.player.class_skill_timer = 0.0
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
            game.player.class_skill_timer = 0.0
            game.player.mana = game.player.max_mana
            game.player_cast_spirit_call()
            familiar = game.familiars[0]
            self.assertTrue(familiar.unkillable)
            game._familiar_take_damage(familiar, 9999, None)
            self.assertGreaterEqual(familiar.hp, 1)

    # --- sprite variants -------------------------------------------------


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

    def test_pet_action_has_non_looping_legacy_ranger_and_beast_fallbacks(self) -> None:
        from arch_rogue.sprite_assets import SpriteAtlas

        atlas = SpriteAtlas(legacy_graphics=True)
        ranger_frames = atlas.legacy.player_animation_frames["Ranger"]["pet"]
        self.assertEqual(len(ranger_frames), 8)
        ranger_midpoint = atlas.player_visual(
            "Ranger",
            "pet",
            99.0,
            99.0,
            action_time=0.4,
            action_progress=0.5,
        )
        self.assertFalse(ranger_midpoint.is_asset)
        self.assertIs(ranger_midpoint.surface, ranger_frames[4])

        beast_frames = atlas.legacy.spirit_beast_pet_animation_frames
        self.assertEqual(len(beast_frames), 8)
        beast_midpoint = atlas.familiar_visual(
            2,
            0.4,
            direction="south",
            moving=True,
            kind="spirit_beast",
            petting=True,
            pet_progress=0.5,
            attacking=True,
            attack_progress=0.5,
        )
        self.assertFalse(beast_midpoint.is_asset)
        self.assertEqual(beast_midpoint.key[-1], "pet")
        self.assertIs(beast_midpoint.surface, beast_frames[4])

    # --- save round-trip ------------------------------------------------

    def test_additive_familiar_fields_preserve_legacy_positional_arguments(self) -> None:
        familiar = Familiar(
            1.0,
            2.0,
            20,
            19,
            6,
            3.2,
            1.25,
            0.85,
            1,
            True,
            False,
            True,
            0.3,
            0.4,
            True,
            -1.0,
            0.0,
            -1.0,
            0.0,
        )
        self.assertEqual(familiar.sprite_variant, 1)
        self.assertTrue(familiar.lifesteal)
        self.assertFalse(familiar.unkillable)
        self.assertTrue(familiar.champion)
        self.assertEqual(familiar.attack_timer, 0.3)
        self.assertEqual(familiar.anim_time, 0.4)
        self.assertTrue(familiar.moving)
        self.assertEqual((familiar.facing_x, familiar.facing_y), (-1.0, 0.0))
        self.assertEqual(familiar.kind, "spirit")
        self.assertEqual(familiar.attack_anim_timer, 0.0)
        self.assertEqual(familiar.command_mode, "attack")
        self.assertEqual(familiar.pet_cooldown, 0.0)
        self.assertEqual(familiar.pet_anim_timer, 0.0)

    def test_familiar_save_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.player.skill_upgrades.extend(
                ["acolyte_spirit_call", "acolyte_bone_legion", "acolyte_wraith_lord"]
            )
            game.player.class_skill_timer = 0.0
            game.player.mana = game.player.max_mana
            game.player_cast_spirit_call()
            self.assertEqual(len(game.familiars), 2)
            before = game.familiars[0]
            data = copy.deepcopy(game.serialize_run_state())
            self.assertIn("familiars", data)
            self.assertEqual(len(data["familiars"]), 2)
            self.assertEqual(data["familiars"][0]["kind"], "spirit")
            # Simulate a pre-beast familiar payload; missing kind must retain the
            # legacy Acolyte spirit behavior.
            data["familiars"][0].pop("kind")

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
            self.assertEqual(after.kind, "spirit")
            self.assertEqual(after.max_hp, before.max_hp)
            self.assertEqual(after.damage, before.damage)
            self.assertEqual(after.champion, before.champion)
            self.assertAlmostEqual(after.x, before.x, places=4)
            self.assertAlmostEqual(after.y, before.y, places=4)

    def test_spirit_beast_save_round_trip_preserves_kind_and_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=4)
            game.player.skill_upgrades.append("ranger_beast_bond")
            game.player.class_skill_timer = 0.0
            game.player.mana = game.player.max_mana
            game.player_cast_class_skill()
            game.player_cast_class_skill()  # first living-beast command = return
            game.familiars[0].pet_cooldown = 1.5
            game.familiars[0].pet_anim_timer = 0.4
            data = copy.deepcopy(game.serialize_run_state())
            self.assertEqual(data["familiars"][0]["kind"], "spirit_beast")
            self.assertEqual(data["familiars"][0]["command_mode"], "follow")
            self.assertNotIn("pet_cooldown", data["familiars"][0])
            self.assertNotIn("pet_anim_timer", data["familiars"][0])

            loaded = Game(
                screen_size=(960, 600),
                headless=True,
                save_path=Path(tmpdir) / "beast-restore.json",
            )
            loaded.options_path = Path(tmpdir) / "beast-restore-opt.json"
            loaded.restore_run_state(data)
            self.assertEqual(len(loaded.familiars), 1)
            self.assertEqual(loaded.familiars[0].kind, "spirit_beast")
            self.assertEqual(loaded.familiars[0].sprite_variant, 2)
            self.assertEqual(loaded.familiars[0].max_hp, 74)
            self.assertEqual(loaded.familiars[0].command_mode, "follow")
            self.assertEqual(loaded.familiars[0].pet_cooldown, 0.0)
            self.assertEqual(loaded.familiars[0].pet_anim_timer, 0.0)

            legacy_data = copy.deepcopy(data)
            legacy_data["familiars"][0].pop("command_mode")
            legacy = Game(
                screen_size=(960, 600),
                headless=True,
                save_path=Path(tmpdir) / "legacy-beast-restore.json",
            )
            legacy.options_path = Path(tmpdir) / "legacy-beast-restore-opt.json"
            legacy.restore_run_state(legacy_data)
            self.assertEqual(legacy.familiars[0].command_mode, "attack")

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
            loaded.player.class_skill_timer = 0.0
            loaded.player.mana = loaded.player.max_mana
            loaded.player_cast_spirit_call()
            self.assertEqual(len(loaded.familiars), 1)

    # --- render smoke test ---------------------------------------------

    def test_spirit_beast_walk_render_uses_local_locomotion_phase(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=4)
            game.player.class_skill_timer = 0.0
            game.player.mana = game.player.max_mana
            game.player_cast_class_skill()
            beast = game.familiars[0]
            beast.moving = True
            beast.anim_time = 0.137
            game.elapsed = 42.0

            observed_times: list[float] = []
            familiar_visual = game.sprites.familiar_visual

            def record_visual(variant: int, clip_time: float, **kwargs):
                observed_times.append(clip_time)
                return familiar_visual(variant, clip_time, **kwargs)

            game.sprites.familiar_visual = record_visual  # type: ignore[method-assign]
            try:
                game.draw_familiar(beast)
            finally:
                game.sprites.familiar_visual = familiar_visual  # type: ignore[method-assign]

            self.assertEqual(observed_times, [beast.anim_time])

    def test_familiar_renders_with_world_depth_sort(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.player.skill_upgrades.extend(
                ["acolyte_spirit_call", "acolyte_wraith_lord"]
            )
            game.player.class_skill_timer = 0.0
            game.player.mana = game.player.max_mana
            game.player_cast_spirit_call()
            self.assertGreater(len(game.familiars), 0)
            # Record the active world-render path while preserving the real draw.
            drawn: list[Familiar] = []
            draw_familiar = game.draw_familiar

            def record_familiar(familiar: Familiar) -> None:
                drawn.append(familiar)
                draw_familiar(familiar)

            game.draw_familiar = record_familiar  # type: ignore[method-assign]
            game.draw()
            self.assertEqual(drawn, game.familiars)