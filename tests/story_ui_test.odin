package archrogue_tests

// Headless MX-story UI contract. These tests exercise only explicit-viewport
// geometry and presentation state; no raylib window or GPU asset is created.

import "core:testing"
import ar "../src"

@(private = "file")
story_ui_center :: proc(rect: ar.Story_UI_Rect) -> ar.Vec2 {
	return {rect.x + rect.width * .5, rect.y + rect.height * .5}
}

@(private = "file")
story_ui_non_overlapping :: proc(a, b: ar.Story_UI_Rect) -> bool {
	return ar.story_ui_rect_right(a) <= b.x || ar.story_ui_rect_right(b) <= a.x ||
		ar.story_ui_rect_bottom(a) <= b.y || ar.story_ui_rect_bottom(b) <= a.y
}

@(test)
mx_story_panel_geometry_is_compact_readable_and_shared_with_hit_testing :: proc(t: ^testing.T) {
	resolutions := [2][2]int{{640, 480}, {3840, 2160}}
	body_fonts: [2]i32
	for resolution, resolution_index in resolutions {
		width, height := resolution.x, resolution.y
		layout := ar.story_panel_ui_layout(width, height, ar.STORY_CHOICE_COUNT)
		body_fonts[resolution_index] = layout.body_font

		testing.expectf(t, ar.story_ui_rect_contains_rect(layout.viewport, layout.panel), "%vx%v panel escaped its viewport", width, height)
		testing.expectf(t, layout.panel.width < f32(width) && layout.panel.height < f32(height), "%vx%v modal must leave live-game framing visible", width, height)
		testing.expectf(t, ar.story_ui_rect_contains_rect(layout.panel, layout.backdrop), "%vx%v backdrop escaped panel", width, height)
		testing.expectf(t, ar.story_ui_rect_contains_rect(layout.panel, layout.lower), "%vx%v lower region escaped panel", width, height)
		panel_insets := ar.UI_CHROME_DEFS[ar.STORY_PANEL_CHROME].content_insets
		testing.expectf(t, layout.backdrop.x-layout.panel.x == f32(panel_insets[0]), "%vx%v backdrop ignored authored panel left inset", width, height)
		testing.expectf(t, layout.backdrop.y-layout.panel.y == f32(panel_insets[1]), "%vx%v backdrop ignored authored panel top inset", width, height)
		testing.expectf(t, ar.story_ui_rect_right(layout.panel)-ar.story_ui_rect_right(layout.backdrop) == f32(panel_insets[2]), "%vx%v backdrop ignored authored panel right inset", width, height)
		testing.expectf(t, ar.story_ui_rect_bottom(layout.panel)-ar.story_ui_rect_bottom(layout.lower) == f32(panel_insets[3]), "%vx%v lower region ignored authored panel bottom inset", width, height)
		testing.expectf(t, ar.story_ui_rect_bottom(layout.backdrop) == layout.lower.y, "%vx%v backdrop and lower region must share one seam", width, height)
		testing.expectf(t, layout.backdrop.height > 0 && layout.lower.height > layout.backdrop.height, "%vx%v compact panel lost its top-art/lower-content balance", width, height)
		testing.expectf(t, ar.story_ui_rect_contains_rect(layout.lower, layout.portrait), "%vx%v portrait escaped lower region", width, height)
		testing.expectf(t, ar.story_ui_rect_contains_rect(layout.lower, layout.narration), "%vx%v narration escaped lower region", width, height)
		testing.expectf(t, story_ui_non_overlapping(layout.portrait, layout.narration), "%vx%v portrait overlaps narration", width, height)
		testing.expectf(t, layout.narration.width >= 300 && layout.narration.height >= 36, "%vx%v narration rail is not readable: %.1fx%.1f", width, height, layout.narration.width, layout.narration.height)
		testing.expectf(t, layout.body_font >= 13 && layout.choice_font >= 13 && layout.detail_font >= 10, "%vx%v typography fell below readability floors", width, height)
		testing.expect(t, layout.choice_count == ar.STORY_CHOICE_COUNT, "three story choices must produce three rows")

		for row in 0 ..< layout.choice_count {
			rect := layout.choice_rows[row]
			testing.expectf(t, ar.story_ui_rect_contains_rect(layout.lower, rect), "%vx%v choice %v escaped lower region", width, height, row)
			testing.expectf(t, rect.height >= 32, "%vx%v choice %v is too short for icon/label/detail", width, height, row)
			if row > 0 do testing.expectf(t, story_ui_non_overlapping(layout.choice_rows[row - 1], rect), "%vx%v choice rows overlap", width, height)
			index, found := ar.story_panel_ui_choice_at(&layout, story_ui_center(rect))
			testing.expectf(t, found && index == row, "%vx%v row center hit %v/%v, want %v/true", width, height, index, found, row)
		}
		_, backdrop_hit := ar.story_panel_ui_choice_at(&layout, story_ui_center(layout.backdrop))
		testing.expectf(t, !backdrop_hit, "%vx%v backdrop must not alias a choice row", width, height)
	}
	testing.expect(t, body_fonts[1] > body_fonts[0], "4K typography must scale above the 640x480 floor")
}

