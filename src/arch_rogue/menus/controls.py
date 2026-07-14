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

import pygame

from ..input import (
    REMAPPABLE_GAMEPAD_COMMANDS,
    Command,
    button_for_command,
    trigger_slot_for_command,
)

MenuRow = tuple[str, str, str]

# Friendly gamepad button names for the SDL Xbox-style layout.
BUTTON_NAMES: dict[int, str] = {
    0: "A",
    1: "B",
    2: "X",
    3: "Y",
    4: "LB",
    5: "RB",
    6: "Back",
    7: "Start",
}

COMMAND_LABELS: dict[str, str] = {
    Command.ABILITY_1: "Melee (key 1)",
    Command.ABILITY_2: "Bolt (key 2)",
    Command.ABILITY_3: "Class skill (key 3)",
    Command.ABILITY_4: "Dash (key 4)",
    Command.ABILITY_5: "Potion (key 5)",
    Command.ABILITY_6: "Mana potion (key 6)",
    Command.INTERACT: "Interact (key E)",
    Command.INVENTORY: "Inventory (key I)",
    Command.CHARACTER: "Character sheet (key C)",
    Command.BACK: "Pause / back / skip",
    Command.CONFIRM: "Confirm / advance",
    Command.HELP: "Help (key H)",
    Command.TAB: "Next tab / sort",
    Command.TAB_PREV: "Previous tab",
}

# Keyboard binding rows (key badge, action label, empty value).
KEYBOARD_ROWS: list[MenuRow] = [
    ("WASD / Arrows", "Move", ""),
    ("Mouse / Arrows", "Aim", ""),
    ("1", "Melee", ""),
    ("2", "Bolt", ""),
    ("3", "Class skill", ""),
    ("4", "Dash", ""),
    ("5", "Potion", ""),
    ("6", "Mana potion", ""),
    ("E", "Interact / talk / open door", ""),
    ("I", "Inventory", ""),
    ("C", "Character sheet", ""),
    ("Q", "Quest log", ""),
    ("H / ?", "Help overlay", ""),
    ("Tab", "Cycle sort / tab", ""),
    ("Esc", "Pause / back", ""),
]


class MenuControlsMixin:
    def _binding_name_for_command(self, command: str) -> str:
        mapping = self.g.gamepad_mapping
        buttons = mapping.get("gameplay_buttons", {})
        if isinstance(buttons, dict):
            button = button_for_command(buttons, command)
            if button is not None:
                return BUTTON_NAMES.get(button, f"Btn {button}")
        triggers = mapping.get("triggers", [])
        if isinstance(triggers, list):
            slot = trigger_slot_for_command(triggers, command)
            if slot is not None:
                names = ("LT", "RT")
                return names[slot] if slot < len(names) else f"Trig {slot}"
        return "Unbound"

    def _gamepad_mapping_rows(self) -> list[MenuRow]:
        rows: list[MenuRow] = []
        capture = self.g.controls_capture_command
        for command in REMAPPABLE_GAMEPAD_COMMANDS:
            label = COMMAND_LABELS.get(command, command)
            binding = self._binding_name_for_command(command)
            value = "Press button/trigger" if capture == command else binding
            rows.append(("Map", label, value))
        return rows

    def draw_controls_menu(self) -> None:
        panel, content = self.menu_frame(
            "Controls", "Keyboard, mouse, and gamepad bindings"
        )
        header_font = self.fit_menu_font(
            self.g.heading_font,
            max_height=max(14, min(self.u(30), content.height // 8)),
            max_width=max(80, int(content.width * 0.42)),
            texts=("Keyboard & Mouse", "Gamepad — None connected"),
            minimum_size=12,
        )
        header_h = header_font.get_height() + max(2, min(self.u(6), 6))
        gap = max(3, min(self.u(8), 8))
        col_gap = max(8, min(self.u(18), content.width // 24))
        left_w = int(content.width * 0.43)
        right_w = content.width - left_w - col_gap
        left = pygame.Rect(content.x, content.y, left_w, content.height)
        right = pygame.Rect(
            content.x + left_w + col_gap, content.y, right_w, content.height
        )

        def draw_fitted_rows(
            rows: list[MenuRow], bounds: pygame.Rect, selected_index: int = -1
        ) -> tuple[pygame.Rect, ...]:
            count = max(1, len(rows))
            row_gap = 1 if bounds.height >= count * 12 else 0
            row_budget = max(
                9, (bounds.height - row_gap * (count - 1)) // count
            )
            body_font = self.fit_menu_font(
                self.g.small_font,
                max_height=max(8, row_budget - 2),
                max_width=max(28, int(bounds.width * 0.48)),
                texts=tuple(label for _key, label, _value in rows),
                minimum_size=8,
            )
            detail_font = self.fit_menu_font(
                self.g.tiny_font,
                max_height=max(8, row_budget - 2),
                max_width=max(24, int(bounds.width * 0.36)),
                texts=tuple(key for key, _label, _value in rows)
                + tuple(value for _key, _label, value in rows if value),
                minimum_size=8,
            )
            row_h = max(
                body_font.get_height() + 2,
                detail_font.get_height() + 2,
                row_budget,
            )
            return self.draw_menu_rows(
                rows,
                bounds,
                selected_index=selected_index,
                body_font=body_font,
                detail_font=detail_font,
                layout_scale=1.0,
                row_height=row_h,
                row_gap=row_gap,
            )

        accent = self.accent()
        kb_header = pygame.Rect(left.x, left.y, left.width, header_h)
        kb_rect = pygame.Rect(
            left.x, kb_header.bottom + gap, left.width, left.height - header_h - gap
        )
        self.draw_text("Keyboard & Mouse", header_font, accent, kb_header)
        keyboard_rows = draw_fitted_rows(KEYBOARD_ROWS, kb_rect)
        self.g._controls_keyboard_row_rects = keyboard_rows

        pad_status = (
            self.g.input.active_name()
            if self.g.input.has_controller()
            else ("Disabled" if not self.g.controller_enabled else "None connected")
        )
        capture = self.g.controls_capture_command
        subtitle = "press any controller button/trigger" if capture else pad_status
        pad_header = pygame.Rect(right.x, right.y, right.width, header_h)
        hint_h = max(18, min(self.u(42), max(18, right.height // 6)))
        pad_rect = pygame.Rect(
            right.x,
            pad_header.bottom + gap,
            right.width,
            max(1, right.height - header_h - gap * 2 - hint_h),
        )
        self.draw_text(f"Gamepad — {subtitle}", header_font, accent, pad_header)
        gamepad_rows = draw_fitted_rows(
            self._gamepad_mapping_rows(),
            pad_rect,
            selected_index=self.g.controls_cursor,
        )
        self.g._controls_gamepad_row_rects = gamepad_rows
        hint_rect = pygame.Rect(
            right.x, pad_rect.bottom + gap, right.width, hint_h
        )
        hint = (
            "Back cancels mapping"
            if capture
            else "Up/down select · Enter/A remaps · Esc/Back returns"
        )
        hint_font = self.fit_menu_font(
            self.g.small_font,
            max_height=max(8, hint_rect.height // 2),
            max_width=max(40, hint_rect.width),
            texts=(hint,),
            minimum_size=8,
        )
        self.draw_wrapped_text(hint, hint_font, self.MUTED, hint_rect)

        self.draw_footer(
            panel,
            "Controller mappings affect gameplay actions; menu confirm/back stay fixed",
        )
