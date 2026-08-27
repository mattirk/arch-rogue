package archrogue

// MX-android's raylib-free mobile core. Platform code supplies physical display
// metrics, stable touch IDs, camera values, and lifecycle events. This module
// owns deterministic layout, touch-role reduction, and fixed-step suspension;
// no mobile type enters Run or the persistence payload.

import "core:math"

MOBILE_MINIMUM_TARGET_DP       :: f32(48)
MOBILE_JOYSTICK_DEADZONE       :: f32(0.12)
MOBILE_PINCH_MINIMUM_PIXELS    :: f32(24)
MOBILE_PINCH_DEADZONE_RATIO    :: f32(0.015)
MOBILE_MAX_TOUCH_CONTACTS      :: 10
MOBILE_MAX_TOUCH_EVENTS        :: MOBILE_MAX_TOUCH_CONTACTS * 2
MOBILE_MAX_DIRECT_TARGETS      :: 128
MOBILE_STATUS_BAR_ASPECT       :: f32(98) / f32(455)
MOBILE_MINIMAP_ASPECT          :: f32(MINIMAP_CARD_WIDTH) / f32(MINIMAP_CARD_HEIGHT)
MOBILE_MINIMAP_HEIGHT_FRACTION :: f32(0.16)
MOBILE_MINIMAP_WIDTH_FRACTION  :: f32(0.22)
MOBILE_GEOMETRY_EPSILON        :: f32(0.001)

// --- Physical geometry ------------------------------------------------------

Mobile_Pixel_Insets :: struct {
	left:   int,
	top:    int,
	right:  int,
	bottom: int,
}

Mobile_Rect :: struct {
	x:      f32,
	y:      f32,
	width:  f32,
	height: f32,
}

Mobile_Display_Metrics :: struct {
	surface_width:  int,
	surface_height: int,
	density:        f32, // physical pixels per Android dp
	cutout:         Mobile_Pixel_Insets,
	system_gesture: Mobile_Pixel_Insets,
	revision:       u64,
}

Mobile_Layout_Status :: enum {
	Valid,
	Unsupported_Portrait,
	Too_Small,
}

Mobile_Layout :: struct {
	revision:          u64,
	display_rect:      Mobile_Rect,
	safe_rect:         Mobile_Rect,
	world_viewport:    Mobile_Rect, // deliberately the complete physical surface
	gameplay_rect:     Mobile_Rect, // unobstructed space between the two rails
	left_rail:         Mobile_Rect,
	right_rail:        Mobile_Rect,
	world_focus:       Vec2,
	minimap:           Mobile_Rect,
	joystick:          Mobile_Rect,
	action_slots:      [6]Mobile_Rect,
	interact:          Mobile_Rect,
	inventory:         Mobile_Rect,
	character:         Mobile_Rect,
	pause:             Mobile_Rect,
	resource_bars:     [4]Mobile_Rect,
	minimum_target_px: f32,
}

mobile_rect_right :: proc(rect: Mobile_Rect) -> f32 {
	return rect.x + rect.width
}

mobile_rect_bottom :: proc(rect: Mobile_Rect) -> f32 {
	return rect.y + rect.height
}

mobile_rect_center :: proc(rect: Mobile_Rect) -> Vec2 {
	return {rect.x + rect.width * .5, rect.y + rect.height * .5}
}

mobile_rect_contains :: proc(rect: Mobile_Rect, point: Vec2) -> bool {
	return rect.width > 0 && rect.height > 0 &&
		point.x >= rect.x && point.y >= rect.y &&
		point.x < mobile_rect_right(rect) && point.y < mobile_rect_bottom(rect)
}

mobile_rect_contains_rect :: proc(outer, inner: Mobile_Rect) -> bool {
	return outer.width >= 0 && outer.height >= 0 && inner.width >= 0 && inner.height >= 0 &&
		inner.x + MOBILE_GEOMETRY_EPSILON >= outer.x &&
		inner.y + MOBILE_GEOMETRY_EPSILON >= outer.y &&
		mobile_rect_right(inner) <= mobile_rect_right(outer) + MOBILE_GEOMETRY_EPSILON &&
		mobile_rect_bottom(inner) <= mobile_rect_bottom(outer) + MOBILE_GEOMETRY_EPSILON
}

mobile_rects_overlap :: proc(a, b: Mobile_Rect) -> bool {
	return a.width > 0 && a.height > 0 && b.width > 0 && b.height > 0 &&
		a.x < mobile_rect_right(b) && mobile_rect_right(a) > b.x &&
		a.y < mobile_rect_bottom(b) && mobile_rect_bottom(a) > b.y
}

mobile_insets_union :: proc(a, b: Mobile_Pixel_Insets) -> Mobile_Pixel_Insets {
	return {
		left   = max(a.left, b.left),
		top    = max(a.top, b.top),
		right  = max(a.right, b.right),
		bottom = max(a.bottom, b.bottom),
	}
}

// Clamp sequentially so even hostile/vendor-broken values leave a non-negative
// one-pixel safe rectangle instead of making opposite insets cross.
mobile_insets_clamp :: proc(insets: Mobile_Pixel_Insets, width, height: int) -> Mobile_Pixel_Insets {
	w := max(1, width)
	h := max(1, height)
	left := clamp(insets.left, 0, w - 1)
	right := clamp(insets.right, 0, w - left - 1)
	top := clamp(insets.top, 0, h - 1)
	bottom := clamp(insets.bottom, 0, h - top - 1)
	return {left, top, right, bottom}
}

mobile_density :: proc(metrics: Mobile_Display_Metrics) -> f32 {
	density := metrics.density
	if density <= 0 || math.is_nan(density) || math.is_inf(density) do return 1
	return density
}

mobile_minimum_target_px :: proc(metrics: Mobile_Display_Metrics) -> f32 {
	return max(f32(1), math.ceil(MOBILE_MINIMUM_TARGET_DP * mobile_density(metrics)))
}

mobile_safe_rect :: proc(metrics: Mobile_Display_Metrics) -> Mobile_Rect {
	width := max(1, metrics.surface_width)
	height := max(1, metrics.surface_height)
	combined := mobile_insets_union(metrics.cutout, metrics.system_gesture)
	insets := mobile_insets_clamp(combined, width, height)
	return {
		x = f32(insets.left),
		y = f32(insets.top),
		width = f32(max(1, width - insets.left - insets.right)),
		height = f32(max(1, height - insets.top - insets.bottom)),
	}
}

mobile_rect_expand_to_minimum :: proc(
	rect: Mobile_Rect,
	minimum: f32,
	bounds: Mobile_Rect,
) -> Mobile_Rect {
	if rect.width <= 0 || rect.height <= 0 || bounds.width <= 0 || bounds.height <= 0 do return {}
	width := min(bounds.width, max(rect.width, minimum))
	height := min(bounds.height, max(rect.height, minimum))
	center := mobile_rect_center(rect)
	x := clamp(center.x - width * .5, bounds.x, mobile_rect_right(bounds) - width)
	y := clamp(center.y - height * .5, bounds.y, mobile_rect_bottom(bounds) - height)
	return {x, y, width, height}
}

