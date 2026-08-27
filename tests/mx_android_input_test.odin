package archrogue_tests

// MX-android — stable-ID touch reduction and semantic input policy. Raw Android
// pointer APIs are intentionally absent: snapshots contain only stable IDs and
// physical positions, and the reducer emits the shared raylib-free Intent.

import "core:math"
import "core:testing"
import ar "../src"

@(private = "file")
mx_android_snapshot :: proc(points: []ar.Mobile_Touch_Point) -> (snapshot: ar.Mobile_Touch_Snapshot) {
	snapshot.count = min(len(points), len(snapshot.points))
	for point, i in points {
		if i >= snapshot.count do break
		snapshot.points[i] = point
	}
	return
}

@(private = "file")
mx_android_gameplay_fixture :: proc(
	layout: ^ar.Mobile_Layout,
	targets: ^ar.Mobile_Target_Set,
) -> ar.Mobile_Input_Environment {
	built, _ := ar.mobile_layout_build({
		surface_width = 1920,
		surface_height = 1080,
		density = 2,
		revision = 41,
	})
	layout^ = built
	input_context := ar.Mobile_Input_Context_Key{
		mode = .Playing,
		layer = .Gameplay,
		generation = 1,
	}
	targets^ = ar.mobile_gameplay_target_set(layout, input_context)
	player_tile := ar.Vec2{12, 11}
	return {
		input_context = input_context,
		layout = layout,
		targets = targets,
		camera = {
			target_world = ar.world_from_tile(player_tile),
			offset_px = layout.world_focus,
			zoom = 1,
		},
		player_tile = player_tile,
		current_view_zoom = 1,
		view_zoom_min = .5,
		view_zoom_max = 2.5,
		pinch_minimum_px = 32,
		pinch_deadzone = .01,
		tap_slop_px = 16,
		gameplay = true,
	}
}

@(test)
mx_android_gameplay_target_vocabulary_maps_to_shared_commands :: proc(t: ^testing.T) {
	layout: ar.Mobile_Layout
	targets: ar.Mobile_Target_Set
	environment := mx_android_gameplay_fixture(&layout, &targets)
	testing.expect(t, targets.count == 7, "closed gameplay HUD must expose six actions plus the primary A button")
	primary, primary_found := ar.mobile_target_by_id(&targets, 200)
	testing.expect(t, primary_found && primary.control == .Utility_Toggle,
		"A must toggle the utility drawer when no contextual interaction is available")

	expanded := ar.mobile_gameplay_target_set(&layout, environment.input_context, false, true)
	testing.expect(t, expanded.count == 10, "expanded A drawer must add Bag, Character, and Menu")
	bag, bag_found := ar.mobile_target_by_id(&expanded, 201)
	character, character_found := ar.mobile_target_by_id(&expanded, 202)
	menu, menu_found := ar.mobile_target_by_id(&expanded, 203)
	testing.expect(t, bag_found && bag.control == .Inventory)
	testing.expect(t, character_found && character.control == .Character)
	testing.expect(t, menu_found && menu.control == .Pause)

	contextual := ar.mobile_gameplay_target_set(&layout, environment.input_context, true, true)
	primary, primary_found = ar.mobile_target_by_id(&contextual, 200)
	testing.expect(t, contextual.count == 7 && primary_found && primary.control == .Interact,
		"a contextual interaction must replace the drawer toggle and suppress expanded utilities")

	hunt_closed:=ar.mobile_soul_hunt_target_set(&layout,environment.input_context)
	hunt_dash,dash_found:=ar.mobile_target_by_id(&hunt_closed,103)
	hunt_primary,hunt_primary_found:=ar.mobile_target_by_id(&hunt_closed,200)
	testing.expect(t,hunt_closed.count==2&&dash_found&&hunt_dash.control==.Ability_4&&
		hunt_primary_found&&hunt_primary.control==.Utility_Toggle,
		"closed hunt HUD must expose only dash and its utility toggle")
	hunt_open:=ar.mobile_soul_hunt_target_set(&layout,environment.input_context,true)
	hunt_menu,hunt_menu_found:=ar.mobile_target_by_id(&hunt_open,203)
	testing.expect(t,hunt_open.count==3&&hunt_menu_found&&hunt_menu.control==.Pause,
		"expanded hunt HUD must expose a direct touch pause without frozen-world controls")

	controls := [11]ar.Mobile_Control{
		.Ability_1,
		.Ability_2,
		.Ability_3,
		.Ability_4,
		.Ability_5,
		.Ability_6,
		.Interact,
		.Inventory,
		.Character,
		.Pause,
		.Utility_Toggle,
	}
	for control, i in controls {
		activation := ar.mobile_activate_target({
			id = i + 1,
			kind = .Control,
			enabled = true,
			control = control,
		}, true)
		testing.expectf(t, activation.activated, "control %v did not activate", control)
		switch control {
		case .Ability_1: testing.expect(t, activation.intent.actions[0])
		case .Ability_2: testing.expect(t, activation.intent.actions[1])
		case .Ability_3: testing.expect(t, activation.intent.actions[2])
		case .Ability_4: testing.expect(t, activation.intent.actions[3])
		case .Ability_5: testing.expect(t, activation.intent.use_heal)
		case .Ability_6: testing.expect(t, activation.intent.use_mana)
		case .Interact:  testing.expect(t, activation.intent.interact)
		case .Inventory: testing.expect(t, activation.intent.toggle_inventory)
		case .Character: testing.expect(t, activation.intent.open_character)
		case .Pause:          testing.expect(t, activation.intent.back)
		case .Utility_Toggle: testing.expect(t, activation.intent.toggle_mobile_utility)
		case .None:           testing.expect(t, false, "None was not part of the fixture")
		}
	}

	back := ar.mobile_android_back_intent(true)
	testing.expect(t, back.back, "Android Back must use Input_Command.Back semantics")
	drawer_back := ar.mobile_android_back_intent(true,true)
	testing.expect(t,drawer_back.toggle_mobile_utility&&!drawer_back.back,
		"Android Back must dismiss an expanded utility drawer before pausing")
	testing.expect(t, ar.mobile_control_command(.Pause) == ar.Input_Command.Back, "Menu control must retain the shared pause command")
}

