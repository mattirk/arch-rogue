package archrogue

// Platform edge for the shared Odin game loop. Desktop keeps the existing
// keyboard/mouse/window path; Android translates NativeActivity lifecycle and
// stable raylib touch IDs into the same raylib-free Intent and mobile reducers.

import "core:c"
import "core:fmt"
import "core:strings"
import rl "../vendor/raylib"

ARCH_ROGUE_ANDROID :: #config(RAYLIB_ANDROID, false)
// The web target is the freestanding wasm32 Emscripten build. Simulation stays
// platform-neutral; this constant only gates platform-facing seams.
ARCH_ROGUE_WEB :: ODIN_OS == .Freestanding
#assert(!(ARCH_ROGUE_ANDROID && ARCH_ROGUE_WEB), "Android and web configs are mutually exclusive")
Platform_C_Int :: c.int

ANDROID_EVENT_START                :: u32(1 << 0)
ANDROID_EVENT_RESUME               :: u32(1 << 1)
ANDROID_EVENT_INIT_WINDOW          :: u32(1 << 2)
ANDROID_EVENT_GAINED_FOCUS         :: u32(1 << 3)
ANDROID_EVENT_PAUSE                :: u32(1 << 4)
ANDROID_EVENT_LOST_FOCUS           :: u32(1 << 5)
ANDROID_EVENT_TERM_WINDOW          :: u32(1 << 6)
ANDROID_EVENT_STOP                 :: u32(1 << 7)
ANDROID_EVENT_DESTROY              :: u32(1 << 8)
ANDROID_EVENT_LOW_MEMORY           :: u32(1 << 9)
ANDROID_EVENT_CONFIG_CHANGED       :: u32(1 << 10)
ANDROID_EVENT_CONTENT_RECT_CHANGED :: u32(1 << 11)

Platform_Runtime :: struct {
	mobile:                bool,
	display_revision:      u64,
	metrics:               Mobile_Display_Metrics,
	layout:                Mobile_Layout,
	layout_status:         Mobile_Layout_Status,
	touch:                 Mobile_Touch_State,
	lifecycle:             Mobile_Lifecycle_State,
	resume_gate:           bool,
	resume_return:         App_Mode,
	graphics_reload_due:   bool,
	ready_marker_emitted:  bool,
	touch_log_initialized: bool,
	last_raw_touch_count:  int,
	last_context:          Mobile_Input_Context_Key,
}

platform_log :: proc(message: string) {
	owned := strings.clone(message)
	defer delete(owned)
	when ARCH_ROGUE_ANDROID {
		rl.ArchRogueAndroidLog(strings.clone_to_cstring(owned, context.temp_allocator))
	} else when ARCH_ROGUE_WEB {
		platform_web_console_log(owned)
	} else {
		fmt.eprintln(owned)
	}
}

platform_android_internal_data_path :: proc() -> string {
	when ARCH_ROGUE_ANDROID {
		path := rl.ArchRogueAndroidInternalDataPath()
		if path == nil do return ""
		return strings.clone(string(path))
	}
	return ""
}

platform_refresh_mobile_layout :: proc(runtime: ^Platform_Runtime) -> bool {
	if runtime == nil || !runtime.mobile do return false
	width := max(1, int(rl.GetScreenWidth()))
	height := max(1, int(rl.GetScreenHeight()))
	dpi := rl.GetWindowScaleDPI()
	density := max(f32(1), dpi.x)
	insets: Mobile_Pixel_Insets
	when ARCH_ROGUE_ANDROID {
		left, top, right, bottom: Platform_C_Int
		if rl.ArchRogueAndroidGetSafeInsets(&left, &top, &right, &bottom) != 0 {
			insets = {int(left), int(top), int(right), int(bottom)}
		}
	}
	changed := runtime.metrics.surface_width != width || runtime.metrics.surface_height != height ||
		runtime.metrics.density != density || runtime.metrics.cutout != insets
	if !changed do return false
	runtime.display_revision += 1
	runtime.metrics = {
		surface_width = width,
		surface_height = height,
		density = density,
		cutout = insets,
		revision = runtime.display_revision,
	}
	runtime.layout, runtime.layout_status = mobile_layout_build(runtime.metrics)
	return true
}

