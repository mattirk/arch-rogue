# pyright: reportAttributeAccessIssue=false, reportUnusedImport=false
from __future__ import annotations

import math
from collections import deque
from typing import cast

import pygame

from ..constants import (
    DARK_LEVEL_LIGHT_RADIUS,
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
        dark = self._frame_dark
        for s in range(min_x + min_y, max_x + max_y + 1):
            for x in range(min_x, max_x + 1):
                y = s - x
                if min_y <= y <= max_y and self.dungeon.in_bounds(x, y):
                    if dark and self.tile_visibility_alpha(x, y) <= 0:
                        continue
                    tile = self.dungeon.tiles[x][y]
                    if tile in (Tile.WALL, Tile.CLOSED_DOOR, Tile.OPEN_DOOR):
                        continue
                    self.draw_tile(x, y, tile)

    def draw_tile(self, x: int, y: int, tile: Tile) -> None:
        sx, sy = self.world_to_screen(x + 0.5, y + 0.5)
        seed = self.tile_seed(x, y)
        surface, anchor_x, anchor_y = self.tile_surface(
            tile, seed, self.is_shop_floor_tile(x, y)
        )
        if self._frame_dark:  # set at start of draw_world_objects/draw_dungeon
            alpha = self.tile_visibility_alpha(x, y)
            # Walls and doors are occluders: never render them translucent, or
            # the player can see floor/objects drawn behind them. Either draw
            # them fully opaque (within/just past the light radius) or skip
            # them entirely (handled by the cull in draw_world_objects). Only
            # floor tiles get the soft light-radius falloff.
            if tile not in (Tile.WALL, Tile.CLOSED_DOOR, Tile.OPEN_DOOR):
                if alpha < 255:
                    surface = surface.copy()
                    surface.set_alpha(alpha)
        self.screen.blit(surface, (sx - anchor_x, sy - anchor_y))

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
        for tile in (Tile.WALL, Tile.FLOOR, Tile.STAIRS):
            variants = (
                DUNGEON_WALL_VARIANTS if tile == Tile.WALL else DUNGEON_FLOOR_VARIANTS
            )
            for seed in range(variants):
                self.tile_surface(tile, seed, shop_floor=False)
                if tile in (Tile.FLOOR, Tile.STAIRS):
                    self.tile_surface(tile, seed, shop_floor=True)

    def is_shop_floor_tile(self, x: int, y: int) -> bool:
        shop_room = self._shop_room_bounds()
        if shop_room is None:
            return False
        rx, ry, rw, rh = shop_room
        if not (rx < x < rx + rw - 1 and ry < y < ry + rh - 1):
            return False
        return self.dungeon.tiles[x][y] in (Tile.FLOOR, Tile.STAIRS)

    def _shop_room_bounds(self) -> tuple[int, int, int, int] | None:
        cache = getattr(self, "_frame_cache", None)
        if cache is not None and "shop_room_bounds" in cache:
            return cache["shop_room_bounds"]  # type: ignore[no-any-return]
        shop_index = self.dungeon.shop_room_index
        result: tuple[int, int, int, int] | None = None
        if shop_index is not None and 0 <= shop_index < len(self.dungeon.rooms):
            room = self.dungeon.rooms[shop_index]
            result = (room.x, room.y, room.w, room.h)
        if cache is not None:
            cache["shop_room_bounds"] = result
        return result

    def tile_surface(
        self, tile: Tile, seed: int, shop_floor: bool = False
    ) -> tuple[pygame.Surface, int, int]:
        key = (self.theme.name, int(tile), seed, shop_floor)
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
                surface, sx, sy, top, right, bottom, left, wall_h, seed
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
                surface, sx, sy, top, right, bottom, left, tile, seed, shop_floor
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
    ) -> None:
        scale = WORLD_SCALE
        cap_top = (top[0], top[1] - wall_h)
        cap_right = (right[0], right[1] - wall_h)
        cap_bottom = (bottom[0], bottom[1] - wall_h)
        cap_left = (left[0], left[1] - wall_h)

        # Four coherent wall variants sharing palette, lighting, and
        # silhouette; they differ only in masonry pattern, so they read as the
        # same cut-stone wall with small, distinct character.
        variant = seed % DUNGEON_WALL_VARIANTS
        # Per-variant tint: a gentle tonal nudge aligned with the variant so
        # adjacent different-variant tiles also separate slightly in color.
        tint = variant * 2 - 3
        top_color = self.shade(self.theme.wall_top, 14 + tint)
        left_color = self.shade(self.theme.wall_left, tint)
        right_color = self.shade(self.theme.wall_right, tint)
        edge = self.shade(self.theme.wall_edge, 6)
        course_color = self.shade(edge, -34)
        course_hi = self.shade(course_color, 16)

        # --- Body: three clean polygons ---
        pygame.draw.polygon(surface, left_color, [cap_left, cap_bottom, bottom, left])
        pygame.draw.polygon(
            surface, right_color, [cap_right, cap_bottom, bottom, right]
        )
        pygame.draw.polygon(
            surface, top_color, [cap_top, cap_right, cap_bottom, cap_left]
        )

        # --- Smooth vertical gradient on each face: a lighter upper third and
        # a darker lower third. Keeps the sculpted look without banding clutter.
        for t0, t1, shade in ((0.0, 0.35, 10), (0.65, 1.0, -12)):
            ly0 = int(cap_left[1] + (left[1] - cap_left[1]) * t0)
            ly1 = int(cap_left[1] + (left[1] - cap_left[1]) * t1)
            lx0 = int(cap_left[0] + (left[0] - cap_left[0]) * t0)
            lx1 = int(cap_left[0] + (left[0] - cap_left[0]) * t1)
            by0 = int(cap_bottom[0] + (bottom[0] - cap_bottom[0]) * t0)
            by1 = int(cap_bottom[0] + (bottom[0] - cap_bottom[0]) * t1)
            pygame.draw.polygon(
                surface,
                self.shade(left_color, shade),
                [(lx0, ly0), (by0, ly0), (by1, ly1), (lx1, ly1)],
            )
            ry0 = int(cap_right[1] + (right[1] - cap_right[1]) * t0)
            ry1 = int(cap_right[1] + (right[1] - cap_right[1]) * t1)
            rx0 = int(cap_right[0] + (right[0] - cap_right[0]) * t0)
            rx1 = int(cap_right[0] + (right[0] - cap_right[0]) * t1)
            by0r = int(cap_bottom[0] + (bottom[0] - cap_bottom[0]) * t0)
            by1r = int(cap_bottom[0] + (bottom[0] - cap_bottom[0]) * t1)
            pygame.draw.polygon(
                surface,
                self.shade(right_color, shade),
                [(by0r, ry0), (rx0, ry0), (rx1, ry1), (by1r, ry1)],
            )

        # --- Cap highlight: a single bright rim along the lit top-left edge.
        pygame.draw.line(
            surface, self.shade(top_color, 30), cap_top, cap_left, max(1, scale)
        )

        # --- Masonry pattern: variant-driven courses + joints on both faces.
        # The same pattern is mirrored onto the left and right faces so the
        # wall reads as one continuous stone course wrapping the pillar.
        if variant == 0:
            # Ashlar: two regular courses, single aligned center joint.
            courses = (0.34, 0.66)
            joints = ([0.5], [0.5], [0.5])
        elif variant == 1:
            # Running bond: two courses, the middle row's joint offset to
            # stagger the brick seams.
            courses = (0.34, 0.66)
            joints = ([0.5], [0.28, 0.72], [0.5])
        elif variant == 2:
            # Large blocks: one tall course, single center joint per row.
            courses = (0.5,)
            joints = ([0.5], [0.5])
        else:
            # Weathered ashlar: same courses as variant 0, with an extra
            # off-center joint in the lower row suggesting a patched block.
            courses = (0.34, 0.66)
            joints = ([0.5], [0.5], [0.35, 0.7])

        left_face = self._wall_face_parallelogram(cap_left, cap_bottom, left, bottom)
        right_face = self._wall_face_parallelogram(cap_bottom, cap_right, bottom, right)
        self._draw_wall_masonry(
            surface, *left_face, courses, joints, course_color, scale
        )
        self._draw_wall_masonry(
            surface, *right_face, courses, joints, course_color, scale
        )
        # Faint highlight along the top course line to read as a cut lip.
        for face in (left_face, right_face):
            top_left, top_right, bot_left, bot_right = face
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
    ) -> None:
        is_stairs = tile == Tile.STAIRS
        scale = WORLD_SCALE
        base = self.theme.stair if is_stairs else self.theme.floor

        # Four coherent floor variants share a flat slab palette and differ
        # only in surface detail (seam / crack / cobble), so they read as one
        # continuous flagstone plane with scattered cracks rather than a grid
        # of beveled slabs. The old radial gradient + diamond outline darkened
        # every tile edge, which made the tile grid the dominant feature; a flat
        # fill lets adjacent tiles merge into a single stone surface.
        variant = seed % DUNGEON_FLOOR_VARIANTS
        tint = variant * 2 - 3
        slab = self.shade(base, tint)
        if is_stairs:
            # The stairwell sits in a recessed stone frame slightly darker
            # than the surrounding floor, so the round shaft reads as an
            # opening cut into the floor rather than a bright slab.
            slab = self.shade(self.theme.floor, -16)

        # --- Flat slab fill. No centered gradient, no inset bevel, no outline,
        # so neighboring tiles blend into a single continuous stone surface.
        # The per-variant tint (step 2, range -3..+3) gives gentle natural
        # mottling between adjacent different-variant tiles without drawing a
        # grid. ---
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

        # --- Shop floor: a single gilded medallion at the tile center, no
        # diamond frame, so the shop floor stays continuous and reads as a field
        # of scattered sigils rather than a tiled grid. Only the smooth-slab
        # variant carries a medallion so they read as occasional inlays. ---
        if shop_floor and not is_stairs and variant == 0:
            gold = self.mix((218, 164, 62), base, 0.4)
            gold_hi = self.mix((245, 215, 120), base, 0.3)
            pygame.draw.circle(surface, gold, (sx, sy), max(3, 3 * scale))
            pygame.draw.circle(surface, gold_hi, (sx, sy), max(2, 2 * scale))
            pygame.draw.circle(surface, gold_hi, (sx, sy), max(1, scale))

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

        # --- Treads: partial arc, painted deepest-first for correct occlusion. ---
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
            pygame.draw.polygon(
                surface, self.shade(tread, -55), outer + outer_bot[::-1]
            )
            # inner side face (the wall toward the central shaft)
            side = [
                inner[0],
                outer[0],
                (outer[0][0], outer[0][1] + riser_h),
                (inner[0][0], inner[0][1] + riser_h),
            ]
            pygame.draw.polygon(surface, self.shade(tread, -26), side)
            # tread top + lit lip + inner shadow
            pygame.draw.polygon(surface, tread, outer + inner)
            pygame.draw.lines(
                surface, self.shade(tread, 42), False, outer, max(2, scale)
            )
            pygame.draw.lines(surface, self.shade(tread, -28), False, inner, 1)
            # specular highlight on the two nearest (entry) steps
            if i < 2:
                pygame.draw.lines(
                    surface, self.shade(tread_light, 50), False, outer, max(1, scale)
                )

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
        dark = self._frame_dark

        def visible(x: float, y: float, margin: float = 0.35) -> bool:
            if not dark:
                return True
            return (
                self.light_distance_to_player(x, y) <= DARK_LEVEL_LIGHT_RADIUS + margin
            )

        min_x, max_x, min_y, max_y = self.visible_bounds()
        for s in range(min_x + min_y, max_x + max_y + 1):
            for x in range(min_x, max_x + 1):
                y = s - x
                if min_y <= y <= max_y and self.dungeon.in_bounds(x, y):
                    tile = self.dungeon.tiles[x][y]
                    if tile == Tile.WALL:
                        if dark and self.tile_visibility_alpha(x, y) <= 0:
                            continue
                        drawables.append((x + y + 1.02, "wall_tile", (x, y)))
                    elif tile in (Tile.CLOSED_DOOR, Tile.OPEN_DOOR):
                        if dark and self.tile_visibility_alpha(x, y) <= 0:
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
        relic_target = self.story_relic_target_position()
        if not dark or (
            relic_target is not None and visible(relic_target[0], relic_target[1], 0.65)
        ):
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