@(test)
mx_android_primary_a_drawer_is_transient_and_contextual :: proc(t: ^testing.T) {
	app: ar.App
	ar.app_init(&app, 7141)
	defer ar.run_destroy(&app.run)
	ar.run_start(&app.run, app.seed, .Warden)
	app.mode = .Playing

	found_clear_tile := false
	for x in 1 ..< ar.MAP_W-1 {
		if found_clear_tile do break
		for y in 1 ..< ar.MAP_H-1 {
			if app.run.dungeon.tiles[x][y] != .Floor do continue
			app.run.player.pos = {f32(x)+.5, f32(y)+.5}
			app.run.player.prev_pos = app.run.player.pos
			if !ar.player_interaction_available(&app.run) {
				found_clear_tile = true
				break
			}
		}
	}
	testing.expect(t, found_clear_tile, "fixture must find ordinary floor away from contextual interactions")
	if !found_clear_tile do return

	_ = ar.app_apply(&app, ar.Intent{toggle_mobile_utility = true})
	testing.expect(t, app.mobile_utility_open, "first idle A tap must expand the utility drawer")
	_ = ar.app_apply(&app, ar.Intent{toggle_mobile_utility = true})
	testing.expect(t, !app.mobile_utility_open, "second idle A tap must collapse the utility drawer")

	_ = ar.app_apply(&app, ar.Intent{toggle_mobile_utility = true})
	_ = ar.app_apply(&app, ar.Intent{toggle_inventory = true})
	testing.expect(t, app.inventory_open && !app.mobile_utility_open,
		"opening Bag must close the transient drawer")
	_ = ar.app_apply(&app, ar.Intent{toggle_inventory = true})

	found_door := false
	for x in 1 ..< ar.MAP_W-1 {
		if found_door do break
		for y in 1 ..< ar.MAP_H-1 {
			if app.run.dungeon.tiles[x][y] != .Closed_Door do continue
			app.run.boss_engaged = false
			app.run.player.pos = {f32(x)+.5, f32(y)+.5}
			app.run.player.prev_pos = app.run.player.pos
			found_door = ar.player_interaction_available(&app.run)
			if found_door do break
		}
	}
	testing.expect(t, found_door, "fixture must expose an actionable door prompt")
	if found_door {
		app.mobile_utility_open = true
		_ = ar.app_apply(&app, {})
		testing.expect(t, !app.mobile_utility_open,
			"entering interaction range must dismiss a previously expanded utility drawer")
	}
}

