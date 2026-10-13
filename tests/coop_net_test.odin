package archrogue_tests

// End-to-end co-op over the real relay reducer with in-process transports:
// lobby, admission, start, checkpoint adoption, predicted movement with host
// acknowledgment, remote actions, and floor transitions.

import "core:encoding/json"
import "core:math/linalg"
import "core:testing"
import ar "../src"
import rc "../tools/relay/core"
import np "../src/net_protocol"

@(private = "file")
@(thread_local)
net_random_counter: u8

@(private = "file")
net_fake_random :: proc(buf: []byte) {
	for &b in buf {
		net_random_counter += 37
		b = net_random_counter
	}
}

@(private = "file")
Delayed :: struct {
	at:   i64,
	data: []byte,
}

// Deterministic network impairment: one-way latency plus jitter per
// direction, delivered in order like TCP.
@(private = "file")
Net_Harness :: struct {
	hub:       rc.Hub,
	pipes:     [2]ar.Net_Test_Pipe,
	opened:    [2]bool,
	apps:      [2]^ar.App,
	now:       i64,
	latency:   i64,
	jitter:    i64,
	rng:       u32,
	up:        [2][dynamic]Delayed, // client -> relay
	down:      [2][dynamic]Delayed, // relay -> client
}

@(private = "file")
harness_delay :: proc(h: ^Net_Harness, queue: ^[dynamic]Delayed) -> i64 {
	h.rng = h.rng * 1664525 + 1013904223
	extra := h.jitter > 0 ? i64(h.rng >> 8) % (h.jitter + 1) : 0
	at := h.now + h.latency + extra
	if len(queue) > 0 do at = max(at, queue[len(queue) - 1].at)
	return at
}

@(private = "file")
harness_new :: proc() -> ^Net_Harness {
	h := new(Net_Harness)
	rc.hub_init(&h.hub, rc.DEFAULT_CONFIG, net_fake_random)
	h.now = 10_000
	for i in 0 ..< 2 {
		h.apps[i] = new(ar.App)
		ar.app_init(h.apps[i], u64(1234 + i))
	}
	return h
}

@(private = "file")
harness_free :: proc(h: ^Net_Harness) {
	for i in 0 ..< 2 {
		ar.coop_destroy(&h.apps[i].coop)
		ar.run_destroy(&h.apps[i].run)
		ar.profile_destroy(&h.apps[i].profile)
		delete(h.apps[i].coop_ui.consented)
		free(h.apps[i])
		ar.net_test_pipe_destroy(&h.pipes[i])
		for d in h.up[i] do delete(d.data)
		for d in h.down[i] do delete(d.data)
		delete(h.up[i])
		delete(h.down[i])
	}
	rc.hub_destroy(&h.hub)
	free(h)
}

@(private = "file")
pump :: proc(h: ^Net_Harness) {
	for i in 0 ..< 2 {
		pipe := &h.pipes[i]
		id := rc.Conn_Id(i + 1)
		if pipe.open && !h.opened[i] {
			rc.hub_open(&h.hub, id, h.now)
			h.opened[i] = true
		}
		for len(pipe.to_relay) > 0 {
			m := pipe.to_relay[0]
			ordered_remove(&pipe.to_relay, 0)
			append(&h.up[i], Delayed{harness_delay(h, &h.up[i]), m})
		}
		for len(h.up[i]) > 0 && h.up[i][0].at <= h.now {
			m := h.up[i][0].data
			ordered_remove(&h.up[i], 0)
			if !pipe.closed do rc.hub_receive(&h.hub, id, m, h.now)
			delete(m)
		}
	}
	for a in h.hub.out {
		i := int(a.conn) - 1
		pipe := &h.pipes[i]
		switch a.kind {
		case .Send:
			copy_ := make([]byte, len(a.data))
			copy(copy_, a.data)
			append(&h.down[i], Delayed{harness_delay(h, &h.down[i]), copy_})
		case .Close:
			pipe.closed = true
		}
	}
	rc.hub_actions_clear(&h.hub)
	for i in 0 ..< 2 {
		for len(h.down[i]) > 0 && h.down[i][0].at <= h.now {
			m := h.down[i][0].data
			ordered_remove(&h.down[i], 0)
			if h.pipes[i].closed do delete(m)
			else do append(&h.pipes[i].to_client, m)
		}
	}
}

