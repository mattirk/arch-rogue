package archrogue_tests

// Headless MX.1 contract for the canonical authored UI pack. No texture is
// loaded here: typed metadata, exact atlas ordering, and PNG headers are
// validated without opening a raylib window.

import "core:crypto/hash"
import "core:encoding/hex"
import "core:fmt"
import "core:os"
import "core:strings"
import "core:testing"
import ar "../src"
import rl "../vendor/raylib"

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
archetype_selection_uses_complete_effective_level_one_stats :: proc(t: ^testing.T) {
	expected_melee := [ar.Archetype_Id]int{
		.Warden = 15, .Rogue = 17, .Arcanist = 12, .Acolyte = 13, .Ranger = 15,
	}
	expected_spell := [ar.Archetype_Id]int{
		.Warden = 16, .Rogue = 16, .Arcanist = 25, .Acolyte = 21, .Ranger = 18,
	}
	expected_armor := [ar.Archetype_Id]int{
		.Warden = 2, .Rogue = 0, .Arcanist = 0, .Acolyte = 1, .Ranger = 0,
	}
	expected_speed := [ar.Archetype_Id]f32{
		.Warden = 2.68, .Rogue = 3.16, .Arcanist = 2.60, .Acolyte = 2.64, .Ranger = 2.96,
	}
	for archetype in ar.Archetype_Id {
		stats := ar.archetype_preview_stats(archetype)
		def := ar.ARCHETYPES[archetype]
		testing.expect(t, stats.health == def.max_hp && stats.mana == def.max_mana && stats.stamina == def.max_stamina)
		testing.expectf(t, stats.melee == expected_melee[archetype], "%v preview melee is %v", archetype, stats.melee)
		testing.expectf(t, stats.spell == expected_spell[archetype], "%v preview spell is %v", archetype, stats.spell)
		testing.expectf(t, stats.armor == expected_armor[archetype], "%v preview armor is %v", archetype, stats.armor)
		testing.expectf(t, ui_test_abs_f32(stats.move_speed-expected_speed[archetype]) < .001, "%v preview speed is %.3f", archetype, stats.move_speed)
	}
}

