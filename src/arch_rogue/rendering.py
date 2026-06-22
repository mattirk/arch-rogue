# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

import math
from collections import deque
from typing import cast

import pygame

from .constants import DUNGEON_DEPTH, TILE_H, TILE_W, WORLD_SCALE, SlashEffect
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
        self.draw_ui()
        if self.active_cutscene is not None:
            self.draw_quest_cutscene_overlay()
        elif self.story_intro_pending:
            self.draw_story_intro_overlay()
        if self.inventory_open:
            self.draw_inventory()
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
                    self.draw_tile(x, y, self.dungeon.tiles[x][y])

    def draw_tile(self, x: int, y: int, tile: Tile) -> None:
        sx, sy = self.world_to_screen(x + 0.5, y + 0.5)
        seed = self.tile_seed(x, y)
        surface, anchor_x, anchor_y = self.tile_surface(tile, seed)
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
        for item in self.items:
            drawables.append((item.x + item.y, "item", item))
        for trap in self.traps:
            drawables.append((trap.x + trap.y - 0.02, "trap", trap))
        for shrine in self.shrines:
            drawables.append((shrine.x + shrine.y, "shrine", shrine))
        for secret in self.secrets:
            if secret.revealed and not secret.opened:
                drawables.append((secret.x + secret.y, "secret", secret))
        for guest in self.story_guests:
            drawables.append((guest.x + guest.y, "story_guest", guest))
        for projectile in self.projectiles:
            drawables.append((projectile.x + projectile.y, "projectile", projectile))
        for enemy in self.enemies:
            drawables.append((enemy.x + enemy.y, "enemy", enemy))
        drawables.append((self.player.x + self.player.y, "player", self.player))
        for slash in self.slashes:
            x, y, _ttl, _dx, _dy = slash
            drawables.append((x + y + 0.05, "slash", slash))
        for effect in self.impact_effects:
            drawables.append((effect.x + effect.y + 0.08, "impact", effect))

        self.draw_aim_cone()
        self.draw_story_relic_guidance()

        for _depth, kind, obj in sorted(drawables, key=lambda entry: entry[0]):
            if kind == "item":
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
        alpha = max(0, min(210, int(190 * life)))
        overlay = pygame.Surface((radius * 2 + 8, radius + 12), pygame.SRCALPHA)
        center = (overlay.get_width() // 2, overlay.get_height() // 2)
        pygame.draw.ellipse(
            overlay,
            (*effect.color, int(alpha * 0.35)),
            overlay.get_rect().inflate(-4, -overlay.get_height() // 3),
            max(1, WORLD_SCALE),
        )
        pygame.draw.circle(overlay, (*effect.color, alpha), center, max(2, radius // 5))
        spoke_count = 8 if effect.kind == "burst" else 5
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
                (*self.shade(effect.color, 45), alpha),
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
            bob = 0.8 + footfall * 2.4
            sway = stride * 1.45
            forward_lean = 1.25 if actor.speed >= 3.0 else 0.85
            lean = forward_lean + math.sin(phase - 0.35) * 0.35
            stretch = 1.0 + footfall * 0.012
            return sway, bob, lean, stretch
        idle = math.sin(self.elapsed * 2.2 + actor.x * 0.7 + actor.y * 0.4)
        return 0.0, idle * 0.8, idle * 0.35, 1.0

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

    def draw_player(self, player: Player) -> None:
        sway, bob, lean, stretch = self.actor_animation(player)
        sprite = self.sprites.player_sprites.get(player.class_name, self.sprites.player)
        self.draw_shadow(player.x, player.y, 34, 13, moving=player.moving, lift=bob)
        self.draw_movement_trail(player, (145, 130, 98), size=2)
        if player.moving:
            self.blit_sprite(
                sprite,
                player.x - player.move_x * 0.035,
                player.y - player.move_y * 0.035,
                y_offset=8 - bob,
                facing_x=player.facing_x,
                x_offset=sway,
                stretch=1.0,
                lean=0.0,
                alpha=52,
            )
        sx, sy = self.blit_sprite(
            sprite,
            player.x,
            player.y,
            y_offset=6.0 - bob,
            facing_x=player.facing_x,
            x_offset=sway,
            stretch=1.0,
            lean=0.0,
        )

    def draw_aim_cone(self) -> None:
        sx, sy = self.world_to_screen(self.player.x, self.player.y)
        vx, vy = self.iso_screen_direction(self.player.facing_x, self.player.facing_y)
        px, py = -vy, vx
        origin = (
            sx + int(vx * 14 * WORLD_SCALE),
            sy - 8 * WORLD_SCALE + int(vy * 6 * WORLD_SCALE),
        )
        tip = (
            origin[0] + int(vx * 108 * WORLD_SCALE),
            origin[1] + int(vy * 108 * WORLD_SCALE),
        )
        left = (
            origin[0] + int(vx * 74 * WORLD_SCALE + px * 36 * WORLD_SCALE),
            origin[1] + int(vy * 74 * WORLD_SCALE + py * 36 * WORLD_SCALE),
        )
        right = (
            origin[0] + int(vx * 74 * WORLD_SCALE - px * 36 * WORLD_SCALE),
            origin[1] + int(vy * 74 * WORLD_SCALE - py * 36 * WORLD_SCALE),
        )
        points = [origin, left, tip, right]
        blur_pad = 14 * WORLD_SCALE
        min_x = min(point[0] for point in points) - blur_pad
        max_x = max(point[0] for point in points) + blur_pad
        min_y = min(point[1] for point in points) - blur_pad
        max_y = max(point[1] for point in points) + blur_pad
        overlay = pygame.Surface((max_x - min_x, max_y - min_y), pygame.SRCALPHA)
        local_points = [(x - min_x, y - min_y) for x, y in points]

        glow = pygame.Surface(overlay.get_size(), pygame.SRCALPHA)
        pygame.draw.polygon(glow, (92, 170, 255, 24), local_points)
        local_tip = (tip[0] - min_x, tip[1] - min_y)
        blur_size = (
            max(1, glow.get_width() // 4),
            max(1, glow.get_height() // 4),
        )
        glow = pygame.transform.smoothscale(glow, blur_size)
        glow = pygame.transform.smoothscale(glow, overlay.get_size())
        overlay.blit(glow, (0, 0))

        pygame.draw.polygon(overlay, (92, 170, 255, 34), local_points)
        pygame.draw.circle(overlay, (225, 245, 255, 120), local_tip, 2 * WORLD_SCALE)
        self.screen.blit(overlay, (min_x, min_y))

    def draw_enemy(self, enemy: Enemy) -> None:
        fallback = (
            self.sprites.enemies["Gate Warden"]
            if enemy.kind == "boss"
            else self.sprites.enemies["Ghoul"]
        )
        sprite = self.sprites.enemies.get(enemy.name, fallback)
        shadow_w = (
            44 if enemy.kind == "boss" else 38 if enemy.name == "Gate Warden" else 32
        )
        sway, bob, lean, stretch = self.actor_animation(enemy)
        if enemy.kind == "boss":
            stretch += math.sin(self.elapsed * 3.4) * 0.025
            lean += math.sin(self.elapsed * 2.1) * 1.0
        elif enemy.elite_modifier or enemy.kind == "miniboss":
            stretch += math.sin(self.elapsed * 5.0) * 0.015
        self.draw_shadow(enemy.x, enemy.y, shadow_w, 12, moving=enemy.moving, lift=bob)
        self.draw_movement_trail(enemy, (120, 84, 68), size=2)
        if enemy.moving:
            self.blit_sprite(
                sprite,
                enemy.x - enemy.move_x * 0.03,
                enemy.y - enemy.move_y * 0.03,
                y_offset=8.0 - bob,
                facing_x=enemy.facing_x,
                x_offset=sway,
                stretch=1.0,
                lean=0.0,
                alpha=42,
            )
        sx, sy = self.blit_sprite(
            sprite,
            enemy.x,
            enemy.y,
            y_offset=6.0 - bob,
            facing_x=enemy.facing_x,
            x_offset=sway,
            stretch=1.0,
            lean=0.0,
        )
        bar_w = (
            46 if enemy.kind == "boss" else 34 if enemy.name == "Gate Warden" else 28
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
        if enemy.elite_modifier or enemy.kind == "miniboss":
            pulse = 0.5 + 0.5 * math.sin(self.elapsed * 5.2)
            marker = pygame.Surface(
                (42 * WORLD_SCALE, 18 * WORLD_SCALE), pygame.SRCALPHA
            )
            pygame.draw.ellipse(
                marker,
                (*enemy.color, int(20 + pulse * 38)),
                marker.get_rect(),
                max(1, WORLD_SCALE),
            )
            self.screen.blit(
                marker, marker.get_rect(center=(sx, sy - 14 * WORLD_SCALE))
            )
            label = self.small_font.render(enemy.elite_modifier, True, enemy.color)
            self.screen.blit(
                label, label.get_rect(center=(sx, bar_y - 8 * WORLD_SCALE))
            )
        if enemy.attack_timer <= 0.28 and enemy.kind in ("boss", "miniboss", "ranged"):
            tell_color = self.theme.accent if enemy.kind == "boss" else enemy.color
            pulse = 0.55 + 0.45 * math.sin(self.elapsed * 18.0)
            pygame.draw.circle(
                self.screen,
                (*tell_color, int(90 + 90 * pulse)),
                (sx, sy - 18 * WORLD_SCALE),
                max(3, int(5 * WORLD_SCALE + pulse * 2 * WORLD_SCALE)),
                max(1, WORLD_SCALE),
            )
            label = self.small_font.render("!", True, tell_color)
            self.screen.blit(label, label.get_rect(center=(sx, sy - 34 * WORLD_SCALE)))
        if enemy.kind == "boss":
            pulse = 0.5 + 0.5 * math.sin(self.elapsed * 4.2)
            aura = pygame.Surface((70 * WORLD_SCALE, 28 * WORLD_SCALE), pygame.SRCALPHA)
            pygame.draw.ellipse(
                aura,
                (*self.theme.accent, int(26 + pulse * 34)),
                aura.get_rect(),
                max(1, WORLD_SCALE),
            )
            self.screen.blit(aura, aura.get_rect(center=(sx, sy - 18 * WORLD_SCALE)))

    def draw_item(self, item: Item) -> None:
        if item.slot == "story_relic":
            self.draw_story_relic(item)
            return
        sx, sy = self.world_to_screen(item.x, item.y)
        rarity_color = self.rarity_color(item.visible_rarity)
        rarity_icon = self.rarity_icon(item.visible_rarity)
        sprite = self.sprites.items.get(item.slot, self.sprites.items["potion"])
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
        self.draw_shadow(guest.x, guest.y, 24, 10)
        pulse = 0.55 + 0.45 * math.sin(self.elapsed * 4.0 + guest.depth)
        if not guest.resolved:
            ring = pygame.Surface((42 * WORLD_SCALE, 22 * WORLD_SCALE), pygame.SRCALPHA)
            pygame.draw.ellipse(
                ring,
                (*color, int(24 + 36 * pulse)),
                ring.get_rect(),
                max(1, WORLD_SCALE),
            )
            self.screen.blit(ring, ring.get_rect(center=(sx, sy + 4 * WORLD_SCALE)))
        cloak = [
            (sx, sy - 26 * WORLD_SCALE),
            (sx - 13 * WORLD_SCALE, sy + 5 * WORLD_SCALE),
            (sx + 13 * WORLD_SCALE, sy + 5 * WORLD_SCALE),
        ]
        pygame.draw.polygon(self.screen, self.shade(color, -55), cloak)
        pygame.draw.polygon(self.screen, color, cloak, max(1, WORLD_SCALE))
        pygame.draw.circle(
            self.screen,
            self.shade(color, 35),
            (sx, sy - 18 * WORLD_SCALE),
            6 * WORLD_SCALE,
        )
        marker = "✓" if guest.resolved else "?"
        marker_surface = self.small_font.render(marker, True, (245, 236, 205))
        self.screen.blit(
            marker_surface, marker_surface.get_rect(center=(sx, sy - 19 * WORLD_SCALE))
        )
        if (
            not guest.resolved
            and math.hypot(guest.x - self.player.x, guest.y - self.player.y) < 1.25
        ):
            label = self.small_font.render(f"1-3: {guest.name}", True, color)
            sublabel = self.small_font.render(guest.role, True, (205, 200, 185))
            self.screen.blit(label, label.get_rect(center=(sx, sy - 43 * WORLD_SCALE)))
            self.screen.blit(
                sublabel, sublabel.get_rect(center=(sx, sy - 30 * WORLD_SCALE))
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
        sprite = self.sprites.projectiles.get(
            projectile.owner, self.sprites.projectiles["enemy"]
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

    def wrap_ui_text(
        self, text: str, font: pygame.font.Font, max_width: int
    ) -> list[str]:
        lines: list[str] = []
        for paragraph in text.splitlines() or [""]:
            words = paragraph.split()
            if not words:
                lines.append("")
                continue
            current = words[0]
            for word in words[1:]:
                candidate = f"{current} {word}"
                if font.size(candidate)[0] <= max_width:
                    current = candidate
                else:
                    lines.append(current)
                    current = word
            lines.append(current)
        return lines

    def draw_story_panel(self) -> None:
        lines = self.story_panel_lines()
        if not lines:
            return
        width, height = self.screen.get_size()
        bottom_panel_top = height - self.ui(112)
        x = self.ui(20)
        y = self.ui(98)
        panel_w = min(width - self.ui(40), self.ui(620))
        max_h = min(self.ui(182), bottom_panel_top - y - self.ui(12))
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
        pad = self.ui(10)
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
        line_h = max(self.small_font.get_height() + self.ui(1), self.ui(16))
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

    def draw_quest_cutscene_overlay(self) -> None:
        asset = self.active_cutscene_asset()
        node = self.active_cutscene_node()
        if asset is None or node is None:
            return
        width, height = self.screen.get_size()
        dim = pygame.Surface((width, height), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 142))
        self.screen.blit(dim, (0, 0))

        accent = self.story_state.accent if self.story_state else self.theme.accent
        panel_w = min(width - self.ui(42), self.ui(880))
        panel_h = min(height - self.ui(30), self.ui(560))
        if panel_w < self.ui(320) or panel_h < self.ui(300):
            return
        rect = pygame.Rect(
            (width - panel_w) // 2,
            max(self.ui(20), (height - panel_h) // 2),
            panel_w,
            panel_h,
        )
        surface = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(
            surface, (10, 8, 14, 246), surface.get_rect(), border_radius=self.ui(13)
        )
        pygame.draw.rect(
            surface,
            (*accent, 220),
            surface.get_rect(),
            self.ui(2),
            border_radius=self.ui(13),
        )

        pad = self.ui(16)
        title_text = asset.title
        if self.story_intro_pending:
            title_text = f"{asset.title} · Depth {self.current_depth}/{DUNGEON_DEPTH}"
        title = self.font.render(title_text, True, accent)
        surface.blit(title, (pad, pad))
        node_label = self.small_font.render(
            node.id.replace("_", " ").title(), True, (170, 165, 180)
        )
        surface.blit(
            node_label, (panel_w - pad - node_label.get_width(), pad + self.ui(4))
        )

        stage_h = max(self.ui(58), min(self.ui(112), int(panel_h * 0.24)))
        stage_rect = pygame.Rect(
            pad,
            pad + title.get_height() + self.ui(10),
            panel_w - pad * 2,
            stage_h,
        )
        self.draw_cutscene_stage(surface, stage_rect, node.animation, accent)

        choices = self.active_cutscene_choices()
        choice_gap = self.ui(4)
        choice_h = max(self.ui(30), self.small_font.get_height() * 2 + self.ui(4))
        choices_to_draw = choices[: min(9, len(choices))]
        choices_block_h = (
            len(choices_to_draw) * choice_h
            + max(0, len(choices_to_draw) - 1) * choice_gap
        )
        footer_h = self.small_font.get_height()
        choices_start = panel_h - pad - footer_h - self.ui(10) - choices_block_h
        y = stage_rect.bottom + self.ui(10)
        speaker = self.active_cutscene_speaker_name()
        speaker_text = self.small_font.render(speaker, True, (246, 235, 210))
        surface.blit(speaker_text, (pad, y))
        pygame.draw.line(
            surface,
            (*accent, 130),
            (
                pad + speaker_text.get_width() + self.ui(8),
                y + speaker_text.get_height() // 2,
            ),
            (panel_w - pad, y + speaker_text.get_height() // 2),
            self.ui(1),
        )
        y += speaker_text.get_height() + self.ui(6)

        text_bottom = max(y + self.small_font.get_height(), choices_start - self.ui(8))
        line_h = max(self.small_font.get_height() + self.ui(2), self.ui(17))
        body_lines: list[str] = []
        for paragraph in self.active_cutscene_text().splitlines() or [""]:
            body_lines.extend(
                self.wrap_ui_text(paragraph, self.small_font, panel_w - pad * 2)
            )
        max_body_lines = max(1, (text_bottom - y) // line_h)
        for index, text_line in enumerate(body_lines[:max_body_lines]):
            color = (225, 218, 202)
            if index == 0 and self.story_intro_pending:
                color = (238, 218, 164)
            text = self.small_font.render(text_line, True, color)
            surface.blit(text, (pad, y))
            y += line_h
        if len(body_lines) > max_body_lines and y + line_h <= choices_start:
            text = self.small_font.render("…", True, (170, 165, 155))
            surface.blit(text, (pad, y))

        y = max(choices_start, stage_rect.bottom + self.ui(8))
        for index, choice in enumerate(choices_to_draw):
            choice_rect = pygame.Rect(pad, y, panel_w - pad * 2, choice_h)
            pygame.draw.rect(
                surface,
                (24, 19, 31, 240),
                choice_rect,
                border_radius=self.ui(8),
            )
            pygame.draw.rect(
                surface,
                (*accent, 155),
                choice_rect,
                self.ui(1),
                border_radius=self.ui(8),
            )
            key_rect = pygame.Rect(
                choice_rect.x + self.ui(8),
                choice_rect.y + self.ui(8),
                self.ui(34),
                choice_rect.height - self.ui(16),
            )
            pygame.draw.rect(
                surface,
                (*self.shade(accent, -55), 238),
                key_rect,
                border_radius=self.ui(6),
            )
            self.draw_cutscene_choice_glyph(
                surface,
                key_rect.center,
                choice.choice_key,
                max(self.ui(8), min(key_rect.width, key_rect.height) // 3),
                alpha=92,
            )
            key = self.font.render(str(index + 1), True, accent)
            surface.blit(key, key.get_rect(center=key_rect.center))
            label = self.small_font.render(choice.label, True, (246, 235, 210))
            text_x = choice_rect.x + self.ui(52)
            label_y = choice_rect.y + self.ui(4)
            surface.blit(label, (text_x, label_y))
            detail_color = (184, 178, 168)
            detail_lines = self.wrap_ui_text(
                choice.detail, self.small_font, choice_rect.width - self.ui(62)
            )[:1]
            if detail_lines:
                detail = self.small_font.render(detail_lines[0], True, detail_color)
                surface.blit(detail, (text_x, label_y + self.small_font.get_height()))
            y += choice_h + choice_gap

        footer_text = (
            "Press 1-3 to choose a dialogue response."
            if len(choices_to_draw) >= 3
            else "Press Enter/E to advance, Esc to close non-blocking dialogue."
        )
        if self.story_intro_pending:
            footer_text = "Press 1-3 to confirm the guest dialog, place the relic, and begin this level."
        footer = self.small_font.render(footer_text, True, (205, 185, 225))
        surface.blit(footer, (pad, panel_h - pad - footer.get_height()))
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
        self.draw_cutscene_theme_motifs(surface, stage_rect, accent, text)
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
        if any(term in text for term in ("blade", "sword", "knife", "fang", "weapon")):
            return "blade"
        if any(term in text for term in ("mirror", "lens", "face", "reflection")):
            return "mirror"
        if any(term in text for term in ("crown", "tyrant", "king", "warden")):
            return "crown"
        if any(term in text for term in ("key", "lock", "gate", "door")):
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
        dim.fill((0, 0, 0, 116))
        self.screen.blit(dim, (0, 0))

        accent = self.story_state.accent if self.story_state else self.theme.accent
        panel_w = min(width - self.ui(48), self.ui(760))
        panel_h = min(height - self.ui(72), self.ui(410))
        rect = pygame.Rect(
            (width - panel_w) // 2,
            max(self.ui(28), (height - panel_h) // 2 - self.ui(18)),
            panel_w,
            panel_h,
        )
        surface = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(
            surface, (11, 9, 15, 244), surface.get_rect(), border_radius=self.ui(12)
        )
        pygame.draw.rect(
            surface,
            (*accent, 210),
            surface.get_rect(),
            self.ui(2),
            border_radius=self.ui(12),
        )
        pad = self.ui(18)
        title = self.font.render("Guest Relic Omen", True, accent)
        surface.blit(title, (pad, pad))
        y = pad + title.get_height() + self.ui(8)
        available_w = panel_w - pad * 2
        options = self.story_relic_choice_options()
        line_h = max(self.small_font.get_height() + self.ui(2), self.ui(18))
        choice_h = max(self.ui(50), self.small_font.get_height() * 2 + self.ui(12))
        choice_gap = self.ui(6)
        footer_h = self.small_font.get_height()
        footer_gap = self.ui(10)
        choices_block_h = (
            len(options) * choice_h + max(0, len(options) - 1) * choice_gap
        )
        choices_start_limit = panel_h - pad - footer_h - footer_gap - choices_block_h

        body_lines: list[tuple[str, Color]] = []
        for index, line in enumerate(lines):
            color = (244, 232, 214) if index == 0 else (214, 207, 196)
            if line.startswith("Depth "):
                color = (238, 218, 164)
            for wrapped in self.wrap_ui_text(line, self.small_font, available_w):
                body_lines.append((wrapped, color))
        body_bottom = max(y + line_h, choices_start_limit - self.ui(8))
        max_body_lines = max(1, (body_bottom - y) // line_h)
        for text_line, color in body_lines[:max_body_lines]:
            text = self.small_font.render(text_line, True, color)
            surface.blit(text, (pad, y))
            y += line_h
        if len(
            body_lines
        ) > max_body_lines and y + line_h <= choices_start_limit - self.ui(4):
            text = self.small_font.render("…", True, (170, 165, 155))
            surface.blit(text, (pad, y))
            y += line_h

        y = max(y + self.ui(8), choices_start_limit)
        for index, (_key, label, detail) in enumerate(options):
            choice_rect = pygame.Rect(pad, y, available_w, choice_h)
            pygame.draw.rect(
                surface,
                (24, 19, 30, 238),
                choice_rect,
                border_radius=self.ui(8),
            )
            pygame.draw.rect(
                surface,
                (*accent, 150),
                choice_rect,
                self.ui(1),
                border_radius=self.ui(8),
            )
            key_rect = pygame.Rect(
                choice_rect.x + self.ui(8),
                choice_rect.y + self.ui(8),
                self.ui(36),
                choice_rect.height - self.ui(16),
            )
            pygame.draw.rect(
                surface,
                (*self.shade(accent, -50), 235),
                key_rect,
                border_radius=self.ui(6),
            )
            key = self.font.render(str(index + 1), True, accent)
            surface.blit(key, key.get_rect(center=key_rect.center))
            label_text = self.small_font.render(label, True, (246, 235, 210))
            surface.blit(
                label_text, (choice_rect.x + self.ui(54), choice_rect.y + self.ui(8))
            )
            detail_text = self.small_font.render(detail, True, (178, 174, 164))
            surface.blit(
                detail_text, (choice_rect.x + self.ui(54), choice_rect.y + self.ui(30))
            )
            y += choice_h + choice_gap

        footer = self.small_font.render(
            "Press 1-3 to confirm the guest dialog, place the relic, and begin this level.",
            True,
            (205, 185, 225),
        )
        surface.blit(footer, (pad, panel_h - pad - footer.get_height()))
        self.screen.blit(surface, rect)

    def draw_ui(self) -> None:
        width, height = self.screen.get_size()
        panel_h = self.ui(112)
        margin = self.ui(22)
        panel = pygame.Rect(0, height - panel_h, width, panel_h)
        pygame.draw.rect(self.screen, (14, 14, 18), panel)
        pygame.draw.line(
            self.screen,
            (75, 65, 54),
            (0, height - panel_h),
            (width, height - panel_h),
            self.ui(2),
        )

        self.draw_bar(
            margin,
            height - self.ui(92),
            self.ui(230),
            self.ui(20),
            self.player.hp,
            self.player.max_hp,
            (185, 46, 46),
            "HP",
        )
        self.draw_bar(
            margin,
            height - self.ui(64),
            self.ui(230),
            self.ui(16),
            self.player.mana,
            self.player.max_mana,
            (54, 102, 210),
            "Mana",
        )
        self.draw_bar(
            margin,
            height - self.ui(40),
            self.ui(230),
            self.ui(16),
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
        lines = [
            self.player.class_name,
            f"Level {self.player.level}  XP {self.player.xp}/{self.player.next_xp}  Upgrades {len(self.player.skill_upgrades)}",
            f"Weapon: {weapon}  Damage: {self.player.melee_damage()}",
            f"Armor: {armor}  DR: {self.player.armor()}",
        ]
        for i, line in enumerate(lines):
            text = self.small_font.render(line, True, (220, 215, 200))
            self.screen.blit(
                text, (self.ui(280), height - self.ui(100) + i * self.ui(24))
            )

        self.draw_run_header()
        self.draw_story_panel()
        self.draw_boss_bar()

        objective = (
            "Objective: find the stairs to descend deeper"
            if self.current_depth < DUNGEON_DEPTH
            else "Objective: defeat the gate tyrant, then reach the stairs"
        )
        hint = self.current_interaction_hint()
        if hint:
            _key, title, _detail, _color = hint
            objective = title
        text = self.font.render(objective, True, self.theme.accent)
        self.screen.blit(
            text, (width - text.get_width() - self.ui(24), height - self.ui(98))
        )
        self.draw_interaction_prompt(hint)
        melee_name, bolt_name, nova_name, dash_name = self.skill_names()
        skill_line = (
            f"Skills: Space {melee_name} | F {bolt_name} {self.player.bolt_timer:.1f}s | "
            f"C {nova_name} {self.player.nova_timer:.1f}s | Shift {dash_name} {self.player.dash_timer:.1f}s"
        )
        control_lines = [
            "Hold Left Mouse to move/aim and slash nearby enemies | E interact | I inventory | Q potion | H help",
            skill_line,
        ]
        for i, controls in enumerate(control_lines):
            text = self.small_font.render(controls, True, (170, 165, 155))
            self.screen.blit(
                text,
                (
                    width - text.get_width() - self.ui(24),
                    height - self.ui(54) + i * self.ui(22),
                ),
            )

    def draw_interaction_prompt(self, hint: tuple[str, str, str, Color] | None) -> None:
        if not hint:
            return
        key, title, detail, color = hint
        width, height = self.screen.get_size()
        prompt_w = min(width - self.ui(40), self.ui(560))
        prompt_h = self.ui(58)
        rect = pygame.Rect(
            width - prompt_w - self.ui(24),
            height - self.ui(164),
            prompt_w,
            prompt_h,
        )
        surface = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(
            surface, (12, 11, 14, 224), surface.get_rect(), border_radius=self.ui(8)
        )
        pygame.draw.rect(
            surface,
            (*color, 180),
            surface.get_rect(),
            self.ui(1),
            border_radius=self.ui(8),
        )
        key_rect = pygame.Rect(
            self.ui(10), self.ui(9), self.ui(44), prompt_h - self.ui(18)
        )
        pygame.draw.rect(
            surface, (*self.shade(color, -55), 236), key_rect, border_radius=self.ui(6)
        )
        pygame.draw.rect(
            surface, (*color, 230), key_rect, self.ui(1), border_radius=self.ui(6)
        )
        key_surface = self.font.render(key, True, color)
        surface.blit(key_surface, key_surface.get_rect(center=key_rect.center))
        title_surface = self.small_font.render(title, True, (245, 238, 216))
        detail_surface = self.small_font.render(detail, True, (178, 174, 164))
        surface.blit(title_surface, (self.ui(66), self.ui(8)))
        surface.blit(detail_surface, (self.ui(66), self.ui(30)))
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
        title = f"Run {self.run_number}: Depth {self.current_depth}/{DUNGEON_DEPTH} — {self.theme.name}"
        modifier = (
            f"Modifier: {self.run_modifier.name} — {self.run_modifier.description}"
        )
        story = self.story_header_line()
        if len(story) > 112:
            story = story[:109] + "..."
        title_surface = self.font.render(title, True, self.theme.accent)
        modifier_surface = self.small_font.render(modifier, True, (205, 200, 190))
        story_surface = self.small_font.render(story, True, (205, 185, 225))
        self.screen.blit(title_surface, (self.ui(20), self.ui(18)))
        self.screen.blit(modifier_surface, (self.ui(20), self.ui(48)))
        self.screen.blit(story_surface, (self.ui(20), self.ui(72)))

    def draw_boss_bar(self) -> None:
        boss = self.boss_enemy()
        if not boss:
            return
        width, _height = self.screen.get_size()
        bar_w = self.ui(520)
        bar_h = self.ui(16)
        x = (width - bar_w) // 2
        y = self.ui(22)
        fill = int(bar_w * max(0, boss.hp) / boss.max_hp)
        pygame.draw.rect(self.screen, (28, 10, 14), (x, y, bar_w, bar_h))
        pygame.draw.rect(self.screen, self.theme.accent, (x, y, fill, bar_h))
        pygame.draw.rect(self.screen, (190, 160, 115), (x, y, bar_w, bar_h), self.ui(1))
        label = self.small_font.render(boss.name, True, (245, 235, 215))
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
        pygame.draw.rect(self.screen, (35, 32, 35), (x, y, w, h))
        fill = int(w * max(0.0, min(1.0, value / max_value)))
        pygame.draw.rect(self.screen, color, (x, y, fill, h))
        pygame.draw.rect(self.screen, (95, 88, 82), (x, y, w, h), self.ui(1))
        text = self.small_font.render(
            f"{label} {int(value)}/{int(max_value)}", True, (245, 240, 230)
        )
        self.screen.blit(text, text.get_rect(center=(x + w // 2, y + h // 2)))

    def draw_inventory(self) -> None:
        self.menus.draw_inventory()

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
        return [
            f"Time {minutes:02d}:{seconds:02d}  Depth {self.current_depth}/{DUNGEON_DEPTH}  Modifier {self.run_modifier.name}",
            f"Kills {self.run_stats.kills}  Boss {'defeated' if self.run_stats.boss_killed else 'alive'}  Damage taken {self.run_stats.damage_taken}",
            f"Loot {self.run_stats.loot_picked_up}  Potions {self.run_stats.potions_used}  Shrines {self.run_stats.shrines_used}",
            f"Secrets {self.run_stats.secrets_opened}  Traps triggered {self.run_stats.traps_triggered}  Story choices {self.run_stats.story_choices}",
            f"Elites {self.run_stats.elites_killed}  Minibosses {self.run_stats.minibosses_killed}  Upgrades {self.run_stats.upgrades_chosen}",
        ]
