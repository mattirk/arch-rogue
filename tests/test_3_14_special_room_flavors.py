from __future__ import annotations

import copy
import os
import random
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys_path_root = Path(__file__).resolve().parents[1] / "src"
import sys

sys.path.insert(0, str(sys_path_root))

from arch_rogue.content import ARCHETYPES
from arch_rogue.dungeon import (
    BAR_ROOM_KIND,
    GARDEN_ROOM_KIND,
    QUEST_ROOM_KIND,
    SHOP_ROOM_KIND,
    SPECIAL_ROOM_DEFINITIONS,
    Dungeon,
)
from arch_rogue.game import Game
from arch_rogue.models import Tile


def _room_contains(room, x: float, y: float) -> bool:
    return room.x <= x < room.x + room.w and room.y <= y < room.y + room.h


class SpecialRoomFlavor314Tests(unittest.TestCase):
    def test_bar_and_garden_definitions_exist_and_are_sealed_flavor_rooms(self) -> None:
        for kind in (BAR_ROOM_KIND, GARDEN_ROOM_KIND):
            definition = SPECIAL_ROOM_DEFINITIONS[kind]
            self.assertEqual(definition.kind, kind)
            # Sealed with doors so the distinct interior wall art always renders.
            self.assertEqual(definition.door_policy, "sealed")
            # Appearance-only: hostiles are NOT cleared (not a safe refuge).
            self.assertEqual(definition.spawn_policy, "normal")
            self.assertIn("flavor", definition.tags)
            self.assertIn("refuge", definition.tags)

    def test_flavor_rooms_spawn_around_50_percent_across_depths(self) -> None:
        # Across many seeds and depths, each flavor kind should appear close to
        # 50% of the time. They never displace the shop/quest room or the first
        # /last room, and never collide with another special room.
        bar_count = 0
        garden_count = 0
        total = 0
        for seed in range(40, 240):
            dungeon = Dungeon(random.Random(seed), guest_room=True)
            total += 1
            kinds = {room.kind for room in dungeon.special_rooms}
            if BAR_ROOM_KIND in kinds:
                bar_count += 1
            if GARDEN_ROOM_KIND in kinds:
                garden_count += 1
            room_indexes = [room.room_index for room in dungeon.special_rooms]
            # No two special rooms share a room, and none sit on the entrance or
            # stairs room.
            self.assertEqual(len(room_indexes), len(set(room_indexes)))
            self.assertNotIn(0, room_indexes)
            self.assertNotIn(len(dungeon.rooms) - 1, room_indexes)
            # The guest room is always present when requested.
            self.assertIn(QUEST_ROOM_KIND, kinds)
        ratio_bar = bar_count / total
        ratio_garden = garden_count / total
        self.assertGreater(ratio_bar, 0.30, f"bar ratio {ratio_bar:.2f} too low")
        self.assertLess(ratio_bar, 0.70, f"bar ratio {ratio_bar:.2f} too high")
        self.assertGreater(
            ratio_garden, 0.30, f"garden ratio {ratio_garden:.2f} too low"
        )
        self.assertLess(ratio_garden, 0.70, f"garden ratio {ratio_garden:.2f} too high")

    def test_flavor_room_planning_is_deterministic(self) -> None:
        first = Dungeon(random.Random(123), guest_room=True)
        second = Dungeon(random.Random(123), guest_room=True)
        self.assertEqual(
            [room.to_dict() for room in first.special_rooms],
            [room.to_dict() for room in second.special_rooms],
        )

    def test_flavor_rooms_do_not_disturb_population_determinism(self) -> None:
        # The flavor-room rolls use a layout-seeded local RNG, so the shared
        # `self.rng` stream (and thus enemy/item population) must be identical to
        # a dungeon without flavor rooms. We approximate by checking enemy and
        # item counts are stable across repeated identical seeds.
        counts_a = self._population_counts(seed=77)
        counts_b = self._population_counts(seed=77)
        self.assertEqual(counts_a, counts_b)

    def _population_counts(self, seed: int) -> tuple[int, int, int]:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = Game(
                screen_size=(820, 540),
                headless=True,
                save_path=Path(tmpdir) / f"pop-{seed}.json",
            )
            game.options_path = Path(tmpdir) / f"opt-{seed}.json"
            game.rng.seed(seed)
            game.restart(ARCHETYPES[1])
            return (
                len(game.enemies),
                len(game.items),
                len(game.idle_npcs),
            )

    def test_idle_npc_spawns_in_flavor_room_and_is_non_interactable(self) -> None:
        game = self._make_game_with_flavor_room()
        try:
            bar = game.dungeon.special_room_for_kind(BAR_ROOM_KIND)
            garden = game.dungeon.special_room_for_kind(GARDEN_ROOM_KIND)
            chosen = bar or garden
            self.assertIsNotNone(chosen)
            assert chosen is not None
            room = game.dungeon.rooms[chosen.room_index]
            # The flavor room hosts at most one idle NPC, placed inside the room.
            npcs_in_room = [
                npc for npc in game.idle_npcs if _room_contains(room, npc.x, npc.y)
            ]
            self.assertLessEqual(len(npcs_in_room), 1)
            if npcs_in_room:
                npc = npcs_in_room[0]
                self.assertIn(npc.kind, (BAR_ROOM_KIND, GARDEN_ROOM_KIND))
                # Idle NPCs are not shopkeepers or story guests and expose no
                # interaction surface — the player cannot talk to or trade with them.
                self.assertFalse(
                    any(_room_contains(room, k.x, k.y) for k in game.shopkeepers)
                )
                # No interaction hint references idle NPCs.
                game.player.x = npc.x
                game.player.y = npc.y
                hint = game.current_interaction_hint()
                if hint is not None:
                    self.assertNotIn("idle", hint[1].lower())
                    self.assertNotIn(npc.name, hint[1])
        finally:
            tmp = getattr(game, "_flavor_tmpdir", None)
            if tmp is not None:
                tmp.cleanup()

    def test_idle_npc_spawn_rate_is_around_50_percent(self) -> None:
        spawned = 0
        rooms_found = 0
        for seed in range(200, 600):
            with tempfile.TemporaryDirectory() as tmpdir:
                game = Game(
                    screen_size=(820, 540),
                    headless=True,
                    save_path=Path(tmpdir) / f"npc-{seed}.json",
                )
                game.options_path = Path(tmpdir) / f"opt-{seed}.json"
                game.rng.seed(seed)
                game.restart(ARCHETYPES[0])
                for kind in (BAR_ROOM_KIND, GARDEN_ROOM_KIND):
                    special = game.dungeon.special_room_for_kind(kind)
                    if special is None:
                        continue
                    rooms_found += 1
                    room = game.dungeon.rooms[special.room_index]
                    if any(
                        _room_contains(room, npc.x, npc.y) for npc in game.idle_npcs
                    ):
                        spawned += 1
        self.assertGreater(rooms_found, 60, "expected enough flavor rooms to sample")
        ratio = spawned / rooms_found
        self.assertGreater(ratio, 0.30, f"npc spawn ratio {ratio:.2f} too low")
        self.assertLess(ratio, 0.70, f"npc spawn ratio {ratio:.2f} too high")

    def test_flavor_floor_and_wall_render_helpers_detect_room_tiles(self) -> None:
        game = self._make_game_with_flavor_room()
        try:
            bar = game.dungeon.special_room_for_kind(BAR_ROOM_KIND)
            garden = game.dungeon.special_room_for_kind(GARDEN_ROOM_KIND)
            for special, detector in (
                (bar, game.is_bar_tile),
                (garden, game.is_garden_tile),
            ):
                if special is None:
                    continue
                room = game.dungeon.rooms[special.room_index]
                interior_hits = 0
                for x in range(room.x + 1, room.x + room.w - 1):
                    for y in range(room.y + 1, room.y + room.h - 1):
                        if game.dungeon.tiles[x][y] == Tile.FLOOR and detector(x, y):
                            interior_hits += 1
                self.assertGreater(interior_hits, 0)
                # The detector must not flag tiles outside the room.
                self.assertFalse(detector(room.x - 1, room.y - 1))
            # Special-room wall face detection returns a kind:side style for at least
            # one perimeter wall of each present flavor room.
            for special in (bar, garden):
                if special is None:
                    continue
                room = game.dungeon.rooms[special.room_index]
                found_face = False
                for x in range(room.x - 1, room.x + room.w + 1):
                    for y in range(room.y - 1, room.y + room.h + 1):
                        if not game.dungeon.in_bounds(x, y):
                            continue
                        if game.dungeon.tiles[x][y] != Tile.WALL:
                            continue
                        style = game.special_wall_faces(x, y)
                        if style and style.startswith(f"{special.kind}:"):
                            found_face = True
                            break
                    if found_face:
                        break
                self.assertTrue(found_face, f"no interior wall face for {special.kind}")
        finally:
            tmp = getattr(game, "_flavor_tmpdir", None)
            if tmp is not None:
                tmp.cleanup()

    def test_idle_npcs_serialize_and_restore(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self._make_game_with_flavor_room(tmpdir=tmpdir, max_seeds=400)
            if not game.idle_npcs:
                self.skipTest("no idle npc generated for sampled seed")
            data = copy.deepcopy(game.serialize_run_state())
            self.assertIn("idle_npcs", data)
            self.assertGreater(len(data["idle_npcs"]), 0)

            loaded = Game(
                screen_size=(820, 540),
                headless=True,
                save_path=Path(tmpdir) / "restore.json",
            )
            loaded.options_path = Path(tmpdir) / "restore-opt.json"
            loaded.restore_run_state(data)
            self.assertEqual(len(loaded.idle_npcs), len(game.idle_npcs))
            for original, restored in zip(game.idle_npcs, loaded.idle_npcs):
                self.assertAlmostEqual(restored.x, original.x)
                self.assertAlmostEqual(restored.y, original.y)
                self.assertEqual(restored.kind, original.kind)
                self.assertEqual(restored.name, original.name)

    def test_rendering_a_frame_with_flavor_rooms_does_not_crash(self) -> None:
        # Exercises the new bar/garden floor + wall face + idle NPC render paths
        # end-to-end through the full depth-sorted draw pipeline.
        game = self._make_game_with_flavor_room()
        try:
            # Ensure the player is inside the flavor room so its tiles are visible
            # and the new render paths actually execute.
            for kind in (BAR_ROOM_KIND, GARDEN_ROOM_KIND):
                special = game.dungeon.special_room_for_kind(kind)
                if special is None:
                    continue
                room = game.dungeon.rooms[special.room_index]
                game.player.x = room.x + room.w / 2
                game.player.y = room.y + room.h / 2
                game.update_revealed_tiles()
                game.draw()
                break
            # Also draw with the player on an idle NPC tile to render the NPC.
            if game.idle_npcs:
                npc = game.idle_npcs[0]
                game.player.x = npc.x
                game.player.y = npc.y
                game.update_revealed_tiles()
                game.draw()
        finally:
            tmp = getattr(game, "_flavor_tmpdir", None)
            if tmp is not None:
                tmp.cleanup()

    def test_old_save_without_idle_npcs_or_flavor_rooms_loads(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self._make_game_with_flavor_room(tmpdir=tmpdir, max_seeds=400)
            data = copy.deepcopy(game.serialize_run_state())
            # Simulate a pre-3.14 save: no idle_npcs and no flavor special rooms.
            data.pop("idle_npcs", None)
            data["dungeon"]["special_rooms"] = [
                room
                for room in data["dungeon"].get("special_rooms", [])
                if room.get("kind") in (SHOP_ROOM_KIND, QUEST_ROOM_KIND)
            ]

            loaded = Game(
                screen_size=(820, 540),
                headless=True,
                save_path=Path(tmpdir) / "old.json",
            )
            loaded.options_path = Path(tmpdir) / "old-opt.json"
            loaded.restore_run_state(data)
            self.assertEqual(loaded.idle_npcs, [])
            # Re-populating must not crash and must not duplicate shop/guest state.
            before_keepers = len(loaded.shopkeepers)
            loaded._populate_special_rooms()
            self.assertEqual(len(loaded.shopkeepers), before_keepers)

    # --- helpers --------------------------------------------------------

    def _make_game_with_flavor_room(
        self, tmpdir: str | None = None, max_seeds: int = 300
    ) -> Game:
        owns_tmp = tmpdir is None
        tmp: tempfile.TemporaryDirectory | None = None
        if owns_tmp:
            tmp = tempfile.TemporaryDirectory()
            tmpdir = tmp.name
        assert tmpdir is not None
        base_dir: str = tmpdir
        try:
            for seed in range(3000, 3000 + max_seeds):
                game = Game(
                    screen_size=(820, 540),
                    headless=True,
                    save_path=Path(base_dir) / f"flavor-{seed}.json",
                )
                game.options_path = Path(base_dir) / f"opt-{seed}.json"
                game.rng.seed(seed)
                game.restart(ARCHETYPES[2])
                if (
                    game.dungeon.special_room_for_kind(BAR_ROOM_KIND) is not None
                    or game.dungeon.special_room_for_kind(GARDEN_ROOM_KIND) is not None
                ):
                    if owns_tmp and tmp is not None:
                        # Keep the temp dir alive for the returned game's save path.
                        game._flavor_tmpdir = tmp  # type: ignore[attr-defined]
                    return game
            self.fail("Expected a seed to generate a bar or garden flavor room")
            raise AssertionError
        except Exception:
            if tmp is not None:
                tmp.cleanup()
            raise


if __name__ == "__main__":
    unittest.main()
