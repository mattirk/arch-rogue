package archrogue_tests

// Headless MX.1 contract for the canonical authored UI pack. No texture is
// loaded here: typed metadata, exact atlas ordering, and PNG headers are
// validated without opening a raylib window.

import "core:crypto/hash"
import "core:encoding/hex"
import "core:fmt"
import "core:os"
import "core:testing"
import ar "../src"

@(private = "file")
ui_test_u32_be :: proc(data: []u8, offset: int) -> u32 {
	return u32(data[offset]) << 24 |
		u32(data[offset + 1]) << 16 |
		u32(data[offset + 2]) << 8 |
		u32(data[offset + 3])
}

@(private = "file")
ui_test_png_size :: proc(t: ^testing.T, path: string) -> ([2]int, bool) {
	data, read_err := os.read_entire_file_from_path(path, context.allocator)
	testing.expectf(t, read_err == nil, "UI registry references missing PNG %v", path)
	if read_err != nil do return {}, false
	defer delete(data)
	valid := len(data) >= 24 &&
		data[0] == 0x89 && data[1] == 'P' && data[2] == 'N' && data[3] == 'G' &&
		data[4] == 0x0d && data[5] == 0x0a && data[6] == 0x1a && data[7] == 0x0a &&
		data[12] == 'I' && data[13] == 'H' && data[14] == 'D' && data[15] == 'R'
	testing.expectf(t, valid, "%v is not a canonical PNG", path)
	if !valid do return {}, false
	return {
		int(ui_test_u32_be(data, 16)),
		int(ui_test_u32_be(data, 20)),
	}, true
}

@(private = "file")
ui_test_expected_region :: proc(ordinal: int) -> [4]int {
	return {
		(ordinal % ar.UI_GLYPH_ATLAS_COLUMNS) * ar.UI_GLYPH_ATLAS_CELL,
		(ordinal / ar.UI_GLYPH_ATLAS_COLUMNS) * ar.UI_GLYPH_ATLAS_CELL,
		ar.UI_GLYPH_ATLAS_CELL,
		ar.UI_GLYPH_ATLAS_CELL,
	}
}

@(test)
mx1_ui_registry_has_complete_typed_chrome :: proc(t: ^testing.T) {
	testing.expectf(t, len(ar.UI_CHROME_DEFS) == ar.UI_CHROME_COUNT, "typed UI chrome registry has %v rows, want %v", len(ar.UI_CHROME_DEFS), ar.UI_CHROME_COUNT)
	title_def := ar.UI_CHROME_DEFS[.Menu_Background_Title]
	testing.expect(t, title_def.render == .Cover, "title background must preserve aspect ratio")
	testing.expect(t, title_def.file == "chrome/menu_background_title.png", "title must load the canonical Iron Gate scene")
	testing.expect(t, title_def.source_size == [2]int{400, 224}, "Iron Gate source dimensions changed")
	testing.expect(t, ar.UI_CHROME_DEFS[.Menu_Background].render == .Cover, "menu scene must preserve aspect ratio")
	frame_def := ar.UI_CHROME_DEFS[.Menu_Background_Frame]
	testing.expect(t, frame_def.render == .Nine_Slice, "menu frame must use responsive nine-slice rendering")
	testing.expect(t, !frame_def.scale_insets_with_fit, "menu frame corners must remain delicate at large resolutions")
	testing.expect(t, frame_def.tile_edges, "menu frame rails must tile instead of stretching")

	for id in ar.UI_Chrome_Id {
		def := ar.ui_chrome_def(id)
		testing.expectf(t, def.key != "", "%v has an empty canonical key", id)
		testing.expectf(t, def.file != "", "%v (%v) has no canonical file", id, def.key)
		testing.expectf(t, def.source_size[0] > 0 && def.source_size[1] > 0, "%v has invalid source dimensions %v", def.key, def.source_size)

		path := fmt.aprintf("assets/ui/%s", def.file)
		png_size, png_ok := ui_test_png_size(t, path)
		if png_ok do testing.expectf(t, png_size == def.source_size, "%v PNG dimensions %v, want %v", def.key, png_size, def.source_size)
		delete(path)

		for other_i in 0 ..< int(id) {
			other := ar.UI_Chrome_Id(other_i)
			other_def := ar.UI_CHROME_DEFS[other]
			testing.expectf(t, other_def.key != def.key, "duplicate UI chrome key %v", def.key)
			testing.expectf(t, other_def.file != def.file, "%v and %v share an owned texture file", other, id)
		}
	}

	testing.expect(t, ar.UI_LOGO_DIAMOND_FRAME_SIZE == [2]int{72, 74}, "logo-animation frame dimensions changed")
	testing.expect(t, ar.UI_LOGO_DIAMOND_FRAME_COUNT == 16, "logo-animation frame count changed")
	testing.expect(t, ar.UI_LOGO_DIAMOND_FPS == 8, "logo-animation speed changed")
	testing.expect(t, ar.UI_LOGO_DIAMOND_SOURCE_RECT == [4]int{266, 24, 70, 74}, "logo-animation placement changed")
	logo_size, logo_ok := ui_test_png_size(t, ar.UI_LOGO_DIAMOND_ATLAS_FILE)
	if logo_ok do testing.expect(t, logo_size == ar.UI_LOGO_DIAMOND_ATLAS_SIZE, "logo-animation PNG dimensions changed")

	for archetype in ar.Archetype_Id {
		panel := ar.UI_DISCIPLINE_PANELS[archetype]
		testing.expectf(t, ar.UI_CHROME_DEFS[panel].key == fmt.tprintf("menu.panel.discipline.%s", ar.ARCHETYPES[archetype].sprite), "%v discipline panel mapping differs", archetype)
	}
}

