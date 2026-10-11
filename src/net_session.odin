package archrogue

// Client-side multiplayer session: one relay connection, the lobby view, and
// bounded reconnect. Raylib-free; time arrives as monotonic milliseconds from
// the platform frame. Gameplay payloads are queued for net_sync; this file
// never touches the Run.

import "core:fmt"
import "core:strings"
import np "net_protocol"

Net_Session_Phase :: enum u8 {
	Idle,
	Connecting,   // socket and hello in flight
	Lobby,        // welcomed into a room before the run starts
	Active,       // run started; gameplay traffic flows
	Reconnecting, // socket lost; reclaiming the seat within the grace window
	Ended,        // run finished or co-op closed; terminal notice shown
	Failed,       // could not connect or was refused; reason shown
}

Net_Event :: enum u8 {
	Welcomed,
	Lobby_Changed,
	Started,
	Partner_Disconnected,
	Partner_Rejoined,
	Partner_Left,
	Reconnected,
	Connection_Lost,
	Failed,
}

NET_NAME_BUF :: np.NAME_MAX_BYTES

Net_Seat :: struct {
	present:   bool,
	connected: bool,
	admitted:  bool,
	ready:     bool,
	archetype: Archetype_Id,
	chosen:    bool,
	name_buf:  [NET_NAME_BUF]byte,
	name_len:  int,
}

net_seat_name :: proc(seat: ^Net_Seat) -> string {
	return string(seat.name_buf[:seat.name_len])
}

Net_Start :: struct {
	session:    u64,
	seed:       u64,
	difficulty: Difficulty_Id,
	story:      bool,
	archetypes: [MAX_PLAYERS]Archetype_Id,
	names:      [MAX_PLAYERS][NET_NAME_BUF]byte,
	name_lens:  [MAX_PLAYERS]int,
}

net_start_name :: proc(start: ^Net_Start, slot: int) -> string {
	return string(start.names[slot][:start.name_lens[slot]])
}

NET_ROOM_CREATE_ATTEMPTS :: 6

Net_Session :: struct {
	transport:        Net_Transport,
	test_pipe:        ^Net_Test_Pipe, // in-process transport for tests only
	phase:            Net_Session_Phase,
	resume_phase:     Net_Session_Phase, // phase to restore after a reconnect
	role:             np.Role,
	endpoint_text:    string, // owned
	endpoint:         Net_Endpoint, // borrows endpoint_text
	name:             string, // owned, sanitized
	room:             [np.ROOM_CODE_LENGTH]byte,
	token:            string, // owned; memory only, never persisted
	session_id:       u64,
	seq:              i64,
	hello_sent:       bool,
	create_attempts:  int,
	// Lobby view (relay authoritative).
	lobby_phase:      np.Lobby_Phase,
	seat_gen:         i64,
	seats:            [MAX_PLAYERS]Net_Seat, // 0 host, 1 joiner
	difficulty:       Difficulty_Id,
	story:            bool,
	start:            Net_Start,
	started:          bool,
	partner_connected: bool,
	partner_grace_until: i64,
	// Liveness and reconnect.
	connect_started_ms: i64,
	last_recv_ms:     i64,
	last_ping_ms:     i64,
	ping_seq_rtt:     i64,
	ping_sent_at:     i64,
	rtt_ms:           i64,
	grace_deadline:   i64,
	next_attempt_ms:  i64,
	backoff_ms:       i64,
	// Outcome.
	error_code:       np.Error_Code,
	error_text:       string, // owned
	events:           [dynamic]Net_Event,
	inbox:            [dynamic][]byte, // gameplay messages awaiting net_sync
}

net_session_destroy :: proc(s: ^Net_Session) {
	net_transport_destroy(&s.transport)
	delete(s.endpoint_text)
	delete(s.name)
	delete(s.token)
	delete(s.error_text)
	delete(s.events)
	for m in s.inbox do delete(m)
	delete(s.inbox)
	s^ = {}
}

net_session_reset :: proc(s: ^Net_Session) {
	net_session_destroy(s)
}

net_session_room_code :: proc(s: ^Net_Session) -> string {
	return string(s.room[:])
}

net_session_local_slot :: proc(s: ^Net_Session) -> int {
	return s.role == .Join ? 1 : HOST_SLOT
}