platform_runtime_init :: proc(runtime: ^Platform_Runtime, mode: App_Mode) {
	if runtime == nil do return
	runtime^ = {}
	when ARCH_ROGUE_ANDROID {
		runtime.mobile = true
		runtime.resume_return = mode
		runtime.lifecycle = mobile_lifecycle_init(mode)
		platform_refresh_mobile_layout(runtime)
		platform_log(fmt.tprintf(
			"ARCH_ROGUE_ANDROID_INIT api=%d native=%dx%d density=%.2f safe=%d,%d,%d,%d",
			rl.ArchRogueAndroidApiLevel(), runtime.metrics.surface_width, runtime.metrics.surface_height,
			runtime.metrics.density, runtime.metrics.cutout.left, runtime.metrics.cutout.top,
			runtime.metrics.cutout.right, runtime.metrics.cutout.bottom,
		))
	}
}

platform_live_descent :: proc(app: ^App) -> bool {
	return app != nil && app.run.run_id != "" && app.run.terminal == .Active &&
		(app.mode == .Playing || app.mode == .Paused || app.mode == .Resume_Veil ||
		((app.mode == .Options || app.mode == .Controls) && app.options_return == .Paused))
}

platform_lifecycle_merge :: proc(destination: ^Mobile_Lifecycle_Result, source: Mobile_Lifecycle_Result) {
	if destination == nil do return
	destination.effects += source.effects
	if .Show_Resume_Veil in source.effects do destination.resume_return = source.resume_return
}

platform_reduce_android_events :: proc(runtime: ^Platform_Runtime, app: ^App) -> Mobile_Lifecycle_Result {
	result: Mobile_Lifecycle_Result
	if runtime == nil || app == nil || !runtime.mobile do return result
	when ARCH_ROGUE_ANDROID {
		mask := u32(rl.ArchRogueAndroidDrainLifecycleEvents())
		live := platform_live_descent(app)
		if mask & ANDROID_EVENT_LOST_FOCUS != 0 {
			platform_lifecycle_merge(&result, mobile_lifecycle_reduce(&runtime.lifecycle, .Focus_Lost, live, app.mode))
		}
		if mask & ANDROID_EVENT_PAUSE != 0 {
			platform_lifecycle_merge(&result, mobile_lifecycle_reduce(&runtime.lifecycle, .Pause, live, app.mode))
		}
		if mask & ANDROID_EVENT_STOP != 0 {
			platform_lifecycle_merge(&result, mobile_lifecycle_reduce(&runtime.lifecycle, .Stop, live, app.mode))
		}
		if mask & ANDROID_EVENT_TERM_WINDOW != 0 {
			platform_lifecycle_merge(&result, mobile_lifecycle_reduce(&runtime.lifecycle, .Surface_Lost, live, app.mode))
		}
		if mask & ANDROID_EVENT_LOW_MEMORY != 0 {
			platform_lifecycle_merge(&result, mobile_lifecycle_reduce(&runtime.lifecycle, .Low_Memory, live, app.mode))
		}
		if mask & ANDROID_EVENT_DESTROY != 0 {
			platform_lifecycle_merge(&result, mobile_lifecycle_reduce(&runtime.lifecycle, .Destroy, live, app.mode))
		}
		if mask & ANDROID_EVENT_INIT_WINDOW != 0 {
			platform_lifecycle_merge(&result, mobile_lifecycle_reduce(&runtime.lifecycle, .Surface_Restored, live, app.mode))
		}
		if mask & (ANDROID_EVENT_START | ANDROID_EVENT_RESUME) != 0 {
			platform_lifecycle_merge(&result, mobile_lifecycle_reduce(&runtime.lifecycle, .Resume, live, app.mode))
		}
		if mask & ANDROID_EVENT_GAINED_FOCUS != 0 {
			platform_lifecycle_merge(&result, mobile_lifecycle_reduce(&runtime.lifecycle, .Focus_Gained, live, app.mode))
		}
		if mask & (ANDROID_EVENT_CONFIG_CHANGED | ANDROID_EVENT_CONTENT_RECT_CHANGED) != 0 {
			result.effects += {.Refresh_Insets, .Reset_Accumulator}
		}
		if mask != 0 {
			platform_log(fmt.tprintf(
				"ARCH_ROGUE_LIFECYCLE mask=0x%x interactive=%v surface=%v focused=%v resumed=%v",
				mask, mobile_lifecycle_interactive(&runtime.lifecycle), runtime.lifecycle.surface_ready,
				runtime.lifecycle.focused, runtime.lifecycle.resumed,
			))
		}
	}
	return result
}

