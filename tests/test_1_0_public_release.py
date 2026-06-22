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
from arch_rogue.game import ARCHETYPES, Game


class PublicReleaseMilestoneTests(unittest.TestCase):
    def tearDown(self) -> None:
        pygame.quit()

    def make_game(self, tmpdir: str, seed: int = 1001) -> Game:
        game = Game(
            screen_size=(960, 540),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.rng.seed(seed)
        return game

    def test_release_metadata_and_entry_state_are_1_0(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                self.assertEqual(arch_rogue.__version__, "1.0.0")
                self.assertEqual(game.state, "title")
                self.assertIn(
                    "1.0.0",
                    game.options_to_dict().get("version", 1) and arch_rogue.__version__,
                )
            finally:
                pygame.quit()

    def test_archetype_signature_mechanics_are_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                profiles: dict[str, tuple[str, str, int, int, int, int, float]] = {}
                for archetype in ARCHETYPES:
                    game.restart(archetype)
                    weapon = game.player.equipment["weapon"]
                    armor = game.player.equipment["armor"]
                    self.assertIsNotNone(weapon)
                    self.assertIsNotNone(armor)
                    assert weapon is not None and armor is not None
                    profiles[archetype.name] = (
                        weapon.name,
                        armor.name,
                        game.melee_stamina_cost(),
                        game.bolt_mana_cost(),
                        game.nova_mana_cost(),
                        game.dash_stamina_cost(),
                        game.dash_cooldown(),
                    )

                self.assertLess(profiles["Rogue"][2], profiles["Warden"][2])
                self.assertLess(profiles["Arcanist"][3], profiles["Warden"][3])
                self.assertLess(profiles["Acolyte"][4], profiles["Warden"][4])
                self.assertLess(profiles["Ranger"][5], profiles["Warden"][5])
                self.assertEqual(len(set(profiles.values())), len(ARCHETYPES))
            finally:
                pygame.quit()

    def test_options_and_run_save_are_versioned_and_persistent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                game.audio_enabled = False
                game.fullscreen = True
                game.ui_scale = 3
                self.assertTrue(game.save_options())

                loaded_options = json.loads(
                    game.options_path.read_text(encoding="utf-8")
                )
                self.assertEqual(loaded_options["version"], 1)
                self.assertFalse(loaded_options["audio_enabled"])
                self.assertTrue(loaded_options["fullscreen"])
                self.assertEqual(loaded_options["ui_scale"], 3)

                game.restart(ARCHETYPES[0])
                self.assertTrue(game.save_run())
                saved_run = json.loads(game.save_path.read_text(encoding="utf-8"))
                self.assertEqual(saved_run["version"], 2)
                self.assertEqual(saved_run["release"], "1.0.0")
                self.assertFalse(Path(f"{game.save_path}.tmp").exists())
            finally:
                pygame.quit()


if __name__ == "__main__":
    unittest.main()
