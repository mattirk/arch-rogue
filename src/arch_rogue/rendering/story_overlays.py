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
    AmbientEffectAsset,
    CurtainAsset,
    CutsceneActorAsset,
    SpriteAnimationFrameAsset,
    StageAsset,
    StageLightAsset,
    StagePropAsset,
    format_asset_text,
)


class RenderingStoryOverlayMixin:
    def draw_story_panel(self) -> None:
        self._story_panel_rect: pygame.Rect | None = None
        if not getattr(self, "quest_info_visible", True):
            return
        lines = self.story_panel_lines()
        if not lines:
            return
        width, height = self.screen.get_size()
        bottom_panel_top = height - self.hud_panel_height()
        x = self.ui(18)
        y = self.ui(104)
        panel_w = min(width - self.ui(36), self.ui(620))
        max_h = min(self.ui(190), bottom_panel_top - y - self.ui(16))
        # When a boss bar is on screen (anchored above the bottom HUD panel),
        # cap the story panel so it never overlaps the boss bar cluster.
        boss_top = self.boss_bar_top()
        if boss_top is not None:
            max_h = min(max_h, max(0, boss_top - y - self.ui(8)))
        prompt_rect = getattr(self, "_interaction_prompt_rect", None)
        if (
            isinstance(prompt_rect, pygame.Rect)
            and x < prompt_rect.right
            and x + panel_w > prompt_rect.x
        ):
            max_h = min(max_h, max(0, prompt_rect.y - y - self.ui(8)))
        if panel_w <= self.ui(220) or max_h < self.ui(84):
            return
        accent = self.story_state.accent if self.story_state else self.theme.accent
        rect = pygame.Rect(x, y, panel_w, max_h)
        self._story_panel_rect = rect.copy()
        surface = pygame.Surface(rect.size, pygame.SRCALPHA)
        self.draw_ornate_hud_panel(
            surface,
            surface.get_rect(),
            (10, 9, 13, 220),
            (*accent, 165),
            radius=self.ui(9),
        )
        pad = self.ui(12)
        content = self.ui_asset_content_rect("hud.panel", surface.get_rect())
        content = (
            content.inflate(-self.ui(3) * 2, -self.ui(1) * 2)
            if content is not None
            else surface.get_rect().inflate(-pad * 2, -pad * 2)
        )
        title = lines[0]
        title_surface = self.small_font.render(
            self.ellipsize_ui_text(title, self.small_font, content.width),
            True,
            (244, 232, 214),
        )
        surface.blit(title_surface, content.topleft)
        divider_y = content.y + title_surface.get_height() + self.ui(4)
        self.draw_hud_divider(
            surface,
            content.x,
            divider_y,
            content.right,
            accent,
        )
        cursor_y = divider_y + self.ui(5)
        line_h = max(self.small_font.get_height() + self.ui(3), self.ui(18))
        max_lines = max(2, (content.bottom - cursor_y) // line_h)
        rendered = 0
        for raw_line in lines[1:]:
            color = (
                (205, 185, 225)
                if raw_line.startswith("Story forces:")
                else (210, 205, 192)
            )
            if raw_line.startswith("Depth ") or raw_line.startswith("Outcome:"):
                color = (238, 218, 164)
            for wrapped in self.wrap_ui_text(
                raw_line, self.small_font, content.width
            ):
                if rendered >= max_lines:
                    ellipsis = self.small_font.render("…", True, (170, 165, 155))
                    surface.blit(ellipsis, (content.x, cursor_y))
                    self.screen.blit(surface, rect)
                    return
                text = self.small_font.render(wrapped, True, color)
                surface.blit(text, (content.x, cursor_y))
                cursor_y += line_h
                rendered += 1
        self.screen.blit(surface, rect)

    def cutscene_response_text_width(self, choice_width: int) -> int:
        key_size = self.ui(36)
        return max(1, choice_width - self.ui(7) - key_size - self.ui(9) - self.ui(8))

    def cutscene_response_lines(
        self, label: str, detail: str, text_width: int
    ) -> tuple[list[str], list[str]]:
        label_lines = self.wrap_ui_text(label, self.small_font, text_width) or [""]
        detail_lines = (
            self.wrap_ui_text(detail, self.tiny_font, text_width) if detail else []
        )
        return label_lines, detail_lines

    def cutscene_response_height(
        self, label: str, detail: str, choice_width: int
    ) -> int:
        text_width = self.cutscene_response_text_width(choice_width)
        label_lines, detail_lines = self.cutscene_response_lines(
            label, detail, text_width
        )
        text_h = len(label_lines) * self.small_font.get_height()
        if detail_lines:
            text_h += self.ui(3) + len(detail_lines) * self.tiny_font.get_height()
        return max(self.ui(44), text_h + self.ui(16))

    def cutscene_response_rects(
        self,
        entries: list[tuple[str, str]],
        x: int,
        y: int,
        width: int,
        gap: int,
    ) -> list[pygame.Rect]:
        rects: list[pygame.Rect] = []
        cursor_y = y
        for label, detail in entries:
            rect_h = self.cutscene_response_height(label, detail, width)
            rects.append(pygame.Rect(x, cursor_y, width, rect_h))
            cursor_y += rect_h + gap
        return rects

    def draw_cutscene_response_text(
        self,
        surface: pygame.Surface,
        label: str,
        detail: str,
        text_rect: pygame.Rect,
    ) -> None:
        label_lines, detail_lines = self.cutscene_response_lines(
            label, detail, text_rect.width
        )
        cursor_y = text_rect.y
        for line in label_lines:
            self.draw_ui_text(
                surface,
                line,
                self.small_font,
                (246, 235, 210),
                pygame.Rect(
                    text_rect.x, cursor_y, text_rect.width, self.small_font.get_height()
                ),
            )
            cursor_y += self.small_font.get_height()
        if detail_lines:
            cursor_y += self.ui(3)
        for line in detail_lines:
            self.draw_ui_text(
                surface,
                line,
                self.tiny_font,
                (184, 178, 168),
                pygame.Rect(
                    text_rect.x, cursor_y, text_rect.width, self.tiny_font.get_height()
                ),
            )
            cursor_y += self.tiny_font.get_height()

    def draw_quest_cutscene_overlay(self) -> None:
        with self.fitted_ui_layout((960, 540)):
            self._draw_quest_cutscene_overlay_fitted()

    def _draw_quest_cutscene_overlay_fitted(self) -> None:
        asset = self.active_cutscene_asset()
        node = self.active_cutscene_node()
        if asset is None or node is None:
            return
        width, height = self.screen.get_size()
        background = self.ui_asset_surface("cutscene.background", (width, height))
        self._cutscene_background_asset_used = background is not None
        if background is not None:
            self.screen.blit(background, (0, 0))
            dim = pygame.Surface((width, height), pygame.SRCALPHA)
            dim.fill((0, 0, 0, 118))
            self.screen.blit(dim, (0, 0))
        else:
            self.screen.fill((0, 0, 0))

        accent = self.story_state.accent if self.story_state else self.theme.accent
        panel_margin_x = max(self.ui(28), 28)
        panel_margin_y = max(self.ui(20), 20)
        panel_w = min(width - panel_margin_x * 2, self.ui(900))
        panel_h = min(height - panel_margin_y * 2, self.ui(600))
        if panel_w < 300 or panel_h < 260:
            return
        rect = pygame.Rect(
            (width - panel_w) // 2,
            (height - panel_h) // 2,
            panel_w,
            panel_h,
        )
        surface = pygame.Surface(rect.size, pygame.SRCALPHA)
        panel_key = (
            "menu.panel.compact"
            if panel_w * 10 <= panel_h * 17
            else "menu.panel"
        )
        panel_asset = self.ui_asset_surface(panel_key, rect.size)
        if panel_asset is None and panel_key != "menu.panel":
            panel_key = "menu.panel"
            panel_asset = self.ui_asset_surface(panel_key, rect.size)
        panel_inner = (
            self.ui_asset_content_rect(panel_key, surface.get_rect())
            if panel_asset is not None
            else None
        )
        if panel_asset is not None and panel_inner is not None:
            surface.blit(panel_asset, (0, 0))
            inner = panel_inner.inflate(-self.ui(4) * 2, -self.ui(3) * 2)
            self._cutscene_panel_asset_used = True
        else:
            self.draw_translucent_panel(
                surface,
                surface.get_rect(),
                (10, 8, 14, 248),
                (*accent, 222),
                radius=self.ui(14),
                width=self.ui(2),
            )
            pad = max(self.ui(14), 18)
            inner = surface.get_rect().inflate(-pad * 2, -pad * 2)
            self._cutscene_panel_asset_used = False

        self._cutscene_panel_rect = rect.copy()
        self._cutscene_content_rect = inner.move(rect.topleft)
        title_text = asset.title
        if self.story_intro_pending:
            title_text = f"{asset.title} · Depth {self.current_depth}/{DUNGEON_DEPTH}"
        header_h = max(self.font.get_height(), self.small_font.get_height()) + self.ui(
            8
        )
        header_meta = node.id.replace("_", " ").title()
        meta_w = min(
            self.small_font.size(header_meta)[0] + self.ui(8),
            max(self.ui(96), inner.width // 3),
        )
        meta_x = inner.right - meta_w
        title_rect = pygame.Rect(
            inner.x,
            inner.y,
            max(1, meta_x - inner.x - self.ui(10)),
            self.font.get_height(),
        )
        meta_rect = pygame.Rect(
            meta_x,
            inner.y + (self.font.get_height() - self.small_font.get_height()) // 2,
            meta_w,
            self.small_font.get_height(),
        )
        self.draw_ui_text(surface, title_text, self.font, accent, title_rect)
        self.draw_ui_text(
            surface,
            header_meta,
            self.small_font,
            (196, 188, 204),
            meta_rect,
            align="right",
        )

        narration_complete = self.active_cutscene_narration_complete()
        choices = self.active_cutscene_choices()
        choices_to_draw = choices[: min(9, len(choices))] if narration_complete else []
        choice_gap = max(self.ui(4), 6)
        choice_w = inner.width
        footer_h = self.small_font.get_height()
        choice_entries = [(choice.label, choice.detail) for choice in choices_to_draw]
        choice_heights = [
            self.cutscene_response_height(label, detail, choice_w)
            for label, detail in choice_entries
        ]
        choices_block_h = (
            sum(choice_heights) + max(0, len(choice_heights) - 1) * choice_gap
        )
        choices_start = (
            inner.bottom - footer_h - self.ui(10) - choices_block_h
        )

        progress_h = max(self.ui(3), 3)
        line_h = max(self.small_font.get_height() + self.ui(3), self.ui(18))
        narrator_content_min_h = (
            self.small_font.get_height()
            + self.ui(5)
            + progress_h
            + self.ui(8)
            + line_h * 2
        )
        narrator_frame_min_h = narrator_content_min_h + self.ui(20)
        stage_top = inner.y + header_h + self.ui(10)
        available_for_stage = (
            choices_start
            - self.ui(8)
            - narrator_frame_min_h
            - self.ui(10)
            - stage_top
        )
        stage_h = max(
            self.ui(74),
            min(int(inner.height * 0.34), available_for_stage),
        )
        stage_rect = pygame.Rect(
            inner.x,
            stage_top,
            inner.width,
            stage_h,
        )
        self._cutscene_stage_rect = stage_rect.move(rect.topleft)
        previous_clip = surface.get_clip()
        surface.set_clip(stage_rect)
        try:
            self.draw_cutscene_stage(surface, stage_rect, node.animation, accent)
        finally:
            surface.set_clip(previous_clip)

        card_top = stage_rect.bottom + self.ui(10)
        card_bottom = choices_start - self.ui(8)
        if card_bottom - card_top < narrator_frame_min_h:
            card_top = card_bottom - narrator_frame_min_h
        speaker = self.active_cutscene_speaker_name()
        # Polished narrator card: a parchment panel with an ornate header,
        # a speaker label, a gilded progress rule, and the scrolling text.
        card_rect = pygame.Rect(
            inner.x,
            card_top,
            inner.width,
            max(1, card_bottom - card_top),
        )
        card = pygame.Surface(card_rect.size, pygame.SRCALPHA)
        self.draw_ornate_hud_panel(
            card,
            card.get_rect(),
            (24, 18, 28, 235),
            (*self.shade(accent, -30), 180),
            radius=self.ui(8),
            width=self.ui(1),
        )
        card_safe = self.ui_asset_content_rect("hud.panel", card.get_rect())
        if card_safe is None:
            # Procedural fallback retains its original parchment inner trim.
            card_inner = card.get_rect().inflate(-self.ui(6), -self.ui(6))
            pygame.draw.rect(
                card,
                (*self.HUD_GOLD, 90),
                card_inner,
                max(1, self.ui(1)),
                border_radius=max(1, self.ui(6)),
            )
            narrator_rect = card_inner.move(card_rect.topleft).inflate(
                -self.ui(3) * 2, -self.ui(1) * 2
            )
        else:
            narrator_rect = card_safe.move(card_rect.topleft).inflate(
                -self.ui(3) * 2, -self.ui(1) * 2
            )
        surface.blit(card, card_rect)
        self._cutscene_narrator_rect = narrator_rect.move(rect.topleft)

        y = narrator_rect.y
        text_bottom = narrator_rect.bottom
        speaker_rect = pygame.Rect(
            narrator_rect.x,
            y,
            narrator_rect.width,
            self.small_font.get_height(),
        )
        # Speaker label with a small accent dot like a stage bill.
        speaker_color = (246, 235, 210)
        pygame.draw.circle(
            surface,
            (*accent, 220),
            (speaker_rect.x + self.ui(3), speaker_rect.centery),
            self.ui(2),
        )
        self.draw_ui_text(
            surface,
            speaker.upper(),
            self.small_font,
            speaker_color,
            pygame.Rect(
                speaker_rect.x + self.ui(10),
                y,
                max(1, speaker_rect.width - self.ui(10)),
                self.small_font.get_height(),
            ),
        )
        speaker_w = min(self.small_font.size(speaker.upper())[0], speaker_rect.width)
        line_y = y + self.small_font.get_height() // 2
        pygame.draw.line(
            surface,
            (*self.HUD_GOLD, 140),
            (speaker_rect.x + self.ui(10) + speaker_w + self.ui(8), line_y),
            (speaker_rect.right, line_y),
            self.ui(1),
        )
        # Center diamond ornament on the rule.
        rule_cx = (
            speaker_rect.x
            + self.ui(10)
            + speaker_w
            + self.ui(8)
            + speaker_rect.right
        ) // 2
        pygame.draw.polygon(
            surface,
            (*self.HUD_GOLD, 180),
            [
                (rule_cx, line_y - self.ui(2)),
                (rule_cx + self.ui(2), line_y),
                (rule_cx, line_y + self.ui(2)),
                (rule_cx - self.ui(2), line_y),
            ],
        )
        y += self.small_font.get_height() + self.ui(5)
        progress = self.active_cutscene_narration_progress()
        progress_rect = pygame.Rect(
            narrator_rect.x, y, narrator_rect.width, max(self.ui(3), 3)
        )
        pygame.draw.rect(
            surface, (33, 25, 43, 210), progress_rect, border_radius=self.ui(2)
        )
        pygame.draw.rect(
            surface,
            (*accent, 170),
            (
                progress_rect.x,
                progress_rect.y,
                int(progress_rect.width * progress),
                progress_rect.height,
            ),
            border_radius=self.ui(2),
        )
        # Glowing leading edge on the progress bar while narrating.
        if not narration_complete and progress > 0:
            edge_x = progress_rect.x + int(progress_rect.width * progress)
            edge = pygame.Surface((self.ui(6), self.ui(6)), pygame.SRCALPHA)
            pygame.draw.circle(
                edge, (*self.shade(accent, 60), 200), edge.get_rect().center, self.ui(3)
            )
            surface.blit(edge, edge.get_rect(center=(edge_x, progress_rect.centery)))
        y += progress_rect.height + self.ui(8)

        line_h = max(self.small_font.get_height() + self.ui(3), self.ui(18))
        body_lines: list[str] = []
        visible_text = self.active_cutscene_visible_text()
        if not visible_text:
            visible_text = " "
        for paragraph in visible_text.splitlines() or [""]:
            body_lines.extend(
                self.wrap_ui_text(paragraph, self.small_font, narrator_rect.width)
            )
        if not narration_complete and body_lines:
            # Blinking quill caret at the end of the spoken line.
            if int(self.elapsed * 2.4) % 2 == 0:
                body_lines[-1] = f"{body_lines[-1]} \u2588"
        max_body_lines = max(0, (text_bottom - y) // line_h)
        omitted_lines = max(0, len(body_lines) - max_body_lines)
        visible_lines = body_lines[-max_body_lines:] if max_body_lines else []
        if omitted_lines and visible_lines:
            visible_lines[0] = "\u2026 " + visible_lines[0]
        for index, text_line in enumerate(visible_lines):
            color = (228, 220, 204)
            is_current_line = index == len(visible_lines) - 1 and not narration_complete
            if index == 0 and self.story_intro_pending and not omitted_lines:
                color = (238, 218, 164)
            elif is_current_line:
                color = self.mix((238, 218, 164), accent, 0.22)
            self.draw_ui_text(
                surface,
                text_line,
                self.small_font,
                color,
                pygame.Rect(narrator_rect.x, y, narrator_rect.width, line_h),
            )
            y += line_h

        choice_rects = self.cutscene_response_rects(
            choice_entries, inner.x, choices_start, choice_w, choice_gap
        )
        self._cutscene_choice_rects = [
            choice_rect.move(rect.topleft) for choice_rect in choice_rects
        ]
        for index, (choice, choice_rect) in enumerate(
            zip(choices_to_draw, choice_rects)
        ):
            choice_color = self.cutscene_choice_color(choice.choice_key, accent)
            is_selected = index == getattr(self, "cutscene_cursor", 0)
            pygame.draw.rect(
                surface,
                (34, 25, 45, 248) if is_selected else (24, 19, 31, 240),
                choice_rect,
                border_radius=self.ui(9),
            )
            if is_selected:
                glow = pygame.Surface(choice_rect.size, pygame.SRCALPHA)
                pygame.draw.rect(
                    glow,
                    (*choice_color, 42),
                    glow.get_rect(),
                    border_radius=self.ui(9),
                )
                surface.blit(glow, choice_rect)
            pygame.draw.rect(
                surface,
                (*choice_color, 235 if is_selected else 170),
                choice_rect,
                max(self.ui(2), 2) if is_selected else self.ui(1),
                border_radius=self.ui(9),
            )
            key_size = min(self.ui(36), choice_rect.height - self.ui(12))
            key_rect = pygame.Rect(
                choice_rect.x + self.ui(7),
                choice_rect.y + (choice_rect.height - key_size) // 2,
                key_size,
                key_size,
            )
            pygame.draw.rect(
                surface,
                (*self.shade(choice_color, -58), 238),
                key_rect,
                border_radius=self.ui(7),
            )
            self.draw_cutscene_choice_glyph(
                surface,
                key_rect.center,
                choice.choice_key,
                max(self.ui(7), key_size // 3),
                alpha=96,
            )
            self.draw_ui_text(
                surface,
                str(index + 1),
                self.font,
                choice_color,
                key_rect,
                align="center",
                valign="center",
            )
            text_x = key_rect.right + self.ui(9)
            text_rect = pygame.Rect(
                text_x,
                choice_rect.y + self.ui(7),
                max(1, choice_rect.right - text_x - self.ui(8)),
                choice_rect.height - self.ui(14),
            )
            self.draw_cutscene_response_text(
                surface, choice.label, choice.detail, text_rect
            )

        footer_text = (
            "Narrator speaking… Enter/E/Space or gamepad A reveals the full line."
            if not narration_complete
            else (
                "Press 1-3 or D-pad + A to choose. Gamepad B skips/closes."
                if len(choices_to_draw) >= 3
                else "Enter/E or gamepad A advances. Esc/B closes non-blocking dialogue."
            )
        )
        if self.story_intro_pending and narration_complete:
            footer_text = (
                "Choose 1-3 or D-pad + A to bind the guest relic and begin this level."
            )
        self.draw_ui_text(
            surface,
            footer_text,
            self.small_font,
            (205, 185, 225),
            pygame.Rect(inner.x, inner.bottom - footer_h, inner.width, footer_h),
        )
        self.screen.blit(surface, rect)

    # ------------------------------------------------------------------
    # Milestone 3.4 cutscene stage — "cursed theater" overhaul
    #
    # The stage is a single cohesive dark-fantasy set rendered entirely
    # inside ``stage_rect`` (panel-surface coordinates are offset by
    # ``stage_rect.topleft`` everywhere, so nothing leaks onto the title
    # or narrator card). The look is worn stone, iron, and dusty
    # accent-tinted tapestry — no bright velvet or gold marble — so it
    # matches the dungeon HUD palette. Static layers (back wall, floor,
    # proscenium frame) are cached per (asset, size, accent); only the
    # animated overlays (curtain open, lights, ambient motes, spectral
    # flames) are redrawn each frame.
    #
    # Curtains start CLOSED and pull open as the narrator speaks, driven
    # by ``active_cutscene_narration_progress()``. Once open they stay
    # gathered at the sides, framing the scene instead of covering it.

    _STAGE_CACHE: dict[tuple, pygame.Surface] = {}

    STAGE_STONE = (54, 49, 58)
    STAGE_STONE_DARK = (28, 25, 32)
    STAGE_STONE_LIGHT = (78, 72, 84)
    STAGE_IRON = (74, 70, 82)
    STAGE_IRON_LIGHT = (118, 110, 128)
    STAGE_IRON_DARK = (32, 30, 38)
    STAGE_TAPESTRY = (60, 36, 52)
    STAGE_TAPESTRY_DARK = (32, 18, 30)
    STAGE_FLAME = (208, 138, 74)
    STAGE_FLAME_CORE = (244, 212, 156)
    # Stage actors move slowly and gently so the scene reads as a measured
    # tableau rather than a fidgeting crowd.
    STAGE_ACTOR_TIME_SCALE = 0.45
    STAGE_ACTOR_MOVE_DAMP = 0.6

    # Stage depth / sizing (milestone 3.11). The stage floor begins at this
    # normalized y (matches ``draw_stage_floor``). Actors are scaled by a
    # perspective curve: figures near the back wall are smaller, figures near
    # the front of the stage are larger, so the set reads with real depth
    # instead of a flat row of equally-sized cutouts.
    STAGE_FLOOR_TOP = 0.62
    STAGE_BACK_SCALE = 0.62
    STAGE_FRONT_SCALE = 1.18
    STAGE_ACTOR_HEIGHT_FRAC = 0.40

    # Player vs antagonist duel cycle (milestone 3.11). When a cutscene casts
    # both a ``player`` and an ``antagonist`` actor, they run at each other,
    # clash in the middle, retreat to their marks, pause, and repeat. Phases
    # are expressed as fractions of the loop period so the choreography stays
    # data-independent and allocation-free.
    STAGE_DUEL_PERIOD = 3.6
    STAGE_DUEL_PHASE_APPROACH = 0.30
    STAGE_DUEL_PHASE_CLASH = 0.12
    STAGE_DUEL_PHASE_RETREAT = 0.30
    STAGE_DUEL_GAP = 0.045
    STAGE_DUEL_ANTAGONIST_ALPHA = 0.88
    # Obstacle avoidance: a center-stage prop such as the altar blocks the
    # direct duel path. The duelers route around it, passing to opposite sides
    # and clashing just in front of it, so the altar reads as solid and
    # unpassable instead of something they walk through.
    STAGE_DUEL_OBSTACLE_CLEAR = 0.09
    STAGE_DUEL_DETOUR_FORWARD = 0.07
    STAGE_DUEL_DETOUR_MAX_Y = 0.92

    def _stage_cache_key(self, asset_id, layer, size, accent, extra=()):
        return (asset_id, layer, size, accent, extra)

    def _cached_stage_layer(self, key, size, painter):
        cached = self._STAGE_CACHE.get(key)
        if cached is not None and cached.get_size() == size:
            return cached
        surface = pygame.Surface(size, pygame.SRCALPHA)
        painter(surface)
        self._STAGE_CACHE[key] = surface
        return surface

    def stage_role_color(self, role, accent):
        role = role.lower()
        if role in ("accent", "spot", "tint"):
            return accent
        if role == "player":
            return (226, 222, 205)
        if role == "danger":
            return (235, 95, 84)
        if role == "warm":
            return self.STAGE_FLAME
        if role == "gold":
            return self.HUD_GOLD
        if role == "velvet":
            return self.STAGE_TAPESTRY
        if role == "stone":
            return self.STAGE_STONE
        if role == "stage_floor":
            return (38, 30, 42)
        if role.startswith("#") and len(role) == 7:
            try:
                return (int(role[1:3], 16), int(role[3:5], 16), int(role[5:7], 16))
            except ValueError:
                return accent
        return accent

    def _curtain_open_amount(self, curtain):
        progress = self.active_cutscene_narration_progress()
        eased = progress * progress * (3.0 - 2.0 * progress)
        return max(0.0, min(1.0, eased))

    def draw_cutscene_stage(self, surface, stage_rect, animation_id, accent):
        asset = self.active_cutscene_asset()
        stage = asset.stage if asset is not None else StageAsset()
        pygame.draw.rect(
            surface, self.STAGE_STONE_DARK, stage_rect, border_radius=self.ui(10)
        )
        self.draw_stage_backdrop(surface, stage_rect, stage, accent)
        self.draw_stage_floor(surface, stage_rect, stage, accent)
        self.draw_stage_props(surface, stage_rect, stage, accent)
        # Resolve the duel once per frame so every actor and the clash flash
        # share the same choreography state without recomputing it.
        duel = self._cutscene_duel_state()
        self._frame_duel_state = duel
        if asset is not None:
            entries = []
            for actor in asset.actors.values():
                dx, dy, frame_scale, alpha, pose = self.cutscene_actor_frame(
                    actor.id, animation_id
                )
                if duel is not None and actor.id in duel:
                    ddx, ddy, dpose, dalpha, dscale = duel[actor.id]
                    dx = ddx
                    dy = ddy
                    pose = dpose
                    if dalpha is not None:
                        alpha = dalpha
                    frame_scale = dscale
                entries.append((actor, dx, dy, frame_scale, alpha, pose))
            # Depth sort back-to-front by stage y so nearer actors occlude
            # further ones and the perspective reads correctly.
            entries.sort(key=lambda entry: entry[0].y + entry[2])
            for actor, dx, dy, frame_scale, alpha, pose in entries:
                self._render_cutscene_actor(
                    surface, stage_rect, actor, dx, dy, frame_scale, alpha, pose, accent
                )
        else:
            self._frame_duel_state = None
        self._draw_duel_clash_flash(surface, stage_rect)
        self.draw_stage_lighting(surface, stage_rect, stage, accent)
        if stage.proscenium:
            self.draw_stage_proscenium(surface, stage_rect, stage, accent)
        self.draw_stage_curtain(surface, stage_rect, stage, accent)
        self.draw_cutscene_letterbox(surface, stage_rect)
        self._frame_duel_state = None

    def draw_cutscene_letterbox(self, surface, stage_rect):
        bar_h = max(2, self.ui(4))
        pygame.draw.rect(
            surface,
            (0, 0, 0, 90),
            (stage_rect.x, stage_rect.y, stage_rect.width, bar_h),
        )
        pygame.draw.rect(
            surface,
            (0, 0, 0, 90),
            (stage_rect.x, stage_rect.bottom - bar_h, stage_rect.width, bar_h),
        )

    def draw_stage_backdrop(self, surface, stage_rect, stage, accent):
        asset = self.active_cutscene_asset()
        asset_id = asset.id if asset is not None else "_default"
        key = self._stage_cache_key(
            asset_id, "backdrop", stage_rect.size, accent, (stage.backdrop,)
        )

        def paint(layer):
            w, h = layer.get_size()
            theme = self.theme
            base = self.shade(theme.floor, -52)
            far = self.mix(base, self.shade(accent, -75), 0.45)
            # Clean vertical gradient back wall — no keyword doodads, no halo blobs.
            bands = 8
            for band in range(bands):
                amount = band / (bands - 1)
                color = self.mix(far, self.shade(theme.wall_top, -28), amount * 0.5)
                y = int(h * band / bands)
                bh = max(1, h // bands + 1)
                pygame.draw.rect(layer, (*color, 255), (0, y, w, bh))
            # A subtle top-down light gradient so the back wall reads as lit
            # from above without any transparent circle/halo overlays.
            warm = self.mix(self.STAGE_FLAME, accent, 0.2)
            light_bands = 6
            for band in range(light_bands):
                t = band / (light_bands - 1)
                y = int(h * 0.62 * band / light_bands)
                bh = max(1, int(h * 0.62) // light_bands + 1)
                pygame.draw.rect(layer, (*warm, int(18 * (1.0 - t))), (0, y, w, bh))
            # Painted horizon line where back wall meets floor.
            horizon_y = int(h * 0.62)
            pygame.draw.line(
                layer,
                (*self.shade(accent, -35), 90),
                (self.ui(8), horizon_y),
                (w - self.ui(8), horizon_y),
                self.ui(1),
            )

        layer = self._cached_stage_layer(key, stage_rect.size, paint)
        surface.blit(layer, stage_rect.topleft)

    def draw_stage_floor(self, surface, stage_rect, stage, accent):
        asset = self.active_cutscene_asset()
        asset_id = asset.id if asset is not None else "_default"
        key = self._stage_cache_key(
            asset_id, "floor", stage_rect.size, accent, (stage.floor_color,)
        )

        def paint(layer):
            w, h = layer.get_size()
            floor_top = int(h * 0.62)
            floor_h = h - floor_top
            floor_color = self.stage_role_color(stage.floor_color, accent)
            planks = 9
            for index in range(planks):
                t = index / max(1, planks - 1)
                front_half = w * (0.18 + 0.42 * t)
                back_half = w * (0.18 + 0.42 * (t - 1.0 / planks))
                y_front = floor_top + int(floor_h * (t + 1.0 / planks))
                y_back = floor_top + int(floor_h * t)
                shade = -32 + int(t * 36)
                color = self.shade(floor_color, shade)
                poly = [
                    (w // 2 - back_half, y_back),
                    (w // 2 + back_half, y_back),
                    (w // 2 + front_half, y_front),
                    (w // 2 - front_half, y_front),
                ]
                pygame.draw.polygon(layer, (*color, 255), poly)
                pygame.draw.polygon(layer, (*self.shade(color, -22), 140), poly, 1)
            pygame.draw.line(
                layer,
                (*self.shade(accent, -45), 110),
                (self.ui(6), h - self.ui(3)),
                (w - self.ui(6), h - self.ui(3)),
                self.ui(1),
            )

        layer = self._cached_stage_layer(key, stage_rect.size, paint)
        surface.blit(layer, stage_rect.topleft)

    def draw_stage_props(self, surface, stage_rect, stage, accent):
        for prop in stage.props:
            painter = self._stage_prop_painter(prop.kind)
            if painter is None:
                continue
            x = stage_rect.x + int(prop.x * stage_rect.width)
            y = stage_rect.y + int(prop.y * stage_rect.height)
            color = self.stage_role_color(prop.color, accent)
            sway = 0.0
            if prop.amplitude > 0:
                sway = math.sin(self.elapsed * 1.6 + prop.phase) * prop.amplitude
            painter(surface, x, y, prop.scale, color, prop.phase, sway)

    def _stage_prop_painter(self, kind):
        return {
            "pillar": self._paint_prop_pillar,
            "altar": self._paint_prop_altar,
            "lectern": self._paint_prop_lectern,
            "candelabra": self._paint_prop_candelabra,
            "banner": self._paint_prop_banner,
        }.get(kind)

    def _paint_prop_pillar(self, surface, x, y, scale, color, phase, sway):
        w = max(self.ui(14), int(self.ui(22) * scale))
        h = max(self.ui(60), int(self.ui(96) * scale))
        rect = pygame.Rect(0, 0, w, h)
        rect.midbottom = (x, y + self.ui(8))
        stone = self.STAGE_STONE
        pygame.draw.rect(surface, (*self.shade(stone, -18), 255), rect)
        pygame.draw.rect(
            surface, (*self.shade(stone, 22), 200), (rect.x, rect.y, self.ui(3), rect.h)
        )
        pygame.draw.rect(
            surface,
            (*self.shade(stone, -42), 220),
            (rect.right - self.ui(3), rect.y, self.ui(3), rect.h),
        )
        for cy in range(rect.y + self.ui(10), rect.bottom - self.ui(8), self.ui(18)):
            pygame.draw.line(
                surface,
                (*self.shade(stone, -50), 160),
                (rect.centerx, cy),
                (rect.centerx + self.ui(2), cy + self.ui(6)),
                1,
            )
        cap = pygame.Rect(
            rect.x - self.ui(4), rect.y - self.ui(6), rect.w + self.ui(8), self.ui(8)
        )
        pygame.draw.rect(surface, (*self.shade(stone, 8), 255), cap)
        pygame.draw.rect(surface, (*self.shade(stone, -32), 220), cap, 1)
        base = pygame.Rect(
            rect.x - self.ui(5),
            rect.bottom - self.ui(4),
            rect.w + self.ui(10),
            self.ui(8),
        )
        pygame.draw.rect(surface, (*self.shade(stone, -12), 255), base)
        pygame.draw.rect(surface, (*self.shade(stone, -42), 220), base, 1)

    def _paint_prop_altar(self, surface, x, y, scale, color, phase, sway):
        stone = self.STAGE_STONE
        w = max(self.ui(40), int(self.ui(64) * scale))
        h = max(self.ui(20), int(self.ui(30) * scale))
        rect = pygame.Rect(0, 0, w, h)
        rect.midbottom = (x, y + self.ui(8))
        pygame.draw.rect(
            surface, (*self.shade(stone, -10), 255), rect, border_radius=self.ui(3)
        )
        pygame.draw.rect(
            surface, (*self.shade(stone, 18), 200), rect, 1, border_radius=self.ui(3)
        )
        top = pygame.Rect(
            rect.x - self.ui(6), rect.y - self.ui(6), rect.w + self.ui(12), self.ui(8)
        )
        pygame.draw.rect(
            surface, (*self.shade(stone, 12), 255), top, border_radius=self.ui(2)
        )
        pygame.draw.rect(
            surface, (*self.shade(stone, -32), 220), top, 1, border_radius=self.ui(2)
        )
        accent = self.story_state.accent if self.story_state else self.theme.accent
        pygame.draw.circle(
            surface, accent, (rect.centerx, rect.centery), self.ui(2)
        )

    def _paint_prop_lectern(self, surface, x, y, scale, color, phase, sway):
        stone = self.STAGE_STONE
        w = max(self.ui(20), int(self.ui(30) * scale))
        h = max(self.ui(40), int(self.ui(56) * scale))
        rect = pygame.Rect(0, 0, w, h)
        rect.midbottom = (x, y + self.ui(8))
        pygame.draw.polygon(
            surface,
            (*self.shade(stone, -8), 255),
            [
                (rect.x, rect.bottom),
                (rect.right, rect.bottom),
                (rect.right - self.ui(4), rect.y),
                (rect.x + self.ui(2), rect.y),
            ],
        )
        ledge = pygame.Rect(
            rect.x - self.ui(2), rect.y - self.ui(4), rect.w + self.ui(4), self.ui(5)
        )
        pygame.draw.rect(surface, (*self.shade(stone, 16), 255), ledge)
        pygame.draw.rect(surface, (*self.shade(stone, -32), 220), ledge, 1)

    def _paint_prop_candelabra(self, surface, x, y, scale, color, phase, sway):
        iron = self.STAGE_IRON
        h = max(self.ui(40), int(self.ui(58) * scale))
        stem_top = (x, y - h + self.ui(8))
        stem_bottom = (x, y + self.ui(6))
        pygame.draw.line(
            surface, (*self.shade(iron, -20), 255), stem_top, stem_bottom, self.ui(3)
        )
        pygame.draw.rect(
            surface,
            (*self.shade(iron, -30), 255),
            (x - self.ui(7), y + self.ui(2), self.ui(14), self.ui(5)),
            border_radius=self.ui(2),
        )
        accent = self.story_state.accent if self.story_state else self.theme.accent
        flame_color = self.mix(self.STAGE_FLAME, accent, 0.35)
        for side in (-1, 0, 1):
            arm_y = y - h + self.ui(10) + side * self.ui(6)
            arm_end = (x + side * self.ui(10), arm_y)
            pygame.draw.line(
                surface,
                (*self.shade(iron, -10), 255),
                (x, arm_y + self.ui(4)),
                arm_end,
                self.ui(2),
            )
            candle = pygame.Rect(
                arm_end[0] - self.ui(2), arm_end[1] - self.ui(8), self.ui(4), self.ui(8)
            )
            pygame.draw.rect(surface, (220, 210, 188), candle)
            flick = 0.7 + 0.3 * math.sin(self.elapsed * 9.0 + phase + side * 1.3)
            flame_y = candle.y - self.ui(3) - int(flick * self.ui(2))
            pygame.draw.polygon(
                surface,
                flame_color,
                [
                    (candle.centerx, flame_y - self.ui(4)),
                    (candle.centerx - self.ui(2), flame_y),
                    (candle.centerx + self.ui(2), flame_y),
                ],
            )

    def _paint_prop_banner(self, surface, x, y, scale, color, phase, sway):
        w = max(self.ui(14), int(self.ui(20) * scale))
        h = max(self.ui(40), int(self.ui(60) * scale))
        top = (x, y)
        bottom_y = y + h
        sway_x = int(sway * self.ui(4))
        pts = [
            (top[0] - w // 2, top[1]),
            (top[0] + w // 2, top[1]),
            (top[0] + w // 2 + sway_x, bottom_y),
            (top[0] - w // 2 + sway_x, bottom_y),
        ]
        pygame.draw.polygon(surface, (*self.shade(color, -25), 235), pts)
        pygame.draw.polygon(surface, (*self.shade(color, 18), 200), pts, 1)
        for fx in range(3):
            cx = pts[2][0] + (pts[3][0] - pts[2][0]) * (fx + 1) / 4
            pygame.draw.line(
                surface,
                (*self.shade(color, 10), 200),
                (cx, bottom_y),
                (cx, bottom_y + self.ui(4)),
                self.ui(1),
            )
        pygame.draw.rect(
            surface,
            (*self.shade(self.STAGE_IRON, 6), 255),
            (
                top[0] - w // 2 - self.ui(2),
                top[1] - self.ui(3),
                w + self.ui(4),
                self.ui(4),
            ),
            border_radius=self.ui(1),
        )

    def draw_stage_lighting(self, surface, stage_rect, stage, accent):
        """Simplified stage lights (milestone 3.11).

        Replaces the old multi-circle spot/cone/wash/beam lights, the ambient
        particle system, and the footlight halos with one clean, cached
        lighting pass: a soft top-down key-light gradient, a warm floor pool,
        and a single thin flickering footlight strip at the front of the
        stage. No transparent ellipses or stacked glow circles.
        """
        asset = self.active_cutscene_asset()
        asset_id = asset.id if asset is not None else "_default"
        key = self._stage_cache_key(asset_id, "lighting", stage_rect.size, accent, ())

        def paint(layer):
            w, h = layer.get_size()
            warm = self.mix(self.STAGE_FLAME, accent, 0.22)
            # Top-down key light: brightest near the top where the rig hangs,
            # fading toward the floor. Smooth band gradient, no circles.
            top_bands = 8
            top_h = int(h * self.STAGE_FLOOR_TOP)
            for band in range(top_bands):
                t = band / max(1, top_bands - 1)
                y = int(top_h * band / top_bands)
                bh = max(1, top_h // top_bands + 1)
                pygame.draw.rect(layer, (*warm, int(30 * (1.0 - t))), (0, y, w, bh))
            # Warm floor pool across the lower stage: brightest just past the
            # horizon, softening toward the front. A gentle accent tint ties
            # the light to the scene mood.
            floor_top = top_h
            floor_h = h - floor_top
            floor_bands = 7
            for band in range(floor_bands):
                t = band / max(1, floor_bands - 1)
                fall = max(0.0, 1.0 - abs(t - 0.35) / 0.65)
                y = floor_top + int(floor_h * band / floor_bands)
                bh = max(1, floor_h // floor_bands + 1)
                pygame.draw.rect(
                    layer, (*accent, int(22 * fall)), (0, y, w, bh)
                )

        layer = self._cached_stage_layer(key, stage_rect.size, paint)
        surface.blit(layer, stage_rect.topleft)
        # Live footlight: a thin warm strip at the front edge with a gentle
        # flicker, plus a crisp iron lip. Cheap (two draw calls), no halos.
        flick = 0.82 + 0.18 * math.sin(self.elapsed * 5.5)
        foot_y = stage_rect.bottom - self.ui(3)
        foot_color = self.mix(self.STAGE_FLAME, accent, 0.4)
        pygame.draw.rect(
            surface,
            (*foot_color, int(120 * flick)),
            (stage_rect.x + self.ui(6), foot_y, stage_rect.width - self.ui(12), self.ui(2)),
        )
        pygame.draw.line(
            surface,
            (*self.shade(self.STAGE_IRON, 18), 180),
            (stage_rect.x, foot_y),
            (stage_rect.right, foot_y),
            1,
        )

    def draw_stage_proscenium(self, surface, stage_rect, stage, accent):
        asset = self.active_cutscene_asset()
        asset_id = asset.id if asset is not None else "_default"
        key = self._stage_cache_key(asset_id, "proscenium", stage_rect.size, accent, ())

        def paint(layer):
            w, h = layer.get_size()
            stone = self.STAGE_STONE
            iron = self.STAGE_IRON
            arch_h = max(self.ui(12), int(h * 0.10))
            side_w = max(self.ui(10), int(w * 0.045))
            pygame.draw.rect(layer, (*self.shade(stone, -8), 255), (0, 0, w, arch_h))
            pygame.draw.rect(layer, (*self.shade(stone, 22), 220), (0, 0, w, arch_h), 1)
            pygame.draw.line(
                layer,
                (*self.shade(iron, 8), 220),
                (self.ui(4), arch_h - self.ui(2)),
                (w - self.ui(4), arch_h - self.ui(2)),
                self.ui(1),
            )
            for side in (0, w - side_w):
                pygame.draw.rect(
                    layer, (*self.shade(stone, -4), 255), (side, 0, side_w, h)
                )
                pygame.draw.rect(
                    layer, (*self.shade(stone, 24), 220), (side, 0, side_w, h), 1
                )
                pygame.draw.line(
                    layer,
                    (*self.shade(iron, -10), 200),
                    (side + side_w // 2, arch_h),
                    (side + side_w // 2, h - self.ui(6)),
                    1,
                )
            for cx in (side_w // 2, w - side_w // 2):
                pygame.draw.circle(
                    layer, (*self.shade(stone, 28), 240), (cx, arch_h // 2), self.ui(4)
                )
                pygame.draw.circle(
                    layer,
                    (*self.shade(iron, 12), 220),
                    (cx, arch_h // 2),
                    self.ui(4),
                    1,
                )
                pygame.draw.circle(layer, (*accent, 150), (cx, arch_h // 2), self.ui(2))

        layer = self._cached_stage_layer(key, stage_rect.size, paint)
        surface.blit(layer, stage_rect.topleft)

    def draw_stage_curtain(self, surface, stage_rect, stage, accent):
        curtain = stage.curtain
        tapestry = self.stage_role_color(curtain.color, accent)
        sides = ("left", "right") if curtain.side == "both" else (curtain.side,)
        open_amount = self._curtain_open_amount(curtain)
        for side in sides:
            self._draw_curtain_panel(
                surface, stage_rect, side, curtain, tapestry, accent, open_amount
            )

    def _draw_curtain_panel(
        self, surface, stage_rect, side, curtain, tapestry, accent, open_amount
    ):
        ox, oy = stage_rect.topleft
        w = stage_rect.width
        h = stage_rect.height
        rest_half = curtain.gather * 0.5
        closed_half = 0.5
        half = closed_half + (rest_half - closed_half) * open_amount
        panel_w = max(self.ui(18), int(w * half))
        base_x = ox if side == "left" else ox + w - panel_w
        top_y = oy
        folds = 6
        fold_w = panel_w / folds
        top_pts = []
        bottom_pts = []
        for index in range(folds + 1):
            fx = base_x + index * fold_w
            sway = (
                math.sin(self.elapsed * 1.0 + curtain.phase + index * 0.9)
                * curtain.sway
                * self.ui(2)
            )
            top_pts.append((int(fx + sway), top_y))
            bottom_pts.append((int(fx + sway), top_y + h))
        outline = top_pts + list(reversed(bottom_pts))
        pygame.draw.polygon(surface, (*self.shade(tapestry, -28), 250), outline)
        for index in range(folds):
            x0 = top_pts[index][0]
            x1 = top_pts[index + 1][0]
            shade_amt = -46 + (index % 2) * 38
            stripe = [
                (x0, top_y),
                (x1, top_y),
                (bottom_pts[index + 1][0], top_y + h),
                (bottom_pts[index][0], top_y + h),
            ]
            pygame.draw.polygon(
                surface, (*self.shade(tapestry, shade_amt), 220), stripe
            )
        inner_x = base_x + panel_w if side == "left" else base_x
        pygame.draw.line(
            surface,
            (*self.shade(accent, -20), 160),
            (inner_x, top_y),
            (inner_x, top_y + h),
            self.ui(1),
        )
        tie_y = top_y + int(h * 0.42)
        if side == "left":
            ring_x = base_x + panel_w
            anchor_x = ox
        else:
            ring_x = base_x
            anchor_x = ox + w
        pygame.draw.line(
            surface,
            (*self.shade(self.STAGE_IRON, 6), 220),
            (ring_x, tie_y),
            (anchor_x, tie_y - self.ui(8)),
            self.ui(1),
        )
        pygame.draw.circle(
            surface,
            (*self.shade(self.STAGE_IRON, 14), 240),
            (ring_x, tie_y),
            self.ui(3),
        )
        pygame.draw.circle(
            surface,
            (*self.shade(self.STAGE_IRON, -20), 220),
            (ring_x, tie_y),
            self.ui(3),
            1,
        )
        for tx in range(-2, 3):
            pygame.draw.line(
                surface,
                (*self.shade(self.STAGE_IRON, -10), 200),
                (ring_x + tx, tie_y + self.ui(2)),
                (ring_x + tx, tie_y + self.ui(7)),
                1,
            )
        valance_h = max(self.ui(7), int(h * 0.07))
        valance_pts = [top_pts[0]]
        for index in range(folds):
            mid_x = (top_pts[index][0] + top_pts[index + 1][0]) // 2
            valance_pts.append((top_pts[index][0], top_y + valance_h))
            valance_pts.append((mid_x, top_y + valance_h // 2))
        valance_pts.append((top_pts[-1][0], top_y + valance_h))
        valance_pts.append((top_pts[-1][0], top_y))
        pygame.draw.polygon(surface, (*self.shade(tapestry, 14), 250), valance_pts)
        pygame.draw.polygon(
            surface, (*self.shade(self.STAGE_IRON, -10), 200), valance_pts, 1
        )



    def draw_cutscene_choice_glyph(
        self,
        surface: pygame.Surface,
        center: tuple[int, int],
        choice_key: str,
        radius: int,
        alpha: int = 180,
    ) -> None:
        color = self.cutscene_choice_color(
            choice_key,
            self.story_state.accent if self.story_state else self.theme.accent,
        )
        cx, cy = center
        pygame.draw.circle(
            surface,
            (*self.shade(color, -55), max(18, alpha // 3)),
            center,
            radius + self.ui(3),
        )
        pygame.draw.circle(surface, (*color, alpha), center, radius, self.ui(1))
        if choice_key == "aid":
            shield = [
                (cx, cy - radius),
                (cx + radius, cy - radius // 3),
                (cx + radius // 2, cy + radius),
                (cx, cy + radius + self.ui(2)),
                (cx - radius // 2, cy + radius),
                (cx - radius, cy - radius // 3),
            ]
            pygame.draw.polygon(surface, (*color, alpha), shield, self.ui(1))
            pygame.draw.line(
                surface,
                (*color, alpha),
                (cx, cy - radius // 2),
                (cx, cy + radius // 2),
                self.ui(1),
            )
            pygame.draw.line(
                surface,
                (*color, alpha),
                (cx - radius // 2, cy),
                (cx + radius // 2, cy),
                self.ui(1),
            )
        elif choice_key == "bargain":
            diamond = [
                (cx, cy - radius),
                (cx + radius, cy),
                (cx, cy + radius),
                (cx - radius, cy),
            ]
            pygame.draw.polygon(surface, (*color, alpha), diamond, self.ui(1))
            pygame.draw.circle(
                surface,
                (*color, alpha),
                (cx - radius // 2, cy - radius // 3),
                max(1, radius // 4),
                self.ui(1),
            )
            pygame.draw.circle(
                surface,
                (190, 45, 70, alpha),
                (cx + radius // 2, cy + radius // 3),
                max(1, radius // 4),
            )
        elif choice_key == "defy":
            pygame.draw.line(
                surface,
                (*color, alpha),
                (cx - radius, cy + radius),
                (cx + radius, cy - radius),
                self.ui(2),
            )
            pygame.draw.line(
                surface,
                (*color, alpha),
                (cx - radius, cy - radius // 2),
                (cx + radius, cy + radius // 2),
                self.ui(1),
            )
            pygame.draw.polygon(
                surface,
                (*color, alpha),
                [
                    (cx + radius, cy - radius),
                    (cx + radius // 2, cy - radius // 2),
                    (cx + radius // 4, cy - radius),
                ],
                0,
            )
        else:
            pygame.draw.circle(surface, (*color, alpha), center, max(1, radius // 3))

    def cutscene_choice_color(self, choice_key: str, accent: Color) -> Color:
        if choice_key == "aid":
            return (108, 218, 156)
        if choice_key == "bargain":
            return (213, 165, 72)
        if choice_key == "defy":
            return (232, 83, 74)
        return accent

    def cutscene_story_text(self) -> str:
        parts = [self.active_cutscene_text()]
        if self.story_state is not None:
            parts.extend(
                [
                    self.story_state.title,
                    self.story_state.objective,
                    self.story_state.faction,
                    self.story_state.relic_name,
                    self.story_state.relic_form,
                    self.story_state.relic_temptation,
                ]
            )
        beat = self.current_story_beat()
        if beat is not None:
            parts.extend(
                [
                    beat.title,
                    beat.summary,
                    beat.theme_name,
                    beat.guest_role,
                    beat.guest_motive,
                ]
            )
        return " ".join(parts)

    def draw_cutscene_actor(
        self,
        surface: pygame.Surface,
        stage_rect: pygame.Rect,
        actor: CutsceneActorAsset,
        animation_id: str,
        accent: Color,
    ) -> None:
        dx, dy, frame_scale, alpha, pose = self.cutscene_actor_frame(
            actor.id, animation_id
        )
        duel = getattr(self, "_frame_duel_state", None)
        if duel is not None and actor.id in duel:
            ddx, ddy, dpose, dalpha, dscale = duel[actor.id]
            dx = ddx
            dy = ddy
            pose = dpose
            if dalpha is not None:
                alpha = dalpha
            frame_scale = dscale
        self._render_cutscene_actor(
            surface, stage_rect, actor, dx, dy, frame_scale, alpha, pose, accent
        )

    def _render_cutscene_actor(
        self,
        surface: pygame.Surface,
        stage_rect: pygame.Rect,
        actor: CutsceneActorAsset,
        dx: float,
        dy: float,
        frame_scale: float,
        alpha: float,
        pose: str,
        accent: Color,
    ) -> None:
        color = self.cutscene_actor_color(actor, accent)
        x = stage_rect.x + int((actor.x + dx) * stage_rect.width)
        y = stage_rect.y + int((actor.y + dy) * stage_rect.height)

        sprite = self.cutscene_actor_surface(actor, color, pose)
        depth_scale = self._stage_actor_depth_scale(actor.y + dy)
        base_h = stage_rect.height * self.STAGE_ACTOR_HEIGHT_FRAC
        target_h = base_h * depth_scale * actor.scale * frame_scale
        scale = target_h / max(1, sprite.get_height())
        sprite_w = max(1, int(sprite.get_width() * scale))
        sprite_h = max(1, int(sprite.get_height() * scale))
        sprite = pygame.transform.scale(sprite, (sprite_w, sprite_h))
        sprite.set_alpha(max(0, min(255, int(255 * alpha))))

        surface.blit(sprite, sprite.get_rect(midbottom=(x, y + self.ui(14))))
        self.draw_cutscene_actor_pose_effects(
            surface, x, y, sprite_w, sprite_h, actor, pose, color, accent
        )

        label_text = self.cutscene_actor_label(actor)
        if label_text:
            label = self.small_font.render(label_text, True, color)
            surface.blit(label, label.get_rect(center=(x, y - sprite_h - self.ui(3))))

    def cutscene_actor_frame(
        self, actor_id: str, animation_id: str
    ) -> tuple[float, float, float, float, str]:
        asset = self.active_cutscene_asset()
        if asset is None or self.active_cutscene is None:
            return 0.0, 0.0, 1.0, 1.0, "idle"
        animation = asset.animations.get(animation_id)
        if animation is None:
            return 0.0, 0.0, 1.0, 1.0, "idle"
        frames = [frame for frame in animation.frames if frame.actor == actor_id]
        if not frames:
            return 0.0, 0.0, 1.0, 1.0, "idle"
        duration = sum(frame.duration for frame in frames)
        if duration <= 0:
            return 0.0, 0.0, 1.0, 1.0, "idle"
        # Slow the stage animation loop so actors drift gently instead of
        # fidgeting. The loop time is scaled and the per-frame movement
        # deltas are damped so poses still read but feel measured.
        t = self.active_cutscene.node_elapsed * self.STAGE_ACTOR_TIME_SCALE
        if animation.loop:
            t %= duration
        else:
            t = min(t, duration - 0.001)
        elapsed = 0.0
        for index, frame in enumerate(frames):
            if t <= elapsed + frame.duration:
                next_frame: SpriteAnimationFrameAsset
                if index + 1 < len(frames):
                    next_frame = frames[index + 1]
                elif animation.loop:
                    next_frame = frames[0]
                else:
                    next_frame = frame
                phase = 0.0 if frame.duration <= 0 else (t - elapsed) / frame.duration
                phase = max(0.0, min(1.0, phase))
                # Smoothstep the phase so motion eases in/out rather than
                # feeling linear and twitchy.
                eased = phase * phase * (3.0 - 2.0 * phase)
                damp = self.STAGE_ACTOR_MOVE_DAMP
                return (
                    (frame.dx + (next_frame.dx - frame.dx) * eased) * damp,
                    (frame.dy + (next_frame.dy - frame.dy) * eased) * damp,
                    frame.scale + (next_frame.scale - frame.scale) * eased,
                    frame.alpha + (next_frame.alpha - frame.alpha) * eased,
                    frame.pose,
                )
            elapsed += frame.duration
        frame = frames[-1]
        return (
            frame.dx * self.STAGE_ACTOR_MOVE_DAMP,
            frame.dy * self.STAGE_ACTOR_MOVE_DAMP,
            frame.scale,
            frame.alpha,
            frame.pose,
        )

    def _stage_actor_depth_scale(self, y):
        # Perspective scale for a stage figure: normalized y is mapped onto
        # the floor plane (STAGE_FLOOR_TOP..1.0) so figures near the back wall
        # read smaller and figures near the front read larger.
        depth_t = max(
            0.0, min(1.0, (y - self.STAGE_FLOOR_TOP) / (1.0 - self.STAGE_FLOOR_TOP))
        )
        return (
            self.STAGE_BACK_SCALE
            + (self.STAGE_FRONT_SCALE - self.STAGE_BACK_SCALE) * depth_t
        )

    def _cutscene_duel_obstacle(self, asset, player, antagonist):
        # Find a stage prop that sits between the duelers' home x positions
        # (e.g. the altar in the middle of the omen stage). It is treated as a
        # solid obstacle the duelers must route around. Returns (x, y) in
        # normalized stage coordinates, or None when the path is clear.
        lo, hi = (player.x, antagonist.x) if player.x < antagonist.x else (
            antagonist.x, player.x
        )
        best = None
        best_dist = None
        mid = (player.x + antagonist.x) * 0.5
        for prop in asset.stage.props:
            if lo < prop.x < hi:
                dist = abs(prop.x - mid)
                if best is None or dist < best_dist:
                    best, best_dist = (prop.x, prop.y), dist
        return best

    def _cutscene_duel_state(self):
        # Choreograph the player/antagonist duel for the current frame.
        # Returns None when the active cutscene has no duel pair, otherwise a
        # mapping with per-actor (dx, dy, pose, alpha, frame_scale) tuples and
        # a "clash" (x, y) point for the clash flash. The duel loops on its
        # own clock so the fight plays continuously while the narrator speaks.
        asset = self.active_cutscene_asset()
        if asset is None:
            return None
        player = asset.actors.get("player")
        antagonist = asset.actors.get("antagonist")
        if player is None or antagonist is None:
            return None

        period = self.STAGE_DUEL_PERIOD
        t = (self.elapsed % period) / period
        p_app = self.STAGE_DUEL_PHASE_APPROACH
        p_clash = p_app + self.STAGE_DUEL_PHASE_CLASH
        p_ret = p_clash + self.STAGE_DUEL_PHASE_RETREAT

        home_p = (player.x, player.y)
        home_a = (antagonist.x, antagonist.y)
        obstacle = self._cutscene_duel_obstacle(asset, player, antagonist)
        if obstacle is not None:
            # Route around the obstacle: pass to opposite sides and clash just
            # in front of it so neither dueler crosses its footprint.
            obs_x, obs_y = obstacle
            clash_y = min(obs_y + self.STAGE_DUEL_DETOUR_FORWARD,
                          self.STAGE_DUEL_DETOUR_MAX_Y)
            # Keep each dueler on their own side of the obstacle.
            if player.x < antagonist.x:
                meet_p = (obs_x - self.STAGE_DUEL_OBSTACLE_CLEAR, clash_y)
                meet_a = (obs_x + self.STAGE_DUEL_OBSTACLE_CLEAR, clash_y)
            else:
                meet_p = (obs_x + self.STAGE_DUEL_OBSTACLE_CLEAR, clash_y)
                meet_a = (obs_x - self.STAGE_DUEL_OBSTACLE_CLEAR, clash_y)
            clash = (obs_x, clash_y)
        else:
            # No obstacle: straight-line meeting at the midpoint, dy = 0.
            mid_x = (player.x + antagonist.x) * 0.5
            meet_p = (mid_x - self.STAGE_DUEL_GAP, player.y)
            meet_a = (mid_x + self.STAGE_DUEL_GAP, antagonist.y)
            clash = (mid_x, (player.y + antagonist.y) * 0.5)

        def ease(value):
            return value * value * (3.0 - 2.0 * value)

        if t < p_app:
            k = ease(t / p_app)
            xp = home_p[0] + (meet_p[0] - home_p[0]) * k
            yp = home_p[1] + (meet_p[1] - home_p[1]) * k
            xa = home_a[0] + (meet_a[0] - home_a[0]) * k
            ya = home_a[1] + (meet_a[1] - home_a[1]) * k
            pose_p, pose_a = "vow", "threaten"
        elif t < p_clash:
            xp, yp = meet_p
            xa, ya = meet_a
            pose_p, pose_a = "defy", "threaten"
        elif t < p_ret:
            k = ease((t - p_clash) / (p_ret - p_clash))
            xp = meet_p[0] + (home_p[0] - meet_p[0]) * k
            yp = meet_p[1] + (home_p[1] - meet_p[1]) * k
            xa = meet_a[0] + (home_a[0] - meet_a[0]) * k
            ya = meet_a[1] + (home_a[1] - meet_a[1]) * k
            pose_p, pose_a = "guard", "watch"
        else:
            xp, yp = home_p
            xa, ya = home_a
            pose_p, pose_a = "listen", "watch"

        return {
            "player": (xp - home_p[0], yp - home_p[1], pose_p, 1.0, 1.0),
            "antagonist": (
                xa - home_a[0],
                ya - home_a[1],
                pose_a,
                self.STAGE_DUEL_ANTAGONIST_ALPHA,
                1.0,
            ),
            "clash": clash,
        }

    def _draw_duel_clash_flash(self, surface, stage_rect):
        # A short spark burst at the duel meeting point during the clash.
        duel = getattr(self, "_frame_duel_state", None)
        if duel is None:
            return
        period = self.STAGE_DUEL_PERIOD
        t = (self.elapsed % period) / period
        p_app = self.STAGE_DUEL_PHASE_APPROACH
        p_clash_end = p_app + self.STAGE_DUEL_PHASE_CLASH
        if t < p_app or t >= p_clash_end:
            return
        local = (t - p_app) / self.STAGE_DUEL_PHASE_CLASH
        intensity = 1.0 - abs(local - 0.5) * 2.0
        clash_x, clash_y = duel["clash"]
        cx = stage_rect.x + int(clash_x * stage_rect.width)
        cy = stage_rect.y + int(clash_y * stage_rect.height)
        accent = self.story_state.accent if self.story_state else self.theme.accent
        spark = self.mix((255, 244, 210), accent, 0.25)
        # Cross-slash lines only: a crisp weapon clash read with no circular
        # glow blobs stacked on the stage.
        arm = self.ui(10) + int(self.ui(8) * intensity)
        for (dx0, dy0), (dx1, dy1) in (
            ((-arm, -arm // 2), (arm, arm // 2)),
            ((-arm, arm // 2), (arm, -arm // 2)),
        ):
            pygame.draw.line(
                surface,
                (*spark, int(180 * intensity)),
                (cx + dx0, cy + dy0),
                (cx + dx1, cy + dy1),
                max(1, self.ui(1)),
            )

    def cutscene_actor_surface(
        self, actor: CutsceneActorAsset, color: Color, pose: str = "idle"
    ) -> pygame.Surface:
        if actor.sprite == "player":
            return self.sprites.player_sprites.get(
                self.player.class_name, self.sprites.player
            ).copy()
        if actor.sprite == "relic":
            return self.cutscene_relic_surface(color, pose)
        if actor.sprite == "story_guest":
            return self.cutscene_guest_surface(color, pose)
        if actor.sprite == "enemy":
            return self.sprites.enemies.get("Gate Warden") or next(
                iter(self.sprites.enemies.values())
            )
        return self.cutscene_guest_surface(color, pose)

    def cutscene_guest_surface(
        self, color: Color, pose: str = "idle"
    ) -> pygame.Surface:
        sprite = pygame.Surface((54, 76), pygame.SRCALPHA)
        sway = 2 if pose in ("shudder", "warn") else 0
        cloak = [(27 + sway, 7), (8, 58), (46, 58)]
        pygame.draw.polygon(sprite, self.shade(color, -62), cloak)
        pygame.draw.polygon(sprite, color, cloak, 2)
        pygame.draw.circle(sprite, self.shade(color, 35), (27 + sway // 2, 21), 10)
        pygame.draw.circle(sprite, (245, 236, 205), (24 + sway // 2, 20), 2)
        pygame.draw.circle(sprite, (245, 236, 205), (30 + sway // 2, 20), 2)
        if pose in ("plead", "reach", "warn"):
            left_hand = (12, 31 if pose == "warn" else 24)
            right_hand = (42, 25 if pose == "reach" else 32)
            pygame.draw.line(sprite, self.shade(color, 28), (20, 35), left_hand, 3)
            pygame.draw.line(sprite, self.shade(color, 28), (34, 35), right_hand, 3)
            pygame.draw.circle(sprite, (235, 218, 190), left_hand, 3)
            pygame.draw.circle(sprite, (235, 218, 190), right_hand, 3)
        else:
            pygame.draw.line(sprite, self.shade(color, 18), (18, 39), (12, 51), 3)
            pygame.draw.line(sprite, self.shade(color, 18), (36, 39), (42, 51), 3)
        mouth_y = 42 if pose in ("plead", "warn") else 41
        pygame.draw.line(
            sprite, (*self.shade(color, 25), 180), (17, mouth_y), (37, mouth_y), 2
        )
        return sprite

    def cutscene_relic_surface(
        self, color: Color, pose: str = "idle"
    ) -> pygame.Surface:
        sprite = pygame.Surface((54, 72), pygame.SRCALPHA)
        pulse = 0.5 + 0.5 * math.sin(self.elapsed * 4.0)
        ring_alpha = int(44 + 44 * pulse)
        if pose in ("reveal", "surge", "pulse"):
            ring_alpha = min(140, ring_alpha + 42)
        pygame.draw.circle(sprite, (*color, ring_alpha), (27, 34), 24, 2)
        diamond = [(27, 6), (44, 34), (27, 62), (10, 34)]
        pygame.draw.polygon(sprite, self.shade(color, -45), diamond)
        pygame.draw.polygon(sprite, color, diamond, 2)
        pygame.draw.line(sprite, self.shade(color, 45), (27, 13), (27, 55), 2)
        pygame.draw.line(sprite, self.shade(color, 28), (16, 34), (38, 34), 2)
        aspect = self.cutscene_relic_aspect()
        if aspect == "blade":
            pygame.draw.line(sprite, (246, 236, 196), (19, 52), (36, 17), 3)
            pygame.draw.polygon(sprite, (246, 236, 196), [(36, 17), (35, 27), (42, 21)])
        elif aspect == "mirror":
            pygame.draw.ellipse(sprite, (235, 229, 245), (18, 20, 18, 26), 2)
            pygame.draw.line(sprite, (235, 229, 245), (27, 46), (27, 56), 2)
        elif aspect == "crown":
            pygame.draw.polygon(
                sprite,
                (242, 211, 94),
                [(16, 28), (21, 18), (27, 28), (34, 18), (39, 28), (39, 36), (16, 36)],
                2,
            )
        elif aspect == "key":
            pygame.draw.circle(sprite, (234, 218, 154), (22, 28), 5, 2)
            pygame.draw.line(sprite, (234, 218, 154), (27, 28), (40, 42), 2)
            pygame.draw.line(sprite, (234, 218, 154), (35, 37), (40, 34), 2)
        elif aspect == "bell":
            pygame.draw.arc(
                sprite, (236, 218, 138), (17, 20, 22, 28), math.pi, math.tau, 2
            )
            pygame.draw.line(sprite, (236, 218, 138), (18, 34), (36, 34), 2)
            pygame.draw.circle(sprite, (236, 218, 138), (27, 39), 3)
        elif aspect == "lantern":
            pygame.draw.rect(
                sprite, (245, 196, 108), (18, 20, 18, 28), 2, border_radius=3
            )
            pygame.draw.line(sprite, (245, 196, 108), (20, 20), (27, 12), 1)
            pygame.draw.line(sprite, (245, 196, 108), (34, 20), (27, 12), 1)
            pygame.draw.circle(sprite, (245, 124, 72), (27, 35), 5)
        elif aspect == "chain":
            for index in range(3):
                pygame.draw.ellipse(
                    sprite, (216, 194, 156), (15 + index * 8, 28, 14, 9), 2
                )
        elif aspect == "map":
            pygame.draw.rect(
                sprite, (228, 208, 162), (15, 23, 24, 24), 1, border_radius=2
            )
            pygame.draw.line(sprite, (228, 208, 162), (19, 40), (36, 28), 1)
            pygame.draw.circle(sprite, (228, 208, 162), (22, 37), 1)
        elif aspect == "vessel":
            pygame.draw.polygon(
                sprite, (170, 210, 232), [(18, 25), (23, 49), (31, 49), (36, 25)], 2
            )
            pygame.draw.line(sprite, (170, 210, 232), (21, 34), (33, 34), 1)
        elif aspect == "seed":
            pygame.draw.ellipse(sprite, (126, 214, 92), (19, 19, 16, 31), 2)
            pygame.draw.line(sprite, (126, 214, 92), (27, 24), (27, 45), 1)
        elif aspect == "spike":
            pygame.draw.polygon(
                sprite, (220, 210, 190), [(27, 15), (36, 52), (18, 52)], 2
            )
        elif aspect == "blood":
            pygame.draw.circle(sprite, (192, 46, 70), (27, 34), 6)
            pygame.draw.polygon(sprite, (192, 46, 70), [(27, 18), (20, 35), (34, 35)])
        else:
            pygame.draw.circle(sprite, self.shade(color, 50), (27, 34), 6, 2)
            pygame.draw.circle(sprite, self.shade(color, 50), (27, 34), 2)
        return sprite

    def draw_cutscene_actor_pose_effects(
        self,
        surface: pygame.Surface,
        x: int,
        y: int,
        sprite_w: int,
        sprite_h: int,
        actor: CutsceneActorAsset,
        pose: str,
        color: Color,
        accent: Color,
    ) -> None:
        # Pose emphasis stays minimal: a guest shudder line and relic surge
        # rays. Player/enemy attack lines are intentionally omitted so the
        # sprites read cleanly during the duel.
        top = y + self.ui(16) - sprite_h
        if actor.id == "guest":
            self.draw_cutscene_guest_prop(
                surface, x + sprite_w // 3, top + self.ui(12), color
            )
            if pose == "shudder":
                pygame.draw.line(
                    surface,
                    (190, 45, 70, 110),
                    (x - self.ui(13), top),
                    (x + self.ui(11), top + self.ui(24)),
                    self.ui(1),
                )
        elif actor.id == "relic":
            if pose in ("surge", "reveal"):
                for angle_index in range(6):
                    angle = self.elapsed * 0.8 + math.tau * angle_index / 6
                    start = (
                        x + int(math.cos(angle) * self.ui(15)),
                        top + sprite_h // 2 + int(math.sin(angle) * self.ui(12)),
                    )
                    end = (
                        x + int(math.cos(angle) * self.ui(29)),
                        top + sprite_h // 2 + int(math.sin(angle) * self.ui(23)),
                    )
                    pygame.draw.line(surface, (*accent, 118), start, end, self.ui(1))

    def draw_cutscene_guest_prop(
        self, surface: pygame.Surface, x: int, y: int, color: Color
    ) -> None:
        text = self.cutscene_story_text().lower()
        if any(term in text for term in ("bell", "toll", "priest", "acolyte")):
            pygame.draw.arc(
                surface,
                (236, 218, 138, 150),
                (x - self.ui(6), y, self.ui(12), self.ui(14)),
                math.pi,
                math.tau,
                self.ui(1),
            )
            pygame.draw.line(
                surface,
                (236, 218, 138, 150),
                (x - self.ui(6), y + self.ui(8)),
                (x + self.ui(6), y + self.ui(8)),
                self.ui(1),
            )
        elif any(
            term in text for term in ("lock", "key", "thief", "rogue", "cartographer")
        ):
            pygame.draw.circle(
                surface,
                (234, 218, 154, 150),
                (x, y + self.ui(5)),
                self.ui(4),
                self.ui(1),
            )
            pygame.draw.line(
                surface,
                (234, 218, 154, 150),
                (x + self.ui(4), y + self.ui(5)),
                (x + self.ui(12), y + self.ui(13)),
                self.ui(1),
            )
        elif any(term in text for term in ("grave", "dead", "bone", "coffin", "crypt")):
            pygame.draw.circle(
                surface,
                (220, 212, 190, 145),
                (x, y + self.ui(6)),
                self.ui(5),
                self.ui(1),
            )
            pygame.draw.line(
                surface,
                (220, 212, 190, 145),
                (x - self.ui(5), y + self.ui(14)),
                (x + self.ui(5), y + self.ui(14)),
                self.ui(1),
            )
        elif any(term in text for term in ("star", "mirror", "dream", "veil")):
            pygame.draw.circle(
                surface,
                (*self.shade(color, 45), 140),
                (x, y + self.ui(7)),
                self.ui(7),
                self.ui(1),
            )
            pygame.draw.circle(
                surface, (*self.shade(color, 45), 140), (x, y + self.ui(7)), self.ui(2)
            )
        else:
            pygame.draw.rect(
                surface,
                (224, 206, 168, 130),
                (x - self.ui(5), y, self.ui(10), self.ui(14)),
                self.ui(1),
            )
            pygame.draw.line(
                surface,
                (224, 206, 168, 130),
                (x - self.ui(3), y + self.ui(4)),
                (x + self.ui(3), y + self.ui(4)),
                self.ui(1),
            )

    def cutscene_relic_aspect(self) -> str:
        text = self.cutscene_story_text().lower()
        if any(
            term in text
            for term in ("spike", "nail", "blade", "sword", "knife", "fang", "weapon")
        ):
            return (
                "spike" if any(term in text for term in ("spike", "nail")) else "blade"
            )
        if any(
            term in text for term in ("mirror", "lens", "face", "reflection", "psalter")
        ):
            return "mirror"
        if any(term in text for term in ("crown", "antler")):
            return "crown"
        if any(term in text for term in ("chain", "oath-eater")):
            return "chain"
        if any(term in text for term in ("map", "vellum", "road", "cartographer")):
            return "map"
        if any(term in text for term in ("lantern", "lamp")):
            return "lantern"
        if any(term in text for term in ("urn", "vessel", "rain", "water")):
            return "vessel"
        if any(term in text for term in ("seed", "heartseed", "reliquary", "heart")):
            return "seed"
        if any(term in text for term in ("key", "cinder-key")):
            return "key"
        if any(term in text for term in ("bell", "toll", "chime")):
            return "bell"
        if any(term in text for term in ("blood", "sin", "curse", "wound")):
            return "blood"
        return "eye"

    def cutscene_actor_color(self, actor: CutsceneActorAsset, accent: Color) -> Color:
        role = actor.color.lower()
        if role == "accent":
            return accent
        if role == "player":
            return (226, 222, 205)
        if role == "danger":
            return (235, 95, 84)
        if role.startswith("#") and len(role) == 7:
            try:
                return (int(role[1:3], 16), int(role[3:5], 16), int(role[5:7], 16))
            except ValueError:
                return accent
        return accent

    def cutscene_actor_label(self, actor: CutsceneActorAsset) -> str:
        if self.active_cutscene is None:
            return ""
        context = {**self.quest_cutscene_context(self.active_cutscene_guest())}
        context.update(self.active_cutscene.context)
        return format_asset_text(actor.name, context)[:32]

    def draw_story_intro_overlay(self) -> None:
        with self.fitted_ui_layout((960, 540)):
            self._draw_story_intro_overlay_fitted()

    def _draw_story_intro_overlay_fitted(self) -> None:
        lines = self.story_intro_lines()
        if not lines:
            return
        width, height = self.screen.get_size()
        dim = pygame.Surface((width, height), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 255))
        self.screen.blit(dim, (0, 0))

        accent = self.story_state.accent if self.story_state else self.theme.accent
        panel_w = min(width - self.ui(28), self.ui(900))
        panel_h = min(height - self.ui(16), self.ui(610))
        if panel_w < 300 or panel_h < 260:
            return
        rect = pygame.Rect(
            (width - panel_w) // 2,
            max(self.ui(8), (height - panel_h) // 2),
            panel_w,
            panel_h,
        )
        surface = pygame.Surface(rect.size, pygame.SRCALPHA)
        self.draw_translucent_panel(
            surface,
            surface.get_rect(),
            (10, 8, 14, 248),
            (*accent, 222),
            radius=self.ui(14),
            width=self.ui(2),
        )
        pygame.draw.line(
            surface,
            (255, 245, 210, 28),
            (self.ui(24), self.ui(10)),
            (panel_w - self.ui(24), self.ui(10)),
            self.ui(1),
        )

        pad = max(self.ui(14), 18)
        available_w = panel_w - pad * 2
        title_text = "Guest Relic Omen"
        depth_text = f"Depth {self.current_depth}/{DUNGEON_DEPTH}"
        header_h = max(self.font.get_height(), self.small_font.get_height()) + self.ui(
            8
        )
        meta_w = min(
            self.small_font.size(depth_text)[0] + self.ui(8),
            max(self.ui(96), available_w // 3),
        )
        meta_x = pad + available_w - meta_w
        title_rect = pygame.Rect(
            pad,
            pad,
            max(1, meta_x - pad - self.ui(10)),
            self.font.get_height(),
        )
        meta_rect = pygame.Rect(
            meta_x,
            pad + (self.font.get_height() - self.small_font.get_height()) // 2,
            meta_w,
            self.small_font.get_height(),
        )
        self.draw_ui_text(surface, title_text, self.font, accent, title_rect)
        self.draw_ui_text(
            surface,
            depth_text,
            self.small_font,
            (196, 188, 204),
            meta_rect,
            align="right",
        )

        options = self.story_relic_choice_options()
        options_to_draw = options[: min(3, len(options))]
        choice_gap = max(self.ui(4), 6)
        footer_h = self.small_font.get_height()
        choice_w = available_w
        option_entries = [
            (label, detail) for _choice_key, label, detail in options_to_draw
        ]
        option_heights = [
            self.cutscene_response_height(label, detail, choice_w)
            for label, detail in option_entries
        ]
        choices_block_h = (
            sum(option_heights) + max(0, len(option_heights) - 1) * choice_gap
        )
        choices_start = panel_h - pad - footer_h - self.ui(10) - choices_block_h

        stage_top = pad + header_h + self.ui(12)
        available_for_stage = max(
            self.ui(48), choices_start - stage_top - self.small_font.get_height() * 3
        )
        stage_h = max(self.ui(52), min(int(panel_h * 0.30), available_for_stage))
        stage_rect = pygame.Rect(pad, stage_top, available_w, stage_h)
        self.draw_story_intro_stage(surface, stage_rect, accent, options_to_draw)

        y = stage_rect.bottom + self.ui(12)
        body_lines: list[tuple[str, Color]] = []
        for index, line in enumerate(lines):
            color = (244, 232, 214) if index == 0 else (214, 207, 196)
            if line.startswith("Depth "):
                color = (238, 218, 164)
            for wrapped in self.wrap_ui_text(line, self.small_font, available_w):
                body_lines.append((wrapped, color))
        text_bottom = max(y + self.small_font.get_height(), choices_start - self.ui(10))
        line_h = max(self.small_font.get_height() + self.ui(3), self.ui(18))
        max_body_lines = max(1, (text_bottom - y) // line_h)
        for text_line, color in body_lines[:max_body_lines]:
            self.draw_ui_text(
                surface,
                text_line,
                self.small_font,
                color,
                pygame.Rect(pad, y, available_w, line_h),
            )
            y += line_h
        if len(body_lines) > max_body_lines and y + line_h <= choices_start:
            self.draw_ui_text(
                surface,
                "…",
                self.small_font,
                (170, 165, 155),
                pygame.Rect(pad, y, available_w, line_h),
            )

        choice_rects = self.cutscene_response_rects(
            option_entries, pad, choices_start, choice_w, choice_gap
        )
        for index, ((choice_key, label, detail), choice_rect) in enumerate(
            zip(options_to_draw, choice_rects)
        ):
            choice_color = self.cutscene_choice_color(choice_key, accent)
            pygame.draw.rect(
                surface,
                (24, 19, 30, 238),
                choice_rect,
                border_radius=self.ui(9),
            )
            pygame.draw.rect(
                surface,
                (*choice_color, 170),
                choice_rect,
                self.ui(1),
                border_radius=self.ui(9),
            )
            key_size = min(self.ui(36), choice_rect.height - self.ui(12))
            key_rect = pygame.Rect(
                choice_rect.x + self.ui(7),
                choice_rect.y + (choice_rect.height - key_size) // 2,
                key_size,
                key_size,
            )
            pygame.draw.rect(
                surface,
                (*self.shade(choice_color, -58), 238),
                key_rect,
                border_radius=self.ui(7),
            )
            self.draw_cutscene_choice_glyph(
                surface,
                key_rect.center,
                choice_key,
                max(self.ui(7), key_size // 3),
                alpha=96,
            )
            self.draw_ui_text(
                surface,
                str(index + 1),
                self.font,
                choice_color,
                key_rect,
                align="center",
                valign="center",
            )
            text_x = key_rect.right + self.ui(9)
            text_rect = pygame.Rect(
                text_x,
                choice_rect.y + self.ui(7),
                max(1, choice_rect.right - text_x - self.ui(8)),
                choice_rect.height - self.ui(14),
            )
            self.draw_cutscene_response_text(surface, label, detail, text_rect)

        footer = "Press 1-3 to confirm the guest dialog, place the relic, and begin this level."
        self.draw_ui_text(
            surface,
            footer,
            self.small_font,
            (205, 185, 225),
            pygame.Rect(pad, panel_h - pad - footer_h, available_w, footer_h),
        )
        self.screen.blit(surface, rect)

    def draw_story_intro_stage(
        self,
        surface: pygame.Surface,
        stage_rect: pygame.Rect,
        accent: Color,
        options: list[tuple[str, str, str]],
    ) -> None:
        pygame.draw.rect(
            surface, self.STAGE_STONE_DARK, stage_rect, border_radius=self.ui(10)
        )
        # Clean gradient backdrop — no motif/sigil/silhouette clutter.
        theme = self.theme
        base = self.shade(theme.floor, -52)
        far = self.mix(base, self.shade(accent, -75), 0.45)
        bands = 8
        for band in range(bands):
            amount = band / (bands - 1)
            color = self.mix(far, self.shade(theme.wall_top, -28), amount * 0.5)
            y = stage_rect.y + int(stage_rect.height * band / bands)
            bh = max(1, stage_rect.height // bands + 1)
            pygame.draw.rect(
                surface, (*color, 255), (stage_rect.x, y, stage_rect.width, bh)
            )
        pygame.draw.rect(
            surface, (*accent, 125), stage_rect, self.ui(1), border_radius=self.ui(10)
        )
        horizon_y = stage_rect.y + int(stage_rect.height * 0.64)
        pygame.draw.line(
            surface,
            (*self.shade(accent, -35), 90),
            (stage_rect.x + self.ui(10), horizon_y),
            (stage_rect.right - self.ui(10), horizon_y),
            self.ui(1),
        )

        guest = self.current_story_guest_for_depth()
        guest_color = self.mix(accent, (228, 218, 198), 0.35)
        player_actor = CutsceneActorAsset(
            "player", self.player.class_name, "player", 0.24, 0.72, 0.74, "player"
        )
        guest_actor = CutsceneActorAsset(
            "guest",
            guest.name if guest is not None else "Guest",
            "story_guest",
            0.50,
            0.70,
            0.80,
            "accent",
        )
        relic_actor = CutsceneActorAsset(
            "relic", "Relic Echo", "relic", 0.76, 0.62, 0.80, "accent"
        )
        self.draw_intro_stage_actor(surface, stage_rect, player_actor, "vow", accent)
        self.draw_intro_stage_actor(
            surface, stage_rect, guest_actor, "plead", guest_color
        )
        self.draw_intro_stage_actor(surface, stage_rect, relic_actor, "reveal", accent)

    def draw_intro_stage_actor(
        self,
        surface: pygame.Surface,
        stage_rect: pygame.Rect,
        actor: CutsceneActorAsset,
        pose: str,
        color: Color,
    ) -> None:
        x = stage_rect.x + int(actor.x * stage_rect.width)
        y = stage_rect.y + int(actor.y * stage_rect.height)
        sprite = self.cutscene_actor_surface(actor, color, pose)
        depth_scale = self._stage_actor_depth_scale(actor.y)
        target_h = (
            stage_rect.height * self.STAGE_ACTOR_HEIGHT_FRAC * depth_scale * actor.scale
        )
        scale = target_h / max(1, sprite.get_height())
        sprite_w = max(1, int(sprite.get_width() * scale))
        sprite_h = max(1, int(sprite.get_height() * scale))
        sprite = pygame.transform.scale(sprite, (sprite_w, sprite_h))
        surface.blit(sprite, sprite.get_rect(midbottom=(x, y + self.ui(14))))
        self.draw_cutscene_actor_pose_effects(
            surface, x, y, sprite_w, sprite_h, actor, pose, color, color
        )
        label_text = actor.name[:32]
        label = self.tiny_font.render(label_text, True, color)
        label.set_alpha(168)
        surface.blit(label, label.get_rect(center=(x, y - sprite_h - self.ui(2))))