mobile_resource_fill_rect :: proc(container: Mobile_Rect, ratio: f32) -> Mobile_Rect {
	if container.width <= 0 || container.height <= 0 do return {}
	amount := ratio
	if math.is_nan(amount) || math.is_inf(amount) do amount = 0
	amount = clamp(amount, f32(0), f32(1))
	height := container.height * amount
	return {
		x = container.x,
		y = mobile_rect_bottom(container) - height,
		width = container.width,
		height = height,
	}
}

// One layout owns both drawing and hit-testing. Primary touch controls are
// physical-size constrained; unsupported surfaces fail explicitly rather than
// silently overlapping controls.
mobile_layout_build :: proc(metrics: Mobile_Display_Metrics) -> (layout: Mobile_Layout, status: Mobile_Layout_Status) {
	width := max(1, metrics.surface_width)
	height := max(1, metrics.surface_height)
	layout.revision = metrics.revision
	layout.display_rect = {0, 0, f32(width), f32(height)}
	layout.world_viewport = layout.display_rect
	layout.safe_rect = mobile_safe_rect(metrics)
	layout.minimum_target_px = mobile_minimum_target_px(metrics)
	if width < height do return layout, .Unsupported_Portrait

	safe := layout.safe_rect
	density := mobile_density(metrics)
	minimum := layout.minimum_target_px
	outer := clamp(8 * density, f32(8), max(f32(8), safe.height * .03))
	rail_gap := clamp(6 * density, f32(6), max(f32(6), safe.height * .02))
	action_gap := max(4 * density, safe.height * .008)
	rail_height := safe.height - outer * 2
	if rail_height <= 0 do return layout, .Too_Small

	max_action := (rail_height - action_gap * 5) / 6
	if max_action < minimum do return layout, .Too_Small
	action_size := clamp(safe.height * .12, minimum, max_action)
	joystick_size := min(safe.height * .28, max(minimum * 1.35, safe.height * .20))
	if joystick_size < minimum do return layout, .Too_Small

	resource_gap := max(f32(3), 3 * density)
	resource_height := min(
		safe.height * .19,
		max(f32(1), rail_height - joystick_size - rail_gap),
	)
	resource_width := resource_height * MOBILE_STATUS_BAR_ASPECT
	resource_cluster_width := resource_width * f32(len(layout.resource_bars)) +
		resource_gap * f32(len(layout.resource_bars) - 1)
	left_control_width := max(joystick_size, resource_cluster_width)
	left_control_inset := max(outer, safe.height * .10)
	left_width := left_control_inset - outer + left_control_width
	layout.left_rail = {safe.x + outer, safe.y + outer, left_width, rail_height}
	layout.right_rail = {
		mobile_rect_right(safe) - outer - action_size,
		safe.y + outer,
		action_size,
		rail_height,
	}
	gameplay_left := mobile_rect_right(layout.left_rail) + rail_gap
	gameplay_right := layout.right_rail.x - rail_gap
	layout.gameplay_rect = {
		gameplay_left,
		safe.y + outer,
		gameplay_right - gameplay_left,
		rail_height,
	}
	if layout.gameplay_rect.width < minimum * 2 || layout.gameplay_rect.height < minimum do return layout, .Too_Small
	layout.world_focus = {
		layout.gameplay_rect.x + layout.gameplay_rect.width * .5,
		layout.gameplay_rect.y + layout.gameplay_rect.height * CAMERA_FOCUS_Y,
	}
	minimap_margin := max(f32(8), 6 * density)
	minimap_height := min(
		layout.gameplay_rect.height * MOBILE_MINIMAP_HEIGHT_FRACTION,
		layout.gameplay_rect.width * MOBILE_MINIMAP_WIDTH_FRACTION / MOBILE_MINIMAP_ASPECT,
	)
	minimap_width := minimap_height * MOBILE_MINIMAP_ASPECT
	layout.minimap = {
		mobile_rect_right(layout.gameplay_rect) - minimap_margin - minimap_width,
		layout.gameplay_rect.y + minimap_margin,
		minimap_width,
		minimap_height,
	}

	stack_height := action_size * 6 + action_gap * 5
	action_y := layout.right_rail.y + (layout.right_rail.height - stack_height) * .5
	for i in 0 ..< len(layout.action_slots) {
		layout.action_slots[i] = {
			layout.right_rail.x,
			action_y + f32(i) * (action_size + action_gap),
			action_size,
			action_size,
		}
	}

	left_control_x := safe.x + left_control_inset
	joystick_bottom_inset := max(outer, safe.height * .09)
	layout.joystick = {
		left_control_x + (left_control_width - joystick_size) * .5,
		mobile_rect_bottom(safe) - joystick_bottom_inset - joystick_size,
		joystick_size,
		joystick_size,
	}
	resource_x := left_control_x + (left_control_width - resource_cluster_width) * .5
	resource_y := safe.y + max(outer, safe.height * .08)
	for i in 0 ..< len(layout.resource_bars) {
		layout.resource_bars[i] = {
			resource_x + f32(i) * (resource_width + resource_gap),
			resource_y,
			resource_width,
			resource_height,
		}
	}

	utility_gap := max(4 * density, safe.height * .008)
	utility_size := clamp(action_size * .75, minimum, action_size)
	utility_total := utility_size * 4 + utility_gap * 3
	primary_rail_gap := max(rail_gap * 2, action_size * .22)
	utility_required_width := utility_total + max(f32(0), primary_rail_gap - rail_gap)
	if utility_required_width > layout.gameplay_rect.width do return layout, .Too_Small
	lowest_action := layout.action_slots[len(layout.action_slots) - 1]
	utility_y := mobile_rect_center(lowest_action).y - utility_size * .5
	layout.interact = {
		layout.right_rail.x - primary_rail_gap - utility_size,
		utility_y,
		utility_size,
		utility_size,
	}
	layout.pause = {
		layout.interact.x - utility_gap - utility_size,
		utility_y,
		utility_size,
		utility_size,
	}
	layout.character = {
		layout.pause.x - utility_gap - utility_size,
		utility_y,
		utility_size,
		utility_size,
	}
	layout.inventory = {
		layout.character.x - utility_gap - utility_size,
		utility_y,
		utility_size,
		utility_size,
	}

	return layout, .Valid
}

mobile_world_aim_allowed :: proc(layout: ^Mobile_Layout, point: Vec2) -> bool {
	if layout == nil do return false
	// World art is edge-to-edge, but world input is intentionally limited to the
	// safe, unobstructed gameplay region. Rail misses cannot hijack facing.
	return mobile_rect_contains(layout.gameplay_rect, point)
}

mobile_point_in_joystick :: proc(layout: ^Mobile_Layout, point: Vec2) -> bool {
	if layout == nil do return false
	center := mobile_rect_center(layout.joystick)
	radius := min(layout.joystick.width, layout.joystick.height) * .55
	return math.hypot(point.x - center.x, point.y - center.y) <= radius
}

