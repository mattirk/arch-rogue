# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
#
# AI Provenance & Liability Notice:
# This repository contains code generated, assisted, or refactored by Artificial
# Intelligence models. Provided strictly "AS IS" under Apache 2.0 with no warranty
# of clean IP provenance or non-infringement; downstream users assume all legal
# and financial risk and should perform their own compliance audits.
#
# Milestone 3.16 — Lighting overhaul.
from __future__ import annotations

# pyright: reportAttributeAccessIssue=false, reportUnknownMemberType=false
import copy
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame  # noqa: F401  (required to initialize pygame subsystems in tests)

from arch_rogue.constants import (
    DARK_LEVEL_LIGHT_RADIUS,
    DUNGEON_DEPTH,
    GRAPHICS_TIER_MODERN,
    LIGHT_AMBIENT_DARK_LEVEL,
    LIGHT_AMBIENT_DEPTH_FLOOR,
    LIGHT_AMBIENT_DEPTH_PEAK,
    LIGHT_AMBIENT_LIGHT_LEVEL,
    LIGHT_BAR_WALL_ELEVATION,
    LIGHT_LANTERN_COLOR,
    LIGHT_LEVEL_SIGHT_RADIUS,
    LIGHT_ROOM_FLASH_SPILL_DISTANCE,
    LIGHT_ROOM_FLASH_TTL,
    LIGHT_STAIRS_COLOR,
    LIGHT_STAIRS_INTENSITY,
    LIGHT_STAIRS_RADIUS,
    LIGHT_TORCH_COLOR,
    LIGHT_TORCH_INTENSITY,
    LIGHT_TORCH_RADIUS,
    TILE_H,
    TILE_W,
    WORLD_SCALE,
)
from arch_rogue.content import ARCHETYPES, SHRINE_HINTS
from arch_rogue.game import Game
from arch_rogue.rendering.lighting import bake_normal_map, hashable_color, light_radius_px
from arch_rogue.models import (
    IdleNpc,
    LightSource,
    Projectile,
    Room,
    Shopkeeper,
    StoryGuest,
    Tile,
)


