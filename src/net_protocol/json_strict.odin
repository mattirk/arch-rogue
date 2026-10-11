package net_protocol

// core:encoding/json is permissive (wrapping integer overflow, duplicate keys,
// trailing data, infinities). Every inbound message passes this strict
// structural validator first; typed readers below then parse the validated
// text. Invalid input fails closed with an error value, never a panic.

import "core:encoding/json"
import "core:math"
import "core:strconv"
import "core:strings"
import "core:unicode/utf8"

Json_Limits :: struct {
	max_bytes:        int,
	max_depth:        int,
	max_values:       int,
	max_string_bytes: int, // decoded-length upper bound of any one string
	max_key_bytes:    int,
}

DEFAULT_JSON_LIMITS :: Json_Limits{
	max_bytes        = MAX_MESSAGE_BYTES,
	max_depth        = 24,
	max_values       = 32_768,
	max_string_bytes = 200 * 1024,
	max_key_bytes    = 32,
}

Json_Error :: enum u8 {
	None,
	Empty,
	Too_Large,
	Bad_Utf8,
	Not_Object_Root,
	Syntax,
	Too_Deep,
	Too_Many_Values,
	String_Too_Long,
	Bad_String,
	Bad_Key,
	Duplicate_Key,
	Bad_Number,
	Trailing_Data,
}

@(private="file")
Validator :: struct {
	data:   []byte,
	pos:    int,
	depth:  int,
	values: int,
	limits: Json_Limits,
	keys:   [dynamic]string, // stack of keys of the currently open objects
	err:    Json_Error,
}

