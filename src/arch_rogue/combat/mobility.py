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
"""Player dash and melee-arc targeting helpers: dash, enemies in melee arc, first enemy near a point."""
# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

import math
from ..constants import (
    ENEMY_HIT_RADIUS,
    PLAYER_MELEE_ARC_DOT,
    PLAYER_MELEE_RANGE,
)
from ..models import (
    Enemy,
    FloatingText,
)


class _MobilityCombatMixin:
    def player_dash(self) -> None:
        if self.mp_is_joiner():
            self.mp_queue_action("dash")
            return
        stamina_cost = self.dash_stamina_cost()
        if self.player.dash_timer > 0 or self.player.stamina < stamina_cost:
            return
        self.player.dash_timer = self.dash_cooldown()
        self.player.stamina -= stamina_cost
        start_x, start_y = self.player.x, self.player.y
        self.set_player_action_visual("dash", 0.22)
        self.add_impact(
            start_x, start_y, self.skill_color(), ttl=0.24, radius=0.34, kind="dash"
        )
        steps = 11 if self.player.class_name == "Ranger" else 8
        if self.player.has_upgrade("rogue_smoke"):
            steps += 2
        if self.equipment_skill_bonus("Dash"):
            steps += 1
        for _ in range(steps):
            self.move_actor(
                self.player,
                self.player.facing_x * 0.20,
                self.player.facing_y * 0.20,
            )
        self.add_impact(
            self.player.x,
            self.player.y,
            self.skill_color(),
            ttl=0.26,
            radius=0.42,
            kind="dash",
        )
        if self.player.class_name == "Rogue" and self.player.has_upgrade("rogue_smoke"):
            self.set_player_status("smoke", 0.9)
        if self.equipped_unique_effect("vanish on dash"):
            self.set_player_status("smoke", 0.8)
        if self.player.class_name == "Warden" and (
            self.player.has_upgrade("warden_aegis")
            or self.equipment_skill_bonus("Dash guard")
        ):
            self.set_player_status("aegis", 0.85)
        if self.player.class_name == "Ranger" and self.player.has_upgrade(
            "ranger_beastmark"
        ):
            self.player.stamina = min(self.player.max_stamina, self.player.stamina + 8)
            self.player.bolt_timer = min(self.player.bolt_timer, 0.12)
        self.floaters.append(
            FloatingText(
                self.skill_names()[3],
                self.player.x,
                self.player.y - 0.4,
                self.skill_color(),
                ttl=0.45,
            )
        )

    def enemies_in_melee_arc(self, reach_bonus: float = 0.0) -> list[Enemy]:
        candidates: list[tuple[float, Enemy]] = []
        for enemy in self.enemies:
            dx = enemy.x - self.player.x
            dy = enemy.y - self.player.y
            distance = math.hypot(dx, dy)
            # Oversized bosses have a much larger body; let melee reach extend
            # past the default arc range by the enemy's extra radius so a 4-tile
            # boss is hittable from its silhouette edge, not just its center.
            extra_reach = max(0.0, self.enemy_hit_radius(enemy) - ENEMY_HIT_RADIUS)
            if (
                distance > PLAYER_MELEE_RANGE + reach_bonus + extra_reach
                or distance < 0.001
                or not self.dungeon.line_of_sight(
                    self.player.x, self.player.y, enemy.x, enemy.y
                )
            ):
                continue
            dot = (dx / distance) * self.player.facing_x + (
                dy / distance
            ) * self.player.facing_y
            if dot > PLAYER_MELEE_ARC_DOT:
                candidates.append((distance, enemy))
        return [
            enemy for _distance, enemy in sorted(candidates, key=lambda entry: entry[0])
        ]

    def enemy_in_melee_arc(self) -> Enemy | None:
        enemies = self.enemies_in_melee_arc()
        return enemies[0] if enemies else None

    def first_enemy_near(self, x: float, y: float, radius: float) -> Enemy | None:
        for enemy in self.enemies:
            hit_radius = radius + self.enemy_hit_radius(enemy) - ENEMY_HIT_RADIUS
            dx = enemy.x - x
            dy = enemy.y - y
            if (
                dx * dx + dy * dy <= hit_radius * hit_radius
                and self.dungeon.line_of_sight(x, y, enemy.x, enemy.y)
            ):
                return enemy
        return None
