from __future__ import annotations

import json
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame  # noqa: E402

from arch_rogue.content import ARCHETYPES  # noqa: E402
from arch_rogue.game import Game  # noqa: E402
from arch_rogue.options import (  # noqa: E402
    MOBILE_RENDER_QUALITY_NATIVE,
    ui_scale_from_display_scale,
)
from arch_rogue.input import (  # noqa: E402
    Command,
    ControllerManager,
    add_missing_deck_gameplay_aliases,
    default_gamepad_mapping,
    hat_commands,
    key_command,
    mapped_joybutton_command,
    normalize_gamepad_mapping,
    serialize_gamepad_mapping,
)
from arch_rogue.models import Enemy, Tile  # noqa: E402
from arch_rogue.story import ActiveQuestCutscene  # noqa: E402


class FakeJoystick:
    """A minimal stand-in for pygame.joystick.Joystick for deterministic tests."""

    def __init__(
        self,
        instance_id: int,
        guid: str = "fake-guid",
        name: str = "Fake Pad",
        num_axes: int = 6,
        axes_rest: tuple[float, ...] | None = None,
        num_buttons: int = 12,
        num_hats: int = 1,
    ) -> None:
        self._id = instance_id
        self._guid = guid
        self._name = name
        self._num_axes = num_axes
        self._num_buttons = num_buttons
        self._num_hats = num_hats
        rest = list(axes_rest or ([0.0] * num_axes))
        # Triggers default-rest at -1.0 on the last two axes to mimic real pads.
        if axes_rest is None and num_axes >= 6:
            rest[-2] = -1.0
            rest[-1] = -1.0
        self._axes = list(rest)
        self.initialized = True
        self.quit_called = False

    def get_instance_id(self) -> int:
        return self._id

    def get_guid(self) -> str:
        return self._guid

    def get_name(self) -> str:
        return self._name

    def get_numaxes(self) -> int:
        return self._num_axes

    def get_numbuttons(self) -> int:
        return self._num_buttons

    def get_numhats(self) -> int:
        return self._num_hats

    def get_axis(self, index: int) -> float:
        if 0 <= index < len(self._axes):
            return self._axes[index]
        return 0.0

    def set_axis(self, index: int, value: float) -> None:
        self._axes[index] = value

    def init(self) -> None:  # compatibility shim
        self.initialized = True

    def quit(self) -> None:  # compatibility shim
        self.quit_called = True


def make_controller_manager(fake: FakeJoystick | None = None) -> ControllerManager:
    """Build a ControllerManager with no real-device init and one optional fake pad."""
    mgr = ControllerManager(last_guid="", enabled=True)
    if fake is not None:
        mgr._joysticks[fake.get_instance_id()] = fake
        mgr._axis_layout[fake.get_instance_id()] = mgr._compute_layout(fake)
        mgr._trigger_layout[fake.get_instance_id()] = mgr._compute_triggers(fake)
        mgr._active_id = fake.get_instance_id()
    return mgr