mobile_joystick_screen_vector :: proc(layout: ^Mobile_Layout, point: Vec2) -> Vec2 {
	if layout == nil do return {}
	center := mobile_rect_center(layout.joystick)
	radius := max(f32(1), min(layout.joystick.width, layout.joystick.height) * .5)
	dx := (point.x - center.x) / radius
	dy := (point.y - center.y) / radius
	magnitude := math.hypot(dx, dy)
	if magnitude <= MOBILE_JOYSTICK_DEADZONE do return {}
	clamped := min(f32(1), magnitude)
	strength := (clamped - MOBILE_JOYSTICK_DEADZONE) / (1 - MOBILE_JOYSTICK_DEADZONE)
	return {dx / magnitude * strength, dy / magnitude * strength}
}

mobile_joystick_to_tile_vector :: proc(screen: Vec2) -> Vec2 {
	return screen_stick_to_tile_vector(screen)
}

// --- Plain camera transform -------------------------------------------------

Mobile_Camera_Transform :: struct {
	target_world: Vec2,
	offset_px:    Vec2,
	zoom:         f32,
}

mobile_screen_to_world :: proc(transform: Mobile_Camera_Transform, screen: Vec2) -> Vec2 {
	zoom := transform.zoom
	if zoom <= 0 || math.is_nan(zoom) || math.is_inf(zoom) do zoom = 1
	return transform.target_world + (screen - transform.offset_px) / zoom
}

mobile_screen_to_tile :: proc(transform: Mobile_Camera_Transform, screen: Vec2) -> Vec2 {
	return tile_from_world(mobile_screen_to_world(transform, screen))
}

mobile_world_touch_aim :: proc(
	transform: Mobile_Camera_Transform,
	player_tile: Vec2,
	screen: Vec2,
) -> Vec2 {
	return mobile_screen_to_tile(transform, screen) - player_tile
}

// --- Semantic direct targets -----------------------------------------------

Mobile_Input_Layer :: enum {
	Base,
	Gameplay,
	Inventory,
	Character,
	Shop,
	Story,
	Minigame,
	Archetype,
	Confirmation,
}

Mobile_Input_Context_Key :: struct {
	mode:       App_Mode,
	layer:      Mobile_Input_Layer,
	generation: u64,
}

Mobile_Control :: enum {
	None,
	Ability_1,
	Ability_2,
	Ability_3,
	Ability_4,
	Ability_5,
	Ability_6,
	Interact,
	Inventory,
	Character,
	Pause,
	Utility_Toggle,
}

Mobile_Target_Kind :: enum {
	None,
	Control,
	Menu_Activate,
	Menu_Select,
	Archetype_Preview,
	Archetype_Confirm,
	Story_Panel,
	Story_Choice,
	Minigame_Cell,
	Character_Tab,
	Shop_Mode,
	Inventory_Sort,
	Chronicle_Filter,
	Guard_Request_Drop,
	Guard_Request_Transaction,
	Guard_Confirm,
	Guard_Cancel,
}

Mobile_Direct_Target :: struct {
	id:      int,
	kind:    Mobile_Target_Kind,
	rect:    Mobile_Rect,
	index:   int,
	enabled: bool,
	control: Mobile_Control,
}

Mobile_Target_Set :: struct {
	input_context:   Mobile_Input_Context_Key,
	layout_revision: u64,
	targets:         [MOBILE_MAX_DIRECT_TARGETS]Mobile_Direct_Target,
	count:           int,
}

Mobile_Guard_Request :: enum u8 {
	None,
	Inventory_Drop,
	Shop_Transaction,
	Confirm,
	Cancel,
}

Mobile_Guard_Kind :: enum u8 {
	None,
	Inventory_Drop,
	Shop_Buy,
	Shop_Sell,
}

Mobile_Guard_State :: struct {
	kind:          Mobile_Guard_Kind,
	selected_index:int,
	input_context: Mobile_Input_Context_Key,
}

Mobile_Target_Activation :: struct {
	intent:    Intent,
	activated: bool,
}

mobile_target_set_init :: proc(
	set: ^Mobile_Target_Set,
	input_context: Mobile_Input_Context_Key,
	layout_revision: u64,
) {
	if set == nil do return
	set^ = {}
	set.input_context = input_context
	set.layout_revision = layout_revision
}

mobile_target_set_add :: proc(set: ^Mobile_Target_Set, target: Mobile_Direct_Target) -> bool {
	if set == nil || set.count < 0 || set.count >= len(set.targets) do return false
	set.targets[set.count] = target
	set.count += 1
	return true
}

mobile_target_by_id :: proc(set: ^Mobile_Target_Set, id: int) -> (Mobile_Direct_Target, bool) {
	if set == nil do return {}, false
	for i in 0 ..< set.count {
		if set.targets[i].id == id do return set.targets[i], true
	}
	return {}, false
}

mobile_target_at :: proc(
	set: ^Mobile_Target_Set,
	input_context: Mobile_Input_Context_Key,
	layout_revision: u64,
	point: Vec2,
) -> (Mobile_Direct_Target, bool) {
	if set == nil || set.input_context != input_context || set.layout_revision != layout_revision do return {}, false
	// Minimum-size expansion can overlap dense menu rows. Select the containing
	// target whose center is nearest to the contact, including disabled targets as
	// inert blockers; reverse traversal preserves visual stacking only for an
	// exact-distance tie.
	best: Mobile_Direct_Target
	best_distance_squared := f32(0)
	found := false
	i := set.count - 1
	for i >= 0 {
		target := set.targets[i]
		if mobile_rect_contains(target.rect, point) {
			center := mobile_rect_center(target.rect)
			dx := point.x - center.x
			dy := point.y - center.y
			distance_squared := dx * dx + dy * dy
			if !found || distance_squared < best_distance_squared {
				best = target
				best_distance_squared = distance_squared
				found = true
			}
		}
		i -= 1
	}
	if found && !best.enabled do return {}, false
	return best, found
}

mobile_control_command :: proc(control: Mobile_Control) -> Input_Command {
	switch control {
	case .Ability_1: return .Ability_1
	case .Ability_2: return .Ability_2
	case .Ability_3: return .Ability_3
	case .Ability_4: return .Ability_4
	case .Ability_5: return .Ability_5
	case .Ability_6: return .Ability_6
	case .Interact:  return .Interact
	case .Inventory: return .Inventory
	case .Character: return .Character
	case .Pause:          return .Back
	case .Utility_Toggle: return .None
	case .None:           return .None
	}
	return .None
}

mobile_apply_control :: proc(intent: ^Intent, control: Mobile_Control, gameplay: bool) {
	if intent == nil do return
	if control == .Utility_Toggle {
		intent.toggle_mobile_utility = true
		return
	}
	intent_apply_command(intent, mobile_control_command(control), gameplay)
}

