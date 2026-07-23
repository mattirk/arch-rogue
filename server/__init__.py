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

"""Arch Rogue standalone multiplayer relay server (4.6).

This package is intentionally **not** part of the installed ``arch_rogue``
game package: it ships its own ``pyproject.toml`` and runs independently
(``python -m server.server``). It is an ephemeral, in-memory relay — rooms,
slots, selected archetypes, reconnect reservations, activity times, and
opaque relayed payloads live in process memory only; nothing is persisted.

The wire codec is the canonical shared ``arch_rogue_protocol`` package (a
local path dependency — never vendored) re-exported via :mod:`server.protocol`.
"""

__version__ = "4.7.7"