platform_wait_suspended :: proc(runtime: ^Platform_Runtime) {
	if runtime == nil || !runtime.mobile do return
	// The reviewed raylib patch makes this a nonblocking looper drain. A short
	// wait avoids spinning while Android owns no drawable surface.
	rl.PollInputEvents()
	rl.WaitTime(.025)
}

platform_mobile_context :: proc(app: ^App) -> Mobile_Input_Context_Key {
	if app == nil do return {}
	layer := Mobile_Input_Layer.Base
	if app.mobile_guard.kind != .None {
		layer = .Confirmation
	} else if app.mode == .Select {
		layer = .Archetype
	} else if app.mode == .Playing {
		if app_story_minigame_active(app) do layer = .Minigame
		else if app_story_panel_active(app) do layer = .Story
		else if app.inventory_open do layer = .Inventory
		else if app.character_open do layer = .Character
		else if app.shop_open do layer = .Shop
		else do layer = .Gameplay
	}
	return {mode = app.mode, layer = layer}
}

platform_mobile_rect_from_design :: proc(rect: rl.Rectangle) -> Mobile_Rect {
	scale := ui_presentation().scale
	return {rect.x * scale, rect.y * scale, rect.width * scale, rect.height * scale}
}

platform_mobile_rect_from_story :: proc(rect: Story_UI_Rect) -> Mobile_Rect {
	return {rect.x, rect.y, rect.width, rect.height}
}

platform_mobile_add_target :: proc(
	set: ^Mobile_Target_Set,
	layout: ^Mobile_Layout,
	id: int,
	kind: Mobile_Target_Kind,
	rect: Mobile_Rect,
	index := 0,
	enabled := true,
	control := Mobile_Control.None,
) {
	if set == nil || layout == nil do return
	target_rect := mobile_rect_expand_to_minimum(rect, layout.minimum_target_px, layout.safe_rect)
	_ = mobile_target_set_add(set, {
		id = id, kind = kind, rect = target_rect, index = index, enabled = enabled, control = control,
	})
}

platform_choice_row_rect :: proc(count, index: int) -> rl.Rectangle {
	panel := menu_panel(560, i32(300 + max(0, count - 2) * 52))
	return {panel.x + 34, panel.y + 118 + f32(index) * 54, panel.width - 68, 44}
}

