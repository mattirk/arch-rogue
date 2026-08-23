package archrogue

// Screen-space UI. MX.1 keeps all presentation policy local to this file so
// the deterministic app/simulation layers remain resolution- and raylib-free.

import "core:fmt"
import "core:strings"
import rl "../vendor/raylib"

COLOR_TITLE :: rl.Color{221, 168, 83, 255}
COLOR_ROW :: rl.Color{28, 24, 36, 255}
COLOR_ROW_SELECTED :: rl.Color{52, 44, 66, 255}

ui_navigation_selected :: proc(app:^App,selected:bool)->bool {
	if app==nil do return selected
	return selected && mobile_navigation_focus_visible(app.input_modality,.Ordinary)
}

UI_REFERENCE_WIDTH  :: f32(1280)
UI_REFERENCE_HEIGHT :: f32(720)
UI_CAROUSEL_WIDE    :: f32(900)

UI_Presentation :: struct {
	scale:            f32,
	width:            f32,
	height:           f32,
	responsive_width: f32,
}

// Physical 640x480 through 2560x1440 all resolve to a roomy design viewport.
// responsive_width deliberately removes only integer high-DPI density: 640 is
// still a compact layout, while 960 and larger use the five-position carousel.
ui_presentation :: proc() -> UI_Presentation {
	physical_w := f32(max(1, rl.GetScreenWidth()))
	physical_h := f32(max(1, rl.GetScreenHeight()))
	scale := min(physical_w / UI_REFERENCE_WIDTH, physical_h / UI_REFERENCE_HEIGHT)
	if scale <= 0 do scale = 1
	density := max(1, int(scale))
	return {
		scale = scale,
		width = physical_w / scale,
		height = physical_h / scale,
		responsive_width = physical_w / f32(density),
	}
}

ui_begin_presentation :: proc() -> UI_Presentation {
	presentation := ui_presentation()
	camera := rl.Camera2D{zoom = presentation.scale}
	rl.BeginMode2D(camera)
	return presentation
}

ui_end_presentation :: proc() {
	rl.EndMode2D()
}

ui_screen_to_design :: proc(point: rl.Vector2) -> rl.Vector2 {
	presentation := ui_presentation()
	return point / presentation.scale
}

ui_design_width :: proc() -> f32 {
	return ui_presentation().width
}

ui_design_height :: proc() -> f32 {
	return ui_presentation().height
}

ui_fit_insets :: proc(first, second, extent: f32) -> (f32, f32) {
	if first + second <= extent || first + second <= 0 do return first, second
	scale := extent / (first + second)
	return first * scale, second * scale
}

ui_chrome_inset_scale :: proc(
	asset: ^UI_Chrome_Asset,
	target_width, target_height: f32,
) -> f32 {
	if asset == nil do return 1
	source_width := max(f32(1), f32(asset.source_size[0]))
	source_height := max(f32(1), f32(asset.source_size[1]))
	if asset.scale_insets_with_fit {
		return min(target_width / source_width, target_height / source_height)
	}
	if asset.scale_insets_with_height do return target_height / source_height
	if asset.shrink_insets_below_height > 0 {
		return min(f32(1), target_height / f32(asset.shrink_insets_below_height))
	}
	return 1
}

// Transparent centers and stretched edges render below authored corners. This
// keeps fractional display scaling from covering or squaring off corner pixels.
UI_NINE_SLICE_DRAW_ORDER := [9][2]int{
	{1, 1},
	{1, 0}, {0, 1}, {2, 1}, {1, 2},
	{0, 0}, {2, 0}, {0, 2}, {2, 2},
}

// Repeat complete edge phases and distribute them evenly across the target.
// This keeps both authored rail ends adjacent to their matching corners instead
// of restarting a partial tile immediately before the far corner.
draw_ui_tiled_slice :: proc(
	tex: rl.Texture2D,
	source, target: rl.Rectangle,
	horizontal: bool,
	tint: rl.Color,
) {
	if source.width <= 0 || source.height <= 0 || target.width <= 0 || target.height <= 0 do return
	if horizontal {
		ideal_width := max(f32(1), source.width * target.height / source.height)
		tile_count := max(1, int(target.width/ideal_width+.5))
		for tile_index in 0..<tile_count {
			left := target.x + target.width*f32(tile_index)/f32(tile_count)
			right := target.x + target.width*f32(tile_index+1)/f32(tile_count)
			rl.DrawTexturePro(
				tex,
				source,
				{left, target.y, right-left, target.height},
				{},
				0,
				tint,
			)
		}
		return
	}

	ideal_height := max(f32(1), source.height * target.width / source.width)
	tile_count := max(1, int(target.height/ideal_height+.5))
	for tile_index in 0..<tile_count {
		top := target.y + target.height*f32(tile_index)/f32(tile_count)
		bottom := target.y + target.height*f32(tile_index+1)/f32(tile_count)
		rl.DrawTexturePro(
			tex,
			source,
			{target.x, top, target.width, bottom-top},
			{},
			0,
			tint,
		)
	}
}

// Reusable metadata-driven nine-slice. Source borders stay at authored pixels;
// target borders follow the manifest's scaling policy before being fitted.
draw_ui_nine_slice :: proc(asset: ^UI_Chrome_Asset, target: rl.Rectangle, tint := rl.WHITE) -> bool {
	if asset == nil || !asset.valid || asset.tex.id == 0 || !asset.has_insets ||
		target.width <= 0 || target.height <= 0 {
		return false
	}
	source_w := f32(asset.source_size[0])
	source_h := f32(asset.source_size[1])
	if source_w <= 0 || source_h <= 0 do return false

	left := f32(asset.insets[0])
	top := f32(asset.insets[1])
	right := f32(asset.insets[2])
	bottom := f32(asset.insets[3])
	if left + right > source_w || top + bottom > source_h do return false

	inset_scale := ui_chrome_inset_scale(asset, target.width, target.height)
	target_left, target_right := ui_fit_insets(left * inset_scale, right * inset_scale, target.width)
	target_top, target_bottom := ui_fit_insets(top * inset_scale, bottom * inset_scale, target.height)
	source_x := [4]f32{0, left, source_w - right, source_w}
	source_y := [4]f32{0, top, source_h - bottom, source_h}
	target_x := [4]f32{target.x, target.x + target_left, target.x + target.width - target_right, target.x + target.width}
	target_y := [4]f32{target.y, target.y + target_top, target.y + target.height - target_bottom, target.y + target.height}
	for cell in UI_NINE_SLICE_DRAW_ORDER {
		column, row := cell[0], cell[1]
		source := rl.Rectangle{
			source_x[column], source_y[row],
			source_x[column + 1] - source_x[column],
			source_y[row + 1] - source_y[row],
		}
		destination := rl.Rectangle{
			target_x[column], target_y[row],
			target_x[column + 1] - target_x[column],
			target_y[row + 1] - target_y[row],
		}
		if source.width <= 0 || source.height <= 0 || destination.width <= 0 || destination.height <= 0 do continue
		if asset.tile_edges && column == 1 && row != 1 {
			draw_ui_tiled_slice(asset.tex, source, destination, true, tint)
		} else if asset.tile_edges && row == 1 && column != 1 {
			draw_ui_tiled_slice(asset.tex, source, destination, false, tint)
		} else {
			rl.DrawTexturePro(asset.tex, source, destination, {}, 0, tint)
		}
	}
	return true
}

// Safe content area corresponding to draw_ui_nine_slice/draw_ui_chrome.
ui_chrome_content_rect :: proc(asset: ^UI_Chrome_Asset, target: rl.Rectangle) -> (rl.Rectangle, bool) {
	if asset == nil || !asset.valid || !asset.has_content_insets || target.width <= 0 || target.height <= 0 {
		return target, false
	}
	left := f32(asset.content_insets[0])
	top := f32(asset.content_insets[1])
	right := f32(asset.content_insets[2])
	bottom := f32(asset.content_insets[3])

	if asset.render == .Nine_Slice && asset.has_insets {
		inset_scale := ui_chrome_inset_scale(asset, target.width, target.height)
		desired_left := f32(asset.insets[0]) * inset_scale
		desired_top := f32(asset.insets[1]) * inset_scale
		desired_right := f32(asset.insets[2]) * inset_scale
		desired_bottom := f32(asset.insets[3]) * inset_scale
		fitted_left, fitted_right := ui_fit_insets(desired_left, desired_right, target.width)
		fitted_top, fitted_bottom := ui_fit_insets(desired_top, desired_bottom, target.height)
		left *= inset_scale
		top *= inset_scale
		right *= inset_scale
		bottom *= inset_scale
		if desired_left > 0 && fitted_left < desired_left do left *= fitted_left / desired_left
		if desired_top > 0 && fitted_top < desired_top do top *= fitted_top / desired_top
		if desired_right > 0 && fitted_right < desired_right do right *= fitted_right / desired_right
		if desired_bottom > 0 && fitted_bottom < desired_bottom do bottom *= fitted_bottom / desired_bottom
		if inset_scale < 1 && !asset.scale_insets_with_fit {
			left = max(left, fitted_left)
			top = max(top, fitted_top)
			right = max(right, fitted_right)
			bottom = max(bottom, fitted_bottom)
		}
	} else {
		source_w := max(f32(1), f32(asset.source_size[0]))
		source_h := max(f32(1), f32(asset.source_size[1]))
		left *= target.width / source_w
		right *= target.width / source_w
		top *= target.height / source_h
		bottom *= target.height / source_h
	}
	left, right = ui_fit_insets(left, right, target.width)
	top, bottom = ui_fit_insets(top, bottom, target.height)
	return {target.x + left, target.y + top, target.width - left - right, target.height - top - bottom}, true
}

ui_chrome_content_rect_from_def :: proc(
	def: UI_Chrome_Def,
	target: rl.Rectangle,
) -> (rl.Rectangle, bool) {
	asset := UI_Chrome_Asset{
		render = def.render,
		source_size = def.source_size,
		insets = def.insets,
		has_insets = def.has_insets,
		content_insets = def.content_insets,
		has_content_insets = def.has_content_insets,
		scale_insets_with_height = def.scale_insets_with_height,
		scale_insets_with_fit = def.scale_insets_with_fit,
		tile_edges = def.tile_edges,
		shrink_insets_below_height = def.shrink_insets_below_height,
		valid = true,
	}
	return ui_chrome_content_rect(&asset, target)
}

menu_background_content_rect :: proc(width, height: f32) -> rl.Rectangle {
	target := rl.Rectangle{0, 0, width, height}
	def := ui_chrome_def(.Menu_Background_Frame)
	if content, ok := ui_chrome_content_rect_from_def(def, target); ok do return content
	return target
}

ui_cover_source_rect :: proc(
	source_width, source_height, target_width, target_height: f32,
) -> rl.Rectangle {
	source := rl.Rectangle{0, 0, max(f32(0), source_width), max(f32(0), source_height)}
	if source.width <= 0 || source.height <= 0 || target_width <= 0 || target_height <= 0 do return source
	source_aspect := source.width / source.height
	target_aspect := target_width / target_height
	if source_aspect > target_aspect {
		cropped_width := source.height * target_aspect
		source.x = (source.width - cropped_width) * .5
		source.width = cropped_width
	} else if source_aspect < target_aspect {
		cropped_height := source.width / target_aspect
		source.y = (source.height - cropped_height) * .5
		source.height = cropped_height
	}
	return source
}

draw_ui_chrome :: proc(asset: ^UI_Chrome_Asset, target: rl.Rectangle, tint := rl.WHITE) -> bool {
	if asset == nil || !asset.valid || asset.tex.id == 0 || target.width <= 0 || target.height <= 0 do return false
	if asset.render == .Nine_Slice do return draw_ui_nine_slice(asset, target, tint)
	source := rl.Rectangle{0, 0, f32(asset.tex.width), f32(asset.tex.height)}
	if asset.render == .Cover {
		source = ui_cover_source_rect(source.width, source.height, target.width, target.height)
	}
	rl.DrawTexturePro(asset.tex, source, target, {}, 0, tint)
	return true
}

draw_menu_background :: proc(
	assets: ^Assets,
	title: bool,
	opacity: f32 = 1,
	frame: bool = true,
) -> rl.Rectangle {
	presentation := ui_presentation()
	target := rl.Rectangle{0, 0, presentation.width, presentation.height}
	id := title ? UI_Chrome_Id.Menu_Background_Title : UI_Chrome_Id.Menu_Background
	tint := rl.WHITE
	tint.a = u8(clamp(opacity * 255, 0, 255))
	if assets == nil || !draw_ui_chrome(ui_chrome_asset(assets, id), target, tint) {
		rl.DrawRectangleRec(target, rl.Fade(rl.Color{10, 8, 15, 255}, opacity))
	}
	if !frame do return target
	safe := menu_background_content_rect(target.width, target.height)
	frame_drawn := assets != nil && draw_ui_chrome(
		ui_chrome_asset(assets, .Menu_Background_Frame),
		target,
		tint,
	)
	if !frame_drawn {
		fallback := rl.Fade(COLOR_TITLE, opacity*.72)
		rl.DrawRectangleLinesEx({1, 1, max(f32(1), target.width-2), max(f32(1), target.height-2)}, 2, fallback)
		rl.DrawRectangleLinesEx(safe, 1, rl.Fade(fallback, .58))
	}
	return safe
}

ui_logo_frame_index :: proc(elapsed_seconds: f32, fps: f32, frame_count: int) -> int {
	if fps <= 0 || frame_count <= 0 do return 0
	return int(max(f32(0), elapsed_seconds) * fps) % frame_count
}

ui_logo_source_to_target :: proc(
	source: rl.Rectangle,
	target: rl.Rectangle,
	logo_source_size: [2]int,
) -> rl.Rectangle {
	logo_width := max(f32(1), f32(logo_source_size[0]))
	logo_height := max(f32(1), f32(logo_source_size[1]))
	return {
		target.x + source.x / logo_width * target.width,
		target.y + source.y / logo_height * target.height,
		source.width / logo_width * target.width,
		source.height / logo_height * target.height,
	}
}

@(private = "file")
draw_menu_logo_region :: proc(
	tex: rl.Texture2D,
	source: rl.Rectangle,
	target: rl.Rectangle,
	logo_source_size: [2]int,
) {
	destination := ui_logo_source_to_target(source, target, logo_source_size)
	rl.DrawTexturePro(tex, source, destination, {}, 0, rl.WHITE)
}

draw_menu_logo :: proc(assets: ^Assets, target: rl.Rectangle, elapsed_seconds: f32 = 0) -> bool {
	if assets == nil do return false
	logo := ui_chrome_asset(assets, .Menu_Logo_Title)
	if logo == nil || !logo.valid || logo.tex.id == 0 do return false
	animation := &assets.ui_logo_animation
	if !animation.loaded || animation.tex.id == 0 || animation.frame_count <= 0 {
		return draw_ui_chrome(logo, target)
	}

	cut := animation.logo_source_rect
	logo_width := f32(logo.source_size[0])
	logo_height := f32(logo.source_size[1])
	cut_x := f32(cut[0])
	cut_y := f32(cut[1])
	cut_width := f32(cut[2])
	cut_height := f32(cut[3])
	regions := [4]rl.Rectangle{
		{0, 0, cut_x, logo_height},
		{cut_x + cut_width, 0, logo_width - cut_x - cut_width, logo_height},
		{cut_x, 0, cut_width, cut_y},
		{cut_x, cut_y + cut_height, cut_width, logo_height - cut_y - cut_height},
	}
	for source in regions do draw_menu_logo_region(logo.tex, source, target, logo.source_size)

	frame_width := f32(animation.frame_size[0])
	frame_height := f32(animation.frame_size[1])
	frame_index := ui_logo_frame_index(elapsed_seconds, animation.fps, animation.frame_count)
	frame_source := rl.Rectangle{f32(frame_index) * frame_width, 0, frame_width, frame_height}
	frame_in_logo := rl.Rectangle{
		cut_x + (cut_width - frame_width) * .5,
		cut_y + (cut_height - frame_height) * .5,
		frame_width,
		frame_height,
	}
	frame_target := ui_logo_source_to_target(frame_in_logo, target, logo.source_size)
	rl.DrawTexturePro(animation.tex, frame_source, frame_target, {}, 0, rl.WHITE)
	return true
}

draw_menu_panel_chrome :: proc(assets: ^Assets, target: rl.Rectangle) -> rl.Rectangle {
	id := target.width * 10 <= target.height * 17 ? UI_Chrome_Id.Menu_Panel_Compact : UI_Chrome_Id.Menu_Panel
	if assets != nil {
		asset := ui_chrome_asset(assets, id)
		if draw_ui_chrome(asset, target) {
			if content, ok := ui_chrome_content_rect(asset, target); ok do return content
		}
	}
	rl.DrawRectangleRec(target, rl.Fade(rl.Color{13, 11, 19, 255}, .98))
	rl.DrawRectangleLinesEx(target, 2, COLOR_TITLE)
	return {target.x + 24, target.y + 22, max(f32(1), target.width - 48), max(f32(1), target.height - 44)}
}

menu_row_content_rect :: proc(target: rl.Rectangle) -> (rl.Rectangle, bool) {
	plain, plain_ok := ui_chrome_content_rect_from_def(ui_chrome_def(.Menu_Row), target)
	selected, selected_ok := ui_chrome_content_rect_from_def(ui_chrome_def(.Menu_Row_Selected), target)
	if !plain_ok do return selected, selected_ok
	if !selected_ok do return plain, true

	// Use one rail for both states so labels never step sideways, while reserving
	// every endcap used by either state. In particular, selected rows have a
	// larger right arrow than plain rows.
	left := max(plain.x, selected.x)
	top := max(plain.y, selected.y)
	right := min(plain.x+plain.width, selected.x+selected.width)
	bottom := min(plain.y+plain.height, selected.y+selected.height)
	if right <= left || bottom <= top do return target, false
	return {left, top, right-left, bottom-top}, true
}

draw_menu_row_chrome :: proc(assets: ^Assets, target: rl.Rectangle, selected: bool) -> rl.Rectangle {
	if assets != nil {
		id := selected ? UI_Chrome_Id.Menu_Row_Selected : UI_Chrome_Id.Menu_Row
		asset := ui_chrome_asset(assets, id)
		if draw_ui_chrome(asset, target) {
			if content, ok := menu_row_content_rect(target); ok do return content
		}
	}
	rl.DrawRectangleRec(target, selected ? COLOR_ROW_SELECTED : COLOR_ROW)
	outline := COLOR_TITLE
	if !selected do outline = rl.Fade(COLOR_TEXT_DIM, .55)
	rl.DrawRectangleLinesEx(target, 1, outline)
	return {target.x + 14, target.y + 6, max(f32(1), target.width - 28), max(f32(1), target.height - 12)}
}

draw_ui_glyph :: proc(glyph: UI_Glyph_Asset, target: rl.Rectangle, tint := rl.WHITE) -> bool {
	if !glyph.valid || glyph.tex.id == 0 || target.width <= 0 || target.height <= 0 do return false
	rl.DrawTexturePro(glyph.tex, glyph.source, target, {}, 0, tint)
	return true
}

title_logo_rect :: proc(width, height: f32) -> rl.Rectangle {
	layout := menu_background_content_rect(width, height)
	logo_width := max(f32(1), min(f32(560), layout.width-80))
	logo_height := logo_width * 122 / 640
	relic_center_x := f32(UI_LOGO_DIAMOND_SOURCE_RECT[0]) + f32(UI_LOGO_DIAMOND_SOURCE_RECT[2]) * .5
	logo_x := layout.x + layout.width*.5 - relic_center_x / 640 * logo_width
	logo_y := max(layout.y+18, height*.17)
	return {logo_x, logo_y, logo_width, logo_height}
}

draw_title_screen :: proc(app: ^App, assets: ^Assets) {
	presentation := ui_begin_presentation()
	defer ui_end_presentation()
	layout := draw_menu_background(assets, true)
	center_x := layout.x + layout.width*.5

	logo := title_logo_rect(presentation.width, presentation.height)
	if !draw_menu_logo(assets, logo, f32(app.tick) * SIM_DT) {
		title: cstring = "ARCH ROGUE"
		ui_draw_text(title, i32(center_x)-ui_measure_text(title,72)/2, i32(logo.y), 72, COLOR_TITLE)
	}
	sub: cstring = "a grim descent into the cursed depths"
	ui_draw_text(sub, i32(center_x)-ui_measure_text(sub,20)/2, i32(logo.y+logo.height+16), 20, COLOR_TEXT_DIM)

	labels := [len(Title_Action)]cstring{"Resume", "New Run", "Chronicle", "Options", "Quit"}
	for label, index in labels {
		rect := title_row_rect_in_bounds(layout, index)
		enabled := title_action_enabled(app, Title_Action(index))
		selected := ui_navigation_selected(app,app.title_index == index)
		content := draw_menu_row_chrome(assets, rect, selected && enabled)
		w := ui_measure_text(label, 22)
		color := enabled ? (selected ? COLOR_TITLE : COLOR_TEXT) : COLOR_TEXT_DIM
		ui_draw_text(label, i32(content.x+(content.width-f32(w))*.5), i32(rect.y+11), 22, color)
	}
	if app.active_run_damaged {
		warning: cstring = "Active descent is damaged - recovery available"
		w := ui_measure_text(warning,14)
		ui_draw_text(warning,i32(center_x)-w/2,i32(layout.y+layout.height-30),14,rl.Color{205,106,92,255})
	}
	ui_draw_text("Arch Rogue "+VERSION+"  -  Odin + raylib rewrite", i32(layout.x)+8, i32(layout.y+layout.height)-24, 14, COLOR_TEXT_DIM)
}

