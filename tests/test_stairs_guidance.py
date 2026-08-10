# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
#
# AI Provenance & Liability Notice:
# This repository contains code generated, assisted, or refactored by Artificial
# Intelligence models. Provided strictly "AS IS" under Apache 2.0 with no warranty
# of clean IP provenance or non-infringement; downstream users assume all legal
# and financial risk and should perform their own compliance audits.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""5.0.2 stairs guidance: Aid-streak extension, dark floors, sticky minimap.

Three related quality-of-descent features:
- an unbroken all-Aid choice streak extends the guiding light from the
  recovered relic onward to the stairs (one bargain/defy anywhere in the
  run silences the extension);
- the guiding light works on dark floors: with modern graphics the authored
  guiding_floor animation carries the guidance in the floor pass on every
  floor (the lantern bounds its reach in the dark), while the legacy
  carve-line fallback draws after the darkness pass with the lantern clip
  relaxed;
- the minimap's stairs marker is sticky on dark floors once seen, so the
  edge arrow can guide back through the black.
"""

from __future__ import annotations

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

from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game


def make_game(tmpdir: str, seed: int = 7101) -> Game:
    game = Game(
        screen_size=(960, 600),
        headless=True,
        save_path=Path(tmpdir) / "run.json",
    )
    game.options_path = Path(tmpdir) / "options.json"
    game.rng.seed(seed)
    game.restart(ARCHETYPES[0])
    return game


def choose_aid(game: Game) -> None:
    # Choice order is seed-shuffled, so find Aid by key.
    options = game.story_relic_choice_options()
    index = next(
        i for i, (key, _label, _detail) in enumerate(options) if key == "aid"
    )
    assert game.choose_story_relic_path(index)
    game.active_cutscene = None


def collect_relic(game: Game) -> None:
    game.items = [item for item in game.items if item.slot != "story_relic"]
    game.story_relic_collected = True


class AidStreakTests(unittest.TestCase):
    def test_streak_tracks_the_recorded_relic_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            self.assertFalse(game.story_aid_streak_intact())
            choose_aid(game)
            self.assertTrue(game.story_aid_streak_intact())
            game.story_state.flags.append("2:relic:bargain")
            self.assertFalse(game.story_aid_streak_intact())

    def test_aid_streak_extends_guidance_to_the_stairs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            choose_aid(game)
            # Uncollected: the light points at the relic, exactly as before.
            self.assertEqual(
                game.story_relic_target_position(), game.story_relic_position
            )
            collect_relic(game)
            stairs_x, stairs_y = game.dungeon.stairs
            self.assertEqual(
                game.story_relic_target_position(),
                (stairs_x + 0.5, stairs_y + 0.5),
            )
            # The minimap beacon follows the same target.
            self.assertEqual(
                game.minimap_guidance(), (stairs_x + 0.5, stairs_y + 0.5)
            )

    def test_broken_streak_ends_guidance_at_the_relic(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            choose_aid(game)
            game.story_state.flags.append("0:relic:defy")
            collect_relic(game)
            self.assertIsNone(game.story_relic_target_position())

    def test_no_story_run_never_extends(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            choose_aid(game)
            collect_relic(game)
            game.story_state = None
            self.assertFalse(game.story_aid_streak_intact())
            self.assertIsNone(game.story_relic_target_position())


class DarkFloorGuidanceTests(unittest.TestCase):
    def test_overlay_defers_to_floor_animation_on_dark_floors(self) -> None:
        # Regression: the carve-line overlay used to come back on dark floors
        # even with modern guidance tiles active, double-drawing beside the
        # authored floor animation. The overlay must defer to the floor pass
        # on every floor; dark levels are no exception.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            choose_aid(game)
            self.assertGreater(
                game.sprites.world_tile_animation_frame_count("guiding_floor"),
                1,
            )
            game.camera_x, game.camera_y = game.player.x, game.player.y

            # Light floor + modern guiding tiles: the overlay defers to the
            # floor-pass tile animation and paints nothing itself.
            game.screen.fill((0, 0, 0))
            before = pygame.image.tobytes(game.screen, "RGB")
            game.is_current_floor_dark = lambda: False
            game.draw_story_relic_guidance()
            self.assertEqual(
                pygame.image.tobytes(game.screen, "RGB"), before
            )

            # Dark floor: still nothing — the guidance stays the floor
            # animation instead of the drawn line.
            game.is_current_floor_dark = lambda: True
            game.draw_story_relic_guidance()
            self.assertEqual(
                pygame.image.tobytes(game.screen, "RGB"), before
            )

            # And the floor animation is genuinely active on the dark floor:
            # once the player has stood still for a moment, the travelling
            # crest assigns guiding_floor frames to route tiles.
            game.player.moving = False
            game.story_guidance_tile_frames()  # arms the idle clock
            game.elapsed += 1.25  # crest reaches mid-window over the route
            self.assertTrue(game.story_guidance_tile_frames())

    def test_legacy_carve_line_still_leads_on_dark_floors(self) -> None:
        # Without modern guidance tiles (legacy graphics / missing assets)
        # the carve line remains the dark-floor guidance, drawn after the
        # darkness pass (5.0.2).
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            choose_aid(game)
            game.camera_x, game.camera_y = game.player.x, game.player.y
            game.is_current_floor_dark = lambda: True
            game.screen.fill((0, 0, 0))
            before = pygame.image.tobytes(game.screen, "RGB")
            with mock.patch.object(
                game.sprites,
                "world_tile_animation_frame_count",
                return_value=1,
            ):
                game.draw_story_relic_guidance()
            self.assertNotEqual(
                pygame.image.tobytes(game.screen, "RGB"), before
            )


class DarkMinimapStairsTests(unittest.TestCase):
    def test_stairs_marker_sticks_once_seen_in_the_dark(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.is_current_floor_dark = lambda: True

            game.tile_visibility_alpha = lambda x, y: 0
            kinds = [kind for kind, _x, _y in game.minimap_markers()]
            self.assertNotIn("stairs", kinds)

            # The lantern touches the stairs once...
            stairs = game.dungeon.stairs
            game.tile_visibility_alpha = (
                lambda x, y: 255 if (x, y) == stairs else 0
            )
            kinds = [kind for kind, _x, _y in game.minimap_markers()]
            self.assertIn("stairs", kinds)

            # ...and the marker persists after the dark swallows them again,
            # while flavor-room markers stay lantern-live only.
            game.tile_visibility_alpha = lambda x, y: 0
            kinds = [kind for kind, _x, _y in game.minimap_markers()]
            self.assertIn("stairs", kinds)
            self.assertNotIn("bar", kinds)
            self.assertNotIn("garden", kinds)


if __name__ == "__main__":
    unittest.main()
