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
"""Actor movement and collision: move_actor, enemy locomotion, animation phase advance, hit radii, contact distance, melee stop distance, actor contact resolution."""
# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

import math
from itertools import chain
from ..constants import (
    ACTOR_GROUND_DEPTH_OFFSET,
    ACTOR_MOVE_COLLISION_RADIUS,
    PLAYER_HIT_RADIUS,
    WALK_ANIM_RUNTIME_SCALE_FLOOR,
    WALK_ANIMATION_RATE,
)
from ..models import (
    Enemy,
    Player,
)

from ._utils import (
    BOSS_FOOTPRINT_MOVE_RADIUS,
    BOSS_FOOTPRINT_HIT_RADIUS,
    PLAYER_MOVE_SPEED,
    WALK_ANIM_SPEED_CEIL,
    actor_hit_radius,
    anim_speed,
    enemy_hit_radius,
)
from .spatial import EnemySpatialIndex

ENEMY_SPATIAL_INDEX_THRESHOLD = 60


class _MovementCombatMixin:
    def move_actor(self, actor: Player | Enemy, dx: float, dy: float) -> float:
        old_x, old_y = actor.x, actor.y
        actor_is_player = isinstance(actor, Player)
        # Big bosses (2x2 footprint) need a wider collision probe so they don't
        # clip into walls; regular actors keep the tight default radius.
        if isinstance(actor, Enemy) and actor.size >= 2:
            radius = BOSS_FOOTPRINT_MOVE_RADIUS
        else:
            radius = ACTOR_MOVE_COLLISION_RADIUS
        block_stairs = actor_is_player
        # Player sprites place their feet south of the logical world point.
        # Relieving only exposed screen-north wall faces aligns that visible
        # contact without translating the actor, changing doors, or weakening
        # collision for enemies and other world probes.
        wall_depth_relief = ACTOR_GROUND_DEPTH_OFFSET if actor_is_player else 0.0
        new_x = actor.x + dx
        if not self.dungeon.blocked_for_radius(
            new_x,
            actor.y,
            radius,
            block_stairs=block_stairs,
            wall_depth_relief=wall_depth_relief,
        ):
            actor.x = new_x
        new_y = actor.y + dy
        if not self.dungeon.blocked_for_radius(
            actor.x,
            new_y,
            radius,
            block_stairs=block_stairs,
            wall_depth_relief=wall_depth_relief,
        ):
            actor.y = new_y
        use_enemy_index = (
            isinstance(actor, Enemy)
            and len(self.enemies) >= ENEMY_SPATIAL_INDEX_THRESHOLD
        )
        if use_enemy_index:
            self._update_enemy_spatial_position(actor)
        self.resolve_actor_contacts(actor)
        if use_enemy_index:
            # Contact resolution can push the mover across another cell edge.
            self._update_enemy_spatial_position(actor)

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
            # using a steady dt-based rate so the walk cycle stays smooth even
            # when per-frame movement distance jitters from frame-rate variance.
        return distance

    def _move_enemy_locomotion(
        self,
        enemy: Enemy,
        dx: float,
        dy: float,
        dt: float,
        planned_scale: float,
    ) -> float:
        moved = self.move_actor(enemy, dx, dy)
        if moved <= 0.0 or dt <= 0.0 or enemy.speed <= 0.0:
            return moved
        actual_scale = moved / (enemy.speed * dt)
        if actual_scale < planned_scale - 1e-9:
            enemy.locomotion_anim_scale = min(
                enemy.locomotion_anim_scale,
                max(WALK_ANIM_RUNTIME_SCALE_FLOOR, actual_scale),
            )
        return moved

    def player_walk_cadence(self) -> float:
        """Base walk-cycle cadence (tiles/s) for the player.

        Single seam for the player animation rate: ``advance_animation_phases``
        consumes it, so a future haste/discipline that should change the
        visual cadence overrides this one getter instead of each attack/
        animation call site. Returns ``PLAYER_MOVE_SPEED`` unchanged so
        footsteps stay in sync with movement (movement speed is fixed and
        decoupled from the ``player.speed`` stat; scaling cadence by the
        attack_speed stat here would desync stride from ground speed).
        """
        return PLAYER_MOVE_SPEED

    def advance_animation_phases(self, dt: float) -> None:
        # Base cadence remains clamped by actor type, then the runtime movement
        # multiplier follows analog input, status effects, and Time Skip. This
        # keeps authored footsteps synchronized when simulation speed changes
        # without making naturally slow enemy archetypes freeze between frames.
        for actor in self.active_players():
            # Death visuals: a fallen actor accrues time on its one-shot "die"
            # clip (then the looping "dead" idle) instead of walk cadence.
            if actor.hp <= 0:
                actor.death_anim_time += dt
                continue
            actor.death_anim_time = 0.0
            if actor.moving:
                speed = min(
                    WALK_ANIM_SPEED_CEIL,
                    anim_speed(self.player_walk_cadence())
                    * max(
                        WALK_ANIM_RUNTIME_SCALE_FLOOR,
                        actor.locomotion_anim_scale,
                    ),
                )
                actor.anim_time += dt * WALK_ANIMATION_RATE * speed
        for enemy in self.enemies:
            if enemy.moving:
                speed = min(
                    WALK_ANIM_SPEED_CEIL,
                    anim_speed(enemy.speed)
                    * max(
                        WALK_ANIM_RUNTIME_SCALE_FLOOR,
                        enemy.locomotion_anim_scale,
                    ),
                )
                enemy.anim_time += dt * WALK_ANIMATION_RATE * speed

    def actor_hit_radius(self, actor: Player | Enemy) -> float:
        return actor_hit_radius(actor)

    def enemy_hit_radius(self, enemy: Enemy) -> float:
        return enemy_hit_radius(enemy)

    def contact_distance(self, enemy: Enemy) -> float:
        return PLAYER_HIT_RADIUS + self.enemy_hit_radius(enemy)

    def _enemy_melee_stop_distance(self, enemy: Enemy) -> float:
        """Distance a melee enemy should close to before halting its approach.

        Stopping a small cushion inside ``attack_range`` prevents low-FPS/mobile
        frames and small player micro-kiting from leaving the enemy oscillating
        just outside melee reach. The result is clamped to [contact + margin,
        attack_range] so extremely short attack ranges (e.g. test dummies) do
        not fall inside collision resolution.
        """
        contact = self.contact_distance(enemy)
        return min(
            enemy.attack_range,
            max(contact + 0.02, enemy.attack_range - 0.12),
        )

    def _rebuild_enemy_spatial_index(self) -> EnemySpatialIndex | None:
        """Rebuild the broad phase at a deterministic simulation boundary."""

        if len(self.enemies) < ENEMY_SPATIAL_INDEX_THRESHOLD:
            self._enemy_spatial_index = None
            return None
        index = EnemySpatialIndex(self.enemies)
        self._enemy_spatial_index = index
        return index

    def _current_enemy_spatial_index(self) -> EnemySpatialIndex | None:
        """Return an index matching the active enemy collection."""

        if len(self.enemies) < ENEMY_SPATIAL_INDEX_THRESHOLD:
            self._enemy_spatial_index = None
            return None
        index = getattr(self, "_enemy_spatial_index", None)
        if index is None or not index.matches(self.enemies):
            return self._rebuild_enemy_spatial_index()
        return index

    def nearby_enemies(
        self,
        x: float,
        y: float,
        radius: float,
    ) -> list[Enemy]:
        """Broad-phase enemy candidates in canonical ``self.enemies`` order."""

        if len(self.enemies) < ENEMY_SPATIAL_INDEX_THRESHOLD:
            return self.enemies
        index = self._current_enemy_spatial_index()
        assert index is not None
        return index.candidates(x, y, radius)

    def _update_enemy_spatial_position(self, enemy: Enemy) -> None:
        index = self._current_enemy_spatial_index()
        if index is not None:
            index.update(enemy)

    def _resolve_actor_contacts_indexed(self, actor: Player | Enemy) -> None:
        """Resolve contacts through the local broad phase for dense crowds."""

        actor_is_player = isinstance(actor, Player)
        actor_radius = (
            PLAYER_HIT_RADIUS if actor_is_player else self.enemy_hit_radius(actor)
        )
        if actor_is_player:
            # Players never body-block one another (4.6 co-op rule), so other
            # players are deliberately absent from a player's contact list.
            self._resolve_enemy_contacts(actor, actor_radius, actor_is_player=True)
            others = self.iter_friendly_npcs()
        else:
            # 4.8.10: enemies body-block against aggressive NPC allies (the
            # foes they now trade blows with); pacifist props stay ghosts to
            # them exactly as before.
            for player in self.active_players():
                self._resolve_actor_contact(
                    actor,
                    player,
                    actor_radius,
                    actor_is_player=False,
                )
            self._resolve_enemy_contacts(actor, actor_radius, actor_is_player=False)
            others = chain(
                self.shopkeepers,
                self.iter_npc_allies(),
            )

        for other in others:
            self._resolve_actor_contact(
                actor,
                other,
                actor_radius,
                actor_is_player=actor_is_player,
            )

    def resolve_actor_contacts(self, actor: Player | Enemy) -> None:
        """Resolve contacts without penalizing ordinary-sized enemy rosters."""

        actor_is_player = isinstance(actor, Player)
        actor_radius = (
            PLAYER_HIT_RADIUS if actor_is_player else self.enemy_hit_radius(actor)
        )
        if len(self.enemies) >= ENEMY_SPATIAL_INDEX_THRESHOLD:
            self._resolve_actor_contacts_indexed(actor)
            return
        # Keep the historical narrow phase inline below the measured crossover.
        # Calling a helper for every pair is measurably slower at normal density.
        if actor_is_player:
            # Players never body-block one another (4.6 co-op rule), so other
            # players are deliberately absent from a player's contact list.
            others = chain(self.enemies, self.iter_friendly_npcs())
        else:
            # 4.8.10: enemies body-block against aggressive NPC allies (the
            # foes they now trade blows with); pacifist props stay ghosts to
            # them exactly as before.
            others = chain(
                self.active_players(),
                self.enemies,
                self.shopkeepers,
                self.iter_npc_allies(),
            )

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
            elif actor_is_player:
                other_radius = self.FRIENDLY_NPC_RADIUS
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
            block_stairs = isinstance(actor, Player)
            wall_depth_relief = (
                ACTOR_GROUND_DEPTH_OFFSET if block_stairs else 0.0
            )
            if not self.dungeon.blocked_for_radius(
                target_x,
                actor.y,
                block_stairs=block_stairs,
                wall_depth_relief=wall_depth_relief,
            ):
                actor.x = target_x
            if not self.dungeon.blocked_for_radius(
                actor.x,
                target_y,
                block_stairs=block_stairs,
                wall_depth_relief=wall_depth_relief,
            ):
                actor.y = target_y

    def _resolve_enemy_contacts(
        self,
        actor: Player | Enemy,
        actor_radius: float,
        *,
        actor_is_player: bool,
    ) -> None:
        """Resolve enemies once in source order, re-querying after a shove.

        A contact can move ``actor`` by more than one spatial cell. Re-querying
        only after real displacement finds later-list enemies at the new
        position without revisiting earlier actors that the historical full
        scan had already processed.
        """

        index = self._current_enemy_spatial_index()
        assert index is not None
        search_radius = actor_radius + BOSS_FOOTPRINT_HIT_RADIUS
        processed_order = -1
        while True:
            entries = index.candidate_entries(
                actor.x,
                actor.y,
                search_radius,
                after_order=processed_order,
            )
            actor_moved = False
            for order, other in entries:
                processed_order = order
                if other is actor:
                    continue
                if self._resolve_actor_contact(
                    actor,
                    other,
                    actor_radius,
                    actor_is_player=actor_is_player,
                ):
                    actor_moved = True
                    break
            if not actor_moved:
                return

    def _resolve_actor_contact(
        self,
        actor: Player | Enemy,
        other,
        actor_radius: float,
        *,
        actor_is_player: bool,
    ) -> bool:
        """Resolve one ordered body contact and report actual displacement."""

        if other is actor:
            return False
        dx = actor.x - other.x
        dy = actor.y - other.y
        distance_squared = dx * dx + dy * dy
        if isinstance(other, Player):
            other_radius = PLAYER_HIT_RADIUS
        elif isinstance(other, Enemy):
            other_radius = self.enemy_hit_radius(other)
        elif actor_is_player:
            other_radius = self.FRIENDLY_NPC_RADIUS
        else:
            other_radius = 0.34
        min_distance = actor_radius + other_radius
        if distance_squared >= min_distance * min_distance:
            return False

        if distance_squared > 0.000001:
            distance = math.sqrt(distance_squared)
            nx, ny = dx / distance, dy / distance
        else:
            nx, ny = -actor.facing_x, -actor.facing_y
            if math.hypot(nx, ny) <= 0.001:
                nx, ny = 1.0, 0.0

        old_x, old_y = actor.x, actor.y
        target_x = other.x + nx * min_distance
        target_y = other.y + ny * min_distance
        block_stairs = isinstance(actor, Player)
        wall_depth_relief = ACTOR_GROUND_DEPTH_OFFSET if block_stairs else 0.0
        if not self.dungeon.blocked_for_radius(
            target_x,
            actor.y,
            block_stairs=block_stairs,
            wall_depth_relief=wall_depth_relief,
        ):
            actor.x = target_x
        if not self.dungeon.blocked_for_radius(
            actor.x,
            target_y,
            block_stairs=block_stairs,
            wall_depth_relief=wall_depth_relief,
        ):
            actor.y = target_y
        return actor.x != old_x or actor.y != old_y
