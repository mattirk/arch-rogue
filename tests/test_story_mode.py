from __future__ import annotations

import json
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

import pygame

from arch_rogue.constants import DUNGEON_DEPTH
from arch_rogue.content import STORY_CORPUS
from arch_rogue.game import ARCHETYPES, Game
from arch_rogue.quest_assets import load_quest_cutscene_library
from arch_rogue.story import StoryEngine, story_state_to_dict


class StoryModeTests(unittest.TestCase):
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

    def confirm_story_intro(self, game: Game, choice_index: int = 0) -> None:
        if game.story_intro_pending:
            self.assertTrue(game.choose_story_relic_path(choice_index))

    def story_relic_option_index(self, game: Game, choice_key: str) -> int:
        for index, (key, _label, _detail) in enumerate(
            game.story_relic_choice_options()
        ):
            if key == choice_key:
                return index
        self.fail(f"story relic choice {choice_key!r} was not available")
        return -1

    def test_story_guidance_uses_tight_local_alpha_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                self.confirm_story_intro(game)
                game.story_relic_guidance_enabled = True
                game.story_intro_pending = False
                game.player.moving = False
                px = float(game.player.x)
                py = float(game.player.y)
                step = 1.0 if int(px) + 4 < len(game.dungeon.tiles) else -1.0
                route = [(px + step * index, py) for index in range(4)]
                target = route[-1]
                game.screen.fill((9, 11, 15))
                before = pygame.image.tobytes(game.screen, "RGB")
                with (
                    patch.object(
                        game,
                        "story_relic_target_position",
                        return_value=target,
                    ),
                    patch.object(
                        game,
                        "story_relic_guidance_route",
                        return_value=route,
                    ),
                    patch.object(game, "tile_visibility_alpha", return_value=255),
                    patch.object(
                        game,
                        "_guidance_glow_layer",
                        wraps=game._guidance_glow_layer,
                    ) as glow_layer,
                ):
                    game.draw_story_relic_guidance()
                    game.draw_story_relic_guidance()

                self.assertEqual(glow_layer.call_count, 2)
                self.assertTrue(glow_layer.call_args_list[0].kwargs["clear"])
                self.assertFalse(glow_layer.call_args_list[1].kwargs["clear"])

                rect = game._guidance_glow_blit_rect
                self.assertIsNotNone(rect)
                assert rect is not None
                self.assertTrue(game.screen.get_rect().contains(rect))
                layer_w, layer_h = game._mobile_guidance_surface_size
                self.assertEqual(rect.size, (layer_w, layer_h))
                self.assertLess(
                    layer_w * layer_h,
                    game.screen.get_width() * game.screen.get_height() // 3,
                )
                self.assertNotEqual(pygame.image.tobytes(game.screen, "RGB"), before)
            finally:
                game.story_relic_guidance_enabled = False

    def test_story_corpus_and_engine_are_deterministic_and_backstory_aligned(
        self,
    ) -> None:
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
                self.assertTrue(game.story_intro_pending)
                pending_hint = game.current_interaction_hint()
                self.assertIsNotNone(pending_hint)
                assert pending_hint is not None
                self.assertEqual(pending_hint[0], "1-3")
                self.assertIn("Guest dialog", pending_hint[1])
                self.assertTrue(game.choose_story_relic_path(2))
                self.assertFalse(game.story_intro_pending)

                guest = game.story_guests[0]
                game.player.x = guest.x
                game.player.y = guest.y

                hint = game.current_interaction_hint()
                self.assertIsNotNone(hint)
                assert hint is not None
                self.assertEqual(hint[0], "1-3")
                self.assertIn("Aid", hint[2])
                self.assertIn("Bargain", hint[2])
                self.assertIn("relic power", hint[2])
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
                self.assertGreater(game.story_effect_value("relic_power"), 0)
                self.assertGreater(game.story_effect_value("blood_price"), 0)
                self.assertGreater(game.run_stats.damage_taken, 0)
                self.assertGreater(len(game.items), item_count)
                bargain_items = game.items[item_count:]
                self.assertTrue(
                    any("Relic-Touched" in item.affixes for item in bargain_items)
                )

                saved = json.loads(game.save_path.read_text(encoding="utf-8"))
                self.assertIn("story_state", saved)
                self.assertIn("story_guests", saved)
                self.assertEqual(saved["run_stats"]["story_choices"], 1)
            finally:
                pass

    def test_story_effects_persist_and_future_depth_uses_story_theme(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, seed=2102)
            try:
                assert game.story_state is not None
                self.confirm_story_intro(game)
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
                self.assertTrue(game.story_intro_pending)
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
                self.assertTrue(loaded.story_intro_pending)
                self.assertGreater(loaded.story_effect_value("enemy_pressure"), 0)
                self.assertEqual(loaded.run_stats.story_choices, 1)
                self.assertTrue(
                    any("Defy" in entry for entry in loaded.story_state.log)
                )
            finally:
                pass

    def test_level_intro_blocks_gameplay_until_story_relic_is_chosen(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, seed=2502)
            try:
                self.assertEqual(game.state, "playing")
                self.assertTrue(game.story_intro_pending)
                starting_depth = game.current_depth
                game.player.x = game.dungeon.stairs[0] + 0.5
                game.player.y = game.dungeon.stairs[1] + 0.5
                game.interact()
                self.assertEqual(game.current_depth, starting_depth)
                self.assertTrue(game.story_intro_pending)
                self.assertTrue(
                    any("Choose 1-3" in floater.text for floater in game.floaters)
                )

                guest = game.current_story_guest_for_depth()
                self.assertIsNotNone(guest)
                assert guest is not None
                self.assertTrue(
                    game.choose_story_relic_path(
                        self.story_relic_option_index(game, "aid")
                    )
                )
                self.assertFalse(game.story_intro_pending)
                relic = game.current_story_relic()
                self.assertIsNotNone(relic)
                assert relic is not None
                self.assertEqual(relic.slot, "story_relic")
                self.assertEqual(game.story_relic_choice_key, "aid")
                self.assertTrue(game.story_relic_guidance_enabled)
                self.assertFalse(game.story_relic_guarded)
                self.assertFalse(
                    any(
                        enemy.elite_modifier == "Relic Guardian"
                        for enemy in game.enemies
                    )
                )
                self.assertLess(math.hypot(relic.x - guest.x, relic.y - guest.y), 3.0)
                self.assertTrue(
                    any(
                        "follow the guiding light" in line
                        for line in game.story_panel_lines()
                    )
                )

                game.player.x = relic.x
                game.player.y = relic.y
                game.interact()
                self.assertIsNone(game.current_story_relic())
                self.assertTrue(game.story_relic_collected)
                self.assertIsNone(game.story_relic_target_position())
            finally:
                pass

    def test_quest_cutscene_assets_and_guest_dialogue_lifecycle(self) -> None:
        # One Arcanist run exercises both the cutscene asset binding (intro omen)
        # and the full guest dialogue-tree lifecycle (save -> load -> resolve).
        # The dialogue lifecycle saves+loads before the intro is dismissed, so the
        # asset-binding section's non-mutating assertions run first; the intro is
        # only dismissed at the end on the original (un-saved) game.
        library = load_quest_cutscene_library()
        self.assertIn("story_guest_omen", library)
        self.assertIn("story_guest_dialogue", library)
        self.assertEqual(
            library["story_guest_omen"]
            .nodes[library["story_guest_omen"].start_node]
            .choice_source,
            "story_relic_options",
        )
        omen_poses = {
            frame.pose
            for frame in library["story_guest_omen"].animations["omen_idle"].frames
        }
        dialogue_poses = {
            frame.pose
            for frame in library["story_guest_dialogue"]
            .animations["dialogue_idle"]
            .frames
        }
        self.assertLessEqual(
            {"guard", "plead", "reach", "reveal", "shudder", "surge", "warn"},
            omen_poses,
        )
        self.assertLessEqual(
            {"defy", "guard", "plead", "price", "reach", "vow", "warn"},
            dialogue_poses,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, seed=2302)
            try:
                # --- Cutscene asset binding (intro omen) ---
                self.assertTrue(game.story_intro_pending)
                self.assertIsNotNone(game.active_cutscene)
                assert game.active_cutscene is not None
                self.assertEqual(game.active_cutscene.asset_id, "story_guest_omen")
                choices = game.active_cutscene_choices()
                self.assertEqual(len(choices), 3)
                self.assertEqual(
                    [choice.choice_key for choice in choices],
                    [key for key, _label, _detail in game.story_relic_choice_options()],
                )

                # --- Guest dialogue-tree lifecycle (save before dismissing) ---
                self.assertTrue(game.save_run())
                saved = json.loads(game.save_path.read_text(encoding="utf-8"))
                self.assertEqual(
                    saved["active_cutscene"]["asset_id"], "story_guest_omen"
                )

                loaded = Game(
                    screen_size=(820, 540),
                    headless=True,
                    save_path=game.save_path,
                )
                self.assertTrue(loaded.load_run(), loaded.last_load_error)
                self.assertTrue(loaded.story_intro_pending)
                self.assertIsNotNone(loaded.active_cutscene)
                assert loaded.active_cutscene is not None
                self.assertEqual(loaded.active_cutscene.asset_id, "story_guest_omen")
                self.assertTrue(loaded.choose_active_cutscene_option(1))

                guest = loaded.story_guests[0]
                loaded.player.x = guest.x
                loaded.player.y = guest.y
                loaded.interact()
                self.assertIsNotNone(loaded.active_cutscene)
                assert loaded.active_cutscene is not None
                self.assertEqual(
                    loaded.active_cutscene.asset_id, "story_guest_dialogue"
                )
                dialogue_choices = loaded.active_cutscene_choices()
                self.assertEqual(
                    [choice.choice_key for choice in dialogue_choices],
                    ["aid", "bargain", "defy"],
                )
                self.assertTrue(loaded.choose_active_cutscene_option(2))
                self.assertTrue(guest.resolved)
                self.assertEqual(guest.resolved_choice, "defy")
                self.assertEqual(loaded.run_stats.story_choices, 1)
                self.assertIsNone(loaded.active_cutscene)

                # --- Dismiss the intro on the original (un-saved) game ---
                self.assertTrue(game.choose_active_cutscene_option(0))
                self.assertFalse(game.story_intro_pending)
                self.assertIsNone(game.active_cutscene)
            finally:
                pass


if __name__ == "__main__":
    unittest.main()
