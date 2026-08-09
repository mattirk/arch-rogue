# SPDX-License-Identifier: Apache-2.0
"""Repeatable wall-clock benchmarks for the first performance pass.

The harness uses SDL's dummy drivers, temporary save files, and uninstrumented
``perf_counter`` samples. It intentionally lives outside the game runtime and
does not modify the source checkout; only an explicit ``--output`` path is
persisted.

Run the current tree:

    python tools/benchmark_first_pass.py --output build/performance/current.json

Run the same harness against another checkout:

    PYTHONPATH=/path/to/baseline/src \
      python tools/benchmark_first_pass.py --output baseline.json

Use ``--quick`` for a short smoke run. The default output contains a compact
human summary followed by JSON; ``--json-only`` is convenient for automation.
"""

from __future__ import annotations

import argparse
import copy
import gc
import json
import math
import os
import platform
import statistics
import subprocess
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

import pygame

import arch_rogue
from arch_rogue.audio import AudioSystem, MusicProfile
from arch_rogue.constants import DUNGEON_DEPTH
from arch_rogue.content import ARCHETYPES
from arch_rogue.dungeon import MAP_H, MAP_W
from arch_rogue.game import Game
from arch_rogue.models import Enemy, Tile

FIXED_DT = 1.0 / 60.0


@dataclass(frozen=True, slots=True)
class TimingSummary:
    samples: int
    p50_ms: float
    p95_ms: float
    mean_ms: float
    min_ms: float
    max_ms: float

    @classmethod
    def from_values(cls, values: Sequence[float]) -> TimingSummary:
        if not values:
            raise ValueError("at least one timing sample is required")
        ordered = sorted(float(value) for value in values)
        return cls(
            samples=len(ordered),
            p50_ms=_percentile(ordered, 0.50),
            p95_ms=_percentile(ordered, 0.95),
            mean_ms=statistics.fmean(ordered),
            min_ms=ordered[0],
            max_ms=ordered[-1],
        )


@dataclass(frozen=True, slots=True)
class BenchmarkConfig:
    seed: int
    depth: int
    width: int
    height: int
    warmup: int
    update_samples: int
    render_samples: int
    ui_samples: int
    kill_samples: int
    music_samples: int
    music_timeout: float
    music_poll_seconds: float
    include_ui: bool
    include_music: bool


def _percentile(ordered: Sequence[float], quantile: float) -> float:
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    fraction = position - lower
    return float(ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction)


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true", help="Use smoke-sized samples.")
    parser.add_argument("--seed", type=int, default=3161)
    parser.add_argument(
        "--depth",
        type=int,
        choices=range(1, DUNGEON_DEPTH + 1),
        default=DUNGEON_DEPTH,
    )
    parser.add_argument("--width", type=_positive_int, default=1280)
    parser.add_argument("--height", type=_positive_int, default=720)
    parser.add_argument("--warmup", type=int, default=None)
    parser.add_argument("--update-samples", type=_positive_int, default=None)
    parser.add_argument("--render-samples", type=_positive_int, default=None)
    parser.add_argument("--ui-samples", type=_positive_int, default=None)
    parser.add_argument("--kill-samples", type=_positive_int, default=None)
    parser.add_argument("--music-samples", type=_positive_int, default=None)
    parser.add_argument("--music-timeout", type=float, default=5.0)
    parser.add_argument("--music-poll-ms", type=float, default=2.0)
    parser.add_argument("--skip-ui", action="store_true")
    parser.add_argument("--skip-music", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optionally write the JSON result to this path.",
    )
    output_mode = parser.add_mutually_exclusive_group()
    output_mode.add_argument("--json-only", action="store_true")
    output_mode.add_argument("--text-only", action="store_true")
    args = parser.parse_args(argv)
    if args.warmup is not None and args.warmup < 0:
        parser.error("--warmup cannot be negative")
    if args.width < 320 or args.height < 240:
        parser.error("benchmark resolution must be at least 320x240")
    if args.music_timeout <= 0.0:
        parser.error("--music-timeout must be positive")
    if args.music_poll_ms <= 0.0:
        parser.error("--music-poll-ms must be positive")
    return args


