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
from arch_rogue.game import ARCHETYPES, DUNGEON_DEPTH, ENEMY_DEFINITIONS, Game


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

    def test_release_metadata_and_entry_state_are_current(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                self.assertEqual(arch_rogue.__version__, "2.0.0")
                self.assertEqual(game.state, "title")
                self.assertIn(
                    "2.0.0",
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

    def test_new_enemy_roster_has_unique_sprites(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                enemy_names = {definition.name for definition in ENEMY_DEFINITIONS}
                for name in {
                    "Ash Hound",
                    "Rune Sentinel",
                    "Plague Toad",
                    "Hollow Knight",
                }:
                    self.assertIn(name, enemy_names)
                    self.assertIn(name, game.sprites.enemies)
                self.assertGreaterEqual(len(game.sprites.enemies), len(enemy_names))
            finally:
                pygame.quit()

    def test_skill_variation_and_compact_menus_render(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = Game(
                screen_size=(640, 480),
                headless=True,
                save_path=Path(tmpdir) / "run.json",
            )
            game.options_path = Path(tmpdir) / "options.json"
            try:
                skill_profiles = set()
                for archetype in ARCHETYPES:
                    game.restart(archetype)
                    skill_profiles.add(game.skill_names())
                self.assertEqual(len(skill_profiles), len(ARCHETYPES))

                game.state = "title"
                game.draw_title_menu()
                game.state = "options"
                game.draw_options_menu()
                game.state = "about"
                game.draw_about_screen()
                fresh_game = Game(
                    screen_size=(640, 480),
                    headless=True,
                    save_path=Path(tmpdir) / "fresh_run.json",
                )
                fresh_game.state = "archetype_select"
                fresh_game.draw_archetype_select()

                game.state = "archetype_select"
                for archetype in ARCHETYPES:
                    self.assertIn(archetype.name, game.sprites.player_sprites)
                    sprite = game.sprites.player_sprites[archetype.name]
                    self.assertGreater(sprite.get_width(), 0)
                    self.assertGreater(sprite.get_height(), 0)
                    game.selected_archetype = archetype
                    game.draw_archetype_select()
                game.show_help = True
                game.draw_help_overlay()
                game.inventory_open = True
                game.draw_inventory()
                game.state = "dead"
                game.draw_state_overlay()
            finally:
                pygame.quit()

    def test_options_and_run_save_are_versioned_and_persistent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                game.audio_enabled = False
                game.fullscreen = True
                game.ui_scale = 3
                game.difficulty_name = "Hard"
                game.hell_unlocked = False
                self.assertTrue(game.save_options())

                loaded_options = json.loads(
                    game.options_path.read_text(encoding="utf-8")
                )
                self.assertEqual(loaded_options["version"], 1)
                self.assertFalse(loaded_options["audio_enabled"])
                self.assertTrue(loaded_options["fullscreen"])
                self.assertEqual(loaded_options["ui_scale"], 3)
                self.assertEqual(loaded_options["difficulty"], "Hard")
                self.assertFalse(loaded_options["hell_unlocked"])

                game.restart(ARCHETYPES[0])
                self.assertTrue(game.save_run())
                saved_run = json.loads(game.save_path.read_text(encoding="utf-8"))
                self.assertEqual(saved_run["version"], 4)
                self.assertEqual(saved_run["release"], "2.0.0")
                self.assertEqual(saved_run["difficulty"], "Hard")
                self.assertFalse(Path(f"{game.save_path}.tmp").exists())
            finally:
                pygame.quit()

    def test_difficulty_cycles_and_hell_unlocks_after_first_clear(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, seed=1017)
            try:
                game.difficulty_name = "Hard"
                game.hell_unlocked = False
                self.assertEqual(game.difficulty_profile().name, "Hard")

                game.cycle_difficulty()
                self.assertEqual(game.difficulty_profile().name, "Easy")
                game.cycle_difficulty()
                self.assertEqual(game.difficulty_profile().name, "Medium")
                game.cycle_difficulty()
                self.assertEqual(game.difficulty_profile().name, "Hard")
                game.cycle_difficulty()
                self.assertEqual(game.difficulty_profile().name, "Easy")

                game.difficulty_name = "Hard"
                game.restart(ARCHETYPES[0])
                game.current_depth = DUNGEON_DEPTH
                game.descend_to_next_depth()

                self.assertEqual(game.state, "victory")
                self.assertTrue(game.hell_unlocked)
                self.assertTrue(game.hell_unlocked_this_run)
                options = json.loads(game.options_path.read_text(encoding="utf-8"))
                self.assertTrue(options["hell_unlocked"])

                game.cycle_difficulty()
                self.assertEqual(game.difficulty_profile().name, "Hell")
            finally:
                pygame.quit()


if __name__ == "__main__":
    unittest.main()
