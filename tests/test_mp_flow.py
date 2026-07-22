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

"""4.6 end-to-end multiplayer flow tests.

An in-process asyncio relay bound to a loopback port serves a pair of
``MultiplayerClient`` instances and a pair of headless ``Game`` instances.
No non-loopback network access occurs; SDL runs on the dummy drivers.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game
from arch_rogue.input import Command
from arch_rogue.net import (
    ConnectionUp,
    InboundMessage,
    MultiplayerClient,
    SnapshotMessage,
)
from arch_rogue.net.messages import IntentMessage, Welcome
from arch_rogue_protocol import (
    generate_run_id,
    make_hello,
    make_intent,
    make_ready,
    make_snapshot,
)
from server.config import ServerConfig
from server.server import MultiplayerServer


class LoopbackServer:
    """A real relay on 127.0.0.1 with its event loop on a daemon thread."""

    def __init__(self, **config_overrides) -> None:
        defaults = dict(host="127.0.0.1", port=0)
        defaults.update(config_overrides)
        self.loop = asyncio.new_event_loop()
        self.server = MultiplayerServer(ServerConfig(**defaults))
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)

    def start(self) -> int:
        self.thread.start()
        asyncio.run_coroutine_threadsafe(
            self.server.start(), self.loop
        ).result(timeout=10)
        return self.server.bound_port

    def stop(self) -> None:
        asyncio.run_coroutine_threadsafe(
            self.server.close(), self.loop
        ).result(timeout=10)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=5)
        if not self.thread.is_alive():
            self.loop.close()


def wait_for(client: MultiplayerClient, kinds: tuple[str, ...], timeout=8.0):
    """Poll until an event/message whose type name is in ``kinds`` arrives."""

    collected = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        for event in client.poll_events():
            collected.append(event)
            if isinstance(event, InboundMessage):
                if type(event.message).__name__ in kinds:
                    return event.message, collected
            elif type(event).__name__ in kinds:
                return event, collected
        time.sleep(0.005)
    raise AssertionError(f"timed out waiting for {kinds}; saw {collected}")


class ClientPairTests(unittest.TestCase):
    """Raw ``MultiplayerClient`` pair against the real relay."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.harness = LoopbackServer()
        cls.port = cls.harness.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.harness.stop()

    def _client(self, generation: int = 1) -> MultiplayerClient:
        client = MultiplayerClient("127.0.0.1", self.port, generation=generation)
        client.start()
        wait_for(client, ("ConnectionUp",))
        return client

    def test_full_handshake_and_relay(self) -> None:
        run_id = generate_run_id()
        host = self._client()
        join = self._client()
        try:
            host.send_message(
                make_hello(
                    seq=1, name="Matti", run_id=run_id, role="host",
                    content_revision="t",
                )
            )
            welcome, _ = wait_for(host, ("Welcome",))
            assert isinstance(welcome, Welcome)
            self.assertEqual(welcome.you_are, "host")

            join.send_message(
                make_hello(
                    seq=1, name="Partner", run_id=run_id, role="join",
                    content_revision="t",
                )
            )
            join_welcome, _ = wait_for(join, ("Welcome",))
            assert isinstance(join_welcome, Welcome)
            self.assertEqual(join_welcome.partner_name, "Matti")
            wait_for(host, ("PartnerJoined",))

            # Ready race: joiner first, then host with the seed.
            join.send_message(make_ready(seq=2, archetype_key="Rogue"))
            host.send_message(
                make_ready(seq=2, archetype_key="Warden", run_seed=77)
            )
            start_host, _ = wait_for(host, ("Start",))
            start_join, _ = wait_for(join, ("Start",))
            self.assertEqual(start_host, start_join)
            self.assertEqual(start_host.run_seed, 77)

            # Snapshot coalescing: only the newest queued snapshot survives a
            # burst; ordering vs reliable events is preserved.
            for tick in range(1, 40):
                host.send_message(
                    make_snapshot(floor_revision=1, tick=tick, state={}),
                    coalesce_key="snapshot",
                )
            snapshot, _ = wait_for(join, ("SnapshotMessage",))
            assert isinstance(snapshot, SnapshotMessage)
            self.assertGreaterEqual(snapshot.tick, 1)
            deadline = time.time() + 2.0
            newest = snapshot.tick
            while newest < 39 and time.time() < deadline:
                for event in join.poll_events():
                    if isinstance(event, InboundMessage) and isinstance(
                        event.message, SnapshotMessage
                    ):
                        self.assertGreater(event.message.tick, newest)
                        newest = event.message.tick
                time.sleep(0.005)
            self.assertEqual(newest, 39)

            # Intent relay stamps the authoritative player id.
            join.send_message(
                make_intent(input_seq=1, move_x=1.0, move_y=0.0, action="melee")
            )
            intent, _ = wait_for(host, ("IntentMessage",))
            assert isinstance(intent, IntentMessage)
            self.assertEqual(intent.player_id, "p2")

            # Graceful bye is final: the host hears partner_left.
            join.close(send_bye=True)
            self.assertFalse(join.running)
            wait_for(host, ("PartnerLeft",))
        finally:
            host.close(send_bye=True)
            join.close()

    def test_bounded_queue_shutdown_joins_thread_promptly(self) -> None:
        client = MultiplayerClient("127.0.0.1", self.port, generation=3)
        client.start()
        wait_for(client, ("ConnectionUp",))
        for index in range(300):
            client.send_message(
                make_snapshot(floor_revision=1, tick=index, state={}),
                coalesce_key="snapshot",
            )
        started = time.time()
        client.close(send_bye=True)
        self.assertLess(time.time() - started, 3.0)
        self.assertFalse(client.running)
        # Events after close still drain without blocking, ending in a
        # terminal connection event.
        names = [type(event).__name__ for event in client.poll_events()]
        self.assertTrue(
            any(name in ("ConnectionClosed", "ConnectionLost") for name in names)
        )

    def test_stale_generation_events_are_distinguishable(self) -> None:
        client = MultiplayerClient("127.0.0.1", self.port, generation=41)
        client.start()
        event, _ = wait_for(client, ("ConnectionUp",))
        self.assertEqual(event.generation, 41)
        client.close()


