// Transport-independent relay room reducer. It receives connection events,
// raw message bytes, and monotonic milliseconds, and returns bounded send/close
// actions. It never simulates the dungeon: gameplay payloads are validated
// structurally and forwarded verbatim between the two seats of a room.
//
// Ported from arch-rogue-python/server/room.py with the v4 changes recorded in
// MULTIPLAYER.md: relay-enforced host admission, same-release gating,
// fresh-sync reconnect instead of cached world replay, and a bounded
// terminal-result delivery window.
package relay_core

import "core:encoding/json"
import "core:fmt"
import "core:strings"
import np "../../../src/net_protocol"

Conn_Id :: distinct u32

CLOSE_NORMAL     :: 1000
CLOSE_POLICY     :: 1008
CLOSE_SUSPENDED  :: 4000
CLOSE_SUPERSEDED :: 4001

Config :: struct {
	max_rooms:          int,
	hello_timeout_ms:   i64,
	grace_ms:           i64,
	idle_timeout_ms:    i64,
	liveness_ms:        i64,
	result_delivery_ms: i64,
	rate_msgs_per_s:    f64,
	rate_msgs_burst:    f64,
	rate_bytes_per_s:   f64,
	rate_bytes_burst:   f64,
	max_invalid:        int,
}

DEFAULT_CONFIG :: Config{
	max_rooms          = np.MAX_ROOMS,
	hello_timeout_ms   = np.HELLO_TIMEOUT_MS,
	grace_ms           = np.RECONNECT_GRACE_MS,
	idle_timeout_ms    = np.ROOM_IDLE_TIMEOUT_MS,
	liveness_ms        = np.LIVENESS_TIMEOUT_MS,
	result_delivery_ms = np.RESULT_DELIVERY_MS,
	rate_msgs_per_s    = 150,
	rate_msgs_burst    = 300,
	rate_bytes_per_s   = 2 * 1024 * 1024,
	rate_bytes_burst   = 4 * 1024 * 1024,
	max_invalid        = 32,
}

Action_Kind :: enum u8 {
	Send,
	Close,
}

// data is owned by the hub allocator; the caller frees it after use with
// hub_actions_clear.
Action :: struct {
	kind:       Action_Kind,
	conn:       Conn_Id,
	data:       []byte,
	close_code: int,
}

Conn :: struct {
	id:          Conn_Id,
	opened_at:   i64,
	last_recv:   i64,
	hello_done:  bool,
	closing:     bool,
	room:        string, // room code when bound to a seat
	role:        np.Role,
	last_seq:    i64,
	invalid:     int,
	msg_tokens:  f64,
	byte_tokens: f64,
	bucket_at:   i64,
}

Seat :: struct {
	present:         bool,
	connected:       bool,
	conn:            Conn_Id,
	token:           string,
	name:            string,
	archetype:       string,
	ready:           bool,
	admitted:        bool,
	disconnected_at: i64, // valid while present && !connected
	seed:            u64, // host only
}

Room :: struct {
	code:          string,
	game:          string,
	session:       u64,
	phase:         np.Lobby_Phase,
	seat_gen:      i64,
	seats:         [np.Role]Seat, // .None unused
	difficulty:    string,
	story:         bool,
	last_activity: i64,
	// Ended-state exception: the immutable result survives host departure
	// until the joiner acknowledges it or the delivery deadline passes.
	result:          []byte,
	result_id:       u64,
	result_deadline: i64,
	result_acked:    bool,
}

Hub :: struct {
	config:    Config,
	rooms:     map[string]^Room,
	conns:     map[Conn_Id]^Conn,
	out:       [dynamic]Action,
	random:    proc(buf: []byte), // cryptographic randomness, injected for tests
	log:       proc(text: string), // optional metadata-only log sink
}

hub_init :: proc(hub: ^Hub, config: Config, random: proc(buf: []byte)) {
	hub.config = config
	hub.random = random
	hub.rooms = make(map[string]^Room)
	hub.conns = make(map[Conn_Id]^Conn)
	hub.out = make([dynamic]Action)
}

