from __future__ import annotations

import hashlib
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

from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game
from arch_rogue.input import REMAPPABLE_GAMEPAD_COMMANDS
from arch_rogue.menus.controls import KEYBOARD_ROWS
from arch_rogue.rendering.hud import HUD_ACTION_SKILL_ASSETS
from arch_rogue.ui_assets import UiAssetLibrary


class UiAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode((64, 64), pygame.HIDDEN)

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def make_game(
        self, tmpdir: str, size: tuple[int, int] = (960, 540)
    ) -> Game:
        game = Game(
            screen_size=size,
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.set_legacy_graphics(False)
        game.ui_scale = 1
        game.rebuild_fonts()
        return game

    @staticmethod
    def surface_signature(surface: pygame.Surface) -> str:
        digest = hashlib.blake2s(
            pygame.image.tobytes(surface, "RGBA"), digest_size=16
        ).hexdigest()
        return f"{surface.get_width()}x{surface.get_height()}:{digest}"

    def test_manifest_assets_and_package_data(self) -> None:
        library = UiAssetLibrary()
        self.assertTrue(library.available, library.load_error)
        self.assertEqual(library.manifest["format_version"], 1)
        action_icon_keys = {
            key
            for class_assets in HUD_ACTION_SKILL_ASSETS.values()
            for key in class_assets
        } | {
            "hud.action.health_potion",
            "hud.action.mana_potion",
            "hud.action.ranger.spirit_beast_angry",
        }
        self.assertEqual(len(action_icon_keys), 23)
        expected = {
            "menu.background.title",
            "menu.background",
            "cutscene.background",
            "menu.panel",
            "menu.panel.compact",
            "menu.panel.inset",
            "menu.row",
            "hud.panel",
            "hud.dock",
            "hud.action_slot",
            "hud.bar",
            *action_icon_keys,
        }
        self.assertEqual(set(library.manifest["assets"]), expected)

        sizes = {
            "menu.background.title": (960, 540),
            "menu.background": (640, 480),
            "cutscene.background": (960, 540),
            "menu.panel": (720, 360),
            "menu.panel.compact": (480, 360),
            "menu.panel.inset": (320, 160),
            "menu.row": (520, 44),
            "hud.panel": (740, 72),
            "hud.dock": (340, 62),
            "hud.action_slot": (54, 54),
            "hud.bar": (240, 14),
        }
        for key, size in sizes.items():
            with self.subTest(key=key):
                source = library.source(key)
                self.assertIsNotNone(source)
                assert source is not None
                self.assertGreater(source.get_bounding_rect(min_alpha=1).width, 0)
                rendered = library.render(key, size)
                self.assertIsNotNone(rendered)
                assert rendered is not None
                self.assertEqual(rendered.get_size(), size)
                self.assertGreater(rendered.get_bounding_rect(min_alpha=1).width, 0)
                self.assertIs(library.render(key, size), rendered)

        for key in action_icon_keys:
            with self.subTest(action_icon=key):
                source = library.source(key)
                self.assertIsNotNone(source)
                assert source is not None
                self.assertEqual(source.get_size(), (32, 32))
                self.assertGreater(source.get_bounding_rect(min_alpha=1).width, 0)
                self.assertTrue(
                    any(
                        source.get_at((x, y)).a == 0
                        for y in range(source.get_height())
                        for x in range(source.get_width())
                    )
                )
                rendered = library.render(key, (48, 48))
                self.assertIsNotNone(rendered)
                assert rendered is not None
                self.assertEqual(rendered.get_size(), (48, 48))

        bar_source = library.source("hud.bar")
        self.assertIsNotNone(bar_source)
        assert bar_source is not None
        self.assertEqual(bar_source.get_size(), (474, 66))
        self.assertEqual(
            library.content_rect("hud.bar", pygame.Rect(0, 0, 260, 20)),
            pygame.Rect(8, 4, 244, 12),
        )

        # The 22-icon audit intentionally exceeds the source LRU. Touch the row
        # again before checking that clear_derived_caches retains decoded sources.
        self.assertIsNotNone(library.source("menu.row"))
        builds = library.render_build_count
        decodes = library.source_decode_count
        library.clear_derived_caches()
        rebuilt = library.render("menu.row", sizes["menu.row"])
        self.assertIsNotNone(rebuilt)
        self.assertEqual(library.render_build_count, builds + 1)
        self.assertEqual(library.source_decode_count, decodes)

        pyproject = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(
            encoding="utf-8"
        )
        self.assertIn('"assets/sprites/menus/*.png"', pyproject)
        self.assertIn('"assets/sprites/hud/*.png"', pyproject)

    def test_invalid_manifest_and_missing_resource_are_contained(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "ui_manifest.json").write_text(
                json.dumps(
                    {
                        "format_version": 1,
                        "assets": {
                            "escape": {
                                "path": "../escape.png",
                                "render": "scale",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            invalid = UiAssetLibrary(root)
            self.assertFalse(invalid.available)
            self.assertTrue(invalid.load_error)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            valid_surface = pygame.Surface((16, 16), pygame.SRCALPHA)
            valid_surface.fill((22, 18, 30, 255))
            pygame.draw.rect(valid_surface, (210, 168, 92), valid_surface.get_rect(), 2)
            pygame.image.save(valid_surface, root / "valid.png")
            (root / "ui_manifest.json").write_text(
                json.dumps(
                    {
                        "format_version": 1,
                        "assets": {
                            "valid": {"path": "valid.png", "render": "scale"},
                            "missing": {"path": "missing.png", "render": "scale"},
                            "slice": {
                                "path": "valid.png",
                                "render": "nine_slice",
                                "insets": [4, 4, 4, 4],
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            library = UiAssetLibrary(root)
            self.assertTrue(library.available, library.load_error)
            self.assertIsNotNone(library.render("valid", (40, 24)))
            self.assertIsNotNone(library.render("slice", (9, 7)))
            before_missing = library.source_decode_count
            self.assertIsNone(library.render("missing", (40, 24)))
            self.assertEqual(library.source_decode_count, before_missing + 1)
            self.assertIsNone(library.render("missing", (40, 24)))
            self.assertEqual(library.source_decode_count, before_missing + 1)
            self.assertIsNotNone(library.render("valid", (40, 24)))

    def test_modern_and_legacy_menu_hud_paths_and_warm_caches(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.assertTrue(game.asset_ui_active())

            game.state = "title"
            game.screen.fill((0, 0, 0))
            game.draw_title_menu()
            modern_title = self.surface_signature(game.screen)
            menu_keys = {key[0] for key in game.ui_assets._render_cache}
            self.assertTrue(
                {"menu.background.title", "menu.panel", "menu.row"}.issubset(
                    menu_keys
                )
            )
            warm_builds = game.ui_assets.render_build_count
            warm_decodes = game.ui_assets.source_decode_count
            game.draw_title_menu()
            self.assertEqual(game.ui_assets.render_build_count, warm_builds)
            self.assertEqual(game.ui_assets.source_decode_count, warm_decodes)

            game.set_legacy_graphics(True)
            self.assertFalse(game.asset_ui_active())
            legacy_builds = game.ui_assets.render_build_count
            game.screen.fill((0, 0, 0))
            game.draw_title_menu()
            self.assertEqual(game.ui_assets.render_build_count, legacy_builds)
            self.assertNotEqual(self.surface_signature(game.screen), modern_title)
            self.assertIsNone(game.menus._title_logo(24))

            game.set_legacy_graphics(False)
            game.rng.seed(4100)
            game.restart(ARCHETYPES[0])
            if game.story_intro_pending:
                self.assertTrue(game.choose_story_relic_path(0))
            game.active_cutscene = None
            game.screen.fill((10, 10, 14))
            game.draw_ui()
            hud_keys = {key[0] for key in game.ui_assets._render_cache}
            self.assertTrue(
                {
                    "hud.panel",
                    "hud.dock",
                    "hud.action_slot",
                    "hud.bar",
                    *HUD_ACTION_SKILL_ASSETS["Warden"],
                    "hud.action.health_potion",
                    "hud.action.mana_potion",
                }.issubset(hud_keys)
            )
            warm_builds = game.ui_assets.render_build_count
            warm_decodes = game.ui_assets.source_decode_count
            game.screen.fill((10, 10, 14))
            game.draw_ui()
            self.assertEqual(game.ui_assets.render_build_count, warm_builds)
            self.assertEqual(game.ui_assets.source_decode_count, warm_decodes)
            self.assertLessEqual(len(game.ui_assets._render_cache), 256)
            self.assertLessEqual(len(game.ui_assets._source_cache), 16)

    def test_compact_controls_keep_rows_visible_and_contained(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, (640, 480))
            game.ui_scale = 4
            game.rebuild_fonts()
            game.state = "controls"
            game.draw_controls_menu()
            keyboard = game._controls_keyboard_row_rects
            gamepad = game._controls_gamepad_row_rects
            self.assertEqual(len(keyboard), len(KEYBOARD_ROWS))
            self.assertEqual(len(gamepad), len(REMAPPABLE_GAMEPAD_COMMANDS))
            screen_rect = game.screen.get_rect()
            for group in (keyboard, gamepad):
                self.assertTrue(all(screen_rect.contains(rect) for rect in group))
                self.assertTrue(
                    all(first.bottom <= second.y for first, second in zip(group, group[1:]))
                )


if __name__ == "__main__":
    unittest.main()
