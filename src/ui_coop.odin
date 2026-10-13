package archrogue

// Co-op screens: setup (name/server/code), connection consent, lobby with the
// two-sigil verification seal, connection/reconnect wait, and in-run partner
// HUD. Reads App state only; every decision lives in net_lobby/net_sync.

import "core:fmt"
import "core:strings"
import rl "../vendor/raylib"
import np "net_protocol"

COOP_MENU_LABELS := [Coop_Menu_Row]cstring{
	.Name   = "Name",
	.Server = "Server",
	.Host   = "Host a room",
	.Code   = "Room code",
	.Join   = "Join room",
	.Back   = "Back",
}

COOP_LOBBY_LABELS := [Coop_Lobby_Row]cstring{
	.Accept     = "Accept",
	.Kick       = "Turn away",
	.Archetype  = "Archetype",
	.Difficulty = "Difficulty",
	.Story      = "Story",
	.Ready      = "Ready",
	.Leave      = "Leave",
}

COOP_ACCENT  :: rl.Color{240, 228, 160, 255}
COOP_WARNING :: rl.Color{214, 112, 92, 255}

@(private = "file")
coop_panel :: proc(width, height: f32) -> rl.Rectangle {
	presentation := ui_presentation()
	bounds := menu_background_content_rect(presentation.width, presentation.height)
	return menu_panel_in_bounds(bounds, width, height)
}

coop_menu_row_rect :: proc(index: int) -> rl.Rectangle {
	panel := coop_panel(640, 470)
	return {panel.x + 40, panel.y + 92 + f32(index) * 56, panel.width - 80, 46}
}

coop_menu_row_at :: proc(point: rl.Vector2) -> (int, bool) {
	p := ui_screen_to_design(point)
	for i in 0 ..< len(Coop_Menu_Row) do if rl.CheckCollisionPointRec(p, coop_menu_row_rect(i)) do return i, true
	return 0, false
}

coop_consent_row_rect :: proc(index: int) -> rl.Rectangle {
	panel := coop_panel(700, 400)
	w := (panel.width - 120) * .5
	return {panel.x + 40 + f32(index) * (w + 40), panel.y + panel.height - 76, w, 46}
}

coop_consent_row_at :: proc(point: rl.Vector2) -> (int, bool) {
	p := ui_screen_to_design(point)
	for i in 0 ..< 2 do if rl.CheckCollisionPointRec(p, coop_consent_row_rect(i)) do return i, true
	return 0, false
}

COOP_LOBBY_PANEL_W :: 760
COOP_LOBBY_PANEL_H :: 600

// Seven rows at most (host during admission); they end at y+526 and the two
// hint lines sit below them inside the 600-tall panel.
coop_lobby_row_rect :: proc(index: int) -> rl.Rectangle {
	panel := coop_panel(COOP_LOBBY_PANEL_W, COOP_LOBBY_PANEL_H)
	return {panel.x + 40, panel.y + 264 + f32(index) * 38, panel.width - 80, 32}
}

// The room-code inset at the top of the lobby.
@(private = "file")
coop_lobby_code_rect :: proc() -> rl.Rectangle {
	panel := coop_panel(COOP_LOBBY_PANEL_W, COOP_LOBBY_PANEL_H)
	return {panel.x + 40, panel.y + 36, panel.width - 80, 84}
}

coop_lobby_row_at :: proc(point: rl.Vector2, count: int) -> (int, bool) {
	p := ui_screen_to_design(point)
	for i in 0 ..< count do if rl.CheckCollisionPointRec(p, coop_lobby_row_rect(i)) do return i, true
	return 0, false
}

@(private = "file")
draw_centered :: proc(text: cstring, center_x, y: f32, size: i32, color: rl.Color) {
	ui_draw_text(text, i32(center_x) - ui_measure_text(text, size) / 2, i32(y), size, color)
}

