package archrogue_tests

import "core:testing"
import np "../src/net_protocol"

@(test)
net_json_rejects_hostile_documents :: proc(t: ^testing.T) {
	Case :: struct {
		text: string,
		want: np.Json_Error,
	}
	cases := []Case{
		{`{"t":"ping","seq":1,"ts":"5"}`, .None},
		{``, .Empty},
		{`[1]`, .Not_Object_Root},
		{`"x"`, .Not_Object_Root},
		{`{"t":"a","t":"b"}`, .Duplicate_Key},
		{`{"a":{"x":1,"x":2}}`, .Duplicate_Key},
		{`{"a":{"x":1},"b":{"x":2}}`, .None}, // same key in sibling objects is fine
		{`{"a":1} x`, .Trailing_Data},
		{`{"a":1}{"b":2}`, .Trailing_Data},
		{`{"a":1e999}`, .Bad_Number},
		{`{"a":-1e400}`, .Bad_Number},
		{`{"a":99999999999999999999}`, .Bad_Number}, // ints beyond i64 must be strings
		{`{"a":01}`, .Syntax},
		{`{"a":1.}`, .Bad_Number},
		{`{"a":NaN}`, .Syntax},
		{`{"a":Infinity}`, .Syntax},
		{`{"a":"tab	inside"}`, .Bad_String},
		{`{"a b":1}`, .Bad_Key},
		{`{"a":[1,2,]}`, .Syntax},
		{`{"a":tru}`, .Syntax},
		{`{"a":1`, .Syntax},
	}
	for c in cases {
		got := np.json_validate(transmute([]byte)c.text)
		testing.expectf(t, got == c.want, "%q: got %v want %v", c.text, got, c.want)
	}
	// Escapes are assembled from parts so no tooling rewrites them.
	escaped := []Case{
		{concat(`{"a":"`, BS, "ud800", `"}`), .Bad_String},
		{concat(`{"a":"`, BS, "udc00", `"}`), .Bad_String},
		{concat(`{"a":"`, BS, "ud800x", `"}`), .Bad_String},
		{concat(`{"a":"`, BS, "ud83d", BS, "ude00", `"}`), .None},
		{concat(`{"a":"`, BS, "x", `"}`), .Bad_String},
		{concat(`{"a":"`, BS, "n", BS, "u0041", `"}`), .None},
		{concat(`{"a`, BS, "u0062", `":1}`), .Bad_Key},
	}
	for c in escaped {
		got := np.json_validate(transmute([]byte)c.text)
		testing.expectf(t, got == c.want, "%q: got %v want %v", c.text, got, c.want)
	}
	invalid_utf8 := []byte{'{', '"', 'a', '"', ':', '"', 0xff, '"', '}'}
	testing.expect_value(t, np.json_validate(invalid_utf8), np.Json_Error.Bad_Utf8)

	deep: [dynamic]byte
	defer delete(deep)
	append(&deep, '{', '"', 'a', '"', ':')
	for _ in 0 ..< 40 do append(&deep, '[')
	for _ in 0 ..< 40 do append(&deep, ']')
	append(&deep, '}')
	testing.expect_value(t, np.json_validate(deep[:]), np.Json_Error.Too_Deep)

	limits := np.DEFAULT_JSON_LIMITS
	limits.max_bytes = 8
	testing.expect_value(t, np.json_validate(transmute([]byte)string(`{"a":123456}`), limits), np.Json_Error.Too_Large)

	// Per-object key cap: the duplicate-key scan is linear per key, so a
	// flat object with thousands of keys is refused outright.
	wide: [dynamic]byte
	defer delete(wide)
	append(&wide, '{')
	for i in 0 ..< 129 {
		if i > 0 do append(&wide, ',')
		append(&wide, '"', 'k', byte('a' + i % 26), byte('a' + (i / 26) % 26), '"', ':', '0')
	}
	append(&wide, '}')
	testing.expect_value(t, np.json_validate(wide[:]), np.Json_Error.Too_Many_Keys)
	wide_limits := np.DEFAULT_JSON_LIMITS
	wide_limits.max_object_keys = 129
	testing.expect_value(t, np.json_validate(wide[:], wide_limits), np.Json_Error.None)
}

