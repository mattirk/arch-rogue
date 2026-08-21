package archrogue_tests

// Headless desktop-control parity tests. Raw raylib polling stays in main.odin;
// Desktop_Input -> Intent and all held-input simulation behavior are pure.

import "core:math"
import "core:testing"
import ar "../src"

@(test)
desktop_world_axis_movement_matches_pygame :: proc(t: ^testing.T) {
	intent := ar.desktop_gameplay_intent(ar.Desktop_Input{right = true}, .Warden)
	testing.expect(t, intent.move == ar.Vec2{1, 0}, "D/right must move world +x")
	intent = ar.desktop_gameplay_intent(ar.Desktop_Input{left = true}, .Warden)
	testing.expect(t, intent.move == ar.Vec2{-1, 0}, "A/left must move world -x")
	intent = ar.desktop_gameplay_intent(ar.Desktop_Input{up = true}, .Warden)
	testing.expect(t, intent.move == ar.Vec2{0, -1}, "W/up must move world -y")
	intent = ar.desktop_gameplay_intent(ar.Desktop_Input{down = true}, .Warden)
	testing.expect(t, intent.move == ar.Vec2{0, 1}, "S/down must move world +y")
	intent = ar.desktop_gameplay_intent(ar.Desktop_Input{right = true, up = true}, .Warden)
	testing.expect(t, intent.move == ar.Vec2{1, -1}, "diagonal input must preserve both world axes")
	intent = ar.desktop_gameplay_intent(ar.Desktop_Input{left = true, right = true}, .Warden)
	testing.expect(t, intent.move == ar.Vec2{}, "opposing directions must cancel")
}

@(test)
desktop_action_slots_and_inert_buttons_match_current_parity :: proc(t: ^testing.T) {
	intent := ar.desktop_gameplay_intent(ar.Desktop_Input{
		abilities = {true, true, true, true, false, false}, ability1_released = true,
	}, .Warden)
	testing.expect(t, intent.actions == [4]bool{true,true,true,true}, "keys 1-4 must map to the complete action kit")
	testing.expect(t, intent.action1_released, "key 1 release must propagate for charge cancellation")

	intent = ar.desktop_gameplay_intent(ar.Desktop_Input{abilities = {false, false, false, false, true, true}}, .Warden)
	testing.expect(t, intent.use_heal && intent.use_mana, "potions must be keys 5 and 6")
	intent = ar.desktop_gameplay_intent(ar.Desktop_Input{mouse_right = true, tab = true}, .Warden)
	testing.expect(t, intent.actions == {} && !intent.toggle_inventory, "RMB and gameplay Tab must be inert")

	target := ar.Vec2{7, 9}
	intent = ar.desktop_gameplay_intent(ar.Desktop_Input{
		aim = {0, -1},
		mouse_target = target,
		interact = true,
		inventory = true,
		back = true,
	}, .Warden)
	testing.expect(t, intent.aim == ar.Vec2{0, -1} && intent.mouse_target == target, "aim and mouse target must propagate")
	testing.expect(t, intent.interact && intent.toggle_inventory && intent.back, "E, I, and Esc must resolve independently")
}

@(test)
keyboard_movement_overrides_held_mouse_walk :: proc(t: ^testing.T) {
	raw := ar.Desktop_Input{
		right = true,
		mouse_left = true,
		mouse_target = {20, 20},
	}
	intent := ar.desktop_gameplay_intent(raw, .Warden)
	testing.expect(t, intent.move == ar.Vec2{1, 0}, "keyboard movement must survive")
	testing.expect(t, !intent.mouse_walk, "held mouse must yield to keyboard")

	raw.right = false
	intent = ar.desktop_gameplay_intent(raw, .Warden)
	testing.expect(t, intent.mouse_walk, "held mouse must walk when keyboard is idle")
}

