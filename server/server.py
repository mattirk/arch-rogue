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

"""Asyncio TCP shell for the Arch Rogue multiplayer relay.

Run from a repo checkout with ``python -m server.server`` (or install the
``server/`` project and use the ``arch-rogue-server`` script). One asyncio
event loop serializes every :class:`~server.room.RoomHub` call, so the hub
needs no locks. Each connection gets a bounded outbound queue that coalesces
queued snapshots to the newest one, so one stalled reader can neither grow
server memory without bound nor watch an ever-older world.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
from collections import deque

from .config import ServerConfig
from .protocol import (
    LineFramer,
    MessageTooLargeError,
    ProtocolError,
    decode_message,
    encode_message,
)
from .room import RoomHub

log = logging.getLogger("arch_rogue_server")

_TICK_INTERVAL_SECONDS = 1.0
_READ_CHUNK_BYTES = 64 * 1024
_OUTBOUND_QUEUE_LIMIT = 256


class AsyncioPeer:
    """A ``PeerTransport`` over one ``StreamWriter`` with a writer task."""

    def __init__(self, writer: asyncio.StreamWriter, label: str) -> None:
        self._writer = writer
        self.label = label
        self._queue: deque[dict] = deque()
        self._wakeup = asyncio.Event()
        self._closing = False
        self._writer_task = asyncio.create_task(self._drain_loop())

    def send_message(self, message: dict) -> None:
        if self._closing:
            return
        if (
            message.get("t") == "snapshot"
            and self._queue
            and self._queue[-1].get("t") == "snapshot"
        ):
            # Coalesce queued snapshots to the newest one: a slow reader
            # skips world states instead of replaying an ever-older backlog.
            self._queue[-1] = message
        else:
            self._queue.append(message)
        if len(self._queue) > _OUTBOUND_QUEUE_LIMIT:
            log.warning("%s: outbound queue overflow, dropping peer", self.label)
            self.close()
            return
        self._wakeup.set()

    def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._wakeup.set()

    async def _drain_loop(self) -> None:
        try:
            while True:
                while self._queue:
                    message = self._queue.popleft()
                    try:
                        payload = encode_message(message)
                    except ProtocolError:
                        log.exception("%s: dropping unencodable message", self.label)
                        continue
                    self._writer.write(payload)
                    await self._writer.drain()
                if self._closing:
                    break
                self._wakeup.clear()
                await self._wakeup.wait()
        except (ConnectionError, OSError, asyncio.CancelledError):
            pass
        finally:
            self._closing = True
            with contextlib.suppress(ConnectionError, OSError):
                self._writer.close()

    async def wait_closed(self) -> None:
        with contextlib.suppress(asyncio.CancelledError):
            await self._writer_task
        with contextlib.suppress(ConnectionError, OSError):
            await self._writer.wait_closed()


class MultiplayerServer:
    def __init__(self, config: ServerConfig | None = None) -> None:
        self.config = config or ServerConfig()
        self.hub = RoomHub(self.config)
        self._server: asyncio.base_events.Server | None = None
        self._tick_task: asyncio.Task | None = None

    @property
    def bound_port(self) -> int:
        """The actual listening port (useful when configured with port 0)."""

        if self._server is None or not self._server.sockets:
            return self.config.port
        return int(self._server.sockets[0].getsockname()[1])

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle_client, self.config.host, self.config.port
        )
        self._tick_task = asyncio.create_task(self._tick_loop())
        log.info(
            "listening on %s:%d (run-id length %d, grace %.0fs, idle %.0fs)",
            self.config.host,
            self.bound_port,
            self.config.run_id_length,
            self.config.reconnect_grace,
            self.config.idle_timeout,
        )

    async def serve_forever(self) -> None:
        if self._server is None:
            await self.start()
        assert self._server is not None
        async with self._server:
            await self._server.serve_forever()

    async def close(self) -> None:
        if self._tick_task is not None:
            self._tick_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._tick_task
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _tick_loop(self) -> None:
        while True:
            await asyncio.sleep(_TICK_INTERVAL_SECONDS)
            self.hub.tick()

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer_name = writer.get_extra_info("peername")
        label = f"{peer_name[0]}:{peer_name[1]}" if peer_name else "peer"
        peer = AsyncioPeer(writer, label)
        connection = self.hub.connect(peer, peer_label=label)
        framer = LineFramer()
        expected_close = False
        try:
            while True:
                chunk = await reader.read(_READ_CHUNK_BYTES)
                if not chunk:
                    break
                try:
                    lines = framer.feed(chunk)
                except MessageTooLargeError as exc:
                    self.hub.handle_protocol_violation(connection, str(exc))
                    expected_close = True
                    break
                for line in lines:
                    try:
                        message = decode_message(line)
                    except ProtocolError as exc:
                        self.hub.handle_protocol_violation(connection, str(exc))
                        expected_close = True
                        break
                    self.hub.handle_message(connection, message)
                    if connection.closed:
                        expected_close = True
                        break
                if connection.closed:
                    expected_close = True
                    break
        except (ConnectionError, OSError):
            pass
        finally:
            self.hub.disconnect(connection, expected=expected_close)
            peer.close()
            await peer.wait_closed()


def main(argv: list[str] | None = None) -> None:
    defaults = ServerConfig.from_env()
    parser = argparse.ArgumentParser(
        prog="arch-rogue-server",
        description=(
            "Ephemeral in-memory relay server for Arch Rogue two-player "
            "co-op. Persists nothing; a room is dropped when both clients "
            "disconnect or after the idle timeout."
        ),
    )
    parser.add_argument("--host", default=defaults.host)
    parser.add_argument("--port", type=int, default=defaults.port)
    parser.add_argument(
        "--run-id-length",
        type=int,
        default=defaults.run_id_length,
        help=(
            "room code length (default %(default)s; raise to 8+ and "
            "rate-limit upstream for Internet-facing deployments)"
        ),
    )
    parser.add_argument(
        "--hello-timeout", type=float, default=defaults.hello_timeout
    )
    parser.add_argument(
        "--reconnect-grace", type=float, default=defaults.reconnect_grace
    )
    parser.add_argument(
        "--idle-timeout", type=float, default=defaults.idle_timeout
    )
    parser.add_argument("--max-rooms", type=int, default=defaults.max_rooms)
    parser.add_argument("--log-level", default=defaults.log_level)
    args = parser.parse_args(argv)

    config = ServerConfig(
        host=args.host,
        port=args.port,
        run_id_length=args.run_id_length,
        hello_timeout=args.hello_timeout,
        reconnect_grace=args.reconnect_grace,
        idle_timeout=args.idle_timeout,
        max_rooms=args.max_rooms,
        log_level=args.log_level,
    )
    logging.basicConfig(
        level=getattr(logging, str(config.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    server = MultiplayerServer(config)
    try:
        asyncio.run(server.serve_forever())
    except KeyboardInterrupt:
        log.info("shutting down")


if __name__ == "__main__":
    main()
