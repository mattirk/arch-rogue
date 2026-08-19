package archrogue_tests

// Headless M9 shell foundations: exact difficulty/options tables and pure
// controller resolution and isolated options persistence. Raw raylib polling
// remains in the platform layer.

import "core:math"
import "core:strings"
import "core:testing"
import ar "../src"

@(private = "file")
m9_near :: proc(a, b: f32, epsilon: f32 = 1e-5) -> bool {
	return abs(a - b) < epsilon
}

@(test)
m9_difficulty_table_matches_pygame :: proc(t: ^testing.T) {
	expected := [ar.Difficulty_Id]ar.Difficulty_Profile{
		.Easy = {
			"Easy",
			"Still dangerous: tougher enemies, real ambush pressure, and fewer safety nets.",
			1.76, 1.64, 1, 1.08, .90, .60, 0, .35, .03, .015, .05, 1.50, 0, 0,
		},
		.Medium = {
			"Medium",
			"Default: severe pressure with doubled monster durability, damage, traps, and room threats.",
			2.36, 2.30, 2, 1.14, .82, 1.40, 1, .70, .05, .03, .10, 2.20, -.08, -.04,
		},
		.Hard = {
			"Hard",
			"Brutal density, crushing hits, relentless attacks, and scarce recovery.",
			2.85, 2.60, 5, 1.18, .74, 2.50, 2, .75, .16, .085, .25, 2.55, -.13, -.065,
		},
		.Hell = {
			"Hell",
			"Unlocked after a clear: overwhelming density, constant elites, lethal traps, and no mercy.",
			3.80, 3.30, 8, 1.30, .60, 4.75, 3, .90, .30, .17, .42, 3.35, -.20, -.12,
		},
	}
	for difficulty in ar.Difficulty_Id {
		testing.expectf(
			t,
			ar.DIFFICULTY_PROFILES[difficulty] == expected[difficulty],
			"%v difficulty profile diverged from Pygame",
			difficulty,
		)
	}
	testing.expect(t, ar.DEFAULT_DIFFICULTY == .Medium, "fresh runs must default to Medium")
}

@(test)
m9_difficulty_lock_normalization_and_cycle :: proc(t: ^testing.T) {
	testing.expect(t, ar.difficulty_cycle(.Easy, false) == .Medium)
	testing.expect(t, ar.difficulty_cycle(.Medium, false) == .Hard)
	testing.expect(t, ar.difficulty_cycle(.Hard, false) == .Easy)
	testing.expect(t, ar.difficulty_cycle(.Hard, true) == .Hell)
	testing.expect(t, ar.difficulty_cycle(.Hell, true) == .Easy)
	testing.expect(t, ar.difficulty_cycle(.Easy, false, -1) == .Hard)
	testing.expect(t, ar.difficulty_cycle(.Easy, true, -1) == .Hell)
	testing.expect(t, ar.difficulty_normalize(.Hell, false) == .Medium, "locked Hell must sanitize to Medium")

	bad_value := 99
	bad := ar.Difficulty_Id(bad_value)
	testing.expect(t, ar.difficulty_normalize(bad, true) == .Medium, "malformed difficulty must sanitize to Medium")
}

@(test)
m9_difficulty_apply_helpers_match_order_and_clamps :: proc(t: ^testing.T) {
	stats := ar.difficulty_apply_enemy_stats(ar.Difficulty_Enemy_Stats{
		hp = 10,
		damage = 10,
		speed = 2,
		attack_cooldown = .40,
		aggro_range = 3,
	}, .Medium)
	testing.expect(t, stats.hp == 23, "enemy HP must truncate after multiplication")
	testing.expect(t, stats.damage == 25, "enemy damage must round, then add the flat bonus")
	testing.expect(t, m9_near(stats.speed, 2.28))
	testing.expect(t, m9_near(stats.attack_cooldown, .35), "enemy cooldown must clamp at .35 seconds")
	testing.expect(t, m9_near(stats.aggro_range, 4.4))

	testing.expect(t, ar.difficulty_enemy_count(2, .Hard, .74) == 5, "count bonus must precede the extra roll")
	testing.expect(t, ar.difficulty_enemy_count(2, .Hard, .75) == 4, "extra chance uses a strict less-than roll")
	testing.expect(t, m9_near(ar.difficulty_elite_chance(.50, .Hard), .55), "elite chance cap changed")
	testing.expect(t, m9_near(ar.difficulty_miniboss_chance(.10, .Hell), .22), "miniboss chance cap changed")
	testing.expect(t, m9_near(ar.difficulty_trap_chance(.35, .Hell), .70), "trap chance cap changed")
	testing.expect(t, ar.difficulty_trap_damage(10, .Easy) == 15)
	testing.expect(t, m9_near(ar.difficulty_loot_chance(.18, .Hell), .12), "loot chance floor changed")
	testing.expect(t, m9_near(ar.difficulty_shrine_chance(.08, .Hard), .04), "shrine chance floor changed")
}

