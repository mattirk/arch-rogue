from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame  # noqa: E402

from arch_rogue.content import ARCHETYPES  # noqa: E402
from arch_rogue.game import Game  # noqa: E402
from arch_rogue.input import (  # noqa: E402
    CUTSCENE_BUTTON_COMMANDS,
    DEFAULT_JOY_BUTTON_COMMANDS,
    GAMEPLAY_BUTTON_COMMANDS,
    Command,
    ControllerManager,
    default_gamepad_mapping,
    hat_commands,
    joybutton_command,
    joybutton_command_for_state,
    key_command,
    mapped_joybutton_command,
    normalize_gamepad_mapping,
)
from arch_rogue.quest_assets import ActiveQuestCutscene  # noqa: E402


class FakeJoystick:
    """A minimal stand-in for pygame.joystick.Joystick for deterministic tests."""

    def __init__(
        self,
        instance_id: int,
        guid: str = "fake-guid",
        name: str = "Fake Pad",
        num_axes: int = 6,
        axes_rest: tuple[float, ...] | None = None,
    ) -> None:
        self._id = instance_id
        self._guid = guid
        self._name = name
        self._num_axes = num_axes
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
    def test_key_command_navigation_keys(self) -> None:
        self.assertEqual(key_command(pygame.K_UP, 0), Command.UP)
        self.assertEqual(key_command(pygame.K_DOWN, 0), Command.DOWN)
        self.assertEqual(key_command(pygame.K_LEFT, 0), Command.LEFT)
        self.assertEqual(key_command(pygame.K_RIGHT, 0), Command.RIGHT)
        self.assertEqual(key_command(pygame.K_RETURN, 0), Command.CONFIRM)
        self.assertEqual(key_command(pygame.K_ESCAPE, 0), Command.BACK)
        self.assertEqual(key_command(pygame.K_BACKSPACE, 0), Command.BACK)
        self.assertEqual(key_command(pygame.K_TAB, 0), Command.TAB)

    def test_shift_tab_maps_to_tab_prev(self) -> None:
        self.assertEqual(key_command(pygame.K_TAB, pygame.KMOD_SHIFT), Command.TAB_PREV)
        # Without shift, plain Tab is forward tab.
        self.assertEqual(key_command(pygame.K_TAB, 0), Command.TAB)

    def test_gameplay_keys_are_not_mapped_here(self) -> None:
        # Ability / interact / inventory keys stay with Game.handle_events so
        # legacy keyboard bindings are preserved exactly.
        for key in (
            pygame.K_1,
            pygame.K_e,
            pygame.K_i,
            pygame.K_c,
            pygame.K_q,
            pygame.K_h,
        ):
            self.assertIsNone(key_command(key, 0))

    def test_joybutton_command_default_layout(self) -> None:
        self.assertEqual(joybutton_command(0), Command.CONFIRM)
        self.assertEqual(joybutton_command(1), Command.BACK)
        self.assertEqual(joybutton_command(2), Command.INTERACT)
        self.assertEqual(joybutton_command(5), Command.TAB)
        self.assertEqual(joybutton_command(4), Command.TAB_PREV)
        self.assertEqual(joybutton_command(6), Command.INVENTORY)
        self.assertEqual(joybutton_command(7), Command.CHARACTER)

    def test_joybutton_unknown_returns_none(self) -> None:
        self.assertIsNone(joybutton_command(99))

    def test_contextual_gamepad_button_maps(self) -> None:
        self.assertEqual(joybutton_command_for_state(0, "menu"), Command.CONFIRM)
        self.assertEqual(joybutton_command_for_state(0, "gameplay"), Command.ABILITY_1)
        self.assertEqual(joybutton_command_for_state(2, "gameplay"), Command.ABILITY_2)
        self.assertEqual(joybutton_command_for_state(3, "gameplay"), Command.ABILITY_3)
        self.assertEqual(joybutton_command_for_state(0, "cutscene"), Command.CONFIRM)
        self.assertEqual(joybutton_command_for_state(2, "cutscene"), Command.ABILITY_1)
        self.assertEqual(joybutton_command_for_state(1, "cutscene"), Command.BACK)

    def test_gameplay_and_cutscene_maps_expose_actions(self) -> None:
        self.assertEqual(GAMEPLAY_BUTTON_COMMANDS[0], Command.ABILITY_1)
        self.assertEqual(GAMEPLAY_BUTTON_COMMANDS[2], Command.ABILITY_2)
        self.assertEqual(GAMEPLAY_BUTTON_COMMANDS[3], Command.ABILITY_3)
        self.assertEqual(CUTSCENE_BUTTON_COMMANDS[2], Command.ABILITY_1)
        self.assertEqual(CUTSCENE_BUTTON_COMMANDS[3], Command.ABILITY_2)

    def test_default_button_map_is_unique(self) -> None:
        commands = list(DEFAULT_JOY_BUTTON_COMMANDS.values())
        self.assertEqual(len(commands), len(set(commands)))

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

    def test_duplicate_saved_trigger_binding_is_cleared_when_button_exists(
        self,
    ) -> None:
        mapping = normalize_gamepad_mapping(
            {
                "gameplay_buttons": {"0": Command.ABILITY_4},
                "triggers": [Command.ABILITY_4, Command.INTERACT],
            }
        )
        self.assertEqual(mapping["gameplay_buttons"][0], Command.ABILITY_4)
        self.assertEqual(mapping["triggers"][0], "")
        self.assertEqual(mapping["triggers"][1], Command.INTERACT)

    def test_saved_trigger_blanks_do_not_shift_slots(self) -> None:
        mapping = normalize_gamepad_mapping({"triggers": ["", Command.ABILITY_6]})
        self.assertEqual(mapping["triggers"][0], "")
        self.assertEqual(mapping["triggers"][1], Command.ABILITY_6)

    def test_hat_commands_translate_dpad(self) -> None:
        up = SimpleNamespace(type=pygame.JOYHATMOTION, joy=0, hat=0, value=(0, 1))
        self.assertEqual(list(hat_commands(up)), [Command.UP])
        down = SimpleNamespace(type=pygame.JOYHATMOTION, joy=0, hat=0, value=(0, -1))
        self.assertEqual(list(hat_commands(down)), [Command.DOWN])
        diag = SimpleNamespace(type=pygame.JOYHATMOTION, joy=0, hat=0, value=(-1, 1))
        cmds = list(hat_commands(diag))
        self.assertIn(Command.LEFT, cmds)
        self.assertIn(Command.UP, cmds)
        center = SimpleNamespace(type=pygame.JOYHATMOTION, joy=0, hat=0, value=(0, 0))
        self.assertEqual(list(hat_commands(center)), [])


