# SPDX-License-Identifier: Apache-2.0
"""Tests for the 4.3.17 FramePacing consolidation and frame_rate_cap option."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame  # noqa: E402

from arch_rogue.constants import (  # noqa: E402
    DEFAULT_FRAME_RATE,
    FRAME_RATE_CAP_DEFAULT,
    FRAME_RATE_CAP_VALUES,
    FPS,
    normalize_frame_rate_cap,
)
from arch_rogue.content import ARCHETYPES  # noqa: E402
from arch_rogue.game import FramePacing, Game  # noqa: E402


def make_game(tmpdir: str) -> Game:
    game = Game(
        screen_size=(820, 540),
        headless=True,
        save_path=Path(tmpdir) / "run.json",
    )
    game.options_path = Path(tmpdir) / "options.json"
    game.meta_progress = game.default_meta_progress()
    game.run_history = []
    game.rng.seed(2323)
    game.restart(ARCHETYPES[0])
    return game


class FramePacingUnitTests(unittest.TestCase):
    def test_default_frame_rate_constant_matches_legacy_fps(self) -> None:
        self.assertEqual(DEFAULT_FRAME_RATE, 60)
        self.assertEqual(FPS, DEFAULT_FRAME_RATE)

    def test_frame_rate_cap_values_order(self) -> None:
        self.assertEqual(FRAME_RATE_CAP_VALUES, (30, 60, 90, 120, "Unlimited"))
        self.assertEqual(FRAME_RATE_CAP_DEFAULT, 60)

    def test_normalize_frame_rate_cap(self) -> None:
        self.assertEqual(normalize_frame_rate_cap(30), 30)
        self.assertEqual(normalize_frame_rate_cap("120"), 120)
        self.assertEqual(normalize_frame_rate_cap("Unlimited"), "Unlimited")
        self.assertEqual(normalize_frame_rate_cap("unlimited"), "Unlimited")
        self.assertEqual(normalize_frame_rate_cap(None), 60)
        self.assertEqual(normalize_frame_rate_cap(144), 60)
        self.assertEqual(normalize_frame_rate_cap("garbage"), 60)

    def test_frame_pacing_default_targets_60(self) -> None:
        clock = pygame.time.Clock()
        pacing = FramePacing(clock)
        self.assertEqual(pacing.target_fps, 60)
        self.assertEqual(pacing.suspended_fps, 10)
        self.assertFalse(pacing.vsync)

    def test_set_frame_rate_cap_resolves_target(self) -> None:
        clock = pygame.time.Clock()
        pacing = FramePacing(clock)
        pacing.set_frame_rate_cap(120)
        self.assertEqual(pacing.target_fps, 120)
        self.assertEqual(pacing.frame_rate_cap, 120)
        pacing.set_frame_rate_cap("Unlimited")
        self.assertEqual(pacing.target_fps, 0)
        self.assertEqual(pacing.frame_rate_cap, "Unlimited")
        pacing.set_frame_rate_cap(30)
        self.assertEqual(pacing.target_fps, 30)

    def test_tick_uses_suspended_fps_when_suspended(self) -> None:
        clock = MagicMock()
        clock.tick.return_value = 100  # 0.1s -> clamped to 0.05
        pacing = FramePacing(clock)
        pacing.set_frame_rate_cap(120)
        dt = pacing.tick(suspended=True)
        # Suspended overrides the 120 cap to the 10 Hz throttle.
        clock.tick.assert_called_once_with(10)
        self.assertAlmostEqual(dt, 0.05)

    def test_tick_uses_target_fps_when_active(self) -> None:
        clock = MagicMock()
        clock.tick.return_value = 16
        pacing = FramePacing(clock)
        pacing.set_frame_rate_cap(90)
        dt = pacing.tick(suspended=False)
        clock.tick.assert_called_once_with(90)
        self.assertAlmostEqual(dt, 0.016)

    def test_tick_unlimited_calls_with_zero(self) -> None:
        clock = MagicMock()
        clock.tick.return_value = 5
        pacing = FramePacing(clock)
        pacing.set_frame_rate_cap("Unlimited")
        pacing.tick(suspended=False)
        clock.tick.assert_called_once_with(0)


class FrameRateOptionTests(unittest.TestCase):
    def test_normal_startup_applies_cap_loaded_before_clock_exists(self) -> None:
        # Game loads options before constructing FramePacing so display mode can
        # honor persisted settings. The newly created pacing object must then
        # inherit that already-loaded value instead of silently resetting to 60.
        def load_persisted_cap(game: Game) -> bool:
            game.frame_rate_cap = 120
            return True

        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "arch_rogue.game.OptionsMixin.load_options",
            load_persisted_cap,
        ):
            game = Game(
                screen_size=(820, 540),
                headless=False,
                save_path=Path(tmpdir) / "run.json",
            )
            self.assertEqual(game.frame_rate_cap, 120)
            self.assertEqual(game.frame_pacing.target_fps, 120)

    def test_default_options_serialize_schema_8_with_cap_and_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            self.assertTrue(game.save_options())
            data = json.loads(game.options_path.read_text(encoding="utf-8"))
            self.assertEqual(data["schema_version"], 8)
            self.assertEqual(data["frame_rate_cap"], 60)
            self.assertFalse(data["show_perf_overlay"])

    def test_cycle_frame_rate_cap_advances_and_persists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            self.assertEqual(game.frame_rate_cap, 60)
            self.assertTrue(game.cycle_frame_rate_cap(forward=True))
            self.assertEqual(game.frame_rate_cap, 90)
            self.assertEqual(game.frame_pacing.target_fps, 90)
            # Cycle wraps through Unlimited back to 30.
            game.cycle_frame_rate_cap(forward=True)  # -> 120
            game.cycle_frame_rate_cap(forward=True)  # -> Unlimited
            self.assertEqual(game.frame_rate_cap, "Unlimited")
            self.assertEqual(game.frame_pacing.target_fps, 0)
            game.cycle_frame_rate_cap(forward=True)  # -> 30
            self.assertEqual(game.frame_rate_cap, 30)
            data = json.loads(game.options_path.read_text(encoding="utf-8"))
            self.assertEqual(data["frame_rate_cap"], 30)

    def test_cycle_frame_rate_cap_reverse(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.cycle_frame_rate_cap(forward=False)
            self.assertEqual(game.frame_rate_cap, 30)

    def test_old_schema_v6_options_migrate_to_default_cap_and_overlay_off(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            legacy = {
                "version": 1,
                "schema_version": 6,
                "audio_enabled": True,
                "music_enabled": False,
                "fullscreen": False,
                "ui_scale": 1,
                "ui_scale_auto": True,
                "difficulty": "Medium",
                "hell_unlocked": False,
                "meta_progress": game.default_meta_progress(),
                "run_history": [],
                "controller_enabled": True,
                "last_controller_guid": "",
                "lighting_enabled": True,
                "lighting_normal_maps": True,
                "legacy_graphics": False,
            }
            game.options_path.write_text(json.dumps(legacy), encoding="utf-8")
            self.assertTrue(game.load_options())
            self.assertEqual(game.frame_rate_cap, 60)
            self.assertEqual(game.frame_pacing.target_fps, 60)
            self.assertFalse(game.show_perf_overlay)

    def test_persisted_unlimited_cap_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.frame_rate_cap = "Unlimited"
            game.frame_pacing.set_frame_rate_cap("Unlimited")
            self.assertTrue(game.save_options())
            # Construct a fresh game without restart() so its save_options()
            # (called from restart -> record_run_start_meta) does not clobber
            # the file before we read it back.
            reloaded = Game(
                screen_size=(820, 540),
                headless=True,
                save_path=Path(tmpdir) / "run.json",
            )
            reloaded.options_path = Path(tmpdir) / "options.json"
            self.assertTrue(reloaded.load_options())
            self.assertEqual(reloaded.frame_rate_cap, "Unlimited")
            self.assertEqual(reloaded.frame_pacing.target_fps, 0)

    def test_toggle_perf_overlay_persists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            self.assertFalse(game.show_perf_overlay)
            self.assertTrue(game.toggle_perf_overlay())
            self.assertTrue(game.show_perf_overlay)
            data = json.loads(game.options_path.read_text(encoding="utf-8"))
            self.assertTrue(data["show_perf_overlay"])


class OptionsRowCountTests(unittest.TestCase):
    """Row count is platform-dependent (desktop gets the perf-overlay row)."""

    def test_desktop_row_count_includes_perf_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            self.assertFalse(game.mobile_mode)
            self.assertEqual(game.OPTIONS_ROW_COUNT, 15)
            self.assertEqual(game.OPTIONS_ROW_BACK, 14)
            self.assertEqual(game.OPTIONS_ROW_FRAME_RATE, 4)
            self.assertEqual(game.OPTIONS_ROW_MP_HOST, 11)
            self.assertEqual(game.OPTIONS_ROW_MP_PORT, 12)
            self.assertEqual(game.OPTIONS_ROW_PERF_OVERLAY, 13)

    def test_mobile_row_count_omits_perf_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = Game(
                screen_size=(1280, 720),
                headless=True,
                save_path=Path(tmpdir) / "run.json",
                mobile=True,
            )
            game.options_path = Path(tmpdir) / "options.json"
            self.assertTrue(game.mobile_mode)
            self.assertEqual(game.OPTIONS_ROW_COUNT, 14)
            self.assertEqual(game.OPTIONS_ROW_BACK, 13)


class PerfOverlayTests(unittest.TestCase):
    """WS-E: desktop perf overlay defaults off, opt-in via show_perf_overlay."""

    def test_default_desktop_has_no_performance_monitor(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            self.assertFalse(game.mobile_mode)
            self.assertFalse(game.show_perf_overlay)
            self.assertIsNone(game._mobile_performance_monitor)



    def test_toggle_perf_overlay_round_trips_and_reconciles(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            self.assertTrue(game.toggle_perf_overlay())
            self.assertTrue(game.show_perf_overlay)
            self.assertIsNotNone(game._mobile_performance_monitor)
            self.assertFalse(game.toggle_perf_overlay())
            self.assertFalse(game.show_perf_overlay)
            self.assertIsNone(game._mobile_performance_monitor)


if __name__ == "__main__":
    unittest.main()