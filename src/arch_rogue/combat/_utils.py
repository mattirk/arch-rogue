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

"""Pure combat helpers and combat-only tuning constants.

Centralizes stateless logic shared across :mod:`arch_rogue.combat` submodules so
each helper has one canonical home:

- :func:`average_slow_factors` — exact average movement/cadence scales for
  overlapping slows (moved out of ``statuses.py``; used by the locomotion
  scale getters).
- :func:`anim_speed` — walk-cycle cadence clamp (moved out of ``movement.py``).
- :func:`enemy_hit_radius` / :func:`actor_hit_radius` — hit-radius lookups
  (moved out of ``movement.py``; the mixin keeps thin wrapper methods so
  external callers such as ``run_flow.boss_arena_enemy_radius`` and the test
  suite can keep calling ``self.enemy_hit_radius(enemy)``).

The combat-only movement/hit-radius tuning constants that these helpers depend
on live here too, colocated with the logic that uses them. Constants shared
with the rest of the engine (``PLAYER_HIT_RADIUS``, ``BOSS_HIT_RADIUS``,
``WALK_ANIM_RUNTIME_SCALE_FLOOR``, ``WALK_ANIMATION_RATE`` …) stay in
:mod:`arch_rogue.constants`.
"""

from __future__ import annotations

from ..constants import (
    BOSS_HIT_RADIUS,
    ENEMY_HIT_RADIUS,
    LARGE_ENEMY_HIT_RADIUS,
    PLAYER_HIT_RADIUS,
    WALK_ANIM_RUNTIME_SCALE_FLOOR,
)
from ..models import Enemy, Player

# 4-tile bosses (2x2 footprint) use a much larger body radius so melee swings,
# projectiles, and movement collision all respect the hulking silhouette.
BOSS_FOOTPRINT_HIT_RADIUS = 0.92
BOSS_FOOTPRINT_MOVE_RADIUS = 0.82

# Fixed player movement speed in tiles per second. Decoupled from the
# ``player.speed`` stat so movement is always constant regardless of archetype,
# discipline-tree speed bonuses, or Haste Shrine buffs. ``player.speed`` is
# retained as a character stat for future affix-driven movement bonuses but no
# longer drives base locomotion or the walk-cycle animation rate.
PLAYER_MOVE_SPEED = 2.8

# Walk-cycle cadence is scaled by movement speed so faster units take faster
# steps, but clamped to a floor/ceiling so slow units never freeze into a
# stuttering handful of discrete frames and very fast units (elites, haste)
# don't blur. Effective range gives ~1.2..1.9 stride cycles per second.
WALK_ANIM_SPEED_FLOOR = 2.2
WALK_ANIM_SPEED_CEIL = 3.6

# Knockback: incoming hits set ``enemy.knockback_vx/vy`` to a unit direction
# times KNOCKBACK_SPEED (tiles/sec); ``update_enemies`` integrates it with
# exponential decay so the shove is framerate-independent and the total
# displacement is KNOCKBACK_SPEED / KNOCKBACK_DECAY_RATE (~0.16 tiles, matching
# the pre-4.5 one-shot nudge magnitude). Time Skip slows the integration via
# scaled_dt but the total displacement stays the same.
KNOCKBACK_SPEED = 1.6
KNOCKBACK_DECAY_RATE = 10.0

# Enemy attack windup: when an enemy is attack-ready + in range + LOS, it
# COMMITS (sets windup_time) instead of attacking immediately, pauses to
# telegraph, then fires on windup completion (locked -- the committed hit lands
# even if the player moves during the short windup; the player counters with
# abilities, not by walking out). Ranged casts snapshot the aim direction at
# commit so the fired projectile is dodgeable after launch. Bosses wind up
# shorter so multi-bolt fans don't feel sluggish.
ENEMY_MELEE_WINDUP = 0.35
ENEMY_CAST_WINDUP = 0.5
ENEMY_BOSS_WINDUP = 0.25


def average_slow_factors(
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


def anim_speed(speed: float) -> float:
    """Clamp a walk-cycle cadence to the authored floor/ceiling."""
    if speed < WALK_ANIM_SPEED_FLOOR:
        return WALK_ANIM_SPEED_FLOOR
    if speed > WALK_ANIM_SPEED_CEIL:
        return WALK_ANIM_SPEED_CEIL
    return speed


def enemy_hit_radius(enemy: Enemy) -> float:
    """Collision/attack hit radius for an enemy by size/kind/name."""
    if enemy.size >= 2:
        return BOSS_FOOTPRINT_HIT_RADIUS
    if enemy.kind == "boss":
        return BOSS_HIT_RADIUS
    if enemy.name in ("Gate Warden", "Crypt Brute"):
        return LARGE_ENEMY_HIT_RADIUS
    return ENEMY_HIT_RADIUS


def actor_hit_radius(actor: Player | Enemy) -> float:
    """Hit radius for any actor (player or enemy)."""
    if isinstance(actor, Player):
        return PLAYER_HIT_RADIUS
    return enemy_hit_radius(actor)