// One rendered frame on both clients plus a 60 Hz tick each.
@(private = "file")
frame :: proc(h: ^Net_Harness, ticks := 1) {
	for _ in 0 ..< ticks {
		h.now += 16
		for i in 0 ..< 2 {
			app := h.apps[i]
			app.net_now_ms = h.now
			ar.coop_frame(app, h.now)
			ar.coop_update_screens(app)
			ar.app_tick(app)
			ar.coop_frame(app, h.now) // flush snapshots/intents produced by the tick
			pump(h)
		}
		pump(h)
		free_all(context.temp_allocator)
	}
}

@(private = "file")
start_pair :: proc(t: ^testing.T, h: ^Net_Harness, host_arch: ar.Archetype_Id = .Warden, join_arch: ar.Archetype_Id = .Rogue) -> bool {
	host, join := h.apps[0], h.apps[1]
	ar.coop_open_menu(host)
	ar.net_test_pipe_next = &h.pipes[0]
	ar.coop_connect(host, .Host, h.now)
	for _ in 0 ..< 5 do frame(h)
	testing.expect_value(t, host.mode, ar.App_Mode.Coop_Lobby)
	code := ar.net_session_room_code(&host.coop.session)

	ar.coop_open_menu(join)
	ar.coop_field_set(&join.coop_ui, .Code, code)
	ar.net_test_pipe_next = &h.pipes[1]
	ar.coop_connect(join, .Join, h.now)
	ar.net_test_pipe_next = nil
	for _ in 0 ..< 5 do frame(h)
	testing.expect_value(t, join.mode, ar.App_Mode.Coop_Lobby)
	testing.expect(t, host.coop.session.seats[1].present, "host does not see the knock")
	testing.expect(t, !host.coop.session.seats[1].admitted)

	// Nobody starts before the host accepts.
	ar.net_session_select(&join.coop.session, join_arch)
	ar.net_session_ready(&join.coop.session, true)
	for _ in 0 ..< 3 do frame(h)
	testing.expect(t, !join.coop.session.seats[1].ready, "unadmitted joiner became ready")

	ar.net_session_admit(&host.coop.session)
	ar.net_session_select(&host.coop.session, host_arch)
	for _ in 0 ..< 3 do frame(h)
	ar.net_session_select(&join.coop.session, join_arch)
	ar.net_session_ready(&join.coop.session, true)
	ar.net_session_ready(&host.coop.session, true, 0xBEEF)
	for _ in 0 ..< 10 do frame(h)
	testing.expect_value(t, host.mode, ar.App_Mode.Playing)
	testing.expect_value(t, join.mode, ar.App_Mode.Playing)
	return host.mode == .Playing && join.mode == .Playing
}

@(test)
coop_net_lobby_start_and_checkpoint :: proc(t: ^testing.T) {
	h := harness_new()
	defer harness_free(h)
	if !start_pair(t, h, .Warden, .Ranger) do return
	host, join := h.apps[0], h.apps[1]
	testing.expect_value(t, host.run.player_count, 2)
	testing.expect_value(t, join.run.player_count, 2)
	testing.expect_value(t, join.run.local_slot, 1)
	testing.expect_value(t, join.run.players[1].archetype, ar.Archetype_Id.Ranger)
	testing.expect_value(t, join.run.seed, u64(0xBEEF))
	testing.expect(t, join.run.dungeon.tiles == host.run.dungeon.tiles, "joiner world differs from host")
	testing.expect_value(t, len(join.run.enemies), len(host.run.enemies))
	testing.expect(t, host.coop.h_joiner_synced, "host never saw the checkpoint ack")
	frame(h, 10)
	testing.expectf(t, join.coop.j_snapshots_applied > 0 && join.coop.j_snapshots_rejected == 0,
		"snapshots applied %v rejected %v", join.coop.j_snapshots_applied, join.coop.j_snapshots_rejected)
	// Co-op never claims the solo save identity.
	testing.expect_value(t, host.run.run_id, "")
	testing.expect_value(t, join.run.run_id, "")
}

