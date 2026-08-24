package archrogue

// App owns everything raylib-free: the state machine and the simulation.
// Title screen proper lands in M5; until then boot goes straight to
// archetype select.

import "core:math"
import "core:math/linalg"

SIM_HZ :: 60
SIM_DT :: 1.0 / SIM_HZ
MOUSE_WALK_STOP_RADIUS :: 0.12 // combat/player.py click-to-walk dead zone
MOUSE_AIM_DEAD_ZONE :: 0.05 // combat/aim.py ignores cursor jitter at the feet
INVENTORY_VISIBLE_ROWS :: 8
SHOP_VISIBLE_ROWS :: 8
MINIMAP_ZOOM_DEFAULT :: f32(1.0)
MINIMAP_ZOOM_MIN     :: f32(0.5)
MINIMAP_ZOOM_MAX     :: f32(2.5)
MINIMAP_ZOOM_STEP    :: f32(1.2)
MINIMAP_CARD_WIDTH   :: 172
MINIMAP_CARD_HEIGHT  :: 110
MINIMAP_BASE_HALF_STEP_X :: f32(4)
MINIMAP_BASE_HALF_STEP_Y :: f32(2)
MINIMAP_MARKER_EDGE_INSET :: f32(7)
MINIMAP_ARROW_TIP_LENGTH :: f32(5)
MINIMAP_ARROW_BACK_LENGTH :: f32(2)
MINIMAP_ARROW_HALF_BASE :: f32(2)
MINIMAP_PLAYER_RADIUS :: f32(2)
MINIMAP_PLAYER_TICK_REACH :: f32(3)
MINIMAP_PLAYER_FACING_SAMPLE :: f32(1.4)
MINIMAP_BAR_COLOR :: [4]u8{226,168,88,255}
MINIMAP_GARDEN_COLOR :: [4]u8{116,196,118,255}
MINIMAP_STAIRS_COLOR :: [4]u8{186,120,255,255}
MINIMAP_PLAYER_COLOR :: [4]u8{240,238,224,255}
MINIMAP_INK_COLOR :: [4]u8{12,11,16,255}
MINIMAP_GOLD_BRIGHT :: [4]u8{236,214,168,255}
GUIDANCE_WAVE_WINDOW_TILES :: f32(3)
GUIDANCE_WAVE_TILES_PER_SECOND :: f32(1.2)
PLAYER_DIE_SECONDS :: 1.0
PLAYER_DEATH_OVERLAY_DELAY :: PLAYER_DIE_SECONDS + 0.9

App_Mode :: enum {
	Title,
	Select,
	Playing,
	Paused,
	Options,
	Controls,
	Chronicle,
	Abandon_Confirm,
	Recovery,
	Save_Wait,
	Save_Error,
	Resume_Veil,
	Dead,
	Victory,
}

Title_Action :: enum u8 {
	Resume,
	New_Run,
	Chronicle,
	Options,
	Quit,
}

Pause_Action :: enum u8 {
	Resume,
	Options,
	Save_Return,
	Quit,
}

Character_Tab :: enum {
	Overview,
	Disciplines,
}

Shop_Mode :: enum {
	Buy,
	Sell,
}

Platform_Effect :: enum {
	Apply_Window,
	Apply_FPS,
	Apply_Zoom,
	Apply_Audio,
	Save_Options,
}

App :: struct {
	tick:           u64,
	mode:           App_Mode,
	select_index:   int,
	seed:           u64,
	options:        Options,
	profile:        Profile_State,
	title_index:    int,
	pause_index:    int,
	options_index:  int,
	options_return: App_Mode,
	quit_requested: bool,
	platform_effects: bit_set[Platform_Effect],
	ui_sfx_bank:     Sfx_Bank, // transient reducer decision, consumed after app_apply
	ui_sfx_override: bool,
	ui_sfx_suppress: bool,
	input_modality:      Mobile_Input_Modality,
	mobile_guard:        Mobile_Guard_State,
	mobile_utility_open: bool,
	controls_index: int,
	controls_capture: bool,
	controls_status: string,
	run:            Run,
	story_panel:    Story_Panel_State,
	story_minigame: Story_Minigame_State,
	story_minigame_cursor: int,
	move_input:     Vec2, // held keyboard movement, applied every sim tick
	aim_input:      Vec2, // live desktop cursor/arrow aim in tile space
	aim_live:       bool, // aim_input came from an actively pointed device this frame
	mouse_walk:     bool, // held LMB fallback when no movement key is down
	mouse_target:   Vec2,
	mouse_press_pending: bool, // latched until a fixed tick sees a short click
	mouse_press_aim:     Vec2,
	mouse_input_blocked: bool, // consume the click that began a run until release
	death_pending: bool, // die/dead authored presentation before summary
	death_timer:   f32,
	inventory_open: bool,
	character_open: bool,
	character_tab:  Character_Tab,
	discipline_column: int,
	discipline_degree: int, // zero-based row in the 4x5 grid
	shop_open:      bool,
	shop_mode:      Shop_Mode,
	shop_index:     int,
	shop_scroll:    int,
	inv_index:      int,
	inv_scroll:     int,
	inv_sort_mode:  Inventory_Sort_Mode,
	minimap_visible: bool,
	minimap_zoom:    f32,
	dev_controls:    bool, // ARCH_ROGUE_DEV=1: N/R/B floor shortcuts
	dev_reveal:     bool, // ARCH_ROGUE_REVEAL=1: fog disabled for screenshots
	active_run_available: bool,
	active_run_damaged:   bool,
	profile_save_damaged: bool,
	options_save_damaged: bool,
	persistence_request:  Persistence_Request,
	failed_request:       Persistence_Request,
	persistence_error:    Persistence_Error_Kind,
	persistence_return:   App_Mode,
	confirm_index:        int,
	chronicle:            Chronicle_View_State,
	run_dirty:            bool,
	run_critical:         bool,
	run_dirty_serial:     u64,
}

