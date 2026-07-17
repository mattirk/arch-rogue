# SPDX-License-Identifier: Apache-2.0
"""Deterministic headless CPU profiler for representative gameplay frames.

Run from the repository root, for example:

    .venv/bin/python tools/profile_game.py --scenario crowd --frames 240

The harness alternates fixed-step updates and renders while recording them in
separate cProfile files. It deliberately bypasses ``Game.run`` so frame limiting
sleep and human input do not contaminate the CPU profile.
"""

from __future__ import annotations

import argparse
import cProfile
import os
import pstats
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from arch_rogue.constants import DUNGEON_DEPTH
from arch_rogue.content import ARCHETYPES
from arch_rogue.dungeon import MAP_H, MAP_W
from arch_rogue.game import Game
from arch_rogue.models import Tile

FIXED_DT = 1.0 / 60.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=("quiet", "crowd"),
        default="crowd",
        help="Generated floor as-is, or a dense deterministic combat arena.",
    )
    parser.add_argument("--frames", type=int, default=240)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--seed", type=int, default=3161)
    parser.add_argument("--depth", type=int, choices=range(1, DUNGEON_DEPTH + 1), default=DUNGEON_DEPTH)
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=540)
    parser.add_argument("--zoom", type=float, default=1.0)
    parser.add_argument(
        "--no-lighting",
        action="store_true",
        help="Disable continuous lighting to isolate its rendering cost.",
    )
    parser.add_argument("--top", type=int, default=25, help="Number of cumulative-time rows to print.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("build/profiles"),
        help="Directory for update.prof and render.prof outputs.",
    )
    args = parser.parse_args()
    if args.frames <= 0:
        parser.error("--frames must be positive")
    if args.warmup < 0:
        parser.error("--warmup cannot be negative")
    if args.width < 320 or args.height < 240:
        parser.error("profile resolution must be at least 320x240")
    if args.zoom <= 0.0:
        parser.error("--zoom must be positive")
    if args.top <= 0:
        parser.error("--top must be positive")
    return args


def prepare_game(args: argparse.Namespace, temp_dir: Path) -> Game:
    game = Game(
        screen_size=(args.width, args.height),
        headless=True,
        save_path=temp_dir / "run.json",
    )
    game.options_path = temp_dir / "options.json"
    game.rng.seed(args.seed)
    game.restart(ARCHETYPES[2])  # Fixed archetype keeps player asset setup deterministic.

    if game.story_intro_pending:
        if not game.choose_story_relic_path(0):
            raise RuntimeError("could not resolve the deterministic story intro")
    for _ in range(args.depth - 1):
        game.descend_to_next_depth()

    game.active_cutscene = None
    game.story_intro_pending = False
    game.state = "playing"
    game.view_zoom = args.zoom
    game._lighting_enabled = not args.no_lighting
    game.player.max_hp = 1_000_000
    game.player.hp = game.player.max_hp

    if args.scenario == "crowd":
        prepare_crowd_arena(game)

    game.revealed_tiles = set()
    game.update_revealed_tiles()
    game.snap_camera_to_player()
    return game


def prepare_crowd_arena(game: Game) -> None:
    """Cluster the generated floor population without changing entity behavior."""

    px, py = game.player.x, game.player.y
    center_x, center_y = int(px), int(py)
    for x in range(max(0, center_x - 7), min(MAP_W, center_x + 8)):
        for y in range(max(0, center_y - 7), min(MAP_H, center_y + 8)):
            game.dungeon.tiles[x][y] = Tile.FLOOR

    for index, enemy in enumerate(game.enemies):
        enemy.x = px + ((index % 9) - 4) * 0.72
        enemy.y = py + ((index // 9) - 2) * 0.72
        enemy.aggro_range = 99.0
        enemy.attack_timer = 0.0


def run_profile(game: Game, warmup: int, frames: int) -> tuple[cProfile.Profile, cProfile.Profile, float, float]:
    for _ in range(warmup):
        game.ui_elapsed += FIXED_DT
        game.update(FIXED_DT)
        game.draw()

    update_profile = cProfile.Profile()
    render_profile = cProfile.Profile()
    update_seconds = 0.0
    render_seconds = 0.0

    for _ in range(frames):
        game.ui_elapsed += FIXED_DT

        started = time.perf_counter()
        update_profile.enable()
        game.update(FIXED_DT)
        update_profile.disable()
        update_seconds += time.perf_counter() - started

        started = time.perf_counter()
        render_profile.enable()
        game.draw()
        render_profile.disable()
        render_seconds += time.perf_counter() - started

    return update_profile, render_profile, update_seconds, render_seconds


def print_profile(label: str, profile: cProfile.Profile, top: int) -> None:
    print(f"\n{label} hotspots (cumulative time)")
    print("-" * (len(label) + 28))
    pstats.Stats(profile, stream=sys.stdout).strip_dirs().sort_stats("cumulative").print_stats(top)


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        with tempfile.TemporaryDirectory(prefix="arch-rogue-profile-") as temp_name:
            game = prepare_game(args, Path(temp_name))
            enemy_count = len(game.enemies)
            update_profile, render_profile, update_seconds, render_seconds = run_profile(
                game, args.warmup, args.frames
            )

            update_path = output_dir / f"{args.scenario}-update.prof"
            render_path = output_dir / f"{args.scenario}-render.prof"
            update_profile.dump_stats(update_path)
            render_profile.dump_stats(render_path)

            print(
                "Profile summary: "
                f"scenario={args.scenario} seed={args.seed} depth={args.depth} "
                f"frames={args.frames} enemies={enemy_count} zoom={args.zoom:.2f} "
                f"lighting={'off' if args.no_lighting else 'on'}"
            )
            print(
                f"Profiled update: {update_seconds * 1000.0 / args.frames:.3f} ms/frame; "
                f"render: {render_seconds * 1000.0 / args.frames:.3f} ms/frame"
            )
            print(f"Profiles: {update_path} and {render_path}")
            print_profile("Update", update_profile, args.top)
            print_profile("Render", render_profile, args.top)
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