hub_destroy :: proc(hub: ^Hub) {
	for _, room in hub.rooms do room_free(room)
	delete(hub.rooms)
	for _, conn in hub.conns do conn_free(conn)
	delete(hub.conns)
	hub_actions_clear(hub)
	delete(hub.out)
}

hub_actions_clear :: proc(hub: ^Hub) {
	for a in hub.out do delete(a.data)
	clear(&hub.out)
}

hub_room_count :: proc(hub: ^Hub) -> int {return len(hub.rooms)}

@(private)
logf :: proc(hub: ^Hub, format: string, args: ..any) {
	if hub.log == nil do return
	hub.log(fmt.tprintf(format, ..args))
}

@(private)
room_free :: proc(room: ^Room) {
	delete(room.code)
	delete(room.game)
	delete(room.difficulty)
	delete(room.result)
	for &seat in room.seats do seat_clear(&seat)
	free(room)
}

@(private)
seat_clear :: proc(seat: ^Seat) {
	delete(seat.token)
	delete(seat.name)
	delete(seat.archetype)
	seat^ = {}
}

@(private)
conn_free :: proc(conn: ^Conn) {
	delete(conn.room)
	free(conn)
}

// ------------------------------------------------------------ transport in --

hub_open :: proc(hub: ^Hub, id: Conn_Id, now: i64) {
	if id in hub.conns do return
	conn := new(Conn)
	conn.id = id
	conn.opened_at = now
	conn.last_recv = now
	conn.bucket_at = now
	conn.msg_tokens = hub.config.rate_msgs_burst
	conn.byte_tokens = hub.config.rate_bytes_burst
	hub.conns[id] = conn
}

// The transport reports the socket is gone (peer close, error, or our own
// close completing). Unexpected loss of a bound seat starts the grace hold.
hub_closed :: proc(hub: ^Hub, id: Conn_Id, now: i64, close_code := 0) {
	conn, found := hub.conns[id]
	if !found do return
	logf(hub, "conn %d closed by transport (code %d, role %v, hello %v, invalid %d)", id, close_code, conn.role, conn.hello_done, conn.invalid)
	room_code := strings.clone(conn.room, context.temp_allocator)
	role := conn.role
	delete_key(&hub.conns, id)
	conn_free(conn)
	if room_code == "" do return
	room := hub.rooms[room_code] or_else nil
	if room == nil do return
	seat := &room.seats[role]
	if !seat.present || !seat.connected || seat.conn != id do return
	seat_lost(hub, room, role, now)
}

