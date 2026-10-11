package net_protocol

// Protocol v4 envelope and relay-facing control messages. Every message is
// one JSON object with a string "t". Gameplay payloads (checkpoint, snapshot,
// intent, run_ended) are validated structurally by the relay and forwarded
// verbatim; their schemas live with the game-side codec.

import "core:encoding/json"
import "core:strings"

Msg_Type :: enum u8 {
	Unknown,
	// client -> relay
	Hello,
	Select,
	Ready,
	Settings,
	Admit,
	Kick,
	Ping,
	Bye,
	Suspend,
	Result_Ack,
	// relay -> client
	Welcome,
	Lobby,
	Start,
	Partner_Disconnected,
	Partner_Rejoined,
	Partner_Left,
	Pong,
	Error,
	// host <-> joiner, forwarded by the relay
	Checkpoint,
	Checkpoint_Ack,
	Sync_Request,
	Snapshot,
	Intent,
	Run_Ended,
}

MSG_TYPE_NAMES := [Msg_Type]string{
	.Unknown              = "",
	.Hello                = "hello",
	.Select               = "select",
	.Ready                = "ready",
	.Settings             = "settings",
	.Admit                = "admit",
	.Kick                 = "kick",
	.Ping                 = "ping",
	.Bye                  = "bye",
	.Suspend              = "suspend",
	.Result_Ack           = "result_ack",
	.Welcome              = "welcome",
	.Lobby                = "lobby",
	.Start                = "start",
	.Partner_Disconnected = "partner_disconnected",
	.Partner_Rejoined     = "partner_rejoined",
	.Partner_Left         = "partner_left",
	.Pong                 = "pong",
	.Error                = "error",
	.Checkpoint           = "checkpoint",
	.Checkpoint_Ack       = "checkpoint_ack",
	.Sync_Request         = "sync_request",
	.Snapshot             = "snapshot",
	.Intent               = "intent",
	.Run_Ended            = "run_ended",
}

msg_type_from_name :: proc(name: string) -> Msg_Type {
	for text, t in MSG_TYPE_NAMES {
		if t != .Unknown && text == name do return t
	}
	return .Unknown
}

// Which client role may originate a message to the relay. Relay-originated
// types are never accepted from clients.
msg_allowed_from :: proc(t: Msg_Type, role: Role) -> bool {
	#partial switch t {
	case .Select, .Ready, .Ping, .Bye, .Suspend: return role == .Host || role == .Join
	case .Settings, .Admit, .Kick: return role == .Host
	case .Checkpoint, .Snapshot, .Run_Ended: return role == .Host
	case .Checkpoint_Ack, .Sync_Request, .Intent, .Result_Ack: return role == .Join
	}
	return false
}

msg_is_passthrough :: proc(t: Msg_Type) -> bool {
	#partial switch t {
	case .Checkpoint, .Checkpoint_Ack, .Sync_Request, .Snapshot, .Intent, .Run_Ended: return true
	}
	return false
}

Lobby_Phase :: enum u8 {
	Waiting,   // host alone; the code is open
	Admission, // a joiner knocked; host must Accept or Kick
	Selecting, // admitted pair choosing archetypes/readiness
	Active,    // run started
	Ended,     // host published the terminal result
}

LOBBY_PHASE_NAMES := [Lobby_Phase]string{
	.Waiting   = "waiting",
	.Admission = "admission",
	.Selecting = "selecting",
	.Active    = "active",
	.Ended     = "ended",
}

Hello :: struct {
	seq:      i64,
	protocol: i64,
	game:     string, // exact game release identity; both seats must match
	name:     string,
	room:     string,
	role:     Role,
	token:    string, // reconnect token, "" for a fresh seat
}

Welcome :: struct {
	seq:     i64,
	room:    string,
	role:    Role,
	token:   string,
	session: u64, // immutable per room creation; never reused with a code
	resumed: bool, // token reclaim of an existing seat, not a fresh lobby
	phase:   Lobby_Phase,
}