Run :: struct {
	run_id:       string, // allocator-owned stable identity for the active descent
	revision:     u64,
	active_ticks: u64,
	started_at_utc: string, // allocator-owned; wall time never feeds simulation
	ended_at_utc:   string, // allocator-owned once terminal
	terminal:       Run_Terminal_State,
	finalization:   Run_Finalization_Phase,
	seed:         u64,
	depth:        int, // 1-based dungeon level
	difficulty:   Difficulty_Id, // snapshotted at run start; options affect the next run
	dungeon:      Dungeon,
	player:       Player,
	enemies:      [dynamic]Enemy,
	next_enemy_id: u32,
	next_familiar_id: u32,
	next_save_entity_id: u64,
	storm_cast_counter: u32,
	floor_epoch:   u32, // increments whenever dungeon geometry is regenerated
	projectiles:  [dynamic]Projectile,
	familiars:    [dynamic]Familiar,
	bells:        [dynamic]Ambush_Bell,
	numbers:      [dynamic]Damage_Number,
	ground_items: [dynamic]Ground_Item,
	shopkeeper:   Shopkeeper,
	has_shopkeeper: bool,
	ambient_residents: Ambient_Room_Npc_Set,
	refuge:       Refuge_State,
	shop_requested: bool,
	loot_rng:     Pcg32, // kill-drop stream, consumed across the floor's life
	combat_rng:   Pcg32, // independent crit/proc/familiar stream
	nav:          Nav_Field, // player-tracking route field (MX.2.3)
	sfx:          [dynamic]Sfx_Event, // transient; drained by the audio layer each frame
	feel:         [dynamic]Feel_Event, // deterministic presentation events
	hitstop_ticks: int, // impact-freeze ticks pending; transient, never saved
	dark_floor:   bool,
	theme_index:  int,
	explored:     [MAP_W][MAP_H]bool, // fog-of-war memory (lit floors render it)
	visible:      [MAP_W][MAP_H]bool, // current LOS visibility, sim-refreshed
	boss_engaged: bool,
	sealed:       [dynamic]Sealed_Tile, // arena seal, restored on boss death
	tyrant_dead:  bool,
	victory:      bool,
	kills:        int,
	// MX.4 — authored descent plan and run-wide ledgers.
	modifier:     Run_Modifier_Id, // one modifier per run, rolled with the plan
	plan:         [DUNGEON_DEPTH]Floor_Plan,
	story:        Story_State,
	story_runtime: Story_Run_Runtime,
	bars_visited: int, // Bar pilgrimage: counted where floors are created,
	bars_toasted: int, // never reset per floor (unlike Refuge_State)
	challenge_rooms_cleared: int,
	arrival_timer: f32, // non-blocking depth/theme title card countdown
	// MX.5 — interactables, run reward ledgers, and the wall-face touch.
	traps:        [dynamic]Trap,
	shrines:      [dynamic]Shrine,
	secrets:      [dynamic]Secret,
	traps_triggered: int,
	shrines_used:    int,
	secrets_opened:  int,
	notable_loot:  [MAX_NOTABLE_LOOT]Notable_Loot,
	notable_count: int,
	visited_themes:  [len(THEMES)]bool,
	defeated_bosses: [Boss_Id]bool,
	last_damage_source: string, // semantic/static source id or adopted save string
	critical_save_requested: bool, // transient typed signal from simulation rewards
	save_owned_strings: [dynamic]string, // decoded static-content strings owned by this Run
	wall_face_tile:  [2]int,
	wall_face_timer: f32, // counts down; renderer derives the frame
	wall_touches:    int,
	potions_used:    int, // persisted run facts for the Steam achievement funnel
	elites_killed:   int,
}

ARRIVAL_TITLE_SECONDS :: 2.4
ARRIVAL_FADE_SECONDS :: 0.55

// Frame commands from the platform layer; the sim never sees raylib.
Intent :: struct {
	move:             Vec2, // tile-space, unnormalized sum of held keys
	aim:              Vec2, // tile-space direction from player toward the cursor
	aim_live:         bool, // aim device actively pointed this frame; a parked cursor is not live
	mouse_walk:       bool,
	mouse_press:      bool,
	mouse_press_aim:  Vec2,
	mouse_released:   bool,
	mouse_target:     Vec2,
	actions:          [4]bool,
	action1_released: bool,
	interact:         bool,
	use_heal:         bool,
	use_mana:         bool,
	toggle_inventory:      bool,
	toggle_mobile_utility: bool,
	toggle_minimap:        bool,
	minimap_zoom:     int,
	menu_delta:       int,
	menu_index:       int,
	menu_index_valid: bool,
	inv_drop:         bool,
	inv_sort:         bool,
	inv_cycle_sort:   int,
	inv_sort_mode:    Inventory_Sort_Mode,
	inv_sort_valid:   bool,
	open_character:   bool,
	open_disciplines: bool,
	character_tab:    Character_Tab,
	character_tab_valid: bool,
	menu_horizontal:  int,
	tab:              bool,
	toggle_fullscreen: bool,
	confirm:          bool,
	pointer_confirm:  bool,
	back:             bool,
	quit:             bool,
	remap_button:     Controller_Button,
	remap_button_valid: bool,
	remap_trigger:    Controller_Trigger,
	remap_trigger_valid: bool,
	chronicle_focus:       Chronicle_Focus,
	chronicle_focus_valid: bool,
	mobile_guard_request:  Mobile_Guard_Request,
	descend:          bool, // dev: N
	new_run:          bool, // dev: R
	boss_floor:       bool, // dev: B
}

presentation_scale_for_height :: proc(height: int) -> f32 {
	return f32(max(1, height)) / 720
}

effective_view_zoom :: proc(base: f32, height: int) -> f32 {
	return base * presentation_scale_for_height(height)
}

minimap_zoom_apply :: proc(current: f32, delta: int) -> f32 {
	return clamp(
		current * math.pow(MINIMAP_ZOOM_STEP, f32(delta)),
		MINIMAP_ZOOM_MIN,
		MINIMAP_ZOOM_MAX,
	)
}

minimap_project_relative :: proc(relative, center: Vec2, zoom: f32) -> Vec2 {
	return center + Vec2{
		(relative.x - relative.y) * MINIMAP_BASE_HALF_STEP_X * zoom,
		(relative.x + relative.y) * MINIMAP_BASE_HALF_STEP_Y * zoom,
	}
}

Minimap_Marker_Kind :: enum u8 {
	Bar,
	Garden,
	Stairs,
	Relic,
}

Minimap_Marker :: struct {
	kind: Minimap_Marker_Kind,
	world_pos: Vec2,
}

Minimap_Marker_List :: struct {
	items: [3]Minimap_Marker,
	count: int,
}

minimap_room_discovered :: proc(run: ^Run, room: Room) -> bool {
	if run == nil do return false
	for x in room.x ..< room.x + room.w {
		for y in room.y ..< room.y + room.h {
			if dungeon_in_bounds(x,y) && run.explored[x][y] do return true
		}
	}
	return false
}

// Semantic markers are kept separate from terrain paint. Normal floors use
// cumulative discovery; dark floors expose refuge markers only under live LOS,
// while a once-seen stairs marker remains available as navigation guidance.
minimap_markers :: proc(run: ^Run) -> (result: Minimap_Marker_List) {
	if run == nil do return
	for special in special_rooms(&run.dungeon) {
		if special.kind != .Bar && special.kind != .Garden do continue
		if special.room_index < 0 || special.room_index >= run.dungeon.room_count do continue
		room := run.dungeon.rooms_buf[special.room_index]
		center := room_center(room)
		shown := false
		if run.dark_floor {
			shown = dungeon_in_bounds(center.x,center.y) && run.visible[center.x][center.y]
		} else {
			shown = minimap_room_discovered(run,room)
		}
		if !shown || result.count >= len(result.items) do continue
		kind := special.kind == .Bar ? Minimap_Marker_Kind.Bar : Minimap_Marker_Kind.Garden
		result.items[result.count] = {kind,{f32(center.x)+.5,f32(center.y)+.5}}
		result.count += 1
	}
	stairs := run.dungeon.stairs
	if dungeon_in_bounds(stairs.x,stairs.y) {
		shown := run.dark_floor ? (run.visible[stairs.x][stairs.y] || run.explored[stairs.x][stairs.y]) : run.explored[stairs.x][stairs.y]
		if shown && result.count < len(result.items) {
			result.items[result.count] = {.Stairs,{f32(stairs.x)+.5,f32(stairs.y)+.5}}
			result.count += 1
		}
	}
	return
}

