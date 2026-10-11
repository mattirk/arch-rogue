// Headless co-op client bot for automated multi-process soak testing. Runs the
// real client code (session, sync, prediction) with a real-time frame loop and
// real libwebsockets sockets, in its own process, exactly one role per process.
//
//   build/coop_bot --role host --url ws://127.0.0.1:8765/mp --code-file /tmp/code --seconds 20
//   build/coop_bot --role join --url ws://127.0.0.1:8765/mp --code-file /tmp/code --seconds 20
//
// Options: --fps N (frame cadence; ticks still run at 60 Hz through the same
// accumulator as the game), --script idle|walk|combat, --drop-at SECONDS
// (joiner only: force-close the socket once to exercise reconnect),
// --archetype NAME. Prints one "RESULT {...}" line and exits non-zero when
// the session failed, dropped without being asked to, or rejected data.
package main

import "core:fmt"
import "core:math/linalg"
import "core:os"
import "core:strconv"
import "core:strings"
import "core:time"
import ar "../src"

Options :: struct {
	role:      ar.Coop_Role,
	url:       string,
	code_file: string,
	seconds:   f64,
	fps:       f64,
	script:    string,
	drop_at:   f64,
	archetype: ar.Archetype_Id,
}

main :: proc() {
	opts := Options{role = .Host, url = "ws://127.0.0.1:8765/mp", code_file = "build/coop-soak/code", seconds = 15, fps = 60, script = "combat", drop_at = -1, archetype = .Warden}
	args := os.args[1:]
	for i := 0; i < len(args); i += 1 {
		next :: proc(args: []string, i: ^int) -> string {
			i^ += 1
			if i^ >= len(args) {fmt.eprintln("missing value"); os.exit(2)}
			return args[i^]
		}
		switch args[i] {
		case "--role":
			v := next(args, &i)
			opts.role = v == "join" ? .Join : .Host
		case "--url": opts.url = next(args, &i)
		case "--code-file": opts.code_file = next(args, &i)
		case "--seconds": opts.seconds, _ = strconv.parse_f64(next(args, &i))
		case "--fps": opts.fps, _ = strconv.parse_f64(next(args, &i))
		case "--script": opts.script = next(args, &i)
		case "--drop-at": opts.drop_at, _ = strconv.parse_f64(next(args, &i))
		case "--archetype":
			v := strings.to_lower(next(args, &i), context.temp_allocator)
			for id in ar.Archetype_Id do if strings.to_lower(ar.ARCHETYPES[id].name, context.temp_allocator) == v do opts.archetype = id
		case: fmt.eprintln("unknown option", args[i]); os.exit(2)
		}
	}
	os.exit(run_bot(opts))
}

Bot :: struct {
	app:        ^ar.App,
	opts:       Options,
	start:      time.Tick,
	accumulator: f64,
	last_frame: f64,
	// metrics
	frames:         int,
	ticks:          int,
	disconnects:    int,
	reconnects:     int,
	max_correction: f32,
	max_drawn_jump: f32,
	last_drawn:     ar.Vec2,
	drawn_valid:    bool,
	explored_before_drop: int,
	explored_after_drop:  int,
	dropped:        bool,
	admitted:       bool,
	readied:        bool,
	code_written:   bool,
	play_started:   f64,
	just_dashed:    bool,
	admitted_gen:   i64,
	last_report_s:  int,
	checkpoints_seen: int,
	archers_spawned: bool,
	max_proj_jerk:  f32, // per-tick deviation of a shot from its own velocity
	proj_last:      map[u64]ar.Vec2,
}

now_ms :: proc(b: ^Bot) -> i64 {return i64(time.duration_milliseconds(time.tick_since(b.start)))}
elapsed_s :: proc(b: ^Bot) -> f64 {return time.duration_seconds(time.tick_since(b.start))}

log :: proc(b: ^Bot, format: string, args: ..any) {
	fmt.eprintf("[%s %6.2f] ", b.opts.role == .Host ? "host" : "join", elapsed_s(b))
	fmt.eprintfln(format, ..args)
}

count_explored :: proc(run: ^ar.Run) -> int {
	n := 0
	for x in 0 ..< ar.MAP_W do for y in 0 ..< ar.MAP_H do if run.explored[x][y] do n += 1
	return n
}