platform_mobile_build_targets :: proc(runtime: ^Platform_Runtime, app: ^App) -> Mobile_Target_Set {
	set: Mobile_Target_Set
	if runtime == nil || app == nil || !runtime.mobile || runtime.layout_status != .Valid do return set
	context_key := platform_mobile_context(app)
	mobile_target_set_init(&set, context_key, runtime.layout.revision)
	layout := &runtime.layout

	if runtime.resume_gate {
		platform_mobile_add_target(&set, layout, 1, .Menu_Activate, layout.safe_rect)
		return set
	}
	if app.mobile_guard.kind != .None {
		confirm, cancel := mobile_guard_button_rects(layout)
		platform_mobile_add_target(&set, layout, 2, .Guard_Confirm, confirm)
		platform_mobile_add_target(&set, layout, 3, .Guard_Cancel, cancel)
		return set
	}

	switch app.mode {
	case .Title:
		for i in 0 ..< len(Title_Action) {
			platform_mobile_add_target(&set, layout, 100 + i, .Menu_Activate,
				platform_mobile_rect_from_design(title_row_rect(i)), index = i,
				enabled = title_action_enabled(app, Title_Action(i)))
		}
	case .Select:
		for i in 0 ..< len(Archetype_Id) {
			platform_mobile_add_target(&set, layout, 200 + i, .Archetype_Preview,
				platform_mobile_rect_from_design(select_slot_rect(app, i)), index = i)
		}
		platform_mobile_add_target(&set, layout, 210, .Archetype_Confirm, mobile_center_button_rect(layout))
	case .Paused:
		for i in 0 ..< len(Pause_Action) {
			platform_mobile_add_target(&set, layout, 300 + i, .Menu_Activate,
				platform_mobile_rect_from_design(pause_row_rect(i)), index = i)
		}
	case .Options:
		// Fullscreen is a desktop window effect; Android owns one native surface.
		// Keep its disabled row as an inert target so neighboring 48 dp expansion
		// cannot activate Frame rate cap through the visible fullscreen row.
		for i in 0 ..< 10 {
			platform_mobile_add_target(&set, layout, 400 + i, .Menu_Activate,
				platform_mobile_rect_from_design(options_row_rect(app, i)), index = i,
				enabled = i != 0)
		}
	case .Controls:
		if !app.controls_capture {
			for i in 0 ..< len(CONTROLLER_REMAPPABLE_COMMANDS) {
				platform_mobile_add_target(&set, layout, 500 + i, .Menu_Activate,
					platform_mobile_rect_from_design(controls_row_rect(app, i)), index = i)
			}
		}
	case .Chronicle:
		presentation := ui_presentation()
		chronicle_layout := chronicle_ui_layout(presentation.width, presentation.height, presentation.responsive_width)
		chip_w := min(f32(190), (chronicle_layout.filters.width - 24) / 3)
		for i in 0 ..< 3 {
			rect := rl.Rectangle{chronicle_layout.filters.x + f32(i) * (chip_w + 12), chronicle_layout.filters.y, chip_w, 38}
			platform_mobile_add_target(&set, layout, 600 + i, .Chronicle_Filter,
				platform_mobile_rect_from_design(rect), index = i)
		}
		count := chronicle_filtered_count(&app.profile, &app.chronicle)
		visible := min(chronicle_layout.visible_cards, max(0, count - app.chronicle.scroll))
		for i in 0 ..< visible {
			platform_mobile_add_target(&set, layout, 610 + i, .Menu_Select,
				platform_mobile_rect_from_design(chronicle_card_rect_for_count(chronicle_layout, i, visible)),
				index = app.chronicle.scroll + i)
		}
	case .Abandon_Confirm:
		for i in 0 ..< 2 {
			platform_mobile_add_target(&set, layout, 700 + i, .Menu_Activate,
				platform_mobile_rect_from_design(platform_choice_row_rect(2, i)), index = i)
		}
	case .Recovery, .Save_Error:
		for i in 0 ..< 3 {
			platform_mobile_add_target(&set, layout, 710 + i, .Menu_Activate,
				platform_mobile_rect_from_design(platform_choice_row_rect(3, i)), index = i)
		}
	case .Resume_Veil, .Dead, .Victory:
		platform_mobile_add_target(&set, layout, 720, .Menu_Activate, layout.safe_rect)
	case .Save_Wait:
	case .Playing:
		if app_play_modal_open(app) {
			modal := story_modal_layout(app, runtime.metrics.surface_width, runtime.metrics.surface_height)
			switch modal.kind {
			case .Minigame:
				for i in 0 ..< modal.minigame.board_count {
					platform_mobile_add_target(&set, layout, 800 + i, .Minigame_Cell,
						platform_mobile_rect_from_story(modal.minigame.cells[i]), index = i)
				}
				if app.story_minigame.phase == .Ready {
					platform_mobile_add_target(&set, layout, 830, .Story_Panel,
						platform_mobile_rect_from_story(modal.minigame.panel))
				}
			case .Panel:
				if app_story_panel_narration_complete(app) && modal.panel.choice_count > 0 {
					for i in 0 ..< modal.panel.choice_count {
						platform_mobile_add_target(&set, layout, 840 + i, .Story_Choice,
							platform_mobile_rect_from_story(modal.panel.choice_rows[i]), index = i)
					}
				} else {
					platform_mobile_add_target(&set, layout, 850, .Story_Panel,
						platform_mobile_rect_from_story(modal.panel.panel))
				}
			case .None:
			}
		} else if app.character_open {
			for tab in Character_Tab {
				platform_mobile_add_target(&set, layout, 900 + int(tab), .Character_Tab,
					platform_mobile_rect_from_design(character_tab_rect(tab)), index = int(tab))
			}
			if app.character_tab == .Disciplines {
				for degree in 0 ..< DISCIPLINE_DEGREES do for column in 0 ..< DISCIPLINE_PATHS_PER_ARCHETYPE {
					index := degree * DISCIPLINE_PATHS_PER_ARCHETYPE + column
					platform_mobile_add_target(&set, layout, 910 + index, .Menu_Activate,
						platform_mobile_rect_from_design(discipline_cell_rect(column, degree)), index = index)
				}
			}
		} else if app.shop_open {
			for mode in Shop_Mode {
				platform_mobile_add_target(&set, layout, 950 + int(mode), .Shop_Mode,
					platform_mobile_rect_from_design(shop_mode_rect(mode)), index = int(mode),
					enabled = mode != app.shop_mode)
			}
			visible := min(SHOP_VISIBLE_ROWS, max(0, shop_entry_count(app) - app.shop_scroll))
			for row in 0 ..< visible {
				platform_mobile_add_target(&set, layout, 960 + row, .Menu_Select,
					platform_mobile_rect_from_design(shop_row_rect(row)), index = app.shop_scroll + row)
			}
			platform_mobile_add_target(&set, layout, 980, .Guard_Request_Transaction, mobile_center_button_rect(layout))
		} else if app.inventory_open {
			for mode in Inventory_Sort_Mode {
				platform_mobile_add_target(&set, layout, 1000 + int(mode), .Inventory_Sort,
					platform_mobile_rect_from_design(inventory_sort_chip_rect(mode)), index = int(mode))
			}
			visible := min(INVENTORY_VISIBLE_ROWS, max(0, app.run.player.bag_count - app.inv_scroll))
			for row in 0 ..< visible {
				platform_mobile_add_target(&set, layout, 1010 + row, .Menu_Select,
					platform_mobile_rect_from_design(inventory_row_rect(row)), index = app.inv_scroll + row)
			}
			confirm, drop := mobile_guard_button_rects(layout)
			platform_mobile_add_target(&set, layout, 1030, .Menu_Activate, confirm, index = app.inv_index,
				enabled = app.run.player.bag_count > 0)
			platform_mobile_add_target(&set, layout, 1031, .Guard_Request_Drop, drop,
				enabled = app.run.player.bag_count > 0)
		} else {
			set = mobile_gameplay_target_set(
				layout,
				context_key,
				player_interaction_available(&app.run),
				app.mobile_utility_open,
			)
		}
	}
	return set
}

