package archrogue

// Co-op gameplay synchronization (MULTIPLAYER.md sections 5-6). The host
// simulates both seats; the joiner sends fixed-step movement commands plus
// ordered action edges, predicts only its own movement, and adopts
// authoritative snapshots. Raylib-free: the platform supplies monotonic time.

import "core:encoding/base64"
import "core:encoding/json"
import "core:fmt"
import "core:math"
import "core:math/linalg"
import "core:strings"
import np "net_protocol"

COOP_CMD_RING          :: 256
COOP_HOST_QUEUE_MAX    :: 30  // hard cap on buffered guest steps (500 ms)
COOP_HOST_ACTIONS_MAX  :: 32
COOP_SNAPSHOT_MS       :: 33  // 30 Hz
COOP_SLOW_CHECK_EVERY  :: 5   // snapshots between slow-section hash checks
COOP_SNAP_DISTANCE     :: 3.0 // tiles: larger corrections snap instead of easing
COOP_SMOOTH_MAX        :: f32(0.75) // tiles of accumulated error the guest may hide by easing
COOP_OFFSET_DECAY_PER_TICK :: f32(0.85) // ~70 ms half-life at 60 Hz

Coop_Role :: enum u8 {
	None,
	Host,
	Join,
}

Coop_State :: struct {
	role:      Coop_Role,
	session:   Net_Session,
	strings:   map[string]string, // intern pool for replicated text
	result_id: u64,
	outcome:   Run_Terminal_State,
	ended:     bool,
	floor_changed: bool, // presentation must recenter after a remote descent

	// ---- host
	h_cmds:            [dynamic]Coop_Command,
	h_actions:         [dynamic]Coop_Action,
	h_hold:            int,
	h_starved:         int, // diagnostics: ticks without a guest step
	h_refilling:       bool,
	h_trimmed:         int, // diagnostics: steps dropped to bound latency
	h_resolved:        u32, // contiguous resolved joiner command step
	h_seen_seq:        u32,
	h_seen_action:     u32,
	h_actions_resolved: u32,
	h_snapshot_seq:    u64,
	h_last_snapshot_ms: i64,
	h_checkpoint_id:   u64,
	h_checkpoint_epoch: u32,
	h_need_checkpoint: bool,
	h_joiner_synced:   bool,
	h_joiner_pause:    Coop_Pause,
	h_sfx:             [dynamic]Sfx_Event,
	h_events:          [dynamic]Coop_Joiner_Event,
	h_slow_hash:       [Coop_Slow_Section]u64,
	h_slow_counter:    int,
	h_slow_force:      bit_set[Coop_Slow_Section],

	// ---- joiner
	j_have_world:      bool,
	j_epoch:           u32,
	j_ckpt_id:         u64,
	j_ckpt_count:      int,
	j_ckpt_total:      int,
	j_ckpt_epoch:      u32,
	j_ckpt_sum:        string,
	j_ckpt_parts:      [dynamic]string,
	j_last_snapshot:   u64,
	j_cmd_seq:         u32,
	j_ring:            [COOP_CMD_RING]Coop_Command,
	j_unsent_from:     u32,
	j_action_id:       u32,
	j_actions:         [dynamic]Coop_Action,
	j_pause:           Coop_Pause, // host-reported shared pause
	j_local_pause:     Coop_Pause, // this joiner's own shop
	j_send_counter:    int,
	j_interp:          Coop_Interp_State,
	j_shop_requested:  bool,
	j_visual_hold:     int, // ticks during which a predicted clip outranks host visuals
	j_visual_offset:   Vec2, // render-only reconciliation offset, decays over time
	j_offset_ms:       i64,
	j_pending_melee:   bool, // action edges waiting for the next command step
	j_pending_melee_aim: Vec2,
	j_pending_dash:    bool,
	j_pending_dash_aim: Vec2,
	j_cmd_sent_ms:     [COOP_CMD_RING]i64,
	// Diagnostics for the F3 co-op overlay.
	j_last_correction: f32,
	j_max_correction:  f32,
	j_ack_latency_ms:  i64,
	j_snapshot_bytes:  int,
	j_last_snapshot_ms: i64,
	j_checkpoints_adopted: int,
	j_snapshots_applied:  int, // diagnostics
	j_snapshots_rejected: int,
}

coop_active :: proc(app: ^App) -> bool {
	return app.coop.role != .None
}

coop_is_joiner :: proc(app: ^App) -> bool {
	return app.coop.role == .Join
}

coop_is_host :: proc(app: ^App) -> bool {
	return app.coop.role == .Host
}

coop_destroy :: proc(c: ^Coop_State) {
	net_session_destroy(&c.session)
	for key, value in c.strings {
		delete(key)
		_ = value
	}
	delete(c.strings)
	delete(c.h_cmds)
	delete(c.h_actions)
	delete(c.h_sfx)
	delete(c.h_events)
	coop_reset_checkpoint(c)
	delete(c.j_ckpt_parts)
	delete(c.j_actions)
	coop_interp_destroy(&c.j_interp)
	c^ = {}
}

coop_intern :: proc(c: ^Coop_State, s: string) -> string {
	if s == "" do return ""
	if existing, found := c.strings[s]; found do return existing
	owned := strings.clone(s)
	c.strings[owned] = owned
	return owned
}

@(private = "file")
coop_reset_checkpoint :: proc(c: ^Coop_State) {
	for part in c.j_ckpt_parts do delete(part)
	clear(&c.j_ckpt_parts)
	delete(c.j_ckpt_sum)
	c.j_ckpt_sum = ""
	c.j_ckpt_id = 0
	c.j_ckpt_count = 0
}

// The co-op pause state the shared dungeon is in right now, as seen by host.
coop_host_pause :: proc(app: ^App) -> Coop_Pause {
	pause: Coop_Pause
	if app.inventory_open || app.character_open || app.shop_open || app.mode != .Playing do pause += {.Host_Menu}
	if app_play_modal_open(app) || app_story_world_minigame_active(app) do pause += {.Host_Story}
	pause += app.coop.h_joiner_pause
	if !app.coop.session.partner_connected || !app.coop.h_joiner_synced do pause += {.Partner_Lost}
	return pause
}

// Whether the shared simulation advances this tick (host side). Host menus
// already stop app_tick before the sim; this adds partner-owned reasons.
coop_host_sim_blocked :: proc(app: ^App) -> bool {
	c := &app.coop
	return .Joiner_Shop in c.h_joiner_pause || !c.session.partner_connected || !c.h_joiner_synced
}

// ------------------------------------------------------------------- start --

// Both roles enter play from the relay's start. The host builds the world and
// owes the joiner a checkpoint; the joiner waits for that checkpoint.
coop_begin_run :: proc(app: ^App) {
	c := &app.coop
	start := &c.session.start
	app_story_runtime_reset(app)
	run_destroy(&app.run)
	app.run = {}
	app_reset_run_ui(app)
	app.death_pending = false
	c.ended = false
	c.result_id = 0
	if c.role == .Host {
		run_start_coop(&app.run, start.seed, start.archetypes, start.difficulty, start.story)
		app.run.local_slot = HOST_SLOT
		c.h_need_checkpoint = true
		c.h_joiner_synced = false
		clear(&c.h_cmds)
		clear(&c.h_actions)
		c.h_resolved = 0
		c.h_seen_seq = 0
		c.h_seen_action = 0
		c.h_actions_resolved = 0
		c.h_slow_force = ~bit_set[Coop_Slow_Section]{}
		app.mode = .Playing
	} else {
		c.j_have_world = false
		c.j_cmd_seq = 0
		c.j_unsent_from = 1
		app.mode = .Coop_Wait
	}
	app_clear_play_input(app)
	app.mouse_input_blocked = true
}

// --------------------------------------------------------------- per frame --