minimap_clamp_to_bounds :: proc(pos, center, half_extents: Vec2) -> (clamped: Vec2, was_clamped: bool) {
	delta := pos-center
	scale: f32 = 1
	if abs(delta.x) > half_extents.x && abs(delta.x) > 1e-6 do scale = min(scale,half_extents.x/abs(delta.x))
	if abs(delta.y) > half_extents.y && abs(delta.y) > 1e-6 do scale = min(scale,half_extents.y/abs(delta.y))
	if scale >= 1 do return pos,false
	return center+delta*scale,true
}

// Triangle order is tip, then the two base wings. Renderers may draw it
// directly; tests can pin the ray/bounds math without a display.
minimap_edge_arrow_vertices :: proc(anchor, center: Vec2) -> (points: [3]Vec2) {
	direction := anchor-center
	length := math.hypot(direction.x,direction.y)
	if length <= 1e-6 do direction = {0,-1}
	else do direction /= length
	perpendicular := Vec2{-direction.y,direction.x}
	base := anchor-direction*MINIMAP_ARROW_BACK_LENGTH
	points[0] = anchor+direction*MINIMAP_ARROW_TIP_LENGTH
	points[1] = base+perpendicular*MINIMAP_ARROW_HALF_BASE
	points[2] = base-perpendicular*MINIMAP_ARROW_HALF_BASE
	return
}

minimap_player_tick_end :: proc(center, facing: Vec2, zoom: f32) -> (end: Vec2, shown: bool) {
	if math.hypot(facing.x,facing.y) <= 1e-6 do return center,false
	projected := minimap_project_relative(facing*MINIMAP_PLAYER_FACING_SAMPLE,center,zoom)-center
	length := math.hypot(projected.x,projected.y)
	if length <= 1e-6 do return center,false
	return center+projected/length*MINIMAP_PLAYER_TICK_REACH,true
}

// Pygame's authored guiding-floor sequence is a brightness ramp: frame zero is
// ordinary floor and the final frame is the full rune. A three-tile triangular
// crest travels away from the player whenever they stop moving.
guidance_wave_frame :: proc(order, tile_count, peak_frame: int, idle_elapsed: f32, moving: bool) -> int {
	if moving || tile_count <= 0 || peak_frame <= 0 do return 0
	crest := math.mod(max(f32(0),idle_elapsed)*GUIDANCE_WAVE_TILES_PER_SECOND,f32(tile_count)+GUIDANCE_WAVE_WINDOW_TILES)
	distance := crest-f32(order)
	if distance < 0 || distance >= GUIDANCE_WAVE_WINDOW_TILES do return 0
	half_window := GUIDANCE_WAVE_WINDOW_TILES*.5
	envelope := 1-abs(distance-half_window)/half_window
	return max(0,int(f32(peak_frame)*envelope+.5))
}

app_init :: proc(app: ^App, seed: u64) {
	app.seed = seed
	app.mode = .Title
	app.options = options_default()
	app.options_return = .Title
	app.controls_status = ""
	app.title_index = 1 // New Run; Resume may be disabled until storage is scanned
	app.discipline_degree = 0
	app.minimap_visible = true
	app.minimap_zoom = MINIMAP_ZOOM_DEFAULT
	app.chronicle.archetype_filter = -1
	app.chronicle.difficulty_filter = -1
}

app_reset_run_ui :: proc(app: ^App) {
	app.death_pending = false
	app.death_timer = 0
	app.inventory_open = false
	app.character_open = false
	app.shop_open = false
	app.mobile_utility_open = false
	app.inv_index = 0
	app.inv_scroll = 0
	app.shop_index = 0
	app.shop_scroll = 0
	app.shop_mode = .Buy
	app.pause_index = 0
	app.character_tab = .Overview
	app.discipline_column = 0
	app.discipline_degree = 0
	app.minimap_zoom = MINIMAP_ZOOM_DEFAULT
	app_story_runtime_reset(app)
}

// Restore clears process-local UI/input without discarding the persisted story
// panel or minigame. Their authored text is rebuilt from semantic state.
app_reset_run_ui_after_restore :: proc(app: ^App) {
	if app == nil do return
	app.death_pending = false
	app.death_timer = 0
	app.inventory_open = false
	app.character_open = false
	app.shop_open = false
	app.mobile_utility_open = false
	app.inv_index = 0
	app.inv_scroll = 0
	app.shop_index = 0
	app.shop_scroll = 0
	app.shop_mode = .Buy
	app.pause_index = 0
	app.character_tab = .Overview
	app.discipline_column = 0
	app.discipline_degree = 0
	app.minimap_zoom = MINIMAP_ZOOM_DEFAULT
	app_clear_play_input(app)
	app.mouse_input_blocked = true
	app_story_restore_panel_text(app)
}

aim_outside_dead_zone :: proc(aim: Vec2) -> bool {
	return math.hypot(aim.x, aim.y) > MOUSE_AIM_DEAD_ZONE
}

app_tick :: proc(app: ^App) {
	app.tick += 1
	if app.mode == .Resume_Veil || app.mode == .Save_Wait || app.mode == .Save_Error ||
		app.mode == .Recovery || app.mode == .Abandon_Confirm || app.mode == .Chronicle {
		return
	}
	if app.mode == .Playing {
		if app_play_modal_open(app) {
			app_story_tick_modal(app,SIM_DT)
			app.run.active_ticks += 1
			app_mark_run_dirty(app)
			app_clear_play_input(app)
			return
		}
	}
	tick_feel_events(&app.run,SIM_DT)
	app.run.arrival_timer = max(0, app.run.arrival_timer - SIM_DT)
	app.run.wall_face_timer = max(0, app.run.wall_face_timer - SIM_DT)
	if app.mode == .Playing {
		if app.death_pending {
			app.death_timer += SIM_DT
			player_tick_visual_action(&app.run.player,SIM_DT)
			app.run.player.prev_pos = app.run.player.pos
			app.run.player.moving = false
			if app.death_timer >= PLAYER_DEATH_OVERLAY_DELAY {
				app.mode = .Dead
			}
			return
		}
		// Inventory is a modal pause in the pygame game. UI animation still uses
		// app.tick, but no cooldown, enemy, projectile, or movement clock advances.
		if app.inventory_open || app.character_open || app.shop_open do return
		app.run.active_ticks += 1

		// An actively pointed device (moved/held mouse, touch aim, right stick)
		// owns idle facing; keyboard movement overwrites it in tick_player. A
		// parked cursor is not live, so stopping keeps the last heading instead
		// of snapping toward wherever the mouse happens to rest.
		if app.move_input == {} && app.aim_live && aim_outside_dead_zone(app.aim_input) {
			app.run.player.facing = linalg.normalize0(app.aim_input)
		}

		// A raylib pressed edge may begin and end between two 60 Hz sim ticks.
		// Consume the latched click once so the Pygame MOUSEBUTTONDOWN melee is
		// never lost, even while keyboard movement owns locomotion.
		if app.mouse_press_pending {
			attack_aim := app.mouse_press_aim
			if !aim_outside_dead_zone(attack_aim) do attack_aim = app.run.player.facing
			if app.run.player.hp > 0 && enemy_in_melee_arc(&app.run, attack_aim) {
				player_melee(&app.run, attack_aim)
			}
			app.mouse_press_pending = false
		}

		move := app.move_input
		max_step: f32 = -1
		if move == {} && app.mouse_walk {
			to_cursor := app.mouse_target - app.run.player.pos
			distance := math.hypot(to_cursor.x, to_cursor.y)
			if distance > MOUSE_WALK_STOP_RADIUS {
				move = to_cursor
				// Cap the final fixed step so low render rates cannot overshoot the
				// same 0.12-tile cursor dead zone used by the pygame implementation.
				max_step = distance - MOUSE_WALK_STOP_RADIUS
			}
		}
		// The sim resolves movement auto-melee after player movement but before
		// enemy actions, matching update_player() ordering in the Pygame game.
		sim_tick_limited(
			&app.run,
			move,
			max_step,
			auto_melee = app.run.player.hp > 0 && (app.move_input != {} || app.mouse_walk),
		)
		critical_save:=app.run.critical_save_requested
		app.run.critical_save_requested=false
		app_mark_run_dirty(app,critical=critical_save)
		if app.run.victory {
			app.mode = .Victory
			app_request_terminal(app, .Victory)
			app_clear_play_input(app)
		} else if app.run.player.hp <= 0 {
			app.death_pending = true
			app.death_timer = 0
			app.mobile_utility_open = false
			// Death owns the presentation from this point onward.  Combat clocks are
			// frozen during the authored sequence, so discard the lethal-hit tint
			// instead of leaving the die/dead clips permanently flashed red.
			app.run.player.hit_flash = 0
			app.run.player.hit_flash_duration = 0
			player_start_visual_action(&app.run.player,.Die,PLAYER_DIE_SECONDS)
			app_request_terminal(app, .Death)
			app_clear_play_input(app)
			sfx_emit(&app.run, .Player_Death)
		}
	}
}

