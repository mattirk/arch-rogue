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
# The authored stair sprite (512x512, source anchor [256, 336]) is composited so
# the anchor lands on the logical tile center, but the visible circular shaft is
# centered on source pixel (256, 296) -- 40 master pixels, or 5 logical sprite
# pixels, north of the anchor.
# At WORLD_SCALE=5 that is 25 screen pixels north, which in the isometric
# projection (screen_y = (x + y) * TILE_H / 2) is a world shift of -25 / 80 =
# -0.3125 in (x + y), split symmetrically to -0.15625 on each axis. The inset
# shrinks the footprint so the player can step up to the masonry rim from every
# direction instead of being kept a full tile away.
STAIR_COLLISION_OFFSET_X = -0.15625
STAIR_COLLISION_OFFSET_Y = -0.15625
STAIR_COLLISION_INSET = 0.15

# Where the authored floor art paints its diamond center, in logical sprite
# pixels (x WORLD_SCALE at draw time) SOUTH of the projected tile center.
# Measured through the real tile pipeline (5.0): the generic dungeon floor
# lands +6 screen px at render bucket 0.8 (world_pixel_scale 4) and the
# authored special-room floors (soul hall, bar, shop) land +12 px. Standing
# props anchor their base-diamond axis (manifest ``source_anchor``) and add
# the matching contact offset so the prop base rests centered on the floor
# diamond the player actually sees.
FLOOR_ART_CONTACT_Y_OFFSET = 1.5
SPECIAL_FLOOR_ART_CONTACT_Y_OFFSET = 3.0