// Mirrors game_frame: network pump once per frame before input, then the
// fixed-step accumulator drives app_tick.
frame :: proc(b: ^Bot) {
	app := b.app
	t := elapsed_s(b)
	dt := b.last_frame == 0 ? 1.0 / 60 : min(t - b.last_frame, 0.25)
	b.last_frame = t
	app.net_now_ms = now_ms(b)
	phase_before := app.coop.session.phase
	ar.coop_frame(app, app.net_now_ms)
	ar.coop_update_screens(app)
	phase_after := app.coop.session.phase
	if phase_before != .Reconnecting && phase_after == .Reconnecting {
		b.disconnects += 1
		log(b, "connection lost (%s)", ar.net_session_error(&app.coop.session))
	}
	if phase_before == .Reconnecting && phase_after == .Active {
		b.reconnects += 1
		log(b, "reconnected")
	}
	b.accumulator += dt
	for b.accumulator >= ar.SIM_DT {
		b.accumulator -= ar.SIM_DT
		drive(b)
		ar.app_tick(app)
		b.ticks += 1
		if app.mode == .Playing && app.coop.role == .Join && app.coop.j_have_world {
			b.max_correction = max(b.max_correction, app.coop.j_last_correction)
			drawn := ar.local_player_render_pos(app, 1)
			resynced := app.coop.j_checkpoints_adopted != b.checkpoints_seen
			b.checkpoints_seen = app.coop.j_checkpoints_adopted
			if b.drawn_valid && app.coop.session.phase == .Active && !resynced {
				jump := linalg.distance(drawn, b.last_drawn)
				if jump > .3 && !b.just_dashed {
					p := &app.run.players[app.run.local_slot]
					log(b, "JUMP %.3f tiles: tick %d from %v to %v (pos %v prev %v offset %v corr %.3f ack-lag %d dash_pending %v hp %d)",
						jump, b.ticks, b.last_drawn, drawn, p.pos, p.prev_pos, app.coop.j_visual_offset, app.coop.j_last_correction,
						app.coop.j_cmd_seq, app.coop.j_pending_dash, p.hp)
				}
				if jump > b.max_drawn_jump && !b.just_dashed do b.max_drawn_jump = jump
			}
			b.last_drawn = drawn
			b.drawn_valid = true
			b.just_dashed = false
			// Projectile smoothness: each shot should move by vel*dt per tick.
			// A tick where every shot stood still is the host's hitstop (whole
			// world frozen), replicated on purpose; skip it.
			if app.coop.session.phase == .Active {
				// A shot flying at (near) full speed this tick proves world time
				// ran normally; without one, a slowdown is the host's hitstop
				// smeared across interpolation and not a per-shot stutter.
				any_moved := false
				for &p in app.run.projectiles {
					if last, seen := b.proj_last[p.entity_id]; seen && !p.hidden {
						expected := linalg.length(p.vel) * ar.SIM_DT
						if expected > 0 && linalg.distance(p.pos, last) >= expected * .9 do any_moved = true
					}
				}
				for &p in app.run.projectiles {
					if p.hidden {
						delete_key(&b.proj_last, p.entity_id) // a hidden shot has no visible history
						continue
					}
					if !any_moved {
						b.proj_last[p.entity_id] = p.pos
						continue
					}
					if last, seen := b.proj_last[p.entity_id]; seen {
						expected := last + p.vel * ar.SIM_DT
						jerk := linalg.distance(p.pos, expected)
						if jerk > .08 && linalg.distance(p.pos, last) < 2 {
							ip := &app.coop.j_interp
							log(b, "PJERK %.3f id %d player %v homing %.2f vel %v moved %.3f render %.0f newest %.0f age %.2f", jerk, p.entity_id, p.from_player, p.homing, p.vel, linalg.distance(p.pos, last), ip.render_ms, ip.samples[ip.head].host_ms, p.visual_age)
						}
						if jerk > b.max_proj_jerk && linalg.distance(p.pos, last) < 2 do b.max_proj_jerk = jerk
					}
					b.proj_last[p.entity_id] = p.pos
				}
			}
		}
	}
	b.frames += 1
	if int(t) != b.last_report_s && app.mode == .Playing {
		b.last_report_s = int(t)
		s := &app.coop.session
		pc, pb := ar.net_transport_pending(&s.transport)
		if b.opts.role == .Join {
			ip := &app.coop.j_interp
			log(b, "rtt %d ms | snap age %d ms transit +%.0f spread %.0f delay %.0f | inbox %d | pending %d msgs %d B | out %d B | ok %d rej %d | corr %.3f offset %.3f",
				s.rtt_ms, app.net_now_ms - app.coop.j_last_snapshot_ms, ip.last_transit_ms, ip.jitter_ms, ip.delay_ms, len(s.inbox), pc, pb, ar.net_transport_outbound_bytes(&s.transport),
				app.coop.j_snapshots_applied, app.coop.j_snapshots_rejected, app.coop.j_last_correction, linalg.length(app.coop.j_visual_offset))
		} else {
			log(b, "rtt %d ms | queued steps %d | starved %d trimmed %d | inbox %d | pending %d msgs | out %d B | synced %v",
				s.rtt_ms, len(app.coop.h_cmds), app.coop.h_starved, app.coop.h_trimmed, len(s.inbox), pc, ar.net_transport_outbound_bytes(&s.transport), app.coop.h_joiner_synced)
		}
	}
	free_all(context.temp_allocator)
}