@(test)
mx_android_mobile_hud_imports_are_exact_pygame_assets :: proc(t:^testing.T) {
	testing.expect(t,len(ar.MOBILE_HUD_ASSET_DEFS)==ar.MOBILE_HUD_ASSET_COUNT)
	expected_hashes:=[ar.Mobile_Hud_Asset_Id]string{
		.Joystick_Base="d70ecd1bd3c7da63d1128a64ec5567f1e5f9f5765a776ae7a583992b732c9988",
		.Joystick_Knob="1556c511e61a20e5bd37fbbb9908af2d2ef73b4657dd350f74b9409dad4b1174",
		.Status_Bar_Frame="23883dc5cd81f439d59bdf9d9ab1dcc716fb197fc0d88fb481c3b5891ebe320a",
	}
	for id in ar.Mobile_Hud_Asset_Id {
		def:=ar.MOBILE_HUD_ASSET_DEFS[id]
		path:=fmt.aprintf("assets/hud/%s",def.file)
		size,ok:=ui_test_png_size(t,path)
		if ok do testing.expectf(t,size==def.size,"%v dimensions changed",id)
		data,read_err:=os.read_entire_file_from_path(path,context.allocator)
		testing.expectf(t,read_err==nil,"%v could not be hashed",id)
		if read_err==nil {
			digest:=hash.hash_bytes(.SHA256,data,context.allocator)
			encoded,encode_err:=hex.encode(digest,context.allocator)
			delete(digest)
			testing.expect(t,encode_err==.None)
			if encode_err==.None {
				testing.expectf(t,string(encoded)==expected_hashes[id],"%v differs from the canonical Pygame asset",id)
				delete(encoded)
			}
			delete(data)
		}
		delete(path)
	}
}

@(private = "file")
ui_test_abs_f32 :: proc(value: f32) -> f32 {
	return value < 0 ? -value : value
}

@(test)
menu_background_cover_crop_preserves_aspect_ratio :: proc(t: ^testing.T) {
	sources := [2][2]f32{{400, 224}, {490, 300}}
	targets := [4][2]f32{{1024, 768}, {1920, 1200}, {1920, 1080}, {2560, 1080}}
	for source_size in sources {
		for target in targets {
			source := ar.ui_cover_source_rect(source_size[0], source_size[1], target[0], target[1])
			testing.expect(t, source.x >= 0 && source.y >= 0, "cover crop starts outside source")
			testing.expect(t, source.x + source.width <= source_size[0]+.001, "cover crop exceeds source width")
			testing.expect(t, source.y + source.height <= source_size[1]+.001, "cover crop exceeds source height")
			testing.expect(t, ui_test_abs_f32(source.width * target[1] - source.height * target[0]) < .1, "cover crop distorts target aspect")
			testing.expect(t, ui_test_abs_f32(source.x * 2 + source.width - source_size[0]) < .01, "cover crop is not horizontally centered")
			testing.expect(t, ui_test_abs_f32(source.y * 2 + source.height - source_size[1]) < .01, "cover crop is not vertically centered")
		}
	}
}