draw_coop_menu :: proc(app: ^App, assets: ^Assets) {
	presentation := ui_begin_presentation()
	defer ui_end_presentation()
	draw_menu_background(assets, false)
	ui := &app.coop_ui
	panel := coop_panel(640, 470)
	draw_menu_panel_chrome(assets, panel)
	center := panel.x + panel.width * .5
	draw_centered("ONLINE CO-OP", center, panel.y + 30, 30, COLOR_TITLE)
	for row in Coop_Menu_Row {
		i := int(row)
		rect := coop_menu_row_rect(i)
		selected := ui_navigation_selected(app, ui.row == i) || (ui.editing && ui.row == i)
		content := draw_menu_row_chrome(assets, rect, selected)
		color := selected ? COLOR_TITLE : COLOR_TEXT
		label := COOP_MENU_LABELS[row]
		field_text := ""
		has_field := true
		switch row {
		case .Name:   field_text = coop_field_text(ui, .Name)
		case .Server: field_text = coop_field_text(ui, .Server)
		case .Code:   field_text = coop_field_text(ui, .Code)
		case .Host, .Join, .Back: has_field = false
		}
		if !has_field {
			w := ui_measure_text(label, 20)
			ui_draw_text(label, i32(content.x + (content.width - f32(w)) * .5), i32(rect.y + 12), 20, color)
			continue
		}
		ui_draw_text(label, i32(content.x), i32(rect.y + 12), 18, COLOR_TEXT_DIM)
		value := fmt.ctprintf("%s%s", field_text, ui.editing && ui.row == i && (app.tick / 30) % 2 == 0 ? "_" : "")
		size: i32 = 18
		available := i32(content.width) - 150
		for size > 11 && ui_measure_text(value, size) > available do size -= 1
		ui_draw_text(value, i32(content.x) + 140, i32(rect.y + 12), size, color)
	}
	if row := Coop_Menu_Row(ui.row); ui.editing {
		hint: cstring = row == .Code ? "Type the 4-character code, Enter to finish" : "Type, Enter to finish"
		draw_centered(hint, center, panel.y + panel.height - 40, 14, COLOR_TEXT_DIM)
	} else if ui.message != "" {
		draw_centered(fmt.ctprintf("%s", ui.message), center, panel.y + panel.height - 40, 15, COOP_WARNING)
	} else {
		draw_centered("Enter: edit or choose   Esc: back", center, panel.y + panel.height - 40, 14, COLOR_TEXT_DIM)
	}
	if ui.consent_open do draw_coop_consent(app, assets)
	_ = presentation
}

draw_coop_consent :: proc(app: ^App, assets: ^Assets) {
	presentation := ui_presentation()
	rl.DrawRectangleRec({0, 0, presentation.width, presentation.height}, rl.Fade(rl.BLACK, .66))
	ui := &app.coop_ui
	panel := coop_panel(700, 400)
	content := draw_menu_panel_chrome(assets, panel)
	center := panel.x + panel.width * .5
	url := strings.trim_space(coop_field_text(ui, .Server))
	endpoint, _ := net_url_parse(url)
	draw_centered("Connect to this server?", center, panel.y + 28, 26, COLOR_TITLE)
	draw_centered(fmt.ctprintf("%s", url), center, panel.y + 74, 18, COLOR_TEXT)
	if endpoint.secure {
		draw_centered("Encrypted (TLS) between you and the server", center, panel.y + 104, 16, rl.Color{150, 210, 150, 255})
	} else {
		draw_centered(net_endpoint_is_local(endpoint) ? "NOT encrypted: local/LAN testing only" : "NOT encrypted: anyone on the path can read it",
			center, panel.y + 104, 16, COOP_WARNING)
	}
	lines := [?]cstring{
		"The relay operator can read the game state it forwards",
		"and the name you chose. Self-hosted servers have their own",
		"operator. Names and room codes are not passwords.",
		"More: " + PROJECT_URL,
	}
	for line, i in lines {
		size: i32 = 15
		for size > 11 && ui_measure_text(line, size) > i32(content.width) do size -= 1
		draw_centered(line, center, panel.y + 146 + f32(i) * 26, size, COLOR_TEXT_DIM)
	}
	labels := [2]cstring{"Connect", "Cancel"}
	for label, i in labels {
		rect := coop_consent_row_rect(i)
		selected := ui_navigation_selected(app, ui.row == i)
		row := draw_menu_row_chrome(assets, rect, selected)
		w := ui_measure_text(label, 20)
		ui_draw_text(label, i32(row.x + (row.width - f32(w)) * .5), i32(rect.y + 12), 20, selected ? COLOR_TITLE : COLOR_TEXT)
	}
}

