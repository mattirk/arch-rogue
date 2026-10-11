package relay_core

import "core:testing"
import np "../../../src/net_protocol"

GAME :: "6.0.0-test"

// Thread-local: the runner executes tests in parallel and a shared counter
// could hand two rooms the same fake token.
@(private="file")
@(thread_local)
random_counter: u8

@(private="file")
fake_random :: proc(buf: []byte) {
	for &b in buf {
		random_counter += 1
		b = random_counter
	}
}

@(private="file")
Harness :: struct {
	hub: Hub,
	now: i64,
	seq: [64]i64,
}

@(private="file")
harness_init :: proc(h: ^Harness, config := DEFAULT_CONFIG) {
	random_counter = 0
	hub_init(&h.hub, config, fake_random)
	h.now = 1_000
}

@(private="file")
harness_destroy :: proc(h: ^Harness) {
	hub_destroy(&h.hub)
}

@(private="file")
next_seq :: proc(h: ^Harness, c: Conn_Id) -> i64 {
	h.seq[c] += 1
	return h.seq[c]
}

@(private="file")
send_msg :: proc(h: ^Harness, c: Conn_Id, msg: np.Message) {
	bytes := np.encode(msg, context.temp_allocator)
	hub_receive(&h.hub, c, bytes, h.now)
}

@(private="file")
send_text :: proc(h: ^Harness, c: Conn_Id, text: string) {
	hub_receive(&h.hub, c, transmute([]byte)text, h.now)
}

// Decoded outbound control messages for one connection since the last drain.
@(private="file")
Drained :: struct {
	msgs:   [dynamic]np.Message,
	raw:    [dynamic]string,
	closed: bool,
	code:   int,
}

@(private="file")
drain :: proc(h: ^Harness, c: Conn_Id) -> (d: Drained) {
	d.msgs = make([dynamic]np.Message, context.temp_allocator)
	d.raw = make([dynamic]string, context.temp_allocator)
	keep := make([dynamic]Action, context.temp_allocator)
	for a in h.hub.out {
		if a.conn != c {
			append(&keep, a)
			continue
		}
		switch a.kind {
		case .Send:
			text := string(a.data)
			append(&d.raw, clone_tmp(text))
			msg, _, err := np.decode_control(a.data, context.temp_allocator)
			if err == .None do append(&d.msgs, msg)
			delete(a.data)
		case .Close:
			d.closed = true
			d.code = a.close_code
		}
	}
	clear(&h.hub.out)
	for a in keep do append(&h.hub.out, a)
	return
}

@(private="file")
clone_tmp :: proc(s: string) -> string {
	b := make([]byte, len(s), context.temp_allocator)
	copy(b, s)
	return string(b)
}

@(private="file")
find :: proc(d: Drained, $T: typeid) -> (T, bool) {
	#reverse for m in d.msgs do if v, ok := m.(T); ok do return v, true
	return {}, false
}

@(private="file")
open_hello :: proc(h: ^Harness, c: Conn_Id, role: np.Role, room: string, token := "", game := GAME, name := "") -> Drained {
	hub_open(&h.hub, c, h.now)
	send_msg(h, c, np.Hello{
		seq = next_seq(h, c),
		protocol = np.PROTOCOL_VERSION,
		game = game,
		name = name != "" ? name : (role == .Host ? "Host" : "Guest"),
		room = room,
		role = role,
		token = token,
	})
	return drain(h, c)
}

// Host 1 creates ABCD, joiner 2 knocks and is admitted, both pick archetypes.
@(private="file")
setup_selecting :: proc(t: ^testing.T, h: ^Harness) -> (host_token, join_token: string) {
	d := open_hello(h, 1, .Host, "abcd")
	w, ok := find(d, np.Welcome)
	testing.expect(t, ok)
	host_token = clone_tmp(w.token)
	d = open_hello(h, 2, .Join, "ABCD")
	w, ok = find(d, np.Welcome)
	testing.expect(t, ok)
	join_token = clone_tmp(w.token)
	lobby, _ := find(drain(h, 1), np.Lobby)
	testing.expect_value(t, lobby.phase, np.Lobby_Phase.Admission)
	send_msg(h, 1, np.Admit{seq = next_seq(h, 1), seat_gen = lobby.seat_gen})
	send_msg(h, 1, np.Select{seq = next_seq(h, 1), archetype = "warden"})
	send_msg(h, 2, np.Select{seq = next_seq(h, 2), archetype = "warden"})
	_ = drain(h, 1)
	_ = drain(h, 2)
	return
}