hub_receive :: proc(hub: ^Hub, id: Conn_Id, data: []byte, now: i64) {
	conn, found := hub.conns[id]
	if !found || conn.closing do return
	conn.last_recv = now
	if !rate_take(hub, conn, len(data), now) {
		logf(hub, "conn %d rate limited (%d bytes, msg tokens %.1f, byte tokens %.0f)", id, len(data), conn.msg_tokens, conn.byte_tokens)
		fatal(hub, conn, .Rate_Limited, "message rate exceeded")
		return
	}
	t, json_err, has_type := np.peek_type(data)
	if json_err != .None || !has_type {
		if !conn.hello_done {
			fatal(hub, conn, .Bad_Msg, "malformed hello")
		} else {
			reject(hub, conn, .Bad_Msg, "malformed message", 0)
		}
		return
	}
	if !conn.hello_done {
		if t != .Hello {
			fatal(hub, conn, .Bad_Msg, "the first message must be hello")
			return
		}
		msg, _, err := np.decode_control(data, context.temp_allocator)
		if err != .None {
			fatal(hub, conn, .Bad_Msg, "invalid hello")
			return
		}
		handle_hello(hub, conn, msg.(np.Hello), now)
		return
	}
	if t == .Unknown {
		// Unknown types are tolerated for diagnostics but count as invalid
		// and never refresh room lifetime.
		note_invalid(hub, conn)
		return
	}
	if t == .Hello {
		reject(hub, conn, .Bad_State, "hello was already accepted", 0)
		return
	}
	room := hub.rooms[conn.room] or_else nil
	if room == nil {
		fatal(hub, conn, .Bad_State, "room is closed")
		return
	}
	if !np.msg_allowed_from(t, conn.role) {
		reject(hub, conn, .Role_Forbidden, "role may not send this message", 0)
		return
	}
	if np.msg_is_passthrough(t) {
		handle_passthrough(hub, conn, room, t, data, now)
		return
	}
	msg, _, err := np.decode_control(data, context.temp_allocator)
	if err != .None {
		reject(hub, conn, .Bad_Msg, "invalid message fields", 0)
		return
	}
	seq := message_seq(msg)
	if seq > 0 {
		if seq <= conn.last_seq {
			reject(hub, conn, .Bad_Msg, "seq must increase", seq)
			return
		}
		conn.last_seq = seq
	}
	switch m in msg {
	case np.Select:   handle_select(hub, conn, room, m, now)
	case np.Ready:    handle_ready(hub, conn, room, m, now)
	case np.Settings: handle_settings(hub, conn, room, m, now)
	case np.Admit:    handle_admit(hub, conn, room, m, now)
	case np.Kick:     handle_kick(hub, conn, room, m, now)
	case np.Ping:
		room.last_activity = now
		send(hub, conn.id, np.Pong{seq = m.seq, ts = m.ts})
	case np.Bye:        handle_bye(hub, conn, room, now)
	case np.Suspend:    handle_suspend(hub, conn, room, now)
	case np.Result_Ack: handle_result_ack(hub, conn, room, m, now)
	case np.Hello, np.Welcome, np.Lobby, np.Start, np.Pong, np.Error,
	     np.Partner_Disconnected, np.Partner_Rejoined, np.Partner_Left:
		reject(hub, conn, .Role_Forbidden, "relay-only message", seq)
	}
}

@(private)
message_seq :: proc(msg: np.Message) -> i64 {
	#partial switch m in msg {
	case np.Select:   return m.seq
	case np.Ready:    return m.seq
	case np.Settings: return m.seq
	case np.Admit:    return m.seq
	case np.Kick:     return m.seq
	case np.Ping:     return m.seq
	}
	return 0
}

// ------------------------------------------------------------------ timers --

hub_tick :: proc(hub: ^Hub, now: i64) {
	cfg := hub.config
	expired := make([dynamic]Conn_Id, context.temp_allocator)
	for id, conn in hub.conns {
		if conn.closing do continue
		if !conn.hello_done && now - conn.opened_at > cfg.hello_timeout_ms {
			append(&expired, id)
		} else if conn.hello_done && now - conn.last_recv > cfg.liveness_ms {
			append(&expired, id)
		}
	}
	for id in expired {
		conn := hub.conns[id] or_else nil
		if conn == nil do continue
		if !conn.hello_done {
			fatal(hub, conn, .Timeout, "hello timeout")
		} else {
			// Half-open or frozen peer: drop the socket and let the
			// ordinary unexpected-disconnect path start the grace hold.
			logf(hub, "conn %d liveness timeout (%d ms since last message)", id, now - conn.last_recv)
			close_conn(hub, conn, CLOSE_POLICY)
			hub_closed(hub, id, now)
		}
	}

	codes := make([dynamic]string, context.temp_allocator)
	for code in hub.rooms do append(&codes, code)
	for code in codes {
		room := hub.rooms[code] or_else nil
		if room == nil do continue
		for role in ([]np.Role{.Host, .Join}) {
			seat := &room.seats[role]
			if seat.present && !seat.connected && now - seat.disconnected_at > cfg.grace_ms {
				seat_departed(hub, room, role, "timeout", now)
				if hub.rooms[code] == nil do break
			}
		}
		room = hub.rooms[code] or_else nil
		if room == nil do continue
		if room.phase == .Ended {
			if room.result_acked || now > room.result_deadline do close_room(hub, room, .None, "")
			continue
		}
		if now - room.last_activity > cfg.idle_timeout_ms {
			logf(hub, "room idle timeout")
			close_room(hub, room, .Timeout, "room idle timeout")
		}
	}
}

