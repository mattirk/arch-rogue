from __future__ import annotations

import json
import math
import os
import sys
import tempfile
import unittest
import warnings
from collections import OrderedDict
from pathlib import Path
from unittest.mock import call, patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame

import arch_rogue.mobile as mobile_runtime
from arch_rogue.constants import DUNGEON_DEPTH, TILE_H, TILE_W
from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game
from arch_rogue.input import Command
from arch_rogue.mobile import (
    MobilePerformanceMonitor,
    SafeInsets,
    build_mobile_layout,
    detect_mobile_runtime,
    optimize_immutable_alpha_surface,
)
from arch_rogue.models import LightSource, StoryGuest, Tile
from arch_rogue.options import (
    MOBILE_RENDER_QUALITY_BALANCED,
    MOBILE_RENDER_QUALITY_HEIGHT_CAPS,
    MOBILE_RENDER_QUALITY_MODES,
    MOBILE_RENDER_QUALITY_NATIVE,
    MOBILE_RENDER_QUALITY_PERFORMANCE,
    default_mobile_render_quality,
    mobile_logical_resolution,
    mobile_render_quality_label,
    next_mobile_render_quality,
)


def make_mobile_game(
    tmpdir: str,
    size: tuple[int, int] = (1280, 720),
    insets: tuple[int, int, int, int] = (0, 0, 0, 0),
) -> Game:
    game = Game(
        screen_size=size,
        headless=True,
        save_path=Path(tmpdir) / "run.json",
        mobile=True,
        safe_insets=insets,
    )
    game.options_path = Path(tmpdir) / "options.json"
    game.rng.seed(2026)
    game.restart(ARCHETYPES[2])
    if game.story_intro_pending:
        game.choose_story_relic_path(0)
    game.active_cutscene = None
    return game