app_clear_play_input :: proc(app: ^App) {
	app.move_input = {}
	app.aim_input = {}
	app.aim_live = false
	app.mouse_walk = false
	app.mouse_press_pending = false
}

inventory_clamp_selection :: proc(app: ^App) {
	n := app.run.player.bag_count
	if n <= 0 {
		app.inv_index = 0
		app.inv_scroll = 0
		return
	}
	app.inv_index = clamp(app.inv_index, 0, n - 1)
	if app.inv_index < app.inv_scroll {
		app.inv_scroll = app.inv_index
	} else if app.inv_index >= app.inv_scroll + INVENTORY_VISIBLE_ROWS {
		app.inv_scroll = app.inv_index - INVENTORY_VISIBLE_ROWS + 1
	}
	app.inv_scroll = clamp(app.inv_scroll, 0, max(0, n - INVENTORY_VISIBLE_ROWS))
}

app_mark_options_changed :: proc(app: ^App, effects: bit_set[Platform_Effect] = {}) {
	app.platform_effects += effects + {Platform_Effect.Save_Options}
}

shop_entry_count :: proc(app: ^App) -> int {
	if !app.run.has_shopkeeper do return 0
	return app.shop_mode == .Buy ? app.run.shopkeeper.stock_count : app.run.player.bag_count
}

shop_clamp_selection :: proc(app: ^App) {
	n := shop_entry_count(app)
	app.shop_index = clamp(app.shop_index, 0, max(0, n - 1))
	if n <= 0 {
		app.shop_scroll = 0
		return
	}
	if app.shop_index < app.shop_scroll {
		app.shop_scroll = app.shop_index
	} else if app.shop_index >= app.shop_scroll + SHOP_VISIBLE_ROWS {
		app.shop_scroll = app.shop_index - SHOP_VISIBLE_ROWS + 1
	}
	app.shop_scroll = clamp(app.shop_scroll, 0, max(0, n - SHOP_VISIBLE_ROWS))
}

character_selected_discipline :: proc(app: ^App) -> (Discipline_Id, bool) {
	path, found := discipline_path_at(app.run.player.archetype, app.discipline_column)
	if !found do return {}, false
	return discipline_at(path, app.discipline_degree + 1)
}

app_enter_options :: proc(app: ^App, from: App_Mode) {
	app.options_return = from
	app.options_index = 0
	app.mode = .Options
	app_clear_play_input(app)
}

app_leave_options :: proc(app: ^App) {
	app.mode = app.options_return
	app_clear_play_input(app)
}

app_unlock_hell :: proc(app: ^App) {
	if app == nil do return
	if profile_unlock_hell(&app.profile) {
		app.profile.revision += 1
		app.run_critical = true
	}
}

app_begin_new_run :: proc(app: ^App, seed: u64, archetype: Archetype_Id) {
	if app == nil do return
	run_destroy(&app.run)
	app.run = {}
	run_start(&app.run, seed, archetype, app.options.difficulty)
	app.run.run_id = profile_begin_run(&app.profile, seed)
	app.profile.revision += 1
	app.active_run_available = true
	app.active_run_damaged = false
	app.run_dirty = true
	app.run_dirty_serial += 1
	app.run_critical = true
	app.persistence_request = .Save_Checkpoint
}

title_action_enabled :: proc(app: ^App, action: Title_Action) -> bool {
	if action == .Resume do return app != nil && app.active_run_available
	return true
}

title_move_selection :: proc(app: ^App, delta: int) {
	if app == nil || delta == 0 do return
	direction := delta > 0 ? 1 : -1
	for _ in 0 ..< len(Title_Action) {
		app.title_index = ((app.title_index + direction) % len(Title_Action) + len(Title_Action)) % len(Title_Action)
		if title_action_enabled(app, Title_Action(app.title_index)) do return
	}
}

app_request_terminal :: proc(app: ^App, terminal: Run_Terminal_State) {
	if app == nil || app.run.terminal != .Active do return
	app.run.terminal = terminal
	app.run.finalization = .None
	if terminal==.Victory do app_unlock_hell(app)
	app.run_dirty = true
	app.run_dirty_serial += 1
	app.run_critical = true
	app.persistence_request = terminal == .Victory ? .Finalize_Victory : .Finalize_Death
}

app_mark_run_dirty :: proc(app: ^App, critical := false) {
	if app == nil || app.run.run_id == "" || app.run.terminal != .Active do return
	app.run_dirty = true
	app.run_dirty_serial += 1
	app.run_critical = app.run_critical || critical
}

