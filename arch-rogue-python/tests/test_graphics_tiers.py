from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame

from arch_rogue.constants import (
    GRAPHICS_TIER_DEFAULT,
    GRAPHICS_TIER_HD,
    GRAPHICS_TIER_LABELS,
    GRAPHICS_TIER_LEGACY,
    GRAPHICS_TIER_MODERN,
    GRAPHICS_TIER_VALUES,
    TILE_H,
    TILE_W,
    WORLD_SCALE,
)
from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game
from arch_rogue.models import Tile
from arch_rogue.sprites import SpriteAtlas


MODERN_WORLD_SHA256 = {
    "floor": "e032434a28c15c853de42b9d3156184f92ca4059ddc4030497c6ed3d65d8f7b3",
    "wall": "9c1b076b04be177e139ad8ef0e76a1821596a77528cbcbb897527b839da76b13",
    "stairs": "d84b16ba2ca6f56bc2ea736df3e9116bef3a82c6faebfa7bd1d3e73b2ac2c731",
}


class GraphicsTierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode((64, 64), pygame.HIDDEN)

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

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
            eager_tile_prewarm=False,
        )
        game.options_path = Path(tmpdir) / "options.json"
        return game

    def start_game(self, tmpdir: str, *, mobile: bool = False) -> Game:
        game = self.make_game(tmpdir, mobile=mobile)
        game.rng.seed(4914)
        game.restart(ARCHETYPES[0])
        if game.story_intro_pending:
            self.assertTrue(game.choose_story_relic_path(0))
        game.active_cutscene = None
        game.story_intro_pending = False
        game.state = "playing"
        game._lighting_enabled = False
        game.set_view_zoom(1.0)
        game.snap_camera_to_player()
        return game

    def test_fresh_default_labels_and_order_are_exact(self) -> None:
        self.assertEqual(GRAPHICS_TIER_DEFAULT, GRAPHICS_TIER_HD)
        self.assertEqual(
            GRAPHICS_TIER_VALUES,
            (GRAPHICS_TIER_LEGACY, GRAPHICS_TIER_MODERN, GRAPHICS_TIER_HD),
        )
        self.assertEqual(
            GRAPHICS_TIER_LABELS,
            {
                GRAPHICS_TIER_LEGACY: "Legacy",
                GRAPHICS_TIER_MODERN: "Modern",
                GRAPHICS_TIER_HD: "HD",
            },
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.assertEqual(game.graphics_tier, GRAPHICS_TIER_HD)
            self.assertEqual(game.graphics_tier_label(), "HD")
            self.assertEqual(game.sprites.graphics_tier, GRAPHICS_TIER_HD)
            self.assertFalse(game.legacy_graphics)

    def test_old_binary_options_migrate_to_the_matching_historical_tier(
        self,
    ) -> None:
        cases = (
            ({"legacy_graphics": True}, GRAPHICS_TIER_LEGACY),
            ({"legacy_graphics": False}, GRAPHICS_TIER_MODERN),
            ({}, GRAPHICS_TIER_MODERN),
        )
        for fields, expected in cases:
            with self.subTest(fields=fields), tempfile.TemporaryDirectory() as tmpdir:
                game = self.make_game(tmpdir)
                game.options_path.write_text(
                    json.dumps(
                        {"version": 1, "schema_version": 9, **fields}
                    ),
                    encoding="utf-8",
                )
                self.assertTrue(game.load_options())
                self.assertEqual(game.graphics_tier, expected)
                self.assertEqual(game.sprites.graphics_tier, expected)
                self.assertEqual(
                    game.legacy_graphics,
                    expected == GRAPHICS_TIER_LEGACY,
                )
                self.assertEqual(
                    game._authored_graphics_tier,
                    GRAPHICS_TIER_MODERN,
                )
                if expected == GRAPHICS_TIER_LEGACY:
                    # The atlas-level compatibility shim is synchronized too,
                    # not just Game's Ctrl+Alt+L path.
                    game.sprites.set_legacy_graphics(False)
                    self.assertEqual(
                        game.sprites.graphics_tier,
                        GRAPHICS_TIER_MODERN,
                    )

    def test_schema_10_round_trip_and_run_save_exclusion(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.start_game(tmpdir)
            reloaded = self.make_game(tmpdir)
            reloaded.options_path = game.options_path

            for tier in GRAPHICS_TIER_VALUES:
                with self.subTest(tier=tier):
                    game.set_graphics_tier(tier)
                    saved = json.loads(
                        game.options_path.read_text(encoding="utf-8")
                    )
                    self.assertEqual(saved["schema_version"], 10)
                    self.assertEqual(saved["graphics_tier"], tier)
                    self.assertEqual(
                        saved["legacy_graphics"],
                        tier == GRAPHICS_TIER_LEGACY,
                    )
                    self.assertTrue(reloaded.load_options())
                    self.assertEqual(reloaded.graphics_tier, tier)
                    self.assertEqual(reloaded.sprites.graphics_tier, tier)

            run_data = game.serialize_run_state()
            encoded = json.dumps(run_data)
            for option_key in (
                "graphics_tier",
                "authored_graphics_tier",
                "legacy_graphics",
            ):
                self.assertNotIn(option_key, run_data)
                self.assertNotIn(f'"{option_key}"', encoded)

    def test_forward_reverse_cycle_and_legacy_shim_restore_authored_tier(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.set_graphics_tier(GRAPHICS_TIER_LEGACY)

            forward = [game.graphics_tier]
            for _ in range(3):
                game.cycle_graphics_tier(True)
                forward.append(game.graphics_tier)
            self.assertEqual(
                forward,
                [
                    GRAPHICS_TIER_LEGACY,
                    GRAPHICS_TIER_MODERN,
                    GRAPHICS_TIER_HD,
                    GRAPHICS_TIER_LEGACY,
                ],
            )

            reverse = [game.graphics_tier]
            for _ in range(3):
                game.cycle_graphics_tier(False)
                reverse.append(game.graphics_tier)
            self.assertEqual(
                reverse,
                [
                    GRAPHICS_TIER_LEGACY,
                    GRAPHICS_TIER_HD,
                    GRAPHICS_TIER_MODERN,
                    GRAPHICS_TIER_LEGACY,
                ],
            )

            for authored in (GRAPHICS_TIER_MODERN, GRAPHICS_TIER_HD):
                with self.subTest(authored=authored):
                    game.set_graphics_tier(authored)
                    game.set_legacy_graphics(True)
                    self.assertEqual(game.graphics_tier, GRAPHICS_TIER_LEGACY)
                    game.set_legacy_graphics(False)
                    self.assertEqual(game.graphics_tier, authored)
                    self.assertEqual(game.sprites.graphics_tier, authored)

    def test_sprite_atlas_selects_modern_hd_and_procedural_sources(self) -> None:
        atlas = SpriteAtlas(graphics_tier=GRAPHICS_TIER_MODERN)
        self.assertTrue(atlas.assets.available, atlas.assets.load_error)
        self.assertFalse(
            atlas.assets.modern_world_load_error,
            atlas.assets.modern_world_load_error,
        )

        def source_size(key: str) -> tuple[str, tuple[int, int]]:
            entry = atlas.assets._active_world_manifest()[key]
            path = str(entry["path"])
            source = atlas.assets._source_surface(path)
            self.assertIsNotNone(source, path)
            assert source is not None
            return path, source.get_size()

        modern_floor = source_size("floor")
        modern_wall = source_size("wall")
        modern_door = source_size("door_closed")
        self.assertTrue(modern_floor[0].startswith("world/modern/"))
        self.assertTrue(atlas.modern_world_active)
        self.assertEqual(modern_floor[1], (64, 64))
        self.assertEqual(modern_wall[1], (68, 68))
        self.assertEqual(modern_door[1], (68, 68))
        for key, expected_hash in MODERN_WORLD_SHA256.items():
            with self.subTest(modern_asset=key):
                path = str(atlas.assets._active_world_manifest()[key]["path"])
                resource = atlas.assets.root.joinpath(path)
                self.assertEqual(
                    hashlib.sha256(resource.read_bytes()).hexdigest(),
                    expected_hash,
                )
        active_paths: set[str] = set()
        for entry in atlas.assets._active_world_manifest().values():
            for field in ("path", "frames", "variants", "overlay_frames"):
                value = entry.get(field)
                if isinstance(value, str):
                    active_paths.add(value)
                elif isinstance(value, list):
                    active_paths.update(str(path) for path in value)
        active_digest = hashlib.sha256()
        for path in sorted(active_paths):
            active_digest.update(path.encode("utf-8"))
            active_digest.update(b"\0")
            active_digest.update(atlas.assets._resource(path).read_bytes())
        self.assertEqual(len(active_paths), 35)
        self.assertEqual(
            active_digest.hexdigest(),
            "efd4943a115416a8f8cb56308f4f3e738e3f22d3bcba6edaf194d8a2940745ff",
        )
        self.assertTrue(
            atlas.player_visual("Warden", "idle", 0.0, 0.0).is_asset
        )

        atlas.set_graphics_tier(GRAPHICS_TIER_HD)
        self.assertFalse(atlas.modern_world_active)
        self.assertTrue(atlas.hd_graphics_active)
        for key in ("floor", "wall", "door_closed"):
            path, size = source_size(key)
            self.assertTrue(path.startswith("world/hd/"))
            self.assertEqual(size, (512, 512))
        self.assertTrue(
            atlas.player_visual("Warden", "idle", 0.0, 0.0).is_asset
        )

        atlas.set_graphics_tier(GRAPHICS_TIER_LEGACY)
        self.assertFalse(
            atlas.player_visual("Warden", "idle", 0.0, 0.0).is_asset
        )
        self.assertIsNone(
            atlas.world_tile_surface(
                "floor",
                target_canvas=(360, 360),
                target_anchor=(180, 220),
                tint=(100, 100, 110),
                accent=(150, 90, 180),
                variant=0,
            )
        )

    def test_only_hd_uses_native_world_render_buckets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            for tier in (GRAPHICS_TIER_LEGACY, GRAPHICS_TIER_MODERN):
                game.set_graphics_tier(tier)
                self.assertEqual(
                    [game.world_render_scale_bucket(z) for z in (0.65, 1.0, 1.6)],
                    [1.0, 1.0, 1.0],
                )

            game.set_graphics_tier(GRAPHICS_TIER_HD)
            self.assertEqual(
                [
                    game.world_render_scale_bucket(z)
                    for z in (0.65, 0.8, 1.0, 1.01, 1.2, 1.21, 1.4, 1.41, 1.6)
                ],
                [0.8, 0.8, 1.0, 1.2, 1.2, 1.4, 1.4, 1.6, 1.6],
            )
            del game.graphics_tier
            game.legacy_graphics = True
            self.assertEqual(game.world_render_scale_bucket(1.6), 1.0)

    def test_compatibility_tiers_keep_master_world_layout_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.start_game(tmpdir)
            coordinates = ((0, 0), (1, 7), (13, 29), (41, 5))
            old_seed = lambda x, y: (
                (x * 73856093) ^ (y * 19349663)
            ) % 4
            for tier in (GRAPHICS_TIER_LEGACY, GRAPHICS_TIER_MODERN):
                game.set_graphics_tier(tier)
                self.assertEqual(
                    [game.tile_seed(x, y) for x, y in coordinates],
                    [old_seed(x, y) for x, y in coordinates],
                )

            margin = 4 * WORLD_SCALE
            game.set_graphics_tier(GRAPHICS_TIER_MODERN)
            modern_special = game.tile_surface(
                Tile.FLOOR,
                0,
                special_floor_kind="bar",
            )[0]
            self.assertEqual(
                modern_special.get_size(),
                (TILE_W + margin * 2, TILE_H + margin * 2),
            )
            game.set_graphics_tier(GRAPHICS_TIER_HD)
            hd_special = game.tile_surface(
                Tile.FLOOR,
                0,
                special_floor_kind="bar",
            )[0]
            self.assertEqual(
                hd_special.get_size(),
                (TILE_W + margin * 2, TILE_W + margin * 2),
            )

            original_tiles = (
                game.dungeon.tiles[0][0],
                game.dungeon.tiles[1][0],
            )
            game.dungeon.tiles[0][0] = Tile.WALL
            game.dungeon.tiles[1][0] = Tile.FLOOR
            game.revealed_tiles.update(((0, 0), (1, 0)))
            try:
                for tier, expected_calls in (
                    (GRAPHICS_TIER_MODERN, 1),
                    (GRAPHICS_TIER_HD, 2),
                ):
                    game.set_graphics_tier(tier)
                    calls: list[Tile] = []

                    def record_entry(
                        _x: int, _y: int, tile: Tile
                    ) -> None:
                        calls.append(tile)
                        return None

                    with (
                        mock.patch.object(
                            game,
                            "visible_bounds",
                            return_value=(0, 1, 0, 0),
                        ),
                        mock.patch.object(
                            game,
                            "tile_visibility_alpha",
                            return_value=255,
                        ),
                        mock.patch.object(
                            game,
                            "_tile_blit_entry",
                            side_effect=record_entry,
                        ),
                    ):
                        game._floor_blit_entries()
                    self.assertEqual(len(calls), expected_calls)
                    self.assertTrue(
                        all(tile == Tile.FLOOR for tile in calls)
                    )
            finally:
                game.dungeon.tiles[0][0], game.dungeon.tiles[1][0] = (
                    original_tiles
                )

    def test_modern_world_surfaces_match_master_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.rng.seed(4914)
            game.restart(ARCHETYPES[0])
            game.active_cutscene = None
            game.story_intro_pending = False
            game.set_graphics_tier(GRAPHICS_TIER_MODERN)
            records: dict[str, str] = {}

            def record(
                name: str,
                resolved: tuple[pygame.Surface, int, int],
            ) -> None:
                surface, anchor_x, anchor_y = resolved
                digest = hashlib.sha256()
                digest.update(pygame.image.tobytes(surface, "RGBA"))
                digest.update(
                    f"{surface.get_size()}:{anchor_x}:{anchor_y}".encode(
                        "utf-8"
                    )
                )
                records[name] = digest.hexdigest()

            for seed in range(4):
                record(
                    f"floor:{seed}",
                    game.tile_surface(Tile.FLOOR, seed),
                )
                record(
                    f"wall:{seed}",
                    game.tile_surface(Tile.WALL, seed),
                )
                record(
                    f"bar-floor:{seed}",
                    game.tile_surface(
                        Tile.FLOOR,
                        seed,
                        special_floor_kind="bar",
                    ),
                )
            for frame in range(8):
                record(
                    f"stairs:{frame}",
                    game.tile_surface(
                        Tile.STAIRS,
                        1,
                        animation_frame=frame,
                    ),
                )
            for direction in ("north", "east", "south", "west"):
                record(
                    f"door:{direction}",
                    game.door_tile_surface(
                        Tile.CLOSED_DOOR,
                        2,
                        direction,
                    ),
                )

            aggregate = hashlib.sha256(
                "".join(
                    f"{key}:{records[key]}\n" for key in sorted(records)
                ).encode("utf-8")
            ).hexdigest()
            self.assertEqual(
                aggregate,
                "62881fc7f4c11a3976edbf802d404825f8a5cb997aed2d9e42a5f9a3b2848f32",
            )

    def test_switching_tier_clears_world_and_render_caches(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.start_game(tmpdir)
            game.tile_surface(Tile.FLOOR, 0)
            game.door_tile_surface(Tile.CLOSED_DOOR, 0, "north")
            normal_source = pygame.Surface((12, 12), pygame.SRCALPHA)
            normal_source.fill((120, 100, 140, 255))
            self.assertIsNotNone(game.sprites.normal_map_for(normal_source))
            self.assertGreater(
                game.sprites.cache_stats()["world_surfaces"], 0
            )
            self.assertGreater(game.sprites.cache_stats()["normal_maps"], 0)

            sentinel = pygame.Surface((2, 2), pygame.SRCALPHA)
            for name in (
                "ambient_overlay_cache",
                "_world_scaled_sprite_cache",
                "_wall_fog_gradient_cache",
                "_wall_fog_surface_cache",
                "_tile_render_descriptor_cache",
            ):
                setattr(game, name, {("sentinel",): sentinel})
            game._world_layer = sentinel
            game._mobile_floor_layer_cache = ("sentinel",)
            game._paused_scene_cache = ("sentinel",)
            game._world_scaled_sprite_cache_bytes = 16
            game._wall_fog_surface_cache_bytes = 16

            game.set_graphics_tier(GRAPHICS_TIER_MODERN)

            for name in (
                "ambient_overlay_cache",
                "_world_scaled_sprite_cache",
                "_wall_fog_gradient_cache",
                "_wall_fog_surface_cache",
                "_tile_render_descriptor_cache",
                "tile_cache",
                "door_tile_cache",
            ):
                self.assertFalse(getattr(game, name), name)
            self.assertIsNone(game._world_layer)
            self.assertIsNone(game._mobile_floor_layer_cache)
            self.assertIsNone(game._paused_scene_cache)
            self.assertEqual(game._world_scaled_sprite_cache_bytes, 0)
            self.assertEqual(game._wall_fog_surface_cache_bytes, 0)
            self.assertEqual(game.sprites.cache_stats()["world_surfaces"], 0)
            self.assertEqual(game.sprites.cache_stats()["normal_maps"], 0)

    def test_desktop_and_mobile_draw_all_tiers(self) -> None:
        for mobile in (False, True):
            with self.subTest(mobile=mobile), tempfile.TemporaryDirectory() as tmpdir:
                game = self.start_game(tmpdir, mobile=mobile)
                for tier in GRAPHICS_TIER_VALUES:
                    with self.subTest(mobile=mobile, tier=tier):
                        game.set_graphics_tier(tier)
                        game.screen.fill((0, 0, 0))
                        game.draw()
                        self.assertEqual(game.sprites.graphics_tier, tier)
                        self.assertTrue(
                            any(pygame.image.tobytes(game.screen, "RGB"))
                        )


if __name__ == "__main__":
    unittest.main()
