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


class RenderingStoryOverlayMixin:
    def draw_story_panel(self) -> None:
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
        if panel_w <= self.ui(220) or max_h < self.ui(84):
            return
        accent = self.story_state.accent if self.story_state else self.theme.accent
        rect = pygame.Rect(x, y, panel_w, max_h)
        surface = pygame.Surface(rect.size, pygame.SRCALPHA)
        self.draw_ornate_hud_panel(
            surface,
            surface.get_rect(),
            (10, 9, 13, 220),
            (*accent, 165),
            radius=self.ui(9),
        )
        pad = self.ui(12)
        title = lines[0]
        title_surface = self.small_font.render(title, True, (244, 232, 214))
        surface.blit(title_surface, (pad, pad))
        self.draw_hud_divider(
            surface,
            pad,
            pad + title_surface.get_height() + self.ui(4),
            panel_w - pad,
            accent,
        )
        cursor_y = pad + title_surface.get_height() + self.ui(9)
        line_h = max(self.small_font.get_height() + self.ui(3), self.ui(18))
        max_lines = max(2, (max_h - cursor_y - pad) // line_h)
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
                raw_line, self.small_font, panel_w - pad * 2
            ):
                if rendered >= max_lines:
                    ellipsis = self.small_font.render("…", True, (170, 165, 155))
                    surface.blit(ellipsis, (pad, cursor_y))
                    self.screen.blit(surface, rect)
                    return
                text = self.small_font.render(wrapped, True, color)
                surface.blit(text, (pad, cursor_y))
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
        asset = self.active_cutscene_asset()
        node = self.active_cutscene_node()
        if asset is None or node is None:
            return
        width, height = self.screen.get_size()
        dim = pygame.Surface((width, height), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 255))
        self.screen.blit(dim, (0, 0))

        accent = self.story_state.accent if self.story_state else self.theme.accent
        panel_w = min(width - self.ui(28), self.ui(920))
        panel_h = min(height - self.ui(16), self.ui(620))
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
        title_text = asset.title
        if self.story_intro_pending:
            title_text = f"{asset.title} · Depth {self.current_depth}/{DUNGEON_DEPTH}"
        header_h = max(self.font.get_height(), self.small_font.get_height()) + self.ui(
            8
        )
        header_meta = node.id.replace("_", " ").title()
        meta_w = min(
            self.small_font.size(header_meta)[0] + self.ui(8),
            max(self.ui(96), (panel_w - pad * 2) // 3),
        )
        meta_x = panel_w - pad - meta_w
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
        choice_w = panel_w - pad * 2
        footer_h = self.small_font.get_height()
        choice_entries = [(choice.label, choice.detail) for choice in choices_to_draw]
        choice_heights = [
            self.cutscene_response_height(label, detail, choice_w)
            for label, detail in choice_entries
        ]
        choices_block_h = (
            sum(choice_heights) + max(0, len(choice_heights) - 1) * choice_gap
        )
        choices_start = panel_h - pad - footer_h - self.ui(10) - choices_block_h

        stage_top = pad + header_h + self.ui(12)
        available_for_stage = max(
            self.ui(54), choices_start - stage_top - self.small_font.get_height() * 3
        )
        stage_h = max(self.ui(74), min(int(panel_h * 0.38), available_for_stage))
        stage_rect = pygame.Rect(
            pad,
            stage_top,
            panel_w - pad * 2,
            stage_h,
        )
        self.draw_cutscene_stage(surface, stage_rect, node.animation, accent)

        y = stage_rect.bottom + self.ui(12)
        speaker = self.active_cutscene_speaker_name()
        speaker_rect = pygame.Rect(
            pad, y, panel_w - pad * 2, self.small_font.get_height()
        )
        self.draw_ui_text(
            surface, speaker, self.small_font, (246, 235, 210), speaker_rect
        )
        speaker_w = min(self.small_font.size(speaker)[0], speaker_rect.width)
        line_y = y + self.small_font.get_height() // 2
        pygame.draw.line(
            surface,
            (*accent, 130),
            (pad + speaker_w + self.ui(10), line_y),
            (panel_w - pad, line_y),
            self.ui(1),
        )
        y += self.small_font.get_height() + self.ui(5)
        progress = self.active_cutscene_narration_progress()
        progress_rect = pygame.Rect(pad, y, panel_w - pad * 2, max(self.ui(3), 3))
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
        y += progress_rect.height + self.ui(8)

        text_bottom = max(y + self.small_font.get_height(), choices_start - self.ui(10))
        line_h = max(self.small_font.get_height() + self.ui(3), self.ui(18))
        body_lines: list[str] = []
        visible_text = self.active_cutscene_visible_text()
        if not visible_text:
            visible_text = " "
        for paragraph in visible_text.splitlines() or [""]:
            body_lines.extend(
                self.wrap_ui_text(paragraph, self.small_font, panel_w - pad * 2)
            )
        if not narration_complete and body_lines and int(self.elapsed * 2.0) % 2 == 0:
            body_lines[-1] = f"{body_lines[-1]} |"
        max_body_lines = max(1, (text_bottom - y) // line_h)
        omitted_lines = max(0, len(body_lines) - max_body_lines)
        visible_lines = body_lines[-max_body_lines:]
        if omitted_lines and visible_lines:
            visible_lines[0] = "… " + visible_lines[0]
        for index, text_line in enumerate(visible_lines):
            color = (225, 218, 202)
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
                pygame.Rect(pad, y, panel_w - pad * 2, line_h),
            )
            y += line_h

        choice_rects = self.cutscene_response_rects(
            choice_entries, pad, choices_start, choice_w, choice_gap
        )
        for index, (choice, choice_rect) in enumerate(
            zip(choices_to_draw, choice_rects)
        ):
            choice_color = self.cutscene_choice_color(choice.choice_key, accent)
            pygame.draw.rect(
                surface,
                (24, 19, 31, 240),
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
            "Narrator speaking… Press Enter/E/Space to reveal the full line."
            if not narration_complete
            else (
                "Press 1-3 to choose a dialogue response."
                if len(choices_to_draw) >= 3
                else "Press Enter/E to advance, Esc to close non-blocking dialogue."
            )
        )
        if self.story_intro_pending and narration_complete:
            footer_text = "Press 1-3 to confirm the guest dialog, place the relic, and begin this level."
        self.draw_ui_text(
            surface,
            footer_text,
            self.small_font,
            (205, 185, 225),
            pygame.Rect(pad, panel_h - pad - footer_h, panel_w - pad * 2, footer_h),
        )
        self.screen.blit(surface, rect)

    def draw_cutscene_stage(
        self,
        surface: pygame.Surface,
        stage_rect: pygame.Rect,
        animation_id: str,
        accent: Color,
    ) -> None:
        pygame.draw.rect(
            surface, (15, 13, 21, 245), stage_rect, border_radius=self.ui(10)
        )
        pygame.draw.rect(
            surface, (*accent, 125), stage_rect, self.ui(1), border_radius=self.ui(10)
        )
        self.draw_cutscene_story_backdrop(surface, stage_rect, accent)
        self.draw_cutscene_memory_ribbon(surface, stage_rect, accent)
        horizon_y = stage_rect.y + int(stage_rect.height * 0.62)
        pygame.draw.line(
            surface,
            (*self.shade(accent, -25), 76),
            (stage_rect.x + self.ui(10), horizon_y),
            (stage_rect.right - self.ui(10), horizon_y),
            self.ui(1),
        )
        self.draw_cutscene_choice_tableau(surface, stage_rect, accent)
        for index in range(9):
            phase = self.elapsed * (0.45 + index * 0.035) + index * 1.7
            mote_x = stage_rect.x + int(
                (0.08 + (index * 0.11) % 0.86) * stage_rect.width
            )
            mote_y = stage_rect.y + int(
                (0.22 + 0.18 * math.sin(phase)) * stage_rect.height
            )
            pygame.draw.circle(surface, (*accent, 54), (mote_x, mote_y), self.ui(1))
        asset = self.active_cutscene_asset()
        if asset is None:
            return
        for actor in asset.actors.values():
            self.draw_cutscene_actor(surface, stage_rect, actor, animation_id, accent)
        self.draw_cutscene_letterbox(surface, stage_rect)

    def draw_cutscene_letterbox(
        self, surface: pygame.Surface, stage_rect: pygame.Rect
    ) -> None:
        bar_h = max(2, self.ui(5))
        pygame.draw.rect(
            surface,
            (0, 0, 0, 74),
            (stage_rect.x, stage_rect.y, stage_rect.width, bar_h),
        )
        pygame.draw.rect(
            surface,
            (0, 0, 0, 74),
            (stage_rect.x, stage_rect.bottom - bar_h, stage_rect.width, bar_h),
        )

    def draw_cutscene_memory_ribbon(
        self, surface: pygame.Surface, stage_rect: pygame.Rect, accent: Color
    ) -> None:
        asset = self.active_cutscene_asset()
        if asset is None:
            return
        actor_order = ("player", "relic", "guest", "antagonist")
        points: list[tuple[int, int]] = []
        for actor_id in actor_order:
            actor = asset.actors.get(actor_id)
            if actor is None:
                continue
            points.append(
                (
                    stage_rect.x + int(actor.x * stage_rect.width),
                    stage_rect.y + int(actor.y * stage_rect.height),
                )
            )
        if len(points) < 2:
            return
        for start, end in zip(points, points[1:]):
            pygame.draw.line(surface, (*accent, 42), start, end, self.ui(1))
        progress = self.active_cutscene_narration_progress()
        scaled = progress * (len(points) - 1)
        segment_index = min(len(points) - 2, int(scaled))
        segment_t = scaled - segment_index
        start = points[segment_index]
        end = points[segment_index + 1]
        pulse = 0.5 + 0.5 * math.sin(self.elapsed * 5.0)
        marker = (
            int(start[0] + (end[0] - start[0]) * segment_t),
            int(start[1] + (end[1] - start[1]) * segment_t),
        )
        pygame.draw.circle(
            surface, (*self.shade(accent, 42), int(92 + pulse * 86)), marker, self.ui(4)
        )
        pygame.draw.circle(surface, (*accent, 76), marker, self.ui(10), self.ui(1))

    def draw_cutscene_story_backdrop(
        self, surface: pygame.Surface, stage_rect: pygame.Rect, accent: Color
    ) -> None:
        theme = self.theme
        base = self.shade(theme.floor, -42)
        far = self.mix(base, self.shade(accent, -65), 0.35)
        for band in range(6):
            amount = band / 5
            color = self.mix(far, self.shade(theme.wall_top, -18), amount * 0.45)
            y = stage_rect.y + int(stage_rect.height * band / 6)
            h = max(1, stage_rect.height // 6 + 1)
            pygame.draw.rect(
                surface,
                (*color, 52 + band * 16),
                (stage_rect.x + self.ui(2), y, stage_rect.width - self.ui(4), h),
            )
        text = self.cutscene_story_text().lower()
        current_sentence = self.active_cutscene_current_sentence_text().lower()
        scene_text = f"{text} {current_sentence}"
        self.draw_cutscene_theme_motifs(surface, stage_rect, accent, scene_text)
        self.draw_cutscene_relic_silhouette(surface, stage_rect, accent)
        self.draw_cutscene_faction_sigil(surface, stage_rect, accent)
        beat = self.current_story_beat()
        story = self.story_state
        tags = [beat.theme_name if beat else self.theme.name]
        if story is not None:
            tags.extend([story.relic_name, story.antagonist])
        tag_x = stage_rect.x + self.ui(8)
        tag_y = stage_rect.y + self.ui(5)
        for tag in tags[:3]:
            rendered = self.small_font.render(tag[:32], True, (205, 198, 188))
            rendered.set_alpha(112)
            surface.blit(rendered, (tag_x, tag_y))
            tag_y += max(self.ui(10), rendered.get_height() - self.ui(4))

    def draw_cutscene_theme_motifs(
        self, surface: pygame.Surface, stage_rect: pygame.Rect, accent: Color, text: str
    ) -> None:
        if any(
            term in text
            for term in ("ash", "ember", "flame", "fire", "forge", "foundry")
        ):
            for index in range(14):
                phase = self.elapsed * (1.4 + index * 0.05) + index
                x = stage_rect.x + int(
                    (0.08 + (index * 0.071) % 0.88) * stage_rect.width
                )
                y = (
                    stage_rect.bottom
                    - self.ui(12)
                    - int((math.sin(phase) * 0.5 + 0.5) * stage_rect.height * 0.55)
                )
                pygame.draw.circle(
                    surface, (245, 126, 64, 92), (x, y), max(1, self.ui(1))
                )
        if any(
            term in text
            for term in ("frozen", "moon", "water", "aquifer", "sunken", "river")
        ):
            for index in range(4):
                y = stage_rect.y + int(stage_rect.height * (0.42 + index * 0.11))
                wave = []
                for step in range(9):
                    x = stage_rect.x + int(stage_rect.width * step / 8)
                    wy = y + int(
                        math.sin(self.elapsed * 1.2 + step + index) * self.ui(3)
                    )
                    wave.append((x, wy))
                pygame.draw.lines(
                    surface, (*self.shade(accent, 35), 58), False, wave, self.ui(1)
                )
        if any(term in text for term in ("thorn", "root", "forest", "vine", "wilder")):
            for index in range(5):
                x = stage_rect.x + int(stage_rect.width * (0.1 + index * 0.19))
                points = []
                for step in range(5):
                    points.append(
                        (
                            x + int(math.sin(step + index) * self.ui(5)),
                            stage_rect.bottom - self.ui(5 + step * 12),
                        )
                    )
                pygame.draw.lines(surface, (68, 142, 86, 84), False, points, self.ui(1))
                for px, py in points[1::2]:
                    pygame.draw.circle(surface, (98, 176, 94, 82), (px, py), self.ui(2))
        if any(
            term in text
            for term in ("crypt", "grave", "bone", "dead", "ossuary", "coffin")
        ):
            for index in range(4):
                x = stage_rect.x + int(stage_rect.width * (0.18 + index * 0.2))
                y = stage_rect.bottom - self.ui(13 + (index % 2) * 7)
                pygame.draw.line(
                    surface,
                    (198, 190, 172, 72),
                    (x - self.ui(5), y),
                    (x + self.ui(5), y),
                    self.ui(1),
                )
                pygame.draw.line(
                    surface,
                    (198, 190, 172, 72),
                    (x, y - self.ui(5)),
                    (x, y + self.ui(5)),
                    self.ui(1),
                )
        if any(
            term in text
            for term in ("star", "mirror", "choir", "veil", "reliquary", "dream")
        ):
            for index in range(12):
                x = stage_rect.x + int(
                    stage_rect.width * (0.07 + (index * 0.083) % 0.86)
                )
                y = stage_rect.y + int(
                    stage_rect.height * (0.12 + (index * 0.137) % 0.42)
                )
                pulse = 0.5 + 0.5 * math.sin(self.elapsed * 2.2 + index)
                pygame.draw.circle(
                    surface,
                    (*self.shade(accent, 45), int(42 + pulse * 62)),
                    (x, y),
                    max(1, self.ui(1)),
                )
        if any(term in text for term in ("blood", "curse", "sin", "price", "debt")):
            for index in range(5):
                x = stage_rect.x + int(stage_rect.width * (0.32 + index * 0.09))
                y = stage_rect.y + int(stage_rect.height * (0.18 + (index % 3) * 0.13))
                pygame.draw.circle(surface, (180, 45, 68, 72), (x, y), self.ui(2))
                pygame.draw.polygon(
                    surface,
                    (180, 45, 68, 62),
                    [(x, y - self.ui(5)), (x - self.ui(2), y), (x + self.ui(2), y)],
                )
        if any(term in text for term in ("gate", "door", "threshold", "lock", "key")):
            door_w = max(self.ui(26), stage_rect.width // 9)
            door_h = max(self.ui(46), int(stage_rect.height * 0.46))
            door_rect = pygame.Rect(0, 0, door_w, door_h)
            door_rect.midbottom = (stage_rect.centerx, stage_rect.bottom - self.ui(8))
            pulse = 0.5 + 0.5 * math.sin(self.elapsed * 2.2)
            pygame.draw.rect(
                surface, (20, 15, 25, 150), door_rect, border_radius=self.ui(5)
            )
            pygame.draw.rect(
                surface,
                (*accent, int(82 + pulse * 76)),
                door_rect,
                self.ui(1),
                border_radius=self.ui(5),
            )
            crack_x = door_rect.centerx + int(math.sin(self.elapsed * 0.8) * self.ui(2))
            pygame.draw.line(
                surface,
                (*self.shade(accent, 55), 95),
                (crack_x, door_rect.y + self.ui(6)),
                (crack_x, door_rect.bottom - self.ui(4)),
                self.ui(1),
            )
        if any(
            term in text for term in ("bell", "toll", "chant", "choir", "song", "voice")
        ):
            center = (
                stage_rect.x + int(stage_rect.width * 0.24),
                stage_rect.y + int(stage_rect.height * 0.28),
            )
            for index in range(3):
                radius = self.ui(18 + index * 13) + int(
                    math.sin(self.elapsed * 2.1 + index) * self.ui(2)
                )
                pygame.draw.arc(
                    surface,
                    (236, 218, 138, 68 - index * 12),
                    (center[0] - radius, center[1] - radius, radius * 2, radius * 2),
                    -0.7,
                    0.7,
                    self.ui(1),
                )
        if any(
            term in text for term in ("map", "road", "path", "route", "cartographer")
        ):
            path_points = []
            for index in range(6):
                path_points.append(
                    (
                        stage_rect.x + int(stage_rect.width * (0.12 + index * 0.15)),
                        stage_rect.bottom - self.ui(12 + (index % 2) * 12),
                    )
                )
            pygame.draw.lines(
                surface, (224, 206, 150, 78), False, path_points, self.ui(1)
            )
            for point in path_points[1::2]:
                pygame.draw.circle(surface, (224, 206, 150, 86), point, self.ui(2))
        if any(
            term in text for term in ("chain", "pulley", "machine", "engine", "gear")
        ):
            for index in range(5):
                rect = pygame.Rect(
                    stage_rect.right - self.ui(42),
                    stage_rect.y + self.ui(18 + index * 16),
                    self.ui(14),
                    self.ui(9),
                )
                pygame.draw.ellipse(surface, (198, 170, 126, 78), rect, self.ui(1))
            gear_center = (
                stage_rect.right - self.ui(30),
                stage_rect.bottom - self.ui(28),
            )
            for spoke in range(8):
                angle = self.elapsed * 0.45 + math.tau * spoke / 8
                pygame.draw.line(
                    surface,
                    (198, 170, 126, 74),
                    gear_center,
                    (
                        gear_center[0] + int(math.cos(angle) * self.ui(16)),
                        gear_center[1] + int(math.sin(angle) * self.ui(16)),
                    ),
                    self.ui(1),
                )
            pygame.draw.circle(
                surface, (198, 170, 126, 78), gear_center, self.ui(15), self.ui(1)
            )
        if any(
            term in text
            for term in ("antler", "hunter", "beast", "stag", "predator", "prey")
        ):
            base = (
                stage_rect.x + int(stage_rect.width * 0.72),
                stage_rect.y + int(stage_rect.height * 0.28),
            )
            for side in (-1, 1):
                trunk_end = (base[0] + side * self.ui(18), base[1] - self.ui(24))
                pygame.draw.line(
                    surface, (214, 212, 192, 78), base, trunk_end, self.ui(1)
                )
                for branch in range(3):
                    start = (
                        base[0] + side * self.ui(8 + branch * 5),
                        base[1] - self.ui(8 + branch * 6),
                    )
                    end = (start[0] + side * self.ui(9), start[1] - self.ui(8))
                    pygame.draw.line(
                        surface, (214, 212, 192, 70), start, end, self.ui(1)
                    )
        if any(
            term in text for term in ("coin", "auction", "broker", "payment", "marked")
        ):
            for index in range(6):
                center = (
                    stage_rect.x + int(stage_rect.width * (0.18 + index * 0.09)),
                    stage_rect.bottom - self.ui(10 + (index % 3) * 5),
                )
                pygame.draw.circle(
                    surface, (213, 165, 72, 82), center, self.ui(4), self.ui(1)
                )
                pygame.draw.circle(surface, (213, 165, 72, 46), center, self.ui(1))
        if any(
            term in text for term in ("mirror", "mask", "reflection", "glass", "face")
        ):
            for index in range(4):
                cx = stage_rect.x + int(stage_rect.width * (0.42 + index * 0.08))
                cy = stage_rect.y + int(stage_rect.height * (0.18 + (index % 2) * 0.1))
                shard = [
                    (cx, cy - self.ui(9)),
                    (cx + self.ui(8), cy),
                    (cx - self.ui(3), cy + self.ui(11)),
                ]
                pygame.draw.polygon(surface, (218, 232, 245, 54), shard)
                pygame.draw.polygon(
                    surface, (*self.shade(accent, 42), 72), shard, self.ui(1)
                )

    def draw_cutscene_relic_silhouette(
        self, surface: pygame.Surface, stage_rect: pygame.Rect, accent: Color
    ) -> None:
        center = (stage_rect.centerx, stage_rect.y + int(stage_rect.height * 0.36))
        progress = self.active_cutscene_narration_progress()
        pulse = 0.5 + 0.5 * math.sin(self.elapsed * 3.4)
        radius = self.ui(20) + int(self.ui(12) * progress + self.ui(5) * pulse)
        pygame.draw.circle(surface, (*self.shade(accent, -25), 34), center, radius)
        pygame.draw.circle(surface, (*accent, 64), center, radius, self.ui(1))
        aspect = self.cutscene_relic_aspect()
        color = (*self.shade(accent, 52), 118)
        if aspect == "bell":
            rect = pygame.Rect(0, 0, self.ui(30), self.ui(30))
            rect.center = center
            pygame.draw.arc(surface, color, rect, math.pi, math.tau, self.ui(2))
            pygame.draw.line(
                surface,
                color,
                (rect.x, center[1] + self.ui(6)),
                (rect.right, center[1] + self.ui(6)),
                self.ui(2),
            )
        elif aspect == "lantern":
            rect = pygame.Rect(
                center[0] - self.ui(13),
                center[1] - self.ui(18),
                self.ui(26),
                self.ui(34),
            )
            pygame.draw.rect(surface, color, rect, self.ui(2), border_radius=self.ui(3))
            pygame.draw.line(
                surface,
                color,
                (center[0] - self.ui(8), rect.y),
                (center[0], rect.y - self.ui(8)),
                self.ui(1),
            )
            pygame.draw.line(
                surface,
                color,
                (center[0] + self.ui(8), rect.y),
                (center[0], rect.y - self.ui(8)),
                self.ui(1),
            )
            pygame.draw.circle(surface, (245, 174, 92, 86), center, self.ui(7))
        elif aspect == "key":
            pygame.draw.circle(
                surface,
                color,
                (center[0] - self.ui(8), center[1] - self.ui(4)),
                self.ui(7),
                self.ui(2),
            )
            pygame.draw.line(
                surface,
                color,
                (center[0], center[1]),
                (center[0] + self.ui(20), center[1] + self.ui(14)),
                self.ui(2),
            )
            pygame.draw.line(
                surface,
                color,
                (center[0] + self.ui(14), center[1] + self.ui(10)),
                (center[0] + self.ui(20), center[1] + self.ui(5)),
                self.ui(1),
            )
        elif aspect == "crown":
            crown = [
                (center[0] - self.ui(20), center[1] + self.ui(9)),
                (center[0] - self.ui(12), center[1] - self.ui(10)),
                (center[0], center[1] + self.ui(3)),
                (center[0] + self.ui(12), center[1] - self.ui(10)),
                (center[0] + self.ui(20), center[1] + self.ui(9)),
            ]
            pygame.draw.lines(surface, color, False, crown, self.ui(2))
        elif aspect == "mirror":
            pygame.draw.ellipse(
                surface,
                color,
                (
                    center[0] - self.ui(13),
                    center[1] - self.ui(18),
                    self.ui(26),
                    self.ui(34),
                ),
                self.ui(2),
            )
            pygame.draw.line(
                surface,
                color,
                (center[0], center[1] + self.ui(16)),
                (center[0], center[1] + self.ui(28)),
                self.ui(2),
            )
        elif aspect == "chain":
            for index in range(3):
                rect = pygame.Rect(
                    center[0] - self.ui(20) + index * self.ui(14),
                    center[1] - self.ui(7),
                    self.ui(18),
                    self.ui(12),
                )
                pygame.draw.ellipse(surface, color, rect, self.ui(2))
        elif aspect == "map":
            rect = pygame.Rect(
                center[0] - self.ui(18),
                center[1] - self.ui(13),
                self.ui(36),
                self.ui(26),
            )
            pygame.draw.rect(surface, color, rect, self.ui(1), border_radius=self.ui(2))
            pygame.draw.line(
                surface,
                color,
                (rect.x + self.ui(6), rect.y + self.ui(18)),
                (rect.right - self.ui(5), rect.y + self.ui(7)),
                self.ui(1),
            )
        elif aspect == "vessel":
            urn = [
                (center[0] - self.ui(14), center[1] - self.ui(9)),
                (center[0] - self.ui(8), center[1] + self.ui(17)),
                (center[0] + self.ui(8), center[1] + self.ui(17)),
                (center[0] + self.ui(14), center[1] - self.ui(9)),
            ]
            pygame.draw.polygon(surface, color, urn, self.ui(2))
            pygame.draw.line(
                surface,
                (*self.shade(accent, 70), 92),
                (center[0] - self.ui(10), center[1]),
                (center[0] + self.ui(10), center[1]),
                self.ui(1),
            )
        elif aspect == "seed":
            pygame.draw.ellipse(
                surface,
                color,
                (
                    center[0] - self.ui(10),
                    center[1] - self.ui(17),
                    self.ui(20),
                    self.ui(34),
                ),
                self.ui(2),
            )
            pygame.draw.line(
                surface,
                color,
                (center[0], center[1] - self.ui(12)),
                (center[0], center[1] + self.ui(12)),
                self.ui(1),
            )
        elif aspect == "spike":
            spike = [
                (center[0], center[1] - self.ui(24)),
                (center[0] + self.ui(9), center[1] + self.ui(20)),
                (center[0] - self.ui(9), center[1] + self.ui(20)),
            ]
            pygame.draw.polygon(surface, color, spike, self.ui(2))
        else:
            pygame.draw.line(
                surface,
                color,
                (center[0], center[1] - self.ui(22)),
                (center[0], center[1] + self.ui(22)),
                self.ui(2),
            )
            pygame.draw.circle(surface, color, center, self.ui(6), self.ui(1))

    def draw_cutscene_faction_sigil(
        self, surface: pygame.Surface, stage_rect: pygame.Rect, accent: Color
    ) -> None:
        if self.story_state is None:
            return
        seed = sum(ord(char) for char in self.story_state.faction)
        center = (stage_rect.right - self.ui(34), stage_rect.y + self.ui(34))
        radius = self.ui(18)
        sides = 5 + seed % 4
        points = []
        for index in range(sides):
            angle = -math.pi / 2 + math.tau * index / sides + self.elapsed * 0.08
            wobble = 0.78 + 0.22 * ((seed >> index) & 1)
            points.append(
                (
                    center[0] + int(math.cos(angle) * radius * wobble),
                    center[1] + int(math.sin(angle) * radius * wobble),
                )
            )
        pygame.draw.polygon(surface, (*self.shade(accent, -35), 54), points)
        pygame.draw.polygon(surface, (*accent, 116), points, self.ui(1))
        initials = "".join(
            part[0] for part in self.story_state.faction.split()[:2]
        ).upper()
        label = self.small_font.render(initials[:2], True, self.shade(accent, 50))
        label.set_alpha(126)
        surface.blit(label, label.get_rect(center=center))

    def draw_cutscene_choice_tableau(
        self, surface: pygame.Surface, stage_rect: pygame.Rect, accent: Color
    ) -> None:
        if not self.active_cutscene_narration_complete():
            self.draw_cutscene_narrator_wave(surface, stage_rect, accent)
            return
        choices = self.active_cutscene_choices()
        if not choices:
            return
        asset = self.active_cutscene_asset()
        source = None
        if asset is not None:
            source = asset.actors.get("relic") or asset.actors.get("guest")
        if source is not None:
            source_x = stage_rect.x + int(source.x * stage_rect.width)
            source_y = stage_rect.y + int(source.y * stage_rect.height)
        else:
            source_x, source_y = stage_rect.center
        count = min(3, len(choices))
        for index, choice in enumerate(choices[:count]):
            center = (
                stage_rect.x + int(stage_rect.width * (0.34 + index * 0.16)),
                stage_rect.bottom - self.ui(18),
            )
            color = self.cutscene_choice_color(choice.choice_key, accent)
            pulse = 0.5 + 0.5 * math.sin(self.elapsed * 2.8 + index * 1.7)
            pygame.draw.line(
                surface,
                (*color, int(36 + pulse * 56)),
                (source_x, source_y),
                center,
                self.ui(1),
            )
            self.draw_cutscene_choice_glyph(
                surface,
                center,
                choice.choice_key,
                self.ui(10),
                alpha=int(86 + pulse * 92),
            )

    def draw_cutscene_narrator_wave(
        self, surface: pygame.Surface, stage_rect: pygame.Rect, accent: Color
    ) -> None:
        source = (stage_rect.x + self.ui(20), stage_rect.y + self.ui(24))
        target = (stage_rect.centerx, stage_rect.y + int(stage_rect.height * 0.34))
        node = self.active_cutscene_node()
        asset = self.active_cutscene_asset()
        if node is not None and asset is not None and node.speaker in asset.actors:
            actor = asset.actors[node.speaker]
            target = (
                stage_rect.x + int(actor.x * stage_rect.width),
                stage_rect.y + int(actor.y * stage_rect.height),
            )
        progress = self.active_cutscene_narration_progress()
        for index in range(4):
            t = (progress + index * 0.18 + self.elapsed * 0.08) % 1.0
            x = int(source[0] + (target[0] - source[0]) * t)
            y = int(source[1] + (target[1] - source[1]) * t)
            wobble = int(math.sin(self.elapsed * 4.0 + index) * self.ui(3))
            pygame.draw.circle(
                surface,
                (*self.shade(accent, 48), 80 - index * 10),
                (x, y + wobble),
                max(1, self.ui(2)),
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
        color = self.cutscene_actor_color(actor, accent)
        x = stage_rect.x + int((actor.x + dx) * stage_rect.width)
        y = stage_rect.y + int((actor.y + dy) * stage_rect.height)
        shadow_w = int(54 * actor.scale * frame_scale)
        shadow_h = max(6, int(14 * actor.scale * frame_scale))
        shadow = pygame.Surface((shadow_w, shadow_h), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 92), shadow.get_rect())
        surface.blit(shadow, shadow.get_rect(center=(x, y + self.ui(20))))

        node = self.active_cutscene_node()
        if node is not None and node.speaker == actor.id:
            glow_radius = int(42 * actor.scale * frame_scale)
            glow = pygame.Surface((glow_radius * 2, glow_radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(
                glow,
                (*color, 38 + int(22 * (0.5 + 0.5 * math.sin(self.elapsed * 3.6)))),
                (glow_radius, glow_radius),
                glow_radius,
            )
            surface.blit(glow, glow.get_rect(center=(x, y - self.ui(18))))

        sprite = self.cutscene_actor_surface(actor, color, pose)
        scale = actor.scale * frame_scale * (1.0 + max(0, self.ui_scale - 1) * 0.16)
        sprite_w = max(1, int(sprite.get_width() * scale))
        sprite_h = max(1, int(sprite.get_height() * scale))
        sprite = pygame.transform.scale(sprite, (sprite_w, sprite_h))
        sprite.set_alpha(max(0, min(255, int(255 * alpha))))
        surface.blit(sprite, sprite.get_rect(midbottom=(x, y + self.ui(16))))
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
        t = self.active_cutscene.node_elapsed
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
                return (
                    frame.dx + (next_frame.dx - frame.dx) * phase,
                    frame.dy + (next_frame.dy - frame.dy) * phase,
                    frame.scale + (next_frame.scale - frame.scale) * phase,
                    frame.alpha + (next_frame.alpha - frame.alpha) * phase,
                    frame.pose,
                )
            elapsed += frame.duration
        frame = frames[-1]
        return frame.dx, frame.dy, frame.scale, frame.alpha, frame.pose

    def cutscene_actor_surface(
        self, actor: CutsceneActorAsset, color: Color, pose: str = "idle"
    ) -> pygame.Surface:
        if actor.sprite == "player":
            sprite = self.sprites.player_sprites.get(
                self.player.class_name, self.sprites.player
            ).copy()
            if pose in ("vow", "guard", "defy"):
                pygame.draw.line(
                    sprite,
                    (245, 236, 190),
                    (sprite.get_width() // 2, 8),
                    (sprite.get_width() // 2 + 12, 2),
                    max(1, self.ui_scale),
                )
            return sprite
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
        pygame.draw.ellipse(sprite, (*color, 44), (5, 51, 44, 18))
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
        pygame.draw.circle(sprite, (*color, ring_alpha), (27, 34), 24)
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
        top = y + self.ui(16) - sprite_h
        if actor.id == "guest":
            self.draw_cutscene_guest_prop(
                surface, x + sprite_w // 3, top + self.ui(12), color
            )
            if pose in ("plead", "reach", "warn"):
                for index in range(3):
                    phase = self.elapsed * 2.4 + index * 1.1
                    mote = (
                        x - self.ui(22 - index * 9),
                        top
                        + self.ui(12 + index * 5)
                        + int(math.sin(phase) * self.ui(3)),
                    )
                    pygame.draw.circle(
                        surface, (*color, 96 - index * 18), mote, self.ui(2)
                    )
            if pose == "shudder":
                pygame.draw.line(
                    surface,
                    (190, 45, 70, 110),
                    (x - self.ui(13), top),
                    (x + self.ui(11), top + self.ui(24)),
                    self.ui(1),
                )
        elif actor.id == "player":
            if pose in ("vow", "guard"):
                shield = pygame.Surface((self.ui(42), self.ui(42)), pygame.SRCALPHA)
                pygame.draw.circle(
                    shield,
                    (108, 218, 156, 52),
                    shield.get_rect().center,
                    self.ui(20),
                    self.ui(2),
                )
                surface.blit(shield, shield.get_rect(center=(x, top + self.ui(24))))
            elif pose == "defy":
                pygame.draw.line(
                    surface,
                    (232, 83, 74, 150),
                    (x - self.ui(17), top + self.ui(36)),
                    (x + self.ui(19), top + self.ui(10)),
                    self.ui(2),
                )
                pygame.draw.line(
                    surface,
                    (245, 228, 170, 120),
                    (x - self.ui(11), top + self.ui(12)),
                    (x + self.ui(23), top + self.ui(33)),
                    self.ui(1),
                )
            elif pose == "price":
                pygame.draw.circle(
                    surface,
                    (190, 45, 70, 120),
                    (x + self.ui(16), top + self.ui(21)),
                    self.ui(3),
                )
        elif actor.id == "relic":
            pulse = 0.5 + 0.5 * math.sin(self.elapsed * 5.0)
            for index in range(2):
                radius = self.ui(18 + index * 11) + int(pulse * self.ui(6))
                pygame.draw.circle(
                    surface,
                    (*accent, 44 - index * 12),
                    (x, top + sprite_h // 2),
                    radius,
                    self.ui(1),
                )
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
        elif actor.id == "antagonist":
            pulse = 0.5 + 0.5 * math.sin(self.elapsed * 2.8)
            crown_y = top + self.ui(8)
            pygame.draw.circle(
                surface,
                (232, 83, 74, int(42 + pulse * 42)),
                (x, top + sprite_h // 2),
                self.ui(28),
                self.ui(1),
            )
            for side in (-1, 1):
                pygame.draw.line(
                    surface,
                    (232, 83, 74, 104),
                    (x, crown_y),
                    (x + side * self.ui(20), crown_y - self.ui(12)),
                    self.ui(1),
                )
                pygame.draw.line(
                    surface,
                    (232, 83, 74, 72),
                    (x + side * self.ui(12), crown_y + self.ui(4)),
                    (x + side * self.ui(28), crown_y + self.ui(18)),
                    self.ui(1),
                )

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
            surface, (15, 13, 21, 245), stage_rect, border_radius=self.ui(10)
        )
        self.draw_cutscene_story_backdrop(surface, stage_rect, accent)
        pygame.draw.rect(
            surface, (*accent, 125), stage_rect, self.ui(1), border_radius=self.ui(10)
        )
        horizon_y = stage_rect.y + int(stage_rect.height * 0.64)
        pygame.draw.line(
            surface,
            (*self.shade(accent, -25), 76),
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

        source = (
            stage_rect.x + int(relic_actor.x * stage_rect.width),
            stage_rect.y + int(relic_actor.y * stage_rect.height) - self.ui(18),
        )
        for index, (choice_key, _label, _detail) in enumerate(options[:3]):
            choice_color = self.cutscene_choice_color(choice_key, accent)
            pulse = 0.5 + 0.5 * math.sin(self.elapsed * 2.8 + index * 1.7)
            center = (
                stage_rect.x + int(stage_rect.width * (0.34 + index * 0.16)),
                stage_rect.bottom - self.ui(18),
            )
            pygame.draw.line(
                surface,
                (*choice_color, int(36 + pulse * 56)),
                source,
                center,
                self.ui(1),
            )
            self.draw_cutscene_choice_glyph(
                surface,
                center,
                choice_key,
                self.ui(10),
                alpha=int(86 + pulse * 92),
            )

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
        shadow_w = max(1, int(54 * actor.scale))
        shadow_h = max(6, int(14 * actor.scale))
        shadow = pygame.Surface((shadow_w, shadow_h), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 92), shadow.get_rect())
        surface.blit(shadow, shadow.get_rect(center=(x, y + self.ui(20))))
        sprite = self.cutscene_actor_surface(actor, color, pose)
        scale = actor.scale * (1.0 + max(0, self.ui_scale - 1) * 0.16)
        sprite_w = max(1, int(sprite.get_width() * scale))
        sprite_h = max(1, int(sprite.get_height() * scale))
        sprite = pygame.transform.scale(sprite, (sprite_w, sprite_h))
        surface.blit(sprite, sprite.get_rect(midbottom=(x, y + self.ui(16))))
        self.draw_cutscene_actor_pose_effects(
            surface, x, y, sprite_w, sprite_h, actor, pose, color, color
        )
        label_text = actor.name[:32]
        label = self.tiny_font.render(label_text, True, color)
        label.set_alpha(168)
        surface.blit(label, label.get_rect(center=(x, y - sprite_h - self.ui(2))))
