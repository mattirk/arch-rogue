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
"""HD smooth fog-of-war edge (4.10.1).

Light floors remember explored terrain in ``revealed_tiles``; historically the
renderer expressed that memory as hard tile-diamond edges (unrevealed tiles
culled, ambient light stamped as per-tile rects). On the HD desktop renderer
this module replaces the ambient rects with a continuous **revelation field**:

* every revealed tile carries a value V in [0, 1] — 1 deep inside explored
  territory, ramping to 0 at the outermost remembered tile — derived from the
  Euclidean distance to the nearest unrevealed tile;
* the field lives on the diagonal (u, v) = (x - y, x + y) lattice, where the
  2:1 isometric projection is a pure per-axis scale, so one ``smoothscale``
  maps it into the half-resolution light buffer with bilinear-smooth edges;
* the buffer's existing ``BLEND_RGB_MULT`` composite then feathers the world
  into black across the frontier at pixel resolution.

Tile culling is untouched: unrevealed terrain is still never drawn, so the
gradient reveals no unexplored map — it lives inside the outer band of tiles
the player has already earned. The field eases toward its targets over a few
frames so an advancing frontier rolls back smoothly instead of stepping one
tile at a time, and a fresh floor's starting disc blooms outward from the
player. Everything derives per frame from ``revealed_tiles`` (guarded by an
identity/size signature), so saves, floor changes, and multiplayer syncs need
no bookkeeping and no state is serialized.
"""

from __future__ import annotations

import math
from typing import Iterable

import pygame

from ..constants import (
    HD_FOG_REVEAL_BLOOM_LIMIT,
    HD_FOG_REVEAL_DRAW_MARGIN,
    HD_FOG_REVEAL_EASE_RATE,
    HD_FOG_REVEAL_FALLOFF_SPAN,
    HD_FOG_REVEAL_FALLOFF_START,
    TILE_H,
    TILE_W,
)
from ..dungeon import MAP_H, MAP_W
from ..models import Tile

# Lattice geometry: tile (x, y) sits at (u, v) = (x - y, x + y); u is shifted
# by _U_OFFSET into a non-negative surface column. Tile sites have even u + v;
# odd-parity sites are the shared corners of four tile diamonds and hold the
# average of those tiles, which is exactly the bilinear support smoothscale
# needs for a seamless diamond-space gradient.
_U_OFFSET = MAP_H - 1
_LATTICE_SIZE = MAP_W + MAP_H - 1


def _field_value(distance: float) -> float:
    return max(
        0.0,
        min(
            1.0,
            (distance - HD_FOG_REVEAL_FALLOFF_START) / HD_FOG_REVEAL_FALLOFF_SPAN,
        ),
    )


# Neighbor offsets ordered by ascending distance with the field value each
# distance produces. The scan early-outs on the first unrevealed neighbor, so
# it yields the true nearest-unrevealed distance; beyond ~2.24 tiles the ramp
# has already reached 1.0 and farther terrain cannot matter.
_ORDERED_OFFSETS: tuple[tuple[int, int, float], ...] = tuple(
    (dx, dy, _field_value(math.hypot(dx, dy)))
    for dx, dy in sorted(
        (
            (dx, dy)
            for dx in range(-2, 3)
            for dy in range(-2, 3)
            if (dx, dy) != (0, 0) and dx * dx + dy * dy <= 5
        ),
        key=lambda offset: offset[0] ** 2 + offset[1] ** 2,
    )
)

_CORNER_STEPS = ((1, 0), (-1, 0), (0, 1), (0, -1))

# The bilinear tent spills at most one lattice site (half a tile) past the
# frontier and only at ground level, so the margin is exactly ring 1 of every
# revealed tile. Margin tiles contribute their ground diamond alone: the
# wall/door pass keeps the strict revealed gate (draw_world_objects), because
# a prism's own site eases up from zero the moment its tile is revealed —
# margin prisms would be hundreds of provably black tall blits per frame.
_DRAW_MARGIN_OFFSETS: tuple[tuple[int, int], ...] = tuple(
    (dx, dy)
    for dx in range(-HD_FOG_REVEAL_DRAW_MARGIN, HD_FOG_REVEAL_DRAW_MARGIN + 1)
    for dy in range(-HD_FOG_REVEAL_DRAW_MARGIN, HD_FOG_REVEAL_DRAW_MARGIN + 1)
)

