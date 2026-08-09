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
"""Player attack casts: melee swing, Big Hit, bolt, frost nova, and Warden Time Skip."""
# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

import math
from ..content import (
    MAX_COMMITTED_PATHS,
    completed_paths,
    path_progress,
)
from ..models import (
    Enemy,
    FloatingText,
    Projectile,
    StormChainCharge,
)

from ._utils import (
    BIGHIT_BOSS_THROW_FACTOR,
    BIGHIT_CHARGING_STATUS,
    BIGHIT_CLEAVE_FACTOR,
    BIGHIT_COMMIT_FRACTION,
    BIGHIT_DAMAGE_MULT,
    BIGHIT_THROW_TILES,
    BIGHIT_THROW_TILES_RANGER,
    KNOCKBACK_DECAY_RATE,
)

from .damage import DamageContext

# Frost Nova reach tuning. The Nova discipline path is the dedicated widening
# route: every acquired Nova-path node adds one radius step on top of the
# base blast, so the fully mastered path more than doubles the nova's reach.
NOVA_BASE_RADIUS = 2.45
NOVA_RADIUS_PER_NOVA_NODE = 0.55
# draw_impact expands a ring to ``radius * (1 + 1.4 * progress)`` tiles over
# its life, so dividing the true blast reach by this factor makes the cast
# ring die exactly at the blast edge.
_NOVA_RING_EXPANSION = 2.4

