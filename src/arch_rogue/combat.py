# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
#
# AI Provenance & Liability Notice:
# This repository contains code generated, assisted, or refactored by Artificial
# Intelligence models. Provided strictly "AS IS" under Apache 2.0 with no warranty
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

# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

import math
from itertools import chain

import pygame

from .constants import (
    BOSS_FOOTPRINT_HIT_RADIUS,
    BOSS_FOOTPRINT_MOVE_RADIUS,
    BOSS_HIT_RADIUS,
    ENEMY_HIT_RADIUS,
    ENEMY_PROJECTILE_HIT_RADIUS,
    LARGE_ENEMY_HIT_RADIUS,
    LIGHT_PROJECTILE_INTENSITY,
    LIGHT_PROJECTILE_RADIUS,
    LIGHT_PROJECTILE_TTL,
    PLAYER_HIT_RADIUS,
    PLAYER_MELEE_ARC_DOT,
    PLAYER_MELEE_RANGE,
    PLAYER_MOVE_SPEED,
    PLAYER_PROJECTILE_HIT_RADIUS,
    WALK_ANIM_RUNTIME_SCALE_FLOOR,
    WALK_ANIM_SPEED_CEIL,
    WALK_ANIM_SPEED_FLOOR,
    WALK_ANIMATION_RATE,
)
from .content import (
    DISCIPLINE_UPGRADES,
    combo_bonus,
    completed_paths,
    cross_path_tag_bonus,
    is_path_locked,
    discipline_by_key,
    disciplines_for_archetype,
)
from .models import (
    AmbushBell,
    AmbushBellTuning,
    Color,
    Enemy,
    Familiar,
    FloatingText,
    Player,
    Projectile,
)