Seat_View :: struct {
	present:   bool,
	connected: bool,
	admitted:  bool,
	ready:     bool,
	name:      string,
	archetype: string, // "" until selected
}

Lobby :: struct {
	phase:      Lobby_Phase,
	seat_gen:   i64, // increments whenever the join seat is (re)occupied
	host:       Seat_View,
	join:       Seat_View,
	difficulty: string,
	story:      bool,
}

Select :: struct {
	seq:       i64,
	archetype: string,
}

Ready :: struct {
	seq:   i64,
	ready: bool,
	seed:  u64, // host only, required when ready; joiner sends 0
}

Settings :: struct {
	seq:        i64,
	difficulty: string,
	story:      bool,
}

Admit :: struct {
	seq:      i64,
	seat_gen: i64,
}

Kick :: struct {
	seq:      i64,
	seat_gen: i64,
}

Start :: struct {
	session:        u64,
	seed:           u64,
	difficulty:     string,
	story:          bool,
	host_name:      string,
	host_archetype: string,
	join_name:      string,
	join_archetype: string,
}

Ping :: struct {
	seq: i64,
	ts:  u64, // sender-local monotonic milliseconds, echoed verbatim
}

Pong :: struct {
	seq: i64,
	ts:  u64,
}

Error :: struct {
	code:  Error_Code,
	msg:   string,
	fatal: bool,
	seq:   i64, // 0 when not replying to a sequenced request
}

Partner_Disconnected :: struct {
	grace_ms: i64,
}

Partner_Rejoined :: struct {
	name: string,
}

Partner_Left :: struct {
	reason: string,
}

Result_Ack :: struct {
	result: u64,
}

Bye :: struct {}
Suspend :: struct {}

Message :: union {
	Hello,
	Welcome,
	Lobby,
	Select,
	Ready,
	Settings,
	Admit,
	Kick,
	Start,
	Ping,
	Pong,
	Error,
	Partner_Disconnected,
	Partner_Rejoined,
	Partner_Left,
	Result_Ack,
	Bye,
	Suspend,
}

Decode_Error :: enum u8 {
	None,
	Json,          // failed strict JSON validation
	No_Type,       // missing/non-string "t"
	Unknown_Type,  // well-formed but unrecognized type
	Bad_Field,     // recognized type with missing/invalid fields
	Not_Control,   // passthrough type: use peek_type and forward
}

// Strictly validates then returns the message type without decoding fields.
peek_type :: proc(data: []byte, limits := DEFAULT_JSON_LIMITS) -> (t: Msg_Type, json_err: Json_Error, type_name_ok: bool) {
	json_err = json_validate(data, limits)
	if json_err != .None do return .Unknown, json_err, false
	// The validator guarantees a well-formed object root. Find the top-level
	// "t" key without materializing the whole document.
	name, found := top_level_type_name(data)
	if !found do return .Unknown, .None, false
	return msg_type_from_name(name), .None, true
}

// Scans a validated object for its top-level "t" string. Keys never contain
// escapes (validator rule), so a byte scan with a container stack is exact.
@(private)
top_level_type_name :: proc(data: []byte) -> (name: string, found: bool) {
	is_ws :: proc(c: byte) -> bool {return c == ' ' || c == '\t' || c == '\n' || c == '\r'}
	stack: [64]byte
	depth := 0
	expect_key := false
	i := 0
	for i < len(data) {
		switch data[i] {
		case '{', '[':
			if depth >= len(stack) do return "", false
			stack[depth] = data[i]
			depth += 1
			expect_key = data[i] == '{'
			i += 1
		case '}', ']':
			depth -= 1
			i += 1
		case ',':
			expect_key = depth > 0 && stack[depth - 1] == '{'
			i += 1
		case '"':
			j := i + 1
			for j < len(data) && data[j] != '"' {
				if data[j] == '\\' do j += 1
				j += 1
			}
			if j >= len(data) do return "", false
			if depth == 1 && expect_key && string(data[i + 1:j]) == "t" {
				k := j + 1
				for k < len(data) && is_ws(data[k]) do k += 1
				if k >= len(data) || data[k] != ':' do return "", false
				k += 1
				for k < len(data) && is_ws(data[k]) do k += 1
				if k >= len(data) || data[k] != '"' do return "", false
				end := k + 1
				for end < len(data) && data[end] != '"' {
					if data[end] == '\\' do return "", false
					end += 1
				}
				if end >= len(data) do return "", false
				return string(data[k + 1:end]), true
			}
			expect_key = false
			i = j + 1
		case:
			i += 1
		}
	}
	return "", false
}

