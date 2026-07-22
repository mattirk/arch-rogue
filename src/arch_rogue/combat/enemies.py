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
"""Enemy AI per-frame update, melee swing, and spell cast."""
# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

import math
from ..models import (
    Enemy,
    FloatingText,
    Projectile,
)

from ._utils import (
    ENEMY_BOSS_WINDUP,
    ENEMY_CAST_WINDUP,
    ENEMY_MELEE_WINDUP,
    KNOCKBACK_DECAY_RATE,
)


class _EnemiesCombatMixin:
    def _apply_enemy_knockback(self, enemy: Enemy, dt: float) -> None:
        """Integrate and exponentially decay enemy knockback velocity.

        Collision-aware (via move_actor) and framerate-independent. Runs for
        every enemy each frame regardless of aggro/stun state so shoves from
        any hit land even on enemies that would otherwise skip the movement
        branches. Total displacement ~= KNOCKBACK_SPEED / KNOCKBACK_DECAY_RATE.
        """
        kvx = enemy.knockback_vx
        kvy = enemy.knockback_vy
        if kvx == 0.0 and kvy == 0.0:
            return
        if dt <= 0.0:
            return
        moved = self.move_actor(enemy, kvx * dt, kvy * dt)
        if moved > 0.0:
            enemy.moving = True
        decay = math.exp(-KNOCKBACK_DECAY_RATE * dt)
        enemy.knockback_vx = kvx * decay
        enemy.knockback_vy = kvy * decay
        if abs(enemy.knockback_vx) < 0.01 and abs(enemy.knockback_vy) < 0.01:
            enemy.knockback_vx = 0.0
            enemy.knockback_vy = 0.0

    def _enemy_windup_duration(self, enemy: Enemy) -> float:
        """Telegraph windup (seconds) for an enemy's next attack."""
        if enemy.kind == "boss" or enemy.is_boss_encounter:
            return ENEMY_BOSS_WINDUP
        if enemy.kind == "ranged":
            return ENEMY_CAST_WINDUP
        return ENEMY_MELEE_WINDUP

    def _commit_enemy_attack(self, enemy: Enemy, attack: str, nx: float = 0.0, ny: float = 0.0) -> None:
        """Commit to an attack: start the windup telegraph instead of firing now.

        ``attack`` is "melee" or "cast"; ``nx``/``ny`` snapshot the cast aim so
        the projectile (fired on windup completion) travels along the committed
        direction and is dodgeable after launch. No-op if already winding up.
        """
        if enemy.windup_time > 0.0:
            return
        duration = self._enemy_windup_duration(enemy)
        enemy.windup_time = duration
        enemy.windup_duration = duration
        enemy.windup_attack = attack
        enemy.windup_nx = nx
        enemy.windup_ny = ny

    def _fire_committed_attack(self, enemy: Enemy) -> None:
        """Fire the attack a windup committed to.

        Locked: ``line_of_sight_confirmed=True`` so the committed hit lands
        even if the player moved during the short windup; the player counters
        with abilities (evade/block), not by walking out of a committed swing.
        """
        attack = enemy.windup_attack
        enemy.windup_attack = ""
        if attack == "cast":
            self.enemy_cast(
                enemy, enemy.windup_nx, enemy.windup_ny, line_of_sight_confirmed=True
            )
        elif attack:
            self.enemy_melee(enemy, line_of_sight_confirmed=True)

    def update_enemies(
        self,
        dt: float,
        *,
        time_scale: float | None = None,
        time_skip_remaining: float | None = None,
    ) -> None:
        # Milestone 3.18 — Time Skip slows the enemy simulation uniformly
        # (movement and attack cadence) without affecting the player.
        if time_scale is None:
            time_scale = self.enemy_time_scale(
                dt, remaining=time_skip_remaining
            )
        scaled_dt = dt * time_scale
        # 4.6 co-op: enemies target the nearest living player, breaking
        # equal-distance ties by stable player id. Single-player keeps the
        # zero-allocation fast path (the tuple below is the lone player).
        players = self.living_players() or self.active_players()
        single_target = players[0] if len(players) == 1 else None
        for enemy in self.enemies:
            enemy.moving = False
            enemy.locomotion_anim_scale = 0.0
            locomotion_scale = enemy.pending_locomotion_scale
            animation_scale = enemy.pending_locomotion_anim_scale
            if locomotion_scale is None or animation_scale is None:
                locomotion_scale, animation_scale = self.enemy_locomotion_scales(
                    enemy,
                    dt,
                    time_skip_remaining=time_skip_remaining,
                )
            enemy.pending_locomotion_scale = None
            enemy.pending_locomotion_anim_scale = None
            self._apply_enemy_knockback(enemy, scaled_dt)
            # Windup phase: a committed attack telegraphs, then fires. Takes
            # precedence over the aggro/stun skips below so the committed hit
            # resolves even if the player left aggro range mid-windup. Stun
            # interrupts a committed windup (a stunned enemy can't finish).
            if enemy.statuses.get("stunned", 0.0) > 0 and enemy.windup_time > 0.0:
                enemy.windup_time = 0.0
                enemy.windup_attack = ""
            if enemy.windup_time > 0.0:
                enemy.windup_time = max(0.0, enemy.windup_time - scaled_dt)
                if enemy.windup_time <= 0.0 and enemy.windup_attack:
                    self._fire_committed_attack(enemy)
                continue
            if enemy.telegraph == "lured":
                enemy.telegraph = ""
            enemy.attack_timer = max(0.0, enemy.attack_timer - scaled_dt)
            if single_target is not None:
                target_player = single_target
            else:
                target_player = min(
                    players,
                    key=lambda p: (
                        (p.x - enemy.x) ** 2 + (p.y - enemy.y) ** 2,
                        p.player_id,
                    ),
                )
            player_dx = target_player.x - enemy.x
            player_dy = target_player.y - enemy.y
            player_distance = math.hypot(player_dx, player_dy)
            lure = self.ambush_bell_lure_target(enemy)
            if player_distance > enemy.aggro_range and lure is None:
                continue
            if enemy.statuses.get("stunned", 0.0) > 0:
                enemy.telegraph = "stunned"
                continue

            target_x = lure.x if lure is not None else target_player.x
            target_y = lure.y if lure is not None else target_player.y
            dx = target_x - enemy.x
            dy = target_y - enemy.y
            distance = math.hypot(dx, dy)
            nx, ny = (dx / distance, dy / distance) if distance > 0.001 else (0.0, 0.0)
            player_nx, player_ny = (
                (player_dx / player_distance, player_dy / player_distance)
                if player_distance > 0.001
                else (0.0, 0.0)
            )
            move_speed = enemy.speed * locomotion_scale
            enemy.locomotion_anim_scale = animation_scale
            if distance > 0.001:
                enemy.facing_x = nx
                enemy.facing_y = ny

            # Enemies must actually see the player to attack; movement remains
            # intentionally ungated so pursuit around corners still works. Trace
            # LOS only when the pre-movement state could attack this frame. This
            # preserves the former attack position/ordering while avoiding a wall
            # walk for distant enemies and enemies whose cooldown is still active.
            attack_ready = enemy.attack_timer <= 0
            if lure is not None:
                attack_in_range = player_distance <= enemy.attack_range
            elif enemy.kind == "boss" or enemy.is_boss_encounter:
                attack_in_range = (
                    2.0 < distance <= 6.0 or distance <= enemy.attack_range
                )
            else:
                attack_in_range = distance <= enemy.attack_range
            has_los = (
                attack_ready
                and attack_in_range
                and self.dungeon.line_of_sight(
                    enemy.x, enemy.y, target_player.x, target_player.y
                )
            )

            if lure is not None:
                enemy.telegraph = "lured"
                if distance > 0.12:
                    step = min(move_speed * dt, distance - 0.12)
                    self._move_enemy_locomotion(
                        enemy, nx * step, ny * step, dt, locomotion_scale
                    )
                if (
                    player_distance <= enemy.attack_range
                    and attack_ready
                    and has_los
                ):
                    if enemy.kind == "ranged":
                        self._commit_enemy_attack(enemy, "cast", player_nx, player_ny)
                    else:
                        self._commit_enemy_attack(enemy, "melee")
                continue

            if enemy.kind == "boss" or enemy.is_boss_encounter:
                # 4-tile boss encounters (final tyrant + floor guardians) use the
                # same pressure pattern: close the gap, cast a bolt fan at mid
                # range, and crush with melee up close.
                stop_distance = self._enemy_melee_stop_distance(enemy)
                if distance > stop_distance:
                    step = min(move_speed * dt, distance - stop_distance)
                    self._move_enemy_locomotion(
                        enemy, nx * step, ny * step, dt, locomotion_scale
                    )
                if 2.0 < distance <= 6.0 and attack_ready and has_los:
                    self._commit_enemy_attack(enemy, "cast", nx, ny)
                elif distance <= enemy.attack_range and attack_ready and has_los:
                    self._commit_enemy_attack(enemy, "melee")
            elif enemy.kind == "ranged":
                if 3.5 < distance:
                    step = min(move_speed * dt, distance - 3.5)
                    self._move_enemy_locomotion(
                        enemy, nx * step, ny * step, dt, locomotion_scale
                    )
                elif distance < 2.5:
                    step = min(move_speed * dt, 2.5 - distance)
                    self._move_enemy_locomotion(
                        enemy, -nx * step, -ny * step, dt, locomotion_scale
                    )
                if (
                    distance <= enemy.attack_range
                    and attack_ready
                    and has_los
                ):
                    self._commit_enemy_attack(enemy, "cast", nx, ny)
            else:
                stop_distance = self._enemy_melee_stop_distance(enemy)
                if distance > stop_distance:
                    step = min(
                        move_speed * dt, distance - stop_distance
                    )
                    self._move_enemy_locomotion(
                        enemy, nx * step, ny * step, dt, locomotion_scale
                    )
                if distance <= enemy.attack_range and attack_ready and has_los:
                    self._commit_enemy_attack(enemy, "melee")

    def enemy_target_player(self, enemy: Enemy):
        """Nearest living player for this enemy (ties break by player id)."""

        players = self.living_players() or self.active_players()
        if len(players) == 1:
            return players[0]
        return min(
            players,
            key=lambda p: (
                (p.x - enemy.x) ** 2 + (p.y - enemy.y) ** 2,
                p.player_id,
            ),
        )

    def enemy_melee(
        self, enemy: Enemy, *, line_of_sight_confirmed: bool = False
    ) -> None:
        victim = self.enemy_target_player(enemy)
        if victim is None:
            return
        if not line_of_sight_confirmed:
            distance = math.hypot(enemy.x - victim.x, enemy.y - victim.y)
            if distance > enemy.attack_range or not self.dungeon.line_of_sight(
                enemy.x, enemy.y, victim.x, victim.y
            ):
                return
        enemy.attack_timer = enemy.attack_cooldown
        enemy.telegraph = "melee"
        raw = enemy.damage + self.rng.randrange(-2, 3)
        amount = self.take_player_damage(
            raw,
            source="melee",
            damage_type=enemy.damage_type,
            attacker=enemy,
            victim=victim,
        )
        if enemy.damage_type == "poison" and amount > 0:
            self.set_player_status("poisoned", 1.4, player=victim)
        elif enemy.damage_type == "frost" and amount > 0:
            self.set_player_status("chilled", 0.9, player=victim)
        self.floaters.append(
            FloatingText(
                f"-{amount}",
                victim.x,
                victim.y - 0.2,
                self.damage_type_color(enemy.damage_type),
            )
        )
        self.slashes.append(
            (
                (enemy.x + victim.x) * 0.5,
                (enemy.y + victim.y) * 0.5,
                0.14,
                enemy.facing_x,
                enemy.facing_y,
            )
        )
        self.add_impact(
            (enemy.x + victim.x) * 0.5,
            (enemy.y + victim.y) * 0.5,
            (255, 180, 130),
            ttl=0.26,
            radius=0.34,
            kind="slash",
        )

    def enemy_cast(
        self,
        enemy: Enemy,
        nx: float,
        ny: float,
        *,
        line_of_sight_confirmed: bool = False,
    ) -> None:
        if not line_of_sight_confirmed:
            victim = self.enemy_target_player(enemy)
            if victim is None:
                return
            distance = math.hypot(enemy.x - victim.x, enemy.y - victim.y)
            cast_range = (
                max(6.0, enemy.attack_range)
                if enemy.kind == "boss" or enemy.is_boss_encounter
                else enemy.attack_range
            )
            if distance > cast_range or not self.dungeon.line_of_sight(
                enemy.x, enemy.y, victim.x, victim.y
            ):
                return
        enemy.attack_timer = enemy.attack_cooldown
        enemy.telegraph = "cast"
        projectile_color = self.damage_type_color(enemy.damage_type)
        if enemy.elite_modifier:
            projectile_color = self.mix(projectile_color, (245, 100, 235), 0.35)
        if enemy.kind in ("boss", "miniboss"):
            projectile_color = self.theme.accent
        self.add_impact(
            enemy.x, enemy.y, projectile_color, ttl=0.28, radius=0.36, kind="cast"
        )
        # 4-tile bosses are serious threats: they fire a 3-bolt fan instead of a
        # single projectile so the player has to dodge laterally, not just step.
        spreads = (-0.28, 0.0, 0.28) if enemy.size >= 2 else (0.0,)
        # perpendicular vector for fanning the spread
        px, py = -ny, nx
        for spread in spreads:
            vx = nx * 6.0 + px * spread * 6.0
            vy = ny * 6.0 + py * spread * 6.0
            self.projectiles.append(
                Projectile(
                    enemy.x,
                    enemy.y,
                    vx,
                    vy,
                    enemy.damage,
                    "enemy",
                    projectile_color,
                    ttl=1.8,
                    damage_type=enemy.damage_type,
                    status_effect="chilled" if enemy.damage_type == "frost" else "",
                    status_duration=0.9,
                )
            )
