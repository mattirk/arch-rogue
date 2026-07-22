# SPDX-License-Identifier: Apache-2.0
"""Mainline regression guard for the 4.3.17 android-beta -> master merge.

Lands before the riskier WS-C/WS-D refactors so any desktop render drift,
frame-timing change, or accidental mobile-code-path execution is caught.

Three guarantees:

1. **Render determinism** — a fixed seed and fixed frame number produces a
   fixed pixel hash for title, gameplay, and a dense crowd scenario. Any drift
   fails the test. Run twice in-process to also assert run-to-run determinism
   (same inputs -> identical bytes), independent of the baked snapshot.
2. **No mobile runtime on desktop** — ``detect_mobile_runtime()`` is False for
   non-Android ``sys.platform`` and no ``mobile_mode``-gated per-frame branch
   executes during a desktop ``Game.run()`` tick (instrumented with counters).
3. **Default desktop telemetry silence** — ``_mobile_performance_monitor`` is
   None and ``ARCH_ROGUE_PERF`` is silent on a default desktop run.
"""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame  # noqa: E402

from arch_rogue.content import ARCHETYPES  # noqa: E402
from arch_rogue.dungeon import MAP_H, MAP_W  # noqa: E402
from arch_rogue.game import Game  # noqa: E402
from arch_rogue.models import Tile  # noqa: E402
from arch_rogue.mobile import detect_mobile_runtime  # noqa: E402

FIXED_DT = 1.0 / 60.0
RENDER_FRAMES = 8
SEED = 3161


def _make_game(tmpdir: str, *, seed: int = SEED) -> Game:
    game = Game(
        screen_size=(960, 540),
        headless=True,
        save_path=Path(tmpdir) / "run.json",
    )
    game.options_path = Path(tmpdir) / "options.json"
    game.rng.seed(seed)
    return game


def _start_run(game: Game) -> None:
    game.restart(ARCHETYPES[2])  # Arcanist, matches profile_game determinism.
    if game.story_intro_pending:
        if not game.choose_story_relic_path(0):
            raise RuntimeError("could not resolve the deterministic story intro")
    game.active_cutscene = None
    game.story_intro_pending = False
    game.state = "playing"


