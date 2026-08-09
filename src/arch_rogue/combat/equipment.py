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
"""Equipment stat queries: damage-type colors, weapon/bolt/nova damage types, equipment stat totals, proc/unique effect rolls, lifesteal ratio, thorns."""
# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

from ..models import (
    Color,
)

from .damage_types import damage_color


class _EquipmentCombatMixin:
    def damage_type_color(self, damage_type: str) -> Color:
        return damage_color(damage_type)

    def weapon_damage_type(self) -> str:
        weapon = self.player.equipment.get("weapon")
        if weapon and weapon.damage_type:
            return weapon.damage_type
        if self.player.class_name == "Arcanist":
            return "arcane"
        if self.player.class_name == "Acolyte":
            return "shadow"
        return "physical"

    def bolt_damage_type(self) -> str:
        weapon = self.player.equipment.get("weapon")
        if weapon and weapon.damage_type in (
            "fire",
            "frost",
            "poison",
            "arcane",
            "shadow",
        ):
            return weapon.damage_type
        return {
            "Warden": "holy",
            "Rogue": "poison" if self.player.has_upgrade("rogue_venom") else "physical",
            "Arcanist": "arcane",
            "Acolyte": "shadow",
            "Ranger": "physical",
        }.get(self.player.class_name, "arcane")

    def nova_damage_type(self) -> str:
        return "frost"

    def equipment_stat_total(self, stat: str) -> float:
        return sum(
            float(getattr(item, stat, 0.0))
            for item in self.player.equipment.values()
            if item is not None
        )

    def equipment_skill_bonus(self, text: str) -> bool:
        return any(
            item is not None and text in item.skill_bonus
            for item in self.player.equipment.values()
        )

    def equipped_proc_effect(self, effect: str) -> bool:
        normalized = effect.lower()
        return any(
            item is not None
            and (item.proc_effect == effect or normalized in item.affix_tags)
            for item in self.player.equipment.values()
        )

    def roll_equipped_proc(self, effect: str) -> bool:
        normalized = effect.lower()
        for item in self.player.equipment.values():
            if item is None:
                continue
            if item.proc_effect != effect and normalized not in item.affix_tags:
                continue
            chance = float(item.proc_chance)
            if chance <= 0.0 or chance >= 1.0 or self.rng.random() < chance:
                return True
        return False

    def equipped_unique_effect(self, effect: str) -> bool:
        return any(
            item is not None and item.unique_effect == effect
            for item in self.player.equipment.values()
        )

    def equipment_lifesteal_ratio(self) -> float:
        ratio = self.equipment_stat_total("lifesteal")
        if self.equipped_proc_effect("lifesteal") and ratio <= 0.0:
            ratio = 0.08
        if self.equipped_unique_effect("sanguine echo"):
            ratio += 0.06
        if self.player.has_upgrade("acolyte_blood_pact"):
            ratio += 0.03
        return max(0.0, min(0.24, ratio))

    def equipment_thorns_damage(self, damage_taken: int) -> int:
        thorns = int(self.equipment_stat_total("thorns"))
        if self.equipped_proc_effect("thorns") and thorns <= 0:
            thorns = 3
        if self.equipped_unique_effect("grave chorus"):
            thorns += 2
        if thorns <= 0:
            return 0
        return max(1, thorns + damage_taken // 8)
