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

from ..constants import MAX_INVENTORY
from ..models import Color, Item

MenuRow = tuple[str, str, str]


class MenuInventoryMixin:
    def inventory_layout(self) -> dict[str, pygame.Rect]:
        width, height = self.screen.get_size()
        margin = max(self.u(16), 18)
        box_w = min(max(self.u(620), int(width * 0.78)), width - margin * 2)
        box_h = min(max(self.u(440), int(height * 0.86)), height - margin * 2)
        legacy_box = pygame.Rect(
            (width - box_w) // 2, (height - box_h) // 2, box_w, box_h
        )
        short_layout = height < 440
        if short_layout:
            modern_side_margin = max(16, min(self.u(20), width // 32))
            modern_vertical_margin = max(8, min(self.u(10), height // 36))
            minimum_w, minimum_h = 600, 340
            width_ratio, height_ratio = 0.94, 0.94
        else:
            modern_side_margin = max(22, min(self.u(42), width // 16))
            modern_vertical_margin = max(18, min(self.u(32), height // 18))
            minimum_w, minimum_h = 560, 400
            width_ratio, height_ratio = 0.88, 0.88
        modern_w = min(
            max(1, width - modern_side_margin * 2),
            max(minimum_w, round(width * width_ratio)),
        )
        modern_h = min(
            max(1, height - modern_vertical_margin * 2),
            max(minimum_h, round(height * height_ratio)),
        )
        modern_box = pygame.Rect(
            (width - modern_w) // 2,
            (height - modern_h) // 2,
            modern_w,
            modern_h,
        )
        safe = self.menu_panel_content_rect(modern_box)
        modern = safe is not None
        box = modern_box if modern else legacy_box
        if modern:
            assert safe is not None
            inner = safe.inflate(-self.u(5) * 2, -self.u(3) * 2)
            if short_layout:
                gap = max(self.u(6), 6)
                header_h = max(
                    self.g.font.get_height()
                    + self.g.small_font.get_height()
                    + self.u(18),
                    56,
                )
                sort_h = max(self.g.small_font.get_height() + self.u(14), 36)
                controls_h = max(
                    (self.g.tiny_font.get_height() + 4) * 2 + self.u(18),
                    56,
                )
            else:
                gap = max(self.u(8), 8)
                header_h = max(
                    self.g.font.get_height()
                    + self.g.small_font.get_height()
                    + max(self.u(8), 8)
                    + max(self.u(14), 14),
                    68,
                )
                sort_h = max(
                    self.g.small_font.get_height() + max(self.u(16), 16), 40
                )
                controls_h = max(
                    (self.g.tiny_font.get_height() + 7) * 2 + self.u(18),
                    68,
                )
        else:
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
        if modern:
            column_gap = max(self.u(7), 7)
            details_w = min(
                max(180, int(content.width * 0.38)),
                max(1, content.width - column_gap - 220),
            )
            list_w = max(1, content.width - column_gap - details_w)
        else:
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

    def _draw_inventory_section_panel(
        self, name: str, rect: pygame.Rect, accent: Color | None = None
    ) -> pygame.Rect:
        content, _used_asset = self.inset_panel(rect, accent)
        self.g._inventory_inset_rects[name] = rect.copy()
        self.g._inventory_inset_content_rects[name] = content.copy()
        return content

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
        with self.g.fitted_ui_layout((960, 540)):
            self._draw_inventory_fitted()

    def _draw_inventory_fitted(self) -> None:
        width, height = self.screen.get_size()
        dim = pygame.Surface((width, height), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 108))
        self.screen.blit(dim, (0, 0))

        layout = self.inventory_layout()
        self.g._inventory_layout = {key: rect.copy() for key, rect in layout.items()}
        self.g._inventory_inset_rects = {}
        self.g._inventory_inset_content_rects = {}
        box = layout["box"]
        header = layout["header"]
        sort_rect = layout["sort"]
        list_rect = layout["list"]
        details_rect = layout["details"]
        controls_rect = layout["controls"]
        used_asset = self.panel(box, (150, 120, 70), alpha=252)

        row_h, row_gap, visible_rows = self.inventory_row_metrics(list_rect)
        self.g.ensure_inventory_cursor_visible(visible_rows)
        self._inventory_asset_panel = used_asset
        try:
            self.draw_inventory_header(header)
            self.draw_inventory_sort_bar(sort_rect)
            self.draw_inventory_list(list_rect, row_h, row_gap, visible_rows)
            self.draw_inventory_details(details_rect)
            self.draw_inventory_controls(controls_rect)
        finally:
            del self._inventory_asset_panel

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
        modern = bool(getattr(self, "_inventory_asset_panel", False))
        content = rect
        if modern:
            content = self._draw_inventory_section_panel("sort", rect)
        else:
            pygame.draw.rect(self.screen, self.PANEL_INK, rect, border_radius=self.u(8))
            pygame.draw.rect(
                self.screen,
                self.STONE_LIGHT,
                rect,
                max(1, self.u(1)),
                border_radius=self.u(8),
            )
        pad = max(self.u(3), 3) if modern else max(self.u(10), 10)
        label_w = min(max(self.u(42), 42), content.width // 5)
        self.draw_text(
            "Sort",
            self.g.small_font,
            self.MUTED,
            pygame.Rect(content.x + pad, content.y, label_w, content.height),
            valign="center",
        )
        modes = (("type", "Type"), ("rarity", "Rarity"), ("power", "Power"))
        chip_gap = max(self.u(5), 5)
        x = content.x + pad + label_w + chip_gap
        hint_w = min(max(self.u(116), 104), max(0, content.right - x) // 3)
        chip_w = max(
            1,
            (content.right - x - hint_w - chip_gap * 3 - pad) // 3,
        )
        chip_h = max(1, content.height - pad * 2)
        for mode, label in modes:
            active = self.g.inventory_sort_mode == mode
            chip = pygame.Rect(x, content.y + pad, chip_w, chip_h)
            color = self.WARNING if active else self.IRON
            if active:
                fill = self.shade(color, -64)
                pygame.draw.rect(self.screen, fill, chip, border_radius=self.u(7))
                glow = pygame.Surface(chip.size, pygame.SRCALPHA)
                pygame.draw.rect(
                    glow,
                    (*color, 40),
                    glow.get_rect(),
                    border_radius=self.u(7),
                )
                self.screen.blit(glow, chip)
            elif not modern:
                pygame.draw.rect(
                    self.screen, self.PANEL_INK, chip, border_radius=self.u(7)
                )
            if active or not modern:
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
        hint_rect = pygame.Rect(
            x,
            content.y,
            max(1, content.right - x - pad),
            content.height,
        )
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
        modern = bool(getattr(self, "_inventory_asset_panel", False))
        if modern:
            list_rect = self._draw_inventory_section_panel("list", list_rect)
        else:
            pygame.draw.rect(
                self.screen, self.PANEL_INK, list_rect, border_radius=self.u(9)
            )
            pygame.draw.rect(
                self.screen,
                self.STONE_LIGHT,
                list_rect,
                max(1, self.u(1)),
                border_radius=self.u(9),
            )
        header_h = max(self.g.small_font.get_height() + self.u(12), self.u(30))
        header_rect = pygame.Rect(list_rect.x, list_rect.y, list_rect.width, header_h)
        if not modern:
            band = pygame.Surface(header_rect.size, pygame.SRCALPHA)
            pygame.draw.rect(
                band,
                (214, 196, 150, 22),
                band.get_rect(),
                border_radius=self.u(9),
            )
            self.screen.blit(band, header_rect)
        self.draw_text(
            "Items",
            self.g.small_font,
            self.WARNING,
            header_rect.inflate(-self.u(4) if modern else -self.u(12), 0),
            valign="center",
        )
        count_text = f"{len(self.g.player.inventory)} carried"
        self.draw_text(
            count_text,
            self.g.tiny_font,
            self.MUTED,
            header_rect.inflate(-self.u(4) if modern else -self.u(12), 0),
            align="right",
            valign="center",
        )
        side_pad = self.u(2) if modern else self.u(8)
        bottom_pad = self.u(2) if modern else self.u(12)
        rows_rect = pygame.Rect(
            list_rect.x + side_pad,
            header_rect.bottom + self.u(4),
            max(1, list_rect.width - side_pad * 2),
            max(1, list_rect.bottom - header_rect.bottom - bottom_pad),
        )
        self.g._inventory_visible_row_rects = []
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
        old_clip = self.screen.get_clip()
        self.screen.set_clip(rows_rect.clip(old_clip))
        try:
            for index in range(start, end):
                row = pygame.Rect(rows_rect.x, y, row_w, min(row_h, rows_rect.height))
                self.g._inventory_visible_row_rects.append(row.copy())
                self.draw_inventory_item_row(
                    self.g.player.inventory[index],
                    index,
                    row,
                    index == self.g.inventory_cursor,
                )
                y += row_h + row_gap
        finally:
            self.screen.set_clip(old_clip)
        self.draw_inventory_scrollbar(rows_rect, visible_rows)


    def draw_inventory_item_row(
        self, item: Item, index: int, row: pygame.Rect, selected: bool
    ) -> None:
        color = self.item_color(item)
        # Recessed plate; selected rows get a gold inner glow.
        modern = bool(getattr(self, "_inventory_asset_panel", False))
        fill = self.PANEL_2 if selected else self.PANEL_INK
        if selected or not modern:
            pygame.draw.rect(self.screen, fill, row, border_radius=self.u(7))
        if selected:
            glow = pygame.Surface(row.size, pygame.SRCALPHA)
            pygame.draw.rect(
                glow,
                (*self.WARNING, 36),
                glow.get_rect(),
                border_radius=self.u(7),
            )
            self.screen.blit(glow, row)
        border = self.WARNING if selected else self.STONE_LIGHT
        if selected or not modern:
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
            pygame.draw.rect(
                self.screen,
                self.shade(self.WARNING, 40),
                marker,
                border_radius=self.u(3),
            )
        # Gem-style rarity slot — faceted look with a highlight.
        slot_size = min(self.u(38), row.height - self.u(14))
        slot_rect = pygame.Rect(
            row.x + self.u(9),
            row.y + (row.height - slot_size) // 2,
            slot_size,
            slot_size,
        )
        pygame.draw.rect(self.screen, self.BG_DEEP, slot_rect, border_radius=self.u(5))
        icon = self.g.rarity_icon(item.visible_rarity)
        shortcut = str(index + 1) if index < 9 else f"{index + 1}"
        if self.g.legacy_graphics:
            # Preserve the original faceted rarity gem in legacy mode.
            gem = slot_rect.inflate(-self.u(6), -self.u(6))
            pygame.draw.rect(
                self.screen, self.shade(color, -60), gem, border_radius=self.u(4)
            )
            tri = [
                (gem.x, gem.y),
                (gem.right, gem.y),
                (gem.x, gem.bottom),
            ]
            pygame.draw.polygon(self.screen, self.shade(color, 30), tri)
            pygame.draw.rect(
                self.screen, color, gem, max(1, self.u(1)), border_radius=self.u(4)
            )
            self.draw_text(
                f"{shortcut}{icon}",
                self.g.tiny_font,
                self.shade(color, 60),
                slot_rect.inflate(-self.u(2), 0),
                align="center",
                valign="center",
            )
        else:
            preview = self.g.sprites.item_preview(
                item.slot, max(1, slot_rect.width - self.u(6))
            )
            self.screen.blit(preview, preview.get_rect(center=slot_rect.center))
            badge = pygame.Rect(
                slot_rect.right - self.u(17),
                slot_rect.bottom - self.u(15),
                self.u(16),
                self.u(14),
            )
            pygame.draw.rect(self.screen, self.BG_DEEP, badge, border_radius=self.u(3))
            pygame.draw.rect(
                self.screen, color, badge, max(1, self.u(1)), border_radius=self.u(3)
            )
            self.draw_text(
                shortcut,
                self.g.tiny_font,
                self.shade(color, 60),
                badge,
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
        pygame.draw.rect(self.screen, self.PANEL_INK, tag_rect, border_radius=self.u(5))
        pygame.draw.rect(
            self.screen, self.IRON, tag_rect, max(1, self.u(1)), border_radius=self.u(5)
        )
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
            text_w,
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
        pygame.draw.rect(self.screen, self.PANEL_INK, track, border_radius=self.u(3))
        pygame.draw.rect(
            self.screen,
            self.IRON_DARK,
            track,
            max(1, self.u(1)),
            border_radius=self.u(3),
        )
        thumb_h = max(self.u(18), int(track.height * visible_rows / count))
        max_scroll = max(1, count - visible_rows)
        travel = max(1, track.height - thumb_h)
        thumb_y = track.y + int(travel * self.g.inventory_scroll / max_scroll)
        thumb = pygame.Rect(track.x, thumb_y, track.width, thumb_h)
        pygame.draw.rect(self.screen, self.WARNING, thumb, border_radius=self.u(3))
        pygame.draw.rect(
            self.screen, self.shade(self.WARNING, 40), thumb, border_radius=self.u(3)
        )

    def draw_inventory_details(self, rect: pygame.Rect) -> None:
        modern = bool(getattr(self, "_inventory_asset_panel", False))
        gap = max(self.u(8), 8)
        if modern and rect.height < self.u(220):
            gap = max(self.u(4), 4)
            equipment_h = min(max(self.u(44), 44), max(1, rect.height // 2))
            item_h = max(1, rect.height - equipment_h - gap)
        else:
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
        modern = bool(getattr(self, "_inventory_asset_panel", False))
        panel_rect = rect
        if modern:
            rect = self._draw_inventory_section_panel("selected", rect)
        else:
            pygame.draw.rect(self.screen, self.PANEL_INK, rect, border_radius=self.u(9))
            pygame.draw.rect(
                self.screen,
                self.STONE_LIGHT,
                rect,
                max(1, self.u(1)),
                border_radius=self.u(9),
            )
        compact = modern and panel_rect.height < self.u(110)
        pad = max(self.u(4), 4) if modern else max(self.u(10), 10)
        title_font = self.g.tiny_font if compact else self.g.small_font
        title_rect = pygame.Rect(
            rect.x + pad,
            rect.y + pad,
            rect.width - pad * 2,
            title_font.get_height(),
        )
        self.draw_text("Selected", title_font, self.WARNING, title_rect)
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
        if compact:
            y = title_rect.bottom + self.u(1)
            self.draw_text(
                item.display_name,
                self.g.small_font,
                color,
                pygame.Rect(
                    rect.x + pad,
                    y,
                    rect.width - pad * 2,
                    self.g.small_font.get_height(),
                ),
            )
            y += self.g.small_font.get_height() + self.u(1)
            self.draw_text(
                self.g.item_decision_summary(item),
                self.g.tiny_font,
                self.TEXT,
                pygame.Rect(
                    rect.x + pad,
                    y,
                    rect.width - pad * 2,
                    max(1, rect.bottom - y - pad),
                ),
            )
            return
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
        # Tag chip row — procedural icons + labels, wrapping inside the card.
        tags = self.g.item_affix_tag_chips(item)
        if tags:
            y = self._draw_affix_tag_chips(rect, pad, y, tags, color)
        extra_lines: list[str] = self.g.item_affix_tooltip_lines(item)
        if item.unique_effect:
            extra_lines.append(f"Effect: {item.unique_effect}")
        if item.cursed:
            extra_lines.append("Cursed bargain: hotter rolls, slower handling.")
        extra_lines.append("Enter/E use · Del drop")
        line_gap = max(self.g.tiny_font.get_height() + self.u(3), self.u(15))
        text_rect_w = rect.width - pad * 2
        for line in extra_lines:
            for wrapped in self.wrap_text(line, self.g.tiny_font, text_rect_w):
                if y + self.g.tiny_font.get_height() > rect.bottom - pad:
                    return
                self.draw_text(
                    wrapped,
                    self.g.tiny_font,
                    self.MUTED,
                    pygame.Rect(
                        rect.x + pad, y, text_rect_w, self.g.tiny_font.get_height()
                    ),
                )
                y += line_gap

    def draw_inventory_equipment(self, rect: pygame.Rect) -> None:
        modern = bool(getattr(self, "_inventory_asset_panel", False))
        panel_rect = rect
        if modern:
            rect = self._draw_inventory_section_panel("equipment", rect)
        if modern and panel_rect.height < self.u(112):
            weapon = self.g.player.equipment["weapon"]
            armor = self.g.player.equipment["armor"]
            pad = max(self.u(3), 3)
            line_h = max(1, (rect.height - pad * 2) // 2)
            equipment = (
                (
                    "Weapon",
                    weapon.label if weapon else "Training Sword (+0 dmg)",
                    self.item_color(weapon) if weapon else self.MUTED,
                ),
                (
                    "Armor",
                    armor.label if armor else "Cloth (+0 armor)",
                    self.item_color(armor) if armor else self.MUTED,
                ),
            )
            for index, (label, value, color) in enumerate(equipment):
                self.draw_text(
                    f"{label} · {value}",
                    self.g.tiny_font,
                    color,
                    pygame.Rect(
                        rect.x + pad,
                        rect.y + pad + index * line_h,
                        rect.width - pad * 2,
                        line_h,
                    ),
                    valign="center",
                )
            return
        if not modern:
            pygame.draw.rect(self.screen, self.PANEL_INK, rect, border_radius=self.u(9))
            pygame.draw.rect(
                self.screen,
                self.STONE_LIGHT,
                rect,
                max(1, self.u(1)),
                border_radius=self.u(9),
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
        modern = bool(getattr(self, "_inventory_asset_panel", False))
        if not modern:
            pygame.draw.rect(self.screen, self.BG_DEEP, rect, border_radius=self.u(6))
            pygame.draw.rect(
                self.screen,
                self.IRON_DARK,
                rect,
                max(1, self.u(1)),
                border_radius=self.u(6),
            )
        # Left accent strip tinted to the rarity color.
        strip = pygame.Rect(rect.x, rect.y, self.u(3), rect.height)
        pygame.draw.rect(self.screen, color, strip, border_radius=self.u(2))
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
        modern = bool(getattr(self, "_inventory_asset_panel", False))
        panel_rect = rect
        if modern:
            rect = self._draw_inventory_section_panel("controls", rect)
        else:
            pygame.draw.rect(self.screen, self.PANEL_INK, rect, border_radius=self.u(9))
            pygame.draw.rect(
                self.screen,
                self.STONE_LIGHT,
                rect,
                max(1, self.u(1)),
                border_radius=self.u(9),
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
        compact = modern and panel_rect.height <= 56
        pad = 1 if compact else (3 if modern else 7)
        gap = 1 if compact else (3 if modern else 5)
        font = self.g.tiny_font
        if compact:
            pill_h = max(font.get_height() + 4, 18)
            pill_pad_x = 12
        else:
            pill_h = max(
                font.get_height() + (6 if modern else 8),
                20 if modern else 22,
            )
            pill_pad_x = 16
        x = rect.x + pad
        y = rect.y + pad
        self.g._inventory_control_pill_rects = []
        for entry in entries:
            pill_w = min(
                max(font.size(entry)[0] + pill_pad_x, 68),
                rect.width - pad * 2,
            )
            if x + pill_w > rect.right - pad:
                x = rect.x + pad
                y += pill_h + gap
            if y + pill_h > rect.bottom - pad:
                break
            pill = pygame.Rect(x, y, pill_w, pill_h)
            self.g._inventory_control_pill_rects.append(pill.copy())
            if not modern:
                pygame.draw.rect(
                    self.screen, self.PANEL_2, pill, border_radius=self.u(6)
                )
                pygame.draw.rect(
                    self.screen,
                    self.IRON,
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

    def _draw_affix_tag_chips(
        self, rect: pygame.Rect, pad: int, y: int, tags: list[str], color: Color
    ) -> int:
        from ..inventory import AFFIX_TAG_LABELS

        tiny = self.g.tiny_font
        tiny_h = tiny.get_height()
        icon_size = max(self.u(12), tiny_h)
        chip_h = max(icon_size + self.u(2), tiny_h + self.u(4))
        chip_gap = self.u(4)
        inner_x = rect.x + pad
        max_x = rect.right - pad
        x = inner_x
        for tag in tags:
            label = AFFIX_TAG_LABELS.get(tag, tag)
            label_w = tiny.size(label)[0]
            chip_w = icon_size + self.u(4) + label_w + self.u(8)
            if x + chip_w > max_x:
                x = inner_x
                y += chip_h + self.u(2)
            if y + chip_h > rect.bottom - pad:
                return y
            chip_rect = pygame.Rect(x, y, chip_w, chip_h)
            pygame.draw.rect(
                self.screen, self.PANEL_2, chip_rect, border_radius=self.u(4)
            )
            pygame.draw.rect(
                self.screen,
                self.IRON_DARK,
                chip_rect,
                max(1, self.u(1)),
                border_radius=self.u(4),
            )
            icon_rect = pygame.Rect(
                x + self.u(3), y + (chip_h - icon_size) // 2, icon_size, icon_size
            )
            self.draw_tag_icon(tag, icon_rect, color)
            self.draw_text(
                label,
                tiny,
                self.MUTED,
                pygame.Rect(
                    icon_rect.right + self.u(3), y, label_w + self.u(2), chip_h
                ),
                valign="center",
            )
            x += chip_w + chip_gap
        return y + chip_h + self.u(4)

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
