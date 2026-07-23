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

"""Line-delimited JSON wire codec for Arch Rogue multiplayer (protocol v1).

One JSON **object** per UTF-8, ``\\n``-terminated line. The server is a relay:
it validates and routes messages but never simulates the world. This module is
stdlib-only by contract — the standalone server consumes it via a local path
dependency and must never need Pygame or the game package.
"""

from __future__ import annotations

import getpass
import json
import math
import secrets

__all__ = [
    "MP_PROTOCOL_VERSION",
    "MP_MAX_MESSAGE_BYTES",
    "MP_RUN_ID_ALPHABET",
    "MP_RUN_ID_LENGTH",
    "MP_RUN_ID_MAX_LENGTH",
    "MP_PLAYER_NAME_MAX_CHARS",
    "MP_HELLO_TIMEOUT_SECONDS",
    "MP_RECONNECT_GRACE_SECONDS",
    "MP_ROOM_IDLE_TIMEOUT_SECONDS",
    "MP_SNAPSHOT_RATE_HZ",
    "MP_INTENT_RATE_HZ",
    "ROLE_HOST",
    "ROLE_JOIN",
    "ROOM_WAITING_FOR_JOIN",
    "ROOM_SELECTING",
    "ROOM_ACTIVE",
    "ROOM_CLOSED",
    "ROOM_STATES",
    "ERROR_RUN_FULL",
    "ERROR_RUN_NOT_FOUND",
    "ERROR_RUN_ID_IN_USE",
    "ERROR_BAD_MSG",
    "ERROR_BAD_VERSION",
    "ERROR_BAD_REVISION",
    "ERROR_ROLE_FORBIDDEN",
    "ERROR_BAD_STATE",
    "ERROR_TIMEOUT",
    "ERROR_KICKED",
    "CLIENT_MESSAGE_TYPES",
    "SERVER_MESSAGE_TYPES",
    "HOST_ONLY_TYPES",
    "JOIN_ONLY_TYPES",
    "INTENT_ACTIONS",
    "ProtocolError",
    "MessageTooLargeError",
    "LineFramer",
    "encode_message",
    "decode_message",
    "generate_run_id",
    "normalize_run_id",
    "is_valid_run_id",
    "sanitize_player_name",
    "default_player_name",
    "generate_reconnect_token",
    "clamp_unit",
    "is_finite_number",
    "role_allowed",
    "validate_client_message",
    "make_hello",
    "make_ready",
    "make_kick",
    "make_intent",
    "make_floor",
    "make_snapshot",
    "make_run_ended",
    "make_ping",
    "make_pong",
    "make_bye",
    "make_error",
    "make_welcome",
    "make_partner_joined",
    "make_ready_ack",
    "make_start",
    "make_partner_disconnected",
    "make_partner_rejoined",
    "make_partner_left",
]

MP_PROTOCOL_VERSION = 1
MP_MAX_MESSAGE_BYTES = 256 * 1024

# Run ids are room locators, not authentication: the alphabet drops 0/O/1/I so
# a code read aloud is unambiguous. Servers exposed to the Internet should
# configure a longer code and rate-limit connection attempts.
MP_RUN_ID_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
MP_RUN_ID_LENGTH = 4
MP_RUN_ID_MAX_LENGTH = 32
MP_PLAYER_NAME_MAX_CHARS = 16

MP_HELLO_TIMEOUT_SECONDS = 10.0
MP_RECONNECT_GRACE_SECONDS = 30.0
MP_ROOM_IDLE_TIMEOUT_SECONDS = 600.0

# Bounded cadences shared by host snapshot emission and joiner intent
# coalescing. Kept here so both sides of the wire agree on the contract.
MP_SNAPSHOT_RATE_HZ = 15.0
MP_INTENT_RATE_HZ = 20.0

ROLE_HOST = "host"
ROLE_JOIN = "join"

ROOM_WAITING_FOR_JOIN = "waiting_for_join"
ROOM_SELECTING = "selecting"
ROOM_ACTIVE = "active"
ROOM_CLOSED = "closed"
ROOM_STATES = (
    ROOM_WAITING_FOR_JOIN,
    ROOM_SELECTING,
    ROOM_ACTIVE,
    ROOM_CLOSED,
)