// Pump the relay connection and route gameplay traffic. Called once per
// rendered frame before input is applied.
coop_frame :: proc(app: ^App, now_ms: i64) {
	c := &app.coop
	if c.role == .None do return
	s := &c.session
	net_session_update(s, now_ms)
	for event in s.events {
		switch event {
		case .Started:
			coop_begin_run(app)
		case .Partner_Rejoined:
			// A reclaimed joiner needs a fresh, current baseline.
			if c.role == .Host && s.phase == .Active {
				c.h_need_checkpoint = true
				c.h_joiner_synced = false
			}
		case .Reconnected:
			if c.role == .Join && s.phase == .Active {
				// The host sends a fresh baseline on its partner_rejoined; hold
				// input until it lands rather than request a duplicate.
				c.j_have_world = false
				if app.mode == .Playing do app.mode = .Coop_Wait
			} else if c.role == .Host && s.phase == .Active {
				c.h_need_checkpoint = true
				c.h_joiner_synced = false
			}
		case .Partner_Disconnected:
			if c.role == .Host do c.h_joiner_synced = false
		case .Welcomed, .Lobby_Changed, .Partner_Left, .Connection_Lost, .Failed:
		}
	}
	for {
		data, ok := net_session_take_inbox(s)
		if !ok do break
		coop_handle_message(app, data)
		delete(data)
	}
	if c.role == .Host && s.phase == .Active && !c.ended {
		if c.h_need_checkpoint && s.partner_connected do coop_host_send_checkpoint(app)
		if now_ms - c.h_last_snapshot_ms >= COOP_SNAPSHOT_MS {
			c.h_last_snapshot_ms = now_ms
			coop_host_send_snapshot(app)
		}
	}
}

coop_handle_message :: proc(app: ^App, data: []byte) {
	c := &app.coop
	t, _, _ := np.peek_type(data)
	#partial switch t {
	case .Intent:
		if c.role == .Host do coop_host_receive_intent(app, data)
	case .Checkpoint_Ack:
		if c.role != .Host do return
		obj, root, ok := np.json_parse_object(data, context.temp_allocator)
		defer json.destroy_value(root, context.temp_allocator)
		if !ok do return
		if id, id_ok := np.read_u64s(obj, "id"); id_ok && id == c.h_checkpoint_id {
			c.h_joiner_synced = true
			// Fresh baseline: stale commands from before it are void.
			clear(&c.h_cmds)
			clear(&c.h_actions)
		}
	case .Sync_Request:
		if c.role == .Host {
			c.h_need_checkpoint = true
			c.h_joiner_synced = false
		}
	case .Checkpoint:
		if c.role == .Join do coop_joiner_receive_checkpoint(app, data)
	case .Snapshot:
		if c.role == .Join do coop_joiner_receive_snapshot(app, data)
	case .Run_Ended:
		if c.role == .Join do coop_joiner_receive_run_ended(app, data)
	}
}

// ==================================================================== host ==

@(private = "file")
coop_host_receive_intent :: proc(app: ^App, data: []byte) {
	c := &app.coop
	commands := make([dynamic]Coop_Command, 0, COOP_MAX_BATCH_COMMANDS, context.temp_allocator)
	actions := make([dynamic]Coop_Action, 0, COOP_MAX_BATCH_ACTIONS, context.temp_allocator)
	pause, ok := coop_decode_intent(data, &commands, &actions)
	if !ok do return
	c.h_joiner_pause = pause & {.Joiner_Shop}
	if !c.h_joiner_synced do return
	for cmd in commands {
		if cmd.seq <= c.h_seen_seq do continue // duplicate or already resolved
		c.h_seen_seq = cmd.seq
		append(&c.h_cmds, cmd)
	}
	// Hard cap on the backlog (a stalled host); steady trimming happens per
	// tick in coop_host_next_input. Skipped steps still advance the cursor.
	for len(c.h_cmds) > COOP_HOST_QUEUE_MAX {
		c.h_resolved = c.h_cmds[0].seq
		ordered_remove(&c.h_cmds, 0)
	}
	for action in actions {
		if action.id <= c.h_seen_action do continue
		c.h_seen_action = action.id
		if len(c.h_actions) >= COOP_HOST_ACTIONS_MAX do continue
		append(&c.h_actions, action)
	}
}

// One remote movement step per host tick, and every step exactly once. A step
// that has not arrived leaves the seat still this tick (input latency grows
// by one tick instead of the host guessing and later re-executing it); a
// backlog beyond COOP_HOST_QUEUE_TARGET is trimmed so latency stays bounded.
// Late steps never grant extra movement and nothing is applied twice.
COOP_HOST_QUEUE_TARGET :: 4 // ~67 ms of buffered steps absorbs normal jitter
COOP_HOST_REFILL       :: 2 // steps to rebuffer after the queue ran dry

coop_host_next_input :: proc(app: ^App) -> Player_Tick_Input {
	c := &app.coop
	run := &app.run
	slot := 1
	if len(c.h_cmds) > COOP_HOST_QUEUE_TARGET + 2 {
		// Trim one stale step per tick; the resolved cursor still covers it.
		c.h_resolved = c.h_cmds[0].seq
		c.h_trimmed += 1
		ordered_remove(&c.h_cmds, 0)
	}
	cmd: Coop_Command
	have := false
	// After running dry, refill a small jitter buffer before resuming so the
	// guest's seat moves evenly on the host's screen instead of stuttering.
	if c.h_refilling && len(c.h_cmds) >= COOP_HOST_REFILL do c.h_refilling = false
	if len(c.h_cmds) > 0 && !c.h_refilling {
		cmd = c.h_cmds[0]
		ordered_remove(&c.h_cmds, 0)
		c.h_resolved = cmd.seq
		have = true
		c.h_hold = 0
	} else {
		c.h_hold += 1 // starved: diagnostics only
		c.h_starved += 1
		if len(c.h_cmds) == 0 do c.h_refilling = true
	}
	// Action edges ordered at or before this step resolve first.
	limit := have ? cmd.seq : c.h_resolved
	for len(c.h_actions) > 0 && c.h_actions[0].at <= limit {
		action := c.h_actions[0]
		ordered_remove(&c.h_actions, 0)
		coop_host_apply_action(app, action)
		c.h_actions_resolved = action.id
	}
	if !have do return {max_move_step = -1}
	player := &run.players[slot]
	if cmd.move == {} && cmd.aim_live && player.hp > 0 && linalg.length(cmd.aim) > MOUSE_AIM_DEAD_ZONE {
		player.facing = linalg.normalize0(cmd.aim)
	}
	return {move = cmd.move, max_move_step = cmd.max_step, auto_melee = cmd.auto_melee}
}

@(private = "file")
coop_host_apply_action :: proc(app: ^App, a: Coop_Action) {
	c := &app.coop
	run := &app.run
	slot := 1
	player := &run.players[slot]
	aim := a.aim
	if linalg.length(aim) <= MOUSE_AIM_DEAD_ZONE do aim = player.facing
	if player.hp <= 0 && a.kind != .Big_Hit_Release do return
	switch a.kind {
	case .None:
	case .Melee:
		if enemy_in_melee_arc(run, slot, aim) do player_melee(run, slot, aim)
	case .Big_Hit_Begin:   _ = player_big_hit_begin(run, slot, aim)
	case .Big_Hit_Release: _ = player_big_hit_release(player, run)
	case .Bolt:            _ = player_cast_bolt(run, slot, aim)
	case .Class_Skill:     _ = player_cast_class_skill(run, slot, aim)
	case .Dash:            _ = player_dash(run, slot, aim)
	case .Potion_Heal:     player_use_potion(run, slot, .Heal_Potion)
	case .Potion_Mana:     player_use_potion(run, slot, .Mana_Potion)
	case .Interact:
		run.shop_requested = false
		if story_handle_final_stairs_request(run, slot) do break
		depth := run.depth
		changed := player_interact(run, slot)
		if run.shop_requested {
			// A remote trade opens the joiner's own shop, never the host's.
			run.shop_requested = false
			append(&c.h_events, Coop_Joiner_Event.Open_Shop)
		}
		if changed || run.depth != depth {
			c.floor_changed = true
			_ = app_story_process_requests(app, include_omen = true)
		}
	case .Equip:
		if coop_bag_index_valid(player, a.index, a.check) do equip_from_bag(player, int(a.index))
	case .Drop:
		if coop_bag_index_valid(player, a.index, a.check) do _ = drop_from_bag(run, slot, int(a.index))
	case .Sort:
		if a.arg >= 0 && int(a.arg) < len(Inventory_Sort_Mode) do sort_bag(player, Inventory_Sort_Mode(a.arg))
	case .Discipline:
		if a.arg >= 0 && int(a.arg) < len(Discipline_Id) do _ = run_try_acquire_discipline(run, slot, Discipline_Id(a.arg))
	case .Shop_Buy:
		if !player_near_shop(run, slot) || a.index < 0 || int(a.index) >= run.shopkeeper.stock_count do break
		if coop_item_check(run.shopkeeper.stock[a.index]) != a.check do break
		if shop_buy(&run.shopkeeper, player, int(a.index)).result == .Success do sfx_emit(run, .Coin_Pickup_Light)
	case .Shop_Sell:
		if !player_near_shop(run, slot) || !coop_bag_index_valid(player, a.index, a.check) do break
		if shop_sell_bag(&run.shopkeeper, player, int(a.index)).result == .Success do sfx_emit(run, .Coin_Pickup_Light)
	}
}

