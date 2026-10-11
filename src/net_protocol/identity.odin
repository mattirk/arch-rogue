package net_protocol

import "core:strings"
import "core:unicode"
import "core:unicode/utf8"

// Display names are self-chosen, not identities. Keep ASCII space and visible
// graphic code points only (control, format, and other whitespace characters
// are dropped), collapse space runs, trim, and cap at 16 code points
// (arch-rogue-python/src/arch_rogue_protocol/wire.py sanitize_player_name).
// Applied on every boundary.
sanitize_name :: proc(name: string, allocator := context.allocator) -> string {
	b := strings.builder_make(0, len(name), allocator)
	count := 0
	pending_space := false
	for r in name {
		if count >= NAME_MAX_CODEPOINTS do break
		if r == ' ' {
			pending_space = count > 0
			continue
		}
		if r == utf8.RUNE_ERROR || !unicode.is_graphic(r) || unicode.is_space(r) do continue
		if pending_space {
			if count + 1 >= NAME_MAX_CODEPOINTS do break
			strings.write_byte(&b, ' ')
			count += 1
			pending_space = false
		}
		strings.write_rune(&b, r)
		count += 1
	}
	return strings.to_string(b)
}

name_is_sanitized :: proc(name: string) -> bool {
	clean := sanitize_name(name, context.temp_allocator)
	return clean == name
}

// Uppercases and trims entry text; returns "" for anything that cannot be a
// room code, so callers can disable Join without guessing.
room_code_normalize :: proc(text: string, allocator := context.allocator) -> string {
	trimmed := strings.trim_space(text)
	if len(trimmed) != ROOM_CODE_LENGTH do return ""
	out := make([]byte, ROOM_CODE_LENGTH, allocator)
	for i in 0 ..< ROOM_CODE_LENGTH {
		c := trimmed[i]
		if 'a' <= c && c <= 'z' do c -= 32
		if strings.index_byte(ROOM_CODE_ALPHABET, c) < 0 {
			delete(out, allocator)
			return ""
		}
		out[i] = c
	}
	return string(out)
}

room_code_valid :: proc(code: string) -> bool {
	if len(code) != ROOM_CODE_LENGTH do return false
	for i in 0 ..< len(code) do if strings.index_byte(ROOM_CODE_ALPHABET, code[i]) < 0 do return false
	return true
}

// Builds a code from caller-supplied cryptographic random bytes. The 32-letter
// alphabet divides 256, so a plain modulo stays uniform.
room_code_from_random :: proc(random: [ROOM_CODE_LENGTH]byte) -> [ROOM_CODE_LENGTH]byte {
	out: [ROOM_CODE_LENGTH]byte
	alphabet := ROOM_CODE_ALPHABET
	for i in 0 ..< ROOM_CODE_LENGTH do out[i] = alphabet[int(random[i]) % len(alphabet)]
	return out
}

// Two-sigil verification seal: SHA-256 of the uppercase code, first two digest
// bytes modulo the frozen vocabulary (arch-rogue-python/src/arch_rogue/menus/mp.py
// _mp_code_seal). Catches mistyped codes; not authentication.
room_code_seal :: proc(code: string) -> (first, second: int) {
	upper := strings.to_upper(strings.trim_space(code), context.temp_allocator)
	digest := sha256_digest(transmute([]byte)upper)
	return int(digest[0]) % len(SEAL_SIGILS), int(digest[1]) % len(SEAL_SIGILS)
}

token_from_random :: proc(random: [TOKEN_BYTES]byte, allocator := context.allocator) -> string {
	hex := "0123456789abcdef"
	out := make([]byte, TOKEN_HEX_LENGTH, allocator)
	for b, i in random {
		out[i * 2] = hex[b >> 4]
		out[i * 2 + 1] = hex[b & 0xf]
	}
	return string(out)
}

token_well_formed :: proc(token: string) -> bool {
	if len(token) != TOKEN_HEX_LENGTH do return false
	for c in transmute([]byte)token do if !(('0' <= c && c <= '9') || ('a' <= c && c <= 'f')) do return false
	return true
}

// Constant-time comparison for reconnect tokens of equal, fixed length.
token_equal :: proc(a, b: string) -> bool {
	if len(a) != len(b) do return false
	diff: byte = 0
	for i in 0 ..< len(a) do diff |= a[i] ~ b[i]
	return diff == 0
}

game_id_valid :: proc(id: string) -> bool {
	if len(id) == 0 || len(id) > GAME_ID_MAX_BYTES do return false
	for c in transmute([]byte)id {
		if !(('0' <= c && c <= '9') || ('a' <= c && c <= 'z') || ('A' <= c && c <= 'Z') || c == '.' || c == '-' || c == '+' || c == '_') {
			return false
		}
	}
	return true
}
