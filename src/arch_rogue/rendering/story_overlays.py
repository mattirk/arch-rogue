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

# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

import math

import pygame

from ..constants import DUNGEON_DEPTH
from ..models import Color
from ..story import (
    CutsceneActorAsset,
    SpriteAnimationFrameAsset,
    StageAsset,
    StagePropAsset,
    format_asset_text,
)

StagePoint = tuple[float, float]
StageActorState = tuple[float, float, str, float, float, bool]


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _smoothstep(value: float) -> float:
    value = _clamp(value, 0.0, 1.0)
    return value * value * (3.0 - 2.0 * value)


def _lerp_point(start: StagePoint, end: StagePoint, amount: float) -> StagePoint:
    return (
        start[0] + (end[0] - start[0]) * amount,
        start[1] + (end[1] - start[1]) * amount,
    )


def _bezier_control(start: StagePoint, end: StagePoint, bow: float) -> StagePoint:
    return (
        (start[0] + end[0]) * 0.5,
        (start[1] + end[1]) * 0.5 + bow,
    )


def _quadratic_bezier(
    start: StagePoint,
    control: StagePoint,
    end: StagePoint,
    progress: float,
) -> StagePoint:
    progress = _clamp(progress, 0.0, 1.0)
    remaining = 1.0 - progress
    return (
        remaining * remaining * start[0]
        + 2.0 * remaining * progress * control[0]
        + progress * progress * end[0],
        remaining * remaining * start[1]
        + 2.0 * remaining * progress * control[1]
        + progress * progress * end[1],
    )


def _delayed_phase(elapsed: float, span: float, delay: float) -> float:
    delay = _clamp(delay, 0.0, span - 0.001)
    return _clamp((elapsed - delay) / max(0.001, span - delay), 0.0, 1.0)


def _duel_breathing(
    clock: float,
    seed: float,
    amount_x: float,
    amount_y: float,
    envelope: float = 1.0,
) -> StagePoint:
    return (
        math.sin(clock * 3.1 + seed) * amount_x * envelope,
        math.sin(clock * 2.3 + seed * 1.7) * amount_y * envelope,
    )


