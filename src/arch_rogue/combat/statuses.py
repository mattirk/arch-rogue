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
"""Player and enemy status effects: application, slow-factor averaging, enemy speed/locomotion scales, damage mitigation, per-frame status updates."""
# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

from ..models import (
    Enemy,
    FloatingText,
)

from ._utils import average_slow_factors
from .damage_types import clamp_resistance, status_damage_type


class _StatusesCombatMixin:
    def player_status(self, name: str) -> float:
        return float(self.player.status_effects.get(name, 0.0))

    def set_player_status(
        self, name: str, duration: float, player=None
    ) -> None:
        target = player if player is not None else self.player
        target.status_effects[name] = max(
            target.status_effects.get(name, 0.0), duration
        )

    def apply_enemy_status(self, enemy: Enemy, status: str, duration: float) -> None:
        if duration <= 0:
            return
        if status == "poisoned" and enemy.resistances.get("poison", 0.0) >= 0.55:
            duration *= 0.55
        enemy.statuses[status] = max(enemy.statuses.get(status, 0.0), duration)
        self.floaters.append(
            FloatingText(
                status.title(),
                enemy.x,
                enemy.y - 0.45,
                self.damage_type_color(status_damage_type(status)),
                ttl=0.65,
            )
        )

    def enemy_speed_multiplier(self, enemy: Enemy, dt: float = 0.0) -> float:
        movement_scale, _animation_scale = average_slow_factors(
            dt,
            (
                (enemy.statuses.get("chilled", 0.0), 0.58),
                (enemy.statuses.get("snared", 0.0), 0.45),
                (enemy.statuses.get("bound", 0.0), 0.62),
            ),
        )
        return movement_scale

    def enemy_locomotion_scales(
        self,
        enemy: Enemy,
        dt: float,
        *,
        time_skip_remaining: float | None = None,
    ) -> tuple[float, float]:
        time_ttl = (
            self.player.time_skip_timer
            if time_skip_remaining is None
            else time_skip_remaining
        )
        return average_slow_factors(
            dt,
            (
                (time_ttl, self.time_skip_factor()),
                (enemy.statuses.get("chilled", 0.0), 0.58),
                (enemy.statuses.get("snared", 0.0), 0.45),
                (enemy.statuses.get("bound", 0.0), 0.62),
            ),
        )

    def enemy_locomotion_scale(
        self,
        enemy: Enemy,
        dt: float,
        *,
        time_skip_remaining: float | None = None,
    ) -> float:
        movement_scale, _animation_scale = self.enemy_locomotion_scales(
            enemy,
            dt,
            time_skip_remaining=time_skip_remaining,
        )
        return movement_scale

    def mitigate_enemy_damage(self, enemy: Enemy, amount: int, damage_type: str) -> int:
        resistance = clamp_resistance(enemy.resistances.get(damage_type, 0.0))
        adjusted = int(round(amount * (1.0 - resistance)))
        if enemy.statuses.get("chilled", 0.0) > 0 and damage_type == "arcane":
            adjusted = int(round(adjusted * 1.18))
        if enemy.statuses.get("snared", 0.0) > 0 and self.player.has_upgrade(
            "ranger_beastmark"
        ):
            adjusted = int(round(adjusted * 1.22))
        return max(1, adjusted)

    def update_enemy_statuses(
        self, dt: float, *, time_skip_remaining: float | None = None
    ) -> None:
        for enemy in list(self.enemies):
            # Sample combined movement slows before decrementing status TTLs.
            # update_enemies() consumes this once for exact partial intervals.
            (
                enemy.pending_locomotion_scale,
                enemy.pending_locomotion_anim_scale,
            ) = self.enemy_locomotion_scales(
                enemy,
                dt,
                time_skip_remaining=time_skip_remaining,
            )
            if not enemy.statuses:
                continue
            if enemy.statuses.get("poisoned", 0.0) > 0:
                tick = enemy.statuses.get("_poison_tick", 1.0) - dt
                if tick <= 0:
                    enemy.hp -= max(1, int(2 + self.player.level * 0.35))
                    tick += 1.0
                    if enemy.hp <= 0:
                        self.kill_enemy(enemy)
                        continue
                enemy.statuses["_poison_tick"] = tick
            expired: list[str] = []
            for status, ttl in list(enemy.statuses.items()):
                if status.startswith("_"):
                    continue
                ttl -= dt
                if ttl <= 0:
                    expired.append(status)
                else:
                    enemy.statuses[status] = ttl
            if "poisoned" in expired:
                enemy.statuses.pop("_poison_tick", None)
            for status in expired:
                enemy.statuses.pop(status, None)