// Decodes a control message. Passthrough types return .Not_Control.
decode_control :: proc(data: []byte, allocator := context.allocator, limits := DEFAULT_JSON_LIMITS) -> (msg: Message, t: Msg_Type, err: Decode_Error) {
	if json_validate(data, limits) != .None do return nil, .Unknown, .Json
	obj, root, ok := json_parse_object(data, context.temp_allocator)
	if !ok do return nil, .Unknown, .Json
	defer json.destroy_value(root, context.temp_allocator)
	name, has_t := read_str(obj, "t", 32)
	if !has_t do return nil, .Unknown, .No_Type
	t = msg_type_from_name(name)
	if t == .Unknown do return nil, t, .Unknown_Type
	if msg_is_passthrough(t) do return nil, t, .Not_Control
	m, fields_ok := decode_fields(obj, t, allocator)
	if !fields_ok do return nil, t, .Bad_Field
	return m, t, .None
}

@(private)
role_from_name :: proc(name: string) -> (Role, bool) {
	switch name {
	case "host": return .Host, true
	case "join": return .Join, true
	}
	return .None, false
}

@(private)
phase_from_name :: proc(name: string) -> (Lobby_Phase, bool) {
	for text, p in LOBBY_PHASE_NAMES do if text == name do return p, true
	return .Waiting, false
}

@(private)
clone :: proc(s: string, allocator := context.allocator) -> string {
	return strings.clone(s, allocator)
}

SEQ_MAX :: i64(1) << 53 - 1