mobile_android_back_intent :: proc(gameplay: bool, utility_open := false) -> Intent {
	if gameplay && utility_open do return {toggle_mobile_utility = true}
	intent: Intent
	intent_apply_command(&intent, .Back, gameplay)
	return intent
}

mobile_activate_target :: proc(target: Mobile_Direct_Target, gameplay: bool) -> Mobile_Target_Activation {
	if !target.enabled do return {}
	activation := Mobile_Target_Activation{activated = true}
	switch target.kind {
	case .Control:
		mobile_apply_control(&activation.intent, target.control, gameplay)
	case .Menu_Activate:
		activation.intent.menu_index = target.index
		activation.intent.menu_index_valid = true
		activation.intent.confirm = true
	case .Menu_Select, .Archetype_Preview:
		activation.intent.menu_index = target.index
		activation.intent.menu_index_valid = true
	case .Archetype_Confirm:
		activation.intent.confirm = true
	case .Story_Panel:
		activation.intent.confirm = true
		activation.intent.pointer_confirm = true
	case .Story_Choice, .Minigame_Cell:
		activation.intent.menu_index = target.index
		activation.intent.menu_index_valid = true
		activation.intent.confirm = true
		activation.intent.pointer_confirm = true
	case .Character_Tab:
		activation.intent.character_tab = Character_Tab(target.index)
		activation.intent.character_tab_valid = true
	case .Shop_Mode:
		activation.intent.tab = true
	case .Inventory_Sort:
		activation.intent.inv_sort_mode = Inventory_Sort_Mode(target.index)
		activation.intent.inv_sort_valid = true
	case .Chronicle_Filter:
		activation.intent.chronicle_focus = Chronicle_Focus(target.index)
		activation.intent.chronicle_focus_valid = true
	case .Guard_Request_Drop:
		activation.intent.mobile_guard_request = .Inventory_Drop
	case .Guard_Request_Transaction:
		activation.intent.mobile_guard_request = .Shop_Transaction
	case .Guard_Confirm:
		activation.intent.mobile_guard_request = .Confirm
	case .Guard_Cancel:
		activation.intent.mobile_guard_request = .Cancel
	case .None:
		activation.activated = false
	}
	return activation
}

mobile_gameplay_target_set :: proc(
	layout: ^Mobile_Layout,
	input_context: Mobile_Input_Context_Key,
	interaction_available := false,
	utility_open := false,
) -> Mobile_Target_Set {
	set: Mobile_Target_Set
	if layout == nil do return set
	mobile_target_set_init(&set, input_context, layout.revision)
	controls := [6]Mobile_Control{
		.Ability_1, .Ability_2, .Ability_3,
		.Ability_4, .Ability_5, .Ability_6,
	}
	for control, i in controls {
		_ = mobile_target_set_add(&set, {
			id = 100 + i,
			kind = .Control,
			rect = layout.action_slots[i],
			enabled = true,
			control = control,
		})
	}
	primary_control := interaction_available ? Mobile_Control.Interact : Mobile_Control.Utility_Toggle
	_ = mobile_target_set_add(&set, {
		id = 200,
		kind = .Control,
		rect = layout.interact,
		enabled = true,
		control = primary_control,
	})
	if utility_open && !interaction_available {
		utilities := [3]struct {id: int, rect: Mobile_Rect, control: Mobile_Control}{
			{201, layout.inventory, .Inventory},
			{202, layout.character, .Character},
			{203, layout.pause, .Pause},
		}
		for utility in utilities {
			_ = mobile_target_set_add(&set, {
				id = utility.id,
				kind = .Control,
				rect = utility.rect,
				enabled = true,
				control = utility.control,
			})
		}
	}
	return set
}

// The mist chase needs only movement, dash, and a directly reachable pause.
// Suppressing the other action targets avoids advertising frozen-world combat,
// inventory, character, or interaction controls inside the virtual room.
mobile_soul_hunt_target_set :: proc(
	layout: ^Mobile_Layout,
	input_context: Mobile_Input_Context_Key,
	utility_open := false,
) -> Mobile_Target_Set {
	set: Mobile_Target_Set
	if layout == nil do return set
	mobile_target_set_init(&set,input_context,layout.revision)
	_ = mobile_target_set_add(&set,{
		id=103,kind=.Control,rect=layout.action_slots[3],enabled=true,control=.Ability_4,
	})
	_ = mobile_target_set_add(&set,{
		id=200,kind=.Control,rect=layout.interact,enabled=true,control=.Utility_Toggle,
	})
	if utility_open {
		_ = mobile_target_set_add(&set,{
			id=203,kind=.Control,rect=layout.pause,enabled=true,control=.Pause,
		})
	}
	return set
}

// Merge another semantic source after the destination. Continuous controller
// movement/aim therefore retains today's priority, while edge actions combine.
mobile_intent_merge :: proc(destination: ^Intent, source: Intent) {
	if destination == nil do return
	if destination.move == {} do destination.move = source.move
	if destination.aim == {} do destination.aim = source.aim
	destination.aim_live = destination.aim_live || source.aim_live
	if source.mouse_walk do destination.mouse_walk = true
	if source.mouse_press {
		destination.mouse_press = true
		destination.mouse_press_aim = source.mouse_press_aim
	}
	if source.mouse_released do destination.mouse_released = true
	if source.mouse_target != {} do destination.mouse_target = source.mouse_target
	for i in 0 ..< len(destination.actions) do destination.actions[i] = destination.actions[i] || source.actions[i]
	destination.action1_released = destination.action1_released || source.action1_released
	destination.interact = destination.interact || source.interact
	destination.use_heal = destination.use_heal || source.use_heal
	destination.use_mana = destination.use_mana || source.use_mana
	destination.toggle_inventory = destination.toggle_inventory || source.toggle_inventory
	destination.toggle_mobile_utility = destination.toggle_mobile_utility || source.toggle_mobile_utility
	destination.toggle_minimap = destination.toggle_minimap || source.toggle_minimap
	destination.minimap_zoom += source.minimap_zoom
	destination.menu_delta += source.menu_delta
	destination.menu_horizontal += source.menu_horizontal
	if source.menu_index_valid {
		destination.menu_index = source.menu_index
		destination.menu_index_valid = true
	}
	destination.inv_drop = destination.inv_drop || source.inv_drop
	destination.inv_sort = destination.inv_sort || source.inv_sort
	destination.inv_cycle_sort += source.inv_cycle_sort
	if source.inv_sort_valid {
		destination.inv_sort_mode = source.inv_sort_mode
		destination.inv_sort_valid = true
	}
	destination.open_character = destination.open_character || source.open_character
	destination.open_disciplines = destination.open_disciplines || source.open_disciplines
	if source.character_tab_valid {
		destination.character_tab = source.character_tab
		destination.character_tab_valid = true
	}
	destination.tab = destination.tab || source.tab
	destination.toggle_fullscreen = destination.toggle_fullscreen || source.toggle_fullscreen
	destination.confirm = destination.confirm || source.confirm
	destination.pointer_confirm = destination.pointer_confirm || source.pointer_confirm
	destination.back = destination.back || source.back
	destination.quit = destination.quit || source.quit
	if source.remap_button_valid {
		destination.remap_button = source.remap_button
		destination.remap_button_valid = true
	}
	if source.remap_trigger_valid {
		destination.remap_trigger = source.remap_trigger
		destination.remap_trigger_valid = true
	}
	destination.descend = destination.descend || source.descend
	destination.new_run = destination.new_run || source.new_run
	destination.boss_floor = destination.boss_floor || source.boss_floor
	if source.chronicle_focus_valid {
		destination.chronicle_focus = source.chronicle_focus
		destination.chronicle_focus_valid = true
	}
	if source.mobile_guard_request != .None do destination.mobile_guard_request = source.mobile_guard_request
}

