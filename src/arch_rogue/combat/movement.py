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
"""Actor movement and collision: move_actor, enemy locomotion, animation phase advance, hit radii, contact distance, melee stop distance, actor contact resolution."""
# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

import math
from itertools import chain
from ..constants import (
    PLAYER_HIT_RADIUS,
    WALK_ANIM_RUNTIME_SCALE_FLOOR,
    WALK_ANIMATION_RATE,
)
from ..models import (
    Enemy,
    Player,
)

from ._utils import (
    BOSS_FOOTPRINT_MOVE_RADIUS,
    PLAYER_MOVE_SPEED,
    WALK_ANIM_SPEED_CEIL,
    actor_hit_radius,
    anim_speed,
    enemy_hit_radius,
)


class _MovementCombatMixin:
    def move_actor(self, actor: Player | Enemy, dx: float, dy: float) -> float:
        old_x, old_y = actor.x, actor.y
        # Big bosses (2x2 footprint) need a wider collision probe so they don't
        # clip into walls; regular actors keep the tight default radius.
        if isinstance(actor, Enemy) and actor.size >= 2:
            radius = BOSS_FOOTPRINT_MOVE_RADIUS
        else:
            radius = 0.27
        new_x = actor.x + dx
        if not self.dungeon.blocked_for_radius(new_x, actor.y, radius):
            actor.x = new_x
        new_y = actor.y + dy
        if not self.dungeon.blocked_for_radius(actor.x, new_y, radius):
            actor.y = new_y
        self.resolve_actor_contacts(actor)

        actual_dx = actor.x - old_x
        actual_dy = actor.y - old_y
        distance = math.hypot(actual_dx, actual_dy)
        if distance > 0.0:
            actor.moving = True
            target_x = actual_dx / distance
            target_y = actual_dy / distance
            # Frame-rate-independent exponential smoothing. The old fixed
            # blend=0.38 per frame made facing/lean ease twice as fast at
            # 120fps as at 30fps; normalizing to dt keeps the feel stable
            # across frame rates. k~=4.77 reproduces 0.38/frame at 60fps.
            dt = getattr(self, "_last_dt", 1.0 / 60.0)
            blend = 1.0 - pow(2.718281828459045, -4.77 * dt)
            blend = 0.999 if blend > 0.999 else blend
            smoothed_x = actor.move_x * (1.0 - blend) + target_x * blend
            smoothed_y = actor.move_y * (1.0 - blend) + target_y * blend
            smoothed_length = math.hypot(smoothed_x, smoothed_y)
            if smoothed_length > 0.001:
                actor.move_x = smoothed_x / smoothed_length
                actor.move_y = smoothed_y / smoothed_length
            else:
                actor.move_x = target_x
                actor.move_y = target_y
            # anim_time is advanced in update() via advance_animation_phases()
            # using a steady dt-based rate so the walk cycle stays smooth even
            # when per-frame movement distance jitters from frame-rate variance.
        return distance

    def _move_enemy_locomotion(
        self,
        enemy: Enemy,
        dx: float,
        dy: float,
        dt: float,
        planned_scale: float,
    ) -> None:
        moved = self.move_actor(enemy, dx, dy)
        if moved <= 0.0 or dt <= 0.0 or enemy.speed <= 0.0:
            return
        actual_scale = moved / (enemy.speed * dt)
        if actual_scale < planned_scale - 1e-9:
            enemy.locomotion_anim_scale = min(
                enemy.locomotion_anim_scale,
                max(WALK_ANIM_RUNTIME_SCALE_FLOOR, actual_scale),
            )

    def player_walk_cadence(self) -> float:
        """Base walk-cycle cadence (tiles/s) for the player.

        Single seam for the player animation rate: ``advance_animation_phases``
        consumes it, so a future haste/discipline that should change the
        visual cadence overrides this one getter instead of each attack/
        animation call site. Returns ``PLAYER_MOVE_SPEED`` unchanged so
        footsteps stay in sync with movement (movement speed is fixed and
        decoupled from the ``player.speed`` stat; scaling cadence by the
        attack_speed stat here would desync stride from ground speed).
        """
        return PLAYER_MOVE_SPEED

    def advance_animation_phases(self, dt: float) -> None:
        # Base cadence remains clamped by actor type, then the runtime movement
        # multiplier follows analog input, status effects, and Time Skip. This
        # keeps authored footsteps synchronized when simulation speed changes
        # without making naturally slow enemy archetypes freeze between frames.
        if self.player.moving:
            speed = min(
                WALK_ANIM_SPEED_CEIL,
                anim_speed(self.player_walk_cadence())
                * max(
                    WALK_ANIM_RUNTIME_SCALE_FLOOR,
                    self.player.locomotion_anim_scale,
                ),
            )
            self.player.anim_time += dt * WALK_ANIMATION_RATE * speed
        for enemy in self.enemies:
            if enemy.moving:
                speed = min(
                    WALK_ANIM_SPEED_CEIL,
                    anim_speed(enemy.speed)
                    * max(
                        WALK_ANIM_RUNTIME_SCALE_FLOOR,
                        enemy.locomotion_anim_scale,
                    ),
                )
                enemy.anim_time += dt * WALK_ANIMATION_RATE * speed

    def actor_hit_radius(self, actor: Player | Enemy) -> float:
        return actor_hit_radius(actor)

    def enemy_hit_radius(self, enemy: Enemy) -> float:
        return enemy_hit_radius(enemy)

    def contact_distance(self, enemy: Enemy) -> float:
        return PLAYER_HIT_RADIUS + self.enemy_hit_radius(enemy)

    def _enemy_melee_stop_distance(self, enemy: Enemy) -> float:
        """Distance a melee enemy should close to before halting its approach.

        Stopping a small cushion inside ``attack_range`` prevents low-FPS/mobile
        frames and small player micro-kiting from leaving the enemy oscillating
        just outside melee reach. The result is clamped to [contact + margin,
        attack_range] so extremely short attack ranges (e.g. test dummies) do
        not fall inside collision resolution.
        """
        contact = self.contact_distance(enemy)
        return min(
            enemy.attack_range,
            max(contact + 0.02, enemy.attack_range - 0.12),
        )

    def resolve_actor_contacts(self, actor: Player | Enemy) -> None:
        actor_is_player = isinstance(actor, Player)
        actor_radius = (
            PLAYER_HIT_RADIUS if actor_is_player else self.enemy_hit_radius(actor)
        )
        # Preserve the original deterministic resolution order without allocating
        # a fresh all-actor list for every mover. Most pairs do not overlap, so a
        # squared-distance rejection also avoids their comparatively costly sqrt.
        if actor_is_player:
            others = chain(self.enemies, self.shopkeepers)
        else:
            others = chain((self.player,), self.enemies, self.shopkeepers)

        for other in others:
            if other is actor:
                continue
            dx = actor.x - other.x
            dy = actor.y - other.y
            distance_squared = dx * dx + dy * dy
            if isinstance(other, Player):
                other_radius = PLAYER_HIT_RADIUS
            elif isinstance(other, Enemy):
                other_radius = self.enemy_hit_radius(other)
            else:
                other_radius = 0.34
            min_distance = actor_radius + other_radius
            if distance_squared >= min_distance * min_distance:
                continue

            if distance_squared > 0.000001:
                distance = math.sqrt(distance_squared)
                nx, ny = dx / distance, dy / distance
            else:
                nx, ny = -actor.facing_x, -actor.facing_y
                if math.hypot(nx, ny) <= 0.001:
                    nx, ny = 1.0, 0.0

            target_x = other.x + nx * min_distance
            target_y = other.y + ny * min_distance
            if not self.dungeon.blocked_for_radius(target_x, actor.y):
                actor.x = target_x
            if not self.dungeon.blocked_for_radius(actor.x, target_y):
                actor.y = target_y