// -------------------------------------------------------------------- hello --

@(private)
handle_hello :: proc(hub: ^Hub, conn: ^Conn, hello: np.Hello, now: i64) {
	if hello.protocol != np.PROTOCOL_VERSION {
		fatal(hub, conn, .Bad_Version, fmt.tprintf("protocol %d is unsupported (relay speaks %d)", hello.protocol, np.PROTOCOL_VERSION), hello.seq)
		return
	}
	code := np.room_code_normalize(hello.room, context.temp_allocator)
	if code == "" {
		fatal(hub, conn, hello.role == .Join ? .Run_Not_Found : .Bad_Msg, "room code must be 4 characters from the code alphabet", hello.seq)
		return
	}
	room := hub.rooms[code] or_else nil

	if hello.token != "" {
		reclaim(hub, conn, room, hello, now)
		return
	}

	if hello.role == .Host {
		if room != nil {
			fatal(hub, conn, .Run_Id_In_Use, "a run with this code already exists", hello.seq)
			return
		}
		if len(hub.rooms) >= hub.config.max_rooms {
			fatal(hub, conn, .Server_Full, "the relay is at its room limit", hello.seq)
			return
		}
		room = new(Room)
		room.code = strings.clone(code)
		room.game = strings.clone(hello.game)
		room.session = random_u64(hub)
		room.phase = .Waiting
		room.difficulty = strings.clone(np.DIFFICULTY_KEYS[0])
		room.story = true
		room.last_activity = now
		hub.rooms[room.code] = room
		seat_fill(hub, &room.seats[.Host], conn, hello)
		room.seats[.Host].admitted = true
		bind(hub, conn, room, .Host, hello.seq, false)
		broadcast_lobby(hub, room)
		logf(hub, "room created (%d rooms)", len(hub.rooms))
		return
	}

	if room == nil {
		fatal(hub, conn, .Run_Not_Found, "no run with this code is waiting", hello.seq)
		return
	}
	if room.phase != .Waiting || room.seats[.Join].present {
		fatal(hub, conn, .Run_Full, "this run is not open for joining", hello.seq)
		return
	}
	if hello.game != room.game {
		fatal(hub, conn, .Bad_Revision, fmt.tprintf("the host runs %s but you run %s; both players need the same release", room.game, hello.game), hello.seq)
		return
	}
	seat_fill(hub, &room.seats[.Join], conn, hello)
	room.seat_gen += 1
	room.phase = .Admission
	room.last_activity = now
	// A new knock always needs fresh host consent and fresh readiness.
	room.seats[.Host].ready = false
	bind(hub, conn, room, .Join, hello.seq, false)
	broadcast_lobby(hub, room)
}

@(private)
seat_fill :: proc(hub: ^Hub, seat: ^Seat, conn: ^Conn, hello: np.Hello) {
	seat_clear(seat)
	seat.present = true
	seat.connected = true
	seat.conn = conn.id
	seat.name = strings.clone(hello.name)
	seat.archetype = strings.clone("")
	random: [np.TOKEN_BYTES]byte
	hub.random(random[:])
	seat.token = np.token_from_random(random)
}

@(private)
bind :: proc(hub: ^Hub, conn: ^Conn, room: ^Room, role: np.Role, seq: i64, resumed: bool) {
	conn.hello_done = true
	delete(conn.room)
	conn.room = strings.clone(room.code)
	conn.role = role
	conn.last_seq = seq
	seat := &room.seats[role]
	send(hub, conn.id, np.Welcome{
		seq = seq,
		room = room.code,
		role = role,
		token = seat.token,
		session = room.session,
		resumed = resumed,
		phase = room.phase,
	})
}