coop_bag_index_valid :: proc(player: ^Player, index: i32, check: u32) -> bool {
	if index < 0 || int(index) >= player.bag_count do return false
	return coop_item_check(player.bag[index]) == check
}

// Taps this frame's sound events before the host's audio drains them, so the
// joiner hears the same cues (bounded; cosmetic only).
coop_host_capture_sfx :: proc(app: ^App) {
	c := &app.coop
	if c.role != .Host || !c.h_joiner_synced do return
	for e in app.run.sfx {
		if len(c.h_sfx) >= COOP_MAX_SFX do break
		append(&c.h_sfx, e)
	}
}

@(private = "file")
coop_host_send_checkpoint :: proc(app: ^App) {
	c := &app.coop
	raw, ok := coop_checkpoint_encode(app, context.temp_allocator)
	if !ok do return
	random: [8]byte
	net_random_bytes(random[:])
	id: u64
	for b in random do id = id << 8 | u64(b)
	if id == 0 do id = 1
	chunks := make([dynamic][]byte, 0, 4, context.temp_allocator)
	if !coop_encode_checkpoint_chunks(id, app.run.floor_epoch, raw, &chunks, context.temp_allocator) do return
	for chunk in chunks do if !net_session_send_raw(&c.session, chunk) do return
	c.h_checkpoint_id = id
	c.h_checkpoint_epoch = app.run.floor_epoch
	c.h_need_checkpoint = false
	c.h_slow_force = ~bit_set[Coop_Slow_Section]{}
	// The baseline restarts the guest's command stream: cursors return to
	// zero and nothing from the previous stream is applied or acknowledged.
	c.h_joiner_synced = false
	c.h_resolved = 0
	c.h_seen_seq = 0
	c.h_seen_action = 0
	c.h_actions_resolved = 0
	c.h_hold = 0
	c.h_refilling = false
	clear(&c.h_cmds)
	clear(&c.h_actions)
	platform_log(fmt.tprintf("[coop] host sent checkpoint %d (epoch %d, %d bytes, %d chunks)", id, app.run.floor_epoch, len(raw), len(chunks)))
}

@(private = "file")
coop_host_send_snapshot :: proc(app: ^App) {
	c := &app.coop
	run := &app.run
	// A new floor always reaches the joiner as a checkpoint first.
	if run.floor_epoch != c.h_checkpoint_epoch {
		c.h_need_checkpoint = true
		c.h_joiner_synced = false
		clear(&c.h_cmds)
		clear(&c.h_actions)
		coop_host_send_checkpoint(app)
	}
	c.h_snapshot_seq += 1
	slow := c.h_slow_force
	c.h_slow_counter += 1
	refresh := c.h_slow_counter % COOP_SLOW_REFRESH == 0
	check := c.h_slow_counter % COOP_SLOW_CHECK_EVERY == 0
	for section in Coop_Slow_Section {
		cheap := section == .Ground || section == .Tiles || section == .Scalars || section == .Interactables
		if refresh || cheap || check {
			h := coop_slow_section_hash(run, section)
			if h != c.h_slow_hash[section] || refresh {
				c.h_slow_hash[section] = h
				slow += {section}
			}
		}
	}
	bytes := coop_encode_snapshot(app, {
		seq = c.h_snapshot_seq,
		pause = coop_host_pause(app),
		ack = c.h_resolved,
		actions_ack = c.h_actions_resolved,
		sfx = c.h_sfx[:],
		events = c.h_events[:],
		slow = slow,
	}, context.temp_allocator)
	if net_session_send_raw(&c.session, bytes) {
		c.h_slow_force = {}
		clear(&c.h_sfx)
		clear(&c.h_events)
	}
}

// Terminal result: identity, outcome, and both seats' final facts.
coop_host_publish_result :: proc(app: ^App, outcome: Run_Terminal_State) {
	c := &app.coop
	if c.ended do return
	random: [8]byte
	net_random_bytes(random[:])
	for b in random do c.result_id = c.result_id << 8 | u64(b)
	if c.result_id == 0 do c.result_id = 1
	c.outcome = outcome
	c.ended = true
	run := &app.run
	w: np.Json_Writer
	np.jw_init(&w, context.temp_allocator)
	np.jw_begin(&w)
	np.jw_str(&w, "t", "run_ended")
	np.jw_u64s(&w, "result", c.result_id)
	np.jw_str(&w, "outcome", outcome == .Victory ? "victory" : "death")
	np.jw_int(&w, "depth", i64(run.depth))
	np.jw_int(&w, "kills", i64(run.kills))
	np.jw_int(&w, "difficulty", i64(run.difficulty))
	np.jw_begin_array_key(&w, "seats")
	for slot in 0 ..< MAX_PLAYERS {
		p := &run.players[slot]
		np.jw_begin(&w)
		np.jw_int(&w, "archetype", i64(p.archetype))
		np.jw_int(&w, "level", i64(p.level))
		np.jw_int(&w, "gold", i64(p.gold))
		np.jw_bool(&w, "alive", p.hp > 0)
		np.jw_end(&w)
	}
	np.jw_end_array(&w)
	np.jw_end(&w)
	// Final snapshot first so the joiner presents the same last frame.
	coop_host_send_snapshot(app)
	_ = net_session_send_raw(&c.session, np.jw_bytes(&w))
}

// ================================================================== joiner ==

// Queue a local action edge. It is ordered with the next movement step.
coop_joiner_action :: proc(app: ^App, kind: Coop_Action_Kind, aim: Vec2 = {}, index: i32 = -1, arg: i32 = -1, check: u32 = 0) {
	c := &app.coop
	if !c.j_have_world || len(c.j_actions) >= COOP_MAX_BATCH_ACTIONS do return
	c.j_action_id += 1
	append(&c.j_actions, Coop_Action{id = c.j_action_id, at = c.j_cmd_seq + 1, kind = kind, aim = aim, index = index, arg = arg, check = check})
}

coop_joiner_paused :: proc(app: ^App) -> bool {
	c := &app.coop
	return !c.j_have_world || c.j_pause != {} || .Joiner_Shop in c.j_local_pause || c.session.phase != .Active
}

