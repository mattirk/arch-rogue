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

from typing import Sequence

import pygame

from ..models import Archetype, Color

MenuRow = tuple[str, str, str]


class MenuCharacterMixin:
    _ARCHETYPE_PANEL_SCALE = 0.8
    _ARCHETYPE_PREVIEW_DIRECTIONS = {"Ranger": "south-west"}

    def archetype_preview_direction(self, archetype: Archetype) -> str:
        return self._ARCHETYPE_PREVIEW_DIRECTIONS.get(archetype.name, "south")

    def draw_archetype_select(self) -> None:
        with self.g.fitted_ui_layout((960, 540)):
            library = getattr(self.g, "ui_assets", None)
            modern = bool(
                self.asset_ui_active()
                and library is not None
                and library.source("menu.panel") is not None
            )
            if modern:
                self._draw_archetype_select_modern()
            else:
                self._draw_archetype_select_legacy()

    def _draw_archetype_select_modern(self) -> None:
        width, height = self.screen.get_size()
        self.draw_menu_backdrop()
        selected = self.g.selected_archetype
        accent = self.archetype_accent(selected.name)
        side_margin = max(20, min(self.u(36), width // 16))
        preferred_title_font = self.g.title_font if width >= 800 else self.g.big_font
        title_font = self.fit_menu_font(
            preferred_title_font,
            max_height=max(30, min(48, height // 9)),
            max_width=max(1, width - side_margin * 2),
            texts=("Choose Your Archetype",),
            minimum_size=20,
        )
        subtitle_font = self.g.font
        reference_title_rect = pygame.Rect(
            side_margin,
            max(20, int(height * 0.04)),
            width - side_margin * 2,
            title_font.get_height(),
        )
        reference_subtitle_rect = pygame.Rect(
            side_margin,
            reference_title_rect.bottom + self.u(5),
            width - side_margin * 2,
            subtitle_font.get_height(),
        )

        footer_h = max(
            self.menu_shortcut_section_height(self.g.small_font) + self.u(4),
            self.g.small_font.get_height() + self.u(8),
            32,
        )
        panel_margin = max(26, min(self.u(44), width // 18))
        panel_bottom_gap = max(self.u(10), 10)
        reference_panel_rect = pygame.Rect(
            panel_margin,
            reference_subtitle_rect.bottom + max(self.u(14), 14),
            max(1, width - panel_margin * 2),
            max(
                1,
                height
                - reference_subtitle_rect.bottom
                - max(self.u(14), 14)
                - footer_h
                - panel_bottom_gap,
            ),
        )
        panel_rect = pygame.Rect(
            0,
            0,
            max(1, round(reference_panel_rect.width * self._ARCHETYPE_PANEL_SCALE)),
            max(1, round(reference_panel_rect.height * self._ARCHETYPE_PANEL_SCALE)),
        )
        panel_rect.center = reference_panel_rect.center

        # Move the header down by the same amount removed from the panel's top.
        # The shortcut remains attached below the panel and therefore moves up.
        header_shift_y = max(0, panel_rect.y - reference_panel_rect.y)
        title_rect = reference_title_rect.move(0, header_shift_y)
        subtitle_rect = reference_subtitle_rect.move(0, header_shift_y)
        self.g._archetype_title_rect = title_rect.copy()
        self.g._archetype_subtitle_rect = subtitle_rect.copy()
        self.g._archetype_panel_reference_rect = reference_panel_rect.copy()
        self.g._archetype_panel_rect = panel_rect.copy()
        self.draw_text(
            "Choose Your Archetype",
            title_font,
            self.TITLE,
            title_rect,
            align="center",
        )
        self.draw_text(
            "Arrow keys select · Enter begins · Backspace returns",
            subtitle_font,
            self.MUTED,
            subtitle_rect,
            align="center",
        )

        if not self.panel(panel_rect, accent, alpha=248):
            self._draw_archetype_select_legacy()
            return
        safe = self.menu_panel_content_rect(panel_rect)
        if safe is None:
            self._draw_archetype_select_legacy()
            return
        safe = safe.inflate(-self.u(6) * 2, -self.u(4) * 2)
        gap = max(self.u(14), 14)
        list_min = 170 if safe.width >= 500 else 140
        preview_min = min(220, max(180, int(safe.width * 0.46)))
        list_w = min(
            max(list_min, int(safe.width * 0.31)),
            max(1, safe.width - gap - preview_min),
        )
        list_rect = pygame.Rect(safe.x, safe.y, list_w, safe.height)
        preview_rect = pygame.Rect(
            list_rect.right + gap,
            safe.y,
            max(1, safe.right - list_rect.right - gap),
            safe.height,
        )
        self.g._archetype_content_rect = safe.copy()
        self.g._archetype_list_rect = list_rect.copy()
        self.g._archetype_preview_rect = preview_rect.copy()
        self._draw_archetype_list_modern(list_rect, selected)
        self._draw_archetype_preview_modern(preview_rect, selected)
        shortcut_h = self.menu_shortcut_section_height(self.g.small_font)
        shortcut_rect = pygame.Rect(
            panel_rect.x,
            panel_rect.bottom + self.u(4),
            panel_rect.width,
            min(shortcut_h, max(1, height - panel_rect.bottom - self.u(8))),
        )
        selected_index = self.archetypes.index(selected)
        self.draw_menu_shortcut_section(
            shortcut_rect,
            str(selected_index + 1),
            f"Select {selected.name}",
            font=self.g.small_font,
        )
        self.g._archetype_shortcut_rect = shortcut_rect.copy()

    def _draw_archetype_list_modern(
        self, rect: pygame.Rect, selected: Archetype
    ) -> None:
        heading_h = self.g.font.get_height()
        self.draw_text(
            "Classes",
            self.g.font,
            self.TITLE,
            pygame.Rect(rect.x, rect.y, rect.width, heading_h),
        )
        rows_top = rect.y + heading_h + self.u(7)
        rows_rect = pygame.Rect(
            rect.x,
            rows_top,
            rect.width,
            max(1, rect.bottom - rows_top),
        )
        gap = max(3, self.u(4))
        row_h = max(
            self.g.small_font.get_height() + self.u(5),
            (rows_rect.height - gap * (len(self.archetypes) - 1))
            // max(1, len(self.archetypes)),
        )
        rows: list[MenuRow] = [
            (str(index + 1), archetype.name, "")
            for index, archetype in enumerate(self.archetypes)
        ]
        self.draw_menu_rows(
            rows,
            rows_rect,
            selected_index=self.archetypes.index(selected),
            body_font=self.g.font,
            detail_font=self.g.small_font,
            row_height=row_h,
            row_gap=gap,
            keys_in_rows=False,
        )

    def _draw_archetype_preview_modern(
        self, rect: pygame.Rect, archetype: Archetype
    ) -> None:
        accent = self.archetype_accent(archetype.name)
        name_font = self.fit_menu_font(
            self.g.big_font,
            max_height=max(22, rect.height // 7),
            max_width=max(1, rect.width),
            texts=(archetype.name,),
            minimum_size=16,
        )
        self.draw_text(
            archetype.name,
            name_font,
            self.TITLE,
            pygame.Rect(rect.x, rect.y, rect.width, name_font.get_height()),
            align="center",
        )
        skills_y = rect.y + name_font.get_height() + self.u(2)
        skills_text = " · ".join(self.skill_names_for(archetype.name))
        skills_font = self.fit_menu_font(
            self.g.small_font,
            max_height=self.g.small_font.get_height(),
            max_width=max(1, rect.width),
            texts=(skills_text,),
            minimum_size=9,
        )
        self.g._archetype_skills_text = skills_text
        self.g._archetype_skills_font = skills_font
        self.draw_text(
            skills_text,
            skills_font,
            accent,
            pygame.Rect(rect.x, skills_y, rect.width, skills_font.get_height()),
            align="center",
        )

        middle_y = skills_y + skills_font.get_height() + self.u(7)
        stat_gap = max(self.u(4), 5)
        stat_columns = self._stat_grid_columns(rect.width, modern=True)
        stat_rows = max(1, (7 + stat_columns - 1) // stat_columns)
        stat_cell_h = max(self.g.small_font.get_height() + self.u(3), self.u(18))
        desired_stat_h = stat_rows * stat_cell_h + (stat_rows - 1) * stat_gap
        stat_h = min(
            max(desired_stat_h, self.u(56)),
            max(1, rect.bottom - middle_y - self.u(24)),
        )
        stat_rect = pygame.Rect(rect.x, rect.bottom - stat_h, rect.width, stat_h)
        middle = pygame.Rect(
            rect.x,
            middle_y,
            rect.width,
            max(1, stat_rect.y - middle_y - self.u(7)),
        )
        description_font = (
            self.g.small_font if rect.width < self.u(300) else self.g.font
        )
        description_line_h = max(
            description_font.get_height() + self.u(3), self.u(18)
        )
        description_lines = self.wrap_text(
            archetype.description, description_font, rect.width
        )
        desired_description_h = (
            (len(description_lines) - 1) * description_line_h
            + description_font.get_height()
        )
        description_h = min(
            max(description_font.get_height(), desired_description_h),
            max(1, middle.height - self.u(18)),
        )
        desc_rect = pygame.Rect(
            middle.x,
            middle.bottom - description_h,
            middle.width,
            description_h,
        )
        sprite_box = pygame.Rect(
            middle.x,
            middle.y,
            middle.width,
            max(1, desc_rect.y - middle.y - self.u(5)),
        )
        visual = self.g.sprites.player_visual(
            archetype.name,
            "idle",
            0.0,
            self.g.ui_elapsed,
            direction=self.archetype_preview_direction(archetype),
        )
        sprite = visual.surface
        scale = min(
            max(1, sprite_box.width - self.u(20)) / max(1, sprite.get_width()),
            max(1, sprite_box.height - self.u(12)) / max(1, sprite.get_height()),
            3.4,
        )
        scale = max(0.15, scale)
        preview = pygame.transform.scale(
            sprite,
            (
                max(1, round(sprite.get_width() * scale)),
                max(1, round(sprite.get_height() * scale)),
            ),
        )
        preview_anchor = (
            round(visual.anchor[0] * preview.get_width() / max(1, sprite.get_width())),
            round(visual.anchor[1] * preview.get_height() / max(1, sprite.get_height())),
        )
        pedestal = pygame.Rect(
            0,
            0,
            min(sprite_box.width, preview.get_width() + self.u(26)),
            max(5, self.u(9)),
        )
        pedestal.midbottom = (sprite_box.centerx, sprite_box.bottom - self.u(2))
        glow = pygame.Surface(
            (max(1, pedestal.width), max(1, pedestal.height * 2)), pygame.SRCALPHA
        )
        pygame.draw.ellipse(glow, (*accent, 42), glow.get_rect())
        self.screen.blit(glow, glow.get_rect(center=pedestal.center))
        # Asset frames are cropped independently, so their canvas centers move.
        # Pin the authored ground anchor to the pedestal instead.
        preview_ground = (sprite_box.centerx, pedestal.centery)
        preview_rect = preview.get_rect(
            topleft=(
                preview_ground[0] - preview_anchor[0],
                preview_ground[1] - preview_anchor[1],
            )
        )
        self.screen.blit(preview, preview_rect)
        self.g._archetype_sprite_box = sprite_box.copy()
        self.g._archetype_sprite_rect = preview_rect.copy()
        self.g._archetype_sprite_anchor = preview_anchor
        self.g._archetype_sprite_ground = preview_ground
        self.g._archetype_description_rect = desc_rect.copy()
        self.g._archetype_description_font = description_font
        self.g._archetype_description_line_height = description_line_h
        self.g._archetype_description_lines = tuple(description_lines)
        self.draw_wrapped_text(
            archetype.description,
            description_font,
            self.TEXT,
            desc_rect,
            description_line_h,
        )
        stats = [
            ("HP", str(archetype.max_hp)),
            ("Mana", str(archetype.max_mana)),
            ("Stamina", str(archetype.max_stamina)),
            ("Speed", f"{archetype.speed:.2f}"),
            ("Melee", f"+{archetype.melee_bonus}"),
            ("Spell", f"+{archetype.spell_bonus}"),
            ("DR", f"+{archetype.armor_bonus}"),
        ]
        self.g._archetype_stat_rect = stat_rect.copy()
        self.g._archetype_stat_rects = self.draw_stat_grid(
            stats, stat_rect, modern=True, cards=True, accent=accent
        )

    def _draw_archetype_select_legacy(self) -> None:
        width, height = self.screen.get_size()
        self.draw_menu_backdrop()
        selected = self.g.selected_archetype
        accent = self.archetype_accent(selected.name)

        title_font = self.g.title_font if height >= self.u(330) else self.g.big_font
        subtitle_font = self.g.font
        title_h = title_font.get_height()
        top_margin = max(self.u(12), int(height * 0.04))
        self.draw_text(
            "Choose Your Archetype",
            title_font,
            self.TITLE,
            pygame.Rect(28, top_margin, width - 56, title_h),
            align="center",
        )
        subtitle_y = top_margin + title_h + self.u(5)
        self.draw_text(
            "Arrow keys select · Enter begins · Backspace returns",
            subtitle_font,
            self.MUTED,
            pygame.Rect(32, subtitle_y, width - 64, subtitle_font.get_height()),
            align="center",
        )

        footer_h = max(self.u(30), self.g.small_font.get_height() + self.u(14))
        content_top = subtitle_y + subtitle_font.get_height() + self.u(14)
        content_margin = max(self.u(14), 18)
        content = pygame.Rect(
            content_margin,
            content_top,
            max(1, width - content_margin * 2),
            max(1, height - content_top - footer_h - self.u(8)),
        )
        if content.height < 230:
            content.y = max(86, content.y - (230 - content.height))
            content.height = max(1, min(230, height - content.y - footer_h - 10))

        compact = width < max(620, self.u(360)) or content.width < self.u(360)
        gap = max(self.u(8), 12)
        base_list_w = min(self.u(250), max(self.u(180), int(content.width * 0.36)))
        preview_min_w = min(self.u(250), max(self.u(180), int(content.width * 0.28)))
        list_w = (
            min(base_list_w * 4, max(base_list_w, content.width - gap - preview_min_w))
            if not compact
            else content.width
        )
        if compact:
            min_preview_h = min(max(self.u(110), 110), max(1, content.height - gap - 1))
            preferred_list_h = min(
                max(self.u(128), content.height // 2), content.height
            )
            if content.height > gap + min_preview_h:
                list_h = min(preferred_list_h, content.height - gap - min_preview_h)
                list_h = max(1, list_h)
                preview_y = content.y + list_h + gap
                preview_h = max(1, content.bottom - preview_y)
            else:
                list_h = max(1, content.height // 2)
                preview_y = content.y + list_h
                preview_h = max(1, content.bottom - preview_y)
            list_rect = pygame.Rect(content.x, content.y, content.width, list_h)
            preview_rect = pygame.Rect(content.x, preview_y, content.width, preview_h)
        else:
            list_rect = pygame.Rect(content.x, content.y, list_w, content.height)
            preview_rect = pygame.Rect(
                list_rect.right + gap,
                content.y,
                content.right - list_rect.right - gap,
                content.height,
            )

        self.panel(list_rect, accent, alpha=248)
        self.panel(preview_rect, accent, alpha=248)
        preview_header_cover = pygame.Rect(
            preview_rect.x + self.u(6),
            preview_rect.y + self.u(4),
            preview_rect.width - self.u(12),
            self.g.big_font.get_height() + self.u(16),
        )
        pygame.draw.rect(self.screen, self.PANEL, preview_header_cover)
        self.draw_archetype_list(list_rect, selected)
        self.draw_archetype_preview(preview_rect, selected)

        footer_font = self.g.small_font
        self.draw_text(
            f"Press 1-{min(len(self.archetypes), 9)} to jump directly to a class",
            footer_font,
            self.WARNING,
            pygame.Rect(32, height - footer_h, width - 64, footer_h - 4),
            align="center",
            valign="center",
        )

    def draw_archetype_list(self, rect: pygame.Rect, selected: Archetype) -> None:
        compact_fonts = rect.height < self.u(190)
        heading_font = self.g.font if compact_fonts else self.g.heading_font
        name_font_large = self.g.font
        row_font = self.g.small_font
        inner = rect.inflate(-self.u(22), -self.u(22))
        header_rect = pygame.Rect(
            inner.x,
            inner.y - self.u(2),
            inner.width,
            heading_font.get_height() + self.u(10),
        )
        pygame.draw.rect(self.screen, self.PANEL_INK, header_rect)
        self.draw_text(
            "Classes",
            heading_font,
            self.TITLE,
            pygame.Rect(inner.x, inner.y, inner.width, heading_font.get_height()),
        )
        header_line_y = inner.y + heading_font.get_height() + self.u(6)
        pygame.draw.line(
            self.screen,
            self.shade(self.archetype_accent(selected.name), 18),
            (inner.x, header_line_y),
            (inner.right, header_line_y),
            max(1, self.u(1)),
        )
        list_top = header_line_y + self.u(10)
        gap = max(self.u(4), 5)
        available_rows_h = max(
            1, inner.bottom - list_top - gap * (len(self.archetypes) - 1)
        )
        row_h = max(
            self.g.small_font.get_height() + self.u(18),
            min(self.u(74), available_rows_h // len(self.archetypes)),
        )
        y = list_top
        for index, archetype in enumerate(self.archetypes):
            row = pygame.Rect(inner.x, y, inner.width, row_h)
            is_selected = archetype == selected
            row_accent = self.archetype_accent(archetype.name)
            if is_selected:
                # Selected: gold-tinted plate with a soft inner glow.
                fill = self.shade(row_accent, -100)
                pygame.draw.rect(self.screen, fill, row, border_radius=self.u(7))
                glow = pygame.Surface(row.size, pygame.SRCALPHA)
                pygame.draw.rect(
                    glow,
                    (*row_accent, 36),
                    glow.get_rect(),
                    border_radius=self.u(7),
                )
                self.screen.blit(glow, row)
            else:
                pygame.draw.rect(
                    self.screen, self.PANEL_INK, row, border_radius=self.u(7)
                )
            border = row_accent if is_selected else self.IRON
            radius = self.u(7)
            pygame.draw.rect(
                self.screen, border, row, max(1, self.u(1)), border_radius=radius
            )
            if is_selected:
                strip = pygame.Rect(
                    row.x, row.y + self.u(4), self.u(4), row.height - self.u(8)
                )
                pygame.draw.rect(
                    self.screen, row_accent, strip, border_radius=self.u(3)
                )
                pygame.draw.rect(
                    self.screen,
                    self.shade(row_accent, 40),
                    strip,
                    border_radius=self.u(3),
                )
            # Sigil badge — iron plate with the class number etched in gold.
            badge_size = min(self.u(34), row_h - self.u(10))
            badge = pygame.Rect(
                row.x + self.u(10),
                row.y + (row_h - badge_size) // 2,
                badge_size,
                badge_size,
            )
            pygame.draw.rect(
                self.screen, self.IRON_DARK, badge, border_radius=self.u(5)
            )
            pygame.draw.rect(
                self.screen,
                self.IRON,
                badge.inflate(-self.u(2), -self.u(2)),
                border_radius=self.u(4),
            )
            pygame.draw.rect(
                self.screen, border, badge, max(1, self.u(1)), border_radius=self.u(5)
            )
            self.draw_text(
                str(index + 1),
                row_font,
                self.TITLE if is_selected else self.IRON_LIGHT,
                badge,
                align="center",
                valign="center",
            )
            name_rect = pygame.Rect(
                badge.right + self.u(14),
                row.y + self.u(3),
                row.width - badge.width - self.u(28),
                max(1, row_h // 2 - 2),
            )
            name_font = name_font_large if row_h >= 46 else row_font
            self.draw_text(
                archetype.name,
                name_font,
                self.TITLE if is_selected else self.TEXT,
                name_rect,
                valign="center",
            )
            role_rect = pygame.Rect(
                badge.right + self.u(14),
                row.centery + self.u(2),
                row.width - badge.width - self.u(28),
                max(1, row_h // 2 - 6),
            )
            self.draw_text(
                self.class_tagline(archetype.name),
                row_font,
                self.MUTED,
                role_rect,
                valign="center",
            )
            y += row_h + gap

    def draw_archetype_preview(self, rect: pygame.Rect, archetype: Archetype) -> None:
        compact_fonts = rect.height < self.u(190)
        accent = self.archetype_accent(archetype.name)
        name_font = self.g.heading_font if compact_fonts else self.g.big_font
        detail_font = self.g.small_font if compact_fonts else self.g.font
        inner = rect.inflate(-self.u(28), -self.u(24))
        name_h = name_font.get_height()
        name_rect = pygame.Rect(
            inner.x, inner.y + self.u(5), inner.width, name_h + self.u(8)
        )
        # Parchment name plaque.
        plaque = pygame.Surface(name_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(
            plaque,
            (214, 196, 150, 24),
            plaque.get_rect(),
            border_radius=self.u(6),
        )
        pygame.draw.rect(
            plaque,
            (*accent, 90),
            plaque.get_rect(),
            max(1, self.u(1)),
            border_radius=self.u(6),
        )
        self.screen.blit(plaque, name_rect)
        self.draw_text(
            archetype.name,
            name_font,
            self.TITLE,
            name_rect,
            align="center",
            valign="center",
        )
        skill_names = self.skill_names_for(archetype.name)
        skills_y = name_rect.bottom + self.u(8)
        self.draw_text(
            " · ".join(skill_names),
            detail_font,
            accent,
            pygame.Rect(inner.x, skills_y, inner.width, detail_font.get_height()),
            align="center",
        )
        divider_y = skills_y + detail_font.get_height() + self.u(12)
        # Ornamental divider — thin line with a center diamond.
        pygame.draw.line(
            self.screen,
            self.shade(accent, -16),
            (inner.x + 8, divider_y),
            (inner.right - 8, divider_y),
            max(1, self.u(1)),
        )
        cx = inner.centerx
        dr = self.u(3)
        pygame.draw.polygon(
            self.screen,
            accent,
            [
                (cx, divider_y - dr),
                (cx + dr, divider_y),
                (cx, divider_y + dr),
                (cx - dr, divider_y),
            ],
        )

        visual = self.g.sprites.player_visual(
            archetype.name,
            "idle",
            0.0,
            self.g.ui_elapsed,
            direction=self.archetype_preview_direction(archetype),
        )
        sprite = visual.surface
        sprite_max_h = max(128, int(inner.height * (0.58 if compact_fonts else 0.68)))
        sprite_max_w = max(140, int(inner.width * 0.88))
        scale = min(
            sprite_max_w / sprite.get_width(), sprite_max_h / sprite.get_height()
        )
        scale = max(1.0, min(4.5, scale))
        preview = pygame.transform.scale(
            sprite,
            (
                max(1, int(sprite.get_width() * scale)),
                max(1, int(sprite.get_height() * scale)),
            ),
        )
        preview_anchor = (
            round(visual.anchor[0] * preview.get_width() / max(1, sprite.get_width())),
            round(visual.anchor[1] * preview.get_height() / max(1, sprite.get_height())),
        )
        sprite_y = divider_y + self.u(8)
        pedestal = pygame.Rect(0, 0, preview.get_width() + self.u(40), self.u(18))
        pedestal.center = (inner.centerx, sprite_y + preview.get_height() + 8)
        # Pedestal glow — a soft elliptical halo in the class accent.
        glow = pygame.Surface((pedestal.width, pedestal.height * 2), pygame.SRCALPHA)
        for i in range(3):
            alpha = 60 - i * 16
            pygame.draw.ellipse(
                glow,
                (*accent, alpha),
                glow.get_rect().inflate(-i * self.u(6), -i * self.u(4)),
            )
        self.screen.blit(glow, glow.get_rect(center=pedestal.center))
        # Pedestal base — a thin stone slab.
        pygame.draw.ellipse(self.screen, self.STONE_SHADOW, pedestal)
        pygame.draw.ellipse(
            self.screen,
            self.STONE_LIGHT,
            pedestal,
            max(1, self.u(1)),
        )
        preview_ground = (inner.centerx, pedestal.centery + 2)
        preview_rect = preview.get_rect(
            topleft=(
                preview_ground[0] - preview_anchor[0],
                preview_ground[1] - preview_anchor[1],
            )
        )
        self.screen.blit(preview, preview_rect)
        self.g._archetype_sprite_rect = preview_rect.copy()
        self.g._archetype_sprite_anchor = preview_anchor
        self.g._archetype_sprite_ground = preview_ground

        text_top = pedestal.bottom + self.u(10)
        stat_h = max(self.u(96), self.g.small_font.get_height() * 4 + self.u(22))
        desc_rect = pygame.Rect(
            inner.x,
            text_top,
            inner.width,
            max(30, inner.bottom - text_top - stat_h - 12),
        )
        self.draw_wrapped_text(
            archetype.description,
            detail_font,
            self.TEXT,
            desc_rect,
            max(detail_font.get_height() + self.u(2), self.u(18)),
        )

        stats = [
            ("HP", str(archetype.max_hp)),
            ("Mana", str(archetype.max_mana)),
            ("Stamina", str(archetype.max_stamina)),
            ("Speed", f"{archetype.speed:.2f}"),
            ("Melee", f"+{archetype.melee_bonus}"),
            ("Spell", f"+{archetype.spell_bonus}"),
            ("DR", f"+{archetype.armor_bonus}"),
        ]
        self.draw_stat_grid(
            stats, pygame.Rect(inner.x, inner.bottom - stat_h, inner.width, stat_h)
        )

    def _stat_grid_columns(self, width: int, *, modern: bool) -> int:
        if not modern:
            return 4 if width >= self.u(260) else 3
        if width >= self.u(360):
            return 4
        if width >= self.u(220):
            return 3
        return 2

    def draw_stat_grid(
        self,
        stats: list[tuple[str, str]],
        rect: pygame.Rect,
        *,
        modern: bool = False,
        cards: bool = False,
        accent: Color | None = None,
    ) -> list[pygame.Rect]:
        stat_font = self.g.small_font
        columns = self._stat_grid_columns(rect.width, modern=modern)
        gap = max(self.u(4), 5)
        row_count = max(1, (len(stats) + columns - 1) // columns)
        max_rows = row_count if modern else 2
        cell_w = (rect.width - gap * (columns - 1)) // columns
        cell_h = (
            max(1, (rect.height - gap * (row_count - 1)) // row_count)
            if modern
            else max(stat_font.get_height() + self.u(12), (rect.height - gap) // 2)
        )
        cells: list[pygame.Rect] = []
        card_text_layout: list[
            tuple[str, pygame.font.Font, pygame.Rect, str, pygame.Rect]
        ] = []
        stat_colors: dict[str, Color] = {
            "HP": (215, 88, 82),
            "Mana": (92, 150, 235),
            "Stamina": (118, 192, 112),
            "Speed": (220, 190, 105),
            "Melee": (225, 145, 90),
            "Spell": (168, 125, 230),
            "DR": (170, 185, 205),
        }
        for index, (label, value) in enumerate(stats):
            row = index // columns
            col = index % columns
            if row >= max_rows:
                break
            cell = pygame.Rect(
                rect.x + col * (cell_w + gap),
                rect.y + row * (cell_h + gap),
                cell_w,
                cell_h,
            )
            cells.append(cell.copy())
            if modern and cards:
                tone = stat_colors.get(label, accent or self.WARNING)
                panel_asset = self.ui_asset("hud.bar", cell.size)
                if panel_asset is not None:
                    self.screen.blit(panel_asset, cell)
                else:
                    pygame.draw.rect(
                        self.screen, self.PANEL_INK, cell, border_radius=self.u(4)
                    )
                    pygame.draw.rect(
                        self.screen,
                        self.shade(tone, -48),
                        cell,
                        max(1, self.u(1)),
                        border_radius=self.u(4),
                    )
                line_pad = min(max(4, self.u(6)), max(1, cell.width // 4))
                pygame.draw.line(
                    self.screen,
                    self.shade(tone, -18),
                    (cell.x + line_pad, cell.bottom - max(2, self.u(3))),
                    (cell.right - line_pad, cell.bottom - max(2, self.u(3))),
                    max(1, self.u(1)),
                )
                text_pad = min(max(4, self.u(5)), max(1, cell.width // 5))
                content = cell.inflate(-text_pad * 2, -max(2, self.u(2)) * 2)
                value_w = min(
                    max(stat_font.size(value)[0], content.width // 4),
                    max(1, content.width // 2),
                )
                value_rect = pygame.Rect(
                    content.right - value_w,
                    content.y,
                    value_w,
                    content.height,
                )
                label_rect = pygame.Rect(
                    content.x,
                    content.y,
                    max(1, value_rect.x - content.x - self.u(3)),
                    content.height,
                )
                label_font = self.fit_menu_font(
                    stat_font,
                    max_height=max(1, content.height),
                    max_width=max(1, label_rect.width),
                    texts=(label,),
                    minimum_size=9,
                )
                card_text_layout.append(
                    (label, label_font, label_rect.copy(), value, value_rect.copy())
                )
                self.draw_text(
                    label, label_font, tone, label_rect, valign="center"
                )
                self.draw_text(
                    value,
                    stat_font,
                    self.TITLE,
                    value_rect,
                    align="right",
                    valign="center",
                )
                continue

            if not modern:
                # Procedural mode keeps the original recessed stat cells.
                pygame.draw.rect(
                    self.screen, self.PANEL_INK, cell, border_radius=self.u(5)
                )
                pygame.draw.rect(
                    self.screen,
                    self.STONE_LIGHT,
                    cell,
                    max(1, self.u(1)),
                    border_radius=self.u(5),
                )
                pygame.draw.line(
                    self.screen,
                    self.IRON,
                    (cell.x + self.u(4), cell.y + self.u(1)),
                    (cell.right - self.u(4), cell.y + self.u(1)),
                    max(1, self.u(1)),
                )
            self.draw_text(
                label,
                stat_font,
                self.MUTED,
                pygame.Rect(cell.x + self.u(7), cell.y, cell.width // 2, cell.height),
                valign="center",
            )
            self.draw_text(
                value,
                stat_font,
                self.WARNING,
                pygame.Rect(
                    cell.centerx, cell.y, cell.width // 2 - self.u(7), cell.height
                ),
                align="right",
                valign="center",
            )
        if cards:
            self.g._last_stat_card_text_layout = tuple(card_text_layout)
        return cells

    def archetype_accent(self, name: str) -> Color:
        colors: dict[str, Color] = {
            "Warden": (235, 205, 120),
            "Rogue": (170, 230, 150),
            "Arcanist": (120, 210, 255),
            "Acolyte": (220, 95, 140),
            "Ranger": (150, 215, 105),
        }
        return colors[name] if name in colors else self.accent()

    def class_tagline(self, name: str) -> str:
        return {
            "Warden": "armored cleaver",
            "Rogue": "crit skirmisher",
            "Arcanist": "arc caster",
            "Acolyte": "blood priest",
            "Ranger": "mobile marksman",
        }.get(name, "adventurer")

    def skill_names_for(self, name: str) -> tuple[str, str, str, str]:
        return {
            "Warden": ("Shield Bash", "Guard Bolt", "Time Skip", "Guard Step"),
            "Rogue": ("Backstab", "Knife Fan", "Ambush Bell", "Shadow Dash"),
            "Arcanist": ("Mage Strike", "Arc Bolt", "Frost Nova", "Blink"),
            "Acolyte": ("Blood Rite", "Spirit Bolt", "Spirit Call", "Dark Step"),
            "Ranger": ("Hawk Slash", "Multishot", "Snare Nova", "Vault"),
        }.get(name, ("Slash", "Bolt", "Nova", "Dash"))

    def _draw_character_section_panel(
        self, name: str, rect: pygame.Rect, accent: Color | None = None
    ) -> pygame.Rect:
        content, _used_asset = self.inset_panel(rect, accent)
        self.g._character_inset_rects[name] = rect.copy()
        self.g._character_inset_content_rects[name] = content.copy()
        return content

    def draw_character_menu(self) -> None:
        with self.g.fitted_ui_layout((960, 540)):
            self._draw_character_menu_fitted()

    def _draw_character_menu_fitted(self) -> None:
        width, height = self.screen.get_size()
        dim = pygame.Surface((width, height), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 92))
        self.screen.blit(dim, (0, 0))

        margin = max(self.u(18), 20)
        box_w = min(max(self.u(560), int(width * 0.72)), width - margin * 2)
        box_h = min(max(self.u(400), int(height * 0.82)), height - margin * 2)
        legacy_box = pygame.Rect(
            (width - box_w) // 2,
            (height - box_h) // 2,
            box_w,
            box_h,
        )
        box = legacy_box
        short_layout = height < 440
        modern_requested = self.asset_ui_active()
        if modern_requested:
            if short_layout:
                side_margin = max(16, min(self.u(20), width // 32))
                vertical_margin = max(8, min(self.u(10), height // 36))
                minimum_w, minimum_h = 600, 340
                width_ratio, height_ratio = 0.94, 0.94
            else:
                side_margin = max(22, min(self.u(42), width // 16))
                vertical_margin = max(18, min(self.u(32), height // 18))
                minimum_w, minimum_h = 560, 400
                width_ratio, height_ratio = 0.88, 0.88
            box_w = min(
                max(1, width - side_margin * 2),
                max(minimum_w, round(width * width_ratio)),
            )
            box_h = min(
                max(1, height - vertical_margin * 2),
                max(minimum_h, round(height * height_ratio)),
            )
            box = pygame.Rect(
                (width - box_w) // 2,
                (height - box_h) // 2,
                box_w,
                box_h,
            )
            if self.menu_panel_content_rect(box) is None:
                box = legacy_box
        used_asset = self.panel(box, self.accent(), alpha=250)
        self._character_asset_panel = used_asset

        gap = max(self.u(8), 10)
        safe = self.menu_panel_content_rect(box) if used_asset else None
        if safe is not None:
            inner = safe.inflate(-self.u(5) * 2, -self.u(3) * 2)
            gap = max(self.u(5), 5) if short_layout else max(self.u(6), 7)
        else:
            pad = max(self.u(16), 18)
            inner = box.inflate(-pad * 2, -pad * 2)
        self.g._character_panel_rect = box.copy()
        self.g._character_content_rect = inner.copy()
        self.g._character_inset_rects = {}
        self.g._character_inset_content_rects = {}
        player = self.g.player
        title_h = self.g.font.get_height()
        small_h = self.g.small_font.get_height()
        tiny_h = self.g.tiny_font.get_height()

        close_w = min(
            max(
                self.u(150),
                self.g.small_font.size("C/Esc closes · Tab switches tabs")[0]
                + self.u(20),
            ),
            inner.width // 2,
        )
        self.draw_text(
            "Character",
            self.g.font,
            self.accent(),
            pygame.Rect(inner.x, inner.y, inner.width - close_w - gap, title_h),
        )
        close_rect = pygame.Rect(inner.right - close_w, inner.y, close_w, title_h)
        if not used_asset:
            pygame.draw.rect(
                self.screen, self.PANEL_INK, close_rect, border_radius=self.u(6)
            )
            pygame.draw.rect(
                self.screen,
                self.IRON,
                close_rect,
                max(1, self.u(1)),
                border_radius=self.u(6),
            )
        self.draw_text(
            "C/Esc closes · Tab switches tabs",
            self.g.small_font,
            self.MUTED,
            close_rect.inflate(-self.u(8), 0),
            align="center",
            valign="center",
        )

        subtitle_y = inner.y + title_h + self.u(5)
        # Milestone 3.3: surface unspent mastery tokens in the subtitle so the
        # player knows to open the Disciplines tab and spend them.
        mastery_tokens = self.g.player.mastery_tokens
        point_text = (
            f" · {mastery_tokens} Mastery Token{'s' if mastery_tokens != 1 else ''}"
            if mastery_tokens > 0
            else ""
        )
        subtitle = (
            f"{player.class_name} · Level {player.level} · "
            f"XP {player.xp}/{player.next_xp}{point_text}"
        )
        subtitle_color = self.WARNING if mastery_tokens > 0 else self.TEXT
        self.draw_text(
            subtitle,
            self.g.small_font,
            subtitle_color,
            pygame.Rect(inner.x, subtitle_y, inner.width, small_h),
        )

        # Tab strip — Overview and Disciplines. Tab/Left/Right switch while the
        # menu is open. The active tab is highlighted; the inactive one dims.
        tab_y = subtitle_y + small_h + self.u(4)
        tab_h = max(self.u(22), small_h + self.u(6))
        tab_gap = self.u(6)
        tab_w = (inner.width - tab_gap) // 2
        overview_tab = pygame.Rect(inner.x, tab_y, tab_w, tab_h)
        tree_tab = pygame.Rect(inner.x + tab_w + tab_gap, tab_y, tab_w, tab_h)
        active_tab = self.g.character_menu_tab
        self._draw_character_tab(overview_tab, "Overview (1)", active_tab == "overview")
        self._draw_character_tab(tree_tab, "Disciplines (2)", active_tab == "disciplines")

        stats_y = tab_y + tab_h + gap
        content_top = stats_y
        content_bottom = inner.bottom

        if active_tab == "disciplines":
            discipline_rect = pygame.Rect(
                inner.x,
                content_top,
                inner.width,
                max(1, content_bottom - content_top),
            )
            discipline_content = (
                self._draw_character_section_panel(
                    "disciplines", discipline_rect, self.g.skill_color()
                )
                if used_asset
                else discipline_rect
            )
            self._draw_character_disciplines(discipline_content)
            return

        if used_asset and short_layout:
            stats_h = max(self.u(58), small_h * 2 + self.u(14))
        else:
            stats_h = max(
                self.u(78 if used_asset else 72),
                small_h * 2 + self.u(24),
            )
        stats = [
            ("HP", f"{int(player.hp)}/{player.max_hp}"),
            ("Mana", f"{int(player.mana)}/{player.max_mana}"),
            ("Stamina", f"{int(player.stamina)}/{player.max_stamina}"),
            ("Speed", f"{player.speed:.1f}"),
            ("Melee", str(player.melee_damage())),
            ("Armor", str(player.armor())),
            ("Weapon", self.g.weapon_damage_type().title()),
            ("Nova", self.g.nova_damage_type().title()),
        ]
        stats_rect = pygame.Rect(inner.x, stats_y, inner.width, stats_h)
        stats_content = (
            self._draw_character_section_panel(
                "stats", stats_rect, self.g.skill_color()
            )
            if used_asset
            else stats_rect
        )
        self.draw_stat_grid(stats, stats_content, modern=used_asset)

        content_y = stats_y + stats_h + gap
        content_h = max(1, inner.bottom - content_y)
        if used_asset and short_layout:
            columns, rows = 4, 1
        else:
            columns = 2 if inner.width >= self.u(420) else 1
            rows = 2 if columns == 2 else 4
        card_gap = gap
        card_w = (inner.width - card_gap * (columns - 1)) // columns
        card_h = (content_h - card_gap * (rows - 1)) // rows

        def card_rect(index: int) -> pygame.Rect:
            col = index % columns
            row = index // columns
            return pygame.Rect(
                inner.x + col * (card_w + card_gap),
                content_y + row * (card_h + card_gap),
                card_w,
                max(1, card_h),
            )

        def draw_card(
            name: str,
            rect: pygame.Rect,
            title: str,
            lines: Sequence[tuple[str, Color]],
            accent: Color | None = None,
        ) -> None:
            accent = accent or self.accent()
            modern = bool(getattr(self, "_character_asset_panel", False))
            content = rect
            if modern:
                content = self._draw_character_section_panel(name, rect, accent)
            else:
                pygame.draw.rect(
                    self.screen, self.PANEL_INK, rect, border_radius=self.u(8)
                )

            wash = pygame.Surface(content.size, pygame.SRCALPHA)
            pygame.draw.rect(
                wash,
                (*accent, 14 if modern else 18),
                wash.get_rect(),
                border_radius=self.u(6 if modern else 8),
            )
            self.screen.blit(wash, content)
            if not modern:
                pygame.draw.rect(
                    self.screen,
                    accent,
                    rect,
                    max(1, self.u(1)),
                    border_radius=self.u(8),
                )
                strip = pygame.Rect(
                    rect.x + self.u(8),
                    rect.y + self.u(4),
                    rect.width - self.u(16),
                    self.u(2),
                )
                pygame.draw.rect(
                    self.screen,
                    self.shade(accent, 30),
                    strip,
                    border_radius=self.u(1),
                )
            card_pad = max(self.u(3), 3) if modern else max(self.u(9), 9)
            self.draw_text(
                title,
                self.g.small_font,
                self.WARNING,
                pygame.Rect(
                    content.x + card_pad,
                    content.y + card_pad,
                    content.width - card_pad * 2,
                    small_h,
                ),
            )
            y = content.y + card_pad + small_h + self.u(6)
            line_h = max(tiny_h + self.u(3), self.u(15))
            text_w = max(1, content.width - card_pad * 2)
            for line, color in lines:
                for wrapped in self.wrap_text(line, self.g.tiny_font, text_w):
                    if y + tiny_h > content.bottom - card_pad:
                        return
                    self.draw_text(
                        wrapped,
                        self.g.tiny_font,
                        color,
                        pygame.Rect(content.x + card_pad, y, text_w, line_h),
                    )
                    y += line_h

        melee_name, bolt_name, class_skill_name, dash_name = self.g.skill_names()
        if used_asset and short_layout:
            skill_lines = [
                (f"1 {melee_name} · {self.g.melee_stamina_cost()} STM", self.TEXT),
                (f"2 {bolt_name} · {self.g.bolt_mana_cost()} MP", self.TEXT),
                (
                    f"3 {class_skill_name} · {self.g.class_skill_mana_cost()} MP",
                    self.TEXT,
                ),
                (f"4 {dash_name} · {self.g.dash_stamina_cost()} STM", self.TEXT),
            ]
        else:
            skill_lines = [
                (f"1 {melee_name} · {self.g.melee_stamina_cost()} stamina", self.TEXT),
                (f"2 {bolt_name} · {self.g.bolt_mana_cost()} mana", self.TEXT),
                (
                    f"3 {class_skill_name} · {self.g.class_skill_mana_cost()} mana",
                    self.TEXT,
                ),
                (f"4 {dash_name} · {self.g.dash_stamina_cost()} stamina", self.TEXT),
            ]

        weapon = player.equipment.get("weapon")
        armor = player.equipment.get("armor")
        equipment_lines = [
            (
                weapon.label if weapon else "Weapon: Training Sword (+0 dmg)",
                self.item_color(weapon) if weapon else self.MUTED,
            ),
            (
                armor.label if armor else "Armor: Cloth (+0 armor)",
                self.item_color(armor) if armor else self.MUTED,
            ),
            (f"Bolt type: {self.g.bolt_damage_type().title()}", self.MUTED),
        ]

        upgrades = self.g.acquired_discipline_summaries()
        upgrade_lines = (
            [(name, self.TEXT) for name, _description in upgrades[:4]]
            if upgrades
            else [("No skill upgrades yet", self.MUTED)]
        )

        status_lines: list[tuple[str, Color]] = []
        active_statuses = [
            f"{name.title()} {ttl:.1f}s"
            for name, ttl in player.status_effects.items()
            if ttl > 0
        ]
        status_lines.extend((line, self.TEXT) for line in active_statuses[:2])
        for item in (weapon, armor):
            if item is None or item.unidentified:
                continue
            if item.skill_bonus:
                status_lines.append((f"Skill: {item.skill_bonus}", self.WARNING))
            if item.proc_effect:
                chance = (
                    f" {int(round(item.proc_chance * 100))}%"
                    if 0.0 < item.proc_chance < 1.0
                    else ""
                )
                status_lines.append((f"Proc: {item.proc_effect}{chance}", self.WARNING))
            if item.unique_effect:
                status_lines.append((f"Unique: {item.unique_effect}", self.TITLE))
            if item.attack_speed:
                status_lines.append(
                    (f"{item.attack_speed:+.0%} attack speed", self.TEXT)
                )
            if item.cast_speed:
                status_lines.append((f"{item.cast_speed:+.0%} cast speed", self.TEXT))
            if item.move_speed:
                status_lines.append((f"{item.move_speed:+.0%} movement", self.TEXT))
            if item.thorns:
                status_lines.append((f"{item.thorns} thorns", self.TEXT))
            if item.lifesteal:
                status_lines.append((f"{item.lifesteal:.0%} lifesteal", self.TEXT))
            if item.cursed:
                status_lines.append(("Cursed bargain active", (220, 95, 140)))
        if not status_lines:
            status_lines.append(("No active statuses or procs", self.MUTED))

        draw_card(
            "skills", card_rect(0), "Skills", skill_lines, self.g.skill_color()
        )
        draw_card(
            "equipment", card_rect(1), "Equipment", equipment_lines, self.accent()
        )
        draw_card(
            "upgrades", card_rect(2), "Upgrades", upgrade_lines, self.g.skill_color()
        )
        draw_card(
            "status", card_rect(3), "Status & Procs", status_lines[:4], self.accent()
        )

    def _draw_character_tab(self, rect: pygame.Rect, label: str, active: bool) -> None:
        accent = self.g.skill_color() if active else self.IRON
        fill = self.PANEL_2 if active else self.PANEL_INK
        modern = bool(getattr(self, "_character_asset_panel", False))
        if active or not modern:
            pygame.draw.rect(self.screen, fill, rect, border_radius=self.u(6))
        if not modern:
            pygame.draw.rect(
                self.screen,
                accent,
                rect,
                max(1, self.u(1)),
                border_radius=self.u(6),
            )
        if active:
            strip = pygame.Rect(
                rect.x + self.u(6),
                rect.bottom - self.u(3),
                rect.width - self.u(12),
                self.u(2),
            )
            pygame.draw.rect(
                self.screen, self.shade(accent, 30), strip, border_radius=self.u(1)
            )
        self.draw_text(
            label,
            self.g.small_font,
            self.TEXT if active else self.MUTED,
            rect.inflate(-self.u(10), 0),
            align="center",
            valign="center",
        )

    def _draw_character_disciplines(self, rect: pygame.Rect) -> None:
        """Render the archetype discipline tree as a degree x path grid.

        Each row is a degree (1..5, top to bottom). Each column is a path route.
        Nodes are drawn as small cards with state-tinted borders:
            chosen   — gold border, filled
            available — accent border, ready to pick on level-up/shrine
            locked   — iron border, prerequisites unmet
        A legend, a combo-state strip, and a hint line explain the colors, the
        current combo bonus, and how to gain nodes. Hovering an available node
        with the mouse previews the combo tier it would unlock.
        """
        from ..content import (
            MAX_COMMITTED_PATHS,
            committed_paths,
            is_path_locked,
            discipline_paths_for_archetype,
            disciplines_for_archetype,
            max_discipline_degree,
        )

        player = self.g.player
        archetype = player.class_name
        nodes = disciplines_for_archetype(archetype)
        paths = discipline_paths_for_archetype(archetype)
        max_degree = max_discipline_degree(archetype)
        if not nodes or not paths or max_degree <= 0:
            self.draw_text(
                "No disciplines defined for this archetype.",
                self.g.small_font,
                self.MUTED,
                rect,
                align="center",
                valign="center",
            )
            return

        # Index nodes by (degree, path). A path may have at most one node
        # per degree in the current tree definition.
        grid: dict[tuple[int, str], object] = {}
        for node in nodes:
            grid[(node.degree, node.path)] = node

        tiny_h = self.g.tiny_font.get_height()
        small_h = self.g.small_font.get_height()
        pad = max(self.u(10), 10)
        gap = self.u(6)

        # Acquired-node set, reused by the combo strip and the path headers.
        acquired = set(player.skill_upgrades)

        # Combo state — completed paths and current bonus. Surfaced in a
        # strip above the grid so the player can see their commitment payoff.
        completed, combo_melee, combo_spell, combo_hp = self.g.combo_state()
        completed_count = len(completed)
        combo_active = completed_count >= 2
        # The combo_state total combines the per-path depth bonus and the
        # multi-path combo breadth bonus. Show the breakdown when both apply.
        from ..content import (
            COMBO_BONUS_PER_STEP_MAX_HP,
            COMBO_BONUS_PER_STEP_MELEE,
            COMBO_BONUS_PER_STEP_SPELL,
            COMPLETED_PATH_BONUS_MAX_HP,
            COMPLETED_PATH_BONUS_MELEE,
            COMPLETED_PATH_BONUS_SPELL,
        )

        depth_melee = completed_count * COMPLETED_PATH_BONUS_MELEE
        depth_spell = completed_count * COMPLETED_PATH_BONUS_SPELL
        depth_hp = completed_count * COMPLETED_PATH_BONUS_MAX_HP
        steps = max(0, completed_count - 1) if completed_count >= 2 else 0
        breadth_melee = steps * COMBO_BONUS_PER_STEP_MELEE
        breadth_spell = steps * COMBO_BONUS_PER_STEP_SPELL
        breadth_hp = steps * COMBO_BONUS_PER_STEP_MAX_HP
        # Milestone 3.7 - always show a commitment strip so the player can see
        # how many of the MAX_COMMITTED_PATHS paths they have committed to.
        combo_strip_h = small_h + self.u(4)

        # Header: path names across the top.
        header_h = small_h + self.u(6)
        # Footer: legend + hint.
        legend_h = tiny_h + self.u(8)
        hint_h = tiny_h + self.u(6)
        footer_h = legend_h + hint_h
        grid_rect = pygame.Rect(
            rect.x,
            rect.y + header_h + combo_strip_h,
            rect.width,
            max(
                1,
                rect.height - header_h - combo_strip_h - footer_h - gap * 2,
            ),
        )

        # Combo strip — only drawn when there is something to show.
        combo_rect = pygame.Rect(rect.x, rect.y + header_h, rect.width, combo_strip_h)
        committed_count = len(committed_paths(acquired, archetype))
        if completed_count and combo_active:
            label = (
                f"Committed {committed_count}/{MAX_COMMITTED_PATHS} paths "
                f"· {completed_count} complete: "
                f"depth +{depth_melee}m/+{depth_spell}s/+{depth_hp}hp"
                f" · combo +{breadth_melee}m/+{breadth_spell}s/+{breadth_hp}hp"
            )
            color = self.WARNING
        elif completed_count:
            label = (
                f"Committed {committed_count}/{MAX_COMMITTED_PATHS} paths "
                f"· {completed_count} complete: "
                f"depth +{depth_melee}m/+{depth_spell}s/+{depth_hp}hp"
                f" · commit to 2 for a combo bonus"
            )
            color = self.TEXT
        else:
            label = (
                f"Committed {committed_count}/{MAX_COMMITTED_PATHS} paths "
                f"· pick a node to commit to a route"
            )
            color = self.MUTED
        self.draw_text(
            label,
            self.g.small_font,
            color,
            combo_rect,
            align="center",
            valign="center",
        )

        # Row layout — degree label gutter on the left, columns to its right.
        degree_label_w = max(self.u(28), self.g.tiny_font.size(f"Degree {max_degree}")[0] + self.u(6))
        rows_area = pygame.Rect(
            grid_rect.x + degree_label_w,
            grid_rect.y,
            max(1, grid_rect.width - degree_label_w),
            grid_rect.height,
        )
        # Column layout — columns live inside `rows_area` (after the degree-label
        # gutter), so size them from `rows_area.width` to avoid overflowing the
        # container's right edge.
        col_gap = self.u(6)
        col_w = max(
            1, (rows_area.width - col_gap * (len(paths) - 1)) // len(paths)
        )
        row_h = max(1, (rows_area.height - gap * (max_degree - 1)) // max_degree)

        # Path headers. Locked paths (Milestone 3.7 two-path
        # commitment limit) are dimmed and tagged with a lock glyph so the
        # player can see which routes are sealed.
        committed = committed_paths(acquired, archetype)
        for col, path in enumerate(paths):
            col_x = rows_area.x + col * (col_w + col_gap)
            if path in completed:
                header_color = self.WARNING
            elif path in committed:
                header_color = self.TEXT
            elif is_path_locked(acquired, archetype, path):
                header_color = self.MUTED
            else:
                header_color = self.MUTED
            label = path
            if is_path_locked(acquired, archetype, path):
                label = f"[lock] {path}"
            self.draw_text(
                label,
                self.g.small_font,
                header_color,
                pygame.Rect(col_x, rect.y, col_w, header_h),
                align="center",
                valign="center",
            )

        # Reset the mouse-hover cell map; repopulated as nodes are drawn so
        # `handle_events` can map mouse positions to node keys next frame.
        self.g._discipline_cells = {}

        # Degree rows.
        for degree in range(1, max_degree + 1):
            row_y = rows_area.y + (degree - 1) * (row_h + gap)
            # Degree label in the gutter.
            self.draw_text(
                f"Degree {degree}",
                self.g.tiny_font,
                self.MUTED,
                pygame.Rect(grid_rect.x, row_y, degree_label_w, row_h),
                align="left",
                valign="center",
            )
            for col, path in enumerate(paths):
                node = grid.get((degree, path))
                col_x = rows_area.x + col * (col_w + col_gap)
                cell = pygame.Rect(col_x, row_y, col_w, row_h)
                if node is None:
                    # Empty cell — a faint placeholder keeps the grid aligned.
                    pygame.draw.rect(
                        self.screen,
                        self.PANEL_INK,
                        cell,
                        border_radius=self.u(6),
                    )
                    pygame.draw.rect(
                        self.screen,
                        self.IRON_DARK,
                        cell,
                        max(1, self.u(1)),
                        border_radius=self.u(6),
                    )
                    continue
                self._draw_discipline_cell(node, cell, pad, tiny_h, small_h)
                self.g._discipline_cells[node.key] = cell
                # Hover highlight — a bright outline around the cell the mouse
                # is over, so the player can see which node the preview refers to.
                if self.g.character_menu_hovered_node == node.key:
                    pygame.draw.rect(
                        self.screen,
                        self.TEXT,
                        cell,
                        max(1, self.u(2)),
                        border_radius=self.u(6),
                    )

        # Legend + hint footer.
        legend_y = grid_rect.bottom + gap
        legend_rect = pygame.Rect(rect.x, legend_y, rect.width, legend_h)
        sw_h = max(self.u(10), tiny_h)
        sw_gap = self.u(6)
        x = legend_rect.x
        samples = (
            (self.WARNING, "Chosen"),
            (self.g.skill_color(), "Available"),
            (self.IRON, "Locked"),
            ((132, 74, 74), "Sealed"),
        )
        for color, label in samples:
            sw_rect = pygame.Rect(x, legend_rect.y, sw_h, sw_h)
            pygame.draw.rect(
                self.screen, self.PANEL_INK, sw_rect, border_radius=self.u(2)
            )
            pygame.draw.rect(
                self.screen, color, sw_rect, max(1, self.u(1)), border_radius=self.u(2)
            )
            text_rect = pygame.Rect(
                x + sw_h + sw_gap,
                legend_rect.y,
                self.g.tiny_font.size(label)[0],
                sw_h,
            )
            self.draw_text(
                label, self.g.tiny_font, self.TEXT, text_rect, valign="center"
            )
            x = text_rect.right + self.u(16)
        # Available count on the right of the legend.
        available = self.g.available_disciplines()
        count_text = f"{len(available)} path{'s' if len(available) != 1 else ''} ready"
        count_w = self.g.tiny_font.size(count_text)[0]
        self.draw_text(
            count_text,
            self.g.tiny_font,
            self.g.skill_color() if available else self.MUTED,
            pygame.Rect(legend_rect.right - count_w, legend_rect.y, count_w, sw_h),
            valign="center",
        )

        hint_y = legend_y + legend_h
        hint_rect = pygame.Rect(rect.x, hint_y, rect.width, hint_h)
        # Milestone 3.3: if the player is hovering an available node, preview
        # the combo tier it would unlock; otherwise show the mastery-token spend
        # hint so the player knows how to acquire nodes.
        hovered_key = self.g.character_menu_hovered_node
        hint_text = "Level-ups award mastery tokens · click or press A on an available node to spend one."
        hint_color = self.MUTED
        if hovered_key:
            from ..content import discipline_by_key

            hovered = discipline_by_key(hovered_key)
            if hovered is not None:
                state = self.g.discipline_state(hovered)
                if state == "available":
                    p_melee, p_spell, p_hp = self.g.combo_preview(hovered)
                    _, c_melee, c_spell, c_hp = self.g.combo_state()
                    if (p_melee, p_spell, p_hp) != (c_melee, c_spell, c_hp):
                        hint_text = (
                            f"{hovered.name} -> combo +{p_melee} melee "
                            f"+{p_spell} spell +{p_hp} HP"
                        )
                        hint_color = self.WARNING
                    elif self.g.player.mastery_tokens > 0:
                        hint_text = (
                            f"{hovered.name} · click or press A to spend 1 mastery token"
                        )
                        hint_color = self.g.skill_color()
                    else:
                        hint_text = f"{hovered.name} · no mastery tokens available"
                elif state == "chosen":
                    hint_text = f"{hovered.name} · acquired"
                elif state == "path_locked":
                    hint_text = (
                        f"{hovered.name} · path sealed "
                        f"(max {MAX_COMMITTED_PATHS} paths)"
                    )
                else:
                    hint_text = f"{hovered.name} · locked"
        self.draw_text(
            hint_text,
            self.g.tiny_font,
            hint_color,
            hint_rect,
            align="center",
            valign="center",
        )

    def _draw_discipline_cell(
        self,
        node,
        cell: pygame.Rect,
        pad: int,
        tiny_h: int,
        small_h: int,
    ) -> None:
        state = self.g.discipline_state(node)
        # Milestone 3.7 - "path_locked" nodes are sealed by the two-path
        # commitment limit and render with a dim red wash so they read as a
        # deliberate specialization seal rather than a prereq gate.
        sealed = (132, 74, 74)
        if state == "chosen":
            border = self.WARNING
            fill = self.PANEL_2
            name_color = self.WARNING
        elif state == "available":
            border = self.g.skill_color()
            fill = self.PANEL_2
            name_color = self.TEXT
        elif state == "path_locked":
            border = sealed
            fill = self.PANEL_INK
            name_color = self.MUTED
        else:
            border = self.IRON
            fill = self.PANEL_INK
            name_color = self.MUTED

        pygame.draw.rect(self.screen, fill, cell, border_radius=self.u(6))
        # Soft state-tinted wash.
        wash = pygame.Surface(cell.size, pygame.SRCALPHA)
        wash_alpha = 36 if state == "chosen" else (22 if state == "available" else 0)
        if wash_alpha:
            pygame.draw.rect(
                wash,
                (*border, wash_alpha),
                wash.get_rect(),
                border_radius=self.u(6),
            )
            self.screen.blit(wash, cell)
        pygame.draw.rect(
            self.screen,
            border,
            cell,
            max(1, self.u(1)),
            border_radius=self.u(6),
        )

        inner = cell.inflate(-pad * 2, -pad)
        minimum_detail_h = small_h + self.u(2) + tiny_h
        if inner.height < minimum_detail_h:
            self.draw_text(
                self.ellipsize(node.name, self.g.tiny_font, inner.width),
                self.g.tiny_font,
                name_color,
                inner,
                align="center",
                valign="center",
            )
            return

        name_rect = pygame.Rect(inner.x, inner.y, inner.width, small_h)
        self.draw_text(
            self.ellipsize(node.name, self.g.small_font, name_rect.width),
            self.g.small_font,
            name_color,
            name_rect,
            align="center",
            valign="center",
        )
        desc_rect = pygame.Rect(
            inner.x,
            name_rect.bottom + self.u(2),
            inner.width,
            inner.bottom - name_rect.bottom - self.u(2),
        )
        # Wrap the description into the remaining space; show as many lines as fit.
        lines = self.wrap_text(node.description, self.g.tiny_font, desc_rect.width)
        line_h = tiny_h + self.u(2)
        y = desc_rect.y
        shown = 0
        max_lines = max(1, desc_rect.height // line_h)
        for line in lines[:max_lines]:
            self.draw_text(
                line,
                self.g.tiny_font,
                self.TEXT if state != "locked" else self.MUTED,
                pygame.Rect(desc_rect.x, y, desc_rect.width, line_h),
                align="center",
                valign="top",
            )
            y += line_h
            shown += 1
        if shown == 0:
            self.draw_text(
                self.ellipsize(node.description, self.g.tiny_font, desc_rect.width),
                self.g.tiny_font,
                self.MUTED,
                desc_rect,
                align="center",
                valign="center",
            )