@(private = "file")
draw_seal :: proc(assets: ^Assets, code: string, left_x, y, size: f32) {
	first, second := np.room_code_seal(code)
	names := [2]string{np.SEAL_SIGILS[first], np.SEAL_SIGILS[second]}
	for name, i in names {
		x := left_x + f32(i) * (size + 12)
		drawn := false
		if glyph, found := ui_seal_sigil_glyph(assets, name); found do drawn = draw_ui_glyph(glyph, {x, y, size, size}, COOP_ACCENT)
		if !drawn do rl.DrawRectangleLinesEx({x, y, size, size}, 1, rl.Fade(COOP_ACCENT, .6))
	}
}

// The room code as large, letter-spaced glyphs; returns the width drawn.
@(private = "file")
draw_big_code :: proc(code: string, x, y: f32, size: i32, color: rl.Color) -> f32 {
	gap := f32(size) * .28
	cursor := x
	for i in 0 ..< len(code) {
		glyph := fmt.ctprintf("%c", code[i])
		ui_draw_text(glyph, i32(cursor), i32(y), size, color)
		cursor += f32(ui_measure_text(glyph, size)) + gap
	}
	return cursor - gap - x
}

// Checklist box: filled accent when done, outlined otherwise.
@(private = "file")
draw_check_box :: proc(x, y, size: f32, done: bool, current: bool) {
	rect := rl.Rectangle{x, y, size, size}
	if done {
		rl.DrawRectangleRec(rect, COOP_ACCENT)
		rl.DrawRectangleRec({x + size * .3, y + size * .3, size * .4, size * .4}, rl.Color{20, 16, 24, 255})
	} else {
		rl.DrawRectangleLinesEx(rect, 1, current ? COOP_ACCENT : rl.Fade(COLOR_TEXT_DIM, .7))
	}
}