@(private)
decode_fields :: proc(o: json.Object, t: Msg_Type, allocator := context.allocator) -> (msg: Message, ok: bool) {
	#partial switch t {
	case .Hello:
		m: Hello
		m.seq = read_int(o, "seq", 1, SEQ_MAX) or_return
		m.protocol = read_int(o, "protocol", 0, 1_000_000) or_return
		game := read_str(o, "game", GAME_ID_MAX_BYTES) or_return
		if !game_id_valid(game) do return nil, false
		name := read_str(o, "name", NAME_MAX_BYTES * 2) or_return
		room := read_str(o, "room", 16) or_return
		role_name := read_str(o, "role", 8) or_return
		m.role = role_from_name(role_name) or_return
		token := read_opt_str(o, "token", TOKEN_HEX_LENGTH) or_return
		if token != "" && !token_well_formed(token) do return nil, false
		m.game = clone(game, allocator)
		m.name = sanitize_name(name, allocator)
		m.room = clone(room, allocator)
		m.token = clone(token, allocator)
		return m, true
	case .Welcome:
		m: Welcome
		m.seq = read_int(o, "seq", 1, SEQ_MAX) or_return
		room := read_str(o, "room", 16) or_return
		if !room_code_valid(room) do return nil, false
		role_name := read_str(o, "role", 8) or_return
		m.role = role_from_name(role_name) or_return
		token := read_str(o, "token", TOKEN_HEX_LENGTH) or_return
		if !token_well_formed(token) do return nil, false
		m.session = read_u64s(o, "session") or_return
		m.resumed = read_bool(o, "resumed") or_return
		phase_name := read_str(o, "phase", 16) or_return
		m.phase = phase_from_name(phase_name) or_return
		m.room = clone(room, allocator)
		m.token = clone(token, allocator)
		return m, true
	case .Lobby:
		m: Lobby
		phase_name := read_str(o, "phase", 16) or_return
		m.phase = phase_from_name(phase_name) or_return
		m.seat_gen = read_int(o, "seat_gen", 0, SEQ_MAX) or_return
		difficulty := read_str(o, "difficulty", 16) or_return
		if !difficulty_key_valid(difficulty) do return nil, false
		m.difficulty = clone(difficulty, allocator)
		m.story = read_bool(o, "story") or_return
		host := read_object(o, "host") or_return
		join := read_object(o, "join") or_return
		m.host = decode_seat(host, allocator) or_return
		m.join = decode_seat(join, allocator) or_return
		return m, true
	case .Select:
		m: Select
		m.seq = read_int(o, "seq", 1, SEQ_MAX) or_return
		archetype := read_str(o, "archetype", 16) or_return
		if !archetype_key_valid(archetype) do return nil, false
		m.archetype = clone(archetype, allocator)
		return m, true
	case .Ready:
		m: Ready
		m.seq = read_int(o, "seq", 1, SEQ_MAX) or_return
		m.ready = read_bool(o, "ready") or_return
		if "seed" in o {
			m.seed = read_u64s(o, "seed") or_return
		}
		return m, true
	case .Settings:
		m: Settings
		m.seq = read_int(o, "seq", 1, SEQ_MAX) or_return
		difficulty := read_str(o, "difficulty", 16) or_return
		if !difficulty_key_valid(difficulty) do return nil, false
		m.difficulty = clone(difficulty, allocator)
		m.story = read_bool(o, "story") or_return
		return m, true
	case .Admit:
		m: Admit
		m.seq = read_int(o, "seq", 1, SEQ_MAX) or_return
		m.seat_gen = read_int(o, "seat_gen", 1, SEQ_MAX) or_return
		return m, true
	case .Kick:
		m: Kick
		m.seq = read_int(o, "seq", 1, SEQ_MAX) or_return
		m.seat_gen = read_int(o, "seat_gen", 1, SEQ_MAX) or_return
		return m, true
	case .Start:
		m: Start
		m.session = read_u64s(o, "session") or_return
		m.seed = read_u64s(o, "seed") or_return
		difficulty := read_str(o, "difficulty", 16) or_return
		if !difficulty_key_valid(difficulty) do return nil, false
		m.story = read_bool(o, "story") or_return
		host_name := read_str(o, "host_name", NAME_MAX_BYTES * 2) or_return
		join_name := read_str(o, "join_name", NAME_MAX_BYTES * 2) or_return
		host_arch := read_str(o, "host_archetype", 16) or_return
		join_arch := read_str(o, "join_archetype", 16) or_return
		if !archetype_key_valid(host_arch) || !archetype_key_valid(join_arch) do return nil, false
		m.difficulty = clone(difficulty, allocator)
		m.host_name = sanitize_name(host_name, allocator)
		m.join_name = sanitize_name(join_name, allocator)
		m.host_archetype = clone(host_arch, allocator)
		m.join_archetype = clone(join_arch, allocator)
		return m, true
	case .Ping:
		m: Ping
		m.seq = read_int(o, "seq", 1, SEQ_MAX) or_return
		m.ts = read_u64s(o, "ts") or_return
		return m, true
	case .Pong:
		m: Pong
		m.seq = read_int(o, "seq", 1, SEQ_MAX) or_return
		m.ts = read_u64s(o, "ts") or_return
		return m, true
	case .Error:
		m: Error
		code_name := read_str(o, "code", 32) or_return
		code, known := error_code_from_name(code_name)
		m.code = known ? code : .Bad_Msg
		text := read_str(o, "msg", ERROR_MSG_MAX_BYTES * 2) or_return
		m.fatal = read_bool(o, "fatal") or_return
		m.seq = read_opt_int(o, "seq", 0, SEQ_MAX) or_return
		m.msg = clone(text, allocator)
		return m, true
	case .Partner_Disconnected:
		m: Partner_Disconnected
		m.grace_ms = read_int(o, "grace_ms", 0, 3_600_000) or_return
		return m, true
	case .Partner_Rejoined:
		name := read_str(o, "name", NAME_MAX_BYTES * 2) or_return
		return Partner_Rejoined{name = sanitize_name(name, allocator)}, true
	case .Partner_Left:
		reason := read_opt_str(o, "reason", 32) or_return
		return Partner_Left{reason = clone(reason, allocator)}, true
	case .Result_Ack:
		m: Result_Ack
		m.result = read_u64s(o, "result") or_return
		return m, true
	case .Bye:
		return Bye{}, true
	case .Suspend:
		return Suspend{}, true
	}
	return nil, false
}

