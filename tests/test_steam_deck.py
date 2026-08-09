# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
"""Steam Deck detection helper behaviour (Phase 7a — Deck readiness).

The detector reads Valve's DMI product identifiers from sysfs and an
``ARCH_ROGUE_STEAM_DECK`` environment override. These tests cover:

* the env override wins in both directions and on every platform,
* off-Linux platforms never report a Deck even when the override is unset,
* the DMI probe path matches Valve + Jupiter/Galileo and rejects unknown
  Valve hardware or non-Valve vendors,
* results are cached per process and ``clear_detection_cache`` resets them,
* the model name surfaces through ``steam_deck_model``.

DMI reads are patched so the tests do not depend on the host actually being a
Deck (CI runs on a generic Ubuntu runner).
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import json  # noqa: E402

import pygame  # noqa: E402

from arch_rogue import steam_deck  # noqa: E402
from arch_rogue.constants import (  # noqa: E402
    GRAPHICS_TIER_HD,
    GRAPHICS_TIER_MODERN,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
)
from arch_rogue.content import ARCHETYPES, DISCIPLINES  # noqa: E402
from arch_rogue.game import Game  # noqa: E402
from arch_rogue.input import (  # noqa: E402
    DECK_GAMEPAD_PROFILE_VERSION,
    Command,
)


def make_desktop_game(tmpdir: str) -> Game:
    game = Game(
        screen_size=(820, 540),
        headless=True,
        save_path=Path(tmpdir) / "run.json",
    )
    game.options_path = Path(tmpdir) / "options.json"
    game.rng.seed(2026)
    game.restart(ARCHETYPES[0])
    if game.story_intro_pending:
        game.choose_story_relic_path(0)
    game.active_cutscene = None
    return game


def deck_finger_event(
    event_type: int,
    finger_id: int,
    x: float,
    y: float,
) -> pygame.event.Event:
    return pygame.event.Event(
        event_type,
        touch_id=0,
        finger_id=finger_id,
        x=x,
        y=y,
    )


def force_deck() -> None:
    """Force deck detection on for the duration of a single test."""

    steam_deck.clear_detection_cache()
    os.environ[steam_deck._OVERRIDE_ENV] = "1"


def clear_deck() -> None:
    steam_deck.clear_detection_cache()
    os.environ.pop(steam_deck._OVERRIDE_ENV, None)


def patch_deck_on():
    """Context manager that forces deck detection on within its block."""

    from contextlib import contextmanager

    @contextmanager
    def _cm():
        steam_deck.clear_detection_cache()
        prior = os.environ.get(steam_deck._OVERRIDE_ENV)
        os.environ[steam_deck._OVERRIDE_ENV] = "1"
        try:
            yield
        finally:
            steam_deck.clear_detection_cache()
            if prior is None:
                os.environ.pop(steam_deck._OVERRIDE_ENV, None)
            else:
                os.environ[steam_deck._OVERRIDE_ENV] = prior

    return _cm()


class SteamDeckDetectionTests(unittest.TestCase):
    def setUp(self) -> None:
        # Every test starts from a clean cache so prior cases cannot leak.
        steam_deck.clear_detection_cache()
        # Drop the override between cases; patch.dict is used below for the
        # actual assertions so we never mutate the real environment.
        os.environ.pop(steam_deck._OVERRIDE_ENV, None)

    def tearDown(self) -> None:
        steam_deck.clear_detection_cache()
        os.environ.pop(steam_deck._OVERRIDE_ENV, None)

    def test_env_override_force_on_without_dmi(self) -> None:
        with patch.dict(os.environ, {"ARCH_ROGUE_STEAM_DECK": "1"}):
            self.assertTrue(steam_deck.is_steam_deck())
            # Forced on without a real DMI read → no model name available.
            self.assertIsNone(steam_deck.steam_deck_model())

    def test_env_override_force_off_even_on_a_real_deck(self) -> None:
        def fake_read(path: str) -> str | None:
            if path == steam_deck._BOARD_VENDOR_PATH:
                return "Valve"
            if path == steam_deck._PRODUCT_NAME_PATH:
                return "Jupiter"
            return None

        with patch.dict(os.environ, {"ARCH_ROGUE_STEAM_DECK": "0"}), patch(
            f"{steam_deck.__name__}._read_dmi_field", side_effect=fake_read
        ), patch.object(sys, "platform", "linux"):
            self.assertFalse(steam_deck.is_steam_deck())
            self.assertIsNone(steam_deck.steam_deck_model())

    def test_env_override_unknown_value_falls_through_to_dmi(self) -> None:
        def fake_read(path: str) -> str | None:
            if path == steam_deck._BOARD_VENDOR_PATH:
                return "Valve"
            if path == steam_deck._PRODUCT_NAME_PATH:
                return "Galileo"
            return None

        with patch.dict(
            os.environ, {"ARCH_ROGUE_STEAM_DECK": "maybe"}
        ), patch(
            f"{steam_deck.__name__}._read_dmi_field", side_effect=fake_read
        ), patch.object(sys, "platform", "linux"):
            self.assertTrue(steam_deck.is_steam_deck())
            self.assertEqual(steam_deck.steam_deck_model(), "Galileo")

    def test_off_linux_never_reports_deck_without_override(self) -> None:
        with patch.object(sys, "platform", "win32"):
            self.assertFalse(steam_deck.is_steam_deck())
            self.assertIsNone(steam_deck.steam_deck_model())

    def test_off_linux_env_override_still_wins(self) -> None:
        # The override must work on Windows too — a developer might be on a
        # Windows laptop validating Deck-specific code paths.
        with patch.object(sys, "platform", "win32"), patch.dict(
            os.environ, {"ARCH_ROGUE_STEAM_DECK": "true"}
        ):
            self.assertTrue(steam_deck.is_steam_deck())

    def test_valve_jupiter_lcd_deck_is_detected(self) -> None:
        def fake_read(path: str) -> str | None:
            if path == steam_deck._BOARD_VENDOR_PATH:
                return "Valve"
            if path == steam_deck._PRODUCT_NAME_PATH:
                return "Jupiter"
            return None

        with patch(
            f"{steam_deck.__name__}._read_dmi_field", side_effect=fake_read
        ), patch.object(sys, "platform", "linux"):
            self.assertTrue(steam_deck.is_steam_deck())
            self.assertEqual(steam_deck.steam_deck_model(), "Jupiter")

    def test_valve_galileo_oled_deck_is_detected(self) -> None:
        def fake_read(path: str) -> str | None:
            if path == steam_deck._BOARD_VENDOR_PATH:
                return "Valve"
            if path == steam_deck._PRODUCT_NAME_PATH:
                return "Galileo"
            return None

        with patch(
            f"{steam_deck.__name__}._read_dmi_field", side_effect=fake_read
        ), patch.object(sys, "platform", "linux"):
            self.assertTrue(steam_deck.is_steam_deck())
            self.assertEqual(steam_deck.steam_deck_model(), "Galileo")

    def test_non_valve_vendor_is_not_a_deck(self) -> None:
        def fake_read(path: str) -> str | None:
            if path == steam_deck._BOARD_VENDOR_PATH:
                return "ASUS"
            if path == steam_deck._PRODUCT_NAME_PATH:
                return "Jupiter"
            return None

        with patch(
            f"{steam_deck.__name__}._read_dmi_field", side_effect=fake_read
        ), patch.object(sys, "platform", "linux"):
            self.assertFalse(steam_deck.is_steam_deck())
            self.assertIsNone(steam_deck.steam_deck_model())

    def test_valve_vendor_unknown_product_is_not_a_deck(self) -> None:
        # Valve ships other hardware (Index, devkits) that should not pick up
        # Deck-specific defaults.
        def fake_read(path: str) -> str | None:
            if path == steam_deck._BOARD_VENDOR_PATH:
                return "Valve"
            if path == steam_deck._PRODUCT_NAME_PATH:
                return "Index"
            return None

        with patch(
            f"{steam_deck.__name__}._read_dmi_field", side_effect=fake_read
        ), patch.object(sys, "platform", "linux"):
            self.assertFalse(steam_deck.is_steam_deck())
            self.assertIsNone(steam_deck.steam_deck_model())

    def test_missing_dmi_files_treated_as_not_deck(self) -> None:
        with patch(
            f"{steam_deck.__name__}._read_dmi_field", return_value=None
        ), patch.object(sys, "platform", "linux"):
            self.assertFalse(steam_deck.is_steam_deck())

    def test_blank_dmi_fields_treated_as_not_deck(self) -> None:
        def fake_read(path: str) -> str | None:
            if path == steam_deck._BOARD_VENDOR_PATH:
                return "   "
            if path == steam_deck._PRODUCT_NAME_PATH:
                return "Jupiter"
            return None

        with patch(
            f"{steam_deck.__name__}._read_dmi_field", side_effect=fake_read
        ), patch.object(sys, "platform", "linux"):
            self.assertFalse(steam_deck.is_steam_deck())

    def test_detection_is_cached_across_calls(self) -> None:
        calls: list[str] = []

        def fake_read(path: str) -> str | None:
            calls.append(path)
            if path == steam_deck._BOARD_VENDOR_PATH:
                return "Valve"
            if path == steam_deck._PRODUCT_NAME_PATH:
                return "Jupiter"
            return None

        with patch(
            f"{steam_deck.__name__}._read_dmi_field", side_effect=fake_read
        ), patch.object(sys, "platform", "linux"):
            steam_deck.is_steam_deck()
            steam_deck.is_steam_deck()
            steam_deck.steam_deck_model()
        # DMI is read at most twice per detection (vendor + product); the cache
        # ensures subsequent calls do not re-read.
        self.assertEqual(len(calls), 2)

    def test_clear_detection_cache_forces_reread(self) -> None:
        reads: list[str] = []

        def fake_read(path: str) -> str | None:
            reads.append(path)
            if path == steam_deck._BOARD_VENDOR_PATH:
                return "Valve"
            if path == steam_deck._PRODUCT_NAME_PATH:
                return "Jupiter"
            return None

        with patch(
            f"{steam_deck.__name__}._read_dmi_field", side_effect=fake_read
        ), patch.object(sys, "platform", "linux"):
            steam_deck.is_steam_deck()
            steam_deck.clear_detection_cache()
            steam_deck.is_steam_deck()
        self.assertEqual(len(reads), 4)


class DeckGamepadProfileMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_deck()

    def tearDown(self) -> None:
        clear_deck()

    @staticmethod
    def old_gamepad_mapping() -> dict[str, object]:
        return {
            "gameplay_buttons": {
                "0": Command.INTERACT,
                "5": Command.ABILITY_6,
                "15": Command.CHARACTER,
            },
            "triggers": [Command.ABILITY_1, Command.ABILITY_4],
        }

    def test_old_deck_profile_gains_new_aliases_once(self) -> None:
        with patch_deck_on(), tempfile.TemporaryDirectory() as tmpdir:
            game = make_desktop_game(tmpdir)
            data = game.options_to_dict()
            data.pop("deck_gamepad_profile_version", None)
            data["gamepad_mapping"] = self.old_gamepad_mapping()
            game.options_path.write_text(json.dumps(data), encoding="utf-8")

            self.assertTrue(game.load_options())
            buttons = game.gamepad_mapping["gameplay_buttons"]
            self.assertEqual(buttons[9], Command.ABILITY_6)
            self.assertEqual(buttons[16], Command.OPEN_DISCIPLINES)

    def test_current_profile_does_not_restore_removed_aliases(self) -> None:
        with patch_deck_on(), tempfile.TemporaryDirectory() as tmpdir:
            game = make_desktop_game(tmpdir)
            data = game.options_to_dict()
            data["deck_gamepad_profile_version"] = DECK_GAMEPAD_PROFILE_VERSION
            data["gamepad_mapping"] = self.old_gamepad_mapping()
            game.options_path.write_text(json.dumps(data), encoding="utf-8")

            self.assertTrue(game.load_options())
            buttons = game.gamepad_mapping["gameplay_buttons"]
            self.assertNotIn(9, buttons)
            self.assertNotIn(16, buttons)


class DeckGraphicsTierDefaultTests(unittest.TestCase):
    """Fresh desktop installs default to HD, including Steam Deck."""

    def setUp(self) -> None:
        clear_deck()

    def tearDown(self) -> None:
        clear_deck()

    def test_off_deck_fresh_install_uses_hd(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_desktop_game(tmpdir)
            self.assertFalse(steam_deck.is_steam_deck())
            self.assertEqual(game.graphics_tier, GRAPHICS_TIER_HD)
            self.assertEqual(game._authored_graphics_tier, GRAPHICS_TIER_HD)

    def test_on_deck_fresh_install_uses_hd(self) -> None:
        with patch_deck_on():
            self.assertTrue(steam_deck.is_steam_deck())
            with tempfile.TemporaryDirectory() as tmpdir:
                game = make_desktop_game(tmpdir)
                self.assertEqual(game.graphics_tier, GRAPHICS_TIER_HD)
                self.assertEqual(game._authored_graphics_tier, GRAPHICS_TIER_HD)

    def test_saved_modern_preference_wins_over_deck_hd_default(self) -> None:
        with patch_deck_on(), tempfile.TemporaryDirectory() as tmpdir:
            game = make_desktop_game(tmpdir)
            game.set_graphics_tier(GRAPHICS_TIER_MODERN)
            self.assertTrue(game.save_options())

            reloaded = Game(
                screen_size=(820, 540),
                headless=True,
                save_path=Path(tmpdir) / "run.json",
            )
            reloaded.options_path = Path(tmpdir) / "options.json"
            self.assertTrue(reloaded.load_options())
            self.assertEqual(reloaded.graphics_tier, GRAPHICS_TIER_MODERN)
            self.assertEqual(
                reloaded._authored_graphics_tier,
                GRAPHICS_TIER_MODERN,
            )


class DeckTouchscreenTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_deck()

    def tearDown(self) -> None:
        clear_deck()

    def test_single_finger_tap_routes_on_release(self) -> None:
        with patch_deck_on(), tempfile.TemporaryDirectory() as tmpdir:
            game = make_desktop_game(tmpdir)
            down = deck_finger_event(pygame.FINGERDOWN, 1, 0.25, 0.4)
            up = deck_finger_event(pygame.FINGERUP, 1, 0.25, 0.4)
            with patch.object(
                game, "handle_menu_mouse_click", return_value=True
            ) as click:
                self.assertTrue(game.handle_deck_pinch_event(down))
                click.assert_not_called()
                self.assertTrue(game.handle_deck_pinch_event(up))
            click.assert_called_once_with((205, 216))

    def test_discipline_tap_selects_cell_on_release(self) -> None:
        with patch_deck_on(), tempfile.TemporaryDirectory() as tmpdir:
            game = make_desktop_game(tmpdir)
            game.character_menu_open = True
            game.character_menu_tab = "disciplines"
            game._discipline_cells = {
                "discipline.test": pygame.Rect(180, 190, 80, 60)
            }
            down = deck_finger_event(pygame.FINGERDOWN, 2, 0.25, 0.4)
            up = deck_finger_event(pygame.FINGERUP, 2, 0.25, 0.4)
            with patch.object(game, "choose_discipline") as choose:
                game.handle_deck_pinch_event(down)
                choose.assert_not_called()
                game.handle_deck_pinch_event(up)
            choose.assert_called_once_with("discipline.test")

    def test_two_finger_pinch_never_activates_first_finger_ui(self) -> None:
        with patch_deck_on(), tempfile.TemporaryDirectory() as tmpdir:
            game = make_desktop_game(tmpdir)
            game.view_zoom = 1.0
            events = (
                deck_finger_event(pygame.FINGERDOWN, 3, 0.2, 0.2),
                deck_finger_event(pygame.FINGERDOWN, 4, 0.8, 0.8),
                deck_finger_event(pygame.FINGERMOTION, 4, 0.9, 0.9),
                deck_finger_event(pygame.FINGERUP, 4, 0.9, 0.9),
                deck_finger_event(pygame.FINGERUP, 3, 0.2, 0.2),
            )
            with patch.object(
                game, "handle_menu_mouse_click", return_value=True
            ) as click:
                for event in events:
                    self.assertTrue(game.handle_deck_pinch_event(event))
            click.assert_not_called()
            self.assertGreater(game.view_zoom, 1.0)
            self.assertFalse(game._deck_pinch_active)
            self.assertEqual(game._deck_pinch_fingers, {})

    def test_single_finger_drag_does_not_activate_ui(self) -> None:
        with patch_deck_on(), tempfile.TemporaryDirectory() as tmpdir:
            game = make_desktop_game(tmpdir)
            events = (
                deck_finger_event(pygame.FINGERDOWN, 5, 0.2, 0.2),
                deck_finger_event(pygame.FINGERMOTION, 5, 0.4, 0.4),
                deck_finger_event(pygame.FINGERUP, 5, 0.4, 0.4),
            )
            with patch.object(
                game, "handle_menu_mouse_click", return_value=True
            ) as click:
                for event in events:
                    game.handle_deck_pinch_event(event)
            click.assert_not_called()


class DeckDisplayModeTests(unittest.TestCase):
    """On the Deck, fullscreen renders at the panel size, not 2560×1440."""

    def setUp(self) -> None:
        clear_deck()

    def tearDown(self) -> None:
        clear_deck()

    def test_off_deck_fullscreen_uses_fixed_canvas(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_desktop_game(tmpdir)
            game.fullscreen = True
            captured: dict[str, object] = {}

            def fake_set_mode(size, flags=0, depth=0, display=0):
                captured["size"] = tuple(size)
                captured["flags"] = flags
                return pygame.Surface(size)

            fake_info = MagicMock()
            fake_info.current_w = 2560
            fake_info.current_h = 1440
            with patch.object(pygame.display, "set_mode", side_effect=fake_set_mode), \
                 patch.object(pygame.display, "Info", return_value=fake_info):
                game.apply_display_mode(headless=False)
            self.assertEqual(captured["size"], (SCREEN_WIDTH, SCREEN_HEIGHT))

    def test_on_deck_fullscreen_uses_panel_size(self) -> None:
        with patch_deck_on():
            with tempfile.TemporaryDirectory() as tmpdir:
                game = make_desktop_game(tmpdir)
                game.fullscreen = True
                captured: dict[str, object] = {}

                def fake_set_mode(size, flags=0, depth=0, display=0):
                    captured["size"] = tuple(size)
                    captured["flags"] = flags
                    return pygame.Surface(size)

                # pygame.display.Info() under SDL_VIDEODRIVER=dummy reports the
                # dummy 1×1 surface; patch it to look like a 1280×800 Deck panel.
                fake_info = MagicMock()
                fake_info.current_w = 1280
                fake_info.current_h = 800
                with patch.object(pygame.display, "set_mode", side_effect=fake_set_mode), \
                     patch.object(pygame.display, "Info", return_value=fake_info):
                    game.apply_display_mode(headless=False)
                self.assertEqual(captured["size"], (1280, 800))
                self.assertTrue(captured["flags"] & pygame.FULLSCREEN)
                self.assertTrue(captured["flags"] & pygame.SCALED)

    def test_off_deck_non_16_9_display_matches_canvas_aspect(self) -> None:
        # A 16:10 panel without Deck DMI detection (e.g. a sandboxed install
        # on a Deck, or any 16:10 laptop): the logical canvas keeps the
        # quality-capped height but widens/narrows to the display aspect so
        # FULLSCREEN|SCALED fills the screen instead of letterboxing.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_desktop_game(tmpdir)
            game.fullscreen = True
            captured: dict[str, object] = {}

            def fake_set_mode(size, flags=0, depth=0, display=0):
                captured["size"] = tuple(size)
                captured["flags"] = flags
                return pygame.Surface(size)

            fake_info = MagicMock()
            fake_info.current_w = 1280
            fake_info.current_h = 800
            with patch.object(pygame.display, "set_mode", side_effect=fake_set_mode), \
                 patch.object(pygame.display, "Info", return_value=fake_info):
                game.apply_display_mode(headless=False)
            self.assertEqual(captured["size"], (2304, 1440))
            self.assertTrue(captured["flags"] & pygame.FULLSCREEN)
            self.assertTrue(captured["flags"] & pygame.SCALED)

    def test_off_deck_windowed_uses_fixed_canvas_scaled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_desktop_game(tmpdir)
            game.fullscreen = False
            captured: dict[str, object] = {}

            def fake_set_mode(size, flags=0, depth=0, display=0):
                captured["size"] = tuple(size)
                captured["flags"] = flags
                return pygame.Surface(size)

            fake_info = MagicMock()
            fake_info.current_w = 2560
            fake_info.current_h = 1440
            with patch.object(pygame.display, "set_mode", side_effect=fake_set_mode), \
                 patch.object(pygame.display, "Info", return_value=fake_info):
                game.apply_display_mode(headless=False)
            self.assertEqual(captured["size"], (SCREEN_WIDTH, SCREEN_HEIGHT))
            self.assertTrue(captured["flags"] & pygame.RESIZABLE)
            self.assertTrue(captured["flags"] & pygame.SCALED)

    def test_on_deck_windowed_uses_panel_logical_size(self) -> None:
        with patch_deck_on():
            with tempfile.TemporaryDirectory() as tmpdir:
                game = make_desktop_game(tmpdir)
                game.fullscreen = False
                captured: dict[str, object] = {}

                def fake_set_mode(size, flags=0, depth=0, display=0):
                    captured["size"] = tuple(size)
                    captured["flags"] = flags
                    return pygame.Surface(size)

                fake_info = MagicMock()
                fake_info.current_w = 1280
                fake_info.current_h = 800
                with patch.object(pygame.display, "set_mode", side_effect=fake_set_mode), \
                     patch.object(pygame.display, "Info", return_value=fake_info):
                    game.apply_display_mode(headless=False)
                self.assertEqual(captured["size"], (1280, 800))
                self.assertTrue(captured["flags"] & pygame.RESIZABLE)
                self.assertTrue(captured["flags"] & pygame.SCALED)

    def test_off_deck_render_resolution_tiers_shrink_canvas(self) -> None:
        # 4.9.25: the desktop render-resolution option swaps the fixed canvas
        # between native 1440p and the 720p/540p performance tiers; both
        # windowed and fullscreen flow through the same logical size.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_desktop_game(tmpdir)
            captured: dict[str, object] = {}

            def fake_set_mode(size, flags=0, depth=0, display=0):
                captured["size"] = tuple(size)
                captured["flags"] = flags
                return pygame.Surface(size)

            fake_info = MagicMock()
            fake_info.current_w = 2560
            fake_info.current_h = 1440
            with patch.object(pygame.display, "set_mode", side_effect=fake_set_mode), \
                 patch.object(pygame.display, "Info", return_value=fake_info):
                for fullscreen in (True, False):
                    game.fullscreen = fullscreen
                    for quality, expected in (
                        ("balanced", (1280, 720)),
                        ("performance", (960, 540)),
                        ("native", (SCREEN_WIDTH, SCREEN_HEIGHT)),
                    ):
                        game.desktop_render_quality = quality
                        game.apply_display_mode(headless=False)
                        self.assertEqual(captured["size"], expected)

    def test_on_deck_render_resolution_is_hidden_and_inert(self) -> None:
        # The Deck renders panel-native (already the cheapest configuration):
        # the row never exists there and the canvas ignores the tier.
        with patch_deck_on():
            with tempfile.TemporaryDirectory() as tmpdir:
                game = make_desktop_game(tmpdir)
                self.assertEqual(game.OPTIONS_ROW_RENDER_RES, -1)
                self.assertFalse(game.cycle_desktop_render_quality(True))
                game.desktop_render_quality = "performance"
                game.fullscreen = True
                captured: dict[str, object] = {}

                def fake_set_mode(size, flags=0, depth=0, display=0):
                    captured["size"] = tuple(size)
                    return pygame.Surface(size)

                fake_info = MagicMock()
                fake_info.current_w = 1280
                fake_info.current_h = 800
                with patch.object(pygame.display, "set_mode", side_effect=fake_set_mode), \
                     patch.object(pygame.display, "Info", return_value=fake_info):
                    game.apply_display_mode(headless=False)
                self.assertEqual(captured["size"], (1280, 800))

    def test_on_deck_invalid_display_info_falls_back_to_canvas(self) -> None:
        with patch_deck_on():
            with tempfile.TemporaryDirectory() as tmpdir:
                game = make_desktop_game(tmpdir)
                game.fullscreen = True
                captured: dict[str, object] = {}

                def fake_set_mode(size, flags=0, depth=0, display=0):
                    captured["size"] = tuple(size)
                    return pygame.Surface(size)

                fake_info = MagicMock()
                fake_info.current_w = 0
                fake_info.current_h = 0
                with patch.object(pygame.display, "set_mode", side_effect=fake_set_mode), \
                     patch.object(pygame.display, "Info", return_value=fake_info):
                    game.apply_display_mode(headless=False)
                self.assertEqual(captured["size"], (SCREEN_WIDTH, SCREEN_HEIGHT))


class DeckDisciplineHintTests(unittest.TestCase):
    """5.0: the discipline hint bar is the only readable node copy on Deck."""

    def setUp(self) -> None:
        clear_deck()

    def tearDown(self) -> None:
        clear_deck()

    def test_hint_bar_uses_the_standard_menu_font_on_deck(self) -> None:
        with patch_deck_on(), tempfile.TemporaryDirectory() as tmpdir:
            game = Game(
                screen_size=(1280, 800),
                headless=True,
                save_path=Path(tmpdir) / "run.json",
            )
            game.options_path = Path(tmpdir) / "options.json"
            game.rng.seed(2026)
            game.restart(ARCHETYPES[0])
            if game.story_intro_pending:
                game.choose_story_relic_path(0)
            game.active_cutscene = None
            game.character_menu_open = True
            game.character_menu_tab = "disciplines"
            game.character_menu_hovered_node = None
            game.draw_character_menu()

            hint = pygame.Rect(game._discipline_footer_layout["hint"])
            # Footer budget reserves the standard font's height (was
            # small_font's ~11 px before 5.0).
            self.assertGreaterEqual(
                hint.height, game.font.get_height() + game.menus.u(4)
            )

            # Hovering a node renders its description with the standard font
            # (fit_menu_font may shrink pathological lengths, but a typical
            # description keeps the full size).
            tree = None
            for node in DISCIPLINES:
                if node.archetype == game.player.class_name and node.degree == 1:
                    tree = node
                    break
            assert tree is not None
            game.character_menu_hovered_node = tree.key
            game.draw_character_menu()
            detail = game._discipline_detail_layout
            self.assertEqual(detail["node_key"], tree.key)
            self.assertGreater(
                detail["font"].get_height(),
                game.small_font.get_height(),
                "Deck hint description no longer uses the enlarged font",
            )


class DeckLifecycleTests(unittest.TestCase):
    """Steam Deck suspend/resume events save the run and pause audio."""

    def setUp(self) -> None:
        clear_deck()

    def tearDown(self) -> None:
        clear_deck()

    def test_off_deck_lifecycle_events_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_desktop_game(tmpdir)
            self.assertFalse(steam_deck.is_steam_deck())
            event = pygame.event.Event(getattr(pygame, "APP_WILLENTERBACKGROUND", -20))
            self.assertFalse(game.handle_deck_lifecycle_event(event))
            self.assertFalse(game.deck_suspended)

    def test_background_event_saves_run_and_pauses_audio(self) -> None:
        with patch_deck_on():
            with tempfile.TemporaryDirectory() as tmpdir:
                game = make_desktop_game(tmpdir)
                self.assertEqual(game.state, "playing")
                game.player.gold = 31337
                game._deck_pinch_fingers[1] = (0.2, 0.2)
                game._deck_touch_starts[1] = (0.2, 0.2)
                game._deck_pinch_active = True
                game._deck_pinch_start_distance = 0.4
                with patch.object(game.audio, "suspend") as suspend:
                    event = pygame.event.Event(
                        getattr(pygame, "APP_WILLENTERBACKGROUND", -20)
                    )
                    self.assertTrue(game.handle_deck_lifecycle_event(event))
                    suspend.assert_called_once_with()
                self.assertTrue(game.deck_suspended)
                self.assertEqual(game._deck_pinch_fingers, {})
                self.assertEqual(game._deck_touch_starts, {})
                self.assertFalse(game._deck_pinch_active)
                self.assertEqual(game._deck_pinch_start_distance, 0.0)
                self.assertTrue(game.save_path.exists())
                saved = json.loads(game.save_path.read_text(encoding="utf-8"))
                self.assertEqual(saved["player"]["gold"], 31337)

    def test_foreground_event_clears_suspension_and_resumes_audio(self) -> None:
        with patch_deck_on():
            with tempfile.TemporaryDirectory() as tmpdir:
                game = make_desktop_game(tmpdir)
                game.handle_deck_lifecycle_event(
                    pygame.event.Event(getattr(pygame, "APP_WILLENTERBACKGROUND", -20))
                )
                self.assertTrue(game.deck_suspended)
                with patch.object(game.audio, "resume") as resume:
                    game.handle_deck_lifecycle_event(
                        pygame.event.Event(
                            getattr(pygame, "APP_DIDENTERFOREGROUND", -23)
                        )
                    )
                    resume.assert_called_once_with()
                self.assertFalse(game.deck_suspended)

    def test_second_background_event_is_idempotent(self) -> None:
        with patch_deck_on():
            with tempfile.TemporaryDirectory() as tmpdir:
                game = make_desktop_game(tmpdir)
                game.handle_deck_lifecycle_event(
                    pygame.event.Event(getattr(pygame, "APP_WILLENTERBACKGROUND", -20))
                )
                with patch.object(game, "save_run") as save_run:
                    game.handle_deck_lifecycle_event(
                        pygame.event.Event(getattr(pygame, "APP_WILLENTERBACKGROUND", -20))
                    )
                    save_run.assert_not_called()

    def test_terminating_event_saves_active_run(self) -> None:
        with patch_deck_on():
            with tempfile.TemporaryDirectory() as tmpdir:
                game = make_desktop_game(tmpdir)
                with patch.object(game, "save_run", return_value=True) as save_run:
                    event = pygame.event.Event(getattr(pygame, "APP_TERMINATING", -24))
                    self.assertTrue(game.handle_deck_lifecycle_event(event))
                    save_run.assert_called_once_with()

    def test_suspended_update_is_noop(self) -> None:
        with patch_deck_on():
            with tempfile.TemporaryDirectory() as tmpdir:
                game = make_desktop_game(tmpdir)
                elapsed_before = game.elapsed
                game.handle_deck_lifecycle_event(
                    pygame.event.Event(getattr(pygame, "APP_WILLENTERBACKGROUND", -20))
                )
                game.update(dt=0.016)
                self.assertEqual(game.elapsed, elapsed_before)

    def test_unrelated_event_is_not_consumed(self) -> None:
        with patch_deck_on():
            with tempfile.TemporaryDirectory() as tmpdir:
                game = make_desktop_game(tmpdir)
                self.assertFalse(
                    game.handle_deck_lifecycle_event(
                        pygame.event.Event(pygame.QUIT)
                    )
                )
                self.assertFalse(game.deck_suspended)




class DeckOptionsFullscreenTests(unittest.TestCase):
    """Fullscreen row is hidden from the options menu on Steam Deck."""

    def setUp(self) -> None:
        clear_deck()

    def tearDown(self) -> None:
        clear_deck()

    def test_off_deck_has_16_option_rows(self) -> None:
        # 16 rather than 17 since 4.11.0: the music row is parked until real
        # tracks exist.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_desktop_game(tmpdir)
            self.assertEqual(game.OPTIONS_ROW_COUNT, 16)
            self.assertEqual(game.OPTIONS_ROW_BACK, 15)
            self.assertEqual(game.OPTIONS_ROW_FULLSCREEN, 0)
            self.assertEqual(game.OPTIONS_ROW_RENDER_RES, 1)
            self.assertEqual(game.OPTIONS_ROW_DIFFICULTY, 2)

    def test_on_deck_has_13_option_rows(self) -> None:
        with patch_deck_on():
            with tempfile.TemporaryDirectory() as tmpdir:
                game = make_desktop_game(tmpdir)
                self.assertEqual(game.OPTIONS_ROW_COUNT, 13)
                self.assertEqual(game.OPTIONS_ROW_BACK, 12)

    def test_on_deck_fullscreen_row_is_invalid(self) -> None:
        with patch_deck_on():
            with tempfile.TemporaryDirectory() as tmpdir:
                game = make_desktop_game(tmpdir)
                self.assertEqual(game.OPTIONS_ROW_FULLSCREEN, -1)

    def test_on_deck_row_indices_shift_down(self) -> None:
        with patch_deck_on():
            with tempfile.TemporaryDirectory() as tmpdir:
                game = make_desktop_game(tmpdir)
                self.assertEqual(game.OPTIONS_ROW_DIFFICULTY, 0)
                self.assertEqual(game.OPTIONS_ROW_UI_SCALE, -1)
                self.assertEqual(game.OPTIONS_ROW_GRAPHICS, 1)
                self.assertEqual(game.OPTIONS_ROW_AUDIO, 5)
                self.assertEqual(game.OPTIONS_ROW_PERF_OVERLAY, 11)

    def test_on_deck_f_key_does_not_toggle_fullscreen(self) -> None:
        with patch_deck_on():
            with tempfile.TemporaryDirectory() as tmpdir:
                game = make_desktop_game(tmpdir)
                game.state = "options"
                game.fullscreen = True
                pygame.event.clear()
                pygame.event.post(
                    pygame.event.Event(pygame.KEYDOWN, key=pygame.K_f, mod=0)
                )
                game.handle_events()
                self.assertTrue(game.fullscreen)

    def test_off_deck_f_key_toggles_fullscreen(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_desktop_game(tmpdir)
            game.state = "options"
            game.fullscreen = True
            pygame.event.clear()
            pygame.event.post(
                pygame.event.Event(pygame.KEYDOWN, key=pygame.K_f, mod=0)
            )
            game.handle_events()
            self.assertFalse(game.fullscreen)

    def test_on_deck_activate_fullscreen_row_is_noop(self) -> None:
        with patch_deck_on():
            with tempfile.TemporaryDirectory() as tmpdir:
                game = make_desktop_game(tmpdir)
                game.fullscreen = True
                # OPTIONS_ROW_FULLSCREEN is -1 on Deck; activating it should
                # not toggle fullscreen.
                game._activate_options_row(game.OPTIONS_ROW_FULLSCREEN, True)
                self.assertTrue(game.fullscreen)

if __name__ == "__main__":
    unittest.main()