@(test)
menu_background_frame_preserves_corners_and_safe_area :: proc(t: ^testing.T) {
	targets := [4][2]f32{{1280, 960}, {1280, 800}, {1280, 720}, {1680, 720}}
	for target in targets {
		safe := ar.menu_background_content_rect(target[0], target[1])
		testing.expect(t, safe.x >= 0 && safe.y >= 0, "menu frame safe area begins outside the viewport")
		testing.expect(t, safe.x+safe.width <= target[0]+.01, "menu frame safe area exceeds viewport width")
		testing.expect(t, safe.y+safe.height <= target[1]+.01, "menu frame safe area exceeds viewport height")
		testing.expect(t, ui_test_abs_f32(safe.x-42) < .01, "menu frame left content inset changed")
		testing.expect(t, ui_test_abs_f32(safe.y-38) < .01, "menu frame top content inset changed")
		testing.expect(t, ui_test_abs_f32(target[0]-safe.x-safe.width-42) < .01, "menu frame right content inset changed")
		testing.expect(t, ui_test_abs_f32(target[1]-safe.y-safe.height-38) < .01, "menu frame bottom content inset changed")
	}

	testing.expect(t, ar.UI_NINE_SLICE_DRAW_ORDER[0] == [2]int{1,1}, "nine-slice center must render first")
	for cell,index in ar.UI_NINE_SLICE_DRAW_ORDER {
		corner := cell[0] != 1 && cell[1] != 1
		testing.expectf(t, corner == (index >= 5), "nine-slice cell %v has the wrong compositing rank", cell)
	}
}

@(test)
options_and_controls_fit_inside_responsive_menu_frame :: proc(t: ^testing.T) {
	targets := [4][2]f32{{1280, 960}, {1280, 800}, {1280, 720}, {1680, 720}}
	for target in targets {
		safe := ar.menu_background_content_rect(target[0], target[1])
		panel := ar.menu_panel_in_bounds(safe, 660, 650)
		testing.expect(t, panel.x >= safe.x && panel.y >= safe.y, "options panel starts outside the frame safe area")
		testing.expect(t, panel.x+panel.width <= safe.x+safe.width+.01, "options panel exceeds frame-safe width")
		testing.expect(t, panel.y+panel.height <= safe.y+safe.height+.01, "options panel exceeds frame-safe height")
		previous_bottom := panel.y
		for index in 0..<10 {
			row := ar.options_row_rect_in_panel(panel, index)
			testing.expect(t, row.y >= previous_bottom, "responsive options rows overlap")
			testing.expect(t, row.height >= 28, "responsive options row became too short")
			testing.expect(t, row.x >= panel.x && row.x+row.width <= panel.x+panel.width+.01, "options row exceeds panel width")
			testing.expect(t, row.y+row.height <= panel.y+panel.height, "options row exceeds panel height")
			previous_bottom = row.y+row.height
		}

		controls := ar.menu_panel_in_bounds(safe, 940, 620)
		previous_bottom = controls.y
		for index in 0..<len(ar.CONTROLLER_REMAPPABLE_COMMANDS) {
			row := ar.controls_row_rect_in_panel(controls, index)
			testing.expect(t, row.y >= previous_bottom, "responsive Controls rows overlap")
			testing.expect(t, row.height >= 26, "responsive Controls row became too short")
			testing.expect(t, row.x >= controls.x && row.x+row.width <= controls.x+controls.width+.01, "Controls row exceeds panel width")
			testing.expect(t, row.y+row.height <= ar.controls_status_y(controls), "Controls row collides with status text")
			previous_bottom = row.y+row.height
		}
		testing.expect(t, ar.controls_status_y(controls) < ar.controls_footer_y(controls), "Controls status/footer order changed")
		testing.expect(t, ar.controls_footer_y(controls)+14 <= controls.y+controls.height, "Controls footer exceeds panel height")
	}
}