@(private="file")
start_run :: proc(t: ^testing.T, h: ^Harness) -> (host_token, join_token: string) {
	host_token, join_token = setup_selecting(t, h)
	send_msg(h, 1, np.Ready{seq = next_seq(h, 1), ready = true, seed = 42})
	send_msg(h, 2, np.Ready{seq = next_seq(h, 2), ready = true})
	s1, ok1 := find(drain(h, 1), np.Start)
	s2, ok2 := find(drain(h, 2), np.Start)
	testing.expect(t, ok1 && ok2)
	testing.expect_value(t, s1.seed, u64(42))
	testing.expect_value(t, s2.session, s1.session)
	testing.expect_value(t, s2.join_archetype, "warden")
	return
}

@(test)
relay_full_lobby_flow_starts_once :: proc(t: ^testing.T) {
	h: Harness
	harness_init(&h)
	defer harness_destroy(&h)
	start_run(t, &h)
	testing.expect_value(t, h.hub.rooms["ABCD"].phase, np.Lobby_Phase.Active)
	// Ready after start is a state error, not a second start.
	send_msg(&h, 2, np.Ready{seq = next_seq(&h, 2), ready = true})
	d := drain(&h, 2)
	_, started := find(d, np.Start)
	testing.expect(t, !started)
	e, _ := find(d, np.Error)
	testing.expect_value(t, e.code, np.Error_Code.Bad_State)
	testing.expect(t, !e.fatal)
}

@(test)
relay_admission_is_enforced_before_readiness :: proc(t: ^testing.T) {
	h: Harness
	harness_init(&h)
	defer harness_destroy(&h)
	_ = open_hello(&h, 1, .Host, "ABCD")
	_ = open_hello(&h, 2, .Join, "ABCD")
	_ = drain(&h, 1)
	// Unadmitted joiner cannot select or ready; host cannot ready either.
	send_msg(&h, 2, np.Select{seq = next_seq(&h, 2), archetype = "rogue"})
	e, _ := find(drain(&h, 2), np.Error)
	testing.expect_value(t, e.code, np.Error_Code.Bad_State)
	send_msg(&h, 1, np.Select{seq = next_seq(&h, 1), archetype = "rogue"})
	send_msg(&h, 1, np.Ready{seq = next_seq(&h, 1), ready = true, seed = 9})
	e, _ = find(drain(&h, 1), np.Error)
	testing.expect_value(t, e.code, np.Error_Code.Bad_State)
	// Stale seat generation cannot admit.
	send_msg(&h, 1, np.Admit{seq = next_seq(&h, 1), seat_gen = 99})
	e, _ = find(drain(&h, 1), np.Error)
	testing.expect_value(t, e.code, np.Error_Code.Bad_State)
	testing.expect_value(t, h.hub.rooms["ABCD"].phase, np.Lobby_Phase.Admission)
}

