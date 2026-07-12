from __future__ import annotations

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

from arch_rogue import __version__
from arch_rogue.constants import (
    LIGHT_SHADE_DOWNSAMPLE_LONG,
    TILE_H,
    TILE_W,
    WORLD_SCALE,
)
from arch_rogue.content import (
    ARCHETYPES,
    BOSS_DEFINITIONS,
    ENEMY_DEFINITIONS,
    FINAL_ROOM_ENEMY_DEFINITIONS,
)
from arch_rogue.game import Game
from arch_rogue.models import Tile
from arch_rogue.sprite_assets import AssetSpriteLibrary, DIRECTIONS, SpriteAtlas


class AssetSpriteMilestone40Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode((64, 64), pygame.HIDDEN)

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def make_game(self, tmpdir: str, size: tuple[int, int] = (960, 540)) -> Game:
        game = Game(
            screen_size=size,
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.set_legacy_graphics(False)
        game.rng.seed(4000)
        game.restart(ARCHETYPES[0])
        if game.story_intro_pending:
            self.assertTrue(game.choose_story_relic_path(0))
        game.active_cutscene = None
        return game

    def test_release_and_manifest_cover_runtime_visual_roster(self) -> None:
        self.assertEqual(__version__, "4.0.0")
        library = AssetSpriteLibrary()
        self.assertTrue(library.available, library.load_error)
        manifest = library.manifest
        self.assertEqual(manifest["format_version"], 1)
        self.assertEqual(tuple(manifest["directions"]), DIRECTIONS)

        for archetype in ARCHETYPES:
            for direction in DIRECTIONS:
                frame = library.resolve_actor(
                    archetype.name, "run", direction, 0.22
                )
                self.assertIsNotNone(frame, (archetype.name, direction))
                if frame is None:
                    continue
                self.assertEqual(frame.key[3], direction)
        for definition in (*ENEMY_DEFINITIONS, *FINAL_ROOM_ENEMY_DEFINITIONS):
            frame = library.resolve_actor(
                definition.name, "idle", "south", 0.0, kind=definition.kind
            )
            self.assertIsNotNone(frame, definition.name)
        for definition in BOSS_DEFINITIONS:
            frame = library.resolve_actor(
                definition.name, "idle", "south", 0.0, kind="boss"
            )
            self.assertIsNotNone(frame, definition.name)

        self.assertEqual(
            set(manifest["items"]),
            {"potion", "mana_potion", "identify", "weapon", "armor", "story_relic"},
        )
        required_props = {
            "trap_spike",
            "trap_rune",
            "trap_poison",
            "shrine",
            "secret_cache",
            "shop_sign",
            "gold_stack",
            "ambush_bell",
        }
        self.assertTrue(required_props.issubset(manifest["props"]))
        for prop in required_props:
            self.assertIsNotNone(library.resolve_prop(prop), prop)
        self.assertTrue(
            {
                "floor",
                "wall",
                "stairs",
                "door_open",
                "door_closed",
                "shop_floor",
                "quest_floor",
                "bar_floor",
                "garden_floor",
            }.issubset(manifest["world"])
        )

    def test_directional_animation_and_resolved_frames_are_cached(self) -> None:
        atlas = SpriteAtlas()
        self.assertTrue(atlas.modern_graphics_active, atlas.assets.load_error)
        east = atlas.player_visual(
            "Warden", "run", 0.0, 0.0, direction="east"
        )
        east_again = atlas.player_visual(
            "Warden", "run", 0.0, 0.0, direction="east"
        )
        east_later = atlas.player_visual(
            "Warden", "run", 0.28, 0.28, direction="east"
        )
        west = atlas.player_visual(
            "Warden", "run", 0.0, 0.0, direction="west"
        )
        self.assertTrue(east.is_asset)
        self.assertIs(east.surface, east_again.surface)
        self.assertNotEqual(east.key, east_later.key)
        self.assertNotEqual(east.key, west.key)
        attack_start = atlas.player_visual(
            "Warden",
            "attack",
            0.0,
            0.0,
            direction="south",
            action_time=0.0,
            action_progress=0.0,
        )
        attack_recovery = atlas.player_visual(
            "Warden",
            "attack",
            0.0,
            0.0,
            direction="south",
            action_time=0.19,
            action_progress=0.95,
        )
        self.assertEqual(attack_start.key[-1], 0)
        self.assertEqual(attack_recovery.key[-1], 5)
        self.assertGreater(east.surface.get_height(), TILE_H)
        self.assertGreaterEqual(east.anchor[0], 0)
        self.assertGreaterEqual(east.anchor[1], 0)
        preview = atlas.item_preview("weapon", 36)
        self.assertIs(preview, atlas.item_preview("weapon", 36))
        wisp_idle = atlas.familiar_visual(0, 0.0, moving=False)
        wisp_idle_later = atlas.familiar_visual(0, 0.25, moving=False)
        self.assertNotEqual(wisp_idle.key, wisp_idle_later.key)
        stats = atlas.cache_stats()
        self.assertLessEqual(stats["resolved_frames"], 320)
        self.assertEqual(stats["missing_resources"], 0)

    def test_player_action_ttl_drives_the_full_authored_clip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.set_player_action_visual("attack", 0.20)
            game.update_visual_effects(0.19)
            resolved_frames = []
            resolve_player_visual = game.sprites.player_visual

            def capture_frame(*args, **kwargs):
                frame = resolve_player_visual(*args, **kwargs)
                resolved_frames.append(frame)
                return frame

            with mock.patch.object(
                game.sprites,
                "player_visual",
                side_effect=capture_frame,
            ) as player_visual:
                game.draw_player(game.player)
            self.assertAlmostEqual(game.player_action_duration, 0.20)
            self.assertAlmostEqual(game.player_action_elapsed, 0.19)
            self.assertAlmostEqual(
                player_visual.call_args.kwargs["action_progress"],
                0.95,
            )
            self.assertEqual(resolved_frames[-1].key[-1], 5)
            game.update_visual_effects(0.02)
            self.assertEqual(game.player_action_state, "")
            self.assertEqual(game.player_action_duration, 0.0)

    def test_invalid_library_and_missing_actor_frame_fall_back_independently(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            atlas = SpriteAtlas(asset_root=Path(tmpdir))
            self.assertFalse(atlas.modern_graphics_active)
            fallback = atlas.player_visual("Warden", "idle", 0.0, 0.0)
            self.assertFalse(fallback.is_asset)

        atlas = SpriteAtlas()
        warden = atlas.assets.manifest["actors"]["warden"]
        warden["clips"] = {}
        warden["rotations"] = {"south": "actors/warden/missing.png"}
        with mock.patch.object(
            atlas.assets,
            "_resource",
            wraps=atlas.assets._resource,
        ) as resource:
            with self.assertLogs("arch_rogue.sprite_assets", level="WARNING"):
                fallback = atlas.player_visual("Warden", "idle", 0.0, 0.0)
            fallback_again = atlas.player_visual("Warden", "idle", 0.0, 0.0)
        unaffected = atlas.player_visual("Rogue", "idle", 0.0, 0.0)
        self.assertFalse(fallback.is_asset)
        self.assertFalse(fallback_again.is_asset)
        self.assertEqual(resource.call_count, 1)
        self.assertTrue(unaffected.is_asset)

    def test_malformed_manifest_shape_disables_assets_without_escaping(self) -> None:
        malformed = {
            "format_version": 1,
            "actors": {
                "broken": {
                    "source_anchor": [32, 48],
                    "reference_height": 48,
                    "target_height": 96,
                    "rotations": list(DIRECTIONS),
                }
            },
            "items": {},
            "props": {},
            "world": {},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "manifest.json").write_text(
                json.dumps(malformed),
                encoding="utf-8",
            )
            library = AssetSpriteLibrary(root)
        self.assertFalse(library.available)
        self.assertIn("rotation map", library.load_error)

        malformed["actors"] = {}
        malformed["items"] = {
            "broken": {
                "path": "items/missing.png",
                "aliases": None,
            }
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "manifest.json").write_text(
                json.dumps(malformed),
                encoding="utf-8",
            )
            library = AssetSpriteLibrary(root)
        self.assertFalse(library.available)
        self.assertIn("alias list", library.load_error)

    def test_modern_world_preserves_canonical_canvases_and_legacy_toggle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            margin = 4 * WORLD_SCALE
            flat_size = (TILE_W + margin * 2, TILE_H + margin * 2)
            stair_size = (TILE_W + margin * 2, TILE_W + margin * 2)
            tall_size = (
                TILE_W + margin * 2,
                TILE_H + 48 * WORLD_SCALE + margin * 2,
            )
            floor, floor_x, floor_y = game.tile_surface(Tile.FLOOR, 0)
            wall, wall_x, wall_y = game.tile_surface(Tile.WALL, 0)
            stairs, stairs_x, stairs_y = game.tile_surface(Tile.STAIRS, 0)
            closed = game.door_tile_surface(Tile.CLOSED_DOOR, 0, "left")
            opened = game.door_tile_surface(Tile.OPEN_DOOR, 0, "left")
            self.assertEqual(floor.get_size(), flat_size)
            self.assertEqual(stairs.get_size(), stair_size)
            self.assertEqual(wall.get_size(), tall_size)
            self.assertEqual((floor_x, floor_y), (flat_size[0] // 2, margin + TILE_H // 2))
            self.assertEqual(
                (stairs_x, stairs_y),
                (stair_size[0] // 2, margin + TILE_W * 5 // 8),
            )
            self.assertEqual((wall_x, wall_y), (tall_size[0] // 2, margin + 48 * WORLD_SCALE + TILE_H // 2))
            self.assertEqual(closed[0].get_size(), tall_size)
            self.assertEqual(opened[0].get_size(), tall_size)
            self.assertNotEqual(
                pygame.image.tobytes(closed[0], "RGBA"),
                pygame.image.tobytes(opened[0], "RGBA"),
            )
            for surface in (floor, wall, stairs, closed[0], opened[0]):
                bounds = surface.get_bounding_rect(min_alpha=1)
                self.assertGreaterEqual(bounds.left, 2)
                self.assertGreaterEqual(bounds.top, 2)
                self.assertLessEqual(bounds.right, surface.get_width() - 2)
                self.assertLessEqual(bounds.bottom, surface.get_height() - 2)

            asset_player = game.sprites.player_visual("Warden", "idle", 0.0, 0.0)
            self.assertTrue(asset_player.is_asset)
            game.set_legacy_graphics(True)
            legacy_player = game.sprites.player_visual("Warden", "idle", 0.0, 0.0)
            self.assertFalse(legacy_player.is_asset)
            self.assertGreater(len(game.tile_cache), 0)

    def test_graphics_option_scrolls_persists_and_stays_out_of_run_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, (640, 480))
            game.set_legacy_graphics(True)
            options = json.loads(game.options_path.read_text(encoding="utf-8"))
            self.assertEqual(options["schema_version"], 4)
            self.assertTrue(options["legacy_graphics"])
            game.legacy_graphics = False
            self.assertTrue(game.load_options())
            self.assertTrue(game.legacy_graphics)
            self.assertTrue(game.sprites.legacy_graphics)

            run_data = game.serialize_run_state()
            self.assertEqual(run_data["version"], 5)
            self.assertNotIn("legacy_graphics", run_data)
            self.assertNotIn("sprite", json.dumps(run_data).casefold())

            game.state = "options"
            game.ui_scale = 4
            game.rebuild_fonts()
            game.options_cursor = game.OPTIONS_ROW_BACK
            game.options_scroll = 0
            game.draw()
            self.assertGreater(game.options_scroll, 0)
            self.assertLessEqual(
                game._options_visible_range[0], game.OPTIONS_ROW_BACK
            )
            self.assertGreater(
                game._options_visible_range[1], game.OPTIONS_ROW_BACK
            )
            self.assertTrue(game.screen.get_rect().contains(game._options_row_viewport))
            self.assertGreater(game._options_row_font_height, 0)
            self.assertLessEqual(game._options_row_font_height, 28)
            self.assertTrue(
                game.screen.get_rect().contains(game._options_selected_row_rect)
            )
            self.assertGreaterEqual(
                game._options_selected_row_rect.height,
                game._options_row_font_height,
            )

    def test_normal_map_cache_is_bounded_and_identity_safe(self) -> None:
        atlas = SpriteAtlas()
        for index in range(720):
            width = 12 + index % 17
            height = 13 + index % 19
            surface = pygame.Surface((width, height), pygame.SRCALPHA)
            pygame.draw.rect(
                surface,
                (80 + index % 120, 100, 140, 255),
                (1, 1, width - 2, height - 2),
            )
            normal = atlas.normal_map_for(surface)
            self.assertIsNotNone(normal)
            if normal is None:
                continue
            long_side = max(width, height)
            if long_side > LIGHT_SHADE_DOWNSAMPLE_LONG:
                factor = LIGHT_SHADE_DOWNSAMPLE_LONG / long_side
                expected = (
                    max(1, int(width * factor)),
                    max(1, int(height * factor)),
                )
            else:
                expected = (width, height)
            self.assertEqual(normal.get_size(), expected)
        self.assertLessEqual(atlas.cache_stats()["normal_maps"], 320)

    def test_full_modern_frame_renders_without_resource_misses(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.draw()
            self.assertTrue(game.sprites.modern_graphics_active)
            self.assertEqual(game.sprites.cache_stats()["missing_resources"], 0)
            self.assertGreater(len(game.tile_cache), 0)
            self.assertGreater(len(game.door_tile_cache), 0)


if __name__ == "__main__":
    unittest.main()
