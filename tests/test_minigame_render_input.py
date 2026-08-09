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

"""Responsive presentation and modal input for the 4.9.x mini-games."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from arch_rogue.game import Game
from arch_rogue.input import Command
from arch_rogue.story import (
    GARDEN_MINI_GAME,
    MINI_GAME_INSTRUCTIONS,
    MINI_GAME_TIME_LIMITS,
    SOUL_MINI_GAME,
    STORY_MINI_GAME,
    create_mini_game,
)


def _make_game(
    tmpdir: str,
    *,
    size: tuple[int, int] = (640, 360),
    mobile: bool = False,
) -> Game:
    game = Game(
        screen_size=size,
        headless=True,
        mobile=mobile,
        save_path=Path(tmpdir) / "run.json",
    )
    game.options_path = Path(tmpdir) / "options.json"
    game.state = "playing"
    game.active_cutscene = None
    game.story_intro_pending = False
    return game


def _playing_state(kind: str, *, instance_id: int = 1):
    state = create_mini_game(
        kind,
        instance_id=instance_id,
        seed=8173 + instance_id,
        depth=8,
    )
    state.phase = "play"
    state.time_left = MINI_GAME_TIME_LIMITS[kind]
    return state


class MiniGameRenderTests(unittest.TestCase):
    def test_ready_copy_is_not_duplicated_and_uses_authored_button(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            for instance_id, kind in enumerate(
                (STORY_MINI_GAME, GARDEN_MINI_GAME, SOUL_MINI_GAME),
                start=40,
            ):
                with self.subTest(kind=kind):
                    game = _make_game(tmpdir)
                    game.active_mini_game = create_mini_game(
                        kind,
                        instance_id=instance_id,
                        seed=91 + instance_id,
                    )
                    original_asset = game.ui_asset_surface
                    with (
                        patch.object(
                            game,
                            "draw_ui_text",
                            wraps=game.draw_ui_text,
                        ) as draw_text,
                        patch.object(
                            game,
                            "ui_asset_surface",
                            wraps=original_asset,
                        ) as draw_asset,
                    ):
                        game.draw()

                    rendered_copy = [
                        call.args[1]
                        for call in draw_text.call_args_list
                        if len(call.args) > 1
                    ]
                    self.assertNotIn("HOW TO PLAY", rendered_copy)
                    self.assertNotIn(
                        MINI_GAME_INSTRUCTIONS[kind],
                        rendered_copy,
                    )
                    self.assertFalse(
                        any("TIMER STARTS" in text for text in rendered_copy)
                    )
                    self.assertIn("READY", rendered_copy)
                    assert game._mini_game_ready_rect is not None
                    draw_asset.assert_any_call(
                        "menu.panel.action.accept",
                        game._mini_game_ready_rect.size,
                    )

    def test_ready_guide_replaces_board_with_one_large_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            for mobile in (False, True):
                with self.subTest(mobile=mobile):
                    game = _make_game(tmpdir, mobile=mobile)
                    game.active_mini_game = create_mini_game(
                        STORY_MINI_GAME,
                        instance_id=21 if mobile else 20,
                        seed=81,
                        required_player_ids=["p1", "p2"],
                    )

                    game.draw()

                    self.assertEqual(game._mini_game_cell_rects, [])
                    self.assertIsInstance(game._mini_game_ready_rect, pygame.Rect)
                    assert game._mini_game_ready_rect is not None
                    self.assertTrue(
                        game.screen.get_rect().contains(game._mini_game_ready_rect)
                    )
                    self.assertGreaterEqual(game._mini_game_ready_rect.width, 220)
                    self.assertGreaterEqual(game._mini_game_ready_rect.height, 48)

    def test_each_board_renders_large_nonoverlapping_hitboxes_and_skips_world(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_game(tmpdir)
            expected_counts = {
                STORY_MINI_GAME: 6,
                GARDEN_MINI_GAME: 9,
                SOUL_MINI_GAME: 8,
            }
            with (
                patch.object(game, "_render_world_view") as draw_world,
                patch.object(game, "draw_ui") as draw_hud,
            ):
                for instance_id, (kind, count) in enumerate(
                    expected_counts.items(), start=1
                ):
                    with self.subTest(kind=kind):
                        game.active_mini_game = _playing_state(
                            kind, instance_id=instance_id
                        )
                        game.draw()
                        rects = game._mini_game_cell_rects
                        self.assertEqual(len(rects), count)
                        self.assertTrue(
                            all(game.screen.get_rect().contains(rect) for rect in rects)
                        )
                        self.assertGreaterEqual(min(rect.width for rect in rects), 52)
                        for left, first in enumerate(rects):
                            for second in rects[left + 1 :]:
                                self.assertFalse(first.colliderect(second))
                draw_world.assert_not_called()
                draw_hud.assert_not_called()

    def test_each_kind_uses_authored_socket_and_keeps_procedural_fallback(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_game(tmpdir)
            expected = {
                STORY_MINI_GAME: "minigame.socket.story",
                GARDEN_MINI_GAME: "minigame.socket.garden",
                SOUL_MINI_GAME: "minigame.socket.soul",
            }
            original_lookup = game.ui_asset_surface
            for instance_id, (kind, socket_key) in enumerate(
                expected.items(), start=1
            ):
                with self.subTest(kind=kind):
                    game.active_mini_game = _playing_state(
                        kind,
                        instance_id=instance_id,
                    )
                    with patch.object(
                        game,
                        "ui_asset_surface",
                        wraps=original_lookup,
                    ) as lookup:
                        game.draw()
                    cell_size = game._mini_game_cell_rects[0].size
                    lookup.assert_any_call(socket_key, cell_size)

                    def without_socket(
                        asset_key: str,
                        size: tuple[int, int],
                    ):
                        if asset_key == socket_key:
                            return None
                        return original_lookup(asset_key, size)

                    with patch.object(
                        game,
                        "ui_asset_surface",
                        side_effect=without_socket,
                    ):
                        game.draw()
                    self.assertEqual(
                        len(game._mini_game_cell_rects),
                        len(game.active_mini_game.board),
                    )

    def test_mobile_board_has_no_persistent_cursor_highlight(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_game(tmpdir, mobile=True)
            game.active_mini_game = _playing_state(GARDEN_MINI_GAME)
            game.mini_game_cursor = 4
            original = game._draw_mini_game_cell
            probe = Mock(wraps=original)
            game._draw_mini_game_cell = probe

            game.draw()

            self.assertEqual(probe.call_count, 9)
            self.assertTrue(
                all(call.kwargs["selected"] is False for call in probe.call_args_list)
            )
            self.assertEqual(game.mobile_input_context(), "mini_game")
            self.assertIsNone(game._mobile_back_button_rect)


class MiniGameInputTests(unittest.TestCase):
    def test_ready_uses_interact_for_keyboard_controller_and_mouse(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_game(tmpdir)
            game.active_mini_game = create_mini_game(
                STORY_MINI_GAME,
                instance_id=30,
                seed=90,
                required_player_ids=["p1", "p2"],
            )
            game.confirm_active_mini_game_ready = Mock(return_value=True)
            game.activate_mini_game_cell = Mock(return_value=True)
            game.draw()
            assert game._mini_game_ready_rect is not None

            # Confirm/select and direct cell keys cannot skip the guide.
            self.assertEqual(game._input_context(), "gameplay")
            self.assertTrue(game._dispatch_command(Command.CONFIRM))
            game.confirm_active_mini_game_ready.assert_not_called()
            game.activate_mini_game_cell.assert_not_called()

            self.assertTrue(game._dispatch_command(Command.INTERACT))
            game.confirm_active_mini_game_ready.assert_called_once_with()
            game.confirm_active_mini_game_ready.reset_mock()

            pygame.event.post(
                pygame.event.Event(pygame.KEYDOWN, key=pygame.K_1, mod=0)
            )
            pygame.event.post(
                pygame.event.Event(pygame.KEYDOWN, key=pygame.K_e, mod=0)
            )
            game.handle_events()
            game.activate_mini_game_cell.assert_not_called()
            game.confirm_active_mini_game_ready.assert_called_once_with()
            game.confirm_active_mini_game_ready.reset_mock()

            event = pygame.event.Event(
                pygame.JOYBUTTONDOWN,
                joy=99,
                button=0,
            )
            self.assertTrue(game.handle_controller_event(event))
            game.confirm_active_mini_game_ready.assert_called_once_with()
            game.confirm_active_mini_game_ready.reset_mock()

            self.assertTrue(game.handle_menu_mouse_click((1, 1)))
            game.confirm_active_mini_game_ready.assert_not_called()
            self.assertTrue(
                game.handle_menu_mouse_click(game._mini_game_ready_rect.center)
            )
            game.confirm_active_mini_game_ready.assert_called_once_with()

    def test_ready_touch_requires_the_visible_button(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_game(tmpdir, mobile=True)
            game.active_mini_game = create_mini_game(
                SOUL_MINI_GAME,
                instance_id=31,
                seed=91,
                required_player_ids=["p1", "p2"],
            )
            game.confirm_active_mini_game_ready = Mock(return_value=True)
            game.draw()
            assert game._mini_game_ready_rect is not None

            self.assertTrue(game.handle_mobile_tap((1, 1)))
            game.confirm_active_mini_game_ready.assert_not_called()
            self.assertTrue(
                game.handle_mobile_tap(game._mini_game_ready_rect.center)
            )
            game.confirm_active_mini_game_ready.assert_called_once_with()

    def test_keyboard_controller_mouse_and_back_are_modal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_game(tmpdir)
            game.active_mini_game = _playing_state(STORY_MINI_GAME)
            game.activate_mini_game_cell = Mock(return_value=True)
            game.request_exit_confirmation = Mock()
            game.draw()

            self.assertEqual(game._input_context(), "mini_game")
            self.assertTrue(game._dispatch_command(Command.RIGHT))
            self.assertEqual(game.mini_game_cursor, 1)
            self.assertTrue(game._dispatch_command(Command.DOWN))
            self.assertEqual(game.mini_game_cursor, 4)
            self.assertTrue(game._dispatch_command(Command.CONFIRM))
            game.activate_mini_game_cell.assert_called_once_with(4)

            self.assertTrue(
                game.handle_menu_mouse_motion(game._mini_game_cell_rects[2].center)
            )
            self.assertEqual(game.mini_game_cursor, 2)
            self.assertTrue(
                game.handle_menu_mouse_click(game._mini_game_cell_rects[2].center)
            )
            game.activate_mini_game_cell.assert_called_with(2)
            calls = game.activate_mini_game_cell.call_count
            self.assertTrue(game.handle_menu_mouse_click((1, 1)))
            self.assertEqual(game.activate_mini_game_cell.call_count, calls)

            self.assertTrue(game._dispatch_command(Command.BACK))
            game.request_exit_confirmation.assert_not_called()

    def test_touch_activates_cells_and_consumes_misses_and_swipes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_game(tmpdir, mobile=True)
            game.active_mini_game = _playing_state(SOUL_MINI_GAME)
            game.activate_mini_game_cell = Mock(return_value=True)
            game.draw()
            point = game._mini_game_cell_rects[6].center

            self.assertTrue(game.handle_mobile_tap(point))
            self.assertEqual(game.mini_game_cursor, 6)
            game.activate_mini_game_cell.assert_called_once_with(6)
            self.assertTrue(game.handle_mobile_tap((1, 1)))
            game.activate_mini_game_cell.assert_called_once_with(6)

            game.mini_game_cursor = 6
            game._handle_mobile_swipe("tap", 0, -200, point)
            self.assertEqual(game.mini_game_cursor, 6)
            game.activate_mini_game_cell.assert_called_once_with(6)


if __name__ == "__main__":
    unittest.main()