// Legacy defect: a replacement joiner inherited stale host readiness and
// bypassed a fresh Accept.
@(test)
relay_kick_reopens_code_and_requires_fresh_consent :: proc(t: ^testing.T) {
	h: Harness
	harness_init(&h)
	defer harness_destroy(&h)
	_, join_token := setup_selecting(t, &h)
	send_msg(&h, 1, np.Ready{seq = next_seq(&h, 1), ready = true, seed = 5})
	_ = drain(&h, 1)
	room := h.hub.rooms["ABCD"]
	send_msg(&h, 1, np.Kick{seq = next_seq(&h, 1), seat_gen = room.seat_gen})
	d2 := drain(&h, 2)
	e, _ := find(d2, np.Error)
	testing.expect_value(t, e.code, np.Error_Code.Kicked)
	testing.expect(t, e.fatal && d2.closed)
	d1 := drain(&h, 1)
	left, has_left := find(d1, np.Partner_Left)
	testing.expect(t, has_left)
	testing.expect_value(t, left.reason, "kicked")
	lobby, _ := find(d1, np.Lobby)
	testing.expect_value(t, lobby.phase, np.Lobby_Phase.Waiting)
	testing.expect(t, !lobby.host.ready)
	hub_closed(&h.hub, 2, h.now)

	// The kicked token cannot reclaim.
	d := open_hello(&h, 3, .Join, "ABCD", token = join_token)
	e, _ = find(d, np.Error)
	testing.expect_value(t, e.code, np.Error_Code.Run_Not_Found)
	hub_closed(&h.hub, 3, h.now)

	// A fresh stranger gets a new seat generation and needs a new Accept.
	_ = open_hello(&h, 4, .Join, "ABCD")
	lobby, _ = find(drain(&h, 1), np.Lobby)
	testing.expect_value(t, lobby.phase, np.Lobby_Phase.Admission)
	testing.expect(t, lobby.seat_gen == 2)
	testing.expect(t, !lobby.host.ready && !lobby.join.admitted)
	send_msg(&h, 4, np.Select{seq = next_seq(&h, 4), archetype = "rogue"})
	e, _ = find(drain(&h, 4), np.Error)
	testing.expect_value(t, e.code, np.Error_Code.Bad_State)
}

@(test)
relay_rejects_mismatched_release_and_protocol :: proc(t: ^testing.T) {
	h: Harness
	harness_init(&h)
	defer harness_destroy(&h)
	_ = open_hello(&h, 1, .Host, "ABCD")
	d := open_hello(&h, 2, .Join, "ABCD", game = "6.0.0-other")
	e, _ := find(d, np.Error)
	testing.expect_value(t, e.code, np.Error_Code.Bad_Revision)
	testing.expect(t, e.fatal && d.closed)
	testing.expect_value(t, h.hub.rooms["ABCD"].phase, np.Lobby_Phase.Waiting)

	hub_open(&h.hub, 3, h.now)
	send_msg(&h, 3, np.Hello{seq = 1, protocol = 3, game = GAME, name = "x", room = "WXYZ", role = .Host})
	d = drain(&h, 3)
	e, _ = find(d, np.Error)
	testing.expect_value(t, e.code, np.Error_Code.Bad_Version)
	testing.expect_value(t, len(h.hub.rooms), 1)
}

@(test)
relay_hello_rules :: proc(t: ^testing.T) {
	h: Harness
	harness_init(&h)
	defer harness_destroy(&h)
	// First message must be hello.
	hub_open(&h.hub, 1, h.now)
	send_msg(&h, 1, np.Ping{seq = 1, ts = 1})
	d := drain(&h, 1)
	e, _ := find(d, np.Error)
	testing.expect(t, e.fatal && d.closed)
	// Malformed JSON before hello is fatal, without a panic.
	hub_open(&h.hub, 2, h.now)
	send_text(&h, 2, `{"t":"hello","seq":1,"seq":2}`)
	d = drain(&h, 2)
	testing.expect(t, d.closed)
	// A second hello is rejected explicitly but non-fatally.
	_ = open_hello(&h, 3, .Host, "ABCD")
	send_msg(&h, 3, np.Hello{seq = 50, protocol = 4, game = GAME, name = "x", room = "ABCD", role = .Host})
	d = drain(&h, 3)
	e, _ = find(d, np.Error)
	testing.expect_value(t, e.code, np.Error_Code.Bad_State)
	testing.expect(t, !e.fatal && !d.closed)
	// Code collision and joiner to a missing room.
	d = open_hello(&h, 4, .Host, "ABCD")
	e, _ = find(d, np.Error)
	testing.expect_value(t, e.code, np.Error_Code.Run_Id_In_Use)
	d = open_hello(&h, 5, .Join, "ZZZZ")
	e, _ = find(d, np.Error)
	testing.expect_value(t, e.code, np.Error_Code.Run_Not_Found)
	d = open_hello(&h, 6, .Join, "AB0D")
	e, _ = find(d, np.Error)
	testing.expect_value(t, e.code, np.Error_Code.Run_Not_Found)
	// Hello timeout.
	hub_open(&h.hub, 7, h.now)
	h.now += np.HELLO_TIMEOUT_MS + 1
	hub_tick(&h.hub, h.now)
	d = drain(&h, 7)
	e, _ = find(d, np.Error)
	testing.expect_value(t, e.code, np.Error_Code.Timeout)
}

