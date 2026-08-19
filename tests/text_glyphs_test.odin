package archrogue_tests

// Global source-level contract for every string literal that can flow into the
// default raylib font. The vendored font owns 224 consecutive glyphs,
// U+0020..U+00FF; tab and line feed are accepted layout controls. Comments
// are deliberately ignored so source documentation can use
// richer punctuation without weakening the player-visible text contract.

import "core:os"
import "core:strings"
import "core:testing"

Text_Glyph_Issue_Kind :: enum u8 {
	None,
	Unsupported_Codepoint,
	Invalid_UTF8,
	Invalid_Escape,
	Unterminated_String,
	Unterminated_Block_Comment,
}

Text_Glyph_Issue :: struct {
	kind:      Text_Glyph_Issue_Kind,
	codepoint: i32,
	line:      int,
	column:    int,
}

Text_Glyph_Source_State :: enum u8 {
	Code,
	Line_Comment,
	Block_Comment,
	String,
	Raw_String,
	Rune,
}

Text_Glyph_UTF8_Stream :: struct {
	bytes:  [4]u8,
	count:  int,
	width:  int,
	line:   int,
	column: int,
}

Text_Glyph_Escape :: struct {
	bytes: [4]u8,
	count: int,
	next:  int,
	valid: bool,
}

// `#directory` is bound to this source file at compile time, so the audit does
// not depend on the test process's working directory.
TEXT_GLYPH_SOURCE_ROOT :: #directory + "../src"

@(private = "file")
text_glyph_is_layout_control :: proc(codepoint: i32) -> bool {
	return codepoint == '\t' || codepoint == '\n'
}

@(private = "file")
text_glyph_is_default_font_supported :: proc(codepoint: i32) -> bool {
	return text_glyph_is_layout_control(codepoint) || (0x20 <= codepoint && codepoint <= 0xff)
}

@(private = "file")
text_glyph_is_continuation :: proc(value: u8) -> bool {
	return (value & 0xc0) == 0x80
}

// Strict UTF-8 decoding rejects overlong forms, surrogate codepoints, and
// values beyond Unicode's U+10FFFF ceiling.
@(private = "file")
text_glyph_decode_utf8 :: proc(text: string, index: int) -> (codepoint: i32, width: int, valid: bool) {
	if index < 0 || index >= len(text) do return 0, 0, false
	first := u8(text[index])
	if first < 0x80 do return i32(first), 1, true

	if 0xc2 <= first && first <= 0xdf {
		if index + 1 >= len(text) do return 0, 1, false
		second := u8(text[index + 1])
		if !text_glyph_is_continuation(second) do return 0, 1, false
		return i32(first & 0x1f) << 6 | i32(second & 0x3f), 2, true
	}

	if 0xe0 <= first && first <= 0xef {
		if index + 2 >= len(text) do return 0, 1, false
		second, third := u8(text[index + 1]), u8(text[index + 2])
		if !text_glyph_is_continuation(second) || !text_glyph_is_continuation(third) do return 0, 1, false
		codepoint = i32(first & 0x0f) << 12 | i32(second & 0x3f) << 6 | i32(third & 0x3f)
		if codepoint < 0x800 || (0xd800 <= codepoint && codepoint <= 0xdfff) do return 0, 1, false
		return codepoint, 3, true
	}

	if 0xf0 <= first && first <= 0xf4 {
		if index + 3 >= len(text) do return 0, 1, false
		second, third, fourth := u8(text[index + 1]), u8(text[index + 2]), u8(text[index + 3])
		if !text_glyph_is_continuation(second) || !text_glyph_is_continuation(third) ||
			!text_glyph_is_continuation(fourth) {
			return 0, 1, false
		}
		codepoint = i32(first & 0x07) << 18 | i32(second & 0x3f) << 12 |
			i32(third & 0x3f) << 6 | i32(fourth & 0x3f)
		if codepoint < 0x10000 || codepoint > 0x10ffff do return 0, 1, false
		return codepoint, 4, true
	}

	return 0, 1, false
}