@(private)
decode_seat :: proc(o: json.Object, allocator := context.allocator) -> (seat: Seat_View, ok: bool) {
	seat.present = read_bool(o, "present") or_return
	seat.connected = read_bool(o, "connected") or_return
	seat.admitted = read_bool(o, "admitted") or_return
	seat.ready = read_bool(o, "ready") or_return
	name := read_str(o, "name", NAME_MAX_BYTES * 2) or_return
	archetype := read_str(o, "archetype", 16) or_return
	if archetype != "" && !archetype_key_valid(archetype) do return {}, false
	seat.name = sanitize_name(name, allocator)
	seat.archetype = clone(archetype, allocator)
	return seat, true
}

message_destroy :: proc(msg: Message, allocator := context.allocator) {
	switch m in msg {
	case Hello:
		delete(m.game, allocator); delete(m.name, allocator); delete(m.room, allocator); delete(m.token, allocator)
	case Welcome:
		delete(m.room, allocator); delete(m.token, allocator)
	case Lobby:
		delete(m.difficulty, allocator)
		delete(m.host.name, allocator); delete(m.host.archetype, allocator)
		delete(m.join.name, allocator); delete(m.join.archetype, allocator)
	case Select:
		delete(m.archetype, allocator)
	case Settings:
		delete(m.difficulty, allocator)
	case Start:
		delete(m.difficulty, allocator)
		delete(m.host_name, allocator); delete(m.join_name, allocator)
		delete(m.host_archetype, allocator); delete(m.join_archetype, allocator)
	case Error:
		delete(m.msg, allocator)
	case Partner_Rejoined:
		delete(m.name, allocator)
	case Partner_Left:
		delete(m.reason, allocator)
	case Ready, Admit, Kick, Ping, Pong, Partner_Disconnected, Result_Ack, Bye, Suspend:
	}
}