@(test)
net_u64_identity_strings_survive_beyond_2_53 :: proc(t: ^testing.T) {
	values := []u64{0, 1, (1 << 53) - 1, 1 << 53, (1 << 53) + 1, max(u64)}
	for v in values {
		bytes := np.encode(np.Ping{seq = 7, ts = v}, context.temp_allocator)
		msg, typ, err := np.decode_control(bytes, context.temp_allocator)
		testing.expect_value(t, err, np.Decode_Error.None)
		testing.expect_value(t, typ, np.Msg_Type.Ping)
		ping, ok := msg.(np.Ping)
		testing.expect(t, ok)
		testing.expect_value(t, ping.ts, v)
	}
	bad := []string{`"01"`, `"-1"`, `"18446744073709551616"`, `""`, `"1e3"`, `5`}
	for b in bad {
		text := concat(`{"t":"ping","seq":1,"ts":`, b, `}`)
		_, _, err := np.decode_control(transmute([]byte)text, context.temp_allocator)
		testing.expectf(t, err == .Bad_Field, "%s accepted", text)
	}
}

@(private="file") BS :: "\\"
@(private="file") NUL :: "\x00"
@(private="file") ZWSP :: "\xe2\x80\x8b"

@(private="file")
concat :: proc(parts: ..string) -> string {
	n := 0
	for p in parts do n += len(p)
	out := make([]byte, n, context.temp_allocator)
	i := 0
	for p in parts {
		copy(out[i:], p)
		i += len(p)
	}
	return string(out)
}

@(test)
net_control_messages_round_trip :: proc(t: ^testing.T) {
	token := "0123456789abcdef0123456789abcdef"
	msgs := []np.Message{
		np.Hello{seq = 1, protocol = np.PROTOCOL_VERSION, game = "6.0.0-alpha.27", name = "Matti", room = "ABCD", role = .Host},
		np.Hello{seq = 3, protocol = np.PROTOCOL_VERSION, game = "6.0.0-alpha.27", name = "Väinö", room = "WXYZ", role = .Join, token = token},
		np.Welcome{seq = 1, room = "ABCD", role = .Join, token = token, session = max(u64) - 3, resumed = true, phase = .Active},
		np.Lobby{phase = .Selecting, seat_gen = 2, difficulty = "hard", story = true,
			host = {present = true, connected = true, admitted = true, ready = true, name = "A", archetype = "warden"},
			join = {present = true, connected = false, admitted = true, ready = false, name = "B", archetype = ""}},
		np.Select{seq = 4, archetype = "ranger"},
		np.Ready{seq = 5, ready = true, seed = 1 << 60},
		np.Settings{seq = 6, difficulty = "hell", story = false},
		np.Admit{seq = 7, seat_gen = 3},
		np.Kick{seq = 8, seat_gen = 3},
		np.Start{session = 99, seed = max(u64), difficulty = "easy", story = true, host_name = "A", host_archetype = "rogue", join_name = "B", join_archetype = "rogue"},
		np.Pong{seq = 9, ts = 123},
		np.Error{code = .Run_Full, msg = "full \"quoted\"", fatal = true, seq = 2},
		np.Partner_Disconnected{grace_ms = 30_000},
		np.Partner_Rejoined{name = "B"},
		np.Partner_Left{reason = "bye"},
		np.Result_Ack{result = 1 << 63},
		np.Bye{},
		np.Suspend{},
	}
	for m in msgs {
		bytes := np.encode(m, context.temp_allocator)
		testing.expectf(t, np.json_validate(bytes) == .None, "encoder produced invalid JSON: %s", string(bytes))
		back, _, err := np.decode_control(bytes, context.temp_allocator)
		testing.expectf(t, err == .None, "%s -> %v", string(bytes), err)
		again := np.encode(back, context.temp_allocator)
		testing.expectf(t, string(again) == string(bytes), "round trip drift:\n%s\n%s", string(bytes), string(again))
	}
}