// Returns true when the floor changed and the camera should snap to spawn.
app_apply :: proc(app: ^App, intent: Intent) -> (floor_changed: bool) {
	// UI feedback is an app-apply result, not persistent app state. Main consumes
	// it immediately after this reducer returns.
	app.ui_sfx_bank = {}
	app.ui_sfx_override = false
	app.ui_sfx_suppress = false

	// Release edges remain global across paused/modal screens so a cancellable
	// Big Hit can never become stuck merely because its key was released there.
	if intent.action1_released && (app.mode == .Playing || app.mode == .Paused ||
		app.mode == .Options || app.mode == .Controls) {
		_ = player_big_hit_release(&app.run.player, &app.run)
	}
	if intent.toggle_fullscreen && !ARCH_ROGUE_ANDROID {
		app.options.fullscreen = !app.options.fullscreen
		app_mark_options_changed(app, {Platform_Effect.Apply_Window})
	}
	if app.mode == .Playing && app.death_pending {
		if app.mouse_input_blocked && intent.mouse_released do app.mouse_input_blocked = false
		return false
	}

	switch app.mode {
	case .Title:
		if intent.back || intent.quit {
			app.quit_requested = true
			return false
		}
		if intent.menu_index_valid do app.title_index = clamp(intent.menu_index, 0, len(Title_Action)-1)
		if intent.menu_delta != 0 do title_move_selection(app, intent.menu_delta)
		if intent.confirm {
			action := Title_Action(app.title_index)
			if (app.profile_save_damaged||app.options_save_damaged)&&action!=.Quit {
				app.mode=.Recovery
				app.confirm_index=0
				return false
			}
			switch action {
			case .Resume:
				if app.active_run_available {
					app.persistence_request = .Resume
					app.persistence_return = .Title
					app.mode = .Save_Wait
				} else if app.active_run_damaged {
					app.mode = .Recovery
					app.confirm_index = 0
				}
			case .New_Run:
				if app.active_run_damaged {
					app.mode=.Recovery
					app.confirm_index=0
				} else if app.active_run_available {
					app.mode = .Abandon_Confirm
					app.confirm_index = 0
				} else {
					app.mode = .Select
				}
			case .Chronicle:
				app.mode = .Chronicle
				app.chronicle.selected = 0
				app.chronicle.scroll = 0
			case .Options: app_enter_options(app, .Title)
			case .Quit: app.quit_requested = true
			}
		}
	case .Select:
		if intent.back {
			app.mode = .Title
			return false
		}
		n := len(Archetype_Id)
		if intent.menu_index_valid do app.select_index = clamp(intent.menu_index, 0, n - 1)
		app.select_index = ((app.select_index + intent.menu_delta + intent.menu_horizontal) % n + n) % n
		if intent.confirm {
			app_begin_new_run(app, app.seed, Archetype_Id(app.select_index))
			sfx_emit(&app.run, .Run_Start)
			app.ui_sfx_suppress = true
			app_reset_run_ui(app)
			app.mouse_input_blocked = intent.pointer_confirm
			app.mode = .Playing
			app_clear_play_input(app)
			_ = app_story_process_requests(app,include_omen=true)
			return true
		}
	case .Paused:
		if intent.back {
			app.mode = .Playing
			app_clear_play_input(app)
			return false
		}
		if intent.menu_index_valid do app.pause_index = clamp(intent.menu_index, 0, len(Pause_Action)-1)
		app.pause_index = ((app.pause_index + intent.menu_delta) % len(Pause_Action) + len(Pause_Action)) % len(Pause_Action)
		if intent.confirm {
			switch Pause_Action(app.pause_index) {
			case .Resume:
				app.mode = .Playing
				app.mouse_input_blocked = intent.pointer_confirm
				app_clear_play_input(app)
			case .Options: app_enter_options(app, .Paused)
			case .Save_Return:
				app.persistence_request = .Save_Return_Title
				app.persistence_return = .Paused
				app.mode = .Save_Wait
				app_clear_play_input(app)
			case .Quit:
				app.persistence_request = .Save_Quit
				app.persistence_return = .Paused
				app.mode = .Save_Wait
				app_clear_play_input(app)
			}
		}
	case .Options:
		if intent.back {
			app_leave_options(app)
			return false
		}
		if intent.menu_index_valid do app.options_index = clamp(intent.menu_index, 0, 10)
		app.options_index = ((app.options_index + intent.menu_delta) % 11 + 11) % 11
		direction := intent.menu_horizontal
		if direction == 0 && intent.confirm do direction = 1
		if direction != 0 {
			switch app.options_index {
			case 0:
				if !ARCH_ROGUE_ANDROID {
					app.options.fullscreen = !app.options.fullscreen
					app_mark_options_changed(app, {Platform_Effect.Apply_Window})
				}
			case 1:
				options_cycle_frame_rate_cap(&app.options, direction)
				app_mark_options_changed(app, {Platform_Effect.Apply_FPS})
			case 2:
				options_cycle_view_zoom(&app.options, direction)
				app_mark_options_changed(app, {Platform_Effect.Apply_Zoom})
			case 3:
				options_cycle_difficulty(&app.options, direction, app.profile.hell_unlocked)
				app_mark_options_changed(app)
			case 4:
				app.mode = .Controls
				app.controls_index = 0
				app.controls_capture = false
				app.controls_status = ""
			case 5:
				_ = player_big_hit_release(&app.run.player, &app.run)
				app.options.controller_enabled = !app.options.controller_enabled
				app_mark_options_changed(app)
			case 6:
				options_cycle_sfx_volume(&app.options, direction)
				app_mark_options_changed(app, {Platform_Effect.Apply_Audio})
			case 7:
				options_cycle_music_volume(&app.options, direction)
				app_mark_options_changed(app)
			case 8:
				app.options.lighting_enabled = !app.options.lighting_enabled
				app_mark_options_changed(app)
			case 9:
				app.options.mist_enabled = !app.options.mist_enabled
				app_mark_options_changed(app)
			case 10: app_leave_options(app)
			}
		}
	case .Controls:
		if app.controls_capture {
			if intent.back {
				app.controls_capture = false
				app.controls_status = "Mapping cancelled"
				return false
			}
			command := CONTROLLER_REMAPPABLE_COMMANDS[app.controls_index]
			result: Controller_Remap_Result
			has_input := false
			if intent.remap_button_valid {
				result = controller_remap_button(&app.options.gamepad_mapping, intent.remap_button, command)
				has_input = true
			} else if intent.remap_trigger_valid {
				result = controller_remap_trigger(&app.options.gamepad_mapping, intent.remap_trigger, command)
				has_input = true
			}
			if has_input {
				if result == .Applied {
					_ = player_big_hit_release(&app.run.player, &app.run)
					app.controls_capture = false
					app.controls_status = "Binding saved"
					app_mark_options_changed(app)
				} else if result == .Rejected_Fixed_Input {
					app.controls_status = "D-pad navigation is fixed"
				} else {
					app.controls_status = "That input cannot be assigned"
				}
			}
			return false
		}
		if intent.back {
			app.mode = .Options
			return false
		}
		if intent.menu_index_valid do app.controls_index = clamp(intent.menu_index, 0, len(CONTROLLER_REMAPPABLE_COMMANDS)-1)
		count := len(CONTROLLER_REMAPPABLE_COMMANDS)
		app.controls_index = ((app.controls_index + intent.menu_delta + intent.menu_horizontal) % count + count) % count
		if intent.confirm {
			app.controls_capture = true
			app.controls_status = "Press a controller button or trigger"
		}
	case .Playing:
		if app.mouse_input_blocked && intent.mouse_released do app.mouse_input_blocked = false
		story_request_processed := app_story_process_requests(app)
		if app_play_modal_open(app) {
			app.mobile_utility_open = false
			app_story_reduce_modal(app,intent)
			if intent.confirm || intent.pointer_confirm do app_mark_run_dirty(app,critical=true)
			if app.run.victory {
				app.mode = .Victory
				app_request_terminal(app, .Victory)
				app_clear_play_input(app)
			}
			return false
		}
		if story_request_processed {
			app.mobile_utility_open = false
			return false
		}
		interaction_available := player_interaction_available(&app.run)
		if interaction_available do app.mobile_utility_open = false
		if intent.toggle_mobile_utility && !interaction_available {
			app.mobile_utility_open = !app.mobile_utility_open
		}
		if intent.toggle_minimap {
			app.minimap_visible = !app.minimap_visible
			app.options.minimap_visible = app.minimap_visible
			app_mark_options_changed(app)
		}
		if intent.minimap_zoom != 0 {
			app.minimap_zoom = minimap_zoom_apply(app.minimap_zoom, intent.minimap_zoom)
		}

		if intent.toggle_inventory {
			app.mobile_utility_open = false
			app.inventory_open = !app.inventory_open
			app.character_open = false
			app.shop_open = false
			inventory_clamp_selection(app)
			app_clear_play_input(app)
			return false
		}
		if intent.open_character {
			app.mobile_utility_open = false
			app.character_open = !app.character_open
			app.inventory_open = false
			app.shop_open = false
			app_clear_play_input(app)
			return false
		}
		if intent.open_disciplines && app.run.player.memory_tokens > 0 {
			app.mobile_utility_open = false
			app.character_open = true
			app.character_tab = .Disciplines
			app.inventory_open = false
			app.shop_open = false
			app_clear_play_input(app)
			return false
		}

		if app.inventory_open {
			app_clear_play_input(app)
			if intent.back {
				app.inventory_open = false
				return false
			}
			if n := app.run.player.bag_count; n > 0 {
				if intent.menu_index_valid do app.inv_index = intent.menu_index
				app.inv_index += intent.menu_delta
				inventory_clamp_selection(app)
				if intent.confirm {
					item_kind := app.run.player.bag[app.inv_index].kind
					equip_attempt := item_kind == .Weapon || item_kind == .Armor
					equip_allowed := (item_kind == .Weapon && (!app.run.player.has_weapon || !app.run.player.weapon.cursed)) ||
						(item_kind == .Armor && (!app.run.player.has_armor || !app.run.player.armor.cursed))
					equip_from_bag(&app.run.player, app.inv_index)
					if equip_attempt {
						app.ui_sfx_bank = equip_allowed ? .Ui_Equip : .Ui_Reject
						app.ui_sfx_override = true
					}
					app_mark_run_dirty(app)
					inventory_clamp_selection(app)
				}
				if intent.inv_drop {
					if drop_from_bag(&app.run, app.inv_index) do app_mark_run_dirty(app)
					inventory_clamp_selection(app)
				}
			}
			if intent.inv_sort_valid do app.inv_sort_mode = intent.inv_sort_mode
			inv_cycle_sort := intent.inv_cycle_sort
			if intent.tab do inv_cycle_sort += 1
			if inv_cycle_sort != 0 {
				count := len(Inventory_Sort_Mode)
				app.inv_sort_mode = Inventory_Sort_Mode(((int(app.inv_sort_mode) + inv_cycle_sort) % count + count) % count)
			}
			if intent.inv_sort || intent.inv_sort_valid || inv_cycle_sort != 0 {
				sort_bag(&app.run.player, app.inv_sort_mode)
				inventory_clamp_selection(app)
			}
			return false
		}

		if app.character_open {
			app_clear_play_input(app)
			if intent.back || intent.open_character {
				app.character_open = false
				return false
			}
			if intent.tab {
				app.character_tab = app.character_tab == .Overview ? .Disciplines : .Overview
			}
			if intent.character_tab_valid {
				app.character_tab = intent.character_tab
			}
			if app.character_tab == .Overview && intent.menu_horizontal != 0 {
				app.character_tab = .Disciplines
				return false
			}
			if app.character_tab == .Disciplines {
				if intent.menu_horizontal != 0 {
					app.discipline_column = clamp(app.discipline_column + intent.menu_horizontal, 0, DISCIPLINE_PATHS_PER_ARCHETYPE - 1)
				}
				if intent.menu_delta != 0 {
					app.discipline_degree = clamp(app.discipline_degree + intent.menu_delta, 0, DISCIPLINE_DEGREES - 1)
				}
				if intent.menu_index_valid {
					app.discipline_column = clamp(intent.menu_index % DISCIPLINE_PATHS_PER_ARCHETYPE, 0, DISCIPLINE_PATHS_PER_ARCHETYPE - 1)
					app.discipline_degree = clamp(intent.menu_index / DISCIPLINE_PATHS_PER_ARCHETYPE, 0, DISCIPLINE_DEGREES - 1)
				}
				if intent.confirm {
					if id, found := character_selected_discipline(app); found {
						if run_try_acquire_discipline(&app.run, id)==.Acquired do app_mark_run_dirty(app,critical=true)
					}
				}
			}
			return false
		}

		if app.shop_open {
			app_clear_play_input(app)
			if intent.back {
				app.shop_open = false
				return false
			}
			if intent.tab || intent.menu_horizontal != 0 {
				app.shop_mode = app.shop_mode == .Buy ? .Sell : .Buy
				app.shop_index = 0
				app.shop_scroll = 0
			}
			if n := shop_entry_count(app); n > 0 {
				if intent.menu_index_valid do app.shop_index = intent.menu_index
				app.shop_index = ((app.shop_index + intent.menu_delta) % n + n) % n
				shop_clamp_selection(app)
				if intent.confirm {
					transaction: Shop_Transaction
					if app.shop_mode == .Buy {
						transaction = shop_buy(&app.run.shopkeeper, &app.run.player, app.shop_index)
					} else {
						transaction = shop_sell_bag(&app.run.shopkeeper, &app.run.player, app.shop_index)
					}
					if transaction.result == .Success {
						app_mark_run_dirty(app,critical=true)
						app.ui_sfx_bank = .Ui_Purchase
						app.ui_sfx_override = true
						sfx_emit(&app.run, .Coin_Pickup_Light)
						append(&app.run.numbers, Damage_Number{pos=app.run.player.pos,kind=.Text,text=app.shop_mode == .Buy ? "Bought" : "Sold"})
					} else {
						app.ui_sfx_bank = .Ui_Reject
						app.ui_sfx_override = true
						if transaction.result == .Insufficient_Gold {
							append(&app.run.numbers, Damage_Number{pos=app.run.player.pos,kind=.Text,text="Need more gold"})
						} else if transaction.result == .Inventory_Full {
							append(&app.run.numbers, Damage_Number{pos=app.run.player.pos,kind=.Text,text="Inventory full"})
						}
					}
					shop_clamp_selection(app)
				}
			} else if intent.confirm {
				app.ui_sfx_bank = .Ui_Reject
				app.ui_sfx_override = true
			}
			return false
		}

		if intent.back || intent.quit {
			app.mobile_utility_open = false
			app.mode = .Paused
			app.pause_index = 0
			app_clear_play_input(app)
			return false
		}
		app.move_input = intent.move
		app.aim_input = intent.aim
		app.aim_live = intent.aim_live
		app.mouse_walk = !app.mouse_input_blocked && intent.mouse_walk && intent.move == {}
		app.mouse_target = intent.mouse_target
		if !app.mouse_input_blocked && intent.mouse_press {
			app.mouse_press_pending = true
			app.mouse_press_aim = intent.mouse_press_aim
		}
		action_aim := intent.aim
		if !aim_outside_dead_zone(action_aim) do action_aim = app.run.player.facing
		if intent.actions[0] do _ = player_big_hit_begin(&app.run, action_aim)
		if intent.actions[1] do _ = player_cast_bolt(&app.run, action_aim)
		if intent.actions[2] do _ = player_cast_class_skill(&app.run, action_aim)
		if intent.actions[3] do _ = player_dash(&app.run, action_aim)
		if intent.use_heal {player_use_potion(&app.run, .Heal_Potion);app_mark_run_dirty(app)}
		if intent.use_mana {player_use_potion(&app.run, .Mana_Potion);app_mark_run_dirty(app)}
		if intent.interact {
			app.mobile_utility_open = false
			if story_handle_final_stairs_request(&app.run) {
				app_clear_play_input(app)
				return false
			}
			floor_changed = player_interact(&app.run)
			// Web persistence encodes synchronously into the IndexedDB mirror. Only a
			// floor transition needs an immediate checkpoint; ordinary and no-op
			// interactions use the existing quiet/deadline autosave debounce.
			app_mark_run_dirty(app,critical=floor_changed)
			if floor_changed do _ = app_story_process_requests(app,include_omen=true)
			if app.run.shop_requested {
				app.run.shop_requested = false
				app.mobile_utility_open = false
				app.shop_open = true
				app.shop_mode = .Buy
				app.shop_index = 0
				app.shop_scroll = 0
				app_clear_play_input(app)
			}
		if app.run.victory {
			app.mode = .Victory
			app_request_terminal(app, .Victory)
			app_clear_play_input(app)
		}
			return floor_changed
		}
		if intent.descend {
			run_descend(&app.run)
			app_mark_run_dirty(app,critical=true)
			_ = app_story_process_requests(app,include_omen=true)
			return true
		}
		if intent.new_run {
			app_begin_new_run(app, derive_seed(app.run.seed, app.tick ~ 0xC0FFEE), app.run.player.archetype)
			app_reset_run_ui(app)
			_ = app_story_process_requests(app,include_omen=true)
			return true
		}
		if intent.boss_floor {
			run_regenerate_floor(&app.run, boss_arena = true)
			app_mark_run_dirty(app,critical=true)
			return true
		}
	case .Chronicle:
		if intent.back {
			app.mode = .Title
			return false
		}
		if intent.chronicle_focus_valid do app.chronicle.focus = intent.chronicle_focus
		if intent.tab {
			app.chronicle.focus = Chronicle_Focus((int(app.chronicle.focus)+1)%len(Chronicle_Focus))
		}
		if intent.menu_horizontal != 0 {
			direction := intent.menu_horizontal > 0 ? 1 : -1
			switch app.chronicle.focus {
			case .Outcome:
				count := len(Chronicle_Outcome_Filter)
				app.chronicle.outcome = Chronicle_Outcome_Filter(((int(app.chronicle.outcome)+direction)%count+count)%count)
			case .Archetype:
				count := len(Archetype_Id)+1
				app.chronicle.archetype_filter = ((app.chronicle.archetype_filter+1+direction)%count+count)%count-1
			case .Difficulty:
				count := len(Difficulty_Id)+1
				app.chronicle.difficulty_filter = ((app.chronicle.difficulty_filter+1+direction)%count+count)%count-1
			case .Timeline:
			}
			app.chronicle.selected = 0
			app.chronicle.scroll = 0
		}
		count := chronicle_filtered_count(&app.profile, &app.chronicle)
		if intent.menu_index_valid do app.chronicle.selected = clamp(intent.menu_index, 0, max(0,count-1))
		if intent.menu_delta != 0 {
			app.chronicle.focus = .Timeline
			app.chronicle.selected = clamp(app.chronicle.selected+intent.menu_delta,0,max(0,count-1))
		}
		app.chronicle.scroll = min(app.chronicle.scroll,app.chronicle.selected)
		if app.chronicle.selected >= app.chronicle.scroll+6 do app.chronicle.scroll=app.chronicle.selected-5
	case .Abandon_Confirm:
		if intent.back {
			app.mode = .Title
			return false
		}
		if intent.menu_index_valid do app.confirm_index=clamp(intent.menu_index,0,1)
		app.confirm_index=((app.confirm_index+intent.menu_delta)%2+2)%2
		if intent.confirm {
			if app.confirm_index==0 {
				app.mode=.Title
			} else {
				app.persistence_request=.Abandon
				app.persistence_return=.Title
				app.mode=.Save_Wait
			}
		}
	case .Recovery:
		if intent.back {
			app.mode=.Title
			return false
		}
		if intent.menu_index_valid do app.confirm_index=clamp(intent.menu_index,0,2)
		app.confirm_index=((app.confirm_index+intent.menu_delta)%3+3)%3
		if intent.confirm {
			switch app.confirm_index {
			case 0:
				app.persistence_request=(app.profile_save_damaged||app.options_save_damaged)?.Recover_Documents:.Recover_Run
				app.persistence_return=.Recovery
				app.mode=.Save_Wait
			case 1:
				app.persistence_request=(app.profile_save_damaged||app.options_save_damaged)?.Quarantine_Documents:.Quarantine_Run
				app.persistence_return=.Recovery
				app.mode=.Save_Wait
			case 2: app.mode=.Title
			}
		}
	case .Save_Wait:
		// The platform coordinator owns completion; simulation remains frozen.
	case .Save_Error:
		if intent.back {
			app.persistence_request=.None
			app.mode=app.persistence_return
			return false
		}
		if intent.menu_index_valid do app.confirm_index=clamp(intent.menu_index,0,2)
		app.confirm_index=((app.confirm_index+intent.menu_delta)%3+3)%3
		if intent.confirm {
			switch app.confirm_index {
			case 0:
				app.persistence_request=app.failed_request
				app.mode=.Save_Wait
			case 1:
				app.persistence_request=.None
				app.mode=app.persistence_return
			case 2:
				request:=app.failed_request
				app.persistence_request=.None
				if request==.Save_Quit do app.quit_requested=true
				else do app.mode=.Title
			}
		}
	case .Resume_Veil:
		if intent.confirm || intent.back {
			app.mode=.Playing
			app.mouse_input_blocked=intent.pointer_confirm
			app_clear_play_input(app)
		}
	case .Dead:
		if intent.back || intent.confirm do app.mode = .Title
	case .Victory:
		if intent.back || intent.confirm do app.mode = .Title
	}
	return false
}