@(test)
relay_room_cap_is_server_full :: proc(t: ^testing.T) {
	h: Harness
	cfg := DEFAULT_CONFIG
	cfg.max_rooms = 1
	harness_init(&h, cfg)
	defer harness_destroy(&h)
	_ = open_hello(&h, 1, .Host, "ABCD")
	d := open_hello(&h, 2, .Host, "WXYZ")
	e, _ := find(d, np.Error)
	testing.expect_value(t, e.code, np.Error_Code.Server_Full)
}

@(test)
relay_sequence_must_increase :: proc(t: ^testing.T) {
	h: Harness
	harness_init(&h)
	defer harness_destroy(&h)
	_ = open_hello(&h, 1, .Host, "ABCD")
	send_msg(&h, 1, np.Ping{seq = 5, ts = 1})
	send_msg(&h, 1, np.Ping{seq = 5, ts = 2})
	d := drain(&h, 1)
	_, ponged := find(d, np.Pong)
	e, _ := find(d, np.Error)
	testing.expect(t, ponged)
	testing.expect_value(t, e.code, np.Error_Code.Bad_Msg)
}

@(test)
relay_reconnect_within_grace_reclaims_and_supersedes :: proc(t: ^testing.T) {
	h: Harness
	harness_init(&h)
	defer harness_destroy(&h)
	_, join_token := start_run(t, &h)
	hub_closed(&h.hub, 2, h.now)
	pd, ok := find(drain(&h, 1), np.Partner_Disconnected)
	testing.expect(t, ok)
	testing.expect_value(t, pd.grace_ms, i64(np.RECONNECT_GRACE_MS))

	h.now += 10_000
	d := open_hello(&h, 3, .Join, "ABCD", token = join_token)
	w, welcomed := find(d, np.Welcome)
	testing.expect(t, welcomed && w.resumed)
	testing.expect_value(t, w.phase, np.Lobby_Phase.Active)
	_, rejoined := find(drain(&h, 1), np.Partner_Rejoined)
	testing.expect(t, rejoined)

	// A zombie: reclaim while the transport still believes conn 3 is alive.
	d = open_hello(&h, 4, .Join, "ABCD", token = join_token)
	_, welcomed = find(d, np.Welcome)
	testing.expect(t, welcomed)
	d3 := drain(&h, 3)
	testing.expect(t, d3.closed && d3.code == CLOSE_SUPERSEDED)
	// The superseded socket's late close must not disconnect the replacement.
	hub_closed(&h.hub, 3, h.now)
	_, disconnected := find(drain(&h, 1), np.Partner_Disconnected)
	testing.expect(t, !disconnected)
	testing.expect(t, h.hub.rooms["ABCD"].seats[.Join].connected)
	// Role spoofing with a valid token is refused.
	d = open_hello(&h, 5, .Host, "ABCD", token = join_token)
	e, _ := find(d, np.Error)
	testing.expect_value(t, e.code, np.Error_Code.Run_Not_Found)
}

