# pyright: reportAttributeAccessIssue=false, reportUnusedImport=false
from __future__ import annotations

import math
from collections import deque
from typing import cast

import pygame

from ..constants import DUNGEON_DEPTH, TILE_H, TILE_W, WORLD_SCALE, SlashEffect
from ..content import HUMANOID_ENEMY_NAMES
from ..models import (
    Color,
    Enemy,
    ImpactEffect,
    Item,
    Player,
    Projectile,
    SecretCache,
    Shopkeeper,
    Shrine,
    StoryGuest,
    Tile,
    Trap,
)
from ..quest_assets import (
    CutsceneActorAsset,
    SpriteAnimationFrameAsset,
    format_asset_text,
)


class RenderingHudMixin:
    def cooldown_ratio(self, timer: float, cooldown: float) -> float:
        if cooldown <= 0.001:
            return 0.0
        return max(0.0, min(1.0, timer / cooldown))

    def draw_hud_cooldown_pips(self, bounds: pygame.Rect) -> None:
        timers = (
            ("M", self.player.melee_timer, self.melee_cooldown(), (255, 226, 150)),
            ("B", self.player.bolt_timer, self.bolt_cooldown(), (96, 190, 255)),
            ("N", self.player.nova_timer, self.nova_cooldown(), (185, 125, 255)),
            ("D", self.player.dash_timer, self.dash_cooldown(), (225, 184, 82)),
        )
        active = [entry for entry in timers if entry[1] > 0.001 and entry[2] > 0.001]
        if not active:
            return

        radius = max(self.ui(7), min(self.ui(12), bounds.height // 8))
        spacing = radius * 2 + self.ui(7)
        total_w = spacing * (len(active) - 1) + radius * 2
        base_x = bounds.right - total_w + radius
        center_y = bounds.y + radius + self.ui(2)
        line_w = max(1, self.ui(1))
        label = self.tiny_font.render("CD", True, (154, 148, 138))
        label_rect = label.get_rect(
            right=max(bounds.x, base_x - radius - self.ui(6)), centery=center_y
        )
        self.screen.blit(label, label_rect)

        for index, (key, timer, cooldown, color) in enumerate(active):
            cx = base_x + index * spacing
            cy = center_y
            remaining = self.cooldown_ratio(timer, cooldown)
            progress = 1.0 - remaining
            outer_rect = pygame.Rect(0, 0, radius * 2, radius * 2)
            outer_rect.center = (cx, cy)

            pygame.draw.circle(self.screen, (14, 13, 18), (cx, cy), radius)
            pygame.draw.circle(
                self.screen,
                (74, 70, 82),
                (cx, cy),
                max(1, radius - self.ui(2)),
                line_w,
            )
            fill_h = max(1, int((radius * 1.45) * progress))
            fill_rect = pygame.Rect(
                cx - radius // 2,
                cy + radius // 2 - fill_h,
                radius,
                fill_h,
            )
            pygame.draw.rect(self.screen, (*self.shade(color, -38), 165), fill_rect)

            if progress > 0.0:
                start = -math.pi / 2
                end = start + math.tau * progress
                pygame.draw.arc(
                    self.screen,
                    color,
                    outer_rect.inflate(-self.ui(1), -self.ui(1)),
                    start,
                    end,
                    max(2, line_w + 1),
                )
            text = self.tiny_font.render(key, True, (226, 220, 210))
            self.screen.blit(text, text.get_rect(center=(cx, cy)))

    def inventory_count_for_slot(self, slot: str) -> int:
        return sum(1 for item in self.player.inventory if item.slot == slot)

    def hud_action_slots(self) -> list[dict[str, object]]:
        melee_name, bolt_name, nova_name, dash_name = self.skill_names()
        class_color = self.skill_color()
        return [
            {
                "kind": "melee",
                "icon": "melee",
                "hotkey": "1",
                "label": melee_name,
                "timer": self.player.melee_timer,
                "cooldown": self.melee_cooldown(),
                "cost": self.melee_stamina_cost(),
                "resource": self.player.stamina,
                "resource_name": "ST",
                "color": self.mix((255, 226, 150), class_color, 0.18),
            },
            {
                "kind": "bolt",
                "icon": "bolt",
                "hotkey": "2",
                "label": bolt_name,
                "timer": self.player.bolt_timer,
                "cooldown": self.bolt_cooldown(),
                "cost": self.bolt_mana_cost(),
                "resource": self.player.mana,
                "resource_name": "MP",
                "color": self.mix((96, 190, 255), class_color, 0.24),
            },
            {
                "kind": "nova",
                "icon": "nova",
                "hotkey": "3",
                "label": nova_name,
                "timer": self.player.nova_timer,
                "cooldown": self.nova_cooldown(),
                "cost": self.nova_mana_cost(),
                "resource": self.player.mana,
                "resource_name": "MP",
                "color": self.mix((185, 125, 255), class_color, 0.24),
            },
            {
                "kind": "dash",
                "icon": "dash",
                "hotkey": "4",
                "label": dash_name,
                "timer": self.player.dash_timer,
                "cooldown": self.dash_cooldown(),
                "cost": self.dash_stamina_cost(),
                "resource": self.player.stamina,
                "resource_name": "ST",
                "color": self.mix((225, 184, 82), class_color, 0.18),
            },
            {
                "kind": "health_potion",
                "icon": "health_potion",
                "hotkey": "5",
                "label": "Health",
                "timer": 0.0,
                "cooldown": 0.0,
                "cost": 0,
                "resource": self.player.hp,
                "resource_name": "HP",
                "count": self.inventory_count_for_slot("potion"),
                "color": (220, 66, 70),
            },
            {
                "kind": "mana_potion",
                "icon": "mana_potion",
                "hotkey": "6",
                "label": "Mana",
                "timer": 0.0,
                "cooldown": 0.0,
                "cost": 0,
                "resource": self.player.mana,
                "resource_name": "MP",
                "count": self.inventory_count_for_slot("mana_potion"),
                "color": (76, 128, 230),
            },
        ]

    def hud_slot_int(self, slot: dict[str, object], key: str, default: int = 0) -> int:
        return int(cast(int | float | str, slot.get(key, default)))

    def hud_slot_float(
        self, slot: dict[str, object], key: str, default: float = 0.0
    ) -> float:
        return float(cast(int | float | str, slot.get(key, default)))

    def hud_action_slot_status(self, slot: dict[str, object]) -> str:
        kind = str(slot.get("kind", ""))
        if kind == "health_potion":
            count = self.hud_slot_int(slot, "count")
            if count <= 0:
                return "EMPTY"
            return "FULL" if self.player.hp >= self.player.max_hp else f"x{count}"
        if kind == "mana_potion":
            count = self.hud_slot_int(slot, "count")
            if count <= 0:
                return "EMPTY"
            return "FULL" if self.player.mana >= self.player.max_mana else f"x{count}"
        timer = self.hud_slot_float(slot, "timer")
        if timer > 0.001:
            return f"{timer:.1f}s"
        resource = self.hud_slot_float(slot, "resource")
        cost = self.hud_slot_float(slot, "cost")
        if resource < cost:
            return str(slot.get("resource_name", "RES"))
        return "READY"

    def hud_action_slot_ready(self, slot: dict[str, object]) -> bool:
        kind = str(slot.get("kind", ""))
        if kind == "health_potion":
            return (
                self.hud_slot_int(slot, "count") > 0
                and self.player.hp < self.player.max_hp
            )
        if kind == "mana_potion":
            return (
                self.hud_slot_int(slot, "count") > 0
                and self.player.mana < self.player.max_mana
            )
        return self.hud_slot_float(slot, "timer") <= 0.001 and self.hud_slot_float(
            slot, "resource"
        ) >= self.hud_slot_float(slot, "cost")

    def draw_hud_action_bar(self, rect: pygame.Rect) -> None:
        slots = self.hud_action_slots()
        if not slots or rect.width < self.ui(210) or rect.height < self.ui(42):
            return
        inner = rect.inflate(-max(self.ui(12), 12), -max(self.ui(8), 8))
        gap = max(self.ui(6), 6)
        icon_size = min(
            max(self.ui(40), 40),
            inner.height,
            max(28, (inner.width - gap * (len(slots) - 1)) // len(slots)),
        )
        if icon_size < 30:
            gap = max(3, self.ui(3))
            icon_size = max(24, (inner.width - gap * (len(slots) - 1)) // len(slots))
        total_w = icon_size * len(slots) + gap * (len(slots) - 1)
        x = inner.centerx - total_w // 2
        y = inner.centery - icon_size // 2
        for slot in slots:
            self.draw_hud_action_icon(slot, pygame.Rect(x, y, icon_size, icon_size))
            x += icon_size + gap

    def draw_hud_action_icon(self, slot: dict[str, object], rect: pygame.Rect) -> None:
        color = cast(Color, slot.get("color", self.theme.accent))
        ready = self.hud_action_slot_ready(slot)
        status = self.hud_action_slot_status(slot)
        timer = self.hud_slot_float(slot, "timer")
        cooldown = self.hud_slot_float(slot, "cooldown")
        remaining = self.cooldown_ratio(timer, cooldown)
        border = color if ready or timer > 0.001 else (92, 86, 94)
        fill = self.shade(color, -112 if ready else -136)
        pygame.draw.rect(self.screen, fill, rect, border_radius=self.ui(8))
        pygame.draw.rect(
            self.screen, border, rect, max(1, self.ui(1)), border_radius=self.ui(8)
        )
        shine = pygame.Rect(rect.x + 2, rect.y + 2, rect.width - 4, rect.height // 3)
        shine_surface = pygame.Surface(shine.size, pygame.SRCALPHA)
        pygame.draw.rect(
            shine_surface,
            (255, 255, 255, 18 if ready else 9),
            shine_surface.get_rect(),
            border_radius=self.ui(7),
        )
        self.screen.blit(shine_surface, shine)

        glyph_rect = rect.inflate(-self.ui(13), -self.ui(14))
        glyph_rect.y += self.ui(3)
        glyph_rect.height = max(8, glyph_rect.height - self.tiny_font.get_height() // 2)
        self.draw_hud_action_glyph(str(slot.get("icon", "")), glyph_rect, color, ready)

        label_rect = pygame.Rect(
            rect.x + self.ui(3),
            rect.bottom - self.tiny_font.get_height() - self.ui(2),
            rect.width - self.ui(6),
            self.tiny_font.get_height(),
        )
        self.draw_ui_text(
            self.screen,
            str(slot.get("label", "")),
            self.tiny_font,
            (224, 218, 205) if ready else (162, 158, 152),
            label_rect,
            align="center",
        )

        hotkey = str(slot.get("hotkey", ""))
        key_w = min(
            rect.width - self.ui(4),
            max(self.ui(16), self.tiny_font.size(hotkey)[0] + self.ui(6)),
        )
        key_rect = pygame.Rect(
            rect.x + self.ui(3), rect.y + self.ui(3), key_w, self.ui(14)
        )
        pygame.draw.rect(self.screen, (9, 8, 12), key_rect, border_radius=self.ui(4))
        pygame.draw.rect(
            self.screen,
            (*border, 255),
            key_rect,
            max(1, self.ui(1)),
            border_radius=self.ui(4),
        )
        self.draw_ui_text(
            self.screen,
            hotkey,
            self.tiny_font,
            (245, 238, 218),
            key_rect.inflate(-self.ui(2), 0),
            align="center",
            valign="center",
        )

        if "count" in slot:
            count_text = str(slot.get("count", 0))
            count_size = max(
                self.ui(15), self.tiny_font.size(count_text)[0] + self.ui(6)
            )
            count_rect = pygame.Rect(0, 0, count_size, self.ui(15))
            count_rect.bottomright = (rect.right - self.ui(3), rect.bottom - self.ui(3))
            pygame.draw.rect(
                self.screen, (8, 8, 12), count_rect, border_radius=self.ui(7)
            )
            pygame.draw.rect(
                self.screen,
                color,
                count_rect,
                max(1, self.ui(1)),
                border_radius=self.ui(7),
            )
            self.draw_ui_text(
                self.screen,
                count_text,
                self.tiny_font,
                (245, 238, 218),
                count_rect.inflate(-self.ui(2), 0),
                align="center",
                valign="center",
            )

        if remaining > 0.001:
            overlay_h = max(1, int(rect.height * remaining))
            overlay = pygame.Surface((rect.width, overlay_h), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 142))
            self.screen.blit(overlay, (rect.x, rect.y))
            progress = 1.0 - remaining
            pygame.draw.arc(
                self.screen,
                color,
                rect.inflate(-self.ui(4), -self.ui(4)),
                -math.pi / 2,
                -math.pi / 2 + math.tau * progress,
                max(2, self.ui(2)),
            )
        elif not ready:
            overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 90))
            self.screen.blit(overlay, rect)

        if status != "READY" and not ("count" in slot and status.startswith("x")):
            status_rect = pygame.Rect(
                rect.x + self.ui(4),
                rect.centery - self.tiny_font.get_height() // 2,
                rect.width - self.ui(8),
                self.tiny_font.get_height(),
            )
            text_color = (250, 230, 170) if timer > 0.001 else (218, 204, 176)
            self.draw_ui_text(
                self.screen,
                status,
                self.tiny_font,
                text_color,
                status_rect,
                align="center",
                valign="center",
            )

    def draw_hud_action_glyph(
        self, icon: str, rect: pygame.Rect, color: Color, ready: bool
    ) -> None:
        color = color if ready else self.shade(color, -48)
        cx, cy = rect.center
        line_w = max(2, self.ui(2))
        if icon == "melee":
            pygame.draw.line(
                self.screen,
                (24, 22, 28),
                (rect.left, rect.bottom),
                (rect.right, rect.top),
                line_w + max(1, self.ui(1)),
            )
            pygame.draw.line(
                self.screen,
                color,
                (rect.left, rect.bottom),
                (rect.right, rect.top),
                line_w,
            )
            pygame.draw.line(
                self.screen,
                self.shade(color, 34),
                (cx - rect.width // 5, cy + rect.height // 5),
                (cx + rect.width // 5, cy + rect.height // 5),
                line_w,
            )
        elif icon == "bolt":
            points = [
                (cx - rect.width // 5, rect.top),
                (cx + rect.width // 8, cy - rect.height // 8),
                (cx - rect.width // 10, cy),
                (cx + rect.width // 5, rect.bottom),
            ]
            pygame.draw.lines(self.screen, (24, 22, 28), False, points, line_w + 2)
            pygame.draw.lines(self.screen, color, False, points, line_w)
        elif icon == "nova":
            radius = max(5, min(rect.width, rect.height) // 3)
            pygame.draw.circle(self.screen, color, (cx, cy), radius, line_w)
            for angle in (0.0, math.pi / 2, math.pi, math.pi * 1.5):
                pygame.draw.line(
                    self.screen,
                    self.shade(color, 24),
                    (
                        cx + int(math.cos(angle) * radius * 0.45),
                        cy + int(math.sin(angle) * radius * 0.45),
                    ),
                    (
                        cx + int(math.cos(angle) * radius * 1.55),
                        cy + int(math.sin(angle) * radius * 1.55),
                    ),
                    max(1, self.ui(1)),
                )
        elif icon == "dash":
            for offset in (-rect.width // 7, rect.width // 7):
                points = [
                    (cx + offset - rect.width // 6, rect.top + rect.height // 5),
                    (cx + offset + rect.width // 7, cy),
                    (cx + offset - rect.width // 6, rect.bottom - rect.height // 5),
                ]
                pygame.draw.lines(self.screen, color, False, points, line_w)
        else:
            bottle = pygame.Rect(
                0, 0, max(8, rect.width // 2), max(12, rect.height * 2 // 3)
            )
            bottle.center = (cx, cy + rect.height // 10)
            neck = pygame.Rect(
                0, 0, max(4, bottle.width // 2), max(4, bottle.height // 4)
            )
            neck.midbottom = (bottle.centerx, bottle.y + self.ui(3))
            liquid = self.shade(color, 18 if icon == "mana_potion" else 8)
            pygame.draw.rect(self.screen, (28, 26, 32), neck, border_radius=self.ui(2))
            pygame.draw.rect(
                self.screen, (28, 26, 32), bottle, border_radius=self.ui(5)
            )
            fill = bottle.inflate(-self.ui(3), -self.ui(3))
            fill.y += fill.height // 3
            fill.height = max(2, fill.height * 2 // 3)
            pygame.draw.rect(self.screen, liquid, fill, border_radius=self.ui(4))
            pygame.draw.rect(
                self.screen,
                self.shade(color, 52),
                bottle,
                max(1, self.ui(1)),
                border_radius=self.ui(5),
            )

    def draw_ui(self) -> None:
        width, height = self.screen.get_size()
        reserved_h = self.hud_panel_height()
        accent = self.theme.accent
        outer = max(self.ui(14), 18)
        gap = max(self.ui(8), 12)
        action_gap = max(self.ui(8), 8)
        reserved_inner_h = max(1, reserved_h - self.ui(24))
        action_h = max(self.ui(54), min(self.ui(70), int(reserved_inner_h * 0.46)))
        panel_h = max(1, reserved_h - action_h - action_gap)
        panel = pygame.Rect(0, height - panel_h, width, panel_h)
        dock = pygame.Surface(panel.size, pygame.SRCALPHA)
        pygame.draw.rect(dock, (12, 12, 17, 238), dock.get_rect())
        pygame.draw.line(
            dock, (*self.shade(accent, -18), 190), (0, 0), (width, 0), self.ui(2)
        )
        pygame.draw.line(
            dock,
            (255, 245, 210, 26),
            (self.ui(18), self.ui(8)),
            (width - self.ui(18), self.ui(8)),
            self.ui(1),
        )
        self.screen.blit(dock, panel)

        inner = pygame.Rect(
            outer,
            panel.y + self.ui(12),
            max(1, width - outer * 2),
            max(1, panel_h - self.ui(24)),
        )
        top_area = pygame.Rect(inner.x, inner.y, inner.width, inner.height)
        action_bar = pygame.Rect(
            inner.x, panel.y - action_gap - action_h, inner.width, action_h
        )
        left_w = max(170, min(max(self.ui(120), 190), int(top_area.width * 0.29)))
        center_w = max(190, min(max(self.ui(150), 230), int(top_area.width * 0.33)))
        if top_area.width - left_w - center_w - gap * 2 < 170:
            left_w = max(150, int(top_area.width * 0.30))
            center_w = max(170, int(top_area.width * 0.32))
        right_w = max(1, top_area.width - left_w - center_w - gap * 2)
        resources = pygame.Rect(top_area.x, top_area.y, left_w, top_area.height)
        character = pygame.Rect(
            resources.right + gap, top_area.y, center_w, top_area.height
        )
        mission = pygame.Rect(
            character.right + gap, top_area.y, right_w, top_area.height
        )
        hud_cards: tuple[tuple[pygame.Rect, Color], ...] = (
            (resources, (118, 94, 72)),
            (character, accent),
            (mission, self.shade(accent, -18)),
        )
        for card, border in hud_cards:
            self.draw_translucent_panel(
                self.screen,
                card,
                (18, 17, 23, 232),
                (border[0], border[1], border[2], 128),
                radius=self.ui(8),
            )

        pad = max(self.ui(8), 10)
        bar_gap = max(self.ui(4), 6)
        bar_h = max(
            self.ui(10),
            min(self.ui(17), (resources.height - pad * 2 - bar_gap * 2) // 3),
        )
        bars_h = bar_h * 3 + bar_gap * 2
        bar_y = resources.y + (resources.height - bars_h) // 2
        bar_w = max(1, resources.width - pad * 2)
        self.draw_bar(
            resources.x + pad,
            bar_y,
            bar_w,
            bar_h,
            self.player.hp,
            self.player.max_hp,
            (185, 46, 46),
            "HP",
        )
        self.draw_bar(
            resources.x + pad,
            bar_y + bar_h + bar_gap,
            bar_w,
            bar_h,
            self.player.mana,
            self.player.max_mana,
            (54, 102, 210),
            "Mana",
        )
        self.draw_bar(
            resources.x + pad,
            bar_y + (bar_h + bar_gap) * 2,
            bar_w,
            bar_h,
            self.player.stamina,
            self.player.max_stamina,
            (216, 170, 66),
            "Stamina",
        )

        weapon = (
            self.player.equipment["weapon"].name
            if self.player.equipment["weapon"]
            else "Training Sword"
        )
        armor = (
            self.player.equipment["armor"].name
            if self.player.equipment["armor"]
            else "Cloth"
        )
        line_h = max(self.small_font.get_height() + self.ui(3), self.ui(18))
        text_rect = character.inflate(-pad * 2, -pad * 2)
        self.draw_ui_text(
            self.screen,
            self.player.class_name,
            self.font,
            (242, 232, 210),
            pygame.Rect(
                text_rect.x, text_rect.y, text_rect.width, self.font.get_height()
            ),
        )
        char_y = text_rect.y + self.font.get_height() + self.ui(5)
        potion_count = sum(1 for item in self.player.inventory if item.slot == "potion")
        mana_potion_count = sum(
            1 for item in self.player.inventory if item.slot == "mana_potion"
        )
        stat_lines = [
            f"Level {self.player.level} · XP {self.player.xp}/{self.player.next_xp}",
            f"Upgrades {len(self.player.skill_upgrades)} · Potions {potion_count}/{mana_potion_count}",
            f"{weapon} · DMG {self.player.melee_damage()}",
            f"{armor} · DR {self.player.armor()}",
        ]
        for line in stat_lines:
            if char_y + line_h > text_rect.bottom:
                break
            self.draw_ui_text(
                self.screen,
                line,
                self.small_font,
                (210, 204, 190),
                pygame.Rect(text_rect.x, char_y, text_rect.width, line_h),
            )
            char_y += line_h

        hint = self.current_interaction_hint()
        objective = (
            "Find the stairs to descend deeper"
            if self.current_depth < DUNGEON_DEPTH
            else "Defeat the gate tyrant, then reach the stairs"
        )
        detail = ""
        objective_color = accent
        if hint:
            _key, title, detail, objective_color = hint
            objective = title
        mission_inner = mission.inflate(-pad * 2, -pad * 2)
        self.draw_ui_text(
            self.screen,
            objective,
            self.font,
            objective_color,
            pygame.Rect(
                mission_inner.x,
                mission_inner.y,
                mission_inner.width,
                self.font.get_height(),
            ),
            align="right",
        )
        mission_y = mission_inner.y + self.font.get_height() + self.ui(4)
        if detail:
            for wrapped in self.wrap_ui_text(
                detail, self.small_font, mission_inner.width
            )[:2]:
                if mission_y + line_h > mission_inner.bottom:
                    break
                self.draw_ui_text(
                    self.screen,
                    wrapped,
                    self.small_font,
                    (218, 210, 190),
                    pygame.Rect(
                        mission_inner.x, mission_y, mission_inner.width, line_h
                    ),
                    align="right",
                )
                mission_y += line_h
        self.draw_interaction_prompt(hint)

        quest_control = (
            "Q hide quest"
            if getattr(self, "quest_info_visible", True)
            else "Q show quest"
        )
        debug_dark = (
            " · Ctrl+Shift+D light"
            if self.is_current_floor_dark()
            else " · Ctrl+Shift+D dark"
        )
        control_lines = [
            f"Mouse/aim · 1-6 actions · E interact · I inventory · C character · {quest_control} · H help{debug_dark}",
        ]
        control_y = max(
            mission_y + self.ui(4),
            mission_inner.bottom - self.tiny_font.get_height() * 3,
        )
        tiny_h = max(self.tiny_font.get_height() + self.ui(2), self.ui(15))
        for controls in control_lines:
            for wrapped in self.wrap_ui_text(
                controls, self.tiny_font, mission_inner.width
            )[:2]:
                if control_y + tiny_h > mission_inner.bottom:
                    break
                self.draw_ui_text(
                    self.screen,
                    wrapped,
                    self.tiny_font,
                    (170, 165, 155),
                    pygame.Rect(
                        mission_inner.x, control_y, mission_inner.width, tiny_h
                    ),
                    align="right",
                )
                control_y += tiny_h

        self.draw_hud_action_bar(action_bar)
        self.draw_run_header()
        self.draw_story_panel()
        self.draw_boss_bar()

    def draw_interaction_prompt(self, hint: tuple[str, str, str, Color] | None) -> None:
        if not hint:
            return
        key, title, detail, color = hint
        width, height = self.screen.get_size()
        prompt_w = min(width - self.ui(40), self.ui(560))
        prompt_h = max(self.ui(56), self.small_font.get_height() * 2 + self.ui(18))
        rect = pygame.Rect(
            width - prompt_w - self.ui(22),
            height - self.hud_panel_height() - prompt_h - self.ui(12),
            prompt_w,
            prompt_h,
        )
        if rect.y < self.ui(108):
            rect.y = self.ui(108)
        surface = pygame.Surface(rect.size, pygame.SRCALPHA)
        self.draw_translucent_panel(
            surface,
            surface.get_rect(),
            (12, 11, 14, 232),
            (*color, 184),
            radius=self.ui(9),
        )
        key_rect = pygame.Rect(
            self.ui(10),
            self.ui(10),
            self.ui(44),
            prompt_h - self.ui(20),
        )
        pygame.draw.rect(
            surface, (*self.shade(color, -55), 236), key_rect, border_radius=self.ui(7)
        )
        pygame.draw.rect(
            surface, (*color, 230), key_rect, self.ui(1), border_radius=self.ui(7)
        )
        self.draw_ui_text(surface, key, self.font, color, key_rect, "center", "center")
        text_x = key_rect.right + self.ui(12)
        text_w = max(1, prompt_w - text_x - self.ui(12))
        self.draw_ui_text(
            surface,
            title,
            self.small_font,
            (245, 238, 216),
            pygame.Rect(text_x, self.ui(8), text_w, self.small_font.get_height()),
        )
        detail_y = self.ui(10) + self.small_font.get_height()
        for wrapped in self.wrap_ui_text(detail, self.small_font, text_w)[:1]:
            self.draw_ui_text(
                surface,
                wrapped,
                self.small_font,
                (178, 174, 164),
                pygame.Rect(text_x, detail_y, text_w, self.small_font.get_height()),
            )
        self.screen.blit(surface, rect)

    def draw_screen_flash(self) -> None:
        if self.screen_flash_ttl <= 0:
            return
        width, height = self.screen.get_size()
        alpha = max(0, min(120, int(120 * (self.screen_flash_ttl / 0.30))))
        overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        overlay.fill((*self.screen_flash_color, alpha))
        self.screen.blit(overlay, (0, 0))

    def draw_run_header(self) -> None:
        width, _height = self.screen.get_size()
        darkness = " — Dark" if self.is_current_floor_dark() else ""
        title = f"Run {self.run_number}: Depth {self.current_depth}/{DUNGEON_DEPTH} — {self.theme.name}{darkness}"
        difficulty = self.difficulty_profile()
        floor_plan = self.current_floor_plan()
        floor_summary = self.floor_plan_summary(floor_plan)
        modifier = (
            f"Difficulty: {difficulty.name} · Modifier: "
            f"{self.run_modifier.name} — {self.run_modifier.description}"
        )
        if floor_plan is not None:
            modifier = f"{modifier} · {floor_summary}"
        quest_info_visible = getattr(self, "quest_info_visible", True)
        story = (
            self.story_header_line()
            if quest_info_visible
            else "Quest info hidden · press Q to show"
        )
        story_color = (205, 185, 225) if quest_info_visible else (155, 150, 145)
        margin = self.ui(18)
        pad = self.ui(10)
        line_h = max(self.small_font.get_height() + self.ui(3), self.ui(18))
        header_w = min(width - margin * 2, self.ui(740))
        header_h = pad * 2 + self.font.get_height() + line_h * 2 + self.ui(4)
        rect = pygame.Rect(margin, self.ui(14), header_w, header_h)
        surface = pygame.Surface(rect.size, pygame.SRCALPHA)
        self.draw_translucent_panel(
            surface,
            surface.get_rect(),
            (10, 10, 15, 210),
            (*self.theme.accent, 120),
            radius=self.ui(9),
        )
        self.draw_ui_text(
            surface,
            title,
            self.font,
            self.theme.accent,
            pygame.Rect(pad, pad, header_w - pad * 2, self.font.get_height()),
        )
        y = pad + self.font.get_height() + self.ui(5)
        self.draw_ui_text(
            surface,
            modifier,
            self.small_font,
            (205, 200, 190),
            pygame.Rect(pad, y, header_w - pad * 2, line_h),
        )
        y += line_h
        self.draw_ui_text(
            surface,
            story,
            self.small_font,
            story_color,
            pygame.Rect(pad, y, header_w - pad * 2, line_h),
        )
        self.screen.blit(surface, rect)

    def draw_boss_bar(self) -> None:
        boss = self.boss_enemy()
        if not boss:
            return
        width, _height = self.screen.get_size()
        margin = self.ui(18)
        bar_w = min(width - margin * 2, self.ui(520))
        bar_h = max(self.ui(10), self.small_font.get_height() // 2)
        x = (width - bar_w) // 2
        y = self.ui(22)
        fill = int(bar_w * max(0, boss.hp) / boss.max_hp)
        rect = pygame.Rect(x, y, bar_w, bar_h)
        pygame.draw.rect(self.screen, (28, 10, 14), rect, border_radius=self.ui(5))
        pygame.draw.rect(
            self.screen,
            self.theme.accent,
            pygame.Rect(x, y, fill, bar_h),
            border_radius=self.ui(5),
        )
        pygame.draw.rect(
            self.screen,
            (190, 160, 115),
            rect,
            self.ui(1),
            border_radius=self.ui(5),
        )
        label = self.small_font.render(
            self.ellipsize_ui_text(boss.name, self.small_font, bar_w),
            True,
            (245, 235, 215),
        )
        self.screen.blit(label, label.get_rect(center=(width // 2, y - self.ui(9))))

    def draw_bar(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        value: float,
        max_value: float,
        color: Color,
        label: str,
    ) -> None:
        radius = max(2, min(self.ui(5), h // 2))
        rect = pygame.Rect(x, y, w, h)
        pygame.draw.rect(self.screen, (34, 31, 36), rect, border_radius=radius)
        ratio = 0.0 if max_value <= 0 else max(0.0, min(1.0, value / max_value))
        fill = int(w * ratio)
        if fill > 0:
            pygame.draw.rect(
                self.screen,
                color,
                pygame.Rect(x, y, fill, h),
                border_radius=radius,
            )
        pygame.draw.rect(
            self.screen,
            (105, 96, 88),
            rect,
            self.ui(1),
            border_radius=radius,
        )
        text = self.tiny_font.render(
            f"{label} {int(value)}/{int(max_value)}", True, (245, 240, 230)
        )
        self.screen.blit(text, text.get_rect(center=rect.center))

    def draw_inventory(self) -> None:
        self.menus.draw_inventory()

    def draw_shop_overlay(self) -> None:
        shopkeeper = self.active_shopkeeper
        if shopkeeper is None:
            return
        width, height = self.screen.get_size()
        panel_w = min(self.ui(620), width - self.ui(48))
        panel_h = min(self.ui(430), height - self.ui(70))
        rect = pygame.Rect(0, 0, panel_w, panel_h)
        rect.center = (width // 2, height // 2)
        overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 118))
        self.screen.blit(overlay, (0, 0))
        pygame.draw.rect(self.screen, (20, 18, 22), rect, border_radius=self.ui(10))
        pygame.draw.rect(
            self.screen, (225, 190, 92), rect, self.ui(2), border_radius=self.ui(10)
        )

        title = self.heading_font.render(shopkeeper.name, True, (245, 232, 194))
        self.screen.blit(
            title, title.get_rect(x=rect.x + self.ui(18), y=rect.y + self.ui(14))
        )
        subtitle = self.small_font.render(
            f"{shopkeeper.role} · {self.player.gold} gold · Tab {('Sell' if self.shop_mode == 'buy' else 'Buy')} · E trade · Esc close",
            True,
            (184, 174, 145),
        )
        self.screen.blit(
            subtitle, subtitle.get_rect(x=rect.x + self.ui(18), y=rect.y + self.ui(48))
        )

        mode_text = "BUY STOCK" if self.shop_mode == "buy" else "SELL INVENTORY"
        mode = self.font.render(mode_text, True, (225, 190, 92))
        self.screen.blit(
            mode, mode.get_rect(x=rect.x + self.ui(18), y=rect.y + self.ui(82))
        )

        entries = self.shop_entries()
        self.clamp_shop_cursor()
        list_top = rect.y + self.ui(112)
        row_h = self.ui(34)
        max_rows = max(1, (rect.bottom - list_top - self.ui(22)) // row_h)
        start = 0
        if self.shop_cursor >= max_rows:
            start = self.shop_cursor - max_rows + 1
        visible_entries = entries[start : start + max_rows]
        if not visible_entries:
            empty = self.font.render(
                "No wares here." if self.shop_mode == "buy" else "Nothing to sell.",
                True,
                (184, 174, 145),
            )
            self.screen.blit(empty, empty.get_rect(x=rect.x + self.ui(24), y=list_top))
            return

        for offset, item in enumerate(visible_entries):
            index = start + offset
            y = list_top + offset * row_h
            row = pygame.Rect(
                rect.x + self.ui(16), y, rect.w - self.ui(32), row_h - self.ui(4)
            )
            selected = index == self.shop_cursor
            if selected:
                pygame.draw.rect(
                    self.screen, (55, 45, 36), row, border_radius=self.ui(5)
                )
                pygame.draw.rect(
                    self.screen,
                    (225, 190, 92),
                    row,
                    self.ui(1),
                    border_radius=self.ui(5),
                )
            price = (
                self.shop_price(shopkeeper, item)
                if self.shop_mode == "buy"
                else self.shop_buyback_value(shopkeeper, item)
            )
            label_color = self.rarity_color(item.visible_rarity)
            label = self.small_font.render(item.label, True, label_color)
            self.screen.blit(
                label, label.get_rect(x=row.x + self.ui(8), centery=row.centery)
            )
            price_text = self.small_font.render(f"{price}g", True, (225, 190, 92))
            self.screen.blit(
                price_text,
                price_text.get_rect(right=row.right - self.ui(10), centery=row.centery),
            )

    def draw_character_menu(self) -> None:
        self.menus.draw_character_menu()

    def draw_title_menu(self) -> None:
        self.menus.draw_title_menu()

    def draw_options_menu(self) -> None:
        self.menus.draw_options_menu()

    def draw_about_screen(self) -> None:
        self.menus.draw_about_screen()

    def draw_exit_confirmation(self) -> None:
        self.menus.draw_exit_confirmation()

    def draw_help_overlay(self) -> None:
        self.menus.draw_help_overlay()

    def draw_archetype_select(self) -> None:
        self.menus.draw_archetype_select()

    def draw_state_overlay(self) -> None:
        self.menus.draw_state_overlay()

    def run_summary_lines(self) -> list[str]:
        minutes = int(self.elapsed // 60)
        seconds = int(self.elapsed % 60)
        bosses = ", ".join(self.run_stats.defeated_bosses[-3:]) or (
            "Gate defeated" if self.run_stats.boss_killed else "none"
        )
        notable = ", ".join(self.run_stats.notable_loot[-3:]) or "none"
        discoveries = ", ".join(self.run_stats.discoveries[-3:]) or "none"
        cause = self.run_stats.cause_of_death or "survived"
        progress = self.meta_progress
        return [
            (
                f"Time {minutes:02d}:{seconds:02d}  "
                f"Depth {self.current_depth}/{DUNGEON_DEPTH}  "
                f"Difficulty {self.difficulty_profile().name}  "
                f"Modifier {self.run_modifier.name}"
            ),
            f"Kills {self.run_stats.kills}  Boss {'defeated' if self.run_stats.boss_killed else 'alive'}  Damage taken {self.run_stats.damage_taken}  Cause {cause}",
            f"Loot {self.run_stats.loot_picked_up}  Potions {self.run_stats.potions_used}  Shrines {self.run_stats.shrines_used}  Notable {notable}",
            f"Secrets {self.run_stats.secrets_opened} ({discoveries})  Traps triggered {self.run_stats.traps_triggered}  Story choices {self.run_stats.story_choices}",
            f"Elites {self.run_stats.elites_killed}  Minibosses {self.run_stats.minibosses_killed}  Challenge rooms {self.run_stats.challenge_rooms_cleared}  Upgrades {self.run_stats.upgrades_chosen}",
            f"Bosses defeated {bosses}",
            f"Mastery: best depth {progress.get('best_depth', 0)}  clears {progress.get('clears', 0)}  known bosses {len(progress.get('bosses_defeated', []))}",
        ]