@(test)
m9_option_defaults_normalize_and_cycle :: proc(t: ^testing.T) {
	options := ar.options_default()
	testing.expect(t, options.fullscreen, "fresh desktop install must be fullscreen")
	testing.expect(t, options.frame_rate_cap == .FPS_60 && ar.frame_rate_cap_target(options.frame_rate_cap) == 60)
	testing.expect(t, m9_near(options.view_zoom, 2.0))
	testing.expect(t, options.difficulty == .Medium)
	testing.expect(t, options.controller_enabled && options.audio_enabled && options.lighting_enabled)

	ar.options_cycle_frame_rate_cap(&options)
	testing.expect(t, options.frame_rate_cap == .FPS_90)
	ar.options_cycle_frame_rate_cap(&options, -1)
	testing.expect(t, options.frame_rate_cap == .FPS_60)
	testing.expect(t, ar.frame_rate_cap_cycle(.Unlimited) == .FPS_30)
	testing.expect(t, ar.frame_rate_cap_cycle(.FPS_30, -1) == .Unlimited)
	testing.expect(t, ar.frame_rate_cap_target(.Unlimited) == 0)
	testing.expect(t, ar.frame_rate_cap_label(.Unlimited) == "Unlimited")

	ar.options_cycle_view_zoom(&options)
	testing.expect(t, m9_near(options.view_zoom, 2.24))
	ar.options_cycle_view_zoom(&options, -1)
	testing.expect(t, m9_near(options.view_zoom, 2.0))
	for _ in 0 ..< 32 do ar.options_cycle_view_zoom(&options, -1)
	testing.expect(t, m9_near(options.view_zoom, ar.OPTIONS_VIEW_ZOOM_MIN))
	for _ in 0 ..< 64 do ar.options_cycle_view_zoom(&options)
	testing.expect(t, m9_near(options.view_zoom, ar.OPTIONS_VIEW_ZOOM_MAX))

	options.difficulty = .Hard
	ar.options_cycle_difficulty(&options)
	testing.expect(t, options.difficulty == .Easy, "locked difficulty cycle must omit Hell")
	profile: ar.Profile_State
	ar.profile_init(&profile,"options-test")
	defer ar.profile_destroy(&profile)
	testing.expect(t, ar.profile_unlock_hell(&profile))
	testing.expect(t, !ar.profile_unlock_hell(&profile), "Hell unlock must be idempotent")
	options.difficulty = .Hard
	ar.options_cycle_difficulty(&options,hell_unlocked=profile.hell_unlocked)
	testing.expect(t, options.difficulty == .Hell)

	bad_cap_value := 77
	options.frame_rate_cap = ar.Frame_Rate_Cap(bad_cap_value)
	options.view_zoom = math.nan_f32()
	options.difficulty = .Hell
	ar.options_normalize(&options,false)
	testing.expect(t, options.frame_rate_cap == .FPS_60)
	testing.expect(t, m9_near(options.view_zoom, ar.OPTIONS_VIEW_ZOOM_DEFAULT))
	testing.expect(t, options.difficulty == .Medium)
}