@(test)
relay_grace_expiry_ends_active_run :: proc(t: ^testing.T) {
	h: Harness
	harness_init(&h)
	defer harness_destroy(&h)
	_, join_token := start_run(t, &h)
	hub_closed(&h.hub, 2, h.now)
	_ = drain(&h, 1)
	h.now += np.RECONNECT_GRACE_MS + 1
	// Expiry is validated during reclaim, not only by the periodic timer.
	d := open_hello(&h, 3, .Join, "ABCD", token = join_token)
	e, _ := find(d, np.Error)
	testing.expect_value(t, e.code, np.Error_Code.Run_Not_Found)
	d1 := drain(&h, 1)
	_, left := find(d1, np.Partner_Left)
	testing.expect(t, left && d1.closed)
	testing.expect_value(t, len(h.hub.rooms), 0)
}

@(test)
relay_host_departure_closes_room :: proc(t: ^testing.T) {
	h: Harness
	harness_init(&h)
	defer harness_destroy(&h)
	start_run(t, &h)
	send_msg(&h, 1, np.Bye{})
	d2 := drain(&h, 2)
	left, ok := find(d2, np.Partner_Left)
	testing.expect(t, ok)
	testing.expect_value(t, left.reason, "host_left")
	testing.expect(t, d2.closed)
	testing.expect_value(t, len(h.hub.rooms), 0)
}

@(test)
relay_prestart_joiner_departure_reopens_code :: proc(t: ^testing.T) {
	h: Harness
	harness_init(&h)
	defer harness_destroy(&h)
	setup_selecting(t, &h)
	send_msg(&h, 2, np.Bye{})
	lobby, _ := find(drain(&h, 1), np.Lobby)
	testing.expect_value(t, lobby.phase, np.Lobby_Phase.Waiting)
	testing.expect(t, !lobby.join.present)
	_ = open_hello(&h, 3, .Join, "ABCD")
	lobby, _ = find(drain(&h, 1), np.Lobby)
	testing.expect_value(t, lobby.phase, np.Lobby_Phase.Admission)
}

@(test)
relay_passthrough_forwards_verbatim_with_role_checks :: proc(t: ^testing.T) {
	h: Harness
	harness_init(&h)
	defer harness_destroy(&h)
	// Before start, gameplay traffic is a state error.
	setup_selecting(t, &h)
	send_text(&h, 1, `{"t":"snapshot","x":1}`)
	e, _ := find(drain(&h, 1), np.Error)
	testing.expect_value(t, e.code, np.Error_Code.Bad_State)
	send_msg(&h, 1, np.Ready{seq = next_seq(&h, 1), ready = true, seed = 3})
	send_msg(&h, 2, np.Ready{seq = next_seq(&h, 2), ready = true})
	_ = drain(&h, 1)
	_ = drain(&h, 2)

	snap := `{"t":"snapshot", "tick":"18446744073709551615","s":[1,2]}`
	send_text(&h, 1, snap)
	d2 := drain(&h, 2)
	testing.expect_value(t, len(d2.raw), 1)
	testing.expect_value(t, d2.raw[0], snap)

	intent := `{"t":"intent","steps":[]}`
	send_text(&h, 2, intent)
	d1 := drain(&h, 1)
	testing.expect_value(t, d1.raw[0], intent)

	// Joiner cannot send host-only gameplay; host cannot send intents.
	send_text(&h, 2, `{"t":"snapshot"}`)
	e, _ = find(drain(&h, 2), np.Error)
	testing.expect_value(t, e.code, np.Error_Code.Role_Forbidden)
	send_text(&h, 1, `{"t":"intent"}`)
	e, _ = find(drain(&h, 1), np.Error)
	testing.expect_value(t, e.code, np.Error_Code.Role_Forbidden)
	// Unknown types do not refresh room lifetime.
	before := h.hub.rooms["ABCD"].last_activity
	h.now += 50
	send_text(&h, 2, `{"t":"mystery"}`)
	testing.expect_value(t, h.hub.rooms["ABCD"].last_activity, before)
}

