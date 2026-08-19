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
"""Input abstraction for Arch Rogue (milestone 3.9).

This module is the single source of truth for translating raw keyboard, mouse,
and gamepad input into a small set of shared *commands* (move, aim, ability,
interact, navigate, confirm, back, tab). ``Game.handle_events`` keeps its
existing flow; controller events and the unified menu navigation path route
through the helpers here so keyboard and gamepad behave consistently.

The hot-path pieces (per-frame axis polling) cache float attributes and
independent stick deadzone state, keeping movement stable across noisy frames
without changing the public vector API.
"""

from __future__ import annotations

import os
import time
from typing import Any, Iterable

import pygame

from .content import ARCHETYPES
from .steam_deck import is_steam_deck


class Command:
    """Shared gameplay/menu command names.

    These are intentionally string constants (not an Enum) so they can be
    serialized into options and compared cheaply without attribute lookup
    overhead in the event loop.
    """

    # Directional navigation (also movement intent for menus).
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"

    # Universal menu actions.
    CONFIRM = "confirm"
    BACK = "back"
    TAB = "tab"
    TAB_PREV = "tab_prev"

    # Gameplay actions.
    INTERACT = "interact"
    HELP = "help"
    QUEST = "quest"
    INVENTORY = "inventory"
    CHARACTER = "character"
    OPEN_DISCIPLINES = "open_disciplines"
    MOBILE_MENU = "mobile_menu"
    MOBILE_EXIT = "mobile_exit"
    ABILITY_1 = "ability_1"
    ABILITY_2 = "ability_2"
    ABILITY_3 = "ability_3"
    ABILITY_4 = "ability_4"
    ABILITY_5 = "ability_5"
    ABILITY_6 = "ability_6"

    # Minimap zoom. Commands rather than a direct adjust_minimap_zoom() call so
    # the D-pad, a remapped button and a Steam Input action all reach it the
    # same way.
    MAP_ZOOM_IN = "map_zoom_in"
    MAP_ZOOM_OUT = "map_zoom_out"

    # Cycling (archetype select, difficulty, sort mode).
    NEXT = "next"
    PREV = "prev"

    # Inventory list extras (mirror keyboard PageUp/Down/Home/End/Drop).
    PAGE_UP = "page_up"
    PAGE_DOWN = "page_down"
    HOME = "home"
    END = "end"
    DROP = "drop"


# Keyboard keys that map to a single command regardless of state. Only the
# navigation + universal action keys live here; the delicate gameplay ability
# keys (1-9, E, Q, C, I, H) are still handled by Game.handle_events directly so
# existing keyboard bindings are preserved exactly.
KEY_COMMANDS: dict[int, str] = {
    pygame.K_UP: Command.UP,
    pygame.K_DOWN: Command.DOWN,
    pygame.K_LEFT: Command.LEFT,
    pygame.K_RIGHT: Command.RIGHT,
    pygame.K_RETURN: Command.CONFIRM,
    pygame.K_ESCAPE: Command.BACK,
    pygame.K_BACKSPACE: Command.BACK,
    pygame.K_TAB: Command.TAB,
    pygame.K_PAGEUP: Command.PAGE_UP,
    pygame.K_PAGEDOWN: Command.PAGE_DOWN,
    pygame.K_HOME: Command.HOME,
    pygame.K_END: Command.END,
    pygame.K_DELETE: Command.DROP,
}

# Shift+Tab -> previous tab. Detected separately in the keyboard path.
KEY_COMMANDS_SHIFT: dict[int, str] = {
    pygame.K_TAB: Command.TAB_PREV,
}


def key_command(key: int, mod: int) -> str | None:
    """Map a KEYDOWN key/modifier pair to a shared command, or ``None``.

    Only navigation/universal keys are mapped here. Gameplay-specific keys are
    intentionally left for ``Game.handle_events`` so legacy bindings stay intact.
    """
    if mod & pygame.KMOD_SHIFT:
        cmd = KEY_COMMANDS_SHIFT.get(key)
        if cmd is not None:
            return cmd
    return KEY_COMMANDS.get(key)


# Default gamepad button -> command mapping for MENU navigation. Button
# indices follow the SDL Xbox-style layout (A=0, B=1, X=2, Y=3, LB=4, RB=5,
# Back=6, Start=7, LS=8, RS=9). Used in every non-gameplay state and while an
# overlay (inventory/shop/character) is open.
DEFAULT_JOY_BUTTON_COMMANDS: dict[int, str] = {
    0: Command.CONFIRM,
    1: Command.BACK,
    2: Command.INTERACT,
    3: Command.HELP,
    4: Command.BACK,
    5: Command.TAB,
    6: Command.BACK,
    7: Command.CHARACTER,
}

# Base gameplay button map. These raw SDL button IDs intentionally mirror the
# shipped controller profile; menu/cutscene buttons keep their context-specific
# meanings. Stick and hat movement remain handled independently.
GAMEPLAY_BUTTON_COMMANDS: dict[int, str] = {
    0: Command.INTERACT,
    1: Command.ABILITY_3,
    2: Command.ABILITY_2,
    3: Command.ABILITY_5,
    4: Command.BACK,
    5: Command.ABILITY_6,
    6: Command.INVENTORY,
    7: Command.CHARACTER,
    15: Command.CHARACTER,
}

# Steam Deck's built-in controls use raw indices outside the common SDL/Xbox
# layout. Keep these aliases platform-scoped so a generic controller's right
# stick click (usually button 9) does not drink a potion or rotate a menu tab.
DECK_GAMEPAD_PROFILE_VERSION = 1
DECK_MENU_BUTTON_COMMANDS: dict[int, str] = {
    9: Command.TAB,  # R1
    10: Command.TAB_PREV,  # L1
}
DECK_GAMEPLAY_BUTTON_COMMANDS: dict[int, str] = {
    9: Command.ABILITY_6,  # R1 -> mana potion
    16: Command.OPEN_DISCIPLINES,
}

# Cutscene button map: A advances narration / selects the highlighted choice,
# B skips, and X/Y/LB/RB quick-pick choices 0-3 so dialogue stays fast on pad.
CUTSCENE_BUTTON_COMMANDS: dict[int, str] = {
    0: Command.CONFIRM,  # A  -> advance / select highlighted
    1: Command.BACK,  # B  -> skip / close
    2: Command.ABILITY_1,  # X  -> choice 0
    3: Command.ABILITY_2,  # Y  -> choice 1
    4: Command.BACK,  # LB -> back / skip
    5: Command.ABILITY_4,  # RB -> choice 3
}

# D-pad button indices on the standard SDL/Xbox layout (when the D-pad is
# reported as buttons rather than a hat). These are ALWAYS converted to
# directional commands in every context (gameplay, menus, cutscenes) — the
# D-pad is navigation-only and cannot be remapped to other actions. The
# gameplay button map no longer includes these indices.
# What a D-pad direction means during gameplay.
#
# In menus the D-pad must stay navigation -- nothing else moves a cursor. During
# gameplay the sticks carry movement and aim, so bare directional commands did
# nothing there at all: that is why the D-pad felt dead in-game while still
# working in menus.
#
# Up/Down only. Left/Right briefly opened the inventory and character sheet in
# 4.9.22 and were reverted: those overlays switch the input context to a menu,
# where the D-pad is navigation, so the direction that opened one could not
# close it without a special case that fought the rest of the input model.
# Inventory and character stay on their remappable face buttons.
#
# Applies to every controller, not just the Deck's built-in pad. The previous
# Up/Down zoom was gated on is_steam_deck(), which is the DMI-probe mistake that
# also broke the button mapping when Steam substitutes a virtual pad.
DPAD_GAMEPLAY_COMMANDS: dict[str, str] = {
    Command.UP: Command.MAP_ZOOM_IN,
    Command.DOWN: Command.MAP_ZOOM_OUT,
}

DPAD_BUTTON_COMMANDS: dict[int, str] = {
    # Standard Linux/SDL evdev ordering (BTN_DPAD_UP/DOWN/LEFT/RIGHT).
    # The previous mapping used the Xbox-style ordering (Up/Right/Down/Left)
    # which swapped Down and Left on the Steam Deck.
    11: Command.UP,
    12: Command.DOWN,
    13: Command.LEFT,
    14: Command.RIGHT,
}

# Trigger axes: LT = action skill 1 (melee), RT = dash. Order is by ascending
# trigger axis index (LT before RT on common pads).
TRIGGER_COMMANDS: tuple[str, ...] = (Command.ABILITY_1, Command.ABILITY_4)
TRIGGER_PRESS_THRESHOLD = 0.25
# Left-stick menu navigation thresholds. ACTIVATION is how far the stick must
# be pushed to register a directional "tap"; RELEASE is how far it must return
# toward center before another tap can fire. Hysteresis prevents a single push
# from emitting multiple commands.
STICK_NAV_ACTIVATION = 0.5
STICK_NAV_RELEASE = 0.3

REMAPPABLE_GAMEPAD_COMMANDS: tuple[str, ...] = (
    Command.ABILITY_1,
    Command.ABILITY_2,
    Command.ABILITY_3,
    Command.ABILITY_4,
    Command.ABILITY_5,
    Command.ABILITY_6,
    Command.INTERACT,
    Command.INVENTORY,
    Command.CHARACTER,
    Command.BACK,
)

# Shown in the Controls menu so the D-pad zoom is discoverable, without being
# assignable -- the D-pad is navigation everywhere else and cannot be rebound.
# (label, binding) in the same shape as the remappable rows so the binding text
# lands in the same right-aligned column rather than leaving a ragged gap.
FIXED_GAMEPAD_BINDINGS: tuple[tuple[str, str], ...] = (
    ("Zoom minimap in", "D-pad Up"),
    ("Zoom minimap out", "D-pad Down"),
)


# Controller diagnostics. Set ARCH_ROGUE_LOG_JOYSTICK=1 to print the device
# name and the raw index of every button press.
#
# This exists because the button indices a pad reports depend on *how* it is
# reached, not on the hardware. Run natively, a Steam Deck reports its own evdev
# layout (D-pad as buttons 11-14, R1 as 9). Run through Steam with Steam Input
# active, Steam hides the physical device and substitutes a virtual Xbox-style
# pad where 9 is right-stick-click and the D-pad is a hat. The same Deck
# therefore needs different mappings depending on the launch path, and the only
# way to tell which one is live is to look at what actually arrives.
LOG_JOYSTICK_ENV = "ARCH_ROGUE_LOG_JOYSTICK"
_TRUTHY = {"1", "true", "yes", "on"}
_LOG_JOYSTICK_SEEN: set[int] = set()


def log_joystick_button(manager: Any, joy_id: int, button: int) -> None:
    if os.environ.get(LOG_JOYSTICK_ENV, "").strip().lower() not in _TRUTHY:
        return
    joy = getattr(manager, "_joysticks", {}).get(joy_id)
    if joy is not None and joy_id not in _LOG_JOYSTICK_SEEN:
        _LOG_JOYSTICK_SEEN.add(joy_id)
        try:
            print(
                f"[joystick] device {joy_id}: name={manager._name(joy)!r} "
                f"guid={manager._guid(joy)!r} buttons={joy.get_numbuttons()} "
                f"hats={joy.get_numhats()} axes={joy.get_numaxes()}",
                flush=True,
            )
        except (AttributeError, pygame.error):
            pass
    print(f"[joystick] button {button} pressed (device {joy_id})", flush=True)


# Device names that mean Steam is interposing a virtual pad rather than handing
# us the physical device. Steam Input hides the real controller and synthesises
# an Xbox-layout one, so the Deck's own evdev indices do not apply even though
# the DMI probe still says "this is a Steam Deck". Matched case-insensitively as
# substrings, because the exact string varies by Steam client version.
STEAM_VIRTUAL_PAD_NAME_MARKERS: tuple[str, ...] = (
    "x-box",
    "xbox",
    "steam virtual",
    "steam controller",
)
# Conversely, these mean we are talking to the Deck's built-in controls directly.
DECK_NATIVE_PAD_NAME_MARKERS: tuple[str, ...] = (
    "steam deck",
    "valve software",
)


def uses_deck_native_layout(controller_name: str | None) -> bool:
    """Whether raw Steam Deck button indices apply to this device.

    The layout a pad reports depends on how it is reached, not on the hardware
    underneath. Launched natively, a Deck reports its own evdev layout: D-pad on
    buttons 11-14, R1 on 9, the quick-access button on 16. Launched through Steam
    with Steam Input active, Steam hides that device and substitutes a virtual
    Xbox-style pad where 9 is right-stick-click and the D-pad is a hat.

    Deciding from the DMI probe alone therefore decoded an Xbox pad with a Deck
    keymap whenever the game was launched through Steam -- right-stick-click
    drank a potion, and half the face buttons landed on the wrong command. Prefer
    what the connected device says about itself; fall back to the hardware probe
    only when nothing is connected yet, which is the case while options load.
    """

    name = (controller_name or "").casefold()
    if name:
        if any(marker in name for marker in STEAM_VIRTUAL_PAD_NAME_MARKERS):
            return False
        if any(marker in name for marker in DECK_NATIVE_PAD_NAME_MARKERS):
            return True
        # An unrecognised pad plugged into a Deck is a generic pad, not the
        # built-in controls.
        return False
    return is_steam_deck()