json_validate :: proc(data: []byte, limits := DEFAULT_JSON_LIMITS) -> Json_Error {
	if len(data) == 0 do return .Empty
	if len(data) > limits.max_bytes do return .Too_Large
	if !utf8.valid_string(string(data)) do return .Bad_Utf8
	v := Validator{data = data, limits = limits}
	v.keys = make([dynamic]string, 0, 32, context.temp_allocator)
	defer delete(v.keys)
	skip_ws(&v)
	if v.pos >= len(v.data) || v.data[v.pos] != '{' do return .Not_Object_Root
	if !value(&v) do return v.err == .None ? .Syntax : v.err
	skip_ws(&v)
	if v.pos != len(v.data) do return .Trailing_Data
	return .None

	fail :: proc(v: ^Validator, err: Json_Error) -> bool {
		if v.err == .None do v.err = err
		return false
	}

	skip_ws :: proc(v: ^Validator) {
		for v.pos < len(v.data) {
			switch v.data[v.pos] {
			case ' ', '\t', '\n', '\r': v.pos += 1
			case: return
			}
		}
	}

	value :: proc(v: ^Validator) -> bool {
		v.values += 1
		if v.values > v.limits.max_values do return fail(v, .Too_Many_Values)
		skip_ws(v)
		if v.pos >= len(v.data) do return fail(v, .Syntax)
		switch v.data[v.pos] {
		case '{': return object(v)
		case '[': return array(v)
		case '"':
			_, ok := str(v, false)
			return ok
		case 't': return literal(v, "true")
		case 'f': return literal(v, "false")
		case 'n': return literal(v, "null")
		case '-', '0'..='9': return number(v)
		}
		return fail(v, .Syntax)
	}

	literal :: proc(v: ^Validator, word: string) -> bool {
		if v.pos + len(word) > len(v.data) || string(v.data[v.pos:][:len(word)]) != word do return fail(v, .Syntax)
		v.pos += len(word)
		return true
	}

	object :: proc(v: ^Validator) -> bool {
		v.depth += 1
		if v.depth > v.limits.max_depth do return fail(v, .Too_Deep)
		v.pos += 1
		base := len(v.keys)
		defer resize(&v.keys, base)
		skip_ws(v)
		if v.pos < len(v.data) && v.data[v.pos] == '}' {
			v.pos += 1
			v.depth -= 1
			return true
		}
		for {
			skip_ws(v)
			if v.pos >= len(v.data) || v.data[v.pos] != '"' do return fail(v, .Syntax)
			key, ok := str(v, true)
			if !ok do return false
			for existing in v.keys[base:] do if existing == key do return fail(v, .Duplicate_Key)
			append(&v.keys, key)
			skip_ws(v)
			if v.pos >= len(v.data) || v.data[v.pos] != ':' do return fail(v, .Syntax)
			v.pos += 1
			if !value(v) do return false
			skip_ws(v)
			if v.pos >= len(v.data) do return fail(v, .Syntax)
			if v.data[v.pos] == ',' {
				v.pos += 1
				continue
			}
			if v.data[v.pos] == '}' {
				v.pos += 1
				v.depth -= 1
				return true
			}
			return fail(v, .Syntax)
		}
	}

	array :: proc(v: ^Validator) -> bool {
		v.depth += 1
		if v.depth > v.limits.max_depth do return fail(v, .Too_Deep)
		v.pos += 1
		skip_ws(v)
		if v.pos < len(v.data) && v.data[v.pos] == ']' {
			v.pos += 1
			v.depth -= 1
			return true
		}
		for {
			if !value(v) do return false
			skip_ws(v)
			if v.pos >= len(v.data) do return fail(v, .Syntax)
			if v.data[v.pos] == ',' {
				v.pos += 1
				continue
			}
			if v.data[v.pos] == ']' {
				v.pos += 1
				v.depth -= 1
				return true
			}
			return fail(v, .Syntax)
		}
	}

	// Keys are restricted to short ASCII identifiers without escapes, so
	// duplicate detection compares exact bytes with no aliasing.
	str :: proc(v: ^Validator, is_key: bool) -> (text: string, ok: bool) {
		v.pos += 1
		start := v.pos
		decoded := 0
		for v.pos < len(v.data) {
			c := v.data[v.pos]
			switch {
			case c == '"':
				text = string(v.data[start:v.pos])
				v.pos += 1
				if is_key {
					if len(text) == 0 || len(text) > v.limits.max_key_bytes do return "", fail(v, .Bad_Key)
					for b in transmute([]byte)text {
						if !(b == '_' || ('a' <= b && b <= 'z') || ('A' <= b && b <= 'Z') || ('0' <= b && b <= '9')) {
							return "", fail(v, .Bad_Key)
						}
					}
				}
				return text, true
			case c < 0x20:
				return "", fail(v, .Bad_String)
			case c == '\\':
				if is_key do return "", fail(v, .Bad_Key)
				v.pos += 1
				if v.pos >= len(v.data) do return "", fail(v, .Bad_String)
				switch v.data[v.pos] {
				case '"', '\\', '/', 'b', 'f', 'n', 'r', 't':
					v.pos += 1
				case 'u':
					cp, hex_ok := hex4(v)
					if !hex_ok do return "", fail(v, .Bad_String)
					if 0xDC00 <= cp && cp <= 0xDFFF do return "", fail(v, .Bad_String)
					if 0xD800 <= cp && cp <= 0xDBFF {
						if v.pos + 1 >= len(v.data) || v.data[v.pos] != '\\' || v.data[v.pos + 1] != 'u' {
							return "", fail(v, .Bad_String)
						}
						v.pos += 1
						low, low_ok := hex4(v)
						if !low_ok || low < 0xDC00 || low > 0xDFFF do return "", fail(v, .Bad_String)
					}
				case:
					return "", fail(v, .Bad_String)
				}
			case:
				v.pos += 1
			}
			decoded += 1
			if decoded > v.limits.max_string_bytes do return "", fail(v, .String_Too_Long)
		}
		return "", fail(v, .Syntax)
	}

	hex4 :: proc(v: ^Validator) -> (cp: u32, ok: bool) {
		v.pos += 1 // skip 'u'
		if v.pos + 4 > len(v.data) do return 0, false
		for i in 0 ..< 4 {
			c := v.data[v.pos + i]
			d: u32
			switch c {
			case '0'..='9': d = u32(c - '0')
			case 'a'..='f': d = u32(c - 'a' + 10)
			case 'A'..='F': d = u32(c - 'A' + 10)
			case: return 0, false
			}
			cp = cp * 16 + d
		}
		v.pos += 4
		return cp, true
	}

	number :: proc(v: ^Validator) -> bool {
		start := v.pos
		if v.data[v.pos] == '-' do v.pos += 1
		if v.pos >= len(v.data) do return fail(v, .Bad_Number)
		if v.data[v.pos] == '0' {
			v.pos += 1
		} else if '1' <= v.data[v.pos] && v.data[v.pos] <= '9' {
			for v.pos < len(v.data) && '0' <= v.data[v.pos] && v.data[v.pos] <= '9' do v.pos += 1
		} else {
			return fail(v, .Bad_Number)
		}
		is_float := false
		if v.pos < len(v.data) && v.data[v.pos] == '.' {
			is_float = true
			v.pos += 1
			digits := 0
			for v.pos < len(v.data) && '0' <= v.data[v.pos] && v.data[v.pos] <= '9' {
				v.pos += 1
				digits += 1
			}
			if digits == 0 do return fail(v, .Bad_Number)
		}
		if v.pos < len(v.data) && (v.data[v.pos] == 'e' || v.data[v.pos] == 'E') {
			is_float = true
			v.pos += 1
			if v.pos < len(v.data) && (v.data[v.pos] == '+' || v.data[v.pos] == '-') do v.pos += 1
			digits := 0
			for v.pos < len(v.data) && '0' <= v.data[v.pos] && v.data[v.pos] <= '9' {
				v.pos += 1
				digits += 1
			}
			if digits == 0 do return fail(v, .Bad_Number)
		}
		text := string(v.data[start:v.pos])
		if len(text) > 40 do return fail(v, .Bad_Number)
		if is_float {
			f, ok := strconv.parse_f64(text)
			if !ok || math.is_nan(f) || math.is_inf(f) do return fail(v, .Bad_Number)
		} else {
			// Bare integers must fit i64, or u64 when non-negative (embedded
			// game structs carry u64 fields). Protocol-level 64-bit identities
			// still travel as decimal strings for JavaScript safety.
			if _, ok := i64_parse_strict(text); !ok {
				if _, uok := u64_parse_canonical(text); !uok do return fail(v, .Bad_Number)
			}
		}
		return true
	}
}

