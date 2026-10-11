package archrogue

// Co-op setup, consent, lobby, and wait screens as a raylib-free reducer.
// Presentation lives in ui_coop.odin; platform text entry arrives on Intent.

import "core:strings"
import "core:unicode/utf8"
import np "net_protocol"

PROJECT_URL :: "https://github.com/mattirk/arch-rogue"

Coop_Lobby_Row :: enum u8 {
	Accept,
	Kick,
	Archetype,
	Difficulty,
	Story,
	Ready,
	Leave,
}

coop_field_text :: proc(ui: ^Coop_Ui_State, field: Coop_Text_Field) -> string {
	return string(ui.fields[field][:ui.lens[field]])
}

coop_field_set :: proc(ui: ^Coop_Ui_State, field: Coop_Text_Field, text: string) {
	n := copy(ui.fields[field][:], text)
	for n > 0 && n < len(text) && (text[n] & 0xC0) == 0x80 do n -= 1
	ui.lens[field] = n
}

// Boot-time defaults (platform env/query) for the server field.
coop_set_default_server :: proc(app: ^App, url: string) {
	if url != "" do coop_field_set(&app.coop_ui, .Server, url)
}

coop_open_menu :: proc(app: ^App) {
	ui := &app.coop_ui
	if ui.lens[.Server] == 0 do coop_field_set(ui, .Server, DEFAULT_RELAY_URL)
	if ui.lens[.Name] == 0 do coop_field_set(ui, .Name, "Wanderer")
	ui.row = int(Coop_Menu_Row.Host)
	ui.editing = false
	ui.consent_open = false
	app.mode = .Coop_Menu
}

// Field editing: append typed UTF-8 within the field's limits; names keep
// the protocol's code-point cap and codes their alphabet.
@(private = "file")
coop_edit_field :: proc(ui: ^Coop_Ui_State, field: Coop_Text_Field, intent: Intent) {
	buf := &ui.fields[field]
	n := &ui.lens[field]
	for _ in 0 ..< intent.text_backspace {
		if n^ == 0 do break
		_, size := utf8.decode_last_rune(buf[:n^])
		n^ -= max(1, size)
	}
	text := intent.text
	typed := string(text[:clamp(intent.text_len, 0, len(text))])
	for r in typed {
		if r == utf8.RUNE_ERROR || r < 0x20 || r == 0x7f do continue
		switch field {
		case .Name:
			if utf8.rune_count(string(buf[:n^])) >= np.NAME_MAX_CODEPOINTS do continue
		case .Code:
			c := r
			if 'a' <= c && c <= 'z' do c -= 32
			if n^ >= np.ROOM_CODE_LENGTH || c > 0x7f || strings.index_byte(np.ROOM_CODE_ALPHABET, byte(c)) < 0 do continue
			buf[n^] = byte(c)
			n^ += 1
			continue
		case .Server:
			if r == ' ' do continue
		}
		bytes, size := utf8.encode_rune(r)
		if n^ + size > NET_URL_MAX_BYTES || n^ + size > COOP_FIELD_MAX do continue
		copy(buf[n^:], bytes[:size])
		n^ += size
	}
}

@(private = "file")
coop_request_connect :: proc(app: ^App, role: np.Role, now_ms: i64) {
	ui := &app.coop_ui
	url := strings.trim_space(coop_field_text(ui, .Server))
	if _, err := net_url_parse(url); err != .None {
		ui.message = net_url_error_text(err)
		return
	}
	if role == .Join && np.room_code_normalize(coop_field_text(ui, .Code), context.temp_allocator) == "" {
		ui.message = "Enter the four-character room code"
		ui.row = int(Coop_Menu_Row.Code)
		return
	}
	// Consent before the first connection to this endpoint in this process;
	// declining opens no socket.
	if ui.consented != url {
		ui.consent_open = true
		ui.consent_role = role
		ui.row = 0
		return
	}
	coop_connect(app, role, now_ms)
}

coop_connect :: proc(app: ^App, role: np.Role, now_ms: i64) {
	ui := &app.coop_ui
	coop_destroy(&app.coop)
	app.coop.strings = make(map[string]string)
	app.coop.role = role == .Host ? .Host : .Join
	url := coop_field_text(ui, .Server)
	name := coop_field_text(ui, .Name)
	ok := false
	if role == .Host {
		ok = net_session_host(&app.coop.session, url, name, now_ms)
	} else {
		ok = net_session_join(&app.coop.session, url, name, coop_field_text(ui, .Code), now_ms)
	}
	if !ok {
		ui.message = net_session_error(&app.coop.session)
		coop_destroy(&app.coop)
		return
	}
	ui.message = ""
	ui.select_index = app.select_index
	app.mode = .Coop_Wait
}

coop_lobby_rows :: proc(app: ^App, rows: ^[len(Coop_Lobby_Row)]Coop_Lobby_Row) -> int {
	s := &app.coop.session
	n := 0
	if s.role == .Host && s.lobby_phase == .Admission {
		rows[n] = .Accept; n += 1
		rows[n] = .Kick; n += 1
	}
	if s.role == .Host && s.lobby_phase == .Selecting {
		rows[n] = .Kick; n += 1
	}
	rows[n] = .Archetype; n += 1
	if s.role == .Host {
		rows[n] = .Difficulty; n += 1
		rows[n] = .Story; n += 1
	}
	rows[n] = .Ready; n += 1
	rows[n] = .Leave; n += 1
	return n
}

