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
        rows: list[MenuRow] = [
            ("A", "Audio cues", "On" if self.g.audio_enabled else "Off"),
            ("M", "Static menu/run music", "On" if self.g.music_enabled else "Off"),
            ("F", "Fullscreen", "On" if self.g.fullscreen else "Off"),
            ("D", "Difficulty", difficulty_value),
            ("+ / -", "UI scale", f"{self.g.ui_scale}x"),
            ("Enter / O / Backspace", "Return to title", ""),
        ]
        self.draw_menu_rows(rows, content)
        note_rect = pygame.Rect(
            content.x, content.bottom - self.u(60), content.width, self.u(48)
        )
        self.draw_wrapped_text(
            "Difficulty defaults to Hard. Cycle Easy, Medium, and Hard here; "
            "Hell appears after your first clear. Options persist to "
            "~/.arch_rogue_options.json.",
            self.g.small_font,
            self.MUTED,
            note_rect,
        )
        self.draw_footer(panel, "Use the highlighted keys to change settings")

