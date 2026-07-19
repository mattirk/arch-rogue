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


class MenuTitleMixin:
    def draw_title_menu(self) -> None:
        panel, content = self.menu_frame(
            "Arch Rogue", title_asset="menu.logo.title"
        )
        resume_value = "Ready" if self.g.save_exists() else "None"
        rows: list[MenuRow] = [
            ("N / Enter", "Begin a new descent", ""),
            ("L / R", "Resume a saved run", resume_value),
            ("O", "Options", ""),
            ("A / C / H / ?", "About, credits, and quick help", ""),
        ]
        modern = bool(getattr(self, "_last_menu_frame_used_asset", False))
        shortcut_h = self.menu_shortcut_section_height() if modern else 0
        shortcut_gap = min(self.u(7), 7) if modern else 0
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
        self._draw_parchment_note(
            note_rect,
            "Choose an archetype, follow a seeded dark-fantasy storyline, meet story guests, shape future floors with choices, and break the gate tyrant's seal.",
            modern=modern,
        )
        if modern:
            selected_index = max(0, min(self.g.title_selection, len(rows) - 1))
            shortcut_labels = (
                "New descent",
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
        shortcut_h = self.menu_shortcut_section_height() if modern else 0
        shortcut_gap = min(self.u(7), 7) if modern else 0
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
        if modern:
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
            "About / Onboarding", "Arch Rogue milestone 2.5"
        )
        paragraphs = [
            f"Arch Rogue {__version__} is a Rogue-inspired isometric action RPG built around compact, replayable dungeon runs, procedural stories, and dark-level exploration.",
            "Goal: descend through ten depths, survive escalating encounters, resolve story guest dilemmas, defeat the final-depth gate tyrant, then use the stairs to complete the run.",
            "Combat: hold left mouse to move and aim. Number keys trigger skills and potions: 1 melee, 2 bolt, 3 nova, 4 movement skill, 5 health potion, 6 mana potion. C opens the character sheet. The bottom HUD action bar shows hotkeys, cooldowns, and potion counts.",
            "Difficulty: Options cycle Easy, Medium, and Hard; Medium is the default, and Hell unlocks after your first complete clear.",
            "Story: every run generates an archetype-aligned backstory, factions, relic, guests, and floor beats. Near a story guest, press E to hear their plea or 1-3 to choose Aid, Bargain, or Defy.",
            "Loot and discovery: press E for pickups, shrines, secrets, and stairs. Interaction prompts explain risks, and inventory rows summarize upgrades, curses, and comparisons.",
            "Dark floors: some depths limit sight to a small light radius while monsters still navigate the dungeon perfectly.",
            "Credits: design, code, procedural art, procedural audio, and procedural story corpus by the Arch Rogue project.",
        ]
        y = content.y
        gap = max(self.u(10), 10)
        for paragraph in paragraphs:
            y = (
                self.draw_wrapped_text(
                    paragraph,
                    self.g.small_font,
                    self.TEXT,
                    pygame.Rect(content.x, y, content.width, content.bottom - y),
                    max(self.g.small_font.get_height() + 3, self.u(18)),
                )
                + gap
            )
            if y >= content.bottom:
                break
        self.draw_footer(panel, "Enter or Backspace returns to title")

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
        footer_h = self.g.small_font.get_height() + self.u(4)
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
