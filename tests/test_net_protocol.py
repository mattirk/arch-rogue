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

"""4.6 wire-protocol tests: framing, codec, validation, and run ids.

Everything here is pure-stdlib (the canonical ``arch_rogue_protocol``
package); no Pygame, no sockets, no network access.
"""

from __future__ import annotations

import math
import unittest

from arch_rogue_protocol import (
    MP_MAX_MESSAGE_BYTES,
    MP_PROTOCOL_VERSION,
    MP_RUN_ID_ALPHABET,
    MP_RUN_ID_LENGTH,
    INTENT_ACTIONS,
    LineFramer,
    MessageTooLargeError,
    ProtocolError,
    clamp_unit,
    decode_message,
    encode_message,
    generate_reconnect_token,
    generate_run_id,
    is_valid_run_id,
    make_bye,
    make_error,
    make_floor,
    make_hello,
    make_intent,
    make_partner_disconnected,
    make_partner_joined,
    make_partner_left,
    make_partner_rejoined,
    make_ping,
    make_pong,
    make_ready,
    make_ready_ack,
    make_run_ended,
    make_snapshot,
    make_start,
    make_welcome,
    normalize_run_id,
    role_allowed,
    sanitize_player_name,
    validate_client_message,
)

from arch_rogue.net.messages import (
    ErrorMessage,
    FloorMessage,
    IntentMessage,
    SnapshotMessage,
    Start,
    UnknownMessage,
    Welcome,
    message_from_dict,
)


def _every_message() -> list[dict]:
    """One instance of every canonical message type (client and server)."""

    return [
        make_hello(
            seq=1,
            name="Matti",
            run_id="AB2C",
            role="host",
            content_revision="4.6.0",
            reconnect_token="cafe" * 8,
        ),
        make_ready(seq=2, archetype_key="Warden", run_seed=987654321),
        make_ready(seq=3, archetype_key="Rogue"),
        make_floor(
            floor_revision=1,
            depth=3,
            floor_seed=42,
            state={"tiles": [[0, 1], [1, 0]], "players": []},
        ),
        make_snapshot(
            floor_revision=1, tick=99, state={"players": [], "enemies": []}
        ),
        make_intent(
            input_seq=5, move_x=0.5, move_y=-1.0, action="melee", target=None
        ),
        make_intent(
            input_seq=6, move_x=0.0, move_y=0.0, px=12.345, py=6.789
        ),
        make_run_ended(outcome="victory", results=[{"player_id": "p1"}]),
        make_ping(seq=6, ts=123.5),
        make_pong(seq=6, ts=123.5),
        make_bye(),
        make_error(code="run_full", msg="full", fatal=True, seq=4),
        make_welcome(
            seq=1,
            run_id="AB2C",
            you_are="join",
            player_id="p2",
            reconnect_token="beef" * 8,
            partner_name="Matti",
            partner_ready=True,
        ),
        make_partner_joined(name="Partner", player_id="p2"),
        make_ready_ack(seq=2, player_id="p1", archetype_key="Warden"),
        make_start(
            run_seed=7,
            host_player_id="p1",
            host_name="Matti",
            host_archetype="Warden",
            joiner_player_id="p2",
            joiner_name="Partner",
            joiner_archetype="Arcanist",
        ),
        make_partner_disconnected(grace_seconds=30.0),
        make_partner_rejoined(name="Partner", player_id="p2"),
        make_partner_left(),
    ]


