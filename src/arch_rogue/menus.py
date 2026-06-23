from __future__ import annotations

from typing import Any, Sequence

import pygame

from . import __version__
from .constants import MAX_INVENTORY
from .models import Archetype, Color, Item

MenuRow = tuple[str, str, str]


class MenuRenderer:
    """Centralized menu and overlay renderer.

    The renderer uses a small set of primitives—centered panels, fixed-width key
    badges, wrapped body text, and clipped single-line labels—so every menu uses
    the same alignment rules instead of hand-placed text offsets.
    """

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

    def draw_title_menu(self) -> None:
        panel, content = self.menu_frame(
            f"Arch Rogue {__version__}",
            "Milestone 2.5 · dark-level cleanup, boss runs, and choice-shaped stories",
        )
        resume_value = "Ready" if self.g.save_exists() else "None"
        rows: list[MenuRow] = [
            ("N / Enter", "Start a new run", ""),
            ("L / R", "Resume saved run", resume_value),
            ("O", "Options", ""),
            ("A / C / H / ?", "About, credits, and quick help", ""),
        ]
        self.draw_menu_rows(rows, content)
        note_rect = pygame.Rect(
            content.x, content.bottom - self.u(72), content.width, self.u(60)
        )
        self.draw_wrapped_text(
            "Choose an archetype, follow a seeded dark-fantasy storyline, meet story guests, shape future floors with choices, and break the gate tyrant's seal.",
            self.g.small_font,
            self.MUTED,
            note_rect,
        )
        self.draw_footer(
            panel, "Esc asks before quitting · Backspace returns from submenus"
        )

    def draw_exit_confirmation(self) -> None:
        panel, content = self.menu_frame("Exit Arch Rogue?", "Confirm before closing")
        from_run = self.g.exit_previous_state == "playing"
        rows: list[MenuRow] = [
            ("Y / Enter", "Exit game", "Save run" if from_run else "Close"),
            ("N / Esc / Backspace", "Cancel and return", "Safe"),
        ]
        self.draw_menu_rows(rows, content)
        note_rect = pygame.Rect(
            content.x, content.bottom - self.u(92), content.width, self.u(78)
        )
        note = (
            "Your current run will be saved before the game closes. Choose Cancel to keep playing."
            if from_run
            else "No run is active. Choose Exit to close the game, or Cancel to return to the menu."
        )
        self.draw_wrapped_text(note, self.g.small_font, self.MUTED, note_rect)
        self.draw_footer(panel, "Y confirms · N cancels")

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

    def draw_about_screen(self) -> None:
        panel, content = self.menu_frame(
            "About / Onboarding", "Arch Rogue milestone 2.5"
        )
        paragraphs = [
            f"Arch Rogue {__version__} is a Rogue-inspired isometric action RPG built around compact, replayable dungeon runs, procedural stories, and dark-level exploration.",
            "Goal: descend through ten depths, survive escalating encounters, resolve story guest dilemmas, defeat the final-depth gate tyrant, then use the stairs to complete the run.",
            "Combat: hold left mouse to move and aim. Space uses your class melee skill, F casts your bolt skill, V uses your nova skill, Left Ctrl uses your movement skill, and C opens the character sheet. The bottom HUD action bar shows hotkeys, cooldowns, and potion counts.",
            "Difficulty: Options cycle Easy, Medium, and Hard; Hard is the default, and Hell unlocks after your first complete clear.",
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
        width, height = self.screen.get_size()
        overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 118))
        self.screen.blit(overlay, (0, 0))
        margin = max(self.u(20), 28)
        box_w = min(width - margin * 2, self.u(760))
        box_h = min(height - margin * 2, self.u(430))
        box = pygame.Rect((width - box_w) // 2, (height - box_h) // 2, box_w, box_h)
        self.panel(box, alpha=238)
        pad = max(self.u(22), 26)
        title_rect = pygame.Rect(
            box.x + pad,
            box.y + pad,
            box.width - pad * 2,
            self.g.font.get_height(),
        )
        self.draw_text("Run Guide", self.g.font, self.accent(), title_rect)
        lines = [
            "Goal: defeat the gate tyrant in the final room, then press E on the stairs.",
            "Movement: hold left mouse to move and aim. Arrow keys can aim without moving.",
            "Class skills: level ups, Oath Shrines, and skill altars can add class-specific upgrades.",
            "Story guests: press E to hear their plea; press 1 Aid, 2 Bargain, or 3 Defy to shape future floors. Q toggles quest HUD info.",
            "Elites/minibosses: named foes have brighter telegraphs, more danger, and better rewards.",
            f"Difficulty: {self.g.difficulty_profile().name} — change it from Options; Hell unlocks after one clear.",
            "Resources: stamina powers melee and movement skills; mana powers bolt and nova skills. The bottom action bar combines skill icons, hotkeys, and cooldowns.",
            "Inventory and HUD: E picks up; I opens inventory; C opens character; R drinks health, T drinks mana; 1-9 uses/equips; Shift+1-9 drops; Tab/S sorts.",
            "Discovery: unidentified gear needs scrolls, Insight Shrines, or equipping to reveal.",
            "Dark floors: sight is limited to 4 tiles; monsters navigate normally. Temporary debug: Ctrl+Shift+D toggles darkness on the current level.",
            "Hazards: traps are single-use but dangerous; shrines and secrets can swing a run.",
        ]
        y = title_rect.bottom + self.u(18)
        for line in lines:
            y = self.draw_wrapped_text(
                line,
                self.g.small_font,
                self.TEXT,
                pygame.Rect(
                    box.x + pad,
                    y,
                    box.width - pad * 2,
                    box.bottom - y - self.u(26),
                ),
                max(self.g.small_font.get_height() + self.u(2), self.u(18)),
            ) + self.u(8)
            if y >= box.bottom:
                break
        self.draw_text(
            "H / ? closes",
            self.g.small_font,
            self.MUTED,
            pygame.Rect(
                box.x + pad,
                box.bottom - self.g.small_font.get_height() - self.u(12),
                box.width - pad * 2,
                self.g.small_font.get_height(),
            ),
            align="right",
        )

    def draw_archetype_select(self) -> None:
        width, height = self.screen.get_size()
        self.draw_menu_backdrop()
        selected = self.g.selected_archetype
        accent = self.archetype_accent(selected.name)

        title_font = self.g.title_font if height >= self.u(330) else self.g.big_font
        subtitle_font = self.g.font
        title_h = title_font.get_height()
        top_margin = max(self.u(12), int(height * 0.04))
        self.draw_text(
            "Choose Your Archetype",
            title_font,
            self.TITLE,
            pygame.Rect(28, top_margin, width - 56, title_h),
            align="center",
        )
        subtitle_y = top_margin + title_h + self.u(5)
        self.draw_text(
            "Arrow keys select · Enter begins · Backspace returns",
            subtitle_font,
            self.MUTED,
            pygame.Rect(32, subtitle_y, width - 64, subtitle_font.get_height()),
            align="center",
        )

        footer_h = max(self.u(30), self.g.small_font.get_height() + self.u(14))
        content_top = subtitle_y + subtitle_font.get_height() + self.u(14)
        content_margin = max(self.u(14), 18)
        content = pygame.Rect(
            content_margin,
            content_top,
            max(1, width - content_margin * 2),
            max(1, height - content_top - footer_h - self.u(8)),
        )
        if content.height < 230:
            content.y = max(86, content.y - (230 - content.height))
            content.height = max(1, min(230, height - content.y - footer_h - 10))

        compact = width < max(620, self.u(360)) or content.width < self.u(360)
        gap = max(self.u(8), 12)
        base_list_w = min(self.u(250), max(self.u(180), int(content.width * 0.36)))
        preview_min_w = min(self.u(250), max(self.u(180), int(content.width * 0.28)))
        list_w = (
            min(base_list_w * 4, max(base_list_w, content.width - gap - preview_min_w))
            if not compact
            else content.width
        )
        if compact:
            min_preview_h = min(max(self.u(110), 110), max(1, content.height - gap - 1))
            preferred_list_h = min(
                max(self.u(128), content.height // 2), content.height
            )
            if content.height > gap + min_preview_h:
                list_h = min(preferred_list_h, content.height - gap - min_preview_h)
                list_h = max(1, list_h)
                preview_y = content.y + list_h + gap
                preview_h = max(1, content.bottom - preview_y)
            else:
                list_h = max(1, content.height // 2)
                preview_y = content.y + list_h
                preview_h = max(1, content.bottom - preview_y)
            list_rect = pygame.Rect(content.x, content.y, content.width, list_h)
            preview_rect = pygame.Rect(content.x, preview_y, content.width, preview_h)
        else:
            list_rect = pygame.Rect(content.x, content.y, list_w, content.height)
            preview_rect = pygame.Rect(
                list_rect.right + gap,
                content.y,
                content.right - list_rect.right - gap,
                content.height,
            )

        self.panel(list_rect, accent, alpha=248)
        self.panel(preview_rect, accent, alpha=248)
        preview_header_cover = pygame.Rect(
            preview_rect.x + self.u(6),
            preview_rect.y + self.u(4),
            preview_rect.width - self.u(12),
            self.g.big_font.get_height() + self.u(16),
        )
        pygame.draw.rect(self.screen, self.PANEL, preview_header_cover)
        self.draw_archetype_list(list_rect, selected)
        self.draw_archetype_preview(preview_rect, selected)

        footer_font = self.g.small_font
        self.draw_text(
            f"Press 1-{min(len(self.archetypes), 9)} to jump directly to a class",
            footer_font,
            self.WARNING,
            pygame.Rect(32, height - footer_h, width - 64, footer_h - 4),
            align="center",
            valign="center",
        )

    def draw_archetype_list(self, rect: pygame.Rect, selected: Archetype) -> None:
        compact_fonts = rect.height < self.u(190)
        heading_font = self.g.font if compact_fonts else self.g.heading_font
        name_font_large = self.g.font
        row_font = self.g.small_font
        inner = rect.inflate(-self.u(22), -self.u(22))
        header_rect = pygame.Rect(
            inner.x,
            inner.y - self.u(2),
            inner.width,
            heading_font.get_height() + self.u(10),
        )
        pygame.draw.rect(self.screen, self.PANEL, header_rect)
        self.draw_text(
            "Classes",
            heading_font,
            self.TITLE,
            pygame.Rect(inner.x, inner.y, inner.width, heading_font.get_height()),
        )
        header_line_y = inner.y + heading_font.get_height() + self.u(6)
        pygame.draw.line(
            self.screen,
            self.shade(self.archetype_accent(selected.name), 18),
            (inner.x, header_line_y),
            (inner.right, header_line_y),
            max(1, self.u(1)),
        )
        list_top = header_line_y + self.u(10)
        gap = max(self.u(4), 5)
        available_rows_h = max(
            1, inner.bottom - list_top - gap * (len(self.archetypes) - 1)
        )
        row_h = max(
            self.g.small_font.get_height() + self.u(18),
            min(self.u(74), available_rows_h // len(self.archetypes)),
        )
        y = list_top
        for index, archetype in enumerate(self.archetypes):
            row = pygame.Rect(inner.x, y, inner.width, row_h)
            is_selected = archetype == selected
            row_accent = self.archetype_accent(archetype.name)
            fill = self.shade(row_accent, -92) if is_selected else self.PANEL_2
            border = row_accent if is_selected else (58, 52, 62)
            radius = self.u(7)
            pygame.draw.rect(self.screen, fill, row, border_radius=radius)
            pygame.draw.rect(
                self.screen, border, row, max(1, self.u(1)), border_radius=radius
            )
            if is_selected:
                strip = pygame.Rect(
                    row.x, row.y + self.u(4), self.u(4), row.height - self.u(8)
                )
                pygame.draw.rect(
                    self.screen, row_accent, strip, border_radius=self.u(3)
                )
            badge_size = min(self.u(34), row_h - self.u(10))
            badge = pygame.Rect(
                row.x + self.u(10),
                row.y + (row_h - badge_size) // 2,
                badge_size,
                badge_size,
            )
            pygame.draw.rect(self.screen, (38, 34, 45), badge, border_radius=self.u(5))
            pygame.draw.rect(
                self.screen, border, badge, max(1, self.u(1)), border_radius=self.u(5)
            )
            self.draw_text(
                str(index + 1),
                row_font,
                border,
                badge,
                align="center",
                valign="center",
            )
            name_rect = pygame.Rect(
                badge.right + self.u(14),
                row.y + self.u(3),
                row.width - badge.width - self.u(28),
                max(1, row_h // 2 - 2),
            )
            name_font = name_font_large if row_h >= 46 else row_font
            self.draw_text(
                archetype.name,
                name_font,
                self.TITLE if is_selected else self.TEXT,
                name_rect,
                valign="center",
            )
            role_rect = pygame.Rect(
                badge.right + self.u(14),
                row.centery + self.u(2),
                row.width - badge.width - self.u(28),
                max(1, row_h // 2 - 6),
            )
            self.draw_text(
                self.class_tagline(archetype.name),
                row_font,
                self.MUTED,
                role_rect,
                valign="center",
            )
            y += row_h + gap

    def draw_archetype_preview(self, rect: pygame.Rect, archetype: Archetype) -> None:
        compact_fonts = rect.height < self.u(190)
        accent = self.archetype_accent(archetype.name)
        name_font = self.g.heading_font if compact_fonts else self.g.big_font
        detail_font = self.g.small_font if compact_fonts else self.g.font
        inner = rect.inflate(-self.u(28), -self.u(24))
        name_h = name_font.get_height()
        name_rect = pygame.Rect(
            inner.x, inner.y + self.u(5), inner.width, name_h + self.u(8)
        )
        pygame.draw.rect(self.screen, self.PANEL, name_rect.inflate(0, self.u(6)))
        self.draw_text(
            archetype.name,
            name_font,
            self.TITLE,
            name_rect,
            align="center",
            valign="center",
        )
        skill_names = self.skill_names_for(archetype.name)
        skills_y = name_rect.bottom + self.u(8)
        self.draw_text(
            " · ".join(skill_names),
            detail_font,
            accent,
            pygame.Rect(inner.x, skills_y, inner.width, detail_font.get_height()),
            align="center",
        )
        divider_y = skills_y + detail_font.get_height() + self.u(12)
        pygame.draw.line(
            self.screen,
            self.shade(accent, -16),
            (inner.x + 8, divider_y),
            (inner.right - 8, divider_y),
            max(1, self.u(1)),
        )

        sprite = self.g.sprites.player_sprites.get(
            archetype.name, self.g.sprites.player
        )
        sprite_max_h = max(128, int(inner.height * (0.58 if compact_fonts else 0.68)))
        sprite_max_w = max(140, int(inner.width * 0.88))
        scale = min(
            sprite_max_w / sprite.get_width(), sprite_max_h / sprite.get_height()
        )
        scale = max(1.0, min(4.5, scale))
        preview = pygame.transform.scale(
            sprite,
            (
                max(1, int(sprite.get_width() * scale)),
                max(1, int(sprite.get_height() * scale)),
            ),
        )
        sprite_y = divider_y + self.u(8)
        pedestal = pygame.Rect(0, 0, preview.get_width() + self.u(40), self.u(18))
        pedestal.center = (inner.centerx, sprite_y + preview.get_height() + 8)
        glow = pygame.Surface((pedestal.width, pedestal.height), pygame.SRCALPHA)
        pygame.draw.ellipse(glow, (*accent, 72), glow.get_rect())
        self.screen.blit(glow, pedestal)
        self.screen.blit(
            preview, preview.get_rect(midbottom=(inner.centerx, pedestal.centery + 2))
        )

        text_top = pedestal.bottom + self.u(10)
        stat_h = max(self.u(96), self.g.small_font.get_height() * 4 + self.u(22))
        desc_rect = pygame.Rect(
            inner.x,
            text_top,
            inner.width,
            max(30, inner.bottom - text_top - stat_h - 12),
        )
        self.draw_wrapped_text(
            archetype.description,
            detail_font,
            self.TEXT,
            desc_rect,
            max(detail_font.get_height() + self.u(2), self.u(18)),
        )

        stats = [
            ("HP", str(archetype.max_hp)),
            ("Mana", str(archetype.max_mana)),
            ("Stamina", str(archetype.max_stamina)),
            ("Speed", f"{archetype.speed:.2f}"),
            ("Melee", f"+{archetype.melee_bonus}"),
            ("Spell", f"+{archetype.spell_bonus}"),
            ("DR", f"+{archetype.armor_bonus}"),
        ]
        self.draw_stat_grid(
            stats, pygame.Rect(inner.x, inner.bottom - stat_h, inner.width, stat_h)
        )

    def draw_stat_grid(self, stats: list[tuple[str, str]], rect: pygame.Rect) -> None:
        stat_font = self.g.small_font
        columns = 4 if rect.width >= self.u(260) else 3
        gap = max(self.u(4), 5)
        cell_w = (rect.width - gap * (columns - 1)) // columns
        cell_h = max(stat_font.get_height() + self.u(12), (rect.height - gap) // 2)
        for index, (label, value) in enumerate(stats):
            row = index // columns
            col = index % columns
            if row > 1:
                break
            cell = pygame.Rect(
                rect.x + col * (cell_w + gap),
                rect.y + row * (cell_h + gap),
                cell_w,
                cell_h,
            )
            pygame.draw.rect(self.screen, self.PANEL_2, cell, border_radius=self.u(5))
            pygame.draw.rect(
                self.screen,
                (58, 52, 62),
                cell,
                max(1, self.u(1)),
                border_radius=self.u(5),
            )
            self.draw_text(
                label,
                stat_font,
                self.MUTED,
                pygame.Rect(cell.x + self.u(7), cell.y, cell.width // 2, cell.height),
                valign="center",
            )
            self.draw_text(
                value,
                stat_font,
                self.WARNING,
                pygame.Rect(
                    cell.centerx, cell.y, cell.width // 2 - self.u(7), cell.height
                ),
                align="right",
                valign="center",
            )

    def archetype_accent(self, name: str) -> Color:
        return {
            "Warden": (235, 205, 120),
            "Rogue": (170, 230, 150),
            "Arcanist": (120, 210, 255),
            "Acolyte": (220, 95, 140),
            "Ranger": (150, 215, 105),
        }.get(name, self.accent())

    def class_tagline(self, name: str) -> str:
        return {
            "Warden": "armored cleaver",
            "Rogue": "crit skirmisher",
            "Arcanist": "arc caster",
            "Acolyte": "blood priest",
            "Ranger": "mobile marksman",
        }.get(name, "adventurer")

    def skill_names_for(self, name: str) -> tuple[str, str, str, str]:
        return {
            "Warden": ("Shield Bash", "Guard Bolt", "Bulwark Wave", "Guard Step"),
            "Rogue": ("Backstab", "Knife Fan", "Smoke Burst", "Shadow Dash"),
            "Arcanist": ("Mage Strike", "Arc Bolt", "Frost Nova", "Blink"),
            "Acolyte": ("Blood Rite", "Spirit Bolt", "Blood Nova", "Dark Step"),
            "Ranger": ("Hawk Slash", "Multishot", "Snare Nova", "Vault"),
        }.get(name, ("Slash", "Bolt", "Nova", "Dash"))

    def draw_character_menu(self) -> None:
        width, height = self.screen.get_size()
        dim = pygame.Surface((width, height), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 92))
        self.screen.blit(dim, (0, 0))

        margin = max(self.u(18), 20)
        box_w = min(max(self.u(560), int(width * 0.72)), width - margin * 2)
        box_h = min(max(self.u(400), int(height * 0.82)), height - margin * 2)
        box = pygame.Rect((width - box_w) // 2, (height - box_h) // 2, box_w, box_h)
        self.panel(box, self.accent(), alpha=250)

        pad = max(self.u(16), 18)
        gap = max(self.u(8), 10)
        inner = box.inflate(-pad * 2, -pad * 2)
        player = self.g.player
        title_h = self.g.font.get_height()
        small_h = self.g.small_font.get_height()
        tiny_h = self.g.tiny_font.get_height()

        close_w = min(
            max(self.u(130), self.g.small_font.size("C or Esc closes")[0] + self.u(20)),
            inner.width // 2,
        )
        self.draw_text(
            "Character",
            self.g.font,
            self.accent(),
            pygame.Rect(inner.x, inner.y, inner.width - close_w - gap, title_h),
        )
        close_rect = pygame.Rect(inner.right - close_w, inner.y, close_w, title_h)
        pygame.draw.rect(self.screen, (30, 27, 36), close_rect, border_radius=self.u(6))
        pygame.draw.rect(
            self.screen,
            (78, 70, 86),
            close_rect,
            max(1, self.u(1)),
            border_radius=self.u(6),
        )
        self.draw_text(
            "C or Esc closes",
            self.g.small_font,
            self.MUTED,
            close_rect.inflate(-self.u(8), 0),
            align="center",
            valign="center",
        )

        subtitle_y = inner.y + title_h + self.u(5)
        self.draw_text(
            f"{player.class_name} · Level {player.level} · XP {player.xp}/{player.next_xp}",
            self.g.small_font,
            self.TEXT,
            pygame.Rect(inner.x, subtitle_y, inner.width, small_h),
        )

        stats_y = subtitle_y + small_h + gap
        stats_h = max(self.u(72), small_h * 2 + self.u(24))
        stats = [
            ("HP", f"{int(player.hp)}/{player.max_hp}"),
            ("Mana", f"{int(player.mana)}/{player.max_mana}"),
            ("Stamina", f"{int(player.stamina)}/{player.max_stamina}"),
            ("Speed", f"{player.speed:.1f}"),
            ("Melee", str(player.melee_damage())),
            ("Armor", str(player.armor())),
            ("Weapon", self.g.weapon_damage_type().title()),
            ("Nova", self.g.nova_damage_type().title()),
        ]
        self.draw_stat_grid(stats, pygame.Rect(inner.x, stats_y, inner.width, stats_h))

        content_y = stats_y + stats_h + gap
        content_h = max(1, inner.bottom - content_y)
        columns = 2 if inner.width >= self.u(420) else 1
        rows = 2 if columns == 2 else 4
        card_gap = gap
        card_w = (inner.width - card_gap * (columns - 1)) // columns
        card_h = (content_h - card_gap * (rows - 1)) // rows

        def card_rect(index: int) -> pygame.Rect:
            col = index % columns
            row = index // columns
            return pygame.Rect(
                inner.x + col * (card_w + card_gap),
                content_y + row * (card_h + card_gap),
                card_w,
                max(1, card_h),
            )

        def draw_card(
            rect: pygame.Rect,
            title: str,
            lines: Sequence[tuple[str, Color]],
            accent: Color | None = None,
        ) -> None:
            accent = accent or self.accent()
            pygame.draw.rect(self.screen, self.PANEL_2, rect, border_radius=self.u(8))
            pygame.draw.rect(
                self.screen,
                accent,
                rect,
                max(1, self.u(1)),
                border_radius=self.u(8),
            )
            card_pad = max(self.u(9), 9)
            self.draw_text(
                title,
                self.g.small_font,
                self.WARNING,
                pygame.Rect(
                    rect.x + card_pad,
                    rect.y + card_pad,
                    rect.width - card_pad * 2,
                    small_h,
                ),
            )
            y = rect.y + card_pad + small_h + self.u(6)
            line_h = max(tiny_h + self.u(3), self.u(15))
            for line, color in lines:
                if y + line_h > rect.bottom - card_pad:
                    break
                self.draw_text(
                    line,
                    self.g.tiny_font,
                    color,
                    pygame.Rect(
                        rect.x + card_pad, y, rect.width - card_pad * 2, line_h
                    ),
                )
                y += line_h

        melee_name, bolt_name, nova_name, dash_name = self.g.skill_names()
        skill_lines = [
            (f"Space {melee_name} · {self.g.melee_stamina_cost()} stamina", self.TEXT),
            (f"F {bolt_name} · {self.g.bolt_mana_cost()} mana", self.TEXT),
            (f"V {nova_name} · {self.g.nova_mana_cost()} mana", self.TEXT),
            (f"Ctrl {dash_name} · {self.g.dash_stamina_cost()} stamina", self.TEXT),
        ]

        weapon = player.equipment.get("weapon")
        armor = player.equipment.get("armor")
        equipment_lines = [
            (
                weapon.label if weapon else "Weapon: Training Sword (+0 dmg)",
                self.item_color(weapon) if weapon else self.MUTED,
            ),
            (
                armor.label if armor else "Armor: Cloth (+0 armor)",
                self.item_color(armor) if armor else self.MUTED,
            ),
            (f"Bolt type: {self.g.bolt_damage_type().title()}", self.MUTED),
        ]

        upgrades = self.g.acquired_skill_upgrades()
        upgrade_lines = (
            [(name, self.TEXT) for name, _description in upgrades[:4]]
            if upgrades
            else [("No skill upgrades yet", self.MUTED)]
        )

        status_lines: list[tuple[str, Color]] = []
        active_statuses = [
            f"{name.title()} {ttl:.1f}s"
            for name, ttl in player.status_effects.items()
            if ttl > 0
        ]
        status_lines.extend((line, self.TEXT) for line in active_statuses[:2])
        for item in (weapon, armor):
            if item is None or item.unidentified:
                continue
            if item.skill_bonus:
                status_lines.append((f"Skill: {item.skill_bonus}", self.WARNING))
            if item.proc_effect:
                status_lines.append((f"Proc: {item.proc_effect}", self.WARNING))
            if item.cursed:
                status_lines.append(("Cursed bargain active", (220, 95, 140)))
        if not status_lines:
            status_lines.append(("No active statuses or procs", self.MUTED))

        draw_card(card_rect(0), "Skills", skill_lines, self.g.skill_color())
        draw_card(card_rect(1), "Equipment", equipment_lines, self.accent())
        draw_card(card_rect(2), "Upgrades", upgrade_lines, self.g.skill_color())
        draw_card(card_rect(3), "Status & Procs", status_lines[:4], self.accent())

    def inventory_layout(self) -> dict[str, pygame.Rect]:
        width, height = self.screen.get_size()
        margin = max(self.u(16), 18)
        box_w = min(max(self.u(620), int(width * 0.78)), width - margin * 2)
        box_h = min(max(self.u(440), int(height * 0.86)), height - margin * 2)
        box = pygame.Rect((width - box_w) // 2, (height - box_h) // 2, box_w, box_h)
        pad = max(self.u(16), 18)
        inner = box.inflate(-pad * 2, -pad * 2)
        gap = max(self.u(8), 8)
        header_h = max(
            self.g.font.get_height()
            + self.g.small_font.get_height()
            + max(self.u(10), 10)
            + max(self.u(22), 22),
            72,
        )
        sort_h = max(self.g.small_font.get_height() + max(self.u(20), 20), 42)
        controls_h = max(
            self.g.tiny_font.get_height() * 3 + 34,
            90,
        )
        header = pygame.Rect(inner.x, inner.y, inner.width, header_h)
        sort = pygame.Rect(inner.x, header.bottom + gap, inner.width, sort_h)
        controls = pygame.Rect(
            inner.x,
            inner.bottom - controls_h,
            inner.width,
            controls_h,
        )
        content_y = sort.bottom + gap
        content_h = max(1, controls.y - gap - content_y)
        content = pygame.Rect(inner.x, content_y, inner.width, content_h)
        column_gap = max(self.u(10), 10)
        details_w = max(self.u(190), min(int(content.width * 0.38), self.u(300)))
        list_w = content.width - column_gap - details_w
        min_list_w = min(self.u(330), max(self.u(240), int(content.width * 0.55)))
        if list_w < min_list_w:
            list_w = min_list_w
            details_w = max(1, content.width - column_gap - list_w)
        list_rect = pygame.Rect(content.x, content.y, list_w, content.height)
        details_rect = pygame.Rect(
            list_rect.right + column_gap,
            content.y,
            max(1, content.right - list_rect.right - column_gap),
            content.height,
        )
        return {
            "box": box,
            "inner": inner,
            "header": header,
            "sort": sort,
            "content": content,
            "list": list_rect,
            "details": details_rect,
            "controls": controls,
        }

    def inventory_row_metrics(self, list_rect: pygame.Rect) -> tuple[int, int, int]:
        row_gap = max(self.u(5), 5)
        row_h = max(self.g.small_font.get_height() * 2 + self.u(18), self.u(56))
        visible_rows = max(1, (list_rect.height + row_gap) // (row_h + row_gap))
        return row_h, row_gap, visible_rows

    def inventory_category_label(self, item: Item) -> str:
        return {
            "weapon": "Weapon",
            "armor": "Armor",
            "potion": "Health",
            "mana_potion": "Mana",
            "identify": "Identify",
        }.get(item.slot, item.slot.replace("_", " ").title())

    def inventory_action_label(self, item: Item) -> str:
        if item.slot in ("weapon", "armor"):
            return "Equip" if not item.unidentified else "Identify"
        if item.slot in ("potion", "mana_potion"):
            return "Drink"
        if item.slot == "identify":
            return "Read"
        return "Use"

    def draw_inventory(self) -> None:
        width, height = self.screen.get_size()
        dim = pygame.Surface((width, height), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 86))
        self.screen.blit(dim, (0, 0))

        layout = self.inventory_layout()
        box = layout["box"]
        header = layout["header"]
        sort_rect = layout["sort"]
        list_rect = layout["list"]
        details_rect = layout["details"]
        controls_rect = layout["controls"]
        self.panel(box, (105, 90, 68), alpha=252)

        row_h, row_gap, visible_rows = self.inventory_row_metrics(list_rect)
        self.g.ensure_inventory_cursor_visible(visible_rows)
        self.draw_inventory_header(header)
        self.draw_inventory_sort_bar(sort_rect)
        self.draw_inventory_list(list_rect, row_h, row_gap, visible_rows)
        self.draw_inventory_details(details_rect)
        self.draw_inventory_controls(controls_rect)

    def draw_inventory_header(self, rect: pygame.Rect) -> None:
        top_pad = max(self.u(10), 10)
        line_gap = max(self.u(10), 10)
        title_h = self.g.font.get_height()
        subtitle_h = self.g.small_font.get_height()
        title_y = rect.y + top_pad
        subtitle_y = title_y + title_h + line_gap
        capacity = f"{len(self.g.player.inventory)}/{MAX_INVENTORY} slots"
        close_text = "I or Esc closes"
        meta_w = min(
            rect.width // 2,
            max(self.u(150), self.g.small_font.size(capacity)[0] + self.u(24)),
        )
        meta_rect = pygame.Rect(
            rect.right - meta_w,
            title_y + max(0, (title_h - self.g.small_font.get_height()) // 2),
            meta_w,
            self.g.small_font.get_height(),
        )
        title_rect = pygame.Rect(
            rect.x,
            title_y,
            max(1, meta_rect.x - rect.x - self.u(12)),
            title_h,
        )
        self.draw_text("Inventory", self.g.font, self.TITLE, title_rect)
        self.draw_text(
            capacity, self.g.small_font, self.WARNING, meta_rect, align="right"
        )
        upgrade_names = self.g.player.skill_upgrades
        subtitle = "Select an item for details, compare, use, or drop."
        if upgrade_names:
            subtitle = f"{len(upgrade_names)} upgrades learned · {subtitle}"
        close_w = min(
            max(self.g.tiny_font.size(close_text)[0] + self.u(8), self.u(112)),
            rect.width // 3,
        )
        close_rect = pygame.Rect(
            rect.right - close_w,
            subtitle_y + max(0, (subtitle_h - self.g.tiny_font.get_height()) // 2),
            close_w,
            self.g.tiny_font.get_height(),
        )
        subtitle_rect = pygame.Rect(
            rect.x,
            subtitle_y,
            max(1, close_rect.x - rect.x - self.u(12)),
            subtitle_h,
        )
        self.draw_text(subtitle, self.g.small_font, self.MUTED, subtitle_rect)
        self.draw_text(
            close_text,
            self.g.tiny_font,
            self.MUTED,
            close_rect,
            align="right",
        )

    def draw_inventory_sort_bar(self, rect: pygame.Rect) -> None:
        pygame.draw.rect(self.screen, self.PANEL_2, rect, border_radius=self.u(8))
        pygame.draw.rect(
            self.screen,
            (62, 55, 66),
            rect,
            max(1, self.u(1)),
            border_radius=self.u(8),
        )
        pad = max(self.u(10), 10)
        label_w = min(max(self.u(42), 42), rect.width // 5)
        self.draw_text(
            "Sort",
            self.g.small_font,
            self.MUTED,
            pygame.Rect(rect.x + pad, rect.y, label_w, rect.height),
            valign="center",
        )
        modes = (("type", "Type"), ("rarity", "Rarity"), ("power", "Power"))
        chip_gap = max(self.u(5), 5)
        x = rect.x + pad + label_w + chip_gap
        hint_w = min(max(self.u(116), 104), max(0, rect.right - x) // 3)
        chip_w = max(1, (rect.right - x - hint_w - chip_gap * 3 - pad) // 3)
        chip_h = rect.height - pad * 2
        for mode, label in modes:
            active = self.g.inventory_sort_mode == mode
            chip = pygame.Rect(x, rect.y + pad, chip_w, chip_h)
            color = self.WARNING if active else (80, 72, 86)
            fill = self.shade(color, -52) if active else (30, 28, 36)
            pygame.draw.rect(self.screen, fill, chip, border_radius=self.u(7))
            pygame.draw.rect(
                self.screen,
                color,
                chip,
                max(1, self.u(1)),
                border_radius=self.u(7),
            )
            self.draw_text(
                label,
                self.g.tiny_font,
                color if active else self.MUTED,
                chip.inflate(-self.u(6), 0),
                align="center",
                valign="center",
            )
            x += chip_w + chip_gap
        hint_rect = pygame.Rect(x, rect.y, max(1, rect.right - x - pad), rect.height)
        self.draw_text(
            "Tab cycles · S re-sorts",
            self.g.tiny_font,
            self.MUTED,
            hint_rect,
            align="right",
            valign="center",
        )

    def draw_inventory_list(
        self, list_rect: pygame.Rect, row_h: int, row_gap: int, visible_rows: int
    ) -> None:
        pygame.draw.rect(self.screen, (14, 13, 18), list_rect, border_radius=self.u(9))
        pygame.draw.rect(
            self.screen,
            (55, 50, 62),
            list_rect,
            max(1, self.u(1)),
            border_radius=self.u(9),
        )
        header_h = max(self.g.small_font.get_height() + self.u(12), self.u(30))
        header_rect = pygame.Rect(list_rect.x, list_rect.y, list_rect.width, header_h)
        self.draw_text(
            "Items",
            self.g.small_font,
            self.WARNING,
            header_rect.inflate(-self.u(12), 0),
            valign="center",
        )
        count_text = f"{len(self.g.player.inventory)} carried"
        self.draw_text(
            count_text,
            self.g.tiny_font,
            self.MUTED,
            header_rect.inflate(-self.u(12), 0),
            align="right",
            valign="center",
        )
        rows_rect = pygame.Rect(
            list_rect.x + self.u(8),
            header_rect.bottom + self.u(4),
            list_rect.width - self.u(16),
            max(1, list_rect.bottom - header_rect.bottom - self.u(12)),
        )
        if not self.g.player.inventory:
            self.draw_text(
                "Empty pack",
                self.g.small_font,
                self.MUTED,
                rows_rect,
                align="center",
                valign="center",
            )
            return
        _, _, rows_available = self.inventory_row_metrics(rows_rect)
        visible_rows = max(1, min(visible_rows, rows_available))
        self.g.ensure_inventory_cursor_visible(visible_rows)
        start = self.g.inventory_scroll
        end = min(len(self.g.player.inventory), start + visible_rows)
        y = rows_rect.y
        row_w = rows_rect.width - (
            self.u(8) if len(self.g.player.inventory) > visible_rows else 0
        )
        for index in range(start, end):
            row = pygame.Rect(rows_rect.x, y, row_w, row_h)
            self.draw_inventory_item_row(
                self.g.player.inventory[index],
                index,
                row,
                index == self.g.inventory_cursor,
            )
            y += row_h + row_gap
        self.draw_inventory_scrollbar(rows_rect, visible_rows)

    def draw_inventory_item_row(
        self, item: Item, index: int, row: pygame.Rect, selected: bool
    ) -> None:
        color = self.item_color(item)
        fill = (38, 34, 45) if selected else self.PANEL_2
        border = self.WARNING if selected else color
        pygame.draw.rect(self.screen, fill, row, border_radius=self.u(7))
        pygame.draw.rect(
            self.screen,
            border,
            row,
            max(1, self.u(2) if selected else self.u(1)),
            border_radius=self.u(7),
        )
        if selected:
            marker = pygame.Rect(
                row.x, row.y + self.u(5), self.u(4), row.height - self.u(10)
            )
            pygame.draw.rect(self.screen, self.WARNING, marker, border_radius=self.u(3))
        slot_size = min(self.u(38), row.height - self.u(14))
        slot_rect = pygame.Rect(
            row.x + self.u(9),
            row.y + (row.height - slot_size) // 2,
            slot_size,
            slot_size,
        )
        pygame.draw.rect(self.screen, (13, 12, 17), slot_rect, border_radius=self.u(5))
        pygame.draw.rect(
            self.screen, color, slot_rect, max(1, self.u(1)), border_radius=self.u(5)
        )
        icon = self.g.rarity_icon(item.visible_rarity)
        shortcut = str(index + 1) if index < 9 else f"{index + 1}"
        self.draw_text(
            f"{shortcut}{icon}",
            self.g.tiny_font,
            color,
            slot_rect.inflate(-self.u(2), 0),
            align="center",
            valign="center",
        )
        tag = self.inventory_category_label(item)
        tag_w = min(
            max(self.g.tiny_font.size(tag)[0] + self.u(16), self.u(62)),
            max(self.u(58), row.width // 4),
        )
        tag_rect = pygame.Rect(
            row.right - tag_w - self.u(8),
            row.y + self.u(8),
            tag_w,
            self.g.tiny_font.get_height() + self.u(8),
        )
        pygame.draw.rect(self.screen, (18, 17, 23), tag_rect, border_radius=self.u(5))
        self.draw_text(
            tag,
            self.g.tiny_font,
            self.MUTED,
            tag_rect.inflate(-self.u(6), 0),
            align="center",
            valign="center",
        )
        text_x = slot_rect.right + self.u(10)
        text_w = max(1, tag_rect.x - text_x - self.u(8))
        name_rect = pygame.Rect(
            text_x, row.y + self.u(7), text_w, self.g.small_font.get_height()
        )
        detail_rect = pygame.Rect(
            text_x,
            name_rect.bottom + self.u(3),
            max(1, row.right - text_x - self.u(10)),
            self.g.tiny_font.get_height(),
        )
        name = f"{item.visible_rarity} · {item.display_name}{self.compare_hint(item)}"
        self.draw_text(name, self.g.small_font, color, name_rect)
        self.draw_text(
            self.g.item_decision_summary(item),
            self.g.tiny_font,
            self.MUTED,
            detail_rect,
        )

    def draw_inventory_scrollbar(
        self, rows_rect: pygame.Rect, visible_rows: int
    ) -> None:
        count = len(self.g.player.inventory)
        if count <= visible_rows:
            return
        track = pygame.Rect(
            rows_rect.right - self.u(5), rows_rect.y, self.u(4), rows_rect.height
        )
        pygame.draw.rect(self.screen, (34, 31, 39), track, border_radius=self.u(3))
        thumb_h = max(self.u(18), int(track.height * visible_rows / count))
        max_scroll = max(1, count - visible_rows)
        travel = max(1, track.height - thumb_h)
        thumb_y = track.y + int(travel * self.g.inventory_scroll / max_scroll)
        thumb = pygame.Rect(track.x, thumb_y, track.width, thumb_h)
        pygame.draw.rect(self.screen, self.WARNING, thumb, border_radius=self.u(3))

    def draw_inventory_details(self, rect: pygame.Rect) -> None:
        gap = max(self.u(8), 8)
        equipment_h = min(
            max(self.u(116), rect.height // 3),
            max(self.u(92), rect.height - self.u(128)),
        )
        item_h = max(self.u(110), rect.height - equipment_h - gap)
        item_rect = pygame.Rect(rect.x, rect.y, rect.width, item_h)
        equipment_rect = pygame.Rect(
            rect.x,
            item_rect.bottom + gap,
            rect.width,
            max(1, rect.bottom - item_rect.bottom - gap),
        )
        self.draw_inventory_selected_card(item_rect)
        self.draw_inventory_equipment(equipment_rect)

    def draw_inventory_selected_card(self, rect: pygame.Rect) -> None:
        pygame.draw.rect(self.screen, self.PANEL_2, rect, border_radius=self.u(9))
        pygame.draw.rect(
            self.screen, (58, 52, 66), rect, max(1, self.u(1)), border_radius=self.u(9)
        )
        pad = max(self.u(10), 10)
        title_rect = pygame.Rect(
            rect.x + pad,
            rect.y + pad,
            rect.width - pad * 2,
            self.g.small_font.get_height(),
        )
        self.draw_text("Selected", self.g.small_font, self.WARNING, title_rect)
        if not self.g.player.inventory:
            self.draw_text(
                "No item selected",
                self.g.small_font,
                self.MUTED,
                rect.inflate(-pad * 2, -pad * 2),
                align="center",
                valign="center",
            )
            return
        self.g.clamp_inventory_selection()
        item = self.g.player.inventory[self.g.inventory_cursor]
        color = self.item_color(item)
        y = title_rect.bottom + self.u(8)
        self.draw_text(
            item.display_name,
            self.g.small_font,
            color,
            pygame.Rect(
                rect.x + pad, y, rect.width - pad * 2, self.g.small_font.get_height()
            ),
        )
        y += self.g.small_font.get_height() + self.u(5)
        meta = f"{item.visible_rarity} {self.inventory_category_label(item)} · {self.inventory_action_label(item)}"
        self.draw_text(
            meta,
            self.g.tiny_font,
            self.MUTED,
            pygame.Rect(
                rect.x + pad, y, rect.width - pad * 2, self.g.tiny_font.get_height()
            ),
        )
        y += self.g.tiny_font.get_height() + self.u(8)
        y = self.draw_wrapped_text(
            self.g.item_decision_summary(item),
            self.g.tiny_font,
            self.TEXT,
            pygame.Rect(rect.x + pad, y, rect.width - pad * 2, rect.bottom - y - pad),
            max(self.g.tiny_font.get_height() + self.u(3), self.u(16)),
        ) + self.u(6)
        extra_lines: list[str] = []
        if item.unidentified and item.slot in ("weapon", "armor"):
            extra_lines.append("Stats hidden until identified or equipped.")
        elif item.affixes:
            extra_lines.append(f"Affixes: {', '.join(item.affixes)}")
        if item.unique_effect:
            extra_lines.append(f"Effect: {item.unique_effect}")
        if item.cursed:
            extra_lines.append("Cursed bargain: powerful, but costly.")
        extra_lines.append("Enter/E use · Del drop")
        for line in extra_lines:
            if y + self.g.tiny_font.get_height() > rect.bottom - pad:
                break
            self.draw_text(
                line,
                self.g.tiny_font,
                self.MUTED,
                pygame.Rect(
                    rect.x + pad, y, rect.width - pad * 2, self.g.tiny_font.get_height()
                ),
            )
            y += self.g.tiny_font.get_height() + self.u(3)

    def draw_inventory_equipment(self, rect: pygame.Rect) -> None:
        pygame.draw.rect(self.screen, self.PANEL_2, rect, border_radius=self.u(9))
        pygame.draw.rect(
            self.screen, (58, 52, 66), rect, max(1, self.u(1)), border_radius=self.u(9)
        )
        pad = max(self.u(10), 10)
        title_h = self.g.small_font.get_height()
        self.draw_text(
            "Equipped",
            self.g.small_font,
            self.WARNING,
            pygame.Rect(rect.x + pad, rect.y + pad, rect.width - pad * 2, title_h),
        )
        card_gap = max(self.u(6), 6)
        card_h = max(self.g.tiny_font.get_height() * 2 + self.u(12), self.u(42))
        y = rect.y + pad + title_h + self.u(8)
        available_h = rect.bottom - y - pad
        if available_h < card_h * 2 + card_gap:
            card_h = max(
                self.g.tiny_font.get_height() + self.u(10),
                (available_h - card_gap) // 2,
            )
        weapon = self.g.player.equipment["weapon"]
        armor = self.g.player.equipment["armor"]
        self.draw_equipment_card(
            pygame.Rect(rect.x + pad, y, rect.width - pad * 2, card_h),
            "Weapon",
            weapon.label if weapon else "Training Sword (+0 dmg)",
            self.item_color(weapon) if weapon else self.MUTED,
        )
        y += card_h + card_gap
        self.draw_equipment_card(
            pygame.Rect(rect.x + pad, y, rect.width - pad * 2, card_h),
            "Armor",
            armor.label if armor else "Cloth (+0 armor)",
            self.item_color(armor) if armor else self.MUTED,
        )

    def draw_equipment_card(
        self, rect: pygame.Rect, label: str, value: str, color: Color
    ) -> None:
        pygame.draw.rect(self.screen, (16, 15, 20), rect, border_radius=self.u(6))
        pygame.draw.rect(
            self.screen, color, rect, max(1, self.u(1)), border_radius=self.u(6)
        )
        self.draw_text(
            label,
            self.g.tiny_font,
            self.MUTED,
            pygame.Rect(
                rect.x + self.u(8),
                rect.y + self.u(4),
                rect.width - self.u(16),
                self.g.tiny_font.get_height(),
            ),
        )
        self.draw_text(
            value,
            self.g.tiny_font,
            color,
            pygame.Rect(
                rect.x + self.u(8),
                rect.y + self.u(4) + self.g.tiny_font.get_height(),
                rect.width - self.u(16),
                self.g.tiny_font.get_height(),
            ),
        )

    def draw_inventory_controls(self, rect: pygame.Rect) -> None:
        pygame.draw.rect(self.screen, (16, 15, 20), rect, border_radius=self.u(9))
        pygame.draw.rect(
            self.screen, (58, 52, 66), rect, max(1, self.u(1)), border_radius=self.u(9)
        )
        entries = [
            "Up/Down select",
            "Enter/E use",
            "Del drop",
            "Tab sort mode",
            "S re-sort",
            "Shift+1-9 drop",
            "1-9 quick use",
            "I/Esc close",
        ]
        pad = 7
        gap = 5
        font = self.g.tiny_font
        pill_h = max(font.get_height() + 8, 22)
        x = rect.x + pad
        y = rect.y + pad
        for entry in entries:
            pill_w = min(max(font.size(entry)[0] + 16, 68), rect.width - pad * 2)
            if x + pill_w > rect.right - pad:
                x = rect.x + pad
                y += pill_h + gap
            if y + pill_h > rect.bottom - pad:
                break
            pill = pygame.Rect(x, y, pill_w, pill_h)
            pygame.draw.rect(self.screen, (27, 25, 33), pill, border_radius=self.u(6))
            pygame.draw.rect(
                self.screen,
                (78, 70, 86),
                pill,
                max(1, self.u(1)),
                border_radius=self.u(6),
            )
            self.draw_text(
                entry,
                font,
                self.MUTED,
                pill.inflate(-6, 0),
                align="center",
                valign="center",
            )
            x += pill_w + gap

    def compare_hint(self, item: Item) -> str:
        if item.unidentified or item.slot not in ("weapon", "armor"):
            return ""
        equipped = self.g.player.equipment.get(item.slot)
        current = 0
        incoming = item.power if item.slot == "weapon" else item.defense
        if equipped:
            current = equipped.power if item.slot == "weapon" else equipped.defense
        delta = incoming - current
        if delta == 0:
            return ""
        stat = "dmg" if item.slot == "weapon" else "arm"
        sign = "+" if delta > 0 else ""
        return f" ({sign}{delta} {stat})"

    def item_color(self, item: Item) -> Color:
        return self.g.rarity_color(item.visible_rarity)

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
