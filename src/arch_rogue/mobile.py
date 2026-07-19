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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pygame

from .content import ARCHETYPES
from .input import Command


_TRUE_VALUES = frozenset(("1", "true", "yes", "on"))
_FALSE_VALUES = frozenset(("0", "false", "no", "off"))


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
        if getattr(self, "mobile_mode", False):
            self.refresh_mobile_safe_insets()

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

    def handle_mobile_lifecycle_event(self, event: pygame.event.Event) -> bool:
        if not getattr(self, "mobile_mode", False):
            return False
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
        self._world_layer = None
        self._screen_flash_surface = None
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