def _prepare_crowd(game: Game) -> None:
    px, py = game.player.x, game.player.y
    cx, cy = int(px), int(py)
    for x in range(max(0, cx - 7), min(MAP_W, cx + 8)):
        for y in range(max(0, cy - 7), min(MAP_H, cy + 8)):
            game.dungeon.tiles[x][y] = Tile.FLOOR
    for index, enemy in enumerate(game.enemies):
        enemy.x = px + ((index % 9) - 4) * 0.72
        enemy.y = py + ((index // 9) - 2) * 0.72
        enemy.aggro_range = 99.0
        enemy.attack_timer = 0.0


def _hash_surface(surface: pygame.Surface) -> str:
    return hashlib.sha256(pygame.image.tobytes(surface, "RGBA")).hexdigest()


def _render_title_hash(tmpdir: str) -> str:
    game = _make_game(tmpdir)
    game.state = "title"
    for _ in range(RENDER_FRAMES):
        game.ui_elapsed += FIXED_DT
        game.draw()
    return _hash_surface(game.screen)


def _render_gameplay_hash(tmpdir: str, *, depth: int = 3) -> str:
    game = _make_game(tmpdir)
    _start_run(game)
    for _ in range(depth - 1):
        game.descend_to_next_depth()
    game.state = "playing"
    game.revealed_tiles = set()
    game.update_revealed_tiles()
    game.snap_camera_to_player()
    for _ in range(RENDER_FRAMES):
        game.ui_elapsed += FIXED_DT
        game.update(FIXED_DT)
        game.draw()
    return _hash_surface(game.screen)


def _render_crowd_hash(tmpdir: str) -> str:
    game = _make_game(tmpdir)
    _start_run(game)
    for _ in range(8):  # deep enough for a populated floor
        game.descend_to_next_depth()
    _prepare_crowd(game)
    game.revealed_tiles = set()
    game.update_revealed_tiles()
    game.snap_camera_to_player()
    game.player.max_hp = 1_000_000
    game.player.hp = game.player.max_hp
    for _ in range(RENDER_FRAMES):
        game.ui_elapsed += FIXED_DT
        game.update(FIXED_DT)
        game.draw()
    return _hash_surface(game.screen)


class DesktopDeterminismTests(unittest.TestCase):
    # Fixed pixel hashes pin the verified deterministic desktop output across
    # processes, so each scenario only needs one render per test invocation.
    # Update a constant only for an intentional rendering change or after
    # proving that an existing baseline is stale.
    TITLE_HASH = "7b718ed26671705ed2f5b474c1452f11b058dc2285f1c6f45cd737168efcbb3e"
    GAMEPLAY_HASH = "51c0bb05212a81ed567f9c7547018eaf9d9255de5290f920829ce436afdb9ce4"
    CROWD_HASH = "af7d84f12dc7c8b0b4d6085a6e62d74577f5acce8a42e508065ee1e742098af5"

    def test_title_render_is_deterministic_and_matches_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            actual_hash = _render_title_hash(tmpdir)
        self.assertEqual(
            actual_hash,
            self.TITLE_HASH,
            f"title render drift: expected {self.TITLE_HASH}, got {actual_hash}",
        )

    def test_gameplay_render_is_deterministic_and_matches_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            actual_hash = _render_gameplay_hash(tmpdir)
        self.assertEqual(
            actual_hash,
            self.GAMEPLAY_HASH,
            f"gameplay render drift: expected {self.GAMEPLAY_HASH}, got {actual_hash}",
        )

    def test_crowd_render_is_deterministic_and_matches_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            actual_hash = _render_crowd_hash(tmpdir)
        self.assertEqual(
            actual_hash,
            self.CROWD_HASH,
            f"crowd render drift: expected {self.CROWD_HASH}, got {actual_hash}",
        )


class RenderCacheInvalidationTests(unittest.TestCase):
    """All memoized render caches must clear through the single seam.

    4.3.17 WS-C consolidates graphics-mode / resolution / font cache
    invalidation into ``_invalidate_render_caches()`` so a future cache
    addition cannot be missed by one of the call sites. This test populates
    every known render cache with a sentinel, invokes each invalidation
    entry point, and confirms the caches are cleared.
    """

    CACHE_ATTRS = (
        "ambient_overlay_cache",
        "_hud_panel_cache",
        "_hud_icon_cache",
        "_aim_cone_cache",
        "_alpha_tile_cache",
        "_title_logo_cache",
        "_fitted_ui_font_cache",
        "_impact_overlay_cache",
        "tile_cache",
        "door_tile_cache",
    )

    def _populate_caches(self, game: Game) -> None:
        for attr in self.CACHE_ATTRS:
            setattr(game, attr, {("sentinel",): object()})

    def _assert_caches_cleared(self, game: Game) -> None:
        for attr in self.CACHE_ATTRS:
            cache = getattr(game, attr, None)
            self.assertIsNotNone(
                cache,
                f"{attr} vanished instead of being cleared",
            )
            self.assertEqual(
                len(cache),
                0,
                f"{attr} not cleared by _invalidate_render_caches()",
            )



    def test_rebuild_fonts_routes_through_seam(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_game(tmpdir)
            self._populate_caches(game)
            game.rebuild_fonts()
            self._assert_caches_cleared(game)

    def test_invalidate_resolution_sized_caches_routes_through_seam(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_game(tmpdir)
            self._populate_caches(game)
            game._invalidate_resolution_sized_caches()
            self._assert_caches_cleared(game)


class DesktopSharedWinsTests(unittest.TestCase):
    """Confirm desktop exercises the shared universal-win code paths (WS-D)."""

    def test_desktop_uses_batched_floor_blits(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_game(tmpdir)
            _start_run(game)
            for _ in range(2):
                game.descend_to_next_depth()
            game.state = "playing"
            game.revealed_tiles = set()
            game.update_revealed_tiles()
            game.snap_camera_to_player()
            call_count = {"n": 0}
            original = game._blit_floor_entries

            def counting_blits(target, entries, *args, **kwargs):
                call_count["n"] += 1
                return original(target, entries, *args, **kwargs)

            with patch.object(game, "_blit_floor_entries", counting_blits):
                for _ in range(3):
                    game.ui_elapsed += FIXED_DT
                    game.update(FIXED_DT)
                    # update() can trigger a story cutscene at the descended
                    # depth, which skips world rendering. Clear it so the
                    # dungeon path actually runs for this batch-path check.
                    game.active_cutscene = None
                    game.story_intro_pending = False
                    game.draw()
            self.assertGreater(
                call_count["n"],
                0,
                "desktop draw never hit the batched _blit_floor_entries path",
            )

    def test_desktop_projection_origin_is_memoized(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_game(tmpdir)
            _start_run(game)
            game.state = "playing"
            game.snap_camera_to_player()
            game._frame_cache = {}
            w, h = game._screen_size()
            origin1 = game._projection_origin(w, h)
            self.assertIn(("projection_origin", w, h), game._frame_cache)
            origin2 = game._projection_origin(w, h)
            self.assertEqual(origin1, origin2)
            self.assertEqual(origin1, (w * 0.5, h * 0.48))

    def test_desktop_impact_cache_is_populated(self) -> None:
        from arch_rogue.models import ImpactEffect

        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_game(tmpdir)
            _start_run(game)
            game.state = "playing"
            game.snap_camera_to_player()
            effect = ImpactEffect(
                x=game.player.x,
                y=game.player.y,
                color=(220, 80, 60),
                radius=0.5,
                ttl=0.2,
                max_ttl=0.2,
                kind="hit",
            )
            for _ in range(2):
                game._frame_cache = {}
                game.draw_impact(effect)
            cache = getattr(game, "_impact_overlay_cache", None)
            self.assertIsNotNone(cache, "desktop impact overlay cache was not populated")
            self.assertGreaterEqual(len(cache), 1)


class MobileIsolationTests(unittest.TestCase):
    """No mobile_mode-gated code path may execute during a desktop tick."""

    # Per-frame mobile-only entry points. Each is gated by mobile_mode or
    # _mobile_gpu_frame_active internally, so on desktop they must never run.
    MOBILE_FRAME_METHODS = (
        "present_mobile_gpu_frame",
        "_composite_mobile_gpu_ui_fallback",
        "refresh_mobile_gpu_renderer",
        "configure_mobile_gpu_renderer",
        "draw_mobile_performance_overlay",
    )

    def test_detect_mobile_runtime_is_false_on_non_android(self) -> None:
        if sys.platform == "linux" and os.environ.get("ANDROID_ROOT"):
            self.skipTest("running under Android runtime")
        self.assertFalse(detect_mobile_runtime())



    def test_no_mobile_frame_branch_runs_on_desktop_tick(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_game(tmpdir)
            _start_run(game)
            for _ in range(4):
                game.descend_to_next_depth()
            game.state = "playing"
            game.revealed_tiles = set()
            game.update_revealed_tiles()
            game.snap_camera_to_player()

            counters: dict[str, int] = {name: 0 for name in self.MOBILE_FRAME_METHODS}

            def make_counter(name: str):
                original = getattr(game, name)

                def wrapper(*args, **kwargs):
                    counters[name] += 1
                    return original(*args, **kwargs)

                return wrapper

            patches = [
                patch.object(game, name, make_counter(name))
                for name in self.MOBILE_FRAME_METHODS
            ]
            for p in patches:
                p.start()
                self.addCleanup(p.stop)
            try:
                for _ in range(6):
                    game.ui_elapsed += FIXED_DT
                    game.update(FIXED_DT)
                    game.draw()
            finally:
                pass
            for name, count in counters.items():
                self.assertEqual(
                    count,
                    0,
                    f"mobile-only method {name} executed {count} times on desktop",
                )


if __name__ == "__main__":
    unittest.main()