@(test)
m9_controller_default_semantic_layout_matches_pygame :: proc(t: ^testing.T) {
	mapping := ar.controller_default_mapping()
	expected_buttons := [ar.Controller_Button]ar.Input_Command{
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
	testing.expect(t, mapping.gameplay_buttons == expected_buttons)
	testing.expect(t, mapping.triggers == [ar.Controller_Trigger]ar.Input_Command{
		.Left = .Ability_1,
		.Right = .Ability_4,
	})

	testing.expect(t, ar.controller_button_command(&mapping, .A, .Menu) == .Confirm)
	testing.expect(t, ar.controller_button_command(&mapping, .B, .Menu) == .Back)
	testing.expect(t, ar.controller_button_command(&mapping, .X, .Menu) == .Interact)
	testing.expect(t, ar.controller_button_command(&mapping, .Y, .Menu) == .Help)
	testing.expect(t, ar.controller_button_command(&mapping, .Left_Bumper, .Menu) == .Back)
	testing.expect(t, ar.controller_button_command(&mapping, .Right_Bumper, .Menu) == .Tab)
	testing.expect(t, ar.controller_button_command(&mapping, .Back, .Menu) == .Back)
	testing.expect(t, ar.controller_button_command(&mapping, .Start, .Menu) == .Character)
	testing.expect(t, ar.controller_button_command(&mapping, .Dpad_Up, .Menu) == .Up)
	testing.expect(t, ar.controller_button_command(&mapping, .Dpad_Down, .Gameplay) == .Minimap_Zoom_Out)
	testing.expect(t, ar.controller_button_command(&mapping, .Dpad_Left, .Gameplay) == .None)
	testing.expect(t, ar.controller_trigger_command(&mapping, .Left) == .Ability_1)
	testing.expect(t, ar.controller_trigger_command(&mapping, .Right) == .Ability_4)
	_ = ar.controller_remap_button(&mapping, .A, .Character)
	testing.expect(t, ar.controller_button_command(&mapping, .A, .Menu) == .Character,
		"a remapped Character button must remain an overlay toggle in menu context")
	_ = ar.controller_remap_button(&mapping, .X, .Back)
	testing.expect(t, ar.controller_button_command(&mapping, .X, .Menu) == .Interact,
		"other gameplay remaps must not leak through the fixed menu layout")
	menu_intent:ar.Intent
	ar.intent_apply_command(&menu_intent,ar.controller_button_command(&mapping,.Right_Bumper,.Menu),false)
	ar.intent_apply_command(&menu_intent,ar.controller_button_command(&mapping,.Y,.Menu),false)
	testing.expect(t,menu_intent.tab&&menu_intent.inv_drop,"menu RB/Y must resolve to tab/drop overlay intents")
}

@(test)
m9_controller_remap_moves_commands_and_rejects_dpad :: proc(t: ^testing.T) {
	mapping := ar.controller_default_mapping()
	result := ar.controller_remap_button(&mapping, .A, .Ability_2)
	testing.expect(t, result == .Applied)
	testing.expect(t, mapping.gameplay_buttons[.A] == .Ability_2)
	testing.expect(t, mapping.gameplay_buttons[.X] == .None, "moving a command must clear its old button")
	testing.expect(t, mapping.gameplay_buttons[.A] != .Interact, "target collision must leave the displaced command unbound")

	result = ar.controller_remap_trigger(&mapping, .Left, .Ability_3)
	testing.expect(t, result == .Applied)
	testing.expect(t, mapping.triggers[.Left] == .Ability_3)
	testing.expect(t, mapping.gameplay_buttons[.B] == .None, "trigger remap must clear the command's old button")

	before := mapping
	result = ar.controller_remap_button(&mapping, .Dpad_Up, .Ability_1)
	testing.expect(t, result == .Rejected_Fixed_Input && mapping == before, "D-pad remap must be consumed without assignment")
	result = ar.controller_remap_button(&mapping, .Y, .Confirm)
	testing.expect(t, result == .Rejected_Command && mapping == before, "fixed menu commands cannot become gameplay bindings")
}

@(test)
m9_controller_mapping_normalize_deduplicates_buttons_before_triggers :: proc(t: ^testing.T) {
	mapping: ar.Controller_Mapping
	mapping.gameplay_buttons[.A] = .Ability_1
	mapping.gameplay_buttons[.X] = .Ability_1
	mapping.gameplay_buttons[.Dpad_Up] = .Ability_2
	mapping.gameplay_buttons[.B] = .Confirm
	mapping.triggers[.Left] = .Ability_1
	mapping.triggers[.Right] = .Ability_3
	ar.controller_mapping_normalize(&mapping)
	testing.expect(t, mapping.gameplay_buttons[.A] == .Ability_1)
	testing.expect(t, mapping.gameplay_buttons[.X] == .None)
	testing.expect(t, mapping.gameplay_buttons[.Dpad_Up] == .None)
	testing.expect(t, mapping.gameplay_buttons[.B] == .None)
	testing.expect(t, mapping.triggers[.Left] == .None, "buttons must win over duplicate triggers")
	testing.expect(t, mapping.triggers[.Right] == .Ability_3)
}

@(test)
m9_controller_radial_deadzone_has_activation_and_release_hysteresis :: proc(t: ^testing.T) {
	state: ar.Controller_Stick_State
	resolved := ar.controller_resolve_stick({.1, .1}, &state)
	testing.expect(t, resolved == ar.Vec2{} && !state.active)

	resolved = ar.controller_resolve_stick({.3, .4}, &state)
	expected_magnitude := f32((.5 - ar.CONTROLLER_DEADZONE) / (1 - ar.CONTROLLER_DEADZONE))
	testing.expect(t, state.active)
	testing.expect(t, m9_near(resolved.x, .6 * expected_magnitude))
	testing.expect(t, m9_near(resolved.y, .8 * expected_magnitude))

	resolved = ar.controller_resolve_stick({.25, 0}, &state)
	testing.expect(t, state.active && resolved.x > 0, "active stick must remain latched above .24")
	resolved = ar.controller_resolve_stick({.23, 0}, &state)
	testing.expect(t, !state.active && resolved == ar.Vec2{}, "stick must release below .24")
	resolved = ar.controller_resolve_stick({.25, 0}, &state)
	testing.expect(t, !state.active && resolved == ar.Vec2{}, "released stick must cross .28 to reactivate")
}

@(test)
m9_controller_trigger_edges_use_strict_quarter_threshold :: proc(t: ^testing.T) {
	state: ar.Controller_Trigger_State
	testing.expect(t, ar.controller_resolve_trigger(.25, &state) == .None)
	testing.expect(t, ar.controller_resolve_trigger(.26, &state) == .Pressed)
	testing.expect(t, ar.controller_resolve_trigger(1, &state) == .None)
	testing.expect(t, ar.controller_resolve_trigger(.25, &state) == .Released)
	testing.expect(t, ar.controller_resolve_trigger(-1, &state) == .None)
}

@(test)
m9_controller_menu_stick_emits_one_dominant_axis_edge_per_push :: proc(t: ^testing.T) {
	state: ar.Controller_Menu_Stick_State
	testing.expect(t, ar.controller_resolve_menu_stick({.7, .9}, &state) == .Down)
	testing.expect(t, ar.controller_resolve_menu_stick({.7, .9}, &state) == .None, "held menu stick must not repeat")
	testing.expect(t, ar.controller_resolve_menu_stick({0, .3}, &state) == .None)
	testing.expect(t, state.active, "release threshold is strict")
	testing.expect(t, ar.controller_resolve_menu_stick({0, .29}, &state) == .None)
	testing.expect(t, !state.active)
	testing.expect(t, ar.controller_resolve_menu_stick({-.9, .7}, &state) == .Left)
	testing.expect(t, ar.controller_resolve_menu_stick({}, &state) == .None)
	testing.expect(t, ar.controller_resolve_menu_stick({.5, -.5}, &state) == .Up, "dominant-axis ties must resolve vertically")
}

@(test)
m9_options_document_round_trip_and_malformed_fallback :: proc(t:^testing.T) {
	options:=ar.options_default()
	options.fullscreen=false
	options.frame_rate_cap=.FPS_120
	options.view_zoom=3.1
	options.difficulty=.Hell
	options.audio_enabled=false
	options.lighting_enabled=false
	options.minimap_visible=false
	_ = ar.controller_remap_button(&options.gamepad_mapping,.A,.Ability_2)
	data,encoded:=ar.persistence_encode_options(options,7,"2026-08-17T00:00:00Z")
	testing.expect(t,encoded,"options envelope encoding failed")
	defer delete(data)
	testing.expect(t,!strings.contains(string(data),"hell_unlocked"),"profile progress leaked into options.json")
	loaded,legacy_hell,revision,status:=ar.persistence_decode_options(data,true)
	testing.expect(t,status==.Valid&&!legacy_hell&&revision==7&&loaded==options,"persisted options did not round-trip")

	malformed:string="{ definitely not json"
	fallback,_,_,invalid_status:=ar.persistence_decode_options(transmute([]byte)(malformed))
	testing.expect(t,invalid_status==.Corrupt&&fallback==ar.options_default(),"malformed options must fall back independently to defaults")
}
