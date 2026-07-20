# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
#
# AI Provenance & Liability Notice:
# This repository contains code generated, assisted, or refactored by Artificial
# Intelligence models. Provided strictly "AS IS" under Apache 2.0 with no warranty
# of clean IP provenance or non-infringement; downstream users assume all legal
# and financial risk and should perform their own compliance audits.

# pyright: reportAttributeAccessIssue=false
"""Android/mobile layout, touch input, lifecycle, and storage helpers.

The desktop renderer and input paths remain authoritative.  Mobile mode adds a
safe-area-aware landscape composition and translates true SDL finger events into
the same semantic commands used by keyboard and gamepad input.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

import pygame

from .content import ARCHETYPES
from .input import Command


_TRUE_VALUES = frozenset(("1", "true", "yes", "on"))
_FALSE_VALUES = frozenset(("0", "false", "no", "off"))
MOBILE_PERF_LOG_PREFIX = "ARCH_ROGUE_PERF"
MOBILE_PERF_REPORT_INTERVAL = 4.0
PYGAME_BLEND_ALPHA_SDL2_ENV = "PYGAME_BLEND_ALPHA_SDL2"
MOBILE_PERF_PHASES = (
    "tick",
    "events",
    "update",
    "clear",
    "menu",
    "world",
    "hud",
    "overlays",
    "flip",
    "audio",
)
MOBILE_PERF_DETAIL_PHASES = (
    "floor",
    "objects",
    "guidance",
    "light_build",
    "ambient",
    "base_upload",
    "light_upload",
    "ui_upload",
    "gpu_present",
)
# SDL2's stable blend-mode values. pygame._sdl2 accepts these integer values but
# does not export the corresponding SDL_BLENDMODE_* constants in pygame-ce 2.5.7.
SDL_BLENDMODE_NONE = 0
SDL_BLENDMODE_BLEND = 1
SDL_BLENDMODE_MOD = 4
_ANDROID_XRGB_MASKS = (0x00FF0000, 0x0000FF00, 0x000000FF, 0x00000000)
_ANDROID_ARGB_MASKS = (0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000)
_COLORKEY_CANDIDATES = (
    (255, 0, 255),
    (0, 255, 0),
    (1, 0, 2),
    (254, 1, 253),
    (3, 5, 7),
    (255, 255, 1),
)
_ANDROID_BINARY_ALPHA_MODE: str | None = None
_ANDROID_BINARY_ALPHA_MIN_BENCHMARK_AREA = 4096


def android_runtime_active() -> bool:
    """Return whether SDL is hosted by a real python-for-android activity."""

    return sys.platform == "android" or "ANDROID_ARGUMENT" in os.environ


def mobile_performance_telemetry_enabled() -> bool:
    """Enable beta telemetry by default on Android, with an env escape hatch."""

    override = os.environ.get("ARCH_ROGUE_PERF", "").strip().lower()
    if override in _TRUE_VALUES:
        return True
    if override in _FALSE_VALUES:
        return False
    return android_runtime_active()


def sdl2_alpha_blitter_requested() -> bool:
    """Return whether pygame cached/uses SDL2's alpha blending semantics."""

    # pygame-ce tests only whether the variable exists, not whether its value is
    # truthy. Mirror that import-time behavior exactly.
    return PYGAME_BLEND_ALPHA_SDL2_ENV in os.environ


def _unused_colorkey(surface: pygame.Surface) -> tuple[int, int, int] | None:
    """Choose a key absent from the source's visible pixels."""

    for color in _COLORKEY_CANDIDATES:
        try:
            matches = pygame.mask.from_threshold(
                surface,
                (*color, 255),
                (1, 1, 1, 1),
            ).count()
        except (TypeError, ValueError, pygame.error):
            return None
        if matches == 0:
            return color
    return None


def _binary_colorkey_surface(
    surface: pygame.Surface,
    key: tuple[int, int, int],
    *,
    rle: bool,
) -> pygame.Surface:
    optimized = pygame.Surface(surface.get_size()).convert()
    optimized.fill(key)
    optimized.blit(surface, (0, 0))
    optimized.set_colorkey(key, pygame.RLEACCEL if rle else 0)
    return optimized


def _benchmark_android_binary_alpha_mode(
    surface: pygame.Surface,
    key: tuple[int, int, int],
) -> tuple[str, pygame.Surface] | None:
    """Choose the fastest equivalent binary-alpha source on this SDL build."""

    global _ANDROID_BINARY_ALPHA_MODE
    if not android_runtime_active() or not pygame.display.get_init():
        return None
    try:
        alpha = surface.convert_alpha()
        alpha_rle = alpha.copy()
        alpha_rle.set_alpha(255, pygame.RLEACCEL)
        colorkey = _binary_colorkey_surface(surface, key, rle=False)
        colorkey_rle = _binary_colorkey_surface(surface, key, rle=True)
        candidates = {
            "alpha": alpha,
            "alpha_rle": alpha_rle,
            "colorkey": colorkey,
            "colorkey_rle": colorkey_rle,
        }
        destination = pygame.Surface(
            (surface.get_width() + 4, surface.get_height() + 4)
        ).convert()
        loops = 12
        timings: dict[str, float] = {}
        for name, candidate in candidates.items():
            # Warm the lazy RLE encoder before measuring steady repeated blits.
            destination.blit(candidate, (1, 1))
            destination.blit(candidate, (2, 2))
            started = time.perf_counter()
            for index in range(loops):
                destination.blit(candidate, (1 + index % 2, 1 + index % 2))
            timings[name] = (time.perf_counter() - started) / loops
        mode = min(timings.items(), key=lambda item: item[1])[0]
    except (TypeError, ValueError, pygame.error):
        _ANDROID_BINARY_ALPHA_MODE = "colorkey_rle"
        return None

    _ANDROID_BINARY_ALPHA_MODE = mode
    labels = ",".join(
        f"{name}:{seconds * 1000.0:.3f}" for name, seconds in timings.items()
    )
    print(
        f"{MOBILE_PERF_LOG_PREFIX} alpha_blit mode={mode} ms={labels} "
        f"sample={surface.get_width()}x{surface.get_height()}",
        flush=True,
    )
    return mode, candidates[mode]


def optimize_immutable_alpha_surface(
    surface: pygame.Surface,
    *,
    alpha: int | None = None,
) -> pygame.Surface:
    """Optimize a read-only transparent source for Android's software blitter.

    Authored pixel art has binary alpha. Converting those final immutable cache
    entries to display-format colorkey surfaces selects SDL's much cheaper RLE
    copy path instead of alpha blending every occupied pixel on ARM. Gradients,
    text, shadows, panels, and any source with partial alpha retain per-pixel
    alpha and only receive the previous RLE hint. Desktop behavior is unchanged.
    """

    if not sdl2_alpha_blitter_requested() or not surface.get_flags() & pygame.SRCALPHA:
        return surface
    area = surface.get_width() * surface.get_height()
    if area <= 0:
        return surface
    target_alpha = surface.get_alpha() if alpha is None else int(alpha)
    target_alpha = 255 if target_alpha is None else max(0, min(255, target_alpha))
    try:
        occupied = pygame.mask.from_surface(surface, 0).count()
        fully_opaque = pygame.mask.from_surface(surface, 254).count()
    except (TypeError, ValueError, pygame.error):
        return surface
    # RLE is a win for transparent runs but adds decode overhead to nearly opaque
    # panels. Actor frames and isometric floor diamonds are typically 15–75%
    # occupied; dense UI art stays on pygame's normal contiguous path.
    if occupied * 100 > area * 85:
        return surface

    if target_alpha == 255 and occupied == fully_opaque:
        key = _unused_colorkey(surface)
        if key is not None:
            try:
                mode = _ANDROID_BINARY_ALPHA_MODE
                if (
                    mode is None
                    and android_runtime_active()
                    and area >= _ANDROID_BINARY_ALPHA_MIN_BENCHMARK_AREA
                ):
                    benchmark = _benchmark_android_binary_alpha_mode(surface, key)
                    if benchmark is not None:
                        return benchmark[1]
                    mode = "colorkey_rle"
                elif mode is None:
                    mode = "colorkey_rle"

                if mode == "colorkey":
                    return _binary_colorkey_surface(surface, key, rle=False)
                if mode == "colorkey_rle":
                    return _binary_colorkey_surface(surface, key, rle=True)
                if mode == "alpha_rle":
                    surface.set_alpha(255, pygame.RLEACCEL)
                return surface
            except (TypeError, ValueError, pygame.error):
                pass

    if surface.get_flags() & pygame.RLEACCEL and surface.get_alpha() == target_alpha:
        return surface
    try:
        surface.set_alpha(target_alpha, pygame.RLEACCEL)
    except (TypeError, ValueError, pygame.error):
        pass
    return surface


def detect_mobile_runtime() -> bool:
    """Return whether Arch Rogue is running in its Android/mobile profile."""

    override = os.environ.get("ARCH_ROGUE_MOBILE", "").strip().lower()
    if override in _TRUE_VALUES:
        return True
    if override in _FALSE_VALUES:
        return False
    return sys.platform == "android" or "ANDROID_ARGUMENT" in os.environ


def application_storage_directory(mobile: bool) -> Path:
    """Return a writable per-application directory for saves and options."""

    if mobile:
        try:
            value = pygame.system.get_pref_path("Arch Rogue", "Arch Rogue")
            if value:
                return Path(value)
        except (AttributeError, OSError, pygame.error):
            pass
        private = os.environ.get("ANDROID_PRIVATE")
        if private:
            return Path(private)
    return Path.home()


