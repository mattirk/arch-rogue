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

"""5.0.1 desktop storage: SDL pref dir + legacy dotfile migration.

Steam Auto-Cloud has per-OS roots for the SDL pref locations but none for the
bare Windows home directory, so desktop saves moved out of home dotfiles.
"""

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

import pygame

from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game
from arch_rogue.mobile import application_storage_directory


class StorageDirectoryTests(unittest.TestCase):
    def test_desktop_uses_the_sdl_pref_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pref = str(Path(tmpdir) / "pref") + os.sep
            Path(pref).mkdir()
            with patch.object(
                pygame.system, "get_pref_path", return_value=pref
            ):
                self.assertEqual(
                    application_storage_directory(False), Path(pref)
                )

    def test_desktop_falls_back_to_home_when_sdl_fails(self) -> None:
        with patch.object(
            pygame.system, "get_pref_path", side_effect=pygame.error("no")
        ):
            self.assertEqual(application_storage_directory(False), Path.home())


class LegacyMigrationTests(unittest.TestCase):
    def _make_game(self, tmpdir: str) -> Game:
        game = Game(
            screen_size=(820, 540),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        return game

    def test_legacy_dotfiles_copy_once_into_the_pref_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            storage = Path(tmpdir) / "pref"
            home.mkdir()
            storage.mkdir()
            (home / ".arch_rogue_options.json").write_text('{"legacy": 1}')
            (home / ".arch_rogue_run.json").write_text('{"legacy_run": 1}')
            (home / ".arch_rogue_steam_queue.json").write_text("[]")

            game = self._make_game(tmpdir)
            game.save_path = storage / "run.json"
            game.options_path = storage / "options.json"
            with patch.object(Path, "home", return_value=home):
                game.migrate_legacy_desktop_storage(storage)

            self.assertEqual(
                (storage / "options.json").read_text(), '{"legacy": 1}'
            )
            self.assertEqual(
                (storage / "run.json").read_text(), '{"legacy_run": 1}'
            )
            self.assertEqual(
                (storage / ".arch_rogue_steam_queue.json").read_text(), "[]"
            )
            # Originals stay behind as a downgrade-safe backup.
            self.assertTrue((home / ".arch_rogue_options.json").is_file())

            # A second migration never overwrites newer files.
            (storage / "options.json").write_text('{"new": 2}')
            with patch.object(Path, "home", return_value=home):
                game.migrate_legacy_desktop_storage(storage)
            self.assertEqual(
                (storage / "options.json").read_text(), '{"new": 2}'
            )

    def test_missing_legacy_files_are_a_no_op(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            storage = Path(tmpdir) / "pref"
            home.mkdir()
            storage.mkdir()
            game = self._make_game(tmpdir)
            game.save_path = storage / "run.json"
            game.options_path = storage / "options.json"
            with patch.object(Path, "home", return_value=home):
                game.migrate_legacy_desktop_storage(storage)
            self.assertFalse((storage / "options.json").exists())
            self.assertFalse((storage / "run.json").exists())

    def test_loaded_legacy_options_round_trip(self) -> None:
        # A migrated options file must actually load: real save_options
        # output copied byte-for-byte parses through load_options.
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = self._make_game(tmpdir)
            writer.rng.seed(4242)
            writer.restart(ARCHETYPES[0])
            if writer.story_intro_pending:
                self.assertTrue(writer.choose_story_relic_path(0))
            writer.run_history.append(
                {
                    "outcome": "death",
                    "class": "Warden",
                    "depth": 3,
                    "time": 512,
                    "difficulty": "Medium",
                    "modifier": "Blood Moon",
                    "kills": 41,
                    "bosses": [],
                    "notable_loot": ["Emberbrand"],
                    "cause": "slain by a Crypt Brute",
                }
            )
            self.assertTrue(writer.save_options())

            home = Path(tmpdir) / "home"
            storage = Path(tmpdir) / "pref"
            home.mkdir()
            storage.mkdir()
            (home / ".arch_rogue_options.json").write_bytes(
                writer.options_path.read_bytes()
            )

            reader = self._make_game(tmpdir)
            reader.save_path = storage / "run.json"
            reader.options_path = storage / "options.json"
            with patch.object(Path, "home", return_value=home):
                reader.migrate_legacy_desktop_storage(storage)
            self.assertTrue(reader.load_options())
            self.assertEqual(len(reader.run_history), 1)
            self.assertEqual(reader.run_history[0]["class"], "Warden")


if __name__ == "__main__":
    unittest.main()
