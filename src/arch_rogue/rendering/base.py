# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
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


class RenderingBaseMixin:
    def draw(self) -> None:
        # Per-frame caches for hot-path lookups. These are invalidated every
        # frame so they never go stale within a single render pass.
        self._frame_cache: dict[str, object] = {}
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
        if self.state == "controls":
            self.draw_controls_menu()
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
        if self.shop_open:
            self.draw_shop_overlay()
        if self.character_menu_open:
            self.draw_character_menu()
        if self.show_help:
            self.draw_help_overlay()
        if self.state != "playing":
            self.draw_state_overlay()
        self.draw_screen_flash()
        pygame.display.flip()
        self.sync_music()

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

    def _text_size(self, font: pygame.font.Font, text: str) -> tuple[int, int]:
        # font.size() is a hot per-frame call (HUD text wrapping/ellipsizing).
        # Cache by (font, text) so repeated labels (ability names, HP headers,
        # cooldown counts, ...) don't re-measure every frame. Cleared in
        # rebuild_fonts (Font objects are replaced, so id(font) keys would collide).
        cache = getattr(self, "_text_size_cache", None)
        if cache is None:
            cache = {}
            self._text_size_cache = cache
        key = (id(font), text)
        v = cache.get(key)
        if v is None:
            v = font.size(text)
            if len(cache) >= 8192:
                cache.clear()
            cache[key] = v
        return v

    def ellipsize_ui_text(
        self, text: str, font: pygame.font.Font, max_width: int
    ) -> str:
        max_width = max(1, max_width)
        if self._text_size(font, text)[0] <= max_width:
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
                if self._text_size(font, candidate)[0] <= max_width:
                    current = candidate
                else:
                    lines.append(current)
                    current = self.ellipsize_ui_text(word, font, max_width)
            lines.append(current)
        return lines

    # --- Gothic HUD helpers -------------------------------------------------
    # Shared palette tokens for the in-world HUD. Kept here so the HUD and the
    # menu renderer speak the same visual language without import cycles.
    HUD_INK = (12, 11, 16)
    HUD_PANEL = (18, 17, 24)
    HUD_STONE_LIGHT = (54, 49, 58)
    HUD_STONE_SHADOW = (8, 7, 11)
    HUD_IRON = (74, 70, 82)
    HUD_IRON_LIGHT = (118, 110, 128)
    HUD_IRON_DARK = (32, 30, 38)
    HUD_GOLD = (214, 168, 92)
    HUD_GOLD_BRIGHT = (236, 214, 168)
    HUD_PARCHMENT = (224, 214, 196)
    HUD_BONE = (210, 204, 190)
    HUD_MUTED = (148, 138, 124)

    def draw_ornate_hud_panel(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        fill: tuple[int, int, int, int],
        border: tuple[int, int, int, int],
        radius: int | None = None,
        width: int | None = None,
        studs: bool = False,
    ) -> None:
        """A translucent stone panel with a chiseled bevel and optional iron studs."""
        radius = self.ui(9) if radius is None else radius
        width = self.ui(1) if width is None else width
        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        panel_rect = panel.get_rect()
        pygame.draw.rect(panel, fill, panel_rect, border_radius=radius)
        # Inner bevel — dark rim then a faint light rim.
        pygame.draw.rect(
            panel,
            (*self.HUD_STONE_SHADOW, fill[3] // 2 + 40),
            panel_rect,
            max(1, self.ui(2)),
            border_radius=radius,
        )
        inner = panel_rect.inflate(-self.ui(2), -self.ui(2))
        pygame.draw.rect(
            panel,
            (*self.HUD_STONE_LIGHT, fill[3] // 2 + 30),
            inner,
            max(1, self.ui(1)),
            border_radius=max(1, radius - self.ui(1)),
        )
        # Gold inner trim.
        trim = inner.inflate(-self.ui(4), -self.ui(4))
        pygame.draw.rect(
            panel,
            (*self.shade(self.HUD_GOLD, -40), fill[3] // 2 + 20),
            trim,
            max(1, self.ui(1)),
            border_radius=max(1, radius - self.ui(2)),
        )
        # Outer accent border (caller-supplied color).
        pygame.draw.rect(panel, border, panel_rect, width, border_radius=radius)
        if studs:
            stud_r = max(2, self.ui(3))
            inset = self.ui(7)
            for corner in (
                (inset, inset),
                (panel_rect.width - inset, inset),
                (inset, panel_rect.height - inset),
                (panel_rect.width - inset, panel_rect.height - inset),
            ):
                pygame.draw.circle(panel, self.HUD_IRON_DARK, corner, stud_r + 1)
                pygame.draw.circle(panel, self.HUD_IRON, corner, stud_r)
                pygame.draw.circle(
                    panel,
                    self.HUD_IRON_LIGHT,
                    (corner[0] - 1, corner[1] - 1),
                    max(1, stud_r - 1),
                )
        surface.blit(panel, rect)

    def draw_hud_divider(
        self, surface: pygame.Surface, x1: int, y: int, x2: int, color: Color
    ) -> None:
        """An ornamental gold rule with a center diamond."""
        pygame.draw.line(
            surface, self.shade(color, -40), (x1, y), (x2, y), max(1, self.ui(1))
        )
        cx = (x1 + x2) // 2
        dr = self.ui(2)
        pygame.draw.polygon(
            surface,
            color,
            [(cx, y - dr), (cx + dr, y), (cx, y + dr), (cx - dr, y)],
        )
