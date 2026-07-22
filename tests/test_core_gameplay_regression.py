from __future__ import annotations

import os
import random
import sys
import unittest
from collections import deque
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame

from arch_rogue.dungeon import Dungeon
from arch_rogue.game import ARCHETYPES, DUNGEON_DEPTH, MAX_INVENTORY, Game
from arch_rogue.models import FloatingText, Item, Projectile, Tile


class Rc1RegressionTests(unittest.TestCase):
    def make_game(self, seed: int = 1234) -> Game:
        game = Game(screen_size=(960, 540), headless=True)
        game.rng.seed(seed)
        return game

    def confirm_story_intro(self, game: Game) -> None:
        if game.story_intro_pending:
            self.assertTrue(game.choose_story_relic_path(0))



    def test_dungeon_generation_has_connected_rooms_and_stairs(self) -> None:
        for seed in range(8):
            dungeon = Dungeon(random.Random(seed))
            self.assertGreaterEqual(len(dungeon.rooms), 8)
            sx, sy = dungeon.stairs
            self.assertEqual(dungeon.tiles[sx][sy], Tile.STAIRS)

            start = dungeon.rooms[0].center
            reachable = {start}
            frontier: deque[tuple[int, int]] = deque([start])
            while frontier:
                x, y = frontier.popleft()
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if (nx, ny) in reachable or not dungeon.in_bounds(nx, ny):
                        continue
                    if dungeon.tiles[nx][ny] == Tile.WALL:
                        continue
                    reachable.add((nx, ny))
                    frontier.append((nx, ny))

            for room in dungeon.rooms:
                self.assertIn(room.center, reachable)
            self.assertIn(dungeon.stairs, reachable)

    def test_item_interactions_and_hotkey_behaviors(self) -> None:
        # Shared Game/restart/story-intro setup; each section resets the
        # player state it asserts, so scenarios do not interfere. Nova and
        # dash gate only on their own timers (see combat.py), so reusing one
        # Game across all four former tests is safe.
        game = self.make_game()
        try:
            game.restart(ARCHETYPES[0])
            self.confirm_story_intro(game)

            # --- item pickup, equip, identify, and consumable use ---
            game.items.clear()
            px, py = game.player.x, game.player.y

            blade = Item(
                "Regression Blade",
                "weapon",
                power=9,
                rarity="Magic",
                x=px,
                y=py,
                unidentified=True,
            )
            game.items.append(blade)
            game.interact()
            self.assertNotIn(blade, game.items)
            self.assertIn(blade, game.player.inventory)

            game.use_inventory_slot(0)
            self.assertIs(game.player.equipment["weapon"], blade)
            self.assertFalse(blade.unidentified)
            self.assertEqual(
                game.player.melee_damage(),
                12 + game.player.level * 2 + game.player.melee_bonus + 9,
            )

            game.player.hp = 10
            game.player.inventory.append(
                Item("Minor Healing Potion", "potion", heal=35)
            )
            game.use_first_potion()
            self.assertEqual(game.player.hp, 45)

            game.player.mana = 5
            game.player.inventory.append(
                Item("Lesser Mana Potion", "mana_potion", mana=24)
            )
            game.use_inventory_slot(len(game.player.inventory) - 1)
            self.assertEqual(game.player.mana, 29)

            armor = Item(
                "Mystery Mail", "armor", defense=4, rarity="Rare", unidentified=True
            )
            game.player.inventory.append(Item("Scroll of Identify", "identify"))
            game.player.inventory.append(armor)
            scroll_index = len(game.player.inventory) - 2
            game.use_inventory_slot(scroll_index)
            self.assertFalse(armor.unidentified)
            self.assertNotIn(
                "Scroll of Identify", [item.name for item in game.player.inventory]
            )

            # --- Q toggles quest HUD; 5 uses health potion ---
            game.player.hp = 10
            game.player.inventory = [Item("Minor Healing Potion", "potion", heal=35)]

            self.assertFalse(game.quest_info_visible)
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_q, mod=0))
            game.handle_events()
            self.assertTrue(game.quest_info_visible)
            self.assertEqual(game.player.hp, 10)
            self.assertEqual(len(game.player.inventory), 1)

            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_q, mod=0))
            game.handle_events()
            self.assertFalse(game.quest_info_visible)

            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_5, mod=0))
            game.handle_events()
            self.assertEqual(game.player.hp, 45)
            self.assertEqual(game.player.inventory, [])

            # --- C toggles character menu; 3 uses class skill ---
            game.active_cutscene = None
            game.player.class_skill_timer = 0.0
            game.player.mana = game.player.max_mana
            starting_mana = game.player.mana

            self.assertFalse(game.character_menu_open)
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_c, mod=0))
            game.handle_events()
            self.assertTrue(game.character_menu_open)
            self.assertEqual(game.player.class_skill_timer, 0.0)
            self.assertEqual(game.player.mana, starting_mana)
            game.draw_character_menu()

            pygame.event.post(
                pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0)
            )
            game.handle_events()
            self.assertFalse(game.character_menu_open)

            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_c, mod=0))
            game.handle_events()
            self.assertTrue(game.character_menu_open)
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_i, mod=0))
            game.handle_events()
            self.assertTrue(game.inventory_open)
            self.assertFalse(game.character_menu_open)

            game.inventory_open = False
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_3, mod=0))
            game.handle_events()
            self.assertGreater(game.player.class_skill_timer, 0.0)
            self.assertLess(game.player.mana, starting_mana)

            # --- 4 dashes; Left Shift does not ---
            game.active_cutscene = None
            game.player.dash_timer = 0.0
            game.player.stamina = game.player.max_stamina
            starting_stamina = game.player.stamina

            pygame.event.post(
                pygame.event.Event(pygame.KEYDOWN, key=pygame.K_LSHIFT, mod=0)
            )
            game.handle_events()
            self.assertEqual(game.player.dash_timer, 0.0)
            self.assertEqual(game.player.stamina, starting_stamina)

            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_4, mod=0))
            game.handle_events()
            self.assertGreater(game.player.dash_timer, 0.0)
            self.assertLess(game.player.stamina, starting_stamina)
        finally:
            pass

    def test_stairs_advance_until_depth_ten_then_boss_gates_victory(self) -> None:
        game = self.make_game()
        try:
            game.restart(ARCHETYPES[0])
            self.assertEqual(game.current_depth, 1)
            self.assertFalse(game.boss_alive())

            for expected_depth in range(2, DUNGEON_DEPTH + 1):
                self.confirm_story_intro(game)
                stair_x, stair_y = (
                    game.dungeon.stairs[0] + 0.5,
                    game.dungeon.stairs[1] + 0.5,
                )
                game.player.x = stair_x
                game.player.y = stair_y
                game.interact()
                self.assertEqual(game.state, "playing")
                self.assertEqual(game.current_depth, expected_depth)
                self.assertTrue(game.dungeon.is_floor(game.player.x, game.player.y))

            self.confirm_story_intro(game)
            self.assertTrue(game.boss_alive())
            stair_x, stair_y = (
                game.dungeon.stairs[0] + 0.5,
                game.dungeon.stairs[1] + 0.5,
            )
            game.player.x = stair_x
            game.player.y = stair_y
            game.interact()
            self.assertEqual(game.state, "playing")
            self.assertTrue(any("sealed" in floater.text for floater in game.floaters))

            boss = game.boss_enemy()
            self.assertIsNotNone(boss)
            assert boss is not None
            game.kill_enemy(boss)
            self.assertFalse(game.boss_alive())
            self.assertTrue(any(item.rarity == "Unique" for item in game.items))
            self.assertTrue(
                all(
                    abs(item.x - stair_x) >= 1.0 or abs(item.y - stair_y) >= 1.0
                    for item in game.items
                    if item.rarity == "Unique"
                )
            )

            game.interact()
            self.assertEqual(game.state, "victory")
        finally:
            pass

    def test_restart_clears_transient_run_state(self) -> None:
        game = self.make_game()
        try:
            game.restart(ARCHETYPES[0])
            first_run = game.run_number
            game.inventory_open = True
            game.character_menu_open = True
            game.elapsed = 99.0
            game.state = "dead"
            game.projectiles.append(
                Projectile(
                    game.player.x, game.player.y, 1.0, 0.0, 1, "player", (255, 255, 255)
                )
            )
            game.floaters.append(
                FloatingText("test", game.player.x, game.player.y, (255, 255, 255))
            )
            game.slashes.append((game.player.x, game.player.y, 0.2, 1.0, 0.0))
            game.player.inventory.extend(
                Item(f"Filler {index}", "potion", heal=1)
                for index in range(MAX_INVENTORY)
            )

            game.restart(ARCHETYPES[-1])
            self.assertEqual(game.run_number, first_run + 1)
            self.assertEqual(game.current_depth, 1)
            self.assertEqual(game.state, "playing")
            self.assertFalse(game.inventory_open)
            self.assertFalse(game.character_menu_open)
            self.assertEqual(game.elapsed, 0.0)
            self.assertEqual(game.projectiles, [])
            self.assertEqual(game.floaters, [])
            self.assertEqual(game.slashes, [])
            self.assertEqual(game.player.inventory, [])
            self.assertEqual(game.player.class_name, ARCHETYPES[-1].name)
        finally:
            pass


if __name__ == "__main__":
    unittest.main()