// One fixed tick on the joiner: produce and predict this seat's movement
// command, and ease remote actors between snapshots.
coop_joiner_tick :: proc(app: ^App, move: Vec2, max_step: f32, auto_melee: bool) {
	c := &app.coop
	run := &app.run
	if !c.j_have_world do return
	slot := run.local_slot
	player := &run.players[slot]
	player.prev_pos = player.pos
	player_tick_visual_action(player, SIM_DT)
	c.j_visual_hold = max(0, c.j_visual_hold - 1)
	if !coop_joiner_paused(app) && player.hp > 0 {
		c.j_cmd_seq += 1
		cmd := Coop_Command{
			seq = c.j_cmd_seq,
			move = move,
			max_step = max_step,
			auto_melee = auto_melee,
			aim = app.aim_input,
			aim_live = app.aim_live,
			melee = c.j_pending_melee,
			melee_aim = c.j_pending_melee_aim,
			dash = c.j_pending_dash,
			dash_aim = c.j_pending_dash_aim,
		}
		c.j_pending_melee, c.j_pending_dash = false, false
		c.j_ring[cmd.seq % COOP_CMD_RING] = cmd
		c.j_cmd_sent_ms[cmd.seq % COOP_CMD_RING] = app.net_now_ms
		// Contacts and melee arcs use the newest authoritative enemy positions,
		// not the delayed ones drawn for presentation.
		shown := coop_swap_in_newest_enemies(&c.j_interp, run)
		swung := sim_predict_player_step(run, slot, coop_predict_step(cmd))
		coop_restore_shown_enemies(run, shown)
		if swung && player.visual_action == .None {
			player_start_visual_action(player, .Attack, PLAYER_ATTACK_ACTION_SECONDS)
			coop_hold_visual(c, PLAYER_ATTACK_ACTION_SECONDS)
		}
		if cmd.move == {} && cmd.aim_live && linalg.length(cmd.aim) > MOUSE_AIM_DEAD_ZONE do player.facing = linalg.normalize0(cmd.aim)
	}
	c.j_send_counter += 1
	if c.j_send_counter >= 2 || len(c.j_actions) > 0 {
		c.j_send_counter = 0
		coop_joiner_flush(app)
	}
	coop_interp_advance(&c.j_interp, app.net_now_ms)
	coop_interp_apply(&c.j_interp, run)
	coop_joiner_age_transients(run)
	// The render-only correction eases out per fixed tick (~70 ms half-life),
	// so the drawn seat glides the same way at any frame rate.
	c.j_visual_offset *= COOP_OFFSET_DECAY_PER_TICK
	if linalg.length(c.j_visual_offset) < .002 do c.j_visual_offset = {}
	// Fog and discovery follow this seat every tick, as on the host.
	refresh_visibility(run)
}

// Damage numbers age locally between snapshots; matching keeps their clocks.
@(private = "file")
coop_joiner_age_transients :: proc(run: ^Run) {
	#reverse for &n, i in run.numbers {
		n.age += SIM_DT
		if n.age >= DAMAGE_NUMBER_SECONDS do unordered_remove(&run.numbers, i)
	}
}

coop_joiner_flush :: proc(app: ^App) {
	c := &app.coop
	if c.session.phase != .Active do return
	if c.j_unsent_from == 0 do c.j_unsent_from = 1
	commands := make([dynamic]Coop_Command, 0, COOP_MAX_BATCH_COMMANDS, context.temp_allocator)
	for seq := c.j_unsent_from; seq <= c.j_cmd_seq && len(commands) < COOP_MAX_BATCH_COMMANDS; seq += 1 {
		append(&commands, c.j_ring[seq % COOP_CMD_RING])
	}
	bytes := coop_encode_intent(commands[:], c.j_actions[:], c.j_local_pause, context.temp_allocator)
	if net_session_send_raw(&c.session, bytes) {
		c.j_unsent_from = c.j_cmd_seq + 1
		clear(&c.j_actions)
	}
}

@(private = "file")
coop_joiner_receive_checkpoint :: proc(app: ^App, data: []byte) {
	c := &app.coop
	obj, root, ok := np.json_parse_object(data, context.temp_allocator)
	defer json.destroy_value(root, context.temp_allocator)
	if !ok do return
	chunk, chunk_ok := coop_decode_checkpoint_chunk(obj)
	if !chunk_ok do return
	if chunk.index == 0 || chunk.id != c.j_ckpt_id {
		if chunk.index != 0 do return // missed the start; wait for a fresh one
		coop_reset_checkpoint(c)
		c.j_ckpt_id = chunk.id
		c.j_ckpt_count = chunk.count
		c.j_ckpt_total = chunk.total
		c.j_ckpt_epoch = chunk.epoch
		c.j_ckpt_sum = strings.clone(chunk.sum)
	}
	if chunk.index != len(c.j_ckpt_parts) || chunk.count != c.j_ckpt_count {
		coop_reset_checkpoint(c)
		return
	}
	append(&c.j_ckpt_parts, strings.clone(chunk.data))
	if len(c.j_ckpt_parts) < c.j_ckpt_count do return
	// Complete: decode, verify, and adopt atomically.
	joined := strings.concatenate(c.j_ckpt_parts[:], context.temp_allocator)
	raw, decode_err := base64.decode(joined, allocator = context.temp_allocator)
	id := c.j_ckpt_id
	epoch := c.j_ckpt_epoch
	verified := decode_err == nil && len(raw) == c.j_ckpt_total && coop_checkpoint_verify(raw, c.j_ckpt_sum)
	coop_reset_checkpoint(c)
	if !verified {
		platform_log(fmt.tprintf("[coop] checkpoint %d failed verification (%d/%d bytes); requesting resync", id, len(raw), c.j_ckpt_total))
		_ = net_session_send_raw(&c.session, coop_encode_sync_request(context.temp_allocator))
		return
	}
	// Heap-held scratch: see coop_checkpoint_decode for why no `Run` local.
	fresh := new(Run, context.temp_allocator)
	panel: Story_Panel_State
	minigame: Story_Minigame_State
	cursor: int
	turn_page: Turn_Page_State
	if !coop_checkpoint_decode(raw, fresh, &panel, &minigame, &cursor, &turn_page) {
		platform_log(fmt.tprintf("[coop] checkpoint %d did not decode (%d bytes); requesting resync", id, len(raw)))
		_ = net_session_send_raw(&c.session, coop_encode_sync_request(context.temp_allocator))
		return
	}
	platform_log(fmt.tprintf("[coop] checkpoint %d adopted: epoch %d, %d bytes, %d enemies", id, epoch, len(raw), len(fresh.enemies)))
	// Keep this client's own fog when the floor did not change, including a
	// rejoin: discovery is local presentation and the host never ships it.
	same_floor := app.run.player_count == MAX_PLAYERS && app.run.floor_epoch == fresh.floor_epoch && app.run.seed == fresh.seed
	explored := app.run.explored
	old := app.run
	app.run = fresh^
	run_destroy(&old)
	if same_floor do app.run.explored = explored
	app.run.local_slot = 1
	app.run.run_id = ""
	app.story_panel = panel
	app.story_minigame = minigame
	app.story_minigame_cursor = cursor
	app.turn_page = turn_page
	refresh_visibility(&app.run)
	c.j_have_world = true
	c.j_checkpoints_adopted += 1
	c.j_epoch = epoch
	c.j_cmd_seq = 0
	c.j_unsent_from = 1
	clear(&c.j_actions)
	c.j_visual_hold = 0
	// A new baseline restarts the presented timeline: never ease across it.
	coop_interp_reset(&c.j_interp)
	c.floor_changed = true
	if app.mode == .Coop_Wait do app.mode = .Playing
	_ = net_session_send_raw(&c.session, coop_encode_checkpoint_ack(id, context.temp_allocator))
}

@(private = "file")
coop_joiner_receive_snapshot :: proc(app: ^App, data: []byte) {
	c := &app.coop
	if !c.j_have_world do return
	obj, root, ok := np.json_parse_object(data, context.temp_allocator)
	defer json.destroy_value(root, context.temp_allocator)
	if !ok do return
	header, header_ok := coop_decode_snapshot_header(obj)
	if !header_ok || header.seq <= c.j_last_snapshot do return
	// A new floor's snapshots wait for its checkpoint; never apply them to
	// the previous floor.
	if header.epoch != c.j_epoch do return
	if header.ack > c.j_cmd_seq {
		platform_log(fmt.tprintf("[coop] snapshot %d acknowledges step %d beyond our %d; ignored", header.seq, header.ack, c.j_cmd_seq))
		return
	}
	if !coop_joiner_apply_snapshot(app, data, obj, header) {
		c.j_snapshots_rejected += 1
		if c.j_snapshots_rejected <= 5 || c.j_snapshots_rejected % 100 == 0 {
			platform_log(fmt.tprintf("[coop] snapshot %d rejected (%d bytes, epoch %d, ack %d/%d)", header.seq, len(data), header.epoch, header.ack, c.j_cmd_seq))
		}
		return
	}
	c.j_snapshots_applied += 1
	c.j_last_snapshot = header.seq
	c.j_snapshot_bytes = len(data)
	c.j_last_snapshot_ms = app.net_now_ms
}