// Encodes any control message into a new byte slice owned by allocator.
encode :: proc(msg: Message, allocator := context.allocator) -> []byte {
	w: Json_Writer
	jw_init(&w, allocator)
	jw_begin(&w)
	switch m in msg {
	case Hello:
		jw_str(&w, "t", "hello")
		jw_int(&w, "seq", m.seq)
		jw_int(&w, "protocol", m.protocol)
		jw_str(&w, "game", m.game)
		jw_str(&w, "name", m.name)
		jw_str(&w, "room", m.room)
		jw_str(&w, "role", ROLE_NAMES[m.role])
		if m.token != "" do jw_str(&w, "token", m.token)
	case Welcome:
		jw_str(&w, "t", "welcome")
		jw_int(&w, "seq", m.seq)
		jw_str(&w, "room", m.room)
		jw_str(&w, "role", ROLE_NAMES[m.role])
		jw_str(&w, "token", m.token)
		jw_u64s(&w, "session", m.session)
		jw_bool(&w, "resumed", m.resumed)
		jw_str(&w, "phase", LOBBY_PHASE_NAMES[m.phase])
	case Lobby:
		jw_str(&w, "t", "lobby")
		jw_str(&w, "phase", LOBBY_PHASE_NAMES[m.phase])
		jw_int(&w, "seat_gen", m.seat_gen)
		jw_str(&w, "difficulty", m.difficulty)
		jw_bool(&w, "story", m.story)
		encode_seat(&w, "host", m.host)
		encode_seat(&w, "join", m.join)
	case Select:
		jw_str(&w, "t", "select")
		jw_int(&w, "seq", m.seq)
		jw_str(&w, "archetype", m.archetype)
	case Ready:
		jw_str(&w, "t", "ready")
		jw_int(&w, "seq", m.seq)
		jw_bool(&w, "ready", m.ready)
		if m.seed != 0 do jw_u64s(&w, "seed", m.seed)
	case Settings:
		jw_str(&w, "t", "settings")
		jw_int(&w, "seq", m.seq)
		jw_str(&w, "difficulty", m.difficulty)
		jw_bool(&w, "story", m.story)
	case Admit:
		jw_str(&w, "t", "admit")
		jw_int(&w, "seq", m.seq)
		jw_int(&w, "seat_gen", m.seat_gen)
	case Kick:
		jw_str(&w, "t", "kick")
		jw_int(&w, "seq", m.seq)
		jw_int(&w, "seat_gen", m.seat_gen)
	case Start:
		jw_str(&w, "t", "start")
		jw_u64s(&w, "session", m.session)
		jw_u64s(&w, "seed", m.seed)
		jw_str(&w, "difficulty", m.difficulty)
		jw_bool(&w, "story", m.story)
		jw_str(&w, "host_name", m.host_name)
		jw_str(&w, "host_archetype", m.host_archetype)
		jw_str(&w, "join_name", m.join_name)
		jw_str(&w, "join_archetype", m.join_archetype)
	case Ping:
		jw_str(&w, "t", "ping")
		jw_int(&w, "seq", m.seq)
		jw_u64s(&w, "ts", m.ts)
	case Pong:
		jw_str(&w, "t", "pong")
		jw_int(&w, "seq", m.seq)
		jw_u64s(&w, "ts", m.ts)
	case Error:
		jw_str(&w, "t", "error")
		jw_str(&w, "code", ERROR_CODE_NAMES[m.code])
		msg_text := m.msg
		if len(msg_text) > ERROR_MSG_MAX_BYTES do msg_text = msg_text[:ERROR_MSG_MAX_BYTES]
		jw_str(&w, "msg", msg_text)
		jw_bool(&w, "fatal", m.fatal)
		if m.seq > 0 do jw_int(&w, "seq", m.seq)
	case Partner_Disconnected:
		jw_str(&w, "t", "partner_disconnected")
		jw_int(&w, "grace_ms", m.grace_ms)
	case Partner_Rejoined:
		jw_str(&w, "t", "partner_rejoined")
		jw_str(&w, "name", m.name)
	case Partner_Left:
		jw_str(&w, "t", "partner_left")
		if m.reason != "" do jw_str(&w, "reason", m.reason)
	case Result_Ack:
		jw_str(&w, "t", "result_ack")
		jw_u64s(&w, "result", m.result)
	case Bye:
		jw_str(&w, "t", "bye")
	case Suspend:
		jw_str(&w, "t", "suspend")
	}
	jw_end(&w)
	return jw_bytes(&w)
}

@(private)
encode_seat :: proc(w: ^Json_Writer, key: string, seat: Seat_View) {
	jw_begin_obj_key(w, key)
	jw_bool(w, "present", seat.present)
	jw_bool(w, "connected", seat.connected)
	jw_bool(w, "admitted", seat.admitted)
	jw_bool(w, "ready", seat.ready)
	jw_str(w, "name", seat.name)
	jw_str(w, "archetype", seat.archetype)
	jw_end(w)
}