@(test)
mx_story_panel_chrome_maps_to_authored_outer_socket_and_choice_assets :: proc(t: ^testing.T) {
	panel := ar.UI_CHROME_DEFS[ar.STORY_PANEL_CHROME]
	socket := ar.UI_CHROME_DEFS[ar.STORY_RELIC_SOCKET_CHROME]
	row := ar.UI_CHROME_DEFS[ar.STORY_CHOICE_ROW_CHROME]
	testing.expect(t, panel.key == "menu.panel" && panel.render == .Nine_Slice, "story outer container lost authored panel chrome")
	testing.expect(t, socket.key == "cutscene.relic.socket" && socket.render == .Scale, "relic slot lost its distinct authored socket")
	testing.expect(t, socket.has_content_insets && socket.content_insets == [4]int{64,64,64,64}, "relic socket icon well changed")
	testing.expect(t, row.key == "cutscene.choice.panel" && row.render == .Nine_Slice, "story choice lost its dedicated minimal row chrome")
	testing.expect(t, row.scale_insets_with_height && row.content_insets[0] > row.content_insets[2]*4, "story choice no longer reserves its distinct left icon socket")
}


@(test)
mx_story_cinematic_backdrop_preserves_the_complete_centered_artwork :: proc(t: ^testing.T) {
	resolutions := [3][2]int{{640, 480}, {1280, 720}, {3840, 2160}}
	for resolution in resolutions {
		layout := ar.story_panel_ui_layout(resolution.x, resolution.y, ar.STORY_CHOICE_COUNT)
		art := ar.story_ui_texture_contain_rect(640, 360, layout.backdrop)
		testing.expectf(t, ar.story_ui_rect_contains_rect(layout.backdrop, art), "%vx%v complete art escaped backdrop", resolution.x, resolution.y)

		ratio_error := art.width * 9 - art.height * 16
		if ratio_error < 0 do ratio_error = -ratio_error
		testing.expectf(t, ratio_error < .1, "%vx%v foreground art is not 16:9: %.1fx%.1f", resolution.x, resolution.y, art.width, art.height)

		height_error := art.height - layout.backdrop.height
		if height_error < 0 do height_error = -height_error
		testing.expectf(t, height_error < .1, "%vx%v foreground art should use the banner's full height", resolution.x, resolution.y)

		left_fill := art.x - layout.backdrop.x
		right_fill := ar.story_ui_rect_right(layout.backdrop) - ar.story_ui_rect_right(art)
		center_error := left_fill - right_fill
		if center_error < 0 do center_error = -center_error
		testing.expectf(t, center_error < .1, "%vx%v foreground art is not centered", resolution.x, resolution.y)
		testing.expectf(t, left_fill >= layout.backdrop.width * .2, "%vx%v cinematic side field is too narrow to read as intentional", resolution.x, resolution.y)
	}
}

@(test)
mx_story_minigame_geometry_supports_three_and_four_column_boards_at_extremes :: proc(t: ^testing.T) {
	resolutions := [2][2]int{{640, 480}, {3840, 2160}}
	for resolution in resolutions {
		width, height := resolution.x, resolution.y
		for fixture in ([2][2]int{{9, 3}, {8, 4}}) {
			count, columns := fixture.x, fixture.y
			layout := ar.story_minigame_ui_layout(width, height, count, columns)
			testing.expectf(t, ar.story_ui_rect_contains_rect(layout.viewport, layout.panel), "%vx%v minigame panel escaped viewport", width, height)
			testing.expectf(t, layout.panel.width < f32(width) && layout.panel.height < f32(height), "%vx%v minigame must remain a live-game modal", width, height)
			testing.expectf(t, layout.board_count == count && layout.columns == columns, "%vx%v board dimensions changed", width, height)
			testing.expectf(t, layout.rows == (count + columns - 1) / columns, "%vx%v board row count changed", width, height)
			testing.expectf(t, ar.story_ui_rect_contains_rect(layout.board_region, layout.board), "%vx%v board escaped board region", width, height)
			testing.expectf(t, layout.body_font >= 12 && layout.stat_font >= 11 && layout.cell_font >= 16, "%vx%v minigame typography fell below floors", width, height)
			for cell in 0 ..< count {
				rect := layout.cells[cell]
				testing.expectf(t, ar.story_ui_rect_contains_rect(layout.board, rect), "%vx%v cell %v escaped board", width, height, cell)
				testing.expectf(t, rect.width == rect.height && rect.width >= 60, "%vx%v cell %v is not a readable square", width, height, cell)
				index, found := ar.story_minigame_ui_cell_at(&layout, story_ui_center(rect))
				testing.expectf(t, found && index == cell, "%vx%v cell center hit %v/%v, want %v/true", width, height, index, found, cell)
				if cell > 0 do testing.expectf(t, story_ui_non_overlapping(layout.cells[cell - 1], rect), "%vx%v adjacent board cells overlap", width, height)
			}
			_, title_hit := ar.story_minigame_ui_cell_at(&layout, story_ui_center(layout.title))
			testing.expectf(t, !title_hit, "%vx%v title must not alias a board cell", width, height)
		}
	}
}