run_destroy :: proc(run: ^Run, allocator := context.allocator) {
	if run == nil do return
	story_run_destroy(run, allocator)
	delete(run.run_id, allocator)
	delete(run.started_at_utc, allocator)
	delete(run.ended_at_utc, allocator)
	for value in run.save_owned_strings do delete(value, allocator)
	delete(run.save_owned_strings)
	delete(run.enemies)
	delete(run.projectiles)
	delete(run.familiars)
	delete(run.bells)
	delete(run.numbers)
	delete(run.ground_items)
	delete(run.sfx)
	delete(run.feel)
	delete(run.sealed)
	delete(run.traps)
	delete(run.shrines)
	delete(run.secrets)
	run.sealed = nil
	run.enemies = nil
	run.sfx = nil
	run.feel = nil
	run.projectiles = nil
	run.familiars = nil
	run.bells = nil
	run.numbers = nil
	run.ground_items = nil
	run.traps = nil
	run.shrines = nil
	run.secrets = nil
	run.run_id = ""
	run.started_at_utc = ""
	run.ended_at_utc = ""
	run.save_owned_strings = nil
}

run_start :: proc(run: ^Run, seed: u64, archetype: Archetype_Id, difficulty := DEFAULT_DIFFICULTY) {
	run.seed = seed
	run.revision = 0
	run.active_ticks = 0
	run.terminal = .Active
	run.finalization = .None
	run.started_at_utc = ""
	run.ended_at_utc = ""
	run.depth = 1
	run.difficulty = difficulty_normalize(difficulty, difficulty == .Hell)
	run.victory = false
	run.tyrant_dead = false
	run.kills = 0
	run.next_enemy_id = 0
	run.next_familiar_id = 0
	run.next_save_entity_id = 0
	run.storm_cast_counter = 0
	run.bars_visited = 0
	run.bars_toasted = 0
	run.challenge_rooms_cleared = 0
	run.traps_triggered = 0
	run.shrines_used = 0
	run.secrets_opened = 0
	run.notable_count = 0
	run.visited_themes = {}
	run.defeated_bosses = {}
	run.last_damage_source = ""
	run.critical_save_requested = false
	run.wall_face_timer = 0
	run.wall_touches = 0
	// The whole descent is authored before the first floor exists: the floor
	// generator and populater read theme/darkness/boss/encounter from the plan.
	run.plan, run.modifier = generate_run_plan(seed)
	story_run_initialize(run,archetype)
	// Keep floor_epoch monotonic when this Run storage is reused for New Run;
	// renderer caches must never mistake a new floor for the previous one.
	run_generate_floor(run)
	run.player = player_spawn(run, archetype)
	refresh_visibility(run)
}

