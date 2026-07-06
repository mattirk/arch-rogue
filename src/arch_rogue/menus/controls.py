# pyright: reportAttributeAccessIssue=false, reportUnusedImport=false
from __future__ import annotations

import pygame

from ..input import (
    CUTSCENE_BUTTON_COMMANDS,
    DEFAULT_JOY_BUTTON_COMMANDS,
    GAMEPLAY_BUTTON_COMMANDS,
    TRIGGER_COMMANDS,
    Command,
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
    def _gameplay_pad_rows(self) -> list[MenuRow]:
        """Build gamepad rows from the live button/trigger maps so the page
        never drifts from the actual input code."""
        rows: list[MenuRow] = [
            ("L stick", "Move", ""),
            ("R stick", "Aim", ""),
            ("D-pad", "Navigate menus / move", ""),
        ]
        # Sort buttons by index for a stable, predictable listing.
        for button in sorted(GAMEPLAY_BUTTON_COMMANDS):
            name = BUTTON_NAMES.get(button, f"Btn {button}")
            label = COMMAND_LABELS.get(
                GAMEPLAY_BUTTON_COMMANDS[button], GAMEPLAY_BUTTON_COMMANDS[button]
            )
            rows.append((name, label, ""))
        # Triggers: LT (first) = dash, RT (second) = interact.
        trigger_names = ("LT", "RT")
        for slot, cmd in enumerate(TRIGGER_COMMANDS):
            name = trigger_names[slot] if slot < len(trigger_names) else f"Trig {slot}"
            rows.append((name, COMMAND_LABELS.get(cmd, cmd), ""))
        return rows

    def draw_controls_menu(self) -> None:
        panel, content = self.menu_frame(
            "Controls", "Keyboard, mouse, and gamepad bindings"
        )
        header_h = self.u(30)
        gap = self.u(10)
        # Split the content area into a keyboard section and a gamepad section.
        half = content.height // 2
        kb_header = pygame.Rect(content.x, content.y, content.width, header_h)
        kb_rect = pygame.Rect(
            content.x, kb_header.bottom + gap, content.width, half - header_h - gap
        )
        pad_header = pygame.Rect(content.x, content.y + half, content.width, header_h)
        pad_rect = pygame.Rect(
            content.x, pad_header.bottom + gap, content.width, half - header_h - gap
        )

        accent = self.accent()
        self.draw_text("Keyboard & Mouse", self.g.heading_font, accent, kb_header)
        self.draw_menu_rows(KEYBOARD_ROWS, kb_rect)

        pad_status = (
            self.g.input.active_name()
            if self.g.input.has_controller()
            else ("Disabled" if not self.g.controller_enabled else "None connected")
        )
        self.draw_text(
            f"Gamepad — {pad_status}",
            self.g.heading_font,
            accent,
            pad_header,
        )
        self.draw_menu_rows(self._gameplay_pad_rows(), pad_rect)

        self.draw_footer(panel, "Esc / Back / any key returns to Options")
