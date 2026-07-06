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
# skill-tree speed bonuses, or Haste Shrine buffs. `player.speed` is retained
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

SlashEffect = tuple[float, float, float, float, float]
