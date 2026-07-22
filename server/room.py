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

"""Transport-agnostic room registry and message routing for the MP relay.

The hub never simulates the world: it validates and routes. All methods are
synchronous and single-threaded by contract (the asyncio shell serializes
calls; tests call directly with a fake clock). Transports are anything with
``send_message(dict)`` and ``close()``.
"""

from __future__ import annotations

import hmac
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from .config import ServerConfig
from .protocol import (
    ERROR_BAD_MSG,
    ERROR_BAD_REVISION,
    ERROR_BAD_STATE,
    ERROR_BAD_VERSION,
    ERROR_KICKED,
    ERROR_ROLE_FORBIDDEN,
    ERROR_RUN_FULL,
    ERROR_RUN_ID_IN_USE,
    ERROR_RUN_NOT_FOUND,
    ERROR_TIMEOUT,
    MP_PROTOCOL_VERSION,
    ROLE_HOST,
    ROLE_JOIN,
    ROOM_ACTIVE,
    ROOM_CLOSED,
    ROOM_SELECTING,
    ROOM_WAITING_FOR_JOIN,
    clamp_unit,
    generate_reconnect_token,
    is_valid_run_id,
    make_error,
    make_partner_disconnected,
    make_partner_joined,
    make_partner_left,
    make_partner_rejoined,
    make_pong,
    make_ready_ack,
    make_start,
    make_welcome,
    normalize_run_id,
    role_allowed,
    sanitize_player_name,
    validate_client_message,
)

log = logging.getLogger("arch_rogue_server")

_UNKNOWN_TYPE_LOG_FIRST = 3
_UNKNOWN_TYPE_LOG_EVERY = 100


class PeerTransport(Protocol):
    def send_message(self, message: dict) -> None: ...

    def close(self) -> None: ...


@dataclass(eq=False)
class Connection:
    """One accepted socket-level peer (pre- or post-hello).

    ``eq=False`` keeps identity hashing so connections can live in sets.
    """

    transport: PeerTransport
    connected_at: float
    peer_label: str = ""
    hello_done: bool = False
    closed: bool = False
    room: "Room | None" = None
    role: str = ""
    last_seq: int = 0
    unknown_type_count: int = 0

    def send(self, message: dict) -> None:
        if self.closed:
            return
        try:
            self.transport.send_message(message)
        except Exception:  # noqa: BLE001 - a dying peer must not crash the room
            log.debug("send to %s failed", self.peer_label, exc_info=True)

    def hard_close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            self.transport.close()
        except Exception:  # noqa: BLE001
            log.debug("close of %s failed", self.peer_label, exc_info=True)


@dataclass
class PlayerSlot:
    """One of the two per-room player seats (host or joiner)."""

    role: str
    player_id: str
    name: str = ""
    archetype_key: str = ""
    ready: bool = False
    run_seed: int | None = None
    reconnect_token: str = ""
    connection: Connection | None = None
    disconnected_at: float | None = None
    left: bool = False

    @property
    def connected(self) -> bool:
        return self.connection is not None and not self.connection.closed

    @property
    def reserved(self) -> bool:
        """A grace-period reservation only a reconnect token can reclaim."""

        return (
            not self.left
            and not self.connected
            and self.disconnected_at is not None
        )


@dataclass
class Room:
    run_id: str
    created_at: float
    content_revision: str = ""
    state: str = ROOM_WAITING_FOR_JOIN
    last_activity: float = 0.0
    started: bool = False
    slots: dict[str, PlayerSlot] = field(default_factory=dict)
    # Opaque relayed payloads retained so a reconnecting joiner receives the
    # latest floor descriptor and a fresh snapshot before input re-enables.
    latest_floor: dict[str, Any] | None = None
    latest_snapshot: dict[str, Any] | None = None

    def slot(self, role: str) -> PlayerSlot | None:
        return self.slots.get(role)

    def partner_slot(self, role: str) -> PlayerSlot | None:
        return self.slots.get(ROLE_JOIN if role == ROLE_HOST else ROLE_HOST)

    def touch(self, now: float) -> None:
        self.last_activity = now

    @property
    def occupied_count(self) -> int:
        return sum(
            1 for slot in self.slots.values() if slot.connected or slot.reserved
        )


