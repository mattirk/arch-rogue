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
"""Friendly NPCs that join the fight (4.8.10, "Glory to the machine" Part B).

Greeted bar patrons, garden wanderers, and bar dancers — plus the Story
Guest once its dialogue resolves and the Lossless Soul once her reflection
resolves — become killable combat allies. Modeled on ``update_familiars``:
aggressive NPCs leave the music-beat wander, pick the nearest living enemy
with line of sight inside a 9-tile leash of their home anchor, chase it with
the shared 4.8.9 distance-field/greedy movement, and attack on their own
timer. Damage routes through ``DamageContext``/``damage_enemy`` while acting
as the greeting player, so kill XP, gold, and credit land on the greeter
exactly like familiar kills. With no enemy in leash they walk home and the
beat wander resumes (``aggressive`` stays true for the rest of the run).
"""
# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

import math
from typing import Iterator, NamedTuple

from ..constants import GREETABLE_IDLE_NPC_KINDS
from ..models import Enemy, FloatingText, IdleNpc, Projectile, StoryGuest
from .damage import DamageContext
from .pathing import NAV_STALL_LATCH_SECONDS

NpcAlly = IdleNpc | StoryGuest


class NpcAllyStats(NamedTuple):
    """Base combat statline for one greetable kind (pre depth/difficulty)."""

    max_hp: int
    damage: int
    attack_range: float
    attack_cooldown: float
    combat_speed: float
    damage_type: str


# Authored per-kind statlines. The barkeep-ish bar patron is the sturdy
# bruiser of the roster, the gardener a quick light melee, the dancer a fast
# flurry of low-damage hits, the soul a ranged ward-bolt caster, and the
# resolved Story Guest a balanced blade. Scaled by depth and difficulty in
# ``npc_ally_stats`` (the ``familiar_stats`` idiom: explicit, felt steps).
NPC_ALLY_STATS: dict[str, NpcAllyStats] = {
    "bar": NpcAllyStats(34, 7, 1.15, 1.05, 1.9, "physical"),
    "garden": NpcAllyStats(26, 6, 1.1, 0.82, 2.2, "physical"),
    "bar_dancer": NpcAllyStats(22, 4, 1.1, 0.55, 2.6, "physical"),
    "lossless_soul": NpcAllyStats(24, 8, 4.2, 1.5, 1.7, "arcane"),
    "guest": NpcAllyStats(30, 7, 1.15, 0.9, 2.0, "physical"),
}

# One authored greeting line per greetable kind, spoken as a floater when the
# player recruits the NPC. No cutscene — the fight talk stays in the world.
NPC_GREETING_LINES: dict[str, str] = {
    "bar": "“The road drinks alone. I'd rather swing beside you.”",
    "garden": "“The garden keeps its own — and now it keeps you.”",
    "bar_dancer": "“One more dance, then — with steel for a partner!”",
}