platform_touch_snapshot :: proc() -> Mobile_Touch_Snapshot {
	snapshot: Mobile_Touch_Snapshot
	count := clamp(int(rl.GetTouchPointCount()), 0, len(snapshot.points))
	for i in 0 ..< count {
		id := rl.GetTouchPointId(i32(i))
		if id < 0 do continue
		position := rl.GetTouchPosition(i32(i))
		snapshot.points[snapshot.count] = {Mobile_Touch_Id(id), Vec2(position)}
		snapshot.count += 1
	}
	return snapshot
}

platform_intent_has_navigation :: proc(intent: Intent) -> bool {
	return intent.menu_delta != 0 || intent.menu_horizontal != 0 || intent.menu_index_valid ||
		intent.confirm || intent.back || intent.tab
}

platform_mobile_apply_guard :: proc(app: ^App, intent: ^Intent, context_key: Mobile_Input_Context_Key) {
	if app == nil || intent == nil do return
	if app.mobile_guard.kind != .None && intent.back {
		app.mobile_guard = {}
		intent.back = false
	}
	switch intent.mobile_guard_request {
	case .Inventory_Drop:
		if app.inventory_open && app.run.player.bag_count > 0 {
			app.mobile_guard = {.Inventory_Drop, app.inv_index, context_key}
		}
	case .Shop_Transaction:
		if app.shop_open && shop_entry_count(app) > 0 {
			kind := app.shop_mode == .Buy ? Mobile_Guard_Kind.Shop_Buy : Mobile_Guard_Kind.Shop_Sell
			app.mobile_guard = {kind, app.shop_index, context_key}
		}
	case .Confirm:
		guard := app.mobile_guard
		app.mobile_guard = {}
		switch guard.kind {
		case .Inventory_Drop:
			intent.menu_index = guard.selected_index
			intent.menu_index_valid = true
			intent.inv_drop = true
		case .Shop_Buy, .Shop_Sell:
			intent.menu_index = guard.selected_index
			intent.menu_index_valid = true
			intent.confirm = true
		case .None:
		}
	case .Cancel:
		app.mobile_guard = {}
	case .None:
	}
	intent.mobile_guard_request = .None
}