@(private = "file")
text_glyph_hex_digit :: proc(value: u8) -> (digit: i32, valid: bool) {
	if '0' <= value && value <= '9' do return i32(value - '0'), true
	if 'a' <= value && value <= 'f' do return i32(value - 'a') + 10, true
	if 'A' <= value && value <= 'F' do return i32(value - 'A') + 10, true
	return 0, false
}

@(private = "file")
text_glyph_parse_fixed_hex :: proc(text: string, start, count: int) -> (codepoint: i32, next: int, valid: bool) {
	if count <= 0 || start < 0 || start + count > len(text) do return 0, start, false
	for index in start ..< start + count {
		digit, ok := text_glyph_hex_digit(u8(text[index]))
		if !ok do return 0, start, false
		codepoint = codepoint * 16 + digit
	}
	return codepoint, start + count, true
}

@(private = "file")
text_glyph_parse_fixed_octal :: proc(text: string, start, count: int) -> (value: i32, next: int, valid: bool) {
	if count <= 0 || start < 0 || start + count > len(text) do return 0, start, false
	for index in start ..< start + count {
		byte := u8(text[index])
		if byte < '0' || byte > '7' do return 0, start, false
		value = value * 8 + i32(byte - '0')
	}
	return value, start + count, value <= 0xff
}

@(private = "file")
text_glyph_encode_utf8 :: proc(codepoint: i32) -> (bytes: [4]u8, count: int, valid: bool) {
	if codepoint < 0 || codepoint > 0x10ffff || (0xd800 <= codepoint && codepoint <= 0xdfff) {
		return {}, 0, false
	}
	if codepoint <= 0x7f {
		bytes[0] = u8(codepoint)
		return bytes, 1, true
	}
	if codepoint <= 0x7ff {
		bytes[0] = u8(0xc0 | codepoint >> 6)
		bytes[1] = u8(0x80 | codepoint & 0x3f)
		return bytes, 2, true
	}
	if codepoint <= 0xffff {
		bytes[0] = u8(0xe0 | codepoint >> 12)
		bytes[1] = u8(0x80 | codepoint >> 6 & 0x3f)
		bytes[2] = u8(0x80 | codepoint & 0x3f)
		return bytes, 3, true
	}
	bytes[0] = u8(0xf0 | codepoint >> 18)
	bytes[1] = u8(0x80 | codepoint >> 12 & 0x3f)
	bytes[2] = u8(0x80 | codepoint >> 6 & 0x3f)
	bytes[3] = u8(0x80 | codepoint & 0x3f)
	return bytes, 4, true
}

// Feed the bytes that an Odin literal emits into one strict UTF-8 stream.
// This is intentionally byte-oriented: `"\\xE2\\x80\\x94"` must decode to
// U+2014 rather than masquerading as three individually supported values.
@(private = "file")
text_glyph_push_runtime_byte :: proc(stream: ^Text_Glyph_UTF8_Stream, value: u8, line, column: int) -> Text_Glyph_Issue {
	if stream.count == 0 {
		if value < 0x80 {
			codepoint := i32(value)
			if !text_glyph_is_default_font_supported(codepoint) {
				return {kind = .Unsupported_Codepoint, codepoint = codepoint, line = line, column = column}
			}
			return {}
		}

		switch {
		case 0xc2 <= value && value <= 0xdf:
			stream.width = 2
		case 0xe0 <= value && value <= 0xef:
			stream.width = 3
		case 0xf0 <= value && value <= 0xf4:
			stream.width = 4
		case:
			return {kind = .Invalid_UTF8, line = line, column = column}
		}
		stream.bytes[0] = value
		stream.count = 1
		stream.line = line
		stream.column = column
		return {}
	}

	if !text_glyph_is_continuation(value) {
		return {kind = .Invalid_UTF8, line = stream.line, column = stream.column}
	}
	stream.bytes[stream.count] = value
	stream.count += 1
	if stream.count < stream.width do return {}

	issue_line, issue_column := stream.line, stream.column
	codepoint, _, valid := text_glyph_decode_utf8(string(stream.bytes[:stream.width]), 0)
	stream.count = 0
	stream.width = 0
	if !valid do return {kind = .Invalid_UTF8, line = issue_line, column = issue_column}
	if !text_glyph_is_default_font_supported(codepoint) {
		return {kind = .Unsupported_Codepoint, codepoint = codepoint, line = issue_line, column = issue_column}
	}
	return {}
}

