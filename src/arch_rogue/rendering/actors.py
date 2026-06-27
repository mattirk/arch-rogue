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


class RenderingActorMixin:
    def draw_shopkeeper(self, shopkeeper: Shopkeeper) -> None:
        self.draw_shadow(shopkeeper.x, shopkeeper.y, 32, 12)
        sx, sy = self.world_to_screen(shopkeeper.x, shopkeeper.y)
        scale = WORLD_SCALE
        gold = (245, 205, 92)
        pulse = 0.5 + 0.5 * math.sin(self.elapsed * 4.0 + shopkeeper.x + shopkeeper.y)

        ring = pygame.Surface((28 * scale, 12 * scale), pygame.SRCALPHA)
        pygame.draw.ellipse(
            ring,
            (*gold, int(55 + 45 * pulse)),
            ring.get_rect(),
            max(1, scale),
        )
        self.screen.blit(ring, ring.get_rect(center=(sx, sy + 5 * scale)))

        sprite = self.sprites.shopkeeper_frame(self.elapsed + shopkeeper.x * 0.17)
        self.screen.blit(sprite, sprite.get_rect(midbottom=(sx, sy + 6 * scale)))

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