title_prompt_rect :: proc() -> rl.Rectangle {
	return title_row_rect(0)
}

title_row_rect_in_bounds :: proc(bounds: rl.Rectangle, index: int) -> rl.Rectangle {
	center_offset := clamp(bounds.height*.015, f32(4), f32(12))
	pitch:f32=50
	row_height:f32=44
	desired_start:=bounds.y+bounds.height*.5+center_offset
	latest_start:=bounds.y+bounds.height-row_height-f32(len(Title_Action)-1)*pitch
	start:=max(bounds.y,min(desired_start,latest_start))
	return {
		bounds.x+bounds.width*.5-150,
		start+f32(index)*pitch,
		300,
		row_height,
	}
}

title_row_rect :: proc(index: int) -> rl.Rectangle {
	presentation := ui_presentation()
	bounds := menu_background_content_rect(presentation.width, presentation.height)
	return title_row_rect_in_bounds(bounds, index)
}

title_row_at :: proc(point: rl.Vector2) -> (index: int, found: bool) {
	design_point := ui_screen_to_design(point)
	presentation := ui_presentation()
	bounds := menu_background_content_rect(presentation.width, presentation.height)
	for i in 0 ..< len(Title_Action) {
		if rl.CheckCollisionPointRec(design_point, title_row_rect_in_bounds(bounds,i)) do return i, true
	}
	return 0, false
}

Select_Slot :: struct {
	archetype:  Archetype_Id,
	offset:     int,
	visible:    bool,
	feet:       rl.Vector2,
	sprite_size:f32,
	hit_rect:   rl.Rectangle,
}

select_carousel_slots :: proc(app: ^App) -> [Archetype_Id]Select_Slot {
	slots: [Archetype_Id]Select_Slot
	if app == nil do return slots
	presentation := ui_presentation()
	layout := menu_background_content_rect(presentation.width, presentation.height)
	wide := presentation.responsive_width >= UI_CAROUSEL_WIDE
	max_offset := wide ? 2 : 1
	spread := wide ? min(f32(230), (layout.width-180)/4) : min(f32(270), (layout.width-160)/2)
	spread = max(f32(120), spread)
	stage_y := clamp(layout.y+layout.height*.48, layout.y+230, layout.y+268)
	size_scale := clamp(layout.height/650, f32(.86), f32(1))
	center_x := layout.x + layout.width*.5
	count := len(Archetype_Id)
	for archetype in Archetype_Id {
		offset := int(archetype) - app.select_index
		if offset > count/2 do offset -= count
		if offset < -count/2 do offset += count
		distance := abs(offset)
		base_size: f32 = distance == 0 ? 210 : distance == 1 ? 158 : 118
		size := base_size * size_scale
		feet := rl.Vector2{center_x+f32(offset)*spread, stage_y-f32(distance*18)}
		hit_width := max(size*.72, spread*.62)
		slots[archetype] = {
			archetype = archetype,
			offset = offset,
			visible = distance <= max_offset,
			feet = feet,
			sprite_size = size,
			hit_rect = {feet.x-hit_width*.5, feet.y-size*.92, hit_width, size+48},
		}
	}
	return slots
}

select_slot_rect :: proc(app: ^App, index: int) -> rl.Rectangle {
	if app == nil || index < 0 || index >= len(Archetype_Id) do return {}
	return select_carousel_slots(app)[Archetype_Id(index)].hit_rect
}

// Public hit test consumes exactly the same slot geometry as drawing.
select_slot_at :: proc(app: ^App, point: rl.Vector2) -> (index: int, found: bool) {
	if app == nil do return 0, false
	design_point := ui_screen_to_design(point)
	slots := select_carousel_slots(app)
	for distance in 0 ..= 2 {
		for archetype in Archetype_Id {
			slot := slots[archetype]
			if slot.visible && abs(slot.offset) == distance && rl.CheckCollisionPointRec(design_point, slot.hit_rect) {
				return int(archetype), true
			}
		}
	}
	return 0, false
}

// Compatibility name for input code; MX.1 adds the App argument.
select_row_at :: proc(app: ^App, point: rl.Vector2) -> (index: int, found: bool) {
	return select_slot_at(app, point)
}

@(private = "file")
draw_select_actor :: proc(app: ^App, assets: ^Assets, slot: Select_Slot) {
	distance := abs(slot.offset)
	selected := distance == 0
	pedestal_w := slot.sprite_size * (selected ? .62 : .52)
	if selected {
		rl.DrawEllipse(i32(slot.feet.x), i32(slot.feet.y+2), pedestal_w*.72, 15, rl.Fade(COLOR_TITLE, .18))
	}
	rl.DrawEllipse(i32(slot.feet.x), i32(slot.feet.y), pedestal_w*.5, selected ? 10 : 7, rl.Fade(rl.BLACK, selected ? .70 : .50))

	sprites := &assets.archetypes[slot.archetype]
	clip := sprites.clips[.Preview_Idle]
	if !sprites.loaded || !clip.valid || clip.frames <= 0 || sprites.cell <= 0 {
		rl.DrawCircleV({slot.feet.x, slot.feet.y-slot.sprite_size*.42}, selected ? 28 : 20, selected ? COLOR_TITLE : COLOR_TEXT_DIM)
		return
	}
	frame := int(f32(app.tick)*SIM_DT*clip.fps) % clip.frames
	cell := f32(sprites.cell)
	source := rl.Rectangle{f32(frame)*cell, 0, cell, cell} // south idle
	destination := rl.Rectangle{
		slot.feet.x-sprites.anchor.x*slot.sprite_size,
		slot.feet.y-sprites.anchor.y*slot.sprite_size,
		slot.sprite_size,
		slot.sprite_size,
	}
	tint := rl.WHITE
	if distance == 1 do tint = rl.Color{148, 148, 158, 225}
	if distance >= 2 do tint = rl.Color{92, 92, 104, 205}
	rl.DrawTexturePro(clip.tex, source, destination, {}, 0, tint)
}

draw_select_screen :: proc(app: ^App, assets: ^Assets) {
	_ = ui_begin_presentation()
	defer ui_end_presentation()
	layout := draw_menu_background(assets, false)
	center_x := layout.x + layout.width*.5

	heading: cstring = "CHOOSE YOUR ARCHETYPE"
	heading_y := layout.y + 4
	ui_draw_text(heading, i32(center_x)-ui_measure_text(heading,30)/2, i32(heading_y), 30, COLOR_TITLE)
	difficulty := fmt.ctprintf("Difficulty: %s", difficulty_profile(app.options.difficulty).name)
	ui_draw_text(difficulty, i32(center_x)-ui_measure_text(difficulty,15)/2, i32(heading_y+40), 15, COLOR_TEXT_DIM)

	slots := select_carousel_slots(app)
	for distance in ([3]int{2, 1, 0}) {
		for archetype in Archetype_Id {
			slot := slots[archetype]
			if !slot.visible || abs(slot.offset) != distance do continue
			draw_select_actor(app, assets, slot)
			if distance > 0 {
				name := fmt.ctprintf("%s", ARCHETYPES[archetype].name)
				color := COLOR_TEXT_DIM
				if distance != 1 do color = rl.Fade(COLOR_TEXT_DIM, .58)
				ui_draw_text(name, i32(slot.feet.x)-ui_measure_text(name,15)/2, i32(slot.feet.y+14), 15, color)
			}
		}
	}

	selected := Archetype_Id(app.select_index)
	def := ARCHETYPES[selected]
	selected_slot := slots[selected]
	name := fmt.ctprintf("%s", def.name)
	ui_draw_text(name, i32(center_x)-ui_measure_text(name,30)/2, i32(selected_slot.feet.y+28), 30, COLOR_TITLE)
	rl.DrawRectangle(i32(center_x-64), i32(selected_slot.feet.y+63), 128, 2, COLOR_TITLE)

	detail_y := selected_slot.feet.y+78
	detail_h := clamp(layout.y+layout.height-detail_y-42, f32(112), f32(214))
	detail_w := min(f32(780), layout.width-40)
	detail := rl.Rectangle{center_x-detail_w*.5, detail_y, detail_w, detail_h}
	content := draw_menu_panel_chrome(assets, detail)
	blurb := fmt.ctprintf("%s", def.blurb)
	blurb_size: i32 = 17
	for blurb_size > 10 && ui_measure_text(blurb, blurb_size) > i32(content.width-24) do blurb_size -= 1
	ui_draw_text(blurb, i32(content.x+(content.width-f32(ui_measure_text(blurb,blurb_size)))*.5), i32(content.y+10), blurb_size, COLOR_TEXT)
	stats := fmt.ctprintf("HP %v     Mana %v     Stamina %v     Speed %.2f", def.max_hp, def.max_mana, def.max_stamina, def.speed)
	ui_draw_text(stats, i32(content.x+(content.width-f32(ui_measure_text(stats,16)))*.5), i32(content.y+48), 16, COLOR_TITLE)

	hint: cstring = "Arrows: choose   1-5: begin   Enter: confirm   Backspace: return   F11: fullscreen"
	ui_draw_text(hint, i32(center_x)-ui_measure_text(hint,14)/2, i32(layout.y+layout.height)-27, 14, COLOR_TEXT_DIM)
}

// --- M9 shell --------------------------------------------------------------

menu_panel :: proc(width, height: i32) -> rl.Rectangle {
	return {ui_design_width()*.5-f32(width)*.5, ui_design_height()*.5-f32(height)*.5, f32(width), f32(height)}
}

menu_panel_in_bounds :: proc(bounds: rl.Rectangle, width, height: f32) -> rl.Rectangle {
	panel_width := max(f32(1), min(width, bounds.width))
	panel_height := max(f32(1), min(height, bounds.height))
	return {
		bounds.x + (bounds.width-panel_width)*.5,
		bounds.y + (bounds.height-panel_height)*.5,
		panel_width,
		panel_height,
	}
}

pause_row_rect :: proc(index: int) -> rl.Rectangle {
	panel := menu_panel(420,360)
	return {panel.x+34,panel.y+82+f32(index*58),panel.width-68,46}
}

pause_row_at :: proc(point: rl.Vector2) -> (int, bool) {
	design_point := ui_screen_to_design(point)
	for i in 0..<4 {
		if rl.CheckCollisionPointRec(design_point,pause_row_rect(i)) do return i,true
	}
	return 0,false
}

draw_pause_panel :: proc(app: ^App, assets: ^Assets) {
	presentation := ui_begin_presentation()
	defer ui_end_presentation()
	panel := menu_panel(420,360)
	rl.DrawRectangleRec({0,0,presentation.width,presentation.height},rl.Fade(rl.BLACK,.62))
	draw_menu_panel_chrome(assets,panel)
	ui_draw_text("DESCENT PAUSED",i32(panel.x+32),i32(panel.y+24),28,COLOR_TITLE)
	labels := [len(Pause_Action)]cstring{"Resume","Options","Save & Return","Save & Quit"}
	for label,i in labels {
		rect := pause_row_rect(i)
		selected := ui_navigation_selected(app,i==app.pause_index)
		content := draw_menu_row_chrome(assets,rect,selected)
		ui_draw_text(label,i32(content.x),i32(rect.y+12),20,selected?COLOR_TITLE:COLOR_TEXT)
	}
}

Chronicle_UI_Layout :: struct {
	outer:         rl.Rectangle,
	content:       rl.Rectangle,
	summary:       rl.Rectangle,
	filters:       rl.Rectangle,
	body:          rl.Rectangle,
	timeline:      rl.Rectangle,
	detail:        rl.Rectangle,
	compact:       bool,
	card_height:   f32,
	visible_cards: int,
	heading_y:     f32,
	footer_y:      f32,
}

chronicle_ui_layout :: proc(width, height, responsive_width: f32) -> Chronicle_UI_Layout {
	// The Chronicle owns its screen chrome. Its PixelLab ledger frame reaches the
	// viewport edges; all readable and interactive content stays inside its rails.
	outer := rl.Rectangle{0,0,width,height}
	frame_clearance:=clamp(min(width,height)*.045,f32(22),f32(52))
	content:=rl.Rectangle{frame_clearance,frame_clearance,width-frame_clearance*2,height-frame_clearance*2}
	compact := responsive_width < 900
	// At 640x480 the UI is rendered through a 1280x960 design viewport, so this
	// clearance remains useful physical breathing room around the ornate border.
	heading_y := content.y+54
	summary := rl.Rectangle{content.x+24,content.y+90,content.width-48,54}
	filters := rl.Rectangle{content.x+24,summary.y+summary.height+8,content.width-48,40}
	content_y := filters.y+filters.height+10
	footer_y := content.y+content.height-36
	content_h := max(f32(1),footer_y-20-content_y)
	card_height:=compact?f32(52):f32(46)
	layout := Chronicle_UI_Layout{
		outer=outer,content=content,summary=summary,filters=filters,compact=compact,
		card_height=card_height,heading_y=heading_y,footer_y=footer_y,
	}
	if compact {
		layout.timeline={content.x+24,content_y,content.width-48,content_h*.43}
		layout.detail={content.x+24,layout.timeline.y+layout.timeline.height+10,content.width-48,content_h-layout.timeline.height-10}
	} else {
		left_width:=clamp(content.width*.43,f32(390),f32(560))
		layout.timeline={content.x+24,content_y,left_width,content_h}
		layout.detail={layout.timeline.x+layout.timeline.width+14,content_y,content.x+content.width-24-(layout.timeline.x+layout.timeline.width+14),content_h}
	}
	layout.body={
		layout.timeline.x,
		layout.timeline.y,
		layout.detail.x+layout.detail.width-layout.timeline.x,
		layout.detail.y+layout.detail.height-layout.timeline.y,
	}
	layout.visible_cards=max(1,int((layout.timeline.height-CHRONICLE_CARD_RAIL_INSET*2)/(layout.card_height+CHRONICLE_CARD_GAP)))
	return layout
}

CHRONICLE_CARD_SIDE_INSET :: f32(36)
CHRONICLE_CARD_RAIL_INSET :: f32(32)
CHRONICLE_CARD_GAP        :: f32(4)

chronicle_card_rect_for_count :: proc(
	layout: Chronicle_UI_Layout,
	visible_index, visible_count: int,
) -> rl.Rectangle {
	count:=clamp(visible_count,1,layout.visible_cards)
	stack_height:=f32(count)*layout.card_height+f32(max(0,count-1))*CHRONICLE_CARD_GAP
	stack_y:=layout.timeline.y+max(CHRONICLE_CARD_RAIL_INSET,(layout.timeline.height-stack_height)*.5)
	return {
		layout.timeline.x+CHRONICLE_CARD_SIDE_INSET,
		stack_y+f32(visible_index)*(layout.card_height+CHRONICLE_CARD_GAP),
		layout.timeline.width-CHRONICLE_CARD_SIDE_INSET*2,
		layout.card_height,
	}
}

chronicle_card_rect :: proc(layout: Chronicle_UI_Layout, visible_index: int) -> rl.Rectangle {
	return chronicle_card_rect_for_count(layout,visible_index,layout.visible_cards)
}

CHRONICLE_DETAIL_PAD_X :: f32(64)
CHRONICLE_DETAIL_PAD_Y :: f32(46)

chronicle_detail_content_rect :: proc(rect:rl.Rectangle) -> rl.Rectangle {
	return {
		rect.x+CHRONICLE_DETAIL_PAD_X,
		rect.y+CHRONICLE_DETAIL_PAD_Y,
		max(f32(1),rect.width-CHRONICLE_DETAIL_PAD_X*2),
		max(f32(1),rect.height-CHRONICLE_DETAIL_PAD_Y*2),
	}
}

chronicle_card_at :: proc(app: ^App, point: rl.Vector2) -> (int,bool) {
	if app==nil do return 0,false
	presentation:=ui_presentation()
	layout:=chronicle_ui_layout(presentation.width,presentation.height,presentation.responsive_width)
	design:=ui_screen_to_design(point)
	count:=chronicle_filtered_count(&app.profile,&app.chronicle)
	visible_count:=min(layout.visible_cards,max(0,count-app.chronicle.scroll))
	for visible in 0..<visible_count {
		if rl.CheckCollisionPointRec(design,chronicle_card_rect_for_count(layout,visible,visible_count)) {
			return app.chronicle.scroll+visible,true
		}
	}
	return 0,false
}

@(private = "file")
draw_chronicle_portrait :: proc(app:^App,assets:^Assets,archetype:Archetype_Id,rect:rl.Rectangle) {
	rl.DrawCircleV({rect.x+rect.width*.5,rect.y+rect.height*.5},min(rect.width,rect.height)*.48,rl.Color{21,18,28,255})
	rl.DrawCircleLinesV({rect.x+rect.width*.5,rect.y+rect.height*.5},min(rect.width,rect.height)*.48,COLOR_TITLE)
	sprites:=&assets.archetypes[archetype]
	clip:=sprites.clips[.Preview_Idle]
	if sprites.loaded&&clip.valid&&clip.frames>0&&sprites.cell>0 {
		cell:=f32(sprites.cell);source:=rl.Rectangle{0,0,cell,cell}
		size:=min(rect.width,rect.height)*1.16
		destination:=rl.Rectangle{rect.x+rect.width*.5-sprites.anchor.x*size,rect.y+rect.height*.88-sprites.anchor.y*size,size,size}
		// Scissor coordinates are physical pixels even while drawing through the
		// fitted design-space camera. Without this conversion compact captures clip
		// the portrait against an unrelated part of the screen.
		presentation:=ui_presentation()
		rl.BeginScissorMode(
			i32(rect.x*presentation.scale),i32(rect.y*presentation.scale),
			max(1,i32(rect.width*presentation.scale)),max(1,i32(rect.height*presentation.scale)),
		)
		rl.DrawTexturePro(clip.tex,source,destination,{},0,rl.WHITE)
		rl.EndScissorMode()
		return
	}
	name:=fmt.ctprintf("%c",ARCHETYPES[archetype].name[0])
	ui_draw_text(name,i32(rect.x+rect.width*.5)-ui_measure_text(name,22)/2,i32(rect.y+rect.height*.5-11),22,COLOR_TITLE)
}

@(private = "file")
draw_chronicle_filter :: proc(assets:^Assets,label:cstring,rect:rl.Rectangle,focused:bool) {
	tint:=focused?rl.Color{255,228,202,255}:rl.WHITE
	if !draw_ui_chrome(ui_chrome_asset(assets,.Chronicle_Filter_Panel),rect,tint) {
		color:=focused?rl.Color{82,58,48,255}:rl.Color{33,28,40,245}
		rl.DrawRectangleRounded(rect,.22,5,color)
		outline := COLOR_TITLE
		if !focused do outline = rl.Fade(COLOR_TEXT_DIM,.5)
		rl.DrawRectangleRoundedLinesEx(rect,.22,5,focused?2:1,outline)
	}
	if focused do rl.DrawRectangleRoundedLinesEx(rect,.18,5,1,rl.Fade(COLOR_TITLE,.75))
	font_size:=i32(18)
	text_width:=ui_measure_text(label,font_size)
	ui_draw_text(label,i32(rect.x+(rect.width-f32(text_width))*.5),i32(rect.y+(rect.height-f32(font_size))*.5),font_size,focused?COLOR_TITLE:COLOR_TEXT)
}

@(private = "file")
draw_chronicle_content_panel :: proc(assets:^Assets,layout:Chronicle_UI_Layout) {
	if !draw_ui_chrome(ui_chrome_asset(assets,.Chronicle_Content_Panel),layout.body) {
		rl.DrawRectangleRounded(layout.body,.035,8,rl.Color{18,16,23,238})
		rl.DrawRectangleRoundedLinesEx(layout.body,.035,8,1,rl.Fade(COLOR_TEXT_DIM,.4))
	}
	divider_color:=rl.Fade(COLOR_TITLE,.28)
	if layout.compact {
		divider_y:=(layout.timeline.y+layout.timeline.height+layout.detail.y)*.5
		rl.DrawLineEx({layout.body.x+26,divider_y},{layout.body.x+layout.body.width-26,divider_y},1,divider_color)
	} else {
		divider_x:=(layout.timeline.x+layout.timeline.width+layout.detail.x)*.5
		rl.DrawLineEx({divider_x,layout.body.y+24},{divider_x,layout.body.y+layout.body.height-24},1,divider_color)
	}
}