net_session_partner :: proc(s: ^Net_Session) -> ^Net_Seat {
	return &s.seats[s.role == .Join ? HOST_SLOT : 1]
}

net_session_error :: proc(s: ^Net_Session) -> string {
	return s.error_text
}

@(private = "file")
set_error :: proc(s: ^Net_Session, code: np.Error_Code, text: string) {
	delete(s.error_text)
	s.error_code = code
	s.error_text = strings.clone(text)
}

@(private = "file")
fail :: proc(s: ^Net_Session, code: np.Error_Code, text: string) {
	set_error(s, code, text)
	s.phase = .Failed
	net_transport_close(&s.transport)
	append(&s.events, Net_Event.Failed)
}

@(private = "file")
begin :: proc(s: ^Net_Session, role: np.Role, endpoint_text, name: string, now: i64) -> bool {
	net_session_destroy(s)
	s.endpoint_text = strings.clone(strings.trim_space(endpoint_text))
	endpoint, err := net_url_parse(s.endpoint_text)
	if err != .None {
		set_error(s, .None, net_url_error_text(err))
		s.phase = .Failed
		return false
	}
	s.test_pipe = net_test_pipe_next
	if !net_transport_available() && s.test_pipe == nil {
		set_error(s, .None, "Online co-op is not available in this build yet")
		s.phase = .Failed
		return false
	}
	s.endpoint = endpoint
	s.role = role
	s.name = np.sanitize_name(name)
	if s.name == "" {
		delete(s.name)
		s.name = strings.clone(role == .Host ? "Host" : "Guest")
	}
	s.difficulty = DEFAULT_DIFFICULTY
	s.story = true
	return connect(s, now)
}

@(private = "file")
connect :: proc(s: ^Net_Session, now: i64) -> bool {
	s.hello_sent = false
	s.connect_started_ms = now
	s.last_recv_ms = now
	if !net_transport_open(&s.transport, s.endpoint, s.test_pipe) {
		if s.phase != .Reconnecting do fail(s, .None, "Could not start the connection")
		return false
	}
	if s.phase != .Reconnecting do s.phase = .Connecting
	return true
}

// Host: generate a fresh code with platform randomness and open the room.
net_session_host :: proc(s: ^Net_Session, endpoint_text, name: string, now: i64) -> bool {
	if !begin(s, .Host, endpoint_text, name, now) do return false
	new_room_code(s)
	return true
}

net_session_join :: proc(s: ^Net_Session, endpoint_text, name, code: string, now: i64) -> bool {
	normalized := np.room_code_normalize(code, context.temp_allocator)
	if normalized == "" {
		net_session_destroy(s)
		set_error(s, .Run_Not_Found, "Codes are four letters or digits")
		s.phase = .Failed
		return false
	}
	if !begin(s, .Join, endpoint_text, name, now) do return false
	copy(s.room[:], normalized)
	return true
}

@(private = "file")
new_room_code :: proc(s: ^Net_Session) {
	random: [np.ROOM_CODE_LENGTH]byte
	net_random_bytes(random[:])
	s.room = np.room_code_from_random(random)
}

// Intentional departure: bye skips the reconnect hold on the relay.
net_session_leave :: proc(s: ^Net_Session) {
	if s.phase == .Lobby || s.phase == .Active || s.phase == .Connecting {
		_ = net_session_send(s, np.Bye{})
		// Give the queued bye a brief chance to leave so the partner sees a
		// clean departure instead of a 30 s reconnect hold.
		net_transport_flush(&s.transport, 100)
	}
	net_transport_close(&s.transport)
	s.phase = .Idle
}

// Lifecycle suspension (tab hidden / Android pause): tell the relay so its
// grace window starts now, then drop the socket without bye semantics.
net_session_suspend :: proc(s: ^Net_Session, now: i64) {
	if s.phase != .Lobby && s.phase != .Active do return
	_ = net_session_send(s, np.Suspend{})
	net_transport_close(&s.transport)
	enter_reconnecting(s, now)
	// Resume waits for the platform to return; the first attempt fires then.
	s.next_attempt_ms = max(i64)
}

net_session_resume :: proc(s: ^Net_Session, now: i64) {
	if s.phase == .Reconnecting && s.next_attempt_ms == max(i64) do s.next_attempt_ms = now
}