// Validates the whole snapshot into scratch state, then installs it.
@(private = "file")
coop_joiner_apply_snapshot :: proc(app: ^App, raw: []byte, obj: json.Object, h: Coop_Snapshot_Header) -> bool {
	c := &app.coop
	run := &app.run
	local := run.local_slot
	remote := 1 - local

	players, players_ok := np.read_array(obj, "p", MAX_PLAYERS)
	if !players_ok || len(players) != MAX_PLAYERS do return false
	new_players := run.players
	// Slow player sections first (inventory, disciplines), then fast fields.
	if _, has_slow := np.read_object(obj, "sl"); has_slow {
		members, found := np.raw_object_members(raw, "sl")
		if !found || !coop_joiner_apply_slow(app, members, &new_players) do return false
	}
	for slot in 0 ..< MAX_PLAYERS {
		if !coop_decode_player_fast(players[slot], &new_players[slot]) do return false
	}

	enemies_v, e_ok := np.read_array(obj, "e", COOP_MAX_ENEMIES)
	projectiles_v, pr_ok := np.read_array(obj, "pr", COOP_MAX_PROJECTILES)
	familiars_v, fa_ok := np.read_array(obj, "fa", COOP_MAX_FAMILIARS)
	bells_v, bl_ok := np.read_array(obj, "bl", COOP_MAX_BELLS)
	numbers_v, nu_ok := np.read_array(obj, "nu", COOP_MAX_NUMBERS)
	feel_v, fe_ok := np.read_array(obj, "fe", COOP_MAX_FEEL)
	sfx_v, sx_ok := np.read_array(obj, "sx", COOP_MAX_SFX)
	events_v, ev_ok := np.read_array(obj, "ev", 16)
	npcs_v, np_ok := np.read_array(obj, "np", MAX_AMBIENT_ROOM_RESIDENTS + 1)
	guests_v, gu_ok := np.read_array(obj, "gu", COOP_MAX_GUESTS)
	if !(e_ok && pr_ok && fa_ok && bl_ok && nu_ok && fe_ok && sx_ok && ev_ok && np_ok && gu_ok) do return false

	enemies := make([dynamic]Enemy, 0, len(enemies_v), context.temp_allocator)
	for v in enemies_v {
		arr, is_arr := v.(json.Array)
		if !is_arr || len(arr) < 1 do return false
		id, id_ok := arr[0].(json.Integer)
		if !id_ok do return false
		e: Enemy
		found := false
		for &old in run.enemies do if i64(old.entity_id) == i64(id) {
			e = old
			found = true
			break
		}
		if !found {
			e = enemy_make(.Ghoul, {}, run.depth)
		}
		if !coop_decode_enemy(arr, &e) do return false
		append(&enemies, e)
	}
	projectiles := make([dynamic]Projectile, 0, len(projectiles_v), context.temp_allocator)
	for v in projectiles_v {
		p, p_ok := coop_decode_projectile(v)
		if !p_ok do return false
		append(&projectiles, p)
	}
	familiars := make([dynamic]Familiar, 0, len(familiars_v), context.temp_allocator)
	for v in familiars_v {
		arr, is_arr := v.(json.Array)
		if !is_arr || len(arr) < 1 do return false
		f: Familiar
		if id, id_ok := arr[0].(json.Integer); id_ok {
			for &old in run.familiars do if i64(old.entity_id) == i64(id) do f = old
		}
		if !coop_decode_familiar(v, &f) do return false
		append(&familiars, f)
	}
	bells := make([dynamic]Ambush_Bell, 0, len(bells_v), context.temp_allocator)
	for v in bells_v {
		b, b_ok := coop_decode_bell(v)
		if !b_ok do return false
		append(&bells, b)
	}
	intern := proc(s: string) -> string {return s}
	numbers := make([dynamic]Damage_Number, 0, len(numbers_v), context.temp_allocator)
	for v in numbers_v {
		n, n_ok := coop_decode_number(v, intern)
		if !n_ok do return false
		append(&numbers, n)
	}
	feel := make([dynamic]Feel_Event, 0, len(feel_v), context.temp_allocator)
	for v in feel_v {
		f, f_ok := coop_decode_feel(v)
		if !f_ok do return false
		append(&feel, f)
	}
	sfx := make([dynamic]Sfx_Event, 0, len(sfx_v), context.temp_allocator)
	for v in sfx_v {
		e, s_ok := coop_decode_sfx(v)
		if !s_ok do return false
		append(&sfx, e)
	}

	// ---- install (everything above validated)
	c.j_pause = h.pause
	run.active_ticks = h.tick
	hs, _ := np.read_int(obj, "hs", 0, 100)
	run.hitstop_ticks = int(hs)
	if at, at_ok := np.read_f32(obj, "at", 0, 100); at_ok do run.arrival_timer = at
	if wf, wf_ok := np.read_f32(obj, "wf", 0, 100); wf_ok do run.wall_face_timer = wf
	wx, _ := np.read_int(obj, "wx", 0, MAP_W)
	wy, _ := np.read_int(obj, "wy", 0, MAP_H)
	run.wall_face_tile = {int(wx), int(wy)}

	// Displayed (interpolated) positions before this snapshot, by identity.
	Shown :: struct {key: u64, pos, prev, facing: Vec2, anim: f32}
	shown := make([dynamic]Shown, 0, len(run.enemies) + len(run.familiars) + 1, context.temp_allocator)
	for &e in run.enemies do append(&shown, Shown{coop_actor_key(.Enemy, u64(e.entity_id)), e.pos, e.prev_pos, e.facing, e.anim_time})
	for &f in run.familiars do append(&shown, Shown{coop_actor_key(.Familiar, u64(f.entity_id)), f.pos, f.prev_pos, f.facing, f.anim_time})
	for &p in run.projectiles do append(&shown, Shown{coop_actor_key(.Projectile, p.entity_id), p.pos, p.prev_pos, p.vel, p.visual_age})
	partner_shown := run.players[remote]

	// Remote seat and actor lists: authoritative state at host time.
	run.players[remote] = new_players[remote]
	clear(&run.enemies)
	append(&run.enemies, ..enemies[:])
	clear(&run.familiars)
	append(&run.familiars, ..familiars[:])
	clear(&run.projectiles)
	append(&run.projectiles, ..projectiles[:])
	clear(&run.bells)
	append(&run.bells, ..bells[:])
	coop_joiner_install_npcs(run, npcs_v, guests_v)
	if so, so_ok := np.read_array(obj, "so", 8); so_ok && len(so) == 8 {
		soul_pos := run.story_runtime.soul.pos
		if x, x_ok := so[0].(json.Float); x_ok do soul_pos.x = f32(x)
		if y, y_ok := so[1].(json.Float); y_ok do soul_pos.y = f32(y)
		run.story_runtime.soul.pos = soul_pos
		if hp, hp_ok := so[7].(json.Integer); hp_ok do run.story_runtime.soul.hp = int(hp)
	}
	// Positions belong to the host's last fixed tick, so the timeline is the
	// tick clock (not the host frame clock): samples carry no sub-tick
	// timing jitter and the presented world pauses exactly when the host's does.
	coop_interp_record(&c.j_interp, run, f64(h.tick) * (1000.0 / SIM_HZ), app.net_now_ms)
	// Local seat: adopt gameplay authority (vitals, cooldowns, statuses,
	// inventory), replay unacknowledged steps against the authoritative
	// actor positions just installed, and keep the presentation this client
	// owns: facing, walk phase, and its predicted action clip.
	shown_local := run.players[local]
	run.players[local] = new_players[local]
	me := &run.players[local]
	for seq := h.ack + 1; seq <= c.j_cmd_seq; seq += 1 {
		if c.j_cmd_seq - seq >= COOP_CMD_RING do continue
		_ = sim_predict_player_step(run, local, coop_predict_step(c.j_ring[seq % COOP_CMD_RING]))
	}
	correction := linalg.distance(shown_local.pos, me.pos)
	c.j_last_correction = correction
	c.j_max_correction = max(c.j_max_correction, correction)
	if h.ack > 0 && c.j_cmd_seq - h.ack < COOP_CMD_RING {
		sent := c.j_cmd_sent_ms[h.ack % COOP_CMD_RING]
		if sent > 0 do c.j_ack_latency_ms = app.net_now_ms - sent
	}
	// Corrections ease out through a render-only offset; collision, targeting,
	// and the next replay always use the corrected position.
	if correction <= COOP_SNAP_DISTANCE {
		// Keep the drawn position continuous: offset = drawn_before - new.
		c.j_visual_offset += shown_local.pos - me.pos
		// Beyond the smoothing bound the discrepancy is shown honestly (snap),
		// never eased through geometry or a host-imposed stop.
		if l := linalg.length(c.j_visual_offset); l > COOP_SMOOTH_MAX do c.j_visual_offset *= COOP_SMOOTH_MAX / l
	} else {
		c.j_visual_offset = {}
	}
	me.prev_pos = me.pos + (shown_local.prev_pos - shown_local.pos)
	me.facing = shown_local.facing
	me.heading_stable, me.heading_hold = shown_local.heading_stable, shown_local.heading_hold
	me.anim_time = shown_local.anim_time
	me.moving = shown_local.moving
	me.guidance_idle_elapsed = shown_local.guidance_idle_elapsed
	authoritative_death := me.hp <= 0 || me.visual_action == .Die || me.visual_action == .Dead
	host_flourish := me.visual_action == .Pet // raise/pet poses start on the host
	if !authoritative_death && !host_flourish && (c.j_visual_hold > 0 || shown_local.visual_action != .None) {
		me.visual_action = shown_local.visual_action
		me.action_time = shown_local.action_time
		me.action_duration = shown_local.action_duration
	}

	// Presentation continuity: actors stay where they were drawn until the
	// delayed timeline moves them on the next tick.
	restore :: proc(shown: []Shown, key: u64, pos, prev, facing: ^Vec2, anim: ^f32) {
		for sh in shown do if sh.key == key {
			pos^, prev^, facing^, anim^ = sh.pos, sh.prev, sh.facing, sh.anim
			return
		}
		prev^ = pos^
	}
	for &e in run.enemies do restore(shown[:], coop_actor_key(.Enemy, u64(e.entity_id)), &e.pos, &e.prev_pos, &e.facing, &e.anim_time)
	for &f in run.familiars do restore(shown[:], coop_actor_key(.Familiar, u64(f.entity_id)), &f.pos, &f.prev_pos, &f.facing, &f.anim_time)
	for &p in run.projectiles {
		// A brand-new shot stays at its spawn sample until the timeline
		// reaches it, instead of appearing ahead of itself.
		vel := p.vel
		restore(shown[:], coop_actor_key(.Projectile, p.entity_id), &p.pos, &p.prev_pos, &p.vel, &p.visual_age)
		p.vel = vel
	}
	partner := &run.players[remote]
	if partner_shown.pos != {} && linalg.distance(partner_shown.pos, partner.pos) <= COOP_SNAP_DISTANCE {
		partner.pos, partner.prev_pos = partner_shown.pos, partner_shown.prev_pos
		partner.facing, partner.anim_time = partner_shown.facing, partner_shown.anim_time
	}

	// Numbers and feel effects: keep local clocks for ones already shown,
	// add new ones, drop ones the host has retired.
	coop_merge_numbers(c, run, numbers[:])
	coop_merge_feel(run, feel[:])
	for e in sfx do if len(run.sfx) < MAX_SFX_EVENTS_PER_FRAME do append(&run.sfx, e)

	for v in events_v {
		n, is_int := v.(json.Integer)
		if !is_int do continue
		if Coop_Joiner_Event(n) == .Open_Shop do c.j_shop_requested = true
	}
	return true
}