platform_collect_mobile_intent :: proc(
	runtime: ^Platform_Runtime,
	app: ^App,
	view: ^View,
	controller: ^Controller_Runtime,
) -> Intent {
	intent: Intent
	if runtime == nil || app == nil || view == nil do return intent
	raw_touch_count:=max(0,int(rl.GetTouchPointCount()))
	if !runtime.touch_log_initialized {
		runtime.touch_log_initialized=true
		runtime.last_raw_touch_count=raw_touch_count
	} else if raw_touch_count!=runtime.last_raw_touch_count {
		first_id:i32=-1
		first_position:rl.Vector2
		if raw_touch_count>0 {
			first_id=rl.GetTouchPointId(0)
			first_position=rl.GetTouchPosition(0)
		}
		platform_log(fmt.tprintf(
			"ARCH_ROGUE_TOUCH contacts=%d first_id=%d first=%.1f,%.1f",
			raw_touch_count,first_id,first_position.x,first_position.y,
		))
		runtime.last_raw_touch_count=raw_touch_count
	}
	snapshot := platform_touch_snapshot()
	had_touch := snapshot.count > 0 || runtime.touch.contact_count > 0

	// With no contact, preserve the existing connected keyboard/controller/mouse
	// vocabulary. Android also maps touch[0] to mouse; some devices expose that
	// synthetic press one frame before the stable touch ID. Suppress that press so
	// it cannot enter a menu and then activate a row in the newly changed context.
	touch_mapped_mouse_press := raw_touch_count == 0 && rl.IsMouseButtonPressed(.LEFT)
	if !had_touch && !runtime.resume_gate && !touch_mapped_mouse_press {
		intent = collect_intent(app, view, controller)
		intent.toggle_fullscreen = false
		if platform_intent_has_navigation(intent) do app.input_modality = .Keyboard_Mouse
	} else {
		collect_controller_intent(app, controller, &intent)
	}
	back_pressed := rl.IsKeyPressed(.BACK)
	when ARCH_ROGUE_ANDROID {
		if rl.ArchRogueAndroidDrainBackPresses() > 0 {
			back_pressed = true
			platform_log("ARCH_ROGUE_BACK source=dispatcher")
		}
	}
	if back_pressed {
		back := mobile_android_back_intent(app.mode == .Playing, app.mobile_utility_open)
		mobile_intent_merge(&intent, back)
		app.input_modality = .Keyboard_Mouse
	}

	targets := platform_mobile_build_targets(runtime, app)
	context_key := platform_mobile_context(app)
	environment := Mobile_Input_Environment{
		input_context = context_key,
		layout = &runtime.layout,
		targets = &targets,
		camera = {
			target_world = Vec2(view.camera.target),
			offset_px = Vec2(view.camera.offset),
			zoom = view.camera.zoom,
		},
		player_tile = app.run.player.pos,
		current_view_zoom = view.base_zoom,
		view_zoom_min = ZOOM_MIN,
		view_zoom_max = ZOOM_MAX,
		gameplay = app.mode == .Playing && !app.inventory_open && !app.character_open && !app.shop_open &&
			!app_play_modal_open(app) && !runtime.resume_gate,
	}
	mobile_result := mobile_touch_process_snapshot(&runtime.touch, snapshot, &environment)
	view.mobile_joystick_vector = runtime.touch.joystick_vector
	if had_touch || mobile_result.intent.confirm || mobile_result.intent.menu_index_valid {
		app.input_modality = .Touch
	}
	if runtime.resume_gate && (mobile_result.intent.confirm || mobile_result.intent.back || intent.back) {
		runtime.resume_gate = false
		return_mode:=runtime.resume_return
		if return_mode==.Resume_Veil do return_mode=.Playing
		app.mode=return_mode
		intent = {}
		return intent
	}
	mobile_intent_merge(&intent, mobile_result.intent)
	if mobile_result.view_zoom.valid {
		view_apply_base_zoom(view, mobile_result.view_zoom.value)
		app.options.view_zoom = view.base_zoom
		if mobile_result.view_zoom.commit do app_mark_options_changed(app)
	}
	platform_mobile_apply_guard(app, &intent, context_key)
	return intent
}

platform_collect_intent :: proc(
	runtime: ^Platform_Runtime,
	app: ^App,
	view: ^View,
	controller: ^Controller_Runtime,
) -> Intent {
	if runtime != nil && runtime.mobile do return platform_collect_mobile_intent(runtime, app, view, controller)
	return collect_intent(app, view, controller)
}
