from __future__ import annotations

import json
import os
import random
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame

from arch_rogue.content import ARCHETYPES
from arch_rogue.dungeon import BAR_ROOM_KIND, GARDEN_ROOM_KIND, MAP_H, MAP_W
from arch_rogue.game import Game
from arch_rogue.menus.controls import KEYBOARD_ROWS
from arch_rogue.models import SpecialRoom


def make_game(tmpdir: str, screen_size: tuple[int, int] = (1100, 620)) -> Game:
    game = Game(
        screen_size=screen_size,
        headless=True,
        save_path=Path(tmpdir) / "run.json",
    )
    game.options_path = Path(tmpdir) / "options.json"
    game.meta_progress = game.default_meta_progress()
    game.run_history = []
    game.rng.seed(2323)
    game.restart(ARCHETYPES[0])
    if game.story_intro_pending:
        game.choose_story_relic_path(0)
    game.active_cutscene = None
    return game


def post_key(game: Game, key: int, mod: int = 0) -> None:
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key, mod=mod))
    game.handle_events()


def inject_special_room(game: Game, kind: str, room_index: int) -> None:
    game.dungeon.special_rooms = [
        special
        for special in game.dungeon.special_rooms
        if special.kind != kind
    ] + [SpecialRoom(room_index=room_index, kind=kind)]
    # Force the minimap floor cache to rebuild its room lookup.
    game._minimap_cache = {}


