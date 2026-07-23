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
from collections import OrderedDict, deque
from typing import cast

import pygame

from ..constants import (
    DUNGEON_DEPTH,
    WALK_CYCLE_FRAMES,
    WALK_FRAME_RATE,
    TILE_H,
    TILE_W,
    WORLD_SCALE,
    SlashEffect,
)
from ..content import HUMANOID_ENEMY_NAMES
from ..mobile import optimize_immutable_alpha_surface
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
from ..story import (
    CutsceneActorAsset,
    SpriteAnimationFrameAsset,
    format_asset_text,
)
from arch_rogue.sprites import ResolvedSpriteFrame


class RenderingActorMixin:
    def draw_shopkeeper(self, shopkeeper: Shopkeeper) -> None:
        facing_x, facing_y, moving, loop_progress = self.friendly_npc_visual_state(
            shopkeeper
        )
        beat_lift, beat_accent = self.friendly_npc_beat_pulse(loop_progress, moving)
        body_lift = beat_lift * (1.1 if moving else 1.8)
        self.draw_shadow(
            shopkeeper.x,
            shopkeeper.y,
            32,
            12,
            moving=False,
            lift=body_lift,
        )
        sx, sy = self.world_to_screen(shopkeeper.x, shopkeeper.y)
        scale = WORLD_SCALE
        gold = (245, 205, 92)
        pulse = beat_accent

        ring = pygame.Surface((28 * scale, 12 * scale), pygame.SRCALPHA)
        pygame.draw.ellipse(
            ring,
            (*gold, int(55 + 45 * pulse)),
            ring.get_rect(),
            max(1, scale),
        )
        self.screen.blit(ring, ring.get_rect(center=(sx, sy + 5 * scale)))

        motion = self.friendly_npc_motion(shopkeeper)
        direction = self.actor_sprite_direction(
            facing_x,
            facing_y,
            previous=motion.sprite_direction,
        )
        motion.sprite_direction = direction
        frame = self.sprites.shopkeeper_visual(
            self.elapsed,
            direction=direction,
            moving=moving,
            dancing=not moving,
            clip_progress=loop_progress,
        )
        y_offset = 6.0 - body_lift
        if frame.is_asset:
            self.blit_resolved_sprite(
                frame, shopkeeper.x, shopkeeper.y, y_offset=y_offset
            )
        else:
            sprite = frame.surface
            self.screen.blit(
                sprite, sprite.get_rect(midbottom=(sx, sy + y_offset * scale))
            )

    def walk_offsets(self, actor: Player | Enemy) -> tuple[int, int]:
        sway, bob, _lean, _stretch = self.actor_animation(actor)
        return round(sway), round(bob)

    def walk_cycle_position(self, anim_time: float) -> float:
        """Continuous 0..1 position within the walk stride cycle.

        This is derived from the *exact* same expression the sprite atlas uses
        to pick the displayed walk frame (``anim_time * WALK_FRAME_RATE`` mod
        ``WALK_CYCLE_FRAMES``), so the whole-body bob/sway/lean advance in lock
        step with the cached frame instead of using an unrelated frequency.
        """
        return (
            (anim_time * WALK_FRAME_RATE)
            % WALK_CYCLE_FRAMES
            / WALK_CYCLE_FRAMES
        )

    def actor_animation(
        self, actor: Player | Enemy
    ) -> tuple[float, float, float, float]:
        if actor.moving:
            cycle_t = self.walk_cycle_position(actor.anim_time)
            phase = cycle_t * math.tau
            footfall = 0.5 - 0.5 * math.cos(phase)
            stride = math.sin(phase)
            # Grounded bob: signed around zero so the body dips at foot-plant
            # (footfall 0) and rises at mid-lift (footfall 1), reading as
            # weighted walking instead of a constant upward float.
            bob = (footfall - 0.5) * 1.2
            sway = stride * 0.55
            # Directional lean: tilt the top of the sprite a few degrees toward
            # the screen-space facing direction so the character leans into its
            # stride. The lean follows the facing vector (which snaps to the
            # input/aim direction every frame) rather than the gameplay-smoothed
            # move vector, so it changes consistently and immediately on a
            # direction change instead of easing slowly or stalling against a wall.
            vx, vy = self.iso_screen_direction(actor.facing_x, actor.facing_y)
            lean = max(-5.0, min(5.0, vx * 4.0))
            # Subtle vertical stretch: moving up-screen stretches slightly,
            # moving down-screen squashes slightly, for a natural feel.
            stretch = max(0.97, min(1.03, 1.0 + (-vy) * 0.02))
            return sway, bob, lean, stretch
        idle = math.sin(self.elapsed * 2.2 + actor.x * 0.7 + actor.y * 0.4)
        return 0.0, idle * 0.32, idle * 0.08, 1.0

    def iso_screen_direction(self, dx: float, dy: float) -> tuple[float, float]:
        screen_dx = (dx - dy) * TILE_W / 2
        screen_dy = (dx + dy) * TILE_H / 2
        length = math.hypot(screen_dx, screen_dy)
        if length <= 0.001:
            return 1.0, 0.0
        return screen_dx / length, screen_dy / length

    def actor_sprite_direction(
        self, dx: float, dy: float, *, previous: str = ""
    ) -> str:
        """Quantize facing with a small render-only directional hysteresis."""
        screen_x, screen_y = self.iso_screen_direction(dx, dy)
        angle = math.degrees(math.atan2(screen_y, screen_x))
        directions = (
            "east",
            "south-east",
            "south",
            "south-west",
            "west",
            "north-west",
            "north",
            "north-east",
        )
        if previous in directions:
            previous_angle = directions.index(previous) * 45.0
            delta = (angle - previous_angle + 180.0) % 360.0 - 180.0
            if abs(delta) <= 27.5:
                return previous
        return directions[round(angle / 45.0) % len(directions)]

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
        x_offset: float = 0.0,
        stretch: float = 1.0,
        lean: float = 0.0,
        alpha: int = 255,
        apply_shading: bool = True,
        base_sprite: pygame.Surface | None = None,
    ) -> tuple[int, int]:
        sx, sy = self.world_to_screen(x, y)
        turned_sprite = sprite
        # Milestone 3.16 - lit-actor shading is applied to the untransformed
        # frame (so the cached base-sprite tint aligns) BEFORE stretch/lean;
        # the transforms then carry the shading with the sprite.
        if apply_shading and base_sprite is not None:
            shaded = self.apply_lit_shading(sprite, base_sprite, x, y)
            if shaded is not sprite:
                turned_sprite = shaded
        if abs(stretch - 1.0) > 0.018:
            turned_sprite = pygame.transform.scale(
                turned_sprite,
                (
                    max(1, round(turned_sprite.get_width() / stretch)),
                    max(1, round(turned_sprite.get_height() * stretch)),
                ),
            )
        if abs(lean) > 1.0:
            # ``lean`` is signed by the screen-space movement direction
            # (positive = moving screen-right); a consistent rotation tilts
            # the top toward where the character is moving. The sprite is
            # never mirror-flipped on facing changes.
            turned_sprite = pygame.transform.rotate(turned_sprite, -lean)
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

    def blit_resolved_sprite(
        self,
        frame: ResolvedSpriteFrame,
        x: float,
        y: float,
        *,
        y_offset: float = 0.0,
        x_offset: float = 0.0,
        alpha: int = 255,
        apply_shading: bool = True,
    ) -> pygame.Rect:
        sx, sy = self.world_to_screen(x, y)
        sprite = frame.surface
        if apply_shading:
            shaded = self.apply_lit_shading(sprite, sprite, x, y)
            if shaded is not sprite:
                sprite = shaded
        if alpha < 255:
            sprite = sprite.copy()
            sprite.set_alpha(alpha)
        rect = sprite.get_rect(
            topleft=(
                round(sx + x_offset * WORLD_SCALE - frame.anchor[0]),
                round(sy + y_offset * WORLD_SCALE - frame.anchor[1]),
            )
        )
        self.screen.blit(sprite, rect)
        return rect

    def _player_is_local(self, player: Player) -> bool:
        return (
            not getattr(self, "mp_active", False)
            or player.player_id == self.local_player_id
        )

    def player_death_clip_seconds(self, player: Player) -> float:
        seconds = self.sprites.actor_clip_seconds(player.class_name, "die")
        return seconds if seconds else 1.0

    def player_visual_state(self, player: Player) -> str:
        if player.hp <= 0:
            # Death trumps every other pose, including the killing blow's
            # hit flash: the one-shot "die" clip, then the corpse idle.
            if player.death_anim_time < self.player_death_clip_seconds(player):
                return "die"
            return "dead"
        if self._player_is_local(player):
            if getattr(self, "player_hit_flash", 0.0) > 0.0:
                return "hit"
            action_state = getattr(self, "player_action_state", "")
            if getattr(self, "player_action_ttl", 0.0) > 0.0 and action_state:
                return action_state
            return "walk" if player.moving else "idle"
        # 4.6: a network partner's pose comes from its own transient fields
        # (applied from snapshots on the joiner, intents on the host).
        if player.hit_flash > 0.0:
            return "hit"
        if player.action_ttl > 0.0 and player.action_state:
            return player.action_state
        return "walk" if player.moving else "idle"

    def enemy_visual_state(self, enemy: Enemy) -> str:
        if getattr(self, "enemy_hit_flashes", {}).get(id(enemy), 0.0) > 0.0:
            return "hit"
        just_attacked = enemy.attack_timer > max(0.0, enemy.attack_cooldown - 0.22)
        if just_attacked and enemy.telegraph == "cast":
            return "cast"
        if just_attacked and enemy.telegraph == "melee":
            return "attack"
        return "walk" if enemy.moving else "idle"

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

    def _mobile_windup_ring(
        self,
        size: tuple[int, int],
        color: Color,
        alpha: int,
        radius: int,
        width: int,
    ) -> pygame.Surface:
        cache = getattr(self, "_mobile_windup_ring_cache", None)
        if not isinstance(cache, OrderedDict):
            cache = OrderedDict()
            self._mobile_windup_ring_cache = cache
        key = (size, color, alpha, radius, width)
        cached = cache.get(key)
        if cached is not None:
            cache.move_to_end(key)
            return cached

        overlay = pygame.Surface(size, pygame.SRCALPHA)
        ring_rect = pygame.Rect(0, 0, radius * 2, radius * 2)
        ring_rect.center = overlay.get_rect().center
        segments = 32
        visible = max(0, min(segments, round(segments * alpha / 120.0)))
        for index in range(segments):
            # Multiplicative permutation distributes retained dashes uniformly
            # instead of erasing one contiguous side as the telegraph fades.
            if (index * 13) % segments >= visible:
                continue
            start = index * math.tau / segments
            end = (index + 0.82) * math.tau / segments
            pygame.draw.arc(
                overlay,
                (*color, 255),
                ring_rect,
                start,
                end,
                width,
            )
        overlay = optimize_immutable_alpha_surface(overlay)
        cache[key] = overlay
        cache.move_to_end(key)
        while len(cache) > 192:
            cache.popitem(last=False)
        return overlay

    def draw_windup_telegraph(self, enemy: Enemy, sx: int, sy: int) -> None:
        """Pre-attack windup telegraph: a fading ring while an enemy winds up.

        Driven by ``enemy.windup_time`` (set by ``_commit_enemy_attack`` in the
        ``update_enemies`` AI loop, decayed each frame, fired on completion). The
        attack lands AFTER the windup -- this is the readability win -- so the
        ring gives the player a window to react with abilities (evade/block).
        Color follows the enemy's damage type so the telegraph reads as the same
        flavor as the incoming hit.
        """
        ttl = enemy.windup_time
        if ttl <= 0.0:
            return
        duration = max(0.01, enemy.windup_duration)
        life = max(0.0, min(1.0, ttl / duration))
        color = self.damage_type_color(enemy.damage_type)
        # Expanding ring: grows outward as the swing follows through, fading
        # with the remaining telegraph time. Android spell crowds used to allocate
        # and rasterize one alpha surface per winding-up enemy per frame. Quantize
        # only the mobile animation and reuse the shared outlined-circle cache;
        # twelve states still cover a typical windup at near frame cadence.
        if getattr(self, "mobile_mode", False):
            life = round(life * 12.0) / 12.0
        base = 10 * WORLD_SCALE
        radius = int(base + (1.0 - life) * 10 * WORLD_SCALE)
        alpha = int(120 * life)
        if getattr(self, "mobile_mode", False):
            radius = max(base, round(radius / WORLD_SCALE) * WORLD_SCALE)
            alpha = max(0, min(120, round(alpha / 8) * 8))
        size = (radius * 2 + 8 * WORLD_SCALE, radius * 2 + 8 * WORLD_SCALE)
        line_width = max(1, WORLD_SCALE * 2)
        if getattr(self, "mobile_mode", False):
            overlay = self._mobile_windup_ring(
                size, color, alpha, radius, line_width
            )
        else:
            overlay = self._cached_circle_overlay(
                "enemy_windup",
                size,
                color,
                alpha,
                radius,
                line_width,
            )
        self.screen.blit(overlay, overlay.get_rect(center=(sx, sy)))

    def draw_garden_heal_glow(self, sx: int, sy: int, width: int, height: int) -> None:
        # 4.2: greenish aura that fades in around the player after each garden
        # room healing tick. ``garden_heal_glow`` is a transient timer set by
        # ``CombatMixin._update_garden_healing`` and decayed in
        # ``Game.update_visual_effects``. The aura is drawn beneath the
        # sprite's centerline as a soft pulsing ring so it reads as warmth
        # rising from the overgrown garden floor rather than a flat flash.
        ttl = getattr(self, "garden_heal_glow", 0.0)
        if ttl <= 0.0:
            return
        duration = max(0.01, getattr(self, "garden_heal_glow_duration", 0.9))
        life = max(0.0, min(1.0, ttl / duration))
        pulse = 0.5 + 0.5 * math.sin(self.elapsed * 6.0)
        aura_w = width + int(18 * WORLD_SCALE) + int(6 * WORLD_SCALE * pulse)
        aura_h = height + int(14 * WORLD_SCALE) + int(4 * WORLD_SCALE * pulse)
        overlay = pygame.Surface((aura_w, aura_h), pygame.SRCALPHA)
        overlay_rect = overlay.get_rect()
        # Outer halo: a wide, low-alpha green wash.
        halo_color = (130, 220, 150)
        pygame.draw.ellipse(
            overlay,
            (*halo_color, int(46 * life)),
            overlay_rect.inflate(-overlay_rect.width // 6, -overlay_rect.height // 6),
        )
        # Inner ring: a brighter, tighter band to read as a healing pulse.
        ring_rect = overlay_rect.inflate(
            -overlay_rect.width // 3, -overlay_rect.height // 3
        )
        pygame.draw.ellipse(
            overlay,
            (*self.shade(halo_color, 28), int(96 * life)),
            ring_rect,
            max(1, WORLD_SCALE * 2),
        )
        # Soft rising sparks: four short vertical wisps rotating slowly to
        # evoke leaves/petals drifting up from the garden floor.
        for index in range(4):
            angle = self.elapsed * 2.4 + index * math.tau / 4
            radius_x = overlay_rect.width * 0.30
            radius_y = overlay_rect.height * 0.22
            cx = overlay_rect.centerx + int(math.cos(angle) * radius_x)
            cy = overlay_rect.centery + int(math.sin(angle) * radius_y)
            spark_h = int(10 * WORLD_SCALE * (0.6 + 0.4 * pulse))
            pygame.draw.line(
                overlay,
                (*halo_color, int(120 * life)),
                (cx, cy),
                (cx, cy - spark_h),
                max(1, WORLD_SCALE),
            )
        self.screen.blit(overlay, overlay.get_rect(center=(sx, sy - height // 2)))

    def draw_player(self, player: Player) -> None:
        sway, bob, lean, stretch = self.actor_animation(player)
        state = self.player_visual_state(player)
        direction = self.actor_sprite_direction(
            player.facing_x,
            player.facing_y,
            previous=player.sprite_direction,
        )
        player.sprite_direction = direction
        is_local = self._player_is_local(player)
        if is_local:
            action_elapsed = getattr(self, "player_action_elapsed", 0.0)
            action_duration = getattr(self, "player_action_duration", 0.0)
            hit_flash_ttl = getattr(self, "player_hit_flash", 0.0)
            hit_flash_duration = getattr(
                self, "player_hit_flash_duration", hit_flash_ttl
            )
        else:
            action_elapsed = player.action_elapsed
            action_duration = player.action_duration
            hit_flash_ttl = player.hit_flash
            hit_flash_duration = player.hit_flash_duration
        if state == "hit":
            hit_ttl = max(0.0, hit_flash_ttl)
            action_duration = max(0.01, hit_flash_duration or hit_ttl)
            action_elapsed = max(0.0, action_duration - hit_ttl)
        elif state in ("die", "dead"):
            # Clip time comes straight from the death timer (the "dead" loop
            # starts where the one-shot "die" clip ended); frame stepping is
            # driven by the manifest fps, so no progress override is needed.
            die_seconds = self.player_death_clip_seconds(player)
            action_elapsed = (
                player.death_anim_time
                if state == "die"
                else max(0.0, player.death_anim_time - die_seconds)
            )
            action_duration = 0.0
            hit_flash_ttl = 0.0
        action_progress = (
            max(0.0, min(1.0, action_elapsed / action_duration))
            if action_duration > 0.0
            else None
        )
        frame = self.sprites.player_visual(
            player.class_name,
            state,
            player.anim_time,
            self.elapsed,
            direction=direction,
            action_time=action_elapsed,
            action_progress=action_progress,
        )
        sprite = frame.surface
        if frame.is_asset:
            self.draw_shadow(player.x, player.y, 34, 13, moving=player.moving)
            rect = self.blit_resolved_sprite(frame, player.x, player.y, y_offset=6.0)
            sx = rect.centerx
            _ground_x, sy = self.world_to_screen(player.x, player.y)
        else:
            self.draw_shadow(player.x, player.y, 34, 13, moving=player.moving, lift=bob)
            sx, sy = self.blit_sprite(
                sprite,
                player.x,
                player.y,
                y_offset=6.0 - bob,
                x_offset=sway,
                stretch=stretch,
                lean=lean,
                base_sprite=self.sprites.legacy_player_base(player.class_name),
            )
        self.draw_hit_flash_overlay(
            sx,
            sy,
            sprite.get_width(),
            sprite.get_height(),
            hit_flash_ttl,
            (255, 110, 90),
        )
        if is_local:
            # 4.2: garden healing aura. Drawn after the hit flash so a recent
            # hit does not mask the green tint, and lazily skipped when no glow
            # timer is active (the common case in non-garden floors).
            self.draw_garden_heal_glow(
                sx,
                sy,
                sprite.get_width(),
                sprite.get_height(),
            )
        elif player.display_name:
            # A network partner carries their chosen name overhead so two
            # same-archetype descenders stay tellable-apart.
            label = self._cached_text_surface(
                self.tiny_font, player.display_name, (222, 210, 176)
            )
            self.screen.blit(
                label,
                (
                    sx - label.get_width() // 2,
                    sy - sprite.get_height() - label.get_height() - 4,
                ),
            )

    def draw_aim_cone(self) -> None:
        if self.player.hp <= 0:
            return
        sx, sy = self.world_to_screen(self.player.x, self.player.y)
        raw_vx, raw_vy = self.iso_screen_direction(
            self.player.facing_x, self.player.facing_y
        )
        mobile_fast = bool(getattr(self, "mobile_mode", False))
        bucket_count = 32 if mobile_fast else 64
        raw_angle = math.atan2(raw_vy, raw_vx)
        direction_bucket = int(
            round(raw_angle / math.tau * bucket_count)
        ) % bucket_count
        bucket_width = math.tau / bucket_count
        previous_bucket = getattr(self, "_aim_cone_direction_bucket", None)
        if (
            isinstance(previous_bucket, tuple)
            and len(previous_bucket) == 2
            and previous_bucket[0] == bucket_count
        ):
            previous_index = int(previous_bucket[1]) % bucket_count
            previous_angle = previous_index * bucket_width
            angle_delta = (
                (raw_angle - previous_angle + math.pi) % math.tau
            ) - math.pi
            if abs(angle_delta) <= bucket_width * 0.62:
                direction_bucket = previous_index
        self._aim_cone_direction_bucket = (bucket_count, direction_bucket)
        bucket_angle = direction_bucket * bucket_width
        vx, vy = math.cos(bucket_angle), math.sin(bucket_angle)
        px, py = -vy, vx
        aim_blue = self.mix((92, 170, 255), self.theme.accent, 0.18)
        modern_aim = self.sprites.modern_graphics_active
        cone_alpha = 28 if modern_aim else 14

        # Touch and analog aim produce effectively continuous vectors. Quantize
        # only this visual indicator (gameplay aim remains exact), otherwise tiny
        # camera/finger changes rebuild three blurred surfaces every frame and grow
        # an unbounded cache. Mobile uses a cheaper pixel-art cone; desktop keeps
        # the soft blur at finer angular resolution.
        raw_cache = getattr(self, "_aim_cone_cache", None)
        if isinstance(raw_cache, OrderedDict):
            cache = raw_cache
        else:
            cache = OrderedDict(raw_cache.items() if isinstance(raw_cache, dict) else ())
            self._aim_cone_cache = cache
        cone_key = (
            modern_aim,
            aim_blue,
            mobile_fast,
            bucket_count,
            direction_bucket,
        )
        cached = cache.get(cone_key)

        if cached is None:
            self._aim_cone_cache_misses = int(
                getattr(self, "_aim_cone_cache_misses", 0)
            ) + 1
            # Build the cone in a facing-local space (origin at 0,0) so the
            # same surface is reusable across player positions.
            local_origin = (0.0, 0.0)

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
                            local_origin[0] + (vx * forward + px * side) * radius,
                            local_origin[1] + (vy * forward + py * side) * radius,
                        )
                    )
                return points

            def cone_points(
                length: float,
                half_angle: float,
                start_length: float = 0.0,
                samples: int = 24,
            ) -> list[tuple[float, float]]:
                # Truncated cone: when start_length > 0 the apex is cut away so
                # the overlay no longer originates straight from the player.
                if start_length <= 0.0:
                    return [local_origin] + arc_points(length, half_angle, samples)
                far = arc_points(length, half_angle, samples)
                near = arc_points(start_length, half_angle, samples)
                return far + near[::-1]

            # Halved cone size (0.5x) with a forward cutout so it starts away
            # from the player body instead of at the player origin.
            cutout = 16.0
            bounds_points = cone_points(61.0, 0.21, cutout, 28)
            pad = (3 if mobile_fast else 18) * WORLD_SCALE
            min_x = math.floor(min(point[0] for point in bounds_points) - pad)
            max_x = math.ceil(max(point[0] for point in bounds_points) + pad)
            min_y = math.floor(min(point[1] for point in bounds_points) - pad)
            max_y = math.ceil(max(point[1] for point in bounds_points) + pad)
            width = max(1, max_x - min_x)
            height = max(1, max_y - min_y)
            supersample = 1 if mobile_fast else 3
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

            for length, angle, alpha, start in (
                (60.5, 0.21, cone_alpha, cutout),
            ):
                pygame.draw.polygon(
                    overlay,
                    (*aim_blue, alpha),
                    localize(cone_points(length, angle, start, 30)),
                )

            if not mobile_fast:
                overlay = pygame.transform.smoothscale(overlay, (width, height))
                # Soft blur pass: downscale then upscale to feather the edges and
                # make the cone read as a subtle glow rather than a hard shape.
                blur_w = max(1, width // 3)
                blur_h = max(1, height // 3)
                overlay = pygame.transform.smoothscale(overlay, (blur_w, blur_h))
                overlay = pygame.transform.smoothscale(overlay, (width, height))
            overlay = optimize_immutable_alpha_surface(overlay)
            # Anchor: the local origin (0,0) maps to pixel (-min_x, -min_y)
            # within the surface. Store that anchor so the blit can place it
            # relative to the player's screen position.
            anchor_x = -min_x
            anchor_y = -min_y
            cached = (overlay, anchor_x, anchor_y, width, height)
            cache[cone_key] = cached
            cache.move_to_end(cone_key)
            cache_limit = 36 if mobile_fast else 72
            while len(cache) > cache_limit:
                cache.popitem(last=False)
        else:
            self._aim_cone_cache_hits = int(
                getattr(self, "_aim_cone_cache_hits", 0)
            ) + 1
            cache.move_to_end(cone_key)

        overlay, anchor_x, anchor_y, _w, _h = cached
        # Player screen position offset by the same origin offset used in the
        # original absolute-space cone (vx*14*WORLD_SCALE, -8*WORLD_SCALE+vy*6).
        blit_x = int(sx + vx * 14 * WORLD_SCALE - anchor_x)
        blit_y = int(sy - 8 * WORLD_SCALE + vy * 6 * WORLD_SCALE - anchor_y)
        self.screen.blit(overlay, (blit_x, blit_y))

    def draw_enemy(self, enemy: Enemy) -> None:
        base_name = self.sprites.enemy_key(enemy.name, enemy.kind)
        state = self.enemy_visual_state(enemy)
        big_boss = enemy.is_boss_encounter and enemy.size >= 2
        direction = self.actor_sprite_direction(
            enemy.facing_x,
            enemy.facing_y,
            previous=enemy.sprite_direction,
        )
        enemy.sprite_direction = direction
        action_time = max(0.0, enemy.attack_cooldown - enemy.attack_timer)
        action_progress = None
        if state == "hit":
            enemy_id = id(enemy)
            hit_ttl = max(0.0, self.enemy_hit_flashes.get(enemy_id, 0.0))
            hit_duration = max(
                0.01,
                self.enemy_hit_flash_durations.get(enemy_id, hit_ttl),
            )
            action_time = max(0.0, hit_duration - hit_ttl)
            action_progress = min(1.0, action_time / hit_duration)
        frame = self.sprites.enemy_visual(
            enemy.name,
            enemy.kind,
            state,
            enemy.anim_time,
            self.elapsed,
            direction=direction,
            action_time=action_time,
            action_progress=action_progress,
        )
        sprite = frame.surface
        if big_boss and not frame.is_asset:
            # Legacy tyrants were authored smaller and retain their established
            # encounter scale. Asset bosses have per-identity target heights.
            sprite = pygame.transform.smoothscale(
                sprite,
                (int(sprite.get_width() * 1.18), int(sprite.get_height() * 1.18)),
            )
            frame = ResolvedSpriteFrame(
                sprite,
                (sprite.get_width() // 2, sprite.get_height()),
                "legacy",
                frame.key,
            )
        shadow_w = (
            78
            if big_boss
            else 44
            if enemy.kind == "boss"
            else 38
            if base_name == "Gate Warden"
            else 32
        )
        if frame.is_asset:
            sway, bob, lean, stretch = 0.0, 0.0, 0.0, 1.0
        else:
            sway, bob, lean, stretch = self.actor_animation(enemy)
        if not frame.is_asset and (big_boss or enemy.kind == "boss"):
            stretch += math.sin(self.elapsed * 3.4) * 0.010
            lean += math.sin(self.elapsed * 2.1) * 1.5
        elif not frame.is_asset and (
            enemy.elite_modifier or enemy.kind == "miniboss"
        ):
            stretch += math.sin(self.elapsed * 5.0) * 0.006
            lean += math.sin(self.elapsed * 5.0) * 0.6
        ordinary_enemy = bool(
            not big_boss
            and enemy.kind not in ("boss", "miniboss")
            and not enemy.elite_modifier
        )
        if not (
            ordinary_enemy
            and getattr(self, "_frame_mobile_dense_enemy_render", False)
        ):
            self.draw_shadow(
                enemy.x,
                enemy.y,
                shadow_w,
                18 if big_boss else 12,
                moving=enemy.moving,
                lift=bob,
            )
        # Big bosses sit a little lower in their footprint so the sprite base
        # lands near the center of the 2x2 block instead of the center tile.
        y_off = (10.0 if big_boss else 6.0) - bob
        if frame.is_asset:
            rect = self.blit_resolved_sprite(
                frame,
                enemy.x,
                enemy.y,
                y_offset=y_off,
                apply_shading=(enemy.kind == "boss" or big_boss),
            )
            sx = rect.centerx
            _ground_x, sy = self.world_to_screen(enemy.x, enemy.y)
        else:
            sx, sy = self.blit_sprite(
                sprite,
                enemy.x,
                enemy.y,
                y_offset=y_off,
                x_offset=sway,
                stretch=stretch,
                lean=lean,
                apply_shading=(enemy.kind == "boss"),
                base_sprite=self.sprites.legacy_enemy_base(enemy.name, enemy.kind),
            )
            rect = sprite.get_rect(midbottom=(sx, sy + round(y_off * WORLD_SCALE)))
        self.draw_hit_flash_overlay(
            sx,
            sy,
            sprite.get_width(),
            sprite.get_height(),
            getattr(self, "enemy_hit_flashes", {}).get(id(enemy), 0.0),
            enemy.color,
        )
        self.draw_windup_telegraph(enemy, sx, sy)
        bar_w = (
            96
            if big_boss
            else 46
            if enemy.kind == "boss"
            else 34
            if base_name == "Gate Warden"
            else 28
        ) * WORLD_SCALE
        bar_h = (7 if big_boss else 4) * WORLD_SCALE
        bar_y = rect.top - (4 if big_boss else 2) * WORLD_SCALE
        status_entries = [
            status
            for status, ttl in getattr(enemy, "statuses", {}).items()
            if ttl > 0 and not status.startswith("_")
        ]
        show_health_bar = bool(
            enemy.hp < enemy.max_hp
            or big_boss
            or enemy.kind in ("boss", "miniboss")
            or enemy.elite_modifier
            or status_entries
        )
        if show_health_bar:
            fill_w = int(bar_w * max(0, enemy.hp) / enemy.max_hp)
            pygame.draw.rect(
                self.screen, (40, 10, 10), (sx - bar_w // 2, bar_y, bar_w, bar_h)
            )
            pygame.draw.rect(
                self.screen, (215, 62, 52), (sx - bar_w // 2, bar_y, fill_w, bar_h)
            )
            if big_boss:
                # Gilded frame around the boss's floating health bar so it reads
                # as a named encounter, not just a tougher enemy.
                pygame.draw.rect(
                    self.screen,
                    self.theme.accent,
                    (sx - bar_w // 2, bar_y, bar_w, bar_h),
                    max(1, WORLD_SCALE),
                )
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
        if enemy.telegraph == "lured":
            lure_color = self.damage_type_color("shadow")
            pulse = 0.5 + 0.5 * math.sin(self.elapsed * 10.0 + enemy.x)
            marker_y = sy - (30 if big_boss else 22) * WORLD_SCALE
            pygame.draw.circle(
                self.screen,
                (*lure_color, int(80 + pulse * 80)),
                (sx, marker_y),
                max(3, int((3 + pulse * 2) * WORLD_SCALE)),
                max(1, WORLD_SCALE),
            )
            pygame.draw.line(
                self.screen,
                self.shade(lure_color, 45),
                (sx - 4 * WORLD_SCALE, marker_y - 2 * WORLD_SCALE),
                (sx + 4 * WORLD_SCALE, marker_y - 2 * WORLD_SCALE),
                max(1, WORLD_SCALE),
            )
        if enemy.elite_modifier or enemy.kind == "miniboss":
            pulse = 0.5 + 0.5 * math.sin(self.elapsed * 5.2)
            marker_w = (96 if big_boss else 46) * WORLD_SCALE
            marker_h = (34 if big_boss else 20) * WORLD_SCALE
            marker = self._cached_ellipse_overlay(
                "elite_marker",
                (marker_w, marker_h),
                enemy.color,
                (int(28 + pulse * 48) // 8) * 8,
                outer_width=max(1, WORLD_SCALE),
                inner_color=self.shade(enemy.color, 45),
                inner_alpha=(int(16 + pulse * 30) // 8) * 8,
                inner_inflate=(-marker_w // 3, -marker_h // 3),
            )
            self.screen.blit(
                marker,
                marker.get_rect(
                    center=(sx, sy - (22 if big_boss else 14) * WORLD_SCALE)
                ),
            )
            label_color = self.theme.accent if big_boss else enemy.color
            label_font = self.small_font
            label = self._cached_text_surface(
                label_font, enemy.elite_modifier, label_color
            )
            self.screen.blit(
                label, label.get_rect(center=(sx, bar_y - 8 * WORLD_SCALE))
            )
        if (
            enemy.windup_time <= 0.0
            and enemy.attack_timer <= 0.28
            and (enemy.kind in ("boss", "miniboss", "ranged") or big_boss)
        ):
            tell_color = (
                self.theme.accent
                if enemy.kind == "boss" or big_boss
                else self.damage_type_color(getattr(enemy, "damage_type", "physical"))
            )
            pulse = 0.55 + 0.45 * math.sin(self.elapsed * 18.0)
            tell_size = (64 if big_boss else 42) * WORLD_SCALE
            telegraph = self._cached_circle_overlay(
                "attack_telegraph",
                (tell_size, tell_size),
                tell_color,
                (int(82 + 92 * pulse) // 8) * 8,
                max(
                    3,
                    int((7 if big_boss else 5) * WORLD_SCALE + pulse * 3 * WORLD_SCALE),
                ),
                max(1, WORLD_SCALE),
            )
            self.screen.blit(
                telegraph,
                telegraph.get_rect(
                    center=(sx, sy - (28 if big_boss else 18) * WORLD_SCALE)
                ),
            )
            label = self._cached_text_surface(self.small_font, "!", tell_color)
            self.screen.blit(
                label,
                label.get_rect(
                    center=(sx, sy - (52 if big_boss else 35) * WORLD_SCALE)
                ),
            )
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
        if enemy.kind == "boss" or big_boss:
            pulse = 0.5 + 0.5 * math.sin(self.elapsed * 4.2)
            aura_w = (132 if big_boss else 74) * WORLD_SCALE
            aura_h = (52 if big_boss else 30) * WORLD_SCALE
            aura = self._cached_ellipse_overlay(
                "boss_aura",
                (aura_w, aura_h),
                self.theme.accent,
                (int(30 + pulse * 42) // 8) * 8,
                outer_width=max(1, WORLD_SCALE),
                inner_color=self.shade(self.theme.accent, 55),
                inner_alpha=(int(15 + pulse * 22) // 8) * 8,
                inner_inflate=(-aura_w // 3, -aura_h // 3),
            )
            self.screen.blit(
                aura,
                aura.get_rect(center=(sx, sy - (28 if big_boss else 18) * WORLD_SCALE)),
            )
