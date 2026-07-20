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
import random
from typing import Any, Sequence

import pygame

from ..models import Archetype, Color

MenuRow = tuple[str, str, str]


class MenuBaseMixin:
    """Shared menu renderer primitives and state.

    The renderer uses a small set of primitives—centered panels, fixed-width key
    badges, wrapped body text, and clipped single-line labels—so every menu uses
    the same alignment rules instead of hand-placed text offsets.

    The visual language is grim and gothic: deep obsidian backgrounds, cold
    stone panels with chiseled bevels, iron corner studs, parchment header
    bands, and a restrained gold/ember accent. All ornament is procedural so the
    look stays crisp at any UI scale.
    """

    # --- Gothic palette -----------------------------------------------------
    # Deep, desaturated obsidian/charcoal base with cold blue undertones.
    BG = (10, 9, 13)
    BG_DEEP = (5, 5, 8)
    PANEL = (20, 18, 24)
    PANEL_2 = (28, 25, 33)
    PANEL_INK = (14, 12, 17)  # recessed inner surface
    STONE_LIGHT = (54, 49, 58)  # bevel highlight
    STONE_SHADOW = (10, 9, 13)  # bevel shadow
    IRON = (74, 70, 82)  # studs / rivets
    IRON_LIGHT = (118, 110, 128)
    IRON_DARK = (32, 30, 38)

    # Text tones — parchment and bone rather than pure white.
    TEXT = (224, 214, 196)
    MUTED = (148, 138, 124)
    TITLE = (236, 214, 168)  # aged gold
    WARNING = (214, 168, 92)  # ember gold
    BLOOD = (152, 38, 40)
    BLOOD_LIGHT = (196, 64, 60)

    # Cached procedural textures (lazily built, keyed by size + scale).
    _stone_cache: dict[tuple[int, int, int], pygame.Surface] = {}

    def __init__(
        self, game: Any, archetypes: Sequence[Archetype], dungeon_depth: int
    ) -> None:
        self.g = game
        self.archetypes = archetypes
        self.dungeon_depth = dungeon_depth
        self._menu_font_cache: dict[int, pygame.font.Font] = {}
        self._menu_backdrop_cache: tuple[object, pygame.Surface] | None = None

    # --- Accessors ----------------------------------------------------------
    @property
    def screen(self) -> pygame.Surface:
        return self.g.screen

    def u(self, value: int) -> int:
        return self.g.ui(value)

    def shade(self, color: Color, amount: int) -> Color:
        return self.g.shade(color, amount)

    def mix(self, a: Color, b: Color, ratio: float) -> Color:
        return (
            int(a[0] * (1.0 - ratio) + b[0] * ratio),
            int(a[1] * (1.0 - ratio) + b[1] * ratio),
            int(a[2] * (1.0 - ratio) + b[2] * ratio),
        )

    def accent(self) -> Color:
        return self.g.theme.accent

    def asset_ui_active(self) -> bool:
        library = getattr(self.g, "ui_assets", None)
        return (
            not getattr(self.g, "legacy_graphics", False)
            and library is not None
            and bool(getattr(library, "available", False))
        )

    def ui_asset(self, key: str, size: tuple[int, int]) -> pygame.Surface | None:
        if not self.asset_ui_active():
            return None
        return self.g.ui_assets.render(key, size)

    def ui_content_rect(self, key: str, rect: pygame.Rect) -> pygame.Rect | None:
        if not self.asset_ui_active():
            return None
        return self.g.ui_assets.content_rect(key, rect)

    # --- Text helpers -------------------------------------------------------
    def ellipsize(self, text: str, font: pygame.font.Font, max_width: int) -> str:
        max_width = max(1, max_width)
        if font.size(text)[0] <= max_width:
            return text
        suffix = "…"
        while text and font.size(text + suffix)[0] > max_width:
            text = text[:-1]
        return text + suffix if text else suffix

    def wrap_text(self, text: str, font: pygame.font.Font, max_width: int) -> list[str]:
        max_width = max(1, max_width)
        if not text:
            return [""]
        lines: list[str] = []
        current = ""
        for word in text.split():
            candidate = word if not current else f"{current} {word}"
            if font.size(candidate)[0] <= max_width:
                current = candidate
                continue
            if current:
                lines.append(current)
            current = self.ellipsize(word, font, max_width)
        if current:
            lines.append(current)
        return lines or [""]

    def draw_text(
        self,
        text: str,
        font: pygame.font.Font,
        color: Color,
        rect: pygame.Rect,
        align: str = "left",
        valign: str = "top",
    ) -> None:
        if rect.width <= 0 or rect.height <= 0:
            return
        surface = font.render(self.ellipsize(text, font, rect.width), True, color)
        if align == "center":
            x = rect.centerx - surface.get_width() // 2
        elif align == "right":
            x = rect.right - surface.get_width()
        else:
            x = rect.x
        if valign == "center":
            y = rect.centery - surface.get_height() // 2
        elif valign == "bottom":
            y = rect.bottom - surface.get_height()
        else:
            y = rect.y
        old_clip = self.screen.get_clip()
        text_clip = rect.clip(self.screen.get_rect()).clip(old_clip)
        self.screen.set_clip(text_clip)
        self.screen.blit(surface, (x, y))
        self.screen.set_clip(old_clip)

    def fit_menu_font(
        self,
        preferred: pygame.font.Font,
        *,
        max_height: int,
        max_width: int,
        texts: Sequence[str] = (),
        minimum_size: int = 10,
    ) -> pygame.font.Font:
        """Return the largest cached default font that fits physical bounds.

        UI scale is an accessibility preference, but a scaled font must not make
        a menu unusable on a small window. Callers provide the real pixel budget;
        the preferred scaled font is retained whenever it fits, and only then is
        a smaller physical font selected. Render-time construction is avoided by
        caching the small set of fallback point sizes on the menu renderer.
        """

        max_height = max(1, int(max_height))
        max_width = max(1, int(max_width))
        samples = tuple(text for text in texts if text)

        def fits(candidate: pygame.font.Font) -> bool:
            return candidate.get_height() <= max_height and all(
                candidate.size(text)[0] <= max_width for text in samples
            )

        if fits(preferred):
            return preferred

        minimum_size = max(8, int(minimum_size))

        def cached_font(point_size: int) -> pygame.font.Font:
            font = self._menu_font_cache.get(point_size)
            if font is None:
                font = pygame.font.Font(None, point_size)
                self._menu_font_cache[point_size] = font
            return font

        best = cached_font(minimum_size)
        low = minimum_size
        high = max(low, min(512, max_height * 2 + 4))
        while low <= high:
            point_size = (low + high) // 2
            candidate = cached_font(point_size)
            if fits(candidate):
                best = candidate
                low = point_size + 1
            else:
                high = point_size - 1
        return best

    def draw_tag_icon(self, tag: str, rect: pygame.Rect, color: Color) -> None:
        """Draw a small procedural glyph for an affix tag inside ``rect``.

        Pygame's bundled default font does not guarantee emoji/symbol glyph
        coverage, so tag icons are drawn with primitives (matching the project's
        procedural pixel-art style) instead of font characters. Each icon fits
        inside ``rect`` and strokes/fills with ``color``.
        """
        tag = tag.lower()
        cx, cy = rect.center
        size = min(rect.width, rect.height)
        if size < 3:
            return
        screen = self.screen
        r = size // 2
        w = max(1, size // 7)

        def line(p1, p2, width=w):
            pygame.draw.line(screen, color, p1, p2, width)

        def poly(points, width=0):
            if width:
                pygame.draw.polygon(screen, color, points, width)
            else:
                pygame.draw.polygon(screen, color, points)

        def circle(center, radius, width=0):
            if radius <= 0:
                return
            if width:
                pygame.draw.circle(screen, color, center, radius, width)
            else:
                pygame.draw.circle(screen, color, center, radius)

        def star4(points=4, outer=r, inner=r * 0.38, width=0):
            pts = []
            for i in range(points * 2):
                ang = math.radians((360 / (points * 2)) * i - 90)
                rad = outer if i % 2 == 0 else inner
                pts.append((cx + math.cos(ang) * rad, cy + math.sin(ang) * rad))
            poly(pts, width)

        def arrow(oy=0, shaft=r * 0.7, head=r * 0.35):
            line((cx - shaft, cy + oy), (cx + shaft * 0.6, cy + oy))
            poly(
                [
                    (cx + shaft, cy + oy),
                    (cx + shaft * 0.4, cy + oy - head),
                    (cx + shaft * 0.4, cy + oy + head),
                ],
                width=w,
            )

        # --- icon families ---------------------------------------------------
        if tag == "fire":
            poly(
                [
                    (cx, cy - r),
                    (cx + r * 0.7, cy + r * 0.6),
                    (cx - r * 0.7, cy + r * 0.6),
                ],
                width=w,
            )
            poly(
                [
                    (cx, cy - r * 0.3),
                    (cx + r * 0.35, cy + r * 0.45),
                    (cx - r * 0.35, cy + r * 0.45),
                ],
                width=w,
            )
        elif tag == "frost":
            for ang in (0, 60, 120):
                dx = math.cos(math.radians(ang)) * r * 0.85
                dy = math.sin(math.radians(ang)) * r * 0.85
                line((cx - dx, cy - dy), (cx + dx, cy + dy))
        elif tag in ("poison", "blood", "bleed"):
            circle((cx, cy + int(r * 0.25)), int(r * 0.5), width=w)
            line((cx - int(r * 0.4), cy + int(r * 0.05)), (cx, cy - int(r * 0.7)))
            line((cx + int(r * 0.4), cy + int(r * 0.05)), (cx, cy - int(r * 0.7)))
        elif tag in ("arcane", "critical", "proc"):
            star4(width=w)
        elif tag == "shadow":
            pygame.draw.circle(screen, color, (cx, cy), int(r * 0.8), 0)
            pygame.draw.circle(
                screen,
                self.PANEL_INK,
                (cx + int(r * 0.35), cy - int(r * 0.1)),
                int(r * 0.65),
            )
        elif tag == "holy":
            line((cx, cy - r * 0.7), (cx, cy + r * 0.7))
            line((cx - r * 0.5, cy - r * 0.1), (cx + r * 0.5, cy - r * 0.1))
        elif tag == "physical":
            line((cx - r * 0.7, cy + r * 0.7), (cx + r * 0.7, cy - r * 0.7))
        elif tag == "melee":
            line((cx, cy - r * 0.8), (cx, cy + r * 0.5))
            line((cx - r * 0.4, cy - r * 0.3), (cx + r * 0.4, cy - r * 0.3))
            poly(
                [
                    (cx, cy - r * 0.95),
                    (cx - r * 0.15, cy - r * 0.6),
                    (cx + r * 0.15, cy - r * 0.6),
                ],
                width=w,
            )
        elif tag == "attack_speed":
            poly(
                [
                    (cx - r * 0.2, cy - r * 0.8),
                    (cx + r * 0.3, cy - r * 0.1),
                    (cx, cy - r * 0.1),
                    (cx + r * 0.2, cy + r * 0.8),
                    (cx - r * 0.3, cy + r * 0.1),
                    (cx, cy + r * 0.1),
                ],
                width=w,
            )
        elif tag in ("cast_speed", "spell"):
            poly(
                [
                    (cx, cy - r * 0.8),
                    (cx + r * 0.2, cy),
                    (cx, cy + r * 0.8),
                    (cx - r * 0.2, cy),
                ],
                width=w,
            )
            poly(
                [
                    (cx - r * 0.8, cy),
                    (cx, cy + r * 0.2),
                    (cx + r * 0.8, cy),
                    (cx, cy - r * 0.2),
                ],
                width=w,
            )
        elif tag in ("movement", "bolt", "knockback", "retaliate"):
            arrow()
        elif tag == "dash":
            for ox in (-r * 0.3, r * 0.3):
                line((cx + ox - r * 0.2, cy - r * 0.5), (cx + ox + r * 0.2, cy))
                line((cx + ox + r * 0.2, cy), (cx + ox - r * 0.2, cy + r * 0.5))
        elif tag == "lifesteal":
            circle((cx - int(r * 0.3), cy - int(r * 0.15)), int(r * 0.35), width=w)
            circle((cx + int(r * 0.3), cy - int(r * 0.15)), int(r * 0.35), width=w)
            poly([(cx - r * 0.6, cy), (cx + r * 0.6, cy), (cx, cy + r * 0.7)], width=w)
        elif tag == "thorns":
            for ox in (-r * 0.5, 0, r * 0.5):
                poly(
                    [
                        (ox + cx - r * 0.15, cy + r * 0.6),
                        (ox + cx, cy - r * 0.6),
                        (ox + cx + r * 0.15, cy + r * 0.6),
                    ],
                    width=w,
                )
        elif tag == "nova":
            circle((cx, cy), int(r * 0.7), width=w)
            circle((cx, cy), max(1, w), width=0)
        elif tag in ("guard", "ward", "armor"):
            poly(
                [
                    (cx - r * 0.6, cy - r * 0.6),
                    (cx + r * 0.6, cy - r * 0.6),
                    (cx + r * 0.6, cy + r * 0.2),
                    (cx, cy + r * 0.8),
                    (cx - r * 0.6, cy + r * 0.2),
                ],
                width=w,
            )
            if tag == "ward":
                line((cx, cy - r * 0.35), (cx, cy + r * 0.45))
                line((cx - r * 0.3, cy - r * 0.05), (cx + r * 0.3, cy - r * 0.05))
        elif tag == "control":
            pygame.draw.rect(
                screen,
                color,
                pygame.Rect(
                    cx - int(r * 0.7), cy - int(r * 0.2), int(r * 0.7), int(r * 0.4)
                ),
                w,
                border_radius=int(r * 0.2),
            )
            pygame.draw.rect(
                screen,
                color,
                pygame.Rect(cx, cy - int(r * 0.2), int(r * 0.7), int(r * 0.4)),
                w,
                border_radius=int(r * 0.2),
            )
        elif tag == "curse":
            line((cx - r * 0.6, cy - r * 0.6), (cx + r * 0.6, cy + r * 0.6))
            line((cx - r * 0.6, cy + r * 0.6), (cx + r * 0.6, cy - r * 0.6))
        elif tag == "beast":
            circle((cx, cy + int(r * 0.3)), int(r * 0.35), width=w)
            for ox in (-r * 0.4, 0, r * 0.4):
                circle(
                    (cx + int(ox), cy - int(r * 0.4)), max(1, int(r * 0.15)), width=w
                )
        elif tag == "spirit":
            circle((cx, cy - int(r * 0.2)), int(r * 0.4), width=w)
            line((cx - r * 0.3, cy + r * 0.2), (cx + r * 0.3, cy + r * 0.2))
            line((cx - r * 0.2, cy + r * 0.5), (cx + r * 0.2, cy + r * 0.5))
        elif tag == "stealth":
            pygame.draw.ellipse(
                screen,
                color,
                pygame.Rect(
                    cx - int(r * 0.7), cy - int(r * 0.35), int(r * 1.4), int(r * 0.7)
                ),
                w,
            )
            circle((cx, cy), max(1, int(r * 0.2)), width=0)
        elif tag == "survival":
            pygame.draw.ellipse(
                screen,
                color,
                pygame.Rect(
                    cx - int(r * 0.5), cy - int(r * 0.6), int(r * 1.0), int(r * 1.2)
                ),
                w,
            )
            line((cx - r * 0.3, cy + r * 0.5), (cx + r * 0.3, cy - r * 0.5))
        elif tag == "counter":
            pygame.draw.arc(
                screen,
                color,
                pygame.Rect(
                    cx - int(r * 0.6), cy - int(r * 0.6), int(r * 1.2), int(r * 1.2)
                ),
                0.5,
                5.5,
                w,
            )
            poly(
                [
                    (cx + int(r * 0.5), cy - int(r * 0.5)),
                    (cx + int(r * 0.6), cy - int(r * 0.1)),
                    (cx + int(r * 0.1), cy - int(r * 0.5)),
                ],
                width=w,
            )
        elif tag == "legendary":
            poly(
                [
                    (cx - r * 0.7, cy + r * 0.4),
                    (cx - r * 0.7, cy - r * 0.2),
                    (cx - r * 0.4, cy + r * 0.1),
                    (cx, cy - r * 0.5),
                    (cx + r * 0.4, cy + r * 0.1),
                    (cx + r * 0.7, cy - r * 0.2),
                    (cx + r * 0.7, cy + r * 0.4),
                ],
                width=w,
            )
        elif tag == "risk":
            poly(
                [
                    (cx, cy - r * 0.7),
                    (cx + r * 0.7, cy + r * 0.6),
                    (cx - r * 0.7, cy + r * 0.6),
                ],
                width=w,
            )
            line((cx, cy - r * 0.2), (cx, cy + r * 0.2))
            circle((cx, cy + int(r * 0.4)), max(1, w), width=0)
        elif tag == "volley":
            for oy in (-r * 0.4, 0, r * 0.4):
                line((cx - r * 0.6, cy + oy), (cx + r * 0.3, cy + oy))
                poly(
                    [
                        (cx + r * 0.5, cy + oy),
                        (cx + r * 0.2, cy + oy - r * 0.2),
                        (cx + r * 0.2, cy + oy + r * 0.2),
                    ],
                    width=w,
                )
        else:
            # Generic fallback: a small diamond so unknown tags still read as a tag.
            poly(
                [
                    (cx, cy - r * 0.7),
                    (cx + r * 0.5, cy),
                    (cx, cy + r * 0.7),
                    (cx - r * 0.5, cy),
                ],
                width=w,
            )

    def draw_wrapped_text(
        self,
        text: str,
        font: pygame.font.Font,
        color: Color,
        rect: pygame.Rect,
        line_gap: int | None = None,
    ) -> int:
        line_gap = line_gap or max(font.get_height() + 3, self.u(18))
        y = rect.y
        for line in self.wrap_text(text, font, rect.width):
            if y + font.get_height() > rect.bottom:
                return y
            if line:
                self.draw_text(
                    line, font, color, pygame.Rect(rect.x, y, rect.width, line_gap)
                )
            y += line_gap
        return y

    # --- Procedural gothic textures ---------------------------------------
    def _stone_texture(self, w: int, h: int) -> pygame.Surface:
        """A cached, tileable cold-stone noise texture used for backdrops."""
        scale = self.g.ui_scale
        key = (w, h, scale)
        cached = self._stone_cache.get(key)
        if cached is not None:
            return cached
        # Build at a modest resolution then scale up for performance + grit.
        tw, th = max(1, w // (4 * scale) or 1), max(1, h // (4 * scale) or 1)
        surf = pygame.Surface((tw, th))
        surf.fill(self.BG_DEEP)
        rng = random.Random(0xBEEF)
        for _ in range(tw * th // 2):
            x = rng.randint(0, tw - 1)
            y = rng.randint(0, th - 1)
            shade = rng.randint(-10, 14)
            base = surf.get_at((x, y))
            surf.set_at(
                (x, y),
                (
                    max(0, min(255, base[0] + shade)),
                    max(0, min(255, base[1] + shade)),
                    max(0, min(255, base[2] + shade)),
                ),
            )
        # A few hairline cracks for ancient-stone character.
        for _ in range(max(2, th // 24)):
            cx = rng.randint(0, tw - 1)
            cy = rng.randint(0, th - 1)
            length = rng.randint(4, max(5, tw // 3))
            angle = rng.uniform(0, math.tau)
            for i in range(length):
                px = int(cx + math.cos(angle) * i)
                py = int(cy + math.sin(angle) * i)
                if 0 <= px < tw and 0 <= py < th:
                    surf.set_at((px, py), self.STONE_SHADOW)
        scaled = pygame.transform.smoothscale(surf, (w, h))
        self._stone_cache[key] = scaled
        return scaled

    def draw_menu_backdrop(self) -> None:
        width, height = self.screen.get_size()
        accent = self.accent()
        key = (
            "menu.background.title"
            if getattr(self.g, "state", "") == "title"
            else "menu.background"
        )
        asset = self.ui_asset(key, (width, height))
        if asset is None and key != "menu.background":
            asset = self.ui_asset("menu.background", (width, height))
        if asset is not None:
            cache_key = (
                key,
                width,
                height,
                id(asset),
                tuple(accent),
                tuple(self.screen.get_masks()),
                self.g.ui_scale,
            )
            cached = self._menu_backdrop_cache
            if cached is None or cached[0] != cache_key:
                backdrop = pygame.Surface((width, height)).convert(self.screen)
                backdrop.fill(self.BG_DEEP)
                backdrop.blit(asset, (0, 0))
                wash = pygame.Surface((width, height), pygame.SRCALPHA)
                wash.fill((*self.shade(accent, -126), 34))
                backdrop.blit(wash, (0, 0))
                cached = (cache_key, backdrop)
                self._menu_backdrop_cache = cached
            self.screen.blit(cached[1], (0, 0))
            return

        # Base cold-obsidian wash with a faint stone texture for depth.
        self.screen.fill(self.BG_DEEP)
        stone = self._stone_texture(width, height)
        self.screen.blit(stone, (0, 0))

        backdrop = pygame.Surface((width, height), pygame.SRCALPHA)

        # Cold moonlight pools — desaturated, off-center, never bright.
        pygame.draw.ellipse(
            backdrop,
            (*self.shade(accent, -96), 30),
            pygame.Rect(-width // 4, -height // 5, width * 3 // 4, height * 3 // 4),
        )
        pygame.draw.ellipse(
            backdrop,
            (*self.shade(accent, -120), 24),
            pygame.Rect(width // 2, height // 8, width * 2 // 3, height * 2 // 3),
        )

        # Faint gothic arch silhouettes — three nested arches framing the title.
        arch_color = (*self.shade(accent, -128), 22)
        arch_w = max(self.u(120), width // 6)
        arch_h = max(self.u(220), height * 2 // 5)
        arch_cx = width // 2
        arch_cy = int(height * 0.34)
        for i, scale in enumerate((1.0, 0.78, 0.56)):
            w = int(arch_w * scale)
            h = int(arch_h * scale)
            rect = pygame.Rect(arch_cx - w // 2, arch_cy - h // 2, w, h)
            points = self._arch_points(rect, shoulder=0.62)
            pygame.draw.polygon(backdrop, arch_color, points)
            pygame.draw.lines(
                backdrop,
                (*self.shade(accent, -90), 40),
                True,
                points,
                max(1, self.u(1)),
            )

        # Distant diamond sigils — occult, very faint.
        diamond_color = (*self.shade(accent, -118), 22)
        for center_x, center_y, size in (
            (width // 5, height * 3 // 5, max(70, width // 9)),
            (width * 4 // 5, height * 7 // 12, max(90, width // 8)),
            (width // 2, height * 4 // 5, max(120, width // 6)),
        ):
            points = [
                (center_x, center_y - size // 2),
                (center_x + size, center_y),
                (center_x, center_y + size // 2),
                (center_x - size, center_y),
            ]
            pygame.draw.polygon(backdrop, diamond_color, points)
            pygame.draw.lines(
                backdrop,
                (*self.shade(accent, -80), 36),
                True,
                points,
                max(1, self.u(1)),
            )

        # Bottom vignette — sink the foreground into shadow.
        pygame.draw.ellipse(
            backdrop,
            (0, 0, 0, 96),
            pygame.Rect(-width // 5, height * 2 // 3, width * 7 // 5, height // 2),
        )

        self.screen.blit(backdrop, (0, 0))
        self._draw_edge_vignette()

    def _draw_edge_vignette(self) -> None:
        width, height = self.screen.get_size()
        vignette = pygame.Surface((width, height), pygame.SRCALPHA)
        steps = 6
        for i in range(steps):
            alpha = int(8 + i * 10)
            inset = i * max(2, self.u(6))
            if inset * 2 >= width or inset * 2 >= height:
                break
            pygame.draw.rect(
                vignette,
                (0, 0, 0, alpha),
                vignette.get_rect().inflate(-inset * 2, -inset * 2),
                max(1, self.u(2)),
                border_radius=self.u(6),
            )
        self.screen.blit(vignette, (0, 0))

    def _arch_points(
        self, rect: pygame.Rect, shoulder: float = 0.6, segments: int = 18
    ) -> list[tuple[int, int]]:
        """Return a closed gothic-arch outline (rectangle with a rounded top)."""
        shoulder = max(0.1, min(0.95, shoulder))
        top_y = rect.y
        shoulder_y = rect.y + int(rect.height * shoulder)
        bottom_y = rect.bottom
        left_x = rect.x
        right_x = rect.right
        points: list[tuple[int, int]] = [(left_x, bottom_y), (left_x, shoulder_y)]
        cx = rect.centerx
        rx = max(1, rect.width // 2)
        ry = max(1, shoulder_y - top_y)
        for i in range(segments + 1):
            t = i / segments
            angle = math.pi + t * math.pi  # pi -> 2pi sweeps the top arc
            px = cx + int(math.cos(angle) * rx)
            py = shoulder_y + int(math.sin(angle) * ry)
            points.append((px, py))
        points.append((right_x, shoulder_y))
        points.append((right_x, bottom_y))
        return points

    # --- Ornate panel primitive -------------------------------------------
    def menu_panel_key(self, rect: pygame.Rect) -> str:
        return (
            "menu.panel.compact"
            if rect.width * 10 <= rect.height * 17
            else "menu.panel"
        )

    def _menu_panel_keys(self, rect: pygame.Rect) -> tuple[str, ...]:
        primary = self.menu_panel_key(rect)
        return (primary, "menu.panel") if primary != "menu.panel" else (primary,)

    def menu_panel_content_rect(self, rect: pygame.Rect) -> pygame.Rect | None:
        """Return the safe area for the same authored frame used by ``panel``."""
        for key in self._menu_panel_keys(rect):
            if self.ui_asset(key, rect.size) is None:
                continue
            safe = self.ui_content_rect(key, rect)
            if safe is not None:
                return safe
        return None

    def inset_panel(
        self, rect: pygame.Rect, accent: Color | None = None, alpha: int = 238
    ) -> tuple[pygame.Rect, bool]:
        """Draw a nested content frame and return its safe area and asset state."""
        target = pygame.Rect(rect)
        if target.width <= 0 or target.height <= 0:
            return target, False

        asset = self.ui_asset("menu.panel.inset", target.size)
        safe = (
            self.ui_content_rect("menu.panel.inset", target)
            if asset is not None
            else None
        )
        if asset is not None and safe is not None:
            self.screen.blit(asset, target)
            return safe, True

        accent = accent or self.accent()
        radius = max(2, self.u(7))
        body = pygame.Surface(target.size, pygame.SRCALPHA)
        pygame.draw.rect(
            body,
            (*self.PANEL_INK, max(0, min(255, alpha))),
            body.get_rect(),
            border_radius=radius,
        )
        self.screen.blit(body, target)
        pygame.draw.rect(
            self.screen,
            self.shade(accent, -58),
            target,
            max(1, self.u(1)),
            border_radius=radius,
        )
        inner_bevel = target.inflate(-self.u(2), -self.u(2))
        pygame.draw.rect(
            self.screen,
            self.IRON_DARK,
            inner_bevel,
            max(1, self.u(1)),
            border_radius=max(1, radius - self.u(1)),
        )
        pad_x = min(max(self.u(10), 10), max(1, target.width // 4))
        pad_y = min(max(self.u(8), 8), max(1, target.height // 4))
        return target.inflate(-pad_x * 2, -pad_y * 2), False

    def panel(
        self, rect: pygame.Rect, accent: Color | None = None, alpha: int = 245
    ) -> bool:
        """Draw a panel and report whether authored asset art was used."""
        accent = accent or self.accent()
        radius = self.u(10)

        for panel_key in self._menu_panel_keys(rect):
            asset = self.ui_asset(panel_key, rect.size)
            safe = (
                self.ui_content_rect(panel_key, rect)
                if asset is not None
                else None
            )
            if asset is not None and safe is not None:
                self.screen.blit(asset, rect)
                return True

        # The procedural fallback keeps its original soft drop shadow.
        shadow = rect.move(max(2, self.u(3)), max(3, self.u(5)))
        shadow_surf = pygame.Surface(shadow.size, pygame.SRCALPHA)
        pygame.draw.rect(
            shadow_surf, (0, 0, 0, 150), shadow_surf.get_rect(), border_radius=radius
        )
        self.screen.blit(shadow_surf, shadow)

        # Body — recessed stone with a subtle vertical gradient.
        if alpha < 255:
            body = pygame.Surface(rect.size, pygame.SRCALPHA)
            self._fill_stone_gradient(body, accent, alpha)
            self.screen.blit(body, rect)
        else:
            self._fill_stone_gradient(self.screen.subsurface(rect), accent, 255)

        # Outer bevel — dark rim then light rim, gives a chiseled edge.
        pygame.draw.rect(
            self.screen,
            self.STONE_SHADOW,
            rect,
            max(1, self.u(2)),
            border_radius=radius,
        )
        inner_bevel = rect.inflate(-self.u(2), -self.u(2))
        pygame.draw.rect(
            self.screen,
            self.STONE_LIGHT,
            inner_bevel,
            max(1, self.u(1)),
            border_radius=max(1, radius - self.u(1)),
        )

        # Gold inner trim — the gothic accent line.
        trim = inner_bevel.inflate(-self.u(4), -self.u(4))
        pygame.draw.rect(
            self.screen,
            self.shade(accent, -32),
            trim,
            max(1, self.u(1)),
            border_radius=max(1, radius - self.u(2)),
        )

        # Iron corner studs — four rivets framing the panel.
        stud_r = max(2, self.u(3))
        inset = self.u(8)
        for corner in (
            (rect.x + inset, rect.y + inset),
            (rect.right - inset, rect.y + inset),
            (rect.x + inset, rect.bottom - inset),
            (rect.right - inset, rect.bottom - inset),
        ):
            pygame.draw.circle(self.screen, self.IRON_DARK, corner, stud_r + 1)
            pygame.draw.circle(self.screen, self.IRON, corner, stud_r)
            pygame.draw.circle(
                self.screen,
                self.IRON_LIGHT,
                (corner[0] - 1, corner[1] - 1),
                max(1, stud_r - 1),
            )
        return False

    def _fill_stone_gradient(
        self, surface: pygame.Surface, accent: Color, alpha: int
    ) -> None:
        """Vertical gradient from a slightly lit top to a deep recessed bottom."""
        w, h = surface.get_size()
        if w <= 0 or h <= 0:
            return
        top = self.mix(self.PANEL, accent, 0.06)
        bottom = self.PANEL_INK
        # Draw a few horizontal bands for a smooth-enough gradient without
        # per-pixel work; cheap and reads as cold stone.
        bands = max(8, min(48, h))
        for i in range(bands):
            t = i / max(1, bands - 1)
            color = (
                int(top[0] * (1 - t) + bottom[0] * t),
                int(top[1] * (1 - t) + bottom[1] * t),
                int(top[2] * (1 - t) + bottom[2] * t),
                alpha,
            )
            y = int(i * h / bands)
            y2 = int((i + 1) * h / bands)
            pygame.draw.rect(surface, color, pygame.Rect(0, y, w, y2 - y + 1))

    # --- Menu frame --------------------------------------------------------
    def menu_frame(
        self,
        title: str,
        subtitle: str = "",
        *,
        title_asset: str = "",
    ) -> tuple[pygame.Rect, pygame.Rect]:
        width, height = self.screen.get_size()
        self.draw_menu_backdrop()
        side_margin = min(max(self.u(24), 32), max(16, width // 12))
        text_width = max(1, width - side_margin * 2)
        compact_scaled_layout = self.g.ui_scale_factor() >= 3 and height <= 720
        modern_header = self.asset_ui_active()
        title_limit = max(24, height // (10 if compact_scaled_layout else 8))
        title_font = next(
            (
                font
                for font in (
                    self.g.title_font,
                    self.g.big_font,
                    self.g.heading_font,
                    self.g.font,
                    self.g.small_font,
                    self.g.tiny_font,
                )
                if font.get_height() <= title_limit
                and font.size(title)[0] <= text_width
            ),
            None,
        )
        if title_font is None:
            title_font = self.fit_menu_font(
                self.g.tiny_font,
                max_height=title_limit,
                max_width=text_width,
                texts=(title,),
                minimum_size=12,
            )
        subtitle_limit = max(16, height // (18 if compact_scaled_layout else 10))
        subtitle_font = next(
            (
                font
                for font in (self.g.small_font, self.g.tiny_font)
                if font.get_height() <= subtitle_limit
                and font.size(subtitle)[0] <= text_width
            ),
            None,
        )
        if subtitle_font is None:
            subtitle_font = self.fit_menu_font(
                self.g.tiny_font,
                max_height=subtitle_limit,
                max_width=text_width,
                texts=(subtitle,),
                minimum_size=10,
            )

        title_surface: pygame.Surface | None = None
        title_height = title_font.get_height()
        if title_asset and modern_header:
            source = self.g.ui_assets.source(title_asset)
            if (
                source is not None
                and source.get_width() > 0
                and source.get_height() > 0
            ):
                max_logo_width = max(
                    1,
                    min(text_width, self.u(520), max(1, width * 3 // 5)),
                )
                max_logo_height = max(
                    1,
                    min(self.u(72), max(32, height // 6)),
                )
                logo_scale = min(
                    max_logo_width / source.get_width(),
                    max_logo_height / source.get_height(),
                )
                logo_size = (
                    max(1, round(source.get_width() * logo_scale)),
                    max(1, round(source.get_height() * logo_scale)),
                )
                title_surface = self.ui_asset(title_asset, logo_size)
                if title_surface is not None:
                    title_height = title_surface.get_height()
        self.g._menu_header_title_asset_used = title_surface is not None

        requested_title_y = max(self.u(30), int(height * 0.12))
        title_y = max(
            title_height // 2 + 8,
            min(
                requested_title_y,
                max(24, height // (12 if compact_scaled_layout else 8)),
            ),
        )
        if modern_header:
            title_y += min(8, max(5, height // 90))

        # Authored backgrounds already frame the header. The procedural flourish
        # remains part of legacy graphics, where it cannot cross a subtitle.
        if not modern_header:
            self._draw_title_ornament(
                title_y, title_font.get_height(), accent=self.accent()
            )

        title_rect = pygame.Rect(
            side_margin,
            title_y - title_height // 2,
            width - side_margin * 2,
            title_height,
        )
        self.g._menu_header_title_rect = title_rect.copy()
        if title_surface is not None:
            self.screen.blit(
                title_surface,
                title_surface.get_rect(center=title_rect.center),
            )
        else:
            self.draw_text(
                title,
                title_font,
                self.TITLE,
                title_rect,
                align="center",
                valign="center",
            )
        title_bottom = title_y + title_height // 2
        panel_gap = min(
            self.u(24),
            max(7 if compact_scaled_layout else 10, height // 64)
            + (6 if modern_header else 0),
        )
        top = title_bottom + panel_gap
        self.g._menu_header_subtitle_rect = pygame.Rect(0, 0, 0, 0)
        if subtitle:
            subtitle_top = title_bottom + min(
                self.u(10), 10 if modern_header else 8
            )
            subtitle_rect = pygame.Rect(
                side_margin,
                subtitle_top,
                width - side_margin * 2,
                subtitle_font.get_height(),
            )
            self.g._menu_header_subtitle_rect = subtitle_rect.copy()
            self.draw_text(
                subtitle,
                subtitle_font,
                self.MUTED,
                subtitle_rect,
                align="center",
            )
            top = subtitle_rect.bottom + panel_gap
        requested_footer = max(
            self.g.small_font.get_height() + self.u(18), self.u(42)
        )
        footer_space = min(requested_footer, max(32, height // 7))
        panel_w = min(width - side_margin * 2, self.u(860))
        panel_h = max(80, height - top - footer_space - min(self.u(10), 10))
        panel_h = min(panel_h, max(1, height - top - 4))
        rect = pygame.Rect(
            (width - panel_w) // 2,
            top,
            panel_w,
            panel_h,
        )
        self.g._last_menu_panel_rect = rect.copy()
        used_asset = self.panel(rect)
        self._last_menu_frame_used_asset = False
        if used_asset:
            safe = self.ui_content_rect("menu.panel", rect)
            if safe is not None:
                self._last_menu_frame_used_asset = True
                gutter_x = min(self.u(6), max(2, safe.width // 80))
                gutter_y = min(self.u(4), max(1, safe.height // 80))
                content = safe.inflate(-gutter_x * 2, -gutter_y * 2)
                return rect, content
        self._draw_parchment_header(rect, title)
        content_pad_x = min(max(self.u(22), 28), max(8, rect.width // 10))
        content_pad_y = min(max(self.u(20), 24), max(8, rect.height // 12))
        content = rect.inflate(-content_pad_x * 2, -content_pad_y * 2)
        content.y += min(self.u(8), max(2, rect.height // 30))
        content.h -= min(self.u(4), max(1, rect.height // 45))
        return rect, content

    def _draw_title_ornament(self, title_y: int, title_h: int, accent: Color) -> None:
        width, _height = self.screen.get_size()
        cx = width // 2
        rule_y = title_y + title_h // 2 + self.u(18)
        half_w = min(width // 2 - self.u(40), self.u(280))
        if half_w <= self.u(20):
            return
        gold = self.shade(accent, 8)
        gold_dim = self.shade(accent, -90)
        # Two thin rules with a gap, dimming toward the edges.
        for offset in (self.u(2), 0):
            pygame.draw.line(
                self.screen,
                gold_dim if offset else gold,
                (cx - half_w, rule_y + offset),
                (cx - self.u(18), rule_y + offset),
                max(1, self.u(1)),
            )
            pygame.draw.line(
                self.screen,
                gold_dim if offset else gold,
                (cx + self.u(18), rule_y + offset),
                (cx + half_w, rule_y + offset),
                max(1, self.u(1)),
            )
        # Center crest: the octahedron relic logo (the game's brand mark),
        # sized to sit between the two gold rules. Falls back to a small
        # diamond if the bundled icon assets are unavailable.
        crest_h = self.u(26)
        logo = self._title_logo(crest_h)
        if logo is not None:
            self.screen.blit(logo, logo.get_rect(center=(cx, rule_y)))
        else:
            crest_r = self.u(5)
            crest = [
                (cx, rule_y - crest_r),
                (cx + crest_r, rule_y),
                (cx, rule_y + crest_r),
                (cx - crest_r, rule_y),
            ]
            pygame.draw.polygon(self.screen, gold, crest)
            pygame.draw.polygon(
                self.screen, self.shade(accent, -40), crest, max(1, self.u(1))
            )
            pygame.draw.circle(
                self.screen, self.BG_DEEP, (cx, rule_y), max(1, self.u(1))
            )

    def _title_logo(self, height: int) -> pygame.Surface | None:
        if getattr(self.g, "legacy_graphics", False):
            return None
        # Cached octahedron logo scaled to the requested height. Cached on the
        # Game so a UI-scale change (which changes self.u) rebuilds once.
        cache = getattr(self.g, "_title_logo_cache", None)
        if cache is None:
            cache = {}
            self.g._title_logo_cache = cache
        surf = cache.get(height)
        if surf is not None:
            return surf
        from ..icon import title_logo

        surf = title_logo(height)
        if surf is not None:
            cache[height] = surf
        return surf

    def _draw_parchment_header(self, rect: pygame.Rect, title: str) -> None:
        """A thin aged-parchment band across the top of a panel, with a gold rule."""
        band_h = self.u(6)
        band = pygame.Rect(
            rect.x + self.u(6), rect.y + self.u(6), rect.width - self.u(12), band_h
        )
        parchment = pygame.Surface(band.size, pygame.SRCALPHA)
        parchment.fill((214, 196, 150, 28))
        self.screen.blit(parchment, band)
        pygame.draw.line(
            self.screen,
            self.shade(self.accent(), 18),
            (band.x, band.bottom),
            (band.right, band.bottom),
            max(1, self.u(1)),
        )

    def draw_footer(
        self,
        panel: pygame.Rect,
        text: str,
        font: pygame.font.Font | None = None,
    ) -> None:
        width, height = self.screen.get_size()
        margin = min(max(self.u(18), 28), max(16, width // 12))
        available_width = max(1, width - margin * 2)
        footer_room = max(10, height - panel.bottom - 4)
        footer_font = self.fit_menu_font(
            font or self.g.small_font,
            max_height=max(10, min(max(18, height // 18), footer_room)),
            max_width=available_width,
            texts=(text,),
            minimum_size=10,
        )
        bottom_pad = min(self.u(10), max(6, height // 48))
        panel_gap = min(self.u(14), max(8, height // 40))
        rect = pygame.Rect(
            margin,
            min(
                height - footer_font.get_height() - bottom_pad,
                panel.bottom + panel_gap,
            ),
            available_width,
            footer_font.get_height()
            + min(self.u(4), max(2, footer_font.get_height() // 3)),
        )
        self.draw_text(text, footer_font, self.MUTED, rect, align="center")

    def menu_shortcut_section_height(
        self, font: pygame.font.Font | None = None
    ) -> int:
        shortcut_font = font or self.g.small_font
        return max(self.u(28), shortcut_font.get_height() + self.u(12))

    def draw_menu_shortcut_section(
        self,
        rect: pygame.Rect,
        key: str,
        label: str,
        *,
        font: pygame.font.Font | None = None,
    ) -> None:
        """Draw the selected menu item's shortcut in a dedicated bottom strip."""

        if rect.width <= 0 or rect.height <= 0:
            return
        shortcut_font = font or self.g.small_font
        heading_font = self.g.tiny_font
        plate = pygame.Surface(rect.size, pygame.SRCALPHA)
        plate.fill((8, 8, 12, 172))
        self.screen.blit(plate, rect)
        accent = self.accent()
        pygame.draw.line(
            self.screen,
            self.shade(accent, -38),
            (rect.x + self.u(8), rect.y),
            (rect.right - self.u(8), rect.y),
            max(1, self.u(1)),
        )
        marker = pygame.Rect(
            rect.x + self.u(7),
            rect.y + self.u(6),
            max(2, self.u(3)),
            max(1, rect.height - self.u(12)),
        )
        pygame.draw.rect(self.screen, accent, marker, border_radius=self.u(2))
        heading_w = min(
            max(self.u(66), heading_font.size("SHORTCUT")[0] + self.u(10)),
            max(1, rect.width // 3),
        )
        heading_rect = pygame.Rect(
            marker.right + self.u(8), rect.y, heading_w, rect.height
        )
        self.draw_text(
            "SHORTCUT",
            heading_font,
            self.MUTED,
            heading_rect,
            valign="center",
        )
        detail_rect = pygame.Rect(
            heading_rect.right + self.u(4),
            rect.y,
            max(1, rect.right - heading_rect.right - self.u(12)),
            rect.height,
        )
        detail = f"{key}  ·  {label}" if label else key
        detail_font = self.fit_menu_font(
            shortcut_font,
            max_height=max(8, rect.height - self.u(6)),
            max_width=detail_rect.width,
            texts=(detail,),
            minimum_size=9,
        )
        self.draw_text(
            detail,
            detail_font,
            self.TITLE,
            detail_rect,
            valign="center",
        )
        self.g._menu_shortcut_rect = rect.copy()
        self.g._menu_shortcut_key = key
        self.g._menu_shortcut_label = label

    def draw_menu_rows(
        self,
        rows: Sequence[MenuRow],
        rect: pygame.Rect,
        selected_index: int = -1,
        sections: Sequence[tuple[int, str]] | None = None,
        *,
        body_font: pygame.font.Font | None = None,
        detail_font: pygame.font.Font | None = None,
        layout_scale: float | None = None,
        row_height: int | None = None,
        row_gap: int | None = None,
        section_header_height: int | None = None,
        keys_in_rows: bool = True,
    ) -> tuple[pygame.Rect, ...]:
        """Draw menu rows and return the rectangles that were actually rendered.

        Explicit metrics let a scrolling menu calculate visibility with exactly
        the same geometry used for drawing. Other menus keep the original scaled
        defaults by omitting the keyword-only responsive-layout arguments.
        """

        if body_font is None:
            body_font = self.g.font
        if detail_font is None:
            detail_font = self.g.small_font
        assert body_font is not None
        assert detail_font is not None
        active_scale = self.g.ui_scale_factor()
        scale = (
            active_scale
            if layout_scale is None
            else max(1.0, min(active_scale, float(layout_scale)))
        )

        def px(value: int) -> int:
            return max(1, round(value * scale))

        # Optional section headers: ``sections`` is a list of
        # ``(start_row_index, title)`` entries. The cursor remains in the flat
        # row index space so callers do not need separate navigation semantics.
        section_starts = dict(sections or ())
        label_h = detail_font.get_height()
        header_h = max(
            label_h + px(2),
            section_header_height
            if section_header_height is not None
            else label_h + px(12),
        )
        total_header_h = header_h * len(section_starts)
        row_count = max(1, len(rows))
        base_gap = max(px(7), 7)
        base_row_h = max(body_font.get_height() + px(18), px(44))
        available_h = max(1, rect.height - total_header_h)
        if row_height is not None:
            row_h = max(body_font.get_height() + px(2), int(row_height))
            gap = max(0, int(row_gap if row_gap is not None else px(3)))
        elif row_count * base_row_h + (row_count - 1) * base_gap > available_h:
            gap = max(1, min(base_gap, px(3)))
            row_h = max(
                body_font.get_height() + px(8),
                (available_h - gap * (row_count - 1)) // row_count,
            )
        else:
            row_h = base_row_h
            gap = base_gap

        row_inset = min(px(8), max(5, row_h // 7))
        key_text_pad = min(px(8), max(4, detail_font.get_height() // 3))
        key_limit = max(1, min(rect.width - 1, max(48, int(rect.width * 0.40))))
        widest_key = max((detail_font.size(key)[0] for key, _, _ in rows), default=0)
        desired_key_w = widest_key + row_inset * 2 + key_text_pad
        base_key_w = min(max(px(108), 108), key_limit)
        key_w = min(key_limit, max(base_key_w, desired_key_w))
        column_gap = min(px(12), max(8, rect.width // 40))
        right_pad = min(px(10), max(6, rect.width // 60))
        value_pad = min(px(18), max(10, detail_font.get_height()))

        y = rect.y
        accent = self.accent()
        rendered_rows: list[pygame.Rect] = []
        rendered_key_rects: list[pygame.Rect] = []
        rendered_value_rects: list[pygame.Rect] = []
        for index, (key, label, value) in enumerate(rows):
            title = section_starts.get(index)
            if title is not None:
                self.draw_text(
                    title.upper(),
                    detail_font,
                    self.TITLE,
                    pygame.Rect(
                        rect.x + px(4),
                        y,
                        rect.width - px(8),
                        label_h + px(2),
                    ),
                )
                line_y = y + header_h - px(4)
                pygame.draw.line(
                    self.screen,
                    self.PANEL_2,
                    (rect.x + px(4), line_y),
                    (rect.right - px(4), line_y),
                    px(1),
                )
                y += header_h
            if y + row_h > rect.bottom:
                break

            row_rect = pygame.Rect(rect.x, y, rect.width, row_h)
            rendered_rows.append(row_rect.copy())
            is_selected = index == selected_index
            plate_fill = self.shade(accent, -100) if is_selected else self.PANEL_INK
            row_asset = self.ui_asset("menu.row", row_rect.size)
            row_safe = (
                self.ui_content_rect("menu.row", row_rect)
                if row_asset is not None
                else None
            )
            authored_row = bool(
                row_asset is not None
                and row_safe is not None
                and row_safe.width >= max(72, row_rect.width // 5)
                and row_h >= detail_font.get_height() + px(6)
            )
            modern_row = row_asset is not None
            if authored_row:
                assert row_asset is not None
                self.screen.blit(row_asset, row_rect)
            elif modern_row:
                # Tiny modern rows cannot preserve the authored endcaps. Keep a
                # quiet flat plate instead of reintroducing procedural bevels.
                pygame.draw.rect(self.screen, self.PANEL_INK, row_rect, border_radius=px(4))
            else:
                pygame.draw.rect(self.screen, plate_fill, row_rect, border_radius=px(5))
            if is_selected:
                glow = pygame.Surface(row_rect.size, pygame.SRCALPHA)
                pygame.draw.rect(
                    glow,
                    (*accent, 32),
                    glow.get_rect(),
                    border_radius=px(5),
                )
                self.screen.blit(glow, row_rect)
            if not modern_row:
                border_color = accent if is_selected else self.PANEL_2
                pygame.draw.rect(
                    self.screen,
                    border_color,
                    row_rect,
                    px(1),
                    border_radius=px(5),
                )
                pygame.draw.line(
                    self.screen,
                    self.STONE_LIGHT,
                    (row_rect.x + px(6), row_rect.y + px(1)),
                    (row_rect.right - px(6), row_rect.y + px(1)),
                    px(1),
                )
            if is_selected:
                strip_inset = min(px(4), max(2, row_h // 5))
                strip = pygame.Rect(
                    row_rect.x,
                    row_rect.y + strip_inset,
                    px(4),
                    max(1, row_h - strip_inset * 2),
                )
                pygame.draw.rect(self.screen, accent, strip, border_radius=px(3))
                pygame.draw.rect(
                    self.screen,
                    self.shade(accent, 40),
                    strip,
                    border_radius=px(3),
                )

            value_rect: pygame.Rect | None = None
            key_rect = pygame.Rect(row_rect.x, row_rect.y, 0, row_h)
            if authored_row:
                assert row_safe is not None
                if keys_in_rows:
                    endcap_pad = min(px(8), max(3, row_h // 8))
                    key_rect = pygame.Rect(
                        row_rect.x + endcap_pad,
                        row_rect.y,
                        max(1, row_safe.x - row_rect.x - endcap_pad * 2),
                        row_h,
                    )
                    label_rect = row_safe.inflate(
                        -min(px(6), row_safe.width // 12) * 2, 0
                    )
                    if value:
                        value_rect = pygame.Rect(
                            row_safe.right + endcap_pad,
                            row_rect.y,
                            max(1, row_rect.right - row_safe.right - endcap_pad * 2),
                            row_h,
                        )
                else:
                    center_pad = min(px(10), max(6, row_safe.width // 30))
                    center_rect = row_safe.inflate(-center_pad * 2, 0)
                    label_right = center_rect.right
                    if value:
                        status_right_gap = min(
                            px(18), max(8, center_rect.width // 24)
                        )
                        status_limit = max(1, center_rect.width // 2)
                        desired_status_w = detail_font.size(value)[0] + value_pad
                        value_w = min(
                            status_limit,
                            max(desired_status_w, center_rect.width // 4),
                        )
                        value_rect = pygame.Rect(
                            center_rect.right - status_right_gap - value_w,
                            row_rect.y,
                            value_w,
                            row_h,
                        )
                        label_right = value_rect.x - column_gap
                    label_rect = pygame.Rect(
                        center_rect.x,
                        row_rect.y,
                        max(0, label_right - center_rect.x),
                        row_h,
                    )
            else:
                if keys_in_rows:
                    key_y_inset = min(
                        px(7), max(3, (row_h - detail_font.get_height()) // 4)
                    )
                    key_rect = pygame.Rect(
                        row_rect.x + row_inset,
                        row_rect.y + key_y_inset,
                        max(1, key_w - row_inset * 2),
                        max(1, row_h - key_y_inset * 2),
                    )
                    if not modern_row:
                        pygame.draw.rect(
                            self.screen,
                            self.IRON_DARK,
                            key_rect,
                            border_radius=px(4),
                        )
                        pygame.draw.rect(
                            self.screen,
                            self.IRON,
                            key_rect.inflate(-px(2), -px(2)),
                            border_radius=px(3),
                        )
                        pygame.draw.rect(
                            self.screen,
                            self.shade(self.accent(), -40),
                            key_rect,
                            px(1),
                            border_radius=px(4),
                        )
                    label_x = row_rect.x + key_w + column_gap
                    status_right_gap = 0
                else:
                    label_x = row_rect.x + row_inset + px(6)
                    status_right_gap = px(10)
                label_right = row_rect.right - right_pad - status_right_gap
                if value:
                    available_for_value = max(0, label_right - label_x)
                    value_limit = min(
                        rect.width // (3 if keys_in_rows else 2),
                        max(0, available_for_value // 2),
                    )
                    value_w = min(
                        value_limit,
                        detail_font.size(value)[0] + value_pad,
                    )
                    value_rect = pygame.Rect(
                        label_right - value_w,
                        row_rect.y,
                        value_w,
                        row_h,
                    )
                    label_right = value_rect.x - column_gap
                label_rect = pygame.Rect(
                    label_x,
                    row_rect.y,
                    max(0, label_right - label_x),
                    row_h,
                )

            if keys_in_rows and key:
                self.draw_text(
                    key,
                    detail_font,
                    self.TITLE,
                    key_rect.inflate(-key_text_pad, 0),
                    align="center",
                    valign="center",
                )
            self.draw_text(label, body_font, self.TEXT, label_rect, valign="center")
            if value and value_rect is not None:
                self.draw_text(
                    value,
                    detail_font,
                    self.WARNING,
                    value_rect,
                    align="right",
                    valign="center",
                )
            rendered_key_rects.append(key_rect.copy())
            rendered_value_rects.append(
                value_rect.copy() if value_rect is not None else pygame.Rect(0, 0, 0, 0)
            )
            y += row_h + gap
        self.g._menu_row_rects = tuple(row.copy() for row in rendered_rows)
        self.g._menu_row_key_rects = tuple(rendered_key_rects)
        self.g._menu_row_value_rects = tuple(rendered_value_rects)
        return tuple(rendered_rows)
