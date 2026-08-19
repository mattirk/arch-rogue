from __future__ import annotations

import io
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame

from arch_rogue.constants import (
    GRAPHICS_TIER_HD,
    GRAPHICS_TIER_MODERN,
    TILE_H,
    TILE_W,
)
from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game
from arch_rogue.models import LightSource, Tile


class NativeZoomPipelineTests(unittest.TestCase):
    """Plan 2 contract for native-resolution world rendering.

    Camera zoom stays continuous, while world rasterization uses four bounded
    resolution buckets.  These tests deliberately validate output behavior as
    well as the small bucket-selection seam: geometry, fog, lights, actors and
    painter order must not change meaning when the raster resolution changes.
    """

    BUCKETS = (0.8, 1.0, 1.2, 1.4, 1.6)
    CAMERA_ZOOMS = (0.65, 0.8, 1.0, 1.2, 1.4, 1.6)
    BACKGROUND = (10, 10, 14)

    def make_game(
        self,
        tmpdir: str,
        *,
        mobile: bool = False,
        size: tuple[int, int] = (960, 540),
    ) -> Game:
        game = Game(
            screen_size=size,
            headless=True,
            save_path=Path(tmpdir) / "run.json",
            mobile=mobile,
            safe_insets=(0, 0, 0, 0),
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.rng.seed(49210)
        game.restart(ARCHETYPES[0])
        if game.story_intro_pending:
            self.assertTrue(game.choose_story_relic_path(0))
        game.active_cutscene = None
        game.snap_camera_to_player()
        # Tests request only the surfaces they inspect. Avoid making every
        # bucket transition prewarm the complete themed tile family.
        game.eager_tile_prewarm = False
        return game

    @staticmethod
    def alpha_bytes(surface: pygame.Surface) -> bytes:
        return pygame.image.tobytes(surface, "RGBA")[3::4]

    @staticmethod
    def non_background_bounds(
        surface: pygame.Surface, background: tuple[int, int, int]
    ) -> pygame.Rect:
        width, height = surface.get_size()
        pixels = pygame.image.tobytes(surface, "RGB")
        min_x, min_y = width, height
        max_x = max_y = -1
        background_bytes = bytes(background)
        for byte_index in range(0, len(pixels), 3):
            if pixels[byte_index : byte_index + 3] == background_bytes:
                continue
            pixel_index = byte_index // 3
            x = pixel_index % width
            y = pixel_index // width
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
        if max_x < min_x or max_y < min_y:
            return pygame.Rect(0, 0, 0, 0)
        return pygame.Rect(
            min_x,
            min_y,
            max_x - min_x + 1,
            max_y - min_y + 1,
        )

    @staticmethod
    def cached_world_surface_bytes(game: Game) -> int:
        """Count each live high-resolution world surface only once."""

        surfaces: dict[int, pygame.Surface] = {}
        values = getattr(game.sprites.assets._world_cache, "_values", {})
        for value in values.values():
            surface = value[0]
            surfaces[id(surface)] = surface
        for value in game.tile_cache.values():
            surface = value[0]
            surfaces[id(surface)] = surface
        for value in game.door_tile_cache.values():
            surface = value[0]
            surfaces[id(surface)] = surface
        scaled_sprites = getattr(game, "_world_scaled_sprite_cache", {})
        for value in scaled_sprites.values():
            surface = value
            if isinstance(value, tuple):
                surface = (
                    value[1]
                    if len(value) > 1 and isinstance(value[1], pygame.Surface)
                    else value[0]
                )
            if isinstance(surface, pygame.Surface):
                surfaces[id(surface)] = surface
        return sum(surface.get_pitch() * surface.get_height() for surface in surfaces.values())

    def test_bucket_contract_and_world_picking_are_invariant(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.assertEqual(game.WORLD_RENDER_SCALE_BUCKETS, self.BUCKETS)

            # Always choose the smallest native bucket that is at least as
            # detailed as the continuous camera zoom. Residual composition is
            # therefore identity or a downscale, never an upscale.
            cases = (
                (game.VIEW_ZOOM_MIN, 0.8),
                (0.8, 0.8),
                (0.8001, 1.0),
                (1.0, 1.0),
                (1.0001, 1.2),
                (1.1999, 1.2),
                (1.2001, 1.4),
                (1.3999, 1.4),
                (1.4001, 1.6),
                (game.VIEW_ZOOM_MAX, 1.6),
            )
            for zoom, expected in cases:
                with self.subTest(zoom=zoom):
                    self.assertEqual(game.world_render_scale_bucket(zoom), expected)

            origin = (game.player.x, game.player.y)
            points = (
                origin,
                (origin[0] + 0.5, origin[1] + 0.5),
                (origin[0] + 2.75, origin[1] - 1.25),
                (origin[0] - 1.5, origin[1] + 2.25),
            )
            for zoom in self.CAMERA_ZOOMS:
                with self.subTest(zoom=zoom):
                    game.set_view_zoom(zoom)
                    game._frame_cache = {}
                    self.assertEqual(
                        game.world_render_scale,
                        game.world_render_scale_bucket(zoom),
                    )
                    for wx, wy in points:
                        sx, sy = game.world_to_display(wx, wy)
                        picked_x, picked_y = game.screen_to_world(sx, sy)
                        self.assertAlmostEqual(picked_x, wx, delta=0.025)
                        self.assertAlmostEqual(picked_y, wy, delta=0.025)

                    center = game.world_to_display(*origin)
                    x_step = game.world_to_display(origin[0] + 1.0, origin[1])
                    y_step = game.world_to_display(origin[0], origin[1] + 1.0)
                    expected_half_w = TILE_W * zoom / 2.0
                    expected_half_h = TILE_H * zoom / 2.0
                    self.assertAlmostEqual(
                        x_step[0] - center[0], expected_half_w, delta=2.0
                    )
                    self.assertAlmostEqual(
                        x_step[1] - center[1], expected_half_h, delta=2.0
                    )
                    self.assertAlmostEqual(
                        y_step[0] - center[0], -expected_half_w, delta=2.0
                    )
                    self.assertAlmostEqual(
                        y_step[1] - center[1], expected_half_h, delta=2.0
                    )

    def test_max_zoom_resolves_floor_at_native_master_detail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.tile_cache.clear()
            game.sprites.assets.clear_derived_caches()

            widths: dict[float, int] = {}
            surfaces: dict[float, pygame.Surface] = {}
            for bucket in self.BUCKETS:
                game.set_view_zoom(bucket)
                surface, _anchor_x, _anchor_y = game.tile_surface(Tile.FLOOR, 0)
                bounds = surface.get_bounding_rect(min_alpha=1)
                widths[bucket] = bounds.width
                surfaces[bucket] = surface

            self.assertEqual(
                widths,
                {
                    0.8: 256,
                    1.0: 320,
                    1.2: 384,
                    1.4: 448,
                    1.6: 512,
                },
            )

            manifest_entry = game.sprites.assets.manifest["world"]["floor"]
            source_path = str(manifest_entry["variants"][0])
            resource = game.sprites.assets.root.joinpath(source_path)
            source = pygame.image.load(
                io.BytesIO(resource.read_bytes()), source_path
            ).convert_alpha()
            source_bounds = source.get_bounding_rect(min_alpha=1)
            max_surface = surfaces[1.6]
            max_bounds = max_surface.get_bounding_rect(min_alpha=1)
            self.assertEqual(max_bounds.size, source_bounds.size)
            self.assertEqual(
                self.alpha_bytes(max_surface.subsurface(max_bounds)),
                self.alpha_bytes(source.subsurface(source_bounds)),
                "maximum zoom resampled the canonical 512px floor alpha",
            )

            # Exact maximum zoom has no residual scale: rendering happens on
            # the display itself and the layer compositor is not invoked.
            game.set_view_zoom(game.VIEW_ZOOM_MAX)
            target_sizes: list[tuple[int, int]] = []
            active_scales: list[float] = []

            def draw_background() -> None:
                target_sizes.append(game.screen.get_size())
                active_scales.append(game.world_render_scale)
                game.screen.fill(self.BACKGROUND)

            with (
                patch.object(game, "draw_dungeon", side_effect=draw_background),
                patch.object(game, "draw_world_objects"),
                patch.object(game, "_shade_world"),
                patch.object(
                    game,
                    "_composite_world_layer",
                    wraps=game._composite_world_layer,
                ) as composite,
            ):
                game._frame_cache = {}
                game._render_world_target()

            self.assertEqual(target_sizes, [game.screen.get_size()])
            self.assertEqual(active_scales, [1.6])
            composite.assert_not_called()

    def test_continuous_zoom_reuses_four_bounded_asset_buckets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.tile_cache.clear()
            game.sprites.assets.clear_derived_caches()

            ids_by_bucket: dict[float, set[int]] = {
                bucket: set() for bucket in self.BUCKETS
            }
            widths_by_bucket: dict[float, set[int]] = {
                bucket: set() for bucket in self.BUCKETS
            }
            for index in range(257):
                zoom = game.VIEW_ZOOM_MIN + (
                    game.VIEW_ZOOM_MAX - game.VIEW_ZOOM_MIN
                ) * index / 256
                game.set_view_zoom(zoom)
                bucket = game.world_render_scale_bucket()
                game._activate_world_render_scale(bucket)
                surface, _anchor_x, _anchor_y = game.tile_surface(Tile.FLOOR, 0)
                ids_by_bucket[bucket].add(id(surface))
                widths_by_bucket[bucket].add(
                    surface.get_bounding_rect(min_alpha=1).width
                )

            self.assertEqual(
                widths_by_bucket,
                {
                    0.8: {256},
                    1.0: {320},
                    1.2: {384},
                    1.4: {448},
                    1.6: {512},
                },
            )
            self.assertTrue(
                all(len(surface_ids) == 1 for surface_ids in ids_by_bucket.values()),
                ids_by_bucket,
            )
            self.assertEqual(
                game.sprites.cache_stats()["world_surfaces"],
                len(self.BUCKETS),
            )
            # The front cache is discarded at a bucket boundary, so it holds
            # only the active bucket while the bounded library LRU retains all
            # four reusable derived surfaces.
            self.assertEqual(len(game.tile_cache), 1)
            self.assertLessEqual(game.sprites.cache_stats()["world_surfaces"], 192)
            game._active_world_render_scale = None

    def test_wall_and_door_cells_receive_floor_underlays_in_both_paths(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            px, py = int(game.player.x), int(game.player.y)
            coordinates = ((px - 1, py), (px, py), (px + 1, py))
            self.assertTrue(
                all(game.dungeon.in_bounds(x, y) for x, y in coordinates)
            )
            for (x, y), tile in zip(
                coordinates,
                (Tile.WALL, Tile.CLOSED_DOOR, Tile.OPEN_DOOR),
                strict=True,
            ):
                game.dungeon.tiles[x][y] = tile
                game.revealed_tiles.add((x, y))

            probe = pygame.Surface((1, 1), pygame.SRCALPHA)
            desktop_calls: list[tuple[int, int, Tile]] = []

            def desktop_entry(
                x: int, y: int, tile: Tile
            ) -> tuple[pygame.Surface, tuple[int, int]]:
                desktop_calls.append((x, y, tile))
                return probe, (0, 0)

            with (
                patch.object(
                    game,
                    "visible_bounds",
                    return_value=(px - 1, px + 1, py, py),
                ),
                patch.object(game, "tile_visibility_alpha", return_value=255),
                patch.object(game, "is_current_floor_dark", return_value=False),
                patch.object(
                    game, "_tile_blit_entry", side_effect=desktop_entry
                ),
            ):
                game._floor_blit_entries()

            expected = [
                (x, y, Tile.FLOOR)
                for x, y in sorted(
                    coordinates,
                    key=lambda point: (point[0] + point[1], point[0]),
                )
            ]
            self.assertEqual(desktop_calls, expected)

            mobile_calls: list[tuple[int, int, Tile]] = []

            def mobile_entry(
                x: int, y: int, tile: Tile
            ) -> tuple[pygame.Surface, tuple[int, int]]:
                mobile_calls.append((x, y, tile))
                return probe, (0, 0)

            with patch.object(
                game, "_tile_blit_entry", side_effect=mobile_entry
            ):
                game._mobile_floor_entries_for_tiles(set(coordinates))
            self.assertEqual(mobile_calls, expected)

    def test_painter_order_is_identical_at_every_render_bucket(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            px, py = int(game.player.x), int(game.player.y)
            game.player.x, game.player.y = px + 0.5, py + 0.5
            game.snap_camera_to_player()
            bounds = (px - 2, px + 2, py - 2, py + 2)
            for x in range(bounds[0], bounds[1] + 1):
                for y in range(bounds[2], bounds[3] + 1):
                    if game.dungeon.in_bounds(x, y):
                        game.dungeon.tiles[x][y] = Tile.FLOOR
                        game.revealed_tiles.add((x, y))
            game.dungeon.tiles[px - 1][py - 1] = Tile.WALL
            game.dungeon.tiles[px + 1][py + 1] = Tile.WALL

            for collection in (
                "items",
                "traps",
                "ambush_bells",
                "shrines",
                "secrets",
                "story_guests",
                "idle_npcs",
                "shopkeepers",
                "projectiles",
                "enemies",
                "familiars",
                "slashes",
                "impact_effects",
            ):
                getattr(game, collection).clear()

            for zoom in self.CAMERA_ZOOMS:
                with self.subTest(zoom=zoom):
                    events: list[str] = []
                    game.set_view_zoom(zoom)
                    game._frame_cache = {}

                    def record_wall_batch(
                        _target: pygame.Surface,
                        entries: list[
                            tuple[pygame.Surface, tuple[int, int]]
                        ],
                    ) -> None:
                        self.assertEqual(len(entries), 1)
                        events.append("wall")

                    with (
                        patch.object(game, "visible_bounds", return_value=bounds),
                        patch.object(game, "draw_aim_cone"),
                        patch.object(
                            game, "story_relic_target_position", return_value=None
                        ),
                        patch.object(game, "_append_gold_stack_drawables"),
                        patch.object(game, "_append_lossless_soul_prop_drawables"),
                        patch.object(game, "_append_bar_prop_drawables"),
                        patch.object(
                            game,
                            "_blit_floor_entries",
                            side_effect=record_wall_batch,
                        ),
                        patch.object(
                            game,
                            "draw_player",
                            side_effect=lambda _player: events.append("player"),
                        ),
                        patch.object(
                            game, "_draw_actor_wall_ghosts", return_value=0
                        ),
                    ):
                        game.draw_world_objects()

                    self.assertEqual(events, ["wall", "player", "wall"])

    def test_actor_scale_and_ground_anchor_are_stable_at_every_zoom(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.player.moving = False
            game.elapsed = 0.0
            metrics: dict[float, tuple[float, float, float, float]] = {}

            for zoom in self.CAMERA_ZOOMS:
                game.set_view_zoom(zoom)
                game._frame_cache = {}
                game.screen.fill(self.BACKGROUND)

                def draw_background() -> None:
                    game.screen.fill(self.BACKGROUND)

                def draw_actor() -> None:
                    game.draw_player(game.player)

                with (
                    patch.object(game, "draw_dungeon", side_effect=draw_background),
                    patch.object(game, "draw_world_objects", side_effect=draw_actor),
                    patch.object(game, "_shade_world"),
                    patch.object(game, "draw_shadow"),
                    patch.object(game, "draw_hit_flash_overlay"),
                    patch.object(game, "draw_garden_heal_glow"),
                    patch.object(
                        game,
                        "apply_lit_shading",
                        side_effect=lambda sprite, *_args, **_kwargs: sprite,
                    ),
                ):
                    game._render_world_target()

                bounds = self.non_background_bounds(game.screen, self.BACKGROUND)
                self.assertGreater(bounds.width, 0, zoom)
                self.assertGreater(bounds.height, 0, zoom)
                projected_x, projected_y = game.world_to_display(
                    game.player.x, game.player.y
                )
                metrics[zoom] = (
                    bounds.width / zoom,
                    bounds.height / zoom,
                    (bounds.centerx - projected_x) / zoom,
                    (bounds.bottom - projected_y) / zoom,
                )

            reference = metrics[1.0]
            for zoom, actual in metrics.items():
                with self.subTest(zoom=zoom):
                    for measured, expected in zip(actual, reference):
                        self.assertAlmostEqual(measured, expected, delta=3.0)

    def test_fog_and_lighting_centers_follow_display_projection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game._lighting_enabled = True
            game._lighting_normal_maps = False
            game.state = "playing"
            scale = game.light_buffer_scale()
            buffer_size = (
                game.screen.get_width() // scale,
                game.screen.get_height() // scale,
            )
            tx, ty = int(game.player.x), int(game.player.y)

            game.set_current_floor_dark(False)
            # Both light-floor fog paths must stay centered on the display
            # projection at every zoom: Modern's per-tile rect stamp exactly,
            # and HD's smooth revelation field (4.10.1) within interpolation
            # tolerance — its lone-tile stamp is a bilinear tent whose support
            # spans about one tile width.
            for tier in (GRAPHICS_TIER_MODERN, GRAPHICS_TIER_HD):
                game.graphics_tier = tier
                for zoom in self.CAMERA_ZOOMS:
                    with self.subTest(kind="fog", tier=tier, zoom=zoom):
                        game.set_view_zoom(zoom)
                        game.revealed_tiles = {(tx, ty)}
                        game._shade_post_composite = True
                        game._frame_cache = {}
                        game._fog_field_sync()
                        game.ui_elapsed = (
                            float(getattr(game, "ui_elapsed", 0.0)) + 5.0
                        )
                        game._fog_advance_easing()
                        fog = pygame.Surface(buffer_size, pygame.SRCALPHA)
                        game._stamp_ambient(fog, scale)
                        # min_alpha=8 for the smooth field: large smoothscale
                        # factors leave sub-1% filter dust across the blit, so
                        # measure the tent where its alpha is meaningful. The
                        # rect path is exact at any threshold.
                        bounds = fog.get_bounding_rect(
                            min_alpha=1
                            if tier == GRAPHICS_TIER_MODERN
                            else 8
                        )
                        projected = game.world_to_display(tx + 0.5, ty + 0.5)
                        expected_center = (
                            projected[0] // scale,
                            projected[1] // scale,
                        )
                        tile_width = max(1, int(TILE_W * zoom) // scale)
                        if tier == GRAPHICS_TIER_MODERN:
                            self.assertAlmostEqual(
                                bounds.centerx, expected_center[0], delta=1.0
                            )
                            self.assertAlmostEqual(
                                bounds.centery, expected_center[1], delta=1.0
                            )
                            self.assertEqual(bounds.width, tile_width)
                        else:
                            self.assertAlmostEqual(
                                bounds.centerx, expected_center[0], delta=2.5
                            )
                            self.assertAlmostEqual(
                                bounds.centery, expected_center[1], delta=2.5
                            )
                            # The lone tile's bilinear tent measures ~1.7 tile
                            # widths at the min_alpha=8 threshold (stable
                            # across every zoom bucket).
                            self.assertAlmostEqual(
                                bounds.width,
                                1.7 * tile_width,
                                delta=max(4.0, tile_width * 0.3),
                            )

            game.set_current_floor_dark(True)
            controlled_light = LightSource(
                x=game.player.x,
                y=game.player.y,
                radius=0.55,
                color=(255, 220, 170),
                intensity=1.0,
                ttl=None,
                max_ttl=None,
                flicker=False,
                kind="zoom_alignment_probe",
            )
            for zoom in self.CAMERA_ZOOMS:
                with self.subTest(kind="light", zoom=zoom):
                    game.set_view_zoom(zoom)
                    game._shade_post_composite = True
                    game._frame_cache = {}
                    game.reset_lighting_caches()
                    game.screen.fill((255, 255, 255))
                    # Zero the ambient: the dark wash is now a player-centered
                    # feathered ellipse (not spatially flat), so the (1,1)
                    # baseline subtraction below would fold its clipped
                    # centroid into the probe-light measurement.
                    with patch.object(
                        game, "_collect_frame_lights", return_value=[controlled_light]
                    ), patch.object(game, "_ambient_level", return_value=0.0):
                        game.draw_lighting()
                    buffer = game._light_buffer_surface
                    self.assertIsNotNone(buffer)
                    assert buffer is not None
                    baseline = sum(buffer.get_at((1, 1))[:3])
                    total_weight = weighted_x = weighted_y = 0.0
                    for y in range(buffer.get_height()):
                        for x in range(buffer.get_width()):
                            weight = max(
                                0,
                                sum(buffer.get_at((x, y))[:3]) - baseline,
                            )
                            total_weight += weight
                            weighted_x += x * weight
                            weighted_y += y * weight
                    self.assertGreater(total_weight, 0.0)
                    light_center = (
                        weighted_x / total_weight,
                        weighted_y / total_weight,
                    )
                    projected = game.world_to_display(
                        controlled_light.x, controlled_light.y
                    )
                    expected_center = (
                        projected[0] / scale,
                        projected[1] / scale,
                    )
                    self.assertLessEqual(
                        math.dist(light_center, expected_center),
                        2.5,
                    )

    def test_mobile_zoom_memory_is_bounded_and_low_memory_releases_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(
                tmpdir,
                mobile=True,
                size=(1280, 720),
            )
            viewport = game.mobile_world_viewport()
            target_areas: dict[float, int] = {}

            # Exercise both the widest camera and every exact native bucket.
            for zoom in self.CAMERA_ZOOMS:
                game.set_view_zoom(zoom)
                observed: list[tuple[int, int]] = []

                def observe_target() -> None:
                    observed.append(game.screen.get_size())
                    game.screen.fill(self.BACKGROUND)

                with (
                    patch.object(game, "draw_dungeon", side_effect=observe_target),
                    patch.object(
                        game,
                        "draw_world_objects",
                        side_effect=lambda: game.draw_player(game.player),
                    ),
                    patch.object(game, "_shade_world"),
                    patch.object(game, "draw_shadow"),
                    patch.object(game, "draw_hit_flash_overlay"),
                    patch.object(game, "draw_garden_heal_glow"),
                    patch.object(
                        game,
                        "apply_lit_shading",
                        side_effect=lambda sprite, *_args, **_kwargs: sprite,
                    ),
                ):
                    game._frame_cache = {}
                    game._render_world_view()
                self.assertEqual(len(observed), 1)
                target_areas[zoom] = observed[0][0] * observed[0][1]

            self.assertEqual(
                target_areas[game.VIEW_ZOOM_MAX],
                viewport.width * viewport.height,
            )
            self.assertLessEqual(
                max(target_areas.values()),
                math.ceil(viewport.width / 0.65)
                * math.ceil(viewport.height / 0.65),
            )

            game.tile_cache.clear()
            game.door_tile_cache.clear()
            game.sprites.assets.clear_derived_caches()
            for bucket in self.BUCKETS:
                game.set_view_zoom(bucket)
                game._activate_world_render_scale(bucket)
                for tile in (Tile.FLOOR, Tile.WALL, Tile.STAIRS):
                    for variant in range(4):
                        game.tile_surface(tile, variant)
            game._active_world_render_scale = None

            stats = game.sprites.cache_stats()
            self.assertLessEqual(stats["world_surfaces"], 192)
            self.assertLessEqual(
                stats["world_surface_bytes"],
                game.sprites.assets.WORLD_CACHE_BYTE_BUDGET,
            )
            self.assertLessEqual(
                int(getattr(game, "_world_scaled_sprite_cache_bytes", 0)),
                game.WORLD_SCALED_SPRITE_CACHE_MAX_BYTES,
            )
            self.assertLessEqual(
                self.cached_world_surface_bytes(game),
                64 * 1024 * 1024,
                "zoom-bucket world surfaces exceed the mobile 64 MiB budget",
            )

            # Mobile picking uses the safe-area viewport and must invert the
            # same continuous projection at every raster bucket.
            for zoom in self.CAMERA_ZOOMS:
                game.set_view_zoom(zoom)
                game._frame_cache = {}
                for wx, wy in (
                    (game.player.x, game.player.y),
                    (game.player.x + 1.5, game.player.y - 0.75),
                ):
                    sx, sy = game.world_to_display(wx, wy)
                    picked_x, picked_y = game.screen_to_world(sx, sy)
                    self.assertAlmostEqual(picked_x, wx, delta=0.03)
                    self.assertAlmostEqual(picked_y, wy, delta=0.03)

            game.clear_mobile_memory_caches()
            self.assertEqual(game.tile_cache, {})
            self.assertEqual(game.door_tile_cache, {})
            self.assertEqual(game.sprites.cache_stats()["world_surfaces"], 0)
            self.assertEqual(
                len(getattr(game, "_world_scaled_sprite_cache", {})),
                0,
            )
            self.assertIsNone(game._world_layer)
            self.assertIsNone(game._mobile_floor_layer_cache)


if __name__ == "__main__":
    unittest.main()
