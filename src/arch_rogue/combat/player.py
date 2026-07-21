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
"""Player damage intake and per-frame update: take_player_damage, thorns reflect, update_player, garden-room healing."""
# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

import math
import pygame
from ..dungeon import (
    GARDEN_ROOM_KIND,
)
from ..models import (
    Enemy,
    FloatingText,
)

from ._utils import PLAYER_MOVE_SPEED
from .damage_types import (
    PLAYER_ARMOR_TYPED_RESIST_BONUS,
    PLAYER_RESIST_AFFIXES,
    PLAYER_RESIST_UNIQUES,
)


from .damage import DamageContext

class _PlayerCombatMixin:
    def player_typed_resistance(self, damage_type: str) -> float:
        """Per-damage-type resistance fraction the player has against ``damage_type``.

        Centralizes the typed-resist accumulation that used to live inline in
        ``take_player_damage``: armor defense, the armor typed-match bonus,
        per-damage-type affix/unique bonuses (table-driven in
        :mod:`arch_rogue.combat.damage_types`), plus the all-types bonuses
        (``oathwall aegis``, the ``aegis`` status, Warden Temporal Aegis).
        Adding a new damage type's resist affix is one table entry instead
        of editing scattered ``if`` chains here.
        """
        typed = 0.0
        armor = self.player.equipment.get("armor")
        if armor is not None:
            typed += armor.defense * 0.006
            if armor.damage_type and armor.damage_type == damage_type:
                typed += PLAYER_ARMOR_TYPED_RESIST_BONUS
            for affix, bonuses in PLAYER_RESIST_AFFIXES.items():
                if affix in armor.affixes:
                    typed += bonuses.get(damage_type, 0.0)
        for unique, bonuses in PLAYER_RESIST_UNIQUES.items():
            if self.equipped_unique_effect(unique):
                typed += bonuses.get(damage_type, 0.0)
        if self.equipped_unique_effect("oathwall aegis"):
            typed += 0.06
        if self.player_status("aegis") > 0:
            typed += 0.24
        # Milestone 3.18.1 — Time path Degree 4 (Temporal Aegis): while Time
        # Skip is active the Warden takes 20% less damage from incoming hits.
        if (
            self.player.class_name == "Warden"
            and self.player.time_skip_timer > 0
            and self.player.has_upgrade("warden_unyielding")
        ):
            typed += 0.20
        return typed

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
        typed_resist = self.player_typed_resistance(damage_type)
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
                DamageContext(
                    target=attacker,
                    amount=counter,
                    damage_type="holy",
                    knockback_from=(self.player.facing_x, self.player.facing_y),
                    status_effect="stunned"
                    if self.player.has_upgrade("warden_aegis")
                    else "",
                    status_duration=0.35,
                    source="counter",
                )
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
        mobile_moving = False
        if controller_moving:
            self.aim_input_mode = "controller"
            kbd_dx, kbd_dy = cx, cy
        elif getattr(self, "mobile_mode", False):
            mobile_x, mobile_y = self.mobile_joystick_world_vector()
            mobile_moving = bool(mobile_x or mobile_y)
            if mobile_moving:
                kbd_dx, kbd_dy = mobile_x, mobile_y
        if petting:
            # Keep the authored kneel grounded. Cooldowns, statuses, and resource
            # regeneration below still advance normally during this brief pause.
            kbd_dx = kbd_dy = 0.0
            controller_moving = False
            mobile_moving = False
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
                mobile_aiming = bool(
                    getattr(self, "mobile_mode", False)
                    and self.active_mobile_world_touch() is not None
                )
                if not (aim_x or aim_y) and not mobile_aiming:
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
        elif not petting:
            mouse_point = (
                pygame.mouse.get_pos()
                if not getattr(self, "mobile_mode", False)
                and pygame.mouse.get_pressed()[0]
                else None
            )
            target_point = mouse_point
            if target_point is not None:
                dx, dy = self.face_player_toward_screen_point(*target_point)
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
        self._update_garden_healing(dt)

    def _update_garden_healing(self, dt: float) -> None:
        # 4.2: standing inside an overgrown garden flavor room mends the
        # player a little. The heal is slow (one +HP tick per second) so it
        # reads as a calm refuge rather than a full heal station, and it only
        # ticks while HP is actually missing. Each tick refreshes a greenish
        # aura the renderer fades out so the player can see the garden is
        # doing something.
        if self.player.hp <= 0:
            return
        if self.player.hp >= self.player.max_hp:
            self.garden_heal_accumulator = 0.0
            return
        special_room = self.dungeon.special_room_at_point(
            self.player.x, self.player.y
        )
        if special_room is None or special_room.kind != GARDEN_ROOM_KIND:
            self.garden_heal_accumulator = 0.0
            return
        self.garden_heal_accumulator += dt
        if self.garden_heal_accumulator < 1.0:
            return
        self.garden_heal_accumulator -= 1.0
        heal = max(2, self.player.max_hp // 25 + 2)
        healed = min(self.player.max_hp - self.player.hp, heal)
        if healed <= 0:
            return
        self.player.hp += healed
        self.garden_heal_glow_duration = 0.9
        self.garden_heal_glow = self.garden_heal_glow_duration
        self.floaters.append(
            FloatingText(
                f"Garden +{healed}",
                self.player.x,
                self.player.y - 0.55,
                (130, 220, 150),
                ttl=0.95,
            )
        )
