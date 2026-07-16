from __future__ import annotations

import copy
import os
import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

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
from arch_rogue.models import IdleNpc, Tile
from arch_rogue.population import PopulationMixin


def _room_contains(room, x: float, y: float) -> bool:
    return room.x <= x < room.x + room.w and room.y <= y < room.y + room.h


class _FlavorPopulationHarness(PopulationMixin):
    def __init__(self, dungeon: Dungeon) -> None:
        self.dungeon = dungeon
        self.idle_npcs = []
        self.enemies: list[SimpleNamespace] = []
        self.items: list[SimpleNamespace] = []
        self.traps: list[SimpleNamespace] = []
        self.shrines: list[SimpleNamespace] = []
        self.secrets: list[SimpleNamespace] = []
        self.shopkeepers: list[SimpleNamespace] = []
        self.story_guests: list[SimpleNamespace] = []
        self.familiars: list[SimpleNamespace] = []
        self.player: SimpleNamespace | None = None
        self.rng = random.Random(0)


class FlavorRoomTests(unittest.TestCase):
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

    def test_flavor_population_does_not_advance_shared_rng(self) -> None:
        for seed in (40, 42):
            dungeon = Dungeon(random.Random(seed), guest_room=True)
            harness = _FlavorPopulationHarness(dungeon)
            before = harness.rng.getstate()
            flavor_rooms = [
                room
                for room in dungeon.special_rooms
                if room.kind in (BAR_ROOM_KIND, GARDEN_ROOM_KIND)
            ]
            self.assertTrue(flavor_rooms)
            for special in flavor_rooms:
                handler = harness._special_room_handlers()[special.kind]
                handler(special, dungeon.rooms[special.room_index])
            self.assertEqual(harness.rng.getstate(), before)

    def test_frog_reconciliation_does_not_add_optional_wanderer(self) -> None:
        seed = None
        for candidate in range(1, 1000):
            dungeon = Dungeon(random.Random(candidate), guest_room=True)
            special = dungeon.special_room_for_kind(GARDEN_ROOM_KIND)
            if special is None:
                continue
            roll = _FlavorPopulationHarness(dungeon)._flavor_room_rng(
                special, salt=0x6A6
            )
            if roll.random() < 0.50:
                seed = candidate
                break
        self.assertIsNotNone(seed)
        assert seed is not None

        restored_dungeon = Dungeon(random.Random(seed), guest_room=True)
        restored = _FlavorPopulationHarness(restored_dungeon)
        restored._reconcile_garden_frogs()
        self.assertEqual(
            [npc.kind for npc in restored.idle_npcs],
            ["garden_frog", "garden_frog"],
        )

        fresh_dungeon = Dungeon(random.Random(seed), guest_room=True)
        fresh_special = fresh_dungeon.special_room_for_kind(GARDEN_ROOM_KIND)
        assert fresh_special is not None
        fresh = _FlavorPopulationHarness(fresh_dungeon)
        fresh._populate_garden_special_room(
            fresh_special, fresh_dungeon.rooms[fresh_special.room_index]
        )
        self.assertEqual(
            sum(npc.kind == "garden" for npc in fresh.idle_npcs), 1
        )
        self.assertEqual(
            sum(npc.kind == "garden_frog" for npc in fresh.idle_npcs), 2
        )

    def test_idle_npcs_spawn_in_flavor_rooms_and_are_non_interactable(self) -> None:
        game = self._make_game_with_flavor_room()
        try:
            bar = game.dungeon.special_room_for_kind(BAR_ROOM_KIND)
            garden = game.dungeon.special_room_for_kind(GARDEN_ROOM_KIND)
            self.assertIsNotNone(bar)
            self.assertIsNotNone(garden)
            assert bar is not None and garden is not None

            bar_room = game.dungeon.rooms[bar.room_index]
            garden_room = game.dungeon.rooms[garden.room_index]
            bar_npcs = [
                npc for npc in game.idle_npcs if _room_contains(bar_room, npc.x, npc.y)
            ]
            garden_npcs = [
                npc
                for npc in game.idle_npcs
                if _room_contains(garden_room, npc.x, npc.y)
            ]
            self.assertLessEqual(len(bar_npcs), 1)
            self.assertTrue(all(npc.kind == "bar" for npc in bar_npcs))
            frogs = [npc for npc in garden_npcs if npc.kind == "garden_frog"]
            wanderers = [npc for npc in garden_npcs if npc.kind == "garden"]
            self.assertEqual(len(frogs), 2)
            self.assertEqual(len({frog.name for frog in frogs}), 2)
            self.assertTrue(all(frog.role == "Garden Dancer" for frog in frogs))
            self.assertLessEqual(len(wanderers), 1)

            # Idle NPCs are not shopkeepers or story guests and expose no
            # interaction surface — the player cannot talk to or trade with them.
            for room, npc in [
                *((bar_room, npc) for npc in bar_npcs),
                *((garden_room, npc) for npc in garden_npcs),
            ]:
                self.assertFalse(
                    any(_room_contains(room, k.x, k.y) for k in game.shopkeepers)
                )
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

    def test_optional_humanoid_spawn_rate_is_around_50_percent(self) -> None:
        spawned = {BAR_ROOM_KIND: 0, GARDEN_ROOM_KIND: 0}
        rooms_found = {BAR_ROOM_KIND: 0, GARDEN_ROOM_KIND: 0}
        for seed in range(200, 600):
            dungeon = Dungeon(random.Random(seed), guest_room=True)
            harness = _FlavorPopulationHarness(dungeon)
            for special in dungeon.special_rooms:
                if special.kind not in (BAR_ROOM_KIND, GARDEN_ROOM_KIND):
                    continue
                rooms_found[special.kind] += 1
                room = dungeon.rooms[special.room_index]
                handler = harness._special_room_handlers()[special.kind]
                handler(special, room)
                room_npcs = [
                    npc
                    for npc in harness.idle_npcs
                    if _room_contains(room, npc.x, npc.y)
                ]
                spawned[special.kind] += any(
                    npc.kind == special.kind for npc in room_npcs
                )
                if special.kind == GARDEN_ROOM_KIND:
                    frogs = [
                        npc for npc in room_npcs if npc.kind == "garden_frog"
                    ]
                    self.assertEqual(len(frogs), 2)
                    self.assertEqual(len({frog.name for frog in frogs}), 2)
                    self.assertIsNotNone(special.anchor("garden_frog_0"))
                    self.assertIsNotNone(special.anchor("garden_frog_1"))

                populated = [
                    (npc.kind, npc.name, npc.role, npc.x, npc.y)
                    for npc in harness.idle_npcs
                ]
                handler(special, room)
                self.assertEqual(
                    [
                        (npc.kind, npc.name, npc.role, npc.x, npc.y)
                        for npc in harness.idle_npcs
                    ],
                    populated,
                )

        for kind in (BAR_ROOM_KIND, GARDEN_ROOM_KIND):
            self.assertGreater(
                rooms_found[kind], 30, f"expected enough {kind} rooms to sample"
            )
            ratio = spawned[kind] / rooms_found[kind]
            self.assertGreater(
                ratio, 0.30, f"{kind} npc spawn ratio {ratio:.2f} too low"
            )
            self.assertLess(
                ratio, 0.70, f"{kind} npc spawn ratio {ratio:.2f} too high"
            )

    def test_garden_frogs_choose_clear_deterministic_spawn_tiles(self) -> None:
        garden_seed = next(
            seed
            for seed in range(1, 500)
            if Dungeon(random.Random(seed), guest_room=True).special_room_for_kind(
                GARDEN_ROOM_KIND
            )
            is not None
        )

        def populate() -> tuple[list[tuple[str, float, float]], set[tuple[int, int]]]:
            dungeon = Dungeon(random.Random(garden_seed), guest_room=True)
            special = dungeon.special_room_for_kind(GARDEN_ROOM_KIND)
            assert special is not None
            room = dungeon.rooms[special.room_index]
            blocker_tiles = [
                (x, y)
                for x in range(room.x + 1, room.x + room.w - 1)
                for y in range(room.y + 1, room.y + room.h - 1)
            ][:10]
            self.assertEqual(len(blocker_tiles), 10)
            occupied = set(blocker_tiles)
            blockers = [
                SimpleNamespace(x=x + 0.5, y=y + 0.5)
                for x, y in blocker_tiles
            ]
            harness = _FlavorPopulationHarness(dungeon)
            harness.enemies = [blockers[0]]
            harness.items = [blockers[1]]
            harness.traps = [blockers[2]]
            harness.shrines = [blockers[3]]
            harness.secrets = [blockers[4]]
            harness.shopkeepers = [blockers[5]]
            harness.story_guests = [blockers[6]]
            harness.familiars = [blockers[7]]
            harness.player = blockers[8]
            harness.idle_npcs = [
                IdleNpc(
                    blockers[9].x,
                    blockers[9].y,
                    kind="garden",
                    name="Existing Wanderer",
                    role="Wanderer",
                )
            ]
            harness._populate_garden_special_room(special, room)
            frogs = [
                (npc.name, npc.x, npc.y)
                for npc in harness.idle_npcs
                if npc.kind == "garden_frog"
            ]
            self.assertEqual(len(frogs), 2)
            self.assertTrue(
                all((int(x), int(y)) not in occupied for _name, x, y in frogs)
            )
            return frogs, occupied

        first, _occupied = populate()
        second, _occupied = populate()
        self.assertEqual(first, second)

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
            game = self._make_game_with_flavor_room(tmpdir=tmpdir)
            self.assertEqual(
                sum(npc.kind == "garden_frog" for npc in game.idle_npcs), 2
            )
            self.assertTrue(
                {npc.kind for npc in game.idle_npcs}.issubset(
                    {"bar", "garden", "garden_frog"}
                )
            )
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
                self.assertEqual(restored.role, original.role)
                self.assertEqual(restored.color, original.color)

    def test_pre_frog_garden_save_backfills_exactly_two_frogs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self._make_game_with_flavor_room(tmpdir=tmpdir)
            data = copy.deepcopy(game.serialize_run_state())
            data["idle_npcs"] = [
                npc
                for npc in data["idle_npcs"]
                if npc.get("kind") != "garden_frog"
            ]
            garden_data = next(
                room
                for room in data["dungeon"]["special_rooms"]
                if room.get("kind") == GARDEN_ROOM_KIND
            )
            frog_anchor_tiles = [
                garden_data["anchor_points"].pop(key)
                for key in ("garden_frog_0", "garden_frog_1")
            ]
            garden_data["reserved_tiles"] = [
                tile
                for tile in garden_data["reserved_tiles"]
                if tile not in frog_anchor_tiles
            ]

            loaded = Game(
                screen_size=(820, 540),
                headless=True,
                save_path=Path(tmpdir) / "pre-frog.json",
            )
            loaded.options_path = Path(tmpdir) / "pre-frog-options.json"
            loaded.restore_run_state(data)
            frogs = [
                npc for npc in loaded.idle_npcs if npc.kind == "garden_frog"
            ]
            self.assertEqual(len(frogs), 2)
            self.assertEqual(len({frog.name for frog in frogs}), 2)
            before = [
                (npc.kind, npc.name, npc.role, npc.color, npc.x, npc.y)
                for npc in loaded.idle_npcs
            ]
            loaded._reconcile_garden_frogs()
            self.assertEqual(
                [
                    (npc.kind, npc.name, npc.role, npc.color, npc.x, npc.y)
                    for npc in loaded.idle_npcs
                ],
                before,
            )

    def test_garden_reconciliation_repairs_duplicates_and_stale_anchors(self) -> None:
        game = self._make_game_with_flavor_room()
        try:
            special = game.dungeon.special_room_for_kind(GARDEN_ROOM_KIND)
            assert special is not None
            frogs = [npc for npc in game.idle_npcs if npc.kind == "garden_frog"]
            self.assertEqual(len(frogs), 2)
            expected_names = {frog.name for frog in frogs}
            retained, removed = frogs
            old_anchor = special.anchor("garden_frog_1")
            self.assertIsNotNone(old_anchor)
            game.idle_npcs.remove(removed)
            game.idle_npcs.extend(
                [
                    IdleNpc(
                        removed.x,
                        removed.y,
                        kind="garden_frog",
                        name=retained.name,
                        role="Garden Dancer",
                    ),
                    IdleNpc(
                        removed.x,
                        removed.y,
                        kind="garden_frog",
                        name="Unknown Frog",
                        role="Garden Dancer",
                    ),
                ]
            )

            game._reconcile_garden_frogs()
            repaired = [
                npc for npc in game.idle_npcs if npc.kind == "garden_frog"
            ]
            self.assertEqual(len(repaired), 2)
            self.assertEqual({frog.name for frog in repaired}, expected_names)
            self.assertTrue(any(frog is retained for frog in repaired))
            new_anchor = special.anchor("garden_frog_1")
            self.assertIsNotNone(new_anchor)
            self.assertNotEqual(new_anchor, old_anchor)
            referenced = {
                tuple(anchor[:2]) for anchor in special.anchor_points.values()
            }
            assert old_anchor is not None
            if old_anchor not in referenced:
                self.assertNotIn(list(old_anchor), special.reserved_tiles)

            before = (
                [(id(npc), npc.name, npc.x, npc.y) for npc in repaired],
                copy.deepcopy(special.anchor_points),
                copy.deepcopy(special.reserved_tiles),
            )
            game._reconcile_garden_frogs()
            self.assertEqual(
                (
                    [
                        (id(npc), npc.name, npc.x, npc.y)
                        for npc in game.idle_npcs
                        if npc.kind == "garden_frog"
                    ],
                    special.anchor_points,
                    special.reserved_tiles,
                ),
                before,
            )
        finally:
            tmp = getattr(game, "_flavor_tmpdir", None)
            if tmp is not None:
                tmp.cleanup()

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
            # Explicitly render on a frog tile so the dedicated asset path runs.
            frog = next(npc for npc in game.idle_npcs if npc.kind == "garden_frog")
            self.assertTrue(
                game.sprites.garden_frog_visual(
                    game.elapsed, dancing=True, clip_progress=0.0
                ).is_asset
            )
            game.player.x = frog.x
            game.player.y = frog.y
            game.update_revealed_tiles()
            game.draw()
        finally:
            tmp = getattr(game, "_flavor_tmpdir", None)
            if tmp is not None:
                tmp.cleanup()

    def test_old_save_without_idle_npcs_or_flavor_rooms_loads(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self._make_game_with_flavor_room(tmpdir=tmpdir)
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

    def _make_game_with_flavor_room(self, tmpdir: str | None = None) -> Game:
        owns_tmp = tmpdir is None
        tmp: tempfile.TemporaryDirectory | None = None
        if owns_tmp:
            tmp = tempfile.TemporaryDirectory()
            tmpdir = tmp.name
        assert tmpdir is not None
        seed = 3001
        try:
            game = Game(
                screen_size=(820, 540),
                headless=True,
                save_path=Path(tmpdir) / f"flavor-{seed}.json",
            )
            game.options_path = Path(tmpdir) / f"opt-{seed}.json"
            game.rng.seed(seed)
            game.restart(ARCHETYPES[2])
            self.assertIsNotNone(game.dungeon.special_room_for_kind(BAR_ROOM_KIND))
            self.assertIsNotNone(game.dungeon.special_room_for_kind(GARDEN_ROOM_KIND))
            self.assertEqual(
                sum(npc.kind == "garden_frog" for npc in game.idle_npcs), 2
            )
            self.assertTrue(
                {npc.kind for npc in game.idle_npcs}.issubset(
                    {"bar", "garden", "garden_frog"}
                )
            )
            if owns_tmp and tmp is not None:
                game._flavor_tmpdir = tmp  # type: ignore[attr-defined]
            return game
        except Exception:
            if tmp is not None:
                tmp.cleanup()
            raise


if __name__ == "__main__":
    unittest.main()