class _AttacksCombatMixin:
    def _rogue_crit_profile(self) -> tuple[float, float]:
        """Rogue Precision-path melee crit profile: (chance, multiplier).

        Crits are gated behind the Precision discipline path -- base
        backstabs never crit, so committing to Precision is essential to
        the crit playstyle. Tiers escalate with deeper Precision upgrades.
        Centralized so disciplines/affixes can hook in by overriding this
        one getter instead of editing the melee attack.
        """
        if self.player.has_upgrade("rogue_deathmark"):
            return 0.40, 2.25
        if self.player.has_upgrade("rogue_crimson_edge"):
            return 0.34, 2.10
        if self.player.has_upgrade("rogue_executioner"):
            return 0.28, 1.95
        if self.player.has_upgrade("rogue_venom"):
            return 0.20, 1.75
        if self.player.has_upgrade("rogue_precision"):
            return 0.15, 1.60
        return 0.0, 1.0

    def roll_melee_crit(
        self, enemy: Enemy, chance_scale: float = 1.0
    ) -> tuple[bool, float]:
        """Roll a melee crit. Returns (is_crit, damage_multiplier).

        Rogue Precision-path crits plus the ``smoke crits`` unique-effect
        override (a 30% chance crit while benefiting from Smoke, flavored
        as a poison hit). Emits the ``Smoke Crit`` floater when the smoke
        override fires; the caller applies the multiplier and emits the
        ``Critical`` floater. RNG consumption order is preserved exactly
        (Precision roll, then smoke roll) so replays stay deterministic.
        ``chance_scale`` bends only the Precision chance (Killing Blow's
        doubled-crit rider); the smoke override keeps its flat odds.
        """
        crit_chance, crit_mult = self._rogue_crit_profile()
        is_crit = (
            self.player.class_name == "Rogue"
            and self.rng.random() < min(1.0, crit_chance * chance_scale)
        )
        if (
            not is_crit
            and self.equipped_unique_effect("smoke crits")
            and self.player_status("smoke") > 0
            and self.rng.random() < 0.30
        ):
            is_crit = True
            crit_mult = 1.80
            self.floaters.append(
                FloatingText(
                    "Smoke Crit", enemy.x, enemy.y - 0.45, (255, 225, 120)
                )
            )
        return is_crit, crit_mult

    def player_melee_attack(self) -> None:
        # Winding up the Big Hit suppresses the auto-jab: you are hauling the
        # weapon back, not poking. The status replicates, so a co-op joiner
        # stops queueing melee intents during its own charge too.
        if self.player_big_hit_charging():
            return
        if self.mp_is_joiner():
            self.mp_queue_action("melee")
            return
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
        self.add_slash(tx, ty, 0.18, self.player.facing_x, self.player.facing_y)
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
                is_crit, crit_mult = self.roll_melee_crit(enemy)
                if is_crit:
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
                    DamageContext(
                        target=enemy,
                        amount=damage,
                        damage_type=damage_type,
                        knockback_from=(self.player.facing_x, self.player.facing_y),
                        status_effect=status_effect,
                        status_duration=status_duration,
                        source="melee",
                        is_crit=is_crit,
                    )
                )
                if self.player.class_name == "Acolyte":
                    # Milestone 3.7 — Blood Rite's leech is gated behind the
                    # Blood path; base melee drains nothing until the Acolyte
                    # commits to Blood.
                    leech = self._acolyte_melee_leech()
                    if leech:
                        self.player.hp = min(self.player.max_hp, self.player.hp + leech)

    # --- Big Hit (action slot 1) -----------------------------------------
    #
    # Hold-to-charge heavy blow shared by all archetypes (build/bighit.md):
    # press starts a 0.9 s windup at half move speed, stamina spent up front.
    # Releasing in the first half cancels at a 1.5 s cooldown price; past
    # halfway the blow is committed and auto-fires when the charge completes,
    # in whatever direction the player is facing at that moment. The charge
    # itself is the underscore status ``_charging`` (skipped by the generic
    # status decrement; _update_big_hit owns its TTL) so it replicates to a
    # co-op partner and rides run saves with zero extra plumbing.

    def player_big_hit_charging(self) -> bool:
        return self.player_status(BIGHIT_CHARGING_STATUS) > 0.0

    def player_big_hit_charge_progress(self) -> float:
        """Charge completion in [0, 1]; 0 when not charging."""
        ttl = self.player_status(BIGHIT_CHARGING_STATUS)
        if ttl <= 0.0:
            return 0.0
        charge_time = self.bighit_charge_time()
        return max(0.0, min(1.0, 1.0 - ttl / charge_time))

    def player_big_hit_committed(self) -> bool:
        """Past the halfway point the blow can no longer be reverted."""
        return (
            self.player_big_hit_charging()
            and self.player_big_hit_charge_progress() >= BIGHIT_COMMIT_FRACTION
        )

    def player_big_hit(self) -> None:
        if self.player_big_hit_charging():
            return
        if self.mp_is_joiner():
            self.mp_queue_action("bighit")
            return
        stamina_cost = self.bighit_stamina_cost()
        if self.player.bighit_timer > 0 or self.player.stamina < stamina_cost:
            return
        # Spent at press, never refunded — cancelling still costs the wind.
        self.player.stamina -= stamina_cost
        self.set_player_status(
            BIGHIT_CHARGING_STATUS, self.bighit_charge_time()
        )
        # Slow-motion cast pose doubles as the windup animation until the
        # strike swaps it for the attack clip.
        self.set_player_action_visual("cast", self.bighit_charge_time())

    def player_big_hit_release(self) -> None:
        """Button released: cancel the charge unless it already committed."""
        if self.mp_is_joiner():
            if self.player_big_hit_charging():
                # The host re-checks commitment on arrival; a release that
                # raced past the halfway point is simply ignored there.
                self.mp_queue_action("bighit_release")
            return
        if not self.player_big_hit_charging():
            return
        if self.player_big_hit_committed():
            return
        self._cancel_big_hit()

    def _cancel_big_hit(self) -> None:
        """Abort an uncommitted charge: short cooldown, stamina stays spent."""
        self.player.status_effects.pop(BIGHIT_CHARGING_STATUS, None)
        self.player.bighit_timer = max(
            self.player.bighit_timer, self.bighit_cancel_cooldown()
        )
        self.set_player_action_visual("", 0.0)

    def _update_big_hit(self, dt: float) -> None:
        """Per-frame charge/cooldown bookkeeping for the acting player.

        Called from ``update_player`` and, under ``acting_as_player``, from
        the host's partner simulation — the charge must tick (and fire) for
        both actors. Owns the ``_charging`` TTL because underscore statuses
        skip the generic decrement loop.
        """
        player = self.player
        player.bighit_timer = max(0.0, player.bighit_timer - dt)
        ttl = player.status_effects.get(BIGHIT_CHARGING_STATUS, 0.0)
        if ttl <= 0.0:
            return
        ttl -= dt
        if ttl > 0.0:
            player.status_effects[BIGHIT_CHARGING_STATUS] = ttl
            return
        player.status_effects.pop(BIGHIT_CHARGING_STATUS, None)
        self._fire_big_hit()

    def _fire_big_hit(self) -> None:
        """The charge completed: land the blow in the current facing."""
        player = self.player
        player.bighit_timer = self.bighit_cooldown()
        self.set_player_action_visual("attack", 0.26)
        strike_x = player.x + player.facing_x * 0.9
        strike_y = player.y + player.facing_y * 0.9
        targets = self.enemies_in_melee_arc()
        if targets:
            strike_x = (player.x + targets[0].x) * 0.5
            strike_y = (player.y + targets[0].y) * 0.5
        self.add_slash(
            strike_x, strike_y, 0.24, player.facing_x, player.facing_y
        )
        self.add_impact(
            strike_x,
            strike_y,
            self.skill_color(),
            ttl=0.42,
            radius=0.62,
            kind="burst",
            archetype=player.class_name,
        )
        self.floaters.append(
            FloatingText(
                self.skill_names()[0],
                player.x,
                player.y - 0.5,
                self.skill_color(),
                ttl=0.8,
            )
        )
        if not targets:
            # Whiff: you committed before you knew. Full cooldown, no refund.
            return
        class_name = player.class_name
        throw_tiles = (
            BIGHIT_THROW_TILES_RANGER
            if class_name == "Ranger"
            else BIGHIT_THROW_TILES
        )
        total_damage = 0
        for index, enemy in enumerate(list(targets)):
            # Warden rider (Bulwark Slam): everyone in the arc takes the full
            # blow and the full hurl — no cleave falloff, no throw exemption.
            thrown = index == 0 or class_name == "Warden"
            damage = int(
                player.melee_damage() * BIGHIT_DAMAGE_MULT
            ) + self.rng.randrange(-4, 7)
            if self.equipment_skill_bonus("Melee"):
                damage += 2
            if index > 0 and class_name != "Warden":
                damage = max(1, int(damage * BIGHIT_CLEAVE_FACTOR))
            # Rogue rider (Killing Blow): doubled Precision crit chance.
            is_crit, crit_mult = self.roll_melee_crit(enemy, chance_scale=2.0)
            if is_crit:
                damage = int(damage * crit_mult)
                self.floaters.append(
                    FloatingText(
                        "Critical", enemy.x, enemy.y - 0.45, (255, 225, 120)
                    )
                )
            status_effect = ""
            status_duration = 0.0
            if class_name == "Arcanist" and thrown:
                # Force Slam: every hurled enemy lands chilled.
                status_effect = "chilled"
                status_duration = 2.5
            elif class_name == "Ranger" and index == 0:
                # Pinning Strike: the primary target is snared once it lands
                # (the throw needs ~0.25 s; the extra duration covers it).
                status_effect = "snared"
                status_duration = 1.75
            damage = self.apply_story_player_damage(damage)
            total_damage += damage
            knockback_speed = None
            if thrown:
                knockback_speed = throw_tiles * KNOCKBACK_DECAY_RATE
                if enemy.size >= 2:
                    knockback_speed *= BIGHIT_BOSS_THROW_FACTOR
            self.damage_enemy(
                DamageContext(
                    target=enemy,
                    amount=damage,
                    damage_type=self.weapon_damage_type(),
                    knockback_from=(player.facing_x, player.facing_y),
                    status_effect=status_effect,
                    status_duration=status_duration,
                    source="bighit",
                    is_crit=is_crit,
                    knockback_speed=knockback_speed,
                )
            )
        if class_name == "Acolyte" and total_damage > 0:
            # Blood Reap: drink a quarter of the carnage.
            healed = min(
                player.max_hp - player.hp, max(1, int(total_damage * 0.25))
            )
            if healed > 0:
                player.hp += healed
                self.floaters.append(
                    FloatingText(
                        f"+{healed}",
                        player.x,
                        player.y - 0.45,
                        (214, 92, 150),
                    )
                )

    def player_cast_bolt(self) -> None:
        if self.player_big_hit_charging():
            return
        if self.mp_is_joiner():
            self.mp_queue_action("bolt")
            return
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
        damage = self.player.spell_damage()
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
                angles = [-0.12, 0.0, 0.12]  # 3-bolt fan
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
        # Every shard shares one cast-level Storm charge. The first shard to
        # hit spends it, so a missed fan shard cannot discard the effect while
        # the shared token still prevents Bolt's fan from multiplying Storm.
        storm_chain_charge = (
            StormChainCharge()
            if self.player.class_name == "Arcanist"
            and any(
                self.player.has_upgrade(key)
                for key in (
                    "arcanist_chain_lightning",
                    "arcanist_tempest",
                    "arcanist_storm_caller",
                    "arcanist_world_storm",
                )
            )
            else None
        )
        status_effect = ""
        status_duration = 0.0
        if damage_type == "poison" or self.player.has_upgrade("rogue_venom"):
            status_effect = "poisoned"
            status_duration = 2.0
        elif damage_type == "frost":
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
                    owner_id=self.player.player_id,
                    storm_chain_charge=storm_chain_charge,
                )
            )

    def nova_radius(self) -> float:
        """Frost Nova blast radius in tiles for the current player.

        The Nova discipline path is the dedicated widening route: every
        acquired node in it adds one radius step, so each pick reaches
        farther and the fully mastered path more than doubles the blast
        reach. Equipment class-skill affixes stack on top.
        """
        radius = NOVA_BASE_RADIUS + NOVA_RADIUS_PER_NOVA_NODE * path_progress(
            set(self.player.skill_upgrades), self.player.class_name, "Nova"
        )
        if self.equipment_class_skill_bonus():
            radius += 0.25
        if self.equipment_class_skill_bonus("Nova radius"):
            radius += 0.35
        return radius

    def nova_engulfs_room(self) -> bool:
        """True when Frost Nova blankets the player's whole room.

        The maximum reach: mastering the Nova path plus a second full
        discipline path (the run's entire two-path commitment) lets the
        nova catch every foe in the room the Arcanist stands in, regardless
        of distance. Foes outside the room still need the radius.
        """
        done = completed_paths(set(self.player.skill_upgrades), self.player.class_name)
        return "Nova" in done and len(done) >= MAX_COMMITTED_PATHS

    def player_cast_nova(self) -> None:
        if self.player.class_name != "Arcanist":
            return
        mana_cost = self.class_skill_mana_cost()
        if self.player.class_skill_timer > 0 or self.player.mana < mana_cost:
            return
        self.player.class_skill_timer = self.class_skill_cooldown()
        self.player.mana -= mana_cost
        self.set_player_action_visual("cast", 0.32)
        radius = self.nova_radius()
        room = (
            self.dungeon.room_at(self.player.x, self.player.y)
            if self.nova_engulfs_room()
            else None
        )
        # The cast ring expands to the true blast edge so every Nova-path
        # pick is visible in play. It deliberately stays at blast size even
        # at the max effect: room-scale impact overlays rasterize thousands
        # of pixels per frame and plant their perspective ground ellipse
        # (offset by radius // 3) tiles below the caster. The room-filling
        # spectacle is the light wave's job, not the ring's.
        self.add_impact(
            self.player.x,
            self.player.y,
            self.skill_color(),
            ttl=0.48,
            radius=radius / _NOVA_RING_EXPANSION,
            kind="cast",
            archetype=self.player.class_name,
        )
        if self.nova_engulfs_room():
            # Max-effect spectacle: light bursts from the caster and floods
            # the surrounding chamber — a room, a corridor stretch, or both
            # sides of a doorway — stopping at walls and doors, open or
            # closed, exactly like the blast.
            self.trigger_room_flash(self.player.x, self.player.y)
        self.apply_story_blood_price("nova")
        hits = 0
        for enemy in list(self.enemies):
            dx = enemy.x - self.player.x
            dy = enemy.y - self.player.y
            distance = math.hypot(dx, dy)
            in_reach = distance <= radius
            if not in_reach and room is not None:
                # Max effect: the nova engulfs the whole room, so any foe in
                # the same room is caught regardless of distance.
                in_reach = self.dungeon.room_at(enemy.x, enemy.y) is room
            if in_reach and self.dungeon.line_of_sight(
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
                    DamageContext(
                        target=enemy,
                        amount=damage,
                        damage_type=damage_type,
                        knockback_from=direction,
                        status_effect=status_effect,
                        status_duration=status_duration,
                        source="nova",
                    )
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