# Solid soul-hall/bar furnishings get the stairs treatment: an inset collision
# box shifted to align with what the player actually sees. Since 5.0 the prop
# sprites anchor their base-diamond axis directly on the special-floor contact
# line (SPECIAL_FLOOR_ART_CONTACT_Y_OFFSET = 3.0 logical px south of the tile
# center), while actors draw their feet on the ground line
# (ACTOR_FEET_Y_OFFSET = 10 logical px south). The remaining visual depth gap
# is therefore 10 - 3.0 = 7.0 logical px = 35 screen px at WORLD_SCALE=5,
# which in the isometric projection (screen_y = (x + y) * TILE_H / 2) is a
# world shift of -35 / 80 = -0.4375 in (x + y), split symmetrically to
# -0.21875 per axis. Shifting the box north-west by that amount makes the
# player's FEET stop at the pedestal's visible base from the south, and stops
# them slipping visually inside the pedestal from the north. The offset moves
# stops only along the screen-depth axis (x and y shift equally, so x-y is
# unchanged); east/west clearances are governed by the inset alone.
SOLID_FURNISHING_COLLISION_OFFSET_X = -0.21875
SOLID_FURNISHING_COLLISION_OFFSET_Y = -0.21875
SOLID_FURNISHING_COLLISION_INSET = 0.2
MAX_INVENTORY = 20
DUNGEON_DEPTH = 10
UI_SCALE = 1
PLAYER_HIT_RADIUS = 0.42
# Tight world-space footprint used when ordinary-sized actors move through the
# dungeon. It stays smaller than the combat hit radius so one-tile passages
# remain comfortable to navigate.
ACTOR_MOVE_COLLISION_RADIUS = 0.27
# The visual ground line for actors, in source pixels south of the projected
# world position (×WORLD_SCALE at draw time). ``draw_shadow`` centers every
# contact shadow on this line, and each grounded actor's sprite offset is
# expressed relative to it so feet stand on the shadow. Before 4.8.6.x the
# sprites anchored 4-5 source px above the shadow line, which read as every
# actor hovering above the floor.
ACTOR_FEET_Y_OFFSET = 10.0
# Moving both world axes by this amount projects the logical actor point onto
# the visible feet/contact line:
#
#   screen_y_delta = (dx + dy) * TILE_H / 2
#
# With dx == dy, the per-axis shift is therefore the rendered feet offset
# divided by TILE_H. Terrain collision uses this derived value to soften only
# the screen-north wall faces hidden by the logical/visual depth difference;
# camera position, zoom, and graphics tier cannot affect it.
ACTOR_GROUND_DEPTH_OFFSET = ACTOR_FEET_Y_OFFSET * WORLD_SCALE / TILE_H
# Players, enemies, and familiars "shine through" the tall wall/door graphics
# the painter's algorithm draws over them: after the depth-sorted world pass, each
# occluded actor's sprite is re-blitted in place at this alpha. Where the
# actor is still visible the re-blit lands on its own pixels (no change);
# where a wall covered it, a translucent silhouette shows through — clearly
# readable, but still short of x-ray vision.
ACTOR_WALL_GHOST_ALPHA = 112
# Peak (core) alpha of the soft elliptical aura drawn behind each through-wall
# silhouette. The radial falloff fades to zero at the ellipse edge, so the
# halo lifts the silhouette off the dark wall stone without reading as a
# spotlight.
ACTOR_WALL_GHOST_AURA_ALPHA = 96
# Floor traps stay invisible until a player closes within this range; it
# matches the HUD's nearby-trap "!" warning radius so the plate materializes
# on the same frame the hint appears. The trigger radius is 0.55, so even at
# full equipment sprint the trap surfaces roughly a quarter second before it
# can fire — a dodgeable telegraph, not a free map reveal.
TRAP_REVEAL_RADIUS = 1.35
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
# 4.10.1 — HD smooth fog-of-war edge (rendering/fog.py). On the HD desktop
# renderer with continuous lighting, the explored-area boundary is darkened by
# a continuous per-pixel "revelation field" composited through the light
# buffer instead of the per-tile ambient rects, so the fog edge is a soft
# gradient rather than hard tile diamonds. A revealed tile's field value is
# clamp((d - START) / SPAN, 0, 1) where d is the Euclidean distance (in
# tiles) to the nearest unrevealed in-bounds tile: the ramp starts just
# inside the outermost remembered tile and reaches full visibility ~2.25
# tiles into explored territory. EASE_RATE is the exponential per-second
# pull of the rendered field toward its target, so a fresh reveal rolls the
# fog back instead of stepping it one tile at a time; BLOOM_LIMIT caps how
# many tiles a full field rebuild may animate from black (floor entry blooms,
# restored saves far above the limit appear instantly).
HD_FOG_REVEAL_FALLOFF_START = 0.55
HD_FOG_REVEAL_FALLOFF_SPAN = 1.7
HD_FOG_REVEAL_EASE_RATE = 9.0
HD_FOG_REVEAL_BLOOM_LIMIT = 120
# Ground diamonds are drawn this many rings (Chebyshev) beyond the remembered
# frontier while smooth fog is active, sitting under field value 0 —
# multiplied to black, so nothing unexplored is shown. The fog lift then only
# ever uncovers geometry already on screen; without the margin, a tile and
# its fog fade would appear in the same frame and the diamond silhouette
# reads as a pop. One ring is exact: the bilinear tent spills at most half a
# tile past the frontier. Wall/door prisms keep the strict revealed gate and
# ease up from zero through their own lattice site instead.
HD_FOG_REVEAL_DRAW_MARGIN = 1
# Dark-floor (lantern) visibility edge. OUTER_MARGIN is the authored slack
# between the lantern radius and the hard tile-cull disc. Under continuous
# lighting the flat near-black ambient wash used to reach that cull boundary
# at full level, so terrain crossing it popped straight in at ambient
# brightness. DRAW_MARGIN widens the drawn disc by this many world tiles and
# the ambient wash feathers from its authored level at the old boundary to
# zero across the band — tiles now enter the frame multiplied to black and
# brighten as the player approaches. Quantized-alpha paths (lighting off,
# mobile lightweight) keep the strict disc and per-tile falloff unchanged.
DARK_VISIBILITY_OUTER_MARGIN = 0.65
DARK_VISIBILITY_DRAW_MARGIN = 2.0
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
# HD ships ten authored 512 px wall masters (wall_401..wall_410 in the sprite
# manifest's ``variants`` list): the plain block plus nine weathering
# treatments. Modern and Legacy keep the four-variant families above.
DUNGEON_HD_WALL_VARIANTS = 10

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
# 4.8.7 tapped ale barrel: a warm candle stub marks the bar's one free drink so
# the barrel stays findable on dark floors (real light source, same rationale
# as the soul-prop auras).
LIGHT_BAR_TAP_COLOR = (238, 178, 96)
LIGHT_BAR_TAP_RADIUS = 1.8
LIGHT_BAR_TAP_INTENSITY = 0.42
LIGHT_SHRINE_RADIUS = 2.3
LIGHT_SHRINE_INTENSITY = 0.55
# Descending stairs emit only a restrained violet wash; their authored frames
# carry the stronger local shaft pulse, so this light should not flood the room.
LIGHT_STAIRS_COLOR = (126, 74, 170)
LIGHT_STAIRS_RADIUS = 1.45
LIGHT_STAIRS_INTENSITY = 0.18
# 4.8.6 soul-hall furnishings glow as real static light sources so the pool of
# memory-light fades with scene lighting instead of fighting the screen-space
# lighting pass. The brazier keeps its full flickering torch flame; the
# mirror/chimes/reliquary carry this dimmer steady aura.
LIGHT_SOUL_PROP_RADIUS = 1.7
LIGHT_SOUL_PROP_INTENSITY = 0.3
# Transient skill/impact/projectile light tuning.
LIGHT_SKILL_PULSE_RADIUS = 2.1
LIGHT_SKILL_PULSE_TTL = 0.28
LIGHT_IMPACT_RADIUS = 1.8
LIGHT_IMPACT_TTL = 0.22
LIGHT_PROJECTILE_RADIUS = 1.5
LIGHT_PROJECTILE_TTL = 0.14
LIGHT_PROJECTILE_INTENSITY = 0.55
# Frost Nova max effect: with the Nova path plus a second full path mastered,
# the whole chamber flashes in light. The flash is a wave: it bursts from the
# caster, floods outward at WAVE_SPEED along the flood-filled chamber region
# (walls block it; doors catch the light but never pass it, open or closed),
# holds bright, then the whole lit area fades out together over the FADE
# window. Stamped per-tile into the light buffer so the wave hugs rooms,
# corridors, and doorway thresholds alike instead of bleeding through walls
# like a radial halo would.
LIGHT_ROOM_FLASH_COLOR = (228, 242, 255)
LIGHT_ROOM_FLASH_PEAK = 0.85
# Seconds a fully expanded flash lingers (hold + fade); the total ttl adds
# the wave's travel time to the farthest region tile on top of this.
LIGHT_ROOM_FLASH_TTL = 0.55
LIGHT_ROOM_FLASH_WAVE_SPEED = 26.0  # tiles per second of wavefront travel
LIGHT_ROOM_FLASH_ATTACK = 0.07  # per-tile brighten time as the wave arrives
LIGHT_ROOM_FLASH_FADE = 0.38  # global fade-out window at the end of the ttl
# Wave travel limit outside the caster's room. Inside a room the wave always
# reaches the far corner (the engulf damage does, so the light must too);
# corridor casts and spill through doorless room openings stop at this many
# BFS steps. Eight steps covers the maxed 5.2-tile blast radius along the
# worst L-shaped corridor path (~7.3 grid steps) plus a tile of glow, and
# keeps the wave snappy instead of crawling down distant hallways.
LIGHT_ROOM_FLASH_SPILL_DISTANCE = 8
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

