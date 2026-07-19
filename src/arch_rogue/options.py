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
import re
import sys
from pathlib import Path
from typing import Any

import pygame

from .audio import MusicProfile
from .constants import SCREEN_HEIGHT, SCREEN_WIDTH, UI_SCALE
from .content import (
    DEFAULT_DIFFICULTY_NAME,
    DIFFICULTY_PROFILES,
    HELL_DIFFICULTY_NAME,
    DifficultyProfile,
)
from .input import normalize_gamepad_mapping, serialize_gamepad_mapping


_BASE_DISPLAY_DPI = 96.0
_XFT_DPI_PATTERN = re.compile(
    r"^\s*Xft\.dpi\s*:\s*([0-9]+(?:\.[0-9]+)?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _valid_display_scale(value: Any) -> float | None:
    try:
        scale = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(scale) or not 0.5 <= scale <= 8.0:
        return None
    return scale


def ui_scale_from_display_scale(display_scale: float | None) -> int:
    """Map an OS display scale to the existing integer UI scale range."""

    scale = _valid_display_scale(display_scale)
    if scale is None:
        return UI_SCALE
    return max(1, min(4, math.floor(scale + 0.5)))


def _scale_from_xresources(resources: str | bytes | None) -> float | None:
    if isinstance(resources, bytes):
        resources = resources.decode("utf-8", errors="replace")
    if not resources:
        return None
    match = _XFT_DPI_PATTERN.search(resources)
    if match is None:
        return None
    try:
        dpi = float(match.group(1))
    except ValueError:
        return None
    if not math.isfinite(dpi) or dpi <= 0:
        return None
    return _valid_display_scale(dpi / _BASE_DISPLAY_DPI)


def _x11_display_scale() -> float | None:
    """Read the desktop's Xft DPI without launching an external process."""

    try:
        import ctypes
        import ctypes.util

        library_name = ctypes.util.find_library("X11")
        if not library_name:
            return None
        x11 = ctypes.CDLL(library_name)
        x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x11.XOpenDisplay.restype = ctypes.c_void_p
        x11.XResourceManagerString.argtypes = [ctypes.c_void_p]
        x11.XResourceManagerString.restype = ctypes.c_char_p
        x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        x11.XCloseDisplay.restype = ctypes.c_int
        display = x11.XOpenDisplay(None)
        if not display:
            return None
        try:
            return _scale_from_xresources(x11.XResourceManagerString(display))
        finally:
            x11.XCloseDisplay(display)
    except (AttributeError, OSError, TypeError, ValueError):
        return None


def _windows_display_scale() -> float | None:
    try:
        import ctypes

        window = pygame.display.get_wm_info().get("window")
        if not isinstance(window, int) or window <= 0:
            return None
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        get_dpi_for_window = user32.GetDpiForWindow
        get_dpi_for_window.argtypes = [ctypes.c_void_p]
        get_dpi_for_window.restype = ctypes.c_uint
        dpi = int(get_dpi_for_window(ctypes.c_void_p(window)))
        if dpi <= 0:
            return None
        return _valid_display_scale(dpi / _BASE_DISPLAY_DPI)
    except (AttributeError, OSError, TypeError, ValueError, pygame.error):
        return None


def _macos_display_scale() -> float | None:
    """Return the main display's backing-pixel-to-point ratio."""

    try:
        import ctypes
        import ctypes.util

        core_graphics_name = ctypes.util.find_library("CoreGraphics")
        core_foundation_name = ctypes.util.find_library("CoreFoundation")
        if not core_graphics_name or not core_foundation_name:
            return None
        core_graphics = ctypes.CDLL(core_graphics_name)
        core_foundation = ctypes.CDLL(core_foundation_name)
        core_graphics.CGMainDisplayID.argtypes = []
        core_graphics.CGMainDisplayID.restype = ctypes.c_uint32
        display_id = core_graphics.CGMainDisplayID()
        try:
            class CGPoint(ctypes.Structure):
                _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

            core_graphics.CGGetDisplaysWithPoint.argtypes = [
                CGPoint,
                ctypes.c_uint32,
                ctypes.POINTER(ctypes.c_uint32),
                ctypes.POINTER(ctypes.c_uint32),
            ]
            core_graphics.CGGetDisplaysWithPoint.restype = ctypes.c_int32
            window_x, window_y = pygame.display.get_window_position()
            window_w, window_h = pygame.display.get_window_size()
            display_ids = (ctypes.c_uint32 * 1)()
            display_count = ctypes.c_uint32()
            result = core_graphics.CGGetDisplaysWithPoint(
                CGPoint(window_x + window_w * 0.5, window_y + window_h * 0.5),
                1,
                display_ids,
                ctypes.byref(display_count),
            )
            if result == 0 and display_count.value:
                display_id = display_ids[0]
        except (AttributeError, TypeError, ValueError, pygame.error):
            pass
        core_graphics.CGDisplayCopyDisplayMode.argtypes = [ctypes.c_uint32]
        core_graphics.CGDisplayCopyDisplayMode.restype = ctypes.c_void_p
        core_graphics.CGDisplayModeGetWidth.argtypes = [ctypes.c_void_p]
        core_graphics.CGDisplayModeGetWidth.restype = ctypes.c_size_t
        core_graphics.CGDisplayModeGetPixelWidth.argtypes = [ctypes.c_void_p]
        core_graphics.CGDisplayModeGetPixelWidth.restype = ctypes.c_size_t
        core_foundation.CFRelease.argtypes = [ctypes.c_void_p]
        core_foundation.CFRelease.restype = None
        mode = core_graphics.CGDisplayCopyDisplayMode(display_id)
        if not mode:
            return None
        try:
            logical_width = int(core_graphics.CGDisplayModeGetWidth(mode))
            pixel_width = int(core_graphics.CGDisplayModeGetPixelWidth(mode))
        finally:
            core_foundation.CFRelease(mode)
        if logical_width <= 0 or pixel_width <= 0:
            return None
        return _valid_display_scale(pixel_width / logical_width)
    except (AttributeError, OSError, TypeError, ValueError):
        return None


def _environment_display_scale() -> float | None:
    # The app-specific override is useful on Wayland compositors where SDL2 does
    # not expose output scaling. Toolkit variables are lower-confidence fallbacks.
    for name in ("ARCH_ROGUE_DISPLAY_SCALE", "GDK_SCALE", "QT_SCALE_FACTOR"):
        scale = _valid_display_scale(os.environ.get(name))
        if scale is not None:
            return scale
    return None


def detect_host_display_scale() -> float | None:
    """Best-effort OS desktop scale for the display hosting the game window."""

    try:
        driver = pygame.display.get_driver()
    except pygame.error:
        driver = ""
    if driver == "dummy" or sys.platform == "emscripten":
        return None

    override = _valid_display_scale(os.environ.get("ARCH_ROGUE_DISPLAY_SCALE"))
    if override is not None:
        return override
    if sys.platform == "win32":
        return _windows_display_scale() or _environment_display_scale()
    if sys.platform == "darwin":
        return _macos_display_scale() or _environment_display_scale()
    if driver == "x11":
        return _x11_display_scale() or _environment_display_scale()
    return _environment_display_scale()


class OptionsMixin:
    def prepare_display_scaling(self) -> None:
        # SDL must declare DPI awareness before its video subsystem starts.
        if sys.platform == "win32":
            os.environ.setdefault("SDL_WINDOWS_DPI_AWARENESS", "permonitorv2")

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
        if getattr(self, "mobile_mode", False) and hasattr(self, "screen"):
            width, height = self.screen.get_size()
            display_scale = max(1.0, min(width / 1280.0, height / 720.0))
            target = max(1, min(4, math.floor(display_scale + 0.5)))
        else:
            display_scale = detect_host_display_scale()
            if display_scale is None:
                self.detected_display_scale = None
                return False
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

    def display_size(self) -> tuple[int, int]:
        try:
            sizes = pygame.display.get_desktop_sizes()
            if sizes:
                return sizes[0]
        except pygame.error:
            pass
        display_info = pygame.display.Info()
        return display_info.current_w, display_info.current_h

    def apply_display_mode(self, headless: bool = False) -> pygame.Surface:
        if headless:
            return pygame.display.set_mode(self.windowed_size, pygame.HIDDEN)
        if getattr(self, "mobile_mode", False):
            # Android SDL owns the native surface and orientation. Request the
            # actual landscape display instead of scaling a fixed 16:9 desktop
            # canvas, so wide phones and tablets use every safe pixel.
            return pygame.display.set_mode(self.display_size(), pygame.FULLSCREEN)
        if self.fullscreen:
            # Use SDL's scaled fullscreen path so the game surface is expanded to
            # the actual monitor instead of being placed unscaled in the top-left
            # when the requested logical size differs from the desktop mode.
            return pygame.display.set_mode(
                (SCREEN_WIDTH, SCREEN_HEIGHT), pygame.FULLSCREEN | pygame.SCALED
            )
        return pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)

    def rebuild_fonts(self) -> None:
        self.tiny_font = pygame.font.Font(None, 14 * self.ui_scale)
        self.small_font = pygame.font.Font(None, 16 * self.ui_scale)
        self.font = pygame.font.Font(None, 22 * self.ui_scale)
        self.heading_font = pygame.font.Font(None, 32 * self.ui_scale)
        self.big_font = pygame.font.Font(None, 48 * self.ui_scale)
        self.title_font = pygame.font.Font(None, 62 * self.ui_scale)
        # Clear the cached font.size() results: the Font objects are replaced, so
        # keys based on id(font) would otherwise collide with the new fonts.
        self._text_size_cache = {}
        # Rendered HUD text surfaces and panel art are keyed by id(font) /
        # ui_scale, so drop them when fonts are rebuilt (which also fires on
        # ui_scale / resolution changes) to avoid stale or colliding entries.
        self._ui_text_cache = {}
        self._hud_panel_cache = {}
        self._hud_icon_cache = {}
        self._title_logo_cache = {}
        self._fitted_ui_font_cache = {}

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
            "bosses_defeated": [],
            "themes_seen": [],
            "modifiers_seen": [],
            "legendary_loot_seen": [],
        }

    def normalize_meta_progress(self, data: Any) -> dict[str, Any]:
        progress = self.default_meta_progress()
        if not isinstance(data, dict):
            return progress
        for key in ("runs_started", "clears", "best_depth"):
            try:
                progress[key] = max(0, int(data.get(key, progress[key])))
            except (TypeError, ValueError):
                progress[key] = 0
        for key in (
            "bosses_defeated",
            "themes_seen",
            "modifiers_seen",
            "legendary_loot_seen",
        ):
            values = data.get(key, [])
            if isinstance(values, list):
                progress[key] = sorted({str(value) for value in values if str(value)})[
                    :80
                ]
        return progress

    def options_to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "schema_version": 5,
            "audio_enabled": self.audio_enabled,
            "music_enabled": self.music_enabled,
            "fullscreen": self.fullscreen,
            "ui_scale": self.ui_scale,
            "ui_scale_auto": getattr(self, "ui_scale_auto", True),
            "difficulty": self.difficulty_profile().name,
            "hell_unlocked": self.hell_unlocked,
            "meta_progress": self.meta_progress,
            "run_history": self.run_history[-12:],
            "controller_enabled": getattr(self, "controller_enabled", True),
            "last_controller_guid": getattr(self, "last_controller_guid", ""),
            "gamepad_mapping": serialize_gamepad_mapping(
                normalize_gamepad_mapping(getattr(self, "gamepad_mapping", None))
            ),
            "lighting_enabled": getattr(self, "_lighting_enabled", True),
            "lighting_normal_maps": getattr(self, "_lighting_normal_maps", True),
            "legacy_graphics": getattr(self, "legacy_graphics", False),
        }

    def load_options(self) -> bool:
        try:
            data = json.loads(self.options_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        try:
            self.audio_enabled = bool(data.get("audio_enabled", True))
            self.music_enabled = bool(data.get("music_enabled", False))
            self.fullscreen = bool(data.get("fullscreen", True))
            has_saved_ui_scale = "ui_scale" in data
            loaded_ui_scale = max(
                1, min(4, int(data.get("ui_scale", UI_SCALE)))
            )
            has_auto_mode = "ui_scale_auto" in data
            loaded_ui_scale_auto = bool(
                data.get("ui_scale_auto", not has_saved_ui_scale)
            )
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
            # Milestone 3.16 - continuous lighting. Missing on older saves
            # falls back to safe native defaults. The web build forces these
            # off in make_game.
            self._lighting_enabled = bool(data.get("lighting_enabled", True))
            self._lighting_normal_maps = bool(data.get("lighting_normal_maps", True))
            # Schema v4 (milestone 4.0): modern asset sprites are the default.
            # Older option files omit this field and migrate to modern graphics;
            # missing individual resources still fall back procedurally.
            self.legacy_graphics = bool(data.get("legacy_graphics", False))
        except (TypeError, ValueError):
            return False
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
            and getattr(sprites, "legacy_graphics", self.legacy_graphics)
            != self.legacy_graphics
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
        if sprites is not None and hasattr(sprites, "set_legacy_graphics"):
            sprites.set_legacy_graphics(self.legacy_graphics)
        ui_assets = getattr(self, "ui_assets", None)
        if ui_assets is not None and hasattr(ui_assets, "clear_derived_caches"):
            ui_assets.clear_derived_caches()
        if hasattr(self, "clear_stage_render_cache"):
            self.clear_stage_render_cache()
        self._hud_panel_cache = {}
        self._hud_icon_cache = {}
        self._aim_cone_cache = {}
        tile_cache = getattr(self, "tile_cache", None)
        if tile_cache is not None:
            tile_cache.clear()
        self.door_tile_cache = {}
        self._alpha_tile_cache = {}
        if hasattr(self, "reset_lighting_caches"):
            self.reset_lighting_caches()
        if tile_cache is not None and hasattr(self, "theme"):
            self.prewarm_tile_cache()

    def set_legacy_graphics(self, enabled: bool) -> None:
        enabled = bool(enabled)
        sprites = getattr(self, "sprites", None)
        renderer_matches = (
            sprites is None or getattr(sprites, "legacy_graphics", enabled) == enabled
        )
        if enabled == getattr(self, "legacy_graphics", False) and renderer_matches:
            return
        self.legacy_graphics = enabled
        self._apply_graphics_mode()
        self.save_options()

    def current_music_profile(self) -> MusicProfile | None:
        if self.state in (
            "title",
            "options",
            "controls",
            "about",
            "archetype_select",
            "confirm_exit",
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
