# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
#
# AI Provenance & Liability Notice:
# This repository contains code generated, assisted, or refactored by Artificial
# Intelligence models. Provided strictly "AS IS" under Apache 2.0 with no warranty
# of clean IP provenance or non-infringement; downstream users assume all legal
# and financial risk and should perform their own compliance audits.
#
# 4.8.8 desktop mouse menus: hovering a menu row moves the selection highlight
# and clicking activates it, over the render-published hitboxes that mobile
# taps already consume. Selection-preview lists (archetype select, inventory,
# shop) confirm on double click only.
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
from arch_rogue.models import Item


class MouseMenuTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.game = Game(
            screen_size=(1280, 800),
            headless=True,
            save_path=Path(self._tmpdir.name) / "run.json",
        )
        self.game.options_path = Path(self._tmpdir.name) / "options.json"

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def start_run(self) -> None:
        game = self.game
        game.rng.seed(11)
        game.restart(ARCHETYPES[0])
        if game.story_intro_pending:
            self.assertTrue(game.choose_story_relic_path(0))
        game.active_cutscene = None

    # --- title ----------------------------------------------------------

    def test_title_rows_hover_highlight_and_click_activate(self) -> None:
        game = self.game
        game.state = "title"
        game.draw()
        rows = game._title_row_rects
        self.assertEqual(len(rows), game.TITLE_ROW_COUNT)

        game.title_selection = 0
        self.assertTrue(game.handle_menu_mouse_motion(rows[4].center))
        self.assertEqual(game.title_selection, 4)
        # Disabled Resume row: hover never moves the highlight onto it and a
        # click falls through unconsumed.
        self.assertFalse(game.save_exists())
        game.handle_menu_mouse_motion(rows[game.TITLE_RESUME_ROW].center)
        self.assertEqual(game.title_selection, 4)
        self.assertFalse(
            game.handle_menu_mouse_click(rows[game.TITLE_RESUME_ROW].center)
        )
        # 5.0.1: row 3 is the Chronicle; Options moved to row 4.
        self.assertTrue(game.handle_menu_mouse_click(rows[4].center))
        self.assertEqual(game.state, "options")

    # --- options --------------------------------------------------------

    def test_options_rows_hover_and_click_toggle(self) -> None:
        game = self.game
        game.state = "options"
        game.draw()
        rows = game._menu_row_rects
        start = int(game._options_visible_range[0])
        self.assertGreaterEqual(len(rows), 2)

        game.handle_menu_mouse_motion(rows[1].center)
        self.assertEqual(game.options_cursor, start + 1)

        with patch.object(type(game), "_activate_options_row") as activate:
            self.assertTrue(game.handle_menu_mouse_click(rows[1].center))
            activate.assert_called_once_with(start + 1, True)
        # A click on empty space is not consumed.
        self.assertFalse(game.handle_menu_mouse_click((2, 2)))

    # --- archetype select ----------------------------------------------

    def test_archetype_click_previews_and_double_click_descends(self) -> None:
        game = self.game
        game.state = "archetype_select"
        game.draw()
        rows = game._menu_row_rects
        self.assertEqual(len(rows), len(ARCHETYPES))

        game.handle_menu_mouse_motion(rows[2].center)
        self.assertIs(game.selected_archetype, ARCHETYPES[2])

        # First click only previews — a stray click never starts a run.
        self.assertTrue(game.handle_menu_mouse_click(rows[1].center))
        self.assertIs(game.selected_archetype, ARCHETYPES[1])
        self.assertEqual(game.state, "archetype_select")
        # The second click on the same row confirms the descent.
        self.assertTrue(game.handle_menu_mouse_click(rows[1].center))
        self.assertEqual(game.state, "playing")
        self.assertEqual(game.player.class_name, ARCHETYPES[1].name)

    # --- cutscene / story intro -----------------------------------------

    def test_cutscene_click_advances_then_chooses(self) -> None:
        game = self.game
        game.state = "archetype_select"
        game.draw()
        rows = game._menu_row_rects
        game.handle_menu_mouse_click(rows[0].center)
        game.handle_menu_mouse_click(rows[0].center)
        self.assertEqual(game.state, "playing")
        self.assertIsNotNone(game.active_cutscene)
        self.assertEqual(game.mobile_input_context(), "cutscene")

        for _ in range(200):
            if game.active_cutscene_narration_complete():
                break
            self.assertTrue(game.handle_menu_mouse_click((5, 5)))
        else:
            self.fail("cutscene narration never completed")

        game.draw()
        choices = game._cutscene_choice_rects
        count = len(game.active_cutscene_choices())
        self.assertGreaterEqual(count, 2)
        self.assertGreaterEqual(len(choices), count)

        game.handle_menu_mouse_motion(choices[1].center)
        self.assertEqual(game.cutscene_cursor, 1)
        self.assertTrue(game.handle_menu_mouse_click(choices[1].center))
        self.assertFalse(game.story_intro_pending)

    # --- inventory ------------------------------------------------------

    def test_inventory_hover_selects_and_double_click_confirms(self) -> None:
        game = self.game
        self.start_run()
        game.player.inventory.append(
            Item("Restorative Draught", "potion", rarity="Common")
        )
        game.player.inventory.append(
            Item("Mana Philtre", "mana_potion", rarity="Common")
        )
        game.inventory_open = True
        game.clamp_inventory_selection()
        game.draw()
        inv_rows = game._inventory_visible_row_rects
        self.assertGreaterEqual(len(inv_rows), 2)

        game.handle_menu_mouse_motion(inv_rows[1].center)
        self.assertEqual(game.inventory_cursor, game.inventory_scroll + 1)

        with patch.object(type(game), "_dispatch_command") as dispatch:
            game.handle_menu_mouse_click(inv_rows[0].center)
            dispatch.assert_not_called()
            game.handle_menu_mouse_click(inv_rows[0].center)
            dispatch.assert_called_once()

        # Sort chips act on a single click.
        chips = game._inventory_sort_mode_rects
        self.assertTrue(chips)
        mode, rect = chips[-1]
        self.assertTrue(game.handle_menu_mouse_click(rect.center))
        self.assertEqual(game.inventory_sort_mode, mode)

    # --- shop (fabricated rects: selection semantics only) ---------------

    def test_shop_rows_select_and_double_click_confirms(self) -> None:
        game = self.game
        self.start_run()
        game.shop_open = True
        game.shop_mode = "buy"
        game.shop_cursor = 0
        game._shop_visible_start = 0
        game._shop_visible_row_rects = [
            pygame.Rect(100, 100, 300, 24),
            pygame.Rect(100, 130, 300, 24),
        ]
        game._shop_mode_rects = (
            pygame.Rect(100, 60, 80, 24),
            pygame.Rect(190, 60, 80, 24),
        )
        game.handle_menu_mouse_motion((250, 142))
        self.assertEqual(game.shop_cursor, 1)
        with patch.object(type(game), "_dispatch_command") as dispatch:
            self.assertTrue(game.handle_menu_mouse_click((250, 142)))
            dispatch.assert_not_called()
            self.assertTrue(game.handle_menu_mouse_click((250, 142)))
            dispatch.assert_called_once()
        with patch.object(type(game), "cycle_shop_mode") as cycle:
            self.assertTrue(game.handle_menu_mouse_click((230, 70)))
            cycle.assert_called_once()
        game.shop_open = False

    # --- character tabs --------------------------------------------------

    def test_memory_token_prompt_click_opens_character_disciplines(self) -> None:
        game = self.game
        self.start_run()
        game.player.memory_tokens = 2
        game.character_menu_tab = "overview"
        # Desktop quest information is non-modal; its presence must not prevent
        # the bottom-left prompt from opening the requested Character tab.
        game.quest_info_visible = True
        game.draw()

        prompt = game._memory_token_prompt_rect
        self.assertIsInstance(prompt, pygame.Rect)
        assert isinstance(prompt, pygame.Rect)
        pygame.event.clear()
        pygame.event.post(
            pygame.event.Event(
                pygame.MOUSEBUTTONDOWN,
                button=1,
                pos=prompt.center,
                touch=False,
            )
        )
        with patch.object(game, "player_melee_attack") as melee:
            game.handle_events()

        self.assertTrue(game.character_menu_open)
        self.assertEqual(game.character_menu_tab, "disciplines")
        self.assertIsNotNone(game.character_menu_hovered_node)
        self.assertFalse(game.quest_info_visible)
        self.assertEqual(game.player.memory_tokens, 2)
        melee.assert_not_called()

    def test_character_tab_click_switches_tabs(self) -> None:
        game = self.game
        self.start_run()
        game.character_menu_open = True
        game.draw()
        tabs = game._character_tab_rects
        self.assertEqual(len(tabs), 2)
        self.assertTrue(game.handle_menu_mouse_click(tabs[1].center))
        self.assertEqual(game.character_menu_tab, "disciplines")
        self.assertTrue(game.handle_menu_mouse_click(tabs[0].center))
        self.assertEqual(game.character_menu_tab, "overview")
        # Clicks outside the tabs stay unconsumed so the discipline-cell /
        # gameplay branch keeps seeing them.
        self.assertFalse(game.handle_menu_mouse_click((2, 2)))

    # --- exit confirmation ----------------------------------------------

    def test_confirm_exit_rows_hover_and_click(self) -> None:
        game = self.game
        self.start_run()
        game.request_exit_confirmation()
        self.assertEqual(game.state, "confirm_exit")
        game.draw()
        rows = game._menu_row_rects
        self.assertEqual(len(rows), game.EXIT_CONFIRMATION_OPTION_COUNT)
        game.handle_menu_mouse_motion(rows[1].center)
        self.assertEqual(game.exit_confirmation_cursor, 1)
        with patch.object(
            type(game), "activate_exit_confirmation_selection"
        ) as activate:
            self.assertTrue(game.handle_menu_mouse_click(rows[1].center))
            activate.assert_called_once()

    # --- mp consent (fabricated rects) -----------------------------------

    def test_mp_consent_rows_hover_and_click(self) -> None:
        game = self.game
        game.state = "mp_consent"
        game._mp_row_rects = (
            pygame.Rect(100, 100, 300, 30),
            pygame.Rect(100, 140, 300, 30),
        )
        game.handle_menu_mouse_motion((120, 150))
        self.assertEqual(game.mp_consent_cursor, 1)
        with patch.object(type(game), "mp_consent_agree") as agree:
            self.assertTrue(game.handle_menu_mouse_click((120, 110)))
            agree.assert_called_once()
        with patch.object(type(game), "mp_consent_exit") as leave:
            self.assertTrue(game.handle_menu_mouse_click((120, 150)))
            leave.assert_called_once()

    # --- gameplay and overlays -------------------------------------------

    def test_gameplay_context_declines_and_overlays_continue(self) -> None:
        game = self.game
        self.start_run()
        self.assertFalse(game.handle_menu_mouse_motion((10, 10)))
        self.assertFalse(game.handle_menu_mouse_click((10, 10)))

        game.show_help = True
        self.assertTrue(game.handle_menu_mouse_click((10, 10)))
        self.assertFalse(game.show_help)

        game.state = "dead"
        self.assertTrue(game.handle_menu_mouse_click((10, 10)))
        self.assertEqual(game.state, "archetype_select")

    def test_text_input_session_blocks_menu_clicks(self) -> None:
        game = self.game
        game.state = "options"
        game.draw()
        rows = game._menu_row_rects
        game.open_text_input(
            target="mp_server_host",
            prompt="Multiplayer server host",
            initial="",
            max_length=128,
        )
        self.assertTrue(game.text_input_active())
        self.assertFalse(game.handle_menu_mouse_motion(rows[1].center))
        self.assertFalse(game.handle_menu_mouse_click(rows[1].center))
        game.close_text_input(confirm=False)

    # --- event-loop wiring ------------------------------------------------

    def test_event_loop_routes_desktop_mouse_to_menus(self) -> None:
        game = self.game
        game.state = "title"
        game.draw()
        rows = game._title_row_rects
        game.title_selection = 0

        pygame.event.clear()
        pygame.event.post(
            pygame.event.Event(pygame.MOUSEMOTION, pos=rows[4].center, rel=(3, 3))
        )
        game.handle_events()
        self.assertEqual(game.title_selection, 4)

        pygame.event.post(
            pygame.event.Event(
                pygame.MOUSEBUTTONDOWN, pos=rows[4].center, button=1
            )
        )
        game.handle_events()
        self.assertEqual(game.state, "options")


if __name__ == "__main__":
    unittest.main()