// Scripted play on the local seat.
drive :: proc(b: ^Bot) {
	app := b.app
	if app.mode != .Playing do return
	if b.play_started == 0 do b.play_started = elapsed_s(b)
	// Host: ranged enemies near the pair so projectiles cross the wire.
	if b.opts.role == .Host && !b.archers_spawned && app.coop.h_joiner_synced {
		b.archers_spawned = true
		anchor := app.run.players[1].pos
		for k in 0 ..< 3 {
			e := ar.enemy_make(.Grave_Archer, anchor + {4 + f32(k), f32(k) * 1.5 - 1.5}, 1)
			e.hp, e.max_hp = 400, 400
			ar.enemy_ensure_id(&app.run, &e)
			append(&app.run.enemies, e)
		}
	}
	since := elapsed_s(b) - b.play_started
	tick := b.ticks
	switch b.opts.script {
	case "idle":
		app.move_input = {}
	case "walk":
		app.move_input = tick % 240 < 180 ? ar.Vec2{1, 0} : ar.Vec2{-1, 0}
	case "combat":
		app.move_input = tick % 180 < 120 ? ar.Vec2{1, .3} : ar.Vec2{-1, -.3}
		app.aim_input = app.move_input
		app.aim_live = true
		if tick % 45 == 0 {
			app.mouse_press_pending = true
			app.mouse_press_aim = app.move_input
		}
		if tick % 150 == 75 && since > 1 {
			_ = ar.app_act(app, .Dash, app.move_input)
			b.just_dashed = true
		}
		if tick % 300 == 200 do _ = ar.app_act(app, .Bolt, app.move_input)
	}
	// Forced socket loss (joiner): the relay must hold the seat and the
	// client must reclaim it; fog must survive the fresh checkpoint.
	if b.opts.drop_at >= 0 && !b.dropped && since >= b.opts.drop_at {
		b.dropped = true
		b.explored_before_drop = count_explored(&app.run)
		log(b, "forcing socket close (explored %d tiles)", b.explored_before_drop)
		ar.net_transport_close(&app.coop.session.transport)
	}
	if b.dropped && b.explored_after_drop == 0 && app.coop.session.phase == .Active && app.coop.j_have_world && b.reconnects > 0 {
		b.explored_after_drop = count_explored(&app.run)
		log(b, "after reconnect: explored %d tiles", b.explored_after_drop)
	}
}

