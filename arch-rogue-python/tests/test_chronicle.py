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

"""5.0.1 Chronicle of descents: title entry, navigation, rendering, records."""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame

from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game


def make_game(tmpdir: str) -> Game:
    game = Game(
        screen_size=(1100, 620),
        headless=True,
        save_path=Path(tmpdir) / "run.json",
    )
    game.options_path = Path(tmpdir) / "options.json"
    game.meta_progress = game.default_meta_progress()
    game.run_history = []
    return game


def post_key(game: Game, key: int, mod: int = 0) -> None:
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key, mod=mod))
    game.handle_events()


def sample_records(count: int) -> list[dict]:
    records = []
    for index in range(count):
        records.append(
            {
                "outcome": "victory" if index % 3 == 0 else "death",
                "class": ("Warden", "Rogue", "Arcanist")[index % 3],
                "depth": 1 + index % 10,
                "time": 61 + index * 37,
                "difficulty": "Medium",
                "modifier": "Blood Moon",
                "kills": 10 + index,
                "bosses": ["Ash Gallows Knight"] if index % 2 else [],
                "notable_loot": ["Emberbrand"] if index % 2 else [],
                "cause": "slain by a Crypt Brute" if index % 3 else "",
                "ended": "2026-08-08",
            }
        )
    return records


class ChronicleEntryTests(unittest.TestCase):
    def test_title_menu_has_six_rows_and_v_opens_the_chronicle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            self.assertEqual(game.TITLE_ROW_COUNT, 6)
            game.draw()
            self.assertEqual(len(game._title_row_rects), 6)

            post_key(game, pygame.K_v)
            self.assertEqual(game.state, "chronicle")
            self.assertEqual(game.chronicle_selection, 0)

            post_key(game, pygame.K_ESCAPE)
            self.assertEqual(game.state, "title")

    def test_title_row_activation_opens_the_chronicle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.title_selection = game.TITLE_CHRONICLE_ROW
            game._activate_title_selection()
            self.assertEqual(game.state, "chronicle")

    def test_selection_moves_and_clamps(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.run_history = sample_records(3)
            game.open_chronicle()
            post_key(game, pygame.K_DOWN)
            post_key(game, pygame.K_DOWN)
            self.assertEqual(game.chronicle_selection, 2)
            post_key(game, pygame.K_DOWN)
            self.assertEqual(game.chronicle_selection, 2)
            post_key(game, pygame.K_UP)
            self.assertEqual(game.chronicle_selection, 1)
            game.move_chronicle_selection(-5)
            self.assertEqual(game.chronicle_selection, 0)

    def test_empty_history_selection_stays_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.open_chronicle()
            game.move_chronicle_selection(1)
            self.assertEqual(game.chronicle_selection, 0)


class ChronicleRenderTests(unittest.TestCase):
    def test_draw_publishes_row_rects_and_visible_range(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.run_history = sample_records(12)
            game.open_chronicle()
            game.draw()
            rects = game._chronicle_row_rects
            self.assertTrue(rects)
            start, stop = game._chronicle_visible_range
            self.assertEqual(start, 0)
            self.assertEqual(stop - start, len(rects))

            # Selecting the oldest record scrolls the window to include it.
            game.chronicle_selection = 11
            game.draw()
            start, stop = game._chronicle_visible_range
            self.assertEqual(stop, 12)
            self.assertLessEqual(start, 11)

    def test_empty_history_renders_the_empty_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.open_chronicle()
            game.draw()
            self.assertEqual(game._chronicle_row_rects, ())

    def test_legacy_records_without_new_fields_render(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.run_history = [
                {
                    "outcome": "death",
                    "class": "Ranger",
                    "depth": 4,
                    "time": 300,
                    "difficulty": "Hard",
                    "modifier": "Thin Veil",
                    "kills": 30,
                    "bosses": [],
                    "notable_loot": [],
                    "cause": "",
                }
            ]
            game.open_chronicle()
            game.draw()
            self.assertEqual(len(game._chronicle_row_rects), 1)


class ChronicleRecordTests(unittest.TestCase):
    def test_finalized_runs_stamp_the_ended_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.rng.seed(6001)
            game.restart(ARCHETYPES[0])
            if game.story_intro_pending:
                self.assertTrue(game.choose_story_relic_path(0))
            game.active_cutscene = None
            game.finalize_run("death")
            self.assertEqual(len(game.run_history), 1)
            record = game.run_history[0]
            self.assertEqual(record["ended"], time.strftime("%Y-%m-%d"))
            self.assertEqual(record["class"], "Warden")


if __name__ == "__main__":
    unittest.main()
