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
"""Projectile simulation: update_projectiles, homing steer, chain lightning, acolyte leech, and trap updates."""
# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

import math
from ..constants import (
    ENEMY_PROJECTILE_HIT_RADIUS,
    LIGHT_PROJECTILE_INTENSITY,
    LIGHT_PROJECTILE_RADIUS,
    LIGHT_PROJECTILE_TTL,
    PLAYER_PROJECTILE_HIT_RADIUS,
)
from ..models import (
    Enemy,
    FloatingText,
    Projectile,
)


from .damage import DamageContext

class _ProjectilesCombatMixin:
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
                        DamageContext(
                            target=hit,
                            amount=projectile.damage,
                            damage_type=projectile.damage_type,
                            knockback_from=(projectile.vx, projectile.vy),
                            status_effect=projectile.status_effect,
                            status_duration=projectile.status_duration,
                            source="projectile",
                        )
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
                struck_player = None
                for candidate in self.living_players():
                    player_dx = projectile.x - candidate.x
                    player_dy = projectile.y - candidate.y
                    if (
                        player_dx * player_dx + player_dy * player_dy
                        < ENEMY_PROJECTILE_HIT_RADIUS
                        * ENEMY_PROJECTILE_HIT_RADIUS
                        and self.dungeon.line_of_sight(
                            projectile.x,
                            projectile.y,
                            candidate.x,
                            candidate.y,
                        )
                    ):
                        struck_player = candidate
                        break
                if struck_player is not None:
                    amount = self.take_player_damage(
                        projectile.damage,
                        source="projectile",
                        damage_type=projectile.damage_type,
                        victim=struck_player,
                    )
                    if projectile.status_effect == "chilled" and amount > 0:
                        self.set_player_status(
                            "chilled",
                            projectile.status_duration,
                            player=struck_player,
                        )
                    self.floaters.append(
                        FloatingText(
                            f"-{amount}",
                            struck_player.x,
                            struck_player.y - 0.2,
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
            DamageContext(
                target=best,
                amount=chain_damage,
                damage_type=projectile.damage_type,
                knockback_from=(best.x - primary.x, best.y - primary.y),
                status_effect=projectile.status_effect,
                status_duration=projectile.status_duration * 0.7,
                source="chain",
            )
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
        players = self.living_players()
        for trap in self.traps:
            if not trap.active:
                continue
            victim = next(
                (
                    player
                    for player in players
                    if math.hypot(trap.x - player.x, trap.y - player.y) <= 0.55
                ),
                None,
            )
            if victim is None:
                continue
            trap.active = False
            amount = self.take_player_damage(
                trap.damage, source="trap", victim=victim
            )
            self.run_stats.traps_triggered += 1
            self.floaters.append(
                FloatingText(
                    f"{trap.kind}! -{amount}",
                    victim.x,
                    victim.y - 0.2,
                    (245, 95, 70),
                    ttl=1.2,
                )
            )
            self.add_impact(
                trap.x, trap.y, (245, 95, 70), ttl=0.46, radius=0.58, kind="burst"
            )
            self.play_sfx("trap")
