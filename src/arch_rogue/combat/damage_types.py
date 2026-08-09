# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
#
# AI Provenance & Liability Notice:
# This repository contains code generated, assisted, or refactored by Artificial
# Intelligence models. Provided strictly "AS IS" under Apache-2.0 with no warranty
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

"""Damage-type data tables and resistance helpers.

Centralizes the damage-type *data* that was previously inlined across combat
submodules (the per-type color table, the status→damage-type map, and the
resistance clamp bounds) so adding a new damage type (poison, holy, …) is a
single edit here instead of touching scattered ``if`` chains and dict literals.

Combat submodules route through the helpers below:

- :func:`damage_color` — RGB color for a damage type (used by floaters/impacts).
- :func:`status_damage_type` — damage type a status effect is flavored as.
- :func:`clamp_resistance` — clamp a resistance fraction to the legal range.
"""

from __future__ import annotations

from ..models import Color

DAMAGE_TYPE_COLORS: dict[str, Color] = {
    "physical": (255, 210, 120),
    "fire": (255, 132, 74),
    "frost": (126, 206, 242),
    "poison": (126, 214, 92),
    "arcane": (160, 118, 245),
    "holy": (235, 205, 120),
    "shadow": (214, 92, 150),
}
DEFAULT_DAMAGE_COLOR: Color = (255, 210, 120)

# Status effect -> damage type used to color the status-application floater.
STATUS_DAMAGE_TYPE: dict[str, str] = {
    "poisoned": "poison",
    "chilled": "frost",
    "burning": "fire",
    "snared": "physical",
    "bound": "shadow",
    "stunned": "holy",
}
DEFAULT_STATUS_DAMAGE_TYPE = "holy"

# Resistance fractions are clamped to this closed range before mitigation.
RESISTANCE_FLOOR = -0.35
RESISTANCE_CEIL = 0.70

# --- Player per-damage-type resistance bonuses ---------------------------
# The typed-resist "if chains" that used to live inline in
# ``take_player_damage`` are table-driven here so a new damage type or a
# new resist affix/unique drops in as one entry instead of editing
# scattered conditionals. All-types bonuses (``oathwall aegis``, the
# ``aegis`` status, Warden Temporal Aegis) stay inline in the helper since
# they do not branch on damage type.
PLAYER_ARMOR_TYPED_RESIST_BONUS = 0.08
PLAYER_RESIST_AFFIXES: dict[str, dict[str, float]] = {
    "Grounded": {"arcane": 0.12},
    "Sealed": {"shadow": 0.10, "poison": 0.10},
}
PLAYER_RESIST_UNIQUES: dict[str, dict[str, float]] = {
    "glacial ward": {"frost": 0.15},
}


def damage_color(damage_type: str) -> Color:
    """RGB color for ``damage_type`` (falls back to the default physical color)."""
    return DAMAGE_TYPE_COLORS.get(damage_type, DEFAULT_DAMAGE_COLOR)


def status_damage_type(status: str) -> str:
    """Damage type a status effect is flavored as (default ``holy``)."""
    return STATUS_DAMAGE_TYPE.get(status, DEFAULT_STATUS_DAMAGE_TYPE)


def clamp_resistance(value: float) -> float:
    """Clamp a resistance fraction to the legal [floor, ceil] range."""
    return max(RESISTANCE_FLOOR, min(RESISTANCE_CEIL, value))