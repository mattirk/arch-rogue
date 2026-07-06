from __future__ import annotations

import math
import random

from .models import Room, Tile

MAP_W = 72
MAP_H = 72

# Passable tile kinds (used by the hot `is_floor` path). Module-level so the
# membership test avoids rebuilding a tuple each call.
_PASSABLE_TILES = (Tile.FLOOR, Tile.STAIRS, Tile.OPEN_DOOR)


class Dungeon:
    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.tiles: list[list[Tile]] = []
        self.rooms: list[Room] = []
        self.stairs: tuple[int, int] = (0, 0)
        self.shop_room_index: int | None = None
        self.generate()

    def generate(self) -> None:
        for _ in range(20):
            self.tiles = [[Tile.WALL for _ in range(MAP_H)] for _ in range(MAP_W)]
            self.rooms = []
            for _attempt in range(180):
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
                if len(self.rooms) >= 14:
                    break
            if len(self.rooms) >= 8:
                self.stairs = self.rooms[-1].center
                sx, sy = self.stairs
                self.tiles[sx][sy] = Tile.STAIRS
                self._place_doors()
                return
        raise RuntimeError("Could not generate a valid dungeon")

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

    def _place_doors(self) -> None:
        if len(self.rooms) < 3:
            return
        doorways_by_room = {
            room_index: self._doorways_for_room(room)
            for room_index, room in enumerate(self.rooms[1:-1], start=1)
        }
        eligible_shop_rooms = [
            room_index for room_index, doorways in doorways_by_room.items() if doorways
        ]
        if eligible_shop_rooms and self.rng.random() < 0.75:
            self.shop_room_index = self.rng.choice(eligible_shop_rooms)
        for room_index, room in enumerate(self.rooms[1:-1], start=1):
            doorways = doorways_by_room[room_index]
            if not doorways:
                continue
            should_have_door = (
                room_index == self.shop_room_index or self.rng.random() < 0.24
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
