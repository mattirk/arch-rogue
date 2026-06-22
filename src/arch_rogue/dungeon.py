from __future__ import annotations

import random

from .models import Room, Tile

MAP_W = 72
MAP_H = 72

class Dungeon:
    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.tiles: list[list[Tile]] = []
        self.rooms: list[Room] = []
        self.stairs: tuple[int, int] = (0, 0)
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

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < MAP_W and 0 <= y < MAP_H

    def is_floor(self, x: float, y: float) -> bool:
        tx, ty = int(x), int(y)
        return self.in_bounds(tx, ty) and self.tiles[tx][ty] != Tile.WALL

    def blocked_for_radius(self, x: float, y: float, radius: float = 0.27) -> bool:
        for ox in (-radius, radius):
            for oy in (-radius, radius):
                if not self.is_floor(x + ox, y + oy):
                    return True
        return False
