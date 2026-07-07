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

from typing import Any, Sequence

import pygame

from .. import __version__
from ..constants import MAX_INVENTORY
from ..models import Archetype, Color, Item

MenuRow = tuple[str, str, str]


class MenuOptionsMixin:
    def draw_options_menu(self) -> None:
        panel, content = self.menu_frame("Options", "Settings are saved automatically")
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
            ("A", "Audio cues", "On" if self.g.audio_enabled else "Off"),
            ("M", "Static menu/run music", "On" if self.g.music_enabled else "Off"),
            ("F", "Fullscreen", "On" if self.g.fullscreen else "Off"),
            ("D", "Difficulty", difficulty_value),
            ("+ / -", "UI scale", f"{self.g.ui_scale}x"),
            ("Enter", "Controls & gamepad mapping", ""),
            ("Gamepad", "Controller", controller_value),
            ("Enter / O / Backspace", "Return to title", ""),
        ]
        note_h = max(self.u(54), self.g.small_font.get_height() * 3 + self.u(8))
        row_rect = pygame.Rect(
            content.x,
            content.y,
            content.width,
            max(self.u(120), content.height - note_h - self.u(10)),
        )
        self.draw_menu_rows(rows, row_rect, selected_index=self.g.options_cursor)
        note_rect = pygame.Rect(
            content.x, row_rect.bottom + self.u(10), content.width, note_h
        )
        self.draw_wrapped_text(
            "Difficulty defaults to Hard. Cycle Easy, Medium, and Hard here; "
            "Hell appears after your first clear. Options persist to "
            "~/.arch_rogue_options.json.",
            self.g.small_font,
            self.MUTED,
            note_rect,
        )
        self.draw_footer(
            panel,
            "Arrow keys / D-pad navigate · Enter activates · Backspace returns",
        )