@(test)
archetype_stat_panels_have_stable_art_and_layout :: proc(t: ^testing.T) {
	expected_chrome := [ar.Select_Stat_Id]ar.UI_Chrome_Id{
		.Health = .Stat_Health,
		.Mana = .Stat_Mana,
		.Stamina = .Stat_Stamina,
		.Movement = .Stat_Movement,
		.Melee = .Stat_Melee,
		.Spell = .Stat_Spell,
		.Armor = .Stat_Armor,
	}
	for id in ar.Select_Stat_Id {
		chrome := expected_chrome[id]
		testing.expect(t, ar.SELECT_STAT_CHROME[id] == chrome)
		def := ar.UI_CHROME_DEFS[chrome]
		testing.expect(t, def.render == .Nine_Slice && def.source_size == [2]int{328, 85})
		testing.expect(t, def.scale_insets_with_height && def.has_content_insets)
	}

	content := rl.Rectangle{20, 30, 732, 170}
	rects := ar.select_stat_rects(content)
	for id in ar.Select_Stat_Id {
		rect := rects[id]
		testing.expect(t, rect.x >= content.x && rect.y >= content.y)
		testing.expect(t, rect.x+rect.width <= content.x+content.width+.01)
		testing.expect(t, rect.y+rect.height <= content.y+content.height+.01)
		testing.expect(t, rect.width >= 250 && rect.width <= 264.01 && rect.height >= 30)
	}
	testing.expect(t, rects[.Health].x+rects[.Health].width < rects[.Melee].x)
	group_center := (rects[.Health].x+rects[.Armor].x+rects[.Armor].width)*.5
	testing.expect(t, ui_test_abs_f32(group_center-(content.x+content.width*.5)) < .01)
	testing.expect(t, rects[.Movement].y > rects[.Stamina].y)

	expected_art := [7]struct{path, sha256: string}{
		{"assets/ui/chrome/stat_health.png", "d90be5e517cc689ea632fd1b6dfaa55f06c7655939753b05b90a112c59eebe20"},
		{"assets/ui/chrome/stat_mana.png", "8a8df97249064c354e6dfdb4d3beb522bff97533e7d505836036813437545e7e"},
		{"assets/ui/chrome/stat_stamina.png", "2bda2a1fef8577d1f01ab445543867c0106a2a7f11f7ba91a9affdd87b65edbf"},
		{"assets/ui/chrome/stat_movement.png", "020e14de8cb5d0a46055501f5a63e01174052facd5d0d7c8f36c8c5fad51df4b"},
		{"assets/ui/chrome/stat_melee.png", "09bbb4b8245bba72e9ccc33f6d61462aacef8daf420901792982479e281b0166"},
		{"assets/ui/chrome/stat_spell.png", "97cc29ccbe8b193fc90435050159b6f2b57ae6bb304a0e90bdff042b4515f398"},
		{"assets/ui/chrome/stat_armor.png", "b6a66a1d73f8f7d7816dbce69d841726e538bb7a2e5a683cfb321dff968e3c30"},
	}
	for item in expected_art {
		size, ok := ui_test_png_size(t, item.path)
		if ok do testing.expect(t, size == [2]int{328, 85})
		data, read_err := os.read_entire_file_from_path(item.path, context.allocator)
		testing.expect(t, read_err == nil)
		if read_err != nil do continue
		digest := hash.hash_bytes(.SHA256, data, context.allocator)
		delete(data)
		encoded, encode_err := hex.encode(digest, context.allocator)
		delete(digest)
		testing.expect(t, encode_err == .None)
		if encode_err == .None {
			testing.expectf(t, string(encoded) == item.sha256, "%s hash changed", item.path)
			delete(encoded)
		}
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
forged_iron_ui_imports_match_approved_pixellab_art :: proc(t: ^testing.T) {
	expected := [5]struct{id: ar.UI_Chrome_Id, sha256: string}{
		{.Menu_Panel, "97e959742185395240a8c64bf937e30d1514702a4c365bb635b5922d38ee2470"},
		{.Menu_Panel_Compact, "97e959742185395240a8c64bf937e30d1514702a4c365bb635b5922d38ee2470"},
		{.Menu_Panel_Inset, "97e959742185395240a8c64bf937e30d1514702a4c365bb635b5922d38ee2470"},
		{.Menu_Row, "3ba0caecf0040a7ac346d2e8c5d9e2592df5f48f9ecdc0324772f535cb6ecdab"},
		{.Menu_Row_Selected, "db0553102e35fc6e1986d50c93c641aa4866de4ee9e041dce825d3b6bf461304"},
	}
	for item in expected {
		def := ar.UI_CHROME_DEFS[item.id]
		path := fmt.aprintf("assets/ui/%s", def.file)
		defer delete(path)
		data, read_err := os.read_entire_file_from_path(path, context.allocator)
		testing.expect(t, read_err == nil)
		if read_err != nil do continue
		digest := hash.hash_bytes(.SHA256, data, context.allocator)
		delete(data)
		encoded, encode_err := hex.encode(digest, context.allocator)
		delete(digest)
		testing.expect(t, encode_err == .None)
		if encode_err == .None {
			testing.expectf(t, string(encoded) == item.sha256, "%s differs from approved PixelLab art", path)
			delete(encoded)
		}
		if item.id == .Menu_Panel || item.id == .Menu_Panel_Compact || item.id == .Menu_Panel_Inset {
			testing.expect(t, def.fill_color == rl.Color{16,16,20,255}, "transparent iron frames need an opaque dark backing")
		}
	}
}

@(test)
menu_rows_keep_text_stable_and_clear_iron_endcaps :: proc(t: ^testing.T) {
	targets := [5]rl.Rectangle{
		{0,0,600,44}, // options
		{0,0,430,34}, // controls
		{0,0,360,ar.ITEM_ROW_HEIGHT}, // inventory
		{0,0,180,34}, // character tabs
		{0,0,150,30}, // shop tabs
	}
	for target in targets {
		plain, plain_ok := ar.ui_chrome_content_rect_from_def(ar.ui_chrome_def(.Menu_Row),target)
		selected, selected_ok := ar.ui_chrome_content_rect_from_def(ar.ui_chrome_def(.Menu_Row_Selected),target)
		stable, stable_ok := ar.menu_row_content_rect(target)
		testing.expect(t,plain_ok && selected_ok && stable_ok,"menu row content metadata must resolve headlessly")
		if !plain_ok || !selected_ok || !stable_ok do continue

		plain_right := plain.x+plain.width
		selected_right := selected.x+selected.width
		stable_right := stable.x+stable.width
		testing.expect(t,plain == selected,"iron row states must keep identical text placement")
		testing.expect(t,selected_right == plain_right,"iron row states must keep identical right margins")
		testing.expect(t,ui_test_abs_f32(stable.x-max(plain.x,selected.x)) < .01,"stable menu text rail changed its left anchor")
		testing.expect(t,ui_test_abs_f32(stable_right-min(plain_right,selected_right)) < .01,"stable menu text rail can overlap a row-state endcap")
		testing.expect(t,stable.width >= 48,"supported menu row collapsed below its usable text width")
	}
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
menu_title_logo_is_centered_and_spin_matches_pygame_timing :: proc(t: ^testing.T) {
	for size in ([4][2]f32{{640, 480}, {1280, 720}, {1920, 1200}, {2560, 1080}}) {
		safe := ar.menu_background_content_rect(size[0], size[1])
		rect := ar.title_logo_rect(size[0], size[1])
		logo_center := rect.x + rect.width*.5
		testing.expect(t, ui_test_abs_f32(logo_center - (safe.x+safe.width*.5)) < .01, "title logo is not horizontally centered")
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

// Proportional uppercase advances and small-font tracking, deliberately unlike
// a character-count estimate. No raylib font, texture, or global font mutation.
@(private = "file")
ui_test_inventory_measure :: proc(text: string, size: i32) -> i32 {
	width: f32
	count := 0
	for character in text {
		upper := character
		if upper >= 'a' && upper <= 'z' do upper -= 'a'-'A'
		advance: f32 = .60
		switch upper {
		case ' ': advance = .34
		case 'I', '!', '.', ':', '|': advance = .28
		case 'M', 'W': advance = .85
		}
		width += advance*f32(size)
		if count > 0 && size < 14 do width += .5
		count += 1
	}
	return i32(width+.5)
}

@(private = "file")
ui_test_rect_inside :: proc(inner, outer: rl.Rectangle) -> bool {
	return inner.x >= outer.x-.01 && inner.y >= outer.y-.01 &&
		inner.width >= 0 && inner.height >= 0 &&
		inner.x+inner.width <= outer.x+outer.width+.01 &&
		inner.y+inner.height <= outer.y+outer.height+.01
}

@(test)
inventory_ui_fitted_and_wrapped_text_uses_measured_width :: proc(t: ^testing.T) {
	texts := [5]string{
		"! Storm-touched greatsword of the forgotten moon",
		"Grave-hungering, of the occult, of alacrity",
		"Cursed bargain: stronger, slower handling.\n\nPower 2147483647 | lightning damage",
		"éclatéclatéclatéclatéclatéclatéclat",
		"WWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWW",
	}
	for text in texts {
		for width in ([7]f32{0, 5, 16, 48, 120, 241, 359}) {
			fit := ar.ui_fit_text_line(text, width, 16, 12, ui_test_inventory_measure)
			testing.expect(t, fit.font >= 12 && fit.font <= 16, "row fitting must retain a readable size floor")
			testing.expectf(t, f32(ui_test_inventory_measure(fit.text,fit.font)) <= width, "fitted %s escapes width %.0f", fit.text, width)
			if fit.text != text && fit.text != "" {
				testing.expect(t, strings.has_suffix(fit.text,"..."), "truncated rows need an explicit ellipsis")
				keep := len(fit.text)-3
				testing.expect(t, keep >= 0 && keep < len(text) && (text[keep]&0xc0) != 0x80, "ellipsis splits a UTF-8 codepoint")
			}
		}
		for width in ([5]f32{16, 48, 120, 241, 275}) {
			lines: [ar.STORY_UI_MAX_TEXT_LINES]ar.Story_UI_Text_Line
			count := ar.story_ui_wrap_text(text, width, 12, &lines, ui_test_inventory_measure)
			testing.expect(t, count > 0 && count < len(lines))
			covered := 0
			for line in lines[:count] {
				testing.expect(t, line.start >= covered && line.end >= line.start && line.end <= len(text))
				for byte in text[covered:line.start] do testing.expect(t, byte == ' ' || byte == '\n' || byte == '\t' || byte == '\r', "wrapping discarded non-whitespace content")
				testing.expect(t, f32(ui_test_inventory_measure(text[line.start:line.end],12)) <= width, "wrapped line escapes its measured rail")
				if line.end < len(text) do testing.expect(t, (text[line.end]&0xc0) != 0x80, "long-word wrapping splits UTF-8")
				covered = line.end
			}
			testing.expect(t, covered == len(text), "wrapping must preserve the final content, not just clip it")
		}
	}
	short := ar.ui_fit_text_line("Iron", 200, 16, 12, ui_test_inventory_measure)
	testing.expect(t, short.text == "Iron" && short.font == 16, "short rows should not shrink")
	testing.expect(t, ar.ui_fit_text_line("WW",5,16,12,ui_test_inventory_measure).text == "", "a rail narrower than an ellipsis must not return overflowing text")
}

@(test)
inventory_ui_rows_reserve_stats_and_clear_native_and_compact_endcaps :: proc(t: ^testing.T) {
	for row_width in ([3]f32{360, 300, 240}) {
		row := rl.Rectangle{80,120,row_width,ar.ITEM_ROW_HEIGHT}
		chrome_content, ok := ar.menu_row_content_rect(row)
		testing.expect(t, ok)
		testing.expect(t, chrome_content.y >= row.y+8 && chrome_content.y+chrome_content.height <= row.y+row.height-8, "item content must clear the iron rails vertically")
		testing.expect(t, chrome_content.height >= 30, "row must fit a shop icon or an inventory name plus affixes")
		// Equipped lines use the whole inset rail; bag rows also reserve the
		// iron endcap, regardless of the row's selected state.
		for content in ([2]rl.Rectangle{{row.x,row.y,row.width,38}, chrome_content}) {
			for has_icon in ([2]bool{false,true}) {
				for affixed in ([2]bool{false,true}) {
					stat := "pow 2147483647"
					layout := ar.inventory_item_line_layout(content, has_icon, affixed, f32(ui_test_inventory_measure(stat,14))+1)
					testing.expect(t, ui_test_rect_inside(layout.name,content) && ui_test_rect_inside(layout.stat,content))
					testing.expect(t, layout.name.x+layout.name.width+7.99 <= layout.stat.x, "name and power/defense columns overlap")
					if has_icon do testing.expect(t, layout.name.x >= layout.icon.x+layout.icon.width+6 && ui_test_rect_inside(layout.icon,content))
					if affixed do testing.expect(t, ui_test_rect_inside(layout.affixes,content), "affixes fall below the row")
					name := ar.ui_fit_text_line("! Storm-touched greatsword of the forgotten moon",layout.name.width-1,16,12,ui_test_inventory_measure)
					power := ar.ui_fit_text_line(stat,layout.stat.width-1,14,11,ui_test_inventory_measure)
					testing.expect(t, f32(ui_test_inventory_measure(name.text,name.font)) < layout.name.width)
					testing.expect(t, f32(ui_test_inventory_measure(power.text,power.font)) < layout.stat.width)
					if affixed {
						fit := ar.ui_fit_text_line("Grave-hungering, of the occult, of alacrity",layout.affixes.width-1,12,11,ui_test_inventory_measure)
						testing.expect(t, f32(ui_test_inventory_measure(fit.text,fit.font)) < layout.affixes.width)
					}
				}
			}
			no_stat := ar.inventory_item_line_layout(content, true, false, 0)
			testing.expect(t, no_stat.stat.width == 0 && no_stat.name.x+no_stat.name.width == content.x+content.width, "unidentified and consumable names should reclaim the stat column")
		}
	}
}

@(private = "file")
ui_test_inventory_stacked_item :: proc() -> ar.Item {
	item := ar.Item{
		kind = .Weapon, rarity = .Rare, power = 2147483647, cursed = true,
		name = "Storm-touched greatsword of the forgotten moon and the last watch over the ancient gates beneath the sunken bastion of the first warden and the undying sovereign of the deep",
		affix_count = 3, affixes = {{kind=.Grave_Hungering},{kind=.Of_The_Occult},{kind=.Of_Alacrity}},
		attack_speed = .25, cast_speed = -.15, move_speed = -.08, thorns = 2147483647, lifesteal = .12,
		typed = true, damage_type = .Physical, proc_effect = .Ignite, proc_chance = .33, unique_effect = .Oathwall_Aegis,
	}
	for effect in ar.Proc_Effect do item.proc_effects[effect] = effect != .None
	for bonus in ar.Skill_Bonus do item.skill_bonuses[bonus] = true
	return item
}

@(private = "file")
ui_test_inventory_detail_text :: proc(layout: ar.Inventory_Detail_Layout) -> string {
	parts: [ar.STORY_UI_MAX_TEXT_LINES]string
	for index in 0..<layout.line_count do parts[index] = layout.lines[index].text
	return strings.join(parts[:layout.line_count], " ", context.temp_allocator)
}

@(test)
inventory_ui_detail_wraps_and_grows_without_losing_proc_or_skill_lines :: proc(t: ^testing.T) {
	item := ui_test_inventory_stacked_item()
	for screen in ([4][2]f32{{1280,720},{640,480},{960,540},{2560,1440}}) {
		presentation := ar.ui_presentation_for_size(screen[0],screen[1])
		inventory := ar.inventory_panel_rect_for_width(presentation.width)
		layout := ar.inventory_detail_layout(item,inventory,presentation.height,false,ui_test_inventory_measure)
		testing.expectf(t, !layout.overflowed, "maximal detail must fit at %v: panel %v, %v visible lines", screen, layout.panel, layout.line_count)
		testing.expect(t, layout.panel.height > 372, "dense details must grow beyond the old fixed plate")
		testing.expect(t, layout.panel.x >= 8 && layout.panel.x+layout.panel.width+16 <= inventory.x+.01)
		testing.expect(t, layout.panel.y+layout.panel.height <= presentation.height-16+.01)
		chrome, ok := ar.ui_chrome_content_rect_from_def(ar.ui_chrome_def(.Menu_Panel_Compact),layout.panel)
		testing.expect(t, ok && ui_test_rect_inside(layout.content,chrome), "detail content must honor the 24px/22px panel insets")
		testing.expect(t, ui_test_rect_inside(layout.icon,layout.content))
		previous_bottom := layout.content.y
		names, procs := 0, 0
		curse := false
		for line in layout.lines[:layout.line_count] {
			testing.expectf(t, ui_test_rect_inside(line.rect,layout.content), "%s escapes the detail content area",line.text)
			testing.expectf(t, f32(ui_test_inventory_measure(line.text,line.font)) <= line.rect.width, "%s exceeds its measured width",line.text)
			testing.expect(t, line.rect.y >= previous_bottom, "wrapped details overlap a following stat or curse")
			previous_bottom = line.rect.y+line.rect.height
			if line.font == 18 do names += 1
			if strings.has_prefix(line.text,"Proc: ") do procs += 1

			if strings.has_prefix(line.text,"Cursed bargain:") do curse = true
		}
		testing.expectf(t, names > 1 && procs == len(ar.Proc_Effect)-1 && curse, "detail content missing at %v: name lines %v, procs %v/%v, curse %v", screen, names, procs, len(ar.Proc_Effect)-1, curse)
		text := ui_test_inventory_detail_text(layout)
		skill_names: [len(ar.Skill_Bonus)]string
		for bonus in ar.Skill_Bonus do skill_names[int(bonus)] = ar.SKILL_BONUS_NAMES[bonus]
		expected_skills := fmt.tprintf("Skills: %s", strings.join(skill_names[:], ", ", context.temp_allocator))
		testing.expect(t, strings.contains(text,expected_skills), "wrapping must preserve every complete skill name in order")
		testing.expect(t, strings.contains(text,"Unique: oathwall aegis"), "the bespoke unique effect must remain visible")
		testing.expect(t, strings.contains(text,"Cursed bargain: stronger, slower handling."), "the complete curse description must survive, not just its first line")
		for effect in ar.Proc_Effect {
			if effect == .None do continue
			found := false
			for line in layout.lines[:layout.line_count] do if line.text == fmt.tprintf("Proc: %s  33%%",ar.PROC_EFFECT_NAMES[effect]) do found = true
			testing.expect(t, found, "a proc name or its chance disappeared")
		}
		plain := ar.inventory_detail_layout(ar.Item{kind=.Weapon,name="Iron sword",power=5},inventory,presentation.height,false,ui_test_inventory_measure)
		testing.expect(t, plain.panel.width == 324 && plain.panel.height == 372, "ordinary items must retain the existing detail plate")
		armor := item
		armor.kind = .Armor
		armor.defense = 2147483647
		armor_layout := ar.inventory_detail_layout(armor,inventory,presentation.height,true,ui_test_inventory_measure)
		testing.expect(t, !armor_layout.overflowed && strings.contains(ui_test_inventory_detail_text(armor_layout),"Defense 2147483647"), "equipped armor must retain defense and all final descriptions too")
	}
}

@(test)
inventory_ui_unidentified_and_empty_rows_do_not_reveal_hidden_details :: proc(t: ^testing.T) {
	inventory := ar.inventory_panel_rect_for_width(1280)
	for kind in ([2]ar.Item_Kind{.Weapon,.Armor}) {
		hidden := ui_test_inventory_stacked_item()
		hidden.kind = kind
		hidden.unidentified = true
		minimal := ar.Item{kind=kind,unidentified=true}
		actual := ar.inventory_detail_layout(hidden,inventory,720,true,ui_test_inventory_measure)
		expected := ar.inventory_detail_layout(minimal,inventory,720,true,ui_test_inventory_measure)
		testing.expect(t, actual.line_count == expected.line_count && actual.panel == expected.panel, "hidden stats changed the detail shape")
		for line,index in actual.lines[:actual.line_count] do testing.expect(t, line == expected.lines[index], "unidentified details reveal name, rarity, curse, affixes, or rolls")
		testing.expect(t, actual.lines[0].text == "EQUIPPED ITEM")
		row := ar.inventory_item_line_text(hidden,true,"")
		testing.expect(t, row.name == ar.item_display_name(minimal) && row.stat == "" && row.affixes == "")
		empty := ar.inventory_item_line_text(hidden,false,"weapon")
		testing.expect(t, empty.name == "- no weapon -" && empty.stat == "" && empty.affixes == "", "an empty focused slot must not render stale item data")
	}
}

@(test)
inventory_ui_equipped_hitboxes_and_clipping_follow_presentation_scale :: proc(t: ^testing.T) {
	testing.expect(t, len(ar.INVENTORY_FOOTER_LINES) <= 3, "inventory hints must stay compact instead of listing every alternate shortcut")
	for action in ([6]string{"browse", "preview", "use/equip", "drop", "sort", "close"}) {
		count := 0
		for text in ar.INVENTORY_FOOTER_LINES do count += strings.count(text, action)
		testing.expectf(t, count == 1, "footer must describe %s once, not repeat it for alternate bindings", action)
	}
	for screen in ([5][2]f32{{1280,720},{640,480},{960,540},{1366,768},{2560,1440}}) {
		presentation := ar.ui_presentation_for_size(screen[0],screen[1])
		panel := ar.inventory_panel_rect_for_width(presentation.width)
		weapon := ar.inventory_equipped_rect_in_panel(panel,.Weapon)
		armor := ar.inventory_equipped_rect_in_panel(panel,.Armor)
		testing.expect(t, weapon.y+weapon.height <= armor.y && armor.y+armor.height <= panel.y+118, "equipped hitboxes overlap each other or sorting chips")
		for focus in ([2]ar.Inventory_Focus{.Weapon,.Armor}) {
			rect := ar.inventory_equipped_rect_in_panel(panel,focus)
			testing.expect(t, rect.x >= panel.x+24 && rect.x+rect.width <= panel.x+panel.width-24)
			physical := rl.Vector2{rect.x+rect.width*.5,rect.y+rect.height*.5}*presentation.scale
			actual, found := ar.inventory_equipped_at_in_panel(panel,physical/presentation.scale)
			testing.expect(t, found && actual == focus, "screen-to-design hit testing selects the wrong equipped slot")
			clip := ar.ui_content_scissor_rect(rect,presentation.scale)
			physical_rect := rl.Rectangle{rect.x*presentation.scale,rect.y*presentation.scale,rect.width*presentation.scale,rect.height*presentation.scale}
			testing.expect(t, ui_test_rect_inside(clip,physical_rect) && clip.width > 0 && clip.height > 0, "scissors must round inward after scaling")
			testing.expect(t, clip.x == f32(i32(clip.x)) && clip.y == f32(i32(clip.y)) && clip.width == f32(i32(clip.width)) && clip.height == f32(i32(clip.height)))
		}
		for point in ([5]rl.Vector2{{panel.x+23,weapon.y+5},{weapon.x+weapon.width,weapon.y+5},{weapon.x,weapon.y-1},{weapon.x,weapon.y+weapon.height},{armor.x,armor.y+armor.height}}) {
			_, found := ar.inventory_equipped_at_in_panel(panel,point)
			testing.expect(t, !found, "a panel margin or gap must not select an equipped item")
		}
		testing.expect(t, ar.inventory_equipped_rect_in_panel(panel,.Bag) == rl.Rectangle{})
		for text,line in ar.INVENTORY_FOOTER_LINES {
			rect := ar.inventory_footer_rect(panel,line)
			fit := ar.ui_fit_text_line(text,rect.width-1,11,10,ui_test_inventory_measure)
			testing.expect(t, fit.text == text && fit.font == 11, "primary hints must fit without truncation or shrinking")
			testing.expect(t, rect.y > panel.y+544 && rect.y+rect.height <= panel.y+panel.height-22, "footer collides with bag rows or panel rails")
		}
		testing.expect(t, panel.y+panel.height <= presentation.height-16, "taller inventory must remain inside the viewport")
	}
}

@(test)
inventory_ui_focus_highlights_only_its_section_and_allows_empty_equipment :: proc(t: ^testing.T) {
	app: ar.App
	testing.expect(t, app.inv_focus == .Bag)
	app.inv_index = 1
	app.run.player.bag_count = 2
	app.run.player.bag[1] = {kind=.Weapon,name="Bag sword"}
	app.run.player.weapon = {kind=.Weapon,name="Equipped sword"}
	app.run.player.armor = {kind=.Armor,name="Equipped mail"}
	app.run.player.has_weapon = true
	app.run.player.has_armor = true
	for modality in ([2]ar.Mobile_Input_Modality{.Keyboard_Mouse,.Controller}) {
		app.input_modality = modality
		for focus in ar.Inventory_Focus {
			app.inv_focus = focus
			for candidate in ar.Inventory_Focus do testing.expect(t, ar.inventory_row_selected(&app,candidate,1) == (candidate == focus), "selection leaked into an unfocused section")
			testing.expect(t, !ar.inventory_row_selected(&app,.Bag,0))
			item, found := ar.inventory_selected_item(&app)
			testing.expect(t, found)
			layout := ar.inventory_detail_layout(item,ar.inventory_panel_rect_for_width(1280),720,focus != .Bag,ui_test_inventory_measure)
			testing.expect(t, layout.lines[0].text == (focus == .Bag ? "SELECTED ITEM" : "EQUIPPED ITEM"))
		}
	}
	app.run.player.has_weapon = false
	app.run.player.has_armor = false
	for focus in ([2]ar.Inventory_Focus{.Weapon,.Armor}) {
		app.inv_focus = focus
		_, found := ar.inventory_selected_item(&app)
		testing.expect(t, !found && ar.inventory_row_selected(&app,focus), "empty equipment can hold focus but must not show a detail panel")
	}
	app.input_modality = .Touch
	for focus in ar.Inventory_Focus do testing.expect(t, !ar.inventory_row_selected(&app,focus,1), "ordinary touch rows must not retain navigation highlighting")
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
