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
"""Resource cost and cooldown getters: melee/bolt stamina+mana+cooldowns, class-skill mana+cooldown, time-skip factor/duration, enemy time scale, dash cost+cooldown."""
# pyright: reportAttributeAccessIssue=false
from __future__ import annotations


class _CostsCombatMixin:
    def player_attack_speed(self) -> float:
        """Clamped attack-speed stat from equipment (range [-0.20, 0.35]).

        Single source of truth for melee haste: ``melee_cooldown`` consumes
        it and it is the seam future disciplines/affixes hook into to speed
        up attack visuals without touching every attack method.
        """
        return max(-0.20, min(0.35, self.equipment_stat_total("attack_speed")))

    def player_cast_speed(self) -> float:
        """Clamped cast-speed stat from equipment (range [-0.20, 0.35])."""
        return max(-0.20, min(0.35, self.equipment_stat_total("cast_speed")))

    def melee_stamina_cost(self) -> int:
        cost = 9 if self.player.class_name == "Rogue" else 12
        if self.player.has_upgrade("rogue_precision"):
            cost -= 2
        if self.equipment_skill_bonus("Melee"):
            cost -= 1
        if any(
            item is not None and item.cursed for item in self.player.equipment.values()
        ):
            cost += 1
        return max(5, cost)

    def melee_cooldown(self) -> float:
        cooldown = 0.30 if self.player.class_name == "Rogue" else 0.36
        if self.player.has_upgrade("warden_bulwark"):
            cooldown += 0.02
        if self.equipment_skill_bonus("Melee"):
            cooldown -= 0.03
        attack_speed = self.player_attack_speed()
        cooldown *= 1.0 - attack_speed
        return max(0.20, cooldown)

    def bolt_mana_cost(self) -> int:
        cost = 7 if self.player.class_name in ("Arcanist", "Ranger") else 10
        if self.player.has_upgrade("arcanist_focus"):
            cost -= 1
        if self.equipment_skill_bonus("Bolt"):
            cost -= 1
        if any(
            item is not None and item.cursed for item in self.player.equipment.values()
        ):
            cost += 1
        return max(4, cost)

    def bolt_cooldown(self) -> float:
        cooldown = 0.38 if self.player.class_name in ("Arcanist", "Ranger") else 0.48
        if self.equipment_skill_bonus("Bolt"):
            cooldown -= 0.04
        cast_speed = self.player_cast_speed()
        cooldown *= 1.0 - cast_speed
        return max(0.22, cooldown)

    def class_skill_mana_cost(self) -> int | float:
        """Mana cost for the archetype class skill bound to hotkey 3."""
        if self.player.class_name == "Ranger":
            # Summoning Spirit Beast always costs exactly half of the current
            # maximum mana. Commands issued while it is alive are free.
            return self.player.max_mana * 0.5
        cost = 14 if self.player.class_name in ("Arcanist", "Acolyte") else 18
        if self.player.has_upgrade("acolyte_veil"):
            cost -= 2
        # Warden Time path Degree 1 (Temporal Sigil) discounts the class-skill budget.
        if self.player.class_name == "Warden" and self.player.has_upgrade("warden_ward"):
            cost -= 1
        if self.equipment_class_skill_bonus():
            cost -= 1
        if any(
            item is not None and item.cursed for item in self.player.equipment.values()
        ):
            cost += 2
        return max(8, cost)

    def class_skill_cooldown(self) -> float:
        """Cooldown before an absent archetype class summon can be used again."""
        if self.player.class_name == "Ranger":
            # This gates replacement summons only; a living Spirit Beast can
            # still receive free return/attack commands while the timer runs.
            return 60.0
        cooldown = 2.65 if self.player.class_name == "Arcanist" else 3.2
        # Warden Time path Degree 1 (Temporal Sigil) cools the class skill faster.
        if self.player.class_name == "Warden" and self.player.has_upgrade("warden_ward"):
            cooldown -= 0.3
        if self.equipment_class_skill_bonus():
            cooldown -= 0.18
        cast_speed = self.player_cast_speed()
        cooldown *= 1.0 - cast_speed * 0.75
        return max(1.85, cooldown)

    def time_skip_factor(self) -> float:
        """Enemy simulation speed while Time Skip is active (lower = slower)."""
        # Milestone 3.18.1 — Time path Degree 3 (Stutter Step) deepens the slow.
        if self.player.has_upgrade("warden_stone_aegis"):
            return 0.3
        return 0.4

    def time_skip_duration(self) -> float:
        """How long Time Skip slows enemies, in seconds."""
        duration = 3.0
        # Time path scaling (Degree 1 Temporal Sigil, Degree 2 Time Skip).
        if self.player.has_upgrade("warden_ward"):
            duration += 0.5
        if self.player.has_upgrade("warden_bulwark_wave"):
            duration += 1.0
        if self.equipment_class_skill_bonus("Time Skip duration"):
            duration += 0.5
        return duration

    def enemy_time_scale(
        self, dt: float = 0.0, *, remaining: float | None = None
    ) -> float:
        """Average enemy simulation multiplier across this update interval."""
        ttl = self.player.time_skip_timer if remaining is None else remaining
        if ttl <= 0.0:
            return 1.0
        factor = self.time_skip_factor()
        if dt > 0.0 and ttl < dt:
            active_fraction = max(0.0, min(1.0, ttl / dt))
            return 1.0 - (1.0 - factor) * active_fraction
        return factor

    def dash_stamina_cost(self) -> int:
        cost = 12 if self.player.class_name in ("Rogue", "Ranger") else 18
        if self.player.has_upgrade("rogue_smoke"):
            cost -= 2
        if self.equipment_skill_bonus("Dash"):
            cost -= 2
        return max(8, cost)

    def dash_cooldown(self) -> float:
        cooldown = 0.62 if self.player.class_name == "Ranger" else 0.85
        if self.equipment_skill_bonus("Dash tempo"):
            cooldown -= 0.08
        return max(0.48, cooldown)
