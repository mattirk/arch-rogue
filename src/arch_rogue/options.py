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

import json
import math
import os
import sys
import warnings
from pathlib import Path
from typing import Any

import pygame

from .audio import MusicProfile
from .constants import (
    FRAME_RATE_CAP_DEFAULT,
    FRAME_RATE_CAP_VALUES,
    GRAPHICS_TIER_DEFAULT,
    GRAPHICS_TIER_LABELS,
    GRAPHICS_TIER_LEGACY,
    GRAPHICS_TIER_MODERN,
    GRAPHICS_TIER_VALUES,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    UI_SCALE,
    normalize_frame_rate_cap,
    normalize_graphics_tier,
)
from .content import (
    DEFAULT_DIFFICULTY_NAME,
    DIFFICULTY_PROFILES,
    HELL_DIFFICULTY_NAME,
    DifficultyProfile,
    canonical_boss_name,
)
from .input import (
    DECK_GAMEPAD_PROFILE_VERSION,
    add_missing_deck_gameplay_aliases,
    normalize_gamepad_mapping,
    serialize_gamepad_mapping,
)
from .mobile import android_runtime_active
from .steam_deck import is_steam_deck
from arch_rogue_protocol import sanitize_player_name


DEFAULT_MP_SERVER_HOST = "ar.rita-kasari.fi"
DEFAULT_MP_SERVER_PORT = 43666


def normalize_mp_server_host(value: object) -> str:
    """Sanitize a persisted multiplayer server host/address string."""

    if not isinstance(value, str):
        return ""
    host = "".join(char for char in value if char.isprintable())
    return host.strip()[:128]


def normalize_mp_server_port(value: object) -> int:
    """Coerce a persisted port to an int in 1..65535, or 0 (unset)."""

    try:
        port = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    return port if 1 <= port <= 65535 else 0


def normalize_mp_server_tls(value: object) -> bool:
    """Coerce the persisted TLS flag; anything malformed stays secure (on)."""

    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return True


MOBILE_RENDER_QUALITY_PERFORMANCE = "performance"
MOBILE_RENDER_QUALITY_BALANCED = "balanced"
MOBILE_RENDER_QUALITY_NATIVE = "native"
MOBILE_RENDER_QUALITY_MODES: tuple[str, ...] = (
    MOBILE_RENDER_QUALITY_PERFORMANCE,
    MOBILE_RENDER_QUALITY_BALANCED,
    MOBILE_RENDER_QUALITY_NATIVE,
)
MOBILE_RENDER_QUALITY_HEIGHT_CAPS: dict[str, int | None] = {
    MOBILE_RENDER_QUALITY_PERFORMANCE: 540,
    MOBILE_RENDER_QUALITY_BALANCED: 720,
    MOBILE_RENDER_QUALITY_NATIVE: None,
}
MOBILE_RENDER_QUALITY_LABELS: dict[str, str] = {
    MOBILE_RENDER_QUALITY_PERFORMANCE: "Performance · 540p cap",
    MOBILE_RENDER_QUALITY_BALANCED: "Balanced · 720p cap",
    MOBILE_RENDER_QUALITY_NATIVE: "Native · full resolution",
}
# Desktop reuses the same three-tier vocabulary against the fixed 16:9 canvas,
# where the height caps resolve to exact resolutions: 960×540, 1280×720, and
# the unchanged 2560×1440 canvas.
DESKTOP_RENDER_RESOLUTION_LABELS: dict[str, str] = {
    MOBILE_RENDER_QUALITY_PERFORMANCE: "Performance · 540p",
    MOBILE_RENDER_QUALITY_BALANCED: "Balanced · 720p",
    MOBILE_RENDER_QUALITY_NATIVE: "Native · 1440p",
}
ANDROID_RENDER_DRIVER_CANDIDATES: tuple[str, ...] = ("opengles2", "opengles")


def default_mobile_render_quality(_mobile: bool) -> str:
    """Return the fresh-install quality default for the active platform."""

    return MOBILE_RENDER_QUALITY_NATIVE


def normalize_mobile_render_quality(
    value: object,
    *,
    default: str = MOBILE_RENDER_QUALITY_NATIVE,
) -> str:
    """Normalize a persisted quality name without depending on runtime state."""

    fallback = str(default).strip().lower()
    if fallback not in MOBILE_RENDER_QUALITY_MODES:
        fallback = MOBILE_RENDER_QUALITY_NATIVE
    quality = str(value).strip().lower() if value is not None else ""
    return quality if quality in MOBILE_RENDER_QUALITY_MODES else fallback


