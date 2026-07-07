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

# pyright: reportAttributeAccessIssue=false, reportUnusedImport=false
from __future__ import annotations

import math
import random
from collections import deque
from typing import cast

import pygame

from ..constants import (
    DUNGEON_DEPTH,
    DUNGEON_FLOOR_VARIANTS,
    DUNGEON_WALL_VARIANTS,
    TILE_H,
    TILE_W,
    WORLD_SCALE,
    SlashEffect,
)
from ..content import HUMANOID_ENEMY_NAMES
from ..models import (
    Color,
    Enemy,
    ImpactEffect,
    Item,
    Player,
    Projectile,
    SecretCache,
    Shopkeeper,
    Shrine,
    StoryGuest,
    Tile,
    Trap,
)
from ..quest_assets import (
    CutsceneActorAsset,
    SpriteAnimationFrameAsset,
    format_asset_text,
)


class RenderingWorldMixin:
    def draw_dungeon(self) -> None:
        min_x, max_x, min_y, max_y = self.visible_bounds()
        self._frame_dark = self.is_current_floor_dark()
        entries: list[tuple[pygame.Surface, tuple[int, int]]] = []
        for s in range(min_x + min_y, max_x + max_y + 1):
            for x in range(min_x, max_x + 1):
                y = s - x
                if min_y <= y <= max_y and self.dungeon.in_bounds(x, y):
                    if self.tile_visibility_alpha(x, y) <= 0:
                        continue
                    tile = self.dungeon.tiles[x][y]
                    if tile in (Tile.WALL, Tile.CLOSED_DOOR, Tile.OPEN_DOOR):
                        continue
                    entry = self._tile_blit_entry(x, y, tile)
                    if entry is not None:
                        entries.append(entry)
        if entries:
            blits = getattr(self.screen, "blits", None)
            if blits is not None:
                blits(entries)
            else:
                for src, dest in entries:
                    self.screen.blit(src, dest)

    def _tile_blit_entry(
        self, x: int, y: int, tile: Tile
    ) -> tuple[pygame.Surface, tuple[int, int]] | None:
        sx, sy = self.world_to_screen(x + 0.5, y + 0.5)
        # Cull tiles whose center is off-screen. `visible_bounds` pads the tile
        # radius for camera-smoothing safety, so the box corners sit outside the
        # viewport; skipping them avoids the tile_seed/tile_surface/shop work and
        # a blit for tiles the player never sees.
        sw, sh = self._screen_size()
        if sx < -TILE_W or sx > sw + TILE_W or sy < -TILE_H or sy > sh + TILE_H:
            return None
        seed = self.tile_seed(x, y)
        wall_guest_face = self.guest_wall_faces(x, y) if tile == Tile.WALL else None
        surface, anchor_x, anchor_y = self.tile_surface(
            tile,
            seed,
            self.is_shop_floor_tile(x, y),
            self.is_guest_tile(x, y),
            wall_guest_face,
        )
        if self._frame_dark:  # set at start of draw_world_objects/draw_dungeon
            alpha = self.tile_visibility_alpha(x, y)
            # Walls and doors are occluders: never render them translucent, or
            # the player can see floor/objects drawn behind them. Either draw
            # them fully opaque (within/just past the light radius) or skip
            # them entirely (handled by the cull in draw_world_objects). Only
            # floor tiles get the soft light-radius falloff.
            if tile not in (Tile.WALL, Tile.CLOSED_DOOR, Tile.OPEN_DOOR):
                if alpha <= 0:
                    return None
                if alpha < 255:
                    surface = self._alpha_tile_surface(surface, alpha)
        return (surface, (sx - anchor_x, sy - anchor_y))

    def draw_tile(self, x: int, y: int, tile: Tile) -> None:
        # Used by draw_world_objects for depth-sorted walls/doors (few of them);
        # the flat floor is batched in draw_dungeon via _tile_blit_entry.
        entry = self._tile_blit_entry(x, y, tile)
        if entry is not None:
            self.screen.blit(entry[0], entry[1])

    def _alpha_tile_surface(self, base: pygame.Surface, alpha: int) -> pygame.Surface:
        # Dark-floor light falloff: previously every frame did
        # `surface.copy(); surface.set_alpha(alpha)` per tile, allocating a fresh
        # surface ~289x/frame. Instead quantize alpha into a small set of buckets
        # and cache one set_alpha copy per (surface, bucket) so the hot loop only
        # blits. The cache is cleared on floor/theme change (prewarm_tile_cache).
        if alpha >= 255:
            return base
        cache = getattr(self, "_alpha_tile_cache", None)
        if cache is None:
            cache = {}
            self._alpha_tile_cache = cache
        bucket = min(7, alpha >> 5)  # 8 buckets over [0,255)
        key = (id(base), bucket)
        cached = cache.get(key)
        if cached is None:
            cached = base.copy()
            cached.set_alpha(bucket * 32 + 16)
            cache[key] = cached
        return cached

    def tile_seed(self, x: int, y: int) -> int:
        # Deterministic per-tile texture-variant index in
        # [0, max(DUNGEON_WALL_VARIANTS, DUNGEON_FLOOR_VARIANTS)). A mixing hash
        # avoids the visible axis streaks a naive `& 31` produces, and folding
        # into a tiny bounded range keeps the pre-generated tile cache small.
        h = (x * 73856093) ^ (y * 19349663)
        return h % max(DUNGEON_WALL_VARIANTS, DUNGEON_FLOOR_VARIANTS)

    def prewarm_tile_cache(self) -> None:
        # Pre-generate every wall/floor/shop texture variant for the current
        # theme so the first frame after a floor transition never pays the
        # procedural-draw cost, and the hot render loop only ever blits cached
        # surfaces. Called whenever the floor (and thus the theme) changes.
        # Also drop the dark-floor alpha-bucket cache since its keyed surfaces
        # belong to the previous theme.
        self._alpha_tile_cache = {}
        for tile in (Tile.WALL, Tile.FLOOR, Tile.STAIRS):
            variants = (
                DUNGEON_WALL_VARIANTS if tile == Tile.WALL else DUNGEON_FLOOR_VARIANTS
            )
            for seed in range(variants):
                self.tile_surface(tile, seed, shop_floor=False)
                if tile in (Tile.FLOOR, Tile.STAIRS):
                    self.tile_surface(tile, seed, shop_floor=True)
                if tile == Tile.WALL:
                    # Guest-room perimeter walls render the distinct art on one
                    # interior side face only; prewarm both face options.
                    self.tile_surface(
                        tile, seed, shop_floor=False, wall_guest_face="left"
                    )
                    self.tile_surface(
                        tile, seed, shop_floor=False, wall_guest_face="right"
                    )
                elif tile == Tile.FLOOR:
                    self.tile_surface(tile, seed, shop_floor=False, guest=True)

    def is_shop_floor_tile(self, x: int, y: int) -> bool:
        return self.is_special_room_floor_tile(x, y, kind="shop")

    def is_guest_tile(self, x: int, y: int) -> bool:
        # Interior guest-room floor only (not walls). Walls are handled per-face
        # by guest_wall_faces so the distinct wall art appears only on the
        # face that borders the room interior, not on the outside.
        return self.is_special_room_floor_tile(x, y, kind="quest_room")

    def is_special_room_floor_tile(
        self,
        x: int,
        y: int,
        kind: str | None = None,
        tag: str | None = None,
    ) -> bool:
        bounds = self._special_room_bounds(kind=kind, tag=tag)
        if bounds is None:
            return False
        rx, ry, rw, rh = bounds
        if not (rx < x < rx + rw - 1 and ry < y < ry + rh - 1):
            return False
        if not self.dungeon.in_bounds(x, y):
            return False
        return self.dungeon.tiles[x][y] in (Tile.FLOOR, Tile.STAIRS)

    def _special_room_interior_floor(
        self,
        x: int,
        y: int,
        kind: str | None = None,
        tag: str | None = None,
    ) -> bool:
        return self.is_special_room_floor_tile(x, y, kind=kind, tag=tag)

    def _guest_interior_floor(self, x: int, y: int) -> bool:
        # Compatibility wrapper for tests and old render helpers.
        return self._special_room_interior_floor(x, y, kind="quest_room")

    def guest_wall_faces(self, x: int, y: int) -> str | None:
        # For a wall tile on the guest-room perimeter, return which visible side
        # face borders the room interior: "left" (the +y face), "right" (the +x
        # face), or None. Only that face gets the distinct guest wall art, so the
        # markings never appear on the room's outside. Walls not on the guest
        # perimeter return None.
        if self.dungeon.tiles[x][y] != Tile.WALL:
            return None
        left_interior = self._special_room_interior_floor(x, y + 1, kind="quest_room")
        right_interior = self._special_room_interior_floor(x + 1, y, kind="quest_room")
        if left_interior:
            return "left"
        if right_interior:
            return "right"
        return None

    def _special_room_bounds(
        self,
        kind: str | None = None,
        tag: str | None = None,
        room_index: int | None = None,
    ) -> tuple[int, int, int, int] | None:
        cache = getattr(self, "_frame_cache", None)
        cache_key = ("special_room_bounds", kind, tag, room_index)
        if cache is not None and cache_key in cache:
            return cache[cache_key]  # type: ignore[no-any-return]
        special_room = None
        if room_index is not None:
            special_room = self.dungeon.special_room_at_index(room_index)
        elif kind is not None:
            special_room = self.dungeon.special_room_for_kind(kind)
        elif tag is not None:
            rooms = self.dungeon.special_rooms_with_tag(tag)
            special_room = rooms[0] if rooms else None
        result: tuple[int, int, int, int] | None = None
        if special_room is not None and 0 <= special_room.room_index < len(
            self.dungeon.rooms
        ):
            room = self.dungeon.rooms[special_room.room_index]
            result = (room.x, room.y, room.w, room.h)
        if cache is not None:
            cache[cache_key] = result
        return result

    def _shop_room_bounds(self) -> tuple[int, int, int, int] | None:
        return self._special_room_bounds(kind="shop")

    def _guest_room_bounds(self) -> tuple[int, int, int, int] | None:
        return self._special_room_bounds(kind="quest_room")

    def tile_surface(
        self,
        tile: Tile,
        seed: int,
        shop_floor: bool = False,
        guest: bool = False,
        wall_guest_face: str | None = None,
    ) -> tuple[pygame.Surface, int, int]:
        # ``wall_guest_face`` selects which side face of a WALL tile gets the
        # distinct guest-room wall art ("left"/"right"/None). Ignored for
        # non-wall tiles; floors/stairs use the ``guest`` flag instead.
        key = (
            self.theme.name,
            int(tile),
            seed,
            shop_floor,
            guest,
            wall_guest_face,
        )
        cached = self.tile_cache.get(key)
        if cached:
            return cached

        margin = 4 * WORLD_SCALE
        wall_h = (
            48 * WORLD_SCALE
            if tile in (Tile.WALL, Tile.CLOSED_DOOR, Tile.OPEN_DOOR)
            else 0
        )
        width = TILE_W + margin * 2
        height = TILE_H + wall_h + margin * 2
        surface = pygame.Surface((width, height), pygame.SRCALPHA)
        anchor_x = width // 2
        anchor_y = margin + wall_h + TILE_H // 2
        sx, sy = anchor_x, anchor_y
        top = (sx, sy - TILE_H // 2)
        right = (sx + TILE_W // 2, sy)
        bottom = (sx, sy + TILE_H // 2)
        left = (sx - TILE_W // 2, sy)

        if tile == Tile.WALL:
            self.draw_wall_tile_surface(
                surface,
                sx,
                sy,
                top,
                right,
                bottom,
                left,
                wall_h,
                seed,
                guest_face=wall_guest_face,
            )
        elif tile in (Tile.CLOSED_DOOR, Tile.OPEN_DOOR):
            self.draw_door_tile_surface(
                surface,
                sx,
                sy,
                top,
                right,
                bottom,
                left,
                wall_h,
                seed,
                tile == Tile.OPEN_DOOR,
                "right",
            )
        else:
            self.draw_floor_tile_surface(
                surface,
                sx,
                sy,
                top,
                right,
                bottom,
                left,
                tile,
                seed,
                shop_floor,
                guest=guest,
            )

        cached = (surface.convert_alpha(), anchor_x, anchor_y)
        self.tile_cache[key] = cached
        return cached

    def _wall_face_parallelogram(self, cap_a, cap_b, base_a, base_b):
        # Returns (top_left, top_right, bot_left, bot_right) describing a wall
        # side face as a parallelogram with a top edge (cap_a->cap_b) and a
        # bottom edge (base_a->base_b), ordered left-to-right so course/joint
        # interpolation is face-agnostic. The left face is built from
        # (cap_left, cap_bottom, left, bottom); the right face from
        # (cap_bottom, cap_right, bottom, right).
        return cap_a, cap_b, base_a, base_b

    def _draw_wall_masonry(
        self,
        surface: pygame.Surface,
        top_left,
        top_right,
        bot_left,
        bot_right,
        courses,
        joints_per_gap,
        color,
        scale: int,
    ) -> None:
        # Draw horizontal course lines at fractions `courses` (0 = cap edge,
        # 1 = base) and vertical joints within each gap between consecutive
        # course lines (and the cap edge / base). `joints_per_gap` has one
        # joint-fraction list per gap (len = len(courses) + 1).
        bounds = [0.0, *courses, 1.0]

        def course_pts(t: float):
            ax = top_left[0] + (bot_left[0] - top_left[0]) * t
            ay = top_left[1] + (bot_left[1] - top_left[1]) * t
            bx = top_right[0] + (bot_right[0] - top_right[0]) * t
            by = top_right[1] + (bot_right[1] - top_right[1]) * t
            return (ax, ay), (bx, by)

        for t in courses:
            a, b = course_pts(t)
            pygame.draw.line(surface, color, a, b, max(1, scale))
        for gi in range(len(bounds) - 1):
            t0, t1 = bounds[gi], bounds[gi + 1]
            a0, b0 = course_pts(t0)
            a1, b1 = course_pts(t1)
            for s in joints_per_gap[gi]:
                p0 = (a0[0] + (b0[0] - a0[0]) * s, a0[1] + (b0[1] - a0[1]) * s)
                p1 = (a1[0] + (b1[0] - a1[0]) * s, a1[1] + (b1[1] - a1[1]) * s)
                pygame.draw.line(surface, color, p0, p1, max(1, scale))

    def draw_wall_tile_surface(
        self,
        surface: pygame.Surface,
        sx: int,
        sy: int,
        top: tuple[int, int],
        right: tuple[int, int],
        bottom: tuple[int, int],
        left: tuple[int, int],
        wall_h: int,
        seed: int,
        guest_face: str | None = None,
    ) -> None:
        left_guest = guest_face == "left"
        right_guest = guest_face == "right"
        scale = WORLD_SCALE
        cap_top = (top[0], top[1] - wall_h)
        cap_right = (right[0], right[1] - wall_h)
        cap_bottom = (bottom[0], bottom[1] - wall_h)
        cap_left = (left[0], left[1] - wall_h)

        # Four coherent wall variants sharing palette, lighting, and
        # silhouette; they differ only in masonry pattern, so they read as the
        # same cut-stone wall with small, distinct character.
        variant = seed % DUNGEON_WALL_VARIANTS
        tint = variant * 2 - 3
        top_color = self.shade(self.theme.wall_top, 14 + tint)
        left_color = self.shade(self.theme.wall_left, tint)
        right_color = self.shade(self.theme.wall_right, tint)
        # Guest-room interior faces use a cooler/darker stone so the consecrated
        # chamber reads distinctly only on the inside; the outside stays normal.
        guest_left_color = self.shade(self.theme.wall_left, -6 + tint)
        guest_right_color = self.shade(self.theme.wall_right, -10 + tint)
        accent = (
            self.story_state.accent
            if getattr(self, "story_state", None) is not None
            else self.theme.accent
        )
        edge = self.shade(self.theme.wall_edge, 6)
        course_color = self.shade(edge, -34)
        course_hi = self.shade(course_color, 16)

        # Masonry pattern: variant-driven courses + joints, mirrored on both
        # faces so the wall reads as one continuous stone course wrapping the
        # pillar.
        if variant == 0:
            courses = (0.34, 0.66)
            joints = ([0.5], [0.5], [0.5])
        elif variant == 1:
            courses = (0.34, 0.66)
            joints = ([0.5], [0.28, 0.72], [0.5])
        elif variant == 2:
            courses = (0.5,)
            joints = ([0.5], [0.5])
        else:
            courses = (0.34, 0.66)
            joints = ([0.5], [0.5], [0.35, 0.7])

        left_face = self._wall_face_parallelogram(cap_left, cap_bottom, left, bottom)
        right_face = self._wall_face_parallelogram(cap_bottom, cap_right, bottom, right)
        # Side faces first (each in normal or guest style), then the cap on top.
        # The cap is always normal stone — the distinct guest art is for the
        # interior side faces only, never the top visible from outside.
        self._draw_wall_side_face(
            surface,
            left_face,
            guest_left_color if left_guest else left_color,
            courses,
            joints,
            course_color,
            course_hi,
            scale,
            guest=left_guest,
            accent=accent,
        )
        self._draw_wall_side_face(
            surface,
            right_face,
            guest_right_color if right_guest else right_color,
            courses,
            joints,
            course_color,
            course_hi,
            scale,
            guest=right_guest,
            accent=accent,
        )
        pygame.draw.polygon(
            surface, top_color, [cap_top, cap_right, cap_bottom, cap_left]
        )

        # --- Cap highlight: a single bright rim along the lit top-left edge.
        pygame.draw.line(
            surface, self.shade(top_color, 30), cap_top, cap_left, max(1, scale)
        )

        # --- Weathered variant: a short jagged crack down the left face for
        # ancient, broken character. Subtle and single so it stays in-family.
        if variant == 3:
            top_left, top_right, bot_left, bot_right = left_face
            crack = [
                (
                    top_left[0] + (top_right[0] - top_left[0]) * 0.78,
                    top_left[1] + (top_right[1] - top_left[1]) * 0.78,
                ),
                (
                    top_left[0]
                    + (bot_left[0] - top_left[0]) * 0.42
                    + (top_right[0] - top_left[0]) * 0.2,
                    top_left[1]
                    + (bot_left[1] - top_left[1]) * 0.42
                    + (top_right[1] - top_left[1]) * 0.2,
                ),
                (
                    top_left[0]
                    + (bot_left[0] - top_left[0]) * 0.62
                    + (top_right[0] - top_left[0]) * 0.12,
                    top_left[1]
                    + (bot_left[1] - top_left[1]) * 0.62
                    + (top_right[1] - top_left[1]) * 0.12,
                ),
            ]
            pygame.draw.lines(
                surface, self.shade(course_color, -18), False, crack, max(1, scale)
            )

        # --- Clean silhouette edges ---
        pygame.draw.lines(
            surface, edge, True, [cap_top, cap_right, cap_bottom, cap_left], scale
        )
        pygame.draw.line(surface, self.shade(edge, -14), cap_left, left, scale)
        pygame.draw.line(surface, self.shade(edge, -30), cap_right, right, scale)
        pygame.draw.line(surface, self.shade(edge, -50), cap_bottom, bottom, scale)
        pygame.draw.line(surface, self.shade(edge, -44), left, bottom, scale)
        pygame.draw.line(surface, self.shade(edge, -56), bottom, right, scale)

    def _draw_wall_side_face(
        self,
        surface: pygame.Surface,
        face_quad: tuple[
            tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]
        ],
        base_color: Color,
        courses: tuple[float, ...],
        joints: tuple,
        course_color: Color,
        course_hi: Color,
        scale: int,
        *,
        guest: bool = False,
        accent: Color | None = None,
    ) -> None:
        # Draw one side face of a wall (base fill + vertical gradient + masonry
        # + course lip), and when ``guest`` add the carved accent band so the
        # distinct consecrated-chamber wall art appears only on this (interior)
        # face. ``face_quad`` is (top_left, top_right, bot_left, bot_right).
        top_left, top_right, bot_left, bot_right = face_quad
        pygame.draw.polygon(
            surface, base_color, [top_left, top_right, bot_right, bot_left]
        )
        # Smooth vertical gradient: lighter upper third, darker lower third.
        for t0, t1, sh in ((0.0, 0.35, 10), (0.65, 1.0, -12)):
            lx0 = top_left[0] + (bot_left[0] - top_left[0]) * t0
            ly0 = top_left[1] + (bot_left[1] - top_left[1]) * t0
            lx1 = top_left[0] + (bot_left[0] - top_left[0]) * t1
            ly1 = top_left[1] + (bot_left[1] - top_left[1]) * t1
            rx0 = top_right[0] + (bot_right[0] - top_right[0]) * t0
            ry0 = top_right[1] + (bot_right[1] - top_right[1]) * t0
            rx1 = top_right[0] + (bot_right[0] - top_right[0]) * t1
            ry1 = top_right[1] + (bot_right[1] - top_right[1]) * t1
            pygame.draw.polygon(
                surface,
                self.shade(base_color, sh),
                [(lx0, ly0), (rx0, ry0), (rx1, ry1), (lx1, ly1)],
            )
        self._draw_wall_masonry(
            surface, *face_quad, courses, joints, course_color, scale
        )
        # Faint highlight along each top course line to read as a cut lip.
        for t in courses:
            ax = top_left[0] + (bot_left[0] - top_left[0]) * t
            ay = top_left[1] + (bot_left[1] - top_left[1]) * t
            bx = top_right[0] + (bot_right[0] - top_right[0]) * t
            by = top_right[1] + (bot_right[1] - top_right[1]) * t
            pygame.draw.line(
                surface, course_hi, (ax, ay - scale), (bx, by - scale), max(1, scale)
            )
        # Carved accent band near the top of the face — guest/interior only.
        if guest and accent is not None:
            band_t = 0.22
            band_color = self.shade(accent, -34)
            ax = top_left[0] + (bot_left[0] - top_left[0]) * band_t
            ay = top_left[1] + (bot_left[1] - top_left[1]) * band_t
            bx = top_right[0] + (bot_right[0] - top_right[0]) * band_t
            by = top_right[1] + (bot_right[1] - top_right[1]) * band_t
            pygame.draw.line(surface, band_color, (ax, ay), (bx, by), max(1, scale))
            pygame.draw.aalines(
                surface, self.shade(band_color, 14), False, [(ax, ay - 1), (bx, by - 1)]
            )

    def _floor_groove(
        self,
        surface: pygame.Surface,
        points: list[tuple[float, float]],
        slab: Color,
        thick: bool = False,
    ) -> None:
        # Render a flagstone joint or fracture as a carved groove rather than a
        # flat scratch: a soft shadowed recess with a faint lit lip on the
        # upper side (the floor is lit from above). Anti-aliased so the line
        # stays crisp without jagged aliasing, and low-contrast so the detail
        # reads as elegant tooling instead of a bold drawn-on mark. Drawing a
        # shadow core plus a one-pixel-up lit lip gives the joint real form
        # (a beveled recess), which is what separates high-end from cheap.
        if len(points) < 2:
            return
        shadow = self.shade(slab, -24)
        lip = self.shade(slab, 16)
        pygame.draw.aalines(surface, shadow, False, points)
        if thick:
            down = [(p[0], p[1] + 1) for p in points]
            pygame.draw.aalines(surface, shadow, False, down)
        up = [(p[0], p[1] - 1) for p in points]
        pygame.draw.aalines(surface, lip, False, up)

    def _draw_shop_checker_floor(self, surface, top, right, bottom, left, scale):
        # Polished checker-tile shop floor. A grout-colored diamond base shows
        # in the gaps; a 4x2 grid of 80px square tiles (two warm stone tones,
        # set in a checker) is clipped to the diamond, with per-cell top/bottom
        # shading and a global lit-from-above pass. The 80px cell size divides
        # both iso neighbor offsets (TILE_W/2=160, TILE_H/2=80), so the same
        # cached surface tiles seamlessly across adjacent shop floor diamonds.
        grout = (62, 54, 44)
        grout_edge = (40, 34, 28)
        tile_a = (138, 120, 96)
        tile_b = (118, 102, 80)
        diamond = [top, right, bottom, left]
        pygame.draw.polygon(surface, grout, diamond)
        pattern = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        cols, rows = 4, 2
        cw = TILE_W / cols
        ch = TILE_H / rows
        inset = 3
        bx, by = left[0], top[1]
        for i in range(cols):
            for j in range(rows):
                x0 = bx + i * cw
                y0 = by + j * ch
                color = tile_a if (i + j) % 2 == 0 else tile_b
                rect = pygame.Rect(
                    int(x0 + inset),
                    int(y0 + inset),
                    int(cw - 2 * inset),
                    int(ch - 2 * inset),
                )
                pygame.draw.rect(pattern, color, rect)
                pygame.draw.line(
                    pattern,
                    self.shade(color, 18),
                    (rect.x, rect.y),
                    (rect.right - 1, rect.y),
                    2,
                )
                pygame.draw.line(
                    pattern,
                    self.shade(color, -22),
                    (rect.x, rect.bottom - 1),
                    (rect.right - 1, rect.bottom - 1),
                    2,
                )
        mask = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        pygame.draw.polygon(mask, (255, 255, 255, 255), diamond)
        pattern.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        surface.blit(pattern, (0, 0))
        pygame.draw.polygon(surface, grout_edge, diamond, max(2, scale // 2))
        shade_surf = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        pygame.draw.line(shade_surf, (255, 255, 255, 28), top, left, max(2, scale))
        pygame.draw.line(shade_surf, (255, 255, 255, 18), top, right, max(2, scale))
        pygame.draw.line(shade_surf, (0, 0, 0, 38), left, bottom, max(2, scale))
        pygame.draw.line(shade_surf, (0, 0, 0, 28), right, bottom, max(2, scale))
        shade_surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        surface.blit(shade_surf, (0, 0))

    def _draw_guest_floor(self, surface, top, right, bottom, left, scale):
        # Consecrated chamber floor: a dim stone slab with a low-contrast
        # accent inlay (a small diamond insignia near the center) and a crisp
        # lit lip along the top-left edge. Reads as a ceremonial chamber, not a
        # glowing beacon.
        accent = (
            self.story_state.accent
            if getattr(self, "story_state", None) is not None
            else self.theme.accent
        )
        base = self.shade(self.theme.floor, -8)
        diamond = [top, right, bottom, left]
        pygame.draw.polygon(surface, base, diamond)
        cx = (top[0] + bottom[0]) // 2
        cy = (top[1] + bottom[1]) // 2
        # Insignia: a small accent-colored diamond outline near the center,
        # darkened so it reads as a carved groove rather than a glowing mark.
        insignia_color = self.shade(accent, -30)
        iw = 14 * scale
        ih = 7 * scale
        insignia = [
            (cx, cy - ih),
            (cx + iw, cy),
            (cx, cy + ih),
            (cx - iw, cy),
        ]
        pygame.draw.aalines(surface, insignia_color, True, insignia)
        # Inner dot of the insignia, faint.
        pygame.draw.aalines(
            surface,
            self.shade(insignia_color, -10),
            True,
            [
                (cx, cy - ih // 2),
                (cx + iw // 2, cy),
                (cx, cy + ih // 2),
                (cx - iw // 2, cy),
            ],
        )
        # Crisp lit lip along the top-left edge.
        pygame.draw.aalines(surface, self.shade(base, 18), False, [top, left])

    def draw_floor_tile_surface(
        self,
        surface: pygame.Surface,
        sx: int,
        sy: int,
        top: tuple[int, int],
        right: tuple[int, int],
        bottom: tuple[int, int],
        left: tuple[int, int],
        tile: Tile,
        seed: int,
        shop_floor: bool = False,
        guest: bool = False,
    ) -> None:
        is_stairs = tile == Tile.STAIRS
        scale = WORLD_SCALE
        # Shop floor: a polished checker-tile floor instead of the flagstone
        # slab, so the shop reads as a distinct tiled refuge. Stairs keep the
        # normal slab so the stairwell still integrates with the floor plane.
        if shop_floor and not is_stairs:
            self._draw_shop_checker_floor(surface, top, right, bottom, left, scale)
            return
        if guest and not is_stairs:
            self._draw_guest_floor(surface, top, right, bottom, left, scale)
            return
        # Stairs sit in the same flagstone slab as the surrounding floor (same
        # base color + per-variant tint) so the stairwell reads as an opening
        # cut into the continuous floor plane rather than a contrasting patch.
        # The spiral itself is drawn on top in the theme's stair color.
        base = self.theme.floor

        # Four coherent floor variants share a flat slab palette and differ
        # only in surface detail (seam / crack / cobble), so they read as one
        # continuous flagstone plane with scattered cracks rather than a grid
        # of beveled slabs. The old radial gradient + diamond outline darkened
        # every tile edge, which made the tile grid the dominant feature; a flat
        # fill lets adjacent tiles merge into a single stone surface.
        variant = seed % DUNGEON_FLOOR_VARIANTS
        tint = variant * 2 - 3
        slab = self.shade(base, tint)

        # --- Flat slab fill. No centered gradient, no inset bevel, no outline,
        # so neighboring tiles blend into a single continuous stone surface.
        # The per-variant tint (step 2, range -3..+3) gives gentle natural
        # mottling between adjacent different-variant tiles without drawing a
        # grid. For stairs this same floor slab opaquely fills the area outside
        # the stairwell circle, so the tile integrates with the floor plane. ---
        pygame.draw.polygon(surface, slab, [top, right, bottom, left])

        # --- Variant surface detail, rendered as carved grooves (shadowed
        # recess + lit lip, anti-aliased) rather than flat scratches, so the
        # tooling reads as high-end masonry. All joint coordinates are kept
        # inside the slab diamond (boundary |dx|/32s + |dy|/16s <= 1) so the
        # grooves never poke into the transparent tile margin. Stairs keep
        # their step motif instead so the descent reads clearly. ---
        if not is_stairs:
            if variant == 1:
                # A single hand-cut grout joint along the iso diagonal, gently
                # undulated so it does not look like a ruler-drawn scratch.
                self._floor_groove(
                    surface,
                    [
                        (sx - 14 * scale, sy - 6 * scale),
                        (sx - 5 * scale, sy - 3 * scale),
                        (sx + 5 * scale, sy + 2 * scale),
                        (sx + 14 * scale, sy + 7 * scale),
                    ],
                    slab,
                )
            elif variant == 2:
                # An organic fracture with a short branch, smoother than the
                # old 4-segment zigzag so it reads as a real crack in the stone.
                self._floor_groove(
                    surface,
                    [
                        (sx - 16 * scale, sy - 6 * scale),
                        (sx - 10 * scale, sy - 2 * scale),
                        (sx - 5 * scale, sy + 1 * scale),
                        (sx + 2 * scale, sy - 1 * scale),
                        (sx + 9 * scale, sy + 3 * scale),
                    ],
                    slab,
                )
                self._floor_groove(
                    surface,
                    [
                        (sx - 5 * scale, sy + 1 * scale),
                        (sx - 2 * scale, sy + 7 * scale),
                    ],
                    slab,
                )
            elif variant == 3:
                # Two parallel grout courses along the iso diagonal, offset
                # from the centerline, dividing the slab into laid-stone panels
                # (intentional masonry, not a random cross).
                self._floor_groove(
                    surface,
                    [
                        (sx - 14 * scale, sy - 2 * scale),
                        (sx - 6 * scale, sy + 2 * scale),
                        (sx + 2 * scale, sy + 6 * scale),
                        (sx + 10 * scale, sy + 10 * scale),
                    ],
                    slab,
                    thick=True,
                )
                self._floor_groove(
                    surface,
                    [
                        (sx - 10 * scale, sy - 10 * scale),
                        (sx - 2 * scale, sy - 6 * scale),
                        (sx + 6 * scale, sy - 2 * scale),
                        (sx + 14 * scale, sy + 2 * scale),
                    ],
                    slab,
                    thick=True,
                )
            # variant 0: smooth premium slab, no extra detail.

        # Gold-coin visuals now live on the shop floor as stacked-coin props
        # (see _gold_stack / draw_gold_stack), not as a per-tile inlay, so the
        # shop floor stays a continuous stone surface.

        if is_stairs:
            self._draw_spiral_staircase(surface, sx, sy, scale)

    def _draw_spiral_staircase(
        self, surface: pygame.Surface, cx: int, cy: int, scale: int
    ) -> None:
        # Spiral staircase descending into a round stone shaft. Each tread is a
        # FLAT block at its own height z = rise * i (clean discrete steps), and
        # only a PARTIAL arc of the helix is drawn (visible = total - 2) so the
        # deepest tread never sits adjacent to the entry tread -- that avoids
        # the seam where the next-loop-down step overlapped the top. The open
        # wedge is the shaft you look down into. Treads are painted deepest-first
        # so nearer/higher steps correctly occlude deeper ones. The recessed
        # stone frame is already painted by the slab fill.
        stair = self.theme.stair
        accent = self.theme.accent
        rx_o, ry_o = 21 * scale, 10 * scale
        rx_i, ry_i = 6 * scale, 3 * scale
        total = 12
        visible = total - 2  # partial arc; the missing wedge is the open shaft
        da = 2 * math.pi / total
        twist = da * 0.30  # rotate the inner ring so treads read as swept blades
        rise = int(1.2 * scale)  # per-tread vertical drop
        riser_h = int(2.6 * scale)  # height of the visible step lip
        front = math.pi / 2  # screen-down: the entry step faces the camera
        direction = -1  # wind clockwise from the entry step
        tread_dark = self.mix((14, 10, 16), stair, 0.18)
        tread_light = stair
        dim = 0.5

        def P(rx: int, ry: int, base_y: int, ang: float) -> tuple[int, int]:
            return (int(cx + rx * math.cos(ang)), int(base_y + ry * math.sin(ang)))

        # --- Shaft: radial gradient darker toward the center (deeper), with a
        # faint warm glow at the bottom (the landing far below) for depth. ---
        well_outer = self.mix((10, 8, 12), stair, 0.10)
        well_inner = self.mix((4, 3, 6), stair, 0.05)
        for r in range(8, 0, -1):
            t = r / 8
            pygame.draw.ellipse(
                surface,
                self.mix(well_inner, well_outer, t),
                (
                    cx - int(rx_o * t),
                    cy - int(ry_o * t),
                    int(rx_o * t * 2),
                    int(ry_o * t * 2),
                ),
            )
        glow = self.mix((4, 3, 6), (255, 210, 130), 0.18)
        pygame.draw.ellipse(surface, glow, (cx - rx_i, cy - ry_i, rx_i * 2, ry_i * 2))

        # --- Treads are drawn onto a separate layer and clipped to the
        # stairwell ellipse, so the z-shifted steps can never poke outside the
        # opening onto the floor -- you only see the stairs through the hole.
        # Painted deepest-first for correct occlusion. ---
        size = surface.get_size()
        layer = pygame.Surface(size, pygame.SRCALPHA)
        outer_t = [j / 6 for j in range(7)]
        inner_t = [j / 6 for j in range(6, -1, -1)]
        for i in reversed(range(visible)):
            c = front + direction * i * da
            z = rise * i
            a0, a1 = c - da / 2, c + da / 2
            base_y = cy + z
            outer = [P(rx_o, ry_o, base_y, a0 + (a1 - a0) * t) for t in outer_t]
            inner = [
                P(rx_i, ry_i, base_y, (a1 + twist) + ((a0 + twist) - (a1 + twist)) * t)
                for t in inner_t
            ]
            b = 1.0 - (i / (visible - 1)) * dim
            tread = self.mix(tread_dark, tread_light, b)
            # riser face under the leading (outer) edge
            outer_bot = [(x, y + riser_h) for (x, y) in outer]
            pygame.draw.polygon(layer, self.shade(tread, -55), outer + outer_bot[::-1])
            # inner side face (the wall toward the central shaft)
            side = [
                inner[0],
                outer[0],
                (outer[0][0], outer[0][1] + riser_h),
                (inner[0][0], inner[0][1] + riser_h),
            ]
            pygame.draw.polygon(layer, self.shade(tread, -26), side)
            # tread top + lit lip + inner shadow
            pygame.draw.polygon(layer, tread, outer + inner)
            pygame.draw.lines(layer, self.shade(tread, 42), False, outer, max(2, scale))
            pygame.draw.lines(layer, self.shade(tread, -28), False, inner, 1)
            # specular highlight on the two nearest (entry) steps
            if i < 2:
                pygame.draw.lines(
                    layer, self.shade(tread_light, 50), False, outer, max(1, scale)
                )
        # Clip the tread layer to the stairwell opening (opaque ellipse mask,
        # alpha-multiplied), then composite it over the shaft.
        mask = pygame.Surface(size, pygame.SRCALPHA)
        pygame.draw.ellipse(
            mask, (255, 255, 255, 255), (cx - rx_o, cy - ry_o, rx_o * 2, ry_o * 2)
        )
        layer.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(layer, (0, 0))

        # --- Lit outer rim: the stone lip of the stairwell, bright on the
        # camera-facing side, shadowed at the back. ---
        n = 48
        for k in range(n):
            a0 = 2 * math.pi * k / n
            a1 = 2 * math.pi * (k + 1) / n
            lit = (math.sin((a0 + a1) / 2 - front) + 1) / 2
            col = self.mix(self.shade(accent, -50), self.shade(accent, 55), lit)
            pygame.draw.line(
                surface,
                col,
                P(rx_o, ry_o, cy, a0),
                P(rx_o, ry_o, cy, a1),
                max(2, scale),
            )

    def draw_world_objects(self) -> None:
        drawables: list[tuple[float, str, object]] = []
        self._frame_dark = self.is_current_floor_dark()

        def visible(x: float, y: float, margin: float = 0.35) -> bool:
            # Live-object sight gate. On dark floors this is the lantern radius;
            # on light floors it is the fog-of-war sight radius (objects are not
            # remembered, only terrain is).
            return self.can_see_world_position(x, y, margin)

        min_x, max_x, min_y, max_y = self.visible_bounds()
        for s in range(min_x + min_y, max_x + max_y + 1):
            for x in range(min_x, max_x + 1):
                y = s - x
                if min_y <= y <= max_y and self.dungeon.in_bounds(x, y):
                    tile = self.dungeon.tiles[x][y]
                    if tile == Tile.WALL:
                        if self.tile_visibility_alpha(x, y) <= 0:
                            continue
                        drawables.append((x + y + 1.02, "wall_tile", (x, y)))
                    elif tile in (Tile.CLOSED_DOOR, Tile.OPEN_DOOR):
                        if self.tile_visibility_alpha(x, y) <= 0:
                            continue
                        drawables.append((x + y + 1.02, "door", (x, y, tile)))

        for item in self.items:
            if visible(item.x, item.y, 0.45):
                drawables.append((item.x + item.y, "item", item))
        for trap in self.traps:
            if visible(trap.x, trap.y, 0.20):
                drawables.append((trap.x + trap.y - 0.02, "trap", trap))
        for shrine in self.shrines:
            if visible(shrine.x, shrine.y, 0.55):
                drawables.append((shrine.x + shrine.y, "shrine", shrine))
        for secret in self.secrets:
            if (
                secret.revealed
                and not secret.opened
                and visible(secret.x, secret.y, 0.45)
            ):
                drawables.append((secret.x + secret.y, "secret", secret))
        for guest in self.story_guests:
            if visible(guest.x, guest.y, 0.55):
                drawables.append((guest.x + guest.y, "story_guest", guest))
        for shopkeeper in self.shopkeepers:
            if visible(shopkeeper.x, shopkeeper.y, 0.55):
                drawables.append(
                    (shopkeeper.x + shopkeeper.y, "shopkeeper", shopkeeper)
                )
        self._append_gold_stack_drawables(drawables, visible)
        for projectile in self.projectiles:
            if visible(projectile.x, projectile.y, 0.55):
                drawables.append(
                    (projectile.x + projectile.y, "projectile", projectile)
                )
        for enemy in self.enemies:
            if visible(enemy.x, enemy.y, 0.65) and self.has_line_of_sight_to_player(
                enemy.x, enemy.y
            ):
                drawables.append((enemy.x + enemy.y, "enemy", enemy))
        drawables.append((self.player.x + self.player.y, "player", self.player))
        for slash in self.slashes:
            x, y, _ttl, _dx, _dy = slash
            if visible(x, y, 0.55):
                drawables.append((x + y + 0.05, "slash", slash))
        for effect in self.impact_effects:
            if visible(effect.x, effect.y, max(0.35, effect.radius)):
                drawables.append((effect.x + effect.y + 0.08, "impact", effect))

        self.draw_aim_cone()
        # The guiding light leads the player TO the relic, so it must render
        # even when the relic is far outside the sight radius. The per-tile
        # visibility clipping inside draw_story_relic_guidance keeps the crack
        # from painting over dark / unrevealed floor.
        if self.story_relic_target_position() is not None:
            self.draw_story_relic_guidance()

        for _depth, kind, obj in sorted(drawables, key=lambda entry: entry[0]):
            if kind == "wall_tile":
                x, y = cast(tuple[int, int], obj)
                self.draw_tile(x, y, Tile.WALL)
            elif kind == "item":
                self.draw_item(cast(Item, obj))
            elif kind == "trap":
                self.draw_trap(cast(Trap, obj))
            elif kind == "shrine":
                self.draw_shrine(cast(Shrine, obj))
            elif kind == "secret":
                self.draw_secret(cast(SecretCache, obj))
            elif kind == "story_guest":
                self.draw_story_guest(cast(StoryGuest, obj))
            elif kind == "shopkeeper":
                self.draw_shopkeeper(cast(Shopkeeper, obj))
            elif kind == "gold_stack":
                gx, gy, gsize = cast(tuple[int, int, int], obj)
                self.draw_gold_stack(gx, gy, gsize)
            elif kind == "door":
                x, y, tile = cast(tuple[int, int, Tile], obj)
                self.draw_door(x, y, tile)
            elif kind == "projectile":
                self.draw_projectile(cast(Projectile, obj))
            elif kind == "enemy":
                self.draw_enemy(cast(Enemy, obj))
            elif kind == "player":
                self.draw_player(cast(Player, obj))
            elif kind == "slash":
                self.draw_slash(cast(SlashEffect, obj))
            elif kind == "impact":
                self.draw_impact(cast(ImpactEffect, obj))

        for floater in self.floaters:
            if not visible(floater.x, floater.y, 0.8):
                continue
            sx, sy = self.world_to_screen(floater.x, floater.y)
            alpha = max(0, min(255, int(255 * floater.ttl)))
            surface = self.font.render(floater.text, True, floater.color)
            surface.set_alpha(alpha)
            self.screen.blit(
                surface, surface.get_rect(center=(sx, sy - 34 * WORLD_SCALE))
            )

    def _append_gold_stack_drawables(self, drawables, visible) -> None:
        # Scattered gold-coin stacks on the shop floor. Placements are stable
        # for a given shop room (seeded from the room bounds) and cached per
        # frame so the scatter never flickers between frames.
        for gx, gy, gsize in self._shop_gold_stack_placements():
            if visible(gx + 0.5, gy + 0.5, 0.45):
                drawables.append((gx + gy + 0.5, "gold_stack", (gx, gy, gsize)))

    def _shop_gold_stack_placements(self) -> list[tuple[int, int, int]]:
        cache = getattr(self, "_frame_cache", None)
        if cache is not None and "gold_stack_placements" in cache:
            return cache["gold_stack_placements"]  # type: ignore[no-any-return]
        placements: list[tuple[int, int, int]] = []
        shop = self._shop_room_bounds()
        if shop is not None:
            rx, ry, rw, rh = shop
            avoid: set[tuple[int, int]] = set()
            for keeper in self.shopkeepers:
                avoid.add((int(keeper.x), int(keeper.y)))
            for it in self.items:
                if it.slot == "shop_sign":
                    avoid.add((int(it.x), int(it.y)))
            interior: list[tuple[int, int]] = []
            for x in range(rx + 1, rx + rw - 1):
                for y in range(ry + 1, ry + rh - 1):
                    if not self.dungeon.in_bounds(x, y):
                        continue
                    if self.dungeon.tiles[x][y] in (Tile.FLOOR, Tile.STAIRS):
                        if (x, y) not in avoid:
                            interior.append((x, y))
            if interior:
                interior.sort()
                seed = (
                    (rx * 73856093)
                    ^ (ry * 19349663)
                    ^ (rw * 83492791)
                    ^ (rh * 22345761)
                )
                rng = random.Random(seed)
                count = max(3, min(8, len(interior) // 3))
                stride = max(1, len(interior) // count)
                start = rng.randrange(stride) if stride else 0
                chosen = interior[start::stride][:count]
                sizes = [2, 1, 3, 2, 1, 3, 2, 1]
                rng.shuffle(sizes)
                for i, (tx, ty) in enumerate(chosen):
                    placements.append((tx, ty, sizes[i % len(sizes)]))
        if cache is not None:
            cache["gold_stack_placements"] = placements
        return placements

    def draw_gold_stack(self, x: int, y: int, size: int) -> None:
        sx, sy = self.world_to_screen(x + 0.5, y + 0.5)
        sprite = self.sprites.gold_stack_sprite(size)
        rect = sprite.get_rect(midbottom=(sx, sy + 2 * WORLD_SCALE))
        self.screen.blit(sprite, rect)

    def draw_door_tile_surface(
        self,
        surface: pygame.Surface,
        sx: int,
        sy: int,
        top: tuple[int, int],
        right: tuple[int, int],
        bottom: tuple[int, int],
        left: tuple[int, int],
        wall_h: int,
        seed: int,
        open_door: bool,
        face: str,
    ) -> None:
        self.draw_wall_tile_surface(
            surface, sx, sy, top, right, bottom, left, wall_h, seed
        )

        scale = WORLD_SCALE
        cap_left = (left[0], left[1] - wall_h)
        cap_right = (right[0], right[1] - wall_h)
        cap_bottom = (bottom[0], bottom[1] - wall_h)
        edge_color = self.shade(self.theme.wall_edge, 8)
        left_color = self.shade(self.theme.wall_left, -4)
        right_color = self.shade(self.theme.wall_right, -20)
        void = self.shade(self.theme.wall_right, -54)
        wood = self.mix(self.theme.wall_left, (100, 62, 36), 0.42)
        wood_dark = self.shade(wood, -36)
        metal = self.mix(self.theme.wall_edge, self.theme.accent, 0.16)

        def lerp(a: tuple[int, int], b: tuple[int, int], t: float) -> tuple[int, int]:
            return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t))

        def face_point(u: float, v: float) -> tuple[int, int]:
            if face == "left":
                upper = lerp(cap_left, cap_bottom, u)
                lower = lerp(left, bottom, u)
            else:
                upper = lerp(cap_bottom, cap_right, u)
                lower = lerp(bottom, right, u)
            return lerp(upper, lower, v)

        opening = [
            face_point(0.12, 0.16),
            face_point(0.88, 0.16),
            face_point(0.88, 0.98),
            face_point(0.12, 0.98),
        ]
        inset = [
            face_point(0.19, 0.24),
            face_point(0.81, 0.24),
            face_point(0.81, 0.94),
            face_point(0.19, 0.94),
        ]
        frame_color = self.mix(
            left_color if face == "left" else right_color, edge_color, 0.30
        )
        pygame.draw.polygon(surface, self.shade(frame_color, -30), opening)
        pygame.draw.polygon(surface, void, inset)
        pygame.draw.lines(surface, edge_color, True, opening, max(1, scale))

        for u in (0.12, 0.88):
            pygame.draw.line(
                surface,
                self.shade(edge_color, -18),
                face_point(u, 0.17),
                face_point(u, 0.98),
                max(1, scale),
            )
        pygame.draw.line(
            surface,
            self.shade(edge_color, 8),
            face_point(0.11, 0.16),
            face_point(0.89, 0.16),
            max(2, 2 * scale),
        )
        pygame.draw.line(
            surface,
            self.shade(edge_color, -24),
            face_point(0.09, 0.99),
            face_point(0.91, 0.99),
            max(1, scale),
        )

        if open_door:
            hinge_u = 0.24 if face == "right" else 0.76
            swing_u = 0.03 if face == "right" else 0.97
            panel = [
                face_point(hinge_u, 0.31),
                face_point(swing_u, 0.39),
                face_point(swing_u, 0.92),
                face_point(hinge_u, 0.88),
            ]
            pygame.draw.polygon(surface, wood_dark, panel)
            pygame.draw.lines(
                surface, self.shade(metal, -18), True, panel, max(1, scale)
            )
            for v in (0.48, 0.66, 0.82):
                pygame.draw.line(
                    surface,
                    self.shade(wood, 10),
                    face_point(hinge_u, v),
                    face_point(swing_u, v + 0.04),
                    max(1, scale),
                )
        else:
            panel = [
                face_point(0.22, 0.27),
                face_point(0.78, 0.27),
                face_point(0.78, 0.94),
                face_point(0.22, 0.94),
            ]
            pygame.draw.polygon(
                surface,
                wood_dark,
                [
                    face_point(0.18, 0.26),
                    face_point(0.82, 0.26),
                    face_point(0.82, 0.96),
                    face_point(0.18, 0.96),
                ],
            )
            pygame.draw.polygon(surface, wood, panel)
            pygame.draw.lines(
                surface, self.shade(metal, -18), True, panel, max(1, scale)
            )
            for v in (0.48, 0.66, 0.82):
                pygame.draw.line(
                    surface,
                    self.shade(wood, 12),
                    face_point(0.26, v),
                    face_point(0.74, v),
                    max(1, scale),
                )
            pygame.draw.line(
                surface,
                self.shade(wood, -18),
                face_point(0.50, 0.30),
                face_point(0.50, 0.93),
                max(1, scale),
            )
            pygame.draw.circle(
                surface,
                self.shade(metal, 18),
                face_point(0.70, 0.63),
                max(2, 2 * scale),
            )

    def door_render_face(self, x: int, y: int) -> str:
        doorish = (Tile.WALL, Tile.CLOSED_DOOR, Tile.OPEN_DOOR)
        x_axis = (
            self.dungeon.in_bounds(x - 1, y)
            and self.dungeon.in_bounds(x + 1, y)
            and self.dungeon.tiles[x - 1][y] in doorish
            and self.dungeon.tiles[x + 1][y] in doorish
        )
        y_axis = (
            self.dungeon.in_bounds(x, y - 1)
            and self.dungeon.in_bounds(x, y + 1)
            and self.dungeon.tiles[x][y - 1] in doorish
            and self.dungeon.tiles[x][y + 1] in doorish
        )
        if x_axis and not y_axis:
            return "left"
        if y_axis and not x_axis:
            return "right"
        return "left"

    def door_tile_surface(
        self, tile: Tile, seed: int, face: str
    ) -> tuple[pygame.Surface, int, int]:
        key = (self.theme.name, int(tile), seed, face)
        cache: dict[tuple[str, int, int, str], tuple[pygame.Surface, int, int]] = (
            getattr(self, "door_tile_cache", {})
        )
        cached = cache.get(key)
        if cached is not None:
            return cached

        margin = 4 * WORLD_SCALE
        wall_h = 48 * WORLD_SCALE
        width = TILE_W + margin * 2
        height = TILE_H + wall_h + margin * 2
        surface = pygame.Surface((width, height), pygame.SRCALPHA)
        anchor_x = width // 2
        anchor_y = margin + wall_h + TILE_H // 2
        local_sx, local_sy = anchor_x, anchor_y
        top = (local_sx, local_sy - TILE_H // 2)
        right = (local_sx + TILE_W // 2, local_sy)
        bottom = (local_sx, local_sy + TILE_H // 2)
        left = (local_sx - TILE_W // 2, local_sy)
        self.draw_door_tile_surface(
            surface,
            local_sx,
            local_sy,
            top,
            right,
            bottom,
            left,
            wall_h,
            seed,
            tile == Tile.OPEN_DOOR,
            face,
        )
        cached = (surface.convert_alpha(), anchor_x, anchor_y)
        cache[key] = cached
        self.door_tile_cache = cache
        return cached

    def draw_door(self, x: int, y: int, tile: Tile) -> None:
        sx, sy = self.world_to_screen(x + 0.5, y + 0.5)
        seed = self.tile_seed(x, y)
        surface, anchor_x, anchor_y = self.door_tile_surface(
            tile, seed, self.door_render_face(x, y)
        )
        # Doors are tall occluders like walls; never render them translucent in
        # dark mode or the player can see through them. Culling beyond the
        # light radius is handled in draw_world_objects.
        self.screen.blit(surface, (sx - anchor_x, sy - anchor_y))
