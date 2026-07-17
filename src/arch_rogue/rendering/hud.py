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


HUD_ACTION_SKILL_ASSETS: dict[str, tuple[str, str, str, str]] = {
    "Warden": (
        "hud.action.warden.shield_bash",
        "hud.action.warden.guard_bolt",
        "hud.action.warden.time_skip",
        "hud.action.warden.guard_step",
    ),
    "Rogue": (
        "hud.action.rogue.backstab",
        "hud.action.rogue.knife_fan",
        "hud.action.rogue.ambush_bell",
        "hud.action.rogue.shadow_dash",
    ),
    "Arcanist": (
        "hud.action.arcanist.mage_strike",
        "hud.action.arcanist.arc_bolt",
        "hud.action.arcanist.frost_nova",
        "hud.action.arcanist.blink",
    ),
    "Acolyte": (
        "hud.action.acolyte.blood_rite",
        "hud.action.acolyte.spirit_bolt",
        "hud.action.acolyte.spirit_call",
        "hud.action.acolyte.dark_step",
    ),
    "Ranger": (
        "hud.action.ranger.hawk_slash",
        "hud.action.ranger.multishot",
        "hud.action.ranger.spirit_beast",
        "hud.action.ranger.vault",
    ),
}


class RenderingHudMixin:
    def cooldown_ratio(self, timer: float, cooldown: float) -> float:
        if cooldown <= 0.001:
            return 0.0
        return max(0.0, min(1.0, timer / cooldown))

    def draw_hud_cooldown_pips(self, bounds: pygame.Rect) -> None:
        timers = (
            ("1", self.player.melee_timer, self.melee_cooldown(), (255, 226, 150)),
            ("2", self.player.bolt_timer, self.bolt_cooldown(), (96, 190, 255)),
            ("3", self.player.class_skill_timer, self.class_skill_cooldown(), (185, 125, 255)),
            ("4", self.player.dash_timer, self.dash_cooldown(), (225, 184, 82)),
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

            # Recessed iron disc with a gold rim.
            pygame.draw.circle(self.screen, self.HUD_STONE_SHADOW, (cx, cy), radius)
            pygame.draw.circle(
                self.screen,
                self.HUD_IRON,
                (cx, cy),
                max(1, radius - self.ui(1)),
            )
            pygame.draw.circle(
                self.screen,
                self.HUD_IRON_LIGHT,
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
            text = self.tiny_font.render(key, True, self.HUD_GOLD_BRIGHT)
            self.screen.blit(text, text.get_rect(center=(cx, cy)))

    def inventory_count_for_slot(self, slot: str) -> int:
        return sum(1 for item in self.player.inventory if item.slot == slot)

    def hud_action_slots(self) -> list[dict[str, object]]:
        melee_name, bolt_name, class_skill_name, dash_name = self.skill_names()
        class_color = self.skill_color()
        class_skill_kind = self.class_skill_kind()
        class_skill_icon = {
            "ambush_bell": "ambush_bell",
            "time_skip": "time_skip",
            "spirit_beast": "spirit_beast",
        }.get(class_skill_kind, "nova")
        if class_skill_kind == "ambush_bell":
            class_skill_color = self.mix((214, 92, 150), class_color, 0.34)
        elif class_skill_kind == "time_skip":
            class_skill_color = self.mix((235, 205, 120), class_color, 0.30)
        elif class_skill_kind == "spirit_beast":
            class_skill_color = self.mix((142, 202, 92), class_color, 0.34)
        else:
            class_skill_color = self.mix((185, 125, 255), class_color, 0.24)
        class_skill_command = (
            self.spirit_beast_next_command()
            if class_skill_kind == "spirit_beast"
            else ""
        )
        class_skill_cost = 0 if class_skill_command else self.class_skill_mana_cost()
        skill_assets = HUD_ACTION_SKILL_ASSETS.get(
            self.player.class_name, ("", "", "", "")
        )
        return [
            {
                "kind": "melee",
                "icon": "melee",
                "asset": skill_assets[0],
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
                "asset": skill_assets[1],
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
                "kind": class_skill_kind,
                "icon": class_skill_icon,
                "asset": skill_assets[2],
                "hotkey": "3",
                "label": class_skill_name,
                "timer": self.player.class_skill_timer,
                "cooldown": self.class_skill_cooldown(),
                "cost": class_skill_cost,
                "resource": self.player.mana,
                "resource_name": "MP",
                "color": class_skill_color,
                "cooldown_command": class_skill_command,
            },
            {
                "kind": "dash",
                "icon": "dash",
                "asset": skill_assets[3],
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
                "asset": "hud.action.health_potion",
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
                "asset": "hud.action.mana_potion",
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
        cooldown_command = str(slot.get("cooldown_command", ""))
        if cooldown_command:
            return cooldown_command
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
        if str(slot.get("cooldown_command", "")):
            return True
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
        dock_w = min(rect.width, total_w + max(self.ui(38), 38))
        dock_rect = pygame.Rect(0, 0, dock_w, rect.height)
        dock_rect.center = rect.center
        dock = self.ui_asset_surface("hud.dock", dock_rect.size)
        if dock is not None:
            self.screen.blit(dock, dock_rect)
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
        border = color if ready or timer > 0.001 else self.HUD_IRON
        icon = str(slot.get("icon", ""))
        asset = str(slot.get("asset", ""))
        label = str(slot.get("label", ""))
        hotkey = str(slot.get("hotkey", ""))
        # The static plate, authored/procedural glyph, legacy label, and hotkey
        # badge do not depend on per-frame cooldown/count/status. Cache the
        # composed body so steady-state frames pay one blit per slot.
        cache = getattr(self, "_hud_icon_cache", None)
        if cache is None:
            cache = {}
            self._hud_icon_cache = cache
        key = (
            rect.size,
            color,
            ready,
            border,
            icon,
            asset,
            label,
            hotkey,
            self.ui_scale,
            self.asset_ui_active(),
        )
        body = cache.get(key)
        if body is None:
            body = self._build_hud_action_icon_body(
                rect.size, color, ready, border, icon, label, hotkey, asset
            )
            if len(cache) >= 256:
                cache.clear()
            cache[key] = body
        self.screen.blit(body, rect.topleft)

        # --- dynamic overlays (depend on per-frame cooldown/count/status) ---
        if "count" in slot:
            count_text = str(slot.get("count", 0))
            count_size = max(
                self.ui(15), self.tiny_font.size(count_text)[0] + self.ui(6)
            )
            count_rect = pygame.Rect(0, 0, count_size, self.ui(15))
            count_rect.bottomright = (rect.right - self.ui(3), rect.bottom - self.ui(3))
            pygame.draw.rect(
                self.screen, self.HUD_STONE_SHADOW, count_rect, border_radius=self.ui(7)
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
                self.HUD_GOLD_BRIGHT,
                count_rect.inflate(-self.ui(2), 0),
                align="center",
                valign="center",
            )

        if remaining > 0.001:
            overlay_h = max(1, int(rect.height * remaining))
            overlay = pygame.Surface((rect.width, overlay_h), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 150))
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
            overlay.fill((0, 0, 0, 100))
            self.screen.blit(overlay, rect)

        if status != "READY" and not ("count" in slot and status.startswith("x")):
            status_rect = pygame.Rect(
                rect.x + self.ui(4),
                rect.centery - self.tiny_font.get_height() // 2,
                rect.width - self.ui(8),
                self.tiny_font.get_height(),
            )
            text_color = self.HUD_GOLD_BRIGHT if timer > 0.001 else self.HUD_PARCHMENT
            self.draw_ui_text(
                self.screen,
                status,
                self.tiny_font,
                text_color,
                status_rect,
                align="center",
                valign="center",
            )

    def _build_hud_action_icon_body(
        self,
        size: tuple[int, int],
        color: Color,
        ready: bool,
        border: Color,
        icon: str,
        label: str,
        hotkey: str,
        asset: str = "",
    ) -> pygame.Surface:
        body = pygame.Surface(size, pygame.SRCALPHA)
        r = body.get_rect()
        modern_ui = self.asset_ui_active()
        # Draw onto the body via a self.screen swap so draw_hud_action_glyph /
        # draw_ui_text (which target self.screen) compose into the body without
        # needing a dest parameter. Coordinates are 0-relative to r.
        real_screen = self.screen
        self.screen = body
        try:
            # Recessed iron plate body with a vertical gradient. Modern mode
            # replaces only the static chrome; glyphs and state overlays remain live.
            action_slot = self.ui_asset_surface("hud.action_slot", size)
            modern_slot = action_slot is not None
            if modern_slot:
                assert action_slot is not None
                self.screen.blit(action_slot, (0, 0))
            else:
                top_fill = self.shade(color, -118 if ready else -140)
                bot_fill = self.shade(color, -150 if ready else -168)
                bands = max(4, min(12, r.height))
                for i in range(bands):
                    t = i / max(1, bands - 1)
                    c = (
                        int(top_fill[0] * (1 - t) + bot_fill[0] * t),
                        int(top_fill[1] * (1 - t) + bot_fill[1] * t),
                        int(top_fill[2] * (1 - t) + bot_fill[2] * t),
                    )
                    fy = r.y + int(i * r.height / bands)
                    fy2 = r.y + int((i + 1) * r.height / bands)
                    pygame.draw.rect(
                        self.screen,
                        c,
                        pygame.Rect(r.x, fy, r.width, fy2 - fy + 1),
                        border_top_left_radius=self.ui(8) if i == 0 else 0,
                        border_top_right_radius=self.ui(8) if i == 0 else 0,
                        border_bottom_left_radius=self.ui(8) if i == bands - 1 else 0,
                        border_bottom_right_radius=self.ui(8) if i == bands - 1 else 0,
                    )
                pygame.draw.rect(
                    self.screen,
                    self.HUD_STONE_SHADOW,
                    r,
                    max(1, self.ui(2)),
                    border_radius=self.ui(8),
                )
                pygame.draw.rect(
                    self.screen,
                    self.HUD_STONE_LIGHT,
                    r.inflate(-self.ui(2), -self.ui(2)),
                    max(1, self.ui(1)),
                    border_radius=self.ui(7),
                )
                # Procedural fallback keeps its original accent rim and shine.
                pygame.draw.rect(
                    self.screen,
                    border,
                    r,
                    max(1, self.ui(1)),
                    border_radius=self.ui(8),
                )
                shine = pygame.Rect(
                    r.x + self.ui(2),
                    r.y + self.ui(2),
                    r.width - self.ui(4),
                    r.height // 3,
                )
                shine_surface = pygame.Surface(shine.size, pygame.SRCALPHA)
                pygame.draw.rect(
                    shine_surface,
                    (255, 255, 255, 22 if ready else 11),
                    shine_surface.get_rect(),
                    border_radius=self.ui(7),
                )
                self.screen.blit(shine_surface, shine)
            if modern_slot and ready:
                # A small semantic readiness lamp replaces the legacy full rim.
                pygame.draw.circle(
                    self.screen,
                    self.shade(color, 36),
                    (r.right - self.ui(7), r.y + self.ui(7)),
                    max(2, self.ui(2)),
                )

            authored_icon = None
            authored_rect = r
            if modern_ui:
                authored_rect = r.inflate(-self.ui(9), -self.ui(9))
                authored_rect.y += self.ui(1)
                authored_icon = self.ui_asset_surface(asset, authored_rect.size)
            if authored_icon is not None:
                self.screen.blit(authored_icon, authored_rect)
            else:
                glyph_rect = r.inflate(-self.ui(13), -self.ui(14))
                glyph_rect.y += self.ui(3)
                glyph_rect.height = max(
                    8, glyph_rect.height - self.tiny_font.get_height() // 2
                )
                self.draw_hud_action_glyph(icon, glyph_rect, color, ready)

            if authored_icon is None:
                label_rect = pygame.Rect(
                    r.x + self.ui(3),
                    r.bottom - self.tiny_font.get_height() - self.ui(2),
                    r.width - self.ui(6),
                    self.tiny_font.get_height(),
                )
                self.draw_ui_text(
                    self.screen,
                    label,
                    self.tiny_font,
                    self.HUD_PARCHMENT if ready else self.HUD_MUTED,
                    label_rect,
                    align="center",
                )

            key_w = min(
                r.width - self.ui(4),
                max(self.ui(16), self.tiny_font.size(hotkey)[0] + self.ui(6)),
            )
            key_rect = pygame.Rect(
                r.x + self.ui(3), r.y + self.ui(3), key_w, self.ui(14)
            )
            if not modern_slot:
                # The authored slot already supplies the plate and trim.
                pygame.draw.rect(
                    self.screen,
                    self.HUD_STONE_SHADOW,
                    key_rect,
                    border_radius=self.ui(4),
                )
                pygame.draw.rect(
                    self.screen,
                    self.HUD_IRON,
                    key_rect.inflate(-self.ui(1), -self.ui(1)),
                    border_radius=self.ui(3),
                )
                pygame.draw.rect(
                    self.screen,
                    border,
                    key_rect,
                    max(1, self.ui(1)),
                    border_radius=self.ui(4),
                )
            self.draw_ui_text(
                self.screen,
                hotkey,
                self.tiny_font,
                self.HUD_GOLD_BRIGHT,
                key_rect.inflate(-self.ui(2), 0),
                align="center",
                valign="center",
            )
        finally:
            self.screen = real_screen
        try:
            body = body.convert_alpha()
        except pygame.error:
            pass
        return body

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
        elif icon == "spirit_beast":
            radius = max(6, min(rect.width, rect.height) // 3)
            outline = (24, 22, 28)
            head = [
                (cx - radius, cy - radius // 2),
                (cx - radius, cy - radius),
                (cx - radius // 3, cy - radius * 2 // 3),
                (cx, cy - radius),
                (cx + radius // 3, cy - radius * 2 // 3),
                (cx + radius, cy - radius),
                (cx + radius, cy - radius // 2),
                (cx + radius * 2 // 3, cy + radius // 2),
                (cx, cy + radius),
                (cx - radius * 2 // 3, cy + radius // 2),
            ]
            pygame.draw.polygon(self.screen, outline, head)
            pygame.draw.polygon(self.screen, color, head, line_w)
            muzzle = pygame.Rect(0, 0, radius, max(3, radius // 2))
            muzzle.center = (cx, cy + radius // 2)
            pygame.draw.ellipse(self.screen, self.shade(color, 28), muzzle)
            pygame.draw.circle(
                self.screen,
                outline,
                (cx - radius // 3, cy),
                max(1, self.ui(1)),
            )
            pygame.draw.circle(
                self.screen,
                outline,
                (cx + radius // 3, cy),
                max(1, self.ui(1)),
            )
            pygame.draw.circle(
                self.screen, outline, (cx, muzzle.centery), max(2, self.ui(2))
            )
        elif icon == "ambush_bell":
            radius = max(5, min(rect.width, rect.height) // 3)
            bell_rect = pygame.Rect(0, 0, radius + self.ui(7), radius)
            bell_rect.center = (cx, cy + self.ui(1))
            pygame.draw.ellipse(self.screen, (24, 22, 28), bell_rect.inflate(line_w, line_w))
            pygame.draw.ellipse(self.screen, color, bell_rect, line_w)
            pygame.draw.arc(
                self.screen,
                self.shade(color, 40),
                bell_rect.inflate(self.ui(5), self.ui(5)),
                math.pi,
                math.tau,
                line_w,
            )
            pygame.draw.line(
                self.screen,
                self.shade(color, 50),
                (cx + self.ui(1), bell_rect.top + self.ui(2)),
                (cx - self.ui(2), bell_rect.centery),
                max(1, self.ui(1)),
            )
            pygame.draw.circle(self.screen, self.shade(color, 48), (cx, bell_rect.bottom), max(2, self.ui(2)))
            for angle in (-0.75, 0.0, 0.75):
                pygame.draw.line(
                    self.screen,
                    self.shade(color, 28),
                    (cx, cy),
                    (
                        cx + int(math.sin(angle) * radius * 1.25),
                        cy - int(math.cos(angle) * radius * 0.85),
                    ),
                    max(1, self.ui(1)),
                )
        elif icon == "time_skip":
            # Milestone 3.18 — a clock face with swept hands: enemies slip
            # into slow time while the Warden keeps their own tempo.
            radius = max(6, min(rect.width, rect.height) // 3)
            pygame.draw.circle(self.screen, (24, 22, 28), (cx, cy), radius + line_w // 2)
            pygame.draw.circle(self.screen, color, (cx, cy), radius, line_w)
            pygame.draw.circle(
                self.screen, self.shade(color, 48), (cx, cy), max(2, self.ui(2))
            )
            for angle in (0.0, math.pi / 2, math.pi, math.pi * 1.5):
                pygame.draw.line(
                    self.screen,
                    self.shade(color, 30),
                    (
                        cx + int(math.cos(angle) * radius * 0.78),
                        cy + int(math.sin(angle) * radius * 0.78),
                    ),
                    (
                        cx + int(math.cos(angle) * radius * 0.96),
                        cy + int(math.sin(angle) * radius * 0.96),
                    ),
                    max(1, self.ui(1)),
                )
            pygame.draw.line(
                self.screen, color, (cx, cy), (cx, cy - radius * 0.6), line_w
            )
            pygame.draw.line(
                self.screen,
                self.shade(color, 34),
                (cx, cy),
                (cx + int(radius * 0.42), cy + int(radius * 0.32)),
                line_w,
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
        with self.fitted_ui_layout((960, 540)):
            self._draw_ui_fitted()

    def _draw_ui_fitted(self) -> None:
        width, height = self.screen.get_size()
        reserved_h = self.hud_panel_height()
        accent = self.theme.accent
        modern = self.asset_ui_active()
        outer = max(self.ui(14), 18)
        gap = max(self.ui(8), 12)
        if modern:
            action_gap = max(self.ui(6), 8)
            action_h = max(
                self.ui(52),
                min(self.ui(56), int(reserved_h * 0.38)),
            )
        else:
            action_gap = max(self.ui(8), 8)
            reserved_inner_h = max(1, reserved_h - self.ui(24))
            action_h = max(
                self.ui(54),
                min(self.ui(70), int(reserved_inner_h * 0.46)),
            )
        panel_h = max(1, reserved_h - action_h - action_gap)
        panel = pygame.Rect(0, height - panel_h, width, panel_h)

        panel_asset = self.ui_asset_surface("hud.panel", panel.size)
        panel_safe: pygame.Rect | None = None
        if panel_asset is not None:
            self.screen.blit(panel_asset, panel)
            panel_safe = self.ui_assets.content_rect("hud.panel", panel)
        else:
            # Legacy dock — a heavy recessed slab with a gold top edge and studs.
            dock = pygame.Surface(panel.size, pygame.SRCALPHA)
            top = self.mix(self.HUD_PANEL, accent, 0.05)
            bottom = self.HUD_STONE_SHADOW
            bands = max(8, min(32, panel_h))
            for i in range(bands):
                t = i / max(1, bands - 1)
                color = (
                    int(top[0] * (1 - t) + bottom[0] * t),
                    int(top[1] * (1 - t) + bottom[1] * t),
                    int(top[2] * (1 - t) + bottom[2] * t),
                    240,
                )
                y = int(i * panel_h / bands)
                y2 = int((i + 1) * panel_h / bands)
                pygame.draw.rect(dock, color, pygame.Rect(0, y, width, y2 - y + 1))
            pygame.draw.line(dock, (0, 0, 0, 220), (0, 0), (width, 0), self.ui(2))
            pygame.draw.line(
                dock,
                (*self.shade(accent, -18), 210),
                (0, self.ui(1)),
                (width, self.ui(1)),
                self.ui(1),
            )
            pygame.draw.line(
                dock,
                (*self.HUD_GOLD_BRIGHT, 40),
                (self.ui(18), self.ui(3)),
                (width - self.ui(18), self.ui(3)),
                self.ui(1),
            )
            stud_r = max(2, self.ui(3))
            stud_spacing = max(self.ui(80), 80)
            for sx in range(self.ui(40), width - self.ui(20), stud_spacing):
                cy = self.ui(6)
                pygame.draw.circle(dock, self.HUD_IRON_DARK, (sx, cy), stud_r + 1)
                pygame.draw.circle(dock, self.HUD_IRON, (sx, cy), stud_r)
                pygame.draw.circle(
                    dock,
                    self.HUD_IRON_LIGHT,
                    (sx - 1, cy - 1),
                    max(1, stud_r - 1),
                )
            self.screen.blit(dock, panel)

        panel_pad_y = self.ui(1 if modern else 2)
        inner = (
            panel_safe.inflate(-self.ui(4) * 2, -panel_pad_y * 2)
            if panel_safe is not None
            else pygame.Rect(
                outer,
                panel.y + self.ui(12),
                max(1, width - outer * 2),
                max(1, panel_h - self.ui(24)),
            )
        )
        top_area = pygame.Rect(inner.x, inner.y, inner.width, inner.height)
        action_bar = pygame.Rect(
            inner.x, panel.y - action_gap - action_h, inner.width, action_h
        )
        if modern:
            left_w = min(
                max(self.ui(240), int(top_area.width * 0.36)),
                self.ui(322),
            )
            center_w = min(
                max(self.ui(180), int(top_area.width * 0.27)),
                self.ui(242),
            )
            minimum_right_w = max(self.ui(160), 160)
            if top_area.width - left_w - center_w - gap * 2 < minimum_right_w:
                available_w = max(1, top_area.width - gap * 2)
                left_w = max(self.ui(190), int(available_w * 0.39))
                center_w = max(self.ui(150), int(available_w * 0.29))
        else:
            left_w = max(
                170,
                min(max(self.ui(120), 190), int(top_area.width * 0.29)),
            )
            center_w = max(
                190,
                min(max(self.ui(150), 230), int(top_area.width * 0.33)),
            )
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
            self.draw_ornate_hud_panel(
                self.screen,
                card,
                (18, 17, 23, 232),
                (border[0], border[1], border[2], 150),
                radius=self.ui(8),
            )

        pad = max(self.ui(8), 10)
        resources_content = self.ui_asset_content_rect("hud.panel", resources)
        character_content = self.ui_asset_content_rect("hud.panel", character)
        mission_content = self.ui_asset_content_rect("hud.panel", mission)
        card_pad_y = 0 if modern else self.ui(2)
        resources_inner = (
            resources_content.inflate(-self.ui(3) * 2, -card_pad_y * 2)
            if resources_content is not None
            else resources.inflate(-pad * 2, -pad * 2)
        )
        character_inner = (
            character_content.inflate(-self.ui(3) * 2, -card_pad_y * 2)
            if character_content is not None
            else character.inflate(-pad * 2, -pad * 2)
        )
        mission_inner = (
            mission_content.inflate(-self.ui(3) * 2, -card_pad_y * 2)
            if mission_content is not None
            else mission.inflate(-pad * 2, -pad * 2)
        )
        self._hud_layout = {
            "panel": panel.copy(),
            "panel_content": inner.copy(),
            "action_bar": action_bar.copy(),
            "resources": resources.copy(),
            "resources_content": resources_inner.copy(),
            "character": character.copy(),
            "character_content": character_inner.copy(),
            "mission": mission.copy(),
            "mission_content": mission_inner.copy(),
        }
        bar_gap = max(self.ui(3), 3) if modern else max(self.ui(4), 6)
        maximum_bar_h = self.ui(16 if modern else 17)
        bar_h = max(
            self.ui(8 if modern else 10),
            min(maximum_bar_h, (resources_inner.height - bar_gap * 2) // 3),
        )
        bars_h = bar_h * 3 + bar_gap * 2
        bar_y = resources_inner.y + (resources_inner.height - bars_h) // 2
        bar_w = max(1, resources_inner.width)
        bar_rects = tuple(
            pygame.Rect(
                resources_inner.x,
                bar_y + index * (bar_h + bar_gap),
                bar_w,
                bar_h,
            )
            for index in range(3)
        )
        self._hud_resource_bar_rects = tuple(rect.copy() for rect in bar_rects)
        bar_values = (
            (self.player.hp, self.player.max_hp, (168, 38, 38), "HP"),
            (self.player.mana, self.player.max_mana, (48, 92, 188), "Mana"),
            (
                self.player.stamina,
                self.player.max_stamina,
                (196, 156, 60),
                "Stamina",
            ),
        )
        for rect, (value, maximum, color, label) in zip(bar_rects, bar_values):
            self.draw_bar(
                rect.x,
                rect.y,
                rect.width,
                rect.height,
                value,
                maximum,
                color,
                label,
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
        title_font = self.small_font if modern else self.font
        body_font = self.tiny_font if modern else self.small_font
        line_h = (
            max(body_font.get_height() + self.ui(2), self.ui(13))
            if modern
            else max(body_font.get_height() + self.ui(3), self.ui(18))
        )
        text_rect = character_inner
        self.draw_ui_text(
            self.screen,
            self.player.class_name,
            title_font,
            self.HUD_GOLD_BRIGHT,
            pygame.Rect(
                text_rect.x, text_rect.y, text_rect.width, title_font.get_height()
            ),
        )
        # Thin divider under the class name.
        self.draw_hud_divider(
            self.screen,
            text_rect.x,
            text_rect.y + title_font.get_height() + self.ui(2),
            text_rect.right,
            self.HUD_GOLD,
        )
        char_y = text_rect.y + title_font.get_height() + self.ui(5 if modern else 8)
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
                body_font,
                self.HUD_BONE,
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
        objective_color = self.HUD_GOLD_BRIGHT
        if hint:
            _key, title, detail, objective_color = hint
            objective = title
        self.draw_ui_text(
            self.screen,
            objective,
            title_font,
            objective_color,
            pygame.Rect(
                mission_inner.x,
                mission_inner.y,
                mission_inner.width,
                title_font.get_height(),
            ),
            align="right",
        )
        mission_y = mission_inner.y + title_font.get_height() + self.ui(
            3 if modern else 4
        )
        if detail:
            for wrapped in self.wrap_ui_text(
                detail, body_font, mission_inner.width
            )[:2]:
                if mission_y + line_h > mission_inner.bottom:
                    break
                self.draw_ui_text(
                    self.screen,
                    wrapped,
                    body_font,
                    self.HUD_PARCHMENT,
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
                    self.HUD_MUTED,
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
        self._interaction_prompt_rect: pygame.Rect | None = None
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
        self._interaction_prompt_rect = rect.copy()
        surface = pygame.Surface(rect.size, pygame.SRCALPHA)
        self.draw_ornate_hud_panel(
            surface,
            surface.get_rect(),
            (12, 11, 14, 236),
            (*color, 200),
            radius=self.ui(9),
        )
        content = self.ui_asset_content_rect("hud.panel", surface.get_rect())
        content = (
            content.inflate(-self.ui(3) * 2, -self.ui(1) * 2)
            if content is not None
            else surface.get_rect().inflate(-self.ui(10) * 2, -self.ui(10) * 2)
        )
        key_rect = pygame.Rect(
            content.x,
            content.y,
            min(self.ui(44), max(1, content.width // 5)),
            content.height,
        )
        # Iron key plate with gold trim.
        pygame.draw.rect(
            surface, self.HUD_STONE_SHADOW, key_rect, border_radius=self.ui(7)
        )
        pygame.draw.rect(
            surface,
            self.HUD_IRON,
            key_rect.inflate(-self.ui(2), -self.ui(2)),
            border_radius=self.ui(6),
        )
        pygame.draw.rect(
            surface, (*color, 230), key_rect, self.ui(1), border_radius=self.ui(7)
        )
        self.draw_ui_text(
            surface, key, self.font, self.HUD_GOLD_BRIGHT, key_rect, "center", "center"
        )
        text_x = key_rect.right + self.ui(12)
        text_w = max(1, content.right - text_x)
        self.draw_ui_text(
            surface,
            title,
            self.small_font,
            self.HUD_PARCHMENT,
            pygame.Rect(text_x, content.y, text_w, self.small_font.get_height()),
        )
        detail_y = content.y + self.small_font.get_height() + self.ui(2)
        for wrapped in self.wrap_ui_text(detail, self.small_font, text_w)[:1]:
            self.draw_ui_text(
                surface,
                wrapped,
                self.small_font,
                self.HUD_MUTED,
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
        story_color = (205, 185, 225) if quest_info_visible else self.HUD_MUTED
        margin = self.ui(18)
        pad = self.ui(10)
        line_h = max(self.small_font.get_height() + self.ui(3), self.ui(18))
        header_w = min(width - margin * 2, self.ui(740))
        header_h = pad * 2 + self.font.get_height() + line_h * 2 + self.ui(4)
        rect = pygame.Rect(margin, self.ui(14), header_w, header_h)
        surface = pygame.Surface(rect.size, pygame.SRCALPHA)
        self.draw_ornate_hud_panel(
            surface,
            surface.get_rect(),
            (10, 10, 15, 215),
            (*self.theme.accent, 150),
            radius=self.ui(9),
            studs=True,
        )
        content = self.ui_asset_content_rect("hud.panel", surface.get_rect())
        content = (
            content.inflate(-self.ui(3) * 2, -self.ui(1) * 2)
            if content is not None
            else pygame.Rect(pad, pad, header_w - pad * 2, header_h - pad * 2)
        )
        title_rect = pygame.Rect(
            content.x, content.y, content.width, self.font.get_height()
        )
        self.draw_ui_text(
            surface,
            title,
            self.font,
            self.HUD_GOLD_BRIGHT,
            title_rect,
        )
        # Ornamental divider under the title.
        divider_y = title_rect.bottom + self.ui(3)
        self.draw_hud_divider(
            surface,
            content.x,
            divider_y,
            content.right,
            self.HUD_GOLD,
        )
        y = divider_y + self.ui(4)
        self.draw_ui_text(
            surface,
            modifier,
            self.small_font,
            self.HUD_BONE,
            pygame.Rect(content.x, y, content.width, line_h),
        )
        y += line_h
        self.draw_ui_text(
            surface,
            story,
            self.small_font,
            story_color,
            pygame.Rect(content.x, y, content.width, line_h),
        )
        self.screen.blit(surface, rect)

    def run_header_bottom(self) -> int:
        """Bottom y of the top-left run header panel (mirrors draw_run_header)."""
        pad = self.ui(10)
        line_h = max(self.small_font.get_height() + self.ui(3), self.ui(18))
        header_h = pad * 2 + self.font.get_height() + line_h * 2 + self.ui(4)
        return self.ui(14) + header_h

    def boss_bar_metrics(self) -> tuple[pygame.Rect, pygame.Rect, bool] | None:
        """Compute the boss bar + plaque rects so the HUD can avoid overlapping it.

        The bar is placed lower than the old top-of-screen position so it no
        longer overlaps the run header: the name plaque sits just below the run
        header and the bar sits below the plaque. If that would crash into the
        bottom HUD panel (short windows), it falls back to anchoring just above
        the bottom panel. Returns (bar_rect, plaque_rect, big) or None."""
        boss = self.boss_enemy()
        if not boss:
            return None
        width, height = self.screen.get_size()
        margin = self.ui(18)
        big = boss.size >= 2
        bar_w = min(width - margin * 2, self.ui(640 if big else 520))
        bar_h = max(
            self.ui(20 if big else 12),
            self.small_font.get_height() // 2 + self.ui(4),
        )
        plaque_h = self.ui(24 if big else 20)
        bottom_panel_top = height - self.hud_panel_height()
        bar_x = (width - bar_w) // 2
        # Preferred: plaque below the run header, bar below the plaque.
        plaque_top = self.run_header_bottom() + self.ui(8)
        bar_y = plaque_top + plaque_h + self.ui(4)
        # If that pushes the bar into the bottom HUD panel, anchor above it.
        if bar_y + bar_h > bottom_panel_top - self.ui(6):
            bar_y = bottom_panel_top - bar_h - self.ui(8)
            plaque_top = bar_y - plaque_h - self.ui(2)
        bar_rect = pygame.Rect(bar_x, bar_y, bar_w, bar_h)
        plaque = pygame.Rect(0, 0, bar_w, plaque_h)
        plaque.center = (width // 2, plaque_top + plaque_h // 2)
        return bar_rect, plaque, big

    def boss_bar_top(self) -> int | None:
        """Topmost y the boss bar cluster occupies, or None."""
        metrics = self.boss_bar_metrics()
        if metrics is None:
            return None
        _bar_rect, plaque_rect, _big = metrics
        return plaque_rect.top

    def draw_boss_bar(self) -> None:
        metrics = self.boss_bar_metrics()
        if metrics is None:
            return
        rect, plaque, big = metrics
        boss = self.boss_enemy()
        assert boss is not None
        width, _height = self.screen.get_size()
        bar_w = rect.width
        bar_h = rect.height
        x, y = rect.x, rect.y
        ratio = max(0.0, min(1.0, boss.hp / boss.max_hp))
        fill = int(bar_w * ratio)
        # Boss name plaque above the bar.
        label = self.small_font.render(
            self.ellipsize_ui_text(boss.name, self.small_font, bar_w),
            True,
            self.HUD_GOLD_BRIGHT,
        )
        plaque_w = label.get_width() + self.ui(28)
        plaque.size = (plaque_w, plaque.height)
        plaque.center = (width // 2, plaque.centery)
        plaque_surf = pygame.Surface(plaque.size, pygame.SRCALPHA)
        pygame.draw.rect(
            plaque_surf,
            (12, 8, 12, 230),
            plaque_surf.get_rect(),
            border_radius=self.ui(4),
        )
        pygame.draw.rect(
            plaque_surf,
            (*self.HUD_GOLD, 200),
            plaque_surf.get_rect(),
            max(1, self.ui(1)),
            border_radius=self.ui(4),
        )
        self.screen.blit(plaque_surf, plaque)
        self.screen.blit(label, label.get_rect(center=plaque.center))
        if big and boss.elite_modifier:
            # Subtitle role tag (e.g. "Floor Boss") under the name plaque.
            sub = self.small_font.render(boss.elite_modifier, True, self.theme.accent)
            sub_rect = sub.get_rect(midtop=(plaque.centerx, plaque.bottom + self.ui(1)))
            self.screen.blit(sub, sub_rect)
        # Blood trough — deep red recessed bar.
        pygame.draw.rect(
            self.screen, self.HUD_STONE_SHADOW, rect, border_radius=self.ui(5)
        )
        trough = rect.inflate(-self.ui(2), -self.ui(2))
        pygame.draw.rect(self.screen, (28, 10, 14), trough, border_radius=self.ui(4))
        if fill > 0:
            fill_rect = pygame.Rect(x, y, fill, bar_h)
            top_c = self.shade(self.theme.accent, 30)
            bot_c = self.shade(self.theme.accent, -40)
            fbands = max(2, min(10, bar_h))
            for i in range(fbands):
                t = i / max(1, fbands - 1)
                c = (
                    int(top_c[0] * (1 - t) + bot_c[0] * t),
                    int(top_c[1] * (1 - t) + bot_c[1] * t),
                    int(top_c[2] * (1 - t) + bot_c[2] * t),
                )
                fy = y + int(i * bar_h / fbands)
                fy2 = y + int((i + 1) * bar_h / fbands)
                pygame.draw.rect(
                    self.screen,
                    c,
                    pygame.Rect(x, fy, fill, fy2 - fy + 1),
                    border_radius=self.ui(5) if i == 0 else 0,
                )
            # Top specular.
            shine = pygame.Rect(
                x + self.ui(2),
                y + self.ui(1),
                max(1, fill - self.ui(4)),
                max(1, bar_h // 3),
            )
            shine_surf = pygame.Surface(shine.size, pygame.SRCALPHA)
            pygame.draw.rect(
                shine_surf,
                (255, 255, 255, 50),
                shine_surf.get_rect(),
                border_radius=self.ui(4),
            )
            self.screen.blit(shine_surf, shine)
        # Ornate gold frame.
        pygame.draw.rect(
            self.screen,
            self.HUD_GOLD,
            rect,
            self.ui(1),
            border_radius=self.ui(5),
        )
        # Iron studs at the bar ends.
        for sx in (rect.x + self.ui(6), rect.right - self.ui(6)):
            pygame.draw.circle(
                self.screen, self.HUD_IRON_DARK, (sx, rect.centery), self.ui(3) + 1
            )
            pygame.draw.circle(
                self.screen, self.HUD_IRON, (sx, rect.centery), self.ui(3)
            )
            pygame.draw.circle(
                self.screen,
                self.HUD_IRON_LIGHT,
                (sx - 1, rect.centery - 1),
                max(1, self.ui(2)),
            )
        # Quarter tick marks on big boss bars so the player can read phase
        # transitions and chunked health at a glance.
        if big:
            for frac in (0.25, 0.5, 0.75):
                tx = rect.x + int(bar_w * frac)
                pygame.draw.line(
                    self.screen,
                    (12, 8, 12),
                    (tx, rect.y + self.ui(1)),
                    (tx, rect.bottom - self.ui(1)),
                    max(1, self.ui(1)),
                )
                pygame.draw.line(
                    self.screen,
                    self.HUD_IRON_DARK,
                    (tx, rect.y + self.ui(2)),
                    (tx, rect.bottom - self.ui(2)),
                    max(1, self.ui(1)),
                )

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
        bar_asset = self.ui_asset_surface("hud.bar", rect.size)
        if bar_asset is not None:
            self.screen.blit(bar_asset, rect)
            trough = self.ui_asset_content_rect("hud.bar", rect)
            if trough is None:
                inset_x = max(2, min(self.ui(5), max(2, w // 12)))
                inset_y = max(1, min(self.ui(3), max(1, h // 5)))
                trough = rect.inflate(-inset_x * 2, -inset_y * 2)
            ratio = 0.0 if max_value <= 0 else max(0.0, min(1.0, value / max_value))
            fill = int(trough.width * ratio)
            if fill > 0 and trough.height > 0:
                fill_rect = pygame.Rect(trough.x, trough.y, fill, trough.height)
                top_c = self.shade(color, 36)
                bot_c = self.shade(color, -28)
                bands = max(2, min(10, fill_rect.height))
                for i in range(bands):
                    t = i / max(1, bands - 1)
                    band_color = (
                        int(top_c[0] * (1 - t) + bot_c[0] * t),
                        int(top_c[1] * (1 - t) + bot_c[1] * t),
                        int(top_c[2] * (1 - t) + bot_c[2] * t),
                    )
                    fy = fill_rect.y + int(i * fill_rect.height / bands)
                    fy2 = fill_rect.y + int((i + 1) * fill_rect.height / bands)
                    pygame.draw.rect(
                        self.screen,
                        band_color,
                        pygame.Rect(fill_rect.x, fy, fill_rect.width, fy2 - fy + 1),
                    )
                shine = pygame.Surface(
                    (fill_rect.width, max(1, fill_rect.height // 4)),
                    pygame.SRCALPHA,
                )
                shine.fill((255, 255, 255, 42))
                self.screen.blit(shine, fill_rect.topleft)
            bar_font = (
                self.small_font
                if h >= self.small_font.get_height() + self.ui(4)
                else self.tiny_font
            )
            label_text = f"{label} {int(value)}/{int(max_value)}"
            shadow = bar_font.render(label_text, True, (4, 4, 7))
            text = bar_font.render(label_text, True, self.HUD_PARCHMENT)
            text_rect = text.get_rect(center=rect.center)
            self.screen.blit(shadow, text_rect.move(self.ui(1), self.ui(1)))
            self.screen.blit(text, text_rect)
            return
        # Recessed stone trough — dark interior with a light top edge.
        pygame.draw.rect(self.screen, self.HUD_STONE_SHADOW, rect, border_radius=radius)
        trough = rect.inflate(-self.ui(2), -self.ui(2))
        pygame.draw.rect(
            self.screen, (24, 22, 28), trough, border_radius=max(1, radius - 1)
        )
        pygame.draw.line(
            self.screen,
            self.HUD_STONE_LIGHT,
            (trough.x + self.ui(2), trough.y),
            (trough.right - self.ui(2), trough.y),
            max(1, self.ui(1)),
        )
        ratio = 0.0 if max_value <= 0 else max(0.0, min(1.0, value / max_value))
        fill = int(w * ratio)
        if fill > 0:
            fill_rect = pygame.Rect(x, y, fill, h)
            # Vertical gradient on the fill — bright top, saturated bottom.
            top_c = self.shade(color, 36)
            bot_c = self.shade(color, -28)
            fbands = max(2, min(10, h))
            for i in range(fbands):
                t = i / max(1, fbands - 1)
                c = (
                    int(top_c[0] * (1 - t) + bot_c[0] * t),
                    int(top_c[1] * (1 - t) + bot_c[1] * t),
                    int(top_c[2] * (1 - t) + bot_c[2] * t),
                )
                fy = y + int(i * h / fbands)
                fy2 = y + int((i + 1) * h / fbands)
                pygame.draw.rect(
                    self.screen,
                    c,
                    pygame.Rect(x, fy, fill, fy2 - fy + 1),
                    border_radius=radius if i == 0 else 0,
                )
            # Specular highlight along the top of the fill.
            shine = pygame.Rect(
                x + self.ui(2),
                y + self.ui(1),
                max(1, fill - self.ui(4)),
                max(1, h // 4),
            )
            shine_surf = pygame.Surface(shine.size, pygame.SRCALPHA)
            pygame.draw.rect(
                shine_surf,
                (255, 255, 255, 55),
                shine_surf.get_rect(),
                border_radius=max(1, radius - 1),
            )
            self.screen.blit(shine_surf, shine)
        # Outer stone rim.
        pygame.draw.rect(
            self.screen,
            self.HUD_IRON,
            rect,
            self.ui(1),
            border_radius=radius,
        )
        text = self.tiny_font.render(
            f"{label} {int(value)}/{int(max_value)}", True, self.HUD_PARCHMENT
        )
        self.screen.blit(text, text.get_rect(center=rect.center))

    def draw_inventory(self) -> None:
        self.menus.draw_inventory()

    def draw_shop_overlay(self) -> None:
        with self.fitted_ui_layout((960, 540)):
            self._draw_shop_overlay_fitted()

    def _draw_shop_overlay_fitted(self) -> None:
        shopkeeper = self.active_shopkeeper
        if shopkeeper is None:
            return
        width, height = self.screen.get_size()
        panel_w = min(self.ui(620), width - self.ui(48))
        panel_h = min(self.ui(430), height - self.ui(70))
        rect = pygame.Rect(0, 0, panel_w, panel_h)
        rect.center = (width // 2, height // 2)
        overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 132))
        self.screen.blit(overlay, (0, 0))
        # Ornate shop panel — stone with gold trim and iron studs.
        self.draw_ornate_hud_panel(
            self.screen,
            rect,
            (20, 18, 22, 252),
            (*self.HUD_GOLD, 230),
            radius=self.ui(10),
            studs=True,
        )

        safe = self.ui_asset_content_rect("hud.panel", rect)
        modern = safe is not None
        if safe is not None:
            safe = safe.inflate(-self.ui(4) * 2, -self.ui(3) * 2)
        title_x = safe.x if safe is not None else rect.x + self.ui(18)
        title_y = safe.y if safe is not None else rect.y + self.ui(14)
        content_right = safe.right if safe is not None else rect.right - self.ui(18)
        content_bottom = safe.bottom if safe is not None else rect.bottom - self.ui(22)
        title = self.heading_font.render(shopkeeper.name, True, self.HUD_GOLD_BRIGHT)
        self.screen.blit(title, title.get_rect(x=title_x, y=title_y))
        # Ornamental divider under the title.
        self.draw_hud_divider(
            self.screen,
            title_x,
            title_y + title.get_height() + self.ui(4),
            content_right,
            self.HUD_GOLD,
        )
        subtitle = self.small_font.render(
            f"{shopkeeper.role} · {self.player.gold} gold · Tab {('Sell' if self.shop_mode == 'buy' else 'Buy')} · E trade · Esc close",
            True,
            self.HUD_BONE,
        )
        subtitle_y = (
            title_y + title.get_height() + self.ui(10)
            if modern
            else rect.y + self.ui(48)
        )
        self.screen.blit(subtitle, subtitle.get_rect(x=title_x, y=subtitle_y))

        mode_text = "BUY STOCK" if self.shop_mode == "buy" else "SELL INVENTORY"
        mode = self.font.render(mode_text, True, self.HUD_GOLD)
        mode_y = (
            subtitle_y + self.small_font.get_height() + self.ui(10)
            if modern
            else rect.y + self.ui(82)
        )
        self.screen.blit(mode, mode.get_rect(x=title_x, y=mode_y))

        entries = self.shop_entries()
        self.clamp_shop_cursor()
        list_top = (
            mode_y + self.font.get_height() + self.ui(8)
            if modern
            else rect.y + self.ui(112)
        )
        row_h = self.ui(34)
        max_rows = max(1, (content_bottom - list_top) // row_h)
        start = 0
        if self.shop_cursor >= max_rows:
            start = self.shop_cursor - max_rows + 1
        visible_entries = entries[start : start + max_rows]
        if not visible_entries:
            empty = self.font.render(
                "No wares here." if self.shop_mode == "buy" else "Nothing to sell.",
                True,
                self.HUD_MUTED,
            )
            self.screen.blit(empty, empty.get_rect(x=title_x + self.ui(6), y=list_top))
            return

        for offset, item in enumerate(visible_entries):
            index = start + offset
            y = list_top + offset * row_h
            row = pygame.Rect(
                safe.x if safe is not None else rect.x + self.ui(16),
                y,
                safe.width if safe is not None else rect.w - self.ui(32),
                row_h - self.ui(4),
            )
            selected = index == self.shop_cursor
            if selected:
                # Selected: gold-tinted plate with a soft glow.
                pygame.draw.rect(
                    self.screen,
                    self.shade(self.HUD_GOLD, -110),
                    row,
                    border_radius=self.ui(5),
                )
                glow = pygame.Surface(row.size, pygame.SRCALPHA)
                pygame.draw.rect(
                    glow,
                    (*self.HUD_GOLD, 40),
                    glow.get_rect(),
                    border_radius=self.ui(5),
                )
                self.screen.blit(glow, row)
                # Left marker strip.
                strip = pygame.Rect(
                    row.x, row.y + self.ui(3), self.ui(3), row.height - self.ui(6)
                )
                pygame.draw.rect(
                    self.screen, self.HUD_GOLD, strip, border_radius=self.ui(2)
                )
            else:
                pygame.draw.rect(
                    self.screen, self.HUD_STONE_SHADOW, row, border_radius=self.ui(5)
                )
            border = self.HUD_GOLD if selected else self.HUD_IRON
            pygame.draw.rect(
                self.screen,
                border,
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
            price_text = self.small_font.render(f"{price}g", True, self.HUD_GOLD)
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

    def draw_controls_menu(self) -> None:
        self.menus.draw_controls_menu()

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
