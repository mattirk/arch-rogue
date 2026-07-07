from __future__ import annotations

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

from arch_rogue.constants import DUNGEON_FLOOR_VARIANTS, DUNGEON_WALL_VARIANTS
from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game
from arch_rogue.models import Tile


class GuestRoomTests(unittest.TestCase):
    def tearDown(self) -> None:
        pass

    def make_game(self, tmpdir: str, seed: int = 2602) -> Game:
        game = Game(
            screen_size=(820, 540),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.rng.seed(seed)
        game.restart(ARCHETYPES[2])
        return game

    def story_relic_option_index(self, game: Game, choice_key: str) -> int:
        for index, (key, _label, _detail) in enumerate(
            game.story_relic_choice_options()
        ):
            if key == choice_key:
                return index
        self.fail(f"story relic choice {choice_key!r} was not available")
        return -1

    def test_guest_room_sealed_and_marked_on_story_floor(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                self.assertTrue(game.story_intro_pending)
                self.assertIsNotNone(game.dungeon.guest_room_index)
                assert game.dungeon.guest_room_index is not None
                room = game.dungeon.rooms[game.dungeon.guest_room_index]
                perimeter = [
                    (x, y)
                    for x in range(room.x, room.x + room.w)
                    for y in range(room.y, room.y + room.h)
                    if x in (room.x, room.x + room.w - 1)
                    or y in (room.y, room.y + room.h - 1)
                ]
                closed_doors = [
                    (x, y)
                    for x, y in perimeter
                    if game.dungeon.tiles[x][y] == Tile.CLOSED_DOOR
                ]
                self.assertGreaterEqual(len(closed_doors), 1)
                self.assertTrue(
                    all(
                        game.dungeon.tiles[x][y] in (Tile.WALL, Tile.CLOSED_DOOR)
                        for x, y in perimeter
                    )
                )
                cx, cy = room.center
                self.assertTrue(game.is_guest_tile(cx, cy))
                # Perimeter walls are NOT whole-guest tiles; instead each wall
                # reports which visible face borders the room interior
                # ("left" = +y face, "right" = +x face). At least one
                # perimeter wall has an interior guest face; corners have none.
                wall_faces = [
                    game.guest_wall_faces(x, y)
                    for x, y in perimeter
                    if game.dungeon.tiles[x][y] == Tile.WALL
                ]
                self.assertTrue(any(f in ("left", "right") for f in wall_faces))
                self.assertIsNone(game.guest_wall_faces(room.x, room.y))
                # A perimeter wall is not flagged as a whole guest tile.
                wall_tile = next(
                    (x, y)
                    for x, y in perimeter
                    if game.dungeon.tiles[x][y] == Tile.WALL
                )
                self.assertFalse(game.is_guest_tile(*wall_tile))
            finally:
                pass

    def test_story_guest_at_guest_room_center(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                self.assertTrue(game.story_intro_pending)
                guest = game.current_story_guest_for_depth()
                self.assertIsNotNone(guest)
                assert guest is not None
                assert game.dungeon.guest_room_index is not None
                cx, cy = game.dungeon.rooms[game.dungeon.guest_room_index].center
                self.assertLess(
                    math.hypot(guest.x - (cx + 0.5), guest.y - (cy + 0.5)), 0.1
                )
            finally:
                pass

    def test_relic_placed_near_guest_room_center_after_aid_choice(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                self.assertTrue(game.story_intro_pending)
                self.assertTrue(
                    game.choose_story_relic_path(
                        self.story_relic_option_index(game, "aid")
                    )
                )
                relic = game.current_story_relic()
                self.assertIsNotNone(relic)
                assert relic is not None
                assert game.dungeon.guest_room_index is not None
                cx, cy = game.dungeon.rooms[game.dungeon.guest_room_index].center
                self.assertLess(
                    math.hypot(relic.x - (cx + 0.5), relic.y - (cy + 0.5)), 1.5
                )
                guest = game.current_story_guest_for_depth()
                self.assertIsNotNone(guest)
                assert guest is not None
                self.assertGreater(
                    math.hypot(relic.x - guest.x, relic.y - guest.y), 0.1
                )
            finally:
                pass

    def test_guest_tile_surfaces_cached_and_sized(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                theme = game.theme.name
                floor_surf, fax, fay = game.tile_surface(
                    Tile.FLOOR, 0, shop_floor=False, guest=True
                )
                self.assertIsNotNone(floor_surf)
                self.assertGreater(floor_surf.get_width(), 0)
                self.assertGreater(floor_surf.get_height(), 0)
                wall_surf, wax, way = game.tile_surface(
                    Tile.WALL, 0, shop_floor=False, wall_guest_face="left"
                )
                self.assertIsNotNone(wall_surf)
                self.assertGreater(wall_surf.get_width(), 0)
                self.assertGreater(wall_surf.get_height(), 0)
                # Cached under the guest key (6-tuple: the wall face mask is
                # the last element; floors use the ``guest`` flag).
                self.assertIn(
                    (theme, int(Tile.FLOOR), 0, False, True, None),
                    game.tile_cache,
                )
                self.assertIn(
                    (theme, int(Tile.WALL), 0, False, False, "left"),
                    game.tile_cache,
                )
                # Prewarm populated the full guest variant set: walls for both
                # interior face options, floors in one guest form.
                guest_walls = [
                    k
                    for k in game.tile_cache
                    if k[0] == theme
                    and k[1] == int(Tile.WALL)
                    and k[5] in ("left", "right")
                ]
                guest_floors = [
                    k
                    for k in game.tile_cache
                    if k[0] == theme and k[1] == int(Tile.FLOOR) and k[4]
                ]
                self.assertEqual(len(guest_walls), DUNGEON_WALL_VARIANTS * 2)
                self.assertEqual(len(guest_floors), DUNGEON_FLOOR_VARIANTS)
            finally:
                pass

    def test_save_roundtrip_preserves_guest_room_and_guest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                self.assertTrue(game.story_intro_pending)
                guest = game.current_story_guest_for_depth()
                self.assertIsNotNone(guest)
                assert guest is not None
                guest_index = game.dungeon.guest_room_index
                guest_x, guest_y = guest.x, guest.y
                self.assertTrue(game.save_run())

                loaded = Game(
                    screen_size=(820, 540),
                    headless=True,
                    save_path=game.save_path,
                )
                loaded.options_path = game.options_path
                self.assertTrue(loaded.load_run(), loaded.last_load_error)
                self.assertEqual(loaded.dungeon.guest_room_index, guest_index)
                self.assertTrue(loaded.story_guests)
                restored = loaded.current_story_guest_for_depth()
                self.assertIsNotNone(restored)
                assert restored is not None
                self.assertAlmostEqual(restored.x, guest_x, places=4)
                self.assertAlmostEqual(restored.y, guest_y, places=4)
            finally:
                pass


if __name__ == "__main__":
    unittest.main()