class InputMappingTests(unittest.TestCase):
    def test_default_gamepad_mapping_matches_shipped_profile(self) -> None:
        expected = {
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
        with patch("arch_rogue.input.is_steam_deck", return_value=False):
            mapping = default_gamepad_mapping()
        self.assertEqual(mapping["gameplay_buttons"], expected)
        self.assertEqual(mapping["triggers"], [Command.ABILITY_1, Command.ABILITY_4])
        self.assertEqual(
            serialize_gamepad_mapping(mapping)["gameplay_buttons"],
            {str(button): command for button, command in expected.items()},
        )
        for button, command in expected.items():
            self.assertEqual(
                mapped_joybutton_command(button, "gameplay", mapping), command
            )
        # 4.9.20: button 11 (D-pad Up) is no longer in the gameplay map — it's
        # converted to UP by DPAD_BUTTON_COMMANDS before the button map is
        # consulted. The button map itself returns None for it.
        self.assertIsNone(mapped_joybutton_command(11, "menu", mapping))
        self.assertIsNone(mapped_joybutton_command(11, "gameplay", mapping))
        self.assertEqual(
            mapped_joybutton_command(0, "menu", mapping), Command.CONFIRM
        )
        self.assertEqual(mapped_joybutton_command(1, "menu", mapping), Command.BACK)
        self.assertEqual(mapped_joybutton_command(4, "menu", mapping), Command.BACK)
        self.assertIsNone(mapped_joybutton_command(9, "menu", mapping))

    def test_deck_defaults_are_scoped_and_survive_persistence(self) -> None:
        with patch("arch_rogue.input.is_steam_deck", return_value=True):
            mapping = default_gamepad_mapping()
            self.assertEqual(mapping["menu_buttons"][9], Command.TAB)
            self.assertEqual(mapping["menu_buttons"][10], Command.TAB_PREV)
            self.assertEqual(mapping["gameplay_buttons"][9], Command.ABILITY_6)
            self.assertEqual(
                mapping["gameplay_buttons"][16], Command.OPEN_DISCIPLINES
            )

            restored = normalize_gamepad_mapping(
                serialize_gamepad_mapping(mapping)
            )
            self.assertEqual(restored["gameplay_buttons"][9], Command.ABILITY_6)
            self.assertEqual(
                restored["gameplay_buttons"][16], Command.OPEN_DISCIPLINES
            )

    def test_existing_deck_profile_gains_unoccupied_fixed_aliases(self) -> None:
        old_profile = {
            "gameplay_buttons": {
                "0": Command.INTERACT,
                "5": Command.ABILITY_6,
                "15": Command.CHARACTER,
            },
            "triggers": [Command.ABILITY_1, Command.ABILITY_4],
        }
        mapping = normalize_gamepad_mapping(old_profile)
        add_missing_deck_gameplay_aliases(mapping)
        self.assertEqual(mapping["gameplay_buttons"][9], Command.ABILITY_6)
        self.assertEqual(
            mapping["gameplay_buttons"][16], Command.OPEN_DISCIPLINES
        )

    def test_key_command_navigation_keys(self) -> None:
        self.assertEqual(key_command(pygame.K_UP, 0), Command.UP)
        self.assertEqual(key_command(pygame.K_DOWN, 0), Command.DOWN)
        self.assertEqual(key_command(pygame.K_LEFT, 0), Command.LEFT)
        self.assertEqual(key_command(pygame.K_RIGHT, 0), Command.RIGHT)
        self.assertEqual(key_command(pygame.K_RETURN, 0), Command.CONFIRM)
        self.assertEqual(key_command(pygame.K_ESCAPE, 0), Command.BACK)
        self.assertEqual(key_command(pygame.K_BACKSPACE, 0), Command.BACK)
        self.assertEqual(key_command(pygame.K_TAB, 0), Command.TAB)

    def test_custom_gameplay_button_map_overrides_default(self) -> None:
        mapping = normalize_gamepad_mapping(
            {"gameplay_buttons": {"0": Command.ABILITY_2, "2": Command.ABILITY_1}}
        )
        self.assertEqual(
            mapped_joybutton_command(0, "gameplay", mapping), Command.ABILITY_2
        )
        self.assertEqual(
            mapped_joybutton_command(2, "gameplay", mapping), Command.ABILITY_1
        )
        self.assertEqual(mapped_joybutton_command(0, "menu", mapping), Command.CONFIRM)

    def test_hat_commands_translate_dpad(self) -> None:
        up = pygame.event.Event(
            pygame.JOYHATMOTION, joy=0, hat=0, value=(0, 1)
        )
        self.assertEqual(list(hat_commands(up)), [Command.UP])
        down = pygame.event.Event(
            pygame.JOYHATMOTION, joy=0, hat=0, value=(0, -1)
        )
        self.assertEqual(list(hat_commands(down)), [Command.DOWN])
        diagonal = pygame.event.Event(
            pygame.JOYHATMOTION, joy=0, hat=0, value=(-1, 1)
        )
        commands = list(hat_commands(diagonal))
        self.assertIn(Command.LEFT, commands)
        self.assertIn(Command.UP, commands)
        center = pygame.event.Event(
            pygame.JOYHATMOTION, joy=0, hat=0, value=(0, 0)
        )
        self.assertEqual(list(hat_commands(center)), [])


class ControllerManagerTests(unittest.TestCase):
    def test_deadzone_zeros_small_deflection(self) -> None:
        fake = FakeJoystick(0, num_axes=4, axes_rest=(0, 0, 0, 0))
        mgr = make_controller_manager(fake)
        fake.set_axis(0, 0.1)  # inside the 0.24 deadzone
        fake.set_axis(1, 0.1)
        mgr.poll_axes()
        self.assertEqual(mgr.left_vec(), (0.0, 0.0))

    def test_deadzone_noise_around_old_threshold_does_not_activate(self) -> None:
        fake = FakeJoystick(0, num_axes=4, axes_rest=(0, 0, 0, 0))
        mgr = make_controller_manager(fake)
        noise = (mgr.DEADZONE - 0.01, mgr.DEADZONE + 0.01) * 4

        for frame, value in enumerate(noise):
            with self.subTest(frame=frame, value=value):
                fake.set_axis(0, value)
                mgr.poll_axes()
                self.assertEqual(mgr.left_vec(), (0.0, 0.0))

    def test_deadzone_deliberate_activation_preserves_radial_scaling(self) -> None:
        fake = FakeJoystick(0, num_axes=4, axes_rest=(0, 0, 0, 0))
        mgr = make_controller_manager(fake)
        fake.set_axis(0, 0.3)
        fake.set_axis(1, 0.4)

        mgr.poll_axes()

        expected_magnitude = (0.5 - mgr.DEADZONE) / (1.0 - mgr.DEADZONE)
        lx, ly = mgr.left_vec()
        self.assertAlmostEqual(lx, 0.6 * expected_magnitude)
        self.assertAlmostEqual(ly, 0.8 * expected_magnitude)

    def test_deadzone_active_stick_releases_at_neutral_boundary(self) -> None:
        fake = FakeJoystick(0, num_axes=4, axes_rest=(0, 0, 0, 0))
        mgr = make_controller_manager(fake)
        fake.set_axis(0, mgr.DEADZONE_ACTIVATION + 0.05)
        mgr.poll_axes()
        self.assertNotEqual(mgr.left_vec(), (0.0, 0.0))

        for frame, value in enumerate((0.25, 0.27, 0.25)):
            with self.subTest(frame=frame, value=value):
                fake.set_axis(0, value)
                mgr.poll_axes()
                self.assertGreater(math.hypot(*mgr.left_vec()), 0.0)

        # Returning to the original neutral range must release the latch so a
        # controller resting near 0.23 cannot cause permanent movement/aim drift.
        fake.set_axis(0, mgr.DEADZONE_RELEASE - 0.01)
        mgr.poll_axes()
        self.assertEqual(mgr.left_vec(), (0.0, 0.0))

        fake.set_axis(0, mgr.DEADZONE + 0.01)
        mgr.poll_axes()
        self.assertEqual(mgr.left_vec(), (0.0, 0.0))

    def test_hot_plug_add_and_remove(self) -> None:
        mgr = ControllerManager(last_guid="", enabled=True)
        added = pygame.event.Event(pygame.JOYDEVICEADDED, device_index=0)
        # Inject a fake via _add_device by patching the constructor.
        original = pygame.joystick.Joystick
        try:
            pygame.joystick.Joystick = lambda idx: FakeJoystick(idx)  # type: ignore[misc]
            mgr.handle_device_event(added)
        finally:
            pygame.joystick.Joystick = original  # type: ignore[misc]
        self.assertTrue(mgr.has_controller())
        active = mgr.active()
        self.assertIsNotNone(active)
        assert active is not None
        active_id = active.get_instance_id()
        removed = pygame.event.Event(
            pygame.JOYDEVICEREMOVED, instance_id=active_id, which=active_id
        )
        mgr.handle_device_event(removed)
        self.assertFalse(mgr.has_controller())

    def test_mobile_filter_rejects_motion_sensor_but_keeps_real_gamepad(self) -> None:
        mgr = ControllerManager(
            last_guid="", enabled=True, ignore_motion_sensors=True
        )
        sensor = FakeJoystick(
            17,
            guid="sensor-guid",
            name="Android Linear Acceleration Sensor",
            num_axes=3,
            num_buttons=0,
            num_hats=0,
        )
        gamepad = FakeJoystick(
            23,
            guid="pad-guid",
            name="8BitDo Pro 2",
            num_axes=6,
        )
        original = pygame.joystick.Joystick
        try:
            pygame.joystick.Joystick = lambda _idx: sensor  # type: ignore[misc]
            self.assertIsNone(mgr._add_device(0))
            pygame.joystick.Joystick = lambda _idx: gamepad  # type: ignore[misc]
            self.assertIs(mgr._add_device(1), gamepad)
        finally:
            pygame.joystick.Joystick = original  # type: ignore[misc]

        self.assertTrue(sensor.quit_called)
        self.assertNotIn(sensor.get_instance_id(), mgr._joysticks)
        self.assertIs(mgr.active(), gamepad)
        self.assertEqual(mgr.active_name(), "8BitDo Pro 2")
        self.assertTrue(mgr.has_controller())

    def test_mobile_filter_preserves_controller_with_gyro_in_its_name(self) -> None:
        mgr = ControllerManager(
            last_guid="", enabled=True, ignore_motion_sensors=True
        )
        gamepad = FakeJoystick(
            29,
            name="Pro Gamepad with Gyro",
            num_buttons=14,
            num_hats=1,
        )
        original = pygame.joystick.Joystick
        try:
            pygame.joystick.Joystick = lambda _idx: gamepad  # type: ignore[misc]
            self.assertIs(mgr._add_device(0), gamepad)
        finally:
            pygame.joystick.Joystick = original  # type: ignore[misc]
        self.assertIs(mgr.active(), gamepad)
        self.assertFalse(gamepad.quit_called)

    def test_desktop_manager_does_not_filter_named_sensor_devices(self) -> None:
        mgr = ControllerManager(
            last_guid="", enabled=True, ignore_motion_sensors=False
        )
        sensor = FakeJoystick(31, name="Android Accelerometer", num_axes=3)
        original = pygame.joystick.Joystick
        try:
            pygame.joystick.Joystick = lambda _idx: sensor  # type: ignore[misc]
            self.assertIs(mgr._add_device(0), sensor)
        finally:
            pygame.joystick.Joystick = original  # type: ignore[misc]
        self.assertFalse(sensor.quit_called)
        self.assertIs(mgr.active(), sensor)

    def test_disabled_manager_never_reads_axes_and_clears_pending_input(self) -> None:
        fake = FakeJoystick(0, num_axes=4, axes_rest=(0, 0, 0, 0))
        mgr = make_controller_manager(fake)
        fake.set_axis(0, 0.8)
        mgr.poll_axes()
        self.assertNotEqual(mgr.left_vec(), (0.0, 0.0))
        mgr._queued_commands.append(Command.ABILITY_1)
        mgr._queued_trigger_slots.append(0)

        mgr.set_enabled(False)
        with patch.object(fake, "get_axis", wraps=fake.get_axis) as get_axis:
            mgr.poll_axes()

        get_axis.assert_not_called()
        self.assertEqual(mgr.left_vec(), (0.0, 0.0))
        self.assertEqual(mgr.right_vec(), (0.0, 0.0))
        self.assertEqual(mgr.drain_trigger_commands(), [])
        self.assertEqual(mgr.drain_trigger_slots(), [])


def make_game(tmpdir: str) -> Game:
    game = Game(
        screen_size=(820, 540),
        headless=True,
        save_path=Path(tmpdir) / "run.json",
    )
    game.options_path = Path(tmpdir) / "options.json"
    game.meta_progress = game.default_meta_progress()
    game.run_history = []
    game.rng.seed(2323)
    game.restart(ARCHETYPES[0])
    if game.story_intro_pending:
        game.choose_story_relic_path(0)
    game.active_cutscene = None
    return game


def attach_fake_controller(game: Game, instance_id: int = 123) -> FakeJoystick:
    fake = FakeJoystick(instance_id, num_axes=4, axes_rest=(0, 0, 0, 0))
    game.input._joysticks[fake.get_instance_id()] = fake
    game.input._axis_layout[fake.get_instance_id()] = game.input._compute_layout(fake)
    game.input._trigger_layout[fake.get_instance_id()] = game.input._compute_triggers(
        fake
    )
    game.input._active_id = fake.get_instance_id()
    game.input._layout_id = None
    return fake


def open_floor_band_to_target(game: Game, target_x: float, target_y: float) -> None:
    min_x = max(0, int(min(game.player.x, target_x)) - 1)
    max_x = min(len(game.dungeon.tiles) - 1, int(max(game.player.x, target_x)) + 2)
    min_y = max(0, int(min(game.player.y, target_y)) - 1)
    max_y = min(len(game.dungeon.tiles[0]) - 1, int(max(game.player.y, target_y)) + 2)
    for x in range(min_x, max_x + 1):
        for y in range(min_y, max_y + 1):
            game.dungeon.tiles[x][y] = Tile.FLOOR


def make_target_enemy(x: float, y: float) -> Enemy:
    return Enemy(
        name="Aim Dummy",
        kind="melee",
        x=x,
        y=y,
        max_hp=40,
        hp=40,
        speed=0.0,
        damage=0,
        xp=0,
        attack_range=1.0,
        attack_cooldown=1.0,
    )


class CommandDispatchTests(unittest.TestCase):
    def test_exit_confirmation_cursor_keyboard_and_gamepad(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            with patch.object(game, "save_run", return_value=True) as save_run:
                game.state = "playing"
                game.request_exit_confirmation()
                self.assertEqual(
                    game.exit_confirmation_cursor,
                    game.EXIT_CONFIRMATION_CANCEL,
                )

                pygame.event.clear()
                pygame.event.post(
                    pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0)
                )
                game.handle_events()
                self.assertTrue(game.running)
                self.assertEqual(game.state, "playing")
                save_run.assert_not_called()

                game.request_exit_confirmation()
                pygame.event.post(
                    pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UP, mod=0)
                )
                pygame.event.post(
                    pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0)
                )
                game.handle_events()
                self.assertTrue(game.running)
                self.assertEqual(game.state, "title")
                save_run.assert_called_once_with()

                game.state = "playing"
                game.request_exit_confirmation()
                pygame.event.post(
                    pygame.event.Event(pygame.KEYDOWN, key=pygame.K_e, mod=0)
                )
                game.handle_events()
                self.assertTrue(game.running)
                self.assertEqual(game.state, "playing")
                self.assertEqual(save_run.call_count, 1)

                game.request_exit_confirmation()
                self.assertTrue(game._dispatch_command(Command.CONFIRM))
                self.assertTrue(game.running)
                self.assertEqual(game.state, "playing")

                game.request_exit_confirmation()
                pygame.event.post(
                    pygame.event.Event(pygame.KEYDOWN, key=pygame.K_m, mod=0)
                )
                game.handle_events()
                self.assertEqual(game.state, "title")
                self.assertEqual(save_run.call_count, 2)

                game.state = "playing"
                game.request_exit_confirmation()
                pygame.event.post(
                    pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN, mod=0)
                )
                pygame.event.post(
                    pygame.event.Event(pygame.KEYDOWN, key=pygame.K_e, mod=0)
                )
                game.handle_events()
                self.assertFalse(game.running)
                self.assertEqual(save_run.call_count, 3)

    def test_return_to_main_menu_persists_current_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.player.gold = 987654
            game.request_exit_confirmation()
            game.exit_confirmation_cursor = game.EXIT_CONFIRMATION_MAIN_MENU
            game.activate_exit_confirmation_selection()

            self.assertEqual(game.state, "title")
            saved = json.loads(game.save_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["player"]["gold"], 987654)

    def test_save_failure_keeps_exit_confirmation_open(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            blocked_save = Path(tmpdir) / "blocked-save"
            blocked_save.mkdir()
            game.save_path = blocked_save
            game.request_exit_confirmation()

            game.return_to_main_menu()
            self.assertEqual(game.state, "confirm_exit")
            self.assertTrue(game.running)
            self.assertTrue(game.last_save_error)

            game.confirm_exit()
            self.assertEqual(game.state, "confirm_exit")
            self.assertTrue(game.running)
            self.assertTrue(game.last_save_error)

    def test_title_navigation_and_confirm(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.state = "title"
            # Discard the run save so the Resume row is disabled and arrow nav
            # skips it (mirrors a fresh install).
            game.save_path.unlink(missing_ok=True)
            game.title_selection = 0
            # 5.0.1 rows: 0=One will descend, 1=Two will descend, 2=Resume,
            # 3=Chronicle, 4=Options, 5=About. Down lands on the multiplayer
            # row first.
            game._dispatch_command(Command.DOWN)
            self.assertEqual(game.title_selection, 1)
            # Down again skips the disabled Resume row (no save) -> the
            # Chronicle, then one more reaches Options.
            game._dispatch_command(Command.DOWN)
            self.assertEqual(game.title_selection, 3)
            game._dispatch_command(Command.DOWN)
            self.assertEqual(game.title_selection, 4)
            game._dispatch_command(Command.CONFIRM)
            self.assertEqual(game.state, "options")

    def test_controls_menu_remaps_selected_gamepad_button(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.state = "controls"
            game.controls_cursor = 1  # ability 2 / bolt
            game._dispatch_command(Command.CONFIRM)
            self.assertEqual(game.controls_capture_command, Command.ABILITY_2)
            event = pygame.event.Event(pygame.JOYBUTTONDOWN, joy=999, button=0)
            self.assertTrue(game.handle_controller_event(event))
            self.assertIsNone(game.controls_capture_command)
            self.assertEqual(
                game.gamepad_mapping["gameplay_buttons"][0], Command.ABILITY_2
            )

    def test_disabled_controller_events_are_consumed_without_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.state = "title"
            game.input.set_enabled(False)
            events = (
                pygame.event.Event(
                    pygame.JOYBUTTONDOWN, joy=999, button=0
                ),
                pygame.event.Event(
                    pygame.JOYHATMOTION, joy=999, hat=0, value=(0, -1)
                ),
                pygame.event.Event(
                    pygame.JOYAXISMOTION, joy=999, axis=0, value=1.0
                ),
            )
            with patch.object(game, "_dispatch_command") as dispatch:
                for event in events:
                    with self.subTest(event_type=event.type):
                        self.assertTrue(game.handle_controller_event(event))
            dispatch.assert_not_called()
            self.assertEqual(game.aim_input_mode, "mouse")

    def test_inventory_overlay_navigation_and_use(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            # Put an item in the inventory so there's something to navigate.
            from arch_rogue.models import Item

            game.player.inventory.append(
                Item(
                    name="Torch",
                    slot="potion",
                    rarity="common",
                    x=0.0,
                    y=0.0,
                )
            )
            game.inventory_open = True
            game.inventory_cursor = 0
            game._dispatch_command(Command.DOWN)
            # Single item: cursor clamps to 0.
            self.assertEqual(game.inventory_cursor, 0)
            # Tab cycles sort mode without error.
            before = game.inventory_sort_mode
            game._dispatch_command(Command.TAB)
            self.assertNotEqual(game.inventory_sort_mode, before)
            # Back closes the inventory overlay.
            game._dispatch_command(Command.BACK)
            self.assertFalse(game.inventory_open)



    def test_completed_cutscene_narration_scroll_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            self.assertTrue(game.start_quest_cutscene("story_guest_omen"))
            # 4.9 keeps real narration inside the choice window; scrolling
            # needs deliberately over-budget text.
            assert game.active_cutscene is not None
            game.active_cutscene.context = {
                **game.active_cutscene.context,
                "omen_body": "A test of margins. " * 160,
            }
            game.reveal_active_cutscene_narration()
            game.draw()
            self.assertGreater(game._cutscene_narration_scroll_max, 0)
            bottom = game.cutscene_narration_scroll

            pygame.event.clear()
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_PAGEUP, mod=0))
            game.handle_events()
            self.assertLess(game.cutscene_narration_scroll, bottom)

            game.cutscene_narration_scroll = bottom
            game.cutscene_narration_follow_tail = False
            pygame.event.post(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=1))
            game.handle_events()
            self.assertEqual(game.cutscene_narration_scroll, bottom - 2)

            game.cutscene_narration_scroll = bottom
            game.cutscene_narration_follow_tail = False
            game.input._right_vec = (0.0, -1.0)
            game.update_active_cutscene_scroll_input(0.016)
            self.assertEqual(game.cutscene_narration_scroll, bottom - 2)

            assert game.active_cutscene is not None
            game.active_cutscene.node_elapsed = 0.0
            game.cutscene_narration_scroll = 0
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_PAGEDOWN, mod=0))
            game.handle_events()
            self.assertEqual(game.cutscene_narration_scroll, 0)

    def test_cutscene_cursor_and_confirm_select_story_option(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.story_intro_pending = True
            game.active_cutscene = ActiveQuestCutscene(
                asset_id="story_guest_omen",
                node_id="relic_choice",
                guest_depth=game.current_depth,
                guest_beat_index=0,
                node_elapsed=999.0,
                context=game.quest_cutscene_context(),
            )
            game.cutscene_cursor = 0
            self.assertGreaterEqual(len(game.active_cutscene_choices()), 3)
            game._dispatch_command(Command.DOWN)
            self.assertEqual(game.cutscene_cursor, 1)
            game._dispatch_command(Command.CONFIRM)
            self.assertFalse(game.story_intro_pending)
            self.assertIsNone(game.active_cutscene)

    def test_cutscene_arrow_keys_and_enter_or_e_confirm_cursor(self) -> None:
        for confirm_key in (pygame.K_RETURN, pygame.K_e):
            with self.subTest(confirm_key=confirm_key), tempfile.TemporaryDirectory() as tmpdir:
                game = make_game(tmpdir)
                game.story_intro_pending = True
                game.active_cutscene = ActiveQuestCutscene(
                    asset_id="story_guest_omen",
                    node_id="relic_choice",
                    guest_depth=game.current_depth,
                    guest_beat_index=0,
                    node_elapsed=999.0,
                    context=game.quest_cutscene_context(),
                )
                game.cutscene_cursor = 0
                expected_choice_key = game.active_cutscene_choices()[1].choice_key
                pygame.event.clear()
                pygame.event.post(
                    pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN, mod=0)
                )
                game.handle_events()
                self.assertEqual(game.cutscene_cursor, 1)

                pygame.event.post(
                    pygame.event.Event(pygame.KEYDOWN, key=confirm_key, mod=0)
                )
                game.handle_events()
                self.assertFalse(game.story_intro_pending)
                self.assertIsNone(game.active_cutscene)
                self.assertEqual(game.story_relic_choice_key, expected_choice_key)

    def test_invalid_cutscene_number_keeps_visible_cursor(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.story_intro_pending = True
            game.active_cutscene = ActiveQuestCutscene(
                asset_id="story_guest_omen",
                node_id="relic_choice",
                guest_depth=game.current_depth,
                guest_beat_index=0,
                node_elapsed=999.0,
                context=game.quest_cutscene_context(),
            )
            game.cutscene_cursor = 1
            pygame.event.clear()
            pygame.event.post(
                pygame.event.Event(pygame.KEYDOWN, key=pygame.K_9, mod=0)
            )
            game.handle_events()
            self.assertEqual(game.cutscene_cursor, 1)
            self.assertIsNotNone(game.active_cutscene)

    def test_fallback_story_intro_gamepad_a_confirms_cursor(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            fake = attach_fake_controller(game)
            game.story_intro_pending = True
            game.active_cutscene = None
            game.cutscene_cursor = 1
            with patch.object(
                game, "choose_story_relic_path", return_value=True
            ) as choose:
                event = pygame.event.Event(
                    pygame.JOYBUTTONDOWN,
                    joy=fake.get_instance_id(),
                    button=0,
                )
                self.assertTrue(game.handle_controller_event(event))
            choose.assert_called_once_with(1)


class DPadButtonNavigationTests(unittest.TestCase):
    """D-pad buttons (11-14) are navigation-only in all contexts (4.9.20)."""

    def test_dpad_buttons_produce_directional_commands(self):
        from arch_rogue.input import DPAD_BUTTON_COMMANDS
        self.assertEqual(DPAD_BUTTON_COMMANDS[11], Command.UP)
        self.assertEqual(DPAD_BUTTON_COMMANDS[12], Command.DOWN)
        self.assertEqual(DPAD_BUTTON_COMMANDS[13], Command.LEFT)
        self.assertEqual(DPAD_BUTTON_COMMANDS[14], Command.RIGHT)

    def test_dpad_buttons_not_in_gameplay_map(self):
        from arch_rogue.input import GAMEPLAY_BUTTON_COMMANDS
        for button in (11, 12, 13, 14):
            self.assertNotIn(button, GAMEPLAY_BUTTON_COMMANDS)

    def test_dpad_up_in_menu_dispatches_up(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.state = "title"
            event = pygame.event.Event(pygame.JOYBUTTONDOWN, joy=0, button=11)
            with patch.object(game, "_dispatch_command") as dispatch:
                game.handle_controller_event(event)
                dispatch.assert_called_once_with(Command.UP)

    def test_dpad_down_in_menu_dispatches_down(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.state = "title"
            event = pygame.event.Event(pygame.JOYBUTTONDOWN, joy=0, button=12)
            with patch.object(game, "_dispatch_command") as dispatch:
                game.handle_controller_event(event)
                dispatch.assert_called_once_with(Command.DOWN)

    def test_dpad_in_gameplay_dispatches_its_gameplay_binding_not_back(self):
        # The original point of this test was that the D-pad must not leak BACK
        # into gameplay. It now also pins the 4.9.22 binding.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.state = "playing"
            event = pygame.event.Event(pygame.JOYBUTTONDOWN, joy=0, button=11)
            with (
                patch("arch_rogue.input.is_steam_deck", return_value=False),
                patch.object(game, "_dispatch_command") as dispatch,
            ):
                game.handle_controller_event(event)
                dispatch.assert_called_once_with(Command.MAP_ZOOM_IN)

    def test_repeated_dpad_down_is_consumed_within_one_event_frame(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.state = "options"
            down = pygame.event.Event(pygame.JOYBUTTONDOWN, joy=0, button=12)
            with patch.object(game, "_dispatch_command") as dispatch:
                game._dpad_consumed_this_frame = set()
                game.handle_controller_event(down)
                game.handle_controller_event(down)
                dispatch.assert_called_once_with(Command.DOWN)

                game._dpad_consumed_this_frame = set()
                game.handle_controller_event(down)
                self.assertEqual(dispatch.call_count, 2)

    def test_deck_hat_only_controller_still_navigates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.state = "options"
            game._dpad_consumed_this_frame = set()
            hat_up = pygame.event.Event(
                pygame.JOYHATMOTION, joy=2, hat=0, value=(0, 1)
            )
            with (
                patch("arch_rogue.input.is_steam_deck", return_value=True),
                patch.object(game, "_dispatch_command") as dispatch,
            ):
                game.handle_controller_event(hat_up)
            dispatch.assert_called_once_with(Command.UP)

    def test_deck_button_and_hat_duplicate_dispatch_once(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.state = "options"
            game._dpad_consumed_this_frame = set()
            button_up = pygame.event.Event(
                pygame.JOYBUTTONDOWN, joy=0, button=11
            )
            hat_up = pygame.event.Event(
                pygame.JOYHATMOTION, joy=0, hat=0, value=(0, 1)
            )
            with (
                patch("arch_rogue.input.is_steam_deck", return_value=True),
                patch.object(game, "_dispatch_command") as dispatch,
            ):
                game.handle_controller_event(button_up)
                game.handle_controller_event(hat_up)
            dispatch.assert_called_once_with(Command.UP)

    def test_dpad_up_down_zoom_the_minimap_during_gameplay(self):
        # 4.9.22: the zoom is now a MAP_ZOOM_IN/OUT command rather than a direct
        # adjust_minimap_zoom() call, so the D-pad, a remapped button and a Steam
        # Input action all reach it the same way. No longer gated on
        # is_steam_deck(): that DMI probe is wrong the moment Steam Input
        # substitutes a virtual pad.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.state = "playing"
            game.minimap_zoom = 1.0
            dpad_up = pygame.event.Event(pygame.JOYBUTTONDOWN, joy=0, button=11)
            dpad_down = pygame.event.Event(pygame.JOYBUTTONDOWN, joy=0, button=12)
            with patch("arch_rogue.input.is_steam_deck", return_value=False):
                game.handle_controller_event(dpad_up)
                self.assertAlmostEqual(game.minimap_zoom, 1.2)

                # A repeated press before release is not a second zoom notch.
                game.handle_controller_event(dpad_up)
                self.assertAlmostEqual(game.minimap_zoom, 1.2)

                game.handle_controller_event(dpad_down)
                self.assertAlmostEqual(game.minimap_zoom, 1.0)

    def test_dpad_keeps_plain_navigation_outside_gameplay(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.state = "title"
            event = pygame.event.Event(pygame.JOYBUTTONDOWN, joy=0, button=11)
            with patch.object(game, "_dispatch_command") as dispatch:
                game.handle_controller_event(event)
                dispatch.assert_called_once_with(Command.UP)

    def test_pulling_a_trigger_in_the_controls_menu_rebinds_it(self):
        """Drives the real run-loop branch, not the helper it calls.

        The previous capture code lived in Game.update(), guarded by
        `state == "controls"` -- a condition that can never be true there, since
        update() only runs while playing. It read correctly and was dead: trigger
        remapping never worked on any controller. A test that called
        assign_gamepad_trigger_slot directly would have passed throughout, so
        this one steps the frame the way the loop does.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            fake = FakeJoystick(7, num_axes=6)
            game.input._joysticks[7] = fake
            game.input._axis_layout[7] = game.input._compute_layout(fake)
            game.input._trigger_layout[7] = game.input._compute_triggers(fake)
            game.input._active_id = 7
            game.input._layout_id = None
            game.state = "controls"
            game.controls_capture_command = Command.ABILITY_3

            # One frame at rest, then the trigger pulled: the binding is taken
            # from the rising edge, so both frames matter.
            self._step_controls_frame(game)
            fake.set_axis(4, 1.0)
            self._step_controls_frame(game)

            self.assertEqual(game.gamepad_mapping["triggers"][0], Command.ABILITY_3)
            self.assertIsNone(game.controls_capture_command)

    def test_a_trigger_pull_that_rebinds_does_not_also_fire_a_command(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            fake = FakeJoystick(7, num_axes=6)
            game.input._joysticks[7] = fake
            game.input._axis_layout[7] = game.input._compute_layout(fake)
            game.input._trigger_layout[7] = game.input._compute_triggers(fake)
            game.input._active_id = 7
            game.input._layout_id = None
            game.state = "controls"
            game.controls_capture_command = Command.ABILITY_3
            self._step_controls_frame(game)
            fake.set_axis(4, 1.0)
            with patch.object(game, "_dispatch_command") as dispatch:
                self._step_controls_frame(game)
                dispatch.assert_not_called()

    @staticmethod
    def _step_controls_frame(game: Game) -> None:
        """Exactly what Game.run() calls for a non-playing frame.

        Calling the real method, not a copy of it: a test that reimplemented the
        loop body would have passed against the unreachable version too.
        """
        game.poll_menu_axes()

    def test_dpad_buttons_blocked_in_controls_rebind(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.state = "controls"
            game.controls_capture_command = Command.ABILITY_1
            # Pressing D-pad Up during rebind capture should NOT assign it.
            event = pygame.event.Event(pygame.JOYBUTTONDOWN, joy=0, button=11)
            result = game.handle_controller_event(event)
            self.assertTrue(result)  # consumed (ignored)
            # Capture should still be open — the command was not assigned.
            self.assertEqual(game.controls_capture_command, Command.ABILITY_1)
            self.assertNotIn(11, game.gamepad_mapping["gameplay_buttons"])

    def test_non_dpad_button_still_assignable_in_rebind(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.state = "controls"
            game.controls_capture_command = Command.ABILITY_1
            event = pygame.event.Event(pygame.JOYBUTTONDOWN, joy=0, button=4)
            game.handle_controller_event(event)
            self.assertIsNone(game.controls_capture_command)
            self.assertEqual(
                game.gamepad_mapping["gameplay_buttons"][4], Command.ABILITY_1
            )


class StickMenuNavigationTests(unittest.TestCase):
    """Left-stick -> discrete directional commands for menu navigation (4.9.20)."""

    def setUp(self):
        # Re-import to pick up the new constants
        from arch_rogue.input import STICK_NAV_ACTIVATION, STICK_NAV_RELEASE
        self.activation = STICK_NAV_ACTIVATION
        self.release = STICK_NAV_RELEASE

    def test_push_up_emits_up_command(self):
        fake = FakeJoystick(0, num_axes=4, axes_rest=(0, 0, 0, 0))
        mgr = make_controller_manager(fake)
        fake.set_axis(0, 0.0)   # x = 0
        fake.set_axis(1, -0.8)  # y = -0.8 (up)
        mgr.poll_axes()
        self.assertEqual(mgr.drain_stick_commands(), [Command.UP])

    def test_push_down_emits_down_command(self):
        fake = FakeJoystick(0, num_axes=4, axes_rest=(0, 0, 0, 0))
        mgr = make_controller_manager(fake)
        fake.set_axis(1, 0.8)  # y = +0.8 (down)
        mgr.poll_axes()
        self.assertEqual(mgr.drain_stick_commands(), [Command.DOWN])

    def test_push_left_emits_left_command(self):
        fake = FakeJoystick(0, num_axes=4, axes_rest=(0, 0, 0, 0))
        mgr = make_controller_manager(fake)
        fake.set_axis(0, -0.8)
        mgr.poll_axes()
        self.assertEqual(mgr.drain_stick_commands(), [Command.LEFT])

    def test_push_right_emits_right_command(self):
        fake = FakeJoystick(0, num_axes=4, axes_rest=(0, 0, 0, 0))
        mgr = make_controller_manager(fake)
        fake.set_axis(0, 0.8)
        mgr.poll_axes()
        self.assertEqual(mgr.drain_stick_commands(), [Command.RIGHT])

    def test_held_stick_does_not_repeat_until_released(self):
        fake = FakeJoystick(0, num_axes=4, axes_rest=(0, 0, 0, 0))
        mgr = make_controller_manager(fake)
        # Push up past activation
        fake.set_axis(1, -0.8)
        mgr.poll_axes()
        self.assertEqual(mgr.drain_stick_commands(), [Command.UP])
        # Still held — no new command
        mgr.poll_axes()
        self.assertEqual(mgr.drain_stick_commands(), [])
        mgr.poll_axes()
        self.assertEqual(mgr.drain_stick_commands(), [])

    def test_release_and_re_push_emits_again(self):
        fake = FakeJoystick(0, num_axes=4, axes_rest=(0, 0, 0, 0))
        mgr = make_controller_manager(fake)
        # Push
        fake.set_axis(1, -0.8)
        mgr.poll_axes()
        self.assertEqual(mgr.drain_stick_commands(), [Command.UP])
        # Release below RELEASE threshold
        fake.set_axis(1, -0.1)
        mgr.poll_axes()
        self.assertEqual(mgr.drain_stick_commands(), [])
        # Push again
        fake.set_axis(1, -0.8)
        mgr.poll_axes()
        self.assertEqual(mgr.drain_stick_commands(), [Command.UP])

    def test_below_activation_threshold_does_not_fire(self):
        fake = FakeJoystick(0, num_axes=4, axes_rest=(0, 0, 0, 0))
        mgr = make_controller_manager(fake)
        fake.set_axis(1, -0.4)  # between release and activation
        mgr.poll_axes()
        self.assertEqual(mgr.drain_stick_commands(), [])

    def test_dominant_axis_wins_for_diagonal(self):
        fake = FakeJoystick(0, num_axes=4, axes_rest=(0, 0, 0, 0))
        mgr = make_controller_manager(fake)
        # x=0.7, y=0.9 — y dominates, so DOWN
        fake.set_axis(0, 0.7)
        fake.set_axis(1, 0.9)
        mgr.poll_axes()
        self.assertEqual(mgr.drain_stick_commands(), [Command.DOWN])
        # Reset
        fake.set_axis(0, 0.0)
        fake.set_axis(1, 0.0)
        mgr.poll_axes()
        mgr.drain_stick_commands()
        # x=0.9, y=0.7 — x dominates, so RIGHT
        fake.set_axis(0, 0.9)
        fake.set_axis(1, 0.7)
        mgr.poll_axes()
        self.assertEqual(mgr.drain_stick_commands(), [Command.RIGHT])

    def test_disabled_manager_emits_no_stick_commands(self):
        fake = FakeJoystick(0, num_axes=4, axes_rest=(0, 0, 0, 0))
        mgr = make_controller_manager(fake)
        fake.set_axis(1, -0.8)
        mgr.poll_axes()
        mgr.drain_stick_commands()
        mgr.set_enabled(False)
        fake.set_axis(1, 0.0)
        mgr.poll_axes()
        fake.set_axis(1, -0.8)
        mgr.poll_axes()
        self.assertEqual(mgr.drain_stick_commands(), [])

    def test_drain_clears_queue(self):
        fake = FakeJoystick(0, num_axes=4, axes_rest=(0, 0, 0, 0))
        mgr = make_controller_manager(fake)
        fake.set_axis(1, -0.8)
        mgr.poll_axes()
        self.assertEqual(mgr.drain_stick_commands(), [Command.UP])
        self.assertEqual(mgr.drain_stick_commands(), [])


class CombatAxisIntegrationTests(unittest.TestCase):
    def test_controller_aim_helper_snaps_to_visible_enemy(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            attach_fake_controller(game)
            px, py = game.player.x, game.player.y
            target = make_target_enemy(px + 3.0, py + 0.7)
            open_floor_band_to_target(game, target.x, target.y)
            game.enemies = [target]
            game.input._right_vec = (1.0, 0.0)  # close to the target line

            game.update_player_aim()

            length = math.hypot(target.x - px, target.y - py)
            self.assertAlmostEqual(
                game.player.facing_x, (target.x - px) / length, places=4
            )
            self.assertAlmostEqual(
                game.player.facing_y, (target.y - py) / length, places=4
            )

    def test_controller_bolt_uses_right_stick_aim_while_moving(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.input._right_vec = (0.0, 1.0)  # aim down
            game.input._left_vec = (1.0, 0.0)  # move right
            game.update_player_aim()
            game.update_player(0.1)
            game.player.mana = 100
            game.player.bolt_timer = 0.0
            before = len(game.projectiles)
            game._dispatch_command(Command.ABILITY_2)
            self.assertEqual(len(game.projectiles), before + 1)
            bolt = game.projectiles[-1]
            self.assertAlmostEqual(bolt.vx, 0.0, places=4)
            self.assertGreater(bolt.vy, 0.0)


class DisplayScaleTests(unittest.TestCase):
    def test_display_scale_quantizes_to_supported_ui_scales(self) -> None:
        cases = (
            (None, 1),
            (float("nan"), 1),
            (1.0, 1),
            (1.25, 1),
            (1.5, 2),
            (2.0, 2),
            (2.5, 3),
            (3.5, 4),
            (8.0, 4),
        )
        for display_scale, expected in cases:
            with self.subTest(display_scale=display_scale):
                self.assertEqual(
                    ui_scale_from_display_scale(display_scale), expected
                )

    def test_auto_scale_refresh_and_manual_override_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.ui_scale_auto = True
            # The desktop always renders the fixed 2560×1440 logical canvas
            # (SDL's SCALED renderer fits it to the real window/monitor), so
            # the automatic scale derives from the canvas — deterministically 2.
            game.screen = pygame.Surface((2560, 1440))
            self.assertTrue(game.refresh_automatic_ui_scale())
            self.assertEqual(game.ui_scale, 2)
            self.assertEqual(game.ui_scale_label(), "Auto · 2x")

            game._activate_options_row(game.OPTIONS_ROW_UI_SCALE, True)
            self.assertFalse(game.ui_scale_auto)
            self.assertEqual(game.ui_scale, 3)
            self.assertEqual(game.ui_scale_label(), "3x")

            game.ui_scale = 4
            self.assertTrue(game.cycle_ui_scale(True))
            self.assertTrue(game.ui_scale_auto)
            self.assertEqual(game.ui_scale, 2)

    def test_auto_scale_honors_display_scale_environment_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.ui_scale_auto = True
            game.screen = pygame.Surface((2560, 1440))
            with patch.dict(os.environ, {"ARCH_ROGUE_DISPLAY_SCALE": "3"}):
                self.assertTrue(game.refresh_automatic_ui_scale())
            self.assertEqual(game.ui_scale, 3)
            self.assertTrue(game.ui_scale_auto)

    def test_auto_scale_mode_round_trips_and_rebuilds_fonts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            # Auto mode recomputes from the live surface on load, so hand the
            # game the fixed desktop canvas the loaded value must agree with.
            game.screen = pygame.Surface((2560, 1440))
            game.ui_scale = 2
            game.ui_scale_auto = True
            self.assertTrue(game.save_options())

            game.ui_scale = 1
            game.ui_scale_auto = False
            game.rebuild_fonts()
            old_font_height = game.font.get_height()
            self.assertTrue(game.load_options())
            self.assertEqual(game.ui_scale, 2)
            self.assertTrue(game.ui_scale_auto)
            self.assertGreater(game.font.get_height(), old_font_height)

    def test_legacy_custom_scale_conflicting_with_host_stays_manual(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.ui_scale = 3
            game.ui_scale_auto = False
            game._legacy_ui_scale_migration = True
            game.screen = pygame.Surface((2560, 1440))
            self.assertFalse(game.refresh_automatic_ui_scale())
            self.assertEqual(game.ui_scale, 3)
            self.assertFalse(game.ui_scale_auto)

    def test_manual_choice_cancels_delayed_legacy_migration(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.ui_scale = 1
            game.ui_scale_auto = False
            game._legacy_ui_scale_migration = True
            # Before the display exists (load_options runs pre-set_mode) the
            # automatic scale cannot be determined and migration is deferred.
            del game.screen
            self.assertFalse(game.refresh_automatic_ui_scale())
            self.assertTrue(game.cycle_ui_scale(True))
            self.assertFalse(game._legacy_ui_scale_migration)
            game.screen = pygame.Surface((2560, 1440))
            self.assertFalse(game.refresh_automatic_ui_scale())
            self.assertFalse(game.ui_scale_auto)
            self.assertEqual(game.ui_scale, 2)

    def test_window_resize_does_not_recreate_scaled_mode(self) -> None:
        # The desktop window is RESIZABLE | SCALED: SDL rescales the fixed
        # logical canvas on drag, so the resize event must leave the display
        # mode (and therefore the logical surface the UI laid out on) alone.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.fullscreen = False
            surface_before = game.screen
            with patch.object(pygame.display, "set_mode") as set_mode:
                pygame.event.post(
                    pygame.event.Event(pygame.VIDEORESIZE, w=1024, h=640)
                )
                game.handle_events()
            set_mode.assert_not_called()
            self.assertIs(game.screen, surface_before)


class DesktopRenderResolutionTests(unittest.TestCase):
    """4.9.25: desktop render canvas tiers (native 1440p / 720p / 540p)."""

    def test_cycle_applies_canvas_auto_scale_and_persists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.fullscreen = False
            game.ui_scale = 2
            game.ui_scale_auto = True
            self.assertEqual(game.desktop_render_quality, "native")
            # Pin a 16:9 desktop: the logical canvas now follows the display
            # aspect (non-16:9 panels fill edge-to-edge instead of
            # letterboxing), and the dummy driver reports the host desktop.
            fake_info = unittest.mock.MagicMock()
            fake_info.current_w = 2560
            fake_info.current_h = 1440
            self.enterContext(
                patch.object(pygame.display, "Info", return_value=fake_info)
            )
            # Backward from native lands on the balanced 720p tier.
            self.assertTrue(game.cycle_desktop_render_quality(False))
            self.assertEqual(game.desktop_render_quality, "balanced")
            self.assertEqual(game.screen.get_size(), (1280, 720))
            self.assertEqual(game.desktop_render_resolution_label(), "Balanced · 720p")
            # The canvas-derived automatic UI scale follows the half canvas.
            self.assertEqual(game.ui_scale, 1)
            data = json.loads(game.options_path.read_text(encoding="utf-8"))
            self.assertEqual(data["desktop_render_quality"], "balanced")

    def test_persisted_tier_round_trips_and_malformed_resets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.desktop_render_quality = "performance"
            self.assertTrue(game.save_options())
            game.desktop_render_quality = "native"
            self.assertTrue(game.load_options())
            self.assertEqual(game.desktop_render_quality, "performance")

            data = json.loads(game.options_path.read_text(encoding="utf-8"))
            data["desktop_render_quality"] = "ultrawide"
            game.options_path.write_text(json.dumps(data), encoding="utf-8")
            self.assertTrue(game.load_options())
            self.assertEqual(game.desktop_render_quality, "native")

    def test_mobile_mode_does_not_cycle_desktop_canvas(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.mobile_mode = True
            self.assertEqual(game.OPTIONS_ROW_RENDER_RES, -1)
            self.assertFalse(game.cycle_desktop_render_quality(True))
            self.assertEqual(game.desktop_render_quality, "native")


class OptionsPersistenceTests(unittest.TestCase):
    def test_controller_prefs_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.controller_enabled = False
            game.last_controller_guid = "abc-123"
            self.assertTrue(game.save_options())
            loaded = game.load_options()
            self.assertTrue(loaded)
            self.assertFalse(game.controller_enabled)
            self.assertEqual(game.last_controller_guid, "abc-123")
            data = game.options_to_dict()
            self.assertEqual(data["schema_version"], 10)
            self.assertEqual(
                data["mobile_render_quality"], MOBILE_RENDER_QUALITY_NATIVE
            )
            self.assertEqual(
                data["desktop_render_quality"], MOBILE_RENDER_QUALITY_NATIVE
            )
            self.assertEqual(
                game.mobile_render_quality, MOBILE_RENDER_QUALITY_NATIVE
            )
            self.assertIn("gamepad_mapping", data)
            self.assertTrue(data["ui_scale_auto"])
            self.assertFalse(data["legacy_graphics"])

    def test_missing_display_and_difficulty_fields_use_fresh_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            import json

            game.fullscreen = False
            game.difficulty_name = "Hard"
            game.options_path.write_text(
                json.dumps({"version": 1, "schema_version": 4}),
                encoding="utf-8",
            )
            self.assertTrue(game.load_options())
            self.assertTrue(game.fullscreen)
            self.assertTrue(game.ui_scale_auto)
            self.assertEqual(game.difficulty_profile().name, "Medium")
            self.assertEqual(
                game.gamepad_mapping["gameplay_buttons"],
                default_gamepad_mapping()["gameplay_buttons"],
            )

    def test_persisted_music_preference_is_ignored_while_music_is_parked(self) -> None:
        # 4.11.0: the music option is parked until real tracks exist. A profile
        # that enabled the old placeholder loop must load silent, and no
        # options-menu key may re-enable it (the M binding is gone).
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.music_enabled = True
            game.save_options()
            other = make_game(tmpdir)
            other.options_path = game.options_path
            self.assertTrue(other.load_options())
            self.assertFalse(other.music_enabled)

    def test_old_schema_v2_loads_with_safe_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            import json

            old = {
                "version": 1,
                "schema_version": 2,
                "audio_enabled": True,
                "music_enabled": False,
                "fullscreen": False,
                "ui_scale": 1,
                "difficulty": "Hard",
                "hell_unlocked": False,
                "meta_progress": game.default_meta_progress(),
                "run_history": [],
            }
            game.options_path.write_text(json.dumps(old), encoding="utf-8")
            # Legacy migration quantizes against the fixed desktop canvas.
            game.screen = pygame.Surface((2560, 1440))
            self.assertTrue(game.load_options())
            # Missing controller fields default to enabled / no preferred device.
            self.assertTrue(game.controller_enabled)
            self.assertEqual(game.last_controller_guid, "")
            # Explicit legacy values remain authoritative despite new defaults.
            self.assertTrue(game.audio_enabled)
            self.assertFalse(game.fullscreen)
            self.assertTrue(game.ui_scale_auto)
            self.assertEqual(game.ui_scale, 2)
            self.assertEqual(game.difficulty_profile().name, "Hard")


class LegacyGraphicsHotkeyTests(unittest.TestCase):
    """Ctrl+Alt+L toggles legacy graphics from any game state."""

    def _post_key(self, game: Game, key: int, mod: int) -> None:
        pygame.event.post(
            pygame.event.Event(pygame.KEYDOWN, key=key, mod=mod)
        )
        game.handle_events()

    def test_ctrl_alt_l_toggles_legacy_graphics_in_playing_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            self.assertEqual(game.state, "playing")
            self.assertFalse(game.legacy_graphics)
            self.assertFalse(game.sprites.legacy_graphics)

            self._post_key(
                game, pygame.K_l, pygame.KMOD_CTRL | pygame.KMOD_ALT
            )
            self.assertTrue(game.legacy_graphics)
            self.assertTrue(game.sprites.legacy_graphics)
            # Feedback floater appears in playing state.
            self.assertTrue(
                any(
                    floater.text
                    in ("Legacy graphics", "Modern graphics", "HD graphics")
                    for floater in game.floaters
                )
            )

            # Toggling again returns to modern asset sprites.
            self._post_key(
                game, pygame.K_l, pygame.KMOD_CTRL | pygame.KMOD_ALT
            )
            self.assertFalse(game.legacy_graphics)
            self.assertFalse(game.sprites.legacy_graphics)

    def test_ctrl_alt_l_persists_to_options_file(self) -> None:
        import json

        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            self._post_key(
                game, pygame.K_l, pygame.KMOD_CTRL | pygame.KMOD_ALT
            )
            data = json.loads(
                game.options_path.read_text(encoding="utf-8")
            )
            self.assertTrue(data["legacy_graphics"])

            # A fresh Game loading the same options inherits the toggle.
            loaded = Game(
                screen_size=(820, 540),
                headless=True,
                save_path=Path(tmpdir) / "run.json",
            )
            loaded.options_path = Path(tmpdir) / "options.json"
            loaded.meta_progress = loaded.default_meta_progress()
            loaded.run_history = []
            self.assertTrue(loaded.load_options())
            self.assertTrue(loaded.legacy_graphics)
            self.assertTrue(loaded.sprites.legacy_graphics)

    def test_ctrl_alt_l_works_from_title_without_load_run_side_effect(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            # On the title screen, plain K_l would load a run if a save exists.
            # The Ctrl+Alt+L hotkey must intercept that binding instead.
            game.state = "title"
            game.save_path.unlink(missing_ok=True)
            self.assertFalse(game.legacy_graphics)

            self._post_key(
                game, pygame.K_l, pygame.KMOD_CTRL | pygame.KMOD_ALT
            )
            self.assertTrue(game.legacy_graphics)
            # Still on the title screen, no run was loaded.
            self.assertEqual(game.state, "title")

    def test_plain_l_in_options_menu_does_not_toggle_legacy_graphics(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.state = "options"
            self.assertFalse(game.legacy_graphics)

            # Plain K_l in options adjusts the lighting row, not graphics.
            self._post_key(game, pygame.K_l, 0)
            self.assertFalse(game.legacy_graphics)
            self.assertEqual(game.options_cursor, game.OPTIONS_ROW_LIGHTING)

    def test_ctrl_alt_l_does_not_fire_on_lone_ctrl_or_alt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            self.assertFalse(game.legacy_graphics)

            # Only Ctrl (no Alt) — must not toggle.
            self._post_key(game, pygame.K_l, pygame.KMOD_CTRL)
            self.assertFalse(game.legacy_graphics)

            # Only Alt (no Ctrl) — must not toggle.
            self._post_key(game, pygame.K_l, pygame.KMOD_ALT)
            self.assertFalse(game.legacy_graphics)

    def test_ctrl_alt_l_hint_appears_in_hud_control_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.ui_scale = 1
            game.rebuild_fonts()

            seen: list[str] = []
            original = game.draw_ui_text

            def spy(surface, text, font, color, rect, align="left", valign="top"):
                if font is game.tiny_font and "Ctrl+Alt+L" in str(text):
                    seen.append(str(text))
                return original(surface, text, font, color, rect, align, valign)

            game.draw_ui_text = spy
            game.draw_ui()
            game.draw_ui_text = original

            self.assertTrue(seen, "Ctrl+Alt+L hint not rendered in HUD")
            self.assertIn("Ctrl+Alt+L", seen[0])


class QuestInfoScrollInputTests(unittest.TestCase):
    """4.2.2: plain wheel and PgUp/PgDn scroll the quest info panel text."""

    def _make_scrollable_game(self, tmpdir: str) -> Game:
        game = make_game(tmpdir)
        game.quest_info_visible = True
        # Simulate the renderer having published an overflowing panel.
        game._story_panel_scroll_max = 10
        game._story_panel_visible_lines = 5
        return game

    def test_plain_wheel_scrolls_and_ctrl_wheel_still_zooms(self) -> None:
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmpdir:
            game = self._make_scrollable_game(tmpdir)
            self.assertEqual(game.state, "playing")
            self.assertEqual(game.story_panel_scroll, 0)

            # Wheel down (y=-1) advances the story text by two lines.
            pygame.event.post(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=-1))
            game.handle_events()
            self.assertEqual(game.story_panel_scroll, 2)

            # Wheel up returns toward the top and clamps at zero.
            for _ in range(3):
                pygame.event.post(
                    pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=1)
                )
                game.handle_events()
            self.assertEqual(game.story_panel_scroll, 0)

            # Ctrl+wheel keeps zooming the viewport instead of scrolling.
            game.view_zoom = 1.0
            zoom_before = getattr(game, "view_zoom", 1.0)
            with patch.object(
                pygame.key, "get_mods", return_value=pygame.KMOD_CTRL
            ):
                pygame.event.post(
                    pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=-1)
                )
                game.handle_events()
            self.assertEqual(game.story_panel_scroll, 0)
            self.assertNotEqual(getattr(game, "view_zoom", 1.0), zoom_before)

            # With the quest panel hidden, plain wheel does nothing.
            game.quest_info_visible = False
            pygame.event.post(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=-1))
            game.handle_events()
            self.assertEqual(game.story_panel_scroll, 0)

    def test_page_keys_page_quest_text_but_inventory_keeps_priority(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self._make_scrollable_game(tmpdir)

            # PgDn pages by one panel of lines (visible lines minus one).
            pygame.event.post(
                pygame.event.Event(pygame.KEYDOWN, key=pygame.K_PAGEDOWN, mod=0)
            )
            game.handle_events()
            self.assertEqual(game.story_panel_scroll, 4)

            # PgUp pages back and clamps at the top.
            for _ in range(2):
                pygame.event.post(
                    pygame.event.Event(
                        pygame.KEYDOWN, key=pygame.K_PAGEUP, mod=0
                    )
                )
                game.handle_events()
            self.assertEqual(game.story_panel_scroll, 0)

            # While the inventory overlay is open, PgDn moves the inventory
            # cursor (existing behavior) and leaves the quest text alone.
            from arch_rogue.models import Item

            game.player.inventory = [
                Item(f"Test Blade {index}", "weapon", power=index + 1)
                for index in range(8)
            ]
            game.inventory_open = True
            game.set_inventory_selection(0)
            pygame.event.post(
                pygame.event.Event(pygame.KEYDOWN, key=pygame.K_PAGEDOWN, mod=0)
            )
            game.handle_events()
            self.assertEqual(game.story_panel_scroll, 0)
            self.assertEqual(game.inventory_cursor, 5)
