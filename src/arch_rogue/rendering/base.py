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
import time
from collections import OrderedDict, deque
from contextlib import contextmanager
from typing import Iterator, cast

import pygame

from ..constants import DUNGEON_DEPTH, TILE_H, TILE_W, WORLD_SCALE, SlashEffect
from ..content import HUMANOID_ENEMY_NAMES
from ..input import Command
from ..mobile import optimize_immutable_alpha_surface
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
from ..story import (
    CutsceneActorAsset,
    SpriteAnimationFrameAsset,
    format_asset_text,
)


class RenderingBaseMixin:
    _mobile_back_button_rect: pygame.Rect | None = None
    _mobile_back_panel_cache: dict[int, pygame.Surface] = {}

    def _clear_frame_surface(self) -> bool:
        """Clear the CPU framebuffer unless an opaque floor replaces every pixel."""

        skip_clear = bool(
            getattr(self, "mobile_mode", False)
            and self.mobile_gpu_frame_active()
            and getattr(self, "active_cutscene", None) is None
            and getattr(self, "state", "") in ("playing", "dead", "victory")
            and self.mobile_opaque_floor_layer_active()
        )
        if skip_clear:
            return False
        self.screen.fill((10, 10, 14))
        return True

    def _mobile_static_menu_signature(self) -> object | None:
        if not getattr(self, "mobile_mode", False):
            return None
        state = getattr(self, "state", "")
        if state not in {"title", "options", "controls", "about", "confirm_exit"}:
            return None
        monitor = getattr(self, "_mobile_performance_monitor", None)
        safe = self.mobile_safe_rect()
        ui_assets = getattr(self, "ui_assets", None)
        common = (
            state,
            id(self.screen),
            self.screen.get_size(),
            (safe.x, safe.y, safe.width, safe.height),
            int(getattr(self, "ui_scale", 1)),
            bool(getattr(self, "ui_scale_auto", True)),
            id(getattr(self, "tiny_font", None)),
            id(getattr(self, "small_font", None)),
            id(getattr(self, "font", None)),
            id(getattr(self, "heading_font", None)),
            bool(getattr(self, "legacy_graphics", False)),
            bool(getattr(ui_assets, "available", False)),
            tuple(getattr(getattr(self, "theme", None), "accent", ())),
            int(getattr(self, "_mobile_render_generation", 0)),
            getattr(monitor, "overlay_text", ""),
            getattr(monitor, "overlay_detail_text", ""),
        )
        input_manager = getattr(self, "input", None)
        has_controller = bool(
            input_manager is not None and input_manager.has_controller()
        )
        controller_name = (
            input_manager.active_name() if has_controller and input_manager is not None else ""
        )
        if state == "title":
            return common + (
                int(getattr(self, "title_selection", 0)),
                bool(self.save_exists()),
            )
        if state == "options":
            return common + (
                int(getattr(self, "options_cursor", 0)),
                int(getattr(self, "options_scroll", 0)),
                getattr(self, "mobile_render_quality", ""),
                getattr(self, "difficulty_name", ""),
                bool(getattr(self, "hell_unlocked", False)),
                bool(getattr(self, "controller_enabled", True)),
                has_controller,
                controller_name,
                bool(getattr(self, "audio_enabled", True)),
                bool(getattr(self, "music_enabled", True)),
                bool(getattr(self, "_lighting_enabled", True)),
                bool(getattr(self, "_lighting_normal_maps", False)),
            )
        if state == "controls":
            return common + (
                int(getattr(self, "controls_cursor", 0)),
                getattr(self, "controls_capture_command", None),
                bool(getattr(self, "controller_enabled", True)),
                has_controller,
                controller_name,
                repr(getattr(self, "gamepad_mapping", {})),
            )
        if state == "confirm_exit":
            return common + (
                getattr(self, "exit_previous_state", ""),
                int(getattr(self, "exit_confirmation_cursor", 0)),
                getattr(self, "last_save_error", ""),
            )
        return common

    def _draw_mobile_back_button(self) -> None:
        """Draw one safe-area-aware Back control for reversible mobile screens."""

        if not getattr(self, "mobile_mode", False):
            self._mobile_back_button_rect = None
            return
        context = self.mobile_input_context()
        reversible_contexts = {
            "options",
            "controls",
            "about",
            "archetype_select",
            "confirm_exit",
            "mobile_hub",
            "quest",
            "inventory",
            "shop",
            "character",
            "help",
            "state_overlay",
        }
        if context == "cutscene" and not getattr(self, "story_intro_pending", False):
            reversible_contexts.add("cutscene")
        if context not in reversible_contexts:
            self._mobile_back_button_rect = None
            return

        safe = self.mobile_safe_rect()
        size = max(52, min(68, safe.height // 8))
        margin = max(8, size // 7)
        rect = pygame.Rect(safe.x + margin, safe.y + margin, size, size)
        panel = self._mobile_back_panel_cache.get(size)
        if panel is None:
            panel = pygame.Surface((size, size), pygame.SRCALPHA)
            radius = max(9, size // 5)
            pygame.draw.rect(
                panel,
                (11, 10, 15, 208),
                panel.get_rect(),
                border_radius=radius,
            )
            pygame.draw.rect(
                panel,
                (126, 104, 68, 150),
                panel.get_rect(),
                max(1, size // 30),
                border_radius=radius,
            )
            inner = panel.get_rect().inflate(-max(6, size // 9), -max(6, size // 9))
            pygame.draw.rect(
                panel,
                (48, 42, 52, 92),
                inner,
                max(1, size // 36),
                border_radius=max(5, radius // 2),
            )
            self._mobile_back_panel_cache[size] = panel
        self.screen.blit(panel, rect)

        glyph_inset = max(3, size // 14)
        glyph_rect = rect.inflate(-glyph_inset * 2, -glyph_inset * 2)
        glyph = self.ui_asset_surface("hud.mobile.back", glyph_rect.size)
        if glyph is not None:
            self.screen.blit(glyph, glyph_rect)
        else:
            color = (210, 185, 126)
            line_width = max(2, size // 12)
            left = rect.x + size // 4
            right = rect.x + size * 3 // 4
            center_y = rect.centery
            pygame.draw.lines(
                self.screen,
                color,
                False,
                (
                    (right, rect.y + size // 4),
                    (left, center_y),
                    (right, rect.bottom - size // 4),
                ),
                line_width,
            )
        self._mobile_back_button_rect = rect.copy()
        self.register_mobile_touch_target(
            rect,
            Command.BACK,
            "Back",
            context=context,
        )

    def draw(self) -> None:
        # Per-frame caches for hot-path lookups. These are invalidated every
        # frame so they never go stale within a single render pass.
        self._frame_cache: dict[str, object] = {}
        performance = getattr(self, "_mobile_performance_monitor", None)
        menu_draw = {
            "title": self.draw_title_menu,
            "options": self.draw_options_menu,
            "controls": self.draw_controls_menu,
            "about": self.draw_about_screen,
            "archetype_select": self.draw_archetype_select,
            "confirm_exit": self.draw_exit_confirmation,
        }.get(self.state)
        mobile = bool(getattr(self, "mobile_mode", False))
        menu_signature = self._mobile_static_menu_signature() if menu_draw else None
        if (
            menu_signature is not None
            and getattr(self, "_mobile_static_menu_last_signature", None)
            == menu_signature
        ):
            started = time.perf_counter()
            self.sync_music()
            if performance is not None:
                performance.record_phase("audio", time.perf_counter() - started)
            return
        if menu_signature is None:
            self._mobile_static_menu_last_signature = None
        if mobile:
            self.reset_mobile_touch_targets()
            self.begin_mobile_gpu_frame()

        started = time.perf_counter()
        self._clear_frame_surface()
        if performance is not None:
            performance.record_phase("clear", time.perf_counter() - started)
        if menu_draw is not None:
            started = time.perf_counter()
            with self.mobile_full_render_target():
                menu_draw()
            if performance is not None:
                performance.record_phase("menu", time.perf_counter() - started)
            self._draw_mobile_back_button()

            started = time.perf_counter()
            if performance is not None:
                self.draw_mobile_performance_overlay()
                performance.record_phase("overlays", time.perf_counter() - started)

            started = time.perf_counter()
            self._present_frame()
            if performance is not None:
                performance.record_phase("flip", time.perf_counter() - started)

            started = time.perf_counter()
            self.sync_music()
            if performance is not None:
                performance.record_phase("audio", time.perf_counter() - started)
            if menu_signature is not None:
                self._mobile_static_menu_last_signature = (
                    self._mobile_static_menu_signature()
                )
            return

        # A cutscene is a full-screen cinematic: it owns the display with an
        # opaque background, so rendering the dungeon world + HUD underneath is
        # wasted work (and on Android it drives the biggest frame cost). Skip
        # both while a cutscene is active; the story intro and other overlays
        # still composite over the live world.
        cutscene_active = self.active_cutscene is not None
        if not cutscene_active:
            started = time.perf_counter()
            self._render_world_view()
            if performance is not None:
                performance.record_phase("world", time.perf_counter() - started)

            started = time.perf_counter()
            self.draw_ui()
            if performance is not None:
                performance.record_phase("hud", time.perf_counter() - started)

        started = time.perf_counter()
        cutscene_active = self.active_cutscene is not None
        if cutscene_active:
            # A quest cutscene owns the full display (opaque backdrop +
            # letterboxed stage), so render it full-bleed without the
            # safe-area subsurface that clips other overlays.
            with self.mobile_full_render_target():
                self.draw_quest_cutscene_overlay()
        else:
            # The death/victory red tint must cover the full display (including
            # cutout/notch areas), not just the safe area. Draw the background
            # to the root screen before the safe-area render target clips the
            # overlay content, so the tint stretches edge-to-edge like the world
            # viewport. The stat panels are then drawn inside the safe area on
            # top of the tint, without red bleeding through them.
            state_overlay_active = self.state != "playing"
            if state_overlay_active:
                self.draw_state_overlay_background()

            with self.mobile_safe_render_target():
                if self.story_intro_pending:
                    self.draw_story_intro_overlay()
                if self.inventory_open:
                    self.draw_inventory()
                if self.shop_open:
                    self.draw_shop_overlay()
                if self.character_menu_open:
                    self.draw_character_menu()
                if self.show_help:
                    self.draw_help_overlay()
                if state_overlay_active:
                    self.draw_state_overlay_content()
        self._draw_mobile_back_button()
        self.draw_screen_flash()
        if performance is not None:
            self.draw_mobile_performance_overlay()
            performance.record_phase("overlays", time.perf_counter() - started)

        started = time.perf_counter()
        self._present_frame()
        if performance is not None:
            performance.record_phase("flip", time.perf_counter() - started)

        started = time.perf_counter()
        self.sync_music()
        if performance is not None:
            performance.record_phase("audio", time.perf_counter() - started)

    def _present_frame(self) -> None:
        if getattr(self, "mobile_mode", False) and self.present_mobile_gpu_frame():
            return
        pygame.display.flip()

    @contextmanager
    def mobile_safe_render_target(self) -> Iterator[None]:
        """Render menus/overlays inside the Android safe area."""

        yield from self._mobile_render_target(safe_area=True)

    @contextmanager
    def mobile_full_render_target(self) -> Iterator[None]:
        """Render a screen across the whole Android display.

        Menu screens (title, options, about, archetype select, exit confirm)
        own the whole screen while open; there is no HUD rail to avoid, so
        they paint edge-to-edge like their desktop counterparts.
        """

        yield from self._mobile_render_target(safe_area=False)

    def _mobile_render_target(self, *, safe_area: bool) -> Iterator[None]:
        if not getattr(self, "mobile_mode", False):
            yield
            return
        root = self.screen
        if not safe_area:
            # Full-bleed menus still draw on the root surface; nothing to
            # re-target. Keep the frame-size cache consistent for fitted
            # layouts that query the display size.
            yield
            return
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
        layer: pygame.Surface | None = None
        if use_layer:
            layer = self._world_layer_surface(real_screen, zoom)
            layer.fill((10, 10, 14))
            self.screen = layer
            # ``_screen_size`` caches the surface size; reset so it picks up the
            # layer instead of the display while the world is being drawn.
            self._frame_cache = {}
        performance = getattr(self, "_mobile_performance_monitor", None)
        try:
            started = time.perf_counter()
            self.draw_dungeon()
            if performance is not None:
                performance.record_detail_phase(
                    "floor", time.perf_counter() - started
                )
            started = time.perf_counter()
            self.draw_world_objects()
            if performance is not None:
                performance.record_detail_phase(
                    "objects", time.perf_counter() - started
                )
            if not shade_post:
                # Zoomed in: shade the (smaller) world layer before it is
                # upscaled to the display.
                self._shade_world()
        finally:
            if use_layer:
                self.screen = real_screen
                assert layer is not None
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
        performance = getattr(self, "_mobile_performance_monitor", None)
        started = time.perf_counter()
        self.draw_lighting()
        if performance is not None:
            performance.record_detail_phase(
                "light_build", time.perf_counter() - started
            )
        started = time.perf_counter()
        self.draw_ambient_depth_overlay()
        self.draw_darkness_overlay()
        if performance is not None:
            performance.record_detail_phase("ambient", time.perf_counter() - started)

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
        scaler = (
            pygame.transform.scale
            if getattr(self, "mobile_mode", False)
            else pygame.transform.smoothscale
        )
        try:
            scaler(layer, size, dest)
        except (TypeError, ValueError, pygame.error):
            dest.blit(scaler(layer, size), (0, 0))

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

    def _cached_text_surface(
        self,
        font: pygame.font.Font,
        text: str,
        color: Color,
    ) -> pygame.Surface:
        """Return a cached immutable text surface for world-space labels."""

        cache = getattr(self, "_world_text_cache", None)
        if not isinstance(cache, OrderedDict):
            cache = OrderedDict()
            self._world_text_cache = cache
        key = (id(font), text, color)
        cached = cache.get(key)
        if cached is not None:
            cache.move_to_end(key)
            return cached
        rendered = optimize_immutable_alpha_surface(font.render(text, True, color))
        cache[key] = rendered
        cache.move_to_end(key)
        while len(cache) > 1024:
            cache.popitem(last=False)
        return rendered

    def _cached_alpha_surface(
        self,
        source: pygame.Surface,
        alpha: int,
    ) -> pygame.Surface:
        """Return a 16-step global-alpha variant without per-frame copies."""

        bucket_alpha = max(0, min(255, ((int(alpha) + 8) // 16) * 16))
        cache = getattr(self, "_world_alpha_surface_cache", None)
        if not isinstance(cache, OrderedDict):
            cache = OrderedDict()
            self._world_alpha_surface_cache = cache
        key = (id(source), bucket_alpha)
        cached = cache.get(key)
        if cached is not None and cached[0] is source:
            cache.move_to_end(key)
            return cached[1]
        variant = source.copy()
        variant.set_alpha(bucket_alpha, pygame.RLEACCEL)
        variant = optimize_immutable_alpha_surface(variant, alpha=bucket_alpha)
        cache[key] = (source, variant)
        cache.move_to_end(key)
        while len(cache) > 2048:
            cache.popitem(last=False)
        return variant

    def _cached_rotated_surface(
        self,
        source: pygame.Surface,
        angle: float,
        *,
        step_degrees: int = 1,
    ) -> pygame.Surface:
        """Return a bounded, quantized rotation of an immutable sprite.

        Decorative props retain degree-level motion by default. Fast-moving combat
        sprites can request a coarser direction step, avoiding a fresh software
        rotation for every projectile on every frame while staying visually smooth.
        """

        step_degrees = max(1, int(step_degrees))
        angle_bucket = int(round(angle / step_degrees)) * step_degrees
        cache = getattr(self, "_rotated_surface_cache", None)
        if not isinstance(cache, OrderedDict):
            cache = OrderedDict()
            self._rotated_surface_cache = cache
        key = (id(source), angle_bucket, step_degrees)
        cached = cache.get(key)
        if cached is not None and cached[0] is source:
            cache.move_to_end(key)
            return cached[1]
        rotated = optimize_immutable_alpha_surface(
            pygame.transform.rotate(source, angle_bucket)
        )
        cache[key] = (source, rotated)
        cache.move_to_end(key)
        while len(cache) > 256:
            cache.popitem(last=False)
        return rotated

    def _cached_circle_overlay(
        self,
        namespace: str,
        size: tuple[int, int],
        color: Color,
        alpha: int,
        radius: int,
        width: int,
    ) -> pygame.Surface:
        """Cache a small outlined circle used by attack telegraphs."""

        cache = getattr(self, "_circle_overlay_cache", None)
        if not isinstance(cache, OrderedDict):
            cache = OrderedDict()
            self._circle_overlay_cache = cache
        key = (namespace, size, color, int(alpha), int(radius), int(width))
        cached = cache.get(key)
        if cached is not None:
            cache.move_to_end(key)
            return cached
        overlay = pygame.Surface(size, pygame.SRCALPHA)
        pygame.draw.circle(
            overlay,
            (*color, int(alpha)),
            overlay.get_rect().center,
            int(radius),
            int(width),
        )
        overlay = optimize_immutable_alpha_surface(overlay)
        cache[key] = overlay
        cache.move_to_end(key)
        while len(cache) > 128:
            cache.popitem(last=False)
        return overlay

    def _cached_ellipse_overlay(
        self,
        namespace: str,
        size: tuple[int, int],
        outer_color: Color,
        outer_alpha: int,
        *,
        outer_width: int = 0,
        inner_color: Color | None = None,
        inner_alpha: int = 0,
        inner_inflate: tuple[int, int] = (0, 0),
        inner_width: int = 0,
    ) -> pygame.Surface:
        """Cache small pulsing ellipse overlays by their quantized appearance."""

        cache = getattr(self, "_ellipse_overlay_cache", None)
        if not isinstance(cache, OrderedDict):
            cache = OrderedDict()
            self._ellipse_overlay_cache = cache
        key = (
            namespace,
            size,
            outer_color,
            int(outer_alpha),
            int(outer_width),
            inner_color,
            int(inner_alpha),
            inner_inflate,
            int(inner_width),
        )
        cached = cache.get(key)
        if cached is not None:
            cache.move_to_end(key)
            return cached
        overlay = pygame.Surface(size, pygame.SRCALPHA)
        pygame.draw.ellipse(
            overlay,
            (*outer_color, int(outer_alpha)),
            overlay.get_rect(),
            int(outer_width),
        )
        if inner_color is not None and inner_alpha > 0:
            pygame.draw.ellipse(
                overlay,
                (*inner_color, int(inner_alpha)),
                overlay.get_rect().inflate(*inner_inflate),
                int(inner_width),
            )
        overlay = optimize_immutable_alpha_surface(overlay)
        cache[key] = overlay
        cache.move_to_end(key)
        while len(cache) > 256:
            cache.popitem(last=False)
        return overlay

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
            rendered = optimize_immutable_alpha_surface(rendered)
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
            panel = optimize_immutable_alpha_surface(panel)
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
        return optimize_immutable_alpha_surface(panel)

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