@(test)
net_control_decoder_rejects_invalid_fields :: proc(t: ^testing.T) {
	bad := []string{
		`{"seq":1}`,                                                        // no type
		`{"t":7}`,                                                          // non-string type
		`{"t":"hello","seq":0,"protocol":4,"game":"g","name":"n","room":"ABCD","role":"host"}`,     // seq must be positive
		`{"t":"hello","seq":true,"protocol":4,"game":"g","name":"n","room":"ABCD","role":"host"}`,  // booleans are not integers
		`{"t":"hello","seq":1.5,"protocol":4,"game":"g","name":"n","room":"ABCD","role":"host"}`,
		`{"t":"hello","seq":1,"protocol":4,"game":"g","name":"n","room":"ABCD","role":"admin"}`,
		`{"t":"hello","seq":1,"protocol":4,"game":"g h","name":"n","room":"ABCD","role":"host"}`,
		`{"t":"hello","seq":1,"protocol":4,"game":"g","name":"n","room":"ABCD","role":"join","token":"short"}`,
		`{"t":"select","seq":1,"archetype":"paladin"}`,
		`{"t":"settings","seq":1,"difficulty":"nightmare","story":true}`,
		`{"t":"admit","seq":1,"seat_gen":0}`,
		`{"t":"error","code":"x","msg":"m"}`, // missing fatal
	}
	for text in bad {
		_, _, err := np.decode_control(transmute([]byte)text, context.temp_allocator)
		testing.expectf(t, err != .None, "accepted %s", text)
	}
	_, typ, err := np.decode_control(transmute([]byte)string(`{"t":"warp","x":1}`), context.temp_allocator)
	testing.expect_value(t, err, np.Decode_Error.Unknown_Type)
	testing.expect_value(t, typ, np.Msg_Type.Unknown)
	_, typ, err = np.decode_control(transmute([]byte)string(`{"t":"snapshot","x":{"t":"hello"}}`), context.temp_allocator)
	testing.expect_value(t, err, np.Decode_Error.Not_Control)
	testing.expect_value(t, typ, np.Msg_Type.Snapshot)
}

@(test)
net_peek_type_reads_only_the_top_level_key :: proc(t: ^testing.T) {
	Case :: struct {
		text: string,
		want: np.Msg_Type,
		ok:   bool,
	}
	cases := []Case{
		{`{"t":"intent","b":1}`, .Intent, true},
		{`{"a":{"t":"hello"},"t":"snapshot"}`, .Snapshot, true},
		{`{"a":["t","hello"],"t":"intent"}`, .Intent, true},
		{`{"a":"t","t":"ping"}`, .Ping, true},
		{` { "x" : [ {"t":"bye"} ] , "t" : "run_ended" } `, .Run_Ended, true},
		{`{"a":{"t":"hello"}}`, .Unknown, false},
		{`{"t":"nope"}`, .Unknown, true},
	}
	for c in cases {
		typ, jerr, ok := np.peek_type(transmute([]byte)c.text)
		testing.expectf(t, jerr == .None, "%s json %v", c.text, jerr)
		testing.expectf(t, typ == c.want && ok == c.ok, "%s -> %v %v", c.text, typ, ok)
	}
}

@(test)
net_names_codes_and_tokens :: proc(t: ^testing.T) {
	testing.expect_value(t, np.sanitize_name("  Matti \t  R  ", context.temp_allocator), "Matti R")
	testing.expect_value(t, np.sanitize_name(concat("a", NUL, "b", ZWSP, "c", "\n", "d e"), context.temp_allocator), "abcd e")
	testing.expect_value(t, np.sanitize_name("ääääääääääääääääääää", context.temp_allocator), "ääääääääääääääää")
	testing.expect_value(t, np.sanitize_name("abcdefghijklmno pq", context.temp_allocator), "abcdefghijklmno")
	testing.expect_value(t, np.room_code_normalize(" abcd ", context.temp_allocator), "ABCD")
	testing.expect_value(t, np.room_code_normalize("AB0D", context.temp_allocator), "")
	testing.expect_value(t, np.room_code_normalize("ABCDE", context.temp_allocator), "")
	testing.expect(t, np.room_code_valid("Z9Z9"))
	testing.expect(t, !np.room_code_valid("abcd"))

	code := np.room_code_from_random({0, 31, 32, 255})
	testing.expect_value(t, string(code[:]), "A9A9"[:])

	// Seal mapping parity with the archive: sha256("ABCD") = e12e115a...
	first, second := np.room_code_seal(" abcd")
	testing.expect_value(t, first, 0xe1 % 18)
	testing.expect_value(t, second, 0x2e % 18)

	tok := np.token_from_random({0x00, 0x01, 0xab, 0xff, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x10}, context.temp_allocator)
	testing.expect_value(t, tok, "0001abff000000000000000000000010")
	testing.expect(t, np.token_well_formed(tok))
	testing.expect(t, !np.token_well_formed("0001ABFF000000000000000000000010"))
	testing.expect(t, np.token_equal(tok, "0001abff000000000000000000000010"))
	testing.expect(t, !np.token_equal(tok, "0001abff000000000000000000000011"))
}
