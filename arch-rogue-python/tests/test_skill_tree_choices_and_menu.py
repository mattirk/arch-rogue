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

from arch_rogue.content import (
    ARCHETYPES,
    DISCIPLINES,
    DISCIPLINE_UPGRADES,
    discipline_paths_for_archetype,
    discipline_by_key,
    disciplines_for_archetype,
    max_discipline_degree,
)
from arch_rogue.game import Game


class SkillTree32Tests(unittest.TestCase):


    def make_game(
        self, tmpdir: str, archetype_index: int = 0, seed: int = 3201
    ) -> Game:
        game = Game(
            screen_size=(960, 600),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.rng.seed(seed)
        game.restart(ARCHETYPES[archetype_index])
        if game.story_intro_pending:
            self.assertTrue(game.choose_story_relic_path(0))
        game.active_cutscene = None
        return game

    # --- Content table shape -------------------------------------------------

    def test_discipline_content_table_shape(self) -> None:
        # Every archetype has a 5-degree, >=2-path discipline tree with sane prerequisites.
        for archetype in ARCHETYPES:
            nodes = disciplines_for_archetype(archetype.name)
            self.assertGreaterEqual(
                len(nodes), 10, f"{archetype.name} should have >=10 nodes"
            )
            self.assertEqual(
                {node.degree for node in nodes},
                set(range(1, 6)),
                f"{archetype.name} must cover degrees 1..5",
            )
            self.assertEqual(max_discipline_degree(archetype.name), 5)
            paths = discipline_paths_for_archetype(archetype.name)
            self.assertGreaterEqual(
                len(paths), 2, f"{archetype.name} needs >=2 paths"
            )
            # Degree 1 nodes are open (no prerequisites); higher degrees require
            # an earlier-degree prerequisite of the same path.
            for node in nodes:
                if node.degree == 1:
                    self.assertEqual(
                        node.prerequisites,
                        (),
                        f"{node.key} degree-1 nodes must be open",
                    )
                else:
                    self.assertTrue(
                        node.prerequisites,
                        f"{node.key} degree-{node.degree} must require something",
                    )
                    for prereq_key in node.prerequisites:
                        prereq = discipline_by_key(prereq_key)
                        self.assertIsNotNone(prereq)
                        assert prereq is not None
                        self.assertEqual(prereq.archetype, archetype.name)
                        self.assertLess(prereq.degree, node.degree)

        # DISCIPLINE_UPGRADES is derived 1:1 from DISCIPLINES and every key resolves.
        node_keys = {node.key for node in DISCIPLINES}
        upgrade_keys = {upgrade.key for upgrade in DISCIPLINE_UPGRADES}
        self.assertEqual(node_keys, upgrade_keys)
        for node in DISCIPLINES:
            self.assertIs(discipline_by_key(node.key), node)

    # --- Combat grant logic --------------------------------------------------

    def test_skill_choice_prerequisites_and_rejection_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0)  # Warden
            try:
                # Milestone 3.3: choosing nodes now spends memory tokens, so
                # bank enough tokens to exercise the discipline tree.
                game.player.memory_tokens = 10
                # Initially only degree-1 nodes are available.
                available = game.available_disciplines()
                self.assertTrue(available)
                self.assertTrue(all(node.degree == 1 for node in available))

                # Rogue node cannot be chosen by a Warden.
                self.assertFalse(game.choose_discipline("rogue_precision"))
                self.assertNotIn("rogue_precision", game.player.skill_upgrades)

                # Acquire a degree-1 Bulwark node; its degree-2 child unlocks.
                self.assertTrue(game.choose_discipline("warden_bulwark"))
                # Duplicate acquisition is rejected.
                self.assertFalse(game.choose_discipline("warden_bulwark"))

                available = game.available_disciplines()
                keys = {node.key for node in available}
                self.assertIn("warden_aegis", keys)
                # The other degree-1 node is still available.
                self.assertIn("warden_riposte", keys)
                # Degree-2 Riposte child stays locked (its parent unchosen).
                self.assertNotIn("warden_counter", keys)

                # Trying to skip ahead fails.
                self.assertFalse(game.choose_discipline("warden_bulwark_ward"))
                self.assertFalse(game.choose_discipline("warden_iron_vow"))
            finally:
                pass

    # --- Save compatibility ---------------------------------------------------

    def test_save_restore_preserves_progress_and_drops_unknown_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=1, seed=3241)  # Rogue
            try:
                game.player.memory_tokens = 2
                game.choose_discipline("rogue_precision")
                game.choose_discipline("rogue_venom")
                self.assertEqual(
                    game.player.skill_upgrades,
                    ["rogue_precision", "rogue_venom"],
                )
                # Memory tokens are spent on save.
                self.assertEqual(game.player.memory_tokens, 0)
                game.save_run()

                game2 = Game(
                    screen_size=(960, 600),
                    headless=True,
                    save_path=Path(tmpdir) / "run.json",
                )
                game2.options_path = Path(tmpdir) / "options.json"
                game2.rng.seed(9999)
                self.assertTrue(game2.load_run())
                self.assertEqual(
                    game2.player.skill_upgrades,
                    ["rogue_precision", "rogue_venom"],
                )
                # Discipline tree state is consistent after restore.
                self.assertEqual(
                    game2.discipline_state(discipline_by_key("rogue_precision")),
                    "chosen",
                )
                self.assertEqual(
                    game2.discipline_state(discipline_by_key("rogue_executioner")),
                    "available",
                )

                # Inject an obsolete/unknown key into the restored run, re-save,
                # and reload to confirm migration drops it without breaking play.
                game2.player.skill_upgrades.append("obsolete_node_key")
                game2.save_run()

                game3 = Game(
                    screen_size=(960, 600),
                    headless=True,
                    save_path=Path(tmpdir) / "run.json",
                )
                game3.options_path = Path(tmpdir) / "options.json"
                game3.rng.seed(7777)
                self.assertTrue(game3.load_run())
                self.assertEqual(
                    game3.player.skill_upgrades,
                    ["rogue_precision", "rogue_venom"],
                )
                # The run is still playable and the discipline tree offers valid choices.
                self.assertTrue(game3.available_disciplines())
            finally:
                pass

    # --- Character menu tabs --------------------------------------------------

    def test_character_menu_tabs_toggle_and_render(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=3, seed=3271)  # Acolyte
            try:
                self.assertEqual(game.character_menu_tab, "overview")
                # Toggle open, then switch tabs via Tab key.
                game.character_menu_open = True
                pygame.event.post(
                    pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB, mod=0)
                )
                game.handle_events()
                self.assertEqual(game.character_menu_tab, "disciplines")
                pygame.event.post(
                    pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB, mod=0)
                )
                game.handle_events()
                self.assertEqual(game.character_menu_tab, "overview")
                # Direct arrow keys also switch.
                pygame.event.post(
                    pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHT, mod=0)
                )
                game.handle_events()
                self.assertEqual(game.character_menu_tab, "disciplines")
                pygame.event.post(
                    pygame.event.Event(pygame.KEYDOWN, key=pygame.K_LEFT, mod=0)
                )
                game.handle_events()
                self.assertEqual(game.character_menu_tab, "overview")
                # Number keys switch too.
                pygame.event.post(
                    pygame.event.Event(pygame.KEYDOWN, key=pygame.K_2, mod=0)
                )
                game.handle_events()
                self.assertEqual(game.character_menu_tab, "disciplines")

                # Render overview tab.
                game.character_menu_tab = "overview"
                game.draw_character_menu()
                # Render Disciplines tab with some acquired nodes.
                game.character_menu_tab = "disciplines"
                game.player.memory_tokens = 2
                game.choose_discipline("acolyte_sanguine")
                game.choose_discipline("acolyte_gravebind")
                game.player.memory_tokens = 2
                game.character_menu_hovered_node = None
                rendered_text: list[str] = []
                original_draw_text = game.menus.draw_text

                def capture_draw_text(text, font, color, rect, *args, **kwargs):
                    rendered_text.append(str(text))
                    return original_draw_text(
                        text, font, color, rect, *args, **kwargs
                    )

                with patch.object(
                    game.menus,
                    "draw_text",
                    side_effect=capture_draw_text,
                ):
                    game.draw_character_menu()
                self.assertIn(
                    "By consuming a memory token, you will remember a discipline you have once acquired",
                    rendered_text,
                )
                self.assertTrue(
                    any("2 Memory Tokens" in text for text in rendered_text)
                )
                self.assertNotIn(
                    "mastery token",
                    " ".join(rendered_text).lower(),
                )
                # Compact screen size should still render without error.
                compact = Game(
                    screen_size=(640, 360),
                    headless=True,
                    save_path=Path(tmpdir) / "run2.json",
                )
                compact.options_path = Path(tmpdir) / "options2.json"
                compact.rng.seed(3272)
                compact.restart(ARCHETYPES[4])  # Ranger
                if compact.story_intro_pending:
                    self.assertTrue(compact.choose_story_relic_path(0))
                compact.active_cutscene = None
                compact.character_menu_open = True
                compact.character_menu_tab = "disciplines"
                compact.draw_character_menu()
            finally:
                pass

    def test_discipline_menu_reuses_static_tree_and_batches_node_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=1, seed=3272)
            game.character_menu_open = True
            game.character_menu_tab = "disciplines"
            game.character_menu_hovered_node = None

            game.draw_character_menu()
            tree = game.menus._discipline_tree_cache["Rogue"]
            layout_count = len(game.menus._discipline_grid_layout_cache)
            self.assertGreater(layout_count, 0)

            # Rendering derives all node states once from the acquired set. It
            # must not repeat the public O(tree) queries for every cell.
            with (
                patch.object(
                    game,
                    "discipline_state",
                    side_effect=AssertionError("per-cell state query"),
                ),
                patch.object(
                    game,
                    "available_disciplines",
                    side_effect=AssertionError("duplicate availability query"),
                ),
            ):
                game.draw_character_menu()

            self.assertIs(game.menus._discipline_tree_cache["Rogue"], tree)
            self.assertEqual(
                len(game.menus._discipline_grid_layout_cache), layout_count
            )

    def test_discipline_footer_token_status_padding_and_stable_geometry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0, seed=3273)  # Warden
            game.character_menu_open = True
            game.character_menu_tab = "disciplines"
            game.character_menu_hovered_node = None

            def render_footer(
                memory_tokens: int,
            ) -> tuple[
                dict[str, object],
                dict[str, pygame.Rect],
                list[tuple[str, pygame.Rect]],
            ]:
                game.player.memory_tokens = memory_tokens
                rendered: list[tuple[str, pygame.Rect]] = []
                original_draw_text = game.menus.draw_text

                def capture_draw_text(text, font, color, rect, *args, **kwargs):
                    rendered.append((str(text), pygame.Rect(rect)))
                    return original_draw_text(
                        text,
                        font,
                        color,
                        rect,
                        *args,
                        **kwargs,
                    )

                with patch.object(
                    game.menus,
                    "draw_text",
                    side_effect=capture_draw_text,
                ):
                    game.draw_character_menu()
                layout = dict(game._discipline_footer_layout)
                cells = {
                    key: pygame.Rect(rect)
                    for key, rect in game._discipline_cells.items()
                }
                return layout, cells, rendered

            plural, plural_cells, plural_text = render_footer(2)
            legend = pygame.Rect(plural["legend"])
            ready = pygame.Rect(plural["ready"])
            tokens = pygame.Rect(plural["tokens"])
            hint = pygame.Rect(plural["hint"])
            padding = int(plural["padding"])
            legend_items = plural["legend_items"]
            self.assertIsInstance(legend_items, tuple)
            assert isinstance(legend_items, tuple)
            chosen_swatch = pygame.Rect(legend_items[0]["swatch"])

            self.assertEqual(chosen_swatch.left - legend.left, padding)
            self.assertEqual(legend.right - ready.right, padding)
            self.assertEqual(tokens.top, legend.bottom)
            self.assertEqual(hint.top, tokens.bottom)
            self.assertEqual(plural["token_text"], "+2 memory tokens available")
            self.assertIn(
                ("+2 memory tokens available", tokens),
                plural_text,
            )
            self.assertIn(
                (
                    "By consuming a memory token, you will remember a discipline "
                    "you have once acquired",
                    hint,
                ),
                plural_text,
            )

            singular, singular_cells, singular_text = render_footer(1)
            self.assertEqual(singular["token_text"], "+1 memory token available")
            self.assertIn(
                (
                    "+1 memory token available",
                    pygame.Rect(singular["tokens"]),
                ),
                singular_text,
            )
            self.assertEqual(singular_cells, plural_cells)

            empty, empty_cells, empty_text = render_footer(0)
            self.assertEqual(empty["token_text"], "")
            self.assertNotIn(
                "+0 memory tokens available",
                {text for text, _rect in empty_text},
            )
            for key in ("footer", "legend", "ready", "tokens", "hint"):
                self.assertEqual(
                    pygame.Rect(empty[key]),
                    pygame.Rect(plural[key]),
                    key,
                )
            self.assertEqual(empty_cells, plural_cells)

            game.character_menu_tab = "overview"
            game.draw_character_menu()
            self.assertEqual(game._discipline_footer_layout, {})

    def test_discipline_headers_match_footer_panel_padding(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=0, seed=3274)  # Warden
            game.character_menu_open = True
            game.character_menu_tab = "disciplines"
            rendered: list[tuple[str, pygame.Rect]] = []
            original_draw_text = game.menus.draw_text

            def capture_draw_text(text, font, color, rect, *args, **kwargs):
                rendered.append((str(text), pygame.Rect(rect)))
                return original_draw_text(
                    text,
                    font,
                    color,
                    rect,
                    *args,
                    **kwargs,
                )

            with (
                patch.object(
                    game.menus,
                    "_draw_character_disciplines",
                    wraps=game.menus._draw_character_disciplines,
                ) as draw_disciplines,
                patch.object(
                    game.menus,
                    "draw_text",
                    side_effect=capture_draw_text,
                ),
            ):
                game.draw_character_menu()

            panel = pygame.Rect(draw_disciplines.call_args.args[0])
            padding = int(game._discipline_footer_layout["padding"])
            degree_one = next(
                rect for text, rect in rendered if text == "Degree 1"
            )
            path_names = {
                "Vow",
                "Bulwark",
                "Riposte",
                "Juggernaut",
            }
            path_header = next(
                rect for text, rect in rendered if text in path_names
            )

            self.assertEqual(degree_one.left - panel.left, padding)
            self.assertEqual(path_header.top - panel.top, padding)
            for cell in game._discipline_cells.values():
                self.assertLessEqual(pygame.Rect(cell).right, panel.right)
                self.assertLessEqual(pygame.Rect(cell).bottom, panel.bottom)


if __name__ == "__main__":
    unittest.main()
