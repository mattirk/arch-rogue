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

from typing import Any, NamedTuple, Sequence

import pygame

from .. import __version__
from ..constants import MAX_INVENTORY
from ..models import Archetype, Color, Item

MenuRow = tuple[str, str, str]


class AboutEntry(NamedTuple):
    """One renderable line of the About / Quick Help screen.

    The About screen is laid out as a flat list of these entries so a single
    scroll cursor (in entry units) can walk a viewport whose lines have variable
    heights — section headers are taller than body lines, and labeled quick-help
    bodies are indented under an accent-colored label.
    """

    text: str
    font: pygame.font.Font
    color: Color
    height: int
    text_offset: int  # pixels from the box top to draw the text top
    indent: int  # left inset for this line (e.g. labeled body indent)
    underline_y: int  # box-relative y for a section divider, or -1 for none


class MenuTitleMixin:
    def draw_title_menu(self) -> None:
        panel, content = self.menu_frame(
            "Arch Rogue", title_asset="menu.logo.title"
        )
        resume_value = "Ready" if self.g.save_exists() else "None"
        rows: list[MenuRow] = [
            ("N / Enter", "One will descend", ""),
            ("T", "Two will descend", ""),
            ("L / R", "Resume a saved run", resume_value),
            ("O", "Options", ""),
            ("A / C / H / ?", "About, credits, and quick help", ""),
        ]
        modern = bool(getattr(self, "_last_menu_frame_used_asset", False))
        show_hints = self.menu_input_hints_visible()
        shortcut_h = (
            self.menu_shortcut_section_height() if modern and show_hints else 0
        )
        shortcut_gap = min(self.u(7), 7) if modern and show_hints else 0
        shortcut_rect = pygame.Rect(
            content.x,
            content.bottom - shortcut_h,
            content.width,
            shortcut_h,
        )
        note_bottom = shortcut_rect.y - shortcut_gap if modern else content.bottom
        note_h = (
            min(self.u(56), max(36, content.height // 5))
            if modern
            else min(self.u(60), max(38, content.height // 4))
        )
        note_rect = pygame.Rect(
            content.x, note_bottom - note_h, content.width, note_h
        )
        rows_rect = (
            pygame.Rect(
                content.x,
                content.y,
                content.width,
                max(1, note_rect.y - content.y - self.u(7)),
            )
            if modern
            else content
        )
        rendered_rows = self.draw_menu_rows(
            rows,
            rows_rect,
            selected_index=self.g.title_selection,
            keys_in_rows=not modern,
        )
        self.g._title_row_rects = rendered_rows
        self._draw_multiplayer_glyph(rendered_rows)
        self._draw_parchment_note(
            note_rect,
            "Choose an archetype, follow a seeded dark-fantasy storyline, meet story guests, shape future floors with choices, and break the gate tyrant's seal.",
            modern=modern,
        )
        mp_notice = getattr(self.g, "mp_title_notice", "")
        if mp_notice:
            self.draw_text(
                mp_notice,
                self.g.small_font,
                self.WARNING,
                pygame.Rect(
                    note_rect.x,
                    note_rect.y - self.g.small_font.get_height() - self.u(4),
                    note_rect.width,
                    self.g.small_font.get_height(),
                ),
                align="center",
            )
        if modern and show_hints:
            selected_index = max(0, min(self.g.title_selection, len(rows) - 1))
            shortcut_labels = (
                "One will descend",
                "Two will descend",
                "Resume saved run",
                "Options",
                "About & help",
            )
            self.draw_menu_shortcut_section(
                shortcut_rect,
                rows[selected_index][0],
                shortcut_labels[selected_index],
            )
        self.draw_footer(
            panel,
            "Arrows select · Enter confirms · Esc asks before quitting · Backspace returns from submenus",
        )

    def _draw_multiplayer_glyph(
        self, rendered_rows: tuple[pygame.Rect, ...]
    ) -> None:
        """The two-hooded-figures emblem beside the "Two will descend" row.

        Uses the generated ``menu.glyph.multiplayer`` UI asset when available
        and falls back to a small procedural two-figure mark in tests or
        development builds without the asset.
        """

        if len(rendered_rows) < 2:
            return
        row = rendered_rows[1]
        size = max(12, row.height - self.u(8))
        rect = pygame.Rect(
            row.right - size - self.u(10),
            row.y + (row.height - size) // 2,
            size,
            size,
        )
        glyph = self.ui_asset("menu.glyph.multiplayer", rect.size)
        if glyph is not None:
            self.screen.blit(glyph, rect)
            return
        # Fallback: two tiny hooded silhouettes, side by side.
        color = self.shade(self.accent(), 30)
        half = rect.width // 2
        for index in range(2):
            cx = rect.x + half // 2 + index * half
            head_r = max(2, rect.height // 6)
            pygame.draw.circle(
                self.screen, color, (cx, rect.y + head_r + 1), head_r
            )
            pygame.draw.polygon(
                self.screen,
                color,
                (
                    (cx - head_r - 1, rect.bottom - 1),
                    (cx, rect.y + head_r),
                    (cx + head_r + 1, rect.bottom - 1),
                ),
            )

    def _draw_parchment_note(
        self, rect: pygame.Rect, text: str, *, modern: bool = False
    ) -> None:
        """Draw flavor copy as a plaque in legacy mode or a quiet modern wash."""
        plaque = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(
            plaque,
            (208, 188, 142, 24 if modern else 38),
            plaque.get_rect(),
            border_radius=self.u(6),
        )
        if not modern:
            pygame.draw.rect(
                plaque,
                (180, 152, 96, 90),
                plaque.get_rect(),
                max(1, self.u(1)),
                border_radius=self.u(6),
            )
            # Subtle inner shadow line at the top.
            pygame.draw.line(
                plaque,
                (90, 70, 40, 60),
                (self.u(6), self.u(2)),
                (rect.width - self.u(6), self.u(2)),
                max(1, self.u(1)),
            )
        self.screen.blit(plaque, rect)
        self.draw_wrapped_text(
            text,
            self.g.small_font,
            (228, 214, 178),
            rect.inflate(-self.u(16), -self.u(10)),
        )

    def draw_exit_confirmation(self) -> None:
        panel, content = self.menu_frame("Exit Arch Rogue?", "Confirm before closing")
        from_run = self.g.exit_previous_state == "playing"
        rows: list[MenuRow] = [
            ("Y", "Exit game", "Save run" if from_run else "Close"),
            (
                "M",
                "Return to main menu",
                "Save & return" if from_run else "Main menu",
            ),
            (
                "N / Esc / Backspace",
                "Cancel and return to game",
                "Keep playing" if from_run else "Return",
            ),
        ]
        modern = bool(getattr(self, "_last_menu_frame_used_asset", False))
        show_hints = self.menu_input_hints_visible()
        shortcut_h = (
            self.menu_shortcut_section_height() if modern and show_hints else 0
        )
        shortcut_gap = min(self.u(7), 7) if modern and show_hints else 0
        shortcut_rect = pygame.Rect(
            content.x,
            content.bottom - shortcut_h,
            content.width,
            shortcut_h,
        )
        note_bottom = shortcut_rect.y - shortcut_gap if modern else content.bottom
        if modern:
            note_h = min(self.u(78), max(48, content.height // 3))
            note_rect = pygame.Rect(
                content.x, note_bottom - note_h, content.width, note_h
            )
            rows_rect = pygame.Rect(
                content.x,
                content.y,
                content.width,
                max(1, note_rect.y - content.y - self.u(7)),
            )
        else:
            note_rect = pygame.Rect(
                content.x, content.bottom - self.u(92), content.width, self.u(78)
            )
            rows_rect = content
        self.draw_menu_rows(
            rows,
            rows_rect,
            selected_index=max(
                0,
                min(
                    getattr(self.g, "exit_confirmation_cursor", 0),
                    self.g.EXIT_CONFIRMATION_OPTION_COUNT - 1,
                ),
            ),
            keys_in_rows=not modern,
        )
        save_error = getattr(self.g, "last_save_error", "")
        note = (
            save_error
            if save_error
            else (
                "Exit closes the game after saving. Return to main menu saves this run and keeps Arch Rogue open. Cancel resumes the game."
                if from_run
                else "No run is active. Exit closes Arch Rogue; Return to main menu keeps it open."
            )
        )
        self.draw_wrapped_text(note, self.g.small_font, self.MUTED, note_rect)
        if modern and show_hints:
            selected_label = rows[
                max(
                    0,
                    min(
                        getattr(self.g, "exit_confirmation_cursor", 0),
                        self.g.EXIT_CONFIRMATION_OPTION_COUNT - 1,
                    ),
                )
            ][1]
            self.draw_menu_shortcut_section(
                shortcut_rect,
                "Enter / E",
                f"Confirm {selected_label} · Arrow keys select",
            )
        self.draw_footer(
            panel,
            "Arrow keys select · Enter / E confirms · M returns to menu · Esc cancels",
        )

    def draw_about_screen(self) -> None:
        panel, content = self.menu_frame(
            "About / Open Source Licenses", f"Arch Rogue {__version__}"
        )
        # 4.3.17 WS-G: the About screen surfaces the Apache-2.0 license text,
        # the third-party NOTICE list, and the AI Provenance & Liability notice
        # so APK installers get Apache-2.0 §4 attribution without opening the
        # repo. 4.4.7 splits the previously unformatted wall of text into named
        # sections (Overview, Quick Help, Credits, Open Source Licenses, and one
        # section per bundled license document) with gold section headers, iron
        # divider rules, accent-colored quick-help labels, and indented bodies.
        # The whole document is still one scrollable region (Up/Down/PgUp/PgDn on
        # desktop, swipe on mobile); the renderer publishes
        # _licenses_scroll_max / _licenses_visible_lines for the input layer.
        from ..licenses import (
            ai_provenance_text,
            license_text,
            notice_text,
            pygame_lgpl_text,
        )

        mobile = bool(self.g.mobile_mode)
        intro = (
            f"Arch Rogue {__version__} is a Rogue-inspired isometric action RPG "
            "built around compact, replayable dungeon runs, procedural stories, "
            "and dark-level exploration."
        )
        goal = (
            "Descend through ten depths, survive escalating encounters, resolve "
            "story guest dilemmas, defeat the final-depth gate tyrant, then use "
            "the stairs to complete the run."
        )
        difficulty = (
            "Options cycle Easy, Medium, and Hard; Medium is the default, and "
            "Hell unlocks after your first complete clear."
        )
        dark = (
            "Some depths limit sight to a small light radius while monsters "
            "still navigate the dungeon perfectly."
        )
        credits = (
            "Design, code, procedural art, procedural audio, and procedural story "
            "corpus by the Arch Rogue project."
        )
        if mobile:
            combat = (
                "Touch the world to move and aim. Use the six action buttons for "
                "attacks, class skills, movement, and potions. The action rail "
                "shows cooldowns and potion counts."
            )
            story = (
                "Every run generates an archetype-aligned backstory, factions, "
                "relic, guests, and floor beats. Use the interaction control near "
                "a guest, then tap a response to shape future floors."
            )
            loot = (
                "Use the interaction control for pickups, shrines, secrets, and "
                "stairs. Interaction prompts explain risks, and inventory rows "
                "summarize upgrades, curses, and comparisons."
            )
        else:
            combat = (
                "Hold left mouse to move and aim. Number keys trigger skills and "
                "potions: 1 melee, 2 bolt, 3 nova, 4 movement skill, 5 health "
                "potion, 6 mana potion. C opens the character sheet. The bottom "
                "HUD action bar shows hotkeys, cooldowns, and potion counts."
            )
            story = (
                "Every run generates an archetype-aligned backstory, factions, "
                "relic, guests, and floor beats. Near a story guest, press E to "
                "hear their plea or 1-3 to choose Aid, Bargain, or Defy."
            )
            loot = (
                "Press E for pickups, shrines, secrets, and stairs. Interaction "
                "prompts explain risks, and inventory rows summarize upgrades, "
                "curses, and comparisons."
            )
        license_summary = (
            "Arch Rogue is licensed under Apache-2.0. pygame-ce is "
            "LGPL-2.1-or-later. SDL2 and its image/mixer/ttf libraries use zlib; "
            "other bundled Python, crypto, database, image, font, and codec "
            "components retain the licenses listed in the NOTICE below. The full "
            "NOTICE, pygame-ce LGPL, and Apache-2.0 texts follow."
        )

        # Fonts and metrics. Reserve a narrow right rail up front so wrapped
        # lines never collide with the scrollbar when the document overflows.
        if content.height >= 360:
            header_font = self.g.font
            body_font = self.g.small_font
        else:
            header_font = self.g.small_font
            body_font = self.g.tiny_font
        pre_font = self.g.tiny_font
        rail = self.u(10)
        text_rect = pygame.Rect(
            content.x, content.y, max(1, content.width - rail), content.height
        )
        wrap_width = text_rect.width
        line_gap = max(body_font.get_height() + 2, self.u(16))
        pre_line_gap = max(pre_font.get_height() + 2, self.u(14))
        section_gap = self.u(12)
        paragraph_gap = self.u(6)
        item_gap = self.u(5)
        divider_gap = self.u(6)
        label_indent = self.u(14)
        header_text_h = header_font.get_height()
        body_vcenter = max(0, (line_gap - body_font.get_height()) // 2)
        pre_vcenter = max(0, (pre_line_gap - pre_font.get_height()) // 2)

        entries: list[AboutEntry] = []

        def add_section(title: str) -> None:
            entries.append(
                AboutEntry(
                    text=title,
                    font=header_font,
                    color=self.TITLE,
                    height=section_gap + header_text_h + divider_gap,
                    text_offset=section_gap,
                    indent=0,
                    underline_y=section_gap + header_text_h + 1,
                )
            )

        def add_paragraph(text: str) -> None:
            wrapped = self.wrap_text(text, body_font, wrap_width)
            for i, line in enumerate(wrapped):
                if i == 0:
                    entries.append(
                        AboutEntry(
                            line, body_font, self.TEXT,
                            paragraph_gap + line_gap,
                            paragraph_gap + body_vcenter, 0, -1,
                        )
                    )
                else:
                    entries.append(
                        AboutEntry(
                            line, body_font, self.TEXT,
                            line_gap, body_vcenter, 0, -1,
                        )
                    )

        def add_labeled(label: str, body: str) -> None:
            entries.append(
                AboutEntry(
                    label, body_font, self.accent(),
                    item_gap + line_gap, item_gap + body_vcenter, 0, -1,
                )
            )
            for line in self.wrap_text(body, body_font, wrap_width - label_indent):
                entries.append(
                    AboutEntry(
                        line, body_font, self.TEXT,
                        line_gap, body_vcenter, label_indent, -1,
                    )
                )

        def add_preformatted(text: str) -> None:
            first = True
            for src_line in text.split("\n"):
                for line in self.wrap_text(src_line, pre_font, wrap_width):
                    if first:
                        entries.append(
                            AboutEntry(
                                line, pre_font, self.MUTED,
                                paragraph_gap + pre_line_gap,
                                paragraph_gap + pre_vcenter, 0, -1,
                            )
                        )
                        first = False
                    else:
                        entries.append(
                            AboutEntry(
                                line, pre_font, self.MUTED,
                                pre_line_gap, pre_vcenter, 0, -1,
                            )
                        )

        add_section("Overview")
        add_paragraph(intro)
        add_section("Quick Help")
        add_labeled("Goal", goal)
        add_labeled("Combat", combat)
        add_labeled("Difficulty", difficulty)
        add_labeled("Story", story)
        add_labeled("Loot & Discovery", loot)
        add_labeled("Dark Floors", dark)
        add_section("Credits")
        add_paragraph(credits)
        add_section("Open Source Licenses")
        add_paragraph(license_summary)
        add_paragraph(ai_provenance_text())
        add_section("Third-Party Notices")
        add_preformatted(notice_text())
        add_section("pygame-ce — GNU LGPL 2.1-or-later")
        add_preformatted(pygame_lgpl_text())
        add_section("Arch Rogue — Apache License 2.0")
        add_preformatted(license_text())

        # Scroll in entry units across a viewport with variable line heights.
        # Prefix sums make the visible-window and scroll-max search exact and
        # O(log n) per query, so the long license documents stay cheap to lay out
        # every frame.
        n = len(entries)
        prefix = [0] * (n + 1)
        for i, e in enumerate(entries):
            prefix[i + 1] = prefix[i] + e.height
        total_h = prefix[n]

        def visible_end(start: int) -> int:
            # Largest end in [start+1, n] whose cumulative height fits the
            # viewport. Always returns at least start + 1 so a single tall entry
            # (e.g. a header on a tiny window) is never stuck off-screen.
            lo, hi = start + 1, n
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if prefix[mid] - prefix[start] <= content.height:
                    lo = mid
                else:
                    hi = mid - 1
            return lo

        if total_h <= content.height:
            scroll_max = 0
        else:
            # Smallest start index whose window reaches the final entry: that is
            # the bottom-stick scroll position. visible_end is non-decreasing in
            # start, so a binary search finds it.
            lo, hi = 0, max(0, n - 1)
            while lo < hi:
                mid = (lo + hi) // 2
                if visible_end(mid) >= n:
                    hi = mid
                else:
                    lo = mid + 1
            scroll_max = lo

        scroll = max(
            0, min(int(getattr(self.g, "licenses_scroll", 0)), scroll_max)
        )
        self.g.licenses_scroll = scroll
        self.g._licenses_scroll_max = scroll_max
        v_end = visible_end(scroll) if n else 0
        self.g._licenses_visible_lines = max(1, v_end - scroll)

        y = text_rect.y
        for i in range(scroll, v_end):
            e = entries[i]
            line_x = text_rect.x + e.indent
            line_w = max(1, text_rect.width - e.indent)
            if e.text:
                self.draw_text(
                    e.text,
                    e.font,
                    e.color,
                    pygame.Rect(
                        line_x,
                        y + e.text_offset,
                        line_w,
                        max(1, e.height - e.text_offset),
                    ),
                )
            if e.underline_y >= 0:
                uy = y + e.underline_y
                pygame.draw.line(
                    self.screen,
                    self.IRON,
                    (line_x, uy),
                    (text_rect.right, uy),
                    max(1, self.u(1)),
                )
            y += e.height
        if scroll_max > 0:
            self._draw_licenses_scrollbar(
                content, scroll, scroll_max, v_end - scroll, n
            )
        self.draw_footer(
            panel,
            "Up / Down / PgUp / PgDn scroll · Enter or Backspace returns to title",
        )

    def _draw_licenses_scrollbar(
        self,
        rows_rect: pygame.Rect,
        scroll: int,
        scroll_max: int,
        visible_count: int,
        total_count: int,
    ) -> None:
        # Mirrors the options/inventory scrollbar look (recessed track, ember
        # thumb) so the About screen reads as one family with the other menus.
        # The thumb travel is driven by scroll_max (the bottom-stick entry index)
        # rather than total - visible, because the sectioned layout uses variable
        # line heights and the last reachable scroll position is scroll_max.
        if scroll_max <= 0 or total_count <= visible_count or visible_count <= 1:
            return
        track = pygame.Rect(
            rows_rect.right - self.u(5),
            rows_rect.y,
            self.u(4),
            rows_rect.height,
        )
        pygame.draw.rect(self.screen, self.PANEL_INK, track, border_radius=self.u(3))
        pygame.draw.rect(
            self.screen, self.IRON_DARK, track, max(1, self.u(1)), border_radius=self.u(3)
        )
        thumb_h = max(self.u(18), int(track.height * visible_count / total_count))
        travel = max(1, track.height - thumb_h)
        clamped = max(0, min(scroll, scroll_max))
        thumb = pygame.Rect(
            track.x,
            track.y + int(travel * clamped / max(1, scroll_max)),
            track.width,
            thumb_h,
        )
        pygame.draw.rect(self.screen, self.WARNING, thumb, border_radius=self.u(3))
        pygame.draw.rect(
            self.screen, self.shade(self.WARNING, 40), thumb, border_radius=self.u(3)
        )

    def draw_help_overlay(self) -> None:
        with self.g.fitted_ui_layout((960, 540)):
            self._draw_help_overlay_fitted()

    def _draw_help_overlay_fitted(self) -> None:
        width, height = self.screen.get_size()
        overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 118))
        self.screen.blit(overlay, (0, 0))
        margin = max(self.u(20), 28)
        box_w = min(width - margin * 2, self.u(760))
        box_h = min(height - margin * 2, self.u(460))
        box = pygame.Rect((width - box_w) // 2, (height - box_h) // 2, box_w, box_h)
        library = getattr(self.g, "ui_assets", None)
        if (
            self.asset_ui_active()
            and library is not None
            and library.source("menu.panel") is not None
        ):
            margin = max(10, min(self.u(16), width // 28, height // 22))
            box = pygame.Rect(margin, margin, width - margin * 2, height - margin * 2)
        used_asset = self.panel(box, alpha=238)
        safe = self.ui_content_rect("menu.panel", box) if used_asset else None
        if safe is not None:
            inner = safe.inflate(-self.u(6) * 2, -self.u(4) * 2)
        else:
            pad = max(self.u(22), 26)
            inner = box.inflate(-pad * 2, -pad * 2)
        self.g._help_panel_rect = box.copy()
        self.g._help_content_rect = inner.copy()
        title_rect = pygame.Rect(
            inner.x,
            inner.y,
            inner.width,
            self.g.font.get_height(),
        )
        self.draw_text("Run Guide", self.g.font, self.accent(), title_rect)
        lines = [
            "Goal: defeat the gate tyrant in the final room, then use the interaction control on the stairs.",
            "Movement: touch or drag in the world view to move and aim.",
            "Class skills: level ups, Oath Shrines, and skill altars can add class-specific upgrades.",
            "Story guests: use the interaction control to hear their plea, tap a response to shape future floors, and swipe overflowing story text.",
            "Elites/minibosses: named foes have brighter telegraphs, more danger, and better rewards.",
            f"Difficulty: {self.g.difficulty_profile().name} — change it from Options; Hell unlocks after one clear.",
            "Resources: stamina powers melee and movement skills; mana powers bolts and class skills. The action rail combines skill icons and cooldowns.",
            "Inventory and character menus open from the left rail. Tap rows and swipe lists to navigate.",
            "Discovery: unidentified gear needs scrolls, Insight Shrines, or equipping to reveal.",
            "Dark floors: sight is limited to 4 tiles; monsters navigate normally.",
            "Hazards: traps are single-use but dangerous; shrines and secrets can swing a run.",
        ] if self.g.mobile_mode else [
            "Goal: defeat the gate tyrant in the final room, then press E on the stairs.",
            "Movement: hold left mouse to move and aim. Arrow keys can aim without moving.",
            "Class skills: level ups, Oath Shrines, and skill altars can add class-specific upgrades.",
            "Story guests: press E to hear their plea; press 1 Aid, 2 Bargain, or 3 Defy to shape future floors. Q toggles quest HUD info; scroll wheel or PgUp/PgDn scrolls its story text when it overflows.",
            "Elites/minibosses: named foes have brighter telegraphs, more danger, and better rewards.",
            f"Difficulty: {self.g.difficulty_profile().name} — change it from Options; Hell unlocks after one clear.",
            "Resources: stamina powers melee and movement skills; mana powers bolts and class skills. The bottom action bar combines skill icons, hotkeys, and cooldowns.",
            "Inventory and HUD: E picks up; I opens inventory; C opens character; 1-9 triggers skills/potions and uses/equips inventory; Shift+1-9 drops; Tab/S sorts.",
            "Discovery: unidentified gear needs scrolls, Insight Shrines, or equipping to reveal.",
            "Dark floors: sight is limited to 4 tiles; monsters navigate normally. Temporary debug: Ctrl+Shift+D toggles darkness on the current level.",
            "Hazards: traps are single-use but dangerous; shrines and secrets can swing a run.",
            "View: Ctrl + scroll wheel zooms the viewport in/out.",
            "Graphics: Ctrl+Alt+L toggles between authored asset sprites and the procedural legacy renderer.",
        ]
        body_font = self.g.tiny_font if inner.height < 390 else self.g.small_font
        footer_h = (
            self.g.small_font.get_height() + self.u(4)
            if self.menu_input_hints_visible()
            else 0
        )
        y = title_rect.bottom + self.u(10)
        for line in lines:
            y = self.draw_wrapped_text(
                line,
                body_font,
                self.TEXT,
                pygame.Rect(
                    inner.x,
                    y,
                    inner.width,
                    max(1, inner.bottom - footer_h - y),
                ),
                max(body_font.get_height() + self.u(1), self.u(15)),
            ) + self.u(4)
            if y >= inner.bottom - footer_h:
                break
        if self.menu_input_hints_visible():
            self.draw_text(
                "H / ? closes",
                self.g.small_font,
                self.MUTED,
                pygame.Rect(
                    inner.x,
                    inner.bottom - self.g.small_font.get_height(),
                    inner.width,
                    self.g.small_font.get_height(),
                ),
                align="right",
            )