@(private)
reclaim :: proc(hub: ^Hub, conn: ^Conn, room: ^Room, hello: np.Hello, now: i64) {
	if room == nil {
		fatal(hub, conn, .Run_Not_Found, "that session has ended", hello.seq)
		return
	}
	role := np.Role.None
	for r in ([]np.Role{.Host, .Join}) {
		seat := &room.seats[r]
		if seat.present && np.token_equal(seat.token, hello.token) {
			role = r
			break
		}
	}
	// A failed reclaim never falls back to claiming a fresh seat.
	if role == .None || role != hello.role {
		fatal(hub, conn, .Run_Not_Found, "that session has ended", hello.seq)
		return
	}
	seat := &room.seats[role]
	if !seat.connected && now - seat.disconnected_at > hub.config.grace_ms {
		seat_departed(hub, room, role, "timeout", now)
		fatal(hub, conn, .Run_Not_Found, "the reconnect window expired", hello.seq)
		return
	}
	if hello.game != room.game {
		fatal(hub, conn, .Bad_Revision, "reconnect must use the same release", hello.seq)
		return
	}
	if room.phase == .Ended && (role != .Join || room.result_acked) {
		fatal(hub, conn, .Run_Not_Found, "that session has ended", hello.seq)
		return
	}
	if seat.connected {
		// The old socket may be a zombie the transport has not reported dead
		// yet; the token holder supersedes it, and its later close event is
		// ignored because it no longer owns the seat.
		if old := hub.conns[seat.conn] or_else nil; old != nil {
			delete(old.room)
			old.room = ""
			old.role = .None
			close_conn(hub, old, CLOSE_SUPERSEDED)
		}
	}
	seat.connected = true
	seat.conn = conn.id
	held_since := seat.disconnected_at
	seat.disconnected_at = 0
	if hello.name != "" {
		delete(seat.name)
		seat.name = strings.clone(hello.name)
	}
	room.last_activity = now
	bind(hub, conn, room, role, hello.seq, true)
	partner := partner_role(role)
	if pconn := seat_conn(hub, room, partner); pconn != nil {
		send(hub, pconn.id, np.Partner_Rejoined{name = seat.name})
	}
	if room.phase == .Ended && room.result != nil {
		send_raw(hub, conn.id, room.result)
	}
	// Re-evaluate start: a ready pair must not stall after a reconnect.
	if pre_start(room) && !maybe_start(hub, room) do broadcast_lobby(hub, room)
	if held_since > 0 {
		logf(hub, "room %s: %v seat reclaimed by conn %d after %d ms", room.code, role, conn.id, now - held_since)
	} else {
		logf(hub, "room %s: %v seat reclaimed by conn %d, superseding its still-open socket", room.code, role, conn.id)
	}
}

// ------------------------------------------------------------------- lobby --

@(private)
pre_start :: proc(room: ^Room) -> bool {
	return room.phase == .Waiting || room.phase == .Admission || room.phase == .Selecting
}

@(private)
handle_select :: proc(hub: ^Hub, conn: ^Conn, room: ^Room, m: np.Select, now: i64) {
	seat := &room.seats[conn.role]
	if !pre_start(room) || !seat.admitted {
		reject(hub, conn, .Bad_State, "cannot choose an archetype now", m.seq)
		return
	}
	if seat.archetype != m.archetype {
		delete(seat.archetype)
		seat.archetype = strings.clone(m.archetype)
		seat.ready = false
	}
	room.last_activity = now
	broadcast_lobby(hub, room)
}

@(private)
handle_ready :: proc(hub: ^Hub, conn: ^Conn, room: ^Room, m: np.Ready, now: i64) {
	seat := &room.seats[conn.role]
	if room.phase != .Selecting || !seat.admitted {
		reject(hub, conn, .Bad_State, "readiness needs an admitted partner", m.seq)
		return
	}
	if m.ready {
		if seat.archetype == "" {
			reject(hub, conn, .Bad_State, "choose an archetype first", m.seq)
			return
		}
		if conn.role == .Host {
			if m.seed == 0 {
				reject(hub, conn, .Bad_Msg, "host ready must carry a seed", m.seq)
				return
			}
			seat.seed = m.seed
		} else if m.seed != 0 {
			reject(hub, conn, .Role_Forbidden, "only the host supplies the seed", m.seq)
			return
		}
	}
	seat.ready = m.ready
	room.last_activity = now
	if !maybe_start(hub, room) do broadcast_lobby(hub, room)
}