@(test)
coop_net_joiner_movement_is_predicted_and_acknowledged :: proc(t: ^testing.T) {
	h := harness_new()
	defer harness_free(h)
	if !start_pair(t, h) do return
	host, join := h.apps[0], h.apps[1]
	for &e in host.run.enemies do e.hp = 0 // a quiet floor for exact movement
	frame(h, 3)
	start := host.run.players[1].pos
	join.move_input = {1, 0}
	frame(h, 40)
	join.move_input = {}
	frame(h, 20)
	moved := host.run.players[1].pos - start
	testing.expectf(t, linalg.length(moved) > 1.0, "host did not move the joiner seat: %v", moved)
	// After the stream settles, prediction and authority agree.
	gap := linalg.distance(host.run.players[1].pos, join.run.players[1].pos)
	testing.expectf(t, gap < 0.05, "joiner prediction diverged by %v tiles", gap)
	testing.expect(t, host.coop.h_resolved > 0)
	// The host seat on the joiner follows the host's authority.
	gap = linalg.distance(host.run.players[0].pos, join.run.players[0].pos)
	testing.expectf(t, gap < 0.05, "remote host seat diverged by %v", gap)
}

@(test)
coop_net_remote_actions_resolve_on_the_host :: proc(t: ^testing.T) {
	h := harness_new()
	defer harness_free(h)
	if !start_pair(t, h, .Warden, .Arcanist) do return
	host, join := h.apps[0], h.apps[1]
	mana := host.run.players[1].mana
	_ = ar.app_act(join, .Bolt, {1, 0})
	frame(h, 6)
	testing.expect(t, host.run.players[1].mana < mana, "remote bolt never spent the joiner's mana")
	frame(h, 4)
	// One snapshot of latency at most: regeneration keeps both moving.
	testing.expectf(t, abs(join.run.players[1].mana - host.run.players[1].mana) < .5, "joiner mana %v host %v", join.run.players[1].mana, host.run.players[1].mana)
	// Index actions carry a fingerprint: a stale view cannot drop another item.
	potion := host.run.players[1].heal_potions
	_ = ar.app_act(join, .Potion_Heal)
	host.run.players[1].hp = 1
	frame(h, 6)
	_ = potion
}

@(test)
coop_net_remote_descent_reaches_the_joiner_as_a_new_checkpoint :: proc(t: ^testing.T) {
	h := harness_new()
	defer harness_free(h)
	if !start_pair(t, h) do return
	host, join := h.apps[0], h.apps[1]
	epoch := host.run.floor_epoch
	ar.run_descend(&host.run)
	frame(h, 10)
	testing.expect(t, host.run.floor_epoch != epoch)
	testing.expect_value(t, join.run.floor_epoch, host.run.floor_epoch)
	testing.expect_value(t, join.run.depth, host.run.depth)
	testing.expect(t, join.run.dungeon.tiles == host.run.dungeon.tiles, "joiner kept the old floor")
}

@(test)
coop_net_partner_disconnect_holds_the_world :: proc(t: ^testing.T) {
	h := harness_new()
	defer harness_free(h)
	if !start_pair(t, h) do return
	host := h.apps[0]
	ticks := host.run.active_ticks
	// The joiner's socket drops without bye.
	h.pipes[1].closed = true
	rc.hub_closed(&h.hub, 2, h.now)
	h.opened[1] = false
	frame(h, 3)
	testing.expect(t, !host.coop.session.partner_connected)
	held := host.run.active_ticks
	frame(h, 20) // still inside the first 500 ms reconnect backoff
	testing.expect_value(t, host.run.active_ticks, held)
	testing.expect(t, held >= ticks)
}

