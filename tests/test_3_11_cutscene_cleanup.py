"""Milestone 3.11 — Cutscene cleanup.

Validates the stage cleanup work: removal of the unused transparent-overlay
rendering functions, the depth/perspective scaling that fixes oversized
sprites, the cleaner ground shadows, and the procedural player/antagonist
duel choreography (run together, clash, retreat, repeat).
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame

from arch_rogue.game import ARCHETYPES, Game
from arch_rogue.rendering.story_overlays import RenderingStoryOverlayMixin


class CutsceneCleanup311Tests(unittest.TestCase):
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

    # --- Unused overlay code removed -------------------------------------

    def test_unused_stage_overlay_functions_removed(self) -> None:
        removed = [
            "draw_cutscene_memory_ribbon",
            "draw_cutscene_story_backdrop",
            "draw_cutscene_theme_motifs",
            "draw_cutscene_relic_silhouette",
            "draw_cutscene_faction_sigil",
            "draw_cutscene_choice_tableau",
            "draw_cutscene_narrator_wave",
            # 3.11 stage-lights simplification: the old multi-circle lighting,
            # ambient particle, and footlight-halo systems are gone.
            "draw_stage_lights",
            "_draw_stage_light",
            "draw_stage_ambient",
            "_ambient_painter",
            "_ambient_particle_pos",
            "_paint_ambient_mote",
            "_paint_ambient_dust",
            "_paint_ambient_ember",
            "_paint_ambient_spark",
            "_paint_ambient_leaf",
            "_paint_ambient_snow",
            "_paint_ambient_ash",
            "draw_stage_footlights",
            # Unused prop painters (never placed by any cutscene JSON).
            "_paint_prop_brazier",
            "_paint_prop_throne",
            "_paint_prop_crate",
        ]
        for name in removed:
            self.assertFalse(
                hasattr(RenderingStoryOverlayMixin, name),
                f"unused overlay function {name} should be removed",
            )
        # The new simplified lighting pass and the choice glyph helper remain.
        self.assertTrue(hasattr(RenderingStoryOverlayMixin, "draw_stage_lighting"))
        self.assertTrue(
            hasattr(RenderingStoryOverlayMixin, "draw_cutscene_choice_glyph")
        )
        self.assertTrue(
            hasattr(RenderingStoryOverlayMixin, "draw_cutscene_choice_glyph")
        )

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

    def test_player_depth_scale_exceeds_relic(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.reveal_active_cutscene_narration()
            game.draw()
            asset = game.active_cutscene_asset()
            self.assertIsNotNone(asset)
            assert asset is not None
            relic = asset.actors["relic"]
            player = asset.actors["player"]
            # The relic sits above the floor plane (back of stage) and the
            # player stands near the front; the player's depth scale must be
            # larger so the stage reads with perspective.
            self.assertGreater(
                game._stage_actor_depth_scale(player.y),
                game._stage_actor_depth_scale(relic.y),
            )

    def test_stage_lighting_draws_no_ellipses_or_circles(self) -> None:
        # The simplified stage-lights effect must use only gradient bands and
        # line work — no transparent ellipse/circle blobs on the stage.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            asset = game.active_cutscene_asset()
            self.assertIsNotNone(asset)
            assert asset is not None
            stage = asset.stage
            accent = game.story_state.accent if game.story_state else game.theme.accent
            stage_rect = pygame.Rect(20, 20, 600, 220)
            surf = pygame.Surface((640, 260), pygame.SRCALPHA)

            ellipse_calls = {"n": 0}
            circle_calls = {"n": 0}
            real_ellipse = pygame.draw.ellipse
            real_circle = pygame.draw.circle

            def count_ellipse(*args, **kwargs):
                ellipse_calls["n"] += 1
                return real_ellipse(*args, **kwargs)

            def count_circle(*args, **kwargs):
                circle_calls["n"] += 1
                return real_circle(*args, **kwargs)

            pygame.draw.ellipse = count_ellipse
            pygame.draw.circle = count_circle
            try:
                game.draw_stage_lighting(surf, stage_rect, stage, accent)
            finally:
                pygame.draw.ellipse = real_ellipse
                pygame.draw.circle = real_circle
            self.assertEqual(ellipse_calls["n"], 0)
            self.assertEqual(circle_calls["n"], 0)

    def test_stage_lighting_caches_static_layer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            asset = game.active_cutscene_asset()
            assert asset is not None
            stage = asset.stage
            accent = game.story_state.accent if game.story_state else game.theme.accent
            stage_rect = pygame.Rect(20, 20, 600, 220)
            surf = pygame.Surface((640, 260), pygame.SRCALPHA)
            game.draw_stage_lighting(surf, stage_rect, stage, accent)
            before = dict(RenderingStoryOverlayMixin._STAGE_CACHE)
            game.draw_stage_lighting(surf, stage_rect, stage, accent)
            after = RenderingStoryOverlayMixin._STAGE_CACHE
            # Static lighting layer is reused, not rebuilt.
            self.assertLessEqual(len(after), len(before))

    # --- Duel choreography -----------------------------------------------

    def test_duel_state_none_without_antagonist(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.assertTrue(game.choose_story_relic_path(0))
            guest = game.story_guests[0]
            self.assertTrue(game.start_quest_cutscene("story_guest_dialogue", guest))
            self.assertIsNone(game._cutscene_duel_state())

    def test_duel_state_present_for_omen(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.assertIsNotNone(game.active_cutscene)
            duel = game._cutscene_duel_state()
            self.assertIsNotNone(duel)
            assert duel is not None
            self.assertIn("player", duel)
            self.assertIn("antagonist", duel)
            self.assertIn("clash", duel)
            # Per-actor tuples are (dx, dy, pose, alpha, frame_scale).
            for key in ("player", "antagonist"):
                self.assertEqual(len(duel[key]), 5)
            self.assertEqual(len(duel["clash"]), 2)

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
            clash_y = min(obs_y + game.STAGE_DUEL_DETOUR_FORWARD,
                          game.STAGE_DUEL_DETOUR_MAX_Y)
            meet_p = (obs_x - game.STAGE_DUEL_OBSTACLE_CLEAR, clash_y)
            meet_a = (obs_x + game.STAGE_DUEL_OBSTACLE_CLEAR, clash_y)

            def state_at(t):
                game.elapsed = t
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

    def test_duel_never_crosses_altar_obstacle(self) -> None:
        # Sampling across the whole cycle, the duelers must stay on their own
        # sides of the altar and never pass through its footprint.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            asset = game.active_cutscene_asset()
            assert asset is not None
            player = asset.actors["player"]
            antagonist = asset.actors["antagonist"]
            obstacle = game._cutscene_duel_obstacle(asset, player, antagonist)
            assert obstacle is not None
            obs_x = obstacle[0]
            period = game.STAGE_DUEL_PERIOD
            for index in range(48):
                game.elapsed = index * period / 48
                duel = game._cutscene_duel_state()
                assert duel is not None
                px = player.x + duel["player"][0]
                ax = antagonist.x + duel["antagonist"][0]
                self.assertLess(px, obs_x, "player crossed the altar")
                self.assertGreater(ax, obs_x, "antagonist crossed the altar")

    def test_duel_loops_on_period(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            period = game.STAGE_DUEL_PERIOD
            base_t = 0.37 * period
            game.elapsed = base_t
            first = game._cutscene_duel_state()
            game.elapsed = base_t + period
            second = game._cutscene_duel_state()
            self.assertEqual(first, second)

    def test_duel_clash_flash_safe_outside_clash(self) -> None:
        # The clash flash must early-out cleanly when no duel is active and
        # must not raise during the rest phase.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            period = game.STAGE_DUEL_PERIOD
            stage = pygame.Rect(40, 40, 600, 220)
            surf = pygame.Surface((680, 300), pygame.SRCALPHA)
            game._frame_duel_state = None
            game._draw_duel_clash_flash(surf, stage)  # no duel -> no-op
            game._frame_duel_state = game._cutscene_duel_state()
            rest_t = (
                game.STAGE_DUEL_PHASE_APPROACH
                + game.STAGE_DUEL_PHASE_CLASH
                + game.STAGE_DUEL_PHASE_RETREAT
                + 0.02
            ) * period
            game.elapsed = rest_t
            game._draw_duel_clash_flash(surf, stage)

    # --- Narration speed -------------------------------------------------

    def test_narrator_read_speed_is_2_25x(self) -> None:
        # Per-character delays are divided by the speed multiplier. The
        # original 1.0x baseline was first raised to 1.5x, then another
        # 1.5x faster -> 2.25x overall.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            speed = game.CUTSCENE_NARRATION_SPEED
            self.assertAlmostEqual(speed, 2.25, places=6)
            sample = "Hello, world! This is a test.\nNew line; done."
            fast = sum(game.cutscene_narration_char_delay(c) for c in sample)
            # Reconstruct the baseline (multiplier = 1) by undoing the division.
            baseline = fast * speed
            self.assertAlmostEqual(fast, baseline / 2.25, places=6)
            # Spot-check a regular character and a sentence-end pause.
            self.assertAlmostEqual(
                game.cutscene_narration_char_delay("a"), 0.026 / 2.25, places=6
            )
            self.assertAlmostEqual(
                game.cutscene_narration_char_delay("!"), 0.25 / 2.25, places=6
            )

    # --- Full render regression ------------------------------------------

    def test_cutscene_renders_clean_across_duel_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.reveal_active_cutscene_narration()
            period = game.STAGE_DUEL_PERIOD
            for index in range(12):
                game.elapsed = index * period / 12
                game.draw()
            cache = RenderingStoryOverlayMixin._STAGE_CACHE
            self.assertLess(len(cache), 32)


if __name__ == "__main__":
    unittest.main()
