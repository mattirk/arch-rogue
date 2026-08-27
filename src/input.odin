package archrogue

// Raylib-free desktop input resolution. main.odin samples platform state into
// this flat snapshot; tests exercise the exact desktop bindings without
// opening a window or linking input behavior to render timing.

import "core:math"

// Platform adapters translate raw key/button enums into these commands. The
// state machine and remapping code never import raylib or assume its ordinals.
Input_Command :: enum u8 {
	None,
	Up,
	Down,
	Left,
	Right,
	Confirm,
	Back,
	Tab,
	Help,
	Interact,
	Inventory,
	Character,
	Ability_1,
	Ability_2,
	Ability_3,
	Ability_4,
	Ability_5,
	Ability_6,
	Minimap_Zoom_In,
	Minimap_Zoom_Out,
}

@(rodata)
INPUT_COMMAND_LABELS := [Input_Command]string{
	.None = "Unbound",
	.Up = "Up",
	.Down = "Down",
	.Left = "Left",
	.Right = "Right",
	.Confirm = "Confirm",
	.Back = "Back / Pause",
	.Tab = "Next tab",
	.Help = "Help",
	.Interact = "Interact",
	.Inventory = "Inventory",
	.Character = "Character",
	.Ability_1 = "Ability 1",
	.Ability_2 = "Ability 2",
	.Ability_3 = "Ability 3",
	.Ability_4 = "Ability 4",
	.Ability_5 = "Health potion",
	.Ability_6 = "Mana potion",
	.Minimap_Zoom_In = "Zoom minimap in",
	.Minimap_Zoom_Out = "Zoom minimap out",
}

// Apply one semantic controller command to the same platform-free Intent used
// by keyboard/mouse input. Menu Y/Help is the inventory drop shortcut; other
// menu surfaces simply ignore that field.
intent_apply_command :: proc(intent:^Intent,command:Input_Command,gameplay:bool) {
	if intent==nil do return
	switch command {
	case .None:
	case .Help:
		if !gameplay do intent.inv_drop = true
	case .Up: intent.menu_delta-=1
	case .Down: intent.menu_delta+=1
	case .Left: intent.menu_horizontal-=1
	case .Right: intent.menu_horizontal+=1
	case .Confirm: intent.confirm=true
	case .Back: intent.back=true
	case .Tab: intent.tab=true
	case .Interact: intent.interact=true
	case .Inventory: intent.toggle_inventory=true
	case .Character: intent.open_character=true
	case .Ability_1: intent.actions[0]=true
	case .Ability_2: intent.actions[1]=true
	case .Ability_3: intent.actions[2]=true
	case .Ability_4: intent.actions[3]=true
	case .Ability_5: intent.use_heal=true
	case .Ability_6: intent.use_mana=true
	case .Minimap_Zoom_In: intent.minimap_zoom+=1
	case .Minimap_Zoom_Out: intent.minimap_zoom-=1
	}
}

Controller_Button :: enum u8 {
	A,
	B,
	X,
	Y,
	Left_Bumper,
	Right_Bumper,
	Back,
	Start,
	Left_Stick,
	Right_Stick,
	Dpad_Up,
	Dpad_Down,
	Dpad_Left,
	Dpad_Right,
}

Controller_Trigger :: enum u8 {
	Left,
	Right,
}

Controller_Context :: enum {
	Menu,
	Gameplay,
}

@(rodata)
CONTROLLER_BUTTON_LABELS := [Controller_Button]string{
	.A = "A",
	.B = "B",
	.X = "X",
	.Y = "Y",
	.Left_Bumper = "LB",
	.Right_Bumper = "RB",
	.Back = "Back / View",
	.Start = "Start / Menu",
	.Left_Stick = "Left stick",
	.Right_Stick = "Right stick",
	.Dpad_Up = "D-pad Up",
	.Dpad_Down = "D-pad Down",
	.Dpad_Left = "D-pad Left",
	.Dpad_Right = "D-pad Right",
}

@(rodata)
CONTROLLER_TRIGGER_LABELS := [Controller_Trigger]string{
	.Left = "LT",
	.Right = "RT",
}

