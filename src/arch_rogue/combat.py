# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
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
    WALK_ANIM_SPEED_CEIL,
    WALK_ANIM_SPEED_FLOOR,
    WALK_ANIMATION_RATE,
)
from .content import (
    SKILL_UPGRADES,
    combo_bonus,
    completed_branches,
    cross_branch_tag_bonus,
    is_branch_locked,
    skill_node_by_key,
    skill_nodes_for_archetype,
)
from .models import (
    Color,
    Enemy,
    Familiar,
    FloatingText,
    Player,
    Projectile,
    Shopkeeper,
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
        return {
            "Warden": "holy",
            "Rogue": "poison",
            "Arcanist": "frost",
            "Acolyte": "shadow",
            "Ranger": "physical",
        }.get(self.player.class_name, "arcane")

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
        self.floaters.append(
            FloatingText(
                status.title(),
                enemy.x,
                enemy.y - 0.45,
                self.damage_type_color(
                    "poison"
                    if status == "poisoned"
                    else "frost"
                    if status == "chilled"
                    else "shadow"
                    if status == "bound"
                    else "holy"
                ),
                ttl=0.65,
            )
        )

    def enemy_speed_multiplier(self, enemy: Enemy) -> float:
        multiplier = 1.0
        if enemy.statuses.get("chilled", 0.0) > 0:
            multiplier *= 0.58
        if enemy.statuses.get("snared", 0.0) > 0:
            multiplier *= 0.45
        if enemy.statuses.get("bound", 0.0) > 0:
            multiplier *= 0.62
        return multiplier

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

    def update_enemy_statuses(self, dt: float) -> None:
        for enemy in list(self.enemies):
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
            "Warden": ("Shield Bash", "Guard Bolt", "Bulwark Wave", "Guard Step"),
            "Rogue": ("Backstab", "Knife Fan", "Smoke Burst", "Shadow Dash"),
            "Arcanist": ("Mage Strike", "Arc Bolt", "Frost Nova", "Blink"),
            "Acolyte": ("Blood Rite", "Spirit Bolt", "Spirit Call", "Dark Step"),
            "Ranger": ("Hawk Slash", "Multishot", "Snare Nova", "Vault"),
        }
        return names.get(self.player.class_name, ("Slash", "Bolt", "Nova", "Dash"))

    def skill_color(self) -> Color:
        colors = {
            "Warden": (235, 205, 120),
            "Rogue": (170, 230, 150),
            "Arcanist": (120, 210, 255),
            "Acolyte": (220, 95, 140),
            "Ranger": (150, 215, 105),
        }
        return colors.get(self.player.class_name, (120, 210, 255))

    def available_skill_choices(self) -> list:
        """Skill nodes the player can choose right now.

        A node is available when it belongs to the player's archetype, is not
        yet acquired, every prerequisite node has already been acquired, and
        its branch has not been locked by the two-branch commitment limit
        (Milestone 3.7). Tier-1 nodes are always available until taken, unless
        their branch is locked.
        """
        acquired = set(self.player.skill_upgrades)
        choices: list = []
        for node in skill_nodes_for_archetype(self.player.class_name):
            if node.key in acquired:
                continue
            if is_branch_locked(acquired, node.archetype, node.branch):
                continue
            if all(prereq in acquired for prereq in node.prerequisites):
                choices.append(node)
        return choices

    def skill_node_state(self, node) -> str:
        """Return one of "chosen", "available", "branch_locked", "locked".

        "branch_locked" (Milestone 3.7) marks nodes whose branch is sealed by
        the two-branch commitment limit and is distinct from "locked" so the
        menu can render the two reasons differently.
        """
        acquired = set(self.player.skill_upgrades)
        if node.key in acquired:
            return "chosen"
        if is_branch_locked(acquired, node.archetype, node.branch):
            return "branch_locked"
        if all(prereq in acquired for prereq in node.prerequisites):
            return "available"
        return "locked"

    def choose_skill_upgrade(self, key: str, reason: str = "chosen") -> bool:
        """Apply a specific skill node by key, spending one skill point.

        Returns False (without spending a point) if the node is unknown, belongs
        to another archetype, is already acquired, has unmet prerequisites, is
        in a branch locked by the commitment limit, or the player has no skill
        points to spend.
        """
        node = skill_node_by_key(key)
        if node is None or node.archetype != self.player.class_name:
            return False
        if node.key in self.player.skill_upgrades:
            return False
        if not all(
            prereq in self.player.skill_upgrades for prereq in node.prerequisites
        ):
            return False
        if is_branch_locked(
            set(self.player.skill_upgrades), node.archetype, node.branch
        ):
            return False
        if self.player.skill_points <= 0:
            return False
        self.player.skill_points -= 1
        self._apply_skill_node(node, reason)
        self._apply_combo_bonus_delta(node)
        return True

    def grant_skill_point(self, amount: int = 1, reason: str = "reward") -> None:
        """Award skill points from run rewards (shrines, altars, story)."""
        if amount <= 0:
            return
        self.player.skill_points += amount
        self.floaters.append(
            FloatingText(
                f"+{amount} Skill Point{'s' if amount != 1 else ''}",
                self.player.x,
                self.player.y - 0.6,
                self.skill_color(),
                ttl=1.6,
            )
        )

    def _apply_skill_node(self, node, reason: str) -> None:
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

    def _apply_combo_bonus_delta(self, node) -> None:
        """Apply the combo-bonus delta caused by acquiring `node`.

        Called after a node is chosen. If the acquisition completed a new
        branch and pushed the player into a higher combo tier, the delta is
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
        """Return (completed_branches, melee_bonus, spell_bonus, max_hp_bonus).

        Cheap O(nodes) lookup with no per-frame allocations beyond the returned
        tuple; safe to call from the hot path or the character sheet.
        """
        acquired = set(self.player.skill_upgrades)
        done = completed_branches(acquired, self.player.class_name)
        melee, spell, max_hp = combo_bonus(acquired, self.player.class_name)
        return (done, melee, spell, max_hp)

    def cross_branch_bonus_state(self) -> tuple[int, int]:
        """Return (melee, spell) bonus from acquired cross-branch modifiers."""
        return cross_branch_tag_bonus(set(self.player.skill_upgrades))

    def combo_preview(self, node) -> tuple[int, int, int]:
        """Combo bonus if `node` were acquired next (for sheet hover preview)."""
        from .content import combo_bonus_preview

        return combo_bonus_preview(
            set(self.player.skill_upgrades), self.player.class_name, node.key
        )

    def grant_skill_upgrade(self, reason: str = "level up") -> bool:
        """Grant a random available skill node, respecting tree prerequisites.

        Used by shrines/altars/story rewards. These are bonus grants that do
        NOT spend the player's banked skill points (level-up points are spent
        by the player via `choose_skill_upgrade`). Falls back to the flat
        `SKILL_UPGRADES` pool only if the tree yields no available nodes.
        """
        choices = self.available_skill_choices()
        if not choices:
            legacy_choices = [
                upgrade
                for upgrade in SKILL_UPGRADES
                if upgrade.archetype == self.player.class_name
                and upgrade.key not in self.player.skill_upgrades
            ]
            if not legacy_choices:
                return False
            upgrade = self.rng.choice(legacy_choices)
            node = skill_node_by_key(upgrade.key)
            if node is not None:
                self._apply_skill_node(node, reason)
                self._apply_combo_bonus_delta(node)
                return True
            return False
        node = self.rng.choice(choices)
        self._apply_skill_node(node, reason)
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

    def nova_mana_cost(self) -> int:
        cost = 14 if self.player.class_name in ("Arcanist", "Acolyte") else 18
        if self.player.has_upgrade("acolyte_veil"):
            cost -= 2
        if self.equipment_skill_bonus("Nova"):
            cost -= 1
        if any(
            item is not None and item.cursed for item in self.player.equipment.values()
        ):
            cost += 2
        return max(8, cost)

    def nova_cooldown(self) -> float:
        cooldown = 2.65 if self.player.class_name == "Arcanist" else 3.2
        if self.equipment_skill_bonus("Nova"):
            cooldown -= 0.18
        cast_speed = max(-0.20, min(0.35, self.equipment_stat_total("cast_speed")))
        cooldown *= 1.0 - cast_speed * 0.75
        return max(1.85, cooldown)

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
        flash = (160, 35, 32) if amount >= self.player.max_hp * 0.18 else (105, 24, 28)
        self.player_hit_flash = max(
            self.player_hit_flash, 0.22 if amount < self.player.max_hp * 0.18 else 0.32
        )
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

    def _reflect_thorns(self, attacker: Enemy, amount: int) -> None:
        attacker.hp -= amount
        self.enemy_hit_flashes[id(attacker)] = max(
            self.enemy_hit_flashes.get(id(attacker), 0.0), 0.18
        )
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
                self.move_actor(
                    self.player,
                    nx * magnitude * move_speed * dt,
                    ny * magnitude * move_speed * dt,
                )
            if self.enemy_in_melee_arc():
                self.player_melee_attack()
        elif pygame.mouse.get_pressed()[0]:
            dx, dy = self.face_player_toward_screen_point(*pygame.mouse.get_pos())
            distance = math.hypot(dx, dy)
            if distance > 0.12:
                self.move_actor(
                    self.player,
                    (dx / distance) * move_speed * dt,
                    (dy / distance) * move_speed * dt,
                )
            if self.enemy_in_melee_arc():
                self.player_melee_attack()

        self.player.melee_timer = max(0.0, self.player.melee_timer - dt)
        self.player.bolt_timer = max(0.0, self.player.bolt_timer - dt)
        self.player.dash_timer = max(0.0, self.player.dash_timer - dt)
        self.player.nova_timer = max(0.0, self.player.nova_timer - dt)
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

    def move_actor(self, actor: Player | Enemy, dx: float, dy: float) -> None:
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
        if distance > 0.0001:
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

    def advance_animation_phases(self, dt: float) -> None:
        # Advance run-cycle animation phases on a fixed-timestep accumulator
        # so the sprite/limb animation stays smooth even when per-frame dt
        # jitters from frame-rate variance. The rate scales with the actor's
        # speed so faster units take faster steps, but is clamped to a
        # floor/ceiling (WALK_ANIM_SPEED_FLOOR/CEIL): without the floor, slow
        # enemies cycle so slowly that the 12 discrete run frames are each
        # held for many render frames, producing a visible stutter; the
        # ceiling keeps very fast units (elites, haste) from blurring.
        anim_dt = dt
        if self.player.moving:
            self.player.anim_time += (
                anim_dt * WALK_ANIMATION_RATE * self._anim_speed(PLAYER_MOVE_SPEED)
            )
        for enemy in self.enemies:
            if enemy.moving:
                enemy.anim_time += (
                    anim_dt * WALK_ANIMATION_RATE * self._anim_speed(enemy.speed)
                )

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
        others: list[Player | Enemy | Shopkeeper]
        if isinstance(actor, Player):
            others = [*self.enemies, *self.shopkeepers]
        else:
            others = [
                self.player,
                *(enemy for enemy in self.enemies if enemy is not actor),
                *self.shopkeepers,
            ]

        for other in others:
            dx = actor.x - other.x
            dy = actor.y - other.y
            distance = math.hypot(dx, dy)
            other_radius = (
                self.actor_hit_radius(other)
                if isinstance(other, (Player, Enemy))
                else 0.34
            )
            min_distance = self.actor_hit_radius(actor) + other_radius
            if distance >= min_distance:
                continue

            if distance > 0.001:
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

    def update_enemies(self, dt: float) -> None:
        for enemy in self.enemies:
            enemy.moving = False
            enemy.attack_timer = max(0.0, enemy.attack_timer - dt)
            dx = self.player.x - enemy.x
            dy = self.player.y - enemy.y
            distance = math.hypot(dx, dy)
            if distance > enemy.aggro_range:
                continue
            if enemy.statuses.get("stunned", 0.0) > 0:
                enemy.telegraph = "stunned"
                continue
            nx, ny = (dx / distance, dy / distance) if distance > 0.001 else (0.0, 0.0)
            move_speed = enemy.speed * self.enemy_speed_multiplier(enemy)
            if distance > 0.001:
                enemy.facing_x = nx
                enemy.facing_y = ny

            # Enemies must actually see the player to attack; without this they
            # melee/cast through walls when adjacent on the far side of a wall.
            # Movement is intentionally not gated so pursuit around corners still
            # works once an enemy has aggro'd.
            has_los = self.dungeon.line_of_sight(
                enemy.x, enemy.y, self.player.x, self.player.y
            )

            if enemy.kind == "boss" or enemy.is_boss_encounter:
                # 4-tile boss encounters (final tyrant + floor guardians) use the
                # same pressure pattern: close the gap, cast a bolt fan at mid
                # range, and crush with melee up close.
                if distance > enemy.attack_range:
                    self.move_actor(enemy, nx * move_speed * dt, ny * move_speed * dt)
                if 2.0 < distance <= 6.0 and enemy.attack_timer <= 0 and has_los:
                    self.enemy_cast(enemy, nx, ny)
                elif (
                    distance <= enemy.attack_range
                    and enemy.attack_timer <= 0
                    and has_los
                ):
                    self.enemy_melee(enemy)
            elif enemy.kind == "ranged":
                if 3.5 < distance:
                    self.move_actor(enemy, nx * move_speed * dt, ny * move_speed * dt)
                elif distance < 2.5:
                    self.move_actor(enemy, -nx * move_speed * dt, -ny * move_speed * dt)
                if (
                    distance <= enemy.attack_range
                    and enemy.attack_timer <= 0
                    and has_los
                ):
                    self.enemy_cast(enemy, nx, ny)
            else:
                if distance > enemy.attack_range:
                    self.move_actor(enemy, nx * move_speed * dt, ny * move_speed * dt)
                elif enemy.attack_timer <= 0 and has_los:
                    self.enemy_melee(enemy)

    def enemy_melee(self, enemy: Enemy) -> None:
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

    def enemy_cast(self, enemy: Enemy, nx: float, ny: float) -> None:
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
            # Milestone 3.16 - carry a small moving light along each live
            # projectile so bolts and arrows read as streaks of light. Reuses
            # this loop so no new pass is added; the light is transient and
            # decays in update_lights when the projectile dies.
            self.add_light(
                projectile.x, projectile.y,
                LIGHT_PROJECTILE_RADIUS, projectile.color,
                intensity=LIGHT_PROJECTILE_INTENSITY,
                ttl=LIGHT_PROJECTILE_TTL, kind="projectile",
            )
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
                    # Milestone 3.7 — Storm-branch chain lightning arcs from
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
                # Milestone 3.15 — a summoner's familiars bodyguard the
                # Acolyte, intercepting enemy bolts that pass near them. Only
                # checked when a host is active so non-Acolyte runs pay nothing.
                if self.familiars:
                    struck = None
                    for familiar in self.familiars:
                        if (
                            math.hypot(
                                projectile.x - familiar.x,
                                projectile.y - familiar.y,
                            )
                            < ENEMY_PROJECTILE_HIT_RADIUS
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
                if (
                    math.hypot(
                        projectile.x - self.player.x, projectile.y - self.player.y
                    )
                    < ENEMY_PROJECTILE_HIT_RADIUS
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
        best_dist = 6.5
        for enemy in self.enemies:
            dist = math.hypot(enemy.x - projectile.x, enemy.y - projectile.y)
            if dist < best_dist:
                best_dist = dist
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
        """Storm-branch chain lightning: arc from a struck foe to a neighbour.

        Triggered by the Arcanist Storm branch (arcanist_chain_lightning and
        deeper). The chain hits one extra foe near the primary for partial
        damage, giving the Storm path a distinct bolt behavior versus the Bolt
        path's pierce/homing.
        """
        if not self.player.has_upgrade("arcanist_chain_lightning"):
            return
        if projectile.owner != "player":
            return
        best = None
        best_dist = 2.6
        for enemy in self.enemies:
            if enemy is primary or id(enemy) in projectile.hit_enemies:
                continue
            dist = math.hypot(enemy.x - primary.x, enemy.y - primary.y)
            if dist < best_dist:
                best_dist = dist
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
        # Milestone 3.7 refinement: ramp one step per Blood tier; 0 until Blood
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

    def _acolyte_nova_leech(self) -> int:
        # Milestone 3.7 refinement: ramp one step per Blood tier; 0 until Blood
        # is committed.
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
                # Bulwark branch's first node unlocks the cleave arc so the
                # branch choice changes how melee plays, not just its damage.
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
                # branch; base backstabs never crit, so committing to Precision
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
                    # Blood branch; base melee drains nothing until the Acolyte
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
        # default and gains one projectile per branch tier rather than jumping
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
        # Milestone 3.7 refinement — branch-progression projectile mechanics
        # ramp one step per tier. Bolt path (Arcanist): pierce climbs 0->1->2
        # and the capstone adds homing. Volley path (Ranger): piercing unlocks
        # at the piercing tier and the capstone adds homing.
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
        mana_cost = self.nova_mana_cost()
        if self.player.nova_timer > 0 or self.player.mana < mana_cost:
            return
        self.player.nova_timer = self.nova_cooldown()
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
            # Nova tier so each pick reaches farther, instead of one big jump.
            if self.player.class_name == "Arcanist":
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
            if self.equipment_skill_bonus("Nova"):
                radius += 0.25
            if self.equipment_skill_bonus("Nova radius"):
                radius += 0.35
            if distance <= radius:
                hits += 1
                damage = (
                    10
                    + self.player.level * 2
                    + self.player.spell_bonus
                    + self.rng.randrange(0, 5)
                )
                damage_type = self.nova_damage_type()
                status_effect = ""
                status_duration = 0.0
                if self.equipment_skill_bonus("Nova"):
                    damage += 2
                if self.player.class_name == "Warden":
                    status_effect = "stunned"
                    status_duration = (
                        0.35 if self.player.has_upgrade("warden_aegis") else 0.2
                    )
                    enemy.attack_timer = max(enemy.attack_timer, 0.45)
                elif self.player.class_name == "Rogue":
                    status_effect = "poisoned"
                    status_duration = (
                        2.4 if self.player.has_upgrade("rogue_venom") else 1.4
                    )
                    self.set_player_status("smoke", 0.65)
                elif self.player.class_name == "Arcanist":
                    status_effect = "chilled"
                    status_duration = (
                        1.9 if self.player.has_upgrade("arcanist_permafrost") else 1.2
                    )
                elif self.player.class_name == "Ranger":
                    snare_time = (
                        1.25 if self.player.has_upgrade("ranger_snare") else 0.8
                    )
                    enemy.attack_timer = max(enemy.attack_timer, snare_time)
                    status_effect = "snared"
                    status_duration = snare_time
                if self.player.class_name == "Acolyte":
                    # Milestone 3.15 — Acolyte's action-bar slot 3 is now Spirit
                    # Call, so this nova path is only reachable when
                    # ``player_cast_nova`` is invoked directly (legacy calls).
                    # The Blood-branch leech still applies here; the gravebind
                    # *bind* has retired from the nova (it now lives on Spirit
                    # Bolt, where ``player_cast_bolt`` applies "bound").
                    leech = self._acolyte_nova_leech()
                    if leech:
                        self.player.hp = min(self.player.max_hp, self.player.hp + leech)
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

    # ------------------------------------------------------------------
    # Milestone 3.15 — Spirit Call / familiar (summon) system.
    # ------------------------------------------------------------------
    FAMILIAR_BASE_HP = 20
    FAMILIAR_BASE_DAMAGE = 6
    FAMILIAR_BASE_SPEED = 3.2
    FAMILIAR_ATTACK_RANGE = 1.25
    FAMILIAR_ATTACK_COOLDOWN = 0.85
    FAMILIAR_AGGRO_RANGE = 7.0
    FAMILIAR_FOLLOW_DISTANCE = 1.6

    def familiar_max_count(self) -> int:
        """How many familiars Spirit Call maintains at once.

        Base 1, +1 from ``acolyte_bone_legion`` (t3), +1 from
        ``acolyte_legion_eternal`` (t5 capstone). Committing deeper into Spirit
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

        Scales with Spirit branch investment so each pick is felt:
          * ``acolyte_spirit_call`` (t1) — the core summoning node — grows the
            familiar (HP + damage) and unlocks the medium sprite variant.
          * ``acolyte_wraith_host`` (t2) — lifesteal + HP.
          * ``acolyte_bone_legion`` (t3) — damage.
          * ``acolyte_wraith_lord`` (t4) — champion: large sprite, HP + damage,
            taunts foes.
          * ``acolyte_legion_eternal`` (t5) — unkillable (regenerates, HP
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

    def familiar_damage_type(self) -> str:
        # Summoned spirits deal shadow damage, matching the Acolyte's theme.
        return "shadow"

    def player_cast_spirit_call(self) -> None:
        """Acolyte slot-3 ability: summon / refresh the spirit familiar host.

        Reuses the nova-slot mana cost and cooldown (``nova_mana_cost`` /
        ``nova_cooldown``) so the action bar stays balanced. On cast, the host
        is always recreated fresh: any existing familiars are dismissed and a
        full ``familiar_max_count`` host is summoned in a small ring around the
        player, so the summon always snaps to the Acolyte's current position
        and picks up the latest build stats. The host persists until each
        familiar is killed or the floor is descended.
        """
        if self.player.class_name != "Acolyte":
            # Defensive: only the Acolyte channels Spirit Call. Other classes
            # fall through to their nova.
            self.player_cast_nova()
            return
        mana_cost = self.nova_mana_cost()
        if self.player.nova_timer > 0 or self.player.mana < mana_cost:
            return
        self.player.nova_timer = self.nova_cooldown()
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
                    lifesteal=self.player.has_upgrade("acolyte_wraith_host"),
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

    def update_familiars(self, dt: float) -> None:
        """Follow-and-attack AI for the familiar host.

        O(familiar) per frame with no per-frame allocations: each familiar finds
        the nearest living enemy within aggro range (one pass over the enemy
        list), then either closes to attack, pursues, or returns to follow the
        player. Familiars persist until killed (HP <= 0) or floor descent.
        """
        if not self.familiars:
            return
        if not self.enemies:
            # No threats: regroup around the player.
            for familiar in self.familiars:
                self._familiar_follow_player(familiar, dt)
                self._familiar_regen(familiar, dt)
            self._cull_dead_familiars()
            return
        for familiar in self.familiars:
            familiar.attack_timer = max(0.0, familiar.attack_timer - dt)
            # Nearest living enemy within aggro range (single pass).
            target = None
            best_dist = self.FAMILIAR_AGGRO_RANGE
            for enemy in self.enemies:
                if not enemy.alive:
                    continue
                d = math.hypot(enemy.x - familiar.x, enemy.y - familiar.y)
                if d < best_dist:
                    best_dist = d
                    target = enemy
            if target is not None:
                dx = target.x - familiar.x
                dy = target.y - familiar.y
                dist = math.hypot(dx, dy)
                if dist <= familiar.attack_range:
                    # In melee range: face and strike on cooldown.
                    if dist > 0.001:
                        familiar.facing_x = dx / dist
                        familiar.facing_y = dy / dist
                    if familiar.attack_timer <= 0:
                        self._familiar_attack(familiar, target)
                    familiar.moving = False
                else:
                    # Pursue the target.
                    if dist > 0.001:
                        nx, ny = dx / dist, dy / dist
                        familiar.facing_x = nx
                        familiar.facing_y = ny
                        familiar.move_x = nx
                        familiar.move_y = ny
                        self._move_familiar(
                            familiar, nx * familiar.speed * dt, ny * familiar.speed * dt
                        )
                        familiar.moving = True
            else:
                self._familiar_follow_player(familiar, dt)
            familiar.anim_time += dt * (WALK_ANIMATION_RATE if familiar.moving else 0.0)
            self._familiar_regen(familiar, dt)
        self._cull_dead_familiars()

    def _familiar_follow_player(self, familiar: Familiar, dt: float) -> None:
        dx = self.player.x - familiar.x
        dy = self.player.y - familiar.y
        dist = math.hypot(dx, dy)
        if dist > self.FAMILIAR_FOLLOW_DISTANCE and dist > 0.001:
            nx, ny = dx / dist, dy / dist
            familiar.facing_x = nx
            familiar.facing_y = ny
            familiar.move_x = nx
            familiar.move_y = ny
            self._move_familiar(
                familiar, nx * familiar.speed * dt, ny * familiar.speed * dt
            )
            familiar.moving = True
        else:
            familiar.moving = False

    def _move_familiar(self, familiar: Familiar, dx: float, dy: float) -> None:
        """Lightweight familiar locomotion.

        Familiars skip the shared ``move_actor`` path because that resolves
        contacts via ``enemy_hit_radius``, which assumes Enemy fields
        (``size``/``kind``/``name``). Instead we do a tight wall probe plus a
        soft separation from the player so the summon orbits the Acolyte
        rather than overlapping. Stays O(1) and allocation-free.
        """
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

    def _familiar_attack(self, familiar: Familiar, enemy: Enemy) -> None:
        familiar.attack_timer = familiar.attack_cooldown
        damage = familiar.damage + self.rng.randrange(0, 3)
        # Familiars are summoner-aligned, so they bypass the player's
        # story-damage modifiers and apply directly (keeping the hot path
        # allocation-free).
        enemy.hp -= max(1, damage)
        self.enemy_hit_flashes[id(enemy)] = 0.18
        hit_color = self.damage_type_color(self.familiar_damage_type())
        self.floaters.append(
            FloatingText(
                f"-{max(1, damage)}",
                enemy.x,
                enemy.y - 0.25,
                hit_color,
                ttl=0.6,
            )
        )
        self.add_impact(enemy.x, enemy.y, hit_color, ttl=0.26, radius=0.30, kind="hit")
        # Owl Companion (t2): familiar hits siphon life into the Acolyte.
        if familiar.lifesteal:
            heal = max(1, damage // 3)
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
                self.damage_type_color("shadow"),
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
            if math.hypot(enemy.x - x, enemy.y - y) <= hit_radius:
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
        self.enemy_hit_flashes[id(enemy)] = 0.22 if enemy.kind != "boss" else 0.32
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
            if distance < best_distance:
                best_distance = distance
                target = enemy
        if target is None:
            return
        target.hp -= damage
        self.enemy_hit_flashes[id(target)] = max(
            self.enemy_hit_flashes.get(id(target), 0.0), 0.18
        )
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
            # Milestone 3.3: level-ups award a skill point (handled inside
            # `gain_xp`) instead of auto-granting a node. The player spends
            # the point in the character sheet. Surface the banked point so the
            # player knows to open the sheet.
            self.floaters.append(
                FloatingText(
                    "LEVEL UP · SKILL POINT",
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