@(test)
menu_title_relic_is_centered_and_spin_matches_pygame_timing :: proc(t: ^testing.T) {
	for size in ([4][2]f32{{640, 480}, {1280, 720}, {1920, 1200}, {2560, 1080}}) {
		safe := ar.menu_background_content_rect(size[0], size[1])
		rect := ar.title_logo_rect(size[0], size[1])
		relic_source_center := f32(ar.UI_LOGO_DIAMOND_SOURCE_RECT[0]) + f32(ar.UI_LOGO_DIAMOND_SOURCE_RECT[2]) * .5
		relic_center := rect.x + relic_source_center / 640 * rect.width
		testing.expect(t, ui_test_abs_f32(relic_center - size[0] * .5) < .01, "title relic is not on screen center")
		testing.expect(t, ui_test_abs_f32(rect.y - max(safe.y+18, size[1]*.17)) < .01, "title logo does not honor frame-safe placement")
		testing.expect(t, ui_test_abs_f32(rect.width * 122 - rect.height * 640) < .1, "title logo aspect ratio changed")
		testing.expect(t, rect.x >= safe.x && rect.y >= safe.y && rect.x+rect.width <= safe.x+safe.width, "title logo falls outside frame-safe viewport")
		for index in 0..<len(ar.Title_Action) {
			row := ar.title_row_rect_in_bounds(safe, index)
			testing.expect(t, row.x >= safe.x && row.x+row.width <= safe.x+safe.width, "title row exceeds frame-safe width")
			testing.expect(t, row.y >= safe.y && row.y+row.height <= safe.y+safe.height, "title row exceeds frame-safe height")
		}
	}
	testing.expect(t, ar.ui_logo_frame_index(0, 8, 16) == 0, "logo animation must begin on static frame zero")
	testing.expect(t, ar.ui_logo_frame_index(.124, 8, 16) == 0, "logo frame advances too early")
	testing.expect(t, ar.ui_logo_frame_index(.125, 8, 16) == 1, "logo frame does not advance at 8 fps")
	testing.expect(t, ar.ui_logo_frame_index(2, 8, 16) == 0, "logo animation does not loop after 16 frames")
}

@(test)
mx_save_chronicle_pixellab_pack_has_exact_dimensions_and_hashes :: proc(t:^testing.T) {
	expected:=[5]struct{path:string,size:[2]int,sha256:string}{
		{"assets/ui/chronicle/ledger_frame.png",{417,321},"52d658e93e41d93b8ea594d7f665576c9ea3dce8c4a253d8eeb155505f42412b"},
		{"assets/ui/chronicle/content_panel.png",{528,383},"be3d70a33eb1a4b434fd6546bd14d35f5dfe0d8b4d12832d64f869b3dee31150"},
		{"assets/ui/chronicle/filter_panel.png",{355,152},"2913836b0c07b559df296fcafa2bbfab9471c7f7488ba5e1d7b10c6f2a8903bd"},
		{"assets/ui/chronicle/outcome_seals.png",{256,128},"cab211f88ce570840a1d44110b9eb9937988df9ba1dfe2f8e4714a233a461a62"},
		{"assets/ui/chronicle/unwritten_ledger.png",{256,256},"0bcb5469f9e0f7939fa5ed55a2b9aac099b6045a699fa76378b398bf33633ae9"},
	}
	for item in expected {
		size,ok:=ui_test_png_size(t,item.path)
		if ok do testing.expectf(t,size==item.size,"%s dimensions changed",item.path)
		data,read_err:=os.read_entire_file_from_path(item.path,context.allocator)
		testing.expect(t,read_err==nil)
		if read_err!=nil do continue
		digest:=hash.hash_bytes(.SHA256,data,context.allocator);delete(data)
		encoded,encode_err:=hex.encode(digest,context.allocator);delete(digest)
		testing.expect(t,encode_err==.None)
		if encode_err==.None {testing.expectf(t,string(encoded)==item.sha256,"%s hash changed",item.path);delete(encoded)}
	}
	testing.expect(t,ar.UI_CHROME_DEFS[.Chronicle_Ledger_Frame].file=="chronicle/ledger_frame.png")
	testing.expect(t,ar.UI_CHROME_DEFS[.Chronicle_Content_Panel].file=="chronicle/content_panel.png")
	testing.expect(t,ar.UI_CHROME_DEFS[.Chronicle_Filter_Panel].file=="chronicle/filter_panel.png")
	testing.expect(t,ar.UI_CHROME_DEFS[.Chronicle_Unwritten_Ledger].file=="chronicle/unwritten_ledger.png")
	testing.expect(t,ar.UI_CHROME_DEFS[.Chronicle_Outcome_Seals].file=="chronicle/outcome_seals.png")
}

