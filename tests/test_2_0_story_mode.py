from __future__ import annotations

import json
import math
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
from arch_rogue.quest_assets import RuntimeDialogueChoice, load_quest_cutscene_library
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

    def test_story_corpus_and_engine_are_deterministic_and_backstory_aligned(
        self,
    ) -> None:
        self.assertEqual(arch_rogue.__version__, "3.5.0")
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
                self.assertEqual(saved["version"], 4)
                self.assertEqual(saved["release"], "3.5.0")
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
                pygame.quit()

    def test_story_effects_directly_modify_combat_resources_and_hunters(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, seed=2302)
            try:
                assert game.story_state is not None
                game.story_state.effects["damage_resist"] = 0.30
                raw_damage = 40
                baseline = max(1, raw_damage - game.player.armor())
                taken = game.take_player_damage(raw_damage, source="trap")
                self.assertLess(taken, baseline)

                game.player.hp = game.player.max_hp
                game.player.mana = game.player.max_mana
                game.projectiles.clear()
                game.story_state.effects["damage_bonus"] = 0.20
                game.story_state.effects["relic_power"] = 0.20
                game.story_state.effects["blood_price"] = 0.25
                base_bolt_damage = 14 + game.player.level * 2 + game.player.spell_bonus
                before_hp = game.player.hp
                game.player_cast_bolt()
                self.assertTrue(game.projectiles)
                self.assertGreater(
                    max(projectile.damage for projectile in game.projectiles),
                    base_bolt_damage,
                )
                self.assertLess(game.player.hp, before_hp)

                self.assertTrue(game.enemies)
                game.story_state.effects["healing_echo"] = 1.0
                game.player.hp = game.player.max_hp - 20
                before_heal = game.player.hp
                game.kill_enemy(game.enemies[0])
                self.assertGreater(game.player.hp, before_heal)
            finally:
                pygame.quit()

    def test_unanswered_story_guest_hardens_next_floor(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, seed=2402)
            try:
                assert game.story_state is not None
                beat = game.story_state.beats[0]
                self.assertEqual(beat.resolved_choice, "")

                game.descend_to_next_depth()

                self.assertEqual(game.current_depth, 2)
                self.assertEqual(beat.resolved_choice, "unanswered")
                self.assertGreater(game.story_effect_value("hunter_pressure"), 0)
                self.assertGreater(game.story_effect_value("boss_pressure"), 0)
                self.assertTrue(
                    any(
                        "Hunter" in enemy.name or "Story-Marked" in enemy.name
                        for enemy in game.enemies
                    )
                )
                self.assertEqual(game.run_stats.story_choices, 0)
            finally:
                pygame.quit()

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
                pygame.quit()

    def test_story_relic_choices_change_location_render_cues_and_persist(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            positions: dict[str, tuple[float, float]] = {}
            expected_traits = {
                "aid": (True, False),
                "bargain": (True, True),
                "defy": (False, True),
            }
            for expected_key in ("aid", "bargain", "defy"):
                game = self.make_game(tmpdir, seed=2602)
                try:
                    self.assertTrue(game.story_intro_pending)
                    guest = game.current_story_guest_for_depth()
                    self.assertIsNotNone(guest)
                    assert guest is not None
                    final_room = game.dungeon.rooms[-1]
                    final_x, final_y = (
                        final_room.center[0] + 0.5,
                        final_room.center[1] + 0.5,
                    )

                    self.assertTrue(
                        game.choose_story_relic_path(
                            self.story_relic_option_index(game, expected_key)
                        )
                    )
                    expected_guidance, expected_guarded = expected_traits[expected_key]
                    self.assertEqual(game.story_relic_choice_key, expected_key)
                    self.assertEqual(
                        game.story_relic_guidance_enabled, expected_guidance
                    )
                    self.assertEqual(game.story_relic_guarded, expected_guarded)
                    relic = game.current_story_relic()
                    self.assertIsNotNone(relic)
                    assert relic is not None
                    positions[expected_key] = (round(relic.x, 2), round(relic.y, 2))

                    guardians = [
                        enemy
                        for enemy in game.enemies
                        if enemy.elite_modifier == "Relic Guardian"
                    ]
                    self.assertEqual(bool(guardians), expected_guarded)
                    if expected_guarded:
                        guardian = guardians[0]
                        self.assertLess(
                            math.hypot(guardian.x - relic.x, guardian.y - relic.y), 3.0
                        )
                        self.assertGreater(guardian.max_hp, 40)

                    if expected_key == "aid":
                        self.assertLess(
                            math.hypot(relic.x - guest.x, relic.y - guest.y), 3.0
                        )
                    elif expected_key == "bargain" and game.secrets:
                        self.assertTrue(any(secret.revealed for secret in game.secrets))
                    elif expected_key == "defy":
                        relic_to_final = math.hypot(
                            relic.x - final_x, relic.y - final_y
                        )
                        guest_to_final = math.hypot(
                            guest.x - final_x, guest.y - final_y
                        )
                        self.assertLess(relic_to_final, guest_to_final)

                    self.assertEqual(
                        game.story_relic_target_position(), (relic.x, relic.y)
                    )
                    panel_lines = game.story_panel_lines()
                    if expected_guidance:
                        self.assertTrue(
                            any(
                                "follow the guiding light" in line
                                for line in panel_lines
                            )
                        )
                        route = game.story_relic_guidance_route((relic.x, relic.y))
                        self.assertGreaterEqual(len(route), 2)
                        self.assertTrue(
                            all(game.dungeon.is_floor(x, y) for x, y in route)
                        )
                        samples = game.sample_guidance_route(route, 7)
                        self.assertTrue(
                            all(game.dungeon.is_floor(x, y) for x, y in samples)
                        )
                    else:
                        self.assertTrue(
                            any("no guiding light" in line for line in panel_lines)
                        )
                    if expected_guarded:
                        self.assertTrue(
                            any(
                                "guarded by a relic guardian" in line
                                for line in panel_lines
                            )
                        )
                    game.draw()
                    saved = json.loads(game.save_path.read_text(encoding="utf-8"))
                    self.assertFalse(saved["story_intro_pending"])
                    self.assertEqual(saved["story_relic_choice_key"], expected_key)
                    self.assertEqual(saved["story_relic_position"], [relic.x, relic.y])
                    self.assertEqual(
                        saved["story_relic_guidance_enabled"], expected_guidance
                    )
                    self.assertEqual(saved["story_relic_guarded"], expected_guarded)

                    loaded = Game(
                        screen_size=(820, 540),
                        headless=True,
                        save_path=game.save_path,
                    )
                    self.assertTrue(loaded.load_run(), loaded.last_load_error)
                    self.assertFalse(loaded.story_intro_pending)
                    self.assertEqual(loaded.story_relic_choice_key, expected_key)
                    self.assertEqual(loaded.story_relic_position, (relic.x, relic.y))
                    self.assertEqual(
                        loaded.story_relic_guidance_enabled, expected_guidance
                    )
                    self.assertEqual(loaded.story_relic_guarded, expected_guarded)
                    self.assertIsNotNone(loaded.current_story_relic())
                finally:
                    pygame.quit()
            self.assertGreater(len(set(positions.values())), 1)

    def test_story_intro_overlay_renders_all_three_opening_choices(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = Game(
                screen_size=(640, 480),
                headless=True,
                save_path=Path(tmpdir) / "run.json",
            )
            game.options_path = Path(tmpdir) / "options.json"
            game.rng.seed(2702)
            game.restart(ARCHETYPES[2])
            try:
                self.assertTrue(game.story_intro_pending)
                hidden_terms = (
                    "guiding",
                    "light",
                    "guardian",
                    "guarded",
                    "unguarded",
                )
                consequence_hint = game.story_intro_lines()[-1].lower()
                self.assertFalse(any(term in consequence_hint for term in hidden_terms))
                options = game.story_relic_choice_options()
                self.assertEqual(len(options), 3)
                option_keys = [key for key, _label, _detail in options]
                self.assertCountEqual(option_keys, ["aid", "bargain", "defy"])
                self.assertNotEqual(option_keys, ["aid", "bargain", "defy"])
                for _key, label, detail in options:
                    visible_text = f"{label} {detail}".lower()
                    self.assertFalse(any(term in visible_text for term in hidden_terms))
                original_rect = pygame.draw.rect
                choice_boxes: list[pygame.Rect] = []

                def record_rect(surface, color, rect, *args, **kwargs):
                    if color == (24, 19, 30, 238):
                        choice_boxes.append(pygame.Rect(rect))
                    return original_rect(surface, color, rect, *args, **kwargs)

                pygame.draw.rect = record_rect
                try:
                    game.draw_story_intro_overlay()
                finally:
                    pygame.draw.rect = original_rect
                self.assertEqual(len(choice_boxes), 3)
            finally:
                pygame.quit()

    def test_cutscene_response_layout_expands_for_wrapped_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = Game(
                screen_size=(640, 480),
                headless=True,
                save_path=Path(tmpdir) / "run.json",
            )
            game.options_path = Path(tmpdir) / "options.json"
            game.rng.seed(2703)
            game.restart(ARCHETYPES[2])
            try:
                width, _height = game.screen.get_size()
                panel_w = min(width - game.ui(28), game.ui(920))
                pad = max(game.ui(14), 18)
                choice_w = panel_w - pad * 2
                text_width = game.cutscene_response_text_width(choice_w)
                label = "Swear the lantern-oath before the drowned archive"
                detail = (
                    "Promise blood, memory, and every unquiet name you carry so the "
                    "guest can open a hidden road through the ruins without silencing "
                    "the warning bells behind you."
                )

                label_lines, detail_lines = game.cutscene_response_lines(
                    label, detail, text_width
                )
                height = game.cutscene_response_height(label, detail, choice_w)
                required_height = (
                    len(label_lines) * game.small_font.get_height()
                    + game.ui(3)
                    + len(detail_lines) * game.tiny_font.get_height()
                    + game.ui(16)
                )

                self.assertGreater(len(detail_lines), 1)
                self.assertGreater(height, game.ui(44))
                self.assertGreaterEqual(height, required_height)
            finally:
                pygame.quit()

    def test_active_cutscene_overlay_draws_full_wrapped_response_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = Game(
                screen_size=(640, 480),
                headless=True,
                save_path=Path(tmpdir) / "run.json",
            )
            game.options_path = Path(tmpdir) / "options.json"
            game.rng.seed(2704)
            game.restart(ARCHETYPES[2])
            try:
                self.assertIsNotNone(game.active_cutscene)
                game.reveal_active_cutscene_narration()
                long_detail = (
                    "The guest answers with a cinematic vow about ash, bells, "
                    "bloodlit stairs, and a relic shadow that must remain visible "
                    "across several wrapped response lines."
                )
                choices = [
                    RuntimeDialogueChoice(
                        label="Accept the vow",
                        detail=long_detail,
                        choice_key="aid",
                    )
                ]
                game.active_cutscene_choices = lambda: choices

                width, _height = game.screen.get_size()
                panel_w = min(width - game.ui(28), game.ui(920))
                pad = max(game.ui(14), 18)
                choice_w = panel_w - pad * 2
                text_width = game.cutscene_response_text_width(choice_w)
                expected_detail_lines = game.wrap_ui_text(
                    long_detail, game.tiny_font, text_width
                )
                self.assertGreater(len(expected_detail_lines), 1)

                captured: list[str] = []
                original_draw_ui_text = game.draw_ui_text

                def capture_draw_ui_text(
                    surface, text, font, color, rect, *args, **kwargs
                ):
                    captured.append(text)
                    return original_draw_ui_text(
                        surface, text, font, color, rect, *args, **kwargs
                    )

                game.draw_ui_text = capture_draw_ui_text
                game.draw_quest_cutscene_overlay()

                for line in expected_detail_lines:
                    self.assertIn(line, captured)
            finally:
                pygame.quit()

    def test_story_intro_overlay_draws_full_wrapped_response_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = Game(
                screen_size=(640, 480),
                headless=True,
                save_path=Path(tmpdir) / "run.json",
            )
            game.options_path = Path(tmpdir) / "options.json"
            game.rng.seed(2705)
            game.restart(ARCHETYPES[2])
            try:
                long_detail = (
                    "Choose a path described by the narrator with enough omen, "
                    "consequence, hidden architecture, and relic imagery to wrap "
                    "through multiple readable response lines."
                )
                options = [("aid", "Lift the lantern", long_detail)]
                game.story_relic_choice_options = lambda: options

                width, _height = game.screen.get_size()
                panel_w = min(width - game.ui(28), game.ui(900))
                pad = max(game.ui(14), 18)
                choice_w = panel_w - pad * 2
                text_width = game.cutscene_response_text_width(choice_w)
                expected_detail_lines = game.wrap_ui_text(
                    long_detail, game.tiny_font, text_width
                )
                self.assertGreater(len(expected_detail_lines), 1)

                captured: list[str] = []
                original_draw_ui_text = game.draw_ui_text

                def capture_draw_ui_text(
                    surface, text, font, color, rect, *args, **kwargs
                ):
                    captured.append(text)
                    return original_draw_ui_text(
                        surface, text, font, color, rect, *args, **kwargs
                    )

                game.draw_ui_text = capture_draw_ui_text
                game.draw_story_intro_overlay()

                for line in expected_detail_lines:
                    self.assertIn(line, captured)
            finally:
                pygame.quit()

    def test_story_intro_choices_are_dynamic_stable_and_corpus_based(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, seed=2802)
            try:
                assert game.story_state is not None
                beat = game.current_story_beat()
                self.assertIsNotNone(beat)
                assert beat is not None

                first_options = game.story_relic_choice_options()
                self.assertEqual(len(first_options), 3)
                first_keys = [key for key, _label, _detail in first_options]
                self.assertCountEqual(first_keys, ["aid", "bargain", "defy"])
                self.assertNotEqual(first_keys, ["aid", "bargain", "defy"])
                self.assertEqual(first_options, game.story_relic_choice_options())
                self.assertCountEqual(
                    [key for key, _label, _detail in first_options],
                    [choice.key for choice in beat.choices[:3]],
                )

                visible_text = " ".join(
                    f"{label} {detail}" for _key, label, detail in first_options
                ).lower()
                story_terms = []
                for source in (
                    beat.guest_name,
                    beat.guest_role,
                    beat.title,
                    game.story_state.relic_name,
                ):
                    for token in (
                        game.safe_story_choice_text(source, "").lower().split()
                    ):
                        token = token.strip("'s;:,.—")
                        if len(token) >= 4:
                            story_terms.append(token)
                corpus_terms = []
                for choice in beat.choices[:3]:
                    for token in (
                        game.safe_story_choice_text(choice.intent, "").lower().split()
                    ):
                        token = token.strip("'s;:,.—")
                        if len(token) >= 5:
                            corpus_terms.append(token)
                self.assertTrue(any(term in visible_text for term in story_terms))
                self.assertTrue(any(term in visible_text for term in corpus_terms))

                self.assertTrue(game.save_run())
                loaded = Game(
                    screen_size=(820, 540),
                    headless=True,
                    save_path=game.save_path,
                )
                self.assertTrue(loaded.load_run(), loaded.last_load_error)
                self.assertEqual(first_options, loaded.story_relic_choice_options())

                game.current_depth = 2
                second_depth_options = game.story_relic_choice_options()
                self.assertNotEqual(first_options, second_depth_options)
            finally:
                pygame.quit()

    def test_quest_cutscene_assets_bind_generated_story_choices(self) -> None:
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
            game = self.make_game(tmpdir, seed=2301)
            try:
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
                self.assertTrue(game.choose_active_cutscene_option(0))
                self.assertFalse(game.story_intro_pending)
                self.assertIsNone(game.active_cutscene)
            finally:
                pygame.quit()

    def test_active_cutscene_persists_and_guest_dialogue_tree_resolves(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, seed=2302)
            try:
                self.assertIsNotNone(game.active_cutscene)
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
                choices = loaded.active_cutscene_choices()
                self.assertEqual(
                    [choice.choice_key for choice in choices],
                    ["aid", "bargain", "defy"],
                )
                self.assertTrue(loaded.choose_active_cutscene_option(2))
                self.assertTrue(guest.resolved)
                self.assertEqual(guest.resolved_choice, "defy")
                self.assertEqual(loaded.run_stats.story_choices, 1)
                self.assertIsNone(loaded.active_cutscene)
            finally:
                pygame.quit()

    def test_story_guest_and_menus_are_renderable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, seed=2202)
            try:
                self.assertTrue(game.story_guests)
                assert game.story_state is not None
                guest = game.story_guests[0]
                game.player.x = guest.x
                game.player.y = guest.y
                game.story_state.effects["damage_resist"] = 0.10
                panel_lines = game.story_panel_lines()
                self.assertTrue(any(line.startswith("Goal:") for line in panel_lines))
                self.assertTrue(any("Story forces:" in line for line in panel_lines))
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