// Every tuple layout round-trips exactly through the strict decoder.
@(test)
coop_net_snapshot_tuples_round_trip :: proc(t: ^testing.T) {
	app := new(ar.App)
	defer free(app)
	ar.app_init(app, 7)
	defer ar.profile_destroy(&app.profile)
	ar.run_start_coop(&app.run, 99, {.Ranger, .Acolyte}, .Hard)
	defer ar.run_destroy(&app.run)
	app.run.players[1].statuses[.Chilled] = 1.25
	app.run.players[1].gold = 77
	app.run.players[0].raise_charges = 3
	bytes := ar.coop_encode_snapshot(app, {seq = 5, ack = 3, slow = ~bit_set[ar.Coop_Slow_Section]{}}, context.temp_allocator)
	testing.expect_value(t, np.json_validate(bytes), np.Json_Error.None)
	obj, root, ok := np.json_parse_object(bytes, context.temp_allocator)
	testing.expect(t, ok)
	_ = root
	players, _ := np.read_array(obj, "p", 2)
	for slot in 0 ..< 2 {
		p: ar.Player = app.run.players[slot]
		p.gold = -1
		p.raise_charges = -1
		testing.expect(t, ar.coop_decode_player_fast(players[slot], &p), "player tuple rejected")
		testing.expect_value(t, p.gold, app.run.players[slot].gold)
		testing.expect_value(t, p.raise_charges, app.run.players[slot].raise_charges)
	}
	enemies, _ := np.read_array(obj, "e", 512)
	{
		pa, _ := players[0].(json.Array)
		ea, _ := enemies[0].(json.Array)
		testing.expectf(t, len(pa) == ar.PLAYER_FAST_FIELDS && len(ea) == ar.ENEMY_FAST_FIELDS, "tuple lengths player %v/%v enemy %v/%v", len(pa), ar.PLAYER_FAST_FIELDS, len(ea), ar.ENEMY_FAST_FIELDS)
	}
	testing.expect(t, len(enemies) > 0)
	for v, i in enemies {
		e: ar.Enemy
		arr, _ := v.(json.Array)
		testing.expectf(t, ar.coop_decode_enemy(arr, &e), "enemy tuple %v rejected", i)
	}
	// Every transient/actor list decodes, so one bad tuple can never silently
	// reject whole snapshots in play.
	append(&app.run.projectiles, ar.Projectile{pos = {5, 5}, vel = {1, 0}, from_player = true, owner_slot = 1, ttl = 1})
	append(&app.run.bells, ar.Ambush_Bell{pos = {6, 6}, lifetime = 3, owner_slot = 1})
	append(&app.run.numbers, ar.Damage_Number{pos = {4, 4}, value = 12, kind = .Text, text = "LEVEL UP!"})
	ar.feel_emit(&app.run, .Burst, {3, 3}, {1, 2, 3, 4}, .5, .7)
	app.run.players[1].mana = 100
	_ = ar.player_cast_spirit_call(&app.run, 1)
	sfx := []ar.Sfx_Event{{kind = .Play, bank = .Level_Up, pos = {1, 2}, spatial = true, emitter_id = 9}}
	full := ar.coop_encode_snapshot(app, {seq = 6, sfx = sfx, events = {.Open_Shop}}, context.temp_allocator)
	full_obj, _, full_ok := np.json_parse_object(full, context.temp_allocator)
	testing.expect(t, full_ok)
	lists := [?]struct{key: string, want_min: int}{{"pr", 1}, {"bl", 1}, {"nu", 1}, {"fe", 1}, {"sx", 1}, {"fa", 0}}
	for l in lists {
		arr, ok_arr := np.read_array(full_obj, l.key, 1024)
		testing.expectf(t, ok_arr && len(arr) >= l.want_min, "%s missing", l.key)
		for v in arr {
			item_ok := false
			switch l.key {
			case "pr": _, item_ok = ar.coop_decode_projectile(v)
			case "bl": _, item_ok = ar.coop_decode_bell(v)
			case "nu": _, item_ok = ar.coop_decode_number(v, proc(s: string) -> string {return s})
			case "fe": _, item_ok = ar.coop_decode_feel(v)
			case "sx": _, item_ok = ar.coop_decode_sfx(v)
			case "fa":
				f: ar.Familiar
				item_ok = ar.coop_decode_familiar(v, &f)
			}
			testing.expectf(t, item_ok, "%s tuple rejected", l.key)
		}
	}
	header, header_ok := ar.coop_decode_snapshot_header(obj)
	testing.expect(t, header_ok)
	testing.expect_value(t, header.seq, u64(5))
	testing.expect_value(t, header.ack, u32(3))
}