draw_coop_lobby :: proc(app: ^App, assets: ^Assets) {
	presentation := ui_begin_presentation()
	defer ui_end_presentation()
	draw_menu_background(assets, false)
	s := &app.coop.session
	ui := &app.coop_ui
	panel := coop_panel(COOP_LOBBY_PANEL_W, COOP_LOBBY_PANEL_H)
	draw_menu_panel_chrome(assets, panel)
	center := panel.x + panel.width * .5
	code := net_session_room_code(s)
	host_seat := &s.seats[0]
	partner := &s.seats[1]
	local_slot := net_session_local_slot(s)
	local := &s.seats[local_slot]
	is_host := s.role == .Host
	knocking := partner.present && !partner.admitted
	both_ready := host_seat.present && partner.present && host_seat.ready && partner.ready
	pulse := f32(0.55) + 0.45 * f32((app.tick / 20) % 2)
	// The partner is ready and only this player's readiness is missing: the
	// Ready row pulses the same way the Accept row does for a knock.
	other := &s.seats[1 - local_slot]
	awaiting_me := other.present && other.admitted && other.ready && !local.ready && !(is_host && knocking)

	// ---- room code inset: the one thing to share, drawn big.
	inset := coop_lobby_code_rect()
	inset_asset := ui_chrome_asset(assets, .Menu_Panel_Inset)
	if !draw_ui_chrome(inset_asset, inset) {
		rl.DrawRectangleRec(inset, rl.Fade(rl.BLACK, .35))
		rl.DrawRectangleLinesEx(inset, 1, rl.Fade(COLOR_TEXT_DIM, .5))
	}
	ui_draw_text("ROOM CODE", i32(inset.x + 24), i32(inset.y + 10), 13, COLOR_TEXT_DIM)
	_ = draw_big_code(code, inset.x + 24, inset.y + 26, 44, COLOR_TITLE)
	// Seal marks sit at the inset's right edge (two 44 px glyphs, 12 px apart).
	draw_seal(assets, code, inset.x + inset.width - 24 - (44 * 2 + 12), inset.y + 20, 44)

	// ---- checklist: the three things that must happen, in order.
	steps_done := [3]bool{partner.present, partner.admitted, both_ready}
	step_labels := [3]cstring{"Partner joined", "Host accepted", "Both ready"}
	current_step := 3
	for done, i in steps_done do if !done {current_step = i; break}
	step_w := (panel.width - 80) / 3
	for i in 0 ..< 3 {
		x := panel.x + 40 + f32(i) * step_w
		y := panel.y + 134
		is_current := i == current_step
		draw_check_box(x, y + 1, 14, steps_done[i], is_current)
		label := step_labels[i]
		if i == 0 && !steps_done[0] do label = "Waiting for a partner"
		ui_draw_text(label, i32(x + 22), i32(y - 1), 15, steps_done[i] ? COLOR_TEXT : (is_current ? COOP_ACCENT : COLOR_TEXT_DIM))
	}

	// ---- seats.
	for slot in 0 ..< MAX_PLAYERS {
		seat := &s.seats[slot]
		col_w := (panel.width - 80) * .5
		card := rl.Rectangle{panel.x + 40 + f32(slot) * col_w, panel.y + 162, col_w - 10, 86}
		is_knock := slot == 1 && knocking
		border := rl.Fade(COLOR_TEXT_DIM, .35)
		if is_knock do border = rl.Fade(COOP_ACCENT, pulse)
		else if seat.present && seat.ready do border = rl.Fade(COOP_ACCENT, .6)
		rl.DrawRectangleLinesEx(card, is_knock ? 2 : 1, border)
		x := card.x + 12
		y := card.y + 8
		role: cstring = slot == 0 ? "HOST" : "PARTNER"
		ui_draw_text(role, i32(x), i32(y), 13, COLOR_TEXT_DIM)
		if !seat.present {
			ui_draw_text("Waiting for a partner...", i32(x), i32(y + 22), 17, COLOR_TEXT_DIM)
			continue
		}
		name := fmt.ctprintf("%s%s", net_seat_name(seat), slot == local_slot ? " (you)" : "")
		ui_draw_text(name, i32(x), i32(y + 20), 18, COLOR_TEXT)
		status: cstring
		status_color := COLOR_TEXT_DIM
		switch {
		case !seat.connected: status = "Reconnecting..."
		case !seat.admitted:
			status = is_host ? "Wants to join. Accept them below" : "Waiting for the host to accept you"
			status_color = COOP_ACCENT
		case seat.chosen: status = fmt.ctprintf("%s", ARCHETYPES[seat.archetype].name)
		case: status = "Choosing an archetype"
		}
		ui_draw_text(status, i32(x), i32(y + 46), 14, status_color)
		// Ready badge, top right of the card.
		if seat.admitted {
			badge: cstring = seat.ready ? "READY" : "NOT READY"
			bw := ui_measure_text(badge, 12)
			bx := card.x + card.width - f32(bw) - 24
			draw_check_box(bx - 4, y + 2, 12, seat.ready, false)
			ui_draw_text(badge, i32(bx + 12), i32(y), 12, seat.ready ? COOP_ACCENT : COLOR_TEXT_DIM)
		}
	}

	// ---- rows.
	rows: [len(Coop_Lobby_Row)]Coop_Lobby_Row
	count := coop_lobby_rows(app, &rows)
	partner_name := net_seat_name(partner)
	if partner_name == "" do partner_name = "your partner"
	for i in 0 ..< count {
		row := rows[i]
		rect := coop_lobby_row_rect(i)
		selected := ui_navigation_selected(app, ui.lobby_row == i)
		content := draw_menu_row_chrome(assets, rect, selected)
		color := selected ? COLOR_TITLE : COLOR_TEXT
		label := COOP_LOBBY_LABELS[row]
		if row == .Accept do label = fmt.ctprintf("Accept %s", partner_name)
		disabled := row == .Ready && is_host && knocking
		if disabled do color = COLOR_TEXT_DIM
		if (row == .Accept && knocking) || (row == .Ready && awaiting_me) {
			// Pulsing marker so the player cannot miss where to act.
			rl.DrawRectangleRec({rect.x - 10, rect.y + 10, 5, rect.height - 20}, rl.Fade(COOP_ACCENT, pulse))
			if !selected do color = rl.Fade(COOP_ACCENT, pulse)
		}
		ui_draw_text(label, i32(content.x), i32(rect.y + 7), 17, color)
		value: cstring
		#partial switch row {
		case .Archetype: value = fmt.ctprintf("< %s >", ARCHETYPES[Archetype_Id(ui.select_index)].name)
		case .Difficulty: value = fmt.ctprintf("< %s >", DIFFICULTY_PROFILES[s.difficulty].name)
		case .Story: value = s.story ? "On" : "Off"
		case .Ready:
			switch {
			case disabled: value = "Accept your partner first"
			case both_ready: value = "Starting..."
			case local.ready && partner.present: value = fmt.ctprintf("Waiting for %s", net_seat_name(&s.seats[1 - local_slot]))
			case local.ready: value = "Ready"
			case: value = "Ready up"
			}
		}
		if value != nil {
			w := ui_measure_text(value, 17)
			ui_draw_text(value, i32(content.x + content.width) - w, i32(rect.y + 7), 17, color)
		}
	}

	// ---- hints.
	hint: cstring
	hint_color := COLOR_TEXT_DIM
	switch {
	case is_host && knocking: hint = "Accept your partner to continue"
	case !partner.present: hint = is_host ? "Waiting for a partner to join with the code" : "Waiting for the host"
	case awaiting_me:
		hint = fmt.ctprintf("%s is ready and waiting for you", net_seat_name(other))
		hint_color = rl.Fade(COOP_ACCENT, pulse)
	case !both_ready: hint = "Both players must ready up to begin"
	case:
		hint = "Starting the descent..."
		hint_color = COOP_ACCENT
	}
	draw_centered(hint, center, panel.y + panel.height - 50, 15, hint_color)
	if s.role == .Join {
		settings := fmt.ctprintf("Host settings: %s, story %s", DIFFICULTY_PROFILES[s.difficulty].name, s.story ? "on" : "off")
		draw_centered(settings, center, panel.y + panel.height - 30, 13, COLOR_TEXT_DIM)
	} else {
		draw_centered("Arrows: change   Enter: choose   Esc: leave", center, panel.y + panel.height - 30, 13, COLOR_TEXT_DIM)
	}
	_ = presentation
}