run_bot :: proc(opts: Options) -> int {
	b := new(Bot)
	b.opts = opts
	b.start = time.tick_now()
	app := new(ar.App)
	b.app = app
	ar.app_init(app, u64(opts.role == .Host ? 11 : 22))
	ar.coop_open_menu(app)
	ar.coop_field_set(&app.coop_ui, .Server, opts.url)
	ar.coop_field_set(&app.coop_ui, .Name, opts.role == .Host ? "HostBot" : "JoinBot")
	app.coop_ui.select_index = int(opts.archetype)
	frame_period := 1.0 / max(opts.fps, 1)

	if opts.role == .Host {
		ar.coop_connect(app, .Host, now_ms(b))
	} else {
		// Wait for the host to publish its code.
		deadline := time.tick_now()
		code := ""
		for code == "" {
			if data, err := os.read_entire_file(opts.code_file, context.temp_allocator); err == nil do code = strings.trim_space(string(data))
			if code != "" do break
			if time.duration_seconds(time.tick_since(deadline)) > 15 {
				log(b, "no room code appeared at %s", opts.code_file)
				return 3
			}
			time.sleep(50 * time.Millisecond)
		}
		ar.coop_field_set(&app.coop_ui, .Code, code)
		ar.coop_connect(app, .Join, now_ms(b))
	}

	failed := false
	for elapsed_s(b) < opts.seconds {
		frame(b)
		s := &app.coop.session
		if opts.role == .Host {
			if app.mode == .Coop_Lobby && !b.code_written {
				_ = os.write_entire_file(opts.code_file, transmute([]byte)ar.net_session_room_code(s))
				b.code_written = true
				log(b, "room %s", ar.net_session_room_code(s))
			}
			if app.mode == .Coop_Lobby && s.lobby_phase == .Admission && s.seat_gen != b.admitted_gen {
				ar.net_session_admit(s) // once per knock; a repeat would be a relay rejection
				b.admitted_gen = s.seat_gen
			}
			if app.mode == .Coop_Lobby && s.lobby_phase == .Selecting && !b.readied {
				ar.net_session_select(s, opts.archetype)
				ar.net_session_ready(s, true, 0xBEEF)
				b.readied = true
			}
		} else if app.mode == .Coop_Lobby && s.seats[1].admitted && !b.readied {
			ar.net_session_select(s, opts.archetype)
			ar.net_session_ready(s, true)
			b.readied = true
		}
		if s.phase == .Failed || app.mode == .Coop_Menu && app.coop.role == .None {
			log(b, "session failed: %s", app.coop_ui.message)
			failed = true
			break
		}
		// Pace the frame loop like a vsynced game.
		target := f64(b.frames) * frame_period
		for elapsed_s(b) < target do time.sleep(time.Duration(0.5 * f64(time.Millisecond)))
	}

	c := &app.coop
	played := b.play_started > 0 ? elapsed_s(b) - b.play_started : 0
	pos := app.run.player_count == 2 ? app.run.players[app.run.local_slot].pos : ar.Vec2{}
	partner := app.run.player_count == 2 ? app.run.players[1 - app.run.local_slot].pos : ar.Vec2{}
	fmt.printfln("RESULT {{\"role\":\"%s\",\"failed\":%v,\"played_s\":%.1f,\"frames\":%d,\"ticks\":%d,\"disconnects\":%d,\"reconnects\":%d,\"snapshots_ok\":%d,\"snapshots_rejected\":%d,\"max_correction\":%.3f,\"max_drawn_jump\":%.3f,\"max_proj_jerk\":%.3f,\"rtt_ms\":%d,\"snapshot_bytes\":%d,\"snapshot_age_ms\":%d,\"starved\":%d,\"trimmed\":%d,\"explored_before_drop\":%d,\"explored_after_drop\":%d,\"pos\":[%.2f,%.2f],\"partner\":[%.2f,%.2f],\"hp\":%d,\"partner_hp\":%d,\"enemies\":%d}}",
		opts.role == .Host ? "host" : "join", failed, played, b.frames, b.ticks, b.disconnects, b.reconnects,
		c.j_snapshots_applied, c.j_snapshots_rejected, b.max_correction, b.max_drawn_jump, b.max_proj_jerk, c.session.rtt_ms, c.j_snapshot_bytes, c.j_last_snapshot_ms > 0 ? app.net_now_ms - c.j_last_snapshot_ms : 0,
		c.h_starved, c.h_trimmed, b.explored_before_drop, b.explored_after_drop, pos.x, pos.y, partner.x, partner.y,
		app.run.player_count == 2 ? app.run.players[app.run.local_slot].hp : 0,
		app.run.player_count == 2 ? app.run.players[1 - app.run.local_slot].hp : 0, len(app.run.enemies))
	expected_drops := opts.drop_at >= 0 ? 1 : 0
	status := 0
	if failed do status = 1
	if played < opts.seconds * 0.5 {log(b, "FAIL: played only %.1f s", played); status = 1}
	if b.disconnects > expected_drops {log(b, "FAIL: %d unexpected disconnects", b.disconnects - expected_drops); status = 1}
	if b.dropped && b.reconnects == 0 {log(b, "FAIL: never reconnected after the forced drop"); status = 1}
	if b.dropped && b.explored_after_drop < b.explored_before_drop {log(b, "FAIL: fog lost on reconnect (%d -> %d)", b.explored_before_drop, b.explored_after_drop); status = 1}
	if c.j_snapshots_rejected > 0 {log(b, "FAIL: %d snapshots rejected", c.j_snapshots_rejected); status = 1}
	if opts.role == .Join && b.max_proj_jerk > .1 {log(b, "FAIL: projectile stutter %.3f tiles/tick", b.max_proj_jerk); status = 1}
	if opts.role == .Join && b.max_drawn_jump > .25 {log(b, "FAIL: drawn seat jumped %.3f tiles in one tick", b.max_drawn_jump); status = 1}
	ar.coop_leave(app)
	return status
}