// Menu navigation is fixed. Gameplay actions are remappable except for the
// D-pad: it always navigates menus and only Up/Down zoom the minimap in play.
@(rodata)
CONTROLLER_MENU_BUTTON_BINDINGS := [Controller_Button]Input_Command{
	.A = .Confirm,
	.B = .Back,
	.X = .Interact,
	.Y = .Help,
	.Left_Bumper = .Back,
	.Right_Bumper = .Tab,
	.Back = .Back,
	.Start = .Character,
	.Left_Stick = .None,
	.Right_Stick = .None,
	.Dpad_Up = .Up,
	.Dpad_Down = .Down,
	.Dpad_Left = .Left,
	.Dpad_Right = .Right,
}

@(rodata)
DEFAULT_CONTROLLER_GAMEPLAY_BINDINGS := [Controller_Button]Input_Command{
	.A = .Interact,
	.B = .Ability_3,
	.X = .Ability_2,
	.Y = .Ability_5,
	.Left_Bumper = .Back,
	.Right_Bumper = .Ability_6,
	.Back = .Inventory,
	.Start = .Character,
	.Left_Stick = .None,
	.Right_Stick = .None,
	.Dpad_Up = .None,
	.Dpad_Down = .None,
	.Dpad_Left = .None,
	.Dpad_Right = .None,
}

@(rodata)
DEFAULT_CONTROLLER_TRIGGER_BINDINGS := [Controller_Trigger]Input_Command{
	.Left = .Ability_1,
	.Right = .Ability_4,
}

@(rodata)
CONTROLLER_REMAPPABLE_COMMANDS := [10]Input_Command{
	.Ability_1,
	.Ability_2,
	.Ability_3,
	.Ability_4,
	.Ability_5,
	.Ability_6,
	.Interact,
	.Inventory,
	.Character,
	.Back,
}

Controller_Mapping :: struct {
	gameplay_buttons: [Controller_Button]Input_Command,
	triggers:         [Controller_Trigger]Input_Command,
}

controller_default_mapping :: proc() -> Controller_Mapping {
	return {
		gameplay_buttons = DEFAULT_CONTROLLER_GAMEPLAY_BINDINGS,
		triggers = DEFAULT_CONTROLLER_TRIGGER_BINDINGS,
	}
}

input_command_is_valid :: proc(command: Input_Command) -> bool {
	i := int(command)
	return i >= 0 && i < len(Input_Command)
}

controller_command_is_remappable :: proc(command: Input_Command) -> bool {
	for candidate in CONTROLLER_REMAPPABLE_COMMANDS {
		if command == candidate do return true
	}
	return false
}

controller_button_is_valid :: proc(button: Controller_Button) -> bool {
	i := int(button)
	return i >= 0 && i < len(Controller_Button)
}

controller_button_is_dpad :: proc(button: Controller_Button) -> bool {
	return button == .Dpad_Up || button == .Dpad_Down ||
		button == .Dpad_Left || button == .Dpad_Right
}

controller_trigger_is_valid :: proc(trigger: Controller_Trigger) -> bool {
	i := int(trigger)
	return i >= 0 && i < len(Controller_Trigger)
}

controller_button_command :: proc(
	mapping: ^Controller_Mapping,
	button: Controller_Button,
	ctx: Controller_Context,
) -> Input_Command {
	if mapping == nil || !controller_button_is_valid(button) do return .None
	if ctx == .Menu {
		// Character is an overlay toggle: the remapped gameplay button must
		// close the sheet as well as open it. Other gameplay actions never
		// bleed into menu navigation.
		if mapping.gameplay_buttons[button] == .Character do return .Character
		return CONTROLLER_MENU_BUTTON_BINDINGS[button]
	}
	#partial switch button {
	case .Dpad_Up:   return .Minimap_Zoom_In
	case .Dpad_Down: return .Minimap_Zoom_Out
	case .Dpad_Left, .Dpad_Right: return .None
	case: return mapping.gameplay_buttons[button]
	}
}

controller_trigger_command :: proc(
	mapping: ^Controller_Mapping,
	trigger: Controller_Trigger,
) -> Input_Command {
	if mapping == nil || !controller_trigger_is_valid(trigger) do return .None
	return mapping.triggers[trigger]
}