draw_coop_wait :: proc(app: ^App, assets: ^Assets) {
	presentation := ui_begin_presentation()
	defer ui_end_presentation()
	s := &app.coop.session
	if !app.coop.j_have_world do draw_menu_background(assets, false)
	else do rl.DrawRectangleRec({0, 0, presentation.width, presentation.height}, rl.Fade(rl.BLACK, .55))
	panel := coop_panel(620, 200)
	draw_menu_panel_chrome(assets, panel)
	center := panel.x + panel.width * .5
	title: cstring
	detail: cstring = ""
	switch s.phase {
	case .Connecting:
		title = "Connecting..."
		detail = fmt.ctprintf("%s", s.endpoint_text)
	case .Reconnecting:
		title = "Connection lost - reconnecting"
		remaining := max(0, (s.grace_deadline - app.net_now_ms) / 1000)
		detail = fmt.ctprintf("%v s left to restore the session", remaining)
	case .Active, .Lobby:
		title = "Entering the descent..."
		detail = "Receiving the world from the host"
	case .Idle, .Ended, .Failed:
		title = "Closing..."
	}
	draw_centered(title, center, panel.y + 52, 24, COLOR_TITLE)
	draw_centered(detail, center, panel.y + 96, 15, COLOR_TEXT_DIM)
	draw_centered("Esc: cancel", center, panel.y + 146, 14, COLOR_TEXT_DIM)
}

