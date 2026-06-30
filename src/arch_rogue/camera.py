# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

from .constants import TILE_H, TILE_W
from .dungeon import MAP_H, MAP_W


class CameraMixin:
    def world_to_iso(self, x: float, y: float) -> tuple[float, float]:
        return (x - y) * TILE_W / 2, (x + y) * TILE_H / 2

    def camera_iso(self) -> tuple[float, float]:
        cache = getattr(self, "_frame_cache", None)
        if cache is not None and "camera_iso" in cache:
            return cache["camera_iso"]  # type: ignore[no-any-return]
        iso = self.world_to_iso(self.player.x, self.player.y)
        if cache is not None:
            cache["camera_iso"] = iso
        return iso

    def world_to_screen(self, x: float, y: float) -> tuple[int, int]:
        iso_x, iso_y = self.world_to_iso(x, y)
        cam_x, cam_y = self.camera_iso()
        width, height = self._screen_size()
        return int(iso_x - cam_x + width * 0.5), int(iso_y - cam_y + height * 0.48)

    def _screen_size(self) -> tuple[int, int]:
        cache = getattr(self, "_frame_cache", None)
        if cache is not None and "screen_size" in cache:
            return cache["screen_size"]  # type: ignore[no-any-return]
        size = self.screen.get_size()
        if cache is not None:
            cache["screen_size"] = size
        return size

    def screen_to_world(self, sx: int, sy: int) -> tuple[float, float]:
        cam_x, cam_y = self.camera_iso()
        width, height = self._screen_size()
        iso_x = sx - width * 0.5 + cam_x
        iso_y = sy - height * 0.48 + cam_y
        x = iso_y / TILE_H + iso_x / TILE_W
        y = iso_y / TILE_H - iso_x / TILE_W
        return x, y

    def visible_bounds(self) -> tuple[int, int, int, int]:
        # Derive the visible tile radius from the actual screen size and tile
        # dimensions so we only iterate tiles that can appear on screen.
        # The iso diamond's half-extent along either world axis is roughly
        # (screen_w/TILE_W + screen_h/TILE_H) / 2; pad by 2 for safety.
        width, height = self._screen_size()
        radius = int((width / TILE_W + height / TILE_H) / 2) + 2
        # Clamp to a sane floor so tiny windows still render something, and
        # to a ceiling so the loop stays cheap on huge displays.
        radius = max(6, min(radius, 22))
        min_x = max(0, int(self.player.x) - radius)
        max_x = min(MAP_W - 1, int(self.player.x) + radius)
        min_y = max(0, int(self.player.y) - radius)
        max_y = min(MAP_H - 1, int(self.player.y) + radius)
        return min_x, max_x, min_y, max_y
