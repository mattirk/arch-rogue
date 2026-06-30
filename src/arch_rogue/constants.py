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

SlashEffect = tuple[float, float, float, float, float]