@(test)
mx_story_modal_hit_test_maps_pointer_intent_without_raylib_state :: proc(t: ^testing.T) {
	app: ar.App
	app.story_panel = {
		active = true,
		node = .Soul_Reflection,
		text_len = 0,
	}
	panel_layout := ar.story_modal_layout(&app, 640, 480)
	testing.expect(t, panel_layout.kind == .Panel && panel_layout.panel.choice_count == 3, "Soul reflection must expose a three-choice panel layout")
	choice_point := story_ui_center(panel_layout.panel.choice_rows[1])
	hit := ar.story_modal_hit_test(&app, 640, 480, choice_point)
	testing.expect(t, hit.kind == .Choice && hit.index == 1, "completed panel pointer must map to its exact choice index")
	hit = ar.story_modal_hit_test(&app, 640, 480, {-1, -1})
	testing.expect(t, hit.kind == .None, "outside panel pointer must not confirm")

	app.story_panel.text[0] = 'A'
	app.story_panel.text_len = 1
	app.story_panel.node_elapsed = 0
	hit = ar.story_modal_hit_test(&app, 640, 480, story_ui_center(panel_layout.panel.backdrop))
	testing.expect(t, hit.kind == .Panel && hit.index == -1, "unfinished typewriter click must request reveal without selecting a row")

	app.story_panel = {}
	app.story_minigame = {
		active = true,
		kind = .Wake_The_Moonbloom,
		phase = .Play,
		board_count = 9,
		goal = 6,
	}
	minigame_layout := ar.story_modal_layout(&app, 3840, 2160)
	testing.expect(t, minigame_layout.kind == .Minigame, "active minigame must take modal priority")
	cell_point := story_ui_center(minigame_layout.minigame.cells[7])
	hit = ar.story_modal_hit_test(&app, 3840, 2160, cell_point)
	testing.expect(t, hit.kind == .Minigame_Cell && hit.index == 7, "minigame pointer must map to its exact cell")
	hit = ar.story_modal_hit_test(&app, 3840, 2160, story_ui_center(minigame_layout.minigame.title))
	testing.expect(t, hit.kind == .None, "Play-phase panel chrome must not press the current cell")
	app.story_minigame.phase = .Ready
	hit = ar.story_modal_hit_test(&app, 3840, 2160, story_ui_center(minigame_layout.minigame.title))
	testing.expect(t, hit.kind == .Panel && hit.index == -1, "Ready-phase panel click must start without inventing a cell index")

	app.story_minigame = {
		active = true,
		kind = .Mirror_The_Unlost,
		phase = .Play,
		board_count = 8,
	}
	hunt_layout := ar.story_modal_layout(&app, 3840, 2160)
	testing.expect(t, hunt_layout.kind == .None, "the active Lossless Soul hunt must stay in the world instead of opening a modal layout")
	hunt_point := story_ui_center(minigame_layout.minigame.cells[7])
	hit = ar.story_modal_hit_test(&app, 3840, 2160, hunt_point)
	testing.expect(t, hit.kind == .None, "the active Lossless Soul hunt must not expose modal pointer hits")
	_, hunt_cell_found := ar.story_minigame_cell_at(&app, 3840, 2160, hunt_point)
	testing.expect(t, !hunt_cell_found, "the active Lossless Soul hunt must not expose legacy board cells")
}

@(test)
mx_story_minigame_cell_views_cover_ready_preview_play_and_result :: proc(t: ^testing.T) {
	bind := ar.Story_Minigame_State{
		active = true,
		kind = .Bind_The_Page,
		phase = .Ready,
		board_count = 6,
		sequence_count = 1,
		sequence = {2, 0, 0, 0, 0, 0},
	}
	view := ar.story_minigame_cell_view(&bind, 2, 2)
	testing.expect(t, !view.face_up && view.selected, "Ready board must show selectable sealed cells")
	bind.phase = .Preview
	bind.elapsed = .31
	view = ar.story_minigame_cell_view(&bind, 2, 0)
	testing.expect(t, view.face_up && view.active && !view.selected, "Bind Preview must reveal and pulse the runtime preview cell")
	bind.phase = .Play
	view = ar.story_minigame_cell_view(&bind, 4, 4)
	testing.expect(t, view.face_up && view.selected, "Bind Play must keep sigils readable and expose keyboard cursor")
	bind.phase = .Result
	view = ar.story_minigame_cell_view(&bind, 4, 4)
	testing.expect(t, view.face_up && !view.selected, "Result board must reveal without an actionable cursor")

	moon := ar.Story_Minigame_State{active = true, kind = .Wake_The_Moonbloom, phase = .Play, board_count = 9, active_cell = 5}
	view = ar.story_minigame_cell_view(&moon, 5, 0)
	testing.expect(t, view.face_up && view.active, "Moonbloom Play must identify the live target")
}