// In-run co-op overlay: partner vitals and the shared pause/hold reasons.
draw_coop_hud :: proc(app: ^App, assets: ^Assets) {
	presentation := ui_begin_presentation()
	defer ui_end_presentation()
	c := &app.coop
	s := &c.session
	run := &app.run
	if run_seat_count(run) < 2 do return
	partner_slot := 1 - run.local_slot
	partner := &run.players[partner_slot]
	name := net_start_name(&s.start, partner_slot)
	// Same chrome as the minimap card, to its left with a gap, and sharing
	// its top edge (the minimap sits at y 18, MINIMAP_CARD_WIDTH wide, 18 px
	// from the right edge), so the two read as one HUD row.
	box_w, box_h: f32 = 204, 56
	box := rl.Rectangle{presentation.width - 18 - f32(MINIMAP_CARD_WIDTH) - 12 - box_w, 18, box_w, box_h}
	panel := ui_chrome_asset(assets, .Hud_Panel)
	content := rl.Rectangle{box.x + 8, box.y + 7, box.width - 16, box.height - 14}
	if draw_ui_chrome(panel, box) {
		if inner, ok := ui_chrome_content_rect(panel, box); ok do content = inner
	} else {
		rl.DrawRectangleRec(box, rl.Fade(rl.BLACK, .72))
		rl.DrawRectangleLinesEx(box, 1, rl.Fade(rl.WHITE, .22))
	}
	label := fmt.ctprintf("%s - %s  Lv %v", name != "" ? name : "Partner", ARCHETYPES[partner.archetype].name, partner.level)
	ui_draw_text(label, i32(content.x + 2), i32(content.y + 1), 13, COLOR_TEXT)
	bar := rl.Rectangle{content.x + 2, content.y + content.height - 13, content.width - 4, 11}
	rl.DrawRectangleRec(bar, rl.Color{40, 20, 24, 255})
	if partner.hp > 0 {
		frac := clamp(f32(partner.hp) / f32(max(1, partner.max_hp)), 0, 1)
		rl.DrawRectangleRec({bar.x, bar.y, bar.width * frac, bar.height}, rl.Color{186, 52, 46, 255})
		hp := fmt.ctprintf("%v / %v", partner.hp, partner.max_hp)
		ui_draw_text(hp, i32(bar.x + bar.width * .5) - ui_measure_text(hp, 10) / 2, i32(bar.y), 10, rl.WHITE)
	} else {
		ui_draw_text("FALLEN", i32(bar.x + 4), i32(bar.y - 1), 11, COOP_WARNING)
	}
	if run.players[run.local_slot].raise_charges > 0 {
		// Aligned with the chrome's visible left edge, not the panel rectangle.
		ui_draw_text(fmt.ctprintf("Raises: %v", run.players[run.local_slot].raise_charges), i32(content.x + 2), i32(box.y + box.height + 3), 12, COLOR_TEXT_DIM)
	}

	banner: cstring
	pause := coop_is_host(app) ? coop_host_pause(app) : c.j_pause
	switch {
	case s.phase == .Reconnecting:
		banner = fmt.ctprintf("Connection lost - reconnecting (%v s)", max(0, (s.grace_deadline - app.net_now_ms) / 1000))
	case !s.partner_connected:
		banner = fmt.ctprintf("%s lost connection - holding the descent (%v s)", name != "" ? name : "Partner", max(0, (s.partner_grace_until - app.net_now_ms) / 1000))
	case .Partner_Lost in pause && coop_is_host(app):
		banner = "Waiting for your partner to load the floor..."
	case .Joiner_Shop in pause && coop_is_host(app):
		banner = "Your partner is trading - the descent is held"
	case .Host_Story in pause && coop_is_joiner(app):
		banner = "The host is deciding - the descent is held"
	case .Host_Menu in pause && coop_is_joiner(app):
		banner = "The host paused the descent"
	}
	if banner != nil {
		w := ui_measure_text(banner, 18)
		rect := rl.Rectangle{presentation.width * .5 - f32(w) * .5 - 16, 92, f32(w) + 32, 34}
		rl.DrawRectangleRec(rect, rl.Fade(rl.BLACK, .72))
		ui_draw_text(banner, i32(rect.x + 16), i32(rect.y + 8), 18, COOP_ACCENT)
	}
	local := &run.players[run.local_slot]
	if local.hp <= 0 && !c.ended {
		text: cstring = "You have fallen - your partner can raise you, or you rise on the next floor"
		w := ui_measure_text(text, 18)
		ui_draw_text(text, i32(presentation.width * .5) - w / 2, i32(presentation.height * .5 + 60), 18, COOP_WARNING)
	}
}