@(private)
handle_settings :: proc(hub: ^Hub, conn: ^Conn, room: ^Room, m: np.Settings, now: i64) {
	if !pre_start(room) {
		reject(hub, conn, .Bad_State, "the run has already started", m.seq)
		return
	}
	if room.difficulty != m.difficulty || room.story != m.story {
		delete(room.difficulty)
		room.difficulty = strings.clone(m.difficulty)
		room.story = m.story
		// The joiner agreed to the previous settings; ask again.
		room.seats[.Join].ready = false
	}
	room.last_activity = now
	broadcast_lobby(hub, room)
}

@(private)
handle_admit :: proc(hub: ^Hub, conn: ^Conn, room: ^Room, m: np.Admit, now: i64) {
	join := &room.seats[.Join]
	if room.phase != .Admission || !join.present || m.seat_gen != room.seat_gen {
		reject(hub, conn, .Bad_State, "there is no matching request to accept", m.seq)
		return
	}
	join.admitted = true
	room.phase = .Selecting
	room.last_activity = now
	broadcast_lobby(hub, room)
}

@(private)
handle_kick :: proc(hub: ^Hub, conn: ^Conn, room: ^Room, m: np.Kick, now: i64) {
	join := &room.seats[.Join]
	if !pre_start(room) || !join.present || m.seat_gen != room.seat_gen {
		reject(hub, conn, .Bad_State, "there is no lobby partner to turn away", m.seq)
		return
	}
	if jconn := seat_conn(hub, room, .Join); jconn != nil {
		detach(jconn)
		fatal(hub, jconn, .Kicked, "the host turned you away")
	}
	// Cancels the token/reservation and reopens the same code.
	seat_clear(join)
	room.seats[.Host].ready = false
	room.phase = .Waiting
	room.last_activity = now
	send(hub, conn.id, np.Partner_Left{reason = "kicked"})
	broadcast_lobby(hub, room)
}

@(private)
maybe_start :: proc(hub: ^Hub, room: ^Room) -> bool {
	host := &room.seats[.Host]
	join := &room.seats[.Join]
	if room.phase != .Selecting do return false
	for seat in ([]^Seat{host, join}) {
		if !seat.present || !seat.connected || !seat.admitted || !seat.ready || seat.archetype == "" do return false
	}
	room.phase = .Active
	start := np.Start{
		session = room.session,
		seed = host.seed,
		difficulty = room.difficulty,
		story = room.story,
		host_name = host.name,
		host_archetype = host.archetype,
		join_name = join.name,
		join_archetype = join.archetype,
	}
	send(hub, host.conn, start)
	send(hub, join.conn, start)
	logf(hub, "room %s started (session %d)", room.code, room.session)
	return true
}

@(private)
handle_bye :: proc(hub: ^Hub, conn: ^Conn, room: ^Room, now: i64) {
	role := conn.role
	detach(conn)
	close_conn(hub, conn, CLOSE_NORMAL)
	seat_departed(hub, room, role, "left", now)
}

// Lifecycle suspension: grace starts now instead of whenever the browser or
// OS eventually tears the socket down.
@(private)
handle_suspend :: proc(hub: ^Hub, conn: ^Conn, room: ^Room, now: i64) {
	role := conn.role
	detach(conn)
	close_conn(hub, conn, CLOSE_SUSPENDED)
	seat := &room.seats[role]
	if seat.present && seat.connected do seat_lost(hub, room, role, now)
}

@(private)
handle_result_ack :: proc(hub: ^Hub, conn: ^Conn, room: ^Room, m: np.Result_Ack, now: i64) {
	if room.phase != .Ended || m.result != room.result_id {
		reject(hub, conn, .Bad_State, "no matching result", 0)
		return
	}
	room.result_acked = true
	room.last_activity = now
}

// ------------------------------------------------------------- passthrough --

