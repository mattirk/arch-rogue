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
        ]
        for name in removed:
            self.assertFalse(
                hasattr(RenderingStoryOverlayMixin, name),
                f"unused overlay function {name} should be removed",
            )
        # The choice glyph helper is still used by the active choice rendering.
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
            for value in duel.values():
                self.assertEqual(len(value), 4)

    def test_duel_approach_clash_retreat_rest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            asset = game.active_cutscene_asset()
            self.assertIsNotNone(asset)
            assert asset is not None
            player = asset.actors["player"]
            antagonist = asset.actors["antagonist"]
            period = game.STAGE_DUEL_PERIOD

            def state_at(t):
                game.elapsed = t
                duel = game._cutscene_duel_state()
                assert duel is not None
                return duel["player"], duel["antagonist"]

            # Rest phase (end of cycle): both at home, listening/watching.
            rest_t = (
                game.STAGE_DUEL_PHASE_APPROACH
                + game.STAGE_DUEL_PHASE_CLASH
                + game.STAGE_DUEL_PHASE_RETREAT
                + 0.04
            ) * period
            p_rest, a_rest = state_at(rest_t)
            self.assertAlmostEqual(p_rest[0], 0.0, places=6)
            self.assertAlmostEqual(a_rest[0], 0.0, places=6)
            self.assertEqual(p_rest[1], "listen")
            self.assertEqual(a_rest[1], "watch")

            # Approach phase: player advances right (dx > 0), antagonist
            # advances left (dx < 0).
            approach_t = game.STAGE_DUEL_PHASE_APPROACH * 0.5 * period
            p_app, a_app = state_at(approach_t)
            self.assertGreater(p_app[0], 0.0)
            self.assertLess(a_app[0], 0.0)
            self.assertEqual(p_app[1], "vow")
            self.assertEqual(a_app[1], "threaten")

            # Clash phase: meeting point reached, attack poses.
            clash_t = (
                game.STAGE_DUEL_PHASE_APPROACH + game.STAGE_DUEL_PHASE_CLASH * 0.5
            ) * period
            p_clash, a_clash = state_at(clash_t)
            mid = (player.x + antagonist.x) / 2
            self.assertAlmostEqual(
                player.x + p_clash[0], mid - game.STAGE_DUEL_GAP, places=6
            )
            self.assertAlmostEqual(
                antagonist.x + a_clash[0], mid + game.STAGE_DUEL_GAP, places=6
            )
            self.assertEqual(p_clash[1], "defy")
            self.assertGreater(a_clash[2], 0.5)

            # Retreat phase: heading back toward home, guarded withdrawal.
            retreat_t = (
                game.STAGE_DUEL_PHASE_APPROACH
                + game.STAGE_DUEL_PHASE_CLASH
                + game.STAGE_DUEL_PHASE_RETREAT * 0.5
            ) * period
            p_ret, a_ret = state_at(retreat_t)
            self.assertLess(p_ret[0], p_clash[0])
            self.assertGreater(a_ret[0], a_clash[0])
            self.assertEqual(p_ret[1], "guard")
            self.assertEqual(a_ret[1], "watch")

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