class RenderingStoryOverlayMixin:
    def draw_story_panel(self) -> None:
        self._story_panel_rect: pygame.Rect | None = None
        self._story_panel_render_key: object | None = None
        # 4.2.2: scroll introspection resets whenever the panel is not drawn
        # so input paging never acts on a stale overflow range.
        self._story_panel_scrollbar_rect: pygame.Rect | None = None
        self._story_panel_scroll_max = 0
        if not getattr(self, "quest_info_visible", True):
            return
        lines = self.story_panel_lines()
        if not lines:
            return
        width, height = self.screen.get_size()
        mobile = bool(getattr(self, "mobile_mode", False))
        if mobile:
            layout = self.mobile_layout()
            viewport = layout.world_viewport
            gameplay = layout.gameplay_rect.move(-viewport.x, -viewport.y)
            margin = self.ui(14)
            x = gameplay.x + margin
            y = gameplay.y + margin
            panel_w = gameplay.width - margin * 2
            max_h = gameplay.height - margin * 2
        else:
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
            # 4.2.x — a little more air between quest texts and the frame.
            content.inflate(-self.ui(5) * 2, -self.ui(3) * 2)
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

        def body_color(raw_line: str) -> Color:
            if raw_line.startswith("Depth ") or raw_line.startswith("Outcome:"):
                return (238, 218, 164)
            if raw_line.startswith("Story forces:"):
                return (205, 185, 225)
            return (210, 205, 192)

        def wrap_body(width: int) -> list[tuple[str, Color]]:
            wrapped: list[tuple[str, Color]] = []
            for raw_line in lines[1:]:
                color = body_color(raw_line)
                for piece in self.wrap_ui_text(raw_line, self.small_font, width):
                    wrapped.append((piece, color))
            return wrapped

        # 4.2.2: overflowing story text scrolls instead of truncating with an
        # ellipsis. When it overflows, the body wraps a little narrower so the
        # right-rail scrollbar never overlaps a line.
        body_width = content.width
        wrapped_lines = wrap_body(body_width)
        if len(wrapped_lines) > max_lines:
            body_width = max(1, content.width - self.ui(9))
            wrapped_lines = wrap_body(body_width)
        scroll_max = max(0, len(wrapped_lines) - max_lines)
        scroll = max(
            0, min(int(getattr(self, "story_panel_scroll", 0)), scroll_max)
        )
        self.story_panel_scroll = scroll
        self._story_panel_scroll_max = scroll_max
        self._story_panel_visible_lines = max_lines
        for piece, color in wrapped_lines[scroll : scroll + max_lines]:
            text = self.small_font.render(piece, True, color)
            surface.blit(text, (content.x, cursor_y))
            cursor_y += line_h
        if scroll_max > 0:
            track = self.draw_story_panel_scrollbar(
                surface,
                content,
                divider_y + self.ui(5),
                scroll,
                max_lines,
                len(wrapped_lines),
            )
            self._story_panel_scrollbar_rect = track.move(rect.x, rect.y)
        self._story_panel_render_key = (
            tuple(lines),
            scroll,
            max_lines,
            tuple(accent),
            rect.size,
            self.ui_scale,
            id(self.small_font),
            self.asset_ui_active(),
        )
        self.screen.blit(surface, rect)

    def draw_story_panel_scrollbar(
        self,
        surface: pygame.Surface,
        content: pygame.Rect,
        top: int,
        scroll: int,
        visible_count: int,
        total_count: int,
    ) -> pygame.Rect:
        # 4.2.2: thin scrollbar on the right rail of the quest info panel's
        # body so the player can see there is more story than fits and where
        # they are within it. Mirrors the inventory/options scrollbars'
        # recessed track + ember-gold thumb so the panels read as one family.
        track = pygame.Rect(
            content.right - self.ui(4),
            top,
            self.ui(4),
            max(1, content.bottom - top),
        )
        pygame.draw.rect(
            surface, (*self.HUD_INK, 235), track, border_radius=self.ui(3)
        )
        pygame.draw.rect(
            surface,
            (*self.HUD_IRON_DARK, 255),
            track,
            max(1, self.ui(1)),
            border_radius=self.ui(3),
        )
        thumb_h = max(
            self.ui(14), int(track.height * visible_count / total_count)
        )
        max_scroll = max(1, total_count - visible_count)
        travel = max(1, track.height - thumb_h)
        clamped_scroll = max(0, min(scroll, max_scroll))
        thumb_y = track.y + int(travel * clamped_scroll / max_scroll)
        thumb = pygame.Rect(track.x, thumb_y, track.width, thumb_h)
        pygame.draw.rect(
            surface, self.HUD_GOLD, thumb, border_radius=self.ui(3)
        )
        pygame.draw.rect(
            surface,
            self.shade(self.HUD_GOLD, 40),
            thumb,
            max(1, self.ui(1)),
            border_radius=self.ui(3),
        )
        return track

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
        heights: list[int] | None = None,
    ) -> list[pygame.Rect]:
        rects: list[pygame.Rect] = []
        cursor_y = y
        for index, (label, detail) in enumerate(entries):
            rect_h = (
                heights[index]
                if heights is not None and index < len(heights)
                else self.cutscene_response_height(label, detail, width)
            )
            rects.append(pygame.Rect(x, cursor_y, width, rect_h))
            cursor_y += rect_h + gap
        return rects

    def draw_cutscene_response_text(
        self,
        surface: pygame.Surface,
        label: str,
        detail: str,
        text_rect: pygame.Rect,
        *,
        center_vertically: bool = False,
    ) -> None:
        label_lines, detail_lines = self.cutscene_response_lines(
            label, detail, text_rect.width
        )
        label_height = self.small_font.get_height()
        detail_height = self.tiny_font.get_height()
        detail_gap = self.ui(3) if detail_lines else 0
        text_height = (
            len(label_lines) * label_height
            + detail_gap
            + len(detail_lines) * detail_height
        )
        cursor_y = text_rect.y
        if center_vertically:
            cursor_y += max(0, (text_rect.height - text_height) // 2)
        for line in label_lines:
            self.draw_ui_text(
                surface,
                line,
                self.small_font,
                (246, 235, 210),
                pygame.Rect(
                    text_rect.x, cursor_y, text_rect.width, label_height
                ),
            )
            cursor_y += label_height
        cursor_y += detail_gap
        for line in detail_lines:
            self.draw_ui_text(
                surface,
                line,
                self.tiny_font,
                (184, 178, 168),
                pygame.Rect(
                    text_rect.x, cursor_y, text_rect.width, detail_height
                ),
            )
            cursor_y += detail_height

    def draw_quest_cutscene_overlay(self) -> None:
        with self.fitted_ui_layout((960, 540)):
            self._draw_quest_cutscene_overlay_fitted()

    def _draw_quest_cutscene_overlay_fitted(self) -> None:
        self._cutscene_narration_scrollbar_rect: pygame.Rect | None = None
        self._cutscene_narration_scroll_max = 0
        self._cutscene_narration_visible_lines = 0
        asset = self.active_cutscene_asset()
        node = self.active_cutscene_node()
        if asset is None or node is None:
            return
        width, height = self.screen.get_size()
        background = self.ui_asset_surface("cutscene.background", (width, height))
        self._cutscene_background_asset_used = background is not None
        if background is not None:
            # Clear first so a malformed/partially transparent optional asset
            # can never leak the previous gameplay frame around the overlay.
            self.screen.fill((0, 0, 0))
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

        (
            _narration,
            visible_text,
            narration_complete,
            progress,
        ) = self.active_cutscene_narration_snapshot()
        choices = self.active_cutscene_choices()
        choices_to_draw = choices[: min(9, len(choices))] if narration_complete else []
        choice_gap = max(self.ui(4), 6)
        choice_w = inner.width
        show_input_hints = not bool(getattr(self, "mobile_mode", False))
        footer_h = self.small_font.get_height() if show_input_hints else 0
        choice_entries = [(choice.label, choice.detail) for choice in choices_to_draw]
        choice_heights = [
            self.cutscene_response_height(label, detail, choice_w)
            for label, detail in choice_entries
        ]
        choices_block_h = (
            sum(choice_heights) + max(0, len(choice_heights) - 1) * choice_gap
        )
        footer_gap = self.ui(10) if show_input_hints else 0
        choices_start = inner.bottom - footer_h - footer_gap - choices_block_h

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
        text_top = y
        max_body_lines = max(0, (text_bottom - text_top) // line_h)
        visible_text = visible_text or " "

        def wrap_narration(width: int) -> list[str]:
            wrapped: list[str] = []
            for paragraph in visible_text.splitlines() or [""]:
                wrapped.extend(self.wrap_ui_text(paragraph, self.small_font, width))
            return wrapped

        body_width = narrator_rect.width
        body_lines = wrap_narration(body_width)
        if narration_complete and len(body_lines) > max_body_lines:
            body_width = max(1, narrator_rect.width - self.ui(9))
            body_lines = wrap_narration(body_width)

        scroll_max = (
            max(0, len(body_lines) - max_body_lines) if max_body_lines else 0
        )
        self._cutscene_narration_visible_lines = max_body_lines
        scroll = 0
        if narration_complete:
            if scroll_max <= 0:
                scroll = 0
                self.cutscene_narration_follow_tail = True
            elif getattr(self, "cutscene_narration_follow_tail", True):
                scroll = scroll_max
            else:
                scroll = max(
                    0,
                    min(
                        int(getattr(self, "cutscene_narration_scroll", 0)),
                        scroll_max,
                    ),
                )
            self.cutscene_narration_scroll = scroll
            self._cutscene_narration_scroll_max = scroll_max
            visible_lines = body_lines[scroll : scroll + max_body_lines]
            omitted_lines = scroll
        else:
            self.cutscene_narration_scroll = 0
            self.cutscene_narration_follow_tail = True
            omitted_lines = max(0, len(body_lines) - max_body_lines)
            visible_lines = body_lines[-max_body_lines:] if max_body_lines else []
            if body_lines and int(self.elapsed * 2.4) % 2 == 0:
                if visible_lines:
                    visible_lines[-1] = f"{visible_lines[-1]} |"
            if omitted_lines and visible_lines:
                visible_lines[0] = "… " + visible_lines[0]

        for index, text_line in enumerate(visible_lines):
            color = (228, 220, 204)
            is_current_line = index == len(visible_lines) - 1 and not narration_complete
            source_index = scroll + index if narration_complete else omitted_lines + index
            if source_index == 0 and self.story_intro_pending:
                color = (238, 218, 164)
            elif is_current_line:
                color = self.mix((238, 218, 164), accent, 0.22)
            self.draw_ui_text(
                surface,
                text_line,
                self.small_font,
                color,
                pygame.Rect(narrator_rect.x, y, body_width, line_h),
            )
            y += line_h
        if narration_complete and scroll_max > 0:
            track = self.draw_story_panel_scrollbar(
                surface,
                narrator_rect,
                text_top,
                scroll,
                max_body_lines,
                len(body_lines),
            )
            self._cutscene_narration_scrollbar_rect = track.move(rect.topleft)

        choice_rects = self.cutscene_response_rects(
            choice_entries,
            inner.x,
            choices_start,
            choice_w,
            choice_gap,
            choice_heights,
        )
        self._cutscene_choice_rects = [
            choice_rect.move(rect.topleft) for choice_rect in choice_rects
        ]
        self._cutscene_choice_asset_used = False
        for index, (choice, choice_rect) in enumerate(
            zip(choices_to_draw, choice_rects)
        ):
            self.draw_cutscene_choice_option(
                surface,
                choice_rect,
                choice.choice_key,
                index,
                choice.label,
                choice.detail,
                is_selected=index == getattr(self, "cutscene_cursor", 0),
            )

        if show_input_hints:
            footer_text = (
                "Narrator speaking… Enter/E/Space or gamepad A reveals the full line."
                if not narration_complete
                else (
                    "Arrow keys select · Enter/E confirms · 1-3 quick-picks · D-pad + A."
                    if choices_to_draw
                    else "Enter/E or gamepad A advances. Esc/B closes non-blocking dialogue."
                )
            )
            if self.story_intro_pending and narration_complete:
                footer_text = (
                    "Arrow keys select · Enter/E confirms · 1-3 quick-picks the guest relic."
                )
            if narration_complete and self._cutscene_narration_scroll_max > 0:
                action_hint = (
                    "Arrows select · Enter/E confirms."
                    if choices_to_draw
                    else "Enter/E or gamepad A advances."
                )
                footer_text = (
                    "Scroll: wheel/PgUp/PgDn/right stick · " + action_hint
                )
            self.draw_ui_text(
                surface,
                footer_text,
                self.small_font,
                (205, 185, 225),
                pygame.Rect(
                    inner.x, inner.bottom - footer_h, inner.width, footer_h
                ),
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
    # Curtains stay gathered at the sides so the authored stage and actor
    # performance remain visible throughout narration.

    STAGE_CACHE_LIMIT = 96

    STAGE_STONE = (54, 49, 58)
    STAGE_STONE_DARK = (28, 25, 32)
    STAGE_IRON = (74, 70, 82)
    STAGE_TAPESTRY = (60, 36, 52)
    STAGE_FLAME = (208, 138, 74)
    # Stage actors move slowly and gently so the scene reads as a measured
    # tableau rather than a fidgeting crowd.
    STAGE_ACTOR_TIME_SCALE = 0.40
    STAGE_ACTOR_MOVE_DAMP = 0.6

    # Stage depth / sizing (milestone 3.11). The stage floor begins at this
    # normalized y (matches ``draw_stage_floor``). Actors are scaled by a
    # perspective curve: figures near the back wall are smaller, figures near
    # the front of the stage are larger, so the set reads with real depth
    # instead of a flat row of equally-sized cutouts.
    STAGE_FLOOR_TOP = 0.62
    STAGE_BACK_SCALE = 0.62
    STAGE_FRONT_SCALE = 1.18
    STAGE_ACTOR_HEIGHT_FRAC = 0.38
    # South-facing PixelLab performance clips serve declarative non-duel beats
    # and the duelist's brief audience-facing pause at the left home mark.
    # Quieter listening poses keep their directional idle clip.
    STAGE_PLAYER_ACT_POSES = frozenset(("guard", "vow", "price", "defy"))

    # Player vs antagonist duel cycle (milestone 3.11). When a cutscene casts
    # both a ``player`` and an ``antagonist`` actor, they run at each other,
    # clash in the middle, retreat to their marks, pause, and repeat. Phases
    # are expressed as fractions of the loop period so the choreography stays
    # data-independent and allocation-free.
    STAGE_DUEL_TIMING_REFERENCE = 6.0
    STAGE_DUEL_PERIOD = 6.9
    STAGE_DUEL_CLIP_TIME_SCALE = 0.60
    # Travel and witness beats are roughly 11% slower while the attack exchange
    # stays crisp. The remaining two-second audience-facing tail shows all eight
    # act frames once at the authored 4 FPS.
    STAGE_DUEL_PHASE_APPROACH = 1.80 / STAGE_DUEL_PERIOD
    STAGE_DUEL_PHASE_CLASH = 1.296 / STAGE_DUEL_PERIOD
    STAGE_DUEL_PHASE_RETREAT = 1.80 / STAGE_DUEL_PERIOD
    STAGE_DUEL_GAP = 0.045
    STAGE_DUEL_ANTAGONIST_ALPHA = 0.88
    # A clash is a staged exchange rather than one held pose: the hero commits
    # first, then the Gate Warden counters as the hero recovers. Progress is
    # normalized per actor so differently sized non-looping clips both play in
    # full, independent of the cutscene's global clock.
    STAGE_DUEL_ATTACK_WINDOWS = ((0.0, 0.56), (0.42, 1.0))
    STAGE_DUEL_IMPACT_BEATS = (0.20, 0.62)
    STAGE_DUEL_IMPACT_HALF_WIDTH = 0.09
    STAGE_DUEL_IMPACT_HEIGHT = 0.14
    STAGE_DUEL_RECOIL_X = 0.008
    # Obstacle avoidance: a center-stage prop such as the altar blocks the
    # direct duel path. The duelers route around it, passing to opposite sides
    # and clashing just in front of it, so the altar reads as solid and
    # unpassable instead of something they walk through.
    STAGE_DUEL_DETOUR_FORWARD = 0.07
    STAGE_DUEL_DETOUR_MAX_Y = 0.92
    # Natural movement tuning. Approach and retreat follow quadratic
    # bezier curves whose control points bow the actors slightly
    # forward-and-inward, so the path reads as stagecraft footing rather than
    # a straight-line slide. A subtle breathing sway keeps the rest and clash
    # holds alive, and a small desync phase offset stops the two duelers from
    # moving in perfect lockstep.
    STAGE_DUEL_PATH_BOW = 0.035
    STAGE_DUEL_APPROACH_HOLD = (0.54, 0.70)
    STAGE_DUEL_RETREAT_HOLD = (0.38, 0.62)
    STAGE_DUEL_BREATH_X = 0.0035
    STAGE_DUEL_BREATH_Y = 0.0025
    # Each cycle picks one deterministic tactical plan from the run/story seed.
    # The values vary pressure, lane, clearance, feint mark, and initiative but
    # always keep both fighters on their own side of the central obstacle.
    STAGE_DUEL_TACTICS = (
        {
            "name": "measured",
            "clash_x": 0.0,
            "clash_y": 0.0,
            "clearance": 0.09,
            "blend_p": 0.56,
            "blend_a": 0.56,
            "feint_p": 0.0,
            "feint_a": 0.0,
            "waypoint_y": 0.0,
            "approach_delay_p": 0.0,
            "approach_delay_a": 0.025,
            "retreat_delay_p": 0.0,
            "retreat_delay_a": 0.025,
            "pose_p": "vow",
            "pose_a": "threaten",
        },
        {
            "name": "player_press",
            "clash_x": 0.024,
            "clash_y": 0.016,
            "clearance": 0.082,
            "blend_p": 0.66,
            "blend_a": 0.48,
            "feint_p": 0.012,
            "feint_a": -0.018,
            "waypoint_y": 0.012,
            "approach_delay_p": 0.0,
            "approach_delay_a": 0.05,
            "retreat_delay_p": 0.04,
            "retreat_delay_a": 0.0,
            "pose_p": "defy",
            "pose_a": "watch",
        },
        {
            "name": "antagonist_press",
            "clash_x": -0.024,
            "clash_y": 0.012,
            "clearance": 0.082,
            "blend_p": 0.48,
            "blend_a": 0.66,
            "feint_p": -0.018,
            "feint_a": 0.012,
            "waypoint_y": 0.01,
            "approach_delay_p": 0.05,
            "approach_delay_a": 0.0,
            "retreat_delay_p": 0.0,
            "retreat_delay_a": 0.04,
            "pose_p": "guard",
            "pose_a": "threaten",
        },
        {
            "name": "wide_feint",
            "clash_x": 0.0,
            "clash_y": -0.014,
            "clearance": 0.108,
            "blend_p": 0.44,
            "blend_a": 0.44,
            "feint_p": -0.024,
            "feint_a": -0.024,
            "waypoint_y": -0.012,
            "approach_delay_p": 0.015,
            "approach_delay_a": 0.04,
            "retreat_delay_p": 0.04,
            "retreat_delay_a": 0.015,
            "pose_p": "guard",
            "pose_a": "watch",
        },
        {
            "name": "close_exchange",
            "clash_x": 0.008,
            "clash_y": 0.02,
            "clearance": 0.075,
            "blend_p": 0.64,
            "blend_a": 0.64,
            "feint_p": 0.018,
            "feint_a": 0.018,
            "waypoint_y": 0.016,
            "approach_delay_p": 0.03,
            "approach_delay_a": 0.0,
            "retreat_delay_p": 0.0,
            "retreat_delay_a": 0.03,
            "pose_p": "defy",
            "pose_a": "threaten",
        },
    )

    def _stage_cache_key(self, asset_id, layer, size, accent, extra=()):
        theme = getattr(self, "theme", None)
        context = (
            getattr(theme, "name", ""),
            round(float(self.ui_scale_factor()), 4),
            bool(getattr(self, "legacy_graphics", False)),
        )
        return (asset_id, layer, size, accent, extra, context)

    def _stage_cache(self) -> dict[tuple, pygame.Surface]:
        cache = getattr(self, "_stage_surface_cache", None)
        if cache is None:
            cache = {}
            self._stage_surface_cache = cache
        return cache

    def clear_stage_render_cache(self) -> None:
        self._stage_surface_cache = {}

    def _cached_stage_layer(self, key, size, painter):
        cache = self._stage_cache()
        cached = cache.get(key)
        if cached is not None and cached.get_size() == size:
            return cached
        if len(cache) >= self.STAGE_CACHE_LIMIT:
            cache.clear()
        surface = pygame.Surface(size, pygame.SRCALPHA)
        painter(surface)
        cache[key] = surface
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



    def draw_cutscene_stage(self, surface, stage_rect, animation_id, accent):
        asset = self.active_cutscene_asset()
        stage = asset.stage if asset is not None else StageAsset()
        pygame.draw.rect(
            surface, self.STAGE_STONE_DARK, stage_rect, border_radius=self.ui(10)
        )
        # With a full authored scene backdrop, the painted set replaces
        # the procedural back wall, floor, and proscenium wholesale; only the
        # live layers (props, actors, lights, curtain) draw on top of it.
        full_set = self.draw_stage_full_set(surface, stage_rect, stage, accent)
        if not full_set:
            self.draw_stage_backdrop(surface, stage_rect, stage, accent)
            self.draw_stage_floor(surface, stage_rect, stage, accent)
        # Wall dressing belongs behind the cast. Grounded props join actors in
        # one depth-sorted pass below so an altar correctly occludes a figure
        # behind it while a dueler in front can occlude the altar.
        self.draw_stage_props(surface, stage_rect, stage, accent, grounded=False)
        # Resolve the duel once per frame so every actor and the clash flash
        # share the same choreography state without recomputing it.
        duel = self._cutscene_duel_state()
        self._frame_duel_state = duel
        if asset is not None:
            entries = []
            for prop in stage.props:
                if self._stage_prop_is_grounded(prop):
                    entries.append((prop.y, 1, "prop", prop))
            for actor in asset.actors.values():
                moving = False
                if duel is not None and actor.id in duel:
                    dx, dy, pose, alpha, frame_scale, moving = duel[actor.id]
                else:
                    dx, dy, frame_scale, alpha, pose = self.cutscene_actor_frame(
                        actor.id, animation_id
                    )
                payload = (actor, dx, dy, frame_scale, alpha, pose, moving)
                entries.append((actor.y + dy, 0, "actor", payload))
            entries.sort(key=lambda entry: (entry[0], entry[1]))
            for _depth, _priority, entry_kind, payload in entries:
                if entry_kind == "prop":
                    self._draw_stage_prop(surface, stage_rect, payload, accent)
                    continue
                actor, dx, dy, frame_scale, alpha, pose, moving = payload
                self._render_cutscene_actor(
                    surface,
                    stage_rect,
                    actor,
                    dx,
                    dy,
                    frame_scale,
                    alpha,
                    pose,
                    accent,
                    moving=moving,
                )
        else:
            self.draw_stage_props(surface, stage_rect, stage, accent, grounded=True)
            self._frame_duel_state = None
        self._draw_duel_clash_flash(surface, stage_rect)
        self.draw_stage_lighting(surface, stage_rect, stage, accent)
        if stage.proscenium and not full_set:
            # The authored set frames itself; the procedural stone arch only
            # dresses the legacy/fallback stage.
            self.draw_stage_proscenium(surface, stage_rect, accent)
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

    # Full authored scene backdrops per stage. Each entry maps the
    # stage's backdrop id to (ui asset key, floor-horizon fraction within the
    # art). The art is cover-scaled to the stage width and vertically anchored
    # so its painted floor line lands on STAGE_FLOOR_TOP, keeping actor
    # perspective and duel choreography aligned with the painted floor.
    STAGE_FULL_SET_ASSETS = {
        "omen": ("stage.backdrop.omen", 0.66),
        "dialogue": ("stage.backdrop.dialogue", 0.74),
    }

    def draw_stage_full_set(self, surface, stage_rect, stage, accent) -> bool:
        """Blit the full authored set for this stage; False -> procedural."""
        entry = self.STAGE_FULL_SET_ASSETS.get(stage.backdrop)
        if entry is None or not self.asset_ui_active():
            return False
        asset_key, art_horizon = entry
        library = getattr(self, "ui_assets", None)
        source = library.source(asset_key) if library is not None else None
        if source is None:
            return False
        asset = self.active_cutscene_asset()
        asset_id = asset.id if asset is not None else "_default"
        key = self._stage_cache_key(
            asset_id, "backdrop-full", stage_rect.size, None, (stage.backdrop,)
        )

        def paint(layer):
            w, h = layer.get_size()
            scaled_h = max(1, round(source.get_height() * w / source.get_width()))
            scene = pygame.transform.scale(source, (w, scaled_h))
            if scaled_h <= h:
                layer.blit(scene, (0, h - scaled_h))
                return
            # Anchor the art's floor horizon onto the stage's floor line.
            crop_y = round(art_horizon * scaled_h - self.STAGE_FLOOR_TOP * h)
            crop_y = max(0, min(scaled_h - h, crop_y))
            layer.blit(scene.subsurface((0, crop_y, w, h)), (0, 0))

        layer = self._cached_stage_layer(key, stage_rect.size, paint)
        surface.blit(layer, stage_rect.topleft)
        return True

    def draw_stage_backdrop(self, surface, stage_rect, stage, accent):
        asset = self.active_cutscene_asset()
        asset_id = asset.id if asset is not None else "_default"
        scenery = self._stage_scenery_source() if self.asset_ui_active() else None
        key = self._stage_cache_key(
            asset_id,
            "backdrop",
            stage_rect.size,
            accent,
            (stage.backdrop, scenery is not None),
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
            # 4.2.x theater redesign: the authored vaulted-hall art hangs as a
            # painted scenery flat across the back wall. An aspect-true band
            # centered on the art's arcade row (arches, column bases, candle
            # glows) fills the wall so the hall reads with depth behind the
            # actors; the gradient above stays underneath as the darkness.
            if scenery is not None:
                horizon = max(1, int(h * 0.62))
                src_w, src_h = scenery.get_size()
                band_h = max(1, min(src_h, round(horizon * src_w / max(1, w))))
                band_y = max(0, min(src_h - band_h, round(src_h * 0.60 - band_h / 2)))
                band = scenery.subsurface((0, band_y, src_w, band_h))
                flat = pygame.transform.scale(band, (w, horizon)).copy()
                # Sink the flat into the stage gloom so live light reads on top.
                flat.fill((174, 168, 190, 255), special_flags=pygame.BLEND_RGBA_MULT)
                layer.blit(flat, (0, 0))
            # A subtle top-down light gradient so the back wall reads as lit
            # from above without any transparent circle/halo overlays. Drawn
            # on a scratch surface and blitted so the translucent bands tint
            # the wall (and scenery flat) instead of overwriting its pixels.
            warm = self.mix(self.STAGE_FLAME, accent, 0.2)
            light_bands = 6
            wall_h = max(1, int(h * 0.62))
            glow = pygame.Surface((w, wall_h), pygame.SRCALPHA)
            for band in range(light_bands):
                t = band / (light_bands - 1)
                y = int(wall_h * band / light_bands)
                bh = max(1, wall_h // light_bands + 1)
                pygame.draw.rect(glow, (*warm, int(18 * (1.0 - t))), (0, y, w, bh))
            layer.blit(glow, (0, 0))
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

    def _stage_scenery_source(self) -> pygame.Surface | None:
        """Decoded cutscene backdrop art for the stage's painted scenery flat."""
        library = getattr(self, "ui_assets", None)
        if library is None:
            return None
        return library.source("cutscene.background")

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

    # Authored sprite props are sized per kind as a
    # fraction of the stage height, tuned to the procedural painters'
    # footprints so authored stage layouts keep their composition (and the
    # altar keeps reading as the duel obstacle it is).
    STAGE_PROP_HEIGHT_FRACS = {
        "pillar": 0.90,
        "altar": 0.27,
        "lectern": 0.36,
        "candelabra": 0.46,
        "banner": 0.44,
    }
    STAGE_PROP_PAINTER_NAMES = {
        "pillar": "_paint_prop_pillar",
        "altar": "_paint_prop_altar",
        "lectern": "_paint_prop_lectern",
        "candelabra": "_paint_prop_candelabra",
        "banner": "_paint_prop_banner",
    }

    def _stage_prop_is_grounded(self, prop: StagePropAsset) -> bool:
        return prop.kind != "banner" and prop.y >= self.STAGE_FLOOR_TOP

    def draw_stage_props(
        self, surface, stage_rect, stage, accent, grounded: bool | None = None
    ):
        for prop in stage.props:
            if (
                grounded is not None
                and self._stage_prop_is_grounded(prop) is not grounded
            ):
                continue
            self._draw_stage_prop(surface, stage_rect, prop, accent)

    def _draw_stage_prop(self, surface, stage_rect, prop, accent):
        x = stage_rect.x + int(prop.x * stage_rect.width)
        y = stage_rect.y + int(prop.y * stage_rect.height)
        sway = 0.0
        if prop.amplitude > 0:
            sway = math.sin(self.elapsed * 1.6 + prop.phase) * prop.amplitude
        if self._draw_stage_prop_sprite(surface, stage_rect, prop, x, y, sway):
            return
        painter_name = self.STAGE_PROP_PAINTER_NAMES.get(prop.kind)
        if painter_name is None:
            return
        painter = getattr(self, painter_name)
        color = self.stage_role_color(prop.color, accent)
        painter(surface, x, y, prop.scale, color, prop.phase, sway)

    def _draw_stage_prop_sprite(self, surface, stage_rect, prop, x, y, sway):
        """Blit the authored sprite for a stage prop; False -> use painter.

        Props are perspective-scaled by their stage y so a candelabra
        near the back wall reads smaller than one near the front of the stage,
        matching the painted floor's depth. The base lands on the floor mark
        so grounded props don't float against the authored backdrop.
        """
        height_frac = self.STAGE_PROP_HEIGHT_FRACS.get(prop.kind)
        if height_frac is None:
            return False
        base = self.sprites.stage_prop_visual(prop.kind)
        if base is None:
            return False
        # Perspective scale: props further back (lower y, closer to the
        # horizon at STAGE_FLOOR_TOP) are smaller, props further forward are
        # larger — the same depth curve the actors use.
        depth_scale = self._stage_prop_depth_scale(prop.y)
        target_h = max(
            1.0, stage_rect.height * height_frac * prop.scale * depth_scale
        )
        frame = self.sprites.stage_prop_visual(
            prop.kind, target_h / max(1, base.surface.get_height())
        )
        if frame is None:
            return False
        sway_px = int(sway * self.ui(3))
        anchor_x, anchor_y = frame.anchor
        if prop.kind == "banner":
            # Banners hang from their y mark; sway drifts the cloth sideways.
            dest = (x + sway_px - anchor_x, y - self.ui(3) - anchor_y)
        else:
            # Grounded props: the anchor is the base, so it lands on the
            # floor mark directly (no legacy +ui(8) lift that floated props
            # above the painted floor).
            dest = (x + sway_px - anchor_x, y - anchor_y)
        if self._stage_prop_is_grounded(prop):
            self._draw_stage_contact_shadow(
                surface,
                (x + sway_px, y),
                frame.surface.get_width(),
                alpha=88,
            )
        surface.blit(frame.surface, dest)
        return True

    def _draw_stage_contact_shadow(self, surface, foot, source_width, alpha=104):
        """Draw a cached soft contact shadow under a grounded stage element."""
        raw_w = max(self.ui(8), int(source_width * 0.46))
        bucket = max(4, self.ui(8))
        shadow_w = max(bucket, int(round(raw_w / bucket)) * bucket)
        shadow_h = max(self.ui(2), int(shadow_w * 0.16))
        cache_key = ("contact-shadow", shadow_w, shadow_h, int(alpha))
        cache = self._stage_cache()
        shadow = cache.get(cache_key)
        if shadow is None or shadow.get_size() != (shadow_w, shadow_h):
            shadow = pygame.Surface((shadow_w, shadow_h), pygame.SRCALPHA)
            pygame.draw.ellipse(
                shadow,
                (5, 3, 8, max(0, min(255, int(alpha)))),
                shadow.get_rect(),
            )
            if len(cache) >= self.STAGE_CACHE_LIMIT:
                cache.clear()
            cache[cache_key] = shadow
        dest = shadow.get_rect(
            center=(int(foot[0]), int(foot[1] - shadow_h * 0.15))
        )
        surface.blit(shadow, dest)

    def _stage_prop_depth_scale(self, y):
        """Perspective scale for a stage prop at normalized y.

        Props above the floor horizon (y < STAGE_FLOOR_TOP) are wall-mounted
        (banners, high candelabra arms) and keep a flat scale so they don't
        shrink into the wall. Grounded props on the floor plane follow the
        same depth curve as actors.
        """
        if y < self.STAGE_FLOOR_TOP:
            return 1.0
        depth_t = max(
            0.0,
            min(1.0, (y - self.STAGE_FLOOR_TOP) / (1.0 - self.STAGE_FLOOR_TOP)),
        )
        return (
            self.STAGE_BACK_SCALE
            + (self.STAGE_FRONT_SCALE - self.STAGE_BACK_SCALE) * depth_t
        )



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
        if not stage.footlights:
            return
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

    def draw_stage_proscenium(self, surface, stage_rect, accent):
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
        authored = self.ui_asset_surface("stage.curtain.open", stage_rect.size)
        if authored is not None:
            surface.blit(authored, stage_rect.topleft)
            self._cutscene_curtain_asset_used = True
            return
        self._cutscene_curtain_asset_used = False
        curtain = stage.curtain
        tapestry = self.stage_role_color(curtain.color, accent)
        sides = ("left", "right") if curtain.side == "both" else (curtain.side,)
        for side in sides:
            self._draw_curtain_panel(
                surface,
                stage_rect,
                side,
                curtain,
                tapestry,
                accent,
            )

    def _draw_curtain_panel(
        self, surface, stage_rect, side, curtain, tapestry, accent
    ):
        ox, oy = stage_rect.topleft
        w = stage_rect.width
        h = stage_rect.height
        half = curtain.gather * 0.5
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



    def draw_cutscene_choice_option(
        self,
        surface: pygame.Surface,
        choice_rect: pygame.Rect,
        choice_key: str,
        index: int,
        label: str,
        detail: str,
        *,
        is_selected: bool = False,
    ) -> None:
        """Draw one story option using authored UI or the procedural fallback."""
        choice_color = self.cutscene_choice_color(
            choice_key,
            self.story_state.accent if self.story_state else self.theme.accent,
        )
        key_size = min(self.ui(36), choice_rect.height - self.ui(12))
        key_rect = pygame.Rect(
            choice_rect.x + self.ui(7),
            choice_rect.y + (choice_rect.height - key_size) // 2,
            key_size,
            key_size,
        )
        panel = self.ui_asset_surface("cutscene.choice.panel", choice_rect.size)
        icon = self.ui_asset_surface(
            f"cutscene.choice.icon.{choice_key}", key_rect.size
        )
        authored = panel is not None and icon is not None
        panel_content = (
            self.ui_asset_content_rect("cutscene.choice.panel", choice_rect)
            if authored
            else None
        )
        self._cutscene_choice_asset_used = bool(
            getattr(self, "_cutscene_choice_asset_used", False) or authored
        )

        if authored:
            assert panel is not None and icon is not None
            if panel_content is not None:
                socket_width = panel_content.x - choice_rect.x
                divider_gap = max(1, socket_width // 10)
                socket_right = panel_content.x - divider_gap
                key_rect.centerx = (choice_rect.x + socket_right) // 2
            surface.blit(panel, choice_rect)
            if is_selected:
                glow = pygame.Surface(choice_rect.size, pygame.SRCALPHA)
                pygame.draw.rect(
                    glow,
                    (*choice_color, 18),
                    glow.get_rect().inflate(-self.ui(2), -self.ui(2)),
                    border_radius=self.ui(8),
                )
                surface.blit(glow, choice_rect)
                pygame.draw.rect(
                    surface,
                    (*choice_color, 120),
                    choice_rect,
                    max(self.ui(1), 1),
                    border_radius=self.ui(9),
                )
            if is_selected:
                pygame.draw.circle(
                    surface,
                    (*choice_color, 24),
                    key_rect.center,
                    key_size // 2 + self.ui(2),
                )
            surface.blit(icon, key_rect)
            if not getattr(self, "mobile_mode", False):
                badge_size = max(8, min(key_size // 3, self.ui(11)))
                badge_rect = pygame.Rect(0, 0, badge_size, badge_size)
                badge_rect.bottomright = key_rect.bottomright
                pygame.draw.circle(
                    surface,
                    (*self.shade(choice_color, -70), 245),
                    badge_rect.center,
                    badge_size // 2,
                )
                pygame.draw.circle(
                    surface,
                    (*self.HUD_GOLD, 220),
                    badge_rect.center,
                    badge_size // 2,
                    max(1, self.ui(1)),
                )
                self.draw_ui_text(
                    surface,
                    str(index + 1),
                    self.tiny_font,
                    (246, 235, 210),
                    badge_rect,
                    align="center",
                    valign="center",
                )
        else:
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
            if not getattr(self, "mobile_mode", False):
                self.draw_ui_text(
                    surface,
                    str(index + 1),
                    self.font,
                    choice_color,
                    key_rect,
                    align="center",
                    valign="center",
                )

        if authored and panel_content is not None:
            text_rect = panel_content.inflate(
                -self.ui(8),
                -self.ui(4),
            )
        else:
            text_x = max(
                key_rect.right + self.ui(12),
                choice_rect.x + self.ui(62),
            )
            text_rect = pygame.Rect(
                text_x,
                choice_rect.y + self.ui(7),
                max(1, choice_rect.right - text_x - self.ui(8)),
                choice_rect.height - self.ui(14),
            )
        self.draw_cutscene_response_text(
            surface,
            label,
            detail,
            text_rect,
            center_vertically=authored and panel_content is not None,
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
        moving: bool = False,
    ) -> None:
        color = self.cutscene_actor_color(actor, accent)
        x = stage_rect.x + int((actor.x + dx) * stage_rect.width)
        y = stage_rect.y + int((actor.y + dy) * stage_rect.height)

        direction = self._cutscene_actor_direction(actor, dx)
        sprite, anchor = self.cutscene_actor_visual(
            actor, color, pose, direction, moving
        )
        depth_scale = self._stage_actor_depth_scale(actor.y + dy)
        base_h = stage_rect.height * self.STAGE_ACTOR_HEIGHT_FRAC
        target_h = base_h * depth_scale * actor.scale * frame_scale
        scale = target_h / max(1, sprite.get_height())
        sprite_w = max(1, int(sprite.get_width() * scale))
        sprite_h = max(1, int(sprite.get_height() * scale))
        sprite = pygame.transform.scale(sprite, (sprite_w, sprite_h))
        sprite.set_alpha(max(0, min(255, int(255 * alpha))))

        # Actor y is the foot-contact coordinate, matching grounded props and
        # the backdrop's floor plane. This keeps depth scale, sort depth, and
        # the visible floor contact in one perspective system.
        foot = (x, y)
        if actor.sprite != "relic":
            self._draw_stage_contact_shadow(surface, foot, sprite_w, alpha=88)
        if anchor is not None:
            # Asset frames carry a foot-contact anchor: land it on the mark so
            # animated frames of differing bounds never bob around the stage.
            dest = (
                foot[0] - int(anchor[0] * scale),
                foot[1] - int(anchor[1] * scale),
            )
            surface.blit(sprite, dest)
        else:
            surface.blit(sprite, sprite.get_rect(midbottom=foot))
        self.draw_cutscene_actor_pose_effects(
            surface, x, y, sprite_w, sprite_h, actor, pose, color, accent
        )

        label_text = self.cutscene_actor_label(actor)
        duel = getattr(self, "_frame_duel_state", None)
        if (
            actor.id == "guest"
            and duel is not None
            and duel.get("guest_hidden", True)
        ):
            # Suppress the floating label only while the witness is physically
            # concealed by the pillar. It returns once they clear the cover.
            label_text = ""
        if label_text:
            label = self.small_font.render(label_text, True, color)
            label_rect = label.get_rect(
                center=(x, foot[1] - sprite_h - self.ui(3))
            )
            if actor.id == "guest" and duel is not None:
                # Keep the long witness name on the clear center-facing side of
                # their body instead of letting the nearest pillar split it.
                if actor.x >= 0.5:
                    label_rect.right = x - self.ui(4)
                else:
                    label_rect.left = x + self.ui(4)
            surface.blit(label, label_rect)

    def _cutscene_stage_clock(self) -> float:
        """Clock for stage actor animation clips.

        Uses the whole-cutscene elapsed time so idle/walk clips play
        continuously across dialogue nodes; the story intro overlay has no
        active cutscene and falls back to the app-wide visual clock.
        """
        if self.active_cutscene is not None:
            return max(0.0, self.active_cutscene.elapsed)
        return self.ui_elapsed

    def _cutscene_actor_direction(self, actor: CutsceneActorAsset, dx: float) -> str:
        """Resolve a sprite facing for the frontal stage projection.

        Traveling duelists use the direction of their path through stage depth
        (including diagonals toward/away from the audience). Held poses face
        the opponent, while non-duel actors face center stage.
        """
        duel = getattr(self, "_frame_duel_state", None)
        if duel is not None:
            travel_direction = duel.get("directions", {}).get(actor.id)
            if travel_direction:
                return travel_direction
        if duel is not None and actor.id in ("player", "antagonist"):
            asset = self.active_cutscene_asset()
            other_id = "antagonist" if actor.id == "player" else "player"
            other = asset.actors.get(other_id) if asset is not None else None
            if other is not None:
                other_dx = duel[other_id][0] if other_id in duel else 0.0
                return "east" if actor.x + dx <= other.x + other_dx else "west"
        return "east" if actor.x < 0.5 else "west"

    def _stage_travel_direction(self, dx: float, dy: float) -> str:
        """Map a stage-space travel vector to one of the eight actor views."""
        horizontal = ""
        vertical = ""
        if abs(dx) >= abs(dy) * 0.35:
            horizontal = "east" if dx > 0 else "west" if dx < 0 else ""
        if abs(dy) >= abs(dx) * 0.35:
            vertical = "south" if dy > 0 else "north" if dy < 0 else ""
        if vertical and horizontal:
            return f"{vertical}-{horizontal}"
        return vertical or horizontal or "south"

    def _cutscene_actor_state(
        self,
        pose: str,
        moving: bool,
        dueling: bool,
        *,
        is_player: bool = False,
    ) -> str:
        """Map a frontal-stage performance beat to an actor sprite clip.

        Movement always wins; the attack clip is reserved for the duel's
        clash poses. Declarative player beats and the dedicated home-stage
        ``act`` pose use the authored south-facing performance. Other
        performers and quieter poses keep their directional idle clips.
        """
        if moving:
            return "walk"
        if dueling and pose in ("defy", "threaten"):
            return "attack"
        if is_player and (
            pose == "act"
            or (not dueling and pose in self.STAGE_PLAYER_ACT_POSES)
        ):
            return "act"
        return "idle"

    def cutscene_actor_visual(
        self,
        actor: CutsceneActorAsset,
        color: Color,
        pose: str,
        direction: str = "south",
        moving: bool = False,
    ) -> tuple[pygame.Surface, tuple[int, int] | None]:
        """Resolve the surface (and foot anchor) for a stage actor.

        4.2.x theater redesign: with asset sprites active, player, guest, and
        antagonist request their authored idle/walk/attack/act clips so the stage
        reads as live performers instead of static cutouts. Archetypes whose
        attack group is not authored yet retain the asset library's idle fallback.
        The relic stays procedural, and legacy graphics keep the historical look.
        """
        if actor.sprite != "relic" and self.sprites.modern_graphics_active:
            duel = getattr(self, "_frame_duel_state", None)
            dueling = duel is not None and actor.id in ("player", "antagonist")
            state = self._cutscene_actor_state(
                pose,
                moving,
                dueling,
                is_player=actor.sprite == "player",
            )
            if state == "act":
                # The theater performance group is intentionally authored only
                # from the audience-facing south view.
                direction = "south"
            clock = self._cutscene_stage_clock()
            if state == "act" and duel is not None and actor.id == "player":
                # Restart the performance when the hero reaches the left home
                # mark so every cycle gets a readable audience-facing gesture.
                clock = float(duel.get("home_act_time", clock))
            elif moving and duel is not None:
                # Match every moving performer to the deliberately slow stage
                # travel, including the witness's brief trip out of cover.
                clock *= self.STAGE_DUEL_CLIP_TIME_SCALE
            action_progress = None
            if state == "attack" and duel is not None:
                action_progress = duel.get("action_progress", {}).get(actor.id)
            if actor.sprite == "player":
                frame = self.sprites.player_visual(
                    self.player.class_name,
                    state,
                    clock,
                    clock,
                    direction=direction,
                    action_progress=action_progress,
                )
                return frame.surface, frame.anchor
            if actor.sprite == "story_guest":
                frame = self.sprites.story_guest_visual(
                    clock,
                    direction=direction,
                    moving=moving,
                )
                return frame.surface, frame.anchor
            if actor.sprite == "enemy":
                frame = self.sprites.enemy_visual(
                    "Gate Warden",
                    "brute",
                    state,
                    clock,
                    clock,
                    direction=direction,
                    action_progress=action_progress,
                )
                return frame.surface, frame.anchor
        return self.cutscene_actor_surface(actor, color, pose), None

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
            if prop.kind not in ("altar", "lectern", "throne"):
                continue
            if lo < prop.x < hi:
                dist = abs(prop.x - mid)
                if best is None or dist < best_dist:
                    best, best_dist = (prop.x, prop.y), dist
        return best

    def _cutscene_duel_clock(self) -> tuple[int, float]:
        if self.active_cutscene is None:
            return 0, 0.0
        # Whole-cutscene time keeps the duel continuous across dialogue nodes,
        # while still starting at cycle/phase zero regardless of run-global time.
        elapsed = max(0.0, self.active_cutscene.elapsed)
        period = self.STAGE_DUEL_PERIOD
        cycle = int(elapsed // period)
        return cycle, (elapsed % period) / period



    def _cutscene_duel_tactical_hash(self, cycle: int) -> int:
        """Stable per-cycle variation without allocating RNG state each frame."""
        seed = int(getattr(self, "story_seed", 0))
        depth = int(getattr(self, "current_depth", 1))
        guest_index = (
            int(getattr(self.active_cutscene, "guest_beat_index", -1))
            if self.active_cutscene is not None
            else -1
        )
        value = (
            seed
            ^ ((depth + 1) * 0x45D9F3B)
            ^ ((guest_index + 2) * 0x85EBCA6B)
            ^ ((cycle + 1) * 0x9E3779B1)
        ) & 0xFFFFFFFF
        value ^= value >> 16
        value = (value * 0x7FEB352D) & 0xFFFFFFFF
        value ^= value >> 15
        value = (value * 0x846CA68B) & 0xFFFFFFFF
        return value ^ (value >> 16)

    def _cutscene_duel_tactic_index(self, cycle: int) -> int:
        """Return one allocation-free permutation slot per five-cycle block."""
        count = len(self.STAGE_DUEL_TACTICS)
        if count <= 1:
            return 0
        block, slot = divmod(max(0, cycle), count)
        context_hash = self._cutscene_duel_tactical_hash(-1)
        start = context_hash % count
        step = 1 + ((context_hash >> 8) % (count - 1))
        while math.gcd(step, count) != 1:
            step = 1 + (step % (count - 1))
        if count == 2:
            return (start + cycle) % count
        # Rotating each complete permutation by one step keeps every block
        # unique while preventing its first tactic from repeating the prior end.
        return (start + (block + slot) * step) % count

    def _cutscene_duel_route(
        self,
        local: float,
        start: StagePoint,
        waypoint: StagePoint,
        end: StagePoint,
        hold: tuple[float, float],
        forward: bool,
    ) -> tuple[float, float, bool, float, float]:
        hold_start, hold_end = hold
        if local < hold_start:
            progress = _smoothstep(local / max(0.001, hold_start))
            control = _bezier_control(
                start,
                waypoint,
                self.STAGE_DUEL_PATH_BOW
                if forward
                else self.STAGE_DUEL_PATH_BOW * 0.5,
            )
            x, y = _quadratic_bezier(start, control, waypoint, progress)
            return x, y, local > 0.0, waypoint[0] - start[0], waypoint[1] - start[1]
        if local < hold_end:
            return waypoint[0], waypoint[1], False, 0.0, 0.0
        progress = _smoothstep((local - hold_end) / max(0.001, 1.0 - hold_end))
        control = _bezier_control(
            waypoint,
            end,
            self.STAGE_DUEL_PATH_BOW * (0.35 if forward else 0.2),
        )
        x, y = _quadratic_bezier(waypoint, control, end, progress)
        return x, y, True, end[0] - waypoint[0], end[1] - waypoint[1]

    def _cutscene_duel_guest_state(
        self,
        asset,
        cycle: int,
        phase: float,
        tactical_hash: int,
    ) -> tuple[StageActorState | None, bool, bool, str]:
        guest = asset.actors.get("guest")
        if guest is None:
            return None, True, False, ""

        guest_home = (guest.x, guest.y)
        excursion_parity = self._cutscene_duel_tactical_hash(-1) & 1
        guest_excursion = (cycle + excursion_parity) % 2 == 1
        x_variation = ((tactical_hash >> 8) & 0xFF) / 255.0
        y_variation = ((tactical_hash >> 16) & 0xFF) / 255.0
        target_x = 0.655 + x_variation * 0.015
        if guest.x < 0.5:
            target_x = 1.0 - target_x
        guest_target = (target_x, 0.655 + y_variation * 0.012)
        guest_x, guest_y = guest_home
        guest_pose = "shudder"
        guest_alpha = 0.86
        guest_scale = 0.98
        guest_moving = False
        guest_hidden = True
        guest_direction = ""

        exit_start, exit_end = 0.10, 0.28
        return_start, return_end = 0.68, 0.90
        if guest_excursion and exit_start <= phase < exit_end:
            local = (phase - exit_start) / (exit_end - exit_start)
            progress = _smoothstep(local)
            control = _bezier_control(guest_home, guest_target, -0.025)
            guest_x, guest_y = _quadratic_bezier(
                guest_home, control, guest_target, progress
            )
            guest_pose = "warn"
            guest_alpha = 0.86 + 0.14 * progress
            guest_scale = 0.98 + 0.02 * progress
            guest_moving = local > 0.0
            guest_hidden = progress < 0.38
            if guest_moving:
                guest_direction = self._stage_travel_direction(
                    guest_target[0] - guest_home[0],
                    guest_target[1] - guest_home[1],
                )
        elif guest_excursion and exit_end <= phase < return_start:
            watch_local = (phase - exit_end) / (return_start - exit_end)
            guest_x = guest_target[0] + math.sin(watch_local * math.tau) * 0.0025
            guest_y = guest_target[1] + math.sin(watch_local * math.pi) * 0.0015
            guest_alpha = 1.0
            guest_scale = 1.0 + math.sin(watch_local * math.pi) * 0.008
            guest_hidden = False
            clash_start = self.STAGE_DUEL_PHASE_APPROACH
            clash_end = clash_start + self.STAGE_DUEL_PHASE_CLASH
            retreat_end = clash_end + self.STAGE_DUEL_PHASE_RETREAT
            if clash_start <= phase < clash_end:
                guest_pose = "shudder"
            elif phase < retreat_end:
                guest_pose = "warn"
            else:
                guest_pose = "plead"
        elif guest_excursion and return_start <= phase < return_end:
            local = (phase - return_start) / (return_end - return_start)
            progress = _smoothstep(local)
            control = _bezier_control(guest_target, guest_home, -0.075)
            guest_x, guest_y = _quadratic_bezier(
                guest_target, control, guest_home, progress
            )
            guest_pose = "plead"
            guest_alpha = 1.0 - 0.14 * progress
            guest_scale = 1.0 - 0.02 * progress
            guest_moving = local > 0.0
            guest_hidden = progress > 0.02
            if guest_moving:
                guest_direction = self._stage_travel_direction(
                    guest_home[0] - guest_target[0],
                    guest_home[1] - guest_target[1],
                )

        return (
            (
                guest_x - guest_home[0],
                guest_y - guest_home[1],
                guest_pose,
                guest_alpha,
                guest_scale,
                guest_moving,
            ),
            guest_hidden,
            guest_excursion,
            guest_direction,
        )

    def _cutscene_duel_state(self):
        # Choreograph the player/antagonist duel for the current frame.
        # Returns None when the active cutscene has no duel pair, otherwise a
        # mapping with per-actor (dx, dy, pose, alpha, frame_scale, moving)
        # tuples plus tactical marks used by rendering and regression tests.
        # The duel loops on cutscene-local time while its deterministic plan
        # changes only at home-to-home cycle boundaries.
        asset = self.active_cutscene_asset()
        if asset is None:
            return None
        player = asset.actors.get("player")
        antagonist = asset.actors.get("antagonist")
        if player is None or antagonist is None:
            return None

        cycle, t = self._cutscene_duel_clock()
        tactical_hash = self._cutscene_duel_tactical_hash(cycle)
        tactic = self.STAGE_DUEL_TACTICS[self._cutscene_duel_tactic_index(cycle)]
        p_app = self.STAGE_DUEL_PHASE_APPROACH
        p_clash = p_app + self.STAGE_DUEL_PHASE_CLASH
        p_ret = p_clash + self.STAGE_DUEL_PHASE_RETREAT



        home_p = (player.x, player.y)
        home_a = (antagonist.x, antagonist.y)
        player_on_left = player.x < antagonist.x
        inward_p = 1.0 if player_on_left else -1.0
        inward_a = -inward_p
        obstacle = self._cutscene_duel_obstacle(asset, player, antagonist)
        if obstacle is not None:
            # Vary the exchange around the altar without ever entering its
            # footprint: each performer keeps a minimum margin on their side.
            obs_x, obs_y = obstacle
            clash_x = _clamp(obs_x + float(tactic["clash_x"]), 0.40, 0.60)
            clash_y = _clamp(
                obs_y + self.STAGE_DUEL_DETOUR_FORWARD + float(tactic["clash_y"]),
                obs_y + 0.035,
                self.STAGE_DUEL_DETOUR_MAX_Y,
            )
            clearance = float(tactic["clearance"])
            if player_on_left:
                meet_p = (min(clash_x - clearance, obs_x - 0.035), clash_y)
                meet_a = (max(clash_x + clearance, obs_x + 0.035), clash_y)
            else:
                meet_p = (max(clash_x + clearance, obs_x + 0.035), clash_y)
                meet_a = (min(clash_x - clearance, obs_x - 0.035), clash_y)
            clash = (clash_x, clash_y)
            center_line = obs_x
        else:
            # Keep the same tactical vocabulary on stages without an obstacle,
            # but use a tighter clearance around the cast midpoint.
            center_line = (player.x + antagonist.x) * 0.5
            clash_x = _clamp(
                center_line + float(tactic["clash_x"]),
                min(player.x, antagonist.x) + 0.10,
                max(player.x, antagonist.x) - 0.10,
            )
            clash_y = _clamp(
                (player.y + antagonist.y) * 0.5 + float(tactic["clash_y"]),
                self.STAGE_FLOOR_TOP + 0.02,
                self.STAGE_DUEL_DETOUR_MAX_Y,
            )
            clearance = max(
                self.STAGE_DUEL_GAP,
                float(tactic["clearance"]) * 0.65,
            )
            meet_p = (clash_x - inward_p * clearance, clash_y)
            meet_a = (clash_x - inward_a * clearance, clash_y)
            clash = (clash_x, clash_y)

        # The acting marks vary independently: positive feints move inward for
        # either side, while negative values widen that actor's stance.
        waypoint_p = _lerp_point(home_p, meet_p, float(tactic["blend_p"]))
        waypoint_a = _lerp_point(home_a, meet_a, float(tactic["blend_a"]))
        waypoint_p = (
            waypoint_p[0] + inward_p * float(tactic["feint_p"]),
            waypoint_p[1] + float(tactic["waypoint_y"]),
        )
        waypoint_a = (
            waypoint_a[0] + inward_a * float(tactic["feint_a"]),
            waypoint_a[1] + float(tactic["waypoint_y"]),
        )
        side_margin = 0.035
        if player_on_left:
            waypoint_p = (min(waypoint_p[0], center_line - side_margin), waypoint_p[1])
            waypoint_a = (max(waypoint_a[0], center_line + side_margin), waypoint_a[1])
        else:
            waypoint_p = (max(waypoint_p[0], center_line + side_margin), waypoint_p[1])
            waypoint_a = (min(waypoint_a[0], center_line - side_margin), waypoint_a[1])
        waypoint_p = (
            _clamp(waypoint_p[0], 0.08, 0.92),
            _clamp(
                waypoint_p[1],
                self.STAGE_FLOOR_TOP + 0.02,
                self.STAGE_DUEL_DETOUR_MAX_Y - 0.01,
            ),
        )
        waypoint_a = (
            _clamp(waypoint_a[0], 0.08, 0.92),
            _clamp(
                waypoint_a[1],
                self.STAGE_FLOOR_TOP + 0.02,
                self.STAGE_DUEL_DETOUR_MAX_Y - 0.01,
            ),
        )

        direction_p = ""
        direction_a = ""
        moving_p = False
        moving_a = False
        action_progress = None
        impact_strengths = ()
        home_act_time = None
        delay_scale = self.STAGE_DUEL_TIMING_REFERENCE / self.STAGE_DUEL_PERIOD
        if t < p_app:
            local_p = _delayed_phase(
                t,
                p_app,
                float(tactic["approach_delay_p"]) * delay_scale,
            )
            local_a = _delayed_phase(
                t,
                p_app,
                float(tactic["approach_delay_a"]) * delay_scale,
            )
            xp, yp, moving_p, travel_px, travel_py = self._cutscene_duel_route(
                local_p,
                home_p,
                waypoint_p,
                meet_p,
                self.STAGE_DUEL_APPROACH_HOLD,
                True,
            )
            xa, ya, moving_a, travel_ax, travel_ay = self._cutscene_duel_route(
                local_a,
                home_a,
                waypoint_a,
                meet_a,
                self.STAGE_DUEL_APPROACH_HOLD,
                True,
            )
            pose_p = str(tactic["pose_p"])
            pose_a = str(tactic["pose_a"])
            if moving_p:
                direction_p = self._stage_travel_direction(travel_px, travel_py)
            if moving_a:
                direction_a = self._stage_travel_direction(travel_ax, travel_ay)
        elif t < p_clash:
            clash_local = (t - p_app) / self.STAGE_DUEL_PHASE_CLASH
            envelope = math.sin(math.pi * _clamp(clash_local, 0.0, 1.0))
            cycle_sway = cycle * 0.41 + (tactical_hash & 0xFF) / 97.0
            sway_p = _duel_breathing(
                t + cycle_sway,
                0.0,
                self.STAGE_DUEL_BREATH_X,
                self.STAGE_DUEL_BREATH_Y,
                envelope,
            )
            sway_a = _duel_breathing(
                t + cycle_sway,
                1.0,
                self.STAGE_DUEL_BREATH_X,
                self.STAGE_DUEL_BREATH_Y,
                envelope,
            )
            first_beat, second_beat = self.STAGE_DUEL_IMPACT_BEATS
            impact_strengths = (
                _smoothstep(
                    1.0
                    - abs(clash_local - first_beat)
                    / self.STAGE_DUEL_IMPACT_HALF_WIDTH
                ),
                _smoothstep(
                    1.0
                    - abs(clash_local - second_beat)
                    / self.STAGE_DUEL_IMPACT_HALF_WIDTH
                ),
            )
            player_window, antagonist_window = self.STAGE_DUEL_ATTACK_WINDOWS
            action_progress = {
                "player": _clamp(
                    (clash_local - player_window[0])
                    / (player_window[1] - player_window[0]),
                    0.0,
                    1.0,
                ),
                "antagonist": _clamp(
                    (clash_local - antagonist_window[0])
                    / (antagonist_window[1] - antagonist_window[0]),
                    0.0,
                    1.0,
                ),
            }
            # Each impact pushes only its recipient away from the opponent. The
            # six-pixel-scale recoil reads clearly without violating the altar
            # side constraint or disturbing the established tactical marks.
            xp = (
                meet_p[0]
                + sway_p[0]
                - inward_p * self.STAGE_DUEL_RECOIL_X * impact_strengths[1]
            )
            yp = meet_p[1] + sway_p[1]
            xa = (
                meet_a[0]
                + sway_a[0]
                - inward_a * self.STAGE_DUEL_RECOIL_X * impact_strengths[0]
            )
            ya = meet_a[1] + sway_a[1]
            pose_p, pose_a = "defy", "threaten"
        elif t < p_ret:
            retreat_span = p_ret - p_clash
            retreat_elapsed = t - p_clash
            local_p = _delayed_phase(
                retreat_elapsed,
                retreat_span,
                float(tactic["retreat_delay_p"]) * delay_scale,
            )
            local_a = _delayed_phase(
                retreat_elapsed,
                retreat_span,
                float(tactic["retreat_delay_a"]) * delay_scale,
            )
            xp, yp, moving_p, travel_px, travel_py = self._cutscene_duel_route(
                local_p,
                meet_p,
                waypoint_p,
                home_p,
                self.STAGE_DUEL_RETREAT_HOLD,
                False,
            )
            xa, ya, moving_a, travel_ax, travel_ay = self._cutscene_duel_route(
                local_a,
                meet_a,
                waypoint_a,
                home_a,
                self.STAGE_DUEL_RETREAT_HOLD,
                False,
            )
            pose_p, pose_a = "guard", "watch"
            if moving_p:
                direction_p = self._stage_travel_direction(travel_px, travel_py)
            if moving_a:
                direction_a = self._stage_travel_direction(travel_ax, travel_ay)
        else:
            rest_local = (t - p_ret) / max(0.001, 1.0 - p_ret)
            home_act_time = max(0.0, (t - p_ret) * self.STAGE_DUEL_PERIOD)
            envelope = math.sin(math.pi * _clamp(rest_local, 0.0, 1.0))
            cycle_sway = cycle * 0.41 + (tactical_hash & 0xFF) / 97.0
            sway_p = _duel_breathing(
                t + cycle_sway,
                0.0,
                self.STAGE_DUEL_BREATH_X,
                self.STAGE_DUEL_BREATH_Y,
                envelope,
            )
            sway_a = _duel_breathing(
                t + cycle_sway,
                1.0,
                self.STAGE_DUEL_BREATH_X,
                self.STAGE_DUEL_BREATH_Y,
                envelope,
            )
            xp = home_p[0] + sway_p[0]
            yp = home_p[1] + sway_p[1]
            xa = home_a[0] + sway_a[0]
            ya = home_a[1] + sway_a[1]
            pose_p, pose_a = "act", "watch"

        directions = {}
        if direction_p:
            directions["player"] = direction_p
        if direction_a:
            directions["antagonist"] = direction_a

        # The witness alternates between pillar cover and an upstage watch mark.
        (
            guest_state,
            guest_hidden,
            guest_excursion,
            guest_direction,
        ) = self._cutscene_duel_guest_state(
            asset,
            cycle,
            min(1.0, t * self.STAGE_DUEL_PERIOD / self.STAGE_DUEL_TIMING_REFERENCE),
            tactical_hash,
        )
        if guest_direction:
            directions["guest"] = guest_direction

        state = {
            "player": (
                xp - home_p[0],
                yp - home_p[1],
                pose_p,
                1.0,
                1.0,
                moving_p,
            ),
            "antagonist": (
                xa - home_a[0],
                ya - home_a[1],
                pose_a,
                self.STAGE_DUEL_ANTAGONIST_ALPHA,
                1.0,
                moving_a,
            ),
            "directions": directions,
            "clash": clash,
            "cycle": cycle,
            "phase": t,
            "tactic": tactic["name"],
            "meet": {"player": meet_p, "antagonist": meet_a},
            "waypoints": {"player": waypoint_p, "antagonist": waypoint_a},
            "guest_hidden": guest_hidden,
            "guest_excursion": guest_excursion,
        }
        if guest_state is not None:
            state["guest"] = guest_state
        if action_progress is not None:
            state["action_progress"] = action_progress
            state["impact_strengths"] = impact_strengths
        if home_act_time is not None:
            state["home_act_time"] = home_act_time
        return state

    def _draw_duel_clash_flash(self, surface, stage_rect):
        # Two short spark bursts punctuate the hero's strike and the counter.
        duel = getattr(self, "_frame_duel_state", None)
        if duel is None:
            return
        impact_strengths = duel.get("impact_strengths", ())
        intensity = max(impact_strengths, default=0.0)
        if intensity <= 0.0:
            return
        clash_x, clash_y = duel["clash"]
        cx = stage_rect.x + int(clash_x * stage_rect.width)
        cy = (
            stage_rect.y
            + int(clash_y * stage_rect.height)
            - int(stage_rect.height * self.STAGE_DUEL_IMPACT_HEIGHT)
        )
        accent = self.story_state.accent if self.story_state else self.theme.accent
        spark = self.mix((255, 244, 210), accent, 0.25)
        # Crisp cross-slash lines and a tiny diamond core: enough contact light
        # to read over the altar without restoring the old circular glow blobs.
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
        core = self.ui(2) + int(self.ui(2) * intensity)
        pygame.draw.polygon(
            surface,
            (*spark, int(220 * intensity)),
            ((cx, cy - core), (cx + core, cy), (cx, cy + core), (cx - core, cy)),
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
        self._story_intro_choice_rects: list[pygame.Rect] = []
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
        show_input_hints = not bool(getattr(self, "mobile_mode", False))
        footer_h = self.small_font.get_height() if show_input_hints else 0
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
        footer_gap = self.ui(10) if show_input_hints else 0
        choices_start = panel_h - pad - footer_h - footer_gap - choices_block_h

        stage_top = pad + header_h + self.ui(12)
        available_for_stage = max(
            self.ui(48), choices_start - stage_top - self.small_font.get_height() * 3
        )
        stage_h = max(self.ui(52), min(int(panel_h * 0.30), available_for_stage))
        stage_rect = pygame.Rect(pad, stage_top, available_w, stage_h)
        self.draw_story_intro_stage(surface, stage_rect, accent)

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
            option_entries,
            pad,
            choices_start,
            choice_w,
            choice_gap,
            option_heights,
        )
        self._story_intro_choice_rects = [
            choice_rect.move(rect.topleft) for choice_rect in choice_rects
        ]
        self._cutscene_choice_asset_used = False
        for index, ((choice_key, label, detail), choice_rect) in enumerate(
            zip(options_to_draw, choice_rects)
        ):
            self.draw_cutscene_choice_option(
                surface,
                choice_rect,
                choice_key,
                index,
                label,
                detail,
                is_selected=index == getattr(self, "cutscene_cursor", 0),
            )

        if show_input_hints:
            footer = (
                "Arrow keys select · Enter/E confirms · 1-3 quick-picks the guest relic."
            )
            self.draw_ui_text(
                surface,
                footer,
                self.small_font,
                (205, 185, 225),
                pygame.Rect(
                    pad, panel_h - pad - footer_h, available_w, footer_h
                ),
            )
        self.screen.blit(surface, rect)

    def draw_story_intro_stage(
        self,
        surface: pygame.Surface,
        stage_rect: pygame.Rect,
        accent: Color,
    ) -> None:
        pygame.draw.rect(
            surface, self.STAGE_STONE_DARK, stage_rect, border_radius=self.ui(10)
        )
        # The relic-choice tableau rides the same authored omen set as
        # the level-intro cutscene so the story intro stops looking like a
        # cheaper cousin of the real theater. Falls back to the gradient
        # backdrop in legacy mode or if the asset is unavailable.
        stage = StageAsset(backdrop="omen")
        if not self.draw_stage_full_set(surface, stage_rect, stage, accent):
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
                    surface,
                    (*color, 255),
                    (stage_rect.x, y, stage_rect.width, bh),
                )
            pygame.draw.rect(
                surface,
                (*accent, 125),
                stage_rect,
                self.ui(1),
                border_radius=self.ui(10),
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
            "player", self.player.class_name, "player", 0.24, 0.8, 0.74, "player"
        )
        guest_actor = CutsceneActorAsset(
            "guest",
            guest.name if guest is not None else "Guest",
            "story_guest",
            0.50,
            0.78,
            0.80,
            "accent",
        )
        relic_actor = CutsceneActorAsset(
            "relic", "Relic Echo", "relic", 0.76, 0.7, 0.80, "accent"
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
        sprite, anchor = self.cutscene_actor_visual(
            actor, color, pose, self._cutscene_actor_direction(actor, 0.0)
        )
        depth_scale = self._stage_actor_depth_scale(actor.y)
        target_h = (
            stage_rect.height * self.STAGE_ACTOR_HEIGHT_FRAC * depth_scale * actor.scale
        )
        scale = target_h / max(1, sprite.get_height())
        sprite_w = max(1, int(sprite.get_width() * scale))
        sprite_h = max(1, int(sprite.get_height() * scale))
        sprite = pygame.transform.scale(sprite, (sprite_w, sprite_h))
        foot = (x, y)
        if actor.sprite != "relic":
            self._draw_stage_contact_shadow(surface, foot, sprite_w, alpha=88)
        if anchor is not None:
            surface.blit(
                sprite,
                (foot[0] - int(anchor[0] * scale), foot[1] - int(anchor[1] * scale)),
            )
        else:
            surface.blit(sprite, sprite.get_rect(midbottom=foot))
        self.draw_cutscene_actor_pose_effects(
            surface, x, y, sprite_w, sprite_h, actor, pose, color, color
        )
        label_text = actor.name[:32]
        label = self.tiny_font.render(label_text, True, color)
        label.set_alpha(168)
        surface.blit(
            label,
            label.get_rect(center=(x, foot[1] - sprite_h - self.ui(2))),
        )