ERROR_RUN_FULL = "run_full"
ERROR_RUN_NOT_FOUND = "run_not_found"
ERROR_RUN_ID_IN_USE = "run_id_in_use"
ERROR_BAD_MSG = "bad_msg"
ERROR_BAD_VERSION = "bad_version"
ERROR_BAD_REVISION = "bad_revision"
ERROR_ROLE_FORBIDDEN = "role_forbidden"
ERROR_BAD_STATE = "bad_state"
ERROR_TIMEOUT = "timeout"
# 4.6.x: the host turned the joiner away in the lobby (partner accept gate).
ERROR_KICKED = "kicked"

CLIENT_MESSAGE_TYPES = frozenset(
    (
        "hello",
        "ready",
        "kick",
        "floor",
        "snapshot",
        "intent",
        "run_ended",
        "ping",
        "bye",
    )
)
SERVER_MESSAGE_TYPES = frozenset(
    (
        "welcome",
        "partner_joined",
        "ready_ack",
        "start",
        "floor",
        "snapshot",
        "intent",
        "partner_disconnected",
        "partner_rejoined",
        "partner_left",
        "run_ended",
        "pong",
        "error",
        "bye",
    )
)
HOST_ONLY_TYPES = frozenset(("floor", "snapshot", "run_ended", "kick"))
JOIN_ONLY_TYPES = frozenset(("intent",))

# Documented finite intent action enum. ``use_slot``/``drop_slot`` carry the
# inventory slot index in ``target``; ``choose_discipline`` carries the
# discipline node key; ``interact`` targets the nearest host-validated
# interactable. Movement fields of an action intent carry the aim vector.
INTENT_ACTIONS = (
    "",
    "melee",
    "bolt",
    "skill",
    "dash",
    "potion_hp",
    "potion_mana",
    "interact",
    "use_slot",
    "drop_slot",
    "choose_discipline",
)


class ProtocolError(ValueError):
    """A malformed, oversized, or schema-invalid wire message."""

    def __init__(self, message: str, code: str = ERROR_BAD_MSG) -> None:
        super().__init__(message)
        self.code = code


class MessageTooLargeError(ProtocolError):
    """A line exceeded MP_MAX_MESSAGE_BYTES."""


def _reject_constant(token: str) -> float:
    raise ProtocolError(f"non-finite number {token!r} is not allowed")


