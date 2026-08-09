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
# Chain-shove: contact resolution ejects the MOVER from any body overlap, so
# without help a hurled enemy body-blocks to a halt on the first packmate in
# its path (measured: a 2-tile Big Hit throw moved ~0.06 tiles into a pack).
# Above this speed the knockback integrator instead transfers velocity to
# packmates in the flight path so the group plows backwards together. The
# threshold sits far above the ordinary KNOCKBACK_SPEED nudge — routine melee
# shoves never chain — and below the boss-resisted Big Hit throw (7.0).
KNOCKBACK_CHAIN_MIN_SPEED = 4.0
KNOCKBACK_CHAIN_TRANSFER = 0.85
KNOCKBACK_CHAIN_ARC_DOT = 0.35

# Big Hit (action slot 1): hold-to-charge heavy blow shared by all archetypes.
# The charge is tracked as the underscore status ``_charging`` on the player
# (underscore statuses skip the generic TTL decrement; _update_big_hit owns
# it), so it replicates and saves with the rest of ``status_effects``.
# Committing at half charge and the throw distances are design constants from
# build/bighit.md; ``BIGHIT_THROW_TILES * KNOCKBACK_DECAY_RATE`` becomes the
# knockback v0 because the decay integral's total displacement is v0 / rate.
BIGHIT_CHARGE_TIME = 0.9
BIGHIT_COMMIT_FRACTION = 0.5
BIGHIT_COOLDOWN = 6.0
BIGHIT_CANCEL_COOLDOWN = 1.5
BIGHIT_STAMINA_COST = 20
BIGHIT_DAMAGE_MULT = 3.0
BIGHIT_THROW_TILES = 2.0
BIGHIT_THROW_TILES_RANGER = 2.2
# Oversized bosses (size >= 2) resist the hurl so arenas and boss AI
# positioning survive; they still take full damage.
BIGHIT_BOSS_THROW_FACTOR = 0.35
BIGHIT_CLEAVE_FACTOR = 0.62
BIGHIT_CHARGING_STATUS = "_charging"

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

# 4.8.9 perception: an engaged enemy remembers its target's last noticed
# position for this long after the target leaves aggro range, drifting there
# instead of freezing mid-stride at the radius edge. Entering the engaged
# state alerts idle packmates within the alert radius (one hop, no chain).
ENEMY_ALERT_MEMORY = 4.0
ENEMY_ALERT_RADIUS = 4.0
# Memory pursuit ends when the enemy gets this close to the remembered spot.
ENEMY_MEMORY_ARRIVE_DISTANCE = 0.35

# 4.8.9 movement: perpendicular blend added to an advance step to keep packs
# from funneling into one shoving column (resolve_actor_contacts stays the
# hard backstop), triggered when another enemy overlaps within this fraction
# of the combined hit radii.
ENEMY_SEPARATION_BIAS = 0.35
ENEMY_SEPARATION_FRACTION = 0.9


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