@(test)
mx_android_soul_hunt_drawer_keeps_touch_pause_reachable :: proc(t:^testing.T) {
	app:ar.App
	ar.app_init(&app,7142)
	defer ar.run_destroy(&app.run)
	ar.run_start(&app.run,app.seed,.Warden)
	app.mode=.Playing
	app.story_minigame={active=true,kind=.Mirror_The_Unlost,phase=.Play}
	_=ar.app_apply(&app,ar.Intent{toggle_mobile_utility=true})
	testing.expect(t,app.mobile_utility_open,"hunt A control must open its pause drawer")
	_=ar.app_apply(&app,ar.Intent{back=true})
	testing.expect(t,app.mode==.Paused&&ar.app_story_soul_hunt_active(&app),
		"hunt Menu control must pause without abandoning the encounter")
}

@(test)
mx_android_stable_ids_support_move_aim_held_big_hit_and_other_action :: proc(t: ^testing.T) {
	layout: ar.Mobile_Layout
	targets: ar.Mobile_Target_Set
	environment := mx_android_gameplay_fixture(&layout, &targets)
	state: ar.Mobile_Touch_State

	joystick_point := ar.mobile_rect_center(layout.joystick) + ar.Vec2{layout.joystick.width * .4, 0}
	aim_point := layout.world_focus + ar.Vec2{120, 20}
	ability1_point := ar.mobile_rect_center(layout.action_slots[0])
	ability2_point := ar.mobile_rect_center(layout.action_slots[1])
	all := mx_android_snapshot([]ar.Mobile_Touch_Point{
		{id = 10, position = joystick_point},
		{id = 20, position = aim_point},
		{id = 30, position = ability1_point},
		{id = 40, position = ability2_point},
	})

	result := ar.mobile_touch_process_snapshot(&state, all, &environment)
	testing.expect(t, result.intent.move != ar.Vec2{}, "joystick must emit movement while other contacts are down")
	testing.expect(t, result.intent.aim != ar.Vec2{}, "world contact must emit aim while moving")
	testing.expect(t, result.intent.actions[0] && result.intent.actions[1], "Big Hit and another action must press together")
	joy_role, joy_found := ar.mobile_touch_role_for_id(&state, 10)
	aim_role, aim_found := ar.mobile_touch_role_for_id(&state, 20)
	big_role, big_found := ar.mobile_touch_role_for_id(&state, 30)
	testing.expect(t, joy_found && joy_role.kind == .Joystick)
	testing.expect(t, aim_found && aim_role.kind == .World_Aim)
	testing.expect(t, big_found && big_role.kind == .Control && big_role.control == .Ability_1)

	// Reorder every contact and move both continuous controls. Stable IDs, not
	// snapshot indices, retain ownership; discrete actions do not repeat.
	joystick_moved := joystick_point + ar.Vec2{0, -layout.joystick.height * .25}
	aim_moved := aim_point + ar.Vec2{50, -30}
	reordered := mx_android_snapshot([]ar.Mobile_Touch_Point{
		{id = 40, position = ability2_point},
		{id = 20, position = aim_moved},
		{id = 10, position = joystick_moved},
		{id = 30, position = ability1_point},
	})
	result = ar.mobile_touch_process_snapshot(&state, reordered, &environment)
	testing.expect(t, result.intent.move != ar.Vec2{} && result.intent.aim != ar.Vec2{}, "continuous roles must survive snapshot reorder")
	testing.expect(t, result.intent.actions == [4]bool{}, "held controls must not retrigger press edges")
	joy_role, _ = ar.mobile_touch_role_for_id(&state, 10)
	aim_role, _ = ar.mobile_touch_role_for_id(&state, 20)
	testing.expect(t, joy_role.kind == .Joystick && aim_role.kind == .World_Aim, "stable IDs changed roles after reorder")

	without_other := mx_android_snapshot([]ar.Mobile_Touch_Point{
		{id = 10, position = joystick_moved},
		{id = 20, position = aim_moved},
		{id = 30, position = ability1_point},
	})
	result = ar.mobile_touch_process_snapshot(&state, without_other, &environment)
	testing.expect(t, !result.intent.action1_released, "releasing another action must not release Big Hit")

	continuous_only := mx_android_snapshot([]ar.Mobile_Touch_Point{
		{id = 10, position = joystick_moved},
		{id = 20, position = aim_moved},
	})
	result = ar.mobile_touch_process_snapshot(&state, continuous_only, &environment)
	testing.expect(t, result.intent.action1_released, "Big Hit owner must emit one release edge")
	result = ar.mobile_touch_process_snapshot(&state, continuous_only, &environment)
	testing.expect(t, !result.intent.action1_released, "Big Hit release must never repeat")
}

