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
"""Enemy AI per-frame update, ability executors, and perception.

4.8.9 machine intelligence: behavior is driven by per-role tactics
(:func:`arch_rogue.combat.abilities.enemy_tactic`), authored abilities
dispatched through the windup/commit seam, a shared per-player distance
field for cornering (:mod:`arch_rogue.combat.pathing`), and an
idle/engaged perception model with damage aggro, one-hop pack alerts, and
short target memory. Enemies without authored abilities synthesize their
default strike/bolt from the stat columns and keep the pre-4.8.9 cadence.
"""
# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

import math
from ..content import EnemyAbility
from ..models import (
    Enemy,
    FloatingText,
    Player,
    Projectile,
)

from ._utils import (
    BOSS_FOOTPRINT_HIT_RADIUS,
    ENEMY_ALERT_MEMORY,
    ENEMY_ALERT_RADIUS,
    ENEMY_BOSS_WINDUP,
    ENEMY_CAST_WINDUP,
    ENEMY_MELEE_WINDUP,
    ENEMY_MEMORY_ARRIVE_DISTANCE,
    ENEMY_SEPARATION_BIAS,
    ENEMY_SEPARATION_FRACTION,
    KNOCKBACK_CHAIN_ARC_DOT,
    KNOCKBACK_CHAIN_MIN_SPEED,
    KNOCKBACK_CHAIN_TRANSFER,
    KNOCKBACK_DECAY_RATE,
)
from .abilities import (
    ABILITY_INDEX,
    LEGACY_CAST_KEY,
    LEGACY_MELEE_KEY,
    ability_attack_range,
    boss_phase_cooldown_factor,
    enemy_tactic,
    select_boss_attack,
)
from .pathing import NAV_STALL_LATCH_SECONDS