controller_binding_label :: proc(mapping: ^Controller_Mapping, command: Input_Command) -> string {
	if mapping == nil do return "Unbound"
	for button in Controller_Button {
		if mapping.gameplay_buttons[button] == command do return CONTROLLER_BUTTON_LABELS[button]
	}
	for trigger in Controller_Trigger {
		if mapping.triggers[trigger] == command do return CONTROLLER_TRIGGER_LABELS[trigger]
	}
	return "Unbound"
}

controller_clear_command_bindings :: proc(mapping: ^Controller_Mapping, command: Input_Command) {
	if mapping == nil do return
	for button in Controller_Button {
		if mapping.gameplay_buttons[button] == command do mapping.gameplay_buttons[button] = .None
	}
	for trigger in Controller_Trigger {
		if mapping.triggers[trigger] == command do mapping.triggers[trigger] = .None
	}
}

Controller_Remap_Result :: enum {
	Applied,
	Rejected_Fixed_Input,
	Rejected_Invalid_Input,
	Rejected_Command,
}

// Assigning a command moves it from its previous button/trigger. If the target
// already held another command, that displaced command becomes unbound, which
// matches the Pygame controls menu's collision behavior.
controller_remap_button :: proc(
	mapping: ^Controller_Mapping,
	button: Controller_Button,
	command: Input_Command,
) -> Controller_Remap_Result {
	if mapping == nil || !controller_button_is_valid(button) do return .Rejected_Invalid_Input
	if controller_button_is_dpad(button) do return .Rejected_Fixed_Input
	if !controller_command_is_remappable(command) do return .Rejected_Command
	controller_clear_command_bindings(mapping, command)
	mapping.gameplay_buttons[button] = command
	return .Applied
}

controller_remap_trigger :: proc(
	mapping: ^Controller_Mapping,
	trigger: Controller_Trigger,
	command: Input_Command,
) -> Controller_Remap_Result {
	if mapping == nil || !controller_trigger_is_valid(trigger) do return .Rejected_Invalid_Input
	if !controller_command_is_remappable(command) do return .Rejected_Command
	controller_clear_command_bindings(mapping, command)
	mapping.triggers[trigger] = command
	return .Applied
}

// Repair malformed/persisted mappings deterministically: buttons win over
// triggers, and the first semantic button/trigger wins within each group.
controller_mapping_normalize :: proc(mapping: ^Controller_Mapping) {
	if mapping == nil do return
	seen: [Input_Command]bool
	for button in Controller_Button {
		command := mapping.gameplay_buttons[button]
		if controller_button_is_dpad(button) || !controller_command_is_remappable(command) {
			mapping.gameplay_buttons[button] = .None
			continue
		}
		if seen[command] {
			mapping.gameplay_buttons[button] = .None
		} else {
			seen[command] = true
		}
	}
	for trigger in Controller_Trigger {
		command := mapping.triggers[trigger]
		if !controller_command_is_remappable(command) || seen[command] {
			mapping.triggers[trigger] = .None
		} else {
			seen[command] = true
		}
	}
}

CONTROLLER_DEADZONE            :: f32(0.24)
CONTROLLER_DEADZONE_ACTIVATION :: f32(0.28)
CONTROLLER_DEADZONE_RELEASE    :: CONTROLLER_DEADZONE
CONTROLLER_TRIGGER_THRESHOLD   :: f32(0.25)
CONTROLLER_MENU_ACTIVATION     :: f32(0.50)
CONTROLLER_MENU_RELEASE        :: f32(0.30)

Controller_Stick_State :: struct {
	active: bool,
}

// Radial deadzone with separate activation/release thresholds. In the latched
// band (0.24, 0.28), interpolate down to zero so drift releases cleanly while
// deliberate movement retains the established radial response curve.
controller_resolve_stick :: proc(raw: Vec2, state: ^Controller_Stick_State) -> Vec2 {
	if state == nil do return {}
	magnitude := math.hypot(raw.x, raw.y)
	threshold := state.active ? CONTROLLER_DEADZONE_RELEASE : CONTROLLER_DEADZONE_ACTIVATION
	if magnitude <= threshold {
		state.active = false
		return {}
	}

	scaled_magnitude: f32
	if magnitude < CONTROLLER_DEADZONE_ACTIVATION {
		activation_magnitude :=
			(CONTROLLER_DEADZONE_ACTIVATION - CONTROLLER_DEADZONE) /
			(1 - CONTROLLER_DEADZONE)
		scaled_magnitude = activation_magnitude *
			((magnitude - CONTROLLER_DEADZONE_RELEASE) /
			(CONTROLLER_DEADZONE_ACTIVATION - CONTROLLER_DEADZONE_RELEASE))
	} else {
		scaled_magnitude = min(
			f32(1),
			(magnitude - CONTROLLER_DEADZONE) / (1 - CONTROLLER_DEADZONE),
		)
	}
	state.active = true
	return raw * (scaled_magnitude / magnitude)
}

