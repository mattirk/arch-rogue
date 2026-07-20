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

    # Viewport zoom ("viewport distance"). 1.0 = native; >1 zooms in (fewer
    # tiles, larger sprites), <1 zooms out (more tiles, smaller sprites).
    # Implemented as an offscreen world layer rendered at screen_size/zoom and
    # scaled back to the display, so tiles, sprites, and lighting zoom uniformly.
    VIEW_ZOOM_MIN = 0.65
    VIEW_ZOOM_MAX = 1.6
    VIEW_ZOOM_STEP = 1.12

    def adjust_view_zoom(self, notches: float) -> None:
        """Adjust viewport zoom by a number of scroll notches (positive = in)."""
        if not notches:
            return
        factor = self.VIEW_ZOOM_STEP ** notches
        zoom = getattr(self, "view_zoom", 1.0) * factor
        self.view_zoom = max(self.VIEW_ZOOM_MIN, min(self.VIEW_ZOOM_MAX, zoom))

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

    def _mobile_projection_origin(
        self, width: int, height: int
    ) -> tuple[float, float]:
        # world_to_screen runs tens of thousands of times per frame in crowds;
        # the origin only depends on the (cached) layout and the render-target
        # size, so memoize it per frame instead of recomputing the focus math
        # and re-validating the layout on every call.
        cache = getattr(self, "_frame_cache", None)
        key = ("mobile_projection_origin", width, height)
        if cache is not None and key in cache:
            return cache[key]  # type: ignore[return-value]
        layout = self.mobile_layout()
        viewport = layout.world_viewport
        focus_x = (layout.world_focus[0] - viewport.x) / max(1, viewport.width)
        focus_y = (layout.world_focus[1] - viewport.y) / max(1, viewport.height)
        origin = (width * focus_x, height * focus_y)
        if cache is not None:
            cache[key] = origin
        return origin

    def world_to_screen(self, x: float, y: float) -> tuple[int, int]:
        iso_x, iso_y = self.world_to_iso(x, y)
        cam_x, cam_y = self.camera_iso()
        width, height = self._screen_size()
        origin_x, origin_y = width * 0.5, height * 0.48
        if getattr(self, "mobile_mode", False) and getattr(
            self, "_mobile_world_rendering", False
        ):
            origin_x, origin_y = self._mobile_projection_origin(width, height)
        return int(iso_x - cam_x + origin_x), int(iso_y - cam_y + origin_y)

    def world_to_display(self, x: float, y: float) -> tuple[int, int]:
        # Real-display-pixel projection for post-composite screen-space effects
        # (lighting, vignettes). ``world_to_screen`` maps into the current render
        # target and is deliberately zoom-unaware: the world-layer pipeline
        # sizes that target to ``screen/zoom`` so tile/sprite drawing fills the
        # display when scaled back. Effects that run *after* the composite
        # cannot rely on that trick — they see the real display — so this scales
        # the iso offset by ``view_zoom`` and is correct at any zoom level. At
        # zoom 1.0 it is identical to ``world_to_screen``.
        iso_x, iso_y = self.world_to_iso(x, y)
        cam_x, cam_y = self.camera_iso()
        mobile = bool(getattr(self, "mobile_mode", False))
        world_rendering = bool(getattr(self, "_mobile_world_rendering", False))
        if mobile and not world_rendering:
            layout = self.mobile_layout()
            focus_x, focus_y = layout.world_focus
            zoom = getattr(self, "view_zoom", 1.0)
            return (
                int((iso_x - cam_x) * zoom + focus_x),
                int((iso_y - cam_y) * zoom + focus_y),
            )

        width, height = self._screen_size()
        origin_x, origin_y = width * 0.5, height * 0.48
        if mobile:
            origin_x, origin_y = self._mobile_projection_origin(width, height)
        zoom = getattr(self, "view_zoom", 1.0)
        return (
            int((iso_x - cam_x) * zoom + origin_x),
            int((iso_y - cam_y) * zoom + origin_y),
        )

    def _screen_size(self) -> tuple[int, int]:
        cache = getattr(self, "_frame_cache", None)
        if cache is not None and "screen_size" in cache:
            return cache["screen_size"]  # type: ignore[no-any-return]
        size = self.screen.get_size()
        if cache is not None:
            cache["screen_size"] = size
        return size

    def screen_to_world(self, sx: int, sy: int) -> tuple[float, float]:
        # Mouse coordinates arrive in real display pixels. With viewport zoom,
        # the world is rendered to a layer of size (screen/zoom) and scaled up
        # by `zoom` to fill the display, so a display pixel maps to layer
        # pixel / zoom. Invert that, then undo the world_to_iso projection.
        cam_x, cam_y = self.camera_iso()
        mobile = bool(getattr(self, "mobile_mode", False))
        if mobile:
            viewport = self.mobile_world_viewport()
            sx -= viewport.x
            sy -= viewport.y
            width, height = viewport.size
            origin_x, origin_y = self._mobile_projection_origin(width, height)
        else:
            width, height = self.screen.get_size()
            origin_x, origin_y = width * 0.5, height * 0.48
        zoom = getattr(self, "view_zoom", 1.0)
        iso_x = (sx - origin_x) / zoom + cam_x
        iso_y = (sy - origin_y) / zoom + cam_y
        x = iso_y / TILE_H + iso_x / TILE_W
        y = iso_y / TILE_H - iso_x / TILE_W
        return x, y

    def visible_bounds(self) -> tuple[int, int, int, int]:
        # Derive the visible tile radius from the actual screen size and tile
        # dimensions so we only iterate tiles that can appear on screen.
        # The iso diamond's half-extent along either world axis is roughly
        # (screen_w/TILE_W + screen_h/TILE_H) / 2; pad by 2 for safety.
        #
        # Cached per frame: the first caller each frame runs while the render
        # target is the (zoom-sized) world layer, so the cached bounds describe
        # the world area actually shown. Post-composite callers (lighting) then
        # reuse those layer-derived bounds instead of recomputing against the
        # real display, which would under-estimate the visible area when
        # zoomed out and drop edge lights/tiles.
        cache = getattr(self, "_frame_cache", None)
        if cache is not None:
            cached = cache.get("visible_bounds")
            if cached is not None:
                return cached  # type: ignore[no-any-return]
        width, height = self._screen_size()
        radius = int((width / TILE_W + height / TILE_H) / 2) + 2
        # Clamp to a sane floor so tiny windows still render something, and
        # to a ceiling so the loop stays cheap on huge displays.
        radius = max(6, min(radius, 22))
        min_x = max(0, int(self.player.x) - radius)
        max_x = min(MAP_W - 1, int(self.player.x) + radius)
        min_y = max(0, int(self.player.y) - radius)
        max_y = min(MAP_H - 1, int(self.player.y) + radius)
        bounds = (min_x, max_x, min_y, max_y)
        if cache is not None:
            cache["visible_bounds"] = bounds
        return bounds