// ---------------------------------------------------------------- reading --

// Parses already-validated text into a json.Object owned by allocator.
json_parse_object :: proc(data: []byte, allocator := context.allocator) -> (obj: json.Object, root: json.Value, ok: bool) {
	value, err := json.parse(data, .JSON, true, allocator)
	if err != .None {
		json.destroy_value(value, allocator)
		return nil, nil, false
	}
	o, is_obj := value.(json.Object)
	if !is_obj {
		json.destroy_value(value, allocator)
		return nil, nil, false
	}
	return o, value, true
}

read_str :: proc(o: json.Object, key: string, max_bytes: int) -> (string, bool) {
	v, present := o[key]
	if !present do return "", false
	s, is_str := v.(json.String)
	if !is_str || len(s) > max_bytes do return "", false
	return string(s), true
}

read_opt_str :: proc(o: json.Object, key: string, max_bytes: int) -> (string, bool) {
	if key not_in o do return "", true
	return read_str(o, key, max_bytes)
}

read_int :: proc(o: json.Object, key: string, lo, hi: i64) -> (i64, bool) {
	v, present := o[key]
	if !present do return 0, false
	n, is_int := v.(json.Integer)
	if !is_int || n < lo || n > hi do return 0, false
	return i64(n), true
}

read_opt_int :: proc(o: json.Object, key: string, lo, hi: i64, fallback: i64 = 0) -> (i64, bool) {
	if key not_in o do return fallback, true
	return read_int(o, key, lo, hi)
}