Controller_Trigger_State :: struct {
	pressed: bool,
}

Controller_Trigger_Edge :: enum {
	None,
	Pressed,
	Released,
}

// Browser-standard gamepads commonly expose LT/RT as buttons 6/7 and report
// only four stick axes. Prefer the digital/pressure-button signal when down,
// while retaining the analog trigger axis used by native raylib backends.
controller_trigger_sample :: proc(axis_available: bool, axis_value: f32, button_down: bool) -> f32 {
	if button_down do return 1
	if axis_available do return axis_value
	return 0
}

controller_resolve_trigger :: proc(value: f32, state: ^Controller_Trigger_State) -> Controller_Trigger_Edge {
	if state == nil do return .None
	pressed := value > CONTROLLER_TRIGGER_THRESHOLD
	if pressed == state.pressed do return .None
	state.pressed = pressed
	return pressed ? .Pressed : .Released
}

Controller_Menu_Stick_State :: struct {
	active: bool,
}

// `stick` is the already deadzone-resolved left-stick vector. Emit exactly one
// dominant-axis menu command per push; ties resolve vertically as in Pygame.
controller_resolve_menu_stick :: proc(
	stick: Vec2,
	state: ^Controller_Menu_Stick_State,
) -> Input_Command {
	if state == nil do return .None
	magnitude := math.hypot(stick.x, stick.y)
	if !state.active {
		if magnitude < CONTROLLER_MENU_ACTIVATION do return .None
		state.active = true
		if abs(stick.x) > abs(stick.y) {
			return stick.x > 0 ? .Right : .Left
		}
		return stick.y > 0 ? .Down : .Up
	}
	if magnitude < CONTROLLER_MENU_RELEASE do state.active = false
	return .None
}

Desktop_Input :: struct {
	left:  bool,
	right: bool,
	up:    bool,
	down:  bool,

	aim:          Vec2,
	mouse_left:   bool,
	mouse_left_pressed: bool,
	mouse_press_aim:    Vec2,
	mouse_right:  bool, // deliberately inert: pygame has no RMB gameplay action
	mouse_target: Vec2,

	abilities:       [6]bool, // discrete presses for keys 1..6
	ability1_released: bool,
	interact:         bool,
	inventory:        bool,
	tab:              bool, // consumed only while the inventory overlay is open
	back:             bool,
}

Menu_Click_Context :: enum {
	None,
	Inventory,
	Shop,
	Shop_Buy,
	Shop_Sell,
}

MENU_MOUSE_DOUBLE_CLICK_SECONDS :: 0.45

Desktop_Click_State :: struct {
	click_context: Menu_Click_Context,
	index:   int,
	time:    f64,
	valid:   bool,
}

// Register one menu click. Only the same row in the same menu inside the
// Pygame 0.45-second interval confirms; a successful pair is consumed.
desktop_register_menu_click :: proc(
	state: ^Desktop_Click_State,
	click_context: Menu_Click_Context,
	index: int,
	now: f64,
) -> bool {
	double := state.valid &&
		state.click_context == click_context &&
		state.index == index &&
		now >= state.time &&
		now - state.time <= MENU_MOUSE_DOUBLE_CLICK_SECONDS
	if double {
		state.valid = false
		return true
	}
	state.click_context = click_context
	state.index = index
	state.time = now
	state.valid = true
	return false
}

desktop_archetype_click_intent :: proc(selected_index, clicked_index: int) -> Intent {
	if clicked_index < 0 || clicked_index >= len(Archetype_Id) do return {}
	return {
		menu_index = clicked_index,
		menu_index_valid = true,
		confirm = clicked_index == selected_index,
		pointer_confirm = clicked_index == selected_index,
	}
}