def _resolved_config(args: argparse.Namespace) -> BenchmarkConfig:
    quick = bool(args.quick)

    def selected(value: int | None, normal: int, smoke: int) -> int:
        return int(value if value is not None else (smoke if quick else normal))

    return BenchmarkConfig(
        seed=int(args.seed),
        depth=int(args.depth),
        width=int(args.width),
        height=int(args.height),
        warmup=selected(args.warmup, 60, 2),
        update_samples=selected(args.update_samples, 180, 8),
        render_samples=selected(args.render_samples, 90, 6),
        ui_samples=selected(args.ui_samples, 60, 4),
        kill_samples=selected(args.kill_samples, 31, 4),
        music_samples=selected(args.music_samples, 3, 1),
        music_timeout=float(args.music_timeout),
        music_poll_seconds=float(args.music_poll_ms) / 1000.0,
        include_ui=not bool(args.skip_ui),
        include_music=not bool(args.skip_music),
    )


def _time_samples(
    callback: Callable[[], object],
    count: int,
    *,
    before_each: Callable[[], None] | None = None,
) -> TimingSummary:
    gc.collect()
    samples: list[float] = []
    for _ in range(count):
        if before_each is not None:
            before_each()
        started = time.perf_counter_ns()
        callback()
        samples.append((time.perf_counter_ns() - started) / 1_000_000.0)
    return TimingSummary.from_values(samples)


def _warm(
    callback: Callable[[], object],
    count: int,
    *,
    before_each: Callable[[], None] | None = None,
) -> None:
    for _ in range(count):
        if before_each is not None:
            before_each()
        callback()


def _prepare_game(config: BenchmarkConfig, temp_dir: Path) -> Game:
    game = Game(
        screen_size=(config.width, config.height),
        headless=True,
        save_path=temp_dir / "run.json",
    )
    game.options_path = temp_dir / "options.json"
    game.rng.seed(config.seed)
    game.restart(ARCHETYPES[2])
    if game.story_intro_pending and not game.choose_story_relic_path(0):
        raise RuntimeError("could not resolve deterministic story introduction")
    for _ in range(config.depth - 1):
        game.descend_to_next_depth()
    game.active_cutscene = None
    if hasattr(game, "active_mini_game"):
        game.active_mini_game = None
    game.story_intro_pending = False
    game.state = "playing"
    game.music_enabled = False
    game.audio_enabled = False
    game.player.max_hp = 1_000_000
    game.player.hp = game.player.max_hp
    game.player.next_xp = 1_000_000_000
    game.revealed_tiles = set()
    game.update_revealed_tiles()
    game.snap_camera_to_player()
    reset_checkpoint = getattr(game, "reset_run_checkpoint", None)
    if callable(reset_checkpoint):
        reset_checkpoint()
    return game


def _open_crowd_arena(game: Game) -> None:
    center_x, center_y = int(game.player.x), int(game.player.y)
    for x in range(max(0, center_x - 11), min(MAP_W, center_x + 12)):
        for y in range(max(0, center_y - 11), min(MAP_H, center_y + 12)):
            game.dungeon.tiles[x][y] = Tile.FLOOR


