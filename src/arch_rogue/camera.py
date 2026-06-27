# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

from .constants import TILE_H, TILE_W
from .dungeon import MAP_H, MAP_W


class CameraMixin:
    def world_to_iso(self, x: float, y: float) -> tuple[float, float]:
        return (x - y) * TILE_W / 2, (x + y) * TILE_H / 2

    def camera_iso(self) -> tuple[float, float]:
        return self.world_to_iso(self.player.x, self.player.y)

    def world_to_screen(self, x: float, y: float) -> tuple[int, int]:
        iso_x, iso_y = self.world_to_iso(x, y)
        cam_x, cam_y = self.camera_iso()
        width, height = self.screen.get_size()
        return int(iso_x - cam_x + width * 0.5), int(iso_y - cam_y + height * 0.48)

    def screen_to_world(self, sx: int, sy: int) -> tuple[float, float]:
        cam_x, cam_y = self.camera_iso()
        width, height = self.screen.get_size()
        iso_x = sx - width * 0.5 + cam_x
        iso_y = sy - height * 0.48 + cam_y
        x = iso_y / TILE_H + iso_x / TILE_W
        y = iso_y / TILE_H - iso_x / TILE_W
        return x, y

    def visible_bounds(self) -> tuple[int, int, int, int]:
        radius = 22
        min_x = max(0, int(self.player.x) - radius)
        max_x = min(MAP_W - 1, int(self.player.x) + radius)
        min_y = max(0, int(self.player.y) - radius)
        max_y = min(MAP_H - 1, int(self.player.y) + radius)
        return min_x, max_x, min_y, max_y
