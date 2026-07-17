from __future__ import annotations

import math
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame

from arch_rogue.constants import (
    RUN_CYCLE_FRAMES,
    RUN_FRAME_RATE,
    TILE_H,
    TILE_W,
)
from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game
from arch_rogue.sprites import PixelSpriteAtlas


class MovementAnimationPolish35Tests(unittest.TestCase):
    def tearDown(self) -> None:
        pass

    def make_game(self, tmpdir: str, seed: int = 3501) -> Game:
        game = Game(
            screen_size=(960, 540),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.rng.seed(seed)
        game.restart(ARCHETYPES[0])
        if game.story_intro_pending:
            self.assertTrue(game.choose_story_relic_path(0))
        game.active_cutscene = None
        return game

    def test_directional_sprite_hysteresis_rejects_sector_edge_noise(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)

            def world_vector(screen_angle: float) -> tuple[float, float]:
                radians = math.radians(screen_angle)
                projected_x = math.cos(radians) / (TILE_W / 2)
                projected_y = math.sin(radians) / (TILE_H / 2)
                return (
                    (projected_x + projected_y) * 0.5,
                    (projected_y - projected_x) * 0.5,
                )

            for angle in (22.0, 24.0, 27.0):
                dx, dy = world_vector(angle)
                self.assertEqual(
                    game.actor_sprite_direction(dx, dy, previous="east"),
                    "east",
                )

            dx, dy = world_vector(30.0)
            self.assertEqual(
                game.actor_sprite_direction(dx, dy, previous="east"),
                "south-east",
            )

    def test_tiny_movement_detection_is_frame_rate_independent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.enemies = []
            game.dungeon.blocked_for_radius = lambda *_args: False  # type: ignore[method-assign]
            start_x = game.player.x

            for fps in (30, 60, 120):
                with self.subTest(fps=fps):
                    dt = 1.0 / fps
                    game._last_dt = dt
                    game.player.x = start_x
                    game.player.moving = False
                    moved = game.move_actor(game.player, 0.000001 * dt, 0.0)
                    self.assertGreater(moved, 0.0)
                    self.assertTrue(game.player.moving)

    def test_player_walk_cadence_scales_with_partial_movement(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.enemies = []
            player = game.player
            player.moving = True
            player.locomotion_anim_scale = 1.0
            game.advance_animation_phases(0.1)
            full_speed_phase = player.anim_time

            player.anim_time = 0.0
            player.locomotion_anim_scale = 0.25
            game.advance_animation_phases(0.1)
            self.assertAlmostEqual(
                player.anim_time,
                full_speed_phase * 0.25,
                places=6,
            )

    def set_moving(self, player, mx: float, my: float) -> None:
        player.moving = True
        length = math.hypot(mx, my)
        if length > 0:
            mx /= length
            my /= length
        # The lean now follows the facing vector, so drive facing from the
        # movement direction (matching gameplay, where facing snaps to input).
        player.move_x = mx
        player.move_y = my
        player.facing_x = mx
        player.facing_y = my

    def test_bob_is_grounded_phase_locked_and_footfall_matched(self) -> None:
        # The whole-body bob must (a) be signed so the body dips below its
        # anchor at foot-plant instead of constantly floating upward, and
        # (b) complete exactly one cycle per run-frame stride cycle, proving
        # it is phase-locked to the displayed frames (old code ran the bob at
        # 3x the frame frequency, producing a wobblish ghost-float look), and
        # (c) match the footfall of the displayed run frame so the body rises
        # exactly when the lifted foot rises.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                player = game.player
                self.set_moving(player, 1.0, 0.0)

                # (a)+(b): sample bob over one stride cycle; assert sign span
                # and exactly one interior maximum.
                frame_cycle_span = RUN_CYCLE_FRAMES / RUN_FRAME_RATE  # one stride
                samples = 40
                bobs = []
                for i in range(samples + 1):
                    t = i / samples * frame_cycle_span
                    player.anim_time = t
                    _, bob, _, _ = game.actor_animation(player)
                    bobs.append(bob)

                self.assertLess(min(bobs), -0.1, "bob never dips below anchor")
                self.assertGreater(max(bobs), 0.1, "bob never rises above anchor")

                interior_maxima = 0
                for i in range(1, len(bobs) - 1):
                    if bobs[i] > bobs[i - 1] and bobs[i] > bobs[i + 1]:
                        interior_maxima += 1
                self.assertEqual(
                    interior_maxima,
                    1,
                    f"expected one bob cycle per stride, got {interior_maxima}",
                )

                # (c): at each frame's display anim_time the bob must match the
                # (frame+0.5)/N footfall formula. The renderer advances the bob
                # on a continuous phase (smooth) while the cached frame steps in
                # discrete increments; they share one frequency, so the body
                # rises in lockstep with the lifted foot.
                for frame in range(RUN_CYCLE_FRAMES):
                    player.anim_time = (frame + 0.5) / RUN_FRAME_RATE
                    _, bob, _, _ = game.actor_animation(player)
                    cycle_t = (frame + 0.5) / RUN_CYCLE_FRAMES
                    footfall = 0.5 - 0.5 * math.cos(cycle_t * math.tau)
                    expected = (footfall - 0.5) * 1.2
                    self.assertAlmostEqual(bob, expected, places=2)
            finally:
                pass

    def test_run_pose_keeps_upper_body_stable_while_feet_lift(self) -> None:
        # The polished run pose must keep the head/cap stable while the feet
        # do the lifting work, so the upper body no longer floats. Compare the
        # opaque-pixel mask of the foot-plant frame (i=0) against the peak-lift
        # frame (i=half): the feet region must shift, the head region stays put.
        atlas = PixelSpriteAtlas()
        try:
            for class_name in atlas.player_animation_frames:
                run = atlas.player_animation_frames[class_name]["run"]
                self.assertEqual(len(run), RUN_CYCLE_FRAMES)
                plant = run[0]
                peak = run[RUN_CYCLE_FRAMES // 2]
                self.assertIsInstance(plant, pygame.Surface)
                self.assertIsInstance(peak, pygame.Surface)

                plant_mask = pygame.mask.from_surface(plant)
                peak_mask = pygame.mask.from_surface(peak)
                h = plant.get_height()

                def band_centroid_y(mask: pygame.Mask, y0: int, y1: int) -> float:
                    total = 0
                    count = 0
                    for y in range(y0, y1):
                        for x in range(0, plant.get_width()):
                            if mask.get_at((x, y)):
                                total += y
                                count += 1
                    return total / count if count else 0.0

                # Feet band = bottom ~18% must move vertically (feet lift).
                feet_y0 = round(h * 0.82)
                plant_feet = band_centroid_y(plant_mask, feet_y0, h)
                peak_feet = band_centroid_y(peak_mask, feet_y0, h)
                self.assertNotEqual(
                    plant_feet,
                    peak_feet,
                    f"{class_name}: feet band did not move between plant/peak",
                )
                # Head band = top ~16% must stay nearly fixed (no float).
                head_y1 = round(h * 0.16)
                plant_head = band_centroid_y(plant_mask, 0, head_y1)
                peak_head = band_centroid_y(peak_mask, 0, head_y1)
                self.assertLess(
                    abs(plant_head - peak_head),
                    2.0,
                    f"{class_name}: head band floated between plant/peak",
                )
        finally:
            pass

    def test_lean_follows_facing_and_movement_direction(self) -> None:
        # The lean must tilt toward the screen-space movement direction, differ
        # between opposing directions, be large enough to actually rotate the
        # sprite (above the blit_sprite rotation threshold), be clamped to a sane
        # cap, and follow the facing vector (which snaps to input) rather than
        # the gameplay-smoothed move vector.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                player = game.player

                # Cardinal movement directions: signs + magnitude/cap bounds.
                leans: dict[tuple[float, float], float] = {}
                for mx, my in ((1.0, 0.0), (-1.0, 0.0), (0.0, 1.0), (0.0, -1.0)):
                    self.set_moving(player, mx, my)
                    player.anim_time = 0.25
                    _, _, lean, _ = game.actor_animation(player)
                    leans[(mx, my)] = lean

                self.assertGreater(leans[(1.0, 0.0)], 0.0)
                self.assertLess(leans[(-1.0, 0.0)], 0.0)
                self.assertLess(leans[(0.0, 1.0)], 0.0)
                self.assertGreater(leans[(0.0, -1.0)], 0.0)
                for lean in leans.values():
                    self.assertGreater(abs(lean), 1.0)
                for lean in leans.values():
                    self.assertLessEqual(abs(lean), 5.0)

                # Facing-vs-smoothed-move flip: smoothed move vector still points
                # the old way but facing snaps to input -> lean must flip
                # instantly so direction changes feel consistent.
                player.moving = True
                player.anim_time = 0.25
                player.move_x = 1.0
                player.move_y = 0.0
                player.facing_x = -1.0
                player.facing_y = 0.0
                _, _, lean_left, _ = game.actor_animation(player)
                player.move_x = -1.0
                player.facing_x = 1.0
                _, _, lean_right, _ = game.actor_animation(player)
                self.assertLess(lean_left, 0.0, "lean did not follow facing left")
                self.assertGreater(lean_right, 0.0, "lean did not follow facing right")
                self.assertLess(lean_left, lean_right)
            finally:
                pass

    def test_idle_pose_stays_seamless_across_band_boundaries(self) -> None:
        # Regression guard for the idle-seam bug: the breathing animation
        # slices the sprite into vertical bands and offsets each band by a
        # small per-frame dy. Without the band-overlap fill, adjacent bands
        # that separate vertically leave transparent seams between sprite
        # sections (very visible while standing still, masked while moving).
        # Every idle frame must therefore retain nearly the full base
        # silhouette: the only legitimate opaque-pixel loss is the body
        # shifting up/down by a couple of pixels at the very top/bottom edge,
        # never a full-width seam punched across an internal band boundary.
        pygame.init()
        pygame.display.set_mode((64, 64), pygame.HIDDEN)
        atlas = PixelSpriteAtlas()
        self.assertGreaterEqual(atlas.BAND_OVERLAP, 1)

        frame_sets = {
            name: atlas.player_animation_frames[name]
            for name in atlas.player_animation_frames
        }
        frame_sets.update(atlas.enemy_animation_frames)
        frame_sets["shopkeeper"] = atlas.shopkeeper_animation_frames
        bases = {
            name: atlas.player_sprites.get(name)
            or atlas.enemies.get(name)
            or atlas.shopkeeper_sprite
            for name in frame_sets
        }

        for name, states in frame_sets.items():
            base = bases[name]
            width = base.get_width()
            base_count = pygame.mask.from_surface(base).count()
            idle = states["idle"]
            self.assertGreaterEqual(len(idle), 6)
            for frame in idle:
                self.assertEqual(frame.get_size(), base.get_size())
                count = pygame.mask.from_surface(frame).count()
                # Breathing only shifts the body by a couple of pixels; the
                # band-overlap fills internal seams. The only legitimate loss
                # is the silhouette sliding a hair at the top/bottom edge, so
                # anything beyond ~0.9px of full-width loss means a seam
                # reopened at a band boundary (the overlap fill was dropped or a
                # pose offset exceeded the BAND_OVERLAP budget).
                self.assertLess(
                    base_count - count,
                    round(width * 0.9),
                    f"{name}: idle frame lost too much silhouette ({base_count - count} "
                    f"opaque px) vs base ({base_count}); a band seam reopened",
                )


if __name__ == "__main__":
    unittest.main()