class ControllerManagerTests(unittest.TestCase):
    def test_layout_skips_trigger_axes(self) -> None:
        # 6 axes; last two rest at -1 (triggers). Sticks should be 0,1 and 2,3.
        fake = FakeJoystick(0, num_axes=6)
        mgr = make_controller_manager(fake)
        left, right = mgr._axis_layout[fake.get_instance_id()]
        self.assertEqual(left, (0, 1))
        self.assertEqual(right, (2, 3))

    def test_layout_handles_xbox_raw_trigger_on_axis2(self) -> None:
        # Xbox-raw: axis 2 and 5 are triggers at rest (-1).
        fake = FakeJoystick(0, num_axes=6, axes_rest=(0, 0, -1, 0, 0, -1))
        mgr = make_controller_manager(fake)
        left, right = mgr._axis_layout[fake.get_instance_id()]
        self.assertEqual(left, (0, 1))
        self.assertEqual(right, (3, 4))

    def test_layout_four_axis_pad(self) -> None:
        fake = FakeJoystick(0, num_axes=4, axes_rest=(0, 0, 0, 0))
        mgr = make_controller_manager(fake)
        left, right = mgr._axis_layout[fake.get_instance_id()]
        self.assertEqual(left, (0, 1))
        self.assertEqual(right, (2, 3))

    def test_deadzone_zeros_small_deflection(self) -> None:
        fake = FakeJoystick(0, num_axes=4, axes_rest=(0, 0, 0, 0))
        mgr = make_controller_manager(fake)
        fake.set_axis(0, 0.1)  # inside the 0.24 deadzone
        fake.set_axis(1, 0.1)
        mgr.poll_axes()
        self.assertEqual(mgr.left_vec(), (0.0, 0.0))

    def test_poll_axes_rescales_past_deadzone(self) -> None:
        fake = FakeJoystick(0, num_axes=4, axes_rest=(0, 0, 0, 0))
        mgr = make_controller_manager(fake)
        fake.set_axis(0, 1.0)  # full right
        mgr.poll_axes()
        lx, ly = mgr.left_vec()
        self.assertAlmostEqual(lx, 1.0, places=5)
        self.assertAlmostEqual(ly, 0.0, places=5)

    def test_right_stick_read_via_layout(self) -> None:
        fake = FakeJoystick(0, num_axes=4, axes_rest=(0, 0, 0, 0))
        mgr = make_controller_manager(fake)
        fake.set_axis(2, 0.0)
        fake.set_axis(3, 1.0)  # right stick down
        mgr.poll_axes()
        rx, ry = mgr.right_vec()
        self.assertAlmostEqual(rx, 0.0, places=5)
        self.assertAlmostEqual(ry, 1.0, places=5)

    def test_trigger_axes_emit_dash_and_interact_edges(self) -> None:
        fake = FakeJoystick(0, num_axes=6, axes_rest=(0, 0, 0, 0, -1, -1))
        mgr = make_controller_manager(fake)
        self.assertEqual(mgr._trigger_layout[fake.get_instance_id()], [4, 5])
        fake.set_axis(4, 1.0)  # LT press -> dash
        mgr.poll_axes()
        self.assertEqual(mgr.drain_trigger_commands(), [Command.ABILITY_4])
        mgr.poll_axes()
        self.assertEqual(mgr.drain_trigger_commands(), [])
        fake.set_axis(4, -1.0)
        fake.set_axis(5, 1.0)  # RT press -> interact
        mgr.poll_axes()
        self.assertEqual(mgr.drain_trigger_commands(), [Command.INTERACT])

    def test_no_controller_returns_zero_vectors(self) -> None:
        mgr = make_controller_manager(None)
        mgr.poll_axes()
        self.assertEqual(mgr.left_vec(), (0.0, 0.0))
        self.assertEqual(mgr.right_vec(), (0.0, 0.0))
        self.assertFalse(mgr.has_controller())

    def test_set_enabled_disables_controller(self) -> None:
        fake = FakeJoystick(0)
        mgr = make_controller_manager(fake)
        self.assertTrue(mgr.has_controller())
        mgr.set_enabled(False)
        self.assertFalse(mgr.has_controller())
        mgr.set_enabled(True)
        self.assertTrue(mgr.has_controller())

    def test_hot_plug_add_and_remove(self) -> None:
        mgr = ControllerManager(last_guid="", enabled=True)
        added = SimpleNamespace(type=pygame.JOYDEVICEADDED, device_index=0)
        # Inject a fake via _add_device by patching the constructor.
        original = pygame.joystick.Joystick
        try:
            pygame.joystick.Joystick = lambda idx: FakeJoystick(idx)  # type: ignore[misc]
            mgr.handle_device_event(added)
        finally:
            pygame.joystick.Joystick = original  # type: ignore[misc]
        self.assertTrue(mgr.has_controller())
        active_id = mgr.active().get_instance_id()
        removed = SimpleNamespace(
            type=pygame.JOYDEVICEREMOVED, instance_id=active_id, which=active_id
        )
        mgr.handle_device_event(removed)
        self.assertFalse(mgr.has_controller())

    def test_prefer_last_guid_on_connect(self) -> None:
        # First connect an unrelated pad, then the persisted-guid pad; the
        # persisted one should become active.
        mgr = ControllerManager(last_guid="want-this", enabled=True)
        original = pygame.joystick.Joystick
        seq = [FakeJoystick(0, guid="other"), FakeJoystick(1, guid="want-this")]

        def ctor(idx: int) -> FakeJoystick:
            return seq[idx]

        try:
            pygame.joystick.Joystick = ctor  # type: ignore[misc]
            mgr.handle_device_event(
                SimpleNamespace(type=pygame.JOYDEVICEADDED, device_index=0)
            )
            mgr.handle_device_event(
                SimpleNamespace(type=pygame.JOYDEVICEADDED, device_index=1)
            )
        finally:
            pygame.joystick.Joystick = original  # type: ignore[misc]
        self.assertEqual(mgr.active_guid(), "want-this")


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


