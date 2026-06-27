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


class RenderingBaseMixin:
    def draw(self) -> None:
        self.screen.fill((10, 10, 14))
        if self.state == "title":
            self.draw_title_menu()
            pygame.display.flip()
            self.sync_music()
            return
        if self.state == "options":
            self.draw_options_menu()
            pygame.display.flip()
            self.sync_music()
            return
        if self.state == "about":
            self.draw_about_screen()
            pygame.display.flip()
            self.sync_music()
            return
        if self.state == "archetype_select":
            self.draw_archetype_select()
            pygame.display.flip()
            self.sync_music()
            return
        if self.state == "confirm_exit":
            self.draw_exit_confirmation()
            pygame.display.flip()
            self.sync_music()
            return
        self.draw_dungeon()
        self.draw_world_objects()
        self.draw_ambient_depth_overlay()
        self.draw_darkness_overlay()
        self.draw_ui()
        if self.active_cutscene is not None:
            self.draw_quest_cutscene_overlay()
        elif self.story_intro_pending:
            self.draw_story_intro_overlay()
        if self.inventory_open:
            self.draw_inventory()
        if self.shop_open:
            self.draw_shop_overlay()
        if self.character_menu_open:
            self.draw_character_menu()
        if self.show_help:
            self.draw_help_overlay()
        if self.state != "playing":
            self.draw_state_overlay()
        self.draw_screen_flash()
        pygame.display.flip()
        self.sync_music()

    def shade(self, color: Color, amount: int) -> Color:
        return (
            max(0, min(255, color[0] + amount)),
            max(0, min(255, color[1] + amount)),
            max(0, min(255, color[2] + amount)),
        )

    def mix(self, a: Color, b: Color, ratio: float) -> Color:
        return (
            int(a[0] * (1.0 - ratio) + b[0] * ratio),
            int(a[1] * (1.0 - ratio) + b[1] * ratio),
            int(a[2] * (1.0 - ratio) + b[2] * ratio),
        )

    def ui(self, value: int) -> int:
        return value * self.ui_scale

    def hud_panel_height(self) -> int:
        _width, height = self.screen.get_size()
        desired = (
            self.font.get_height() + self.small_font.get_height() * 3 + self.ui(74)
        )
        minimum = min(self.ui(112), max(132, int(height * 0.30)))
        maximum = max(minimum, int(height * 0.38))
        return min(max(desired, minimum), maximum)

    def ellipsize_ui_text(
        self, text: str, font: pygame.font.Font, max_width: int
    ) -> str:
        max_width = max(1, max_width)
        if font.size(text)[0] <= max_width:
            return text
        suffix = "…"
        while text and font.size(text + suffix)[0] > max_width:
            text = text[:-1]
        return text + suffix if text else suffix

    def draw_ui_text(
        self,
        surface: pygame.Surface,
        text: str,
        font: pygame.font.Font,
        color: Color,
        rect: pygame.Rect,
        align: str = "left",
        valign: str = "top",
    ) -> None:
        rendered = font.render(
            self.ellipsize_ui_text(text, font, rect.width), True, color
        )
        if align == "center":
            x = rect.centerx - rendered.get_width() // 2
        elif align == "right":
            x = rect.right - rendered.get_width()
        else:
            x = rect.x
        if valign == "center":
            y = rect.centery - rendered.get_height() // 2
        elif valign == "bottom":
            y = rect.bottom - rendered.get_height()
        else:
            y = rect.y
        surface.blit(rendered, (x, y))

    def draw_translucent_panel(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        fill: tuple[int, int, int, int],
        border: tuple[int, int, int, int],
        radius: int | None = None,
        width: int | None = None,
    ) -> None:
        radius = self.ui(9) if radius is None else radius
        width = self.ui(1) if width is None else width
        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        panel_rect = panel.get_rect()
        pygame.draw.rect(panel, fill, panel_rect, border_radius=radius)
        pygame.draw.rect(panel, border, panel_rect, width, border_radius=radius)
        surface.blit(panel, rect)

    def wrap_ui_text(
        self, text: str, font: pygame.font.Font, max_width: int
    ) -> list[str]:
        lines: list[str] = []
        for paragraph in text.splitlines() or [""]:
            words = paragraph.split()
            if not words:
                lines.append("")
                continue
            current = self.ellipsize_ui_text(words[0], font, max_width)
            for word in words[1:]:
                candidate = f"{current} {word}"
                if font.size(candidate)[0] <= max_width:
                    current = candidate
                else:
                    lines.append(current)
                    current = self.ellipsize_ui_text(word, font, max_width)
            lines.append(current)
        return lines