@(test)
relay_result_survives_host_departure :: proc(t: ^testing.T) {
	h: Harness
	harness_init(&h)
	defer harness_destroy(&h)
	_, join_token := start_run(t, &h)
	hub_closed(&h.hub, 2, h.now) // joiner blips right as the run ends
	_ = drain(&h, 1)
	result := `{"t":"run_ended","result":"777","outcome":"victory"}`
	send_text(&h, 1, result)
	send_msg(&h, 1, np.Bye{})
	testing.expect_value(t, len(h.hub.rooms), 1)
	testing.expect_value(t, h.hub.rooms["ABCD"].phase, np.Lobby_Phase.Ended)

	h.now += 5_000
	d := open_hello(&h, 3, .Join, "ABCD", token = join_token)
	w, ok := find(d, np.Welcome)
	testing.expect(t, ok && w.resumed)
	testing.expect_value(t, w.phase, np.Lobby_Phase.Ended)
	testing.expect_value(t, d.raw[len(d.raw) - 1], result)
	send_msg(&h, 3, np.Result_Ack{result = 777})
	hub_tick(&h.hub, h.now)
	testing.expect_value(t, len(h.hub.rooms), 0)
}

@(test)
relay_result_delivery_window_expires :: proc(t: ^testing.T) {
	h: Harness
	harness_init(&h)
	defer harness_destroy(&h)
	start_run(t, &h)
	send_text(&h, 1, `{"t":"run_ended","result":"5"}`)
	_ = drain(&h, 2)
	h.now += np.RESULT_DELIVERY_MS + 1
	// Pings would extend nothing: the deadline is fixed.
	hub_tick(&h.hub, h.now)
	testing.expect_value(t, len(h.hub.rooms), 0)
}

@(test)
relay_rate_limit_and_invalid_flood :: proc(t: ^testing.T) {
	h: Harness
	cfg := DEFAULT_CONFIG
	cfg.rate_msgs_burst = 5
	cfg.rate_msgs_per_s = 1
	harness_init(&h, cfg)
	defer harness_destroy(&h)
	_ = open_hello(&h, 1, .Host, "ABCD")
	for _ in 0 ..< 6 do send_msg(&h, 1, np.Ping{seq = next_seq(&h, 1), ts = 0})
	d := drain(&h, 1)
	e, _ := find(d, np.Error)
	testing.expect_value(t, e.code, np.Error_Code.Rate_Limited)
	testing.expect(t, d.closed)
	testing.expect_value(t, len(h.hub.rooms), 0)

	h2: Harness
	harness_init(&h2)
	defer harness_destroy(&h2)
	_ = open_hello(&h2, 1, .Host, "ABCD")
	for _ in 0 ..< DEFAULT_CONFIG.max_invalid do send_text(&h2, 1, `{"t":"mystery"}`)
	d = drain(&h2, 1)
	testing.expect(t, d.closed)
}

@(test)
relay_liveness_and_idle :: proc(t: ^testing.T) {
	h: Harness
	harness_init(&h)
	defer harness_destroy(&h)
	start_run(t, &h)
	// Joiner goes silent (half-open): liveness drops it into grace.
	h.now += np.LIVENESS_TIMEOUT_MS - 1000
	send_msg(&h, 1, np.Ping{seq = next_seq(&h, 1), ts = 0})
	h.now += 2000
	hub_tick(&h.hub, h.now)
	testing.expect(t, drain(&h, 2).closed)
	_, held := find(drain(&h, 1), np.Partner_Disconnected)
	testing.expect(t, held)

	h2: Harness
	harness_init(&h2)
	defer harness_destroy(&h2)
	_ = open_hello(&h2, 1, .Host, "ABCD")
	for i in 0 ..< 70 {
		h2.now += 10_000
		_ = i
		send_msg(&h2, 1, np.Ping{seq = next_seq(&h2, 1), ts = 0})
		hub_tick(&h2.hub, h2.now)
	}
	// Valid pings keep a waiting lobby alive (archive behavior).
	testing.expect_value(t, len(h2.hub.rooms), 1)
	for i in 0 ..< 70 {
		h2.now += 10_000
		_ = i
		send_text(&h2, 1, `{"t":"mystery"}`) // invalid traffic does not
		if i % 20 == 0 do h2.hub.conns[1].invalid = 0
		h2.hub.conns[1].last_recv = h2.now
		hub_tick(&h2.hub, h2.now)
		if len(h2.hub.rooms) == 0 do break
	}
	testing.expect_value(t, len(h2.hub.rooms), 0)
}

