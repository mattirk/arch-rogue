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
"""Acolyte familiars and Ranger Spirit Beast: stats, summons, commands, locomotion, attacks, damage intake, regen, and culling."""
# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

import math
from ..constants import (
    WALK_ANIM_RUNTIME_SCALE_FLOOR,
)
from ..models import (
    Enemy,
    Familiar,
    FloatingText,
)


class _FamiliarsCombatMixin:
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
        # Co-op: only the acting player's own summons are replaced.
        self.familiars = [
            f for f in self.familiars if f.owner_id != self.player.player_id
        ]
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
                    owner_id=self.player.player_id,
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
        # Co-op: only the acting player's own summons are replaced.
        self.familiars = [
            f for f in self.familiars if f.owner_id != self.player.player_id
        ]
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
                owner_id=self.player.player_id,
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

    def _familiar_owner(self, familiar: Familiar):
        """The player this summon belongs to (co-op-aware, local fallback)."""

        if self.mp_active:
            for player in self.active_players():
                if player.player_id == familiar.owner_id:
                    return player
        return self.player

    def _familiar_follow_player(self, familiar: Familiar, dt: float) -> None:
        owner = self._familiar_owner(familiar)
        dx = owner.x - familiar.x
        dy = owner.y - familiar.y
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
        owner = self._familiar_owner(familiar)
        px_dx = familiar.x - owner.x
        px_dy = familiar.y - owner.y
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