def default_gamepad_mapping(
    controller_name: str | None = None,
) -> dict[str, dict[int, str] | list[str]]:
    menu_buttons = dict(DEFAULT_JOY_BUTTON_COMMANDS)
    gameplay_buttons = dict(GAMEPLAY_BUTTON_COMMANDS)
    if uses_deck_native_layout(controller_name):
        menu_buttons.update(DECK_MENU_BUTTON_COMMANDS)
        gameplay_buttons.update(DECK_GAMEPLAY_BUTTON_COMMANDS)
    return {
        "menu_buttons": menu_buttons,
        "gameplay_buttons": gameplay_buttons,
        "cutscene_buttons": dict(CUTSCENE_BUTTON_COMMANDS),
        "triggers": list(TRIGGER_COMMANDS),
    }


def add_missing_deck_gameplay_aliases(
    mapping: dict[str, dict[int, str] | list[str]],
) -> None:
    """One-time migration for Deck aliases added after controller profiles.

    A command the player bound to a trigger must not gain a button alias:
    save-time dedupe lets buttons win over triggers, so the injected alias
    would silently blank the player's trigger slot on the next save.
    """
    buttons = mapping.get("gameplay_buttons", {})
    if not isinstance(buttons, dict):
        return
    triggers = mapping.get("triggers", [])
    trigger_bound = (
        {cmd for cmd in triggers if cmd} if isinstance(triggers, list) else set()
    )
    for button, cmd in DECK_GAMEPLAY_BUTTON_COMMANDS.items():
        if cmd in trigger_bound:
            continue
        buttons.setdefault(button, cmd)


# Version stamp for the persisted gamepad mapping, written to options as
# "gamepad_mapping_version". Bump when the shipped default layout changes so
# load_options can tell a deliberate player profile from stale defaults that
# an old build persisted verbatim.
#   1 — initial controller support (2026-07-06): A=melee, LT=dash, RT=interact.
#   2 — Steam-merge redesign (2026-07-31): A=interact, LT=melee/Big Hit,
#       RT=dash. Saved profiles override defaults, so version-1 files kept the
#       old layout forever; on the Deck this surfaced as "triggers stopped
#       working" after the 5.0.1 storage migration resurrected July profiles.
GAMEPAD_MAPPING_VERSION = 2

# Every default layout an earlier build ever persisted, deck aliases aside.
# serialize_gamepad_mapping always wrote the full mapping, so a profile that
# matches one of these was never customized and is safe to re-default.
_LEGACY_DEFAULT_LAYOUTS: tuple[
    tuple[dict[int, str], tuple[str, ...]], ...
] = (
    (
        {
            0: Command.ABILITY_1,
            1: Command.BACK,
            2: Command.ABILITY_2,
            3: Command.ABILITY_3,
            4: Command.ABILITY_5,
            5: Command.ABILITY_6,
            6: Command.INVENTORY,
            7: Command.CHARACTER,
        },
        (Command.ABILITY_4, Command.INTERACT),
    ),
)


def migrate_legacy_gamepad_layout(
    mapping: dict[str, dict[int, str] | list[str]],
) -> bool:
    """Re-default a persisted mapping that is exactly an old shipped default.

    Called for option files whose gamepad_mapping_version predates
    GAMEPAD_MAPPING_VERSION. Any customized profile is left alone — only a
    verbatim copy of an earlier default layout is replaced, because that
    player never chose it; an old build simply wrote its defaults to disk.
    Deck alias entries are ignored for the comparison and kept afterwards.
    """
    buttons = mapping.get("gameplay_buttons", {})
    triggers = mapping.get("triggers", [])
    if not isinstance(buttons, dict) or not isinstance(triggers, list):
        return False
    aliases = {
        button: cmd
        for button, cmd in buttons.items()
        if DECK_GAMEPLAY_BUTTON_COMMANDS.get(button) == cmd
    }
    bare_buttons = {
        button: cmd for button, cmd in buttons.items() if button not in aliases
    }
    bare_triggers = tuple(cmd for cmd in triggers if cmd)
    for legacy_buttons, legacy_triggers in _LEGACY_DEFAULT_LAYOUTS:
        if bare_buttons == legacy_buttons and bare_triggers == legacy_triggers:
            new_buttons: dict[int, str] = dict(GAMEPLAY_BUTTON_COMMANDS)
            new_buttons.update(aliases)
            mapping["gameplay_buttons"] = new_buttons
            mapping["triggers"] = list(TRIGGER_COMMANDS)
            return True
    return False


def heal_gamepad_trigger_slots(
    mapping: dict[str, dict[int, str] | list[str]],
) -> bool:
    """Rebind default trigger commands that are bound to nothing at all.

    Save-time dedupe historically blanked a trigger slot whenever its command
    also appeared on a button — including buttons injected by the Deck alias
    migration — leaving the slot as a persisted "" with no way to notice short
    of the Controls menu. A blank slot whose default command is still reachable
    elsewhere is a deliberate layout and stays blank; one whose default command
    is bound nowhere is damage, and gets its default back.
    """
    buttons = mapping.get("gameplay_buttons", {})
    triggers = mapping.get("triggers", [])
    if not isinstance(buttons, dict) or not isinstance(triggers, list):
        return False
    bound = set(buttons.values()) | {cmd for cmd in triggers if cmd}
    changed = False
    for slot, cmd in enumerate(TRIGGER_COMMANDS):
        if cmd in bound:
            continue
        while len(triggers) <= slot:
            triggers.append("")
        if not triggers[slot]:
            triggers[slot] = cmd
            bound.add(cmd)
            changed = True
    if changed and "triggers" not in mapping:
        mapping["triggers"] = triggers
    return changed


def normalize_gamepad_mapping(data: object) -> dict[str, dict[int, str] | list[str]]:
    mapping = default_gamepad_mapping()
    if not isinstance(data, dict):
        return mapping
    valid = set(REMAPPABLE_GAMEPAD_COMMANDS) | {
        Command.CONFIRM,
        Command.HELP,
        Command.OPEN_DISCIPLINES,
        Command.TAB,
        Command.TAB_PREV,
    }
    raw_buttons = data.get("gameplay_buttons", {})
    has_raw_buttons = "gameplay_buttons" in data and isinstance(raw_buttons, dict)
    raw_triggers = data.get("triggers", [])
    has_raw_triggers = "triggers" in data and isinstance(raw_triggers, list)
    if has_raw_buttons:
        buttons: dict[int, str] = {}
        for raw_button, raw_cmd in raw_buttons.items():
            try:
                button = int(raw_button)
            except (TypeError, ValueError):
                continue
            cmd = str(raw_cmd)
            if 0 <= button <= 31 and cmd in valid:
                buttons[button] = cmd
        if buttons:
            mapping["gameplay_buttons"] = buttons
    if has_raw_triggers:
        triggers: list[str] = []
        for raw_cmd in raw_triggers[:4]:
            cmd = str(raw_cmd)
            triggers.append(cmd if cmd in valid else "")
        if triggers:
            mapping["triggers"] = triggers
    if has_raw_buttons and has_raw_triggers:
        _dedupe_gamepad_mapping(mapping, buttons_win=True)
    elif has_raw_buttons:
        _dedupe_gamepad_mapping(mapping, buttons_win=True)
    elif has_raw_triggers:
        _dedupe_gamepad_mapping(mapping, buttons_win=False)
    return mapping


def _dedupe_gamepad_mapping(
    mapping: dict[str, dict[int, str] | list[str]], buttons_win: bool = True
) -> None:
    """Keep one physical binding per command, repairing older duplicate saves.

    Buttons win over triggers when loading full old saves because the previous UI
    would show the button binding first while the hidden default trigger binding
    still fired. Trigger-only partial data instead wins over default buttons.
    Within triggers, the first slot wins and later duplicates are cleared.
    """
    buttons = mapping.get("gameplay_buttons", {})
    triggers = mapping.get("triggers", [])
    if not isinstance(buttons, dict) or not isinstance(triggers, list):
        return
    seen_triggers: set[str] = set()
    trigger_commands = {cmd for cmd in triggers if cmd}
    if not buttons_win:
        for button, cmd in list(buttons.items()):
            if cmd in trigger_commands:
                del buttons[button]
    button_commands = set(buttons.values())
    for index, cmd in enumerate(list(triggers)):
        if not cmd:
            continue
        if (buttons_win and cmd in button_commands) or cmd in seen_triggers:
            triggers[index] = ""
        else:
            seen_triggers.add(cmd)


def serialize_gamepad_mapping(
    mapping: dict[str, dict[int, str] | list[str]],
) -> dict[str, dict[str, str] | list[str]]:
    buttons = mapping.get("gameplay_buttons", {})
    triggers = mapping.get("triggers", [])
    return {
        "gameplay_buttons": {
            str(button): cmd
            for button, cmd in sorted(buttons.items())
            if isinstance(button, int) and isinstance(cmd, str)
        }
        if isinstance(buttons, dict)
        else {},
        "triggers": list(triggers) if isinstance(triggers, list) else [],
    }


def button_for_command(mapping: dict[int, str], command: str) -> int | None:
    for button, cmd in sorted(mapping.items()):
        if cmd == command:
            return button
    return None


def trigger_slot_for_command(commands: list[str], command: str) -> int | None:
    for slot, cmd in enumerate(commands):
        if cmd == command:
            return slot
    return None


def joybutton_command(button: int) -> str | None:
    return DEFAULT_JOY_BUTTON_COMMANDS.get(button)


def joybutton_command_for_state(button: int, context: str) -> str | None:
    """Resolve a gamepad button to a command for the given input context.

    context is one of "menu", "gameplay", "cutscene". ``InputMixin`` picks the
    context from the current Game state so a single physical button (e.g. A)
    can mean confirm in a menu, melee in gameplay, and advance in a cutscene.
    """
    if context == "gameplay":
        return GAMEPLAY_BUTTON_COMMANDS.get(button)
    if context == "cutscene":
        return CUTSCENE_BUTTON_COMMANDS.get(button)
    return DEFAULT_JOY_BUTTON_COMMANDS.get(button)


# Button indices that only exist on the Deck's own evdev layout. On the virtual
# Xbox pad Steam Input substitutes, these indices mean something else entirely
# (9 is right-stick-click, not R1), so a persisted Deck profile must not be
# applied to one. Suppressed at resolve time rather than rewritten in options,
# because the same install can move between the two paths -- launched from Steam
# one day and directly the next -- and the saved profile has to stay valid for
# both.
DECK_ONLY_BUTTON_INDICES: frozenset[int] = frozenset(
    set(DECK_MENU_BUTTON_COMMANDS) | set(DECK_GAMEPLAY_BUTTON_COMMANDS)
) - set(GAMEPLAY_BUTTON_COMMANDS) - set(DEFAULT_JOY_BUTTON_COMMANDS)


def mapped_joybutton_command(
    button: int,
    context: str,
    mapping: dict[str, dict[int, str] | list[str]],
    deck_native: bool = True,
) -> str | None:
    if not deck_native and button in DECK_ONLY_BUTTON_INDICES:
        return None
    # 4.9.20: the gameplay button map used to leak BACK into every context
    # via a special case (`if cmd == Command.BACK: return Command.BACK`). That
    # meant any gameplay-only button mapped to BACK -- e.g. button 11 (D-pad
    # Up on the original controller profile) -- also fired BACK in menus,
    # closing them instead of navigating the cursor. Removed: the menu map
    # already has its own BACK binding (button 1 / B), so gameplay-only buttons
    # no longer bleed across contexts. Gameplay BACK still works because the
    # `context == "gameplay"` path below returns the gameplay-mapped command
    # directly.
    gameplay_buttons = mapping.get("gameplay_buttons", {})
    if isinstance(gameplay_buttons, dict):
        cmd = gameplay_buttons.get(button)
        if context == "gameplay":
            return cmd
        # Character is an overlay toggle: its remapped gameplay button must
        # also close the character sheet while menu context is active.
        if cmd == Command.CHARACTER:
            return cmd
    if context == "cutscene":
        buttons = mapping.get("cutscene_buttons", {})
        return buttons.get(button) if isinstance(buttons, dict) else None
    buttons = mapping.get("menu_buttons", {})
    return buttons.get(button) if isinstance(buttons, dict) else None