read_bool :: proc(o: json.Object, key: string) -> (bool, bool) {
	v, present := o[key]
	if !present do return false, false
	b, is_bool := v.(json.Boolean)
	return bool(b), is_bool
}

read_f32 :: proc(o: json.Object, key: string, lo, hi: f32) -> (f32, bool) {
	v, present := o[key]
	if !present do return 0, false
	f: f64
	#partial switch n in v {
	case json.Integer: f = f64(n)
	case json.Float: f = f64(n)
	case: return 0, false
	}
	if math.is_nan(f) || f < f64(lo) || f > f64(hi) do return 0, false
	return f32(f), true
}

read_object :: proc(o: json.Object, key: string) -> (json.Object, bool) {
	v, present := o[key]
	if !present do return nil, false
	sub, is_obj := v.(json.Object)
	return sub, is_obj
}

read_array :: proc(o: json.Object, key: string, max_len: int) -> (json.Array, bool) {
	v, present := o[key]
	if !present do return nil, false
	arr, is_arr := v.(json.Array)
	if !is_arr || len(arr) > max_len do return nil, false
	return arr, true
}

// Canonical unsigned decimal strings: no sign, no leading zeros, fits u64.
u64_parse_canonical :: proc(text: string) -> (u64, bool) {
	if len(text) == 0 || len(text) > 20 do return 0, false
	if len(text) > 1 && text[0] == '0' do return 0, false
	value: u64
	for c in transmute([]byte)text {
		if c < '0' || c > '9' do return 0, false
		d := u64(c - '0')
		if value > (max(u64) - d) / 10 do return 0, false
		value = value * 10 + d
	}
	return value, true
}

// Decimal integer with an optional leading '-', rejecting i64 overflow
// (core:strconv wraps silently).
i64_parse_strict :: proc(text: string) -> (i64, bool) {
	digits := text
	negative := false
	if len(digits) > 0 && digits[0] == '-' {
		negative = true
		digits = digits[1:]
	}
	if len(digits) == 0 || len(digits) > 19 do return 0, false
	magnitude: u64
	for c in transmute([]byte)digits {
		if c < '0' || c > '9' do return 0, false
		magnitude = magnitude * 10 + u64(c - '0')
	}
	limit := negative ? u64(1) << 63 : (u64(1) << 63) - 1
	if magnitude > limit do return 0, false
	if negative do return -i64(magnitude - 1) - 1, true
	return i64(magnitude), true
}

read_u64s :: proc(o: json.Object, key: string) -> (u64, bool) {
	s, ok := read_str(o, key, 20)
	if !ok do return 0, false
	return u64_parse_canonical(s)
}

// ---------------------------------------------------------------- writing --

// Minimal compact JSON writer for wire messages. Callers write keys in a
// fixed order; strings are escaped per RFC 8259.
Json_Writer :: struct {
	b:     strings.Builder,
	first: [32]bool,
	depth: int,
}

jw_init :: proc(w: ^Json_Writer, allocator := context.allocator) {
	w.b = strings.builder_make(0, 256, allocator)
	w.depth = 0
}

jw_destroy :: proc(w: ^Json_Writer) {
	strings.builder_destroy(&w.b)
}

jw_bytes :: proc(w: ^Json_Writer) -> []byte {
	return w.b.buf[:]
}

@(private="file")
jw_sep :: proc(w: ^Json_Writer) {
	if w.depth == 0 do return
	if w.first[w.depth] {
		w.first[w.depth] = false
	} else {
		strings.write_byte(&w.b, ',')
	}
}

jw_begin :: proc(w: ^Json_Writer) {
	jw_sep(w)
	strings.write_byte(&w.b, '{')
	w.depth += 1
	w.first[w.depth] = true
}