class CommandDispatchTests(unittest.TestCase):
    def test_title_navigation_and_confirm(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.state = "title"
            # Discard the run save so the Resume row is disabled and arrow nav
            # skips it (mirrors a fresh install).
            game.save_path.unlink(missing_ok=True)
            game.title_selection = 0
            # Down skips the disabled Resume row (no save) -> lands on Options.
            game._dispatch_command(Command.DOWN)
            self.assertEqual(game.title_selection, 2)
            game._dispatch_command(Command.CONFIRM)
            self.assertEqual(game.state, "options")

    def test_title_back_requests_exit_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.state = "title"
            game._dispatch_command(Command.BACK)
            self.assertEqual(game.state, "confirm_exit")

    def test_options_cursor_navigation_shared_with_gamepad(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.state = "options"
            game.options_cursor = 0
            game._dispatch_command(Command.DOWN)
            self.assertEqual(game.options_cursor, 1)
            game._dispatch_command(Command.DOWN)
            self.assertEqual(game.options_cursor, 2)
            game._dispatch_command(Command.UP)
            self.assertEqual(game.options_cursor, 1)

    def test_options_confirm_toggles_focused_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.state = "options"
            game.audio_enabled = True
            game.options_cursor = game.OPTIONS_ROW_AUDIO
            game._dispatch_command(Command.CONFIRM)
            self.assertFalse(game.audio_enabled)
            # Confirm again toggles back.
            game._dispatch_command(Command.CONFIRM)
            self.assertTrue(game.audio_enabled)

    def test_options_left_right_adjusts_ui_scale(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.state = "options"
            start = game.ui_scale
            game.options_cursor = game.OPTIONS_ROW_UI_SCALE
            game._dispatch_command(Command.RIGHT)
            self.assertEqual(game.ui_scale, min(4, start + 1))
            game._dispatch_command(Command.LEFT)
            self.assertEqual(game.ui_scale, start)

    def test_options_controller_toggle_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.state = "options"
            game.options_cursor = game.OPTIONS_ROW_CONTROLLER
            before = game.controller_enabled
            game._dispatch_command(Command.CONFIRM)
            self.assertNotEqual(game.controller_enabled, before)
            self.assertEqual(game.input.enabled, game.controller_enabled)

    def test_options_controls_row_opens_mapping_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.state = "options"
            game.options_cursor = game.OPTIONS_ROW_CONTROLS
            game._dispatch_command(Command.CONFIRM)
            self.assertEqual(game.state, "controls")
            game._dispatch_command(Command.BACK)
            self.assertEqual(game.state, "options")

    def test_controls_menu_remaps_selected_gamepad_button(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.state = "controls"
            game.controls_cursor = 1  # ability 2 / bolt
            game._dispatch_command(Command.CONFIRM)
            self.assertEqual(game.controls_capture_command, Command.ABILITY_2)
            event = SimpleNamespace(type=pygame.JOYBUTTONDOWN, joy=999, button=0)
            self.assertTrue(game.handle_controller_event(event))
            self.assertIsNone(game.controls_capture_command)
            self.assertEqual(
                game.gamepad_mapping["gameplay_buttons"][0], Command.ABILITY_2
            )

    def test_controls_menu_remaps_trigger_slot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.state = "controls"
            game.controls_capture_command = Command.INTERACT
            game.assign_gamepad_trigger_slot(0, Command.INTERACT)
            self.assertEqual(game.gamepad_mapping["triggers"][0], Command.INTERACT)
            self.assertEqual(game.input.trigger_commands[0], Command.INTERACT)

    def test_button_remap_clears_same_action_from_triggers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.gamepad_mapping = default_gamepad_mapping()
            game.input.trigger_commands = list(game.gamepad_mapping["triggers"])
            # Dash starts on LT by default. Moving Dash to a button must clear LT,
            # otherwise pressing the trigger still dashes even though the menu
            # shows the new button binding.
            self.assertEqual(game.gamepad_mapping["triggers"][0], Command.ABILITY_4)
            game._assign_gamepad_button(0, Command.ABILITY_4)
            self.assertEqual(
                game.gamepad_mapping["gameplay_buttons"][0], Command.ABILITY_4
            )
            self.assertEqual(game.gamepad_mapping["triggers"][0], "")
            self.assertEqual(game.input.trigger_commands[0], "")

    def test_trigger_remap_clears_same_action_from_buttons(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.gamepad_mapping = default_gamepad_mapping()
            # Potion starts on LB/button 4. Moving Potion to LT must clear LB so
            # one action does not live on multiple physical controls.
            self.assertEqual(
                game.gamepad_mapping["gameplay_buttons"][4], Command.ABILITY_5
            )
            self.assertEqual(
                game.gamepad_mapping["gameplay_buttons"][4], Command.ABILITY_5
            )
            game.assign_gamepad_trigger_slot(0, Command.ABILITY_5)
            self.assertEqual(game.gamepad_mapping["triggers"][0], Command.ABILITY_5)
            self.assertNotIn(4, game.gamepad_mapping["gameplay_buttons"])

    def test_archetype_select_left_right_and_confirm(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.state = "archetype_select"
            start = ARCHETYPES.index(game.selected_archetype)
            game._dispatch_command(Command.RIGHT)
            self.assertEqual(
                ARCHETYPES.index(game.selected_archetype),
                (start + 1) % len(ARCHETYPES),
            )
            game._dispatch_command(Command.LEFT)
            self.assertEqual(ARCHETYPES.index(game.selected_archetype), start)
            game._dispatch_command(Command.BACK)
            self.assertEqual(game.state, "title")

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

    def test_shop_overlay_navigation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            from arch_rogue.models import Shopkeeper

            keeper = Shopkeeper(
                x=game.player.x,
                y=game.player.y,
                name="Keeper",
                role="merchant",
                inventory=[],
            )
            game.shopkeepers = [keeper]
            game.open_shop(keeper)
            self.assertTrue(game.shop_open)
            game.shop_cursor = 0
            game._dispatch_command(Command.TAB)
            # cycle_shop_mode alternates buy/sell.
            self.assertIn(game.shop_mode, ("buy", "sell"))
            game._dispatch_command(Command.BACK)
            self.assertFalse(game.shop_open)

    def test_character_menu_tab_switches(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.character_menu_open = True
            game.character_menu_tab = "overview"
            game._dispatch_command(Command.TAB)
            self.assertEqual(game.character_menu_tab, "skill_tree")
            self.assertIsNotNone(game.character_menu_hovered_node)
            game._dispatch_command(Command.TAB)
            self.assertEqual(game.character_menu_tab, "overview")
            game._dispatch_command(Command.BACK)
            self.assertFalse(game.character_menu_open)

    def test_character_skill_tree_cursor_moves_and_confirm_upgrades(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.character_menu_open = True
            game.character_menu_tab = "skill_tree"
            game.player.skill_points = 1
            choices = game.available_skill_choices()
            self.assertGreater(len(choices), 0)
            game.character_menu_hovered_node = choices[0].key
            before = set(game.player.skill_upgrades)
            game._dispatch_command(Command.RIGHT)
            self.assertIsNotNone(game.character_menu_hovered_node)
            # Put the cursor back on an available node and press A/confirm.
            game.character_menu_hovered_node = choices[0].key
            game._dispatch_command(Command.CONFIRM)
            self.assertIn(choices[0].key, game.player.skill_upgrades)
            self.assertEqual(game.player.skill_points, 0)
            self.assertNotEqual(before, set(game.player.skill_upgrades))

    def test_gameplay_ability_commands_fire_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            # Give the player enough mana and clear cooldowns so the bolt cast
            # actually produces a projectile (proving the command wired through).
            game.player.mana = 100
            game.player.bolt_timer = 0.0
            before = len(game.projectiles)
            game._dispatch_command(Command.ABILITY_2)  # cast bolt
            self.assertGreater(len(game.projectiles), before)

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

    def test_gamepad_back_skips_mandatory_story_intro_with_default_choice(self) -> None:
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
            game._dispatch_command(Command.BACK)
            self.assertFalse(game.story_intro_pending)
            self.assertIsNone(game.active_cutscene)

    def test_gameplay_interact_and_inventory_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game._dispatch_command(Command.INVENTORY)
            self.assertTrue(game.inventory_open)
            game._dispatch_command(Command.INVENTORY)
            self.assertFalse(game.inventory_open)
            game._dispatch_command(Command.CHARACTER)
            self.assertTrue(game.character_menu_open)


class CombatAxisIntegrationTests(unittest.TestCase):
    def test_left_stick_drives_movement(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            start_x = game.player.x
            # Inject a rightward left-stick vector.
            game.input._left_vec = (1.0, 0.0)
            game.update_player(0.5)
            self.assertGreater(game.player.x, start_x)
            self.assertAlmostEqual(game.player.facing_x, 1.0, places=4)

    def test_analog_magnitude_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            start_x = game.player.x
            # Half-deflection should move roughly half as far as full deflection.
            game.input._left_vec = (0.5, 0.0)
            game.update_player(0.5)
            half = game.player.x - start_x
            game.player.x = start_x
            game.input._left_vec = (1.0, 0.0)
            game.update_player(0.5)
            full = game.player.x - start_x
            self.assertAlmostEqual(half, full * 0.5, places=3)

    def test_right_stick_drives_aim(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.input._right_vec = (0.0, 1.0)  # aim down
            game.update_player_aim()
            self.assertAlmostEqual(game.player.facing_x, 0.0, places=4)
            self.assertAlmostEqual(game.player.facing_y, 1.0, places=4)

    def test_right_stick_aim_survives_left_stick_movement(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.input._right_vec = (0.0, 1.0)  # aim down
            game.input._left_vec = (1.0, 0.0)  # move right
            game.update_player_aim()
            game.update_player(0.1)
            self.assertAlmostEqual(game.player.facing_x, 0.0, places=4)
            self.assertAlmostEqual(game.player.facing_y, 1.0, places=4)

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

    def test_controller_bolt_uses_existing_aim_cone_when_stick_neutral(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.input._right_vec = (0.0, 0.0)
            # The visible aim cone is represented by player.facing_x/y.
            game.player.facing_x = 0.0
            game.player.facing_y = 1.0
            game.player.mana = 100
            game.player.bolt_timer = 0.0
            before = len(game.projectiles)
            game._dispatch_command(Command.ABILITY_2)
            self.assertEqual(len(game.projectiles), before + 1)
            bolt = game.projectiles[-1]
            self.assertAlmostEqual(bolt.vx, 0.0, places=4)
            self.assertGreater(bolt.vy, 0.0)

    def test_button_axis_overlap_does_not_also_fire_trigger_dash(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            fake = FakeJoystick(44, num_axes=6, axes_rest=(0, 0, 0, 0, -1, -1))
            game.input._joysticks[fake.get_instance_id()] = fake
            game.input._axis_layout[fake.get_instance_id()] = (
                game.input._compute_layout(fake)
            )
            game.input._trigger_layout[fake.get_instance_id()] = (
                game.input._compute_triggers(fake)
            )
            game.input._active_id = fake.get_instance_id()
            game.input._layout_id = None
            # Simulate a controller that reports LB as button 4 and also moves the
            # first trigger-like axis. The button is mapped to potion, so this must
            # not queue the default dash trigger command.
            fake.set_axis(4, 1.0)
            event = SimpleNamespace(
                type=pygame.JOYBUTTONDOWN,
                joy=fake.get_instance_id(),
                button=4,
            )
            game.handle_controller_event(event)
            self.assertEqual(game.input.drain_trigger_commands(), [])
            game.input.poll_axes()
            self.assertEqual(game.input.drain_trigger_commands(), [])

    def test_controller_button_fire_polls_fresh_right_stick_aim(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            fake = FakeJoystick(99, num_axes=4, axes_rest=(0, 0, 0, 0))
            game.input._joysticks[fake.get_instance_id()] = fake
            game.input._axis_layout[fake.get_instance_id()] = (
                game.input._compute_layout(fake)
            )
            game.input._trigger_layout[fake.get_instance_id()] = (
                game.input._compute_triggers(fake)
            )
            # Move the stick after rest layout detection, like a real controller.
            fake.set_axis(2, 0.0)
            fake.set_axis(3, 1.0)  # right stick down
            game.input._active_id = fake.get_instance_id()
            game.input._layout_id = None
            game.input._right_vec = (0.0, 0.0)  # stale aim before the button press
            game.player.facing_x = 1.0
            game.player.facing_y = 0.0
            game.player.mana = 100
            game.player.bolt_timer = 0.0

            event = SimpleNamespace(
                type=pygame.JOYBUTTONDOWN,
                joy=fake.get_instance_id(),
                button=2,  # X -> bolt in gameplay context
            )
            game.handle_controller_event(event)

            self.assertGreater(len(game.projectiles), 0)
            bolt = game.projectiles[-1]
            self.assertAlmostEqual(bolt.vx, 0.0, places=4)
            self.assertGreater(bolt.vy, 0.0)


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
            self.assertEqual(data["schema_version"], 3)
            self.assertIn("gamepad_mapping", data)

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
            self.assertTrue(game.load_options())
            # Missing controller fields default to enabled / no preferred device.
            self.assertTrue(game.controller_enabled)
            self.assertEqual(game.last_controller_guid, "")
            # Other fields still load correctly.
            self.assertTrue(game.audio_enabled)


class MenuConsistencyTests(unittest.TestCase):
    def test_keyboard_arrows_navigate_options_cursor(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.state = "options"
            game.options_cursor = 0
            # Simulate a KEYDOWN arrow-down via the unified key_command path.
            cmd = key_command(pygame.K_DOWN, 0)
            self.assertEqual(cmd, Command.DOWN)
            game._dispatch_command(cmd)
            self.assertEqual(game.options_cursor, 1)

    def test_options_menu_renders_cursor_and_controller_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.state = "options"
            game.options_cursor = 2
            # Should not raise; the renderer reads the cursor + controller row.
            game.draw_options_menu()

    def test_controls_menu_renders(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.state = "controls"
            game.draw_controls_menu()

    def test_controller_back_mirrors_keyboard_escape_in_overlays(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.inventory_open = True
            game._dispatch_command(Command.BACK)
            self.assertFalse(game.inventory_open)
            game.character_menu_open = True
            game._dispatch_command(Command.BACK)
            self.assertFalse(game.character_menu_open)


if __name__ == "__main__":
    unittest.main()