def _configure_crowd(game: Game, count: int) -> list[tuple[float, float]]:
    if not game.enemies:
        raise RuntimeError("generated benchmark floor has no enemy templates")
    templates = [copy.deepcopy(enemy) for enemy in game.enemies]
    enemies: list[Enemy] = []
    columns = 10
    rows = math.ceil(count / columns)
    positions: list[tuple[float, float]] = []
    for index in range(count):
        enemy = copy.deepcopy(templates[index % len(templates)])
        enemy.name = f"Benchmark Enemy {index:03d}"
        enemy.kind = "melee"
        enemy.role = "bruiser"
        enemy.size = 1
        enemy.damage = 0
        enemy.hp = enemy.max_hp
        enemy.attack_range = 0.8
        enemy.attack_timer = 60.0
        enemy.aggro_range = 99.0
        enemy.elite_modifier = ""
        enemy.telegraph = ""
        enemy.ability_keys = ()
        enemy.ability_timers.clear()
        x = game.player.x + (index % columns - (columns - 1) / 2.0) * 0.72
        y = game.player.y + (index // columns - (rows - 1) / 2.0) * 0.72
        enemy.x, enemy.y = x, y
        positions.append((x, y))
        enemies.append(enemy)
    game.enemies = enemies
    _open_crowd_arena(game)
    return positions


def _reset_crowd(game: Game, positions: Sequence[tuple[float, float]]) -> None:
    for enemy, (x, y) in zip(game.enemies, positions, strict=True):
        enemy.x, enemy.y = x, y
        enemy.hp = enemy.max_hp
        enemy.attack_timer = 60.0
        enemy.windup_time = 0.0
        enemy.windup_duration = 0.0
        enemy.windup_attack = ""
        enemy.knockback_vx = 0.0
        enemy.knockback_vy = 0.0
        enemy.pending_locomotion_scale = None
        enemy.pending_locomotion_anim_scale = None
        enemy.statuses.clear()
    game.player.hp = game.player.max_hp
    game.projectiles.clear()
    game.slashes.clear()
    game.impact_effects.clear()
    game.floaters.clear()
    if hasattr(game, "_enemy_spatial_index"):
        game._enemy_spatial_index = None


def _benchmark_update(
    game: Game,
    count: int,
    config: BenchmarkConfig,
) -> TimingSummary:
    positions = _configure_crowd(game, count)

    def reset() -> None:
        _reset_crowd(game, positions)

    _warm(
        lambda: game.update(FIXED_DT),
        config.warmup,
        before_each=reset,
    )
    return _time_samples(
        lambda: game.update(FIXED_DT),
        config.update_samples,
        before_each=reset,
    )


def _reset_render_retention(game: Game) -> None:
    for name in (
        "_paused_scene_cache",
        "_static_menu_last_signature",
        "_mobile_static_menu_last_signature",
    ):
        if hasattr(game, name):
            setattr(game, name, None)


def _set_playing_overlay(
    game: Game,
    *,
    inventory: bool = False,
    character: bool = False,
) -> None:
    game.state = "playing"
    game.inventory_open = inventory
    game.character_menu_open = character
    game.shop_open = False
    game.show_help = False
    if character:
        game.character_menu_tab = "disciplines"
    _reset_render_retention(game)


def _benchmark_draw_state(
    game: Game,
    config: BenchmarkConfig,
    *,
    warmup: int | None = None,
    samples: int | None = None,
) -> TimingSummary:
    _warm(game.draw, config.warmup if warmup is None else warmup)
    return _time_samples(
        game.draw,
        config.render_samples if samples is None else samples,
    )


def _make_kill_target(game: Game, index: int) -> Enemy:
    return Enemy(
        f"Checkpoint Benchmark {index}",
        "melee",
        game.player.x + 0.8,
        game.player.y,
        1,
        1,
        0.0,
        0,
        0,
        1.0,
        1.0,
    )


def _benchmark_routine_kill(
    game: Game,
    config: BenchmarkConfig,
) -> TimingSummary:
    game.state = "playing"
    game.inventory_open = False
    game.character_menu_open = False
    game.shop_open = False
    game.player.next_xp = 1_000_000_000
    index = 0

    def kill_once() -> None:
        nonlocal index
        target = _make_kill_target(game, index)
        index += 1
        game.enemies.append(target)
        game.kill_enemy(target)

    def cleanup() -> None:
        game.items.clear()
        game.floaters.clear()
        game.impact_effects.clear()
        game.enemy_hit_flashes.clear()
        reset_checkpoint = getattr(game, "reset_run_checkpoint", None)
        if callable(reset_checkpoint):
            reset_checkpoint()

    samples: list[float] = []
    gc.collect()
    for _ in range(config.kill_samples):
        cleanup()
        started = time.perf_counter_ns()
        kill_once()
        samples.append((time.perf_counter_ns() - started) / 1_000_000.0)
    cleanup()
    return TimingSummary.from_values(samples)


def _benchmark_forced_save(
    game: Game,
    config: BenchmarkConfig,
) -> tuple[TimingSummary, int]:
    """Measure an explicit durable checkpoint and its on-disk payload size."""

    game.state = "playing"
    game.inventory_open = False
    game.character_menu_open = False
    game.shop_open = False
    reset_checkpoint = getattr(game, "reset_run_checkpoint", None)

    def save_once() -> None:
        if callable(reset_checkpoint):
            reset_checkpoint()
        if not game.save_run():
            raise RuntimeError(game.last_save_error or "benchmark save failed")

    # A handful of untimed writes settles filesystem/page-cache setup without
    # turning a durable-I/O probe into most of the harness runtime.
    _warm(save_once, min(3, config.warmup))
    summary = _time_samples(save_once, config.kill_samples)
    return summary, game.save_path.stat().st_size


def _music_profile(kind: str, sample_index: int) -> MusicProfile:
    if kind == "menu":
        return MusicProfile(
            0xA11CE + sample_index,
            "Menu",
            "Main Menu",
            "Quiet",
            depth=0,
            mood="menu",
        )
    return MusicProfile(
        0xB000 + sample_index,
        "Arcanist",
        "Obsidian Vault",
        "Cursed",
        depth=10,
    )


def _stop_audio(audio: AudioSystem) -> None:
    try:
        audio.stop_music()
    except pygame.error:
        pass
    shutdown = getattr(audio, "shutdown", None)
    if callable(shutdown):
        shutdown()


def _benchmark_music_kind(
    kind: str,
    config: BenchmarkConfig,
) -> tuple[TimingSummary | None, TimingSummary | None, dict[str, Any]]:
    call_samples: list[float] = []
    ready_samples: list[float] = []
    timeouts = 0
    unavailable = 0
    background_capable = False
    for sample_index in range(config.music_samples):
        audio = AudioSystem()
        background_capable = background_capable or hasattr(
            audio, "_request_music_generation"
        )
        try:
            if not audio.initialize(headless=False):
                unavailable += 1
                continue
            profile = _music_profile(kind, sample_index)
            target_key = audio._profile_seed(profile)
            started = time.perf_counter()
            audio.sync_music(profile, enabled=True)
            call_finished = time.perf_counter()
            call_samples.append((call_finished - started) * 1000.0)
            deadline = started + config.music_timeout
            while (
                audio.current_music_seed != target_key
                and time.perf_counter() < deadline
            ):
                time.sleep(config.music_poll_seconds)
                audio.sync_music(profile, enabled=True)
            if audio.current_music_seed == target_key:
                ready_samples.append((time.perf_counter() - started) * 1000.0)
            else:
                timeouts += 1
        finally:
            _stop_audio(audio)
    details = {
        "mode": "background" if background_capable else "synchronous",
        "requested_samples": config.music_samples,
        "completed_samples": len(ready_samples),
        "timeouts": timeouts,
        "mixer_unavailable": unavailable,
    }
    return (
        TimingSummary.from_values(call_samples) if call_samples else None,
        TimingSummary.from_values(ready_samples) if ready_samples else None,
        details,
    )


def _source_revision(package_file: Path) -> str | None:
    for candidate in package_file.parents:
        if not (candidate / ".git").exists():
            continue
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=candidate,
                check=True,
                capture_output=True,
                text=True,
                timeout=2.0,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return result.stdout.strip() or None
    return None


def _source_dirty(package_file: Path) -> bool | None:
    for candidate in package_file.parents:
        if not (candidate / ".git").exists():
            continue
        try:
            result = subprocess.run(
                ["git", "diff-index", "--quiet", "HEAD", "--"],
                cwd=candidate,
                check=False,
                capture_output=True,
                text=True,
                timeout=2.0,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode == 0:
            return False
        if result.returncode == 1:
            return True
        return None
    return None


def _summary_dict(summary: TimingSummary) -> dict[str, int | float]:
    return asdict(summary)


def run_benchmarks(config: BenchmarkConfig) -> dict[str, Any]:
    benchmarks: dict[str, dict[str, int | float]] = {}
    details: dict[str, Any] = {}
    package_file = Path(arch_rogue.__file__).resolve()
    with tempfile.TemporaryDirectory(prefix="arch-rogue-first-pass-") as temp_name:
        game = _prepare_game(config, Path(temp_name))
        default_zoom = float(game.view_zoom)

        benchmarks["game_update_45_enemies"] = _summary_dict(
            _benchmark_update(game, 45, config)
        )
        benchmarks["game_update_90_enemies"] = _summary_dict(
            _benchmark_update(game, 90, config)
        )

        positions = _configure_crowd(game, 45)
        _reset_crowd(game, positions)
        _set_playing_overlay(game)
        benchmarks["render_crowd_default_zoom"] = _summary_dict(
            _benchmark_draw_state(game, config)
        )

        if config.include_ui:
            _set_playing_overlay(game, inventory=True)
            benchmarks["render_inventory_paused"] = _summary_dict(
                _benchmark_draw_state(
                    game,
                    config,
                    warmup=max(1, config.warmup),
                    samples=config.ui_samples,
                )
            )

            _set_playing_overlay(game, character=True)
            benchmarks["render_disciplines_paused"] = _summary_dict(
                _benchmark_draw_state(
                    game,
                    config,
                    warmup=max(1, config.warmup),
                    samples=config.ui_samples,
                )
            )

            game.inventory_open = False
            game.character_menu_open = False
            game.state = "about"
            game.licenses_scroll = 0
            _reset_render_retention(game)
            benchmarks["render_about_opaque"] = _summary_dict(
                _benchmark_draw_state(
                    game,
                    config,
                    warmup=max(1, config.warmup),
                    samples=config.ui_samples,
                )
            )

        forced_save, payload_bytes = _benchmark_forced_save(game, config)
        benchmarks["forced_save"] = _summary_dict(forced_save)
        details["save_checkpoint"] = {
            "payload_bytes": payload_bytes,
            "mode": "compact"
            if callable(getattr(game, "request_run_checkpoint", None))
            else "indented",
        }
        benchmarks["routine_kill"] = _summary_dict(
            _benchmark_routine_kill(game, config)
        )

        features = {
            "deferred_kill_checkpoint": callable(
                getattr(game, "request_run_checkpoint", None)
            ),
            "paused_scene_retention": hasattr(game, "_paused_scene_cache"),
            "static_menu_retention": hasattr(game, "_static_menu_last_signature"),
        }
        if config.include_music:
            for kind in ("run", "menu"):
                call, ready, music_details = _benchmark_music_kind(kind, config)
                if call is not None:
                    benchmarks[f"music_{kind}_sync_call"] = _summary_dict(call)
                if ready is not None:
                    benchmarks[f"music_{kind}_ready"] = _summary_dict(ready)
                details[f"music_{kind}"] = music_details
            features["background_music_generation"] = any(
                entry.get("mode") == "background"
                for key, entry in details.items()
                if key.startswith("music_")
            )

        audio_shutdown = getattr(game.audio, "shutdown", None)
        if callable(audio_shutdown):
            audio_shutdown()

    return {
        "schema_version": 1,
        "source": {
            "package_file": str(package_file),
            "version": getattr(arch_rogue, "__version__", ""),
            "revision": _source_revision(package_file),
            "dirty": _source_dirty(package_file),
        },
        "runtime": {
            "python": platform.python_version(),
            "pygame_ce": pygame.version.ver,
            "sdl": ".".join(str(part) for part in pygame.get_sdl_version()),
            "platform": platform.platform(),
            "video_driver": pygame.display.get_driver(),
        },
        "config": asdict(config),
        "scenario": {
            "fixed_dt_seconds": FIXED_DT,
            "default_zoom": default_zoom,
            "lighting": True,
            "enemy_counts": [45, 90],
        },
        "features": features,
        "benchmarks": benchmarks,
        "details": details,
    }


def _print_text(result: dict[str, Any]) -> None:
    source = result["source"]
    config = result["config"]
    scenario = result["scenario"]
    print("Arch Rogue first-pass benchmark")
    print(
        f"source={source['package_file']} version={source['version']} "
        f"revision={source['revision'] or 'unknown'} dirty={source['dirty']}"
    )
    print(
        f"resolution={config['width']}x{config['height']} "
        f"depth={config['depth']} zoom={scenario['default_zoom']:.2f} "
        f"warmup={config['warmup']}"
    )
    print(
        f"{'metric':34} {'p50 ms':>9} {'p95 ms':>9} "
        f"{'mean ms':>9} {'n':>5}"
    )
    for name, summary in result["benchmarks"].items():
        print(
            f"{name:34} {summary['p50_ms']:9.3f} "
            f"{summary['p95_ms']:9.3f} {summary['mean_ms']:9.3f} "
            f"{summary['samples']:5d}"
        )
    for name, detail in result["details"].items():
        print(
            f"{name}: mode={detail['mode']} completed="
            f"{detail['completed_samples']}/{detail['requested_samples']} "
            f"timeouts={detail['timeouts']} unavailable={detail['mixer_unavailable']}"
        )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    config = _resolved_config(args)
    try:
        result = run_benchmarks(config)
        rendered = json.dumps(result, indent=2, sort_keys=True)
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
        if not args.json_only:
            _print_text(result)
        if not args.text_only:
            if not args.json_only:
                print("\nJSON")
            print(rendered)
        return 0
    finally:
        pygame.quit()


if __name__ == "__main__":
    raise SystemExit(main())