@(test)
coop_net_joiner_reconnects_with_its_token_and_resyncs :: proc(t: ^testing.T) {
	h := harness_new()
	defer harness_free(h)
	if !start_pair(t, h) do return
	host, join := h.apps[0], h.apps[1]
	frame(h, 5)
	// Socket drops without bye: relay holds the seat, both clients hold.
	h.pipes[1].closed = true
	rc.hub_closed(&h.hub, 2, h.now)
	h.opened[1] = false
	frame(h, 3)
	testing.expect_value(t, join.coop.session.phase, ar.Net_Session_Phase.Reconnecting)
	testing.expect(t, !host.coop.session.partner_connected)
	// Backoff retry reclaims the seat by token; the host sends a fresh baseline.
	for _ in 0 ..< 120 {
		frame(h)
		if join.mode == .Playing && host.coop.h_joiner_synced do break
	}
	testing.expect_value(t, join.coop.session.phase, ar.Net_Session_Phase.Active)
	testing.expect(t, host.coop.session.partner_connected, "host never saw the rejoin")
	testing.expect(t, host.coop.h_joiner_synced, "rejoined joiner never adopted a fresh checkpoint")
	testing.expect_value(t, join.mode, ar.App_Mode.Playing)
	ticks := host.run.active_ticks
	frame(h, 10)
	testing.expect(t, host.run.active_ticks > ticks, "world stayed held after the rejoin")
}

// 100/250 ms one-way latency with jitter: the guest's own movement stays
// responsive with small corrections, and the remote host seat moves without
// visible jumps on the guest's screen.
@(test)
coop_net_impaired_network_stays_smooth :: proc(t: ^testing.T) {
	for latency in ([]i64{50, 125}) {
		h := harness_new()
		defer harness_free(h)
		if !start_pair(t, h) do return
		host, join := h.apps[0], h.apps[1]
		for &e in host.run.enemies do e.hp = 0
		h.latency = latency
		h.jitter = 30
		frame(h, 30)
		join.coop.j_max_correction = 0
		// Both walk at once.
		join.move_input = {1, 0}
		host.move_input = {0, 1}
		max_step: f32 = 0
		last := join.run.players[0].pos
		for _ in 0 ..< 90 {
			frame(h)
			step := linalg.distance(join.run.players[0].pos, last)
			max_step = max(max_step, step)
			last = join.run.players[0].pos
		}
		join.move_input = {}
		host.move_input = {}
		frame(h, 60)
		testing.expectf(t, join.coop.j_max_correction < .15, "latency %v: guest correction %.3f tiles", latency, join.coop.j_max_correction)
		// Host walks ~0.047 tiles per tick; a smooth timeline never jumps.
		testing.expectf(t, max_step < .12, "latency %v: remote host seat jumped %.3f tiles in one tick", latency, max_step)
		gap := linalg.distance(host.run.players[1].pos, join.run.players[1].pos)
		testing.expectf(t, gap < .05, "latency %v: settled guest prediction gap %.3f", latency, gap)
		remote_gap := linalg.distance(host.run.players[0].pos, join.run.players[0].pos)
		testing.expectf(t, remote_gap < .05, "latency %v: settled remote seat gap %.3f", latency, remote_gap)
	}
}

