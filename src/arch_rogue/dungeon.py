# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
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

from .models import Room, SpecialRoom, SpecialRoomDefinition, Tile

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

# Passable tile kinds (used by the hot `is_floor` path). Module-level so the
# membership test avoids rebuilding a tuple each call.
_PASSABLE_TILES = (Tile.FLOOR, Tile.STAIRS, Tile.OPEN_DOOR)

SHOP_ROOM_KIND = "shop"
QUEST_GUEST_ROOM_KIND = "quest_guest"

SPECIAL_ROOM_DEFINITIONS: dict[str, SpecialRoomDefinition] = {
    SHOP_ROOM_KIND: SpecialRoomDefinition(
        kind=SHOP_ROOM_KIND,
        display_name="Dungeon Shop",
        tags=("shop", "merchant", "refuge"),
        door_policy="sealed",
        spawn_policy="safe",
    ),
    QUEST_GUEST_ROOM_KIND: SpecialRoomDefinition(
        kind=QUEST_GUEST_ROOM_KIND,
        display_name="Quest Guest Room",
        tags=("quest", "guest", "story", "refuge"),
        door_policy="sealed",
        spawn_policy="safe",
    ),
}


class Dungeon:
    def __init__(
        self, rng: random.Random, boss_arena: bool = False, guest_room: bool = False
    ) -> None:
        self.rng = rng
        self.boss_arena = boss_arena
        self.guest_room = guest_room
        self.tiles: list[list[Tile]] = []
        self.rooms: list[Room] = []
        self.stairs: tuple[int, int] = (0, 0)
        self.special_rooms: list[SpecialRoom] = []
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
        room = self.special_room_for_kind(QUEST_GUEST_ROOM_KIND)
        return room.room_index if room is not None else None

    @guest_room_index.setter
    def guest_room_index(self, room_index: int | None) -> None:
        self._set_legacy_special_room(QUEST_GUEST_ROOM_KIND, room_index)

    def _set_legacy_special_room(self, kind: str, room_index: int | None) -> None:
        self.special_rooms = [room for room in self.special_rooms if room.kind != kind]
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
        return next((room for room in self.special_rooms if room.kind == kind), None)

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

    def _plan_special_rooms(
        self,
        eligible_rooms: list[int],
        doorways_by_room: dict[int, list[tuple[int, int]]],
    ) -> None:
        self.special_rooms = []
        if eligible_rooms and self.rng.random() < 0.75:
            self._add_special_room(SHOP_ROOM_KIND, self.rng.choice(eligible_rooms))

        if self.guest_room:
            occupied = {room.room_index for room in self.special_rooms}
            guest_candidates = [
                idx
                for idx in eligible_rooms
                if idx not in occupied and idx not in (0, len(self.rooms) - 1)
            ]
            if guest_candidates:
                # Pick with a local RNG seeded from the dungeon layout so the
                # shared `self.rng` stream (and thus population determinism) is
                # preserved across story-beat floors.
                guest_seed = (
                    (self.stairs[0] * 73856093)
                    ^ (self.stairs[1] * 19349663)
                    ^ len(self.rooms)
                )
                guest_rng = random.Random(guest_seed)
                self._add_special_room(
                    QUEST_GUEST_ROOM_KIND, guest_rng.choice(guest_candidates)
                )

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
        # Hot path (called many times per frame for LOS/movement/collision):
        # inline the bounds check to avoid the `in_bounds` method call, and use
        # a module-level tuple for the passable-tile membership test.
        tx, ty = int(x), int(y)
        if not (0 <= tx < MAP_W and 0 <= ty < MAP_H):
            return False
        return self.tiles[tx][ty] in _PASSABLE_TILES

    def blocked_for_radius(self, x: float, y: float, radius: float = 0.27) -> bool:
        for ox in (-radius, radius):
            for oy in (-radius, radius):
                if not self.is_floor(x + ox, y + oy):
                    return True
        return False

    def line_of_sight(self, x0: float, y0: float, x1: float, y1: float) -> bool:
        # Trace the straight line between two world points and return False if a
        # wall/closed door blocks it. Endpoints are skipped so actors standing on
        # floor are not treated as blocking themselves. Sampling step is small
        # enough (<= 0.25 tile) that no 1-tile wall can be jumped between samples.
        dx = x1 - x0
        dy = y1 - y0
        distance = math.hypot(dx, dy)
        if distance < 1e-3:
            return True
        steps = int(distance / 0.25)
        if steps <= 1:
            return True
        inv = 1.0 / steps
        for i in range(1, steps):
            t = i * inv
            if not self.is_floor(x0 + dx * t, y0 + dy * t):
                return False
        return True
