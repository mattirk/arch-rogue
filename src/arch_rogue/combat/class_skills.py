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
"""Class-skill registry: typed per-archetype entries driving hotkey-3 dispatch.

Replaces the previous triple-dict (``_CLASS_SKILL_KINDS`` / ``_CASTS`` /
``_BONUS_TERMS``) plus the inline color dict with a single :class:`ClassSkill`
table. Adding a new archetype's class skill is now one registry entry instead of
editing three parallel dicts. Cast implementations stay in ``attacks.py`` /
``ambush_bell.py`` / ``familiars.py`` and are referenced here by method name.
"""
# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

from dataclasses import dataclass

from ..models import Color


@dataclass(frozen=True, slots=True)
class ClassSkill:
    """One archetype's class-skill (hotkey 3) dispatch record.

    ``cast_method`` is the name of the ``player_cast_*`` method on
    :class:`arch_rogue.combat.CombatMixin` that implements the skill; the
    registry only references it by name (the mixin isn't fully composed at
    module-load time, so callables can't be stored here).
    """

    archetype: str
    kind: str
    cast_method: str
    bonus_term: str
    color: Color


# Fallback for unknown archetypes; matches the pre-registry defaults
# (kind "nova", cast player_cast_nova, bonus "Nova", Arcanist blue).
_DEFAULT_CLASS_SKILL = ClassSkill(
    archetype="",
    kind="nova",
    cast_method="player_cast_nova",
    bonus_term="Nova",
    color=(120, 210, 255),
)

CLASS_SKILLS: dict[str, ClassSkill] = {
    "Warden": ClassSkill(
        "Warden", "time_skip", "player_cast_time_skip", "Time Skip", (235, 205, 120)
    ),
    "Rogue": ClassSkill(
        "Rogue", "ambush_bell", "player_cast_ambush_bell", "Ambush Bell", (170, 230, 150)
    ),
    "Arcanist": ClassSkill(
        "Arcanist", "nova", "player_cast_nova", "Nova", (120, 210, 255)
    ),
    "Acolyte": ClassSkill(
        "Acolyte", "spirit_call", "player_cast_spirit_call", "Spirit Call", (220, 95, 140)
    ),
    "Ranger": ClassSkill(
        "Ranger", "spirit_beast", "player_cast_spirit_beast", "Spirit Beast", (150, 215, 105)
    ),
}


class _ClassSkillsCombatMixin:
    def _class_skill(self) -> ClassSkill:
        """The class-skill record for the current player's archetype."""
        return CLASS_SKILLS.get(self.player.class_name, _DEFAULT_CLASS_SKILL)

    def class_skill_kind(self) -> str:
        """The archetype-specific class skill bound to hotkey 3."""
        return self._class_skill().kind

    def player_cast_class_skill(self) -> None:
        """Dispatch the archetype-specific class skill."""
        getattr(self, self._class_skill().cast_method)()

    def equipment_class_skill_bonus(self, text: str = "") -> bool:
        """Whether equipped gear boosts this archetype's canonical class skill."""
        canonical = self._class_skill().bonus_term
        if text:
            return canonical in text and self.equipment_skill_bonus(text)
        return self.equipment_skill_bonus(canonical)

    def skill_color(self) -> Color:
        """Per-archetype accent color used by the HUD, floaters, and menus."""
        return self._class_skill().color