from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame

import arch_rogue
from arch_rogue.constants import DUNGEON_DEPTH
from arch_rogue.content import STORY_CORPUS
from arch_rogue.game import ARCHETYPES, Game
from arch_rogue.story import StoryEngine, story_state_to_dict


class StoryMode20Tests(unittest.TestCase):
    def tearDown(self) -> None:
        pygame.quit()

    def make_game(self, tmpdir: str, seed: int = 2002) -> Game:
        game = Game(
            screen_size=(820, 540),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.rng.seed(seed)
        game.restart(ARCHETYPES[2])
        return game

    def test_story_corpus_and_engine_are_deterministic_and_backstory_aligned(
        self,
    ) -> None:
        self.assertEqual(arch_rogue.__version__, "2.0.0")
        self.assertGreaterEqual(len(STORY_CORPUS["factions"]), 8)
        self.assertGreaterEqual(len(STORY_CORPUS["relics"]), 8)
        self.assertGreaterEqual(len(STORY_CORPUS["guest_templates"]), 8)
        self.assertGreaterEqual(len(STORY_CORPUS["dilemmas"]), DUNGEON_DEPTH)
        self.assertIn("Arcanist", STORY_CORPUS["backstories"])

        first = StoryEngine.generate(
            424242, "Arcanist", 11, "Crypt of Ash", "Blood Moon"
        )
        second = StoryEngine.generate(
            424242, "Arcanist", 11, "Crypt of Ash", "Blood Moon"
        )
        self.assertEqual(story_state_to_dict(first), story_state_to_dict(second))
        self.assertIn("Arcanist", first.player_backstory)
        self.assertEqual(len(first.beats), DUNGEON_DEPTH)
        self.assertEqual([beat.depth for beat in first.beats], list(range(1, 11)))
        self.assertTrue(all(len(beat.choices) == 3 for beat in first.beats))

    def test_story_guest_choice_updates_effects_run_stats_and_save_version(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                self.assertIsNotNone(game.story_state)
                assert game.story_state is not None
                self.assertEqual(game.story_seed, game.story_state.seed)
                self.assertEqual(len(game.story_state.beats), DUNGEON_DEPTH)
                self.assertTrue(game.story_guests)
                guest = game.story_guests[0]
                game.player.x = guest.x
                game.player.y = guest.y

                hint = game.current_interaction_hint()
                self.assertIsNotNone(hint)
                assert hint is not None
                self.assertEqual(hint[0], "1-3")
                self.assertIn("Aid", hint[2])
                self.assertIn("Bargain", hint[2])
                self.assertIn("Defy", hint[2])

                game.interact()
                game.interact()
                self.assertTrue(guest.met)
                self.assertEqual(game.run_stats.guests_met, 1)

                item_count = len(game.items)
                self.assertTrue(game.resolve_story_choice(guest, 1))
                self.assertEqual(game.run_stats.guests_met, 1)
                self.assertTrue(guest.resolved)
                self.assertEqual(guest.resolved_choice, "bargain")
                self.assertEqual(game.run_stats.story_choices, 1)
                self.assertGreater(game.story_effect_value("loot_bonus"), 0)
                self.assertGreater(game.story_effect_value("trap_bonus"), 0)
                self.assertGreater(len(game.items), item_count)

                saved = json.loads(game.save_path.read_text(encoding="utf-8"))
                self.assertEqual(saved["version"], 4)
                self.assertEqual(saved["release"], "2.0.0")
                self.assertIn("story_state", saved)
                self.assertIn("story_guests", saved)
                self.assertEqual(saved["run_stats"]["story_choices"], 1)
            finally:
                pygame.quit()

    def test_story_effects_persist_and_future_depth_uses_story_theme(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, seed=2102)
            try:
                assert game.story_state is not None
                first_guest = game.story_guests[0]
                game.player.x = first_guest.x
                game.player.y = first_guest.y
                self.assertTrue(game.resolve_story_choice(first_guest, 2))
                self.assertGreater(game.story_effect_value("enemy_pressure"), 0)
                next_theme_name = game.story_state.beats[1].theme_name

                game.player.x = game.dungeon.stairs[0] + 0.5
                game.player.y = game.dungeon.stairs[1] + 0.5
                game.interact()
                self.assertEqual(game.current_depth, 2)
                self.assertEqual(game.theme.name, next_theme_name)
                self.assertTrue(game.story_guests)
                self.assertEqual(game.story_guests[0].depth, 2)

                self.assertTrue(game.save_run())
                loaded = Game(
                    screen_size=(820, 540),
                    headless=True,
                    save_path=game.save_path,
                )
                self.assertTrue(loaded.load_run(), loaded.last_load_error)
                self.assertIsNotNone(loaded.story_state)
                assert loaded.story_state is not None
                self.assertEqual(loaded.current_depth, 2)
                self.assertGreater(loaded.story_effect_value("enemy_pressure"), 0)
                self.assertEqual(loaded.run_stats.story_choices, 1)
                self.assertTrue(
                    any("Defy" in entry for entry in loaded.story_state.log)
                )
            finally:
                pygame.quit()

    def test_story_guest_and_menus_are_renderable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, seed=2202)
            try:
                self.assertTrue(game.story_guests)
                guest = game.story_guests[0]
                game.player.x = guest.x
                game.player.y = guest.y
                game.draw_help_overlay()
                game.draw()
                game.state = "title"
                game.draw_title_menu()
                game.state = "about"
                game.draw_about_screen()
            finally:
                pygame.quit()


if __name__ == "__main__":
    unittest.main()
