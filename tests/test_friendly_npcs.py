from __future__ import annotations

import copy
import math
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
from arch_rogue.dungeon import MAP_H, MAP_W, Dungeon
from arch_rogue.game import Game
from arch_rogue.models import IdleNpc, Room, Shopkeeper, StoryGuest, Tile


class FriendlyNpcRuntimeTests(unittest.TestCase):
    ROOM = Room(20, 20, 12, 12)
    DOOR = (ROOM.x + ROOM.w - 1, ROOM.y + ROOM.h // 2)

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.game_count = 0

    def make_game(self, rng_seed: int = 4301) -> Game:
        self.game_count += 1
        game = Game(
            screen_size=(820, 540),
            headless=True,
            save_path=Path(self.tmpdir.name) / f"run-{self.game_count}.json",
        )
        game.options_path = Path(self.tmpdir.name) / f"options-{self.game_count}.json"
        game.rng.seed(4300)
        game.restart(ARCHETYPES[0])

        game.dungeon = self.make_dungeon()
        game.shopkeepers = [
            Shopkeeper(24.5, 25.5, "Mara", "Quartermaster", inventory=[])
        ]
        game.story_guests = [
            StoryGuest(
                26.5,
                25.5,
                4,
                0,
                "Ilyra",
                "Veiled Witness",
                "seeks safe passage",
                "The old stones remember.",
                [],
            )
        ]
        game.idle_npcs = [
            IdleNpc(28.5, 25.5, kind="bar", name="Tovin", role="Patron")
        ]
        game.player.x = 4.5
        game.player.y = 4.5
        game.current_depth = 4
        # No active profile makes the mixin use its deterministic elapsed-time
        # fallback, avoiding dependence on the audio transport's start instant.
        game.run_music_seed = 0
        game.elapsed = 0.0
        game.story_intro_pending = False
        game.active_cutscene = None
        game.inventory_open = False
        game.character_menu_open = False
        game.shop_open = False
        game.active_shopkeeper = None
        game.reset_friendly_npc_runtime()

        # Seed only after fixture construction so the assertions cover runtime
        # movement rather than dungeon/population setup performed by restart().
        game.rng.seed(rng_seed)
        return game

    def make_dungeon(self) -> Dungeon:
        dungeon = object.__new__(Dungeon)
        dungeon.rng = random.Random(991)
        dungeon.boss_arena = False
        dungeon.guest_room = False
        dungeon.rooms = [self.ROOM]
        dungeon.special_rooms = []
        dungeon.stairs = (self.ROOM.x + 1, self.ROOM.y + 1)
        dungeon.tiles = [
            [Tile.WALL for _ in range(MAP_H)] for _ in range(MAP_W)
        ]

        for x in range(self.ROOM.x + 1, self.ROOM.x + self.ROOM.w - 1):
            for y in range(self.ROOM.y + 1, self.ROOM.y + self.ROOM.h - 1):
                dungeon.tiles[x][y] = Tile.FLOOR

        door_x, door_y = self.DOOR
        dungeon.tiles[door_x][door_y] = Tile.CLOSED_DOOR
        for x in range(door_x + 1, door_x + 4):
            dungeon.tiles[x][door_y] = Tile.FLOOR
        return dungeon

    @staticmethod
    def positions(game: Game) -> tuple[tuple[float, float], ...]:
        return tuple((npc.x, npc.y) for npc in game.iter_friendly_npcs())

    def assert_faces_player(self, game: Game, npc: Shopkeeper | StoryGuest) -> None:
        motion = game.friendly_npc_motion(npc)
        dx = game.player.x - npc.x
        dy = game.player.y - npc.y
        distance = math.hypot(dx, dy)
        self.assertGreater(distance, 0.001)
        self.assertAlmostEqual(motion.facing_x, dx / distance, places=7)
        self.assertAlmostEqual(motion.facing_y, dy / distance, places=7)
        self.assertFalse(motion.moving)

    def test_all_friendly_npc_types_move_deterministically_without_using_game_rng(
        self,
    ) -> None:
        first = self.make_game(rng_seed=11)
        second = self.make_game(rng_seed=987654)
        first_rng_state = first.rng.getstate()
        second_rng_state = second.rng.getstate()
        starts = self.positions(first)
        moved = [False] * len(starts)

        for step in range(160):
            elapsed = (step + 1) * 0.125
            first.elapsed = elapsed
            second.elapsed = elapsed
            first.update_friendly_npcs(0.125)
            second.update_friendly_npcs(0.125)

            first_positions = self.positions(first)
            second_positions = self.positions(second)
            for index, (first_position, second_position) in enumerate(
                zip(first_positions, second_positions, strict=True)
            ):
                self.assertAlmostEqual(first_position[0], second_position[0], places=12)
                self.assertAlmostEqual(first_position[1], second_position[1], places=12)
                if math.hypot(
                    first_position[0] - starts[index][0],
                    first_position[1] - starts[index][1],
                ) > 0.05:
                    moved[index] = True

        self.assertTrue(all(moved), "each friendly NPC type should visibly roam")
        self.assertEqual(first.rng.getstate(), first_rng_state)
        self.assertEqual(second.rng.getstate(), second_rng_state)

    def test_npcs_stay_in_original_room_interior_after_door_opens(self) -> None:
        game = self.make_game()
        room = game.dungeon.rooms[0]
        original_rooms = {
            id(npc): game.dungeon.room_at(npc.x, npc.y)
            for npc in game.iter_friendly_npcs()
        }
        radius = game.FRIENDLY_NPC_RADIUS
        min_x = room.x + 1.0 + radius
        max_x = room.x + room.w - 1.0 - radius
        min_y = room.y + 1.0 + radius
        max_y = room.y + room.h - 1.0 - radius

        for step in range(480):
            if step == 40:
                self.assertTrue(game.dungeon.open_door(*self.DOOR))
            game.elapsed = (step + 1) * 0.125
            game.update_friendly_npcs(0.125)

            for npc in game.iter_friendly_npcs():
                self.assertIs(game.dungeon.room_at(npc.x, npc.y), original_rooms[id(npc)])
                self.assertGreaterEqual(npc.x + 1e-9, min_x)
                self.assertLessEqual(npc.x, max_x + 1e-9)
                self.assertGreaterEqual(npc.y + 1e-9, min_y)
                self.assertLessEqual(npc.y, max_y + 1e-9)

        door_x, door_y = self.DOOR
        self.assertEqual(game.dungeon.tiles[door_x][door_y], Tile.OPEN_DOOR)

    def test_active_shopkeeper_and_near_story_guest_hold_and_face_player(self) -> None:
        game = self.make_game()
        shopkeeper = game.shopkeepers[0]
        guest = game.story_guests[0]

        game.shop_open = True
        game.active_shopkeeper = shopkeeper
        game.player.x = 29.5
        game.player.y = 29.5
        shopkeeper_position = (shopkeeper.x, shopkeeper.y)
        game.elapsed = 0.25
        game.update_friendly_npcs(0.5)
        self.assertEqual((shopkeeper.x, shopkeeper.y), shopkeeper_position)
        self.assert_faces_player(game, shopkeeper)

        game.shop_open = False
        game.active_shopkeeper = None
        game.player.x = guest.x + 0.7
        game.player.y = guest.y - 0.4
        self.assertLess(math.hypot(guest.x - game.player.x, guest.y - game.player.y), 1.45)
        guest_position = (guest.x, guest.y)
        game.elapsed += 0.25
        game.update_friendly_npcs(0.5)
        self.assertEqual((guest.x, guest.y), guest_position)
        self.assert_faces_player(game, guest)

    def test_inventory_pause_freezes_positions_while_dance_progress_advances(self) -> None:
        game = self.make_game()
        game.elapsed = 0.125
        game.update_friendly_npcs(0.25)
        positions_before = self.positions(game)
        states_before = [
            game.friendly_npc_visual_state(npc) for npc in game.iter_friendly_npcs()
        ]

        game.inventory_open = True
        game.update(0.25)

        states_after = [
            game.friendly_npc_visual_state(npc) for npc in game.iter_friendly_npcs()
        ]
        self.assertEqual(self.positions(game), positions_before)
        self.assertTrue(all(not state[2] for state in states_after))
        for state_before, state_after in zip(states_before, states_after, strict=True):
            self.assertAlmostEqual(state_before[3], 0.125, places=7)
            self.assertAlmostEqual(state_after[3], 0.375, places=7)
            self.assertGreater(state_after[3], state_before[3])

    def test_visual_states_share_the_same_music_beat_phase(self) -> None:
        game = self.make_game()
        game.elapsed = 3.375

        phases = [
            game.friendly_npc_visual_state(npc)[3]
            for npc in game.iter_friendly_npcs()
        ]

        self.assertEqual(len(phases), 3)
        for phase in phases:
            self.assertAlmostEqual(phase, phases[0], places=12)
            self.assertAlmostEqual(phase, 0.375, places=7)

    def test_moved_npc_positions_round_trip_and_resume_inside_their_rooms(self) -> None:
        self.game_count += 1
        game = Game(
            screen_size=(820, 540),
            headless=True,
            save_path=Path(self.tmpdir.name) / f"round-trip-{self.game_count}.json",
        )
        game.options_path = Path(self.tmpdir.name) / "round-trip-options.json"
        game.rng.seed(2602)
        game.restart(ARCHETYPES[2])
        if game.story_intro_pending:
            self.assertTrue(game.choose_story_relic_path(0))
        game.active_cutscene = None
        game.player.x, game.player.y = game.dungeon.rooms[0].random_point(
            random.Random(7)
        )

        homes = {
            id(npc): (npc.x, npc.y) for npc in game.iter_friendly_npcs()
        }
        for _ in range(160):
            game.elapsed += 0.125
            game.update_friendly_npcs(0.125)
        before = self.positions(game)
        self.assertTrue(
            any(
                math.hypot(npc.x - homes[id(npc)][0], npc.y - homes[id(npc)][1])
                > 0.05
                for npc in game.iter_friendly_npcs()
            )
        )

        data = copy.deepcopy(game.serialize_run_state())
        self.game_count += 1
        loaded = Game(
            screen_size=(820, 540),
            headless=True,
            save_path=Path(self.tmpdir.name) / f"round-trip-{self.game_count}.json",
        )
        loaded.options_path = Path(self.tmpdir.name) / "loaded-options.json"
        loaded.restore_run_state(data)
        self.assertEqual(self.positions(loaded), before)
        self.assertEqual(loaded._friendly_npc_motions, {})

        assigned_rooms = {
            id(npc): loaded.dungeon.room_at(npc.x, npc.y)
            for npc in loaded.iter_friendly_npcs()
        }
        for _ in range(80):
            loaded.elapsed += 0.125
            loaded.update_friendly_npcs(0.125)
        for npc in loaded.iter_friendly_npcs():
            self.assertIs(
                loaded.dungeon.room_at(npc.x, npc.y), assigned_rooms[id(npc)]
            )

    def test_runtime_cache_prunes_removed_npcs_and_can_be_reset(self) -> None:
        game = self.make_game()
        game.update_friendly_npcs(0.0)
        self.assertEqual(len(game._friendly_npc_motions), 3)

        game.shopkeepers = []
        game.story_guests = []
        for index in range(64):
            npc = IdleNpc(
                25.5,
                25.5,
                kind="bar",
                name=f"Patron {index}",
                role="Patron",
            )
            game.idle_npcs = [npc]
            game.elapsed = float(index)
            game.update_friendly_npcs(0.0)
            self.assertEqual(set(game._friendly_npc_motions), {id(npc)})
            self.assertIs(game._friendly_npc_motions[id(npc)].actor, npc)
            self.assertLessEqual(
                len(game._friendly_npc_motions),
                len(tuple(game.iter_friendly_npcs())),
            )

        game.reset_friendly_npc_runtime()
        self.assertEqual(game._friendly_npc_motions, {})


if __name__ == "__main__":
    unittest.main()
