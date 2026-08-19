# SPDX-License-Identifier: Apache-2.0
"""Capture staged 1920x1080 gameplay screenshots for the Steam store page.

Runs the game headless (dummy SDL drivers) like tools/profile_game.py, but
instead of profiling it stages one scene per shot — exploration, combat,
shrines, bosses, overlays — renders a few frames so animations and effects
settle, and saves the final frame as PNG.

    .venv_host/bin/python tools/capture_screenshots.py [--out DIR] [--only NAME]

Each recipe is deterministic (fixed seed) but staging is best-effort: a shot
whose target is missing on the generated floor (no shrine, no boss) is
reported and skipped rather than failing the batch.
"""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("ARCH_ROGUE_NO_STEAM", "1")

import pygame

from arch_rogue.content import ARCHETYPES
from arch_rogue.dungeon import MAP_H, MAP_W
from arch_rogue.game import Game
from arch_rogue.models import Tile

FIXED_DT = 1.0 / 60.0
SIZE = (1920, 1080)


def new_game(seed: int, depth: int, archetype_index: int, temp_dir: Path) -> Game:
    game = Game(
        screen_size=SIZE,
        headless=True,
        save_path=temp_dir / "run.json",
    )
    game.options_path = temp_dir / "options.json"
    game.set_graphics_tier("hd")
    game.rng.seed(seed)
    game.restart(ARCHETYPES[archetype_index])
    if game.story_intro_pending:
        game.choose_story_relic_path(0)
    for _ in range(depth - 1):
        game.descend_to_next_depth()
    game.active_cutscene = None
    game.story_intro_pending = False
    game.state = "playing"
    game.player.max_hp = 1_000_000
    game.player.hp = game.player.max_hp
    game.update_revealed_tiles()
    game.snap_camera_to_player()
    return game


def open_arena(game: Game, radius: int = 6) -> None:
    cx, cy = int(game.player.x), int(game.player.y)
    for x in range(max(1, cx - radius), min(MAP_W - 1, cx + radius + 1)):
        for y in range(max(1, cy - radius), min(MAP_H - 1, cy + radius + 1)):
            game.dungeon.tiles[x][y] = Tile.FLOOR
    game.update_revealed_tiles()


def cluster_enemies(game: Game, count: int, spread: float = 1.1) -> None:
    px, py = game.player.x, game.player.y
    for index, enemy in enumerate(game.enemies[:count]):
        enemy.x = px + ((index % 5) - 2) * spread
        enemy.y = py + ((index // 5) - 1) * spread - 1.4
        enemy.aggro_range = 99.0
        enemy.attack_timer = 0.2 + (index % 7) * 0.1


def settle(game: Game, frames: int, cast_frames: tuple[int, ...] = ()) -> None:
    for frame in range(frames):
        if frame in cast_frames:
            game.player.mana = game.player.max_mana
            game.player_cast_bolt()
        game.ui_elapsed += FIXED_DT
        game.update(FIXED_DT)
        game.snap_camera_to_player()
        game.draw()


def move_player_to(game: Game, x: float, y: float) -> None:
    game.player.x, game.player.y = x, y
    game.update_revealed_tiles()
    game.snap_camera_to_player()


def biggest_room_center(game: Game) -> tuple[float, float]:
    rooms = sorted(
        game.dungeon.rooms, key=lambda r: r.w * r.h, reverse=True
    )
    cx, cy = rooms[0].center if rooms else (game.player.x, game.player.y)
    return float(cx), float(cy)


def scatter_loot(game: Game, count: int, spread: float = 2.2) -> None:
    px, py = game.player.x, game.player.y
    for index in range(count):
        x = px + ((index % 3) - 1) * spread + 0.4 * (index % 2)
        y = py + ((index // 3) - 1) * spread - 0.5
        game.items.append(game._make_loot(x, y))


def remove_bosses(game: Game) -> None:
    game.enemies = [e for e in game.enemies if getattr(e, "size", 1) < 2]


def shot_explore(game: Game) -> bool:
    remove_bosses(game)
    move_player_to(game, *biggest_room_center(game))
    scatter_loot(game, 5)
    nearby = game.enemies[:4]
    for index, enemy in enumerate(nearby):
        enemy.x = game.player.x + ((index % 2) * 2 - 1) * 3.4
        enemy.y = game.player.y + ((index // 2) * 2 - 1) * 2.4
    game.update_revealed_tiles()
    settle(game, 14)
    return True


def shot_combat(game: Game) -> bool:
    if not game.enemies:
        return False
    open_arena(game)
    cluster_enemies(game, 10)
    settle(game, 45, cast_frames=(20, 34))
    return True


def shot_shrine(game: Game) -> bool:
    if not game.shrines:
        return False
    remove_bosses(game)
    shrine = game.shrines[0]
    move_player_to(game, shrine.x + 1.2, shrine.y + 0.6)
    scatter_loot(game, 3)
    settle(game, 12)
    return True


def shot_boss(game: Game) -> bool:
    bosses = [e for e in game.enemies if getattr(e, "size", 1) >= 2]
    if not bosses:
        return False
    boss = bosses[0]
    move_player_to(game, boss.x + 1.6, boss.y + 2.2)
    open_arena(game, radius=5)
    boss.aggro_range = 99.0
    settle(game, 40, cast_frames=(18,))
    return True


def shot_inventory(game: Game) -> bool:
    px, py = game.player.x, game.player.y
    for _ in range(60):
        if len(game.player.inventory) >= 9:
            break
        item = game._make_loot(px, py)
        if item.name not in {i.name for i in game.player.inventory}:
            game.player.inventory.append(item)
    game.sort_inventory()
    settle(game, 8)
    game.inventory_open = True
    game.draw()
    return True


RECIPES = (
    # name, depth, archetype index, zoom, stage function
    ("explore_depth1", 1, 0, 1.15, shot_explore),
    ("combat_depth3", 3, 1, 1.2, shot_combat),
    ("shrine_depth2", 2, 3, 1.15, shot_shrine),
    ("dark_depth6", 6, 4, 1.15, shot_explore),
    ("combat_depth8", 8, 2, 1.2, shot_combat),
    ("boss_depth10", 10, 0, 1.05, shot_boss),
    ("inventory_depth5", 5, 1, 1.0, shot_inventory),
)

# A recipe whose staging target is floor-dependent (shrines) retries with
# bumped seeds until one generates.
SEED_ATTEMPTS = 6


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("tools/steam/store_assets/screenshots"),
    )
    parser.add_argument("--only", help="Capture just the named recipe.")
    parser.add_argument("--seed", type=int, default=5031380)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    try:
        for index, (name, depth, arch, zoom, stage) in enumerate(RECIPES):
            if args.only and name != args.only:
                continue
            for attempt in range(SEED_ATTEMPTS):
                with tempfile.TemporaryDirectory(prefix="ar-shot-") as temp:
                    seed = args.seed + index + attempt * 1013
                    game = new_game(seed, depth, arch, Path(temp))
                    game.view_zoom = zoom
                    if not stage(game):
                        continue
                    path = args.out / f"{name}.png"
                    pygame.image.save(game.screen, path)
                    print(f"wrote {path} (seed {seed})")
                    break
            else:
                print(f"SKIP {name}: no staging target in {SEED_ATTEMPTS} seeds")
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
