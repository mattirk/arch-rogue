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

"""Full-screen presentation for the cooperative 4.9.x story mini-games."""

from __future__ import annotations

import math

import pygame

from ..constants import SHARED_SIGIL_NAMES
from ..story import (
    GARDEN_MINI_GAME,
    MINI_GAME_INSTRUCTIONS,
    MINI_GAME_TIME_LIMITS,
    MINI_GAME_TITLES,
    SOUL_MINI_GAME,
    STORY_MINI_GAME,
    MiniGameState,
    preview_cell,
)

_KIND_COLORS = {
    STORY_MINI_GAME: ((120, 105, 190), (196, 179, 255)),
    GARDEN_MINI_GAME: ((72, 135, 94), (171, 229, 151)),
    SOUL_MINI_GAME: ((71, 126, 151), (156, 220, 226)),
}

_SOCKET_ASSETS = {
    STORY_MINI_GAME: "minigame.socket.story",
    GARDEN_MINI_GAME: "minigame.socket.garden",
    SOUL_MINI_GAME: "minigame.socket.soul",
}

_READY_GUIDES = {
    STORY_MINI_GAME: (
        "WATCH · REMEMBER · REPEAT",
        "Watch the runes glow. When the omen fades, choose the same runes "
        "in the same order.",
    ),
    GARDEN_MINI_GAME: (
        "CHASE THE LIGHT",
        "Touch only the glowing bloom before its light moves to another seal.",
    ),
    SOUL_MINI_GAME: (
        "FIND THE TWINS",
        "Turn two seals at a time. Matching glyphs stay open until every pair "
        "is reunited.",
    ),
}

_RESULT_COPY = {
    (STORY_MINI_GAME, "won"): "The page remembers your hands.",
    (STORY_MINI_GAME, "lost"): "The binding slips back into shadow.",
    (GARDEN_MINI_GAME, "won"): "The moonbloom wakes beneath both hands.",
    (GARDEN_MINI_GAME, "lost"): "The petals fold, waiting for another season.",
    (SOUL_MINI_GAME, "won"): "Every divided seal remembers its twin.",
    (SOUL_MINI_GAME, "lost"): "The mirrors cloud before the soul can answer.",
}