@(test)
mx_android_sliding_never_retargets_buttons_or_world :: proc(t: ^testing.T) {
	layout: ar.Mobile_Layout
	targets: ar.Mobile_Target_Set
	environment := mx_android_gameplay_fixture(&layout, &targets)
	state: ar.Mobile_Touch_State

	ability2 := ar.mobile_rect_center(layout.action_slots[1])
	ability3 := ar.mobile_rect_center(layout.action_slots[2])
	down := mx_android_snapshot([]ar.Mobile_Touch_Point{{id = 51, position = ability2}})
	result := ar.mobile_touch_process_snapshot(&state, down, &environment)
	testing.expect(t, result.intent.actions[1] && !result.intent.actions[2], "touch-down must capture Ability 2")

	slid := mx_android_snapshot([]ar.Mobile_Touch_Point{{id = 51, position = ability3}})
	result = ar.mobile_touch_process_snapshot(&state, slid, &environment)
	testing.expect(t, result.intent.actions == [4]bool{}, "sliding over Ability 3 must not fire it")
	role, found := ar.mobile_touch_role_for_id(&state, 51)
	testing.expect(t, found && role.kind == .Control && role.control == .Ability_2, "slide must retain the down-assigned role")

	result = ar.mobile_touch_process_snapshot(&state, {}, &environment)
	testing.expect(t, result.intent.actions == [4]bool{}, "button release must not become a different action")
	testing.expect(t, state.contact_count == 0)

	// World art is edge-to-edge, but rail touches never acquire world aim.
	testing.expect(t, ar.mobile_rect_contains(layout.world_viewport, ar.mobile_rect_center(layout.right_rail)))
	testing.expect(t, !ar.mobile_world_aim_allowed(&layout, ar.mobile_rect_center(layout.right_rail)))
	testing.expect(t, ar.mobile_world_aim_allowed(&layout, layout.world_focus))
}

@(test)
mx_android_context_change_quarantines_held_contacts_until_up :: proc(t: ^testing.T) {
	layout: ar.Mobile_Layout
	targets: ar.Mobile_Target_Set
	environment := mx_android_gameplay_fixture(&layout, &targets)
	state: ar.Mobile_Touch_State
	joystick_point := ar.mobile_rect_center(layout.joystick) + ar.Vec2{layout.joystick.width * .4, 0}
	ability1_point := ar.mobile_rect_center(layout.action_slots[0])
	held := mx_android_snapshot([]ar.Mobile_Touch_Point{
		{id = 61, position = joystick_point},
		{id = 62, position = ability1_point},
	})

	pressed := ar.mobile_touch_process_snapshot(&state, held, &environment)
	testing.expect(t, pressed.intent.actions[0] && pressed.intent.move != ar.Vec2{})

	// A modal/pause generation change cancels ownership, emits the charge release,
	// and consumes the still-physical contacts instead of reacquiring them.
	environment.input_context.generation += 1
	targets = ar.mobile_gameplay_target_set(&layout, environment.input_context)
	cancelled := ar.mobile_touch_process_snapshot(&state, held, &environment)
	testing.expect(t, cancelled.intent.action1_released, "context cancellation must release Ability 1 exactly once")
	testing.expect(t, cancelled.intent.move == ar.Vec2{} && cancelled.intent.actions == [4]bool{}, "cancelled contacts must be quarantined")
	joystick_role, joystick_found := ar.mobile_touch_role_for_id(&state, 61)
	ability_role, ability_found := ar.mobile_touch_role_for_id(&state, 62)
	testing.expect(t, joystick_found && joystick_role.kind == .Consumed_Until_Up, "joystick escaped cancellation quarantine")
	testing.expect(t, ability_found && ability_role.kind == .Consumed_Until_Up, "ability escaped cancellation quarantine")

	cancelled = ar.mobile_touch_process_snapshot(&state, held, &environment)
	testing.expect(t, !cancelled.intent.action1_released && cancelled.intent.move == ar.Vec2{}, "quarantine must be quiet on later frames")
	_ = ar.mobile_touch_process_snapshot(&state, {}, &environment)
	testing.expect(t, state.contact_count == 0, "physical up must end quarantine")

	reacquired := ar.mobile_touch_process_snapshot(&state, held, &environment)
	testing.expect(t, reacquired.intent.actions[0] && reacquired.intent.move != ar.Vec2{}, "a genuinely new down may acquire roles again")
}