class MinimapToggleTests(unittest.TestCase):
    def test_ctrl_m_toggles_and_persists_to_options_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            self.assertEqual(game.state, "playing")
            self.assertTrue(game.minimap_visible)

            post_key(game, pygame.K_m, pygame.KMOD_CTRL)
            self.assertFalse(game.minimap_visible)

            data = json.loads(Path(game.options_path).read_text())
            self.assertEqual(data["schema_version"], 10)
            self.assertFalse(data["minimap_visible"])

            post_key(game, pygame.K_m, pygame.KMOD_CTRL)
            self.assertTrue(game.minimap_visible)

            # A fresh instance loading the same file restores the choice.
            game.toggle_minimap()
            other = Game(
                screen_size=(1100, 620),
                headless=True,
                save_path=Path(tmpdir) / "run2.json",
            )
            other.options_path = game.options_path
            self.assertTrue(other.load_options())
            self.assertFalse(other.minimap_visible)

    def test_bare_m_and_wrong_states_do_not_toggle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            post_key(game, pygame.K_m)
            self.assertTrue(game.minimap_visible)

            # Options menu: Ctrl+M must not toggle the minimap, and M no
            # longer maps to anything there (the music row is parked until
            # real tracks exist — 4.11.0).
            game.state = "options"
            post_key(game, pygame.K_m, pygame.KMOD_CTRL)
            self.assertTrue(game.minimap_visible)
            post_key(game, pygame.K_m)
            self.assertFalse(game.music_enabled)
            game.state = "playing"

    def test_ctrl_m_ignored_on_title(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = Game(
                screen_size=(1100, 620),
                headless=True,
                save_path=Path(tmpdir) / "run.json",
            )
            game.options_path = Path(tmpdir) / "options.json"
            self.assertEqual(game.state, "title")
            post_key(game, pygame.K_m, pygame.KMOD_CTRL)
            self.assertTrue(game.minimap_visible)

    def test_controls_screen_documents_ctrl_m(self) -> None:
        self.assertTrue(
            any(row[0] == "Ctrl+M" for row in KEYBOARD_ROWS),
            "Ctrl+M should be listed on the controls screen",
        )


class MinimapZoomTests(unittest.TestCase):
    def test_adjust_zoom_steps_clamps_and_resets_per_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.draw()
            base_half_w, _ = game._minimap_tile_scale()
            self.assertEqual(game.minimap_zoom, 1.0)

            game.adjust_minimap_zoom(1)
            self.assertGreater(game.minimap_zoom, 1.0)
            self.assertGreater(game._minimap_tile_scale()[0], base_half_w)

            for _ in range(20):
                game.adjust_minimap_zoom(1)
            self.assertLessEqual(game.minimap_zoom, game.MINIMAP_ZOOM_MAX)
            for _ in range(40):
                game.adjust_minimap_zoom(-1)
            self.assertGreaterEqual(game.minimap_zoom, game.MINIMAP_ZOOM_MIN)

            # The floor cache key carries the tile scale, so the next draw
            # rebuilds the terrain at the new zoom.
            game.draw()
            self.assertEqual(
                game._minimap_cache["floor_key"][3],
                game._minimap_tile_scale()[0],
            )

            # Zoom is per-run: a new run starts back at the default scale,
            # and nothing about it is written to the options file.
            game.restart(ARCHETYPES[0])
            self.assertEqual(game.minimap_zoom, 1.0)
            options_path = Path(game.options_path)
            if options_path.exists():
                saved = json.loads(options_path.read_text())
                self.assertNotIn("minimap_zoom", saved)

    def test_wheel_over_card_zooms_only_when_hovered(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.draw()
            rect = game._minimap_rect
            self.assertIsNotNone(rect)
            self.assertTrue(game.minimap_contains_screen_point(rect.center))
            self.assertFalse(
                game.minimap_contains_screen_point(
                    (rect.left - 40, rect.centery)
                )
            )

            with mock.patch("pygame.mouse.get_pos", return_value=rect.center):
                pygame.event.post(pygame.event.Event(pygame.MOUSEWHEEL, y=1))
                game.handle_events()
            self.assertGreater(game.minimap_zoom, 1.0)

            zoomed = game.minimap_zoom
            away = (rect.left - 40, rect.centery)
            with mock.patch("pygame.mouse.get_pos", return_value=away):
                pygame.event.post(pygame.event.Event(pygame.MOUSEWHEEL, y=1))
                game.handle_events()
            self.assertEqual(game.minimap_zoom, zoomed)


class MinimapDrawTests(unittest.TestCase):
    def test_draw_publishes_rect_and_respects_hidden_states(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.draw()
            rect = game._minimap_rect
            self.assertIsNotNone(rect)
            width, _height = game.screen.get_size()
            # Top-right corner: right edge at the canonical screen margin.
            self.assertEqual(rect.right, width - game.ui(18))
            self.assertEqual(rect.top, game.ui(14))

            game.minimap_visible = False
            game.draw()
            self.assertIsNone(game._minimap_rect)

            game.minimap_visible = True
            game.mobile_mode = True
            game.draw_minimap()
            self.assertIsNone(game._minimap_rect)
            game.mobile_mode = False

    def test_incremental_reveal_matches_one_shot_redraw(self) -> None:
        # The fog mirror patches the cached terrain surface in place. Lifted
        # wall blocks and neighbor-aware rims overlap adjacent cells, so any
        # reveal order must still converge on exactly the pixels a single
        # full-map reveal produces.
        full = [(x, y) for x in range(MAP_W) for y in range(MAP_H)]
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.revealed_tiles = set(full)
            game.draw_minimap()
            expected = pygame.image.tobytes(
                game._minimap_cache["surface"], "RGBA"
            )

        shuffled = full[:]
        random.Random(7).shuffle(shuffled)
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.revealed_tiles = set()
            for start in range(0, len(shuffled), 337):
                game.revealed_tiles |= set(shuffled[start : start + 337])
                game.draw_minimap()
            incremental = pygame.image.tobytes(
                game._minimap_cache["surface"], "RGBA"
            )
        self.assertTrue(
            expected == incremental,
            "incrementally revealed terrain diverged from a one-shot redraw",
        )

    def test_narrow_window_suppresses_card(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir, screen_size=(820, 540))
            game.draw()
            self.assertIsNone(game._minimap_rect)

    def test_boss_bar_shrinks_or_suppresses_card(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.draw()
            full_height = game._minimap_rect.height

            game.boss_bar_top = lambda: game.ui(96)
            game.draw_minimap()
            self.assertIsNotNone(game._minimap_rect)
            self.assertLess(game._minimap_rect.height, full_height)

            game.boss_bar_top = lambda: game.ui(40)
            game.draw_minimap()
            self.assertIsNone(game._minimap_rect)

    def test_deck_boss_floor_keeps_the_minimap(self) -> None:
        # 5.0 regression: the Deck's 1.6x card minimum exceeded the
        # header-height budget, so the give-way clamp suppressed the card on
        # every boss floor even though the centered boss bar (640 wide at
        # 1280x800) ends well short of the right-aligned card. The clamp now
        # applies only when the cluster actually reaches under the card.
        from types import SimpleNamespace

        from arch_rogue import steam_deck

        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["ARCH_ROGUE_STEAM_DECK"] = "1"
            steam_deck.clear_detection_cache()
            try:
                game = make_game(tmpdir, screen_size=(1280, 800))
                game.draw()
                no_boss_rect = game._minimap_rect
                self.assertIsNotNone(no_boss_rect)

                game.enemies.append(
                    SimpleNamespace(
                        is_boss_encounter=True, alive=True, size=2
                    )
                )
                metrics = game.boss_bar_metrics()
                self.assertIsNotNone(metrics)
                game.draw_minimap()
                rect = game._minimap_rect
                self.assertIsNotNone(
                    rect, "boss floor suppressed the Deck minimap"
                )
                self.assertEqual(rect.height, no_boss_rect.height)
                bar_rect, plaque_rect, _big = metrics
                self.assertFalse(rect.colliderect(bar_rect))
                self.assertFalse(rect.colliderect(plaque_rect))

                # A cluster that genuinely reaches under the card still
                # forces the give-way clamp (here: suppression, because the
                # Deck minimum height exceeds the header budget).
                wide = pygame.Rect(0, bar_rect.y, 1280, bar_rect.height)
                game.boss_bar_metrics = lambda: (wide, plaque_rect, True)
                game.draw_minimap()
                self.assertIsNone(game._minimap_rect)
            finally:
                os.environ.pop("ARCH_ROGUE_STEAM_DECK", None)
                steam_deck.clear_detection_cache()

    def test_terrain_mirror_grows_and_resets_with_floor(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.update_revealed_tiles()
            game.draw()
            state = game._minimap_cache
            self.assertTrue(state["drawn"])
            self.assertEqual(len(state["drawn"]), len(game.revealed_tiles))
            first_key = state["floor_key"]

            # New run -> new floor key -> fresh mirror.
            game.restart(ARCHETYPES[0])
            if game.story_intro_pending:
                game.choose_story_relic_path(0)
            game.active_cutscene = None
            game.draw()
            self.assertNotEqual(game._minimap_cache["floor_key"], first_key)

    def test_invalidate_render_caches_clears_minimap_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.draw()
            self.assertTrue(game._minimap_cache)
            game._invalidate_render_caches()
            self.assertFalse(game._minimap_cache)

    def test_legacy_graphics_mode_draws_too(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.set_legacy_graphics(True)
            game.draw()
            self.assertIsNotNone(game._minimap_rect)


class MinimapMarkerTests(unittest.TestCase):
    def test_bar_and_garden_markers_require_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            inject_special_room(game, BAR_ROOM_KIND, 1)
            inject_special_room(game, GARDEN_ROOM_KIND, 2)
            game.revealed_tiles = set()

            kinds = {kind for kind, _x, _y in game.minimap_markers()}
            self.assertNotIn(BAR_ROOM_KIND, kinds)
            self.assertNotIn(GARDEN_ROOM_KIND, kinds)
            self.assertNotIn("stairs", kinds)

            bar_room = game.dungeon.rooms[1]
            game.revealed_tiles.add((bar_room.x + 1, bar_room.y + 1))
            kinds = {kind for kind, _x, _y in game.minimap_markers()}
            self.assertIn(BAR_ROOM_KIND, kinds)
            self.assertNotIn(GARDEN_ROOM_KIND, kinds)

            # Discovery is remembered for the floor even if the reveal set
            # is later rebuilt without those tiles.
            game.revealed_tiles = set()
            kinds = {kind for kind, _x, _y in game.minimap_markers()}
            self.assertIn(BAR_ROOM_KIND, kinds)

            stairs_x, stairs_y = game.dungeon.stairs
            game.revealed_tiles.add((stairs_x, stairs_y))
            kinds = {kind for kind, _x, _y in game.minimap_markers()}
            self.assertIn("stairs", kinds)

    def test_marker_positions_are_room_centers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            inject_special_room(game, BAR_ROOM_KIND, 1)
            room = game.dungeon.rooms[1]
            game.revealed_tiles.add((room.x + 1, room.y + 1))
            markers = {
                kind: (x, y) for kind, x, y in game.minimap_markers()
            }
            cx, cy = room.center
            self.assertEqual(markers[BAR_ROOM_KIND], (cx + 0.5, cy + 0.5))

    def test_dark_floor_markers_follow_lantern(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.set_current_floor_dark(True)
            stairs_x, stairs_y = game.dungeon.stairs

            # Park the player far away from the stairs: nothing to show.
            game.player.x = float(stairs_x + 20.5) if stairs_x < 40 else 2.5
            game.player.y = float(stairs_y + 20.5) if stairs_y < 40 else 2.5
            kinds = {kind for kind, _x, _y in game.minimap_markers()}
            self.assertNotIn("stairs", kinds)

            game.player.x = stairs_x + 0.5
            game.player.y = stairs_y + 0.5
            kinds = {kind for kind, _x, _y in game.minimap_markers()}
            self.assertIn("stairs", kinds)

            # The dark-floor draw path renders without touching fog memory.
            game.draw()
            self.assertIsNotNone(game._minimap_rect)
            self.assertFalse(game.revealed_tiles)

    def test_guidance_gating_and_route(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            spawn_room = game.dungeon.rooms[0]
            cx, cy = spawn_room.center
            # Drop any live relic item so the injected fallback position is
            # authoritative for the target.
            game.items = [
                item
                for item in game.items
                if getattr(item, "slot", "") != "story_relic"
            ]
            game.story_relic_position = (cx + 0.5, cy + 0.5)
            game.story_relic_collected = False
            game.story_intro_pending = False

            game.story_relic_guidance_enabled = False
            self.assertIsNone(game.minimap_guidance())

            game.story_relic_guidance_enabled = True
            self.assertEqual(game.minimap_guidance(), (cx + 0.5, cy + 0.5))

            game.story_intro_pending = True
            self.assertIsNone(game.minimap_guidance())
            game.story_intro_pending = False

            # And the full frame draws with guidance active.
            game.draw()
            self.assertIsNotNone(game._minimap_rect)


if __name__ == "__main__":
    unittest.main()
