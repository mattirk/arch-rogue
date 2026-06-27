# pyright: reportAttributeAccessIssue=false, reportUnusedImport=false
from __future__ import annotations

from typing import Any, Sequence

import pygame

from .. import __version__
from ..constants import MAX_INVENTORY
from ..models import Archetype, Color, Item

MenuRow = tuple[str, str, str]


class MenuStateOverlayMixin:
    def draw_state_overlay(self) -> None:
        width, height = self.screen.get_size()
        overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 172))
        self.screen.blit(overlay, (0, 0))
        victory = self.g.state == "victory"
        color = (235, 205, 120) if victory else (225, 75, 65)
        title = "Dungeon Cleared" if victory else "You Died"
        unlock_note = (
            " Hell difficulty is now unlocked in Options."
            if victory and getattr(self.g, "hell_unlocked_this_run", False)
            else ""
        )
        subtitle = (
            f"You survived all {self.dungeon_depth} depths and broke the gate."
            f"{unlock_note} Press R to choose a new run."
            if victory
            else f"The dungeon claims another {self.g.player.class_name}. Press R to choose again."
        )
        panel_w = min(width - 64, self.u(820))
        panel_h = min(height - 80, self.u(470))
        panel = pygame.Rect(
            (width - panel_w) // 2, (height - panel_h) // 2, panel_w, panel_h
        )
        self.panel(panel, color, alpha=248)
        inner = panel.inflate(-self.u(54), -self.u(42))
        self.draw_text(
            title,
            self.g.big_font,
            color,
            pygame.Rect(inner.x, inner.y, inner.width, self.g.big_font.get_height()),
            align="center",
        )
        y = inner.y + self.g.big_font.get_height() + self.u(14)
        y = self.draw_wrapped_text(
            subtitle,
            self.g.font,
            self.TEXT,
            pygame.Rect(inner.x, y, inner.width, inner.bottom - y),
            max(self.g.font.get_height() + 4, self.u(24)),
        ) + self.u(14)
        for line in self.g.run_summary_lines():
            self.draw_text(
                line,
                self.g.small_font,
                self.MUTED,
                pygame.Rect(inner.x, y, inner.width, self.g.small_font.get_height()),
                align="center",
            )
            y += max(self.g.small_font.get_height() + self.u(4), self.u(22))

