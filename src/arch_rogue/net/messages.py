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

"""Typed message dataclasses for the multiplayer client.

The background receiver thread parses decoded wire dicts into these immutable
message objects and enqueues them; ``NetMixin.poll()`` consumes them on the
main thread. Unknown message types become :class:`UnknownMessage` so forward
compatibility never raises. This module must stay Pygame-free.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .protocol import clamp_unit

__all__ = [
    "NetMessage",
    "Welcome",
    "PartnerJoined",
    "PartnerRejoined",
    "PartnerDisconnected",
    "PartnerLeft",
    "ReadyAck",
    "Start",
    "FloorMessage",
    "SnapshotMessage",
    "IntentMessage",
    "RunEndedMessage",
    "PongMessage",
    "ErrorMessage",
    "ByeMessage",
    "UnknownMessage",
    "message_from_dict",
]


@dataclass(frozen=True)
class NetMessage:
    """Base class for all typed inbound messages."""


@dataclass(frozen=True)
class Welcome(NetMessage):
    seq: int
    run_id: str
    you_are: str
    player_id: str
    reconnect_token: str
    partner_name: str | None
    partner_ready: bool


@dataclass(frozen=True)
class PartnerJoined(NetMessage):
    name: str
    player_id: str


@dataclass(frozen=True)
class PartnerRejoined(NetMessage):
    name: str
    player_id: str


@dataclass(frozen=True)
class PartnerDisconnected(NetMessage):
    grace_seconds: float


@dataclass(frozen=True)
class PartnerLeft(NetMessage):
    pass


@dataclass(frozen=True)
class ReadyAck(NetMessage):
    player_id: str
    archetype_key: str
    seq: int | None


@dataclass(frozen=True)
class Start(NetMessage):
    run_seed: int
    host_player_id: str
    host_name: str
    host_archetype: str
    joiner_player_id: str
    joiner_name: str
    joiner_archetype: str


@dataclass(frozen=True)
class FloorMessage(NetMessage):
    floor_revision: int
    depth: int
    floor_seed: int
    state: dict[str, Any] = field(compare=False)


@dataclass(frozen=True)
class SnapshotMessage(NetMessage):
    floor_revision: int
    tick: int
    state: dict[str, Any] = field(compare=False)


@dataclass(frozen=True)
class IntentMessage(NetMessage):
    input_seq: int
    player_id: str
    move_x: float
    move_y: float
    action: str
    target: str | None


@dataclass(frozen=True)
class RunEndedMessage(NetMessage):
    outcome: str
    results: tuple[dict[str, Any], ...] = field(compare=False)


@dataclass(frozen=True)
class PongMessage(NetMessage):
    seq: int
    ts: float


@dataclass(frozen=True)
class ErrorMessage(NetMessage):
    code: str
    msg: str
    fatal: bool
    seq: int | None


@dataclass(frozen=True)
class ByeMessage(NetMessage):
    pass


@dataclass(frozen=True)
class UnknownMessage(NetMessage):
    type: str
    data: dict[str, Any] = field(compare=False)


def _opt_str(value: Any) -> str | None:
    return str(value) if isinstance(value, str) else None


def _opt_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def message_from_dict(data: dict[str, Any]) -> NetMessage:
    """Convert one decoded wire dict into a typed, immutable message.

    Field coercion is defensive: a peer that omits or mistypes optional
    fields yields safe defaults rather than an exception on the receiver
    thread. Structurally hopeless payloads become :class:`UnknownMessage`.
    """

    message_type = str(data.get("t", ""))
    try:
        if message_type == "welcome":
            return Welcome(
                seq=int(data.get("seq", 0)),
                run_id=str(data.get("run_id", "")),
                you_are=str(data.get("you_are", "")),
                player_id=str(data.get("player_id", "")),
                reconnect_token=str(data.get("reconnect_token", "")),
                partner_name=_opt_str(data.get("partner_name")),
                partner_ready=bool(data.get("partner_ready", False)),
            )
        if message_type == "partner_joined":
            return PartnerJoined(
                name=str(data.get("name", "")),
                player_id=str(data.get("player_id", "")),
            )
        if message_type == "partner_rejoined":
            return PartnerRejoined(
                name=str(data.get("name", "")),
                player_id=str(data.get("player_id", "")),
            )
        if message_type == "partner_disconnected":
            return PartnerDisconnected(
                grace_seconds=float(data.get("grace_seconds", 0.0)),
            )
        if message_type == "partner_left":
            return PartnerLeft()
        if message_type == "ready_ack":
            return ReadyAck(
                player_id=str(data.get("player_id", "")),
                archetype_key=str(data.get("archetype_key", "")),
                seq=_opt_int(data.get("seq")),
            )
        if message_type == "start":
            return Start(
                run_seed=int(data.get("run_seed", 0)),
                host_player_id=str(data.get("host_player_id", "")),
                host_name=str(data.get("host_name", "")),
                host_archetype=str(data.get("host_archetype", "")),
                joiner_player_id=str(data.get("joiner_player_id", "")),
                joiner_name=str(data.get("joiner_name", "")),
                joiner_archetype=str(data.get("joiner_archetype", "")),
            )
        if message_type == "floor":
            state = data.get("state")
            return FloorMessage(
                floor_revision=int(data.get("floor_revision", 0)),
                depth=int(data.get("depth", 1)),
                floor_seed=int(data.get("floor_seed", 0)),
                state=state if isinstance(state, dict) else {},
            )
        if message_type == "snapshot":
            state = data.get("state")
            return SnapshotMessage(
                floor_revision=int(data.get("floor_revision", 0)),
                tick=int(data.get("tick", 0)),
                state=state if isinstance(state, dict) else {},
            )
        if message_type == "intent":
            return IntentMessage(
                input_seq=int(data.get("input_seq", 0)),
                player_id=str(data.get("player_id", "")),
                move_x=clamp_unit(data.get("move_x", 0.0)),
                move_y=clamp_unit(data.get("move_y", 0.0)),
                action=str(data.get("action", "")),
                target=_opt_str(data.get("target")),
            )
        if message_type == "run_ended":
            results = data.get("results", [])
            return RunEndedMessage(
                outcome=str(data.get("outcome", "")),
                results=tuple(
                    result for result in results if isinstance(result, dict)
                )
                if isinstance(results, list)
                else (),
            )
        if message_type == "pong":
            return PongMessage(
                seq=int(data.get("seq", 0)),
                ts=float(data.get("ts", 0.0)),
            )
        if message_type == "error":
            return ErrorMessage(
                code=str(data.get("code", "")),
                msg=str(data.get("msg", "")),
                fatal=bool(data.get("fatal", False)),
                seq=_opt_int(data.get("seq")),
            )
        if message_type == "bye":
            return ByeMessage()
    except (TypeError, ValueError):
        return UnknownMessage(type=message_type, data=data)
    return UnknownMessage(type=message_type, data=data)
