# pyright: reportAttributeAccessIssue=false, reportUnusedImport=false
from __future__ import annotations

from typing import Any, Sequence

import pygame

from .. import __version__
from ..constants import MAX_INVENTORY
from ..models import Archetype, Color, Item

MenuRow = tuple[str, str, str]


class MenuBaseMixin:
    """Shared menu renderer primitives and state."""

    BG = (8, 8, 12)
    PANEL = (18, 17, 22)
    PANEL_2 = (24, 23, 30)
    TEXT = (225, 220, 205)
    MUTED = (170, 165, 155)
    TITLE = (235, 220, 180)
    WARNING = (235, 205, 120)

    def __init__(
        self, game: Any, archetypes: Sequence[Archetype], dungeon_depth: int
    ) -> None:
        self.g = game
        self.archetypes = archetypes
        self.dungeon_depth = dungeon_depth

    @property
    def screen(self) -> pygame.Surface:
        return self.g.screen

    def u(self, value: int) -> int:
        return self.g.ui(value)

    def shade(self, color: Color, amount: int) -> Color:
        return self.g.shade(color, amount)

    def accent(self) -> Color:
        return self.g.theme.accent

    def ellipsize(self, text: str, font: pygame.font.Font, max_width: int) -> str:
        max_width = max(1, max_width)
        if font.size(text)[0] <= max_width:
            return text
        suffix = "…"
        while text and font.size(text + suffix)[0] > max_width:
            text = text[:-1]
        return text + suffix if text else suffix

    def wrap_text(self, text: str, font: pygame.font.Font, max_width: int) -> list[str]:
        max_width = max(1, max_width)
        if not text:
            return [""]
        lines: list[str] = []
        current = ""
        for word in text.split():
            candidate = word if not current else f"{current} {word}"
            if font.size(candidate)[0] <= max_width:
                current = candidate
                continue
            if current:
                lines.append(current)
            current = self.ellipsize(word, font, max_width)
        if current:
            lines.append(current)
        return lines or [""]

    def draw_text(
        self,
        text: str,
        font: pygame.font.Font,
        color: Color,
        rect: pygame.Rect,
        align: str = "left",
        valign: str = "top",
    ) -> None:
        surface = font.render(self.ellipsize(text, font, rect.width), True, color)
        if align == "center":
            x = rect.centerx - surface.get_width() // 2
        elif align == "right":
            x = rect.right - surface.get_width()
        else:
            x = rect.x
        if valign == "center":
            y = rect.centery - surface.get_height() // 2
        elif valign == "bottom":
            y = rect.bottom - surface.get_height()
        else:
            y = rect.y
        self.screen.blit(surface, (x, y))

    def draw_wrapped_text(
        self,
        text: str,
        font: pygame.font.Font,
        color: Color,
        rect: pygame.Rect,
        line_gap: int | None = None,
    ) -> int:
        line_gap = line_gap or max(font.get_height() + 3, self.u(18))
        y = rect.y
        for line in self.wrap_text(text, font, rect.width):
            if y + font.get_height() > rect.bottom:
                return y
            if line:
                self.draw_text(
                    line, font, color, pygame.Rect(rect.x, y, rect.width, line_gap)
                )
            y += line_gap
        return y

    def draw_menu_backdrop(self) -> None:
        width, height = self.screen.get_size()
        accent = self.accent()

        # Keep the title/menu background intentionally clean and static. Earlier
        # animated gradients, scanlines, and grid lines could produce shimmering
        # horizontal artifacts on scaled SDL backends. This version avoids any
        # line-based or per-row drawing on the main menu surface.
        self.screen.fill((9, 9, 14))

        backdrop = pygame.Surface((width, height), pygame.SRCALPHA)
        pygame.draw.ellipse(
            backdrop,
            (*self.shade(accent, -92), 34),
            pygame.Rect(-width // 4, -height // 5, width * 3 // 4, height * 3 // 4),
        )
        pygame.draw.ellipse(
            backdrop,
            (*self.shade(accent, -118), 28),
            pygame.Rect(width // 2, height // 8, width * 2 // 3, height * 2 // 3),
        )
        pygame.draw.ellipse(
            backdrop,
            (0, 0, 0, 74),
            pygame.Rect(-width // 5, height * 2 // 3, width * 7 // 5, height // 2),
        )

        diamond_color = (*self.shade(accent, -120), 24)
        for center_x, center_y, size in (
            (width // 5, height * 3 // 5, max(70, width // 9)),
            (width * 4 // 5, height * 7 // 12, max(90, width // 8)),
            (width // 2, height * 4 // 5, max(120, width // 6)),
        ):
            points = [
                (center_x, center_y - size // 2),
                (center_x + size, center_y),
                (center_x, center_y + size // 2),
                (center_x - size, center_y),
            ]
            pygame.draw.polygon(backdrop, diamond_color, points)

        self.screen.blit(backdrop, (0, 0))

    def panel(
        self, rect: pygame.Rect, accent: Color | None = None, alpha: int = 245
    ) -> None:
        accent = accent or self.accent()
        radius = self.u(10)
        shadow = rect.move(max(2, self.u(3)), max(3, self.u(4)))
        pygame.draw.rect(self.screen, (3, 3, 6), shadow, border_radius=radius)
        if alpha < 255:
            surface = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(
                surface, (*self.PANEL, alpha), surface.get_rect(), border_radius=radius
            )
            self.screen.blit(surface, rect)
        else:
            pygame.draw.rect(self.screen, self.PANEL, rect, border_radius=radius)
        pygame.draw.rect(
            self.screen, accent, rect, max(1, self.u(2)), border_radius=radius
        )
        pygame.draw.line(
            self.screen,
            self.shade(accent, 36),
            (rect.x + self.u(22), rect.y + self.u(22)),
            (rect.right - self.u(22), rect.y + self.u(22)),
            max(1, self.u(1)),
        )
        for corner in (
            rect.topleft,
            (rect.right, rect.y),
            (rect.x, rect.bottom),
            rect.bottomright,
        ):
            pygame.draw.circle(
                self.screen, self.shade(accent, 22), corner, max(2, self.u(2))
            )

    def menu_frame(
        self, title: str, subtitle: str = ""
    ) -> tuple[pygame.Rect, pygame.Rect]:
        width, height = self.screen.get_size()
        self.draw_menu_backdrop()
        title_font = self.g.title_font if height >= self.u(360) else self.g.big_font
        subtitle_font = self.g.small_font
        side_margin = max(self.u(24), 32)
        title_y = max(self.u(30), int(height * 0.12))
        self.draw_text(
            title,
            title_font,
            self.TITLE,
            pygame.Rect(
                side_margin,
                title_y - title_font.get_height() // 2,
                width - side_margin * 2,
                title_font.get_height(),
            ),
            align="center",
            valign="center",
        )
        if subtitle:
            self.draw_text(
                subtitle,
                subtitle_font,
                self.MUTED,
                pygame.Rect(
                    side_margin,
                    title_y + title_font.get_height() // 2 + self.u(8),
                    width - side_margin * 2,
                    subtitle_font.get_height(),
                ),
                align="center",
            )

        top = title_y + title_font.get_height() // 2 + self.u(48)
        footer_space = max(self.g.small_font.get_height() + self.u(18), self.u(42))
        panel_w = min(width - side_margin * 2, self.u(860))
        rect = pygame.Rect(
            (width - panel_w) // 2,
            top,
            panel_w,
            max(self.u(110), height - top - footer_space - self.u(10)),
        )
        self.panel(rect)
        content_pad_x = max(self.u(22), 28)
        content_pad_y = max(self.u(20), 24)
        content = rect.inflate(-content_pad_x * 2, -content_pad_y * 2)
        content.y += self.u(8)
        content.h -= self.u(4)
        return rect, content

    def draw_footer(self, panel: pygame.Rect, text: str) -> None:
        width, height = self.screen.get_size()
        margin = max(self.u(18), 28)
        rect = pygame.Rect(
            margin,
            min(
                height - self.g.small_font.get_height() - self.u(10),
                panel.bottom + self.u(14),
            ),
            width - margin * 2,
            self.g.small_font.get_height() + self.u(4),
        )
        self.draw_text(text, self.g.small_font, self.MUTED, rect, align="center")

    def draw_menu_rows(self, rows: Sequence[MenuRow], rect: pygame.Rect) -> None:
        key_w = min(max(self.u(108), 108), max(self.u(96), rect.width // 3))
        row_h = max(self.g.font.get_height() + self.u(18), self.u(44))
        gap = max(self.u(7), 7)
        y = rect.y
        for key, label, value in rows:
            if y + row_h > rect.bottom:
                break
            row_rect = pygame.Rect(rect.x, y, rect.width, row_h)
            pygame.draw.rect(
                self.screen, self.PANEL_2, row_rect, border_radius=self.u(5)
            )
            pygame.draw.rect(
                self.screen,
                (48, 43, 52),
                row_rect,
                max(1, self.u(1)),
                border_radius=self.u(5),
            )
            key_rect = pygame.Rect(
                row_rect.x + self.u(8),
                row_rect.y + self.u(7),
                key_w - self.u(16),
                row_h - self.u(14),
            )
            pygame.draw.rect(
                self.screen, (38, 34, 45), key_rect, border_radius=self.u(4)
            )
            pygame.draw.rect(
                self.screen,
                self.accent(),
                key_rect,
                max(1, self.u(1)),
                border_radius=self.u(4),
            )
            self.draw_text(
                key,
                self.g.small_font,
                self.accent(),
                key_rect.inflate(-self.u(8), 0),
                align="center",
                valign="center",
            )
            value_w = (
                min(rect.width // 4, self.g.small_font.size(value)[0] + self.u(18))
                if value
                else 0
            )
            label_rect = pygame.Rect(
                row_rect.x + key_w + self.u(12),
                row_rect.y,
                row_rect.width - key_w - value_w - self.u(24),
                row_h,
            )
            self.draw_text(label, self.g.font, self.TEXT, label_rect, valign="center")
            if value:
                value_rect = pygame.Rect(
                    row_rect.right - value_w - self.u(10), row_rect.y, value_w, row_h
                )
                self.draw_text(
                    value,
                    self.g.small_font,
                    self.WARNING,
                    value_rect,
                    align="right",
                    valign="center",
                )
            y += row_h + gap

