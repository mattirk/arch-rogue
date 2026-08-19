# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
#
# AI Provenance & Liability Notice:
# This repository contains code generated, assisted, or refactored by Artificial
# Intelligence models. Provided strictly "AS IS" under Apache 2.0 with no warranty
# of clean IP provenance or non-infringement; downstream users assume all legal
# and financial risk and should perform their own compliance audits.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import math
import random
from collections import deque

from .constants import (
    ACTOR_MOVE_COLLISION_RADIUS,
    SOLID_FURNISHING_COLLISION_INSET,
    SOLID_FURNISHING_COLLISION_OFFSET_X,
    SOLID_FURNISHING_COLLISION_OFFSET_Y,
    STAIR_COLLISION_INSET,
    STAIR_COLLISION_OFFSET_X,
    STAIR_COLLISION_OFFSET_Y,
)
from .models import (
    Room,
    SpecialRoom,
    SpecialRoomDefinition,
    SpecialRoomPlacement,
    Tile,
)

MAP_W = 72
MAP_H = 72
MIN_ROOM_COUNT = 8
MAX_ROOM_COUNT = 14
# Large boss floors reserve the final room as a real arena. The regular room
# generator can produce 6x6 rooms; those are fine for exploration, but a 2x2
# boss plus a sealed entrance needs enough interior tiles for collision-safe
# repositioning and readable combat spacing.
BOSS_ARENA_MIN_W = 10
BOSS_ARENA_MIN_H = 10
BOSS_ARENA_MAX_W = 14
BOSS_ARENA_MAX_H = 13

# Floor-like tiles remain transparent to line-of-sight and projectiles. The
# stair shaft is intentionally excluded from physical walkability below.
_PASSABLE_TILES = (Tile.FLOOR, Tile.STAIRS, Tile.OPEN_DOOR)
_WALKABLE_TILES = (Tile.FLOOR, Tile.OPEN_DOOR)

SHOP_ROOM_KIND = "shop"
QUEST_ROOM_KIND = "quest_room"
LEGACY_QUEST_GUEST_ROOM_KIND = "quest_guest"
# Flavor special rooms (3.14 bar/garden, 4.8.6 lossless-soul hall): sealed
# chambers that roll on every depth via the layout-seeded flavor stream so the
# shared ``self.rng`` sequence — and thus downstream population determinism —
# stays byte-identical to runs without them. ``door_policy="sealed"`` gives
# them a closed perimeter with doors so the distinct interior wall art always
# renders and the room reads as a discovered chamber rather than open dungeon
# floor.
# Bar/garden keep ``spawn_policy="normal"`` (appearance-only, hostiles stay);
# the Lossless Soul hall is ``"safe"`` like the shop/quest rooms because it
# hosts a dialogue NPC and a story moment, not a gauntlet.
BAR_ROOM_KIND = "bar"
GARDEN_ROOM_KIND = "garden"
LOSSLESS_SOUL_ROOM_KIND = "lossless_soul"

# Special-room furnishing anchors whose tiles are physically solid: the soul
# hall's block props and the bar's barrels/standing tables stand on these, so
# every movement probe (players, enemies, NPCs, familiars, spawn scans) treats
# the anchor tile as blocked. LOS and projectiles are unaffected — solidity is
# physical, not visual. Population reserves these anchors;
# ``refresh_solid_furnishing_tiles`` derives the tile set from them after
# every special-room / anchor mutation.
SOLID_FURNISHING_ANCHOR_KEYS = frozenset(
    {
        "soul_mirror",
        "soul_chimes",
        "soul_brazier",
        "soul_reliquary",
        "bar_barrel_1",
        "bar_barrel_2",
        "bar_barrel_3",
        "bar_barrel_4",
        "bar_table_1",
        "bar_table_2",
        "bar_table_3",
        "bar_table_4",
    }
)

