# pyright: reportAttributeAccessIssue=false, reportUnusedImport=false
from __future__ import annotations

from typing import Any, Sequence

import pygame

from .. import __version__
from ..constants import MAX_INVENTORY
from ..models import Archetype, Color, Item

MenuRow = tuple[str, str, str]


class MenuCharacterMixin:
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
        pygame.draw.rect(self.screen, self.PANEL_INK, header_rect)
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
            if is_selected:
                # Selected: gold-tinted plate with a soft inner glow.
                fill = self.shade(row_accent, -100)
                pygame.draw.rect(self.screen, fill, row, border_radius=self.u(7))
                glow = pygame.Surface(row.size, pygame.SRCALPHA)
                pygame.draw.rect(
                    glow,
                    (*row_accent, 36),
                    glow.get_rect(),
                    border_radius=self.u(7),
                )
                self.screen.blit(glow, row)
            else:
                pygame.draw.rect(
                    self.screen, self.PANEL_INK, row, border_radius=self.u(7)
                )
            border = row_accent if is_selected else self.IRON
            radius = self.u(7)
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
                pygame.draw.rect(
                    self.screen,
                    self.shade(row_accent, 40),
                    strip,
                    border_radius=self.u(3),
                )
            # Sigil badge — iron plate with the class number etched in gold.
            badge_size = min(self.u(34), row_h - self.u(10))
            badge = pygame.Rect(
                row.x + self.u(10),
                row.y + (row_h - badge_size) // 2,
                badge_size,
                badge_size,
            )
            pygame.draw.rect(
                self.screen, self.IRON_DARK, badge, border_radius=self.u(5)
            )
            pygame.draw.rect(
                self.screen,
                self.IRON,
                badge.inflate(-self.u(2), -self.u(2)),
                border_radius=self.u(4),
            )
            pygame.draw.rect(
                self.screen, border, badge, max(1, self.u(1)), border_radius=self.u(5)
            )
            self.draw_text(
                str(index + 1),
                row_font,
                self.TITLE if is_selected else self.IRON_LIGHT,
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
        # Parchment name plaque.
        plaque = pygame.Surface(name_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(
            plaque,
            (214, 196, 150, 24),
            plaque.get_rect(),
            border_radius=self.u(6),
        )
        pygame.draw.rect(
            plaque,
            (*accent, 90),
            plaque.get_rect(),
            max(1, self.u(1)),
            border_radius=self.u(6),
        )
        self.screen.blit(plaque, name_rect)
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
        # Ornamental divider — thin line with a center diamond.
        pygame.draw.line(
            self.screen,
            self.shade(accent, -16),
            (inner.x + 8, divider_y),
            (inner.right - 8, divider_y),
            max(1, self.u(1)),
        )
        cx = inner.centerx
        dr = self.u(3)
        pygame.draw.polygon(
            self.screen,
            accent,
            [
                (cx, divider_y - dr),
                (cx + dr, divider_y),
                (cx, divider_y + dr),
                (cx - dr, divider_y),
            ],
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
        # Pedestal glow — a soft elliptical halo in the class accent.
        glow = pygame.Surface((pedestal.width, pedestal.height * 2), pygame.SRCALPHA)
        for i in range(3):
            alpha = 60 - i * 16
            pygame.draw.ellipse(
                glow,
                (*accent, alpha),
                glow.get_rect().inflate(-i * self.u(6), -i * self.u(4)),
            )
        self.screen.blit(glow, glow.get_rect(center=pedestal.center))
        # Pedestal base — a thin stone slab.
        pygame.draw.ellipse(self.screen, self.STONE_SHADOW, pedestal)
        pygame.draw.ellipse(
            self.screen,
            self.STONE_LIGHT,
            pedestal,
            max(1, self.u(1)),
        )
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
            # Recessed stat cell with a faint top highlight.
            pygame.draw.rect(self.screen, self.PANEL_INK, cell, border_radius=self.u(5))
            pygame.draw.rect(
                self.screen,
                self.STONE_LIGHT,
                cell,
                max(1, self.u(1)),
                border_radius=self.u(5),
            )
            pygame.draw.line(
                self.screen,
                self.IRON,
                (cell.x + self.u(4), cell.y + self.u(1)),
                (cell.right - self.u(4), cell.y + self.u(1)),
                max(1, self.u(1)),
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
            max(
                self.u(150),
                self.g.small_font.size("C/Esc closes · Tab switches tabs")[0]
                + self.u(20),
            ),
            inner.width // 2,
        )
        self.draw_text(
            "Character",
            self.g.font,
            self.accent(),
            pygame.Rect(inner.x, inner.y, inner.width - close_w - gap, title_h),
        )
        close_rect = pygame.Rect(inner.right - close_w, inner.y, close_w, title_h)
        pygame.draw.rect(
            self.screen, self.PANEL_INK, close_rect, border_radius=self.u(6)
        )
        pygame.draw.rect(
            self.screen,
            self.IRON,
            close_rect,
            max(1, self.u(1)),
            border_radius=self.u(6),
        )
        self.draw_text(
            "C/Esc closes · Tab switches tabs",
            self.g.small_font,
            self.MUTED,
            close_rect.inflate(-self.u(8), 0),
            align="center",
            valign="center",
        )

        subtitle_y = inner.y + title_h + self.u(5)
        # Milestone 3.3: surface unspent skill points in the subtitle so the
        # player knows to open the skill tree tab and spend them.
        skill_points = self.g.player.skill_points
        point_text = (
            f" · {skill_points} Skill Point{'s' if skill_points != 1 else ''}"
            if skill_points > 0
            else ""
        )
        subtitle = (
            f"{player.class_name} · Level {player.level} · "
            f"XP {player.xp}/{player.next_xp}{point_text}"
        )
        subtitle_color = self.WARNING if skill_points > 0 else self.TEXT
        self.draw_text(
            subtitle,
            self.g.small_font,
            subtitle_color,
            pygame.Rect(inner.x, subtitle_y, inner.width, small_h),
        )

        # Tab strip — Overview and Skill Tree. Tab/Left/Right switch while the
        # menu is open. The active tab is highlighted; the inactive one dims.
        tab_y = subtitle_y + small_h + self.u(4)
        tab_h = max(self.u(22), small_h + self.u(6))
        tab_gap = self.u(6)
        tab_w = (inner.width - tab_gap) // 2
        overview_tab = pygame.Rect(inner.x, tab_y, tab_w, tab_h)
        tree_tab = pygame.Rect(inner.x + tab_w + tab_gap, tab_y, tab_w, tab_h)
        active_tab = self.g.character_menu_tab
        self._draw_character_tab(overview_tab, "Overview (1)", active_tab == "overview")
        self._draw_character_tab(tree_tab, "Skill Tree (2)", active_tab == "skill_tree")

        stats_y = tab_y + tab_h + gap
        content_top = stats_y
        content_bottom = inner.bottom

        if active_tab == "skill_tree":
            self._draw_character_skill_tree(
                pygame.Rect(
                    inner.x, content_top, inner.width, content_bottom - content_top
                )
            )
            return

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
            pygame.draw.rect(self.screen, self.PANEL_INK, rect, border_radius=self.u(8))
            # Soft accent-tinted wash to distinguish cards.
            wash = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(
                wash,
                (*accent, 18),
                wash.get_rect(),
                border_radius=self.u(8),
            )
            self.screen.blit(wash, rect)
            pygame.draw.rect(
                self.screen,
                accent,
                rect,
                max(1, self.u(1)),
                border_radius=self.u(8),
            )
            # Top accent strip — a thin gold band on the card header.
            strip = pygame.Rect(
                rect.x + self.u(8),
                rect.y + self.u(4),
                rect.width - self.u(16),
                self.u(2),
            )
            pygame.draw.rect(
                self.screen, self.shade(accent, 30), strip, border_radius=self.u(1)
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

    def _draw_character_tab(self, rect: pygame.Rect, label: str, active: bool) -> None:
        accent = self.g.skill_color() if active else self.IRON
        fill = self.PANEL_2 if active else self.PANEL_INK
        pygame.draw.rect(self.screen, fill, rect, border_radius=self.u(6))
        pygame.draw.rect(
            self.screen,
            accent,
            rect,
            max(1, self.u(1)),
            border_radius=self.u(6),
        )
        if active:
            strip = pygame.Rect(
                rect.x + self.u(6),
                rect.bottom - self.u(3),
                rect.width - self.u(12),
                self.u(2),
            )
            pygame.draw.rect(
                self.screen, self.shade(accent, 30), strip, border_radius=self.u(1)
            )
        self.draw_text(
            label,
            self.g.small_font,
            self.TEXT if active else self.MUTED,
            rect.inflate(-self.u(10), 0),
            align="center",
            valign="center",
        )

    def _draw_character_skill_tree(self, rect: pygame.Rect) -> None:
        """Render the archetype skill tree as a tier x branch grid.

        Each row is a tier (1..5, top to bottom). Each column is a branch route.
        Nodes are drawn as small cards with state-tinted borders:
            chosen   — gold border, filled
            available — accent border, ready to pick on level-up/shrine
            locked   — iron border, prerequisites unmet
        A legend, a combo-state strip, and a hint line explain the colors, the
        current combo bonus, and how to gain nodes. Hovering an available node
        with the mouse previews the combo tier it would unlock.
        """
        from ..content import (
            skill_branches_for_archetype,
            skill_nodes_for_archetype,
            skill_tree_max_tier,
        )

        player = self.g.player
        archetype = player.class_name
        nodes = skill_nodes_for_archetype(archetype)
        branches = skill_branches_for_archetype(archetype)
        max_tier = skill_tree_max_tier(archetype)
        if not nodes or not branches or max_tier <= 0:
            self.draw_text(
                "No skill tree defined for this archetype.",
                self.g.small_font,
                self.MUTED,
                rect,
                align="center",
                valign="center",
            )
            return

        # Index nodes by (tier, branch). A branch may have at most one node
        # per tier in the current tree definition.
        grid: dict[tuple[int, str], object] = {}
        for node in nodes:
            grid[(node.tier, node.branch)] = node

        tiny_h = self.g.tiny_font.get_height()
        small_h = self.g.small_font.get_height()
        pad = max(self.u(10), 10)
        gap = self.u(6)

        # Combo state — completed branches and current bonus. Surfaced in a
        # strip above the grid so the player can see their commitment payoff.
        completed, combo_melee, combo_spell, combo_hp = self.g.combo_state()
        completed_count = len(completed)
        combo_active = completed_count >= 2
        # The combo_state total combines the per-branch depth bonus and the
        # multi-branch combo breadth bonus. Show the breakdown when both apply.
        from ..content import (
            COMBO_BONUS_PER_STEP_MAX_HP,
            COMBO_BONUS_PER_STEP_MELEE,
            COMBO_BONUS_PER_STEP_SPELL,
            COMPLETED_BRANCH_BONUS_MAX_HP,
            COMPLETED_BRANCH_BONUS_MELEE,
            COMPLETED_BRANCH_BONUS_SPELL,
        )

        depth_melee = completed_count * COMPLETED_BRANCH_BONUS_MELEE
        depth_spell = completed_count * COMPLETED_BRANCH_BONUS_SPELL
        depth_hp = completed_count * COMPLETED_BRANCH_BONUS_MAX_HP
        steps = max(0, completed_count - 1) if completed_count >= 2 else 0
        breadth_melee = steps * COMBO_BONUS_PER_STEP_MELEE
        breadth_spell = steps * COMBO_BONUS_PER_STEP_SPELL
        breadth_hp = steps * COMBO_BONUS_PER_STEP_MAX_HP
        combo_strip_h = small_h + self.u(4) if completed_count else 0

        # Header: branch names across the top.
        header_h = small_h + self.u(6)
        # Footer: legend + hint.
        legend_h = tiny_h + self.u(8)
        hint_h = tiny_h + self.u(6)
        footer_h = legend_h + hint_h
        grid_rect = pygame.Rect(
            rect.x,
            rect.y + header_h + combo_strip_h,
            rect.width,
            max(
                1,
                rect.height - header_h - combo_strip_h - footer_h - gap * 2,
            ),
        )

        # Combo strip — only drawn when there is something to show.
        if combo_strip_h:
            combo_rect = pygame.Rect(
                rect.x, rect.y + header_h, rect.width, combo_strip_h
            )
            if combo_active:
                label = (
                    f"{completed_count} branch complete: "
                    f"depth +{depth_melee}m/+{depth_spell}s/+{depth_hp}hp"
                    f" · combo x{completed_count} +{breadth_melee}m/"
                    f"+{breadth_spell}s/+{breadth_hp}hp"
                )
                color = self.WARNING
            else:
                label = (
                    f"{completed_count} branch complete: "
                    f"depth +{depth_melee}m/+{depth_spell}s/+{depth_hp}hp"
                    f" · commit to 2 for a combo bonus"
                )
                color = self.TEXT
            self.draw_text(
                label,
                self.g.small_font,
                color,
                combo_rect,
                align="center",
                valign="center",
            )

        # Row layout — tier label gutter on the left, columns to its right.
        tier_label_w = max(self.u(28), self.g.tiny_font.size("Tier 5")[0] + self.u(6))
        rows_area = pygame.Rect(
            grid_rect.x + tier_label_w,
            grid_rect.y,
            max(1, grid_rect.width - tier_label_w),
            grid_rect.height,
        )
        # Column layout — columns live inside `rows_area` (after the tier-label
        # gutter), so size them from `rows_area.width` to avoid overflowing the
        # container's right edge.
        col_gap = self.u(6)
        col_w = max(
            1, (rows_area.width - col_gap * (len(branches) - 1)) // len(branches)
        )
        row_h = max(1, (rows_area.height - gap * (max_tier - 1)) // max_tier)

        # Branch headers.
        for col, branch in enumerate(branches):
            col_x = rows_area.x + col * (col_w + col_gap)
            header_color = self.WARNING if branch in completed else self.MUTED
            self.draw_text(
                branch,
                self.g.small_font,
                header_color,
                pygame.Rect(col_x, rect.y, col_w, header_h),
                align="center",
                valign="center",
            )

        # Reset the mouse-hover cell map; repopulated as nodes are drawn so
        # `handle_events` can map mouse positions to node keys next frame.
        self.g._skill_node_cells = {}

        # Tier rows.
        for tier in range(1, max_tier + 1):
            row_y = rows_area.y + (tier - 1) * (row_h + gap)
            # Tier label in the gutter.
            self.draw_text(
                f"Tier {tier}",
                self.g.tiny_font,
                self.MUTED,
                pygame.Rect(grid_rect.x, row_y, tier_label_w, row_h),
                align="left",
                valign="center",
            )
            for col, branch in enumerate(branches):
                node = grid.get((tier, branch))
                col_x = rows_area.x + col * (col_w + col_gap)
                cell = pygame.Rect(col_x, row_y, col_w, row_h)
                if node is None:
                    # Empty cell — a faint placeholder keeps the grid aligned.
                    pygame.draw.rect(
                        self.screen,
                        self.PANEL_INK,
                        cell,
                        border_radius=self.u(6),
                    )
                    pygame.draw.rect(
                        self.screen,
                        self.IRON_DARK,
                        cell,
                        max(1, self.u(1)),
                        border_radius=self.u(6),
                    )
                    continue
                self._draw_skill_node_cell(node, cell, pad, tiny_h, small_h)
                self.g._skill_node_cells[node.key] = cell
                # Hover highlight — a bright outline around the cell the mouse
                # is over, so the player can see which node the preview refers to.
                if self.g.character_menu_hovered_node == node.key:
                    pygame.draw.rect(
                        self.screen,
                        self.TEXT,
                        cell,
                        max(1, self.u(2)),
                        border_radius=self.u(6),
                    )

        # Legend + hint footer.
        legend_y = grid_rect.bottom + gap
        legend_rect = pygame.Rect(rect.x, legend_y, rect.width, legend_h)
        sw_h = max(self.u(10), tiny_h)
        sw_gap = self.u(6)
        x = legend_rect.x
        samples = (
            (self.WARNING, "Chosen"),
            (self.g.skill_color(), "Available"),
            (self.IRON, "Locked"),
        )
        for color, label in samples:
            sw_rect = pygame.Rect(x, legend_rect.y, sw_h, sw_h)
            pygame.draw.rect(
                self.screen, self.PANEL_INK, sw_rect, border_radius=self.u(2)
            )
            pygame.draw.rect(
                self.screen, color, sw_rect, max(1, self.u(1)), border_radius=self.u(2)
            )
            text_rect = pygame.Rect(
                x + sw_h + sw_gap,
                legend_rect.y,
                self.g.tiny_font.size(label)[0],
                sw_h,
            )
            self.draw_text(
                label, self.g.tiny_font, self.TEXT, text_rect, valign="center"
            )
            x = text_rect.right + self.u(16)
        # Available count on the right of the legend.
        available = self.g.available_skill_choices()
        count_text = f"{len(available)} path{'s' if len(available) != 1 else ''} ready"
        count_w = self.g.tiny_font.size(count_text)[0]
        self.draw_text(
            count_text,
            self.g.tiny_font,
            self.g.skill_color() if available else self.MUTED,
            pygame.Rect(legend_rect.right - count_w, legend_rect.y, count_w, sw_h),
            valign="center",
        )

        hint_y = legend_y + legend_h
        hint_rect = pygame.Rect(rect.x, hint_y, rect.width, hint_h)
        # Milestone 3.3: if the player is hovering an available node, preview
        # the combo tier it would unlock; otherwise show the skill-point spend
        # hint so the player knows how to acquire nodes.
        hovered_key = self.g.character_menu_hovered_node
        hint_text = (
            "Level-ups award skill points · click an available node to spend one."
        )
        hint_color = self.MUTED
        if hovered_key:
            from ..content import skill_node_by_key

            hovered = skill_node_by_key(hovered_key)
            if hovered is not None:
                state = self.g.skill_node_state(hovered)
                if state == "available":
                    p_melee, p_spell, p_hp = self.g.combo_preview(hovered)
                    _, c_melee, c_spell, c_hp = self.g.combo_state()
                    if (p_melee, p_spell, p_hp) != (c_melee, c_spell, c_hp):
                        hint_text = (
                            f"{hovered.name} → combo +{p_melee} melee "
                            f"+{p_spell} spell +{p_hp} HP"
                        )
                        hint_color = self.WARNING
                    elif self.g.player.skill_points > 0:
                        hint_text = f"{hovered.name} · click to spend 1 skill point"
                        hint_color = self.g.skill_color()
                    else:
                        hint_text = f"{hovered.name} · no skill points available"
                elif state == "chosen":
                    hint_text = f"{hovered.name} · acquired"
                else:
                    hint_text = f"{hovered.name} · locked"
        self.draw_text(
            hint_text,
            self.g.tiny_font,
            hint_color,
            hint_rect,
            align="center",
            valign="center",
        )

    def _draw_skill_node_cell(
        self,
        node,
        cell: pygame.Rect,
        pad: int,
        tiny_h: int,
        small_h: int,
    ) -> None:
        state = self.g.skill_node_state(node)
        if state == "chosen":
            border = self.WARNING
            fill = self.PANEL_2
            name_color = self.WARNING
        elif state == "available":
            border = self.g.skill_color()
            fill = self.PANEL_2
            name_color = self.TEXT
        else:
            border = self.IRON
            fill = self.PANEL_INK
            name_color = self.MUTED

        pygame.draw.rect(self.screen, fill, cell, border_radius=self.u(6))
        # Soft state-tinted wash.
        wash = pygame.Surface(cell.size, pygame.SRCALPHA)
        wash_alpha = 36 if state == "chosen" else (22 if state == "available" else 0)
        if wash_alpha:
            pygame.draw.rect(
                wash,
                (*border, wash_alpha),
                wash.get_rect(),
                border_radius=self.u(6),
            )
            self.screen.blit(wash, cell)
        pygame.draw.rect(
            self.screen,
            border,
            cell,
            max(1, self.u(1)),
            border_radius=self.u(6),
        )

        inner = cell.inflate(-pad * 2, -pad)
        if inner.height < tiny_h:
            # Cell too short for text — just show the name ellipsized.
            self.draw_text(
                self.ellipsize(node.name, self.g.tiny_font, inner.width),
                self.g.tiny_font,
                name_color,
                inner,
                align="center",
                valign="center",
            )
            return

        name_rect = pygame.Rect(inner.x, inner.y, inner.width, small_h)
        self.draw_text(
            self.ellipsize(node.name, self.g.small_font, name_rect.width),
            self.g.small_font,
            name_color,
            name_rect,
            align="center",
            valign="center",
        )
        desc_rect = pygame.Rect(
            inner.x,
            name_rect.bottom + self.u(2),
            inner.width,
            inner.bottom - name_rect.bottom - self.u(2),
        )
        # Wrap the description into the remaining space; show as many lines as fit.
        lines = self.wrap_text(node.description, self.g.tiny_font, desc_rect.width)
        line_h = tiny_h + self.u(2)
        y = desc_rect.y
        shown = 0
        max_lines = max(1, desc_rect.height // line_h)
        for line in lines[:max_lines]:
            self.draw_text(
                line,
                self.g.tiny_font,
                self.TEXT if state != "locked" else self.MUTED,
                pygame.Rect(desc_rect.x, y, desc_rect.width, line_h),
                align="center",
                valign="top",
            )
            y += line_h
            shown += 1
        if shown == 0:
            self.draw_text(
                self.ellipsize(node.description, self.g.tiny_font, desc_rect.width),
                self.g.tiny_font,
                self.MUTED,
                desc_rect,
                align="center",
                valign="center",
            )