@(test)
mouse_walk_caps_final_step_at_stop_radius :: proc(t: ^testing.T) {
	app: ar.App
	ar.app_init(&app, ar.derive_seed(41, 0))
	defer ar.run_destroy(&app.run)
	ar.run_start(&app.run, app.seed, .Warden)
	app.mode = .Playing
	clear(&app.run.enemies)

	start := app.run.player.pos
	target := start + ar.Vec2{0.13, 0}
	ar.app_apply(&app, ar.Intent{
		aim = target - start,
		mouse_walk = true,
		mouse_target = target,
	})
	ar.app_tick(&app)
	remaining := math.hypot(
		target.x - app.run.player.pos.x,
		target.y - app.run.player.pos.y,
	)
	testing.expectf(t, abs(remaining - ar.MOUSE_WALK_STOP_RADIUS) < 1e-4, "remaining %.5f, want %.2f", remaining, ar.MOUSE_WALK_STOP_RADIUS)
}

@(test)
idle_mouse_aim_updates_facing_without_attacking :: proc(t: ^testing.T) {
	app: ar.App
	ar.app_init(&app, ar.derive_seed(42, 0))
	defer ar.run_destroy(&app.run)
	ar.run_start(&app.run, app.seed, .Warden)
	app.mode = .Playing
	clear(&app.run.enemies)
	stamina := app.run.player.stamina

	ar.app_apply(&app, ar.Intent{aim = {0, -3}})
	ar.app_tick(&app)
	testing.expect(t, abs(app.run.player.facing.x) < 1e-5 && abs(app.run.player.facing.y + 1) < 1e-5, "idle facing must follow cursor aim")
	testing.expect(t, app.run.player.melee_timer == 0 && app.run.player.stamina == stamina, "idle aim must not swing")
}

@(test)
held_mouse_auto_melees_only_when_target_is_in_arc :: proc(t: ^testing.T) {
	app: ar.App
	ar.app_init(&app, ar.derive_seed(43, 0))
	defer ar.run_destroy(&app.run)
	ar.run_start(&app.run, app.seed, .Warden)
	app.mode = .Playing
	clear(&app.run.enemies)

	start := app.run.player.pos
	target := start + ar.Vec2{1, 0}
	ar.app_apply(&app, ar.Intent{aim = {1, 0}, mouse_walk = true, mouse_target = target})
	ar.app_tick(&app)
	testing.expect(t, app.run.player.melee_timer == 0, "empty click must not start melee cooldown")
	testing.expect(t, app.run.player.stamina == f32(app.run.player.max_stamina), "empty click must not spend stamina")

	app.run.player.pos = start
	app.run.player.prev_pos = start
	enemy := ar.enemy_make(.Ghoul, start + ar.Vec2{0.9, 0}, 1)
	enemy.aggro_range = 0
	append(&app.run.enemies, enemy)
	hp_before := app.run.enemies[0].hp
	ar.app_tick(&app)
	testing.expect(t, app.run.player.melee_timer > 0, "targeted held click must start melee cooldown")
	testing.expect(t, app.run.enemies[0].hp < hp_before, "target in arc must take auto-melee damage")
}

@(test)
short_lmb_click_is_not_lost_between_fixed_ticks :: proc(t: ^testing.T) {
	app: ar.App
	ar.app_init(&app, ar.derive_seed(46, 0))
	defer ar.run_destroy(&app.run)
	ar.run_start(&app.run, app.seed, .Warden)
	app.mode = .Playing
	clear(&app.run.enemies)

	start := app.run.player.pos
	enemy := ar.enemy_make(.Ghoul, start + ar.Vec2{0.9, 0}, 1)
	enemy.aggro_range = 0
	append(&app.run.enemies, enemy)
	hp_before := app.run.enemies[0].hp

	// Press and release both reach the app before its next 60 Hz step.
	ar.app_apply(&app, ar.Intent{
		aim = {1, 0}, mouse_press = true, mouse_press_aim = {1, 0},
		mouse_walk = true, mouse_target = start + ar.Vec2{1, 0},
	})
	ar.app_apply(&app, ar.Intent{aim = {1, 0}, mouse_released = true})
	ar.app_tick(&app)
	testing.expect(t, app.run.enemies[0].hp < hp_before, "latched click must deal melee damage")
	testing.expect(t, !app.mouse_press_pending, "fixed tick must consume the click latch")
}

@(test)
mouse_press_aim_is_independent_of_keyboard_steering :: proc(t: ^testing.T) {
	raw := ar.Desktop_Input{
		right = true,
		aim = {1, 0},
		mouse_left = true,
		mouse_left_pressed = true,
		mouse_press_aim = {-1, 0},
	}
	intent := ar.desktop_gameplay_intent(raw, .Warden)
	testing.expect(t, intent.move == ar.Vec2{1, 0} && !intent.mouse_walk, "keyboard must still own movement")
	testing.expect(t, intent.mouse_press && intent.mouse_press_aim == ar.Vec2{-1, 0}, "click edge must retain cursor aim")
}