@(test)
mx_save_chronicle_layout_is_readable_at_compact_deck_desktop_and_4k :: proc(t:^testing.T) {
	viewports:=[4][3]f32{
		{1280,960,640},   // physical 640x480 compact design viewport
		{1280,720,1280},
		{1280,800,1280}, // Steam Deck
		{1280,720,1280}, // 4K resolves through density to this design viewport
	}
	for viewport,index in viewports {
		layout:=ar.chronicle_ui_layout(viewport[0],viewport[1],viewport[2])
		testing.expect(t,layout.outer.x==0&&layout.outer.y==0,"Chronicle ledger frame must start at the viewport edge")
		testing.expect(t,layout.outer.width==viewport[0]&&layout.outer.height==viewport[1],"Chronicle ledger frame must fill the viewport")
		testing.expect(t,layout.content.x>layout.outer.x&&layout.content.y>layout.outer.y,"Chronicle content must clear the top and left frame rails")
		testing.expect(t,layout.content.x+layout.content.width<layout.outer.width&&layout.content.y+layout.content.height<layout.outer.height,"Chronicle content must clear the right and bottom frame rails")
		testing.expect(t,layout.heading_y>=layout.content.y&&layout.footer_y<layout.content.y+layout.content.height,"Chronicle heading and footer must remain inside the frame-safe area")
		testing.expect(t,layout.summary.x>=layout.content.x&&layout.summary.x+layout.summary.width<=layout.content.x+layout.content.width)
		testing.expect(t,layout.summary.y+layout.summary.height<=layout.filters.y)
		testing.expect(t,layout.timeline.x>=layout.content.x&&layout.detail.x+layout.detail.width<=layout.content.x+layout.content.width)
		testing.expect(t,layout.timeline.y+layout.timeline.height<=layout.footer_y&&layout.detail.y+layout.detail.height<=layout.footer_y)
		testing.expect(t,layout.body.x==layout.timeline.x&&layout.body.y==layout.timeline.y,"Unified Chronicle panel must begin with the descents list")
		testing.expect(t,layout.body.x+layout.body.width==layout.detail.x+layout.detail.width&&layout.body.y+layout.body.height==layout.detail.y+layout.detail.height,"Unified Chronicle panel must enclose the descent description")
		testing.expect(t,layout.timeline.width>300&&layout.timeline.height>150)
		testing.expect(t,layout.detail.width>300&&layout.detail.height>120)
		testing.expect(t,layout.card_height==(layout.compact?f32(52):f32(46)),"Chronicle descent rows must remain compact")
		testing.expect(t,layout.visible_cards>=1)
		for visible in 0..<layout.visible_cards {
			card:=ar.chronicle_card_rect(layout,visible)
			testing.expect(t,card.x-layout.timeline.x>=ar.CHRONICLE_CARD_SIDE_INSET&&layout.timeline.x+layout.timeline.width-card.x-card.width>=ar.CHRONICLE_CARD_SIDE_INSET,"Chronicle card must clear unified panel side rails")
			testing.expect(t,card.y-layout.timeline.y>=ar.CHRONICLE_CARD_RAIL_INSET&&card.y+card.height<=layout.timeline.y+layout.timeline.height-ar.CHRONICLE_CARD_RAIL_INSET,"Chronicle card must clear unified panel top and bottom rails")
		}
		for visible_count in 1..=min(3,layout.visible_cards) {
			first:=ar.chronicle_card_rect_for_count(layout,0,visible_count)
			last:=ar.chronicle_card_rect_for_count(layout,visible_count-1,visible_count)
			top_clearance:=first.y-layout.timeline.y
			bottom_clearance:=layout.timeline.y+layout.timeline.height-last.y-last.height
			testing.expect(t,ui_test_abs_f32(top_clearance-bottom_clearance)<.01,"Filtered Chronicle row stack must remain vertically centered")
		}
		overview_safe:=ar.chronicle_detail_content_rect(layout.detail)
		testing.expect(t,overview_safe.x-layout.detail.x>=ar.CHRONICLE_DETAIL_PAD_X&&layout.detail.x+layout.detail.width-overview_safe.x-overview_safe.width>=ar.CHRONICLE_DETAIL_PAD_X,"Chronicle overview text must clear the unified panel and divider")
		testing.expect(t,overview_safe.y-layout.detail.y>=ar.CHRONICLE_DETAIL_PAD_Y&&layout.detail.y+layout.detail.height-overview_safe.y-overview_safe.height>=ar.CHRONICLE_DETAIL_PAD_Y,"Chronicle overview text must clear unified panel top and bottom rails")
		if index==0 {
			testing.expect(t,layout.compact&&layout.timeline.y+layout.timeline.height<=layout.detail.y,"compact Chronicle must stack timeline and memorial")
		} else {
			testing.expect(t,!layout.compact&&layout.timeline.x+layout.timeline.width<=layout.detail.x,"wide Chronicle must use master/detail columns")
		}
	}
}

