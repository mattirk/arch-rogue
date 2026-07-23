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
            patrons = [npc for npc in bar_npcs if npc.kind == "bar"]
            dancers = [npc for npc in bar_npcs if npc.kind == "bar_dancer"]
            self.assertLessEqual(len(patrons), 1)
            self.assertEqual(len(dancers), 1)
            self.assertEqual(dancers[0].name, "Bar Dancer")
            self.assertEqual(dancers[0].role, "Tavern Reveler")
            dancer_anchor = bar.anchor("bar_dancer")
            self.assertIsNotNone(dancer_anchor)
            assert dancer_anchor is not None
            dancer_motion = game.friendly_npc_motion(dancers[0])
            self.assertEqual(
                (dancer_motion.home_x, dancer_motion.home_y),
                (dancer_anchor[0] + 0.5, dancer_anchor[1] + 0.5),
            )
            self.assertEqual(
                len({(int(npc.x), int(npc.y)) for npc in bar_npcs}),
                len(bar_npcs),
            )
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
                if special.kind == BAR_ROOM_KIND:
                    dancers = [
                        npc for npc in room_npcs if npc.kind == "bar_dancer"
                    ]
                    self.assertEqual(len(dancers), 1)
                    self.assertIsNotNone(special.anchor("bar_dancer"))
                    patrons = [npc for npc in room_npcs if npc.kind == "bar"]
                    self.assertLessEqual(len(patrons), 1)
                    self.assertEqual(
                        len({(int(npc.x), int(npc.y)) for npc in room_npcs}),
                        len(room_npcs),
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
                sum(npc.kind == "bar_dancer" for npc in game.idle_npcs), 1
            )
            self.assertEqual(
                sum(npc.kind == "garden_frog" for npc in game.idle_npcs), 2
            )
            self.assertTrue(
                {npc.kind for npc in game.idle_npcs}.issubset(
                    {"bar", "bar_dancer", "garden", "garden_frog"}
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

    def test_pre_dancer_bar_save_backfills_without_adding_optional_patron(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self._make_game_with_flavor_room(tmpdir=tmpdir, seed=4)
            source_bar = game.dungeon.special_room_for_kind(BAR_ROOM_KIND)
            assert source_bar is not None
            patron_roll = game._flavor_room_rng(source_bar, salt=0xB4B).random()
            self.assertLess(patron_roll, 0.50)
            self.assertEqual(
                sum(npc.kind == "bar" for npc in game.idle_npcs), 1
            )
            data = copy.deepcopy(game.serialize_run_state())
            data["idle_npcs"] = [
                npc
                for npc in data["idle_npcs"]
                if npc.get("kind") not in {"bar", "bar_dancer"}
            ]
            bar_data = next(
                room
                for room in data["dungeon"]["special_rooms"]
                if room.get("kind") == BAR_ROOM_KIND
            )
            dancer_anchor_tile = bar_data["anchor_points"].pop("bar_dancer")
            bar_data["reserved_tiles"] = [
                tile
                for tile in bar_data["reserved_tiles"]
                if tile != dancer_anchor_tile
            ]

            loaded = Game(
                screen_size=(820, 540),
                headless=True,
                save_path=Path(tmpdir) / "pre-dancer.json",
            )
            loaded.options_path = Path(tmpdir) / "pre-dancer-options.json"
            loaded.restore_run_state(data)
            dancers = [
                npc for npc in loaded.idle_npcs if npc.kind == "bar_dancer"
            ]
            self.assertEqual(len(dancers), 1)
            self.assertEqual(dancers[0].name, "Bar Dancer")
            self.assertEqual(dancers[0].role, "Tavern Reveler")
            self.assertEqual(dancers[0].color, (224, 126, 72))
            self.assertFalse(any(npc.kind == "bar" for npc in loaded.idle_npcs))
            bar = loaded.dungeon.special_room_for_kind(BAR_ROOM_KIND)
            assert bar is not None
            self.assertIsNotNone(bar.anchor("bar_dancer"))

            before = [
                (id(npc), npc.kind, npc.name, npc.x, npc.y)
                for npc in loaded.idle_npcs
            ]
            loaded._reconcile_bar_dancers()
            self.assertEqual(
                [
                    (id(npc), npc.kind, npc.name, npc.x, npc.y)
                    for npc in loaded.idle_npcs
                ],
                before,
            )

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

    def test_bar_dancer_reconciliation_preserves_moved_actor_and_deduplicates(self) -> None:
        game = self._make_game_with_flavor_room()
        try:
            special = game.dungeon.special_room_for_kind(BAR_ROOM_KIND)
            assert special is not None
            room = game.dungeon.rooms[special.room_index]
            dancers = [
                npc
                for npc in game.idle_npcs
                if npc.kind == "bar_dancer"
                and _room_contains(room, npc.x, npc.y)
            ]
            self.assertEqual(len(dancers), 1)
            retained = dancers[0]
            old_anchor = special.anchor("bar_dancer")
            self.assertIsNotNone(old_anchor)
            assert old_anchor is not None
            occupied = {
                (int(npc.x), int(npc.y))
                for npc in game.idle_npcs
                if npc is not retained
            }
            moved_tile = next(
                (x, y)
                for x in range(room.x + 1, room.x + room.w - 1)
                for y in range(room.y + 1, room.y + room.h - 1)
                if (x, y) != old_anchor
                and (x, y) not in occupied
                and not game.dungeon.blocked_for_radius(x + 0.5, y + 0.5, 0.27)
            )
            retained.x = moved_tile[0] + 0.5
            retained.y = moved_tile[1] + 0.5
            game.idle_npcs.append(
                IdleNpc(
                    old_anchor[0] + 0.5,
                    old_anchor[1] + 0.5,
                    kind="bar_dancer",
                    name="Duplicate Dancer",
                    role="Duplicate",
                )
            )
            special.anchor_points.pop("bar_dancer")
            special.reserved_tiles = [
                tile for tile in special.reserved_tiles if tuple(tile[:2]) != old_anchor
            ]

            game._reconcile_bar_dancers()
            repaired = [
                npc
                for npc in game.idle_npcs
                if npc.kind == "bar_dancer"
                and _room_contains(room, npc.x, npc.y)
            ]
            self.assertEqual(repaired, [retained])
            self.assertEqual(
                (retained.x, retained.y),
                (moved_tile[0] + 0.5, moved_tile[1] + 0.5),
            )
            self.assertEqual(special.anchor("bar_dancer"), moved_tile)

            before = (
                [(id(npc), npc.name, npc.x, npc.y) for npc in repaired],
                copy.deepcopy(special.anchor_points),
                copy.deepcopy(special.reserved_tiles),
            )
            game._reconcile_bar_dancers()
            self.assertEqual(
                (
                    [
                        (id(npc), npc.name, npc.x, npc.y)
                        for npc in game.idle_npcs
                        if npc.kind == "bar_dancer"
                        and _room_contains(room, npc.x, npc.y)
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
            # Explicitly render both dedicated flavor-actor asset branches.
            dancer = next(npc for npc in game.idle_npcs if npc.kind == "bar_dancer")
            dancer_frame = game.sprites.bar_dancer_visual(
                game.elapsed, dancing=True, clip_progress=0.0
            )
            self.assertTrue(dancer_frame.is_asset)
            self.assertEqual(dancer_frame.key[1], "bar_dancer")
            game.player.x = dancer.x
            game.player.y = dancer.y
            game.update_revealed_tiles()
            game.draw()

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

    def test_garden_heal_glow_renders_without_crashing(self) -> None:
        # 4.2: the greenish garden healing aura is drawn by
        # ``draw_garden_heal_glow`` when ``garden_heal_glow`` is active. Verify
        # a full frame render with the glow timer set does not crash and
        # leaves the glow timer decayed by the visual-effects step.
        game = self._make_game_with_flavor_room()
        try:
            special = game.dungeon.special_room_for_kind(GARDEN_ROOM_KIND)
            assert special is not None
            room = game.dungeon.rooms[special.room_index]
            game.player.x = room.x + room.w / 2
            game.player.y = room.y + room.h / 2
            game.update_revealed_tiles()
            game.garden_heal_glow = 0.9
            game.garden_heal_glow_duration = 0.9
            # Rendering with the glow active must not crash; the aura is drawn
            # by ``draw_garden_heal_glow`` inside ``draw_player``.
            game.draw()
            # The decay happens in update_visual_effects (the game-loop update
            # step), not during draw. Exercise it directly to confirm the
            # timer decays toward zero.
            glow_before = game.garden_heal_glow
            game.update_visual_effects(0.2)
            self.assertLess(game.garden_heal_glow, glow_before)
            self.assertGreaterEqual(game.garden_heal_glow, 0.0)
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

    def _make_game_with_flavor_room(
        self, tmpdir: str | None = None, *, seed: int = 3001
    ) -> Game:
        owns_tmp = tmpdir is None
        tmp: tempfile.TemporaryDirectory | None = None
        if owns_tmp:
            tmp = tempfile.TemporaryDirectory()
            tmpdir = tmp.name
        assert tmpdir is not None
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
                sum(npc.kind == "bar_dancer" for npc in game.idle_npcs), 1
            )
            self.assertEqual(
                sum(npc.kind == "garden_frog" for npc in game.idle_npcs), 2
            )
            self.assertTrue(
                {npc.kind for npc in game.idle_npcs}.issubset(
                    {"bar", "bar_dancer", "garden", "garden_frog"}
                )
            )
            if owns_tmp and tmp is not None:
                game._flavor_tmpdir = tmp  # type: ignore[attr-defined]
            return game
        except Exception:
            if tmp is not None:
                tmp.cleanup()
            raise

    def test_bar_room_heals_slower_than_garden_and_saps_stamina(self) -> None:
        # 4.7.12: the bar refuge pours at half the garden's pace and quickly
        # drains the drinker's stamina to zero while they linger. No greenish
        # glow — that aura belongs to the garden.
        game = self._make_game_with_flavor_room()
        try:
            special = game.dungeon.special_room_for_kind(BAR_ROOM_KIND)
            assert special is not None
            room = game.dungeon.rooms[special.room_index]
            cx, cy = room.center
            game.dungeon.tiles[cx][cy] = Tile.FLOOR
            game.player.x = cx + 0.5
            game.player.y = cy + 0.5
            game.player.hp = max(1, game.player.max_hp - 24)
            hp_before = game.player.hp
            game.player.stamina = game.player.max_stamina
            game.player.garden_heal_accumulator = 0.0
            game.garden_heal_glow = 0.0
            game.floaters.clear()

            # A quick sip (one second) saps stamina hard but has not yet
            # earned a heal tick — the pour is slow.
            game.update_player(0.6)
            game.update_player(0.5)
            self.assertEqual(game.player.hp, hp_before)
            self.assertLess(
                game.player.stamina, game.player.max_stamina * 0.25
            )

            # Lingering a moment longer empties the stamina bar outright.
            game.update_player(0.8)
            self.assertEqual(game.player.stamina, 0.0)

            # Crossing the five-second tick: one heal lands at half the
            # garden's strength, with an amber floater and no garden glow.
            game.update_player(2.0)
            game.update_player(2.5)
            self.assertGreater(game.player.hp, hp_before)
            self.assertEqual(
                game.player.hp - hp_before,
                max(1, game.player.max_hp // 50 + 1),
            )
            self.assertEqual(game.garden_heal_glow, 0.0)
            bar_floaters = [
                f for f in game.floaters if str(f.text).startswith("Bar +")
            ]
            self.assertEqual(len(bar_floaters), 1)
        finally:
            tmp = getattr(game, "_flavor_tmpdir", None)
            if tmp is not None:
                tmp.cleanup()

    def test_garden_room_slowly_heals_player_and_emits_greenish_glow(self) -> None:
        # 4.2 (retuned 4.7.12): standing inside an overgrown garden flavor
        # room mends the player a little (one +HP tick per five seconds) and
        # refreshes a greenish aura timer the renderer fades out. The heal
        # only ticks while HP is actually missing and only while standing
        # inside the garden.
        game = self._make_game_with_flavor_room()
        try:
            special = game.dungeon.special_room_for_kind(GARDEN_ROOM_KIND)
            assert special is not None
            room = game.dungeon.rooms[special.room_index]
            cx, cy = room.center
            # Ensure the garden center is walkable and park the player there.
            game.dungeon.tiles[cx][cy] = Tile.FLOOR
            game.player.x = cx + 0.5
            game.player.y = cy + 0.5
            game.player.hp = max(1, game.player.max_hp - 24)
            hp_before = game.player.hp
            game.player.garden_heal_accumulator = 0.0
            game.garden_heal_glow = 0.0
            game.floaters.clear()

            # Under the tick threshold: accumulator banks time but no tick yet.
            game.update_player(2.5)
            self.assertEqual(game.player.hp, hp_before)
            self.assertEqual(game.garden_heal_glow, 0.0)

            # Cross the five-second tick threshold: HP rises, glow activates,
            # and a "Garden +N" floater is emitted.
            game.update_player(2.6)
            self.assertGreater(game.player.hp, hp_before)
            self.assertGreater(game.garden_heal_glow, 0.0)
            self.assertGreater(game.garden_heal_glow_duration, 0.0)
            garden_floaters = [
                f for f in game.floaters if str(f.text).startswith("Garden +")
            ]
            self.assertEqual(len(garden_floaters), 1)
            self.assertEqual(garden_floaters[0].color, (130, 220, 150))

            # Step out of the garden: accumulator resets and no further heal.
            outside_x = game.player.x + room.w + 2
            game.dungeon.tiles[int(outside_x)][int(game.player.y)] = Tile.FLOOR
            game.player.x = outside_x
            hp_in_garden = game.player.hp
            game.player.garden_heal_accumulator = 0.0
            game.update_player(1.6)
            self.assertEqual(game.player.hp, hp_in_garden)
            self.assertEqual(game.player.garden_heal_accumulator, 0.0)

            # At full HP, standing in the garden does nothing (no wasted glow).
            game.player.x = cx + 0.5
            game.player.y = cy + 0.5
            game.player.hp = game.player.max_hp
            game.player.garden_heal_accumulator = 0.0
            game.garden_heal_glow = 0.0
            game.update_player(1.6)
            self.assertEqual(game.player.hp, game.player.max_hp)
            self.assertEqual(game.garden_heal_glow, 0.0)
        finally:
            tmp = getattr(game, "_flavor_tmpdir", None)
            if tmp is not None:
                tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
