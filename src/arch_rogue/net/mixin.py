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

"""``NetMixin`` — the Game-side driver of a 4.6 co-op session.

``poll()`` runs once per ``Game.run()`` iteration on the main thread while a
client exists (setup and lobby included) and performs every state change; the
background receiver thread only ever decodes and enqueues. When no session
exists the poll is a two-attribute check and allocates nothing.

The mixin owns: the ``mp_setup``/``mp_lobby`` flow, the handshake, host
snapshot/floor emission, joiner intent emission, remote-intent application on
the host, the reconnect window, and session teardown.
"""

from __future__ import annotations

import math
import time
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

import pygame

from .. import __version__
from ..constants import (
    MP_INTENT_RATE_HZ,
    MP_RECONNECT_GRACE_SECONDS,
    MP_RUN_ID_LENGTH,
    MP_SNAPSHOT_RATE_HZ,
)
from ..models import FloatingText, Player
from . import sync
from .client import (
    ConnectionClosed,
    ConnectionFailed,
    ConnectionLost,
    ConnectionUp,
    InboundMessage,
    MultiplayerClient,
    COALESCE_MOVE_INTENT,
    COALESCE_SNAPSHOT,
)
from .messages import (
    ByeMessage,
    ErrorMessage,
    FloorMessage,
    IntentMessage,
    PartnerDisconnected,
    PartnerJoined,
    PartnerLeft,
    PartnerRejoined,
    PongMessage,
    ReadyAck,
    RunEndedMessage,
    SnapshotMessage,
    Start,
    UnknownMessage,
    Welcome,
)
from .protocol import (
    ROLE_HOST,
    ROLE_JOIN,
    generate_run_id,
    is_valid_run_id,
    make_floor,
    make_hello,
    make_intent,
    make_kick,
    make_ping,
    make_ready,
    make_run_ended,
    make_snapshot,
    normalize_run_id,
    sanitize_player_name,
)

_PING_INTERVAL_SECONDS = 5.0
_INTENT_MOVE_TIMEOUT_SECONDS = 0.6
_SNAPSHOT_INTERVAL = 1.0 / MP_SNAPSHOT_RATE_HZ
_INTENT_INTERVAL = 1.0 / MP_INTENT_RATE_HZ
_RECONNECT_BACKOFF_START = 0.5
_RECONNECT_BACKOFF_CAP = 4.0

# Human-readable notices for recoverable setup failures.
_SETUP_ERROR_NOTICES = {
    "run_id_in_use": "That code is already hosting a run — a fresh code was drawn.",
    "run_not_found": "No run is waiting behind that code.",
    "run_full": "That run already has two players.",
    "bad_revision": "Your game version does not match the host's.",
    "bad_version": "This server speaks a different protocol version.",
    "timeout": "The server timed out the connection.",
    "kicked": "The host turned you away.",
}


@dataclass
class MpSession:
    """Transient co-op session state (never persisted)."""

    role: str = ""
    phase: str = "setup"  # setup | lobby | active | ended
    run_id: str = ""
    player_id: str = ""
    partner_player_id: str = ""
    partner_name: str = ""
    partner_ready: bool = False
    partner_archetype: str = ""
    partner_connected: bool = True
    # Host-side accept gate: True from partner_joined until the host admits
    # or turns away the knocking joiner. Room codes are locators, not
    # secrets, so joining is an explicit host decision.
    partner_pending_accept: bool = False
    local_ready: bool = False
    local_archetype: str = ""
    reconnect_token: str = ""
    seq: int = 0
    started: bool = False
    run_seed: int = 0
    floor_revision: int = 0
    last_snapshot_key: tuple[int, int] = (-1, -1)
    snapshot_tick: int = 0
    next_snapshot_at: float = 0.0
    next_intent_at: float = 0.0
    next_ping_at: float = 0.0
    last_world_lengths: tuple = ()
    input_seq: int = 0
    # Reconnect bookkeeping (client side of the 30-second grace window).
    reconnecting: bool = False
    reconnect_deadline: float = 0.0
    next_reconnect_at: float = 0.0
    reconnect_backoff: float = _RECONNECT_BACKOFF_START
    awaiting_floor: bool = False
    rtt_ms: float = 0.0
    ping_sent_at: dict[int, float] = field(default_factory=dict)
    # Host-side latest joiner movement intent + queued one-shot actions.
    intent_move: tuple[float, float] = (0.0, 0.0)
    intent_move_at: float = 0.0
    intent_last_seq: int = 0
    intent_actions: deque = field(default_factory=deque)