@(private = "file")
draw_chronicle_empty :: proc(layout:Chronicle_UI_Layout,assets:^Assets) {
	panel:=layout.timeline
	center_factor:=layout.compact?f32(.40):f32(.46)
	center:=rl.Vector2{panel.x+panel.width*.5,panel.y+panel.height*center_factor}
	// PixelLab-authored unwritten ledger; geometry fallback keeps missing optional
	// art non-fatal without turning the empty state into a blank list.
	size:=layout.compact?f32(124):f32(208)
	illustration:=rl.Rectangle{center.x-size*.5,center.y-size*.44,size,size}
	if !draw_ui_chrome(ui_chrome_asset(assets,.Chronicle_Unwritten_Ledger),illustration) {
		fallback:=rl.Rectangle{center.x-size*.35,center.y-size*.24,size*.7,size*.5}
		rl.DrawRectangleRounded(fallback,.08,7,rl.Color{48,36,38,255})
		rl.DrawRectangleRoundedLinesEx(fallback,.08,7,3,COLOR_TITLE)
		rl.DrawLineEx({center.x,fallback.y+4},{center.x,fallback.y+fallback.height-4},2,rl.Fade(COLOR_TITLE,.55))
	}
	text:cstring="THE LEDGER WAITS"
	text_y:=center.y+(layout.compact?f32(68):f32(112))
	text_size:=layout.compact?i32(24):i32(22)
	ui_draw_text(text,i32(center.x)-ui_measure_text(text,text_size)/2,i32(text_y),text_size,COLOR_TITLE)
	sub:cstring="No descent has yet reached its final line."
	sub_size:=layout.compact?i32(17):i32(15)
	ui_draw_text(sub,i32(center.x)-ui_measure_text(sub,sub_size)/2,i32(text_y+30),sub_size,COLOR_TEXT_DIM)
}

@(private="file")
draw_chronicle_outcome_seal :: proc(assets:^Assets,outcome:Chronicle_Outcome,target:rl.Rectangle) {
	asset:=ui_chrome_asset(assets,.Chronicle_Outcome_Seals)
	if asset==nil||!asset.valid||asset.tex.id==0 do return
	source:=rl.Rectangle{outcome==.Victory?f32(0):f32(128),0,128,128}
	rl.DrawTexturePro(asset.tex,source,target,{},0,rl.WHITE)
}

@(private = "file")
draw_chronicle_detail :: proc(record:^Chronicle_Record,rect:rl.Rectangle,assets:^Assets,compact:bool) {
	content:=chronicle_detail_content_rect(rect)
	content_bottom:=content.y+content.height
	if record==nil {
		text:cstring="Select a descent to open its memorial."
		font_size:=compact?i32(20):i32(18)
		text_width:=ui_measure_text(text,font_size)
		ui_draw_text(
			text,
			i32(content.x+(content.width-f32(text_width))*.5),
			i32(content.y+(content.height-f32(font_size))*.5),
			font_size,
			COLOR_TEXT_DIM,
		)
		return
	}

	outcome:=record.outcome==.Victory?"VICTORIOUS":"FALLEN"
	outcome_color:=record.outcome==.Victory?COLOR_TITLE:rl.Color{196,72,68,255}
	seal_size:=compact?f32(52):f32(58)
	draw_chronicle_outcome_seal(assets,record.outcome,{content.x+content.width-seal_size,content.y,seal_size,seal_size})
	ui_draw_text(fmt.ctprintf("%s DESCENT",outcome),i32(content.x),i32(content.y),compact?28:27,outcome_color)
	ui_draw_text(fmt.ctprintf("%s  /  %s",ARCHETYPES[record.archetype].name,difficulty_profile(record.difficulty).name),i32(content.x),i32(content.y+35),compact?18:16,COLOR_TEXT)
	y:=content.y+68

	if record.outcome==.Fallen {
		font_size:=compact?i32(19):i32(17)
		if y+f32(font_size)<=content_bottom {
			cause:=persistence_cause_label(record.cause_of_death)
			ui_draw_text(fmt.ctprintf("Cause: %s",cause),i32(content.x),i32(y),font_size,rl.Color{226,126,108,255})
			y+=compact?24:26
		}
	} else if record.story_ending_id!="" {
		font_size:=compact?i32(19):i32(17)
		if y+f32(font_size)<=content_bottom {
			ui_draw_text(fmt.ctprintf("Ending: %s",persistence_ending_label(record.story_ending_id)),i32(content.x),i32(y),font_size,COLOR_TITLE)
			y+=compact?24:26
		}
	}

	if y+1<=content_bottom {
		rl.DrawLineEx({content.x,y},{content.x+content.width,y},1,rl.Fade(COLOR_TITLE,.4))
		y+=compact?10:12
	}
	stats_heading_size:=compact?i32(18):i32(16)
	if y+f32(stats_heading_size)<=content_bottom {
		ui_draw_text("FINAL STATISTICS",i32(content.x),i32(y),stats_heading_size,COLOR_TITLE)
		y+=compact?22:22
	}
	stats_size:=compact?i32(19):i32(16)
	if y+f32(stats_size)<=content_bottom {
		ui_draw_text(fmt.ctprintf("Depth %d    Level %d    Kills %d",record.deepest_floor,record.final_level,record.kills),i32(content.x),i32(y),stats_size,COLOR_TEXT)
		y+=compact?24:23
	}
	minor_size:=compact?i32(17):i32(15)
	if y+f32(minor_size)<=content_bottom {
		ui_draw_text(fmt.ctprintf("Traps %d    Shrines %d    Secrets %d",record.traps_triggered,record.shrines_used,record.secrets_opened),i32(content.x),i32(y),minor_size,COLOR_TEXT_DIM)
		y+=compact?22:22
	}
	if y+f32(minor_size)<=content_bottom {
		ui_draw_text(fmt.ctprintf("Bars %d/%d    Challenges %d",record.bars_toasted,record.bars_visited,record.challenge_rooms_cleared),i32(content.x),i32(y),minor_size,COLOR_TEXT_DIM)
		y+=compact?24:26
	}

	if compact {
		heading_size:=i32(17)
		line_size:=i32(16)
		if (record.story_relic_id!=""||record.notable_count>0)&&y+f32(heading_size+line_size+5)<=content_bottom {
			ui_draw_text("STORY & NOTABLE LOOT",i32(content.x),i32(y),heading_size,COLOR_TITLE)
			y+=22
			if record.story_relic_id!=""&&y+f32(line_size)<=content_bottom {
				ui_draw_text(fmt.ctprintf("Relic: %s",persistence_relic_label(record.story_relic_id)),i32(content.x),i32(y),line_size,COLOR_TEXT)
				y+=21
			}
			for i in 0..<min(record.notable_count,2) {
				if y+f32(line_size)>content_bottom do break
				name:=record.notable_items[i].display_name!=""?record.notable_items[i].display_name:"Unknown relic"
				ui_draw_text(fmt.ctprintf("- %s",name),i32(content.x+6),i32(y),line_size,COLOR_TEXT)
				y+=20
			}
		}
		return
	}

	heading_size:=i32(15)
	line_size:=i32(14)
	if record.story_relic_id!=""&&y+f32(heading_size+line_size+7)<=content_bottom {
		ui_draw_text("STORY & DISCOVERIES",i32(content.x),i32(y),heading_size,COLOR_TITLE)
		y+=22
		ui_draw_text(fmt.ctprintf("Relic: %s",persistence_relic_label(record.story_relic_id)),i32(content.x),i32(y),line_size,COLOR_TEXT)
		y+=21
	}
	if record.notable_count>0&&y+f32(heading_size+line_size+7)<=content_bottom {
		ui_draw_text("NOTABLE LOOT",i32(content.x),i32(y),heading_size,COLOR_TITLE)
		y+=22
		for i in 0..<min(record.notable_count,4) {
			if y+f32(line_size)>content_bottom do break
			name:=record.notable_items[i].display_name!=""?record.notable_items[i].display_name:"Unknown relic"
			ui_draw_text(fmt.ctprintf("- %s",name),i32(content.x+6),i32(y),line_size,COLOR_TEXT)
			y+=19
		}
	}
}

draw_chronicle_screen :: proc(app:^App,assets:^Assets) {
	presentation:=ui_begin_presentation();defer ui_end_presentation()
	_ = draw_menu_background(assets,false,frame=false)
	layout:=chronicle_ui_layout(presentation.width,presentation.height,presentation.responsive_width)
	if !draw_ui_chrome(ui_chrome_asset(assets,.Chronicle_Ledger_Frame),layout.outer) do draw_menu_panel_chrome(assets,layout.outer)
	heading:cstring="CHRONICLE OF DESCENTS"
	heading_size:=layout.compact?i32(32):i32(30)
	heading_width:=ui_measure_text(heading,heading_size)
	ui_draw_text(heading,i32(layout.content.x+(layout.content.width-f32(heading_width))*.5),i32(layout.heading_y),heading_size,COLOR_TITLE)
	rl.DrawRectangleRounded(layout.summary,.08,6,rl.Color{24,20,29,245})
	summary:=fmt.ctprintf("Descents  %d     Victories  %d     Best depth  %d     Total kills  %d     Endings  %d",
		app.profile.lifetime_descents,app.profile.lifetime_victories,app.profile.best_depth,
		app.profile.lifetime_kills,app.profile.discovered_ending_count)
	summary_size:=layout.compact?i32(19):i32(17)
	summary_width:=ui_measure_text(summary,summary_size)
	ui_draw_text(summary,i32(layout.summary.x+(layout.summary.width-f32(summary_width))*.5),i32(layout.summary.y+(layout.summary.height-f32(summary_size))*.5),summary_size,COLOR_TEXT)
	chip_w:=min(f32(190),(layout.filters.width-24)/3)
	outcome_labels:=[len(Chronicle_Outcome_Filter)]cstring{"All descents","Victories","Fallen"}
	arch:=app.chronicle.archetype_filter<0?"All archetypes":ARCHETYPES[Archetype_Id(app.chronicle.archetype_filter)].name
	diff:=app.chronicle.difficulty_filter<0?"All difficulties":difficulty_profile(Difficulty_Id(app.chronicle.difficulty_filter)).name
	draw_chronicle_filter(assets,outcome_labels[app.chronicle.outcome],{layout.filters.x,layout.filters.y,chip_w,38},app.chronicle.focus==.Outcome)
	draw_chronicle_filter(assets,fmt.ctprintf("%s",arch),{layout.filters.x+chip_w+12,layout.filters.y,chip_w,38},app.chronicle.focus==.Archetype)
	draw_chronicle_filter(assets,fmt.ctprintf("%s",diff),{layout.filters.x+(chip_w+12)*2,layout.filters.y,chip_w,38},app.chronicle.focus==.Difficulty)
	draw_chronicle_content_panel(assets,layout)
	count:=chronicle_filtered_count(&app.profile,&app.chronicle)
	if count==0 {
		draw_chronicle_empty(layout,assets)
	} else {
		visible_count:=min(layout.visible_cards,max(0,count-app.chronicle.scroll))
		for visible in 0..<visible_count {
			index:=app.chronicle.scroll+visible
			record:=chronicle_record_at(&app.profile,&app.chronicle,index)
			if record==nil do continue
			rect:=chronicle_card_rect_for_count(layout,visible,visible_count)
			selected:=ui_navigation_selected(app,index==app.chronicle.selected)
			rl.DrawRectangleRounded(rect,.08,6,selected?rl.Color{66,47,49,255}:rl.Color{25,22,31,245})
			outline := COLOR_TITLE
			if !selected do outline = rl.Fade(COLOR_TEXT_DIM,.4)
			rl.DrawRectangleRoundedLinesEx(rect,.08,6,selected?2:1,outline)
			portrait_size:=layout.compact?f32(42):f32(36)
			portrait_y:=rect.y+(rect.height-portrait_size)*.5
			text_x:=rect.x+portrait_size+15
			draw_chronicle_portrait(app,assets,record.archetype,{rect.x+7,portrait_y,portrait_size,portrait_size})
			seal_size:=f32(20)
			draw_chronicle_outcome_seal(assets,record.outcome,{rect.x+rect.width-seal_size-8,rect.y+(rect.height-seal_size)*.5,seal_size,seal_size})
			outcome:=record.outcome==.Victory?"VICTORY":"FALLEN"
			color:=record.outcome==.Victory?COLOR_TITLE:rl.Color{205,80,72,255}
			ui_draw_text(fmt.ctprintf("%s - %s",ARCHETYPES[record.archetype].name,outcome),i32(text_x),i32(rect.y+3),layout.compact?15:14,color)
			ui_draw_text(fmt.ctprintf("%s  Depth %d  Level %d",difficulty_profile(record.difficulty).name,record.deepest_floor,record.final_level),i32(text_x),i32(rect.y+(layout.compact?19:17)),layout.compact?12:11,COLOR_TEXT)
			date:=record.ended_at_utc
			if len(date)>10 do date=date[:10]
			ui_draw_text(fmt.ctprintf("%s  /  %d kills  /  %.1f min",date,record.kills,f64(record.active_ticks)/f64(SIM_HZ*60)),i32(text_x),i32(rect.y+(layout.compact?36:31)),layout.compact?11:10,COLOR_TEXT_DIM)
			trail_x:=rect.x+rect.width-184
			for step in 0..<DUNGEON_DEPTH {
				filled:=step<record.deepest_floor
				trail_color := color
				if !filled do trail_color = rl.Fade(COLOR_TEXT_DIM,.35)
				rl.DrawCircleV({trail_x+f32(step)*10,rect.y+11},filled?3:2,trail_color)
			}
		}
	}
	draw_chronicle_detail(chronicle_record_at(&app.profile,&app.chronicle,app.chronicle.selected),layout.detail,assets,layout.compact)
	back:cstring="Esc / B: Return to title     Tab / RB: Change filter focus"
	back_size:=layout.compact?i32(16):i32(13)
	back_width:=ui_measure_text(back,back_size)
	ui_draw_text(back,i32(layout.content.x+(layout.content.width-f32(back_width))*.5),i32(layout.footer_y),back_size,COLOR_TEXT_DIM)
}

choice_overlay_row_at :: proc(point:rl.Vector2,count:int) -> (int,bool) {
	if count<=0 do return 0,false
	presentation:=ui_presentation()
	panel:=menu_panel(560,i32(300+max(0,count-2)*52))
	design:=point/presentation.scale
	for index in 0..<count {
		rect:=rl.Rectangle{panel.x+34,panel.y+118+f32(index)*54,panel.width-68,44}
		if rl.CheckCollisionPointRec(design,rect) do return index,true
	}
	return 0,false
}

chronicle_filter_at :: proc(point:rl.Vector2) -> (Chronicle_Focus,bool) {
	presentation:=ui_presentation()
	layout:=chronicle_ui_layout(presentation.width,presentation.height,presentation.responsive_width)
	design:=point/presentation.scale
	chip_w:=min(f32(190),(layout.filters.width-24)/3)
	for index in 0..<3 {
		rect:=rl.Rectangle{layout.filters.x+f32(index)*(chip_w+12),layout.filters.y,chip_w,38}
		if rl.CheckCollisionPointRec(design,rect) do return Chronicle_Focus(index),true
	}
	return .Timeline,false
}

@(private = "file")
draw_choice_overlay :: proc(app:^App,assets:^Assets,title:cstring,body:cstring,labels:[]cstring) {
	presentation:=ui_begin_presentation();defer ui_end_presentation()
	rl.DrawRectangleRec({0,0,presentation.width,presentation.height},rl.Fade(rl.BLACK,.72))
	panel:=menu_panel(560,i32(300+max(0,len(labels)-2)*52))
	draw_menu_panel_chrome(assets,panel)
	ui_draw_text(title,i32(panel.x+30),i32(panel.y+24),27,COLOR_TITLE)
	ui_draw_text(body,i32(panel.x+30),i32(panel.y+66),16,COLOR_TEXT)
	for label,index in labels {
		rect:=rl.Rectangle{panel.x+34,panel.y+118+f32(index)*54,panel.width-68,44}
		selected:=ui_navigation_selected(app,index==app.confirm_index)
		content:=draw_menu_row_chrome(assets,rect,selected)
		ui_draw_text(label,i32(content.x),i32(rect.y+11),18,selected?COLOR_TITLE:COLOR_TEXT)
	}
}

draw_abandon_confirm :: proc(app:^App,assets:^Assets) {
	labels:=[2]cstring{"Keep this descent","Abandon and begin anew"}
	draw_choice_overlay(app,assets,"ABANDON ACTIVE DESCENT?","The unfinished run will not enter the Chronicle.",labels[:])
}

draw_recovery_screen :: proc(app:^App,assets:^Assets) {
	labels:=[3]cstring{"Retry best backup recovery","Quarantine save and begin anew","Back to title"}
	if app.profile_save_damaged||app.options_save_damaged {
		title:cstring="DAMAGED LOCAL RECORDS"
		body:cstring="Profile or option data failed validation. Recover it or preserve the bytes in quarantine."
		if app.profile_save_damaged&&!app.options_save_damaged {
			title="DAMAGED PROFILE"
			body="Chronicle and unlock data failed validation. Recover it or preserve the bytes in quarantine."
		} else if app.options_save_damaged&&!app.profile_save_damaged {
			title="DAMAGED OPTIONS"
			body="Option data failed validation. Recover it or preserve the bytes in quarantine."
		}
		draw_choice_overlay(app,assets,title,body,labels[:])
		return
	}
	draw_choice_overlay(app,assets,"DAMAGED ACTIVE SAVE","The checkpoint failed validation. Recover it or preserve the bytes in quarantine.",labels[:])
}

draw_save_wait_overlay :: proc(app:^App,assets:^Assets) {
	presentation:=ui_begin_presentation();defer ui_end_presentation()
	rl.DrawRectangleRec({0,0,presentation.width,presentation.height},rl.Fade(rl.BLACK,.7))
	panel:=menu_panel(480,190);draw_menu_panel_chrome(assets,panel)
	ui_draw_text("INSCRIBING THE LEDGER",i32(panel.x+30),i32(panel.y+34),25,COLOR_TITLE)
	ui_draw_text("Writing a durable checkpoint...",i32(panel.x+30),i32(panel.y+82),17,COLOR_TEXT)
	phase:=f32(app.tick%60)/60
	rl.DrawRing({panel.x+panel.width-62,panel.y+95},15,20,phase*360,phase*360+245,24,COLOR_TITLE)
}

draw_save_error_overlay :: proc(app:^App,assets:^Assets) {
	if app.failed_request==.Recover_Run||app.failed_request==.Recover_Documents {
		labels:=[3]cstring{"Retry","Back to recovery","Return to title"}
		draw_choice_overlay(app,assets,"RECOVERY FAILED","No valid candidate could be promoted. The original bytes remain unchanged.",labels[:])
		return
	}
	labels:=[3]cstring{"Retry","Cancel","Exit without saving"}
	draw_choice_overlay(app,assets,"SAVE FAILED","The last durable checkpoint is unchanged.",labels[:])
}

draw_resume_veil :: proc(app:^App,assets:^Assets) {
	presentation:=ui_begin_presentation();defer ui_end_presentation()
	rl.DrawRectangleRec({0,0,presentation.width,presentation.height},rl.Fade(rl.BLACK,.54))
	panel:=menu_panel(520,170);draw_menu_panel_chrome(assets,panel)
	ui_draw_text("DESCENT RESTORED",i32(panel.x+30),i32(panel.y+30),28,COLOR_TITLE)
	ui_draw_text("The fixed moment waits.",i32(panel.x+30),i32(panel.y+80),16,COLOR_TEXT)
	ui_draw_text("Tap or press Enter / A to continue.",i32(panel.x+30),i32(panel.y+104),16,COLOR_TEXT)
}

options_layout_bounds :: proc(app: ^App) -> rl.Rectangle {
	presentation := ui_presentation()
	bounds := rl.Rectangle{0, 0, presentation.width, presentation.height}
	if app != nil && app.options_return != .Paused {
		return menu_background_content_rect(bounds.width, bounds.height)
	}
	return bounds
}

options_panel_rect :: proc(app: ^App) -> rl.Rectangle {
	return menu_panel_in_bounds(options_layout_bounds(app), 660, 650)
}

options_row_rect_in_panel :: proc(panel: rl.Rectangle, index: int) -> rl.Rectangle {
	top_padding := clamp(panel.height*.10, f32(52), f32(65))
	bottom_padding := clamp(panel.height*.07, f32(34), f32(45))
	pitch := max(f32(32), (panel.height-top_padding-bottom_padding)/11)
	row_height := min(f32(44), max(f32(28), pitch-5))
	return {panel.x+30, panel.y+top_padding+f32(index)*pitch, panel.width-60, row_height}
}

options_row_rect :: proc(app: ^App, index: int) -> rl.Rectangle {
	return options_row_rect_in_panel(options_panel_rect(app), index)
}

options_row_at :: proc(app: ^App, point: rl.Vector2) -> (int,bool) {
	design_point := ui_screen_to_design(point)
	panel := options_panel_rect(app)
	for i in 0..<11 {
		if rl.CheckCollisionPointRec(design_point,options_row_rect_in_panel(panel,i)) do return i,true
	}
	return 0,false
}

on_off :: proc(value: bool) -> cstring {return value?"On":"Off"}

