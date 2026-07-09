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
    Command.ABILITY_3: "Nova (key 3)",
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
    ("3", "Nova", ""),
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
        header_h = self.u(30)
        gap = self.u(10)
        col_gap = self.u(18)
        left_w = int(content.width * 0.43)
        right_w = content.width - left_w - col_gap
        left = pygame.Rect(content.x, content.y, left_w, content.height)
        right = pygame.Rect(
            content.x + left_w + col_gap, content.y, right_w, content.height
        )

        accent = self.accent()
        kb_header = pygame.Rect(left.x, left.y, left.width, header_h)
        kb_rect = pygame.Rect(
            left.x, kb_header.bottom + gap, left.width, left.height - header_h - gap
        )
        self.draw_text("Keyboard & Mouse", self.g.heading_font, accent, kb_header)
        self.draw_menu_rows(KEYBOARD_ROWS, kb_rect)

        pad_status = (
            self.g.input.active_name()
            if self.g.input.has_controller()
            else ("Disabled" if not self.g.controller_enabled else "None connected")
        )
        capture = self.g.controls_capture_command
        subtitle = "press any controller button/trigger" if capture else pad_status
        pad_header = pygame.Rect(right.x, right.y, right.width, header_h)
        pad_rect = pygame.Rect(
            right.x,
            pad_header.bottom + gap,
            right.width,
            right.height - header_h - gap - self.u(42),
        )
        self.draw_text(f"Gamepad — {subtitle}", self.g.heading_font, accent, pad_header)
        self.draw_menu_rows(
            self._gamepad_mapping_rows(),
            pad_rect,
            selected_index=self.g.controls_cursor,
        )
        hint_rect = pygame.Rect(
            right.x, pad_rect.bottom + self.u(8), right.width, self.u(34)
        )
        hint = (
            "Back cancels mapping"
            if capture
            else "Up/down select · Enter/A remaps · Esc/Back returns"
        )
        self.draw_wrapped_text(hint, self.g.small_font, self.MUTED, hint_rect)

        self.draw_footer(
            panel,
            "Controller mappings affect gameplay actions; menu confirm/back stay fixed",
        )
