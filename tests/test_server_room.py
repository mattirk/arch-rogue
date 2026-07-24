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

"""4.6 relay-room lifecycle tests against the transport-agnostic hub.

The ``RoomHub`` is exercised directly with fake transports and an injected
fake clock — no sockets, no asyncio, no timers.
"""

from __future__ import annotations

import unittest

from server.config import ServerConfig
from server.protocol import MP_PROTOCOL_VERSION, make_hello
from server.room import Connection, RoomHub


class FakeTransport:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.closed = False

    def send_message(self, message: dict) -> None:
        self.sent.append(message)

    def close(self) -> None:
        self.closed = True

    def types(self) -> list[str]:
        return [message["t"] for message in self.sent]

    def last(self, message_type: str) -> dict:
        for message in reversed(self.sent):
            if message["t"] == message_type:
                return message
        raise AssertionError(
            f"no {message_type!r} in {self.types()}"
        )


class RoomHubHarness:
    def __init__(self, **config_overrides) -> None:
        defaults = dict(
            reconnect_grace=30.0,
            idle_timeout=600.0,
            hello_timeout=10.0,
        )
        defaults.update(config_overrides)
        self.now = 1000.0
        self.hub = RoomHub(
            ServerConfig(**defaults), clock=lambda: self.now
        )

    def advance(self, seconds: float) -> None:
        self.now += seconds
        self.hub.tick()

    def connect(self) -> tuple[Connection, FakeTransport]:
        transport = FakeTransport()
        return self.hub.connect(transport), transport

    def hello(
        self,
        connection: Connection,
        *,
        run_id: str,
        role: str,
        name: str = "Player",
        revision: str = "4.6.0",
        token: str = "",
        seq: int = 1,
    ) -> None:
        self.hub.handle_message(
            connection,
            make_hello(
                seq=seq,
                name=name,
                run_id=run_id,
                role=role,
                content_revision=revision,
                reconnect_token=token,
            ),
        )

    def pair(
        self, run_id: str = "AB2C"
    ) -> tuple[Connection, FakeTransport, Connection, FakeTransport]:
        host_conn, host = self.connect()
        self.hello(host_conn, run_id=run_id, role="host", name="Host")
        join_conn, join = self.connect()
        self.hello(join_conn, run_id=run_id, role="join", name="Join")
        return host_conn, host, join_conn, join

    def start_pair(
        self, run_id: str = "AB2C"
    ) -> tuple[Connection, FakeTransport, Connection, FakeTransport]:
        host_conn, host, join_conn, join = self.pair(run_id)
        self.hub.handle_message(
            host_conn,
            {"t": "ready", "seq": 2, "archetype_key": "Warden", "run_seed": 7},
        )
        self.hub.handle_message(
            join_conn, {"t": "ready", "seq": 2, "archetype_key": "Rogue"}
        )
        return host_conn, host, join_conn, join