# South-frontier prisms: a wall south (down-screen) of revealed terrain
# rises up-screen into the lit zone, so waiting for its own reveal would pop
# its top in under a bright mask. Any occluder whose prism could overlap a
# revealed tile's screen area is drawn early instead: prism reach is ~4
# v-units (dx + dy) and one tile wide (|dx - dy| <= 2). Entry happens while
# the overlapped frontier tile is still easing from zero, so the prism
# surfaces into darkness and brightens continuously with the field.
_PRISM_MARGIN_OFFSETS: tuple[tuple[int, int], ...] = tuple(
    (dx, dy)
    for dx in range(-1, 5)
    for dy in range(-1, 5)
    if 1 <= dx + dy <= 4 and abs(dx - dy) <= 2
)
_PRISM_OCCLUDERS = (Tile.WALL, Tile.CLOSED_DOOR, Tile.OPEN_DOOR)
# Early prisms only matter over lit ground. When the overlapped revealed tile
# is itself rock, the newcomer's prism lands on near-identical fogged rock
# texture and the swap is invisible — the same reasoning as the wall-fog
# support-tile rule. Skipping rock-on-rock keeps deep-rock frontiers from
# adding rows of tall blits.
_PRISM_SUPPORT_TILES = (Tile.FLOOR, Tile.STAIRS, Tile.OPEN_DOOR)


