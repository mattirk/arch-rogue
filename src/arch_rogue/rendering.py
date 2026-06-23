# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

import math
from collections import deque
from typing import cast

import pygame

from .constants import (
    DARK_LEVEL_LIGHT_RADIUS,
    DUNGEON_DEPTH,
    TILE_H,
    TILE_W,
    WORLD_SCALE,
    SlashEffect,
)
from .content import HUMANOID_ENEMY_NAMES
from .models import (
    Color,
    Enemy,
    ImpactEffect,
    Item,
    Player,
    Projectile,
    SecretCache,
    Shrine,
    StoryGuest,
    Tile,
    Trap,
)
from .quest_assets import (
    CutsceneActorAsset,
    SpriteAnimationFrameAsset,
    format_asset_text,
)


class RenderingMixin:
    def draw(self) -> None:
        self.screen.fill((10, 10, 14))
        if self.state == "title":
            self.draw_title_menu()
            pygame.display.flip()
            self.sync_music()
            return
        if self.state == "options":
            self.draw_options_menu()
            pygame.display.flip()
            self.sync_music()
            return
        if self.state == "about":
            self.draw_about_screen()
            pygame.display.flip()
            self.sync_music()
            return
        if self.state == "archetype_select":
            self.draw_archetype_select()
            pygame.display.flip()
            self.sync_music()
            return
        if self.state == "confirm_exit":
            self.draw_exit_confirmation()
            pygame.display.flip()
            self.sync_music()
            return
        self.draw_dungeon()
        self.draw_world_objects()
        self.draw_ambient_depth_overlay()
        self.draw_darkness_overlay()
        self.draw_ui()
        if self.active_cutscene is not None:
            self.draw_quest_cutscene_overlay()
        elif self.story_intro_pending:
            self.draw_story_intro_overlay()
        if self.inventory_open:
            self.draw_inventory()
        if self.character_menu_open:
            self.draw_character_menu()
        if self.show_help:
            self.draw_help_overlay()
        if self.state != "playing":
            self.draw_state_overlay()
        self.draw_screen_flash()
        pygame.display.flip()
        self.sync_music()

    def draw_dungeon(self) -> None:
        min_x, max_x, min_y, max_y = self.visible_bounds()
        for s in range(min_x + min_y, max_x + max_y + 1):
            for x in range(min_x, max_x + 1):
                y = s - x
                if min_y <= y <= max_y and self.dungeon.in_bounds(x, y):
                    if self.tile_visibility_alpha(x, y) <= 0:
                        continue
                    tile = self.dungeon.tiles[x][y]
                    if tile == Tile.WALL:
                        continue
                    self.draw_tile(x, y, tile)

    def ambient_overlay_surface(self) -> pygame.Surface:
        width, height = self.screen.get_size()
        key = (width, height, self.theme.name, self.ui_scale)
        cache: dict[tuple[int, int, str, int], pygame.Surface] = getattr(
            self, "ambient_overlay_cache", {}
        )
        cached = cache.get(key)
        if cached is not None:
            return cached

        overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        depth_tint = self.mix((8, 9, 14), self.theme.accent, 0.14)
        overlay.fill((*depth_tint, 18))
        layers = 9
        for index in range(layers):
            ratio = index / max(1, layers - 1)
            alpha = int(22 + (1.0 - ratio) * 54)
            inset_x = int(width * ratio * 0.07)
            inset_y = int(height * ratio * 0.08)
            rect = pygame.Rect(
                inset_x, inset_y, width - inset_x * 2, height - inset_y * 2
            )
            pygame.draw.rect(overlay, (0, 0, 0, alpha), rect, max(1, self.ui(4)))

        # Deterministic wisps: cached, subtle, and theme-colored so floors feel
        # ancient without per-frame noise generation.
        fog_color = self.mix(self.theme.accent, (38, 40, 50), 0.72)
        for index in range(9):
            seed = (index * 92821 + len(self.theme.name) * 31337) & 0xFFFF
            wx = int((seed % 997) / 997 * width)
            wy = int(
                ((seed // 7) % 991) / 991 * max(1, height - self.hud_panel_height())
            )
            fog_w = int((110 + seed % 140) * WORLD_SCALE)
            fog_h = int((22 + (seed // 13) % 34) * WORLD_SCALE)
            alpha = 7 + seed % 12
            pygame.draw.ellipse(
                overlay,
                (*fog_color, alpha),
                pygame.Rect(wx - fog_w // 2, wy - fog_h // 2, fog_w, fog_h),
            )

        try:
            overlay = overlay.convert_alpha()
        except pygame.error:
            pass
        cache[key] = overlay
        self.ambient_overlay_cache = cache
        return overlay

    def draw_ambient_depth_overlay(self) -> None:
        if self.state not in ("playing", "dead", "victory"):
            return
        if not self.is_current_floor_dark():
            self.screen.blit(self.ambient_overlay_surface(), (0, 0))
        # A faint breathing light around the player preserves readability under
        # the vignette without requiring expensive light masks.
        sx, sy = self.world_to_screen(self.player.x, self.player.y)
        pulse = 0.5 + 0.5 * math.sin(self.elapsed * 2.3)
        radius = int(
            ((88 if self.is_current_floor_dark() else 58) + pulse * 10) * WORLD_SCALE
        )
        light = pygame.Surface((radius * 2, radius), pygame.SRCALPHA)
        pygame.draw.ellipse(
            light,
            (*self.mix(self.theme.accent, (235, 220, 170), 0.35), int(10 + pulse * 8)),
            light.get_rect(),
        )
        self.screen.blit(light, light.get_rect(center=(sx, sy - 7 * WORLD_SCALE)))

    def draw_darkness_overlay(self) -> None:
        if self.state not in ("playing", "dead", "victory"):
            return
        if not self.is_current_floor_dark():
            return
        sx, sy = self.world_to_screen(self.player.x, self.player.y)
        pulse = 0.5 + 0.5 * math.sin(self.elapsed * 2.0)
        radius_x = int(DARK_LEVEL_LIGHT_RADIUS * TILE_W * (1.02 + pulse * 0.025))
        radius_y = int(DARK_LEVEL_LIGHT_RADIUS * TILE_H * (1.18 + pulse * 0.035))
        pad = int(42 * WORLD_SCALE)
        surface = pygame.Surface(
            (radius_x * 2 + pad * 2, radius_y * 2 + pad * 2), pygame.SRCALPHA
        )
        center = (surface.get_width() // 2, surface.get_height() // 2)

        glow_color = self.mix(self.theme.accent, (235, 218, 165), 0.35)
        warm_rect = pygame.Rect(0, 0, int(radius_x * 1.45), int(radius_y * 0.78))
        warm_rect.center = (center[0], center[1] + int(14 * WORLD_SCALE))
        pygame.draw.ellipse(surface, (*glow_color, int(34 + pulse * 18)), warm_rect)
        pygame.draw.ellipse(
            surface,
            (*self.shade(glow_color, 36), int(20 + pulse * 22)),
            warm_rect.inflate(-warm_rect.width // 2, -warm_rect.height // 2),
        )

        for layer in range(6):
            ratio = layer / 5
            ring = pygame.Rect(0, 0, radius_x * 2, radius_y * 2)
            ring.inflate_ip(
                int(-ratio * radius_x * 0.42), int(-ratio * radius_y * 0.42)
            )
            ring.center = center
            alpha = int(76 - ratio * 42)
            width = max(2, int((18 - ratio * 9) * WORLD_SCALE))
            pygame.draw.ellipse(surface, (0, 0, 0, alpha), ring, width)

        self.screen.blit(
            surface,
            surface.get_rect(center=(sx, sy - int(8 * WORLD_SCALE))),
        )

    def draw_tile(self, x: int, y: int, tile: Tile) -> None:
        sx, sy = self.world_to_screen(x + 0.5, y + 0.5)
        seed = self.tile_seed(x, y)
        surface, anchor_x, anchor_y = self.tile_surface(tile, seed)
        alpha = self.tile_visibility_alpha(x, y)
        if alpha < 255:
            surface = surface.copy()
            surface.set_alpha(alpha)
        self.screen.blit(surface, (sx - anchor_x, sy - anchor_y))

    def tile_seed(self, x: int, y: int) -> int:
        return (x * 1103515245 + y * 12345) & 31

    def shade(self, color: Color, amount: int) -> Color:
        return (
            max(0, min(255, color[0] + amount)),
            max(0, min(255, color[1] + amount)),
            max(0, min(255, color[2] + amount)),
        )

    def mix(self, a: Color, b: Color, ratio: float) -> Color:
        return (
            int(a[0] * (1.0 - ratio) + b[0] * ratio),
            int(a[1] * (1.0 - ratio) + b[1] * ratio),
            int(a[2] * (1.0 - ratio) + b[2] * ratio),
        )

    def tile_surface(self, tile: Tile, seed: int) -> tuple[pygame.Surface, int, int]:
        key = (self.theme.name, int(tile), seed)
        cached = self.tile_cache.get(key)
        if cached:
            return cached

        margin = 4 * WORLD_SCALE
        wall_h = 48 * WORLD_SCALE if tile == Tile.WALL else 0
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
        else:
            self.draw_floor_tile_surface(
                surface, sx, sy, top, right, bottom, left, tile, seed
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

        def visible(x: float, y: float, margin: float = 0.35) -> bool:
            return self.can_see_world_position(x, y, margin)

        min_x, max_x, min_y, max_y = self.visible_bounds()
        for s in range(min_x + min_y, max_x + max_y + 1):
            for x in range(min_x, max_x + 1):
                y = s - x
                if min_y <= y <= max_y and self.dungeon.in_bounds(x, y):
                    if self.dungeon.tiles[x][y] != Tile.WALL:
                        continue
                    if self.tile_visibility_alpha(x, y) <= 0:
                        continue
                    drawables.append((x + y + 1.02, "wall_tile", (x, y)))

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
        if not self.is_current_floor_dark() or (
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

    def draw_impact(self, effect: ImpactEffect) -> None:
        sx, sy = self.world_to_screen(effect.x, effect.y)
        life = max(0.0, min(1.0, effect.ttl / max(0.01, effect.max_ttl)))
        progress = effect.progress
        radius = max(
            2, int((effect.radius + progress * effect.radius * 1.4) * 28 * WORLD_SCALE)
        )
        alpha = max(0, min(230, int(205 * life)))
        overlay = pygame.Surface((radius * 2 + 18, radius * 2 + 18), pygame.SRCALPHA)
        center = (overlay.get_width() // 2, overlay.get_height() // 2)
        bright = self.shade(effect.color, 48)
        dark = self.shade(effect.color, -64)

        ground_rect = pygame.Rect(0, 0, radius * 2, max(4, radius // 2))
        ground_rect.center = (center[0], center[1] + radius // 3)
        pygame.draw.ellipse(
            overlay,
            (*effect.color, int(alpha * (0.16 if effect.kind == "death" else 0.30))),
            ground_rect,
            max(1, WORLD_SCALE),
        )

        if effect.kind == "blood":
            pygame.draw.circle(
                overlay, (*effect.color, alpha), center, max(2, radius // 6)
            )
            for index in range(7):
                angle = -math.pi * 0.85 + index * math.pi / 3.0 + progress * 0.35
                drop_len = radius * (0.28 + index % 3 * 0.08 + progress * 0.30)
                end = (
                    center[0] + int(math.cos(angle) * drop_len),
                    center[1] + int(math.sin(angle) * drop_len * 0.62),
                )
                pygame.draw.circle(
                    overlay,
                    (*self.shade(effect.color, -15), int(alpha * 0.84)),
                    end,
                    max(1, radius // 13),
                )
        elif effect.kind == "death":
            ring_radius = max(2, int(radius * (0.32 + progress * 0.58)))
            pygame.draw.circle(
                overlay,
                (*dark, int(alpha * 0.46)),
                center,
                ring_radius,
                max(1, WORLD_SCALE),
            )
            pygame.draw.circle(
                overlay,
                (*bright, int(alpha * 0.34)),
                center,
                max(2, ring_radius // 2),
                max(1, WORLD_SCALE),
            )
            for index in range(10):
                angle = index * math.tau / 10 + progress * 1.2
                smoke_radius = radius * (0.22 + progress * 0.55 + (index % 2) * 0.06)
                puff = (
                    center[0] + int(math.cos(angle) * smoke_radius),
                    center[1]
                    + int(math.sin(angle) * smoke_radius * 0.55)
                    - int(progress * 10),
                )
                pygame.draw.circle(
                    overlay,
                    (*self.mix(dark, bright, 0.28), int(alpha * 0.22)),
                    puff,
                    max(2, radius // 9),
                )
        elif effect.kind == "cast":
            ring_radius = max(3, int(radius * (0.42 + progress * 0.48)))
            pygame.draw.circle(
                overlay,
                (*effect.color, int(alpha * 0.36)),
                center,
                ring_radius,
                max(1, WORLD_SCALE),
            )
            for index in range(6):
                angle = index * math.tau / 6 - progress * 0.9
                rune = (
                    center[0] + int(math.cos(angle) * ring_radius),
                    center[1] + int(math.sin(angle) * ring_radius * 0.55),
                )
                pygame.draw.rect(
                    overlay,
                    (*bright, int(alpha * 0.72)),
                    (
                        rune[0] - WORLD_SCALE,
                        rune[1] - WORLD_SCALE,
                        WORLD_SCALE * 2,
                        WORLD_SCALE * 2,
                    ),
                )
            pygame.draw.circle(
                overlay, (*bright, int(alpha * 0.62)), center, max(2, radius // 7)
            )
        elif effect.kind == "dash":
            for index in range(4):
                streak_alpha = int(alpha * (0.55 - index * 0.10))
                length = int(radius * (0.8 + progress * 0.8 + index * 0.25))
                y_offset = int((index - 1.5) * 3 * WORLD_SCALE)
                pygame.draw.line(
                    overlay,
                    (*bright, max(0, streak_alpha)),
                    (center[0] - length, center[1] + y_offset),
                    (center[0] + length // 2, center[1] + y_offset // 2),
                    max(1, WORLD_SCALE),
                )
        else:
            pygame.draw.circle(
                overlay, (*effect.color, alpha), center, max(2, radius // 5)
            )
            spoke_count = 9 if effect.kind in ("burst", "hit") else 6
            for index in range(spoke_count):
                angle = index * math.tau / spoke_count + progress * 0.8
                inner = radius * (0.12 + progress * 0.15)
                outer = radius * (0.35 + progress * 0.52)
                start = (
                    center[0] + int(math.cos(angle) * inner),
                    center[1] + int(math.sin(angle) * inner * 0.55),
                )
                end = (
                    center[0] + int(math.cos(angle) * outer),
                    center[1] + int(math.sin(angle) * outer * 0.55),
                )
                pygame.draw.line(
                    overlay,
                    (*bright, alpha),
                    start,
                    end,
                    max(1, WORLD_SCALE),
                )

        self.screen.blit(overlay, overlay.get_rect(center=(sx, sy - 12 * WORLD_SCALE)))

    def draw_shadow(
        self,
        x: float,
        y: float,
        width: int,
        height: int,
        moving: bool = False,
        lift: float = 0.0,
    ) -> None:
        sx, sy = self.world_to_screen(x, y)
        pulse = 0.5 + 0.5 * math.sin(self.elapsed * 12.0)
        squash = pulse * 1.4 if moving else 0.0
        scaled_w = max(1, round((width + squash * 3 + lift) * WORLD_SCALE))
        scaled_h = max(1, round((height - squash - lift * 0.32) * WORLD_SCALE))
        shadow = pygame.Surface((scaled_w, scaled_h), pygame.SRCALPHA)
        alpha = 92 if moving else 78
        pygame.draw.ellipse(shadow, (0, 0, 0, alpha), shadow.get_rect())
        pygame.draw.ellipse(
            shadow,
            (0, 0, 0, alpha // 2),
            shadow.get_rect().inflate(-scaled_w // 4, -scaled_h // 3),
        )
        self.screen.blit(
            shadow,
            shadow.get_rect(center=(sx, sy + 10 * WORLD_SCALE)),
        )

    def walk_offsets(self, actor: Player | Enemy) -> tuple[int, int]:
        sway, bob, _lean, _stretch = self.actor_animation(actor)
        return round(sway), round(bob)

    def actor_animation(
        self, actor: Player | Enemy
    ) -> tuple[float, float, float, float]:
        if actor.moving:
            phase = actor.anim_time * math.tau
            footfall = 0.5 - 0.5 * math.cos(phase * 2.0)
            stride = math.sin(phase)
            bob = 0.45 + footfall * 1.15
            sway = stride * 0.55
            lean = 0.18 + math.sin(phase - 0.35) * 0.10
            return sway, bob, lean, 1.0
        idle = math.sin(self.elapsed * 2.2 + actor.x * 0.7 + actor.y * 0.4)
        return 0.0, idle * 0.32, idle * 0.08, 1.0

    def iso_screen_direction(self, dx: float, dy: float) -> tuple[float, float]:
        screen_dx = (dx - dy) * TILE_W / 2
        screen_dy = (dx + dy) * TILE_H / 2
        length = math.hypot(screen_dx, screen_dy)
        if length <= 0.001:
            return 1.0, 0.0
        return screen_dx / length, screen_dy / length

    def draw_movement_trail(
        self, actor: Player | Enemy, color: Color, size: int = 2
    ) -> None:
        if not actor.moving:
            return
        sx, sy = self.world_to_screen(actor.x, actor.y)
        vx, vy = self.iso_screen_direction(actor.move_x, actor.move_y)
        phase = abs(math.sin(actor.anim_time * math.tau))
        px_perp = -vy
        for step, alpha in ((1, 92), (2, 58), (3, 30)):
            offset = math.sin(actor.anim_time * math.tau + step) * 3 * WORLD_SCALE
            px = sx - int(vx * (7 + step * 8) * WORLD_SCALE + px_perp * offset)
            py = sy + int(8 * WORLD_SCALE) - int(vy * (3 + step * 5) * WORLD_SCALE)
            dust = pygame.Surface(
                (size * (5 + step) * WORLD_SCALE, size * 2 * WORLD_SCALE),
                pygame.SRCALPHA,
            )
            pygame.draw.ellipse(
                dust,
                (*color, int(alpha * (0.55 + phase * 0.45))),
                dust.get_rect(),
            )
            pygame.draw.rect(
                dust,
                (*self.shade(color, 35), max(18, alpha // 3)),
                dust.get_rect().inflate(
                    -dust.get_width() // 2, -dust.get_height() // 2
                ),
            )
            self.screen.blit(dust, dust.get_rect(center=(px, py)))

    def is_humanoid(self, actor: Player | Enemy) -> bool:
        if isinstance(actor, Player):
            return True
        return actor.kind == "boss" or actor.name in HUMANOID_ENEMY_NAMES

    def humanoid_run_scale(self, actor: Player | Enemy) -> float:
        if isinstance(actor, Player):
            return 1.0
        if actor.kind == "boss":
            return 1.24
        if actor.name in ("Gate Warden", "Crypt Brute"):
            return 1.12
        if actor.name == "Bone Imp":
            return 0.82
        return 0.96

    def humanoid_limb_palette(
        self, actor: Player | Enemy, hostile: bool = False
    ) -> tuple[Color, Color, Color, Color]:
        if isinstance(actor, Player):
            return (44, 75, 132), (154, 168, 178), (74, 48, 39), (19, 24, 35)
        if actor.kind == "boss":
            return (
                self.theme.accent,
                self.shade(self.theme.accent, 35),
                (50, 34, 45),
                (28, 18, 24),
            )
        palettes: dict[str, tuple[Color, Color, Color, Color]] = {
            "Cultist": ((78, 44, 132), (184, 138, 218), (38, 28, 54), (22, 18, 33)),
            "Grave Archer": ((86, 116, 72), (145, 164, 98), (58, 43, 31), (26, 31, 25)),
            "Rune Sentinel": (
                (88, 98, 112),
                (142, 155, 168),
                (42, 46, 56),
                (28, 30, 38),
            ),
            "Hollow Knight": (
                (74, 78, 86),
                (182, 178, 160),
                (42, 38, 42),
                (24, 22, 24),
            ),
            "Gate Warden": (
                (171, 105, 48),
                (126, 132, 128),
                (58, 46, 43),
                (29, 23, 22),
            ),
            "Crypt Brute": (
                (155, 105, 74),
                (126, 132, 128),
                (58, 46, 43),
                (29, 23, 22),
            ),
            "Bone Imp": ((150, 92, 180), (210, 160, 230), (64, 42, 76), (30, 22, 36)),
            "Ghoul": ((118, 154, 94), (161, 189, 116), (72, 55, 47), (31, 20, 22)),
        }
        return palettes.get(
            actor.name,
            ((135, 80, 76), (180, 110, 92), (64, 42, 38), (28, 20, 22))
            if hostile
            else ((90, 90, 110), (135, 135, 150), (55, 45, 50), (25, 25, 30)),
        )

    def draw_jointed_limb(
        self,
        points: tuple[tuple[float, float], tuple[float, float], tuple[float, float]],
        color: Color,
        outline: Color,
        width: int,
        alpha: int = 255,
    ) -> None:
        rounded_points = tuple((round(x), round(y)) for x, y in points)
        surface = self.screen
        min_x = 0
        min_y = 0
        if alpha < 255:
            min_x = min(point[0] for point in rounded_points) - width * 3
            min_y = min(point[1] for point in rounded_points) - width * 3
            max_x = max(point[0] for point in rounded_points) + width * 3
            max_y = max(point[1] for point in rounded_points) + width * 3
            surface = pygame.Surface((max_x - min_x, max_y - min_y), pygame.SRCALPHA)
            rounded_points = tuple((x - min_x, y - min_y) for x, y in rounded_points)
        pygame.draw.lines(
            surface, outline, False, rounded_points, width + max(1, WORLD_SCALE)
        )
        pygame.draw.lines(surface, color, False, rounded_points, width)
        for point in rounded_points:
            pygame.draw.circle(surface, color, point, max(1, width // 2))
        if surface is not self.screen:
            surface.set_alpha(alpha)
            self.screen.blit(surface, (min_x, min_y))

    def draw_humanoid_run_layer(
        self,
        actor: Player | Enemy,
        anchor_x: float,
        anchor_bottom: float,
        layer: str,
        hostile: bool = False,
    ) -> None:
        if not self.is_humanoid(actor):
            return
        scale = WORLD_SCALE * self.humanoid_run_scale(actor)
        vx, vy = self.iso_screen_direction(actor.move_x, actor.move_y)
        px, py = -vy, vx
        phase = actor.anim_time * math.tau
        moving_amount = 1.0 if actor.moving else 0.12
        torso_color, limb_color, boot_color, outline = self.humanoid_limb_palette(
            actor, hostile
        )
        if layer == "back":
            torso_color = self.shade(torso_color, -32)
            limb_color = self.shade(limb_color, -30)
            boot_color = self.shade(boot_color, -26)
            alpha = 210
        else:
            alpha = 255

        hip_y = anchor_bottom - 18.0 * scale
        shoulder_y = anchor_bottom - 39.0 * scale
        hip_width = 4.6 * scale
        shoulder_width = 5.4 * scale
        stride = 12.0 * scale * moving_amount
        arm_stride = 9.5 * scale * moving_amount
        leg_len = 17.5 * scale
        arm_len = 14.0 * scale
        line_w = max(2, round(2.2 * scale))

        torso_top = (anchor_x + vx * 2.0 * scale, shoulder_y)
        torso_bottom = (anchor_x - vx * 1.5 * scale, hip_y)
        if layer == "back":
            pygame.draw.line(
                self.screen,
                outline,
                (round(torso_top[0]), round(torso_top[1])),
                (round(torso_bottom[0]), round(torso_bottom[1])),
                line_w + WORLD_SCALE,
            )
            pygame.draw.line(
                self.screen,
                self.shade(torso_color, -18),
                (round(torso_top[0]), round(torso_top[1])),
                (round(torso_bottom[0]), round(torso_bottom[1])),
                line_w,
            )

        for side in (-1, 1):
            side_is_front_layer = side > 0
            if (layer == "front") != side_is_front_layer:
                continue
            phase_offset = 0.0 if side > 0 else math.pi
            leg_swing = math.sin(phase + phase_offset)
            lift = (
                (0.5 - 0.5 * math.cos(phase + phase_offset))
                * 4.5
                * scale
                * moving_amount
            )
            knee_bend = lift * 0.7 + abs(leg_swing) * 1.3 * scale * moving_amount
            hip = (
                anchor_x + px * side * hip_width,
                hip_y + py * side * hip_width * 0.25,
            )
            knee = (
                hip[0] + vx * leg_swing * stride * 0.46 + px * side * 1.7 * scale,
                hip[1]
                + leg_len * 0.48
                + vy * leg_swing * stride * 0.16
                - knee_bend * 0.38,
            )
            foot = (
                hip[0] + vx * leg_swing * stride + px * side * 2.8 * scale,
                hip[1] + leg_len + vy * leg_swing * stride * 0.26 - lift,
            )
            self.draw_jointed_limb(
                (hip, knee, foot), limb_color, outline, line_w, alpha
            )
            foot_tip = (foot[0] + vx * 4.2 * scale, foot[1] + vy * 1.8 * scale)
            pygame.draw.line(
                self.screen,
                outline,
                (round(foot[0]), round(foot[1])),
                (round(foot_tip[0]), round(foot_tip[1])),
                line_w + WORLD_SCALE,
            )
            pygame.draw.line(
                self.screen,
                boot_color,
                (round(foot[0]), round(foot[1])),
                (round(foot_tip[0]), round(foot_tip[1])),
                line_w,
            )

        for side in (-1, 1):
            side_is_front_layer = side > 0
            if (layer == "front") != side_is_front_layer:
                continue
            phase_offset = 0.0 if side > 0 else math.pi
            leg_swing = math.sin(phase + phase_offset)
            arm_swing = -leg_swing
            shoulder = (
                anchor_x + px * side * shoulder_width,
                shoulder_y + py * side * shoulder_width * 0.2,
            )
            elbow = (
                shoulder[0]
                + vx * arm_swing * arm_stride * 0.50
                + px * side * 1.1 * scale,
                shoulder[1] + arm_len * 0.42 + vy * arm_swing * arm_stride * 0.14,
            )
            hand = (
                shoulder[0] + vx * arm_swing * arm_stride - px * side * 1.5 * scale,
                shoulder[1] + arm_len + vy * arm_swing * arm_stride * 0.22,
            )
            self.draw_jointed_limb(
                (shoulder, elbow, hand), torso_color, outline, max(2, line_w - 1), alpha
            )

    def draw_sprite_direction_cue(
        self,
        sx: int,
        sy: int,
        dx: float,
        dy: float,
        color: Color,
        hostile: bool = False,
    ) -> None:
        vx, vy = self.iso_screen_direction(dx, dy)
        scale = WORLD_SCALE
        chest_x = sx + int(vx * 12 * scale)
        chest_y = sy - 42 * scale + int(vy * 5 * scale)
        foot_x = sx + int(vx * 10 * scale)
        foot_y = sy - 9 * scale + int(vy * 4 * scale)
        dark = (30, 24, 30) if hostile else (25, 33, 44)
        pygame.draw.rect(
            self.screen,
            dark,
            (chest_x - 3 * scale, chest_y - 3 * scale, 6 * scale, 6 * scale),
        )
        pygame.draw.rect(
            self.screen,
            color,
            (chest_x - 2 * scale, chest_y - 2 * scale, 4 * scale, 4 * scale),
        )
        pygame.draw.line(
            self.screen,
            color,
            (sx, sy - 20 * scale),
            (foot_x, foot_y),
            max(1, scale),
        )
        pygame.draw.rect(
            self.screen,
            color,
            (foot_x - 2 * scale, foot_y - scale, 4 * scale, 2 * scale),
        )

    def blit_sprite(
        self,
        sprite: pygame.Surface,
        x: float,
        y: float,
        y_offset: float = 0.0,
        facing_x: float = 1.0,
        x_offset: float = 0.0,
        stretch: float = 1.0,
        lean: float = 0.0,
        alpha: int = 255,
    ) -> tuple[int, int]:
        sx, sy = self.world_to_screen(x, y)
        turned_sprite = (
            pygame.transform.flip(sprite, True, False) if facing_x < 0 else sprite
        )
        if abs(stretch - 1.0) > 0.018:
            turned_sprite = pygame.transform.scale(
                turned_sprite,
                (
                    max(1, round(turned_sprite.get_width() / stretch)),
                    max(1, round(turned_sprite.get_height() * stretch)),
                ),
            )
        if abs(lean) > 1.85:
            turned_sprite = pygame.transform.rotate(
                turned_sprite, -lean if facing_x >= 0 else lean
            )
        if alpha < 255:
            turned_sprite = turned_sprite.copy()
            turned_sprite.set_alpha(alpha)
        rect = turned_sprite.get_rect(
            midbottom=(
                round(sx + x_offset * WORLD_SCALE),
                round(sy + y_offset * WORLD_SCALE),
            )
        )
        self.screen.blit(turned_sprite, rect)
        return rect.centerx, sy

    def player_visual_state(self, player: Player) -> str:
        if getattr(self, "player_hit_flash", 0.0) > 0.0:
            return "hit"
        action_state = getattr(self, "player_action_state", "")
        if getattr(self, "player_action_ttl", 0.0) > 0.0 and action_state:
            return action_state
        return "run" if player.moving else "idle"

    def enemy_visual_state(self, enemy: Enemy) -> str:
        if getattr(self, "enemy_hit_flashes", {}).get(id(enemy), 0.0) > 0.0:
            return "hit"
        just_attacked = enemy.attack_timer > max(0.0, enemy.attack_cooldown - 0.22)
        if just_attacked and enemy.telegraph == "cast":
            return "cast"
        if just_attacked and enemy.telegraph == "melee":
            return "attack"
        return "run" if enemy.moving else "idle"

    def draw_hit_flash_overlay(
        self, sx: int, sy: int, width: int, height: int, ttl: float, color: Color
    ) -> None:
        if ttl <= 0:
            return
        life = max(0.0, min(1.0, ttl / 0.22))
        overlay = pygame.Surface(
            (width + 12 * WORLD_SCALE, height + 10 * WORLD_SCALE), pygame.SRCALPHA
        )
        rect = overlay.get_rect()
        pygame.draw.ellipse(
            overlay,
            (*self.shade(color, 55), int(70 * life)),
            rect.inflate(-rect.width // 5, -rect.height // 7),
            max(1, WORLD_SCALE),
        )
        for index in range(4):
            angle = self.elapsed * 9.0 + index * math.tau / 4
            start = (rect.centerx, rect.centery)
            end = (
                rect.centerx + int(math.cos(angle) * rect.width * 0.36),
                rect.centery + int(math.sin(angle) * rect.height * 0.28),
            )
            pygame.draw.line(
                overlay, (*color, int(96 * life)), start, end, max(1, WORLD_SCALE)
            )
        self.screen.blit(overlay, overlay.get_rect(center=(sx, sy - height // 2)))

    def cooldown_ratio(self, timer: float, cooldown: float) -> float:
        if cooldown <= 0.001:
            return 0.0
        return max(0.0, min(1.0, timer / cooldown))

    def draw_hud_cooldown_pips(self, bounds: pygame.Rect) -> None:
        timers = (
            ("M", self.player.melee_timer, self.melee_cooldown(), (255, 226, 150)),
            ("B", self.player.bolt_timer, self.bolt_cooldown(), (96, 190, 255)),
            ("N", self.player.nova_timer, self.nova_cooldown(), (185, 125, 255)),
            ("D", self.player.dash_timer, self.dash_cooldown(), (225, 184, 82)),
        )
        active = [entry for entry in timers if entry[1] > 0.001 and entry[2] > 0.001]
        if not active:
            return

        radius = max(self.ui(7), min(self.ui(12), bounds.height // 8))
        spacing = radius * 2 + self.ui(7)
        total_w = spacing * (len(active) - 1) + radius * 2
        base_x = bounds.right - total_w + radius
        center_y = bounds.y + radius + self.ui(2)
        line_w = max(1, self.ui(1))
        label = self.tiny_font.render("CD", True, (154, 148, 138))
        label_rect = label.get_rect(
            right=max(bounds.x, base_x - radius - self.ui(6)), centery=center_y
        )
        self.screen.blit(label, label_rect)

        for index, (key, timer, cooldown, color) in enumerate(active):
            cx = base_x + index * spacing
            cy = center_y
            remaining = self.cooldown_ratio(timer, cooldown)
            progress = 1.0 - remaining
            outer_rect = pygame.Rect(0, 0, radius * 2, radius * 2)
            outer_rect.center = (cx, cy)

            pygame.draw.circle(self.screen, (14, 13, 18), (cx, cy), radius)
            pygame.draw.circle(
                self.screen,
                (74, 70, 82),
                (cx, cy),
                max(1, radius - self.ui(2)),
                line_w,
            )
            fill_h = max(1, int((radius * 1.45) * progress))
            fill_rect = pygame.Rect(
                cx - radius // 2,
                cy + radius // 2 - fill_h,
                radius,
                fill_h,
            )
            pygame.draw.rect(self.screen, (*self.shade(color, -38), 165), fill_rect)

            if progress > 0.0:
                start = -math.pi / 2
                end = start + math.tau * progress
                pygame.draw.arc(
                    self.screen,
                    color,
                    outer_rect.inflate(-self.ui(1), -self.ui(1)),
                    start,
                    end,
                    max(2, line_w + 1),
                )
            text = self.tiny_font.render(key, True, (226, 220, 210))
            self.screen.blit(text, text.get_rect(center=(cx, cy)))

    def inventory_count_for_slot(self, slot: str) -> int:
        return sum(1 for item in self.player.inventory if item.slot == slot)

    def hud_action_slots(self) -> list[dict[str, object]]:
        melee_name, bolt_name, nova_name, dash_name = self.skill_names()
        class_color = self.skill_color()
        return [
            {
                "kind": "melee",
                "icon": "melee",
                "hotkey": "1",
                "label": melee_name,
                "timer": self.player.melee_timer,
                "cooldown": self.melee_cooldown(),
                "cost": self.melee_stamina_cost(),
                "resource": self.player.stamina,
                "resource_name": "ST",
                "color": self.mix((255, 226, 150), class_color, 0.18),
            },
            {
                "kind": "bolt",
                "icon": "bolt",
                "hotkey": "2",
                "label": bolt_name,
                "timer": self.player.bolt_timer,
                "cooldown": self.bolt_cooldown(),
                "cost": self.bolt_mana_cost(),
                "resource": self.player.mana,
                "resource_name": "MP",
                "color": self.mix((96, 190, 255), class_color, 0.24),
            },
            {
                "kind": "nova",
                "icon": "nova",
                "hotkey": "3",
                "label": nova_name,
                "timer": self.player.nova_timer,
                "cooldown": self.nova_cooldown(),
                "cost": self.nova_mana_cost(),
                "resource": self.player.mana,
                "resource_name": "MP",
                "color": self.mix((185, 125, 255), class_color, 0.24),
            },
            {
                "kind": "dash",
                "icon": "dash",
                "hotkey": "4",
                "label": dash_name,
                "timer": self.player.dash_timer,
                "cooldown": self.dash_cooldown(),
                "cost": self.dash_stamina_cost(),
                "resource": self.player.stamina,
                "resource_name": "ST",
                "color": self.mix((225, 184, 82), class_color, 0.18),
            },
            {
                "kind": "health_potion",
                "icon": "health_potion",
                "hotkey": "5",
                "label": "Health",
                "timer": 0.0,
                "cooldown": 0.0,
                "cost": 0,
                "resource": self.player.hp,
                "resource_name": "HP",
                "count": self.inventory_count_for_slot("potion"),
                "color": (220, 66, 70),
            },
            {
                "kind": "mana_potion",
                "icon": "mana_potion",
                "hotkey": "6",
                "label": "Mana",
                "timer": 0.0,
                "cooldown": 0.0,
                "cost": 0,
                "resource": self.player.mana,
                "resource_name": "MP",
                "count": self.inventory_count_for_slot("mana_potion"),
                "color": (76, 128, 230),
            },
        ]

    def hud_action_slot_status(self, slot: dict[str, object]) -> str:
        kind = str(slot.get("kind", ""))
        if kind == "health_potion":
            count = int(slot.get("count", 0))
            if count <= 0:
                return "EMPTY"
            return "FULL" if self.player.hp >= self.player.max_hp else f"x{count}"
        if kind == "mana_potion":
            count = int(slot.get("count", 0))
            if count <= 0:
                return "EMPTY"
            return "FULL" if self.player.mana >= self.player.max_mana else f"x{count}"
        timer = float(slot.get("timer", 0.0))
        if timer > 0.001:
            return f"{timer:.1f}s"
        resource = float(slot.get("resource", 0.0))
        cost = float(slot.get("cost", 0.0))
        if resource < cost:
            return str(slot.get("resource_name", "RES"))
        return "READY"

    def hud_action_slot_ready(self, slot: dict[str, object]) -> bool:
        kind = str(slot.get("kind", ""))
        if kind == "health_potion":
            return int(slot.get("count", 0)) > 0 and self.player.hp < self.player.max_hp
        if kind == "mana_potion":
            return (
                int(slot.get("count", 0)) > 0
                and self.player.mana < self.player.max_mana
            )
        return float(slot.get("timer", 0.0)) <= 0.001 and float(
            slot.get("resource", 0.0)
        ) >= float(slot.get("cost", 0.0))

    def draw_hud_action_bar(self, rect: pygame.Rect) -> None:
        slots = self.hud_action_slots()
        if not slots or rect.width < self.ui(210) or rect.height < self.ui(42):
            return
        inner = rect.inflate(-max(self.ui(12), 12), -max(self.ui(8), 8))
        gap = max(self.ui(6), 6)
        icon_size = min(
            max(self.ui(40), 40),
            inner.height,
            max(28, (inner.width - gap * (len(slots) - 1)) // len(slots)),
        )
        if icon_size < 30:
            gap = max(3, self.ui(3))
            icon_size = max(24, (inner.width - gap * (len(slots) - 1)) // len(slots))
        total_w = icon_size * len(slots) + gap * (len(slots) - 1)
        x = inner.centerx - total_w // 2
        y = inner.centery - icon_size // 2
        for slot in slots:
            self.draw_hud_action_icon(slot, pygame.Rect(x, y, icon_size, icon_size))
            x += icon_size + gap

    def draw_hud_action_icon(self, slot: dict[str, object], rect: pygame.Rect) -> None:
        color = cast(Color, slot.get("color", self.theme.accent))
        ready = self.hud_action_slot_ready(slot)
        status = self.hud_action_slot_status(slot)
        timer = float(slot.get("timer", 0.0))
        cooldown = float(slot.get("cooldown", 0.0))
        remaining = self.cooldown_ratio(timer, cooldown)
        border = color if ready or timer > 0.001 else (92, 86, 94)
        fill = self.shade(color, -112 if ready else -136)
        pygame.draw.rect(self.screen, fill, rect, border_radius=self.ui(8))
        pygame.draw.rect(
            self.screen, border, rect, max(1, self.ui(1)), border_radius=self.ui(8)
        )
        shine = pygame.Rect(rect.x + 2, rect.y + 2, rect.width - 4, rect.height // 3)
        shine_surface = pygame.Surface(shine.size, pygame.SRCALPHA)
        pygame.draw.rect(
            shine_surface,
            (255, 255, 255, 18 if ready else 9),
            shine_surface.get_rect(),
            border_radius=self.ui(7),
        )
        self.screen.blit(shine_surface, shine)

        glyph_rect = rect.inflate(-self.ui(13), -self.ui(14))
        glyph_rect.y += self.ui(3)
        glyph_rect.height = max(8, glyph_rect.height - self.tiny_font.get_height() // 2)
        self.draw_hud_action_glyph(str(slot.get("icon", "")), glyph_rect, color, ready)

        label_rect = pygame.Rect(
            rect.x + self.ui(3),
            rect.bottom - self.tiny_font.get_height() - self.ui(2),
            rect.width - self.ui(6),
            self.tiny_font.get_height(),
        )
        self.draw_ui_text(
            self.screen,
            str(slot.get("label", "")),
            self.tiny_font,
            (224, 218, 205) if ready else (162, 158, 152),
            label_rect,
            align="center",
        )

        hotkey = str(slot.get("hotkey", ""))
        key_w = min(
            rect.width - self.ui(4),
            max(self.ui(16), self.tiny_font.size(hotkey)[0] + self.ui(6)),
        )
        key_rect = pygame.Rect(
            rect.x + self.ui(3), rect.y + self.ui(3), key_w, self.ui(14)
        )
        pygame.draw.rect(self.screen, (9, 8, 12), key_rect, border_radius=self.ui(4))
        pygame.draw.rect(
            self.screen,
            (*border, 255),
            key_rect,
            max(1, self.ui(1)),
            border_radius=self.ui(4),
        )
        self.draw_ui_text(
            self.screen,
            hotkey,
            self.tiny_font,
            (245, 238, 218),
            key_rect.inflate(-self.ui(2), 0),
            align="center",
            valign="center",
        )

        if "count" in slot:
            count_text = str(slot.get("count", 0))
            count_size = max(
                self.ui(15), self.tiny_font.size(count_text)[0] + self.ui(6)
            )
            count_rect = pygame.Rect(0, 0, count_size, self.ui(15))
            count_rect.bottomright = (rect.right - self.ui(3), rect.bottom - self.ui(3))
            pygame.draw.rect(
                self.screen, (8, 8, 12), count_rect, border_radius=self.ui(7)
            )
            pygame.draw.rect(
                self.screen,
                color,
                count_rect,
                max(1, self.ui(1)),
                border_radius=self.ui(7),
            )
            self.draw_ui_text(
                self.screen,
                count_text,
                self.tiny_font,
                (245, 238, 218),
                count_rect.inflate(-self.ui(2), 0),
                align="center",
                valign="center",
            )

        if remaining > 0.001:
            overlay_h = max(1, int(rect.height * remaining))
            overlay = pygame.Surface((rect.width, overlay_h), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 142))
            self.screen.blit(overlay, (rect.x, rect.y))
            progress = 1.0 - remaining
            pygame.draw.arc(
                self.screen,
                color,
                rect.inflate(-self.ui(4), -self.ui(4)),
                -math.pi / 2,
                -math.pi / 2 + math.tau * progress,
                max(2, self.ui(2)),
            )
        elif not ready:
            overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 90))
            self.screen.blit(overlay, rect)

        if status != "READY" and not ("count" in slot and status.startswith("x")):
            status_rect = pygame.Rect(
                rect.x + self.ui(4),
                rect.centery - self.tiny_font.get_height() // 2,
                rect.width - self.ui(8),
                self.tiny_font.get_height(),
            )
            text_color = (250, 230, 170) if timer > 0.001 else (218, 204, 176)
            self.draw_ui_text(
                self.screen,
                status,
                self.tiny_font,
                text_color,
                status_rect,
                align="center",
                valign="center",
            )

    def draw_hud_action_glyph(
        self, icon: str, rect: pygame.Rect, color: Color, ready: bool
    ) -> None:
        color = color if ready else self.shade(color, -48)
        cx, cy = rect.center
        line_w = max(2, self.ui(2))
        if icon == "melee":
            pygame.draw.line(
                self.screen,
                (24, 22, 28),
                (rect.left, rect.bottom),
                (rect.right, rect.top),
                line_w + max(1, self.ui(1)),
            )
            pygame.draw.line(
                self.screen,
                color,
                (rect.left, rect.bottom),
                (rect.right, rect.top),
                line_w,
            )
            pygame.draw.line(
                self.screen,
                self.shade(color, 34),
                (cx - rect.width // 5, cy + rect.height // 5),
                (cx + rect.width // 5, cy + rect.height // 5),
                line_w,
            )
        elif icon == "bolt":
            points = [
                (cx - rect.width // 5, rect.top),
                (cx + rect.width // 8, cy - rect.height // 8),
                (cx - rect.width // 10, cy),
                (cx + rect.width // 5, rect.bottom),
            ]
            pygame.draw.lines(self.screen, (24, 22, 28), False, points, line_w + 2)
            pygame.draw.lines(self.screen, color, False, points, line_w)
        elif icon == "nova":
            radius = max(5, min(rect.width, rect.height) // 3)
            pygame.draw.circle(self.screen, color, (cx, cy), radius, line_w)
            for angle in (0.0, math.pi / 2, math.pi, math.pi * 1.5):
                pygame.draw.line(
                    self.screen,
                    self.shade(color, 24),
                    (
                        cx + int(math.cos(angle) * radius * 0.45),
                        cy + int(math.sin(angle) * radius * 0.45),
                    ),
                    (
                        cx + int(math.cos(angle) * radius * 1.55),
                        cy + int(math.sin(angle) * radius * 1.55),
                    ),
                    max(1, self.ui(1)),
                )
        elif icon == "dash":
            for offset in (-rect.width // 7, rect.width // 7):
                points = [
                    (cx + offset - rect.width // 6, rect.top + rect.height // 5),
                    (cx + offset + rect.width // 7, cy),
                    (cx + offset - rect.width // 6, rect.bottom - rect.height // 5),
                ]
                pygame.draw.lines(self.screen, color, False, points, line_w)
        else:
            bottle = pygame.Rect(
                0, 0, max(8, rect.width // 2), max(12, rect.height * 2 // 3)
            )
            bottle.center = (cx, cy + rect.height // 10)
            neck = pygame.Rect(
                0, 0, max(4, bottle.width // 2), max(4, bottle.height // 4)
            )
            neck.midbottom = (bottle.centerx, bottle.y + self.ui(3))
            liquid = self.shade(color, 18 if icon == "mana_potion" else 8)
            pygame.draw.rect(self.screen, (28, 26, 32), neck, border_radius=self.ui(2))
            pygame.draw.rect(
                self.screen, (28, 26, 32), bottle, border_radius=self.ui(5)
            )
            fill = bottle.inflate(-self.ui(3), -self.ui(3))
            fill.y += fill.height // 3
            fill.height = max(2, fill.height * 2 // 3)
            pygame.draw.rect(self.screen, liquid, fill, border_radius=self.ui(4))
            pygame.draw.rect(
                self.screen,
                self.shade(color, 52),
                bottle,
                max(1, self.ui(1)),
                border_radius=self.ui(5),
            )

    def draw_player(self, player: Player) -> None:
        sway, bob, lean, stretch = self.actor_animation(player)
        state = self.player_visual_state(player)
        sprite = self.sprites.player_frame(
            player.class_name, state, player.anim_time, self.elapsed
        )
        self.draw_shadow(player.x, player.y, 34, 13, moving=player.moving, lift=bob)
        self.draw_movement_trail(player, (145, 130, 98), size=2)
        sx, sy = self.blit_sprite(
            sprite,
            player.x,
            player.y,
            y_offset=6.0 - bob,
            facing_x=player.facing_x,
            x_offset=sway,
            stretch=stretch,
            lean=lean * 0.12,
        )
        self.draw_hit_flash_overlay(
            sx,
            sy,
            sprite.get_width(),
            sprite.get_height(),
            getattr(self, "player_hit_flash", 0.0),
            (255, 110, 90),
        )

    def draw_aim_cone(self) -> None:
        sx, sy = self.world_to_screen(self.player.x, self.player.y)
        vx, vy = self.iso_screen_direction(self.player.facing_x, self.player.facing_y)
        px, py = -vy, vx
        origin = (
            sx + vx * 14 * WORLD_SCALE,
            sy - 8 * WORLD_SCALE + vy * 6 * WORLD_SCALE,
        )
        aim_blue = self.mix((92, 170, 255), self.theme.accent, 0.18)

        def arc_points(
            length: float, half_angle: float, samples: int = 24
        ) -> list[tuple[float, float]]:
            radius = length * WORLD_SCALE
            points: list[tuple[float, float]] = []
            for index in range(samples + 1):
                angle = half_angle - (half_angle * 2.0 * index / samples)
                forward = math.cos(angle)
                side = math.sin(angle)
                points.append(
                    (
                        origin[0] + (vx * forward + px * side) * radius,
                        origin[1] + (vy * forward + py * side) * radius,
                    )
                )
            return points

        def cone_points(
            length: float, half_angle: float, samples: int = 24
        ) -> list[tuple[float, float]]:
            return [origin] + arc_points(length, half_angle, samples)

        bounds_points = cone_points(122.0, 0.42, 28)
        pad = 18 * WORLD_SCALE
        min_x = math.floor(min(point[0] for point in bounds_points) - pad)
        max_x = math.ceil(max(point[0] for point in bounds_points) + pad)
        min_y = math.floor(min(point[1] for point in bounds_points) - pad)
        max_y = math.ceil(max(point[1] for point in bounds_points) + pad)
        width = max(1, max_x - min_x)
        height = max(1, max_y - min_y)
        supersample = 3
        overlay = pygame.Surface(
            (width * supersample, height * supersample), pygame.SRCALPHA
        )

        def localize(points: list[tuple[float, float]]) -> list[tuple[int, int]]:
            return [
                (
                    int(round((x - min_x) * supersample)),
                    int(round((y - min_y) * supersample)),
                )
                for x, y in points
            ]

        # Layer several translucent curved sectors instead of one hard polygon; the
        # supersampled draw keeps the rim and diagonal edges smooth at low UI scales.
        for length, angle, alpha in (
            (121.0, 0.42, 18),
            (110.0, 0.36, 32),
            (88.0, 0.25, 24),
        ):
            pygame.draw.polygon(
                overlay,
                (*aim_blue, alpha),
                localize(cone_points(length, angle, 30)),
            )

        overlay = pygame.transform.smoothscale(overlay, (width, height))
        self.screen.blit(overlay, (min_x, min_y))

    def draw_enemy(self, enemy: Enemy) -> None:
        base_name = self.sprites.enemy_key(enemy.name, enemy.kind)
        state = self.enemy_visual_state(enemy)
        sprite = self.sprites.enemy_frame(
            enemy.name, enemy.kind, state, enemy.anim_time, self.elapsed
        )
        shadow_w = (
            44 if enemy.kind == "boss" else 38 if base_name == "Gate Warden" else 32
        )
        sway, bob, lean, stretch = self.actor_animation(enemy)
        if enemy.kind == "boss":
            stretch += math.sin(self.elapsed * 3.4) * 0.010
            lean += math.sin(self.elapsed * 2.1) * 0.25
        elif enemy.elite_modifier or enemy.kind == "miniboss":
            stretch += math.sin(self.elapsed * 5.0) * 0.006
        self.draw_shadow(enemy.x, enemy.y, shadow_w, 12, moving=enemy.moving, lift=bob)
        trail_color = self.mix(enemy.color, (120, 84, 68), 0.45)
        self.draw_movement_trail(enemy, trail_color, size=2)

        sx, sy = self.blit_sprite(
            sprite,
            enemy.x,
            enemy.y,
            y_offset=6.0 - bob,
            facing_x=enemy.facing_x,
            x_offset=sway,
            stretch=stretch,
            lean=lean * 0.12,
        )
        self.draw_hit_flash_overlay(
            sx,
            sy,
            sprite.get_width(),
            sprite.get_height(),
            getattr(self, "enemy_hit_flashes", {}).get(id(enemy), 0.0),
            enemy.color,
        )
        bar_w = (
            46 if enemy.kind == "boss" else 34 if base_name == "Gate Warden" else 28
        ) * WORLD_SCALE
        fill_w = int(bar_w * max(0, enemy.hp) / enemy.max_hp)
        bar_h = 4 * WORLD_SCALE
        bar_y = sy - sprite.get_height() - 2 * WORLD_SCALE
        pygame.draw.rect(
            self.screen, (40, 10, 10), (sx - bar_w // 2, bar_y, bar_w, bar_h)
        )
        pygame.draw.rect(
            self.screen, (215, 62, 52), (sx - bar_w // 2, bar_y, fill_w, bar_h)
        )
        status_entries = [
            status
            for status, ttl in getattr(enemy, "statuses", {}).items()
            if ttl > 0 and not status.startswith("_")
        ]
        if status_entries:
            status_colors = {
                "poisoned": (126, 214, 92),
                "burning": (255, 132, 74),
                "chilled": (126, 206, 242),
                "snared": (150, 215, 105),
                "bound": (214, 92, 150),
                "stunned": (235, 205, 120),
            }
            pip_y = bar_y - 5 * WORLD_SCALE
            pip_spacing = 7 * WORLD_SCALE
            start_x = sx - ((len(status_entries) - 1) * pip_spacing) // 2
            for index, status in enumerate(status_entries[:5]):
                color = status_colors.get(status, enemy.color)
                pygame.draw.circle(
                    self.screen,
                    color,
                    (start_x + index * pip_spacing, pip_y),
                    max(2, 3 * WORLD_SCALE),
                )
        if enemy.elite_modifier or enemy.kind == "miniboss":
            pulse = 0.5 + 0.5 * math.sin(self.elapsed * 5.2)
            marker = pygame.Surface(
                (46 * WORLD_SCALE, 20 * WORLD_SCALE), pygame.SRCALPHA
            )
            pygame.draw.ellipse(
                marker,
                (*enemy.color, int(28 + pulse * 48)),
                marker.get_rect(),
                max(1, WORLD_SCALE),
            )
            pygame.draw.ellipse(
                marker,
                (*self.shade(enemy.color, 45), int(16 + pulse * 30)),
                marker.get_rect().inflate(
                    -marker.get_width() // 3, -marker.get_height() // 3
                ),
            )
            self.screen.blit(
                marker, marker.get_rect(center=(sx, sy - 14 * WORLD_SCALE))
            )
            label = self.small_font.render(enemy.elite_modifier, True, enemy.color)
            self.screen.blit(
                label, label.get_rect(center=(sx, bar_y - 8 * WORLD_SCALE))
            )
        if enemy.attack_timer <= 0.28 and enemy.kind in ("boss", "miniboss", "ranged"):
            tell_color = (
                self.theme.accent
                if enemy.kind == "boss"
                else self.damage_type_color(getattr(enemy, "damage_type", "physical"))
            )
            pulse = 0.55 + 0.45 * math.sin(self.elapsed * 18.0)
            telegraph = pygame.Surface(
                (42 * WORLD_SCALE, 42 * WORLD_SCALE), pygame.SRCALPHA
            )
            pygame.draw.circle(
                telegraph,
                (*tell_color, int(82 + 92 * pulse)),
                telegraph.get_rect().center,
                max(3, int(5 * WORLD_SCALE + pulse * 3 * WORLD_SCALE)),
                max(1, WORLD_SCALE),
            )
            self.screen.blit(
                telegraph, telegraph.get_rect(center=(sx, sy - 18 * WORLD_SCALE))
            )
            label = self.small_font.render("!", True, tell_color)
            self.screen.blit(label, label.get_rect(center=(sx, sy - 35 * WORLD_SCALE)))
        if state == "cast":
            cast_color = (
                self.theme.accent if enemy.kind in ("boss", "miniboss") else enemy.color
            )
            pygame.draw.circle(
                self.screen,
                (*cast_color, 112),
                (sx, sy - 24 * WORLD_SCALE),
                max(3, 4 * WORLD_SCALE),
                max(1, WORLD_SCALE),
            )
        if enemy.kind == "boss":
            pulse = 0.5 + 0.5 * math.sin(self.elapsed * 4.2)
            aura = pygame.Surface((74 * WORLD_SCALE, 30 * WORLD_SCALE), pygame.SRCALPHA)
            pygame.draw.ellipse(
                aura,
                (*self.theme.accent, int(30 + pulse * 42)),
                aura.get_rect(),
                max(1, WORLD_SCALE),
            )
            pygame.draw.ellipse(
                aura,
                (*self.shade(self.theme.accent, 55), int(15 + pulse * 22)),
                aura.get_rect().inflate(
                    -aura.get_width() // 3, -aura.get_height() // 3
                ),
            )
            self.screen.blit(aura, aura.get_rect(center=(sx, sy - 18 * WORLD_SCALE)))

    def draw_item(self, item: Item) -> None:
        if item.slot == "story_relic":
            self.draw_story_relic(item)
            return
        sx, sy = self.world_to_screen(item.x, item.y)
        rarity_color = self.rarity_color(item.visible_rarity)
        rarity_icon = self.rarity_icon(item.visible_rarity)
        sprite = self.sprites.item_frame(
            item.slot, self.elapsed + item.x * 0.31 + item.y * 0.17, item.visible_rarity
        )
        pulse = 0.65 + 0.35 * math.sin(self.elapsed * 4.0 + item.x + item.y)
        rare_scale = 1.25 if item.visible_rarity in ("Rare", "Unique") else 1.0
        glow = pygame.Surface(
            (int(42 * rare_scale) * WORLD_SCALE, int(20 * rare_scale) * WORLD_SCALE),
            pygame.SRCALPHA,
        )
        pygame.draw.ellipse(
            glow, (*rarity_color, int(55 + 45 * pulse)), glow.get_rect()
        )
        pygame.draw.ellipse(
            glow,
            (*self.shade(rarity_color, 45), int(22 + 30 * pulse)),
            glow.get_rect().inflate(-glow.get_width() // 3, -glow.get_height() // 3),
        )
        self.screen.blit(glow, glow.get_rect(center=(sx, sy + WORLD_SCALE)))
        bob = int(math.sin(self.elapsed * 3.2 + item.x * 0.7) * 2 * WORLD_SCALE)
        if item.visible_rarity in ("Magic", "Rare", "Unique", "Unidentified"):
            for index in range(3 if item.visible_rarity == "Unique" else 2):
                angle = (
                    self.elapsed * (2.4 + index * 0.7) + item.x + index * math.tau / 3
                )
                sparkle_x = sx + int(math.cos(angle) * (11 + index * 4) * WORLD_SCALE)
                sparkle_y = (
                    sy - int((8 + math.sin(angle * 1.7) * 5) * WORLD_SCALE) - bob
                )
                sparkle_alpha = int(95 + 95 * (0.5 + 0.5 * math.sin(angle * 2.0)))
                pygame.draw.line(
                    self.screen,
                    (*rarity_color, sparkle_alpha),
                    (sparkle_x - 2 * WORLD_SCALE, sparkle_y),
                    (sparkle_x + 2 * WORLD_SCALE, sparkle_y),
                    max(1, WORLD_SCALE),
                )
                pygame.draw.line(
                    self.screen,
                    (*rarity_color, sparkle_alpha),
                    (sparkle_x, sparkle_y - 2 * WORLD_SCALE),
                    (sparkle_x, sparkle_y + 2 * WORLD_SCALE),
                    max(1, WORLD_SCALE),
                )
        item_sprite = sprite
        tilt = math.sin(self.elapsed * 2.8 + item.y) * 3.0
        if item.visible_rarity in ("Rare", "Unique"):
            item_sprite = pygame.transform.rotate(sprite, tilt)
        rect = item_sprite.get_rect(midbottom=(sx, sy + 4 * WORLD_SCALE - bob))
        self.screen.blit(item_sprite, rect)
        if math.hypot(item.x - self.player.x, item.y - self.player.y) < 1.0:
            label = self.small_font.render(
                f"E {rarity_icon} {item.display_name}", True, rarity_color
            )
            self.screen.blit(
                label, label.get_rect(center=(sx, rect.top - 10 * WORLD_SCALE))
            )

    def draw_story_relic_guidance(self) -> None:
        target = self.story_relic_target_position()
        if (
            target is None
            or self.story_intro_pending
            or not self.story_relic_guidance_enabled
        ):
            return
        tx, ty = target
        route = self.story_relic_guidance_route(target)
        route_distance = self.route_distance(route)
        if route_distance < 0.8:
            return
        accent = self.story_state.accent if self.story_state else self.theme.accent
        light = self.mix(accent, (255, 232, 142), 0.72)
        core = self.mix(light, (255, 255, 238), 0.55)
        cue_count = min(7, max(3, int(route_distance // 2.1) + 1))
        samples = self.sample_guidance_route(route, cue_count)
        screen_w, screen_h = self.screen.get_size()
        glow_layer = pygame.Surface((screen_w, screen_h), pygame.SRCALPHA)
        screen_points = [
            (sx, sy - int(9 * WORLD_SCALE))
            for sx, sy in (self.world_to_screen(wx, wy) for wx, wy in samples)
        ]
        points: list[tuple[int, int, float, float]] = []
        for index, (sx, sy) in enumerate(screen_points):
            prev_x, prev_y = screen_points[max(0, index - 1)]
            next_x, next_y = screen_points[min(len(screen_points) - 1, index + 1)]
            tangent_x = next_x - prev_x
            tangent_y = next_y - prev_y
            tangent_len = math.hypot(tangent_x, tangent_y)
            if tangent_len <= 0.001:
                tangent_x, tangent_y, tangent_len = 1.0, 0.0, 1.0
            points.append((sx, sy, tangent_x / tangent_len, tangent_y / tangent_len))

        if len(points) >= 2:
            beam_points = [(sx, sy) for sx, sy, _dir_x, _dir_y in points]
            for width, alpha in (
                (12 * WORLD_SCALE, 10),
                (7 * WORLD_SCALE, 18),
                (3 * WORLD_SCALE, 34),
            ):
                pygame.draw.lines(
                    glow_layer,
                    (*light, alpha),
                    False,
                    beam_points,
                    max(1, width),
                )
            pygame.draw.lines(
                glow_layer,
                (*core, 48),
                False,
                beam_points,
                max(1, 2 * WORLD_SCALE),
            )

        for index, (sx, sy, dir_x, dir_y) in enumerate(points):
            shimmer = math.sin(self.elapsed * 5.2 + index * 1.15)
            drift = math.sin(self.elapsed * 2.4 + index) * 1.25 * WORLD_SCALE
            perp_x, perp_y = -dir_y, dir_x
            glint_x = sx + int(perp_x * drift)
            glint_y = sy + int(perp_y * drift)
            flame_tip = (
                glint_x + int(dir_x * 10 * WORLD_SCALE),
                glint_y + int(dir_y * 10 * WORLD_SCALE),
            )
            flame_left = (
                glint_x - int(dir_x * 2 * WORLD_SCALE) + int(perp_x * 3 * WORLD_SCALE),
                glint_y - int(dir_y * 2 * WORLD_SCALE) + int(perp_y * 3 * WORLD_SCALE),
            )
            flame_right = (
                glint_x - int(dir_x * 2 * WORLD_SCALE) - int(perp_x * 3 * WORLD_SCALE),
                glint_y - int(dir_y * 2 * WORLD_SCALE) - int(perp_y * 3 * WORLD_SCALE),
            )
            pygame.draw.polygon(
                glow_layer,
                (*self.mix(light, accent, 0.35), int(38 + shimmer * 14)),
                [flame_tip, flame_left, flame_right],
            )

        target_sx, target_sy = self.world_to_screen(tx, ty)
        target_center = (target_sx, target_sy - int(12 * WORLD_SCALE))
        relic_pulse = 0.5 + 0.5 * math.sin(self.elapsed * 4.0)
        pygame.draw.circle(
            glow_layer,
            (*light, int(24 + relic_pulse * 20)),
            target_center,
            int((20 + relic_pulse * 5) * WORLD_SCALE),
        )
        pygame.draw.circle(
            glow_layer,
            (*core, int(54 + relic_pulse * 46)),
            target_center,
            int((7 + relic_pulse * 3) * WORLD_SCALE),
        )
        self.screen.blit(glow_layer, (0, 0))

    def story_relic_guidance_route(
        self, target: tuple[float, float]
    ) -> list[tuple[float, float]]:
        start = (int(self.player.x), int(self.player.y))
        goal = (int(target[0]), int(target[1]))

        def walkable(tile: tuple[int, int]) -> bool:
            x, y = tile
            return (
                self.dungeon.in_bounds(x, y) and self.dungeon.tiles[x][y] != Tile.WALL
            )

        if not walkable(start) or not walkable(goal):
            return []
        if start == goal:
            return [(self.player.x, self.player.y), target]

        frontier: deque[tuple[int, int]] = deque([start])
        came_from: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
        while frontier:
            current = frontier.popleft()
            if current == goal:
                break
            neighbors = [
                (current[0] + 1, current[1]),
                (current[0] - 1, current[1]),
                (current[0], current[1] + 1),
                (current[0], current[1] - 1),
            ]
            neighbors.sort(
                key=lambda tile: abs(tile[0] - goal[0]) + abs(tile[1] - goal[1])
            )
            for neighbor in neighbors:
                if neighbor in came_from or not walkable(neighbor):
                    continue
                came_from[neighbor] = current
                frontier.append(neighbor)

        if goal not in came_from:
            return []

        tile_path: list[tuple[int, int]] = []
        current: tuple[int, int] | None = goal
        while current is not None:
            tile_path.append(current)
            current = came_from[current]
        tile_path.reverse()

        route: list[tuple[float, float]] = [(self.player.x, self.player.y)]
        route.extend((x + 0.5, y + 0.5) for x, y in tile_path[1:-1])
        route.append(target)
        return route

    def route_distance(self, route: list[tuple[float, float]]) -> float:
        return sum(
            math.hypot(bx - ax, by - ay) for (ax, ay), (bx, by) in zip(route, route[1:])
        )

    def sample_guidance_route(
        self, route: list[tuple[float, float]], sample_count: int
    ) -> list[tuple[float, float]]:
        total = self.route_distance(route)
        if total <= 0.001 or len(route) < 2:
            return route
        start_distance = min(1.05, total * 0.35)
        end_distance = max(start_distance, total - 0.45)
        if sample_count <= 1 or end_distance <= start_distance:
            distances = [end_distance]
        else:
            step = (end_distance - start_distance) / (sample_count - 1)
            distances = [start_distance + index * step for index in range(sample_count)]

        samples: list[tuple[float, float]] = []
        segment_start_distance = 0.0
        segment_index = 0
        for distance in distances:
            while segment_index < len(route) - 2:
                ax, ay = route[segment_index]
                bx, by = route[segment_index + 1]
                segment_length = math.hypot(bx - ax, by - ay)
                if segment_start_distance + segment_length >= distance:
                    break
                segment_start_distance += segment_length
                segment_index += 1
            ax, ay = route[segment_index]
            bx, by = route[segment_index + 1]
            segment_length = max(0.001, math.hypot(bx - ax, by - ay))
            ratio = max(
                0.0,
                min(1.0, (distance - segment_start_distance) / segment_length),
            )
            samples.append((ax + (bx - ax) * ratio, ay + (by - ay) * ratio))
        return samples

    def draw_story_relic(self, item: Item) -> None:
        sx, sy = self.world_to_screen(item.x, item.y)
        accent = self.story_state.accent if self.story_state else self.theme.accent
        pulse = 0.5 + 0.5 * math.sin(self.elapsed * 5.2 + item.x)
        glow = pygame.Surface((58 * WORLD_SCALE, 34 * WORLD_SCALE), pygame.SRCALPHA)
        pygame.draw.ellipse(glow, (*accent, int(54 + pulse * 70)), glow.get_rect())
        pygame.draw.ellipse(
            glow,
            (*self.shade(accent, 50), int(28 + pulse * 44)),
            glow.get_rect().inflate(-glow.get_width() // 3, -glow.get_height() // 3),
        )
        self.screen.blit(glow, glow.get_rect(center=(sx, sy)))
        bob = int(math.sin(self.elapsed * 3.5 + item.y) * 3 * WORLD_SCALE)
        points = [
            (sx, sy - 21 * WORLD_SCALE + bob),
            (sx + 12 * WORLD_SCALE, sy - 5 * WORLD_SCALE + bob),
            (sx, sy + 9 * WORLD_SCALE + bob),
            (sx - 12 * WORLD_SCALE, sy - 5 * WORLD_SCALE + bob),
        ]
        pygame.draw.polygon(self.screen, self.shade(accent, -45), points)
        pygame.draw.polygon(
            self.screen, self.shade(accent, 42), points, max(1, WORLD_SCALE)
        )
        pygame.draw.circle(
            self.screen,
            (245, 238, 210),
            (sx, sy - 5 * WORLD_SCALE + bob),
            max(2, 3 * WORLD_SCALE),
        )
        for index in range(4):
            angle = self.elapsed * 2.2 + index * math.tau / 4
            mote = (
                sx + int(math.cos(angle) * 20 * WORLD_SCALE),
                sy - int((10 + math.sin(angle) * 8) * WORLD_SCALE) + bob,
            )
            pygame.draw.circle(
                self.screen, self.shade(accent, 55), mote, max(1, WORLD_SCALE)
            )
        if math.hypot(item.x - self.player.x, item.y - self.player.y) < 1.0:
            label = self.small_font.render(f"E: {item.display_name}", True, accent)
            self.screen.blit(label, label.get_rect(center=(sx, sy - 36 * WORLD_SCALE)))

    def draw_trap(self, trap: Trap) -> None:
        if not trap.active:
            return
        sx, sy = self.world_to_screen(trap.x, trap.y)
        color = {
            "Spike Trap": (205, 75, 58),
            "Rune Trap": (160, 86, 230),
            "Poison Needle": (110, 185, 95),
        }.get(trap.kind, (205, 75, 58))
        pulse = 0.5 + 0.5 * math.sin(self.elapsed * 5.4 + trap.x)
        wobble = math.sin(self.elapsed * 3.7 + trap.y) * 2 * WORLD_SCALE
        points = [
            (sx, sy - int((10 + pulse * 2) * WORLD_SCALE)),
            (sx + 16 * WORLD_SCALE + int(wobble), sy),
            (sx, sy + int((10 + pulse * 2) * WORLD_SCALE)),
            (sx - 16 * WORLD_SCALE + int(wobble), sy),
        ]
        warning = pygame.Surface((42 * WORLD_SCALE, 22 * WORLD_SCALE), pygame.SRCALPHA)
        pygame.draw.ellipse(warning, (*color, int(22 + pulse * 28)), warning.get_rect())
        self.screen.blit(warning, warning.get_rect(center=(sx, sy + WORLD_SCALE)))
        pygame.draw.lines(self.screen, color, True, points, max(1, WORLD_SCALE))
        pygame.draw.lines(
            self.screen, self.shade(color, 45), True, points, max(1, WORLD_SCALE)
        )
        pygame.draw.circle(self.screen, color, (sx, sy), max(2, 2 * WORLD_SCALE))
        pygame.draw.circle(
            self.screen, self.shade(color, 45), (sx, sy), max(1, WORLD_SCALE)
        )
        sprite = self.sprites.trap_frame(trap.kind, self.elapsed + trap.x * 0.5)
        self.screen.blit(sprite, sprite.get_rect(center=(sx, sy - 2 * WORLD_SCALE)))
        if math.hypot(trap.x - self.player.x, trap.y - self.player.y) < 1.35:
            label = self.small_font.render(f"! {trap.kind}", True, color)
            self.screen.blit(label, label.get_rect(center=(sx, sy - 24 * WORLD_SCALE)))

    def draw_secret(self, secret: SecretCache) -> None:
        sx, sy = self.world_to_screen(secret.x, secret.y)
        color = self.theme.accent
        pulse = 0.55 + 0.45 * math.sin(self.elapsed * 5.0 + secret.x)
        glow = pygame.Surface((34 * WORLD_SCALE, 18 * WORLD_SCALE), pygame.SRCALPHA)
        pygame.draw.ellipse(glow, (*color, int(34 + 46 * pulse)), glow.get_rect())
        self.screen.blit(glow, glow.get_rect(center=(sx, sy + 2 * WORLD_SCALE)))
        pygame.draw.rect(
            self.screen,
            (35, 28, 24),
            (
                sx - 8 * WORLD_SCALE,
                sy - 8 * WORLD_SCALE,
                16 * WORLD_SCALE,
                10 * WORLD_SCALE,
            ),
        )
        pygame.draw.rect(
            self.screen,
            color,
            (
                sx - 8 * WORLD_SCALE,
                sy - 8 * WORLD_SCALE,
                16 * WORLD_SCALE,
                10 * WORLD_SCALE,
            ),
            max(1, WORLD_SCALE),
        )
        sprite = self.sprites.secret_frame(self.elapsed + secret.x * 0.33)
        self.screen.blit(sprite, sprite.get_rect(midbottom=(sx, sy + 4 * WORLD_SCALE)))
        if math.hypot(secret.x - self.player.x, secret.y - self.player.y) < 1.1:
            hint = self.current_interaction_hint()
            detail = hint[2] if hint else "Open secret"
            label = self.small_font.render(f"E: {secret.kind}", True, color)
            sublabel = self.small_font.render(detail, True, (205, 200, 185))
            self.screen.blit(label, label.get_rect(center=(sx, sy - 31 * WORLD_SCALE)))
            self.screen.blit(
                sublabel, sublabel.get_rect(center=(sx, sy - 18 * WORLD_SCALE))
            )

    def draw_story_guest(self, guest: StoryGuest) -> None:
        sx, sy = self.world_to_screen(guest.x, guest.y)
        color = guest.color if not guest.resolved else self.shade(guest.color, -60)
        self.draw_shadow(guest.x, guest.y, 26, 11)
        pulse = 0.55 + 0.45 * math.sin(self.elapsed * 4.0 + guest.depth)
        ring = pygame.Surface((48 * WORLD_SCALE, 25 * WORLD_SCALE), pygame.SRCALPHA)
        ring_alpha = int(
            (18 if guest.resolved else 34) + (18 if guest.resolved else 46) * pulse
        )
        pygame.draw.ellipse(
            ring, (*color, ring_alpha), ring.get_rect(), max(1, WORLD_SCALE)
        )
        if not guest.resolved:
            pygame.draw.ellipse(
                ring,
                (*self.shade(color, 55), int(14 + 30 * pulse)),
                ring.get_rect().inflate(
                    -ring.get_width() // 3, -ring.get_height() // 3
                ),
            )
        self.screen.blit(ring, ring.get_rect(center=(sx, sy + 4 * WORLD_SCALE)))

        sprite = self.sprites.story_guest_frame(
            self.elapsed + guest.depth, guest.resolved
        )
        sprite = sprite.copy()
        sprite.fill(
            (*color, 36 if not guest.resolved else 18),
            special_flags=pygame.BLEND_RGBA_ADD,
        )
        self.screen.blit(sprite, sprite.get_rect(midbottom=(sx, sy + 5 * WORLD_SCALE)))

        portrait_radius = 10 * WORLD_SCALE
        portrait_y = sy - 34 * WORLD_SCALE
        pygame.draw.circle(self.screen, (15, 12, 18), (sx, portrait_y), portrait_radius)
        pygame.draw.circle(
            self.screen, color, (sx, portrait_y), portrait_radius, max(1, WORLD_SCALE)
        )
        pygame.draw.circle(
            self.screen,
            (*self.shade(color, 45), int(35 + pulse * 50)),
            (sx, portrait_y),
            max(3, int(5 * WORLD_SCALE)),
        )
        marker = "✓" if guest.resolved else "?"
        role_glyph = (guest.role[:1] or "G").upper()
        glyph = marker if not guest.met or guest.resolved else role_glyph
        marker_surface = self.small_font.render(glyph, True, (245, 236, 205))
        self.screen.blit(
            marker_surface, marker_surface.get_rect(center=(sx, portrait_y))
        )
        if (
            not guest.resolved
            and math.hypot(guest.x - self.player.x, guest.y - self.player.y) < 1.25
        ):
            label = self.small_font.render(f"1-3: {guest.name}", True, color)
            sublabel = self.small_font.render(guest.role, True, (205, 200, 185))
            self.screen.blit(label, label.get_rect(center=(sx, sy - 55 * WORLD_SCALE)))
            self.screen.blit(
                sublabel, sublabel.get_rect(center=(sx, sy - 42 * WORLD_SCALE))
            )

    def draw_shrine(self, shrine: Shrine) -> None:
        sx, sy = self.world_to_screen(shrine.x, shrine.y)
        color = (92, 92, 100) if shrine.used else (235, 205, 110)
        pulse = 0.6 + 0.4 * math.sin(self.elapsed * 3.0 + shrine.x)
        glow = pygame.Surface((50 * WORLD_SCALE, 28 * WORLD_SCALE), pygame.SRCALPHA)
        pygame.draw.ellipse(glow, (*color, int(42 + 48 * pulse)), glow.get_rect())
        pygame.draw.ellipse(
            glow,
            (*self.shade(color, 38), int(20 + 32 * pulse)),
            glow.get_rect().inflate(-glow.get_width() // 3, -glow.get_height() // 3),
        )
        self.screen.blit(glow, glow.get_rect(center=(sx, sy)))
        if not shrine.used:
            for index in range(3):
                angle = self.elapsed * 1.8 + shrine.x + index * math.tau / 3
                mote_x = sx + int(math.cos(angle) * 17 * WORLD_SCALE)
                mote_y = sy - int((16 + math.sin(angle) * 6) * WORLD_SCALE)
                pygame.draw.circle(
                    self.screen,
                    self.shade(color, 35),
                    (mote_x, mote_y),
                    max(1, WORLD_SCALE),
                )
        pygame.draw.rect(
            self.screen,
            (48, 42, 50),
            (
                sx - 7 * WORLD_SCALE,
                sy - 24 * WORLD_SCALE,
                14 * WORLD_SCALE,
                25 * WORLD_SCALE,
            ),
        )
        pygame.draw.rect(
            self.screen,
            color,
            (
                sx - 4 * WORLD_SCALE,
                sy - 19 * WORLD_SCALE,
                8 * WORLD_SCALE,
                6 * WORLD_SCALE,
            ),
        )
        sprite = self.sprites.shrine_frame(
            shrine.kind, self.elapsed + shrine.x, shrine.used
        )
        self.screen.blit(sprite, sprite.get_rect(midbottom=(sx, sy + 2 * WORLD_SCALE)))
        if (
            not shrine.used
            and math.hypot(shrine.x - self.player.x, shrine.y - self.player.y) < 1.15
        ):
            hint = self.current_interaction_hint()
            detail = hint[2] if hint else "Use shrine"
            label = self.small_font.render(f"E: {shrine.kind}", True, color)
            sublabel = self.small_font.render(detail, True, (218, 210, 186))
            self.screen.blit(label, label.get_rect(center=(sx, sy - 44 * WORLD_SCALE)))
            self.screen.blit(
                sublabel, sublabel.get_rect(center=(sx, sy - 31 * WORLD_SCALE))
            )

    def draw_projectile(self, projectile: Projectile) -> None:
        sx, sy = self.world_to_screen(projectile.x, projectile.y)
        sprite = self.sprites.projectile_frame(
            projectile.owner, self.elapsed + projectile.x * 0.2 + projectile.y * 0.15
        )
        vx, vy = self.iso_screen_direction(projectile.vx, projectile.vy)
        color = projectile.color or (
            (70, 165, 255) if projectile.owner == "player" else (210, 83, 238)
        )
        px, py = -vy, vx
        flicker = 0.5 + 0.5 * math.sin(self.elapsed * 18.0 + projectile.x)
        for step, alpha in ((1, 136), (2, 92), (3, 54), (4, 26)):
            trail = pygame.Surface((10 * WORLD_SCALE, 5 * WORLD_SCALE), pygame.SRCALPHA)
            pygame.draw.ellipse(trail, (*color, alpha), trail.get_rect())
            side = math.sin(self.elapsed * 12.0 + step) * 2 * WORLD_SCALE
            self.screen.blit(
                trail,
                trail.get_rect(
                    center=(
                        sx - int(vx * step * 9 * WORLD_SCALE + px * side),
                        sy
                        - 12 * WORLD_SCALE
                        - int(vy * step * 9 * WORLD_SCALE + py * side),
                    )
                ),
            )
        pygame.draw.circle(
            self.screen,
            (*self.shade(color, 45), int(72 + flicker * 72)),
            (sx, sy - 12 * WORLD_SCALE),
            max(3, int((3 + flicker * 2) * WORLD_SCALE)),
        )
        angle = -math.degrees(math.atan2(vy, vx))
        sprite = pygame.transform.rotate(
            sprite, angle + math.sin(self.elapsed * 20.0) * 4
        )
        rect = sprite.get_rect(center=(sx, sy - 12 * WORLD_SCALE))
        self.screen.blit(sprite, rect)

    def draw_slash(self, slash: SlashEffect) -> None:
        x, y, ttl, dx, dy = slash
        sx, sy = self.world_to_screen(x, y)
        life = max(0.0, min(1.0, ttl / 0.18))
        sprite = self.sprites.slash.copy()
        if dx < 0:
            sprite = pygame.transform.flip(sprite, True, False)
        if life < 0.7:
            grow = 1.0 + (0.7 - life) * 0.25
            sprite = pygame.transform.scale(
                sprite,
                (int(sprite.get_width() * grow), int(sprite.get_height() * grow)),
            )
        sprite.set_alpha(max(0, min(255, int(255 * life))))
        vx, vy = self.iso_screen_direction(dx, dy)
        px, py = -vy, vx
        center = (
            sx + int(vx * (1.0 - life) * 12 * WORLD_SCALE),
            sy - 18 * WORLD_SCALE + int(vy * (1.0 - life) * 6 * WORLD_SCALE),
        )
        for index, alpha in enumerate((92, 54, 26)):
            arc_offset = (index + 1) * 7 * WORLD_SCALE
            pygame.draw.line(
                self.screen,
                (255, 235, 170, int(alpha * life)),
                (
                    center[0] - int(vx * arc_offset + px * 8 * WORLD_SCALE),
                    center[1] - int(vy * arc_offset + py * 4 * WORLD_SCALE),
                ),
                (
                    center[0] + int(vx * arc_offset + px * 8 * WORLD_SCALE),
                    center[1] + int(vy * arc_offset + py * 4 * WORLD_SCALE),
                ),
                max(1, WORLD_SCALE),
            )
        rect = sprite.get_rect(center=center)
        self.screen.blit(sprite, rect)
        spark_alpha = max(0, min(255, int(180 * life)))
        for side in (-1, 1):
            pygame.draw.line(
                self.screen,
                (255, 252, 210, spark_alpha),
                center,
                (
                    center[0]
                    + int((vx * 16 + px * side * 10) * WORLD_SCALE * (1.0 - life)),
                    center[1]
                    + int((vy * 8 + py * side * 6) * WORLD_SCALE * (1.0 - life)),
                ),
                max(1, WORLD_SCALE),
            )

    def ui(self, value: int) -> int:
        return value * self.ui_scale

    def hud_panel_height(self) -> int:
        _width, height = self.screen.get_size()
        desired = (
            self.font.get_height() + self.small_font.get_height() * 3 + self.ui(74)
        )
        minimum = min(self.ui(112), max(132, int(height * 0.30)))
        maximum = max(minimum, int(height * 0.38))
        return min(max(desired, minimum), maximum)

    def ellipsize_ui_text(
        self, text: str, font: pygame.font.Font, max_width: int
    ) -> str:
        max_width = max(1, max_width)
        if font.size(text)[0] <= max_width:
            return text
        suffix = "…"
        while text and font.size(text + suffix)[0] > max_width:
            text = text[:-1]
        return text + suffix if text else suffix

    def draw_ui_text(
        self,
        surface: pygame.Surface,
        text: str,
        font: pygame.font.Font,
        color: Color,
        rect: pygame.Rect,
        align: str = "left",
        valign: str = "top",
    ) -> None:
        rendered = font.render(
            self.ellipsize_ui_text(text, font, rect.width), True, color
        )
        if align == "center":
            x = rect.centerx - rendered.get_width() // 2
        elif align == "right":
            x = rect.right - rendered.get_width()
        else:
            x = rect.x
        if valign == "center":
            y = rect.centery - rendered.get_height() // 2
        elif valign == "bottom":
            y = rect.bottom - rendered.get_height()
        else:
            y = rect.y
        surface.blit(rendered, (x, y))

    def draw_translucent_panel(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        fill: tuple[int, int, int, int],
        border: tuple[int, int, int, int],
        radius: int | None = None,
        width: int | None = None,
    ) -> None:
        radius = self.ui(9) if radius is None else radius
        width = self.ui(1) if width is None else width
        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        panel_rect = panel.get_rect()
        pygame.draw.rect(panel, fill, panel_rect, border_radius=radius)
        pygame.draw.rect(panel, border, panel_rect, width, border_radius=radius)
        surface.blit(panel, rect)

    def wrap_ui_text(
        self, text: str, font: pygame.font.Font, max_width: int
    ) -> list[str]:
        lines: list[str] = []
        for paragraph in text.splitlines() or [""]:
            words = paragraph.split()
            if not words:
                lines.append("")
                continue
            current = self.ellipsize_ui_text(words[0], font, max_width)
            for word in words[1:]:
                candidate = f"{current} {word}"
                if font.size(candidate)[0] <= max_width:
                    current = candidate
                else:
                    lines.append(current)
                    current = self.ellipsize_ui_text(word, font, max_width)
            lines.append(current)
        return lines

    def draw_story_panel(self) -> None:
        if not getattr(self, "quest_info_visible", True):
            return
        lines = self.story_panel_lines()
        if not lines:
            return
        width, height = self.screen.get_size()
        bottom_panel_top = height - self.hud_panel_height()
        x = self.ui(18)
        y = self.ui(104)
        panel_w = min(width - self.ui(36), self.ui(620))
        max_h = min(self.ui(190), bottom_panel_top - y - self.ui(16))
        if panel_w <= self.ui(220) or max_h < self.ui(84):
            return
        accent = self.story_state.accent if self.story_state else self.theme.accent
        rect = pygame.Rect(x, y, panel_w, max_h)
        surface = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(
            surface, (10, 9, 13, 218), surface.get_rect(), border_radius=self.ui(9)
        )
        pygame.draw.rect(
            surface,
            (*accent, 155),
            surface.get_rect(),
            self.ui(1),
            border_radius=self.ui(9),
        )
        pad = self.ui(12)
        title = lines[0]
        title_surface = self.small_font.render(title, True, (244, 232, 214))
        surface.blit(title_surface, (pad, pad))
        pygame.draw.line(
            surface,
            (*accent, 120),
            (pad, pad + title_surface.get_height() + self.ui(4)),
            (panel_w - pad, pad + title_surface.get_height() + self.ui(4)),
            self.ui(1),
        )
        cursor_y = pad + title_surface.get_height() + self.ui(9)
        line_h = max(self.small_font.get_height() + self.ui(3), self.ui(18))
        max_lines = max(2, (max_h - cursor_y - pad) // line_h)
        rendered = 0
        for raw_line in lines[1:]:
            color = (
                (205, 185, 225)
                if raw_line.startswith("Story forces:")
                else (210, 205, 192)
            )
            if raw_line.startswith("Depth ") or raw_line.startswith("Outcome:"):
                color = (238, 218, 164)
            for wrapped in self.wrap_ui_text(
                raw_line, self.small_font, panel_w - pad * 2
            ):
                if rendered >= max_lines:
                    ellipsis = self.small_font.render("…", True, (170, 165, 155))
                    surface.blit(ellipsis, (pad, cursor_y))
                    self.screen.blit(surface, rect)
                    return
                text = self.small_font.render(wrapped, True, color)
                surface.blit(text, (pad, cursor_y))
                cursor_y += line_h
                rendered += 1
        self.screen.blit(surface, rect)

    def cutscene_response_text_width(self, choice_width: int) -> int:
        key_size = self.ui(36)
        return max(1, choice_width - self.ui(7) - key_size - self.ui(9) - self.ui(8))

    def cutscene_response_lines(
        self, label: str, detail: str, text_width: int
    ) -> tuple[list[str], list[str]]:
        label_lines = self.wrap_ui_text(label, self.small_font, text_width) or [""]
        detail_lines = (
            self.wrap_ui_text(detail, self.tiny_font, text_width) if detail else []
        )
        return label_lines, detail_lines

    def cutscene_response_height(
        self, label: str, detail: str, choice_width: int
    ) -> int:
        text_width = self.cutscene_response_text_width(choice_width)
        label_lines, detail_lines = self.cutscene_response_lines(
            label, detail, text_width
        )
        text_h = len(label_lines) * self.small_font.get_height()
        if detail_lines:
            text_h += self.ui(3) + len(detail_lines) * self.tiny_font.get_height()
        return max(self.ui(44), text_h + self.ui(16))

    def cutscene_response_rects(
        self,
        entries: list[tuple[str, str]],
        x: int,
        y: int,
        width: int,
        gap: int,
    ) -> list[pygame.Rect]:
        rects: list[pygame.Rect] = []
        cursor_y = y
        for label, detail in entries:
            rect_h = self.cutscene_response_height(label, detail, width)
            rects.append(pygame.Rect(x, cursor_y, width, rect_h))
            cursor_y += rect_h + gap
        return rects

    def draw_cutscene_response_text(
        self,
        surface: pygame.Surface,
        label: str,
        detail: str,
        text_rect: pygame.Rect,
    ) -> None:
        label_lines, detail_lines = self.cutscene_response_lines(
            label, detail, text_rect.width
        )
        cursor_y = text_rect.y
        for line in label_lines:
            self.draw_ui_text(
                surface,
                line,
                self.small_font,
                (246, 235, 210),
                pygame.Rect(
                    text_rect.x, cursor_y, text_rect.width, self.small_font.get_height()
                ),
            )
            cursor_y += self.small_font.get_height()
        if detail_lines:
            cursor_y += self.ui(3)
        for line in detail_lines:
            self.draw_ui_text(
                surface,
                line,
                self.tiny_font,
                (184, 178, 168),
                pygame.Rect(
                    text_rect.x, cursor_y, text_rect.width, self.tiny_font.get_height()
                ),
            )
            cursor_y += self.tiny_font.get_height()

    def draw_quest_cutscene_overlay(self) -> None:
        asset = self.active_cutscene_asset()
        node = self.active_cutscene_node()
        if asset is None or node is None:
            return
        width, height = self.screen.get_size()
        dim = pygame.Surface((width, height), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 255))
        self.screen.blit(dim, (0, 0))

        accent = self.story_state.accent if self.story_state else self.theme.accent
        panel_w = min(width - self.ui(28), self.ui(920))
        panel_h = min(height - self.ui(16), self.ui(620))
        if panel_w < 300 or panel_h < 260:
            return
        rect = pygame.Rect(
            (width - panel_w) // 2,
            max(self.ui(8), (height - panel_h) // 2),
            panel_w,
            panel_h,
        )
        surface = pygame.Surface(rect.size, pygame.SRCALPHA)
        self.draw_translucent_panel(
            surface,
            surface.get_rect(),
            (10, 8, 14, 248),
            (*accent, 222),
            radius=self.ui(14),
            width=self.ui(2),
        )
        pygame.draw.line(
            surface,
            (255, 245, 210, 28),
            (self.ui(24), self.ui(10)),
            (panel_w - self.ui(24), self.ui(10)),
            self.ui(1),
        )

        pad = max(self.ui(14), 18)
        title_text = asset.title
        if self.story_intro_pending:
            title_text = f"{asset.title} · Depth {self.current_depth}/{DUNGEON_DEPTH}"
        header_h = max(self.font.get_height(), self.small_font.get_height()) + self.ui(
            8
        )
        header_meta = node.id.replace("_", " ").title()
        meta_w = min(
            self.small_font.size(header_meta)[0] + self.ui(8),
            max(self.ui(96), (panel_w - pad * 2) // 3),
        )
        meta_x = panel_w - pad - meta_w
        title_rect = pygame.Rect(
            pad,
            pad,
            max(1, meta_x - pad - self.ui(10)),
            self.font.get_height(),
        )
        meta_rect = pygame.Rect(
            meta_x,
            pad + (self.font.get_height() - self.small_font.get_height()) // 2,
            meta_w,
            self.small_font.get_height(),
        )
        self.draw_ui_text(surface, title_text, self.font, accent, title_rect)
        self.draw_ui_text(
            surface,
            header_meta,
            self.small_font,
            (196, 188, 204),
            meta_rect,
            align="right",
        )

        narration_complete = self.active_cutscene_narration_complete()
        choices = self.active_cutscene_choices()
        choices_to_draw = choices[: min(9, len(choices))] if narration_complete else []
        choice_gap = max(self.ui(4), 6)
        choice_w = panel_w - pad * 2
        footer_h = self.small_font.get_height()
        choice_entries = [(choice.label, choice.detail) for choice in choices_to_draw]
        choice_heights = [
            self.cutscene_response_height(label, detail, choice_w)
            for label, detail in choice_entries
        ]
        choices_block_h = (
            sum(choice_heights) + max(0, len(choice_heights) - 1) * choice_gap
        )
        choices_start = panel_h - pad - footer_h - self.ui(10) - choices_block_h

        stage_top = pad + header_h + self.ui(12)
        available_for_stage = max(
            self.ui(54), choices_start - stage_top - self.small_font.get_height() * 3
        )
        stage_h = max(self.ui(74), min(int(panel_h * 0.38), available_for_stage))
        stage_rect = pygame.Rect(
            pad,
            stage_top,
            panel_w - pad * 2,
            stage_h,
        )
        self.draw_cutscene_stage(surface, stage_rect, node.animation, accent)

        y = stage_rect.bottom + self.ui(12)
        speaker = self.active_cutscene_speaker_name()
        speaker_rect = pygame.Rect(
            pad, y, panel_w - pad * 2, self.small_font.get_height()
        )
        self.draw_ui_text(
            surface, speaker, self.small_font, (246, 235, 210), speaker_rect
        )
        speaker_w = min(self.small_font.size(speaker)[0], speaker_rect.width)
        line_y = y + self.small_font.get_height() // 2
        pygame.draw.line(
            surface,
            (*accent, 130),
            (pad + speaker_w + self.ui(10), line_y),
            (panel_w - pad, line_y),
            self.ui(1),
        )
        y += self.small_font.get_height() + self.ui(5)
        progress = self.active_cutscene_narration_progress()
        progress_rect = pygame.Rect(pad, y, panel_w - pad * 2, max(self.ui(3), 3))
        pygame.draw.rect(
            surface, (33, 25, 43, 210), progress_rect, border_radius=self.ui(2)
        )
        pygame.draw.rect(
            surface,
            (*accent, 170),
            (
                progress_rect.x,
                progress_rect.y,
                int(progress_rect.width * progress),
                progress_rect.height,
            ),
            border_radius=self.ui(2),
        )
        y += progress_rect.height + self.ui(8)

        text_bottom = max(y + self.small_font.get_height(), choices_start - self.ui(10))
        line_h = max(self.small_font.get_height() + self.ui(3), self.ui(18))
        body_lines: list[str] = []
        visible_text = self.active_cutscene_visible_text()
        if not visible_text:
            visible_text = " "
        for paragraph in visible_text.splitlines() or [""]:
            body_lines.extend(
                self.wrap_ui_text(paragraph, self.small_font, panel_w - pad * 2)
            )
        if not narration_complete and body_lines and int(self.elapsed * 2.0) % 2 == 0:
            body_lines[-1] = f"{body_lines[-1]} |"
        max_body_lines = max(1, (text_bottom - y) // line_h)
        omitted_lines = max(0, len(body_lines) - max_body_lines)
        visible_lines = body_lines[-max_body_lines:]
        if omitted_lines and visible_lines:
            visible_lines[0] = "… " + visible_lines[0]
        for index, text_line in enumerate(visible_lines):
            color = (225, 218, 202)
            is_current_line = index == len(visible_lines) - 1 and not narration_complete
            if index == 0 and self.story_intro_pending and not omitted_lines:
                color = (238, 218, 164)
            elif is_current_line:
                color = self.mix((238, 218, 164), accent, 0.22)
            self.draw_ui_text(
                surface,
                text_line,
                self.small_font,
                color,
                pygame.Rect(pad, y, panel_w - pad * 2, line_h),
            )
            y += line_h

        choice_rects = self.cutscene_response_rects(
            choice_entries, pad, choices_start, choice_w, choice_gap
        )
        for index, (choice, choice_rect) in enumerate(
            zip(choices_to_draw, choice_rects)
        ):
            choice_color = self.cutscene_choice_color(choice.choice_key, accent)
            pygame.draw.rect(
                surface,
                (24, 19, 31, 240),
                choice_rect,
                border_radius=self.ui(9),
            )
            pygame.draw.rect(
                surface,
                (*choice_color, 170),
                choice_rect,
                self.ui(1),
                border_radius=self.ui(9),
            )
            key_size = min(self.ui(36), choice_rect.height - self.ui(12))
            key_rect = pygame.Rect(
                choice_rect.x + self.ui(7),
                choice_rect.y + (choice_rect.height - key_size) // 2,
                key_size,
                key_size,
            )
            pygame.draw.rect(
                surface,
                (*self.shade(choice_color, -58), 238),
                key_rect,
                border_radius=self.ui(7),
            )
            self.draw_cutscene_choice_glyph(
                surface,
                key_rect.center,
                choice.choice_key,
                max(self.ui(7), key_size // 3),
                alpha=96,
            )
            self.draw_ui_text(
                surface,
                str(index + 1),
                self.font,
                choice_color,
                key_rect,
                align="center",
                valign="center",
            )
            text_x = key_rect.right + self.ui(9)
            text_rect = pygame.Rect(
                text_x,
                choice_rect.y + self.ui(7),
                max(1, choice_rect.right - text_x - self.ui(8)),
                choice_rect.height - self.ui(14),
            )
            self.draw_cutscene_response_text(
                surface, choice.label, choice.detail, text_rect
            )

        footer_text = (
            "Narrator speaking… Press Enter/E/Space to reveal the full line."
            if not narration_complete
            else (
                "Press 1-3 to choose a dialogue response."
                if len(choices_to_draw) >= 3
                else "Press Enter/E to advance, Esc to close non-blocking dialogue."
            )
        )
        if self.story_intro_pending and narration_complete:
            footer_text = "Press 1-3 to confirm the guest dialog, place the relic, and begin this level."
        self.draw_ui_text(
            surface,
            footer_text,
            self.small_font,
            (205, 185, 225),
            pygame.Rect(pad, panel_h - pad - footer_h, panel_w - pad * 2, footer_h),
        )
        self.screen.blit(surface, rect)

    def draw_cutscene_stage(
        self,
        surface: pygame.Surface,
        stage_rect: pygame.Rect,
        animation_id: str,
        accent: Color,
    ) -> None:
        pygame.draw.rect(
            surface, (15, 13, 21, 245), stage_rect, border_radius=self.ui(10)
        )
        pygame.draw.rect(
            surface, (*accent, 125), stage_rect, self.ui(1), border_radius=self.ui(10)
        )
        self.draw_cutscene_story_backdrop(surface, stage_rect, accent)
        self.draw_cutscene_memory_ribbon(surface, stage_rect, accent)
        horizon_y = stage_rect.y + int(stage_rect.height * 0.62)
        pygame.draw.line(
            surface,
            (*self.shade(accent, -25), 76),
            (stage_rect.x + self.ui(10), horizon_y),
            (stage_rect.right - self.ui(10), horizon_y),
            self.ui(1),
        )
        self.draw_cutscene_choice_tableau(surface, stage_rect, accent)
        for index in range(9):
            phase = self.elapsed * (0.45 + index * 0.035) + index * 1.7
            mote_x = stage_rect.x + int(
                (0.08 + (index * 0.11) % 0.86) * stage_rect.width
            )
            mote_y = stage_rect.y + int(
                (0.22 + 0.18 * math.sin(phase)) * stage_rect.height
            )
            pygame.draw.circle(surface, (*accent, 54), (mote_x, mote_y), self.ui(1))
        asset = self.active_cutscene_asset()
        if asset is None:
            return
        for actor in asset.actors.values():
            self.draw_cutscene_actor(surface, stage_rect, actor, animation_id, accent)
        self.draw_cutscene_letterbox(surface, stage_rect)

    def draw_cutscene_letterbox(
        self, surface: pygame.Surface, stage_rect: pygame.Rect
    ) -> None:
        bar_h = max(2, self.ui(5))
        pygame.draw.rect(
            surface,
            (0, 0, 0, 74),
            (stage_rect.x, stage_rect.y, stage_rect.width, bar_h),
        )
        pygame.draw.rect(
            surface,
            (0, 0, 0, 74),
            (stage_rect.x, stage_rect.bottom - bar_h, stage_rect.width, bar_h),
        )

    def draw_cutscene_memory_ribbon(
        self, surface: pygame.Surface, stage_rect: pygame.Rect, accent: Color
    ) -> None:
        asset = self.active_cutscene_asset()
        if asset is None:
            return
        actor_order = ("player", "relic", "guest", "antagonist")
        points: list[tuple[int, int]] = []
        for actor_id in actor_order:
            actor = asset.actors.get(actor_id)
            if actor is None:
                continue
            points.append(
                (
                    stage_rect.x + int(actor.x * stage_rect.width),
                    stage_rect.y + int(actor.y * stage_rect.height),
                )
            )
        if len(points) < 2:
            return
        for start, end in zip(points, points[1:]):
            pygame.draw.line(surface, (*accent, 42), start, end, self.ui(1))
        progress = self.active_cutscene_narration_progress()
        scaled = progress * (len(points) - 1)
        segment_index = min(len(points) - 2, int(scaled))
        segment_t = scaled - segment_index
        start = points[segment_index]
        end = points[segment_index + 1]
        pulse = 0.5 + 0.5 * math.sin(self.elapsed * 5.0)
        marker = (
            int(start[0] + (end[0] - start[0]) * segment_t),
            int(start[1] + (end[1] - start[1]) * segment_t),
        )
        pygame.draw.circle(
            surface, (*self.shade(accent, 42), int(92 + pulse * 86)), marker, self.ui(4)
        )
        pygame.draw.circle(surface, (*accent, 76), marker, self.ui(10), self.ui(1))

    def draw_cutscene_story_backdrop(
        self, surface: pygame.Surface, stage_rect: pygame.Rect, accent: Color
    ) -> None:
        theme = self.theme
        base = self.shade(theme.floor, -42)
        far = self.mix(base, self.shade(accent, -65), 0.35)
        for band in range(6):
            amount = band / 5
            color = self.mix(far, self.shade(theme.wall_top, -18), amount * 0.45)
            y = stage_rect.y + int(stage_rect.height * band / 6)
            h = max(1, stage_rect.height // 6 + 1)
            pygame.draw.rect(
                surface,
                (*color, 52 + band * 16),
                (stage_rect.x + self.ui(2), y, stage_rect.width - self.ui(4), h),
            )
        text = self.cutscene_story_text().lower()
        current_sentence = self.active_cutscene_current_sentence_text().lower()
        scene_text = f"{text} {current_sentence}"
        self.draw_cutscene_theme_motifs(surface, stage_rect, accent, scene_text)
        self.draw_cutscene_relic_silhouette(surface, stage_rect, accent)
        self.draw_cutscene_faction_sigil(surface, stage_rect, accent)
        beat = self.current_story_beat()
        story = self.story_state
        tags = [beat.theme_name if beat else self.theme.name]
        if story is not None:
            tags.extend([story.relic_name, story.antagonist])
        tag_x = stage_rect.x + self.ui(8)
        tag_y = stage_rect.y + self.ui(5)
        for tag in tags[:3]:
            rendered = self.small_font.render(tag[:32], True, (205, 198, 188))
            rendered.set_alpha(112)
            surface.blit(rendered, (tag_x, tag_y))
            tag_y += max(self.ui(10), rendered.get_height() - self.ui(4))

    def draw_cutscene_theme_motifs(
        self, surface: pygame.Surface, stage_rect: pygame.Rect, accent: Color, text: str
    ) -> None:
        if any(
            term in text
            for term in ("ash", "ember", "flame", "fire", "forge", "foundry")
        ):
            for index in range(14):
                phase = self.elapsed * (1.4 + index * 0.05) + index
                x = stage_rect.x + int(
                    (0.08 + (index * 0.071) % 0.88) * stage_rect.width
                )
                y = (
                    stage_rect.bottom
                    - self.ui(12)
                    - int((math.sin(phase) * 0.5 + 0.5) * stage_rect.height * 0.55)
                )
                pygame.draw.circle(
                    surface, (245, 126, 64, 92), (x, y), max(1, self.ui(1))
                )
        if any(
            term in text
            for term in ("frozen", "moon", "water", "aquifer", "sunken", "river")
        ):
            for index in range(4):
                y = stage_rect.y + int(stage_rect.height * (0.42 + index * 0.11))
                wave = []
                for step in range(9):
                    x = stage_rect.x + int(stage_rect.width * step / 8)
                    wy = y + int(
                        math.sin(self.elapsed * 1.2 + step + index) * self.ui(3)
                    )
                    wave.append((x, wy))
                pygame.draw.lines(
                    surface, (*self.shade(accent, 35), 58), False, wave, self.ui(1)
                )
        if any(term in text for term in ("thorn", "root", "forest", "vine", "wilder")):
            for index in range(5):
                x = stage_rect.x + int(stage_rect.width * (0.1 + index * 0.19))
                points = []
                for step in range(5):
                    points.append(
                        (
                            x + int(math.sin(step + index) * self.ui(5)),
                            stage_rect.bottom - self.ui(5 + step * 12),
                        )
                    )
                pygame.draw.lines(surface, (68, 142, 86, 84), False, points, self.ui(1))
                for px, py in points[1::2]:
                    pygame.draw.circle(surface, (98, 176, 94, 82), (px, py), self.ui(2))
        if any(
            term in text
            for term in ("crypt", "grave", "bone", "dead", "ossuary", "coffin")
        ):
            for index in range(4):
                x = stage_rect.x + int(stage_rect.width * (0.18 + index * 0.2))
                y = stage_rect.bottom - self.ui(13 + (index % 2) * 7)
                pygame.draw.line(
                    surface,
                    (198, 190, 172, 72),
                    (x - self.ui(5), y),
                    (x + self.ui(5), y),
                    self.ui(1),
                )
                pygame.draw.line(
                    surface,
                    (198, 190, 172, 72),
                    (x, y - self.ui(5)),
                    (x, y + self.ui(5)),
                    self.ui(1),
                )
        if any(
            term in text
            for term in ("star", "mirror", "choir", "veil", "reliquary", "dream")
        ):
            for index in range(12):
                x = stage_rect.x + int(
                    stage_rect.width * (0.07 + (index * 0.083) % 0.86)
                )
                y = stage_rect.y + int(
                    stage_rect.height * (0.12 + (index * 0.137) % 0.42)
                )
                pulse = 0.5 + 0.5 * math.sin(self.elapsed * 2.2 + index)
                pygame.draw.circle(
                    surface,
                    (*self.shade(accent, 45), int(42 + pulse * 62)),
                    (x, y),
                    max(1, self.ui(1)),
                )
        if any(term in text for term in ("blood", "curse", "sin", "price", "debt")):
            for index in range(5):
                x = stage_rect.x + int(stage_rect.width * (0.32 + index * 0.09))
                y = stage_rect.y + int(stage_rect.height * (0.18 + (index % 3) * 0.13))
                pygame.draw.circle(surface, (180, 45, 68, 72), (x, y), self.ui(2))
                pygame.draw.polygon(
                    surface,
                    (180, 45, 68, 62),
                    [(x, y - self.ui(5)), (x - self.ui(2), y), (x + self.ui(2), y)],
                )
        if any(term in text for term in ("gate", "door", "threshold", "lock", "key")):
            door_w = max(self.ui(26), stage_rect.width // 9)
            door_h = max(self.ui(46), int(stage_rect.height * 0.46))
            door_rect = pygame.Rect(0, 0, door_w, door_h)
            door_rect.midbottom = (stage_rect.centerx, stage_rect.bottom - self.ui(8))
            pulse = 0.5 + 0.5 * math.sin(self.elapsed * 2.2)
            pygame.draw.rect(
                surface, (20, 15, 25, 150), door_rect, border_radius=self.ui(5)
            )
            pygame.draw.rect(
                surface,
                (*accent, int(82 + pulse * 76)),
                door_rect,
                self.ui(1),
                border_radius=self.ui(5),
            )
            crack_x = door_rect.centerx + int(math.sin(self.elapsed * 0.8) * self.ui(2))
            pygame.draw.line(
                surface,
                (*self.shade(accent, 55), 95),
                (crack_x, door_rect.y + self.ui(6)),
                (crack_x, door_rect.bottom - self.ui(4)),
                self.ui(1),
            )
        if any(
            term in text for term in ("bell", "toll", "chant", "choir", "song", "voice")
        ):
            center = (
                stage_rect.x + int(stage_rect.width * 0.24),
                stage_rect.y + int(stage_rect.height * 0.28),
            )
            for index in range(3):
                radius = self.ui(18 + index * 13) + int(
                    math.sin(self.elapsed * 2.1 + index) * self.ui(2)
                )
                pygame.draw.arc(
                    surface,
                    (236, 218, 138, 68 - index * 12),
                    (center[0] - radius, center[1] - radius, radius * 2, radius * 2),
                    -0.7,
                    0.7,
                    self.ui(1),
                )
        if any(
            term in text for term in ("map", "road", "path", "route", "cartographer")
        ):
            path_points = []
            for index in range(6):
                path_points.append(
                    (
                        stage_rect.x + int(stage_rect.width * (0.12 + index * 0.15)),
                        stage_rect.bottom - self.ui(12 + (index % 2) * 12),
                    )
                )
            pygame.draw.lines(
                surface, (224, 206, 150, 78), False, path_points, self.ui(1)
            )
            for point in path_points[1::2]:
                pygame.draw.circle(surface, (224, 206, 150, 86), point, self.ui(2))
        if any(
            term in text for term in ("chain", "pulley", "machine", "engine", "gear")
        ):
            for index in range(5):
                rect = pygame.Rect(
                    stage_rect.right - self.ui(42),
                    stage_rect.y + self.ui(18 + index * 16),
                    self.ui(14),
                    self.ui(9),
                )
                pygame.draw.ellipse(surface, (198, 170, 126, 78), rect, self.ui(1))
            gear_center = (
                stage_rect.right - self.ui(30),
                stage_rect.bottom - self.ui(28),
            )
            for spoke in range(8):
                angle = self.elapsed * 0.45 + math.tau * spoke / 8
                pygame.draw.line(
                    surface,
                    (198, 170, 126, 74),
                    gear_center,
                    (
                        gear_center[0] + int(math.cos(angle) * self.ui(16)),
                        gear_center[1] + int(math.sin(angle) * self.ui(16)),
                    ),
                    self.ui(1),
                )
            pygame.draw.circle(
                surface, (198, 170, 126, 78), gear_center, self.ui(15), self.ui(1)
            )
        if any(
            term in text
            for term in ("antler", "hunter", "beast", "stag", "predator", "prey")
        ):
            base = (
                stage_rect.x + int(stage_rect.width * 0.72),
                stage_rect.y + int(stage_rect.height * 0.28),
            )
            for side in (-1, 1):
                trunk_end = (base[0] + side * self.ui(18), base[1] - self.ui(24))
                pygame.draw.line(
                    surface, (214, 212, 192, 78), base, trunk_end, self.ui(1)
                )
                for branch in range(3):
                    start = (
                        base[0] + side * self.ui(8 + branch * 5),
                        base[1] - self.ui(8 + branch * 6),
                    )
                    end = (start[0] + side * self.ui(9), start[1] - self.ui(8))
                    pygame.draw.line(
                        surface, (214, 212, 192, 70), start, end, self.ui(1)
                    )
        if any(
            term in text for term in ("coin", "auction", "broker", "payment", "marked")
        ):
            for index in range(6):
                center = (
                    stage_rect.x + int(stage_rect.width * (0.18 + index * 0.09)),
                    stage_rect.bottom - self.ui(10 + (index % 3) * 5),
                )
                pygame.draw.circle(
                    surface, (213, 165, 72, 82), center, self.ui(4), self.ui(1)
                )
                pygame.draw.circle(surface, (213, 165, 72, 46), center, self.ui(1))
        if any(
            term in text for term in ("mirror", "mask", "reflection", "glass", "face")
        ):
            for index in range(4):
                cx = stage_rect.x + int(stage_rect.width * (0.42 + index * 0.08))
                cy = stage_rect.y + int(stage_rect.height * (0.18 + (index % 2) * 0.1))
                shard = [
                    (cx, cy - self.ui(9)),
                    (cx + self.ui(8), cy),
                    (cx - self.ui(3), cy + self.ui(11)),
                ]
                pygame.draw.polygon(surface, (218, 232, 245, 54), shard)
                pygame.draw.polygon(
                    surface, (*self.shade(accent, 42), 72), shard, self.ui(1)
                )

    def draw_cutscene_relic_silhouette(
        self, surface: pygame.Surface, stage_rect: pygame.Rect, accent: Color
    ) -> None:
        center = (stage_rect.centerx, stage_rect.y + int(stage_rect.height * 0.36))
        progress = self.active_cutscene_narration_progress()
        pulse = 0.5 + 0.5 * math.sin(self.elapsed * 3.4)
        radius = self.ui(20) + int(self.ui(12) * progress + self.ui(5) * pulse)
        pygame.draw.circle(surface, (*self.shade(accent, -25), 34), center, radius)
        pygame.draw.circle(surface, (*accent, 64), center, radius, self.ui(1))
        aspect = self.cutscene_relic_aspect()
        color = (*self.shade(accent, 52), 118)
        if aspect == "bell":
            rect = pygame.Rect(0, 0, self.ui(30), self.ui(30))
            rect.center = center
            pygame.draw.arc(surface, color, rect, math.pi, math.tau, self.ui(2))
            pygame.draw.line(
                surface,
                color,
                (rect.x, center[1] + self.ui(6)),
                (rect.right, center[1] + self.ui(6)),
                self.ui(2),
            )
        elif aspect == "lantern":
            rect = pygame.Rect(
                center[0] - self.ui(13),
                center[1] - self.ui(18),
                self.ui(26),
                self.ui(34),
            )
            pygame.draw.rect(surface, color, rect, self.ui(2), border_radius=self.ui(3))
            pygame.draw.line(
                surface,
                color,
                (center[0] - self.ui(8), rect.y),
                (center[0], rect.y - self.ui(8)),
                self.ui(1),
            )
            pygame.draw.line(
                surface,
                color,
                (center[0] + self.ui(8), rect.y),
                (center[0], rect.y - self.ui(8)),
                self.ui(1),
            )
            pygame.draw.circle(surface, (245, 174, 92, 86), center, self.ui(7))
        elif aspect == "key":
            pygame.draw.circle(
                surface,
                color,
                (center[0] - self.ui(8), center[1] - self.ui(4)),
                self.ui(7),
                self.ui(2),
            )
            pygame.draw.line(
                surface,
                color,
                (center[0], center[1]),
                (center[0] + self.ui(20), center[1] + self.ui(14)),
                self.ui(2),
            )
            pygame.draw.line(
                surface,
                color,
                (center[0] + self.ui(14), center[1] + self.ui(10)),
                (center[0] + self.ui(20), center[1] + self.ui(5)),
                self.ui(1),
            )
        elif aspect == "crown":
            crown = [
                (center[0] - self.ui(20), center[1] + self.ui(9)),
                (center[0] - self.ui(12), center[1] - self.ui(10)),
                (center[0], center[1] + self.ui(3)),
                (center[0] + self.ui(12), center[1] - self.ui(10)),
                (center[0] + self.ui(20), center[1] + self.ui(9)),
            ]
            pygame.draw.lines(surface, color, False, crown, self.ui(2))
        elif aspect == "mirror":
            pygame.draw.ellipse(
                surface,
                color,
                (
                    center[0] - self.ui(13),
                    center[1] - self.ui(18),
                    self.ui(26),
                    self.ui(34),
                ),
                self.ui(2),
            )
            pygame.draw.line(
                surface,
                color,
                (center[0], center[1] + self.ui(16)),
                (center[0], center[1] + self.ui(28)),
                self.ui(2),
            )
        elif aspect == "chain":
            for index in range(3):
                rect = pygame.Rect(
                    center[0] - self.ui(20) + index * self.ui(14),
                    center[1] - self.ui(7),
                    self.ui(18),
                    self.ui(12),
                )
                pygame.draw.ellipse(surface, color, rect, self.ui(2))
        elif aspect == "map":
            rect = pygame.Rect(
                center[0] - self.ui(18),
                center[1] - self.ui(13),
                self.ui(36),
                self.ui(26),
            )
            pygame.draw.rect(surface, color, rect, self.ui(1), border_radius=self.ui(2))
            pygame.draw.line(
                surface,
                color,
                (rect.x + self.ui(6), rect.y + self.ui(18)),
                (rect.right - self.ui(5), rect.y + self.ui(7)),
                self.ui(1),
            )
        elif aspect == "vessel":
            urn = [
                (center[0] - self.ui(14), center[1] - self.ui(9)),
                (center[0] - self.ui(8), center[1] + self.ui(17)),
                (center[0] + self.ui(8), center[1] + self.ui(17)),
                (center[0] + self.ui(14), center[1] - self.ui(9)),
            ]
            pygame.draw.polygon(surface, color, urn, self.ui(2))
            pygame.draw.line(
                surface,
                (*self.shade(accent, 70), 92),
                (center[0] - self.ui(10), center[1]),
                (center[0] + self.ui(10), center[1]),
                self.ui(1),
            )
        elif aspect == "seed":
            pygame.draw.ellipse(
                surface,
                color,
                (
                    center[0] - self.ui(10),
                    center[1] - self.ui(17),
                    self.ui(20),
                    self.ui(34),
                ),
                self.ui(2),
            )
            pygame.draw.line(
                surface,
                color,
                (center[0], center[1] - self.ui(12)),
                (center[0], center[1] + self.ui(12)),
                self.ui(1),
            )
        elif aspect == "spike":
            spike = [
                (center[0], center[1] - self.ui(24)),
                (center[0] + self.ui(9), center[1] + self.ui(20)),
                (center[0] - self.ui(9), center[1] + self.ui(20)),
            ]
            pygame.draw.polygon(surface, color, spike, self.ui(2))
        else:
            pygame.draw.line(
                surface,
                color,
                (center[0], center[1] - self.ui(22)),
                (center[0], center[1] + self.ui(22)),
                self.ui(2),
            )
            pygame.draw.circle(surface, color, center, self.ui(6), self.ui(1))

    def draw_cutscene_faction_sigil(
        self, surface: pygame.Surface, stage_rect: pygame.Rect, accent: Color
    ) -> None:
        if self.story_state is None:
            return
        seed = sum(ord(char) for char in self.story_state.faction)
        center = (stage_rect.right - self.ui(34), stage_rect.y + self.ui(34))
        radius = self.ui(18)
        sides = 5 + seed % 4
        points = []
        for index in range(sides):
            angle = -math.pi / 2 + math.tau * index / sides + self.elapsed * 0.08
            wobble = 0.78 + 0.22 * ((seed >> index) & 1)
            points.append(
                (
                    center[0] + int(math.cos(angle) * radius * wobble),
                    center[1] + int(math.sin(angle) * radius * wobble),
                )
            )
        pygame.draw.polygon(surface, (*self.shade(accent, -35), 54), points)
        pygame.draw.polygon(surface, (*accent, 116), points, self.ui(1))
        initials = "".join(
            part[0] for part in self.story_state.faction.split()[:2]
        ).upper()
        label = self.small_font.render(initials[:2], True, self.shade(accent, 50))
        label.set_alpha(126)
        surface.blit(label, label.get_rect(center=center))

    def draw_cutscene_choice_tableau(
        self, surface: pygame.Surface, stage_rect: pygame.Rect, accent: Color
    ) -> None:
        if not self.active_cutscene_narration_complete():
            self.draw_cutscene_narrator_wave(surface, stage_rect, accent)
            return
        choices = self.active_cutscene_choices()
        if not choices:
            return
        asset = self.active_cutscene_asset()
        source = None
        if asset is not None:
            source = asset.actors.get("relic") or asset.actors.get("guest")
        if source is not None:
            source_x = stage_rect.x + int(source.x * stage_rect.width)
            source_y = stage_rect.y + int(source.y * stage_rect.height)
        else:
            source_x, source_y = stage_rect.center
        count = min(3, len(choices))
        for index, choice in enumerate(choices[:count]):
            center = (
                stage_rect.x + int(stage_rect.width * (0.34 + index * 0.16)),
                stage_rect.bottom - self.ui(18),
            )
            color = self.cutscene_choice_color(choice.choice_key, accent)
            pulse = 0.5 + 0.5 * math.sin(self.elapsed * 2.8 + index * 1.7)
            pygame.draw.line(
                surface,
                (*color, int(36 + pulse * 56)),
                (source_x, source_y),
                center,
                self.ui(1),
            )
            self.draw_cutscene_choice_glyph(
                surface,
                center,
                choice.choice_key,
                self.ui(10),
                alpha=int(86 + pulse * 92),
            )

    def draw_cutscene_narrator_wave(
        self, surface: pygame.Surface, stage_rect: pygame.Rect, accent: Color
    ) -> None:
        source = (stage_rect.x + self.ui(20), stage_rect.y + self.ui(24))
        target = (stage_rect.centerx, stage_rect.y + int(stage_rect.height * 0.34))
        node = self.active_cutscene_node()
        asset = self.active_cutscene_asset()
        if node is not None and asset is not None and node.speaker in asset.actors:
            actor = asset.actors[node.speaker]
            target = (
                stage_rect.x + int(actor.x * stage_rect.width),
                stage_rect.y + int(actor.y * stage_rect.height),
            )
        progress = self.active_cutscene_narration_progress()
        for index in range(4):
            t = (progress + index * 0.18 + self.elapsed * 0.08) % 1.0
            x = int(source[0] + (target[0] - source[0]) * t)
            y = int(source[1] + (target[1] - source[1]) * t)
            wobble = int(math.sin(self.elapsed * 4.0 + index) * self.ui(3))
            pygame.draw.circle(
                surface,
                (*self.shade(accent, 48), 80 - index * 10),
                (x, y + wobble),
                max(1, self.ui(2)),
            )

    def draw_cutscene_choice_glyph(
        self,
        surface: pygame.Surface,
        center: tuple[int, int],
        choice_key: str,
        radius: int,
        alpha: int = 180,
    ) -> None:
        color = self.cutscene_choice_color(
            choice_key,
            self.story_state.accent if self.story_state else self.theme.accent,
        )
        cx, cy = center
        pygame.draw.circle(
            surface,
            (*self.shade(color, -55), max(18, alpha // 3)),
            center,
            radius + self.ui(3),
        )
        pygame.draw.circle(surface, (*color, alpha), center, radius, self.ui(1))
        if choice_key == "aid":
            shield = [
                (cx, cy - radius),
                (cx + radius, cy - radius // 3),
                (cx + radius // 2, cy + radius),
                (cx, cy + radius + self.ui(2)),
                (cx - radius // 2, cy + radius),
                (cx - radius, cy - radius // 3),
            ]
            pygame.draw.polygon(surface, (*color, alpha), shield, self.ui(1))
            pygame.draw.line(
                surface,
                (*color, alpha),
                (cx, cy - radius // 2),
                (cx, cy + radius // 2),
                self.ui(1),
            )
            pygame.draw.line(
                surface,
                (*color, alpha),
                (cx - radius // 2, cy),
                (cx + radius // 2, cy),
                self.ui(1),
            )
        elif choice_key == "bargain":
            diamond = [
                (cx, cy - radius),
                (cx + radius, cy),
                (cx, cy + radius),
                (cx - radius, cy),
            ]
            pygame.draw.polygon(surface, (*color, alpha), diamond, self.ui(1))
            pygame.draw.circle(
                surface,
                (*color, alpha),
                (cx - radius // 2, cy - radius // 3),
                max(1, radius // 4),
                self.ui(1),
            )
            pygame.draw.circle(
                surface,
                (190, 45, 70, alpha),
                (cx + radius // 2, cy + radius // 3),
                max(1, radius // 4),
            )
        elif choice_key == "defy":
            pygame.draw.line(
                surface,
                (*color, alpha),
                (cx - radius, cy + radius),
                (cx + radius, cy - radius),
                self.ui(2),
            )
            pygame.draw.line(
                surface,
                (*color, alpha),
                (cx - radius, cy - radius // 2),
                (cx + radius, cy + radius // 2),
                self.ui(1),
            )
            pygame.draw.polygon(
                surface,
                (*color, alpha),
                [
                    (cx + radius, cy - radius),
                    (cx + radius // 2, cy - radius // 2),
                    (cx + radius // 4, cy - radius),
                ],
                0,
            )
        else:
            pygame.draw.circle(surface, (*color, alpha), center, max(1, radius // 3))

    def cutscene_choice_color(self, choice_key: str, accent: Color) -> Color:
        if choice_key == "aid":
            return (108, 218, 156)
        if choice_key == "bargain":
            return (213, 165, 72)
        if choice_key == "defy":
            return (232, 83, 74)
        return accent

    def cutscene_story_text(self) -> str:
        parts = [self.active_cutscene_text()]
        if self.story_state is not None:
            parts.extend(
                [
                    self.story_state.title,
                    self.story_state.objective,
                    self.story_state.faction,
                    self.story_state.relic_name,
                    self.story_state.relic_form,
                    self.story_state.relic_temptation,
                ]
            )
        beat = self.current_story_beat()
        if beat is not None:
            parts.extend(
                [
                    beat.title,
                    beat.summary,
                    beat.theme_name,
                    beat.guest_role,
                    beat.guest_motive,
                ]
            )
        return " ".join(parts)

    def draw_cutscene_actor(
        self,
        surface: pygame.Surface,
        stage_rect: pygame.Rect,
        actor: CutsceneActorAsset,
        animation_id: str,
        accent: Color,
    ) -> None:
        dx, dy, frame_scale, alpha, pose = self.cutscene_actor_frame(
            actor.id, animation_id
        )
        color = self.cutscene_actor_color(actor, accent)
        x = stage_rect.x + int((actor.x + dx) * stage_rect.width)
        y = stage_rect.y + int((actor.y + dy) * stage_rect.height)
        shadow_w = int(54 * actor.scale * frame_scale)
        shadow_h = max(6, int(14 * actor.scale * frame_scale))
        shadow = pygame.Surface((shadow_w, shadow_h), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 92), shadow.get_rect())
        surface.blit(shadow, shadow.get_rect(center=(x, y + self.ui(20))))

        node = self.active_cutscene_node()
        if node is not None and node.speaker == actor.id:
            glow_radius = int(42 * actor.scale * frame_scale)
            glow = pygame.Surface((glow_radius * 2, glow_radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(
                glow,
                (*color, 38 + int(22 * (0.5 + 0.5 * math.sin(self.elapsed * 3.6)))),
                (glow_radius, glow_radius),
                glow_radius,
            )
            surface.blit(glow, glow.get_rect(center=(x, y - self.ui(18))))

        sprite = self.cutscene_actor_surface(actor, color, pose)
        scale = actor.scale * frame_scale * (1.0 + max(0, self.ui_scale - 1) * 0.16)
        sprite_w = max(1, int(sprite.get_width() * scale))
        sprite_h = max(1, int(sprite.get_height() * scale))
        sprite = pygame.transform.scale(sprite, (sprite_w, sprite_h))
        sprite.set_alpha(max(0, min(255, int(255 * alpha))))
        surface.blit(sprite, sprite.get_rect(midbottom=(x, y + self.ui(16))))
        self.draw_cutscene_actor_pose_effects(
            surface, x, y, sprite_w, sprite_h, actor, pose, color, accent
        )

        label_text = self.cutscene_actor_label(actor)
        if label_text:
            label = self.small_font.render(label_text, True, color)
            surface.blit(label, label.get_rect(center=(x, y - sprite_h - self.ui(3))))

    def cutscene_actor_frame(
        self, actor_id: str, animation_id: str
    ) -> tuple[float, float, float, float, str]:
        asset = self.active_cutscene_asset()
        if asset is None or self.active_cutscene is None:
            return 0.0, 0.0, 1.0, 1.0, "idle"
        animation = asset.animations.get(animation_id)
        if animation is None:
            return 0.0, 0.0, 1.0, 1.0, "idle"
        frames = [frame for frame in animation.frames if frame.actor == actor_id]
        if not frames:
            return 0.0, 0.0, 1.0, 1.0, "idle"
        duration = sum(frame.duration for frame in frames)
        if duration <= 0:
            return 0.0, 0.0, 1.0, 1.0, "idle"
        t = self.active_cutscene.node_elapsed
        if animation.loop:
            t %= duration
        else:
            t = min(t, duration - 0.001)
        elapsed = 0.0
        for index, frame in enumerate(frames):
            if t <= elapsed + frame.duration:
                next_frame: SpriteAnimationFrameAsset
                if index + 1 < len(frames):
                    next_frame = frames[index + 1]
                elif animation.loop:
                    next_frame = frames[0]
                else:
                    next_frame = frame
                phase = 0.0 if frame.duration <= 0 else (t - elapsed) / frame.duration
                phase = max(0.0, min(1.0, phase))
                return (
                    frame.dx + (next_frame.dx - frame.dx) * phase,
                    frame.dy + (next_frame.dy - frame.dy) * phase,
                    frame.scale + (next_frame.scale - frame.scale) * phase,
                    frame.alpha + (next_frame.alpha - frame.alpha) * phase,
                    frame.pose,
                )
            elapsed += frame.duration
        frame = frames[-1]
        return frame.dx, frame.dy, frame.scale, frame.alpha, frame.pose

    def cutscene_actor_surface(
        self, actor: CutsceneActorAsset, color: Color, pose: str = "idle"
    ) -> pygame.Surface:
        if actor.sprite == "player":
            sprite = self.sprites.player_sprites.get(
                self.player.class_name, self.sprites.player
            ).copy()
            if pose in ("vow", "guard", "defy"):
                pygame.draw.line(
                    sprite,
                    (245, 236, 190),
                    (sprite.get_width() // 2, 8),
                    (sprite.get_width() // 2 + 12, 2),
                    max(1, self.ui_scale),
                )
            return sprite
        if actor.sprite == "relic":
            return self.cutscene_relic_surface(color, pose)
        if actor.sprite == "story_guest":
            return self.cutscene_guest_surface(color, pose)
        if actor.sprite == "enemy":
            return self.sprites.enemies.get("Gate Warden") or next(
                iter(self.sprites.enemies.values())
            )
        return self.cutscene_guest_surface(color, pose)

    def cutscene_guest_surface(
        self, color: Color, pose: str = "idle"
    ) -> pygame.Surface:
        sprite = pygame.Surface((54, 76), pygame.SRCALPHA)
        pygame.draw.ellipse(sprite, (*color, 44), (5, 51, 44, 18))
        sway = 2 if pose in ("shudder", "warn") else 0
        cloak = [(27 + sway, 7), (8, 58), (46, 58)]
        pygame.draw.polygon(sprite, self.shade(color, -62), cloak)
        pygame.draw.polygon(sprite, color, cloak, 2)
        pygame.draw.circle(sprite, self.shade(color, 35), (27 + sway // 2, 21), 10)
        pygame.draw.circle(sprite, (245, 236, 205), (24 + sway // 2, 20), 2)
        pygame.draw.circle(sprite, (245, 236, 205), (30 + sway // 2, 20), 2)
        if pose in ("plead", "reach", "warn"):
            left_hand = (12, 31 if pose == "warn" else 24)
            right_hand = (42, 25 if pose == "reach" else 32)
            pygame.draw.line(sprite, self.shade(color, 28), (20, 35), left_hand, 3)
            pygame.draw.line(sprite, self.shade(color, 28), (34, 35), right_hand, 3)
            pygame.draw.circle(sprite, (235, 218, 190), left_hand, 3)
            pygame.draw.circle(sprite, (235, 218, 190), right_hand, 3)
        else:
            pygame.draw.line(sprite, self.shade(color, 18), (18, 39), (12, 51), 3)
            pygame.draw.line(sprite, self.shade(color, 18), (36, 39), (42, 51), 3)
        mouth_y = 42 if pose in ("plead", "warn") else 41
        pygame.draw.line(
            sprite, (*self.shade(color, 25), 180), (17, mouth_y), (37, mouth_y), 2
        )
        return sprite

    def cutscene_relic_surface(
        self, color: Color, pose: str = "idle"
    ) -> pygame.Surface:
        sprite = pygame.Surface((54, 72), pygame.SRCALPHA)
        pulse = 0.5 + 0.5 * math.sin(self.elapsed * 4.0)
        ring_alpha = int(44 + 44 * pulse)
        if pose in ("reveal", "surge", "pulse"):
            ring_alpha = min(140, ring_alpha + 42)
        pygame.draw.circle(sprite, (*color, ring_alpha), (27, 34), 24)
        diamond = [(27, 6), (44, 34), (27, 62), (10, 34)]
        pygame.draw.polygon(sprite, self.shade(color, -45), diamond)
        pygame.draw.polygon(sprite, color, diamond, 2)
        pygame.draw.line(sprite, self.shade(color, 45), (27, 13), (27, 55), 2)
        pygame.draw.line(sprite, self.shade(color, 28), (16, 34), (38, 34), 2)
        aspect = self.cutscene_relic_aspect()
        if aspect == "blade":
            pygame.draw.line(sprite, (246, 236, 196), (19, 52), (36, 17), 3)
            pygame.draw.polygon(sprite, (246, 236, 196), [(36, 17), (35, 27), (42, 21)])
        elif aspect == "mirror":
            pygame.draw.ellipse(sprite, (235, 229, 245), (18, 20, 18, 26), 2)
            pygame.draw.line(sprite, (235, 229, 245), (27, 46), (27, 56), 2)
        elif aspect == "crown":
            pygame.draw.polygon(
                sprite,
                (242, 211, 94),
                [(16, 28), (21, 18), (27, 28), (34, 18), (39, 28), (39, 36), (16, 36)],
                2,
            )
        elif aspect == "key":
            pygame.draw.circle(sprite, (234, 218, 154), (22, 28), 5, 2)
            pygame.draw.line(sprite, (234, 218, 154), (27, 28), (40, 42), 2)
            pygame.draw.line(sprite, (234, 218, 154), (35, 37), (40, 34), 2)
        elif aspect == "bell":
            pygame.draw.arc(
                sprite, (236, 218, 138), (17, 20, 22, 28), math.pi, math.tau, 2
            )
            pygame.draw.line(sprite, (236, 218, 138), (18, 34), (36, 34), 2)
            pygame.draw.circle(sprite, (236, 218, 138), (27, 39), 3)
        elif aspect == "lantern":
            pygame.draw.rect(
                sprite, (245, 196, 108), (18, 20, 18, 28), 2, border_radius=3
            )
            pygame.draw.line(sprite, (245, 196, 108), (20, 20), (27, 12), 1)
            pygame.draw.line(sprite, (245, 196, 108), (34, 20), (27, 12), 1)
            pygame.draw.circle(sprite, (245, 124, 72), (27, 35), 5)
        elif aspect == "chain":
            for index in range(3):
                pygame.draw.ellipse(
                    sprite, (216, 194, 156), (15 + index * 8, 28, 14, 9), 2
                )
        elif aspect == "map":
            pygame.draw.rect(
                sprite, (228, 208, 162), (15, 23, 24, 24), 1, border_radius=2
            )
            pygame.draw.line(sprite, (228, 208, 162), (19, 40), (36, 28), 1)
            pygame.draw.circle(sprite, (228, 208, 162), (22, 37), 1)
        elif aspect == "vessel":
            pygame.draw.polygon(
                sprite, (170, 210, 232), [(18, 25), (23, 49), (31, 49), (36, 25)], 2
            )
            pygame.draw.line(sprite, (170, 210, 232), (21, 34), (33, 34), 1)
        elif aspect == "seed":
            pygame.draw.ellipse(sprite, (126, 214, 92), (19, 19, 16, 31), 2)
            pygame.draw.line(sprite, (126, 214, 92), (27, 24), (27, 45), 1)
        elif aspect == "spike":
            pygame.draw.polygon(
                sprite, (220, 210, 190), [(27, 15), (36, 52), (18, 52)], 2
            )
        elif aspect == "blood":
            pygame.draw.circle(sprite, (192, 46, 70), (27, 34), 6)
            pygame.draw.polygon(sprite, (192, 46, 70), [(27, 18), (20, 35), (34, 35)])
        else:
            pygame.draw.circle(sprite, self.shade(color, 50), (27, 34), 6, 2)
            pygame.draw.circle(sprite, self.shade(color, 50), (27, 34), 2)
        return sprite

    def draw_cutscene_actor_pose_effects(
        self,
        surface: pygame.Surface,
        x: int,
        y: int,
        sprite_w: int,
        sprite_h: int,
        actor: CutsceneActorAsset,
        pose: str,
        color: Color,
        accent: Color,
    ) -> None:
        top = y + self.ui(16) - sprite_h
        if actor.id == "guest":
            self.draw_cutscene_guest_prop(
                surface, x + sprite_w // 3, top + self.ui(12), color
            )
            if pose in ("plead", "reach", "warn"):
                for index in range(3):
                    phase = self.elapsed * 2.4 + index * 1.1
                    mote = (
                        x - self.ui(22 - index * 9),
                        top
                        + self.ui(12 + index * 5)
                        + int(math.sin(phase) * self.ui(3)),
                    )
                    pygame.draw.circle(
                        surface, (*color, 96 - index * 18), mote, self.ui(2)
                    )
            if pose == "shudder":
                pygame.draw.line(
                    surface,
                    (190, 45, 70, 110),
                    (x - self.ui(13), top),
                    (x + self.ui(11), top + self.ui(24)),
                    self.ui(1),
                )
        elif actor.id == "player":
            if pose in ("vow", "guard"):
                shield = pygame.Surface((self.ui(42), self.ui(42)), pygame.SRCALPHA)
                pygame.draw.circle(
                    shield,
                    (108, 218, 156, 52),
                    shield.get_rect().center,
                    self.ui(20),
                    self.ui(2),
                )
                surface.blit(shield, shield.get_rect(center=(x, top + self.ui(24))))
            elif pose == "defy":
                pygame.draw.line(
                    surface,
                    (232, 83, 74, 150),
                    (x - self.ui(17), top + self.ui(36)),
                    (x + self.ui(19), top + self.ui(10)),
                    self.ui(2),
                )
                pygame.draw.line(
                    surface,
                    (245, 228, 170, 120),
                    (x - self.ui(11), top + self.ui(12)),
                    (x + self.ui(23), top + self.ui(33)),
                    self.ui(1),
                )
            elif pose == "price":
                pygame.draw.circle(
                    surface,
                    (190, 45, 70, 120),
                    (x + self.ui(16), top + self.ui(21)),
                    self.ui(3),
                )
        elif actor.id == "relic":
            pulse = 0.5 + 0.5 * math.sin(self.elapsed * 5.0)
            for index in range(2):
                radius = self.ui(18 + index * 11) + int(pulse * self.ui(6))
                pygame.draw.circle(
                    surface,
                    (*accent, 44 - index * 12),
                    (x, top + sprite_h // 2),
                    radius,
                    self.ui(1),
                )
            if pose in ("surge", "reveal"):
                for angle_index in range(6):
                    angle = self.elapsed * 0.8 + math.tau * angle_index / 6
                    start = (
                        x + int(math.cos(angle) * self.ui(15)),
                        top + sprite_h // 2 + int(math.sin(angle) * self.ui(12)),
                    )
                    end = (
                        x + int(math.cos(angle) * self.ui(29)),
                        top + sprite_h // 2 + int(math.sin(angle) * self.ui(23)),
                    )
                    pygame.draw.line(surface, (*accent, 118), start, end, self.ui(1))
        elif actor.id == "antagonist":
            pulse = 0.5 + 0.5 * math.sin(self.elapsed * 2.8)
            crown_y = top + self.ui(8)
            pygame.draw.circle(
                surface,
                (232, 83, 74, int(42 + pulse * 42)),
                (x, top + sprite_h // 2),
                self.ui(28),
                self.ui(1),
            )
            for side in (-1, 1):
                pygame.draw.line(
                    surface,
                    (232, 83, 74, 104),
                    (x, crown_y),
                    (x + side * self.ui(20), crown_y - self.ui(12)),
                    self.ui(1),
                )
                pygame.draw.line(
                    surface,
                    (232, 83, 74, 72),
                    (x + side * self.ui(12), crown_y + self.ui(4)),
                    (x + side * self.ui(28), crown_y + self.ui(18)),
                    self.ui(1),
                )

    def draw_cutscene_guest_prop(
        self, surface: pygame.Surface, x: int, y: int, color: Color
    ) -> None:
        text = self.cutscene_story_text().lower()
        if any(term in text for term in ("bell", "toll", "priest", "acolyte")):
            pygame.draw.arc(
                surface,
                (236, 218, 138, 150),
                (x - self.ui(6), y, self.ui(12), self.ui(14)),
                math.pi,
                math.tau,
                self.ui(1),
            )
            pygame.draw.line(
                surface,
                (236, 218, 138, 150),
                (x - self.ui(6), y + self.ui(8)),
                (x + self.ui(6), y + self.ui(8)),
                self.ui(1),
            )
        elif any(
            term in text for term in ("lock", "key", "thief", "rogue", "cartographer")
        ):
            pygame.draw.circle(
                surface,
                (234, 218, 154, 150),
                (x, y + self.ui(5)),
                self.ui(4),
                self.ui(1),
            )
            pygame.draw.line(
                surface,
                (234, 218, 154, 150),
                (x + self.ui(4), y + self.ui(5)),
                (x + self.ui(12), y + self.ui(13)),
                self.ui(1),
            )
        elif any(term in text for term in ("grave", "dead", "bone", "coffin", "crypt")):
            pygame.draw.circle(
                surface,
                (220, 212, 190, 145),
                (x, y + self.ui(6)),
                self.ui(5),
                self.ui(1),
            )
            pygame.draw.line(
                surface,
                (220, 212, 190, 145),
                (x - self.ui(5), y + self.ui(14)),
                (x + self.ui(5), y + self.ui(14)),
                self.ui(1),
            )
        elif any(term in text for term in ("star", "mirror", "dream", "veil")):
            pygame.draw.circle(
                surface,
                (*self.shade(color, 45), 140),
                (x, y + self.ui(7)),
                self.ui(7),
                self.ui(1),
            )
            pygame.draw.circle(
                surface, (*self.shade(color, 45), 140), (x, y + self.ui(7)), self.ui(2)
            )
        else:
            pygame.draw.rect(
                surface,
                (224, 206, 168, 130),
                (x - self.ui(5), y, self.ui(10), self.ui(14)),
                self.ui(1),
            )
            pygame.draw.line(
                surface,
                (224, 206, 168, 130),
                (x - self.ui(3), y + self.ui(4)),
                (x + self.ui(3), y + self.ui(4)),
                self.ui(1),
            )

    def cutscene_relic_aspect(self) -> str:
        text = self.cutscene_story_text().lower()
        if any(
            term in text
            for term in ("spike", "nail", "blade", "sword", "knife", "fang", "weapon")
        ):
            return (
                "spike" if any(term in text for term in ("spike", "nail")) else "blade"
            )
        if any(
            term in text for term in ("mirror", "lens", "face", "reflection", "psalter")
        ):
            return "mirror"
        if any(term in text for term in ("crown", "antler")):
            return "crown"
        if any(term in text for term in ("chain", "oath-eater")):
            return "chain"
        if any(term in text for term in ("map", "vellum", "road", "cartographer")):
            return "map"
        if any(term in text for term in ("lantern", "lamp")):
            return "lantern"
        if any(term in text for term in ("urn", "vessel", "rain", "water")):
            return "vessel"
        if any(term in text for term in ("seed", "heartseed", "reliquary", "heart")):
            return "seed"
        if any(term in text for term in ("key", "cinder-key")):
            return "key"
        if any(term in text for term in ("bell", "toll", "chime")):
            return "bell"
        if any(term in text for term in ("blood", "sin", "curse", "wound")):
            return "blood"
        return "eye"

    def cutscene_actor_color(self, actor: CutsceneActorAsset, accent: Color) -> Color:
        role = actor.color.lower()
        if role == "accent":
            return accent
        if role == "player":
            return (226, 222, 205)
        if role == "danger":
            return (235, 95, 84)
        if role.startswith("#") and len(role) == 7:
            try:
                return (int(role[1:3], 16), int(role[3:5], 16), int(role[5:7], 16))
            except ValueError:
                return accent
        return accent

    def cutscene_actor_label(self, actor: CutsceneActorAsset) -> str:
        if self.active_cutscene is None:
            return ""
        context = {**self.quest_cutscene_context(self.active_cutscene_guest())}
        context.update(self.active_cutscene.context)
        return format_asset_text(actor.name, context)[:32]

    def draw_story_intro_overlay(self) -> None:
        lines = self.story_intro_lines()
        if not lines:
            return
        width, height = self.screen.get_size()
        dim = pygame.Surface((width, height), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 255))
        self.screen.blit(dim, (0, 0))

        accent = self.story_state.accent if self.story_state else self.theme.accent
        panel_w = min(width - self.ui(28), self.ui(900))
        panel_h = min(height - self.ui(16), self.ui(610))
        if panel_w < 300 or panel_h < 260:
            return
        rect = pygame.Rect(
            (width - panel_w) // 2,
            max(self.ui(8), (height - panel_h) // 2),
            panel_w,
            panel_h,
        )
        surface = pygame.Surface(rect.size, pygame.SRCALPHA)
        self.draw_translucent_panel(
            surface,
            surface.get_rect(),
            (10, 8, 14, 248),
            (*accent, 222),
            radius=self.ui(14),
            width=self.ui(2),
        )
        pygame.draw.line(
            surface,
            (255, 245, 210, 28),
            (self.ui(24), self.ui(10)),
            (panel_w - self.ui(24), self.ui(10)),
            self.ui(1),
        )

        pad = max(self.ui(14), 18)
        available_w = panel_w - pad * 2
        title_text = "Guest Relic Omen"
        depth_text = f"Depth {self.current_depth}/{DUNGEON_DEPTH}"
        header_h = max(self.font.get_height(), self.small_font.get_height()) + self.ui(
            8
        )
        meta_w = min(
            self.small_font.size(depth_text)[0] + self.ui(8),
            max(self.ui(96), available_w // 3),
        )
        meta_x = pad + available_w - meta_w
        title_rect = pygame.Rect(
            pad,
            pad,
            max(1, meta_x - pad - self.ui(10)),
            self.font.get_height(),
        )
        meta_rect = pygame.Rect(
            meta_x,
            pad + (self.font.get_height() - self.small_font.get_height()) // 2,
            meta_w,
            self.small_font.get_height(),
        )
        self.draw_ui_text(surface, title_text, self.font, accent, title_rect)
        self.draw_ui_text(
            surface,
            depth_text,
            self.small_font,
            (196, 188, 204),
            meta_rect,
            align="right",
        )

        options = self.story_relic_choice_options()
        options_to_draw = options[: min(3, len(options))]
        choice_gap = max(self.ui(4), 6)
        footer_h = self.small_font.get_height()
        choice_w = available_w
        option_entries = [
            (label, detail) for _choice_key, label, detail in options_to_draw
        ]
        option_heights = [
            self.cutscene_response_height(label, detail, choice_w)
            for label, detail in option_entries
        ]
        choices_block_h = (
            sum(option_heights) + max(0, len(option_heights) - 1) * choice_gap
        )
        choices_start = panel_h - pad - footer_h - self.ui(10) - choices_block_h

        stage_top = pad + header_h + self.ui(12)
        available_for_stage = max(
            self.ui(48), choices_start - stage_top - self.small_font.get_height() * 3
        )
        stage_h = max(self.ui(52), min(int(panel_h * 0.30), available_for_stage))
        stage_rect = pygame.Rect(pad, stage_top, available_w, stage_h)
        self.draw_story_intro_stage(surface, stage_rect, accent, options_to_draw)

        y = stage_rect.bottom + self.ui(12)
        body_lines: list[tuple[str, Color]] = []
        for index, line in enumerate(lines):
            color = (244, 232, 214) if index == 0 else (214, 207, 196)
            if line.startswith("Depth "):
                color = (238, 218, 164)
            for wrapped in self.wrap_ui_text(line, self.small_font, available_w):
                body_lines.append((wrapped, color))
        text_bottom = max(y + self.small_font.get_height(), choices_start - self.ui(10))
        line_h = max(self.small_font.get_height() + self.ui(3), self.ui(18))
        max_body_lines = max(1, (text_bottom - y) // line_h)
        for text_line, color in body_lines[:max_body_lines]:
            self.draw_ui_text(
                surface,
                text_line,
                self.small_font,
                color,
                pygame.Rect(pad, y, available_w, line_h),
            )
            y += line_h
        if len(body_lines) > max_body_lines and y + line_h <= choices_start:
            self.draw_ui_text(
                surface,
                "…",
                self.small_font,
                (170, 165, 155),
                pygame.Rect(pad, y, available_w, line_h),
            )

        choice_rects = self.cutscene_response_rects(
            option_entries, pad, choices_start, choice_w, choice_gap
        )
        for index, ((choice_key, label, detail), choice_rect) in enumerate(
            zip(options_to_draw, choice_rects)
        ):
            choice_color = self.cutscene_choice_color(choice_key, accent)
            pygame.draw.rect(
                surface,
                (24, 19, 30, 238),
                choice_rect,
                border_radius=self.ui(9),
            )
            pygame.draw.rect(
                surface,
                (*choice_color, 170),
                choice_rect,
                self.ui(1),
                border_radius=self.ui(9),
            )
            key_size = min(self.ui(36), choice_rect.height - self.ui(12))
            key_rect = pygame.Rect(
                choice_rect.x + self.ui(7),
                choice_rect.y + (choice_rect.height - key_size) // 2,
                key_size,
                key_size,
            )
            pygame.draw.rect(
                surface,
                (*self.shade(choice_color, -58), 238),
                key_rect,
                border_radius=self.ui(7),
            )
            self.draw_cutscene_choice_glyph(
                surface,
                key_rect.center,
                choice_key,
                max(self.ui(7), key_size // 3),
                alpha=96,
            )
            self.draw_ui_text(
                surface,
                str(index + 1),
                self.font,
                choice_color,
                key_rect,
                align="center",
                valign="center",
            )
            text_x = key_rect.right + self.ui(9)
            text_rect = pygame.Rect(
                text_x,
                choice_rect.y + self.ui(7),
                max(1, choice_rect.right - text_x - self.ui(8)),
                choice_rect.height - self.ui(14),
            )
            self.draw_cutscene_response_text(surface, label, detail, text_rect)

        footer = "Press 1-3 to confirm the guest dialog, place the relic, and begin this level."
        self.draw_ui_text(
            surface,
            footer,
            self.small_font,
            (205, 185, 225),
            pygame.Rect(pad, panel_h - pad - footer_h, available_w, footer_h),
        )
        self.screen.blit(surface, rect)

    def draw_story_intro_stage(
        self,
        surface: pygame.Surface,
        stage_rect: pygame.Rect,
        accent: Color,
        options: list[tuple[str, str, str]],
    ) -> None:
        pygame.draw.rect(
            surface, (15, 13, 21, 245), stage_rect, border_radius=self.ui(10)
        )
        self.draw_cutscene_story_backdrop(surface, stage_rect, accent)
        pygame.draw.rect(
            surface, (*accent, 125), stage_rect, self.ui(1), border_radius=self.ui(10)
        )
        horizon_y = stage_rect.y + int(stage_rect.height * 0.64)
        pygame.draw.line(
            surface,
            (*self.shade(accent, -25), 76),
            (stage_rect.x + self.ui(10), horizon_y),
            (stage_rect.right - self.ui(10), horizon_y),
            self.ui(1),
        )

        guest = self.current_story_guest_for_depth()
        guest_color = self.mix(accent, (228, 218, 198), 0.35)
        player_actor = CutsceneActorAsset(
            "player", self.player.class_name, "player", 0.24, 0.72, 0.74, "player"
        )
        guest_actor = CutsceneActorAsset(
            "guest",
            guest.name if guest is not None else "Guest",
            "story_guest",
            0.50,
            0.70,
            0.80,
            "accent",
        )
        relic_actor = CutsceneActorAsset(
            "relic", "Relic Echo", "relic", 0.76, 0.62, 0.80, "accent"
        )
        self.draw_intro_stage_actor(surface, stage_rect, player_actor, "vow", accent)
        self.draw_intro_stage_actor(
            surface, stage_rect, guest_actor, "plead", guest_color
        )
        self.draw_intro_stage_actor(surface, stage_rect, relic_actor, "reveal", accent)

        source = (
            stage_rect.x + int(relic_actor.x * stage_rect.width),
            stage_rect.y + int(relic_actor.y * stage_rect.height) - self.ui(18),
        )
        for index, (choice_key, _label, _detail) in enumerate(options[:3]):
            choice_color = self.cutscene_choice_color(choice_key, accent)
            pulse = 0.5 + 0.5 * math.sin(self.elapsed * 2.8 + index * 1.7)
            center = (
                stage_rect.x + int(stage_rect.width * (0.34 + index * 0.16)),
                stage_rect.bottom - self.ui(18),
            )
            pygame.draw.line(
                surface,
                (*choice_color, int(36 + pulse * 56)),
                source,
                center,
                self.ui(1),
            )
            self.draw_cutscene_choice_glyph(
                surface,
                center,
                choice_key,
                self.ui(10),
                alpha=int(86 + pulse * 92),
            )

    def draw_intro_stage_actor(
        self,
        surface: pygame.Surface,
        stage_rect: pygame.Rect,
        actor: CutsceneActorAsset,
        pose: str,
        color: Color,
    ) -> None:
        x = stage_rect.x + int(actor.x * stage_rect.width)
        y = stage_rect.y + int(actor.y * stage_rect.height)
        shadow_w = max(1, int(54 * actor.scale))
        shadow_h = max(6, int(14 * actor.scale))
        shadow = pygame.Surface((shadow_w, shadow_h), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 92), shadow.get_rect())
        surface.blit(shadow, shadow.get_rect(center=(x, y + self.ui(20))))
        sprite = self.cutscene_actor_surface(actor, color, pose)
        scale = actor.scale * (1.0 + max(0, self.ui_scale - 1) * 0.16)
        sprite_w = max(1, int(sprite.get_width() * scale))
        sprite_h = max(1, int(sprite.get_height() * scale))
        sprite = pygame.transform.scale(sprite, (sprite_w, sprite_h))
        surface.blit(sprite, sprite.get_rect(midbottom=(x, y + self.ui(16))))
        self.draw_cutscene_actor_pose_effects(
            surface, x, y, sprite_w, sprite_h, actor, pose, color, color
        )
        label_text = actor.name[:32]
        label = self.tiny_font.render(label_text, True, color)
        label.set_alpha(168)
        surface.blit(label, label.get_rect(center=(x, y - sprite_h - self.ui(2))))

    def draw_ui(self) -> None:
        width, height = self.screen.get_size()
        reserved_h = self.hud_panel_height()
        accent = self.theme.accent
        outer = max(self.ui(14), 18)
        gap = max(self.ui(8), 12)
        action_gap = max(self.ui(8), 8)
        reserved_inner_h = max(1, reserved_h - self.ui(24))
        action_h = max(self.ui(54), min(self.ui(70), int(reserved_inner_h * 0.46)))
        panel_h = max(1, reserved_h - action_h - action_gap)
        panel = pygame.Rect(0, height - panel_h, width, panel_h)
        dock = pygame.Surface(panel.size, pygame.SRCALPHA)
        pygame.draw.rect(dock, (12, 12, 17, 238), dock.get_rect())
        pygame.draw.line(
            dock, (*self.shade(accent, -18), 190), (0, 0), (width, 0), self.ui(2)
        )
        pygame.draw.line(
            dock,
            (255, 245, 210, 26),
            (self.ui(18), self.ui(8)),
            (width - self.ui(18), self.ui(8)),
            self.ui(1),
        )
        self.screen.blit(dock, panel)

        inner = pygame.Rect(
            outer,
            panel.y + self.ui(12),
            max(1, width - outer * 2),
            max(1, panel_h - self.ui(24)),
        )
        top_area = pygame.Rect(inner.x, inner.y, inner.width, inner.height)
        action_bar = pygame.Rect(
            inner.x, panel.y - action_gap - action_h, inner.width, action_h
        )
        left_w = max(170, min(max(self.ui(120), 190), int(top_area.width * 0.29)))
        center_w = max(190, min(max(self.ui(150), 230), int(top_area.width * 0.33)))
        if top_area.width - left_w - center_w - gap * 2 < 170:
            left_w = max(150, int(top_area.width * 0.30))
            center_w = max(170, int(top_area.width * 0.32))
        right_w = max(1, top_area.width - left_w - center_w - gap * 2)
        resources = pygame.Rect(top_area.x, top_area.y, left_w, top_area.height)
        character = pygame.Rect(
            resources.right + gap, top_area.y, center_w, top_area.height
        )
        mission = pygame.Rect(
            character.right + gap, top_area.y, right_w, top_area.height
        )
        hud_cards: tuple[tuple[pygame.Rect, Color], ...] = (
            (resources, (118, 94, 72)),
            (character, accent),
            (mission, self.shade(accent, -18)),
        )
        for card, border in hud_cards:
            self.draw_translucent_panel(
                self.screen,
                card,
                (18, 17, 23, 232),
                (border[0], border[1], border[2], 128),
                radius=self.ui(8),
            )

        pad = max(self.ui(8), 10)
        bar_gap = max(self.ui(4), 6)
        bar_h = max(
            self.ui(10),
            min(self.ui(17), (resources.height - pad * 2 - bar_gap * 2) // 3),
        )
        bars_h = bar_h * 3 + bar_gap * 2
        bar_y = resources.y + (resources.height - bars_h) // 2
        bar_w = max(1, resources.width - pad * 2)
        self.draw_bar(
            resources.x + pad,
            bar_y,
            bar_w,
            bar_h,
            self.player.hp,
            self.player.max_hp,
            (185, 46, 46),
            "HP",
        )
        self.draw_bar(
            resources.x + pad,
            bar_y + bar_h + bar_gap,
            bar_w,
            bar_h,
            self.player.mana,
            self.player.max_mana,
            (54, 102, 210),
            "Mana",
        )
        self.draw_bar(
            resources.x + pad,
            bar_y + (bar_h + bar_gap) * 2,
            bar_w,
            bar_h,
            self.player.stamina,
            self.player.max_stamina,
            (216, 170, 66),
            "Stamina",
        )

        weapon = (
            self.player.equipment["weapon"].name
            if self.player.equipment["weapon"]
            else "Training Sword"
        )
        armor = (
            self.player.equipment["armor"].name
            if self.player.equipment["armor"]
            else "Cloth"
        )
        line_h = max(self.small_font.get_height() + self.ui(3), self.ui(18))
        text_rect = character.inflate(-pad * 2, -pad * 2)
        self.draw_ui_text(
            self.screen,
            self.player.class_name,
            self.font,
            (242, 232, 210),
            pygame.Rect(
                text_rect.x, text_rect.y, text_rect.width, self.font.get_height()
            ),
        )
        char_y = text_rect.y + self.font.get_height() + self.ui(5)
        potion_count = sum(1 for item in self.player.inventory if item.slot == "potion")
        mana_potion_count = sum(
            1 for item in self.player.inventory if item.slot == "mana_potion"
        )
        stat_lines = [
            f"Level {self.player.level} · XP {self.player.xp}/{self.player.next_xp}",
            f"Upgrades {len(self.player.skill_upgrades)} · Potions {potion_count}/{mana_potion_count}",
            f"{weapon} · DMG {self.player.melee_damage()}",
            f"{armor} · DR {self.player.armor()}",
        ]
        for line in stat_lines:
            if char_y + line_h > text_rect.bottom:
                break
            self.draw_ui_text(
                self.screen,
                line,
                self.small_font,
                (210, 204, 190),
                pygame.Rect(text_rect.x, char_y, text_rect.width, line_h),
            )
            char_y += line_h

        hint = self.current_interaction_hint()
        objective = (
            "Find the stairs to descend deeper"
            if self.current_depth < DUNGEON_DEPTH
            else "Defeat the gate tyrant, then reach the stairs"
        )
        detail = ""
        objective_color = accent
        if hint:
            _key, title, detail, objective_color = hint
            objective = title
        mission_inner = mission.inflate(-pad * 2, -pad * 2)
        self.draw_ui_text(
            self.screen,
            objective,
            self.font,
            objective_color,
            pygame.Rect(
                mission_inner.x,
                mission_inner.y,
                mission_inner.width,
                self.font.get_height(),
            ),
            align="right",
        )
        mission_y = mission_inner.y + self.font.get_height() + self.ui(4)
        if detail:
            for wrapped in self.wrap_ui_text(
                detail, self.small_font, mission_inner.width
            )[:2]:
                if mission_y + line_h > mission_inner.bottom:
                    break
                self.draw_ui_text(
                    self.screen,
                    wrapped,
                    self.small_font,
                    (218, 210, 190),
                    pygame.Rect(
                        mission_inner.x, mission_y, mission_inner.width, line_h
                    ),
                    align="right",
                )
                mission_y += line_h
        self.draw_interaction_prompt(hint)

        quest_control = (
            "Q hide quest"
            if getattr(self, "quest_info_visible", True)
            else "Q show quest"
        )
        debug_dark = (
            " · Ctrl+Shift+D light"
            if self.is_current_floor_dark()
            else " · Ctrl+Shift+D dark"
        )
        control_lines = [
            f"Mouse/aim · 1-6 actions · E interact · I inventory · C character · {quest_control} · H help{debug_dark}",
        ]
        control_y = max(
            mission_y + self.ui(4),
            mission_inner.bottom - self.tiny_font.get_height() * 3,
        )
        tiny_h = max(self.tiny_font.get_height() + self.ui(2), self.ui(15))
        for controls in control_lines:
            for wrapped in self.wrap_ui_text(
                controls, self.tiny_font, mission_inner.width
            )[:2]:
                if control_y + tiny_h > mission_inner.bottom:
                    break
                self.draw_ui_text(
                    self.screen,
                    wrapped,
                    self.tiny_font,
                    (170, 165, 155),
                    pygame.Rect(
                        mission_inner.x, control_y, mission_inner.width, tiny_h
                    ),
                    align="right",
                )
                control_y += tiny_h

        self.draw_hud_action_bar(action_bar)
        self.draw_run_header()
        self.draw_story_panel()
        self.draw_boss_bar()

    def draw_interaction_prompt(self, hint: tuple[str, str, str, Color] | None) -> None:
        if not hint:
            return
        key, title, detail, color = hint
        width, height = self.screen.get_size()
        prompt_w = min(width - self.ui(40), self.ui(560))
        prompt_h = max(self.ui(56), self.small_font.get_height() * 2 + self.ui(18))
        rect = pygame.Rect(
            width - prompt_w - self.ui(22),
            height - self.hud_panel_height() - prompt_h - self.ui(12),
            prompt_w,
            prompt_h,
        )
        if rect.y < self.ui(108):
            rect.y = self.ui(108)
        surface = pygame.Surface(rect.size, pygame.SRCALPHA)
        self.draw_translucent_panel(
            surface,
            surface.get_rect(),
            (12, 11, 14, 232),
            (*color, 184),
            radius=self.ui(9),
        )
        key_rect = pygame.Rect(
            self.ui(10),
            self.ui(10),
            self.ui(44),
            prompt_h - self.ui(20),
        )
        pygame.draw.rect(
            surface, (*self.shade(color, -55), 236), key_rect, border_radius=self.ui(7)
        )
        pygame.draw.rect(
            surface, (*color, 230), key_rect, self.ui(1), border_radius=self.ui(7)
        )
        self.draw_ui_text(surface, key, self.font, color, key_rect, "center", "center")
        text_x = key_rect.right + self.ui(12)
        text_w = max(1, prompt_w - text_x - self.ui(12))
        self.draw_ui_text(
            surface,
            title,
            self.small_font,
            (245, 238, 216),
            pygame.Rect(text_x, self.ui(8), text_w, self.small_font.get_height()),
        )
        detail_y = self.ui(10) + self.small_font.get_height()
        for wrapped in self.wrap_ui_text(detail, self.small_font, text_w)[:1]:
            self.draw_ui_text(
                surface,
                wrapped,
                self.small_font,
                (178, 174, 164),
                pygame.Rect(text_x, detail_y, text_w, self.small_font.get_height()),
            )
        self.screen.blit(surface, rect)

    def draw_screen_flash(self) -> None:
        if self.screen_flash_ttl <= 0:
            return
        width, height = self.screen.get_size()
        alpha = max(0, min(120, int(120 * (self.screen_flash_ttl / 0.30))))
        overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        overlay.fill((*self.screen_flash_color, alpha))
        self.screen.blit(overlay, (0, 0))

    def draw_run_header(self) -> None:
        width, _height = self.screen.get_size()
        darkness = " — Dark" if self.is_current_floor_dark() else ""
        title = f"Run {self.run_number}: Depth {self.current_depth}/{DUNGEON_DEPTH} — {self.theme.name}{darkness}"
        difficulty = self.difficulty_profile()
        floor_plan = self.current_floor_plan()
        floor_summary = self.floor_plan_summary(floor_plan)
        modifier = (
            f"Difficulty: {difficulty.name} · Modifier: "
            f"{self.run_modifier.name} — {self.run_modifier.description}"
        )
        if floor_plan is not None:
            modifier = f"{modifier} · {floor_summary}"
        quest_info_visible = getattr(self, "quest_info_visible", True)
        story = (
            self.story_header_line()
            if quest_info_visible
            else "Quest info hidden · press Q to show"
        )
        story_color = (205, 185, 225) if quest_info_visible else (155, 150, 145)
        margin = self.ui(18)
        pad = self.ui(10)
        line_h = max(self.small_font.get_height() + self.ui(3), self.ui(18))
        header_w = min(width - margin * 2, self.ui(740))
        header_h = pad * 2 + self.font.get_height() + line_h * 2 + self.ui(4)
        rect = pygame.Rect(margin, self.ui(14), header_w, header_h)
        surface = pygame.Surface(rect.size, pygame.SRCALPHA)
        self.draw_translucent_panel(
            surface,
            surface.get_rect(),
            (10, 10, 15, 210),
            (*self.theme.accent, 120),
            radius=self.ui(9),
        )
        self.draw_ui_text(
            surface,
            title,
            self.font,
            self.theme.accent,
            pygame.Rect(pad, pad, header_w - pad * 2, self.font.get_height()),
        )
        y = pad + self.font.get_height() + self.ui(5)
        self.draw_ui_text(
            surface,
            modifier,
            self.small_font,
            (205, 200, 190),
            pygame.Rect(pad, y, header_w - pad * 2, line_h),
        )
        y += line_h
        self.draw_ui_text(
            surface,
            story,
            self.small_font,
            story_color,
            pygame.Rect(pad, y, header_w - pad * 2, line_h),
        )
        self.screen.blit(surface, rect)

    def draw_boss_bar(self) -> None:
        boss = self.boss_enemy()
        if not boss:
            return
        width, _height = self.screen.get_size()
        margin = self.ui(18)
        bar_w = min(width - margin * 2, self.ui(520))
        bar_h = max(self.ui(10), self.small_font.get_height() // 2)
        x = (width - bar_w) // 2
        y = self.ui(22)
        fill = int(bar_w * max(0, boss.hp) / boss.max_hp)
        rect = pygame.Rect(x, y, bar_w, bar_h)
        pygame.draw.rect(self.screen, (28, 10, 14), rect, border_radius=self.ui(5))
        pygame.draw.rect(
            self.screen,
            self.theme.accent,
            pygame.Rect(x, y, fill, bar_h),
            border_radius=self.ui(5),
        )
        pygame.draw.rect(
            self.screen,
            (190, 160, 115),
            rect,
            self.ui(1),
            border_radius=self.ui(5),
        )
        label = self.small_font.render(
            self.ellipsize_ui_text(boss.name, self.small_font, bar_w),
            True,
            (245, 235, 215),
        )
        self.screen.blit(label, label.get_rect(center=(width // 2, y - self.ui(9))))

    def draw_bar(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        value: float,
        max_value: float,
        color: Color,
        label: str,
    ) -> None:
        radius = max(2, min(self.ui(5), h // 2))
        rect = pygame.Rect(x, y, w, h)
        pygame.draw.rect(self.screen, (34, 31, 36), rect, border_radius=radius)
        ratio = 0.0 if max_value <= 0 else max(0.0, min(1.0, value / max_value))
        fill = int(w * ratio)
        if fill > 0:
            pygame.draw.rect(
                self.screen,
                color,
                pygame.Rect(x, y, fill, h),
                border_radius=radius,
            )
        pygame.draw.rect(
            self.screen,
            (105, 96, 88),
            rect,
            self.ui(1),
            border_radius=radius,
        )
        text = self.tiny_font.render(
            f"{label} {int(value)}/{int(max_value)}", True, (245, 240, 230)
        )
        self.screen.blit(text, text.get_rect(center=rect.center))

    def draw_inventory(self) -> None:
        self.menus.draw_inventory()

    def draw_character_menu(self) -> None:
        self.menus.draw_character_menu()

    def draw_title_menu(self) -> None:
        self.menus.draw_title_menu()

    def draw_options_menu(self) -> None:
        self.menus.draw_options_menu()

    def draw_about_screen(self) -> None:
        self.menus.draw_about_screen()

    def draw_exit_confirmation(self) -> None:
        self.menus.draw_exit_confirmation()

    def draw_help_overlay(self) -> None:
        self.menus.draw_help_overlay()

    def draw_archetype_select(self) -> None:
        self.menus.draw_archetype_select()

    def draw_state_overlay(self) -> None:
        self.menus.draw_state_overlay()

    def run_summary_lines(self) -> list[str]:
        minutes = int(self.elapsed // 60)
        seconds = int(self.elapsed % 60)
        bosses = ", ".join(self.run_stats.defeated_bosses[-3:]) or (
            "Gate defeated" if self.run_stats.boss_killed else "none"
        )
        notable = ", ".join(self.run_stats.notable_loot[-3:]) or "none"
        discoveries = ", ".join(self.run_stats.discoveries[-3:]) or "none"
        cause = self.run_stats.cause_of_death or "survived"
        progress = self.meta_progress
        return [
            (
                f"Time {minutes:02d}:{seconds:02d}  "
                f"Depth {self.current_depth}/{DUNGEON_DEPTH}  "
                f"Difficulty {self.difficulty_profile().name}  "
                f"Modifier {self.run_modifier.name}"
            ),
            f"Kills {self.run_stats.kills}  Boss {'defeated' if self.run_stats.boss_killed else 'alive'}  Damage taken {self.run_stats.damage_taken}  Cause {cause}",
            f"Loot {self.run_stats.loot_picked_up}  Potions {self.run_stats.potions_used}  Shrines {self.run_stats.shrines_used}  Notable {notable}",
            f"Secrets {self.run_stats.secrets_opened} ({discoveries})  Traps triggered {self.run_stats.traps_triggered}  Story choices {self.run_stats.story_choices}",
            f"Elites {self.run_stats.elites_killed}  Minibosses {self.run_stats.minibosses_killed}  Challenge rooms {self.run_stats.challenge_rooms_cleared}  Upgrades {self.run_stats.upgrades_chosen}",
            f"Bosses defeated {bosses}",
            f"Mastery: best depth {progress.get('best_depth', 0)}  clears {progress.get('clears', 0)}  known bosses {len(progress.get('bosses_defeated', []))}",
        ]
