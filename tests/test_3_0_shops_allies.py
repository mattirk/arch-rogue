from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame

from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game
from arch_rogue.models import Item, Tile


class ShopsAndAlliesMilestoneTests(unittest.TestCase):
    def make_game_with_shop(self) -> Game:
        for seed in range(100, 140):
            game = Game(screen_size=(960, 540), headless=True)
            game.rng.seed(seed)
            game.restart(ARCHETYPES[0])
            if game.shopkeepers:
                return game
            pygame.quit()
        self.fail("Expected at least one deterministic seed to generate a shop")

    def tearDown(self) -> None:
        pygame.quit()

    def test_shop_room_has_allied_shopkeeper_stock_and_closed_door(self) -> None:
        game = self.make_game_with_shop()
        try:
            shop_index = game.dungeon.shop_room_index
            self.assertIsNotNone(shop_index)
            assert shop_index is not None
            self.assertEqual(len(game.shopkeepers), 1)
            shopkeeper = game.shopkeepers[0]
            self.assertEqual(shopkeeper.role, "Allied Shopkeeper")
            self.assertGreaterEqual(len(shopkeeper.inventory), 5)
            self.assertTrue(any(item.slot == "potion" for item in shopkeeper.inventory))
            shop_room = game.dungeon.rooms[shop_index]
            self.assertTrue(
                shop_room.x <= shopkeeper.x < shop_room.x + shop_room.w
                and shop_room.y <= shopkeeper.y < shop_room.y + shop_room.h
            )
            perimeter = [
                (x, y)
                for x in range(shop_room.x, shop_room.x + shop_room.w)
                for y in range(shop_room.y, shop_room.y + shop_room.h)
                if x in (shop_room.x, shop_room.x + shop_room.w - 1)
                or y in (shop_room.y, shop_room.y + shop_room.h - 1)
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
            for door_x, door_y in closed_doors:
                self.assertFalse(game.dungeon.is_floor(door_x + 0.5, door_y + 0.5))
                side_walls = game.dungeon._door_side_wall_tiles(
                    shop_room, door_x, door_y
                )
                self.assertIsNotNone(side_walls)
                assert side_walls is not None
                self.assertTrue(
                    all(game.dungeon.tiles[x][y] == Tile.WALL for x, y in side_walls)
                )
        finally:
            pygame.quit()

    def test_doors_open_with_interact_and_become_walkable(self) -> None:
        game = self.make_game_with_shop()
        try:
            door = next(
                (x, y)
                for x, column in enumerate(game.dungeon.tiles)
                for y, tile in enumerate(column)
                if tile == Tile.CLOSED_DOOR
            )
            game.player.x = door[0] + 0.5
            game.player.y = door[1] - 0.45
            self.assertIsNotNone(game.nearby_closed_door())
            self.assertTrue(game.open_nearby_door())
            self.assertEqual(game.dungeon.tiles[door[0]][door[1]], Tile.OPEN_DOOR)
            self.assertTrue(game.dungeon.is_floor(door[0] + 0.5, door[1] + 0.5))
        finally:
            pygame.quit()

    def test_shopkeeper_buys_and_sells_items_for_gold(self) -> None:
        game = self.make_game_with_shop()
        try:
            shopkeeper = game.shopkeepers[0]
            game.player.x = shopkeeper.x
            game.player.y = shopkeeper.y + 0.8
            game.open_shop(shopkeeper)
            self.assertTrue(game.shop_open)
            first_stock = shopkeeper.inventory[0]
            price = game.shop_price(shopkeeper, first_stock)
            game.player.gold = price
            inventory_count = len(game.player.inventory)
            self.assertTrue(game.transact_shop_selection())
            self.assertEqual(game.player.gold, 0)
            self.assertEqual(len(game.player.inventory), inventory_count + 1)
            self.assertIn(first_stock, game.player.inventory)

            sell_item = Item("Test Sale Dagger", "weapon", power=2, rarity="Common")
            game.player.inventory.append(sell_item)
            game.shop_mode = "sell"
            game.shop_cursor = game.player.inventory.index(sell_item)
            sell_value = game.shop_buyback_value(shopkeeper, sell_item)
            self.assertTrue(game.transact_shop_selection())
            self.assertEqual(game.player.gold, sell_value)
            self.assertIn(sell_item, shopkeeper.inventory)
            self.assertNotIn(sell_item, game.player.inventory)
        finally:
            pygame.quit()


if __name__ == "__main__":
    unittest.main()