class FogOfWarMixin:
    def _smooth_fog_reveal_active(self) -> bool:
        """HD desktop light floors with continuous lighting only.

        Legacy and Modern keep the authored instant tile-quantized reveal,
        dark floors have no fog memory, mobile keeps its cached floor layer,
        and with lighting off the light buffer (the fog's carrier) never
        composites — every one of those paths renders exactly as before.
        """

        if getattr(self, "mobile_mode", False):
            return False
        if self.is_current_floor_dark():
            return False
        if not self.continuous_lighting_active():
            return False
        return self._hd_world_graphics_selected()

    # --- revelation field ------------------------------------------------

    def _fog_tile_target(
        self, tile: tuple[int, int], revealed: set[tuple[int, int]]
    ) -> float:
        # Out-of-bounds neighbors are ignored (treated as revealed): the map
        # border renders crisply against the void exactly as it always has,
        # instead of pulling permanent fog onto border walls.
        x, y = tile
        for dx, dy, value in _ORDERED_OFFSETS:
            nx = x + dx
            ny = y + dy
            if 0 <= nx < MAP_W and 0 <= ny < MAP_H and (nx, ny) not in revealed:
                return value
        return 1.0

    def _fog_rendered_value(self, tile: tuple[int, int]) -> float:
        eased = self._fog_ease.get(tile)
        if eased is not None:
            return eased
        return self._fog_field.get(tile, 0.0)

    def _fog_lattice_surface(self) -> pygame.Surface:
        # RGBA with alpha == value: the light composite only reads RGB, but
        # carrying the field in alpha keeps the buffer's "how much ambient
        # coverage here" convention from the rect path intact for tests and
        # any future consumer.
        lattice = getattr(self, "_fog_lattice", None)
        if lattice is None:
            lattice = pygame.Surface(
                (_LATTICE_SIZE, _LATTICE_SIZE), pygame.SRCALPHA
            ).convert_alpha()
            lattice.fill((0, 0, 0, 0))
            self._fog_lattice = lattice
        return lattice

    def _fog_write_sites(self, tiles: Iterable[tuple[int, int]]) -> None:
        """Write the lattice texels for ``tiles`` and their shared corners."""

        lattice = self._fog_lattice_surface()
        set_at = lattice.set_at
        corners: set[tuple[int, int]] = set()
        for x, y in tiles:
            value = self._fog_rendered_value((x, y))
            byte = int(value * 255.0 + 0.5)
            iu = x - y + _U_OFFSET
            iv = x + y
            set_at((iu, iv), (byte, byte, byte, byte))
            corners.add((iu - 1, iv))
            corners.add((iu + 1, iv))
            corners.add((iu, iv - 1))
            corners.add((iu, iv + 1))
        for iu, iv in corners:
            if not (0 <= iu < _LATTICE_SIZE and 0 <= iv < _LATTICE_SIZE):
                continue
            u = iu - _U_OFFSET
            total = 0.0
            for du, dv in _CORNER_STEPS:
                uu = u + du
                vv = iv + dv
                # Corner sites have odd u + v, so every uv-neighbor lands back
                # on a tile site; the shift halves exactly.
                total += self._fog_rendered_value(((uu + vv) >> 1, (vv - uu) >> 1))
            byte = int(total * 63.75 + 0.5)
            set_at((iu, iv), (byte, byte, byte, byte))
        self._fog_field_version = getattr(self, "_fog_field_version", 0) + 1

    def _fog_field_sync(self) -> None:
        """Refresh the field from ``revealed_tiles``; no producer coupling.

        Reveals, floor changes, save restores, and multiplayer syncs all reach
        the renderer as either the same set having grown (incremental delta:
        the new tiles plus their falloff neighborhood are recomputed) or a new
        set object / floor identity (full rebuild). A rebuild of at most
        ``HD_FOG_REVEAL_BLOOM_LIMIT`` tiles blooms from black — the floor
        entry disc — while larger rebuilds (restored saves) appear instantly.
        """

        revealed = self.revealed_tiles
        field = getattr(self, "_fog_field", None)
        if field is None:
            field = {}
            self._fog_field = field
            self._fog_ease = {}
            self._fog_ease_clock = float(getattr(self, "ui_elapsed", 0.0))
        signature = (
            id(revealed),
            getattr(self, "current_depth", 0),
            getattr(self, "run_number", 0),
        )
        if signature != getattr(self, "_fog_field_signature", None):
            self._fog_field_signature = signature
            field.clear()
            self._fog_ease.clear()
            self._fog_draw_tiles = set()
            self._fog_prism_tiles = set()
            self._fog_lattice_surface().fill((0, 0, 0, 0))
            self._fog_field_version = getattr(self, "_fog_field_version", 0) + 1
            # Restart the ease clock: a floor transition spends hundreds of
            # milliseconds without draws, and measuring the first bloom step
            # against the previous floor's last frame would skip most of it.
            self._fog_ease_clock = float(getattr(self, "ui_elapsed", 0.0))
            fresh: Iterable[tuple[int, int]] = revealed
            bloom = len(revealed) <= HD_FOG_REVEAL_BLOOM_LIMIT
        elif len(revealed) != len(field):
            fresh = revealed.difference(field)
            bloom = True
        else:
            return
        affected = set(fresh)
        if not affected:
            return
        # Widen the draw set: every fresh tile plus its margin ball is drawn
        # (under field 0 until revealed), so the fog lift never uncovers
        # geometry that was not already on screen.
        draw_tiles = getattr(self, "_fog_draw_tiles", None)
        if draw_tiles is None:
            draw_tiles = set()
            self._fog_draw_tiles = draw_tiles
        prism_tiles = getattr(self, "_fog_prism_tiles", None)
        if prism_tiles is None:
            prism_tiles = set()
            self._fog_prism_tiles = prism_tiles
        dungeon_tiles = self.dungeon.tiles
        for x, y in affected:
            for dx, dy in _DRAW_MARGIN_OFFSETS:
                draw_tiles.add((x + dx, y + dy))
            if dungeon_tiles[x][y] not in _PRISM_SUPPORT_TILES:
                continue
            for dx, dy in _PRISM_MARGIN_OFFSETS:
                nx = x + dx
                ny = y + dy
                if (
                    0 <= nx < MAP_W
                    and 0 <= ny < MAP_H
                    and dungeon_tiles[nx][ny] in _PRISM_OCCLUDERS
                ):
                    prism_tiles.add((nx, ny))
        if field:
            for x, y in tuple(affected):
                for dx, dy, _value in _ORDERED_OFFSETS:
                    neighbor = (x + dx, y + dy)
                    if neighbor in field:
                        affected.add(neighbor)
        ease = self._fog_ease
        for tile in affected:
            previous = field.get(tile)
            target = self._fog_tile_target(tile, revealed)
            field[tile] = target
            if not bloom:
                continue
            start = ease.get(tile)
            if start is None:
                start = previous if previous is not None else 0.0
            if abs(start - target) > 0.004:
                ease[tile] = start
            else:
                ease.pop(tile, None)
        self._fog_write_sites(affected)

    def _fog_advance_easing(self) -> None:
        ease = getattr(self, "_fog_ease", None)
        if not ease:
            return
        now = float(getattr(self, "ui_elapsed", 0.0))
        dt = now - getattr(self, "_fog_ease_clock", now)
        self._fog_ease_clock = now
        if dt <= 0.0:
            return
        # Exponential form keeps the pull frame-rate independent: many small
        # steps and one large step over the same wall-clock time converge to
        # the same rendered value, and hitches simply snap the fog forward.
        blend = 1.0 - math.exp(-dt * HD_FOG_REVEAL_EASE_RATE)
        field = self._fog_field
        finished: list[tuple[int, int]] = []
        for tile, value in ease.items():
            target = field.get(tile, 0.0)
            value += (target - value) * blend
            if abs(target - value) <= 0.02:
                finished.append(tile)
            else:
                ease[tile] = value
        for tile in finished:
            del ease[tile]
        self._fog_write_sites(tuple(ease) + tuple(finished))

    def _fog_draw_tiles_synced(self) -> set[tuple[int, int]]:
        """The widened render cull set: revealed plus the black fog margin.

        Called by ``_visibility_scan_params`` at the start of the world draw,
        before the lighting pass runs its own sync — ``_fog_field_sync`` is a
        cheap length check when nothing changed this frame.
        """

        self._fog_field_sync()
        draw_tiles = getattr(self, "_fog_draw_tiles", None)
        if draw_tiles is None:
            draw_tiles = set()
            self._fog_draw_tiles = draw_tiles
        return draw_tiles

    # --- light-buffer stamp ----------------------------------------------

    def _stamp_smooth_fog(
        self,
        buffer: pygame.Surface,
        scale: int,
        ambient: tuple[int, ...],
    ) -> None:
        """Rasterize the field into the light buffer as ambient * V.

        The buffer's existing nearest-scale + ``BLEND_RGB_MULT`` composite
        (see ``apply_world_lighting``) then carries the gradient to the
        screen; interior tiles multiply by ambient * 1.0, byte-identical to
        the rect fills this replaces, so only the frontier band changes.
        """

        self._fog_field_sync()
        self._fog_advance_easing()
        eff_zoom, project = self._shade_params()
        su = TILE_W * 0.5 * eff_zoom
        sv = TILE_H * 0.5 * eff_zoom
        if su <= 0.0 or sv <= 0.0:
            return
        # Anchor from one live projection so both shading spaces (world layer
        # pre-composite, display post-composite) stay exact. Tile (0, 0) is
        # lattice site (u, v) = (0, 0) and its center projects at iso v = 1,
        # so with sx(u) = cx + u * su and sy(v) = cy + v * sv the reference
        # already contains the one-unit center shift: cx, cy = project(.5, .5).
        # project() floors to int, costing at most one shaded pixel —
        # invisible inside a multi-hundred-pixel gradient.
        ref_x, ref_y = project(0.5, 0.5)
        cx = float(ref_x)
        cy = float(ref_y)
        buffer_w, buffer_h = buffer.get_size()
        view_w = buffer_w * scale
        view_h = buffer_h * scale
        iu0 = max(0, math.floor((0.0 - cx) / su) - 1 + _U_OFFSET)
        iu1 = min(_LATTICE_SIZE - 1, math.ceil((view_w - cx) / su) + 1 + _U_OFFSET)
        iv0 = max(0, math.floor((0.0 - cy) / sv) - 1)
        iv1 = min(_LATTICE_SIZE - 1, math.ceil((view_h - cy) / sv) + 1)
        if iu0 > iu1 or iv0 > iv1:
            # Viewport entirely off the map: the buffer's cleared black is the
            # correct void, matching the tile cull.
            return
        nu = iu1 - iu0 + 1
        nv = iv1 - iv0 + 1
        dest_w = max(1, round(nu * su / scale))
        dest_h = max(1, round(nv * sv / scale))
        blit_x = round((cx + (iu0 - _U_OFFSET - 0.5) * su) / scale)
        blit_y = round((cy + (iv0 - 0.5) * sv) / scale)
        key = (
            getattr(self, "_fog_field_version", 0),
            iu0,
            iv0,
            nu,
            nv,
            dest_w,
            dest_h,
            tuple(ambient[:3]),
        )
        cache = getattr(self, "_fog_stamp_cache", None)
        if cache is not None and cache[0] == key:
            stamped = cache[1]
        else:
            # Reuse one destination surface: while the camera glides the
            # region size is stable, so steady frames avoid re-allocating a
            # near-buffer-sized surface and stationary frames skip the
            # smoothscale entirely via the cache key above.
            stamped = getattr(self, "_fog_stamp_dest", None)
            if stamped is None or stamped.get_size() != (dest_w, dest_h):
                stamped = pygame.Surface(
                    (dest_w, dest_h), pygame.SRCALPHA
                ).convert_alpha()
                self._fog_stamp_dest = stamped
            region = self._fog_lattice_surface().subsurface(
                (iu0, iv0, nu, nv)
            )
            pygame.transform.smoothscale(region, (dest_w, dest_h), stamped)
            stamped.fill(tuple(ambient[:3]), special_flags=pygame.BLEND_RGB_MULT)
            self._fog_stamp_cache = (key, stamped)
        # RGBA_MAX onto the freshly zeroed buffer is an exact channel copy —
        # a plain blit would alpha-composite and square the field into RGB.
        buffer.blit(stamped, (blit_x, blit_y), special_flags=pygame.BLEND_RGBA_MAX)
