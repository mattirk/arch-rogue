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

# pyright: reportAttributeAccessIssue=false, reportUnusedImport=false
from __future__ import annotations

import math
import random
import time
from collections import deque
from typing import cast

import pygame

from ..constants import (
    DUNGEON_DEPTH,
    DUNGEON_FLOOR_VARIANTS,
    DUNGEON_WALL_VARIANTS,
    LIGHT_BAR_WALL_ELEVATION,
    TILE_H,
    TILE_W,
    WORLD_SCALE,
    SlashEffect,
)
from ..content import HUMANOID_ENEMY_NAMES
from ..mobile import (
    optimize_immutable_alpha_surface,
    sdl2_alpha_blitter_requested,
)
from ..models import (
    AmbushBell,
    Color,
    Enemy,
    Familiar,
    IdleNpc,
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


_DOOR_DIRECTIONS = (
    "south",
    "south-east",
    "east",
    "north-east",
    "north",
    "north-west",
    "west",
    "south-west",
)
_SPECIAL_WALL_ASSET_PREFIXES = {
    "quest_room": "wall_quest_room",
    "bar": "wall_bar",
    "garden": "wall_garden",
}
_GOLD_STACK_VARIANT_COUNT = 5
_GOLD_STACK_VARIANT_SALT = 0x4A17C0DE
_GOLD_STACK_EXTRA_SALT = 0x71D6B295


class RenderingWorldMixin:
    def draw_dungeon(self) -> None:
        if self._draw_cached_mobile_floor_layer():
            return
        self._blit_floor_entries(self.screen, self._floor_blit_entries())

    @staticmethod
    def _blit_floor_entries(
        target: pygame.Surface,
        entries: list[tuple[pygame.Surface, tuple[int, int]]],
    ) -> None:
        if not entries:
            return
        blits = getattr(target, "blits", None)
        if blits is not None:
            blits(entries)
        else:
            for source, destination in entries:
                target.blit(source, destination)

    def _floor_blit_entries(self) -> list[tuple[pygame.Surface, tuple[int, int]]]:
        min_x, max_x, min_y, max_y = self.visible_bounds()
        self._frame_dark = self.is_current_floor_dark()
        entries: list[tuple[pygame.Surface, tuple[int, int]]] = []
        for diagonal in range(min_x + min_y, max_x + max_y + 1):
            for x in range(min_x, max_x + 1):
                y = diagonal - x
                if min_y <= y <= max_y and self.dungeon.in_bounds(x, y):
                    if self.tile_visibility_alpha(x, y) <= 0:
                        continue
                    tile = self.dungeon.tiles[x][y]
                    if tile in (Tile.WALL, Tile.CLOSED_DOOR, Tile.OPEN_DOOR):
                        continue
                    entry = self._tile_blit_entry(x, y, tile)
                    if entry is not None:
                        entries.append(entry)
        return entries

    def _mobile_floor_entries_for_tiles(
        self, tiles: set[tuple[int, int]]
    ) -> list[tuple[pygame.Surface, tuple[int, int]]]:
        """Return canonical painter-order entries for a small reveal delta."""

        entries: list[tuple[pygame.Surface, tuple[int, int]]] = []
        for x, y in sorted(tiles, key=lambda point: (point[0] + point[1], point[0])):
            if not self.dungeon.in_bounds(x, y) or (x, y) not in self.revealed_tiles:
                continue
            tile = self.dungeon.tiles[x][y]
            if tile in (Tile.WALL, Tile.CLOSED_DOOR, Tile.OPEN_DOOR):
                continue
            entry = self._tile_blit_entry(x, y, tile)
            if entry is not None:
                entries.append(entry)
        return entries

    def _patch_cached_mobile_floor_layer(
        self,
        layer: pygame.Surface,
        build_camera: tuple[float, float],
        pending: set[tuple[int, int]],
        rendered: set[tuple[int, int]],
    ) -> int:
        # A flattened isometric layer cannot insert a new tile by simply drawing
        # it (or its neighbors) on top: that changes painter order and makes the
        # diamond look temporarily raised until the next cold rebuild. Rebuild
        # only each new tile's pixel rectangle, clipping every canonical floor
        # entry against that rectangle so the result is byte-equivalent locally.
        root_screen = self.screen
        frame_cache = self._frame_cache
        self.screen = layer
        self._frame_cache = {"camera_iso": build_camera}
        self._frame_dark = False
        try:
            all_entries = self._mobile_floor_entries_for_tiles(rendered | pending)
            pending_entries = self._mobile_floor_entries_for_tiles(pending)
        finally:
            self.screen = root_screen
            self._frame_cache = frame_cache

        dirty_rects = [
            source.get_rect(topleft=destination).clip(layer.get_rect())
            for source, destination in pending_entries
        ]
        previous_clip = layer.get_clip()
        try:
            for dirty in dirty_rects:
                if dirty.width <= 0 or dirty.height <= 0:
                    continue
                layer.fill((10, 10, 14), dirty)
                layer.set_clip(dirty)
                self._blit_floor_entries(
                    layer,
                    [
                        entry
                        for entry in all_entries
                        if entry[0]
                        .get_rect(topleft=entry[1])
                        .colliderect(dirty)
                    ],
                )
        finally:
            layer.set_clip(previous_clip)
        return len(pending_entries)

    @staticmethod
    def _mobile_floor_layer_destination(
        screen_size: tuple[int, int],
        layer: pygame.Surface,
        build_camera: tuple[float, float],
        live_camera: tuple[float, float],
    ) -> tuple[int, int]:
        # world_to_screen uses int() on positive on-screen coordinates, which is
        # floor semantics. Compute the translation from the same two projected
        # origins; round() changes at a different half-pixel boundary and caused
        # the cached floor to jump one pixel relative to live walls and actors.
        screen_w, screen_h = screen_size
        build_cam_x, build_cam_y = build_camera
        cam_x, cam_y = live_camera
        return (
            math.floor(-cam_x + screen_w * 0.5)
            - math.floor(-build_cam_x + layer.get_width() * 0.5),
            math.floor(-cam_y + screen_h * 0.48)
            - math.floor(-build_cam_y + layer.get_height() * 0.48),
        )

    def _draw_cached_mobile_floor_layer(self) -> bool:
        """Blit a reusable opaque floor layer on the Android SDL2-alpha path."""

        if (
            not getattr(self, "mobile_mode", False)
            or not sdl2_alpha_blitter_requested()
            or self.is_current_floor_dark()
        ):
            return False
        screen_w, screen_h = self._screen_size()
        if screen_w <= 0 or screen_h <= 0:
            return False

        cam_x, cam_y = self.camera_iso()
        # A one-third-screen gutter keeps the layer reusable for several world
        # steps instead of rebuilding roughly once per tile while the camera
        # follows the player. Native mode pays a bounded ~1.8x surface dimension,
        # replacing frequent alpha-tile rebuilds with one opaque translated blit.
        margin_x = max(TILE_W, screen_w // 3)
        margin_y = max(TILE_H, screen_h // 3)
        layer_size = (screen_w + margin_x * 2, screen_h + margin_y * 2)
        story_accent = tuple(getattr(getattr(self, "story_state", None), "accent", ()))
        lightweight_lighting = self.mobile_lightweight_lighting_active()
        ambient_tint = (
            self._mobile_lightweight_ambient_color()
            if lightweight_lighting
            else None
        )
        cache_key = (
            id(self.dungeon),
            getattr(self, "run_number", 0),
            getattr(self, "current_depth", 0),
            self.theme.name,
            story_accent,
            layer_size,
            round(float(getattr(self, "view_zoom", 1.0)), 4),
            bool(getattr(self, "legacy_graphics", False)),
            bool(self.continuous_lighting_active()),
            lightweight_lighting,
            ambient_tint,
            id(self.revealed_tiles),
        )
        cache = getattr(self, "_mobile_floor_layer_cache", None)
        rebuild = cache is None or cache[0] != cache_key
        if not rebuild:
            assert cache is not None
            build_cam_x, build_cam_y = cache[1], cache[2]
            rebuild = (
                abs(cam_x - build_cam_x) >= margin_x * 0.75
                or abs(cam_y - build_cam_y) >= margin_y * 0.75
            )
            if not rebuild:
                rendered = cache[4]
                rebuild = not rendered.issubset(self.revealed_tiles)

        if rebuild:
            layer = pygame.Surface(layer_size).convert()
            layer.fill((10, 10, 14))
            root_screen = self.screen
            frame_cache = self._frame_cache
            self.screen = layer
            self._frame_cache = {}
            try:
                entries = self._floor_blit_entries()
            finally:
                self.screen = root_screen
                self._frame_cache = frame_cache
            self._blit_floor_entries(layer, entries)
            cache = (
                cache_key,
                cam_x,
                cam_y,
                layer,
                set(self.revealed_tiles),
            )
            self._mobile_floor_layer_cache = cache
            self._mobile_floor_cache_rebuilds = int(
                getattr(self, "_mobile_floor_cache_rebuilds", 0)
            ) + 1
        else:
            assert cache is not None
            rendered = cache[4]
            pending = self.revealed_tiles.difference(rendered)
            if pending:
                patched = self._patch_cached_mobile_floor_layer(
                    cache[3],
                    (cache[1], cache[2]),
                    pending,
                    rendered,
                )
                rendered.update(pending)
                if patched:
                    self._mobile_floor_cache_patches = int(
                        getattr(self, "_mobile_floor_cache_patches", 0)
                    ) + 1

        assert cache is not None
        build_cam_x, build_cam_y, layer = cache[1], cache[2], cache[3]
        destination = self._mobile_floor_layer_destination(
            (screen_w, screen_h),
            layer,
            (build_cam_x, build_cam_y),
            (cam_x, cam_y),
        )
        self.screen.blit(layer, destination)
        return True

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
        wall_face_style = self.special_wall_faces(x, y) if tile == Tile.WALL else None
        bar_wall_light_side = (
            self.bar_wall_light_side(x, y) if tile == Tile.WALL else None
        )
        surface, anchor_x, anchor_y = self.tile_surface(
            tile,
            seed,
            shop_floor=self.is_shop_floor_tile(x, y),
            guest=self.is_guest_tile(x, y),
            bar_floor=self.is_bar_tile(x, y),
            garden_floor=self.is_garden_tile(x, y),
            wall_face_style=wall_face_style,
            bar_wall_light_side=bar_wall_light_side,
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
                # Continuous lighting replaces per-tile alpha with a screen-space
                # multiply. Lighting Off, web, and Android Native's lightweight
                # tier retain the quantized tile falloff so no native framebuffer
                # transfer is required to preserve darkness.
                if alpha < 255 and not self.continuous_lighting_active():
                    surface = self._alpha_tile_surface(surface, alpha)
        if self.mobile_lightweight_lighting_active():
            surface = self.apply_mobile_lightweight_ambient(surface)
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
        self.door_tile_cache = {}
        self._mobile_floor_layer_cache = None
        # Milestone 3.16: lighting caches are keyed by theme accent and
        # per-sprite identity, so reset them on floor/theme change alongside
        # the alpha-bucket cache.
        if hasattr(self, "reset_lighting_caches"):
            self.reset_lighting_caches()
        # Per-kind interior wall face styles (one side face gets distinct art).
        wall_face_styles: list[str | None] = [None]
        for kind in ("quest_room", "bar", "garden"):
            for side in ("left", "right"):
                wall_face_styles.append(f"{kind}:{side}")
        for tile in (Tile.WALL, Tile.FLOOR, Tile.STAIRS):
            variants = (
                DUNGEON_WALL_VARIANTS if tile == Tile.WALL else DUNGEON_FLOOR_VARIANTS
            )
            for seed in range(variants):
                if tile == Tile.WALL:
                    for style in wall_face_styles:
                        self.tile_surface(
                            tile, seed, shop_floor=False, wall_face_style=style
                        )
                    for side in ("left", "right"):
                        self.tile_surface(
                            tile,
                            seed,
                            shop_floor=False,
                            wall_face_style=f"bar:{side}",
                            bar_wall_light_side=side,
                        )
                else:
                    self.tile_surface(tile, seed, shop_floor=False)
                    self.tile_surface(tile, seed, shop_floor=True)
                    if tile == Tile.FLOOR:
                        # Special-room floor art only applies to FLOOR tiles;
                        # stairs keep the normal slab in every special room, so
                        # they are not prewarmed with these flags (avoids
                        # wasting cache entries on identical stairs surfaces).
                        self.tile_surface(tile, seed, shop_floor=False, guest=True)
                        self.tile_surface(tile, seed, shop_floor=False, bar_floor=True)
                        self.tile_surface(
                            tile, seed, shop_floor=False, garden_floor=True
                        )
        door_orientations = (
            _DOOR_DIRECTIONS
            if self.sprites.modern_graphics_active
            else ("left", "right")
        )
        for tile in (Tile.CLOSED_DOOR, Tile.OPEN_DOOR):
            for seed in range(DUNGEON_WALL_VARIANTS):
                for orientation in door_orientations:
                    self.door_tile_surface(tile, seed, orientation)

    def is_shop_floor_tile(self, x: int, y: int) -> bool:
        return self.is_special_room_floor_tile(x, y, kind="shop")

    def is_guest_tile(self, x: int, y: int) -> bool:
        # Interior guest-room floor only (not walls). Walls are handled per-face
        # by guest_wall_faces so the distinct wall art appears only on the
        # face that borders the room interior, not on the outside.
        return self.is_special_room_floor_tile(x, y, kind="quest_room")

    def is_bar_tile(self, x: int, y: int) -> bool:
        # 3.14 flavor room: tavern floor. Distinct floor art; perimeter walls get
        # warm wood-panel art on the interior face via special_wall_faces.
        return self.is_special_room_floor_tile(x, y, kind="bar")

    def is_garden_tile(self, x: int, y: int) -> bool:
        # 3.14 flavor room: overgrown garden floor. Perimeter walls get moss/vine
        # art on the interior face via special_wall_faces.
        return self.is_special_room_floor_tile(x, y, kind="garden")

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
        # Backwards-compatible wrapper: returns the legacy bare side string
        # ("left"/"right") for the quest-room perimeter, or None. New code should
        # call `special_wall_faces` which returns a "<kind>:<side>" style.
        style = self.special_wall_faces(x, y)
        if style is None:
            return None
        kind, side = self._parse_wall_face_style(style)
        if kind == "quest_room":
            return side
        return None

    def special_wall_faces(self, x: int, y: int) -> str | None:
        # For a wall tile on a special-room perimeter, return which visible side
        # face borders the room interior as a "<kind>:<side>" style string
        # (e.g. "quest_room:left", "bar:right", "garden:left"), or None. Only that
        # face gets the distinct interior wall art, so the markings never appear
        # on the room's outside. The first matching kind/side wins (a wall rarely
        # borders two special rooms). ``side`` is "left" (the +y face) or
        # "right" (the +x face).
        if self.dungeon.tiles[x][y] != Tile.WALL:
            return None
        for kind in ("quest_room", "bar", "garden"):
            left_interior = self._special_room_interior_floor(x, y + 1, kind=kind)
            if left_interior:
                return f"{kind}:left"
            right_interior = self._special_room_interior_floor(x + 1, y, kind=kind)
            if right_interior:
                return f"{kind}:right"
        return None

    def bar_wall_light_side(self, x: int, y: int) -> str | None:
        cache = getattr(self, "_frame_cache", None)
        cache_key = "bar_wall_light_mounts"
        mounts = cache.get(cache_key) if cache is not None else None
        if mounts is None:
            mounts = {}
            special_room = self.dungeon.special_room_for_kind("bar")
            if special_room is not None:
                for side in ("left", "right"):
                    tile = special_room.anchor(f"bar_wall_light_{side}")
                    if tile is not None:
                        mounts[tile] = side
            if cache is not None:
                cache[cache_key] = mounts
        return mounts.get((x, y))

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
        bar_floor: bool = False,
        garden_floor: bool = False,
        wall_face_style: str | None = None,
        bar_wall_light_side: str | None = None,
    ) -> tuple[pygame.Surface, int, int]:
        # ``wall_face_style`` is "<kind>:<side>" (or legacy "left"/"right") and
        # selects which side face of a WALL tile gets distinct interior wall art.
        # ``shop_floor`` / ``guest`` / ``bar_floor`` / ``garden_floor`` select the
        # floor art for the four special-room floor kinds; they are mutually
        # exclusive in practice (a tile belongs to at most one special room).
        key = (
            self.theme.name,
            int(tile),
            seed,
            shop_floor,
            guest,
            bar_floor,
            garden_floor,
            wall_face_style,
            bar_wall_light_side,
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
        anchor_x = width // 2
        anchor_y = margin + wall_h + TILE_H // 2
        asset_key = ""
        tint = self.theme.floor
        if tile == Tile.WALL:
            asset_key = "wall"
            tint = self.mix(self.theme.wall_top, self.theme.wall_left, 0.42)
        elif tile == Tile.STAIRS:
            asset_key = "stairs"
            tint = self.theme.stair
        elif tile == Tile.CLOSED_DOOR:
            asset_key = "door_closed"
            tint = self.theme.wall_top
        elif tile == Tile.OPEN_DOOR:
            asset_key = "door_open"
            tint = self.theme.wall_top
        elif garden_floor:
            asset_key = "garden_floor"
        elif bar_floor:
            asset_key = "bar_floor"
        elif guest:
            asset_key = "quest_floor"
        elif shop_floor:
            asset_key = "shop_floor"
        else:
            asset_key = "floor"
        accent = (
            self.story_state.accent
            if getattr(self, "story_state", None) is not None
            else self.theme.accent
        )
        asset_canvas = (width, height)
        asset_anchor = (anchor_x, anchor_y)
        if tile == Tile.STAIRS:
            # The authored stairwell occupies a full isometric block. Give it a
            # taller transparent canvas so its upper rim and descending steps
            # remain intact instead of clipping them into the flat-floor canvas.
            asset_canvas = (width, TILE_W + margin * 2)
            asset_anchor = (anchor_x, margin + TILE_W * 5 // 8)
        asset_surface = None
        if tile == Tile.WALL and wall_face_style:
            face_kind, face_side = self._parse_wall_face_style(wall_face_style)
            prefix = _SPECIAL_WALL_ASSET_PREFIXES.get(face_kind or "")
            if prefix is not None and face_side is not None:
                asset_surface = self.sprites.world_tile_surface(
                    f"{prefix}_{face_side}",
                    target_canvas=asset_canvas,
                    target_anchor=asset_anchor,
                    tint=tint,
                    accent=accent,
                    variant=seed,
                )
        if asset_surface is None:
            # Missing 4.0.1 variants intentionally fall back one resource at a
            # time. For special walls this preserves the 4.0 generic wall plus
            # procedural face decoration instead of disabling modern graphics.
            asset_surface = self.sprites.world_tile_surface(
                asset_key,
                target_canvas=asset_canvas,
                target_anchor=asset_anchor,
                tint=tint,
                accent=accent,
                variant=seed,
                wall_face_style=wall_face_style,
            )
        if asset_surface is not None:
            wall_surface, wall_anchor_x, wall_anchor_y = asset_surface
            if tile == Tile.WALL and bar_wall_light_side is not None:
                wall_surface = wall_surface.copy()
                self._draw_bar_wall_light(
                    wall_surface,
                    wall_anchor_x,
                    wall_anchor_y,
                    bar_wall_light_side,
                )
            wall_surface = optimize_immutable_alpha_surface(wall_surface)
            asset_surface = (wall_surface, wall_anchor_x, wall_anchor_y)
            self.tile_cache[key] = asset_surface
            return asset_surface

        surface = pygame.Surface((width, height), pygame.SRCALPHA)
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
                wall_face_style=wall_face_style,
            )
            if bar_wall_light_side is not None:
                self._draw_bar_wall_light(
                    surface, anchor_x, anchor_y, bar_wall_light_side
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
                bar_floor=bar_floor,
                garden_floor=garden_floor,
            )

        surface = optimize_immutable_alpha_surface(surface.convert_alpha())
        cached = (surface, anchor_x, anchor_y)
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
        wall_face_style: str | None = None,
    ) -> None:
        # ``wall_face_style`` is "<kind>:<side>" (e.g. "quest_room:left",
        # "bar:right", "garden:left") or None. Only the named side face gets the
        # distinct interior wall art for that special room; the other face and the
        # cap stay normal dungeon stone so the room reads as found, not sealed.
        face_kind, face_side = self._parse_wall_face_style(wall_face_style)
        left_kind = face_kind if face_side == "left" else None
        right_kind = face_kind if face_side == "right" else None
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
        # Side faces first (each in normal or special-room style), then the cap.
        # The cap is always normal stone — distinct art is for the interior side
        # faces only, never the top visible from outside.
        self._draw_wall_side_face(
            surface,
            left_face,
            self._wall_face_base_color("left", left_kind, tint),
            courses,
            joints,
            course_color,
            course_hi,
            scale,
            face_kind=left_kind,
            accent=accent,
        )
        self._draw_wall_side_face(
            surface,
            right_face,
            self._wall_face_base_color("right", right_kind, tint),
            courses,
            joints,
            course_color,
            course_hi,
            scale,
            face_kind=right_kind,
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
        # Only on plain (non-special) walls so it never clashes with interior art.
        if variant == 3 and left_kind is None:
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

    def _parse_wall_face_style(
        self, style: str | None
    ) -> tuple[str | None, str | None]:
        # ``style`` is "<kind>:<side>" or None/"<side>" (legacy guest form).
        if not style:
            return None, None
        if ":" not in style:
            # Legacy bare side string → quest_room (the original guest-room face).
            if style in ("left", "right"):
                return "quest_room", style
            return None, None
        kind, _, side = style.partition(":")
        if side not in ("left", "right"):
            return None, None
        return kind or None, side

    def _wall_face_base_color(self, side: str, kind: str | None, tint: int) -> Color:
        base = self.shade(
            self.theme.wall_left if side == "left" else self.theme.wall_right, tint
        )
        if kind == "quest_room":
            # Cooler/darker consecrated stone; left face is lit so it stays a touch
            # lighter than the right.
            return self.shade(base, -6 if side == "left" else -10)
        if kind == "bar":
            # Warm wood-paneled stone: mix toward aged oak so the tavern reads
            # warmly without abandoning the dungeon palette.
            return self.mix(base, (120, 84, 52), 0.55)
        if kind == "garden":
            # Moss-veined stone: mix toward damp green so the garden reads as
            # reclaimed by growth.
            return self.mix(base, (80, 108, 72), 0.45)
        return base

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
        face_kind: str | None = None,
        accent: Color | None = None,
    ) -> None:
        # Draw one side face of a wall (base fill + vertical gradient + masonry
        # + course lip), and when ``face_kind`` is set add the per-room interior
        # wall art so the distinct chamber markings appear only on this (interior)
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
        # Bar wood paneling replaces the cut-stone masonry with horizontal plank
        # grooves; quest_room/garden keep the stone courses.
        if face_kind != "bar":
            self._draw_wall_masonry(
                surface, *face_quad, courses, joints, course_color, scale
            )
        # Faint highlight along each top course line to read as a cut lip
        # (stone faces only; bar planks draw their own lip below).
        if face_kind != "bar":
            for t in courses:
                ax = top_left[0] + (bot_left[0] - top_left[0]) * t
                ay = top_left[1] + (bot_left[1] - top_left[1]) * t
                bx = top_right[0] + (bot_right[0] - top_right[0]) * t
                by = top_right[1] + (bot_right[1] - top_right[1]) * t
                pygame.draw.line(
                    surface,
                    course_hi,
                    (ax, ay - scale),
                    (bx, by - scale),
                    max(1, scale),
                )
        if face_kind == "quest_room" and accent is not None:
            self._draw_quest_wall_band(
                surface, top_left, top_right, bot_left, bot_right, accent, scale
            )
        elif face_kind == "bar":
            self._draw_bar_wall_planks(
                surface, top_left, top_right, bot_left, bot_right, base_color, scale
            )
        elif face_kind == "garden":
            self._draw_garden_wall_vines(
                surface, top_left, top_right, bot_left, bot_right, base_color, scale
            )

    def _face_h_line(
        self,
        top_left: tuple[int, int],
        top_right: tuple[int, int],
        bot_left: tuple[int, int],
        bot_right: tuple[int, int],
        t: float,
    ) -> tuple[tuple[float, float], tuple[float, float]]:
        # A horizontal (iso-projected) line across the face at vertical fraction t.
        a = (
            top_left[0] + (bot_left[0] - top_left[0]) * t,
            top_left[1] + (bot_left[1] - top_left[1]) * t,
        )
        b = (
            top_right[0] + (bot_right[0] - top_right[0]) * t,
            top_right[1] + (bot_right[1] - top_right[1]) * t,
        )
        return a, b

    def _draw_quest_wall_band(
        self,
        surface: pygame.Surface,
        top_left: tuple[int, int],
        top_right: tuple[int, int],
        bot_left: tuple[int, int],
        bot_right: tuple[int, int],
        accent: Color,
        scale: int,
    ) -> None:
        # Carved accent band near the top of the face — consecrated-chamber mark.
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

    def _draw_bar_wall_light(
        self,
        surface: pygame.Surface,
        anchor_x: int,
        anchor_y: int,
        side: str,
    ) -> None:
        if side not in ("left", "right"):
            return
        direction = -1 if side == "left" else 1
        # Static bar lights sit half a world tile inward from their wall tile,
        # which projects them TILE_H/4 downward. Subtracting the shared elevation
        # here keeps the visible fixture centered on its light halo.
        mount = (
            anchor_x + direction * TILE_W // 4,
            anchor_y
            - round(LIGHT_BAR_WALL_ELEVATION * TILE_H)
            + TILE_H // 4,
        )
        frame = self.sprites.bar_wall_sconce_visual(side)
        if frame is not None:
            surface.blit(
                frame.surface,
                (mount[0] - frame.anchor[0], mount[1] - frame.anchor[1]),
            )
            return

        # Legacy/missing-asset fallback: a compact iron backplate, bracket,
        # beeswax candle, and flame drawn directly onto the selected wall face.
        scale = WORLD_SCALE
        iron = (39, 31, 27)
        iron_hi = (92, 69, 47)
        wax = (219, 178, 104)
        flame = (255, 174, 54)
        pygame.draw.circle(surface, iron, mount, 5 * scale)
        pygame.draw.circle(surface, iron_hi, mount, 5 * scale, max(1, scale))
        bracket_end = (
            mount[0] + direction * 8 * scale,
            mount[1] + 3 * scale,
        )
        pygame.draw.line(surface, iron, mount, bracket_end, max(2, 2 * scale))
        candle = pygame.Rect(0, 0, 5 * scale, 12 * scale)
        candle.midbottom = (bracket_end[0], bracket_end[1] + scale)
        pygame.draw.rect(surface, iron, candle.inflate(2 * scale, 2 * scale))
        pygame.draw.rect(surface, wax, candle)
        flame_points = [
            (candle.centerx, candle.top - 7 * scale),
            (candle.centerx + 3 * scale, candle.top - scale),
            (candle.centerx, candle.top + scale),
            (candle.centerx - 3 * scale, candle.top - scale),
        ]
        pygame.draw.polygon(surface, flame, flame_points)
        pygame.draw.circle(
            surface,
            (255, 232, 132),
            (candle.centerx, candle.top - 2 * scale),
            max(1, scale),
        )

    def _draw_bar_wall_planks(
        self,
        surface: pygame.Surface,
        top_left: tuple[int, int],
        top_right: tuple[int, int],
        bot_left: tuple[int, int],
        bot_right: tuple[int, int],
        base_color: Color,
        scale: int,
    ) -> None:
        # Horizontal wood-plank grooves (shadowed recess + lit lip) reading as
        # aged paneling. Five courses evenly spaced, with a per-plank seam offset
        # so it does not look like ruled lines.
        groove = self.shade(base_color, -34)
        lip = self.shade(base_color, 16)
        planks = (0.20, 0.42, 0.64, 0.86)
        for t in planks:
            a, b = self._face_h_line(top_left, top_right, bot_left, bot_right, t)
            pygame.draw.aalines(surface, groove, False, [a, b])
            pygame.draw.aalines(
                surface, lip, False, [(a[0], a[1] - 1), (b[0], b[1] - 1)]
            )
        # A short vertical plank seam near one-third, gently offset.
        seam_t = 0.34
        top_a, top_b = self._face_h_line(top_left, top_right, bot_left, bot_right, 0.08)
        mid_a, mid_b = self._face_h_line(top_left, top_right, bot_left, bot_right, 0.52)
        sx = top_a[0] + (top_b[0] - top_a[0]) * seam_t
        sy = top_a[1] + (top_b[1] - top_a[1]) * seam_t
        ex = mid_a[0] + (mid_b[0] - mid_a[0]) * seam_t
        ey = mid_a[1] + (mid_b[1] - mid_a[1]) * seam_t
        pygame.draw.aalines(surface, groove, False, [(sx, sy), (ex, ey)])

    def _draw_garden_wall_vines(
        self,
        surface: pygame.Surface,
        top_left: tuple[int, int],
        top_right: tuple[int, int],
        bot_left: tuple[int, int],
        bot_right: tuple[int, int],
        base_color: Color,
        scale: int,
    ) -> None:
        # Moss and creeping vines: a few low-contrast green splotches and a
        # wandering vine line, deterministic from the face geometry so cached
        # surfaces stay stable. Subtle so it reads as weathered growth, not a
        # painted mural.
        moss = self.mix(base_color, (96, 132, 84), 0.55)
        vine = self.shade(moss, -18)
        # Two moss patches near the lower corners (damp collects at the base).
        for corner_t, side_t in ((0.82, 0.18), (0.78, 0.80)):
            a, b = self._face_h_line(top_left, top_right, bot_left, bot_right, corner_t)
            cx = a[0] + (b[0] - a[0]) * side_t
            cy = a[1] + (b[1] - a[1]) * side_t
            pygame.draw.circle(surface, moss, (int(cx), int(cy)), max(2, scale))
        # A wandering vine down the upper-middle of the face.
        pts: list[tuple[float, float]] = []
        for vt, hs in ((0.16, 0.50), (0.40, 0.40), (0.62, 0.58), (0.86, 0.46)):
            a, b = self._face_h_line(top_left, top_right, bot_left, bot_right, vt)
            pts.append((a[0] + (b[0] - a[0]) * hs, a[1] + (b[1] - a[1]) * hs))
        pygame.draw.aalines(surface, vine, False, pts)
        # Faint leaf motes along the vine.
        for px, py in pts:
            pygame.draw.circle(
                surface, self.shade(moss, 8), (int(px), int(py)), max(1, scale)
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

    def _draw_bar_floor(self, surface, top, right, bottom, left, scale):
        # Tavern floor: warm aged-wood planks running along the iso diagonal,
        # with a faint spilled-ale sheen near the center. Reads as a worn common
        # room, not a polished hall. Plank spacing divides the iso neighbor
        # offsets so the cached surface tiles seamlessly across the room.
        diamond = [top, right, bottom, left]
        wood_base = self.mix(self.theme.floor, (96, 64, 40), 0.62)
        plank_dark = self.shade(wood_base, -26)
        plank_light = self.shade(wood_base, 14)
        pygame.draw.polygon(surface, wood_base, diamond)
        # Plank grooves: five shadowed recesses along the long iso diagonal,
        # each with a one-pixel-up lit lip so they read as beveled joins.
        cx = (top[0] + bottom[0]) / 2
        cy = (top[1] + bottom[1]) / 2
        # Direction along the iso long axis (top-left -> bottom-right).
        axis_dx = (right[0] - left[0]) / 2
        axis_dy = 0
        perp_dx = 0
        perp_dy = (bottom[1] - top[1]) / 2
        plank_ts = (0.18, 0.36, 0.54, 0.72, 0.90)
        for t in plank_ts:
            # Offset perpendicular to the long axis by fraction (t-0.5).
            off = (t - 0.5) * 2
            p_start = (cx - axis_dx + perp_dx * off, cy - axis_dy + perp_dy * off)
            p_end = (cx + axis_dx + perp_dx * off, cy + axis_dy + perp_dy * off)
            pygame.draw.aalines(surface, plank_dark, False, [p_start, p_end])
            up = [(p_start[0], p_start[1] - 1), (p_end[0], p_end[1] - 1)]
            pygame.draw.aalines(surface, plank_light, False, up)
        # Faint ale spill: a small low-contrast warm ellipse off-center.
        spill = self.mix(wood_base, (180, 150, 90), 0.30)
        spill_cx = int(cx + axis_dx * 0.25)
        spill_cy = int(cy + 2 * scale)
        pygame.draw.ellipse(
            surface,
            spill,
            (spill_cx - 6 * scale, spill_cy - 2 * scale, 12 * scale, 4 * scale),
        )
        # Crisp lit lip along the top-left edge.
        pygame.draw.aalines(surface, self.shade(wood_base, 18), False, [top, left])

    def _draw_garden_floor(self, surface, top, right, bottom, left, scale, seed=0):
        # Overgrown garden floor: stone barely visible under dense ivy and
        # wandering vines. Reads as ruins reclaimed by growth rather than a
        # tended lawn. ``seed`` drives a per-tile ivy pattern so each garden
        # tile varies while staying deterministic and bounded to
        # DUNGEON_FLOOR_VARIANTS cache entries.
        diamond = [top, right, bottom, left]
        stone = self.mix(self.theme.floor, (70, 80, 64), 0.20)
        pygame.draw.polygon(surface, stone, diamond)
        ivy = (62, 94, 52)
        ivy_hi = (90, 124, 70)
        ivy_lo = (40, 70, 38)
        rng = random.Random(int(seed) * 0x1000193 + 0x9E3779B1)
        pat = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        # Wandering vine stems across the slab.
        for _ in range(5):
            sx = rng.randint(left[0] + 6 * scale, right[0] - 6 * scale)
            sy = rng.randint(top[1] + 4 * scale, bottom[1] - 4 * scale)
            pts: list[tuple[int, int]] = [(sx, sy)]
            x, y = sx, sy
            for _ in range(5):
                x += rng.randint(-18, 18)
                y += rng.randint(-10, 10)
                pts.append((x, y))
            pygame.draw.lines(pat, ivy_lo, False, pts, max(2, scale))
            pygame.draw.aalines(pat, ivy, False, pts)
        # Dense ivy leaves (small clustered circles) covering most of the slab.
        for _ in range(120):
            lx = rng.randint(left[0] + 4 * scale, right[0] - 4 * scale)
            ly = rng.randint(top[1] + 3 * scale, bottom[1] - 3 * scale)
            r = rng.randint(2, 4)
            col = rng.choice((ivy, ivy_hi, ivy_lo))
            pygame.draw.circle(pat, col, (lx, ly), r)
        # Clip the organic detail to the diamond so leaves never bleed into the
        # transparent tile margin (and thus onto neighboring tiles).
        mask = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        pygame.draw.polygon(mask, (255, 255, 255, 255), diamond)
        pat.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        surface.blit(pat, (0, 0))
        # Crisp lit lip along the top-left edge.
        pygame.draw.aalines(surface, self.shade(ivy, 24), False, [top, left])

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
        bar_floor: bool = False,
        garden_floor: bool = False,
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
        if bar_floor and not is_stairs:
            self._draw_bar_floor(surface, top, right, bottom, left, scale)
            return
        if garden_floor and not is_stairs:
            self._draw_garden_floor(surface, top, right, bottom, left, scale, seed)
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
        for bell in getattr(self, "ambush_bells", []):
            if visible(bell.x, bell.y, 0.55):
                drawables.append((bell.x + bell.y - 0.03, "ambush_bell", bell))
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
        for npc in self.idle_npcs:
            if visible(npc.x, npc.y, 0.55):
                drawables.append((npc.x + npc.y, "idle_npc", npc))
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
        for familiar in self.familiars:
            drawables.append((familiar.x + familiar.y, "familiar", familiar))
        drawables.append((self.player.x + self.player.y, "player", self.player))
        for slash in self.slashes:
            x, y, _ttl, _dx, _dy = slash
            if visible(x, y, 0.55):
                drawables.append((x + y + 0.05, "slash", slash))
        for effect in self.impact_effects:
            if visible(effect.x, effect.y, max(0.35, effect.radius)):
                drawables.append((effect.x + effect.y + 0.08, "impact", effect))

        aim_started = time.perf_counter()
        self.draw_aim_cone()
        performance = getattr(self, "_mobile_performance_monitor", None)
        if performance is not None:
            performance.record_detail_phase(
                "aim", time.perf_counter() - aim_started
            )
        self._guidance_glow_blit_rect = None
        self._mobile_guidance_surface_size = (0, 0)
        # The guiding light leads the player TO the relic, so it must render
        # even when the relic is far outside the sight radius. The per-tile
        # visibility clipping inside draw_story_relic_guidance keeps the crack
        # from painting over dark / unrevealed floor.
        if self.story_relic_target_position() is not None:
            guidance_started = time.perf_counter()
            self.draw_story_relic_guidance()
            performance = getattr(self, "_mobile_performance_monitor", None)
            if performance is not None:
                performance.record_detail_phase(
                    "guidance", time.perf_counter() - guidance_started
                )

        wall_entries: list[tuple[pygame.Surface, tuple[int, int]]] = []

        def flush_wall_entries() -> None:
            if not wall_entries:
                return
            self._blit_floor_entries(self.screen, wall_entries)
            wall_entries.clear()

        visible_wall_count = 0
        visible_enemy_count = 0
        for _depth, kind, obj in sorted(drawables, key=lambda entry: entry[0]):
            if kind == "wall_tile":
                x, y = cast(tuple[int, int], obj)
                entry = self._tile_blit_entry(x, y, Tile.WALL)
                if entry is not None:
                    wall_entries.append(entry)
                    visible_wall_count += 1
                continue

            flush_wall_entries()
            if kind == "item":
                self.draw_item(cast(Item, obj))
            elif kind == "trap":
                self.draw_trap(cast(Trap, obj))
            elif kind == "ambush_bell":
                self.draw_ambush_bell(cast(AmbushBell, obj))
            elif kind == "shrine":
                self.draw_shrine(cast(Shrine, obj))
            elif kind == "secret":
                self.draw_secret(cast(SecretCache, obj))
            elif kind == "story_guest":
                self.draw_story_guest(cast(StoryGuest, obj))
            elif kind == "idle_npc":
                self.draw_idle_npc(cast(IdleNpc, obj))
            elif kind == "shopkeeper":
                self.draw_shopkeeper(cast(Shopkeeper, obj))
            elif kind == "gold_stack":
                gx, gy, gsize, variant = cast(tuple[int, int, int, int], obj)
                self.draw_gold_stack(gx, gy, gsize, variant)
            elif kind == "door":
                x, y, tile = cast(tuple[int, int, Tile], obj)
                self.draw_door(x, y, tile)
            elif kind == "projectile":
                self.draw_projectile(cast(Projectile, obj))
            elif kind == "enemy":
                self.draw_enemy(cast(Enemy, obj))
                visible_enemy_count += 1
            elif kind == "familiar":
                self.draw_familiar(cast(Familiar, obj))
            elif kind == "player":
                self.draw_player(cast(Player, obj))
            elif kind == "slash":
                self.draw_slash(cast(SlashEffect, obj))
            elif kind == "impact":
                self.draw_impact(cast(ImpactEffect, obj))

        flush_wall_entries()
        self._mobile_visible_wall_count = visible_wall_count
        self._mobile_visible_enemy_count = visible_enemy_count

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
        for gx, gy, gsize, variant in self._shop_gold_stack_placements():
            if visible(gx + 0.5, gy + 0.5, 0.45):
                drawables.append(
                    (gx + gy + 0.5, "gold_stack", (gx, gy, gsize, variant))
                )

    def _shop_gold_stack_placements(self) -> list[tuple[int, int, int, int]]:
        cache = getattr(self, "_frame_cache", None)
        if cache is not None and "gold_stack_placements" in cache:
            return cache["gold_stack_placements"]  # type: ignore[no-any-return]
        placements: list[tuple[int, int, int, int]] = []
        shop = self._shop_room_bounds()
        if shop is not None:
            rx, ry, rw, rh = shop
            avoid: set[tuple[int, int]] = set()
            special_room = self.dungeon.special_room_for_kind("shop")
            keeper_anchor = None
            sign_anchor = None
            if special_room is not None:
                keeper_anchor = special_room.anchor("shopkeeper")
                if keeper_anchor is None:
                    keeper_anchor = special_room.anchor("center")
                sign_anchor = special_room.anchor("shop_sign")
            if keeper_anchor is not None:
                avoid.add(keeper_anchor)
            else:
                for keeper in self.shopkeepers:
                    avoid.add((int(keeper.x), int(keeper.y)))
            if sign_anchor is not None:
                avoid.add(sign_anchor)
            else:
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
                target_count = min(
                    len(interior), max(count, max(5, min(12, len(interior) // 2)))
                )
                if len(chosen) < target_count:
                    chosen_tiles = set(chosen)
                    extras = [tile for tile in interior if tile not in chosen_tiles]
                    extra_rng = random.Random(seed ^ _GOLD_STACK_EXTRA_SALT)
                    extra_rng.shuffle(extras)
                    chosen.extend(extras[: target_count - len(chosen)])
                sizes = [2, 1, 3, 2, 1, 3, 2, 1]
                rng.shuffle(sizes)
                variant_rng = random.Random(seed ^ _GOLD_STACK_VARIANT_SALT)
                for i, (tx, ty) in enumerate(chosen):
                    placements.append(
                        (
                            tx,
                            ty,
                            sizes[i % len(sizes)],
                            variant_rng.randrange(_GOLD_STACK_VARIANT_COUNT),
                        )
                    )
        if cache is not None:
            cache["gold_stack_placements"] = placements
        return placements

    def draw_gold_stack(
        self, x: int, y: int, size: int, variant: int = 0
    ) -> None:
        sx, sy = self.world_to_screen(x + 0.5, y + 0.5)
        frame = self.sprites.gold_stack_visual(size, variant)
        if frame.is_asset:
            self.blit_resolved_sprite(frame, x + 0.5, y + 0.5, y_offset=2.0)
        else:
            sprite = frame.surface
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

    def door_render_direction(self, x: int, y: int) -> str:
        room = self.dungeon.room_at(x, y)
        if room is not None:
            vertical = ""
            horizontal = ""
            if y == room.y:
                vertical = "north"
            elif y == room.y + room.h - 1:
                vertical = "south"
            if x == room.x:
                horizontal = "west"
            elif x == room.x + room.w - 1:
                horizontal = "east"
            if vertical and horizontal:
                return f"{vertical}-{horizontal}"
            if vertical:
                return vertical
            if horizontal:
                return horizontal

        # Corridors and malformed legacy maps may contain a door outside any
        # room. Recover a stable cardinal from its wall run; dedicated assets
        # still render, while ambiguous topology keeps the old deterministic
        # north/west convention rather than storing orientation in the save.
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
            return "north"
        if y_axis and not x_axis:
            return "west"
        return "north"

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
        self, tile: Tile, seed: int, direction: str
    ) -> tuple[pygame.Surface, int, int]:
        face = (
            self._door_asset_face(direction)
            if self.sprites.modern_graphics_active
            else self._legacy_door_face(direction)
        )
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
        anchor_x = width // 2
        anchor_y = margin + wall_h + TILE_H // 2
        accent = (
            self.story_state.accent
            if getattr(self, "story_state", None) is not None
            else self.theme.accent
        )
        base_asset_key = "door_open" if tile == Tile.OPEN_DOOR else "door_closed"
        asset_surface = None
        if direction in _DOOR_DIRECTIONS:
            asset_surface = self.sprites.world_tile_surface(
                f"{base_asset_key}_{direction.replace('-', '_')}",
                target_canvas=(width, height),
                target_anchor=(anchor_x, anchor_y),
                tint=self.theme.wall_top,
                accent=accent,
                variant=seed,
            )
        if asset_surface is None:
            asset_surface = self.sprites.world_tile_surface(
                base_asset_key,
                target_canvas=(width, height),
                target_anchor=(anchor_x, anchor_y),
                tint=self.theme.wall_top,
                accent=accent,
                variant=seed,
                mirror=face == "right",
            )
        if asset_surface is not None:
            cache[key] = asset_surface
            self.door_tile_cache = cache
            return asset_surface

        surface = pygame.Surface((width, height), pygame.SRCALPHA)
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

    @staticmethod
    def _door_asset_face(direction: str) -> str:
        if direction in ("left", "right"):
            return direction
        if direction in ("north", "south", "north-west", "south-east"):
            return "left"
        return "right"

    @staticmethod
    def _legacy_door_face(direction: str) -> str:
        if direction in ("left", "right"):
            return direction
        if "-" in direction or direction in ("north", "south"):
            return "left"
        return "right"

    def draw_door(self, x: int, y: int, tile: Tile) -> None:
        sx, sy = self.world_to_screen(x + 0.5, y + 0.5)
        seed = self.tile_seed(x, y)
        surface, anchor_x, anchor_y = self.door_tile_surface(
            tile, seed, self.door_render_direction(x, y)
        )
        # Doors are tall occluders like walls; never render them translucent in
        # dark mode or the player can see through them. Culling beyond the
        # light radius is handled in draw_world_objects.
        self.screen.blit(surface, (sx - anchor_x, sy - anchor_y))