// F3: live co-op network diagnostics (MULTIPLAYER.md P0 task 6).
draw_coop_debug :: proc(app: ^App) {
	presentation := ui_begin_presentation()
	defer ui_end_presentation()
	c := &app.coop
	s := &c.session
	lines := make([dynamic]cstring, 0, 12, context.temp_allocator)
	append(&lines, fmt.ctprintf("co-op %v  phase %v  rtt %v ms", c.role, s.phase, s.rtt_ms))
	if c.role == .Join {
		ip := &c.j_interp
		append(&lines, fmt.ctprintf("snapshot age %v ms  bytes %v", app.net_now_ms - c.j_last_snapshot_ms, c.j_snapshot_bytes))
		append(&lines, fmt.ctprintf("render delay %.0f ms  jitter %.0f ms  buffer %v", ip.delay_ms, ip.jitter_ms, ip.count))
		append(&lines, fmt.ctprintf("input->ack %v ms  unacked steps %v", c.j_ack_latency_ms, c.j_cmd_seq - min(c.j_cmd_seq, c.j_unsent_from - 1)))
		append(&lines, fmt.ctprintf("correction %.3f (max %.3f) tiles", c.j_last_correction, c.j_max_correction))
		append(&lines, fmt.ctprintf("snapshots ok %v  rejected %v  pause %v", c.j_snapshots_applied, c.j_snapshots_rejected, c.j_pause))
	} else {
		append(&lines, fmt.ctprintf("joiner synced %v  queued steps %v  starved %v  trimmed %v", c.h_joiner_synced, len(c.h_cmds), c.h_starved, c.h_trimmed))
		append(&lines, fmt.ctprintf("resolved step %v  actions %v  snapshot %v", c.h_resolved, c.h_actions_resolved, c.h_snapshot_seq))
		append(&lines, fmt.ctprintf("pause %v", coop_host_pause(app)))
	}
	box := rl.Rectangle{12, presentation.height - f32(len(lines)) * 18 - 22, 470, f32(len(lines)) * 18 + 12}
	rl.DrawRectangleRec(box, rl.Fade(rl.BLACK, .72))
	for line, i in lines do ui_draw_text(line, i32(box.x + 8), i32(box.y + 6) + i32(i) * 18, 14, rl.Color{180, 230, 180, 255})
}