# The multiplayer lobby's verification seal and the 4.9.x cooperative
# mini-games deliberately share one frozen rune vocabulary.  These names map
# to ``menu.glyph.sigil.<name>`` UI assets; keeping the tuple outside either
# renderer lets the lobby and story runtime reuse the artwork without creating
# an import dependency between menus and story code.  Order is protocol-like
# content: changing it alters deterministic seals and mini-game boards.
SHARED_SIGIL_NAMES = (
    "serpent",
    "hammer",
    "skull",
    "star",
    "cross",
    "flame",
    "key",
    "map",
    "shield",
    "sword",
    "claw",
    "sun",
    "moon",
    "dragon",
    "phoenix",
    "ouroboros",
    "clock",
    "infinity",
)

# 4.3.17 frame-rate cap option (schema 7). The order here is also the cycle
# order used by the Options row. "Unlimited" maps to ``clock.tick(0)``.
FRAME_RATE_CAP_VALUES: tuple[int | str, ...] = (30, 60, 90, 120, "Unlimited")
FRAME_RATE_CAP_DEFAULT: int | str = DEFAULT_FRAME_RATE

# Graphics-quality tiers. Legacy keeps the procedural renderer, Modern uses
# the original lower-resolution authored world set, and HD uses the current
# high-resolution world masters. Actors, props, menus, and HUD art are shared
# by the two authored tiers.
GRAPHICS_TIER_LEGACY = "legacy"
GRAPHICS_TIER_MODERN = "modern"
GRAPHICS_TIER_HD = "hd"
GRAPHICS_TIER_VALUES = (
    GRAPHICS_TIER_LEGACY,
    GRAPHICS_TIER_MODERN,
    GRAPHICS_TIER_HD,
)
GRAPHICS_TIER_DEFAULT = GRAPHICS_TIER_HD
GRAPHICS_TIER_LABELS = {
    GRAPHICS_TIER_LEGACY: "Legacy",
    GRAPHICS_TIER_MODERN: "Modern",
    GRAPHICS_TIER_HD: "HD",
}

# 4.8.10 "NPCs join the fight": IdleNpc kinds a player can greet into combat
# allies. The garden frog (non-humanoid ambience) is pacifist permanently; the
# Lossless Soul and Story Guest join through their own story resolutions
# instead of the greeting. Shared by interactions, story NPC runtime, and the
# combat ally mixin, so it lives here rather than in any one of them.
GREETABLE_IDLE_NPC_KINDS = frozenset(("bar", "garden", "bar_dancer"))


def normalize_graphics_tier(
    value: object,
    *,
    default: str = GRAPHICS_TIER_DEFAULT,
) -> str:
    """Normalize persisted/user-facing graphics-tier values."""

    normalized_default = str(default).strip().casefold()
    if normalized_default not in GRAPHICS_TIER_VALUES:
        normalized_default = GRAPHICS_TIER_DEFAULT
    candidate = str(value).strip().casefold()
    if candidate in GRAPHICS_TIER_VALUES:
        return candidate
    return normalized_default


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