@(test)
held_melee_resolves_before_enemy_windup :: proc(t: ^testing.T) {
	app: ar.App
	ar.app_init(&app, ar.derive_seed(47, 0))
	defer ar.run_destroy(&app.run)
	ar.run_start(&app.run, app.seed, .Warden)
	app.mode = .Playing
	clear(&app.run.enemies)

	start := app.run.player.pos
	enemy := ar.enemy_make(.Ghoul, start + ar.Vec2{0.8, 0}, 1)
	enemy.hp = 1
	enemy.ai = .Windup
	enemy.windup = 0
	enemy.pending_ability = -1
	enemy.damage = app.run.player.max_hp + 10
	enemy.attack_range = 2
	append(&app.run.enemies, enemy)
	app.move_input = {1, 0}

	ar.app_tick(&app)
	testing.expect(t, app.run.player.hp > 0, "player swing must cancel a lethal enemy windup first")
	testing.expect(t, len(app.run.enemies) == 0, "killed enemy must sweep in the same tick")
}

@(test)
dead_player_cannot_auto_melee_on_transition_tick :: proc(t: ^testing.T) {
	app: ar.App
	ar.app_init(&app, ar.derive_seed(48, 0))
	defer ar.run_destroy(&app.run)
	ar.run_start(&app.run, app.seed, .Warden)
	app.mode = .Playing
	clear(&app.run.enemies)

	start := app.run.player.pos
	enemy := ar.enemy_make(.Ghoul, start + ar.Vec2{0.8, 0}, 1)
	enemy.aggro_range = 0
	append(&app.run.enemies, enemy)
	hp_before := app.run.enemies[0].hp
	app.run.player.hp = 0
	app.move_input = {1, 0}

	ar.app_tick(&app)
	testing.expect(t, app.run.enemies[0].hp == hp_before, "fallen player must not attack")
	testing.expect(t, app.mode == .Playing && app.death_pending, "zero hp must begin the death presentation")
}

@(test)
mouse_aim_respects_facing_dead_zone :: proc(t: ^testing.T) {
	app: ar.App
	ar.app_init(&app, ar.derive_seed(49, 0))
	defer ar.run_destroy(&app.run)
	ar.run_start(&app.run, app.seed, .Warden)
	app.mode = .Playing
	clear(&app.run.enemies)
	app.run.player.facing = {1, 0}

	ar.app_apply(&app, ar.Intent{aim = {0, 0.01}})
	ar.app_tick(&app)
	testing.expect(t, app.run.player.facing == ar.Vec2{1, 0}, "cursor jitter at the player's feet must not turn them")
	ar.app_apply(&app, ar.Intent{aim = {0, 0.06}})
	ar.app_tick(&app)
	testing.expect(t, abs(app.run.player.facing.x) < 1e-5 && app.run.player.facing.y > 0.99, "aim outside 0.05 tiles must update facing")
}

@(test)
keyboard_steering_updates_facing_during_swing :: proc(t: ^testing.T) {
	run: ar.Run
	defer ar.run_destroy(&run)
	ar.run_start(&run, ar.derive_seed(50, 0), .Warden)
	clear(&run.enemies)
	run.player.facing = {1, 0}
	run.player.swing_timer = 0.4
	ar.sim_tick(&run, {0, -1})
	testing.expect(t, abs(run.player.facing.x) < 1e-5 && run.player.facing.y < -0.99, "movement must steer during an action clip")
}