@(private)
handle_passthrough :: proc(hub: ^Hub, conn: ^Conn, room: ^Room, t: np.Msg_Type, data: []byte, now: i64) {
	if room.phase != .Active {
		reject(hub, conn, .Bad_State, "the run is not active", 0)
		return
	}
	room.last_activity = now
	if t == .Run_Ended {
		obj, root, ok := np.json_parse_object(data, context.temp_allocator)
		defer json.destroy_value(root, context.temp_allocator)
		result_id: u64
		if ok do result_id, ok = np.read_u64s(obj, "result")
		if !ok {
			reject(hub, conn, .Bad_Msg, "run_ended needs a result id", 0)
			return
		}
		room.phase = .Ended
		room.result = make([]byte, len(data))
		copy(room.result, data)
		room.result_id = result_id
		room.result_deadline = now + hub.config.result_delivery_ms
	}
	partner := partner_role(conn.role)
	if pconn := seat_conn(hub, room, partner); pconn != nil do send_raw(hub, pconn.id, data)
}

// --------------------------------------------------------------- departures --

@(private)
partner_role :: proc(role: np.Role) -> np.Role {
	return role == .Host ? .Join : .Host
}

@(private)
seat_conn :: proc(hub: ^Hub, room: ^Room, role: np.Role) -> ^Conn {
	seat := &room.seats[role]
	if !seat.present || !seat.connected do return nil
	return hub.conns[seat.conn] or_else nil
}

// Unexpected loss: reserve the seat for the grace window.
@(private)
seat_lost :: proc(hub: ^Hub, room: ^Room, role: np.Role, now: i64) {
	seat := &room.seats[role]
	seat.connected = false
	seat.conn = 0
	seat.disconnected_at = now
	if room.phase == .Ended {
		if role == .Host do return // the retained result needs no live host
		return
	}
	if pconn := seat_conn(hub, room, partner_role(role)); pconn != nil {
		send(hub, pconn.id, np.Partner_Disconnected{grace_ms = hub.config.grace_ms})
	}
	if pre_start(room) do broadcast_lobby(hub, room)
	logf(hub, "room %s: %v seat disconnected unexpectedly; %d ms grace", room.code, role, hub.config.grace_ms)
}

// Final departure: intentional bye, kick, or grace expiry.
@(private)
seat_departed :: proc(hub: ^Hub, room: ^Room, role: np.Role, reason: string, now: i64) {
	seat := &room.seats[role]
	if !seat.present do return
	if conn := seat_conn(hub, room, role); conn != nil {
		detach(conn)
		close_conn(hub, conn, CLOSE_NORMAL)
	}
	seat_clear(seat)
	if room.phase == .Ended {
		if role == .Join do room.result_acked = true // nobody left to deliver to
		if role == .Join || room.result_acked do close_room(hub, room, .None, "")
		return
	}
	partner := partner_role(role)
	if role == .Host || room.phase == .Active {
		// A room cannot outlive its host, and an active run never accepts a
		// replacement stranger: co-op ends for the survivor.
		if pconn := seat_conn(hub, room, partner); pconn != nil {
			send(hub, pconn.id, np.Partner_Left{reason = role == .Host ? "host_left" : reason})
		}
		close_room(hub, room, .None, "")
		return
	}
	// Pre-start joiner departure reopens the same code.
	room.phase = .Waiting
	room.seats[.Host].ready = false
	room.last_activity = now
	if pconn := seat_conn(hub, room, .Host); pconn != nil do send(hub, pconn.id, np.Partner_Left{reason = reason})
	broadcast_lobby(hub, room)
}

@(private)
close_room :: proc(hub: ^Hub, room: ^Room, code: np.Error_Code, text: string) {
	for role in ([]np.Role{.Host, .Join}) {
		if conn := seat_conn(hub, room, role); conn != nil {
			detach(conn)
			if code != .None {
				fatal(hub, conn, code, text)
			} else {
				close_conn(hub, conn, CLOSE_NORMAL)
			}
		}
	}
	key := room.code
	delete_key(&hub.rooms, key)
	room_free(room)
	logf(hub, "room closed (%d rooms)", len(hub.rooms))
}