// Realistic guest session: independent jittery tick timing on each client
// (frame hitches deliver 0-3 ticks per frame), latency with jitter, held
// movement into enemies (auto-melee plants), clicks, and periodic dashes.
// Measures what the guest actually sees of its own character.
@(private = "file")
Guest_Metrics :: struct {
	max_jump:      f32, // largest per-tick displacement of the guest's own seat
	big_jumps:     int, // ticks moving more than 2x walking speed without a dash
	corrections:   int, // reconciliations moving the seat more than 0.1 tiles
	max_correction: f32,
}

@(private = "file")
frame_jittered :: proc(h: ^Net_Harness, rng: ^u32) -> (host_ticks, join_ticks: int) {
	h.now += 16
	for i in 0 ..< 2 {
		app := h.apps[i]
		app.net_now_ms = h.now
		ar.coop_frame(app, h.now)
		ar.coop_update_screens(app)
		rng^ = rng^ * 1664525 + 1013904223
		r := (rng^ >> 16) % 10
		ticks := r == 0 ? 0 : (r == 1 ? 2 : 1) // hitch, catch-up, normal
		for _ in 0 ..< ticks do ar.app_tick(app)
		if i == 0 do host_ticks = ticks
		else do join_ticks = ticks
		ar.coop_frame(app, h.now)
		pump(h)
	}
	pump(h)
	free_all(context.temp_allocator)
	return
}

@(private = "file")
run_guest_session :: proc(t: ^testing.T, h: ^Net_Harness) -> (m: Guest_Metrics) {
	host, join := h.apps[0], h.apps[1]
	rng: u32 = 12345
	// Three enemies in the guest's path.
	guest := host.run.players[1].pos
	clear(&host.run.enemies)
	for k in 0 ..< 3 {
		e := ar.enemy_make(.Ghoul, guest + {2.5 + f32(k) * .6, f32(k) * .4 - .4}, 1)
		ar.enemy_ensure_id(&host.run, &e)
		append(&host.run.enemies, e)
	}
	for _ in 0 ..< 20 do frame_jittered(h, &rng)
	join.coop.j_max_correction = 0
	last := ar.local_player_render_pos(join, 1)
	dash_cooldown := 0
	for tick in 0 ..< 360 {
		join.move_input = tick % 120 < 90 ? ar.Vec2{1, 0} : ar.Vec2{-1, 0}
		dashed := false
		if tick % 97 == 50 {
			_ = ar.app_act(join, .Dash, join.move_input)
			dashed = true
			dash_cooldown = 8
		}
		if tick % 23 == 0 do join.mouse_press_pending, join.mouse_press_aim = true, ar.Vec2{1, 0}
		_, jt := frame_jittered(h, &rng)
		pos := ar.local_player_render_pos(join, 1) // what the guest sees
		jump := linalg.distance(pos, last)
		last = pos
		if dash_cooldown > 0 || dashed {
			dash_cooldown -= 1
			continue
		}
		per_tick := jump / f32(max(jt, 1))
		m.max_jump = max(m.max_jump, per_tick)
		if per_tick > .1 do m.big_jumps += 1
		if join.coop.j_last_correction > .1 {
			m.corrections += 1
			join.coop.j_last_correction = 0
		}
	}
	m.max_correction = join.coop.j_max_correction
	return
}

@(test)
coop_net_guest_combat_session_is_smooth :: proc(t: ^testing.T) {
	h := harness_new()
	defer harness_free(h)
	if !start_pair(t, h, .Warden, .Warden) do return
	h.latency = 40
	h.jitter = 25
	m := run_guest_session(t, h)
	testing.expectf(t, m.big_jumps <= 3, "guest seat jumped %v times (max %.3f tiles/tick)", m.big_jumps, m.max_jump)
	testing.expectf(t, m.corrections <= 4 && m.max_correction < .8, "%v corrections over 0.1 tiles (max %.3f)", m.corrections, m.max_correction)
	testing.expectf(t, m.max_jump < .2, "drawn guest seat moved %.3f tiles in one tick", m.max_jump)
}