class CombatMixin:
    CONTROLLER_AIM_SNAP_RANGE = 5.0
    CONTROLLER_AIM_SNAP_DOT = 0.86

    def damage_type_color(self, damage_type: str) -> Color:
        return {
            "physical": (255, 210, 120),
            "fire": (255, 132, 74),
            "frost": (126, 206, 242),
            "poison": (126, 214, 92),
            "arcane": (160, 118, 245),
            "holy": (235, 205, 120),
            "shadow": (214, 92, 150),
        }.get(damage_type, (255, 210, 120))

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

    def player_status(self, name: str) -> float:
        return float(self.player.status_effects.get(name, 0.0))

    def set_player_status(self, name: str, duration: float) -> None:
        self.player.status_effects[name] = max(
            self.player.status_effects.get(name, 0.0), duration
        )

    def apply_enemy_status(self, enemy: Enemy, status: str, duration: float) -> None:
        if duration <= 0:
            return
        if status == "poisoned" and enemy.resistances.get("poison", 0.0) >= 0.55:
            duration *= 0.55
        enemy.statuses[status] = max(enemy.statuses.get(status, 0.0), duration)
        status_damage_type = {
            "poisoned": "poison",
            "chilled": "frost",
            "burning": "fire",
            "snared": "physical",
            "bound": "shadow",
            "stunned": "holy",
        }.get(status, "holy")
        self.floaters.append(
            FloatingText(
                status.title(),
                enemy.x,
                enemy.y - 0.45,
                self.damage_type_color(status_damage_type),
                ttl=0.65,
            )
        )

    @staticmethod
    def _average_slow_factors(
        dt: float, factors: tuple[tuple[float, float], ...]
    ) -> tuple[float, float]:
        """Return exact average movement and cadence scales for overlapping slows."""
        constant_scale = 1.0
        partial: list[tuple[float, float]] | None = None
        for ttl, scale in factors:
            if ttl <= 0.0:
                continue
            if dt <= 0.0 or ttl >= dt:
                constant_scale *= scale
                continue
            if partial is None:
                partial = []
            partial.append((ttl, scale))
        if partial is None:
            return (
                constant_scale,
                max(WALK_ANIM_RUNTIME_SCALE_FLOOR, constant_scale),
            )

        # Partial expirations are rare (one frame per effect). Integrate the
        # exact piecewise product only on those frames; the common path above
        # stays allocation-light.
        breakpoints = [0.0, dt, *(ttl for ttl, _scale in partial)]
        breakpoints.sort()
        weighted_movement = 0.0
        weighted_animation = 0.0
        for start, end in zip(breakpoints, breakpoints[1:]):
            if end <= start:
                continue
            midpoint = (start + end) * 0.5
            interval_scale = constant_scale
            for ttl, scale in partial:
                if midpoint < ttl:
                    interval_scale *= scale
            duration = end - start
            weighted_movement += interval_scale * duration
            weighted_animation += max(
                WALK_ANIM_RUNTIME_SCALE_FLOOR, interval_scale
            ) * duration
        return weighted_movement / dt, weighted_animation / dt

    def enemy_speed_multiplier(self, enemy: Enemy, dt: float = 0.0) -> float:
        movement_scale, _animation_scale = self._average_slow_factors(
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
        return self._average_slow_factors(
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
        resistance = max(-0.35, min(0.70, enemy.resistances.get(damage_type, 0.0)))
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
        elif getattr(self, "aim_input_mode", "mouse") != "controller":
            self.face_player_toward_screen_point(*pygame.mouse.get_pos())
        else:
            self.snap_controller_aim_to_enemy()

    def face_player_toward_screen_point(self, sx: int, sy: int) -> tuple[float, float]:
        target_x, target_y = self.screen_to_world(sx, sy)
        dx = target_x - self.player.x
        dy = target_y - self.player.y
        distance = math.hypot(dx, dy)
        if distance > 0.05:
            self.player.facing_x = dx / distance
            self.player.facing_y = dy / distance
        return dx, dy

    def skill_names(self) -> tuple[str, str, str, str]:
        names = {
            "Warden": ("Shield Bash", "Guard Bolt", "Time Skip", "Guard Step"),
            "Rogue": ("Backstab", "Knife Fan", "Ambush Bell", "Shadow Dash"),
            "Arcanist": ("Mage Strike", "Arc Bolt", "Frost Nova", "Blink"),
            "Acolyte": ("Blood Rite", "Spirit Bolt", "Spirit Call", "Dark Step"),
            "Ranger": ("Hawk Slash", "Multishot", "Spirit Beast", "Vault"),
        }
        return names.get(self.player.class_name, ("Slash", "Bolt", "Nova", "Dash"))

    # ------------------------------------------------------------------
    # Class skill registry — data-driven dispatch for hotkey 3.
    #
    # Each archetype maps to a class-skill *kind* (the identifier used by the
    # HUD and dispatch), and each kind maps to a cast method. Adding a new
    # class skill only requires extending these two tables, not editing the
    # dispatch logic.
    # ------------------------------------------------------------------
    _CLASS_SKILL_KINDS: dict[str, str] = {
        "Warden": "time_skip",
        "Rogue": "ambush_bell",
        "Arcanist": "nova",
        "Acolyte": "spirit_call",
        "Ranger": "spirit_beast",
    }
    _CLASS_SKILL_CASTS: dict[str, str] = {
        "spirit_call": "player_cast_spirit_call",
        "spirit_beast": "player_cast_spirit_beast",
        "ambush_bell": "player_cast_ambush_bell",
        "time_skip": "player_cast_time_skip",
        "nova": "player_cast_nova",
    }
    _CLASS_SKILL_BONUS_TERMS: dict[str, str] = {
        "Warden": "Time Skip",
        "Rogue": "Ambush Bell",
        "Arcanist": "Nova",
        "Acolyte": "Spirit Call",
        "Ranger": "Spirit Beast",
    }

    def class_skill_kind(self) -> str:
        """The archetype-specific class skill bound to hotkey 3."""
        return self._CLASS_SKILL_KINDS.get(self.player.class_name, "nova")

    def player_cast_class_skill(self) -> None:
        """Dispatch the archetype-specific class skill."""
        kind = self.class_skill_kind()
        cast_name = self._CLASS_SKILL_CASTS.get(kind, "player_cast_nova")
        getattr(self, cast_name)()

    def equipment_class_skill_bonus(self, text: str = "") -> bool:
        """Whether equipped gear boosts this archetype's canonical class skill."""
        canonical = self._CLASS_SKILL_BONUS_TERMS.get(
            self.player.class_name, "Nova"
        )
        if text:
            return canonical in text and self.equipment_skill_bonus(text)
        return self.equipment_skill_bonus(canonical)

    def skill_color(self) -> Color:
        colors = {
            "Warden": (235, 205, 120),
            "Rogue": (170, 230, 150),
            "Arcanist": (120, 210, 255),
            "Acolyte": (220, 95, 140),
            "Ranger": (150, 215, 105),
        }
        return colors.get(self.player.class_name, (120, 210, 255))

    def available_disciplines(self) -> list:
        """Disciplines the player can choose right now.

        A discipline is available when it belongs to the player's archetype, is not
        yet acquired, every prerequisite discipline has already been acquired, and
        its path has not been locked by the two-path commitment limit
        (Milestone 3.7). Degree-1 disciplines are always available until taken, unless
        their path is locked.
        """
        acquired = set(self.player.skill_upgrades)
        choices: list = []
        for node in disciplines_for_archetype(self.player.class_name):
            if node.key in acquired:
                continue
            if is_path_locked(acquired, node.archetype, node.path):
                continue
            if all(prereq in acquired for prereq in node.prerequisites):
                choices.append(node)
        return choices

    def discipline_state(self, node) -> str:
        """Return one of "chosen", "available", "path_locked", "locked".

        "path_locked" (Milestone 3.7) marks disciplines whose path is sealed by
        the two-path commitment limit and is distinct from "locked" so the
        menu can render the two reasons differently.
        """
        acquired = set(self.player.skill_upgrades)
        if node.key in acquired:
            return "chosen"
        if is_path_locked(acquired, node.archetype, node.path):
            return "path_locked"
        if all(prereq in acquired for prereq in node.prerequisites):
            return "available"
        return "locked"

    def choose_discipline(self, key: str, reason: str = "chosen") -> bool:
        """Apply a specific discipline by key, spending one mastery token.

        Returns False (without spending a point) if the discipline is unknown, belongs
        to another archetype, is already acquired, has unmet prerequisites, is
        in a path locked by the commitment limit, or the player has no mastery
        tokens to spend.
        """
        node = discipline_by_key(key)
        if node is None or node.archetype != self.player.class_name:
            return False
        if node.key in self.player.skill_upgrades:
            return False
        if not all(
            prereq in self.player.skill_upgrades for prereq in node.prerequisites
        ):
            return False
        if is_path_locked(
            set(self.player.skill_upgrades), node.archetype, node.path
        ):
            return False
        if self.player.mastery_tokens <= 0:
            return False
        self.player.mastery_tokens -= 1
        self._apply_discipline(node, reason)
        self._apply_combo_bonus_delta(node)
        return True

    def grant_mastery_token(self, amount: int = 1, reason: str = "reward") -> None:
        """Award mastery tokens from run rewards (shrines, altars, story)."""
        if amount <= 0:
            return
        self.player.mastery_tokens += amount
        self.floaters.append(
            FloatingText(
                f"+{amount} Mastery Token{'s' if amount != 1 else ''}",
                self.player.x,
                self.player.y - 0.6,
                self.skill_color(),
                ttl=1.6,
            )
        )

    def _apply_discipline(self, node, reason: str) -> None:
        self.player.skill_upgrades.append(node.key)
        self.player.melee_bonus += node.melee_bonus
        self.player.spell_bonus += node.spell_bonus
        self.player.armor_bonus += node.armor_bonus
        self.player.max_hp += node.max_hp_bonus
        self.player.hp = min(self.player.max_hp, self.player.hp + node.max_hp_bonus)
        self.player.max_mana += node.max_mana_bonus
        self.player.mana = min(
            self.player.max_mana, self.player.mana + node.max_mana_bonus
        )
        self.player.max_stamina += node.max_stamina_bonus
        self.player.stamina = min(
            self.player.max_stamina, self.player.stamina + node.max_stamina_bonus
        )
        self.player.speed += node.speed_bonus
        self.run_stats.upgrades_chosen += 1
        self.floaters.append(
            FloatingText(
                f"{node.name}: {reason}",
                self.player.x,
                self.player.y - 0.65,
                self.skill_color(),
                ttl=1.8,
            )
        )
        if node.archetype == "Ranger" and node.path == "Beast":
            self._refresh_active_spirit_beast()

    def _apply_combo_bonus_delta(self, node) -> None:
        """Apply the combo-bonus delta caused by acquiring `node`.

        Called after a discipline is chosen. If the acquisition completed a new
        path and pushed the player into a higher combo tier, the delta is
        applied to the player's derived stats so the bonus is felt immediately.
        """
        acquired = set(self.player.skill_upgrades)
        melee, spell, max_hp = combo_bonus(acquired, self.player.class_name)
        # Track the cumulative combo bonus already applied so we only apply the
        # delta on changes. Stored on the player as a private attribute.
        prev = getattr(self.player, "_combo_applied", (0, 0, 0))
        d_melee = melee - prev[0]
        d_spell = spell - prev[1]
        d_hp = max_hp - prev[2]
        if d_melee or d_spell or d_hp:
            self.player.melee_bonus += d_melee
            self.player.spell_bonus += d_spell
            self.player.max_hp += d_hp
            self.player.hp = min(self.player.max_hp, self.player.hp + d_hp)
        self.player._combo_applied = (melee, spell, max_hp)

    def combo_state(self) -> tuple[tuple[str, ...], int, int, int]:
        """Return (completed_paths, melee_bonus, spell_bonus, max_hp_bonus).

        Cheap O(nodes) lookup with no per-frame allocations beyond the returned
        tuple; safe to call from the hot path or the character sheet.
        """
        acquired = set(self.player.skill_upgrades)
        done = completed_paths(acquired, self.player.class_name)
        melee, spell, max_hp = combo_bonus(acquired, self.player.class_name)
        return (done, melee, spell, max_hp)

    def cross_path_bonus_state(self) -> tuple[int, int]:
        """Return (melee, spell) bonus from acquired cross-path modifiers."""
        return cross_path_tag_bonus(set(self.player.skill_upgrades))

    def combo_preview(self, node) -> tuple[int, int, int]:
        """Combo bonus if `node` were acquired next (for sheet hover preview)."""
        from .content import combo_bonus_preview

        return combo_bonus_preview(
            set(self.player.skill_upgrades), self.player.class_name, node.key
        )

    def grant_discipline(self, reason: str = "level up") -> bool:
        """Grant a random available discipline, respecting discipline tree prerequisites.

        Used by shrines/altars/story rewards. These are bonus grants that do
        NOT spend the player's banked mastery tokens (level-up tokens are spent
        by the player via `choose_discipline`). Falls back to the flat
        `DISCIPLINE_UPGRADES` pool only if the discipline tree yields no available disciplines.
        """
        choices = self.available_disciplines()
        if not choices:
            legacy_choices = [
                upgrade
                for upgrade in DISCIPLINE_UPGRADES
                if upgrade.archetype == self.player.class_name
                and upgrade.key not in self.player.skill_upgrades
            ]
            if not legacy_choices:
                return False
            upgrade = self.rng.choice(legacy_choices)
            node = discipline_by_key(upgrade.key)
            if node is not None:
                self._apply_discipline(node, reason)
                self._apply_combo_bonus_delta(node)
                return True
            return False
        node = self.rng.choice(choices)
        self._apply_discipline(node, reason)
        self._apply_combo_bonus_delta(node)
        return True

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
        attack_speed = max(-0.20, min(0.35, self.equipment_stat_total("attack_speed")))
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
        cast_speed = max(-0.20, min(0.35, self.equipment_stat_total("cast_speed")))
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
        cast_speed = max(-0.20, min(0.35, self.equipment_stat_total("cast_speed")))
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

    def take_player_damage(
        self,
        raw_damage: int,
        source: str = "hit",
        damage_type: str = "physical",
        attacker: Enemy | None = None,
    ) -> int:
        rogue_evade = 0.18 if self.player.has_upgrade("rogue_smoke") else 0.12
        if self.player_status("smoke") > 0:
            rogue_evade += 0.22
        can_evade = source != "trap"
        if (
            can_evade
            and self.player.class_name == "Rogue"
            and self.rng.random() < rogue_evade
        ):
            self.floaters.append(
                FloatingText(
                    "Evaded", self.player.x, self.player.y - 0.2, (170, 220, 170)
                )
            )
            return 0
        armor_bonus = (
            2 if self.player.class_name == "Warden" and source == "melee" else 0
        )
        armor = self.player.equipment.get("armor")
        typed_resist = 0.0
        if armor is not None:
            typed_resist += armor.defense * 0.006
            if armor.damage_type and armor.damage_type == damage_type:
                typed_resist += 0.08
            if "Grounded" in armor.affixes and damage_type == "arcane":
                typed_resist += 0.12
            if "Sealed" in armor.affixes and damage_type in ("shadow", "poison"):
                typed_resist += 0.10
        if self.equipped_unique_effect("glacial ward") and damage_type == "frost":
            typed_resist += 0.15
        if self.equipped_unique_effect("oathwall aegis"):
            typed_resist += 0.06
        if self.player_status("aegis") > 0:
            typed_resist += 0.24
        # Milestone 3.18.1 — Time path Degree 4 (Temporal Aegis): while Time
        # Skip is active the Warden takes 20% less damage from incoming hits.
        if (
            self.player.class_name == "Warden"
            and self.player.time_skip_timer > 0
            and self.player.has_upgrade("warden_unyielding")
        ):
            typed_resist += 0.20
        amount = max(1, raw_damage - self.player.armor() - armor_bonus)
        if typed_resist > 0:
            amount = max(1, int(round(amount * (1.0 - min(0.45, typed_resist)))))
        if self.player.has_upgrade("warden_riposte") and source == "melee":
            amount = max(1, amount - 2)
        if self.player.class_name == "Acolyte" and self.player.mana >= 4:
            self.player.mana -= 4
            amount = max(
                1, amount - (5 if self.player.has_upgrade("acolyte_veil") else 3)
            )
        resist = self.story_effect_value("damage_resist", 0.0, 0.35)
        if resist > 0:
            before_resist = amount
            amount = max(1, int(round(amount * (1.0 - resist))))
            if amount < before_resist:
                self.floaters.append(
                    FloatingText(
                        f"Story ward -{before_resist - amount}",
                        self.player.x,
                        self.player.y - 0.45,
                        self.story_state.accent
                        if self.story_state
                        else (190, 150, 245),
                        ttl=0.9,
                    )
                )
        if (
            attacker is not None
            and self.player.has_upgrade("warden_riposte")
            and source == "melee"
        ):
            counter = max(2, self.player.level + self.player.armor_bonus)
            if self.equipped_unique_effect("counter smite"):
                counter += max(3, self.player.level // 2 + 2)
            self.damage_enemy(
                attacker,
                counter,
                knockback_from=(self.player.facing_x, self.player.facing_y),
                damage_type="holy",
                status_effect="stunned"
                if self.player.has_upgrade("warden_aegis")
                else "",
                status_duration=0.35,
            )
        if any(
            item is not None and item.cursed for item in self.player.equipment.values()
        ):
            amount += 1 if damage_type in ("shadow", "poison") else 0
        if attacker is not None and attacker.alive and source == "melee" and amount > 0:
            reflected = self.equipment_thorns_damage(amount)
            if reflected > 0:
                self._reflect_thorns(attacker, reflected)
            if self.equipped_unique_effect("glacial ward"):
                self.apply_enemy_status(attacker, "chilled", 1.2)
            if self.equipped_unique_effect("pack pursuit"):
                self.apply_enemy_status(attacker, "snared", 1.0)
        self.player.hp -= amount
        if self.player.hp <= 0 and not self.run_stats.cause_of_death:
            self.run_stats.cause_of_death = f"{source} {damage_type} damage"
        self.run_stats.damage_taken += amount
        heavy_hit = amount >= self.player.max_hp * 0.18
        flash = (160, 35, 32) if heavy_hit else (105, 24, 28)
        hit_duration = 0.32 if heavy_hit else 0.22
        if hit_duration >= self.player_hit_flash:
            self.player_hit_flash_duration = hit_duration
        self.player_hit_flash = max(self.player_hit_flash, hit_duration)
        self.trigger_screen_flash(
            flash, 0.18 if amount < self.player.max_hp * 0.18 else 0.30
        )
        self.add_impact(
            self.player.x,
            self.player.y,
            (245, 95, 70),
            ttl=0.34,
            radius=0.42,
            kind="blood",
        )
        if self.player.hp > 0 and self.player.hp <= self.player.max_hp * 0.25:
            self.floaters.append(
                FloatingText(
                    "Low health",
                    self.player.x,
                    self.player.y - 0.7,
                    (245, 95, 70),
                    ttl=1.0,
                )
            )
        return amount

    def _trigger_enemy_hit_flash(self, enemy: Enemy) -> None:
        duration = 0.32 if enemy.kind == "boss" else 0.22
        enemy_id = id(enemy)
        if duration >= self.enemy_hit_flashes.get(enemy_id, 0.0):
            self.enemy_hit_flash_durations[enemy_id] = duration
        self.enemy_hit_flashes[enemy_id] = max(
            self.enemy_hit_flashes.get(enemy_id, 0.0), duration
        )

    def _reflect_thorns(self, attacker: Enemy, amount: int) -> None:
        attacker.hp -= amount
        self._trigger_enemy_hit_flash(attacker)
        self.floaters.append(
            FloatingText(
                f"Thorns -{amount}",
                attacker.x,
                attacker.y - 0.35,
                self.damage_type_color(attacker.damage_type),
                ttl=0.7,
            )
        )
        self.add_impact(
            attacker.x,
            attacker.y,
            self.damage_type_color("physical"),
            ttl=0.26,
            radius=0.30,
            kind="hit",
        )
        if attacker.hp <= 0:
            self.kill_enemy(attacker)

    def update_player(self, dt: float) -> None:
        self.player.moving = False
        self.player.locomotion_anim_scale = 0.0
        petting = (
            getattr(self, "player_action_state", "") == "pet"
            and getattr(self, "player_action_ttl", 0.0) > 0.0
        )
        # Keyboard movement (WASD + arrows) takes priority so the game is
        # playable without holding the mouse. Mouse-hold-to-walk remains as
        # a fallback for players who prefer click-to-move style.
        keys = pygame.key.get_pressed()
        kbd_dx = float(keys[pygame.K_RIGHT] or keys[pygame.K_d]) - float(
            keys[pygame.K_LEFT] or keys[pygame.K_a]
        )
        kbd_dy = float(keys[pygame.K_DOWN] or keys[pygame.K_s]) - float(
            keys[pygame.K_UP] or keys[pygame.K_w]
        )
        # Analog controller movement overrides the keyboard vector when the
        # stick is deflected past the deadzone, giving precise speed control.
        cx, cy = self.input.left_vec()
        controller_moving = bool(cx or cy)
        if controller_moving:
            self.aim_input_mode = "controller"
            kbd_dx, kbd_dy = cx, cy
        if petting:
            # Keep the authored kneel grounded. Cooldowns, statuses, and resource
            # regeneration below still advance normally during this brief pause.
            kbd_dx = kbd_dy = 0.0
            controller_moving = False
        equipment_move = max(-0.25, min(0.30, self.equipment_stat_total("move_speed")))
        move_speed = (
            PLAYER_MOVE_SPEED
            * (1.0 + equipment_move)
            * (0.82 if self.player_status("chilled") > 0 else 1.0)
        )
        if kbd_dx or kbd_dy:
            length = math.hypot(kbd_dx, kbd_dy)
            if length > 0.0:
                # Unit direction for movement; magnitude preserves analog stick
                # deflection (clamped to 1.0) so keyboard diagonals stay full
                # speed while controllers get partial-speed creeping. When the
                # right stick is actively aiming, keep facing locked to that aim
                # vector so the aim cone and projectiles do not snap to movement.
                nx, ny = kbd_dx / length, kbd_dy / length
                aim_x, aim_y = self.input.right_vec()
                if not (aim_x or aim_y):
                    self.player.facing_x = nx
                    self.player.facing_y = ny
                    if controller_moving:
                        self.snap_controller_aim_to_enemy()
                magnitude = min(1.0, length)
                moved = self.move_actor(
                    self.player,
                    nx * magnitude * move_speed * dt,
                    ny * magnitude * move_speed * dt,
                )
                if moved > 0.0 and dt > 0.0:
                    self.player.locomotion_anim_scale = (
                        moved / (dt * PLAYER_MOVE_SPEED)
                    )
            if self.enemy_in_melee_arc():
                self.player_melee_attack()
        elif not petting and pygame.mouse.get_pressed()[0]:
            dx, dy = self.face_player_toward_screen_point(*pygame.mouse.get_pos())
            distance = math.hypot(dx, dy)
            if distance > 0.12:
                step = min(move_speed * dt, distance - 0.12)
                moved = self.move_actor(
                    self.player,
                    (dx / distance) * step,
                    (dy / distance) * step,
                )
                if moved > 0.0 and dt > 0.0:
                    self.player.locomotion_anim_scale = (
                        moved / (dt * PLAYER_MOVE_SPEED)
                    )
            if self.enemy_in_melee_arc():
                self.player_melee_attack()

        self.player.melee_timer = max(0.0, self.player.melee_timer - dt)
        self.player.bolt_timer = max(0.0, self.player.bolt_timer - dt)
        self.player.dash_timer = max(0.0, self.player.dash_timer - dt)
        self.player.class_skill_timer = max(0.0, self.player.class_skill_timer - dt)
        self.player.time_skip_timer = max(0.0, self.player.time_skip_timer - dt)
        if self.player_status("poisoned") > 0:
            tick = self.player.status_effects.get("_poison_tick", 1.0) - dt
            if tick <= 0:
                poison_damage = max(1, self.current_depth // 3 + 1)
                self.player.hp -= poison_damage
                if self.player.hp <= 0 and not self.run_stats.cause_of_death:
                    self.run_stats.cause_of_death = "poisoned by lingering venom"
                self.run_stats.damage_taken += poison_damage
                tick += 1.0
                self.floaters.append(
                    FloatingText(
                        f"Poison -{poison_damage}",
                        self.player.x,
                        self.player.y - 0.55,
                        self.damage_type_color("poison"),
                        ttl=0.75,
                    )
                )
            self.player.status_effects["_poison_tick"] = tick
        next_statuses: dict[str, float] = {}
        for status, ttl in self.player.status_effects.items():
            if status.startswith("_"):
                next_statuses[status] = ttl
                continue
            ttl -= dt
            if ttl > 0:
                next_statuses[status] = ttl
        if "poisoned" not in next_statuses:
            next_statuses.pop("_poison_tick", None)
        self.player.status_effects = next_statuses
        stamina_regen = 38 if self.player.class_name == "Ranger" else 30
        mana_regen = 8 if self.player.class_name == "Arcanist" else 5
        if self.player.has_upgrade("arcanist_focus"):
            mana_regen += 3
        if self.player.has_upgrade("ranger_snare"):
            stamina_regen += 4
        self.player.stamina = min(
            self.player.max_stamina, self.player.stamina + stamina_regen * dt
        )
        self.player.mana = min(self.player.max_mana, self.player.mana + mana_regen * dt)

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
            # using a steady dt-based rate so the run cycle stays smooth even
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

    def advance_animation_phases(self, dt: float) -> None:
        # Base cadence remains clamped by actor type, then the runtime movement
        # multiplier follows analog input, status effects, and Time Skip. This
        # keeps authored footsteps synchronized when simulation speed changes
        # without making naturally slow enemy archetypes freeze between frames.
        if self.player.moving:
            speed = min(
                WALK_ANIM_SPEED_CEIL,
                self._anim_speed(PLAYER_MOVE_SPEED)
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
                    self._anim_speed(enemy.speed)
                    * max(
                        WALK_ANIM_RUNTIME_SCALE_FLOOR,
                        enemy.locomotion_anim_scale,
                    ),
                )
                enemy.anim_time += dt * WALK_ANIMATION_RATE * speed

    @staticmethod
    def _anim_speed(speed: float) -> float:
        if speed < WALK_ANIM_SPEED_FLOOR:
            return WALK_ANIM_SPEED_FLOOR
        if speed > WALK_ANIM_SPEED_CEIL:
            return WALK_ANIM_SPEED_CEIL
        return speed

    def actor_hit_radius(self, actor: Player | Enemy) -> float:
        if isinstance(actor, Player):
            return PLAYER_HIT_RADIUS
        return self.enemy_hit_radius(actor)

    def enemy_hit_radius(self, enemy: Enemy) -> float:
        if enemy.size >= 2:
            return BOSS_FOOTPRINT_HIT_RADIUS
        if enemy.kind == "boss":
            return BOSS_HIT_RADIUS
        if enemy.name in ("Gate Warden", "Crypt Brute"):
            return LARGE_ENEMY_HIT_RADIUS
        return ENEMY_HIT_RADIUS

    def contact_distance(self, enemy: Enemy) -> float:
        return PLAYER_HIT_RADIUS + self.enemy_hit_radius(enemy)

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
            if enemy.telegraph == "lured":
                enemy.telegraph = ""
            enemy.attack_timer = max(0.0, enemy.attack_timer - scaled_dt)
            player_dx = self.player.x - enemy.x
            player_dy = self.player.y - enemy.y
            player_distance = math.hypot(player_dx, player_dy)
            lure = self.ambush_bell_lure_target(enemy)
            if player_distance > enemy.aggro_range and lure is None:
                continue
            if enemy.statuses.get("stunned", 0.0) > 0:
                enemy.telegraph = "stunned"
                continue

            target_x = lure.x if lure is not None else self.player.x
            target_y = lure.y if lure is not None else self.player.y
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
            attack_los_x, attack_los_y = enemy.x, enemy.y
            has_los = (
                attack_ready
                and attack_in_range
                and self.dungeon.line_of_sight(
                    enemy.x, enemy.y, self.player.x, self.player.y
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
                        self.enemy_cast(
                            enemy,
                            player_nx,
                            player_ny,
                            line_of_sight_confirmed=(
                                enemy.x == attack_los_x and enemy.y == attack_los_y
                            ),
                        )
                    else:
                        self.enemy_melee(
                            enemy,
                            line_of_sight_confirmed=(
                                enemy.x == attack_los_x and enemy.y == attack_los_y
                            ),
                        )
                continue

            if enemy.kind == "boss" or enemy.is_boss_encounter:
                # 4-tile boss encounters (final tyrant + floor guardians) use the
                # same pressure pattern: close the gap, cast a bolt fan at mid
                # range, and crush with melee up close.
                if distance > enemy.attack_range:
                    step = min(
                        move_speed * dt, distance - enemy.attack_range
                    )
                    self._move_enemy_locomotion(
                        enemy, nx * step, ny * step, dt, locomotion_scale
                    )
                if 2.0 < distance <= 6.0 and attack_ready and has_los:
                    self.enemy_cast(
                        enemy,
                        nx,
                        ny,
                        line_of_sight_confirmed=(
                            enemy.x == attack_los_x and enemy.y == attack_los_y
                        ),
                    )
                elif distance <= enemy.attack_range and attack_ready and has_los:
                    self.enemy_melee(
                        enemy,
                        line_of_sight_confirmed=(
                            enemy.x == attack_los_x and enemy.y == attack_los_y
                        ),
                    )
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
                    self.enemy_cast(
                        enemy,
                        nx,
                        ny,
                        line_of_sight_confirmed=(
                            enemy.x == attack_los_x and enemy.y == attack_los_y
                        ),
                    )
            else:
                if distance > enemy.attack_range:
                    step = min(
                        move_speed * dt, distance - enemy.attack_range
                    )
                    self._move_enemy_locomotion(
                        enemy, nx * step, ny * step, dt, locomotion_scale
                    )
                elif attack_ready and has_los:
                    self.enemy_melee(enemy, line_of_sight_confirmed=True)

    def enemy_melee(
        self, enemy: Enemy, *, line_of_sight_confirmed: bool = False
    ) -> None:
        if not line_of_sight_confirmed:
            distance = math.hypot(enemy.x - self.player.x, enemy.y - self.player.y)
            if distance > enemy.attack_range or not self.dungeon.line_of_sight(
                enemy.x, enemy.y, self.player.x, self.player.y
            ):
                return
        enemy.attack_timer = enemy.attack_cooldown
        enemy.telegraph = "melee"
        raw = enemy.damage + self.rng.randrange(-2, 3)
        amount = self.take_player_damage(
            raw, source="melee", damage_type=enemy.damage_type, attacker=enemy
        )
        if enemy.damage_type == "poison" and amount > 0:
            self.set_player_status("poisoned", 1.4)
        elif enemy.damage_type == "frost" and amount > 0:
            self.set_player_status("chilled", 0.9)
        self.floaters.append(
            FloatingText(
                f"-{amount}",
                self.player.x,
                self.player.y - 0.2,
                self.damage_type_color(enemy.damage_type),
            )
        )
        self.slashes.append(
            (
                (enemy.x + self.player.x) * 0.5,
                (enemy.y + self.player.y) * 0.5,
                0.14,
                enemy.facing_x,
                enemy.facing_y,
            )
        )
        self.add_impact(
            (enemy.x + self.player.x) * 0.5,
            (enemy.y + self.player.y) * 0.5,
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
            distance = math.hypot(enemy.x - self.player.x, enemy.y - self.player.y)
            cast_range = (
                max(6.0, enemy.attack_range)
                if enemy.kind == "boss" or enemy.is_boss_encounter
                else enemy.attack_range
            )
            if distance > cast_range or not self.dungeon.line_of_sight(
                enemy.x, enemy.y, self.player.x, self.player.y
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

    def update_projectiles(self, dt: float) -> None:
        kept: list[Projectile] = []
        for projectile in self.projectiles:
            # Milestone 3.7 — homing bolts (e.g. Arc Tyrant / Sky Quiver
            # capstones) steer toward the nearest enemy before moving.
            if projectile.owner == "player" and projectile.homing > 0.0:
                self._steer_homing_projectile(projectile, dt)
            if not projectile.update(dt, self.dungeon):
                continue
            # Carry one small moving light per live projectile. Refreshing the
            # same source preserves the leading glow and lets it decay after the
            # projectile dies, without accumulating eight or more overlapping
            # light-buffer stamps along every flight path.
            projectile_light = projectile.light_source
            if projectile_light is None or not projectile_light.alive:
                projectile_light = self.add_light(
                    projectile.x,
                    projectile.y,
                    LIGHT_PROJECTILE_RADIUS,
                    projectile.color,
                    intensity=LIGHT_PROJECTILE_INTENSITY,
                    ttl=LIGHT_PROJECTILE_TTL,
                    kind="projectile",
                )
                projectile.light_source = projectile_light
            else:
                projectile_light.x = projectile.x
                projectile_light.y = projectile.y
                projectile_light.color = projectile.color
                projectile_light.ttl = LIGHT_PROJECTILE_TTL
                projectile_light.max_ttl = LIGHT_PROJECTILE_TTL
            if projectile.owner == "player":
                hit = self.first_enemy_near(
                    projectile.x, projectile.y, PLAYER_PROJECTILE_HIT_RADIUS
                )
                if hit is not None and id(hit) not in projectile.hit_enemies:
                    self.add_impact(
                        projectile.x,
                        projectile.y,
                        projectile.color,
                        ttl=0.32,
                        radius=0.38,
                        kind="burst",
                    )
                    self.damage_enemy(
                        hit,
                        projectile.damage,
                        knockback_from=(projectile.vx, projectile.vy),
                        damage_type=projectile.damage_type,
                        status_effect=projectile.status_effect,
                        status_duration=projectile.status_duration,
                    )
                    # Acolyte Spirit Bolt siphons life when the Blood path is
                    # committed, using the same ramp as Spirit Call familiars.
                    if projectile.archetype == "Acolyte":
                        leech = self._acolyte_spell_leech()
                        if leech:
                            self.player.hp = min(
                                self.player.max_hp, self.player.hp + leech
                            )
                    # Milestone 3.7 — Storm-path chain lightning arcs from
                    # the struck foe to a nearby second target.
                    self._maybe_chain_lightning(projectile, hit)
                    projectile.hit_enemies.add(id(hit))
                    if projectile.pierce > 0:
                        projectile.pierce -= 1
                        # Piercing bolts deal reduced damage to subsequent foes.
                        projectile.damage = max(1, int(projectile.damage * 0.7))
                        kept.append(projectile)
                        continue
                    continue
            else:
                # A summoner's familiars bodyguard their owner by intercepting
                # enemy bolts that pass near them. This path is skipped when no
                # Acolyte spirit or Ranger Spirit Beast is active.
                if self.familiars:
                    struck = None
                    for familiar in self.familiars:
                        dx = projectile.x - familiar.x
                        dy = projectile.y - familiar.y
                        if (
                            dx * dx + dy * dy
                            < ENEMY_PROJECTILE_HIT_RADIUS
                            * ENEMY_PROJECTILE_HIT_RADIUS
                            and self.dungeon.line_of_sight(
                                projectile.x,
                                projectile.y,
                                familiar.x,
                                familiar.y,
                            )
                        ):
                            struck = familiar
                            break
                    if struck is not None:
                        self._familiar_take_damage(struck, projectile.damage, None)
                        self.floaters.append(
                            FloatingText(
                                f"-{max(1, projectile.damage // 2)}",
                                struck.x,
                                struck.y - 0.2,
                                (235, 90, 80),
                                ttl=0.55,
                            )
                        )
                        self.add_impact(
                            projectile.x,
                            projectile.y,
                            projectile.color,
                            ttl=0.34,
                            radius=0.42,
                            kind="burst",
                        )
                        continue
                player_dx = projectile.x - self.player.x
                player_dy = projectile.y - self.player.y
                if (
                    player_dx * player_dx + player_dy * player_dy
                    < ENEMY_PROJECTILE_HIT_RADIUS * ENEMY_PROJECTILE_HIT_RADIUS
                    and self.dungeon.line_of_sight(
                        projectile.x,
                        projectile.y,
                        self.player.x,
                        self.player.y,
                    )
                ):
                    amount = self.take_player_damage(
                        projectile.damage,
                        source="projectile",
                        damage_type=projectile.damage_type,
                    )
                    if projectile.status_effect == "chilled" and amount > 0:
                        self.set_player_status("chilled", projectile.status_duration)
                    self.floaters.append(
                        FloatingText(
                            f"-{amount}",
                            self.player.x,
                            self.player.y - 0.2,
                            (235, 90, 80),
                        )
                    )
                    self.add_impact(
                        projectile.x,
                        projectile.y,
                        projectile.color,
                        ttl=0.34,
                        radius=0.42,
                        kind="burst",
                    )
                    continue
            kept.append(projectile)
        self.projectiles = kept

    def _steer_homing_projectile(self, projectile: Projectile, dt: float) -> None:
        """Gently turn a homing projectile toward the nearest enemy.

        Cheap O(enemies) per homing bolt; homing bolts are rare (capstone-only)
        so this stays off the hot path for builds that did not pick the seeking
        capstone.
        """
        nearest = None
        best_distance_squared = 6.5 * 6.5
        for enemy in self.enemies:
            dx = enemy.x - projectile.x
            dy = enemy.y - projectile.y
            distance_squared = dx * dx + dy * dy
            if distance_squared < best_distance_squared:
                best_distance_squared = distance_squared
                nearest = enemy
        if nearest is None:
            return
        speed = math.hypot(projectile.vx, projectile.vy)
        if speed < 0.001:
            return
        desired_x = nearest.x - projectile.x
        desired_y = nearest.y - projectile.y
        desired_len = math.hypot(desired_x, desired_y)
        if desired_len < 0.001:
            return
        turn = projectile.homing * dt * 6.0
        cur_dx = projectile.vx / speed
        cur_dy = projectile.vy / speed
        new_dx = cur_dx + (desired_x / desired_len - cur_dx) * turn
        new_dy = cur_dy + (desired_y / desired_len - cur_dy) * turn
        new_len = math.hypot(new_dx, new_dy)
        if new_len > 0.001:
            new_dx /= new_len
            new_dy /= new_len
        projectile.vx = new_dx * speed
        projectile.vy = new_dy * speed

    def _maybe_chain_lightning(self, projectile: Projectile, primary: Enemy) -> None:
        """Storm-path chain lightning: arc from a struck foe to a neighbour.

        Triggered by the Arcanist Storm path (arcanist_chain_lightning and
        deeper). The chain hits one extra foe near the primary for partial
        damage, giving the Storm path a distinct bolt behavior versus the Bolt
        path's pierce/homing.
        """
        if not self.player.has_upgrade("arcanist_chain_lightning"):
            return
        if projectile.owner != "player":
            return
        best = None
        best_distance_squared = 2.6 * 2.6
        for enemy in self.enemies:
            if enemy is primary or id(enemy) in projectile.hit_enemies:
                continue
            dx = enemy.x - primary.x
            dy = enemy.y - primary.y
            distance_squared = dx * dx + dy * dy
            if distance_squared < best_distance_squared and self.dungeon.line_of_sight(
                primary.x, primary.y, enemy.x, enemy.y
            ):
                best_distance_squared = distance_squared
                best = enemy
        if best is None:
            return
        chain_damage = max(1, int(projectile.damage * 0.6))
        self.add_impact(
            best.x, best.y, projectile.color, ttl=0.22, radius=0.3, kind="burst"
        )
        self.damage_enemy(
            best,
            chain_damage,
            knockback_from=(best.x - primary.x, best.y - primary.y),
            damage_type=projectile.damage_type,
            status_effect=projectile.status_effect,
            status_duration=projectile.status_duration * 0.7,
        )
        projectile.hit_enemies.add(id(best))

    def _acolyte_melee_leech(self) -> int:
        # Milestone 3.7 refinement: ramp one step per Blood degree; 0 until Blood
        # is committed.
        if self.player.has_upgrade("acolyte_sanguine_ascendant"):
            return 6
        if self.player.has_upgrade("acolyte_crimson_maw"):
            return 5
        if self.player.has_upgrade("acolyte_blood_pact"):
            return 4
        if self.player.has_upgrade("acolyte_gravebind"):
            return 3
        if self.player.has_upgrade("acolyte_sanguine"):
            return 2
        if self.equipment_skill_bonus("Blood leech"):
            return 1
        return 0

    def _acolyte_spell_leech(self) -> int:
        # Blood-path spell leech ramps one step per Blood degree (0 until Blood
        # is committed) and applies to Spirit Bolt and Spirit Call familiar hits.
        if self.player.has_upgrade("acolyte_sanguine_ascendant"):
            return 8
        if self.player.has_upgrade("acolyte_crimson_maw"):
            return 7
        if self.player.has_upgrade("acolyte_blood_pact"):
            return 5
        if self.player.has_upgrade("acolyte_gravebind"):
            return 4
        if self.player.has_upgrade("acolyte_sanguine"):
            return 3
        if self.equipment_skill_bonus("Blood leech"):
            return 1
        return 0

    def update_traps(self, _dt: float) -> None:
        for trap in self.traps:
            if not trap.active:
                continue
            if math.hypot(trap.x - self.player.x, trap.y - self.player.y) > 0.55:
                continue
            trap.active = False
            amount = self.take_player_damage(trap.damage, source="trap")
            self.run_stats.traps_triggered += 1
            self.floaters.append(
                FloatingText(
                    f"{trap.kind}! -{amount}",
                    self.player.x,
                    self.player.y - 0.2,
                    (245, 95, 70),
                    ttl=1.2,
                )
            )
            self.add_impact(
                trap.x, trap.y, (245, 95, 70), ttl=0.46, radius=0.58, kind="burst"
            )
            self.play_sfx("trap")

    def player_melee_attack(self) -> None:
        stamina_cost = self.melee_stamina_cost()
        if self.player.melee_timer > 0 or self.player.stamina < stamina_cost:
            return
        self.player.melee_timer = self.melee_cooldown()
        self.player.stamina -= stamina_cost
        self.set_player_action_visual("attack", 0.20)
        target = self.enemy_in_melee_arc()
        if target:
            tx = (self.player.x + target.x) * 0.5
            ty = (self.player.y + target.y) * 0.5
        else:
            tx = self.player.x + self.player.facing_x * 0.9
            ty = self.player.y + self.player.facing_y * 0.9
        self.slashes.append((tx, ty, 0.18, self.player.facing_x, self.player.facing_y))
        if target:
            targets = [target]
            if self.player.class_name == "Warden":
                # Milestone 3.7 — base Shield Bash hits a single foe; the
                # Bulwark path's first discipline unlocks the cleave arc so the
                # path choice changes how melee plays, not just its damage.
                if self.player.has_upgrade("warden_bulwark_ward"):
                    targets = self.enemies_in_melee_arc(reach_bonus=0.35)[:4]
                elif self.player.has_upgrade("warden_aegis"):
                    targets = self.enemies_in_melee_arc(reach_bonus=0.28)[:3]
                elif self.player.has_upgrade("warden_bulwark"):
                    targets = self.enemies_in_melee_arc(reach_bonus=0.22)[:2]
                else:
                    targets = [target]
            for index, enemy in enumerate(list(targets)):
                damage = self.player.melee_damage() + self.rng.randrange(-3, 5)
                damage_type = self.weapon_damage_type()
                status_effect = ""
                status_duration = 0.0
                if self.equipment_skill_bonus("Melee"):
                    damage += 2
                if index > 0:
                    damage = max(1, int(damage * 0.62))
                # Milestone 3.7 — Rogue crits are gated behind the Precision
                # path; base backstabs never crit, so committing to Precision
                # feels essential to the crit playstyle.
                if self.player.has_upgrade("rogue_deathmark"):
                    crit_chance = 0.40
                    crit_mult = 2.25
                elif self.player.has_upgrade("rogue_crimson_edge"):
                    crit_chance = 0.34
                    crit_mult = 2.10
                elif self.player.has_upgrade("rogue_executioner"):
                    crit_chance = 0.28
                    crit_mult = 1.95
                elif self.player.has_upgrade("rogue_venom"):
                    crit_chance = 0.20
                    crit_mult = 1.75
                elif self.player.has_upgrade("rogue_precision"):
                    crit_chance = 0.15
                    crit_mult = 1.60
                else:
                    crit_chance = 0.0
                    crit_mult = 1.0
                rogue_crit = (
                    self.player.class_name == "Rogue"
                    and self.rng.random() < crit_chance
                )
                if (
                    not rogue_crit
                    and self.equipped_unique_effect("smoke crits")
                    and self.player_status("smoke") > 0
                    and self.rng.random() < 0.30
                ):
                    rogue_crit = True
                    crit_mult = 1.80
                    status_effect = "poisoned"
                    status_duration = 1.4
                    self.floaters.append(
                        FloatingText(
                            "Smoke Crit", enemy.x, enemy.y - 0.45, (255, 225, 120)
                        )
                    )
                if rogue_crit:
                    damage = int(damage * crit_mult)
                    status_effect = "poisoned"
                    status_duration = (
                        2.2 if self.player.has_upgrade("rogue_venom") else 1.2
                    )
                    self.floaters.append(
                        FloatingText(
                            "Critical", enemy.x, enemy.y - 0.45, (255, 225, 120)
                        )
                    )
                if self.player.class_name == "Warden":
                    enemy.attack_timer = max(enemy.attack_timer, 0.35)
                    if self.player.has_upgrade("warden_aegis"):
                        damage_type = "holy"
                        status_effect = "stunned"
                        status_duration = 0.35
                elif self.player.class_name == "Arcanist" and self.player.has_upgrade(
                    "arcanist_permafrost"
                ):
                    status_effect = "chilled"
                    status_duration = 1.0
                elif self.player.class_name == "Acolyte" and self.player.has_upgrade(
                    "acolyte_gravebind"
                ):
                    status_effect = "bound"
                    status_duration = 1.1
                elif self.player.class_name == "Ranger" and self.player.has_upgrade(
                    "ranger_beastmark"
                ):
                    status_effect = "snared"
                    status_duration = 1.15
                damage = self.apply_story_player_damage(damage)
                self.damage_enemy(
                    enemy,
                    damage,
                    knockback_from=(self.player.facing_x, self.player.facing_y),
                    damage_type=damage_type,
                    status_effect=status_effect,
                    status_duration=status_duration,
                )
                if self.player.class_name == "Acolyte":
                    # Milestone 3.7 — Blood Rite's leech is gated behind the
                    # Blood path; base melee drains nothing until the Acolyte
                    # commits to Blood.
                    leech = self._acolyte_melee_leech()
                    if leech:
                        self.player.hp = min(self.player.max_hp, self.player.hp + leech)

    def player_cast_bolt(self) -> None:
        mana_cost = self.bolt_mana_cost()
        if self.player.bolt_timer > 0 or self.player.mana < mana_cost:
            return
        self.player.bolt_timer = self.bolt_cooldown()
        self.player.mana -= mana_cost
        self.set_player_action_visual("cast", 0.24)
        self.add_impact(
            self.player.x,
            self.player.y,
            self.skill_color(),
            ttl=0.28,
            radius=0.34,
            kind="cast",
            archetype=self.player.class_name,
        )
        damage_type = self.bolt_damage_type()
        damage = 14 + self.player.level * 2 + self.player.spell_bonus
        if self.equipment_skill_bonus("Bolt"):
            damage += 2
        if self.player.class_name == "Acolyte":
            damage += max(0, self.player.max_hp - self.player.hp) // 12
        damage = self.apply_story_player_damage(damage, spell=True)
        self.apply_story_blood_price("bolt")
        angles = [0.0]
        # Milestone 3.7 refinement — the bolt ability is a single shot by
        # default and gains one projectile per path degree rather than jumping
        # straight to a full fan, so each upgrade feels like a step.
        if self.player.class_name == "Ranger":
            if self.player.has_upgrade("ranger_storm_volley"):
                angles = [-0.28, -0.12, 0.0, 0.12, 0.28]  # 5-arrow storm cone
            elif self.player.has_upgrade("ranger_rapid"):
                angles = [-0.20, -0.06, 0.06, 0.20]  # 4 arrows (extra arrow)
            elif self.player.has_upgrade("ranger_volley"):
                angles = [-0.16, 0.0, 0.16]  # 3-arrow fan
            else:
                angles = [0.0]  # 1 arrow
        elif self.player.class_name == "Arcanist":
            if self.player.has_upgrade("arcanist_overload"):
                angles = [-0.12, 0.0, 0.12]  # 3 bolts (split on impact)
            elif self.player.has_upgrade("arcanist_splinter"):
                angles = [-0.06, 0.06]  # 2 bolts (one extra shard)
            else:
                angles = [0.0]  # 1 bolt
        if self.equipment_skill_bonus("Bolt") and len(angles) < 5:
            angles = sorted({*angles, -0.18, 0.18})
        if self.equipped_unique_effect("splinter storm") and len(angles) < 5:
            angles = sorted({*angles, -0.10, 0.10})
        if self.equipped_unique_effect("sky volley") and len(angles) < 5:
            angles = sorted({*angles, -0.22, 0.22})
        status_effect = ""
        status_duration = 0.0
        if damage_type == "poison" or self.player.has_upgrade("rogue_venom"):
            status_effect = "poisoned"
            status_duration = 2.0
        elif damage_type == "frost" or self.player.has_upgrade("arcanist_permafrost"):
            status_effect = "chilled"
            status_duration = 1.4
        elif self.player.has_upgrade("acolyte_gravebind"):
            status_effect = "bound"
            status_duration = 1.2
        elif self.player.has_upgrade("ranger_snare"):
            status_effect = "snared"
            status_duration = 1.1
        # Milestone 3.7 refinement — path-progression projectile mechanics
        # ramp one step per degree. Bolt path (Arcanist): pierce climbs 0->1->2
        # and the capstone adds homing. Volley path (Ranger): piercing unlocks
        # at the piercing degree and the capstone adds homing.
        pierce = 0
        homing = 0.0
        if self.player.class_name == "Arcanist":
            if self.player.has_upgrade("arcanist_pierce"):
                pierce = 2
            elif self.player.has_upgrade("arcanist_overload"):
                pierce = 1
            if self.player.has_upgrade("arcanist_arc_tyrant"):
                homing = 0.85
        elif self.player.class_name == "Ranger":
            if self.player.has_upgrade("ranger_piercing_volley"):
                pierce = 1
            if self.player.has_upgrade("ranger_sky_quiver"):
                homing = 0.75
        if self.equipment_skill_bonus("Bolt pierce"):
            pierce = max(pierce, 1)
        for angle in angles:
            dx = self.player.facing_x * math.cos(
                angle
            ) - self.player.facing_y * math.sin(angle)
            dy = self.player.facing_x * math.sin(
                angle
            ) + self.player.facing_y * math.cos(angle)
            self.projectiles.append(
                Projectile(
                    self.player.x,
                    self.player.y,
                    dx * 9.0,
                    dy * 9.0,
                    damage if abs(angle) <= 0.001 else max(1, damage - 4),
                    "player",
                    self.damage_type_color(damage_type),
                    ttl=1.55 if self.player.has_upgrade("arcanist_splinter") else 1.4,
                    damage_type=damage_type,
                    status_effect=status_effect,
                    status_duration=status_duration,
                    pierce=pierce,
                    homing=homing,
                    archetype=self.player.class_name,
                )
            )

    def player_cast_nova(self) -> None:
        if self.player.class_name != "Arcanist":
            return
        mana_cost = self.class_skill_mana_cost()
        if self.player.class_skill_timer > 0 or self.player.mana < mana_cost:
            return
        self.player.class_skill_timer = self.class_skill_cooldown()
        self.player.mana -= mana_cost
        self.set_player_action_visual("cast", 0.32)
        self.add_impact(
            self.player.x,
            self.player.y,
            self.skill_color(),
            ttl=0.48,
            radius=0.82,
            kind="cast",
            archetype=self.player.class_name,
        )
        self.apply_story_blood_price("nova")
        hits = 0
        for enemy in list(self.enemies):
            dx = enemy.x - self.player.x
            dy = enemy.y - self.player.y
            distance = math.hypot(dx, dy)
            radius = 2.45
            # Milestone 3.7 refinement - Frost Nova radius ramps one step per
            # Nova degree so each pick reaches farther, instead of one big jump.
            if self.player.has_upgrade("arcanist_absolute_zero"):
                radius += 1.05
            elif self.player.has_upgrade("arcanist_blizzard"):
                radius += 0.85
            elif self.player.has_upgrade("arcanist_glacial"):
                radius += 0.65
            elif self.player.has_upgrade("arcanist_permafrost"):
                radius += 0.45
            elif self.player.has_upgrade("arcanist_focus"):
                radius += 0.25
            if self.equipment_class_skill_bonus():
                radius += 0.25
            if self.equipment_class_skill_bonus("Nova radius"):
                radius += 0.35
            if distance <= radius and self.dungeon.line_of_sight(
                self.player.x, self.player.y, enemy.x, enemy.y
            ):
                hits += 1
                damage = (
                    10
                    + self.player.level * 2
                    + self.player.spell_bonus
                    + self.rng.randrange(0, 5)
                )
                damage_type = self.nova_damage_type()
                status_effect = "chilled"
                status_duration = (
                    1.9 if self.player.has_upgrade("arcanist_permafrost") else 1.2
                )
                if self.equipment_class_skill_bonus():
                    damage += 2
                damage = self.apply_story_player_damage(damage, spell=True)
                direction = (
                    (dx / distance, dy / distance)
                    if distance > 0.001
                    else (self.player.facing_x, self.player.facing_y)
                )
                self.damage_enemy(
                    enemy,
                    damage,
                    knockback_from=direction,
                    damage_type=damage_type,
                    status_effect=status_effect,
                    status_duration=status_duration,
                )
        self.floaters.append(
            FloatingText(
                f"{self.skill_names()[2]}{f' x{hits}' if hits else ''}",
                self.player.x,
                self.player.y - 0.5,
                self.skill_color(),
                ttl=0.9,
            )
        )

    def player_cast_time_skip(self) -> None:
        """Warden class skill: slow time for all enemies without affecting the player.

        Spends the shared class-skill mana cost / cooldown so the action bar
        stays balanced, then opens a timed window during which the enemy
        simulation (movement + attack cadence) runs at ``time_skip_factor``
        speed. The player's own timers, movement, and attacks are untouched.
        """
        if self.player.class_name != "Warden":
            return
        mana_cost = self.class_skill_mana_cost()
        if self.player.class_skill_timer > 0 or self.player.mana < mana_cost:
            return
        self.player.class_skill_timer = self.class_skill_cooldown()
        self.player.mana -= mana_cost
        self.player.time_skip_timer = self.time_skip_duration()
        self.set_player_action_visual("cast", 0.32)
        self.add_impact(
            self.player.x,
            self.player.y,
            self.skill_color(),
            ttl=0.62,
            radius=3.2,
            kind="cast",
            archetype=self.player.class_name,
        )
        self.apply_story_blood_price("time skip")
        # Milestone 3.18.1 — Time path Degree 2 (Time Skip node): the cast pulse
        # briefly staggers foes caught in the ring, repurposing the old
        # Bulwark Wave knockback fantasy as a holy cast-time stun.
        if self.player.has_upgrade("warden_bulwark_wave"):
            stagger_radius = 2.6
            for enemy in list(self.enemies):
                if not enemy.alive:
                    continue
                if (
                    math.hypot(enemy.x - self.player.x, enemy.y - self.player.y)
                    <= stagger_radius
                    and self.dungeon.line_of_sight(
                        self.player.x, self.player.y, enemy.x, enemy.y
                    )
                ):
                    # Stagger only: apply a brief holy stun and stall the
                    # next attack, without dealing damage or triggering on-hit
                    # procs/lifesteal (Time Skip is a control skill).
                    self.apply_enemy_status(enemy, "stunned", 0.35)
                    enemy.attack_timer = max(enemy.attack_timer, 0.45)
        self.floaters.append(
            FloatingText(
                self.skill_names()[2],
                self.player.x,
                self.player.y - 0.5,
                self.skill_color(),
                ttl=0.9,
            )
        )

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
            enemy,
            amount,
            knockback_from=direction,
            damage_type="physical",
            status_effect=status_effect,
            status_duration=status_duration,
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

    # ------------------------------------------------------------------
    # Persistent familiar system — Acolyte Spirit Call and Ranger Spirit Beast.
    # ------------------------------------------------------------------
    FAMILIAR_BASE_HP = 20
    FAMILIAR_BASE_DAMAGE = 6
    FAMILIAR_BASE_SPEED = 3.2
    FAMILIAR_ATTACK_RANGE = 1.25
    FAMILIAR_ATTACK_COOLDOWN = 0.85
    FAMILIAR_AGGRO_RANGE = 7.0
    FAMILIAR_FOLLOW_DISTANCE = 1.6
    FAMILIAR_ATTACK_ANIMATION_DURATION = 0.42

    SPIRIT_BEAST_BASE_HP = 60
    SPIRIT_BEAST_BASE_DAMAGE = 12
    SPIRIT_BEAST_BASE_SPEED = 3.55
    SPIRIT_BEAST_ATTACK_COOLDOWN = 0.86
    SPIRIT_BEAST_AGGRO_RANGE = 8.0
    SPIRIT_BEAST_FOLLOW_DISTANCE = 1.8
    SPIRIT_BEAST_RETURN_DISTANCE = 0.9
    SPIRIT_BEAST_COLLISION_RADIUS = 0.24

    def familiar_max_count(self) -> int:
        """How many familiars Spirit Call maintains at once.

        Base 1, +1 from ``acolyte_bone_legion`` (Degree 3), +1 from
        ``acolyte_legion_eternal`` (Degree 5 capstone). Committing deeper into Spirit
        visibly grows the host rather than just inflating stats.
        """
        count = 1
        if self.player.has_upgrade("acolyte_bone_legion"):
            count += 1
        if self.player.has_upgrade("acolyte_legion_eternal"):
            count += 1
        return count

    def familiar_stats(self) -> tuple[int, int]:
        """Return ``(max_hp, damage)`` for a freshly summoned familiar.

        Scales with Spirit path investment so each pick is felt:
          * ``acolyte_spirit_call`` (Degree 1) — the core summoning discipline — grows the
            familiar (HP + damage) and unlocks the medium sprite variant.
          * ``acolyte_wraith_host`` (Degree 2) — HP + persistence (lifesteal moved to
            the Blood path in 3.18.4).
          * ``acolyte_bone_legion`` (Degree 3) — damage.
          * ``acolyte_wraith_lord`` (Degree 4) — champion: large sprite, HP + damage,
            taunts foes.
          * ``acolyte_legion_eternal`` (Degree 5) — unkillable (regenerates, HP
            floors at 1).
        """
        hp = self.FAMILIAR_BASE_HP
        damage = self.FAMILIAR_BASE_DAMAGE
        if self.player.has_upgrade("acolyte_spirit_call"):
            hp += 12
            damage += 2
        if self.player.has_upgrade("acolyte_wraith_host"):
            hp += 10
        if self.player.has_upgrade("acolyte_bone_legion"):
            damage += 2
        if self.player.has_upgrade("acolyte_wraith_lord"):
            hp += 24
            damage += 4
        if self.player.has_upgrade("acolyte_legion_eternal"):
            hp += 16
        return hp, damage

    def spirit_beast_stats(self) -> tuple[int, int, float, float]:
        """Return the Spirit Beast's HP, damage, speed, and attack cooldown.

        Every Beast discipline changes at least one familiar stat. The explicit
        steps make Beast Bond immediately meaningful and keep deeper Beast picks
        relevant without coupling the beast to the Ranger's already-large player
        stat bonuses.
        """
        hp = self.SPIRIT_BEAST_BASE_HP
        damage = self.SPIRIT_BEAST_BASE_DAMAGE
        speed = self.SPIRIT_BEAST_BASE_SPEED
        attack_cooldown = self.SPIRIT_BEAST_ATTACK_COOLDOWN
        if self.player.has_upgrade("ranger_beast_bond"):
            hp += 14
            damage += 2
        if self.player.has_upgrade("ranger_pack_tactics"):
            hp += 8
            damage += 2
            attack_cooldown -= 0.08
        if self.player.has_upgrade("ranger_alpha"):
            hp += 18
            damage += 3
            speed += 0.15
        if self.player.has_upgrade("ranger_spirit_companion"):
            hp += 14
            damage += 3
            speed += 0.10
            attack_cooldown -= 0.05
        if self.player.has_upgrade("ranger_primal_lord"):
            hp += 24
            damage += 4
            speed += 0.10
            attack_cooldown -= 0.07
        if self.equipment_class_skill_bonus():
            hp += 12
            damage += 2
        return hp, damage, speed, max(0.52, attack_cooldown)

    def _refresh_active_spirit_beast(self) -> None:
        """Apply newly chosen Beast ranks to an already-summoned Spirit Beast."""
        if not getattr(self, "familiars", None):
            return
        max_hp, damage, speed, attack_cooldown = self.spirit_beast_stats()
        champion = self.player.has_upgrade("ranger_primal_lord")
        for familiar in self.familiars:
            if familiar.kind != "spirit_beast" or not familiar.alive:
                continue
            hp_gain = max(0, max_hp - familiar.max_hp)
            familiar.max_hp = max_hp
            familiar.hp = min(max_hp, familiar.hp + hp_gain)
            familiar.damage = damage
            familiar.speed = speed
            familiar.attack_cooldown = attack_cooldown
            familiar.champion = champion

    def familiar_variant_for_index(self, index: int) -> int:
        """Sprite state for the ``index``-th familiar in the current host.

        Two states: 0 = small wisp before any Spirit skill is chosen, 1 = big
        owl once the Acolyte has learned Spirit Call (``acolyte_spirit_call``).
        Deeper Spirit nodes (Owl Companion / Twin Owls / Owl Lord / Eternal
        Owls) scale stats and count but no longer change the silhouette —
        the big familiar is always the owl.
        """
        if self.player.has_upgrade("acolyte_spirit_call"):
            return 1
        return 0

    def familiar_is_champion(self, index: int) -> bool:
        return self.player.has_upgrade("acolyte_wraith_lord") and index == 0

    def familiar_damage_type(self, familiar: Familiar | None = None) -> str:
        if familiar is not None and familiar.kind == "spirit_beast":
            if self.player.has_upgrade("ranger_spirit_companion"):
                return "arcane"
            return "physical"
        # Summoned spirits deal shadow damage, matching the Acolyte's theme.
        return "shadow"

    def player_cast_spirit_call(self) -> None:
        """Acolyte class skill: summon / refresh the spirit familiar host.

        Spends the shared class-skill mana cost and cooldown
        (``class_skill_mana_cost`` / ``class_skill_cooldown``) so the action bar
        stays balanced. On cast, the host is always recreated fresh: any existing
        familiars are dismissed and a full ``familiar_max_count`` host is
        summoned in a small ring around the player, so the summon always snaps
        to the Acolyte's current position and picks up the latest build stats.
        The host persists until each familiar is killed or the floor is
        descended.
        """
        if self.player.class_name != "Acolyte":
            return
        mana_cost = self.class_skill_mana_cost()
        if self.player.class_skill_timer > 0 or self.player.mana < mana_cost:
            return
        self.player.class_skill_timer = self.class_skill_cooldown()
        self.player.mana -= mana_cost
        self.set_player_action_visual("cast", 0.32)
        self.add_impact(
            self.player.x,
            self.player.y,
            self.skill_color(),
            ttl=0.48,
            radius=0.82,
            kind="cast",
            archetype=self.player.class_name,
        )
        self.apply_story_blood_price("spirit call")
        max_count = self.familiar_max_count()
        max_hp, damage = self.familiar_stats()
        # Always recreate the host from scratch so Spirit Call snaps the
        # familiars to the Acolyte's current position and refreshes stats from
        # the latest build, instead of healing-in-place the old host.
        self.familiars.clear()
        for index in range(max_count):
            angle = (index / max(1, max_count)) * math.tau + 0.7
            offset = 0.9
            fx = self.player.x + math.cos(angle) * offset
            fy = self.player.y + math.sin(angle) * offset
            variant = self.familiar_variant_for_index(index)
            champion = self.familiar_is_champion(index)
            self.familiars.append(
                Familiar(
                    x=fx,
                    y=fy,
                    max_hp=max_hp,
                    hp=max_hp,
                    damage=damage,
                    speed=self.FAMILIAR_BASE_SPEED,
                    attack_range=self.FAMILIAR_ATTACK_RANGE,
                    attack_cooldown=self.FAMILIAR_ATTACK_COOLDOWN,
                    sprite_variant=variant,
                    lifesteal=self._acolyte_spell_leech() > 0,
                    unkillable=self.player.has_upgrade("acolyte_legion_eternal"),
                    champion=champion,
                    facing_x=self.player.facing_x,
                    facing_y=self.player.facing_y,
                )
            )
            self.add_impact(
                fx,
                fy,
                self.skill_color(),
                ttl=0.40,
                radius=0.46,
                kind="burst",
            )
        count = len(self.familiars)
        self.floaters.append(
            FloatingText(
                f"{self.skill_names()[2]} x{count}",
                self.player.x,
                self.player.y - 0.5,
                self.skill_color(),
                ttl=0.9,
            )
        )
        self.play_sfx("hit")

    def active_spirit_beast(self) -> Familiar | None:
        """Return the first living Ranger beast, ignoring dead pending-cull entries."""
        for familiar in self.familiars:
            if familiar.kind == "spirit_beast" and familiar.alive:
                return familiar
        return None

    def spirit_beast_next_command(self) -> str:
        """HUD label for the free command issued by the next class-skill press."""
        familiar = self.active_spirit_beast()
        if self.player.class_name != "Ranger" or familiar is None:
            return ""
        return "ATTACK" if familiar.command_mode == "follow" else "RETURN"

    def _command_spirit_beast(self, familiar: Familiar) -> None:
        """Alternate every living Spirit Beast between close return and attack modes."""
        command_mode = "attack" if familiar.command_mode == "follow" else "follow"
        for beast in self.familiars:
            if beast.kind != "spirit_beast" or not beast.alive:
                continue
            beast.command_mode = command_mode
            if command_mode == "follow":
                beast.attack_anim_timer = 0.0

        command_name = "Attack" if command_mode == "attack" else "Return"
        self.set_player_action_visual("cast", 0.18)
        self.add_impact(
            familiar.x,
            familiar.y,
            self.skill_color(),
            ttl=0.28,
            radius=0.34,
            kind="burst",
        )
        self.floaters.append(
            FloatingText(
                f"Spirit Beast: {command_name}",
                familiar.x,
                familiar.y - 0.45,
                self.skill_color(),
                ttl=0.75,
            )
        )
        self.play_sfx("hit")

    def _spirit_beast_spawn_position(self) -> tuple[float, float] | None:
        """Find a clear spawn connected to the Ranger by an unobstructed segment."""
        px, py = self.player.x, self.player.y
        collision_radius = self.SPIRIT_BEAST_COLLISION_RADIUS

        def valid(x: float, y: float) -> bool:
            dx = x - px
            dy = y - py
            return (
                dx * dx + dy * dy >= 0.45 * 0.45
                and not self.dungeon.blocked_for_radius(x, y, collision_radius)
                and self.dungeon.line_of_sight(px, py, x, y)
            )

        # Prefer a compact ring, then widen it. Sampling around the full circle
        # avoids the old fallback that could place the beast inside a nearby wall.
        angle_offsets = (
            0.0,
            math.pi / 4,
            -math.pi / 4,
            math.pi / 2,
            -math.pi / 2,
            3 * math.pi / 4,
            -3 * math.pi / 4,
            math.pi,
        )
        for distance in (0.9, 1.15, 0.65, 1.4):
            for angle_offset in angle_offsets:
                angle = 0.7 + angle_offset
                x = px + math.cos(angle) * distance
                y = py + math.sin(angle) * distance
                if valid(x, y):
                    return x, y

        # Corrupt or unusually cramped maps may reject the ring samples. Search
        # nearby floor centers, but never spend resources unless one is truly clear.
        tile_x = int(px)
        tile_y = int(py)
        for radius in range(1, 4):
            for offset_y in range(-radius, radius + 1):
                for offset_x in range(-radius, radius + 1):
                    if max(abs(offset_x), abs(offset_y)) != radius:
                        continue
                    x = tile_x + offset_x + 0.5
                    y = tile_y + offset_y + 0.5
                    if valid(x, y):
                        return x, y
        return None

    def player_cast_spirit_beast(self) -> None:
        """Command a living Spirit Beast, or summon one when absent and ready."""
        if self.player.class_name != "Ranger":
            return

        familiar = self.active_spirit_beast()
        if familiar is not None:
            # A living beast is never replaced or healed. Return/attack commands
            # are free and available regardless of the Ranger's current mana.
            self._command_spirit_beast(familiar)
            return

        mana_cost = self.class_skill_mana_cost()
        if self.player.class_skill_timer > 0 or self.player.mana < mana_cost:
            return
        spawn_position = self._spirit_beast_spawn_position()
        if spawn_position is None:
            return

        self._cull_dead_familiars()
        self.player.class_skill_timer = self.class_skill_cooldown()
        self.player.mana -= mana_cost
        self.set_player_action_visual("cast", 0.32)
        self.add_impact(
            self.player.x,
            self.player.y,
            self.skill_color(),
            ttl=0.48,
            radius=0.82,
            kind="spirit_beast_call",
            archetype=self.player.class_name,
        )
        self.apply_story_blood_price("spirit beast")

        max_hp, damage, speed, attack_cooldown = self.spirit_beast_stats()
        fx, fy = spawn_position
        self.familiars.clear()
        self.familiars.append(
            Familiar(
                x=fx,
                y=fy,
                max_hp=max_hp,
                hp=max_hp,
                damage=damage,
                speed=speed,
                attack_range=self.FAMILIAR_ATTACK_RANGE,
                attack_cooldown=attack_cooldown,
                sprite_variant=2,
                kind="spirit_beast",
                champion=self.player.has_upgrade("ranger_primal_lord"),
                facing_x=self.player.facing_x,
                facing_y=self.player.facing_y,
                command_mode="attack",
            )
        )
        self.add_impact(
            fx,
            fy,
            self.skill_color(),
            ttl=0.40,
            radius=0.46,
            kind="burst",
        )
        self.floaters.append(
            FloatingText(
                self.skill_names()[2],
                self.player.x,
                self.player.y - 0.5,
                self.skill_color(),
                ttl=0.9,
            )
        )
        self.play_sfx("hit")

    def update_familiars(self, dt: float) -> None:
        """Follow, perceive, and attack for each persistent familiar.

        Target selection is allocation-free and only accepts enemies with clear
        dungeon line of sight, so Spirit Beasts and spirits cannot perceive or bite
        through walls.
        """
        if not self.familiars:
            return
        for familiar in self.familiars:
            familiar.attack_timer = max(0.0, familiar.attack_timer - dt)
            familiar.attack_anim_timer = max(0.0, familiar.attack_anim_timer - dt)
            pet_cooldown = familiar.pet_cooldown - dt
            pet_anim_timer = familiar.pet_anim_timer - dt
            familiar.pet_cooldown = pet_cooldown if pet_cooldown > 1e-9 else 0.0
            familiar.pet_anim_timer = pet_anim_timer if pet_anim_timer > 1e-9 else 0.0
            familiar.moving = False

            # Petting is a short paired pose. Hold the beast in place and suppress
            # perception/attacks until the non-looping affection clip completes.
            if familiar.pet_anim_timer > 0.0:
                continue

            if familiar.kind == "spirit_beast" and familiar.command_mode == "follow":
                self._familiar_follow_player(familiar, dt)
                self._familiar_regen(familiar, dt)
                continue

            target = None
            aggro_range = (
                self.SPIRIT_BEAST_AGGRO_RANGE
                if familiar.kind == "spirit_beast"
                else self.FAMILIAR_AGGRO_RANGE
            )
            best_dist_sq = aggro_range * aggro_range
            for enemy in self.enemies:
                if not enemy.alive:
                    continue
                dx = enemy.x - familiar.x
                dy = enemy.y - familiar.y
                dist_sq = dx * dx + dy * dy
                if dist_sq >= best_dist_sq:
                    continue
                if not self.dungeon.line_of_sight(
                    familiar.x, familiar.y, enemy.x, enemy.y
                ):
                    continue
                best_dist_sq = dist_sq
                target = enemy

            if target is not None:
                dx = target.x - familiar.x
                dy = target.y - familiar.y
                dist = math.sqrt(best_dist_sq)
                if dist <= familiar.attack_range:
                    if dist > 0.001:
                        familiar.facing_x = dx / dist
                        familiar.facing_y = dy / dist
                    if familiar.attack_timer <= 0:
                        self._familiar_attack(familiar, target)
                elif dist > 0.001:
                    nx, ny = dx / dist, dy / dist
                    familiar.facing_x = nx
                    familiar.facing_y = ny
                    familiar.move_x = nx
                    familiar.move_y = ny
                    step = min(
                        familiar.speed * dt, dist - familiar.attack_range
                    )
                    moved = self._move_familiar(familiar, nx * step, ny * step)
                    self._advance_familiar_locomotion(familiar, moved, dt)
            else:
                self._familiar_follow_player(familiar, dt)

            self._familiar_regen(familiar, dt)
        self._cull_dead_familiars()

    def _familiar_follow_player(self, familiar: Familiar, dt: float) -> None:
        dx = self.player.x - familiar.x
        dy = self.player.y - familiar.y
        dist = math.hypot(dx, dy)
        if familiar.kind == "spirit_beast":
            follow_distance = (
                self.SPIRIT_BEAST_RETURN_DISTANCE
                if familiar.command_mode == "follow"
                else self.SPIRIT_BEAST_FOLLOW_DISTANCE
            )
        else:
            follow_distance = self.FAMILIAR_FOLLOW_DISTANCE
        if dist > follow_distance and dist > 0.001:
            nx, ny = dx / dist, dy / dist
            familiar.facing_x = nx
            familiar.facing_y = ny
            familiar.move_x = nx
            familiar.move_y = ny
            step = min(familiar.speed * dt, dist - follow_distance)
            moved = self._move_familiar(familiar, nx * step, ny * step)
            self._advance_familiar_locomotion(familiar, moved, dt)

    @staticmethod
    def _advance_familiar_locomotion(
        familiar: Familiar, distance: float, dt: float
    ) -> None:
        if distance <= 0.0:
            return
        familiar.moving = True
        # At full speed this advances one animation-second per simulation-second.
        # Smaller final approach/follow steps slow the paw cycle, with the same
        # low cadence floor used by player/enemy authored locomotion clips.
        full_step = max(0.001, familiar.speed * dt)
        movement_scale = max(
            WALK_ANIM_RUNTIME_SCALE_FLOOR,
            min(1.0, distance / full_step),
        )
        familiar.anim_time += dt * movement_scale

    def _move_familiar(self, familiar: Familiar, dx: float, dy: float) -> float:
        """Lightweight familiar locomotion and return actual distance moved.

        Familiars skip the shared ``move_actor`` path because that resolves
        contacts via ``enemy_hit_radius``, which assumes Enemy fields
        (``size``/``kind``/``name``). Instead we do a tight wall probe plus a
        soft separation from the player so the summon orbits the Acolyte
        rather than overlapping. Stays O(1) and allocation-free.
        """
        old_x, old_y = familiar.x, familiar.y
        radius = 0.22
        new_x = familiar.x + dx
        if not self.dungeon.blocked_for_radius(new_x, familiar.y, radius):
            familiar.x = new_x
        new_y = familiar.y + dy
        if not self.dungeon.blocked_for_radius(familiar.x, new_y, radius):
            familiar.y = new_y
        px_dx = familiar.x - self.player.x
        px_dy = familiar.y - self.player.y
        px_dist = math.hypot(px_dx, px_dy)
        min_dist = 0.45
        if 0.001 < px_dist < min_dist:
            nx, ny = px_dx / px_dist, px_dy / px_dist
            familiar.x += nx * (min_dist - px_dist)
            familiar.y += ny * (min_dist - px_dist)
        return math.hypot(familiar.x - old_x, familiar.y - old_y)

    def _familiar_attack(self, familiar: Familiar, enemy: Enemy) -> None:
        if not self.dungeon.line_of_sight(
            familiar.x, familiar.y, enemy.x, enemy.y
        ):
            return
        familiar.attack_timer = familiar.attack_cooldown
        familiar.attack_anim_timer = self.FAMILIAR_ATTACK_ANIMATION_DURATION
        damage = familiar.damage + self.rng.randrange(0, 3)
        damage_type = self.familiar_damage_type(familiar)
        if familiar.kind == "spirit_beast":
            if self.player.has_upgrade("ranger_pack_tactics") and enemy.statuses.get(
                "snared", 0.0
            ) > 0:
                damage = int(round(damage * 1.25))
            if self.player.has_upgrade("ranger_primal_lord") and (
                enemy.elite_modifier or enemy.kind in ("boss", "miniboss")
            ):
                damage = int(round(damage * 1.35))
            damage = self.mitigate_enemy_damage(enemy, damage, damage_type)
        # Familiars bypass player equipment procs and story damage modifiers;
        # their own discipline scaling is already reflected above.
        damage = max(1, damage)
        enemy.hp -= damage
        self._trigger_enemy_hit_flash(enemy)
        hit_color = self.damage_type_color(damage_type)
        self.floaters.append(
            FloatingText(
                f"-{damage}",
                enemy.x,
                enemy.y - 0.25,
                hit_color,
                ttl=0.6,
            )
        )
        self.add_impact(enemy.x, enemy.y, hit_color, ttl=0.26, radius=0.30, kind="hit")
        if (
            familiar.kind == "spirit_beast"
            and self.player.has_upgrade("ranger_alpha")
            and enemy.alive
        ):
            self.move_actor(
                enemy,
                familiar.facing_x * 0.22,
                familiar.facing_y * 0.22,
            )
        # Blood path (3.18.4): familiar hits siphon life into the Acolyte. The
        # ``lifesteal`` flag is set at summon time from Blood investment (see
        # ``player_cast_spirit_call``); the heal amount scales live with the
        # current Blood degree via the shared spell-leech ramp, so leveling Blood
        # after summoning still strengthens the drain on the next cast.
        if familiar.lifesteal:
            heal = self._acolyte_spell_leech()
            if heal:
                self.player.hp = min(self.player.max_hp, self.player.hp + heal)
                self.floaters.append(
                    FloatingText(
                        f"+{heal}",
                        self.player.x,
                        self.player.y - 0.45,
                        self.damage_type_color("shadow"),
                        ttl=0.55,
                    )
                )
        # Enemy retaliation: an adjacent foe hits back if ready, giving
        # familiars a natural way to die in combat (and the champion's taunt
        # value, since it draws the first blows). Eternal Owls makes the
        # host unkillable so retaliation just chips toward 1.
        if enemy.alive and enemy.attack_timer <= 0:
            self._familiar_take_damage(familiar, max(1, enemy.damage // 2), enemy)
            enemy.attack_timer = enemy.attack_cooldown * 0.6
        if enemy.hp <= 0:
            self.kill_enemy(enemy)

    def _familiar_take_damage(
        self, familiar: Familiar, amount: int, source: Enemy | None = None
    ) -> None:
        if familiar.unkillable:
            # Eternal Owls: the host cannot die; damage floors at 1 and
            # regenerates (see ``_familiar_regen``).
            familiar.hp = max(1, familiar.hp - amount)
            return
        familiar.hp -= max(1, amount)
        if source is not None:
            self.add_impact(
                familiar.x,
                familiar.y,
                self.damage_type_color(self.familiar_damage_type(familiar)),
                ttl=0.22,
                radius=0.28,
                kind="hit",
            )

    def _familiar_regen(self, familiar: Familiar, dt: float) -> None:
        # Eternal Owls familiars slowly regenerate, and unkillable ones
        # recover from the 1-HP floor so they stay useful between fights.
        if familiar.unkillable and familiar.hp < familiar.max_hp:
            familiar.hp = min(
                familiar.max_hp, familiar.hp + max(1, familiar.max_hp // 8) * dt
            )

    def _cull_dead_familiars(self) -> None:
        if not self.familiars:
            return
        self.familiars = [f for f in self.familiars if f.hp > 0]

    def player_dash(self) -> None:
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

    def damage_enemy(
        self,
        enemy: Enemy,
        amount: int,
        knockback_from: tuple[float, float],
        damage_type: str = "physical",
        status_effect: str = "",
        status_duration: float = 0.0,
    ) -> None:
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
            self.move_actor(enemy, (kx / length) * 0.16, (ky / length) * 0.16)
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
        if self.rng.random() < 0.45:
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