@(private)
detach :: proc(conn: ^Conn) {
	delete(conn.room)
	conn.room = ""
	conn.role = .None
}

// ------------------------------------------------------------------ output --

@(private)
broadcast_lobby :: proc(hub: ^Hub, room: ^Room) {
	view :: proc(seat: Seat) -> np.Seat_View {
		return {
			present = seat.present,
			connected = seat.connected,
			admitted = seat.admitted,
			ready = seat.ready,
			name = seat.name,
			archetype = seat.archetype,
		}
	}
	msg := np.Lobby{
		phase = room.phase,
		seat_gen = room.seat_gen,
		host = view(room.seats[.Host]),
		join = view(room.seats[.Join]),
		difficulty = room.difficulty,
		story = room.story,
	}
	for role in ([]np.Role{.Host, .Join}) {
		if conn := seat_conn(hub, room, role); conn != nil do send(hub, conn.id, msg)
	}
}

@(private)
send :: proc(hub: ^Hub, id: Conn_Id, msg: np.Message) {
	append(&hub.out, Action{kind = .Send, conn = id, data = np.encode(msg)})
}

@(private)
send_raw :: proc(hub: ^Hub, id: Conn_Id, data: []byte) {
	copy_ := make([]byte, len(data))
	copy(copy_, data)
	append(&hub.out, Action{kind = .Send, conn = id, data = copy_})
}

@(private)
close_conn :: proc(hub: ^Hub, conn: ^Conn, code: int) {
	if conn.closing do return
	conn.closing = true
	append(&hub.out, Action{kind = .Close, conn = conn.id, close_code = code})
}

@(private)
reject :: proc(hub: ^Hub, conn: ^Conn, code: np.Error_Code, text: string, seq: i64) {
	logf(hub, "conn %d rejected: %v (%s)", conn.id, code, text)
	send(hub, conn.id, np.Error{code = code, msg = text, fatal = false, seq = seq})
	note_invalid(hub, conn)
}

@(private)
note_invalid :: proc(hub: ^Hub, conn: ^Conn) {
	conn.invalid += 1
	if conn.invalid >= hub.config.max_invalid do fatal(hub, conn, .Bad_Msg, "too many invalid messages")
}

// Fatal rejections are expected departures: no grace window.
@(private)
fatal :: proc(hub: ^Hub, conn: ^Conn, code: np.Error_Code, text: string, seq: i64 = 0) {
	if conn.closing do return
	logf(hub, "conn %d fatal: %v (%s)", conn.id, code, text)
	send(hub, conn.id, np.Error{code = code, msg = text, fatal = true, seq = seq})
	room_code := strings.clone(conn.room, context.temp_allocator)
	role := conn.role
	detach(conn)
	close_conn(hub, conn, CLOSE_POLICY)
	if room_code != "" {
		if room := hub.rooms[room_code] or_else nil; room != nil {
			seat := &room.seats[role]
			if seat.present && seat.conn == conn.id {
				seat.connected = false
				seat_departed(hub, room, role, "left", conn.last_recv)
			}
		}
	}
}

@(private)
rate_take :: proc(hub: ^Hub, conn: ^Conn, bytes: int, now: i64) -> bool {
	cfg := hub.config
	elapsed := f64(max(0, now - conn.bucket_at)) / 1000
	conn.bucket_at = now
	conn.msg_tokens = min(cfg.rate_msgs_burst, conn.msg_tokens + elapsed * cfg.rate_msgs_per_s)
	conn.byte_tokens = min(cfg.rate_bytes_burst, conn.byte_tokens + elapsed * cfg.rate_bytes_per_s)
	if conn.msg_tokens < 1 || conn.byte_tokens < f64(bytes) do return false
	conn.msg_tokens -= 1
	conn.byte_tokens -= f64(bytes)
	return true
}

@(private)
random_u64 :: proc(hub: ^Hub) -> u64 {
	buf: [8]byte
	for {
		hub.random(buf[:])
		v := u64(0)
		for b in buf do v = v << 8 | u64(b)
		if v != 0 do return v
	}
}
