# pyright: reportAttributeAccessIssue=false
"""Input abstraction for Arch Rogue (milestone 3.9).

This module is the single source of truth for translating raw keyboard, mouse,
and gamepad input into a small set of shared *commands* (move, aim, ability,
interact, navigate, confirm, back, tab). ``Game.handle_events`` keeps its
existing flow; controller events and the unified menu navigation path route
through the helpers here so keyboard and gamepad behave consistently.

The hot-path pieces (per-frame axis polling) are allocation-free: the manager
caches float attributes and only rebuilds the returned tuples when the deadzone
state flips, so the run loop stays cheap.
"""

from __future__ import annotations

from typing import Any, Iterable

import pygame

from .content import ARCHETYPES


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
    ABILITY_1 = "ability_1"
    ABILITY_2 = "ability_2"
    ABILITY_3 = "ability_3"
    ABILITY_4 = "ability_4"
    ABILITY_5 = "ability_5"
    ABILITY_6 = "ability_6"

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
    4: Command.TAB_PREV,
    5: Command.TAB,
    6: Command.INVENTORY,
    7: Command.CHARACTER,
}

# Base gameplay button map. The face/shoulder buttons drive the six combat
# actions (mirroring keyboard 1-6), B opens the pause/exit confirmation, and
# Back/Start open the inventory and character sheet. D-pad movement is handled
# by hat events and the left stick by axis polling.
GAMEPLAY_BUTTON_COMMANDS: dict[int, str] = {
    0: Command.ABILITY_1,  # A  -> melee (key 1)
    2: Command.ABILITY_2,  # X  -> bolt  (key 2)
    3: Command.ABILITY_3,  # Y  -> nova  (key 3)
    4: Command.ABILITY_5,  # LB -> potion (key 5)
    5: Command.ABILITY_6,  # RB -> mana potion (key 6)
    1: Command.BACK,  # B  -> pause / exit
    6: Command.INVENTORY,  # Back/Select
    7: Command.CHARACTER,  # Start
}

# Cutscene button map: A advances narration / selects the highlighted choice,
# B skips, and X/Y/LB/RB quick-pick choices 0-3 so dialogue stays fast on pad.
CUTSCENE_BUTTON_COMMANDS: dict[int, str] = {
    0: Command.CONFIRM,  # A  -> advance / select highlighted
    1: Command.BACK,  # B  -> skip / close
    2: Command.ABILITY_1,  # X  -> choice 0
    3: Command.ABILITY_2,  # Y  -> choice 1
    4: Command.ABILITY_3,  # LB -> choice 2
    5: Command.ABILITY_4,  # RB -> choice 3
}

# Trigger axes (read via JOYAXISMOTION / polling) map to the two actions that
# do not fit on the face buttons: LT = dash (key 4), RT = interact (key E).
# Order is by ascending trigger axis index (LT before RT on common pads).
TRIGGER_COMMANDS: tuple[str, ...] = (Command.ABILITY_4, Command.INTERACT)
TRIGGER_PRESS_THRESHOLD = 0.25

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


def default_gamepad_mapping() -> dict[str, dict[int, str] | list[str]]:
    return {
        "menu_buttons": dict(DEFAULT_JOY_BUTTON_COMMANDS),
        "gameplay_buttons": dict(GAMEPLAY_BUTTON_COMMANDS),
        "cutscene_buttons": dict(CUTSCENE_BUTTON_COMMANDS),
        "triggers": list(TRIGGER_COMMANDS),
    }