@(test)
mx_android_pinch_suppresses_aim_consumes_survivor_and_commits_once :: proc(t: ^testing.T) {
	layout: ar.Mobile_Layout
	targets: ar.Mobile_Target_Set
	environment := mx_android_gameplay_fixture(&layout, &targets)
	state: ar.Mobile_Touch_State
	first := layout.world_focus + ar.Vec2{-100, 30}
	second := layout.world_focus + ar.Vec2{100, 30}
	pinch := mx_android_snapshot([]ar.Mobile_Touch_Point{
		{id = 70, position = first},
		{id = 71, position = second},
	})

	result := ar.mobile_touch_process_snapshot(&state, pinch, &environment)
	testing.expect(t, state.pinch_active, "two world contacts beyond the threshold must begin pinch")
	testing.expect(t, result.intent.aim == ar.Vec2{}, "pinch must suppress world aim immediately")

	second_moved := layout.world_focus + ar.Vec2{200, 30}
	pinch_moved := mx_android_snapshot([]ar.Mobile_Touch_Point{
		{id = 70, position = first},
		{id = 71, position = second_moved},
	})
	result = ar.mobile_touch_process_snapshot(&state, pinch_moved, &environment)
	testing.expect(t, result.view_zoom.valid && !result.view_zoom.commit, "live pinch must preview without persisting")
	testing.expectf(t, math.abs(result.view_zoom.value - 1.5) < 1e-4, "pinch zoom was %.4f, want 1.5", result.view_zoom.value)
	testing.expect(t, result.intent.aim == ar.Vec2{})

	survivor := mx_android_snapshot([]ar.Mobile_Touch_Point{{id = 71, position = second_moved}})
	result = ar.mobile_touch_process_snapshot(&state, survivor, &environment)
	testing.expect(t, result.view_zoom.valid && result.view_zoom.commit, "first pinch up must commit the final zoom")
	testing.expect(t, math.abs(result.view_zoom.value - 1.5) < 1e-4)
	role, found := ar.mobile_touch_role_for_id(&state, 71)
	testing.expect(t, found && role.kind == .Consumed_Until_Up, "pinch survivor must not become aim")
	testing.expect(t, result.intent.aim == ar.Vec2{})

	result = ar.mobile_touch_process_snapshot(&state, survivor, &environment)
	testing.expect(t, !result.view_zoom.commit && !result.view_zoom.valid, "pinch zoom must commit exactly once")
	testing.expect(t, result.intent.aim == ar.Vec2{}, "survivor must remain consumed")
	_ = ar.mobile_touch_process_snapshot(&state, {}, &environment)

	fresh := mx_android_snapshot([]ar.Mobile_Touch_Point{{id = 72, position = second}})
	result = ar.mobile_touch_process_snapshot(&state, fresh, &environment)
	testing.expect(t, result.intent.aim != ar.Vec2{}, "aim may return only after survivor up and a fresh down")
}

