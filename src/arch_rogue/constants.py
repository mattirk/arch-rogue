# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
#
# AI Provenance & Liability Notice:
# This repository contains code generated, assisted, or refactored by Artificial
# Intelligence models. Provided strictly "AS IS" under Apache 2.0 with no warranty
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

from __future__ import annotations

SCREEN_WIDTH = 2560
SCREEN_HEIGHT = 1440
FPS = 60
WORLD_SCALE = 5
TILE_W = 64 * WORLD_SCALE
TILE_H = 32 * WORLD_SCALE
MAX_INVENTORY = 20
DUNGEON_DEPTH = 10
UI_SCALE = 1
PLAYER_HIT_RADIUS = 0.42
ENEMY_HIT_RADIUS = 0.42
LARGE_ENEMY_HIT_RADIUS = 0.52
BOSS_HIT_RADIUS = 0.64
# 4-tile bosses (2x2 footprint) use a much larger body radius so melee swings,
# projectiles, and movement collision all respect the hulking silhouette.
BOSS_FOOTPRINT = 2
BOSS_FOOTPRINT_HIT_RADIUS = 0.92
BOSS_FOOTPRINT_MOVE_RADIUS = 0.82
PLAYER_MELEE_RANGE = 1.55
PLAYER_MELEE_ARC_DOT = 0.05
# Fixed player movement speed in tiles per second. Decoupled from the
# `player.speed` stat so movement is always constant regardless of archetype,
# discipline-tree speed bonuses, or Haste Shrine buffs. `player.speed` is retained
# as a character stat for future affix-driven movement bonuses (milestone 3.4)
# but no longer drives base locomotion or the run-cycle animation rate.
PLAYER_MOVE_SPEED = 2.8
PLAYER_PROJECTILE_HIT_RADIUS = 0.54
ENEMY_PROJECTILE_HIT_RADIUS = 0.52
WALK_ANIMATION_RATE = 0.8
DARK_LEVEL_LIGHT_RADIUS = 4.0
# Milestone 3.8 — light (non-dark) floors use fog of war: terrain stays
# revealed once explored. The live sight radius matches the dark floor's
# lantern radius so both floor types share the same visibility reach; the
# difference is memory, not range.
LIGHT_LEVEL_SIGHT_RADIUS = DARK_LEVEL_LIGHT_RADIUS
# Run-cycle tuning shared by the sprite atlas and the renderer so the cached
# run frames, the whole-body bob, and the directional lean all advance on the
# exact same phase. RUN_FRAME_RATE converts anim_time into run-frame units;
# RUN_CYCLE_FRAMES is the number of cached frames per full stride cycle.
RUN_CYCLE_FRAMES = 12
RUN_FRAME_RATE = 8.0
# Walk-cycle cadence is scaled by movement speed so faster units take faster
# steps, but clamped to a floor/ceiling so slow units never freeze into a
# stuttering handful of discrete frames and very fast units (elites, haste)
# don't blur. Effective range gives ~1.2..1.9 stride cycles per second.
WALK_ANIM_SPEED_FLOOR = 2.2
WALK_ANIM_SPEED_CEIL = 3.6
# Dungeon tile texture variants. A small, coherent family of pre-generated
# wall/floor textures picked deterministically per tile so the dungeon reads
# as hand-laid masonry instead of a single repeating stamp. Bounded set keeps
# the tile cache tiny and guarantees no per-frame texture recomputation. The
# four variants in each family share palette, lighting, and silhouette and
# differ only in masonry joints / surface detail, so they read as the same
# stone with small, distinct character.
DUNGEON_WALL_VARIANTS = 4
DUNGEON_FLOOR_VARIANTS = 4

# Milestone 3.16 — continuous multi-source colored lighting model.
# The light buffer is rendered at 1/LIGHT_BUFFER_SCALE resolution and
# smoothscaled up to the screen for the multiply pass; half-res keeps the
# compositing cheap and the gradients smooth with zero per-frame allocations.
LIGHT_BUFFER_SCALE = 2
# Player lantern: warm firelight. The lantern radius reuses the sight radius so
# the lit area and the combat/LOS reach stay identical.
LIGHT_LANTERN_COLOR = (255, 224, 168)
LIGHT_TORCH_COLOR = (255, 196, 130)
# Ambient floor wash is a white light tinted toward the theme accent so themed
# regions read as lit by their own light rather than flat. The two levels are
# the ambient brightness on dark vs light floors: dark floors stay near-black
# (the lantern does the work), light floors carry a dim memory-level wash.
LIGHT_AMBIENT_TINT_RATIO = 0.35
LIGHT_AMBIENT_DARK_LEVEL = 0.10
LIGHT_AMBIENT_LIGHT_LEVEL = 0.36
# Milestone 3.16 - depth brightness gradient on light floors: brighter near the
# surface, gradually darker as you descend. This is a separate axis from the
# dark-floor flag (lantern-only visibility / no fog-of-war memory), which stays
# intact; dark floors keep their constant near-black ambient regardless of
# depth. The light-floor ambient is LIGHT_AMBIENT_LIGHT_LEVEL * factor, where
# factor goes from PEAK at depth 1 to FLOOR at the max depth.
LIGHT_AMBIENT_DEPTH_PEAK = 1.6
LIGHT_AMBIENT_DEPTH_FLOOR = 0.5
# Subtle lantern/torch flicker amplitudes (fraction of radius/intensity).
# Always applied when the lighting model is on.
LIGHT_FLICKER_RADIUS_AMP = 0.05
LIGHT_FLICKER_INTENSITY_AMP = 0.08
# Static light radii (world tiles) and intensities.
LIGHT_TORCH_RADIUS = 2.6
LIGHT_TORCH_INTENSITY = 0.62
# Bar sconces are mounted halfway up a 48px wall face. Expressing height in
# TILE_H units lets the light buffer project them consistently at every zoom.
LIGHT_BAR_WALL_ELEVATION = 0.75
LIGHT_SHRINE_RADIUS = 2.3
LIGHT_SHRINE_INTENSITY = 0.55
# Transient skill/impact/projectile light tuning.
LIGHT_SKILL_PULSE_RADIUS = 2.1
LIGHT_SKILL_PULSE_TTL = 0.28
LIGHT_IMPACT_RADIUS = 1.8
LIGHT_IMPACT_TTL = 0.22
LIGHT_PROJECTILE_RADIUS = 1.5
LIGHT_PROJECTILE_TTL = 0.14
LIGHT_PROJECTILE_INTENSITY = 0.55
# Lit-actor shading: dominant light direction is quantized into this many
# buckets so a persistent (sprite, bucket) tint cache can be reused across
# frames until the light moves the actor into a new bucket.
LIGHT_DIRECTION_BUCKETS = 8
LIGHT_SHADE_DOWNSAMPLE_LONG = 48
LIGHT_SHADE_BIAS_Z = 0.55

SlashEffect = tuple[float, float, float, float, float]
