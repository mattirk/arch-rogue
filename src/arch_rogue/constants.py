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
# 4.3.17: frame-rate cap is now owned by `FramePacing` and the persisted
# `frame_rate_cap` option (schema 7). `DEFAULT_FRAME_RATE` is the fresh-install
# default for both desktop and mobile. `FPS` is retained as a deprecated alias
# for one release so external callers and the web build keep working; new code
# should read the live target from `Game.frame_pacing.target_fps`.
DEFAULT_FRAME_RATE = 60
FPS = DEFAULT_FRAME_RATE  # Deprecated cutoff: 4.4
WORLD_SCALE = 5
TILE_W = 64 * WORLD_SCALE
TILE_H = 32 * WORLD_SCALE

# Descending spiral stairs collision.
#
# The authored stair sprite (64x64, source anchor [32, 42]) is composited so the
# anchor lands on the logical tile center, but the visible circular shaft is
# centered on source pixel (32, 37) -- 5 source pixels north of the anchor.
# At WORLD_SCALE=5 that is 25 screen pixels north, which in the isometric
# projection (screen_y = (x + y) * TILE_H / 2) is a world shift of -25 / 80 =
# -0.3125 in (x + y), split symmetrically to -0.15625 on each axis. The inset
# shrinks the footprint so the player can step up to the masonry rim from every
# direction instead of being kept a full tile away.
STAIR_COLLISION_OFFSET_X = -0.15625
STAIR_COLLISION_OFFSET_Y = -0.15625
STAIR_COLLISION_INSET = 0.15
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
PLAYER_MELEE_RANGE = 1.55
PLAYER_MELEE_ARC_DOT = 0.05
PLAYER_PROJECTILE_HIT_RADIUS = 0.54
ENEMY_PROJECTILE_HIT_RADIUS = 0.52
WALK_ANIMATION_RATE = 0.8
DARK_LEVEL_LIGHT_RADIUS = 4.0
# Milestone 3.8 — light (non-dark) floors use fog of war: terrain stays
# revealed once explored. The live sight radius matches the dark floor's
# lantern radius so both floor types share the same visibility reach; the
# difference is memory, not range.
LIGHT_LEVEL_SIGHT_RADIUS = DARK_LEVEL_LIGHT_RADIUS
# Walk-cycle tuning shared by the sprite atlas and the renderer so the cached
# walk frames, the whole-body bob, and the directional lean all advance on the
# exact same phase. WALK_FRAME_RATE converts anim_time into walk-frame units;
# WALK_CYCLE_FRAMES is the number of cached frames per full stride cycle.
WALK_CYCLE_FRAMES = 12
WALK_FRAME_RATE = 8.0
# Runtime movement modifiers (analog creep, snares, Time Skip, final approach
# steps) may lower cadence further, but never below this fraction of the base
# cycle so discrete authored frames do not turn into occasional visible ticks.
WALK_ANIM_RUNTIME_SCALE_FLOOR = 0.25
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
# Desktop light-buffer divisor. Mobile quality tiers can increase this at
# runtime before the reused buffer is scaled into the world multiply pass.
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
# Bar sconces sit on the lower third of a 48px wall face, closer to the floor.
# TILE_H units keep the fixture and light halo aligned at every viewport zoom.
LIGHT_BAR_WALL_ELEVATION = 0.50
LIGHT_SHRINE_RADIUS = 2.3
LIGHT_SHRINE_INTENSITY = 0.55
# Descending stairs emit only a restrained violet wash; their authored frames
# carry the stronger local shaft pulse, so this light should not flood the room.
LIGHT_STAIRS_COLOR = (126, 74, 170)
LIGHT_STAIRS_RADIUS = 1.45
LIGHT_STAIRS_INTENSITY = 0.18
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

# 4.6 multiplayer. The canonical wire contract lives in the stdlib-only
# `arch_rogue_protocol` package (shared with the standalone server); these
# re-exports give game code one import site alongside the other constants.
# `MP_RUN_ID_LENGTH` is the client-generated room-code length — a room
# locator, not authentication — and can later be raised to 8 or 12.
from arch_rogue_protocol import (  # noqa: E402
    MP_INTENT_RATE_HZ,
    MP_MAX_MESSAGE_BYTES,
    MP_PLAYER_NAME_MAX_CHARS,
    MP_PROTOCOL_VERSION,
    MP_RECONNECT_GRACE_SECONDS,
    MP_RUN_ID_ALPHABET,
    MP_RUN_ID_LENGTH,
    MP_SNAPSHOT_RATE_HZ,
)

__all_mp__ = (
    "MP_INTENT_RATE_HZ",
    "MP_MAX_MESSAGE_BYTES",
    "MP_PLAYER_NAME_MAX_CHARS",
    "MP_PROTOCOL_VERSION",
    "MP_RECONNECT_GRACE_SECONDS",
    "MP_RUN_ID_ALPHABET",
    "MP_RUN_ID_LENGTH",
    "MP_SNAPSHOT_RATE_HZ",
)

# 4.3.17 frame-rate cap option (schema 7). The order here is also the cycle
# order used by the Options row. "Unlimited" maps to ``clock.tick(0)``.
FRAME_RATE_CAP_VALUES: tuple[int | str, ...] = (30, 60, 90, 120, "Unlimited")
FRAME_RATE_CAP_DEFAULT: int | str = DEFAULT_FRAME_RATE


def normalize_frame_rate_cap(value: object) -> int | str:
    """Normalize a persisted frame-rate cap to one of FRAME_RATE_CAP_VALUES."""

    if isinstance(value, str):
        if value.strip().lower() == "unlimited":
            return "Unlimited"
        try:
            value = int(value.strip())
        except ValueError:
            return FRAME_RATE_CAP_DEFAULT
    try:
        candidate = int(value)
    except (TypeError, ValueError):
        return FRAME_RATE_CAP_DEFAULT
    if candidate in (30, 60, 90, 120):
        return candidate
    return FRAME_RATE_CAP_DEFAULT