draw_options_screen :: proc(app: ^App, assets: ^Assets) {
	_ = ui_begin_presentation()
	defer ui_end_presentation()
	if app.options_return != .Paused do draw_menu_background(assets,false)
	panel := options_panel_rect(app)
	draw_menu_panel_chrome(assets,panel)
	ui_draw_text("OPTIONS",i32(panel.x+30),i32(panel.y+20),28,COLOR_TITLE)
	labels := [11]cstring{
		"Fullscreen","Frame rate cap","View zoom","Difficulty","Controls",
		"Controller","Audio cues","Music","Lighting","Mist","Return",
	}
	values := [11]cstring{
		on_off(app.options.fullscreen),
		fmt.ctprintf("%s",frame_rate_cap_label(app.options.frame_rate_cap)),
		fmt.ctprintf("%.2fx",app.options.view_zoom),
		fmt.ctprintf("%s",difficulty_profile(app.options.difficulty).name),
		"View bindings",
		on_off(app.options.controller_enabled),
		on_off(app.options.audio_enabled),
		fmt.ctprintf("%s",MUSIC_VOLUME_LABELS[music_volume_normalize(app.options.music_volume)]),
		on_off(app.options.lighting_enabled),
		on_off(app.options.mist_enabled),
		"",
	}
	when ARCH_ROGUE_ANDROID {
		labels[0] = "Native fullscreen"
		values[0] = "On"
	}
	for label,i in labels {
		rect := options_row_rect_in_panel(panel,i)
		selected := ui_navigation_selected(app,i==app.options_index)
		content := draw_menu_row_chrome(assets,rect,selected)
		label_y := rect.y+(rect.height-18)*.5
		ui_draw_text(label,i32(content.x),i32(label_y),18,selected?COLOR_TITLE:COLOR_TEXT)
		if values[i]!="" {
			w:=ui_measure_text(values[i],16)
			value_y := rect.y+(rect.height-16)*.5
			ui_draw_text(values[i],i32(content.x+content.width-f32(w)),i32(value_y),16,selected?COLOR_TITLE:COLOR_TEXT_DIM)
		}
	}
	ui_draw_text("Arrows change  |  Enter select  |  Esc return",i32(panel.x+30),i32(panel.y+panel.height-27),14,COLOR_TEXT_DIM)
}

controls_panel_rect :: proc(app: ^App) -> rl.Rectangle {
	return menu_panel_in_bounds(options_layout_bounds(app), 940, 620)
}

controls_right_x :: proc(panel: rl.Rectangle) -> f32 {
	return panel.x + panel.width*.515
}

controls_footer_y :: proc(panel: rl.Rectangle) -> f32 {
	return panel.y + panel.height-32
}

controls_status_y :: proc(panel: rl.Rectangle) -> f32 {
	return controls_footer_y(panel)-38
}

controls_row_rect_in_panel :: proc(panel: rl.Rectangle, index: int) -> rl.Rectangle {
	rows_start := panel.y+72
	pitch := min(
		f32(46),
		max(f32(30), (controls_status_y(panel)-rows_start-8)/f32(len(CONTROLLER_REMAPPABLE_COMMANDS))),
	)
	row_height := min(f32(39), max(f32(26), pitch-6))
	right_x := controls_right_x(panel)
	return {right_x, rows_start+f32(index)*pitch, panel.x+panel.width-30-right_x, row_height}
}

controls_row_rect :: proc(app: ^App, index: int) -> rl.Rectangle {
	return controls_row_rect_in_panel(controls_panel_rect(app), index)
}

controls_row_at :: proc(app: ^App, point: rl.Vector2) -> (int,bool) {
	design_point := ui_screen_to_design(point)
	panel := controls_panel_rect(app)
	for index in 0..<len(CONTROLLER_REMAPPABLE_COMMANDS) {
		if rl.CheckCollisionPointRec(design_point,controls_row_rect_in_panel(panel,index)) do return index,true
	}
	return 0,false
}

draw_controls_screen :: proc(app: ^App, assets: ^Assets) {
	_ = ui_begin_presentation()
	defer ui_end_presentation()
	if app.options_return != .Paused do draw_menu_background(assets,false)
	panel := controls_panel_rect(app)
	draw_menu_panel_chrome(assets,panel)
	ui_draw_text("CONTROLS",i32(panel.x+28),i32(panel.y+18),28,COLOR_TITLE)
	keyboard := [13]cstring{
		"Arrows              Move", "Mouse               Aim / walk",
		"1                   Big Hit", "2                   Bolt",
		"3                   Class skill", "4                   Dash",
		"5                   Health potion", "6                   Mana potion",
		"E                   Interact", "I                   Inventory",
		"C                   Character", "Esc                 Pause / back",
		"Ctrl+M / wheel      Map toggle / zoom",
	}
	ui_draw_text("KEYBOARD & MOUSE",i32(panel.x+32),i32(panel.y+57),15,COLOR_TITLE)
	keyboard_pitch := min(f32(34), max(f32(24), (panel.height-132)/f32(len(keyboard))))
	keyboard_font: i32 = panel.height < 560 ? 15 : 17
	for line,i in keyboard {
		ui_draw_text(line,i32(panel.x+32),i32(panel.y+88+f32(i)*keyboard_pitch),keyboard_font,COLOR_TEXT)
	}

	right_x := controls_right_x(panel)
	ui_draw_text("GAMEPAD -- REMAPPABLE",i32(right_x),i32(panel.y+57),15,COLOR_TITLE)
	for command,index in CONTROLLER_REMAPPABLE_COMMANDS {
		rect := controls_row_rect_in_panel(panel,index)
		focused := index == app.controls_index
		selected := ui_navigation_selected(app,focused)
		capturing := focused && app.controls_capture
		content := draw_menu_row_chrome(assets,rect,selected)
		if capturing do rl.DrawRectangleLinesEx(rect,1,rl.Color{225,120,86,255})
		text_y := rect.y+(rect.height-14)*.5
		ui_draw_text(fmt.ctprintf("%s",INPUT_COMMAND_LABELS[command]),i32(content.x),i32(text_y),14,selected?COLOR_TITLE:COLOR_TEXT)
		binding := capturing ? "..." : controller_binding_label(&app.options.gamepad_mapping,command)
		binding_text := fmt.ctprintf("%s",binding)
		w := ui_measure_text(binding_text,14)
		ui_draw_text(binding_text,i32(content.x+content.width-f32(w)),i32(text_y),14,capturing?rl.Color{225,120,86,255}:COLOR_TEXT_DIM)
	}
	status := app.controls_status
	if status == "" do status = "Select an action, then press a new button or trigger."
	ui_draw_text(fmt.ctprintf("%s",status),i32(right_x),i32(controls_status_y(panel)),13,app.controls_capture?COLOR_TITLE:COLOR_TEXT_DIM)
	ui_draw_text(app.controls_capture?"Esc: cancel mapping":"Enter/A or click: remap   Esc/LB: return",i32(panel.x+32),i32(controls_footer_y(panel)),14,COLOR_TITLE)
}

character_panel_rect :: proc() -> rl.Rectangle {return menu_panel(780,600)}

memory_token_prompt_rect :: proc() -> rl.Rectangle {
	return {22, 76, 190, 50}
}

character_tab_rect :: proc(tab: Character_Tab) -> rl.Rectangle {
	// Wide enough that the arrow-endcap row art leaves a usable label rail. The
	// pair right-aligns to the panel and slightly overlaps its top edge.
	panel := character_panel_rect()
	height: f32 = 34
	return {panel.x + 365 + f32(int(tab) * 195), panel.y-height*.5+6, 180, height}
}

character_tab_at :: proc(point: rl.Vector2) -> (Character_Tab, bool) {
	design_point := ui_screen_to_design(point)
	for tab in Character_Tab {
		if rl.CheckCollisionPointRec(design_point, character_tab_rect(tab)) do return tab, true
	}
	return .Overview, false
}

@(rodata)
DISCIPLINE_PATH_LABELS := [Discipline_Path]string{
	.Warden_Bulwark="Bulwark",.Warden_Riposte="Riposte",.Warden_Vow="Vow",.Warden_Time="Time",
	.Rogue_Precision="Precision",.Rogue_Shadow="Shadow",.Rogue_Traps="Traps",.Rogue_Marksman="Marksman",
	.Arcanist_Bolt="Bolt",.Arcanist_Nova="Nova",.Arcanist_Storm="Storm",.Arcanist_Ward="Ward",
	.Acolyte_Blood="Blood",.Acolyte_Veil="Veil",.Acolyte_Spirit="Spirit",.Acolyte_Curse="Curse",
	.Ranger_Control="Control",.Ranger_Volley="Volley",.Ranger_Beast="Beast",.Ranger_Survival="Survival",
}

discipline_cell_rect :: proc(column,degree: int) -> rl.Rectangle {
	panel:=character_panel_rect()
	return {panel.x+40+f32(column*182),panel.y+142+f32(degree*70),166,58}
}

discipline_cell_at :: proc(point: rl.Vector2) -> (index: int,found: bool) {
	design_point := ui_screen_to_design(point)
	for degree in 0..<DISCIPLINE_DEGREES {
		for column in 0..<DISCIPLINE_PATHS_PER_ARCHETYPE {
			if rl.CheckCollisionPointRec(design_point,discipline_cell_rect(column,degree)) {
				return degree*DISCIPLINE_PATHS_PER_ARCHETYPE+column,true
			}
		}
	}
	return 0,false
}

@(private = "file")
draw_character_card :: proc(assets: ^Assets, rect: rl.Rectangle, title: cstring) {
	content := rect
	if assets != nil {
		asset := ui_chrome_asset(assets,.Menu_Panel_Inset)
		if draw_ui_chrome(asset,rect) {
			if safe,ok:=ui_chrome_content_rect(asset,rect);ok do content=safe
		} else {
			rl.DrawRectangleRec(rect,rl.Fade(COLOR_ROW,.94))
			rl.DrawRectangleLinesEx(rect,1,rl.Fade(COLOR_TEXT_DIM,.65))
		}
	} else {
		rl.DrawRectangleRec(rect,rl.Fade(COLOR_ROW,.94))
		rl.DrawRectangleLinesEx(rect,1,rl.Fade(COLOR_TEXT_DIM,.65))
	}
	ui_draw_text(title,i32(content.x),i32(rect.y+8),13,COLOR_TITLE)
}

@(private = "file")
draw_character_card_line :: proc(rect: rl.Rectangle, row: int, text: cstring, color := COLOR_TEXT) {
	font_size: i32 = 12
	for font_size > 9 && ui_measure_text(text,font_size) > i32(rect.width-28) do font_size -= 1
	ui_draw_text(text, i32(rect.x+14), i32(rect.y+31+f32(row*21)), font_size, color)
}

DISCIPLINE_NAME_FONT_SIZE  :: i32(9)
DISCIPLINE_STATE_FONT_SIZE :: i32(8)
DISCIPLINE_TEXT_LEFT_INSET :: f32(1)

Discipline_Text_Draw :: struct {
	name:        string,
	state_label: cstring,
	text_rect:   rl.Rectangle,
	color:       rl.Color,
}

// Keeping the two lines fixed prevents neighboring cards from changing visual
// weight based on label length. This intentionally has no inner-rail scissor:
// the final text pass must remain visible over decorative panel-frame pixels.
@(private = "file")
draw_discipline_text :: proc(name: string, state_label: cstring, text_rect: rl.Rectangle, color: rl.Color) {
	text := fmt.ctprintf("%s", name)
	block_h := f32(DISCIPLINE_NAME_FONT_SIZE+DISCIPLINE_STATE_FONT_SIZE+1)
	y := text_rect.y+max(f32(0),(text_rect.height-block_h)*.5)
	text_x := i32(text_rect.x+DISCIPLINE_TEXT_LEFT_INSET)
	ui_draw_text(text,text_x,i32(y),DISCIPLINE_NAME_FONT_SIZE,color)
	ui_draw_text(
		state_label,
		text_x,
		i32(y)+DISCIPLINE_NAME_FONT_SIZE+1,
		DISCIPLINE_STATE_FONT_SIZE,
		color,
	)
}

@(private = "file")
character_known_proc :: proc(player: ^Player, effect: Proc_Effect) -> bool {
	return (player.has_weapon && !player.weapon.unidentified && item_has_proc_effect(&player.weapon,effect)) ||
		(player.has_armor && !player.armor.unidentified && item_has_proc_effect(&player.armor,effect))
}

@(private = "file")
character_known_bonus :: proc(player: ^Player, bonus: Skill_Bonus) -> bool {
	return (player.has_weapon && !player.weapon.unidentified && item_has_bonus(&player.weapon,bonus)) ||
		(player.has_armor && !player.armor.unidentified && item_has_bonus(&player.armor,bonus))
}

@(private = "file")
character_has_known_curse :: proc(player: ^Player) -> bool {
	return (player.has_weapon && !player.weapon.unidentified && player.weapon.cursed) ||
		(player.has_armor && !player.armor.unidentified && player.armor.cursed)
}

draw_character_panel :: proc(app: ^App, assets: ^Assets) {
	ui_begin_presentation()
	defer ui_end_presentation()
	player:=&app.run.player
	panel:=character_panel_rect()
	draw_menu_panel_chrome(assets,panel)
	ui_draw_text("CHARACTER",i32(panel.x+36),i32(panel.y+22),28,COLOR_TITLE)
	memory_text:=fmt.ctprintf("%s   Level %v   XP %v/%v   Memory %v",ARCHETYPES[player.archetype].name,player.level,player.xp,player.next_xp,player.memory_tokens)
	ui_draw_text(memory_text,i32(panel.x+36),i32(panel.y+58),18,player.memory_tokens>0?COLOR_TITLE:COLOR_TEXT)
	if assets != nil {
		glyph:=ui_ouroboros_glyph(assets)
		draw_ui_glyph(glyph,{panel.x+panel.width-59,panel.y+56,22,22},player.memory_tokens>0?rl.WHITE:rl.Color{115,115,126,210})
	}
	tab_labels := [2]cstring{"Overview","Disciplines"}
	tab_rects: [2]rl.Rectangle
	tab_contents: [2]rl.Rectangle
	for _,tab in tab_labels {
		tab_rects[tab] = character_tab_rect(Character_Tab(tab))
		selected:=int(app.character_tab)==tab
		tab_contents[tab]=draw_menu_row_chrome(assets,tab_rects[tab],selected)
	}
	tab_font:i32 = 16
	for label,tab in tab_labels {
		for tab_font > 10 && ui_measure_text(label,tab_font) > i32(tab_contents[tab].width-6) do tab_font -= 1
	}
	for label,tab in tab_labels {
		rect,content := tab_rects[tab],tab_contents[tab]
		selected:=int(app.character_tab)==tab
		ui_draw_text(label,i32(content.x+(content.width-f32(ui_measure_text(label,tab_font)))*.5),i32(rect.y+(rect.height-f32(tab_font))*.5),tab_font,selected?COLOR_TITLE:COLOR_TEXT_DIM)
	}
	if app.character_tab==.Overview {
		class_stat: cstring
		switch player.archetype {
		case .Warden:
			class_stat = fmt.ctprintf("Time Skip  %.1fs",TIME_SKIP_DURATION)
		case .Rogue:
			bell_damage := 20 + player.level*3 + ARCHETYPES[player.archetype].melee_bonus + max(0,ARCHETYPES[player.archetype].spell_bonus/2)
			class_stat = fmt.ctprintf("Bell damage  %v",bell_damage)
		case .Arcanist:
			radius := f32(NOVA_BASE_RADIUS)
			if player_has_class_skill_bonus(player) do radius += .25
			class_stat = fmt.ctprintf("Nova reach  %.2f",radius)
		case .Acolyte:
			stats := spirit_call_stats(discipline_path_rank(player,.Acolyte_Spirit))
			class_stat = fmt.ctprintf("Spirit damage  %v",stats.damage)
		case .Ranger:
			stats := spirit_beast_stats(discipline_path_rank(player,.Ranger_Beast))
			class_stat = fmt.ctprintf("Beast damage  %v",stats.damage)
		}
		stats := [9]cstring{
			fmt.ctprintf("HP  %v/%v",player.hp,player.max_hp),
			fmt.ctprintf("Mana  %.0f/%v",player.mana,player.max_mana),
			fmt.ctprintf("Stamina  %.0f/%v",player.stamina,player.max_stamina),
			fmt.ctprintf("Move  %.2f tiles/s",player_speed(player)),
			fmt.ctprintf("Melee  %v",player_melee_damage(player)),
			fmt.ctprintf("Spell  %v",player_spell_damage(player,BOLT_BASE_DAMAGE)),
			fmt.ctprintf("Armor  %v",player_armor(player)),
			fmt.ctprintf("Weapon  %s",DAMAGE_TYPE_NAMES[player_weapon_damage_type(player)]),
			class_stat,
		}
		for line,i in stats {
			x := panel.x+40+f32((i%3)*240)
			y := panel.y+112+f32((i/3)*35)
			ui_draw_text(line,i32(x),i32(y),15,COLOR_TEXT)
		}

		card_w: f32 = 340
		card_h: f32 = 132
		cards := [4]rl.Rectangle{
			{panel.x+40,panel.y+224,card_w,card_h},
			{panel.x+400,panel.y+224,card_w,card_h},
			{panel.x+40,panel.y+370,card_w,card_h},
			{panel.x+400,panel.y+370,card_w,card_h},
		}
		draw_character_card(assets,cards[0],"SKILLS")
		actions := ACTION_NAMES[player.archetype]
		draw_character_card_line(cards[0],0,fmt.ctprintf("1 %s  |  %v stamina",actions[0],BIGHIT_STAMINA_COST))
		draw_character_card_line(cards[0],1,fmt.ctprintf("2 %s  |  %v mana",actions[1],player_bolt_mana_cost(player)))
		draw_character_card_line(cards[0],2,fmt.ctprintf("3 %s  |  %.0f mana",actions[2],player_class_skill_mana_cost(player)))
		draw_character_card_line(cards[0],3,fmt.ctprintf("4 %s  |  %v stamina",actions[3],player_dash_stamina_cost(player)))

		draw_character_card(assets,cards[1],"EQUIPMENT")
		weapon_line: cstring = "Weapon: Training Sword"
		armor_line: cstring = "Armor: Cloth"
		if player.has_weapon {
			if player.weapon.unidentified {
				weapon_line=fmt.ctprintf("Weapon: %s",item_display_name(player.weapon))
			} else {
				curse: cstring = player.weapon.cursed ? "! " : ""
				weapon_line=fmt.ctprintf("Weapon: %s%s  (+%v)",curse,item_display_name(player.weapon),item_power(player.weapon))
			}
		}
		if player.has_armor {
			if player.armor.unidentified {
				armor_line=fmt.ctprintf("Armor: %s",item_display_name(player.armor))
			} else {
				curse: cstring = player.armor.cursed ? "! " : ""
				armor_line=fmt.ctprintf("Armor: %s%s  (+%v)",curse,item_display_name(player.armor),item_defense(player.armor))
			}
		}
		draw_character_card_line(cards[1],0,weapon_line)
		draw_character_card_line(cards[1],1,armor_line)
		draw_character_card_line(cards[1],2,fmt.ctprintf("Bolt type: %s",DAMAGE_TYPE_NAMES[player_bolt_damage_type(player)]),COLOR_TEXT_DIM)
		draw_character_card_line(cards[1],3,fmt.ctprintf("Gold: %v",player.gold),COLOR_TEXT_DIM)

		draw_character_card(assets,cards[2],"UPGRADES")
		upgrade_row := 0
		for id in Discipline_Id {
			if !player.acquired_disciplines[id] do continue
			draw_character_card_line(cards[2],upgrade_row,fmt.ctprintf("%s",DISCIPLINES[id].name))
			upgrade_row += 1
			if upgrade_row>=4 do break
		}
		if upgrade_row==0 do draw_character_card_line(cards[2],0,"No disciplines remembered",COLOR_TEXT_DIM)

		draw_character_card(assets,cards[3],"STATUS & PROCS")
		condition_bytes: [256]byte
		condition_text := strings.builder_from_bytes(condition_bytes[:])
		strings.write_string(&condition_text,"Conditions: ")
		condition_count := 0
		condition_shown := 0
		for status in Status_Kind {
			if player.statuses[status]<=0 do continue
			condition_count += 1
			if condition_shown>=2 do continue
			if condition_shown>0 do strings.write_string(&condition_text,", ")
			fmt.sbprintf(&condition_text,"%s %.1fs",STATUS_DEFS[status].name,player.statuses[status])
			condition_shown += 1
		}
		if condition_count==0 do strings.write_string(&condition_text,"none")
		if condition_count>condition_shown do fmt.sbprintf(&condition_text,"  +%v more",condition_count-condition_shown)
		draw_character_card_line(cards[3],0,strings.unsafe_to_cstring(&condition_text),condition_count>0?COLOR_TEXT:COLOR_TEXT_DIM)

		proc_bytes: [256]byte
		proc_text := strings.builder_from_bytes(proc_bytes[:])
		strings.write_string(&proc_text,"Procs: ")
		proc_count := 0
		proc_shown := 0
		for effect in Proc_Effect {
			if effect==.None||!character_known_proc(player,effect) do continue
			proc_count += 1
			if proc_shown>=2 do continue
			if proc_shown>0 do strings.write_string(&proc_text,", ")
			strings.write_string(&proc_text,PROC_EFFECT_NAMES[effect])
			proc_shown += 1
		}
		if proc_count==0 do strings.write_string(&proc_text,"none")
		if proc_count>proc_shown do fmt.sbprintf(&proc_text,"  +%v more",proc_count-proc_shown)
		if character_has_known_curse(player) do strings.write_string(&proc_text,"  |  CURSED")
		draw_character_card_line(cards[3],1,strings.unsafe_to_cstring(&proc_text),proc_count>0||character_has_known_curse(player)?COLOR_TEXT:COLOR_TEXT_DIM)

		bonus_bytes: [256]byte
		bonus_text := strings.builder_from_bytes(bonus_bytes[:])
		strings.write_string(&bonus_text,"Skill mods: ")
		bonus_count := 0
		bonus_shown := 0
		for bonus in Skill_Bonus {
			if !character_known_bonus(player,bonus) do continue
			bonus_count += 1
			if bonus_shown>=2 do continue
			if bonus_shown>0 do strings.write_string(&bonus_text,", ")
			strings.write_string(&bonus_text,SKILL_BONUS_NAMES[bonus])
			bonus_shown += 1
		}
		if bonus_count==0 do strings.write_string(&bonus_text,"none")
		if bonus_count>bonus_shown do fmt.sbprintf(&bonus_text,"  +%v more",bonus_count-bonus_shown)
		draw_character_card_line(cards[3],2,strings.unsafe_to_cstring(&bonus_text),bonus_count>0?COLOR_TEXT:COLOR_TEXT_DIM)

		draw_character_card_line(cards[3],3,fmt.ctprintf("Attack %+.0f%%  Cast %+.0f%%  Thorns %v  Leech %.0f%%",player_attack_speed(player)*100,player_cast_speed(player)*100,player_thorns(player),player_lifesteal(player)*100))
	} else {
		discipline_text_draws: [DISCIPLINE_PATHS_PER_ARCHETYPE*DISCIPLINE_DEGREES]Discipline_Text_Draw
		for column in 0..<DISCIPLINE_PATHS_PER_ARCHETYPE {
			path,_:=discipline_path_at(player.archetype,column)
			ui_draw_text(fmt.ctprintf("%s",DISCIPLINE_PATH_LABELS[path]),i32(panel.x+46+f32(column*182)),i32(panel.y+108),16,COLOR_TITLE)
			for degree in 0..<DISCIPLINE_DEGREES {
				id,_:=discipline_at(path,degree+1)
				def:=DISCIPLINES[id]
				state:=discipline_state(player,id)
				rect:=discipline_cell_rect(column,degree)
				selected:=ui_navigation_selected(app,column==app.discipline_column&&degree==app.discipline_degree)
				color:=COLOR_TEXT_DIM
				if state==.Chosen do color=rl.Color{126,214,92,255}
				if state==.Available do color=COLOR_TEXT
				if state==.Path_Locked do color=rl.Color{140,74,92,255}
				text_rect:=rl.Rectangle{rect.x+52,rect.y+6,rect.width-60,rect.height-12}
				if assets != nil {
					plate:=ui_discipline_panel(assets,player.archetype)
					if draw_ui_chrome(plate,rect) {
						if safe,ok:=ui_chrome_content_rect(plate,rect);ok do text_rect=safe
						socket_scale:=rect.height/max(f32(1),f32(plate.source_size[1]))
						glyph_size:=clamp(rect.height*.39,f32(9),f32(40))
						glyph_center:=rl.Vector2{rect.x+104*socket_scale,rect.y+96*socket_scale}
						glyph:=ui_discipline_glyph(assets,id)
						glyph_tint:=color
						if state==.Available || state==.Chosen do glyph_tint=rl.WHITE
						draw_ui_glyph(glyph,{glyph_center.x-glyph_size*.5,glyph_center.y-glyph_size*.5,glyph_size,glyph_size},glyph_tint)
					} else {
						rl.DrawRectangleRec(rect,selected?COLOR_ROW_SELECTED:COLOR_ROW)
					}
				} else {
					rl.DrawRectangleRec(rect,selected?COLOR_ROW_SELECTED:COLOR_ROW)
				}
				if selected do rl.DrawRectangleLinesEx(rect,2,COLOR_TITLE)
				state_label: cstring
				switch state {
				case .Chosen: state_label = "CHOSEN"
				case .Available: state_label = player.memory_tokens > 0 ? "AVAILABLE" : "NO TOKEN"
				case .Path_Locked: state_label = "PATH SEALED"
				case .Locked: state_label = "LOCKED"
				}
				// Defer labels until every plate, glyph, and selection outline has
				// landed so no later card artwork can cover their pixels.
				draw_index := column*DISCIPLINE_DEGREES+degree
				discipline_text_draws[draw_index] = {
					name = def.name,
					state_label = state_label,
					text_rect = text_rect,
					color = color,
				}
			}
		}
		if id,found:=character_selected_discipline(app);found {
			def:=DISCIPLINES[id]
			state := discipline_state(player, id)
			suffix: cstring
			switch state {
			case .Chosen: suffix = "  [chosen]"
			case .Available: suffix = player.memory_tokens > 0 ? "  [cost: 1 memory]" : "  [no memory token]"
			case .Path_Locked: suffix = "  [sealed: maximum two paths]"
			case .Locked: suffix = "  [prerequisite locked]"
			}
			detail := fmt.ctprintf("%s%s",def.description,suffix)
			detail_size:i32 = 13
			for detail_size > 8 && ui_measure_text(detail,detail_size) > i32(panel.width-80) do detail_size -= 1
			ui_draw_text(detail,i32(panel.x+40),i32(panel.y+514),detail_size,COLOR_TEXT)
		}
		// Topmost discipline-card pass: text is never followed by plate art.
		for text_draw in discipline_text_draws {
			draw_discipline_text(text_draw.name,text_draw.state_label,text_draw.text_rect,text_draw.color)
		}
	}
	ui_draw_text("Tab/1/2: tabs   Arrows: choose   Enter: learn   C/Esc: close",i32(panel.x+36),i32(panel.y+568),13,COLOR_TEXT_DIM)
}

