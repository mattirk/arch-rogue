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

"""Configuration for the standalone Arch Rogue multiplayer server."""

from __future__ import annotations

import os
from dataclasses import dataclass

from .protocol import (
    MP_HELLO_TIMEOUT_SECONDS,
    MP_RECONNECT_GRACE_SECONDS,
    MP_ROOM_IDLE_TIMEOUT_SECONDS,
    MP_RUN_ID_LENGTH,
    MP_RUN_ID_MAX_LENGTH,
)

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 43666


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


@dataclass
class ServerConfig:
    """Tunable server behavior.

    ``run_id_length`` defaults to the shared 4-character room-locator length.
    A four-character Base32-like code carries only ~20 bits of entropy, so it
    is a locator, not authentication — Internet-exposed deployments should
    raise it (8 or 12) and rate-limit connection attempts upstream.
    """

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    run_id_length: int = MP_RUN_ID_LENGTH
    hello_timeout: float = MP_HELLO_TIMEOUT_SECONDS
    reconnect_grace: float = MP_RECONNECT_GRACE_SECONDS
    idle_timeout: float = MP_ROOM_IDLE_TIMEOUT_SECONDS
    max_rooms: int = 128
    log_level: str = "INFO"

    def __post_init__(self) -> None:
        self.port = int(self.port)
        if not 0 <= self.port <= 65535:
            raise ValueError(f"port {self.port} is out of range 0..65535")
        self.run_id_length = max(
            1, min(MP_RUN_ID_MAX_LENGTH, int(self.run_id_length))
        )
        self.hello_timeout = max(0.5, float(self.hello_timeout))
        self.reconnect_grace = max(0.0, float(self.reconnect_grace))
        self.idle_timeout = max(5.0, float(self.idle_timeout))
        self.max_rooms = max(1, int(self.max_rooms))

    @classmethod
    def from_env(cls) -> "ServerConfig":
        return cls(
            host=os.environ.get("ARCH_ROGUE_MP_HOST", DEFAULT_HOST),
            port=_env_int("ARCH_ROGUE_MP_PORT", DEFAULT_PORT),
            run_id_length=_env_int(
                "ARCH_ROGUE_MP_RUN_ID_LENGTH", MP_RUN_ID_LENGTH
            ),
            hello_timeout=_env_float(
                "ARCH_ROGUE_MP_HELLO_TIMEOUT", MP_HELLO_TIMEOUT_SECONDS
            ),
            reconnect_grace=_env_float(
                "ARCH_ROGUE_MP_RECONNECT_GRACE", MP_RECONNECT_GRACE_SECONDS
            ),
            idle_timeout=_env_float(
                "ARCH_ROGUE_MP_IDLE_TIMEOUT", MP_ROOM_IDLE_TIMEOUT_SECONDS
            ),
            max_rooms=_env_int("ARCH_ROGUE_MP_MAX_ROOMS", 128),
            log_level=os.environ.get("ARCH_ROGUE_MP_LOG_LEVEL", "INFO"),
        )