class LightingTests(unittest.TestCase):
    def make_game(self, tmpdir, archetype_index=0, seed=3161) -> Game:
        game = Game(
            screen_size=(960, 600),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.rng.seed(seed)
        game.restart(ARCHETYPES[archetype_index])
        if game.story_intro_pending:
            self.assertTrue(game.choose_story_relic_path(0))
        game.active_cutscene = None
        return game

    # --- feature 1: normal-map derivation determinism -----------------
    def test_normal_map_is_deterministic_and_alpha_preserved(self) -> None:
        surf = pygame.Surface((16, 20), pygame.SRCALPHA)
        pygame.draw.rect(surf, (200, 180, 120), (4, 4, 8, 10))
        pygame.draw.rect(surf, (90, 70, 50), (6, 14, 4, 4))
        n1 = bake_normal_map(surf)
        n2 = bake_normal_map(surf)
        self.assertEqual(n1.get_size(), surf.get_size())
        # Deterministic: same pixels -> identical normal map.
        for x in range(16):
            for y in range(20):
                self.assertEqual(n1.get_at((x, y)), n2.get_at((x, y)))
        # Empty source pixels stay empty (alpha preserved as the mask).
        self.assertEqual(n1.get_at((0, 0)).a, 0)
        # Filled pixels get a real tangent-space normal (non-zero blue = facing).
        self.assertGreater(n1.get_at((8, 8)).b, 0)
        self.assertEqual(n1.get_at((8, 8)).a, 255)

    def test_normal_map_preserves_colorkey_padding(self) -> None:
        surface = pygame.Surface((12, 12), depth=32)
        key = (255, 0, 255)
        surface.fill(key)
        surface.set_colorkey(key, pygame.RLEACCEL)
        pygame.draw.rect(surface, (190, 150, 90), (3, 2, 6, 8))

        normal = bake_normal_map(surface)

        self.assertEqual(normal.get_at((0, 0)).a, 0)
        self.assertEqual(normal.get_at((5, 5)).a, 255)
        self.assertGreater(normal.get_at((5, 5)).b, 0)

    def test_normal_map_differs_for_different_pixels(self) -> None:
        a = pygame.Surface((8, 8), pygame.SRCALPHA)
        pygame.draw.rect(a, (255, 255, 255), (0, 0, 8, 8))
        b = pygame.Surface((8, 8), pygame.SRCALPHA)
        pygame.draw.rect(b, (255, 255, 255), (2, 2, 4, 4))
        na, nb = bake_normal_map(a), bake_normal_map(b)
        self.assertNotEqual(na.get_at((1, 4)), nb.get_at((1, 4)))



    # --- feature 2 + 3: light-buffer accumulation + player lantern -----
    def test_player_lantern_radius_equals_sight_radius(self) -> None:
        game = self.make_game(tempfile.mkdtemp())
        game._lighting_enabled = True
        lights = game._collect_frame_lights()
        lantern = next(lt for lt in lights if lt.kind == "lantern")
        # Dark floor reach and light-floor sight radius are identical, and the
        # lantern reuses that exact radius so combat/LOS reach is untouched.
        self.assertEqual(lantern.radius, DARK_LEVEL_LIGHT_RADIUS)
        self.assertEqual(DARK_LEVEL_LIGHT_RADIUS, LIGHT_LEVEL_SIGHT_RADIUS)
        self.assertEqual(lantern.color, LIGHT_LANTERN_COLOR)

    def test_stairs_add_one_faint_static_violet_light(self) -> None:
        game = self.make_game(tempfile.mkdtemp())
        stairs_x, stairs_y = game.dungeon.stairs
        stair_lights = [
            light for light in game.light_sources if light.kind == "stairs"
        ]
        self.assertEqual(len(stair_lights), 1)
        light = stair_lights[0]
        self.assertEqual((light.x, light.y), (stairs_x + 0.5, stairs_y + 0.5))
        self.assertEqual(light.color, LIGHT_STAIRS_COLOR)
        self.assertEqual(light.radius, LIGHT_STAIRS_RADIUS)
        self.assertEqual(light.intensity, LIGHT_STAIRS_INTENSITY)
        self.assertFalse(light.flicker)
        self.assertIsNone(light.ttl)

        game._populate_light_sources()
        self.assertEqual(
            len([light for light in game.light_sources if light.kind == "stairs"]),
            1,
        )

    def test_friendly_humanoid_lanterns_follow_npcs_and_exclude_frogs(self) -> None:
        game = self.make_game(tempfile.mkdtemp())
        px, py = game.player.x, game.player.y
        shopkeeper = Shopkeeper(px + 0.3, py, "Mara", "Quartermaster")
        guest = StoryGuest(
            px,
            py + 0.3,
            game.current_depth,
            0,
            "Ilyra",
            "Witness",
            "seeks passage",
            "The stones remember.",
            [],
        )
        patron = IdleNpc(px - 0.3, py, kind="bar", name="Tovin", role="Patron")
        dancer = IdleNpc(
            px + 0.3,
            py + 0.3,
            kind="bar_dancer",
            name="Bar Dancer",
            role="Tavern Reveler",
        )
        frog = IdleNpc(
            px,
            py - 0.3,
            kind="garden_frog",
            name="Pip",
            role="Garden Dancer",
        )
        game.shopkeepers = [shopkeeper]
        game.story_guests = [guest]
        game.idle_npcs = [patron, dancer, frog]
        game.reset_friendly_npc_runtime()
        persistent_count = len(game.light_sources)
        transient_count = len(game.lights)
        game._frame_cache = {}

        lights = game._collect_frame_lights()
        player_lantern = next(light for light in lights if light.kind == "lantern")
        npc_lights = [
            light for light in lights if light.kind == "friendly_lantern"
        ]
        self.assertEqual(len(npc_lights), 4)
        self.assertEqual(
            {(light.x, light.y) for light in npc_lights},
            {
                (shopkeeper.x, shopkeeper.y),
                (guest.x, guest.y),
                (patron.x, patron.y),
                (dancer.x, dancer.y),
            },
        )
        self.assertNotIn((frog.x, frog.y), {(light.x, light.y) for light in npc_lights})
        for light in npc_lights:
            self.assertEqual(light.radius, player_lantern.radius)
            self.assertEqual(light.color, player_lantern.color)
            self.assertEqual(light.intensity, player_lantern.intensity)
            self.assertEqual(light.flicker, player_lantern.flicker)
            self.assertIsNone(light.ttl)

        patron.x += 0.45
        game._frame_cache = {}
        moved_lights = [
            light
            for light in game._collect_frame_lights()
            if light.kind == "friendly_lantern"
        ]
        self.assertIn((patron.x, patron.y), {(light.x, light.y) for light in moved_lights})
        self.assertEqual(len(game.light_sources), persistent_count)
        self.assertEqual(len(game.lights), transient_count)

    def test_light_buffer_accumulates_additively(self) -> None:
        game = self.make_game(tempfile.mkdtemp())
        game._lighting_enabled = True
        sx, sy = game.world_to_screen(game.player.x, game.player.y)
        scale = 2  # LIGHT_BUFFER_SCALE

        def stamp(light: LightSource) -> tuple[int, int, int]:
            sw, sh = game._screen_size()
            buf = game._light_buffer(max(1, sw // scale), max(1, sh // scale))
            buf.fill((0, 0, 0, 0))
            sprite = game._radial_light_sprite(
                light_radius_px(light.radius), light.color
            )
            buf.blit(
                sprite,
                (sx // scale - sprite.get_width() // 2,
                 sy // scale - sprite.get_height() // 2),
                special_flags=pygame.BLEND_RGBA_ADD,
            )
            c = buf.get_at((sx // scale, sy // scale))
            return (c.r, c.g, c.b)

        a = LightSource(game.player.x, game.player.y, 2.0, (200, 60, 60), 0.8)
        b = LightSource(game.player.x, game.player.y, 2.0, (60, 200, 60), 0.8)
        va, vb = stamp(a), stamp(b)
        # Combine both into one buffer to confirm additive accumulation.
        sw, sh = game._screen_size()
        buf = game._light_buffer(max(1, sw // scale), max(1, sh // scale))
        buf.fill((0, 0, 0, 0))
        for light in (a, b):
            sprite = game._radial_light_sprite(
                light_radius_px(light.radius), light.color
            )
            buf.blit(
                sprite,
                (sx // scale - sprite.get_width() // 2,
                 sy // scale - sprite.get_height() // 2),
                special_flags=pygame.BLEND_RGBA_ADD,
            )
        cc = buf.get_at((sx // scale, sy // scale))
        combined = (cc.r, cc.g, cc.b)
        for ch in range(3):
            self.assertGreaterEqual(combined[ch], max(va[ch], vb[ch]))

    # --- feature 4: skill pulse timing/tint per archetype --------------
    def test_skill_pulse_emitted_on_cast_with_archetype_tint(self) -> None:
        for idx, _name in enumerate(("Warden", "Rogue", "Arcanist", "Acolyte", "Ranger")):
            game = self.make_game(tempfile.mkdtemp(), archetype_index=idx)
            game.lights = []
            color = game.skill_color()
            game.add_impact(game.player.x, game.player.y, color, kind="cast")
            self.assertEqual(len(game.lights), 1)
            pulse = game.lights[0]
            self.assertEqual(pulse.color, color)
            self.assertIsNotNone(pulse.max_ttl)
            assert pulse.max_ttl is not None
            self.assertGreater(pulse.max_ttl, 0.0)
            # The pulse decays frame by frame and is removed once expired.
            start = pulse.ttl
            assert start is not None
            game.update_lights(0.01)
            assert game.lights[0].ttl is not None
            self.assertLess(game.lights[0].ttl, start)
            game.lights[0].ttl = 0.001
            game.update_lights(0.01)
            self.assertEqual(len(game.lights), 0)

    def test_projectile_light_follows_path(self) -> None:
        game = self.make_game(tempfile.mkdtemp())
        game.lights = []
        game.enemies = []
        proj = Projectile(
            x=game.player.x + 0.4,
            y=game.player.y,
            vx=8.0,
            vy=0.0,
            damage=5,
            owner="player",
            color=(160, 118, 245),
            damage_type="arcane",
            pierce=2,
        )
        game.projectiles = [proj]
        game.update_projectiles(0.05)
        projectile_lights = [light for light in game.lights if light.kind == "projectile"]
        self.assertEqual(len(projectile_lights), 1)
        first = projectile_lights[0]
        first_x = first.x
        self.assertIs(proj.light_source, first)
        self.assertEqual(first.color, proj.color)

        game.update_lights(0.05)
        game.update_projectiles(0.05)
        projectile_lights = [light for light in game.lights if light.kind == "projectile"]
        self.assertEqual(len(projectile_lights), 1)
        self.assertIs(projectile_lights[0], first)
        self.assertGreater(first.x, first_x)

        # Once the projectile is gone, its unrefreshed light decays normally.
        game.projectiles = []
        game.update_lights(1.0)
        self.assertNotIn(first, game.lights)

    def test_offscreen_transient_lights_are_not_collected_for_rendering(self) -> None:
        game = self.make_game(tempfile.mkdtemp())
        game.lights = []
        near = game.add_light(
            game.player.x + 1.0,
            game.player.y,
            1.5,
            (220, 140, 90),
            ttl=0.3,
        )
        far = game.add_light(
            game.player.x + 1_000.0,
            game.player.y + 1_000.0,
            1.5,
            (220, 140, 90),
            ttl=0.3,
        )
        game._frame_cache = {}
        collected = game._collect_frame_lights()
        self.assertTrue(any(light is near for light in collected))
        self.assertFalse(any(light is far for light in collected))
        self.assertEqual(len(game.lights), 2)

    # --- feature 5: theme ambient tint ---------------------------------
    def test_theme_ambient_tint_uses_theme_accent(self) -> None:
        game = self.make_game(tempfile.mkdtemp())
        game._lighting_enabled = True
        theme_color = game._theme_light_color()
        # Ambient light is white tinted ~35% toward the theme accent.
        for ch in range(3):
            expected = int(255 * 0.65 + game.theme.accent[ch] * 0.35)
            self.assertAlmostEqual(theme_color[ch], expected, delta=1)
        # Dark floors use a much dimmer ambient than light floors.
        light_ambient = game._ambient_level()
        game.set_current_floor_dark(True)
        self.assertLess(game._ambient_level(), light_ambient)

    def test_light_floor_ambient_brightens_near_surface_and_darkens_with_depth(self) -> None:
        # The depth brightness gradient is a separate axis from the dark-floor
        # flag: light floors (fog-of-war memory) are brighter at depth 1 and
        # gradually darken toward the deepest floor.
        game = self.make_game(tempfile.mkdtemp())
        game._lighting_enabled = True
        game.current_depth = 1
        game._frame_cache = {}
        self.assertAlmostEqual(
            game._ambient_depth_factor(), LIGHT_AMBIENT_DEPTH_PEAK, places=4
        )
        # Depth 1 light floor is brighter than the old flat level.
        self.assertGreater(game._ambient_level(), LIGHT_AMBIENT_LIGHT_LEVEL)
        game.current_depth = DUNGEON_DEPTH
        self.assertAlmostEqual(
            game._ambient_depth_factor(), LIGHT_AMBIENT_DEPTH_FLOOR, places=4
        )
        self.assertLess(game._ambient_depth_factor(), LIGHT_AMBIENT_DEPTH_PEAK)
        # Dark floors keep a constant ambient regardless of depth (dark-levels
        # logic intact); the gradient only applies to light floors.
        game.current_depth = 1
        game._frame_cache = {}
        game.set_current_floor_dark(True)
        self.assertEqual(game._ambient_level(), LIGHT_AMBIENT_DARK_LEVEL)
        game.current_depth = DUNGEON_DEPTH
        game.set_current_floor_dark(True)
        self.assertEqual(game._ambient_level(), LIGHT_AMBIENT_DARK_LEVEL)
        self.assertTrue(game.is_current_floor_dark())

    # --- feature 7: static torch/shrine lights ------------------------
    def test_static_shrine_and_bar_wall_lights_populated(self) -> None:
        game = self.make_game(tempfile.mkdtemp(), archetype_index=2, seed=3001)
        # Shrines always become light sources tinted by their accent color.
        for shrine in game.shrines:
            matches = [
                source
                for source in game.light_sources
                if source.kind == "shrine"
                and abs(source.x - shrine.x) < 0.01
                and abs(source.y - shrine.y) < 0.01
            ]
            self.assertEqual(len(matches), 1)
            hint = SHRINE_HINTS.get(shrine.kind)
            self.assertIsNotNone(hint)
            assert hint is not None
            self.assertEqual(matches[0].color, hint.color)
            self.assertFalse(matches[0].flicker)

        bar = game.dungeon.special_room_for_kind("bar")
        self.assertIsNotNone(bar)
        assert bar is not None
        room = game.dungeon.rooms[bar.room_index]
        wall_lights = [
            source for source in game.light_sources if source.kind == "bar_wall_light"
        ]
        self.assertEqual(len(wall_lights), 2)
        for side in ("left", "right"):
            wall_tile = bar.anchor(f"bar_wall_light_{side}")
            self.assertIsNotNone(wall_tile)
            assert wall_tile is not None
            self.assertEqual(game.dungeon.tiles[wall_tile[0]][wall_tile[1]], Tile.WALL)
            self.assertEqual(game.special_wall_faces(*wall_tile), f"bar:{side}")
            self.assertEqual(game.bar_wall_light_side(*wall_tile), side)
            expected_position = (
                (wall_tile[0] + 0.5, wall_tile[1] + 1.0)
                if side == "left"
                else (wall_tile[0] + 1.0, wall_tile[1] + 0.5)
            )
            source = next(
                light
                for light in wall_lights
                if abs(light.x - expected_position[0]) < 0.01
                and abs(light.y - expected_position[1]) < 0.01
            )
            self.assertEqual(source.radius, LIGHT_TORCH_RADIUS)
            self.assertEqual(source.color, LIGHT_TORCH_COLOR)
            self.assertEqual(source.intensity, LIGHT_TORCH_INTENSITY)
            self.assertEqual(source.elevation, LIGHT_BAR_WALL_ELEVATION)
            self.assertTrue(source.flicker)
            self.assertIsNone(source.ttl)

        center_x, center_y = room.center
        self.assertFalse(
            any(
                source.kind == "torch"
                and abs(source.x - (center_x + 0.5)) < 0.01
                and abs(source.y - (center_y + 0.5)) < 0.01
                for source in game.light_sources
            )
        )
        before = [game.light_source_to_dict(source) for source in game.light_sources]
        rng_state = game.rng.getstate()
        game._populate_light_sources()
        self.assertEqual(
            [game.light_source_to_dict(source) for source in game.light_sources], before
        )
        self.assertEqual(game.rng.getstate(), rng_state)

    # --- feature 8: quality-tier toggle fallback to 3.8.0 model --------
    def test_lighting_off_keeps_per_tile_alpha_quantization(self) -> None:
        game = self.make_game(tempfile.mkdtemp())
        game.set_current_floor_dark(True)
        game._lighting_enabled = False
        px, py = int(game.player.x), int(game.player.y)
        alpha = game.tile_visibility_alpha(px, py)
        self.assertGreater(alpha, 0)
        if alpha < 255:
            base = game.tile_surface(Tile.FLOOR, 0, shop_floor=False)[0]
            shaded = game._alpha_tile_surface(base, alpha)
            self.assertIsNot(shaded, base)

    def test_lighting_on_skips_per_tile_alpha_quantization(self) -> None:
        game = self.make_game(tempfile.mkdtemp())
        game.set_current_floor_dark(True)
        game._lighting_enabled = True
        # On the continuous tier, a dark-floor floor tile blits fully opaque
        # (the buffer multiply does the falloff), so no alpha-bucket copy is
        # produced even when alpha < 255.
        px, py = int(game.player.x) + 2, int(game.player.y) + 2
        alpha = game.tile_visibility_alpha(px, py)
        if 0 < alpha < 255:
            entry = game._tile_blit_entry(px, py, Tile.FLOOR)
            self.assertIsNotNone(entry)
        self.assertFalse(getattr(game, "_alpha_tile_cache", None))

    def test_ambient_fog_stamp_reaches_elevated_wall_top_only(self) -> None:
        game = self.make_game(tempfile.mkdtemp())
        game.set_current_floor_dark(False)
        # The per-tile rect stamp (and its elevated wall-top extension) is the
        # Modern/Legacy light-floor path; HD routes through the smooth
        # revelation field since 4.10.1 (tests/test_smooth_fog.py).
        game.graphics_tier = GRAPHICS_TIER_MODERN
        tx, ty = int(game.player.x), int(game.player.y)
        game.revealed_tiles = {(tx, ty)}
        scale = game.light_buffer_scale()

        def stamped_bounds(tile: Tile) -> pygame.Rect:
            game.dungeon.tiles[tx][ty] = tile
            buffer = pygame.Surface((800, 800), pygame.SRCALPHA)
            with (
                patch.object(game, "visible_bounds", return_value=(tx, tx, ty, ty)),
                patch.object(
                    game,
                    "_shade_params",
                    return_value=(1.0, lambda _x, _y: (400, 400)),
                ),
            ):
                game._stamp_ambient(buffer, scale)
            return buffer.get_bounding_rect(min_alpha=1)

        floor = stamped_bounds(Tile.FLOOR)
        wall = stamped_bounds(Tile.WALL)
        door = stamped_bounds(Tile.CLOSED_DOOR)
        tile_width = TILE_W // scale
        wall_top_reach = (48 * WORLD_SCALE + TILE_H // 2) // scale
        expected_extra = wall_top_reach - tile_width // 2

        self.assertEqual(floor.size, (tile_width, tile_width))
        self.assertEqual(wall.width, floor.width)
        self.assertEqual(wall.height, floor.height + expected_extra)
        self.assertEqual(wall.bottom, floor.bottom)
        self.assertEqual(wall.top, floor.top - expected_extra)
        self.assertEqual(door, wall)

    def test_draw_lighting_noop_when_disabled(self) -> None:
        game = self.make_game(tempfile.mkdtemp())
        game._lighting_enabled = False
        game.screen.fill((17, 19, 23))
        before = pygame.image.tobytes(game.screen, "RGBA")
        game.draw_lighting()
        self.assertEqual(pygame.image.tobytes(game.screen, "RGBA"), before)

    # --- save round-trip: empty LightSource list on pre-3.16 saves -----
    def test_save_round_trip_with_light_sources(self) -> None:
        game = self.make_game(tempfile.mkdtemp())
        self.assertTrue(game.save_run())
        data = copy.deepcopy(game.serialize_run_state())
        self.assertEqual(data["version"], 5)
        self.assertIn("light_sources", data)
        # Round-trip: load into a fresh game restores the static lights.
        game2 = self.make_game(tempfile.mkdtemp())
        game2.restore_run_state(data)
        self.assertEqual(
            sorted(
                (
                    source.kind,
                    source.x,
                    source.y,
                    source.radius,
                    source.elevation,
                )
                for source in game2.light_sources
            ),
            sorted(
                (
                    source.kind,
                    source.x,
                    source.y,
                    source.radius,
                    source.elevation,
                )
                for source in game.light_sources
            ),
        )
        # Transient pulses never persist.
        self.assertEqual(game2.lights, [])

    def test_pre_3_16_save_backfills_current_static_light_sources(self) -> None:
        game = self.make_game(tempfile.mkdtemp())
        data = copy.deepcopy(game.serialize_run_state())
        # Simulate a pre-3.16 save that has no light_sources field.
        data.pop("light_sources", None)
        game2 = self.make_game(tempfile.mkdtemp())
        game2.restore_run_state(data)
        self.assertGreater(len(game2.light_sources), 0)
        self.assertEqual(
            len([source for source in game2.light_sources if source.kind == "shrine"]),
            len(game2.shrines),
        )
        legacy = game2.light_source_from_dict(
            {
                "x": 1.0,
                "y": 2.0,
                "radius": 2.5,
                "color": [255, 200, 120],
                "kind": "torch",
            }
        )
        self.assertEqual(legacy.elevation, 0.0)

    def test_legacy_bar_center_torch_migrates_to_wall_sconces(self) -> None:
        game = self.make_game(tempfile.mkdtemp(), archetype_index=2, seed=3001)
        data = copy.deepcopy(game.serialize_run_state())
        bar = game.dungeon.special_room_for_kind("bar")
        self.assertIsNotNone(bar)
        assert bar is not None
        center_x, center_y = game.dungeon.rooms[bar.room_index].center
        data["light_sources"] = [
            source
            for source in data["light_sources"]
            if source.get("kind") != "bar_wall_light"
        ]
        data["light_sources"].append(
            {
                "x": center_x + 0.5,
                "y": center_y + 0.5,
                "radius": LIGHT_TORCH_RADIUS,
                "color": list(LIGHT_TORCH_COLOR),
                "intensity": LIGHT_TORCH_INTENSITY,
                "flicker": True,
                "kind": "torch",
            }
        )

        restored = self.make_game(tempfile.mkdtemp())
        restored.restore_run_state(data)
        wall_lights = [
            source
            for source in restored.light_sources
            if source.kind == "bar_wall_light"
        ]
        self.assertEqual(len(wall_lights), 2)
        self.assertTrue(
            all(source.elevation == LIGHT_BAR_WALL_ELEVATION for source in wall_lights)
        )
        self.assertFalse(
            any(
                source.kind == "torch"
                and abs(source.x - (center_x + 0.5)) < 0.01
                and abs(source.y - (center_y + 0.5)) < 0.01
                for source in restored.light_sources
            )
        )

    # --- feature 3: lantern/torch flicker -----------------------------
    def test_flicker_modulates_when_lighting_on(self) -> None:
        game = self.make_game(tempfile.mkdtemp())
        game._lighting_enabled = True
        lantern = LightSource(
            game.player.x, game.player.y, 4.0, LIGHT_LANTERN_COLOR,
            intensity=1.0, ttl=None, flicker=True, kind="lantern",
        )
        varied = False
        for seed in range(50):
            lantern.flicker_seed = seed
            r, i = game._flicker(lantern)
            if abs(r - 1.0) > 1e-6 or abs(i - 1.0) > 1e-6:
                varied = True
                break
        self.assertTrue(varied)
        # A non-flickering light never modulates.
        lantern.flicker = False
        self.assertEqual(game._flicker(lantern), (1.0, 1.0))
        # Flicker is suppressed entirely when the lighting model is off.
        game._lighting_enabled = False
        lantern.flicker = True
        self.assertEqual(game._flicker(lantern), (1.0, 1.0))

    def test_modulated_light_sprite_reuses_quantized_variants(self) -> None:
        game = self.make_game(tempfile.mkdtemp())
        sprite = game._radial_light_sprite(48, LIGHT_LANTERN_COLOR)

        first = game._modulated_light_sprite(sprite, 225)
        same_bucket = game._modulated_light_sprite(sprite, 231)
        different_bucket = game._modulated_light_sprite(sprite, 210)

        self.assertIs(first, same_bucket)
        self.assertIsNot(first, different_bucket)
        self.assertEqual(len(game._modulated_light_sprite_cache), 2)
        game.reset_lighting_caches()
        self.assertEqual(len(game._modulated_light_sprite_cache), 0)

    # --- render smoke test --------------------------------------------
    def test_full_frame_render_with_lighting_on(self) -> None:
        game = self.make_game(tempfile.mkdtemp())
        # Exercise the direct-to-screen render path (no zoom layer) so the
        # light buffers are sized to the real display surface.
        game.view_zoom = 1.0
        game._lighting_enabled = True
        game._lighting_normal_maps = True
        game.add_light(game.player.x + 1.0, game.player.y, 2.0, (200, 160, 90), ttl=0.3)
        game.light_sources.append(
            LightSource(
                game.player.x - 1.5, game.player.y, 2.5, LIGHT_TORCH_COLOR,
                intensity=0.6, ttl=None, flicker=True, kind="torch",
            )
        )
        for _ in range(3):
            game.update(0.016)
            game.draw()
        # The reused buffers must match the screen size, not grow per frame.
        sw, sh = game._screen_size()
        self.assertIsNotNone(game._light_buffer_surface)
        self.assertIsNotNone(game._light_scratch_surface)
        assert game._light_buffer_surface is not None
        assert game._light_scratch_surface is not None
        self.assertEqual(game._light_buffer_surface.get_size(), (sw // 2, sh // 2))
        self.assertEqual(game._light_scratch_surface.get_size(), (sw, sh))

    def test_list_colored_light_does_not_crash_render(self) -> None:
        # Light colors arrive as JSON lists (save round-trips) or as unhashable
        # pygame.Color; the lighting cache keys on color and must tolerate both
        # instead of raising ``TypeError: unhashable type``.
        game = self.make_game(tempfile.mkdtemp())
        game._lighting_enabled = True
        game._lighting_normal_maps = True
        json_color = cast(tuple[int, int, int], [245, 215, 90])
        game.light_sources.append(
            LightSource(
                game.player.x,
                game.player.y,
                2.3,
                json_color,
                intensity=0.6,
                ttl=None,
                flicker=False,
                kind="shrine",
            )
        )
        game.update(0.016)
        game.draw()
        # The cache key is a hashable tuple, so the sprite is cached/reused.
        self.assertEqual(
            game._radial_light_sprite(48, json_color),
            game._radial_light_sprite(48, (245, 215, 90)),
        )
        self.assertEqual(
            hashable_color(cast(tuple[int, int, int], [1, 2, 3])),
            (1, 2, 3),
        )
        self.assertEqual(hashable_color((1, 2, 3)), (1, 2, 3))


class FrostNovaRoomFlashTests(unittest.TestCase):
    """Frost Nova max effect: light bursts from the caster and fills the room.

    With the Nova path plus a second full path mastered, casting Frost Nova
    floods the caster's chamber with light: a wave that originates at the
    caster and expands along the flood-filled region — a room, a corridor
    stretch, or both sides of a doorway — stopping at walls and doors (open
    or closed) instead of bleeding through them like a radial halo.
    """

    NOVA_PATH = (
        "arcanist_focus",
        "arcanist_permafrost",
        "arcanist_glacial",
        "arcanist_blizzard",
        "arcanist_absolute_zero",
    )
    WARD_PATH = (
        "arcanist_ward",
        "arcanist_ward_mend",
        "arcanist_ward_overload",
        "arcanist_aegis",
        "arcanist_eternal_aegis",
    )

    def make_arcanist(self, tmpdir, seed=3163) -> Game:
        game = Game(
            screen_size=(960, 600),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.rng.seed(seed)
        game.restart(ARCHETYPES[2])  # Arcanist
        if game.story_intro_pending:
            self.assertTrue(game.choose_story_relic_path(0))
        game.active_cutscene = None
        return game

    def place_in_room(self, game: Game):
        room = game.dungeon.rooms[0]
        cx, cy = room.center
        game.player.x, game.player.y = cx + 0.5, cy + 0.5
        game.snap_camera_to_player()
        return room

    def cast_nova(self, game: Game) -> None:
        game.player.class_skill_timer = 0.0
        game.player.mana = game.player.max_mana
        game.player_cast_nova()

    def test_max_nova_cast_flashes_the_casters_room(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_arcanist(tmpdir)
            self.place_in_room(game)

            # Pre-max: no flash, even from inside a room.
            self.cast_nova(game)
            self.assertEqual(game.room_flash_tiles, {})
            self.assertEqual(game.room_flash_ttl, 0.0)

            game.player.skill_upgrades.extend(self.NOVA_PATH + self.WARD_PATH)
            self.assertTrue(game.nova_engulfs_room())
            self.cast_nova(game)
            caster_tile = (int(game.player.x), int(game.player.y))
            # The wave originates at the caster: distance 0 at their tile.
            self.assertEqual(game.room_flash_tiles.get(caster_tile), 0)
            self.assertEqual(
                game.room_flash_origin, (game.player.x, game.player.y)
            )
            # Total ttl covers the wave travel plus the hold-and-fade tail.
            self.assertGreaterEqual(game.room_flash_ttl, LIGHT_ROOM_FLASH_TTL)

    def test_max_nova_cast_flashes_corridors_too(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_arcanist(tmpdir)
            game.player.skill_upgrades.extend(self.NOVA_PATH + self.WARD_PATH)
            tiles = game.dungeon.tiles
            corridor = next(
                (x, y)
                for x in range(len(tiles))
                for y in range(len(tiles[0]))
                if tiles[x][y] == Tile.FLOOR
                and game.dungeon.room_at(x, y) is None
            )
            game.player.x, game.player.y = corridor[0] + 0.5, corridor[1] + 0.5
            game.snap_camera_to_player()
            self.cast_nova(game)
            # Corridors have no Room, but the flood-filled flash still fires,
            # anchored on the caster's tile.
            self.assertEqual(game.room_flash_tiles.get(corridor), 0)
            self.assertGreater(game.room_flash_ttl, 0.0)

    def test_doorway_regions_flood_both_sides_but_never_pass_doors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_arcanist(tmpdir)
            room = self.place_in_largest_room(game)
            cx, cy = room.center
            tiles = game.dungeon.tiles
            # Seal the room, then carve one doorway with a corridor stub.
            for xx in range(room.x - 1, room.x + room.w + 1):
                tiles[xx][room.y - 1] = Tile.WALL
                tiles[xx][room.y + room.h] = Tile.WALL
            for yy in range(room.y - 1, room.y + room.h + 1):
                tiles[room.x - 1][yy] = Tile.WALL
                tiles[room.x + room.w][yy] = Tile.WALL
            door = (room.x + room.w, cy)
            stub = (room.x + room.w + 1, cy)
            tiles[door[0]][door[1]] = Tile.CLOSED_DOOR
            tiles[stub[0]][stub[1]] = Tile.FLOOR
            # Guarantee a clear lane from the room center to the doorway
            # even if the largest room is a sealed flavor room whose own
            # perimeter ring sits inside the rectangle.
            for xx in range(cx, room.x + room.w):
                tiles[xx][cy] = Tile.FLOOR

            # From inside: the door catches the light but never passes it.
            inside = game.dungeon.room_region_distances(cx + 0.5, cy + 0.5)
            self.assertIn(door, inside)
            self.assertNotIn(stub, inside)

            # From the threshold itself: the flash floods both sides.
            threshold = game.dungeon.room_region_distances(
                door[0] + 0.5, door[1] + 0.5
            )
            self.assertEqual(threshold.get(door), 0)
            self.assertIn(stub, threshold)
            self.assertIn((room.x + room.w - 1, cy), threshold)

    def test_wave_covers_the_room_fully_but_spill_is_capped(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_arcanist(tmpdir)
            tiles = game.dungeon.tiles
            # A synthetic 10x8 room with one doorless opening into a long
            # westward corridor, sealed everywhere else.
            x0, y0, w, h = 30, 30, 10, 8
            cy = y0 + 4
            for tx in range(x0 - 16, x0 + w + 2):
                for ty in range(y0 - 2, y0 + h + 2):
                    tiles[tx][ty] = Tile.WALL
            for tx in range(x0, x0 + w):
                for ty in range(y0, y0 + h):
                    tiles[tx][ty] = Tile.FLOOR
            for tx in range(x0 - 14, x0):
                tiles[tx][cy] = Tile.FLOOR
            game.dungeon.rooms = [Room(x0, y0, w, h)]

            # Cast near the west opening: the room's far east corner is
            # beyond the spill limit, yet the wave must still reach it.
            game.trigger_room_flash(x0 + 2 + 0.5, cy + 0.5)
            region = dict(game.room_flash_tiles)
            far_corner = (x0 + w - 1, y0)
            self.assertIn(far_corner, region)
            self.assertGreater(
                region[far_corner], LIGHT_ROOM_FLASH_SPILL_DISTANCE
            )
            # Spill through the doorless opening exists but is trimmed to
            # the corridor travel limit; deep corridor tiles stay dark.
            outside = {
                tile: dist
                for tile, dist in region.items()
                if not (x0 <= tile[0] < x0 + w and y0 <= tile[1] < y0 + h)
            }
            self.assertTrue(outside)
            self.assertLessEqual(
                max(outside.values()), LIGHT_ROOM_FLASH_SPILL_DISTANCE
            )
            self.assertNotIn((x0 - 12, cy), region)

            # A corridor cast has no room: the whole wave obeys the cap.
            game.trigger_room_flash(x0 - 5 + 0.5, cy + 0.5)
            self.assertTrue(game.room_flash_tiles)
            self.assertLessEqual(
                max(game.room_flash_tiles.values()),
                LIGHT_ROOM_FLASH_SPILL_DISTANCE,
            )

    def test_room_flash_decays_and_resets_with_transient_visuals(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_arcanist(tmpdir)
            self.place_in_room(game)
            game.trigger_room_flash(game.player.x, game.player.y)
            self.assertTrue(game.room_flash_tiles)
            self.assertGreaterEqual(game.room_flash_ttl, LIGHT_ROOM_FLASH_TTL)

            game.update_visual_effects(0.2)
            self.assertGreater(game.room_flash_ttl, 0.0)
            game.update_visual_effects(game.room_flash_ttl + 0.01)
            self.assertEqual(game.room_flash_tiles, {})
            self.assertEqual(game.room_flash_ttl, 0.0)
            self.assertEqual(game.room_flash_max_ttl, 0.0)

            game.trigger_room_flash(game.player.x, game.player.y)
            self.assertTrue(game.room_flash_tiles)
            game.reset_transient_visuals()
            self.assertEqual(game.room_flash_tiles, {})
            self.assertEqual(game.room_flash_ttl, 0.0)

    def _probe_value(self, game: Game, x: int, y: int) -> int:
        """Stamp the active flash into a fresh buffer and sample tile (x, y).

        World tiles are hundreds of pixels wide, so only a handful of tiles
        around the camera exist in the light buffer at once. Each probe
        therefore snaps the camera onto the probed tile before stamping —
        the projection is translation-invariant, so neighbor-bleed geometry
        is unaffected by where the camera sits.
        """
        game.player.x, game.player.y = x + 0.5, y + 0.5
        game.snap_camera_to_player()
        game._frame_cache = None  # drop any per-frame visible_bounds cache
        scale = game.light_buffer_scale()
        w, h = game.screen.get_size()
        buffer = pygame.Surface((w // scale, h // scale), pygame.SRCALPHA)
        buffer.fill((0, 0, 0, 0))
        game._stamp_room_flash(buffer, scale)
        _zoom, project = game._shade_params()
        sx, sy = project(x + 0.5, y + 0.5)
        px, py = sx // scale, sy // scale
        self.assertTrue(0 <= px < buffer.get_width())
        self.assertTrue(0 <= py < buffer.get_height())
        return buffer.get_at((px, py))[0]

    def place_in_largest_room(self, game: Game):
        # The stamp uses square tile rects whose edges exactly touch the
        # projected centers of neighboring tiles, so unlit assertions need
        # probes at least two tiles from any lit tile. The largest room on
        # the floor gives that slack (8x8 or better in practice).
        room = max(game.dungeon.rooms, key=lambda r: r.w * r.h)
        self.assertGreaterEqual(room.w, 8)
        self.assertGreaterEqual(room.h, 8)
        cx, cy = room.center
        game.player.x, game.player.y = cx + 0.5, cy + 0.5
        game.snap_camera_to_player()
        return room

    def _finish_wave_expansion(self, game: Game) -> None:
        """Advance the flash clock so the wave has covered the whole region.

        Leaves ``LIGHT_ROOM_FLASH_TTL - 0.1`` on the clock: every region
        tile is past its attack ramp at full strength, and the global fade
        window has not begun.
        """
        self.assertTrue(game.room_flash_tiles)
        game.room_flash_ttl = LIGHT_ROOM_FLASH_TTL - 0.1

    def test_room_flash_stamp_stays_inside_the_room(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_arcanist(tmpdir)
            game.is_current_floor_dark = lambda: False  # type: ignore[method-assign]
            room = self.place_in_largest_room(game)
            cx, cy = room.center
            tiles = game.dungeon.tiles
            # Seal the room so the flood fill cannot wander out through a
            # generated doorless opening, then sculpt readable probes: a 2x2
            # wall pocket in the min corner (probed at its own corner, two
            # tiles from lit floor), a closed door beside it, unreachable
            # floor past the sealed ring, and a never-revealed 3x3 block
            # probed at its center.
            for xx in range(room.x - 1, room.x + room.w + 1):
                tiles[xx][room.y - 1] = Tile.WALL
                tiles[xx][room.y + room.h] = Tile.WALL
            for yy in range(room.y - 1, room.y + room.h + 1):
                tiles[room.x - 1][yy] = Tile.WALL
                tiles[room.x + room.w][yy] = Tile.WALL
            wall_probe = (room.x, room.y)
            door_probe = (room.x + 2, room.y)
            outside_probe = (room.x + room.w + 1, cy)
            for ox in range(2):
                for oy in range(2):
                    tiles[room.x + ox][room.y + oy] = Tile.WALL
            tiles[door_probe[0]][door_probe[1]] = Tile.CLOSED_DOOR
            tiles[outside_probe[0]][outside_probe[1]] = Tile.FLOOR
            game.revealed_tiles.update(
                (x, y)
                for x in range(room.x - 1, room.x + room.w + 2)
                for y in range(room.y - 1, room.y + room.h + 1)
            )
            hidden_probe = (room.x + room.w - 2, room.y + room.h - 2)
            for ox in range(3):
                for oy in range(3):
                    game.revealed_tiles.discard(
                        (room.x + room.w - 3 + ox, room.y + room.h - 3 + oy)
                    )

            game.trigger_room_flash(cx + 0.5, cy + 0.5)
            self._finish_wave_expansion(game)

            def probe(x: int, y: int) -> int:
                return self._probe_value(game, x, y)

            self.assertGreater(probe(cx, cy), 0)
            # Door tiles on the room's edge catch the light...
            self.assertGreater(probe(*door_probe), 0)
            # ...but walls, tiles beyond the room, and (on light floors)
            # never-revealed fog tiles stay dark: the flash does not traverse
            # walls or doors.
            self.assertEqual(probe(*wall_probe), 0)
            self.assertEqual(probe(*outside_probe), 0)
            self.assertEqual(probe(*hidden_probe), 0)

    def test_room_flash_wave_originates_at_the_caster(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_arcanist(tmpdir)
            game.is_current_floor_dark = lambda: False  # type: ignore[method-assign]
            room = self.place_in_largest_room(game)
            cx, cy = room.center
            game.revealed_tiles.update(
                (x, y)
                for x in range(room.x, room.x + room.w)
                for y in range(room.y, room.y + room.h)
            )
            game.trigger_room_flash(cx + 0.5, cy + 0.5)
            region = dict(game.room_flash_tiles)
            far_probe = next(
                (
                    tile
                    for tile, dist in region.items()
                    if dist >= 6
                    and room.x <= tile[0] < room.x + room.w
                    and room.y <= tile[1] < room.y + room.h
                ),
                None,
            )
            self.assertIsNotNone(far_probe)

            # Freeze the clock 0.1 s after the cast: the wavefront (26
            # tiles/s) has lit the caster's surroundings but cannot have
            # reached six steps out yet — the light visibly originates from
            # the caster instead of blinking on everywhere at once.
            game.room_flash_ttl = game.room_flash_max_ttl - 0.1
            self.assertGreater(self._probe_value(game, cx, cy), 0)
            self.assertEqual(self._probe_value(game, *far_probe), 0)

            # Once the wave finishes expanding, the far tile is lit too.
            self._finish_wave_expansion(game)
            self.assertGreater(self._probe_value(game, *far_probe), 0)

    def test_room_flash_lights_unrevealed_tiles_on_dark_floors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_arcanist(tmpdir)
            game.is_current_floor_dark = lambda: True  # type: ignore[method-assign]
            room = self.place_in_largest_room(game)
            cx, cy = room.center
            hidden_probe = (cx + 1, cy)
            game.revealed_tiles.discard(hidden_probe)
            game.trigger_room_flash(cx + 0.5, cy + 0.5)
            self._finish_wave_expansion(game)
            # The dark-floor payoff: the flash illuminates the whole chamber,
            # including tiles the lantern has never revealed.
            self.assertGreater(self._probe_value(game, *hidden_probe), 0)

    def test_draw_lighting_smoke_with_active_room_flash(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_arcanist(tmpdir)
            self.place_in_room(game)
            game.player.skill_upgrades.extend(self.NOVA_PATH + self.WARD_PATH)
            self.cast_nova(game)
            self.assertTrue(game.room_flash_tiles)
            game.state = "playing"
            game.update(0.016)
            game.draw()
            self.assertGreater(game.room_flash_ttl, 0.0)


if __name__ == "__main__":
    unittest.main()