jw_end :: proc(w: ^Json_Writer) {
	strings.write_byte(&w.b, '}')
	w.depth -= 1
}

jw_begin_array :: proc(w: ^Json_Writer) {
	jw_sep(w)
	strings.write_byte(&w.b, '[')
	w.depth += 1
	w.first[w.depth] = true
}

jw_end_array :: proc(w: ^Json_Writer) {
	strings.write_byte(&w.b, ']')
	w.depth -= 1
}

jw_key :: proc(w: ^Json_Writer, key: string) {
	jw_sep(w)
	strings.write_byte(&w.b, '"')
	strings.write_string(&w.b, key)
	strings.write_string(&w.b, "\":")
	// The value that follows must not emit another separator.
	w.depth += 1
	w.first[w.depth] = true
}

@(private="file")
jw_after_value :: proc(w: ^Json_Writer, keyed: bool) {
	if keyed do w.depth -= 1
}

jw_string_raw :: proc(w: ^Json_Writer, s: string) {
	strings.write_byte(&w.b, '"')
	for r in s {
		switch r {
		case '"':  strings.write_string(&w.b, "\\\"")
		case '\\': strings.write_string(&w.b, "\\\\")
		case '\n': strings.write_string(&w.b, "\\n")
		case '\r': strings.write_string(&w.b, "\\r")
		case '\t': strings.write_string(&w.b, "\\t")
		case 0 ..< 0x20, 0x7f, utf8.RUNE_ERROR:
			if r == utf8.RUNE_ERROR {
				strings.write_string(&w.b, "\\ufffd")
			} else {
				hex := "0123456789abcdef"
				strings.write_string(&w.b, "\\u00")
				strings.write_byte(&w.b, hex[(r >> 4) & 0xf])
				strings.write_byte(&w.b, hex[r & 0xf])
			}
		case: strings.write_rune(&w.b, r)
		}
	}
	strings.write_byte(&w.b, '"')
}

jw_str :: proc(w: ^Json_Writer, key: string, value: string) {
	jw_key(w, key)
	jw_string_raw(w, value)
	jw_after_value(w, true)
}

jw_int :: proc(w: ^Json_Writer, key: string, value: i64) {
	jw_key(w, key)
	strings.write_i64(&w.b, value)
	jw_after_value(w, true)
}

jw_u64s :: proc(w: ^Json_Writer, key: string, value: u64) {
	jw_key(w, key)
	strings.write_byte(&w.b, '"')
	strings.write_u64(&w.b, value)
	strings.write_byte(&w.b, '"')
	jw_after_value(w, true)
}

jw_bool :: proc(w: ^Json_Writer, key: string, value: bool) {
	jw_key(w, key)
	strings.write_string(&w.b, value ? "true" : "false")
	jw_after_value(w, true)
}

// Finite floats only; non-finite values are written as 0 rather than emitting
// invalid JSON. Three decimals is ample for tile-space positions.
jw_f32 :: proc(w: ^Json_Writer, key: string, value: f32) {
	jw_key(w, key)
	jw_f32_raw(w, value)
	jw_after_value(w, true)
}

jw_f32_raw :: proc(w: ^Json_Writer, value: f32) {
	v := value
	if math.is_nan(v) || math.is_inf(v) do v = 0
	scaled := i64(math.round(f64(v) * 1000))
	if scaled < 0 {
		strings.write_byte(&w.b, '-')
		scaled = -scaled
	}
	strings.write_i64(&w.b, scaled / 1000)
	frac := scaled % 1000
	if frac != 0 {
		strings.write_byte(&w.b, '.')
		digits := [3]byte{byte('0' + frac / 100), byte('0' + (frac / 10) % 10), byte('0' + frac % 10)}
		n := 3
		for n > 1 && digits[n - 1] == '0' do n -= 1
		strings.write_bytes(&w.b, digits[:n])
	}
}