net_session_send :: proc(s: ^Net_Session, msg: np.Message) -> bool {
	bytes := np.encode(msg, context.temp_allocator)
	return net_transport_send(&s.transport, bytes)
}

net_session_send_raw :: proc(s: ^Net_Session, bytes: []byte) -> bool {
	if s.phase != .Active do return false
	return net_transport_send(&s.transport, bytes)
}

@(private = "file")
next_seq :: proc(s: ^Net_Session) -> i64 {
	s.seq += 1
	return s.seq
}

net_session_select :: proc(s: ^Net_Session, archetype: Archetype_Id) {
	if s.phase != .Lobby do return
	_ = net_session_send(s, np.Select{seq = next_seq(s), archetype = np.ARCHETYPE_KEYS[int(archetype)]})
}

net_session_ready :: proc(s: ^Net_Session, ready: bool, seed: u64 = 0) {
	if s.phase != .Lobby do return
	_ = net_session_send(s, np.Ready{seq = next_seq(s), ready = ready, seed = s.role == .Host ? seed : 0})
}

net_session_settings :: proc(s: ^Net_Session, difficulty: Difficulty_Id, story: bool) {
	if s.phase != .Lobby || s.role != .Host do return
	_ = net_session_send(s, np.Settings{seq = next_seq(s), difficulty = np.DIFFICULTY_KEYS[int(difficulty)], story = story})
}

net_session_admit :: proc(s: ^Net_Session) {
	if s.phase != .Lobby || s.role != .Host do return
	_ = net_session_send(s, np.Admit{seq = next_seq(s), seat_gen = s.seat_gen})
}

net_session_kick :: proc(s: ^Net_Session) {
	if s.phase != .Lobby || s.role != .Host do return
	_ = net_session_send(s, np.Kick{seq = next_seq(s), seat_gen = s.seat_gen})
}

net_session_ack_result :: proc(s: ^Net_Session, result: u64) {
	_ = net_session_send(s, np.Result_Ack{result = result})
}

// ---------------------------------------------------------------- update --

net_session_update :: proc(s: ^Net_Session, now: i64) {
	clear(&s.events)
	if s.phase == .Idle || s.phase == .Failed do return
	net_transport_service(&s.transport)

	if s.phase == .Reconnecting {
		if now > s.grace_deadline {
			fail(s, .Timeout, "The connection could not be restored")
			return
		}
		state := net_transport_state(&s.transport)
		if state == .Closed || state == .Failed {
			if now >= s.next_attempt_ms {
				s.next_attempt_ms = now + s.backoff_ms
				s.backoff_ms = min(s.backoff_ms * 2, np.RECONNECT_BACKOFF_MAX_MS)
				_ = connect(s, now)
			}
			return
		}
	}

	state := net_transport_state(&s.transport)
	switch state {
	case .Connecting:
		if now - s.connect_started_ms > np.CONNECT_BUDGET_MS {
			connection_lost(s, now, "The server did not answer in time")
		}
		return
	case .Closed, .Failed, .Closing:
		connection_lost(s, now, net_friendly_transport_error(net_transport_error(&s.transport)))
		return
	case .Open:
	}

	if !s.hello_sent {
		s.hello_sent = true
		hello := np.Hello{
			seq = next_seq(s),
			protocol = np.PROTOCOL_VERSION,
			game = VERSION,
			name = s.name,
			room = net_session_room_code(s),
			role = s.role,
			token = s.phase == .Reconnecting ? s.token : "",
		}
		_ = net_session_send(s, hello)
	}

	for {
		data, ok := net_transport_recv(&s.transport, context.allocator)
		if !ok do break
		s.last_recv_ms = now
		handle_message(s, data, now)
		if s.phase == .Failed || s.phase == .Ended do break
	}

	if s.phase == .Lobby || s.phase == .Active {
		if now - s.last_ping_ms >= np.HEARTBEAT_INTERVAL_MS {
			s.last_ping_ms = now
			s.ping_sent_at = now
			s.ping_seq_rtt = next_seq(s)
			_ = net_session_send(s, np.Ping{seq = s.ping_seq_rtt, ts = u64(max(now, 0))})
		}
		if now - s.last_recv_ms > np.LIVENESS_TIMEOUT_MS {
			connection_lost(s, now, fmt.tprintf("The connection stopped responding (%d ms silent)", now - s.last_recv_ms))
		}
	}
}

