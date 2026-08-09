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
"""Player aiming: controller aim-snap toward enemies, analog/keyboard/mouse aim resolution, and screen-to-world facing."""
# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

import math
import pygame
from ..models import (
    Enemy,
)


class _AimCombatMixin:
    CONTROLLER_AIM_SNAP_RANGE = 5.0
    CONTROLLER_AIM_SNAP_DOT = 0.86

    def controller_aim_snap_enabled(self) -> bool:
        input_manager = getattr(self, "input", None)
        has_controller = getattr(input_manager, "has_controller", None)
        if input_manager is None or has_controller is None:
            return False
        return (
            bool(getattr(self, "controller_enabled", False))
            and bool(has_controller())
            and getattr(self, "aim_input_mode", "mouse") == "controller"
        )

    def snap_controller_aim_to_enemy(self) -> Enemy | None:
        """Snap controller aim toward a visible enemy near the current aim line."""
        if not self.controller_aim_snap_enabled():
            return None
        facing_x = self.player.facing_x
        facing_y = self.player.facing_y
        facing_len = math.hypot(facing_x, facing_y)
        if facing_len <= 0.001:
            return None
        facing_x /= facing_len
        facing_y /= facing_len

        best_enemy: Enemy | None = None
        best_dx = 0.0
        best_dy = 0.0
        best_distance = 0.0
        best_score = float("inf")
        for enemy in self.enemies:
            if not enemy.alive:
                continue
            dx = enemy.x - self.player.x
            dy = enemy.y - self.player.y
            distance = math.hypot(dx, dy)
            if distance <= 0.001:
                continue
            hit_radius = self.enemy_hit_radius(enemy)
            if distance > self.CONTROLLER_AIM_SNAP_RANGE + hit_radius:
                continue
            if not self.can_see_world_position(enemy.x, enemy.y, hit_radius):
                continue
            if not self.has_line_of_sight_to_player(enemy.x, enemy.y):
                continue
            nx = dx / distance
            ny = dy / distance
            dot = nx * facing_x + ny * facing_y
            if dot < self.CONTROLLER_AIM_SNAP_DOT:
                continue
            # Prefer targets closest to the current aim line, with distance as a
            # light tiebreaker so a nearby foe can beat a barely better far angle.
            score = (1.0 - dot) * 2.0 + distance * 0.04
            if score < best_score:
                best_score = score
                best_enemy = enemy
                best_dx = dx
                best_dy = dy
                best_distance = distance

        if best_enemy is None or best_distance <= 0.001:
            return None
        self.player.facing_x = best_dx / best_distance
        self.player.facing_y = best_dy / best_distance
        return best_enemy

    def update_player_aim(self) -> None:
        # Right stick (controller) takes priority for analog aiming, then
        # arrow keys, then the mouse cursor as a fallback.
        rx, ry = self.input.right_vec()
        if rx or ry:
            self.aim_input_mode = "controller"
            length = math.hypot(rx, ry)
            if length > 0.0:
                self.player.facing_x = rx / length
                self.player.facing_y = ry / length
            self.snap_controller_aim_to_enemy()
            return
        keys = pygame.key.get_pressed()
        dx = float(keys[pygame.K_RIGHT]) - float(keys[pygame.K_LEFT])
        dy = float(keys[pygame.K_DOWN]) - float(keys[pygame.K_UP])
        if dx or dy:
            self.aim_input_mode = "keyboard"
            length = math.hypot(dx, dy)
            self.player.facing_x = dx / length
            self.player.facing_y = dy / length
        elif getattr(self, "aim_input_mode", "mouse") == "touch":
            # Only a live world touch may steer facing; the self-healing
            # accessor drops a touch whose release event was lost so dash and
            # skills follow joystick movement again.
            point = self.active_mobile_world_touch()
            if point is not None:
                self.face_player_toward_screen_point(*point)
        elif getattr(self, "aim_input_mode", "mouse") != "controller":
            self.face_player_toward_screen_point(*pygame.mouse.get_pos())
        else:
            self.snap_controller_aim_to_enemy()

    def face_player_toward_screen_point(self, sx: int, sy: int) -> tuple[float, float]:
        if getattr(self, "mobile_mode", False) and not self.screen_point_in_world_viewport(
            (sx, sy)
        ):
            return 0.0, 0.0
        target_x, target_y = self.screen_to_world(sx, sy)
        dx = target_x - self.player.x
        dy = target_y - self.player.y
        distance = math.hypot(dx, dy)
        if distance > 0.05:
            self.player.facing_x = dx / distance
            self.player.facing_y = dy / distance
        return dx, dy
