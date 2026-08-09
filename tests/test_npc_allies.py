# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
#
# AI Provenance & Liability Notice:
# This repository contains code generated, assisted, or refactored by Artificial
# Intelligence models. Provided strictly "AS IS" under Apache 2.0 with no warranty
# of clean IP provenance or non-infringement; downstream users assume all legal
# and financial risk and should perform their own compliance audits.
#
# 4.8.10 "Glory to the machine" Part B: friendly NPCs join the fight.
from __future__ import annotations

import json
import math
import os
import random
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from arch_rogue.content import ARCHETYPES
from arch_rogue.dungeon import MAP_H, MAP_W, Dungeon
from arch_rogue.game import Game
from arch_rogue.models import (
    Enemy,
    IdleNpc,
    Projectile,
    Room,
    SpecialRoom,
    StoryGuest,
    Tile,
)
from arch_rogue.net import sync
from arch_rogue.save_system import _TRANSIENT_NPC_FIELDS


def _make_enemy(
    x: float,
    y: float,
    *,
    kind: str = "melee",
    hp: int = 200,
    attack_range: float = 1.2,
    aggro_range: float = 20.0,
) -> Enemy:
    return Enemy(
        "Test Dummy",
        kind,
        x,
        y,
        hp,
        hp,
        2.0,
        6,
        12,
        attack_range,
        1.0,
        aggro_range=aggro_range,
    )


