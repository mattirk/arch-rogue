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

"""The loading screen: the animated title logo over long synchronous work.

Floor entry front-loads every actor sprite source (4.11.0), which measures up
to ~10 seconds on older Windows machines — a frozen frame that reads as a
hang. This mixin draws the Arch Rogue logo with its diamond relic spinning
(the ``menu.logo.diamond.<n>`` frames generated for 4.11.0), a caption, and a
progress bar, and repaints them from progress callbacks inside the work loop.

Design constraints:

* The work stays synchronous. Frames are repainted from ``loading_tick``
  calls sprinkled through the work (the sprite prewarm reports per-actor
  progress), not from a thread — SDL surfaces are not thread-safe.
* Absolutely failure-proof: a missing logo, a dead display, or a headless
  test run degrade to no-ops. A loading screen must never be the crash.
* Repaints are rate-limited so a tick per prewarmed actor costs a time check,
  not a display flip.
"""

from __future__ import annotations

import time
from contextlib import contextmanager

import pygame

# Where the diamond sits inside menus/title_logo.png, in source pixels.
LOGO_DIAMOND_RECT = pygame.Rect(266, 24, 70, 74)
LOGO_SOURCE_SIZE = (640, 122)
# The spin plays at this many frames per second — slow, per the art brief.
LOADING_DIAMOND_FPS = 8.0
# Repaint cadence for ticks; the animation needs no more than this.
_REPAINT_INTERVAL = 1.0 / 30.0
_BACKGROUND_FALLBACK = (10, 9, 14)
_CAPTION_COLOR = (214, 204, 176)
_BAR_COLOR = (240, 228, 160)
_BAR_BACK_COLOR = (52, 46, 38)


class LoadingScreenMixin:
    def _loading_diamond_frames(self) -> tuple[pygame.Surface, ...]:
        """The spin frames from the UI manifest, probed once, () when absent."""

        cached = getattr(self, "_loading_diamond_frame_cache", None)
        if cached is not None:
            return cached
        frames: list[pygame.Surface] = []
        assets = getattr(self, "ui_assets", None)
        if assets is not None:
            index = 0
            while True:
                surface = assets.source(f"menu.logo.diamond.{index}")
                if surface is None:
                    break
                frames.append(surface)
                index += 1
        result = tuple(frames)
        self._loading_diamond_frame_cache = result
        return result

    def spinning_logo_frame_index(self) -> int:
        """Diamond spin frame for the menu UI clock (5.0 title animation)."""

        frames = self._loading_diamond_frames()
        if not frames:
            return 0
        elapsed = float(getattr(self, "ui_elapsed", 0.0))
        return int(elapsed * LOADING_DIAMOND_FPS) % len(frames)

    def compose_spinning_logo(self, frame_index: int) -> pygame.Surface | None:
        """The title logo source with its relic diamond spun to ``frame_index``.

        Returns a fresh source-resolution surface (640x122): the authored
        diamond pixels are punched out and the requested spin frame blitted in
        their place. Frame 0 is pixel-identical to the static logo, so callers
        can use this unconditionally. Shared by the loading screen and the 5.0
        animated title menu.
        """

        assets = getattr(self, "ui_assets", None)
        logo = assets.source("menu.logo.title") if assets is not None else None
        if logo is None:
            return None
        frames = self._loading_diamond_frames()
        if not frames:
            return logo
        frame = frames[frame_index % len(frames)]
        logo = logo.copy()
        logo.fill((0, 0, 0, 0), LOGO_DIAMOND_RECT, pygame.BLEND_RGBA_MIN)
        logo.blit(frame, frame.get_rect(center=LOGO_DIAMOND_RECT.center))
        return logo

    def loading_screen_active(self) -> bool:
        return bool(getattr(self, "_loading_screen_label", ""))

    @contextmanager
    def loading_screen(self, label: str):
        """Show the animated loading screen around a long synchronous block.

        Reentrant: a nested use (a descent that also saves, say) keeps the
        outer label and the outer screen simply continues.
        """

        if self.loading_screen_active():
            yield
            return
        self._loading_screen_label = str(label)
        self._loading_screen_started = time.monotonic()
        self._loading_screen_painted = 0.0
        self._loading_screen_progress: float | None = None
        try:
            self._paint_loading_screen()
            yield
        finally:
            self._loading_screen_label = ""

    def loading_tick(self, progress: float | None = None) -> None:
        """Repaint the loading screen if due; cheap enough to call per item."""

        if not self.loading_screen_active():
            return
        if progress is not None:
            self._loading_screen_progress = max(0.0, min(1.0, float(progress)))
        now = time.monotonic()
        if now - float(getattr(self, "_loading_screen_painted", 0.0)) < _REPAINT_INTERVAL:
            return
        self._paint_loading_screen()

    def _paint_loading_screen(self) -> None:
        screen = getattr(self, "screen", None)
        if screen is None or not pygame.display.get_init():
            return
        try:
            self._loading_screen_painted = time.monotonic()
            # Keep the window responsive; input queued behind a load is stale
            # by definition, so it is deliberately dropped.
            pygame.event.pump()
            width, height = screen.get_size()
            assets = getattr(self, "ui_assets", None)
            background = (
                assets.render("menu.background.title", (width, height))
                if assets is not None
                else None
            )
            if background is not None:
                screen.blit(background, (0, 0))
            else:
                screen.fill(_BACKGROUND_FALLBACK)

            elapsed = self._loading_screen_painted - float(
                getattr(self, "_loading_screen_started", 0.0)
            )
            frames = self._loading_diamond_frames()
            frame_index = (
                int(elapsed * LOADING_DIAMOND_FPS) % len(frames)
                if frames
                else 0
            )
            logo = self.compose_spinning_logo(frame_index)
            caption_top = height // 2
            if logo is not None:
                scale = min(
                    0.62 * width / LOGO_SOURCE_SIZE[0],
                    0.28 * height / LOGO_SOURCE_SIZE[1],
                )
                # Integer scale keeps the pixel art crisp; never below 1x.
                factor = max(1, int(scale))
                scaled = pygame.transform.scale_by(logo, factor)
                rect = scaled.get_rect(
                    center=(width // 2, int(height * 0.42))
                )
                screen.blit(scaled, rect)
                caption_top = rect.bottom + max(18, height // 36)

            font = getattr(self, "font", None)
            if font is not None:
                caption = font.render(
                    str(getattr(self, "_loading_screen_label", "")),
                    True,
                    _CAPTION_COLOR,
                )
                screen.blit(
                    caption,
                    caption.get_rect(midtop=(width // 2, caption_top)),
                )
                caption_top += caption.get_height() + max(12, height // 60)

            progress = getattr(self, "_loading_screen_progress", None)
            if progress is not None:
                bar_width = max(120, int(width * 0.26))
                bar_height = max(6, height // 130)
                bar = pygame.Rect(
                    (width - bar_width) // 2,
                    caption_top,
                    bar_width,
                    bar_height,
                )
                pygame.draw.rect(screen, _BAR_BACK_COLOR, bar, border_radius=3)
                filled = bar.copy()
                filled.width = max(0, int(bar_width * progress))
                if filled.width:
                    pygame.draw.rect(screen, _BAR_COLOR, filled, border_radius=3)
            pygame.display.flip()
        except pygame.error:
            # A lost display mid-transition must not take the load down.
            pass
