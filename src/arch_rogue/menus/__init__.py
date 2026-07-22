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

from __future__ import annotations

from .base import MenuBaseMixin, MenuRow
from .character import MenuCharacterMixin
from .controls import MenuControlsMixin
from .inventory import MenuInventoryMixin
from .mp import MenuMultiplayerMixin
from .options import MenuOptionsMixin
from .state_overlay import MenuStateOverlayMixin
from .title import MenuTitleMixin


class MenuRenderer(
    MenuBaseMixin,
    MenuTitleMixin,
    MenuOptionsMixin,
    MenuControlsMixin,
    MenuCharacterMixin,
    MenuInventoryMixin,
    MenuMultiplayerMixin,
    MenuStateOverlayMixin,
):
    """Centralized menu and overlay renderer.

    The renderer uses a small set of primitives—centered panels, fixed-width key
    badges, wrapped body text, and clipped single-line labels—so every menu uses
    the same alignment rules instead of hand-placed text offsets.
    """


__all__ = ["MenuRenderer", "MenuRow"]
