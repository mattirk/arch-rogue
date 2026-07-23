# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
#
# AI Provenance & Liability Notice:
# This repository contains code generated, assisted, or refactored by Artificial
# Intelligence models. Provided strictly "AS IS" under Apache 2.0 with no warranty
# of clean IP provenance or non-infringement; downstream users assume all legal
# and financial risk and should perform their own compliance audits.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""4.7.1 co-op visual replication and joiner responsiveness.

The 4.7.0 joiner never saw action animations: the host's own pose lives on
Game-global fields that were not serialized, the joiner rendered its own
actor from (never-set) globals, enemies lacked ``attack_timer``, and
transient combat fx (slashes, impacts, screen flashes) were host-local.
These tests pin the fixed replication paths plus the joiner-side movement
prediction and the removal of the per-tile-patch cache rebuild.
"""

import math
import os
import tempfile
import time
import types
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game
from arch_rogue.models import Tile
from arch_rogue.net import sync
from arch_rogue.net.mixin import MpSession
from arch_rogue.net.protocol import ROLE_HOST, ROLE_JOIN


def _make_playing_game(tmpdir: str) -> Game:
    game = Game(
        screen_size=(640, 360),
        headless=True,
        save_path=Path(tmpdir) / "run.json",
    )
    game.options_path = Path(tmpdir) / "options.json"
    game.restart(ARCHETYPES[0])
    game.story_intro_pending = False
    game.active_cutscene = None
    game.snap_camera_to_player()
    return game


def _bind_host(game: Game) -> MpSession:
    session = MpSession(role=ROLE_HOST)
    session.started = True
    session.player_id = "p1"
    game.mp_session = session
    game.mp_active = True
    game.mp_role = ROLE_HOST
    game.local_player_id = "p1"
    game.player.player_id = "p1"
    game.players = [game.player]
    return session


def _bind_joiner(game: Game) -> MpSession:
    session = MpSession(role=ROLE_JOIN)
    session.started = True
    session.player_id = "p2"
    game.mp_session = session
    game.mp_active = True
    game.mp_role = ROLE_JOIN
    game.local_player_id = "p2"
    game.player.player_id = "p2"
    game.players = [game.player]
    return session


class PlayerPoseReplicationTests(unittest.TestCase):
    """The action pose must travel from its authoritative home on each side."""

    def test_host_serializes_own_pose_from_game_globals(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_playing_game(tmpdir)
            _bind_host(game)
            game.set_player_action_visual("cast", 0.32)
            self.assertEqual(game.player.action_state, "")  # actor untouched
            data = sync.player_fast_dict(game, game.player)
            self.assertEqual(data["act"][0], "cast")
            self.assertAlmostEqual(data["act"][1], 0.32, places=2)
            self.assertAlmostEqual(data["act"][3], 0.32, places=2)

    def test_host_serializes_partner_pose_from_actor_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_playing_game(tmpdir)
            _bind_host(game)
            partner = sync.build_player_from_full(
                game, {"player_id": "p2", "x": 1.0, "y": 1.0}
            )
            partner.action_state = "attack"
            partner.action_ttl = 0.2
            partner.action_duration = 0.2
            game.players.append(partner)
            data = sync.player_fast_dict(game, partner)
            self.assertEqual(data["act"][0], "attack")
            hit = sync.player_fast_dict(game, game.player)
            self.assertEqual(hit["act"][0], "")

    def test_joiner_applies_own_pose_and_flash_to_globals(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_playing_game(tmpdir)
            _bind_joiner(game)
            sync.apply_player_fast(
                game,
                game.player,
                {"act": ["attack", 0.2, 0.05, 0.2], "hf": [0.22, 0.22]},
            )
            self.assertEqual(game.player_action_state, "attack")
            self.assertAlmostEqual(game.player_action_ttl, 0.2)
            self.assertAlmostEqual(game.player_action_elapsed, 0.05)
            self.assertAlmostEqual(game.player_hit_flash, 0.22)
            # The renderer resolves the local player's pose from the globals.
            self.assertEqual(game.player_visual_state(game.player), "hit")
            game.player_hit_flash = 0.0
            self.assertEqual(game.player_visual_state(game.player), "attack")

    def test_snapshot_echo_does_not_stretch_local_preview_pose(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_playing_game(tmpdir)
            _bind_joiner(game)
            game.set_player_action_visual("attack", 0.20)
            game.player_action_ttl = 0.06  # nearly played out locally
            sync.apply_player_fast(
                game, game.player, {"act": ["attack", 0.2, 0.0, 0.2]}
            )
            self.assertAlmostEqual(game.player_action_ttl, 0.06)
            # A different (unpredicted) pose still takes over immediately.
            sync.apply_player_fast(
                game, game.player, {"act": ["dash", 0.22, 0.0, 0.22]}
            )
            self.assertEqual(game.player_action_state, "dash")

    def test_queued_action_previews_pose_immediately(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_playing_game(tmpdir)
            session = _bind_joiner(game)
            game.state = "playing"
            session.awaiting_floor = False
            sent = []
            game.mp_client = types.SimpleNamespace(
                send_message=lambda *args, **kwargs: sent.append(args)
            )
            game.player.melee_timer = 0.0
            game.mp_queue_action("melee")
            self.assertEqual(len(sent), 1)
            self.assertEqual(game.player_action_state, "attack")
            # On cooldown the pose preview is suppressed (intent still sent).
            game.player_action_state = ""
            game.player_action_ttl = 0.0
            game.player.melee_timer = 1.0
            game.mp_queue_action("melee")
            self.assertEqual(len(sent), 2)
            self.assertEqual(game.player_action_state, "")
            game.mp_client = None


class EnemyPoseReplicationTests(unittest.TestCase):
    def test_attack_timer_round_trips_and_drives_attack_pose(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_playing_game(tmpdir)
            enemy = game.enemies[0]
            enemy.entity_id = "e1"
            enemy.telegraph = "melee"
            enemy.attack_timer = enemy.attack_cooldown  # just struck
            data = sync.enemy_compact_dict(enemy)
            self.assertIn("at", data)

            enemy.attack_timer = 0.0
            sync.apply_enemy_compact(game, enemy, data)
            self.assertAlmostEqual(
                enemy.attack_timer, enemy.attack_cooldown, places=2
            )
            self.assertEqual(game.enemy_visual_state(enemy), "attack")


class FxEventReplicationTests(unittest.TestCase):
    def test_host_records_and_joiner_spawns_each_event_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            host = _make_playing_game(tmpdir)
            _bind_host(host)
            host.add_impact(3.0, 4.0, (10, 20, 30), ttl=0.4, radius=0.5, kind="cast")
            host.add_slash(5.0, 6.0, 0.18, 1.0, 0.0)
            host.trigger_screen_flash((200, 100, 50), 0.36)
            events = host.mp_collect_fx()
            self.assertEqual([entry[1] for entry in events], ["i", "s", "f"])
            self.assertEqual(
                [entry[0] for entry in events], sorted(entry[0] for entry in events)
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            join = _make_playing_game(tmpdir)
            _bind_joiner(join)
            join.impact_effects = []
            join.slashes = []
            join.screen_flash_ttl = 0.0
            baseline_fx = len(join._mp_fx_events)
            sync._apply_fx_events(join, events)
            self.assertEqual(len(join.impact_effects), 1)
            self.assertEqual(len(join.slashes), 1)
            self.assertGreater(join.screen_flash_ttl, 0.0)
            impact = join.impact_effects[0]
            self.assertEqual((impact.x, impact.y), (3.0, 4.0))
            self.assertEqual(impact.kind, "cast")
            # Re-applying the same replay window spawns nothing new...
            sync._apply_fx_events(join, events)
            self.assertEqual(len(join.impact_effects), 1)
            self.assertEqual(len(join.slashes), 1)
            # ...and the joiner never re-records replicated fx for sending.
            self.assertEqual(len(join._mp_fx_events), baseline_fx)

    def test_snapshot_carries_fx_and_floor_send_clears_ring(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_playing_game(tmpdir)
            session = _bind_host(game)
            game.add_impact(1.0, 1.0, (9, 9, 9), ttl=0.2, radius=0.3, kind="spark")
            state = sync.build_snapshot_state(game, include_slow=False)
            self.assertEqual(len(state.get("fx", [])), 1)
            # Events expire out of the replay window after a few ticks.
            session.snapshot_tick += 10
            state = sync.build_snapshot_state(game, include_slow=False)
            self.assertNotIn("fx", state)

    def test_single_player_records_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_playing_game(tmpdir)
            game.add_impact(1.0, 1.0, (9, 9, 9))
            game.add_slash(1.0, 1.0, 0.18, 1.0, 0.0)
            game.trigger_screen_flash((1, 2, 3), 0.2)
            self.assertEqual(len(game._mp_fx_events), 0)


class JoinerWorldApplyTests(unittest.TestCase):
    def test_tile_patch_updates_tiles_without_nuking_tile_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_playing_game(tmpdir)
            _bind_joiner(game)
            sentinel = object()
            game.tile_cache["__sentinel__"] = sentinel
            x = int(game.player.x)
            y = int(game.player.y)
            state = {
                "players": [],
                "enemies": [
                    sync.enemy_compact_dict(e) for e in game.enemies if e.alive
                ],
                "tile_patches": [[x, y, int(Tile.FLOOR)]],
            }
            sync.apply_snapshot_state(game, state)
            self.assertEqual(game.dungeon.tiles[x][y], Tile.FLOOR)
            self.assertIs(game.tile_cache.get("__sentinel__"), sentinel)

    def test_removed_enemy_no_longer_bursts_locally(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_playing_game(tmpdir)
            _bind_joiner(game)
            sync.assign_entity_ids(game)
            doomed = game.enemies[0]
            survivors = [
                sync.enemy_compact_dict(e)
                for e in game.enemies
                if e is not doomed
            ]
            game.impact_effects = []
            sync.apply_snapshot_state(
                game, {"players": [], "enemies": survivors}
            )
            self.assertNotIn(doomed, game.enemies)
            # The authoritative death burst arrives via fx events instead.
            self.assertEqual(len(game.impact_effects), 0)


class JoinerPredictionTests(unittest.TestCase):
    def test_prediction_moves_local_actor_immediately(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_playing_game(tmpdir)
            _bind_joiner(game)
            game.state = "playing"
            game.mp_partner_pause_reason = ""
            game._mp_local_move_vector = lambda: (1.0, 0.0)
            start_x = game.player.x
            for _ in range(30):
                game.mp_update_joiner(1 / 60)
            self.assertGreater(game.player.x, start_x + 1.0)
            self.assertTrue(game.player.moving)

    def test_prediction_freezes_while_host_is_paused(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_playing_game(tmpdir)
            _bind_joiner(game)
            game.state = "playing"
            game.mp_partner_pause_reason = "story"
            game._mp_local_move_vector = lambda: (1.0, 0.0)
            start_x = game.player.x
            for _ in range(30):
                game.mp_update_joiner(1 / 60)
            self.assertEqual(game.player.x, start_x)

    def test_snapshot_reconciles_softly_and_snaps_on_teleport(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_playing_game(tmpdir)
            _bind_joiner(game)
            game.state = "playing"
            game.mp_partner_pause_reason = ""
            self.assertTrue(game.mp_predicts_local_movement())
            x, y = game.player.x, game.player.y
            # Small divergence while walking eases 25%, no lerp target.
            game.player.moving = True
            sync.apply_player_fast(game, game.player, {"x": x + 0.4, "y": y})
            self.assertAlmostEqual(game.player.x, x + 0.1, places=5)
            self.assertIsNone(game.player.net_x)
            # A dash/teleport-sized divergence adopts authority instantly.
            sync.apply_player_fast(game, game.player, {"x": x + 3.0, "y": y})
            self.assertAlmostEqual(game.player.x, x + 3.0, places=5)

    def test_own_damage_synthesizes_screen_flash(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_playing_game(tmpdir)
            _bind_joiner(game)
            game.screen_flash_ttl = 0.0
            hp = game.player.hp
            sync.apply_player_fast(game, game.player, {"hp": hp - 5})
            self.assertGreater(game.screen_flash_ttl, 0.0)

    def test_idle_reconcile_has_deadband_and_gentle_ease(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_playing_game(tmpdir)
            _bind_joiner(game)
            game.state = "playing"
            game.mp_partner_pause_reason = ""
            self.assertTrue(game.mp_predicts_local_movement())
            x, y = game.player.x, game.player.y
            # Standing still: sub-0.2-tile authority overshoot is ignored.
            game.player.moving = False
            sync.apply_player_fast(game, game.player, {"x": x + 0.15, "y": y})
            self.assertEqual(game.player.x, x)
            # Larger idle divergence eases at 10%, not the moving 25%.
            sync.apply_player_fast(game, game.player, {"x": x + 0.5, "y": y})
            self.assertAlmostEqual(game.player.x, x + 0.05, places=5)
            # While moving, the original 25% correction still applies.
            game.player.x = x
            game.player.moving = True
            sync.apply_player_fast(game, game.player, {"x": x + 0.4, "y": y})
            self.assertAlmostEqual(game.player.x, x + 0.1, places=5)


class IntentEdgeSendTests(unittest.TestCase):
    """Start/stop transitions transmit immediately, with position claims."""

    def _joiner_with_stub_client(self, tmpdir: str):
        game = _make_playing_game(tmpdir)
        session = _bind_joiner(game)
        game.state = "playing"
        game.mp_partner_pause_reason = ""
        sent: list[dict] = []
        game.mp_client = types.SimpleNamespace(
            send_message=lambda message, **kwargs: sent.append(message)
        )
        return game, session, sent

    def test_stop_edge_sends_without_waiting_for_the_slot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game, session, sent = self._joiner_with_stub_client(tmpdir)
            game._mp_local_move_vector = lambda: (1.0, 0.0)
            game._mp_send_periodic(100.0)
            intents = [m for m in sent if m.get("t") == "intent"]
            self.assertEqual(len(intents), 1)
            self.assertEqual(intents[0]["move_x"], 1.0)
            self.assertIn("px", intents[0])  # predicted-position claim rides along

            # Release 1 ms later: the slot is not due, the edge still sends.
            game._mp_local_move_vector = lambda: (0.0, 0.0)
            game._mp_send_periodic(100.001)
            intents = [m for m in sent if m.get("t") == "intent"]
            self.assertEqual(len(intents), 2)
            self.assertEqual(intents[1]["move_x"], 0.0)
            self.assertIn("px", intents[1])

            # Still idle, still before the slot: nothing new to say.
            game._mp_send_periodic(100.002)
            intents = [m for m in sent if m.get("t") == "intent"]
            self.assertEqual(len(intents), 2)
            game.mp_client = None

    def test_claims_pause_with_prediction(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game, session, sent = self._joiner_with_stub_client(tmpdir)
            game.mp_partner_pause_reason = "story"  # host paused: no prediction
            game._mp_local_move_vector = lambda: (1.0, 0.0)
            game._mp_send_periodic(100.0)
            intents = [m for m in sent if m.get("t") == "intent"]
            self.assertEqual(len(intents), 1)
            self.assertNotIn("px", intents[0])
            game.mp_client = None


class HostClaimSettleTests(unittest.TestCase):
    """The host walks a resting remote actor onto the joiner's claimed stop."""

    def _host_with_remote(self, tmpdir: str):
        game = _make_playing_game(tmpdir)
        session = _bind_host(game)
        remote = sync.build_player_from_full(
            game,
            {"player_id": "p2", "x": game.player.x, "y": game.player.y},
        )
        game.players.append(remote)
        session.partner_player_id = "p2"
        session.intent_move = (0.0, 0.0)
        session.intent_move_at = time.monotonic()
        return game, session, remote

    def _free_claim(self, game, remote, distance: float):
        for dx, dy in ((-1.0, 0.0), (1.0, 0.0), (0.0, -1.0), (0.0, 1.0)):
            if all(
                not game.dungeon.blocked_for_radius(
                    remote.x + dx * step, remote.y + dy * step, 0.27,
                    block_stairs=True,
                )
                for step in (0.3, distance)
            ):
                return remote.x + dx * distance, remote.y + dy * distance
        raise AssertionError("no free direction near spawn")

    def test_fresh_claim_settles_the_actor_at_walk_speed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game, session, remote = self._host_with_remote(tmpdir)
            claim = self._free_claim(game, remote, 0.4)
            session.intent_claim = claim
            session.intent_claim_at = time.monotonic()
            start = (remote.x, remote.y)
            game.mp_apply_remote_intents(1 / 60)
            first_step = math.hypot(remote.x - start[0], remote.y - start[1])
            self.assertGreater(first_step, 0.0)
            self.assertLess(first_step, 0.08)  # capped at legal walk speed
            for _ in range(60):
                game.mp_apply_remote_intents(1 / 60)
            self.assertLess(
                math.hypot(remote.x - claim[0], remote.y - claim[1]), 0.05
            )

    def test_far_stale_and_suppressed_claims_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game, session, remote = self._host_with_remote(tmpdir)
            start = (remote.x, remote.y)
            # Beyond the one-tile bound (dash/teleport recovery window).
            session.intent_claim = (remote.x + 3.0, remote.y)
            session.intent_claim_at = time.monotonic()
            game.mp_apply_remote_intents(1 / 60)
            self.assertEqual((remote.x, remote.y), start)
            # Stale claim.
            session.intent_claim = self._free_claim(game, remote, 0.4)
            session.intent_claim_at = time.monotonic() - 2.0
            game.mp_apply_remote_intents(1 / 60)
            self.assertEqual((remote.x, remote.y), start)
            # Fresh but suppressed (post-dash window).
            session.intent_claim_at = time.monotonic()
            session.claim_suppressed_until = time.monotonic() + 1.0
            game.mp_apply_remote_intents(1 / 60)
            self.assertEqual((remote.x, remote.y), start)


if __name__ == "__main__":
    unittest.main()
