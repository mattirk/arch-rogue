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
    TRAP_REVEAL_RADIUS,
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
                    projectile.x,
                    projectile.y,
                    PLAYER_PROJECTILE_HIT_RADIUS,
                    excluded_ids=projectile.hit_enemies,
                )
                if hit is not None:
                    self.add_impact(
                        projectile.x,
                        projectile.y,
                        projectile.color,
                        ttl=0.32,
                        radius=0.38,
                        kind="burst",
                    )
                    # 4.7.12 co-op kill credit: the hit resolves frames after
                    # the cast, inside the host's own update loop — act as
                    # the recorded shooter so damage, kill XP/gold, leech,
                    # and chain lightning route to whoever actually fired.
                    shooter = self.player_for_credit(projectile.owner_id)
                    with self.acting_as_player(shooter):
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
                        # Acolyte Spirit Bolt siphons life when the Blood path
                        # is committed, using the same ramp as Spirit Call
                        # familiars.
                        if projectile.archetype == "Acolyte":
                            leech = self._acolyte_spell_leech()
                            if leech:
                                self.player.hp = min(
                                    self.player.max_hp, self.player.hp + leech
                                )
                        # All fan shards share one Storm charge. The first
                        # shard to land spends it even when no secondary target
                        # is present, so later shards and pierces cannot emit
                        # another full chain.
                        storm_charge = projectile.storm_chain_charge
                        if storm_charge is not None and not storm_charge.spent:
                            storm_charge.spent = True
                            self._maybe_chain_lightning(projectile, hit)
                    projectile.hit_enemies.add(id(hit))
                    if projectile.pierce > 0:
                        projectile.pierce -= 1
                        # Piercing bolts deal reduced damage to subsequent foes.
                        # Bolt Degree 4 keeps more of an Arc Bolt's force after
                        # each body. Storm owns chain lightning; Conduit Sigil
                        # remains a distinct projectile-shaping upgrade.
                        pierce_falloff = (
                            0.82
                            if shooter.class_name == "Arcanist"
                            and shooter.has_upgrade("arcanist_storm")
                            else 0.70
                        )
                        projectile.damage = max(
                            1, int(projectile.damage * pierce_falloff)
                        )
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
                # 4.8.10: aggressive NPC allies block enemy bolts in the same
                # pass. Pacifist props stay untouchable, exactly as before.
                struck_npc = None
                for npc in self.iter_npc_allies():
                    npc_dx = projectile.x - npc.x
                    npc_dy = projectile.y - npc.y
                    if (
                        npc_dx * npc_dx + npc_dy * npc_dy
                        < ENEMY_PROJECTILE_HIT_RADIUS
                        * ENEMY_PROJECTILE_HIT_RADIUS
                        and self.dungeon.line_of_sight(
                            projectile.x, projectile.y, npc.x, npc.y
                        )
                    ):
                        struck_npc = npc
                        break
                if struck_npc is not None:
                    self.take_npc_damage(struck_npc, projectile.damage, None)
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
        """Gently turn a homing projectile toward the nearest visible enemy.

        Homing bolts are rare (capstone-only), but the shared broad phase keeps
        multiple seeking projectiles from repeating a full enemy scan. Walls
        block target acquisition as well as projectile travel.
        """
        nearest = None
        best_distance_squared = 6.5 * 6.5
        for enemy in self.nearby_enemies(
            projectile.x,
            projectile.y,
            6.5,
        ):
            if not enemy.alive or id(enemy) in projectile.hit_enemies:
                continue
            dx = enemy.x - projectile.x
            dy = enemy.y - projectile.y
            distance_squared = dx * dx + dy * dy
            if (
                distance_squared < best_distance_squared
                and self.dungeon.line_of_sight(
                    projectile.x,
                    projectile.y,
                    enemy.x,
                    enemy.y,
                )
            ):
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
        """Apply the Arcanist Storm path's bounded Arc Bolt chain.

        Chain Lightning starts with one secondary target. Tempest,
        Stormcaller, and World Storm raise that cap to two, three, and four
        while widening the per-hop search. Stormcaller and its capstone prefer
        elite prey before distance. Every hop still requires line of sight,
        and ``hit_enemies`` prevents a chain/piercing bolt from striking the
        same foe twice.
        """
        if self.player.class_name != "Arcanist":
            return
        if projectile.owner != "player":
            return
        if self.player.has_upgrade("arcanist_world_storm"):
            jump_limit, jump_radius = 4, 3.6
        elif self.player.has_upgrade("arcanist_storm_caller"):
            jump_limit, jump_radius = 3, 3.2
        elif self.player.has_upgrade("arcanist_tempest"):
            jump_limit, jump_radius = 2, 2.8
        elif self.player.has_upgrade("arcanist_chain_lightning"):
            jump_limit, jump_radius = 1, 2.6
        else:
            return

        chain_damage = max(1, int(projectile.damage * 0.55))
        visited = set(projectile.hit_enemies)
        visited.add(id(primary))
        source = primary
        elite_priority = self.player.has_upgrade(
            "arcanist_storm_caller"
        ) or self.player.has_upgrade("arcanist_world_storm")
        jump_radius_squared = jump_radius * jump_radius
        for _ in range(jump_limit):
            candidates: list[tuple[bool, float, Enemy]] = []
            for enemy in self.nearby_enemies(
                source.x,
                source.y,
                jump_radius,
            ):
                if not enemy.alive or id(enemy) in visited:
                    continue
                dx = enemy.x - source.x
                dy = enemy.y - source.y
                distance_squared = dx * dx + dy * dy
                if (
                    distance_squared < jump_radius_squared
                    and self.dungeon.line_of_sight(
                        source.x, source.y, enemy.x, enemy.y
                    )
                ):
                    elite = bool(
                        enemy.elite_modifier
                        or enemy.kind in ("boss", "miniboss")
                        or enemy.is_boss_encounter
                    )
                    candidates.append((elite, distance_squared, enemy))
            if not candidates:
                break
            if elite_priority:
                _elite, _distance, target = min(
                    candidates,
                    key=lambda entry: (not entry[0], entry[1]),
                )
            else:
                _elite, _distance, target = min(
                    candidates, key=lambda entry: entry[1]
                )
            visited.add(id(target))
            projectile.hit_enemies.add(id(target))
            self.add_impact(
                target.x,
                target.y,
                projectile.color,
                ttl=0.22,
                radius=0.3,
                kind="burst",
            )
            self.damage_enemy(
                DamageContext(
                    target=target,
                    amount=chain_damage,
                    damage_type=projectile.damage_type,
                    knockback_from=(target.x - source.x, target.y - source.y),
                    status_effect=projectile.status_effect,
                    status_duration=projectile.status_duration * 0.7,
                    source="chain",
                )
            )
            source = target

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

    def update_traps(self, dt: float) -> None:
        players = self.living_players()
        for trap in self.traps:
            if not trap.active:
                continue
            # Reveal before the victim check so even a dash/teleport straight
            # onto a hidden trap shows the plate the same tick it fires.
            if not trap.revealed and any(
                math.hypot(trap.x - player.x, trap.y - player.y)
                <= TRAP_REVEAL_RADIUS
                for player in players
            ):
                trap.revealed = True
            if trap.revealed and trap.reveal_progress < 1.0:
                trap.reveal_progress = min(1.0, trap.reveal_progress + dt * 6.0)
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