class RoomLifecycleTests(unittest.TestCase):
    def test_host_creates_waiting_room_and_join_completes_handshake(self) -> None:
        h = RoomHubHarness()
        host_conn, host = h.connect()
        h.hello(host_conn, run_id="AB2C", role="host", name="Matti")
        welcome = host.last("welcome")
        self.assertEqual(welcome["you_are"], "host")
        self.assertEqual(welcome["player_id"], "p1")
        self.assertEqual(len(welcome["reconnect_token"]), 32)
        self.assertEqual(h.hub.rooms["AB2C"].state, "waiting_for_join")

        join_conn, join = h.connect()
        h.hello(join_conn, run_id="ab2c", role="join", name="Partner")
        self.assertEqual(join.last("welcome")["player_id"], "p2")
        self.assertEqual(join.last("welcome")["partner_name"], "Matti")
        self.assertEqual(host.last("partner_joined")["name"], "Partner")
        self.assertEqual(h.hub.rooms["AB2C"].state, "selecting")

    def test_join_missing_room_is_rejected(self) -> None:
        h = RoomHubHarness()
        join_conn, join = h.connect()
        h.hello(join_conn, run_id="ZZZZ", role="join")
        error = join.last("error")
        self.assertEqual(error["code"], "run_not_found")
        self.assertTrue(error["fatal"])
        self.assertTrue(join.closed)

    def test_host_code_collision_is_rejected_deterministically(self) -> None:
        h = RoomHubHarness()
        host_conn, _host = h.connect()
        h.hello(host_conn, run_id="AB2C", role="host")
        second_conn, second = h.connect()
        h.hello(second_conn, run_id="AB2C", role="host")
        self.assertEqual(second.last("error")["code"], "run_id_in_use")
        self.assertTrue(second.closed)
        # The original room survives the collision untouched.
        self.assertIn("AB2C", h.hub.rooms)

    def test_third_client_and_late_join_are_rejected(self) -> None:
        h = RoomHubHarness()
        h.pair()
        third_conn, third = h.connect()
        h.hello(third_conn, run_id="AB2C", role="join")
        self.assertEqual(third.last("error")["code"], "run_full")

        h2 = RoomHubHarness()
        h2.start_pair("CDEF")
        late_conn, late = h2.connect()
        h2.hello(late_conn, run_id="CDEF", role="join")
        self.assertEqual(late.last("error")["code"], "run_full")

    def test_revision_mismatch_warns_both_peers_and_allows_join(self) -> None:
        h = RoomHubHarness()
        host_conn, host = h.connect()
        h.hello(host_conn, run_id="AB2C", role="host", revision="4.6.0")
        join_conn, join = h.connect()
        h.hello(join_conn, run_id="AB2C", role="join", revision="4.6.1")

        self.assertFalse(join.closed)
        self.assertEqual(h.hub.rooms["AB2C"].state, "selecting")
        self.assertEqual(join.last("welcome")["partner_revision"], "4.6.0")
        self.assertEqual(
            host.last("partner_joined")["partner_revision"], "4.6.1"
        )

    def test_protocol_version_mismatch_is_fatal(self) -> None:
        h = RoomHubHarness()
        connection, transport = h.connect()
        message = make_hello(
            seq=1,
            name="x",
            run_id="AB2C",
            role="host",
            content_revision="4.6.0",
        )
        message["protocol_version"] = MP_PROTOCOL_VERSION + 1
        h.hub.handle_message(connection, message)
        self.assertEqual(transport.last("error")["code"], "bad_version")
        self.assertTrue(transport.closed)

    def test_ready_handshake_emits_exactly_one_start(self) -> None:
        h = RoomHubHarness()
        host_conn, host, join_conn, join = h.pair()
        # Joiner readies first (ready/hello race variant).
        h.hub.handle_message(
            join_conn, {"t": "ready", "seq": 2, "archetype_key": "Arcanist"}
        )
        self.assertNotIn("start", host.types())
        h.hub.handle_message(
            host_conn,
            {"t": "ready", "seq": 2, "archetype_key": "Warden", "run_seed": 55},
        )
        start_host = host.last("start")
        start_join = join.last("start")
        self.assertEqual(start_host, start_join)
        self.assertEqual(start_host["run_seed"], 55)
        self.assertEqual(start_host["joiner_archetype"], "Arcanist")
        self.assertEqual(host.types().count("start"), 1)
        self.assertEqual(join.types().count("start"), 1)
        # A duplicate ready cannot re-fire start.
        h.hub.handle_message(
            host_conn,
            {"t": "ready", "seq": 3, "archetype_key": "Warden", "run_seed": 56},
        )
        self.assertEqual(join.types().count("start"), 1)

    def test_host_ready_requires_seed_and_joiner_may_not_send_one(self) -> None:
        h = RoomHubHarness()
        host_conn, host, join_conn, join = h.pair()
        h.hub.handle_message(
            host_conn, {"t": "ready", "seq": 2, "archetype_key": "Warden"}
        )
        self.assertEqual(host.last("error")["code"], "bad_msg")
        h.hub.handle_message(
            join_conn,
            {"t": "ready", "seq": 2, "archetype_key": "Rogue", "run_seed": 9},
        )
        self.assertEqual(join.last("error")["code"], "role_forbidden")

    def test_role_forbidden_routing(self) -> None:
        h = RoomHubHarness()
        host_conn, host, join_conn, join = h.start_pair()
        h.hub.handle_message(
            join_conn,
            {"t": "snapshot", "floor_revision": 1, "tick": 1, "state": {}},
        )
        self.assertEqual(join.last("error")["code"], "role_forbidden")
        h.hub.handle_message(
            host_conn,
            {"t": "intent", "input_seq": 1, "move_x": 0, "move_y": 0,
             "action": ""},
        )
        self.assertEqual(host.last("error")["code"], "role_forbidden")
        # Neither non-fatal error dropped the peers.
        self.assertFalse(host.closed)
        self.assertFalse(join.closed)

    def test_relay_paths_and_intent_stamping(self) -> None:
        h = RoomHubHarness()
        host_conn, host, join_conn, join = h.start_pair()
        h.hub.handle_message(
            host_conn,
            {"t": "floor", "floor_revision": 1, "depth": 1, "floor_seed": 3,
             "state": {"a": 1}},
        )
        self.assertEqual(join.last("floor")["state"], {"a": 1})
        h.hub.handle_message(
            host_conn,
            {"t": "snapshot", "floor_revision": 1, "tick": 4, "state": {}},
        )
        self.assertEqual(join.last("snapshot")["tick"], 4)
        h.hub.handle_message(
            join_conn,
            {"t": "intent", "input_seq": 2, "move_x": 3.5, "move_y": -0.25,
             "action": "melee", "target": None},
        )
        intent = host.last("intent")
        self.assertEqual(intent["player_id"], "p2")
        self.assertEqual(intent["move_x"], 1.0)  # server clamps to [-1, 1]
        self.assertEqual(intent["move_y"], -0.25)

    def test_graceful_bye_is_final_and_frees_the_seat_before_start(self) -> None:
        h = RoomHubHarness()
        host_conn, host, join_conn, join = h.pair()
        h.hub.handle_message(join_conn, {"t": "bye"})
        self.assertIn("partner_left", host.types())
        self.assertTrue(join.closed)
        room = h.hub.rooms["AB2C"]
        self.assertEqual(room.state, "waiting_for_join")
        # A replacement partner can join the reopened seat.
        second_conn, second = h.connect()
        h.hello(second_conn, run_id="AB2C", role="join", name="Second")
        self.assertEqual(second.last("welcome")["player_id"], "p2")

    def test_host_bye_closes_the_room(self) -> None:
        h = RoomHubHarness()
        host_conn, _host, _join_conn, join = h.pair()
        h.hub.handle_message(host_conn, {"t": "bye"})
        self.assertIn("partner_left", join.types())
        self.assertNotIn("AB2C", h.hub.rooms)
        self.assertTrue(join.closed)

    def test_unexpected_disconnect_reserves_slot_and_token_reclaims_it(self) -> None:
        h = RoomHubHarness()
        host_conn, host, join_conn, join = h.start_pair()
        token = join.last("welcome")["reconnect_token"]
        h.hub.handle_message(
            host_conn,
            {"t": "floor", "floor_revision": 1, "depth": 1, "floor_seed": 0,
             "state": {"tiles": []}},
        )
        h.hub.handle_message(
            host_conn,
            {"t": "snapshot", "floor_revision": 1, "tick": 9, "state": {}},
        )
        h.hub.disconnect(join_conn, expected=False)
        self.assertEqual(
            host.last("partner_disconnected")["grace_seconds"], 30.0
        )
        room = h.hub.rooms["AB2C"]
        self.assertTrue(room.slot("join").reserved)

        # Wrong token cannot reclaim the reserved seat.
        thief_conn, thief = h.connect()
        h.hello(
            thief_conn, run_id="AB2C", role="join", token="00" * 16
        )
        self.assertEqual(thief.last("error")["code"], "run_full")

        # The real token reclaims within the grace window and replays the
        # latest floor + snapshot before input re-enables.
        h.advance(10.0)
        back_conn, back = h.connect()
        h.hello(back_conn, run_id="AB2C", role="join", token=token, name="Join")
        self.assertEqual(back.last("welcome")["player_id"], "p2")
        self.assertEqual(host.last("partner_rejoined")["player_id"], "p2")
        self.assertEqual(back.last("floor")["floor_revision"], 1)
        self.assertEqual(back.last("snapshot")["tick"], 9)

    def test_grace_expiry_emits_final_partner_left(self) -> None:
        h = RoomHubHarness(reconnect_grace=30.0)
        host_conn, host, join_conn, _join = h.start_pair()
        h.hub.disconnect(join_conn, expected=False)
        h.advance(29.0)
        self.assertNotIn("partner_left", host.types())
        h.advance(2.0)
        self.assertIn("partner_left", host.types())
        # The expired token can no longer reclaim anything.
        stale_conn, stale = h.connect()
        h.hello(stale_conn, run_id="AB2C", role="join", token="ab" * 16)
        self.assertEqual(stale.last("error")["code"], "run_full")

    def test_idle_timeout_drops_the_room(self) -> None:
        h = RoomHubHarness(idle_timeout=600.0)
        host_conn, host, join_conn, join = h.start_pair()
        # Activity refreshes idleness.
        h.advance(500.0)
        h.hub.handle_message(host_conn, {"t": "ping", "seq": 3, "ts": 1.0})
        h.advance(500.0)
        self.assertIn("AB2C", h.hub.rooms)
        # Then true idleness expires the room and both peers hear about it.
        h.advance(601.0)
        self.assertNotIn("AB2C", h.hub.rooms)
        self.assertEqual(host.last("error")["code"], "timeout")
        self.assertEqual(join.last("error")["code"], "timeout")
        self.assertTrue(host.closed)
        self.assertTrue(join.closed)

    def test_hello_timeout_expires_silent_connections(self) -> None:
        h = RoomHubHarness(hello_timeout=10.0)
        _connection, transport = h.connect()
        h.advance(11.0)
        self.assertEqual(transport.last("error")["code"], "timeout")
        self.assertTrue(transport.closed)

    def test_first_message_must_be_hello(self) -> None:
        h = RoomHubHarness()
        connection, transport = h.connect()
        h.hub.handle_message(connection, {"t": "ping", "seq": 1, "ts": 0.0})
        error = transport.last("error")
        self.assertEqual(error["code"], "bad_msg")
        self.assertTrue(error["fatal"])

    def test_seq_must_be_monotonic(self) -> None:
        h = RoomHubHarness()
        host_conn, host, _join_conn, _join = h.pair()
        h.hub.handle_message(
            host_conn,
            {"t": "ready", "seq": 1, "archetype_key": "Warden", "run_seed": 1},
        )
        self.assertEqual(host.last("error")["code"], "bad_msg")
        self.assertFalse(host.closed)

    def test_protocol_violation_is_fatal_without_grace(self) -> None:
        h = RoomHubHarness()
        host_conn, host, _join_conn, join = h.pair()
        h.hub.handle_protocol_violation(host_conn, "malformed line")
        self.assertTrue(host.closed)
        # Host violations close the whole room deterministically.
        self.assertIn("partner_left", join.types())
        self.assertNotIn("AB2C", h.hub.rooms)

    def test_unknown_types_are_ignored_after_hello(self) -> None:
        h = RoomHubHarness()
        host_conn, host, _join_conn, _join = h.pair()
        before = list(host.types())
        h.hub.handle_message(host_conn, {"t": "dance", "style": "macabre"})
        self.assertEqual(host.types(), before)
        self.assertFalse(host.closed)


if __name__ == "__main__":
    unittest.main()