// Arrow keys follow the screen compass: Up walks screen-north, which is the
// tile-space diagonal (-1,-1) under the 2:1 iso projection. Two adjacent
// arrows sum to a tile axis, so screen-diagonal walking hugs the grid.
// tick_player clamps the magnitude, so the diagonal sums stay full speed.
desktop_move_vector :: proc(left, right, up, down: bool) -> Vec2 {
	move: Vec2
	if right do move += {1, -1}
	if left  do move += {-1, 1}
	if down  do move += {1, 1}
	if up    do move += {-1, -1}
	return move
}

// A stick deflection is a screen-space direction. Return the tile-space move
// with the same magnitude so analog walk speed survives the projection; this
// is the exact conversion the mobile virtual joystick already applies.
screen_stick_to_tile_vector :: proc(screen: Vec2) -> Vec2 {
	magnitude := min(f32(1), math.hypot(screen.x, screen.y))
	if magnitude <= 0 do return {}
	world := Vec2{
		screen.x / TILE_W + screen.y / TILE_H,
		screen.y / TILE_H - screen.x / TILE_W,
	}
	world_length := math.hypot(world.x, world.y)
	if world_length <= 0 do return {}
	return world / world_length * magnitude
}

CONTROLLER_AIM_SNAP_RANGE :: f32(5.0)
CONTROLLER_AIM_SNAP_DOT   :: f32(0.86)

// Snap a live right-stick direction toward the closest visible target near
// that aim line. Angle dominates the score; distance is only a light
// tiebreaker, matching combat/aim.py. The caller keeps mouse/keyboard aim out
// of this helper so controller assistance never changes desktop targeting.
controller_snap_aim :: proc(run: ^Run, aim: Vec2) -> Vec2 {
	if run == nil do return aim
	magnitude := math.hypot(aim.x, aim.y)
	if magnitude <= 0.001 do return aim
	facing := aim / magnitude
	best_score := max(f32)
	best_aim := aim
	found := false
	for &enemy in run.enemies {
		if enemy.hp <= 0 do continue
		to := enemy.pos - run.player.pos
		distance := math.hypot(to.x, to.y)
		if distance <= 0.001 || distance > CONTROLLER_AIM_SNAP_RANGE + enemy_hit_radius(&enemy) do continue
		tx, ty := int(enemy.pos.x), int(enemy.pos.y)
		if !dungeon_in_bounds(tx, ty) || !run.visible[tx][ty] do continue
		if !line_of_sight(&run.dungeon, run.player.pos.x, run.player.pos.y, enemy.pos.x, enemy.pos.y) do continue
		direction := to / distance
		dot := direction.x * facing.x + direction.y * facing.y
		if dot < CONTROLLER_AIM_SNAP_DOT do continue
		score := (1 - dot) * 2 + distance * 0.04
		if score < best_score {
			best_score = score
			best_aim = direction
			found = true
		}
	}
	return found ? best_aim : aim
}

controller_scene_aim :: proc(run:^Run,aim:Vec2,allow_target_snap:=true)->Vec2 {
	if !allow_target_snap do return aim
	return controller_snap_aim(run,aim)
}

desktop_gameplay_intent :: proc(input: Desktop_Input, archetype: Archetype_Id) -> Intent {
	_ = archetype // slots are uniform in M8; retained for the stable resolver API
	intent: Intent
	intent.move = desktop_move_vector(input.left, input.right, input.up, input.down)
	intent.aim = input.aim
	intent.mouse_target = input.mouse_target
	// Keyboard movement has priority over held-LMB walking.
	intent.mouse_walk = input.mouse_left && intent.move == {}
	intent.mouse_press = input.mouse_left_pressed
	intent.mouse_press_aim = input.mouse_press_aim
	intent.mouse_released = !input.mouse_left
	for i in 0 ..< 4 do intent.actions[i] = input.abilities[i]
	intent.action1_released = input.ability1_released
	intent.use_heal = input.abilities[4]
	intent.use_mana = input.abilities[5]
	intent.interact = input.interact
	intent.toggle_inventory = input.inventory
	intent.back = input.back
	// Minimap input is contextual (Ctrl+M or wheel-over-card), so raw desktop
	// gameplay input deliberately cannot carry it into the merge a second time.
	// input.mouse_right and input.tab intentionally produce no gameplay action.
	return intent
}
