from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame

from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game
from arch_rogue.models import Item
from arch_rogue.sprites import UiAssetLibrary


class UiLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode((64, 64), pygame.HIDDEN)

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def make_game(
        self,
        tmpdir: str,
        size: tuple[int, int] = (960, 540),
        scale: int = 1,
        *,
        legacy: bool = False,
    ) -> Game:
        game = Game(
            screen_size=size,
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.set_legacy_graphics(legacy)
        game.ui_scale = scale
        game.rebuild_fonts()
        return game

    @staticmethod
    def surface_bytes(surface: pygame.Surface) -> bytes:
        return pygame.image.tobytes(surface, "RGBA")

    def prepare_run(self, game: Game) -> None:
        game.rng.seed(4111)
        game.restart(ARCHETYPES[0])
        if game.story_intro_pending:
            game.choose_story_relic_path(0)
        game.active_cutscene = None
        game.player.inventory = [
            Item(f"Test Blade {index}", "weapon", power=index + 1, rarity="Magic")
            for index in range(8)
        ]

    def test_content_rect_validation_scaling_and_missing_resource(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = pygame.Surface((16, 16), pygame.SRCALPHA)
            source.fill((32, 28, 40, 255))
            pygame.image.save(source, root / "panel.png")
            (root / "ui_manifest.json").write_text(
                json.dumps(
                    {
                        "format_version": 1,
                        "assets": {
                            "slice": {
                                "path": "panel.png",
                                "render": "nine_slice",
                                "insets": [4, 4, 4, 4],
                                "content_insets": [3, 2, 3, 2],
                            },
                            "missing": {
                                "path": "missing.png",
                                "render": "nine_slice",
                                "insets": [4, 4, 4, 4],
                                "content_insets": [3, 2, 3, 2],
                            },
                            "no_metadata": {
                                "path": "panel.png",
                                "render": "scale",
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            library = UiAssetLibrary(root)
            self.assertTrue(library.available, library.load_error)
            self.assertEqual(
                library.content_rect("slice", pygame.Rect(10, 20, 40, 24)),
                pygame.Rect(13, 22, 34, 20),
            )
            self.assertEqual(
                library.content_rect("slice", pygame.Rect(2, 3, 6, 4)),
                pygame.Rect(4, 4, 2, 2),
            )
            self.assertIsNone(
                library.content_rect("missing", pygame.Rect(0, 0, 40, 24))
            )
            self.assertIsNone(
                library.content_rect("no_metadata", pygame.Rect(0, 0, 40, 24))
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "ui_manifest.json").write_text(
                json.dumps(
                    {
                        "format_version": 1,
                        "assets": {
                            "bad": {
                                "path": "panel.png",
                                "render": "scale",
                                "content_insets": [1, -1, 1, 1],
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            invalid = UiAssetLibrary(root)
            self.assertFalse(invalid.available)
            self.assertIn("insets", invalid.load_error)

    def test_fitted_layout_is_modern_only_and_restores_saved_scale_and_fonts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, (640, 480), 4)
            original_fonts = (
                game.tiny_font,
                game.small_font,
                game.font,
                game.heading_font,
                game.big_font,
                game.title_font,
            )
            original_height = game.font.get_height()
            with game.fitted_ui_layout((960, 540)) as effective:
                self.assertEqual(effective, 1.0)
                self.assertEqual(game.ui_scale, 4)
                self.assertEqual(game.ui(10), 10)
                self.assertLess(game.font.get_height(), original_height)
            self.assertEqual(game.ui_scale, 4)
            self.assertEqual(game.ui(10), 40)
            self.assertEqual(
                (
                    game.tiny_font,
                    game.small_font,
                    game.font,
                    game.heading_font,
                    game.big_font,
                    game.title_font,
                ),
                original_fonts,
            )
            self.assertFalse(hasattr(game, "_ui_scale_override"))

            game.set_legacy_graphics(True)
            with game.fitted_ui_layout((960, 540)) as effective:
                self.assertEqual(effective, 4.0)
                self.assertEqual(game.ui(10), 40)

    def test_authored_panels_and_rows_do_not_receive_static_legacy_chrome(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            menu = game.menus
            panel_rect = pygame.Rect(80, 70, 720, 340)
            game.screen.fill((0, 0, 0))
            with patch("pygame.draw.rect", wraps=pygame.draw.rect) as draw_rect:
                self.assertTrue(menu.panel(panel_rect))
            screen_rect_calls = [
                call for call in draw_rect.call_args_list if call.args[0] is game.screen
            ]
            self.assertEqual(screen_rect_calls, [])

            inset_rect = pygame.Rect(120, 100, 360, 140)
            game.screen.fill((0, 0, 0))
            with patch("pygame.draw.rect", wraps=pygame.draw.rect) as draw_rect:
                inset_content, inset_asset = menu.inset_panel(inset_rect)
            self.assertTrue(inset_asset)
            self.assertTrue(inset_rect.contains(inset_content))
            self.assertLess(inset_content.width, inset_rect.width)
            self.assertLess(inset_content.height, inset_rect.height)
            self.assertEqual(
                [call for call in draw_rect.call_args_list if call.args[0] is game.screen],
                [],
            )

            game.screen.fill((0, 0, 0))
            with patch("pygame.draw.rect", wraps=pygame.draw.rect) as draw_rect:
                game.draw_ornate_hud_panel(
                    game.screen,
                    pygame.Rect(30, 20, 520, 80),
                    (12, 12, 16, 230),
                    (210, 168, 92, 180),
                )
            screen_rect_calls = [
                call for call in draw_rect.call_args_list if call.args[0] is game.screen
            ]
            self.assertEqual(screen_rect_calls, [])

            rows = [("Enter", "Begin descent", "Ready")]
            row_rect = pygame.Rect(100, 100, 520, 44)
            game.screen.fill((0, 0, 0))
            with (
                patch("pygame.draw.rect", wraps=pygame.draw.rect) as draw_rect,
                patch("pygame.draw.line", wraps=pygame.draw.line) as draw_line,
            ):
                menu.draw_menu_rows(rows, row_rect)
            self.assertEqual(
                [call for call in draw_rect.call_args_list if call.args[0] is game.screen],
                [],
            )
            self.assertEqual(
                [call for call in draw_line.call_args_list if call.args[0] is game.screen],
                [],
            )
            unselected = self.surface_bytes(game.screen)

            game.screen.fill((0, 0, 0))
            menu.draw_menu_rows(rows, row_rect, selected_index=0)
            self.assertNotEqual(self.surface_bytes(game.screen), unselected)

    def test_missing_individual_resources_restore_procedural_fallbacks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            menu = game.menus
            real_render = game.ui_assets.render

            def missing_panel(key: str, size: tuple[int, int]) -> pygame.Surface | None:
                if key == "menu.panel":
                    return None
                return real_render(key, size)

            with patch.object(game.ui_assets, "render", side_effect=missing_panel):
                game.screen.fill((0, 0, 0))
                with patch("pygame.draw.rect", wraps=pygame.draw.rect) as draw_rect:
                    self.assertFalse(menu.panel(pygame.Rect(80, 60, 640, 320)))
                self.assertTrue(
                    any(call.args[0] is game.screen for call in draw_rect.call_args_list)
                )
                layout = menu.inventory_layout()
                legacy_pad = max(game.ui(16), 18)
                self.assertEqual(
                    layout["inner"], layout["box"].inflate(-legacy_pad * 2, -legacy_pad * 2)
                )

            def missing_row(key: str, size: tuple[int, int]) -> pygame.Surface | None:
                if key == "menu.row":
                    return None
                return real_render(key, size)

            with patch.object(game.ui_assets, "render", side_effect=missing_row):
                game.screen.fill((0, 0, 0))
                with patch("pygame.draw.rect", wraps=pygame.draw.rect) as draw_rect:
                    menu.draw_menu_rows(
                        [("1", "Fallback row", "Value")],
                        pygame.Rect(80, 80, 520, 44),
                    )
                self.assertTrue(
                    any(call.args[0] is game.screen for call in draw_rect.call_args_list)
                )

            def missing_inset(key: str, size: tuple[int, int]) -> pygame.Surface | None:
                if key == "menu.panel.inset":
                    return None
                return real_render(key, size)

            inset_rect = pygame.Rect(100, 90, 360, 140)
            with patch.object(game.ui_assets, "render", side_effect=missing_inset):
                with patch("pygame.draw.rect", wraps=pygame.draw.rect) as draw_rect:
                    inset_content, used_asset = menu.inset_panel(inset_rect)
            self.assertFalse(used_asset)
            self.assertTrue(inset_rect.contains(inset_content))
            self.assertTrue(
                any(call.args[0] is game.screen for call in draw_rect.call_args_list)
            )

            def missing_bar(key: str, size: tuple[int, int]) -> pygame.Surface | None:
                if key == "hud.bar":
                    return None
                return real_render(key, size)

            game.state = "archetype_select"
            game.selected_archetype = ARCHETYPES[2]
            with patch.object(game.ui_assets, "render", side_effect=missing_bar):
                with patch("pygame.draw.rect", wraps=pygame.draw.rect) as draw_rect:
                    game.draw_archetype_select()
            stat_cells = getattr(game, "_archetype_stat_rects")
            fallback_rects = [
                pygame.Rect(call.args[2])
                for call in draw_rect.call_args_list
                if len(call.args) >= 3 and call.args[0] is game.screen
            ]
            self.assertEqual(len(stat_cells), 7)
            self.assertTrue(all(cell in fallback_rects for cell in stat_cells))

    def test_exit_confirmation_draws_keyboard_cursor_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, (960, 540))
            game.state = "title"
            game.request_exit_confirmation()
            self.assertEqual(
                game.exit_confirmation_cursor,
                game.EXIT_CONFIRMATION_CANCEL,
            )
            with patch.object(
                game.menus,
                "draw_menu_rows",
                wraps=game.menus.draw_menu_rows,
            ) as draw_rows:
                game.draw_exit_confirmation()
            self.assertEqual(draw_rows.call_args.kwargs["selected_index"], 2)
            rows = draw_rows.call_args.args[0]
            self.assertEqual(
                [label for _key, label, _value in rows],
                [
                    "Exit game",
                    "Return to main menu",
                    "Cancel and return to game",
                ],
            )
            self.assertEqual(getattr(game, "_menu_shortcut_key"), "Enter / E")
            self.assertIn(
                "Cancel and return to game",
                getattr(game, "_menu_shortcut_label"),
            )

            game.last_save_error = "Could not save run: disk is full"
            with patch.object(
                game.menus,
                "draw_wrapped_text",
                wraps=game.menus.draw_wrapped_text,
            ) as draw_text:
                game.draw_exit_confirmation()
            rendered_notes = [call.args[0] for call in draw_text.call_args_list]
            self.assertIn(game.last_save_error, rendered_notes)

    def test_fallback_story_intro_draws_selected_choice(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, (960, 540))
            game.rng.seed(4247)
            game.restart(ARCHETYPES[0])
            self.assertTrue(game.story_intro_pending)
            game.active_cutscene = None
            game.cutscene_cursor = 1
            with patch.object(
                game,
                "draw_cutscene_choice_option",
                wraps=game.draw_cutscene_choice_option,
            ) as draw_choice:
                game.draw_story_intro_overlay()
            selected = [
                call.args[3]
                for call in draw_choice.call_args_list
                if call.kwargs.get("is_selected")
            ]
            self.assertEqual(selected, [1])

    def test_modern_menu_hotkeys_statuses_and_headers_use_safe_sections(self) -> None:
        for size in ((960, 540), (640, 480)):
            with self.subTest(size=size), tempfile.TemporaryDirectory() as tmpdir:
                game = self.make_game(tmpdir, size)
                screen = game.screen.get_rect()

                game.state = "title"
                game.title_selection = 1
                game.draw_title_menu()
                title_keys = getattr(game, "_menu_row_key_rects")
                title_panel = getattr(game, "_last_menu_panel_rect")
                title_shortcut = getattr(game, "_menu_shortcut_rect")
                title_header = getattr(game, "_menu_header_title_rect")
                self.assertTrue(all(rect.width == 0 for rect in title_keys))
                self.assertEqual(getattr(game, "_menu_shortcut_key"), "L / R")
                self.assertTrue(title_panel.contains(title_shortcut))
                self.assertLessEqual(title_header.bottom + 10, title_panel.y)

                game.state = "options"
                game.options_cursor = 1
                game.options_scroll = 0
                game.draw_options_menu()
                option_keys = getattr(game, "_menu_row_key_rects")
                option_panel = getattr(game, "_last_menu_panel_rect")
                option_shortcut = getattr(game, "_options_shortcut_rect")
                option_title = getattr(game, "_menu_header_title_rect")
                option_subtitle = getattr(game, "_menu_header_subtitle_rect")
                self.assertTrue(all(rect.width == 0 for rect in option_keys))
                self.assertEqual(getattr(game, "_menu_shortcut_key"), "D")
                self.assertTrue(option_panel.contains(option_shortcut))
                self.assertLessEqual(option_title.bottom, option_subtitle.y)
                self.assertLessEqual(option_subtitle.bottom + 12, option_panel.y)
                selected_offset = game.options_cursor - game.options_scroll
                value_rects = getattr(game, "_menu_row_value_rects")
                value_rect = value_rects[selected_offset]
                selected_rect = getattr(game, "_options_selected_row_rect")
                difficulty_text = f"{game.difficulty_profile().name} · Hell locked"
                detail_font = getattr(game, "_options_detail_font")
                self.assertGreaterEqual(
                    value_rect.width,
                    detail_font.size(difficulty_text)[0],
                )
                self.assertGreaterEqual(selected_rect.right - value_rect.right, 80)

                game.state = "archetype_select"
                game.selected_archetype = ARCHETYPES[2]
                game.draw_archetype_select()
                archetype_keys = getattr(game, "_menu_row_key_rects")
                archetype_shortcut = getattr(game, "_archetype_shortcut_rect")
                archetype_title = getattr(game, "_archetype_title_rect")
                archetype_subtitle = getattr(game, "_archetype_subtitle_rect")
                archetype_panel = getattr(game, "_archetype_panel_rect")
                self.assertTrue(all(rect.width == 0 for rect in archetype_keys))
                self.assertEqual(getattr(game, "_menu_shortcut_key"), "3")
                self.assertTrue(screen.contains(archetype_shortcut))
                self.assertLessEqual(archetype_title.bottom, archetype_subtitle.y)
                self.assertLessEqual(
                    archetype_subtitle.bottom + 12,
                    archetype_panel.y,
                )

                game.set_legacy_graphics(True)
                game.state = "title"
                game.draw_title_menu()
                legacy_keys = getattr(game, "_menu_row_key_rects")
                self.assertTrue(any(rect.width > 0 for rect in legacy_keys))

    def test_ranger_archetype_preview_uses_south_west_idle_animation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.state = "archetype_select"
            game.selected_archetype = ARCHETYPES[4]

            game.ui_elapsed = 0.0
            with patch.object(
                game.sprites, "player_visual", wraps=game.sprites.player_visual
            ) as player_visual:
                game.draw_archetype_select()
            self.assertTrue(player_visual.called)
            self.assertEqual(player_visual.call_args.args[:2], ("Ranger", "idle"))
            self.assertEqual(
                player_visual.call_args.kwargs["direction"], "south-west"
            )
            sprite_box = getattr(game, "_archetype_sprite_box").copy()
            first = self.surface_bytes(game.screen.subsurface(sprite_box))

            game.ui_elapsed = 0.2
            game.draw_archetype_select()
            second = self.surface_bytes(game.screen.subsurface(sprite_box))
            self.assertNotEqual(first, second)
            sprite_rect = getattr(game, "_archetype_sprite_rect")
            sprite_anchor = getattr(game, "_archetype_sprite_anchor")
            sprite_ground = getattr(game, "_archetype_sprite_ground")
            self.assertEqual(
                (sprite_rect.x + sprite_anchor[0], sprite_rect.y + sprite_anchor[1]),
                sprite_ground,
            )

            game.selected_archetype = ARCHETYPES[2]
            with patch.object(
                game.sprites, "player_visual", wraps=game.sprites.player_visual
            ) as player_visual:
                game.draw_archetype_select()
            self.assertEqual(player_visual.call_args.args[:2], ("Arcanist", "idle"))
            self.assertEqual(player_visual.call_args.kwargs["direction"], "south")

    def test_rogue_archetype_idle_keeps_ground_anchor_fixed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.state = "archetype_select"
            game.selected_archetype = ARCHETYPES[1]

            ground_positions = []
            crop_centers = []
            for frame_index in range(4):
                game.ui_elapsed = frame_index / 5.0
                game.draw_archetype_select()
                sprite_rect = getattr(game, "_archetype_sprite_rect")
                sprite_anchor = getattr(game, "_archetype_sprite_anchor")
                ground_positions.append(
                    (
                        sprite_rect.x + sprite_anchor[0],
                        sprite_rect.y + sprite_anchor[1],
                    )
                )
                crop_centers.append(sprite_rect.centerx)

            self.assertEqual(len(set(ground_positions)), 1)
            self.assertGreater(len(set(crop_centers)), 1)

    def test_legacy_ranger_archetype_preview_uses_south_west_idle_animation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, legacy=True)
            game.state = "archetype_select"
            game.selected_archetype = ARCHETYPES[4]
            game.ui_elapsed = 0.2
            with patch.object(
                game.sprites, "player_visual", wraps=game.sprites.player_visual
            ) as player_visual:
                game.draw_archetype_select()
            self.assertTrue(player_visual.called)
            self.assertEqual(player_visual.call_args.args[:2], ("Ranger", "idle"))
            self.assertEqual(player_visual.call_args.args[3], game.ui_elapsed)
            self.assertEqual(
                player_visual.call_args.kwargs["direction"], "south-west"
            )

    def test_menu_animation_clock_advances_without_run_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.state = "archetype_select"
            game.running = True
            game.clock = Mock()
            game.clock.tick.return_value = 16

            def stop_after_events() -> None:
                game.running = False

            with (
                patch.object(game, "handle_events", side_effect=stop_after_events),
                patch.object(game, "draw"),
                patch("arch_rogue.game.pygame.quit"),
            ):
                game.run()

            self.assertAlmostEqual(game.ui_elapsed, 0.016)
            self.assertEqual(game.elapsed, 0.0)
            self.prepare_run(game)
            self.assertNotIn("ui_elapsed", game.serialize_run_state())

    def test_compact_archetypes_keep_complete_preview_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, (640, 480))
            game.state = "archetype_select"
            for archetype in ARCHETYPES:
                with self.subTest(archetype=archetype.name):
                    game.selected_archetype = archetype
                    game.draw_archetype_select()
                    preview_rect = getattr(game, "_archetype_preview_rect")
                    skills_text = getattr(game, "_archetype_skills_text")
                    skills_font = getattr(game, "_archetype_skills_font")
                    description_rect = getattr(game, "_archetype_description_rect")
                    description_font = getattr(game, "_archetype_description_font")
                    description_line_h = getattr(
                        game, "_archetype_description_line_height"
                    )
                    description_lines = getattr(game, "_archetype_description_lines")
                    required_description_h = (
                        (len(description_lines) - 1) * description_line_h
                        + description_font.get_height()
                    )
                    self.assertLessEqual(
                        skills_font.size(skills_text)[0], preview_rect.width
                    )
                    self.assertGreaterEqual(
                        description_rect.height, required_description_h
                    )
                    stat_text_layout = getattr(game, "_last_stat_card_text_layout")
                    self.assertEqual(len(stat_text_layout), 7)
                    for label, label_font, label_rect, value, value_rect in stat_text_layout:
                        self.assertLessEqual(
                            label_font.size(label)[0], label_rect.width
                        )
                        self.assertLessEqual(
                            game.small_font.size(value)[0], value_rect.width
                        )

    def test_archetype_stat_cards_do_not_change_character_sheet_stats(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.prepare_run(game)
            game.ui_assets.clear_derived_caches()
            with patch.object(
                game.ui_assets, "render", wraps=game.ui_assets.render
            ) as render:
                game.draw_character_menu()
            rendered_keys = {
                call.args[0] for call in render.call_args_list if call.args
            }
            self.assertNotIn("hud.bar", rendered_keys)

    def test_modern_compact_layout_matrix_stays_contained(self) -> None:
        cases = (((960, 540), 1), ((640, 480), 1), ((640, 480), 4))
        for size, scale in cases:
            with self.subTest(size=size, scale=scale), tempfile.TemporaryDirectory() as tmpdir:
                game = self.make_game(tmpdir, size, scale)
                screen = game.screen.get_rect()

                game.state = "archetype_select"
                game.selected_archetype = ARCHETYPES[2]
                game.draw_archetype_select()
                archetype_panel = getattr(game, "_archetype_panel_rect")
                reference_panel = getattr(game, "_archetype_panel_reference_rect")
                archetype_content = getattr(game, "_archetype_content_rect")
                list_rect = getattr(game, "_archetype_list_rect")
                preview_rect = getattr(game, "_archetype_preview_rect")
                sprite_box = getattr(game, "_archetype_sprite_box")
                sprite_rect = getattr(game, "_archetype_sprite_rect")
                sprite_anchor = getattr(game, "_archetype_sprite_anchor")
                sprite_ground = getattr(game, "_archetype_sprite_ground")
                title_rect = getattr(game, "_archetype_title_rect")
                subtitle_rect = getattr(game, "_archetype_subtitle_rect")
                shortcut_rect = getattr(game, "_archetype_shortcut_rect")
                stat_rect = getattr(game, "_archetype_stat_rect")
                stat_cells = getattr(game, "_archetype_stat_rects")
                self.assertTrue(screen.contains(archetype_panel))
                self.assertEqual(archetype_panel.center, reference_panel.center)
                self.assertEqual(
                    archetype_panel.width, round(reference_panel.width * 0.8)
                )
                self.assertEqual(
                    archetype_panel.height, round(reference_panel.height * 0.8)
                )
                header_shift = archetype_panel.y - reference_panel.y
                self.assertGreater(header_shift, 0)
                self.assertEqual(
                    title_rect.y,
                    max(20, int(screen.height * 0.04)) + header_shift,
                )
                self.assertEqual(subtitle_rect.y, title_rect.bottom + 5)
                self.assertEqual(shortcut_rect.x, archetype_panel.x)
                self.assertEqual(shortcut_rect.width, archetype_panel.width)
                self.assertEqual(shortcut_rect.y, archetype_panel.bottom + 4)
                self.assertLess(shortcut_rect.y, reference_panel.bottom + 4)
                self.assertLessEqual(archetype_panel.width, screen.width - 52)
                self.assertLessEqual(archetype_panel.height, screen.height - 40)
                self.assertTrue(archetype_panel.contains(archetype_content))
                self.assertTrue(archetype_content.contains(list_rect))
                self.assertTrue(archetype_content.contains(preview_rect))
                self.assertTrue(preview_rect.contains(sprite_box))
                self.assertTrue(sprite_box.contains(sprite_rect))
                self.assertEqual(
                    (sprite_rect.x + sprite_anchor[0], sprite_rect.y + sprite_anchor[1]),
                    sprite_ground,
                )
                self.assertEqual(sprite_ground[0], preview_rect.centerx)
                self.assertGreater(list_rect.width * list_rect.height, 0)
                self.assertGreater(preview_rect.width * preview_rect.height, 0)
                self.assertLessEqual(list_rect.right, preview_rect.x)
                self.assertTrue(preview_rect.contains(stat_rect))
                self.assertEqual(len(stat_cells), 7)
                self.assertTrue(all(stat_rect.contains(cell) for cell in stat_cells))
                self.assertIn(
                    "hud.bar", {key[0] for key in game.ui_assets._render_cache}
                )
                panel_key = (
                    "menu.panel" if size[0] >= 800 else "menu.panel.compact"
                )
                self.assertIn(panel_key, {key[0] for key in game.ui_assets._render_cache})

                self.prepare_run(game)
                game.screen.fill((12, 12, 16))
                game.draw_inventory()
                layout = getattr(game, "_inventory_layout")
                self.assertTrue(screen.contains(layout["box"]))
                for key in ("header", "sort", "content", "controls"):
                    self.assertTrue(layout["inner"].contains(layout[key]), key)
                self.assertTrue(layout["content"].contains(layout["list"]))
                self.assertTrue(layout["content"].contains(layout["details"]))
                self.assertLessEqual(layout["list"].right, layout["details"].x)
                self.assertLessEqual(layout["box"].width, round(screen.width * 0.90))
                self.assertLessEqual(layout["box"].height, round(screen.height * 0.90))
                inventory_panels = getattr(game, "_inventory_inset_rects")
                inventory_contents = getattr(game, "_inventory_inset_content_rects")
                self.assertEqual(
                    set(inventory_panels),
                    {"sort", "list", "selected", "equipment", "controls"},
                )
                for name, panel_rect in inventory_panels.items():
                    content_rect = inventory_contents[name]
                    self.assertTrue(layout["box"].contains(panel_rect), name)
                    self.assertTrue(panel_rect.contains(content_rect), name)
                    self.assertLess(content_rect.width, panel_rect.width, name)
                    self.assertLess(content_rect.height, panel_rect.height, name)

                game.character_menu_tab = "overview"
                game.screen.fill((12, 12, 16))
                game.draw_character_menu()
                character_panel = getattr(game, "_character_panel_rect")
                character_content = getattr(game, "_character_content_rect")
                self.assertTrue(screen.contains(character_panel))
                self.assertTrue(character_panel.contains(character_content))
                self.assertLessEqual(character_panel.width, round(screen.width * 0.90))
                self.assertLessEqual(character_panel.height, round(screen.height * 0.90))
                character_panels = getattr(game, "_character_inset_rects")
                character_contents = getattr(game, "_character_inset_content_rects")
                self.assertEqual(
                    set(character_panels),
                    {"stats", "skills", "equipment", "upgrades", "status"},
                )
                for name, panel_rect in character_panels.items():
                    content_rect = character_contents[name]
                    self.assertTrue(character_panel.contains(panel_rect), name)
                    self.assertTrue(panel_rect.contains(content_rect), name)
                    self.assertLess(content_rect.width, panel_rect.width, name)
                    self.assertLess(content_rect.height, panel_rect.height, name)

                game.character_menu_tab = "disciplines"
                game.screen.fill((12, 12, 16))
                game.draw_character_menu()
                discipline_panels = getattr(game, "_character_inset_rects")
                discipline_contents = getattr(game, "_character_inset_content_rects")
                self.assertEqual(set(discipline_panels), {"disciplines"})
                self.assertTrue(
                    discipline_panels["disciplines"].contains(
                        discipline_contents["disciplines"]
                    )
                )

                game.screen.fill((12, 12, 16))
                game.draw_help_overlay()
                help_panel = getattr(game, "_help_panel_rect")
                help_content = getattr(game, "_help_content_rect")
                self.assertTrue(screen.contains(help_panel))
                self.assertTrue(help_panel.contains(help_content))

                game.state = "dead"
                game.screen.fill((12, 12, 16))
                game.draw_state_overlay()
                state_panel = getattr(game, "_state_panel_rect")
                state_content = getattr(game, "_state_content_rect")
                self.assertTrue(screen.contains(state_panel))
                self.assertTrue(state_panel.contains(state_content))

                game.state = "playing"
                game.screen.fill((12, 12, 16))
                game.draw_ui()
                hud = game._hud_layout
                for rect in hud.values():
                    self.assertTrue(screen.contains(rect), rect)
                for card, content in (
                    (hud["resources"], hud["resources_content"]),
                    (hud["character"], hud["character_content"]),
                    (hud["mission"], hud["mission_content"]),
                ):
                    self.assertTrue(card.contains(content), (card, content))
                resource_bars = getattr(game, "_hud_resource_bar_rects")
                self.assertEqual(len(resource_bars), 3)
                for bar in resource_bars:
                    self.assertTrue(hud["resources_content"].contains(bar), bar)
                self.assertLessEqual(hud["action_bar"].bottom, hud["panel"].y)
                self.assertFalse(hasattr(game, "_ui_scale_override"))

    def test_short_modern_character_and_inventory_content_stays_framed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, (640, 360), 4)
            self.prepare_run(game)
            screen = game.screen.get_rect()

            game.screen.fill((12, 12, 16))
            game.draw_inventory()
            inventory_layout = getattr(game, "_inventory_layout")
            self.assertTrue(screen.contains(inventory_layout["box"]))
            self.assertLess(inventory_layout["box"].width, screen.width)
            self.assertLess(inventory_layout["box"].height, screen.height)
            inventory_contents = getattr(game, "_inventory_inset_content_rects")
            visible_rows = getattr(game, "_inventory_visible_row_rects")
            self.assertGreaterEqual(len(visible_rows), 1)
            for row in visible_rows:
                self.assertTrue(inventory_contents["list"].contains(row), row)
            control_pills = getattr(game, "_inventory_control_pill_rects")
            self.assertEqual(len(control_pills), 8)
            for pill in control_pills:
                self.assertTrue(inventory_contents["controls"].contains(pill), pill)

            captured: list[str] = []
            original_draw_text = game.menus.draw_text

            def capture_draw_text(text, font, color, rect, *args, **kwargs):
                captured.append(text)
                return original_draw_text(text, font, color, rect, *args, **kwargs)

            game.character_menu_tab = "overview"
            with patch.object(game.menus, "draw_text", side_effect=capture_draw_text):
                game.draw_character_menu()
            character_panel = getattr(game, "_character_panel_rect")
            self.assertTrue(screen.contains(character_panel))
            self.assertLess(character_panel.width, screen.width)
            self.assertLess(character_panel.height, screen.height)
            rendered_text = " ".join(captured)
            for skill_name in game.skill_names():
                self.assertIn(skill_name, rendered_text)
            self.assertIn("Warden Arming Sword", rendered_text)
            self.assertIn("Warden Mail", rendered_text)
            self.assertEqual(
                set(getattr(game, "_character_inset_rects")),
                {"stats", "skills", "equipment", "upgrades", "status"},
            )

            game.character_menu_tab = "disciplines"
            game.draw_character_menu()
            discipline_content = getattr(game, "_character_inset_content_rects")[
                "disciplines"
            ]
            discipline_cells = getattr(game, "_discipline_cells")
            self.assertTrue(discipline_cells)
            for cell in discipline_cells.values():
                self.assertTrue(discipline_content.contains(cell), cell)

    def test_character_and_inventory_breakpoints_preserve_content(self) -> None:
        for height in (419, 420, 439, 440):
            with self.subTest(height=height), tempfile.TemporaryDirectory() as tmpdir:
                game = self.make_game(tmpdir, (640, height), 4)
                self.prepare_run(game)

                game.draw_inventory()
                inventory_contents = getattr(game, "_inventory_inset_content_rects")
                self.assertEqual(len(getattr(game, "_inventory_control_pill_rects")), 8)
                for row in getattr(game, "_inventory_visible_row_rects"):
                    self.assertTrue(inventory_contents["list"].contains(row), row)

                captured: list[str] = []
                original_draw_text = game.menus.draw_text

                def capture_draw_text(text, font, color, rect, *args, **kwargs):
                    captured.append(text)
                    return original_draw_text(text, font, color, rect, *args, **kwargs)

                game.character_menu_tab = "overview"
                with patch.object(
                    game.menus, "draw_text", side_effect=capture_draw_text
                ):
                    game.draw_character_menu()
                rendered_text = " ".join(captured)
                for skill_name in game.skill_names():
                    self.assertIn(skill_name, rendered_text)

    def test_story_panel_yields_to_interaction_prompt_above_taller_hud(self) -> None:
        for size in ((960, 540), (640, 480), (640, 360)):
            with self.subTest(size=size), tempfile.TemporaryDirectory() as tmpdir:
                game = self.make_game(tmpdir, size, 4)
                self.prepare_run(game)
                game.quest_info_visible = True
                hint = (
                    "E",
                    "Open sealed reliquary",
                    "Costs blood but may contain a relic.",
                    (214, 168, 92),
                )
                story_lines = [
                    "The Ossuary remembers",
                    "Depth 7 · Find the sealed stair",
                    "Story forces: Blood Moon",
                    "Outcome: The reliquary is still unopened",
                ]
                with (
                    patch.object(game, "current_interaction_hint", return_value=hint),
                    patch.object(game, "story_panel_lines", return_value=story_lines),
                ):
                    game.draw_ui()

                prompt_rect = getattr(game, "_interaction_prompt_rect")
                self.assertIsNotNone(prompt_rect)
                assert prompt_rect is not None
                self.assertTrue(game.screen.get_rect().contains(prompt_rect))
                story_rect = getattr(game, "_story_panel_rect")
                if size == (640, 360):
                    self.assertIsNone(story_rect)
                else:
                    self.assertIsNotNone(story_rect)
                    assert story_rect is not None
                    self.assertFalse(story_rect.colliderect(prompt_rect))
                    self.assertLessEqual(story_rect.bottom + 8, prompt_rect.y)

    def test_quest_info_panel_scrolls_overflowing_story_text(self) -> None:
        # 4.2.2: overflowing quest text scrolls with a right-rail scrollbar
        # instead of truncating with an ellipsis; the offset clamps to the
        # overflow and resets when the quest info panel is toggled.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.prepare_run(game)
            game.quest_info_visible = True
            story_lines = ["The Ossuary remembers"] + [
                f"Chronicle entry {index}: the vault doors remember every "
                "oath sworn beneath them."
                for index in range(24)
            ]
            with patch.object(
                game, "story_panel_lines", return_value=story_lines
            ):
                game.screen.fill((12, 12, 16))
                game.draw_ui()
                self.assertGreater(game._story_panel_scroll_max, 0)
                self.assertEqual(game.story_panel_scroll, 0)
                story_rect = game._story_panel_rect
                scrollbar = game._story_panel_scrollbar_rect
                self.assertIsNotNone(story_rect)
                self.assertIsNotNone(scrollbar)
                self.assertTrue(story_rect.contains(scrollbar))
                top_bytes = self.surface_bytes(
                    game.screen.subsurface(story_rect)
                )

                # Scrolling down moves the rendered slice.
                game.scroll_story_panel(4)
                self.assertEqual(game.story_panel_scroll, 4)
                game.screen.fill((12, 12, 16))
                game.draw_ui()
                self.assertNotEqual(
                    top_bytes,
                    self.surface_bytes(game.screen.subsurface(story_rect)),
                )

                # The offset clamps to the overflow in both directions.
                game.scroll_story_panel(999)
                self.assertEqual(
                    game.story_panel_scroll, game._story_panel_scroll_max
                )
                game.scroll_story_panel(-999)
                self.assertEqual(game.story_panel_scroll, 0)

                # A scrolled offset resets when the panel is toggled.
                game.scroll_story_panel(3)
                game.toggle_quest_info_visibility()
                game.toggle_quest_info_visibility()
                self.assertEqual(game.story_panel_scroll, 0)

            # Short story text keeps the no-scroll layout: no overflow, no
            # scrollbar, and a stale offset snaps back to the top.
            game.story_panel_scroll = 7
            with patch.object(
                game,
                "story_panel_lines",
                return_value=[
                    "The Ossuary remembers",
                    "Depth 1 · Find the sealed stair",
                ],
            ):
                game.screen.fill((12, 12, 16))
                game.draw_ui()
            self.assertEqual(game._story_panel_scroll_max, 0)
            self.assertIsNone(game._story_panel_scrollbar_rect)
            self.assertEqual(game.story_panel_scroll, 0)

    def test_obsidian_resource_bars_expand_only_the_modern_hud(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, (960, 540))
            self.prepare_run(game)

            game.screen.fill((12, 12, 16))
            game.draw_ui()
            modern_hud = {key: rect.copy() for key, rect in game._hud_layout.items()}
            modern_bars = tuple(
                rect.copy() for rect in getattr(game, "_hud_resource_bar_rects")
            )
            self.assertEqual(modern_hud["panel"].height, 84)
            self.assertEqual(modern_hud["resources"].width, 322)
            self.assertEqual(len(modern_bars), 3)
            # 4.2.x thin-border slab: the same card yields wider bar troughs.
            self.assertTrue(all(bar.size == (284, 14) for bar in modern_bars))
            self.assertTrue(
                all(modern_hud["resources_content"].contains(bar) for bar in modern_bars)
            )
            self.assertTrue(
                all(
                    first.bottom <= second.y
                    for first, second in zip(modern_bars, modern_bars[1:])
                )
            )

            game.set_legacy_graphics(True)
            game.screen.fill((12, 12, 16))
            game.draw_ui()
            legacy_hud = game._hud_layout
            legacy_bars = getattr(game, "_hud_resource_bar_rects")
            self.assertLess(legacy_hud["panel"].height, modern_hud["panel"].height)
            self.assertLess(
                legacy_hud["resources"].width,
                modern_hud["resources"].width,
            )
            self.assertTrue(
                all(
                    legacy.height < modern.height
                    for legacy, modern in zip(legacy_bars, modern_bars)
                )
            )

            game.ui_scale = 4
            game.rebuild_fonts()
            game.screen.fill((12, 12, 16))
            game.draw_ui()
            scaled_legacy_bars = getattr(game, "_hud_resource_bar_rects")
            expected_gap = max(game.ui(4), 6)
            self.assertTrue(
                all(
                    second.y - first.bottom == expected_gap
                    for first, second in zip(
                        scaled_legacy_bars,
                        scaled_legacy_bars[1:],
                    )
                )
            )

    def test_hud_slab_has_thin_side_borders_and_padded_mission_text(self) -> None:
        # 4.2.x: the regenerated lower HUD slab keeps its left/right nine-slice
        # caps and safe-content insets thin so panel interiors fit more content,
        # and the mission objective sits slightly lower and further left than
        # the raw card content rect.
        library = UiAssetLibrary()
        self.assertTrue(library.available)
        entry = library.manifest["assets"]["hud.panel"]
        left, _top, right, _bottom = entry["insets"]
        self.assertLessEqual(left, 16)
        self.assertLessEqual(right, 16)
        content_left, _, content_right, _ = entry["content_insets"]
        self.assertLessEqual(content_left, 16)
        self.assertLessEqual(content_right, 16)
        self.assertIsNotNone(library.source("hud.panel"))

        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.prepare_run(game)
            captured: list[tuple[str, pygame.Rect]] = []
            original_draw_ui_text = game.draw_ui_text

            def capture(surface, text, font, color, rect, *args, **kwargs):
                captured.append((text, rect.copy()))
                return original_draw_ui_text(
                    surface, text, font, color, rect, *args, **kwargs
                )

            game.screen.fill((12, 12, 16))
            with patch.object(game, "draw_ui_text", side_effect=capture):
                game.draw_ui()
            mission_content = game._hud_layout["mission_content"]
            objective_rect = next(
                rect
                for text, rect in captured
                if text.startswith("Find the stairs")
            )
            self.assertGreaterEqual(objective_rect.y, mission_content.y + 4)
            self.assertLessEqual(
                objective_rect.right, mission_content.right - 8
            )

    def test_modern_state_table_renders_all_twenty_four_statistics(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.prepare_run(game)
            rows = game.menus._run_stats_rows(False)
            self.assertEqual(len(rows), 24)
            with patch.object(game.menus, "draw_text") as draw_text:
                game.menus._draw_modern_run_stats_table(
                    pygame.Rect(80, 100, 800, 300), rows
                )
            self.assertEqual(draw_text.call_count, 52)
            rendered_text = [call.args[0] for call in draw_text.call_args_list]
            for heading in ("RUN", "COMBAT", "EXPLORATION", "LEGACY"):
                self.assertIn(heading, rendered_text)
            for label, value in rows:
                self.assertIn(label, rendered_text)
                self.assertIn(value, rendered_text)

    def test_state_stat_panels_keep_padded_aligned_text_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.prepare_run(game)
            game.state = "dead"
            game.run_stats.cause_of_death = "poisoned by the Ashen Gatekeeper"
            game.run_stats.discoveries = ["Moonlit Bargain", "Forgotten Reliquary"]
            game.run_stats.notable_loot = ["Crown of Cinders", "The Last Oath"]
            game.screen.fill((12, 12, 16))
            game.draw_state_overlay()

            panels = getattr(game, "_state_stat_panel_rects")
            contents = getattr(game, "_state_stat_content_rects")
            layout = getattr(game, "_state_stat_text_layout")
            self.assertEqual(set(panels), {"run", "combat", "exploration", "legacy"})
            self.assertEqual(set(contents), set(panels))
            self.assertEqual(len(layout), 24)

            for key, panel_rect in panels.items():
                content_rect = contents[key]
                self.assertTrue(panel_rect.contains(content_rect), key)
                self.assertGreaterEqual(content_rect.x - panel_rect.x, 10, key)
                self.assertGreaterEqual(panel_rect.right - content_rect.right, 10, key)
                self.assertGreaterEqual(content_rect.y - panel_rect.y, 8, key)
                self.assertGreaterEqual(panel_rect.bottom - content_rect.bottom, 8, key)

            panel_list = list(panels.values())
            for index, first in enumerate(panel_list):
                for second in panel_list[index + 1 :]:
                    self.assertFalse(first.colliderect(second), (first, second))

            for heading in ("Run", "Combat", "Exploration", "Legacy"):
                content_rect = contents[heading.casefold()]
                section_rows = [entry for entry in layout if entry[0] == heading]
                self.assertEqual(len(section_rows), 6)
                label_edges = {entry[2].x for entry in section_rows}
                value_edges = {entry[4].right for entry in section_rows}
                self.assertEqual(label_edges, {content_rect.x})
                self.assertEqual(value_edges, {content_rect.right})
                for _section, _label, label_rect, _value, value_rect in section_rows:
                    self.assertTrue(content_rect.contains(label_rect))
                    self.assertTrue(content_rect.contains(value_rect))
                    self.assertLess(label_rect.right, value_rect.x)

    def test_options_scrollbar_appears_when_rows_overflow_and_is_absent_when_they_fit(self) -> None:
        # 4.2: when the options list does not fit vertically, a thin scrollbar
        # is drawn on the right rail of the row viewport; when everything
        # fits, no scrollbar is drawn and the rows keep the full width.
        from arch_rogue.menus import MenuRenderer

        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, (960, 540))
            game.state = "options"
            # Force vertical overflow: a large UI scale makes each row tall
            # enough that the full options list can no longer fit on screen.
            game.ui_scale = 4
            game.rebuild_fonts()
            game.options_cursor = 0
            game.options_scroll = 0

            with patch.object(
                MenuRenderer, "draw_options_scrollbar", wraps=game.menus.draw_options_scrollbar
            ) as scrollbar:
                game.draw_options_menu()
            self.assertTrue(scrollbar.called)
            viewport_rect, scroll, visible_count, total_count = scrollbar.call_args.args
            # ``total_count`` is the full options list length; ``visible_count``
            # is how many rows fit on screen right now.
            self.assertEqual(total_count, 13)  # fixed options list length (4.3.17: +frame rate cap, +perf overlay)
            # Sanity: the viewport is inside the screen and the visible range
            # really is smaller than the full options list.
            self.assertLess(visible_count, total_count)
            self.assertEqual(len(game._options_visible_rows), visible_count)
            self.assertTrue(game.screen.get_rect().contains(viewport_rect))
            self.assertGreater(viewport_rect.width, 0)
            # The rendered rows were inset from the viewport's right edge to
            # leave room for the scrollbar rail, so the selected row rect does
            # not extend all the way to the viewport's right edge.
            self.assertLess(
                game._options_selected_row_rect.right,
                viewport_rect.right - game.ui(2),
            )

            # When the list fits, no scrollbar is drawn and rows keep full width.
            game = self.make_game(tmpdir, (1600, 1200), scale=1)
            game.state = "options"
            game.options_cursor = 0
            game.options_scroll = 0
            with patch.object(
                MenuRenderer, "draw_options_scrollbar", wraps=game.menus.draw_options_scrollbar
            ) as scrollbar_fit:
                game.draw_options_menu()
            self.assertFalse(scrollbar_fit.called)
            visible_start, visible_end = game._options_visible_range
            self.assertEqual(visible_end - visible_start, len(game._options_visible_rows))


if __name__ == "__main__":
    unittest.main()
