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

"""Protocol v3 snapshot economics: area of interest, explicit removals,
slow-section change gating, urgent action snapshots, and TCP_NODELAY."""

from __future__ import annotations

import os
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game
from arch_rogue.net import ConnectionUp, MultiplayerClient, sync
from arch_rogue.net.mixin import MpSession, _URGENT_SNAPSHOT_MIN_SPACING
from arch_rogue.net.protocol import ROLE_HOST


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


def _compact_ids(state: dict) -> set[str]:
    return {entry["id"] for entry in state["enemies"]}


class AreaOfInterestTests(unittest.TestCase):
    def test_only_nearby_enemies_ride_the_compact_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_playing_game(tmpdir)
            _bind_host(game)
            sync.assign_entity_ids(game)
            near = game.enemies[0]
            far = game.enemies[1]
            near.x, near.y = game.player.x + 3.0, game.player.y
            far.x = game.player.x + sync.AOI_RADIUS_TILES + 5.0
            far.y = game.player.y
            state = sync.build_snapshot_state(game, include_slow=False)
            ids = _compact_ids(state)
            self.assertIn(near.entity_id, ids)
            self.assertNotIn(far.entity_id, ids)

    def test_partner_position_extends_the_area_of_interest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_playing_game(tmpdir)
            _bind_host(game)
            partner = sync.build_player_from_full(
                game, {"player_id": "p2", "x": 1.0, "y": 1.0}
            )
            game.players.append(partner)
            sync.assign_entity_ids(game)
            far = game.enemies[0]
            far.x = game.player.x + sync.AOI_RADIUS_TILES + 8.0
            far.y = game.player.y
            partner.x, partner.y = far.x + 2.0, far.y
            state = sync.build_snapshot_state(game, include_slow=False)
            self.assertIn(far.entity_id, _compact_ids(state))

    def test_bosses_replicate_regardless_of_distance(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_playing_game(tmpdir)
            _bind_host(game)
            sync.assign_entity_ids(game)
            boss = game.enemies[0]
            boss.size = 2
            boss.x = game.player.x + sync.AOI_RADIUS_TILES + 20.0
            boss.y = game.player.y
            state = sync.build_snapshot_state(game, include_slow=False)
            self.assertIn(boss.entity_id, _compact_ids(state))

    def test_death_emits_a_replayed_gone_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_playing_game(tmpdir)
            _bind_host(game)
            sync.assign_entity_ids(game)
            sync.build_snapshot_state(game, include_slow=False)  # baseline
            victim = game.enemies[0]
            victim.hp = 0
            state = sync.build_snapshot_state(game, include_slow=False)
            gone = [
                entry
                for entry in state.get("fx", [])
                if entry[1] == "x" and entry[2] == victim.entity_id
            ]
            self.assertEqual(len(gone), 1)
            # The event replays on the following snapshot too (loss cover).
            state = sync.build_snapshot_state(game, include_slow=False)
            self.assertTrue(
                any(
                    entry[1] == "x" and entry[2] == victim.entity_id
                    for entry in state.get("fx", [])
                )
            )

    def test_default_valued_enemy_fields_are_omitted(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_playing_game(tmpdir)
            _bind_host(game)
            sync.assign_entity_ids(game)
            idle = game.enemies[0]
            idle.moving = False
            idle.telegraph = ""
            idle.windup_time = 0.0
            idle.windup_duration = 0.0
            idle.windup_attack = ""
            idle.attack_timer = 0.0
            idle.statuses = {}
            data = sync.enemy_compact_dict(idle)
            for key in ("mv", "mx", "my", "tg", "wt", "wd", "wa", "at", "st"):
                self.assertNotIn(key, data)
            # And absence resets a previously telegraphing joiner copy.
            idle.telegraph = "stale"
            idle.attack_timer = 0.4
            idle.statuses = {"chilled": 1.0}
            sync.apply_enemy_compact(game, idle, data)
            self.assertEqual(idle.telegraph, "")
            self.assertEqual(idle.attack_timer, 0.0)
            self.assertEqual(idle.statuses, {})


class SlowSectionGatingTests(unittest.TestCase):
    def test_unchanged_sections_are_gated_after_first_send(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_playing_game(tmpdir)
            _bind_host(game)
            sync.build_floor_state(game)  # resets the section cache
            first = sync.build_snapshot_state(game, include_slow=True)
            self.assertIn("items", first["slow"])
            self.assertIn("shop_inv", first["slow"])
            second = sync.build_snapshot_state(game, include_slow=True)
            self.assertIn("eids", second["slow"])  # backstop always rides
            self.assertNotIn("items", second["slow"])
            self.assertNotIn("shop_inv", second["slow"])

    def test_changed_section_is_resent_alone(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_playing_game(tmpdir)
            _bind_host(game)
            sync.build_floor_state(game)
            sync.build_snapshot_state(game, include_slow=True)
            game.player.speed += 1.0  # players slow section content change
            state = sync.build_snapshot_state(game, include_slow=True)
            self.assertIn("players", state["slow"])
            self.assertNotIn("items", state["slow"])

    def test_full_slow_resends_everything(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_playing_game(tmpdir)
            _bind_host(game)
            sync.build_floor_state(game)
            sync.build_snapshot_state(game, include_slow=True)
            state = sync.build_snapshot_state(
                game, include_slow=True, full_slow=True
            )
            for key in ("players", "items", "traps", "shrines", "shop_inv"):
                self.assertIn(key, state["slow"])


class UrgentSnapshotTests(unittest.TestCase):
    def test_remote_action_pulls_the_next_snapshot_forward(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_playing_game(tmpdir)
            session = _bind_host(game)
            partner = sync.build_player_from_full(
                game,
                {"player_id": "p2", "x": game.player.x, "y": game.player.y},
            )
            game.players.append(partner)
            session.partner_player_id = "p2"
            now = time.monotonic()
            session.next_snapshot_at = now + 10.0
            session.last_snapshot_sent_at = now - 1.0
            session.intent_actions.append(("potion_hp", None, 0.0, 0.0))
            game.mp_apply_remote_intents(1 / 60)
            self.assertLessEqual(session.next_snapshot_at, time.monotonic())

    def test_urgent_snapshots_respect_the_minimum_spacing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_playing_game(tmpdir)
            session = _bind_host(game)
            partner = sync.build_player_from_full(
                game,
                {"player_id": "p2", "x": game.player.x, "y": game.player.y},
            )
            game.players.append(partner)
            session.partner_player_id = "p2"
            now = time.monotonic()
            session.next_snapshot_at = now + 10.0
            session.last_snapshot_sent_at = now  # just sent one
            session.intent_actions.append(("potion_hp", None, 0.0, 0.0))
            game.mp_apply_remote_intents(1 / 60)
            self.assertGreaterEqual(
                session.next_snapshot_at,
                now + _URGENT_SNAPSHOT_MIN_SPACING * 0.5,
            )


class NodelayTests(unittest.TestCase):
    def test_client_socket_disables_nagle(self) -> None:
        listener = socket.create_server(("127.0.0.1", 0))
        accepted: list[socket.socket] = []

        def accept_one() -> None:
            conn, _ = listener.accept()
            accepted.append(conn)

        acceptor = threading.Thread(target=accept_one, daemon=True)
        acceptor.start()
        client = MultiplayerClient(
            "127.0.0.1", listener.getsockname()[1], generation=1
        )
        client.start()
        try:
            deadline = time.monotonic() + 5.0
            connected = False
            while time.monotonic() < deadline and not connected:
                connected = any(
                    isinstance(event, ConnectionUp)
                    for event in client.poll_events()
                )
                time.sleep(0.01)
            self.assertTrue(connected)
            sock = client._sock
            self.assertIsNotNone(sock)
            self.assertNotEqual(
                sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY), 0
            )
        finally:
            client.close()
            acceptor.join(timeout=2.0)
            for conn in accepted:
                conn.close()
            listener.close()


if __name__ == "__main__":
    unittest.main()