def encode_message(message: dict) -> bytes:
    """Encode one message dict as a compact, newline-terminated JSON line."""

    if not isinstance(message, dict):
        raise ProtocolError("message must be a JSON object")
    message_type = message.get("t")
    if not isinstance(message_type, str) or not message_type:
        raise ProtocolError("message must carry a non-empty string 't'")
    try:
        text = json.dumps(
            message,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ProtocolError(f"message is not JSON-serializable: {exc}") from exc
    payload = text.encode("utf-8")
    if len(payload) + 1 > MP_MAX_MESSAGE_BYTES:
        raise MessageTooLargeError(
            f"encoded message is {len(payload)} bytes "
            f"(limit {MP_MAX_MESSAGE_BYTES})"
        )
    return payload + b"\n"


def decode_message(line: bytes | bytearray | memoryview | str) -> dict:
    """Decode one wire line into a validated message dict.

    Raises :class:`ProtocolError` for malformed UTF-8/JSON, non-object
    payloads, oversized lines, non-finite numbers, and missing/invalid ``t``.
    """

    if isinstance(line, (bytes, bytearray, memoryview)):
        raw = bytes(line)
        if len(raw) > MP_MAX_MESSAGE_BYTES:
            raise MessageTooLargeError(
                f"line is {len(raw)} bytes (limit {MP_MAX_MESSAGE_BYTES})"
            )
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProtocolError(f"line is not valid UTF-8: {exc}") from exc
    elif isinstance(line, str):
        text = line
        if len(text.encode("utf-8", errors="replace")) > MP_MAX_MESSAGE_BYTES:
            raise MessageTooLargeError("line exceeds the message size limit")
    else:
        raise ProtocolError("line must be bytes or str")
    text = text.strip("\r\n")
    if not text.strip():
        raise ProtocolError("line is empty")
    try:
        message = json.loads(text, parse_constant=_reject_constant)
    except ProtocolError:
        raise
    except (TypeError, ValueError) as exc:
        raise ProtocolError(f"line is not valid JSON: {exc}") from exc
    if not isinstance(message, dict):
        raise ProtocolError("message must be a JSON object")
    message_type = message.get("t")
    if not isinstance(message_type, str) or not message_type:
        raise ProtocolError("message must carry a non-empty string 't'")
    return message


class LineFramer:
    """Reassemble newline-delimited frames from arbitrary TCP chunks.

    Handles fragmented and coalesced lines. Raises
    :class:`MessageTooLargeError` (and drops the buffered overflow) when a
    single line exceeds ``max_line_bytes``, so a hostile peer cannot grow the
    buffer without bound; the caller should disconnect that peer.
    """

    def __init__(self, max_line_bytes: int = MP_MAX_MESSAGE_BYTES) -> None:
        self.max_line_bytes = int(max_line_bytes)
        self._buffer = bytearray()

    def feed(self, data: bytes) -> list[bytes]:
        if not data:
            return []
        self._buffer.extend(data)
        lines: list[bytes] = []
        while True:
            newline = self._buffer.find(b"\n")
            if newline < 0:
                break
            line = bytes(self._buffer[:newline])
            del self._buffer[: newline + 1]
            if len(line) > self.max_line_bytes:
                self._buffer.clear()
                raise MessageTooLargeError(
                    f"line is {len(line)} bytes (limit {self.max_line_bytes})"
                )
            if line.strip():
                lines.append(line)
        if len(self._buffer) > self.max_line_bytes:
            self._buffer.clear()
            raise MessageTooLargeError(
                "partial line exceeded the message size limit"
            )
        return lines

    def pending_bytes(self) -> int:
        return len(self._buffer)

    def reset(self) -> None:
        self._buffer.clear()


def generate_run_id(length: int = MP_RUN_ID_LENGTH) -> str:
    """Generate a run id with ``secrets.choice`` (never the game RNG)."""

    length = max(1, min(MP_RUN_ID_MAX_LENGTH, int(length)))
    return "".join(secrets.choice(MP_RUN_ID_ALPHABET) for _ in range(length))


def normalize_run_id(text: object) -> str:
    if not isinstance(text, str):
        return ""
    return text.strip().upper()


def is_valid_run_id(text: object, length: int | None = None) -> bool:
    normalized = normalize_run_id(text)
    if not normalized or len(normalized) > MP_RUN_ID_MAX_LENGTH:
        return False
    if length is not None and len(normalized) != int(length):
        return False
    return all(char in MP_RUN_ID_ALPHABET for char in normalized)


def sanitize_player_name(name: object) -> str:
    """Strip control characters, collapse whitespace, cap the display length."""

    if not isinstance(name, str):
        return ""
    cleaned = "".join(
        char for char in name if char.isprintable() and char not in "\r\n\t"
    )
    cleaned = " ".join(cleaned.split())
    return cleaned[:MP_PLAYER_NAME_MAX_CHARS]


def default_player_name(fallback: str = "Warden") -> str:
    """Sanitized OS username when available, otherwise ``fallback``."""

    try:
        candidate = sanitize_player_name(getpass.getuser())
    except (KeyError, OSError, ValueError):
        candidate = ""
    return candidate or fallback


def generate_reconnect_token() -> str:
    """A server-generated 128-bit opaque secret bound to one room slot."""

    return secrets.token_hex(16)


def is_finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def clamp_unit(value: object) -> float:
    """Coerce a movement component to a finite float clamped to [-1, 1]."""

    if not is_finite_number(value):
        return 0.0
    return max(-1.0, min(1.0, float(value)))


def role_allowed(message_type: str, role: str) -> bool:
    """Whether a client role may originate ``message_type``."""

    if message_type in HOST_ONLY_TYPES:
        return role == ROLE_HOST
    if message_type in JOIN_ONLY_TYPES:
        return role == ROLE_JOIN
    return True


def _is_nonneg_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_pos_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def validate_client_message(message: dict) -> str:
    """Structurally validate a decoded client message.

    Returns an empty string when the message is acceptable, otherwise an error
    code (``bad_msg``). Role routing (host-only/join-only) and room-state rules
    are the server's job; this checks field presence and types only.
    """

    message_type = message.get("t")
    if not isinstance(message_type, str) or not message_type:
        return ERROR_BAD_MSG
    if message_type == "hello":
        if not _is_pos_int(message.get("seq")):
            return ERROR_BAD_MSG
        if not isinstance(message.get("protocol_version"), int):
            return ERROR_BAD_MSG
        if not isinstance(message.get("content_revision"), str):
            return ERROR_BAD_MSG
        if not isinstance(message.get("name"), str):
            return ERROR_BAD_MSG
        if not isinstance(message.get("run_id"), str):
            return ERROR_BAD_MSG
        if message.get("role") not in (ROLE_HOST, ROLE_JOIN):
            return ERROR_BAD_MSG
        token = message.get("reconnect_token")
        if token is not None and not isinstance(token, str):
            return ERROR_BAD_MSG
    elif message_type == "ready":
        if not _is_pos_int(message.get("seq")):
            return ERROR_BAD_MSG
        archetype_key = message.get("archetype_key")
        if not isinstance(archetype_key, str) or not archetype_key:
            return ERROR_BAD_MSG
        run_seed = message.get("run_seed")
        if run_seed is not None and not _is_nonneg_int(run_seed):
            return ERROR_BAD_MSG
    elif message_type == "kick":
        if not _is_pos_int(message.get("seq")):
            return ERROR_BAD_MSG
    elif message_type == "floor":
        if not _is_nonneg_int(message.get("floor_revision")):
            return ERROR_BAD_MSG
        if not _is_pos_int(message.get("depth")):
            return ERROR_BAD_MSG
        if not _is_nonneg_int(message.get("floor_seed")):
            return ERROR_BAD_MSG
        if not isinstance(message.get("state"), dict):
            return ERROR_BAD_MSG
    elif message_type == "snapshot":
        if not _is_nonneg_int(message.get("floor_revision")):
            return ERROR_BAD_MSG
        if not _is_nonneg_int(message.get("tick")):
            return ERROR_BAD_MSG
        if not isinstance(message.get("state"), dict):
            return ERROR_BAD_MSG
    elif message_type == "intent":
        if not _is_nonneg_int(message.get("input_seq")):
            return ERROR_BAD_MSG
        if not is_finite_number(message.get("move_x", 0.0)):
            return ERROR_BAD_MSG
        if not is_finite_number(message.get("move_y", 0.0)):
            return ERROR_BAD_MSG
        if message.get("action", "") not in INTENT_ACTIONS:
            return ERROR_BAD_MSG
        target = message.get("target")
        if target is not None and not isinstance(target, str):
            return ERROR_BAD_MSG
        # Optional predicted-position claim (4.7.6): both-or-neither, finite.
        claim_x = message.get("px")
        claim_y = message.get("py")
        if (claim_x is None) != (claim_y is None):
            return ERROR_BAD_MSG
        if claim_x is not None and not (
            is_finite_number(claim_x) and is_finite_number(claim_y)
        ):
            return ERROR_BAD_MSG
    elif message_type == "run_ended":
        if not isinstance(message.get("outcome"), str):
            return ERROR_BAD_MSG
        results = message.get("results", [])
        if not isinstance(results, list):
            return ERROR_BAD_MSG
    elif message_type == "ping":
        if not _is_pos_int(message.get("seq")):
            return ERROR_BAD_MSG
        if not is_finite_number(message.get("ts", 0.0)):
            return ERROR_BAD_MSG
    elif message_type == "bye":
        pass
    else:
        # Unknown types are tolerated for forward compatibility; the server
        # logs and ignores them rather than rejecting the peer.
        return ""
    return ""


# --- Canonical message builders ------------------------------------------
# Both projects build wire dicts through these helpers so field names never
# drift between the client and the relay.


def make_hello(
    *,
    seq: int,
    name: str,
    run_id: str,
    role: str,
    content_revision: str,
    reconnect_token: str = "",
) -> dict:
    message = {
        "t": "hello",
        "seq": int(seq),
        "protocol_version": MP_PROTOCOL_VERSION,
        "content_revision": str(content_revision),
        "name": sanitize_player_name(name),
        "run_id": normalize_run_id(run_id),
        "role": str(role),
    }
    if reconnect_token:
        message["reconnect_token"] = str(reconnect_token)
    return message


def make_ready(*, seq: int, archetype_key: str, run_seed: int | None = None) -> dict:
    message = {
        "t": "ready",
        "seq": int(seq),
        "archetype_key": str(archetype_key),
    }
    if run_seed is not None:
        message["run_seed"] = int(run_seed)
    return message


def make_intent(
    *,
    input_seq: int,
    move_x: float = 0.0,
    move_y: float = 0.0,
    action: str = "",
    target: str | None = None,
    px: float | None = None,
    py: float | None = None,
    fx: float | None = None,
    fy: float | None = None,
) -> dict:
    if action not in INTENT_ACTIONS:
        raise ProtocolError(f"unknown intent action {action!r}")
    message = {
        "t": "intent",
        "input_seq": int(input_seq),
        "move_x": clamp_unit(move_x),
        "move_y": clamp_unit(move_y),
        "action": action,
        "target": str(target) if target is not None else None,
    }
    # 4.7.6: a movement intent may carry the joiner's predicted position so
    # the host can settle the remote actor exactly where the joiner stopped
    # (additive optional fields; older peers ignore them).
    if px is not None and py is not None:
        message["px"] = round(float(px), 3)
        message["py"] = round(float(py), 3)
    # 4.7.9: a movement intent may carry the joiner's facing so mouse-hover/
    # right-stick aim — which turns the actor without moving it — reaches the
    # host's view of the idle remote actor (additive optional fields).
    if fx is not None and fy is not None:
        message["fx"] = round(clamp_unit(fx), 3)
        message["fy"] = round(clamp_unit(fy), 3)
    return message


def make_floor(
    *, floor_revision: int, depth: int, floor_seed: int, state: dict
) -> dict:
    return {
        "t": "floor",
        "floor_revision": int(floor_revision),
        "depth": int(depth),
        "floor_seed": int(floor_seed),
        "state": dict(state),
    }


def make_snapshot(*, floor_revision: int, tick: int, state: dict) -> dict:
    return {
        "t": "snapshot",
        "floor_revision": int(floor_revision),
        "tick": int(tick),
        "state": dict(state),
    }


def make_run_ended(*, outcome: str, results: list[dict] | None = None) -> dict:
    return {
        "t": "run_ended",
        "outcome": str(outcome),
        "results": list(results or []),
    }


def make_kick(*, seq: int) -> dict:
    """Host → server: turn away the joiner currently in the lobby."""

    return {"t": "kick", "seq": int(seq)}


def make_ping(*, seq: int, ts: float) -> dict:
    return {"t": "ping", "seq": int(seq), "ts": float(ts)}


def make_pong(*, seq: int, ts: float) -> dict:
    return {"t": "pong", "seq": int(seq), "ts": float(ts)}


def make_bye() -> dict:
    return {"t": "bye"}


def make_error(
    *, code: str, msg: str, fatal: bool, seq: int | None = None
) -> dict:
    message = {
        "t": "error",
        "code": str(code),
        "msg": str(msg),
        "fatal": bool(fatal),
    }
    if seq is not None:
        message["seq"] = int(seq)
    return message


def make_welcome(
    *,
    seq: int,
    run_id: str,
    you_are: str,
    player_id: str,
    reconnect_token: str,
    partner_name: str | None = None,
    partner_ready: bool = False,
) -> dict:
    message = {
        "t": "welcome",
        "seq": int(seq),
        "run_id": normalize_run_id(run_id),
        "you_are": str(you_are),
        "player_id": str(player_id),
        "partner_ready": bool(partner_ready),
        "reconnect_token": str(reconnect_token),
    }
    if partner_name is not None:
        message["partner_name"] = sanitize_player_name(partner_name)
    return message


def make_partner_joined(*, name: str, player_id: str) -> dict:
    return {
        "t": "partner_joined",
        "name": sanitize_player_name(name),
        "player_id": str(player_id),
    }


def make_ready_ack(*, seq: int, player_id: str, archetype_key: str) -> dict:
    return {
        "t": "ready_ack",
        "seq": int(seq),
        "player_id": str(player_id),
        "archetype_key": str(archetype_key),
    }


def make_start(
    *,
    run_seed: int,
    host_player_id: str,
    host_name: str,
    host_archetype: str,
    joiner_player_id: str,
    joiner_name: str,
    joiner_archetype: str,
) -> dict:
    return {
        "t": "start",
        "run_seed": int(run_seed),
        "host_player_id": str(host_player_id),
        "host_name": sanitize_player_name(host_name),
        "host_archetype": str(host_archetype),
        "joiner_player_id": str(joiner_player_id),
        "joiner_name": sanitize_player_name(joiner_name),
        "joiner_archetype": str(joiner_archetype),
    }


def make_partner_disconnected(*, grace_seconds: float) -> dict:
    return {
        "t": "partner_disconnected",
        "grace_seconds": float(grace_seconds),
    }


def make_partner_rejoined(*, name: str, player_id: str) -> dict:
    return {
        "t": "partner_rejoined",
        "name": sanitize_player_name(name),
        "player_id": str(player_id),
    }


def make_partner_left() -> dict:
    return {"t": "partner_left"}
