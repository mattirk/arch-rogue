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

import pygame

from ..models import Color

MenuRow = tuple[str, str, str]


class MenuStateOverlayMixin:
    def draw_state_overlay(self) -> None:
        """Draw the full death/victory overlay (background tint + content).

        The mobile frame loop splits this into :meth:`draw_state_overlay_background`
        (full-screen red/gold tint, drawn to the root display before the safe-area
        render target) and :meth:`draw_state_overlay_content` (panels and stats,
        drawn inside the safe area) so the tint covers cutout/notch areas too.
        This single-call entry point is kept for tests and desktop callers that
        draw the overlay in one pass.
        """
        self.draw_state_overlay_background()
        self.draw_state_overlay_content()

    def draw_state_overlay_background(self) -> None:
        """Full-screen blood-red / gold tint behind the death-victory summary.

        On mobile this is drawn to the root display (before the safe-area render
        target clips content) so the tint stretches edge-to-edge like the world
        viewport instead of only covering the safe area.
        """
        self._draw_state_overlay_background()

    def draw_state_overlay_content(self) -> None:
        """Panels, title, crest, and run stats on top of the background tint."""
        with self.g.fitted_ui_layout((960, 540)):
            self._draw_state_overlay_content()

    def _draw_state_overlay_background(self) -> None:
        width, height = self.screen.get_size()
        victory = self.g.state == "victory"
        color = (214, 168, 92) if victory else (176, 48, 44)

        # Full-screen colored dimming over the world — blood red for death, gold for victory.
        overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        if victory:
            overlay.fill((0, 0, 0, 176))
        else:
            overlay.fill((28, 6, 8, 210))
        self.screen.blit(overlay, (0, 0))
        # A faint colored wash to set the mood.
        wash = pygame.Surface((width, height), pygame.SRCALPHA)
        pygame.draw.ellipse(
            wash,
            (*color, 32),
            pygame.Rect(-width // 4, -height // 3, width * 3 // 2, height * 4 // 3),
        )
        self.screen.blit(wash, (0, 0))

    def _draw_state_overlay_content(self) -> None:
        width, height = self.screen.get_size()
        victory = self.g.state == "victory"
        color = (214, 168, 92) if victory else (176, 48, 44)
        title = "Dungeon Cleared" if victory else "You Died"

        unlock_note = (
            " Hell difficulty is now unlocked in Options."
            if victory and getattr(self.g, "hell_unlocked_this_run", False)
            else ""
        )
        subtitle = (
            f"You survived all {self.dungeon_depth} depths and broke the gate."
            f"{unlock_note}"
            if victory
            else f"The dungeon claims another {self.g.player.class_name}."
        )
        prompt = (
            "Press R or Pause / Back to choose a new run"
            if self.menu_input_hints_visible()
            else ""
        )

        panel_w = min(width - 64, self.u(900))
        panel_h = min(height - 80, self.u(490))
        panel = pygame.Rect(
            (width - panel_w) // 2, (height - panel_h) // 2, panel_w, panel_h
        )
        # Opaque base so the red death tint stays behind the panel and does not
        # bleed through the nine-slice asset's transparent corners — the tint
        # is meant for the background only. Use a rounded rect so the background
        # matches the panel asset's corner shape and avoids sharp triangular
        # artifacts at the transparent corner tips.
        panel_radius = self.u(10)
        pygame.draw.rect(
            self.screen,
            self.PANEL_INK,
            panel,
            border_radius=panel_radius,
        )
        # Draw the panel on top of the red overlay so text stays readable.
        # Use a neutral accent for the body so the stone panel reads as a distinct
        # surface on top of the red wash, instead of being tinted red itself.
        used_asset = self.panel(panel, self.IRON, alpha=255)

        safe = self.ui_content_rect("menu.panel", panel) if used_asset else None
        inner = (
            safe.inflate(-self.u(6) * 2, -self.u(4) * 2)
            if safe is not None
            else panel.inflate(-self.u(54), -self.u(42))
        )
        self.g._state_panel_rect = panel.copy()
        self.g._state_content_rect = inner.copy()
        compact_modern = used_asset and inner.height < 390
        title_font = self.g.heading_font if compact_modern else self.g.big_font
        subtitle_font = self.g.small_font if compact_modern else self.g.font

        # Gothic crest ornament above the title, centered.
        crest_y = inner.y + self.u(8) + self.u(14)
        self._draw_state_crest(panel.centerx, crest_y, color, victory)

        # Title, centered.
        title_y = crest_y + self.u(28)
        self.draw_text(
            title,
            title_font,
            color,
            pygame.Rect(inner.x, title_y, inner.width, title_font.get_height()),
            align="center",
        )
        # Thin gold rule under the title, centered.
        rule_y = title_y + title_font.get_height() + self.u(6)
        rule_half = min(inner.width // 2 - self.u(40), self.u(180))
        pygame.draw.line(
            self.screen,
            self.shade(color, -40),
            (panel.centerx - rule_half, rule_y),
            (panel.centerx + rule_half, rule_y),
            max(1, self.u(1)),
        )
        pygame.draw.circle(
            self.screen, color, (panel.centerx, rule_y), max(2, self.u(2))
        )

        # Subtitle, centered.
        sub_y = rule_y + self.u(14)
        sub_h = subtitle_font.get_height() + self.u(6)
        self.draw_text(
            subtitle,
            subtitle_font,
            self.TEXT,
            pygame.Rect(inner.x, sub_y, inner.width, sub_h),
            align="center",
        )

        # Run-stats table inside a recessed sub-panel.
        table_top = sub_y + sub_h + self.u(14)
        table_bottom = inner.bottom - self.u(34) if prompt else inner.bottom
        self._draw_run_stats_table(
            pygame.Rect(inner.x, table_top, inner.width, table_bottom - table_top),
            victory,
        )

        # Prompt footer, centered.
        if prompt:
            self.draw_text(
                prompt,
                self.g.small_font,
                self.MUTED,
                pygame.Rect(
                    inner.x, inner.bottom - self.u(26), inner.width, self.u(22)
                ),
                align="center",
            )

    def _draw_run_stats_table(self, rect: pygame.Rect, victory: bool) -> None:
        """Draw every run statistic in four balanced, readable panels."""
        rows = self._run_stats_rows(victory)
        if not rows:
            return
        self._draw_modern_run_stats_table(rect, rows, victory=victory)

    def _draw_modern_run_stats_table(
        self,
        rect: pygame.Rect,
        rows: list[tuple[str, str]],
        *,
        victory: bool | None = None,
    ) -> None:
        """Arrange run statistics into a padded two-by-two panel grid."""
        sections = self._run_stats_sections(rows)
        self.g._state_stat_panel_rects = {}
        self.g._state_stat_content_rects = {}
        self.g._state_stat_text_layout = []
        if not sections or rect.width <= 0 or rect.height <= 0:
            return

        if victory is None:
            victory = self.g.state == "victory"
        accent = (214, 168, 92) if victory else (176, 48, 44)
        stat_accent = self.TITLE
        gap_x = min(max(8, self.u(14)), max(0, rect.width // 6))
        gap_y = min(max(8, self.u(12)), max(0, rect.height // 6))
        left_w = max(1, (rect.width - gap_x) // 2)
        right_w = max(1, rect.width - gap_x - left_w)
        top_h = max(1, (rect.height - gap_y) // 2)
        bottom_h = max(1, rect.height - gap_y - top_h)

        for index, (heading, items) in enumerate(sections):
            column = index % 2
            row = index // 2
            panel_rect = pygame.Rect(
                rect.x if column == 0 else rect.x + left_w + gap_x,
                rect.y if row == 0 else rect.y + top_h + gap_y,
                left_w if column == 0 else right_w,
                top_h if row == 0 else bottom_h,
            )
            content_rect, text_layout = self._draw_state_stat_panel(
                panel_rect,
                heading,
                items,
                stat_accent,
            )
            key = heading.casefold()
            self.g._state_stat_panel_rects[key] = panel_rect.copy()
            self.g._state_stat_content_rects[key] = content_rect.copy()
            self.g._state_stat_text_layout.extend(text_layout)

    def _draw_state_stat_panel(
        self,
        rect: pygame.Rect,
        heading: str,
        rows: list[tuple[str, str]],
        accent: Color,
    ) -> tuple[pygame.Rect, list[tuple[str, str, pygame.Rect, str, pygame.Rect]]]:
        """Draw one section with deliberate gutters and aligned value edges."""
        # Fill an opaque base so the red death overlay does not bleed through
        # the inset panel's transparent corners. Use a rounded rect so the
        # background matches the inset panel's corner shape and avoids sharp
        # triangular artifacts at the transparent corner tips.
        radius = max(2, self.u(7))
        pygame.draw.rect(
            self.screen,
            self.PANEL_INK,
            rect,
            border_radius=radius,
        )
        safe, _used_asset = self.inset_panel(rect, accent, alpha=255)
        if safe.width <= 0 or safe.height <= 0:
            return safe, []

        pad_x = min(max(6, self.u(8)), max(6, safe.width // 10))
        pad_y = min(max(4, self.u(6)), max(4, safe.height // 12))
        content = safe.inflate(-pad_x * 2, -pad_y * 2)
        if content.width <= 0 or content.height <= 0:
            content = safe.copy()

        heading_h = min(
            max(self.g.tiny_font.get_height() + 2, content.height // 7),
            max(1, content.height // 3),
        )
        heading_h = max(1, heading_h)
        heading_font = self.fit_menu_font(
            self.g.small_font,
            max_height=heading_h,
            max_width=max(1, content.width - self.u(20)),
            texts=(heading.upper(),),
            minimum_size=8,
        )

        header = pygame.Surface((content.width, heading_h), pygame.SRCALPHA)
        header.fill((*self.IRON, 18))
        self.screen.blit(header, content.topleft)
        marker_r = max(2, min(self.u(4), heading_h // 4))
        marker_x = content.x + marker_r + 1
        marker_y = content.y + heading_h // 2
        pygame.draw.polygon(
            self.screen,
            self.shade(accent, 18),
            (
                (marker_x, marker_y - marker_r),
                (marker_x + marker_r, marker_y),
                (marker_x, marker_y + marker_r),
                (marker_x - marker_r, marker_y),
            ),
        )
        heading_left = marker_x + marker_r + max(3, self.u(4))
        self.draw_text(
            heading.upper(),
            heading_font,
            self.shade(accent, 24),
            pygame.Rect(
                heading_left,
                content.y,
                max(1, content.right - heading_left),
                heading_h,
            ),
            valign="center",
        )

        rule_y = min(content.bottom - 1, content.y + heading_h)
        pygame.draw.line(
            self.screen,
            self.shade(accent, -68),
            (content.x, rule_y),
            (content.right, rule_y),
            max(1, self.u(1)),
        )
        body_gap = max(2, min(self.u(5), content.height // 20))
        body_y = min(content.bottom, rule_y + body_gap)
        body = pygame.Rect(content.x, body_y, content.width, content.bottom - body_y)
        if not rows or body.height <= 0:
            return content, []

        row_count = len(rows)
        minimum_row_h = max(1, body.height // row_count)
        label_budget = max(1, int(body.width * 0.46))
        font = self.fit_menu_font(
            self.g.small_font,
            max_height=minimum_row_h,
            max_width=label_budget,
            texts=tuple(label for label, _value in rows),
            minimum_size=8,
        )
        measured_label_w = max(font.size(label)[0] for label, _value in rows)
        label_w = min(
            max(int(body.width * 0.34), measured_label_w + max(8, self.u(10))),
            max(1, int(body.width * 0.46)),
        )
        text_gap = max(6, min(self.u(12), body.width // 16))
        value_x = min(body.right, body.x + label_w + text_gap)
        value_w = max(1, body.right - value_x)
        separator = self.mix(self.PANEL_INK, self.IRON, 0.18)
        text_layout: list[tuple[str, str, pygame.Rect, str, pygame.Rect]] = []

        for index, (label, value) in enumerate(rows):
            row_top = body.y + body.height * index // row_count
            row_bottom = body.y + body.height * (index + 1) // row_count
            row_rect = pygame.Rect(body.x, row_top, body.width, row_bottom - row_top)
            if index:
                pygame.draw.line(
                    self.screen,
                    separator,
                    (row_rect.x, row_rect.y),
                    (row_rect.right, row_rect.y),
                    1,
                )
            label_rect = pygame.Rect(row_rect.x, row_rect.y, label_w, row_rect.height)
            value_rect = pygame.Rect(value_x, row_rect.y, value_w, row_rect.height)
            self.draw_text(
                label,
                font,
                self.MUTED,
                label_rect,
                valign="center",
            )
            value_color = (
                self.BLOOD_LIGHT
                if label == "Cause of death" and value not in ("—", "survived")
                else self.TITLE
            )
            self.draw_text(
                value,
                font,
                value_color,
                value_rect,
                align="right",
                valign="center",
            )
            text_layout.append((heading, label, label_rect, value, value_rect))
        return content, text_layout

    def _run_stats_sections(
        self, rows: list[tuple[str, str]]
    ) -> list[tuple[str, list[tuple[str, str]]]]:
        """Group the flat compatibility list into four meaningful summaries."""
        section_indices = (
            ("Run", (0, 1, 2, 3, 4, 10)),
            ("Combat", (5, 6, 7, 8, 9, 12)),
            ("Exploration", (11, 13, 14, 15, 16, 17)),
            ("Legacy", (18, 19, 20, 21, 22, 23)),
        )
        return [
            (heading, [rows[index] for index in indices if index < len(rows)])
            for heading, indices in section_indices
        ]

    def _run_stats_rows(self, victory: bool) -> list[tuple[str, str]]:
        """Build clean label/value pairs for the run-stats table."""
        g = self.g
        minutes = int(g.elapsed // 60)
        seconds = int(g.elapsed % 60)
        cause = g.run_stats.cause_of_death or ("survived" if victory else "unknown")
        bosses = ", ".join(g.run_stats.defeated_bosses[-3:]) or (
            "Gate defeated" if g.run_stats.boss_killed else "none"
        )
        notable = ", ".join(g.run_stats.notable_loot[-3:]) or "none"
        discoveries = ", ".join(g.run_stats.discoveries[-3:]) or "none"
        progress = g.meta_progress
        return [
            ("Time", f"{minutes:02d}:{seconds:02d}"),
            ("Depth reached", f"{g.current_depth} / {self.dungeon_depth}"),
            ("Difficulty", g.difficulty_profile().name),
            ("Run modifier", g.run_modifier.name),
            ("Class", g.player.class_name),
            ("Kills", str(g.run_stats.kills)),
            ("Boss", "defeated" if g.run_stats.boss_killed else "alive"),
            ("Elites slain", str(g.run_stats.elites_killed)),
            ("Minibosses slain", str(g.run_stats.minibosses_killed)),
            ("Damage taken", str(g.run_stats.damage_taken)),
            ("Cause of death", cause if not victory else "—"),
            ("Loot picked up", str(g.run_stats.loot_picked_up)),
            ("Potions used", str(g.run_stats.potions_used)),
            ("Shrines used", str(g.run_stats.shrines_used)),
            ("Secrets opened", str(g.run_stats.secrets_opened)),
            ("Discoveries", discoveries),
            ("Traps triggered", str(g.run_stats.traps_triggered)),
            ("Challenge rooms", str(g.run_stats.challenge_rooms_cleared)),
            ("Story choices", str(g.run_stats.story_choices)),
            ("Guests met", str(g.run_stats.guests_met)),
            ("Upgrades chosen", str(g.run_stats.upgrades_chosen)),
            ("Notable loot", notable),
            ("Bosses defeated", bosses),
            (
                "Mastery",
                f"best depth {progress.get('best_depth', 0)} · "
                f"clears {progress.get('clears', 0)} · "
                f"known bosses {len(progress.get('bosses_defeated', []))}",
            ),
        ]

    def _draw_state_crest(self, cx: int, cy: int, color: Color, victory: bool) -> None:
        """A small gothic crest: a downward blade for death, a sunburst for victory."""
        r = self.u(14)
        if victory:
            # Sunburst rays.
            for i in range(12):
                angle = i * math.tau / 12
                x1 = cx + int(math.cos(angle) * r * 0.6)
                y1 = cy + int(math.sin(angle) * r * 0.6)
                x2 = cx + int(math.cos(angle) * r * 1.4)
                y2 = cy + int(math.sin(angle) * r * 1.4)
                pygame.draw.line(
                    self.screen,
                    self.shade(color, -20),
                    (x1, y1),
                    (x2, y2),
                    max(1, self.u(2)),
                )
            pygame.draw.circle(self.screen, color, (cx, cy), max(2, r // 2))
            pygame.draw.circle(
                self.screen, self.shade(color, 40), (cx, cy), max(1, r // 4)
            )
        else:
            # Downward blade / broken sword.
            blade = [
                (cx, cy - r),
                (cx + r // 3, cy),
                (cx, cy + r),
                (cx - r // 3, cy),
            ]
            pygame.draw.polygon(self.screen, self.shade(color, -30), blade)
            pygame.draw.polygon(self.screen, color, blade, max(1, self.u(1)))
            # Crossguard.
            pygame.draw.line(
                self.screen,
                self.shade(color, 20),
                (cx - r, cy - r // 2),
                (cx + r, cy - r // 2),
                max(1, self.u(2)),
            )