@(test)
inventory_is_modal_clamped_and_scrolls :: proc(t: ^testing.T) {
	app: ar.App
	ar.app_init(&app, ar.derive_seed(44, 0))
	defer ar.run_destroy(&app.run)
	ar.run_start(&app.run, app.seed, .Warden)
	app.mode = .Playing
	clear(&app.run.enemies)

	for i in 0 ..< ar.BAG_CAPACITY {
		app.run.player.bag[i] = ar.Item{kind = .Weapon, name = "Test Blade", power = i}
	}
	app.run.player.bag_count = ar.BAG_CAPACITY
	app.inventory_open = true
	app.run.player.melee_timer = 1
	before := app.run.player.pos
	app.move_input = {1, 0}
	ar.app_tick(&app)
	testing.expect(t, app.run.player.pos == before, "inventory must pause movement")
	testing.expect(t, app.run.player.melee_timer == 1, "inventory must pause cooldown clocks")

	ar.app_apply(&app, ar.Intent{menu_delta = 99})
	testing.expect(t, app.inv_index == ar.BAG_CAPACITY - 1, "inventory selection must clamp at end")
	testing.expect(t, app.inv_scroll == ar.BAG_CAPACITY - ar.INVENTORY_VISIBLE_ROWS, "selection must scroll into view")
	ar.app_apply(&app, ar.Intent{menu_delta = -99})
	testing.expect(t, app.inv_index == 0 && app.inv_scroll == 0, "inventory selection must clamp at start")
}

@(test)
inventory_does_not_swallow_big_hit_release :: proc(t: ^testing.T) {
	app: ar.App
	ar.app_init(&app, ar.derive_seed(4401, 0))
	defer ar.run_destroy(&app.run)
	ar.run_start(&app.run, app.seed, .Warden)
	app.mode = .Playing
	testing.expect(t, ar.player_big_hit_begin(&app.run,{1,0}), "Big Hit should begin before opening inventory")
	ar.app_apply(&app,ar.Intent{toggle_inventory=true})
	testing.expect(t, app.inventory_open && ar.bighit_charging(&app.run.player), "opening inventory must pause the active charge")
	ar.app_apply(&app,ar.Intent{action1_released=true})
	testing.expect(t, !ar.bighit_charging(&app.run.player), "key-up through inventory must cancel a pre-commit charge")
	testing.expect(t, abs(app.run.player.bighit_timer-ar.BIGHIT_CANCEL_COOLDOWN)<1e-5, "modal cancellation must start the short cooldown")
}

@(test)
minimap_controls_toggle_and_clamp_scale :: proc(t: ^testing.T) {
	app: ar.App
	ar.app_init(&app, ar.derive_seed(45, 0))
	defer ar.run_destroy(&app.run)
	ar.run_start(&app.run, app.seed, .Warden)
	app.mode = .Playing
	testing.expect(t, app.minimap_visible, "minimap starts visible")
	ar.app_apply(&app, ar.Intent{toggle_minimap = true, minimap_zoom = 99})
	testing.expect(t, !app.minimap_visible, "Ctrl+M intent must hide minimap")
	testing.expect(t, app.minimap_zoom == ar.MINIMAP_ZOOM_MAX, "minimap zoom must clamp high")
	ar.app_apply(&app, ar.Intent{minimap_zoom = -99})
	testing.expect(t, app.minimap_zoom == ar.MINIMAP_ZOOM_MIN, "minimap zoom must clamp low")
}

@(test)
contextual_minimap_delta_is_not_merged_twice :: proc(t: ^testing.T) {
	intent := ar.Intent{toggle_minimap = true, minimap_zoom = 1}
	// This is the same merge boundary used after raw desktop movement/action
	// collection. Contextual minimap commands already live in the destination.
	ar.merge_gameplay_intent(&intent, ar.Intent{toggle_minimap = true, minimap_zoom = 1})
	testing.expect(t, intent.toggle_minimap, "contextual toggle must survive the gameplay merge")
	testing.expect(t, intent.minimap_zoom == 1, "one wheel notch must remain one 1.2x minimap step")
}

@(test)
minimap_zoom_resets_but_session_preferences_survive_new_run :: proc(t: ^testing.T) {
	app: ar.App
	ar.app_init(&app, ar.derive_seed(51, 0))
	defer ar.run_destroy(&app.run)
	app.mode = .Select
	ar.app_apply(&app, ar.Intent{confirm = true})
	app.minimap_zoom = ar.MINIMAP_ZOOM_MAX
	app.minimap_visible = false
	app.inv_sort_mode = .Power
	app.mode = .Select
	ar.app_apply(&app, ar.Intent{confirm = true})
	testing.expect(t, app.minimap_zoom == ar.MINIMAP_ZOOM_DEFAULT, "per-run minimap zoom must reset")
	testing.expect(t, !app.minimap_visible && app.inv_sort_mode == .Power, "session map visibility and bag sort preference must survive")
}

