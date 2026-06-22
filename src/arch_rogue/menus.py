from __future__ import annotations

from typing import Any, Sequence

import pygame

from . import __version__
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

    def panel(
        self, rect: pygame.Rect, accent: Color | None = None, alpha: int = 245
    ) -> None:
        accent = accent or self.accent()
        shadow = rect.move(max(2, self.u(3)), max(3, self.u(4)))
        pygame.draw.rect(self.screen, (3, 3, 6), shadow, border_radius=self.u(8))
        if alpha < 255:
            surface = pygame.Surface(rect.size, pygame.SRCALPHA)
            surface.fill((*self.PANEL, alpha))
            self.screen.blit(surface, rect)
        else:
            pygame.draw.rect(self.screen, self.PANEL, rect, border_radius=self.u(8))
        pygame.draw.rect(
            self.screen, accent, rect, max(1, self.u(2)), border_radius=self.u(8)
        )
        pygame.draw.line(
            self.screen,
            self.shade(accent, 36),
            (rect.x + self.u(18), rect.y + self.u(18)),
            (rect.right - self.u(18), rect.y + self.u(18)),
            max(1, self.u(1)),
        )

    def menu_frame(
        self, title: str, subtitle: str = ""
    ) -> tuple[pygame.Rect, pygame.Rect]:
        width, height = self.screen.get_size()
        self.screen.fill(self.BG)
        title_y = max(38, int(height * 0.13))
        self.draw_text(
            title,
            self.g.big_font,
            self.TITLE,
            pygame.Rect(
                32,
                title_y - self.g.big_font.get_height() // 2,
                width - 64,
                self.g.big_font.get_height(),
            ),
            align="center",
            valign="center",
        )
        if subtitle:
            self.draw_text(
                subtitle,
                self.g.small_font,
                self.MUTED,
                pygame.Rect(
                    40, title_y + self.u(44), width - 80, self.g.small_font.get_height()
                ),
                align="center",
            )

        top = title_y + self.u(78)
        footer_space = max(44, self.u(42))
        rect = pygame.Rect(
            max(28, width // 2 - min(width - 64, self.u(860)) // 2),
            top,
            min(width - 64, self.u(860)),
            max(220, height - top - footer_space - 20),
        )
        self.panel(rect)
        content = rect.inflate(-self.u(48), -self.u(46))
        content.y += self.u(18)
        content.h -= self.u(8)
        return rect, content

    def draw_footer(self, panel: pygame.Rect, text: str) -> None:
        width, height = self.screen.get_size()
        rect = pygame.Rect(
            32, min(height - 32, panel.bottom + self.u(14)), width - 64, 28
        )
        self.draw_text(text, self.g.small_font, self.MUTED, rect, align="center")

    def draw_menu_rows(self, rows: Sequence[MenuRow], rect: pygame.Rect) -> None:
        key_w = min(max(self.u(132), 112), max(118, rect.width // 3))
        row_h = max(self.g.font.get_height() + self.u(13), self.u(42))
        gap = max(5, self.u(5))
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
            "10-depth roguelike ARPG run · loot, shrines, secrets, and the gate tyrant",
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
            "Choose an archetype, explore ten depths, build around what the dungeon gives you, and break the gate tyrant's seal.",
            self.g.small_font,
            self.MUTED,
            note_rect,
        )
        self.draw_footer(panel, "Esc quits · Backspace returns from submenus")

    def draw_options_menu(self) -> None:
        panel, content = self.menu_frame("Options", "Settings are saved automatically")
        rows: list[MenuRow] = [
            ("A", "Audio cues", "On" if self.g.audio_enabled else "Off"),
            ("M", "Music", "On" if self.g.music_enabled else "Off"),
            ("F", "Fullscreen", "On" if self.g.fullscreen else "Off"),
            ("+ / -", "UI scale", f"{self.g.ui_scale}x"),
            ("Enter / O / Backspace", "Return to title", ""),
        ]
        self.draw_menu_rows(rows, content)
        note_rect = pygame.Rect(
            content.x, content.bottom - self.u(60), content.width, self.u(48)
        )
        self.draw_wrapped_text(
            "Audio falls back silently if no mixer device is available. Options persist to ~/.arch_rogue_options.json.",
            self.g.small_font,
            self.MUTED,
            note_rect,
        )
        self.draw_footer(panel, "Use the highlighted keys to change settings")

    def draw_about_screen(self) -> None:
        panel, content = self.menu_frame(
            "About / Onboarding", "Arch Rogue public release"
        )
        paragraphs = [
            f"Arch Rogue {__version__} is a Rogue-inspired isometric action RPG built around compact, replayable dungeon runs.",
            "Goal: descend through ten depths, survive escalating encounters, defeat the final-depth gate tyrant, then use the stairs to complete the run.",
            "Combat: hold left mouse to move and aim. Space uses your class melee skill, F casts your bolt skill, C uses your nova skill, and Shift uses your movement skill.",
            "Loot and discovery: press E for pickups, shrines, secrets, and stairs. Use I for inventory, 1-9 to equip/use, and Q for your first potion.",
            "Credits: design, code, procedural art, and procedural audio by the Arch Rogue project.",
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
        overlay.fill((0, 0, 0, 90))
        self.screen.blit(overlay, (0, 0))
        box_w = min(width - 48, self.u(760))
        box_h = min(height - 72, self.u(430))
        box = pygame.Rect(24, 36, box_w, box_h)
        self.panel(box, alpha=236)
        title_rect = pygame.Rect(
            box.x + self.u(24),
            box.y + self.u(24),
            box.width - self.u(48),
            self.g.font.get_height(),
        )
        self.draw_text("Run Guide", self.g.font, self.accent(), title_rect)
        lines = [
            "Goal: defeat the gate tyrant in the final room, then press E on the stairs.",
            "Movement: hold left mouse to move and aim. Arrow keys can aim without moving.",
            "Class skills: Warden bashes, Rogue crits, Arcanist arcs, Acolyte drains, Ranger controls.",
            "Resources: stamina powers melee and movement skills; mana powers bolt and nova skills.",
            "Inventory: E picks up and interacts; I opens inventory; 1-9 equips/uses; Q drinks a potion.",
            "Discovery: unidentified gear needs scrolls, Insight Shrines, or equipping to reveal.",
            "Hazards: traps are single-use but dangerous; shrines and secrets can swing a run.",
        ]
        y = title_rect.bottom + self.u(16)
        for line in lines:
            y = self.draw_wrapped_text(
                line,
                self.g.small_font,
                self.TEXT,
                pygame.Rect(
                    box.x + self.u(24),
                    y,
                    box.width - self.u(48),
                    box.bottom - y - self.u(18),
                ),
                max(self.g.small_font.get_height() + 3, self.u(18)),
            ) + self.u(7)
            if y >= box.bottom:
                break
        self.draw_text(
            "H / ? closes",
            self.g.small_font,
            self.MUTED,
            pygame.Rect(
                box.x + self.u(24),
                box.bottom - self.u(28),
                box.width - self.u(48),
                self.u(20),
            ),
            align="right",
        )

    def draw_archetype_select(self) -> None:
        width, height = self.screen.get_size()
        self.screen.fill(self.BG)
        selected = self.g.selected_archetype
        accent = self.accent()

        title_font = self.g.big_font if height >= 650 else pygame.font.Font(None, 42)
        subtitle_font = (
            self.g.small_font if height >= 650 else pygame.font.Font(None, 24)
        )
        title_h = title_font.get_height()
        top_margin = 22
        self.draw_text(
            "Choose Your Archetype",
            title_font,
            self.TITLE,
            pygame.Rect(28, top_margin, width - 56, title_h),
            align="center",
        )
        subtitle_y = top_margin + title_h + 6
        self.draw_text(
            "Arrow keys select · Enter begins · Backspace returns",
            subtitle_font,
            self.MUTED,
            pygame.Rect(32, subtitle_y, width - 64, subtitle_font.get_height()),
            align="center",
        )

        footer_h = 34
        content_top = subtitle_y + subtitle_font.get_height() + 18
        content = pygame.Rect(
            24, content_top, width - 48, height - content_top - footer_h - 14
        )
        if content.height < 230:
            content.y = max(86, content.y - (230 - content.height))
            content.height = min(230, height - content.y - footer_h - 10)

        compact = width < 560
        gap = 16
        list_w = (
            min(260, max(205, int(content.width * 0.36)))
            if not compact
            else content.width
        )
        if compact:
            list_rect = pygame.Rect(
                content.x, content.y, content.width, min(210, content.height // 2)
            )
            preview_rect = pygame.Rect(
                content.x,
                list_rect.bottom + gap,
                content.width,
                content.bottom - list_rect.bottom - gap,
            )
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
        self.draw_archetype_list(list_rect, selected)
        self.draw_archetype_preview(preview_rect, selected)

        self.draw_text(
            f"Press 1-{min(len(self.archetypes), 9)} to jump directly to a class",
            self.g.small_font,
            self.WARNING,
            pygame.Rect(32, height - footer_h, width - 64, footer_h - 4),
            align="center",
            valign="center",
        )

    def draw_archetype_list(self, rect: pygame.Rect, selected: Archetype) -> None:
        compact_fonts = rect.height < 390
        heading_font = pygame.font.Font(None, 30) if compact_fonts else self.g.font
        name_font_large = pygame.font.Font(None, 28) if compact_fonts else self.g.font
        row_font = pygame.font.Font(None, 23) if compact_fonts else self.g.small_font
        inner = rect.inflate(-18, -18)
        self.draw_text(
            "Classes",
            heading_font,
            self.TITLE,
            pygame.Rect(inner.x, inner.y, inner.width, heading_font.get_height()),
        )
        list_top = inner.y + heading_font.get_height() + 10
        gap = 6
        minimum_row_h = max(row_font.get_height() + 11, 34)
        row_h = max(
            minimum_row_h,
            min(
                58,
                (inner.bottom - list_top - gap * (len(self.archetypes) - 1))
                // len(self.archetypes),
            ),
        )
        y = list_top
        for index, archetype in enumerate(self.archetypes):
            row = pygame.Rect(inner.x, y, inner.width, row_h)
            is_selected = archetype == selected
            fill = (34, 32, 43) if is_selected else self.PANEL_2
            border = self.accent() if is_selected else (58, 52, 62)
            pygame.draw.rect(self.screen, fill, row, border_radius=8)
            pygame.draw.rect(
                self.screen, border, row, max(1, self.u(1)), border_radius=8
            )
            badge = pygame.Rect(row.x + 8, row.y + 7, min(42, row_h - 10), row_h - 14)
            pygame.draw.rect(self.screen, (38, 34, 45), badge, border_radius=6)
            pygame.draw.rect(
                self.screen, border, badge, max(1, self.u(1)), border_radius=6
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
                badge.right + 10,
                row.y + 4,
                row.width - badge.width - 20,
                row_h // 2,
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
                badge.right + 10,
                row.centery,
                row.width - badge.width - 20,
                row_h // 2 - 3,
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
        compact_fonts = rect.height < 390
        name_font = pygame.font.Font(None, 32) if compact_fonts else self.g.font
        detail_font = pygame.font.Font(None, 23) if compact_fonts else self.g.small_font
        inner = rect.inflate(-24, -22)
        name_h = name_font.get_height()
        self.draw_text(
            archetype.name,
            name_font,
            self.TITLE,
            pygame.Rect(inner.x, inner.y, inner.width, name_h),
            align="center",
        )
        skill_names = self.skill_names_for(archetype.name)
        self.draw_text(
            " · ".join(skill_names),
            detail_font,
            self.accent(),
            pygame.Rect(
                inner.x,
                inner.y + name_h + 4,
                inner.width,
                detail_font.get_height(),
            ),
            align="center",
        )

        sprite = self.g.sprites.player_sprites.get(
            archetype.name, self.g.sprites.player
        )
        sprite_max_h = max(68, int(inner.height * (0.34 if compact_fonts else 0.38)))
        sprite_max_w = max(68, int(inner.width * 0.42))
        scale = min(
            sprite_max_w / sprite.get_width(), sprite_max_h / sprite.get_height()
        )
        scale = max(1.0, min(2.25, scale))
        preview = pygame.transform.scale(
            sprite,
            (
                max(1, int(sprite.get_width() * scale)),
                max(1, int(sprite.get_height() * scale)),
            ),
        )
        sprite_y = inner.y + name_h + detail_font.get_height() + 14
        pedestal = pygame.Rect(0, 0, preview.get_width() + 56, 26)
        pedestal.center = (inner.centerx, sprite_y + preview.get_height() + 8)
        glow = pygame.Surface((pedestal.width, pedestal.height), pygame.SRCALPHA)
        pygame.draw.ellipse(glow, (*self.accent(), 62), glow.get_rect())
        self.screen.blit(glow, pedestal)
        self.screen.blit(
            preview, preview.get_rect(midbottom=(inner.centerx, pedestal.centery + 2))
        )

        text_top = pedestal.bottom + 10
        stat_h = max(46, detail_font.get_height() * 2 + 8)
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
            max(detail_font.get_height() + 3, 18),
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
        stat_font = (
            pygame.font.Font(None, 22) if rect.height < 66 else self.g.small_font
        )
        columns = 4 if rect.width >= 360 else 3
        gap = 6
        cell_w = (rect.width - gap * (columns - 1)) // columns
        cell_h = max(stat_font.get_height() + 4, (rect.height - gap) // 2)
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
            pygame.draw.rect(self.screen, self.PANEL_2, cell, border_radius=5)
            pygame.draw.rect(self.screen, (58, 52, 62), cell, 1, border_radius=5)
            self.draw_text(
                label,
                stat_font,
                self.MUTED,
                pygame.Rect(cell.x + 7, cell.y, cell.width // 2, cell.height),
                valign="center",
            )
            self.draw_text(
                value,
                stat_font,
                self.WARNING,
                pygame.Rect(cell.centerx, cell.y, cell.width // 2 - 7, cell.height),
                align="right",
                valign="center",
            )

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

    def draw_inventory(self) -> None:
        width, height = self.screen.get_size()
        box_w = min(max(360, self.u(390)), width - 48)
        box_h = min(max(320, self.u(320)), height - 80)
        box = pygame.Rect(width - box_w - 24, 32, box_w, box_h)
        self.panel(box, (105, 90, 68), alpha=246)
        inner = box.inflate(-self.u(34), -self.u(30))
        self.draw_text(
            "Inventory",
            self.g.font,
            self.TITLE,
            pygame.Rect(inner.x, inner.y, inner.width, self.g.font.get_height()),
        )
        self.draw_text(
            "1-9 equip/use",
            self.g.small_font,
            self.MUTED,
            pygame.Rect(inner.x, inner.y, inner.width, self.g.small_font.get_height()),
            align="right",
        )
        y = inner.y + self.u(42)
        row_h = max(self.g.small_font.get_height() + self.u(6), self.u(25))
        if not self.g.player.inventory:
            self.draw_text(
                "Empty",
                self.g.small_font,
                self.MUTED,
                pygame.Rect(inner.x, y, inner.width, row_h),
            )
        for index, item in enumerate(self.g.player.inventory):
            if y + row_h > inner.bottom - self.u(66):
                break
            color = self.item_color(item)
            row = pygame.Rect(inner.x, y, inner.width, row_h)
            pygame.draw.rect(self.screen, self.PANEL_2, row, border_radius=self.u(3))
            slot_rect = pygame.Rect(row.x + self.u(5), row.y, self.u(28), row.h)
            self.draw_text(
                str(index + 1),
                self.g.small_font,
                color,
                slot_rect,
                align="center",
                valign="center",
            )
            self.draw_text(
                f"[{item.visible_rarity}] {item.label}",
                self.g.small_font,
                color,
                pygame.Rect(row.x + self.u(38), row.y, row.width - self.u(43), row.h),
                valign="center",
            )
            y += row_h + self.u(3)
        equipment_y = inner.bottom - self.u(58)
        self.draw_text(
            "Equipped",
            self.g.small_font,
            self.WARNING,
            pygame.Rect(inner.x, equipment_y, inner.width, row_h),
        )
        weapon = (
            self.g.player.equipment["weapon"].label
            if self.g.player.equipment["weapon"]
            else "Training Sword (+0 dmg)"
        )
        armor = (
            self.g.player.equipment["armor"].label
            if self.g.player.equipment["armor"]
            else "Cloth (+0 armor)"
        )
        self.draw_text(
            f"Weapon: {weapon}",
            self.g.small_font,
            self.TEXT,
            pygame.Rect(inner.x, equipment_y + row_h, inner.width, row_h),
        )
        self.draw_text(
            f"Armor: {armor}",
            self.g.small_font,
            self.TEXT,
            pygame.Rect(inner.x, equipment_y + row_h * 2, inner.width, row_h),
        )

    def item_color(self, item: Item) -> Color:
        return {
            "Common": (215, 210, 190),
            "Magic": (115, 175, 255),
            "Rare": (245, 215, 90),
            "Unique": (240, 145, 65),
            "Unidentified": (170, 170, 185),
        }.get(item.visible_rarity, (220, 220, 220))

    def draw_state_overlay(self) -> None:
        width, height = self.screen.get_size()
        overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 172))
        self.screen.blit(overlay, (0, 0))
        victory = self.g.state == "victory"
        color = (235, 205, 120) if victory else (225, 75, 65)
        title = "Dungeon Cleared" if victory else "You Died"
        subtitle = (
            f"You survived all {self.dungeon_depth} depths and broke the gate. Press R to choose a new run."
            if victory
            else f"The dungeon claims another {self.g.player.class_name}. Press R to choose again."
        )
        panel_w = min(width - 64, self.u(820))
        panel_h = min(height - 80, self.u(390))
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
