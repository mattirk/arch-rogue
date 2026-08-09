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

"""``MultiplayerClient`` — the thin socket connector for co-op sessions.

One client object owns one TCP connection lifecycle: a single background
thread connects, then multiplexes reads and queued writes with ``select``.
The thread only decodes and enqueues immutable typed messages — it never
mutates ``Game``, Pygame objects, or game collections; all state changes
happen on the main thread inside ``NetMixin.poll()``.

With ``tls=True`` the connection is wrapped in TLS before ``ConnectionUp``
fires: the handshake runs in blocking mode under ``connect_timeout``, the
server certificate chain and hostname are verified against the platform
trust store (``default_tls_context``), and the select loop then treats the
``SSLSocket`` like the plain socket plus the two TLS caveats — WantRead/
WantWrite retries and draining ``pending()`` plaintext that ``select`` on
the raw fd cannot see.

Queue bounds: queued inbound snapshots are coalesced to the newest one while
reliable control events keep their order; outbound movement intents and host
snapshots coalesce by key so a stalled peer never grows an unbounded backlog.
Every event is tagged with the client's connection generation so stale events
from a superseded reconnect attempt are ignored by the consumer.

This module must stay Pygame-free.
"""

from __future__ import annotations

import select
import socket
import ssl
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

from .messages import NetMessage, SnapshotMessage, message_from_dict
from .protocol import (
    LineFramer,
    ProtocolError,
    decode_message,
    encode_message,
    make_bye,
)

__all__ = [
    "MultiplayerClient",
    "ClientEvent",
    "ConnectionUp",
    "ConnectionFailed",
    "ConnectionLost",
    "ConnectionClosed",
    "default_tls_context",
]

_RECV_CHUNK_BYTES = 64 * 1024
_SELECT_TIMEOUT_SECONDS = 0.5
_CLOSE_FLUSH_SECONDS = 0.5
_THREAD_JOIN_SECONDS = 2.0
_INBOUND_QUEUE_LIMIT = 512
_OUTBOUND_QUEUE_LIMIT = 256

# Outbound coalesce keys. Only the newest queued payload per key survives;
# one-shot intents and control messages never pass a key so they are all
# delivered in order.
COALESCE_SNAPSHOT = "snapshot"
COALESCE_MOVE_INTENT = "move_intent"


@dataclass(frozen=True)
class ClientEvent:
    """Base class for connection-lifecycle events."""

    generation: int


@dataclass(frozen=True)
class ConnectionUp(ClientEvent):
    pass


@dataclass(frozen=True)
class ConnectionFailed(ClientEvent):
    reason: str = ""


@dataclass(frozen=True)
class ConnectionLost(ClientEvent):
    reason: str = ""


@dataclass(frozen=True)
class ConnectionClosed(ClientEvent):
    pass


@dataclass(frozen=True)
class InboundMessage(ClientEvent):
    message: NetMessage = field(default_factory=NetMessage)


ConnectFactory = Callable[[str, int, float], socket.socket]


def _default_connect(host: str, port: int, timeout: float) -> socket.socket:
    return socket.create_connection((host, port), timeout=timeout)


def default_tls_context() -> ssl.SSLContext:
    """Strict client-side TLS: system trust store, TLS 1.2+, hostname checked.

    ``create_default_context`` already enables ``CERT_REQUIRED`` and hostname
    verification. On platforms whose Python ships without a system CA bundle
    (notably python-for-android), fall back to ``certifi`` when it is
    installed; with no trust anchors at all the handshake fails closed
    instead of silently trusting any certificate.
    """

    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    if context.cert_store_stats().get("x509_ca", 0) == 0:
        try:
            import certifi
        except ImportError:
            pass
        else:
            context.load_verify_locations(cafile=certifi.where())
    return context