shop_panel_rect :: proc() -> rl.Rectangle {return menu_panel(620,570)}

shop_mode_rect :: proc(mode: Shop_Mode) -> rl.Rectangle {
	// Wide enough that the arrow-endcap row art leaves a usable label rail.
	panel := shop_panel_rect()
	return {panel.x + 24 + f32(int(mode) * 164), panel.y + 78, 150, 30}
}

shop_mode_at :: proc(point: rl.Vector2) -> (Shop_Mode, bool) {
	design_point := ui_screen_to_design(point)
	for mode in Shop_Mode {
		if rl.CheckCollisionPointRec(design_point, shop_mode_rect(mode)) do return mode, true
	}
	return .Buy, false
}

shop_row_rect :: proc(index: int) -> rl.Rectangle {
	panel:=shop_panel_rect()
	return {panel.x+24,panel.y+116+f32(index*49),panel.width-48,42}
}

shop_row_at :: proc(app:^App,point:rl.Vector2)->(int,bool){
	design_point:=ui_screen_to_design(point)
	visible := min(SHOP_VISIBLE_ROWS, max(0, shop_entry_count(app) - app.shop_scroll))
	for row in 0..<visible {
		if rl.CheckCollisionPointRec(design_point,shop_row_rect(row)) do return app.shop_scroll + row,true
	}
	return 0,false
}

draw_shop_panel :: proc(app:^App,assets:^Assets){
	ui_begin_presentation()
	defer ui_end_presentation()
	panel:=shop_panel_rect()
	keeper:=&app.run.shopkeeper
	draw_menu_panel_chrome(assets,panel)
	ui_draw_text(fmt.ctprintf("%s",keeper.name),i32(panel.x+24),i32(panel.y+18),26,COLOR_TITLE)
	ui_draw_text(fmt.ctprintf("%s    Your gold: %v",keeper.role,app.run.player.gold),i32(panel.x+24),i32(panel.y+51),15,COLOR_TEXT_DIM)
	for label,mode in ([2]cstring{"BUY","SELL"}) {
		rect := shop_mode_rect(Shop_Mode(mode))
		selected:=int(app.shop_mode)==mode
		content:=draw_menu_row_chrome(assets,rect,selected)
		font:i32 = 14
		for font > 9 && ui_measure_text(label,font) > i32(content.width-6) do font -= 1
		ui_draw_text(label,i32(content.x+(content.width-f32(ui_measure_text(label,font)))*.5),i32(rect.y+(rect.height-f32(font))*.5),font,selected?COLOR_TITLE:COLOR_TEXT_DIM)
	}
	total := shop_entry_count(app)
	visible_end := min(total, app.shop_scroll + SHOP_VISIBLE_ROWS)
	for i in app.shop_scroll..<visible_end {
		item:=app.shop_mode==.Buy?keeper.stock[i]:app.run.player.bag[i]
		price:=app.shop_mode==.Buy?shop_price(keeper,item):shop_buyback_value(keeper,item)
		rect:=shop_row_rect(i - app.shop_scroll)
		selected:=ui_navigation_selected(app,i==app.shop_index)
		content:=draw_menu_row_chrome(assets,rect,selected)
		icon_x:=content.x
		if draw_item_icon(assets,item,{icon_x,rect.y+6,30,30},rl.WHITE) do icon_x+=36
		ui_draw_text(fmt.ctprintf("%s",item_display_name(item)),i32(icon_x),i32(rect.y+11),16,selected?COLOR_TITLE:COLOR_TEXT)
		cost:=fmt.ctprintf("%vg",price)
		ui_draw_text(cost,i32(content.x+content.width-f32(ui_measure_text(cost,15))),i32(rect.y+12),15,COLOR_TITLE)
	}
	if total==0 do ui_draw_text("No wares in this list.",i32(panel.x+28),i32(panel.y+136),16,COLOR_TEXT_DIM)
	if total > SHOP_VISIBLE_ROWS {
		ui_draw_text(fmt.ctprintf("showing %v-%v of %v", app.shop_scroll+1, visible_end, total),i32(panel.x+390),i32(panel.y+88),11,COLOR_TEXT_DIM)
	}
	ui_draw_text("Tab/Left/Right: Buy/Sell   Enter/E: trade   Esc: close",i32(panel.x+24),i32(panel.y+535),13,COLOR_TEXT_DIM)
}

// --- Inventory panel -------------------------------------------------------

inventory_panel_rect :: proc() -> rl.Rectangle {
	return {ui_design_width()-424, 52, 408, 552}
}

inventory_row_rect :: proc(visible_index: int) -> rl.Rectangle {
	// Rows share the panel's 24px content margin so they clear the border art.
	panel := inventory_panel_rect()
	return {panel.x + 24, panel.y + 146 + f32(visible_index * 40), panel.width - 48, 38}
}

inventory_row_at :: proc(app: ^App, point: rl.Vector2) -> (index: int, found: bool) {
	design_point := ui_screen_to_design(point)
	visible := min(INVENTORY_VISIBLE_ROWS, max(0, app.run.player.bag_count - app.inv_scroll))
	for row in 0 ..< visible {
		if rl.CheckCollisionPointRec(design_point, inventory_row_rect(row)) {
			return app.inv_scroll + row, true
		}
	}
	return 0, false
}

inventory_sort_chip_rect :: proc(mode: Inventory_Sort_Mode) -> rl.Rectangle {
	panel := inventory_panel_rect()
	// Right-aligned to the content margin: the last chip ends 24 in from the edge.
	return {panel.x + panel.width - 24 - 179 + f32(int(mode) * 61), panel.y + 118, 57, 25}
}

inventory_sort_mode_at :: proc(point: rl.Vector2) -> (mode: Inventory_Sort_Mode, found: bool) {
	design_point := ui_screen_to_design(point)
	for candidate in Inventory_Sort_Mode {
		if rl.CheckCollisionPointRec(design_point, inventory_sort_chip_rect(candidate)) {
			return candidate, true
		}
	}
	return .Type, false
}

inventory_sort_label :: proc(mode: Inventory_Sort_Mode) -> cstring {
	switch mode {
	case .Type:   return "TYPE"
	case .Rarity: return "RARITY"
	case .Power:  return "POWER"
	}
	return ""
}

draw_inventory_panel :: proc(app: ^App, assets: ^Assets) {
	ui_begin_presentation()
	defer ui_end_presentation()
	player := &app.run.player
	panel := inventory_panel_rect()
	x := i32(panel.x)
	y := i32(panel.y)
	draw_menu_panel_chrome(assets,panel)

	ui_draw_text("EQUIPPED", x + 24, y + 20, 18, COLOR_TITLE)
	draw_item_line(assets,x + 24, y + 46, player.weapon, player.has_weapon, "weapon", false)
	draw_item_line(assets,x + 24, y + 86, player.armor, player.has_armor, "armor", false)

	ui_draw_text(fmt.ctprintf("BAG  %v / %v", player.bag_count, BAG_CAPACITY), x + 24, y + 124, 18, COLOR_TITLE)
	mouse := ui_screen_to_design(rl.GetMousePosition())
	for mode in Inventory_Sort_Mode {
		rect := inventory_sort_chip_rect(mode)
		active := mode == app.inv_sort_mode
		hovered := app.input_modality != .Touch && rl.CheckCollisionPointRec(mouse, rect)
		if active || hovered {
			fill := COLOR_ROW_SELECTED
			if !active do fill = rl.Fade(COLOR_ROW_SELECTED, 0.65)
			rl.DrawRectangleRec(rect, fill)
		}
		rl.DrawRectangleLinesEx(rect, 1, active ? COLOR_TITLE : COLOR_TEXT_DIM)
		label := inventory_sort_label(mode)
		ui_draw_text(
			label,
			i32(rect.x + (rect.width - f32(ui_measure_text(label, 11))) * 0.5),
			i32(rect.y + 7),
			11,
			active ? COLOR_TITLE : COLOR_TEXT_DIM,
		)
	}
	if player.bag_count == 0 {
		ui_draw_text("empty - equipment you pick up lands here", x + 24, y + 152, 14, COLOR_TEXT_DIM)
	}
	visible_end := min(player.bag_count, app.inv_scroll + INVENTORY_VISIBLE_ROWS)
	for i in app.inv_scroll ..< visible_end {
		row := i - app.inv_scroll
		// draw_item_line puts its 28px icon at row_y-5; +10 centers it in the
		// 38px row (rect.y+146) with the label riding one pixel above center.
		row_y := y + 156 + i32(row) * 40
		row_rect:=inventory_row_rect(row)
		selected:=ui_navigation_selected(app,i==app.inv_index)
		row_content:=draw_menu_row_chrome(assets,row_rect,selected)
		draw_item_line(
			assets,i32(row_content.x),row_y,player.bag[i],true,"",selected,
			content_right=i32(row_content.x+row_content.width),
		)
	}
	if player.bag_count > 0 {
		draw_item_detail_panel(assets,player.bag[app.inv_index], x, y)
	}

	if player.bag_count > INVENTORY_VISIBLE_ROWS {
		ui_draw_text(
			fmt.ctprintf("showing %v-%v", app.inv_scroll + 1, visible_end),
			x + 24, y + 108, 11, COLOR_TEXT_DIM,
		)
	}
	ui_draw_text("Up/Down | Enter/E or 1-9: use/equip", x + 24, y + 496, 11, COLOR_TEXT_DIM)
	ui_draw_text("Tab/S: sort | Del/Shift+1-9: drop | I/Esc", x + 24, y + 515, 11, COLOR_TEXT_DIM)
}

@(private = "file")
draw_item_detail_panel :: proc(assets: ^Assets,item: Item, inventory_x, inventory_y: i32) {
	w: i32 = 324
	h: i32 = 372
	pad: i32 = 22
	x := max(i32(8), inventory_x-w-16)
	y := inventory_y
	left := x + pad
	sub := left + 8 // indented affix/stat list entries
	draw_menu_panel_chrome(assets,{f32(x),f32(y),f32(w),f32(h)})
	ui_draw_text("SELECTED ITEM",left,y+26,14,COLOR_TITLE)
	visible_rarity := item_visible_rarity(item)
	color := rl.Color(RARITIES[visible_rarity].color)
	icon_offset:i32=0
	if draw_item_icon(assets,item,{f32(left),f32(y+49),28,28},rl.WHITE) do icon_offset=34
	ui_draw_text(fmt.ctprintf("%s%s",item.cursed && !item.unidentified ? "! " : "",item_display_name(item)),left+icon_offset,y+52,18,color)
	kind: cstring = "item"
	#partial switch item.kind {
	case .Weapon: kind = "weapon"
	case .Armor: kind = "armor"
	case .Heal_Potion, .Mana_Potion: kind = "potion"
	case .Identify_Scroll, .Remove_Curse_Scroll: kind = "scroll"
	}
	ui_draw_text(fmt.ctprintf("%s  %s",RARITIES[visible_rarity].name,kind),left,y+76,12,COLOR_TEXT_DIM)
	if item.unidentified {
		ui_draw_text("Affixes and rolls hidden until identified.",left,y+108,12,COLOR_TEXT)
		return
	}
	if item.kind != .Weapon && item.kind != .Armor do return

	line_y := y+102
	if item.kind == .Weapon {
		ui_draw_text(fmt.ctprintf("Power %v  |  %s damage",item_power(item),DAMAGE_TYPE_NAMES[player_weapon_type_for_item(item)]),left,line_y,13,COLOR_TEXT)
	} else {
		ui_draw_text(fmt.ctprintf("Defense %v  |  %s ward",item_defense(item),DAMAGE_TYPE_NAMES[item.typed ? item.damage_type : .Physical]),left,line_y,13,COLOR_TEXT)
	}
	line_y += 24
	if item.affix_count > 0 {
		ui_draw_text("AFFIXES",left,line_y,11,COLOR_TITLE)
		line_y += 16
		for i in 0 ..< item.affix_count {
			ui_draw_text(fmt.ctprintf("- %s",AFFIX_DEFS[item.affixes[i].kind].name),sub,line_y,12,COLOR_TEXT_DIM)
			line_y += 15
		}
	}
	if item.attack_speed != 0 || item.cast_speed != 0 || item.move_speed != 0 || item.thorns != 0 || item.lifesteal != 0 {
		line_y += 4
		ui_draw_text("ROLLED STATS",left,line_y,11,COLOR_TITLE)
		line_y += 16
		if item.attack_speed != 0 {
			sign: cstring = item.attack_speed > 0 ? "+" : ""
			ui_draw_text(fmt.ctprintf("%s%.0f%% attack speed",sign,item.attack_speed*100),sub,line_y,12,COLOR_TEXT)
			line_y += 15
		}
		if item.cast_speed != 0 {
			sign: cstring = item.cast_speed > 0 ? "+" : ""
			ui_draw_text(fmt.ctprintf("%s%.0f%% cast speed",sign,item.cast_speed*100),sub,line_y,12,COLOR_TEXT)
			line_y += 15
		}
		if item.move_speed != 0 {
			sign: cstring = item.move_speed > 0 ? "+" : ""
			ui_draw_text(fmt.ctprintf("%s%.0f%% movement",sign,item.move_speed*100),sub,line_y,12,COLOR_TEXT)
			line_y += 15
		}
		if item.thorns != 0 {
			ui_draw_text(fmt.ctprintf("%v thorns",item.thorns),sub,line_y,12,COLOR_TEXT)
			line_y += 15
		}
		if item.lifesteal != 0 {
			ui_draw_text(fmt.ctprintf("%.0f%% lifesteal",item.lifesteal*100),sub,line_y,12,COLOR_TEXT)
			line_y += 15
		}
	}
	for effect in Proc_Effect {
		if effect == .None || (!item.proc_effects[effect] && item.proc_effect != effect) do continue
		chance: cstring = ""
		if item.proc_chance > 0 && item.proc_chance < 1 do chance = fmt.ctprintf("  %.0f%%",item.proc_chance*100)
		ui_draw_text(fmt.ctprintf("Proc: %s%s",PROC_EFFECT_NAMES[effect],chance),left,line_y,12,COLOR_TEXT)
		line_y += 15
	}
	for bonus in Skill_Bonus {
		if !item.skill_bonuses[bonus] do continue
		ui_draw_text(fmt.ctprintf("Skill: %s",SKILL_BONUS_NAMES[bonus]),left,line_y,12,COLOR_TEXT)
		line_y += 15
	}
	if item.cursed {
		ui_draw_text("Cursed bargain: stronger, slower handling.",left,min(y+h-28,line_y+4),12,rl.Color{214,92,150,255})
	}
}

@(private = "file")
player_weapon_type_for_item :: proc(item: Item) -> Damage_Type {
	return item.typed ? item.damage_type : .Physical
}

@(private = "file")
draw_item_icon :: proc(assets: ^Assets,item: Item,target: rl.Rectangle,tint:=rl.WHITE) -> bool {
	if assets==nil do return false
	key:=item.icon
	if item.unidentified {
		if item.kind==.Weapon do key="weapon"
		if item.kind==.Armor do key="armor"
	}
	icon,found:=assets.items[key]
	if !found||!icon.loaded||icon.tex.id==0 do return false
	scale:=min(target.width/f32(icon.tex.width),target.height/f32(icon.tex.height))
	width:=f32(icon.tex.width)*scale
	height:=f32(icon.tex.height)*scale
	dst:=rl.Rectangle{target.x+(target.width-width)*.5,target.y+(target.height-height)*.5,width,height}
	rl.DrawTexturePro(icon.tex,{0,0,f32(icon.tex.width),f32(icon.tex.height)},dst,{},0,tint)
	return true
}

