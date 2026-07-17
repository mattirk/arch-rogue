"""Cutscene runtime, perspective, choreography, timing, and cache regressions."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from arch_rogue.game import ARCHETYPES, Game
from arch_rogue.rendering.story_overlays import RenderingStoryOverlayMixin


class CutsceneRuntimeTests(unittest.TestCase):
    def make_game(self, tmpdir: str, seed: int = 3117) -> Game:
        game = Game(
            screen_size=(960, 600),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.rng.seed(seed)
        game.restart(ARCHETYPES[2])
        return game



    # --- Depth / perspective scaling -------------------------------------

    def test_stage_actor_depth_scale_perspective(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            back = game._stage_actor_depth_scale(game.STAGE_FLOOR_TOP)
            front = game._stage_actor_depth_scale(1.0)
            mid = game._stage_actor_depth_scale((game.STAGE_FLOOR_TOP + 1.0) * 0.5)
            self.assertAlmostEqual(back, game.STAGE_BACK_SCALE, places=6)
            self.assertAlmostEqual(front, game.STAGE_FRONT_SCALE, places=6)
            self.assertGreater(front, mid)
            self.assertGreater(mid, back)

    # --- Duel choreography -----------------------------------------------

    def test_duel_approach_clash_retreat_rest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            asset = game.active_cutscene_asset()
            self.assertIsNotNone(asset)
            assert asset is not None
            player = asset.actors["player"]
            antagonist = asset.actors["antagonist"]
            period = game.STAGE_DUEL_PERIOD

            # The omen altar sits between the duelers and is the obstacle.
            obstacle = game._cutscene_duel_obstacle(asset, player, antagonist)
            self.assertIsNotNone(obstacle)
            assert obstacle is not None
            obs_x, obs_y = obstacle
            clash_y = min(
                obs_y + game.STAGE_DUEL_DETOUR_FORWARD, game.STAGE_DUEL_DETOUR_MAX_Y
            )
            meet_p = (obs_x - game.STAGE_DUEL_OBSTACLE_CLEAR, clash_y)
            meet_a = (obs_x + game.STAGE_DUEL_OBSTACLE_CLEAR, clash_y)

            def state_at(t):
                assert game.active_cutscene is not None
                game.active_cutscene.elapsed = t
                game.elapsed = 137.25
                duel = game._cutscene_duel_state()
                assert duel is not None
                return duel["player"], duel["antagonist"], duel["clash"]

            # Rest phase (end of cycle): both at home, no offset.
            rest_t = (
                game.STAGE_DUEL_PHASE_APPROACH
                + game.STAGE_DUEL_PHASE_CLASH
                + game.STAGE_DUEL_PHASE_RETREAT
                + 0.04
            ) * period
            p_rest, a_rest, _ = state_at(rest_t)
            self.assertAlmostEqual(p_rest[0], 0.0, places=6)
            self.assertAlmostEqual(p_rest[1], 0.0, places=6)
            self.assertAlmostEqual(a_rest[0], 0.0, places=6)
            self.assertAlmostEqual(a_rest[1], 0.0, places=6)
            self.assertEqual(p_rest[2], "listen")
            self.assertEqual(a_rest[2], "watch")

            # Approach phase: both step forward (dy > 0) and toward the altar;
            # player advances right, the duelers stay on their own sides.
            approach_t = game.STAGE_DUEL_PHASE_APPROACH * 0.5 * period
            p_app, a_app, _ = state_at(approach_t)
            self.assertGreater(p_app[0], 0.0)
            self.assertGreater(p_app[1], 0.0)
            self.assertGreater(a_app[1], 0.0)
            self.assertLess(player.x + p_app[0], obs_x)
            self.assertGreater(antagonist.x + a_app[0], obs_x)
            self.assertEqual(p_app[2], "vow")
            self.assertEqual(a_app[2], "threaten")

            # Clash phase: meeting points reached in front of the altar, on
            # opposite sides; clash point is centered on the altar.
            clash_t = (
                game.STAGE_DUEL_PHASE_APPROACH + game.STAGE_DUEL_PHASE_CLASH * 0.5
            ) * period
            p_clash, a_clash, clash = state_at(clash_t)
            self.assertAlmostEqual(player.x + p_clash[0], meet_p[0], places=6)
            self.assertAlmostEqual(player.y + p_clash[1], meet_p[1], places=6)
            self.assertAlmostEqual(antagonist.x + a_clash[0], meet_a[0], places=6)
            self.assertAlmostEqual(antagonist.y + a_clash[1], meet_a[1], places=6)
            self.assertAlmostEqual(clash[0], obs_x, places=6)
            self.assertAlmostEqual(clash[1], clash_y, places=6)
            self.assertEqual(p_clash[2], "defy")
            self.assertGreater(a_clash[3], 0.5)

            # Retreat phase: heading back toward home (offsets shrink).
            retreat_t = (
                game.STAGE_DUEL_PHASE_APPROACH
                + game.STAGE_DUEL_PHASE_CLASH
                + game.STAGE_DUEL_PHASE_RETREAT * 0.5
            ) * period
            p_ret, a_ret, _ = state_at(retreat_t)
            self.assertLess(p_ret[0], p_clash[0])
            self.assertLess(p_ret[1], p_clash[1])
            self.assertLess(a_ret[1], a_clash[1])
            self.assertEqual(p_ret[2], "guard")
            self.assertEqual(a_ret[2], "watch")

    def test_duel_uses_cutscene_local_time_independent_of_run_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            active = game.active_cutscene
            self.assertIsNotNone(active)
            assert active is not None
            period = game.STAGE_DUEL_PERIOD
            clash_t = (
                game.STAGE_DUEL_PHASE_APPROACH
                + game.STAGE_DUEL_PHASE_CLASH * 0.5
            ) * period

            # Entering the cutscene late in a run still starts the duel at its
            # deterministic local origin rather than midway through a cycle.
            self.assertEqual(active.elapsed, 0.0)
            game.elapsed = clash_t + period * 100.0
            start = game._cutscene_duel_state()
            self.assertIsNotNone(start)
            assert start is not None
            self.assertEqual(start["player"][:2], (0.0, 0.0))
            self.assertEqual(start["antagonist"][:2], (0.0, 0.0))
            self.assertEqual(start["player"][2], "vow")

            # The same cutscene-local instant is identical at unrelated
            # run-global times, and wrapping one period preserves the cycle.
            active.elapsed = clash_t
            game.elapsed = 0.0
            first = game._cutscene_duel_state()
            game.elapsed = period * 0.83
            second = game._cutscene_duel_state()
            active.elapsed = clash_t + period
            wrapped = game._cutscene_duel_state()
            self.assertEqual(first, second)
            self.assertEqual(first, wrapped)

    def test_duel_clash_flash_uses_cutscene_local_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            active = game.active_cutscene
            self.assertIsNotNone(active)
            assert active is not None
            period = game.STAGE_DUEL_PERIOD
            clash_t = (
                game.STAGE_DUEL_PHASE_APPROACH
                + game.STAGE_DUEL_PHASE_CLASH * 0.5
            ) * period
            rest_t = (
                game.STAGE_DUEL_PHASE_APPROACH
                + game.STAGE_DUEL_PHASE_CLASH
                + game.STAGE_DUEL_PHASE_RETREAT
                + 0.04
            ) * period
            surface = game.screen.copy()
            stage_rect = surface.get_rect()

            active.elapsed = clash_t
            game.elapsed = rest_t
            game._frame_duel_state = game._cutscene_duel_state()
            with patch("arch_rogue.rendering.story_overlays.pygame.draw.line") as line:
                game._draw_duel_clash_flash(surface, stage_rect)
            self.assertEqual(line.call_count, 2)

            active.elapsed = rest_t
            game.elapsed = clash_t
            game._frame_duel_state = game._cutscene_duel_state()
            with patch("arch_rogue.rendering.story_overlays.pygame.draw.line") as line:
                game._draw_duel_clash_flash(surface, stage_rect)
            line.assert_not_called()
            game._frame_duel_state = None

    # --- Narration speed -------------------------------------------------

    def test_narrator_read_speed_is_2_25x(self) -> None:
        # Per-character delays are divided by the speed multiplier. The
        # original 1.0x baseline was first raised to 1.5x, then another
        # 1.5x faster -> 2.25x overall.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            speed = game.CUTSCENE_NARRATION_SPEED
            self.assertAlmostEqual(speed, 2.25, places=6)
            # Spot-check a regular character and a sentence-end pause.
            self.assertAlmostEqual(
                game.cutscene_narration_char_delay("a"), 0.026 / 2.25, places=6
            )
            self.assertAlmostEqual(
                game.cutscene_narration_char_delay("!"), 0.25 / 2.25, places=6
            )

    # --- Full render regression ------------------------------------------

    def test_cutscene_render_reuses_cached_stage_across_duel_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.reveal_active_cutscene_narration()
            cache = RenderingStoryOverlayMixin._STAGE_CACHE
            cache.clear()
            assert game.active_cutscene is not None
            game.active_cutscene.elapsed = 0.0
            game.elapsed = 91.0
            game.draw()
            snapshot = dict(cache)
            self.assertTrue(snapshot)

            period = game.STAGE_DUEL_PERIOD
            for index in range(1, 12):
                game.active_cutscene.elapsed = index * period / 12
                game.elapsed = 91.0 + index
                game.draw()

            self.assertLessEqual(len(cache), len(snapshot) + 4)
            for key, surface in snapshot.items():
                if key in cache:
                    self.assertIs(cache[key], surface)


if __name__ == "__main__":
    unittest.main()