@(test)
relay_settings_change_invalidates_joiner_ready :: proc(t: ^testing.T) {
	h: Harness
	harness_init(&h)
	defer harness_destroy(&h)
	setup_selecting(t, &h)
	send_msg(&h, 2, np.Ready{seq = next_seq(&h, 2), ready = true})
	send_msg(&h, 1, np.Settings{seq = next_seq(&h, 1), difficulty = "hard", story = false})
	lobby, _ := find(drain(&h, 2), np.Lobby)
	testing.expect(t, !lobby.join.ready)
	testing.expect_value(t, lobby.difficulty, "hard")
	testing.expect(t, !lobby.story)
	// Changing archetype also clears readiness.
	send_msg(&h, 2, np.Ready{seq = next_seq(&h, 2), ready = true})
	send_msg(&h, 2, np.Select{seq = next_seq(&h, 2), archetype = "ranger"})
	lobby, _ = find(drain(&h, 2), np.Lobby)
	testing.expect(t, !lobby.join.ready)
	// Joiner cannot supply a seed or change settings.
	send_msg(&h, 2, np.Ready{seq = next_seq(&h, 2), ready = true, seed = 4})
	e, _ := find(drain(&h, 2), np.Error)
	testing.expect_value(t, e.code, np.Error_Code.Role_Forbidden)
	send_msg(&h, 2, np.Settings{seq = next_seq(&h, 2), difficulty = "easy", story = true})
	e, _ = find(drain(&h, 2), np.Error)
	testing.expect_value(t, e.code, np.Error_Code.Role_Forbidden)
}

@(test)
relay_reconnect_while_ready_still_starts :: proc(t: ^testing.T) {
	h: Harness
	harness_init(&h)
	defer harness_destroy(&h)
	_, join_token := setup_selecting(t, &h)
	send_msg(&h, 2, np.Ready{seq = next_seq(&h, 2), ready = true})
	hub_closed(&h.hub, 2, h.now)
	send_msg(&h, 1, np.Ready{seq = next_seq(&h, 1), ready = true, seed = 8})
	_, started := find(drain(&h, 1), np.Start)
	testing.expect(t, !started) // never start with a disconnected seat
	// Readiness survives a brief blip and the reclaim itself starts the run.
	d := open_hello(&h, 3, .Join, "ABCD", token = join_token)
	_, started = find(d, np.Start)
	testing.expect(t, started)
	_, started = find(drain(&h, 1), np.Start)
	testing.expect(t, started)
}


// ------------------------------------------------------- per-source limits --

@(test)
test_per_source_connection_cap :: proc(t: ^testing.T) {
	h: Harness
	config := DEFAULT_CONFIG
	config.max_conns_per_source = 3
	harness_init(&h, config)
	defer harness_destroy(&h)
	for c in 1 ..= 3 {
		hub_open(&h.hub, Conn_Id(c), h.now, "203.0.113.7")
		testing.expect(t, !drain(&h, Conn_Id(c)).closed, "within the cap stays open")
	}
	hub_open(&h.hub, 4, h.now, "203.0.113.7")
	d := drain(&h, 4)
	testing.expect(t, d.closed && d.code == CLOSE_POLICY, "fourth socket from one source is refused")
	// A different source is unaffected, and sockets without a source never count.
	hub_open(&h.hub, 5, h.now, "198.51.100.2")
	testing.expect(t, !drain(&h, 5).closed)
	hub_open(&h.hub, 6, h.now)
	testing.expect(t, !drain(&h, 6).closed)
	// Closing releases the slot.
	hub_closed(&h.hub, 4, h.now)
	hub_closed(&h.hub, 1, h.now)
	hub_open(&h.hub, 7, h.now, "203.0.113.7")
	testing.expect(t, !drain(&h, 7).closed, "slot freed after close")
	for c in ([]Conn_Id{2, 3, 5, 6, 7}) do hub_closed(&h.hub, c, h.now)
	testing.expect_value(t, hub_source_count(&h.hub), 0)
}