@(private = "file")
connection_lost :: proc(s: ^Net_Session, now: i64, reason: string) {
	platform_log(fmt.tprintf("[coop] connection lost in phase %v: %s (transport %v, close code %d, raw: %s)",
		s.phase, reason, net_transport_state(&s.transport), net_transport_close_code(&s.transport), net_transport_error(&s.transport)))
	switch s.phase {
	case .Connecting:
		fail(s, .None, reason)
	case .Lobby, .Active:
		net_transport_close(&s.transport)
		enter_reconnecting(s, now)
		append(&s.events, Net_Event.Connection_Lost)
	case .Reconnecting:
		// Attempt failed; the backoff timer schedules the next one.
		net_transport_destroy(&s.transport)
	case .Idle, .Ended, .Failed:
	}
}

@(private = "file")
enter_reconnecting :: proc(s: ^Net_Session, now: i64) {
	if s.phase == .Reconnecting do return
	s.resume_phase = s.phase
	s.phase = .Reconnecting
	// One non-extending window: retries never push the deadline out.
	s.grace_deadline = now + np.RECONNECT_GRACE_MS
	s.backoff_ms = np.RECONNECT_BACKOFF_MIN_MS
	s.next_attempt_ms = now + np.RECONNECT_BACKOFF_MIN_MS
}

@(private = "file")
handle_message :: proc(s: ^Net_Session, data: []byte, now: i64) {
	t, json_err, has_type := np.peek_type(data)
	if json_err != .None || !has_type {
		delete(data)
		return
	}
	if np.msg_is_passthrough(t) {
		if s.phase == .Active || s.phase == .Ended do append(&s.inbox, data)
		else do delete(data)
		return
	}
	defer delete(data)
	msg, _, err := np.decode_control(data, context.temp_allocator)
	if err != .None do return
	switch m in msg {
	case np.Welcome:
		was_reconnecting := s.phase == .Reconnecting
		if m.role != s.role do return
		delete(s.token)
		s.token = strings.clone(m.token)
		copy(s.room[:], m.room)
		s.session_id = m.session
		s.partner_connected = true
		if was_reconnecting && m.resumed {
			s.phase = m.phase == .Active ? .Active : (m.phase == .Ended ? .Active : .Lobby)
			append(&s.events, Net_Event.Reconnected)
		} else {
			s.phase = m.phase == .Active ? .Active : .Lobby
			append(&s.events, Net_Event.Welcomed)
		}
	case np.Lobby:
		adopt_lobby(s, m)
		append(&s.events, Net_Event.Lobby_Changed)
	case np.Start:
		adopt_start(s, m)
		s.phase = .Active
		s.started = true
		append(&s.events, Net_Event.Started)
	case np.Partner_Disconnected:
		s.partner_connected = false
		s.partner_grace_until = now + m.grace_ms
		append(&s.events, Net_Event.Partner_Disconnected)
	case np.Partner_Rejoined:
		s.partner_connected = true
		append(&s.events, Net_Event.Partner_Rejoined)
	case np.Partner_Left:
		s.partner_connected = false
		if s.phase == .Active {
			set_error(s, .None, m.reason == "host_left" ? "The host left; co-op has ended" : "Your partner left; co-op has ended")
			s.phase = .Ended
		}
		append(&s.events, Net_Event.Partner_Left)
	case np.Pong:
		if m.seq == s.ping_seq_rtt {
			s.rtt_ms = now - s.ping_sent_at
			if s.rtt_ms > 500 do platform_log(fmt.tprintf("[coop] slow pong seq %d: sent %d now %d rtt %d (echo ts %d)", m.seq, s.ping_sent_at, now, s.rtt_ms, m.ts))
		}
	case np.Error:
		handle_error(s, m)
	case np.Hello, np.Select, np.Ready, np.Settings, np.Admit, np.Kick, np.Ping, np.Bye, np.Suspend, np.Result_Ack:
	}
}