class MobileRenderQualityTests(unittest.TestCase):
    def test_quality_modes_cap_height_without_upscaling_or_aspect_change(self) -> None:
        self.assertEqual(
            MOBILE_RENDER_QUALITY_MODES,
            ("performance", "balanced", "native"),
        )
        self.assertEqual(
            MOBILE_RENDER_QUALITY_HEIGHT_CAPS,
            {"performance": 540, "balanced": 720, "native": None},
        )
        cases = (
            ((2340, 1080), MOBILE_RENDER_QUALITY_PERFORMANCE, (1170, 540)),
            ((2340, 1080), MOBILE_RENDER_QUALITY_BALANCED, (1560, 720)),
            ((2340, 1080), MOBILE_RENDER_QUALITY_NATIVE, (2340, 1080)),
            ((2560, 1600), MOBILE_RENDER_QUALITY_BALANCED, (1152, 720)),
            ((800, 480), MOBILE_RENDER_QUALITY_PERFORMANCE, (800, 480)),
            ((1280, 720), MOBILE_RENDER_QUALITY_BALANCED, (1280, 720)),
        )
        for physical, quality, expected in cases:
            with self.subTest(physical=physical, quality=quality):
                logical = mobile_logical_resolution(physical, quality)
                self.assertEqual(logical, expected)
                self.assertLessEqual(logical[0], physical[0])
                self.assertLessEqual(logical[1], physical[1])
                self.assertAlmostEqual(
                    logical[0] / logical[1],
                    physical[0] / physical[1],
                    places=3,
                )

    def test_quality_defaults_labels_and_cycle_order(self) -> None:
        self.assertEqual(
            default_mobile_render_quality(True),
            MOBILE_RENDER_QUALITY_PERFORMANCE,
        )
        self.assertEqual(
            default_mobile_render_quality(False),
            MOBILE_RENDER_QUALITY_NATIVE,
        )
        self.assertEqual(
            mobile_render_quality_label(MOBILE_RENDER_QUALITY_PERFORMANCE),
            "Performance · 540p cap",
        )
        self.assertEqual(
            next_mobile_render_quality(MOBILE_RENDER_QUALITY_PERFORMANCE),
            MOBILE_RENDER_QUALITY_BALANCED,
        )
        self.assertEqual(
            next_mobile_render_quality(MOBILE_RENDER_QUALITY_PERFORMANCE, False),
            MOBILE_RENDER_QUALITY_NATIVE,
        )

    def test_fresh_platform_defaults_and_mobile_scaler_hint(self) -> None:
        previous_hint = os.environ.get("SDL_RENDER_SCALE_QUALITY")
        try:
            os.environ["SDL_RENDER_SCALE_QUALITY"] = "1"
            with tempfile.TemporaryDirectory() as tmpdir:
                mobile = Game(
                    screen_size=(1280, 720),
                    headless=True,
                    save_path=Path(tmpdir) / "mobile-run.json",
                    mobile=True,
                )
                desktop = Game(
                    screen_size=(820, 540),
                    headless=True,
                    save_path=Path(tmpdir) / "desktop-run.json",
                    mobile=False,
                )
            self.assertEqual(
                mobile.mobile_render_quality,
                MOBILE_RENDER_QUALITY_PERFORMANCE,
            )
            self.assertFalse(mobile._lighting_normal_maps)
            self.assertEqual(
                desktop.mobile_render_quality,
                MOBILE_RENDER_QUALITY_NATIVE,
            )
            self.assertTrue(desktop._lighting_normal_maps)
            self.assertEqual(os.environ["SDL_RENDER_SCALE_QUALITY"], "0")
        finally:
            if previous_hint is None:
                os.environ.pop("SDL_RENDER_SCALE_QUALITY", None)
            else:
                os.environ["SDL_RENDER_SCALE_QUALITY"] = previous_hint

    def test_mobile_display_mode_uses_mocked_scaled_fullscreen_logical_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = Game(
                screen_size=(1280, 720),
                headless=True,
                save_path=Path(tmpdir) / "run.json",
                mobile=True,
            )
            game.mobile_render_quality = MOBILE_RENDER_QUALITY_BALANCED
            with (
                patch.object(game, "display_size", return_value=(1080, 2340)),
                patch(
                    "arch_rogue.options.pygame.display.set_mode",
                    return_value=game.screen,
                ) as set_mode,
            ):
                result = game.apply_display_mode()
            self.assertIs(result, game.screen)
            set_mode.assert_called_once_with(
                (1560, 720), pygame.FULLSCREEN | pygame.SCALED
            )

    def test_android_display_retries_with_second_accelerated_gles_driver(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = Game(
                screen_size=(1280, 720),
                headless=True,
                save_path=Path(tmpdir) / "run.json",
                mobile=True,
            )
            with (
                patch.dict(os.environ, {"SDL_RENDER_DRIVER": "opengles2"}),
                patch("arch_rogue.options.android_runtime_active", return_value=True),
                patch.object(game, "display_size", return_value=(2340, 1080)),
                patch(
                    "arch_rogue.options.pygame.display.set_mode",
                    side_effect=[pygame.error("gles2 failed"), game.screen],
                ) as set_mode,
                patch.object(game, "_reset_android_display_subsystem") as reset,
                patch.object(game, "_record_mobile_renderer") as record,
            ):
                result = game.apply_display_mode()
                self.assertEqual(os.environ["SDL_RENDER_DRIVER"], "opengles")

            self.assertIs(result, game.screen)
            self.assertEqual(
                set_mode.call_args_list,
                [
                    call((1170, 540), pygame.FULLSCREEN | pygame.SCALED),
                    call((1170, 540), pygame.FULLSCREEN | pygame.SCALED),
                ],
            )
            reset.assert_called_once_with()
            record.assert_called_once_with(
                game.screen,
                name="opengles",
                accelerated=True,
                failures=["opengles2:error:gles2 failed"],
            )

    def test_android_display_marks_last_resort_software_renderer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = Game(
                screen_size=(1280, 720),
                headless=True,
                save_path=Path(tmpdir) / "run.json",
                mobile=True,
            )

            def slow_renderer(*_args: object, **_kwargs: object) -> pygame.Surface:
                warnings.warn("no fast renderer available", Warning, stacklevel=2)
                return game.screen

            with (
                patch.dict(os.environ, {"SDL_RENDER_DRIVER": "opengles2"}),
                patch("arch_rogue.options.android_runtime_active", return_value=True),
                patch.object(game, "display_size", return_value=(2340, 1080)),
                patch(
                    "arch_rogue.options.pygame.display.set_mode",
                    side_effect=slow_renderer,
                ) as set_mode,
                patch.object(game, "_reset_android_display_subsystem") as reset,
                patch.object(game, "_record_mobile_renderer") as record,
            ):
                result = game.apply_display_mode()
                self.assertNotIn("SDL_RENDER_DRIVER", os.environ)

            self.assertIs(result, game.screen)
            self.assertEqual(set_mode.call_count, 3)
            self.assertEqual(reset.call_count, 2)
            record.assert_called_once()
            self.assertEqual(record.call_args.kwargs["name"], "software")
            self.assertFalse(record.call_args.kwargs["accelerated"])
            self.assertEqual(len(record.call_args.kwargs["failures"]), 2)

    def test_mobile_quality_persists_and_old_options_migrate_safely(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = Game(
                screen_size=(1280, 720),
                headless=True,
                save_path=Path(tmpdir) / "run.json",
                mobile=True,
            )
            game.options_path = Path(tmpdir) / "options.json"
            game.mobile_render_quality = MOBILE_RENDER_QUALITY_BALANCED
            game._lighting_normal_maps = True
            self.assertTrue(game.save_options())
            saved = json.loads(game.options_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["schema_version"], 6)
            self.assertEqual(
                saved["mobile_render_quality"], MOBILE_RENDER_QUALITY_BALANCED
            )

            game.mobile_render_quality = MOBILE_RENDER_QUALITY_PERFORMANCE
            game._lighting_normal_maps = False
            self.assertTrue(game.load_options())
            self.assertEqual(
                game.mobile_render_quality, MOBILE_RENDER_QUALITY_BALANCED
            )
            self.assertTrue(game._lighting_normal_maps)

            game.options_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "schema_version": 5,
                        "lighting_normal_maps": True,
                    }
                ),
                encoding="utf-8",
            )
            game.mobile_render_quality = MOBILE_RENDER_QUALITY_NATIVE
            game._lighting_normal_maps = True
            self.assertTrue(game.load_options())
            self.assertEqual(
                game.mobile_render_quality,
                MOBILE_RENDER_QUALITY_PERFORMANCE,
            )
            self.assertFalse(game._lighting_normal_maps)

            game.options_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "schema_version": 6,
                        "mobile_render_quality": MOBILE_RENDER_QUALITY_NATIVE,
                        "lighting_normal_maps": True,
                    }
                ),
                encoding="utf-8",
            )
            self.assertTrue(game.load_options())
            self.assertEqual(game.mobile_render_quality, MOBILE_RENDER_QUALITY_NATIVE)
            self.assertTrue(game._lighting_normal_maps)

    def test_mobile_options_row_labels_and_activates_quality_without_real_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir)
            game.state = "options"
            game.options_cursor = game.OPTIONS_ROW_FULLSCREEN
            game.options_scroll = 0
            game.draw_options_menu()
            self.assertEqual(
                getattr(game, "_options_visible_rows")[0],
                ("F", "Render quality", "Performance · 540p cap"),
            )

            game._world_layer = pygame.Surface((8, 8))
            game.ambient_overlay_cache[(8, 8, "test", 1)] = pygame.Surface((8, 8))
            game._light_buffer_surface = pygame.Surface((8, 8))
            game._stage_surface_cache = {("test",): pygame.Surface((8, 8))}
            replacement_screen = pygame.Surface((1560, 720))
            with (
                patch.object(
                    game, "apply_display_mode", return_value=replacement_screen
                ) as apply_mode,
                patch.object(
                    game,
                    "refresh_mobile_safe_insets",
                    wraps=game.refresh_mobile_safe_insets,
                ) as refresh_insets,
                patch.object(
                    game, "mobile_layout", wraps=game.mobile_layout
                ) as refresh_layout,
                patch.object(
                    game,
                    "refresh_automatic_ui_scale",
                    wraps=game.refresh_automatic_ui_scale,
                ) as refresh_ui_scale,
                patch.object(
                    game,
                    "_invalidate_resolution_sized_caches",
                    wraps=game._invalidate_resolution_sized_caches,
                ) as clear_caches,
                patch.object(
                    game, "save_options", wraps=game.save_options
                ) as save_options,
            ):
                game._activate_options_row(game.OPTIONS_ROW_FULLSCREEN, True)

            self.assertEqual(
                game.mobile_render_quality, MOBILE_RENDER_QUALITY_BALANCED
            )
            self.assertIs(game.screen, replacement_screen)
            apply_mode.assert_called_once_with()
            refresh_insets.assert_called_once_with()
            refresh_layout.assert_called_once_with()
            refresh_ui_scale.assert_called_once_with()
            clear_caches.assert_called_once_with()
            save_options.assert_called_once_with()
            self.assertIsNone(game._world_layer)
            self.assertEqual(game.ambient_overlay_cache, {})
            self.assertIsNone(game._light_buffer_surface)
            self.assertEqual(game._stage_surface_cache, {})
            saved = json.loads(game.options_path.read_text(encoding="utf-8"))
            self.assertEqual(
                saved["mobile_render_quality"], MOBILE_RENDER_QUALITY_BALANCED
            )

    def test_mobile_f_shortcut_activates_reused_first_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir)
            game.state = "options"
            pygame.event.clear()
            with patch.object(game, "_activate_options_row") as activate:
                pygame.event.post(
                    pygame.event.Event(pygame.KEYDOWN, key=pygame.K_f, mod=0)
                )
                game.handle_events()
            activate.assert_called_once_with(game.OPTIONS_ROW_FULLSCREEN, True)
            self.assertEqual(game.options_cursor, game.OPTIONS_ROW_FULLSCREEN)

    def test_mobile_continuous_lighting_uses_quarter_resolution_below_native(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            viewport = game.mobile_world_viewport()
            for quality in (
                MOBILE_RENDER_QUALITY_PERFORMANCE,
                MOBILE_RENDER_QUALITY_BALANCED,
            ):
                with self.subTest(quality=quality):
                    game.mobile_render_quality = quality
                    game.reset_lighting_caches()
                    game.draw()
                    buffer = game._light_buffer_surface
                    self.assertIsNotNone(buffer)
                    assert buffer is not None
                    self.assertEqual(
                        buffer.get_size(),
                        (
                            max(1, viewport.width // 4),
                            max(1, viewport.height // 4),
                        ),
                    )
                    scratch = game._light_scratch_surface
                    self.assertIsNotNone(scratch)
                    assert scratch is not None
                    self.assertEqual(scratch.get_masks()[:3], game.screen.get_masks()[:3])

            game.mobile_render_quality = MOBILE_RENDER_QUALITY_NATIVE
            game.reset_lighting_caches()
            game.draw()
            self.assertTrue(game.mobile_lightweight_lighting_active())
            self.assertFalse(game.continuous_lighting_active())
            self.assertIsNone(game._light_buffer_surface)
            self.assertIsNone(game._light_scratch_surface)

    def test_accelerated_native_mobile_uses_quarter_resolution_gpu_lighting(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            game.mobile_render_quality = MOBILE_RENDER_QUALITY_NATIVE
            game._mobile_renderer_accelerated = True
            game.configure_mobile_gpu_renderer(object(), object())
            self.assertFalse(game.mobile_lightweight_lighting_active())
            self.assertTrue(game.continuous_lighting_active())
            game._mobile_gpu_frame_active = True
            game._mobile_gpu_ui_viewport = game.mobile_world_viewport()

            game.draw_lighting()

            buffer = game._light_buffer_surface
            self.assertIsNotNone(buffer)
            assert buffer is not None
            screen_w, screen_h = game._screen_size()
            self.assertEqual(
                buffer.get_size(),
                (max(1, screen_w // 4), max(1, screen_h // 4)),
            )
            pending = game._mobile_gpu_pending_light
            self.assertIsNotNone(pending)
            assert pending is not None
            self.assertIs(pending[2], buffer)
            lights = game._collect_frame_lights()
            self.assertTrue(any(light.kind == "lantern" for light in lights))

    def test_native_local_lighting_caches_depth_tint_and_preserves_transparency(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            game.mobile_render_quality = MOBILE_RENDER_QUALITY_NATIVE
            game.current_depth = DUNGEON_DEPTH
            game.set_current_floor_dark(False)
            source = pygame.Surface((12, 12), pygame.SRCALPHA)
            source.fill((0, 0, 0, 0))
            pygame.draw.rect(source, (208, 184, 160, 255), (2, 2, 8, 8))

            tinted = game.apply_mobile_lightweight_ambient(source)
            self.assertIsNot(tinted, source)
            self.assertEqual(tinted.get_at((0, 0)).a, 0)
            self.assertLess(tinted.get_at((5, 5)).r, source.get_at((5, 5)).r)
            self.assertIs(game.apply_mobile_lightweight_ambient(source), tinted)
            self.assertLess(
                game.apply_mobile_lightweight_ambient_color((208, 184, 160))[0],
                208,
            )
            game._frame_cache = {}
            actor_lit = game.apply_lit_shading(
                source,
                source,
                game.player.x,
                game.player.y,
            )
            self.assertGreater(
                sum(actor_lit.get_at((5, 5))[:3]),
                sum(tinted.get_at((5, 5))[:3]),
            )
            hidden_light = LightSource(
                game.player.x + 8.0,
                game.player.y,
                16.0,
                (255, 0, 0),
                intensity=10.0,
                ttl=None,
                kind="hidden-test",
            )
            game.light_sources.append(hidden_light)
            game._frame_cache = {}
            game._mobile_lightweight_actor_cache.clear()
            hidden_lit = game.apply_lit_shading(
                source,
                source,
                game.player.x,
                game.player.y,
            )
            self.assertEqual(
                pygame.image.tobytes(hidden_lit, "RGBA"),
                pygame.image.tobytes(actor_lit, "RGBA"),
            )
            expected_lip = game.apply_mobile_lightweight_ambient_color(
                game.shade(game.theme.floor, 16)
            )
            shade_after_tint = game.shade(
                game.apply_mobile_lightweight_ambient_color(game.theme.floor),
                16,
            )
            self.assertNotEqual(expected_lip, shade_after_tint)

            game._lighting_enabled = False
            self.assertIs(game.apply_mobile_lightweight_ambient(source), source)

    def test_native_local_lighting_adds_no_unmasked_screen_space_pixels(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            game.mobile_render_quality = MOBILE_RENDER_QUALITY_NATIVE
            game.screen.fill((10, 10, 14))
            before = pygame.image.tobytes(game.screen, "RGB")
            game.draw_lighting()
            self.assertEqual(pygame.image.tobytes(game.screen, "RGB"), before)

    def test_native_floor_cache_rebuilds_when_lighting_mode_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            game.mobile_render_quality = MOBILE_RENDER_QUALITY_NATIVE
            game.set_current_floor_dark(False)
            game._lighting_enabled = True
            game._mobile_floor_layer_cache = None
            with patch.dict(os.environ, {"PYGAME_BLEND_ALPHA_SDL2": "1"}):
                game.draw()
                lit_cache = game._mobile_floor_layer_cache
                self.assertIsNotNone(lit_cache)
                assert lit_cache is not None

                game._lighting_enabled = False
                game.draw()
                unlit_cache = game._mobile_floor_layer_cache
                self.assertIsNotNone(unlit_cache)
                assert unlit_cache is not None
                self.assertIsNot(unlit_cache[3], lit_cache[3])
                self.assertNotEqual(unlit_cache[0], lit_cache[0])

                game._lighting_enabled = True
                game.draw()
                relit_cache = game._mobile_floor_layer_cache
                self.assertIsNotNone(relit_cache)
                assert relit_cache is not None
                self.assertIsNot(relit_cache[3], unlit_cache[3])
                self.assertEqual(relit_cache[0], lit_cache[0])

    def test_overlapping_gpu_ui_regions_are_coalesced_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (780, 360))
            first = pygame.Rect(20, 30, 180, 90)
            second = pygame.Rect(120, 80, 140, 70)
            game._mobile_gpu_ui_regions = [
                ("interaction", first, ("hint",)),
                ("diagnostics", second, ("perf",)),
            ]
            regions = game._mobile_gpu_coalesced_ui_regions()
            self.assertEqual(len(regions), 1)
            key, rect, revision = regions[0]
            self.assertEqual(key, "diagnostics|interaction")
            self.assertEqual(rect, first.union(second))
            self.assertIsInstance(revision, tuple)
            assert isinstance(revision, tuple)
            self.assertEqual(len(revision), 2)

    def test_mobile_floor_layer_patches_reveals_and_rebuilds_after_camera_travel(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1170, 540))
            game.state = "playing"
            self.assertFalse(game.is_current_floor_dark())
            candidate = next(
                point
                for point in game.revealed_tiles
                if game.dungeon.tiles[point[0]][point[1]]
                in (Tile.FLOOR, Tile.STAIRS)
            )
            game.revealed_tiles.remove(candidate)
            with patch.dict(os.environ, {"PYGAME_BLEND_ALPHA_SDL2": "1"}):
                game.draw()
                first = game._mobile_floor_layer_cache
                self.assertIsNotNone(first)
                assert first is not None
                first_surface = first[3]

                game.draw()
                second = game._mobile_floor_layer_cache
                self.assertIsNotNone(second)
                assert second is not None
                self.assertIs(second[3], first_surface)

                patches_before = getattr(game, "_mobile_floor_cache_patches", 0)
                game.revealed_tiles.add(candidate)
                game.draw()
                patched = game._mobile_floor_layer_cache
                self.assertIsNotNone(patched)
                assert patched is not None
                self.assertIs(patched[3], first_surface)
                self.assertGreater(game._mobile_floor_cache_patches, patches_before)
                patched_pixels = pygame.image.tobytes(patched[3], "RGB")

                game._mobile_floor_layer_cache = None
                game.draw()
                cold = game._mobile_floor_layer_cache
                self.assertIsNotNone(cold)
                assert cold is not None
                self.assertEqual(
                    pygame.image.tobytes(cold[3], "RGB"),
                    patched_pixels,
                )

                game._cam_iso = (cold[1] + cold[3].get_width(), cold[2])
                game.draw()
                rebuilt = game._mobile_floor_layer_cache
                self.assertIsNotNone(rebuilt)
                assert rebuilt is not None
                self.assertIsNot(rebuilt[3], cold[3])

    def test_mobile_floor_layer_translation_matches_live_tile_projection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1170, 540))
            game.state = "playing"
            with patch.dict(os.environ, {"PYGAME_BLEND_ALPHA_SDL2": "1"}):
                game.draw()
            cache = game._mobile_floor_layer_cache
            self.assertIsNotNone(cache)
            assert cache is not None
            layer = cache[3]
            candidate = min(
                (
                    point
                    for point in game.revealed_tiles
                    if game.dungeon.tiles[point[0]][point[1]]
                    in (Tile.FLOOR, Tile.STAIRS)
                ),
                key=lambda point: abs(point[0] - game.player.x)
                + abs(point[1] - game.player.y),
            )
            tile = game.dungeon.tiles[candidate[0]][candidate[1]]
            root = game.screen
            viewport = game.mobile_world_viewport().clip(root.get_rect())
            old_cache = game._frame_cache
            old_world_rendering = game._mobile_world_rendering
            try:
                game._mobile_root_screen = root
                game.screen = layer
                game._mobile_world_rendering = True
                game._frame_cache = {"camera_iso": (cache[1], cache[2])}
                cached_entry = game._tile_blit_entry(*candidate, tile)
                self.assertIsNotNone(cached_entry)
                assert cached_entry is not None

                game._cam_iso = (cache[1] + 0.37, cache[2] + 0.37)
                game.screen = root.subsurface(viewport)
                game._frame_cache = {}
                live_entry = game._tile_blit_entry(*candidate, tile)
                self.assertIsNotNone(live_entry)
                assert live_entry is not None
                destination = game._mobile_floor_layer_destination(
                    viewport.size,
                    layer,
                    (cache[1], cache[2]),
                    game._cam_iso,
                )
            finally:
                game.screen = root
                game._frame_cache = old_cache
                game._mobile_world_rendering = old_world_rendering
                del game._mobile_root_screen

            self.assertEqual(
                (
                    cached_entry[1][0] + destination[0],
                    cached_entry[1][1] + destination[1],
                ),
                live_entry[1],
            )

    def test_dark_floor_bypasses_mobile_floor_layer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1170, 540))
            with (
                patch.dict(os.environ, {"PYGAME_BLEND_ALPHA_SDL2": "1"}),
                patch.object(game, "is_current_floor_dark", return_value=True),
            ):
                self.assertFalse(game._draw_cached_mobile_floor_layer())
            self.assertIsNone(getattr(game, "_mobile_floor_layer_cache", None))

    def test_mobile_performance_monitor_reports_phase_and_runtime_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (780, 360))
            game._mobile_renderer_name = "opengles2"
            game._mobile_renderer_accelerated = True
            game._mobile_alpha_sdl2 = True
            game._mobile_cpu_neon = True
            now = [0.0]
            emitted: list[str] = []
            monitor = MobilePerformanceMonitor(
                report_interval=1.0,
                clock=lambda: now[0],
                emit=emitted.append,
            )
            game._aim_cone_cache = OrderedDict()
            game._aim_cone_cache[("test",)] = object()
            game._aim_cone_cache_hits = 7
            game._aim_cone_cache_misses = 2
            monitor.begin_frame()
            monitor.record_phase("world", 0.2)
            monitor.record_phase("hud", 0.05)
            monitor.record_phase("flip", 0.7)
            monitor.record_detail_phase("aim", 0.03)
            now[0] = 1.1
            report = monitor.finish_frame(game)

            self.assertIsNotNone(report)
            assert report is not None
            self.assertEqual(emitted, [report])
            self.assertTrue(report.startswith("ARCH_ROGUE_PERF "))
            self.assertIn("fps=0.91", report)
            self.assertIn("world:200.0", report)
            self.assertIn("hud:50.0", report)
            self.assertIn("flip:700.0", report)
            self.assertIn("logical=780x360", report)
            self.assertIn("renderer=opengles2 accelerated=yes", report)
            self.assertIn("alpha_sdl2=1 neon=yes", report)
            self.assertIn("cache=decoded:", report)
            self.assertIn("aim:30.0", report)
            self.assertIn("aim_cache=entries:1,hits+:7,misses+:2", report)
            self.assertIn("A2:1 N:yes", monitor.overlay_text)
            self.assertIn("T 0 U 0 W 200 H 50 F 700 A 0", monitor.overlay_detail_text)


    def test_mobile_aim_cone_uses_bounded_buckets_without_smoothscale(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            game._aim_cone_cache = OrderedDict()
            game._aim_cone_cache_hits = 0
            game._aim_cone_cache_misses = 0

            with patch.object(
                pygame.transform,
                "smoothscale",
                wraps=pygame.transform.smoothscale,
            ) as smoothscale:
                for index in range(360):
                    angle = math.tau * index / 360
                    game.player.facing_x = math.cos(angle)
                    game.player.facing_y = math.sin(angle)
                    game.draw_aim_cone()

            self.assertEqual(len(game._aim_cone_cache), 32)
            self.assertEqual(
                {int(key[-1]) for key in game._aim_cone_cache},
                set(range(32)),
            )
            self.assertEqual(game._aim_cone_cache_misses, 32)
            self.assertGreater(game._aim_cone_cache_hits, 300)
            total_bytes = sum(
                entry[0].get_width()
                * entry[0].get_height()
                * entry[0].get_bytesize()
                for entry in game._aim_cone_cache.values()
            )
            self.assertLess(total_bytes, 8 * 1024 * 1024)
            smoothscale.assert_not_called()

            def face_screen_angle(angle: float) -> None:
                iso_difference = 2.0 * math.cos(angle) / TILE_W
                iso_sum = 2.0 * math.sin(angle) / TILE_H
                game.player.facing_x = (iso_sum + iso_difference) * 0.5
                game.player.facing_y = (iso_sum - iso_difference) * 0.5

            bucket_width = math.tau / 32
            delattr(game, "_aim_cone_direction_bucket")
            face_screen_angle(bucket_width * 0.5 - 0.01)
            game.draw_aim_cone()
            self.assertEqual(game._aim_cone_direction_bucket, (32, 0))
            face_screen_angle(bucket_width * 0.5 + 0.01)
            game.draw_aim_cone()
            self.assertEqual(game._aim_cone_direction_bucket, (32, 0))
            face_screen_angle(bucket_width * 0.8)
            game.draw_aim_cone()
            self.assertEqual(game._aim_cone_direction_bucket, (32, 1))

            game.clear_mobile_memory_caches()
            self.assertEqual(len(game._aim_cone_cache), 0)

    def test_android_alpha_sources_enable_rle_without_changing_alpha(self) -> None:
        source = pygame.Surface((24, 24), pygame.SRCALPHA)
        source.fill((0, 0, 0, 0))
        pygame.draw.circle(source, (220, 90, 60, 180), (12, 12), 7)
        with patch.dict(os.environ, {"PYGAME_BLEND_ALPHA_SDL2": "1"}):
            optimized = optimize_immutable_alpha_surface(source, alpha=208)
        self.assertIs(optimized, source)
        self.assertEqual(source.get_alpha(), 208)
        self.assertTrue(source.get_flags() & pygame.RLEACCELOK)

    def test_android_binary_pixel_art_uses_equivalent_colorkey_rle(self) -> None:
        source = pygame.Surface((24, 24), pygame.SRCALPHA)
        source.fill((0, 0, 0, 0))
        pygame.draw.rect(source, (220, 90, 60, 255), (5, 4, 13, 16))
        pygame.draw.rect(source, (255, 0, 255, 255), (8, 8, 4, 4))
        with patch.dict(os.environ, {"PYGAME_BLEND_ALPHA_SDL2": "1"}):
            optimized = optimize_immutable_alpha_surface(source)

        self.assertIsNot(optimized, source)
        self.assertIsNotNone(optimized.get_colorkey())
        self.assertTrue(optimized.get_flags() & pygame.RLEACCELOK)
        expected = pygame.Surface((32, 32)).convert()
        actual = expected.copy()
        expected.fill((17, 29, 41))
        actual.fill((17, 29, 41))
        expected.blit(source, (3, 5))
        actual.blit(optimized, (3, 5))
        self.assertEqual(
            pygame.image.tobytes(actual, "RGB"),
            pygame.image.tobytes(expected, "RGB"),
        )

    def test_android_binary_pixel_art_benchmark_preserves_rendered_pixels(self) -> None:
        source = pygame.Surface((96, 96), pygame.SRCALPHA)
        source.fill((0, 0, 0, 0))
        pygame.draw.rect(source, (220, 90, 60, 255), (12, 8, 50, 70))
        expected = pygame.Surface((112, 112)).convert()
        actual = expected.copy()
        expected.fill((17, 29, 41))
        actual.fill((17, 29, 41))
        expected.blit(source, (7, 9))

        with (
            patch.dict(os.environ, {"PYGAME_BLEND_ALPHA_SDL2": "1"}),
            patch.object(mobile_runtime, "android_runtime_active", return_value=True),
            patch.object(mobile_runtime, "_ANDROID_BINARY_ALPHA_MODE", None),
            patch("builtins.print"),
        ):
            optimized = optimize_immutable_alpha_surface(source)
            selected = mobile_runtime._ANDROID_BINARY_ALPHA_MODE

        self.assertIn(
            selected,
            ("alpha", "alpha_rle", "colorkey", "colorkey_rle"),
        )
        actual.blit(optimized, (7, 9))
        self.assertEqual(
            pygame.image.tobytes(actual, "RGB"),
            pygame.image.tobytes(expected, "RGB"),
        )

    def test_mobile_skips_full_viewport_ambient_overlay_when_lighting_is_off(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            game.state = "playing"
            game._lighting_enabled = False
            game.set_current_floor_dark(False)
            with patch.object(
                game,
                "ambient_overlay_surface",
                wraps=game.ambient_overlay_surface,
            ) as ambient_surface:
                game.draw_ambient_depth_overlay()
            ambient_surface.assert_not_called()

    def test_static_native_mobile_menu_redraws_only_when_signature_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            game.state = "options"
            game.options_cursor = 0
            with (
                patch.object(
                    game,
                    "draw_options_menu",
                    wraps=game.draw_options_menu,
                ) as draw_options,
                patch.object(game, "_present_frame") as present,
            ):
                game.draw()
                touch_targets = tuple(game._mobile_touch_targets)
                self.assertEqual(touch_targets, ())
                game.draw()
                self.assertEqual(tuple(game._mobile_touch_targets), touch_targets)
                self.assertEqual(draw_options.call_count, 1)
                self.assertEqual(present.call_count, 1)

                game.options_cursor = 1
                game.draw()
                self.assertEqual(draw_options.call_count, 2)
                self.assertEqual(present.call_count, 2)

    def test_gpu_screen_flash_queues_one_pixel_overlay_and_falls_back_safely(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            base_color = (20, 40, 60)
            post_color = (80, 100, 120)
            flash_color = (210, 48, 24)
            viewport = pygame.Rect(200, 100, 800, 500)
            post_light = pygame.Surface(viewport.size, pygame.SRCALPHA)
            post_light.fill((*post_color, 255))
            game.screen.fill(base_color)
            game._mobile_gpu_frame_active = True
            game._mobile_gpu_ui_viewport = viewport.copy()
            game._mobile_gpu_ui_surface = post_light
            game.screen_flash_color = flash_color
            game.screen_flash_ttl = 0.30

            game.draw_screen_flash()

            self.assertTrue(game.mobile_gpu_frame_active())
            self.assertEqual(game._mobile_gpu_pending_flash, (flash_color, 120))
            self.assertEqual(game.screen.get_at(viewport.center)[:3], base_color)
            self.assertEqual(
                post_light.get_at((viewport.width // 2, viewport.height // 2)),
                (*post_color, 255),
            )

            flash_sample = pygame.Surface((1, 1), pygame.SRCALPHA)
            flash_sample.fill((*flash_color, 120))
            expected_outer = pygame.Surface((1, 1), pygame.SRCALPHA)
            expected_outer.fill((*base_color, 255))
            expected_outer.blit(flash_sample, (0, 0))
            expected_viewport = pygame.Surface((1, 1), pygame.SRCALPHA)
            expected_viewport.fill((*post_color, 255))
            expected_viewport.blit(flash_sample, (0, 0))

            game._composite_mobile_gpu_ui_fallback()

            self.assertFalse(game.mobile_gpu_frame_active())
            self.assertIsNone(game._mobile_gpu_pending_flash)
            self.assertEqual(
                game.screen.get_at(viewport.center),
                expected_viewport.get_at((0, 0)),
            )
            for point in (
                (viewport.centerx, viewport.top // 2),
                (viewport.centerx, (viewport.bottom + game.screen.get_height()) // 2),
                (viewport.left // 2, viewport.centery),
                ((viewport.right + game.screen.get_width()) // 2, viewport.centery),
            ):
                with self.subTest(point=point):
                    self.assertEqual(
                        game.screen.get_at(point),
                        expected_outer.get_at((0, 0)),
                    )

    def test_gpu_lighting_presenter_uses_retained_shell_and_indexed_ui(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (780, 360))
            game.state = "playing"
            game.screen_flash_color = (210, 48, 24)
            game.screen_flash_ttl = 0.30
            calls: list[tuple[str, object, object | None]] = []

            class FakeTexture:
                def __init__(self, size: tuple[int, int]) -> None:
                    self.size = size
                    self.blend_mode = -1

                def update(self, surface: pygame.Surface) -> None:
                    calls.append(("update", self, surface.get_size()))

            class FakeRenderer:
                logical_size = game.screen.get_size()
                draw_color = (0, 0, 0, 0)

                def clear(self) -> None:
                    calls.append(("clear", self.draw_color, None))

                def blit(self, texture: FakeTexture, rect: pygame.Rect) -> None:
                    calls.append(("blit", texture, rect.copy()))

                def present(self) -> None:
                    calls.append(("present", self, None))

            def make_texture(
                _renderer: object, size: tuple[int, int]
            ) -> FakeTexture:
                return FakeTexture(size)

            renderer = FakeRenderer()
            game._mobile_renderer_accelerated = True
            game.configure_mobile_gpu_renderer(object(), renderer)
            with (
                patch.object(game, "_create_mobile_gpu_texture", side_effect=make_texture),
                patch("arch_rogue.rendering.base.pygame.display.flip") as flip,
            ):
                game.draw()
                first_ui_pixels = game._mobile_gpu_ui_upload_pixels
                first_ui_regions = game._mobile_gpu_ui_region_count
                first_dirty = game._mobile_gpu_ui_dirty_rect
                first_base_pixels = game._mobile_gpu_base_upload_pixels
                calls.clear()
                game.draw()

            self.assertFalse(flip.called)
            self.assertTrue(game._mobile_gpu_last_present)
            self.assertFalse(game.screen.get_locked())
            viewport = game.mobile_world_viewport()
            root_pixels = game.screen.get_width() * game.screen.get_height()
            self.assertEqual(first_base_pixels, root_pixels)
            self.assertEqual(first_ui_regions, 1)
            self.assertGreater(first_ui_pixels, 0)
            self.assertIsNotNone(first_dirty)
            assert first_dirty is not None
            self.assertEqual(first_ui_pixels, first_dirty.width * first_dirty.height)

            shell = getattr(game, "_mobile_gpu_shell_texture")
            base = getattr(game, "_mobile_gpu_base_texture")
            light = getattr(game, "_mobile_gpu_light_texture")
            flash = getattr(game, "_mobile_gpu_flash_texture")
            ui_textures = {
                entry[1] for entry in game._mobile_gpu_ui_region_textures.values()
            }
            update_sizes = [
                value
                for action, _texture, value in calls
                if action == "update"
            ]
            self.assertIn(viewport.size, update_sizes)
            self.assertIn((1, 1), update_sizes)
            self.assertFalse(
                any(
                    action == "update" and texture is shell
                    for action, texture, _value in calls
                )
            )
            self.assertFalse(
                any(
                    action == "update" and texture in ui_textures
                    for action, texture, _value in calls
                )
            )
            self.assertEqual(game._mobile_gpu_ui_upload_pixels, 0)
            # Full-screen viewport: every HUD control already lives inside the
            # streamed world texture, so no duplicate base-region uploads remain.
            self.assertEqual(game._mobile_gpu_base_region_count, 0)
            # Second frame uploads only the world viewport, not the shell.
            self.assertLessEqual(game._mobile_gpu_base_upload_pixels, root_pixels)
            self.assertEqual(game._mobile_gpu_base_regions, [])

            blitted = [
                texture
                for action, texture, _value in calls
                if action == "blit"
            ]
            self.assertLess(blitted.index(shell), blitted.index(base))
            self.assertLess(blitted.index(base), blitted.index(light))
            self.assertLess(
                blitted.index(light),
                min(blitted.index(texture) for texture in ui_textures),
            )
            self.assertLess(
                max(blitted.index(texture) for texture in ui_textures),
                blitted.index(flash),
            )
            self.assertEqual(shell.blend_mode, 0)
            self.assertEqual(base.blend_mode, 0)
            self.assertEqual(light.blend_mode, 4)
            self.assertTrue(all(texture.blend_mode == 1 for texture in ui_textures))
            self.assertEqual(flash.blend_mode, 1)


class MobileLayoutTests(unittest.TestCase):
    def test_safe_insets_coerce_and_clamp(self) -> None:
        self.assertEqual(SafeInsets.coerce(None), SafeInsets())
        self.assertEqual(SafeInsets.coerce((1, 2, 3, 4)), SafeInsets(1, 2, 3, 4))
        self.assertEqual(SafeInsets.coerce(SafeInsets(5, 6, 7, 8)), SafeInsets(5, 6, 7, 8))
        clamped = SafeInsets(120, 0, 120, 0).clamp_to(100, 50)
        self.assertEqual(clamped, SafeInsets(99, 0, 0, 0))
        clamped2 = SafeInsets(70, 8, 70, 8).clamp_to(100, 50)
        self.assertEqual(clamped2, SafeInsets(70, 8, 29, 8))
        with self.assertRaises(ValueError):
            SafeInsets.coerce((1, 2, 3))

    def test_layout_matrix_centers_viewport_and_keeps_rails_apart(self) -> None:
        for size, insets in (
            ((780, 360), (0, 0, 0, 0)),
            ((1280, 720), (0, 0, 0, 0)),
            ((2340, 1080), (90, 0, 18, 0)),
            ((2340, 1080), (18, 0, 90, 0)),
            ((1920, 1200), (0, 0, 0, 0)),
            ((1280, 960), (0, 0, 0, 0)),
        ):
            with self.subTest(size=size, insets=insets):
                layout = build_mobile_layout(size, insets)
                self.assertEqual(layout.display_rect.size, size)
                self.assertTrue(layout.safe_rect.contains(layout.left_rail))
                self.assertTrue(layout.safe_rect.contains(layout.right_rail))
                # The world renders edge-to-edge across the whole display; both
                # rails are overlays on top of it.
                self.assertEqual(layout.world_viewport, layout.display_rect)
                self.assertTrue(layout.left_rail.colliderect(layout.world_viewport))
                self.assertTrue(layout.right_rail.colliderect(layout.world_viewport))
                self.assertTrue(layout.world_viewport.contains(layout.gameplay_rect))
                self.assertFalse(layout.left_rail.colliderect(layout.gameplay_rect))
                self.assertFalse(layout.right_rail.colliderect(layout.gameplay_rect))
                self.assertEqual(layout.world_focus[0], layout.gameplay_rect.centerx)
                self.assertEqual(len(layout.action_rects), 6)
                self.assertEqual(len(layout.resource_rects), 3)
                for first, second in zip(
                    layout.action_rects, layout.action_rects[1:]
                ):
                    self.assertFalse(first.colliderect(second))
                self.assertTrue(all(layout.safe_rect.contains(rect) for rect in layout.action_rects))
                self.assertTrue(layout.safe_rect.contains(layout.menu_rect))
                self.assertTrue(layout.safe_rect.contains(layout.joystick_rect))
                self.assertTrue(layout.safe_rect.contains(layout.hub_panel_rect))
                self.assertFalse(layout.left_rail.colliderect(layout.joystick_rect))
                self.assertTrue(layout.world_viewport.colliderect(layout.joystick_rect))
                self.assertTrue(layout.left_rail.contains(layout.run_info_rect))
                self.assertEqual(
                    [name for name, _rect in layout.hub_option_rects],
                    ["inventory", "character", "quest", "exit"],
                )
                self.assertTrue(
                    all(
                        layout.hub_panel_rect.contains(rect)
                        for _name, rect in layout.hub_option_rects
                    )
                )

    def test_character_summary_only_appears_when_the_left_rail_has_room(self) -> None:
        compact = build_mobile_layout((780, 360))
        regular = build_mobile_layout((1280, 720))
        self.assertIsNone(compact.character_rect)
        self.assertIsNotNone(regular.character_rect)
        self.assertGreaterEqual(regular.joystick_rect.width, 180)
        self.assertGreater(regular.joystick_rect.left, regular.left_rail.left)
        self.assertLess(regular.joystick_rect.bottom, regular.safe_rect.bottom)

    def test_story_relic_tint_is_alpha_masked_and_cached(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            visual = game.sprites.item_visual("story_relic", 0.0, "Common")
            accent = (200, 60, 220)
            sprite = game._story_relic_sprite(visual, accent, 2)
            # Same inputs return the identical cached surface (no per-frame
            # copy/rotate), and the additive tint never paints the colorkey
            # background (which would leak as a magenta box on Android).
            self.assertIs(game._story_relic_sprite(visual, accent, 2), sprite)
            if visual.is_asset:
                colorkey = visual.surface.get_colorkey()
                if colorkey is not None:
                    px = sprite.get_at((0, 0))
                    self.assertNotEqual(px[:3], colorkey[:3])
            self.assertLessEqual(len(game._story_relic_sprite_cache), 96)

    def test_cutscene_skips_world_render_and_fills_screen(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            self.assertTrue(game.start_quest_cutscene("story_guest_omen"))
            self.assertIsNotNone(game.active_cutscene)
            with (
                patch.object(game, "_render_world_view") as render_world,
                patch.object(game, "draw_ui") as draw_ui,
            ):
                game.draw()
            render_world.assert_not_called()
            draw_ui.assert_not_called()
            # The cutscene background paints the whole display, not just the
            # safe area (which has zero insets here, but the point is the
            # overlay runs full-bleed and covers the frame).
            self.assertIsNotNone(game._cutscene_panel_rect)

    def test_world_viewport_and_menus_cover_full_display(self) -> None:
        for size, insets in (
            ((780, 360), (0, 0, 0, 0)),
            ((1280, 720), (0, 0, 0, 0)),
            ((2340, 1080), (90, 0, 18, 0)),
            ((2340, 1080), (18, 0, 90, 0)),
        ):
            with self.subTest(size=size, insets=insets):
                layout = build_mobile_layout(size, insets)
                self.assertEqual(layout.world_viewport, layout.display_rect)
                self.assertTrue(layout.safe_rect.contains(layout.menu_rect))
                self.assertTrue(layout.safe_rect.contains(layout.hub_panel_rect))
                self.assertTrue(layout.safe_rect.contains(layout.left_rail))
                self.assertTrue(layout.safe_rect.contains(layout.right_rail))
                self.assertFalse(layout.left_rail.colliderect(layout.gameplay_rect))
                self.assertFalse(layout.right_rail.colliderect(layout.gameplay_rect))

    def test_detect_mobile_runtime_env_override(self) -> None:
        old = os.environ.pop("ARCH_ROGUE_MOBILE", None)
        try:
            os.environ["ARCH_ROGUE_MOBILE"] = "1"
            self.assertTrue(detect_mobile_runtime())
            os.environ["ARCH_ROGUE_MOBILE"] = "no"
            self.assertFalse(detect_mobile_runtime())
        finally:
            if old is not None:
                os.environ["ARCH_ROGUE_MOBILE"] = old
            else:
                os.environ.pop("ARCH_ROGUE_MOBILE", None)


class MobileHudTests(unittest.TestCase):
    def test_mobile_hud_publishes_six_action_targets_and_resource_bars(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720), (42, 8, 18, 12))
            game.draw()
            self.assertEqual(len(game._hud_action_rects), 6)
            self.assertEqual(len(game._hud_resource_bar_rects), 3)
            layout = game.mobile_layout()
            self.assertEqual(game.mobile_safe_rect(), layout.safe_rect)
            self.assertEqual(game.mobile_world_viewport(), layout.world_viewport)
            ability_commands = {
                target.command
                for target in game._mobile_touch_targets
                if target.context == "gameplay"
                and target.command.startswith("ability_")
            }
            self.assertEqual(
                ability_commands,
                {
                    Command.ABILITY_1,
                    Command.ABILITY_2,
                    Command.ABILITY_3,
                    Command.ABILITY_4,
                    Command.ABILITY_5,
                    Command.ABILITY_6,
                },
            )
            targets = game._mobile_touch_targets
            self.assertIn(
                (Command.MOBILE_MENU, "Game menu"),
                {(target.command, target.label) for target in targets},
            )
            self.assertNotIn(
                Command.BACK,
                {target.command for target in targets if target.context == "gameplay"},
            )
            self.assertTrue(
                {
                    Command.INVENTORY,
                    Command.CHARACTER,
                    Command.QUEST,
                }.isdisjoint(
                    {
                        target.command
                        for target in targets
                        if target.context == "gameplay"
                    }
                )
            )
            interaction_targets = [
                target for target in targets if target.command == Command.INTERACT
            ]
            self.assertEqual(len(interaction_targets), 1)
            prompt = game._interaction_prompt_rect
            self.assertIsNotNone(prompt)
            assert prompt is not None
            self.assertEqual(
                interaction_targets[0].rect,
                prompt.move(layout.world_viewport.topleft),
            )
            self.assertLessEqual(prompt.width, game.ui(380))
            self.assertLess(prompt.width, game.ui(560))
            self.assertNotIn("interact", game._hud_layout)
            self.assertFalse(game.quest_info_visible)
            self.assertIsNone(game._story_panel_rect)
            self.assertIsNone(game._run_header_rect)
            self.assertIsNone(game._run_header_render_key)
            run_info_key = game._mobile_run_info_render_key
            self.assertEqual(run_info_key[0], "Run 1: Depth 1/10")
            self.assertTrue(str(run_info_key[1]))
            self.assertEqual(run_info_key[2], "Difficulty: Medium")
            self.assertEqual(game._hud_layout["run_info"], layout.run_info_rect)
            self.assertFalse(
                any(
                    target.label.upper() in {"USE", "INTERACT"}
                    for target in targets
                    if target.context == "gameplay"
                )
            )
            self.assertIsNotNone(game.ui_assets.source("hud.mobile.joystick_base"))
            self.assertIsNotNone(game.ui_assets.source("hud.mobile.joystick_knob"))
            self.assertIsNotNone(game.ui_assets.source("hud.mobile.status_bar_frame"))
            self.assertIsNotNone(game.ui_assets.source("hud.mobile.info_panel"))

    def test_mobile_boss_bar_uses_clear_top_center_without_run_header(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            boss = type("BossStub", (), {"size": 2, "hp": 100, "max_hp": 100})()
            with patch.object(game, "boss_enemy", return_value=boss):
                metrics = game.boss_bar_metrics()
            self.assertIsNotNone(metrics)
            assert metrics is not None
            bar_rect, plaque_rect, _big = metrics
            layout = game.mobile_layout()
            local_focus_x = layout.world_focus[0] - layout.world_viewport.x
            self.assertEqual(bar_rect.centerx, local_focus_x)
            self.assertEqual(plaque_rect.top, game.ui(14))

    def test_mobile_hub_publishes_exactly_four_requested_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            self.assertTrue(game._dispatch_command(Command.MOBILE_MENU))
            game.draw()

            expected = {
                Command.INVENTORY,
                Command.CHARACTER,
                Command.QUEST,
                Command.MOBILE_EXIT,
            }
            rows = [
                target
                for target in game._mobile_touch_targets
                if target.context == "mobile_hub" and target.command in expected
            ]
            self.assertEqual(len(rows), 4)
            self.assertEqual({target.command for target in rows}, expected)
            self.assertEqual(
                [target.label for target in rows],
                ["Inventory", "Character", "Quest", "Exit game"],
            )
            self.assertEqual(
                len(
                    [
                        target
                        for target in game._mobile_touch_targets
                        if target.context == "mobile_hub"
                        and game.mobile_layout().hub_panel_rect.contains(target.rect)
                    ]
                ),
                4,
            )

    def test_mobile_quest_is_modal_and_pauses_simulation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            self.assertTrue(game._dispatch_command(Command.MOBILE_MENU))
            self.assertTrue(game._dispatch_command(Command.QUEST))
            self.assertFalse(game.mobile_hub_open)
            self.assertTrue(game.quest_info_visible)
            self.assertEqual(game.mobile_input_context(), "quest")

            with patch.object(game, "update_player") as update_player:
                game.update(1.0 / 60.0)
            update_player.assert_not_called()

            game.draw()
            story_rect = game._story_panel_rect
            self.assertIsInstance(story_rect, pygame.Rect)
            assert isinstance(story_rect, pygame.Rect)
            self.assertTrue(
                pygame.Rect((0, 0), game.mobile_world_viewport().size).contains(
                    story_rect
                )
            )
            self.assertIsNone(game._interaction_prompt_rect)
            self.assertIsNone(game._run_header_rect)
            local_gameplay = game.mobile_layout().gameplay_rect.move(
                -game.mobile_world_viewport().x,
                -game.mobile_world_viewport().y,
            )
            self.assertTrue(local_gameplay.contains(story_rect))

    def test_spirit_beast_petting_tooltip_is_tappable_on_mobile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            beast = type(
                "BeastStub",
                (),
                {
                    "kind": "spirit_beast",
                    "alive": True,
                    "pet_cooldown": 0.0,
                    "x": game.player.x + 0.6,
                    "y": game.player.y,
                    "name": "Spirit Wolf",
                },
            )()
            with (
                patch.object(game, "nearby_pettable_spirit_beast", return_value=beast),
                patch.object(game.player, "class_name", "Ranger"),
                patch.object(game, "spirit_beast_pet_heal", return_value=4),
            ):
                hint = game.current_interaction_hint()
            self.assertIsNotNone(hint)
            assert hint is not None
            self.assertEqual(hint[0], "E")
            self.assertIn("Pet", hint[1])

    def test_touch_target_minimum_size_and_ripple_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            tiny = pygame.Rect(600, 300, 24, 24)
            game.register_mobile_touch_target(tiny, "test_cmd", "Test", context="gameplay")
            target = game._mobile_touch_targets[-1]
            minimum = max(40, game.mobile_layout().safe_rect.height // 12)
            self.assertGreaterEqual(target.rect.width, minimum)
            self.assertGreaterEqual(target.rect.height, minimum)
            self.assertTrue(target.rect.collidepoint(tiny.center))

            # Finger-down on a target records a confirmation ripple.
            size = game._mobile_display_surface().get_size()
            event = pygame.event.Event(
                pygame.FINGERDOWN, touch_id=0, finger_id=88,
                x=target.rect.centerx / (size[0] - 1),
                y=target.rect.centery / (size[1] - 1),
            )
            with patch.object(game, "_dispatch_command", return_value=True):
                game.handle_mobile_finger_event(event)
            self.assertEqual(len(game._mobile_touch_ripples), 1)

    def test_story_guest_tooltip_is_tappable_on_mobile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            guest = StoryGuest(
                game.player.x + 0.4,
                game.player.y,
                game.current_depth,
                0,
                "Ilyra",
                "Veiled Witness",
                "seeks safe passage",
                "The old stones remember.",
                [],
            )
            game.story_guests = [guest]

            game.draw()

            targets = [
                target
                for target in game._mobile_touch_targets
                if target.context == "gameplay"
                and target.command == Command.INTERACT
            ]
            self.assertEqual(len(targets), 1)
            prompt = game._interaction_prompt_rect
            self.assertIsNotNone(prompt)
            assert prompt is not None
            viewport = game.mobile_world_viewport()
            self.assertEqual(targets[0].rect, prompt.move(viewport.topleft))
            size = game._mobile_display_surface().get_size()
            x, y = targets[0].rect.center
            event = pygame.event.Event(
                pygame.FINGERDOWN,
                touch_id=0,
                finger_id=71,
                x=x / max(1, size[0] - 1),
                y=y / max(1, size[1] - 1),
            )
            with patch.object(game, "talk_to_story_guest") as talk:
                self.assertTrue(game.handle_mobile_finger_event(event))
            talk.assert_called_once_with(guest)

    def test_non_actionable_mobile_prompt_is_not_tappable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            warning = (
                "!",
                "The gate is sealed",
                "Defeat the guardian before trying this ancient lock.",
                (205, 84, 70),
            )
            with patch.object(game, "current_interaction_hint", return_value=warning):
                game.draw()

            self.assertIsInstance(game._interaction_prompt_rect, pygame.Rect)
            self.assertFalse(
                any(
                    target.command == Command.INTERACT
                    for target in game._mobile_touch_targets
                    if target.context == "gameplay"
                )
            )

    def test_safe_insets_override_propagates_to_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (2340, 1080), (90, 0, 18, 0))
            self.assertEqual(game.mobile_safe_insets, SafeInsets(90, 0, 18, 0))
            layout = game.mobile_layout()
            self.assertEqual(layout.safe_rect.x, 90)
            self.assertEqual(layout.safe_rect.right, 2340 - 18)
            self.assertTrue(layout.left_rail.x >= layout.safe_rect.x)
            self.assertTrue(layout.right_rail.right <= layout.safe_rect.right)


class MobileTouchTests(unittest.TestCase):
    def finger_event(self, event_type: int, x: float, y: float, key=(0, 0)) -> pygame.event.Event:
        return pygame.event.Event(event_type, touch_id=key[0], finger_id=key[1], x=x, y=y)

    @staticmethod
    def normalized(
        point: tuple[int, int], size: tuple[int, int]
    ) -> tuple[float, float]:
        return point[0] / size[0], point[1] / size[1]

    def swipe(
        self,
        game: Game,
        start: tuple[int, int],
        end: tuple[int, int],
        key: tuple[int, int] = (0, 41),
    ) -> None:
        size = game._mobile_display_surface().get_size()
        self.assertTrue(
            game.handle_mobile_finger_event(
                self.finger_event(
                    pygame.FINGERDOWN, *self.normalized(start, size), key=key
                )
            )
        )
        self.assertTrue(
            game.handle_mobile_finger_event(
                self.finger_event(
                    pygame.FINGERUP, *self.normalized(end, size), key=key
                )
            )
        )

    def test_joystick_touch_tracks_direction_magnitude_and_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            game.draw()
            joystick = game.mobile_layout().joystick_rect
            size = game._mobile_display_surface().get_size()
            key = (0, 51)
            near = (
                joystick.centerx + max(1, joystick.width // 5),
                joystick.centery,
            )
            far = (joystick.right - 2, joystick.centery)

            self.assertTrue(
                game.handle_mobile_finger_event(
                    self.finger_event(
                        pygame.FINGERDOWN, *self.normalized(near, size), key=key
                    )
                )
            )
            initial_screen = game.mobile_joystick_screen_vector()
            initial_magnitude = math.hypot(*initial_screen)
            self.assertGreater(initial_screen[0], 0.0)
            self.assertLess(abs(initial_screen[1]), 0.02)
            world_x, world_y = game.mobile_joystick_world_vector()
            self.assertGreater(world_x, 0.0)
            self.assertLess(world_y, 0.0)

            self.assertTrue(
                game.handle_mobile_finger_event(
                    self.finger_event(
                        pygame.FINGERMOTION, *self.normalized(far, size), key=key
                    )
                )
            )
            self.assertGreater(
                math.hypot(*game.mobile_joystick_screen_vector()),
                initial_magnitude,
            )

            self.assertTrue(
                game.handle_mobile_finger_event(
                    self.finger_event(
                        pygame.FINGERUP, *self.normalized(far, size), key=key
                    )
                )
            )
            self.assertEqual(game.mobile_joystick_screen_vector(), (0.0, 0.0))
            self.assertEqual(game.mobile_joystick_world_vector(), (0.0, 0.0))
            self.assertIsNone(game._mobile_joystick_finger)

    def test_update_player_uses_mobile_joystick_world_vector(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            game._mobile_joystick_vector = (1.0, 0.0)
            with (
                patch.object(game, "move_actor", return_value=0.25) as move_actor,
                patch.object(game, "enemy_in_melee_arc", return_value=False),
            ):
                game.update_player(0.1)

            move_actor.assert_called_once()
            actor, dx, dy = move_actor.call_args.args
            self.assertIs(actor, game.player)
            self.assertGreater(dx, 0.0)
            self.assertLess(dy, 0.0)
            self.assertGreater(game.player.locomotion_anim_scale, 0.0)

    def test_left_info_overlay_blocks_world_aim_touches(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            game.draw()
            layout = game.mobile_layout()
            size = game._mobile_display_surface().get_size()
            self.assertTrue(
                game.handle_mobile_finger_event(
                    self.finger_event(
                        pygame.FINGERDOWN,
                        *self.normalized(layout.run_info_rect.center, size),
                        key=(0, 53),
                    )
                )
            )
            self.assertFalse(game._mobile_touch_world_active)
            self.assertIsNone(game.active_mobile_world_touch())

    def test_mobile_camera_focus_stays_in_unobstructed_gameplay_area(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            game.snap_camera_to_player()
            game.draw()
            layout = game.mobile_layout()
            self.assertEqual(
                game.world_to_display(game.player.x, game.player.y),
                layout.world_focus,
            )
            world_x, world_y = game.screen_to_world(*layout.world_focus)
            self.assertAlmostEqual(world_x, game.player.x, places=6)
            self.assertAlmostEqual(world_y, game.player.y, places=6)

    def test_world_touch_aims_without_moving_player(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            game.draw()
            viewport = game.mobile_world_viewport()
            size = game._mobile_display_surface().get_size()
            point = (viewport.right - 40, viewport.centery)
            self.assertTrue(
                game.handle_mobile_finger_event(
                    self.finger_event(
                        pygame.FINGERDOWN,
                        *self.normalized(point, size),
                        key=(0, 52),
                    )
                )
            )
            with (
                patch.object(game, "move_actor") as move_actor,
                patch.object(game, "enemy_in_melee_arc", return_value=False),
            ):
                game.update_player(0.1)
            move_actor.assert_not_called()
            self.assertTrue(game._mobile_touch_world_active)
            self.assertEqual(game.aim_input_mode, "touch")

    def test_world_finger_capture_updates_aim_and_release_stops(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            game.draw()
            viewport = game.mobile_world_viewport()
            size = game._mobile_display_surface().get_size()
            down_point = viewport.center
            release_point = (viewport.right - 40, viewport.centery)
            down = self.finger_event(
                pygame.FINGERDOWN, *self.normalized(down_point, size)
            )
            self.assertTrue(game.handle_mobile_finger_event(down))
            self.assertTrue(game._mobile_touch_world_active)
            self.assertEqual(game.aim_input_mode, "touch")
            self.assertEqual(game.active_mobile_world_touch(), down_point)

            up = self.finger_event(
                pygame.FINGERUP, *self.normalized(release_point, size)
            )
            mapped_release = game.mobile_finger_position(up, size)
            target_x, target_y = game.screen_to_world(*mapped_release)
            expected_dx = target_x - game.player.x
            expected_dy = target_y - game.player.y
            expected_length = math.hypot(expected_dx, expected_dy)
            self.assertGreater(expected_length, 0.05)
            expected_facing = (
                expected_dx / expected_length,
                expected_dy / expected_length,
            )

            self.assertTrue(game.handle_mobile_finger_event(up))
            self.assertFalse(game._mobile_touch_world_active)
            self.assertIsNone(game._mobile_touch_world_point)
            self.assertIsNone(game.active_mobile_world_touch())
            self.assertAlmostEqual(game.player.facing_x, expected_facing[0], places=6)
            self.assertAlmostEqual(game.player.facing_y, expected_facing[1], places=6)

            facing_after_release = (game.player.facing_x, game.player.facing_y)
            game._cam_iso = (game._cam_iso[0] + 100.0, game._cam_iso[1] + 100.0)
            game.update_player_aim()
            self.assertEqual(
                (game.player.facing_x, game.player.facing_y),
                facing_after_release,
            )

    def test_skill_finger_dispatches_ability_without_world_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            game.draw()
            layout = game.mobile_layout()
            slot = layout.action_rects[1]
            coords = ((slot.centerx + 0.5) / 1280.0, (slot.centery + 0.5) / 720.0)
            bolt_calls = 0
            original = game.player_cast_bolt

            def cast_bolt() -> None:
                nonlocal bolt_calls
                bolt_calls += 1
                original()

            game.player_cast_bolt = cast_bolt  # type: ignore[assignment]
            down = self.finger_event(pygame.FINGERDOWN, *coords)
            self.assertTrue(game.handle_mobile_finger_event(down))
            self.assertEqual(bolt_calls, 1)
            self.assertFalse(game._mobile_touch_world_active)

    def test_joystick_world_aim_and_skill_fingers_can_coexist(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            game.draw()
            layout = game.mobile_layout()
            size = game._mobile_display_surface().get_size()
            joystick_point = (
                layout.joystick_rect.right - 2,
                layout.joystick_rect.centery,
            )
            world_point = (layout.world_viewport.right - 40, layout.world_viewport.centery)
            skill_point = layout.action_rects[0].center

            joystick_down = self.finger_event(
                pygame.FINGERDOWN,
                *self.normalized(joystick_point, size),
                key=(0, 61),
            )
            world_down = self.finger_event(
                pygame.FINGERDOWN,
                *self.normalized(world_point, size),
                key=(0, 62),
            )
            skill_down = self.finger_event(
                pygame.FINGERDOWN,
                *self.normalized(skill_point, size),
                key=(0, 63),
            )

            self.assertTrue(game.handle_mobile_finger_event(joystick_down))
            self.assertTrue(game.handle_mobile_finger_event(world_down))
            with patch.object(game, "player_melee_attack") as melee:
                self.assertTrue(game.handle_mobile_finger_event(skill_down))
            melee.assert_called_once_with()
            self.assertIsNotNone(game._mobile_joystick_finger)
            self.assertGreater(game.mobile_joystick_screen_vector()[0], 0.0)
            self.assertTrue(game._mobile_touch_world_active)
            self.assertEqual(game.aim_input_mode, "touch")

    def test_world_and_skill_fingers_can_coexist(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            game.draw()
            layout = game.mobile_layout()
            viewport = layout.world_viewport
            world_coords = (viewport.centerx / 1280.0, viewport.centery / 720.0)
            slot = layout.action_rects[0]
            skill_coords = ((slot.centerx + 0.5) / 1280.0, (slot.centery + 0.5) / 720.0)
            world_down = self.finger_event(pygame.FINGERDOWN, *world_coords, key=(0, 1))
            skill_down = self.finger_event(pygame.FINGERDOWN, *skill_coords, key=(0, 2))
            self.assertTrue(game.handle_mobile_finger_event(world_down))
            self.assertTrue(game.handle_mobile_finger_event(skill_down))
            self.assertTrue(game._mobile_touch_world_active)
            melee_calls = 0
            original = game.player_melee_attack

            def melee() -> None:
                nonlocal melee_calls
                melee_calls += 1
                original()

            game.player_melee_attack = melee  # type: ignore[assignment]
            self.assertTrue(game.handle_mobile_finger_event(skill_down))
            self.assertEqual(melee_calls, 1)

    def test_mobile_runtime_disables_sdl_accelerometer_joystick_hint(self) -> None:
        with patch.dict(os.environ, {"SDL_ACCELEROMETER_AS_JOYSTICK": "1"}):
            with tempfile.TemporaryDirectory() as tmpdir:
                game = make_mobile_game(tmpdir, (1280, 720))
                self.assertEqual(os.environ["SDL_ACCELEROMETER_AS_JOYSTICK"], "0")
                self.assertTrue(game.input.ignore_motion_sensors)

    def test_safe_area_title_row_tap_uses_rendered_hitbox(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(
                tmpdir, (1280, 720), insets=(48, 12, 24, 16)
            )
            game.state = "title"
            game.draw()
            local_row = game._title_row_rects[2]
            global_point = (
                local_row.centerx + game.mobile_safe_rect().x,
                local_row.centery + game.mobile_safe_rect().y,
            )
            size = game._mobile_display_surface().get_size()
            coords = self.normalized(global_point, size)
            self.assertTrue(
                game.handle_mobile_finger_event(
                    self.finger_event(pygame.FINGERDOWN, *coords, key=(0, 48))
                )
            )
            self.assertTrue(
                game.handle_mobile_finger_event(
                    self.finger_event(pygame.FINGERUP, *coords, key=(0, 48))
                )
            )
            self.assertEqual(game.state, "options")

    def test_options_horizontal_swipe_changes_the_touched_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            game.state = "options"
            game._options_visible_range = (3, 5)
            game._menu_row_rects = (
                pygame.Rect(100, 100, 500, 50),
                pygame.Rect(100, 160, 500, 50),
            )
            with patch.object(game, "_activate_options_row") as activate:
                self.swipe(game, (450, 185), (250, 185))
            self.assertEqual(game.options_cursor, 4)
            activate.assert_called_once_with(4, True)

    def test_short_drag_between_rows_never_activates_release_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            game.state = "controls"
            game._menu_row_rects = (
                pygame.Rect(180, 100, 640, 43),
                pygame.Rect(180, 143, 640, 43),
            )
            with patch.object(game, "_dispatch_command") as dispatch:
                self.swipe(game, (300, 120), (300, 164), key=(0, 46))
            dispatch.assert_not_called()

    def test_options_swipe_outside_rows_does_not_change_a_setting(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            game.state = "options"
            game.options_cursor = game.OPTIONS_ROW_AUDIO
            game._menu_row_rects = (pygame.Rect(180, 100, 640, 50),)
            with patch.object(game, "_activate_options_row") as activate:
                self.swipe(game, (900, 400), (650, 400), key=(0, 47))
            activate.assert_not_called()
            self.assertEqual(game.options_cursor, game.OPTIONS_ROW_AUDIO)

    def test_inventory_rows_and_horizontal_swipes_replace_helper_buttons(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            game.inventory_open = True
            game.inventory_scroll = 0
            game.inventory_cursor = 0
            game._inventory_visible_row_rects = [pygame.Rect(180, 160, 640, 54)]

            with patch.object(game, "use_selected_inventory_slot") as use_item:
                self.assertTrue(game.handle_mobile_tap((300, 180)))
                use_item.assert_not_called()
                self.assertTrue(game.handle_mobile_tap((300, 180)))
            use_item.assert_called_once_with()

            with patch.object(game, "drop_selected_inventory_slot") as drop_item:
                self.swipe(game, (600, 185), (380, 185), key=(0, 42))
            drop_item.assert_called_once_with()

            before = game.inventory_sort_mode
            with patch.object(
                game,
                "cycle_inventory_sort_mode",
                wraps=game.cycle_inventory_sort_mode,
            ) as sort_inventory:
                self.swipe(game, (380, 185), (600, 185), key=(0, 43))
            sort_inventory.assert_called_once_with()
            self.assertNotEqual(game.inventory_sort_mode, before)

    def test_shop_rows_mode_tabs_and_swipes_replace_helper_buttons(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            game.shop_open = True
            game.shop_cursor = 0
            game.shop_mode = "buy"
            game._shop_visible_start = 0
            game._shop_visible_row_rects = [pygame.Rect(180, 220, 640, 52)]
            game._shop_mode_rects = (
                pygame.Rect(180, 150, 310, 48),
                pygame.Rect(510, 150, 310, 48),
            )

            with patch.object(game, "transact_shop_selection") as transact:
                self.assertTrue(game.handle_mobile_tap((300, 240)))
                transact.assert_not_called()
                self.assertTrue(game.handle_mobile_tap((300, 240)))
            transact.assert_called_once_with()

            self.assertTrue(game.handle_mobile_tap((620, 170)))
            self.assertEqual(game.shop_mode, "sell")
            self.swipe(game, (600, 240), (820, 240), key=(0, 44))
            self.assertEqual(game.shop_mode, "buy")

    def test_character_tab_taps_and_swipes_replace_helper_buttons(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            game.character_menu_open = True
            game.character_menu_tab = "overview"
            game._character_tab_rects = (
                pygame.Rect(180, 120, 300, 52),
                pygame.Rect(500, 120, 300, 52),
            )

            self.assertTrue(game.handle_mobile_tap((620, 145)))
            self.assertEqual(game.character_menu_tab, "disciplines")
            self.swipe(game, (600, 300), (820, 300), key=(0, 45))
            self.assertEqual(game.character_menu_tab, "overview")

    def test_overview_ignores_stale_discipline_hitboxes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            game.character_menu_open = True
            game.character_menu_tab = "overview"
            game._discipline_cells = {
                "arcanist_splinter": pygame.Rect(180, 220, 160, 80)
            }
            with patch.object(game, "choose_discipline") as choose:
                self.assertFalse(game.handle_mobile_tap((220, 250)))
            choose.assert_not_called()

    def test_story_intro_choice_and_choice_free_cutscene_are_tappable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            game.story_intro_pending = True
            game._story_intro_choice_rects = [pygame.Rect(180, 300, 640, 52)]
            choices = [("relic", "Relic", "Detail")]
            with (
                patch.object(game, "story_relic_choice_options", return_value=choices),
                patch.object(game, "choose_story_relic_path") as choose,
            ):
                self.assertTrue(game.handle_mobile_tap((300, 320)))
            choose.assert_called_once_with(0)

            game.story_intro_pending = False
            game.active_cutscene = object()  # type: ignore[assignment]
            with (
                patch.object(
                    game, "active_cutscene_narration_complete", return_value=True
                ),
                patch.object(game, "active_cutscene_choices", return_value=[]),
                patch.object(game, "advance_active_cutscene") as advance,
            ):
                self.assertTrue(game.handle_mobile_tap((300, 320)))
            advance.assert_called_once_with()

    def test_actionable_tooltip_tap_dispatches_interaction(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            game.draw()
            prompt = game._interaction_prompt_rect
            self.assertIsInstance(prompt, pygame.Rect)
            assert isinstance(prompt, pygame.Rect)
            point = prompt.move(game.mobile_world_viewport().topleft).center
            size = game._mobile_display_surface().get_size()

            with patch.object(game, "interact") as interact:
                handled = game.handle_mobile_finger_event(
                    self.finger_event(
                        pygame.FINGERDOWN,
                        *self.normalized(point, size),
                        key=(0, 70),
                    )
                )
            self.assertTrue(handled)
            interact.assert_called_once_with()

    def test_exit_hub_row_opens_existing_exit_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            self.assertTrue(game._dispatch_command(Command.MOBILE_MENU))
            game.draw()
            exit_rect = next(
                rect
                for name, rect in game.mobile_layout().hub_option_rects
                if name == "exit"
            )
            size = game._mobile_display_surface().get_size()
            self.assertTrue(
                game.handle_mobile_finger_event(
                    self.finger_event(
                        pygame.FINGERDOWN,
                        *self.normalized(exit_rect.center, size),
                        key=(0, 71),
                    )
                )
            )
            self.assertEqual(game.state, "confirm_exit")
            self.assertFalse(game.mobile_hub_open)

    def test_opening_inventory_from_hub_cancels_world_contact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            game.draw()
            layout = game.mobile_layout()
            size = game._mobile_display_surface().get_size()
            world = self.normalized(layout.world_viewport.center, size)
            menu = self.normalized(layout.menu_rect.center, size)

            self.assertTrue(
                game.handle_mobile_finger_event(
                    self.finger_event(pygame.FINGERDOWN, *world, key=(0, 8))
                )
            )
            self.assertTrue(game._mobile_touch_world_active)
            self.assertTrue(
                game.handle_mobile_finger_event(
                    self.finger_event(pygame.FINGERDOWN, *menu, key=(0, 9))
                )
            )
            self.assertTrue(game.mobile_hub_open)
            self.assertFalse(game._mobile_touch_world_active)

            game.draw()
            inventory_rect = next(
                rect for name, rect in layout.hub_option_rects if name == "inventory"
            )
            inventory = self.normalized(inventory_rect.center, size)
            self.assertTrue(
                game.handle_mobile_finger_event(
                    self.finger_event(pygame.FINGERDOWN, *inventory, key=(0, 10))
                )
            )
            self.assertTrue(game.inventory_open)
            self.assertFalse(game.mobile_hub_open)


class MobileBackAndPauseTests(unittest.TestCase):
    @staticmethod
    def send_android_back(game: Game) -> None:
        back = pygame.event.Event(
            pygame.KEYDOWN,
            key=getattr(pygame, "K_AC_BACK", -1),
            mod=0,
        )
        with patch.object(pygame.event, "get", return_value=[back]):
            game.handle_events()

    def test_android_back_pauses_base_gameplay(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            self.assertEqual(game.state, "playing")
            self.send_android_back(game)
            self.assertEqual(game.state, "confirm_exit")

    def test_android_back_closes_mobile_overlays_and_submenus(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))

            game.mobile_hub_open = True
            self.send_android_back(game)
            self.assertFalse(game.mobile_hub_open)
            self.assertEqual(game.state, "playing")

            game.quest_info_visible = True
            self.send_android_back(game)
            self.assertFalse(game.quest_info_visible)
            self.assertEqual(game.state, "playing")

            game.inventory_open = True
            self.send_android_back(game)
            self.assertFalse(game.inventory_open)
            self.assertEqual(game.state, "playing")

            game.character_menu_open = True
            self.send_android_back(game)
            self.assertFalse(game.character_menu_open)
            self.assertEqual(game.state, "playing")

            game.shop_open = True
            self.send_android_back(game)
            self.assertFalse(game.shop_open)
            self.assertEqual(game.state, "playing")

            game.show_help = True
            self.send_android_back(game)
            self.assertFalse(game.show_help)
            self.assertEqual(game.state, "playing")

            game.state = "options"
            self.send_android_back(game)
            self.assertEqual(game.state, "title")

            game.state = "controls"
            game.controls_capture_command = Command.ABILITY_1
            self.send_android_back(game)
            self.assertEqual(game.state, "controls")
            self.assertIsNone(game.controls_capture_command)
            self.send_android_back(game)
            self.assertEqual(game.state, "options")

            game.state = "dead"
            self.send_android_back(game)
            self.assertEqual(game.state, "archetype_select")

    def test_android_back_never_commits_story_intro_choice(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            game.state = "playing"
            game.story_intro_pending = True
            self.send_android_back(game)
            self.assertEqual(game.state, "confirm_exit")
            self.assertTrue(game.story_intro_pending)


if __name__ == "__main__":
    unittest.main()