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
import collections
import os
import shutil
import ssl
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

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


@unittest.skipUnless(shutil.which("openssl"), "openssl CLI required")
class TlsTransportTests(unittest.TestCase):
    """TLS end to end: the bundled server terminates, the client verifies.

    Covers the nginx-stream deployment shape too — a client that trusts the
    server certificate completes the handshake and the newline-JSON protocol
    runs unchanged on top; wrong-trust and wrong-transport pairings surface
    clean ``ConnectionFailed``/``ConnectionLost`` events instead of hangs or
    raw ``ECONNRESET`` tracebacks.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmpdir = tempfile.TemporaryDirectory()
        base = Path(cls.tmpdir.name)
        cls.cert_path = base / "cert.pem"
        cls.key_path = base / "key.pem"
        subprocess.run(
            [
                "openssl", "req", "-x509",
                "-newkey", "ec",
                "-pkeyopt", "ec_paramgen_curve:prime256v1",
                "-keyout", str(cls.key_path),
                "-out", str(cls.cert_path),
                "-days", "2", "-nodes",
                "-subj", "/CN=localhost",
                "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
            ],
            check=True,
            capture_output=True,
        )
        cls.harness = LoopbackServer(
            tls_cert=str(cls.cert_path), tls_key=str(cls.key_path)
        )
        cls.port = cls.harness.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.harness.stop()
        cls.tmpdir.cleanup()

    def _trusting_context(self) -> ssl.SSLContext:
        # Standard client verification with the self-signed test certificate
        # pinned as the only trust anchor; hostname checking stays on.
        return ssl.create_default_context(cafile=str(self.cert_path))

    def test_handshake_and_welcome_over_tls(self) -> None:
        client = MultiplayerClient(
            "127.0.0.1",
            self.port,
            generation=7,
            tls=True,
            tls_context=self._trusting_context(),
        )
        client.start()
        wait_for(client, ("ConnectionUp",))
        client.send_message(
            make_hello(
                seq=1, name="Matti", run_id=generate_run_id(), role="host",
                content_revision="t",
            )
        )
        welcome, _ = wait_for(client, ("Welcome",))
        self.assertIsInstance(welcome, Welcome)
        self.assertEqual(welcome.you_are, "host")
        client.close(send_bye=True)
        self.assertFalse(client.running)

    def test_untrusted_certificate_is_rejected(self) -> None:
        # Default trust store (no our-CA): verification must fail closed
        # before any protocol byte is sent.
        client = MultiplayerClient(
            "127.0.0.1", self.port, generation=8, tls=True
        )
        client.start()
        event, _ = wait_for(client, ("ConnectionFailed",), timeout=10.0)
        self.assertIn("certificate", event.reason.lower())
        client.close()

    def test_plaintext_client_to_tls_server_fails_cleanly(self) -> None:
        # The pre-TLS client against a TLS endpoint: the historical
        # "errno 104 connection reset by peer". It must surface as a clean
        # ConnectionLost/ConnectionFailed event, never a hang.
        client = MultiplayerClient("127.0.0.1", self.port, generation=9)
        client.start()
        wait_for(client, ("ConnectionUp",))  # TCP accept precedes TLS reject
        client.send_message(
            make_hello(
                seq=1, name="Doomed", run_id=generate_run_id(), role="host",
                content_revision="t",
            )
        )
        event, _ = wait_for(
            client, ("ConnectionLost", "ConnectionFailed"), timeout=10.0
        )
        self.assertIn(type(event).__name__, ("ConnectionLost", "ConnectionFailed"))
        client.close()

    def test_tls_client_to_plaintext_server_fails_cleanly(self) -> None:
        plain = LoopbackServer()
        port = plain.start()
        try:
            client = MultiplayerClient(
                "127.0.0.1",
                port,
                generation=10,
                tls=True,
                tls_context=self._trusting_context(),
                connect_timeout=1.5,
            )
            client.start()
            event, _ = wait_for(client, ("ConnectionFailed",), timeout=10.0)
            self.assertTrue(event.reason)
            client.close()
        finally:
            plain.stop()


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
        game.mp_server_tls = False  # the loopback relay speaks plain TCP
        game._mp_consented_endpoint = ("127.0.0.1", self.port)
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

                # The host must admit the knocking joiner before readying.
                self.assertTrue(host.mp_session.partner_pending_accept)
                host.mp_lobby_send_ready()
                self.assertFalse(host.mp_session.local_ready)
                host.mp_lobby_accept_partner()
                self.assertFalse(host.mp_session.partner_pending_accept)

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


class JoinerMouseWalkVectorTests(unittest.TestCase):
    """The joiner's move-intent sampling must include mouse hold-to-walk.

    ``_mp_local_move_vector`` feeds both the outbound 20 Hz intents and the
    joiner's local facing prediction, so a solo headless run (whose camera
    and player mirror the joiner's local view) exercises it without a relay.
    """

    def _make_playing_game(self, tmpdir: str) -> Game:
        game = Game(
            screen_size=(640, 360),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.restart(ARCHETYPES[0])
        # A live run opens on the story intro; a real joiner walks only
        # after dismissing it, and the mouse fallback respects the same gate.
        game.story_intro_pending = False
        game.active_cutscene = None
        game.snap_camera_to_player()
        return game

    def test_held_button_walks_toward_cursor_and_menus_suppress(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self._make_playing_game(tmpdir)
            cursor = game.world_to_screen(game.player.x + 3.0, game.player.y)
            with patch("pygame.mouse.get_pressed", return_value=(1, 0, 0)), patch(
                "pygame.mouse.get_pos", return_value=cursor
            ):
                move_x, move_y = game._mp_local_move_vector()
                self.assertGreater(move_x, 0.9)
                self.assertLess(abs(move_y), 0.2)
                # The cursor also aims the local actor, like on the host.
                self.assertGreater(game.player.facing_x, 0.9)
                for flag in ("inventory_open", "character_menu_open", "shop_open"):
                    setattr(game, flag, True)
                    self.assertEqual(
                        game._mp_local_move_vector(), (0.0, 0.0), flag
                    )
                    setattr(game, flag, False)
                game.story_intro_pending = True
                self.assertEqual(game._mp_local_move_vector(), (0.0, 0.0))
                game.story_intro_pending = False

    def test_release_and_stop_radius_give_zero_vector(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self._make_playing_game(tmpdir)
            far = game.world_to_screen(game.player.x + 3.0, game.player.y)
            with patch("pygame.mouse.get_pressed", return_value=(0, 0, 0)), patch(
                "pygame.mouse.get_pos", return_value=far
            ):
                self.assertEqual(game._mp_local_move_vector(), (0.0, 0.0))
            near = game.world_to_screen(game.player.x + 0.05, game.player.y)
            with patch("pygame.mouse.get_pressed", return_value=(1, 0, 0)), patch(
                "pygame.mouse.get_pos", return_value=near
            ):
                self.assertEqual(game._mp_local_move_vector(), (0.0, 0.0))

    def test_keyboard_still_takes_priority_over_mouse(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self._make_playing_game(tmpdir)
            # Cursor to the east, keyboard pressing north: keyboard wins.
            cursor = game.world_to_screen(game.player.x + 3.0, game.player.y)
            keys = collections.defaultdict(int, {pygame.K_w: 1})
            with patch("pygame.key.get_pressed", return_value=keys), patch(
                "pygame.mouse.get_pressed", return_value=(1, 0, 0)
            ), patch("pygame.mouse.get_pos", return_value=cursor):
                self.assertEqual(game._mp_local_move_vector(), (0.0, -1.0))


class HostAcceptGateTests(unittest.TestCase):
    """The lobby accept gate: a knocking joiner is admitted or turned away."""

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
        game.mp_server_tls = False
        game._mp_consented_endpoint = ("127.0.0.1", self.port)
        return game

    def test_decline_kicks_joiner_and_reopens_the_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            host = self._make_game(tmpdir, "Matti")
            first = self._make_game(tmpdir, "Stranger")
            second = self._make_game(tmpdir, "Friend")
            try:
                host.state = "mp_setup"
                host.mp_setup_step = "host_code"
                host.mp_run_id = generate_run_id()
                code = host.mp_run_id
                host.mp_begin_hosting()
                _wait_until([host], lambda: host.state == "mp_lobby")

                first.state = "mp_setup"
                first.mp_setup_step = "join_code"
                first.mp_submit_join_code(code)
                _wait_until(
                    [host, first],
                    lambda: host.mp_session is not None
                    and host.mp_session.partner_pending_accept,
                )

                # Turned away: the joiner lands back in setup with a notice,
                # the host keeps the lobby with an empty partner seat.
                host.mp_lobby_decline_partner()
                _wait_until(
                    [host, first],
                    lambda: first.state == "mp_setup"
                    and first.mp_session is None,
                )
                self.assertIn("turned you away", first.mp_notice.lower())
                self.assertEqual(first.mp_setup_step, "join_code")
                first.close_text_input(confirm=False)
                self.assertEqual(host.state, "mp_lobby")
                self.assertEqual(host.mp_session.partner_name, "")
                self.assertFalse(host.mp_session.partner_pending_accept)

                # The same code accepts a fresh knock, which can be admitted.
                second.state = "mp_setup"
                second.mp_setup_step = "join_code"
                second.mp_submit_join_code(code)
                _wait_until(
                    [host, second],
                    lambda: host.mp_session is not None
                    and host.mp_session.partner_pending_accept,
                )
                self.assertEqual(host.mp_session.partner_name, "Friend")
                host.mp_lobby_confirm()  # admits (does not ready up)
                self.assertFalse(host.mp_session.partner_pending_accept)
                self.assertFalse(host.mp_session.local_ready)
                self.assertEqual(second.state, "mp_lobby")
            finally:
                host.mp_shutdown(send_bye=False)
                first.mp_shutdown(send_bye=False)
                second.mp_shutdown(send_bye=False)

    def test_joiner_never_gates_and_decline_is_host_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self._make_game(tmpdir, "Solo")
            from arch_rogue.net.mixin import MpSession

            session = MpSession(role="join", phase="lobby")
            session.partner_name = "Hosty"
            game.mp_session = session
            # Neither accept nor decline does anything for a joiner.
            game.mp_lobby_accept_partner()
            game.mp_lobby_decline_partner()
            self.assertFalse(session.partner_pending_accept)
            self.assertEqual(session.partner_name, "Hosty")
            game.mp_session = None


class ConsentGateTests(unittest.TestCase):
    """The connection consent screen precedes the first socket per endpoint."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.harness = LoopbackServer()
        cls.port = cls.harness.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.harness.stop()

    def _make_unconsented_game(self, tmpdir: str) -> Game:
        game = Game(
            screen_size=(640, 360),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.mp_player_name = "Wary"
        game.mp_server_host = "127.0.0.1"
        game.mp_server_port = self.port
        game.mp_server_tls = False
        return game

    def test_hosting_shows_consent_before_any_socket(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self._make_unconsented_game(tmpdir)
            try:
                game.state = "mp_setup"
                game.mp_setup_step = "host_code"
                game.mp_run_id = generate_run_id()
                game.mp_begin_hosting()
                self.assertEqual(game.state, "mp_consent")
                self.assertIsNone(game.mp_client)
                self.assertIsNone(game.mp_session)
                # The screen renders headless and publishes Agree/Exit rows.
                game.draw()
                self.assertEqual(len(game._mp_row_rects), 2)
                # Agreeing opens the session and reaches the lobby.
                game.mp_consent_agree()
                self.assertIsNotNone(game.mp_client)
                _wait_until([game], lambda: game.state == "mp_lobby")
                # Re-hosting on the same endpoint skips straight past consent.
                game.mp_back_to_title()
                game.state = "mp_setup"
                game.mp_setup_step = "host_code"
                game.mp_run_id = generate_run_id()
                game.mp_begin_hosting()
                self.assertNotEqual(game.state, "mp_consent")
                self.assertIsNotNone(game.mp_client)
            finally:
                game.mp_shutdown(send_bye=False)

    def test_exit_declines_without_connecting(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self._make_unconsented_game(tmpdir)
            game.state = "mp_setup"
            game.mp_setup_step = "join_code"
            game.mp_submit_join_code(generate_run_id())
            self.assertEqual(game.state, "mp_consent")
            self.assertIsNone(game.mp_client)
            game.mp_consent_exit()
            self.assertEqual(game.state, "mp_setup")
            self.assertEqual(game.mp_setup_step, "role")
            self.assertIsNone(game.mp_client)
            self.assertTrue(game.mp_consent_required())

    def test_endpoint_change_requires_fresh_consent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self._make_unconsented_game(tmpdir)
            game._mp_consented_endpoint = ("127.0.0.1", self.port)
            self.assertFalse(game.mp_consent_required())
            game.mp_server_host = "other.example"
            self.assertTrue(game.mp_consent_required())


class HostileDataTests(unittest.TestCase):
    """Hostile peer payloads: malformed snapshots and unsanitized strings."""

    def _make_game(self, tmpdir: str) -> Game:
        game = Game(
            screen_size=(640, 360),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.mp_server_tls = False
        return game

    def test_malformed_snapshot_fails_the_session_cleanly(self) -> None:
        from arch_rogue.models import Player
        from arch_rogue.net.mixin import MpSession

        with tempfile.TemporaryDirectory() as tmpdir:
            game = self._make_game(tmpdir)
            session = MpSession(role="join")
            session.started = True
            session.floor_revision = 3
            session.last_snapshot_key = (3, 10)
            game.mp_session = session
            actor = Player(1.0, 1.0)
            actor.player_id = "p2"
            game.players = [actor]
            game._mp_on_snapshot(
                SnapshotMessage(
                    floor_revision=3,
                    tick=11,
                    state={"players": [{"id": "p2", "x": "not-a-number"}]},
                )
            )
            # No exception escaped, and the session ended with a notice.
            self.assertIsNone(game.mp_session)
            self.assertIn("snapshot", game.mp_notice.lower())

    def test_inbound_names_are_sanitized_at_ingestion(self) -> None:
        from arch_rogue.net.messages import message_from_dict
        from arch_rogue_protocol import MP_PLAYER_NAME_MAX_CHARS

        hostile = "‮evil\x00\r\n\t" + "A" * 5000
        joined = message_from_dict({"t": "partner_joined", "name": hostile})
        self.assertLessEqual(len(joined.name), MP_PLAYER_NAME_MAX_CHARS)
        self.assertTrue(all(c.isprintable() for c in joined.name))
        self.assertNotIn("‮", joined.name)

        start = message_from_dict(
            {"t": "start", "host_name": hostile, "joiner_name": hostile}
        )
        self.assertLessEqual(len(start.host_name), MP_PLAYER_NAME_MAX_CHARS)
        self.assertLessEqual(len(start.joiner_name), MP_PLAYER_NAME_MAX_CHARS)

        error = message_from_dict(
            {"t": "error", "code": "x" * 999, "msg": "y\x00" * 999}
        )
        self.assertLessEqual(len(error.code), 64)
        self.assertLessEqual(len(error.msg), 256)
        self.assertNotIn("\x00", error.msg)

        ended = message_from_dict(
            {
                "t": "run_ended",
                "outcome": "victory",
                "results": [{"name": hostile, "level": 3, "alive": True}],
            }
        )
        self.assertLessEqual(
            len(ended.results[0]["name"]), MP_PLAYER_NAME_MAX_CHARS
        )

    def test_floor_and_snapshot_display_names_are_sanitized(self) -> None:
        from arch_rogue.models import Player
        from arch_rogue.net import sync

        with tempfile.TemporaryDirectory() as tmpdir:
            game = self._make_game(tmpdir)
            hostile = "bad\x00‮name" + "B" * 500
            player = sync.build_player_from_full(
                game, {"x": 1.0, "y": 1.0, "display_name": hostile}
            )
            self.assertTrue(all(c.isprintable() for c in player.display_name))
            self.assertLess(len(player.display_name), 100)

    def test_kick_is_host_only_and_needs_a_seq(self) -> None:
        from arch_rogue_protocol import (
            make_kick,
            role_allowed,
            validate_client_message,
        )

        self.assertTrue(role_allowed("kick", "host"))
        self.assertFalse(role_allowed("kick", "join"))
        self.assertEqual(validate_client_message({"t": "kick"}), "bad_msg")
        self.assertEqual(validate_client_message(make_kick(seq=3)), "")


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
        game.mp_server_tls = False
        game._mp_consented_endpoint = ("127.0.0.1", 1)
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