@dataclass(frozen=True, slots=True)
class SafeInsets:
    left: int = 0
    top: int = 0
    right: int = 0
    bottom: int = 0

    @classmethod
    def coerce(cls, value: Any) -> SafeInsets:
        if isinstance(value, cls):
            return value
        if value is None:
            return cls()
        values = tuple(int(part) for part in value)
        if len(values) != 4:
            raise ValueError("safe insets must contain left, top, right, bottom")
        return cls(*(max(0, part) for part in values))

    def clamp_to(self, width: int, height: int) -> SafeInsets:
        width = max(1, int(width))
        height = max(1, int(height))
        left = min(max(0, self.left), width - 1)
        right = min(max(0, self.right), width - left - 1)
        top = min(max(0, self.top), height - 1)
        bottom = min(max(0, self.bottom), height - top - 1)
        return SafeInsets(left, top, right, bottom)


def _environment_safe_insets() -> SafeInsets | None:
    raw = os.environ.get("ARCH_ROGUE_SAFE_INSETS", "").strip()
    if not raw:
        return None
    try:
        return SafeInsets.coerce(int(part.strip()) for part in raw.split(","))
    except (TypeError, ValueError):
        return None


def _android_safe_insets(surface_size: tuple[int, int]) -> SafeInsets:
    """Best-effort Android DisplayCutout/system-gesture insets via PyJNIus.

    Pygame CE/SDL currently exposes finger and lifecycle events but no portable
    display-cutout API.  python-for-android includes PyJNIus, so Android builds
    can query WindowInsets without introducing a desktop dependency.  Any bridge
    or vendor failure safely falls back to zero insets.
    """

    override = _environment_safe_insets()
    if override is not None:
        return override.clamp_to(*surface_size)
    if not detect_mobile_runtime() or sys.platform != "android":
        return SafeInsets()
    try:
        from jnius import autoclass  # type: ignore[import-not-found]

        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        decor = activity.getWindow().getDecorView()
        root = decor.getRootWindowInsets()
        if root is None:
            return SafeInsets()
        version = int(autoclass("android.os.Build$VERSION").SDK_INT)
        if version >= 30:
            inset_type = autoclass("android.view.WindowInsets$Type")
            mask = int(inset_type.displayCutout()) | int(inset_type.systemGestures())
            native = root.getInsets(mask)
            values = SafeInsets(
                int(native.left),
                int(native.top),
                int(native.right),
                int(native.bottom),
            )
        elif version >= 28:
            cutout = root.getDisplayCutout()
            if cutout is None:
                return SafeInsets()
            values = SafeInsets(
                int(cutout.getSafeInsetLeft()),
                int(cutout.getSafeInsetTop()),
                int(cutout.getSafeInsetRight()),
                int(cutout.getSafeInsetBottom()),
            )
        else:
            return SafeInsets()
        native_w = max(1, int(decor.getWidth()))
        native_h = max(1, int(decor.getHeight()))
        surface_w, surface_h = surface_size
        scaled = SafeInsets(
            round(values.left * surface_w / native_w),
            round(values.top * surface_h / native_h),
            round(values.right * surface_w / native_w),
            round(values.bottom * surface_h / native_h),
        )
        return scaled.clamp_to(surface_w, surface_h)
    except Exception:
        # JNI availability and Android vendor WindowInsets behavior vary.  The
        # packaged activity also avoids unsafe system regions, so zero is a safe
        # fallback rather than a startup failure.
        return SafeInsets()


@dataclass(frozen=True, slots=True)
class MobileLayout:
    display_rect: pygame.Rect
    safe_rect: pygame.Rect
    left_rail: pygame.Rect
    world_viewport: pygame.Rect
    right_rail: pygame.Rect
    resource_rects: tuple[pygame.Rect, pygame.Rect, pygame.Rect]
    action_rects: tuple[pygame.Rect, ...]
    utility_rects: tuple[tuple[str, pygame.Rect], ...]
    character_rect: pygame.Rect | None
    interact_rect: pygame.Rect
    pause_rect: pygame.Rect