@(private = "file")
coop_joiner_install_npcs :: proc(run: ^Run, npcs_v, guests_v: json.Array) {
	for v, i in npcs_v {
		if i == 0 {
			_ = coop_decode_npc(v, &run.shopkeeper.pos, &run.shopkeeper.motion)
		} else if i - 1 < run.ambient_residents.count {
			r := &run.ambient_residents.items[i - 1]
			_ = coop_decode_npc(v, &r.pos, &r.motion)
		}
	}
	for v, i in guests_v {
		if i >= len(run.story_runtime.guests) do break
		arr, is_arr := v.(json.Array)
		if !is_arr || len(arr) != 8 do continue
		g := &run.story_runtime.guests[i]
		num :: proc(v: json.Value) -> (f32, bool) {
			#partial switch n in v {
			case json.Float: return f32(n), true
			case json.Integer: return f32(n), true
			}
			return 0, false
		}
		if x, ok := num(arr[0]); ok do g.pos.x = x
		if y, ok := num(arr[1]); ok do g.pos.y = y
		if fx, ok := num(arr[2]); ok do g.motion.facing.x = fx
		if fy, ok := num(arr[3]); ok do g.motion.facing.y = fy
		if a, ok := num(arr[4]); ok do g.motion.anim_time = a
		if m, ok := arr[6].(json.Integer); ok do g.motion.moving = m == 1
		if hp, ok := arr[7].(json.Integer); ok do g.hp = int(hp)
	}
	soul := &run.story_runtime.soul
	_ = soul
}

@(private = "file")
coop_merge_numbers :: proc(c: ^Coop_State, run: ^Run, incoming: []Damage_Number) {
	kept := make([dynamic]Damage_Number, 0, len(incoming), context.temp_allocator)
	used := make([]bool, len(run.numbers), context.temp_allocator)
	for n in incoming {
		match := -1
		for &old, i in run.numbers {
			if used[i] || old.kind != n.kind || old.value != n.value || old.text != n.text do continue
			if linalg.distance(old.pos, n.pos) > .01 do continue
			match = i
			break
		}
		if match >= 0 {
			used[match] = true
			append(&kept, run.numbers[match])
		} else {
			fresh := n
			fresh.text = coop_intern(c, n.text)
			append(&kept, fresh)
		}
	}
	clear(&run.numbers)
	append(&run.numbers, ..kept[:])
}

@(private = "file")
coop_merge_feel :: proc(run: ^Run, incoming: []Feel_Event) {
	kept := make([dynamic]Feel_Event, 0, len(incoming), context.temp_allocator)
	used := make([]bool, len(run.feel), context.temp_allocator)
	for f in incoming {
		match := -1
		for &old, i in run.feel {
			if used[i] || old.kind != f.kind || old.duration != f.duration || old.style != f.style do continue
			if linalg.distance(old.pos, f.pos) > .01 || linalg.distance(old.direction, f.direction) > .01 do continue
			match = i
			break
		}
		if match >= 0 {
			used[match] = true
			append(&kept, run.feel[match])
		} else {
			append(&kept, f)
		}
	}
	clear(&run.feel)
	append(&run.feel, ..kept[:])
}

