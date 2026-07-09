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

# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

from .constants import TILE_H, TILE_W
from .dungeon import MAP_H, MAP_W


class CameraMixin:
    # Smoothing factor for camera follow. Higher = snappier, lower = smoother.
    # Frame-rate independent: combined with dt in update_camera().
    # 14.0 ~ 70ms time constant: tight follow with a small ease to absorb
    # collision jitter and per-frame movement variance.
    CAMERA_SMOOTHNESS = 14.0

    def world_to_iso(self, x: float, y: float) -> tuple[float, float]:
        return (x - y) * TILE_W / 2, (x + y) * TILE_H / 2

    def camera_iso(self) -> tuple[float, float]:
        cache = getattr(self, "_frame_cache", None)
        if cache is not None and "camera_iso" in cache:
            return cache["camera_iso"]  # type: ignore[no-any-return]
        # Use the smoothed camera position if it has been initialized;
        # otherwise (first frame / after restart) snap directly to the
        # player so the camera never starts mid-lerp.
        if getattr(self, "_cam_iso", None) is None:
            iso = self.world_to_iso(self.player.x, self.player.y)
            self._cam_iso = iso
        else:
            iso = self._cam_iso
        if cache is not None:
            cache["camera_iso"] = iso
        return iso

    def update_camera(self, dt: float) -> None:
        """Advance the smoothed camera toward the player's iso position.

        Uses an exponential lerp (frame-rate independent) so the camera
        eases toward the player instead of hard-locking. This eliminates
        the micro-jitter from collision resolution and per-frame movement
        variance that made the view feel janky.
        """
        target = self.world_to_iso(self.player.x, self.player.y)
        if getattr(self, "_cam_iso", None) is None:
            self._cam_iso = target
            return
        # Exponential smoothing: t in [0,1], approaches 1 as dt grows.
        # 1 - exp(-k*dt) is the standard frame-rate-independent lerp.
        t = 1.0 - pow(2.718281828459045, -self.CAMERA_SMOOTHNESS * dt)
        cx, cy = self._cam_iso
        self._cam_iso = (cx + (target[0] - cx) * t, cy + (target[1] - cy) * t)

    def snap_camera_to_player(self) -> None:
        """Hard-reset the smoothed camera to the player (used on restart/teleport)."""
        self._cam_iso = self.world_to_iso(self.player.x, self.player.y)

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