def build_mobile_layout(
    size: tuple[int, int], safe_insets: SafeInsets | Iterable[int] | None = None
) -> MobileLayout:
    """Build the landscape layout shown by the mobile UI reference image."""

    width, height = (max(1, int(size[0])), max(1, int(size[1])))
    insets = SafeInsets.coerce(safe_insets).clamp_to(width, height)
    display = pygame.Rect(0, 0, width, height)
    safe = pygame.Rect(
        insets.left,
        insets.top,
        max(1, width - insets.left - insets.right),
        max(1, height - insets.top - insets.bottom),
    )

    outer = max(6, min(24, safe.height // 45))
    rail_gap = max(5, min(18, safe.height // 64))
    action_gap = max(4, min(12, safe.height // 88))
    available_action_h = max(1, safe.height - outer * 2 - action_gap * 5)
    action_size = max(
        38,
        min(
            available_action_h // 6,
            max(38, int(safe.height * 0.13)),
            max(38, int(safe.width * 0.075)),
        ),
    )
    desired_rail_w = max(action_size + outer * 2, int(safe.width * 0.09))
    maximum_rail_w = max(action_size, (safe.width - max(320, safe.width // 2)) // 2)
    rail_w = max(action_size, min(desired_rail_w, maximum_rail_w))

    rail_h = max(1, safe.height - outer * 2)
    left = pygame.Rect(safe.x + outer, safe.y + outer, rail_w, rail_h)
    right = pygame.Rect(safe.right - outer - rail_w, safe.y + outer, rail_w, rail_h)
    viewport_left = left.right + rail_gap
    viewport_right = right.x - rail_gap
    if viewport_right <= viewport_left:
        midpoint = safe.centerx
        viewport_left = midpoint - 1
        viewport_right = midpoint + 1
    viewport = pygame.Rect(
        viewport_left,
        safe.y + outer,
        max(1, viewport_right - viewport_left),
        rail_h,
    )

    total_action_h = action_size * 6 + action_gap * 5
    action_y = right.centery - total_action_h // 2
    actions = tuple(
        pygame.Rect(
            right.centerx - action_size // 2,
            action_y + index * (action_size + action_gap),
            action_size,
            action_size,
        )
        for index in range(6)
    )

    inner_pad = max(5, min(14, rail_w // 12))
    resource_gap = max(3, min(8, rail_w // 22))
    resource_top = left.y + inner_pad
    resource_h = max(90, int(left.height * 0.43))
    resource_h = min(resource_h, max(1, left.height - inner_pad * 4 - 96))
    resource_w = max(
        8,
        (left.width - inner_pad * 2 - resource_gap * 2) // 3,
    )
    resources = tuple(
        pygame.Rect(
            left.x + inner_pad + index * (resource_w + resource_gap),
            resource_top,
            resource_w,
            resource_h,
        )
        for index in range(3)
    )

    utility_gap = max(4, min(8, rail_w // 18))
    utility_h = max(34, min(54, (left.width - inner_pad * 2 - utility_gap) // 2))
    utility_w = max(34, (left.width - inner_pad * 2 - utility_gap) // 2)
    utility_y = left.bottom - inner_pad - utility_h * 2 - utility_gap
    utility_names = ("inventory", "character", "quest", "help")
    utility_rects: list[tuple[str, pygame.Rect]] = []
    for index, name in enumerate(utility_names):
        col = index % 2
        row = index // 2
        utility_rects.append(
            (
                name,
                pygame.Rect(
                    left.x + inner_pad + col * (utility_w + utility_gap),
                    utility_y + row * (utility_h + utility_gap),
                    utility_w,
                    utility_h,
                ),
            )
        )

    character_top = max(rect.bottom for rect in resources) + inner_pad
    character_bottom = utility_y - inner_pad
    character = None
    if character_bottom - character_top >= 58:
        character = pygame.Rect(
            left.x + inner_pad,
            character_top,
            max(1, left.width - inner_pad * 2),
            character_bottom - character_top,
        )

    auxiliary_size = max(46, min(72, int(safe.height * 0.085)))
    pause = pygame.Rect(0, 0, auxiliary_size, auxiliary_size)
    pause.topright = (viewport.right - outer, viewport.y + outer)
    interact_size = max(54, min(84, int(safe.height * 0.105)))
    interact = pygame.Rect(0, 0, interact_size, interact_size)
    interact.bottomright = (viewport.right - outer, viewport.bottom - outer)

    return MobileLayout(
        display_rect=display,
        safe_rect=safe,
        left_rail=left,
        world_viewport=viewport,
        right_rail=right,
        resource_rects=resources,  # type: ignore[arg-type]
        action_rects=actions,
        utility_rects=tuple(utility_rects),
        character_rect=character,
        interact_rect=interact,
        pause_rect=pause,
    )


@dataclass(frozen=True, slots=True)
class MobileTouchTarget:
    rect: pygame.Rect
    command: str
    label: str
    context: str


@dataclass(slots=True)
class _TouchContact:
    role: str
    start: tuple[int, int]
    position: tuple[int, int]


class MobilePerformanceMonitor:
    """Low-overhead rolling Android frame-phase telemetry."""

    def __init__(
        self,
        *,
        report_interval: float = MOBILE_PERF_REPORT_INTERVAL,
        clock: Callable[[], float] = time.perf_counter,
        emit: Callable[[str], None] | None = None,
    ) -> None:
        self.report_interval = max(0.05, float(report_interval))
        self._clock = clock
        self._emit = emit or self._print_line
        self._report_started: float | None = None
        self._frame_started: float | None = None
        self._frame_seconds = 0.0
        self._frame_count = 0
        self._phase_seconds = {phase: 0.0 for phase in MOBILE_PERF_PHASES}
        self._detail_phase_seconds = {
            phase: 0.0 for phase in MOBILE_PERF_DETAIL_PHASES
        }
        self._last_cache_stats: dict[str, int] = {}
        self.last_report = ""
        self.overlay_text = "PERF collecting frame timings..."
        self.overlay_detail_text = "T -- U -- W -- H -- F -- A -- | L+0 B+0"

    @staticmethod
    def _print_line(line: str) -> None:
        print(line, flush=True)

    def begin_frame(self) -> None:
        now = self._clock()
        if self._report_started is None:
            self._report_started = now
        self._frame_started = now

    def record_phase(self, phase: str, seconds: float) -> None:
        if phase not in self._phase_seconds:
            return
        self._phase_seconds[phase] += max(0.0, float(seconds))

    def record_detail_phase(self, phase: str, seconds: float) -> None:
        """Record nested render work without double-counting total frame time."""

        if phase not in self._detail_phase_seconds:
            return
        self._detail_phase_seconds[phase] += max(0.0, float(seconds))

    @staticmethod
    def _safe_len(value: object) -> int:
        try:
            return len(value)  # type: ignore[arg-type]
        except (TypeError, AttributeError):
            return 0

    @staticmethod
    def _size_label(size: tuple[int, int]) -> str:
        return f"{int(size[0])}x{int(size[1])}"

    def finish_frame(self, game: Any) -> str | None:
        if self._frame_started is None:
            return None
        now = self._clock()
        self._frame_seconds += max(0.0, now - self._frame_started)
        self._frame_started = None
        self._frame_count += 1
        report_started = self._report_started if self._report_started is not None else now
        elapsed = max(0.0, now - report_started)
        if elapsed < self.report_interval:
            return None

        frames = max(1, self._frame_count)
        fps = frames / max(elapsed, 1e-9)
        frame_ms = self._frame_seconds * 1000.0 / frames
        phase_ms = {
            phase: self._phase_seconds[phase] * 1000.0 / frames
            for phase in MOBILE_PERF_PHASES
        }
        detail_ms = {
            phase: self._detail_phase_seconds[phase] * 1000.0 / frames
            for phase in MOBILE_PERF_DETAIL_PHASES
        }
        measured_ms = sum(phase_ms.values())
        other_ms = max(0.0, frame_ms - measured_ms)

        try:
            logical = game.screen.get_size()
            logical_size = (int(logical[0]), int(logical[1]))
        except (AttributeError, IndexError, TypeError, ValueError):
            logical_size = (0, 0)
        try:
            window = pygame.display.get_window_size()
            window_size = (int(window[0]), int(window[1]))
        except (AttributeError, IndexError, TypeError, ValueError, pygame.error):
            window_size = (0, 0)
        try:
            viewport = game.mobile_world_viewport().size
            viewport_size = (int(viewport[0]), int(viewport[1]))
        except (AttributeError, IndexError, TypeError, ValueError):
            viewport_size = logical_size
        try:
            video_driver = pygame.display.get_driver()
        except pygame.error:
            video_driver = "unknown"

        sprites = getattr(game, "sprites", None)
        cache_stats_method = getattr(sprites, "cache_stats", None)
        try:
            raw_cache_stats = cache_stats_method() if callable(cache_stats_method) else {}
            cache_stats = {
                str(key): int(value) for key, value in raw_cache_stats.items()
            }
        except (AttributeError, TypeError, ValueError):
            cache_stats = {}
        source_loads = cache_stats.get("source_loads", 0)
        frame_builds = cache_stats.get("frame_builds", 0)
        source_delta = max(
            0, source_loads - self._last_cache_stats.get("source_loads", 0)
        )
        build_delta = max(
            0, frame_builds - self._last_cache_stats.get("frame_builds", 0)
        )
        self._last_cache_stats = cache_stats

        accelerated = getattr(game, "_mobile_renderer_accelerated", None)
        accelerated_label = (
            "yes" if accelerated is True else "no" if accelerated is False else "unknown"
        )
        renderer_name = str(getattr(game, "_mobile_renderer_name", "unknown"))
        alpha_sdl2 = bool(
            getattr(game, "_mobile_alpha_sdl2", sdl2_alpha_blitter_requested())
        )
        neon = getattr(game, "_mobile_cpu_neon", None)
        neon_label = "yes" if neon is True else "no" if neon is False else "unknown"
        phase_label = ",".join(
            f"{phase}:{phase_ms[phase]:.1f}" for phase in MOBILE_PERF_PHASES
        )
        detail_label = ",".join(
            f"{phase}:{detail_ms[phase]:.1f}" for phase in MOBILE_PERF_DETAIL_PHASES
        )
        enemies = self._safe_len(getattr(game, "enemies", ()))
        lights = self._safe_len(getattr(game, "light_sources", ())) + self._safe_len(
            getattr(game, "lights", ())
        )
        effects = self._safe_len(getattr(game, "impact_effects", ()))
        projectiles = self._safe_len(getattr(game, "projectiles", ()))
        ui_dirty = getattr(game, "_mobile_gpu_ui_dirty_rect", None)
        ui_upload_size = (
            (int(ui_dirty.width), int(ui_dirty.height))
            if isinstance(ui_dirty, pygame.Rect)
            else (0, 0)
        )
        guidance_size = getattr(game, "_mobile_guidance_surface_size", (0, 0))
        if not (
            isinstance(guidance_size, tuple)
            and len(guidance_size) == 2
        ):
            guidance_size = (0, 0)
        ui_region_count = int(getattr(game, "_mobile_gpu_ui_region_count", 0))
        ui_upload_pixels = int(getattr(game, "_mobile_gpu_ui_upload_pixels", 0))
        base_region_count = int(getattr(game, "_mobile_gpu_base_region_count", 0))
        base_upload_pixels = int(getattr(game, "_mobile_gpu_base_upload_pixels", 0))
        lighting_enabled = bool(getattr(game, "_lighting_enabled", False))
        lightweight_method = getattr(game, "mobile_lightweight_lighting_active", None)
        lightweight_lighting = bool(
            callable(lightweight_method) and lightweight_method()
        )
        lighting_mode = (
            "off"
            if not lighting_enabled
            else "local"
            if lightweight_lighting
            else "continuous"
        )
        gpu_error = str(getattr(game, "_mobile_gpu_failure", "")).strip()
        gpu_error = gpu_error.replace(" ", "_") if gpu_error else "none"
        line = (
            f"{MOBILE_PERF_LOG_PREFIX} "
            f"state={getattr(game, 'state', 'unknown')} fps={fps:.2f} "
            f"frame_ms={frame_ms:.1f} phase_ms={phase_label},other:{other_ms:.1f} "
            f"render_ms={detail_label} "
            f"logical={self._size_label(logical_size)} "
            f"window={self._size_label(window_size)} "
            f"viewport={self._size_label(viewport_size)} "
            f"quality={getattr(game, 'mobile_render_quality', 'unknown')} "
            f"renderer={renderer_name} accelerated={accelerated_label} "
            f"alpha_sdl2={int(alpha_sdl2)} neon={neon_label} "
            f"gpu_light={int(bool(getattr(game, '_mobile_gpu_last_present', False)))} "
            f"gpu_ui={self._size_label(ui_upload_size)} "
            f"gpu_upload=base:{base_upload_pixels}px/{base_region_count}r,"
            f"ui:{ui_upload_pixels}px/{ui_region_count}r gpu_error={gpu_error} "
            f"video={video_driver} lighting={int(lighting_enabled)} "
            f"lighting_mode={lighting_mode} "
            f"normals={int(bool(getattr(game, '_lighting_normal_maps', False)))} "
            f"entities=enemies:{enemies},lights:{lights},effects:{effects},projectiles:{projectiles} "
            f"visible=walls:{int(getattr(game, '_mobile_visible_wall_count', 0))},"
            f"enemies:{int(getattr(game, '_mobile_visible_enemy_count', 0))} "
            f"guidance_px={self._size_label(guidance_size)} "
            f"cache=decoded:{cache_stats.get('decoded_sources', 0)},"
            f"frames:{cache_stats.get('resolved_frames', 0)},"
            f"loads+:{source_delta},builds+:{build_delta} "
            f"floor_cache=rebuilds:{int(getattr(game, '_mobile_floor_cache_rebuilds', 0))},"
            f"patches:{int(getattr(game, '_mobile_floor_cache_patches', 0))}"
        )
        self.last_report = line
        visible_world_ms = max(phase_ms["menu"], phase_ms["world"])
        self.overlay_text = (
            f"PERF {fps:.1f}fps {frame_ms:.0f}ms | "
            f"{self._size_label(logical_size)} {renderer_name} "
            f"A2:{int(alpha_sdl2)} N:{neon_label}"
        )
        self.overlay_detail_text = (
            f"T {phase_ms['tick']:.0f} U {phase_ms['update']:.0f} "
            f"W {visible_world_ms:.0f} H {phase_ms['hud']:.0f} "
            f"F {phase_ms['flip']:.0f} A {phase_ms['audio']:.0f} | "
            f"L+{source_delta} B+{build_delta}"
        )
        self._emit(line)

        self._report_started = now
        self._frame_seconds = 0.0
        self._frame_count = 0
        for phase in self._phase_seconds:
            self._phase_seconds[phase] = 0.0
        for phase in self._detail_phase_seconds:
            self._detail_phase_seconds[phase] = 0.0
        return line


class MobileMixin:
    """Game mixin implementing mobile geometry, touch, and app lifecycle."""

    def init_mobile_runtime(
        self, safe_insets: SafeInsets | Iterable[int] | None = None
    ) -> None:
        self._mobile_safe_insets_override = (
            SafeInsets.coerce(safe_insets) if safe_insets is not None else None
        )
        self.mobile_safe_insets = SafeInsets()
        self._mobile_layout_cache: tuple[
            tuple[int, int], SafeInsets, MobileLayout
        ] | None = None
        self._mobile_touch_targets: list[MobileTouchTarget] = []
        self._mobile_touch_contacts: dict[tuple[int, int], _TouchContact] = {}
        self._mobile_world_finger: tuple[int, int] | None = None
        self._mobile_touch_world_point: tuple[int, int] | None = None
        self._mobile_touch_world_active = False
        self.mobile_suspended = False
        self.mobile_audio_focus_paused = False
        self._mobile_perf_overlay_cache: tuple[
            tuple[str, str], int, pygame.Surface
        ] | None = None
        self._mobile_gpu_renderer_generation = int(
            getattr(self, "_mobile_gpu_renderer_generation", 0)
        )
        self._mobile_gpu_frame_sequence = 0
        self._mobile_gpu_frame_active = False
        self._mobile_gpu_pending_light: tuple[
            int, int, pygame.Surface, pygame.Rect
        ] | None = None
        self._mobile_gpu_pending_flash: tuple[tuple[int, int, int], int] | None = None
        self._mobile_gpu_ui_surface: pygame.Surface | None = None
        self._mobile_gpu_ui_viewport: pygame.Rect | None = None
        self._mobile_gpu_ui_dirty_rect: pygame.Rect | None = None
        self._mobile_gpu_ui_regions: list[
            tuple[str, pygame.Rect, object]
        ] = []
        self._mobile_gpu_ui_previous_rects: list[pygame.Rect] = []
        self._mobile_gpu_base_regions: list[tuple[str, pygame.Rect]] = []
        self._mobile_gpu_ui_region_textures: dict[str, tuple[object, Any]] = {}
        self._mobile_gpu_ui_region_revisions: dict[str, object] = {}
        self._mobile_gpu_base_region_textures: dict[str, tuple[object, Any]] = {}
        self._mobile_gpu_shell_revision: object | None = None
        self._mobile_gpu_ui_region_count = 0
        self._mobile_gpu_ui_upload_pixels = 0
        self._mobile_gpu_base_region_count = 0
        self._mobile_gpu_base_upload_pixels = 0
        self._mobile_gpu_flash_surface: pygame.Surface | None = None
        self._mobile_gpu_failure = ""
        self._mobile_gpu_last_present = False
        self._mobile_performance_monitor = (
            MobilePerformanceMonitor()
            if getattr(self, "mobile_mode", False)
            and mobile_performance_telemetry_enabled()
            else None
        )
        if getattr(self, "mobile_mode", False):
            self.refresh_mobile_safe_insets()

    def configure_mobile_gpu_renderer(self, window: object, renderer: object) -> None:
        """Attach borrowed wrappers for pygame.display's accelerated renderer."""

        self.release_mobile_gpu_renderer()
        self._mobile_gpu_renderer_generation = int(
            getattr(self, "_mobile_gpu_renderer_generation", 0)
        ) + 1
        self._mobile_gpu_window = window
        self._mobile_gpu_renderer = renderer
        self._mobile_gpu_failure = ""
        self._mobile_gpu_last_present = False

    def release_mobile_gpu_textures(self) -> None:
        """Destroy custom textures while their display-owned renderer is alive."""

        self._mobile_gpu_frame_active = False
        self._mobile_gpu_pending_light = None
        self._mobile_gpu_pending_flash = None
        self._mobile_gpu_last_present = False
        self._mobile_gpu_shell_revision = None
        self._mobile_gpu_ui_region_textures = {}
        self._mobile_gpu_ui_region_revisions = {}
        self._mobile_gpu_base_region_textures = {}
        self._mobile_gpu_ui_regions = []
        self._mobile_gpu_ui_previous_rects = []
        self._mobile_gpu_base_regions = []
        self._mobile_gpu_ui_region_count = 0
        self._mobile_gpu_ui_upload_pixels = 0
        self._mobile_gpu_base_region_count = 0
        self._mobile_gpu_base_upload_pixels = 0
        self._mobile_render_generation = int(
            getattr(self, "_mobile_render_generation", 0)
        ) + 1
        for name in (
            "_mobile_gpu_flash_texture",
            "_mobile_gpu_ui_texture",
            "_mobile_gpu_light_texture",
            "_mobile_gpu_base_texture",
            "_mobile_gpu_shell_texture",
        ):
            if hasattr(self, name):
                setattr(self, name, None)
        self._mobile_gpu_flash_texture_key = None
        self._mobile_gpu_ui_texture_key = None
        self._mobile_gpu_light_texture_key = None
        self._mobile_gpu_base_texture_key = None
        self._mobile_gpu_shell_texture_key = None

    def release_mobile_gpu_renderer(self) -> None:
        """Release textures first, then borrowed renderer/window wrappers."""

        self.release_mobile_gpu_textures()
        self._mobile_gpu_renderer = None
        self._mobile_gpu_window = None

    def refresh_mobile_gpu_renderer(self) -> bool:
        """Re-borrow pygame.display's renderer after an SDL context reset."""

        if not getattr(self, "mobile_mode", False):
            return False
        try:
            from pygame._sdl2.video import Renderer, Window

            window = Window.from_display_module()
            renderer = Renderer.from_window(window)
        except (AttributeError, ImportError, TypeError, ValueError, pygame.error):
            self.release_mobile_gpu_renderer()
            return False
        self.configure_mobile_gpu_renderer(window, renderer)
        return True

    def _mobile_gpu_frame_eligible(self) -> bool:
        continuous_lighting = getattr(self, "continuous_lighting_active", None)
        return bool(
            getattr(self, "mobile_mode", False)
            and not getattr(self, "mobile_suspended", False)
            and getattr(self, "_mobile_renderer_accelerated", False)
            and getattr(self, "_mobile_gpu_renderer", None) is not None
            and not getattr(self, "_mobile_gpu_failure", "")
            and self.mobile_input_context() == "gameplay"
            and callable(continuous_lighting)
            and continuous_lighting()
        )

    @staticmethod
    def _mobile_gpu_upload_layout_supported(surface: pygame.Surface) -> bool:
        return bool(
            sys.byteorder == "little"
            and surface.get_bytesize() == 4
            and surface.get_pitch() == surface.get_width() * 4
            and tuple(surface.get_masks()) == _ANDROID_XRGB_MASKS
        )

    def begin_mobile_gpu_frame(self) -> bool:
        """Latch the direct GLES lighting path before any frame content is drawn."""

        self._mobile_gpu_last_present = False
        self._mobile_gpu_pending_light = None
        self._mobile_gpu_pending_flash = None
        self._mobile_gpu_frame_active = False
        self._mobile_gpu_ui_region_count = 0
        self._mobile_gpu_ui_upload_pixels = 0
        self._mobile_gpu_base_region_count = 0
        self._mobile_gpu_base_upload_pixels = 0
        self._mobile_gpu_ui_regions = []
        self._mobile_gpu_base_regions = []
        if not self._mobile_gpu_frame_eligible():
            return False
        root = self.screen
        if not self._mobile_gpu_upload_layout_supported(root):
            self._mobile_gpu_failure = (
                f"unsupported-root-format:{root.get_masks()}:{root.get_pitch()}"
            )
            return False
        renderer: Any = getattr(self, "_mobile_gpu_renderer", None)
        if renderer is None:
            return False
        try:
            logical_size = tuple(renderer.logical_size)
        except (AttributeError, TypeError, ValueError, pygame.error):
            self._mobile_gpu_failure = "renderer-logical-size-unavailable"
            return False
        if logical_size != root.get_size():
            self._mobile_gpu_failure = (
                f"renderer-logical-size:{logical_size}!={root.get_size()}"
            )
            return False
        viewport = self.mobile_world_viewport().clip(root.get_rect())
        if viewport.width <= 0 or viewport.height <= 0:
            return False
        ui_surface = self._mobile_gpu_ui_surface
        if ui_surface is None or ui_surface.get_size() != viewport.size:
            ui_surface = pygame.Surface(viewport.size, pygame.SRCALPHA)
            try:
                ui_surface = ui_surface.convert_alpha()
            except pygame.error:
                pass
            ui_surface.fill((0, 0, 0, 0))
            self._mobile_gpu_ui_surface = ui_surface
            self._mobile_gpu_ui_dirty_rect = None
            self._mobile_gpu_ui_previous_rects = []
        else:
            previous = getattr(self, "_mobile_gpu_ui_previous_rects", ())
            if previous:
                for rect in previous:
                    ui_surface.fill((0, 0, 0, 0), rect)
            else:
                dirty = self._mobile_gpu_ui_dirty_rect
                if dirty is not None and dirty.width > 0 and dirty.height > 0:
                    ui_surface.fill((0, 0, 0, 0), dirty)
            self._mobile_gpu_ui_dirty_rect = None
        self._mobile_gpu_ui_viewport = viewport
        self._mobile_gpu_frame_sequence += 1
        self._mobile_gpu_frame_active = True
        return True

    def mobile_gpu_frame_active(self) -> bool:
        return bool(getattr(self, "_mobile_gpu_frame_active", False))

    def mobile_gpu_post_light_surface(
        self, viewport: pygame.Rect
    ) -> pygame.Surface | None:
        if not getattr(self, "_mobile_gpu_frame_active", False):
            return None
        target = getattr(self, "_mobile_gpu_ui_viewport", None)
        if target is None or target != viewport:
            return None
        return self._mobile_gpu_ui_surface

    def mark_mobile_gpu_ui_region(
        self,
        key: str,
        rect: pygame.Rect,
        revision: object,
    ) -> bool:
        """Register one viewport-local post-light panel for indexed upload."""

        if not getattr(self, "_mobile_gpu_frame_active", False):
            return False
        overlay = getattr(self, "_mobile_gpu_ui_surface", None)
        if overlay is None:
            return False
        clipped = pygame.Rect(rect).clip(overlay.get_rect())
        if clipped.width <= 0 or clipped.height <= 0:
            return False
        self._mobile_gpu_ui_regions.append((str(key), clipped, revision))
        return True

    def mark_mobile_gpu_base_region(self, key: str, rect: pygame.Rect) -> bool:
        """Register a root-space control rectangle that changes over the GPU shell."""

        if not getattr(self, "_mobile_gpu_frame_active", False):
            return False
        clipped = pygame.Rect(rect).clip(self.screen.get_rect())
        if clipped.width <= 0 or clipped.height <= 0:
            return False
        self._mobile_gpu_base_regions.append((str(key), clipped))
        return True

    def blit_mobile_post_light(
        self, surface: pygame.Surface, destination: tuple[int, int]
    ) -> bool:
        """Blit root-coordinate diagnostics above the GPU lighting pass."""

        if not getattr(self, "_mobile_gpu_frame_active", False):
            return False
        viewport = getattr(self, "_mobile_gpu_ui_viewport", None)
        overlay = getattr(self, "_mobile_gpu_ui_surface", None)
        if viewport is None or overlay is None:
            return False
        rect = surface.get_rect(topleft=destination)
        clipped = rect.clip(viewport)
        if clipped.width <= 0 or clipped.height <= 0:
            return False
        local_rect = clipped.move(-viewport.x, -viewport.y)
        source_area = clipped.move(-rect.x, -rect.y)
        overlay.blit(surface, local_rect, source_area)
        self.mark_mobile_gpu_ui_region(
            "diagnostics",
            local_rect,
            (id(surface), surface.get_size()),
        )
        return True

    def queue_mobile_gpu_lighting(self, surface: pygame.Surface) -> bool:
        if not getattr(self, "_mobile_gpu_frame_active", False):
            return False
        viewport = getattr(self, "_mobile_gpu_ui_viewport", None)
        if viewport is None:
            return False
        self._mobile_gpu_pending_light = (
            self._mobile_gpu_frame_sequence,
            self._mobile_gpu_renderer_generation,
            surface,
            viewport.copy(),
        )
        return True

    def queue_mobile_gpu_flash(
        self, color: tuple[int, int, int], alpha: int
    ) -> bool:
        """Queue a uniform post-light flash without touching native CPU pixels."""

        if not getattr(self, "_mobile_gpu_frame_active", False):
            return False
        red, green, blue = color
        self._mobile_gpu_pending_flash = (
            (int(red), int(green), int(blue)),
            max(0, min(255, int(alpha))),
        )
        return True

    @staticmethod
    def _create_mobile_gpu_texture(
        renderer: Any,
        size: tuple[int, int],
    ) -> Any:
        from pygame._sdl2.video import Texture

        return Texture(renderer, size, streaming=True, scale_quality=0)

    def _mobile_gpu_texture(
        self,
        kind: str,
        size: tuple[int, int],
        blend_mode: int,
    ) -> Any:
        key = (self._mobile_gpu_renderer_generation, size)
        key_name = f"_mobile_gpu_{kind}_texture_key"
        texture_name = f"_mobile_gpu_{kind}_texture"
        texture = getattr(self, texture_name, None)
        if texture is None or getattr(self, key_name, None) != key:
            texture = self._create_mobile_gpu_texture(self._mobile_gpu_renderer, size)
            texture.blend_mode = blend_mode
            setattr(self, texture_name, texture)
            setattr(self, key_name, key)
        return texture

    def _mobile_gpu_region_texture(
        self,
        cache_name: str,
        region_key: str,
        size: tuple[int, int],
        blend_mode: int,
    ) -> Any:
        cache: dict[str, tuple[object, Any]] = getattr(self, cache_name, {})
        texture_key = (self._mobile_gpu_renderer_generation, size)
        cached = cache.get(region_key)
        if cached is None or cached[0] != texture_key:
            texture = self._create_mobile_gpu_texture(self._mobile_gpu_renderer, size)
            texture.blend_mode = blend_mode
            cache[region_key] = (texture_key, texture)
            if cache_name == "_mobile_gpu_ui_region_textures":
                self._mobile_gpu_ui_region_revisions.pop(region_key, None)
        else:
            texture = cached[1]
        setattr(self, cache_name, cache)
        return texture

    @staticmethod
    def _mobile_gpu_regions_union(
        regions: Iterable[pygame.Rect],
    ) -> pygame.Rect | None:
        union: pygame.Rect | None = None
        for rect in regions:
            if rect.width <= 0 or rect.height <= 0:
                continue
            union = rect.copy() if union is None else union.union(rect)
        return union

    def _mobile_gpu_coalesced_ui_regions(
        self,
    ) -> list[tuple[str, pygame.Rect, object]]:
        """Merge overlapping final-composite regions to avoid double blending."""

        deduplicated: dict[str, tuple[pygame.Rect, object]] = {}
        for key, rect, revision in self._mobile_gpu_ui_regions:
            deduplicated[key] = (rect.copy(), revision)
        groups: list[
            tuple[pygame.Rect, list[tuple[str, pygame.Rect, object]]]
        ] = []
        for key, (rect, revision) in deduplicated.items():
            merged_rect = rect.copy()
            components = [(key, rect.copy(), revision)]
            index = 0
            while index < len(groups):
                group_rect, group_components = groups[index]
                if not merged_rect.colliderect(group_rect):
                    index += 1
                    continue
                merged_rect = merged_rect.union(group_rect)
                components.extend(group_components)
                groups.pop(index)
                index = 0
            groups.append((merged_rect, components))

        result: list[tuple[str, pygame.Rect, object]] = []
        for rect, components in groups:
            ordered = sorted(components, key=lambda component: component[0])
            key = "|".join(component[0] for component in ordered)
            revision = tuple(
                (
                    component_key,
                    (
                        component_rect.x - rect.x,
                        component_rect.y - rect.y,
                        component_rect.width,
                        component_rect.height,
                    ),
                    component_revision,
                )
                for component_key, component_rect, component_revision in ordered
            )
            result.append((key, rect, revision))
        return result

    def _composite_mobile_gpu_ui_fallback(self) -> None:
        viewport = getattr(self, "_mobile_gpu_ui_viewport", None)
        overlay = getattr(self, "_mobile_gpu_ui_surface", None)
        pending_flash = getattr(self, "_mobile_gpu_pending_flash", None)
        if viewport is not None and overlay is not None:
            coalesced = self._mobile_gpu_coalesced_ui_regions()
            regions = [rect for _key, rect, _revision in coalesced]
            if not regions:
                dirty = overlay.get_bounding_rect(min_alpha=1)
                if dirty.width > 0 and dirty.height > 0:
                    regions = [dirty]
            self._mobile_gpu_ui_previous_rects = [rect.copy() for rect in regions]
            self._mobile_gpu_ui_dirty_rect = self._mobile_gpu_regions_union(regions)
            for rect in regions:
                self.screen.blit(
                    overlay.subsurface(rect),
                    rect.move(viewport.x, viewport.y),
                )
        if pending_flash is not None:
            color, alpha = pending_flash
            width, height = self.screen.get_size()
            flash = getattr(self, "_screen_flash_surface", None)
            if flash is None or flash.get_size() != (width, height):
                flash = pygame.Surface((width, height), pygame.SRCALPHA)
                self._screen_flash_surface = flash
            flash.fill((*color, alpha))
            self.screen.blit(flash, (0, 0))
        self._mobile_gpu_frame_active = False
        self._mobile_gpu_pending_light = None
        self._mobile_gpu_pending_flash = None

    def present_mobile_gpu_frame(self) -> bool:
        """Composite lighting while uploading only regions that actually change."""

        if not getattr(self, "_mobile_gpu_frame_active", False):
            return False
        pending = getattr(self, "_mobile_gpu_pending_light", None)
        if pending is None:
            self._composite_mobile_gpu_ui_fallback()
            return False
        sequence, generation, light_surface, viewport = pending
        if (
            sequence != self._mobile_gpu_frame_sequence
            or generation != self._mobile_gpu_renderer_generation
        ):
            self._composite_mobile_gpu_ui_fallback()
            return False

        root = self.screen
        ui_surface = self._mobile_gpu_ui_surface
        renderer: Any = getattr(self, "_mobile_gpu_renderer", None)
        if ui_surface is None or renderer is None:
            self._composite_mobile_gpu_ui_fallback()
            return False
        monitor = getattr(self, "_mobile_performance_monitor", None)
        root_buffer = None
        root_alias = None
        try:
            light_texture = self._mobile_gpu_texture(
                "light", light_surface.get_size(), SDL_BLENDMODE_MOD
            )
            shell_texture = self._mobile_gpu_texture(
                "shell", root.get_size(), SDL_BLENDMODE_NONE
            )
            theme = getattr(self, "theme", None)
            layout = self.mobile_layout()
            shell_revision = (
                root.get_size(),
                (viewport.x, viewport.y, viewport.width, viewport.height),
                (layout.left_rail.x, layout.left_rail.y, layout.left_rail.width, layout.left_rail.height),
                (layout.right_rail.x, layout.right_rail.y, layout.right_rail.width, layout.right_rail.height),
                getattr(self, "state", ""),
                getattr(theme, "name", ""),
                tuple(getattr(theme, "accent", ())),
                int(getattr(self, "ui_scale", 1)),
                bool(getattr(self, "legacy_graphics", False)),
            )
            refresh_shell = self._mobile_gpu_shell_revision != shell_revision

            # Preserve registration order but let a later draw replace a region
            # with the same semantic key.
            base_map: dict[str, pygame.Rect] = {}
            for key, rect in self._mobile_gpu_base_regions:
                clipped = rect.clip(root.get_rect())
                if clipped.width > 0 and clipped.height > 0:
                    base_map[key] = clipped
            base_draws: list[tuple[Any, pygame.Rect]] = []
            base_texture = None
            if not refresh_shell:
                base_texture = self._mobile_gpu_texture(
                    "base", viewport.size, SDL_BLENDMODE_NONE
                )
                for key, rect in base_map.items():
                    texture = self._mobile_gpu_region_texture(
                        "_mobile_gpu_base_region_textures",
                        key,
                        rect.size,
                        SDL_BLENDMODE_NONE,
                    )
                    base_draws.append((texture, rect.copy()))
            self._mobile_gpu_base_region_count = len(base_draws)

            ui_map: dict[str, tuple[pygame.Rect, object]] = {}
            for key, rect, revision in self._mobile_gpu_coalesced_ui_regions():
                clipped = rect.clip(ui_surface.get_rect())
                if clipped.width > 0 and clipped.height > 0:
                    ui_map[key] = (clipped, revision)
            if not ui_map:
                fallback_rect = ui_surface.get_bounding_rect(min_alpha=1)
                if fallback_rect.width > 0 and fallback_rect.height > 0:
                    ui_map["legacy"] = (fallback_rect, sequence)
            ui_rects = [rect for rect, _revision in ui_map.values()]
            self._mobile_gpu_ui_previous_rects = [rect.copy() for rect in ui_rects]
            self._mobile_gpu_ui_dirty_rect = self._mobile_gpu_regions_union(ui_rects)
            self._mobile_gpu_ui_region_count = len(ui_rects)
            ui_draws: list[
                tuple[Any, pygame.Rect, pygame.Surface | None, str, object]
            ] = []
            for key, (rect, revision) in ui_map.items():
                texture = self._mobile_gpu_region_texture(
                    "_mobile_gpu_ui_region_textures",
                    key,
                    rect.size,
                    SDL_BLENDMODE_BLEND,
                )
                upload = (
                    ui_surface.subsurface(rect)
                    if self._mobile_gpu_ui_region_revisions.get(key) != revision
                    else None
                )
                ui_draws.append(
                    (
                        texture,
                        rect.move(viewport.x, viewport.y),
                        upload,
                        key,
                        revision,
                    )
                )
            self._mobile_gpu_ui_texture = ui_draws[0][0] if ui_draws else None

            pending_flash = getattr(self, "_mobile_gpu_pending_flash", None)
            flash_texture = None
            flash_surface = self._mobile_gpu_flash_surface
            if pending_flash is not None:
                flash_texture = self._mobile_gpu_texture(
                    "flash", (1, 1), SDL_BLENDMODE_BLEND
                )
                if flash_surface is None:
                    flash_surface = pygame.Surface((1, 1), pygame.SRCALPHA)
                    self._mobile_gpu_flash_surface = flash_surface

            started = time.perf_counter()
            root_buffer = root.get_buffer()
            root_alias = pygame.image.frombuffer(root_buffer, root.get_size(), "BGRA")
            if tuple(root_alias.get_masks()) != _ANDROID_ARGB_MASKS:
                raise ValueError(f"unexpected upload masks {root_alias.get_masks()}")
            if refresh_shell:
                shell_texture.update(root_alias)
                self._mobile_gpu_shell_revision = shell_revision
                base_pixels = root.get_width() * root.get_height()
            else:
                assert base_texture is not None
                base_texture.update(root_alias.subsurface(viewport))
                base_pixels = viewport.width * viewport.height
                for texture, rect in base_draws:
                    texture.update(root_alias.subsurface(rect))
                    base_pixels += rect.width * rect.height
            self._mobile_gpu_base_upload_pixels = base_pixels
            if monitor is not None:
                monitor.record_detail_phase(
                    "base_upload", time.perf_counter() - started
                )

            # Release the BufferProxy lock before touching independent surfaces.
            root_alias = None
            root_buffer = None

            started = time.perf_counter()
            light_texture.update(light_surface)
            if monitor is not None:
                monitor.record_detail_phase(
                    "light_upload", time.perf_counter() - started
                )

            started = time.perf_counter()
            ui_pixels = 0
            for texture, _destination, upload, key, revision in ui_draws:
                if upload is None:
                    continue
                texture.update(upload)
                self._mobile_gpu_ui_region_revisions[key] = revision
                ui_pixels += upload.get_width() * upload.get_height()
            self._mobile_gpu_ui_upload_pixels = ui_pixels
            if (
                flash_texture is not None
                and flash_surface is not None
                and pending_flash is not None
            ):
                color, alpha = pending_flash
                flash_surface.fill((*color, alpha))
                flash_texture.update(flash_surface)
            if monitor is not None:
                monitor.record_detail_phase("ui_upload", time.perf_counter() - started)

            started = time.perf_counter()
            renderer.draw_color = (0, 0, 0, 255)
            renderer.clear()
            renderer.blit(shell_texture, root.get_rect())
            if not refresh_shell and base_texture is not None:
                renderer.blit(base_texture, viewport)
            renderer.blit(light_texture, viewport)
            if not refresh_shell:
                for texture, destination in base_draws:
                    renderer.blit(texture, destination)
            for texture, destination, _upload, _key, _revision in ui_draws:
                renderer.blit(texture, destination)
            if flash_texture is not None:
                renderer.blit(flash_texture, root.get_rect())
            renderer.present()
            if monitor is not None:
                monitor.record_detail_phase(
                    "gpu_present", time.perf_counter() - started
                )
        except (
            AttributeError,
            BufferError,
            ImportError,
            RuntimeError,
            TypeError,
            ValueError,
            pygame.error,
        ) as exc:
            root_alias = None
            root_buffer = None
            self._mobile_gpu_failure = f"{type(exc).__name__}:{exc}"
            self._composite_mobile_gpu_ui_fallback()
            self.release_mobile_gpu_textures()
            return False

        self._mobile_gpu_frame_active = False
        self._mobile_gpu_pending_light = None
        self._mobile_gpu_pending_flash = None
        self._mobile_gpu_last_present = True
        return True

    def _mobile_display_surface(self) -> pygame.Surface:
        return getattr(self, "_mobile_root_screen", self.screen)

    def refresh_mobile_safe_insets(self) -> SafeInsets:
        if not getattr(self, "mobile_mode", False):
            self.mobile_safe_insets = SafeInsets()
            return self.mobile_safe_insets
        size = self._mobile_display_surface().get_size()
        override = getattr(self, "_mobile_safe_insets_override", None)
        insets = (
            SafeInsets.coerce(override).clamp_to(*size)
            if override is not None
            else _android_safe_insets(size)
        )
        if insets != getattr(self, "mobile_safe_insets", SafeInsets()):
            self.mobile_safe_insets = insets
            self._mobile_layout_cache = None
        return insets

    def mobile_layout(self) -> MobileLayout:
        size = self._mobile_display_surface().get_size()
        insets = getattr(self, "mobile_safe_insets", SafeInsets())
        cache = getattr(self, "_mobile_layout_cache", None)
        if cache is None or cache[0] != size or cache[1] != insets:
            layout = build_mobile_layout(size, insets)
            cache = (size, insets, layout)
            self._mobile_layout_cache = cache
        return cache[2]

    def mobile_safe_rect(self) -> pygame.Rect:
        if not getattr(self, "mobile_mode", False):
            return self._mobile_display_surface().get_rect()
        return self.mobile_layout().safe_rect.copy()

    def mobile_world_viewport(self) -> pygame.Rect:
        if not getattr(self, "mobile_mode", False):
            return self._mobile_display_surface().get_rect()
        return self.mobile_layout().world_viewport.copy()

    def screen_point_in_world_viewport(self, point: tuple[int, int]) -> bool:
        return self.mobile_world_viewport().collidepoint(point)

    def mobile_input_context(self) -> str:
        if self.state == "confirm_exit":
            return "confirm_exit"
        if self.state in ("dead", "victory"):
            return "state_overlay"
        if self.state != "playing":
            return self.state
        if getattr(self, "show_help", False):
            return "help"
        if getattr(self, "active_cutscene", None) is not None:
            return "cutscene"
        if getattr(self, "story_intro_pending", False):
            return "story_intro"
        if getattr(self, "character_menu_open", False):
            return "character"
        if getattr(self, "inventory_open", False):
            return "inventory"
        if getattr(self, "shop_open", False):
            return "shop"
        return "gameplay"

    def mobile_world_input_enabled(self) -> bool:
        return (
            getattr(self, "mobile_mode", False)
            and not getattr(self, "mobile_suspended", False)
            and self.mobile_input_context() == "gameplay"
        )

    def active_mobile_world_touch(self) -> tuple[int, int] | None:
        if self.mobile_world_input_enabled() and self._mobile_touch_world_active:
            return self._mobile_touch_world_point
        return None

    def cancel_mobile_touches(self) -> None:
        self._mobile_touch_contacts.clear()
        self._mobile_world_finger = None
        self._mobile_touch_world_active = False

    def register_mobile_touch_target(
        self,
        rect: pygame.Rect,
        command: str,
        label: str,
        *,
        context: str | None = None,
    ) -> None:
        if not getattr(self, "mobile_mode", False) or rect.width <= 0 or rect.height <= 0:
            return
        self._mobile_touch_targets.append(
            MobileTouchTarget(
                rect.copy(), command, label, context or self.mobile_input_context()
            )
        )

    def reset_mobile_touch_targets(self) -> None:
        self._mobile_touch_targets = []

    @staticmethod
    def mobile_finger_position(
        event: pygame.event.Event, size: tuple[int, int]
    ) -> tuple[int, int]:
        width, height = size
        if hasattr(event, "x") and hasattr(event, "y"):
            x = round(max(0.0, min(1.0, float(event.x))) * max(0, width - 1))
            y = round(max(0.0, min(1.0, float(event.y))) * max(0, height - 1))
            return x, y
        pos = getattr(event, "pos", (0, 0))
        return (
            max(0, min(width - 1, int(pos[0]))),
            max(0, min(height - 1, int(pos[1]))),
        )

    @staticmethod
    def _mobile_finger_key(event: pygame.event.Event) -> tuple[int, int]:
        return int(getattr(event, "touch_id", 0)), int(getattr(event, "finger_id", 0))

    def _mobile_target_at(self, point: tuple[int, int]) -> MobileTouchTarget | None:
        context = self.mobile_input_context()
        for target in reversed(self._mobile_touch_targets):
            if target.context == context and target.rect.collidepoint(point):
                return target
        return None

    def _global_story_panel_rect(self) -> pygame.Rect | None:
        rect = getattr(self, "_story_panel_rect", None)
        if not isinstance(rect, pygame.Rect):
            return None
        if getattr(self, "mobile_mode", False) and self.mobile_input_context() == "gameplay":
            return rect.move(self.mobile_world_viewport().topleft)
        return rect.copy()

    def handle_mobile_finger_event(self, event: pygame.event.Event) -> bool:
        if not getattr(self, "mobile_mode", False):
            return False
        finger_types = {
            getattr(pygame, "FINGERDOWN", -10),
            getattr(pygame, "FINGERMOTION", -11),
            getattr(pygame, "FINGERUP", -12),
        }
        if event.type not in finger_types:
            return False
        root = self._mobile_display_surface()
        point = self.mobile_finger_position(event, root.get_size())
        key = self._mobile_finger_key(event)

        if event.type == getattr(pygame, "FINGERDOWN", -10):
            target = self._mobile_target_at(point)
            if target is not None:
                previous_context = self.mobile_input_context()
                self._mobile_touch_contacts[key] = _TouchContact(
                    f"target:{target.command}", point, point
                )
                self._dispatch_command(target.command)
                if self.mobile_input_context() != previous_context:
                    self.cancel_mobile_touches()
                return True

            story_rect = self._global_story_panel_rect()
            if (
                self.mobile_input_context() == "gameplay"
                and story_rect is not None
                and story_rect.collidepoint(point)
            ):
                self._mobile_touch_contacts[key] = _TouchContact(
                    "quest_scroll", point, point
                )
                return True

            if self.mobile_world_input_enabled() and self.screen_point_in_world_viewport(point):
                role = "world" if self._mobile_world_finger is None else "world_secondary"
                self._mobile_touch_contacts[key] = _TouchContact(role, point, point)
                if role == "world":
                    self._mobile_world_finger = key
                    self._mobile_touch_world_point = point
                    self._mobile_touch_world_active = True
                    self.aim_input_mode = "touch"
                    if hasattr(self, "player"):
                        self.face_player_toward_screen_point(*point)
                return True

            self._mobile_touch_contacts[key] = _TouchContact("tap", point, point)
            return True

        contact = self._mobile_touch_contacts.get(key)
        if contact is None:
            return True
        contact.position = point
        if event.type == getattr(pygame, "FINGERMOTION", -11):
            if contact.role == "world" and key == self._mobile_world_finger:
                self._mobile_touch_world_point = point
                self.aim_input_mode = "touch"
                if hasattr(self, "player"):
                    self.face_player_toward_screen_point(*point)
            return True

        self._mobile_touch_contacts.pop(key, None)
        if contact.role == "world" and key == self._mobile_world_finger:
            self._mobile_touch_world_point = point
            self._mobile_world_finger = None
            self._mobile_touch_world_active = False
            return True
        if contact.role in ("tap", "quest_scroll"):
            dx = point[0] - contact.start[0]
            dy = point[1] - contact.start[1]
            threshold = max(34, root.get_height() // 14)
            if abs(dy) >= threshold and abs(dy) > abs(dx):
                self._handle_mobile_swipe(contact.role, dy)
            elif contact.role == "tap":
                self.handle_mobile_tap(point)
        return True

    def _handle_mobile_swipe(self, role: str, dy: int) -> None:
        down = dy < 0
        if role == "quest_scroll":
            page = max(1, getattr(self, "_story_panel_visible_lines", 3) - 1)
            self.scroll_story_panel(page if down else -page)
            return
        context = self.mobile_input_context()
        if context == "cutscene":
            self._dispatch_command(Command.PAGE_DOWN if down else Command.PAGE_UP)
        elif context == "inventory":
            self._dispatch_command(Command.PAGE_DOWN if down else Command.PAGE_UP)
        else:
            self._dispatch_command(Command.DOWN if down else Command.UP)

    def _safe_local_point(self, point: tuple[int, int]) -> tuple[int, int]:
        safe = self.mobile_safe_rect()
        return point[0] - safe.x, point[1] - safe.y

    @staticmethod
    def _rect_index(rects: Any, point: tuple[int, int]) -> int | None:
        if not isinstance(rects, (tuple, list)):
            return None
        for index, rect in enumerate(rects):
            if isinstance(rect, pygame.Rect) and rect.collidepoint(point):
                return index
        return None

    def handle_mobile_tap(self, point: tuple[int, int]) -> bool:
        """Activate direct row/cell taps not covered by persistent nav buttons."""

        local = self._safe_local_point(point)
        context = self.mobile_input_context()
        if context == "title":
            index = self._rect_index(getattr(self, "_title_row_rects", ()), local)
            if index is not None and self._title_row_enabled(index):
                self.title_selection = index
                self._activate_title_selection()
                return True
        elif context == "options":
            index = self._rect_index(getattr(self, "_menu_row_rects", ()), local)
            if index is not None:
                start = int(getattr(self, "_options_visible_range", (0, 0))[0])
                self.options_cursor = min(self.OPTIONS_ROW_COUNT - 1, start + index)
                self._activate_options_row(self.options_cursor, True)
                return True
        elif context == "controls":
            index = self._rect_index(getattr(self, "_menu_row_rects", ()), local)
            if index is not None:
                self.controls_cursor = index
                self._dispatch_command(Command.CONFIRM)
                return True
        elif context == "archetype_select":
            index = self._rect_index(getattr(self, "_menu_row_rects", ()), local)
            if index is not None and index < len(ARCHETYPES):
                selected = ARCHETYPES[index]
                if self.selected_archetype == selected:
                    self.restart(selected)
                else:
                    self.selected_archetype = selected
                return True
        elif context == "confirm_exit":
            index = self._rect_index(getattr(self, "_menu_row_rects", ()), local)
            if index is not None and index < self.EXIT_CONFIRMATION_OPTION_COUNT:
                self.exit_confirmation_cursor = index
                self.activate_exit_confirmation_selection()
                return True
        elif context == "cutscene":
            index = self._rect_index(getattr(self, "_cutscene_choice_rects", ()), local)
            if not self.active_cutscene_narration_complete():
                self.advance_active_cutscene()
                return True
            if index is not None and index < len(self.active_cutscene_choices()):
                self.cutscene_cursor = index
                self.choose_active_cutscene_option(index)
                return True
        elif context == "inventory":
            index = self._rect_index(
                getattr(self, "_inventory_visible_row_rects", ()), local
            )
            if index is not None:
                self.set_inventory_selection(self.inventory_scroll + index)
                return True
        elif context == "shop":
            index = self._rect_index(getattr(self, "_shop_visible_row_rects", ()), local)
            if index is not None:
                self.shop_cursor = int(getattr(self, "_shop_visible_start", 0)) + index
                return True
        elif context == "character":
            cells = getattr(self, "_discipline_cells", {})
            if isinstance(cells, dict):
                for key, rect in cells.items():
                    if isinstance(rect, pygame.Rect) and rect.collidepoint(local):
                        self.character_menu_hovered_node = str(key)
                        self.choose_discipline(str(key))
                        return True
        elif context == "about":
            self._dispatch_command(Command.BACK)
            return True
        elif context == "state_overlay":
            self._dispatch_command(Command.BACK)
            return True
        return False

    def _mobile_navigation_spec(self) -> tuple[tuple[str, str], ...]:
        context = self.mobile_input_context()
        if context == "gameplay":
            return ()
        specs: dict[str, tuple[tuple[str, str], ...]] = {
            "title": (("Back", Command.BACK), ("↑", Command.UP), ("↓", Command.DOWN), ("Select", Command.CONFIRM)),
            "options": (("Back", Command.BACK), ("↑", Command.UP), ("↓", Command.DOWN), ("−", Command.LEFT), ("+", Command.RIGHT), ("Select", Command.CONFIRM)),
            "controls": (("Back", Command.BACK), ("↑", Command.UP), ("↓", Command.DOWN), ("Select", Command.CONFIRM)),
            "about": (("Back", Command.BACK),),
            "archetype_select": (("Back", Command.BACK), ("←", Command.LEFT), ("→", Command.RIGHT), ("Begin", Command.CONFIRM)),
            "confirm_exit": (("Resume", Command.BACK), ("↑", Command.UP), ("↓", Command.DOWN), ("Select", Command.CONFIRM)),
            "state_overlay": (("New run", Command.BACK),),
            "help": (("Close", Command.BACK),),
            "cutscene": (("Pause", Command.BACK), ("↑", Command.UP), ("↓", Command.DOWN), ("Page ↑", Command.PAGE_UP), ("Page ↓", Command.PAGE_DOWN), ("Select", Command.CONFIRM)),
            "story_intro": (("Pause", Command.BACK), ("←", Command.LEFT), ("→", Command.RIGHT), ("Select", Command.CONFIRM)),
            "inventory": (("Close", Command.BACK), ("↑", Command.UP), ("↓", Command.DOWN), ("Sort", Command.TAB), ("Use", Command.CONFIRM), ("Drop", Command.DROP)),
            "shop": (("Close", Command.BACK), ("↑", Command.UP), ("↓", Command.DOWN), ("Mode", Command.TAB), ("Trade", Command.CONFIRM)),
            "character": (("Close", Command.BACK), ("Tab", Command.TAB), ("↑", Command.UP), ("↓", Command.DOWN), ("←", Command.LEFT), ("→", Command.RIGHT), ("Select", Command.CONFIRM)),
        }
        return specs.get(context, (("Back", Command.BACK),))

    def draw_mobile_touch_navigation(self) -> None:
        if not getattr(self, "mobile_mode", False):
            return
        spec = self._mobile_navigation_spec()
        if not spec:
            return
        context = self.mobile_input_context()
        # Modal/menu navigation replaces gameplay rail targets, preventing input
        # from leaking through an overlay drawn above the world.
        self._mobile_touch_targets = []
        safe = self.mobile_safe_rect()
        gap = max(5, min(12, safe.height // 72))
        button_h = max(48, min(68, safe.height // 8))
        available_w = max(1, safe.width - gap * (len(spec) + 1))
        button_w = max(54, min(132, available_w // max(1, len(spec))))
        total_w = button_w * len(spec) + gap * (len(spec) - 1)
        start_x = safe.centerx - total_w // 2
        y = safe.bottom - button_h - gap
        for index, (label, command) in enumerate(spec):
            rect = pygame.Rect(start_x + index * (button_w + gap), y, button_w, button_h)
            surface = pygame.Surface(rect.size, pygame.SRCALPHA)
            surface.fill((15, 14, 20, 224))
            pygame.draw.rect(
                surface,
                (192, 158, 88, 238),
                surface.get_rect(),
                max(2, min(4, button_h // 18)),
                border_radius=max(7, button_h // 7),
            )
            font = self.small_font if button_w >= 78 else self.tiny_font
            text = font.render(label, True, (242, 226, 194))
            surface.blit(text, text.get_rect(center=surface.get_rect().center))
            self.screen.blit(surface, rect)
            self.register_mobile_touch_target(
                rect, command, label, context=context
            )

    def draw_mobile_performance_overlay(self) -> None:
        """Draw the latest compact on-device phase summary without per-frame text work."""

        monitor = getattr(self, "_mobile_performance_monitor", None)
        if monitor is None:
            return
        lines = (monitor.overlay_text, monitor.overlay_detail_text)
        font = self.tiny_font
        cache = getattr(self, "_mobile_perf_overlay_cache", None)
        if cache is None or cache[0] != lines or cache[1] != id(font):
            labels = tuple(font.render(text, True, (236, 231, 206)) for text in lines)
            line_gap = 1
            surface = pygame.Surface(
                (
                    max(label.get_width() for label in labels) + 8,
                    sum(label.get_height() for label in labels) + line_gap + 4,
                ),
                pygame.SRCALPHA,
            )
            surface.fill((4, 5, 8, 212))
            y = 2
            for label in labels:
                surface.blit(label, (4, y))
                y += label.get_height() + line_gap
            surface = optimize_immutable_alpha_surface(surface)
            cache = (lines, id(font), surface)
            self._mobile_perf_overlay_cache = cache
        surface = cache[2]
        bounds = (
            self.mobile_world_viewport()
            if self.state in ("playing", "dead", "victory")
            else self.mobile_safe_rect()
        )
        x = bounds.x + 3
        y = max(bounds.y + 3, bounds.bottom - surface.get_height() - 3)
        if not self.blit_mobile_post_light(surface, (x, y)):
            self._mobile_display_surface().blit(surface, (x, y))

    def handle_mobile_lifecycle_event(self, event: pygame.event.Event) -> bool:
        if not getattr(self, "mobile_mode", False):
            return False
        renderer_resets = {
            getattr(pygame, "RENDER_TARGETS_RESET", -26),
            getattr(pygame, "RENDER_DEVICE_RESET", -27),
        }
        if event.type in renderer_resets:
            self.release_mobile_gpu_textures()
            self.refresh_mobile_gpu_renderer()
            return True
        background = {
            getattr(pygame, "APP_WILLENTERBACKGROUND", -20),
            getattr(pygame, "APP_DIDENTERBACKGROUND", -21),
        }
        foreground = {
            getattr(pygame, "APP_WILLENTERFOREGROUND", -22),
            getattr(pygame, "APP_DIDENTERFOREGROUND", -23),
        }
        if event.type in background:
            if self.mobile_suspended:
                return True
            self.cancel_mobile_touches()
            if self.state == "playing":
                self.save_run()
                self.request_exit_confirmation()
            elif self.state == "confirm_exit" and self.exit_previous_state == "playing":
                self.save_run()
            self.mobile_suspended = True
            self.mobile_audio_focus_paused = True
            if hasattr(self.audio, "suspend"):
                self.audio.suspend()
            return True
        if event.type in foreground:
            self.mobile_suspended = False
            self.release_mobile_gpu_textures()
            self.refresh_mobile_safe_insets()
            try:
                self.clock.tick()
            except (AttributeError, pygame.error):
                pass
            # A run remains on the existing confirmation/pause sheet. Audio is
            # resumed only after the player explicitly chooses Resume.
            if self.state != "confirm_exit":
                self.resume_mobile_audio_focus()
            return True
        if event.type == getattr(pygame, "APP_TERMINATING", -24):
            if self.state == "playing" or (
                self.state == "confirm_exit" and self.exit_previous_state == "playing"
            ):
                self.save_run()
            return True
        if event.type == getattr(pygame, "APP_LOWMEMORY", -25):
            self.clear_mobile_memory_caches()
            return True
        return False

    def resume_mobile_audio_focus(self) -> None:
        if not getattr(self, "mobile_audio_focus_paused", False):
            return
        self.mobile_audio_focus_paused = False
        if hasattr(self.audio, "resume"):
            self.audio.resume()
        self.sync_music()

    def clear_mobile_memory_caches(self) -> None:
        self.release_mobile_gpu_textures()
        self._world_layer = None
        self._mobile_floor_layer_cache = None
        self._screen_flash_surface = None
        self._mobile_static_menu_last_signature = None
        self._mobile_static_shell_signature = None
        menus = getattr(self, "menus", None)
        if menus is not None and hasattr(menus, "_menu_backdrop_cache"):
            menus._menu_backdrop_cache = None
        for name in (
            "_hud_panel_cache",
            "_hud_icon_cache",
            "_ui_text_cache",
            "_alpha_tile_cache",
            "ambient_overlay_cache",
        ):
            cache = getattr(self, name, None)
            if cache is not None and hasattr(cache, "clear"):
                cache.clear()
        if hasattr(self, "reset_lighting_caches"):
            self.reset_lighting_caches()
        if hasattr(self, "clear_stage_render_cache"):
            self.clear_stage_render_cache()
        sprites = getattr(self, "sprites", None)
        if sprites is not None and hasattr(sprites, "clear_derived_caches"):
            sprites.clear_derived_caches()
        ui_assets = getattr(self, "ui_assets", None)
        if ui_assets is not None and hasattr(ui_assets, "clear_derived_caches"):
            ui_assets.clear_derived_caches()