def _pump(games, seconds: float = 0.02, frames: int = 1) -> None:
    for _ in range(frames):
        for game in games:
            game.poll()
            if game.state == "playing":
                game.update(1 / 60)
        time.sleep(seconds)


def _wait_until(games, predicate, timeout: float = 20.0, seconds: float = 0.02):
    deadline = time.time() + timeout
    while time.time() < deadline:
        _pump(games, seconds=seconds)
        if predicate():
            return
    raise AssertionError("condition not reached before timeout")


class TwoGameFlowTests(unittest.TestCase):
    """The complete co-op session between two headless Game instances."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.harness = LoopbackServer()
        cls.port = cls.harness.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.harness.stop()

    def _make_game(self, tmpdir: str, name: str) -> Game:
        game = Game(
            screen_size=(640, 360),
            headless=True,
            save_path=Path(tmpdir) / f"{name}_run.json",
        )
        game.options_path = Path(tmpdir) / f"{name}_options.json"
        game.mp_player_name = name
        game.mp_server_host = "127.0.0.1"
        game.mp_server_port = self.port
        return game

    def test_lobby_start_snapshot_intent_and_partner_left(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            host = self._make_game(tmpdir, "Matti")
            join = self._make_game(tmpdir, "Partner")
            try:
                host.state = "mp_setup"
                host.mp_setup_step = "host_code"
                host.mp_run_id = generate_run_id()
                host.mp_begin_hosting()
                _wait_until([host], lambda: host.state == "mp_lobby")

                join.state = "mp_setup"
                join.mp_setup_step = "join_code"
                join.mp_submit_join_code(host.mp_run_id.lower())
                _wait_until([host, join], lambda: join.state == "mp_lobby")
                self.assertEqual(host.mp_session.partner_name, "Partner")

                host.selected_archetype = ARCHETYPES[0]  # Warden
                join.selected_archetype = ARCHETYPES[2]  # Arcanist
                host.mp_lobby_send_ready()
                join.mp_lobby_send_ready()
                _wait_until(
                    [host, join],
                    lambda: host.state == "playing" and join.state == "playing",
                    timeout=40.0,
                )

                # Both worlds agree on the roster and the floor.
                self.assertEqual(
                    [(p.player_id, p.class_name) for p in host.players],
                    [("p1", "Warden"), ("p2", "Arcanist")],
                )
                self.assertEqual(
                    [(p.player_id, p.class_name) for p in join.players],
                    [("p1", "Warden"), ("p2", "Arcanist")],
                )
                self.assertEqual(join.local_player_id, "p2")
                self.assertTrue(join.mp_is_joiner())
                self.assertTrue(host.mp_is_host())
                self.assertEqual(len(join.enemies), len(host.enemies))
                self.assertEqual(join.current_depth, host.current_depth)

                # Host movement propagates through snapshots to the joiner.
                host.player.x += 2.0
                target = host.player.x

                def joiner_sees_host() -> bool:
                    partner = next(
                        p for p in join.players if p.player_id == "p1"
                    )
                    net_x = getattr(partner, "net_x", None)
                    position = net_x if net_x is not None else partner.x
                    return abs(position - target) < 0.5

                _wait_until([host, join], joiner_sees_host, timeout=10.0)

                # Joiner ability presses become intents applied by the host.
                join.player_melee_attack()  # joiner-side: queues an intent
                _wait_until(
                    [host, join],
                    lambda: host.mp_session.intent_last_seq > 0,
                    timeout=10.0,
                )

                # Both render without touching dungeon-world fallthrough.
                host.draw()
                join.draw()

                # The joiner leaves; the host safely returns to the title.
                join.mp_shutdown(send_bye=True)
                _wait_until([host], lambda: host.state == "title", timeout=10.0)
                self.assertIn("partner", host.mp_title_notice.lower())

                # Multiplayer never wrote either single-player run save.
                self.assertFalse((Path(tmpdir) / "Matti_run.json").exists())
                self.assertFalse((Path(tmpdir) / "Partner_run.json").exists())
            finally:
                host.mp_shutdown(send_bye=False)
                join.mp_shutdown(send_bye=False)

    def test_stale_snapshot_and_stale_intents_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self._make_game(tmpdir, "Solo")
            from arch_rogue.net.mixin import MpSession

            session = MpSession(role="join")
            session.started = True
            session.floor_revision = 3
            session.last_snapshot_key = (3, 10)
            game.mp_session = session
            game.players = []
            game._mp_on_snapshot(
                SnapshotMessage(floor_revision=3, tick=9, state={"players": []})
            )
            self.assertEqual(session.last_snapshot_key, (3, 10))
            game._mp_on_snapshot(
                SnapshotMessage(floor_revision=2, tick=99, state={"players": []})
            )
            self.assertEqual(session.last_snapshot_key, (3, 10))

            host_session = MpSession(role="host")
            host_session.started = True
            host_session.intent_last_seq = 5
            game.mp_session = host_session
            game._mp_on_intent(
                IntentMessage(
                    input_seq=4, player_id="p2", move_x=1.0, move_y=0.0,
                    action="", target=None,
                ),
                time.monotonic(),
            )
            self.assertEqual(host_session.intent_move, (0.0, 0.0))
            game._mp_on_intent(
                IntentMessage(
                    input_seq=6, player_id="p2", move_x=1.0, move_y=0.0,
                    action="", target=None,
                ),
                time.monotonic(),
            )
            self.assertEqual(host_session.intent_move, (1.0, 0.0))
            game.mp_session = None

    def test_setup_error_notices_keep_flow_recoverable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self._make_game(tmpdir, "Lost")
            game.state = "mp_setup"
            game.mp_setup_step = "join_code"
            # Joining a code nobody hosts surfaces run_not_found and keeps
            # the entered code editable.
            game.mp_submit_join_code("ZZZZ")
            _wait_until(
                [game],
                lambda: game.mp_notice != "" and game.mp_session is None,
                timeout=10.0,
            )
            self.assertEqual(game.state, "mp_setup")
            self.assertEqual(game.mp_setup_step, "join_code")
            self.assertEqual(game.mp_join_code, "ZZZZ")
            self.assertTrue(game.text_input_active())
            game.close_text_input(confirm=False)

    def test_unconfigured_endpoint_blocks_role_choice(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self._make_game(tmpdir, "NoServer")
            game.mp_server_host = ""
            game.mp_server_port = 0
            game.state = "mp_setup"
            game.mp_setup_step = "role"
            game.mp_choose_role(True)
            self.assertEqual(game.mp_setup_step, "role")
            self.assertIn("Server not configured", game.mp_notice)
            self.assertIsNone(game.mp_session)


class MobileMultiplayerTests(unittest.TestCase):
    """Headless mobile-mode coverage: touch targets, back handling, and the
    suspend/resume + reconnect-grace paths. All branches stay gated by
    ``mobile_mode``; desktop tests never execute them."""

    def _make_mobile_game(self, tmpdir: str) -> Game:
        game = Game(
            screen_size=(1280, 720),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
            mobile=True,
            safe_insets=(48, 12, 24, 16),
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.mp_player_name = "Pocket"
        game.mp_server_host = "127.0.0.1"
        game.mp_server_port = 1  # loopback, nothing listens: tap tests only
        return game

    def test_mp_setup_role_rows_are_tappable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self._make_mobile_game(tmpdir)
            game.state = "mp_setup"
            game.mp_setup_step = "role"
            game.draw()
            self.assertEqual(game.mobile_input_context(), "mp_setup")
            rows = getattr(game, "_mp_row_rects", ())
            self.assertEqual(len(rows), 2)
            safe = game.mobile_safe_rect()
            tapped = game.handle_mobile_tap(
                (rows[1].centerx + safe.x, rows[1].centery + safe.y)
            )
            self.assertTrue(tapped)
            # Join was chosen: the join-code entry opened the soft keyboard.
            self.assertEqual(game.mp_setup_step, "join_code")
            self.assertTrue(game.text_input_active())
            game.close_text_input(confirm=False)
            game.mp_shutdown(send_bye=False)

    def test_mp_setup_entry_tap_reopens_soft_keyboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self._make_mobile_game(tmpdir)
            game.state = "mp_setup"
            game.mp_setup_step = "join_code"
            game.draw()
            entry = getattr(game, "_mp_entry_rect", None)
            self.assertIsNotNone(entry)
            self.assertFalse(game.text_input_active())
            safe = game.mobile_safe_rect()
            with patch("pygame.key.start_text_input") as start_input:
                tapped = game.handle_mobile_tap(
                    (entry.centerx + safe.x, entry.centery + safe.y)
                )
                self.assertTrue(tapped)
                self.assertTrue(start_input.called)
            self.assertTrue(game.text_input_active())
            with patch("pygame.key.stop_text_input") as stop_input:
                game.close_text_input(confirm=False)
                self.assertTrue(stop_input.called)

    def test_mobile_back_button_covers_mp_screens(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self._make_mobile_game(tmpdir)
            game.state = "mp_setup"
            game.mp_setup_step = "role"
            game.draw()
            targets = [
                target
                for target in game._mobile_touch_targets
                if target.command == Command.BACK
            ]
            self.assertTrue(targets)
            self.assertEqual(targets[0].context, "mp_setup")
            # BACK from the role step leaves to the title.
            game._dispatch_command(Command.BACK)
            self.assertEqual(game.state, "title")

            game.state = "mp_lobby"
            game.draw()
            contexts = {
                target.context for target in game._mobile_touch_targets
            }
            self.assertIn("mp_lobby", contexts)
            game._dispatch_command(Command.BACK)
            self.assertEqual(game.state, "mp_setup")

    def test_suspend_pauses_the_client_pump(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self._make_mobile_game(tmpdir)
            from arch_rogue.net.mixin import MpSession

            game.mp_session = MpSession(role="join")
            game.mp_session.next_ping_at = 0.0
            game.mobile_suspended = True
            # A suspended pump must not advance any session state.
            before = game.mp_session.next_ping_at
            game.poll()
            self.assertEqual(game.mp_session.next_ping_at, before)
            game.mobile_suspended = False
            game.mp_session = None

    def test_reconnect_grace_expiry_returns_to_title_with_notice(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self._make_mobile_game(tmpdir)
            from arch_rogue.net import mixin as net_mixin
            from arch_rogue.net.mixin import MpSession

            fake_now = [5000.0]
            with patch.object(
                net_mixin.time, "monotonic", side_effect=lambda: fake_now[0]
            ):
                session = MpSession(role="join")
                session.started = True
                session.reconnect_token = "ab" * 16
                game.mp_session = session
                game.mp_active = True
                game.mp_role = "join"
                game.state = "playing"
                game.players = []
                game.floaters = []

                # The socket dies during suspension: the grace window arms.
                game._mp_on_connection_lost("socket died", fake_now[0])
                self.assertTrue(session.reconnecting)

                # Within the grace window the client keeps trying (a client
                # object exists again after the next poll).
                fake_now[0] += 1.0
                game.poll()
                self.assertIsNotNone(game.mp_client)
                game._mp_drop_client()

                # Past the 30-second grace window the session fails safely to
                # the title with a loss notice, without touching any save.
                fake_now[0] += 31.0
                game.poll()
                self.assertEqual(game.state, "title")
                self.assertFalse(game.mp_active)
                self.assertTrue(game.mp_title_notice)
                self.assertFalse((Path(tmpdir) / "run.json").exists())


if __name__ == "__main__":
    unittest.main()