@(private = "file")
text_glyph_finish_runtime_utf8 :: proc(stream: ^Text_Glyph_UTF8_Stream) -> Text_Glyph_Issue {
	if stream.count > 0 do return {kind = .Invalid_UTF8, line = stream.line, column = stream.column}
	return {}
}

@(private = "file")
text_glyph_single_byte_escape :: proc(value: u8, next: int) -> Text_Glyph_Escape {
	result := Text_Glyph_Escape{count = 1, next = next, valid = true}
	result.bytes[0] = value
	return result
}

// Decode the bytes emitted by every Odin interpreted-string escape. Octal and
// `\\x` escapes emit raw bytes; `\\u` and `\\U` emit UTF-8 for a codepoint.
@(private = "file")
text_glyph_decode_escape :: proc(text: string, slash: int) -> Text_Glyph_Escape {
	if slash < 0 || slash + 1 >= len(text) || text[slash] != '\\' {
		return {next = slash, valid = false}
	}
	escape := u8(text[slash + 1])
	if '0' <= escape && escape <= '7' {
		value, next, valid := text_glyph_parse_fixed_octal(text, slash + 1, 3)
		if !valid do return {next = slash, valid = false}
		return text_glyph_single_byte_escape(u8(value), next)
	}

	switch escape {
	case 'n':
		return text_glyph_single_byte_escape('\n', slash + 2)
	case 'r':
		return text_glyph_single_byte_escape('\r', slash + 2)
	case 't':
		return text_glyph_single_byte_escape('\t', slash + 2)
	case 'a':
		return text_glyph_single_byte_escape(0x07, slash + 2)
	case 'b':
		return text_glyph_single_byte_escape(0x08, slash + 2)
	case 'e':
		return text_glyph_single_byte_escape(0x1b, slash + 2)
	case 'f':
		return text_glyph_single_byte_escape(0x0c, slash + 2)
	case 'v':
		return text_glyph_single_byte_escape(0x0b, slash + 2)
	case '\\', '"', 0x27:
		return text_glyph_single_byte_escape(escape, slash + 2)
	case 'x':
		value, next, valid := text_glyph_parse_fixed_hex(text, slash + 2, 2)
		if !valid do return {next = slash, valid = false}
		return text_glyph_single_byte_escape(u8(value), next)
	case 'u', 'U':
		digit_count := escape == 'u' ? 4 : 8
		codepoint, next, valid := text_glyph_parse_fixed_hex(text, slash + 2, digit_count)
		if !valid do return {next = slash, valid = false}
		result := Text_Glyph_Escape{next = next}
		result.bytes, result.count, result.valid = text_glyph_encode_utf8(codepoint)
		return result
	}
	return {next = slash, valid = false}
}

@(private = "file")
text_glyph_text_issue :: proc(text: string) -> Text_Glyph_Issue {
	index := 0
	for index < len(text) {
		codepoint, width, valid := text_glyph_decode_utf8(text, index)
		if !valid do return {kind = .Invalid_UTF8, line = 1, column = index + 1}
		if !text_glyph_is_default_font_supported(codepoint) {
			return {kind = .Unsupported_Codepoint, codepoint = codepoint, line = 1, column = index + 1}
		}
		index += width
	}
	return {}
}