jw_begin_obj_key :: proc(w: ^Json_Writer, key: string) {
	jw_key(w, key)
	w.depth -= 1 // jw_begin re-enters; the key already emitted its separator
	strings.write_byte(&w.b, '{')
	w.depth += 1
	w.first[w.depth] = true
}

jw_begin_array_key :: proc(w: ^Json_Writer, key: string) {
	jw_key(w, key)
	w.depth -= 1
	strings.write_byte(&w.b, '[')
	w.depth += 1
	w.first[w.depth] = true
}

// Inserts an already-encoded JSON value under key. Callers pass output of a
// trusted encoder (json.marshal); receivers still validate the whole message.
jw_raw :: proc(w: ^Json_Writer, key: string, value: []byte) {
	jw_key(w, key)
	strings.write_bytes(&w.b, value)
	w.depth -= 1
}

// Array element helpers (no key).
jw_elem_int :: proc(w: ^Json_Writer, value: i64) {
	jw_sep(w)
	strings.write_i64(&w.b, value)
}

jw_elem_f32 :: proc(w: ^Json_Writer, value: f32) {
	jw_sep(w)
	jw_f32_raw(w, value)
}

jw_elem_str :: proc(w: ^Json_Writer, value: string) {
	jw_sep(w)
	jw_string_raw(w, value)
}

// Raw member values of the object stored under top-level `key` in an already
// validated document: each value slice borrows `data`. Used to hand embedded
// sections to a typed decoder without a lossy intermediate json.Value.
raw_object_members :: proc(data: []byte, key: string, allocator := context.temp_allocator) -> (members: map[string][]byte, found: bool) {
	members = make(map[string][]byte, 8, allocator)
	i := skip_ws_at(data, 0)
	if i >= len(data) || data[i] != '{' do return members, false
	i += 1
	for {
		i = skip_ws_at(data, i)
		if i >= len(data) || data[i] == '}' do return members, false
		k, after_key := scan_string(data, i)
		i = skip_ws_at(data, after_key) + 1 // ':'
		i = skip_ws_at(data, i)
		end := scan_value(data, i)
		if k == key {
			if data[i] != '{' do return members, false
			j := i + 1
			for {
				j = skip_ws_at(data, j)
				if j >= len(data) || data[j] == '}' do return members, true
				mk, after := scan_string(data, j)
				j = skip_ws_at(data, after) + 1
				j = skip_ws_at(data, j)
				mend := scan_value(data, j)
				members[mk] = data[j:mend]
				j = skip_ws_at(data, mend)
				if j < len(data) && data[j] == ',' do j += 1
			}
		}
		i = skip_ws_at(data, end)
		if i < len(data) && data[i] == ',' do i += 1
	}

	skip_ws_at :: proc(data: []byte, i: int) -> int {
		j := i
		for j < len(data) && (data[j] == ' ' || data[j] == '\t' || data[j] == '\n' || data[j] == '\r') do j += 1
		return j
	}
	// Keys never contain escapes (validator rule).
	scan_string :: proc(data: []byte, i: int) -> (text: string, end: int) {
		j := i + 1
		for j < len(data) && data[j] != '"' {
			if data[j] == '\\' do j += 1
			j += 1
		}
		return string(data[i + 1:min(j, len(data))]), j + 1
	}
	scan_value :: proc(data: []byte, i: int) -> int {
		if i >= len(data) do return i
		switch data[i] {
		case '"':
			_, end := scan_string(data, i)
			return end
		case '{', '[':
			depth := 0
			j := i
			for j < len(data) {
				switch data[j] {
				case '"':
					_, end := scan_string(data, j)
					j = end
					continue
				case '{', '[': depth += 1
				case '}', ']':
					depth -= 1
					if depth == 0 do return j + 1
				}
				j += 1
			}
			return j
		}
		j := i
		for j < len(data) && data[j] != ',' && data[j] != '}' && data[j] != ']' && data[j] != ' ' && data[j] != '\n' do j += 1
		return j
	}
}