@(private = "file")
draw_item_line :: proc(
	assets:^Assets,
	x, y: i32,
	item: Item,
	present: bool,
	slot_hint: string,
	selected: bool,
	content_right: i32 = 0,
) {
	clip_to_content := content_right > x
	if clip_to_content {
		presentation := ui_presentation()
		rl.BeginScissorMode(
			i32(f32(x)*presentation.scale),
			i32(f32(y-5)*presentation.scale),
			max(1,i32(f32(content_right-x)*presentation.scale)),
			max(1,i32(f32(40)*presentation.scale)),
		)
	}
	defer {
		if clip_to_content do rl.EndScissorMode()
	}
	if !present {
		ui_draw_text(fmt.ctprintf("- no %s -", slot_hint), x, y + 4, 14, COLOR_TEXT_DIM)
		return
	}
	visible_rarity := item_visible_rarity(item)
	color := rl.Color(RARITIES[visible_rarity].color)
	name := item_display_name(item)
	text_x:=x
	if draw_item_icon(assets,item,{f32(x),f32(y-5),28,28},rl.WHITE) do text_x+=34
	// Affixed items carry a second line; lift the pair so both stay centered
	// around the icon instead of the affix spilling past a bag row's bottom.
	name_y := !item.unidentified && item.affix_count > 0 ? y - 4 : y
	ui_draw_text(fmt.ctprintf("%s%s", item.cursed && !item.unidentified ? "! " : "", name), text_x, name_y, 16, color)

	if item.unidentified do return
	stat: cstring
	#partial switch item.kind {
	case .Weapon:
		stat = fmt.ctprintf("pow %v", item_power(item))
	case .Armor:
		stat = fmt.ctprintf("def %v", item_defense(item))
	}
	if stat != "" {
		stat_x := x+220
		if content_right > x do stat_x = min(stat_x,content_right-ui_measure_text(stat,14))
		ui_draw_text(stat,stat_x,name_y+1,14,COLOR_TEXT)
	}

	if item.affix_count > 0 {
		affix_text: cstring
		switch item.affix_count {
		case 1:
			affix_text = fmt.ctprintf("%s", AFFIX_DEFS[item.affixes[0].kind].name)
		case 2:
			affix_text = fmt.ctprintf("%s, %s", AFFIX_DEFS[item.affixes[0].kind].name, AFFIX_DEFS[item.affixes[1].kind].name)
		case:
			affix_text = fmt.ctprintf("%s, %s, %s", AFFIX_DEFS[item.affixes[0].kind].name, AFFIX_DEFS[item.affixes[1].kind].name, AFFIX_DEFS[item.affixes[2].kind].name)
		}
		ui_draw_text(affix_text, text_x, name_y + 17, 12, selected ? COLOR_TEXT : COLOR_TEXT_DIM)
	}
}

// --- MX-story modal ---------------------------------------------------------
//
// Story geometry is intentionally expressed in physical viewport pixels and
// never queries raylib. main.odin can therefore use the same rectangles for
// pointer intent, while headless tests can cover every supported resolution.
// Drawing remains in this presentation file, preserving the raylib boundary.

STORY_UI_MAX_BOARD_CELLS :: 12
STORY_UI_MAX_TEXT_LINES  :: 192

COLOR_STORY_PANEL       :: rl.Color{12, 10, 18, 248}
COLOR_STORY_LOWER       :: rl.Color{18, 15, 25, 252}
COLOR_STORY_BOARD       :: rl.Color{11, 13, 21, 244}
COLOR_STORY_ROW         :: rl.Color{29, 25, 39, 246}
COLOR_STORY_ROW_ACTIVE  :: rl.Color{57, 44, 69, 252}
COLOR_STORY_GOOD        :: rl.Color{118, 205, 146, 255}
COLOR_STORY_BAD         :: rl.Color{220, 105, 112, 255}
COLOR_STORY_MOON        :: rl.Color{154, 177, 226, 255}

STORY_PANEL_CHROME        :: UI_Chrome_Id.Menu_Panel
STORY_RELIC_SOCKET_CHROME :: UI_Chrome_Id.Story_Relic_Socket
STORY_CHOICE_ROW_CHROME   :: UI_Chrome_Id.Story_Choice_Panel

Story_UI_Rect :: struct {
	x, y:          f32,
	width, height: f32,
}

Story_Panel_UI_Layout :: struct {
	viewport:       Story_UI_Rect,
	panel:          Story_UI_Rect,
	backdrop:       Story_UI_Rect,
	lower:          Story_UI_Rect,
	portrait:       Story_UI_Rect,
	speaker:        Story_UI_Rect,
	narration:      Story_UI_Rect,
	choices:        Story_UI_Rect,
	choice_rows:    [STORY_CHOICE_COUNT]Story_UI_Rect,
	footer:         Story_UI_Rect,
	choice_count:   int,
	scale:          f32,
	title_font:     i32,
	speaker_font:   i32,
	body_font:      i32,
	choice_font:    i32,
	detail_font:    i32,
	footer_font:    i32,
}

Story_Minigame_UI_Layout :: struct {
	viewport:       Story_UI_Rect,
	panel:          Story_UI_Rect,
	title:          Story_UI_Rect,
	phase_badge:    Story_UI_Rect,
	instruction:    Story_UI_Rect,
	stats:          Story_UI_Rect,
	board_region:   Story_UI_Rect,
	board:          Story_UI_Rect,
	cells:          [STORY_UI_MAX_BOARD_CELLS]Story_UI_Rect,
	result_banner:  Story_UI_Rect,
	footer:         Story_UI_Rect,
	board_count:    int,
	columns:        int,
	rows:           int,
	scale:          f32,
	title_font:     i32,
	body_font:      i32,
	stat_font:      i32,
	cell_font:      i32,
	cell_detail_font: i32,
	footer_font:    i32,
}

Story_Modal_Kind :: enum u8 {
	None,
	Panel,
	Minigame,
}

Story_Modal_Layout :: struct {
	kind:     Story_Modal_Kind,
	panel:    Story_Panel_UI_Layout,
	minigame: Story_Minigame_UI_Layout,
}

Story_Modal_Hit_Kind :: enum u8 {
	None,
	Panel,
	Choice,
	Minigame_Cell,
}

Story_Modal_Hit :: struct {
	kind:  Story_Modal_Hit_Kind,
	index: int,
}

Story_Minigame_Cell_View :: struct {
	face_up:        bool,
	active:         bool,
	matched:        bool,
	selected:       bool,
	last_correct:   bool,
	last_incorrect: bool,
}

story_ui_rect_right :: proc(rect: Story_UI_Rect) -> f32 {
	return rect.x + rect.width
}

story_ui_rect_bottom :: proc(rect: Story_UI_Rect) -> f32 {
	return rect.y + rect.height
}

story_ui_rect_contains :: proc(rect: Story_UI_Rect, point: Vec2) -> bool {
	return rect.width > 0 && rect.height > 0 &&
		point.x >= rect.x && point.y >= rect.y &&
		point.x < story_ui_rect_right(rect) && point.y < story_ui_rect_bottom(rect)
}

story_ui_rect_contains_rect :: proc(outer, inner: Story_UI_Rect) -> bool {
	return inner.width >= 0 && inner.height >= 0 &&
		inner.x >= outer.x && inner.y >= outer.y &&
		story_ui_rect_right(inner) <= story_ui_rect_right(outer) &&
		story_ui_rect_bottom(inner) <= story_ui_rect_bottom(outer)
}

// Density caps keep 4K text comfortably large without letting a HUD-like panel
// engulf the live game. The .75 floor keeps the 640x480 typography legible.
story_ui_scale :: proc(viewport_w, viewport_h: int) -> f32 {
	width := f32(max(1, viewport_w))
	height := f32(max(1, viewport_h))
	return clamp(min(width / UI_REFERENCE_WIDTH, height / UI_REFERENCE_HEIGHT), f32(.75), f32(2))
}

story_panel_ui_layout :: proc(
	viewport_w, viewport_h: int,
	requested_choice_count: int,
) -> (layout: Story_Panel_UI_Layout) {
	width := f32(max(1, viewport_w))
	height := f32(max(1, viewport_h))
	scale := story_ui_scale(viewport_w, viewport_h)
	margin := clamp(16 * scale, f32(8), f32(40))
	panel_w := min(max(f32(1), width - margin * 2), 1040 * scale)
	panel_h := min(max(f32(1), height - margin * 2), 620 * scale)
	panel := Story_UI_Rect{(width - panel_w) * .5, (height - panel_h) * .5, panel_w, panel_h}
	panel_insets := UI_CHROME_DEFS[STORY_PANEL_CHROME].content_insets
	frame_left := f32(panel_insets[0])
	frame_top := f32(panel_insets[1])
	frame_right := f32(panel_insets[2])
	frame_bottom := f32(panel_insets[3])
	content_w := max(f32(1), panel.width - frame_left - frame_right)
	content_h := max(f32(1), panel.height - frame_top - frame_bottom)
	backdrop_h := max(f32(1), min(content_h, panel.height * .36))
	backdrop := Story_UI_Rect{
		panel.x + frame_left, panel.y + frame_top,
		content_w, backdrop_h,
	}
	lower_y := story_ui_rect_bottom(backdrop)
	lower := Story_UI_Rect{
		panel.x + frame_left, lower_y,
		content_w,
		max(f32(1), story_ui_rect_bottom(panel) - frame_bottom - lower_y),
	}
	pad := clamp(16 * scale, f32(10), f32(32))
	gap := clamp(7 * scale, f32(4), f32(14))
	inner_x := lower.x + pad
	inner_y := lower.y + pad
	inner_w := max(f32(1), lower.width - pad * 2)
	inner_bottom := story_ui_rect_bottom(lower) - pad
	footer_h := clamp(18 * scale, f32(14), f32(36))
	main_bottom := max(inner_y, inner_bottom - footer_h - gap * .5)

	choice_count := clamp(requested_choice_count, 0, STORY_CHOICE_COUNT)
	choice_gap := max(f32(3), 6 * scale)
	choice_y := main_bottom
	choice_total: f32
	row_h: f32
	if choice_count > 0 {
		row_h = clamp(58 * scale, f32(40), f32(116))
		choice_total = row_h * f32(choice_count) + choice_gap * f32(choice_count - 1)
		max_choice_total := max(f32(choice_count * 32), (main_bottom - inner_y) * .58)
		if choice_total > max_choice_total {
			row_h = max(f32(32), (max_choice_total - choice_gap * f32(choice_count - 1)) / f32(choice_count))
			choice_total = row_h * f32(choice_count) + choice_gap * f32(choice_count - 1)
		}
		choice_y = main_bottom - choice_total
	}
	choices := Story_UI_Rect{inner_x, choice_y, inner_w, choice_total}
	text_bottom := choice_count > 0 ? choice_y - gap : main_bottom
	text_height := max(f32(1), text_bottom - inner_y)
	portrait_w := min(inner_w * .21, text_height * .78)
	portrait_w = max(min(54 * scale, inner_w * .18), portrait_w)
	portrait_w = min(portrait_w, inner_w * .27)
	portrait := Story_UI_Rect{inner_x, inner_y, portrait_w, text_height}
	text_x := story_ui_rect_right(portrait) + gap
	text_w := max(f32(1), inner_x + inner_w - text_x)
	speaker_h := min(text_height, clamp(21 * scale, f32(16), f32(38)))
	speaker := Story_UI_Rect{text_x, inner_y, text_w, speaker_h}
	narration_y := story_ui_rect_bottom(speaker) + gap * .35
	narration := Story_UI_Rect{text_x, narration_y, text_w, max(f32(1), text_bottom - narration_y)}
	for index in 0 ..< choice_count {
		layout.choice_rows[index] = {
			inner_x,
			choice_y + f32(index) * (row_h + choice_gap),
			inner_w,
			row_h,
		}
	}

	layout.viewport = {0, 0, width, height}
	layout.panel = panel
	layout.backdrop = backdrop
	layout.lower = lower
	layout.portrait = portrait
	layout.speaker = speaker
	layout.narration = narration
	layout.choices = choices
	layout.footer = {inner_x, main_bottom + gap * .35, inner_w, max(f32(1), inner_bottom - main_bottom - gap * .35)}
	layout.choice_count = choice_count
	layout.scale = scale
	layout.title_font = i32(clamp(25 * scale, f32(17), f32(46)))
	layout.speaker_font = i32(clamp(18 * scale, f32(13), f32(34)))
	layout.body_font = i32(clamp(18 * scale, f32(13), f32(32)))
	layout.choice_font = i32(clamp(17 * scale, f32(13), f32(30)))
	layout.detail_font = i32(clamp(13 * scale, f32(10), f32(23)))
	layout.footer_font = i32(clamp(11 * scale, f32(9), f32(19)))
	return
}

story_minigame_ui_layout :: proc(
	viewport_w, viewport_h, requested_board_count, requested_columns: int,
) -> (layout: Story_Minigame_UI_Layout) {
	width := f32(max(1, viewport_w))
	height := f32(max(1, viewport_h))
	scale := story_ui_scale(viewport_w, viewport_h)
	margin := clamp(16 * scale, f32(8), f32(40))
	panel_w := min(max(f32(1), width - margin * 2), 860 * scale)
	panel_h := min(max(f32(1), height - margin * 2), 600 * scale)
	panel := Story_UI_Rect{(width - panel_w) * .5, (height - panel_h) * .5, panel_w, panel_h}
	pad := clamp(17 * scale, f32(10), f32(34))
	gap := clamp(8 * scale, f32(5), f32(16))
	inner_x := panel.x + pad
	inner_y := panel.y + pad
	inner_w := max(f32(1), panel.width - pad * 2)
	inner_bottom := story_ui_rect_bottom(panel) - pad
	badge_w := min(inner_w * .30, 128 * scale)
	title_h := clamp(36 * scale, f32(27), f32(66))
	instruction_h := clamp(31 * scale, f32(24), f32(56))
	stats_h := clamp(34 * scale, f32(26), f32(62))
	footer_h := clamp(20 * scale, f32(15), f32(38))

	title := Story_UI_Rect{inner_x, inner_y, max(f32(1), inner_w - badge_w - gap), title_h}
	phase_badge := Story_UI_Rect{inner_x + inner_w - badge_w, inner_y, badge_w, title_h}
	instruction := Story_UI_Rect{inner_x, story_ui_rect_bottom(title) + gap * .25, inner_w, instruction_h}
	stats := Story_UI_Rect{inner_x, story_ui_rect_bottom(instruction) + gap * .25, inner_w, stats_h}
	footer := Story_UI_Rect{inner_x, inner_bottom - footer_h, inner_w, footer_h}
	board_top := story_ui_rect_bottom(stats) + gap * .5
	board_region := Story_UI_Rect{inner_x, board_top, inner_w, max(f32(1), footer.y - gap * .5 - board_top)}

	board_count := clamp(requested_board_count, 0, STORY_UI_MAX_BOARD_CELLS)
	columns := requested_columns
	if columns <= 0 do columns = board_count == 8 ? 4 : 3
	columns = clamp(columns, 1, max(1, board_count))
	rows := board_count > 0 ? (board_count + columns - 1) / columns : 0
	cell_gap := clamp(8 * scale, f32(5), f32(17))
	cell_size: f32
	board: Story_UI_Rect
	if board_count > 0 && rows > 0 {
		available_cell_w := (board_region.width - cell_gap * f32(columns - 1)) / f32(columns)
		available_cell_h := (board_region.height - cell_gap * f32(rows - 1)) / f32(rows)
		cell_size = max(f32(1), min(min(available_cell_w, available_cell_h), 118 * scale))
		board_w := cell_size * f32(columns) + cell_gap * f32(columns - 1)
		board_h := cell_size * f32(rows) + cell_gap * f32(rows - 1)
		board = {
			board_region.x + (board_region.width - board_w) * .5,
			board_region.y + (board_region.height - board_h) * .5,
			board_w,
			board_h,
		}
		for index in 0 ..< board_count {
			column := index % columns
			row := index / columns
			layout.cells[index] = {
				board.x + f32(column) * (cell_size + cell_gap),
				board.y + f32(row) * (cell_size + cell_gap),
				cell_size,
				cell_size,
			}
		}
	}

	layout.viewport = {0, 0, width, height}
	layout.panel = panel
	layout.title = title
	layout.phase_badge = phase_badge
	layout.instruction = instruction
	layout.stats = stats
	layout.board_region = board_region
	layout.board = board
	layout.result_banner = {
		board_region.x + board_region.width * .08,
		board_region.y + board_region.height * .36,
		board_region.width * .84,
		board_region.height * .28,
	}
	layout.footer = footer
	layout.board_count = board_count
	layout.columns = columns
	layout.rows = rows
	layout.scale = scale
	layout.title_font = i32(clamp(27 * scale, f32(19), f32(48)))
	layout.body_font = i32(clamp(16 * scale, f32(12), f32(29)))
	layout.stat_font = i32(clamp(14 * scale, f32(11), f32(25)))
	layout.cell_font = i32(clamp(22 * scale, f32(16), f32(40)))
	layout.cell_detail_font = i32(clamp(11 * scale, f32(9), f32(19)))
	layout.footer_font = i32(clamp(11 * scale, f32(9), f32(19)))
	return
}

story_modal_layout :: proc(app: ^App, viewport_w, viewport_h: int) -> (layout: Story_Modal_Layout) {
	if app == nil do return
	if app_story_minigame_active(app) {
		columns, _ := app_story_minigame_grid(app)
		layout.kind = .Minigame
		layout.minigame = story_minigame_ui_layout(
			viewport_w, viewport_h, app.story_minigame.board_count, columns,
		)
		return
	}
	if app_story_panel_active(app) {
		choices := app_story_panel_choices(app)
		layout.kind = .Panel
		layout.panel = story_panel_ui_layout(viewport_w, viewport_h, choices.count)
	}
	return
}

story_panel_ui_choice_at :: proc(
	layout: ^Story_Panel_UI_Layout,
	point: Vec2,
) -> (index: int, found: bool) {
	if layout == nil do return 0, false
	for row in 0 ..< layout.choice_count {
		if story_ui_rect_contains(layout.choice_rows[row], point) do return row, true
	}
	return 0, false
}

story_minigame_ui_cell_at :: proc(
	layout: ^Story_Minigame_UI_Layout,
	point: Vec2,
) -> (index: int, found: bool) {
	if layout == nil do return 0, false
	for cell in 0 ..< layout.board_count {
		if story_ui_rect_contains(layout.cells[cell], point) do return cell, true
	}
	return 0, false
}

story_panel_choice_at :: proc(
	app: ^App,
	viewport_w, viewport_h: int,
	point: Vec2,
) -> (index: int, found: bool) {
	if !app_story_panel_active(app) do return 0, false
	choices := app_story_panel_choices(app)
	layout := story_panel_ui_layout(viewport_w, viewport_h, choices.count)
	return story_panel_ui_choice_at(&layout, point)
}

story_minigame_cell_at :: proc(
	app: ^App,
	viewport_w, viewport_h: int,
	point: Vec2,
) -> (index: int, found: bool) {
	if !app_story_minigame_active(app) do return 0, false
	columns, _ := app_story_minigame_grid(app)
	layout := story_minigame_ui_layout(viewport_w, viewport_h, app.story_minigame.board_count, columns)
	return story_minigame_ui_cell_at(&layout, point)
}

// High-level pointer seam for main. A Choice/Minigame_Cell hit supplies the
// Intent.menu_index; Panel means pointer_confirm without an index (reveal,
// continue, or Ready). Outside clicks deliberately fall through to None.
story_modal_hit_test :: proc(
	app: ^App,
	viewport_w, viewport_h: int,
	point: Vec2,
) -> Story_Modal_Hit {
	if app == nil do return {}
	if app_story_minigame_active(app) {
		columns, _ := app_story_minigame_grid(app)
		layout := story_minigame_ui_layout(viewport_w, viewport_h, app.story_minigame.board_count, columns)
		if cell, found := story_minigame_ui_cell_at(&layout, point); found {
			return {.Minigame_Cell, cell}
		}
		if app.story_minigame.phase == .Ready && story_ui_rect_contains(layout.panel, point) {
			return {.Panel, -1}
		}
		return {}
	}
	if app_story_panel_active(app) {
		choices := app_story_panel_choices(app)
		layout := story_panel_ui_layout(viewport_w, viewport_h, choices.count)
		if app_story_panel_narration_complete(app) {
			if row, found := story_panel_ui_choice_at(&layout, point); found {
				return {.Choice, row}
			}
			if choices.count == 0 && story_ui_rect_contains(layout.panel, point) {
				return {.Panel, -1}
			}
		} else if story_ui_rect_contains(layout.panel, point) {
			return {.Panel, -1}
		}
	}
	return {}
}