mobile_center_button_rect :: proc(layout: ^Mobile_Layout, width_targets := f32(3)) -> Mobile_Rect {
	if layout == nil do return {}
	height := layout.minimum_target_px
	width := min(layout.gameplay_rect.width, max(height * width_targets, layout.gameplay_rect.width * .24))
	return {
		layout.gameplay_rect.x + (layout.gameplay_rect.width - width) * .5,
		mobile_rect_bottom(layout.safe_rect) - height - max(f32(8), height * .18),
		width,
		height,
	}
}

mobile_guard_button_rects :: proc(layout: ^Mobile_Layout) -> (confirm, cancel: Mobile_Rect) {
	if layout == nil do return
	height := layout.minimum_target_px
	gap := max(f32(8), height * .18)
	width := min(layout.gameplay_rect.width * .32, height * 3)
	total := width * 2 + gap
	x := layout.gameplay_rect.x + (layout.gameplay_rect.width - total) * .5
	y := layout.gameplay_rect.y + (layout.gameplay_rect.height - height) * .5 + height
	return {x, y, width, height}, {x + width + gap, y, width, height}
}

Mobile_Input_Modality :: enum {
	Keyboard_Mouse,
	Controller,
	Touch,
}

Mobile_Focus_Surface :: enum {
	Ordinary,
	Archetype,
}

mobile_navigation_focus_visible :: proc(
	modality: Mobile_Input_Modality,
	surface: Mobile_Focus_Surface,
) -> bool {
	return modality != .Touch || surface == .Archetype
}

// --- Stable-ID touch reduction ---------------------------------------------

Mobile_Touch_Id :: i64

Mobile_Touch_Point :: struct {
	id:       Mobile_Touch_Id,
	position: Vec2,
}

Mobile_Touch_Snapshot :: struct {
	points: [MOBILE_MAX_TOUCH_CONTACTS]Mobile_Touch_Point,
	count:  int,
}

Mobile_Touch_Event_Kind :: enum {
	Down,
	Move,
	Up,
	Cancel,
}

Mobile_Touch_Event :: struct {
	kind:     Mobile_Touch_Event_Kind,
	id:       Mobile_Touch_Id,
	position: Vec2,
}

Mobile_Touch_Role_Kind :: enum {
	Consumed_Until_Up,
	Joystick,
	World_Aim,
	World_Secondary,
	Pinch,
	Control,
	Menu_Target,
}

Mobile_Touch_Role :: struct {
	kind:      Mobile_Touch_Role_Kind,
	control:   Mobile_Control,
	target_id: int,
}

Mobile_Touch_Contact :: struct {
	id:              Mobile_Touch_Id,
	role:            Mobile_Touch_Role,
	start:           Vec2,
	position:        Vec2,
	input_context:   Mobile_Input_Context_Key,
	layout_revision: u64,
	captured_target: Mobile_Direct_Target,
	release_sent:    bool,
}

Mobile_View_Zoom_Output :: struct {
	valid:  bool,
	value:  f32,
	commit: bool,
}

Mobile_Input_Result :: struct {
	intent:    Intent,
	view_zoom: Mobile_View_Zoom_Output,
}

Mobile_Input_Environment :: struct {
	input_context:   Mobile_Input_Context_Key,
	layout:          ^Mobile_Layout,
	targets:         ^Mobile_Target_Set,
	camera:          Mobile_Camera_Transform,
	player_tile:     Vec2,
	current_view_zoom: f32,
	view_zoom_min:     f32,
	view_zoom_max:     f32,
	pinch_minimum_px:  f32,
	pinch_deadzone:    f32,
	tap_slop_px:       f32,
	gameplay:          bool,
}

Mobile_Touch_State :: struct {
	contacts:       [MOBILE_MAX_TOUCH_CONTACTS]Mobile_Touch_Contact,
	contact_count:  int,
	binding_valid:  bool,
	input_context:  Mobile_Input_Context_Key,
	layout_revision:u64,

	joystick_owned: bool,
	joystick_owner: Mobile_Touch_Id,
	joystick_vector:Vec2,
	aim_owned:      bool,
	aim_owner:      Mobile_Touch_Id,
	aim_point:      Vec2,

	pinch_active:     bool,
	pinch_first:      Mobile_Touch_Id,
	pinch_second:     Mobile_Touch_Id,
	pinch_start_span: f32,
	pinch_start_zoom: f32,
	pinch_current_zoom:f32,
	pinch_changed:    bool,
}

mobile_result_merge :: proc(destination: ^Mobile_Input_Result, source: Mobile_Input_Result) {
	if destination == nil do return
	mobile_intent_merge(&destination.intent, source.intent)
	if source.view_zoom.valid {
		destination.view_zoom.valid = true
		destination.view_zoom.value = source.view_zoom.value
	}
	destination.view_zoom.commit = destination.view_zoom.commit || source.view_zoom.commit
}

mobile_touch_contact_index :: proc(state: ^Mobile_Touch_State, id: Mobile_Touch_Id) -> int {
	if state == nil do return -1
	for i in 0 ..< state.contact_count {
		if state.contacts[i].id == id do return i
	}
	return -1
}

mobile_touch_role_for_id :: proc(state: ^Mobile_Touch_State, id: Mobile_Touch_Id) -> (Mobile_Touch_Role, bool) {
	index := mobile_touch_contact_index(state, id)
	if index < 0 do return {}, false
	return state.contacts[index].role, true
}

mobile_touch_remove_contact :: proc(state: ^Mobile_Touch_State, index: int) {
	if state == nil || index < 0 || index >= state.contact_count do return
	for i in index ..< state.contact_count - 1 do state.contacts[i] = state.contacts[i + 1]
	state.contact_count -= 1
	state.contacts[state.contact_count] = {}
}

mobile_snapshot_point_for_id :: proc(snapshot: Mobile_Touch_Snapshot, id: Mobile_Touch_Id) -> (Mobile_Touch_Point, bool) {
	count := clamp(snapshot.count, 0, len(snapshot.points))
	for i in 0 ..< count {
		if snapshot.points[i].id == id do return snapshot.points[i], true
	}
	return {}, false
}

