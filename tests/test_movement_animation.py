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
    WALK_ANIM_SPEED_CEIL,
    WALK_ANIM_SPEED_FLOOR,
    WALK_ANIMATION_RATE,
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

    def test_run_cycle_helper_matches_displayed_frame_selection(self) -> None:
        # The renderer's continuous cycle position must be derived from the
        # same expression the sprite atlas uses to pick the displayed run
        # frame, so the whole-body motion stays locked to the cached frame.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                for anim_time in (0.0, 0.05, 0.31, 0.75, 1.1, 1.49, 2.7, 4.2):
                    cycle_t = game.run_cycle_position(anim_time)
                    frame = int(abs(anim_time * RUN_FRAME_RATE)) % RUN_CYCLE_FRAMES
                    frame_t = frame / RUN_CYCLE_FRAMES
                    self.assertLessEqual(abs(cycle_t - frame_t), 1.0 / RUN_CYCLE_FRAMES)
            finally:
                pass

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

    def test_player_renders_across_all_eight_iso_movement_directions(self) -> None:
        # The polished movement must render without error for every diagonal
        # and cardinal movement direction and produce a non-empty frame.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                player = game.player
                directions = [
                    (1.0, 0.0),
                    (-1.0, 0.0),
                    (0.0, 1.0),
                    (0.0, -1.0),
                    (1.0, 1.0),
                    (1.0, -1.0),
                    (-1.0, 1.0),
                    (-1.0, -1.0),
                ]
                for mx, my in directions:
                    self.set_moving(player, mx, my)
                    player.facing_x = 1.0 if mx >= 0 else -1.0
                    player.anim_time = 0.4
                    game.elapsed = 0.4
                    game.draw_player(player)
                    buf = pygame.image.tobytes(game.screen, "RGBA")
                    self.assertTrue(any(buf), "screen empty after draw_player")
            finally:
                pass

    def test_run_lean_tilts_top_toward_movement_direction(self) -> None:
        # Regression guard for the backward-tilt bug: a negative lean (running
        # screen-left) must tilt the top toward screen-left (forward into the
        # run), not screen-right (backward). The renderer rotates by -lean with
        # no facing-conditional and never mirror-flips the sprite.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                # Marker sprite: a red pixel at the top-center and a blue
                # pixel at the bottom-center of an odd-width canvas.
                marker = pygame.Surface((11, 41), pygame.SRCALPHA)
                marker.fill((0, 0, 0, 0))
                marker.set_at((5, 0), (255, 0, 0, 255))  # top
                marker.set_at((5, 40), (0, 0, 255, 255))  # bottom

                canvas = pygame.Surface((400, 400))
                canvas.fill((0, 0, 0))
                game.screen = canvas
                game.world_to_screen = lambda x, y: (200, 200)  # type: ignore

                # lean < 0 (screen-left run) -> top tilts screen-left, so the
                # red top marker lands left of the blue bottom marker.
                game.blit_sprite(marker, 0.0, 0.0, lean=-4.0)

                red_x = blue_x = None
                for y in range(canvas.get_height()):
                    for x in range(canvas.get_width()):
                        px = canvas.get_at((x, y))
                        if px[:3] == (255, 0, 0):
                            red_x = x
                        elif px[:3] == (0, 0, 255):
                            blue_x = x
                self.assertIsNotNone(red_x, "top marker not rendered")
                self.assertIsNotNone(blue_x, "bottom marker not rendered")
                assert red_x is not None and blue_x is not None
                self.assertLess(
                    red_x,
                    blue_x,
                    "run leaned backward (top right of base)",
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

    def test_slow_enemy_walk_cycle_is_floored_to_avoid_stutter(self) -> None:
        # Slow enemies must cycle at least at WALK_ANIM_SPEED_FLOOR so their
        # legs keep moving instead of freezing into a few stuttering frames.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                enemy = game.enemies[0]
                enemy.moving = True
                enemy.speed = 0.5  # well below the floor
                enemy.anim_time = 0.0
                game.advance_animation_phases(0.1)
                expected = 0.1 * WALK_ANIMATION_RATE * WALK_ANIM_SPEED_FLOOR
                self.assertAlmostEqual(enemy.anim_time, expected, places=5)
                # A very fast enemy is capped at the ceiling.
                enemy.speed = 99.0
                enemy.anim_time = 0.0
                game.advance_animation_phases(0.1)
                expected_cap = 0.1 * WALK_ANIMATION_RATE * WALK_ANIM_SPEED_CEIL
                self.assertAlmostEqual(enemy.anim_time, expected_cap, places=5)
            finally:
                pass

    def test_walk_cycle_advances_smoothly_under_dt_jitter(self) -> None:
        # Regression guard: the phase-locked cycle must still advance
        # monotonically under frame-rate jitter.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                player = game.player
                run_frames = game.sprites.player_animation_frames[player.class_name][
                    "run"
                ]
                indices: list[int] = []
                for i in range(50):
                    dt = 0.0166 if i % 4 != 0 else 0.028
                    game.move_actor(player, player.speed * dt, 0.0)
                    game.advance_animation_phases(dt)
                    self.assertTrue(player.moving)
                    idx = int(abs(player.anim_time * RUN_FRAME_RATE)) % len(run_frames)
                    indices.append(idx)
                self.assertGreater(len(set(indices)), 1)
                self.assertGreater(indices.count(0), 1)
            finally:
                pass


if __name__ == "__main__":
    unittest.main()