class NpcAlliesTestCase(unittest.TestCase):
    ROOM = Room(20, 20, 12, 12)

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.game_count = 0

    def make_game(self, rng_seed: int = 4310) -> Game:
        self.game_count += 1
        game = Game(
            screen_size=(820, 540),
            headless=True,
            save_path=Path(self.tmpdir.name) / f"run-{self.game_count}.json",
        )
        game.options_path = (
            Path(self.tmpdir.name) / f"options-{self.game_count}.json"
        )
        game.rng.seed(4300)
        game.restart(ARCHETYPES[0])
        if game.story_intro_pending:
            self.assertTrue(game.choose_story_relic_path(0))
        game.active_cutscene = None

        game.dungeon = self.make_dungeon()
        game.enemies = []
        game.items = []
        game.traps = []
        game.shrines = []
        game.secrets = []
        game.shopkeepers = []
        game.story_guests = []
        game.familiars = []
        game.projectiles = []
        game.idle_npcs = [
            IdleNpc(28.5, 25.5, kind="bar", name="Tovin", role="Wayfarer"),
            IdleNpc(
                25.5,
                28.5,
                kind="bar_dancer",
                name="Bar Dancer",
                role="Tavern Reveler",
                color=(224, 126, 72),
            ),
            IdleNpc(
                22.5,
                25.5,
                kind="garden_frog",
                name="Pip Croakleaf",
                role="Garden Dancer",
                color=(116, 190, 92),
            ),
        ]
        game.player.x = 4.5
        game.player.y = 4.5
        game.current_depth = 4
        game.run_music_seed = 0
        game.elapsed = 0.0
        game.story_intro_pending = False
        game.inventory_open = False
        game.character_menu_open = False
        game.shop_open = False
        game.active_shopkeeper = None
        game.reset_friendly_npc_runtime()
        game.rng.seed(rng_seed)
        return game

    def make_dungeon(self) -> Dungeon:
        dungeon = object.__new__(Dungeon)
        dungeon.rng = random.Random(991)
        dungeon.boss_arena = False
        dungeon.guest_room = False
        dungeon.rooms = [self.ROOM]
        dungeon.special_rooms = []
        dungeon.solid_furnishing_tiles = frozenset()
        dungeon.solid_furnishing_boxes = ()
        dungeon.stairs = (self.ROOM.x + 1, self.ROOM.y + 1)
        dungeon.shop_room_index = None
        dungeon.guest_room_index = None
        dungeon.tiles = [
            [Tile.WALL for _ in range(MAP_H)] for _ in range(MAP_W)
        ]
        for x in range(self.ROOM.x + 1, self.ROOM.x + self.ROOM.w - 1):
            for y in range(self.ROOM.y + 1, self.ROOM.y + self.ROOM.h - 1):
                dungeon.tiles[x][y] = Tile.FLOOR
        return dungeon

    def bar_npc(self, game: Game) -> IdleNpc:
        return next(npc for npc in game.idle_npcs if npc.kind == "bar")

    def frog_npc(self, game: Game) -> IdleNpc:
        return next(
            npc for npc in game.idle_npcs if npc.kind == "garden_frog"
        )

    # ------------------------------------------------------------------
    # B1 — combat model, stats, and persistence.
    # ------------------------------------------------------------------

    def test_old_save_dict_loads_pacifist(self) -> None:
        game = self.make_game()
        npc = game.idle_npc_from_dict(
            {
                "x": 5.0,
                "y": 6.0,
                "kind": "bar",
                "name": "Tovin",
                "role": "Wayfarer",
                "color": [214, 176, 120],
            }
        )
        self.assertFalse(npc.aggressive)
        self.assertEqual(npc.max_hp, 0)
        self.assertEqual(npc.greeter_id, "")
        self.assertTrue(npc.alive)

    def test_transient_fields_stay_out_of_the_save_dict(self) -> None:
        game = self.make_game()
        payload = game.idle_npc_to_dict(self.bar_npc(game))
        self.assertTrue(_TRANSIENT_NPC_FIELDS.isdisjoint(payload))

    def test_greeted_ally_survives_save_load_round_trip(self) -> None:
        game = self.make_game()
        npc = self.bar_npc(game)
        game.player.x, game.player.y = npc.x - 1.0, npc.y
        self.assertTrue(game.greet_idle_npc(npc))
        npc.attack_timer = 0.7
        data = json.loads(json.dumps(game.serialize_run_state()))

        loaded = self.make_game()
        loaded.restore_run_state(data)
        restored = next(n for n in loaded.idle_npcs if n.kind == "bar")
        self.assertTrue(restored.aggressive)
        self.assertEqual(restored.greeter_id, "p1")
        self.assertEqual(restored.max_hp, npc.max_hp)
        self.assertEqual(restored.damage, npc.damage)
        self.assertEqual(
            (restored.home_x, restored.home_y), (npc.home_x, npc.home_y)
        )
        # Transient combat state resets on load.
        self.assertEqual(restored.attack_timer, 0.0)
        self.assertFalse(restored.combat_active)

    def test_stats_scale_with_depth_and_difficulty(self) -> None:
        game = self.make_game()
        game.current_depth = 1
        shallow = game.npc_ally_stats("bar")
        game.current_depth = 8
        deep = game.npc_ally_stats("bar")
        self.assertGreater(deep.max_hp, shallow.max_hp)
        self.assertGreater(deep.damage, shallow.damage)

    # ------------------------------------------------------------------
    # B2 — the greeting.
    # ------------------------------------------------------------------

    def test_greet_flips_aggressive_and_records_credit(self) -> None:
        game = self.make_game()
        npc = self.bar_npc(game)
        game.player.x, game.player.y = npc.x - 1.0, npc.y

        hint = game.current_interaction_hint()
        self.assertIsNotNone(hint)
        self.assertEqual(hint[1], "Greet Tovin")

        floaters_before = len(game.floaters)
        game.interact()
        self.assertTrue(npc.aggressive)
        self.assertEqual(npc.greeter_id, "p1")
        self.assertGreater(npc.max_hp, 0)
        self.assertEqual(npc.hp, npc.max_hp)
        self.assertEqual((npc.home_x, npc.home_y), (npc.x, npc.y))
        self.assertGreater(len(game.floaters), floaters_before)

        # Already-greeted: no prompt, and a second interact is not a greet.
        self.assertIsNone(game.nearby_greetable_npc())
        hint = game.current_interaction_hint()
        if hint is not None:
            self.assertNotEqual(hint[1], "Greet Tovin")

    def test_frog_outside_garden_is_never_greetable_or_interactive(self) -> None:
        game = self.make_game()
        frog = self.frog_npc(game)
        game.player.x, game.player.y = frog.x - 0.9, frog.y
        game.active_mini_game = None

        self.assertIsNone(game.nearby_greetable_npc())
        self.assertIsNone(game.garden_frog_special_room(frog))
        self.assertIsNone(game.nearby_garden_frog())
        game.interact()
        self.assertIsNone(game.active_mini_game)

    # ------------------------------------------------------------------
    # B3 — ally AI, kill credit, damage intake, and death.
    # ------------------------------------------------------------------

    def test_ally_kill_awards_xp_and_credit_to_greeter(self) -> None:
        game = self.make_game()
        npc = self.bar_npc(game)
        game.player.x, game.player.y = npc.x - 1.0, npc.y
        self.assertTrue(game.greet_idle_npc(npc))
        game.player.x, game.player.y = 21.5, 21.5

        enemy = _make_enemy(npc.x + 0.9, npc.y, hp=1)
        game.enemies.append(enemy)
        xp_before = game.player.xp + game.player.level * 1000
        gold_before = game.player.gold
        kills_before = game.run_stats.kills

        game.update_npc_allies(1 / 60)

        self.assertEqual(game.run_stats.kills, kills_before + 1)
        self.assertNotIn(enemy, game.enemies)
        self.assertEqual(enemy.last_player_hit_id, "p1")
        self.assertGreater(game.player.gold, gold_before)
        self.assertGreater(
            game.player.xp + game.player.level * 1000, xp_before
        )
        self.assertGreater(npc.attack_timer, 0.0)

    def test_ally_chases_only_inside_leash_and_walks_home(self) -> None:
        game = self.make_game()
        npc = self.bar_npc(game)
        game.player.x, game.player.y = npc.x - 1.0, npc.y
        self.assertTrue(game.greet_idle_npc(npc))
        game.player.x, game.player.y = 21.5, 21.5

        # An enemy beyond the 9-tile leash of home never engages the ally.
        far = _make_enemy(npc.home_x - 10.5, npc.home_y - 10.0)
        game.enemies.append(far)
        self.assertIsNone(game._npc_ally_target(npc))

        # Displaced ally with no target in leash walks back to its anchor.
        npc.combat_active = True
        npc.x, npc.y = npc.home_x - 3.0, npc.home_y - 3.0
        for _ in range(600):
            game.update_npc_allies(1 / 60)
            if not npc.combat_active:
                break
        self.assertFalse(npc.combat_active)
        self.assertLess(
            math.hypot(npc.x - npc.home_x, npc.y - npc.home_y),
            game.NPC_ALLY_HOME_ARRIVE + 0.05,
        )

    def test_ally_closes_distance_toward_target(self) -> None:
        game = self.make_game()
        npc = self.bar_npc(game)
        game.player.x, game.player.y = npc.x - 1.0, npc.y
        self.assertTrue(game.greet_idle_npc(npc))
        game.player.x, game.player.y = 21.5, 21.5

        enemy = _make_enemy(npc.x - 4.0, npc.y)
        game.enemies.append(enemy)
        distance_before = math.hypot(enemy.x - npc.x, enemy.y - npc.y)
        for _ in range(30):
            game.update_npc_allies(1 / 60)
        self.assertTrue(npc.combat_active)
        self.assertLess(
            math.hypot(enemy.x - npc.x, enemy.y - npc.y), distance_before
        )

    def test_wander_skips_combat_active_allies(self) -> None:
        game = self.make_game()
        npc = self.bar_npc(game)
        game.make_npc_combat_ally(npc, greeter_id="p1")
        npc.combat_active = True
        motion = game.friendly_npc_motion(npc)
        motion.target_x = npc.x + 3.0
        motion.target_y = npc.y
        x_before, y_before = npc.x, npc.y
        game.update_friendly_npcs(0.5)
        self.assertEqual((npc.x, npc.y), (x_before, y_before))

    def test_soul_ward_bolt_is_player_owned_with_greeter_credit(self) -> None:
        game = self.make_game()
        soul = IdleNpc(
            25.5,
            24.5,
            kind="lossless_soul",
            name="Lossless Soul",
            role="Keeper of Unlost Memory",
            color=(142, 214, 205),
        )
        game.idle_npcs.append(soul)
        game.make_npc_combat_ally(soul, greeter_id="p1")
        game.enemies.append(_make_enemy(soul.x + 3.0, soul.y))

        game.update_npc_allies(1 / 60)

        bolts = [p for p in game.projectiles if p.owner == "player"]
        self.assertEqual(len(bolts), 1)
        self.assertEqual(bolts[0].owner_id, "p1")
        self.assertEqual(bolts[0].damage_type, "arcane")
        self.assertGreater(bolts[0].damage, 0)

    def test_take_npc_damage_kills_and_removes_ally(self) -> None:
        game = self.make_game()
        npc = self.bar_npc(game)
        game.make_npc_combat_ally(npc, greeter_id="p1")
        game.take_npc_damage(npc, npc.hp + 50)
        self.assertNotIn(npc, game.idle_npcs)
        self.assertTrue(
            any("falls" in floater.text for floater in game.floaters)
        )

    def test_enemy_projectile_hits_aggressive_ally_not_pacifist(self) -> None:
        game = self.make_game()
        npc = self.bar_npc(game)
        game.make_npc_combat_ally(npc, greeter_id="p1")
        hp_before = npc.hp
        game.projectiles.append(
            Projectile(
                npc.x - 0.2, npc.y, 4.0, 0.0, 5, "enemy", (200, 80, 80)
            )
        )
        game.update_projectiles(1 / 120)
        self.assertLess(npc.hp, hp_before)
        self.assertEqual(len(game.projectiles), 0)

        frog = self.frog_npc(game)
        game.projectiles.append(
            Projectile(
                frog.x - 0.2, frog.y, 4.0, 0.0, 5, "enemy", (200, 80, 80)
            )
        )
        game.update_projectiles(1 / 120)
        self.assertEqual(frog.max_hp, 0)
        self.assertEqual(len(game.projectiles), 1)

    # ------------------------------------------------------------------
    # B4 — enemies aggro back.
    # ------------------------------------------------------------------

    def test_enemy_retargets_aggressive_ally_and_back_on_death(self) -> None:
        game = self.make_game()
        npc = self.bar_npc(game)
        game.player.x, game.player.y = npc.x - 6.0, npc.y
        enemy = _make_enemy(npc.x + 1.0, npc.y)
        game.enemies.append(enemy)

        # Pacifist props are never targeted, even when closest.
        self.assertIs(game.enemy_target(enemy), game.player)

        game.make_npc_combat_ally(npc, greeter_id="p1")
        self.assertIs(game.enemy_target(enemy), npc)

        # Melee executor bleeds the NPC through the dedicated sink.
        hp_before = npc.hp
        game.enemy_melee(enemy)
        self.assertLess(npc.hp, hp_before)

        game.take_npc_damage(npc, npc.hp + 99)
        self.assertIs(game.enemy_target(enemy), game.player)

    def test_enemy_update_pursues_the_nearby_ally(self) -> None:
        game = self.make_game()
        npc = self.bar_npc(game)
        game.make_npc_combat_ally(npc, greeter_id="p1")
        game.player.x, game.player.y = 21.5, 29.5
        enemy = _make_enemy(npc.x - 4.0, npc.y, aggro_range=6.0)
        game.enemies.append(enemy)
        # The aggressive ally is the nearest target, so the full enemy
        # update pursues it instead of the more distant player.
        distance_before = math.hypot(enemy.x - npc.x, enemy.y - npc.y)
        for _ in range(30):
            game.update_enemies(1 / 60, time_scale=1.0)
        self.assertLess(
            math.hypot(enemy.x - npc.x, enemy.y - npc.y), distance_before
        )

    def test_nova_catches_aggressive_allies(self) -> None:
        game = self.make_game()
        from arch_rogue.content import EnemyAbility

        npc = self.bar_npc(game)
        game.make_npc_combat_ally(npc, greeter_id="p1")
        enemy = _make_enemy(npc.x + 1.0, npc.y)
        game.enemies.append(enemy)
        game.player.x, game.player.y = 21.5, 21.5
        hp_before = npc.hp
        game.enemy_nova(
            enemy,
            EnemyAbility(
                key="test_nova",
                effect="nova",
                attack_range=2.5,
                cooldown=4.0,
            ),
        )
        self.assertLess(npc.hp, hp_before)

    # ------------------------------------------------------------------
    # B5 — story-derived aggression and multiplayer replication.
    # ------------------------------------------------------------------

    def test_soul_choice_resolution_arms_the_keeper(self) -> None:
        game = self.make_game()
        game.dungeon.special_rooms = [
            SpecialRoom(
                room_index=0,
                kind="lossless_soul",
                # The ally assertion begins after the 4.9.1 Soul interlude;
                # its win/loss never changes the authored choice effect.
                state={"soul_mini_game_outcome": "lost"},
            )
        ]
        soul = IdleNpc(
            25.5,
            24.5,
            kind="lossless_soul",
            name="Lossless Soul",
            role="Keeper of Unlost Memory",
            color=(142, 214, 205),
        )
        game.idle_npcs.append(soul)
        game.player.x, game.player.y = soul.x - 1.0, soul.y
        self.assertTrue(game.resolve_lossless_soul_choice("preserve"))
        self.assertTrue(soul.aggressive)
        self.assertEqual(soul.greeter_id, "p1")
        self.assertGreater(soul.max_hp, 0)

        # And the derivation survives a reconcile from the room state alone.
        soul.aggressive = False
        game._reconcile_npc_ally_state()
        self.assertTrue(soul.aggressive)

    def test_guest_aggression_derives_from_resolution(self) -> None:
        game = self.make_game()
        answered = StoryGuest(
            26.5, 25.5, 4, 0, "Ilyra", "Witness", "seeks", "words", [],
            resolved=True, resolved_choice="oath",
        )
        forsaken = StoryGuest(
            27.5, 25.5, 4, 1, "Vane", "Witness", "seeks", "words", [],
            resolved=True, resolved_choice="unanswered",
        )
        game.story_guests = [answered, forsaken]
        game._reconcile_npc_ally_state()
        self.assertTrue(answered.aggressive)
        self.assertGreater(answered.max_hp, 0)
        self.assertFalse(forsaken.aggressive)
        self.assertEqual(forsaken.max_hp, 0)

    def test_world_list_lengths_signal_greeting_and_death(self) -> None:
        game = self.make_game()
        npc = self.bar_npc(game)
        baseline = sync.world_list_lengths(game)
        game.make_npc_combat_ally(npc, greeter_id="p1")
        after_greet = sync.world_list_lengths(game)
        self.assertNotEqual(baseline, after_greet)
        game.take_npc_damage(npc, npc.hp + 99)
        self.assertNotEqual(after_greet, sync.world_list_lengths(game))

    def test_snapshot_round_trips_ally_fields_to_joiner(self) -> None:
        host = self.make_game()
        npc = self.bar_npc(host)
        host.player.x, host.player.y = npc.x - 1.0, npc.y
        self.assertTrue(host.greet_idle_npc(npc))
        npc.hp -= 3
        npc.x += 0.4

        state = json.loads(
            json.dumps(sync.build_snapshot_state(host, include_slow=True))
        )

        joiner = self.make_game()
        sync.apply_snapshot_state(joiner, state)
        mirrored = next(n for n in joiner.idle_npcs if n.kind == "bar")
        self.assertTrue(mirrored.aggressive)
        self.assertEqual(mirrored.greeter_id, "p1")
        self.assertEqual(mirrored.max_hp, npc.max_hp)
        self.assertEqual(mirrored.hp, npc.hp)
        self.assertEqual(mirrored.home_x, npc.home_x)
        # Position rides the lerp path (small correction eases in).
        self.assertEqual(mirrored.net_x, npc.x)
        sync.lerp_networked_actors(joiner, 1.0)
        self.assertAlmostEqual(mirrored.x, npc.x, places=3)

    def test_snapshot_roster_shrink_rebuilds_joiner_list(self) -> None:
        host = self.make_game()
        npc = self.bar_npc(host)
        host.make_npc_combat_ally(npc, greeter_id="p1")
        host.take_npc_damage(npc, npc.hp + 99)
        state = json.loads(
            json.dumps(sync.build_snapshot_state(host, include_slow=True))
        )

        joiner = self.make_game()
        self.assertEqual(len(joiner.idle_npcs), 3)
        sync.apply_snapshot_state(joiner, state)
        self.assertEqual(len(joiner.idle_npcs), 2)
        self.assertFalse(
            any(n.kind == "bar" for n in joiner.idle_npcs)
        )


if __name__ == "__main__":
    unittest.main()