@(private = "file")
handle_error :: proc(s: ^Net_Session, m: np.Error) {
	platform_log(fmt.tprintf("[coop] relay error %v fatal=%v: %s", m.code, m.fatal, m.msg))
	if !m.fatal do return // rejected request; lobby state stays authoritative
	if m.code == .Run_Id_In_Use && s.role == .Host && s.phase == .Connecting && s.create_attempts < NET_ROOM_CREATE_ATTEMPTS {
		// Code collision: draw another code and try again on a fresh socket.
		s.create_attempts += 1
		new_room_code(s)
		net_transport_destroy(&s.transport)
		s.seq = 0
		_ = connect(s, s.connect_started_ms)
		return
	}
	text := m.msg
	switch m.code {
	case .Run_Not_Found: text = s.phase == .Reconnecting ? "That session has ended" : "No room with that code is waiting"
	case .Run_Full:      text = "That room already has two players"
	case .Server_Full:   text = "The server is full right now; try again later"
	case .Bad_Version:   text = "This server speaks a different co-op protocol"
	case .Bad_Revision:  text = fmt.tprintf("Version mismatch: %s", m.msg)
	case .Kicked:        text = "The host turned you away"
	case .Timeout:       text = "The room timed out"
	case .Rate_Limited:  text = "Too many messages; disconnected"
	case .None, .Run_Id_In_Use, .Bad_Msg, .Bad_State, .Role_Forbidden, .Host_Left:
	}
	fail(s, m.code, text)
}

@(private = "file")
archetype_from_key :: proc(key: string) -> (Archetype_Id, bool) {
	for k, i in np.ARCHETYPE_KEYS do if k == key do return Archetype_Id(i), true
	return .Warden, false
}

@(private = "file")
difficulty_from_key :: proc(key: string) -> Difficulty_Id {
	for k, i in np.DIFFICULTY_KEYS do if k == key do return Difficulty_Id(i)
	return DEFAULT_DIFFICULTY
}

@(private = "file")
copy_name :: proc(buf: ^[NET_NAME_BUF]byte, n: ^int, name: string) {
	n^ = copy(buf[:], name)
	// Never cut a UTF-8 sequence in half.
	for n^ > 0 && n^ < len(name) && (name[n^] & 0xC0) == 0x80 do n^ -= 1
}

@(private = "file")
adopt_lobby :: proc(s: ^Net_Session, m: np.Lobby) {
	s.lobby_phase = m.phase
	s.seat_gen = m.seat_gen
	s.difficulty = difficulty_from_key(m.difficulty)
	s.story = m.story
	views := [MAX_PLAYERS]np.Seat_View{m.host, m.join}
	for view, i in views {
		seat := &s.seats[i]
		seat.present = view.present
		seat.connected = view.connected
		seat.admitted = view.admitted
		seat.ready = view.ready
		seat.archetype, seat.chosen = archetype_from_key(view.archetype)
		copy_name(&seat.name_buf, &seat.name_len, view.name)
	}
}

@(private = "file")
adopt_start :: proc(s: ^Net_Session, m: np.Start) {
	s.start.session = m.session
	s.start.seed = m.seed
	s.start.difficulty = difficulty_from_key(m.difficulty)
	s.start.story = m.story
	s.start.archetypes[0], _ = archetype_from_key(m.host_archetype)
	s.start.archetypes[1], _ = archetype_from_key(m.join_archetype)
	copy_name(&s.start.names[0], &s.start.name_lens[0], m.host_name)
	copy_name(&s.start.names[1], &s.start.name_lens[1], m.join_name)
}

// Drains queued gameplay messages for net_sync; the caller frees each slice.
net_session_take_inbox :: proc(s: ^Net_Session) -> (data: []byte, ok: bool) {
	if len(s.inbox) == 0 do return nil, false
	data = s.inbox[0]
	ordered_remove(&s.inbox, 0)
	return data, true
}

// Player-facing wording for transport failures; details stay in the log.
net_friendly_transport_error :: proc(raw: string) -> string {
	switch {
	case raw == "": return "The connection closed"
	case strings.contains(raw, "cert") || strings.contains(raw, "tls="):
		return "The server's certificate could not be verified"
	case strings.contains(raw, "refused"): return "The server refused the connection"
	case strings.contains(raw, "DNS") || strings.contains(raw, "dns") || strings.contains(raw, "resolve"):
		return "The server address could not be found"
	case strings.contains(raw, "too large"): return "The server sent an oversized message"
	}
	return "Could not reach the server"
}
