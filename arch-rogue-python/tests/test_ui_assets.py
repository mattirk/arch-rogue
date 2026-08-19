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

from arch_rogue.content import ARCHETYPES, DISCIPLINES
from arch_rogue.game import Game
from arch_rogue.icon import available_sizes, icon_sizes, load_icon
from arch_rogue.input import FIXED_GAMEPAD_BINDINGS, REMAPPABLE_GAMEPAD_COMMANDS
from arch_rogue.menus.controls import KEYBOARD_ROWS
from arch_rogue.rendering.hud import HUD_ACTION_SKILL_ASSETS
from arch_rogue.sprites import UiAssetLibrary


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
        code_glyph_keys = {
            f"menu.glyph.code.{char}"
            for char in "abcdefghijklmnopqrstuvwxyz0123456789"
        }
        join_request_glyph_keys = {
            "menu.glyph.action.accept",
            "menu.glyph.action.kick",
        }
        join_request_panel_keys = {
            "menu.panel.action.accept",
            "menu.panel.action.kick",
        }
        mini_game_socket_keys = {
            "minigame.socket.story",
            "minigame.socket.garden",
            "minigame.socket.soul",
        }
        sigil_keys = {
            f"menu.glyph.sigil.{name}"
            for name in (
                "serpent", "hammer", "skull", "star", "cross", "flame",
                "ember", "key", "map", "shield", "sword", "coin",
                "rune_kenaz", "rune_othala", "rune_bind", "rune_ingwaz",
                "claw", "rune_perth", "rune_branch", "sun", "moon",
                "sunburst", "rune_berkano", "dragon", "phoenix",
                "ouroboros", "clock", "infinity",
            )
        }
        discipline_panel_keys = {
            f"menu.panel.discipline.{archetype.name.casefold()}"
            for archetype in ARCHETYPES
        }
        discipline_glyph_keys = {
            f"menu.glyph.discipline.{node.key}" for node in DISCIPLINES
        }
        self.assertEqual(len(discipline_panel_keys), 5)
        self.assertEqual(len(discipline_glyph_keys), 100)
        # 4.11.0: the loading screen's spinning logo diamond, 16 frames.
        logo_diamond_keys = {f"menu.logo.diamond.{index}" for index in range(16)}
        expected = {
            "menu.background.title",
            "menu.logo.title",
            *logo_diamond_keys,
            "menu.background",
            "cutscene.background",
            "cutscene.choice.panel",
            "cutscene.choice.icon.aid",
            "cutscene.choice.icon.bargain",
            "cutscene.choice.icon.defy",
            "cutscene.choice.icon.soul_preserve",
            "cutscene.choice.icon.soul_release",
            "cutscene.choice.icon.soul_refuse",
            "cutscene.choice.icon.page",
            "stage.backdrop.omen",
            "stage.backdrop.dialogue",
            "stage.backdrop.lossless_soul",
            "stage.curtain.open",
            "menu.panel",
            "menu.panel.compact",
            "menu.panel.inset",
            "menu.row",
            "menu.row.selected",
            "menu.row.two_descend",
            "hud.panel",
            "hud.dock",
            "hud.action_slot",
            "hud.bar",
            "hud.mobile.joystick_base",
            "hud.mobile.joystick_knob",
            "hud.mobile.status_bar_frame",
            "hud.mobile.info_panel",
            "hud.mobile.back",
            "menu.panel.mp_code",
            "menu.panel.mp_seal",
            "menu.panel.mp_carousel",
            "menu.panel.mp_plain",
            *action_icon_keys,
            *code_glyph_keys,
            *join_request_glyph_keys,
            *join_request_panel_keys,
            *mini_game_socket_keys,
            *sigil_keys,
            *discipline_panel_keys,
            *discipline_glyph_keys,
        }
        self.assertEqual(set(library.manifest["assets"]), expected)
        for row_key in (
            "menu.row",
            "menu.row.selected",
            "menu.row.two_descend",
        ):
            self.assertEqual(
                library.manifest["assets"][row_key]["shrink_insets_below_height"],
                88,
            )

        sizes = {
            "menu.background.title": (960, 540),
            "menu.logo.title": (400, 76),
            "menu.background": (640, 480),
            "cutscene.background": (960, 540),
            "cutscene.choice.panel": (640, 52),
            "cutscene.choice.icon.aid": (48, 48),
            "cutscene.choice.icon.bargain": (48, 48),
            "cutscene.choice.icon.defy": (48, 48),
            "stage.backdrop.omen": (688, 384),
            "stage.backdrop.dialogue": (591, 293),
            "stage.curtain.open": (688, 192),
            "menu.panel": (720, 360),
            "menu.panel.compact": (480, 360),
            "menu.panel.inset": (320, 160),
            "minigame.socket.story": (142, 142),
            "minigame.socket.garden": (142, 142),
            "minigame.socket.soul": (142, 142),
            "menu.row": (520, 44),
            "menu.row.two_descend": (520, 44),
            "menu.panel.action.accept": (240, 60),
            "menu.panel.action.kick": (240, 60),
            "hud.panel": (740, 72),
            "hud.dock": (340, 62),
            "hud.action_slot": (54, 54),
            "hud.bar": (240, 14),
            "hud.mobile.joystick_base": (184, 184),
            "hud.mobile.joystick_knob": (112, 112),
            "hud.mobile.status_bar_frame": (60, 160),
            "hud.mobile.info_panel": (240, 108),
            "hud.mobile.back": (52, 52),
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

        title_logo = library.source("menu.logo.title")
        self.assertIsNotNone(title_logo)
        assert title_logo is not None
        self.assertEqual(title_logo.get_size(), (640, 122))
        self.assertEqual(
            title_logo.get_bounding_rect(min_alpha=1),
            pygame.Rect(62, 24, 516, 74),
        )
        self.assertGreater(title_logo.get_at((320, 61)).a, 0)

        for key in action_icon_keys | join_request_glyph_keys:
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

        for key in mini_game_socket_keys:
            with self.subTest(mini_game_socket=key):
                source = library.source(key)
                self.assertIsNotNone(source)
                assert source is not None
                self.assertEqual(source.get_size(), (256, 256))
                self.assertEqual(source.get_at((0, 0)).a, 0)
                self.assertEqual(source.get_at(source.get_rect().center).a, 0)
                self.assertGreater(source.get_bounding_rect(min_alpha=1).width, 200)
                self.assertEqual(
                    library.content_rect(key, pygame.Rect(0, 0, 142, 142)),
                    pygame.Rect(27, 27, 88, 88),
                )

        discipline_panel_metadata = {
            "warden": (
                (192, 0, 80, 0),
                (188, 34, 84, 34),
                "0006d8d5ebc4161ce5f2174f8eea6e70"
                "f8ce9a12400368a2054f2e17ab4eee04",
            ),
            "rogue": (
                (192, 0, 80, 0),
                (192, 38, 84, 38),
                "1a4a4e04d8a2f7f43c58af53189ce048"
                "250ee4c185508b824ffc76ec243a5d61",
            ),
            "arcanist": (
                (192, 0, 76, 0),
                (208, 34, 76, 34),
                "4a8a843ae95e8337db05b6e5991484beb"
                "c135c3b69fd471062e1aef601cd51f3",
            ),
            "acolyte": (
                (192, 0, 112, 0),
                (204, 44, 72, 42),
                "7fb20c433c904779a2534842171dabe4d"
                "7fcd4c4a63b6ef2aed17e535b24a62d",
            ),
            "ranger": (
                (192, 0, 80, 0),
                (192, 36, 80, 36),
                "2082349890f0d5f41b7c10a00867fe010"
                "4335898c8cadbe01ead1cc84590370e",
            ),
        }
        discipline_panel_sources: set[bytes] = set()
        for key in discipline_panel_keys:
            with self.subTest(discipline_panel=key):
                source = library.source(key)
                self.assertIsNotNone(source)
                assert source is not None
                self.assertEqual(source.get_size(), (600, 192))
                self.assertGreater(
                    source.get_bounding_rect(min_alpha=1).width,
                    0,
                )
                source_bytes = pygame.image.tobytes(source, "RGBA")
                discipline_panel_sources.add(source_bytes)
                entry = library.manifest["assets"][key]
                archetype_key = key.rsplit(".", 1)[-1]
                expected_insets, expected_content, expected_digest = (
                    discipline_panel_metadata[archetype_key]
                )
                self.assertEqual(
                    entry["path"],
                    f"menus/discipline_panel_{archetype_key}.png",
                )
                self.assertEqual(entry["render"], "nine_slice")
                self.assertTrue(entry["scale_insets_with_height"])
                self.assertEqual(tuple(entry["insets"]), expected_insets)
                self.assertEqual(
                    tuple(entry["content_insets"]),
                    expected_content,
                )
                self.assertEqual(
                    hashlib.sha256(source_bytes).hexdigest(),
                    expected_digest,
                )
                for target_size in ((180, 52), (110, 24)):
                    target = pygame.Rect((0, 0), target_size)
                    rendered = library.render(key, target_size)
                    self.assertIsNotNone(rendered)
                    assert rendered is not None
                    self.assertEqual(rendered.get_size(), target_size)
                    self.assertGreater(
                        rendered.get_bounding_rect(min_alpha=1).width,
                        0,
                    )
                    expected_endcap = pygame.transform.scale(
                        source.subsurface((0, 0, 192, 192)),
                        (target.height, target.height),
                    )
                    rendered_endcap = rendered.subsurface(
                        (0, 0, target.height, target.height)
                    )
                    self.assertEqual(
                        pygame.image.tobytes(rendered_endcap, "RGBA"),
                        pygame.image.tobytes(expected_endcap, "RGBA"),
                        "the square socket cap must scale equally on both axes",
                    )
                    content = library.content_rect(key, target)
                    self.assertIsNotNone(content)
                    assert content is not None
                    self.assertTrue(target.contains(content))
                    self.assertGreater(content.width, 0)
                    self.assertGreater(content.height, 0)
                    self.assertLess(content.width, target.width)
                    self.assertLess(content.height, target.height)
        self.assertEqual(len(discipline_panel_sources), len(discipline_panel_keys))

        discipline_glyph_sources: set[bytes] = set()
        for key in discipline_glyph_keys:
            with self.subTest(discipline_glyph=key):
                source = library.source(key)
                self.assertIsNotNone(source)
                assert source is not None
                self.assertEqual(source.get_size(), (32, 32))
                self.assertGreater(
                    source.get_bounding_rect(min_alpha=1).width,
                    0,
                )
                alpha = pygame.image.tobytes(source, "RGBA")[3::4]
                self.assertEqual(min(alpha), 0)
                self.assertEqual(max(alpha), 255)
                self.assertLessEqual(set(alpha), {0, 255})
                node_key = key.removeprefix("menu.glyph.discipline.")
                self.assertEqual(
                    library.manifest["assets"][key]["path"],
                    f"menus/glyphs/discipline_{node_key}.png",
                )
                discipline_glyph_sources.add(
                    pygame.image.tobytes(source, "RGBA")
                )
                for target_size in ((32, 32), (16, 16)):
                    rendered = library.render(key, target_size)
                    self.assertIsNotNone(rendered)
                    assert rendered is not None
                    self.assertEqual(rendered.get_size(), target_size)
                    self.assertGreater(
                        rendered.get_bounding_rect(min_alpha=1).width,
                        0,
                    )
        self.assertEqual(len(discipline_glyph_sources), len(discipline_glyph_keys))

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
        self.assertIn('"assets/sprites/menus/glyphs/*.png"', pyproject)
        self.assertIn('"assets/sprites/hud/*.png"', pyproject)

    def test_generated_brand_icons_preserve_the_diamond_silhouette(self) -> None:
        self.assertEqual(available_sizes(), list(icon_sizes()))
        for size in icon_sizes():
            with self.subTest(size=size):
                icon = load_icon(size)
                self.assertIsNotNone(icon)
                assert icon is not None
                self.assertEqual(icon.get_size(), (size, size))
                bounds = icon.get_bounding_rect(min_alpha=1)
                self.assertGreaterEqual(bounds.width, size * 4 // 5)
                self.assertGreaterEqual(bounds.height, size * 4 // 5)
                self.assertEqual(icon.get_at((0, 0)).a, 0)
                self.assertGreater(icon.get_at((size // 2, size // 2)).a, 0)

        master = load_icon(128)
        self.assertIsNotNone(master)
        assert master is not None
        former_halo_points = (
            (113, 55),
            (14, 55),
            (55, 14),
            (55, 113),
            (113, 73),
            (14, 73),
            (73, 14),
            (73, 113),
        )
        self.assertTrue(all(master.get_at(point).a == 0 for point in former_halo_points))

    def test_cutscene_background_is_full_bleed_and_fully_opaque(self) -> None:
        library = UiAssetLibrary()
        source = library.source("cutscene.background")
        self.assertIsNotNone(source)
        assert source is not None
        self.assertEqual(source.get_size(), (688, 384))

        for label, surface in (
            ("source", source),
            ("widescreen", library.render("cutscene.background", (960, 540))),
            ("compact", library.render("cutscene.background", (640, 480))),
        ):
            with self.subTest(label=label):
                self.assertIsNotNone(surface)
                assert surface is not None
                rgba = pygame.image.tobytes(surface, "RGBA")
                alpha = rgba[3::4]
                self.assertTrue(alpha)
                self.assertEqual(min(alpha), 255)
                self.assertEqual(max(alpha), 255)

    def test_menu_rows_preserve_reference_slices_and_adapt_compact_insets(
        self,
    ) -> None:
        library = UiAssetLibrary()
        for key in ("menu.row", "menu.row.selected"):
            with self.subTest(key=key):
                source = library.source(key)
                self.assertIsNotNone(source)
                assert source is not None

                # The accepted 2x mobile and 3x desktop row heights retain the
                # original 105x10 corner slice exactly.
                source_corner = source.subsurface((0, 0, 105, 10))
                for size in ((1648, 88), (2496, 132)):
                    rendered = library.render(key, size)
                    self.assertIsNotNone(rendered)
                    assert rendered is not None
                    self.assertEqual(
                        pygame.image.tobytes(
                            rendered.subsurface((0, 0, 105, 10)), "RGBA"
                        ),
                        pygame.image.tobytes(source_corner, "RGBA"),
                    )

                # At 1x, endcaps and border bands contract together instead of
                # consuming a quarter of the row and crushing its text area.
                compact = library.render(key, (800, 44))
                self.assertIsNotNone(compact)
                assert compact is not None
                expected_corner = pygame.transform.scale(source_corner, (52, 5))
                self.assertEqual(
                    pygame.image.tobytes(
                        compact.subsurface((0, 0, 52, 5)), "RGBA"
                    ),
                    pygame.image.tobytes(expected_corner, "RGBA"),
                )
                expected_compact = (
                    pygame.Rect(52, 3, 673, 38)
                    if key == "menu.row.selected"
                    else pygame.Rect(52, 3, 696, 38)
                )
                expected_reference = (
                    pygame.Rect(92, 6, 1419, 76)
                    if key == "menu.row.selected"
                    else pygame.Rect(92, 6, 1464, 76)
                )
                self.assertEqual(
                    library.content_rect(key, pygame.Rect(0, 0, 800, 44)),
                    expected_compact,
                )
                self.assertEqual(
                    library.content_rect(key, pygame.Rect(0, 0, 1648, 88)),
                    expected_reference,
                )

        selected_entry = library.manifest["assets"]["menu.row.selected"]
        self.assertEqual(selected_entry["insets"], [105, 10, 150, 10])
        self.assertEqual(selected_entry["content_insets"], [92, 6, 137, 6])
        selected = library.source("menu.row.selected")
        default = library.source("menu.row")
        self.assertIsNotNone(selected)
        self.assertIsNotNone(default)
        assert selected is not None and default is not None
        self.assertEqual(
            pygame.image.tobytes(selected.subsurface((0, 0, 488, 52)), "RGBA"),
            pygame.image.tobytes(default.subsurface((0, 0, 488, 52)), "RGBA"),
        )
        self.assertNotEqual(
            pygame.image.tobytes(selected.subsurface((488, 0, 135, 52)), "RGBA"),
            pygame.image.tobytes(default.subsurface((488, 0, 135, 52)), "RGBA"),
        )

        special_key = "menu.row.two_descend"
        special_entry = library.manifest["assets"][special_key]
        self.assertEqual(special_entry["insets"], [105, 10, 196, 10])
        self.assertEqual(special_entry["content_insets"], [92, 6, 183, 6])
        special = library.source(special_key)
        default = library.source("menu.row")
        self.assertIsNotNone(special)
        self.assertIsNotNone(default)
        assert special is not None and default is not None
        self.assertEqual(special.get_size(), default.get_size())
        self.assertEqual(
            pygame.image.tobytes(special.subsurface((0, 0, 441, 52)), "RGBA"),
            pygame.image.tobytes(default.subsurface((0, 0, 441, 52)), "RGBA"),
        )
        self.assertNotEqual(
            pygame.image.tobytes(special.subsurface((441, 0, 182, 52)), "RGBA"),
            pygame.image.tobytes(default.subsurface((441, 0, 182, 52)), "RGBA"),
        )
        self.assertEqual(
            library.content_rect(special_key, pygame.Rect(0, 0, 800, 44)),
            pygame.Rect(52, 3, 650, 38),
        )
        self.assertEqual(
            library.content_rect(special_key, pygame.Rect(0, 0, 1648, 88)),
            pygame.Rect(92, 6, 1373, 76),
        )

    def test_story_choice_plate_and_semantic_icons_are_complete(self) -> None:
        library = UiAssetLibrary()
        panel = library.source("cutscene.choice.panel")
        self.assertIsNotNone(panel)
        assert panel is not None
        self.assertEqual(panel.get_size(), (640, 44))
        self.assertEqual(panel.get_bounding_rect(min_alpha=1), panel.get_rect())
        rendered_panel = library.render("cutscene.choice.panel", (640, 52))
        self.assertIsNotNone(rendered_panel)
        assert rendered_panel is not None
        self.assertEqual(rendered_panel.get_size(), (640, 52))
        self.assertTrue(
            library.manifest["assets"]["cutscene.choice.panel"][
                "scale_insets_with_height"
            ]
        )
        self.assertEqual(
            library.content_rect(
                "cutscene.choice.panel",
                pygame.Rect(0, 0, 640, 44),
            ),
            pygame.Rect(80, 6, 550, 32),
        )
        doubled_panel = library.render("cutscene.choice.panel", (1280, 88))
        self.assertIsNotNone(doubled_panel)
        assert doubled_panel is not None
        self.assertEqual(doubled_panel.get_size(), (1280, 88))
        expected_left_cap = pygame.transform.scale(
            panel.subsurface((0, 0, 77, 44)),
            (154, 88),
        )
        self.assertEqual(
            pygame.image.tobytes(
                doubled_panel.subsurface((0, 0, 154, 88)),
                "RGBA",
            ),
            pygame.image.tobytes(expected_left_cap, "RGBA"),
        )
        self.assertEqual(
            library.content_rect(
                "cutscene.choice.panel",
                pygame.Rect(0, 0, 1280, 88),
            ),
            pygame.Rect(160, 12, 1100, 64),
        )

        icon_bytes = set()
        alpha_masks = set()
        outer_frames = set()
        for choice_key in ("aid", "bargain", "defy"):
            with self.subTest(choice_key=choice_key):
                key = f"cutscene.choice.icon.{choice_key}"
                icon = library.source(key)
                self.assertIsNotNone(icon)
                assert icon is not None
                self.assertEqual(icon.get_size(), (32, 32))
                bounds = icon.get_bounding_rect(min_alpha=1)
                self.assertEqual(bounds, pygame.Rect(3, 3, 26, 26))
                self.assertTrue(
                    any(
                        icon.get_at((x, y)).a == 0
                        for y in range(icon.get_height())
                        for x in range(icon.get_width())
                    )
                )
                rendered = library.render(key, (40, 40))
                self.assertIsNotNone(rendered)
                assert rendered is not None
                self.assertEqual(rendered.get_size(), (40, 40))
                doubled_icon = library.render(key, (64, 64))
                self.assertIsNotNone(doubled_icon)
                assert doubled_icon is not None
                self.assertEqual(
                    doubled_icon.get_bounding_rect(min_alpha=1),
                    pygame.Rect(6, 6, 52, 52),
                )
                icon_bytes.add(pygame.image.tobytes(icon, "RGBA"))
                alpha_masks.add(
                    bytes(
                        icon.get_at((x, y)).a
                        for y in range(icon.get_height())
                        for x in range(icon.get_width())
                    )
                )
                outer_frame = bytearray()
                for y in range(icon.get_height()):
                    for x in range(icon.get_width()):
                        if (2 * x - 31) ** 2 + (2 * y - 31) ** 2 > 19**2:
                            outer_frame.extend(icon.get_at((x, y)))
                outer_frames.add(bytes(outer_frame))
        self.assertEqual(len(icon_bytes), 3)
        self.assertEqual(len(alpha_masks), 1)
        self.assertEqual(len(outer_frames), 1)

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
                {
                    "menu.background.title",
                    "menu.panel",
                    "menu.row",
                    "menu.row.two_descend",
                }.issubset(menu_keys)
            )
            # 5.0: the title logo is composed from source pixels with its
            # relic diamond spinning, cached per (frame, size) on the Game
            # instead of passing through ui_assets.render.
            self.assertTrue(getattr(game, "_animated_logo_cache", None))
            self.assertTrue(
                getattr(game, "_menu_header_title_asset_used", False)
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
            self.assertFalse(
                getattr(game, "_menu_header_title_asset_used", False)
            )
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

    def test_menu_footer_clears_the_backdrop_frame(self) -> None:
        # The authored menu backdrops paint an ornamental frame along the
        # screen edges (content_insets in the manifest). The footer hint line
        # must sit between the panel and the frame's inner edge — on the
        # Deck's 16:10 panel it used to land straight on the title frame's
        # gold rail.
        for state in ("title", "options"):
            with tempfile.TemporaryDirectory() as tmpdir:
                game = self.make_game(tmpdir, (1280, 800))
                game.state = state
                game.draw()
                safe_bottom = game.menus._menu_backdrop_safe_bottom
                self.assertIsNotNone(safe_bottom)
                # The frame insets are live: the safe area ends above the
                # screen bottom, and the footer keeps entirely inside it,
                # below the menu panel.
                self.assertLess(safe_bottom, game.screen.get_height())
                footer = game._menu_footer_rect
                panel = game._last_menu_panel_rect
                self.assertLessEqual(footer.bottom, safe_bottom)
                self.assertGreaterEqual(footer.y, panel.bottom)

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
            # Remappable rows plus the fixed D-pad rows added in 4.9.22. The
            # containment checks below are the real point: four extra rows in a
            # 640x480 panel at ui_scale 4 is exactly where a compact layout
            # would start pushing rows off-screen.
            self.assertEqual(
                len(gamepad),
                len(REMAPPABLE_GAMEPAD_COMMANDS) + len(FIXED_GAMEPAD_BINDINGS),
            )
            screen_rect = game.screen.get_rect()
            for group in (keyboard, gamepad):
                self.assertTrue(all(screen_rect.contains(rect) for rect in group))
                self.assertTrue(
                    all(first.bottom <= second.y for first, second in zip(group, group[1:]))
                )

            row_sizes = {
                (cache_key[-2], cache_key[-1])
                for cache_key in game.ui_assets._render_cache
                if cache_key[0] == "menu.row"
            }
            self.assertIn(keyboard[0].size, row_sizes)
            self.assertIn(gamepad[0].size, row_sizes)

            # A long binding such as "Unbound" selects center-plate columns
            # for the whole gamepad list, so short values do not jump back into
            # the endcaps on neighboring rows.
            key_rects = tuple(game._menu_row_key_rects)
            value_rects = tuple(game._menu_row_value_rects)
            self.assertEqual(len(key_rects), len(gamepad))
            self.assertEqual(len(value_rects), len(gamepad))
            self.assertEqual(len({rect.x for rect in key_rects}), 1)
            self.assertEqual(len({rect.right for rect in value_rects}), 1)
            self.assertTrue(
                all(row.contains(key_rect) for row, key_rect in zip(gamepad, key_rects))
            )
            self.assertTrue(
                all(
                    row.contains(value_rect)
                    for row, value_rect in zip(gamepad, value_rects)
                )
            )


if __name__ == "__main__":
    unittest.main()
