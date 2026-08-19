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
"""Rogue Ambush Bell class-skill subsystem: tuning, arming, lure targeting, detonation, damage application, and kill rewards."""
# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

import math
from ..constants import (
    ENEMY_HIT_RADIUS,
)
from ..models import (
    AmbushBell,
    AmbushBellTuning,
    Enemy,
    FloatingText,
)


from .damage import DamageContext

class _AmbushBellCombatMixin:
    # ------------------------------------------------------------------
    # Rogue Ambush Bell (class-skill lure trap).
    # ------------------------------------------------------------------
    AMBUSH_BELL_PLANT_RANGE = 4.35
    AMBUSH_BELL_ARM_TIME = 0.34
    AMBUSH_BELL_LIFETIME = 6.0
    AMBUSH_BELL_LURE_RADIUS = 6.0
    AMBUSH_BELL_TRIGGER_RADIUS = 0.95
    AMBUSH_BELL_DAMAGE_RADIUS = 1.85

    def ambush_bell_tuning(self) -> AmbushBellTuning:
        """Return the cast profile for Rogue's Ambush Bell action skill.

        The Trap path specializes this profile with utility first and damage
        second: faster setup, stronger lure control, poison/snare payoff, and a
        modest capstone recovery reward on successful ambush kills.
        """
        plant_range = self.AMBUSH_BELL_PLANT_RANGE
        arm_time = self.AMBUSH_BELL_ARM_TIME
        lifetime = self.AMBUSH_BELL_LIFETIME
        lure_radius = self.AMBUSH_BELL_LURE_RADIUS
        trigger_radius = self.AMBUSH_BELL_TRIGGER_RADIUS
        damage_radius = self.AMBUSH_BELL_DAMAGE_RADIUS
        primary_damage = 20 + self.player.level * 3 + self.player.melee_bonus
        primary_damage += max(0, self.player.spell_bonus // 2)
        splash_ratio = 0.48
        smoke_duration = 0.52
        status_effect = ""
        status_duration = 0.0
        primary_snare_duration = 0.0
        splash_snare_duration = 0.0
        expired_damage_scale = 0.55
        kill_cooldown_floor = 0.0
        kill_mana_refund = 0
        facing_damage_multiplier = 1.18
        facing_crit_bonus = 0.12

        if self.player.has_upgrade("rogue_smoke"):
            smoke_duration += 0.22
        if self.player.has_upgrade("rogue_night_veil"):
            smoke_duration += 0.16
        if self.player.has_upgrade("rogue_umbral"):
            smoke_duration += 0.18
        if self.equipment_skill_bonus("Dash tempo"):
            smoke_duration += 0.06

        if self.player.has_upgrade("rogue_trap_craft"):
            arm_time -= 0.04
            lifetime += 0.35
            lure_radius += 0.35
            primary_damage += 1
        if self.player.has_upgrade("rogue_venom"):
            status_effect = "poisoned"
            status_duration = max(status_duration, 2.2)
            primary_damage += 2
        if self.player.has_upgrade("rogue_venom_trap"):
            status_effect = "poisoned"
            status_duration = max(status_duration, 2.45)
            splash_ratio += 0.02
        if self.player.has_upgrade("rogue_bear_trap"):
            trigger_radius += 0.05
            primary_damage += 4
            primary_snare_duration = max(primary_snare_duration, 1.05)
            facing_damage_multiplier += 0.06
        if self.player.has_upgrade("rogue_trap_master"):
            lure_radius += 0.45
            damage_radius += 0.16
            primary_damage += 3
            splash_ratio += 0.05
            expired_damage_scale += 0.08
            facing_crit_bonus += 0.03
            if status_effect:
                status_duration += 0.35
            if primary_snare_duration > 0.0:
                splash_snare_duration = max(splash_snare_duration, 0.45)
        if self.player.has_upgrade("rogue_ambush_engineer"):
            arm_time -= 0.05
            plant_range += 0.20
            lure_radius += 0.25
            damage_radius += 0.14
            primary_damage += 5
            splash_ratio += 0.03
            expired_damage_scale += 0.04
            facing_damage_multiplier += 0.04
            facing_crit_bonus += 0.04
            kill_cooldown_floor = 1.05
            kill_mana_refund = 4
            if status_effect:
                status_duration += 0.35
            if primary_snare_duration > 0.0:
                primary_snare_duration += 0.25
                splash_snare_duration = max(splash_snare_duration, 0.70)
        if self.equipment_class_skill_bonus():
            primary_damage += 2
        if self.equipment_class_skill_bonus("Ambush Bell radius"):
            damage_radius += 0.18

        primary_damage = max(8, primary_damage)
        return AmbushBellTuning(
            plant_range=min(4.75, plant_range),
            arm_time=max(0.22, arm_time),
            lifetime=min(7.0, lifetime),
            lure_radius=min(7.05, lure_radius),
            trigger_radius=min(1.08, trigger_radius),
            damage_radius=min(2.35, damage_radius),
            primary_damage=primary_damage,
            splash_damage=max(5, int(primary_damage * splash_ratio)),
            smoke_duration=min(1.25, smoke_duration),
            status_effect=status_effect,
            status_duration=status_duration,
            primary_snare_duration=primary_snare_duration,
            splash_snare_duration=splash_snare_duration,
            expired_damage_scale=min(0.72, expired_damage_scale),
            kill_cooldown_floor=kill_cooldown_floor,
            kill_mana_refund=kill_mana_refund,
            facing_damage_multiplier=facing_damage_multiplier,
            facing_crit_bonus=facing_crit_bonus,
        )

    def ambush_bell_arm_time(self) -> float:
        return self.ambush_bell_tuning().arm_time

    def ambush_bell_damage_radius(self) -> float:
        return self.ambush_bell_tuning().damage_radius

    def ambush_bell_smoke_duration(self) -> float:
        return self.ambush_bell_tuning().smoke_duration

    def ambush_bell_base_damage(self) -> int:
        return self.ambush_bell_tuning().primary_damage

    def _ambush_bell_status(self) -> tuple[str, float]:
        tuning = self.ambush_bell_tuning()
        return tuning.status_effect, tuning.status_duration

    def _ambush_bell_target_point(
        self, tuning: AmbushBellTuning | None = None
    ) -> tuple[float, float]:
        tuning = tuning or self.ambush_bell_tuning()
        fx, fy = self.player.facing_x, self.player.facing_y
        length = math.hypot(fx, fy)
        if length <= 0.001:
            fx, fy = 1.0, 0.0
        else:
            fx, fy = fx / length, fy / length
        target_x = self.player.x + fx * tuning.plant_range
        target_y = self.player.y + fy * tuning.plant_range
        return self._nearest_ambush_bell_floor(target_x, target_y, tuning.plant_range)

    def _nearest_ambush_bell_floor(
        self, target_x: float, target_y: float, plant_range: float | None = None
    ) -> tuple[float, float]:
        px, py = self.player.x, self.player.y
        dx = target_x - px
        dy = target_y - py
        max_range = plant_range or self.AMBUSH_BELL_PLANT_RANGE
        distance = math.hypot(dx, dy)
        if distance > max_range and distance > 0.001:
            scale = max_range / distance
            dx *= scale
            dy *= scale
        # Walk backward from the aimed point toward the Rogue so a wall-click or
        # wall-facing cast lands on the nearest reachable floor instead of failing.
        for step in range(16, 0, -1):
            t = step / 16.0
            x = px + dx * t
            y = py + dy * t
            if (
                self.dungeon.is_floor(x, y)
                and not self.dungeon.blocked_for_radius(x, y, 0.22)
                and self.dungeon.line_of_sight(px, py, x, y)
            ):
                return x, y
        return px, py

    def player_cast_ambush_bell(self) -> None:
        """Rogue class skill: plant one lure trap at the aimed ground point."""
        if self.player.class_name != "Rogue":
            return
        mana_cost = self.class_skill_mana_cost()
        if self.player.class_skill_timer > 0 or self.player.mana < mana_cost:
            return

        tuning = self.ambush_bell_tuning()
        x, y = self._ambush_bell_target_point(tuning)
        bell = AmbushBell(
            x=x,
            y=y,
            lifetime=tuning.lifetime,
            arm_timer=tuning.arm_time,
            lure_radius=tuning.lure_radius,
            trigger_radius=tuning.trigger_radius,
            damage_radius=tuning.damage_radius,
            primary_damage=tuning.primary_damage,
            splash_damage=tuning.splash_damage,
            max_lifetime=tuning.lifetime,
            max_arm_timer=tuning.arm_time,
            smoke_duration=tuning.smoke_duration,
            status_effect=tuning.status_effect,
            status_duration=tuning.status_duration,
            primary_snare_duration=tuning.primary_snare_duration,
            splash_snare_duration=tuning.splash_snare_duration,
            expired_damage_scale=tuning.expired_damage_scale,
            kill_cooldown_floor=tuning.kill_cooldown_floor,
            kill_mana_refund=tuning.kill_mana_refund,
            facing_damage_multiplier=tuning.facing_damage_multiplier,
            facing_crit_bonus=tuning.facing_crit_bonus,
        )

        self.player.class_skill_timer = self.class_skill_cooldown()
        self.player.mana -= mana_cost
        self.set_player_action_visual("cast", 0.28)
        self.set_player_status("smoke", tuning.smoke_duration)
        self.ambush_bells = [bell]
        self.add_impact(
            self.player.x,
            self.player.y,
            self.skill_color(),
            ttl=0.30,
            radius=0.36,
            kind="cast",
            archetype=self.player.class_name,
        )
        bell_color = self.damage_type_color("shadow")
        self.add_impact(x, y, bell_color, ttl=0.30, radius=0.34, kind="ambush_bell")
        self.add_light(x, y, 1.8, bell_color, intensity=0.75, ttl=0.42, kind="bell")
        self.apply_story_blood_price("ambush")
        self.floaters.append(
            FloatingText("Ambush Bell", x, y - 0.42, self.skill_color(), ttl=0.9)
        )
        self.play_sfx("bell")

    def update_ambush_bells(self, dt: float) -> None:
        bells = getattr(self, "ambush_bells", [])
        if not bells:
            return
        kept: list[AmbushBell] = []
        for bell in bells:
            if bell.triggered:
                continue
            if dt > 0.0:
                bell.lifetime -= dt
                if bell.arm_timer > 0.0:
                    previous_arm = bell.arm_timer
                    bell.arm_timer = max(0.0, bell.arm_timer - dt)
                    if previous_arm > 0.0 and bell.arm_timer <= 0.0:
                        self._announce_ambush_bell_armed(bell)
            elif bell.arm_timer <= 0.0 and not bell.armed_announced:
                self._announce_ambush_bell_armed(bell)

            if bell.armed:
                primary = self._ambush_bell_trigger_enemy(bell)
                if primary is not None:
                    self.detonate_ambush_bell(bell, primary)
                    continue

            if bell.lifetime <= 0.0:
                self.detonate_ambush_bell(bell, None, expired=True)
                continue
            kept.append(bell)
        self.ambush_bells = kept

    def _announce_ambush_bell_armed(self, bell: AmbushBell) -> None:
        if bell.armed_announced:
            return
        bell.armed_announced = True
        color = self.damage_type_color("shadow")
        self.add_impact(bell.x, bell.y, color, ttl=0.24, radius=0.28, kind="spark")
        self.add_light(bell.x, bell.y, 1.45, color, intensity=0.55, ttl=0.30, kind="bell")

    def _ambush_bell_trigger_enemy(self, bell: AmbushBell) -> Enemy | None:
        best: Enemy | None = None
        best_distance = float("inf")
        for enemy in self.enemies:
            if not enemy.alive:
                continue
            hit_radius = max(0.0, self.enemy_hit_radius(enemy) - ENEMY_HIT_RADIUS)
            distance = math.hypot(enemy.x - bell.x, enemy.y - bell.y)
            if (
                distance <= bell.trigger_radius + hit_radius * 0.5
                and distance < best_distance
                and self.dungeon.line_of_sight(bell.x, bell.y, enemy.x, enemy.y)
            ):
                best = enemy
                best_distance = distance
        return best

    def ambush_bell_lure_target(self, enemy: Enemy) -> AmbushBell | None:
        bells = getattr(self, "ambush_bells", [])
        if not bells or enemy.kind == "boss" or enemy.is_boss_encounter:
            return None
        best: AmbushBell | None = None
        best_distance = float("inf")
        for bell in bells:
            if not bell.armed or bell.lifetime <= 0.0:
                continue
            distance = math.hypot(enemy.x - bell.x, enemy.y - bell.y)
            if distance > bell.lure_radius or distance >= best_distance:
                continue
            if not self.dungeon.line_of_sight(enemy.x, enemy.y, bell.x, bell.y):
                continue
            best = bell
            best_distance = distance
        return best

    def _enemy_facing_point(self, enemy: Enemy, x: float, y: float) -> bool:
        dx = x - enemy.x
        dy = y - enemy.y
        distance = math.hypot(dx, dy)
        if distance <= 0.001:
            return True
        facing_dot = enemy.facing_x * (dx / distance) + enemy.facing_y * (dy / distance)
        return facing_dot > 0.48

    def _ambush_bell_primary_damage(self, bell: AmbushBell, enemy: Enemy) -> int:
        damage = bell.primary_damage
        facing_bell = self._enemy_facing_point(enemy, bell.x, bell.y)
        if facing_bell:
            damage = int(damage * bell.facing_damage_multiplier) + 2
        if self.player.has_upgrade("rogue_precision"):
            damage += 3
        if self.player.has_upgrade("rogue_venom"):
            damage += 2
        if self.player.has_upgrade("rogue_executioner"):
            damage += 5 if enemy.statuses.get("poisoned", 0.0) > 0 else 3
        if self.player.has_upgrade("rogue_crimson_edge"):
            damage = int(damage * 1.12)
        if self.player.has_upgrade("rogue_deathmark"):
            damage = int(damage * 1.20)

        crit_chance = 0.0
        crit_mult = 1.0
        if self.player.has_upgrade("rogue_deathmark"):
            crit_chance, crit_mult = 0.34, 2.15
        elif self.player.has_upgrade("rogue_crimson_edge"):
            crit_chance, crit_mult = 0.28, 2.0
        elif self.player.has_upgrade("rogue_executioner"):
            crit_chance, crit_mult = 0.22, 1.9
        elif self.player.has_upgrade("rogue_venom"):
            crit_chance, crit_mult = 0.16, 1.75
        elif self.player.has_upgrade("rogue_precision"):
            crit_chance, crit_mult = 0.10, 1.6
        if facing_bell:
            crit_chance += bell.facing_crit_bonus
        if crit_chance > 0.0 and self.rng.random() < crit_chance:
            damage = int(damage * crit_mult)
            self.floaters.append(
                FloatingText("Bell Crit", enemy.x, enemy.y - 0.48, (255, 225, 120))
            )
        return self.apply_story_player_damage(damage)

    def _ambush_bell_targets(self, bell: AmbushBell, radius: float) -> list[Enemy]:
        targets: list[tuple[float, Enemy]] = []
        for enemy in self.enemies:
            if not enemy.alive:
                continue
            hit_radius = max(0.0, self.enemy_hit_radius(enemy) - ENEMY_HIT_RADIUS)
            distance = math.hypot(enemy.x - bell.x, enemy.y - bell.y)
            if (
                distance <= radius + hit_radius * 0.5
                and self.dungeon.line_of_sight(bell.x, bell.y, enemy.x, enemy.y)
            ):
                targets.append((distance, enemy))
        return [enemy for _distance, enemy in sorted(targets, key=lambda entry: entry[0])]

    def _damage_ambush_bell_enemy(
        self,
        enemy: Enemy,
        amount: int,
        direction: tuple[float, float],
        status_effect: str,
        status_duration: float,
        snare_duration: float,
    ) -> bool:
        """Damage a bell target through shared combat and report whether it died."""
        was_alive = enemy.alive
        self.damage_enemy(
            DamageContext(
                target=enemy,
                amount=amount,
                damage_type="physical",
                knockback_from=direction,
                status_effect=status_effect,
                status_duration=status_duration,
                source="ambush_bell",
            )
        )
        if snare_duration > 0.0 and enemy.alive:
            self.apply_enemy_status(enemy, "snared", snare_duration)
        return was_alive and not enemy.alive

    def _apply_ambush_bell_kill_reward(self, bell: AmbushBell, kills: int) -> None:
        if kills <= 0:
            return
        refunded = 0
        if bell.kill_cooldown_floor > 0.0:
            before = self.player.class_skill_timer
            self.player.class_skill_timer = min(self.player.class_skill_timer, bell.kill_cooldown_floor)
            if self.player.class_skill_timer < before:
                refunded += 1
        if bell.kill_mana_refund > 0:
            before_mana = self.player.mana
            self.player.mana = min(
                self.player.max_mana, self.player.mana + bell.kill_mana_refund
            )
            if self.player.mana > before_mana:
                refunded += 1
        if refunded:
            self.floaters.append(
                FloatingText(
                    "Bell Reprise",
                    self.player.x,
                    self.player.y - 0.55,
                    self.skill_color(),
                    ttl=0.85,
                )
            )

    def detonate_ambush_bell(
        self, bell: AmbushBell, primary: Enemy | None = None, expired: bool = False
    ) -> None:
        if bell.triggered:
            return
        bell.triggered = True
        color = self.damage_type_color("shadow")
        self.add_impact(
            bell.x,
            bell.y,
            color,
            ttl=0.44 if not expired else 0.34,
            radius=bell.damage_radius,
            kind="ambush_bell",
        )
        self.add_light(
            bell.x,
            bell.y,
            2.8 if not expired else 2.0,
            color,
            intensity=0.85 if not expired else 0.55,
            ttl=0.42,
            kind="bell",
        )
        self.set_player_status("smoke", bell.smoke_duration)

        status_effect = bell.status_effect
        status_duration = bell.status_duration
        radius = bell.damage_radius if not expired else bell.damage_radius * 0.82
        targets = self._ambush_bell_targets(bell, radius)
        hits = 0
        kills = 0
        if (
            primary is not None
            and primary.alive
            and self.dungeon.line_of_sight(bell.x, bell.y, primary.x, primary.y)
        ):
            if primary not in targets:
                targets.insert(0, primary)
            direction = (primary.x - bell.x, primary.y - bell.y)
            if self._damage_ambush_bell_enemy(
                primary,
                self._ambush_bell_primary_damage(bell, primary),
                direction,
                status_effect,
                status_duration,
                bell.primary_snare_duration,
            ):
                kills += 1
            hits += 1

        for enemy in targets:
            if enemy is primary or not enemy.alive:
                continue
            direction = (enemy.x - bell.x, enemy.y - bell.y)
            damage = bell.splash_damage
            if expired:
                damage = max(3, int(damage * bell.expired_damage_scale))
            damage = self.apply_story_player_damage(damage)
            if self._damage_ambush_bell_enemy(
                enemy,
                damage,
                direction,
                status_effect,
                status_duration * 0.75,
                bell.splash_snare_duration,
            ):
                kills += 1
            hits += 1

        self._apply_ambush_bell_kill_reward(bell, kills)
        label = "Bell Puff" if expired and hits == 0 else f"Ambush Bell x{hits}"
        self.floaters.append(
            FloatingText(label, bell.x, bell.y - 0.5, self.skill_color(), ttl=0.85)
        )
        self.play_sfx("bell")