mobile_touch_has_role :: proc(state: ^Mobile_Touch_State, kind: Mobile_Touch_Role_Kind) -> bool {
	if state == nil do return false
	for i in 0 ..< state.contact_count do if state.contacts[i].role.kind == kind do return true
	return false
}

mobile_environment_layout_revision :: proc(environment: ^Mobile_Input_Environment) -> u64 {
	if environment == nil || environment.layout == nil do return 0
	return environment.layout.revision
}

mobile_environment_tap_slop :: proc(environment: ^Mobile_Input_Environment) -> f32 {
	if environment == nil do return 10
	if environment.tap_slop_px > 0 do return environment.tap_slop_px
	if environment.layout != nil do return max(f32(10), environment.layout.minimum_target_px * .18)
	return 10
}

mobile_environment_pinch_minimum :: proc(environment: ^Mobile_Input_Environment) -> f32 {
	if environment == nil do return MOBILE_PINCH_MINIMUM_PIXELS
	if environment.pinch_minimum_px > 0 do return environment.pinch_minimum_px
	if environment.layout != nil do return max(MOBILE_PINCH_MINIMUM_PIXELS, environment.layout.minimum_target_px * .5)
	return MOBILE_PINCH_MINIMUM_PIXELS
}

mobile_environment_pinch_deadzone :: proc(environment: ^Mobile_Input_Environment) -> f32 {
	if environment != nil && environment.pinch_deadzone > 0 do return environment.pinch_deadzone
	return MOBILE_PINCH_DEADZONE_RATIO
}

mobile_environment_zoom_bounds :: proc(environment: ^Mobile_Input_Environment) -> (f32, f32) {
	minimum := f32(.05)
	maximum := f32(10)
	if environment != nil {
		if environment.view_zoom_min > 0 do minimum = environment.view_zoom_min
		if environment.view_zoom_max >= minimum do maximum = environment.view_zoom_max
	}
	return minimum, maximum
}

mobile_touch_try_begin_pinch :: proc(
	state: ^Mobile_Touch_State,
	environment: ^Mobile_Input_Environment,
) -> bool {
	if state == nil || state.pinch_active do return state != nil && state.pinch_active
	primary := -1
	secondary := -1
	for i in 0 ..< state.contact_count {
		if state.contacts[i].role.kind == .World_Aim do primary = i
		if state.contacts[i].role.kind == .World_Secondary do secondary = i
	}
	if primary < 0 || secondary < 0 do return false
	first := state.contacts[primary]
	second := state.contacts[secondary]
	span := math.hypot(second.position.x - first.position.x, second.position.y - first.position.y)
	if span < mobile_environment_pinch_minimum(environment) do return false

	state.contacts[primary].role.kind = .Pinch
	state.contacts[secondary].role.kind = .Pinch
	state.pinch_active = true
	state.pinch_first = first.id
	state.pinch_second = second.id
	state.pinch_start_span = span
	zoom := environment != nil ? environment.current_view_zoom : f32(1)
	if zoom <= 0 || math.is_nan(zoom) || math.is_inf(zoom) do zoom = 1
	state.pinch_start_zoom = zoom
	state.pinch_current_zoom = zoom
	state.pinch_changed = false
	state.aim_owned = false
	state.aim_owner = 0
	state.aim_point = {}
	return true
}

mobile_touch_update_pinch :: proc(
	state: ^Mobile_Touch_State,
	environment: ^Mobile_Input_Environment,
) -> Mobile_View_Zoom_Output {
	if state == nil || !state.pinch_active || state.pinch_start_span <= 0 do return {}
	first_index := mobile_touch_contact_index(state, state.pinch_first)
	second_index := mobile_touch_contact_index(state, state.pinch_second)
	if first_index < 0 || second_index < 0 do return {}
	first := state.contacts[first_index].position
	second := state.contacts[second_index].position
	span := math.hypot(second.x - first.x, second.y - first.y)
	ratio := span / state.pinch_start_span
	zoom := state.pinch_start_zoom
	if abs(ratio - 1) > mobile_environment_pinch_deadzone(environment) do zoom *= ratio
	minimum, maximum := mobile_environment_zoom_bounds(environment)
	zoom = clamp(zoom, minimum, maximum)
	if abs(zoom - state.pinch_current_zoom) <= 1e-6 do return {}
	state.pinch_current_zoom = zoom
	if abs(zoom - state.pinch_start_zoom) > 1e-6 do state.pinch_changed = true
	return {valid = true, value = zoom}
}

mobile_touch_end_pinch :: proc(state: ^Mobile_Touch_State) -> Mobile_View_Zoom_Output {
	if state == nil || !state.pinch_active do return {}
	output: Mobile_View_Zoom_Output
	if state.pinch_changed {
		output = {valid = true, value = state.pinch_current_zoom, commit = true}
	}
	for i in 0 ..< state.contact_count {
		if state.contacts[i].role.kind == .Pinch do state.contacts[i].role = {kind = .Consumed_Until_Up}
	}
	state.pinch_active = false
	state.pinch_first = 0
	state.pinch_second = 0
	state.pinch_start_span = 0
	state.pinch_start_zoom = 0
	state.pinch_current_zoom = 0
	state.pinch_changed = false
	state.aim_owned = false
	state.aim_owner = 0
	state.aim_point = {}
	return output
}

mobile_touch_assign_down :: proc(
	state: ^Mobile_Touch_State,
	event: Mobile_Touch_Event,
	environment: ^Mobile_Input_Environment,
	result: ^Mobile_Input_Result,
) {
	if state == nil || result == nil || state.contact_count >= len(state.contacts) do return
	index := state.contact_count
	state.contact_count += 1
	contact := &state.contacts[index]
	contact^ = {
		id = event.id,
		start = event.position,
		position = event.position,
		input_context = environment != nil ? environment.input_context : Mobile_Input_Context_Key{},
		layout_revision = mobile_environment_layout_revision(environment),
		role = {kind = .Consumed_Until_Up},
	}

	if environment != nil && environment.targets != nil {
		if target, found := mobile_target_at(
			environment.targets,
			environment.input_context,
			mobile_environment_layout_revision(environment),
			event.position,
		); found {
			contact.captured_target = target
			if target.kind == .Control {
				contact.role = {kind = .Control, control = target.control, target_id = target.id}
				activation := mobile_activate_target(target, environment.gameplay)
				if activation.activated do mobile_intent_merge(&result.intent, activation.intent)
			} else {
				contact.role = {kind = .Menu_Target, target_id = target.id}
			}
			return
		}
	}

	if environment == nil || environment.layout == nil || !environment.gameplay do return
	if !state.joystick_owned && mobile_point_in_joystick(environment.layout, event.position) {
		contact.role = {kind = .Joystick}
		state.joystick_owned = true
		state.joystick_owner = event.id
		state.joystick_vector = mobile_joystick_screen_vector(environment.layout, event.position)
		return
	}
	if !mobile_world_aim_allowed(environment.layout, event.position) do return
	if state.pinch_active {
		contact.role = {kind = .Consumed_Until_Up}
		return
	}
	if !state.aim_owned {
		contact.role = {kind = .World_Aim}
		state.aim_owned = true
		state.aim_owner = event.id
		state.aim_point = event.position
		return
	}
	if !mobile_touch_has_role(state, .World_Secondary) {
		contact.role = {kind = .World_Secondary}
		_ = mobile_touch_try_begin_pinch(state, environment)
		return
	}
}