class CodecRoundTripTests(unittest.TestCase):
    def test_every_message_type_round_trips(self) -> None:
        for message in _every_message():
            with self.subTest(t=message["t"]):
                line = encode_message(message)
                self.assertTrue(line.endswith(b"\n"))
                self.assertEqual(decode_message(line[:-1]), message)
                # Also through the framer, as one coalesced stream chunk.
                framer = LineFramer()
                (framed,) = framer.feed(line)
                self.assertEqual(decode_message(framed), message)

    def test_typed_message_parsing_covers_server_events(self) -> None:
        welcome = message_from_dict(
            make_welcome(
                seq=1,
                run_id="AB2C",
                you_are="host",
                player_id="p1",
                reconnect_token="00" * 16,
            )
        )
        self.assertIsInstance(welcome, Welcome)
        assert isinstance(welcome, Welcome)
        self.assertEqual(welcome.player_id, "p1")
        self.assertIsNone(welcome.partner_name)

        start = message_from_dict(
            make_start(
                run_seed=9,
                host_player_id="p1",
                host_name="a",
                host_archetype="Warden",
                joiner_player_id="p2",
                joiner_name="b",
                joiner_archetype="Rogue",
            )
        )
        self.assertIsInstance(start, Start)

        snapshot = message_from_dict(
            make_snapshot(floor_revision=2, tick=7, state={"x": 1})
        )
        self.assertIsInstance(snapshot, SnapshotMessage)
        assert isinstance(snapshot, SnapshotMessage)
        self.assertEqual((snapshot.floor_revision, snapshot.tick), (2, 7))

        floor = message_from_dict(
            make_floor(floor_revision=1, depth=1, floor_seed=0, state={})
        )
        self.assertIsInstance(floor, FloorMessage)

        intent = message_from_dict(
            {
                "t": "intent",
                "input_seq": 3,
                "player_id": "p2",
                "move_x": 4.0,
                "move_y": float("nan"),
                "action": "dash",
                "target": None,
            }
        )
        self.assertIsInstance(intent, IntentMessage)
        assert isinstance(intent, IntentMessage)
        # Defensive clamp on the receive path too.
        self.assertEqual(intent.move_x, 1.0)
        self.assertEqual(intent.move_y, 0.0)
        # No claim fields -> None; a valid claim parses through.
        self.assertIsNone(intent.px)
        self.assertIsNone(intent.py)
        claimed = message_from_dict(
            make_intent(input_seq=4, move_x=0.0, move_y=0.0, px=8.25, py=3.5)
        )
        assert isinstance(claimed, IntentMessage)
        self.assertEqual((claimed.px, claimed.py), (8.25, 3.5))
        hostile_claim = message_from_dict(
            {"t": "intent", "input_seq": 5, "player_id": "p2", "move_x": 0.0,
             "move_y": 0.0, "action": "", "target": None,
             "px": "evil", "py": 1.0}
        )
        assert isinstance(hostile_claim, IntentMessage)
        self.assertIsNone(hostile_claim.px)

        error = message_from_dict(
            make_error(code="bad_msg", msg="x", fatal=False)
        )
        self.assertIsInstance(error, ErrorMessage)

    def test_unknown_type_is_tolerated_everywhere(self) -> None:
        line = encode_message({"t": "future_feature", "payload": [1, 2, 3]})
        decoded = decode_message(line[:-1])
        self.assertEqual(decoded["t"], "future_feature")
        # Structural validation tolerates unknown types (forward compat).
        self.assertEqual(validate_client_message(decoded), "")
        parsed = message_from_dict(decoded)
        self.assertIsInstance(parsed, UnknownMessage)

    def test_encode_rejects_bad_shapes(self) -> None:
        with self.assertRaises(ProtocolError):
            encode_message(["not", "an", "object"])  # type: ignore[arg-type]
        with self.assertRaises(ProtocolError):
            encode_message({"seq": 1})  # no t
        with self.assertRaises(ProtocolError):
            encode_message({"t": ""})
        with self.assertRaises(ProtocolError):
            encode_message({"t": "ping", "ts": float("inf")})
        with self.assertRaises(ProtocolError):
            encode_message({"t": "ping", "ts": float("nan")})
        with self.assertRaises(ProtocolError):
            encode_message({"t": "ping", "obj": object()})

    def test_decode_rejects_malformed_lines(self) -> None:
        for raw in (
            b"\xff\xfe invalid utf8",
            b"not json at all",
            b"[1, 2, 3]",
            b'"just a string"',
            b"{}",
            b'{"seq": 1}',
            b'{"t": 5}',
            b"",
            b'{"t": "ping", "ts": NaN}',
            b'{"t": "ping", "ts": Infinity}',
        ):
            with self.subTest(raw=raw[:20]):
                with self.assertRaises(ProtocolError):
                    decode_message(raw)

    def test_oversized_messages_are_rejected(self) -> None:
        huge = {"t": "snapshot", "blob": "x" * MP_MAX_MESSAGE_BYTES}
        with self.assertRaises(MessageTooLargeError):
            encode_message(huge)
        with self.assertRaises(MessageTooLargeError):
            decode_message(b"x" * (MP_MAX_MESSAGE_BYTES + 1))