class ControllerManager:
    """Owns joystick lifecycle, device selection, and axis polling.

    Responsibilities:
    - init/teardown the joystick subsystem and enumerate connected devices.
    - auto-select the last-used device (matched by GUID) or the first device.
    - handle hot-plug connect/disconnect events.
    - expose cheap, allocation-free left/right stick vectors for the run loop.
    """

    # Keep the legacy deadzone as the radial scaling origin. A stick must move
    # clearly beyond it to activate, then remains active until it returns below
    # the lower release threshold, preventing frame-to-frame movement chatter.
    DEADZONE = 0.24
    DEADZONE_ACTIVATION = 0.28
    # Release at the legacy neutral boundary. Once released, activation still
    # requires 0.28, so threshold noise cannot chatter or latch neutral drift.
    DEADZONE_RELEASE = DEADZONE
    # Axes whose rest value is far from zero (|v| > 0.5) are treated as
    # triggers and skipped when locating the analog sticks. This handles the
    # common raw-joystick layouts (Xbox: axes 2/5 are triggers; Stadia/PS:
    # axes 4/5 are triggers) without relying on the SDL controller DB.
    TRIGGER_REST_THRESHOLD = 0.5
    # SDL on Android exposes motion sensors as raw joysticks. Only reject
    # explicit sensor descriptors so Bluetooth/USB gamepads remain available.
    MOTION_SENSOR_NAME_MARKERS = (
        "accelerometer",
        "gyroscope",
        "gyro",
        "gravity",
        "linear acceleration",
        "rotation vector",
        "orientation sensor",
    )

    def __init__(
        self,
        last_guid: str = "",
        enabled: bool = True,
        *,
        ignore_motion_sensors: bool = False,
    ) -> None:
        self.enabled = enabled
        self.ignore_motion_sensors = bool(ignore_motion_sensors)
        self._last_guid = last_guid or ""
        self._joysticks: dict[int, Any] = {}
        self._active_id: int | None = None
        # Per-device (left_axes, right_axes) layout, computed once at connect
        # time from rest axis values so the hot path never recomputes it.
        self._axis_layout: dict[
            int, tuple[tuple[int, int] | None, tuple[int, int] | None]
        ] = {}
        self._layout_id: int | None = None
        self._left_axes: tuple[int, int] | None = None
        self._right_axes: tuple[int, int] | None = None
        # Per-device sorted trigger axis indices (axes that rest far from 0).
        self._trigger_layout: dict[int, list[int]] = {}
        self._active_triggers: list[int] = []
        # Edge-detection state for triggers: previous pressed bool per axis,
        # and a queue of commands emitted by rising-edge presses this frame.
        self._trigger_pressed: dict[int, bool] = {}
        self._queued_commands: list[str] = []
        self._queued_trigger_slots: list[int] = []
        # Falling-edge trigger releases (4.10 Big Hit hold-to-charge). Emitted
        # even while emit_trigger_commands is off: a release can never
        # double-fire the way bumper-as-axis presses could, and dropping one
        # would wrongly commit a charge the player let go of.
        self._queued_release_commands: list[str] = []
        # 4.9.20: left-stick -> discrete directional commands for menu
        # navigation. Analog sticks don't fire events; we poll each frame and
        # emit one UP/DOWN/LEFT/RIGHT per rising-edge deflection (hysteresis
        # prevents repeats while held). The D-pad hat already does this via
        # hat_commands; this is the stick equivalent.
        self._queued_stick_commands: list[str] = []
        self._stick_nav_active = False
        self.trigger_commands = list(TRIGGER_COMMANDS)
        # Cached axis state. Updated in-place by poll_axes(); the returned
        # tuples are only rebuilt when the deadzone crossing changes so the
        # per-frame hot path avoids allocations.
        self._left_x = 0.0
        self._left_y = 0.0
        self._right_x = 0.0
        self._right_y = 0.0
        self._left_stick_active = False
        self._right_stick_active = False
        self._left_vec: tuple[float, float] = (0.0, 0.0)
        self._right_vec: tuple[float, float] = (0.0, 0.0)

    # --- Lifecycle -------------------------------------------------------

    def initialize(self) -> None:
        """Init the joystick subsystem and pick up already-connected devices."""
        try:
            pygame.joystick.init()
        except pygame.error:
            return
        for index in range(pygame.joystick.get_count()):
            self._add_device(index)

    def quit(self) -> None:
        for joy in list(self._joysticks.values()):
            try:
                joy.quit()
            except pygame.error:
                pass
        self._joysticks.clear()
        self._axis_layout.clear()
        self._trigger_layout.clear()
        self._trigger_pressed.clear()
        self._active_id = None
        self._layout_id = None
        self._active_triggers = []

    def _guid(self, joy: Any) -> str:
        try:
            return joy.get_guid()
        except (AttributeError, pygame.error):
            return ""

    def _name(self, joy: Any) -> str:
        try:
            return str(joy.get_name() or "")
        except (AttributeError, pygame.error):
            return ""

    @staticmethod
    def _has_button_or_hat_controls(joy: Any) -> bool:
        """Return whether a named sensor is demonstrably a real controller."""

        try:
            if joy.get_numbuttons() > 0:
                return True
        except (AttributeError, pygame.error):
            pass
        try:
            return joy.get_numhats() > 0
        except (AttributeError, pygame.error):
            return False

    def _is_ignored_motion_sensor(self, joy: Any) -> bool:
        if not self.ignore_motion_sensors:
            return False
        name = self._name(joy).casefold()
        named_as_sensor = any(
            marker in name for marker in self.MOTION_SENSOR_NAME_MARKERS
        )
        return named_as_sensor and not self._has_button_or_hat_controls(joy)

    def _add_device(self, device_index: int) -> Any | None:
        try:
            joy = pygame.joystick.Joystick(device_index)
        except pygame.error:
            return None
        if self._is_ignored_motion_sensor(joy):
            try:
                joy.quit()
            except pygame.error:
                pass
            return None
        # pygame-ce auto-initializes Joystick objects since 2.4; the explicit
        # init() call is deprecated and no longer needed.
        joy_id = joy.get_instance_id()
        self._joysticks[joy_id] = joy
        self._axis_layout[joy_id] = self._compute_layout(joy)
        self._trigger_layout[joy_id] = self._compute_triggers(joy)
        guid = self._guid(joy)
        # Prefer the persisted device; otherwise fall back to the first one.
        # If the persisted GUID connects later, it takes over as active so the
        # last-used controller is honored across hot-plug.
        if self._last_guid and guid == self._last_guid:
            self._active_id = joy_id
        elif self._active_id is None:
            # No persisted match yet; use this device as a fallback without
            # overwriting the persisted GUID so the right pad can claim active
            # later when it hot-plugs in.
            self._active_id = joy_id
        return joy

    def handle_device_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.JOYDEVICEADDED:
            # _add_device already promotes the persisted GUID to active when it
            # matches; we do not overwrite the persisted preference here so a
            # fallback pad does not erase the player's last-used controller.
            self._add_device(event.device_index)
        elif event.type == pygame.JOYDEVICEREMOVED:
            # pygame exposes the removed device's instance id as `which` on
            # JOYDEVICEREMOVED (and `instance_id` on some builds).
            removed_id = getattr(event, "instance_id", None)
            if removed_id is None:
                removed_id = getattr(event, "which", None)
            removed = (
                self._joysticks.pop(removed_id, None)
                if removed_id is not None
                else None
            )
            if removed is not None:
                try:
                    removed.quit()
                except pygame.error:
                    pass
            if self._active_id == removed_id:
                self._active_id = next(iter(self._joysticks), None)
            if removed_id is not None:
                self._axis_layout.pop(removed_id, None)

    # --- Selection -------------------------------------------------------

    def active(self) -> Any | None:
        if self._active_id is None:
            return None
        return self._joysticks.get(self._active_id)

    def has_controller(self) -> bool:
        return self.enabled and self.active() is not None

    def active_name(self) -> str:
        joy = self.active()
        if joy is None:
            return ""
        return self._name(joy) or "Gamepad"

    def active_guid(self) -> str:
        joy = self.active()
        return self._guid(joy) if joy is not None else ""

    def active_controller_is_deck_native(self) -> bool:
        """Whether the active pad reports the Deck's own evdev button layout.

        False for the virtual Xbox-style pad Steam Input substitutes, even when
        running on Deck hardware -- see :func:`uses_deck_native_layout`.
        """

        joy = self.active()
        if joy is None:
            return is_steam_deck()
        return uses_deck_native_layout(self._name(joy))

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        if not self.enabled:
            self._reset_axes()
            self._trigger_pressed.clear()
            self._queued_commands.clear()
            self._queued_trigger_slots.clear()

    def prefer_device(self, guid: str) -> None:
        """Switch the active device to one matching ``guid`` if connected."""
        if not guid:
            return
        for joy_id, joy in self._joysticks.items():
            if self._guid(joy) == guid:
                self._active_id = joy_id
                self._last_guid = guid
                return

    # --- Axis polling (hot path) ----------------------------------------

    def _compute_layout(
        self, joy: Any
    ) -> tuple[tuple[int, int] | None, tuple[int, int] | None]:
        """Identify left/right stick axis indices for a freshly-connected device.

        Sticks rest at 0; triggers rest at -1 (or +1 on a few pads). We sample
        rest values once at connect time, skip trigger axes, and treat the
        first two remaining axes as the left stick and the next two as the
        right stick. This matches every common SDL raw-joystick layout without
        needing the SDL game-controller mapping DB.
        """
        try:
            num_axes = joy.get_numaxes()
        except pygame.error:
            return (None, None)
        if num_axes < 2:
            return (None, None)
        try:
            rest = [joy.get_axis(i) for i in range(num_axes)]
        except pygame.error:
            return ((0, 1) if num_axes >= 2 else None, None)
        stick_axes = [
            i for i, v in enumerate(rest) if abs(v) <= self.TRIGGER_REST_THRESHOLD
        ]
        if len(stick_axes) < 2:
            # No reliable stick detection; assume the first two axes are left.
            stick_axes = list(range(min(num_axes, 4)))
        left = (stick_axes[0], stick_axes[1])
        right = (stick_axes[2], stick_axes[3]) if len(stick_axes) >= 4 else None
        return (left, right)

    def _compute_triggers(self, joy: Any) -> list[int]:
        """Return trigger axis indices (axes resting far from 0), ascending."""
        try:
            num_axes = joy.get_numaxes()
        except pygame.error:
            return []
        try:
            rest = [joy.get_axis(i) for i in range(num_axes)]
        except pygame.error:
            return []
        return [i for i, v in enumerate(rest) if abs(v) > self.TRIGGER_REST_THRESHOLD]

    def _refresh_layout(self) -> None:
        joy = self.active()
        if joy is None:
            self._left_axes = self._right_axes = None
            self._active_triggers = []
            self._left_stick_active = self._right_stick_active = False
            self._layout_id = None
            return
        joy_id = joy.get_instance_id()
        if self._layout_id != joy_id:
            self._left_stick_active = self._right_stick_active = False
            layout = self._axis_layout.get(joy_id)
            if layout is None:
                layout = self._compute_layout(joy)
                self._axis_layout[joy_id] = layout
            self._left_axes, self._right_axes = layout
            triggers = self._trigger_layout.get(joy_id)
            if triggers is None:
                triggers = self._compute_triggers(joy)
                self._trigger_layout[joy_id] = triggers
            self._active_triggers = triggers
            self._layout_id = joy_id

    def poll_axes(self, emit_trigger_commands: bool = True) -> None:
        """Read left/right sticks for the active device into cached floats.

        Cheap by design: no dict/list allocation, just float writes. The public
        ``left_vec``/``right_vec`` rebuild their tuple only when the deadzone
        crossing changes. ``emit_trigger_commands`` is disabled while handling
        button events so controllers that also report bumpers as axes do not fire
        stale trigger bindings in addition to the remapped button command.
        """
        if not self.enabled:
            self._reset_axes()
            self._trigger_pressed.clear()
            self._queued_commands.clear()
            self._queued_trigger_slots.clear()
            self._queued_release_commands.clear()
            return
        joy = self.active()
        if joy is None:
            self._reset_axes()
            return
        self._refresh_layout()
        lx = ly = 0.0
        if self._left_axes is not None:
            ax, ay = self._left_axes
            try:
                lx = joy.get_axis(ax)
                ly = joy.get_axis(ay)
            except pygame.error:
                lx = ly = 0.0
        # SDL reports stick-down as +Y and stick-up as -Y, which already
        # matches the keyboard arrow intent (DOWN = +dy, UP = -dy) used by
        # the movement/aim code, so no Y inversion is needed.
        lx, ly, self._left_stick_active = self._apply_stick_deadzone(
            lx, ly, self._left_stick_active
        )
        rx = ry = 0.0
        if self._right_axes is not None:
            ax, ay = self._right_axes
            try:
                rx = joy.get_axis(ax)
                ry = joy.get_axis(ay)
            except pygame.error:
                rx = ry = 0.0
        rx, ry, self._right_stick_active = self._apply_stick_deadzone(
            rx, ry, self._right_stick_active
        )
        self._left_x = lx
        self._left_y = ly
        self._right_x = rx
        self._right_y = ry
        self._refresh_vecs()
        self._poll_triggers(joy, emit_trigger_commands)
        self._poll_stick_nav()

    def _reset_axes(self) -> None:
        self._left_stick_active = self._right_stick_active = False
        self._stick_nav_active = False
        self._queued_stick_commands.clear()
        if self._left_x or self._left_y or self._right_x or self._right_y:
            self._left_x = self._left_y = self._right_x = self._right_y = 0.0
            self._refresh_vecs()

    def _refresh_vecs(self) -> None:
        left = (self._left_x, self._left_y)
        right = (self._right_x, self._right_y)
        if left != self._left_vec:
            self._left_vec = left
        if right != self._right_vec:
            self._right_vec = right

    def _poll_triggers(self, joy: Any, emit_commands: bool = True) -> None:
        """Detect rising-edge trigger presses and queue their commands.

        Triggers are analog axes, so we treat them as buttons by thresholding.
        Only a fresh press (rising edge) emits a command, mirroring a key press.
        When ``emit_commands`` is false we still update pressed state, which
        prevents button-like bumper axes from emitting a stale trigger command on
        the following frame.
        """
        if not self._active_triggers:
            return
        for slot, axis in enumerate(self._active_triggers):
            try:
                value = joy.get_axis(axis)
            except pygame.error:
                continue
            pressed = value > TRIGGER_PRESS_THRESHOLD
            was_pressed = self._trigger_pressed.get(axis, False)
            if pressed and not was_pressed:
                if emit_commands:
                    self._queued_trigger_slots.append(slot)
                    if (
                        len(self.trigger_commands) > slot
                        and self.trigger_commands[slot]
                    ):
                        self._queued_commands.append(self.trigger_commands[slot])
            elif was_pressed and not pressed:
                if (
                    len(self.trigger_commands) > slot
                    and self.trigger_commands[slot]
                ):
                    self._queued_release_commands.append(
                        self.trigger_commands[slot]
                    )
            self._trigger_pressed[axis] = pressed

    def drain_trigger_commands(self) -> list[str]:
        """Return and clear commands queued by trigger presses this frame."""
        if not self._queued_commands:
            return []
        cmds = self._queued_commands
        self._queued_commands = []
        return cmds

    def drain_trigger_releases(self) -> list[str]:
        """Return and clear commands whose trigger was released this frame."""
        if not self._queued_release_commands:
            return []
        cmds = self._queued_release_commands
        self._queued_release_commands = []
        return cmds

    def drain_trigger_slots(self) -> list[int]:
        """Return and clear trigger slots pressed this frame for remapping UI."""
        if not self._queued_trigger_slots:
            return []
        slots = self._queued_trigger_slots
        self._queued_trigger_slots = []
        return slots

    def _poll_stick_nav(self) -> None:
        """Detect rising-edge left-stick deflections for menu navigation.

        Emits one directional command (UP/DOWN/LEFT/RIGHT) per push using the
        dominant axis. Hysteresis: the stick must return below RELEASE before
        another command fires. This is the analog-stick equivalent of
        ``hat_commands`` for D-pad navigation, and runs inside ``poll_axes``
        so it shares the same per-frame timing.
        """
        lx, ly = self._left_x, self._left_y
        magnitude = (lx * lx + ly * ly) ** 0.5
        if not self._stick_nav_active:
            if magnitude >= STICK_NAV_ACTIVATION:
                self._stick_nav_active = True
                if abs(lx) > abs(ly):
                    self._queued_stick_commands.append(
                        Command.RIGHT if lx > 0 else Command.LEFT
                    )
                else:
                    self._queued_stick_commands.append(
                        Command.DOWN if ly > 0 else Command.UP
                    )
        elif magnitude < STICK_NAV_RELEASE:
            self._stick_nav_active = False

    def drain_stick_commands(self) -> list[str]:
        """Return and clear directional commands queued by stick deflections."""
        if not self._queued_stick_commands:
            return []
        cmds = self._queued_stick_commands
        self._queued_stick_commands = []
        return cmds

    def _apply_stick_deadzone(
        self, x: float, y: float, was_active: bool
    ) -> tuple[float, float, bool]:
        """Apply radial scaling with frame-stable activation hysteresis."""
        mag = (x * x + y * y) ** 0.5
        threshold = self.DEADZONE_RELEASE if was_active else self.DEADZONE_ACTIVATION
        if mag <= threshold:
            return 0.0, 0.0, False

        if mag < self.DEADZONE_ACTIVATION:
            # Interpolate the latched band from zero at release to the legacy
            # radial curve at activation. This keeps the vector nonzero until a
            # real release while preserving the established scaling above it.
            activation_magnitude = (
                (self.DEADZONE_ACTIVATION - self.DEADZONE)
                / (1.0 - self.DEADZONE)
            )
            scaled_magnitude = activation_magnitude * (
                (mag - self.DEADZONE_RELEASE)
                / (self.DEADZONE_ACTIVATION - self.DEADZONE_RELEASE)
            )
        else:
            scaled_magnitude = min(
                1.0, (mag - self.DEADZONE) / (1.0 - self.DEADZONE)
            )
        scale = scaled_magnitude / mag
        return x * scale, y * scale, True

    def _apply_deadzone(self, x: float, y: float) -> tuple[float, float]:
        # Preserve the original stateless helper behavior for compatibility.
        mag = (x * x + y * y) ** 0.5
        if mag <= self.DEADZONE:
            return 0.0, 0.0
        scale = min(1.0, (mag - self.DEADZONE) / (1.0 - self.DEADZONE)) / mag
        return x * scale, y * scale

    def left_vec(self) -> tuple[float, float]:
        return self._left_vec

    def right_vec(self) -> tuple[float, float]:
        return self._right_vec