// Called once per frame by the platform with monotonic milliseconds.
coop_apply :: proc(app: ^App, intent: Intent, now_ms: i64) {
	ui := &app.coop_ui
	#partial switch app.mode {
	case .Coop_Menu:
		if ui.consent_open {
			if intent.menu_index_valid do ui.row = clamp(intent.menu_index, 0, 1)
			if d := intent.menu_delta + intent.menu_horizontal; d != 0 do ui.row = ((ui.row + d) % 2 + 2) % 2
			if intent.back {
				ui.consent_open = false
				ui.row = ui.consent_role == .Host ? int(Coop_Menu_Row.Host) : int(Coop_Menu_Row.Join)
				return
			}
			if intent.confirm {
				ui.consent_open = false
				if ui.row == 0 {
					delete(ui.consented)
					ui.consented = strings.clone(strings.trim_space(coop_field_text(ui, .Server)))
					coop_connect(app, ui.consent_role, now_ms)
				}
				ui.row = ui.consent_role == .Host ? int(Coop_Menu_Row.Host) : int(Coop_Menu_Row.Join)
			}
			return
		}
		if ui.editing {
			field := Coop_Text_Field.Name
			switch Coop_Menu_Row(ui.row) {
			case .Server: field = .Server
			case .Code:   field = .Code
			case .Name, .Host, .Join, .Back:
			}
			coop_edit_field(ui, field, intent)
			if intent.confirm || intent.back do ui.editing = false
			// Mouse selection of another row ends editing too.
			if intent.menu_index_valid && intent.menu_index != ui.row do ui.editing = false
			if ui.editing do return
		}
		if intent.back {
			app.mode = .Title
			return
		}
		rows := len(Coop_Menu_Row)
		if intent.menu_index_valid do ui.row = clamp(intent.menu_index, 0, rows - 1)
		if intent.menu_delta != 0 do ui.row = ((ui.row + intent.menu_delta) % rows + rows) % rows
		if intent.confirm {
			switch Coop_Menu_Row(ui.row) {
			case .Name, .Server, .Code:
				ui.editing = true
				ui.message = ""
			case .Host: coop_request_connect(app, .Host, now_ms)
			case .Join: coop_request_connect(app, .Join, now_ms)
			case .Back: app.mode = .Title
			}
		}
	case .Coop_Wait:
		if intent.back {
			coop_leave(app)
			app.mode = .Coop_Menu
		}
	case .Coop_Lobby:
		s := &app.coop.session
		if intent.back {
			coop_leave(app)
			app.mode = .Coop_Menu
			return
		}
		rows: [len(Coop_Lobby_Row)]Coop_Lobby_Row
		count := coop_lobby_rows(app, &rows)
		if intent.menu_index_valid do ui.lobby_row = clamp(intent.menu_index, 0, count - 1)
		if intent.menu_delta != 0 do ui.lobby_row = ((ui.lobby_row + intent.menu_delta) % count + count) % count
		ui.lobby_row = clamp(ui.lobby_row, 0, count - 1)
		row := rows[ui.lobby_row]
		local := &s.seats[net_session_local_slot(s)]
		horizontal := intent.menu_horizontal
		if intent.confirm && horizontal == 0 && (row == .Archetype || row == .Difficulty) do horizontal = 1
		switch row {
		case .Accept:
			if intent.confirm do net_session_admit(s)
		case .Kick:
			if intent.confirm do net_session_kick(s)
		case .Archetype:
			if horizontal != 0 {
				n := len(Archetype_Id)
				ui.select_index = ((ui.select_index + horizontal) % n + n) % n
				net_session_select(s, Archetype_Id(ui.select_index))
			}
		case .Difficulty:
			if horizontal != 0 {
				options := app.options
				options.difficulty = s.difficulty
				options_cycle_difficulty(&options, horizontal, app.profile.hell_unlocked)
				net_session_settings(s, options.difficulty, s.story)
			}
		case .Story:
			if intent.confirm || horizontal != 0 do net_session_settings(s, s.difficulty, !s.story)
		case .Ready:
			if intent.confirm {
				if !local.chosen do net_session_select(s, Archetype_Id(ui.select_index))
				seed := app.seed
				app.seed = next_run_seed(seed)
				net_session_ready(s, !local.ready, seed)
			}
		case .Leave:
			if intent.confirm {
				coop_leave(app)
				app.mode = .Coop_Menu
			}
		}
	}
}

// Session-driven screen transitions, evaluated every frame after the pump.
coop_update_screens :: proc(app: ^App) {
	c := &app.coop
	if c.role == .None do return
	s := &c.session
	switch s.phase {
	case .Lobby:
		if app.mode == .Coop_Wait {
			app.mode = .Coop_Lobby
			app.coop_ui.lobby_row = 0
			// Announce the remembered archetype so the partner sees a choice.
			net_session_select(s, Archetype_Id(app.coop_ui.select_index))
		}
	case .Failed:
		app.coop_ui.message = s.error_text != "" ? coop_intern(c, s.error_text) : "Connection failed"
		message := app.coop_ui.message
		in_run := app.mode == .Playing || app.mode == .Paused || app.mode == .Options || app.mode == .Coop_Wait || app.mode == .Coop_Lobby
		coop_leave(app)
		app.coop_ui.message = message
		if in_run do app.mode = .Coop_Menu
	case .Ended:
		if !c.ended {
			// Partner left mid-run: co-op ends; no result is manufactured.
			app.coop_ui.message = "Co-op ended: your partner left"
			coop_leave(app)
			app.mode = .Coop_Menu
		}
	case .Idle, .Connecting, .Active, .Reconnecting:
	}
}
