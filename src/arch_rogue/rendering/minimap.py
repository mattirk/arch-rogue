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

from ..steam_deck import is_steam_deck

import math

import pygame

from ..constants import DARK_LEVEL_LIGHT_RADIUS
from ..dungeon import BAR_ROOM_KIND, GARDEN_ROOM_KIND, MAP_H, MAP_W
from ..models import Tile


class RenderingMinimapMixin:
    """Desktop minimap overlay (4.8.11).

    A player-centered, isometric-projected map card in the top-right HUD
    corner, toggled with Ctrl+M and zoomed with the mouse wheel while the
    cursor hovers the card. Terrain honors the fog-of-war contract:
    light floors draw remembered ``revealed_tiles`` from an incrementally
    updated cached surface, dark floors keep their zero-memory lantern model
    and draw only the live visibility patch each frame. The Wayfarer's Bar,
    the Overgrown Garden, and the stairs get glyph markers once discovered
    (edge-clamped with a direction arrow when off-view), and the story
    relic's guiding light marks its target with a pulsing beacon whenever
    guidance is active. Rendering is fully procedural in both graphics modes;
    only the panel chrome swaps to authored art via draw_ornate_hud_panel.
    """

    # Panel geometry in unscaled UI units. The desired size fills the gap the
    # 960x540 fitted layout leaves right of the run header; below the minimum
    # the card is suppressed instead of shrinking into an unreadable stamp.
    MINIMAP_PANEL_W = 172
    MINIMAP_PANEL_H = 110
    MINIMAP_MIN_W = 96
    MINIMAP_MIN_H = 64
    # Iso half-steps per tile (2:1, matching the world projection direction),
    # so "up-right on screen" is "up-right on the map".
    MINIMAP_TILE_HALF_W = 4
    MINIMAP_TILE_HALF_H = 2
    # Wheel-over-card zoom: multiplicative steps, clamped so the map neither
    # degenerates into noise nor fills the card with three tiles.
    MINIMAP_ZOOM_MIN = 0.5
    MINIMAP_ZOOM_MAX = 2.5
    MINIMAP_ZOOM_STEP = 1.2

    # Marker palette. Bar amber and garden green are fixed identity colors —
    # matching the rooms' interior art rather than the per-floor theme — so
    # the same glyph reads the same on every depth.
    MINIMAP_BAR_COLOR = (226, 168, 88)
    MINIMAP_GARDEN_COLOR = (116, 196, 118)
    MINIMAP_PARTNER_COLOR = (122, 196, 255)
    MINIMAP_STAIRS_COLOR = (186, 120, 255)

    # Tiles rendered as lifted iso blocks rather than flat ground.
    MINIMAP_RAISED = (Tile.WALL, Tile.CLOSED_DOOR)

    # The stairs beat: 8 authored frames ping-ponged at ~8.33 fps (manifest
    # world.stairs), one full swell every ~1.68 s.
    MINIMAP_STAIRS_PULSE_PERIOD = (2 * 8 - 2) / 8.333333

    def _minimap_tile_scale(self) -> tuple[int, int]:
        zoom = float(getattr(self, "minimap_zoom", 1.0))
        if is_steam_deck():
            zoom *= 1.6
        half_w = max(2, round(self.ui(self.MINIMAP_TILE_HALF_W) * zoom))
        return half_w, max(1, half_w // 2)

    def adjust_minimap_zoom(self, direction: int) -> float:
        """Step the card's zoom by wheel notches; positive zooms in.

        The value lives for the current run only — restart() resets it to
        1.0. The terrain cache key contains the tile scale, so the next draw
        rebuilds at the new zoom without an explicit invalidation.
        """
        zoom = float(getattr(self, "minimap_zoom", 1.0))
        if direction:
            zoom *= self.MINIMAP_ZOOM_STEP**direction
            zoom = max(self.MINIMAP_ZOOM_MIN, min(self.MINIMAP_ZOOM_MAX, zoom))
            self.minimap_zoom = zoom
        return zoom

    def minimap_contains_screen_point(self, pos: tuple[int, int]) -> bool:
        """Hit-test against the card as published by the last draw."""
        rect = getattr(self, "_minimap_rect", None)
        return rect is not None and rect.collidepoint(pos)

    def _minimap_palette(self) -> dict[str, tuple[int, int, int, int]]:
        # Theme-tinted terrain: floors sink toward the HUD ink, walls keep a
        # readable stone lift, doors glow faintly so chokepoints stand out.
        theme = self.theme
        floor = self.mix(self.HUD_INK, theme.floor, 0.42)
        wall = self.mix((30, 28, 38), theme.wall_top, 0.55)
        return {
            "floor": (*floor, 235),
            "floor_bar": (*self.mix(floor, self.MINIMAP_BAR_COLOR, 0.38), 240),
            "floor_garden": (
                *self.mix(floor, self.MINIMAP_GARDEN_COLOR, 0.38),
                240,
            ),
            "wall": (*wall, 245),
            "wall_edge": (*self.shade(wall, 34), 255),
            "stairs": (*self.mix(floor, self.HUD_GOLD, 0.45), 245),
            "closed_door": (*self.mix(wall, self.HUD_GOLD, 0.35), 250),
            "open_door": (*self.mix(floor, self.HUD_GOLD, 0.25), 240),
        }

    def _minimap_floor_key(self) -> tuple:
        dungeon = self.dungeon
        half_w, half_h = self._minimap_tile_scale()
        return (
            getattr(self, "run_number", 0),
            getattr(self, "current_depth", 0),
            id(dungeon),
            half_w,
            half_h,
            tuple(self.theme.accent),
        )

    def _minimap_state(self) -> dict:
        # One dict holds every long-lived minimap cache so the single
        # _invalidate_render_caches() seam can drop it with one clear().
        cache = getattr(self, "_minimap_cache", None)
        if cache is None:
            cache = {}
            self._minimap_cache = cache
        key = self._minimap_floor_key()
        if cache.get("floor_key") != key:
            cache.clear()
            cache["floor_key"] = key
            half_w, half_h = self._minimap_tile_scale()
            # Terrain surface spans the full 72x72 grid in map-iso space with
            # a one-diamond margin; origin shifts iso coords non-negative. The
            # extra half_h on top keeps lifted wall blocks inside the surface.
            width = (MAP_W + MAP_H) * half_w + 2
            height = (MAP_W + MAP_H) * half_h + 2 + half_h
            cache["origin"] = (MAP_H * half_w + 1, half_h + 1 + half_h)
            cache["surface"] = pygame.Surface((width, height), pygame.SRCALPHA)
            cache["drawn"] = set()
            cache["palette"] = self._minimap_palette()
            cache["room_tiles"] = self._minimap_special_room_tiles()
            cache["discovered"] = {}
        return cache

    def _minimap_special_room_tiles(self) -> dict[tuple[int, int], str]:
        # Tile -> special-room kind for the two flavor refuges, so their
        # interiors tint as they are revealed and discovery checks are O(1).
        tiles: dict[tuple[int, int], str] = {}
        dungeon = self.dungeon
        for kind in (BAR_ROOM_KIND, GARDEN_ROOM_KIND):
            special = dungeon.special_room_for_kind(kind)
            if special is None:
                continue
            if not 0 <= special.room_index < len(dungeon.rooms):
                continue
            room = dungeon.rooms[special.room_index]
            for x in range(room.x, room.x + room.w):
                for y in range(room.y, room.y + room.h):
                    tiles[(x, y)] = kind
        return tiles

    def _minimap_tile_color(
        self,
        tile: Tile,
        tile_pos: tuple[int, int],
        palette: dict[str, tuple[int, int, int, int]],
        room_tiles: dict[tuple[int, int], str],
    ) -> tuple[tuple[int, int, int, int], bool]:
        """Return (rgba, is_wall) for one tile diamond."""
        if tile == Tile.WALL:
            return palette["wall"], True
        if tile == Tile.STAIRS:
            return palette["stairs"], False
        if tile == Tile.CLOSED_DOOR:
            return palette["closed_door"], True
        if tile == Tile.OPEN_DOOR:
            return palette["open_door"], False
        kind = room_tiles.get(tile_pos)
        if kind == BAR_ROOM_KIND:
            return palette["floor_bar"], False
        if kind == GARDEN_ROOM_KIND:
            return palette["floor_garden"], False
        return palette["floor"], False

    def _minimap_draw_tile(
        self,
        surface: pygame.Surface,
        center: tuple[float, float],
        tile_pos: tuple[int, int],
        color: tuple[int, int, int, int],
        is_wall: bool,
        edge_color: tuple[int, int, int, int] | None,
        half_w: int,
        half_h: int,
        exposed,
        alpha_cap: int | None = None,
    ) -> None:
        """Draw one tile: flat diamond for ground, lifted iso block for walls.

        ``exposed(x, y)`` reports whether a neighbor renders as open revealed
        ground; shaded side faces and the light top rim only appear along
        such edges, so contiguous wall runs read as one clean plateau instead
        of a per-tile scallop pattern, and nothing hints at unexplored tiles.
        """
        cx, cy = center
        if alpha_cap is not None:
            color = (*color[:3], min(color[3], alpha_cap))
        top = (cx, cy - half_h)
        right = (cx + half_w, cy)
        bottom = (cx, cy + half_h)
        left = (cx - half_w, cy)
        if not is_wall:
            pygame.draw.polygon(surface, color, (top, right, bottom, left))
            return
        x, y = tile_pos
        lift = max(1, half_h)
        r_top = (cx, cy - half_h - lift)
        r_right = (cx + half_w, cy - lift)
        r_bottom = (cx, cy + half_h - lift)
        r_left = (cx - half_w, cy - lift)
        base, alpha = color[:3], color[3]
        if exposed(x, y + 1):
            face = (*self.shade(base, -26), alpha)
            pygame.draw.polygon(surface, face, (r_left, r_bottom, bottom, left))
        if exposed(x + 1, y):
            face = (*self.shade(base, -48), alpha)
            pygame.draw.polygon(surface, face, (r_bottom, r_right, right, bottom))
        pygame.draw.polygon(surface, color, (r_top, r_right, r_bottom, r_left))
        if edge_color is not None:
            if alpha_cap is not None:
                edge_color = (*edge_color[:3], min(edge_color[3], alpha_cap))
            if exposed(x - 1, y):
                pygame.draw.line(surface, edge_color, r_left, r_top)
            if exposed(x, y - 1):
                pygame.draw.line(surface, edge_color, r_top, r_right)

    def _minimap_update_terrain(self, state: dict) -> None:
        # Incremental fog-of-war mirror: revealed_tiles only ever grows within
        # a floor, so draw just the delta. A shrink (floor reset, MP joiner
        # rebuild) is caught by the containment check and restarts the mirror.
        revealed = getattr(self, "revealed_tiles", None)
        if not revealed:
            return
        drawn: set[tuple[int, int]] = state["drawn"]
        if len(drawn) == len(revealed):
            return
        if len(drawn) > len(revealed):
            # Fog memory was wiped (dark toggle, MP joiner rebuild): restart
            # the mirror and forget discoveries with it.
            state["surface"].fill((0, 0, 0, 0))
            drawn = state["drawn"] = set()
            state["discovered"] = {}
        pending = revealed - drawn
        if not pending:
            return
        surface = state["surface"]
        origin_x, origin_y = state["origin"]
        palette = state["palette"]
        room_tiles = state["room_tiles"]
        half_w, half_h = self._minimap_tile_scale()
        lift = max(1, half_h)
        tiles = self.dungeon.tiles
        edge = palette["wall_edge"]
        raised = self.MINIMAP_RAISED

        fresh = [
            (x, y) for x, y in pending if 0 <= x < MAP_W and 0 <= y < MAP_H
        ]
        drawn |= pending
        if not fresh:
            return

        # Neighbor-aware faces/rims and lifted tops overlapping nearby cells
        # make in-place patching order-sensitive, so the delta is applied as
        # clear-and-redraw: wipe the batch's bounding rect, then repaint every
        # drawn tile whose footprint touches it, back to front, clipped to the
        # rect. Pixels inside get exactly the full-redraw result; pixels
        # outside are never touched.
        xs = [origin_x + (x - y) * half_w for x, y in fresh]
        ys = [origin_y + (x + y) * half_h for x, y in fresh]
        clear = pygame.Rect(
            min(xs) - half_w,
            min(ys) - half_h - lift,
            max(xs) - min(xs) + 2 * half_w + 1,
            max(ys) - min(ys) + 2 * half_h + lift + 1,
        )
        # A cell's footprint spans half_w each side and half_h + lift
        # vertically, so tiles with centers inside this expansion are exactly
        # the ones whose pixels can reach the cleared rect.
        probe = clear.inflate(2 * half_w + 2, 2 * (half_h + lift) + 2)

        def exposed(x: int, y: int) -> bool:
            return (
                0 <= x < MAP_W
                and 0 <= y < MAP_H
                and (x, y) in revealed
                and tiles[x][y] not in raised
            )

        batch = []
        for x, y in drawn:
            if not (0 <= x < MAP_W and 0 <= y < MAP_H):
                continue
            cx = origin_x + (x - y) * half_w
            cy = origin_y + (x + y) * half_h
            if probe.collidepoint(cx, cy):
                batch.append((x, y, cx, cy))
        batch.sort(key=lambda cell: (cell[0] + cell[1], cell[0]))

        surface.fill((0, 0, 0, 0), clear)
        surface.set_clip(clear)
        try:
            for x, y, cx, cy in batch:
                color, is_wall = self._minimap_tile_color(
                    tiles[x][y], (x, y), palette, room_tiles
                )
                self._minimap_draw_tile(
                    surface,
                    (cx, cy),
                    (x, y),
                    color,
                    is_wall,
                    edge,
                    half_w,
                    half_h,
                    exposed,
                )
        finally:
            surface.set_clip(None)

    def _minimap_projector(self, viewport: pygame.Rect):
        # World floats -> overlay-local px, player pinned to the viewport
        # center. Tile (x, y) spans [x, x+1), so its center sits at
        # world (x+0.5, y+0.5) == map-iso ((x-y)*hw, (x+y)*hh) — hence the
        # constant -1.0 on the vertical term for float world positions.
        half_w, half_h = self._minimap_tile_scale()
        player = self.player
        anchor_x = viewport.width / 2 - (player.x - player.y) * half_w
        anchor_y = viewport.height / 2 - (player.x + player.y - 1.0) * half_h

        def project(wx: float, wy: float) -> tuple[float, float]:
            return (
                anchor_x + (wx - wy) * half_w,
                anchor_y + (wx + wy - 1.0) * half_h,
            )

        return project, half_w, half_h

    def _minimap_draw_dark_patch(
        self, overlay: pygame.Surface, project, state: dict
    ) -> None:
        # Dark floors: no memory, only the live lantern ring — mirrors
        # tile_visibility_alpha so the map never leaks unexplored layout.
        palette = state["palette"]
        room_tiles = state["room_tiles"]
        half_w, half_h = self._minimap_tile_scale()
        tiles = self.dungeon.tiles
        edge = palette["wall_edge"]
        raised = self.MINIMAP_RAISED
        reach = int(DARK_LEVEL_LIGHT_RADIUS) + 2
        px, py = int(self.player.x), int(self.player.y)

        # One lantern-ring scan probes each tile several times per frame (the
        # ring itself plus every neighbor test in exposed()); memoize the alpha
        # per tile for the duration of this patch draw.
        alpha_memo: dict[tuple[int, int], int] = {}
        visibility_alpha = self.tile_visibility_alpha

        def tile_alpha(x: int, y: int) -> int:
            key = (x, y)
            alpha = alpha_memo.get(key)
            if alpha is None:
                alpha = visibility_alpha(x, y)
                alpha_memo[key] = alpha
            return alpha

        def exposed(x: int, y: int) -> bool:
            return (
                0 <= x < MAP_W
                and 0 <= y < MAP_H
                and tile_alpha(x, y) > 0
                and tiles[x][y] not in raised
            )

        visible: list[tuple[int, int, int, int]] = []
        for x in range(max(0, px - reach), min(MAP_W, px + reach + 1)):
            for y in range(max(0, py - reach), min(MAP_H, py + reach + 1)):
                alpha = tile_alpha(x, y)
                if alpha > 0:
                    visible.append((x + y, x, y, alpha))
        # Back-to-front so lifted wall blocks overlap the ground behind them.
        for _order, x, y, alpha in sorted(visible):
            color, is_wall = self._minimap_tile_color(
                tiles[x][y], (x, y), palette, room_tiles
            )
            self._minimap_draw_tile(
                overlay,
                project(x + 0.5, y + 0.5),
                (x, y),
                color,
                is_wall,
                edge,
                half_w,
                half_h,
                exposed,
                alpha_cap=alpha,
            )

    # --- Markers -----------------------------------------------------------

    def minimap_markers(self) -> list[tuple[str, float, float]]:
        """Discovery-gated marker list: (kind, world_x, world_y).

        Kinds: ``bar``, ``garden``, ``stairs``. Light floors remember a
        discovery for the rest of the floor once any interior tile has been
        revealed; dark floors follow the lantern-only model and only report
        markers currently inside the live visibility ring.
        """
        state = self._minimap_state()
        dungeon = self.dungeon
        targets: list[tuple[str, float, float]] = []
        for kind in (BAR_ROOM_KIND, GARDEN_ROOM_KIND):
            special = dungeon.special_room_for_kind(kind)
            if special is None:
                continue
            if not 0 <= special.room_index < len(dungeon.rooms):
                continue
            cx, cy = dungeon.rooms[special.room_index].center
            targets.append((kind, cx + 0.5, cy + 0.5))
        stairs_x, stairs_y = dungeon.stairs
        targets.append(("stairs", stairs_x + 0.5, stairs_y + 0.5))

        markers: list[tuple[str, float, float]] = []
        if self.is_current_floor_dark():
            discovered = state["discovered"]
            for kind, wx, wy in targets:
                if self.tile_visibility_alpha(int(wx), int(wy)) > 0:
                    if kind == "stairs":
                        discovered["stairs"] = True
                    markers.append((kind, wx, wy))
                elif kind == "stairs" and discovered.get("stairs"):
                    # 5.0.2: once the stairs have been seen on a dark floor
                    # they stay marked — off-window they clamp to the card
                    # edge as an arrow guiding back through the black.
                    markers.append((kind, wx, wy))
            return markers

        revealed = getattr(self, "revealed_tiles", set())
        discovered: dict[str, bool] = state["discovered"]
        room_tiles = state["room_tiles"]
        for kind, wx, wy in targets:
            if not discovered.get(kind):
                if kind == "stairs":
                    found = (int(wx), int(wy)) in revealed
                else:
                    found = any(
                        tile in revealed
                        for tile, tile_kind in room_tiles.items()
                        if tile_kind == kind
                    )
                if not found:
                    continue
                discovered[kind] = True
            markers.append((kind, wx, wy))
        return markers

    def minimap_guidance(self) -> tuple[float, float] | None:
        """The guiding light's beacon target when guidance is active."""
        target = self.story_relic_target_position()
        if (
            target is None
            or getattr(self, "story_intro_pending", False)
            or not getattr(self, "story_relic_guidance_enabled", False)
        ):
            return None
        return target

    def _minimap_clamp_to_viewport(
        self, pos: tuple[float, float], bounds: pygame.Rect
    ) -> tuple[tuple[float, float], bool]:
        # Clamp an off-view point onto the inset viewport border along the
        # ray from the viewport center, so edge markers point the right way.
        x, y = pos
        if bounds.collidepoint(x, y):
            return pos, False
        cx, cy = bounds.center
        dx, dy = x - cx, y - cy
        scale = 1.0
        if dx:
            scale = min(scale, (bounds.width / 2) / abs(dx))
        if dy:
            scale = min(scale, (bounds.height / 2) / abs(dy))
        return (cx + dx * scale, cy + dy * scale), True

    def _minimap_draw_edge_arrow(
        self,
        overlay: pygame.Surface,
        pos: tuple[float, float],
        center: tuple[float, float],
        color: tuple[int, int, int],
    ) -> None:
        angle = math.atan2(pos[1] - center[1], pos[0] - center[0])
        tip_len = max(4, self.ui(5))
        back = max(1, self.ui(2))
        half_base = float(max(1, self.ui(2)))
        # A triangle this small rasterizes lopsided and nail-thin when drawn
        # directly, so render it 8x oversized and smoothscale down for a
        # symmetric solid head at any angle.
        ss = 8
        reach = tip_len + 2
        box = reach * 2 * ss
        scratch = pygame.Surface((box, box), pygame.SRCALPHA)
        c = box / 2
        dx, dy = math.cos(angle), math.sin(angle)
        px, py = -dy, dx
        bx, by = c - dx * back * ss, c - dy * back * ss
        pygame.draw.polygon(
            scratch,
            (*color, 235),
            (
                (c + dx * tip_len * ss, c + dy * tip_len * ss),
                (bx + px * half_base * ss, by + py * half_base * ss),
                (bx - px * half_base * ss, by - py * half_base * ss),
            ),
        )
        head = pygame.transform.smoothscale(scratch, (reach * 2, reach * 2))
        overlay.blit(head, (round(pos[0] - reach), round(pos[1] - reach)))

    def _minimap_draw_marker_glyph(
        self,
        overlay: pygame.Surface,
        kind: str,
        pos: tuple[float, float],
        pulse: float,
    ) -> None:
        x, y = int(pos[0]), int(pos[1])
        unit = max(2, self.ui(2))
        if kind == "bar":
            # Tiny tankard: amber body, bright foam cap, handle nub.
            body = pygame.Rect(0, 0, unit * 2 + 1, unit * 3 - 1)
            body.center = (x, y + 1)
            pygame.draw.rect(overlay, (*self.HUD_INK, 230), body.inflate(2, 2))
            pygame.draw.rect(overlay, (*self.MINIMAP_BAR_COLOR, 255), body)
            foam = pygame.Rect(body.x, body.y - 1, body.width, max(1, unit - 1))
            pygame.draw.rect(overlay, (250, 242, 214, 255), foam)
            handle = pygame.Rect(body.right, y - unit // 2, max(1, unit - 1), unit)
            pygame.draw.rect(overlay, (*self.MINIMAP_BAR_COLOR, 255), handle)
        elif kind == "garden":
            # Sprout: green crown over a rooted stem.
            radius = unit + 1
            pygame.draw.circle(overlay, (*self.HUD_INK, 230), (x, y - 1), radius + 1)
            pygame.draw.circle(
                overlay, (*self.MINIMAP_GARDEN_COLOR, 255), (x, y - 1), radius
            )
            pygame.draw.circle(
                overlay,
                (*self.shade(self.MINIMAP_GARDEN_COLOR, 50), 255),
                (x - 1, y - 2),
                max(1, radius - 2),
            )
            pygame.draw.line(
                overlay,
                (*self.shade(self.MINIMAP_GARDEN_COLOR, -60), 255),
                (x, y),
                (x, y + unit + 1),
            )
        elif kind == "stairs":
            # Stairwell mouth: gold-rimmed circle with the portal's purple
            # light welling up from the shaft in step with the stairs
            # animation.
            radius = unit + 1
            swell = self._minimap_stairs_pulse()
            glow = self.mix((58, 34, 86), self.MINIMAP_STAIRS_COLOR, swell)
            pygame.draw.circle(overlay, (*self.HUD_INK, 230), (x, y), radius + 1)
            pygame.draw.circle(overlay, (*glow, 255), (x, y), max(1, radius - 1))
            if swell >= 0.65:
                # Hot lavender core at the top of the swell.
                pygame.draw.circle(
                    overlay, (226, 196, 255, 255), (x, y), max(1, radius - 2)
                )
            pygame.draw.circle(
                overlay, (*self.HUD_GOLD_BRIGHT, 255), (x, y), radius, 1
            )
        elif kind == "relic":
            # The guiding light beacon: soft pulsing halo + four-point star.
            glow = max(3, self.ui(6))
            halo = pygame.Surface((glow * 4, glow * 4), pygame.SRCALPHA)
            for radius, alpha in (
                (glow * 2, 34 + int(26 * pulse)),
                (glow + glow // 2, 60 + int(34 * pulse)),
                (glow, 96 + int(50 * pulse)),
            ):
                pygame.draw.circle(
                    halo, (*self.HUD_GOLD, alpha), (glow * 2, glow * 2), radius
                )
            overlay.blit(halo, (x - glow * 2, y - glow * 2))
            arm = glow - 1 + int(pulse * 2)
            core = self.HUD_GOLD_BRIGHT
            pygame.draw.line(overlay, (*core, 255), (x - arm, y), (x + arm, y))
            pygame.draw.line(overlay, (*core, 255), (x, y - arm), (x, y + arm))
            pygame.draw.circle(overlay, (255, 250, 232, 255), (x, y), max(1, unit - 1))

    def _minimap_stairs_pulse(self) -> float:
        """0..1 swell locked to the stairs tile's portal animation.

        With authored graphics the value tracks the actual ping-pong frame
        index, so the marker brightens exactly when the stairs do; retro
        graphics has no tile animation, so a triangle wave keeps the same
        period and phase origin.
        """
        elapsed = getattr(self, "ui_elapsed", 0.0)
        sprites = getattr(self, "sprites", None)
        if sprites is not None:
            count = sprites.world_tile_animation_frame_count("stairs")
            if count > 1:
                frame = sprites.world_tile_animation_frame("stairs", elapsed)
                return frame / (count - 1)
        period = self.MINIMAP_STAIRS_PULSE_PERIOD
        phase = (elapsed % period) / period
        return 1.0 - abs(1.0 - 2.0 * phase)

    def _minimap_marker_color(self, kind: str) -> tuple[int, int, int]:
        if kind == "bar":
            return self.MINIMAP_BAR_COLOR
        if kind == "garden":
            return self.MINIMAP_GARDEN_COLOR
        if kind == "relic":
            return self.HUD_GOLD
        return self.MINIMAP_STAIRS_COLOR

    def _minimap_draw_guidance(
        self,
        overlay: pygame.Surface,
        project,
        bounds: pygame.Rect,
        pulse: float,
    ) -> None:
        target = self.minimap_guidance()
        if target is None:
            return
        pos = project(*target)
        pos, clamped = self._minimap_clamp_to_viewport(pos, bounds)
        if clamped:
            self._minimap_draw_edge_arrow(overlay, pos, bounds.center, self.HUD_GOLD)
        else:
            self._minimap_draw_marker_glyph(overlay, "relic", pos, pulse)

    def _minimap_draw_players(self, overlay: pygame.Surface, project) -> None:
        local = self.player
        for actor in self.active_players():
            if actor is None or getattr(actor, "hp", 1) <= 0:
                continue
            x, y = project(actor.x, actor.y)
            is_local = actor is local
            color = (240, 238, 224) if is_local else self.MINIMAP_PARTNER_COLOR
            radius = max(2, self.ui(2)) if is_local else max(1, self.ui(2) - 1)
            center = (round(x), round(y))
            pygame.draw.circle(overlay, (*self.HUD_INK, 235), center, radius + 1)
            pygame.draw.circle(overlay, (*color, 255), center, radius)
            facing_x = getattr(actor, "facing_x", 0.0)
            facing_y = getattr(actor, "facing_y", 0.0)
            if is_local and (facing_x or facing_y):
                # Facing tick, run through the same projection so it matches
                # the on-screen heading.
                tip_x, tip_y = project(
                    actor.x + facing_x * 1.4, actor.y + facing_y * 1.4
                )
                dx, dy = tip_x - x, tip_y - y
                length = math.hypot(dx, dy) or 1.0
                reach = radius + max(1, self.ui(1))
                pygame.draw.line(
                    overlay,
                    (*color, 220),
                    (x, y),
                    (x + dx / length * reach, y + dy / length * reach),
                )

    # --- Panel -------------------------------------------------------------

    def draw_minimap(self) -> None:
        self._minimap_rect: pygame.Rect | None = None
        if getattr(self, "mobile_mode", False):
            return
        if not getattr(self, "minimap_visible", True):
            return
        if getattr(self, "dungeon", None) is None or getattr(self, "player", None) is None:
            return
        width, _height = self.screen.get_size()
        margin = self.ui(18)
        gap = self.ui(8)
        header = getattr(self, "_run_header_rect", None)
        left_limit = header.right + gap if header is not None else margin
        deck_scale = 1.6 if is_steam_deck() else 1.0
        panel_w = min(self.ui(self.MINIMAP_PANEL_W) * deck_scale, width - margin - left_limit)
        if panel_w < self.ui(self.MINIMAP_MIN_W) * deck_scale:
            # Too narrow to read (small window / large UI scale): suppress
            # rather than shrink into noise. Ctrl+M state is untouched.
            return
        top = self.ui(14)
        panel_h = self.ui(self.MINIMAP_PANEL_H) * deck_scale
        boss_top = self.boss_bar_top()
        if boss_top is not None and boss_top > top:
            # Give way to the boss plaque row during boss fights — but only
            # when the centered boss cluster actually reaches under the
            # right-aligned card. On the Deck the 1.6x card minimum otherwise
            # exceeded the header-height budget and the map vanished on every
            # boss floor (5.0 fix) even though the bar ended ~30 px short of
            # the card's left edge.
            panel_left = width - margin - panel_w
            metrics = self.boss_bar_metrics()
            if metrics is None or metrics[0].right + gap > panel_left:
                panel_h = min(panel_h, boss_top - self.ui(4) - top)
                if panel_h < self.ui(self.MINIMAP_MIN_H) * deck_scale:
                    return
        rect = pygame.Rect(width - margin - panel_w, top, panel_w, panel_h)
        self._minimap_rect = rect.copy()

        surface = pygame.Surface(rect.size, pygame.SRCALPHA)
        self.draw_ornate_hud_panel(
            surface,
            surface.get_rect(),
            (10, 10, 15, 215),
            (*self.theme.accent, 150),
            radius=self.ui(9),
        )
        content = self.ui_asset_content_rect("hud.panel", surface.get_rect())
        viewport = (
            content.inflate(-self.ui(4) * 2, -self.ui(4) * 2)
            if content is not None
            else surface.get_rect().inflate(-self.ui(8) * 2, -self.ui(8) * 2)
        )
        if viewport.width <= 0 or viewport.height <= 0:
            self.screen.blit(surface, rect)
            return
        # Ink well the fog shows through.
        pygame.draw.rect(surface, (6, 6, 10, 235), viewport, border_radius=self.ui(5))

        state = self._minimap_state()
        project, _half_w, _half_h = self._minimap_projector(viewport)
        overlay = pygame.Surface(viewport.size, pygame.SRCALPHA)
        dark = self.is_current_floor_dark()
        if dark:
            self._minimap_draw_dark_patch(overlay, project, state)
        else:
            self._minimap_update_terrain(state)
            terrain = state["surface"]
            origin_x, origin_y = state["origin"]
            anchor = project(0.5, 0.5)
            # Tile (0, 0) sits at (origin_x, origin_y) on the terrain surface
            # and must land at project(0.5, 0.5) on the overlay.
            overlay.blit(
                terrain,
                (round(anchor[0] - origin_x), round(anchor[1] - origin_y)),
            )

        pulse = 0.5 + 0.5 * math.sin(getattr(self, "elapsed", 0.0) * 2.6)
        # Inset past the edge arrows' ui(5) tip reach so a clamped arrow keeps
        # a small gap from the viewport edge instead of kissing it.
        bounds = overlay.get_rect().inflate(-self.ui(7) * 2, -self.ui(7) * 2)
        for kind, wx, wy in self.minimap_markers():
            pos, clamped = self._minimap_clamp_to_viewport(project(wx, wy), bounds)
            if clamped:
                self._minimap_draw_edge_arrow(
                    overlay, pos, bounds.center, self._minimap_marker_color(kind)
                )
            else:
                self._minimap_draw_marker_glyph(overlay, kind, pos, pulse)
        self._minimap_draw_guidance(overlay, project, bounds, pulse)
        self._minimap_draw_players(overlay, project)

        surface.blit(overlay, viewport.topleft)
        # Fine gold keyline framing the map well.
        pygame.draw.rect(
            surface,
            (*self.HUD_GOLD, 70),
            viewport,
            max(1, self.ui(1)),
            border_radius=self.ui(5),
        )
        self.screen.blit(surface, rect)