def mobile_logical_resolution(
    physical_size: tuple[int, int], quality: object
) -> tuple[int, int]:
    """Cap render height while retaining aspect ratio and never upscaling."""

    try:
        width = int(physical_size[0])
        height = int(physical_size[1])
    except (IndexError, TypeError, ValueError) as exc:
        raise ValueError("physical_size must contain two positive integers") from exc
    if width <= 0 or height <= 0:
        raise ValueError("physical_size must contain two positive integers")

    mode = normalize_mobile_render_quality(quality)
    height_cap = MOBILE_RENDER_QUALITY_HEIGHT_CAPS[mode]
    if height_cap is None or height <= height_cap:
        return width, height

    logical_height = height_cap
    logical_width = max(
        1,
        min(width, (width * logical_height + height // 2) // height),
    )
    return logical_width, logical_height


def mobile_render_quality_label(value: object) -> str:
    """Return the concise options-menu label for a quality mode."""

    return MOBILE_RENDER_QUALITY_LABELS[normalize_mobile_render_quality(value)]


def next_mobile_render_quality(value: object, forward: bool = True) -> str:
    """Cycle through performance, balanced, and native quality modes."""

    quality = normalize_mobile_render_quality(value)
    index = MOBILE_RENDER_QUALITY_MODES.index(quality)
    delta = 1 if forward else -1
    return MOBILE_RENDER_QUALITY_MODES[(index + delta) % len(MOBILE_RENDER_QUALITY_MODES)]


def _valid_display_scale(value: Any) -> float | None:
    try:
        scale = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(scale) or not 0.5 <= scale <= 8.0:
        return None
    return scale


def ui_scale_from_display_scale(display_scale: float | None) -> int:
    """Quantize a display scale factor to the integer UI scale range."""

    scale = _valid_display_scale(display_scale)
    if scale is None:
        return UI_SCALE
    return max(1, min(4, math.floor(scale + 0.5)))


class OptionsMixin:
    def prepare_display_scaling(self) -> None:
        # SDL must declare DPI awareness and scaling hints before its video
        # subsystem starts. Nearest-neighbor output keeps logical pixels crisp.
        if sys.platform == "win32":
            os.environ.setdefault("SDL_WINDOWS_DPI_AWARENESS", "permonitorv2")
        if getattr(self, "mobile_mode", False):
            os.environ["SDL_RENDER_SCALE_QUALITY"] = "0"
            if android_runtime_active():
                # SDL_CreateRenderer otherwise accepts a software renderer. On
                # Android that makes every fullscreen scale/present CPU-bound.
                os.environ.setdefault("SDL_RENDER_DRIVER", "opengles2")

    def _set_ui_scale(
        self,
        scale: int,
        *,
        automatic: bool,
        persist: bool,
    ) -> bool:
        scale = max(1, min(4, int(scale)))
        scale_changed = scale != self.ui_scale
        mode_changed = automatic != getattr(self, "ui_scale_auto", True)
        self.ui_scale = scale
        self.ui_scale_auto = automatic
        if not automatic:
            self._legacy_ui_scale_migration = False
        if scale_changed and hasattr(self, "tiny_font"):
            self.rebuild_fonts()
            if hasattr(self, "clear_stage_render_cache"):
                self.clear_stage_render_cache()
        if persist:
            self.save_options()
        return scale_changed or mode_changed

    def refresh_automatic_ui_scale(self) -> bool:
        legacy_migration = bool(
            getattr(self, "_legacy_ui_scale_migration", False)
        )
        if not getattr(self, "ui_scale_auto", True) and not legacy_migration:
            return False
        # Every visible surface is a fixed logical canvas (desktop windowed and
        # fullscreen render the 2560×1440 canvas, the Deck its 1280×800 panel,
        # Android its capped logical surface) and SDL's SCALED renderer maps it
        # to the physical window, so the automatic scale derives from that
        # canvas alone: same canvas, same layout, on every machine. The old
        # host-DPI probing (Xft.dpi / GetDpiForWindow / CoreGraphics) made the
        # auto scale differ between hosts showing the very same canvas.
        # ARCH_ROGUE_DISPLAY_SCALE stays as an explicit override for users who
        # want denser or larger UI than the canvas heuristic picks.
        display_scale = _valid_display_scale(
            os.environ.get("ARCH_ROGUE_DISPLAY_SCALE")
        )
        if display_scale is None:
            screen = getattr(self, "screen", None)
            if screen is None:
                self.detected_display_scale = None
                return False
            width, height = screen.get_size()
            display_scale = max(1.0, min(width / 1280.0, height / 720.0))
        target = ui_scale_from_display_scale(display_scale)
        self.detected_display_scale = display_scale
        if legacy_migration:
            self._legacy_ui_scale_migration = False
            # Schema 4 always serialized a scale, so it could not distinguish
            # the untouched 1x default from a manual preference. Migrate the
            # default and values already matching the host; retain conflicting
            # custom values as manual overrides.
            if self.ui_scale == UI_SCALE or self.ui_scale == target:
                self.ui_scale_auto = True
        if not getattr(self, "ui_scale_auto", True):
            return False
        return self._set_ui_scale(target, automatic=True, persist=False)

    def enable_automatic_ui_scale(self) -> bool:
        mode_changed = not getattr(self, "ui_scale_auto", True)
        self.ui_scale_auto = True
        self._legacy_ui_scale_migration = False
        scale_changed = self.refresh_automatic_ui_scale()
        self.save_options()
        return mode_changed or scale_changed

    def cycle_ui_scale(self, forward: bool = True) -> bool:
        delta = 1 if forward else -1
        if getattr(self, "ui_scale_auto", True):
            target = max(1, min(4, self.ui_scale + delta))
            return self._set_ui_scale(target, automatic=False, persist=True)
        target = self.ui_scale + delta
        if not 1 <= target <= 4:
            return self.enable_automatic_ui_scale()
        return self._set_ui_scale(target, automatic=False, persist=True)

    def ui_scale_label(self) -> str:
        if getattr(self, "ui_scale_auto", True):
            return f"Auto · {self.ui_scale}x"
        return f"{self.ui_scale}x"

    def render_quality_label(self) -> str:
        return mobile_render_quality_label(
            getattr(
                self,
                "mobile_render_quality",
                default_mobile_render_quality(
                    bool(getattr(self, "mobile_mode", False))
                ),
            )
        )

    def desktop_render_resolution_label(self) -> str:
        return DESKTOP_RENDER_RESOLUTION_LABELS[
            normalize_mobile_render_quality(
                getattr(
                    self, "desktop_render_quality", MOBILE_RENDER_QUALITY_NATIVE
                )
            )
        ]

    def mp_endpoint_configured(self) -> bool:
        """Whether a usable multiplayer server endpoint is persisted."""

        host = normalize_mp_server_host(getattr(self, "mp_server_host", ""))
        port = normalize_mp_server_port(getattr(self, "mp_server_port", 0))
        return bool(host) and 1 <= port <= 65535

    def mp_server_host_label(self) -> str:
        host = normalize_mp_server_host(getattr(self, "mp_server_host", ""))
        return host or "Not set"

    def mp_server_port_label(self) -> str:
        port = normalize_mp_server_port(getattr(self, "mp_server_port", 0))
        return str(port) if port else "Not set"

    def mp_server_tls_label(self) -> str:
        tls = normalize_mp_server_tls(getattr(self, "mp_server_tls", True))
        return "On (certificate verified)" if tls else "Off (plaintext)"

    def frame_rate_cap_label(self) -> str:
        cap = normalize_frame_rate_cap(
            getattr(self, "frame_rate_cap", FRAME_RATE_CAP_DEFAULT)
        )
        return "Unlimited" if cap == "Unlimited" else f"{int(cap)} FPS"

    def cycle_frame_rate_cap(self, forward: bool = True) -> bool:
        current = normalize_frame_rate_cap(
            getattr(self, "frame_rate_cap", FRAME_RATE_CAP_DEFAULT)
        )
        try:
            index = FRAME_RATE_CAP_VALUES.index(current)
        except ValueError:
            index = FRAME_RATE_CAP_VALUES.index(FRAME_RATE_CAP_DEFAULT)
        delta = 1 if forward else -1
        new_cap = FRAME_RATE_CAP_VALUES[
            (index + delta) % len(FRAME_RATE_CAP_VALUES)
        ]
        if new_cap == current:
            return False
        self.frame_rate_cap = new_cap
        frame_pacing = getattr(self, "frame_pacing", None)
        if frame_pacing is not None:
            frame_pacing.set_frame_rate_cap(new_cap)
        self.save_options()
        return True

    def toggle_perf_overlay(self) -> bool:
        self.show_perf_overlay = not bool(
            getattr(self, "show_perf_overlay", False)
        )
        self.save_options()
        # Apply immediately so the overlay appears/disappears without a restart.
        if hasattr(self, "_reconcile_performance_monitor"):
            self._reconcile_performance_monitor()
        return self.show_perf_overlay

    def toggle_minimap(self) -> bool:
        # 4.8.11: Ctrl+M. The card reads the flag every frame, so flipping
        # it is the whole apply step.
        self.minimap_visible = not bool(getattr(self, "minimap_visible", True))
        self.save_options()
        return self.minimap_visible

    def _invalidate_render_caches(self) -> None:
        # 4.3.17: single cache-invalidation seam. Graphics-mode, resolution,
        # and font changes all route through here so a future cache addition
        # cannot be missed by one of the call sites. Each cache rebuilds
        # lazily on the next draw; this never changes render output (the WS-B
        # pixel-hash regression test guards that). Caches are read via getattr
        # because rebuild_fonts() runs early in __init__ before some of them
        # (e.g. tile_cache) are constructed.
        for attr in (
            "ambient_overlay_cache",
            "_hud_panel_cache",
            "_hud_icon_cache",
            "_hud_action_dark_overlay_cache",
            "_aim_cone_cache",
            "_alpha_tile_cache",
            "_wall_fog_gradient_cache",
            "_wall_fog_surface_cache",
            "_title_logo_cache",
            "_animated_logo_cache",
            "_fitted_ui_font_cache",
            "_impact_overlay_cache",
            "_world_text_cache",
            "_world_alpha_surface_cache",
            "_rotated_surface_cache",
            "_ellipse_overlay_cache",
            "_circle_overlay_cache",
            "_mobile_windup_ring_cache",
            "_scaled_soft_shadow_cache",
            "_world_scaled_sprite_cache",
            "_tile_render_descriptor_cache",
            "_minimap_cache",
            "tile_cache",
            "door_tile_cache",
        ):
            cache = getattr(self, attr, None)
            if cache is not None and hasattr(cache, "clear"):
                cache.clear()
        self._mobile_action_rail_cache = None
        self._mobile_action_rail_frame_cache = None
        self._mobile_left_hud_cache = None
        self._mobile_floor_layer_cache = None
        self._mobile_gpu_shell_revision = None
        self._world_layer = None
        self._paused_scene_cache = None
        self._static_menu_last_signature = None
        self._world_scaled_sprite_cache_bytes = 0
        self._wall_fog_surface_cache_bytes = 0
        # MenuRenderer is created after the first font build during Game
        # construction, so keep this hook deliberately optional.
        menus = getattr(self, "menus", None)
        if menus is not None and hasattr(menus, "clear_render_caches"):
            menus.clear_render_caches()
        self._impact_overlay_cache_bytes = 0
        if hasattr(self, "reset_lighting_caches"):
            self.reset_lighting_caches()
        if hasattr(self, "clear_stage_render_cache"):
            self.clear_stage_render_cache()

    def _invalidate_resolution_sized_caches(self) -> None:
        # Actor animation frames are resolution-independent and expensive to
        # decode from an APK. Keep them warm when only the logical canvas changes.
        # Render caches flow through the single _invalidate_render_caches() seam;
        # the buffers reset below are resolution-sized layer surfaces, not
        # memoized render caches, so they stay here.
        self._invalidate_render_caches()
        release_gpu_textures = getattr(self, "release_mobile_gpu_textures", None)
        if callable(release_gpu_textures):
            release_gpu_textures()
        self._world_layer = None
        self._mobile_floor_layer_cache = None
        self._screen_flash_surface = None

    def cycle_mobile_render_quality(self, forward: bool = True) -> bool:
        if not getattr(self, "mobile_mode", False):
            return False
        current = normalize_mobile_render_quality(
            getattr(self, "mobile_render_quality", None)
        )
        quality = next_mobile_render_quality(current, forward)
        if quality == current:
            return False

        self.mobile_render_quality = quality
        self.fullscreen = True
        self.screen = self.apply_display_mode()
        self._mobile_layout_cache = None
        self.refresh_mobile_safe_insets()
        self.mobile_layout()
        self.refresh_automatic_ui_scale()
        self._invalidate_resolution_sized_caches()
        self.save_options()
        return True

    def cycle_desktop_render_quality(self, forward: bool = True) -> bool:
        """Cycle the desktop render canvas: 1440p native, 720p, or 540p.

        Lower tiers exist for old hardware: the game renders the whole
        logical canvas in software every frame, so a 720p canvas costs a
        quarter of native's pixels (540p a seventh) while SDL's SCALED
        renderer still fills the window or monitor. Mobile caps its physical
        surface through its own quality row and the Deck already renders
        panel-native (the cheapest configuration), so both are inert here.
        """

        if getattr(self, "mobile_mode", False) or is_steam_deck():
            return False
        current = normalize_mobile_render_quality(
            getattr(self, "desktop_render_quality", None)
        )
        quality = next_mobile_render_quality(current, forward)
        if quality == current:
            return False

        self.desktop_render_quality = quality
        self.screen = self.apply_display_mode()
        self.refresh_automatic_ui_scale()
        self._invalidate_resolution_sized_caches()
        self.save_options()
        return True

    def display_size(self) -> tuple[int, int]:
        try:
            sizes = pygame.display.get_desktop_sizes()
            if sizes:
                return sizes[0]
        except pygame.error:
            pass
        display_info = pygame.display.Info()
        return display_info.current_w, display_info.current_h

    @staticmethod
    def _mobile_slow_renderer_warning(value: object) -> bool:
        message = getattr(value, "message", value)
        return "no fast renderer available" in str(message).lower()

    def _reset_android_display_subsystem(self) -> None:
        # A failed SDL_CreateRenderer tears down Pygame's default window but can
        # leave the video subsystem initialized. Reinitializing gives the next
        # GLES candidate a clean window/context. Custom textures must die before
        # the display-owned renderer or their wrappers retain invalid pointers.
        release_gpu_renderer = getattr(self, "release_mobile_gpu_renderer", None)
        if callable(release_gpu_renderer):
            release_gpu_renderer()
        try:
            title = pygame.display.get_caption()[0] or "Arch Rogue"
        except pygame.error:
            title = "Arch Rogue"
        try:
            pygame.display.quit()
        finally:
            pygame.display.init()
            pygame.display.set_caption(title)

    def _record_mobile_renderer(
        self,
        surface: pygame.Surface,
        *,
        name: str,
        accelerated: bool,
        failures: list[str],
    ) -> None:
        self._mobile_renderer_name = name
        self._mobile_renderer_accelerated = accelerated
        self._mobile_renderer_failures = tuple(failures)
        self._mobile_renderer_logical_size = surface.get_size()
        self._mobile_renderer_scale = (0.0, 0.0)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                from pygame._sdl2.video import Renderer, Window

                window = Window.from_display_module()
                renderer = Renderer.from_window(window)
                self._mobile_renderer_logical_size = tuple(renderer.logical_size)
                self._mobile_renderer_scale = tuple(renderer.scale)
                configure_gpu_renderer = getattr(
                    self, "configure_mobile_gpu_renderer", None
                )
                if callable(configure_gpu_renderer):
                    configure_gpu_renderer(window, renderer)
        except (AttributeError, ImportError, TypeError, ValueError, pygame.error):
            release_gpu_renderer = getattr(self, "release_mobile_gpu_renderer", None)
            if callable(release_gpu_renderer):
                release_gpu_renderer()
        try:
            window_size = pygame.display.get_window_size()
        except pygame.error:
            window_size = (0, 0)
        try:
            cpu_features = pygame.system.get_cpu_instruction_sets()
            neon = bool(cpu_features.get("NEON", False))
        except (AttributeError, TypeError, pygame.error):
            neon = None
        try:
            smoothscale = pygame.transform.get_smoothscale_backend()
        except (AttributeError, ValueError, pygame.error):
            smoothscale = "unknown"
        alpha_sdl2 = "PYGAME_BLEND_ALPHA_SDL2" in os.environ
        self._mobile_cpu_neon = neon
        self._mobile_alpha_sdl2 = alpha_sdl2
        self._mobile_surface_masks = tuple(int(mask) for mask in surface.get_masks())
        neon_label = "yes" if neon is True else "no" if neon is False else "unknown"
        mask_label = "/".join(f"{mask:08x}" for mask in self._mobile_surface_masks)
        failure_label = "|".join(failures) if failures else "none"
        print(
            "ARCH_ROGUE_PERF display "
            f"renderer={name} accelerated={'yes' if accelerated else 'no'} "
            f"alpha_sdl2={'yes' if alpha_sdl2 else 'no'} neon={neon_label} "
            f"smoothscale={smoothscale} bpp={surface.get_bitsize()} masks={mask_label} "
            f"logical={surface.get_width()}x{surface.get_height()} "
            f"window={window_size[0]}x{window_size[1]} "
            f"renderer_logical={self._mobile_renderer_logical_size[0]}x"
            f"{self._mobile_renderer_logical_size[1]} "
            f"renderer_scale={self._mobile_renderer_scale[0]:.3f}x"
            f"{self._mobile_renderer_scale[1]:.3f} failures={failure_label}",
            flush=True,
        )

    def _apply_android_scaled_mode(
        self, logical_size: tuple[int, int]
    ) -> pygame.Surface:
        release_gpu_renderer = getattr(self, "release_mobile_gpu_renderer", None)
        if callable(release_gpu_renderer):
            release_gpu_renderer()
        flags = pygame.FULLSCREEN | pygame.SCALED
        requested = os.environ.get("SDL_RENDER_DRIVER", "").strip().lower()
        candidates: list[str] = []
        for driver in (requested, *ANDROID_RENDER_DRIVER_CANDIDATES):
            if driver and driver != "software" and driver not in candidates:
                candidates.append(driver)

        failures: list[str] = []
        for index, driver in enumerate(candidates):
            if index:
                self._reset_android_display_subsystem()
            os.environ["SDL_RENDER_DRIVER"] = driver
            try:
                # Pygame CE emits this warning only after SDL_GetRendererInfo
                # reports no SDL_RENDERER_ACCELERATED flag. Turning that one
                # warning into an exception also makes display.c clean up the
                # unusable software renderer before we try another candidate.
                with warnings.catch_warnings():
                    warnings.filterwarnings(
                        "error",
                        message=r"^no fast renderer available$",
                        category=Warning,
                    )
                    surface = pygame.display.set_mode(logical_size, flags)
            except (pygame.error, Warning) as exc:
                failures.append(f"{driver}:{type(exc).__name__}:{exc}")
                continue
            self._record_mobile_renderer(
                surface,
                name=driver,
                accelerated=True,
                failures=failures,
            )
            return surface

        # GLES2 is mandatory on the supported Android API range, but retain a
        # last-resort automatic path so a vendor renderer failure does not turn
        # a performance problem into an app-launch failure. Telemetry marks a
        # software fallback explicitly.
        if candidates:
            self._reset_android_display_subsystem()
        os.environ.pop("SDL_RENDER_DRIVER", None)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            surface = pygame.display.set_mode(logical_size, flags)
        accelerated = not any(
            self._mobile_slow_renderer_warning(value) for value in caught
        )
        renderer_name = "auto" if accelerated else "software"
        self._record_mobile_renderer(
            surface,
            name=renderer_name,
            accelerated=accelerated,
            failures=failures,
        )
        return surface

    def apply_display_mode(self, headless: bool = False) -> pygame.Surface:
        if headless:
            return pygame.display.set_mode(self.windowed_size, pygame.HIDDEN)
        if getattr(self, "mobile_mode", False):
            # Android SDL owns the native landscape surface. Render to a capped
            # same-aspect logical surface and let SDL's GPU scaler fill the
            # physical display; low-resolution devices remain native-sized.
            physical_size = self.display_size()
            if physical_size[1] > physical_size[0]:
                # Some Android devices report the boot orientation until the
                # manifest-locked landscape activity creates its first window.
                physical_size = (physical_size[1], physical_size[0])
            logical_size = mobile_logical_resolution(
                physical_size,
                getattr(
                    self,
                    "mobile_render_quality",
                    MOBILE_RENDER_QUALITY_PERFORMANCE,
                ),
            )
            if android_runtime_active():
                return self._apply_android_scaled_mode(logical_size)
            return pygame.display.set_mode(logical_size, pygame.FULLSCREEN | pygame.SCALED)
        if self.fullscreen:
            # Use SDL's scaled fullscreen path so the game surface is expanded to
            # the actual monitor instead of being placed unscaled in the top-left
            # when the requested logical size differs from the desktop mode.
            fullscreen_size = self._desktop_logical_size()
            return pygame.display.set_mode(
                fullscreen_size, pygame.FULLSCREEN | pygame.SCALED
            )
        # Windowed desktop renders the same fixed logical canvas as fullscreen
        # and lets SDL's scaled renderer fit it to whatever size the user drags
        # the window to (aspect kept, mouse coordinates remapped by pygame).
        # The game therefore lays out against one known resolution everywhere
        # instead of re-flowing the UI for arbitrary window sizes.
        return pygame.display.set_mode(
            self._desktop_logical_size(), pygame.RESIZABLE | pygame.SCALED
        )

    def _desktop_logical_size(self) -> tuple[int, int]:
        """Logical render size for the desktop windowed and fullscreen paths.

        Off-Deck we render a fixed 16:9 canvas and let SDL's ``SCALED``
        renderer fit it to the monitor (fullscreen) or the window (windowed).
        That keeps every desktop layout identical. The canvas defaults to
        2560×1440; the render-resolution option drops it to 1280×720 or
        960×540 for old hardware (the same height caps the mobile quality
        tiers use, which on the 16:9 canvas resolve to exact halves so the
        canvas-derived automatic UI scale keeps proportions intact).

        On the Steam Deck the panel is 1280×800 (16:10). The fixed 16:9 canvas
        would be rendered at 2560×1440 logical pixels and then downscaled to
        the panel — a 4× up-then-down waste plus letterbox bars top and
        bottom. Instead, on the Deck we render at the panel's own resolution
        so there is no scaling pass at all and the 16:10 aspect is filled
        edge-to-edge. ``SCALED`` is still passed so the same code path handles
        the swap-to-display.
        """

        if is_steam_deck():
            try:
                info = pygame.display.Info()
                width, height = int(info.current_w), int(info.current_h)
            except (pygame.error, AttributeError, ValueError):
                return (SCREEN_WIDTH, SCREEN_HEIGHT)
            if width >= 640 and height >= 480 and width * height > 0:
                return (width, height)
        base = mobile_logical_resolution(
            (SCREEN_WIDTH, SCREEN_HEIGHT),
            getattr(self, "desktop_render_quality", MOBILE_RENDER_QUALITY_NATIVE),
        )
        # Non-16:9 displays (16:10 handhelds where DMI detection is
        # unavailable — e.g. sandboxed installs — 3:2 laptops, ultrawides):
        # a fixed 16:9 canvas under SCALED keeps its aspect and letterboxes,
        # so menu backdrops and the world get black bars. Match the canvas
        # width to the display aspect at the same quality-capped height and
        # SCALED fills the panel edge-to-edge instead. The 1×1 dummy driver
        # and any unreadable Info fall through to the fixed 16:9 canvas.
        try:
            info = pygame.display.Info()
            display_w, display_h = int(info.current_w), int(info.current_h)
        except (pygame.error, AttributeError, ValueError):
            return base
        if display_w >= 640 and display_h >= 480:
            width = round(base[1] * display_w / display_h / 2) * 2
            if abs(width - base[0]) >= 4:
                return (max(640, width), base[1])
        return base

    def rebuild_fonts(self) -> None:
        self.tiny_font = pygame.font.Font(None, 14 * self.ui_scale)
        self.small_font = pygame.font.Font(None, 16 * self.ui_scale)
        # 4.9.x: cutscene choice labels — between small and the main font.
        self.choice_font = pygame.font.Font(None, 19 * self.ui_scale)
        self.font = pygame.font.Font(None, 22 * self.ui_scale)
        self.heading_font = pygame.font.Font(None, 32 * self.ui_scale)
        self.big_font = pygame.font.Font(None, 48 * self.ui_scale)
        self.title_font = pygame.font.Font(None, 62 * self.ui_scale)
        # Clear the cached font.size() results: the Font objects are replaced, so
        # keys based on id(font) would otherwise collide with the new fonts.
        self._text_size_cache = {}
        # Rendered HUD text surfaces keyed by id(font) / ui_scale; the broader
        # render caches (HUD panels/icons, title logo, fitted fonts, tiles,
        # aim cone, ambient overlay, impact overlays, lighting, stage) flow
        # through the single _invalidate_render_caches() seam.
        self._ui_text_cache = {}
        self._invalidate_render_caches()

    def available_difficulty_profiles(self) -> tuple[DifficultyProfile, ...]:
        return tuple(
            profile
            for profile in DIFFICULTY_PROFILES
            if self.hell_unlocked or profile.name != HELL_DIFFICULTY_NAME
        )

    def sanitize_difficulty_name(self, name: str) -> str:
        available_names = {
            profile.name for profile in self.available_difficulty_profiles()
        }
        if name in available_names:
            return name
        return DEFAULT_DIFFICULTY_NAME

    def difficulty_profile(self) -> DifficultyProfile:
        difficulty_name = self.sanitize_difficulty_name(self.difficulty_name)
        if difficulty_name != self.difficulty_name:
            self.difficulty_name = difficulty_name
        return next(
            profile
            for profile in DIFFICULTY_PROFILES
            if profile.name == self.difficulty_name
        )

    def cycle_difficulty(self) -> None:
        profiles = self.available_difficulty_profiles()
        if not profiles:
            self.difficulty_name = DEFAULT_DIFFICULTY_NAME
            self.save_options()
            return
        current_name = self.sanitize_difficulty_name(self.difficulty_name)
        current_index = next(
            (
                index
                for index, profile in enumerate(profiles)
                if profile.name == current_name
            ),
            0,
        )
        self.difficulty_name = profiles[(current_index + 1) % len(profiles)].name
        self.save_options()

    def unlock_hell_difficulty(self) -> bool:
        if self.hell_unlocked:
            return False
        self.hell_unlocked = True
        self.hell_unlocked_this_run = True
        self.save_options()
        return True

    def default_meta_progress(self) -> dict[str, Any]:
        return {
            "runs_started": 0,
            "clears": 0,
            "best_depth": 0,
            # 4.9.21: co-op clears counted separately because they arrive by a
            # different path on the joining client (see mp_record_local_result).
            "coop_clears": 0,
            "lifetime_kills": 0,
            "lifetime_secrets": 0,
            "lifetime_shrines": 0,
            # 4.9.25: every touch of the hidden face wall, for Wall Facer.
            "lifetime_wall_touches": 0,
            "bosses_defeated": [],
            "themes_seen": [],
            "modifiers_seen": [],
            "legendary_loot_seen": [],
            # Which difficulties and archetypes have actually been cleared.
            # Before 4.9.21 this survived only in the rolling 12-entry
            # run_history, so a player's thirteenth run erased the evidence.
            "clears_by_difficulty": [],
            "clears_by_archetype": [],
            # Achievement ids already granted locally. A cache in front of Steam,
            # not the authority — see arch_rogue.achievements.
            "achievements": [],
            # 4.9: the Ledger remembers — endings as "Archetype:verb" entries,
            # read back by Nim Rue's cross-run greeting.
            "story": {"endings": []},
        }

    def normalize_meta_progress(self, data: Any) -> dict[str, Any]:
        progress = self.default_meta_progress()
        if not isinstance(data, dict):
            return progress
        for key in (
            "runs_started",
            "clears",
            "best_depth",
            "coop_clears",
            "lifetime_kills",
            "lifetime_secrets",
            "lifetime_shrines",
            "lifetime_wall_touches",
        ):
            try:
                progress[key] = max(0, int(data.get(key, progress[key])))
            except (TypeError, ValueError):
                progress[key] = 0
        for key in (
            "bosses_defeated",
            "themes_seen",
            "modifiers_seen",
            "legendary_loot_seen",
            "clears_by_difficulty",
            "clears_by_archetype",
        ):
            values = data.get(key, [])
            if isinstance(values, list):
                cleaned = {str(value) for value in values if str(value)}
                if key == "bosses_defeated":
                    # Ledgers written before 4.9.22 hold runtime nameplates
                    # ("the Toll-Keeper Mycelial Matron", "Voidbound Gate
                    # Tyrant") rather than definition names, which is what boss
                    # achievements key on. Canonicalising here retroactively
                    # heals them: the startup evaluation then grants what the
                    # decorated entry silently withheld.
                    cleaned = {canonical_boss_name(value) for value in cleaned}
                progress[key] = sorted(cleaned)[:80]
        # Granted achievements are capped far higher than the other lists: the
        # catalogue is ~40 ids today and truncating it would silently re-grant.
        unlocked = data.get("achievements", [])
        if isinstance(unlocked, list):
            progress["achievements"] = sorted(
                {str(value) for value in unlocked if str(value)}
            )[:400]
        story_meta = data.get("story")
        if isinstance(story_meta, dict):
            endings = story_meta.get("endings")
            progress["story"] = {
                "endings": [str(entry) for entry in endings if str(entry)][-24:]
                if isinstance(endings, list)
                else []
            }
        return progress

    def options_to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "schema_version": 10,
            "audio_enabled": self.audio_enabled,
            "music_enabled": self.music_enabled,
            "fullscreen": self.fullscreen,
            "mobile_render_quality": normalize_mobile_render_quality(
                getattr(self, "mobile_render_quality", None),
                default=default_mobile_render_quality(
                    bool(getattr(self, "mobile_mode", False))
                ),
            ),
            # 4.9.25: desktop render canvas tier (native 1440p / 720p / 540p).
            # Option files written before the key existed stay at native.
            "desktop_render_quality": normalize_mobile_render_quality(
                getattr(self, "desktop_render_quality", None)
            ),
            "ui_scale": self.ui_scale,
            "ui_scale_auto": getattr(self, "ui_scale_auto", True),
            "difficulty": self.difficulty_profile().name,
            "hell_unlocked": self.hell_unlocked,
            "meta_progress": self.meta_progress,
            "run_history": self.run_history[-12:],
            "controller_enabled": getattr(self, "controller_enabled", True),
            "last_controller_guid": getattr(self, "last_controller_guid", ""),
            "deck_gamepad_profile_version": DECK_GAMEPAD_PROFILE_VERSION,
            "gamepad_mapping": serialize_gamepad_mapping(
                normalize_gamepad_mapping(getattr(self, "gamepad_mapping", None))
            ),
            "lighting_enabled": getattr(self, "_lighting_enabled", True),
            "lighting_normal_maps": getattr(self, "_lighting_normal_maps", True),
            # Schema v10: the former binary flag became a three-tier setting.
            # Keep the derived boolean for one compatibility cycle so older
            # integrations can still identify explicit procedural mode.
            "graphics_tier": normalize_graphics_tier(
                getattr(self, "graphics_tier", GRAPHICS_TIER_DEFAULT)
            ),
            "authored_graphics_tier": normalize_graphics_tier(
                getattr(
                    self,
                    "_authored_graphics_tier",
                    GRAPHICS_TIER_DEFAULT,
                ),
                default=GRAPHICS_TIER_DEFAULT,
            ),
            "legacy_graphics": (
                normalize_graphics_tier(
                    getattr(self, "graphics_tier", GRAPHICS_TIER_DEFAULT)
                )
                == GRAPHICS_TIER_LEGACY
            ),
            # Schema v7 (4.3.17): frame-rate cap and dev perf overlay. Older
            # option files migrate to 60 FPS / overlay off.
            "frame_rate_cap": normalize_frame_rate_cap(
                getattr(self, "frame_rate_cap", FRAME_RATE_CAP_DEFAULT)
            ),
            "show_perf_overlay": bool(
                getattr(self, "show_perf_overlay", False)
            ),
            # Schema v9 (4.8.11): desktop minimap card. Older option files
            # migrate to visible.
            "minimap_visible": bool(getattr(self, "minimap_visible", True)),
            # Schema v8 (4.6): multiplayer identity + server endpoint. The
            # endpoint is unset by default; multiplayer stays unreachable from
            # the menu until a non-empty host and a port in 1..65535 exist.
            "mp_player_name": sanitize_player_name(
                getattr(self, "mp_player_name", "")
            ),
            "mp_server_host": normalize_mp_server_host(
                getattr(self, "mp_server_host", "")
            ),
            "mp_server_port": normalize_mp_server_port(
                getattr(self, "mp_server_port", 0)
            ),
            # 4.6.x: TLS to the relay server, on by default. Option files
            # written before the key existed migrate to encrypted.
            "mp_server_tls": normalize_mp_server_tls(
                getattr(self, "mp_server_tls", True)
            ),
        }

    def load_options(self) -> bool:
        try:
            data = json.loads(self.options_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        try:
            schema_version = int(data.get("schema_version", 1))
            mobile_mode = bool(getattr(self, "mobile_mode", False))
            # Deprecation cutoff: 4.4 — legacy mobile quality migration covered
            # schema < 6 option files (4.2.x -> 4.3.0 upgrade). Keep through
            # 4.3.x; remove in 4.4.
            legacy_mobile_quality_migration = (
                mobile_mode
                and schema_version < 6
                and "mobile_render_quality" not in data
            )
            quality_default = default_mobile_render_quality(mobile_mode)
            if legacy_mobile_quality_migration:
                quality_default = MOBILE_RENDER_QUALITY_PERFORMANCE
            self.mobile_render_quality = normalize_mobile_render_quality(
                data.get("mobile_render_quality"), default=quality_default
            )
            self.desktop_render_quality = normalize_mobile_render_quality(
                data.get("desktop_render_quality")
            )
            self.audio_enabled = bool(data.get("audio_enabled", True))
            # 4.11.0: music is parked until the real tracks land. The persisted
            # key is deliberately ignored (not just defaulted) so a profile
            # that enabled the old placeholder loop stays silent; the Options
            # row and its M shortcut are removed alongside this.
            self.music_enabled = False
            self.fullscreen = bool(data.get("fullscreen", True))
            has_saved_ui_scale = "ui_scale" in data
            loaded_ui_scale = max(
                1, min(4, int(data.get("ui_scale", UI_SCALE)))
            )
            has_auto_mode = "ui_scale_auto" in data
            loaded_ui_scale_auto = bool(
                data.get("ui_scale_auto", not has_saved_ui_scale)
            )
            # Deprecation cutoff: 4.4 -- legacy UI-scale migration covered
            # schema-4 option files that serialized a scale without an auto
            # flag. Keep through 4.3.x; remove in 4.4.
            legacy_ui_scale_migration = (
                has_saved_ui_scale and not has_auto_mode
            )
            self.hell_unlocked = bool(data.get("hell_unlocked", False))
            self.meta_progress = self.normalize_meta_progress(data.get("meta_progress"))
            history = data.get("run_history", [])
            self.run_history = history[-12:] if isinstance(history, list) else []
            self.difficulty_name = self.sanitize_difficulty_name(
                str(data.get("difficulty", DEFAULT_DIFFICULTY_NAME))
            )
            # Schema v3 (milestone 3.9): controller prefs. Missing on older
            # saves -> safe defaults (controller on, no preferred device).
            self.controller_enabled = bool(data.get("controller_enabled", True))
            self.last_controller_guid = str(data.get("last_controller_guid", ""))
            self.gamepad_mapping = normalize_gamepad_mapping(
                data.get("gamepad_mapping")
            )
            deck_profile_version = data.get("deck_gamepad_profile_version", 0)
            if not isinstance(deck_profile_version, int):
                deck_profile_version = 0
            if (
                is_steam_deck()
                and deck_profile_version < DECK_GAMEPAD_PROFILE_VERSION
            ):
                add_missing_deck_gameplay_aliases(self.gamepad_mapping)
            # Milestone 3.16 - continuous lighting. Pre-v6 mobile files already
            # serialized the old True default, so a no-quality migration must
            # explicitly switch normal maps off to avoid the cold ARM cache spike.
            # Schema-v6 choices and non-migrating explicit values stay authoritative.
            self._lighting_enabled = bool(data.get("lighting_enabled", True))
            if legacy_mobile_quality_migration:
                self._lighting_normal_maps = False
            else:
                normal_maps_default = False if mobile_mode else True
                self._lighting_normal_maps = bool(
                    data.get("lighting_normal_maps", normal_maps_default)
                )
            # Schema v10: authored graphics split into the original
            # lower-resolution Modern world and the new HD world. Existing
            # option files retain their previous visuals: procedural stays
            # Legacy, while the old "Asset sprites" state becomes Modern.
            if "graphics_tier" in data:
                self.graphics_tier = normalize_graphics_tier(
                    data.get("graphics_tier"),
                    default=GRAPHICS_TIER_DEFAULT,
                )
                authored_default = GRAPHICS_TIER_DEFAULT
            else:
                self.graphics_tier = (
                    GRAPHICS_TIER_LEGACY
                    if bool(data.get("legacy_graphics", False))
                    else GRAPHICS_TIER_MODERN
                )
                authored_default = GRAPHICS_TIER_MODERN
            authored_tier = normalize_graphics_tier(
                data.get("authored_graphics_tier"),
                default=authored_default,
            )
            if authored_tier == GRAPHICS_TIER_LEGACY:
                authored_tier = authored_default
            if self.graphics_tier != GRAPHICS_TIER_LEGACY:
                authored_tier = self.graphics_tier
            self._authored_graphics_tier = authored_tier
            self.legacy_graphics = (
                self.graphics_tier == GRAPHICS_TIER_LEGACY
            )
            # Schema v7 (4.3.17): frame-rate cap + dev perf overlay. Pre-v7
            # option files default to 60 FPS and overlay off; run saves stay
            # schema 5 and are unaffected.
            self.frame_rate_cap = normalize_frame_rate_cap(
                data.get("frame_rate_cap", FRAME_RATE_CAP_DEFAULT)
            )
            self.show_perf_overlay = bool(data.get("show_perf_overlay", False))
            # Schema v9 (4.8.11): desktop minimap. Pre-v9 files default to
            # visible; Ctrl+M persists the choice from then on.
            self.minimap_visible = bool(data.get("minimap_visible", True))
            # Schema v8 (4.6): multiplayer name + server endpoint. All older
            # schemas migrate to the unset defaults ("", "", 0).
            self.mp_player_name = sanitize_player_name(
                data.get("mp_player_name", "")
            )
            self.mp_server_host = (
                normalize_mp_server_host(data.get("mp_server_host", ""))
                or DEFAULT_MP_SERVER_HOST
            )
            self.mp_server_port = (
                normalize_mp_server_port(data.get("mp_server_port", 0))
                or DEFAULT_MP_SERVER_PORT
            )
            self.mp_server_tls = normalize_mp_server_tls(
                data.get("mp_server_tls", True)
            )
        except (TypeError, ValueError):
            return False
        frame_pacing = getattr(self, "frame_pacing", None)
        if frame_pacing is not None:
            frame_pacing.set_frame_rate_cap(
                getattr(self, "frame_rate_cap", FRAME_RATE_CAP_DEFAULT)
            )
        self._set_ui_scale(
            loaded_ui_scale,
            automatic=loaded_ui_scale_auto,
            persist=False,
        )
        self._legacy_ui_scale_migration = legacy_ui_scale_migration
        if hasattr(self, "screen"):
            self.refresh_automatic_ui_scale()
        sprites = getattr(self, "sprites", None)
        if (
            sprites is not None
            and (
                getattr(sprites, "graphics_tier", self.graphics_tier)
                != self.graphics_tier
                or getattr(
                    sprites,
                    "authored_graphics_tier",
                    self._authored_graphics_tier,
                )
                != self._authored_graphics_tier
            )
        ):
            self._apply_graphics_mode()
        return True

    def save_options(self) -> bool:
        try:
            self.options_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = Path(f"{self.options_path}.tmp")
            tmp_path.write_text(
                json.dumps(self.options_to_dict(), indent=2), encoding="utf-8"
            )
            tmp_path.replace(self.options_path)
        except (OSError, TypeError, ValueError):
            return False
        return True

    def _apply_graphics_mode(self) -> None:
        sprites = getattr(self, "sprites", None)
        if sprites is not None and hasattr(sprites, "set_graphics_tier"):
            sprites.set_graphics_tier(self.graphics_tier)
            if hasattr(sprites, "set_authored_graphics_tier"):
                sprites.set_authored_graphics_tier(
                    self._authored_graphics_tier
                )
        elif sprites is not None and hasattr(sprites, "set_legacy_graphics"):
            sprites.set_legacy_graphics(self.legacy_graphics)
        ui_assets = getattr(self, "ui_assets", None)
        if ui_assets is not None and hasattr(ui_assets, "clear_derived_caches"):
            ui_assets.clear_derived_caches()
        # All memoized render caches flow through the single invalidation seam.
        self._invalidate_render_caches()
        tile_cache = getattr(self, "tile_cache", None)
        if tile_cache is not None and hasattr(self, "theme"):
            self.prewarm_tile_cache()

    def set_legacy_graphics(self, enabled: bool) -> None:
        selected = (
            GRAPHICS_TIER_LEGACY
            if bool(enabled)
            else normalize_graphics_tier(
                getattr(
                    self,
                    "_authored_graphics_tier",
                    GRAPHICS_TIER_DEFAULT,
                ),
                default=GRAPHICS_TIER_DEFAULT,
            )
        )
        if selected == GRAPHICS_TIER_LEGACY and not enabled:
            selected = GRAPHICS_TIER_DEFAULT
        self.set_graphics_tier(selected)

    def set_graphics_tier(self, graphics_tier: str) -> None:
        selected = normalize_graphics_tier(graphics_tier)
        sprites = getattr(self, "sprites", None)
        renderer_matches = (
            sprites is None
            or getattr(sprites, "graphics_tier", selected) == selected
        )
        if (
            selected
            == getattr(self, "graphics_tier", GRAPHICS_TIER_DEFAULT)
            and renderer_matches
        ):
            return
        if selected != GRAPHICS_TIER_LEGACY:
            self._authored_graphics_tier = selected
        self.graphics_tier = selected
        self.legacy_graphics = selected == GRAPHICS_TIER_LEGACY
        self._apply_graphics_mode()
        self.save_options()

    def cycle_graphics_tier(self, forward: bool = True) -> None:
        selected = normalize_graphics_tier(
            getattr(self, "graphics_tier", GRAPHICS_TIER_DEFAULT)
        )
        index = GRAPHICS_TIER_VALUES.index(selected)
        step = 1 if forward else -1
        self.set_graphics_tier(
            GRAPHICS_TIER_VALUES[(index + step) % len(GRAPHICS_TIER_VALUES)]
        )

    def graphics_tier_label(self) -> str:
        selected = normalize_graphics_tier(
            getattr(self, "graphics_tier", GRAPHICS_TIER_DEFAULT)
        )
        return GRAPHICS_TIER_LABELS[selected]

    def current_music_profile(self) -> MusicProfile | None:
        if self.state in (
            "title",
            "options",
            "controls",
            "about",
            "archetype_select",
            "confirm_exit",
            "mp_setup",
            "mp_lobby",
        ):
            return MusicProfile(
                0xA11CE,
                "Menu",
                "Main Menu",
                "Quiet",
                depth=0,
                mood="menu",
            )
        if self.state not in ("playing", "dead", "victory") or self.run_music_seed <= 0:
            return None
        return MusicProfile(
            self.run_music_seed,
            self.selected_archetype.name,
            self.run_music_theme or self.theme.name,
            self.run_modifier.name,
            depth=self.current_depth,
        )

    def sync_music(self) -> None:
        transport_time = (
            None if self.music_enabled and self.audio.available else self.elapsed
        )
        self.audio_available = self.audio.sync_music(
            self.current_music_profile(), self.music_enabled, transport_time
        )

    def play_sfx(self, name: str) -> None:
        self.audio_available = self.audio.play_sfx(name, self.audio_enabled)
