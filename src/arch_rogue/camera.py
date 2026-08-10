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

from .constants import (
    GRAPHICS_TIER_DEFAULT,
    GRAPHICS_TIER_HD,
    GRAPHICS_TIER_LEGACY,
    TILE_H,
    TILE_W,
    WORLD_SCALE,
)
from .dungeon import MAP_H, MAP_W
from .steam_deck import is_steam_deck


class CameraMixin:
    # Smoothing factor for camera follow. Higher = snappier, lower = smoother.
    # Frame-rate independent: combined with dt in update_camera().
    # 14.0 ~ 70ms time constant: tight follow with a small ease to absorb
    # collision jitter and per-frame movement variance.
    CAMERA_SMOOTHNESS = 14.0

    # Viewport zoom ("viewport distance"). 1.0 = native; >1 zooms in (fewer
    # tiles, larger sprites), <1 zooms out (more tiles, smaller sprites).
    # Implemented as an offscreen world layer rendered at
    # screen_size*render_bucket/zoom and scaled by the small residual back to
    # the display, so tiles, sprites, and lighting zoom uniformly.
    VIEW_ZOOM_MIN = 0.65
    VIEW_ZOOM_MAX = 1.6
    VIEW_ZOOM_STEP = 1.12
    # The world render target uses one of five exact authored-art scale
    # buckets.  WORLD_SCALE is 5, so these map to integer render scales
    # 4/5/6/7/8 and the maximum bucket maps a 512 px floor master directly to
    # a 512 px on-screen tile.  Keeping this tuple small bounds every derived
    # sprite/cache family while a residual composite (view zoom / bucket)
    # preserves continuous camera zoom.
    #
    # The 0.8 bucket exists for the wide desktop views: without it, any zoom
    # below 1.0 rendered the whole world into a layer larger than the display
    # (1.5x the pixels at the HD default zoom) and paid a full-frame composite
    # scale. With it, the HD default zoom sits exactly on a bucket, so the
    # world renders directly into the display with no oversized layer at all,
    # and the widest zoom (0.65) over-renders by 1.51x instead of 2.37x.
    WORLD_RENDER_SCALE_BUCKETS = (0.8, 1.0, 1.2, 1.4, 1.6)

    def set_view_zoom(self, zoom: float) -> None:
        """Set viewport zoom while enforcing the shared camera limits."""
        self.view_zoom = max(
            self.VIEW_ZOOM_MIN,
            min(self.VIEW_ZOOM_MAX, float(zoom)),
        )

    def adjust_view_zoom(self, notches: float) -> None:
        """Adjust viewport zoom by a number of scroll notches (positive = in)."""
        if not notches:
            return
        factor = self.VIEW_ZOOM_STEP ** notches
        zoom = getattr(self, "view_zoom", 1.0) * factor
        self.set_view_zoom(zoom)

    def default_view_zoom(self) -> float:
        """Initial viewport zoom for a fresh session.

        Mobile starts at native scale and adjusts by pinch. Desktop starts at
        the widest view so players see more of the dungeon, except on the HD
        tier, whose high-resolution art carries a closer default of roughly
        two zoom notches in from the widest view. The Steam Deck stays at the
        widest view even on HD. The HD default sits exactly
        on the smallest render bucket (0.8, vs. 0.65 * 1.12**2 = 0.815): with
        a zero residual the world renders straight into the display with no
        oversized intermediate layer and no full-frame composite scale, and
        512 px masters map to the display at an exact 2:1 texel ratio, which
        also removes fractional-zoom resample shimmer during camera motion.
        """
        if getattr(self, "mobile_mode", False):
            return 1.0
        # The Deck's 7-inch 1280x800 panel shows few tiles at the HD default,
        # so it always starts at the widest view; pinch zoom still adjusts
        # from there. The 0.8-bucket zero-residual economy is a desktop
        # optimization the small panel-native canvas does not need.
        if is_steam_deck():
            return self.VIEW_ZOOM_MIN
        zoom = self.VIEW_ZOOM_MIN
        if getattr(self, "graphics_tier", GRAPHICS_TIER_DEFAULT) == GRAPHICS_TIER_HD:
            zoom = self.WORLD_RENDER_SCALE_BUCKETS[0]
        return max(self.VIEW_ZOOM_MIN, min(self.VIEW_ZOOM_MAX, zoom))

    def world_render_scale_bucket(self, zoom: float | None = None) -> float:
        """Return the smallest bounded render bucket that covers ``zoom``."""

        # Only HD has 512 px masters to recover at close zoom. Legacy
        # procedural art and the original lower-resolution Modern world both
        # preserve their established single-resolution pipeline.
        graphics_tier = getattr(self, "graphics_tier", None)
        if graphics_tier is None:
            # Compatibility for integrations/test doubles that still expose
            # only the former boolean setting.
            graphics_tier = (
                GRAPHICS_TIER_LEGACY
                if bool(getattr(self, "legacy_graphics", False))
                else GRAPHICS_TIER_DEFAULT
            )
        if graphics_tier != GRAPHICS_TIER_HD:
            return 1.0
        if zoom is None:
            zoom = float(getattr(self, "view_zoom", 1.0))
        zoom = max(self.VIEW_ZOOM_MIN, min(self.VIEW_ZOOM_MAX, float(zoom)))
        # Choose the smallest bucket at least as detailed as the requested
        # zoom. The residual composite is therefore identity or a downscale,
        # never an upscale that would reintroduce enlarged texels between
        # bucket boundaries.
        for candidate in self.WORLD_RENDER_SCALE_BUCKETS:
            if candidate + 1e-9 >= zoom:
                return candidate
        return self.WORLD_RENDER_SCALE_BUCKETS[-1]

    @property
    def world_render_scale(self) -> float:
        """Scale used by the active world render target.

        During a world pass the renderer pins ``_active_world_render_scale`` so
        every projection, tile, actor, effect, and light reads one consistent
        bucket.  Outside a pass (prewarming/tests) the current view zoom selects
        the same deterministic bucket.
        """

        active = getattr(self, "_active_world_render_scale", None)
        if active is not None:
            return float(active)
        return self.world_render_scale_bucket()

    @property
    def world_pixel_scale(self) -> int:
        """Integer world drawing unit for the active 5/6/7/8 px bucket."""

        return round(WORLD_SCALE * self.world_render_scale)

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

    def _projection_origin(
        self, width: int, height: int
    ) -> tuple[float, float]:
        # world_to_screen runs tens of thousands of times per frame in crowds.
        # The origin only depends on the render-target size (desktop: fixed
        # 0.5/0.48 focus) or the cached mobile layout + render-target size
        # (mobile world rendering), so memoize it per frame instead of
        # recomputing on every call. 4.3.17 WS-D: the memoization was a
        # mobile-only win in 4.3.14; it is now shared so desktop crowds avoid
        # recomputing the origin too. _frame_cache is cleared at the start of
        # every draw(), so the origin is invalidated on camera focus / layout /
        # resolution changes automatically.
        cache = getattr(self, "_frame_cache", None)
        key = ("projection_origin", width, height)
        if cache is not None and key in cache:
            return cache[key]  # type: ignore[return-value]
        if getattr(self, "mobile_mode", False) and getattr(
            self, "_mobile_world_rendering", False
        ):
            layout = self.mobile_layout()
            viewport = layout.world_viewport
            focus_x = (layout.world_focus[0] - viewport.x) / max(1, viewport.width)
            focus_y = (layout.world_focus[1] - viewport.y) / max(1, viewport.height)
            origin = (width * focus_x, height * focus_y)
        else:
            origin = (width * 0.5, height * 0.48)
        if cache is not None:
            cache[key] = origin
        return origin

    def _mobile_projection_origin(
        self, width: int, height: int
    ) -> tuple[float, float]:
        # Layout-aware origin used by world_to_display / screen_to_world / the
        # mobile floor cache, which need the mobile focus regardless of the
        # _mobile_world_rendering flag. Kept separate from _projection_origin
        # (which gates on _mobile_world_rendering for world_to_screen) so the
        # two hot paths stay behavior-identical to pre-merge.
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
        origin_x, origin_y = self._projection_origin(width, height)
        render_scale = self.world_render_scale
        return (
            int((iso_x - cam_x) * render_scale + origin_x),
            int((iso_y - cam_y) * render_scale + origin_y),
        )

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
        # the world is rendered with a bucket scale and composed by the residual
        # zoom/bucket. Those factors cancel here, so display projection still
        # inverts through the requested view zoom alone.
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
        render_scale = self.world_render_scale
        radius = int(
            (
                width / (TILE_W * render_scale)
                + height / (TILE_H * render_scale)
            )
            / 2
        ) + 2
        # Clamp to a sane floor so tiny windows still render something, and
        # to a ceiling so the loop stays cheap on huge displays.
        radius = max(6, min(radius, 22))
        # Center the box on the view (the smoothed camera), not the player:
        # while walking, the camera trails the player by up to a tile, and a
        # player-centered box left the trailing screen edge outside the padded
        # radius — whole tile rows popped in and out at the screen border as
        # the camera caught up. Mobile keeps the player center: its projection
        # focus is layout-driven and the player is pinned near it.
        if getattr(self, "mobile_mode", False):
            center_x, center_y = self.player.x, self.player.y
        else:
            cam_x, cam_y = self.camera_iso()
            center_x = cam_y / TILE_H + cam_x / TILE_W
            center_y = cam_y / TILE_H - cam_x / TILE_W
        min_x = max(0, int(center_x) - radius)
        max_x = min(MAP_W - 1, int(center_x) + radius)
        min_y = max(0, int(center_y) - radius)
        max_y = min(MAP_H - 1, int(center_y) + radius)
        bounds = (min_x, max_x, min_y, max_y)
        if cache is not None:
            cache["visible_bounds"] = bounds
        return bounds
