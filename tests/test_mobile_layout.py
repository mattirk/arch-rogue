from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest.mock import call, patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame

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
from arch_rogue.models import Tile
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

    def test_mobile_lighting_buffer_divisor_tracks_quality_tier(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            viewport = game.mobile_world_viewport()
            for quality, divisor in (
                (MOBILE_RENDER_QUALITY_PERFORMANCE, 4),
                (MOBILE_RENDER_QUALITY_BALANCED, 3),
                (MOBILE_RENDER_QUALITY_NATIVE, 2),
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
                            max(1, viewport.width // divisor),
                            max(1, viewport.height // divisor),
                        ),
                    )
                    scratch = game._light_scratch_surface
                    self.assertIsNotNone(scratch)
                    assert scratch is not None
                    self.assertEqual(scratch.get_masks()[:3], game.screen.get_masks()[:3])

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

                game._cam_iso = (first[1] + first_surface.get_width(), first[2])
                game.draw()
                rebuilt = game._mobile_floor_layer_cache
                self.assertIsNotNone(rebuilt)
                assert rebuilt is not None
                self.assertIsNot(rebuilt[3], first_surface)

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
            monitor.begin_frame()
            monitor.record_phase("world", 0.2)
            monitor.record_phase("hud", 0.05)
            monitor.record_phase("flip", 0.7)
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
            self.assertIn("A2:1 N:yes", monitor.overlay_text)
            self.assertIn("T 0 U 0 W 200 H 50 F 700 A 0", monitor.overlay_detail_text)


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

    def test_gpu_lighting_presenter_uses_base_mod_ui_order_without_flip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (780, 360))
            game.state = "playing"
            game.screen_flash_color = (210, 48, 24)
            game.screen_flash_ttl = 0.30
            calls: list[tuple[str, object]] = []

            class FakeTexture:
                def __init__(self, label: str) -> None:
                    self.label = label
                    self.blend_mode = -1

                def update(self, surface: pygame.Surface) -> None:
                    calls.append((f"update:{self.label}", surface.get_size()))

            class FakeRenderer:
                logical_size = game.screen.get_size()
                draw_color = (0, 0, 0, 0)

                def clear(self) -> None:
                    calls.append(("clear", self.draw_color))

                def blit(self, texture: FakeTexture, rect: pygame.Rect) -> None:
                    calls.append((f"blit:{texture.label}", rect.copy()))

                def present(self) -> None:
                    calls.append(("present", None))

            labels = iter(("base", "light", "ui", "flash"))

            def make_texture(_renderer: object, _size: tuple[int, int]) -> FakeTexture:
                return FakeTexture(next(labels))

            renderer = FakeRenderer()
            game._mobile_renderer_accelerated = True
            game.configure_mobile_gpu_renderer(object(), renderer)
            with (
                patch.object(game, "_create_mobile_gpu_texture", side_effect=make_texture),
                patch("arch_rogue.rendering.base.pygame.display.flip") as flip,
            ):
                game.draw()

            self.assertFalse(flip.called)
            self.assertTrue(game._mobile_gpu_last_present)
            self.assertFalse(game.screen.get_locked())
            self.assertEqual(
                [name for name, _value in calls],
                (
                    ["update:base", "update:light", "update:ui", "update:flash"]
                    + [
                        "clear",
                        "blit:base",
                        "blit:light",
                        "blit:ui",
                        "blit:flash",
                        "present",
                    ]
                ),
            )
            self.assertIn(("update:flash", (1, 1)), calls)
            self.assertEqual(getattr(game, "_mobile_gpu_base_texture").blend_mode, 0)
            self.assertEqual(getattr(game, "_mobile_gpu_light_texture").blend_mode, 4)
            self.assertEqual(getattr(game, "_mobile_gpu_ui_texture").blend_mode, 1)
            self.assertEqual(getattr(game, "_mobile_gpu_flash_texture").blend_mode, 1)


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
                self.assertTrue(layout.safe_rect.contains(layout.world_viewport))
                self.assertFalse(layout.left_rail.colliderect(layout.world_viewport))
                self.assertFalse(layout.right_rail.colliderect(layout.world_viewport))
                self.assertEqual(layout.left_rail.width, layout.right_rail.width)
                self.assertEqual(layout.world_viewport.centerx, layout.safe_rect.centerx)
                self.assertEqual(len(layout.action_rects), 6)
                self.assertEqual(len(layout.resource_rects), 3)
                for first, second in zip(
                    layout.action_rects, layout.action_rects[1:]
                ):
                    self.assertFalse(first.colliderect(second))
                self.assertTrue(all(layout.safe_rect.contains(rect) for rect in layout.action_rects))
                self.assertTrue(layout.safe_rect.contains(layout.pause_rect))
                self.assertTrue(layout.safe_rect.contains(layout.interact_rect))

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
            self.assertIn(
                (Command.BACK, "Pause"),
                {(t.command, t.label) for t in game._mobile_touch_targets},
            )
            self.assertIn(
                (Command.INTERACT, "Interact"),
                {(t.command, t.label) for t in game._mobile_touch_targets},
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

    def test_world_finger_capture_updates_aim_and_release_stops(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            game.draw()
            viewport = game.mobile_world_viewport()
            inside = (viewport.centerx / 1280.0, viewport.centery / 720.0)
            down = self.finger_event(pygame.FINGERDOWN, *inside)
            self.assertTrue(game.handle_mobile_finger_event(down))
            self.assertTrue(game._mobile_touch_world_active)
            self.assertEqual(game.aim_input_mode, "touch")
            self.assertEqual(game.active_mobile_world_touch(), (viewport.centerx, viewport.centery))
            up = self.finger_event(pygame.FINGERUP, *inside)
            self.assertTrue(game.handle_mobile_finger_event(up))
            self.assertFalse(game._mobile_touch_world_active)
            self.assertIsNone(game.active_mobile_world_touch())

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

    def test_opening_inventory_cancels_world_contact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            game.draw()
            layout = game.mobile_layout()
            inventory = next(
                rect for name, rect in layout.utility_rects if name == "inventory"
            )
            coords = ((inventory.centerx + 0.5) / 1280.0, (inventory.centery + 0.5) / 720.0)
            world = (layout.world_viewport.centerx / 1280.0, layout.world_viewport.centery / 720.0)
            self.assertTrue(game.handle_mobile_finger_event(self.finger_event(pygame.FINGERDOWN, *world)))
            self.assertTrue(game._mobile_touch_world_active)
            self.assertTrue(game.handle_mobile_finger_event(self.finger_event(pygame.FINGERDOWN, *coords, key=(0, 9))))
            self.assertTrue(game.inventory_open)
            self.assertFalse(game._mobile_touch_world_active)


class MobileBackAndPauseTests(unittest.TestCase):
    def test_android_back_pauses_base_gameplay(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            self.assertEqual(game.state, "playing")
            back = pygame.event.Event(pygame.KEYDOWN, key=getattr(pygame, "K_AC_BACK", -1), mod=0)
            consumed = False
            pygame.event.clear()
            pygame.event.post(back)
            for event in pygame.event.get():
                if event.type == pygame.KEYDOWN and event.key == getattr(pygame, "K_AC_BACK", -1):
                    game._dispatch_command(Command.BACK)
                    consumed = True
            self.assertTrue(consumed)
            self.assertEqual(game.state, "confirm_exit")

    def test_android_back_never_commits_story_intro_choice(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            game.state = "playing"
            game.story_intro_pending = True
            game._dispatch_command(Command.BACK)
            self.assertEqual(game.state, "confirm_exit")
            self.assertTrue(game.story_intro_pending)


if __name__ == "__main__":
    unittest.main()