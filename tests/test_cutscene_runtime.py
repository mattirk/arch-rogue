"""Cutscene runtime, perspective, choreography, timing, and cache regressions."""

from __future__ import annotations

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

import pygame  # noqa: E402

from arch_rogue.game import ARCHETYPES, Game
from arch_rogue.story import StageAsset


class CutsceneGameTestCase(unittest.TestCase):
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


class CutsceneRuntimeTests(CutsceneGameTestCase):
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

            # The omen altar remains the solid divider for every tactical plan.
            obstacle = game._cutscene_duel_obstacle(asset, player, antagonist)
            self.assertEqual(obstacle, (0.5, 0.8))
            obs_x = 0.5

            def state_at(phase: float):
                assert game.active_cutscene is not None
                game.active_cutscene.elapsed = phase * period
                game.elapsed = 137.25
                duel = game._cutscene_duel_state()
                assert duel is not None
                return duel

            # Rest: both return home, the player performs for the audience, and
            # tapered breathing reaches zero at the next cycle boundary.
            rest_phase = (
                game.STAGE_DUEL_PHASE_APPROACH
                + game.STAGE_DUEL_PHASE_CLASH
                + game.STAGE_DUEL_PHASE_RETREAT
                + 0.04
            )
            rest = state_at(rest_phase)
            p_rest = rest["player"]
            a_rest = rest["antagonist"]
            self.assertLess(abs(p_rest[0]), game.STAGE_DUEL_BREATH_X * 2)
            self.assertLess(abs(p_rest[1]), game.STAGE_DUEL_BREATH_Y * 2)
            self.assertLess(abs(a_rest[0]), game.STAGE_DUEL_BREATH_X * 2)
            self.assertLess(abs(a_rest[1]), game.STAGE_DUEL_BREATH_Y * 2)
            self.assertEqual(p_rest[2], "act")
            self.assertEqual(a_rest[2], "watch")
            self.assertGreater(rest["home_act_time"], 0.0)

            # Approach: each actor advances downstage and inward but never
            # crosses the altar. The plan chooses the acting-mark poses.
            approach = state_at(game.STAGE_DUEL_PHASE_APPROACH * 0.5)
            p_app = approach["player"]
            a_app = approach["antagonist"]
            tactic = next(
                item
                for item in game.STAGE_DUEL_TACTICS
                if item["name"] == approach["tactic"]
            )
            self.assertGreater(p_app[0], 0.0)
            self.assertGreater(p_app[1], 0.0)
            self.assertLess(a_app[0], 0.0)
            self.assertGreater(a_app[1], 0.0)
            self.assertLess(player.x + p_app[0], obs_x)
            self.assertGreater(antagonist.x + a_app[0], obs_x)
            self.assertEqual(p_app[2], tactic["pose_p"])
            self.assertEqual(a_app[2], tactic["pose_a"])

            # Clash: the metadata supplies this cycle's deliberately offset
            # meeting marks. Breathing remains only a tiny held-pose offset.
            clash_phase = (
                game.STAGE_DUEL_PHASE_APPROACH
                + game.STAGE_DUEL_PHASE_CLASH * 0.5
            )
            clash_state = state_at(clash_phase)
            p_clash = clash_state["player"]
            a_clash = clash_state["antagonist"]
            meet_p = clash_state["meet"]["player"]
            meet_a = clash_state["meet"]["antagonist"]
            self.assertAlmostEqual(player.x + p_clash[0], meet_p[0], places=2)
            self.assertAlmostEqual(player.y + p_clash[1], meet_p[1], places=2)
            self.assertAlmostEqual(antagonist.x + a_clash[0], meet_a[0], places=2)
            self.assertAlmostEqual(antagonist.y + a_clash[1], meet_a[1], places=2)
            self.assertLess(meet_p[0], obs_x)
            self.assertGreater(meet_a[0], obs_x)
            self.assertGreater(clash_state["clash"][1], 0.8)
            self.assertEqual(p_clash[2], "defy")
            self.assertGreater(a_clash[3], 0.5)

            # Retreat: both withdraw through their guard marks toward home.
            retreat_phase = (
                game.STAGE_DUEL_PHASE_APPROACH
                + game.STAGE_DUEL_PHASE_CLASH
                + game.STAGE_DUEL_PHASE_RETREAT * 0.5
            )
            retreat = state_at(retreat_phase)
            p_ret = retreat["player"]
            a_ret = retreat["antagonist"]
            self.assertLess(p_ret[0], p_clash[0])
            self.assertLess(p_ret[1], p_clash[1])
            self.assertLess(a_ret[1], a_clash[1])
            self.assertEqual(p_ret[2], "guard")
            self.assertEqual(a_ret[2], "watch")

    def test_duel_clash_sequences_strike_counter_and_recipient_recoil(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            asset = game.active_cutscene_asset()
            active = game.active_cutscene
            assert asset is not None and active is not None
            player = asset.actors["player"]
            antagonist = asset.actors["antagonist"]
            self.assertGreaterEqual(
                game.STAGE_DUEL_PHASE_CLASH * game.STAGE_DUEL_PERIOD,
                1.2,
            )

            def clash_at(local: float):
                active.elapsed = (
                    game.STAGE_DUEL_PHASE_APPROACH
                    + local * game.STAGE_DUEL_PHASE_CLASH
                ) * game.STAGE_DUEL_PERIOD
                state = game._cutscene_duel_state()
                assert state is not None
                return state

            opening = clash_at(0.0)
            first = clash_at(game.STAGE_DUEL_IMPACT_BEATS[0])
            second = clash_at(game.STAGE_DUEL_IMPACT_BEATS[1])
            closing = clash_at(0.999)

            self.assertEqual(opening["action_progress"], {
                "player": 0.0,
                "antagonist": 0.0,
            })
            self.assertAlmostEqual(first["impact_strengths"][0], 1.0)
            self.assertAlmostEqual(first["impact_strengths"][1], 0.0)
            self.assertGreater(first["action_progress"]["player"], 0.0)
            self.assertEqual(first["action_progress"]["antagonist"], 0.0)
            self.assertAlmostEqual(second["impact_strengths"][0], 0.0)
            self.assertAlmostEqual(second["impact_strengths"][1], 1.0)
            self.assertEqual(second["action_progress"]["player"], 1.0)
            self.assertGreater(second["action_progress"]["antagonist"], 0.0)
            self.assertEqual(closing["action_progress"]["player"], 1.0)
            self.assertGreater(closing["action_progress"]["antagonist"], 0.99)
            for state in (first, second):
                self.assertEqual(state["player"][2], "defy")
                self.assertEqual(state["antagonist"][2], "threaten")

            player_on_left = player.x < antagonist.x
            first_antagonist_x = antagonist.x + first["antagonist"][0]
            second_player_x = player.x + second["player"][0]
            if player_on_left:
                self.assertGreater(
                    first_antagonist_x,
                    first["meet"]["antagonist"][0],
                )
                self.assertLess(second_player_x, second["meet"]["player"][0])
            else:
                self.assertLess(
                    first_antagonist_x,
                    first["meet"]["antagonist"][0],
                )
                self.assertGreater(second_player_x, second["meet"]["player"][0])

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
            self.assertEqual(start["cycle"], 0)

            # The same cutscene-local instant is identical at unrelated
            # run-global times. A later cycle is deterministic too, but may use
            # a different tactical plan by design.
            active.elapsed = clash_t
            game.elapsed = 0.0
            first = game._cutscene_duel_state()
            game.elapsed = period * 0.83
            second = game._cutscene_duel_state()
            active.elapsed = clash_t + period
            next_cycle = game._cutscene_duel_state()
            self.assertEqual(first, second)
            assert first is not None and next_cycle is not None
            self.assertEqual(first["cycle"], 0)
            self.assertEqual(next_cycle["cycle"], 1)
            game.elapsed = period * 901.0
            self.assertEqual(next_cycle, game._cutscene_duel_state())

    def test_duel_tactics_are_deterministic_varied_bounded_and_continuous(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            asset = game.active_cutscene_asset()
            assert asset is not None and game.active_cutscene is not None
            player = asset.actors["player"]
            antagonist = asset.actors["antagonist"]
            obstacle = game._cutscene_duel_obstacle(asset, player, antagonist)
            assert obstacle is not None
            obs_x = obstacle[0]
            period = game.STAGE_DUEL_PERIOD
            clash_phase = (
                game.STAGE_DUEL_PHASE_APPROACH
                + game.STAGE_DUEL_PHASE_CLASH * 0.5
            )
            tactics: set[str] = set()
            first_deck: list[str] = []
            sequence: list[str] = []

            for cycle in range(15):
                game.active_cutscene.elapsed = (cycle + clash_phase) * period
                game.elapsed = cycle * 113.0
                duel = game._cutscene_duel_state()
                repeat = game._cutscene_duel_state()
                assert duel is not None
                self.assertEqual(duel, repeat)
                self.assertEqual(duel["cycle"], cycle)
                tactics.add(duel["tactic"])
                sequence.append(duel["tactic"])
                if cycle < len(game.STAGE_DUEL_TACTICS):
                    first_deck.append(duel["tactic"])

                meet_p = duel["meet"]["player"]
                meet_a = duel["meet"]["antagonist"]
                waypoint_p = duel["waypoints"]["player"]
                waypoint_a = duel["waypoints"]["antagonist"]
                self.assertLess(meet_p[0], obs_x - 0.02)
                self.assertGreater(meet_a[0], obs_x + 0.02)
                self.assertLess(waypoint_p[0], obs_x - 0.02)
                self.assertGreater(waypoint_a[0], obs_x + 0.02)
                for x, y in (meet_p, meet_a, waypoint_p, waypoint_a):
                    self.assertGreaterEqual(x, 0.08)
                    self.assertLessEqual(x, 0.92)
                    self.assertGreaterEqual(y, game.STAGE_FLOOR_TOP)
                    self.assertLessEqual(y, game.STAGE_DUEL_DETOUR_MAX_Y)

                # Sample the full curve, not only its declared marks.
                for phase in (0.0, 0.08, 0.18, 0.29, 0.36, 0.52, 0.70, 0.86):
                    game.active_cutscene.elapsed = (cycle + phase) * period
                    sample = game._cutscene_duel_state()
                    assert sample is not None
                    px = player.x + sample["player"][0]
                    py = player.y + sample["player"][1]
                    ax = antagonist.x + sample["antagonist"][0]
                    ay = antagonist.y + sample["antagonist"][1]
                    self.assertLess(px, obs_x)
                    self.assertGreater(ax, obs_x)
                    for y in (py, ay):
                        self.assertGreaterEqual(y, game.STAGE_FLOOR_TOP)
                        self.assertLessEqual(y, game.STAGE_DUEL_DETOUR_MAX_Y)

            expected_tactics = {
                str(tactic["name"]) for tactic in game.STAGE_DUEL_TACTICS
            }
            self.assertEqual(set(first_deck), expected_tactics)
            self.assertEqual(len(first_deck), len(set(first_deck)))
            self.assertEqual(tactics, expected_tactics)
            self.assertTrue(
                all(left != right for left, right in zip(sequence, sequence[1:]))
            )

            original_story_seed = game.story_seed
            tactic_count = len(game.STAGE_DUEL_TACTICS)
            for story_seed in range(1, 33):
                game.story_seed = story_seed
                indices = [game._cutscene_duel_tactic_index(cycle) for cycle in range(30)]
                self.assertTrue(
                    all(left != right for left, right in zip(indices, indices[1:])),
                    story_seed,
                )
                for start in range(0, len(indices), tactic_count):
                    block = indices[start : start + tactic_count]
                    self.assertEqual(len(set(block)), tactic_count, story_seed)
            game.story_seed = original_story_seed

            # Tapered breathing and completed guest returns make each plan join
            # the next at the exact home marks without a visible snap.
            for boundary in range(1, 6):
                game.active_cutscene.elapsed = boundary * period - 0.00001
                before = game._cutscene_duel_state()
                game.active_cutscene.elapsed = boundary * period
                after = game._cutscene_duel_state()
                assert before is not None and after is not None
                for actor_id in ("player", "antagonist", "guest"):
                    distance = math.hypot(
                        before[actor_id][0] - after[actor_id][0],
                        before[actor_id][1] - after[actor_id][1],
                    )
                    self.assertLess(distance, 0.0001)

    def test_guest_alternates_cover_excursions_with_label_and_travel_facing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            asset = game.active_cutscene_asset()
            active = game.active_cutscene
            assert asset is not None and active is not None
            guest = asset.actors["guest"]
            period = game.STAGE_DUEL_PERIOD

            def state_at(cycle: int, phase: float):
                # Guest milestones use the shared slowed timing reference;
                # only the covered home pause extends beyond that schedule.
                active.elapsed = (
                    cycle * period
                    + phase * game.STAGE_DUEL_TIMING_REFERENCE
                )
                state = game._cutscene_duel_state()
                assert state is not None
                return state

            excursion_cycles = [
                cycle
                for cycle in range(4)
                if state_at(cycle, 0.40)["guest_excursion"]
            ]
            cover_cycles = [
                cycle
                for cycle in range(4)
                if not state_at(cycle, 0.40)["guest_excursion"]
            ]
            self.assertTrue(excursion_cycles)
            self.assertTrue(cover_cycles)
            cycle = excursion_cycles[0]

            hidden = state_at(cycle, 0.05)
            self.assertTrue(hidden["guest_hidden"])
            self.assertEqual(hidden["guest"][:2], (0.0, 0.0))
            self.assertFalse(hidden["guest"][5])

            exit_state = state_at(cycle, 0.24)
            self.assertFalse(exit_state["guest_hidden"])
            self.assertTrue(exit_state["guest"][5])
            self.assertLess(exit_state["guest"][0], 0.0)
            self.assertLess(exit_state["guest"][1], 0.0)
            self.assertIn(exit_state["directions"]["guest"], ("west", "north-west"))
            game._frame_duel_state = exit_state
            self.assertEqual(
                game._cutscene_actor_direction(guest, exit_state["guest"][0]),
                exit_state["directions"]["guest"],
            )

            watching = state_at(cycle, 0.40)
            watch_x = guest.x + watching["guest"][0]
            watch_y = guest.y + watching["guest"][1]
            self.assertFalse(watching["guest_hidden"])
            self.assertFalse(watching["guest"][5])
            self.assertGreaterEqual(watch_x, 0.65)
            self.assertLessEqual(watch_x, 0.68)
            self.assertGreaterEqual(watch_y, 0.64)
            self.assertLessEqual(watch_y, 0.68)

            returning = state_at(cycle, 0.74)
            self.assertTrue(returning["guest_hidden"])
            self.assertTrue(returning["guest"][5])
            self.assertIn(
                returning["directions"]["guest"],
                ("east", "south-east"),
            )
            game._frame_duel_state = returning
            self.assertEqual(
                game._cutscene_actor_direction(guest, returning["guest"][0]),
                returning["directions"]["guest"],
            )
            behind_architecture = state_at(cycle, 0.78)
            self.assertTrue(behind_architecture["guest_hidden"])
            self.assertTrue(behind_architecture["guest"][5])
            self.assertLess(guest.y + behind_architecture["guest"][1], 0.67)

            concealed_again = state_at(cycle, 0.95)
            self.assertTrue(concealed_again["guest_hidden"])
            self.assertEqual(concealed_again["guest"][:2], (0.0, 0.0))
            covered = state_at(cover_cycles[0], 0.40)
            self.assertTrue(covered["guest_hidden"])
            self.assertEqual(covered["guest"][:2], (0.0, 0.0))

            # The nameplate is absent behind the pillar and returns only after
            # the witness has visibly cleared it.
            class FontProbe:
                def __init__(self) -> None:
                    self.calls: list[str] = []

                def render(self, text, _antialias, _color):
                    self.calls.append(text)
                    return pygame.Surface((12, 5), pygame.SRCALPHA)

            font_probe = FontProbe()
            actor_sprite = pygame.Surface((12, 20), pygame.SRCALPHA)
            stage_surface = pygame.Surface((320, 180), pygame.SRCALPHA)
            stage_rect = stage_surface.get_rect()

            def render_guest(state) -> None:
                game._frame_duel_state = state
                dx, dy, pose, alpha, scale, moving = state["guest"]
                game._render_cutscene_actor(
                    stage_surface,
                    stage_rect,
                    guest,
                    dx,
                    dy,
                    scale,
                    alpha,
                    pose,
                    game.theme.accent,
                    moving=moving,
                )

            with patch.object(
                game,
                "small_font",
                font_probe,
            ), patch.object(
                game,
                "cutscene_actor_visual",
                return_value=(actor_sprite, None),
            ), patch.object(
                game,
                "_draw_stage_contact_shadow",
            ), patch.object(
                game,
                "draw_cutscene_actor_pose_effects",
            ), patch.object(
                game,
                "cutscene_actor_label",
                return_value="Witness",
            ):
                render_guest(hidden)
                self.assertEqual(font_probe.calls, [])
                render_guest(watching)
                self.assertEqual(font_probe.calls, ["Witness"])
            game._frame_duel_state = None

    def test_duel_clash_flash_uses_cutscene_local_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            active = game.active_cutscene
            self.assertIsNotNone(active)
            assert active is not None
            period = game.STAGE_DUEL_PERIOD
            quiet_clash_t = (
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

            for beat in game.STAGE_DUEL_IMPACT_BEATS:
                with self.subTest(beat=beat):
                    active.elapsed = (
                        game.STAGE_DUEL_PHASE_APPROACH
                        + game.STAGE_DUEL_PHASE_CLASH * beat
                    ) * period
                    game.elapsed = rest_t
                    game._frame_duel_state = game._cutscene_duel_state()
                    with patch(
                        "arch_rogue.rendering.story_overlays.pygame.draw.line"
                    ) as line:
                        game._draw_duel_clash_flash(surface, stage_rect)
                    self.assertEqual(line.call_count, 2)

            for local_time, unrelated_global_time in (
                (quiet_clash_t, rest_t),
                (rest_t, quiet_clash_t),
            ):
                active.elapsed = local_time
                game.elapsed = unrelated_global_time
                game._frame_duel_state = game._cutscene_duel_state()
                with patch(
                    "arch_rogue.rendering.story_overlays.pygame.draw.line"
                ) as line:
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

    def test_cutscene_render_scans_narration_and_choice_heights_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.reveal_active_cutscene_narration()
            expected_choices = min(9, len(game.active_cutscene_choices()))
            with patch.object(
                game,
                "active_cutscene_narration_char_count",
                wraps=game.active_cutscene_narration_char_count,
            ) as char_count, patch.object(
                game,
                "cutscene_response_height",
                wraps=game.cutscene_response_height,
            ) as response_height:
                game.draw()
            self.assertEqual(char_count.call_count, 1)
            self.assertEqual(response_height.call_count, expected_choices)

    def test_completed_narration_scrolls_and_incomplete_text_follows_tail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.reveal_active_cutscene_narration()
            game.draw()
            self.assertTrue(game.active_cutscene_narration_complete())
            self.assertGreater(game._cutscene_narration_scroll_max, 0)
            self.assertEqual(
                game.cutscene_narration_scroll,
                game._cutscene_narration_scroll_max,
            )
            self.assertTrue(game.cutscene_narration_follow_tail)
            scrollbar = game._cutscene_narration_scrollbar_rect
            self.assertIsNotNone(scrollbar)
            assert scrollbar is not None
            self.assertTrue(game._cutscene_narrator_rect.contains(scrollbar))

            bottom = game.cutscene_narration_scroll
            self.assertTrue(game.scroll_active_cutscene_narration(-2))
            self.assertEqual(game.cutscene_narration_scroll, bottom - 2)
            self.assertFalse(game.cutscene_narration_follow_tail)
            game.draw()
            self.assertEqual(game.cutscene_narration_scroll, bottom - 2)

            game.scroll_active_cutscene_narration(-10_000)
            self.assertEqual(game.cutscene_narration_scroll, 0)
            game.scroll_active_cutscene_narration(10_000)
            self.assertEqual(
                game.cutscene_narration_scroll,
                game._cutscene_narration_scroll_max,
            )

            assert game.active_cutscene is not None
            game.active_cutscene.node_elapsed = 0.0
            game.draw()
            self.assertFalse(game.active_cutscene_narration_complete())
            self.assertEqual(game._cutscene_narration_scroll_max, 0)
            self.assertEqual(game.cutscene_narration_scroll, 0)
            self.assertTrue(game.cutscene_narration_follow_tail)
            self.assertFalse(game.scroll_active_cutscene_narration(-1))

            game.cutscene_narration_scroll = 4
            game.cutscene_narration_follow_tail = False
            game.reset_transient_visuals()
            self.assertEqual(game.cutscene_narration_scroll, 0)
            self.assertTrue(game.cutscene_narration_follow_tail)
            self.assertTrue(game.start_quest_cutscene("story_guest_dialogue"))
            self.assertEqual(game.cutscene_narration_scroll, 0)
            self.assertTrue(game.cutscene_narration_follow_tail)
            game.close_active_cutscene()
            self.assertEqual(game.cutscene_narration_scroll, 0)
            self.assertTrue(game.cutscene_narration_follow_tail)

    # --- Full render regression ------------------------------------------

    def test_cutscene_render_reuses_cached_stage_across_duel_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.reveal_active_cutscene_narration()
            game.clear_stage_render_cache()
            cache = game._stage_cache()
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
            self.assertLessEqual(len(cache), game.STAGE_CACHE_LIMIT)

            other = self.make_game(str(Path(tmpdir) / "other"))
            self.assertIsNot(cache, other._stage_cache())

    def test_duel_override_skips_redundant_authored_actor_frame_work(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            asset = game.active_cutscene_asset()
            assert asset is not None and game.active_cutscene is not None
            game.active_cutscene.elapsed = (
                game.STAGE_DUEL_PHASE_APPROACH
                + game.STAGE_DUEL_PHASE_CLASH * 0.5
            ) * game.STAGE_DUEL_PERIOD
            with patch.object(
                game,
                "cutscene_actor_frame",
                wraps=game.cutscene_actor_frame,
            ) as actor_frame:
                game.draw_cutscene_stage(
                    pygame.Surface((844, 170), pygame.SRCALPHA),
                    pygame.Rect(0, 0, 844, 170),
                    "omen_idle",
                    game.theme.accent,
                )
            self.assertEqual(
                [call.args[0] for call in actor_frame.call_args_list],
                ["relic"],
            )


class TheaterRedesignTests(CutsceneGameTestCase):
    """4.2.3 cutscene theater redesign: sprite props + animated actors."""


    def test_stage_props_use_authored_sprites_with_procedural_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            for kind in ("pillar", "altar", "lectern", "banner"):
                frame = game.sprites.stage_prop_visual(kind)
                self.assertIsNotNone(frame, kind)
                assert frame is not None
                self.assertTrue(frame.is_asset, kind)
            base = game.sprites.stage_prop_visual("pillar")
            half = game.sprites.stage_prop_visual("pillar", 0.5)
            assert base is not None and half is not None
            self.assertLess(
                half.surface.get_height(), base.surface.get_height()
            )
            self.assertLess(half.anchor[1], base.anchor[1])
            # Unmapped kinds and legacy graphics fall back to the painters.
            self.assertIsNone(game.sprites.stage_prop_visual("throne"))
            game.set_legacy_graphics(True)
            self.assertIsNone(game.sprites.stage_prop_visual("pillar"))
            game.set_legacy_graphics(False)

            # A full cutscene render with the sprite props stays crash-free.
            game.reveal_active_cutscene_narration()
            assert game.active_cutscene is not None
            game.active_cutscene.elapsed = game.STAGE_DUEL_PERIOD * 0.95
            game.draw()

    def test_legacy_stage_matches_cold_procedural_render_after_modern_warmup(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            warm_game = self.make_game(str(Path(tmpdir) / "warm"))
            assert warm_game.active_cutscene is not None
            warm_game.elapsed = 17.25
            warm_game.active_cutscene.elapsed = 0.40 * warm_game.STAGE_DUEL_PERIOD
            stage_rect = pygame.Rect(0, 0, 844, 170)
            warm_game.draw_cutscene_stage(
                pygame.Surface(stage_rect.size, pygame.SRCALPHA),
                stage_rect,
                "omen_idle",
                warm_game.theme.accent,
            )
            self.assertTrue(warm_game._stage_cache())
            warm_game.set_legacy_graphics(True)
            self.assertFalse(warm_game._stage_cache())

            warmed_legacy = pygame.Surface(stage_rect.size, pygame.SRCALPHA)
            warm_game.draw_cutscene_stage(
                warmed_legacy,
                stage_rect,
                "omen_idle",
                warm_game.theme.accent,
            )
            self.assertFalse(warm_game._cutscene_curtain_asset_used)

            cold_game = self.make_game(str(Path(tmpdir) / "cold"))
            assert cold_game.active_cutscene is not None
            cold_game.elapsed = 17.25
            cold_game.active_cutscene.elapsed = 0.40 * cold_game.STAGE_DUEL_PERIOD
            cold_game.set_legacy_graphics(True)
            cold_legacy = pygame.Surface(stage_rect.size, pygame.SRCALPHA)
            cold_game.draw_cutscene_stage(
                cold_legacy,
                stage_rect,
                "omen_idle",
                cold_game.theme.accent,
            )
            self.assertEqual(
                pygame.image.tobytes(warmed_legacy, "RGBA"),
                pygame.image.tobytes(cold_legacy, "RGBA"),
            )

    def test_stage_cache_clears_when_ui_scale_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game._stage_cache()[("sentinel",)] = pygame.Surface((1, 1))
            game._activate_options_row(game.OPTIONS_ROW_UI_SCALE, True)
            self.assertFalse(game._stage_cache())

    def test_stage_cache_keys_the_effective_fitted_scale(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            rect = pygame.Rect(0, 0, 640, 200)

            def render(scale: float, *, cold: bool = False) -> bytes:
                if cold:
                    game.clear_stage_render_cache()
                game._ui_scale_override = scale
                try:
                    surface = pygame.Surface(rect.size, pygame.SRCALPHA)
                    game.draw_stage_proscenium(surface, rect, game.theme.accent)
                    return pygame.image.tobytes(surface, "RGBA")
                finally:
                    del game._ui_scale_override

            scale_one = render(1.0)
            warm_scale_one_half = render(1.5)
            cold_scale_one_half = render(1.5, cold=True)
            self.assertNotEqual(scale_one, warm_scale_one_half)
            self.assertEqual(warm_scale_one_half, cold_scale_one_half)

    def test_cutscene_actors_use_animated_sprite_clips(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            asset = game.active_cutscene_asset()
            assert asset is not None and game.active_cutscene is not None
            player = asset.actors["player"]
            guest = asset.actors["guest"]

            # Idle frames advance with the cutscene clock (animated, not
            # static): sampling across a second yields multiple frames.
            frames = set()
            for t in (0.0, 0.25, 0.5, 0.75):
                game.active_cutscene.elapsed = t
                surface, anchor = game.cutscene_actor_visual(
                    player, (226, 222, 205), "listen", "east", False
                )
                self.assertIsNotNone(anchor)
                frames.add(id(surface))
            self.assertGreater(len(frames), 1)

            # Facing matters: the east and west frames differ.
            game.active_cutscene.elapsed = 0.0
            east, _ = game.cutscene_actor_visual(
                player, (226, 222, 205), "listen", "east", False
            )
            west, _ = game.cutscene_actor_visual(
                player, (226, 222, 205), "listen", "west", False
            )
            self.assertIsNot(east, west)

            # The guest is asset-backed too.
            _, guest_anchor = game.cutscene_actor_visual(
                guest, (226, 222, 205), "plead", "west", False
            )
            self.assertIsNotNone(guest_anchor)

            # During the clash, both duelists receive their own normalized
            # progress instead of sampling non-looping attacks from the global
            # cutscene clock and becoming stuck on the final frame.
            antagonist = asset.actors["antagonist"]
            game.active_cutscene.elapsed = (
                game.STAGE_DUEL_PHASE_APPROACH
                + game.STAGE_DUEL_PHASE_CLASH * 0.5
            ) * game.STAGE_DUEL_PERIOD
            duel = game._cutscene_duel_state()
            assert duel is not None
            game._frame_duel_state = duel
            with patch.object(
                game.sprites,
                "player_visual",
                wraps=game.sprites.player_visual,
            ) as player_visual:
                _, attack_anchor = game.cutscene_actor_visual(
                    player, (226, 222, 205), "defy", "east", False
                )
            self.assertIsNotNone(attack_anchor)
            player_args, player_kwargs = player_visual.call_args
            self.assertEqual(player_args[1], "attack")
            self.assertAlmostEqual(
                player_kwargs["action_progress"],
                duel["action_progress"]["player"],
            )

            with patch.object(
                game.sprites,
                "enemy_visual",
                wraps=game.sprites.enemy_visual,
            ) as enemy_visual:
                _, attack_anchor = game.cutscene_actor_visual(
                    antagonist,
                    (226, 222, 205),
                    "threaten",
                    "west",
                    False,
                )
            self.assertIsNotNone(attack_anchor)
            enemy_args, enemy_kwargs = enemy_visual.call_args
            self.assertEqual(enemy_args[2], "attack")
            self.assertAlmostEqual(
                enemy_kwargs["action_progress"],
                duel["action_progress"]["antagonist"],
            )
            game._frame_duel_state = None

            # The relic apparition stays procedural by design.
            relic = asset.actors["relic"]
            _, relic_anchor = game.cutscene_actor_visual(
                relic, (226, 222, 205), "reveal", "west", False
            )
            self.assertIsNone(relic_anchor)

            # Legacy graphics keep the historical static/procedural look.
            game.set_legacy_graphics(True)
            _, legacy_anchor = game.cutscene_actor_visual(
                player, (226, 222, 205), "listen", "east", False
            )
            self.assertIsNone(legacy_anchor)

    def test_non_duel_player_performs_act_clip_facing_the_audience(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.assertTrue(game.start_quest_cutscene("story_guest_dialogue"))
            asset = game.active_cutscene_asset()
            assert asset is not None and game.active_cutscene is not None
            player = asset.actors["player"]
            game._frame_duel_state = None

            self.assertEqual(
                game._cutscene_actor_state(
                    "vow", False, False, is_player=True
                ),
                "act",
            )
            self.assertEqual(
                game._cutscene_actor_state(
                    "vow", True, False, is_player=True
                ),
                "walk",
            )
            self.assertEqual(
                game._cutscene_actor_state(
                    "defy", False, True, is_player=True
                ),
                "attack",
            )
            self.assertEqual(
                game._cutscene_actor_state(
                    "guard", False, True, is_player=True
                ),
                "idle",
            )

            frames = set()
            with patch.object(
                game.sprites,
                "player_visual",
                wraps=game.sprites.player_visual,
            ) as player_visual:
                for elapsed in (0.0, 0.26, 0.51, 0.76):
                    game.active_cutscene.elapsed = elapsed
                    surface, anchor = game.cutscene_actor_visual(
                        player,
                        (226, 222, 205),
                        "vow",
                        "west",
                        False,
                    )
                    self.assertIsNotNone(anchor)
                    frames.add(id(surface))
                    args, kwargs = player_visual.call_args
                    self.assertEqual(args[1], "act")
                    self.assertEqual(kwargs["direction"], "south")
            self.assertEqual(len(frames), 4)

    def test_duelist_pauses_at_left_home_mark_for_act_clip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            asset = game.active_cutscene_asset()
            active = game.active_cutscene
            assert asset is not None and active is not None
            player = asset.actors["player"]
            antagonist = asset.actors["antagonist"]
            rest_start = (
                game.STAGE_DUEL_PHASE_APPROACH
                + game.STAGE_DUEL_PHASE_CLASH
                + game.STAGE_DUEL_PHASE_RETREAT
            )
            rest_duration = (1.0 - rest_start) * game.STAGE_DUEL_PERIOD
            self.assertGreaterEqual(rest_duration, 2.0)

            def rest_at(local: float):
                active.elapsed = (
                    rest_start + local * (1.0 - rest_start)
                ) * game.STAGE_DUEL_PERIOD
                state = game._cutscene_duel_state()
                assert state is not None
                return state

            first = rest_at(0.05)
            later = rest_at(0.55)
            self.assertLess(player.x, antagonist.x)
            for state in (first, later):
                dx, dy, pose, _alpha, _scale, moving = state["player"]
                self.assertEqual(pose, "act")
                self.assertFalse(moving)
                self.assertLess(abs(dx), game.STAGE_DUEL_BREATH_X * 2)
                self.assertLess(abs(dy), game.STAGE_DUEL_BREATH_Y * 2)
            self.assertAlmostEqual(first["home_act_time"], rest_duration * 0.05)
            self.assertAlmostEqual(later["home_act_time"], rest_duration * 0.55)
            self.assertGreater(later["home_act_time"], first["home_act_time"])

            game._frame_duel_state = first
            with patch.object(
                game.sprites,
                "player_visual",
                wraps=game.sprites.player_visual,
            ) as player_visual:
                _, anchor = game.cutscene_actor_visual(
                    player,
                    (226, 222, 205),
                    first["player"][2],
                    "east",
                    first["player"][5],
                )
            self.assertIsNotNone(anchor)
            args, kwargs = player_visual.call_args
            self.assertEqual(args[1], "act")
            self.assertAlmostEqual(args[2], first["home_act_time"])
            self.assertAlmostEqual(args[3], first["home_act_time"])
            self.assertEqual(kwargs["direction"], "south")
            game._frame_duel_state = None

    def test_story_intro_player_performs_act_clip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.active_cutscene = None
            game._frame_duel_state = None
            surface = pygame.Surface((720, 180), pygame.SRCALPHA)
            with patch.object(
                game.sprites,
                "player_visual",
                wraps=game.sprites.player_visual,
            ) as player_visual:
                game.draw_story_intro_stage(
                    surface,
                    surface.get_rect(),
                    game.theme.accent,
                )
            player_visual.assert_called_once()
            args, kwargs = player_visual.call_args
            self.assertEqual(args[1], "act")
            self.assertEqual(kwargs["direction"], "south")

    def test_duel_state_reports_movement_for_walk_clip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            assert game.active_cutscene is not None
            period = game.STAGE_DUEL_PERIOD
            p_app = game.STAGE_DUEL_PHASE_APPROACH
            p_clash = p_app + game.STAGE_DUEL_PHASE_CLASH
            p_ret = p_clash + game.STAGE_DUEL_PHASE_RETREAT

            def moving_at(t: float) -> tuple[bool, bool]:
                assert game.active_cutscene is not None
                game.active_cutscene.elapsed = t * period
                duel = game._cutscene_duel_state()
                assert duel is not None
                return duel["player"][5], duel["antagonist"][5]

            self.assertEqual(moving_at(p_app * 0.5), (True, True))
            self.assertEqual(moving_at(p_app * 0.62), (False, False))
            self.assertEqual(moving_at(p_app * 0.85), (True, True))
            self.assertEqual(
                moving_at(p_app + game.STAGE_DUEL_PHASE_CLASH * 0.5),
                (False, False),
            )
            self.assertEqual(
                moving_at(p_clash + game.STAGE_DUEL_PHASE_RETREAT * 0.2),
                (True, True),
            )
            self.assertEqual(
                moving_at(p_clash + game.STAGE_DUEL_PHASE_RETREAT * 0.5),
                (False, False),
            )
            self.assertEqual(
                moving_at(p_clash + game.STAGE_DUEL_PHASE_RETREAT * 0.8),
                (True, True),
            )
            self.assertEqual(moving_at(p_ret + 0.04), (False, False))

    def test_omen_blocking_is_symmetric_and_pillars_occlude_the_guest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            asset = game.active_cutscene_asset()
            assert asset is not None and game.active_cutscene is not None
            player = asset.actors["player"]
            antagonist = asset.actors["antagonist"]
            guest = asset.actors["guest"]
            props = {prop.id: prop for prop in asset.stage.props}
            pillars = {
                depth: (
                    props[f"pillar_left_{depth}"],
                    props[f"pillar_right_{depth}"],
                )
                for depth in ("far", "mid", "front")
            }
            self.assertEqual(
                [pillars[depth][0].y for depth in ("far", "mid", "front")],
                [0.7, 0.82, 0.95],
            )
            for left_pillar, right_pillar in pillars.values():
                self.assertAlmostEqual(left_pillar.x + right_pillar.x, 1.0)
            self.assertEqual(pillars["mid"][1].x, guest.x)
            self.assertGreater(
                pillars["mid"][1].y,
                max(actor.y for actor in asset.actors.values()),
            )
            self.assertAlmostEqual(game.STAGE_PROP_HEIGHT_FRACS["pillar"], 0.90)

            obstacle = game._cutscene_duel_obstacle(asset, player, antagonist)
            assert obstacle is not None
            tactics: set[str] = set()
            for cycle in range(10):
                game.active_cutscene.elapsed = (
                    cycle
                    + game.STAGE_DUEL_PHASE_APPROACH
                    + game.STAGE_DUEL_PHASE_CLASH * 0.5
                ) * game.STAGE_DUEL_PERIOD
                duel = game._cutscene_duel_state()
                assert duel is not None
                tactics.add(duel["tactic"])
                meet_player = duel["meet"]["player"]
                meet_antagonist = duel["meet"]["antagonist"]
                self.assertLess(meet_player[0], obstacle[0])
                self.assertGreater(meet_antagonist[0], obstacle[0])
                for candelabra_id, actor_id in (
                    ("candelabra_left", "player"),
                    ("candelabra_right", "antagonist"),
                ):
                    candelabra = props[candelabra_id]
                    waypoint = duel["waypoints"][actor_id]
                    self.assertGreater(
                        math.hypot(
                            candelabra.x - waypoint[0],
                            candelabra.y - waypoint[1],
                        ),
                        0.10,
                    )
            self.assertGreaterEqual(len(tactics), 3)

            game.reveal_active_cutscene_narration()
            game.active_cutscene.elapsed = (
                game.STAGE_DUEL_PHASE_APPROACH
                + game.STAGE_DUEL_PHASE_CLASH * 0.5
            ) * game.STAGE_DUEL_PERIOD
            order: list[tuple[str, str]] = []

            def record_actor(*args, **kwargs):
                order.append(("actor", args[2].id))

            def record_prop(*args, **kwargs):
                order.append(("prop", args[2].id))

            with patch.object(game, "_render_cutscene_actor", side_effect=record_actor), patch.object(
                game, "_draw_stage_prop", side_effect=record_prop
            ):
                game.draw_cutscene_stage(
                    pygame.Surface((844, 170), pygame.SRCALPHA),
                    pygame.Rect(0, 0, 844, 170),
                    "omen_idle",
                    game.theme.accent,
                )
            for side in ("left", "right"):
                far_index = order.index(("prop", f"pillar_{side}_far"))
                mid_index = order.index(("prop", f"pillar_{side}_mid"))
                front_index = order.index(("prop", f"pillar_{side}_front"))
                self.assertLess(far_index, order.index(("actor", "player")))
                self.assertLess(far_index, order.index(("actor", "antagonist")))
                self.assertGreater(mid_index, order.index(("actor", "guest")))
                self.assertLess(mid_index, order.index(("actor", "player")))
                self.assertLess(mid_index, order.index(("actor", "antagonist")))
                for actor_id in ("player", "antagonist", "guest"):
                    self.assertGreater(front_index, order.index(("actor", actor_id)))

    def test_duel_period_and_walk_clip_slow_together(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.assertAlmostEqual(game.STAGE_ACTOR_TIME_SCALE, 0.40)
            self.assertAlmostEqual(game.STAGE_DUEL_PERIOD, 6.9)
            self.assertAlmostEqual(game.STAGE_DUEL_CLIP_TIME_SCALE, 0.60)
            self.assertAlmostEqual(
                game.STAGE_DUEL_PHASE_APPROACH * game.STAGE_DUEL_PERIOD,
                1.80,
            )
            self.assertAlmostEqual(
                game.STAGE_DUEL_PHASE_CLASH * game.STAGE_DUEL_PERIOD,
                1.296,
            )
            self.assertAlmostEqual(
                game.STAGE_DUEL_PHASE_RETREAT * game.STAGE_DUEL_PERIOD,
                1.80,
            )
            asset = game.active_cutscene_asset()
            assert asset is not None and game.active_cutscene is not None
            player = asset.actors["player"]
            game.active_cutscene.elapsed = (
                game.STAGE_DUEL_PHASE_APPROACH * 0.35 * game.STAGE_DUEL_PERIOD
            )
            game._frame_duel_state = game._cutscene_duel_state()
            with patch.object(
                game.sprites,
                "player_visual",
                wraps=game.sprites.player_visual,
            ) as player_visual:
                game.cutscene_actor_visual(
                    player,
                    (226, 222, 205),
                    "vow",
                    "south-east",
                    True,
                )
            args, _kwargs = player_visual.call_args
            expected_clock = (
                game.active_cutscene.elapsed * game.STAGE_DUEL_CLIP_TIME_SCALE
            )
            self.assertAlmostEqual(args[2], expected_clock)
            self.assertAlmostEqual(args[3], expected_clock)
            game._frame_duel_state = None

    def test_authored_curtain_stays_fixed_open_during_narration(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            asset = game.active_cutscene_asset()
            assert asset is not None and game.active_cutscene is not None
            authored_open = game.ui_asset_surface("stage.curtain.open", (688, 192))
            assert authored_open is not None
            start = pygame.Surface((688, 192), pygame.SRCALPHA)
            complete = pygame.Surface((688, 192), pygame.SRCALPHA)
            game.active_cutscene.node_elapsed = 0.0
            game.draw_stage_curtain(start, start.get_rect(), asset.stage, game.theme.accent)
            game.reveal_active_cutscene_narration()
            game.draw_stage_curtain(
                complete,
                complete.get_rect(),
                asset.stage,
                game.theme.accent,
            )
            expected = pygame.image.tobytes(authored_open, "RGBA")
            self.assertEqual(pygame.image.tobytes(start, "RGBA"), expected)
            self.assertEqual(pygame.image.tobytes(complete, "RGBA"), expected)

    def test_legacy_procedural_curtain_also_stays_fixed_open(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            asset = game.active_cutscene_asset()
            assert asset is not None and game.active_cutscene is not None
            game.set_legacy_graphics(True)
            start = pygame.Surface((688, 192), pygame.SRCALPHA)
            complete = pygame.Surface((688, 192), pygame.SRCALPHA)
            game.active_cutscene.node_elapsed = 0.0
            game.draw_stage_curtain(start, start.get_rect(), asset.stage, game.theme.accent)
            self.assertFalse(game._cutscene_curtain_asset_used)
            game.reveal_active_cutscene_narration()
            game.draw_stage_curtain(
                complete,
                complete.get_rect(),
                asset.stage,
                game.theme.accent,
            )
            self.assertEqual(
                pygame.image.tobytes(start, "RGBA"),
                pygame.image.tobytes(complete, "RGBA"),
            )
            rgba = pygame.image.tobytes(start, "RGBA")
            self.assertTrue(any(rgba[3::4]))
            center = start.subsurface((start.get_width() // 3, 0, start.get_width() // 3, start.get_height()))
            center_rgba = pygame.image.tobytes(center, "RGBA")
            self.assertFalse(any(center_rgba[3::4]))

    def test_stage_lighting_honors_footlights_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            without = pygame.Surface((320, 120), pygame.SRCALPHA)
            with_lights = pygame.Surface((320, 120), pygame.SRCALPHA)
            game.draw_stage_lighting(
                without,
                without.get_rect(),
                StageAsset(footlights=False),
                game.theme.accent,
            )
            game.draw_stage_lighting(
                with_lights,
                with_lights.get_rect(),
                StageAsset(footlights=True),
                game.theme.accent,
            )
            foot_y = with_lights.get_height() - game.ui(3)
            self.assertEqual(
                without.get_at((without.get_width() // 2, game.ui(8))),
                with_lights.get_at((with_lights.get_width() // 2, game.ui(8))),
            )
            self.assertNotEqual(
                without.get_at((without.get_width() // 2, foot_y)),
                with_lights.get_at((with_lights.get_width() // 2, foot_y)),
            )

    def test_duel_movement_faces_match_stage_space_travel(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            asset = game.active_cutscene_asset()
            assert asset is not None and game.active_cutscene is not None
            player = asset.actors["player"]
            antagonist = asset.actors["antagonist"]
            period = game.STAGE_DUEL_PERIOD

            game.active_cutscene.elapsed = (
                game.STAGE_DUEL_PHASE_APPROACH * 0.5 * period
            )
            game._frame_duel_state = game._cutscene_duel_state()
            self.assertEqual(
                game._cutscene_actor_direction(player, 0.0), "south-east"
            )
            self.assertEqual(
                game._cutscene_actor_direction(antagonist, 0.0), "south-west"
            )

            game.active_cutscene.elapsed = (
                game.STAGE_DUEL_PHASE_APPROACH
                + game.STAGE_DUEL_PHASE_CLASH
                + game.STAGE_DUEL_PHASE_RETREAT * 0.2
            ) * period
            game._frame_duel_state = game._cutscene_duel_state()
            self.assertEqual(
                game._cutscene_actor_direction(player, 0.0), "north-west"
            )
            self.assertEqual(
                game._cutscene_actor_direction(antagonist, 0.0), "north-east"
            )
            game._frame_duel_state = None

    def test_duelists_face_each_other_and_others_face_center(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            asset = game.active_cutscene_asset()
            assert asset is not None and game.active_cutscene is not None
            game.active_cutscene.elapsed = game.STAGE_DUEL_PERIOD * 0.95
            game._frame_duel_state = game._cutscene_duel_state()
            player = asset.actors["player"]
            antagonist = asset.actors["antagonist"]
            guest = asset.actors["guest"]
            self.assertEqual(game._cutscene_actor_direction(player, 0.0), "east")
            self.assertEqual(
                game._cutscene_actor_direction(antagonist, 0.0), "west"
            )
            # The guest stands on stage right and faces center stage.
            self.assertEqual(game._cutscene_actor_direction(guest, 0.0), "west")
            game._frame_duel_state = None

    def test_stage_full_set_backdrop_used_for_authored_scenes(self) -> None:
        # Authored full-scene backdrops replace the procedural back
        # wall/floor/proscenium on the asset path; legacy stays procedural.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            asset = game.active_cutscene_asset()
            assert asset is not None
            game.clear_stage_render_cache()
            cache = game._stage_cache()
            surface = pygame.Surface((640, 200), pygame.SRCALPHA)
            used = game.draw_stage_full_set(
                surface, pygame.Rect(0, 0, 640, 200), asset.stage, (245, 132, 72)
            )
            self.assertTrue(used)
            self.assertEqual(
                game.STAGE_FULL_SET_ASSETS["omen"],
                ("stage.backdrop.omen", 0.66),
            )
            self.assertTrue(any(key[1] == "backdrop-full" for key in cache))
            game.set_legacy_graphics(True)
            used_legacy = game.draw_stage_full_set(
                surface, pygame.Rect(0, 0, 640, 200), asset.stage, (245, 132, 72)
            )
            self.assertFalse(used_legacy)
            self.assertFalse(game._stage_cache())
            game.set_legacy_graphics(False)

    def test_stage_backdrop_scenery_flat_only_with_asset_ui(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.assertIsNotNone(game._stage_scenery_source())
            asset = game.active_cutscene_asset()
            assert asset is not None
            game.clear_stage_render_cache()
            cache = game._stage_cache()
            surface = pygame.Surface((640, 200), pygame.SRCALPHA)
            game.draw_stage_backdrop(
                surface, pygame.Rect(0, 0, 640, 200), asset.stage, (245, 132, 72)
            )
            self.assertTrue(
                any(key[4] == (asset.stage.backdrop, True) for key in cache)
            )
            game.set_legacy_graphics(True)
            cache = game._stage_cache()
            game.draw_stage_backdrop(
                surface, pygame.Rect(0, 0, 640, 200), asset.stage, (245, 132, 72)
            )
            self.assertTrue(
                any(key[4] == (asset.stage.backdrop, False) for key in cache)
            )
            cache.clear()


if __name__ == "__main__":
    unittest.main()