# Definition order is load-bearing: it is the placement order, and for kinds
# sharing an RNG stream it fixes which draws they consume. Append new kinds
# after existing ones on the same stream to preserve historical layouts.
SPECIAL_ROOM_DEFINITIONS: dict[str, SpecialRoomDefinition] = {
    SHOP_ROOM_KIND: SpecialRoomDefinition(
        kind=SHOP_ROOM_KIND,
        display_name="Dungeon Shop",
        tags=("shop", "merchant", "refuge"),
        door_policy="sealed",
        spawn_policy="safe",
        placement=SpecialRoomPlacement(chance=0.75, rng_stream="shared"),
    ),
    QUEST_ROOM_KIND: SpecialRoomDefinition(
        kind=QUEST_ROOM_KIND,
        display_name="Quest Room",
        tags=("quest", "guest", "story", "refuge"),
        door_policy="sealed",
        spawn_policy="safe",
        placement=SpecialRoomPlacement(
            rng_stream="guest", requires_flag="guest_room"
        ),
    ),
    BAR_ROOM_KIND: SpecialRoomDefinition(
        kind=BAR_ROOM_KIND,
        display_name="Wayfarer's Bar",
        tags=("bar", "refuge", "flavor"),
        door_policy="sealed",
        spawn_policy="normal",
        placement=SpecialRoomPlacement(chance=0.50),
    ),
    GARDEN_ROOM_KIND: SpecialRoomDefinition(
        kind=GARDEN_ROOM_KIND,
        display_name="Overgrown Garden",
        tags=("garden", "refuge", "flavor"),
        door_policy="sealed",
        spawn_policy="normal",
        placement=SpecialRoomPlacement(chance=0.50),
    ),
    LOSSLESS_SOUL_ROOM_KIND: SpecialRoomDefinition(
        kind=LOSSLESS_SOUL_ROOM_KIND,
        display_name="Hall of Unlost Echoes",
        tags=("soul", "story", "refuge", "flavor"),
        door_policy="sealed",
        spawn_policy="safe",
        placement=SpecialRoomPlacement(chance=0.50),
    ),
}


