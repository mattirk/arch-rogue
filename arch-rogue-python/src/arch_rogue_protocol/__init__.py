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

"""Canonical Arch Rogue multiplayer wire protocol (4.6).

This package is the single shared codec/message schema consumed by both the
game client (via the ``arch_rogue.net.protocol`` facade) and the standalone
``server/`` component (via a local path dependency). It is stdlib-only and
must never import Pygame or anything from ``arch_rogue``.
"""

from .wire import *  # noqa: F401,F403
from .wire import __all__ as _wire_all

__all__ = list(_wire_all)