story_minigame_cell_view :: proc(
	state: ^Story_Minigame_State,
	cell, cursor: int,
) -> (view: Story_Minigame_Cell_View) {
	if state == nil || cell < 0 || cell >= state.board_count do return
	view.selected = cell == cursor && (state.phase == .Ready || state.phase == .Play)
	view.matched = state.matched[cell]
	view.last_correct = cell == state.last_cell && state.last_correct
	view.last_incorrect = cell == state.last_cell && !state.last_correct && state.last_cell >= 0
	switch state.phase {
	case .Ready:
		view.face_up = false
	case .Preview:
		view.face_up = true
		if state.kind == .Bind_The_Page do view.active = cell == story_minigame_preview_cell(state)
		if state.kind == .Wake_The_Moonbloom do view.active = cell == state.active_cell
	case .Play:
		switch state.kind {
		case .Bind_The_Page:
			view.face_up = true
		case .Wake_The_Moonbloom:
			view.face_up = true
			view.active = cell == state.active_cell
		case .Mirror_The_Unlost:
			view.face_up = view.matched
			for index in 0 ..< state.revealed_count {
				if state.revealed[index] == cell do view.face_up = true
			}
		case .None:
		}
	case .Result:
		view.face_up = true
	}
	return
}

@(private = "file")
story_ui_ray_rect :: proc(rect: Story_UI_Rect) -> rl.Rectangle {
	return {rect.x, rect.y, rect.width, rect.height}
}

@(private = "file")
story_ui_accent :: proc(app: ^App) -> rl.Color {
	if app != nil && app.run.story_runtime.initialized do return rl.Color(app.run.story.accent)
	return COLOR_TITLE
}

@(private = "file")
story_ui_draw_texture_cover :: proc(
	asset: ^Story_Texture_Asset,
	target: Story_UI_Rect,
	tint := rl.WHITE,
) -> bool {
	if asset == nil || !asset.valid || asset.tex.id == 0 || target.width <= 0 || target.height <= 0 do return false
	source := rl.Rectangle{0, 0, f32(asset.tex.width), f32(asset.tex.height)}
	source_aspect := source.width / max(f32(1), source.height)
	target_aspect := target.width / max(f32(1), target.height)
	if source_aspect > target_aspect {
		cropped_w := source.height * target_aspect
		source.x = (source.width - cropped_w) * .5
		source.width = cropped_w
	} else if source_aspect < target_aspect {
		cropped_h := source.width / target_aspect
		source.y = (source.height - cropped_h) * .5
		source.height = cropped_h
	}
	rl.DrawTexturePro(asset.tex, source, story_ui_ray_rect(target), {}, 0, tint)
	return true
}

story_ui_texture_contain_rect :: proc(
	source_width, source_height: f32,
	target: Story_UI_Rect,
) -> Story_UI_Rect {
	if source_width <= 0 || source_height <= 0 || target.width <= 0 || target.height <= 0 do return {}
	scale := min(target.width / source_width, target.height / source_height)
	width := source_width * scale
	height := source_height * scale
	return {
		target.x + (target.width - width) * .5,
		target.y + (target.height - height) * .5,
		width,
		height,
	}
}

@(private = "file")
story_ui_draw_texture_contain :: proc(
	asset: ^Story_Texture_Asset,
	target: Story_UI_Rect,
	tint := rl.WHITE,
) -> bool {
	if asset == nil || !asset.valid || asset.tex.id == 0 || target.width <= 0 || target.height <= 0 do return false
	destination := story_ui_texture_contain_rect(f32(asset.tex.width), f32(asset.tex.height), target)
	rl.DrawTexturePro(
		asset.tex,
		{0, 0, f32(asset.tex.width), f32(asset.tex.height)},
		story_ui_ray_rect(destination), {}, 0, tint,
	)
	return true
}

@(private = "file")
story_ui_draw_cinematic_backdrop :: proc(
	asset: ^Story_Texture_Asset,
	target: Story_UI_Rect,
	accent: rl.Color,
) -> (art_rect: Story_UI_Rect, drawn: bool) {
	art_rect = target
	if asset == nil || !asset.valid || asset.tex.id == 0 || target.width <= 0 || target.height <= 0 do return

	// The cover layer extends the scene into the panoramic banner. It is kept
	// deliberately subdued so the complete, undistorted foreground art remains
	// the focal plane rather than competing with a duplicate composition.
	_ = story_ui_draw_texture_cover(asset, target, rl.Color{112, 104, 124, 255})
	rl.DrawRectangleRec(story_ui_ray_rect(target), rl.Color{5, 4, 9, 118})

	art_rect = story_ui_texture_contain_rect(f32(asset.tex.width), f32(asset.tex.height), target)
	left_fill := max(f32(0), art_rect.x - target.x)
	right_x := story_ui_rect_right(art_rect)
	right_fill := max(f32(0), story_ui_rect_right(target) - right_x)
	if left_fill > 0 {
		rl.DrawRectangleGradientH(
			i32(target.x), i32(target.y), max(i32(1), i32(left_fill)), max(i32(1), i32(target.height)),
			rl.Color{3, 3, 7, 178}, rl.Color{5, 4, 9, 54},
		)
	}
	if right_fill > 0 {
		rl.DrawRectangleGradientH(
			i32(right_x), i32(target.y), max(i32(1), i32(right_fill)), max(i32(1), i32(target.height)),
			rl.Color{5, 4, 9, 54}, rl.Color{3, 3, 7, 178},
		)
	}

	separator := max(f32(1), target.height * .012)
	rl.DrawRectangleRec(
		{art_rect.x - separator, art_rect.y, art_rect.width + separator * 2, art_rect.height},
		rl.Color{2, 2, 5, 214},
	)
	rl.DrawTexturePro(
		asset.tex,
		{0, 0, f32(asset.tex.width), f32(asset.tex.height)},
		story_ui_ray_rect(art_rect), {}, 0, rl.WHITE,
	)
	rl.DrawRectangleLinesEx(story_ui_ray_rect(art_rect), separator, rl.Fade(accent, .68))
	drawn = true
	return
}

@(private = "file")
story_ui_draw_fallback_backdrop :: proc(rect: Story_UI_Rect, accent: rl.Color) {
	rl.DrawRectangleGradientV(
		i32(rect.x), i32(rect.y), max(i32(1), i32(rect.width)), max(i32(1), i32(rect.height)),
		rl.Color{24, 20, 34, 255}, rl.Color{7, 8, 14, 255},
	)
	for index in 0 ..< 6 {
		x := rect.x + rect.width * (f32(index) + .5) / 6
		y := rect.y + rect.height * (.26 + f32(index & 1) * .18)
		rl.DrawCircleV({x, y}, max(f32(3), rect.height * (.035 + f32(index % 3) * .008)), rl.Fade(accent, .16))
		rl.DrawLineEx({x, y + rect.height * .09}, {x, story_ui_rect_bottom(rect)}, max(f32(1), rect.height * .006), rl.Fade(accent, .10))
	}
}

@(private = "file")
story_ui_backdrop_asset :: proc(app: ^App, assets: ^Assets) -> ^Story_Texture_Asset {
	if app == nil || assets == nil do return nil
	identity := app_story_art_identity(app)
	switch identity.panel_kind {
	case .Omen:
		if identity.has_motif do return story_omen_backdrop_asset(assets, identity.motif)
	case .Guest:
		if identity.has_guest do return story_guest_backdrop_asset(assets, identity.guest_role)
	case .Epilogue:
		if identity.has_ending do return story_ending_panel_asset(assets, identity.archetype, identity.ending_verb)
		if identity.has_motif do return story_omen_backdrop_asset(assets, identity.motif)
	case .Soul:
		return story_lossless_soul_backdrop_asset(assets)
	case .None:
	}
	return nil
}

@(private = "file")
story_ui_fit_font :: proc(text: string, width: f32, preferred, minimum: i32) -> i32 {
	font := max(minimum, preferred)
	for font > minimum && ui_measure_text(fmt.ctprintf("%s", text), font) > i32(max(f32(1), width)) do font -= 1
	return font
}

@(private = "file")
story_ui_draw_centered :: proc(text: string, rect: Story_UI_Rect, preferred, minimum: i32, color: rl.Color) {
	font := story_ui_fit_font(text, rect.width, preferred, minimum)
	label := fmt.ctprintf("%s", text)
	text_w := ui_measure_text(label, font)
	ui_draw_text(label, i32(rect.x + (rect.width - f32(text_w)) * .5), i32(rect.y + (rect.height - f32(font)) * .5), font, color)
}

Story_UI_Text_Line :: struct {
	start, end: int,
}

@(private = "file")
story_ui_utf8_width :: proc(text: string, index: int) -> int {
	if index < 0 || index >= len(text) do return 0
	value := u8(text[index])
	if value < 0x80 do return 1
	if value & 0xe0 == 0xc0 && index + 1 < len(text) do return 2
	if value & 0xf0 == 0xe0 && index + 2 < len(text) do return 3
	if value & 0xf8 == 0xf0 && index + 3 < len(text) do return 4
	return 1
}

@(private = "file")
story_ui_space :: proc(value: u8) -> bool {
	return value == ' ' || value == '\t' || value == '\r'
}

@(private = "file")
story_ui_add_text_line :: proc(
	lines: ^[STORY_UI_MAX_TEXT_LINES]Story_UI_Text_Line,
	count: ^int,
	text: string,
	start, requested_end: int,
) -> bool {
	if count^ >= len(lines^) do return false
	end := clamp(requested_end, start, len(text))
	for end > start && story_ui_space(u8(text[end - 1])) do end -= 1
	lines^[count^] = {start, end}
	count^ += 1
	return true
}

@(private = "file")
story_ui_long_word_end :: proc(text: string, start, end: int, width: f32, font: i32) -> int {
	cursor := start
	last := start
	for cursor < end {
		next := min(end, cursor + max(1, story_ui_utf8_width(text, cursor)))
		measured := ui_measure_text(fmt.ctprintf("%s", text[start:next]), font)
		if f32(measured) > width && last > start do break
		last = next
		cursor = next
		if f32(measured) > width do break
	}
	return max(start + 1, last)
}

@(private = "file")
story_ui_wrap_text :: proc(
	text: string,
	width: f32,
	font: i32,
	lines: ^[STORY_UI_MAX_TEXT_LINES]Story_UI_Text_Line,
) -> (count: int) {
	cursor := 0
	for cursor < len(text) && count < len(lines^) {
		if text[cursor] == '\n' {
			_ = story_ui_add_text_line(lines, &count, text, cursor, cursor)
			cursor += 1
			continue
		}
		for cursor < len(text) && story_ui_space(u8(text[cursor])) do cursor += 1
		if cursor >= len(text) do break
		if text[cursor] == '\n' do continue
		line_start := cursor
		line_end := cursor
		scan := cursor
		emitted := false
		for scan < len(text) {
			if text[scan] == '\n' {
				_ = story_ui_add_text_line(lines, &count, text, line_start, line_end)
				cursor = scan + 1
				emitted = true
				break
			}
			for scan < len(text) && story_ui_space(u8(text[scan])) do scan += 1
			if scan >= len(text) do break
			if text[scan] == '\n' do continue
			word_start := scan
			for scan < len(text) && text[scan] != '\n' && !story_ui_space(u8(text[scan])) {
				scan += max(1, story_ui_utf8_width(text, scan))
			}
			word_end := scan
			measured := ui_measure_text(fmt.ctprintf("%s", text[line_start:word_end]), font)
			if f32(measured) <= width {
				line_end = word_end
				continue
			}
			if line_end > line_start {
				_ = story_ui_add_text_line(lines, &count, text, line_start, line_end)
				cursor = word_start
				emitted = true
				break
			}
			split := story_ui_long_word_end(text, line_start, word_end, width, font)
			_ = story_ui_add_text_line(lines, &count, text, line_start, split)
			cursor = split
			emitted = true
			break
		}
		if !emitted {
			_ = story_ui_add_text_line(lines, &count, text, line_start, line_end)
			cursor = len(text)
		}
	}
	return
}

@(private = "file")
story_ui_draw_narration_tail :: proc(
	text: string,
	rect: Story_UI_Rect,
	font: i32,
	scale: f32,
	complete: bool,
	elapsed: f32,
) {
	line_height := f32(font) + max(f32(3), 4 * scale)
	max_lines := max(1, int(rect.height / line_height))
	lines: [STORY_UI_MAX_TEXT_LINES]Story_UI_Text_Line
	line_count := story_ui_wrap_text(text, max(f32(1), rect.width - 3 * scale), font, &lines)
	first := max(0, line_count - max_lines)
	rl.BeginScissorMode(i32(rect.x), i32(rect.y), max(i32(1), i32(rect.width)), max(i32(1), i32(rect.height)))
	defer rl.EndScissorMode()
	for line_index in first ..< line_count {
		line := lines[line_index]
		line_text := fmt.ctprintf("%s", text[line.start:line.end])
		y := rect.y + f32(line_index - first) * line_height
		ui_draw_text(line_text, i32(rect.x), i32(y), font, COLOR_TEXT)
	}
	if first > 0 {
		marker: cstring = "Up earlier"
		marker_font := max(i32(8), font - 4)
		ui_draw_text(marker, i32(story_ui_rect_right(rect)) - ui_measure_text(marker, marker_font), i32(rect.y), marker_font, rl.Fade(COLOR_TITLE, .82))
	}
	if !complete && int(elapsed * 4) & 1 == 0 {
		cursor_x := rect.x
		cursor_y := rect.y
		if line_count > 0 {
			last := lines[line_count - 1]
			cursor_x += f32(ui_measure_text(fmt.ctprintf("%s", text[last.start:last.end]), font)) + 2 * scale
			cursor_y += f32(line_count - 1 - first) * line_height
		}
		rl.DrawRectangle(i32(cursor_x), i32(cursor_y + f32(font) * .18), max(i32(2), i32(2 * scale)), max(i32(8), i32(f32(font) * .72)), COLOR_TITLE)
	}
}

@(private = "file")
story_ui_panel_heading :: proc(app: ^App) -> string {
	if app == nil do return "STORY"
	switch app.story_panel.kind {
	case .Omen:
		if beat := story_current_beat(&app.run); beat != nil do return story_beat_title(beat)
		return "OMEN"
	case .Guest:
		return "A WAYWARD GUEST"
	case .Epilogue:
		return "THE LAST LEDGER"
	case .Soul:
		return "HALL OF UNLOST ECHOES"
	case .None:
	}
	return "STORY"
}

@(private = "file")
story_ui_draw_panel_portrait :: proc(
	app: ^App,
	assets: ^Assets,
	layout: ^Story_Panel_UI_Layout,
	accent: rl.Color,
) {
	rect := layout.portrait
	rl.DrawRectangleRounded(story_ui_ray_rect(rect), .08, 6, rl.Color{8, 7, 13, 242})
	rl.DrawRectangleRoundedLinesEx(story_ui_ray_rect(rect), .08, 6, max(f32(1), layout.scale), rl.Fade(accent, .72))
	inner := Story_UI_Rect{rect.x + 5 * layout.scale, rect.y + 5 * layout.scale, max(f32(1), rect.width - 10 * layout.scale), max(f32(1), rect.height - 10 * layout.scale)}
	identity := app_story_art_identity(app)
	if identity.has_guest && story_ui_draw_texture_contain(
		story_guest_portrait_asset(assets, identity.guest_role, identity.guest_variant), inner,
	) {
		return
	}
	if identity.has_relic {
		socket_size := min(inner.width * .94, inner.height * .78)
		socket_rect := Story_UI_Rect{
			inner.x + (inner.width - socket_size) * .5,
			inner.y + (inner.height - socket_size) * .5,
			socket_size,
			socket_size,
		}
		rl.DrawRectangleRounded(story_ui_ray_rect(socket_rect), .12, 8, rl.Color{5, 5, 10, 244})
		socket_asset := ui_chrome_asset(assets, STORY_RELIC_SOCKET_CHROME)
		_ = draw_ui_chrome(socket_asset, story_ui_ray_rect(socket_rect))
		icon_well := story_ui_ray_rect(socket_rect)
		if authored_well, found := ui_chrome_content_rect(socket_asset, icon_well); found {
			icon_well = authored_well
		}
		icon_size := min(icon_well.width, icon_well.height) * .72
		icon_rect := Story_UI_Rect{
			icon_well.x + (icon_well.width - icon_size) * .5,
			icon_well.y + (icon_well.height - icon_size) * .5,
			icon_size,
			icon_size,
		}
		if story_ui_draw_texture_contain(story_relic_icon_asset(assets, identity.relic), icon_rect) do return
	}
	rl.DrawCircleV(
		{rect.x + rect.width * .5, rect.y + rect.height * .43},
		min(rect.width, rect.height) * .22,
		rl.Fade(accent, .24),
	)
	speaker := app_story_current_speaker(app)
	initial: cstring = "?"
	if len(speaker) > 0 do initial = fmt.ctprintf("%c", speaker[0])
	font := i32(clamp(min(rect.width, rect.height) * .28, f32(14), f32(54)))
	ui_draw_text(initial, i32(rect.x + rect.width * .5) - ui_measure_text(initial, font) / 2, i32(rect.y + rect.height * .43 - f32(font) * .5), font, accent)
}

@(private = "file")
story_ui_draw_choice_row :: proc(
	assets: ^Assets,
	choice: Story_Panel_Choice,
	rect: Story_UI_Rect,
	layout: ^Story_Panel_UI_Layout,
	selected, enabled: bool,
	accent: rl.Color,
) {
	fill := selected ? COLOR_STORY_ROW_ACTIVE : COLOR_STORY_ROW
	if !enabled do fill = rl.Fade(fill, .58)
	row_tint := selected ? rl.WHITE : rl.Color{205,205,216,220}
	if !enabled do row_tint = rl.Color{142,140,150,138}
	row_asset := assets != nil ? ui_chrome_asset(assets,STORY_CHOICE_ROW_CHROME) : nil
	authored_row := row_asset != nil && draw_ui_chrome(row_asset,story_ui_ray_rect(rect),row_tint)
	row_content := story_ui_ray_rect(rect)
	if authored_row {
		if content, found := ui_chrome_content_rect(row_asset,story_ui_ray_rect(rect)); found {
			row_content = content
		}
		if selected {
			line_y := rect.y + max(f32(1), 2 * layout.scale)
			rl.DrawLineEx(
				{row_content.x,line_y},
				{row_content.x+row_content.width,line_y},
				max(f32(1),1.25*layout.scale),
				rl.Fade(accent,.76),
			)
		}
	} else {
		rl.DrawRectangleRounded(story_ui_ray_rect(rect), .10, 6, fill)
		border := accent
		if !selected do border = rl.Fade(COLOR_TEXT_DIM, enabled ? .48 : .24)
		rl.DrawRectangleRoundedLinesEx(story_ui_ray_rect(rect), .10, 6, selected ? max(f32(2), 2 * layout.scale) : max(f32(1), layout.scale), border)
	}
	cursor_rail := max(f32(12), 14 * layout.scale)
	if selected && !authored_row {
		center_y := rect.y + rect.height * .5
		rl.DrawTriangle(
			{rect.x + cursor_rail * .75, center_y},
			{rect.x + cursor_rail * .25, center_y - 5 * layout.scale},
			{rect.x + cursor_rail * .25, center_y + 5 * layout.scale},
			accent,
		)
	}
	icon_size := min(rect.height - 10 * layout.scale, 34 * layout.scale)
	icon_x := rect.x + cursor_rail + 5 * layout.scale
	if authored_row {
		socket_width := max(f32(1),row_content.x-rect.x)
		icon_x = rect.x + (socket_width-icon_size)*.5
	}
	icon_rect := Story_UI_Rect{icon_x, rect.y + (rect.height - icon_size) * .5, icon_size, icon_size}
	icon_tint := enabled ? rl.WHITE : rl.Color{150, 148, 156, 170}
	if !story_ui_draw_texture_contain(story_choice_icon_asset_for_key(assets, choice.key), icon_rect, icon_tint) {
		icon_outline := rl.Fade(accent, .9)
		if !enabled do icon_outline = rl.Fade(COLOR_TEXT_DIM, .45)
		rl.DrawCircleLinesV({icon_rect.x + icon_rect.width * .5, icon_rect.y + icon_rect.height * .5}, icon_rect.width * .38, icon_outline)
		mark: cstring = "|"
		if len(choice.key) > 0 do mark = fmt.ctprintf("%c", choice.key[0])
		mark_font := max(i32(9), i32(icon_rect.height * .48))
		ui_draw_text(mark, i32(icon_rect.x + (icon_rect.width - f32(ui_measure_text(mark, mark_font))) * .5), i32(icon_rect.y + (icon_rect.height - f32(mark_font)) * .5), mark_font, enabled ? accent : COLOR_TEXT_DIM)
	}
	text_x := story_ui_rect_right(icon_rect) + 8 * layout.scale
	text_right := story_ui_rect_right(rect) - 10 * layout.scale
	if authored_row {
		text_x = row_content.x + max(f32(4),4*layout.scale)
		text_right = row_content.x + row_content.width
	}
	text_w := max(f32(1), text_right - text_x)
	label_font := story_ui_fit_font(choice.label, text_w, layout.choice_font, max(i32(9), layout.choice_font - 5))
	has_detail := choice.detail != ""
	detail_font := has_detail ? story_ui_fit_font(choice.detail, text_w, layout.detail_font, max(i32(8), layout.detail_font - 4)) : 0
	line_gap := has_detail ? max(f32(1), layout.scale) : 0
	text_block_h := f32(label_font+detail_font)+line_gap
	label_y := row_content.y+max(f32(0), (row_content.height-text_block_h)*.5)
	detail_y := label_y+f32(label_font)+line_gap
	label_color := COLOR_TEXT
	if selected do label_color = accent
	if !enabled do label_color = rl.Fade(COLOR_TEXT_DIM, .65)
	detail_color := COLOR_TEXT_DIM
	if !enabled do detail_color = rl.Fade(COLOR_TEXT_DIM, .45)
	rl.BeginScissorMode(i32(text_x), i32(rect.y), max(i32(1), i32(text_w)), max(i32(1), i32(rect.height)))
	ui_draw_text(fmt.ctprintf("%s", choice.label), i32(text_x), i32(label_y), label_font, label_color)
	if has_detail do ui_draw_text(fmt.ctprintf("%s", choice.detail), i32(text_x), i32(detail_y), detail_font, detail_color)
	rl.EndScissorMode()
}

