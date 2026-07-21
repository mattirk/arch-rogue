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

from ..constants import DUNGEON_DEPTH, TILE_H, TILE_W, WORLD_SCALE, SlashEffect
from ..content import HUMANOID_ENEMY_NAMES
from ..mobile import optimize_immutable_alpha_surface
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
from ..story import (
    CutsceneActorAsset,
    SpriteAnimationFrameAsset,
    format_asset_text,
)

# Bounded impact-overlay LRU. Large skill pulses are expensive translucent
# software surfaces, so Android uses fewer animation buckets while desktop keeps
# the original cadence. The byte cap prevents a handful of full-room cast rings
# from retaining tens of megabytes during long, effect-heavy runs.
IMPACT_EFFECT_CACHE_MAX = 128
IMPACT_EFFECT_CACHE_MAX_BYTES = 24 * 1024 * 1024
PROJECTILE_ROTATION_STEP_DEGREES = 15


class RenderingEffectsMixin:
    _impact_overlay_cache_bytes: int = 0

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
        overlay = optimize_immutable_alpha_surface(overlay)
        cache[key] = overlay
        self.ambient_overlay_cache = cache
        return overlay

    def draw_ambient_depth_overlay(self) -> None:
        if self.state not in ("playing", "dead", "victory"):
            return
        if self.is_current_floor_dark():
            return
        if getattr(self, "mobile_mode", False):
            # Android's native framebuffer makes this decorative full-viewport
            # alpha pass cost roughly 13 ms even with continuous lighting off.
            # Terrain visibility already carries the darkness model, while the
            # lighting-on path supplies its own depth tint, so omit the vignette
            # on every mobile quality tier.
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

        # Cache baked overlays by a quantized animation state. Android's
        # software composition benefits from coarser buckets for large effects:
        # a Time Skip ring then reuses each surface for several frames instead of
        # rasterizing and uploading another large RGBA surface every frame.
        mobile = bool(getattr(self, "mobile_mode", False))
        large_mobile_effect = mobile and radius >= 96
        progress_steps = 12 if large_mobile_effect else 24
        progress_bucket = int(progress * progress_steps)
        if large_mobile_effect:
            # Progress already determines size and fade. A single state key lets
            # several consecutive frames share the same full-room surface.
            alpha_bucket = 0
            radius_bucket = 0
        else:
            alpha_bucket = (alpha // 16) * 16
            radius_bucket = (radius // 4) * 4
        cache_key = (
            effect.kind,
            effect.archetype,
            progress_bucket,
            alpha_bucket,
            radius_bucket,
            effect.color,
        )
        cache = getattr(self, "_impact_overlay_cache", None)
        if not isinstance(cache, OrderedDict):
            cache = OrderedDict()
            self._impact_overlay_cache = cache
            self._impact_overlay_cache_bytes = 0
        cached = cache.get(cache_key)
        if cached is not None:
            cache.move_to_end(cache_key)
            self.screen.blit(
                cached, cached.get_rect(center=(sx, sy - 12 * WORLD_SCALE))
            )
            return

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
        elif effect.kind == "spirit_beast_call":
            self._draw_spirit_beast_call(
                overlay, center, radius, alpha, bright, dark, progress
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
                pygame.draw.polygon(
                    overlay,
                    (*self.shade(bright, 35), alpha),
                    [tip, left, right],
                )
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


        # Impact art deliberately contains partial-alpha rings, smoke, and rays.
        # Running the immutable binary-alpha optimizer here scans the full surface
        # twice only to reject it, which is especially costly for Time Skip's
        # full-room pulse. Cache the native alpha surface directly.
        assert cache is not None
        cache[cache_key] = overlay
        cache.move_to_end(cache_key)
        cache_bytes = int(getattr(self, "_impact_overlay_cache_bytes", 0))
        cache_bytes += (
            overlay.get_width() * overlay.get_height() * overlay.get_bytesize()
        )
        while (
            len(cache) > IMPACT_EFFECT_CACHE_MAX
            or cache_bytes > IMPACT_EFFECT_CACHE_MAX_BYTES
        ):
            _old_key, old_surface = cache.popitem(last=False)
            cache_bytes -= (
                old_surface.get_width()
                * old_surface.get_height()
                * old_surface.get_bytesize()
            )
        self._impact_overlay_cache_bytes = max(0, cache_bytes)
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
        """Archetype-themed emanation for shared spell-cast impacts.

        The Arcanist keeps the classic arcane ring with orbiting runes. Other
        shared cast call sites retain distinct colors and motifs matching their
        damage type, while dedicated class-skill effects render separately.
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

    def _draw_spirit_beast_call(
        self,
        overlay: pygame.Surface,
        center: tuple[int, int],
        radius: int,
        alpha: int,
        bright: Color,
        dark: Color,
        progress: float,
    ) -> None:
        """Forest-green call ring and paw sigil for the Ranger's Spirit Beast."""
        call_color = self.mix(bright, (142, 202, 92), 0.42)
        ring_radius = max(4, int(radius * (0.32 + progress * 0.68)))
        ring_rect = pygame.Rect(0, 0, ring_radius * 2, max(4, ring_radius))
        ring_rect.center = center
        pygame.draw.ellipse(
            overlay,
            (*call_color, int(alpha * (0.58 - progress * 0.24))),
            ring_rect,
            max(1, WORLD_SCALE),
        )
        inner_rect = ring_rect.inflate(-max(2, radius // 4), -max(2, radius // 8))
        pygame.draw.ellipse(
            overlay,
            (*self.shade(call_color, -38), int(alpha * 0.28)),
            inner_rect,
            max(1, WORLD_SCALE),
        )

        paw_y = center[1] + max(1, int(radius * 0.05))
        pad_w = max(4, int(radius * 0.34))
        pad_h = max(3, int(radius * 0.24))
        pad = pygame.Rect(0, 0, pad_w, pad_h)
        pad.center = (center[0], paw_y)
        pygame.draw.ellipse(
            overlay,
            (*self.shade(call_color, 28), int(alpha * (0.82 - progress * 0.25))),
            pad,
        )
        toe_radius = max(2, radius // 11)
        toe_y = paw_y - pad_h // 2 - toe_radius
        for offset_x, offset_y in (
            (-toe_radius * 2, toe_radius // 2),
            (-toe_radius, -toe_radius // 2),
            (toe_radius, -toe_radius // 2),
            (toe_radius * 2, toe_radius // 2),
        ):
            pygame.draw.circle(
                overlay,
                (*call_color, int(alpha * (0.74 - progress * 0.22))),
                (center[0] + offset_x, toe_y + offset_y),
                toe_radius,
            )

        for side in (-1, 1):
            arc_rect = ring_rect.inflate(
                int(radius * (0.35 + progress * 0.25)),
                int(radius * (0.18 + progress * 0.12)),
            )
            start = math.pi * (0.64 if side < 0 else 1.64)
            pygame.draw.arc(
                overlay,
                (*self.mix(call_color, dark, 0.18), int(alpha * 0.34)),
                arc_rect,
                start,
                start + math.pi * 0.45,
                max(1, WORLD_SCALE),
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
        # to transparent. Built once per quantized size; final entity dimensions
        # are cached separately so the per-frame hot path only sets alpha + blits.
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

    def _scaled_soft_shadow(
        self, width: int, height: int, alpha: int = 255
    ) -> pygame.Surface:
        alpha = max(0, min(255, (int(alpha) // 8) * 8))
        key = (width, height, alpha)
        cache: dict[tuple[int, int, int], pygame.Surface] = getattr(
            self, "_scaled_soft_shadow_cache", {}
        )
        shadow = cache.get(key)
        if shadow is not None:
            return shadow
        if len(cache) >= 128:
            cache.pop(next(iter(cache)))
        if getattr(self, "mobile_mode", False):
            # Mobile shadows are tiny low-opacity patches; bilinear smoothscale
            # at cache-build time is a measurable ARM cost in crowds, while
            # nearest scaling is visually indistinguishable under a sprite.
            shadow = self._mobile_soft_shadow(width, height)
        else:
            template = self._soft_shadow_template(max(8, max(width, height)))
            shadow = pygame.transform.smoothscale(template, (width, height))
        shadow.set_alpha(alpha)
        shadow = optimize_immutable_alpha_surface(shadow, alpha=alpha)
        cache[key] = shadow
        self._scaled_soft_shadow_cache = cache
        return shadow

    @staticmethod
    def _mobile_soft_shadow(width: int, height: int) -> pygame.Surface:
        # Cheap radial falloff built directly at final size with concentric
        # ellipses (no scaling): center ~55% alpha, fading to transparent at
        # the edge. Constant work per unique (w, h) bucket, cached by caller.
        surf = pygame.Surface((width, height), pygame.SRCALPHA)
        surf.fill((0, 0, 0, 0))
        steps = 5
        cx, cy = width / 2.0, height / 2.0
        for i in range(steps):
            ratio = 1.0 - i / steps  # 1.0 outer -> 0.0 inner
            w = max(1, int(width * ratio))
            h = max(1, int(height * ratio))
            alpha = int(140 * (i / (steps - 1)) ** 1.4)
            rect = pygame.Rect(0, 0, w, h)
            rect.center = (int(cx), int(cy))
            pygame.draw.ellipse(surf, (0, 0, 0, alpha), rect)
        try:
            surf = surf.convert_alpha()
        except pygame.error:
            pass
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
        # Cache the final dimensions and quantized opacity. Keeping each source
        # immutable lets SDL retain its RLE encoding instead of rebuilding it
        # after a per-frame set_alpha call for every actor. Mobile uses the same
        # radial template at a lower opacity: steady-state cost remains one
        # cached alpha blit per actor, but contacts are transparent rather than
        # the opaque ellipses that previously read as black holes under sprites.
        mobile = bool(getattr(self, "mobile_mode", False))
        opacity = (136 if moving else 112) if mobile else (210 if moving else 175)
        opacity = max(0, min(255, int(opacity - lift * 6.0)))
        shadow = self._scaled_soft_shadow(scaled_w, scaled_h, opacity)
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
        glow_size = (
            int(42 * rare_scale) * WORLD_SCALE,
            int(20 * rare_scale) * WORLD_SCALE,
        )
        glow = self._cached_ellipse_overlay(
            "item_glow",
            glow_size,
            rarity_color,
            (int(55 + 45 * pulse) // 8) * 8,
            inner_color=self.shade(rarity_color, 45),
            inner_alpha=(int(22 + 30 * pulse) // 8) * 8,
            inner_inflate=(-glow_size[0] // 3, -glow_size[1] // 3),
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
            item_sprite = self._cached_rotated_surface(sprite, tilt)
        rect = item_sprite.get_rect(midbottom=(sx, sy + 4 * WORLD_SCALE - bob))
        self.screen.blit(item_sprite, rect)
        if math.hypot(item.x - self.player.x, item.y - self.player.y) < 1.0:
            label = self._cached_text_surface(
                self.small_font,
                f"E {rarity_icon} {item.display_name}",
                rarity_color,
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
        glow = self._cached_ellipse_overlay(
            "shop_sign_glow",
            (42 * WORLD_SCALE, 20 * WORLD_SCALE),
            gold,
            (int(40 + 35 * pulse) // 8) * 8,
        )
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
            label = self._cached_text_surface(
                self.small_font,
                f"E {self.rarity_icon(item.visible_rarity)} {item.display_name}",
                gold,
            )
            self.screen.blit(
                label, label.get_rect(center=(sx, rect.top - 10 * WORLD_SCALE))
            )

    def _guidance_glow_layer(
        self, w: int, h: int, *, clear: bool = True
    ) -> pygame.Surface:
        # The caller supplies tight, bucketed bounds around visible crack runs.
        # Reuse that small alpha layer without ever clearing/blitting the full
        # native Android viewport for a route that occupies only a narrow strip.
        surf = getattr(self, "_guidance_glow_surface", None)
        if surf is None or surf.get_size() != (w, h):
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            try:
                surf = surf.convert_alpha()
            except pygame.error:
                pass
            self._guidance_glow_surface = surf
            self._guidance_glow_content_key = None
            self._guidance_glow_blit_areas = ()
            clear = True
        if clear:
            surf.fill((0, 0, 0, 0))
        return surf

    def _cache_guidance_glow_blit_areas(self, surface: pygame.Surface) -> None:
        # The route is a handful of thin anti-aliased cracks inside a much larger
        # bounding rectangle. Split the already-rasterized layer into disjoint
        # chunks and retain only each chunk's occupied alpha bounds. Non-overlap
        # keeps the final source-over result byte-equivalent while avoiding a
        # hundreds-of-thousands-pixel transparent alpha traversal on Android.
        areas: list[pygame.Rect] = []
        chunk_size = 256
        bounds = surface.get_rect()
        for y in range(0, bounds.height, chunk_size):
            for x in range(0, bounds.width, chunk_size):
                chunk = pygame.Rect(
                    x,
                    y,
                    min(chunk_size, bounds.width - x),
                    min(chunk_size, bounds.height - y),
                )
                occupied = surface.subsurface(chunk).get_bounding_rect(min_alpha=1)
                if occupied.width > 0 and occupied.height > 0:
                    areas.append(occupied.move(chunk.topleft))
        self._guidance_glow_blit_areas = tuple(areas)

    def _blit_cached_guidance_glow(
        self, surface: pygame.Surface, destination: tuple[int, int]
    ) -> None:
        areas = getattr(self, "_guidance_glow_blit_areas", ())
        if not areas:
            return
        dest_x, dest_y = destination
        blits = [
            (surface, (dest_x + area.x, dest_y + area.y), area)
            for area in areas
        ]
        batch = getattr(self.screen, "blits", None)
        if batch is not None:
            batch(blits)
        else:
            for source, target, area in blits:
                self.screen.blit(source, target, area)

    def draw_story_relic_guidance(self) -> None:
        self._guidance_glow_blit_rect: pygame.Rect | None = None
        self._mobile_guidance_surface_size = (0, 0)
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
        warm = self.apply_mobile_lightweight_ambient_color(
            self.mix(accent, (255, 232, 142), 0.5)
        )
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
        shadow = self.apply_mobile_lightweight_ambient_color(
            self.shade(slab, -24)
        )
        lip = self.apply_mobile_lightweight_ambient_color(
            self.shade(slab, 16)
        )

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

        guidance_view = pygame.Rect(0, 0, screen_w, screen_h).inflate(
            TILE_W * 2, TILE_H * 2
        )
        lit_flags = [
            tile_lit(wx, wy) and guidance_view.collidepoint(raw_screen[index])
            for index, (wx, wy) in enumerate(crack_world)
        ]
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

        visible_runs = [
            [crack_points[index] for index in run]
            for run in runs
            if len(run) >= 2
        ]

        # Short branch stubs at a couple of interior points (only in open,
        # lit floor) so it reads as a real fracture rather than a drawn line.
        branch_segments: list[
            tuple[tuple[float, float], tuple[float, float]]
        ] = []
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
            branch_segments.append(
                ((bx, by), (bx + perp_x * stub_len, by + perp_y * stub_len))
            )

        # Target: a small worn ring groove lying flat on the iso floor (y
        # squashed to match the floor plane) in the same carved language, with
        # a faint warm pinprick at its center. Build its visible segments before
        # allocating the alpha surface so they contribute to the tight bounds.
        ring_segments: list[
            tuple[tuple[float, float], tuple[float, float]]
        ] = []
        ring_center: tuple[float, float] | None = None
        if tile_lit(tx, ty):
            target_sx, target_sy = self.world_to_screen(tx, ty)
            ring_cx = float(target_sx)
            ring_cy = float(target_sy - int(4 * WORLD_SCALE))
            ring_radius = 7.0 * WORLD_SCALE
            ring_view = pygame.Rect(0, 0, screen_w, screen_h).inflate(
                math.ceil(ring_radius * 2), math.ceil(ring_radius * 2)
            )
            if ring_view.collidepoint(ring_cx, ring_cy):
                r_tile_x, r_tile_y = int(tx), int(ty)
                tcx, tcy = self.world_to_screen(r_tile_x + 0.5, r_tile_y + 0.5)
                half_w = TILE_W / 2
                half_h = TILE_H / 2

                def in_diamond(px: float, py: float) -> bool:
                    return (
                        abs(px - tcx) / half_w + abs(py - tcy) / half_h
                    ) <= 0.97

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
                    if in_diamond(p0[0], p0[1]) and in_diamond(p1[0], p1[1]):
                        ring_segments.append((p0, p1))
                if in_diamond(ring_cx, ring_cy):
                    ring_center = (ring_cx, ring_cy)

        bounds_points = [point for run in visible_runs for point in run]
        for start, end in branch_segments:
            bounds_points.extend((start, end))
        for start, end in ring_segments:
            bounds_points.extend((start, end))
        if ring_center is not None:
            bounds_points.append(ring_center)
        if not bounds_points:
            return

        padding = max(4, int(3 * WORLD_SCALE))
        left = math.floor(min(point[0] for point in bounds_points)) - padding
        top = math.floor(min(point[1] for point in bounds_points)) - padding
        right = math.ceil(max(point[0] for point in bounds_points)) + padding + 1
        bottom = math.ceil(max(point[1] for point in bounds_points)) + padding + 1
        local_rect = pygame.Rect(left, top, right - left, bottom - top).clip(
            pygame.Rect(0, 0, screen_w, screen_h)
        )
        if local_rect.width <= 0 or local_rect.height <= 0:
            return

        # Bucket dimensions reduce reallocations as the camera moves by a pixel,
        # while clipping prevents a bucket at the edge from exceeding the target.
        bucket = 32
        layer_w = min(
            screen_w - local_rect.x,
            ((local_rect.width + bucket - 1) // bucket) * bucket,
        )
        layer_h = min(
            screen_h - local_rect.y,
            ((local_rect.height + bucket - 1) // bucket) * bucket,
        )
        # Content cache: the carved crack only changes shape when its screen
        # bounds move or the visibility run changes; re-rasterizing every
        # segment on every frame was the dominant mobile relic-glitch cost
        # (the overlay is alpha-blitted over lit floor, so stale frames also
        # left visible trails before the buffer cleared).
        content_key = (
            (layer_w, layer_h),
            groove_alpha,
            seep_alpha,
            ring_groove_alpha,
            ring_light_alpha,
            tuple(lit_flags),
            shadow,
            lip,
            warm,
            tuple(
                (point[0] - local_rect.x, point[1] - local_rect.y)
                for point in raw_screen
            ),
        )
        content_unchanged = (
            getattr(self, "_guidance_glow_content_key", None) == content_key
        )
        glow_layer = self._guidance_glow_layer(
            layer_w, layer_h, clear=not content_unchanged
        )
        blit_rect = glow_layer.get_rect(topleft=local_rect.topleft)
        self._guidance_glow_blit_rect = blit_rect.copy()
        self._mobile_guidance_surface_size = glow_layer.get_size()
        if content_unchanged:
            self._blit_cached_guidance_glow(glow_layer, blit_rect.topleft)
            return
        # Rasterizing below: the layer was cleared only after a cache miss.
        def local(point: tuple[float, float]) -> tuple[float, float]:
            return point[0] - blit_rect.x, point[1] - blit_rect.y

        for run_points in visible_runs:
            points = [local(point) for point in run_points]
            pygame.draw.aalines(glow_layer, (*shadow, groove_alpha), False, points)
            pygame.draw.aalines(
                glow_layer,
                (*lip, groove_alpha),
                False,
                [(point[0], point[1] - 1) for point in points],
            )
            pygame.draw.lines(
                glow_layer,
                (*warm, seep_alpha),
                False,
                [(point[0], point[1] + 1) for point in points],
                1,
            )

        for start, end in branch_segments:
            local_start = local(start)
            local_end = local(end)
            pygame.draw.aaline(
                glow_layer, (*shadow, groove_alpha), local_start, local_end
            )
            pygame.draw.aaline(
                glow_layer,
                (*lip, groove_alpha),
                (local_start[0], local_start[1] - 1),
                (local_end[0], local_end[1] - 1),
            )

        for start, end in ring_segments:
            local_start = local(start)
            local_end = local(end)
            pygame.draw.aaline(
                glow_layer, (*shadow, ring_groove_alpha), local_start, local_end
            )
            pygame.draw.aaline(
                glow_layer,
                (*lip, ring_groove_alpha),
                (local_start[0], local_start[1] - 1),
                (local_end[0], local_end[1] - 1),
            )
        if ring_center is not None:
            pygame.draw.circle(
                glow_layer,
                (*warm, ring_light_alpha),
                (round(ring_center[0] - blit_rect.x), round(ring_center[1] - blit_rect.y)),
                max(1, int(2 * WORLD_SCALE)),
            )

        self._guidance_glow_content_key = content_key
        self._cache_guidance_glow_blit_areas(glow_layer)
        self._blit_cached_guidance_glow(glow_layer, blit_rect.topleft)

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

        # Modern graphics use the authored PixelLab diamond; legacy graphics use
        # the procedural octahedron fallback. A slow tilt + bob give either relic a
        # floating, alive read.
        visual = self.sprites.item_visual(
            "story_relic",
            self.elapsed + item.x * 0.31 + item.y * 0.17,
            "Common",
        )
        tilt = math.sin(self.elapsed * 2.8 + item.y) * 3.0
        tilt_bucket = int(round(tilt)) if visual.is_asset else tilt
        # Tint + tilt are baked once per (frame, story accent, tilt bucket) and
        # cached. The additive tint is masked by the sprite's own alpha so the
        # colorkey-optimized asset cannot leak a magenta rectangle, and the
        # cached rotated frame drops the per-frame copy/rotate off the ARM path.
        sprite = self._story_relic_sprite(visual, accent, tilt_bucket)
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

    def _story_relic_sprite(
        self,
        visual: object,
        accent: Color,
        tilt: float,
    ) -> pygame.Surface:
        """Return the cached tinted + tilted relic sprite for this frame.

        The additive story tint is masked by the sprite's own alpha: the
        authored relic is colorkey-optimized for Android's blitter, and an
        unmasked BLEND_RGB_ADD paints the magenta colorkey background, which
        then leaks as a solid box (and a spinning rectangle once rotated).
        """

        surface = visual.surface  # type: ignore[attr-defined]
        is_asset = bool(visual.is_asset)  # type: ignore[attr-defined]
        key = (id(surface), is_asset, accent, tilt)
        cache = getattr(self, "_story_relic_sprite_cache", None)
        if not isinstance(cache, OrderedDict):
            cache = OrderedDict()
            self._story_relic_sprite_cache = cache
        cached = cache.get(key)
        if cached is not None and cached[0] is surface:
            cache.move_to_end(key)
            return cached[1]

        sprite = surface.copy()
        if is_asset:
            tint_add = tuple(round(channel * 0.28) for channel in accent)
            tint = pygame.Surface(sprite.get_size(), pygame.SRCALPHA)
            tint.fill((*tint_add, 255))
            # Keep the tint only where the relic art is actually opaque.
            tint.blit(sprite, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
            sprite.blit(tint, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        else:
            sprite.fill((*accent, 40), special_flags=pygame.BLEND_RGB_ADD)
        if abs(tilt) > 0.1:
            sprite = pygame.transform.rotate(sprite, tilt)
        sprite = optimize_immutable_alpha_surface(sprite)
        cache[key] = (surface, sprite)
        cache.move_to_end(key)
        while len(cache) > 96:
            cache.popitem(last=False)
        return sprite

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
        facing_x, facing_y, moving, loop_progress = self.friendly_npc_visual_state(
            guest
        )
        beat_lift, beat_accent = self.friendly_npc_beat_pulse(loop_progress, moving)
        body_lift = beat_lift * (1.1 if moving else 1.8)
        sx, sy = self.world_to_screen(guest.x, guest.y)
        color = guest.color if not guest.resolved else self.shade(guest.color, -60)
        self.draw_shadow(
            guest.x,
            guest.y,
            26,
            11,
            moving=False,
            lift=body_lift,
        )
        pulse = beat_accent
        # Subtle floor marker (a faint accent ring) so the quest NPC is still
        # distinguishable from a generic traveler, but without the bright
        # pulsing aura that made it read as a glowing quest beacon.
        ring = pygame.Surface((48 * WORLD_SCALE, 25 * WORLD_SCALE), pygame.SRCALPHA)
        ring_alpha = int(20 + 12 * pulse) if not guest.resolved else 14
        pygame.draw.ellipse(
            ring, (*color, ring_alpha), ring.get_rect(), max(1, WORLD_SCALE)
        )
        self.screen.blit(ring, ring.get_rect(center=(sx, sy + 4 * WORLD_SCALE)))

        motion = self.friendly_npc_motion(guest)
        direction = self.actor_sprite_direction(
            facing_x,
            facing_y,
            previous=motion.sprite_direction,
        )
        motion.sprite_direction = direction
        frame = self.sprites.story_guest_visual(
            self.elapsed,
            guest.resolved,
            direction=direction,
            moving=moving,
            dancing=not moving,
            clip_progress=loop_progress,
        )
        # Drawn as-is, like every other actor. The previous additive tint over
        # the whole sprite is what made the guest glow; normal humanoids are not
        # tinted at draw time.
        y_offset = 5.0 - body_lift
        if frame.is_asset:
            self.blit_resolved_sprite(frame, guest.x, guest.y, y_offset=y_offset)
        else:
            sprite = frame.surface
            self.screen.blit(
                sprite, sprite.get_rect(midbottom=(sx, sy + y_offset * WORLD_SCALE))
            )

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
        # Decorative, non-interactable flavor NPC. Generic humanoids reuse the
        # story-guest art; bar dancers and garden frogs have dedicated visuals.
        # No branch draws quest markers, labels, or interaction prompts.
        facing_x, facing_y, moving, loop_progress = self.friendly_npc_visual_state(npc)
        beat_lift, _beat_accent = self.friendly_npc_beat_pulse(
            loop_progress, moving
        )
        body_lift = beat_lift * (1.1 if moving else 1.8)
        sx, sy = self.world_to_screen(npc.x, npc.y)
        is_frog = npc.kind == "garden_frog"
        self.draw_shadow(
            npc.x,
            npc.y,
            18 if is_frog else 24,
            8 if is_frog else 10,
            moving=False,
            lift=body_lift,
        )
        motion = self.friendly_npc_motion(npc)
        direction = self.actor_sprite_direction(
            facing_x,
            facing_y,
            previous=motion.sprite_direction,
        )
        motion.sprite_direction = direction
        if is_frog:
            frame = self.sprites.garden_frog_visual(
                self.elapsed,
                direction=direction,
                moving=moving,
                dancing=not moving,
                clip_progress=loop_progress,
            )
        elif npc.kind == "bar_dancer":
            frame = self.sprites.bar_dancer_visual(
                self.elapsed,
                direction=direction,
                moving=moving,
                dancing=not moving,
                clip_progress=loop_progress,
            )
        else:
            frame = self.sprites.story_guest_visual(
                self.elapsed,
                False,
                direction=direction,
                moving=moving,
                dancing=not moving,
                clip_progress=loop_progress,
            )
        y_offset = 5.0 - body_lift
        if frame.is_asset:
            self.blit_resolved_sprite(frame, npc.x, npc.y, y_offset=y_offset)
        else:
            sprite = frame.surface
            self.screen.blit(
                sprite, sprite.get_rect(midbottom=(sx, sy + y_offset * WORLD_SCALE))
            )

    def draw_spirit_beast_pet_indicator(
        self, familiar: Familiar, sprite_rect: pygame.Rect
    ) -> bool:
        """Draw a compact paw badge when this beast can be petted now."""
        if not self.can_pet_spirit_beast_now(familiar):
            return False

        unit = max(1, WORLD_SCALE)
        size = 5 * unit
        center = size // 2

        def scaled(value: float) -> int:
            return round(value * size / 10.0)

        badge = pygame.Surface((size, size), pygame.SRCALPHA)
        color = self.skill_color()
        pygame.draw.circle(
            badge,
            (10, 16, 13, 90),
            (center, center),
            center - 1,
        )
        pygame.draw.circle(
            badge,
            (*color, 150),
            (center, center),
            center - 1,
            max(1, round(unit * 0.5)),
        )
        paw_color = (232, 244, 218, 180)
        toe_radius = max(1, scaled(1.0))
        for toe_x, toe_y in ((3.0, 4.0), (5.0, 3.0), (7.0, 4.0)):
            pygame.draw.circle(
                badge,
                paw_color,
                (scaled(toe_x), scaled(toe_y)),
                toe_radius,
            )
        pygame.draw.ellipse(
            badge,
            paw_color,
            pygame.Rect(
                scaled(3.0),
                scaled(5.0),
                max(1, scaled(4.0)),
                max(1, scaled(3.0)),
            ),
        )

        health_bar_clearance = (
            5 * unit if familiar.hp < familiar.max_hp else 2 * unit
        )
        bob = round(math.sin(self.elapsed * 4.2 + familiar.x) * unit * 0.35)
        badge_rect = badge.get_rect(
            midbottom=(
                sprite_rect.centerx,
                sprite_rect.top - health_bar_clearance - bob,
            )
        )
        self.screen.blit(badge, badge_rect)
        return True

    def draw_familiar(self, familiar: Familiar) -> None:
        sx, sy = self.world_to_screen(familiar.x, familiar.y)
        kind = getattr(familiar, "kind", "spirit")
        if kind == "spirit_beast":
            bob = 0.0
            shadow_w = 34 if familiar.champion else 28
            y_offset = 2.0
        else:
            bob = (
                math.sin(self.elapsed * 3.4 + familiar.x * 0.7 + familiar.y * 0.4)
                * 1.4
            )
            shadow_w = 30 if familiar.champion else (22 if familiar.sprite_variant else 18)
            y_offset = 5.0 - bob
        self.draw_shadow(familiar.x, familiar.y, shadow_w, 10, moving=familiar.moving)
        direction = self.actor_sprite_direction(
            getattr(familiar, "facing_x", 1.0),
            getattr(familiar, "facing_y", 0.0),
            previous=familiar.sprite_direction,
        )
        familiar.sprite_direction = direction
        pet_timer = max(0.0, getattr(familiar, "pet_anim_timer", 0.0))
        pet_duration = max(
            0.01, getattr(self, "SPIRIT_BEAST_PET_ANIMATION_DURATION", 0.8)
        )
        petting = kind == "spirit_beast" and pet_timer > 0.0
        attack_timer = max(0.0, getattr(familiar, "attack_anim_timer", 0.0))
        attack_duration = max(
            0.01, getattr(self, "FAMILIAR_ATTACK_ANIMATION_DURATION", 0.42)
        )
        attacking = not petting and attack_timer > 0.0
        # Locomotion uses the familiar's simulation-local phase. Sampling walk
        # from run-global elapsed made intermittent slow following restart on an
        # unrelated frame, which read as jitter; ambient idle can stay global.
        clip_time = (
            pet_duration - pet_timer
            if petting
            else familiar.anim_time
            if familiar.moving
            else self.elapsed
        )
        frame = self.sprites.familiar_visual(
            familiar.sprite_variant,
            clip_time,
            direction=direction,
            moving=familiar.moving,
            kind=kind,
            petting=petting,
            pet_progress=(1.0 - pet_timer / pet_duration) if petting else None,
            attacking=attacking,
            attack_progress=(1.0 - attack_timer / attack_duration)
            if attacking
            else None,
        )
        sprite = frame.surface
        if frame.is_asset:
            rect = self.blit_resolved_sprite(
                frame, familiar.x, familiar.y, y_offset=y_offset
            )
        else:
            rect = sprite.get_rect(midbottom=(sx, sy + y_offset * WORLD_SCALE))
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
                (145, 214, 105)
                if kind == "spirit_beast"
                else (160, 235, 230),
                (sx - bar_w // 2, bar_y, fill_w, bar_h),
            )
        if kind == "spirit_beast":
            self.draw_spirit_beast_pet_indicator(familiar, rect)

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

    def _projectile_trail_surface(self, color: Color, alpha: int) -> pygame.Surface:
        normalized_color = (int(color[0]), int(color[1]), int(color[2]))
        key = (*normalized_color, int(alpha))
        cache: dict[tuple[int, int, int, int], pygame.Surface] = getattr(
            self, "_projectile_trail_cache", {}
        )
        trail = cache.get(key)
        if trail is not None:
            return trail
        if len(cache) >= 128:
            cache.pop(next(iter(cache)))
        trail = pygame.Surface((10 * WORLD_SCALE, 5 * WORLD_SCALE), pygame.SRCALPHA)
        pygame.draw.ellipse(trail, (*normalized_color, alpha), trail.get_rect())
        cache[key] = trail
        self._projectile_trail_cache = cache
        return trail

    def draw_projectile(self, projectile: Projectile) -> None:
        sx, sy = self.world_to_screen(projectile.x, projectile.y)
        sprite = self.sprites.projectile_frame(
            projectile.owner,
            projectile.anim_time,
            archetype=getattr(projectile, "archetype", ""),
        )
        vx, vy = self.iso_screen_direction(projectile.vx, projectile.vy)
        color = projectile.color or (
            (70, 165, 255) if projectile.owner == "player" else (210, 83, 238)
        )
        px, py = -vy, vx
        flicker = 0.5 + 0.5 * math.sin(self.elapsed * 18.0 + projectile.x)
        trail_samples = (
            ((1, 136), (3, 54))
            if getattr(self, "mobile_mode", False)
            else ((1, 136), (2, 92), (3, 54), (4, 26))
        )
        for step, alpha in trail_samples:
            trail = self._projectile_trail_surface(color, alpha)
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
        sprite = self._cached_rotated_surface(
            sprite,
            angle + math.sin(self.elapsed * 20.0) * 4,
            step_degrees=PROJECTILE_ROTATION_STEP_DEGREES,
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