@(test)
mx1_ui_registry_maps_exactly_100_discipline_ids_to_atlas_regions :: proc(t: ^testing.T) {
	atlas_rows := (ar.DISCIPLINE_COUNT + ar.UI_STORY_SIGIL_COUNT + ar.UI_GLYPH_ATLAS_COLUMNS - 1) /
		ar.UI_GLYPH_ATLAS_COLUMNS
	expected_atlas_size := [2]int{
		ar.UI_GLYPH_ATLAS_COLUMNS * ar.UI_GLYPH_ATLAS_CELL,
		atlas_rows * ar.UI_GLYPH_ATLAS_CELL,
	}
	testing.expectf(t, len(ar.UI_DISCIPLINE_GLYPH_KEYS) == ar.DISCIPLINE_COUNT, "typed glyph registry has %v entries, want exactly 100", len(ar.UI_DISCIPLINE_GLYPH_KEYS))
	png_size, png_ok := ui_test_png_size(t, ar.UI_GLYPH_ATLAS_FILE)
	if png_ok do testing.expectf(t, png_size == expected_atlas_size, "atlas PNG dimensions %v, want %v", png_size, expected_atlas_size)

	for id in ar.Discipline_Id {
		ordinal := int(id)
		// The canonical progression key and enum ordinal independently pin the
		// semantic key and deterministic atlas cell.
		expected_key := fmt.tprintf("menu.glyph.discipline.%s", ar.DISCIPLINES[id].key)
		region := ui_test_expected_region(ordinal)
		testing.expectf(t, ar.UI_DISCIPLINE_GLYPH_KEYS[id] == expected_key, "%v typed mapping is %v, want %v", id, ar.UI_DISCIPLINE_GLYPH_KEYS[id], expected_key)
		testing.expectf(t, region[2] == ar.UI_GLYPH_ATLAS_CELL && region[3] == ar.UI_GLYPH_ATLAS_CELL, "%v atlas cell size changed", id)
		for other_i in 0 ..< ordinal {
			other := ar.Discipline_Id(other_i)
			testing.expectf(t, ar.UI_DISCIPLINE_GLYPH_KEYS[other] != ar.UI_DISCIPLINE_GLYPH_KEYS[id], "%v duplicates glyph key %v", id, ar.UI_DISCIPLINE_GLYPH_KEYS[id])
			testing.expectf(t, ui_test_expected_region(other_i) != region, "%v duplicates atlas region %v", id, region)
		}
	}

	testing.expectf(t, len(ar.STORY_SIGIL_NAMES) == ar.UI_STORY_SIGIL_COUNT, "typed story sigil registry has %v entries, want %v", len(ar.STORY_SIGIL_NAMES), ar.UI_STORY_SIGIL_COUNT)
	for id in ar.Story_Sigil_Id {
		ordinal := ar.DISCIPLINE_COUNT + int(id)
		name := ar.STORY_SIGIL_NAMES[id]
		key := fmt.tprintf("menu.glyph.sigil.%s", name)
		region := ui_test_expected_region(ordinal)
		testing.expectf(t, name != "" && key != "", "%v story sigil has no semantic key", id)
		testing.expectf(t, region[2] == ar.UI_GLYPH_ATLAS_CELL && region[3] == ar.UI_GLYPH_ATLAS_CELL, "%v story sigil cell size changed", id)
		for other_i in 0 ..< int(id) {
			other := ar.Story_Sigil_Id(other_i)
			testing.expectf(t, ar.STORY_SIGIL_NAMES[other] != name, "%v duplicates story sigil key %v", id, key)
			testing.expectf(t, ui_test_expected_region(ar.DISCIPLINE_COUNT+other_i) != region, "%v duplicates story sigil atlas region %v", id, region)
		}
	}

	ouroboros_ordinal := ar.DISCIPLINE_COUNT + int(ar.Story_Sigil_Id.Ouroboros)
	expected_ouroboros_key := fmt.tprintf("menu.glyph.sigil.%s", ar.STORY_SIGIL_NAMES[.Ouroboros])
	ouroboros_region := ui_test_expected_region(ouroboros_ordinal)
	testing.expect(t, ar.UI_GLYPH_OUROBOROS_KEY == expected_ouroboros_key, "Ouroboros semantic key changed")
	testing.expect(t, ouroboros_region[2] == 32 && ouroboros_region[3] == 32, "Ouroboros atlas region is not deterministic")
}