class Dungeon:
    def __init__(
        self,
        rng: random.Random,
        boss_arena: bool = False,
        guest_room: bool = False,
        force_soul_hall: bool = False,
    ) -> None:
        self.rng = rng
        self.boss_arena = boss_arena
        self.guest_room = guest_room
        # 4.9: Liss Voss is act-III load-bearing — the run guarantees one Hall
        # of Unlost Echoes by depth 7 if the 50% roll never landed. The flavor
        # RNG draw is still consumed so every other stream stays byte-stable.
        self.force_soul_hall = force_soul_hall
        self.tiles: list[list[Tile]] = []
        self.rooms: list[Room] = []
        self.stairs: tuple[int, int] = (0, 0)
        self.special_rooms: list[SpecialRoom] = []
        self.solid_furnishing_tiles: frozenset[tuple[int, int]] = frozenset()
        self.solid_furnishing_boxes: tuple[
            tuple[float, float, float, float], ...
        ] = ()
        self.generate()

    @property
    def shop_room_index(self) -> int | None:
        room = self.special_room_for_kind(SHOP_ROOM_KIND)
        return room.room_index if room is not None else None

    @shop_room_index.setter
    def shop_room_index(self, room_index: int | None) -> None:
        self._set_legacy_special_room(SHOP_ROOM_KIND, room_index)

    @property
    def guest_room_index(self) -> int | None:
        room = self.special_room_for_kind(QUEST_ROOM_KIND)
        return room.room_index if room is not None else None

    @guest_room_index.setter
    def guest_room_index(self, room_index: int | None) -> None:
        self._set_legacy_special_room(QUEST_ROOM_KIND, room_index)

    def _set_legacy_special_room(self, kind: str, room_index: int | None) -> None:
        self.special_rooms = [room for room in self.special_rooms if room.kind != kind]
        self.refresh_solid_furnishing_tiles()
        if room_index is None:
            return
        try:
            index = int(room_index)
        except (TypeError, ValueError):
            return
        if not (0 <= index < len(self.rooms)):
            return
        self._add_special_room(kind, index)

    def special_room_for_kind(self, kind: str) -> SpecialRoom | None:
        if kind == LEGACY_QUEST_GUEST_ROOM_KIND:
            kind = QUEST_ROOM_KIND
        return next(
            (
                room
                for room in self.special_rooms
                if room.kind == kind
                or (
                    kind == QUEST_ROOM_KIND
                    and room.kind == LEGACY_QUEST_GUEST_ROOM_KIND
                )
            ),
            None,
        )

    def special_room_at_index(self, room_index: int) -> SpecialRoom | None:
        return next(
            (room for room in self.special_rooms if room.room_index == room_index), None
        )

    def special_rooms_with_tag(self, tag: str) -> list[SpecialRoom]:
        return [room for room in self.special_rooms if room.has_tag(tag)]

    def room_has_tag(self, room_index: int, tag: str) -> bool:
        return any(
            room.room_index == room_index and room.has_tag(tag)
            for room in self.special_rooms
        )

    def special_room_at_point(self, x: float, y: float) -> SpecialRoom | None:
        """Return the special room whose interior contains the world point, if any."""
        room = self.room_at(x, y)
        if room is None:
            return None
        try:
            room_index = self.rooms.index(room)
        except ValueError:
            return None
        return self.special_room_at_index(room_index)

    def _add_special_room(self, kind: str, room_index: int) -> SpecialRoom | None:
        definition = SPECIAL_ROOM_DEFINITIONS.get(kind)
        if definition is None or not (0 <= room_index < len(self.rooms)):
            return None
        cx, cy = self.rooms[room_index].center
        room = SpecialRoom.from_definition(
            room_index,
            definition,
            reserved_tiles=[[cx, cy]],
            anchor_points={"center": [cx, cy]},
        )
        self.special_rooms.append(room)
        self.refresh_solid_furnishing_tiles()
        return room

    def generate(self) -> None:
        retries = 30 if self.boss_arena else 20
        attempts = 260 if self.boss_arena else 180
        for _ in range(retries):
            self.tiles = [[Tile.WALL for _ in range(MAP_H)] for _ in range(MAP_W)]
            self.rooms = []
            self.special_rooms = []
            for _attempt in range(attempts):
                reserving_final_arena = (
                    self.boss_arena and len(self.rooms) >= MIN_ROOM_COUNT - 1
                )
                if reserving_final_arena:
                    w = self.rng.randrange(BOSS_ARENA_MIN_W, BOSS_ARENA_MAX_W + 1)
                    h = self.rng.randrange(BOSS_ARENA_MIN_H, BOSS_ARENA_MAX_H + 1)
                else:
                    w = self.rng.randrange(6, 13)
                    h = self.rng.randrange(6, 12)
                x = self.rng.randrange(2, MAP_W - w - 2)
                y = self.rng.randrange(2, MAP_H - h - 2)
                room = Room(x, y, w, h)
                if any(room.intersects(existing, padding=2) for existing in self.rooms):
                    continue
                self._carve_room(room)
                if self.rooms:
                    self._connect(self.rooms[-1].center, room.center)
                self.rooms.append(room)
                if self.boss_arena:
                    if len(self.rooms) >= MIN_ROOM_COUNT and self._room_is_boss_arena(
                        room
                    ):
                        break
                elif len(self.rooms) >= MAX_ROOM_COUNT:
                    break
            if len(self.rooms) >= MIN_ROOM_COUNT:
                if self.boss_arena and not self._room_is_boss_arena(self.rooms[-1]):
                    continue
                self.stairs = self.rooms[-1].center
                sx, sy = self.stairs
                self.tiles[sx][sy] = Tile.STAIRS
                self._place_doors()
                self.refresh_solid_furnishing_tiles()
                return
        raise RuntimeError("Could not generate a valid dungeon")

    def _room_is_boss_arena(self, room: Room) -> bool:
        return room.w >= BOSS_ARENA_MIN_W and room.h >= BOSS_ARENA_MIN_H

    def _carve_room(self, room: Room) -> None:
        for x in range(room.x, room.x + room.w):
            for y in range(room.y, room.y + room.h):
                self.tiles[x][y] = Tile.FLOOR

    def _connect(self, a: tuple[int, int], b: tuple[int, int]) -> None:
        ax, ay = a
        bx, by = b
        if self.rng.random() < 0.5:
            self._carve_h(ax, bx, ay)
            self._carve_v(ay, by, bx)
        else:
            self._carve_v(ay, by, ax)
            self._carve_h(ax, bx, by)

    def _carve_h(self, x1: int, x2: int, y: int) -> None:
        for x in range(min(x1, x2), max(x1, x2) + 1):
            self._carve_corridor_tile(x, y)

    def _carve_v(self, y1: int, y2: int, x: int) -> None:
        for y in range(min(y1, y2), max(y1, y2) + 1):
            self._carve_corridor_tile(x, y)

    def _carve_corridor_tile(self, x: int, y: int) -> None:
        for ox, oy in ((0, 0), (1, 0), (0, 1)):
            tx, ty = x + ox, y + oy
            if 1 <= tx < MAP_W - 1 and 1 <= ty < MAP_H - 1:
                self.tiles[tx][ty] = Tile.FLOOR

    def _door_candidates_for_room(self, room: Room) -> list[tuple[int, int]]:
        candidates: list[tuple[int, int]] = []
        for run in self._door_candidate_runs_for_room(room):
            candidates.extend(run)
        return candidates

    def _door_candidate_runs_for_room(self, room: Room) -> list[list[tuple[int, int]]]:
        runs: list[list[tuple[int, int]]] = []

        def append_runs(points: list[tuple[int, int]]) -> None:
            run: list[tuple[int, int]] = []
            for x, y in points:
                if self._is_room_entrance_tile(room, x, y):
                    run.append((x, y))
                elif run:
                    runs.append(run)
                    run = []
            if run:
                runs.append(run)

        append_runs([(x, room.y) for x in range(room.x + 1, room.x + room.w - 1)])
        append_runs(
            [(x, room.y + room.h - 1) for x in range(room.x + 1, room.x + room.w - 1)]
        )
        append_runs([(room.x, y) for y in range(room.y + 1, room.y + room.h - 1)])
        append_runs(
            [(room.x + room.w - 1, y) for y in range(room.y + 1, room.y + room.h - 1)]
        )
        return runs

    def _doorways_for_room(self, room: Room) -> list[tuple[int, int]]:
        return [run[len(run) // 2] for run in self._door_candidate_runs_for_room(room)]

    def _door_side_wall_tiles(
        self, room: Room, x: int, y: int
    ) -> tuple[tuple[int, int], tuple[int, int]] | None:
        if y in (room.y, room.y + room.h - 1):
            return ((x - 1, y), (x + 1, y))
        if x in (room.x, room.x + room.w - 1):
            return ((x, y - 1), (x, y + 1))
        return None

    def _is_room_entrance_tile(self, room: Room, x: int, y: int) -> bool:
        if not self.in_bounds(x, y) or self.tiles[x][y] != Tile.FLOOR:
            return False
        side_walls = self._door_side_wall_tiles(room, x, y)
        if side_walls is None:
            return False
        if any(
            not self.in_bounds(wx, wy) or (wx, wy) == self.stairs
            for wx, wy in side_walls
        ):
            return False
        if x == room.x:
            inward = (x + 1, y)
            outward = (x - 1, y)
        elif x == room.x + room.w - 1:
            inward = (x - 1, y)
            outward = (x + 1, y)
        elif y == room.y:
            inward = (x, y + 1)
            outward = (x, y - 1)
        elif y == room.y + room.h - 1:
            inward = (x, y - 1)
            outward = (x, y + 1)
        else:
            return False
        return all(
            self.in_bounds(tx, ty) and self.tiles[tx][ty] == Tile.FLOOR
            for tx, ty in (inward, outward)
        )

    def _seal_room_with_doors(self, room: Room, doors: list[tuple[int, int]]) -> None:
        door_set = set(doors)
        for x in range(room.x, room.x + room.w):
            for y in (room.y, room.y + room.h - 1):
                self.tiles[x][y] = Tile.CLOSED_DOOR if (x, y) in door_set else Tile.WALL
        for y in range(room.y + 1, room.y + room.h - 1):
            for x in (room.x, room.x + room.w - 1):
                self.tiles[x][y] = Tile.CLOSED_DOOR if (x, y) in door_set else Tile.WALL

    def _placement_rng(
        self, stream: str, streams: dict[str, random.Random]
    ) -> random.Random:
        """Return the RNG behind a placement stream, creating layout-seeded
        streams on first use.

        ``"shared"`` is the main generation RNG: consuming it is part of the
        historical layout contract. The layout-seeded streams exist so optional
        rooms can roll without disturbing that shared sequence — and thus the
        downstream door pass + population stay byte-for-byte identical to runs
        without them, preserving determinism and save compat.
        """
        if stream == "shared":
            return self.rng
        rng = streams.get(stream)
        if rng is None:
            base = (self.stairs[0] * 73856093) ^ (self.stairs[1] * 19349663)
            if stream == "guest":
                seed = base ^ len(self.rooms)
            else:
                seed = base ^ (len(self.rooms) * 0x9E3779B1)
            rng = random.Random(seed)
            streams[stream] = rng
        return rng

    def _plan_special_rooms(
        self,
        eligible_rooms: list[int],
        doorways_by_room: dict[int, list[tuple[int, int]]],
    ) -> None:
        self.special_rooms = []
        streams: dict[str, random.Random] = {}
        for kind, definition in SPECIAL_ROOM_DEFINITIONS.items():
            placement = definition.placement
            if placement.requires_flag and not getattr(
                self, placement.requires_flag, False
            ):
                continue
            occupied = {room.room_index for room in self.special_rooms}
            candidates = [
                idx
                for idx in eligible_rooms
                if idx not in occupied and idx not in (0, len(self.rooms) - 1)
            ]
            if not candidates:
                continue
            rng = self._placement_rng(placement.rng_stream, streams)
            if placement.chance < 1.0 and rng.random() >= placement.chance:
                if not (
                    kind == LOSSLESS_SOUL_ROOM_KIND and self.force_soul_hall
                ):
                    continue
            self._add_special_room(kind, rng.choice(candidates))

        # Room definitions own mandatory gating. Apply those gates before the
        # ordinary optional-door pass so sealed special rooms stay closed even if
        # their random side-room roll below fails.
        for special_room in self.special_rooms:
            if special_room.door_policy != "sealed":
                continue
            room_index = special_room.room_index
            if room_index not in doorways_by_room:
                continue
            self._seal_room_with_doors(
                self.rooms[room_index], doorways_by_room[room_index]
            )

    def _place_doors(self) -> None:
        if len(self.rooms) < 3:
            return
        doorways_by_room = {
            room_index: self._doorways_for_room(room)
            for room_index, room in enumerate(self.rooms[1:-1], start=1)
        }
        eligible_rooms = [
            room_index for room_index, doorways in doorways_by_room.items() if doorways
        ]
        self._plan_special_rooms(eligible_rooms, doorways_by_room)
        for room_index, room in enumerate(self.rooms[1:-1], start=1):
            doorways = doorways_by_room[room_index]
            if not doorways:
                continue
            should_have_door = (
                self.room_has_tag(room_index, "shop") or self.rng.random() < 0.24
            )
            if should_have_door:
                self._seal_room_with_doors(room, doorways)

    def open_door(self, x: int, y: int) -> bool:
        if not self.in_bounds(x, y) or self.tiles[x][y] != Tile.CLOSED_DOOR:
            return False
        self.tiles[x][y] = Tile.OPEN_DOOR
        return True

    def nearby_closed_door(
        self, x: float, y: float, radius: float = 1.15
    ) -> tuple[int, int] | None:
        cx, cy = int(x), int(y)
        best: tuple[float, tuple[int, int]] | None = None
        search = max(1, int(radius) + 1)
        for tx in range(cx - search, cx + search + 1):
            for ty in range(cy - search, cy + search + 1):
                if not self.in_bounds(tx, ty) or self.tiles[tx][ty] != Tile.CLOSED_DOOR:
                    continue
                distance = ((tx + 0.5 - x) ** 2 + (ty + 0.5 - y) ** 2) ** 0.5
                if distance <= radius and (best is None or distance < best[0]):
                    best = (distance, (tx, ty))
        return best[1] if best else None

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < MAP_W and 0 <= y < MAP_H

    def room_at(self, x: float, y: float) -> Room | None:
        """Return the room whose interior contains the given world point, if any."""
        tx, ty = int(x), int(y)
        for room in self.rooms:
            if room.x <= tx < room.x + room.w and room.y <= ty < room.y + room.h:
                return room
        return None

    def room_region_distances(
        self, x: float, y: float, max_distance: int = 24
    ) -> dict[tuple[int, int], int]:
        """BFS step-distances over the contiguous chamber containing (x, y).

        Flood fill over floor-like tiles that stops at walls and at doors:
        door tiles (open or closed) join the region as boundary tiles but
        are never expanded through, so the region hugs one room or corridor
        segment. Starting on a door tile expands normally, flooding both
        adjoining spaces. ``max_distance`` bounds the fill so open corridor
        networks stay cheap; the visible screen covers far fewer tiles than
        the default cap. Returns {} when (x, y) is out of bounds or inside
        a wall.
        """
        start = (int(x), int(y))
        if (
            not self.in_bounds(*start)
            or self.tiles[start[0]][start[1]] == Tile.WALL
        ):
            return {}
        region: dict[tuple[int, int], int] = {start: 0}
        frontier: deque[tuple[int, int]] = deque((start,))
        while frontier:
            cx, cy = frontier.popleft()
            dist = region[(cx, cy)]
            if dist >= max_distance:
                continue
            if (
                self.tiles[cx][cy] in (Tile.CLOSED_DOOR, Tile.OPEN_DOOR)
                and (cx, cy) != start
            ):
                continue
            for nx, ny in (
                (cx + 1, cy),
                (cx - 1, cy),
                (cx, cy + 1),
                (cx, cy - 1),
            ):
                if (nx, ny) in region or not self.in_bounds(nx, ny):
                    continue
                if self.tiles[nx][ny] == Tile.WALL:
                    continue
                region[(nx, ny)] = dist + 1
                frontier.append((nx, ny))
        return region

    def _room_perimeter(self, room: Room) -> list[tuple[int, int]]:
        perimeter: list[tuple[int, int]] = []
        for x in range(room.x, room.x + room.w):
            perimeter.append((x, room.y))
            perimeter.append((x, room.y + room.h - 1))
        for y in range(room.y + 1, room.y + room.h - 1):
            perimeter.append((room.x, y))
            perimeter.append((room.x + room.w - 1, y))
        return perimeter

    def seal_room_openings(self, room: Room) -> list[tuple[int, int, Tile]]:
        """Close actual exits on the room perimeter so nothing can leave.

        Boss arenas should not lose an entire one-tile ring of walkable space when
        the fight starts; that could trap a player who entered through a doorway.
        We therefore seal detected corridor openings plus any existing door tiles,
        recording the previous tile kind so the caller can restore the room when
        the boss dies. A rare fallback seals the passable perimeter only if no
        entrance can be detected, preserving the encounter lock over perfect shape.
        """
        sealed: list[tuple[int, int, Tile]] = []
        seen: set[tuple[int, int]] = set()

        def seal_tile(x: int, y: int) -> None:
            if (x, y) in seen or not self.in_bounds(x, y):
                return
            tile = self.tiles[x][y]
            if tile in (Tile.FLOOR, Tile.OPEN_DOOR, Tile.CLOSED_DOOR):
                seen.add((x, y))
                sealed.append((x, y, tile))
                self.tiles[x][y] = Tile.CLOSED_DOOR

        def outside_room(nx: int, ny: int) -> bool:
            return not (
                room.x <= nx < room.x + room.w and room.y <= ny < room.y + room.h
            )

        def has_passable_outside_neighbor(x: int, y: int) -> bool:
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if not self.in_bounds(nx, ny) or not outside_room(nx, ny):
                    continue
                if self.tiles[nx][ny] in _PASSABLE_TILES:
                    return True
            return False

        perimeter = self._room_perimeter(room)
        for x, y in perimeter:
            if not self.in_bounds(x, y):
                continue
            tile = self.tiles[x][y]
            if tile in (Tile.OPEN_DOOR, Tile.CLOSED_DOOR) or (
                tile == Tile.FLOOR and has_passable_outside_neighbor(x, y)
            ):
                seal_tile(x, y)

        if not sealed:
            for x, y in perimeter:
                seal_tile(x, y)
        return sealed

    def restore_tiles(self, sealed: list[tuple[int, int, Tile]]) -> None:
        for x, y, tile in sealed:
            if self.in_bounds(x, y):
                self.tiles[x][y] = tile

    def is_floor(self, x: float, y: float) -> bool:
        # Hot LOS/projectile path: stairs are floor-like openings and do not block
        # sight or projectiles even though actors cannot walk into the shaft.
        tx, ty = int(x), int(y)
        if not (0 <= tx < MAP_W and 0 <= ty < MAP_H):
            return False
        return self.tiles[tx][ty] in _PASSABLE_TILES

    def is_walkable(self, x: float, y: float) -> bool:
        tx, ty = int(x), int(y)
        if not (0 <= tx < MAP_W and 0 <= ty < MAP_H):
            return False
        return self.tiles[tx][ty] in _WALKABLE_TILES

    def stair_collision_footprint(self) -> tuple[float, float, float, float]:
        """World-space AABB the player may not enter around the stair shaft.

        The footprint is the stair tile cell shifted north to align with the
        visible circular stairwell (the sprite's shaft center sits above the
        logical tile center) and inset on every side so the player can approach
        the masonry rim. LOS/projectiles/enemies are unaffected -- only the
        player's ``block_stairs`` movement probe uses this.
        """
        sx, sy = self.stairs
        ax = sx + STAIR_COLLISION_OFFSET_X + STAIR_COLLISION_INSET
        ay = sy + STAIR_COLLISION_OFFSET_Y + STAIR_COLLISION_INSET
        bx = sx + 1 + STAIR_COLLISION_OFFSET_X - STAIR_COLLISION_INSET
        by = sy + 1 + STAIR_COLLISION_OFFSET_Y - STAIR_COLLISION_INSET
        return ax, ay, bx, by

    def _probe_hits_stair(self, x: float, y: float) -> bool:
        ax, ay, bx, by = self.stair_collision_footprint()
        return ax <= x < bx and ay <= y < by

    def refresh_solid_furnishing_tiles(self) -> None:
        """Rebuild the solid-furnishing tile set from special-room anchors.

        Derived data for the hot movement probe: callers that add, drop, or
        move special rooms / solid anchors (generation, save restore, and
        population's anchor reservation) must call this afterwards so
        ``blocked_for_radius`` stays in sync without scanning rooms per probe.
        """
        tiles: set[tuple[int, int]] = set()
        for special_room in self.special_rooms:
            for key in SOLID_FURNISHING_ANCHOR_KEYS:
                anchor = special_room.anchor_points.get(key)
                if anchor is not None and len(anchor) >= 2:
                    tiles.add((int(anchor[0]), int(anchor[1])))
        self.solid_furnishing_tiles = frozenset(tiles)
        # Shifted/inset physical boxes, one per furnishing (the stairs
        # treatment): aligned with the drawn pedestal as seen against actors'
        # feet rather than with the logical tile square. May spill into the
        # north/west neighbor tiles; the probe checks every box, not tiles.
        self.solid_furnishing_boxes = tuple(
            (
                tx + SOLID_FURNISHING_COLLISION_OFFSET_X
                + SOLID_FURNISHING_COLLISION_INSET,
                ty + SOLID_FURNISHING_COLLISION_OFFSET_Y
                + SOLID_FURNISHING_COLLISION_INSET,
                tx + 1.0 + SOLID_FURNISHING_COLLISION_OFFSET_X
                - SOLID_FURNISHING_COLLISION_INSET,
                ty + 1.0 + SOLID_FURNISHING_COLLISION_OFFSET_Y
                - SOLID_FURNISHING_COLLISION_INSET,
            )
            for tx, ty in sorted(tiles)
        )

    def _probe_hits_solid_furnishing(self, x: float, y: float) -> bool:
        """Shifted, inset collision box per furnishing (the stairs treatment).

        The box is the anchor tile shifted north-west and inset
        (``SOLID_FURNISHING_COLLISION_*``), aligning collision with the drawn
        pedestal as the player's grounded feet meet it. Tile-level bookkeeping
        (spawn scans, anchor reservations) still treats the whole anchor tile
        as occupied via ``solid_furnishing_tiles``.
        """
        for ax, ay, bx, by in self.solid_furnishing_boxes:
            if ax <= x < bx and ay <= y < by:
                return True
        return False

    def furnishing_blocks_radius(self, x: float, y: float, radius: float) -> bool:
        """Whether the radius probe at (x, y) collides with any furnishing box.

        Used by the save-load nudge to detect players trapped by furnishing
        collision specifically (walls are a separate concern there).
        """
        if not self.solid_furnishing_boxes:
            return False
        for ox in (-radius, radius):
            for oy in (-radius, radius):
                if self._probe_hits_solid_furnishing(x + ox, y + oy):
                    return True
        return False

    def _wall_depth_relief_allows_probe(
        self,
        x: float,
        y: float,
        inset: float,
    ) -> bool:
        """Allow shallow overlap with a wall's exposed screen-north edge.

        Grounded actor art is drawn screen-south of its logical world point.
        A symmetric logical probe therefore leaves the same extra distance
        between the visible feet and walls approached toward screen north.
        ``inset`` removes only that shallow strip on a wall's exposed +x/+y
        faces. Bounds, doors, and walls approached from the opposite faces
        retain the ordinary square footprint.

        The diagonal case covers the top corner of a closed room: the actor
        may reach the shared integer corner but cannot cross it because any
        further step moves the probe below both relief strips.
        """
        tx, ty = math.floor(x), math.floor(y)
        if not self.in_bounds(tx, ty) or self.tiles[tx][ty] != Tile.WALL:
            return False

        edge = 1.0 - inset
        local_x = x - tx
        local_y = y - ty

        if (
            local_x >= edge
            and self.in_bounds(tx + 1, ty)
            and self.tiles[tx + 1][ty] in _PASSABLE_TILES
        ):
            return True
        if (
            local_y >= edge
            and self.in_bounds(tx, ty + 1)
            and self.tiles[tx][ty + 1] in _PASSABLE_TILES
        ):
            return True
        return (
            local_x >= edge
            and local_y >= edge
            and self.in_bounds(tx + 1, ty + 1)
            and self.tiles[tx + 1][ty + 1] in _PASSABLE_TILES
        )

    def footprint_wall_depth_relief_tiles(
        self,
        x: float,
        y: float,
        radius: float,
        wall_depth_relief: float,
    ) -> tuple[tuple[int, int], ...]:
        """Wall cells whose allowed relief strip overlaps a footprint.

        Rendering uses these exact cells to move the player only just past the
        contacted wall art in painter order. Keeping the query here prevents
        render ordering from drifting away from the collision contract.
        """

        wall_inset = (
            min(radius, wall_depth_relief)
            if wall_depth_relief > 0.0
            else 0.0
        )
        if wall_inset <= 0.0:
            return ()
        wall_tiles: set[tuple[int, int]] = set()
        for ox in (-radius, radius):
            for oy in (-radius, radius):
                px, py = x + ox, y + oy
                if self._wall_depth_relief_allows_probe(px, py, wall_inset):
                    wall_tiles.add((math.floor(px), math.floor(py)))
        return tuple(sorted(wall_tiles))

    def blocked_for_radius(
        self,
        x: float,
        y: float,
        radius: float = ACTOR_MOVE_COLLISION_RADIUS,
        *,
        block_stairs: bool = False,
        wall_depth_relief: float = 0.0,
    ) -> bool:
        """Whether a square footprint intersects physical dungeon geometry.

        ``wall_depth_relief`` is an opt-in rendering/contact correction used by
        player movement. It is capped to the supplied radius and affects only
        exposed Tile.WALL faces; all generic probes retain their historical
        symmetric behavior.
        """
        furnishings = self.solid_furnishing_boxes
        wall_inset = (
            min(radius, wall_depth_relief)
            if wall_depth_relief > 0.0
            else 0.0
        )
        # A footprint wider than a tile (radius >= 0.5, i.e. the 2x2 bosses)
        # can straddle a one-tile-thick obstacle — e.g. the doorway strip a
        # boss-arena seal just closed under its center — with all four
        # corners on open floor, so wide probes also sample the middle of
        # each axis (3x3 grid, which visits every tile the square footprint
        # overlaps for radius < 1). Narrow probes keep the historical
        # 4-corner sweep; their corners already visit every overlapped tile.
        offsets = (
            (-radius, 0.0, radius) if radius >= 0.5 else (-radius, radius)
        )
        if block_stairs:
            # Player path: stairs block via the shifted/inset footprint so the
            # collision aligns with the visible artwork. Walls and closed doors
            # still block through ``is_floor``; stairs themselves are floor-like
            # for LOS/projectiles and only block this physical probe.
            for ox in offsets:
                for oy in offsets:
                    px, py = x + ox, y + oy
                    if self._probe_hits_stair(px, py):
                        return True
                    if not self.is_floor(px, py) and (
                        wall_inset <= 0.0
                        or not self._wall_depth_relief_allows_probe(
                            px, py, wall_inset
                        )
                    ):
                        return True
                    if furnishings and self._probe_hits_solid_furnishing(px, py):
                        return True
            return False
        for ox in offsets:
            for oy in offsets:
                px, py = x + ox, y + oy
                if not self.is_floor(px, py) and (
                    wall_inset <= 0.0
                    or not self._wall_depth_relief_allows_probe(
                        px, py, wall_inset
                    )
                ):
                    return True
                if furnishings and self._probe_hits_solid_furnishing(px, py):
                    return True
        return False

    def line_of_sight(self, x0: float, y0: float, x1: float, y1: float) -> bool:
        # Trace the straight line between two world points and return False if a
        # wall/closed door blocks it. Endpoints are skipped so actors standing on
        # floor are not treated as blocking themselves. Diagonal tile transitions
        # also reject a closed corner made from two touching orthogonal walls; a
        # zero-width ray must not let attacks slip through that seam.
        dx = x1 - x0
        dy = y1 - y0
        distance = math.hypot(dx, dy)
        if distance < 1e-3:
            return True
        steps = max(1, math.ceil(distance / 0.25))
        inv = 1.0 / steps
        previous_tx = int(x0)
        previous_ty = int(y0)
        for i in range(1, steps + 1):
            t = i * inv
            px = x0 + dx * t
            py = y0 + dy * t
            tx = int(px)
            ty = int(py)
            if tx != previous_tx and ty != previous_ty:
                horizontal_open = self.is_floor(tx + 0.5, previous_ty + 0.5)
                vertical_open = self.is_floor(previous_tx + 0.5, ty + 0.5)
                if not horizontal_open and not vertical_open:
                    return False
            if i < steps and not self.is_floor(px, py):
                return False
            previous_tx = tx
            previous_ty = ty
        return True