class MultiplayerClient:
    """One TCP connection to the relay server, driven by one worker thread."""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        generation: int = 0,
        connect_timeout: float = 6.0,
        connect_factory: ConnectFactory | None = None,
        sock: socket.socket | None = None,
        tls: bool = False,
        tls_context: ssl.SSLContext | None = None,
        server_hostname: str | None = None,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.generation = int(generation)
        self.connect_timeout = float(connect_timeout)
        self._connect_factory = connect_factory or _default_connect
        self._preconnected = sock
        self.tls = bool(tls)
        self._tls_context = tls_context
        self._server_hostname = server_hostname or host

        self._events: deque[ClientEvent] = deque()
        self._events_lock = threading.Lock()
        self._outbound: deque[tuple[str | None, bytes]] = deque()
        self._outbound_lock = threading.Lock()

        self._thread: threading.Thread | None = None
        self._sock: socket.socket | None = None
        self._closing = threading.Event()
        self._finished = threading.Event()
        # A socketpair wakes the selector immediately when the main thread
        # queues a message or requests close, so one-shot intents go out
        # promptly instead of waiting for the select timeout.
        self._wake_recv, self._wake_send = socket.socketpair()
        self._wake_recv.setblocking(False)

    # -- main-thread API -----------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run,
            name=f"mp-client-{self.generation}",
            daemon=True,
        )
        self._thread.start()

    @property
    def running(self) -> bool:
        return self._thread is not None and not self._finished.is_set()

    def send_message(
        self, message: dict, *, coalesce_key: str | None = None
    ) -> bool:
        """Queue one outbound message. Returns False when the client is done."""

        if self._closing.is_set() or self._finished.is_set():
            return False
        try:
            payload = encode_message(message)
        except ProtocolError:
            return False
        with self._outbound_lock:
            if (
                coalesce_key is not None
                and self._outbound
                and self._outbound[-1][0] == coalesce_key
            ):
                self._outbound[-1] = (coalesce_key, payload)
            else:
                if len(self._outbound) >= _OUTBOUND_QUEUE_LIMIT:
                    return False
                self._outbound.append((coalesce_key, payload))
        self._wake()
        return True

    def poll_events(self) -> list[ClientEvent]:
        """Drain all pending events (main thread only)."""

        with self._events_lock:
            if not self._events:
                return []
            events = list(self._events)
            self._events.clear()
        return events

    def close(self, *, send_bye: bool = False) -> None:
        """Request shutdown and join the worker thread.

        ``send_bye`` flushes a final graceful ``bye`` before the socket
        closes. Safe to call repeatedly and from any state.
        """

        if send_bye and not self._closing.is_set() and not self._finished.is_set():
            try:
                payload = encode_message(make_bye())
            except ProtocolError:  # pragma: no cover - bye always encodes
                payload = b""
            if payload:
                with self._outbound_lock:
                    self._outbound.append((None, payload))
        self._closing.set()
        self._wake()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=_THREAD_JOIN_SECONDS)
        if thread is None:
            # Never started: emit the terminal event so consumers converge.
            self._finished.set()
            self._enqueue_event(ConnectionClosed(self.generation))
        self._close_wake_pair()

    # -- worker thread -------------------------------------------------------

    def _wake(self) -> None:
        try:
            self._wake_send.send(b"x")
        except OSError:
            pass

    def _close_wake_pair(self) -> None:
        if not self._finished.is_set():
            return
        for wake_socket in (self._wake_recv, self._wake_send):
            try:
                wake_socket.close()
            except OSError:
                pass

    def _enqueue_event(self, event: ClientEvent) -> None:
        with self._events_lock:
            self._events.append(event)

    def _enqueue_message(self, message: NetMessage) -> bool:
        """Enqueue one inbound message, coalescing consecutive snapshots."""

        with self._events_lock:
            if isinstance(message, SnapshotMessage):
                tail = self._events[-1] if self._events else None
                if isinstance(tail, InboundMessage) and isinstance(
                    tail.message, SnapshotMessage
                ):
                    self._events[-1] = InboundMessage(self.generation, message)
                    return True
            if len(self._events) >= _INBOUND_QUEUE_LIMIT:
                return False
            self._events.append(InboundMessage(self.generation, message))
        return True

    def _run(self) -> None:
        sock: socket.socket | None = None
        try:
            if self._preconnected is not None:
                sock = self._preconnected
            else:
                sock = self._connect_factory(
                    self.host, self.port, self.connect_timeout
                )
            if self.tls:
                # Handshake in blocking mode under the connect timeout;
                # certificate chain and hostname are verified here, so
                # ConnectionUp only ever fires on an authenticated channel.
                context = self._tls_context or default_tls_context()
                sock.settimeout(self.connect_timeout)
                sock = context.wrap_socket(
                    sock, server_hostname=self._server_hostname
                )
        except OSError as exc:
            self._shutdown_socket(sock)
            self._finished.set()
            self._enqueue_event(
                ConnectionFailed(self.generation, reason=str(exc) or "connect failed")
            )
            return
        if self._closing.is_set():
            self._shutdown_socket(sock)
            self._finished.set()
            self._enqueue_event(ConnectionClosed(self.generation))
            return

        self._sock = sock
        sock.setblocking(False)
        framer = LineFramer()
        self._enqueue_event(ConnectionUp(self.generation))
        outcome: ClientEvent | None = None
        pending_send = b""
        flush_deadline: float | None = None
        try:
            while True:
                if self._closing.is_set() and flush_deadline is None:
                    flush_deadline = time.monotonic() + _CLOSE_FLUSH_SECONDS
                with self._outbound_lock:
                    has_outbound = bool(self._outbound) or bool(pending_send)
                if self._closing.is_set() and not has_outbound:
                    outcome = ConnectionClosed(self.generation)
                    break
                if flush_deadline is not None and time.monotonic() > flush_deadline:
                    outcome = ConnectionClosed(self.generation)
                    break
                try:
                    readable, writable, _ = select.select(
                        [sock, self._wake_recv],
                        [sock] if has_outbound else [],
                        [],
                        _SELECT_TIMEOUT_SECONDS,
                    )
                except (OSError, ValueError):
                    outcome = ConnectionLost(self.generation, reason="socket error")
                    break

                if self._wake_recv in readable:
                    try:
                        while self._wake_recv.recv(1024):
                            pass
                    except (BlockingIOError, InterruptedError):
                        pass
                    except OSError:
                        pass

                if sock in readable:
                    while True:
                        try:
                            chunk = sock.recv(_RECV_CHUNK_BYTES)
                        except (
                            BlockingIOError,
                            InterruptedError,
                            ssl.SSLWantReadError,
                            ssl.SSLWantWriteError,
                        ):
                            chunk = None
                        except OSError as exc:
                            outcome = ConnectionLost(
                                self.generation, reason=str(exc) or "recv failed"
                            )
                            break
                        if chunk == b"":
                            if self._closing.is_set():
                                outcome = ConnectionClosed(self.generation)
                            else:
                                outcome = ConnectionLost(
                                    self.generation,
                                    reason="server closed the connection",
                                )
                            break
                        if chunk:
                            try:
                                lines = framer.feed(chunk)
                            except ProtocolError as exc:
                                outcome = ConnectionLost(
                                    self.generation, reason=str(exc)
                                )
                                break
                            for line in lines:
                                try:
                                    decoded = message_from_dict(
                                        decode_message(line)
                                    )
                                except ProtocolError as exc:
                                    outcome = ConnectionLost(
                                        self.generation, reason=str(exc)
                                    )
                                    break
                                if not self._enqueue_message(decoded):
                                    outcome = ConnectionLost(
                                        self.generation,
                                        reason="inbound queue overflow",
                                    )
                                    break
                            if outcome is not None:
                                break
                        # One TLS read may decrypt more records than one
                        # recv returns; drain them now — select() watches
                        # the raw fd and cannot see buffered plaintext.
                        if not (
                            chunk
                            and isinstance(sock, ssl.SSLSocket)
                            and sock.pending() > 0
                        ):
                            break
                    if outcome is not None:
                        break

                if sock in writable or (has_outbound and not pending_send):
                    if not pending_send:
                        with self._outbound_lock:
                            if self._outbound:
                                pending_send = self._outbound.popleft()[1]
                    while pending_send:
                        try:
                            sent = sock.send(pending_send)
                        except (
                            BlockingIOError,
                            InterruptedError,
                            ssl.SSLWantReadError,
                            ssl.SSLWantWriteError,
                        ):
                            break
                        except OSError as exc:
                            outcome = ConnectionLost(
                                self.generation, reason=str(exc) or "send failed"
                            )
                            break
                        pending_send = pending_send[sent:]
                        if not pending_send:
                            with self._outbound_lock:
                                if self._outbound:
                                    pending_send = self._outbound.popleft()[1]
                    if isinstance(outcome, ConnectionLost):
                        break
        finally:
            self._shutdown_socket(sock)
            self._sock = None
            self._finished.set()
            self._enqueue_event(outcome or ConnectionClosed(self.generation))

    @staticmethod
    def _shutdown_socket(sock: socket.socket | None) -> None:
        if sock is None:
            return
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            sock.close()
        except OSError:
            pass