class _NpcAlliesCombatMixin:
    # ------------------------------------------------------------------
    # NPC allies — greeted flavor NPCs, the resolved Guest, and the Soul.
    # ------------------------------------------------------------------
    NPC_ALLY_LEASH = 9.0
    NPC_ALLY_HOME_ARRIVE = 0.45
    NPC_ALLY_COLLISION_RADIUS = 0.27
    NPC_ALLY_PLAYER_CLEARANCE = 0.55
    NPC_ALLY_WARD_BOLT_SPEED = 6.5
    NPC_GREET_RANGE = 1.25

    def npc_ally_stats(self, kind: str) -> NpcAllyStats:
        """The scaled combat statline for an ally of ``kind``.

        Depth grows allies alongside the dungeon (+12% HP/damage per depth)
        and difficulty follows the enemy multipliers at half weight, so a
        recruited barkeep is a real comrade on Hell without outfighting the
        descender who greeted him.
        """
        base = NPC_ALLY_STATS.get(kind) or NPC_ALLY_STATS["guest"]
        depth_scale = 1.0 + 0.12 * max(0, self.current_depth - 1)
        difficulty = self.difficulty_profile()
        hp_scale = depth_scale * (0.5 + 0.5 * difficulty.enemy_hp_multiplier)
        damage_scale = depth_scale * (
            0.5 + 0.5 * difficulty.enemy_damage_multiplier
        )
        return NpcAllyStats(
            max_hp=max(1, int(round(base.max_hp * hp_scale))),
            damage=max(1, int(round(base.damage * damage_scale))),
            attack_range=base.attack_range,
            attack_cooldown=base.attack_cooldown,
            combat_speed=base.combat_speed,
            damage_type=base.damage_type,
        )

    def npc_ally_damage_type(self, npc: NpcAlly) -> str:
        kind = self._npc_ally_kind(npc)
        stats = NPC_ALLY_STATS.get(kind) or NPC_ALLY_STATS["guest"]
        return stats.damage_type

    @staticmethod
    def _npc_ally_kind(npc: NpcAlly) -> str:
        return "guest" if isinstance(npc, StoryGuest) else npc.kind

    def _roll_npc_ally_stats(self, npc: NpcAlly) -> None:
        """Lazily roll combat stats and home anchor (``max_hp == 0`` gate)."""
        if npc.max_hp > 0:
            return
        stats = self.npc_ally_stats(self._npc_ally_kind(npc))
        npc.max_hp = stats.max_hp
        npc.hp = stats.max_hp
        npc.damage = stats.damage
        npc.attack_range = stats.attack_range
        npc.attack_cooldown = stats.attack_cooldown
        npc.combat_speed = stats.combat_speed
        npc.home_x = npc.x
        npc.home_y = npc.y

    def make_npc_combat_ally(self, npc: NpcAlly, greeter_id: str = "") -> None:
        """Flip an NPC aggressive with rolled stats and kill-credit binding."""
        npc.aggressive = True
        if greeter_id:
            npc.greeter_id = greeter_id
        self._roll_npc_ally_stats(npc)

    # ------------------------------------------------------------------
    # B2 — greeting interaction (bar / garden / bar_dancer).
    # ------------------------------------------------------------------

    def nearby_greetable_npc(self) -> IdleNpc | None:
        """The closest un-greeted bar/garden/dancer NPC within greet reach."""
        player = getattr(self, "player", None)
        if player is None:
            return None
        nearby = [
            npc
            for npc in getattr(self, "idle_npcs", [])
            if npc.kind in GREETABLE_IDLE_NPC_KINDS
            and not npc.aggressive
            and math.hypot(npc.x - player.x, npc.y - player.y)
            < self.NPC_GREET_RANGE
        ]
        return min(
            nearby,
            key=lambda npc: math.hypot(npc.x - player.x, npc.y - player.y),
            default=None,
        )

    def greet_idle_npc(self, npc: IdleNpc) -> bool:
        """Recruit a greetable NPC: flag, stats, credit id, one spoken line.

        Runs on the host for both descenders (a joiner's greet arrives as an
        ``interact`` intent under ``acting_as_player``), so ``self.player``
        is always the greeting actor for kill credit.
        """
        if npc.kind not in GREETABLE_IDLE_NPC_KINDS or npc.aggressive:
            return False
        self.make_npc_combat_ally(npc, greeter_id=self.player.player_id)
        line = NPC_GREETING_LINES.get(npc.kind, "")
        if line:
            self.floaters.append(
                FloatingText(line, npc.x, npc.y - 0.6, npc.color, ttl=1.8)
            )
        self.add_impact(
            npc.x, npc.y, npc.color, ttl=0.42, radius=0.52, kind="burst"
        )
        self.play_sfx("shrine")
        self.save_run()
        return True

    # ------------------------------------------------------------------
    # B3 — ally update loop, modeled on ``update_familiars``.
    # ------------------------------------------------------------------

    def iter_npc_allies(self) -> Iterator[NpcAlly]:
        """Living aggressive NPC combatants (idle NPCs + resolved guests)."""
        for npc in getattr(self, "idle_npcs", ()):
            if npc.aggressive and npc.alive:
                yield npc
        for guest in getattr(self, "story_guests", ()):
            if guest.aggressive and guest.alive:
                yield guest

    def update_npc_allies(self, dt: float) -> None:
        """Perceive, chase, attack, and walk home for each aggressive NPC.

        Allies tick on plain ``dt`` (Time Skip slows enemies, never friends),
        pick targets allocation-free with the familiar LOS contract, and hand
        movement to the shared distance-field/greedy seam so they corner like
        4.8.9 enemies instead of grinding along the bar wall.
        """
        allies = tuple(self.iter_npc_allies())
        if not allies:
            return
        for npc in allies:
            self._roll_npc_ally_stats(npc)
            npc.attack_timer = max(0.0, npc.attack_timer - dt)
            if npc.nav_latch > 0.0:
                npc.nav_latch = max(0.0, npc.nav_latch - dt)
            target = self._npc_ally_target(npc)
            motion = self.friendly_npc_motion(npc)
            if target is None:
                self._npc_ally_return_home(npc, motion, dt)
                continue
            if not npc.combat_active:
                npc.combat_active = True
                # Park the wander waypoint on the NPC so the dance resumes
                # in place after the fight rather than chasing a stale target.
                motion.target_x = npc.x
                motion.target_y = npc.y
            dx = target.x - npc.x
            dy = target.y - npc.y
            distance = math.hypot(dx, dy)
            if distance > 0.001:
                motion.facing_x = dx / distance
                motion.facing_y = dy / distance
            stop_distance = max(0.6, npc.attack_range - 0.15)
            motion.moving = False
            if distance > stop_distance:
                nx, ny = (
                    (dx / distance, dy / distance)
                    if distance > 0.001
                    else (0.0, 0.0)
                )
                nav = self._enemy_nav_direction(npc, target)
                if nav is not None:
                    nx, ny = nav
                step = min(npc.combat_speed * dt, distance - stop_distance)
                moved = self._move_npc_ally(npc, nx * step, ny * step)
                if step > 0.02 and moved < step * 0.3:
                    npc.nav_latch = NAV_STALL_LATCH_SECONDS
                motion.moving = moved > 0.0
            if (
                distance <= npc.attack_range
                and npc.attack_timer <= 0.0
                and self.dungeon.line_of_sight(npc.x, npc.y, target.x, target.y)
            ):
                self._npc_ally_attack(npc, target)

    def _npc_ally_target(self, npc: NpcAlly) -> Enemy | None:
        """Nearest living enemy with LOS inside the leash around home."""
        best: Enemy | None = None
        best_dist_sq = self.NPC_ALLY_LEASH * self.NPC_ALLY_LEASH
        leash_sq = best_dist_sq
        for enemy in self.nearby_enemies(
            npc.x,
            npc.y,
            self.NPC_ALLY_LEASH,
        ):
            if not enemy.alive:
                continue
            home_dx = enemy.x - npc.home_x
            home_dy = enemy.y - npc.home_y
            if home_dx * home_dx + home_dy * home_dy > leash_sq:
                continue
            dx = enemy.x - npc.x
            dy = enemy.y - npc.y
            dist_sq = dx * dx + dy * dy
            if dist_sq >= best_dist_sq:
                continue
            if not self.dungeon.line_of_sight(npc.x, npc.y, enemy.x, enemy.y):
                continue
            best_dist_sq = dist_sq
            best = enemy
        return best

    def _npc_ally_return_home(self, npc: NpcAlly, motion, dt: float) -> None:
        """Walk a disengaged ally back to its anchor, then resume the wander."""
        if not npc.combat_active:
            return
        dx = npc.home_x - npc.x
        dy = npc.home_y - npc.y
        distance = math.hypot(dx, dy)
        if distance <= self.NPC_ALLY_HOME_ARRIVE:
            self._npc_ally_stand_down(npc, motion)
            return
        nx, ny = dx / distance, dy / distance
        motion.facing_x = nx
        motion.facing_y = ny
        step = min(npc.combat_speed * dt, distance)
        moved = self._move_npc_ally(npc, nx * step, ny * step)
        motion.moving = moved > 0.0
        if step > 0.02 and moved < step * 0.3:
            # Pressed against a barrel or packmate: hand control back to the
            # beat wander, whose waypoint picker routes around furnishings.
            self._npc_ally_stand_down(npc, motion)

    def _npc_ally_stand_down(self, npc: NpcAlly, motion) -> None:
        npc.combat_active = False
        motion.moving = False
        motion.target_x = npc.x
        motion.target_y = npc.y

    def _move_npc_ally(self, npc: NpcAlly, dx: float, dy: float) -> float:
        """Axis-probed ally locomotion returning the distance moved.

        Allies skip ``move_actor`` for the same reason familiars do (its
        contact pass assumes Enemy fields) and add one courtesy rule: the
        ally yields to player actors instead of shoving them, backing off
        to ``NPC_ALLY_PLAYER_CLEARANCE`` when a step would overlap.
        """
        old_x, old_y = npc.x, npc.y
        radius = self.NPC_ALLY_COLLISION_RADIUS
        new_x = npc.x + dx
        if not self.dungeon.blocked_for_radius(new_x, npc.y, radius):
            npc.x = new_x
        new_y = npc.y + dy
        if not self.dungeon.blocked_for_radius(npc.x, new_y, radius):
            npc.y = new_y
        for player in self.active_players():
            px_dx = npc.x - player.x
            px_dy = npc.y - player.y
            px_dist = math.hypot(px_dx, px_dy)
            clearance = self.NPC_ALLY_PLAYER_CLEARANCE
            if 0.001 < px_dist < clearance:
                nx, ny = px_dx / px_dist, px_dy / px_dist
                pushed_x = npc.x + nx * (clearance - px_dist)
                pushed_y = npc.y + ny * (clearance - px_dist)
                if not self.dungeon.blocked_for_radius(
                    pushed_x, pushed_y, radius
                ):
                    npc.x = pushed_x
                    npc.y = pushed_y
        return math.hypot(npc.x - old_x, npc.y - old_y)

    def _npc_ally_attack(self, npc: NpcAlly, enemy: Enemy) -> None:
        """Strike (or ward-bolt) as the greeter so credit routes correctly."""
        npc.attack_timer = npc.attack_cooldown
        if npc.attack_range > 2.0:
            self._npc_ally_cast(npc, enemy)
            return
        damage = npc.damage + self.rng.randrange(0, 3)
        with self.acting_as_player(self.player_for_credit(npc.greeter_id)):
            self.damage_enemy(
                DamageContext(
                    target=enemy,
                    amount=damage,
                    damage_type=self.npc_ally_damage_type(npc),
                    source="npc_ally",
                )
            )
        aim_dx = enemy.x - npc.x
        aim_dy = enemy.y - npc.y
        aim_length = math.hypot(aim_dx, aim_dy)
        if aim_length > 0.001:
            aim_dx /= aim_length
            aim_dy /= aim_length
        self.add_slash(
            (npc.x + enemy.x) * 0.5,
            (npc.y + enemy.y) * 0.5,
            0.14,
            aim_dx,
            aim_dy,
        )
        if enemy.alive:
            # Point the victim's memory at the ally that struck it; the
            # generalized targeting then decides whom to fight.
            self.alert_enemy(enemy, npc.x, npc.y)

    def _npc_ally_cast(self, npc: NpcAlly, enemy: Enemy) -> None:
        """The Lossless Soul's ward-bolt: a player-owned homing-free bolt.

        Owner ``"player"`` + the greeter's ``owner_id`` reuses the existing
        projectile hit pass, so damage, credit, and delayed kills route like
        any descender bolt with zero new collision code.
        """
        dx = enemy.x - npc.x
        dy = enemy.y - npc.y
        distance = math.hypot(dx, dy)
        if distance <= 0.001:
            return
        nx, ny = dx / distance, dy / distance
        speed = self.NPC_ALLY_WARD_BOLT_SPEED
        self.add_impact(
            npc.x, npc.y, npc.color, ttl=0.26, radius=0.34, kind="cast"
        )
        self.projectiles.append(
            Projectile(
                npc.x,
                npc.y,
                nx * speed,
                ny * speed,
                npc.damage + self.rng.randrange(0, 3),
                "player",
                npc.color,
                ttl=0.9,
                damage_type=self.npc_ally_damage_type(npc),
                owner_id=npc.greeter_id,
            )
        )

    # ------------------------------------------------------------------
    # Damage intake and death.
    # ------------------------------------------------------------------

    def take_npc_damage(
        self, npc: NpcAlly, amount: int, source: Enemy | None = None
    ) -> None:
        """Damage sink for allied NPCs (mirrors ``_familiar_take_damage``)."""
        self._roll_npc_ally_stats(npc)
        npc.hp -= max(1, amount)
        self.floaters.append(
            FloatingText(
                f"-{max(1, amount)}", npc.x, npc.y - 0.25, (235, 90, 80), ttl=0.6
            )
        )
        self.add_impact(
            npc.x,
            npc.y,
            self.damage_type_color(self.npc_ally_damage_type(npc)),
            ttl=0.22,
            radius=0.28,
            kind="hit",
        )
        if npc.hp <= 0:
            self._kill_npc_ally(npc)

    def _kill_npc_ally(self, npc: NpcAlly) -> None:
        """Remove a fallen ally with a farewell; resolved rooms lose nothing."""
        name = npc.name or "The ally"
        self.floaters.append(
            FloatingText(f"{name} falls", npc.x, npc.y - 0.55, npc.color, ttl=1.5)
        )
        self.add_impact(
            npc.x, npc.y, npc.color, ttl=0.52, radius=0.6, kind="death"
        )
        if isinstance(npc, StoryGuest):
            self.story_guests = [g for g in self.story_guests if g is not npc]
        else:
            self.idle_npcs = [n for n in self.idle_npcs if n is not npc]
        self._drop_nav_field_for(npc)
        self.play_sfx("death")
