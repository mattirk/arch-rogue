# pyright: reportAttributeAccessIssue=false, reportUnusedImport=false
from __future__ import annotations

import math
from collections import deque
from typing import cast

import pygame

from ..constants import DUNGEON_DEPTH, TILE_H, TILE_W, WORLD_SCALE, SlashEffect
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


class RenderingEffectsMixin:
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
        if self.is_current_floor_dark():
            return
        self.screen.blit(self.ambient_overlay_surface(), (0, 0))

    def draw_darkness_overlay(self) -> None:
        # Dark floors are now communicated by tile/object visibility itself.
        # Avoid drawing extra ellipse or ring overlays around the player; those
        # artifacts made the light radius look like a UI vector mask instead of
        # in-world darkness.
        return

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

    def _guidance_glow_layer(self, w: int, h: int) -> pygame.Surface:
        # Reuse a persistent full-screen alpha layer instead of allocating
        # one every frame; clear it before each use.
        if not hasattr(self, "_guidance_glow_surface"):
            self._guidance_glow_surface = pygame.Surface((w, h), pygame.SRCALPHA)
        surf = self._guidance_glow_surface
        if surf.get_size() != (w, h):
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            self._guidance_glow_surface = surf
        surf.fill((0, 0, 0, 0))
        return surf

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
        screen_w, screen_h = self._screen_size()
        glow_layer = self._guidance_glow_layer(screen_w, screen_h)
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

        # Cache the route by quantized start/goal; the BFS only needs to
        # re-run when the player or target changes tile.
        if not hasattr(self, "_guidance_route_cache"):
            self._guidance_route_cache: dict[
                tuple[tuple[int, int], tuple[int, int]], list[tuple[float, float]]
            ] = {}
        route_key = (start, goal)
        cached_route = self._guidance_route_cache.get(route_key)
        if cached_route is not None:
            return cached_route

        def walkable(tile: tuple[int, int]) -> bool:
            x, y = tile
            return (
                self.dungeon.in_bounds(x, y) and self.dungeon.tiles[x][y] != Tile.WALL
            )

        if not walkable(start) or not walkable(goal):
            self._guidance_route_cache[route_key] = []
            return []
        if start == goal:
            result = [(self.player.x, self.player.y), target]
            self._guidance_route_cache[route_key] = result
            return result

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
            self._guidance_route_cache[route_key] = []
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
        self._guidance_route_cache[route_key] = route
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
