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
"""Damage application primitives: damage_enemy, player lifesteal, chain proc, kill rewards, and the shared enemy hit-flash trigger used by all damage sites."""
# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

import math
from dataclasses import dataclass

from ._utils import KNOCKBACK_SPEED
from ..models import (
    Enemy,
    FloatingText,
)


@dataclass(frozen=True, slots=True)
class DamageContext:
    """Typed bundle describing one damage event applied to an enemy.

    Replaces the positional/keyword args ``damage_enemy`` took pre-4.5.
    ``source`` is a short label ("melee" / "bolt" / "nova" / "counter" /
    "projectile" / "chain" / "ambush_bell") for future damage modifiers
    that branch on origin; ``is_crit`` carries crit info through to the
    damage pipeline so future crit-driven procs/floaters need not re-roll.
    """

    target: Enemy
    amount: int
    damage_type: str = "physical"
    knockback_from: tuple[float, float] = (0.0, 0.0)
    status_effect: str = ""
    status_duration: float = 0.0
    source: str = ""
    is_crit: bool = False


class _DamageCombatMixin:
    def _trigger_enemy_hit_flash(self, enemy: Enemy) -> None:
        duration = 0.32 if enemy.kind == "boss" else 0.22
        enemy_id = id(enemy)
        if duration >= self.enemy_hit_flashes.get(enemy_id, 0.0):
            self.enemy_hit_flash_durations[enemy_id] = duration
        self.enemy_hit_flashes[enemy_id] = max(
            self.enemy_hit_flashes.get(enemy_id, 0.0), duration
        )

    def damage_enemy(self, ctx: DamageContext) -> None:
        enemy = ctx.target
        amount = ctx.amount
        damage_type = ctx.damage_type
        knockback_from = ctx.knockback_from
        status_effect = ctx.status_effect
        status_duration = ctx.status_duration
        amount = self.mitigate_enemy_damage(enemy, amount, damage_type)
        proc_damage = 0
        ignite_proc = self.equipped_unique_effect(
            "embers on hit"
        ) or self.roll_equipped_proc("ignite")
        if ignite_proc and damage_type != "fire":
            proc_damage += max(1, self.player.level // 2 + 2)
            self.apply_enemy_status(enemy, "burning", 1.1)
        chill_proc = (
            self.equipped_unique_effect("chill on hit")
            or self.roll_equipped_proc("chill")
            or status_effect == "chilled"
        )
        if chill_proc:
            self.apply_enemy_status(enemy, "chilled", max(status_duration, 1.0))
        if self.roll_equipped_proc("poison") or self.roll_equipped_proc("bleed"):
            self.apply_enemy_status(enemy, "poisoned", max(status_duration, 1.4))
        if self.roll_equipped_proc("snare"):
            self.apply_enemy_status(enemy, "snared", max(status_duration, 1.0))
        if self.roll_equipped_proc("smoke"):
            self.set_player_status("smoke", 0.5)
        if self.roll_equipped_proc("smite"):
            proc_damage += max(2, self.player.level + self.player.spell_bonus // 3)
        if status_effect and status_effect != "chilled":
            self.apply_enemy_status(enemy, status_effect, status_duration)
        if enemy.statuses.get("burning", 0.0) > 0 and damage_type == "fire":
            proc_damage += max(1, self.player.level // 3 + 1)
        total = max(1, amount + proc_damage)
        enemy.hp -= total
        self._trigger_enemy_hit_flash(enemy)
        hit_color = (
            self.theme.accent
            if enemy.kind == "boss"
            else self.damage_type_color(damage_type)
        )
        self.floaters.append(
            FloatingText(f"-{total}", enemy.x, enemy.y - 0.2, hit_color)
        )
        self.add_impact(
            enemy.x,
            enemy.y,
            hit_color,
            ttl=0.32 if enemy.kind != "boss" else 0.46,
            radius=0.36 if enemy.kind != "boss" else 0.58,
            kind="hit",
        )
        if self.roll_equipped_proc("chain"):
            self._apply_chain_proc(enemy, max(1, total // 3))
        self._apply_player_lifesteal(total)
        kx, ky = knockback_from
        length = math.hypot(kx, ky)
        if length > 0.001:
            # Set a velocity consumed/decayed in update_enemies so the shove is
            # framerate-independent and respects collision (and applies even to
            # stunned enemies). Total displacement ~= KNOCKBACK_SPEED / rate.
            enemy.knockback_vx = (kx / length) * KNOCKBACK_SPEED
            enemy.knockback_vy = (ky / length) * KNOCKBACK_SPEED
        if enemy.hp <= 0:
            self.kill_enemy(enemy)
        else:
            self.play_sfx("hit")

    def _apply_player_lifesteal(self, damage_done: int) -> None:
        ratio = self.equipment_lifesteal_ratio()
        if ratio <= 0.0 or damage_done <= 0:
            return
        healed = min(
            self.player.max_hp - self.player.hp, max(1, int(damage_done * ratio))
        )
        if healed <= 0:
            return
        self.player.hp += healed
        self.floaters.append(
            FloatingText(
                f"+{healed}",
                self.player.x,
                self.player.y - 0.45,
                (214, 92, 150),
            )
        )

    def _apply_chain_proc(self, source: Enemy, damage: int) -> None:
        target = None
        best_distance = 3.75
        for enemy in self.enemies:
            if enemy is source or not enemy.alive:
                continue
            distance = math.hypot(enemy.x - source.x, enemy.y - source.y)
            if distance < best_distance and self.dungeon.line_of_sight(
                source.x, source.y, enemy.x, enemy.y
            ):
                best_distance = distance
                target = enemy
        if target is None:
            return
        target.hp -= damage
        self._trigger_enemy_hit_flash(target)
        self.floaters.append(
            FloatingText(
                f"Arc -{damage}",
                target.x,
                target.y - 0.35,
                self.damage_type_color("arcane"),
                ttl=0.65,
            )
        )
        self.add_impact(
            target.x,
            target.y,
            self.damage_type_color("arcane"),
            ttl=0.24,
            radius=0.30,
            kind="burst",
        )
        if target.hp <= 0:
            self.kill_enemy(target)

    def kill_enemy(self, enemy: Enemy) -> None:
        if enemy not in self.enemies:
            return
        self.enemies.remove(enemy)
        self.enemy_hit_flashes.pop(id(enemy), None)
        self.run_stats.kills += 1
        # Time path Degree 5 (Eternal Moment): each kill while Time Skip is active
        # refunds ~40% of the class-skill cooldown so aggressive play sustains
        # the slow.
        if (
            self.player.class_name == "Warden"
            and self.player.time_skip_timer > 0
            and self.player.has_upgrade("warden_eternal_wall")
            and self.player.class_skill_timer > 0
        ):
            self.player.class_skill_timer = max(
                0.0, self.player.class_skill_timer - self.class_skill_cooldown() * 0.4
            )
        death_color = (
            self.theme.accent if enemy.kind in ("boss", "miniboss") else enemy.color
        )
        # 4-tile bosses get a much larger death burst so the kill reads as a
        # real milestone.
        big = enemy.size >= 2
        self.add_impact(
            enemy.x,
            enemy.y,
            death_color,
            ttl=0.58 if enemy.kind != "boss" else 0.82,
            radius=0.86 if big else (0.56 if enemy.kind != "boss" else 1.05),
            kind="death",
        )
        if enemy.elite_modifier or enemy.kind in ("boss", "miniboss"):
            self.add_impact(
                enemy.x,
                enemy.y,
                death_color,
                ttl=0.48,
                radius=0.96 if big else (0.66 if enemy.kind != "boss" else 1.15),
                kind="burst",
            )
        if enemy.kind == "boss":
            self.run_stats.boss_killed = True
            if enemy.name not in self.run_stats.defeated_bosses:
                self.run_stats.defeated_bosses.append(enemy.name)
            drop_x, drop_y = self.drop_position_near(enemy.x, enemy.y)
            unique = self._make_unique(drop_x, drop_y)
            self.items.append(unique)
            self.record_notable_loot(unique)
            self.floaters.append(
                FloatingText(
                    "Gate seal broken",
                    enemy.x,
                    enemy.y - 0.5,
                    self.theme.accent,
                    ttl=1.6,
                )
            )
            self.trigger_screen_flash(self.theme.accent, 0.36)
            self.add_impact(
                enemy.x, enemy.y, self.theme.accent, ttl=0.72, radius=0.9, kind="burst"
            )
            self.play_sfx("boss")
        elif enemy.kind == "miniboss":
            self.run_stats.minibosses_killed += 1
            if enemy.role in ("floor_boss", "challenge_boss"):
                if enemy.name not in self.run_stats.defeated_bosses:
                    self.run_stats.defeated_bosses.append(enemy.name)
                plan = self.current_floor_plan()
                if plan is not None and plan.encounter_key == "challenge_room":
                    self.run_stats.challenge_rooms_cleared += 1
            drop_x, drop_y = self.drop_position_near(enemy.x, enemy.y)
            rare = self._make_equipment(
                self.rng.choice(("weapon", "armor")), "Rare", drop_x, drop_y
            )
            self.items.append(rare)
            self.record_notable_loot(rare)
            if big:
                # Floor guardian takedown: flash and a victory-style burst.
                self.trigger_screen_flash(self.theme.accent, 0.28)
                self.add_impact(
                    enemy.x,
                    enemy.y,
                    self.theme.accent,
                    ttl=0.66,
                    radius=0.82,
                    kind="burst",
                )
                self.floaters.append(
                    FloatingText(
                        "Guardian fallen",
                        enemy.x,
                        enemy.y - 0.5,
                        self.theme.accent,
                        ttl=1.6,
                    )
                )
                self.play_sfx("boss")
        elif enemy.elite_modifier:
            self.run_stats.elites_killed += 1
        xp_gain = max(
            1, int(enemy.xp * (1.0 + self.story_effect_value("xp_bonus", 0.0, 0.35)))
        )
        if (
            self.player.class_name == "Acolyte"
            and self.player.has_upgrade("acolyte_gravebind")
            and enemy.statuses.get("bound", 0.0) > 0
        ):
            echo_heal = min(
                self.player.max_hp - self.player.hp, 4 + self.current_depth // 2
            )
            if echo_heal > 0:
                self.player.hp += echo_heal
                self.player.mana = min(self.player.max_mana, self.player.mana + 2)
                self.floaters.append(
                    FloatingText(
                        f"Grave echo +{echo_heal}",
                        self.player.x,
                        self.player.y - 0.5,
                        self.damage_type_color("shadow"),
                        ttl=0.85,
                    )
                )
        if self.player.gain_xp(xp_gain):
            # Milestone 3.3: level-ups award a mastery token (handled inside
            # `gain_xp`) instead of auto-granting a node. The player spends
            # the token in the character sheet. Surface the banked token so the
            # player knows to open the sheet.
            self.floaters.append(
                FloatingText(
                    "LEVEL UP · MASTERY TOKEN",
                    self.player.x,
                    self.player.y - 0.6,
                    (120, 230, 150),
                    ttl=1.4,
                )
            )
        healing_echo = self.story_effect_value("healing_echo", 0.0, 1.0)
        if (
            healing_echo > 0
            and self.player.hp < self.player.max_hp
            and self.rng.random() < min(1.0, healing_echo)
        ):
            healed = min(
                self.player.max_hp - self.player.hp,
                max(2, int(enemy.xp * 0.12) + self.current_depth // 2),
            )
            self.player.hp += healed
            self.player.mana = min(
                self.player.max_mana, self.player.mana + max(1, healed // 2)
            )
            self.floaters.append(
                FloatingText(
                    f"Story echo +{healed}",
                    self.player.x,
                    self.player.y - 0.55,
                    self.story_state.accent if self.story_state else (170, 225, 190),
                    ttl=1.0,
                )
            )
        # 4.2: loot drops are rarer across the board (but not by too much).
        # The previous 0.45 base made most kills spit out an item; nudging down
        # to 0.36 keeps drops exciting while making each piece of loot feel
        # earned. Elites and bosses still grant their existing gold bonuses.
        if self.rng.random() < 0.36:
            drop_x, drop_y = self.drop_position_near(enemy.x, enemy.y)
            loot = self._make_loot(drop_x, drop_y)
            self.items.append(loot)
            self.record_notable_loot(loot)
        gold = self.rng.randrange(4, 11) + self.current_depth * 2
        if enemy.elite_modifier:
            gold += 8
        if enemy.kind in ("boss", "miniboss"):
            gold += 18
        self.player.gold += gold
        self.floaters.append(
            FloatingText(f"+{gold} gold", enemy.x, enemy.y - 0.55, (225, 190, 92))
        )
        self.save_run()