@(test)
menu_double_click_requires_same_context_row_and_interval :: proc(t: ^testing.T) {
	state: ar.Desktop_Click_State
	testing.expect(t, !ar.desktop_register_menu_click(&state, .Archetype, 2, 1.0), "first click only selects")
	testing.expect(t, ar.desktop_register_menu_click(&state, .Archetype, 2, 1.44), "same row inside 0.45 s must confirm")
	testing.expect(t, !state.valid, "successful pair must be consumed")

	state = {}
	_ = ar.desktop_register_menu_click(&state, .Archetype, 1, 2.0)
	testing.expect(t, !ar.desktop_register_menu_click(&state, .Archetype, 2, 2.1), "different row must not confirm")
	testing.expect(t, !ar.desktop_register_menu_click(&state, .Inventory, 2, 2.2), "different menu must not confirm")
	testing.expect(t, !ar.desktop_register_menu_click(&state, .Inventory, 2, 2.7), "expired interval must not confirm")
	testing.expect(t, !ar.desktop_register_menu_click(&state, .Inventory, 2, 2.6), "backwards timestamp must not confirm")
}

@(test)
reflowing_archetype_double_click_keeps_first_slot_target :: proc(t: ^testing.T) {
	state: ar.Desktop_Click_State
	index, found, confirm := ar.desktop_resolve_reflow_menu_click(
		&state, .Archetype, 3, true, false, 1.0,
	)
	testing.expect(t, found && index == 3 && !confirm, "first side-slot click must preview its archetype")

	// Recentring puts another actor under the stationary pointer. Hitting the
	// saved first-click region must still complete the original pair.
	index, found, confirm = ar.desktop_resolve_reflow_menu_click(
		&state, .Archetype, 4, true, true, 1.40,
	)
	testing.expect(t, found && index == 3 && confirm, "stationary second click must confirm the recentered archetype")
	testing.expect(t, !state.valid, "successful reflow pair must be consumed")

	state = {}
	_, _, _ = ar.desktop_resolve_reflow_menu_click(&state, .Archetype, 1, true, false, 2.0)
	index, found, confirm = ar.desktop_resolve_reflow_menu_click(
		&state, .Archetype, 2, true, false, 2.1,
	)
	testing.expect(t, found && index == 2 && !confirm, "a deliberate click outside the saved region must preview the new actor")
}

@(test)
archetype_click_pair_is_cleared_across_select_transitions :: proc(t: ^testing.T) {
	view: ar.View
	view.menu_click = {
		click_context = .Archetype,
		index = 2,
		time = 1.0,
		valid = true,
	}
	view.archetype_click_rect_valid = true
	ar.view_clear_menu_click(&view)
	testing.expect(t, !view.menu_click.valid, "leaving Select must discard the pending click pair")
	testing.expect(t, !view.archetype_click_rect_valid, "leaving Select must discard its pre-reflow hit region")
	_, pending := ar.desktop_pending_menu_click(&view.menu_click, .Archetype, 1.1)
	testing.expect(t, !pending, "a reopened Select screen must start a fresh double-click contract")
}

@(test)
inventory_sort_and_drop_follow_overlay_intents :: proc(t: ^testing.T) {
	app: ar.App
	ar.app_init(&app, ar.derive_seed(52, 0))
	defer ar.run_destroy(&app.run)
	ar.run_start(&app.run, app.seed, .Warden)
	app.mode = .Playing
	app.inventory_open = true
	app.run.player.bag[0] = ar.Item{kind = .Armor, name = "Rare Mail", rarity = .Rare, defense = 2}
	app.run.player.bag[1] = ar.Item{kind = .Weapon, name = "Iron Blade", rarity = .Common, power = 8}
	app.run.player.bag[2] = ar.Item{kind = .Weapon, name = "Runed Blade", rarity = .Rare, power = 3}
	app.run.player.bag_count = 3

	ar.app_apply(&app, ar.Intent{inv_sort_mode = .Rarity, inv_sort_valid = true})
	testing.expect(t, app.inv_sort_mode == .Rarity, "mouse sort chip must choose its mode")
	testing.expect(t, app.run.player.bag[0].name == "Runed Blade" && app.run.player.bag[1].name == "Rare Mail", "rarity sort must use category as its tie-break")

	ground_before := len(app.run.ground_items)
	ar.app_apply(&app, ar.Intent{menu_index = 0, menu_index_valid = true, inv_drop = true})
	testing.expect(t, app.run.player.bag_count == 2 && len(app.run.ground_items) == ground_before + 1, "drop shortcut must move one bag item to the floor")
	testing.expect(t, app.run.player.bag[0].name == "Rare Mail", "drop must preserve the remaining bag order")

	ar.app_apply(&app, ar.Intent{inv_cycle_sort = 1})
	testing.expect(t, app.inv_sort_mode == .Power, "Tab must cycle rarity to power")
}

