# pyright: reportAttributeAccessIssue=false, reportUnusedImport=false
from __future__ import annotations

import math
from typing import Any, Sequence

import pygame

from .. import __version__
from ..constants import MAX_INVENTORY
from ..models import Archetype, Color, Item

MenuRow = tuple[str, str, str]


class MenuStateOverlayMixin:
    def draw_state_overlay(self) -> None:
        width, height = self.screen.get_size()
        victory = self.g.state == "victory"
        color = (214, 168, 92) if victory else (176, 48, 44)
        title = "Dungeon Cleared" if victory else "You Died"

        # Heavy blood/ash dimming over the world.
        overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 184))
        # A faint colored wash to set the mood (gold for victory, blood for death).
        wash = pygame.Surface((width, height), pygame.SRCALPHA)
        wash_color = color
        pygame.draw.ellipse(
            wash,
            (*wash_color, 28),
            pygame.Rect(-width // 4, -height // 3, width * 3 // 2, height * 4 // 3),
        )
        self.screen.blit(overlay, (0, 0))
        self.screen.blit(wash, (0, 0))

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
        self.panel(panel, color, alpha=252)

        # Gothic crest ornament above the title.
        crest_y = panel.y + self.u(36)
        self._draw_state_crest(panel.centerx, crest_y, color, victory)

        inner = panel.inflate(-self.u(54), -self.u(42))
        title_y = crest_y + self.u(28)
        self.draw_text(
            title,
            self.g.big_font,
            color,
            pygame.Rect(inner.x, title_y, inner.width, self.g.big_font.get_height()),
            align="center",
        )
        # Thin gold rule under the title.
        rule_y = title_y + self.g.big_font.get_height() + self.u(6)
        pygame.draw.line(
            self.screen,
            self.shade(color, -40),
            (inner.x + self.u(40), rule_y),
            (inner.right - self.u(40), rule_y),
            max(1, self.u(1)),
        )
        pygame.draw.circle(
            self.screen, color, (panel.centerx, rule_y), max(2, self.u(2))
        )

        y = rule_y + self.u(14)
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