def normalize_gamepad_mapping(data: object) -> dict[str, dict[int, str] | list[str]]:
    mapping = default_gamepad_mapping()
    if not isinstance(data, dict):
        return mapping
    valid = set(REMAPPABLE_GAMEPAD_COMMANDS) | {
        Command.CONFIRM,
        Command.HELP,
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


def mapped_joybutton_command(
    button: int, context: str, mapping: dict[str, dict[int, str] | list[str]]
) -> str | None:
    gameplay_buttons = mapping.get("gameplay_buttons", {})
    if isinstance(gameplay_buttons, dict):
        cmd = gameplay_buttons.get(button)
        if cmd == Command.BACK:
            return Command.BACK
        if context == "gameplay":
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

    DEADZONE = 0.24
    # Axes whose rest value is far from zero (|v| > 0.5) are treated as
    # triggers and skipped when locating the analog sticks. This handles the
    # common raw-joystick layouts (Xbox: axes 2/5 are triggers; Stadia/PS:
    # axes 4/5 are triggers) without relying on the SDL controller DB.
    TRIGGER_REST_THRESHOLD = 0.5

    def __init__(self, last_guid: str = "", enabled: bool = True) -> None:
        self.enabled = enabled
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
        self.trigger_commands = list(TRIGGER_COMMANDS)
        # Cached axis state. Updated in-place by poll_axes(); the returned
        # tuples are only rebuilt when the deadzone crossing changes so the
        # per-frame hot path avoids allocations.
        self._left_x = 0.0
        self._left_y = 0.0
        self._right_x = 0.0
        self._right_y = 0.0
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

    def _add_device(self, device_index: int) -> Any | None:
        try:
            joy = pygame.joystick.Joystick(device_index)
        except pygame.error:
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
        try:
            return joy.get_name() or "Gamepad"
        except pygame.error:
            return "Gamepad"

    def active_guid(self) -> str:
        joy = self.active()
        return self._guid(joy) if joy is not None else ""

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        if not enabled:
            self._reset_axes()

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
            self._layout_id = None
            return
        joy_id = joy.get_instance_id()
        if self._layout_id != joy_id:
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
        lx, ly = self._apply_deadzone(lx, ly)
        rx = ry = 0.0
        if self._right_axes is not None:
            ax, ay = self._right_axes
            try:
                rx = joy.get_axis(ax)
                ry = joy.get_axis(ay)
            except pygame.error:
                rx = ry = 0.0
            rx, ry = self._apply_deadzone(rx, ry)
        self._left_x = lx
        self._left_y = ly
        self._right_x = rx
        self._right_y = ry
        self._refresh_vecs()
        self._poll_triggers(joy, emit_trigger_commands)

    def _reset_axes(self) -> None:
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
            if pressed and not self._trigger_pressed.get(axis, False):
                if emit_commands:
                    self._queued_trigger_slots.append(slot)
                    if (
                        len(self.trigger_commands) > slot
                        and self.trigger_commands[slot]
                    ):
                        self._queued_commands.append(self.trigger_commands[slot])
            self._trigger_pressed[axis] = pressed

    def drain_trigger_commands(self) -> list[str]:
        """Return and clear commands queued by trigger presses this frame."""
        if not self._queued_commands:
            return []
        cmds = self._queued_commands
        self._queued_commands = []
        return cmds

    def drain_trigger_slots(self) -> list[int]:
        """Return and clear trigger slots pressed this frame for remapping UI."""
        if not self._queued_trigger_slots:
            return []
        slots = self._queued_trigger_slots
        self._queued_trigger_slots = []
        return slots

    def _apply_deadzone(self, x: float, y: float) -> tuple[float, float]:
        # Radial deadzone: drop the whole stick if inside the circle, then
        # rescale the surviving magnitude so the active range is full 0..1.
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
    OPTIONS_ROW_COUNT = 8
    OPTIONS_ROW_AUDIO = 0
    OPTIONS_ROW_MUSIC = 1
    OPTIONS_ROW_FULLSCREEN = 2
    OPTIONS_ROW_DIFFICULTY = 3
    OPTIONS_ROW_UI_SCALE = 4
    OPTIONS_ROW_CONTROLS = 5
    OPTIONS_ROW_CONTROLLER = 6
    OPTIONS_ROW_BACK = 7

    def init_input(self) -> None:
        self.input = ControllerManager(
            last_guid=getattr(self, "last_controller_guid", ""),
            enabled=getattr(self, "controller_enabled", True),
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
        self.aim_input_mode = "mouse"
        # Only persist a detected device on first run (no prior preference).
        # If the player's last-used pad is not currently connected we keep the
        # saved GUID so it reclaims active when it hot-plugs back in.
        if not self.last_controller_guid and self.input.active_guid():
            self.last_controller_guid = self.input.active_guid()
        # Options menu cursor for unified arrow/gamepad navigation. -1 means
        # no row focused (legacy direct-key usage stays untouched).
        self.options_cursor = 0
        # Cutscene choice highlight index for gamepad navigation.
        self.cutscene_cursor = 0

    def _input_context(self) -> str:
        if self.state != "playing":
            return "menu"
        if self.active_cutscene is not None:
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
        if event.type == pygame.JOYBUTTONDOWN:
            # Pressing a button on a gamepad makes it the active device so the
            # last-used controller sticks across multi-device setups.
            self.aim_input_mode = "controller"
            if event.joy in self.input._joysticks:
                joy = self.input._joysticks[event.joy]
                self.input._active_id = event.joy
                self.input._last_guid = self.input._guid(joy)
                self.last_controller_guid = self.input._last_guid
            # Button events are processed before Game.update() samples axes for
            # the frame. Poll once here so firing/casting uses the right-stick
            # direction the player sees in the aim cone, not last frame's aim.
            # Do not emit trigger commands from this poll: some controllers expose
            # bumpers as both buttons and axes, and remapped bumpers must not also
            # fire the trigger action.
            self.input.poll_axes(emit_trigger_commands=False)
            if self.state == "controls" and self.controls_capture_command:
                self._assign_gamepad_button(event.button, self.controls_capture_command)
                return True
            cmd = mapped_joybutton_command(
                event.button, self._input_context(), self.gamepad_mapping
            )
            if cmd is not None:
                self._dispatch_command(cmd)
                return True
        if event.type == pygame.JOYHATMOTION:
            self.aim_input_mode = "controller"
            if self.state == "controls" and self.controls_capture_command:
                return True
            for cmd in hat_commands(event):
                self._dispatch_command(cmd)
            return True
        return False

    # --- Unified command dispatch ---------------------------------------

    def _dispatch_command(self, cmd: str) -> bool:
        """Handle a shared command in the current state.

        Returns True if consumed. Mirrors the keyboard menu-navigation
        semantics already present in ``handle_events`` so gamepad and keyboard
        share identical behavior. Gameplay ability commands are only emitted by
        the controller; keyboard abilities keep their dedicated handlers.
        """
        if self.state == "confirm_exit":
            if cmd == Command.CONFIRM:
                self.confirm_exit()
                return True
            if cmd == Command.BACK:
                self.cancel_exit_confirmation()
                return True
            return False

        if cmd == Command.BACK:
            return self._dispatch_back()

        if self.state == "title":
            return self._dispatch_title(cmd)
        if self.state == "options":
            return self._dispatch_options(cmd)
        if self.state == "controls":
            return self._dispatch_controls(cmd)
        if self.state == "about":
            if cmd in (
                Command.CONFIRM,
                Command.UP,
                Command.DOWN,
                Command.LEFT,
                Command.RIGHT,
            ):
                self.state = "title"
                return True
            return False
        if self.state == "archetype_select":
            return self._dispatch_archetype(cmd)

        if self.state == "playing":
            return self._dispatch_playing(cmd)

        return False

    def _dispatch_back(self) -> bool:
        if self.state == "playing":
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
                    choices = self.active_cutscene_choices()
                    if choices:
                        index = max(0, min(self.cutscene_cursor, len(choices) - 1))
                        self.choose_active_cutscene_option(index)
                    return True
                self.close_active_cutscene()
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
        if self.state in ("options", "about"):
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
        elif row == self.OPTIONS_ROW_MUSIC:
            self.music_enabled = not self.music_enabled
            self.sync_music()
            self.save_options()
        elif row == self.OPTIONS_ROW_FULLSCREEN:
            if not self.fullscreen:
                self.windowed_size = self.screen.get_size()
            self.fullscreen = not self.fullscreen
            self.screen = self.apply_display_mode()
            self.save_options()
        elif row == self.OPTIONS_ROW_DIFFICULTY:
            self.cycle_difficulty()
        elif row == self.OPTIONS_ROW_UI_SCALE:
            self.ui_scale = max(1, min(4, self.ui_scale + (1 if forward else -1)))
            self.rebuild_fonts()
            self.save_options()
        elif row == self.OPTIONS_ROW_CONTROLLER:
            self.controller_enabled = not self.controller_enabled
            self.input.set_enabled(self.controller_enabled)
            self.save_options()
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
        # Active cutscenes get the full controller path (D-pad cursor, A confirm,
        # B skip). This includes mandatory story-intro cutscenes.
        if self.active_cutscene is not None:
            return self._dispatch_cutscene(cmd)
        # Fallback for the legacy non-cutscene relic prompt path.
        if self.story_intro_pending:
            if cmd == Command.ABILITY_1:
                self.choose_story_relic_path(0)
                return True
            if cmd == Command.ABILITY_2:
                self.choose_story_relic_path(1)
                return True
            if cmd == Command.ABILITY_3:
                self.choose_story_relic_path(2)
                return True
            return False

        # Overlay toggle commands work from any playing sub-state so the same
        # button that opens an overlay also closes it (mirrors keyboard I / C).
        if cmd == Command.INVENTORY:
            self.inventory_open = not self.inventory_open
            if self.inventory_open:
                self.character_menu_open = False
                self.close_shop()
            self.clamp_inventory_selection()
            return True
        if cmd == Command.CHARACTER:
            self.character_menu_open = not self.character_menu_open
            if self.character_menu_open:
                self.inventory_open = False
                self.close_shop()
                if self.character_menu_tab == "skill_tree":
                    self._ensure_skill_tree_cursor()
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

    def _dispatch_cutscene(self, cmd: str) -> bool:
        choices = self.active_cutscene_choices()
        choice_count = len(choices)
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
            self.choose_active_cutscene_option(quick[cmd])
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
        if cmd == Command.TAB:
            self.cycle_inventory_sort_mode()
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
            self.character_menu_tab = (
                "skill_tree" if self.character_menu_tab == "overview" else "overview"
            )
            if self.character_menu_tab == "skill_tree":
                self._ensure_skill_tree_cursor()
            return True
        if self.character_menu_tab != "skill_tree":
            if cmd in (Command.LEFT, Command.RIGHT):
                self.character_menu_tab = "skill_tree"
                self._ensure_skill_tree_cursor()
                return True
            return False
        if cmd in (Command.UP, Command.DOWN, Command.LEFT, Command.RIGHT):
            self._move_skill_tree_cursor(cmd)
            return True
        if cmd == Command.CONFIRM:
            self._activate_skill_tree_cursor()
            return True
        return False

    def _skill_tree_grid(self):
        from .content import skill_branches_for_archetype, skill_nodes_for_archetype

        archetype = self.player.class_name
        branches = list(skill_branches_for_archetype(archetype))
        nodes = list(skill_nodes_for_archetype(archetype))
        branch_index = {branch: index for index, branch in enumerate(branches)}
        by_key = {node.key: node for node in nodes}
        by_pos = {(node.tier, branch_index.get(node.branch, 0)): node for node in nodes}
        ordered = sorted(
            nodes, key=lambda node: (node.tier, branch_index.get(node.branch, 0))
        )
        return branches, by_key, by_pos, ordered

    def _ensure_skill_tree_cursor(self) -> None:
        branches, by_key, _by_pos, ordered = self._skill_tree_grid()
        del branches
        current = self.character_menu_hovered_node
        if current in by_key:
            return
        available = self.available_skill_choices()
        if available:
            self.character_menu_hovered_node = available[0].key
        elif ordered:
            self.character_menu_hovered_node = ordered[0].key
        else:
            self.character_menu_hovered_node = None

    def _move_skill_tree_cursor(self, cmd: str) -> None:
        branches, by_key, by_pos, ordered = self._skill_tree_grid()
        if not ordered or not branches:
            self.character_menu_hovered_node = None
            return
        self._ensure_skill_tree_cursor()
        current = by_key.get(self.character_menu_hovered_node or "") or ordered[0]
        branch_index = {branch: index for index, branch in enumerate(branches)}
        tier = current.tier
        col = branch_index.get(current.branch, 0)
        max_tier = max(node.tier for node in ordered)
        max_col = len(branches) - 1
        if cmd == Command.LEFT:
            col = max(0, col - 1)
        elif cmd == Command.RIGHT:
            col = min(max_col, col + 1)
        elif cmd == Command.UP:
            tier = max(1, tier - 1)
        elif cmd == Command.DOWN:
            tier = min(max_tier, tier + 1)
        target = by_pos.get((tier, col))
        if target is None:
            # Sparse-tree fallback: choose nearest node to the desired grid cell.
            target = min(
                ordered,
                key=lambda node: (
                    abs(node.tier - tier) + abs(branch_index.get(node.branch, 0) - col),
                    node.tier,
                    branch_index.get(node.branch, 0),
                ),
            )
        self.character_menu_hovered_node = target.key

    def _activate_skill_tree_cursor(self) -> None:
        self._ensure_skill_tree_cursor()
        if self.character_menu_hovered_node:
            self.choose_skill_upgrade(self.character_menu_hovered_node)

    def _sync_controller_action_aim(self) -> None:
        """Refresh facing from right stick only when it is actively aiming.

        Controller actions must launch in the direction of the visible aim cone.
        The cone is stored in `player.facing_x/y`; falling back to mouse aim here
        would silently rotate the shot away from what gamepad players see.
        """
        rx, ry = self.input.right_vec()
        if not (rx or ry):
            return
        length = (rx * rx + ry * ry) ** 0.5
        if length > 0.0:
            self.player.facing_x = rx / length
            self.player.facing_y = ry / length

    def _dispatch_gameplay(self, cmd: str) -> bool:
        if cmd == Command.INTERACT:
            self.interact()
            return True
        if cmd == Command.QUEST:
            self.toggle_quest_info_visibility()
            return True
        if cmd == Command.HELP:
            self.show_help = not self.show_help
            return True
        if cmd == Command.ABILITY_1:
            self._sync_controller_action_aim()
            self.player_melee_attack()
            return True
        if cmd == Command.ABILITY_2:
            self._sync_controller_action_aim()
            self.player_cast_bolt()
            return True
        if cmd == Command.ABILITY_3:
            self._sync_controller_action_aim()
            self.player_cast_nova()
            return True
        if cmd == Command.ABILITY_4:
            self._sync_controller_action_aim()
            self.player_dash()
            return True
        if cmd == Command.ABILITY_5:
            self.use_first_potion()
            return True
        if cmd == Command.ABILITY_6:
            self.use_first_mana_potion()
            return True
        return False
