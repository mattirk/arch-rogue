# pyright: reportAttributeAccessIssue=false, reportUnusedImport=false
from __future__ import annotations

import math
from collections import deque
from typing import cast

import pygame

from ..constants import (
    DARK_LEVEL_LIGHT_RADIUS,
    DUNGEON_DEPTH,
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
            if alpha < 255:
                surface = surface.copy()
                surface.set_alpha(alpha)
        self.screen.blit(surface, (sx - anchor_x, sy - anchor_y))

    def tile_seed(self, x: int, y: int) -> int:
        return (x * 1103515245 + y * 12345) & 31

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
        cap_top = (top[0], top[1] - wall_h)
        cap_right = (right[0], right[1] - wall_h)
        cap_bottom = (bottom[0], bottom[1] - wall_h)
        cap_left = (left[0], left[1] - wall_h)

        top_color = self.shade(self.theme.wall_top, 10 + seed % 7)
        left_color = self.shade(self.theme.wall_left, -4)
        right_color = self.shade(self.theme.wall_right, -20)
        edge_color = self.shade(self.theme.wall_edge, 8)
        mortar = self.mix(edge_color, (210, 205, 190), 0.18)
        crack = self.shade(self.theme.wall_right, -32)
        moss = self.mix(self.theme.accent, (35, 70, 43), 0.55)

        # The tile diamond is the floor-plane footprint. Draw the wall upward from
        # that footprint so actors read as moving between walls, not on top of them.
        pygame.draw.polygon(surface, left_color, [cap_left, cap_bottom, bottom, left])
        pygame.draw.polygon(
            surface, right_color, [cap_right, cap_bottom, bottom, right]
        )
        pygame.draw.polygon(
            surface, top_color, [cap_top, cap_right, cap_bottom, cap_left]
        )

        pygame.draw.lines(
            surface,
            edge_color,
            True,
            [cap_top, cap_right, cap_bottom, cap_left],
            WORLD_SCALE,
        )
        pygame.draw.line(
            surface, self.shade(edge_color, -12), cap_left, left, WORLD_SCALE
        )
        pygame.draw.line(
            surface, self.shade(edge_color, -28), cap_right, right, WORLD_SCALE
        )
        pygame.draw.line(
            surface, self.shade(edge_color, -48), cap_bottom, bottom, WORLD_SCALE
        )
        pygame.draw.line(
            surface, self.shade(edge_color, -42), left, bottom, WORLD_SCALE
        )
        pygame.draw.line(
            surface, self.shade(edge_color, -54), bottom, right, WORLD_SCALE
        )

        # Top cap seams stay high above the walking plane, avoiding the roof illusion.
        pygame.draw.line(
            surface,
            mortar,
            (sx - 28 * WORLD_SCALE, cap_bottom[1] - 5 * WORLD_SCALE),
            (sx + 2 * WORLD_SCALE, cap_top[1] + 12 * WORLD_SCALE),
            max(1, WORLD_SCALE),
        )
        pygame.draw.line(
            surface,
            mortar,
            (sx - 2 * WORLD_SCALE, cap_top[1] + 12 * WORLD_SCALE),
            (sx + 30 * WORLD_SCALE, cap_bottom[1] - 4 * WORLD_SCALE),
            max(1, WORLD_SCALE),
        )

        # Face courses descend from the raised cap to the floor footprint.
        face_start = cap_bottom[1] + 18 * WORLD_SCALE
        for row, offset in enumerate((0, 28, 56)):
            y_face = face_start + offset * WORLD_SCALE
            if y_face >= bottom[1] - 4 * WORLD_SCALE:
                continue
            pygame.draw.line(
                surface,
                self.shade(mortar, -28),
                (sx - 29 * WORLD_SCALE, y_face),
                (sx, y_face + 14 * WORLD_SCALE),
                max(1, WORLD_SCALE),
            )
            pygame.draw.line(
                surface,
                self.shade(mortar, -40),
                (sx, y_face + 14 * WORLD_SCALE),
                (sx + 29 * WORLD_SCALE, y_face),
                max(1, WORLD_SCALE),
            )
            joint = (-19 if (seed + row) & 1 else -8) * WORLD_SCALE
            pygame.draw.line(
                surface,
                self.shade(mortar, -34),
                (sx + joint, y_face - 8 * WORLD_SCALE),
                (sx + joint + 9 * WORLD_SCALE, y_face - 3 * WORLD_SCALE),
                max(1, WORLD_SCALE),
            )
            joint = (13 if (seed + row) & 2 else 23) * WORLD_SCALE
            pygame.draw.line(
                surface,
                self.shade(mortar, -44),
                (sx + joint, y_face - 2 * WORLD_SCALE),
                (sx + joint - 9 * WORLD_SCALE, y_face + 3 * WORLD_SCALE),
                max(1, WORLD_SCALE),
            )

        if seed & 3:
            pygame.draw.line(
                surface,
                crack,
                (sx + (8 - seed % 14) * WORLD_SCALE, cap_bottom[1] + 22 * WORLD_SCALE),
                (sx + (2 - seed % 10) * WORLD_SCALE, cap_bottom[1] + 48 * WORLD_SCALE),
                max(1, WORLD_SCALE),
            )
        if 8 <= seed <= 15 or seed > 27:
            pygame.draw.rect(
                surface,
                moss,
                (
                    sx - 27 * WORLD_SCALE,
                    bottom[1] - 8 * WORLD_SCALE,
                    (5 + seed % 5) * WORLD_SCALE,
                    2 * WORLD_SCALE,
                ),
            )

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
        base = self.theme.stair if is_stairs else self.theme.floor
        edge = self.theme.accent if is_stairs else self.theme.floor_edge
        slab_color = self.shade(base, (seed % 7) - 3)
        inner_edge = self.shade(edge, -18)
        groove = self.shade(base, -24)
        highlight = self.shade(base, 20)
        pebble = self.mix(edge, base, 0.45)

        pygame.draw.polygon(surface, slab_color, [top, right, bottom, left])
        pygame.draw.lines(surface, edge, True, [top, right, bottom, left], WORLD_SCALE)

        inset_top = (sx, sy - 20 * WORLD_SCALE)
        inset_right = (sx + 40 * WORLD_SCALE, sy)
        inset_bottom = (sx, sy + 20 * WORLD_SCALE)
        inset_left = (sx - 40 * WORLD_SCALE, sy)
        pygame.draw.lines(
            surface,
            inner_edge,
            True,
            [inset_top, inset_right, inset_bottom, inset_left],
            max(1, WORLD_SCALE),
        )
        pygame.draw.line(
            surface,
            groove,
            (sx - 28 * WORLD_SCALE, sy - 6 * WORLD_SCALE),
            (sx + 6 * WORLD_SCALE, sy + 11 * WORLD_SCALE),
            max(1, WORLD_SCALE),
        )
        pygame.draw.line(
            surface,
            self.shade(groove, 8),
            (sx - 2 * WORLD_SCALE, sy - 15 * WORLD_SCALE),
            (sx + 29 * WORLD_SCALE, sy + 1 * WORLD_SCALE),
            max(1, WORLD_SCALE),
        )
        pygame.draw.line(
            surface,
            highlight,
            (sx - 32 * WORLD_SCALE, sy - 2 * WORLD_SCALE),
            (sx - 13 * WORLD_SCALE, sy - 11 * WORLD_SCALE),
            max(1, WORLD_SCALE),
        )

        for index in range(2):
            px = sx + (((seed >> (index * 2)) & 15) - 7) * 5 * WORLD_SCALE
            py = sy + (((seed >> (index + 1)) & 7) - 3) * 4 * WORLD_SCALE
            pygame.draw.rect(
                surface,
                self.shade(pebble, -8 + index * 10),
                (px, py, max(1, 2 * WORLD_SCALE), max(1, WORLD_SCALE)),
            )

        if shop_floor and not is_stairs:
            gold = self.mix((218, 164, 62), self.theme.floor, 0.35)
            dark_gold = self.mix((126, 82, 34), self.theme.floor, 0.30)
            glow = self.mix((245, 205, 92), self.theme.floor, 0.42)
            pygame.draw.lines(
                surface,
                self.shade(dark_gold, -8),
                True,
                [inset_top, inset_right, inset_bottom, inset_left],
                max(1, WORLD_SCALE),
            )
            pygame.draw.line(
                surface,
                gold,
                (sx - 24 * WORLD_SCALE, sy),
                (sx, sy - 12 * WORLD_SCALE),
                max(1, WORLD_SCALE),
            )
            pygame.draw.line(
                surface,
                self.shade(gold, -16),
                (sx, sy - 12 * WORLD_SCALE),
                (sx + 24 * WORLD_SCALE, sy),
                max(1, WORLD_SCALE),
            )
            pygame.draw.line(
                surface,
                self.shade(gold, -22),
                (sx - 20 * WORLD_SCALE, sy + 8 * WORLD_SCALE),
                (sx + 20 * WORLD_SCALE, sy + 8 * WORLD_SCALE),
                max(1, WORLD_SCALE),
            )
            if seed & 1:
                pygame.draw.circle(
                    surface,
                    glow,
                    (sx + ((seed % 5) - 2) * 9 * WORLD_SCALE, sy + 2 * WORLD_SCALE),
                    max(1, WORLD_SCALE),
                )
            else:
                pygame.draw.rect(
                    surface,
                    self.shade(glow, -10),
                    (
                        sx - 3 * WORLD_SCALE,
                        sy - 3 * WORLD_SCALE,
                        6 * WORLD_SCALE,
                        max(1, WORLD_SCALE),
                    ),
                )

        if is_stairs:
            for step, width in ((-2, 18), (5, 12), (12, 6)):
                pygame.draw.line(
                    surface,
                    self.theme.stair,
                    (sx - width * WORLD_SCALE, sy + step * WORLD_SCALE),
                    (sx + width * WORLD_SCALE, sy + step * WORLD_SCALE),
                    3 * WORLD_SCALE,
                )
            pygame.draw.line(
                surface,
                self.theme.accent,
                (sx - 20 * WORLD_SCALE, sy - 8 * WORLD_SCALE),
                (sx + 20 * WORLD_SCALE, sy - 8 * WORLD_SCALE),
                WORLD_SCALE,
            )
            pygame.draw.circle(
                surface,
                self.theme.accent,
                (sx, sy - 16 * WORLD_SCALE),
                max(2, 2 * WORLD_SCALE),
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
        alpha = self.tile_visibility_alpha(x, y)
        if alpha < 255:
            surface = surface.copy()
            surface.set_alpha(alpha)
        self.screen.blit(surface, (sx - anchor_x, sy - anchor_y))