# Chokepoint yield: how long a boxed-in enemy keeps clearing away from a
# packmate that is ahead in the queue before re-approaching. Long enough to
# open a full body-width of lane at typical enemy speeds.
ENEMY_YIELD_SECONDS = 0.55
# Stuck probe: net-displacement window. An engaged enemy that wants to close
# but covered a small fraction of its expected ground in this window is
# wedged, however busy its per-frame micro-moves look.
ENEMY_STUCK_PROBE_SECONDS = 0.9


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
        speed = math.hypot(kvx, kvy)
        if speed >= KNOCKBACK_CHAIN_MIN_SPEED:
            self._chain_knockback_through_pack(enemy, kvx, kvy, speed, dt)
        moved = self.move_actor(enemy, kvx * dt, kvy * dt)
        if moved > 0.0:
            enemy.moving = True
        decay = math.exp(-KNOCKBACK_DECAY_RATE * dt)
        enemy.knockback_vx = kvx * decay
        enemy.knockback_vy = kvy * decay
        if abs(enemy.knockback_vx) < 0.01 and abs(enemy.knockback_vy) < 0.01:
            enemy.knockback_vx = 0.0
            enemy.knockback_vy = 0.0

    def _chain_knockback_through_pack(
        self, enemy: Enemy, kvx: float, kvy: float, speed: float, dt: float
    ) -> None:
        """A hurled enemy shoves packmates out of its flight path.

        Contact resolution ejects the *mover* from any body overlap, so a
        Big Hit throw would otherwise dead-stop on the first packmate behind
        the target (~0.06 of the 2.0 tiles, measured). Instead of weakening
        collision, transfer most of the remaining velocity to bodies ahead in
        the path so the pack plows backwards together — the same group-flight
        dynamics the Warden's throw-everyone rider already shows. Pure
        physics: no damage, no statuses, and the transfer only ever raises a
        slower body's velocity (never re-boosts), so chains decay by
        ``KNOCKBACK_CHAIN_TRANSFER`` per hop and cannot ping-pong. Oversized
        bosses (size >= 2) are immovable bulk: the flier thuds against them
        exactly as before.
        """
        nx, ny = kvx / speed, kvy / speed
        my_radius = self.enemy_hit_radius(enemy)
        reach = my_radius + BOSS_FOOTPRINT_HIT_RADIUS + speed * dt + 0.15
        transferred = speed * KNOCKBACK_CHAIN_TRANSFER
        for other in self.nearby_enemies(enemy.x, enemy.y, reach):
            if other is enemy or other.size >= 2:
                continue
            dx = other.x - enemy.x
            dy = other.y - enemy.y
            distance = math.hypot(dx, dy)
            pair_reach = my_radius + self.enemy_hit_radius(other) + speed * dt
            if distance > pair_reach:
                continue
            if (
                distance > 0.001
                and (dx * nx + dy * ny) / distance < KNOCKBACK_CHAIN_ARC_DOT
            ):
                continue
            if math.hypot(other.knockback_vx, other.knockback_vy) >= transferred:
                continue
            other.knockback_vx = nx * transferred
            other.knockback_vy = ny * transferred

    def _enemy_windup_duration(self, enemy: Enemy) -> float:
        """Telegraph windup (seconds) for an enemy's next attack."""
        if enemy.kind == "boss" or enemy.is_boss_encounter:
            return ENEMY_BOSS_WINDUP
        if enemy.kind == "ranged":
            return ENEMY_CAST_WINDUP
        return ENEMY_MELEE_WINDUP

    def _commit_enemy_attack(self, enemy: Enemy, attack: str, nx: float = 0.0, ny: float = 0.0) -> None:
        """Commit to an attack: start the windup telegraph instead of firing now.

        ``attack`` is an ability key — "melee"/"cast" for the synthesized
        defaults, or an authored ``EnemyAbility`` key. ``nx``/``ny`` snapshot
        the cast aim so a projectile (fired on windup completion) travels
        along the committed direction and is dodgeable after launch. Authored
        abilities may override the per-kind windup duration. No-op if already
        winding up.
        """
        if enemy.windup_time > 0.0:
            return
        duration = self._enemy_windup_duration(enemy)
        ability = ABILITY_INDEX.get(attack)
        if ability is not None and ability.windup > 0.0:
            duration = ability.windup
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
        Authored abilities spend their rotation cooldown here (fire time), so
        a stun that cancels the windup does not burn the ability.
        """
        attack = enemy.windup_attack
        enemy.windup_attack = ""
        if not attack:
            return
        ability = ABILITY_INDEX.get(attack)
        if ability is not None and ability.effect in ("bolt", "fan"):
            enemy.last_attack_kind = "cast"
        elif ability is None and attack == LEGACY_CAST_KEY:
            enemy.last_attack_kind = "cast"
        else:
            enemy.last_attack_kind = "melee"
        if ability is None:
            if attack == LEGACY_CAST_KEY:
                self.enemy_cast(
                    enemy,
                    enemy.windup_nx,
                    enemy.windup_ny,
                    line_of_sight_confirmed=True,
                )
            else:
                self.enemy_melee(enemy, line_of_sight_confirmed=True)
            return
        enemy.last_ability = attack
        enemy.ability_timers[attack] = ability.cooldown * boss_phase_cooldown_factor(
            enemy
        )
        if ability.effect == "strike":
            self.enemy_melee(enemy, ability=ability, line_of_sight_confirmed=True)
        elif ability.effect in ("bolt", "fan"):
            self.enemy_cast(
                enemy,
                enemy.windup_nx,
                enemy.windup_ny,
                ability=ability,
                line_of_sight_confirmed=True,
            )
        elif ability.effect == "nova":
            self.enemy_nova(enemy, ability)

    def alert_enemy(self, enemy: Enemy, target_x: float, target_y: float) -> None:
        """Engage an enemy and refresh its target memory.

        The first transition into the engaged state alerts idle packmates
        within ENEMY_ALERT_RADIUS (one hop — alerted enemies do not chain,
        keeping the wave bounded). Damage sinks call this too, so sniping an
        enemy from outside its aggro radius is no longer free.
        """
        newly_engaged = enemy.ai_state != "engaged"
        enemy.ai_state = "engaged"
        enemy.memory_x = target_x
        enemy.memory_y = target_y
        enemy.alert_timer = ENEMY_ALERT_MEMORY
        if not newly_engaged:
            return
        radius_sq = ENEMY_ALERT_RADIUS * ENEMY_ALERT_RADIUS
        for other in self.nearby_enemies(
            enemy.x,
            enemy.y,
            ENEMY_ALERT_RADIUS,
        ):
            if other is enemy or other.ai_state == "engaged":
                continue
            dx = other.x - enemy.x
            dy = other.y - enemy.y
            if dx * dx + dy * dy <= radius_sq:
                other.ai_state = "engaged"
                other.memory_x = target_x
                other.memory_y = target_y
                other.alert_timer = ENEMY_ALERT_MEMORY

    def _enemy_strafe_sign(self, enemy: Enemy) -> float:
        """Stable strafe side for this enemy; position-derived, no RNG."""
        if enemy.strafe_sign == 0.0:
            enemy.strafe_sign = (
                1.0 if (int(enemy.x) + int(enemy.y)) % 2 == 0 else -1.0
            )
        return enemy.strafe_sign

    def _separation_adjusted_direction(
        self, enemy: Enemy, nx: float, ny: float
    ) -> tuple[float, float]:
        """Blend a small away-from-packmate bias into an advance direction.

        Keeps approaching packs fanned out instead of funneling into one
        shoving column; ``resolve_actor_contacts`` stays the hard backstop.
        """
        if len(self.enemies) <= 1:
            return nx, ny
        radius = self.enemy_hit_radius(enemy)
        away_x = 0.0
        away_y = 0.0
        best_sq: float | None = None
        for other in self.nearby_enemies(
            enemy.x,
            enemy.y,
            (radius + BOSS_FOOTPRINT_HIT_RADIUS)
            * ENEMY_SEPARATION_FRACTION,
        ):
            if other is enemy:
                continue
            dx = enemy.x - other.x
            dy = enemy.y - other.y
            limit = (radius + self.enemy_hit_radius(other)) * ENEMY_SEPARATION_FRACTION
            sq = dx * dx + dy * dy
            if sq < limit * limit and (best_sq is None or sq < best_sq):
                best_sq = sq
                away_x = dx
                away_y = dy
        if best_sq is None or best_sq <= 1e-9:
            return nx, ny
        away_len = math.sqrt(best_sq)
        vx = nx + (away_x / away_len) * ENEMY_SEPARATION_BIAS
        vy = ny + (away_y / away_len) * ENEMY_SEPARATION_BIAS
        length = math.hypot(vx, vy)
        if length < 0.001:
            return nx, ny
        return vx / length, vy / length

    def _flank_adjusted_direction(
        self, enemy: Enemy, nx: float, ny: float, bias: float
    ) -> tuple[float, float]:
        """Curve an approach direction sideways (flanker/skirmisher closes)."""
        sign = self._enemy_strafe_sign(enemy)
        vx = nx - ny * bias * sign
        vy = ny + nx * bias * sign
        length = math.hypot(vx, vy)
        if length < 0.001:
            return nx, ny
        return vx / length, vy / length

    def _advance_enemy(
        self,
        enemy: Enemy,
        nx: float,
        ny: float,
        step: float,
        dt: float,
        locomotion_scale: float,
        target=None,
    ) -> None:
        """Advance step that arms the wall-stall latch when barely moving.

        A planned step that goes nearly nowhere means the enemy is pressed
        into something the greedy direction cannot resolve — a wall corner,
        a solid bar furnishing, or a packmate's back (the distance field
        doesn't see bodies or furnishing boxes). Preferring field descent
        for a short latch window steers around terrain; the leftover step
        additionally resolves the body jam: yield backward when a packmate
        closer to the target contests the same chokepoint (single file
        through doorways), otherwise slide perpendicular so a rear enemy
        orbits into a flank instead of shoving a blocker forever ("only the
        closest one attacks") and a prop-wedged enemy works itself free.
        Unobstructed movement never arms the latch, so open-floor behavior
        is untouched.
        """
        if step <= 0.0:
            return
        if enemy.yield_timer > 0.0:
            # Actively yielding a chokepoint: keep clearing away from the
            # contesting packmate instead of advancing; a one-frame sidestep
            # gets dragged straight back next frame and never frees the lane.
            blocker = self._contact_packmate(enemy)
            if blocker is not None:
                away_x = enemy.x - blocker.x
                away_y = enemy.y - blocker.y
                away_len = math.hypot(away_x, away_y)
                if away_len < 0.001:
                    away_x, away_y, away_len = -nx, -ny, 1.0
                moved = self._move_enemy_locomotion(
                    enemy,
                    (away_x / away_len) * step,
                    (away_y / away_len) * step,
                    dt,
                    locomotion_scale,
                )
                if moved <= step * 0.25:
                    self._move_enemy_locomotion(
                        enemy, -nx * step, -ny * step, dt, locomotion_scale
                    )
                return
            enemy.yield_timer = 0.0
        moved = self._move_enemy_locomotion(
            enemy, nx * step, ny * step, dt, locomotion_scale
        )
        if step > 0.02 and moved < step * 0.3:
            enemy.nav_latch = NAV_STALL_LATCH_SECONDS
            self._resolve_stalled_advance(
                enemy, nx, ny, step - moved, dt, locomotion_scale, target
            )

    def _contact_packmate(self, enemy: Enemy) -> Enemy | None:
        """The nearest packmate pressed against this enemy, if any."""
        radius = self.enemy_hit_radius(enemy)
        best: Enemy | None = None
        best_sq = 0.0
        for other in self.nearby_enemies(
            enemy.x,
            enemy.y,
            radius + BOSS_FOOTPRINT_HIT_RADIUS + 0.15,
        ):
            if other is enemy or not other.alive:
                continue
            dx = other.x - enemy.x
            dy = other.y - enemy.y
            reach = radius + self.enemy_hit_radius(other) + 0.15
            sq = dx * dx + dy * dy
            if sq > reach * reach or sq <= 1e-9:
                continue
            if best is None or sq < best_sq:
                best = other
                best_sq = sq
        return best

    def _update_stuck_probe(
        self, enemy: Enemy, target, scaled_dt: float, distance: float
    ) -> None:
        """Net-displacement watchdog for wedged enemies.

        Oscillating deadlocks (two bodies contesting a doorway lane, a disc
        wedged on a furnishing corner) keep making tiny per-frame moves, so
        the stall handlers never see them as boxed in. This probe compares
        real ground covered over ~a second against what the enemy's speed
        should manage; a wedged enemy either yields to the contact packmate
        ahead of it in the queue or re-arms the field-descent latch.
        """
        if distance <= enemy.attack_range or enemy.yield_timer > 0.0:
            enemy.stuck_probe_timer = 0.0
            return
        if enemy.stuck_probe_timer <= 0.0:
            enemy.stuck_probe_x = enemy.x
            enemy.stuck_probe_y = enemy.y
            enemy.stuck_probe_timer = ENEMY_STUCK_PROBE_SECONDS
            return
        enemy.stuck_probe_timer -= scaled_dt
        if enemy.stuck_probe_timer > 0.0:
            return
        moved_sq = (enemy.x - enemy.stuck_probe_x) ** 2 + (
            enemy.y - enemy.stuck_probe_y
        ) ** 2
        expected = enemy.speed * ENEMY_STUCK_PROBE_SECONDS
        threshold = max(0.12, expected * 0.25)
        if moved_sq >= threshold * threshold:
            return
        blocker = self._contact_packmate(enemy)
        if blocker is not None and target is not None:
            my_sq = (enemy.x - target.x) ** 2 + (enemy.y - target.y) ** 2
            their_sq = (blocker.x - target.x) ** 2 + (blocker.y - target.y) ** 2
            if their_sq < my_sq - 1e-6:
                enemy.yield_timer = ENEMY_YIELD_SECONDS
                return
        enemy.nav_latch = NAV_STALL_LATCH_SECONDS

    def _resolve_stalled_advance(
        self,
        enemy: Enemy,
        nx: float,
        ny: float,
        step: float,
        dt: float,
        locomotion_scale: float,
        target,
    ) -> None:
        """Slide sideways past the obstruction; yield when boxed in.

        Open floor: the perpendicular slide (either side) orbits the enemy
        around whatever blocks it — a packmate's back, a bar barrel, a wall
        corner. When even both slides fail against a packmate ahead in the
        queue, a sustained yield starts immediately (the slower path — the
        net-displacement stuck probe — also arms yields for oscillating
        wedges the per-step checks can't see).
        """
        if step <= 0.0:
            return
        sign = self._enemy_strafe_sign(enemy)
        for attempt_sign in (sign, -sign):
            moved = self._move_enemy_locomotion(
                enemy,
                -ny * attempt_sign * step,
                nx * attempt_sign * step,
                dt,
                locomotion_scale,
            )
            if moved > step * 0.25:
                enemy.strafe_sign = attempt_sign
                return
        enemy.strafe_sign = -sign
        blocker = self._contact_packmate(enemy)
        if blocker is not None and target is not None:
            my_sq = (enemy.x - target.x) ** 2 + (enemy.y - target.y) ** 2
            their_sq = (blocker.x - target.x) ** 2 + (blocker.y - target.y) ** 2
            if their_sq < my_sq - 1e-6:
                enemy.yield_timer = ENEMY_YIELD_SECONDS

    def _reposition_for_line_of_sight(
        self,
        enemy: Enemy,
        target,
        nx: float,
        ny: float,
        move_speed: float,
        dt: float,
        locomotion_scale: float,
    ) -> bool:
        """Sidestep toward a firing line instead of standing wall-blocked.

        Bounded probe: two perpendicular candidates, at most two extra LOS
        traces, and only on frames where the enemy was otherwise
        attack-eligible (ready + in range) but the trace failed.
        """
        perp_x, perp_y = -ny, nx
        sign = self._enemy_strafe_sign(enemy)
        for side in (sign, -sign):
            candidate_x = enemy.x + perp_x * side
            candidate_y = enemy.y + perp_y * side
            if self.dungeon.blocked_for_radius(candidate_x, candidate_y):
                continue
            if not self.dungeon.line_of_sight(
                candidate_x, candidate_y, target.x, target.y
            ):
                continue
            step = move_speed * dt
            moved = self._move_enemy_locomotion(
                enemy, perp_x * side * step, perp_y * side * step, dt, locomotion_scale
            )
            if moved <= step * 0.25:
                enemy.strafe_sign = -sign
            return True
        return False

    def update_enemies(
        self,
        dt: float,
        *,
        time_scale: float | None = None,
        time_skip_remaining: float | None = None,
    ) -> None:
        # One deterministic broad-phase build replaces the historical
        # mover-by-all-enemies contact, separation, and packmate scans. Enemy
        # movement updates its own bucket as the frame advances.
        self._rebuild_enemy_spatial_index()
        # Milestone 3.18 — Time Skip slows the enemy simulation uniformly
        # (movement and attack cadence) without affecting the player.
        if time_scale is None:
            time_scale = self.enemy_time_scale(
                dt, remaining=time_skip_remaining
            )
        scaled_dt = dt * time_scale
        # 4.6 co-op: enemies target the nearest living player, breaking
        # equal-distance ties by stable player id. 4.8.10 Part B widens the
        # candidate set to aggressive living NPC allies (players still win
        # equal-distance ties). Single-player without allies keeps the
        # zero-allocation fast path (the tuple below is the lone player).
        living = self.living_players()
        players = living or self.active_players()
        ally_targets = tuple(self.iter_npc_allies())
        single_target = (
            players[0] if len(players) == 1 and not ally_targets else None
        )
        for enemy in self.enemies:
            enemy.moving = False
            enemy.locomotion_anim_scale = 0.0
            if not living:
                # Every descender has fallen: the pack stands down while the
                # death clip plays out instead of pounding the corpse.
                continue
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
            if enemy.nav_latch > 0.0:
                enemy.nav_latch = max(0.0, enemy.nav_latch - scaled_dt)
            if enemy.yield_timer > 0.0:
                enemy.yield_timer = max(0.0, enemy.yield_timer - scaled_dt)
            if enemy.ability_timers:
                for key in enemy.ability_timers:
                    enemy.ability_timers[key] = max(
                        0.0, enemy.ability_timers[key] - scaled_dt
                    )
            if single_target is not None:
                target_actor = single_target
            else:
                target_actor = self._pick_enemy_target(
                    enemy, players, ally_targets
                )
            player_dx = target_actor.x - enemy.x
            player_dy = target_actor.y - enemy.y
            player_distance = math.hypot(player_dx, player_dy)
            lure = self.ambush_bell_lure_target(enemy)
            in_aggro = player_distance <= enemy.aggro_range or lure is not None
            if in_aggro:
                self.alert_enemy(enemy, target_actor.x, target_actor.y)
            elif enemy.ai_state != "engaged" or enemy.alert_timer <= 0.0:
                continue
            if enemy.statuses.get("stunned", 0.0) > 0:
                enemy.telegraph = "stunned"
                continue
            if not in_aggro:
                # Target memory: drift to the last noticed position for a
                # short while instead of freezing at the aggro radius edge.
                # No attacks out here — the target is beyond aggro range.
                enemy.alert_timer = max(0.0, enemy.alert_timer - scaled_dt)
                memory_dx = enemy.memory_x - enemy.x
                memory_dy = enemy.memory_y - enemy.y
                memory_distance = math.hypot(memory_dx, memory_dy)
                if (
                    enemy.alert_timer <= 0.0
                    or memory_distance <= ENEMY_MEMORY_ARRIVE_DISTANCE
                ):
                    enemy.ai_state = ""
                    continue
                nx = memory_dx / memory_distance
                ny = memory_dy / memory_distance
                enemy.facing_x = nx
                enemy.facing_y = ny
                enemy.locomotion_anim_scale = animation_scale
                move_speed = enemy.speed * locomotion_scale
                step = min(
                    move_speed * dt,
                    memory_distance - ENEMY_MEMORY_ARRIVE_DISTANCE * 0.5,
                )
                if step > 0.0:
                    self._move_enemy_locomotion(
                        enemy, nx * step, ny * step, dt, locomotion_scale
                    )
                continue

            target_x = lure.x if lure is not None else target_actor.x
            target_y = lure.y if lure is not None else target_actor.y
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
            self._update_stuck_probe(enemy, target_actor, scaled_dt, distance)

            is_boss = enemy.kind == "boss" or enemy.is_boss_encounter
            boss_attack: str | None = None
            # Enemies must actually see the player to attack; movement remains
            # intentionally ungated so pursuit around corners still works. Trace
            # LOS only when the pre-movement state could attack this frame. This
            # preserves the former attack position/ordering while avoiding a wall
            # walk for distant enemies and enemies whose cooldown is still active.
            attack_ready = enemy.attack_timer <= 0
            if lure is not None:
                attack_in_range = player_distance <= enemy.attack_range
            elif is_boss:
                boss_attack = select_boss_attack(enemy, distance)
                attack_in_range = boss_attack is not None
            else:
                attack_in_range = distance <= enemy.attack_range
            los_clear = False
            los_checked = attack_ready and attack_in_range
            if los_checked:
                los_clear = self.dungeon.line_of_sight(
                    enemy.x, enemy.y, target_actor.x, target_actor.y
                )
            has_los = los_checked and los_clear

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

            if is_boss:
                # Boss encounters (final tyrant + floor guardians) close the
                # gap and weave authored abilities into the legacy pressure
                # pattern: rotation specials when off cooldown and in band,
                # cast at mid range, crush with melee up close.
                stop_distance = self._enemy_melee_stop_distance(enemy)
                if distance > stop_distance:
                    nav = self._enemy_nav_direction(enemy, target_actor)
                    if nav is not None:
                        # Field descent (doorways, corridors, detours): keep
                        # the routed direction pure — the separation fan-out
                        # fights the route and wedged doorway pairs against
                        # the jambs. Single file is correct here.
                        step_nx, step_ny = nav
                    else:
                        step_nx, step_ny = self._separation_adjusted_direction(
                            enemy, nx, ny
                        )
                    step = min(move_speed * dt, distance - stop_distance)
                    self._advance_enemy(
                        enemy,
                        step_nx,
                        step_ny,
                        step,
                        dt,
                        locomotion_scale,
                        target=target_actor,
                    )
                if boss_attack is not None and attack_ready and has_los:
                    self._commit_enemy_attack(enemy, boss_attack, nx, ny)
            elif enemy.kind == "ranged":
                tactic = enemy_tactic(enemy)
                preferred_range = tactic.preferred_range
                min_range = tactic.min_range
                # hold_anchor: plant at the first spot the target is already
                # inside attack range instead of closing to the preferred
                # band. Never holds where it cannot fire — a holding enemy
                # is always one cooldown away from attacking, not stalled.
                holding = tactic.hold_anchor and distance <= enemy.attack_range
                repositioned = False
                if (
                    los_checked
                    and not los_clear
                    and tactic.reposition_for_los
                ):
                    repositioned = self._reposition_for_line_of_sight(
                        enemy,
                        target_actor,
                        nx,
                        ny,
                        move_speed,
                        dt,
                        locomotion_scale,
                    )
                if repositioned:
                    pass
                elif distance > preferred_range:
                    if not holding:
                        nav = self._enemy_nav_direction(enemy, target_actor)
                        if nav is not None:
                            # Routed: no separation fan-out (see boss branch).
                            step_nx, step_ny = nav
                        else:
                            step_nx, step_ny = self._separation_adjusted_direction(
                                enemy, nx, ny
                            )
                        step = min(move_speed * dt, distance - preferred_range)
                        self._advance_enemy(
                            enemy,
                            step_nx,
                            step_ny,
                            step,
                            dt,
                            locomotion_scale,
                            target=target_actor,
                        )
                elif distance < min_range:
                    step = min(move_speed * dt, min_range - distance)
                    self._move_enemy_locomotion(
                        enemy, -nx * step, -ny * step, dt, locomotion_scale
                    )
                elif tactic.strafe_bias > 0.0 and not attack_ready:
                    # In band with the attack recovering: drift sideways so
                    # skirmishers orbit instead of standing in the open.
                    sign = self._enemy_strafe_sign(enemy)
                    step = move_speed * dt * tactic.strafe_bias
                    moved = self._move_enemy_locomotion(
                        enemy, -ny * sign * step, nx * sign * step, dt, locomotion_scale
                    )
                    if moved <= step * 0.25:
                        enemy.strafe_sign = -sign
                if (
                    distance <= enemy.attack_range
                    and attack_ready
                    and has_los
                ):
                    self._commit_enemy_attack(enemy, "cast", nx, ny)
            else:
                tactic = enemy_tactic(enemy)
                stop_distance = self._enemy_melee_stop_distance(enemy)
                if distance > stop_distance:
                    nav = self._enemy_nav_direction(enemy, target_actor)
                    if nav is not None:
                        # Routed: no fan-out (see boss branch) — single file
                        # through doorways beats a wedged pair.
                        step_nx, step_ny = nav
                    else:
                        step_nx, step_ny = nx, ny
                        if (
                            tactic.strafe_bias > 0.0
                            and distance > stop_distance + 1.0
                        ):
                            # Flankers curve toward a side while closing
                            # instead of stacking onto the same vector.
                            step_nx, step_ny = self._flank_adjusted_direction(
                                enemy, step_nx, step_ny, tactic.strafe_bias
                            )
                        step_nx, step_ny = self._separation_adjusted_direction(
                            enemy, step_nx, step_ny
                        )
                    step = min(
                        move_speed * dt, distance - stop_distance
                    )
                    self._advance_enemy(
                        enemy,
                        step_nx,
                        step_ny,
                        step,
                        dt,
                        locomotion_scale,
                        target=target_actor,
                    )
                if distance <= enemy.attack_range and attack_ready and has_los:
                    self._commit_enemy_attack(enemy, "melee")

    def _pick_enemy_target(self, enemy: Enemy, players, ally_targets):
        """Nearest of the given players and NPC allies for this enemy.

        Equal-distance ties break to players first (by stable player id), so
        pre-4.8.10 co-op targeting is preserved verbatim; NPC allies then
        order by their own stable-enough identity for determinism within a
        host frame.
        """
        return min(
            (*players, *ally_targets),
            key=lambda t: (
                (t.x - enemy.x) ** 2 + (t.y - enemy.y) ** 2,
                getattr(t, "player_id", None) is None,
                getattr(t, "player_id", "") or getattr(t, "name", ""),
            ),
        )

    def enemy_target(self, enemy: Enemy):
        """Nearest living target: players ∪ aggressive living NPC allies.

        4.8.10 Part B generalization of the former ``enemy_target_player``.
        Familiars are deliberately absent — they draw blows only through
        retaliation, as before.
        """
        players = self.living_players() or self.active_players()
        ally_targets = tuple(self.iter_npc_allies())
        if not ally_targets:
            if not players:
                return None
            if len(players) == 1:
                return players[0]
        return self._pick_enemy_target(enemy, players, ally_targets)

    def enemy_melee(
        self,
        enemy: Enemy,
        *,
        ability: EnemyAbility | None = None,
        line_of_sight_confirmed: bool = False,
    ) -> None:
        victim = self.enemy_target(enemy)
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
        base_damage = enemy.damage
        if ability is not None:
            base_damage = max(1, int(round(enemy.damage * ability.damage_multiplier)))
        raw = base_damage + self.rng.randrange(-2, 3)
        if isinstance(victim, Player):
            amount = self.take_player_damage(
                raw,
                source="melee",
                damage_type=enemy.damage_type,
                attacker=enemy,
                victim=victim,
            )
            if ability is not None and ability.status_effect:
                if amount > 0:
                    self.set_player_status(
                        ability.status_effect, ability.status_duration, player=victim
                    )
            elif enemy.damage_type == "poison" and amount > 0:
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
        else:
            # 4.8.10: NPC allies have no armor or statuses; the sink prints
            # its own damage floater and handles death removal.
            self.take_npc_damage(victim, max(1, raw), enemy)
        self.add_slash(
            (enemy.x + victim.x) * 0.5,
            (enemy.y + victim.y) * 0.5,
            0.14,
            enemy.facing_x,
            enemy.facing_y,
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
        ability: EnemyAbility | None = None,
        line_of_sight_confirmed: bool = False,
    ) -> None:
        if not line_of_sight_confirmed:
            victim = self.enemy_target(enemy)
            if victim is None:
                return
            distance = math.hypot(enemy.x - victim.x, enemy.y - victim.y)
            if ability is not None:
                cast_range = ability_attack_range(enemy, ability)
            elif enemy.kind == "boss" or enemy.is_boss_encounter:
                cast_range = max(6.0, enemy.attack_range)
            else:
                cast_range = enemy.attack_range
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
        if ability is not None:
            bolt_damage = max(1, int(round(enemy.damage * ability.damage_multiplier)))
            bolt_speed = ability.projectile_speed
            count = max(1, ability.projectile_count)
            if count == 1:
                spreads: tuple[float, ...] = (0.0,)
            else:
                width = ability.spread
                spreads = tuple(
                    -width + (2.0 * width) * index / (count - 1)
                    for index in range(count)
                )
            status_effect = ability.status_effect
            status_duration = ability.status_duration
        else:
            bolt_damage = enemy.damage
            bolt_speed = 6.0
            # 4-tile bosses are serious threats: they fire a 3-bolt fan
            # instead of a single projectile so the player has to dodge
            # laterally, not just step.
            spreads = (-0.28, 0.0, 0.28) if enemy.size >= 2 else (0.0,)
            status_effect = "chilled" if enemy.damage_type == "frost" else ""
            status_duration = 0.9
        # perpendicular vector for fanning the spread
        px, py = -ny, nx
        for spread in spreads:
            vx = nx * bolt_speed + px * spread * bolt_speed
            vy = ny * bolt_speed + py * spread * bolt_speed
            self.projectiles.append(
                Projectile(
                    enemy.x,
                    enemy.y,
                    vx,
                    vy,
                    bolt_damage,
                    "enemy",
                    projectile_color,
                    ttl=1.8,
                    damage_type=enemy.damage_type,
                    status_effect=status_effect,
                    status_duration=status_duration,
                )
            )

    def enemy_nova(self, enemy: Enemy, ability: EnemyAbility) -> None:
        """Radial LOS-checked burst around the caster (boss phase pressure)."""
        enemy.attack_timer = enemy.attack_cooldown
        enemy.telegraph = "cast"
        radius = ability.attack_range if ability.attack_range > 0.0 else 2.4
        burst_color = self.damage_type_color(enemy.damage_type)
        if enemy.kind in ("boss", "miniboss"):
            burst_color = self.theme.accent
        self.add_impact(
            enemy.x, enemy.y, burst_color, ttl=0.4, radius=radius, kind="cast"
        )
        base_damage = max(1, int(round(enemy.damage * ability.damage_multiplier)))
        for victim in self.living_players():
            distance = math.hypot(victim.x - enemy.x, victim.y - enemy.y)
            if distance > radius:
                continue
            if not self.dungeon.line_of_sight(
                enemy.x, enemy.y, victim.x, victim.y
            ):
                continue
            raw = base_damage + self.rng.randrange(-2, 3)
            amount = self.take_player_damage(
                raw,
                source="nova",
                damage_type=enemy.damage_type,
                attacker=enemy,
                victim=victim,
            )
            if ability.status_effect and amount > 0:
                self.set_player_status(
                    ability.status_effect, ability.status_duration, player=victim
                )
            self.floaters.append(
                FloatingText(
                    f"-{amount}",
                    victim.x,
                    victim.y - 0.2,
                    self.damage_type_color(enemy.damage_type),
                )
            )
        # 4.8.10: the radial burst catches NPC allies too (materialized first
        # — the damage sink removes the fallen from their roster mid-loop).
        for npc in tuple(self.iter_npc_allies()):
            distance = math.hypot(npc.x - enemy.x, npc.y - enemy.y)
            if distance > radius:
                continue
            if not self.dungeon.line_of_sight(enemy.x, enemy.y, npc.x, npc.y):
                continue
            self.take_npc_damage(
                npc, max(1, base_damage + self.rng.randrange(-2, 3)), enemy
            )