class NetMixin:
    """Composed into ``Game``; see module docstring."""

    def init_net(self) -> None:
        self.mp_client: MultiplayerClient | None = None
        self.mp_session: MpSession | None = None
        self.mp_generation = 0
        self.mp_active = False
        self.mp_role = ""
        self.mp_setup_step = "name"  # name | role | host_code | join_code
        self.mp_setup_role_cursor = 0
        self.mp_run_id = ""
        self.mp_join_code = ""
        self.mp_notice = ""
        self.mp_status = ""
        self.mp_title_notice = ""
        self.mp_partner_pause_reason = ""
        # 4.7: connection consent gate. Consent is per-launch, per-endpoint
        # and never persisted: every session reaffirms it before the first
        # socket to a given server is opened.
        self.mp_consent_cursor = 0
        self._mp_consented_endpoint: tuple[str, int] | None = None
        self._mp_pending_session: tuple[str, str] | None = None
        # The stable player collection. Single-player logic keeps using the
        # plain ``self.player`` attribute; multiplayer-aware code paths call
        # ``active_players()`` which falls back to ``(self.player,)``.
        self.players: list[Player] = []
        self.local_player_id = "p1"

    # -- collection helpers -------------------------------------------------

    def active_players(self) -> tuple[Player, ...]:
        """Every player actor in the current run (multiplayer-aware)."""

        if self.mp_active and len(self.players) > 1:
            return tuple(self.players)
        player = getattr(self, "player", None)
        return (player,) if player is not None else ()

    def living_players(self) -> tuple[Player, ...]:
        return tuple(p for p in self.active_players() if p.hp > 0)

    def local_player(self) -> Player | None:
        for player in self.players:
            if player.player_id == self.local_player_id:
                return player
        return getattr(self, "player", None)

    def partner_player(self) -> Player | None:
        if not self.mp_active:
            return None
        for player in self.players:
            if player.player_id != self.local_player_id:
                return player
        return None

    def mp_is_joiner(self) -> bool:
        return self.mp_active and self.mp_role == ROLE_JOIN

    def mp_is_host(self) -> bool:
        return self.mp_active and self.mp_role == ROLE_HOST

    @contextmanager
    def acting_as_player(self, player: Player) -> Iterator[None]:
        """Temporarily make ``player`` the acting ``self.player``.

        The host simulates the joiner's actor through the same combat,
        inventory, and interaction code paths as the local player: XP, gold,
        loot claims, and cooldowns all route to the acting player.
        """

        previous = self.player
        self.player = player
        try:
            yield
        finally:
            self.player = previous

    # -- per-frame driver ---------------------------------------------------

    def poll(self) -> None:
        """Main-thread pump; cheap when no multiplayer client exists."""

        client = self.mp_client
        session = self.mp_session
        if client is None and session is None:
            return
        if getattr(self, "mobile_mode", False) and getattr(
            self, "mobile_suspended", False
        ):
            # Android background: pause outbound traffic and hold the socket.
            # Inbound stays queued (bounded, snapshots coalesced) until resume.
            return
        now = time.monotonic()
        if client is not None:
            for event in client.poll_events():
                if event.generation != self.mp_generation:
                    continue
                self._mp_handle_event(event, now)
                # Handlers may tear the session down mid-drain.
                if self.mp_client is None and self.mp_session is None:
                    return
        session = self.mp_session
        if session is None:
            return
        if session.reconnecting:
            self._mp_drive_reconnect(now)
            return
        if self.mp_client is None:
            return
        self._mp_send_periodic(now)

    # -- outbound scheduling ------------------------------------------------

    def _mp_send_periodic(self, now: float) -> None:
        session = self.mp_session
        client = self.mp_client
        if session is None or client is None:
            return
        if not session.player_id:
            # No welcome yet: nothing may precede (or race) the hello.
            return
        if now >= session.next_ping_at:
            session.next_ping_at = now + _PING_INTERVAL_SECONDS
            session.seq += 1
            session.ping_sent_at[session.seq] = now
            if len(session.ping_sent_at) > 8:
                oldest = min(session.ping_sent_at)
                session.ping_sent_at.pop(oldest, None)
            client.send_message(make_ping(seq=session.seq, ts=now))
        if not (self.mp_active and session.started):
            return
        if session.role == ROLE_HOST:
            if now >= session.next_snapshot_at and self.players:
                session.next_snapshot_at = now + _SNAPSHOT_INTERVAL
                self._mp_send_snapshot()
        elif session.role == ROLE_JOIN:
            if (
                now >= session.next_intent_at
                and self.state == "playing"
                and not session.awaiting_floor
            ):
                session.next_intent_at = now + _INTENT_INTERVAL
                local = self.local_player()
                if local is not None and local.hp > 0:
                    move_x, move_y = self._mp_local_move_vector()
                    session.input_seq += 1
                    client.send_message(
                        make_intent(
                            input_seq=session.input_seq,
                            move_x=move_x,
                            move_y=move_y,
                        ),
                        coalesce_key=COALESCE_MOVE_INTENT,
                    )

    def _mp_send_snapshot(self) -> None:
        session = self.mp_session
        client = self.mp_client
        if session is None or client is None:
            return
        session.snapshot_tick += 1
        lengths = sync.world_list_lengths(self)
        include_slow = (
            session.snapshot_tick % sync.SLOW_PAYLOAD_EVERY_TICKS == 0
            or lengths != session.last_world_lengths
        )
        session.last_world_lengths = lengths
        state = sync.build_snapshot_state(self, include_slow=include_slow)
        client.send_message(
            make_snapshot(
                floor_revision=session.floor_revision,
                tick=session.snapshot_tick,
                state=state,
            ),
            coalesce_key=COALESCE_SNAPSHOT,
        )

    def mp_send_floor(self) -> None:
        """Host: serialize and send the full static floor descriptor."""

        session = self.mp_session
        client = self.mp_client
        if session is None or client is None or session.role != ROLE_HOST:
            return
        session.floor_revision += 1
        session.snapshot_tick = 0
        state = sync.build_floor_state(self)
        client.send_message(
            make_floor(
                floor_revision=session.floor_revision,
                depth=self.current_depth,
                floor_seed=session.run_seed,
                state=state,
            )
        )
        # Follow with a fresh snapshot so the joiner starts from live state.
        session.next_snapshot_at = 0.0

    def mp_queue_action(self, action: str, target: str | None = None) -> None:
        """Joiner: transmit a one-shot action intent promptly (never coalesced)."""

        session = self.mp_session
        client = self.mp_client
        if session is None or client is None or not self.mp_is_joiner():
            return
        if session.awaiting_floor or self.state != "playing":
            return
        local = self.local_player()
        if local is None or local.hp <= 0:
            return
        aim_x, aim_y = local.facing_x, local.facing_y
        session.input_seq += 1
        client.send_message(
            make_intent(
                input_seq=session.input_seq,
                move_x=aim_x,
                move_y=aim_y,
                action=action,
                target=target,
            )
        )

    def _mp_local_move_vector(self) -> tuple[float, float]:
        """Sample the joiner's movement input (keyboard/controller/touch/mouse)."""

        keys = pygame.key.get_pressed()
        move_x = float(keys[pygame.K_RIGHT] or keys[pygame.K_d]) - float(
            keys[pygame.K_LEFT] or keys[pygame.K_a]
        )
        move_y = float(keys[pygame.K_DOWN] or keys[pygame.K_s]) - float(
            keys[pygame.K_UP] or keys[pygame.K_w]
        )
        controller_x, controller_y = self.input.left_vec()
        if controller_x or controller_y:
            move_x, move_y = controller_x, controller_y
        elif getattr(self, "mobile_mode", False):
            mobile_x, mobile_y = self.mobile_joystick_world_vector()
            if mobile_x or mobile_y:
                move_x, move_y = mobile_x, mobile_y
        elif not (move_x or move_y):
            move_x, move_y = self._mp_mouse_walk_vector()
        length = math.hypot(move_x, move_y)
        if length > 1.0:
            move_x, move_y = move_x / length, move_y / length
        return move_x, move_y

    def _mp_mouse_walk_vector(self) -> tuple[float, float]:
        """Joiner's mouse hold-to-walk fallback (mirrors ``update_player``).

        The host steps its own mouse walk exactly to the cursor each frame;
        the joiner can only send an analog vector, so deflection tapers to
        zero at the same 0.12-tile stop radius to ease in without orbiting
        the pointer between 20 Hz intents. Menus and cutscenes suppress it —
        on the host those states pause the simulation before the mouse is
        sampled, and joiner-side menu clicks must not double as movement.
        """

        if (
            self.inventory_open
            or self.character_menu_open
            or self.shop_open
            or self.active_cutscene is not None
            or self.story_intro_pending
        ):
            return 0.0, 0.0
        if not pygame.mouse.get_pressed()[0]:
            return 0.0, 0.0
        dx, dy = self.face_player_toward_screen_point(*pygame.mouse.get_pos())
        distance = math.hypot(dx, dy)
        if distance <= 0.12:
            return 0.0, 0.0
        magnitude = min(1.0, (distance - 0.12) * 4.0)
        return (dx / distance) * magnitude, (dy / distance) * magnitude

    # -- inbound dispatch ---------------------------------------------------

    def _mp_handle_event(self, event: Any, now: float) -> None:
        session = self.mp_session
        if isinstance(event, ConnectionUp):
            self._mp_on_connected()
            return
        if isinstance(event, ConnectionFailed):
            self._mp_on_connection_failed(event.reason, now)
            return
        if isinstance(event, ConnectionLost):
            self._mp_on_connection_lost(event.reason, now)
            return
        if isinstance(event, ConnectionClosed):
            return
        if not isinstance(event, InboundMessage) or session is None:
            return
        message = event.message
        if isinstance(message, Welcome):
            self._mp_on_welcome(message)
        elif isinstance(message, PartnerJoined):
            session.partner_name = message.name
            session.partner_player_id = message.player_id
            session.partner_connected = True
            session.partner_ready = False
            session.partner_archetype = ""
            if session.role == ROLE_HOST and not session.started:
                # A 4-rune code is a locator, not a secret: whoever knocks
                # must be admitted explicitly before the descent can begin.
                session.partner_pending_accept = True
                self.mp_status = (
                    f"{message.name or 'A nameless one'} knocks at the gate — "
                    "Enter admits them, D turns them away."
                )
            else:
                self.mp_status = f"{message.name} has answered the call."
        elif isinstance(message, ReadyAck):
            if message.player_id and message.player_id != session.player_id:
                session.partner_ready = True
                session.partner_archetype = message.archetype_key
        elif isinstance(message, Start):
            self._mp_on_start(message)
        elif isinstance(message, FloorMessage):
            self._mp_on_floor(message)
        elif isinstance(message, SnapshotMessage):
            self._mp_on_snapshot(message)
        elif isinstance(message, IntentMessage):
            self._mp_on_intent(message, now)
        elif isinstance(message, PartnerDisconnected):
            session.partner_connected = False
            self.mp_status = "Partner connection lost — the dungeon holds…"
            if self.state == "playing":
                self._mp_world_notice("Partner connection lost…")
        elif isinstance(message, PartnerRejoined):
            session.partner_connected = True
            self.mp_status = f"{message.name or 'Your partner'} has returned."
            if self.state == "playing":
                self._mp_world_notice("Partner reconnected")
            if session.role == ROLE_HOST and session.started:
                self.mp_send_floor()
        elif isinstance(message, PartnerLeft):
            self._mp_on_partner_left()
        elif isinstance(message, RunEndedMessage):
            self._mp_on_run_ended(message)
        elif isinstance(message, PongMessage):
            sent = session.ping_sent_at.pop(message.seq, None)
            if sent is not None:
                session.rtt_ms = max(0.0, (now - sent) * 1000.0)
        elif isinstance(message, ErrorMessage):
            self._mp_on_error(message)
        elif isinstance(message, ByeMessage):
            self._mp_on_partner_left()
        elif isinstance(message, UnknownMessage):
            # Forward compatibility: ignore quietly.
            pass

    # -- connection lifecycle ------------------------------------------------

    def _mp_on_connected(self) -> None:
        session = self.mp_session
        client = self.mp_client
        if session is None or client is None:
            return
        session.seq += 1
        client.send_message(
            make_hello(
                seq=session.seq,
                name=self.mp_player_name or "Warden",
                run_id=session.run_id,
                role=session.role,
                content_revision=__version__,
                reconnect_token=session.reconnect_token,
            )
        )
        self.mp_status = "Reaching the far shore…"

    def _mp_on_welcome(self, message: Welcome) -> None:
        session = self.mp_session
        if session is None:
            return
        was_reconnect = session.reconnecting
        session.reconnecting = False
        session.reconnect_backoff = _RECONNECT_BACKOFF_START
        session.player_id = message.player_id
        session.reconnect_token = message.reconnect_token
        session.run_id = message.run_id
        self.mp_run_id = message.run_id
        self.local_player_id = message.player_id
        if message.partner_name is not None:
            session.partner_name = message.partner_name
        session.partner_ready = message.partner_ready
        if was_reconnect:
            self.mp_status = "Reconnected."
            if session.role == ROLE_HOST and session.started:
                self.mp_send_floor()
            elif session.role == ROLE_JOIN and session.started:
                session.awaiting_floor = True
            return
        # Fresh session: enter the lobby.
        session.phase = "lobby"
        self.state = "mp_lobby"
        self.mp_notice = ""
        self.mp_status = (
            "Share the code with your partner."
            if session.role == ROLE_HOST and not session.partner_name
            else "Choose your archetype."
        )

    def _mp_on_connection_failed(self, reason: str, now: float) -> None:
        session = self.mp_session
        self._mp_drop_client()
        if session is None:
            return
        if session.reconnecting:
            self._mp_schedule_reconnect(now)
            return
        self.mp_notice = f"Could not reach the server: {reason or 'unreachable'}"
        self.mp_status = ""
        self.mp_session = None
        if self.state == "mp_lobby":
            self.state = "mp_setup"
        if self.mp_setup_step not in ("host_code", "join_code"):
            self.mp_setup_step = "role"

    def _mp_on_connection_lost(self, reason: str, now: float) -> None:
        session = self.mp_session
        self._mp_drop_client()
        if session is None:
            return
        if session.reconnect_token and (session.started or session.phase == "lobby"):
            if not session.reconnecting:
                session.reconnecting = True
                session.reconnect_deadline = now + MP_RECONNECT_GRACE_SECONDS
                session.reconnect_backoff = _RECONNECT_BACKOFF_START
                session.next_reconnect_at = now
                self.mp_status = "Connection lost — reattempting…"
                if self.state == "playing":
                    self._mp_world_notice("Connection lost — reattempting…")
            return
        self._mp_fail_session(f"Connection lost: {reason or 'socket closed'}")

    def _mp_drive_reconnect(self, now: float) -> None:
        session = self.mp_session
        if session is None or not session.reconnecting:
            return
        if now > session.reconnect_deadline:
            self._mp_fail_session(
                "Could not reconnect within the grace period."
            )
            return
        if self.mp_client is not None or now < session.next_reconnect_at:
            return
        session.reconnect_backoff = min(
            _RECONNECT_BACKOFF_CAP, session.reconnect_backoff * 2.0
        )
        session.next_reconnect_at = now + session.reconnect_backoff
        self._mp_connect()

    def _mp_schedule_reconnect(self, now: float) -> None:
        session = self.mp_session
        if session is None:
            return
        if now > session.reconnect_deadline:
            self._mp_fail_session("Could not reconnect within the grace period.")

    # -- lobby / start -------------------------------------------------------

    def _mp_on_start(self, message: Start) -> None:
        session = self.mp_session
        if session is None or session.started:
            return
        session.started = True
        session.run_seed = message.run_seed
        session.phase = "active"
        if session.role == ROLE_HOST:
            session.partner_player_id = message.joiner_player_id
            session.partner_name = message.joiner_name
            self.begin_multiplayer_run(
                run_seed=message.run_seed,
                host_archetype=message.host_archetype,
                joiner_archetype=message.joiner_archetype,
                host_player_id=message.host_player_id,
                joiner_player_id=message.joiner_player_id,
                host_name=message.host_name,
                joiner_name=message.joiner_name,
            )
            self.mp_send_floor()
        else:
            session.partner_player_id = message.host_player_id
            session.partner_name = message.host_name
            session.awaiting_floor = True
            self.mp_status = "The host carves the descent…"

    def mp_lobby_confirm(self) -> None:
        """Lobby confirm: admit a knocking partner first, otherwise ready up."""

        session = self.mp_session
        if (
            session is not None
            and session.role == ROLE_HOST
            and session.partner_pending_accept
        ):
            self.mp_lobby_accept_partner()
            return
        self.mp_lobby_send_ready()

    def mp_lobby_accept_partner(self) -> None:
        """Host: admit the joiner who is knocking at the lobby gate."""

        session = self.mp_session
        if (
            session is None
            or session.role != ROLE_HOST
            or not session.partner_pending_accept
        ):
            return
        session.partner_pending_accept = False
        name = session.partner_name or "Your partner"
        self.mp_status = f"{name} is admitted. Bind your archetype to descend."

    def mp_lobby_decline_partner(self) -> None:
        """Host: turn away the knocking joiner; the code stays open."""

        session = self.mp_session
        client = self.mp_client
        if (
            session is None
            or client is None
            or session.role != ROLE_HOST
            or not session.partner_pending_accept
        ):
            return
        session.seq += 1
        client.send_message(make_kick(seq=session.seq))
        session.partner_pending_accept = False
        session.partner_name = ""
        session.partner_player_id = ""
        session.partner_connected = False
        session.partner_ready = False
        session.partner_archetype = ""
        self.mp_status = "Turned away. The code remains open for another knock."

    def mp_lobby_send_ready(self) -> None:
        """Confirm the selected archetype in the lobby (both roles)."""

        session = self.mp_session
        client = self.mp_client
        if session is None or client is None or session.local_ready:
            return
        if session.role == ROLE_HOST and not session.partner_name:
            self.mp_status = "Wait for a partner before beginning the descent."
            return
        if session.role == ROLE_HOST and session.partner_pending_accept:
            self.mp_status = (
                "Answer the knock first — Enter admits, D turns away."
            )
            return
        archetype = self.selected_archetype.name
        session.local_archetype = archetype
        session.local_ready = True
        session.seq += 1
        run_seed = None
        if session.role == ROLE_HOST:
            # A fresh 64-bit seed from the OS entropy pool, never game RNG.
            import secrets as _secrets

            run_seed = _secrets.randbits(63)
        client.send_message(
            make_ready(seq=session.seq, archetype_key=archetype, run_seed=run_seed)
        )
        self.mp_status = "Bound. Waiting for your partner…"

    # -- world messages ------------------------------------------------------

    def _mp_on_floor(self, message: FloorMessage) -> None:
        session = self.mp_session
        if session is None or session.role != ROLE_JOIN:
            return
        if message.floor_revision <= 0:
            return
        try:
            sync.apply_floor_state(self, message.state)
        except (KeyError, TypeError, ValueError) as exc:
            self._mp_fail_session(f"Bad floor data from host: {exc}")
            return
        session.floor_revision = message.floor_revision
        session.last_snapshot_key = (message.floor_revision, -1)
        session.awaiting_floor = False
        self.mp_active = True
        self.mp_role = ROLE_JOIN
        self.state = "playing"

    def _mp_on_snapshot(self, message: SnapshotMessage) -> None:
        session = self.mp_session
        if session is None or session.role != ROLE_JOIN:
            return
        if session.awaiting_floor:
            return
        key = (message.floor_revision, message.tick)
        if (
            key[0] < session.last_snapshot_key[0]
            or key <= session.last_snapshot_key
        ):
            return  # stale revision/tick: ignore
        if key[0] != session.floor_revision:
            return  # snapshot for a floor we have not applied yet
        session.last_snapshot_key = key
        try:
            sync.apply_snapshot_state(self, message.state)
        except (KeyError, TypeError, ValueError, IndexError, AttributeError) as exc:
            # A malformed snapshot must never crash the joiner's main loop;
            # it ends the session cleanly like a bad floor descriptor does.
            self._mp_fail_session(f"Bad snapshot data from host: {exc}")

    def _mp_on_intent(self, message: IntentMessage, now: float) -> None:
        session = self.mp_session
        if session is None or session.role != ROLE_HOST or not session.started:
            return
        if message.input_seq <= session.intent_last_seq:
            return  # stale input
        session.intent_last_seq = message.input_seq
        if message.action:
            session.intent_actions.append(
                (message.action, message.target, message.move_x, message.move_y)
            )
            if len(session.intent_actions) > 32:
                session.intent_actions.popleft()
        else:
            session.intent_move = (message.move_x, message.move_y)
            session.intent_move_at = now

    # -- run lifecycle -------------------------------------------------------

    def mp_notify_run_ended(self, outcome: str) -> None:
        """Host: broadcast the authoritative end of the shared run."""

        session = self.mp_session
        client = self.mp_client
        if (
            session is None
            or client is None
            or session.role != ROLE_HOST
            or not session.started
        ):
            return
        results = [
            {
                "player_id": player.player_id,
                "name": player.display_name,
                "class_name": player.class_name,
                "level": player.level,
                "alive": player.hp > 0,
            }
            for player in self.players
        ]
        client.send_message(make_run_ended(outcome=outcome, results=results))

    def _mp_on_run_ended(self, message: RunEndedMessage) -> None:
        session = self.mp_session
        if session is None or session.role != ROLE_JOIN or not self.mp_active:
            return
        outcome = message.outcome
        self.mp_record_local_result(outcome)
        self.ambush_bells = []
        self.audio.stop_music()
        if outcome == "victory":
            self.state = "victory"
            self.play_sfx("victory")
        else:
            self.state = "dead"
            if not self.run_stats.cause_of_death:
                self.run_stats.cause_of_death = "the shared descent failed"
            self.play_sfx("death")

    def mp_record_local_result(self, outcome: str) -> None:
        """Record this client's own run-history entry after ``run_ended``."""

        local = self.local_player()
        record = {
            "outcome": outcome,
            "class": local.class_name if local is not None else "",
            "depth": self.current_depth,
            "time": int(self.elapsed),
            "difficulty": self.difficulty_profile().name,
            "modifier": self.run_modifier.name,
            "kills": self.run_stats.kills,
            "bosses": list(self.run_stats.defeated_bosses[-4:]),
            "notable_loot": list(self.run_stats.notable_loot[-4:]),
            "cause": self.run_stats.cause_of_death,
            "multiplayer": True,
        }
        self.run_history.append(record)
        del self.run_history[:-12]
        self.save_options()

    def _mp_on_partner_left(self) -> None:
        session = self.mp_session
        if session is None:
            return
        if self.mp_active:
            self.mp_end_session_to_title("Your partner has left the run.")
        elif session.phase == "lobby":
            # After a local decline the partner fields are already empty and
            # the "turned away" status must survive this echoed partner_left.
            had_partner = bool(session.partner_name)
            session.partner_name = ""
            session.partner_ready = False
            session.partner_archetype = ""
            session.partner_connected = True
            session.partner_pending_accept = False
            if session.role == ROLE_HOST:
                if had_partner:
                    self.mp_status = (
                        "Your partner departed. Share the code again."
                    )
            else:
                self.mp_end_session_to_title("The host has closed the run.")

    def _mp_on_error(self, message: ErrorMessage) -> None:
        session = self.mp_session
        if session is None:
            return
        notice = _SETUP_ERROR_NOTICES.get(message.code, message.msg or message.code)
        if not message.fatal and session.started:
            return  # non-fatal in-run errors are diagnostics
        if self.mp_active:
            if message.fatal:
                self.mp_end_session_to_title(notice)
            return
        # Setup/lobby failures are recoverable: back to the right step.
        self._mp_drop_client()
        self.mp_session = None
        self.mp_notice = notice
        self.mp_status = ""
        self.state = "mp_setup"
        if message.code == "run_id_in_use":
            # A host collision returns to code generation with a fresh code.
            self.mp_run_id = generate_run_id(MP_RUN_ID_LENGTH)
            self.mp_setup_step = "host_code"
        elif message.code in ("run_not_found", "run_full", "bad_revision", "kicked"):
            # A join failure keeps the entered code editable.
            self.mp_setup_step = "join_code"
            self.mp_open_join_code_input()
        else:
            self.mp_setup_step = "role"

    def _mp_fail_session(self, notice: str) -> None:
        if self.mp_active:
            self.mp_end_session_to_title(notice)
            return
        self._mp_drop_client()
        self.mp_session = None
        self.mp_status = ""
        self.mp_notice = notice
        if self.state in ("mp_lobby",):
            self.state = "mp_setup"
            self.mp_setup_step = "role"

    def mp_end_session_to_title(self, notice: str) -> None:
        """End the co-op run and return safely to the title screen."""

        self.mp_shutdown(send_bye=True)
        self.mp_title_notice = notice
        self.show_help = False
        self.inventory_open = False
        self.character_menu_open = False
        self.mobile_hub_open = False
        self.quest_info_visible = False
        self.close_shop()
        self.active_cutscene = None
        self.story_intro_pending = False
        self.state = "title"
        self.exit_previous_state = "title"
        self.sync_music()

    def mp_shutdown(self, *, send_bye: bool) -> None:
        """Tear down the client/session. Never touches single-player saves."""

        client = self.mp_client
        self.mp_client = None
        if client is not None:
            client.close(send_bye=send_bye)
        self.mp_session = None
        self.mp_active = False
        self.mp_role = ""
        self.mp_status = ""
        self.mp_partner_pause_reason = ""
        self.players = []
        self.local_player_id = "p1"

    # -- setup flow ----------------------------------------------------------

    def start_mp_setup(self) -> None:
        """Enter ``mp_setup`` from the title's "Two will descend" row."""

        self.mp_shutdown(send_bye=True)
        self.mp_notice = ""
        self.mp_status = ""
        self.mp_title_notice = ""
        self.mp_join_code = ""
        self.mp_run_id = ""
        self.mp_setup_role_cursor = 0
        self.state = "mp_setup"
        self.mp_setup_step = "name"
        initial = self.mp_player_name or sanitize_player_name(
            self._mp_default_name()
        )
        self.open_text_input(
            target="mp_player_name",
            prompt="Name yourself for the descent",
            initial=initial,
            max_length=16,
            help_text="Shown to your partner. Kept between sessions.",
        )

    @staticmethod
    def _mp_default_name() -> str:
        from .protocol import default_player_name

        return default_player_name()

    def mp_confirm_player_name(self, value: str) -> None:
        name = sanitize_player_name(value) or sanitize_player_name(
            self._mp_default_name()
        )
        self.mp_player_name = name
        self.save_options()
        if self.state == "mp_setup" and self.mp_setup_step == "name":
            self.mp_setup_step = "role"

    def mp_text_input_cancelled(self, target: str) -> None:
        if self.state != "mp_setup":
            return
        if target == "mp_player_name":
            self.mp_back_to_title()
        elif target == "mp_join_code":
            self.mp_setup_step = "role"

    def mp_choose_role(self, host: bool) -> None:
        if self.state != "mp_setup":
            return
        self.mp_notice = ""
        if not self.mp_endpoint_configured():
            self.mp_notice = (
                "Server not configured — set the server host and port in Options."
            )
            return
        if host:
            self.mp_run_id = generate_run_id(MP_RUN_ID_LENGTH)
            self.mp_setup_step = "host_code"
        else:
            self.mp_setup_step = "join_code"
            self.mp_open_join_code_input()

    def mp_open_join_code_input(self) -> None:
        from .protocol import MP_RUN_ID_ALPHABET

        self.open_text_input(
            target="mp_join_code",
            prompt="Enter your partner's code",
            initial=self.mp_join_code,
            max_length=MP_RUN_ID_LENGTH,
            charset=MP_RUN_ID_ALPHABET,
            uppercase=True,
            help_text="Ask the host for the four runes above their lobby.",
        )

    def mp_regenerate_host_code(self) -> None:
        if self.state == "mp_setup" and self.mp_setup_step == "host_code":
            self.mp_run_id = generate_run_id(MP_RUN_ID_LENGTH)
            self.mp_notice = ""

    def mp_begin_hosting(self) -> None:
        """Host: connect and open the lobby for this code."""

        if self.state != "mp_setup" or self.mp_setup_step != "host_code":
            return
        if not self.mp_run_id:
            self.mp_run_id = generate_run_id(MP_RUN_ID_LENGTH)
        self._mp_open_session(ROLE_HOST, self.mp_run_id)

    def mp_submit_join_code(self, value: str) -> None:
        code = normalize_run_id(value)
        self.mp_join_code = code
        if self.state != "mp_setup":
            return
        if not is_valid_run_id(code, length=MP_RUN_ID_LENGTH):
            self.mp_notice = (
                f"A run code is {MP_RUN_ID_LENGTH} runes — no 0, O, 1, or I."
            )
            self.mp_setup_step = "join_code"
            self.mp_open_join_code_input()
            return
        self._mp_open_session(ROLE_JOIN, code)

    def _mp_open_session(self, role: str, run_id: str) -> None:
        if not self.mp_endpoint_configured():
            self.mp_notice = (
                "Server not configured — set the server host and port in Options."
            )
            self.mp_setup_step = "role"
            return
        if self.mp_consent_required():
            # No socket may be opened before the player has read and agreed
            # to the connection notice for this endpoint.
            self._mp_pending_session = (role, run_id)
            self.mp_consent_cursor = 0
            self.state = "mp_consent"
            return
        self._mp_open_session_now(role, run_id)

    def _mp_open_session_now(self, role: str, run_id: str) -> None:
        self._mp_drop_client()
        self.mp_session = MpSession(role=role, run_id=run_id)
        self.mp_role = role
        self.mp_notice = ""
        self.mp_status = "Knocking on the server gate…"
        self._mp_connect()

    # -- connection consent gate ---------------------------------------------

    def _mp_endpoint(self) -> tuple[str, int]:
        return (
            str(getattr(self, "mp_server_host", "")).strip(),
            int(getattr(self, "mp_server_port", 0)),
        )

    def mp_consent_required(self) -> bool:
        """Whether the consent screen must run before connecting."""

        return self._mp_consented_endpoint != self._mp_endpoint()

    def mp_consent_agree(self) -> None:
        """Consent screen: agree — remember the endpoint and connect."""

        if self.state != "mp_consent":
            return
        pending = self._mp_pending_session
        self._mp_pending_session = None
        self._mp_consented_endpoint = self._mp_endpoint()
        self.state = "mp_setup"
        if pending is None:
            self.mp_setup_step = "role"
            return
        self._mp_open_session_now(*pending)

    def mp_consent_exit(self) -> None:
        """Consent screen: exit without connecting."""

        if self.state != "mp_consent":
            return
        self._mp_pending_session = None
        self.state = "mp_setup"
        self.mp_setup_step = "role"
        self.mp_status = ""

    def _mp_connect(self) -> None:
        session = self.mp_session
        if session is None:
            return
        self.mp_generation += 1
        client = MultiplayerClient(
            str(self.mp_server_host),
            int(self.mp_server_port),
            generation=self.mp_generation,
            tls=bool(getattr(self, "mp_server_tls", True)),
        )
        self.mp_client = client
        client.start()

    def _mp_drop_client(self) -> None:
        client = self.mp_client
        self.mp_client = None
        if client is not None:
            client.close(send_bye=False)

    def mp_back_from_setup_step(self) -> None:
        """One step back inside mp_setup; leaves to title from the first step."""

        if self.text_input_active():
            self.close_text_input(confirm=False)
            return
        step = self.mp_setup_step
        if step == "name":
            self.mp_back_to_title()
        elif step == "role":
            self.mp_back_to_title()
        elif step in ("host_code", "join_code"):
            self._mp_drop_client()
            self.mp_session = None
            self.mp_status = ""
            self.mp_setup_step = "role"

    def mp_leave_lobby(self) -> None:
        self.mp_shutdown(send_bye=True)
        self.state = "mp_setup"
        self.mp_setup_step = "role"
        self.mp_status = ""

    def mp_back_to_title(self) -> None:
        self.mp_shutdown(send_bye=True)
        if self.text_input_active():
            self.close_text_input(confirm=False)
        self.state = "title"

    # -- host-side remote player simulation ----------------------------------

    def mp_apply_remote_intents(self, dt: float) -> None:
        """Host: move and act the joiner's actor from validated intents."""

        session = self.mp_session
        if session is None or not self.mp_is_host():
            return
        remote = self.partner_player()
        if remote is None:
            return
        if remote.hp <= 0:
            session.intent_actions.clear()
            session.intent_move = (0.0, 0.0)
            return
        now = time.monotonic()
        move_x, move_y = session.intent_move
        if now - session.intent_move_at > _INTENT_MOVE_TIMEOUT_SECONDS:
            move_x = move_y = 0.0
        with self.acting_as_player(remote):
            self._mp_update_remote_player(remote, dt, move_x, move_y)
            while session.intent_actions:
                action, target, aim_x, aim_y = session.intent_actions.popleft()
                if aim_x or aim_y:
                    length = math.hypot(aim_x, aim_y)
                    remote.facing_x = aim_x / length
                    remote.facing_y = aim_y / length
                self._mp_dispatch_remote_action(action, target)

    def _mp_update_remote_player(
        self, remote: Player, dt: float, move_x: float, move_y: float
    ) -> None:
        """Movement, cooldowns, statuses, and regen for the remote actor.

        Mirrors ``update_player`` minus real-input sampling and garden
        healing. Runs inside ``acting_as_player`` so shared helpers resolve
        against the remote actor.
        """

        from ..combat._utils import PLAYER_MOVE_SPEED

        remote.moving = False
        remote.locomotion_anim_scale = 0.0
        equipment_move = max(
            -0.25, min(0.30, self.equipment_stat_total("move_speed"))
        )
        move_speed = (
            PLAYER_MOVE_SPEED
            * (1.0 + equipment_move)
            * (0.82 if self.player_status("chilled") > 0 else 1.0)
        )
        if move_x or move_y:
            length = math.hypot(move_x, move_y)
            if length > 0.0:
                nx, ny = move_x / length, move_y / length
                remote.facing_x = nx
                remote.facing_y = ny
                magnitude = min(1.0, length)
                moved = self.move_actor(
                    remote,
                    nx * magnitude * move_speed * dt,
                    ny * magnitude * move_speed * dt,
                )
                if moved > 0.0 and dt > 0.0:
                    remote.locomotion_anim_scale = moved / (
                        dt * PLAYER_MOVE_SPEED
                    )
            if self.enemy_in_melee_arc():
                self.player_melee_attack()
        remote.melee_timer = max(0.0, remote.melee_timer - dt)
        remote.bolt_timer = max(0.0, remote.bolt_timer - dt)
        remote.dash_timer = max(0.0, remote.dash_timer - dt)
        remote.class_skill_timer = max(0.0, remote.class_skill_timer - dt)
        remote.time_skip_timer = max(0.0, remote.time_skip_timer - dt)
        if self.player_status("poisoned") > 0:
            tick = remote.status_effects.get("_poison_tick", 1.0) - dt
            if tick <= 0:
                poison_damage = max(1, self.current_depth // 3 + 1)
                remote.hp -= poison_damage
                tick += 1.0
                self.floaters.append(
                    FloatingText(
                        f"Poison -{poison_damage}",
                        remote.x,
                        remote.y - 0.55,
                        self.damage_type_color("poison"),
                        ttl=0.75,
                    )
                )
            remote.status_effects["_poison_tick"] = tick
        next_statuses: dict[str, float] = {}
        for status, ttl in remote.status_effects.items():
            if status.startswith("_"):
                next_statuses[status] = ttl
                continue
            ttl -= dt
            if ttl > 0:
                next_statuses[status] = ttl
        if "poisoned" not in next_statuses:
            next_statuses.pop("_poison_tick", None)
        remote.status_effects = next_statuses
        stamina_regen = 38 if remote.class_name == "Ranger" else 30
        mana_regen = 8 if remote.class_name == "Arcanist" else 5
        if remote.has_upgrade("arcanist_focus"):
            mana_regen += 3
        if remote.has_upgrade("ranger_snare"):
            stamina_regen += 4
        remote.stamina = min(
            remote.max_stamina, remote.stamina + stamina_regen * dt
        )
        remote.mana = min(remote.max_mana, remote.mana + mana_regen * dt)
        # Decay the partner's transient visual fields (the local player's
        # equivalents decay on the Game object in update_visual_effects).
        remote.hit_flash = max(0.0, remote.hit_flash - dt)
        if remote.hit_flash <= 0.0:
            remote.hit_flash_duration = 0.0
        if remote.action_ttl > 0.0:
            remote.action_elapsed += dt
        remote.action_ttl = max(0.0, remote.action_ttl - dt)
        if remote.action_ttl <= 0.0:
            remote.action_state = ""
            remote.action_elapsed = 0.0
            remote.action_duration = 0.0

    def _mp_dispatch_remote_action(
        self, action: str, target: str | None
    ) -> None:
        if action == "melee":
            self.player_melee_attack()
        elif action == "bolt":
            self.player_cast_bolt()
        elif action == "skill":
            self.player_cast_class_skill()
        elif action == "dash":
            self.player_dash()
        elif action == "potion_hp":
            self.use_first_potion()
        elif action == "potion_mana":
            self.use_first_mana_potion()
        elif action == "interact":
            self.interact()
        elif action == "use_slot":
            slot = self._mp_slot_index(target)
            if slot is not None:
                self.use_inventory_slot(slot)
        elif action == "drop_slot":
            slot = self._mp_slot_index(target)
            if slot is not None:
                self.drop_inventory_slot(slot)
        elif action == "choose_discipline" and target:
            self.choose_discipline(str(target))

    @staticmethod
    def _mp_slot_index(target: str | None) -> int | None:
        try:
            slot = int(str(target))
        except (TypeError, ValueError):
            return None
        return slot if 0 <= slot < 64 else None

    # -- joiner-side reduced update -------------------------------------------

    def mp_update_joiner(self, dt: float) -> None:
        """The joiner never simulates: it renders authoritative state."""

        session = self.mp_session
        self.update_visual_effects(dt)
        for player in self.players:
            if player.player_id == self.local_player_id:
                continue
            player.hit_flash = max(0.0, player.hit_flash - dt)
            if player.hit_flash <= 0.0:
                player.hit_flash_duration = 0.0
            if player.action_ttl > 0.0:
                player.action_elapsed += dt
            player.action_ttl = max(0.0, player.action_ttl - dt)
            if player.action_ttl <= 0.0:
                player.action_state = ""
        sync.lerp_networked_actors(self, dt)
        # Advance projectiles ballistically between snapshots (render motion
        # only — collision damage is exclusively host business).
        if self.projectiles:
            self.projectiles = [
                projectile
                for projectile in self.projectiles
                if projectile.update(dt, self.dungeon)
            ]
        local = self.local_player()
        if (
            local is not None
            and local.hp > 0
            and session is not None
            and not session.awaiting_floor
        ):
            move_x, move_y = self._mp_local_move_vector()
            if move_x or move_y:
                length = math.hypot(move_x, move_y)
                local.facing_x = move_x / length
                local.facing_y = move_y / length
                local.moving = True
                local.locomotion_anim_scale = min(1.0, length)
        self.update_camera(dt)
        self.update_revealed_tiles()
        self.update_floaters(dt)
        self.advance_animation_phases(dt)

    # -- shared helpers -------------------------------------------------------

    def _mp_world_notice(self, text: str) -> None:
        player = getattr(self, "player", None)
        if player is None:
            return
        self.floaters.append(
            FloatingText(
                text,
                player.x,
                player.y - 0.8,
                (235, 220, 170),
                ttl=1.6,
            )
        )

    def mp_all_living_players_near_stairs(self) -> bool:
        """Stairs gate: every living player must be in range to descend."""

        living = self.living_players()
        if not living:
            return False
        stairs_x, stairs_y = self.dungeon.stairs
        for player in living:
            if (
                math.hypot(
                    player.x - (stairs_x + 0.5), player.y - (stairs_y + 0.5)
                )
                >= 2.2
            ):
                return False
        return True