class LineFramerTests(unittest.TestCase):
    def test_fragmented_lines_reassemble(self) -> None:
        framer = LineFramer()
        payload = encode_message(make_ping(seq=1, ts=0.5))
        for index in range(len(payload) - 1):
            self.assertEqual(framer.feed(payload[index : index + 1]), [])
        (line,) = framer.feed(payload[-1:])
        self.assertEqual(decode_message(line)["t"], "ping")
        self.assertEqual(framer.pending_bytes(), 0)

    def test_coalesced_lines_split(self) -> None:
        chunk = b"".join(
            encode_message(make_ping(seq=seq, ts=float(seq)))
            for seq in range(1, 6)
        )
        framer = LineFramer()
        lines = framer.feed(chunk)
        self.assertEqual(len(lines), 5)
        self.assertEqual(
            [decode_message(line)["seq"] for line in lines], [1, 2, 3, 4, 5]
        )

    def test_partial_then_coalesced_mix(self) -> None:
        first = encode_message(make_ping(seq=1, ts=1.0))
        second = encode_message(make_ping(seq=2, ts=2.0))
        framer = LineFramer()
        self.assertEqual(framer.feed(first[:10]), [])
        lines = framer.feed(first[10:] + second)
        self.assertEqual(len(lines), 2)

    def test_blank_lines_are_skipped(self) -> None:
        framer = LineFramer()
        self.assertEqual(framer.feed(b"\n\r\n  \n"), [])

    def test_oversized_line_raises_and_resets(self) -> None:
        framer = LineFramer(max_line_bytes=64)
        with self.assertRaises(MessageTooLargeError):
            framer.feed(b"y" * 65)  # partial overflow, no newline yet
        self.assertEqual(framer.pending_bytes(), 0)
        framer = LineFramer(max_line_bytes=64)
        with self.assertRaises(MessageTooLargeError):
            framer.feed(b"y" * 80 + b"\n")
        # Recoverable: subsequent traffic still frames.
        self.assertEqual(
            framer.feed(encode_message(make_bye()))[0], b'{"t":"bye"}'
        )