run_descend :: proc(run: ^Run) {
	_ = story_resolve_current_unanswered(run)
	run.depth += 1
	run_regenerate_floor(run, boss_arena = false)
}

run_regenerate_floor :: proc(run: ^Run, boss_arena: bool) {
	was_charging := bighit_charging(&run.player)
	run_generate_floor(run, boss_arena)
	if was_charging do sfx_stop_bank(run, .Big_Hit_Charge)
	run.player.pos = run_spawn_point(run)
	run.player.prev_pos = run.player.pos
	story_refresh_relic_guidance(run)
	// Pygame treats a floor transition as a clean combat boundary: action
	// recoveries never leak downstairs, an in-flight Big Hit is cancelled, and
	// the player receives a quarter-pool breather.  Persistent statuses and the
	// potion cooldown intentionally survive, matching run_flow.py.
	player := &run.player
	player.melee_timer = 0
	player.bolt_timer = 0
	player.dash_timer = 0
	player.class_skill_timer = 0
	player.time_skip_timer = 0
	player.bighit_timer = 0
	player.bighit_charge = 0
	player.swing_timer = 0
	player.melee_commit_timer = 0
	run.hitstop_ticks = 0
	player_clear_visual_action(player)
	player.hit_flash = 0
	player.hit_flash_duration = 0
	run.player.moving = false
	run.player.stamina = min(f32(player.max_stamina), player.stamina + f32(player.max_stamina) * 0.25)
	run.player.mana = min(f32(player.max_mana), player.mana + f32(player.max_mana) * 0.25)
	refresh_visibility(run)
	// Arriving at the gate with every generated Bar toasted summons the
	// immortal dancer (run_flow.py:1002-1004). After the player teleport so
	// her spawn search runs against valid tiles.
	if run.depth >= DUNGEON_DEPTH do _ = maybe_summon_bar_dancer(run)
}

