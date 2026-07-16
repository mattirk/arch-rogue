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
from collections import deque
from typing import cast

import pygame

from ..constants import DUNGEON_DEPTH, TILE_H, TILE_W, WORLD_SCALE, SlashEffect
from ..content import HUMANOID_ENEMY_NAMES
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
            self._draw_cast_emanation(
                overlay, center, radius, alpha, bright, dark, progress, life, effect
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
        elif effect.kind == "ambush_bell":
            snap_radius = max(3, int(radius * (0.30 + progress * 0.55)))
            smoke = self.mix(dark, (38, 30, 45), 0.55)
            pygame.draw.circle(overlay, (*smoke, int(alpha * 0.42)), center, snap_radius)
            pygame.draw.circle(
                overlay,
                (*bright, int(alpha * 0.32)),
                center,
                max(2, int(snap_radius * 0.55)),
                max(1, WORLD_SCALE),
            )
            for index in range(8):
                angle = index * math.tau / 8 + progress * 0.7
                inner = snap_radius * (0.20 + progress * 0.12)
                outer = snap_radius * (0.92 + progress * 0.35)
                start = (
                    center[0] + int(math.cos(angle) * inner),
                    center[1] + int(math.sin(angle) * inner * 0.55),
                )
                tip = (
                    center[0] + int(math.cos(angle) * outer),
                    center[1] + int(math.sin(angle) * outer * 0.55),
                )
                pygame.draw.line(overlay, (*bright, alpha), start, tip, max(1, WORLD_SCALE))
                side = angle + math.pi * 0.5
                barb = max(2, int(radius * 0.08))
                left = (
                    tip[0] - int(math.cos(angle) * barb) + int(math.cos(side) * barb * 0.45),
                    tip[1]
                    - int(math.sin(angle) * barb * 0.55)
                    + int(math.sin(side) * barb * 0.25),
                )
                right = (
                    tip[0] - int(math.cos(angle) * barb) - int(math.cos(side) * barb * 0.45),
                    tip[1]
                    - int(math.sin(angle) * barb * 0.55)
                    - int(math.sin(side) * barb * 0.25),
                )
                pygame.draw.polygon(overlay, (*self.shade(bright, 35), alpha), [tip, left, right])
            for index in range(5):
                angle = index * math.tau / 5 - progress * 1.3
                dist = snap_radius * (0.55 + progress * 0.55)
                puff = (
                    center[0] + int(math.cos(angle) * dist),
                    center[1] + int(math.sin(angle) * dist * 0.55) - int(progress * 8),
                )
                pygame.draw.circle(
                    overlay,
                    (*smoke, int(alpha * (0.24 - progress * 0.14))),
                    puff,
                    max(2, radius // 9),
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

    def _draw_cast_emanation(
        self,
        overlay: pygame.Surface,
        center: tuple[int, int],
        radius: int,
        alpha: int,
        bright: Color,
        dark: Color,
        progress: float,
        life: float,
        effect: ImpactEffect,
    ) -> None:
        """Archetype-themed emanation for bolt/nova cast impacts.

        The Arcanist keeps the classic arcane ring with orbiting runes. The
        other archetypes get distinct visuals that match their damage type and
        fantasy: Warden's holy bulwark wave, Rogue's smoke/poison burst,
        Acolyte's blood nova, and Ranger's snare-vine ring. Nova impacts use a
        larger radius/ttl so the same routine scales up automatically.
        """
        archetype = getattr(effect, "archetype", "")
        if archetype == "Warden":
            self._draw_cast_warden(
                overlay, center, radius, alpha, bright, dark, progress
            )
        elif archetype == "Rogue":
            self._draw_cast_rogue(
                overlay, center, radius, alpha, bright, dark, progress
            )
        elif archetype == "Acolyte":
            self._draw_cast_acolyte(
                overlay, center, radius, alpha, bright, dark, progress
            )
        elif archetype == "Ranger":
            self._draw_cast_ranger(
                overlay, center, radius, alpha, bright, dark, progress
            )
        else:
            # Arcanist (default): the classic magical ring with orbiting runes
            # and a bright arcane core.
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

    def _draw_cast_warden(
        self,
        overlay: pygame.Surface,
        center: tuple[int, int],
        radius: int,
        alpha: int,
        bright: Color,
        dark: Color,
        progress: float,
    ) -> None:
        # Holy bulwark wave: an expanding golden shield-disc front, radiating
        # light rays, and a holy sigil at the center.
        holy = bright
        ring_radius = max(3, int(radius * (0.40 + progress * 0.55)))
        # inner shield face (fades as the wave expands)
        face_alpha = int(alpha * 0.22 * (1.0 - progress))
        if face_alpha > 0:
            pygame.draw.circle(
                overlay, (*holy, face_alpha), center, max(2, ring_radius - 2)
            )
        # expanding wave front (thicker golden ring)
        pygame.draw.circle(
            overlay,
            (*holy, int(alpha * 0.55)),
            center,
            ring_radius,
            max(2, WORLD_SCALE * 2),
        )
        pygame.draw.circle(
            overlay,
            (*self.shade(holy, 40), int(alpha * 0.30)),
            center,
            max(2, ring_radius - 3),
            max(1, WORLD_SCALE),
        )
        # radiating light rays
        ray_count = 8
        for index in range(ray_count):
            angle = index * math.tau / ray_count + progress * 0.4
            inner = ring_radius * 0.18
            outer = ring_radius * (0.95 + progress * 0.15)
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
                (*bright, int(alpha * 0.45 * (1.0 - progress))),
                start,
                end,
                max(1, WORLD_SCALE),
            )
        # holy sigil core: a small diamond
        sigil_r = max(2, radius // 6)
        sigil_pts = [
            (center[0], center[1] - sigil_r),
            (center[0] + sigil_r, center[1]),
            (center[0], center[1] + sigil_r),
            (center[0] - sigil_r, center[1]),
        ]
        pygame.draw.polygon(overlay, (*bright, int(alpha * 0.78)), sigil_pts)
        pygame.draw.circle(
            overlay, (*self.shade(holy, 60), alpha), center, max(1, sigil_r // 2)
        )

    def _draw_cast_rogue(
        self,
        overlay: pygame.Surface,
        center: tuple[int, int],
        radius: int,
        alpha: int,
        bright: Color,
        dark: Color,
        progress: float,
    ) -> None:
        # Smoke/poison burst: no clean ring — expanding puffs of smoke with
        # poison-green wisps that dissipate outward.
        smoke = self.shade(dark, 20)
        poison = bright
        # central smoke puff
        core_r = max(2, int(radius * (0.30 - progress * 0.18)))
        if core_r > 0:
            pygame.draw.circle(overlay, (*smoke, int(alpha * 0.6)), center, core_r)
            pygame.draw.circle(
                overlay, (*poison, int(alpha * 0.5)), center, max(1, core_r // 3)
            )
        # expanding smoke puffs
        puff_count = 9
        for index in range(puff_count):
            angle = index * math.tau / puff_count + progress * 1.6
            dist = radius * (0.30 + progress * 0.75 + (index % 2) * 0.05)
            puff = (
                center[0] + int(math.cos(angle) * dist),
                center[1] + int(math.sin(angle) * dist * 0.55) - int(progress * 6),
            )
            puff_r = max(
                2, int(radius * (0.16 + (index % 3) * 0.04) * (1.0 - progress * 0.4))
            )
            puff_alpha = int(alpha * (0.5 - progress * 0.4))
            if puff_alpha <= 0:
                continue
            pygame.draw.circle(overlay, (*smoke, puff_alpha), puff, puff_r)
            # poison wisp inside each puff
            pygame.draw.circle(
                overlay,
                (*poison, int(puff_alpha * 0.6)),
                puff,
                max(1, puff_r // 3),
            )
        # trailing poison wisps
        for index in range(5):
            angle = index * math.tau / 5 - progress * 2.2
            dist = radius * (0.55 + progress * 0.4)
            wisp = (
                center[0] + int(math.cos(angle) * dist),
                center[1] + int(math.sin(angle) * dist * 0.55),
            )
            pygame.draw.circle(
                overlay,
                (*self.shade(poison, 30), int(alpha * 0.35)),
                wisp,
                max(1, radius // 11),
            )

    def _draw_cast_acolyte(
        self,
        overlay: pygame.Surface,
        center: tuple[int, int],
        radius: int,
        alpha: int,
        bright: Color,
        dark: Color,
        progress: float,
    ) -> None:
        # Blood nova: a dark crimson ring with blood droplets radiating outward,
        # dark tendrils, and a shadowed crimson core.
        blood = bright
        shadow = self.shade(dark, -30)
        ring_radius = max(3, int(radius * (0.40 + progress * 0.55)))
        # dark tendrils from center to ring
        tendril_count = 8
        for index in range(tendril_count):
            angle = index * math.tau / tendril_count - progress * 0.6
            end = (
                center[0] + int(math.cos(angle) * ring_radius),
                center[1] + int(math.sin(angle) * ring_radius * 0.55),
            )
            pygame.draw.line(
                overlay,
                (*shadow, int(alpha * 0.4 * (1.0 - progress * 0.6))),
                center,
                end,
                max(1, WORLD_SCALE),
            )
        # crimson ring
        pygame.draw.circle(
            overlay,
            (*blood, int(alpha * 0.45)),
            center,
            ring_radius,
            max(1, WORLD_SCALE),
        )
        pygame.draw.circle(
            overlay,
            (*shadow, int(alpha * 0.30)),
            center,
            max(2, ring_radius - 2),
            max(1, WORLD_SCALE),
        )
        # radiating blood droplets that elongate outward
        drop_count = 10
        for index in range(drop_count):
            angle = index * math.tau / drop_count + progress * 0.5
            dist = ring_radius * (0.65 + progress * 0.45)
            drop = (
                center[0] + int(math.cos(angle) * dist),
                center[1] + int(math.sin(angle) * dist * 0.55),
            )
            drop_r = max(1, int(radius * (0.06 + progress * 0.05)))
            pygame.draw.circle(
                overlay, (*self.shade(blood, -25), int(alpha * 0.7)), drop, drop_r
            )
        # shadowed crimson core (the blood heart)
        core_r = max(2, int(radius * (0.18 + progress * 0.10)))
        pygame.draw.circle(overlay, (*shadow, int(alpha * 0.7)), center, core_r)
        pygame.draw.circle(
            overlay, (*blood, int(alpha * 0.85)), center, max(1, core_r // 2)
        )

    def _draw_cast_ranger(
        self,
        overlay: pygame.Surface,
        center: tuple[int, int],
        radius: int,
        alpha: int,
        bright: Color,
        dark: Color,
        progress: float,
    ) -> None:
        # Snare-vine ring: an expanding green bramble ring with thorn/leaf
        # accents and rooting lines spreading outward.
        vine = bright
        vine_lo = self.shade(vine, -40)
        ring_radius = max(3, int(radius * (0.40 + progress * 0.55)))
        # rooting lines spreading outward (the snare)
        root_count = 8
        for index in range(root_count):
            angle = index * math.tau / root_count + progress * 0.3
            inner = ring_radius * 0.20
            outer = ring_radius * (1.0 + progress * 0.20)
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
                (*vine_lo, int(alpha * 0.4 * (1.0 - progress * 0.5))),
                start,
                end,
                max(1, WORLD_SCALE),
            )
        # vine ring
        pygame.draw.circle(
            overlay,
            (*vine, int(alpha * 0.50)),
            center,
            ring_radius,
            max(1, WORLD_SCALE),
        )
        pygame.draw.circle(
            overlay,
            (*vine_lo, int(alpha * 0.30)),
            center,
            max(2, ring_radius - 2),
            max(1, WORLD_SCALE),
        )
        # thorn/leaf accents on the ring
        thorn_count = 10
        for index in range(thorn_count):
            angle = index * math.tau / thorn_count - progress * 0.8
            px = center[0] + int(math.cos(angle) * ring_radius)
            py = center[1] + int(math.sin(angle) * ring_radius * 0.55)
            thorn_len = max(2, int(radius * 0.10))
            tip = (
                px + int(math.cos(angle) * thorn_len),
                py + int(math.sin(angle) * thorn_len * 0.55),
            )
            pygame.draw.line(
                overlay,
                (*self.shade(vine, 30), int(alpha * 0.7)),
                (px, py),
                tip,
                max(1, WORLD_SCALE),
            )
            pygame.draw.circle(
                overlay, (*vine, int(alpha * 0.6)), (px, py), max(1, radius // 12)
            )
        # leaf-like core
        core_r = max(2, radius // 7)
        leaf_pts = [
            (center[0], center[1] - core_r),
            (center[0] + core_r, center[1]),
            (center[0], center[1] + core_r),
            (center[0] - core_r, center[1]),
        ]
        pygame.draw.polygon(overlay, (*vine, int(alpha * 0.7)), leaf_pts)
        pygame.draw.circle(
            overlay,
            (*self.shade(vine, 40), int(alpha * 0.9)),
            center,
            max(1, core_r // 2),
        )

    def _soft_shadow_template(self, size: int) -> pygame.Surface:
        # Cached radial-alpha square: center peaks at full opacity, edges fade
        # to transparent. Built once per quantized size and reused across every
        # entity so the hot path only pays for a smoothscale + blit.
        cache: dict[int, pygame.Surface] = getattr(
            self, "_soft_shadow_template_cache", {}
        )
        # Quantize to a 4px bucket so lift/bob jitter across frames does not
        # fragment the cache; the visual difference is sub-pixel after scaling.
        size = max(8, (size // 4) * 4)
        surf = cache.get(size)
        if surf is not None:
            return surf
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        surf.fill((0, 0, 0, 0))
        steps = max(6, size // 2)
        # pygame.draw overwrites destination alpha (no source-over blending),
        # so draw concentric ellipses outer-first with alpha rising toward the
        # center: each smaller ellipse replaces the core with a higher alpha,
        # leaving the outer ring at the lowest alpha for a smooth radial edge.
        peak_alpha = 140
        cx = cy = size / 2.0
        for i in range(steps):
            ratio = 1.0 - i / steps  # 1.0 outer -> 0.0 inner
            radius = (size / 2.0) * ratio
            if radius < 0.5:
                break
            alpha = int(peak_alpha * (i / max(1, steps - 1)))
            rect = pygame.Rect(0, 0, int(radius * 2), int(radius * 2))
            rect.center = (int(cx), int(cy))
            pygame.draw.ellipse(surf, (0, 0, 0, alpha), rect)
        try:
            surf = surf.convert_alpha()
        except pygame.error:
            pass
        cache[size] = surf
        self._soft_shadow_template_cache = cache
        return surf

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
        # Soft contact shadow: a cached radial-alpha template, scaled per entity
        # size and squashed by the iso projection (height < width) so actors
        # read as grounded on the floor diamond instead of floating above it.
        # The template internally quantizes its cache key so lift/bob jitter
        # across frames does not fragment the cache.
        template = self._soft_shadow_template(max(8, max(scaled_w, scaled_h)))
        shadow = pygame.transform.smoothscale(template, (scaled_w, scaled_h))
        # set_alpha acts as a global multiplier on per-pixel-alpha surfaces in
        # pygame-ce, so motion/lift modulation costs nothing per frame.
        opacity = 210 if moving else 175
        opacity = max(0, min(255, int(opacity - lift * 6.0)))
        shadow.set_alpha(opacity)
        self.screen.blit(
            shadow,
            shadow.get_rect(center=(sx, sy + 10 * WORLD_SCALE)),
        )

    def draw_item(self, item: Item) -> None:
        if item.slot == "story_relic":
            self.draw_story_relic(item)
            return
        if item.slot == "shop_sign":
            self.draw_shop_sign_item(item)
            return
        sx, sy = self.world_to_screen(item.x, item.y)
        bob = int(math.sin(self.elapsed * 3.2 + item.x * 0.7) * 2 * WORLD_SCALE)
        # Soft contact shadow grounds the floating loot bob on the floor
        # diamond; lift fades/shrinks the patch as the item rises.
        self.draw_shadow(item.x, item.y, 22, 9, lift=bob / WORLD_SCALE)
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

    def draw_shop_sign_item(self, item: Item) -> None:
        # The shop sign is a mounted hanging sign (built procedurally in the
        # sprite atlas), not a generic loot item — render the shop_sign sprite
        # with a soft gold glow and the trade prompt label.
        sx, sy = self.world_to_screen(item.x, item.y)
        gold = (245, 205, 92)
        pulse = 0.65 + 0.35 * math.sin(self.elapsed * 4.0 + item.x + item.y)
        glow = pygame.Surface((42 * WORLD_SCALE, 20 * WORLD_SCALE), pygame.SRCALPHA)
        pygame.draw.ellipse(glow, (*gold, int(40 + 35 * pulse)), glow.get_rect())
        self.screen.blit(glow, glow.get_rect(center=(sx, sy + WORLD_SCALE)))
        bob = int(math.sin(self.elapsed * 3.2 + item.x * 0.7) * 2 * WORLD_SCALE)
        frame = self.sprites.shop_sign_visual()
        sign = frame.surface
        if frame.is_asset:
            rect = self.blit_resolved_sprite(
                frame,
                item.x,
                item.y,
                y_offset=4.0 - bob / WORLD_SCALE,
            )
        else:
            rect = sign.get_rect(midbottom=(sx, sy + 4 * WORLD_SCALE - bob))
            self.screen.blit(sign, rect)
        if math.hypot(item.x - self.player.x, item.y - self.player.y) < 1.0:
            label = self.small_font.render(
                f"E {self.rarity_icon(item.visible_rarity)} {item.display_name}",
                True,
                gold,
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
        # The guidance uses the same carved-groove language as the floor's
        # own variant cracks (`_floor_groove`: shadowed recess + lit lip,
        # anti-aliased) and the same slab color (`theme.floor`), so it reads
        # as a fracture in the flagstone rather than a painted-on line. The
        # only colored cue is a faint warm seep welling up from the bottom of
        # the recess, kept low-contrast so it never reads as a glowing beam.
        # It pulses on a coarse ~3Hz clock so it steps a few times a second
        # instead of shimmering every frame.
        slab = self.theme.floor
        accent = self.story_state.accent if self.story_state else self.theme.accent
        warm = self.mix(accent, (255, 232, 142), 0.5)
        phase = math.floor(self.elapsed * 3.0) / 3.0
        pulse = 0.5 + 0.5 * math.sin(phase * 2.6)

        # The guiding light is only a faint hint while the player is moving
        # and comes alive (pulsating) when the player stands still, so the
        # floor around the character stays calm during traversal. The carved
        # groove (the crack structure) and the warm seep (the light) both dim
        # while moving and breathe with pulse while idle.
        moving = bool(getattr(self.player, "moving", False))
        if moving:
            groove_alpha = 55
            seep_alpha = 20
            ring_groove_alpha = 45
            ring_light_alpha = 20
        else:
            groove_alpha = int(140 + 70 * pulse)
            seep_alpha = int(50 + 70 * pulse)
            ring_groove_alpha = int(85 + 70 * pulse)
            ring_light_alpha = int(40 + 55 * pulse)

        screen_w, screen_h = self._screen_size()
        glow_layer = self._guidance_glow_layer(screen_w, screen_h)

        # Follow the route's actual waypoints (trimmed a little in from the
        # player and the relic) so the crack bends with the corridor instead
        # of cutting a straight line across wall corners between sparse
        # samples.
        total = route_distance
        start_distance = min(1.05, total * 0.35)
        end_distance = max(start_distance, total - 0.45)
        crack_world = self._guidance_crack_polyline(route, start_distance, end_distance)
        if len(crack_world) < 2:
            return

        def open_tile(tix: int, tiy: int) -> bool:
            if not self.dungeon.in_bounds(tix, tiy):
                return False
            t = self.dungeon.tiles[tix][tiy]
            return t != Tile.WALL and t != Tile.CLOSED_DOOR

        raw_screen = [self.world_to_screen(wx, wy) for wx, wy in crack_world]
        crack_points: list[tuple[float, float]] = []
        can_fracture: list[bool] = []
        for index, (wx, wy) in enumerate(crack_world):
            sx, sy = raw_screen[index]
            prev_x, prev_y = raw_screen[max(0, index - 1)]
            next_x, next_y = raw_screen[min(len(raw_screen) - 1, index + 1)]
            tangent_x = next_x - prev_x
            tangent_y = next_y - prev_y
            tangent_len = math.hypot(tangent_x, tangent_y)
            if tangent_len <= 0.001:
                tangent_x, tangent_y, tangent_len = 1.0, 0.0, 1.0
            dir_x = tangent_x / tangent_len
            dir_y = tangent_y / tangent_len
            perp_x, perp_y = -dir_y, dir_x
            stx, sty = int(wx), int(wy)
            # Only jag when the sample sits in open floor (every orthogonal
            # neighbor walkable); in corridors the crack runs straight so it
            # can never drift into a wall tile and read as overlapping it.
            open_area = (
                open_tile(stx + 1, sty)
                and open_tile(stx - 1, sty)
                and open_tile(stx, sty + 1)
                and open_tile(stx, sty - 1)
            )
            can_fracture.append(open_area)
            if index == 0 or index == len(raw_screen) - 1 or not open_area:
                offset = 0.0
            else:
                jag = ((index * 37) ^ (index << 1)) % 5 - 2  # -2..2 px
                sign = -1.0 if index % 2 else 1.0
                offset = (jag + sign) * WORLD_SCALE
            crack_points.append((sx + perp_x * offset, sy + perp_y * offset))

        # Carved recess + lit lip, same recipe as the floor's own variant
        # grooves (`_floor_groove`), but drawn with a dimming alpha so the
        # whole guiding light reads very faint while the player moves and
        # pulsates when the player stands still.
        shadow = self.shade(slab, -24)
        lip = self.shade(slab, 16)

        # Tile-visibility clipping: the guiding light leads the player toward
        # the relic, which is usually far outside the current sight radius. To
        # avoid painting a glowing crack across dark / unrevealed floor (which
        # would break the darkness effect), split the polyline into runs of
        # consecutive samples that sit on a currently-lit tile and only draw
        # those runs. As the player advances, more of the crack lights up and
        # the leading end fades into the dark ahead.
        def tile_lit(wx: float, wy: float) -> bool:
            ix, iy = int(wx), int(wy)
            if not self.dungeon.in_bounds(ix, iy):
                return False
            return self.tile_visibility_alpha(ix, iy) > 0

        lit_flags = [tile_lit(wx, wy) for wx, wy in crack_world]
        runs: list[list[int]] = []
        current: list[int] = []
        for index, lit in enumerate(lit_flags):
            if lit:
                current.append(index)
            elif current:
                runs.append(current)
                current = []
        if current:
            runs.append(current)

        drew_anything = False
        for run in runs:
            if len(run) < 2:
                continue
            run_points = [crack_points[i] for i in run]
            pygame.draw.aalines(glow_layer, (*shadow, groove_alpha), False, run_points)
            pygame.draw.aalines(
                glow_layer,
                (*lip, groove_alpha),
                False,
                [(p[0], p[1] - 1) for p in run_points],
            )
            # Faint warm seep at the bottom of the recess; the only colored cue.
            seep_points = [(p[0], p[1] + 1) for p in run_points]
            pygame.draw.lines(glow_layer, (*warm, seep_alpha), False, seep_points, 1)
            drew_anything = True

        # Short branch stubs at a couple of interior points (only in open,
        # lit floor) so it reads as a real fracture rather than a drawn line.
        for branch_index in (1, len(crack_points) - 2):
            if branch_index < 1 or branch_index >= len(crack_points) - 1:
                continue
            if not can_fracture[branch_index] or not lit_flags[branch_index]:
                continue
            bx, by = crack_points[branch_index]
            prev_x, prev_y = raw_screen[branch_index - 1]
            next_x, next_y = raw_screen[branch_index + 1]
            tn_x = next_x - prev_x
            tn_y = next_y - prev_y
            tn_len = math.hypot(tn_x, tn_y) or 1.0
            perp_x, perp_y = -tn_y / tn_len, tn_x / tn_len
            stub_len = 5 * WORLD_SCALE
            tip = (bx + perp_x * stub_len, by + perp_y * stub_len)
            pygame.draw.aaline(glow_layer, (*shadow, groove_alpha), (bx, by), tip)
            pygame.draw.aaline(
                glow_layer,
                (*lip, groove_alpha),
                (bx, by - 1),
                (tip[0], tip[1] - 1),
            )
            drew_anything = True

        # Target: a small worn ring groove lying flat on the iso floor (y
        # squashed to match the floor plane) in the same carved language, with
        # a faint warm pinprick at its center. Clipped to the relic's own
        # floor tile diamond so it can't spill over an adjacent wall; like the
        # crack it dims while moving and pulsates when idle. Only drawn when
        # the relic's tile is currently lit, so the ring never appears in the
        # dark ahead of the player.
        if tile_lit(tx, ty):
            target_sx, target_sy = self.world_to_screen(tx, ty)
            ring_cx = float(target_sx)
            ring_cy = float(target_sy - int(4 * WORLD_SCALE))
            ring_radius = 7.0 * WORLD_SCALE
            r_tile_x, r_tile_y = int(tx), int(ty)
            tcx, tcy = self.world_to_screen(r_tile_x + 0.5, r_tile_y + 0.5)
            half_w = TILE_W / 2
            half_h = TILE_H / 2

            def in_diamond(px: float, py: float) -> bool:
                return (abs(px - tcx) / half_w + abs(py - tcy) / half_h) <= 0.97

            segs = 22
            for i in range(segs):
                a0 = i * (2 * math.pi / segs)
                a1 = (i + 1) * (2 * math.pi / segs)
                p0 = (
                    ring_cx + math.cos(a0) * ring_radius,
                    ring_cy + math.sin(a0) * ring_radius * 0.5,
                )
                p1 = (
                    ring_cx + math.cos(a1) * ring_radius,
                    ring_cy + math.sin(a1) * ring_radius * 0.5,
                )
                if not (in_diamond(p0[0], p0[1]) and in_diamond(p1[0], p1[1])):
                    continue
                pygame.draw.aaline(glow_layer, (*shadow, ring_groove_alpha), p0, p1)
                pygame.draw.aaline(
                    glow_layer,
                    (*lip, ring_groove_alpha),
                    (p0[0], p0[1] - 1),
                    (p1[0], p1[1] - 1),
                )
            if in_diamond(ring_cx, ring_cy):
                pygame.draw.circle(
                    glow_layer,
                    (*warm, ring_light_alpha),
                    (int(ring_cx), int(ring_cy)),
                    max(1, int(2 * WORLD_SCALE)),
                )
            drew_anything = True

        if drew_anything:
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

    def _guidance_crack_polyline(
        self,
        route: list[tuple[float, float]],
        start_distance: float,
        end_distance: float,
    ) -> list[tuple[float, float]]:
        # Build the crack polyline by following the route's actual waypoints
        # (trimmed a little in from the player and the relic) rather than
        # sparse evenly-spaced samples. Following every waypoint means the
        # crack bends with the corridor and can never cut a straight line
        # across a wall corner between two samples.
        if len(route) < 2:
            return []
        cum = [0.0]
        for (ax, ay), (bx, by) in zip(route, route[1:]):
            cum.append(cum[-1] + math.hypot(bx - ax, by - ay))
        total = cum[-1]
        if total <= 0.001 or end_distance <= start_distance:
            return []
        start_distance = max(0.0, min(start_distance, total))
        end_distance = max(start_distance, min(end_distance, total))

        def point_at(dist: float) -> tuple[float, float]:
            for i in range(len(route) - 1):
                if cum[i + 1] >= dist:
                    seg_len = cum[i + 1] - cum[i]
                    r = 0.0 if seg_len <= 0.001 else (dist - cum[i]) / seg_len
                    ax, ay = route[i]
                    bx, by = route[i + 1]
                    return (ax + (bx - ax) * r, ay + (by - ay) * r)
            return route[-1]

        points: list[tuple[float, float]] = [point_at(start_distance)]
        for i in range(1, len(route) - 1):
            if start_distance < cum[i] < end_distance:
                points.append(route[i])
        points.append(point_at(end_distance))
        return points

    def draw_story_relic(self, item: Item) -> None:
        sx, sy = self.world_to_screen(item.x, item.y)
        accent = self.story_state.accent if self.story_state else self.theme.accent
        pulse = 0.5 + 0.5 * math.sin(self.elapsed * 5.2 + item.x)
        # Floor glow: a soft accent ellipse so the relic reads as lit from
        # beneath, same idiom as other loot. Breathes with pulse.
        glow = pygame.Surface((58 * WORLD_SCALE, 34 * WORLD_SCALE), pygame.SRCALPHA)
        pygame.draw.ellipse(glow, (*accent, int(54 + pulse * 70)), glow.get_rect())
        pygame.draw.ellipse(
            glow,
            (*self.shade(accent, 50), int(28 + pulse * 44)),
            glow.get_rect().inflate(-glow.get_width() // 3, -glow.get_height() // 3),
        )
        self.screen.blit(glow, glow.get_rect(center=(sx, sy)))
        # Contact shadow grounds the bobbing gem on the floor diamond.
        bob = int(math.sin(self.elapsed * 3.5 + item.y) * 3 * WORLD_SCALE)
        self.draw_shadow(item.x, item.y, 26, 11, lift=bob / WORLD_SCALE)

        # The gem itself is the cached octahedron sprite from the atlas
        # (sprites._story_relic), pulled as the un-tinted base frame and recolored
        # here with the per-story accent via an additive blend so the same art
        # recolors for every story. A slow tilt + bob give it a floating, alive
        # read; the atlas already outlined + upscaled it for the chunky look.
        sprite = self.sprites.item_frame(
            "story_relic",
            self.elapsed + item.x * 0.31 + item.y * 0.17,
            "Common",
        )
        sprite = sprite.copy()
        # BLEND_RGB_ADD (not RGBA) recolors only the gem's opaque pixels;
        # the transparent padding around the sprite stays at alpha 0 so no
        # accent-tinted rectangle leaks around the relic.
        sprite.fill((*accent, 40), special_flags=pygame.BLEND_RGB_ADD)
        tilt = math.sin(self.elapsed * 2.8 + item.y) * 3.0
        if abs(tilt) > 0.1:
            sprite = pygame.transform.rotate(sprite, tilt)
        self.screen.blit(
            sprite, sprite.get_rect(midbottom=(sx, sy + 4 * WORLD_SCALE - bob))
        )

        # Orbiting motes around the relic, drawn on top of the gem so they
        # read as attendant sparks circling the stone. Kept small and
        # accent-tinted so they stay a secondary cue.
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
        self.draw_shadow(trap.x, trap.y, 28, 11)
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
        frame = self.sprites.trap_visual(trap.kind, self.elapsed + trap.x * 0.5)
        if frame.is_asset:
            self.blit_resolved_sprite(frame, trap.x, trap.y, y_offset=1.0)
        else:
            sprite = frame.surface
            self.screen.blit(sprite, sprite.get_rect(center=(sx, sy - 2 * WORLD_SCALE)))
        if math.hypot(trap.x - self.player.x, trap.y - self.player.y) < 1.35:
            label = self.small_font.render(f"! {trap.kind}", True, color)
            self.screen.blit(label, label.get_rect(center=(sx, sy - 24 * WORLD_SCALE)))

    def draw_ambush_bell(self, bell: AmbushBell) -> None:
        sx, sy = self.world_to_screen(bell.x, bell.y)
        color = self.damage_type_color("shadow")
        armed = bell.armed
        pulse = 0.5 + 0.5 * math.sin(self.elapsed * (8.0 if armed else 5.2) + bell.x)
        self.draw_shadow(bell.x, bell.y, 24, 9)

        ring_w = int((42 + pulse * (14 if armed else 7)) * WORLD_SCALE)
        ring_h = int((20 + pulse * (7 if armed else 4)) * WORLD_SCALE)
        ring = pygame.Surface((max(4, ring_w), max(4, ring_h)), pygame.SRCALPHA)
        ring_alpha = int(44 + pulse * (64 if armed else 34))
        pygame.draw.ellipse(ring, (*color, ring_alpha), ring.get_rect(), max(1, WORLD_SCALE))
        if armed:
            inner = ring.get_rect().inflate(-ring.get_width() // 3, -ring.get_height() // 3)
            pygame.draw.ellipse(ring, (*self.shade(color, 48), 36), inner, max(1, WORLD_SCALE))
        self.screen.blit(ring, ring.get_rect(center=(sx, sy + 2 * WORLD_SCALE)))

        if not armed and bell.max_arm_timer > 0.001:
            progress = 1.0 - max(0.0, min(1.0, bell.arm_timer / bell.max_arm_timer))
            arc_rect = pygame.Rect(0, 0, 30 * WORLD_SCALE, 17 * WORLD_SCALE)
            arc_rect.center = (sx, sy - 2 * WORLD_SCALE)
            pygame.draw.arc(
                self.screen,
                self.shade(color, 50),
                arc_rect,
                -math.pi / 2,
                -math.pi / 2 + math.tau * progress,
                max(1, WORLD_SCALE),
            )
        elif armed:
            for index in range(3):
                angle = self.elapsed * 3.8 + index * math.tau / 3 + bell.x
                mote = (
                    sx + int(math.cos(angle) * 15 * WORLD_SCALE),
                    sy - int((8 + math.sin(angle) * 4) * WORLD_SCALE),
                )
                pygame.draw.circle(
                    self.screen,
                    self.shade(color, 60),
                    mote,
                    max(1, WORLD_SCALE),
                )

        bell_frame = self.sprites.ambush_bell_visual()
        if bell_frame is not None:
            self.blit_resolved_sprite(bell_frame, bell.x, bell.y, y_offset=1.0)
        else:
            body_w = max(6, 8 * WORLD_SCALE)
            body_h = max(5, 7 * WORLD_SCALE)
            body = pygame.Rect(0, 0, body_w, body_h)
            body.midbottom = (sx, sy - 1 * WORLD_SCALE)
            pygame.draw.ellipse(
                self.screen, (24, 20, 28), body.inflate(2 * WORLD_SCALE, 0)
            )
            pygame.draw.ellipse(self.screen, self.shade(color, -48), body)
            pygame.draw.arc(
                self.screen,
                self.shade(color, 42),
                body.inflate(2 * WORLD_SCALE, 2 * WORLD_SCALE),
                math.pi,
                math.tau,
                max(1, WORLD_SCALE),
            )
            crack_x = sx + int(math.sin(self.elapsed * 8.0) * WORLD_SCALE)
            pygame.draw.line(
                self.screen,
                self.shade(color, 80),
                (crack_x, body.top + WORLD_SCALE),
                (crack_x - 2 * WORLD_SCALE, body.centery),
                max(1, WORLD_SCALE),
            )
            pygame.draw.circle(
                self.screen,
                self.shade(color, 55),
                (sx, body.bottom),
                max(1, WORLD_SCALE),
            )

    def draw_secret(self, secret: SecretCache) -> None:
        sx, sy = self.world_to_screen(secret.x, secret.y)
        self.draw_shadow(secret.x, secret.y, 26, 11)
        color = self.theme.accent
        frame = self.sprites.secret_visual(self.elapsed + secret.x * 0.33)
        pulse = 0.55 + 0.45 * math.sin(self.elapsed * 5.0 + secret.x)
        glow = pygame.Surface((34 * WORLD_SCALE, 18 * WORLD_SCALE), pygame.SRCALPHA)
        pygame.draw.ellipse(glow, (*color, int(34 + 46 * pulse)), glow.get_rect())
        self.screen.blit(glow, glow.get_rect(center=(sx, sy + 2 * WORLD_SCALE)))
        if not frame.is_asset:
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
        if frame.is_asset:
            self.blit_resolved_sprite(frame, secret.x, secret.y, y_offset=4.0)
        else:
            sprite = frame.surface
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
        facing_x, facing_y, moving, dance_progress = self.friendly_npc_visual_state(
            guest
        )
        sx, sy = self.world_to_screen(guest.x, guest.y)
        color = guest.color if not guest.resolved else self.shade(guest.color, -60)
        self.draw_shadow(guest.x, guest.y, 26, 11, moving=moving)
        pulse = 0.55 + 0.45 * math.sin(self.elapsed * 4.0 + guest.depth)
        # Subtle floor marker (a faint accent ring) so the quest NPC is still
        # distinguishable from a generic traveler, but without the bright
        # pulsing aura that made it read as a glowing quest beacon.
        ring = pygame.Surface((48 * WORLD_SCALE, 25 * WORLD_SCALE), pygame.SRCALPHA)
        ring_alpha = int(20 + 12 * pulse) if not guest.resolved else 14
        pygame.draw.ellipse(
            ring, (*color, ring_alpha), ring.get_rect(), max(1, WORLD_SCALE)
        )
        self.screen.blit(ring, ring.get_rect(center=(sx, sy + 4 * WORLD_SCALE)))

        frame = self.sprites.story_guest_visual(
            self.elapsed,
            guest.resolved,
            direction=self.actor_sprite_direction(facing_x, facing_y),
            moving=moving,
            clip_progress=dance_progress,
        )
        # Drawn as-is, like every other actor. The previous additive tint over
        # the whole sprite is what made the guest glow; normal humanoids are not
        # tinted at draw time.
        if frame.is_asset:
            self.blit_resolved_sprite(frame, guest.x, guest.y, y_offset=5.0)
        else:
            sprite = frame.surface
            self.screen.blit(sprite, sprite.get_rect(midbottom=(sx, sy + 5 * WORLD_SCALE)))

        # The floating portrait badge (a dark disc with a "?"/role/"✓" glyph)
        # used to be drawn above the guest here. It read as a pasted-on status
        # icon and, on aid-choice floors where the relic is placed on the
        # guest's own tile, it sat directly on top of the relic. The floor ring,
        # the sprite itself, and the proximity label below already identify the
        # guest and its state, so the badge is gone.

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

    def draw_idle_npc(self, npc: IdleNpc) -> None:
        # Decorative, non-interactable traveler (bar / garden flavor). Reuses the
        # story-guest humanoid sprite so it reads as a person, but drops the
        # quest aura, label, and interaction prompt — the player cannot talk to
        # or trade with them. A faint floor shadow is enough to ground them.
        facing_x, facing_y, moving, dance_progress = self.friendly_npc_visual_state(npc)
        sx, sy = self.world_to_screen(npc.x, npc.y)
        self.draw_shadow(npc.x, npc.y, 24, 10, moving=moving)
        frame = self.sprites.story_guest_visual(
            self.elapsed,
            False,
            direction=self.actor_sprite_direction(facing_x, facing_y),
            moving=moving,
            clip_progress=dance_progress,
        )
        if frame.is_asset:
            self.blit_resolved_sprite(frame, npc.x, npc.y, y_offset=5.0)
        else:
            sprite = frame.surface
            self.screen.blit(sprite, sprite.get_rect(midbottom=(sx, sy + 5 * WORLD_SCALE)))

    def draw_familiar(self, familiar: Familiar) -> None:
        sx, sy = self.world_to_screen(familiar.x, familiar.y)
        bob = math.sin(self.elapsed * 3.4 + familiar.x * 0.7 + familiar.y * 0.4) * 1.4
        shadow_w = 30 if familiar.champion else (22 if familiar.sprite_variant else 18)
        self.draw_shadow(familiar.x, familiar.y, shadow_w, 10, moving=familiar.moving)
        direction = self.actor_sprite_direction(
            getattr(familiar, "facing_x", 1.0), getattr(familiar, "facing_y", 0.0)
        )
        frame = self.sprites.familiar_visual(
            familiar.sprite_variant,
            self.elapsed,
            direction=direction,
            moving=familiar.moving,
        )
        sprite = frame.surface
        if frame.is_asset:
            rect = self.blit_resolved_sprite(
                frame, familiar.x, familiar.y, y_offset=5.0 - bob
            )
        else:
            rect = sprite.get_rect(midbottom=(sx, sy + (5 - bob) * WORLD_SCALE))
            self.screen.blit(sprite, rect)
        if familiar.hp < familiar.max_hp:
            bar_w = 24 * WORLD_SCALE
            fill_w = int(bar_w * max(0, familiar.hp) / familiar.max_hp)
            bar_h = 3 * WORLD_SCALE
            bar_y = rect.top - 2 * WORLD_SCALE
            pygame.draw.rect(
                self.screen, (40, 10, 10), (sx - bar_w // 2, bar_y, bar_w, bar_h)
            )
            pygame.draw.rect(
                self.screen,
                (160, 235, 230),
                (sx - bar_w // 2, bar_y, fill_w, bar_h),
            )

    def draw_shrine(self, shrine: Shrine) -> None:
        sx, sy = self.world_to_screen(shrine.x, shrine.y)
        self.draw_shadow(shrine.x, shrine.y, 30, 12)
        color = (92, 92, 100) if shrine.used else (235, 205, 110)
        frame = self.sprites.shrine_visual(
            shrine.kind, self.elapsed + shrine.x, shrine.used
        )
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
        if not frame.is_asset:
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
        if frame.is_asset:
            self.blit_resolved_sprite(frame, shrine.x, shrine.y, y_offset=2.0)
        else:
            sprite = frame.surface
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
            projectile.owner,
            self.elapsed + projectile.x * 0.2 + projectile.y * 0.15,
            archetype=getattr(projectile, "archetype", ""),
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
