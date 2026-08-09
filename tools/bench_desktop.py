# SPDX-License-Identifier: Apache-2.0
"""Unprofiled wall-clock desktop frame benchmark for A/B optimization runs.

Reuses tools/profile_game.py scenario preparation but records per-frame
update/draw wall times without cProfile distortion. Prints p50/p95/mean and
a JSON line for machine comparison.

    .venv_host/bin/python tools/bench_desktop.py --width 2560 --height 1440 \
        --zoom 0.81536 --frames 600 --warmup 300
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pygame

from profile_game import FIXED_DT, prepare_game, prepare_profile_frame


def percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, int(round(pct / 100.0 * (len(ordered) - 1)))))
    return ordered[index]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=("quiet", "crowd", "action-effects"), default="crowd")
    parser.add_argument("--frames", type=int, default=600)
    parser.add_argument("--warmup", type=int, default=300)
    parser.add_argument("--seed", type=int, default=3161)
    parser.add_argument("--depth", type=int, default=10)
    parser.add_argument("--width", type=int, default=2560)
    parser.add_argument("--height", type=int, default=1440)
    parser.add_argument("--zoom", type=float, default=0.81536)
    parser.add_argument("--graphics-tier", default="hd")
    parser.add_argument("--mobile", action="store_true")
    parser.add_argument("--mobile-quality", default="performance")
    parser.add_argument("--no-lighting", action="store_true")
    parser.add_argument("--label", default="")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="arch-rogue-bench-") as temp_name:
        game = prepare_game(args, Path(temp_name))
        for frame_index in range(args.warmup):
            prepare_profile_frame(game, frame_index)
            game.ui_elapsed += FIXED_DT
            game.update(FIXED_DT)
            game.draw()

        update_ms: list[float] = []
        draw_ms: list[float] = []
        for frame_index in range(args.frames):
            prepare_profile_frame(game, args.warmup + frame_index)
            game.ui_elapsed += FIXED_DT
            started = time.perf_counter()
            game.update(FIXED_DT)
            update_ms.append((time.perf_counter() - started) * 1000.0)
            started = time.perf_counter()
            game.draw()
            draw_ms.append((time.perf_counter() - started) * 1000.0)

        combined = [u + d for u, d in zip(update_ms, draw_ms)]
        result = {
            "label": args.label,
            "scenario": args.scenario,
            "size": [args.width, args.height],
            "zoom": args.zoom,
            "graphics_tier": args.graphics_tier,
            "enemies": len(game.enemies),
            "frames": args.frames,
            "update_p50": round(statistics.median(update_ms), 3),
            "update_p95": round(percentile(update_ms, 95), 3),
            "draw_p50": round(statistics.median(draw_ms), 3),
            "draw_p95": round(percentile(draw_ms, 95), 3),
            "combined_p50": round(statistics.median(combined), 3),
            "combined_p95": round(percentile(combined, 95), 3),
            "combined_mean": round(statistics.fmean(combined), 3),
        }
        print(
            f"[{args.label or args.scenario}] {args.width}x{args.height} zoom={args.zoom} "
            f"tier={args.graphics_tier} enemies={result['enemies']}\n"
            f"  update p50={result['update_p50']} p95={result['update_p95']} ms\n"
            f"  draw   p50={result['draw_p50']} p95={result['draw_p95']} ms\n"
            f"  total  p50={result['combined_p50']} p95={result['combined_p95']} "
            f"mean={result['combined_mean']} ms "
            f"(~{1000.0 / max(0.001, result['combined_p50']):.1f} FPS CPU ceiling)"
        )
        print("JSON: " + json.dumps(result))
    pygame.quit()


if __name__ == "__main__":
    main()