mobile_touch_activate_captured_target :: proc(
	contact: Mobile_Touch_Contact,
	environment: ^Mobile_Input_Environment,
	position: Vec2,
) -> Mobile_Target_Activation {
	if environment == nil || environment.targets == nil do return {}
	if contact.input_context != environment.input_context || contact.layout_revision != mobile_environment_layout_revision(environment) do return {}
	movement := math.hypot(position.x - contact.start.x, position.y - contact.start.y)
	if movement > mobile_environment_tap_slop(environment) do return {}
	current, found := mobile_target_by_id(environment.targets, contact.captured_target.id)
	if !found || !current.enabled || current.kind != contact.captured_target.kind || current.index != contact.captured_target.index do return {}
	return mobile_activate_target(contact.captured_target, environment.gameplay)
}

mobile_touch_reduce_event :: proc(
	state: ^Mobile_Touch_State,
	event: Mobile_Touch_Event,
	environment: ^Mobile_Input_Environment,
	result: ^Mobile_Input_Result,
) {
	if state == nil || result == nil do return
	index := mobile_touch_contact_index(state, event.id)
	switch event.kind {
	case .Down:
		// A reused ID is a stale contact whose release was swallowed. Quarantine
		// the old ownership before accepting this physical down as a new contact.
		if index >= 0 {
			old := state.contacts[index]
			if old.role.kind == .Control && old.role.control == .Ability_1 && !old.release_sent {
				result.intent.action1_released = true
			}
			if old.role.kind == .Pinch {
				zoom := mobile_touch_end_pinch(state)
				if zoom.valid do result.view_zoom = zoom
			}
			if old.role.kind == .Joystick && state.joystick_owned && state.joystick_owner == old.id {
				state.joystick_owned = false
				state.joystick_vector = {}
			}
			if old.role.kind == .World_Aim && state.aim_owned && state.aim_owner == old.id {
				state.aim_owned = false
				state.aim_point = {}
			}
			mobile_touch_remove_contact(state, index)
		}
		mobile_touch_assign_down(state, event, environment, result)
	case .Move:
		if index < 0 do return
		state.contacts[index].position = event.position
		role := state.contacts[index].role.kind
		if role == .Joystick && state.joystick_owned && state.joystick_owner == event.id {
			state.joystick_vector = mobile_joystick_screen_vector(environment.layout, event.position)
		} else if role == .World_Aim && state.aim_owned && state.aim_owner == event.id {
			state.aim_point = event.position
			if mobile_touch_try_begin_pinch(state, environment) {
				zoom := mobile_touch_update_pinch(state, environment)
				if zoom.valid do result.view_zoom = zoom
			}
		} else if role == .World_Secondary {
			if mobile_touch_try_begin_pinch(state, environment) {
				zoom := mobile_touch_update_pinch(state, environment)
				if zoom.valid do result.view_zoom = zoom
			}
		} else if role == .Pinch {
			zoom := mobile_touch_update_pinch(state, environment)
			if zoom.valid do result.view_zoom = zoom
		}
	case .Up:
		if index < 0 do return
		state.contacts[index].position = event.position
		contact := state.contacts[index]
		switch contact.role.kind {
		case .Control:
			if contact.role.control == .Ability_1 && !contact.release_sent do result.intent.action1_released = true
		case .Joystick:
			if state.joystick_owned && state.joystick_owner == event.id {
				state.joystick_owned = false
				state.joystick_owner = 0
				state.joystick_vector = {}
			}
		case .World_Aim:
			if state.aim_owned && state.aim_owner == event.id {
				state.aim_owned = false
				state.aim_owner = 0
				state.aim_point = {}
			}
		case .Pinch:
			zoom := mobile_touch_update_pinch(state, environment)
			if zoom.valid do result.view_zoom = zoom
			ended := mobile_touch_end_pinch(state)
			if ended.valid {
				result.view_zoom = ended
			}
		case .Menu_Target:
			activation := mobile_touch_activate_captured_target(contact, environment, event.position)
			if activation.activated do mobile_intent_merge(&result.intent, activation.intent)
		case .Consumed_Until_Up, .World_Secondary:
		}
		mobile_touch_remove_contact(state, index)
	case .Cancel:
		if index < 0 do return
		contact := state.contacts[index]
		if contact.role.kind == .Control && contact.role.control == .Ability_1 && !contact.release_sent {
			result.intent.action1_released = true
		}
		if contact.role.kind == .Pinch {
			ended := mobile_touch_end_pinch(state)
			if ended.valid do result.view_zoom = ended
		}
		if contact.role.kind == .Joystick && state.joystick_owned && state.joystick_owner == event.id {
			state.joystick_owned = false
			state.joystick_owner = 0
			state.joystick_vector = {}
		}
		if contact.role.kind == .World_Aim && state.aim_owned && state.aim_owner == event.id {
			state.aim_owned = false
			state.aim_owner = 0
			state.aim_point = {}
		}
		mobile_touch_remove_contact(state, index)
	}
}

mobile_touch_cancel_all :: proc(state: ^Mobile_Touch_State) -> Mobile_Input_Result {
	result: Mobile_Input_Result
	if state == nil do return result
	ended := mobile_touch_end_pinch(state)
	if ended.valid do result.view_zoom = ended
	for i in 0 ..< state.contact_count {
		contact := &state.contacts[i]
		if contact.role.kind == .Control && contact.role.control == .Ability_1 && !contact.release_sent {
			result.intent.action1_released = true
			contact.release_sent = true
		}
		contact.role = {kind = .Consumed_Until_Up}
	}
	state.joystick_owned = false
	state.joystick_owner = 0
	state.joystick_vector = {}
	state.aim_owned = false
	state.aim_owner = 0
	state.aim_point = {}
	return result
}

mobile_touch_finish_frame :: proc(
	state: ^Mobile_Touch_State,
	environment: ^Mobile_Input_Environment,
	result: ^Mobile_Input_Result,
) {
	if state == nil || environment == nil || result == nil || !environment.gameplay do return
	if state.joystick_owned {
		result.intent.move = mobile_joystick_to_tile_vector(state.joystick_vector)
	}
	if state.aim_owned && !state.pinch_active {
		result.intent.aim = mobile_world_touch_aim(environment.camera, environment.player_tile, state.aim_point)
		// A finger on the aim surface is an actively pointed device: it may own
		// idle facing, unlike a desktop cursor merely parked somewhere.
		result.intent.aim_live = true
	}
	if state.pinch_active {
		zoom := mobile_touch_update_pinch(state, environment)
		if zoom.valid do result.view_zoom = zoom
	}
}