@(test)
mx_android_menu_policy_is_direct_except_preview_and_guarded_rows :: proc(t: ^testing.T) {
	ordinary := ar.mobile_activate_target({
		id = 1,
		kind = .Menu_Activate,
		index = 3,
		enabled = true,
	}, false)
	testing.expect(t, ordinary.activated && ordinary.intent.menu_index_valid && ordinary.intent.menu_index == 3 && ordinary.intent.confirm, "ordinary touch rows must directly activate")

	guarded := ar.mobile_activate_target({
		id = 2,
		kind = .Menu_Select,
		index = 4,
		enabled = true,
	}, false)
	testing.expect(t, guarded.intent.menu_index_valid && guarded.intent.menu_index == 4 && !guarded.intent.confirm, "economic/destructive rows may select pending explicit confirmation")

	preview := ar.mobile_activate_target({
		id = 3,
		kind = .Archetype_Preview,
		index = 2,
		enabled = true,
	}, false)
	confirm := ar.mobile_activate_target({
		id = 4,
		kind = .Archetype_Confirm,
		enabled = true,
	}, false)
	testing.expect(t, preview.intent.menu_index_valid && preview.intent.menu_index == 2 && !preview.intent.confirm, "one archetype tap must preview only")
	testing.expect(t, confirm.intent.confirm && !confirm.intent.menu_index_valid, "explicit archetype control must confirm the preview")

	story := ar.mobile_activate_target({id = 5, kind = .Story_Choice, index = 1, enabled = true}, false)
	minigame := ar.mobile_activate_target({id = 6, kind = .Minigame_Cell, index = 7, enabled = true}, false)
	testing.expect(t, story.intent.menu_index == 1 && story.intent.confirm && story.intent.pointer_confirm, "story choice must directly commit its semantic row")
	testing.expect(t, minigame.intent.menu_index == 7 && minigame.intent.confirm && minigame.intent.pointer_confirm, "story minigame cell must directly activate")

	testing.expect(t, !ar.mobile_navigation_focus_visible(.Touch, .Ordinary), "ordinary touch menus must not retain desktop selection focus")
	testing.expect(t, ar.mobile_navigation_focus_visible(.Touch, .Archetype), "archetype preview is the sole touch focus exception")
	testing.expect(t, ar.mobile_navigation_focus_visible(.Keyboard_Mouse, .Ordinary))
	testing.expect(t, ar.mobile_navigation_focus_visible(.Controller, .Ordinary))

	// Drive the real App reducer: preview remains in Select; the separate confirm
	// starts exactly the previewed archetype.
	app: ar.App
	ar.app_init(&app, 7102)
	defer ar.run_destroy(&app.run)
	app.mode = .Select
	_ = ar.app_apply(&app, preview.intent)
	testing.expect(t, app.mode == .Select && app.select_index == 2, "preview tap must not start the run")
	_ = ar.app_apply(&app, confirm.intent)
	testing.expect(t, app.mode == .Playing && app.run.player.archetype == .Arcanist, "confirm must start the previewed archetype")
}

@(test)
mx_android_overlapping_minimum_targets_choose_nearest_row_center :: proc(t: ^testing.T) {
	input_context := ar.Mobile_Input_Context_Key{mode = .Options, layer = .Base, generation = 1}
	targets: ar.Mobile_Target_Set
	ar.mobile_target_set_init(&targets, input_context, 91)
	_ = ar.mobile_target_set_add(&targets, {
		id = 901, kind = .Menu_Activate, rect = {100, 100, 300, 140}, index = 3, enabled = true,
	})
	_ = ar.mobile_target_set_add(&targets, {
		id = 902, kind = .Menu_Activate, rect = {100, 180, 300, 140}, index = 4, enabled = true,
	})

	upper, upper_found := ar.mobile_target_at(&targets, input_context, 91, {250, 185})
	lower, lower_found := ar.mobile_target_at(&targets, input_context, 91, {250, 235})
	testing.expect(t, upper_found && upper.index == 3, "overlap above the midpoint must select the upper Options row")
	testing.expect(t, lower_found && lower.index == 4, "overlap below the midpoint must select the lower Options row")
}