class RoomHub:
    """All rooms plus per-connection routing. Ephemeral and in-memory."""

    def __init__(
        self,
        config: ServerConfig | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config or ServerConfig()
        self.clock = clock
        self.rooms: dict[str, Room] = {}
        self.connections: set[Connection] = set()

    # -- connection lifecycle ------------------------------------------------

    def connect(self, transport: PeerTransport, peer_label: str = "") -> Connection:
        connection = Connection(
            transport=transport,
            connected_at=self.clock(),
            peer_label=peer_label or f"peer-{id(transport):x}",
        )
        self.connections.add(connection)
        return connection

    def disconnect(self, connection: Connection, *, expected: bool = False) -> None:
        """The transport reports this peer's socket is gone.

        ``expected`` marks disconnects the hub itself initiated (post-``bye``
        or fatal error); those never reserve a reconnect slot.
        """

        self.connections.discard(connection)
        connection.closed = True
        room = connection.room
        if room is None:
            return
        slot = room.slot(connection.role)
        connection.room = None
        if slot is None or slot.connection is not connection:
            return
        slot.connection = None
        if slot.left or expected:
            slot.left = True
            slot.disconnected_at = None
            self._maybe_close_room(room)
            return
        if self.config.reconnect_grace <= 0.0:
            self._finalize_slot_departure(room, slot)
            return
        slot.disconnected_at = self.clock()
        partner = room.partner_slot(slot.role)
        if partner is not None and partner.connection is not None:
            partner.connection.send(
                make_partner_disconnected(
                    grace_seconds=self.config.reconnect_grace
                )
            )
        log.info(
            "room %s: %s disconnected unexpectedly (grace %.0fs)",
            room.run_id,
            slot.role,
            self.config.reconnect_grace,
        )

    # -- inbound routing -----------------------------------------------------

    def handle_message(self, connection: Connection, message: dict) -> None:
        if connection.closed:
            return
        message_type = str(message.get("t", ""))
        if not connection.hello_done:
            if message_type != "hello":
                self._fatal(
                    connection,
                    ERROR_BAD_MSG,
                    "the first message must be hello",
                )
                return
            self._handle_hello(connection, message)
            return

        structural_error = validate_client_message(message)
        if structural_error:
            self._reply_error(
                connection,
                structural_error,
                f"invalid {message_type} message",
                seq=self._reply_seq(message),
            )
            return

        room = connection.room
        if room is None or room.state == ROOM_CLOSED:
            self._fatal(connection, ERROR_BAD_STATE, "room is closed")
            return

        if message_type not in (
            "hello",
            "ready",
            "kick",
            "floor",
            "snapshot",
            "intent",
            "run_ended",
            "ping",
            "bye",
        ):
            self._note_unknown_type(connection, message_type)
            return

        if not role_allowed(message_type, connection.role):
            self._reply_error(
                connection,
                ERROR_ROLE_FORBIDDEN,
                f"{connection.role} may not send {message_type}",
                seq=self._reply_seq(message),
            )
            return

        if message_type in ("ready", "kick", "ping"):
            if not self._accept_seq(connection, message):
                return

        handler = {
            "ready": self._handle_ready,
            "kick": self._handle_kick,
            "floor": self._handle_floor,
            "snapshot": self._handle_snapshot,
            "intent": self._handle_intent,
            "run_ended": self._handle_run_ended,
            "ping": self._handle_ping,
            "bye": self._handle_bye,
        }[message_type]
        handler(connection, room, message)

    def handle_protocol_violation(
        self, connection: Connection, detail: str
    ) -> None:
        """Framing/decoding failed for this peer: reject without room damage."""

        self._fatal(connection, ERROR_BAD_MSG, detail)

    # -- timers --------------------------------------------------------------

    def tick(self) -> None:
        """Expire hello timeouts, reconnect grace windows, and idle rooms."""

        now = self.clock()
        for connection in [
            connection
            for connection in self.connections
            if not connection.hello_done
            and now - connection.connected_at > self.config.hello_timeout
        ]:
            self._fatal(connection, ERROR_TIMEOUT, "hello timeout")

        for room in list(self.rooms.values()):
            for slot in list(room.slots.values()):
                if (
                    slot.reserved
                    and slot.disconnected_at is not None
                    and now - slot.disconnected_at > self.config.reconnect_grace
                ):
                    self._finalize_slot_departure(room, slot)
            if room.run_id not in self.rooms:
                continue
            if now - room.last_activity > self.config.idle_timeout:
                log.info("room %s: idle timeout", room.run_id)
                # Tell every live peer before the close tears connections down.
                for slot in room.slots.values():
                    if slot.connection is not None:
                        slot.connection.send(
                            make_error(
                                code=ERROR_TIMEOUT,
                                msg="room idle timeout",
                                fatal=True,
                            )
                        )
                self._close_room(room)

    # -- hello ---------------------------------------------------------------

    def _handle_hello(self, connection: Connection, message: dict) -> None:
        structural_error = validate_client_message(message)
        if structural_error or str(message.get("t")) != "hello":
            self._fatal(connection, ERROR_BAD_MSG, "invalid hello")
            return
        seq = int(message["seq"])
        if int(message["protocol_version"]) != MP_PROTOCOL_VERSION:
            self._fatal(
                connection,
                ERROR_BAD_VERSION,
                f"protocol {message['protocol_version']} is unsupported "
                f"(server speaks {MP_PROTOCOL_VERSION})",
                seq=seq,
            )
            return
        run_id = normalize_run_id(message["run_id"])
        role = str(message["role"])
        name = sanitize_player_name(message["name"])
        revision = str(message["content_revision"])
        token = str(message.get("reconnect_token", "") or "")

        if token and self._try_reconnect(connection, message, token):
            return

        if not is_valid_run_id(run_id, length=self.config.run_id_length):
            self._fatal(
                connection,
                ERROR_RUN_NOT_FOUND if role == ROLE_JOIN else ERROR_BAD_MSG,
                f"run id must be {self.config.run_id_length} characters "
                "from the run-id alphabet",
                seq=seq,
            )
            return

        room = self.rooms.get(run_id)
        if role == ROLE_HOST:
            if room is not None:
                self._fatal(
                    connection,
                    ERROR_RUN_ID_IN_USE,
                    "a run with this code already exists",
                    seq=seq,
                )
                return
            if len(self.rooms) >= self.config.max_rooms:
                self._fatal(
                    connection,
                    ERROR_RUN_FULL,
                    "the server is at its room limit",
                    seq=seq,
                )
                return
            room = Room(
                run_id=run_id,
                created_at=self.clock(),
                content_revision=revision,
            )
            room.touch(self.clock())
            room.slots[ROLE_HOST] = PlayerSlot(
                role=ROLE_HOST,
                player_id="p1",
                name=name,
                reconnect_token=generate_reconnect_token(),
            )
            self.rooms[run_id] = room
            self._bind(connection, room, room.slots[ROLE_HOST], seq)
            log.info("room %s: created by host %r", run_id, name)
            return

        # Joiner path.
        if room is None:
            self._fatal(
                connection,
                ERROR_RUN_NOT_FOUND,
                "no run with this code is waiting",
                seq=seq,
            )
            return
        if room.state != ROOM_WAITING_FOR_JOIN or room.occupied_count != 1:
            self._fatal(
                connection,
                ERROR_RUN_FULL,
                "this run is not open for joining",
                seq=seq,
            )
            return
        joiner = room.slot(ROLE_JOIN)
        if joiner is not None and (joiner.connected or joiner.reserved):
            self._fatal(
                connection, ERROR_RUN_FULL, "this run already has a partner", seq=seq
            )
            return
        if revision != room.content_revision:
            self._fatal(
                connection,
                ERROR_BAD_REVISION,
                "your game revision does not match the host",
                seq=seq,
            )
            return
        slot = PlayerSlot(
            role=ROLE_JOIN,
            player_id="p2",
            name=name,
            reconnect_token=generate_reconnect_token(),
        )
        room.slots[ROLE_JOIN] = slot
        room.state = ROOM_SELECTING
        room.touch(self.clock())
        self._bind(connection, room, slot, seq)
        host = room.slot(ROLE_HOST)
        if host is not None and host.connection is not None:
            host.connection.send(
                make_partner_joined(name=slot.name, player_id=slot.player_id)
            )
        log.info("room %s: %r joined", run_id, name)

    def _try_reconnect(
        self, connection: Connection, message: dict, token: str
    ) -> bool:
        run_id = normalize_run_id(message["run_id"])
        room = self.rooms.get(run_id)
        if room is None:
            return False
        for slot in room.slots.values():
            token_matches = bool(slot.reconnect_token) and hmac.compare_digest(
                slot.reconnect_token, token
            )
            if not token_matches or slot.left:
                continue
            if slot.connected:
                # The original socket may be a zombie the transport has not
                # reported dead yet; the token holder is authoritative.
                stale = slot.connection
                slot.connection = None
                if stale is not None:
                    stale.room = None
                    stale.hard_close()
                    self.connections.discard(stale)
            slot.disconnected_at = None
            slot.name = sanitize_player_name(message["name"]) or slot.name
            room.touch(self.clock())
            self._bind(connection, room, slot, int(message["seq"]))
            partner = room.partner_slot(slot.role)
            if partner is not None and partner.connection is not None:
                partner.connection.send(
                    make_partner_rejoined(
                        name=slot.name, player_id=slot.player_id
                    )
                )
            # A rejoined joiner must render from fresh authoritative data
            # before input re-enables: replay the retained floor descriptor
            # and the latest snapshot in order.
            if slot.role == ROLE_JOIN and room.started:
                if room.latest_floor is not None:
                    connection.send(room.latest_floor)
                if room.latest_snapshot is not None:
                    connection.send(room.latest_snapshot)
            log.info("room %s: %s reclaimed by token", room.run_id, slot.role)
            return True
        return False

    def _bind(
        self, connection: Connection, room: Room, slot: PlayerSlot, seq: int
    ) -> None:
        connection.hello_done = True
        connection.room = room
        connection.role = slot.role
        connection.last_seq = seq
        slot.connection = connection
        slot.disconnected_at = None
        partner = room.partner_slot(slot.role)
        connection.send(
            make_welcome(
                seq=seq,
                run_id=room.run_id,
                you_are=slot.role,
                player_id=slot.player_id,
                reconnect_token=slot.reconnect_token,
                partner_name=(
                    partner.name
                    if partner is not None and (partner.connected or partner.reserved)
                    else None
                ),
                partner_ready=bool(partner is not None and partner.ready),
            )
        )

    # -- post-hello handlers -------------------------------------------------

    def _handle_ready(
        self, connection: Connection, room: Room, message: dict
    ) -> None:
        if room.state not in (ROOM_WAITING_FOR_JOIN, ROOM_SELECTING):
            self._reply_error(
                connection,
                ERROR_BAD_STATE,
                "the run has already started",
                seq=self._reply_seq(message),
            )
            return
        slot = room.slot(connection.role)
        if slot is None:
            return
        run_seed = message.get("run_seed")
        if connection.role == ROLE_HOST:
            if run_seed is None:
                self._reply_error(
                    connection,
                    ERROR_BAD_MSG,
                    "host ready must carry run_seed",
                    seq=self._reply_seq(message),
                )
                return
            slot.run_seed = int(run_seed)
        elif run_seed is not None:
            self._reply_error(
                connection,
                ERROR_ROLE_FORBIDDEN,
                "only the host supplies run_seed",
                seq=self._reply_seq(message),
            )
            return
        slot.archetype_key = str(message["archetype_key"])
        slot.ready = True
        room.touch(self.clock())
        seq = int(message["seq"])
        connection.send(
            make_ready_ack(
                seq=seq,
                player_id=slot.player_id,
                archetype_key=slot.archetype_key,
            )
        )
        partner = room.partner_slot(slot.role)
        if partner is not None and partner.connection is not None:
            ack = make_ready_ack(
                seq=0,
                player_id=slot.player_id,
                archetype_key=slot.archetype_key,
            )
            del ack["seq"]  # unsolicited events never invent a seq
            partner.connection.send(ack)
        self._maybe_start(room)

    def _maybe_start(self, room: Room) -> None:
        if room.started:
            return
        host = room.slot(ROLE_HOST)
        joiner = room.slot(ROLE_JOIN)
        if (
            host is None
            or joiner is None
            or not (host.ready and host.archetype_key and host.run_seed is not None)
            or not (joiner.ready and joiner.archetype_key)
            or not host.connected
            or not joiner.connected
        ):
            return
        room.started = True
        room.state = ROOM_ACTIVE
        room.touch(self.clock())
        start = make_start(
            run_seed=int(host.run_seed),
            host_player_id=host.player_id,
            host_name=host.name,
            host_archetype=host.archetype_key,
            joiner_player_id=joiner.player_id,
            joiner_name=joiner.name,
            joiner_archetype=joiner.archetype_key,
        )
        for slot in (host, joiner):
            if slot.connection is not None:
                slot.connection.send(start)
        log.info(
            "room %s: started (host=%s joiner=%s)",
            room.run_id,
            host.archetype_key,
            joiner.archetype_key,
        )

    def _handle_kick(
        self, connection: Connection, room: Room, message: dict
    ) -> None:
        """Host turns the joiner away in the lobby (partner accept gate).

        Only meaningful before start: the joiner slot is released with a
        fatal ``kicked`` error, ``_finalize_slot_departure`` tells the host
        via ``partner_left``, and the room reopens for another knock.
        """

        seq = self._reply_seq(message)
        joiner = room.slot(ROLE_JOIN)
        if room.started or room.state != ROOM_SELECTING or joiner is None:
            self._reply_error(
                connection,
                ERROR_BAD_STATE,
                "there is no lobby partner to turn away",
                seq=seq,
            )
            return
        log.info("room %s: host turned away %r", room.run_id, joiner.name)
        if joiner.connection is not None:
            # _fatal finalizes the slot departure, which pops the join seat
            # and returns the room to waiting-for-join.
            self._fatal(
                joiner.connection, ERROR_KICKED, "the host turned you away"
            )
        else:
            # The joiner is inside a reconnect-grace window: release the
            # reservation directly so the token cannot reclaim the seat.
            self._finalize_slot_departure(room, joiner)
        host = room.slot(ROLE_HOST)
        if host is not None:
            # The accept gate keeps an honest host from readying while a
            # knock is pending; reset defensively for modified clients.
            host.ready = False
            host.run_seed = None
        room.touch(self.clock())

    def _handle_floor(
        self, connection: Connection, room: Room, message: dict
    ) -> None:
        room.latest_floor = message
        room.latest_snapshot = None
        room.touch(self.clock())
        self._relay_to_partner(room, connection.role, message)

    def _handle_snapshot(
        self, connection: Connection, room: Room, message: dict
    ) -> None:
        room.latest_snapshot = message
        room.touch(self.clock())
        self._relay_to_partner(room, connection.role, message)

    def _handle_intent(
        self, connection: Connection, room: Room, message: dict
    ) -> None:
        slot = room.slot(connection.role)
        if slot is None:
            return
        room.touch(self.clock())
        relayed = dict(message)
        relayed["player_id"] = slot.player_id
        relayed["move_x"] = clamp_unit(relayed.get("move_x", 0.0))
        relayed["move_y"] = clamp_unit(relayed.get("move_y", 0.0))
        self._relay_to_partner(room, connection.role, relayed)

    def _handle_run_ended(
        self, connection: Connection, room: Room, message: dict
    ) -> None:
        room.touch(self.clock())
        self._relay_to_partner(room, connection.role, message)

    def _handle_ping(
        self, connection: Connection, room: Room, message: dict
    ) -> None:
        room.touch(self.clock())
        connection.send(
            make_pong(seq=int(message["seq"]), ts=float(message.get("ts", 0.0)))
        )

    def _handle_bye(
        self, connection: Connection, room: Room, message: dict
    ) -> None:
        slot = room.slot(connection.role)
        if slot is not None:
            self._finalize_slot_departure(room, slot, closing_connection=connection)
        connection.hard_close()
        self.connections.discard(connection)

    # -- shared helpers ------------------------------------------------------

    def _relay_to_partner(
        self, room: Room, from_role: str, message: dict
    ) -> None:
        partner = room.partner_slot(from_role)
        if partner is not None and partner.connection is not None:
            partner.connection.send(message)

    def _finalize_slot_departure(
        self,
        room: Room,
        slot: PlayerSlot,
        *,
        closing_connection: Connection | None = None,
    ) -> None:
        """A departure became final: release the slot and tell the partner."""

        already_left = slot.left
        slot.left = True
        slot.disconnected_at = None
        if slot.connection is not None:
            slot.connection.room = None
            if slot.connection is not closing_connection:
                slot.connection.hard_close()
                self.connections.discard(slot.connection)
            slot.connection = None
        if not already_left:
            partner = room.partner_slot(slot.role)
            if partner is not None and partner.connection is not None:
                partner.connection.send(make_partner_left())
            log.info("room %s: %s left for good", room.run_id, slot.role)
        if slot.role == ROLE_HOST:
            # A room cannot outlive its host: without the sole simulator there
            # is nothing to join or resume.
            self._close_room(room)
            return
        if not room.started:
            # A joiner who departs before start frees the seat: the room
            # returns to waiting so the host can share the code again.
            room.slots.pop(ROLE_JOIN, None)
            room.state = ROOM_WAITING_FOR_JOIN
        self._maybe_close_room(room)

    def _maybe_close_room(self, room: Room) -> None:
        if any(
            slot.connected or slot.reserved for slot in room.slots.values()
        ):
            return
        self._close_room(room)

    def _close_room(self, room: Room) -> None:
        room.state = ROOM_CLOSED
        room.latest_floor = None
        room.latest_snapshot = None
        for slot in room.slots.values():
            if slot.connection is not None:
                connection = slot.connection
                slot.connection = None
                connection.room = None
                connection.hard_close()
                self.connections.discard(connection)
            slot.left = True
            slot.disconnected_at = None
        self.rooms.pop(room.run_id, None)
        log.info("room %s: closed", room.run_id)

    def _accept_seq(self, connection: Connection, message: dict) -> bool:
        seq = message.get("seq")
        if not isinstance(seq, int) or seq <= connection.last_seq:
            self._reply_error(
                connection,
                ERROR_BAD_MSG,
                "seq must be positive and monotonic",
                seq=seq if isinstance(seq, int) else None,
            )
            return False
        connection.last_seq = seq
        return True

    @staticmethod
    def _reply_seq(message: dict) -> int | None:
        seq = message.get("seq")
        return seq if isinstance(seq, int) else None

    def _note_unknown_type(
        self, connection: Connection, message_type: str
    ) -> None:
        connection.unknown_type_count += 1
        count = connection.unknown_type_count
        if count <= _UNKNOWN_TYPE_LOG_FIRST or count % _UNKNOWN_TYPE_LOG_EVERY == 0:
            log.debug(
                "%s: ignoring unknown message type %r (count %d)",
                connection.peer_label,
                message_type,
                count,
            )

    def _reply_error(
        self,
        connection: Connection,
        code: str,
        msg: str,
        *,
        seq: int | None = None,
    ) -> None:
        connection.send(make_error(code=code, msg=msg, fatal=False, seq=seq))

    def _fatal(
        self,
        connection: Connection,
        code: str,
        msg: str,
        *,
        seq: int | None = None,
    ) -> None:
        connection.send(make_error(code=code, msg=msg, fatal=True, seq=seq))
        room = connection.room
        if room is not None:
            slot = room.slot(connection.role)
            if slot is not None and slot.connection is connection:
                # A fatal rejection is an expected departure: no grace window.
                self._finalize_slot_departure(
                    room, slot, closing_connection=connection
                )
        connection.room = None
        connection.hard_close()
        self.connections.discard(connection)
