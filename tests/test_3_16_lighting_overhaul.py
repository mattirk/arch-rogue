# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
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

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame  # noqa: F401  (required to initialize pygame subsystems in tests)

from arch_rogue import __version__
from arch_rogue.constants import (
    DARK_LEVEL_LIGHT_RADIUS,
    LIGHT_LEVEL_SIGHT_RADIUS,
    LIGHT_LANTERN_COLOR,
    LIGHT_TORCH_COLOR,
)
from arch_rogue.content import ARCHETYPES, SHRINE_HINTS
from arch_rogue.game import Game
from arch_rogue.lighting import bake_normal_map, light_radius_px
from arch_rogue.models import LightSource, Projectile, Tile


class Lighting316Tests(unittest.TestCase):
    def make_game(self, tmpdir, archetype_index=0, seed=3161) -> Game:
        game = Game(
            screen_size=(960, 600),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.ui_scale = 1
        game.rebuild_fonts()
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

    def test_normal_map_differs_for_different_pixels(self) -> None:
        a = pygame.Surface((8, 8), pygame.SRCALPHA)
        pygame.draw.rect(a, (255, 255, 255), (0, 0, 8, 8))
        b = pygame.Surface((8, 8), pygame.SRCALPHA)
        pygame.draw.rect(b, (255, 255, 255), (2, 2, 4, 4))
        na, nb = bake_normal_map(a), bake_normal_map(b)
        self.assertNotEqual(na.get_at((1, 4)), nb.get_at((1, 4)))

    def test_sprite_atlas_bakes_normal_maps_lazily(self) -> None:
        game = self.make_game(tempfile.mkdtemp())
        sprite = game.sprites.player_frame("Warden", "idle", 0.0, 0.0)
        nm = game.sprites.normal_map_for(sprite)
        self.assertIsNotNone(nm)
        # Cached: a second request returns the same surface.
        self.assertIs(game.sprites.normal_map_for(sprite), nm)

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
                light_radius_px(light.radius), light.color, light.intensity
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
                light_radius_px(light.radius), light.color, light.intensity
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
        # A moving light is appended inside the projectile loop.
        self.assertGreaterEqual(len(game.lights), 1)
        first = game.lights[0]
        self.assertEqual(first.color, proj.color)
        self.assertEqual(first.kind, "projectile")

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
        game2 = self.make_game(tempfile.mkdtemp())
        game2._lighting_enabled = True
        game2.set_current_floor_dark(True)
        self.assertLess(game2._ambient_level(), game._ambient_level())

    # --- feature 7: static torch/shrine lights ------------------------
    def test_static_shrine_and_torch_lights_populated(self) -> None:
        game = self.make_game(tempfile.mkdtemp())
        # Shrines always become light sources tinted by their accent color.
        for shrine in game.shrines:
            matches = [
                s for s in game.light_sources
                if s.kind == "shrine" and abs(s.x - shrine.x) < 0.01 and abs(s.y - shrine.y) < 0.01
            ]
            self.assertEqual(len(matches), 1)
            hint = SHRINE_HINTS.get(shrine.kind)
            self.assertIsNotNone(hint)
            assert hint is not None
            self.assertEqual(matches[0].color, hint.color)
            self.assertFalse(matches[0].flicker)
        # Torch lights are flickering and warm; garden torches are green.
        torches = [s for s in game.light_sources if s.kind == "torch"]
        for t in torches:
            self.assertTrue(t.flicker)

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

    def test_draw_lighting_noop_when_disabled(self) -> None:
        game = self.make_game(tempfile.mkdtemp())
        game._lighting_enabled = False
        # Should return without raising and without compositing.
        game.draw_lighting()

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
        self.assertEqual(len(game2.light_sources), len(game.light_sources))
        # Transient pulses never persist.
        self.assertEqual(game2.lights, [])

    def test_pre_3_16_save_loads_with_empty_light_sources(self) -> None:
        game = self.make_game(tempfile.mkdtemp())
        data = copy.deepcopy(game.serialize_run_state())
        # Simulate a pre-3.16 save that has no light_sources field.
        data.pop("light_sources", None)
        game2 = self.make_game(tempfile.mkdtemp())
        # Must not raise; defaults to empty and never blocks population.
        game2.restore_run_state(data)
        self.assertEqual(game2.light_sources, [])

    # --- feature 3: reduced-motion flicker suppression ----------------
    def test_reduced_motion_suppresses_flicker(self) -> None:
        game = self.make_game(tempfile.mkdtemp())
        game._lighting_enabled = True
        game._reduced_motion = True
        lantern = LightSource(
            game.player.x, game.player.y, 4.0, LIGHT_LANTERN_COLOR,
            intensity=1.0, ttl=None, flicker=True, kind="lantern",
        )
        rad_scale, int_scale = game._flicker(lantern)
        self.assertEqual((rad_scale, int_scale), (1.0, 1.0))
        # With reduced motion off, a flickering light modulates.
        game._reduced_motion = False
        varied = False
        for seed in range(50):
            lantern.flicker_seed = seed
            r, i = game._flicker(lantern)
            if abs(r - 1.0) > 1e-6 or abs(i - 1.0) > 1e-6:
                varied = True
                break
        self.assertTrue(varied)

    # --- render smoke test --------------------------------------------
    def test_full_frame_render_with_lighting_on(self) -> None:
        game = self.make_game(tempfile.mkdtemp())
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

    def test_version_bumped(self) -> None:
        self.assertEqual(__version__, "3.16.0")


if __name__ == "__main__":
    unittest.main()