@(private = "file")
draw_story_panel_modal :: proc(app: ^App, assets: ^Assets, layout: ^Story_Panel_UI_Layout) {
	accent := story_ui_accent(app)
	panel := layout.panel
	shadow := Story_UI_Rect{panel.x + 5 * layout.scale, panel.y + 7 * layout.scale, panel.width, panel.height}
	rl.DrawRectangleRounded(story_ui_ray_rect(shadow), .025, 8, rl.Fade(rl.BLACK, .62))
	panel_chrome_drawn := assets != nil && draw_ui_chrome(ui_chrome_asset(assets,STORY_PANEL_CHROME),story_ui_ray_rect(panel))
	if !panel_chrome_drawn do rl.DrawRectangleRounded(story_ui_ray_rect(panel), .025, 8, COLOR_STORY_PANEL)

	art_rect, backdrop_drawn := story_ui_draw_cinematic_backdrop(story_ui_backdrop_asset(app, assets), layout.backdrop, accent)
	if !backdrop_drawn {
		story_ui_draw_fallback_backdrop(layout.backdrop, accent)
		art_rect = layout.backdrop
	}
	fade_h := art_rect.height * .38
	rl.DrawRectangleGradientV(
		i32(art_rect.x), i32(story_ui_rect_bottom(art_rect) - fade_h),
		max(i32(1), i32(art_rect.width)), max(i32(1), i32(fade_h)),
		rl.Color{0, 0, 0, 0}, rl.Color{8, 7, 13, 225},
	)
	heading := story_ui_panel_heading(app)
	heading_rect := Story_UI_Rect{
		art_rect.x + 18 * layout.scale,
		story_ui_rect_bottom(art_rect) - 42 * layout.scale,
		art_rect.width - 36 * layout.scale,
		32 * layout.scale,
	}
	heading_font := story_ui_fit_font(heading, heading_rect.width, layout.title_font, max(i32(12), layout.title_font - 8))
	ui_draw_text(fmt.ctprintf("%s", heading), i32(heading_rect.x), i32(heading_rect.y), heading_font, COLOR_TITLE)

	rl.DrawRectangleRec(story_ui_ray_rect(layout.lower), COLOR_STORY_LOWER)
	rl.DrawLineEx({layout.lower.x, layout.lower.y}, {story_ui_rect_right(layout.lower), layout.lower.y}, max(f32(1), 2 * layout.scale), rl.Fade(accent, .66))
	story_ui_draw_panel_portrait(app, assets, layout, accent)
	speaker := app_story_current_speaker(app)
	speaker_font := story_ui_fit_font(speaker, layout.speaker.width, layout.speaker_font, max(i32(10), layout.speaker_font - 5))
	ui_draw_text(fmt.ctprintf("%s", speaker), i32(layout.speaker.x), i32(layout.speaker.y), speaker_font, accent)
	visible := app_story_panel_visible_narration(app)
	complete := app_story_panel_narration_complete(app)
	story_ui_draw_narration_tail(visible, layout.narration, layout.body_font, layout.scale, complete, app.story_panel.elapsed)

	choices := app_story_panel_choices(app)
	for row in 0 ..< choices.count {
		story_ui_draw_choice_row(
			assets, choices.items[row], layout.choice_rows[row], layout,
			complete && ui_navigation_selected(app,row == app.story_panel.choice_cursor), complete, accent,
		)
	}
	footer := complete ? (choices.count > 0 ? "Up/Down choose | Enter or tap to confirm" : "Enter or tap to continue") : "Enter or tap the panel to reveal narration"
	if app.story_panel.mandatory && complete && choices.count > 0 do footer = "A choice is required | Up/Down choose | Enter or tap"
	story_ui_draw_centered(footer, layout.footer, layout.footer_font, max(i32(8), layout.footer_font - 2), COLOR_TEXT_DIM)
	if !panel_chrome_drawn {
		rl.DrawRectangleRoundedLinesEx(story_ui_ray_rect(panel), .025, 8, max(f32(1), 2 * layout.scale), rl.Fade(COLOR_TITLE, .76))
	}
}

@(private = "file")
story_ui_minigame_phase_label :: proc(phase: Story_Minigame_Phase) -> string {
	switch phase {
	case .Ready:   return "READY"
	case .Preview: return "PREVIEW"
	case .Play:    return "PLAY"
	case .Result:  return "RESULT"
	}
	return ""
}

@(private = "file")
story_ui_sigil_mark :: proc(id: Story_Sigil_Id) -> cstring {
	switch id {
	case .Key:        return "K"
	case .Clock:      return "C"
	case .Sun:        return "S"
	case .Moon:       return "M"
	case .Sword:      return "SW"
	case .Shield:     return "SH"
	case .Star:       return "*"
	case .Flame:      return "F"
	case .Serpent:    return "SS"
	case .Ouroboros:  return "O"
	case .Phoenix:    return "P"
	case .Dragon:     return "D"
	case .Cross:      return "+"
	case .Infinity:   return "OO"
	}
	return "?"
}

@(private = "file")
story_ui_minigame_socket_id :: proc(kind: Story_Minigame_Kind) -> UI_Chrome_Id {
	switch kind {
	case .Bind_The_Page:     return .Minigame_Socket_Story
	case .Wake_The_Moonbloom: return .Minigame_Socket_Garden
	case .Mirror_The_Unlost: return .Minigame_Socket_Soul
	case .None:
	}
	return .Minigame_Socket_Story
}

@(private = "file")
story_ui_draw_sigil_cell :: proc(
	assets: ^Assets,
	state: ^Story_Minigame_State,
	cell, cursor: int,
	rect: Story_UI_Rect,
	layout: ^Story_Minigame_UI_Layout,
	accent: rl.Color,
) {
	view := story_minigame_cell_view(state, cell, cursor)
	fill := rl.Color{24, 24, 38, 252}
	border := rl.Fade(COLOR_TEXT_DIM, .64)
	if view.active {
		fill = rl.Color{51, 54, 76, 255}
		border = COLOR_STORY_MOON
	}
	if view.matched {
		fill = rl.Color{28, 52, 42, 252}
		border = COLOR_STORY_GOOD
	}
	if view.last_correct do border = COLOR_STORY_GOOD
	if view.last_incorrect do border = COLOR_STORY_BAD
	if view.selected do border = accent
	rl.DrawRectangleRounded(story_ui_ray_rect(rect), .12, 7, fill)
	if assets != nil && state.kind != .None {
		socket_tint := rl.WHITE
		socket_tint.a = view.matched ? 150 : view.active || view.selected ? 255 : 208
		_ = draw_ui_chrome(
			ui_chrome_asset(assets, story_ui_minigame_socket_id(state.kind)),
			story_ui_ray_rect(rect),
			socket_tint,
		)
	}
	rl.DrawRectangleRoundedLinesEx(story_ui_ray_rect(rect), .12, 7, view.selected || view.active ? max(f32(2), 2 * layout.scale) : max(f32(1), layout.scale), border)

	center := rl.Vector2{rect.x + rect.width * .5, rect.y + rect.height * .43}
	radius := min(rect.width, rect.height) * .23
	if view.face_up {
		rl.DrawCircleV(center, radius, rl.Fade(view.active ? COLOR_STORY_MOON : accent, view.matched ? .30 : .18))
		ring_color := COLOR_STORY_MOON
		if !view.active do ring_color = rl.Fade(accent, .82)
		rl.DrawCircleLinesV(center, radius, ring_color)
		glyph_size := radius * 1.65
		glyph_target := rl.Rectangle{center.x-glyph_size*.5,center.y-glyph_size*.5,glyph_size,glyph_size}
		glyph_tint := COLOR_TEXT
		if view.active do glyph_tint = rl.WHITE
		if !view.active && view.matched do glyph_tint = rl.Fade(COLOR_STORY_GOOD,.72)
		glyph_drawn := assets != nil && draw_ui_glyph(ui_story_sigil_glyph(assets,state.board[cell]),glyph_target,glyph_tint)
		if !glyph_drawn {
			mark := story_ui_sigil_mark(state.board[cell])
			mark_font := story_ui_fit_font(string(mark), radius * 1.45, layout.cell_font, max(i32(10), layout.cell_font - 8))
			ui_draw_text(mark, i32(center.x) - ui_measure_text(mark, mark_font) / 2, i32(center.y - f32(mark_font) * .5), mark_font, glyph_tint)
		}
		name := story_minigame_sigil_name(state.board[cell])
		story_ui_draw_centered(name, {rect.x + 4 * layout.scale, rect.y + rect.height * .72, rect.width - 8 * layout.scale, rect.height * .20}, layout.cell_detail_font, max(i32(7), layout.cell_detail_font - 3), view.matched ? COLOR_STORY_GOOD : COLOR_TEXT_DIM)
	} else {
		rl.DrawCircleLinesV(center, radius, rl.Fade(COLOR_TEXT_DIM, .52))
		question: cstring = "?"
		font := max(i32(12), layout.cell_font)
		ui_draw_text(question, i32(center.x) - ui_measure_text(question, font) / 2, i32(center.y - f32(font) * .5), font, rl.Fade(COLOR_TEXT_DIM, .82))
		story_ui_draw_centered("sealed", {rect.x, rect.y + rect.height * .72, rect.width, rect.height * .20}, layout.cell_detail_font, max(i32(7), layout.cell_detail_font - 3), COLOR_TEXT_DIM)
	}
	if view.selected {
		inset := max(f32(5), 6 * layout.scale)
		rl.DrawLineEx({rect.x + inset, rect.y + inset}, {rect.x + inset * 2.2, rect.y + inset}, max(f32(1), 2 * layout.scale), accent)
		rl.DrawLineEx({rect.x + inset, rect.y + inset}, {rect.x + inset, rect.y + inset * 2.2}, max(f32(1), 2 * layout.scale), accent)
	}
}

@(private = "file")
draw_story_minigame_modal :: proc(app: ^App, assets: ^Assets, layout: ^Story_Minigame_UI_Layout) {
	state := &app.story_minigame
	accent := story_ui_accent(app)
	panel := layout.panel
	shadow := Story_UI_Rect{panel.x + 5 * layout.scale, panel.y + 7 * layout.scale, panel.width, panel.height}
	rl.DrawRectangleRounded(story_ui_ray_rect(shadow), .035, 8, rl.Fade(rl.BLACK, .64))
	rl.DrawRectangleRounded(story_ui_ray_rect(panel), .035, 8, COLOR_STORY_PANEL)
	rl.DrawRectangleRoundedLinesEx(story_ui_ray_rect(panel), .035, 8, max(f32(1), 2 * layout.scale), rl.Fade(accent, .80))

	title := story_minigame_title(state.kind)
	font := story_ui_fit_font(title, layout.title.width, layout.title_font, max(i32(14), layout.title_font - 8))
	ui_draw_text(fmt.ctprintf("%s", title), i32(layout.title.x), i32(layout.title.y + (layout.title.height - f32(font)) * .5), font, COLOR_TITLE)
	rl.DrawRectangleRounded(story_ui_ray_rect(layout.phase_badge), .16, 6, rl.Fade(accent, .16))
	rl.DrawRectangleRoundedLinesEx(story_ui_ray_rect(layout.phase_badge), .16, 6, max(f32(1), layout.scale), rl.Fade(accent, .65))
	story_ui_draw_centered(story_ui_minigame_phase_label(state.phase), layout.phase_badge, layout.stat_font, max(i32(9), layout.stat_font - 3), accent)

	instruction := story_minigame_instruction(state.kind)
	story_ui_draw_centered(instruction, layout.instruction, layout.body_font, max(i32(9), layout.body_font - 5), COLOR_TEXT)
	rl.DrawRectangleRounded(story_ui_ray_rect(layout.stats), .10, 6, rl.Color{23, 20, 32, 238})
	third := layout.stats.width / 3
	time_text: cstring
	switch state.phase {
	case .Ready:
		time_text = "Time  --"
	case .Preview:
		remaining := max(f32(0), story_minigame_preview_duration(state) - state.elapsed)
		time_text = fmt.ctprintf("Preview  %.1fs", remaining)
	case .Play:
		time_text = fmt.ctprintf("Time  %.1fs", state.time_left)
	case .Result:
		time_text = "Time  complete"
	}
	story_ui_draw_centered(string(time_text), {layout.stats.x, layout.stats.y, third, layout.stats.height}, layout.stat_font, max(i32(8), layout.stat_font - 3), COLOR_TEXT_DIM)
	story_ui_draw_centered(fmt.tprintf("Progress  %d / %d", state.score, state.goal), {layout.stats.x + third, layout.stats.y, third, layout.stats.height}, layout.stat_font, max(i32(8), layout.stat_font - 3), state.score >= state.goal ? COLOR_STORY_GOOD : COLOR_TEXT)
	story_ui_draw_centered(fmt.tprintf("Mistakes  %d", state.mistakes), {layout.stats.x + third * 2, layout.stats.y, third, layout.stats.height}, layout.stat_font, max(i32(8), layout.stat_font - 3), state.mistakes > 0 ? COLOR_STORY_BAD : COLOR_TEXT_DIM)

	rl.DrawRectangleRounded(story_ui_ray_rect(layout.board_region), .025, 8, COLOR_STORY_BOARD)
	rl.DrawRectangleRoundedLinesEx(story_ui_ray_rect(layout.board_region), .025, 8, max(f32(1), layout.scale), rl.Fade(COLOR_TEXT_DIM, .38))
	cursor:=app.input_modality==.Touch?-1:app.story_minigame_cursor
	for cell in 0 ..< layout.board_count {
		story_ui_draw_sigil_cell(assets, state, cell, cursor, layout.cells[cell], layout, accent)
	}
	if state.phase == .Result {
		won := state.outcome == .Won
		rl.DrawRectangleRounded(story_ui_ray_rect(layout.result_banner), .12, 8, rl.Fade(won ? rl.Color{17, 48, 36, 255} : rl.Color{58, 23, 31, 255}, .94))
		rl.DrawRectangleRoundedLinesEx(story_ui_ray_rect(layout.result_banner), .12, 8, max(f32(2), 2 * layout.scale), won ? COLOR_STORY_GOOD : COLOR_STORY_BAD)
		result := won ? "RITUAL HELD" : "RITUAL BROKE -- THE STORY CONTINUES"
		story_ui_draw_centered(result, layout.result_banner, layout.title_font, max(i32(12), layout.title_font - 10), won ? COLOR_STORY_GOOD : COLOR_STORY_BAD)
	}
	footer: string
	switch state.phase {
	case .Ready:   footer = "Confirm or tap a seal to begin"
	case .Preview: footer = "Watch the board"
	case .Play:    footer = "Arrows choose | Enter or tap a seal"
	case .Result:  footer = state.outcome == .Won ? "Reward secured" : "No boon -- consequences still move forward"
	}
	story_ui_draw_centered(footer, layout.footer, layout.footer_font, max(i32(8), layout.footer_font - 2), COLOR_TEXT_DIM)
}

// Renderer integration seam. Call after draw_run_scene while the raylib frame is
// open; viewport dimensions are physical pixels (normally GetScreenWidth/Height).
// The modal itself begins no camera and no drawing frame.
draw_story_modal :: proc(app: ^App, assets: ^Assets, viewport_w, viewport_h: int) {
	layout := story_modal_layout(app, viewport_w, viewport_h)
	if layout.kind == .None do return
	rl.DrawRectangleRec(story_ui_ray_rect({0, 0, f32(max(1, viewport_w)), f32(max(1, viewport_h))}), rl.Fade(rl.BLACK, .30))
	switch layout.kind {
	case .Panel:
		draw_story_panel_modal(app, assets, &layout.panel)
	case .Minigame:
		draw_story_minigame_modal(app, assets, &layout.minigame)
	case .None:
	}
}

// ---------------------------------------------------------------------------
// UI typeface. All panel/HUD text draws route through these signature-
// compatible replacements for rl.DrawText/rl.MeasureText: they render the
// active bundled face in uppercase when it is resident and fall back to
// raylib's default font when it is not (missing file, procedural fallback
// boot, or a mid-rebuild window on Android surface recreation).

@(private)
ui_active_font: rl.Font

@(private)
ui_active_font_valid: bool

ui_set_active_font :: proc(font: rl.Font, valid: bool) {
	ui_active_font = font
	ui_active_font_valid = valid
}

// Keep font sizing centralized so typeface trials do not require retuning every
// caller. Edit Undo's cap height fits the original design sizes directly.
UI_FONT_SIZE_SCALE :: 1.0

@(private)
ui_scaled_text_size :: proc(size: i32) -> f32 {
	return f32(size) * UI_FONT_SIZE_SCALE
}

// Extra tracking only at tiny sizes where the minified atlas otherwise lets
// glyphs touch.
@(private)
ui_text_spacing :: proc(size: i32) -> f32 {
	return size < 14 ? 0.5 : 0
}

// Callers position text assuming the drawn line occupies [y, y+size], and row
// layouts center that band inside their plates. Keep an optical adjustment here
// for font-specific vertical tuning.
UI_FONT_OPTICAL_RISE :: 0.0

UI_TEXT_TRANSFORM_CAPACITY :: 4096

// English UI copy and generated labels are ASCII. Transforming at this shared
// seam keeps draw and measurement identical without allocating every frame.
@(private)
ui_uppercase_text :: proc(text: cstring, buffer: ^[UI_TEXT_TRANSFORM_CAPACITY]u8) -> cstring {
	if text == nil do return text
	source := string(text)
	if len(source) >= len(buffer) do return text
	for index in 0 ..< len(source) {
		value := source[index]
		if value >= 'a' && value <= 'z' do value -= 'a' - 'A'
		buffer[index] = value
	}
	buffer[len(source)] = 0
	return cstring(&buffer[0])
}

ui_draw_text :: proc(text: cstring, x, y, size: i32, color: rl.Color) {
	uppercase_buffer: [UI_TEXT_TRANSFORM_CAPACITY]u8
	uppercase := ui_uppercase_text(text, &uppercase_buffer)
	if !ui_active_font_valid {
		rl.DrawText(uppercase, x, y, size, color)
		return
	}
	scaled := ui_scaled_text_size(size)
	draw_y := f32(y) + (f32(size) - scaled) * .5 - f32(size) * UI_FONT_OPTICAL_RISE
	rl.DrawTextEx(ui_active_font, uppercase, {f32(x), draw_y}, scaled, ui_text_spacing(size), color)
}

ui_measure_text :: proc(text: cstring, size: i32) -> i32 {
	uppercase_buffer: [UI_TEXT_TRANSFORM_CAPACITY]u8
	uppercase := ui_uppercase_text(text, &uppercase_buffer)
	if !ui_active_font_valid do return rl.MeasureText(uppercase, size)
	return i32(rl.MeasureTextEx(ui_active_font, uppercase, ui_scaled_text_size(size), ui_text_spacing(size)).x + .5)
}

// Draw centered on center_x, shrinking from size down to min_size until the
// line fits max_width. Panels with player-driven strings (names, ledgers,
// notable loot) use this so text cannot escape their chrome by construction.
ui_draw_text_fitted_centered :: proc(text: cstring, center_x, y, size, min_size, max_width: i32, color: rl.Color) {
	fitted := size
	for fitted > min_size && ui_measure_text(text, fitted) > max_width do fitted -= 1
	final := text
	if ui_measure_text(final, fitted) > max_width {
		// Even the size floor overflows (three long notable finds can): keep
		// the floor readable and ellipsize instead, backing up to a rune
		// start so a split UTF-8 sequence never reaches the renderer.
		full := string(text)
		for keep := len(full) - 1; keep > 1; keep -= 1 {
			for keep > 1 && (full[keep] & 0xC0) == 0x80 do keep -= 1
			candidate := fmt.ctprintf("%s...", full[:keep])
			if ui_measure_text(candidate, fitted) <= max_width {
				final = candidate
				break
			}
		}
	}
	ui_draw_text(final, center_x - ui_measure_text(final, fitted) / 2, y, fitted, color)
}
