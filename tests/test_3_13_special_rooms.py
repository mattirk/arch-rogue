from __future__ import annotations

import copy
import os
import random
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from arch_rogue.content import ARCHETYPES
from arch_rogue.dungeon import Dungeon
from arch_rogue.game import Game
from arch_rogue.models import Item, SpecialRoom


class SpecialRooms313Tests(unittest.TestCase):
    def make_game_with_shop_and_guest(
        self, tmpdir: str, start_seed: int = 2602
    ) -> Game:
        for seed in range(start_seed, start_seed + 120):
            game = Game(
                screen_size=(820, 540),
                headless=True,
                save_path=Path(tmpdir) / f"run-{seed}.json",
            )
            game.options_path = Path(tmpdir) / f"options-{seed}.json"
            game.rng.seed(seed)
            game.restart(ARCHETYPES[2])
            if (
                game.dungeon.special_room_for_kind("shop") is not None
                and game.dungeon.special_room_for_kind("quest_room") is not None
            ):
                return game
        self.fail("Expected a deterministic game seed to generate shop and quest rooms")
        raise AssertionError

    def room_contains(self, room, x: float, y: float) -> bool:
        return room.x <= x < room.x + room.w and room.y <= y < room.y + room.h

    def test_special_room_assignment_is_deterministic_and_non_overlapping(self) -> None:
        seed = 17
        first = Dungeon(random.Random(seed), guest_room=True)
        second = Dungeon(random.Random(seed), guest_room=True)

        first_signature = [room.to_dict() for room in first.special_rooms]
        second_signature = [room.to_dict() for room in second.special_rooms]
        self.assertEqual(first_signature, second_signature)

        kinds = {room.kind for room in first.special_rooms}
        self.assertIn("quest_room", kinds)
        room_indexes = [room.room_index for room in first.special_rooms]
        self.assertEqual(len(room_indexes), len(set(room_indexes)))
        self.assertNotIn(0, room_indexes)
        self.assertNotIn(len(first.rooms) - 1, room_indexes)

        quest = first.special_room_for_kind("quest_room")
        self.assertIsNotNone(quest)
        assert quest is not None
        self.assertEqual(first.guest_room_index, quest.room_index)
        self.assertTrue(first.room_has_tag(quest.room_index, "story"))
        self.assertEqual(first.special_room_at_index(quest.room_index), quest)

    def test_shop_and_quest_handlers_preserve_existing_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game_with_shop_and_guest(tmpdir)
            shop = game.dungeon.special_room_for_kind("shop")
            quest = game.dungeon.special_room_for_kind("quest_room")
            self.assertIsNotNone(shop)
            self.assertIsNotNone(quest)
            assert shop is not None and quest is not None

            shop_room = game.dungeon.rooms[shop.room_index]
            quest_room = game.dungeon.rooms[quest.room_index]

            self.assertEqual(game.dungeon.shop_room_index, shop.room_index)
            self.assertEqual(game.dungeon.guest_room_index, quest.room_index)
            self.assertEqual(len(game.shopkeepers), 1)
            self.assertTrue(
                self.room_contains(
                    shop_room, game.shopkeepers[0].x, game.shopkeepers[0].y
                )
            )
            self.assertTrue(
                any(
                    item.slot == "shop_sign"
                    and self.room_contains(shop_room, item.x, item.y)
                    for item in game.items
                )
            )
            guest = game.current_story_guest_for_depth()
            self.assertIsNotNone(guest)
            assert guest is not None
            self.assertTrue(self.room_contains(quest_room, guest.x, guest.y))
            self.assertFalse(
                any(
                    self.room_contains(shop_room, enemy.x, enemy.y)
                    for enemy in game.enemies
                )
            )
            self.assertFalse(
                any(
                    self.room_contains(shop_room, trap.x, trap.y) for trap in game.traps
                )
            )
            self.assertFalse(
                any(
                    self.room_contains(quest_room, enemy.x, enemy.y)
                    for enemy in game.enemies
                )
            )
            self.assertFalse(
                any(
                    self.room_contains(quest_room, trap.x, trap.y)
                    for trap in game.traps
                )
            )

    def test_shop_gold_stack_variants_are_deterministic_cosmetics(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game_with_shop_and_guest(tmpdir)
            before_rng = game.rng.getstate()
            game._frame_cache = {}
            placements = game._shop_gold_stack_placements()
            self.assertGreaterEqual(len(placements), 3)
            self.assertTrue(all(len(placement) == 4 for placement in placements))
            self.assertTrue(all(0 <= placement[3] < 5 for placement in placements))
            self.assertGreater(len({placement[3] for placement in placements}), 1)
            self.assertEqual(game.rng.getstate(), before_rng)

            game._frame_cache = {}
            self.assertEqual(game._shop_gold_stack_placements(), placements)
            self.assertFalse(any(item.slot.startswith("gold_stack") for item in game.items))

            data = copy.deepcopy(game.serialize_run_state())
            loaded = Game(
                screen_size=(820, 540),
                headless=True,
                save_path=Path(tmpdir) / "gold-restore.json",
            )
            loaded.options_path = Path(tmpdir) / "gold-options.json"
            loaded.restore_run_state(data)
            loaded._frame_cache = {}
            self.assertEqual(loaded._shop_gold_stack_placements(), placements)
            self.assertFalse(
                any(item["slot"].startswith("gold_stack") for item in data["items"])
            )

    def test_legacy_save_indexes_migrate_to_special_rooms(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game_with_shop_and_guest(tmpdir)
            legacy_data = copy.deepcopy(game.serialize_run_state())
            legacy_data["dungeon"].pop("special_rooms", None)
            shop_index = legacy_data["dungeon"].get("shop_room_index")
            guest_index = legacy_data["dungeon"].get("guest_room_index")

            loaded = Game(
                screen_size=(820, 540),
                headless=True,
                save_path=Path(tmpdir) / "legacy-run.json",
            )
            loaded.options_path = Path(tmpdir) / "legacy-options.json"
            loaded.restore_run_state(legacy_data)

            self.assertEqual(loaded.dungeon.shop_room_index, shop_index)
            self.assertEqual(loaded.dungeon.guest_room_index, guest_index)
            self.assertIsNotNone(loaded.dungeon.special_room_for_kind("shop"))
            self.assertIsNotNone(loaded.dungeon.special_room_for_kind("quest_room"))

    def test_unknown_special_room_kind_loads_and_noops(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game_with_shop_and_guest(tmpdir)
            data = copy.deepcopy(game.serialize_run_state())
            data["dungeon"]["special_rooms"].append(
                {
                    "room_index": 1,
                    "kind": "npc_home",
                    "display_name": "Dusty Home",
                    "tags": ["home", "npc"],
                    "door_policy": "sealed",
                    "spawn_policy": "safe",
                    "reserved_tiles": [],
                    "anchor_points": {},
                    "state": {"locked": False},
                }
            )

            loaded = Game(
                screen_size=(820, 540),
                headless=True,
                save_path=Path(tmpdir) / "unknown-run.json",
            )
            loaded.options_path = Path(tmpdir) / "unknown-options.json"
            loaded.restore_run_state(data)
            unknown = loaded.dungeon.special_room_for_kind("npc_home")
            self.assertIsNotNone(unknown)
            before_items = len(loaded.items)
            loaded._populate_special_rooms()
            self.assertEqual(len(loaded.items), before_items)

    def test_future_room_kind_can_register_population_handler(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game_with_shop_and_guest(tmpdir)
            occupied = {room.room_index for room in game.dungeon.special_rooms}
            room_index = next(
                index
                for index in range(1, len(game.dungeon.rooms) - 1)
                if index not in occupied
            )
            garden = SpecialRoom(
                room_index=room_index,
                kind="garden",
                display_name="Grave Garden",
                tags=["garden", "refuge"],
                door_policy="sealed",
                spawn_policy="safe",
            )
            game.dungeon.special_rooms.append(garden)

            def populate_garden(special_room: SpecialRoom, room) -> None:
                cx, cy = room.center
                special_room.anchor_points["feature"] = [cx, cy]
                special_room.state["blooming"] = True
                game.items.append(
                    Item(
                        "Garden Lantern",
                        "garden_feature",
                        rarity="Common",
                        x=cx + 0.5,
                        y=cy + 0.5,
                    )
                )

            game.register_special_room_handler("garden", populate_garden)
            game._populate_special_rooms()

            self.assertTrue(garden.state["blooming"])
            self.assertEqual(
                garden.anchor("feature"), game.dungeon.rooms[room_index].center
            )
            self.assertTrue(
                any(
                    item.slot == "garden_feature"
                    and self.room_contains(
                        game.dungeon.rooms[room_index], item.x, item.y
                    )
                    for item in game.items
                )
            )


if __name__ == "__main__":
    unittest.main()
