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
import json
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
from arch_rogue.options import (
    MOBILE_RENDER_QUALITY_MODES,
    mobile_logical_resolution,
)

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
        "--mobile",
        action="store_true",
        help="Profile the Android layout and mobile rendering quality path.",
    )
    parser.add_argument(
        "--mobile-quality",
        choices=MOBILE_RENDER_QUALITY_MODES,
        default="performance",
        help="Logical render tier used with --mobile (width/height remain physical).",
    )
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
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help=(
            "Write a JSON snapshot of phase timings to this path. "
            "Used to establish a regression baseline."
        ),
    )
    parser.add_argument(
        "--compare",
        type=Path,
        default=None,
        help=(
            "Compare phase timings against the JSON baseline at this path and "
            "exit nonzero if any phase regresses by more than --threshold "
            "(default 10%%)."
        ),
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=10.0,
        help="Max allowed regression percentage per phase when using --compare.",
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
    if args.threshold <= 0.0:
        parser.error("--threshold must be positive")
    if args.baseline and args.compare:
        parser.error("--baseline and --compare are mutually exclusive")
    if args.top <= 0:
        parser.error("--top must be positive")
    return args


def prepare_game(args: argparse.Namespace, temp_dir: Path) -> Game:
    physical_size = (args.width, args.height)
    render_size = (
        mobile_logical_resolution(physical_size, args.mobile_quality)
        if args.mobile
        else physical_size
    )
    game = Game(
        screen_size=render_size,
        headless=True,
        save_path=temp_dir / "run.json",
        mobile=args.mobile,
    )
    game.mobile_render_quality = args.mobile_quality
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


def _compare_baseline(baseline_path: Path, snapshot: dict, threshold_pct: float) -> str | None:
    """Return a failure message if any phase regresses beyond threshold_pct.

    Regression = current timing is more than ``threshold_pct`` percent slower
    than the baseline. Improvements and noise within the threshold pass. A
    missing baseline file or missing phase is reported as a failure message.
    """

    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return f"could not read baseline {baseline_path}: {exc}"
    base_phases = baseline.get("phases") or {}
    cur_phases = snapshot.get("phases") or {}
    if not base_phases or not cur_phases:
        return f"baseline/snapshot missing phases (baseline={base_phases!r})"
    failures: list[str] = []
    for phase, cur_ms in cur_phases.items():
        base_ms = base_phases.get(phase)
        if base_ms is None or base_ms <= 0.0:
            failures.append(f"{phase}: missing/invalid baseline {base_ms!r}")
            continue
        ratio = cur_ms / base_ms
        regression_pct = (ratio - 1.0) * 100.0
        if regression_pct > threshold_pct:
            failures.append(
                f"{phase}: {cur_ms:.3f} ms/frame vs baseline "
                f"{base_ms:.3f} ms/frame (+{regression_pct:.1f}% > {threshold_pct:.1f}%)"
            )
    return "; ".join(failures) if failures else None


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        with tempfile.TemporaryDirectory(prefix="arch-rogue-profile-") as temp_name:
            game = prepare_game(args, Path(temp_name))
            enemy_count = len(game.enemies)
            cache_before = game.sprites.cache_stats()
            update_profile, render_profile, update_seconds, render_seconds = run_profile(
                game, args.warmup, args.frames
            )
            cache_after = game.sprites.cache_stats()

            profile_name = args.scenario
            if args.mobile:
                profile_name = f"{profile_name}-mobile-{args.mobile_quality}"
            update_path = output_dir / f"{profile_name}-update.prof"
            render_path = output_dir / f"{profile_name}-render.prof"
            update_profile.dump_stats(update_path)
            render_profile.dump_stats(render_path)

            print(
                "Profile summary: "
                f"scenario={args.scenario} seed={args.seed} depth={args.depth} "
                f"frames={args.frames} enemies={enemy_count} zoom={args.zoom:.2f} "
                f"lighting={'off' if args.no_lighting else 'on'} "
                f"mobile={args.mobile} quality={args.mobile_quality} "
                f"render_size={game.screen.get_size()} "
                f"viewport={game.mobile_world_viewport().size if args.mobile else game.screen.get_size()}"
            )
            print(
                f"Profiled update: {update_seconds * 1000.0 / args.frames:.3f} ms/frame; "
                f"render: {render_seconds * 1000.0 / args.frames:.3f} ms/frame"
            )
            print(
                "Asset cache: "
                f"{cache_after}; profile loads="
                f"{cache_after.get('source_loads', 0) - cache_before.get('source_loads', 0)}, "
                f"frame builds="
                f"{cache_after.get('frame_builds', 0) - cache_before.get('frame_builds', 0)}"
            )
            print(f"Profiles: {update_path} and {render_path}")
            update_ms = update_seconds * 1000.0 / args.frames
            render_ms = render_seconds * 1000.0 / args.frames
            snapshot = {
                "scenario": profile_name,
                "seed": args.seed,
                "depth": args.depth,
                "frames": args.frames,
                "warmup": args.warmup,
                "width": args.width,
                "height": args.height,
                "zoom": args.zoom,
                "mobile": args.mobile,
                "mobile_quality": args.mobile_quality,
                "lighting": not args.no_lighting,
                "enemies": enemy_count,
                "render_size": list(game.screen.get_size()),
                "phases": {
                    "update_ms_per_frame": update_ms,
                    "render_ms_per_frame": render_ms,
                },
            }
            if args.baseline:
                args.baseline.parent.mkdir(parents=True, exist_ok=True)
                args.baseline.write_text(
                    json.dumps(snapshot, indent=2, sort_keys=True),
                    encoding="utf-8",
                )
                print(f"Baseline written: {args.baseline}")
            if args.compare:
                failure = _compare_baseline(args.compare, snapshot, args.threshold)
                if failure:
                    print(f"REGRESSION: {failure}", file=sys.stderr)
                    sys.exit(1)
                print(f"No regression vs baseline {args.compare}")
            print_profile("Update", update_profile, args.top)
            print_profile("Render", render_profile, args.top)
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
