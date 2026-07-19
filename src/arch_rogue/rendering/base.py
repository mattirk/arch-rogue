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
from contextlib import contextmanager
from typing import Iterator, cast

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
        # Per-frame caches for hot-path lookups. These are invalidated every
        # frame so they never go stale within a single render pass.
        self._frame_cache: dict[str, object] = {}
        if getattr(self, "mobile_mode", False):
            self.reset_mobile_touch_targets()
        self.screen.fill((10, 10, 14))

        menu_draw = {
            "title": self.draw_title_menu,
            "options": self.draw_options_menu,
            "controls": self.draw_controls_menu,
            "about": self.draw_about_screen,
            "archetype_select": self.draw_archetype_select,
            "confirm_exit": self.draw_exit_confirmation,
        }.get(self.state)
        if menu_draw is not None:
            with self.mobile_safe_render_target():
                menu_draw()
            if getattr(self, "mobile_mode", False):
                self.draw_mobile_touch_navigation()
            pygame.display.flip()
            self.sync_music()
            return

        self._render_world_view()
        self.draw_ui()
        with self.mobile_safe_render_target():
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
        if getattr(self, "mobile_mode", False):
            self.draw_mobile_touch_navigation()
        self.draw_screen_flash()
        pygame.display.flip()
        self.sync_music()

    @contextmanager
    def mobile_safe_render_target(self) -> Iterator[None]:
        """Render menus/overlays inside the Android safe area."""

        if not getattr(self, "mobile_mode", False):
            yield
            return
        root = self.screen
        safe = self.mobile_safe_rect().clip(root.get_rect())
        if safe.width <= 0 or safe.height <= 0:
            yield
            return
        self._mobile_root_screen = root
        self.screen = root.subsurface(safe)
        self._frame_cache.pop("screen_size", None)
        try:
            yield
        finally:
            self.screen = root
            self._frame_cache.pop("screen_size", None)
            del self._mobile_root_screen

    def _render_world_view(self) -> None:
        """Render the dungeon + actors, composite the zoom layer, and shade.

        At zoom 1.0 the world is drawn straight to the display surface (the
        existing hot path, no extra allocation). At any other zoom the world is
        drawn to an offscreen layer sized ``screen_size / zoom`` — so
        ``world_to_screen``/``visible_bounds`` naturally cover more tiles when
        zoomed out — then scaled back to fill the display, giving a uniform
        zoom of tiles and sprites.

        Lighting and the ambient depth vignette are screen-space effects, so
        they are applied to the smaller of the world layer and the display:

        - zoomed OUT (zoom below 1): the world layer is larger than the
          display, so shading runs AFTER the composite on the display. Lighting
          buffers are display-sized, so zooming out no longer pays for a
          layer-res light buffer + multiply. Positions use the zoom-aware
          ``world_to_display`` projection.
        - zoomed IN (zoom above 1): the world layer is smaller than the
          display, so shading runs BEFORE the composite on the layer (the
          original hot path) and is upscaled with it. This keeps lighting cheap
          when zoomed in — it never touches display-resolution buffers.
        - zoom 1.0: no layer; shading runs on the display directly.
        """
        if getattr(self, "mobile_mode", False):
            root = self.screen
            viewport = self.mobile_world_viewport().clip(root.get_rect())
            if viewport.width <= 0 or viewport.height <= 0:
                return
            self._mobile_root_screen = root
            self._mobile_world_rendering = True
            self.screen = root.subsurface(viewport)
            self._frame_cache = {}
            try:
                self._render_world_target()
            finally:
                self.screen = root
                self._mobile_world_rendering = False
                self._frame_cache.pop("screen_size", None)
                del self._mobile_root_screen
            return
        self._render_world_target()

    def _render_world_target(self) -> None:
        """Render and shade the world into the current target surface."""

        zoom = getattr(self, "view_zoom", 1.0)
        use_layer = abs(zoom - 1.0) > 1e-3
        # Shade the display post-composite when zoomed out or at native zoom
        # (display is the smaller buffer); shade the layer pre-composite when
        # zoomed in (layer is the smaller buffer). Read by draw_lighting /
        # _stamp_ambient to pick the correct projection + sprite scale.
        shade_post = zoom <= 1.0
        self._shade_post_composite = shade_post
        real_screen = self.screen
        if use_layer:
            layer = self._world_layer_surface(real_screen, zoom)
            layer.fill((10, 10, 14))
            self.screen = layer
            # ``_screen_size`` caches the surface size; reset so it picks up the
            # layer instead of the display while the world is being drawn.
            self._frame_cache = {}
        try:
            self.draw_dungeon()
            self.draw_world_objects()
            if not shade_post:
                # Zoomed in: shade the (smaller) world layer before it is
                # upscaled to the display.
                self._shade_world()
        finally:
            if use_layer:
                self.screen = real_screen
                self._composite_world_layer(layer, real_screen)
                # Drop only the size cache so HUD/UI lay out against the real
                # display. Preserve the zoom-independent frame caches
                # (camera_iso, visible_bounds, frame_lights) so a post-composite
                # shade pass reuses the layer-derived visible bounds instead of
                # recomputing against the display.
                self._frame_cache.pop("screen_size", None)
        if shade_post:
            # Zoomed out or native: shade the (smaller or only) display after
            # the composite. Buffers are display-sized, so this is independent
            # of viewport zoom and stays cheap when zoomed out.
            self._shade_world()

    def _shade_world(self) -> None:
        # Continuous colored lighting + ambient depth vignette. No-op on the
        # LIGHTING_OFF tier, which keeps the 3.8.0 per-tile alpha look as the
        # fallback/web default.
        self.draw_lighting()
        self.draw_ambient_depth_overlay()
        self.draw_darkness_overlay()

    def _world_layer_surface(
        self, real_screen: pygame.Surface, zoom: float
    ) -> pygame.Surface:
        rw, rh = real_screen.get_size()
        lw = max(320, int(round(rw / zoom)))
        lh = max(240, int(round(rh / zoom)))
        layer = getattr(self, "_world_layer", None)
        if layer is None or layer.get_size() != (lw, lh):
            layer = pygame.Surface((lw, lh))
            self._world_layer = layer
        return layer

    def _composite_world_layer(
        self, layer: pygame.Surface, dest: pygame.Surface
    ) -> None:
        size = dest.get_size()
        try:
            pygame.transform.smoothscale(layer, size, dest)
        except (TypeError, ValueError, pygame.error):
            dest.blit(pygame.transform.smoothscale(layer, size), (0, 0))

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

    def ui_scale_factor(self) -> float:
        """Return the active physical UI scale without changing saved settings."""

        return float(getattr(self, "_ui_scale_override", self.ui_scale))

    def ui(self, value: int) -> int:
        override = getattr(self, "_ui_scale_override", None)
        if override is None:
            return value * self.ui_scale
        return round(value * float(override))

    @contextmanager
    def fitted_ui_layout(
        self, reference_size: tuple[int, int] = (960, 540)
    ) -> Iterator[float]:
        """Fit complex modern UI to the display without mutating ``ui_scale``.

        Authored menus and the HUD need a minimum physical canvas. When a saved
        scale would exceed it, this context temporarily substitutes matching
        fonts and makes :meth:`ui` use the largest scale that fits. Legacy mode
        intentionally bypasses this path so its historical geometry is stable.
        """

        requested = float(self.ui_scale)
        if not self.asset_ui_active() or hasattr(self, "_ui_scale_override"):
            yield self.ui_scale_factor()
            return
        reference_width, reference_height = reference_size
        if reference_width <= 0 or reference_height <= 0:
            yield requested
            return
        width, height = self.screen.get_size()
        effective = max(
            1.0,
            min(requested, width / reference_width, height / reference_height),
        )
        if effective >= requested - 1e-6:
            yield requested
            return

        font_sizes = tuple(
            max(1, round(base_size * effective))
            for base_size in (14, 16, 22, 32, 48, 62)
        )
        cache = getattr(self, "_fitted_ui_font_cache", None)
        if cache is None:
            cache = {}
            self._fitted_ui_font_cache = cache
        fonts = cache.get(font_sizes)
        if fonts is None:
            fonts = tuple(pygame.font.Font(None, size) for size in font_sizes)
            cache[font_sizes] = fonts

        names = (
            "tiny_font",
            "small_font",
            "font",
            "heading_font",
            "big_font",
            "title_font",
        )
        previous = tuple(getattr(self, name) for name in names)
        self._ui_scale_override = effective
        for name, font in zip(names, fonts):
            setattr(self, name, font)
        try:
            yield effective
        finally:
            for name, font in zip(names, previous):
                setattr(self, name, font)
            del self._ui_scale_override

    def hud_panel_height(self) -> int:
        if getattr(self, "mobile_mode", False):
            return 0
        _width, height = self.screen.get_size()
        if self.asset_ui_active():
            desired = (
                self.font.get_height()
                + self.small_font.get_height() * 3
                + self.ui(100)
            )
            minimum = min(self.ui(136), max(128, int(height * 0.25)))
            maximum = max(minimum, int(height * 0.39))
        else:
            desired = (
                self.font.get_height()
                + self.small_font.get_height() * 3
                + self.ui(74)
            )
            minimum = min(self.ui(112), max(132, int(height * 0.30)))
            maximum = max(minimum, int(height * 0.38))
        return min(max(desired, minimum), maximum)

    def _text_size(self, font: pygame.font.Font, text: str) -> tuple[int, int]:
        # font.size() is a hot per-frame call (HUD text wrapping/ellipsizing).
        # Cache by (font, text) so repeated labels (ability names, HP headers,
        # cooldown counts, ...) don't re-measure every frame. Cleared in
        # rebuild_fonts (Font objects are replaced, so id(font) keys would collide).
        cache = getattr(self, "_text_size_cache", None)
        if cache is None:
            cache = {}
            self._text_size_cache = cache
        key = (id(font), text)
        v = cache.get(key)
        if v is None:
            v = font.size(text)
            if len(cache) >= 8192:
                cache.clear()
            cache[key] = v
        return v

    def ellipsize_ui_text(
        self, text: str, font: pygame.font.Font, max_width: int
    ) -> str:
        max_width = max(1, max_width)
        if self._text_size(font, text)[0] <= max_width:
            return text
        suffix = "…"
        # Measure truncated candidates through the shared _text_size cache so
        # repeated labels (e.g. an ability name ellipsized every frame) don't
        # re-run font.size() for every character dropped.
        while text and self._text_size(font, text + suffix)[0] > max_width:
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
        # Cache the rendered+ellipsized surface by (font, text, color, width).
        # Most HUD text is stable frame-to-frame (ability names, hotkeys, section
        # headers), so this skips the ellipsize + font.render cost on every frame
        # after the first; dynamic text (cooldown counts, HP/mana numbers) simply
        # misses and renders as before. Cleared in rebuild_fonts.
        cache = getattr(self, "_ui_text_cache", None)
        if cache is None:
            cache = {}
            self._ui_text_cache = cache
        key = (id(font), text, color, rect.width)
        rendered = cache.get(key)
        if rendered is None:
            rendered = font.render(
                self.ellipsize_ui_text(text, font, rect.width), True, color
            )
            if len(cache) >= 2048:
                cache.clear()
            cache[key] = rendered
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

    def asset_ui_active(self) -> bool:
        library = getattr(self, "ui_assets", None)
        return (
            not getattr(self, "legacy_graphics", False)
            and library is not None
            and bool(getattr(library, "available", False))
        )

    def ui_asset_surface(
        self, key: str, size: tuple[int, int]
    ) -> pygame.Surface | None:
        if not self.asset_ui_active():
            return None
        return self.ui_assets.render(key, size)

    def ui_asset_content_rect(
        self, key: str, rect: pygame.Rect
    ) -> pygame.Rect | None:
        if not self.asset_ui_active():
            return None
        return self.ui_assets.content_rect(key, rect)

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
        # The panel art is a pure function of its inputs, so cache the built
        # surface and just blit on subsequent frames. HUD panels are redrawn
        # every frame with stable geometry/colors, so this removes the per-call
        # SRCALPHA allocation + two draw.rects. convert_alpha() also makes the
        # cached blit faster than the previous unconverted surface.
        cache = getattr(self, "_hud_panel_cache", None)
        if cache is None:
            cache = {}
            self._hud_panel_cache = cache
        key = ("plain", rect.size, fill, border, radius, width, self.ui_scale)
        panel = cache.get(key)
        if panel is None:
            panel = pygame.Surface(rect.size, pygame.SRCALPHA)
            panel_rect = panel.get_rect()
            pygame.draw.rect(panel, fill, panel_rect, border_radius=radius)
            pygame.draw.rect(panel, border, panel_rect, width, border_radius=radius)
            try:
                panel = panel.convert_alpha()
            except pygame.error:
                pass
            if len(cache) >= 512:
                cache.clear()
            cache[key] = panel
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
                if self._text_size(font, candidate)[0] <= max_width:
                    current = candidate
                else:
                    lines.append(current)
                    current = self.ellipsize_ui_text(word, font, max_width)
            lines.append(current)
        return lines

    # --- Gothic HUD helpers -------------------------------------------------
    # Shared palette tokens for the in-world HUD. Kept here so the HUD and the
    # menu renderer speak the same visual language without import cycles.
    HUD_INK = (12, 11, 16)
    HUD_PANEL = (18, 17, 24)
    HUD_STONE_LIGHT = (54, 49, 58)
    HUD_STONE_SHADOW = (8, 7, 11)
    HUD_IRON = (74, 70, 82)
    HUD_IRON_LIGHT = (118, 110, 128)
    HUD_IRON_DARK = (32, 30, 38)
    HUD_GOLD = (214, 168, 92)
    HUD_GOLD_BRIGHT = (236, 214, 168)
    HUD_PARCHMENT = (224, 214, 196)
    HUD_BONE = (210, 204, 190)
    HUD_MUTED = (148, 138, 124)

    def draw_ornate_hud_panel(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        fill: tuple[int, int, int, int],
        border: tuple[int, int, int, int],
        radius: int | None = None,
        width: int | None = None,
        studs: bool = False,
    ) -> None:
        """A translucent stone panel with a chiseled bevel and optional iron studs."""
        radius = self.ui(9) if radius is None else radius
        width = self.ui(1) if width is None else width
        asset = self.ui_asset_surface("hud.panel", rect.size)
        if asset is not None:
            surface.blit(asset, rect)
            return
        # The bevel/studs/trim are a pure function of (size, colors, radii,
        # ui_scale), so cache the built panel and blit on subsequent frames.
        # This removes the per-call SRCALPHA allocation + ~5 draw.rects + up to
        # 12 stud circles for the HUD's stable panels, and convert_alpha()
        # makes the cached blit faster than the previous unconverted surface.
        cache = getattr(self, "_hud_panel_cache", None)
        if cache is None:
            cache = {}
            self._hud_panel_cache = cache
        key = ("ornate", rect.size, fill, border, radius, width, studs, self.ui_scale)
        panel = cache.get(key)
        if panel is None:
            panel = self._build_ornate_hud_panel(rect.size, fill, border, radius, width, studs)
            if len(cache) >= 512:
                cache.clear()
            cache[key] = panel
        surface.blit(panel, rect)

    def _build_ornate_hud_panel(
        self,
        size: tuple[int, int],
        fill: tuple[int, int, int, int],
        border: tuple[int, int, int, int],
        radius: int,
        width: int,
        studs: bool,
    ) -> pygame.Surface:
        panel = pygame.Surface(size, pygame.SRCALPHA)
        panel_rect = panel.get_rect()
        pygame.draw.rect(panel, fill, panel_rect, border_radius=radius)
        # Inner bevel — dark rim then a faint light rim.
        pygame.draw.rect(
            panel,
            (*self.HUD_STONE_SHADOW, fill[3] // 2 + 40),
            panel_rect,
            max(1, self.ui(2)),
            border_radius=radius,
        )
        inner = panel_rect.inflate(-self.ui(2), -self.ui(2))
        pygame.draw.rect(
            panel,
            (*self.HUD_STONE_LIGHT, fill[3] // 2 + 30),
            inner,
            max(1, self.ui(1)),
            border_radius=max(1, radius - self.ui(1)),
        )
        # Gold inner trim.
        trim = inner.inflate(-self.ui(4), -self.ui(4))
        pygame.draw.rect(
            panel,
            (*self.shade(self.HUD_GOLD, -40), fill[3] // 2 + 20),
            trim,
            max(1, self.ui(1)),
            border_radius=max(1, radius - self.ui(2)),
        )
        # Outer accent border (caller-supplied color).
        pygame.draw.rect(panel, border, panel_rect, width, border_radius=radius)
        if studs:
            stud_r = max(2, self.ui(3))
            inset = self.ui(7)
            for corner in (
                (inset, inset),
                (panel_rect.width - inset, inset),
                (inset, panel_rect.height - inset),
                (panel_rect.width - inset, panel_rect.height - inset),
            ):
                pygame.draw.circle(panel, self.HUD_IRON_DARK, corner, stud_r + 1)
                pygame.draw.circle(panel, self.HUD_IRON, corner, stud_r)
                pygame.draw.circle(
                    panel,
                    self.HUD_IRON_LIGHT,
                    (corner[0] - 1, corner[1] - 1),
                    max(1, stud_r - 1),
                )
        try:
            panel = panel.convert_alpha()
        except pygame.error:
            pass
        return panel

    def draw_hud_divider(
        self, surface: pygame.Surface, x1: int, y: int, x2: int, color: Color
    ) -> None:
        """An ornamental gold rule with a center diamond."""
        pygame.draw.line(
            surface, self.shade(color, -40), (x1, y), (x2, y), max(1, self.ui(1))
        )
        cx = (x1 + x2) // 2
        dr = self.ui(2)
        pygame.draw.polygon(
            surface,
            color,
            [(cx, y - dr), (cx + dr, y), (cx, y + dr), (cx - dr, y)],
        )