@(test)
mx_android_disabled_options_row_blocks_neighbor_target_expansion :: proc(t: ^testing.T) {
	input_context := ar.Mobile_Input_Context_Key{mode = .Options, layer = .Base, generation = 1}
	layout := ar.Mobile_Layout{
		safe_rect = {0, 0, 1000, 500},
		minimum_target_px = 132,
		revision = 92,
	}
	targets: ar.Mobile_Target_Set
	ar.mobile_target_set_init(&targets, input_context, layout.revision)
	ar.platform_mobile_add_target(&targets, &layout, 400, .Menu_Activate,
		{100, 100, 300, 60}, index = 0, enabled = false)
	ar.platform_mobile_add_target(&targets, &layout, 401, .Menu_Activate,
		{100, 180, 300, 60}, index = 1)

	fullscreen, fullscreen_found := ar.mobile_target_by_id(&targets, 400)
	testing.expect(t, fullscreen_found && !fullscreen.enabled,
		"disabled fullscreen row must remain in target arbitration as an inert blocker")
	_, blocked_found := ar.mobile_target_at(&targets, input_context, layout.revision, {250, 160})
	frame_rate, frame_rate_found := ar.mobile_target_at(&targets, input_context, layout.revision, {250, 180})
	testing.expect(t, !blocked_found,
		"tap nearest the disabled fullscreen row must not activate its expanded neighbor")
	testing.expect(t, frame_rate_found && frame_rate.index == 1,
		"tap nearest the enabled frame-rate row must still activate it")
}

@(test)
mx_android_menu_touch_activates_on_up_without_slide_retarget :: proc(t: ^testing.T) {
	layout, status := ar.mobile_layout_build({surface_width = 1920, surface_height = 1080, density = 2, revision = 81})
	testing.expect(t, status == .Valid)
	input_context := ar.Mobile_Input_Context_Key{mode = .Title, layer = .Base, generation = 1}
	targets: ar.Mobile_Target_Set
	ar.mobile_target_set_init(&targets, input_context, layout.revision)
	first_rect := ar.Mobile_Rect{layout.gameplay_rect.x + 100, layout.gameplay_rect.y + 100, 160, 80}
	second_rect := ar.Mobile_Rect{first_rect.x, first_rect.y + 120, 160, 80}
	_ = ar.mobile_target_set_add(&targets, {id = 901, kind = .Menu_Activate, rect = first_rect, index = 1, enabled = true})
	_ = ar.mobile_target_set_add(&targets, {id = 902, kind = .Menu_Activate, rect = second_rect, index = 2, enabled = true})
	environment := ar.Mobile_Input_Environment{
		input_context = input_context,
		layout = &layout,
		targets = &targets,
		gameplay = false,
		tap_slop_px = 12,
	}
	state: ar.Mobile_Touch_State

	down := mx_android_snapshot([]ar.Mobile_Touch_Point{{id = 90, position = ar.mobile_rect_center(first_rect)}})
	result := ar.mobile_touch_process_snapshot(&state, down, &environment)
	testing.expect(t, !result.intent.confirm, "menu activation must wait for a completed tap")
	result = ar.mobile_touch_process_snapshot(&state, {}, &environment)
	testing.expect(t, result.intent.confirm && result.intent.menu_index_valid && result.intent.menu_index == 1, "up must activate the captured row")

	down = mx_android_snapshot([]ar.Mobile_Touch_Point{{id = 91, position = ar.mobile_rect_center(first_rect)}})
	_ = ar.mobile_touch_process_snapshot(&state, down, &environment)
	slid := mx_android_snapshot([]ar.Mobile_Touch_Point{{id = 91, position = ar.mobile_rect_center(second_rect)}})
	result = ar.mobile_touch_process_snapshot(&state, slid, &environment)
	testing.expect(t, !result.intent.confirm)
	result = ar.mobile_touch_process_snapshot(&state, {}, &environment)
	testing.expect(t, !result.intent.confirm && !result.intent.menu_index_valid, "slide must activate neither original nor crossed row")
}

@(test)
mx_android_touch_merges_without_disabling_keyboard_or_controller :: proc(t: ^testing.T) {
	combined := ar.Intent{move = {1, 0}, aim = {0, -1}}
	combined.actions[2] = true
	touch := ar.Intent{move = {-1, 1}, aim = {1, 0}, interact = true, toggle_inventory = true}
	touch.actions[0] = true
	ar.mobile_intent_merge(&combined, touch)

	testing.expect(t, combined.move == ar.Vec2{1, 0}, "existing keyboard/controller movement keeps priority")
	testing.expect(t, combined.aim == ar.Vec2{0, -1}, "existing keyboard/controller aim keeps priority")
	testing.expect(t, combined.actions[0] && combined.actions[2], "touch and controller action edges must combine")
	testing.expect(t, combined.interact && combined.toggle_inventory, "touch utility edges must merge independently")
}