mobile_touch_process_snapshot :: proc(
	state: ^Mobile_Touch_State,
	snapshot: Mobile_Touch_Snapshot,
	environment: ^Mobile_Input_Environment,
) -> Mobile_Input_Result {
	result: Mobile_Input_Result
	if state == nil || environment == nil do return result
	layout_revision := mobile_environment_layout_revision(environment)
	if !state.binding_valid {
		state.binding_valid = true
		state.input_context = environment.input_context
		state.layout_revision = layout_revision
	} else if state.input_context != environment.input_context || state.layout_revision != layout_revision {
		cancelled := mobile_touch_cancel_all(state)
		mobile_result_merge(&result, cancelled)
		state.input_context = environment.input_context
		state.layout_revision = layout_revision
	}

	// Missing stable IDs are releases. Process them before new downs so one frame
	// may safely release one role and assign another without index-order coupling.
	i := 0
	for i < state.contact_count {
		contact := state.contacts[i]
		if _, found := mobile_snapshot_point_for_id(snapshot, contact.id); !found {
			event_result: Mobile_Input_Result
			mobile_touch_reduce_event(state, {.Up, contact.id, contact.position}, environment, &event_result)
			mobile_result_merge(&result, event_result)
			continue
		}
		i += 1
	}

	count := clamp(snapshot.count, 0, len(snapshot.points))
	for point_index in 0 ..< count {
		point := snapshot.points[point_index]
		kind := Mobile_Touch_Event_Kind.Down
		if mobile_touch_contact_index(state, point.id) >= 0 do kind = .Move
		event_result: Mobile_Input_Result
		mobile_touch_reduce_event(state, {kind, point.id, point.position}, environment, &event_result)
		mobile_result_merge(&result, event_result)
	}
	mobile_touch_finish_frame(state, environment, &result)
	return result
}

// --- Lifecycle reduction and fixed-step reset -------------------------------

Mobile_Lifecycle_Event :: enum {
	Focus_Lost,
	Focus_Gained,
	Pause,
	Resume,
	Stop,
	Surface_Lost,
	Surface_Restored,
	Low_Memory,
	Destroy,
}

Mobile_Lifecycle_Effect :: enum {
	Cancel_Touches,
	Clear_Play_Input,
	Freeze_Simulation,
	Pause_Audio,
	Request_Checkpoint,
	Flush_Checkpoint_Bounded,
	Reset_Accumulator,
	Refresh_Insets,
	Invalidate_Graphics,
	Recreate_Graphics,
	Drop_Reconstructible_Caches,
	Show_Resume_Veil,
}

Mobile_Lifecycle_State :: struct {
	focused:                bool,
	resumed:                bool,
	surface_ready:          bool,
	destroyed:              bool,
	suspended:              bool,
	resources_lost:         bool,
	suspend_effects_emitted:bool,
	resume_veil_due:        bool,
	resume_return:          App_Mode,
	generation:             u64,
}

Mobile_Lifecycle_Result :: struct {
	effects:       bit_set[Mobile_Lifecycle_Effect],
	resume_return: App_Mode,
}

mobile_lifecycle_init :: proc(current_mode: App_Mode) -> Mobile_Lifecycle_State {
	return {
		focused = true,
		resumed = true,
		surface_ready = true,
		resume_return = current_mode,
	}
}

mobile_lifecycle_interactive :: proc(state: ^Mobile_Lifecycle_State) -> bool {
	return state != nil && state.focused && state.resumed && state.surface_ready && !state.destroyed
}

mobile_lifecycle_reduce :: proc(
	state: ^Mobile_Lifecycle_State,
	event: Mobile_Lifecycle_Event,
	live_descent: bool,
	current_mode: App_Mode,
) -> Mobile_Lifecycle_Result {
	result := Mobile_Lifecycle_Result{resume_return = current_mode}
	if state == nil do return result
	before := mobile_lifecycle_interactive(state)
	resources_were_lost := state.resources_lost

	switch event {
	case .Focus_Lost:      state.focused = false
	case .Focus_Gained:    state.focused = true
	case .Pause, .Stop:    state.resumed = false
	case .Resume:          state.resumed = true
	case .Surface_Lost:
		state.surface_ready = false
		state.resources_lost = true
		if !resources_were_lost do result.effects += {.Invalidate_Graphics}
	case .Surface_Restored: state.surface_ready = true
	case .Low_Memory:
		result.effects += {.Drop_Reconstructible_Caches}
		state.generation += 1
		return result
	case .Destroy:
		if state.surface_ready && !state.resources_lost {
			result.effects += {.Invalidate_Graphics}
		}
		state.resources_lost = true
		state.destroyed = true
		state.focused = false
		state.resumed = false
		state.surface_ready = false
	}

	after := mobile_lifecycle_interactive(state)
	if before && !after && !state.suspend_effects_emitted {
		state.suspend_effects_emitted = true
		state.suspended = true
		state.resume_return = current_mode
		state.resume_veil_due = live_descent
		state.generation += 1
		result.effects += {
			.Cancel_Touches,
			.Clear_Play_Input,
			.Freeze_Simulation,
			.Pause_Audio,
			.Reset_Accumulator,
		}
		if live_descent {
			result.effects += {.Request_Checkpoint, .Flush_Checkpoint_Bounded}
		}
	}

	if !before && after {
		state.suspended = false
		state.suspend_effects_emitted = false
		state.generation += 1
		// The audio backend is independent of the EGL surface. Keep its device
		// alive and resume playback only after the app-owned resume gate clears.
		result.effects += {.Reset_Accumulator, .Refresh_Insets}
		if state.resources_lost {
			result.effects += {.Recreate_Graphics}
			state.resources_lost = false
		}
		if state.resume_veil_due {
			result.effects += {.Show_Resume_Veil}
			result.resume_return = state.resume_return
			state.resume_veil_due = false
		}
	}
	return result
}

Mobile_Fixed_Step_State :: struct {
	accumulator:     f32,
	discard_next_dt: bool,
}

mobile_fixed_step_reset :: proc(state: ^Mobile_Fixed_Step_State, discard_next_dt := false) {
	if state == nil do return
	state.accumulator = 0
	state.discard_next_dt = discard_next_dt
}

mobile_fixed_step_advance :: proc(
	state: ^Mobile_Fixed_Step_State,
	frame_dt, step_dt, max_frame_dt: f32,
	enabled: bool,
) -> int {
	if state == nil || step_dt <= 0 || math.is_nan(step_dt) || math.is_inf(step_dt) do return 0
	if !enabled {
		state.accumulator = 0
		return 0
	}
	if state.discard_next_dt {
		state.discard_next_dt = false
		state.accumulator = 0
		return 0
	}
	dt := frame_dt
	if dt < 0 || math.is_nan(dt) || math.is_inf(dt) do dt = 0
	if max_frame_dt > 0 do dt = min(dt, max_frame_dt)
	state.accumulator += dt
	steps := 0
	for state.accumulator >= step_dt {
		state.accumulator -= step_dt
		steps += 1
	}
	return steps
}