@(test)
test_per_source_room_cap :: proc(t: ^testing.T) {
	h: Harness
	config := DEFAULT_CONFIG
	config.max_rooms_per_source = 2
	config.max_conns_per_source = 0 // only the room cap under test
	harness_init(&h, config)
	defer harness_destroy(&h)
	codes := []string{"AAAA", "BBBB", "CCCC"}
	for code, i in codes {
		c := Conn_Id(i + 1)
		hub_open(&h.hub, c, h.now, "203.0.113.7")
		send_msg(&h, c, np.Hello{seq = next_seq(&h, c), protocol = np.PROTOCOL_VERSION, game = GAME, name = "Host", room = code, role = .Host})
		d := drain(&h, c)
		if i < 2 {
			_, ok := find(d, np.Welcome)
			testing.expect(t, ok, "rooms within the cap open")
		} else {
			e, ok := find(d, np.Error)
			testing.expect(t, ok && e.fatal && e.code == np.Error_Code.Server_Full, "third room from one source is refused")
		}
	}
	testing.expect_value(t, hub_room_count(&h.hub), 2)
	// Another source still hosts, and a closed room frees the quota.
	hub_open(&h.hub, 9, h.now, "198.51.100.2")
	send_msg(&h, 9, np.Hello{seq = next_seq(&h, 9), protocol = np.PROTOCOL_VERSION, game = GAME, name = "Host", room = "DDDD", role = .Host})
	_, ok := find(drain(&h, 9), np.Welcome)
	testing.expect(t, ok)
	send_msg(&h, 1, np.Bye{})
	_ = drain(&h, 1)
	hub_closed(&h.hub, 1, h.now)
	hub_open(&h.hub, 4, h.now, "203.0.113.7")
	send_msg(&h, 4, np.Hello{seq = next_seq(&h, 4), protocol = np.PROTOCOL_VERSION, game = GAME, name = "Host", room = "CCCC", role = .Host})
	_, ok = find(drain(&h, 4), np.Welcome)
	testing.expect(t, ok, "quota returns once a room closes")
}

@(test)
test_waiting_room_hard_lifetime :: proc(t: ^testing.T) {
	h: Harness
	config := DEFAULT_CONFIG
	config.waiting_max_ms = 60_000
	harness_init(&h, config)
	defer harness_destroy(&h)
	_ = open_hello(&h, 1, .Host, "ABCD")
	// Pings keep the room "active" but cannot extend an empty room forever.
	for _ in 0 ..< 12 {
		h.now += 5_000
		send_msg(&h, 1, np.Ping{seq = next_seq(&h, 1), ts = 1})
		_ = drain(&h, 1)
		hub_tick(&h.hub, h.now)
	}
	h.now += 5_000
	hub_tick(&h.hub, h.now)
	d := drain(&h, 1)
	e, ok := find(d, np.Error)
	testing.expect(t, ok && e.fatal && e.code == np.Error_Code.Timeout, "waiting room expires despite pings")
	testing.expect_value(t, hub_room_count(&h.hub), 0)

	// A room that has a partner is governed by the ordinary idle rules only.
	h2: Harness
	harness_init(&h2, config)
	defer harness_destroy(&h2)
	_, _ = setup_selecting(t, &h2)
	for _ in 0 ..< 14 {
		h2.now += 5_000
		send_msg(&h2, 1, np.Ping{seq = next_seq(&h2, 1), ts = 1})
		send_msg(&h2, 2, np.Ping{seq = next_seq(&h2, 2), ts = 1})
		_ = drain(&h2, 1)
		_ = drain(&h2, 2)
		hub_tick(&h2.hub, h2.now)
	}
	testing.expect_value(t, hub_room_count(&h2.hub), 1)
}