@(private = "file")
text_glyph_source_issue :: proc(source: string) -> Text_Glyph_Issue {
	state := Text_Glyph_Source_State.Code
	block_depth := 0
	index := 0
	line, column := 1, 1
	utf8_stream: Text_Glyph_UTF8_Stream

	for index < len(source) {
		value := u8(source[index])
		switch state {
		case .Code:
			if value == '/' && index + 1 < len(source) && source[index + 1] == '/' {
				state = .Line_Comment
				index += 2
				column += 2
				continue
			}
			if value == '/' && index + 1 < len(source) && source[index + 1] == '*' {
				state = .Block_Comment
				block_depth = 1
				index += 2
				column += 2
				continue
			}
			if value == '"' {
				state = .String
				utf8_stream = {}
				index += 1
				column += 1
				continue
			}
			if value == '`' {
				state = .Raw_String
				utf8_stream = {}
				index += 1
				column += 1
				continue
			}
			if value == 0x27 {
				state = .Rune
				index += 1
				column += 1
				continue
			}
		case .Line_Comment:
			if value == '\n' do state = .Code
		case .Block_Comment:
			if value == '/' && index + 1 < len(source) && source[index + 1] == '*' {
				block_depth += 1
				index += 2
				column += 2
				continue
			}
			if value == '*' && index + 1 < len(source) && source[index + 1] == '/' {
				block_depth -= 1
				index += 2
				column += 2
				if block_depth == 0 do state = .Code
				continue
			}
		case .Rune:
			if value == '\\' {
				if index + 1 >= len(source) do return {kind = .Invalid_Escape, line = line, column = column}
				if source[index + 1] == '\n' {
					index += 2
					line += 1
					column = 1
				} else {
					index += 2
					column += 2
				}
				continue
			}
			if value == 0x27 {
				state = .Code
				index += 1
				column += 1
				continue
			}
		case .String:
			if value == '"' {
				issue := text_glyph_finish_runtime_utf8(&utf8_stream)
				if issue.kind != .None do return issue
				state = .Code
				index += 1
				column += 1
				continue
			}
			if value == '\\' {
				escape_line, escape_column := line, column
				escape := text_glyph_decode_escape(source, index)
				if !escape.valid do return {kind = .Invalid_Escape, line = escape_line, column = escape_column}
				for byte in escape.bytes[:escape.count] {
					issue := text_glyph_push_runtime_byte(&utf8_stream, byte, escape_line, escape_column)
					if issue.kind != .None do return issue
				}
				column += escape.next - index
				index = escape.next
				continue
			}
			issue := text_glyph_push_runtime_byte(&utf8_stream, value, line, column)
			if issue.kind != .None do return issue
			index += 1
			if value == '\n' {
				line += 1
				column = 1
			} else {
				column += 1
			}
			continue
		case .Raw_String:
			if value == '`' {
				issue := text_glyph_finish_runtime_utf8(&utf8_stream)
				if issue.kind != .None do return issue
				state = .Code
				index += 1
				column += 1
				continue
			}
			issue := text_glyph_push_runtime_byte(&utf8_stream, value, line, column)
			if issue.kind != .None do return issue
			index += 1
			if value == '\n' {
				line += 1
				column = 1
			} else {
				column += 1
			}
			continue
		}

		index += 1
		if value == '\n' {
			line += 1
			column = 1
		} else {
			column += 1
		}
	}

	if state == .String || state == .Raw_String {
		issue := text_glyph_finish_runtime_utf8(&utf8_stream)
		if issue.kind != .None do return issue
		return {kind = .Unterminated_String, line = line, column = column}
	}
	if state == .Block_Comment {
		return {kind = .Unterminated_Block_Comment, line = line, column = column}
	}
	return {}
}


@(test)
default_font_contract_accepts_latin_1_middle_dot_and_layout_controls :: proc(t: ^testing.T) {
	for codepoint in ([8]i32{0x20, 0x7e, 0x7f, 0x80, 0xb7, 0xff, '\t', '\n'}) {
		testing.expectf(t, text_glyph_is_default_font_supported(codepoint), "U+%04X should be accepted by the default-font contract", codepoint)
	}
	testing.expect(t, !text_glyph_is_default_font_supported('\r'), "carriage return is not an accepted layout control")
	testing.expect(t, !text_glyph_is_default_font_supported(0x1f), "non-layout C0 controls must be rejected")
	testing.expect(t, !text_glyph_is_default_font_supported(0x100), "U+0100 lies beyond the vendored default font")

	middle_dot := text_glyph_text_issue("Depth 2 · Crypt of Ash")
	testing.expect(t, middle_dot.kind == .None, "U+00B7 middle dot must remain accepted")
	em_dash := text_glyph_text_issue("Depth 2 — Crypt of Ash")
	testing.expectf(t, em_dash.kind == .Unsupported_Codepoint && em_dash.codepoint == 0x2014, "U+2014 must be rejected, got %v/U+%04X", em_dash.kind, em_dash.codepoint)
}