@(private = "file")
coop_joiner_apply_slow :: proc(app: ^App, sl: map[string][]byte, players: ^[MAX_PLAYERS]Player) -> bool {
	c := &app.coop
	run := &app.run
	for section in Coop_Slow_Section {
		raw, present := sl[COOP_SLOW_KEYS[section]]
		if !present do continue
		switch section {
		case .Player0, .Player1:
			p: Player
			if json.unmarshal(raw, &p, allocator = context.temp_allocator) != nil do return false
			if !coop_player_valid(&p) do return false
			coop_intern_player(c, &p)
			players[section == .Player0 ? 0 : 1] = p
		case .Ground:
			items: [dynamic]Ground_Item
			if json.unmarshal(raw, &items, allocator = context.temp_allocator) != nil do return false
			if len(items) > 512 do return false
			clear(&run.ground_items)
			for g in items {
				gi := g
				coop_intern_item(c, &gi.item)
				append(&run.ground_items, gi)
			}
		case .Tiles:
			if len(raw) != MAP_W * MAP_H + 2 || raw[0] != '"' || raw[len(raw) - 1] != '"' do return false
			text := raw[1:len(raw) - 1]
			i := 0
			for x in 0 ..< MAP_W {
				for y in 0 ..< MAP_H {
					d := int(text[i]) - '0'
					if d < 0 || d >= len(Tile_Kind) do return false
					run.dungeon.tiles[x][y] = Tile_Kind(d)
					i += 1
				}
			}
			refresh_visibility(run)
		case .Interactables:
			it: Coop_Interactables
			if json.unmarshal(raw, &it, allocator = context.temp_allocator) != nil do return false
			clear(&run.traps)
			append(&run.traps, ..it.traps[:])
			clear(&run.shrines)
			append(&run.shrines, ..it.shrines[:])
			clear(&run.secrets)
			append(&run.secrets, ..it.secrets[:])
		case .Shop:
			shop: Coop_Shop
			if json.unmarshal(raw, &shop, allocator = context.temp_allocator) != nil do return false
			if shop.shopkeeper.stock_count < 0 || shop.shopkeeper.stock_count > SHOP_STOCK_CAPACITY do return false
			pos, prev, motion := run.shopkeeper.pos, run.shopkeeper.prev_pos, run.shopkeeper.motion
			run.has_shopkeeper = shop.has_shopkeeper
			run.shopkeeper = shop.shopkeeper
			run.shopkeeper.pos, run.shopkeeper.prev_pos, run.shopkeeper.motion = pos, prev, motion
			run.shopkeeper.name = coop_intern(c, shop.shopkeeper.name)
			run.shopkeeper.role = coop_intern(c, shop.shopkeeper.role)
			for i in 0 ..< SHOP_STOCK_CAPACITY do coop_intern_item(c, &run.shopkeeper.stock[i])
		case .Story:
			st: Coop_Story
			if json.unmarshal(raw, &st, allocator = context.temp_allocator) != nil do return false
			if len(st.guests) > COOP_MAX_GUESTS do return false
			clear(&run.story_runtime.guests)
			for g in st.guests {
				guest := g
				guest.name = coop_intern(c, g.name)
				guest.motive = coop_intern(c, g.motive)
				guest.dialogue = coop_intern(c, g.dialogue)
				append(&run.story_runtime.guests, guest)
			}
			run.story_runtime.soul = st.soul
			run.story_runtime.relic = st.relic
		case .Scalars:
			sc: Coop_Run_Scalars
			if json.unmarshal(raw, &sc, allocator = context.temp_allocator) != nil do return false
			run.depth = clamp(sc.depth, 1, DUNGEON_DEPTH)
			run.difficulty = sc.difficulty
			run.kills = sc.kills
			run.boss_engaged = sc.boss_engaged
			run.tyrant_dead = sc.tyrant_dead
			run.victory = sc.victory
			run.dark_floor = sc.dark_floor
			run.theme_index = clamp(sc.theme_index, 0, len(THEMES) - 1)
			run.traps_triggered = sc.traps_triggered
			run.shrines_used = sc.shrines_used
			run.secrets_opened = sc.secrets_opened
			run.bars_visited = sc.bars_visited
			run.bars_toasted = sc.bars_toasted
			run.challenge_rooms_cleared = sc.challenge_rooms_cleared
			run.refuge = sc.refuge
			run.defeated_bosses = sc.defeated_bosses
			run.notable_count = clamp(sc.notable_count, 0, MAX_NOTABLE_LOOT)
			for i in 0 ..< MAX_NOTABLE_LOOT {
				run.notable_loot[i] = sc.notable_loot[i]
				run.notable_loot[i].item_id = coop_intern(c, sc.notable_loot[i].item_id)
				run.notable_loot[i].name = coop_intern(c, sc.notable_loot[i].name)
			}
			run.modifier = sc.modifier
			run.potions_used = sc.potions_used
			run.elites_killed = sc.elites_killed
			clear(&run.sealed)
			append(&run.sealed, ..sc.sealed[:])
		}
	}
	return true
}

coop_intern_item :: proc(c: ^Coop_State, item: ^Item) {
	item.name = coop_intern(c, item.name)
	item.icon = coop_intern(c, item.icon)
}

coop_intern_player :: proc(c: ^Coop_State, p: ^Player) {
	coop_intern_item(c, &p.weapon)
	coop_intern_item(c, &p.armor)
	for i in 0 ..< BAG_CAPACITY do coop_intern_item(c, &p.bag[i])
}

@(private = "file")
coop_joiner_receive_run_ended :: proc(app: ^App, data: []byte) {
	c := &app.coop
	obj, root, ok := np.json_parse_object(data, context.temp_allocator)
	defer json.destroy_value(root, context.temp_allocator)
	if !ok do return
	id, id_ok := np.read_u64s(obj, "result")
	outcome, out_ok := np.read_str(obj, "outcome", 16)
	if !id_ok || !out_ok do return
	if c.ended && id == c.result_id {
		net_session_ack_result(&c.session, id) // duplicate delivery after a blip
		return
	}
	c.result_id = id
	c.outcome = outcome == "victory" ? .Victory : .Death
	c.ended = true
	app.mode = c.outcome == .Victory ? .Victory : .Dead
	app_clear_play_input(app)
	net_session_ack_result(&c.session, id)
}

// Teardown back to the title: the solo checkpoint on disk is untouched.
coop_leave :: proc(app: ^App) {
	c := &app.coop
	if c.role == .None do return
	net_session_leave(&c.session)
	coop_destroy(c)
	if app.run.run_id == "" {
		run_destroy(&app.run)
		app.run = {}
	}
	app_reset_run_ui(app)
	app.death_pending = false
	app.mode = .Title
}

// Keeps math imported for helpers below when building without asserts.
@(private = "file")
_coop_unused :: proc() {_ = math.PI}

// ---------------------------------------------------------------- menu UI --

Coop_Text_Field :: enum u8 {
	Name,
	Server,
	Code,
}

COOP_FIELD_MAX :: 200

Coop_Menu_Row :: enum u8 {
	Name,
	Server,
	Host,
	Code,
	Join,
	Back,
}

// Raylib-free menu state for setup/lobby screens. Text buffers hold UTF-8.
Coop_Ui_State :: struct {
	row:          int,
	editing:      bool,
	fields:       [Coop_Text_Field][COOP_FIELD_MAX]byte,
	lens:         [Coop_Text_Field]int,
	consented:    string, // endpoint accepted this process; owned
	consent_open: bool,
	consent_role: np.Role,
	lobby_row:    int,
	select_index: int,
	message:      string, // static or temp-safe status line
	debug:        bool,   // F3 co-op network overlay
}

// ------------------------------------------------------------ action seam --

