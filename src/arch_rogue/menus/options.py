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

from typing import Any, Sequence

import pygame

from .. import __version__
from ..constants import MAX_INVENTORY
from ..models import Archetype, Color, Item

MenuRow = tuple[str, str, str]


class MenuOptionsMixin:
    def draw_options_menu(self) -> None:
        panel, content = self.menu_frame("Options", "Settings are saved automatically")
        modern = bool(getattr(self, "_last_menu_frame_used_asset", False))
        difficulty_value = self.g.difficulty_profile().name
        if not self.g.hell_unlocked:
            difficulty_value = f"{difficulty_value} · Hell locked"
        if self.g.input.has_controller():
            controller_value = self.g.input.active_name() or "On"
        elif not self.g.controller_enabled:
            controller_value = "Off"
        else:
            controller_value = "None connected"
        rows: list[MenuRow] = [
            ("F", "Fullscreen", "On" if self.g.fullscreen else "Off"),
            ("D", "Difficulty", difficulty_value),
            ("+ / -", "UI scale", f"{self.g.ui_scale}x"),
            (
                "G",
                "Graphics",
                "Legacy procedural" if self.g.legacy_graphics else "Asset sprites",
            ),
            ("Enter", "Controls & gamepad mapping", ""),
            ("Gamepad", "Controller", controller_value),
            ("A", "Audio cues", "On" if self.g.audio_enabled else "Off"),
            ("M", "Static menu/run music", "On" if self.g.music_enabled else "Off"),
            ("L", "Lighting", "On" if self.g._lighting_enabled else "Off"),
            ("N", "Lighting detail", "On" if self.g._lighting_normal_maps else "Off"),
            ("Enter / O / Backspace", "Return to title", ""),
        ]
        # Visual grouping: (row_index, section_title). Row order above is
        # Display (0-3), Controls (4-5), Audio (6-7), Lights (8-9); the Back
        # row (10) is intentionally ungrouped at the bottom.
        sections = [
            (0, "Display"),
            (4, "Controls"),
            (6, "Audio"),
            (8, "Lights"),
        ]

        # Preserve the selected UI scale when it physically fits. On compact
        # windows, fit a cached fallback font against both row height and the
        # longest label/key rather than clipping oversized text into each row.
        _, screen_h = self.screen.get_size()
        body_font = self.fit_menu_font(
            self.g.font,
            max_height=max(16, screen_h // 18),
            max_width=max(96, int(content.width * 0.58)),
            texts=tuple(label for _, label, _ in rows),
            minimum_size=14,
        )
        detail_font = self.fit_menu_font(
            self.g.small_font,
            max_height=max(12, screen_h // 24),
            max_width=max(72, int(content.width * 0.31)),
            texts=tuple(key for key, _, _ in rows)
            + tuple(value for _, _, value in rows if value),
            minimum_size=12,
        )
        layout_scale = min(
            float(self.g.ui_scale),
            max(
                1.0,
                body_font.get_height() / 15.0,
                detail_font.get_height() / 11.0,
            ),
        )

        def metric(value: int) -> int:
            return max(1, round(value * layout_scale))

        # Keep the selected setting visible instead of shrinking every row until
        # labels become unreadable. The same explicit metrics are passed into the
        # row renderer so the predicted and actual visible ranges cannot diverge.
        row_h = max(body_font.get_height() + metric(8), metric(44))
        gap = metric(3)
        header_h = detail_font.get_height() + metric(12)
        shortcut_h = (
            self.menu_shortcut_section_height(detail_font) if modern else 0
        )
        shortcut_gap = metric(7) if modern else 0
        shortcut_rect = pygame.Rect(
            content.x,
            content.bottom - shortcut_h,
            content.width,
            shortcut_h,
        )
        list_and_note_bottom = (
            shortcut_rect.y - shortcut_gap if modern else content.bottom
        )
        available_content_h = max(1, list_and_note_bottom - content.y)
        note_candidate = max(
            metric(54), detail_font.get_height() * 3 + metric(8)
        )
        minimum_list_h = (row_h + header_h) * (3 if modern else 2)
        note_h = (
            min(note_candidate, available_content_h // 3)
            if available_content_h >= note_candidate + minimum_list_h
            else 0
        )
        note_gap = metric(10) if note_h else 0
        row_rect = pygame.Rect(
            content.x,
            content.y,
            content.width,
            max(1, available_content_h - note_h - note_gap),
        )
        section_map = dict(sections)

        def visible_end(start: int) -> int:
            used = 0
            end = start
            while end < len(rows):
                cost = row_h + (gap if end > start else 0)
                if end in section_map:
                    cost += header_h
                if end > start and used + cost > row_rect.height:
                    break
                used += cost
                end += 1
            return max(start + 1, end)

        scroll = max(0, min(getattr(self.g, "options_scroll", 0), len(rows) - 1))
        cursor = max(0, min(self.g.options_cursor, len(rows) - 1))
        if cursor < scroll:
            scroll = cursor
        end = visible_end(scroll)
        while cursor >= end and scroll < len(rows) - 1:
            scroll += 1
            end = visible_end(scroll)
        self.g.options_scroll = scroll
        self.g._options_row_viewport = row_rect.copy()
        self.g._options_row_font_height = body_font.get_height()
        self.g._options_detail_font = detail_font
        visible_rows = rows[scroll:end]
        self.g._options_visible_rows = tuple(visible_rows)
        visible_sections = [
            (index - scroll, title)
            for index, title in sections
            if scroll <= index < end
        ]
        rendered_rows = self.draw_menu_rows(
            visible_rows,
            row_rect,
            selected_index=cursor - scroll,
            sections=visible_sections,
            body_font=body_font,
            detail_font=detail_font,
            layout_scale=layout_scale,
            row_height=row_h,
            row_gap=gap,
            section_header_height=header_h,
            keys_in_rows=not modern,
        )
        self.g._options_visible_range = (scroll, scroll + len(rendered_rows))
        selected_offset = cursor - scroll
        self.g._options_selected_row_rect = (
            rendered_rows[selected_offset].copy()
            if 0 <= selected_offset < len(rendered_rows)
            else pygame.Rect(0, 0, 0, 0)
        )
        if note_h:
            note_rect = pygame.Rect(
                content.x, row_rect.bottom + note_gap, content.width, note_h
            )
            self.draw_wrapped_text(
                "Difficulty defaults to Hard. Cycle Easy, Medium, and Hard here; "
                "Hell appears after your first clear. Options persist to "
                "~/.arch_rogue_options.json.",
                detail_font,
                self.MUTED,
                note_rect,
            )
        if modern:
            selected = rows[cursor]
            self.draw_menu_shortcut_section(
                shortcut_rect,
                selected[0],
                selected[1],
                font=detail_font,
            )
            self.g._options_shortcut_rect = shortcut_rect.copy()
        self.draw_footer(
            panel,
            "Arrow keys / D-pad navigate · Enter activates · Backspace returns",
        )