class RenderingMiniGameMixin:
    """Render one responsive, pointer-addressable modal mini-game board."""

    def draw_mini_game_overlay(self) -> None:
        state = getattr(self, "active_mini_game", None)
        if not isinstance(state, MiniGameState):
            self._mini_game_cell_rects = []
            self._mini_game_ready_rect = None
            return
        with self.fitted_ui_layout((960, 540)):
            self._draw_mini_game_overlay(state)

    def _draw_mini_game_overlay(self, state: MiniGameState) -> None:
        self._mini_game_cell_rects = []
        self._mini_game_ready_rect = None
        screen_rect = self.screen.get_rect()
        background = self.ui_asset_surface("cutscene.background", screen_rect.size)
        if background is not None:
            self.screen.blit(background, screen_rect)
        else:
            self.screen.fill((7, 7, 12))
            band = max(24, screen_rect.height // 12)
            for y in range(0, screen_rect.height, band):
                color = (10, 9, 17) if (y // band) % 2 else (13, 11, 20)
                pygame.draw.rect(
                    self.screen,
                    color,
                    (0, y, screen_rect.width, min(band, screen_rect.height - y)),
                )

        margin = max(12, min(screen_rect.width, screen_rect.height) // 30)
        panel = pygame.Rect(
            0,
            0,
            min(900, max(1, screen_rect.width - margin * 2)),
            min(500, max(1, screen_rect.height - margin * 2)),
        )
        panel.center = screen_rect.center
        panel_art = self.ui_asset_surface("menu.panel", panel.size)
        if panel_art is not None:
            self.screen.blit(panel_art, panel)
            content = self.ui_asset_content_rect("menu.panel", panel)
        else:
            self.draw_ornate_hud_panel(
                self.screen,
                panel,
                (15, 14, 22, 244),
                (112, 91, 60, 235),
                radius=max(8, min(panel.size) // 28),
                width=max(1, min(panel.size) // 180),
                studs=True,
            )
            content = None
        if content is None:
            inset_x = max(16, panel.width // 28)
            inset_y = max(14, panel.height // 24)
            content = panel.inflate(-inset_x * 2, -inset_y * 2)

        dark, bright = _KIND_COLORS.get(
            state.kind, ((104, 91, 129), (210, 196, 226))
        )
        title = MINI_GAME_TITLES.get(state.kind, "A Test in the Dark")
        instruction = MINI_GAME_INSTRUCTIONS.get(
            state.kind, "Choose before the light is gone."
        )
        title_h = max(self.heading_font.get_height(), 24)
        self.draw_ui_text(
            self.screen,
            title,
            self.heading_font,
            self.HUD_GOLD_BRIGHT,
            pygame.Rect(content.x, content.y, content.width, title_h),
            align="center",
            valign="center",
        )
        instruction_y = content.y + title_h + 1
        instruction_h = 0
        if state.phase != "ready":
            instruction_h = max(self.small_font.get_height(), 17)
            self.draw_ui_text(
                self.screen,
                instruction,
                self.small_font,
                self.HUD_BONE,
                pygame.Rect(
                    content.x,
                    instruction_y,
                    content.width,
                    instruction_h,
                ),
                align="center",
                valign="center",
            )

        status_y = instruction_y + instruction_h + max(3, content.height // 100)
        status_h = max(self.small_font.get_height(), 17)
        if state.phase == "ready":
            phase_text = ""
        elif state.phase == "preview":
            phase_text = "WATCH" if state.kind == STORY_MINI_GAME else "READY"
        elif state.phase == "result":
            phase_text = "COMPLETE"
        elif state.kind == STORY_MINI_GAME:
            phase_text = f"RUNE {min(state.step + 1, state.goal)} OF {state.goal}"
        elif state.kind == GARDEN_MINI_GAME:
            phase_text = "THE BLOOM IS WAKING"
        else:
            phase_text = "TURN TWO SEALS"
        self.draw_ui_text(
            self.screen,
            (
                f"READY  {len(state.ready_player_ids)}/"
                f"{max(1, len(state.required_player_ids))}"
                if state.phase == "ready"
                else f"BOUND  {state.score}/{state.goal}"
            ),
            self.small_font,
            bright,
            pygame.Rect(content.x, status_y, content.width // 3, status_h),
            valign="center",
        )
        self.draw_ui_text(
            self.screen,
            phase_text,
            self.small_font,
            self.HUD_PARCHMENT,
            pygame.Rect(
                content.x + content.width // 3,
                status_y,
                content.width // 3,
                status_h,
            ),
            align="center",
            valign="center",
        )
        timer_text = (
            f"{state.time_left:0.1f}s"
            if state.phase == "play"
            else (
                "WAITING"
                if state.phase == "ready"
                else f"MISSTEPS  {state.mistakes}"
            )
        )
        self.draw_ui_text(
            self.screen,
            timer_text,
            self.small_font,
            self.HUD_MUTED if state.phase != "play" else bright,
            pygame.Rect(
                content.right - content.width // 3,
                status_y,
                content.width // 3,
                status_h,
            ),
            align="right",
            valign="center",
        )

        bar_y = status_y + status_h + max(3, content.height // 110)
        bar_h = max(4, min(8, content.height // 55))
        bar = pygame.Rect(content.x, bar_y, content.width, bar_h)
        pygame.draw.rect(self.screen, (28, 25, 34), bar, border_radius=bar_h // 2)
        if state.phase == "ready":
            fraction = len(state.ready_player_ids) / max(
                1, len(state.required_player_ids)
            )
        elif state.phase == "play":
            limit = MINI_GAME_TIME_LIMITS.get(
                state.kind,
                max(0.1, state.time_left),
            )
            fraction = max(0.0, min(1.0, state.time_left / limit))
        elif state.phase == "preview":
            fraction = 1.0
        else:
            fraction = 0.0
        fill = bar.copy()
        fill.width = round(bar.width * fraction)
        if fill.width > 0:
            pygame.draw.rect(
                self.screen,
                bright if fraction > 0.22 else (205, 78, 70),
                fill,
                border_radius=bar_h // 2,
            )

        footer_h = max(self.tiny_font.get_height(), 14)
        board_top = bar.bottom + max(8, content.height // 45)
        board_bottom = content.bottom - footer_h - max(4, content.height // 90)
        board_area = pygame.Rect(
            content.x,
            board_top,
            content.width,
            max(1, board_bottom - board_top),
        )
        if state.phase == "ready":
            self._draw_mini_game_ready(state, board_area, dark, bright)
            return
        rects = self._mini_game_grid_rects(state, board_area)
        self._mini_game_cell_rects = [rect.copy() for rect in rects]
        cursor = int(getattr(self, "mini_game_cursor", 0))
        if rects:
            cursor %= len(rects)
            self.mini_game_cursor = cursor
        pulse = 0.5 + 0.5 * math.sin(float(getattr(self, "ui_elapsed", 0.0)) * 6.0)
        for index, rect in enumerate(rects):
            selected = (
                not getattr(self, "mobile_mode", False)
                and index == cursor
                and state.phase == "play"
            )
            self._draw_mini_game_cell(
                state,
                index,
                rect,
                dark,
                bright,
                selected=selected,
                pulse=pulse,
            )

        footer = self._mini_game_footer_text(state)
        self.draw_ui_text(
            self.screen,
            footer,
            self.tiny_font,
            self.HUD_MUTED,
            pygame.Rect(content.x, board_bottom, content.width, footer_h),
            align="center",
            valign="bottom",
        )
        if state.phase == "result":
            self._draw_mini_game_result(state, panel, bright)

    def _draw_mini_game_ready(
        self,
        state: MiniGameState,
        area: pygame.Rect,
        dark: tuple[int, int, int],
        bright: tuple[int, int, int],
    ) -> None:
        """Draw the untimed guide and its single explicit ready target."""

        card = pygame.Rect(
            0,
            0,
            max(1, min(650, area.width)),
            max(1, min(300, area.height)),
        )
        card.center = area.center
        self.draw_translucent_panel(
            self.screen,
            card,
            (10, 10, 16, 226),
            (*tuple(max(48, component * 3 // 4) for component in dark), 225),
            radius=max(10, card.height // 18),
            width=max(2, card.height // 110),
        )

        pad_x = max(18, card.width // 18)
        pad_y = max(10, card.height // 18)
        text_width = card.width - pad_x * 2
        guide_heading, guide_body = _READY_GUIDES.get(
            state.kind,
            ("READ THE OMEN", MINI_GAME_INSTRUCTIONS.get(state.kind, "")),
        )
        heading_h = max(self.small_font.get_height(), 18)
        self.draw_ui_text(
            self.screen,
            guide_heading,
            self.small_font,
            bright,
            pygame.Rect(card.x + pad_x, card.y + pad_y, text_width, heading_h),
            align="center",
            valign="center",
        )

        button_h = max(48, min(58, card.height // 4))
        button_w = min(360, max(220, card.width - pad_x * 4))
        button = pygame.Rect(0, 0, button_w, button_h)
        button.centerx = card.centerx
        button.bottom = card.bottom - pad_y
        self._mini_game_ready_rect = button.copy()

        required = list(state.required_player_ids) or [state.origin_player_id]
        ready = set(state.ready_player_ids)
        local_player_id = str(getattr(self, "local_player_id", "") or "p1")
        local_ready = local_player_id in ready
        partner_ready = any(
            player_id != local_player_id and player_id in ready
            for player_id in required
        )
        if len(required) > 1:
            if local_ready:
                readiness = "WAITING FOR YOUR PARTNER"
            elif partner_ready:
                readiness = "YOUR PARTNER IS READY"
            else:
                readiness = "BOTH DESCENDERS MUST BE READY"
        else:
            readiness = ""

        readiness_h = max(self.tiny_font.get_height(), 15) if readiness else 0
        readiness_rect = pygame.Rect(
            card.x + pad_x,
            button.y
            - readiness_h
            - (max(7, card.height // 32) if readiness else 0),
            text_width,
            readiness_h,
        )
        if readiness:
            self.draw_ui_text(
                self.screen,
                readiness,
                self.tiny_font,
                self.HUD_MUTED if local_ready else self.HUD_PARCHMENT,
                readiness_rect,
                align="center",
                valign="center",
            )

        body_top = card.y + pad_y + heading_h + max(7, card.height // 30)
        body_bottom = readiness_rect.y - max(5, card.height // 36)
        body_line_h = max(self.small_font.get_height() + 3, 19)
        body_lines = self.wrap_ui_text(guide_body, self.small_font, text_width)
        body_height = min(
            max(body_line_h, len(body_lines) * body_line_h),
            max(body_line_h, body_bottom - body_top),
        )
        body_y = body_top + max(0, (body_bottom - body_top - body_height) // 2)
        max_lines = max(1, (body_bottom - body_y) // body_line_h)
        for line in body_lines[:max_lines]:
            self.draw_ui_text(
                self.screen,
                line,
                self.small_font,
                self.HUD_BONE,
                pygame.Rect(card.x + pad_x, body_y, text_width, body_line_h),
                align="center",
                valign="center",
            )
            body_y += body_line_h

        button_fill = (
            tuple(max(15, component // 3) for component in dark)
            if local_ready
            else tuple(max(24, component // 2) for component in dark)
        )
        shadow = button.move(0, max(2, button.height // 16))
        self.draw_translucent_panel(
            self.screen,
            shadow,
            (3, 3, 6, 190),
            (3, 3, 6, 0),
            radius=max(9, button.height // 5),
            width=1,
        )
        button_art = self.ui_asset_surface(
            "menu.panel.action.accept",
            button.size,
        )
        if button_art is not None:
            if local_ready:
                button_art = self._cached_alpha_surface(button_art, 115)
            self.screen.blit(button_art, button)
        else:
            self.draw_translucent_panel(
                self.screen,
                button,
                (*button_fill, 245),
                (*bright, 235 if not local_ready else 115),
                radius=max(9, button.height // 5),
                width=max(2, button.height // 24),
            )
        if not local_ready:
            pulse = 0.80 + 0.12 * math.sin(
                float(getattr(self, "ui_elapsed", 0.0)) * 4.0
            )
            focus_color = tuple(
                max(0, min(255, round(component * pulse)))
                for component in bright
            )
            pygame.draw.rect(
                self.screen,
                focus_color,
                button.inflate(5, 5),
                max(2, button.height // 28),
                border_radius=max(10, button.height // 5 + 2),
            )

        button_label = "READY"
        label_font = self.font
        label_width = label_font.size(button_label)[0]
        glyph_size = max(20, min(30, button.height - 18))
        glyph = self.ui_asset_surface(
            "menu.glyph.action.accept",
            (glyph_size, glyph_size),
        )
        if glyph is not None and local_ready:
            glyph = self._cached_alpha_surface(glyph, 105)
        content_gap = max(5, button.height // 12) if glyph is not None else 0
        content_width = label_width + (
            glyph_size + content_gap if glyph is not None else 0
        )
        content_x = button.centerx - content_width // 2
        if glyph is not None:
            glyph_rect = glyph.get_rect(midleft=(content_x, button.centery))
            self.screen.blit(glyph, glyph_rect)
            content_x = glyph_rect.right + content_gap
        self.draw_ui_text(
            self.screen,
            button_label,
            label_font,
            self.HUD_GOLD_BRIGHT if not local_ready else self.HUD_MUTED,
            pygame.Rect(
                content_x,
                button.y,
                label_width,
                button.height,
            ),
            valign="center",
        )

    @staticmethod
    def _mini_game_grid_columns(state: MiniGameState) -> int:
        if state.kind == SOUL_MINI_GAME and len(state.board) > 6:
            return 4
        return 3

    def _mini_game_grid_rects(
        self, state: MiniGameState, area: pygame.Rect
    ) -> list[pygame.Rect]:
        count = len(state.board)
        if count <= 0:
            return []
        columns = self._mini_game_grid_columns(state)
        rows = max(1, math.ceil(count / columns))
        gap = max(6, min(16, area.width // 55, area.height // 24))
        available_w = max(1, area.width - gap * (columns - 1))
        available_h = max(1, area.height - gap * (rows - 1))
        size = max(1, min(142, available_w // columns, available_h // rows))
        grid_w = size * columns + gap * (columns - 1)
        grid_h = size * rows + gap * (rows - 1)
        origin_x = area.centerx - grid_w // 2
        origin_y = area.centery - grid_h // 2
        return [
            pygame.Rect(
                origin_x + (index % columns) * (size + gap),
                origin_y + (index // columns) * (size + gap),
                size,
                size,
            )
            for index in range(count)
        ]

    def _draw_mini_game_cell(
        self,
        state: MiniGameState,
        index: int,
        rect: pygame.Rect,
        dark: tuple[int, int, int],
        bright: tuple[int, int, int],
        *,
        selected: bool,
        pulse: float,
    ) -> None:
        preview = preview_cell(state)
        revealed = index in state.revealed
        matched = index in state.matched
        hidden_soul = state.kind == SOUL_MINI_GAME and not (revealed or matched)
        lit = (
            (state.kind == STORY_MINI_GAME and index == preview)
            or (
                state.kind == GARDEN_MINI_GAME
                and state.phase == "play"
                and index == state.active_cell
            )
            or revealed
        )
        feedback = state.feedback_time > 0.0 and index == state.last_cell
        feedback_color = (91, 203, 120) if state.last_correct else (217, 74, 72)

        radius = max(7, rect.width // 10)
        base = (
            tuple(min(255, component + 24) for component in dark)
            if lit
            else tuple(max(8, component // 3) for component in dark)
        )
        if matched:
            base = tuple(max(10, component // 2) for component in dark)

        socket_key = _SOCKET_ASSETS.get(state.kind, "")
        socket = (
            self.ui_asset_surface(socket_key, rect.size) if socket_key else None
        )
        socket_well = (
            self.ui_asset_content_rect(socket_key, rect)
            if socket is not None
            else None
        )
        authored_socket = socket is not None and socket_well is not None

        pygame.draw.rect(self.screen, (7, 7, 11), rect, border_radius=radius)
        if authored_socket:
            assert socket is not None
            assert socket_well is not None
            # PixelLab-authored frames have a transparent center aperture. Keep
            # all state color live underneath it, so one static sprite remains
            # legible for preview, success, failure, and co-op updates.
            well_fill = socket_well.inflate(
                max(4, rect.width // 14),
                max(4, rect.height // 14),
            )
            pygame.draw.rect(
                self.screen,
                base,
                well_fill,
                border_radius=max(5, radius - 2),
            )
            socket_alpha = 144 if matched else 255 if lit else 208
            socket_art = (
                socket
                if socket_alpha == 255
                else self._cached_alpha_surface(socket, socket_alpha)
            )
            self.screen.blit(socket_art, rect)
            inner = socket_well
        else:
            # Missing optional art and legacy-graphics mode retain the complete
            # procedural cell, including its original padding and silhouette.
            inner = rect.inflate(
                -max(4, rect.width // 18),
                -max(4, rect.height // 18),
            )
            pygame.draw.rect(
                self.screen,
                base,
                inner,
                border_radius=max(5, radius - 2),
            )

        border_color = feedback_color if feedback else bright if lit else (79, 71, 86)
        border_width = max(2, rect.width // 28)
        pygame.draw.rect(
            self.screen,
            border_color,
            rect,
            border_width,
            border_radius=radius,
        )
        if selected:
            selection = rect.inflate(max(5, rect.width // 16), max(5, rect.height // 16))
            pygame.draw.rect(
                self.screen,
                self.HUD_GOLD_BRIGHT,
                selection,
                max(2, rect.width // 32),
                border_radius=radius + max(2, rect.width // 20),
            )
        if lit and state.kind == GARDEN_MINI_GAME and state.phase == "play":
            ring = inner.inflate(
                -round(inner.width * (0.18 + pulse * 0.10)),
                -round(inner.height * (0.18 + pulse * 0.10)),
            )
            pygame.draw.ellipse(
                self.screen,
                bright,
                ring,
                max(2, rect.width // 30),
            )

        if authored_socket:
            glyph_box = inner.inflate(
                -max(6, inner.width // 10),
                -max(6, inner.height // 10),
            )
        else:
            glyph_box = inner.inflate(
                -max(9, inner.width // 5),
                -max(9, inner.height // 5),
            )
        if hidden_soul:
            self._draw_mini_game_seal_back(glyph_box, bright)
        else:
            name = state.board[index]
            glyph = self.ui_asset_surface(f"menu.glyph.sigil.{name}", glyph_box.size)
            if glyph is not None:
                alpha = 130 if matched else 255 if lit or state.phase == "play" else 178
                if alpha < 255:
                    glyph = self._cached_alpha_surface(glyph, alpha)
                self.screen.blit(glyph, glyph.get_rect(center=glyph_box.center))
            else:
                color = (
                    tuple(max(92, component * 3 // 4) for component in bright)
                    if matched
                    else bright
                )
                self._draw_mini_game_fallback_glyph(glyph_box, name, color)

        number_rect = pygame.Rect(
            rect.x + max(4, rect.width // 14),
            rect.y + max(2, rect.height // 18),
            max(14, rect.width // 4),
            max(14, rect.height // 4),
        )
        self.draw_ui_text(
            self.screen,
            str(index + 1),
            self.tiny_font,
            self.HUD_MUTED if not lit else self.HUD_GOLD_BRIGHT,
            number_rect,
        )

    def _draw_mini_game_seal_back(
        self, rect: pygame.Rect, color: tuple[int, int, int]
    ) -> None:
        width = max(2, rect.width // 14)
        pygame.draw.polygon(
            self.screen,
            color,
            (
                (rect.centerx, rect.y),
                (rect.right, rect.centery),
                (rect.centerx, rect.bottom),
                (rect.x, rect.centery),
            ),
            width,
        )
        radius = max(3, min(rect.width, rect.height) // 7)
        pygame.draw.circle(self.screen, color, rect.center, radius, width)

    def _draw_mini_game_fallback_glyph(
        self,
        rect: pygame.Rect,
        name: str,
        color: tuple[int, int, int],
    ) -> None:
        try:
            shape = SHARED_SIGIL_NAMES.index(name) % 6
        except ValueError:
            shape = 0
        width = max(2, min(rect.width, rect.height) // 11)
        inset = max(2, min(rect.width, rect.height) // 12)
        box = rect.inflate(-inset * 2, -inset * 2)
        if shape == 0:
            pygame.draw.ellipse(self.screen, color, box, width)
            pygame.draw.line(
                self.screen, color, box.midleft, box.midright, width
            )
        elif shape == 1:
            pygame.draw.polygon(
                self.screen,
                color,
                (box.midtop, box.midright, box.midbottom, box.midleft),
                width,
            )
            pygame.draw.circle(self.screen, color, box.center, width)
        elif shape == 2:
            pygame.draw.line(self.screen, color, box.topleft, box.bottomright, width)
            pygame.draw.line(self.screen, color, box.topright, box.bottomleft, width)
            pygame.draw.circle(self.screen, color, box.center, box.width // 3, width)
        elif shape == 3:
            pygame.draw.polygon(
                self.screen,
                color,
                (box.midtop, box.bottomright, box.bottomleft),
                width,
            )
            pygame.draw.line(self.screen, color, box.midtop, box.midbottom, width)
        elif shape == 4:
            pygame.draw.rect(
                self.screen,
                color,
                box.inflate(-box.width // 5, 0),
                width,
                border_radius=max(2, box.width // 8),
            )
            pygame.draw.line(self.screen, color, box.midleft, box.midright, width)
        else:
            half = max(3, box.width // 3)
            pygame.draw.circle(
                self.screen, color, (box.centerx - half // 2, box.centery), half, width
            )
            pygame.draw.circle(
                self.screen, color, (box.centerx + half // 2, box.centery), half, width
            )

    def _mini_game_footer_text(self, state: MiniGameState) -> str:
        if state.phase == "preview":
            return "The board will answer when the omen fades."
        if state.phase == "result":
            return "Returning to the tale…"
        contributions = sorted(
            (
                (player_id, value)
                for player_id, value in state.contributions.items()
                if value > 0
            ),
            key=lambda item: item[0],
        )
        if len(contributions) >= 2:
            joined = "  ·  ".join(
                f"{player_id}: {value}" for player_id, value in contributions[:2]
            )
            return f"Shared binding  ·  {joined}"
        if getattr(self, "mobile_mode", False):
            return "Tap a seal."
        return "Arrows move  ·  Enter selects  ·  Number keys choose directly"

    def _draw_mini_game_result(
        self,
        state: MiniGameState,
        panel: pygame.Rect,
        bright: tuple[int, int, int],
    ) -> None:
        card = pygame.Rect(
            0,
            0,
            min(max(280, panel.width * 2 // 3), panel.width - 30),
            min(max(120, panel.height // 3), panel.height - 30),
        )
        card.center = panel.center
        won = state.outcome == "won"
        border = (104, 207, 131, 245) if won else (202, 79, 75, 245)
        self.draw_translucent_panel(
            self.screen,
            card,
            (10, 10, 16, 242),
            border,
            radius=max(10, card.height // 10),
            width=max(2, card.height // 55),
        )
        heading = "THE OMEN HOLDS" if won else "THE OMEN BREAKS"
        self.draw_ui_text(
            self.screen,
            heading,
            self.heading_font,
            bright if won else (234, 135, 128),
            pygame.Rect(card.x + 16, card.y + 12, card.width - 32, card.height // 3),
            align="center",
            valign="center",
        )
        copy = _RESULT_COPY.get(
            (state.kind, state.outcome),
            "The dungeon keeps the answer.",
        )
        self.draw_ui_text(
            self.screen,
            copy,
            self.small_font,
            self.HUD_BONE,
            pygame.Rect(
                card.x + 18,
                card.y + card.height // 3,
                card.width - 36,
                card.height // 3,
            ),
            align="center",
            valign="center",
        )
        self.draw_ui_text(
            self.screen,
            f"{state.score}/{state.goal} bound  ·  {state.mistakes} missteps",
            self.tiny_font,
            self.HUD_MUTED,
            pygame.Rect(
                card.x + 18,
                card.bottom - card.height // 3,
                card.width - 36,
                card.height // 3 - 8,
            ),
            align="center",
            valign="center",
        )


__all__ = ["RenderingMiniGameMixin"]
