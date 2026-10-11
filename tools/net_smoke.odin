// Headless real-socket co-op smoke test: a host App and a joiner App in one
// process, each with its own libwebsockets connection to a running relay.
//
//   build/archrogue_relay --port 18765 &
//   odin run tools/net_smoke.odin -file -- ws://127.0.0.1:18765/mp
//
// Exits non-zero unless lobby, admission, start, checkpoint adoption, joiner
// movement, and acknowledgment all complete over the wire.
package main

import "core:fmt"
import "core:math/linalg"
import "core:os"
import "core:time"
import ar "../src"

main :: proc() {
	url := len(os.args) > 1 ? os.args[1] : "ws://127.0.0.1:18765/mp"
	apps: [2]^ar.App
	for i in 0 ..< 2 {
		apps[i] = new(ar.App)
		ar.app_init(apps[i], u64(77 + i))
		ar.coop_open_menu(apps[i])
		ar.coop_field_set(&apps[i].coop_ui, .Server, url)
	}
	host, join := apps[0], apps[1]
	start := time.tick_now()
	now :: proc(start: time.Tick) -> i64 {return i64(time.duration_milliseconds(time.tick_since(start)))}
	step :: proc(apps: [2]^ar.App, ms: i64) {
		for app in apps {
			app.net_now_ms = ms
			ar.coop_frame(app, ms)
			ar.coop_update_screens(app)
			ar.app_tick(app)
			ar.coop_frame(app, ms)
		}
		time.sleep(16 * time.Millisecond)
		free_all(context.temp_allocator)
	}
	wait :: proc(apps: [2]^ar.App, start: time.Tick, what: string, cond: proc(apps: [2]^ar.App) -> bool) {
		deadline := time.tick_now()
		for !cond(apps) {
			step(apps, i64(time.duration_milliseconds(time.tick_since(start))))
			if time.duration_seconds(time.tick_since(deadline)) > 8 {
				fmt.eprintfln("FAIL: timed out waiting for %s (host %v/%v, join %v/%v: %s %s)", what,
					apps[0].mode, apps[0].coop.session.phase, apps[1].mode, apps[1].coop.session.phase,
					ar.net_session_error(&apps[0].coop.session), ar.net_session_error(&apps[1].coop.session))
				os.exit(1)
			}
		}
		fmt.printfln("ok: %s", what)
	}

	ar.coop_connect(host, .Host, now(start))
	wait(apps, start, "host lobby", proc(a: [2]^ar.App) -> bool {return a[0].mode == .Coop_Lobby})
	code := ar.net_session_room_code(&host.coop.session)
	fmt.printfln("room %s", code)
	ar.coop_field_set(&join.coop_ui, .Code, code)
	ar.coop_connect(join, .Join, now(start))
	wait(apps, start, "joiner knock", proc(a: [2]^ar.App) -> bool {
		return a[1].mode == .Coop_Lobby && a[0].coop.session.seats[1].present
	})
	ar.net_session_admit(&host.coop.session)
	ar.net_session_select(&host.coop.session, .Warden)
	wait(apps, start, "admission", proc(a: [2]^ar.App) -> bool {return a[1].coop.session.seats[1].admitted})
	ar.net_session_select(&join.coop.session, .Ranger)
	ar.net_session_ready(&join.coop.session, true)
	ar.net_session_ready(&host.coop.session, true, 0x5EED)
	wait(apps, start, "both playing", proc(a: [2]^ar.App) -> bool {return a[0].mode == .Playing && a[1].mode == .Playing})
	if join.run.dungeon.tiles != host.run.dungeon.tiles {
		fmt.eprintln("FAIL: joiner floor differs")
		os.exit(1)
	}
	for &e in host.run.enemies do e.hp = 0
	before := host.run.players[1].pos
	join.move_input = {0, 1}
	for _ in 0 ..< 60 do step(apps, now(start))
	join.move_input = {}
	for _ in 0 ..< 40 do step(apps, now(start))
	moved := linalg.distance(before, host.run.players[1].pos)
	gap := linalg.distance(host.run.players[1].pos, join.run.players[1].pos)
	fmt.printfln("joiner moved %.2f tiles on the host; prediction gap %.3f; snapshots applied %v rejected %v; rtt %v ms",
		moved, gap, join.coop.j_snapshots_applied, join.coop.j_snapshots_rejected, join.coop.session.rtt_ms)
	if moved < 0.5 || gap > 0.1 || join.coop.j_snapshots_rejected > 0 {
		fmt.eprintln("FAIL: movement did not synchronize")
		os.exit(1)
	}
	ar.coop_leave(join)
	ar.coop_leave(host)
	fmt.println("PASS")
}