@(test)
source_literal_audit_ignores_comments_and_checks_runtime_codepoints :: proc(t: ^testing.T) {
	safe_source := `// An em dash — in documentation is harmless.
value := "middle · dot"
/* Nested comments may use arrows → and smart punctuation.
   /* The lexer must ignore this em dash too: — */
*/
layout := "first\nsecond\tcolumn"
`
	issue := text_glyph_source_issue(safe_source)
	testing.expectf(t, issue.kind == .None, "comments or supported text produced %v at %v:%v", issue.kind, issue.line, issue.column)

	bad_source := `value := "visible — separator"`
	issue = text_glyph_source_issue(bad_source)
	testing.expectf(t, issue.kind == .Unsupported_Codepoint && issue.codepoint == 0x2014, "visible U+2014 escaped the source audit: %v/U+%04X", issue.kind, issue.codepoint)

	escaped_middle_dot_source := `value := "\xC2\xB7 \302\267 \u00b7 \U000000b7"`
	issue = text_glyph_source_issue(escaped_middle_dot_source)
	testing.expectf(t, issue.kind == .None, "escaped U+00B7 must remain accepted, got %v at %v:%v", issue.kind, issue.line, issue.column)

	for escaped_bad_source in ([3]string{
		`value := "visible \u2014 separator"`,
		`value := "visible \xE2\x80\x94 separator"`,
		`value := "visible \342\200\224 separator"`,
	}) {
		issue = text_glyph_source_issue(escaped_bad_source)
		testing.expectf(t, issue.kind == .Unsupported_Codepoint && issue.codepoint == 0x2014, "escaped U+2014 escaped the source audit: %v/U+%04X", issue.kind, issue.codepoint)
	}
}

@(private = "file")
text_glyph_audit_source_tree :: proc(t: ^testing.T, root: string, audited: ^int) {
	files, directory_err := os.read_all_directory_by_path(root, context.allocator)
	testing.expectf(t, directory_err == nil, "could not enumerate production source at %s", root)
	if directory_err != nil do return
	defer os.file_info_slice_delete(files, context.allocator)

	for file in files {
		if file.type == .Directory {
			text_glyph_audit_source_tree(t, file.fullpath, audited)
			continue
		}
		if file.type != .Regular || !strings.has_suffix(file.name, ".odin") do continue
		audited^ += 1
		data, read_err := os.read_entire_file_from_path(file.fullpath, context.allocator)
		testing.expectf(t, read_err == nil, "could not audit production text source %s", file.fullpath)
		if read_err != nil do continue

		issue := text_glyph_source_issue(string(data))
		if issue.kind == .Unsupported_Codepoint {
			testing.expectf(
				t, false,
				"%s:%v:%v contains unsupported player-visible string codepoint U+%04X",
				file.fullpath, issue.line, issue.column, issue.codepoint,
			)
		} else {
			testing.expectf(t, issue.kind == .None, "%s:%v:%v failed glyph-source decoding: %v", file.fullpath, issue.line, issue.column, issue.kind)
		}
		delete(data)
	}
}

@(test)
all_production_string_literals_fit_the_vendored_default_font :: proc(t: ^testing.T) {
	audited := 0
	text_glyph_audit_source_tree(t, TEXT_GLYPH_SOURCE_ROOT, &audited)
	testing.expectf(t, audited > 0, "no production .odin modules found under %s", TEXT_GLYPH_SOURCE_ROOT)
}