// Every sim-mutating local action goes through here: solo and the co-op host
// act on their own seat immediately; the joiner sends an ordered action edge
// and waits for the host's authoritative result.
app_act :: proc(app: ^App, kind: Coop_Action_Kind, aim: Vec2 = {}, index := -1, arg := -1) -> bool {
	run := &app.run
	slot := run.local_slot
	player := &run.players[slot]
	if coop_is_joiner(app) {
		check: u32 = 0
		switch kind {
		case .Equip, .Drop, .Shop_Sell:
			if index >= 0 && index < player.bag_count do check = coop_item_check(player.bag[index])
		case .Shop_Buy:
			if index >= 0 && index < run.shopkeeper.stock_count do check = coop_item_check(run.shopkeeper.stock[index])
		case .None, .Melee, .Big_Hit_Begin, .Big_Hit_Release, .Bolt, .Class_Skill, .Dash, .Potion_Heal, .Potion_Mana, .Interact, .Sort, .Discipline:
		}
		coop_joiner_predict_action(app, kind, aim)
		coop_joiner_action(app, kind, aim, i32(index), i32(arg), check)
		return true
	}
	switch kind {
	case .None:
	case .Melee:           player_melee(run, slot, aim)
	case .Big_Hit_Begin:   return player_big_hit_begin(run, slot, aim)
	case .Big_Hit_Release: return player_big_hit_release(player, run)
	case .Bolt:            return player_cast_bolt(run, slot, aim)
	case .Class_Skill:     return player_cast_class_skill(run, slot, aim)
	case .Dash:            return player_dash(run, slot, aim)
	case .Potion_Heal:     player_use_potion(run, slot, .Heal_Potion)
	case .Potion_Mana:     player_use_potion(run, slot, .Mana_Potion)
	case .Equip:           equip_from_bag(player, index)
	case .Drop:            return drop_from_bag(run, slot, index)
	case .Sort:            sort_bag(player, Inventory_Sort_Mode(arg))
	case .Discipline:      return run_try_acquire_discipline(run, slot, Discipline_Id(arg)) == .Acquired
	case .Interact, .Shop_Buy, .Shop_Sell:
		// Handled inline by app_apply: these have UI-side results.
	}
	return true
}

// A seat that just fell plays its authored die clip; the replicated visual
// action shows the same death on both clients. The partner fights on.
coop_host_mark_fallen :: proc(app: ^App) {
	run := &app.run
	for slot in 0 ..< run_seat_count(run) {
		p := &run.players[slot]
		if p.hp > 0 || p.visual_action == .Die || p.visual_action == .Dead do continue
		p.hit_flash = 0
		p.hit_flash_duration = 0
		_ = player_big_hit_release(p, run)
		player_start_visual_action(p, .Die, PLAYER_DIE_SECONDS)
		if slot == run.local_slot do app_clear_play_input(app)
	}
}

// The joiner never runs the shared simulation: it predicts its own seat,
// eases the rest, and keeps its local menus responsive.
coop_joiner_app_tick :: proc(app: ^App) {
	c := &app.coop
	run := &app.run
	if !c.j_have_world do return
	tick_feel_events(run, SIM_DT)
	run.arrival_timer = max(0, run.arrival_timer - SIM_DT)
	if c.j_shop_requested {
		c.j_shop_requested = false
		if app.mode == .Playing && !app.inventory_open && !app.character_open {
			app.shop_open = true
			app.shop_mode = .Buy
			app.shop_index = 0
			app.shop_scroll = 0
			app_clear_play_input(app)
		}
	}
	c.j_local_pause = app.shop_open ? {.Joiner_Shop} : {}
	move: Vec2
	max_step: f32 = -1
	auto_melee := false
	player := &run.players[run.local_slot]
	can_move := app.mode == .Playing && !app.inventory_open && !app.character_open && !app.shop_open && player.hp > 0
	if can_move {
		if app.move_input == {} && app.aim_live && aim_outside_dead_zone(app.aim_input) && !coop_joiner_paused(app) {
			player.facing = linalg.normalize0(app.aim_input)
		}
		if app.mouse_press_pending {
			attack_aim := app.mouse_press_aim
			if !aim_outside_dead_zone(attack_aim) do attack_aim = player.facing
			_ = app_act(app, .Melee, attack_aim)
			app.mouse_press_pending = false
		}
		move = app.move_input
		if move == {} && app.mouse_walk {
			to_cursor := app.mouse_target - player.pos
			distance := math.hypot(to_cursor.x, to_cursor.y)
			if distance > MOUSE_WALK_STOP_RADIUS {
				move = to_cursor
				max_step = distance - MOUSE_WALK_STOP_RADIUS
			}
		}
		auto_melee = app.move_input != {} || app.mouse_walk
	}
	coop_joiner_tick(app, move, max_step, auto_melee)
}

// Cosmetic prediction of the guest's own action: the clip, facing, swing
// plant, and resource/cooldown display start on press. Damage, projectiles,
// and every resource spend remain host-authoritative and arrive with the
// next snapshot. A short hold keeps the lagging host copy of the same clip
// from replaying it.
coop_joiner_predict_action :: proc(app: ^App, kind: Coop_Action_Kind, aim: Vec2) {
	c := &app.coop
	run := &app.run
	p := &run.players[run.local_slot]
	if p.hp <= 0 || coop_joiner_paused(app) || bighit_charging(p) do return
	face :: proc(p: ^Player, aim: Vec2) {
		if linalg.length(aim) > MOUSE_AIM_DEAD_ZONE do p.facing = linalg.normalize0(aim)
	}
	clip: Visual_Action
	duration: f32
	#partial switch kind {
	case .Melee:
		// The plant itself happens in the next predicted step, exactly where
		// the host applies the edge; the clip starts there when it lands.
		c.j_pending_melee = true
		c.j_pending_melee_aim = linalg.length(aim) > MOUSE_AIM_DEAD_ZONE ? linalg.normalize0(aim) : p.facing
		return
	case .Bolt:
		if p.bolt_timer > 0 || p.mana < f32(player_bolt_mana_cost(p)) do return
		face(p, aim)
		p.bolt_timer = player_bolt_cooldown(p)
		clip, duration = .Cast, PLAYER_BOLT_ACTION_SECONDS
	case .Class_Skill:
		if p.class_skill_timer > 0 || p.mana < player_class_skill_mana_cost(p) do return
		face(p, aim)
		clip, duration = .Cast, PLAYER_CLASS_ACTION_SECONDS
	case .Dash:
		if p.dash_timer > 0 || p.stamina < f32(player_dash_stamina_cost(p)) do return
		c.j_pending_dash = true
		c.j_pending_dash_aim = linalg.length(aim) > MOUSE_AIM_DEAD_ZONE ? linalg.normalize0(aim) : p.facing
		clip, duration = .Dash, PLAYER_DASH_ACTION_SECONDS
	case:
		return
	}
	player_start_visual_action(p, clip, duration)
	coop_hold_visual(c, duration)
}

coop_hold_visual :: proc(c: ^Coop_State, duration: f32) {
	rtt_ticks := int(f64(max(c.session.rtt_ms, 50)) / 1000 * SIM_HZ)
	c.j_visual_hold = max(c.j_visual_hold, int(duration * SIM_HZ) + rtt_ticks + 6)
}

// Temporarily moves replica enemies to their newest authoritative sample for
// prediction; returns the drawn positions to put back afterwards.
coop_swap_in_newest_enemies :: proc(s: ^Coop_Interp_State, run: ^Run) -> []Vec2 {
	shown := make([]Vec2, len(run.enemies), context.temp_allocator)
	if s.count == 0 do return shown
	newest := &s.samples[s.head]
	for &e, i in run.enemies {
		shown[i] = e.pos
		key := coop_actor_key(.Enemy, u64(e.entity_id))
		hint := i + 1
		if hint < len(newest.actors) && newest.actors[hint].key == key {
			e.pos = newest.actors[hint].pos
			continue
		}
		for a in newest.actors do if a.key == key {
			e.pos = a.pos
			break
		}
	}
	return shown
}

coop_restore_shown_enemies :: proc(run: ^Run, shown: []Vec2) {
	for &e, i in run.enemies do if i < len(shown) do e.pos = shown[i]
}

// Where this client draws (and frames the camera on) its own seat: the
// interpolated simulation position plus the decaying co-op correction.
local_player_render_pos :: proc(app: ^App, alpha: f32) -> Vec2 {
	player := &app.run.players[app.run.local_slot]
	pos := player.prev_pos + (player.pos - player.prev_pos) * alpha
	if coop_is_joiner(app) do pos += app.coop.j_visual_offset
	return pos
}
