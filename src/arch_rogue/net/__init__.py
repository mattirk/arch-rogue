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

"""Arch Rogue multiplayer client package (4.6).

Facade preserving ``from arch_rogue.net import MultiplayerClient`` alongside
the typed message dataclasses, the Game-side :class:`NetMixin`, and the
canonical protocol re-export in :mod:`arch_rogue.net.protocol`.
"""

from .client import (
    ClientEvent,
    ConnectionClosed,
    ConnectionFailed,
    ConnectionLost,
    ConnectionUp,
    InboundMessage,
    MultiplayerClient,
    default_tls_context,
)
from .messages import (
    ByeMessage,
    ErrorMessage,
    FloorMessage,
    IntentMessage,
    NetMessage,
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
    message_from_dict,
)
from .mixin import MpSession, NetMixin

__all__ = [
    "ClientEvent",
    "ConnectionClosed",
    "ConnectionFailed",
    "ConnectionLost",
    "ConnectionUp",
    "InboundMessage",
    "MultiplayerClient",
    "default_tls_context",
    "ByeMessage",
    "ErrorMessage",
    "FloorMessage",
    "IntentMessage",
    "NetMessage",
    "PartnerDisconnected",
    "PartnerJoined",
    "PartnerLeft",
    "PartnerRejoined",
    "PongMessage",
    "ReadyAck",
    "RunEndedMessage",
    "SnapshotMessage",
    "Start",
    "UnknownMessage",
    "Welcome",
    "message_from_dict",
    "MpSession",
    "NetMixin",
]