// Each floor gets its own derived RNG stream, so floor N is identical for a
// given run seed no matter what happened on floors above it.
run_generate_floor :: proc(run: ^Run, boss_arena := false) {
	run.floor_epoch += 1
	if run.floor_epoch == 0 do run.floor_epoch = 1
	clear_feel_events(run)
	plan := run_floor_plan(run)
	story_prepare_floor(run)
	rng := rng_make(derive_seed(run.seed, u64(run.depth)))
	arena := boss_arena || plan.has_boss
	story_floor := run.story_runtime.initialized && 1 <= run.depth && run.depth <= STORY_BEAT_COUNT
	dungeon, ok := dungeon_generate(&rng, {
		boss_arena = arena,
		story_rooms = story_floor,
		quest_requested = story_floor,
		force_hall = story_floor && story_should_force_hall(run),
	})
	assert(ok, "dungeon generation exhausted retries")
	run.dungeon = dungeon
	run.explored = {}
	run.visible = {}
	clear(&run.sealed)
	run.boss_engaged = false
	// Theme and darkness were rolled into the plan at run start (from the same
	// per-depth streams as before MX.4, so recorded seeds replay identically).
	run.dark_floor = plan.dark
	run.theme_index = plan.theme_index
	if 0 <= run.theme_index && run.theme_index < len(run.visited_themes) {
		run.visited_themes[run.theme_index] = true
	}
	populate_floor(run)
	story_populate_floor(run)
	run.has_shopkeeper = false
	run.shopkeeper = {}
	run.refuge = {} // per-floor refuge state; the toast *ledger* lives on Run
	run.shop_requested = false
	if special, found := special_room_for_kind(&run.dungeon, .Shop); found {
		room := run.dungeon.rooms_buf[special.room_index]
		run.shopkeeper = shopkeeper_make(run.seed, run.depth, room, special.room_index)
		run.has_shopkeeper = true
	}
	room_npc_initialize_ambient_residents(run)
	// Bar pilgrimage ledger: counted where a floor is created, exactly like
	// run_flow.py _note_bar_room_for_run, so no floor can double-count.
	if _, found := special_room_for_kind(&run.dungeon, .Bar); found {
		run.bars_visited += 1
	}
	// Non-blocking arrival treatment: a brief dark fade plus the depth/theme
	// title card (drawn by the renderer while arrival_timer runs). Pygame's
	// loading screen only existed because its synchronous prewarm was slow.
	run.arrival_timer = ARRIVAL_TITLE_SECONDS
	feel_emit(run, .Screen_Flash, run_spawn_point(run), {10, 9, 14, 255}, ARRIVAL_FADE_SECONDS, 0)
	if run.dark_floor {
		append(&run.numbers, Damage_Number{pos = run_spawn_point(run), kind = .Text, text = "The darkness thickens..."})
	}
}

run_barrel_tile :: proc(run: ^Run) -> (tile: [2]int, found: bool) {
	if run == nil do return {}, false
	layout := bar_furnishing_layout(&run.dungeon)
	if layout.count > 0 do return layout.tiles[0],true
	return {}, false
}

// Spawn-room center in tile space; the player starts here on every floor.
run_spawn_point :: proc(run: ^Run) -> Vec2 {
	center := room_center(run.dungeon.rooms_buf[0])
	return {f32(center.x) + 0.5, f32(center.y) + 0.5}
}