def hat_commands(event: pygame.event.Event) -> Iterable[str]:
    """Translate a JOYHATMOTION event into directional commands."""
    try:
        hx, hy = event.value
    except (TypeError, ValueError):
        return ()
    cmds: list[str] = []
    if hx > 0:
        cmds.append(Command.RIGHT)
    elif hx < 0:
        cmds.append(Command.LEFT)
    if hy > 0:
        cmds.append(Command.UP)
    elif hy < 0:
        cmds.append(Command.DOWN)
    return cmds


class InputMixin:
    """Game mixin hosting the controller manager and unified command dispatch.

    ``Game.handle_events`` feeds raw controller events here; this mixin
    translates them to commands and routes them through ``_dispatch_command``,
    which mirrors the existing keyboard menu-navigation semantics so both input
    methods behave identically across every navigable menu.
    """

    # Options menu row order (matches MenuOptionsMixin.draw_options_menu).
    # Grouped: Display (0-5), Controls (6-7), Audio (8-9), Lights (10-11),
    # Multiplayer (12-14, schema-8 server endpoint), Diagnostics (desktop
    # only), Back (last). The perf-overlay row is desktop only, so the total
    # count and the Back index depend on mobile_mode.
    # 4.9.20: options row indices are now properties so they can shift when the
    # fullscreen row is hidden on Steam Deck. On the Deck the game always runs
    # fullscreen at the panel's native resolution, so the toggle is removed
    # from the options menu and all subsequent rows shift down by 1. Mobile
    # keeps its render-quality row (a different concept) and is unaffected.
    # 4.9.25: desktop (off-Deck) gains a render-resolution row at index 1; it
    # is hidden on mobile (its quality row covers this) and on the Deck
    # (panel-native), shifting later rows by _options_render_row_offset().

    def _options_skip_fullscreen(self) -> bool:
        """True when fullscreen and UI-scale rows should be hidden (Steam Deck)."""
        return is_steam_deck() and not getattr(self, "mobile_mode", False)

    def _options_skip_render_resolution(self) -> bool:
        """True when the desktop render-resolution row is hidden.

        Mobile caps its physical surface through its own render-quality row
        (the repurposed fullscreen slot) and the Deck always renders panel
        native, so the row exists only on regular desktop.
        """
        return getattr(self, "mobile_mode", False) or self._options_skip_fullscreen()

    def _options_render_row_offset(self) -> int:
        # +1 shift for every row below the desktop render-resolution row.
        return 0 if self._options_skip_render_resolution() else 1

    @property
    def OPTIONS_ROW_FULLSCREEN(self) -> int:
        # Not rendered on Deck; returns -1 so it never matches a cursor index.
        return -1 if self._options_skip_fullscreen() else 0

    @property
    def OPTIONS_ROW_RENDER_RES(self) -> int:
        # Desktop only (see _options_skip_render_resolution): -1 elsewhere.
        return -1 if self._options_skip_render_resolution() else 1

    @property
    def OPTIONS_ROW_DIFFICULTY(self) -> int:
        return (
            0
            if self._options_skip_fullscreen()
            else 1 + self._options_render_row_offset()
        )

    @property
    def OPTIONS_ROW_UI_SCALE(self) -> int:
        # Hidden on Deck (same as fullscreen): returns -1 so it never matches.
        return (
            -1
            if self._options_skip_fullscreen()
            else 2 + self._options_render_row_offset()
        )

    @property
    def OPTIONS_ROW_GRAPHICS(self) -> int:
        return (
            1
            if self._options_skip_fullscreen()
            else 3 + self._options_render_row_offset()
        )

    @property
    def OPTIONS_ROW_FRAME_RATE(self) -> int:
        return (
            2
            if self._options_skip_fullscreen()
            else 4 + self._options_render_row_offset()
        )

    @property
    def OPTIONS_ROW_CONTROLS(self) -> int:
        return (
            3
            if self._options_skip_fullscreen()
            else 5 + self._options_render_row_offset()
        )

    @property
    def OPTIONS_ROW_CONTROLLER(self) -> int:
        return (
            4
            if self._options_skip_fullscreen()
            else 6 + self._options_render_row_offset()
        )

    @property
    def OPTIONS_ROW_AUDIO(self) -> int:
        return (
            5
            if self._options_skip_fullscreen()
            else 7 + self._options_render_row_offset()
        )

    # 4.11.0: the music row (formerly between Audio and Lighting) is parked
    # until real tracks exist; every row below it shifted up one.

    @property
    def OPTIONS_ROW_LIGHTING(self) -> int:
        return (
            6
            if self._options_skip_fullscreen()
            else 8 + self._options_render_row_offset()
        )

    @property
    def OPTIONS_ROW_LIGHTING_DETAIL(self) -> int:
        return (
            7
            if self._options_skip_fullscreen()
            else 9 + self._options_render_row_offset()
        )

    @property
    def OPTIONS_ROW_MP_HOST(self) -> int:
        return (
            8
            if self._options_skip_fullscreen()
            else 10 + self._options_render_row_offset()
        )

    @property
    def OPTIONS_ROW_MP_PORT(self) -> int:
        return (
            9
            if self._options_skip_fullscreen()
            else 11 + self._options_render_row_offset()
        )

    @property
    def OPTIONS_ROW_MP_TLS(self) -> int:
        return (
            10
            if self._options_skip_fullscreen()
            else 12 + self._options_render_row_offset()
        )

    @property
    def OPTIONS_ROW_PERF_OVERLAY(self) -> int:
        return (
            11
            if self._options_skip_fullscreen()
            else 13 + self._options_render_row_offset()
        )

    @property
    def OPTIONS_ROW_COUNT(self) -> int:
        # 14 rows on mobile (no perf-overlay or render-resolution), 16 on
        # desktop (render-resolution added in 4.9.25). On Steam Deck the
        # fullscreen, render-resolution, and UI-scale rows are removed.
        count = 14 if getattr(self, "mobile_mode", False) else 15
        count += self._options_render_row_offset()
        if self._options_skip_fullscreen():
            count -= 2
        return count

    @property
    def OPTIONS_ROW_BACK(self) -> int:
        return self.OPTIONS_ROW_COUNT - 1

    def init_input(self) -> None:
        self.input = ControllerManager(
            last_guid=getattr(self, "last_controller_guid", ""),
            enabled=getattr(self, "controller_enabled", True),
            ignore_motion_sensors=getattr(self, "mobile_mode", False),
        )
        self.input.initialize()
        self.gamepad_mapping = normalize_gamepad_mapping(
            getattr(self, "gamepad_mapping", None)
        )
        triggers = self.gamepad_mapping.get("triggers", list(TRIGGER_COMMANDS))
        self.input.trigger_commands = (
            list(triggers) if isinstance(triggers, list) else list(TRIGGER_COMMANDS)
        )
        self.controls_cursor = 0
        self.controls_capture_command: str | None = None
        self.aim_input_mode = "controller" if is_steam_deck() else "mouse"
        # Only persist a detected device on first run (no prior preference).
        # If the player's last-used pad is not currently connected we keep the
        # saved GUID so it reclaims active when it hot-plugs back in.
        if not self.last_controller_guid and self.input.active_guid():
            self.last_controller_guid = self.input.active_guid()
        # Options menu cursor for unified arrow/gamepad navigation. -1 means
        # no row focused (legacy direct-key usage stays untouched).
        self.options_cursor = 0
        self.options_scroll = 0
        # Cutscene choice highlight shared by keyboard and gamepad navigation.
        self.cutscene_cursor = 0
        # 4.8.8 desktop mouse menus: last (context, row, time) left click, for
        # the double-click confirm on selection-preview lists.
        self._menu_mouse_last_click: tuple[str, int, float] | None = None

    def poll_menu_axes(self) -> None:
        """Per-frame axis handling for every non-playing state.

        A method rather than inline loop code so tests can step exactly what the
        loop steps. The bug this replaced was capture logic sitting in
        ``Game.update()`` behind a ``state == "controls"`` check -- unreachable,
        because ``update()`` only runs while playing -- and it survived because
        nothing exercised the real per-frame path.

        Rebinding a trigger has to happen here rather than in
        ``handle_controller_event``: triggers are axes, so there is no
        JOYBUTTONDOWN edge for capture to hang off the way
        ``_assign_gamepad_button`` does.
        """

        capturing = bool(
            self.state == "controls" and self.controls_capture_command
        )
        # Trigger emission stays ON while capturing. The usual
        # emit_trigger_commands=False path clears the queued slots, which is
        # precisely what capture needs to read.
        self.input.poll_axes(emit_trigger_commands=capturing)
        if capturing:
            for slot in self.input.drain_trigger_slots():
                self.assign_gamepad_trigger_slot(slot, self.controls_capture_command)
                break
            # Capture consumes the input: a pull that binds a slot must not also
            # fire the command it displaced, and the stick must not move the
            # cursor mid-capture. The button path blocks navigation the same way.
            self.input.drain_trigger_commands()
            self.input.drain_stick_commands()
            return
        for cmd in self.input.drain_stick_commands():
            self._dispatch_command(cmd)
        self.input.drain_trigger_commands()
        self.input.drain_trigger_releases()

    def _input_context(self) -> str:
        if self.state != "playing":
            return "menu"
        mini_game = getattr(self, "active_mini_game", None)
        if getattr(mini_game, "phase", "") == "ready":
            # The player's remappable gameplay Interact binding confirms the
            # guide. Once play begins, the modal returns to its menu-like
            # navigation map for D-pad movement and cell selection.
            return "gameplay"
        if mini_game is not None:
            return "mini_game"
        if self.active_cutscene is not None or self.story_intro_pending:
            return "cutscene"
        if self.shop_open or self.inventory_open or self.character_menu_open:
            return "menu"
        return "gameplay"

    # --- Controller event bridge ----------------------------------------

    def handle_controller_event(self, event: pygame.event.Event) -> bool:
        """Process a joystick event. Returns True if it was consumed here."""
        if event.type == pygame.JOYDEVICEADDED or event.type == pygame.JOYDEVICEREMOVED:
            self.input.handle_device_event(event)
            if event.type == pygame.JOYDEVICEADDED and self.input.active_guid():
                self.last_controller_guid = self.input.active_guid()
                self.save_options()
            return True
        if not self.input.enabled and event.type in (
            pygame.JOYAXISMOTION,
            pygame.JOYBALLMOTION,
            pygame.JOYHATMOTION,
            pygame.JOYBUTTONUP,
            pygame.JOYBUTTONDOWN,
        ):
            return True
        if event.type == pygame.JOYBUTTONDOWN:
            # Pressing a button on a gamepad makes it the active device so the
            # last-used controller sticks across multi-device setups.
            self.aim_input_mode = "controller"
            if event.joy in self.input._joysticks:
                joy = self.input._joysticks[event.joy]
                self.input._active_id = event.joy
                self.input._last_guid = self.input._guid(joy)
                self.last_controller_guid = self.input._last_guid
            log_joystick_button(self.input, event.joy, event.button)

            # D-pad buttons (11-14) are directional in every context and cannot
            # be rebound. Resolve them before polling axes: a Deck D-pad press
            # must produce exactly one navigation/zoom action, not an additional
            # synthetic stick-navigation command.
            dpad_cmd = DPAD_BUTTON_COMMANDS.get(event.button)
            if dpad_cmd is not None:
                if self.state == "controls" and self.controls_capture_command:
                    return True
                consumed = getattr(self, "_dpad_consumed_this_frame", None)
                if consumed is None:
                    consumed = set()
                    self._dpad_consumed_this_frame = consumed
                if event.button in consumed:
                    return True
                consumed.add(event.button)
                self._dispatch_command(self._dpad_command(dpad_cmd))
                return True

            # Action button events are processed before Game.update() samples
            # axes. Poll once so firing/casting uses the right-stick direction
            # shown by the aim cone. Do not emit trigger commands here: some
            # controllers expose bumpers as both buttons and axes.
            self.input.poll_axes(emit_trigger_commands=False)
            if self.state == "controls" and self.controls_capture_command:
                self._assign_gamepad_button(event.button, self.controls_capture_command)
                return True
            cmd = mapped_joybutton_command(
                event.button,
                self._input_context(),
                self.gamepad_mapping,
                deck_native=self.input.active_controller_is_deck_native(),
            )
            if cmd is not None:
                self._dispatch_command(cmd)
                return True
        if event.type == pygame.JOYBUTTONUP:
            # Hold-to-charge release for a face-button-remapped slot 1. The
            # trigger axes get the same falling edge via drain_trigger_releases.
            if self._input_context() == "gameplay" and not (
                self.state == "controls" and self.controls_capture_command
            ):
                cmd = mapped_joybutton_command(
                    event.button,
                    "gameplay",
                    self.gamepad_mapping,
                    deck_native=self.input.active_controller_is_deck_native(),
                )
                if cmd == Command.ABILITY_1:
                    self.player_big_hit_release()
                    return True
        if event.type == pygame.JOYHATMOTION:
            self.aim_input_mode = "controller"
            if self.state == "controls" and self.controls_capture_command:
                return True
            commands = tuple(hat_commands(event))
            if is_steam_deck():
                # The integrated D-pad can surface as both buttons and a hat.
                # Suppress only directions already handled in this event frame;
                # a hat-only external controller must remain fully functional.
                consumed_buttons = getattr(self, "_dpad_consumed_this_frame", ())
                consumed_commands = {
                    DPAD_BUTTON_COMMANDS[button]
                    for button in consumed_buttons
                    if button in DPAD_BUTTON_COMMANDS
                }
                commands = tuple(
                    cmd for cmd in commands if cmd not in consumed_commands
                )
            for cmd in commands:
                self._dispatch_command(self._dpad_command(cmd))
            return True
        return False

    def _dpad_command(self, direction: str) -> str:
        """What a D-pad direction does in the current context.

        Menus, cutscenes and mini-games keep plain navigation; nothing else can
        move a cursor there. During gameplay the sticks own movement and aim, so
        the D-pad carries the four bindings in DPAD_GAMEPLAY_COMMANDS instead --
        bare directions did nothing in gameplay, which is why the D-pad felt
        dead in-game.

        Shared by the button and hat paths on purpose: the same physical D-pad
        arrives as buttons 11-14 natively and as a hat through Steam Input, and
        the two must not drift apart.
        """

        if getattr(self, "active_mini_game", None) is not None:
            return direction
        if self._input_context() != "gameplay":
            return direction
        return DPAD_GAMEPLAY_COMMANDS.get(direction, direction)

    # --- Unified command dispatch ---------------------------------------

    def _dispatch_command(self, cmd: str) -> bool:
        """Handle a shared command in the current state.

        Returns True if consumed. Mirrors the keyboard menu-navigation
        semantics already present in ``handle_events`` so gamepad and keyboard
        share identical behavior. Gameplay ability commands are only emitted by
        the controller; keyboard abilities keep their dedicated handlers.
        """
        if self.state == "confirm_exit":
            if cmd in (Command.UP, Command.LEFT):
                self.move_exit_confirmation_cursor(-1)
                return True
            if cmd in (Command.DOWN, Command.RIGHT):
                self.move_exit_confirmation_cursor(1)
                return True
            if cmd == Command.CONFIRM:
                self.activate_exit_confirmation_selection()
                return True
            if cmd == Command.BACK:
                self.cancel_exit_confirmation()
                return True
            return False

        # 4.6: while the shared text-entry field is open, gamepad confirm/back
        # map to confirm/cancel and navigation is swallowed (typing owns focus).
        if self.text_input_active():
            if cmd == Command.CONFIRM:
                self.close_text_input(confirm=True)
                return True
            if cmd == Command.BACK:
                self.close_text_input(confirm=False)
                return True
            return True

        if cmd == Command.BACK:
            return self._dispatch_back()

        if self.state == "title":
            return self._dispatch_title(cmd)
        if self.state == "options":
            return self._dispatch_options(cmd)
        if self.state == "chronicle":
            return self._dispatch_chronicle(cmd)
        if self.state == "controls":
            return self._dispatch_controls(cmd)
        if self.state == "about":
            # 4.3.17 WS-G: Up/Down scroll the Open Source Licenses text;
            # confirm/back/left/right return to the title.
            if cmd == Command.UP:
                self.scroll_licenses(-1)
                return True
            if cmd == Command.DOWN:
                self.scroll_licenses(1)
                return True
            if cmd == Command.PAGE_UP:
                page = max(1, int(getattr(self, "_licenses_visible_lines", 3)) - 1)
                self.scroll_licenses(-page)
                return True
            if cmd == Command.PAGE_DOWN:
                page = max(1, int(getattr(self, "_licenses_visible_lines", 3)) - 1)
                self.scroll_licenses(page)
                return True
            if cmd in (
                Command.CONFIRM,
                Command.BACK,
                Command.LEFT,
                Command.RIGHT,
            ):
                self.state = "title"
                return True
            return False
        if self.state == "archetype_select":
            return self._dispatch_archetype(cmd)
        if self.state == "mp_consent":
            return self._dispatch_mp_consent(cmd)
        if self.state == "mp_setup":
            return self._dispatch_mp_setup(cmd)
        if self.state == "mp_lobby":
            return self._dispatch_mp_lobby(cmd)

        if self.state == "playing":
            return self._dispatch_playing(cmd)

        return False

    def _dispatch_chronicle(self, cmd: Command) -> bool:
        if cmd == Command.UP:
            self.move_chronicle_selection(-1)
            return True
        if cmd == Command.DOWN:
            self.move_chronicle_selection(1)
            return True
        if cmd in (Command.CONFIRM, Command.LEFT, Command.RIGHT):
            # Rows are records, not actions; swallow so confirm cannot fall
            # through to gameplay bindings.
            return True
        return False

    def _dispatch_back(self) -> bool:
        if self.state == "playing":
            if getattr(self, "active_mini_game", None) is not None:
                # A mini-game is a short shared story beat. Back is deliberately
                # swallowed so it cannot close the underlying cutscene or open
                # the exit confirmation while the partner is still playing.
                return True
            if getattr(self, "mobile_hub_open", False):
                self.mobile_hub_open = False
                return True
            if getattr(self, "mobile_mode", False) and self.quest_info_visible:
                self.quest_info_visible = False
                self.story_panel_scroll = 0
                return True
            if self.show_help:
                self.show_help = False
                return True
            if self.shop_open:
                self.close_shop()
                return True
            if self.character_menu_open:
                self.character_menu_open = False
                return True
            if self.inventory_open:
                self.inventory_open = False
                return True
            if self.active_cutscene is not None:
                if self.story_intro_pending:
                    # Back/pause must never commit an irreversible story choice.
                    self.request_exit_confirmation()
                    return True
                self.close_active_cutscene()
                return True
            if self.story_intro_pending:
                self.request_exit_confirmation()
                return True
            self.request_exit_confirmation()
            return True
        if self.state == "title":
            # Mirrors the keyboard Escape binding at the title screen.
            self.request_exit_confirmation()
            return True
        if self.state == "controls":
            if self.controls_capture_command:
                self.controls_capture_command = None
            else:
                self.state = "options"
            return True
        if self.state in ("options", "about", "chronicle"):
            self.state = "title"
            return True
        if self.state in ("dead", "victory"):
            self.show_help = False
            self.inventory_open = False
            self.character_menu_open = False
            self.state = "archetype_select"
            return True
        if self.state == "archetype_select":
            self.state = "title"
            return True
        if self.state == "mp_consent":
            self.mp_consent_exit()
            return True
        if self.state == "mp_setup":
            self.mp_back_from_setup_step()
            return True
        if self.state == "mp_lobby":
            self.mp_leave_lobby()
            return True
        if self.state == "confirm_exit":
            self.cancel_exit_confirmation()
            return True
        return False

    def _dispatch_title(self, cmd: str) -> bool:
        if cmd == Command.UP:
            self.title_selection = self._next_title_selection(-1)
            return True
        if cmd == Command.DOWN:
            self.title_selection = self._next_title_selection(1)
            return True
        if cmd in (Command.LEFT, Command.RIGHT):
            # Title is a vertical list; treat horizontal as vertical for
            # gamepad players who push the stick diagonally.
            direction = 1 if cmd == Command.RIGHT else -1
            self.title_selection = self._next_title_selection(direction)
            return True
        if cmd == Command.CONFIRM:
            self._activate_title_selection()
            return True
        if cmd == Command.INVENTORY:
            # Select Resume if available (mirrors L/R legacy key).
            if self.save_exists():
                self.title_selection = self.TITLE_RESUME_ROW
                self._activate_title_selection()
            return True
        return False

    def _dispatch_mp_consent(self, cmd: str) -> bool:
        if cmd in (Command.UP, Command.DOWN, Command.LEFT, Command.RIGHT):
            self.mp_consent_cursor = (self.mp_consent_cursor + 1) % 2
            return True
        if cmd == Command.CONFIRM:
            if self.mp_consent_cursor == 0:
                self.mp_consent_agree()
            else:
                self.mp_consent_exit()
            return True
        return False

    def _dispatch_mp_setup(self, cmd: str) -> bool:
        step = getattr(self, "mp_setup_step", "name")
        if self.text_input_active():
            if cmd == Command.CONFIRM:
                self.close_text_input(confirm=True)
                return True
            return False
        if step == "role":
            if cmd in (Command.UP, Command.DOWN, Command.LEFT, Command.RIGHT):
                self.mp_setup_role_cursor = (self.mp_setup_role_cursor + 1) % 2
                return True
            if cmd == Command.CONFIRM:
                self.mp_choose_role(self.mp_setup_role_cursor == 0)
                return True
        elif step == "host_code":
            if cmd in (Command.UP, Command.DOWN):
                step_dir = 1 if cmd == Command.DOWN else -1
                self.mp_setup_host_cursor = (
                    int(getattr(self, "mp_setup_host_cursor", 0)) + step_dir
                ) % 2
                return True
            if cmd == Command.CONFIRM:
                self.mp_host_code_activate_selected()
                return True
            if cmd in (Command.NEXT, Command.PREV, Command.TAB):
                self.mp_regenerate_host_code()
                return True
        elif step == "name" and cmd == Command.CONFIRM:
            self.mp_setup_step = "role"
            return True
        elif step == "join_code" and cmd == Command.CONFIRM:
            self.mp_open_join_code_input()
            return True
        return False

    def _dispatch_mp_lobby(self, cmd: str) -> bool:
        session = getattr(self, "mp_session", None)
        ready = bool(session is not None and session.local_ready)
        pending_accept = bool(
            session is not None
            and getattr(session, "role", "") == "host"
            and getattr(session, "partner_pending_accept", False)
        )
        if pending_accept and cmd in (
            Command.UP,
            Command.DOWN,
            Command.LEFT,
            Command.RIGHT,
            Command.PREV,
            Command.NEXT,
        ):
            step = (
                1
                if cmd in (Command.DOWN, Command.RIGHT, Command.NEXT)
                else -1
            )
            self.mp_lobby_cursor = (
                int(getattr(self, "mp_lobby_cursor", 0)) + step
            ) % 2
            return True
        if cmd in (Command.UP, Command.DOWN):
            step = 1 if cmd == Command.DOWN else -1
            self.mp_lobby_cursor = (
                int(getattr(self, "mp_lobby_cursor", 0)) + step
            ) % 2
            return True
        if cmd in (Command.LEFT, Command.PREV) and not ready:
            index = (ARCHETYPES.index(self.selected_archetype) - 1) % len(
                ARCHETYPES
            )
            self.selected_archetype = ARCHETYPES[index]
            return True
        if cmd in (Command.RIGHT, Command.NEXT) and not ready:
            index = (ARCHETYPES.index(self.selected_archetype) + 1) % len(
                ARCHETYPES
            )
            self.selected_archetype = ARCHETYPES[index]
            return True
        if cmd == Command.CONFIRM:
            self.mp_lobby_activate_selected()
            return True
        return False

    def _dispatch_archetype(self, cmd: str) -> bool:
        if cmd in (Command.LEFT, Command.PREV):
            index = (ARCHETYPES.index(self.selected_archetype) - 1) % len(ARCHETYPES)
            self.selected_archetype = ARCHETYPES[index]
            return True
        if cmd in (Command.RIGHT, Command.NEXT):
            index = (ARCHETYPES.index(self.selected_archetype) + 1) % len(ARCHETYPES)
            self.selected_archetype = ARCHETYPES[index]
            return True
        if cmd in (Command.UP, Command.DOWN):
            direction = 1 if cmd == Command.DOWN else -1
            index = (ARCHETYPES.index(self.selected_archetype) + direction) % len(
                ARCHETYPES
            )
            self.selected_archetype = ARCHETYPES[index]
            return True
        if cmd == Command.CONFIRM:
            self.restart(self.selected_archetype)
            return True
        return False

    def _dispatch_options(self, cmd: str) -> bool:
        if cmd == Command.UP:
            self.options_cursor = (self.options_cursor - 1) % self.OPTIONS_ROW_COUNT
            return True
        if cmd == Command.DOWN:
            self.options_cursor = (self.options_cursor + 1) % self.OPTIONS_ROW_COUNT
            return True
        if cmd in (Command.LEFT, Command.RIGHT):
            # On Steam Deck, left/right do nothing in the options menu.
            # Navigate with Up/Down, activate with A (CONFIRM).
            if self._options_skip_fullscreen():
                return True
            self._activate_options_row(self.options_cursor, cmd == Command.RIGHT)
            return True
        if cmd == Command.CONFIRM:
            self._activate_options_row(self.options_cursor, True)
            return True
        return False

    def _activate_options_row(self, row: int, forward: bool = True) -> None:
        if row == self.OPTIONS_ROW_AUDIO:
            self.audio_enabled = not self.audio_enabled
            self.save_options()
        elif row == self.OPTIONS_ROW_FULLSCREEN and not self._options_skip_fullscreen():
            if getattr(self, "mobile_mode", False):
                self.cycle_mobile_render_quality(forward)
                return
            self.fullscreen = not self.fullscreen
            self.screen = self.apply_display_mode()
            self.refresh_automatic_ui_scale()
            self.save_options()
        elif (
            row == self.OPTIONS_ROW_RENDER_RES
            and not self._options_skip_render_resolution()
        ):
            self.cycle_desktop_render_quality(forward)
        elif row == self.OPTIONS_ROW_DIFFICULTY:
            self.cycle_difficulty()
        elif row == self.OPTIONS_ROW_UI_SCALE and not self._options_skip_fullscreen():
            self.cycle_ui_scale(forward)
        elif row == self.OPTIONS_ROW_GRAPHICS:
            self.cycle_graphics_tier(forward)
        elif row == self.OPTIONS_ROW_FRAME_RATE:
            self.cycle_frame_rate_cap(forward)
        elif row == self.OPTIONS_ROW_CONTROLLER:
            self.controller_enabled = not self.controller_enabled
            self.input.set_enabled(self.controller_enabled)
            self.save_options()
        elif row == self.OPTIONS_ROW_LIGHTING:
            self._lighting_enabled = not self._lighting_enabled
            self.save_options()
        elif row == self.OPTIONS_ROW_LIGHTING_DETAIL:
            self._lighting_normal_maps = not self._lighting_normal_maps
            self.save_options()
        elif row == self.OPTIONS_ROW_MP_HOST:
            self.open_text_input(
                target="mp_server_host",
                prompt="Multiplayer server host",
                initial=str(getattr(self, "mp_server_host", "")),
                max_length=128,
                help_text="Hostname or IP of a trusted Arch Rogue relay server.",
            )
        elif row == self.OPTIONS_ROW_MP_PORT:
            port = getattr(self, "mp_server_port", 0)
            self.open_text_input(
                target="mp_server_port",
                prompt="Multiplayer server port",
                initial=str(port) if port else "",
                max_length=5,
                charset="0123456789",
                help_text="TCP port 1-65535 (the bundled server defaults to 43666).",
            )
        elif row == self.OPTIONS_ROW_MP_TLS:
            self.mp_server_tls = not bool(getattr(self, "mp_server_tls", True))
            self.save_options()
        elif (
            row == self.OPTIONS_ROW_PERF_OVERLAY
            and not getattr(self, "mobile_mode", False)
        ):
            self.toggle_perf_overlay()
        elif row == self.OPTIONS_ROW_CONTROLS:
            self.state = "controls"
            self.controls_cursor = 0
            self.controls_capture_command = None
        elif row == self.OPTIONS_ROW_BACK:
            self.state = "title"

    def _dispatch_controls(self, cmd: str) -> bool:
        if self.controls_capture_command:
            if cmd == Command.BACK:
                self.controls_capture_command = None
                return True
            return True
        count = len(REMAPPABLE_GAMEPAD_COMMANDS)
        if cmd == Command.UP:
            self.controls_cursor = (self.controls_cursor - 1) % count
            return True
        if cmd == Command.DOWN:
            self.controls_cursor = (self.controls_cursor + 1) % count
            return True
        if cmd in (Command.LEFT, Command.RIGHT):
            step = -1 if cmd == Command.LEFT else 1
            self.controls_cursor = (self.controls_cursor + step) % count
            return True
        if cmd == Command.CONFIRM:
            self.controls_capture_command = REMAPPABLE_GAMEPAD_COMMANDS[
                self.controls_cursor
            ]
            return True
        return False

    # ------------------------------------------------------------------
    # 4.8.8 desktop mouse menus. Hovering a menu row moves the selection
    # highlight and a left click activates it, reusing the render-published
    # hitboxes that mobile taps already consume (`_title_row_rects`,
    # `_menu_row_rects`, ...). Selection-preview lists — archetype select,
    # inventory, shop — activate on double click only, so a stray click can
    # never fire an irreversible confirm (starting a run, spending gold).
    # Keyboard, controller, and touch input paths are untouched; both
    # handlers are desktop-only (the game.py callers gate on
    # ``not mobile_mode`` because mobile overlay rects live in safe-area
    # coordinates that raw display positions would miss).

    MENU_MOUSE_DOUBLE_CLICK_SECONDS = 0.45

    def _menu_mouse_double_clicked(self, context: str, index: int) -> bool:
        now = time.monotonic()
        previous = getattr(self, "_menu_mouse_last_click", None)
        self._menu_mouse_last_click = (context, index, now)
        if (
            previous is not None
            and previous[0] == context
            and previous[1] == index
            and now - previous[2] <= self.MENU_MOUSE_DOUBLE_CLICK_SECONDS
        ):
            self._menu_mouse_last_click = None
            return True
        return False

    def handle_menu_mouse_motion(self, pos: tuple[int, int]) -> bool:
        """Move the active menu's selection to the row under the mouse.

        Returns True when the current context is a pointer-navigable menu
        (whether or not a row is under the cursor), so the caller skips the
        gameplay aim/hover handling; False hands the event back. The
        highlight simply follows the hover — keyboard and controller
        navigation continue from wherever the mouse last pointed.
        """
        if self.text_input_active():
            return False
        context = self.mobile_input_context()
        if context == "mini_game":
            state = getattr(self, "active_mini_game", None)
            if getattr(state, "phase", "") == "ready":
                return True
            index = self._rect_index(
                getattr(self, "_mini_game_cell_rects", ()), pos
            )
            if index is not None:
                self.mini_game_cursor = index
            # The full-screen modal owns even empty space around its board.
            return True
        if context == "title":
            index = self._rect_index(self._title_row_rects, pos)
            if index is not None and self._title_row_enabled(index):
                self.title_selection = index
            return True
        if context == "chronicle":
            index = self._rect_index(self._chronicle_row_rects, pos)
            if index is not None:
                start = int(
                    getattr(self, "_chronicle_visible_range", (0, 0))[0]
                )
                self.chronicle_selection = start + index
            return True
        if context == "options":
            index = self._rect_index(self._menu_row_rects, pos)
            if index is not None:
                start = int(getattr(self, "_options_visible_range", (0, 0))[0])
                self.options_cursor = min(
                    self.OPTIONS_ROW_COUNT - 1, start + index
                )
            return True
        if context == "controls":
            if not self.controls_capture_command:
                index = self._rect_index(self._controls_gamepad_row_rects, pos)
                if index is not None and index < len(
                    REMAPPABLE_GAMEPAD_COMMANDS
                ):
                    self.controls_cursor = index
            return True
        if context == "archetype_select":
            index = self._rect_index(self._menu_row_rects, pos)
            if index is not None and index < len(ARCHETYPES):
                self.selected_archetype = ARCHETYPES[index]
            return True
        if context == "confirm_exit":
            index = self._rect_index(self._menu_row_rects, pos)
            if index is not None and index < self.EXIT_CONFIRMATION_OPTION_COUNT:
                self.exit_confirmation_cursor = index
            return True
        if context == "mp_consent":
            index = self._rect_index(getattr(self, "_mp_row_rects", ()), pos)
            if index is not None and index < 2:
                self.mp_consent_cursor = index
            return True
        if context == "mp_setup":
            index = self._rect_index(getattr(self, "_mp_row_rects", ()), pos)
            if index is not None:
                step = getattr(self, "mp_setup_step", "name")
                if step == "role":
                    self.mp_setup_role_cursor = index % 2
                elif step == "host_code":
                    self.mp_setup_host_cursor = index % 2
            return True
        if context == "mp_lobby":
            # Rows 2/3 are the lobby's action rows (ready/leave, or
            # admit/turn-away while a joiner knocks); the cursor spans them.
            index = self._rect_index(getattr(self, "_mp_row_rects", ()), pos)
            if index in (2, 3):
                self.mp_lobby_cursor = index - 2
            return True
        if context == "cutscene":
            if self.active_cutscene_narration_complete():
                index = self._rect_index(
                    getattr(self, "_cutscene_choice_rects", ()), pos
                )
                if index is not None and index < len(
                    self.active_cutscene_choices()
                ):
                    self.cutscene_cursor = index
            return True
        if context == "story_intro":
            index = self._rect_index(
                getattr(self, "_story_intro_choice_rects", ()), pos
            )
            if index is not None and index < len(
                self.story_relic_choice_options()[:3]
            ):
                self.cutscene_cursor = index
            return True
        if context == "inventory":
            index = self._rect_index(self._inventory_visible_row_rects, pos)
            if index is not None:
                self.set_inventory_selection(self.inventory_scroll + index)
                return True
            for slot, rect in getattr(
                self, "_inventory_equipment_card_rects", ()
            ):
                if isinstance(rect, pygame.Rect) and rect.collidepoint(pos):
                    if self.player.equipment.get(slot) is not None:
                        self.inventory_equipment_focus = slot
                    break
            return True
        if context == "shop":
            index = self._rect_index(self._shop_visible_row_rects, pos)
            if index is not None:
                self.shop_cursor = (
                    int(getattr(self, "_shop_visible_start", 0)) + index
                )
            return True
        # gameplay, character (discipline hover has its own path), quest,
        # help, about, state_overlay: nothing to hover here.
        return False

    def handle_menu_mouse_click(self, pos: tuple[int, int]) -> bool:
        """Activate the menu row under a desktop left click.

        Returns True when the click was consumed by a menu target; False
        lets the caller's later branches (gameplay aim/melee) see it.
        """
        context = self.mobile_input_context()
        if self.text_input_active() and context != "mp_setup":
            # While a text session is live only mp_setup handles clicks
            # (tapping outside the field confirms, mirroring Enter).
            return False
        if context in ("gameplay", "quest"):
            memory_prompt = getattr(self, "_memory_token_prompt_rect", None)
            if (
                isinstance(memory_prompt, pygame.Rect)
                and int(getattr(self.player, "memory_tokens", 0)) > 0
                and memory_prompt.collidepoint(pos)
            ):
                return self._dispatch_command(Command.OPEN_DISCIPLINES)
        if context == "mini_game":
            state = getattr(self, "active_mini_game", None)
            if getattr(state, "phase", "") == "ready":
                ready_rect = getattr(self, "_mini_game_ready_rect", None)
                if isinstance(ready_rect, pygame.Rect) and ready_rect.collidepoint(pos):
                    self.confirm_active_mini_game_ready()
                return True
            index = self._rect_index(
                getattr(self, "_mini_game_cell_rects", ()), pos
            )
            if index is not None:
                self.mini_game_cursor = index
                if getattr(state, "phase", "") == "play":
                    self.activate_mini_game_cell(index)
            # Misses are consumed too; they must never become a melee click
            # against the paused dungeon under a Garden/Soul mini-game.
            return True
        if context == "title":
            index = self._rect_index(self._title_row_rects, pos)
            if index is not None and self._title_row_enabled(index):
                self.title_selection = index
                self._activate_title_selection()
                return True
            return False
        if context == "chronicle":
            index = self._rect_index(self._chronicle_row_rects, pos)
            if index is not None:
                start = int(
                    getattr(self, "_chronicle_visible_range", (0, 0))[0]
                )
                self.chronicle_selection = start + index
            return True
        if context == "options":
            index = self._rect_index(self._menu_row_rects, pos)
            if index is not None:
                start = int(getattr(self, "_options_visible_range", (0, 0))[0])
                self.options_cursor = min(
                    self.OPTIONS_ROW_COUNT - 1, start + index
                )
                self._activate_options_row(self.options_cursor, True)
                return True
            return False
        if context == "controls":
            if self.controls_capture_command:
                return False
            index = self._rect_index(self._controls_gamepad_row_rects, pos)
            if index is not None and index < len(REMAPPABLE_GAMEPAD_COMMANDS):
                self.controls_cursor = index
                self.controls_capture_command = REMAPPABLE_GAMEPAD_COMMANDS[
                    index
                ]
                return True
            return False
        if context == "archetype_select":
            index = self._rect_index(self._menu_row_rects, pos)
            if index is not None and index < len(ARCHETYPES):
                self.selected_archetype = ARCHETYPES[index]
                # Single click previews; only a double click descends, so a
                # stray click can never overwrite an existing run save.
                if self._menu_mouse_double_clicked("archetype", index):
                    self.restart(self.selected_archetype)
                return True
            return False
        if context == "confirm_exit":
            index = self._rect_index(self._menu_row_rects, pos)
            if index is not None and index < self.EXIT_CONFIRMATION_OPTION_COUNT:
                self.exit_confirmation_cursor = index
                self.activate_exit_confirmation_selection()
                return True
            return False
        if context == "cutscene":
            if not self.active_cutscene_narration_complete():
                self.advance_active_cutscene()
                return True
            choices = self.active_cutscene_choices()
            index = self._rect_index(
                getattr(self, "_cutscene_choice_rects", ()), pos
            )
            if index is not None and index < len(choices):
                self.cutscene_cursor = index
                self.choose_active_cutscene_option(index)
                return True
            if not choices:
                self.advance_active_cutscene()
                return True
            return False
        if context == "story_intro":
            index = self._rect_index(
                getattr(self, "_story_intro_choice_rects", ()), pos
            )
            if index is not None and index < len(
                self.story_relic_choice_options()[:3]
            ):
                self.cutscene_cursor = index
                self.choose_story_relic_path(index)
                return True
            return False
        if context == "inventory":
            for mode, rect in getattr(self, "_inventory_sort_mode_rects", ()):
                if isinstance(rect, pygame.Rect) and rect.collidepoint(pos):
                    self.inventory_sort_mode = str(mode)
                    self.sort_inventory()
                    return True
            index = self._rect_index(self._inventory_visible_row_rects, pos)
            if index is not None:
                selected = self.inventory_scroll + index
                self.set_inventory_selection(selected)
                if self._menu_mouse_double_clicked("inventory", selected):
                    self._dispatch_command(Command.CONFIRM)
                return True
            for slot, rect in getattr(
                self, "_inventory_equipment_card_rects", ()
            ):
                if isinstance(rect, pygame.Rect) and rect.collidepoint(pos):
                    if self.player.equipment.get(slot) is not None:
                        self.inventory_equipment_focus = slot
                        return True
                    break
            return False
        if context == "shop":
            mode_index = self._rect_index(
                getattr(self, "_shop_mode_rects", ()), pos
            )
            if mode_index is not None:
                requested_mode = "buy" if mode_index == 0 else "sell"
                if self.shop_mode != requested_mode:
                    self.cycle_shop_mode()
                return True
            index = self._rect_index(self._shop_visible_row_rects, pos)
            if index is not None:
                selected = int(getattr(self, "_shop_visible_start", 0)) + index
                self.shop_cursor = selected
                if self._menu_mouse_double_clicked("shop", selected):
                    self._dispatch_command(Command.CONFIRM)
                return True
            return False
        if context == "character":
            tab_index = self._rect_index(
                getattr(self, "_character_tab_rects", ()), pos
            )
            if tab_index is not None:
                self.character_menu_tab = (
                    "overview" if tab_index == 0 else "disciplines"
                )
                if self.character_menu_tab == "disciplines":
                    self._ensure_discipline_cursor()
                return True
            # Discipline cells keep their existing hover+click path in the
            # gameplay mouse branch.
            return False
        if context == "mp_consent":
            index = self._rect_index(getattr(self, "_mp_row_rects", ()), pos)
            if index == 0:
                self.mp_consent_cursor = 0
                self.mp_consent_agree()
                return True
            if index == 1:
                self.mp_consent_cursor = 1
                self.mp_consent_exit()
                return True
            return False
        if context == "mp_setup":
            return self._handle_mp_setup_tap(pos)
        if context == "mp_lobby":
            return self._handle_mp_lobby_tap(pos)
        if context in ("about", "help", "state_overlay"):
            # Mirrors the mobile tap: a click continues past these screens.
            self._dispatch_command(Command.BACK)
            return True
        return False

    def _gamepad_button_map(self) -> dict[int, str]:
        buttons = self.gamepad_mapping.get("gameplay_buttons", {})
        if not isinstance(buttons, dict):
            buttons = {}
            self.gamepad_mapping["gameplay_buttons"] = buttons
        return buttons

    def _gamepad_trigger_map(self) -> list[str]:
        triggers = self.gamepad_mapping.get("triggers", [])
        if not isinstance(triggers, list):
            triggers = []
            self.gamepad_mapping["triggers"] = triggers
        return triggers

    def _clear_gamepad_command_bindings(
        self,
        command: str,
        keep_button: int | None = None,
        keep_trigger_slot: int | None = None,
    ) -> None:
        buttons = self._gamepad_button_map()
        for mapped_button, mapped_command in list(buttons.items()):
            if mapped_command == command and mapped_button != keep_button:
                del buttons[mapped_button]
        triggers = self._gamepad_trigger_map()
        for index, mapped_command in enumerate(list(triggers)):
            if mapped_command == command and index != keep_trigger_slot:
                triggers[index] = ""

    def _assign_gamepad_button(self, button: int, command: str) -> None:
        buttons = self._gamepad_button_map()
        self._clear_gamepad_command_bindings(command, keep_button=int(button))
        buttons[int(button)] = command
        self.input.trigger_commands = list(self._gamepad_trigger_map())
        self.controls_capture_command = None
        self.save_options()

    def assign_gamepad_trigger_slot(self, slot: int, command: str) -> None:
        triggers = self._gamepad_trigger_map()
        while len(triggers) <= slot:
            triggers.append("")
        self._clear_gamepad_command_bindings(command, keep_trigger_slot=slot)
        triggers[slot] = command
        self.input.trigger_commands = list(triggers)
        self.controls_capture_command = None
        self.save_options()

    def _dispatch_playing(self, cmd: str) -> bool:
        if getattr(self, "active_mini_game", None) is not None:
            return self._dispatch_mini_game(cmd)
        if cmd == Command.MOBILE_MENU and getattr(self, "mobile_mode", False):
            opening = not getattr(self, "mobile_hub_open", False)
            self.mobile_hub_open = opening
            if opening:
                self.quest_info_visible = False
                self.inventory_open = False
                self.character_menu_open = False
                self.show_help = False
                self.close_shop()
            return True
        if cmd == Command.MOBILE_EXIT and getattr(self, "mobile_mode", False):
            self.mobile_hub_open = False
            self.quest_info_visible = False
            self.request_exit_confirmation()
            return True
        if self.show_help:
            if cmd == Command.HELP:
                self.show_help = False
            # Help is modal for input. BACK is handled before state dispatch.
            return True
        # Active cutscenes get the full controller path (D-pad cursor, A confirm,
        # B skip). This includes mandatory story-intro cutscenes.
        if self.active_cutscene is not None:
            return self._dispatch_cutscene(cmd)
        # Fallback for the legacy non-cutscene relic prompt path.
        if self.story_intro_pending:
            choice_count = min(3, len(self.story_relic_choice_options()))
            if choice_count:
                self.cutscene_cursor %= choice_count
            else:
                self.cutscene_cursor = 0
            if cmd in (Command.UP, Command.LEFT):
                if choice_count:
                    self.cutscene_cursor = (self.cutscene_cursor - 1) % choice_count
                return True
            if cmd in (Command.DOWN, Command.RIGHT):
                if choice_count:
                    self.cutscene_cursor = (self.cutscene_cursor + 1) % choice_count
                return True
            if cmd == Command.CONFIRM:
                if choice_count:
                    self.choose_story_relic_path(self.cutscene_cursor)
                return True
            quick_choice = {
                Command.ABILITY_1: 0,
                Command.ABILITY_2: 1,
                Command.ABILITY_3: 2,
            }.get(cmd)
            if quick_choice is not None and quick_choice < choice_count:
                self.cutscene_cursor = quick_choice
                self.choose_story_relic_path(quick_choice)
                return True
            return False

        # Overlay toggle commands work from any playing sub-state so the same
        # button that opens an overlay also closes it (mirrors keyboard I / C).
        if cmd == Command.OPEN_DISCIPLINES:
            if int(getattr(self.player, "memory_tokens", 0)) <= 0:
                return True
            self.character_menu_tab = "disciplines"
            self.character_menu_open = True
            self.inventory_open = False
            self.mobile_hub_open = False
            self.quest_info_visible = False
            self.close_shop()
            self._ensure_discipline_cursor()
            return True
        if cmd in (Command.MAP_ZOOM_IN, Command.MAP_ZOOM_OUT):
            self.adjust_minimap_zoom(1 if cmd == Command.MAP_ZOOM_IN else -1)
            return True
        if cmd == Command.INVENTORY:
            self.inventory_open = not self.inventory_open
            if getattr(self, "mobile_mode", False):
                self.mobile_hub_open = False
                self.quest_info_visible = False
            if self.inventory_open:
                self.character_menu_open = False
                self.close_shop()
            self.clamp_inventory_selection()
            return True
        if cmd == Command.CHARACTER:
            self.character_menu_open = not self.character_menu_open
            if getattr(self, "mobile_mode", False):
                self.mobile_hub_open = False
                self.quest_info_visible = False
            if self.character_menu_open:
                self.inventory_open = False
                self.close_shop()
                if self.character_menu_tab == "disciplines":
                    self._ensure_discipline_cursor()
            return True

        # Overlay sub-menus.
        if self.shop_open:
            return self._dispatch_shop(cmd)
        if self.inventory_open:
            return self._dispatch_inventory(cmd)
        if self.character_menu_open:
            return self._dispatch_character(cmd)

        # Base gameplay.
        return self._dispatch_gameplay(cmd)

    def _dispatch_mini_game(self, cmd: str) -> bool:
        """Navigate and activate the current modal board.

        Every command is consumed while the board is visible. This keeps
        remapped controller abilities and stale HUD touch targets from reaching
        the paused dungeon underneath the cooperative story beat.
        """

        state = getattr(self, "active_mini_game", None)
        if getattr(state, "phase", "") == "ready":
            if cmd == Command.INTERACT:
                self.confirm_active_mini_game_ready()
            return True
        board = getattr(state, "board", ())
        count = len(board) if isinstance(board, (tuple, list)) else 0
        if count <= 0:
            self.mini_game_cursor = 0
            return True

        cursor = int(getattr(self, "mini_game_cursor", 0)) % count
        kind = str(getattr(state, "kind", ""))
        columns = 4 if kind == "soul" and count > 6 else 3
        rows = max(1, (count + columns - 1) // columns)

        if cmd in (Command.LEFT, Command.RIGHT):
            row = cursor // columns
            row_start = row * columns
            row_count = min(columns, count - row_start)
            offset = cursor - row_start
            step = -1 if cmd == Command.LEFT else 1
            cursor = row_start + (offset + step) % row_count
        elif cmd in (Command.UP, Command.DOWN):
            column = cursor % columns
            row = cursor // columns
            step = -1 if cmd == Command.UP else 1
            for distance in range(1, rows + 1):
                target_row = (row + step * distance) % rows
                row_start = target_row * columns
                row_count = min(columns, count - row_start)
                if row_count > 0:
                    cursor = row_start + min(column, row_count - 1)
                    break
        elif cmd in (Command.TAB, Command.NEXT):
            cursor = (cursor + 1) % count
        elif cmd in (Command.TAB_PREV, Command.PREV):
            cursor = (cursor - 1) % count
        elif cmd == Command.CONFIRM:
            if getattr(state, "phase", "") == "play":
                self.activate_mini_game_cell(cursor)
        self.mini_game_cursor = cursor
        return True

    def _dispatch_cutscene(self, cmd: str) -> bool:
        choices = self.active_cutscene_choices()[:9]
        choice_count = len(choices)
        if choice_count:
            self.cutscene_cursor %= choice_count
        else:
            self.cutscene_cursor = 0
        # D-pad / stick navigates the choice highlight; A confirms it once the
        # narration is fully revealed, otherwise A advances the narration.
        if cmd == Command.UP:
            if choice_count:
                self.cutscene_cursor = (self.cutscene_cursor - 1) % choice_count
            return True
        if cmd == Command.DOWN:
            if choice_count:
                self.cutscene_cursor = (self.cutscene_cursor + 1) % choice_count
            return True
        if cmd in (Command.LEFT, Command.RIGHT):
            if choice_count:
                step = 1 if cmd == Command.RIGHT else -1
                self.cutscene_cursor = (self.cutscene_cursor + step) % choice_count
            return True
        if cmd == Command.PAGE_UP:
            page = max(1, getattr(self, "_cutscene_narration_visible_lines", 3) - 1)
            self.scroll_active_cutscene_narration(-page)
            return True
        if cmd == Command.PAGE_DOWN:
            page = max(1, getattr(self, "_cutscene_narration_visible_lines", 3) - 1)
            self.scroll_active_cutscene_narration(page)
            return True
        if cmd == Command.CONFIRM:
            if not self.active_cutscene_narration_complete():
                self.advance_active_cutscene()
                return True
            if choice_count:
                self.choose_active_cutscene_option(self.cutscene_cursor)
                return True
            self.advance_active_cutscene()
            return True
        # Quick-pick: X/Y/LB/RB map to choices 0-3 (ABILITY_1..4) for fast
        # dialogue on gamepad, mirroring keyboard 1-4.
        quick = {
            Command.ABILITY_1: 0,
            Command.ABILITY_2: 1,
            Command.ABILITY_3: 2,
            Command.ABILITY_4: 3,
            Command.ABILITY_5: 4,
            Command.ABILITY_6: 5,
        }
        if cmd in quick and quick[cmd] < choice_count:
            self.cutscene_cursor = quick[cmd]
            self.choose_active_cutscene_option(self.cutscene_cursor)
            return True
        return False

    def _dispatch_shop(self, cmd: str) -> bool:
        if cmd == Command.UP:
            self.move_shop_selection(-1)
            return True
        if cmd == Command.DOWN:
            self.move_shop_selection(1)
            return True
        if cmd == Command.TAB:
            self.cycle_shop_mode()
            return True
        if cmd == Command.CONFIRM:
            self.transact_shop_selection()
            return True
        return False

    def _dispatch_inventory(self, cmd: str) -> bool:
        if cmd in (Command.LEFT, Command.RIGHT):
            self.cycle_equipment_focus(forward=cmd == Command.RIGHT)
            return True
        if self.focused_equipped_item() is not None and cmd in (
            Command.CONFIRM,
            Command.DROP,
        ):
            # The equipped panel is read-only: acting returns to the bag
            # instead of using/dropping the bag selection by surprise.
            self.inventory_equipment_focus = None
            return True
        if cmd == Command.UP:
            self.move_inventory_selection(-1)
            return True
        if cmd == Command.DOWN:
            self.move_inventory_selection(1)
            return True
        if cmd == Command.PAGE_UP:
            self.move_inventory_selection(-5)
            return True
        if cmd == Command.PAGE_DOWN:
            self.move_inventory_selection(5)
            return True
        if cmd == Command.HOME:
            self.set_inventory_selection(0)
            return True
        if cmd == Command.END:
            self.set_inventory_selection(len(self.player.inventory) - 1)
            return True
        if cmd in (Command.TAB, Command.TAB_PREV):
            self.cycle_inventory_sort_mode(forward=cmd == Command.TAB)
            return True
        if cmd == Command.CONFIRM:
            self.use_selected_inventory_slot()
            return True
        if cmd == Command.DROP:
            self.drop_selected_inventory_slot()
            return True
        # Y button (HELP) doubles as drop in the inventory overlay since help
        # has no use there; keeps a one-button drop available on gamepad.
        if cmd == Command.HELP:
            self.drop_selected_inventory_slot()
            return True
        return False

    def _dispatch_character(self, cmd: str) -> bool:
        if cmd in (Command.TAB, Command.TAB_PREV, Command.NEXT, Command.PREV):
            forward = cmd in (Command.TAB, Command.NEXT)
            self.character_menu_tab = (
                "disciplines" if self.character_menu_tab == "overview" else "overview"
            ) if forward else (
                "overview" if self.character_menu_tab == "disciplines" else "disciplines"
            )
            if self.character_menu_tab == "disciplines":
                self._ensure_discipline_cursor()
            return True
        if self.character_menu_tab != "disciplines":
            if cmd in (Command.LEFT, Command.RIGHT):
                self.character_menu_tab = "disciplines"
                self._ensure_discipline_cursor()
                return True
            return False
        if cmd in (Command.UP, Command.DOWN, Command.LEFT, Command.RIGHT):
            self._move_discipline_cursor(cmd)
            return True
        if cmd == Command.CONFIRM:
            self._activate_discipline_cursor()
            return True
        return False

    def _discipline_grid(self):
        from .content import discipline_paths_for_archetype, disciplines_for_archetype

        archetype = self.player.class_name
        paths = list(discipline_paths_for_archetype(archetype))
        nodes = list(disciplines_for_archetype(archetype))
        path_index = {path: index for index, path in enumerate(paths)}
        by_key = {node.key: node for node in nodes}
        by_pos = {(node.degree, path_index.get(node.path, 0)): node for node in nodes}
        ordered = sorted(
            nodes, key=lambda node: (node.degree, path_index.get(node.path, 0))
        )
        return paths, by_key, by_pos, ordered

    def _ensure_discipline_cursor(self) -> None:
        paths, by_key, _by_pos, ordered = self._discipline_grid()
        del paths
        current = self.character_menu_hovered_node
        if current in by_key:
            return
        available = self.available_disciplines()
        if available:
            self.character_menu_hovered_node = available[0].key
        elif ordered:
            self.character_menu_hovered_node = ordered[0].key
        else:
            self.character_menu_hovered_node = None

    def _move_discipline_cursor(self, cmd: str) -> None:
        paths, by_key, by_pos, ordered = self._discipline_grid()
        if not ordered or not paths:
            self.character_menu_hovered_node = None
            return
        self._ensure_discipline_cursor()
        current = by_key.get(self.character_menu_hovered_node or "") or ordered[0]
        path_index = {path: index for index, path in enumerate(paths)}
        degree = current.degree
        col = path_index.get(current.path, 0)
        max_degree = max(node.degree for node in ordered)
        max_col = len(paths) - 1
        if cmd == Command.LEFT:
            col = max(0, col - 1)
        elif cmd == Command.RIGHT:
            col = min(max_col, col + 1)
        elif cmd == Command.UP:
            degree = max(1, degree - 1)
        elif cmd == Command.DOWN:
            degree = min(max_degree, degree + 1)
        target = by_pos.get((degree, col))
        if target is None:
            # Sparse-grid fallback: choose nearest discipline to the desired grid cell.
            target = min(
                ordered,
                key=lambda node: (
                    abs(node.degree - degree) + abs(path_index.get(node.path, 0) - col),
                    node.degree,
                    path_index.get(node.path, 0),
                ),
            )
        self.character_menu_hovered_node = target.key

    def _activate_discipline_cursor(self) -> None:
        self._ensure_discipline_cursor()
        if self.character_menu_hovered_node:
            self.choose_discipline(self.character_menu_hovered_node)

    def _sync_action_aim(self) -> None:
        """Refresh facing for the active controller, touch, or desktop source."""
        if getattr(self, "aim_input_mode", "mouse") == "touch":
            point = self.active_mobile_world_touch()
            if point is not None:
                self.face_player_toward_screen_point(*point)
            return
        rx, ry = self.input.right_vec()
        if rx or ry or getattr(self, "aim_input_mode", "mouse") == "controller":
            if rx or ry:
                length = (rx * rx + ry * ry) ** 0.5
                if length > 0.0:
                    self.player.facing_x = rx / length
                    self.player.facing_y = ry / length
            self.snap_controller_aim_to_enemy()
            return
        self.update_player_aim()

    def _sync_controller_action_aim(self) -> None:
        """Compatibility alias retained for external controller integrations."""
        self._sync_action_aim()

    def _dispatch_gameplay(self, cmd: str) -> bool:
        if cmd == Command.INTERACT:
            self.interact()
            return True
        if cmd == Command.QUEST:
            if getattr(self, "mobile_mode", False):
                self.mobile_hub_open = False
                self.quest_info_visible = not self.quest_info_visible
                self.story_panel_scroll = 0
            else:
                self.toggle_quest_info_visibility()
            return True
        if cmd == Command.HELP:
            self.show_help = not self.show_help
            return True
        if cmd in (Command.PAGE_UP, Command.PAGE_DOWN) and self.quest_info_visible:
            page = max(1, getattr(self, "_story_panel_visible_lines", 3) - 1)
            self.scroll_story_panel(-page if cmd == Command.PAGE_UP else page)
            return True
        if cmd == Command.ABILITY_1:
            self._sync_action_aim()
            self.player_big_hit()
            return True
        if cmd == Command.ABILITY_2:
            self._sync_action_aim()
            self.player_cast_bolt()
            return True
        if cmd == Command.ABILITY_3:
            self._sync_action_aim()
            self.player_cast_class_skill()
            return True
        if cmd == Command.ABILITY_4:
            self._sync_action_aim()
            self.player_dash()
            return True
        if cmd == Command.ABILITY_5:
            self.use_first_potion()
            return True
        if cmd == Command.ABILITY_6:
            self.use_first_mana_potion()
            return True
        return False