@(test)
archetype_pointer_confirm_suppresses_mouse_until_release :: proc(t: ^testing.T) {
	app: ar.App
	ar.app_init(&app, ar.derive_seed(53, 0))
	defer ar.run_destroy(&app.run)
	app.mode = .Select
	ar.app_apply(&app, ar.Intent{confirm = true, pointer_confirm = true})
	testing.expect(t, app.mode == .Playing && app.mouse_input_blocked, "double-click start must consume its held button")

	target := app.run.player.pos + ar.Vec2{4, 0}
	ar.app_apply(&app, ar.Intent{
		aim = {1, 0}, mouse_walk = true, mouse_press = true,
		mouse_press_aim = {1, 0}, mouse_target = target,
	})
	testing.expect(t, !app.mouse_walk && !app.mouse_press_pending, "held menu click must not leak into gameplay")
	ar.app_apply(&app, ar.Intent{mouse_released = true})
	testing.expect(t, !app.mouse_input_blocked, "release must re-enable gameplay mouse input")
}

@(test)
held_movement_survives_noop_interact_without_forcing_critical_save :: proc(t: ^testing.T) {
	app: ar.App
	ar.app_init(&app, ar.derive_seed(54, 0))
	defer ar.run_destroy(&app.run)
	ar.run_start(&app.run, app.seed, .Warden)
	app.run.run_id = "input-interact-test"
	app.mode = .Playing
	app.story_panel = {}
	app.run.story_runtime.requests = {}
	clear(&app.run.ground_items)
	clear(&app.run.shrines)
	clear(&app.run.secrets)
	app.run.has_shopkeeper = false
	center := ar.room_center(app.run.dungeon.rooms_buf[0])
	app.run.player.pos = {f32(center.x)+.5,f32(center.y)+.5}
	app.run.player.prev_pos = app.run.player.pos
	testing.expect(t, !ar.player_interaction_available(&app.run), "fixture must exercise an ordinary no-op interaction")

	app.run_dirty = false
	app.run_critical = false
	serial := app.run_dirty_serial
	_ = ar.app_apply(&app, ar.Intent{move={1,0},interact=true})
	testing.expect(t, app.move_input == ar.Vec2{1,0}, "Interact must not clear held movement")
	testing.expect(t, app.run_dirty && app.run_dirty_serial == serial+1, "Interact must retain normal autosave tracking")
	testing.expect(t, !app.run_critical, "no-op Interact must not force synchronous web checkpointing")
}

@(test)
browser_standard_gamepad_buttons_drive_trigger_edges_without_trigger_axes :: proc(t: ^testing.T) {
	state: ar.Controller_Trigger_State
	pressed := ar.controller_trigger_sample(false, 0, true)
	testing.expect(t, pressed == 1, "button-backed browser trigger must produce a pressed sample")
	testing.expect(t, ar.controller_resolve_trigger(pressed, &state) == .Pressed, "button-backed trigger must emit its press edge")

	released := ar.controller_trigger_sample(false, 0, false)
	testing.expect(t, released == 0, "released four-axis browser trigger must return to zero")
	testing.expect(t, ar.controller_resolve_trigger(released, &state) == .Released, "button-backed trigger must emit its release edge")

	testing.expect(t, ar.controller_trigger_sample(true, .7, false) == .7, "native analog trigger axis must remain intact")
	testing.expect(t, ar.controller_trigger_sample(false, .7, false) == 0, "unavailable trigger axis must not leak a stale value")
}