class ValidationTests(unittest.TestCase):
    def test_valid_client_messages_pass(self) -> None:
        for message in _every_message():
            if message["t"] in (
                "hello",
                "ready",
                "floor",
                "snapshot",
                "intent",
                "run_ended",
                "ping",
                "bye",
            ):
                with self.subTest(t=message["t"]):
                    self.assertEqual(validate_client_message(message), "")

    def test_invalid_field_types_are_rejected(self) -> None:
        bad = [
            {"t": "hello", "seq": 0, "protocol_version": MP_PROTOCOL_VERSION,
             "content_revision": "r", "name": "n", "run_id": "AB2C",
             "role": "host"},  # seq must be positive
            {"t": "hello", "seq": 1, "protocol_version": "1",
             "content_revision": "r", "name": "n", "run_id": "AB2C",
             "role": "host"},
            {"t": "hello", "seq": 1, "protocol_version": MP_PROTOCOL_VERSION,
             "content_revision": "r", "name": "n", "run_id": "AB2C",
             "role": "spectator"},
            {"t": "ready", "seq": 1, "archetype_key": ""},
            {"t": "ready", "seq": 1, "archetype_key": "Warden",
             "run_seed": "42"},
            {"t": "floor", "floor_revision": -1, "depth": 1, "floor_seed": 0,
             "state": {}},
            {"t": "floor", "floor_revision": 1, "depth": 1, "floor_seed": 0,
             "state": []},
            {"t": "snapshot", "floor_revision": 1, "tick": True, "state": {}},
            {"t": "intent", "input_seq": 1, "move_x": float("inf"),
             "move_y": 0.0, "action": ""},
            {"t": "intent", "input_seq": 1, "move_x": 0.0, "move_y": 0.0,
             "action": "teleport_hack"},
            {"t": "intent", "input_seq": 1, "move_x": 0.0, "move_y": 0.0,
             "action": "", "target": 5},
            # 4.7.6 predicted-position claims: both-or-neither, finite only.
            {"t": "intent", "input_seq": 1, "move_x": 0.0, "move_y": 0.0,
             "action": "", "px": 4.0},
            {"t": "intent", "input_seq": 1, "move_x": 0.0, "move_y": 0.0,
             "action": "", "px": float("nan"), "py": 2.0},
            {"t": "run_ended", "outcome": 3},
            {"t": "ping", "seq": 1, "ts": float("nan")},
        ]
        for message in bad:
            with self.subTest(message=message):
                self.assertEqual(validate_client_message(message), "bad_msg")

    def test_role_routing_table(self) -> None:
        self.assertTrue(role_allowed("floor", "host"))
        self.assertTrue(role_allowed("snapshot", "host"))
        self.assertTrue(role_allowed("run_ended", "host"))
        self.assertFalse(role_allowed("floor", "join"))
        self.assertFalse(role_allowed("snapshot", "join"))
        self.assertFalse(role_allowed("run_ended", "join"))
        self.assertTrue(role_allowed("intent", "join"))
        self.assertFalse(role_allowed("intent", "host"))
        for shared in ("hello", "ready", "ping", "bye"):
            self.assertTrue(role_allowed(shared, "host"))
            self.assertTrue(role_allowed(shared, "join"))

    def test_intent_builder_clamps_and_validates(self) -> None:
        intent = make_intent(input_seq=1, move_x=5.0, move_y=float("nan"))
        self.assertEqual(intent["move_x"], 1.0)
        self.assertEqual(intent["move_y"], 0.0)
        with self.assertRaises(ProtocolError):
            make_intent(input_seq=1, action="not_an_action")
        self.assertIn("interact", INTENT_ACTIONS)
        self.assertIn("choose_discipline", INTENT_ACTIONS)

    def test_clamp_unit_covers_edge_values(self) -> None:
        self.assertEqual(clamp_unit(0.25), 0.25)
        self.assertEqual(clamp_unit(-9), -1.0)
        self.assertEqual(clamp_unit(float("-inf")), 0.0)
        self.assertEqual(clamp_unit("0.5"), 0.0)
        self.assertEqual(clamp_unit(True), 0.0)
        self.assertTrue(math.isfinite(clamp_unit(float("nan"))))

    def test_player_name_sanitization(self) -> None:
        self.assertEqual(sanitize_player_name("  Matti\tthe\nBold  "), "MattitheBold")
        self.assertEqual(sanitize_player_name("x" * 40), "x" * 16)
        self.assertEqual(sanitize_player_name(None), "")
        self.assertEqual(sanitize_player_name("a\x00b\x1fc"), "abc")


class RunIdTests(unittest.TestCase):
    def test_generator_length_and_alphabet(self) -> None:
        self.assertEqual(MP_RUN_ID_LENGTH, 4)
        # The read-aloud-safe alphabet drops 0/O/1/I.
        for ambiguous in "0O1I":
            self.assertNotIn(ambiguous, MP_RUN_ID_ALPHABET)
        self.assertEqual(len(MP_RUN_ID_ALPHABET), 32)
        for _ in range(64):
            run_id = generate_run_id()
            self.assertEqual(len(run_id), MP_RUN_ID_LENGTH)
            self.assertTrue(all(c in MP_RUN_ID_ALPHABET for c in run_id))
            self.assertTrue(is_valid_run_id(run_id, length=MP_RUN_ID_LENGTH))
        # Longer configured codes work for hardened deployments.
        self.assertEqual(len(generate_run_id(12)), 12)

    def test_normalization_and_validation(self) -> None:
        self.assertEqual(normalize_run_id("  ab2c \n"), "AB2C")
        self.assertTrue(is_valid_run_id("ab2c", length=4))
        self.assertFalse(is_valid_run_id("AB2", length=4))
        self.assertFalse(is_valid_run_id("AB20", length=4))  # 0 not in alphabet
        self.assertFalse(is_valid_run_id("", length=4))
        self.assertFalse(is_valid_run_id(None, length=4))
        self.assertFalse(is_valid_run_id("A" * 40))

    def test_reconnect_token_is_128_bit_opaque_hex(self) -> None:
        token = generate_reconnect_token()
        self.assertEqual(len(token), 32)
        int(token, 16)  # hex-parsable
        self.assertNotEqual(token, generate_reconnect_token())


if __name__ == "__main__":
    unittest.main()
