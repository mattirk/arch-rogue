package archrogue

// Presentation layer: camera, hover picking, all drawing. This file (with
// main/ui/assets/audio) is where raylib is allowed; sim files stay clean.
// Camera input uses real frame dt, never the fixed sim step.

import "base:intrinsics"
import "core:fmt"
import "core:math"
import "core:slice"
import rl "../vendor/raylib"

VISUAL_LATTICE_OFFSET :: MAP_H - 1
VISUAL_LATTICE_SIZE :: MAP_W + MAP_H - 1
MAX_GHOST_WEIGHT_TRACKS :: 256

Visual_Mask :: struct {
	values:      [MAP_W][MAP_H]f32,
	pixels:      [VISUAL_LATTICE_SIZE][VISUAL_LATTICE_SIZE]rl.Color, // [row][column]
	texture:     rl.Texture2D,
	ready:       bool,
	seed:        u64,
	depth:       int,
	floor_epoch: u32,
	known_count: int,
	reveal_all:  bool,
}

Ghost_Weight :: struct {
	key:    u64,
	weight: f32,
}

Miniboss_Sprite_Effect :: struct {
	enabled:    bool,
	color:      rl.Color,
	world_time: f32,
	stable_id:  u32,
}

View :: struct {
	camera:        rl.Camera2D,
	base_zoom:     f32, // persisted 720p design-space zoom; camera.zoom is framebuffer-scaled
	hovered:       [2]int,
	hovered_valid: bool,
	menu_click:    Desktop_Click_State,
	lightmap:      rl.RenderTexture2D, // final screen-space multiply lightmap
	light_glow:    rl.RenderTexture2D, // radial lights before live-LOS clipping
	light_tex:     rl.Texture2D, // shared radial gradient for lights/shadows/auras
	radial_ready:  bool,
	effect_mask_shader:       rl.Shader,
	effect_mask_visibility:   i32,
	effect_mask_screen_size:  i32,
	effect_mask_render_size:  i32,
	effect_mask_rect:         i32,
	effect_mask_shader_ready: bool,
	effect_mask_shader_tried: bool,
	explored_mask: Visual_Mask,
	visible_mask:  Visual_Mask,
	frame_dt:      f32,
	lighting_ready: bool, // current-frame compositor readiness, never just requested state
	mist:          ^Mist_Field, // heap-owned: its lattice buffers would bloat View's stack frame
	menu_mist:     Menu_Mist, // run-free drifting band for the first-boot scene
	ghost_floor_epoch: u32,
	ghost_weights: [MAX_GHOST_WEIGHT_TRACKS]Ghost_Weight,
	ghost_weight_count: int,
	cursor_disabled:       bool,
	mobile_mode:           bool,
	mobile_layout:         Mobile_Layout,
	mobile_layout_valid:   bool,
	mobile_joystick_vector:Vec2,
}

// Lighting: the world multiplies against a screen-space lightmap. Both floor
// types use the canonical four-tile lantern/sight reach; deeper normal floors
// lose ambient continuously while dark floors keep a near-black wash.
LIGHT_RADIUS_DARK :: 4.0 // DARK_LEVEL_LIGHT_RADIUS, in tiles
LIGHT_RADIUS_LIT :: 4.0

DEFAULT_ZOOM :: OPTIONS_VIEW_ZOOM_DEFAULT
ZOOM_MIN :: OPTIONS_VIEW_ZOOM_MIN
ZOOM_MAX :: OPTIONS_VIEW_ZOOM_MAX
ZOOM_STEP :: 1.12 // camera.py VIEW_ZOOM_STEP per wheel notch

WALL_PX :: 40 // wall block height in world pixels
DOOR_PX :: 26 // closed door block height

COLOR_BG :: rl.Color{10, 8, 13, 255} // unexcavated rock reads as void
COLOR_TEXT :: rl.Color{200, 195, 210, 255}
COLOR_TEXT_DIM :: rl.Color{130, 125, 145, 255}
COLOR_HOVER :: rl.Color{221, 168, 83, 255}

COLOR_DOOR_TOP :: rl.Color{122, 84, 46, 255}
COLOR_DOOR_LEFT :: rl.Color{74, 50, 27, 255}
COLOR_DOOR_RIGHT :: rl.Color{97, 66, 36, 255}
COLOR_PLACEHOLDER :: rl.Color{200, 70, 70, 255}

// Explored-but-unseen fog memory renders at 45% brightness.
fog_dim :: proc(c: rl.Color, dim: bool) -> rl.Color {
	if !dim do return c
	return {u8(f32(c.r) * 0.45), u8(f32(c.g) * 0.45), u8(f32(c.b) * 0.45), c.a}
}

tile_pos_visible :: proc(app: ^App, pos: Vec2) -> bool {
	x, y := int(pos.x), int(pos.y)
	if !dungeon_in_bounds(x, y) do return false
	return app.run.visible[x][y]
}

@(private = "file")
tile_in_visual_ground_margin :: proc(app: ^App, effective_lighting: bool, x, y: int) -> bool {
	if app == nil || !effective_lighting || app.dev_reveal do return false
	for dy in -1 ..= 1 {
		for dx in -1 ..= 1 {
			nx, ny := x + dx, y + dy
			if !dungeon_in_bounds(nx, ny) do continue
			known := app.run.dark_floor ? app.run.visible[nx][ny] : app.run.explored[nx][ny]
			if known do return true
		}
	}
	return false
}

@(private = "file")
frontier_prism_needed :: proc(app: ^App, effective_lighting: bool, x, y: int) -> bool {
	if app == nil || !effective_lighting || app.dev_reveal do return false
	// A south-frontier wall can rise four diagonal-v units into lit floor. Draw
	// only those prisms early; their own mask site is black, so the tall art
	// surfaces through the neighboring fog gradient instead of popping in.
	for dy in -1 ..= 4 {
		for dx in -1 ..= 4 {
			v_distance := dx + dy
			if v_distance < 1 || v_distance > 4 || abs(dx-dy) > 2 do continue
			sx, sy := x-dx, y-dy
			if !dungeon_in_bounds(sx,sy) do continue
			known := app.run.dark_floor ? app.run.visible[sx][sy] : app.run.explored[sx][sy]
			if !known do continue
			support := app.run.dungeon.tiles[sx][sy]
			if support == .Floor || support == .Stairs || support == .Open_Door do return true
		}
	}
	return false
}

// Port of sprites/library.py _tinted_surface, folded into one multiply tint:
// multiplier = 255 - (255-target)*s*0.72, plus the small additive term
// (target*s*0.12) and the per-tile variant delta {-9,-3,3,7} approximated
// into the same multiplier. Applied via DrawTexturePro's tint.
theme_tint :: proc(target: [4]u8, strength: f32, variant: int) -> rl.Color {
	s := clamp(strength, 0, 1)
	deltas := [4]f32{-9, -3, 3, 7}
	d := deltas[variant & 3]
	c: rl.Color
	for i in 0 ..< 3 {
		m := 255 - (255 - f32(target[i])) * s * 0.72
		m += f32(target[i]) * s * 0.12
		m += d
		c[i] = u8(clamp(m, 0, 255))
	}
	c[3] = 255
	return c
}

world_sprite_frame_index :: proc(frame_count: int, fps: f32, ping_pong: bool, time: f32) -> int {
	if frame_count <= 0 || fps <= 0 do return 0
	idx := int(max(f32(0),time)*fps)
	if ping_pong && frame_count > 1 {
		period := frame_count*2-2
		idx %= period
		if idx >= frame_count do idx = period-idx
	} else {
		idx %= frame_count
	}
	return idx
}

// Draw a world sprite so its anchor pixel lands on the given tile's center.
// `variant` selects the per-tile static art; animated sprites (frames + fps)
// instead pick a frame from `time`, ping-ponging when authored that way.
@(private = "file")
world_sprite_frame :: proc(sprite: ^World_Sprite, variant: int, time: f32) -> rl.Texture2D {
	if sprite == nil do return {}
	if sprite.frame_count > 0 && sprite.fps > 0 {
		idx := world_sprite_frame_index(sprite.frame_count,sprite.fps,sprite.ping_pong,time)
		return sprite.frames[idx]
	}
	if sprite.variant_count <= 0 do return {}
	idx := ((variant % sprite.variant_count) + sprite.variant_count) % sprite.variant_count
	return sprite.variants[idx]
}

@(private = "file")
world_sprite_rect :: proc(sprite: ^World_Sprite, tile: Vec2, variant: int, time: f32) -> (rl.Texture2D, rl.Rectangle) {
	tex := world_sprite_frame(sprite, variant, time)
	if tex.id == 0 do return {}, {}
	center := rl.Vector2(world_from_tile(tile + {0.5, 0.5}))
	w := f32(tex.width) * sprite.scale
	h := f32(tex.height) * sprite.scale
	return tex, rl.Rectangle{
		center.x - sprite.anchor.x * sprite.scale,
		center.y - sprite.anchor.y * sprite.scale,
		w, h,
	}
}

@(private = "file")
draw_world_sprite :: proc(sprite: ^World_Sprite, tile: Vec2, variant: int, time: f32, tint: rl.Color) -> rl.Rectangle {
	tex, dst := world_sprite_rect(sprite, tile, variant, time)
	if tex.id == 0 do return {}
	rl.DrawTexturePro(tex, {0, 0, f32(tex.width), f32(tex.height)}, dst, {0, 0}, 0, tint)
	return dst
}

// Guidance chooses an authored overlay by envelope strength, not by its own
// animation clock. Frame zero is implicit plain floor, so callers pass the
// explicit zero-based overlay index for Pygame guidance frames 1..N.
@(private = "file")
draw_world_sprite_frame :: proc(sprite: ^World_Sprite, tile: Vec2, frame: int, tint: rl.Color) -> rl.Rectangle {
	if sprite == nil || sprite.frame_count <= 0 do return {}
	tex := sprite.frames[clamp(frame,0,sprite.frame_count-1)]
	if tex.id == 0 do return {}
	center := rl.Vector2(world_from_tile(tile+Vec2{.5,.5}))
	dst := rl.Rectangle{
		center.x-sprite.anchor.x*sprite.scale,
		center.y-sprite.anchor.y*sprite.scale,
		f32(tex.width)*sprite.scale,
		f32(tex.height)*sprite.scale,
	}
	rl.DrawTexturePro(tex,{0,0,f32(tex.width),f32(tex.height)},dst,{0,0},0,tint)
	return dst
}

view_apply_base_zoom :: proc(view: ^View, base_zoom: f32, clamp_to_options := true) {
	if view == nil do return
	view.base_zoom = clamp_to_options ? view_zoom_normalize(base_zoom) : max(f32(.05), base_zoom)
	view.camera.zoom = effective_view_zoom(view.base_zoom, int(rl.GetRenderHeight()))
}

view_init :: proc(view: ^View) {
	view_apply_base_zoom(view, DEFAULT_ZOOM)
}

// Menu click pairs never cross screen-context boundaries.
view_clear_menu_click :: proc(view: ^View) {
	if view == nil do return
	view.menu_click = {}
}

@(private = "file")
visual_mask_shutdown :: proc(mask: ^Visual_Mask) {
	if mask != nil && mask.ready {
		rl.UnloadTexture(mask.texture)
		mask.ready = false
		mask.texture = {}
	}
}

view_shutdown :: proc(view: ^View) {
	if view == nil do return
	if view.lightmap.id != 0 do rl.UnloadRenderTexture(view.lightmap)
	if view.light_glow.id != 0 do rl.UnloadRenderTexture(view.light_glow)
	if view.light_tex.id != 0 do rl.UnloadTexture(view.light_tex)
	if view.effect_mask_shader_ready do rl.UnloadShader(view.effect_mask_shader)
	visual_mask_shutdown(&view.explored_mask)
	visual_mask_shutdown(&view.visible_mask)
	mist_shutdown(view.mist)
	menu_mist_shutdown(&view.menu_mist)
	view^ = {}
}

view_center_on :: proc(view: ^View, world: Vec2) {
	view.camera.target = rl.Vector2(world)
}

view_follow :: proc(view: ^View, world: Vec2, dt: f32) {
	target := rl.Vector2(world)
	view.camera.target += (target - view.camera.target) * camera_follow_fraction(dt)
}

view_update :: proc(view: ^View, dt: f32) {
	view.frame_dt = max(f32(0), dt)
	cam := &view.camera
	// Borderless toggles and free window resizing can change framebuffer height
	// without touching persisted options. Recompute the effective zoom every frame
	// so the same 720p design zoom retains identical apparent framing everywhere.
	cam.zoom = effective_view_zoom(view.base_zoom, int(rl.GetRenderHeight()))
	sw := f32(rl.GetScreenWidth())
	sh := f32(rl.GetScreenHeight())
	// The slight upward framing leaves more readable world space below the
	// player for the action bar, matching the desktop pygame camera.
	if view.mobile_mode && view.mobile_layout_valid {
		cam.offset = rl.Vector2(view.mobile_layout.world_focus)
		view.hovered = {}
		view.hovered_valid = false
	} else {
		cam.offset = {sw * 0.5, sh * CAMERA_FOCUS_Y}
		mouse := rl.GetMousePosition()
		t := tile_from_world(Vec2(rl.GetScreenToWorld2D(mouse, cam^)))
		view.hovered = {int(math.floor(t.x)), int(math.floor(t.y))}
		view.hovered_valid = dungeon_in_bounds(view.hovered.x, view.hovered.y)
	}
}

view_zoom_at_cursor :: proc(view: ^View, wheel: f32) {
	if view == nil || wheel == 0 do return
	// Canonical desktop zoom remains centered on the followed actor. Change the
	// persisted design-space zoom, never the resolution-scaled camera value.
	view.base_zoom = clamp(
		view.base_zoom * math.pow(f32(ZOOM_STEP), wheel),
		ZOOM_MIN,
		ZOOM_MAX,
	)
	view.camera.zoom = effective_view_zoom(view.base_zoom, int(rl.GetRenderHeight()))
}

menu_mouse_double_clicked :: proc(view: ^View, click_context: Menu_Click_Context, index: int) -> bool {
	return desktop_register_menu_click(&view.menu_click, click_context, index, rl.GetTime())
}

draw_frame :: proc(view: ^View, app: ^App, assets: ^Assets, alpha: f32) {
	draws_run := app.mode == .Playing || app.mode == .Paused || app.mode == .Dead || app.mode == .Victory ||
		app.mode == .Resume_Veil ||
		((app.mode == .Save_Wait || app.mode == .Save_Error) && app.persistence_return == .Paused) ||
		((app.mode == .Options || app.mode == .Controls) && app.options_return == .Paused)
	view.lighting_ready = false
	if draws_run {
		ensure_radial_texture(view) // contact shadows remain when lighting is off
		if !app_story_soul_hunt_active(app) {
			mist_invalidate_soul_hunt(view)
			update_effect_visibility(view, app)
			if app.options.lighting_enabled do view.lighting_ready = update_lightmap(view, app, alpha)
		}
		// Mist simulation advances only while the world does; pause/panels/death
		// freeze the field exactly like the deterministic animation clock.
		sim_live := app.mode == .Playing && !app.inventory_open && !app.character_open && !app.shop_open &&
			!app_play_modal_open(app)
		if sim_live {
			if app_story_soul_hunt_active(app) {
				if app.options.mist_enabled do mist_update_soul_hunt(view,app,alpha)
				else do mist_invalidate_soul_hunt(view)
			}
			else if app.options.mist_enabled do mist_update(view,app,alpha)
		}
	}

	rl.BeginDrawing()
	rl.ClearBackground(COLOR_BG)

	switch app.mode {
	case .Title:
		draw_title_screen(app, assets)
	case .Story_Decision:
		draw_story_decision_screen(view, app, assets)
	case .Select:
		draw_select_screen(app, assets)
	case .Playing:
		draw_run_scene(view,app,assets,alpha)
		if app.inventory_open && app.mode == .Playing {
			draw_inventory_panel(app, assets)
		}
		if app.character_open do draw_character_panel(app, assets)
		if app.shop_open do draw_shop_panel(app, assets)
	case .Paused:
		draw_run_scene(view,app,assets,alpha)
		draw_pause_panel(app, assets)
	case .Options:
		if app.options_return == .Paused do draw_run_scene(view,app,assets,alpha)
		draw_options_screen(app, assets)
	case .Controls:
		if app.options_return == .Paused do draw_run_scene(view,app,assets,alpha)
		draw_controls_screen(app, assets)
	case .Chronicle:
		draw_chronicle_screen(app,assets)
	case .Abandon_Confirm:
		draw_title_screen(app,assets)
		draw_abandon_confirm(app,assets)
	case .Recovery:
		draw_title_screen(app,assets)
		draw_recovery_screen(app,assets)
	case .Save_Wait:
		if app.persistence_return==.Paused do draw_run_scene(view,app,assets,alpha)
		else do draw_title_screen(app,assets)
		draw_save_wait_overlay(app,assets)
	case .Save_Error:
		if app.persistence_return==.Paused do draw_run_scene(view,app,assets,alpha)
		else do draw_title_screen(app,assets)
		draw_save_error_overlay(app,assets)
	case .Resume_Veil:
		draw_run_scene(view,app,assets,alpha)
		draw_resume_veil(app,assets)
	case .Dead:
		draw_run_scene(view,app,assets,alpha)
		draw_death_overlay(app,assets)
	case .Victory:
		draw_run_scene(view,app,assets,alpha)
		draw_victory_overlay(app,assets)
	}
	draw_screen_feel(app)
	// Story is the final HUD-like layer: combat flashes remain beneath readable
	// narration, while the frozen live world and ordinary HUD stay visible.
	if app.mode == .Playing && app_play_modal_open(app) {
		draw_story_modal(app,assets,int(rl.GetScreenWidth()),int(rl.GetScreenHeight()))
	}
	if view.mobile_mode && view.mobile_layout_valid do draw_mobile_context_controls(view,app)
	draw_custom_cursor(view, app, assets)

	rl.EndDrawing()
}

@(private = "file")
cursor_draw_scale :: proc() -> f32 {
	// The web framebuffer is clamped to CSS pixels. Native window coordinates
	// are already transformed by the desktop compositor, so applying raylib's
	// reported DPI here would scale the cursor twice on some Linux desktops.
	when ARCH_ROGUE_WEB do return UI_CURSOR_WEB_DRAW_SCALE
	return UI_CURSOR_NATIVE_DRAW_SCALE
}

@(private = "file")
draw_custom_cursor :: proc(view: ^View, app: ^App, assets: ^Assets) {
	if view == nil || app == nil || assets == nil do return
	if view.cursor_disabled {
		rl.HideCursor()
		return
	}
	custom_cursor_active := !view.mobile_mode && assets.ui_cursor.id != 0
	if !custom_cursor_active {
		if !view.mobile_mode do rl.ShowCursor()
		return
	}

	rl.HideCursor()
	mouse := rl.GetMousePosition()
	scale := cursor_draw_scale()
	draw_size := f32(UI_CURSOR_SIZE) * scale
	hotspot := rl.Vector2{
		UI_CURSOR_HOTSPOT[0] * scale,
		UI_CURSOR_HOTSPOT[1] * scale,
	}
	rl.DrawTexturePro(
		assets.ui_cursor,
		{0, 0, f32(UI_CURSOR_SIZE), f32(UI_CURSOR_SIZE)},
		{mouse.x - hotspot.x, mouse.y - hotspot.y, draw_size, draw_size},
		{},
		0,
		rl.WHITE,
	)
}

@(private = "file")
draw_mobile_context_controls :: proc(view:^View,app:^App) {
	if view==nil||app==nil do return
	_ = ui_begin_presentation()
	defer ui_end_presentation()
	layout:=&view.mobile_layout
	if app.mobile_guard.kind!=.None {
		display:=mobile_rect_to_design(layout.display_rect)
		rl.DrawRectangleRec(display,rl.Fade(rl.Color{5,4,8,255},.72))
		prompt:="Confirm action?"
		switch app.mobile_guard.kind {
		case .Inventory_Drop: prompt="Drop this item?"
		case .Shop_Buy: prompt="Buy this item?"
		case .Shop_Sell: prompt="Sell this item?"
		case .None:
		}
		font:i32=24
		label:=fmt.ctprintf("%s",prompt)
		x:=i32(ui_design_width()*.5)-ui_measure_text(label,font)/2
		ui_draw_text(label,x,i32(ui_design_height()*.5)-42,font,COLOR_TITLE)
		confirm,cancel:=mobile_guard_button_rects(layout)
		draw_mobile_button(confirm,"CONFIRM",{176,214,126,255})
		draw_mobile_button(cancel,"CANCEL",{220,116,102,255})
		return
	}
	#partial switch app.mode {
	case .Select:
		draw_mobile_button(mobile_center_button_rect(layout),"ENTER THE DEPTHS",COLOR_TITLE)
	case .Playing:
		if app.inventory_open {
			use_button,drop_button:=mobile_guard_button_rects(layout)
			draw_mobile_button(use_button,"USE / EQUIP",{176,214,126,255})
			draw_mobile_button(drop_button,"DROP",{220,116,102,255})
		} else if app.shop_open {
			label:=app.shop_mode==.Buy?cstring("BUY SELECTED"):cstring("SELL SELECTED")
			draw_mobile_button(mobile_center_button_rect(layout),label,COLOR_TITLE)
		}
	case:
	}
}

@(private = "file")
draw_run_scene :: proc(view:^View,app:^App,assets:^Assets,alpha:f32) {
	if app_story_soul_hunt_active(app) {
		rl.BeginMode2D(view.camera)
		draw_soul_hunt_world(view,app,assets,alpha)
		rl.EndMode2D()
		draw_soul_hunt_overlay(view,app,assets)
		return
	}
	rl.BeginMode2D(view.camera)
	draw_world(view,app,assets,alpha)
	rl.EndMode2D()
	if view.lighting_ready && rl.IsRenderTextureValid(view.lightmap) {
		rl.BeginBlendMode(.MULTIPLIED)
		rl.DrawTextureRec(view.lightmap.texture,{0,0,f32(view.lightmap.texture.width),-f32(view.lightmap.texture.height)},{0,0},rl.WHITE)
		rl.EndBlendMode()
	}
	// Text notifications render after the lighting multiply so room-edge labels
	// remain fully legible even when their glyph bounds extend into darkness.
	rl.BeginMode2D(view.camera)
	draw_text_notifications(app)
	rl.EndMode2D()
	draw_overlay(view,app,assets)
}

Soul_Hunt_Draw_Kind :: enum u8 {Ghost,Player}
Soul_Hunt_Draw_Item :: struct {kind:Soul_Hunt_Draw_Kind,index:int,feet:Vec2,depth:f32,alpha:f32}


@(private = "file")
draw_soul_hunt_capture_effect :: proc(feet:Vec2,feedback_time:f32) {
	progress:=clamp(1-feedback_time/.42,f32(0),f32(1))
	life:=1-progress
	center:=rl.Vector2(world_from_tile(feet))-rl.Vector2{0,13+progress*9}
	accent:=rl.Fade(rl.Color{151,232,238,255},life)
	bright:=rl.Fade(rl.Color{226,255,250,255},life*life)
	rl.BeginBlendMode(.ADDITIVE)
	// Tight, angular soul fragments replace the old floor-spanning ring. Their
	// horizontal reach stays inside one isometric tile even at edge spawn sites.
	for i in 0..<6 {
		side:=f32(-1)
		if i%2!=0 do side=1
		rank:=f32(i/2)
		outer:=rl.Vector2{side*(13-rank*3)*(1-progress*.58),f32(8-rank*5)-progress*17}
		tip:=center+outer
		inward:=center+outer*.38
		rl.DrawLineEx(tip,inward,1.4+life*.9,accent)
		shard_h:=f32(3)+life*2
		rl.DrawTriangle(
			tip-rl.Vector2{2,0},
			tip+rl.Vector2{2,0},
			tip-rl.Vector2{0,shard_h},
			bright,
		)
	}
	rl.DrawLineEx(center+rl.Vector2{0,8},center-rl.Vector2{0,12+progress*8},2.0,bright)
	rl.EndBlendMode()
}

@(private = "file")
draw_soul_hunt_player :: proc(view:^View,app:^App,assets:^Assets,feet:Vec2,world_time:f32) {
	player:=&app.run.player
	draw_contact_shadow(view,feet,34,13,player.moving)
	clip:=player.moving?Clip_Kind.Walk:Clip_Kind.Idle
	clip_time:=player.moving?player.anim_time:visual_idle_clip_time(world_time)
	if player.visual_action==.Dash {
		clip=.Walk;action_clip:=&assets.archetypes[player.archetype].clips[clip]
		clip_time=normalized_action_clip_time(player_visual_action_progress(player),action_clip.frames,action_clip.fps)
	}
	draw_actor(assets,&assets.archetypes[player.archetype],clip,player.facing,clip_time,feet,rl.WHITE,0)
}

@(private = "file")
draw_soul_hunt_ghost_fallback :: proc(feet:Vec2,alpha,world_time:f32) {
	center:=rl.Vector2(world_from_tile(feet))-rl.Vector2{0,16+math.sin(world_time*5)*2}
	rl.BeginBlendMode(.ADDITIVE)
	rl.DrawCircleV(center,18,rl.Fade(rl.Color{95,174,198,255},.13*alpha))
	rl.DrawCircleV(center,9,rl.Fade(rl.Color{178,232,238,255},.48*alpha))
	rl.EndBlendMode()
	rl.DrawTriangle(center+rl.Vector2{-8,3},center+rl.Vector2{8,3},center+rl.Vector2{0,24},rl.Fade(rl.Color{92,124,153,255},.72*alpha))
	rl.DrawCircleV(center-rl.Vector2{0,4},5,rl.Fade(rl.Color{221,244,242,255},.88*alpha))
}

@(private = "file")
draw_soul_hunt_world :: proc(view:^View,app:^App,assets:^Assets,alpha:f32) {
	state:=&app.story_minigame;room:=STORY_SOUL_HUNT_ROOM
	world_time:=app.run.player.sim_elapsed+alpha*SIM_DT
	floor:=&assets.world[.Lossless_Soul_Floor]
	// A thin exposed underside makes the unenclosed floor read as a slab hanging
	// over the void, without introducing wall geometry or additional collision.
	drop:=rl.Vector2{0,8}
	for x in room.x+1..<room.x+room.w-1 {
		_,_,b,l:=tile_corners({f32(x),f32(room.y+room.h-2)})
		rl.DrawTriangle(l,l+drop,b+drop,{11,13,20,255})
		rl.DrawTriangle(l,b+drop,b,{17,20,29,255})
	}
	for y in room.y+1..<room.y+room.h-1 {
		_,r,b,_:=tile_corners({f32(room.x+room.w-2),f32(y)})
		rl.DrawTriangle(b,b+drop,r+drop,{9,11,17,255})
		rl.DrawTriangle(b,r+drop,r,{14,17,25,255})
	}
	for y in room.y+1..<room.y+room.h-1 {
		for x in room.x+1..<room.x+room.w-1 {
			tile:=Vec2{f32(x),f32(y)}
			if floor.loaded do draw_world_sprite(floor,tile,visual_floor_variant(state.seed,state.depth,0,x,y),0,{116,132,150,255})
			else do draw_iso_tile_fill(tile,{25,30,42,255})
		}
	}
	items:[2]Soul_Hunt_Draw_Item;count:=0
	if ghost,active:=story_soul_hunt_target_position(state);active {
		ghost_profile:=story_soul_hunt_profile(app.run.story_runtime.hall.verdict)
		appeared:=clamp((ghost_profile.ghost_seconds-state.target_time)/.16,f32(0),f32(1))
		dissolving:=clamp(state.target_time/.20,f32(0),f32(1))
		ghost_alpha:=min(appeared,dissolving)
		items[count]={kind=.Ghost,index=state.active_cell,feet=ghost,depth=ghost.x+ghost.y,alpha=ghost_alpha};count+=1
	}
	feet:=app.run.player.prev_pos+(app.run.player.pos-app.run.player.prev_pos)*alpha
	items[count]={kind=.Player,feet=feet,depth=feet.x+feet.y,alpha=1};count+=1
	for i in 1..<count {
		item:=items[i];j:=i
		for j>0&&items[j-1].depth>item.depth {items[j]=items[j-1];j-=1}
		items[j]=item
	}
	for i in 0..<count {
		item:=items[i]
		switch item.kind {
		case .Ghost:
			if assets.mistbound_ghost.loaded&&assets.mistbound_ghost.clips[.Idle].valid {
				facing:=app.run.player.pos-item.feet;if facing=={} do facing={0,1}
				draw_actor(assets,&assets.mistbound_ghost,.Idle,facing,visual_idle_clip_time(world_time,u32(item.index+1)),item.feet,rl.Fade(rl.WHITE,item.alpha),0)
			} else do draw_soul_hunt_ghost_fallback(item.feet,item.alpha,world_time)
		case .Player:draw_soul_hunt_player(view,app,assets,item.feet,world_time)
		}
	}
	if app.options.mist_enabled&&view.mist!=nil&&view.mist.soul_hunt do mist_draw(view,world_time,1.58)
	if state.feedback_time>0&&state.last_correct&&0<=state.last_cell&&state.last_cell<len(STORY_SOUL_HUNT_SITES) {
		draw_soul_hunt_capture_effect(STORY_SOUL_HUNT_SITES[state.last_cell],state.feedback_time)
	}
}

@(private = "file")
draw_soul_hunt_overlay :: proc(view:^View,app:^App,assets:^Assets) {
	presentation:=ui_begin_presentation();defer ui_end_presentation()
	state:=&app.story_minigame;profile:=story_soul_hunt_profile(app.run.story_runtime.hall.verdict)
	title:=cstring("THE MISTBOUND CHAMBER");title_w:=ui_measure_text(title,22)
	ui_draw_text(title,i32((presentation.width-f32(title_w))*.5),18,22,{190,222,226,255})
	message:="The floor hangs over nothingness. Watch the mist."
	if state.phase==.Play do message="CATCH THE GHOST BEFORE IT DISSOLVES"
	if state.phase==.Result do message=state.outcome==.Won?"THE MIST REMEMBERS YOUR PASSAGE":"THE LAST SHAPE DISSOLVES"
	message_w:=ui_measure_text(fmt.ctprintf("%s",message),15)
	ui_draw_text(fmt.ctprintf("%s",message),i32((presentation.width-f32(message_w))*.5),47,15,COLOR_TEXT)
	bar_w:=min(f32(390),presentation.width*.48);bar_x:=(presentation.width-bar_w)*.5
	remaining:=clamp(state.time_left/max(profile.time_limit,f32(.001)),f32(0),f32(1))
	if state.phase==.Preview {
		remaining=clamp(
			app.story_soul_hunt_wait_remaining_s/max(app.story_soul_hunt_wait_total_s,f32(.001)),
			f32(0),f32(1),
		)
	}
	rl.DrawRectangleRec({bar_x,72,bar_w,9},rl.Fade(rl.Color{9,11,18,255},.88))
	rl.DrawRectangleRec({bar_x,72,bar_w*remaining,9},{112,188,201,230})
	rl.DrawRectangleLinesEx({bar_x,72,bar_w,9},1,{173,211,216,180})
	progress:=fmt.ctprintf("GHOSTS  %v / %v     MISSED  %v",state.score,state.goal,state.mistakes)
	if state.phase==.Preview do progress=fmt.ctprintf("HUNT BEGINS IN  %.1f",max(app.story_soul_hunt_wait_remaining_s,f32(0)))
	progress_w:=ui_measure_text(progress,14);ui_draw_text(progress,i32((presentation.width-f32(progress_w))*.5),88,14,COLOR_TITLE)
	draw_player_hud(view,app,assets)
}

// --- Lighting and transient visibility -------------------------------------

// Effects remain in the ordinary world painter, where walls can occlude them,
// but every fragment also samples the authoritative live-LOS lattice. Unlike a
// final world multiply, this protects unexplored/explored-memory space even
// when continuous lighting is disabled without darkening unrelated world art.
@(private = "file")
EFFECT_MASK_SHADER_FS :: `#version 330
in vec2 fragTexCoord;
in vec4 fragColor;
out vec4 finalColor;

uniform sampler2D texture0;
uniform sampler2D u_visibility;
uniform vec2 u_screen_size;
uniform vec2 u_render_size;
uniform vec4 u_mask_rect; // live-visibility lattice destination in screen pixels

void main() {
    vec4 source = texture(texture0, fragTexCoord) * fragColor;
    vec2 screen = vec2(
        gl_FragCoord.x / u_render_size.x * u_screen_size.x,
        (u_render_size.y - gl_FragCoord.y) / u_render_size.y * u_screen_size.y
    );
    vec2 visibility_uv = (screen - u_mask_rect.xy) / u_mask_rect.zw;
    if (visibility_uv.x < 0.0 || visibility_uv.y < 0.0 ||
        visibility_uv.x > 1.0 || visibility_uv.y > 1.0) {
        finalColor = vec4(0.0);
        return;
    }
    float visible = texture(u_visibility, visibility_uv).r;
    finalColor = vec4(source.rgb, source.a * visible);
}
`

@(private = "file")
EFFECT_MASK_SHADER_FS_GLES2 :: `#version 100
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif
varying vec2 fragTexCoord;
varying vec4 fragColor;

uniform sampler2D texture0;
uniform sampler2D u_visibility;
uniform vec2 u_screen_size;
uniform vec2 u_render_size;
uniform vec4 u_mask_rect;

void main() {
    vec4 source = texture2D(texture0, fragTexCoord) * fragColor;
    vec2 screen = vec2(
        gl_FragCoord.x / u_render_size.x * u_screen_size.x,
        (u_render_size.y - gl_FragCoord.y) / u_render_size.y * u_screen_size.y
    );
    vec2 visibility_uv = (screen - u_mask_rect.xy) / u_mask_rect.zw;
    if (visibility_uv.x < 0.0 || visibility_uv.y < 0.0 ||
        visibility_uv.x > 1.0 || visibility_uv.y > 1.0) {
        gl_FragColor = vec4(0.0);
        return;
    }
    float visible = texture2D(u_visibility, visibility_uv).r;
    gl_FragColor = vec4(source.rgb, source.a * visible);
}
`

// WebGL2 (OpenGL ES 3.0) port of the GLES2 variant above; raylib's ES3 web
// build supplies the matching default vertex shader.
@(private = "file")
EFFECT_MASK_SHADER_FS_ES3 :: `#version 300 es
precision highp float;
in vec2 fragTexCoord;
in vec4 fragColor;
out vec4 finalColor;

uniform sampler2D texture0;
uniform sampler2D u_visibility;
uniform vec2 u_screen_size;
uniform vec2 u_render_size;
uniform vec4 u_mask_rect;

void main() {
    vec4 source = texture(texture0, fragTexCoord) * fragColor;
    vec2 screen = vec2(
        gl_FragCoord.x / u_render_size.x * u_screen_size.x,
        (u_render_size.y - gl_FragCoord.y) / u_render_size.y * u_screen_size.y
    );
    vec2 visibility_uv = (screen - u_mask_rect.xy) / u_mask_rect.zw;
    if (visibility_uv.x < 0.0 || visibility_uv.y < 0.0 ||
        visibility_uv.x > 1.0 || visibility_uv.y > 1.0) {
        finalColor = vec4(0.0);
        return;
    }
    float visible = texture(u_visibility, visibility_uv).r;
    finalColor = vec4(source.rgb, source.a * visible);
}
`

@(private = "file")
effect_mask_shader_source :: proc() -> cstring {
	when ARCH_ROGUE_ANDROID do return cstring(EFFECT_MASK_SHADER_FS_GLES2)
	when ARCH_ROGUE_WEB do return cstring(EFFECT_MASK_SHADER_FS_ES3)
	return cstring(EFFECT_MASK_SHADER_FS)
}

@(private = "file")
ensure_visual_mask :: proc(mask: ^Visual_Mask) {
	if mask == nil || mask.ready do return
	img := rl.GenImageColor(VISUAL_LATTICE_SIZE, VISUAL_LATTICE_SIZE, rl.BLANK)
	mask.texture = rl.LoadTextureFromImage(img)
	rl.UnloadImage(img)
	if rl.IsTextureValid(mask.texture) {
		rl.SetTextureFilter(mask.texture, .BILINEAR)
		rl.SetTextureWrap(mask.texture, .CLAMP)
		mask.ready = true
	}
}

@(private = "file")
visual_mask_source_known :: proc(app: ^App, explored_field: bool, x, y: int) -> bool {
	if app == nil || !dungeon_in_bounds(x, y) do return false
	if app.dev_reveal do return true
	if explored_field && !app.run.dark_floor do return app.run.explored[x][y]
	return app.run.visible[x][y]
}

@(private = "file")
visual_mask_value_at_lattice_site :: proc(mask: ^Visual_Mask, iu, iv: int) -> f32 {
	if mask == nil || iu < 0 || iu >= VISUAL_LATTICE_SIZE || iv < 0 || iv >= VISUAL_LATTICE_SIZE do return 0
	u := iu - VISUAL_LATTICE_OFFSET
	if ((u + iv) & 1) != 0 do return 0
	x := (u + iv) / 2
	y := (iv - u) / 2
	if !dungeon_in_bounds(x, y) do return 0
	return mask.values[x][y]
}

@(private = "file")
visual_mask_upload :: proc(mask: ^Visual_Mask) {
	if mask == nil do return
	ensure_visual_mask(mask)
	if !mask.ready || !rl.IsTextureValid(mask.texture) do return
	for iv in 0 ..< VISUAL_LATTICE_SIZE {
		for iu in 0 ..< VISUAL_LATTICE_SIZE {
			u := iu - VISUAL_LATTICE_OFFSET
			value: f32
			if ((u + iv) & 1) == 0 {
				value = visual_mask_value_at_lattice_site(mask, iu, iv)
			} else {
				value = (
					visual_mask_value_at_lattice_site(mask, iu-1, iv) +
					visual_mask_value_at_lattice_site(mask, iu+1, iv) +
					visual_mask_value_at_lattice_site(mask, iu, iv-1) +
					visual_mask_value_at_lattice_site(mask, iu, iv+1)
				) * .25
			}
			level := u8(clamp(value * 255 + .5, 0, 255))
			// Opaque alpha is required by raylib's MULTIPLIED blend
			// (DST_COLOR, ONE_MINUS_SRC_ALPHA); RGB alone carries the mask.
			mask.pixels[iv][iu] = {level, level, level, 255}
		}
	}
	rl.UpdateTexture(mask.texture, raw_data(mask.pixels[:]))
}

visual_mask_sync :: proc(mask: ^Visual_Mask, app: ^App, explored_field: bool, dt: f32) {
	if mask == nil || app == nil do return
	run := &app.run
	known_count := 0
	lost_persistent_tile := false
	for x in 0 ..< MAP_W {
		for y in 0 ..< MAP_H {
			known := visual_mask_source_known(app, explored_field, x, y)
			if known do known_count += 1
			if explored_field && !run.dark_floor && !known && mask.values[x][y] > VISUAL_FOG_DRAW_EPSILON {
				lost_persistent_tile = true
			}
		}
	}
	reset := !mask.ready || mask.seed != run.seed || mask.depth != run.depth ||
		mask.floor_epoch != run.floor_epoch || mask.reveal_all != app.dev_reveal || lost_persistent_tile
	changed := reset
	if reset {
		mask.values = {}
		mask.seed = run.seed
		mask.depth = run.depth
		mask.floor_epoch = run.floor_epoch
		mask.reveal_all = app.dev_reveal
	}
	bloom := known_count <= 120
	for x in 0 ..< MAP_W {
		for y in 0 ..< MAP_H {
			known := visual_mask_source_known(app, explored_field, x, y)
			target: f32
			if known {
				target = 1
				if explored_field && !run.dark_floor && !app.dev_reveal {
					target = visual_fog_target(&run.explored, x, y)
				}
			}
			previous := mask.values[x][y]
			next := previous
			if !explored_field {
				next = visual_live_visibility_ease(previous, known, dt)
			} else if reset && !bloom {
				next = target
			} else {
				next = visual_fog_ease(previous, target, dt)
			}
			mask.values[x][y] = next
			if abs(next-previous) > .0005 do changed = true
		}
	}
	mask.known_count = known_count
	if changed do visual_mask_upload(mask)
}

@(private = "file")
ensure_effect_mask_shader :: proc(view: ^View) -> bool {
	if view == nil do return false
	if !view.effect_mask_shader_tried {
		view.effect_mask_shader_tried = true
		view.effect_mask_shader = rl.LoadShaderFromMemory(nil, effect_mask_shader_source())
		if rl.IsShaderValid(view.effect_mask_shader) {
			view.effect_mask_visibility = rl.GetShaderLocation(view.effect_mask_shader, "u_visibility")
			view.effect_mask_screen_size = rl.GetShaderLocation(view.effect_mask_shader, "u_screen_size")
			view.effect_mask_render_size = rl.GetShaderLocation(view.effect_mask_shader, "u_render_size")
			view.effect_mask_rect = rl.GetShaderLocation(view.effect_mask_shader, "u_mask_rect")
			view.effect_mask_shader_ready = view.effect_mask_visibility >= 0 &&
				view.effect_mask_screen_size >= 0 && view.effect_mask_render_size >= 0 &&
				view.effect_mask_rect >= 0
		}
	}
	return view.effect_mask_shader_ready
}

view_mobile_shader_preflight :: proc(view:^View)->bool {
	if view==nil do return false
	return ensure_effect_mask_shader(view)&&mist_shader_preflight(view)
}

@(private = "file")
update_effect_visibility :: proc(view: ^View, app: ^App) {
	if view == nil || app == nil do return
	ensure_visual_mask(&view.visible_mask)
	visual_mask_sync(&view.visible_mask, app, false, view.frame_dt)
	if !ensure_effect_mask_shader(view) || !view.visible_mask.ready do return
	screen := [2]f32{f32(rl.GetScreenWidth()), f32(rl.GetScreenHeight())}
	render := [2]f32{f32(rl.GetRenderWidth()), f32(rl.GetRenderHeight())}
	mask_rect := visual_mask_screen_rect(view)
	mask := [4]f32{mask_rect.x,mask_rect.y,mask_rect.width,mask_rect.height}
	rl.SetShaderValue(view.effect_mask_shader, view.effect_mask_screen_size, &screen, .VEC2)
	rl.SetShaderValue(view.effect_mask_shader, view.effect_mask_render_size, &render, .VEC2)
	rl.SetShaderValue(view.effect_mask_shader, view.effect_mask_rect, &mask, .VEC4)
	rl.SetShaderValueTexture(view.effect_mask_shader, view.effect_mask_visibility, view.visible_mask.texture)
}

effect_fallback_compact_visible :: proc(app: ^App, pos: Vec2) -> bool {
	if app == nil do return false
	x,y := int(pos.x),int(pos.y)
	for dx in -1..=1 {
		for dy in -1..=1 {
			nx,ny := x+dx,y+dy
			if !dungeon_in_bounds(nx,ny) || !app.run.visible[nx][ny] do return false
		}
	}
	return true
}

@(private = "file")
begin_effect_visibility :: proc(view: ^View, app: ^App, compact_fallback := false, origin := Vec2{}) -> (ok, active: bool) {
	if app != nil && app.dev_reveal do return true, false
	// Without fragment clipping, only compact gameplay-critical cues may draw,
	// and only when the full surrounding tile footprint is live-visible. Wide
	// decorative effects stay fail-closed rather than crossing the LOS frontier.
	if view == nil || !view.effect_mask_shader_ready || !view.visible_mask.ready {
		return compact_fallback && effect_fallback_compact_visible(app,origin),false
	}
	// raylib's auxiliary sampler bindings are batch-scoped. World sprites drawn
	// after the frame-level uniform update may flush that batch, so bind the live
	// mask immediately before each effect batch rather than relying on persistence.
	rl.SetShaderValueTexture(view.effect_mask_shader,view.effect_mask_visibility,view.visible_mask.texture)
	rl.BeginShaderMode(view.effect_mask_shader)
	return true, true
}

@(private = "file")
end_effect_visibility :: proc(active: bool) {
	if active do rl.EndShaderMode()
}

@(private = "file")
visual_mask_screen_rect :: proc(view: ^View) -> rl.Rectangle {
	if view == nil do return {}
	site_world := Vec2{
		-f32(VISUAL_LATTICE_OFFSET * TILE_HALF_W),
		f32(TILE_HALF_H),
	}
	site_screen := rl.GetWorldToScreen2D(rl.Vector2(site_world), view.camera)
	su := f32(TILE_HALF_W) * view.camera.zoom
	sv := f32(TILE_HALF_H) * view.camera.zoom
	return {
		site_screen.x-su*.5,site_screen.y-sv*.5,
		f32(VISUAL_LATTICE_SIZE)*su,f32(VISUAL_LATTICE_SIZE)*sv,
	}
}

@(private = "file")
draw_visual_mask_screen :: proc(view: ^View, mask: ^Visual_Mask, tint: rl.Color) {
	if view == nil || mask == nil || !mask.ready || !rl.IsTextureValid(mask.texture) do return
	dst := visual_mask_screen_rect(view)
	rl.DrawTexturePro(
		mask.texture,
		{0, 0, f32(VISUAL_LATTICE_SIZE), f32(VISUAL_LATTICE_SIZE)},
		dst,
		{0, 0}, 0, tint,
	)
}

@(private = "file")
ensure_radial_texture :: proc(view: ^View) {
	if view == nil || view.radial_ready do return
	img := rl.GenImageGradientRadial(256, 256, 0, rl.WHITE, rl.BLANK)
	view.light_tex = rl.LoadTextureFromImage(img)
	rl.UnloadImage(img)
	if rl.IsTextureValid(view.light_tex) {
		rl.SetTextureFilter(view.light_tex, .BILINEAR)
		view.radial_ready = true
	}
}

@(private = "file")
ensure_light_resources :: proc(view: ^View) -> bool {
	if view == nil do return false
	ensure_radial_texture(view)
	ensure_visual_mask(&view.explored_mask)
	ensure_visual_mask(&view.visible_mask)
	sw := rl.GetScreenWidth()
	sh := rl.GetScreenHeight()
	if view.lightmap.texture.width != sw || view.lightmap.texture.height != sh ||
		!rl.IsRenderTextureValid(view.lightmap) || !rl.IsRenderTextureValid(view.light_glow) {
		new_lightmap := rl.LoadRenderTexture(sw, sh)
		new_glow := rl.LoadRenderTexture(sw, sh)
		if !rl.IsRenderTextureValid(new_lightmap) || !rl.IsRenderTextureValid(new_glow) {
			if rl.IsRenderTextureValid(new_lightmap) do rl.UnloadRenderTexture(new_lightmap)
			if rl.IsRenderTextureValid(new_glow) do rl.UnloadRenderTexture(new_glow)
			return false
		}
		if view.lightmap.id != 0 do rl.UnloadRenderTexture(view.lightmap)
		if view.light_glow.id != 0 do rl.UnloadRenderTexture(view.light_glow)
		view.lightmap = new_lightmap
		view.light_glow = new_glow
	}
	return view.radial_ready && view.explored_mask.ready && view.visible_mask.ready &&
		rl.IsRenderTextureValid(view.lightmap) && rl.IsRenderTextureValid(view.light_glow)
}

// One light: the shared radial gradient stretched into an iso-squashed
// ellipse at a world position (feet space, lifted to body height).
@(private = "file")
draw_light :: proc(view: ^View, tile_pos: Vec2, radius_tiles: f32, tint: rl.Color, lift: f32) {
	world := rl.Vector2(world_from_tile(tile_pos)) - rl.Vector2{0, lift}
	screen := rl.GetWorldToScreen2D(world, view.camera)
	rx := radius_tiles * TILE_W * view.camera.zoom
	ry := rx * 0.5
	dst := rl.Rectangle{screen.x - rx, screen.y - ry, rx * 2, ry * 2}
	rl.DrawTexturePro(view.light_tex, {0, 0, 256, 256}, dst, {0, 0}, 0, tint)
}

@(private = "file")
draw_light_tile :: proc(view: ^View, x, y: int, tint: rl.Color) {
	top := rl.GetWorldToScreen2D(rl.Vector2(world_from_tile({f32(x)+.5,f32(y)})), view.camera)
	right := rl.GetWorldToScreen2D(rl.Vector2(world_from_tile({f32(x)+1,f32(y)+.5})), view.camera)
	bottom := rl.GetWorldToScreen2D(rl.Vector2(world_from_tile({f32(x)+.5,f32(y)+1})), view.camera)
	left := rl.GetWorldToScreen2D(rl.Vector2(world_from_tile({f32(x),f32(y)+.5})), view.camera)
	rl.DrawTriangle(top,left,bottom,tint)
	rl.DrawTriangle(top,bottom,right,tint)
}

@(private = "file")
update_lightmap :: proc(view: ^View, app: ^App, alpha: f32) -> bool {
	if !ensure_light_resources(view) do return false
	run := &app.run
	if !run.dark_floor {
		visual_mask_sync(&view.explored_mask, app, true, view.frame_dt)
	}

	// Radial sources first, then multiply them by the authoritative live LOS
	// field. This prevents projectile/static/player light from exposing another
	// room while retaining a bilinear, temporally eased edge.
	rl.BeginTextureMode(view.light_glow)
	rl.ClearBackground(rl.BLACK)
	rl.BeginBlendMode(.ADDITIVE)
	player := &run.player
	feet := player.prev_pos + (player.pos - player.prev_pos) * alpha
	radius: f32 = run.dark_floor ? LIGHT_RADIUS_DARK : LIGHT_RADIUS_LIT
	world_time := f32(app.tick) * SIM_DT
	lantern_strength := .92 + .08 * math.sin(world_time * 1.6)
	draw_light(view, feet, radius, rl.Fade(rl.Color{255, 224, 168, 255}, lantern_strength), 20)

	stairs_pos := Vec2{f32(run.dungeon.stairs.x) + 0.5, f32(run.dungeon.stairs.y) + 0.5}
	if app.dev_reveal || tile_pos_visible(app, stairs_pos) {
		draw_light(view, stairs_pos, 2.2, {240, 190, 120, 235}, 0)
	}
	story_relic := &run.story_runtime.relic
	if story_content_enabled(run) && story_relic.present && !story_relic.collected &&
		(app.dev_reveal || tile_pos_visible(app, story_relic.position)) {
		pulse := .72 + .18 * math.sin(world_time * 4.1 + story_relic.position.x)
		draw_light(view, story_relic.position, 1.55, rl.Fade(rl.Color(run.story.accent), pulse), 8)
	}
	for &p in run.projectiles {
		if !app.dev_reveal && !tile_pos_visible(app, p.pos) do continue
		pf := p.prev_pos + (p.pos - p.prev_pos) * alpha
		draw_light(view, pf, 1.1, rl.Fade(rl.Color(p.color), 0.8), PROJECTILE_LIFT)
	}
	// Oathbound minibosses carry a restrained body light. It is rendered into
	// the same live-LOS-clipped target as every other source, so the glow never
	// announces a miniboss through walls or remembered fog.
	for &enemy in run.enemies {
		if enemy.hp <= 0 || !visual_miniboss_effect_enabled(enemy.role) do continue
		if !app.dev_reveal && !tile_pos_visible(app, enemy.pos) do continue
		efeet := enemy.prev_pos + (enemy.pos - enemy.prev_pos) * alpha
		phase := visual_miniboss_effect_phase(enemy.entity_id) * math.TAU
		pulse := .30 + .06 * math.sin(world_time * 2.2 + phase)
		draw_light(view, efeet, 1.35, rl.Fade(rl.Color(enemy.color), pulse), 13)
	}
	// Semantic feel lights join the same pre-mask glow target as every other
	// source. The live-LOS multiply below clips their complete footprint, not
	// merely their origin, so a cast can never illuminate an unseen room.
	for &event in run.feel {
		profile := feel_light_profile(&event)
		life := feel_light_life(&event, profile)
		if profile.enabled && life > 0 {
			source_visible := tile_pos_visible(app, event.pos)
			if feel_event_visible(&event, source_visible, app.dev_reveal) {
				draw_light(
					view,event.pos,profile.radius,
					rl.Fade(rl.Color(event.color),profile.intensity*life),profile.lift,
				)
			}
		}
		if event.kind != .Nova || !event.engulf_room do continue
		room, found := room_at(&run.dungeon,event.pos.x,event.pos.y)
		if !found do continue
		for x in room.x ..< room.x+room.w {
			for y in room.y ..< room.y+room.h {
				strength := visual_nova_room_flash_strength(&event,{f32(x)+.5,f32(y)+.5})
				if strength <= 0 do continue
				draw_light_tile(view,x,y,rl.Fade(rl.Color(event.color),.42*strength))
			}
		}
	}
	if sconces,found:=bar_sconce_positions(&run.dungeon);found {
		for pos,i in sconces do if app.dev_reveal||tile_pos_visible(app,pos) {
			flicker := .90 + .10 * math.sin(world_time * 2.1 + f32(i) * 1.7)
			draw_light(view,pos,1.65,rl.Fade(rl.Color{255,174,92,255},.80*flicker),10)
		}
		if !run.refuge.bar_toasted {
			if barrel,barrel_found:=run_barrel_tile(run);barrel_found {
				pos:=Vec2{f32(barrel.x)+.5,f32(barrel.y)+.5}
				if app.dev_reveal||tile_pos_visible(app,pos) do draw_light(view,pos,1.0,{255,190,105,150},6)
			}
		}
	}
	hall_layout := hall_furnishing_layout(&run.dungeon)
	for i in 0 ..< hall_layout.count {
		if hall_layout.kinds[i] != .Brazier do continue
		tile := hall_layout.tiles[i]
		pos := Vec2{f32(tile.x)+.5,f32(tile.y)+.5}
		if app.dev_reveal || tile_pos_visible(app,pos) {
			flicker := .82 + .18 * math.sin(world_time * 6.4 + f32(tile.x*3+tile.y))
			draw_light(view,pos,1.85,rl.Fade(rl.Color{255,166,76,255},.82*flicker),10)
		}
	}
	if garden,found:=special_room_for_kind(&run.dungeon,.Garden);found {
		center:=room_center(run.dungeon.rooms_buf[garden.room_index])
		pos:=Vec2{f32(center.x)+.5,f32(center.y)+.5}
		if app.dev_reveal||tile_pos_visible(app,pos) do draw_light(view,pos,1.5,{126,214,92,125},4)
	}
	// Shrine identity lights (population.py:415-429): per-kind hint color,
	// steady, retained after use exactly like pygame. The LOS multiply below
	// keeps unseen shrines from announcing themselves.
	for &shrine in run.shrines {
		if !app.dev_reveal && !tile_pos_visible(app, shrine.pos) do continue
		draw_light(view, shrine.pos, SHRINE_LIGHT_RADIUS, rl.Fade(rl.Color(SHRINE_DEFS[shrine.kind].color), SHRINE_LIGHT_INTENSITY), 8)
	}
	for &number in run.numbers {
		if number.kind!=.Garden_Heal || (!app.dev_reveal && !tile_pos_visible(app,number.pos)) do continue
		strength:=clamp(1-number.age/DAMAGE_NUMBER_SECONDS,0,1)
		draw_light(view,number.pos,1.2,rl.Fade(rl.Color{126,214,92,255},strength*.5),8)
	}
	rl.EndBlendMode()
	rl.BeginBlendMode(.MULTIPLIED)
	draw_visual_mask_screen(view, &view.visible_mask, rl.WHITE)
	rl.EndBlendMode()
	rl.EndTextureMode()

	// Ambient is theme-colored and depth-scaled, stamped only into remembered
	// terrain (or live LOS on dark floors). The pre-clipped glow then adds local
	// warmth without crossing the FOW/LOS frontier.
	rl.BeginTextureMode(view.lightmap)
	rl.ClearBackground(rl.BLACK)
	rl.BeginBlendMode(.ADDITIVE)
	ambient := rl.Color(visual_theme_ambient(&THEMES[run.theme_index], run.depth, run.dark_floor))
	ambient_mask := run.dark_floor ? &view.visible_mask : &view.explored_mask
	draw_visual_mask_screen(view, ambient_mask, ambient)
	rl.DrawTextureRec(
		view.light_glow.texture,
		{0, 0, f32(view.light_glow.texture.width), -f32(view.light_glow.texture.height)},
		{0, 0}, rl.WHITE,
	)
	rl.EndBlendMode()
	rl.EndTextureMode()
	return true
}

// --- World -----------------------------------------------------------------

@(private = "file")
Draw_Kind :: enum {
	Wall_Block,
	Door_Block,
	Player,
	Enemy,
	Familiar,
	Story_Guest,
	Lossless_Soul,
	Projectile,
	Ground_Item,
	Story_Relic,
	Bell,
	Trap,
	Shrine,
	Secret,
	Special_Actor,
	Prop,
	Hall_Furnishing,
	Feel,
}

// Flat draw-list item; a union would be overkill for these variants.
@(private = "file")
Draw_Item :: struct {
	depth: f32,
	kind:  Draw_Kind,
	tile:  Vec2, // blocks
	feet:  Vec2, // sprites/projectiles
	index: int, // enemy/projectile array index
	dim:   bool, // explored-but-unseen (fog memory)
	scale: f32, // optional per-instance prop scale; zero means 1
}

@(private = "file")
Ghost_Actor_Kind :: enum {
	Player,
	Enemy,
	Familiar,
	Story_Relic,
}

@(private = "file")
Ghost_Actor :: struct {
	depth:     f32,
	kind:      Ghost_Actor_Kind,
	index:     int,
	key:       u64,
	tex:       rl.Texture2D,
	src:       rl.Rectangle,
	dst:       rl.Rectangle,
	feet:      Vec2,
	big:       bool,
	tint:      rl.Color,
}

@(private = "file")
Ghost_Occluder :: struct {
	depth:     f32,
	rect:      rl.Rectangle,
	open_door: bool,
	tile:      Vec2,
}

// Build the small per-frame overlay map once, before the floor pass. Pygame
// keeps the seeded floor variant and adds one of eight material-glow overlays;
// ordinary tiles outside the crest and all special-room slabs stay untouched.
@(private = "file")
story_guidance_frame_map :: proc(run: ^Run, peak_frame: int) -> (frames: [MAP_W][MAP_H]u8) {
	if !story_content_enabled(run) || run.player.moving || peak_frame <= 0 do return
	_, enabled := story_route_target(run)
	if !enabled do return
	path := story_relic_guidance_path(run)
	tile_count := len(path)-2
	if tile_count <= 0 do return
	for order in 0..<tile_count {
		point := path[order+1]
		if !dungeon_in_bounds(point.x,point.y) do continue
		frame := guidance_wave_frame(order,tile_count,peak_frame,run.player.guidance_idle_elapsed,false)
		if frame > 0 do frames[point.x][point.y] = u8(frame)
	}
	return
}

// Ground pass is painter-order-free (flat), then everything with height is
// depth-sorted: blocks by tile center (x+y+1), sprites by feet (x+y).
@(private = "file")
draw_world :: proc(view: ^View, app: ^App, assets: ^Assets, alpha: f32) {
	d := &app.run.dungeon
	theme := &THEMES[app.run.theme_index]
	x0, x1, y0, y1 := visible_tile_bounds(view)

	floor_sprite := &assets.world[.Floor]
	guiding_overlay_sprite := &assets.world[.Guiding_Overlay]
	stairs_sprite := &assets.world[.Stairs]
	world_time := f32(app.tick) * SIM_DT
	guidance_frames := story_guidance_frame_map(&app.run,guiding_overlay_sprite.frame_count)

	items := make([dynamic]Draw_Item, 0, 512, context.temp_allocator)

	dark := app.run.dark_floor
	for y in y0 ..= y1 {
		for x in x0 ..= x1 {
			vis := app.dev_reveal || app.run.visible[x][y]
			known := app.dev_reveal || (dark ? vis : app.run.explored[x][y])
			ground_margin := !known && tile_in_visual_ground_margin(app, view.lighting_ready, x, y)
			prism_margin := !known && (d.tiles[x][y] == .Wall || d.tiles[x][y] == .Closed_Door || d.tiles[x][y] == .Open_Door) && frontier_prism_needed(app,view.lighting_ready,x,y)
			if !known && !ground_margin && !prism_margin do continue
			// Continuous lighting owns memory darkness and the smooth frontier. The
			// old 45% per-sprite tint remains only when the lighting compositor is off.
			dim := !view.lighting_ready && !vis
			tile := Vec2{f32(x), f32(y)}
			floor_variant := visual_floor_variant(app.run.seed, app.run.depth, app.run.floor_epoch, x, y)
			switch d.tiles[x][y] {
			case .Floor:
				floor_key := World_Key.Floor
				if special_key, found := special_room_floor_world_key(special_room_interior_kind(d, x, y)); found && assets.world[special_key].loaded {
					floor_key = special_key
				}
				tile_floor := &assets.world[floor_key]
				if tile_floor.loaded {
					// Keep the tile's seeded base slab. Pygame then source-over blends
					// overlay frame guidance-1; raylib's default alpha blend is the
					// equivalent operation for these matching 512px masters.
					draw_world_sprite(tile_floor, tile, floor_variant, 0, fog_dim(theme_tint(theme.floor, tile_floor.tint, floor_variant), dim))
					guiding_frame := int(guidance_frames[x][y])
					if floor_key == .Floor && guiding_frame > 0 && guiding_overlay_sprite.loaded {
						draw_world_sprite_frame(
							guiding_overlay_sprite,tile,guiding_frame-1,
							fog_dim(theme_tint(theme.floor,guiding_overlay_sprite.tint,floor_variant),dim),
						)
					}
				} else {
					draw_iso_tile_fill(tile, fog_dim(theme_tint(theme.floor, 1, floor_variant), dim))
				}
			case .Stairs:
				if stairs_sprite.loaded {
					if floor_sprite.loaded {
						draw_world_sprite(floor_sprite, tile, floor_variant, 0, fog_dim(theme_tint(theme.floor, floor_sprite.tint, floor_variant), dim))
					}
					draw_world_sprite(stairs_sprite, tile, floor_variant, world_time, fog_dim(theme_tint(theme.stair, stairs_sprite.tint, floor_variant), dim))
				} else {
					draw_iso_tile_fill(tile, fog_dim(theme_tint(theme.floor, 1, floor_variant), dim))
					draw_iso_tile_inset_fill(tile, 0.72, rl.Color{16, 13, 20, 255})
					draw_iso_tile_inset_outline(tile, 0.72, fog_dim(rl.Color(theme.stair), dim))
				}
			case .Open_Door, .Closed_Door:
				if floor_sprite.loaded {
					draw_world_sprite(floor_sprite, tile, floor_variant, 0, fog_dim(theme_tint(theme.floor, floor_sprite.tint, floor_variant), dim))
				} else {
					draw_iso_tile_fill(tile, fog_dim(theme_tint(theme.floor, 1, floor_variant), dim))
				}
				// Margin cells carry ground only under mask value zero. Tall prisms keep
				// the strict gate except for the south-frontier anti-pop exception.
				if known || frontier_prism_needed(app,view.lighting_ready,x,y) do append(&items, Draw_Item{depth = f32(x + y) + VISUAL_WALL_PAINTER_DEPTH_OFFSET, kind = .Door_Block, tile = tile, dim = dim})
			case .Wall:
				// Deep rock (no passable neighbor) stays void: the dungeon
				// reads as carved out of darkness.
				if (known || frontier_prism_needed(app,view.lighting_ready,x,y)) && wall_is_exposed(d, x, y) {
					append(&items, Draw_Item{depth = f32(x + y) + VISUAL_WALL_PAINTER_DEPTH_OFFSET, kind = .Wall_Block, tile = tile, dim = dim})
				}
			}
		}
	}

	player := &app.run.player
	feet := player.prev_pos + (player.pos - player.prev_pos) * alpha
	// Floor-level exact-aim telegraph: drawn after ground art and before every
	// height-bearing draw item. It stays behind actors/props/foreground walls,
	// and no octant sprite-row quantization can feed back into gameplay aim.
	if app.dev_reveal || (view.effect_mask_shader_ready && view.visible_mask.ready) {
		if effect_ok, effect_active := begin_effect_visibility(view, app); effect_ok {
			draw_player_aim_cone(app, feet)
			end_effect_visibility(effect_active)
		}
	} else if effect_fallback_compact_visible(app,feet) {
		draw_player_aim_tick(app,feet)
	}
	// Enemy tells share the same floor-level pass so their additive accents remain
	// below actors and props; the visibility mask clips the nova edge at live LOS.
	draw_enemy_attack_telegraphs(view,app,alpha)

	story_relic := &app.run.story_runtime.relic
	if story_content_enabled(&app.run) && story_relic.present && !story_relic.collected &&
		(app.dev_reveal || tile_pos_visible(app,story_relic.position)) {
		append(&items,Draw_Item{depth=story_relic.position.x+story_relic.position.y-.01,kind=.Story_Relic,feet=story_relic.position})
	}
	append(&items, Draw_Item{depth = feet.x + feet.y, kind = .Player, feet = feet})

	for &enemy, i in app.run.enemies {
		if !app.dev_reveal && !tile_pos_visible(app, enemy.pos) do continue
		efeet := enemy.prev_pos + (enemy.pos - enemy.prev_pos) * alpha
		append(&items, Draw_Item{depth = efeet.x + efeet.y, kind = .Enemy, feet = efeet, index = i})
	}
	for &familiar, i in app.run.familiars {
		if !app.dev_reveal && !tile_pos_visible(app, familiar.pos) do continue
		ffeet := familiar.prev_pos + (familiar.pos-familiar.prev_pos)*alpha
		append(&items, Draw_Item{depth=ffeet.x+ffeet.y, kind=.Familiar, feet=ffeet, index=i})
	}
	// Use fixed-step interpolation when the runtime exposes prev_pos; older story
	// structs fall back at compile time to their current authoritative position.
	// Either shape still joins the same depth sort and strict live-LOS gate.
	for &guest, i in app.run.story_runtime.guests {
		if !guest.alive || guest.depth != app.run.depth do continue
		if !app.dev_reveal && !tile_pos_visible(app,guest.pos) do continue
		gfeet := story_actor_render_pos(&guest,alpha)
		append(&items,Draw_Item{depth=gfeet.x+gfeet.y,kind=.Story_Guest,feet=gfeet,index=i})
	}
	soul := &app.run.story_runtime.soul
	if soul.present && soul.alive && (app.dev_reveal || tile_pos_visible(app,soul.pos)) {
		sfeet := story_actor_render_pos(soul,alpha)
		append(&items,Draw_Item{depth=sfeet.x+sfeet.y,kind=.Lossless_Soul,feet=sfeet})
	}
	for &p, i in app.run.projectiles {
		if !tile_pos_visible(app, p.pos) do continue
		pfeet := p.prev_pos + (p.pos - p.prev_pos) * alpha
		append(&items, Draw_Item{depth = pfeet.x + pfeet.y, kind = .Projectile, feet = pfeet, index = i})
	}
	for &g, i in app.run.ground_items {
		if !tile_pos_visible(app, g.pos) do continue
		append(&items, Draw_Item{depth = g.pos.x + g.pos.y, kind = .Ground_Item, feet = g.pos, index = i})
	}
	for &bell, i in app.run.bells {
		if !tile_pos_visible(app, bell.pos) do continue
		append(&items, Draw_Item{depth=bell.pos.x+bell.pos.y-.01, kind=.Bell, feet=bell.pos, index=i})
	}
	// MX.5 interactables. Hidden traps and unrevealed secrets are skipped
	// before the sort; nothing may leak through FOW (dev reveal exempt for
	// shrines/secrets like other world dressing, never for hidden traps).
	for &trap, i in app.run.traps {
		if !trap.active || trap.reveal_progress <= 0 do continue
		if !app.dev_reveal && !tile_pos_visible(app, trap.pos) do continue
		// Flat plate art sits under anything standing on it (world.py:2530).
		append(&items, Draw_Item{depth=trap.pos.x+trap.pos.y-.02, kind=.Trap, feet=trap.pos, index=i})
	}
	for &shrine, i in app.run.shrines {
		if !app.dev_reveal && !tile_pos_visible(app, shrine.pos) do continue
		append(&items, Draw_Item{depth=shrine.pos.x+shrine.pos.y, kind=.Shrine, feet=shrine.pos, index=i})
	}
	for &secret, i in app.run.secrets {
		if !secret.revealed || secret.opened do continue
		if !app.dev_reveal && !tile_pos_visible(app, secret.pos) do continue
		append(&items, Draw_Item{depth=secret.pos.x+secret.pos.y, kind=.Secret, feet=secret.pos, index=i})
	}
	for &event, i in app.run.feel {
		if event.kind == .Screen_Flash do continue
		if !feel_event_visible(&event, tile_pos_visible(app,event.pos), app.dev_reveal) do continue
		// Pygame's effect layer is +.05: after a same-foot actor, while preserving
		// occlusion by walls and doors farther down the isometric depth axis.
		append(&items,Draw_Item{depth=event.pos.x+event.pos.y+.05,kind=.Feel,feet=event.pos,index=i})
	}
	if app.run.has_shopkeeper {
		keeper:=&app.run.shopkeeper
		pos:=room_npc_interpolated_position(keeper.prev_pos,keeper.pos,alpha)
		if app.dev_reveal || tile_pos_visible(app,keeper.pos) do append(&items,Draw_Item{depth=pos.x+pos.y,kind=.Special_Actor,feet=pos,index=0})
		sign:=shop_sign_position(keeper)
		if app.dev_reveal||tile_pos_visible(app,sign) do append(&items,Draw_Item{depth=sign.x+sign.y,kind=.Prop,feet=sign,index=int(Prop_Key.Shop_Sign)})
		for i in 0..<d.shop_gold.count {
			gold_feet,gold_depth,prop_index,scale := shop_gold_draw_info(d.shop_gold.stacks[i])
			if app.dev_reveal||tile_pos_visible(app,gold_feet) do append(&items,Draw_Item{depth=gold_depth,kind=.Prop,feet=gold_feet,index=prop_index,scale=scale})
		}
	}
	for i in 0..<app.run.ambient_residents.count {
		resident:=&app.run.ambient_residents.items[i]
		if !resident.active||(!app.dev_reveal&&!tile_pos_visible(app,resident.pos)) do continue
		pos:=room_npc_interpolated_position(resident.prev_pos,resident.pos,alpha)
		append(&items,Draw_Item{depth=pos.x+pos.y,kind=.Special_Actor,feet=pos,index=i+1})
	}
	if _,found:=special_room_for_kind(d,.Bar);found {
		layout:=bar_furnishing_layout(d)
		for i in 0..<layout.count {
			tile:=layout.tiles[i]
			prop:=Vec2{f32(tile.x)+.5,f32(tile.y)+.5}
			if app.dev_reveal||tile_pos_visible(app,prop) {
				key:=layout.kinds[i]==.Barrel?Prop_Key.Bar_Barrel:Prop_Key.Bar_Table
				append(&items,Draw_Item{depth=prop.x+prop.y,kind=.Prop,feet=prop,index=int(key)})
			}
		}
		if sconce_positions,has_sconces:=bar_sconce_positions(d);has_sconces {
			for pos,i in sconce_positions do if app.dev_reveal||tile_pos_visible(app,pos) {
				key:=i==0?Prop_Key.Bar_Sconce_L:Prop_Key.Bar_Sconce_R
				// Positioning a mount higher on an isometric face reduces pos.x+pos.y,
				// so derive painter depth from its wall tile instead. The mount must
				// always draw just after that wall and before actors inside the room.
				wall_depth:=f32(int(math.floor(pos.x))+int(math.floor(pos.y)))
				append(&items,Draw_Item{depth=wall_depth+VISUAL_WALL_PAINTER_DEPTH_OFFSET+.18,kind=.Prop,feet=pos,index=int(key)})
			}
		}
	}
	hall_layout := hall_furnishing_layout(d)
	for i in 0 ..< hall_layout.count {
		tile := hall_layout.tiles[i]
		pos := Vec2{f32(tile.x)+.5,f32(tile.y)+.5}
		if app.dev_reveal || tile_pos_visible(app,pos) {
			append(&items,Draw_Item{depth=f32(tile.x+tile.y)+.45,kind=.Hall_Furnishing,feet=pos,index=i})
		}
	}

	// Same-depth semantic effects retain emission order (body death before rank
	// payoff, cast before plant, and so on) across stable queue compaction.
	slice.stable_sort_by(items[:], proc(a, b: Draw_Item) -> bool { return a.depth < b.depth })

	occluders := make([dynamic]Ghost_Occluder, 0, 128, context.temp_allocator)
	ghost_actors := make([dynamic]Ghost_Actor, 0, 48, context.temp_allocator)
	wall_sprite := &assets.world[.Wall]
	for item in items {
		switch item.kind {
		case .Wall_Block:
			sprite := wall_sprite
			x, y := int(item.tile.x), int(item.tile.y)
			left_kind := special_room_interior_kind(d, x, y+1)
			right_kind := special_room_interior_kind(d, x+1, y)
			if special_key, found := special_room_wall_world_key(left_kind, true); found && assets.world[special_key].loaded {
				sprite = &assets.world[special_key]
			}
			if special_key, found := special_room_wall_world_key(right_kind, false); found && assets.world[special_key].loaded {
				sprite = &assets.world[special_key]
			}
			occluder_rect: rl.Rectangle
			if sprite.loaded {
				variant := int(item.tile.x) * 7 + int(item.tile.y) * 13
				// MX.5 wall-face touch: the worn wall_403 master briefly forms a
				// face. Frames 1..6 at 6 fps, then back to the plain variant.
				face := &assets.world[.Wall_Face]
				if app.run.wall_face_timer > 0 && face.loaded && face.frame_count > 1 &&
					int(item.tile.x) == app.run.wall_face_tile.x &&
					int(item.tile.y) == app.run.wall_face_tile.y {
					elapsed := f32(WALL_FACE_SECONDS) - app.run.wall_face_timer
					frame := clamp(1 + int(elapsed * face.fps), 1, face.frame_count - 1)
					occluder_rect = draw_world_sprite(face, item.tile, 0, (f32(frame) + 0.5) / face.fps, fog_dim(theme_tint(theme.wall_top, face.tint, variant), item.dim))
				} else {
					occluder_rect = draw_world_sprite(sprite, item.tile, variant, 0, fog_dim(theme_tint(theme.wall_top, sprite.tint, variant), item.dim))
				}
			} else {
				draw_iso_block(item.tile, WALL_PX,
					rl.Color(theme.wall_top), rl.Color(theme.wall_left), rl.Color(theme.wall_right))
				center := rl.Vector2(world_from_tile(item.tile + {0.5, 0.5}))
				occluder_rect = {center.x-TILE_HALF_W,center.y-WALL_PX-TILE_HALF_H,f32(TILE_W),f32(WALL_PX+TILE_H)}
			}
			if occluder_rect.width > 0 {
				// Authored 512px canvases have generous transparent margins. A tighter
				// body rect rejects those margins as false actor occlusion.
				shrink_x := occluder_rect.width * .22
				shrink_y := occluder_rect.height * .08
				occluder_rect = {occluder_rect.x+shrink_x*.5,occluder_rect.y+shrink_y*.5,occluder_rect.width-shrink_x,occluder_rect.height-shrink_y}
				append(&occluders,Ghost_Occluder{depth=item.depth,rect=occluder_rect,tile=item.tile})
			}
		case .Door_Block:
			door_rect := draw_door(app, assets, item.tile, item.dim)
			if door_rect.width > 0 {
				shrink_x := door_rect.width * .22
				shrink_y := door_rect.height * .08
				door_rect = {door_rect.x+shrink_x*.5,door_rect.y+shrink_y*.5,door_rect.width-shrink_x,door_rect.height-shrink_y}
				append(&occluders,Ghost_Occluder{depth=item.depth,rect=door_rect,open_door=d.tiles[int(item.tile.x)][int(item.tile.y)]==.Open_Door,tile=item.tile})
			}
		case .Player:
			draw_contact_shadow(view,item.feet,34,13,player.moving)
			if bighit_charging(player) {
				charge := clamp(1-player.bighit_charge/BIGHIT_CHARGE_TIME,0,1)
				w := rl.Vector2(world_from_tile(item.feet))
				radius_h := 8+12*charge
				color := bighit_committed(player) ? rl.Color{235,205,120,255} : rl.Color{205,190,165,255}
				ring_alpha := (50+70*charge)/255
				rl.DrawEllipseLinesV(w,radius_h,radius_h*.5,rl.Fade(color,ring_alpha))
			}
			clip := player.moving ? Clip_Kind.Walk : Clip_Kind.Idle
			clip_time := player.moving ? player.anim_time : visual_idle_clip_time(world_time)
			switch player.visual_action {
			case .Attack:
				clip = .Attack
			case .Cast:
				clip = .Cast
			case .Dash:
				clip = .Walk
			case .Pet:
				// Paired petting pose (MX.3); archetypes without a baked pet
				// clip hold the cast pose instead.
				clip = assets.archetypes[player.archetype].clips[.Pet].valid ? .Pet : .Cast
			case .Die:
				clip,clip_time = .Die,player.action_time
			case .Dead:
				clip,clip_time = .Dead,player.action_time
			case .None:
			}
			if player.visual_action == .Attack || player.visual_action == .Cast ||
				player.visual_action == .Dash || player.visual_action == .Pet {
				action_clip := &assets.archetypes[player.archetype].clips[clip]
				clip_time = normalized_action_clip_time(
					player_visual_action_progress(player),
					action_clip.frames,
					action_clip.fps,
				)
			}
			tint := rl.WHITE
			if status_color, active := actor_status_tint(&player.statuses); active do tint = status_color
			if player.hit_flash > 0 {
				tint = {255, u8(255 - 120 * player.hit_flash), u8(255 - 140 * player.hit_flash), 255}
			}
			tex,src,dst,drawn := draw_actor(assets, &assets.archetypes[player.archetype], clip, player.facing, clip_time, item.feet, tint, 0)
			if drawn do append(&ghost_actors,Ghost_Actor{depth=item.depth,kind=.Player,key=0x100000000,tex=tex,src=src,dst=dst,feet=item.feet,tint=tint})
		case .Enemy:
			enemy := &app.run.enemies[item.index]
			sprites := enemy.role == .Boss ? &assets.bosses[enemy.boss_id] : &assets.enemies[enemy.kind]
			clip := enemy.moving ? Clip_Kind.Walk : Clip_Kind.Idle
			clip_time := enemy.moving ? enemy.anim_time : visual_idle_clip_time(world_time,enemy.entity_id)
			// The action pose follows commitment; the windup itself stays grounded
			// in locomotion/idle and is communicated by the feet telegraph below.
			pose := visual_enemy_pose(enemy, sprites.clips[.Attack].valid, sprites.clips[.Cast].valid)
			if pose == .Attack || pose == .Cast {
				clip = pose == .Attack ? Clip_Kind.Attack : Clip_Kind.Cast
				action_clip := &sprites.clips[clip]
				clip_time = normalized_action_clip_time(
					enemy_action_progress(enemy),action_clip.frames,action_clip.fps,
				)
			}
			tint := rl.WHITE
			if status_color, active := actor_status_tint(&enemy.statuses); active do tint = status_color
			draw_contact_shadow(view,item.feet,enemy.big?78:enemy.kind==.Gate_Warden||enemy.kind==.Crypt_Brute?38:32,enemy.big?18:12,enemy.moving)
			compact_cues_visible := app.dev_reveal || effect_fallback_compact_visible(app,item.feet)
			if compact_cues_visible {
				if visual_miniboss_effect_enabled(enemy.role) {
					draw_miniboss_ground_seal(item.feet,rl.Color(enemy.color),world_time,enemy.entity_id)
				} else if enemy.role == .Boss {
					// Boss presentation remains its own rank language; elites no longer
					// inherit a persistent ground treatment.
					w := rl.Vector2(world_from_tile(item.feet))
					ring := rl.Color(enemy.color)
					pulse := 0.5 + 0.3 * math.sin(world_time * 5)
					rl.BeginBlendMode(.ADDITIVE)
					radius_h: f32 = enemy.big ? 34 : 18
					rl.DrawEllipse(i32(w.x),i32(w.y),radius_h,radius_h*.5,rl.Fade(ring,.28*pulse))
					rl.EndBlendMode()
				}
			}

			miniboss_effect := Miniboss_Sprite_Effect{}
			if visual_miniboss_effect_enabled(enemy.role) {
				miniboss_effect = {
					enabled=true,color=rl.Color(enemy.color),world_time=world_time,stable_id=enemy.entity_id,
				}
			}
			tex,src,dst,drawn := draw_actor(
				assets,sprites,clip,enemy.facing,clip_time,item.feet,tint,enemy.hit_flash,miniboss_effect,
			)
			if drawn {
				key := 0x200000000 + u64(enemy.entity_id)
				if enemy.entity_id == 0 do key += u64(item.index+1)
				append(&ghost_actors,Ghost_Actor{depth=item.depth,kind=.Enemy,index=item.index,key=key,tex=tex,src=src,dst=dst,feet=item.feet,big=enemy.big,tint=tint})
			}
			if compact_cues_visible do draw_enemy_bar(enemy,sprites,item.feet)
		case .Familiar:
			familiar := &app.run.familiars[item.index]
			sprites:^Actor_Sprites
			switch familiar.kind {
			case .Wisp:              sprites=&assets.familiar_wisp
			case .Crow:              sprites=&assets.familiar_crow
			case .Spirit_Beast:      sprites=&assets.spirit_beast
			case .Bar_Dancer:        sprites=&assets.bar_dancer
			case .Soulless_Clanker:  sprites=&assets.soulless_clanker
			case .String:             sprites=&assets.string_guitarist
			}
			clanker:=familiar.kind==.Soulless_Clanker
			attack_clip_kind:=clanker?Clip_Kind.Interact:Clip_Kind.Attack
			attacking := visual_familiar_uses_attack_pose(familiar.attack_anim_timer, sprites.clips[attack_clip_kind].valid)
			clip := attacking ? attack_clip_kind : familiar.moving ? Clip_Kind.Walk : Clip_Kind.Idle
			clip_time := (clip == .Idle) ? visual_idle_clip_time(world_time,familiar.entity_id) : familiar.anim_time
			if familiar.kind == .Bar_Dancer && clip != .Walk {
				// Her baked clips are walk/dance: she dances whether idling or
				// striking, on the world clock so the loop never stalls.
				clip = .Dance
				clip_time = world_time
			}
			if familiar.pet_anim_timer > 0 && sprites.clips[.Pet].valid {
				// The soothing ritual runs its own clock (MX.3), like Attack below.
				pet_clip := &sprites.clips[.Pet]
				pet_elapsed := max(0, SPIRIT_BEAST_PET_SECONDS-familiar.pet_anim_timer)
				clip = .Pet
				clip_time = normalized_action_clip_time(
					pet_elapsed/SPIRIT_BEAST_PET_SECONDS,
					pet_clip.frames,
					pet_clip.fps,
				)
			} else if clip == .Attack || clip == .Interact {
				// The attack clip runs on its own clock; locomotion anim_time
				// stalls while the familiar attacks in place (MX.3).
				attack_clip := &sprites.clips[clip]
				attack_elapsed := max(0, FAMILIAR_ATTACK_ANIMATION_TIME-familiar.attack_anim_timer)
				clip_time = normalized_action_clip_time(
					attack_elapsed/FAMILIAR_ATTACK_ANIMATION_TIME,
					attack_clip.frames,
					attack_clip.fps,
				)
			}
			shadow_w:=familiar.champion?f32(30):familiar.kind==.Spirit_Beast?f32(26):clanker?f32(13):f32(18)
			shadow_h:=clanker?f32(6):f32(10)
			draw_contact_shadow(view,item.feet,shadow_w,shadow_h,familiar.moving)
			tex,src,dst,drawn := draw_actor(assets, sprites, clip, familiar.facing, clip_time, item.feet, rl.WHITE, 0)
			if drawn {
				key := 0x300000000 + u64(familiar.entity_id)
				if familiar.entity_id == 0 do key += u64(item.index+1)
				append(&ghost_actors,Ghost_Actor{depth=item.depth,kind=.Familiar,index=item.index,key=key,tex=tex,src=src,dst=dst,feet=item.feet,tint=rl.WHITE})
			}
			if familiar.hp < familiar.max_hp {
				w := rl.Vector2(world_from_tile(item.feet))
				frac := clamp(f32(familiar.hp)/f32(familiar.max_hp),0,1)
				bar_color := familiar.kind == .Spirit_Beast ? rl.Color{145,214,105,255} : rl.Color{160,235,230,255}
				head := sprites.loaded ? sprites.canvas_world * sprites.anchor.y * .85 : f32(24)
				if effect_ok,effect_active := begin_effect_visibility(view,app,true,item.feet);effect_ok {
					rl.DrawRectangleV({w.x-12,w.y-head-5},{24,3},rl.Fade(rl.BLACK,.65))
					rl.DrawRectangleV({w.x-12,w.y-head-5},{24*frac,3},bar_color)
					end_effect_visibility(effect_active)
				}
			}
		case .Story_Guest:
			guest := &app.run.story_runtime.guests[item.index]
			motion := &guest.motion
			facing := motion.facing
			if facing == {} do facing = {1,1}
			clip,clip_time := room_npc_visual_clip(motion,&assets.story_guest,world_time)
			accent := story_world_accent(&app.run)
			w := rl.Vector2(world_from_tile(item.feet))
			if !guest.resolved {
				pulse := .5 + .5 * math.sin(world_time*3.2+item.feet.x)
				rl.DrawEllipseLinesV(w,16,8,rl.Fade(accent,.09+.08*pulse))
			}
			draw_contact_shadow(view,item.feet,26,10,motion.moving)
			tint := guest.resolved ? rl.Color{210,205,220,255} : rl.WHITE
			if story_actor_sprites_drawable(&assets.story_guest,clip) {
				draw_actor(assets,&assets.story_guest,clip,facing,clip_time,item.feet,tint,0)
			} else {
				draw_story_actor_fallback(item.feet,facing,accent,false,motion.moving,world_time)
			}
			if guest.ally && guest.max_hp > 0 && guest.hp < guest.max_hp {
				draw_story_actor_health_bar(&assets.story_guest,item.feet,guest.hp,guest.max_hp,{166,205,126,255})
			}
		case .Lossless_Soul:
			keeper := &app.run.story_runtime.soul
			motion := &keeper.motion
			facing := motion.facing
			if facing == {} do facing = {1,1}
			clip,clip_time := visual_lossless_soul_clip(
				keeper.armed,motion.moving,motion.dancing,motion.anim_time,world_time,
			)
			accent := story_world_accent(&app.run)
			w := rl.Vector2(world_from_tile(item.feet))
			pulse := .5 + .5 * math.sin(world_time*2.4+item.feet.y)
			rl.BeginBlendMode(.ADDITIVE)
			rl.DrawEllipse(i32(w.x),i32(w.y),18,9,rl.Fade(accent,.08+.08*pulse))
			rl.EndBlendMode()
			draw_contact_shadow(view,item.feet,25,10,motion.moving)
			if story_actor_sprites_drawable(&assets.lossless_soul,clip) {
				draw_actor(assets,&assets.lossless_soul,clip,facing,clip_time,item.feet,rl.WHITE,0)
			} else {
				draw_story_actor_fallback(item.feet,facing,accent,true,motion.moving,world_time)
			}
			if keeper.armed && keeper.max_hp > 0 && keeper.hp < keeper.max_hp {
				draw_story_actor_health_bar(&assets.lossless_soul,item.feet,keeper.hp,keeper.max_hp,{142,190,235,255})
			}
		case .Projectile:
			if effect_ok, effect_active := begin_effect_visibility(view, app, true, item.feet); effect_ok {
				draw_projectile(&app.run.projectiles[item.index], item.feet, alpha, trails=effect_active||app.dev_reveal)
				end_effect_visibility(effect_active)
			}
		case .Ground_Item:
			draw_contact_shadow(view,item.feet,22,9,false)
			draw_ground_item(assets, &app.run.ground_items[item.index])
		case .Story_Relic:
			tex,src,dst:=draw_story_relic_world(view,assets,&app.run,world_time)
			if dst.width>0&&dst.height>0 {
				append(&ghost_actors,Ghost_Actor{
					depth=item.depth,kind=.Story_Relic,key=0x400000000,
					tex=tex,src=src,dst=dst,feet=item.feet,tint=story_world_accent(&app.run),
				})
			}
		case .Bell:
			bell := &app.run.bells[item.index]
			armed := bell.arm_timer <= 0
			color := rl.Color(DAMAGE_TYPE_COLORS[.Shadow])
			prop := &assets.props[.Ambush_Bell]
			if prop.loaded && prop.tex.id != 0 {
				draw_contact_shadow(view,item.feet,24,9,false)
				tint := rl.WHITE
				if !armed do tint = rl.Fade(rl.WHITE,.55)
				draw_prop_asset(prop,item.feet,tint)
				// Armed glow ring at the bell's base.
				w := rl.Vector2(world_from_tile(item.feet))
				rl.DrawEllipseLinesV(w,12,6,rl.Fade(color,armed?.60:.25))
			} else {
				draw_contact_shadow(view,item.feet,24,9,false)
				w := rl.Vector2(world_from_tile(item.feet))
				rl.DrawEllipse(i32(w.x),i32(w.y),armed?10:7,armed?5:3,rl.Fade(color,armed?.75:.40))
			}
		case .Trap:
			draw_trap(assets, &app.run.traps[item.index], world_time)
		case .Shrine:
			draw_shrine(view, assets, &app.run.shrines[item.index], world_time)
		case .Secret:
			draw_secret(view, app, assets, &app.run.secrets[item.index], world_time)
		case .Special_Actor:
			motion:^Room_Npc_Motion
			sprites:^Actor_Sprites
			frog:=false
			bar_dancer:=false
			if item.index==0 {
				motion=&app.run.shopkeeper.motion
				sprites=&assets.shopkeeper
			} else {
				resident:=&app.run.ambient_residents.items[item.index-1]
				motion=&resident.motion
				frog=resident.kind==.Garden_Frog
				switch resident.kind {
				case .Bar_Dancer:
					sprites=&assets.bar_dancer
					bar_dancer=true
				case .Garden_Frog:      sprites=&assets.garden_frog
				case .Soulless_Clanker: sprites=&assets.soulless_clanker
				case .String:            sprites=&assets.string_guitarist
				}
			}
			facing:=motion.facing
			if facing=={} do facing={0,1}
			gesture_clip:=Clip_Kind.Dance
			clanker:=item.index>0 && app.run.ambient_residents.items[item.index-1].kind==.Soulless_Clanker
			string_guitarist:=item.index>0 && app.run.ambient_residents.items[item.index-1].kind==.String
			if clanker do gesture_clip=.Interact
			if string_guitarist do gesture_clip=.Idle
			clip,clip_time:=room_npc_visual_clip(motion,sprites,world_time,gesture_clip,bar_dancer)
			draw_contact_shadow(view,item.feet,frog?18:clanker?13:26,frog?8:clanker?6:11,motion.moving)
			draw_actor(assets,sprites,clip,facing,clip_time,item.feet,rl.WHITE,0)
		case .Prop:
			prop_key := Prop_Key(item.index)
			if prop_key != .Bar_Sconce_L && prop_key != .Bar_Sconce_R {
				shadow_w: f32 = prop_key == .Bar_Table ? 42 : prop_key == .Shop_Sign ? 30 : 22
				shadow_h: f32 = prop_key == .Bar_Table ? 14 : 9
				draw_contact_shadow(view,item.feet,shadow_w,shadow_h,false)
			}
			draw_prop_asset(&assets.props[prop_key],item.feet,scale=item.scale)
		case .Hall_Furnishing:
			layout := hall_furnishing_layout(d)
			if 0 <= item.index && item.index < layout.count {
				draw_hall_furnishing(view,assets,layout.kinds[item.index],item.feet,story_world_accent(&app.run),world_time)
			}
		case .Feel:
			if effect_ok, effect_active := begin_effect_visibility(view, app); effect_ok {
				draw_world_feel_event(&app.run.feel[item.index])
				end_effect_visibility(effect_active)
			}
		}
	}

	draw_actor_wall_ghosts(view,app,ghost_actors[:],occluders[:])
	// Repeat live projectiles and enemy tells above wall geometry at restrained
	// opacity. Their ordinary depth-sorted passes remain primary; these are only
	// x-ray traces for effects already inside the live visibility field.
	draw_projectiles_through_walls(app,alpha)
	draw_enemy_attack_telegraphs_through_walls(app,alpha)
	if app.options.mist_enabled {
		// The shader clock follows simulation time so inventory, pause, and story
		// modals freeze both the disturbance field and its drifting noise body.
		mist_time := app.run.player.sim_elapsed
		mist_live := app.mode == .Playing && !app.inventory_open && !app.character_open && !app.shop_open &&
			!app_play_modal_open(app)
		if mist_live do mist_time += alpha * SIM_DT
		mist_draw(view,mist_time)
	}
	draw_item_labels(view,app)
	draw_damage_numbers(view,app)
}

@(private = "file")
story_actor_render_pos :: proc(actor: ^$T, alpha: f32) -> Vec2 {
	when intrinsics.type_has_field(T,"prev_pos") {
		return room_npc_interpolated_position(actor.prev_pos,actor.pos,alpha)
	}
	return actor.pos
}

@(private = "file")
room_npc_visual_clip :: proc(
	motion: ^Room_Npc_Motion,
	sprites: ^Actor_Sprites,
	world_time: f32,
	gesture_clip := Clip_Kind.Dance,
	always_gesture := false,
) -> (clip: Clip_Kind, clip_time: f32) {
	if motion == nil do return .Idle,0
	if motion.moving {
		return .Walk,motion.anim_time
	}
	if always_gesture {
		return gesture_clip,world_time
	}
	if motion.dancing {
		return gesture_clip,motion.anim_time
	}
	// Frogs and the Soul have no Idle clip. Their waiting pose is exactly Dance
	// frame zero; only an explicit Dancing state advances it.
	if sprites != nil && sprites.clips[.Idle].valid {
		return .Idle,visual_idle_clip_time(world_time,u32(motion.seed))
	}
	return .Dance,0
}

@(private = "file")
story_world_accent :: proc(run: ^Run) -> rl.Color {
	if run != nil {
		if run.story_runtime.initialized do return rl.Color(run.story.accent)
		return rl.Color(THEMES[clamp(run.theme_index,0,len(THEMES)-1)].accent)
	}
	return COLOR_HOVER
}


@(private = "file")
story_actor_sprites_drawable :: proc(sprites: ^Actor_Sprites, preferred: Clip_Kind) -> bool {
	if sprites == nil || !sprites.loaded do return false
	return sprites.clips[preferred].valid || sprites.clips[.Idle].valid ||
		sprites.clips[.Walk].valid || sprites.clips[.Dance].valid
}

// Distinct raylib-native silhouettes keep story actors identifiable if the
// optional actor sheets are absent or fail validation.
@(private = "file")
draw_story_actor_fallback :: proc(
	feet, facing: Vec2,
	accent: rl.Color,
	soul, moving: bool,
	world_time: f32,
) {
	bob: f32
	if !moving do bob = (math.sin(world_time*3.1+feet.x)*.5+.5)*1.5
	base := rl.Vector2(world_from_tile(feet))-rl.Vector2{0,bob}
	dark := rl.Color{u8(f32(accent.r)*.34),u8(f32(accent.g)*.34),u8(f32(accent.b)*.40),255}
	light := rl.Color{
		u8(min(255,int(accent.r)+70)),
		u8(min(255,int(accent.g)+70)),
		u8(min(255,int(accent.b)+70)),255,
	}
	if soul {
		center := base-rl.Vector2{0,16}
		rl.BeginBlendMode(.ADDITIVE)
		rl.DrawCircleV(center,11,rl.Fade(accent,.18))
		rl.DrawCircleV(center,6,rl.Fade(light,.72))
		rl.DrawCircleV(center-rl.Vector2{0,8},4,rl.Fade(rl.WHITE,.88))
		rl.EndBlendMode()
		rl.DrawPoly(center+rl.Vector2{0,8},4,9,45,rl.Fade(dark,.82))
	} else {
		head := base-rl.Vector2{0,25}
		body := base-rl.Vector2{0,12}
		rl.DrawPoly(body,4,13,45,dark)
		rl.DrawRectangleV(head-rl.Vector2{4,1},rl.Vector2{8,9},light)
		rl.DrawRectangleV(head-rl.Vector2{3,0},rl.Vector2{6,6},rl.Color{218,198,176,255})
		rl.DrawLineEx(body-rl.Vector2{8,1},base-rl.Vector2{11,2},2,accent)
	}
	direction := visual_iso_direction(facing)
	if direction != {} {
		origin := base-rl.Vector2{0,10}
		rl.DrawLineEx(origin,origin+rl.Vector2(direction)*8,1,rl.Fade(light,.75))
	}
}

@(private = "file")
draw_story_actor_health_bar :: proc(sprites: ^Actor_Sprites, feet: Vec2, hp, max_hp: int, color: rl.Color) {
	if max_hp <= 0 do return
	world := rl.Vector2(world_from_tile(feet))
	head := sprites != nil && sprites.loaded ? sprites.canvas_world*sprites.anchor.y*.84 : f32(38)
	frac := clamp(f32(max(hp,0))/f32(max_hp),0,1)
	rl.DrawRectangleV({world.x-12,world.y-head-5},{24,3},rl.Fade(rl.BLACK,.65))
	rl.DrawRectangleV({world.x-12,world.y-head-5},{24*frac,3},color)
}

@(private = "file")
draw_story_relic_world :: proc(
	view: ^View,
	assets: ^Assets,
	run: ^Run,
	world_time: f32,
) -> (tex: rl.Texture2D, src, dst: rl.Rectangle) {
	if run == nil do return
	relic := &run.story_runtime.relic
	if !relic.present || relic.collected do return
	accent := story_world_accent(run)
	world := rl.Vector2(world_from_tile(relic.position))
	pulse := .5+.5*math.sin(world_time*5.2+relic.position.x)
	bob := math.sin(world_time*3.5+relic.position.y)*2.2
	center := world-rl.Vector2{0,15+bob}

	rl.BeginBlendMode(.ADDITIVE)
	rl.DrawEllipse(i32(world.x),i32(world.y),20,10,rl.Fade(accent,.18+.18*pulse))
	rl.DrawEllipse(i32(world.x),i32(world.y),10,5,rl.Fade(rl.WHITE,.06+.08*pulse))
	rl.EndBlendMode()
	draw_contact_shadow(view,relic.position,25,10,false)

	icon := story_relic_icon_asset(assets,relic.relic)
	if icon != nil && icon.valid && icon.tex.id != 0 {
		h: f32 = STORY_RELIC_WORLD_ICON_HEIGHT
		w := icon.tex.height > 0 ? h*f32(icon.tex.width)/f32(icon.tex.height) : h
		tex=icon.tex
		src={0,0,f32(icon.tex.width),f32(icon.tex.height)}
		dst={center.x-w*.5,center.y-h*.5,w,h}
		rl.DrawTexturePro(tex,src,dst,{0,0},0,rl.WHITE)
	} else {
		dst={center.x-9,center.y-9,18,18}
		dark := rl.Color{u8(f32(accent.r)*.34),u8(f32(accent.g)*.34),u8(f32(accent.b)*.42),255}
		rl.DrawPoly(center,4,9,45,dark)
		rl.DrawPoly(center,4,5.5,45,accent)
		rl.DrawPolyLinesEx(center,4,9,45,1.2,rl.Fade(rl.WHITE,.72))
	}
	for i in 0 ..< 4 {
		angle := world_time*2.2+f32(i)*math.TAU/4
		mote := center+rl.Vector2{math.cos(angle)*15,math.sin(angle)*7}
		rl.DrawCircleV(mote,1.4,rl.Fade(accent,.72+.18*pulse))
	}
	return
}

STORY_RELIC_WORLD_ICON_HEIGHT :: f32(20)

@(private = "file")
hall_furnishing_prop_key :: proc(kind: Hall_Furnishing_Kind) -> Prop_Key {
	switch kind {
	case .Mirror:     return .Lossless_Soul_Mirror
	case .Chimes:     return .Lossless_Soul_Chimes
	case .Brazier:    return .Lossless_Soul_Brazier
	case .Reliquary:  return .Lossless_Soul_Reliquary
	}
	return .Lossless_Soul_Mirror
}

@(private = "file")
draw_hall_furnishing :: proc(
	view: ^View,
	assets: ^Assets,
	kind: Hall_Furnishing_Kind,
	feet: Vec2,
	accent: rl.Color,
	world_time: f32,
) {
	prop_key := hall_furnishing_prop_key(kind)
	if assets != nil && assets.props[prop_key].loaded {
		shadow_w: f32 = kind == .Mirror ? 34 : kind == .Reliquary ? 36 : 29
		draw_contact_shadow(view,feet,shadow_w,11,false)
		draw_prop_asset(&assets.props[prop_key],feet)
		return
	}

	// Missing optional art retains the former compact procedural vocabulary.
	world := rl.Vector2(world_from_tile(feet))
	dark := rl.Color{35,30,47,255}
	metal := rl.Color{151,126,82,255}
	bright := rl.Color{
		u8(min(255,int(accent.r)+58)),
		u8(min(255,int(accent.g)+58)),
		u8(min(255,int(accent.b)+58)),255,
	}
	switch kind {
	case .Mirror:
		draw_contact_shadow(view,feet,32,11,false)
		rl.DrawRectangleV({world.x-3,world.y-10},{6,10},dark)
		rl.DrawRectangleV({world.x-13,world.y-42},{26,34},metal)
		rl.DrawRectangleV({world.x-10,world.y-39},{20,28},rl.Fade(accent,.78))
		rl.DrawRectangleV({world.x-7,world.y-36},{5,18},rl.Fade(bright,.42))
		rl.DrawRectangleLinesEx({world.x-13,world.y-42,26,34},1,bright)
	case .Chimes:
		draw_contact_shadow(view,feet,27,9,false)
		rl.DrawRectangleV({world.x-2,world.y-35},{4,35},dark)
		rl.DrawRectangleV({world.x-13,world.y-37},{26,4},metal)
		for i in 0 ..< 4 {
			x := world.x-9+f32(i)*6
			length := f32(12+(i&1)*5)
			rl.DrawLineEx({x,world.y-33},{x,world.y-33+length},1,bright)
			rl.DrawTriangle(
				{x,world.y-31+length},
				{x-3,world.y-35+length},
				{x+3,world.y-35+length},metal,
			)
		}
	case .Brazier:
		draw_contact_shadow(view,feet,29,11,false)
		rl.DrawLineEx({world.x-7,world.y-10},{world.x-10,world.y},3,dark)
		rl.DrawLineEx({world.x+7,world.y-10},{world.x+10,world.y},3,dark)
		rl.DrawPoly({world.x,world.y-13},4,12,45,metal)
		rl.DrawRectangleV({world.x-9,world.y-16},{18,5},dark)
		flame := .5+.5*math.sin(world_time*6.4+feet.x)
		rl.BeginBlendMode(.ADDITIVE)
		rl.DrawCircleV({world.x,world.y-23},8,rl.Fade(rl.Color{255,108,42,255},.18+.12*flame))
		rl.DrawTriangle(
			{world.x,world.y-34-flame*3},
			{world.x-6,world.y-18},
			{world.x+6,world.y-18},rl.Color{255,126,48,230},
		)
		rl.DrawTriangle(
			{world.x+1,world.y-29-flame*2},
			{world.x-3,world.y-19},
			{world.x+4,world.y-19},rl.Color{255,226,112,245},
		)
		rl.EndBlendMode()
	case .Reliquary:
		draw_contact_shadow(view,feet,35,12,false)
		rl.DrawRectangleV({world.x-7,world.y-15},{14,15},dark)
		rl.DrawRectangleV({world.x-17,world.y-31},{34,18},metal)
		rl.DrawRectangleV({world.x-14,world.y-28},{28,12},rl.Color{70,54,80,255})
		rl.DrawRectangleLinesEx({world.x-17,world.y-31,34,18},2,bright)
		rl.DrawPoly({world.x,world.y-22},4,4,45,accent)
	}
}

@(private = "file")
draw_enemy_telegraph_arrow :: proc(origin,direction:rl.Vector2,length:f32,color:rl.Color,alpha:f32,opacity_scale:=f32(1)) {
	perpendicular := rl.Vector2{-direction.y,direction.x}
	tail := origin+direction*9
	tip := origin+direction*length
	head_base := tip-direction*4.5
	feather_base := tail-direction*6
	// Keep the low-opacity effect readable through silhouette rather than fill:
	// one shaft, an open arrowhead, and two short tail feathers.
	rl.DrawLineEx(tail,tip,1.2,rl.Fade(color,alpha*.82*opacity_scale))
	rl.DrawLineEx(tip,head_base + perpendicular*2.5,1.4,rl.Fade(color,alpha*opacity_scale))
	rl.DrawLineEx(tip,head_base - perpendicular*2.5,1.4,rl.Fade(color,alpha*opacity_scale))
	rl.DrawLineEx(tail,feather_base + perpendicular*3,1,rl.Fade(color,alpha*.62*opacity_scale))
	rl.DrawLineEx(tail,feather_base - perpendicular*3,1,rl.Fade(color,alpha*.62*opacity_scale))
}

@(private = "file")
draw_enemy_attack_telegraph :: proc(enemy:^Enemy,feet:Vec2,compact:=false,opacity_scale:=f32(1)) {
	plan := visual_enemy_telegraph(enemy)
	if !plan.valid do return
	origin := rl.Vector2(world_from_tile(feet))
	color := rl.Color(DAMAGE_TYPE_COLORS[enemy.damage_type])
	progress := plan.progress
	direction := rl.Vector2(visual_iso_direction(plan.aim))
	if direction == {} do return
	perpendicular := rl.Vector2{-direction.y,direction.x}

	// Match the established Cast/Dash/Slash language: additive color, a small
	// origin pulse, and only a few fine strokes. No opaque danger footprint or UI.
	rl.BeginBlendMode(.ADDITIVE)
	ring_radius := 15-3*progress
	rl.DrawEllipseLinesV(origin,ring_radius,ring_radius*.5,rl.Fade(color,(.13+.10*progress)*opacity_scale))
	for i in 0..<3 {
		angle := f32(i)*math.TAU/3+progress*.8
		mote := origin+rl.Vector2{math.cos(angle)*ring_radius,math.sin(angle)*ring_radius*.5}
		rl.DrawCircleV(mote,1.3,rl.Fade(color,(.10+.08*progress)*opacity_scale))
	}
	if compact {
		rl.EndBlendMode()
		return
	}

	switch plan.kind {
	case .Melee:
		center := origin+direction*(plan.large?f32(23):f32(19))
		radius:f32 = plan.large?15:12
		angle := math.atan2(direction.y,direction.x)*180/math.PI
		rl.DrawRing(center,radius-2,radius,angle-52,angle+52,14,rl.Fade(color,(.15+.12*progress)*opacity_scale))
		stroke_offset := perpendicular*5
		rl.DrawLineEx(origin+direction*8-stroke_offset,center+direction*8-stroke_offset*.35,1,rl.Fade(color,(.07+.07*progress)*opacity_scale))
		rl.DrawLineEx(origin+direction*8+stroke_offset,center+direction*8+stroke_offset*.35,1,rl.Fade(color,(.07+.07*progress)*opacity_scale))
	case .Bolt:
		length:f32 = plan.large?58:48
		draw_enemy_telegraph_arrow(origin,direction,length+progress*7,color,.18+.14*progress,opacity_scale)
	case .Fan:
		tile_perpendicular := Vec2{-plan.aim.y,plan.aim.x}
		count := min(3,plan.projectile_count)
		for i in 0..<count {
			offset:f32
			if count>1 do offset=plan.spread*(f32(i)/f32(count-1)*2-1)
			sample := plan.aim+tile_perpendicular*offset
			sample /= math.hypot(sample.x,sample.y)
			sample_direction := rl.Vector2(visual_iso_direction(sample))
			length:f32 = plan.large?58:48
			draw_enemy_telegraph_arrow(origin,sample_direction,length+progress*6,color,.12+.10*progress,opacity_scale)
		}
	case .Nova:
		radii := visual_iso_radial_radii(plan.attack_range,1)
		pulse := .84+.16*progress
		rl.DrawEllipseLinesV(origin,radii.x,radii.y,rl.Fade(color,(.10+.08*progress)*opacity_scale))
		rl.DrawEllipseLinesV(origin,radii.x*pulse,radii.y*pulse,rl.Fade(color,(.06+.06*progress)*opacity_scale))
	case .None:
	}
	rl.EndBlendMode()
}

@(private = "file")
draw_enemy_attack_telegraphs :: proc(view:^View,app:^App,alpha:f32) {
	if view==nil||app==nil do return
	full := app.dev_reveal||(view.effect_mask_shader_ready&&view.visible_mask.ready)
	if full {
		if effect_ok,effect_active:=begin_effect_visibility(view,app);effect_ok {
			for &enemy in app.run.enemies {
				if enemy.ai!=.Windup||enemy.hp<=0 do continue
				if !app.dev_reveal&&!tile_pos_visible(app,enemy.pos) do continue
				feet:=enemy.prev_pos+(enemy.pos-enemy.prev_pos)*alpha
				draw_enemy_attack_telegraph(&enemy,feet)
			}
			end_effect_visibility(effect_active)
		}
		return
	}
	for &enemy in app.run.enemies {
		if enemy.ai!=.Windup||enemy.hp<=0||!effect_fallback_compact_visible(app,enemy.pos) do continue
		feet:=enemy.prev_pos+(enemy.pos-enemy.prev_pos)*alpha
		draw_enemy_attack_telegraph(&enemy,feet,true)
	}
}

@(private = "file")
draw_enemy_attack_telegraphs_through_walls :: proc(app:^App,alpha:f32) {
	if app==nil do return
	for &enemy in app.run.enemies {
		if enemy.ai!=.Windup||enemy.hp<=0 do continue
		// Do not turn the x-ray trace into an enemy detector: only repeat tells
		// whose committed attacker is already inside the live visibility field.
		if !app.dev_reveal&&!tile_pos_visible(app,enemy.pos) do continue
		feet:=enemy.prev_pos+(enemy.pos-enemy.prev_pos)*alpha
		draw_enemy_attack_telegraph(&enemy,feet,opacity_scale=VISUAL_ENEMY_TELEGRAPH_WALL_ALPHA)
	}
}

@(private = "file")
draw_projectiles_through_walls :: proc(app:^App,alpha:f32) {
	if app==nil do return
	for &projectile in app.run.projectiles {
		if !tile_pos_visible(app,projectile.pos) do continue
		feet:=projectile.prev_pos+(projectile.pos-projectile.prev_pos)*alpha
		draw_projectile(&projectile,feet,alpha,opacity_scale=VISUAL_PROJECTILE_WALL_ALPHA)
	}
}

@(private = "file")
draw_player_aim_tick :: proc(app: ^App, feet: Vec2) {
	if app == nil do return
	direction := visual_iso_direction(app.run.player.facing)
	if direction == {} do return
	center := rl.Vector2(world_from_tile(feet))-rl.Vector2{0,4}
	color := rl.Color(mix_color_u8({92,170,255,255},THEMES[app.run.theme_index].accent,.18))
	rl.DrawLineEx(center,center+rl.Vector2(direction)*12,2,rl.Fade(color,.75))
}

@(private = "file")
draw_player_aim_cone :: proc(app: ^App, feet: Vec2) {
	if app == nil || app.run.player.hp <= 0 do return
	cone := visual_aim_cone(app.run.player.facing)
	if !cone.valid do return
	center := rl.Vector2(world_from_tile(feet)) + rl.Vector2(cone.center_offset)
	color := rl.Color(mix_color_u8({92,170,255,255}, THEMES[app.run.theme_index].accent, .18))
	rl.BeginBlendMode(.ADDITIVE)
	rl.DrawRing(
		center,cone.inner_radius,cone.outer_radius,
		cone.angle_degrees-cone.half_angle_degrees,
		cone.angle_degrees+cone.half_angle_degrees,
		30,rl.Fade(color,28.0/255.0),
	)
	rl.DrawRing(
		center,cone.inner_radius+2,cone.outer_radius*.96,
		cone.angle_degrees-cone.half_angle_degrees*.82,
		cone.angle_degrees+cone.half_angle_degrees*.82,
		24,rl.Fade(color,14.0/255.0),
	)
	rl.EndBlendMode()
}

@(private = "file")
draw_projectile :: proc(projectile: ^Projectile, feet: Vec2, alpha: f32, trails := true, opacity_scale := f32(1)) {
	if projectile == nil do return
	opacity := clamp(opacity_scale,f32(0),f32(1))
	center := rl.Vector2(world_from_tile(feet)) - rl.Vector2{0, PROJECTILE_LIFT}
	color := rl.Color(projectile.color)
	body := rl.Fade(color,opacity)
	age := visual_projectile_render_age(projectile.visual_age, alpha)
	trail_samples := visual_projectile_trails(projectile.vel, age)
	if trails do for trail in trail_samples {
		if trail.alpha <= 0 do continue
		pos := center + rl.Vector2(trail.offset)
		rl.DrawEllipse(i32(pos.x),i32(pos.y),trail.radius*1.5,trail.radius*.72,rl.Fade(color,trail.alpha*opacity))
	}
	frame := visual_projectile_frame(age)
	pulse := .86 + .10 * math.sin((f32(frame)+.5) * math.PI*.5)
	angle := visual_projectile_rotation(projectile.vel)
	bright := rl.Fade(rl.Color(mix_color_u8(projectile.color,{255,255,255,255},.42)),opacity)
	rl.BeginBlendMode(.ADDITIVE)
	rl.DrawCircleV(center,8+f32(frame&1),rl.Fade(color,.25*pulse*opacity))
	rl.EndBlendMode()

	// Raylib-native silhouettes preserve owner/archetype identity; typed color
	// remains on every core/trail. Geometry is also the missing-asset fallback,
	// so projectiles can never disappear because a texture failed to load.
	switch projectile.visual {
	case .Enemy_Void:
		rl.DrawPoly(center,6,5.2,angle+30,body)
		rl.DrawPolyLinesEx(center,6,6.1,angle+30,1.2,bright)
	case .Warden_Guard:
		rl.DrawPoly(center,4,5.8,angle+45,body)
		rl.DrawPolyLinesEx(center,4,6.5,angle+45,1.4,bright)
	case .Rogue_Dagger:
		dir := rl.Vector2{math.cos(angle*math.PI/180),math.sin(angle*math.PI/180)}
		perp := rl.Vector2{-dir.y,dir.x}
		tip := center+dir*9
		left := center-dir*5+perp*2.4
		right := center-dir*5-perp*2.4
		rl.DrawTriangle(tip,left,right,body)
		rl.DrawLineEx(left,tip,1.2,bright)
		rl.DrawLineEx(right,tip,1.2,bright)
	case .Arcanist_Arc:
		rl.DrawRing(center,2.2,5.7,angle-135,angle+135,12,body)
		rl.DrawCircleV(center,2.3,bright)
	case .Acolyte_Spirit:
		for i in 0..<3 {
			orb_angle := age*240+f32(i)*120
			offset := rl.Vector2{math.cos(orb_angle*math.PI/180)*4.5,math.sin(orb_angle*math.PI/180)*2.5}
			rl.DrawCircleV(center+offset,2.4,rl.Fade(color,.82*opacity))
		}
		rl.DrawCircleV(center,3.2,bright)
	case .Ranger_Arrow:
		dir := rl.Vector2{math.cos(angle*math.PI/180),math.sin(angle*math.PI/180)}
		perp := rl.Vector2{-dir.y,dir.x}
		rl.DrawLineEx(center-dir*7,center+dir*8,2,body)
		rl.DrawTriangle(center+dir*9,center+dir*4+perp*3,center+dir*4-perp*3,bright)
	}
}

@(private = "file")
draw_slash_event :: proc(event: ^Feel_Event, world: rl.Vector2, color: rl.Color) {
	sample := visual_slash_sample(event)
	if !sample.valid do return
	center := world + rl.Vector2(sample.center_offset)
	radius := max(f32(8), event.radius * TILE_HALF_W * sample.scale)
	angle := math.atan2(sample.direction.y,sample.direction.x)*180/math.PI
	rl.BeginBlendMode(.ADDITIVE)
	// Committed-asset alternative: a raylib-native crescent with the same
	// growth/fade/travel envelope, followed by pygame's three strokes and sparks.
	rl.DrawRing(center,max(f32(0),radius-3),radius+2,angle-62,angle+62,20,rl.Fade(color,.88*sample.alpha))
	for i in 0..<3 {
		distance := f32(i+1)*7*sample.scale
		perp := rl.Vector2(sample.perpendicular)
		dir := rl.Vector2(sample.direction)
		start := center-dir*distance-perp*(8*sample.scale)
		finish := center+dir*distance+perp*(8*sample.scale)
		alphas := [3]f32{92.0/255.0,54.0/255.0,26.0/255.0}
		rl.DrawLineEx(start,finish,max(f32(1),sample.scale),rl.Fade(color,alphas[i]*sample.alpha))
	}
	for side in ([2]f32{-1,1}) {
		dir := rl.Vector2(sample.direction)
		perp := rl.Vector2(sample.perpendicular)
		finish := center+(dir*16+perp*(side*10))*(1-sample.alpha)
		rl.DrawLineEx(center,finish,max(f32(1),sample.scale),rl.Fade(rl.Color{255,252,210,255},.70*sample.alpha))
	}
	rl.EndBlendMode()
}

// Semantic combat cues are deterministic sim events. Every branch is bounded:
// a fixed number of rings, strokes, or sparks independent of frame rate.
@(private = "file")
draw_world_feel_event :: proc(event: ^Feel_Event) {
	if event == nil || event.kind == .Screen_Flash do return
	p := feel_progress(event)
	life := feel_life(event)
	world := rl.Vector2(world_from_tile(event.pos))
	color := rl.Color(event.color)
	radius := max(f32(3), event.radius * TILE_HALF_W)
	switch event.kind {
	case .Hit:
		center := world - rl.Vector2{0,18}
		rl.BeginBlendMode(.ADDITIVE)
		rl.DrawCircleV(center,radius*(.35+.65*p),rl.Fade(color,.42*life))
		rl.DrawCircleLinesV(center,radius*(.5+.65*p),rl.Fade(rl.WHITE,.75*life))
		rl.EndBlendMode()
	case .Blood:
		center := world - rl.Vector2{0,16}
		for i in 0..<5 {
			angle := -.85+f32(i)*.42
			dir := rl.Vector2{math.cos(angle),math.sin(angle)}
			rl.DrawLineEx(center+dir*(2+p*4),center+dir*(5+radius*p),2,rl.Fade(color,.8*life))
		}
	case .Death:
		rl.BeginBlendMode(.ADDITIVE)
		rl.DrawEllipseLinesV(world,radius*(.25+.75*p),radius*(.12+.38*p),rl.Fade(color,.75*life))
		rl.DrawCircleV(world-rl.Vector2{0,12},radius*.28*(1-p),rl.Fade(color,.35*life))
		rl.EndBlendMode()
	case .Burst, .Elite_Death, .Miniboss_Death, .Boss_Payoff:
		spokes := event.kind == .Boss_Payoff ? 12 : event.kind == .Miniboss_Death ? 10 : 8
		rl.BeginBlendMode(.ADDITIVE)
		rl.DrawRing(world,max(f32(0),radius*p-2),radius*p+2,0,360,24,rl.Fade(color,.72*life))
		for i in 0..<spokes {
			angle := (f32(i)/f32(spokes)*2*math.PI)+p*.55
			dir := rl.Vector2{math.cos(angle),math.sin(angle)*.5}
			rl.DrawLineEx(world+dir*(radius*.15),world+dir*(radius*(.45+.55*p)),event.kind==.Boss_Payoff?f32(2):f32(1),rl.Fade(color,.62*life))
		}
		rl.EndBlendMode()
	case .Slash:
		draw_slash_event(event,world,color)
	case .Cast:
		center := world-rl.Vector2{0,12}
		rl.BeginBlendMode(.ADDITIVE)
		rl.DrawRing(center,max(f32(0),radius*p-2),radius*p+2,0,360,24,rl.Fade(color,.75*life))
		for i in 0..<6 {
			angle := f32(i)*math.PI/3+p*1.2
			dir := rl.Vector2{math.cos(angle),math.sin(angle)}
			rl.DrawCircleV(center+dir*(radius*(.35+.45*p)),2.2,rl.Fade(color,.78*life))
		}
		rl.EndBlendMode()
	case .Dash:
		dir := rl.Vector2(visual_iso_direction(event.direction))
		center := world-rl.Vector2{0,10}
		for i in 0..<4 {
			offset := rl.Vector2{0,f32(i)-1.5}*3
			length := radius*(.8+p*.8+f32(i)*.25)
			rl.DrawLineEx(center-dir*length+offset,center+dir*(length*.5)+offset*.5,1.4,rl.Fade(color,(.55-f32(i)*.10)*life))
		}
	case .Time_Skip:
		rl.BeginBlendMode(.ADDITIVE)
		rl.DrawRing(world,max(f32(0),radius*p-3),radius*p+3,0,360,40,rl.Fade(color,.62*life))
		rl.DrawRing(world,max(f32(0),radius*(1-p)-2),radius*(1-p)+2,0,360,32,rl.Fade(color,.34*life))
		rl.EndBlendMode()
	case .Nova:
		// The gameplay radius lives in tile space, whose isometric projection is
		// an ellipse. Every spoke uses the same projected basis, so the raster's
		// edge and damage reach agree in every direction.
		radii := visual_iso_radial_radii(event.radius, p)
		rl.BeginBlendMode(.ADDITIVE)
		for thickness in 0..<3 {
			rx := max(f32(1), radii.x + f32(thickness-1)*2)
			ry := max(f32(1), radii.y + f32(thickness-1))
			rl.DrawEllipseLinesV(world,rx,ry,rl.Fade(color,(.58-f32(abs(thickness-1))*.15)*life))
		}
		for i in 0..<12 {
			angle := f32(i)*math.PI/6
			start := world+rl.Vector2(visual_iso_radial_offset(event.radius,.18,angle))
			finish := world+rl.Vector2(visual_iso_radial_offset(event.radius,p,angle))
			rl.DrawLineEx(start,finish,1.5,rl.Fade(color,.48*life))
		}
		rl.EndBlendMode()
	case .Summon:
		rl.BeginBlendMode(.ADDITIVE)
		rl.DrawRing(world,max(f32(0),radius*(.2+p*.65)-2),radius*(.2+p*.65)+2,0,360,24,rl.Fade(color,.72*life))
		for i in 0..<6 {
			angle := f32(i)*math.PI/3-p
			dir := rl.Vector2{math.cos(angle),math.sin(angle)*.55}
			rl.DrawCircleV(world+dir*(radius*(.35+.35*p)),2.5,rl.Fade(color,.72*life))
		}
		rl.EndBlendMode()
	case .Command:
		dir := rl.Vector2(visual_iso_direction(event.direction))
		if dir == {} do dir = {1,0}
		perp := rl.Vector2{-dir.y,dir.x}
		tip := world+dir*(radius*(.45+.55*p))-rl.Vector2{0,14}
		rl.DrawTriangle(tip,tip-dir*8+perp*5,tip-dir*8-perp*5,rl.Fade(color,.82*life))
	case .Bell_Plant, .Bell_Arm, .Bell_Detonate:
		armed := event.kind == .Bell_Arm
		spokes := event.kind == .Bell_Detonate ? 8 : 5
		rl.BeginBlendMode(.ADDITIVE)
		rl.DrawRing(world,max(f32(0),radius*(.25+.55*p)-2),radius*(.25+.55*p)+2,0,360,24,rl.Fade(color,(armed?.88:.68)*life))
		for i in 0..<spokes {
			angle := f32(i)*2*math.PI/f32(spokes)+p*.7
			dir := rl.Vector2{math.cos(angle),math.sin(angle)*.5}
			rl.DrawLineEx(world+dir*(radius*.15),world+dir*(radius*(.65+p*.45)),1.4,rl.Fade(color,.78*life))
		}
		rl.EndBlendMode()
	case .Knockback_Travel:
		samples := visual_knockback_samples(event)
		for sample,index in samples {
			center := rl.Vector2(world_from_tile(sample))-rl.Vector2{0,12}
			sample_life := clamp(life + f32(index)*.18,0,1)
			rl.DrawCircleLinesV(center,5+f32(index)*2,rl.Fade(color,.65*sample_life))
		}
	case .Screen_Flash:
	}
}

@(private = "file")
draw_screen_feel :: proc(app: ^App) {
	if app == nil do return
	for &event in app.run.feel {
		if event.kind != .Screen_Flash do continue
		if !feel_event_visible(&event,tile_pos_visible(app,event.pos),app.dev_reveal) do continue
		life := feel_life(&event)
		rl.DrawRectangle(0,0,rl.GetScreenWidth(),rl.GetScreenHeight(),rl.Fade(rl.Color(event.color),.24*life))
	}
}

@(private = "file")
actor_status_tint :: proc(statuses: ^[Status_Kind]f32) -> (rl.Color, bool) {
	priority := [6]Status_Kind{.Stunned,.Burning,.Poisoned,.Chilled,.Bound,.Snared}
	for status in priority {
		if statuses[status] <= 0 do continue
		base := STATUS_DEFS[status].color
		return {u8((int(base[0])+255)/2),u8((int(base[1])+255)/2),u8((int(base[2])+255)/2),255},true
	}
	return rl.WHITE,false
}

PROJECTILE_LIFT :: 22.0 // bolts fly at chest height, not along the floor

COLOR_POTION_HEAL :: rl.Color{196, 66, 58, 255}
COLOR_POTION_MANA :: rl.Color{70, 116, 208, 255}

// Doors: orientation picks the visible isometric face from the surrounding
// wall run. Adjacent door tiles count as part of that run too (wide boss
// seals), matching pygame's door_render_face.
@(private = "file")
draw_door :: proc(app: ^App, assets: ^Assets, tile: Vec2, dim: bool) -> rl.Rectangle {
	d := &app.run.dungeon
	x, y := int(tile.x), int(tile.y)
	doorish := proc(t: Tile_Kind) -> bool {
		return t == .Wall || t == .Closed_Door || t == .Open_Door
	}
	x_axis := dungeon_in_bounds(x-1,y) && dungeon_in_bounds(x+1,y) &&
		doorish(d.tiles[x-1][y]) && doorish(d.tiles[x+1][y])
	y_axis := dungeon_in_bounds(x,y-1) && dungeon_in_bounds(x,y+1) &&
		doorish(d.tiles[x][y-1]) && doorish(d.tiles[x][y+1])
	key := door_world_key(d.tiles[x][y], x_axis, y_axis)
	sprite := &assets.world[key]
	if sprite.loaded {
		theme := &THEMES[app.run.theme_index]
		variant := x * 7 + y * 13
		return draw_world_sprite(sprite, tile, variant, 0, fog_dim(theme_tint(theme.wall_edge, sprite.tint, variant), dim))
	}
	draw_iso_block(tile, DOOR_PX, COLOR_DOOR_TOP, COLOR_DOOR_LEFT, COLOR_DOOR_RIGHT)
	center := rl.Vector2(world_from_tile(tile + {0.5, 0.5}))
	return {center.x-TILE_HALF_W,center.y-DOOR_PX-TILE_HALF_H,f32(TILE_W),f32(DOOR_PX+TILE_H)}
}

@(private = "file")
draw_ground_item :: proc(assets: ^Assets, g: ^Ground_Item) {
	w := rl.Vector2(world_from_tile(g.pos))
	icon_key := g.item.icon
	if g.item.unidentified {
		if g.item.kind == .Weapon do icon_key = "weapon"
		if g.item.kind == .Armor do icon_key = "armor"
	}
	if icon, found := assets.items[icon_key]; found && icon.loaded {
		h := icon.world_h
		width := h * f32(icon.tex.width) / f32(icon.tex.height)
		dst := rl.Rectangle{w.x - icon.anchor.x * width, w.y - icon.anchor.y * h, width, h}
		if item_visible_rarity(g.item) != .Common {
			color := rl.Color(RARITIES[item_visible_rarity(g.item)].color)
			rl.BeginBlendMode(.ADDITIVE)
			rl.DrawCircleV(w - {0, 6}, 11, rl.Fade(color, 0.25))
			rl.EndBlendMode()
		}
		rl.DrawTexturePro(icon.tex, {0, 0, f32(icon.tex.width), f32(icon.tex.height)}, dst, {0, 0}, 0, rl.WHITE)
		return
	}
	switch g.item.kind {
	case .Heal_Potion, .Mana_Potion:
		color := g.item.kind == .Heal_Potion ? COLOR_POTION_HEAL : COLOR_POTION_MANA
		rl.DrawCircleV(w - {0, 5}, 4, color)
		rl.DrawRectangleV(w - {1.5, 12}, {3, 4}, rl.Color{120, 110, 100, 255}) // cork
	case .Identify_Scroll, .Remove_Curse_Scroll:
		color := g.item.kind == .Identify_Scroll ? rl.Color{205, 205, 220, 255} : rl.Color{214, 92, 150, 255}
		rl.DrawRectangleV(w - {5, 12}, {10, 14}, color)
		rl.DrawLineV(w - {3, 8}, w + {3, -8}, rl.Fade(rl.BLACK, .5))
	case .Weapon, .Armor:
		visible_rarity := item_visible_rarity(g.item)
		color := rl.Color(RARITIES[visible_rarity].color)
		draw_iso_tile_inset_fill(g.pos - {0.5, 0.5}, 0.3, rl.Fade(color, 0.9))
		if visible_rarity != .Common {
			rl.BeginBlendMode(.ADDITIVE)
			rl.DrawCircleV(w, 10, rl.Fade(color, 0.22))
			rl.EndBlendMode()
		}
	}
}

@(private = "file")
draw_prop_asset :: proc(prop:^Prop_Asset,feet:Vec2,tint:=rl.WHITE,scale:f32=0) {
	w:=rl.Vector2(world_from_tile(feet))
	if prop==nil||!prop.loaded {
		rl.DrawRectangleV(w-{4,12},{8,12},COLOR_DOOR_TOP)
		return
	}
	instance_scale := scale > 0 ? scale : f32(1)
	h:=prop.world_height*instance_scale
	width:=h*f32(prop.tex.width)/f32(prop.tex.height)
	dst:=rl.Rectangle{w.x-prop.anchor.x*width,w.y-prop.anchor.y*h,width,h}
	rl.DrawTexturePro(prop.tex,{0,0,f32(prop.tex.width),f32(prop.tex.height)},dst,{0,0},0,tint)
}

// --- MX.5 interactables ------------------------------------------------------

@(private = "file")
SHRINE_PROP_KEYS := [Shrine_Kind]Prop_Key{
	.Mending = .Shrine_Mending, .Insight = .Shrine_Insight, .War = .Shrine_War,
	.Haste = .Shrine_Haste, .Fortune = .Shrine_Fortune, .Oath = .Shrine_Oath,
	.Twilight = .Shrine_Twilight,
}

@(rodata)
TRAP_PROP_KEYS := [Trap_Kind]Prop_Key{
	.Spike = .Trap_Spike,
	.Rune = .Trap_Rune,
	.Needle = .Trap_Needle,
}

// Authored trap canvases use standing-prop anchors, but each trap is flat floor
// art in gameplay. Keep the horizontal authored anchor while centering the
// canvas vertically on the actor ground line, matching pygame's draw_trap.
@(private = "file")
draw_trap_asset :: proc(assets: ^Assets, trap: ^Trap, fade: f32) {
	if assets == nil || trap == nil do return
	prop := &assets.props[TRAP_PROP_KEYS[trap.kind]]
	if !prop.loaded || prop.tex.id == 0 do return
	center := rl.Vector2(world_from_tile(trap.pos))
	height := prop.world_height
	width := height * f32(prop.tex.width) / f32(prop.tex.height)
	destination := rl.Rectangle{
		center.x - prop.anchor.x * width,
		center.y - height * .5,
		width,
		height,
	}
	rl.DrawTexturePro(
		prop.tex,
		{0, 0, f32(prop.tex.width), f32(prop.tex.height)},
		destination,
		{},
		0,
		rl.Fade(rl.WHITE, fade),
	)
}

// Flat plate art on the actor ground line (effects.py draw_trap): a pulsing
// warning ellipse, then the diamond outline once half-materialized, with the
// revealed authored plate above both. No shadow — the plate belongs to the floor.
@(private = "file")
draw_trap :: proc(assets: ^Assets, trap: ^Trap, world_time: f32) {
	fade := clamp(trap.reveal_progress, 0, 1)
	if fade <= 0 do return
	def := &TRAP_DEFS[trap.kind]
	color := rl.Color(def.draw_color)
	w := rl.Vector2(world_from_tile(trap.pos))
	pulse := 0.5 + 0.5 * math.sin(world_time * 5.4 + trap.pos.x)
	rl.DrawEllipse(i32(w.x), i32(w.y), 21, 11, rl.Fade(color, (22 + pulse * 28) / 255 * fade))
	if fade >= 0.5 {
		wobble := math.sin(world_time * 3.7 + trap.pos.y) * 2
		points := [5]rl.Vector2{
			{w.x, w.y - (10 + pulse * 2)},
			{w.x + 16 + wobble, w.y},
			{w.x, w.y + (10 + pulse * 2)},
			{w.x - 16 + wobble, w.y},
			{w.x, w.y - (10 + pulse * 2)},
		}
		for i in 0 ..< 4 {
			rl.DrawLineV(points[i], points[i + 1], color)
		}
	}
	draw_trap_asset(assets, trap, fade)
}

// Per-kind shrine prop with the pygame glow treatment (effects.py
// draw_shrine): gold pulse and orbiting motes while unused, greyed when spent.
// Room furniture, not a floor decal: the sprite's base diamond covers the
// whole (solid) tile, so it casts no contact shadow of its own — only the
// live shrine's glow and motes read above it. A spent shrine is inert stone.
@(private = "file")
draw_shrine :: proc(view: ^View, assets: ^Assets, shrine: ^Shrine, world_time: f32) {
	w := rl.Vector2(world_from_tile(shrine.pos))
	tint: rl.Color = shrine.used ? {105, 105, 115, 255} : rl.WHITE
	if !shrine.used {
		color := rl.Color{235, 205, 110, 255}
		pulse := 0.6 + 0.4 * math.sin(world_time * 3.0 + shrine.pos.x)
		// Glow and motes track the half-tile footprint of the prop art.
		rl.DrawEllipse(i32(w.x), i32(w.y), 13, 7, rl.Fade(color, (42 + 48 * pulse) / 255))
		draw_prop_asset(&assets.props[SHRINE_PROP_KEYS[shrine.kind]], shrine.pos, tint)
		for index in 0 ..< 3 {
			angle := world_time * 1.8 + shrine.pos.x + f32(index) * math.TAU / 3
			mote := rl.Vector2{w.x + math.cos(angle) * 9, w.y - (8 + math.sin(angle) * 3) - 8}
			rl.DrawCircleV(mote, 1.4, rl.Fade(color, 0.85))
		}
		return
	}
	draw_prop_asset(&assets.props[SHRINE_PROP_KEYS[shrine.kind]], shrine.pos, tint)
	_ = view
}

// Revealed cache: theme-accent glow under the display-case prop
// (effects.py draw_secret).
@(private = "file")
draw_secret :: proc(view: ^View, app: ^App, assets: ^Assets, secret: ^Secret, world_time: f32) {
	w := rl.Vector2(world_from_tile(secret.pos))
	color := rl.Color(THEMES[app.run.theme_index].accent)
	pulse := 0.55 + 0.45 * math.sin(world_time * 5.0 + secret.pos.x)
	rl.DrawEllipse(i32(w.x), i32(w.y + 1), 9, 5, rl.Fade(color, (34 + 46 * pulse) / 255))
	draw_prop_asset(&assets.props[Prop_Key.Secret_Cache], secret.pos)
}

// Names float over drops the player is close to (rarity-colored).
@(private = "file")
draw_item_labels :: proc(view: ^View, app: ^App) {
	player := &app.run.player
	for &g in app.run.ground_items {
		if !app.dev_reveal && !tile_pos_visible(app, g.pos) do continue
		d := g.pos - player.pos
		if math.hypot(d.x, d.y) > 1.6 do continue
		w := rl.Vector2(world_from_tile(g.pos))
		color := g.item.kind == .Weapon || g.item.kind == .Armor ? rl.Color(RARITIES[item_visible_rarity(g.item)].color) : COLOR_TEXT
		label := fmt.ctprintf("%s", item_display_name(g.item))
		width := ui_measure_text(label, 10)
		if effect_ok,effect_active := begin_effect_visibility(view,app,true,g.pos);effect_ok {
			ui_draw_text(label, i32(w.x) - width / 2, i32(w.y) - 26, 10, color)
			end_effect_visibility(effect_active)
		}
	}
}

@(private = "file")
draw_contact_shadow :: proc(view: ^View, feet: Vec2, width, height: f32, moving: bool) {
	if view == nil || !view.radial_ready do return
	w := rl.Vector2(world_from_tile(feet))
	stretch := moving ? f32(1.12) : f32(1)
	alpha := moving ? f32(.44) : f32(.36)
	dst := rl.Rectangle{w.x-width*stretch*.5,w.y-height*.5,width*stretch,height}
	// Default alpha blending with a black source is dst*(1-alpha), equivalent
	// to the old multiplied result without flushing raylib's batch per actor.
	rl.DrawTexturePro(view.light_tex,{0,0,256,256},dst,{0,0},0,rl.Fade(rl.BLACK,alpha))
}

@(private = "file")
draw_miniboss_ground_seal :: proc(feet: Vec2, color: rl.Color, world_time: f32, stable_id: u32) {
	center := rl.Vector2(world_from_tile(feet))
	phase := world_time*.52 + visual_miniboss_effect_phase(stable_id)*math.TAU
	pulse := .72 + .14*math.sin(world_time*2.2+phase)
	rx,ry := f32(21),f32(10.5)
	rl.BeginBlendMode(.ADDITIVE)
	rl.DrawEllipse(i32(center.x),i32(center.y),rx,ry,rl.Fade(color,.10*pulse))
	rl.DrawEllipseLinesV(center,rx,ry,rl.Fade(color,.26*pulse))
	for index in 0..<8 {
		start_angle := phase + f32(index)*math.TAU/8 + .10
		end_angle := start_angle + .38
		start := center+rl.Vector2{math.cos(start_angle)*rx,math.sin(start_angle)*ry}
		finish := center+rl.Vector2{math.cos(end_angle)*rx,math.sin(end_angle)*ry}
		rl.DrawLineEx(start,finish,1.35,rl.Fade(color,.72*pulse))
	}
	rl.EndBlendMode()
}

@(private = "file")
draw_miniboss_sprite_halo :: proc(tex: rl.Texture2D, src, dst: rl.Rectangle, effect: Miniboss_Sprite_Effect) {
	if !effect.enabled do return
	phase := visual_miniboss_effect_phase(effect.stable_id)*math.TAU
	pulse := .78+.22*math.sin(effect.world_time*2.2+phase)
	offsets := [8]rl.Vector2{
		{-1.15,0},{1.15,0},{0,-1.15},{0,1.15},
		{-.8,-.8},{.8,-.8},{-.8,.8},{.8,.8},
	}
	rl.BeginBlendMode(.ADDITIVE)
	for offset in offsets {
		shifted := dst
		shifted.x += offset.x
		shifted.y += offset.y
		rl.DrawTexturePro(tex,src,shifted,{0,0},0,rl.Fade(effect.color,.065*pulse))
	}
	rl.EndBlendMode()
}

@(private = "file")
draw_miniboss_sprite_foil :: proc(tex: rl.Texture2D, src, dst: rl.Rectangle, effect: Miniboss_Sprite_Effect) {
	if !effect.enabled do return
	// Four horizontal slices offset the narrow highlight into a stepped diagonal.
	// Source and destination rectangles are cropped together, so transparent
	// sprite pixels remain transparent without an extra mask texture or blur pass.
	travel := visual_miniboss_foil_progress(effect.world_time,effect.stable_id)*1.6-.3
	rl.BeginBlendMode(.ADDITIVE)
	for row in 0..<4 {
		y0 := f32(row)/4
		y1 := f32(row+1)/4
		ymid := (y0+y1)*.5
		center := travel+(.5-ymid)*.34
		x0 := max(f32(0),center-.075)
		x1 := min(f32(1),center+.075)
		if x1 <= x0 do continue
		strip_src := rl.Rectangle{
			src.x+src.width*x0,src.y+src.height*y0,
			src.width*(x1-x0),src.height*(y1-y0),
		}
		strip_dst := rl.Rectangle{
			dst.x+dst.width*x0,dst.y+dst.height*y0,
			dst.width*(x1-x0),dst.height*(y1-y0),
		}
		rl.DrawTexturePro(tex,strip_src,strip_dst,{0,0},0,rl.Fade(effect.color,.30))

		core_x0 := max(x0,center-.022)
		core_x1 := min(x1,center+.022)
		if core_x1 > core_x0 {
			core_src := rl.Rectangle{
				src.x+src.width*core_x0,src.y+src.height*y0,
				src.width*(core_x1-core_x0),src.height*(y1-y0),
			}
			core_dst := rl.Rectangle{
				dst.x+dst.width*core_x0,dst.y+dst.height*y0,
				dst.width*(core_x1-core_x0),dst.height*(y1-y0),
			}
			rl.DrawTexturePro(tex,core_src,core_dst,{0,0},0,rl.Fade(rl.WHITE,.20))
		}
	}
	rl.EndBlendMode()
}

// Draw an actor sprite anchored at its feet (a tile-space point). The returned
// frame geometry is reused by the post-painter wall-ghost pass.
@(private = "file")
draw_actor :: proc(
	assets: ^Assets,
	sprites: ^Actor_Sprites,
	clip_kind: Clip_Kind,
	facing: Vec2,
	time: f32,
	feet: Vec2,
	tint: rl.Color,
	flash: f32,
	miniboss_effect := Miniboss_Sprite_Effect{},
) -> (tex: rl.Texture2D, src, dst: rl.Rectangle, drawn: bool) {
	if !sprites.loaded {
		center := rl.Vector2(world_from_tile(feet))
		if miniboss_effect.enabled {
			rl.BeginBlendMode(.ADDITIVE)
			rl.DrawCircleV(center,14,rl.Fade(miniboss_effect.color,.24))
			rl.EndBlendMode()
		}
		rl.DrawCircleV(center,10,COLOR_PLACEHOLDER)
		return
	}
	clip := sprites.clips[clip_kind]
	if !clip.valid do clip = sprites.clips[.Idle]
	if !clip.valid do clip = sprites.clips[.Walk]
	if !clip.valid do clip = sprites.clips[.Dance]
	if !clip.valid {
		rl.DrawCircleV(rl.Vector2(world_from_tile(feet)), 10, COLOR_PLACEHOLDER)
		return
	}

	frame := 0
	if clip.frames > 0 && clip.fps > 0 {
		f := int(time * clip.fps)
		frame = clip.loop ? f % clip.frames : min(f, clip.frames - 1)
	}
	cell := f32(sprites.cell)
	src = {f32(frame) * cell, f32(sprite_row_for_facing(facing)) * cell, cell, cell}
	size := sprites.canvas_world
	w := rl.Vector2(world_from_tile(feet))
	dst = {w.x - sprites.anchor.x * size, w.y - sprites.anchor.y * size, size, size}
	tex = clip.tex
	draw_miniboss_sprite_halo(tex,src,dst,miniboss_effect)
	rl.DrawTexturePro(tex,src,dst,{0,0},0,tint)
	draw_miniboss_sprite_foil(tex,src,dst,miniboss_effect)
	if flash > 0 {
		rl.BeginBlendMode(.ADDITIVE)
		rl.DrawTexturePro(tex,src,dst,{0,0},0,rl.Fade(rl.WHITE,flash*.8))
		rl.EndBlendMode()
	}
	drawn = true
	return
}

@(private = "file")
ghost_previous_weight :: proc(view: ^View, key: u64) -> f32 {
	if view == nil || key == 0 do return 0
	for i in 0 ..< view.ghost_weight_count {
		if view.ghost_weights[i].key == key do return view.ghost_weights[i].weight
	}
	return 0
}

@(private = "file")
draw_actor_wall_ghosts :: proc(view: ^View, app: ^App, actors: []Ghost_Actor, occluders: []Ghost_Occluder) {
	if view == nil || app == nil do return
	if view.ghost_floor_epoch != app.run.floor_epoch {
		view.ghost_weights = {}
		view.ghost_weight_count = 0
		view.ghost_floor_epoch = app.run.floor_epoch
	}
	next: [MAX_GHOST_WEIGHT_TRACKS]Ghost_Weight
	next_count := 0
	for actor in actors {
		// Trim transparent actor-cell margins for the trigger calculation, but use
		// the relic's already-tight world icon rectangle without another inset.
		body := actor.dst
		if actor.kind != .Story_Relic {
			body = {
				actor.dst.x + actor.dst.width * .16,
				actor.dst.y + actor.dst.height * .04,
				actor.dst.width * .68,
				actor.dst.height * .92,
			}
		}
		body_area := body.width * body.height
		if body_area <= 0 do continue
		covered: f32
		open_door_override := false
		for occluder in occluders {
			gap := occluder.depth - actor.depth
			if gap <= 0 do continue
			clip := rl.GetCollisionRec(body, occluder.rect)
			if clip.width <= 0 || clip.height <= 0 do continue
			if actor.kind == .Player && occluder.open_door &&
				occluder.tile.x <= actor.feet.x && actor.feet.x < occluder.tile.x+1 &&
				occluder.tile.y <= actor.feet.y && actor.feet.y < occluder.tile.y+1 {
				// Same-tile open-door art can paint only hundredths of a depth
				// unit later; this traversal override deliberately bypasses the
				// generic .25 gap threshold so the player never disappears.
				open_door_override = true
			}
			fraction := clip.width * clip.height / body_area
			covered += visual_ghost_coverage_contribution(gap, fraction)
			if covered >= VISUAL_GHOST_COVERAGE_RAMP_FULL do break
		}
		target := visual_ghost_target(covered)
		if open_door_override do target = 1
		weight := visual_ghost_ease(ghost_previous_weight(view, actor.key), target, view.frame_dt)
		if weight > VISUAL_FOG_DRAW_EPSILON && next_count < len(next) {
			next[next_count] = {actor.key, weight}
			next_count += 1
		}
		if weight < VISUAL_GHOST_WEIGHT_FLOOR do continue

		center := rl.Vector2{actor.dst.x+actor.dst.width*.5,actor.dst.y+actor.dst.height*.5}
		relic_ghost := actor.kind == .Story_Relic
		aura_scale_x := relic_ghost ? f32(2.4) : f32(1.65)
		aura_scale_y := relic_ghost ? f32(2.0) : f32(1.10)
		aura_dst := rl.Rectangle{
			center.x-actor.dst.width*aura_scale_x*.5,
			center.y-actor.dst.height*aura_scale_y*.5,
			actor.dst.width*aura_scale_x,
			actor.dst.height*aura_scale_y,
		}
		aura_color := relic_ghost ? actor.tint : rl.Color{238,226,196,255}
		aura_alpha := relic_ghost ? VISUAL_RELIC_GHOST_AURA_ALPHA : VISUAL_GHOST_AURA_ALPHA
		rl.BeginBlendMode(.ADDITIVE)
		rl.DrawTexturePro(
			view.light_tex,{0,0,256,256},aura_dst,{0,0},0,
			rl.Fade(aura_color,aura_alpha*weight*weight),
		)
		rl.EndBlendMode()
		if relic_ghost {
			ghost_alpha:=VISUAL_RELIC_GHOST_SPRITE_ALPHA*weight
			if actor.tex.id!=0 {
				rl.DrawTexturePro(actor.tex,actor.src,actor.dst,{0,0},0,rl.Fade(rl.WHITE,ghost_alpha))
			} else {
				dark:=rl.Color{u8(f32(actor.tint.r)*.34),u8(f32(actor.tint.g)*.34),u8(f32(actor.tint.b)*.42),255}
				rl.DrawPoly(center,4,9,45,rl.Fade(dark,ghost_alpha))
				rl.DrawPoly(center,4,5.5,45,rl.Fade(actor.tint,ghost_alpha))
				rl.DrawPolyLinesEx(center,4,9,45,1.2,rl.Fade(rl.WHITE,.82*ghost_alpha))
			}
		} else {
			ghost_tint := actor.tint
			ghost_tint.a = u8(clamp(f32(ghost_tint.a)*VISUAL_GHOST_SPRITE_ALPHA*weight,0,255))
			rl.DrawTexturePro(actor.tex,actor.src,actor.dst,{0,0},0,ghost_tint)
		}
	}
	view.ghost_weights = next
	view.ghost_weight_count = next_count
}

@(private = "file")
draw_enemy_bar :: proc(enemy: ^Enemy, sprites: ^Actor_Sprites, feet: Vec2) {
	if enemy == nil || sprites == nil do return
	has_status := false
	for status in Status_Kind {
		if enemy.statuses[status] > 0 do has_status = true
	}
	if enemy.hp >= enemy.max_hp && enemy.role == .Normal && !has_status do return
	head := sprites.loaded ? sprites.canvas_world * sprites.anchor.y * 0.85 : 40
	w := rl.Vector2(world_from_tile(feet))
	frac := clamp(f32(enemy.hp) / f32(enemy.max_hp), 0, 1)
	miniboss := visual_miniboss_effect_enabled(enemy.role)
	bar_width: f32 = miniboss ? 30 : 24
	bar_height: f32 = miniboss ? 4 : 3
	bar := rl.Rectangle{w.x-bar_width*.5,w.y-head-6,bar_width,bar_height}
	rl.DrawRectangleRec(bar,rl.Fade(rl.BLACK,.68))
	fill := bar
	fill.width *= frac
	rl.DrawRectangleRec(fill,rl.Color{200,60,50,255})
	if miniboss {
		accent := rl.Color(enemy.color)
		rl.DrawRectangleLinesEx(bar,1,rl.Fade(accent,.82))
		rl.DrawPoly({bar.x-4,bar.y+bar.height*.5},4,2.8,45,accent)
	}
	pip_x := bar.x
	for status in Status_Kind {
		if enemy.statuses[status] <= 0 do continue
		rl.DrawRectangleV({pip_x, w.y-head-11}, {4,4}, rl.Color(STATUS_DEFS[status].color))
		pip_x += 6
	}
}

@(private = "file")
draw_damage_numbers :: proc(view: ^View, app: ^App) {
	for &n in app.run.numbers {
		if n.kind==.Text do continue
		if !app.dev_reveal && !tile_pos_visible(app, n.pos) do continue
		t := n.age / DAMAGE_NUMBER_SECONDS
		w := rl.Vector2(world_from_tile(n.pos))
		pos_y := w.y - 44 - t * 20
		color: rl.Color
		label: cstring
		size: i32 = 10
		switch n.kind {
		case .Damage_Dealt:
			color = rl.Color(DAMAGE_TYPE_COLORS[n.damage_type])
			label = fmt.ctprintf("%v", n.value)
		case .Damage_Taken:
			color = rl.Color(DAMAGE_TYPE_COLORS[n.damage_type])
			label = fmt.ctprintf("%v", n.value)
		case .Heal:
			color = {110, 220, 110, 255}
			label = fmt.ctprintf("+%v", n.value)
		case .Garden_Heal:
			color = {126, 214, 92, 255}
			label = fmt.ctprintf("Garden +%v", n.value)
		case .Bar_Heal:
			color = {225, 170, 86, 255}
			label = fmt.ctprintf("Bar +%v", n.value)
		case .Gold:
			color = {225, 190, 92, 255}
			label = fmt.ctprintf("+%vg", n.value)
		case .Text:
			continue
		}
		width := ui_measure_text(label, size)
		x:=i32(w.x)-width/2
		if effect_ok,effect_active := begin_effect_visibility(view,app,true,n.pos);effect_ok {
			ui_draw_text(label,x,i32(pos_y),size,rl.Fade(color,1-t*t))
			end_effect_visibility(effect_active)
		}
	}
}

@(private = "file")
draw_text_notifications :: proc(app: ^App) {
	if app == nil do return
	for &n in app.run.numbers {
		if n.kind != .Text || (!app.dev_reveal && !tile_pos_visible(app, n.pos)) do continue
		t := n.age / DAMAGE_NUMBER_SECONDS
		world := rl.Vector2(world_from_tile(n.pos))
		label := fmt.ctprintf("%s", n.text)
		size: i32 = 11
		width := ui_measure_text(label, size)
		color := rl.Fade(rl.Color{235, 205, 120, 255}, 1-t*t)
		ui_draw_text(label, i32(world.x)-width/2, i32(world.y-44-t*20), size, color)
	}
}

@(private = "file")
wall_is_exposed :: proc(d: ^Dungeon, x, y: int) -> bool {
	for dy in -1 ..= 1 {
		for dx in -1 ..= 1 {
			nx, ny := x + dx, y + dy
			if (dx != 0 || dy != 0) && dungeon_in_bounds(nx, ny) && d.tiles[nx][ny] != .Wall {
				return true
			}
		}
	}
	return false
}

// Visible tile bounds from the four screen corners, padded for wall height.
@(private = "file")
visible_tile_bounds :: proc(view: ^View) -> (x0, x1, y0, y1: int) {
	sw := f32(rl.GetScreenWidth())
	sh := f32(rl.GetScreenHeight())
	corners := [4]Vec2{{0, 0}, {sw, 0}, {0, sh}, {sw, sh}}
	min_t := Vec2{max(f32), max(f32)}
	max_t := Vec2{min(f32), min(f32)}
	for corner in corners {
		t := tile_from_world(Vec2(rl.GetScreenToWorld2D(rl.Vector2(corner), view.camera)))
		min_t.x = min(min_t.x, t.x)
		min_t.y = min(min_t.y, t.y)
		max_t.x = max(max_t.x, t.x)
		max_t.y = max(max_t.y, t.y)
	}
	x0 = clamp(int(math.floor(min_t.x)) - 1, 0, MAP_W - 1)
	x1 = clamp(int(math.ceil(max_t.x)) + 4, 0, MAP_W - 1)
	y0 = clamp(int(math.floor(min_t.y)) - 1, 0, MAP_H - 1)
	y1 = clamp(int(math.ceil(max_t.y)) + 4, 0, MAP_H - 1)
	return
}

// --- Iso primitives --------------------------------------------------------
// Diamond corners of tile (i, j): top/right/bottom/left in screen space.
// raylib fills triangles only when vertices wind counter-clockwise on screen.

@(private = "file")
tile_corners :: proc(tile: Vec2) -> (t, r, b, l: rl.Vector2) {
	t = rl.Vector2(world_from_tile(tile))
	r = rl.Vector2(world_from_tile(tile + {1, 0}))
	b = rl.Vector2(world_from_tile(tile + {1, 1}))
	l = rl.Vector2(world_from_tile(tile + {0, 1}))
	return
}

draw_iso_tile_fill :: proc(tile: Vec2, color: rl.Color) {
	t, r, b, l := tile_corners(tile)
	rl.DrawTriangle(t, l, b, color)
	rl.DrawTriangle(t, b, r, color)
}

draw_iso_tile_outline :: proc(tile: Vec2, color: rl.Color) {
	t, r, b, l := tile_corners(tile)
	rl.DrawLineV(t, r, color)
	rl.DrawLineV(r, b, color)
	rl.DrawLineV(b, l, color)
	rl.DrawLineV(l, t, color)
}

@(private = "file")
inset_corners :: proc(tile: Vec2, scale: f32) -> (t, r, b, l: rl.Vector2) {
	center := rl.Vector2(world_from_tile(tile + {0.5, 0.5}))
	t0, r0, b0, l0 := tile_corners(tile)
	t = center + (t0 - center) * scale
	r = center + (r0 - center) * scale
	b = center + (b0 - center) * scale
	l = center + (l0 - center) * scale
	return
}

@(private = "file")
draw_iso_tile_inset_fill :: proc(tile: Vec2, scale: f32, color: rl.Color) {
	t, r, b, l := inset_corners(tile, scale)
	rl.DrawTriangle(t, l, b, color)
	rl.DrawTriangle(t, b, r, color)
}

@(private = "file")
draw_iso_tile_inset_outline :: proc(tile: Vec2, scale: f32, color: rl.Color) {
	t, r, b, l := inset_corners(tile, scale)
	rl.DrawLineV(t, r, color)
	rl.DrawLineV(r, b, color)
	rl.DrawLineV(b, l, color)
	rl.DrawLineV(l, t, color)
}

// Raised prism: elevated top diamond plus the two camera-facing side faces.
@(private = "file")
draw_iso_block :: proc(tile: Vec2, height: f32, top, left, right: rl.Color) {
	t, r, b, l := tile_corners(tile)
	lift := rl.Vector2{0, -height}
	te, re, be, le := t + lift, r + lift, b + lift, l + lift

	rl.DrawTriangle(te, le, be, top)
	rl.DrawTriangle(te, be, re, top)
	rl.DrawTriangle(le, l, b, left)
	rl.DrawTriangle(le, b, be, left)
	rl.DrawTriangle(be, b, r, right)
	rl.DrawTriangle(be, r, re, right)
}

// --- Overlay ---------------------------------------------------------------

// Greedy word wrap for the plan texts (guardian subtitles overflow a single
// line). Splitting on the space byte is UTF-8-safe; up to four lines.
@(private = "file")
wrap_text_lines :: proc(text: string, size: i32, max_width: i32, buf: ^[4]string) -> (count: int) {
	remaining := text
	for len(remaining) > 0 && count < len(buf) {
		take := len(remaining)
		if ui_measure_text(fmt.ctprintf("%s", remaining), size) > max_width {
			take = 0
			for i in 1 ..< len(remaining) {
				if remaining[i] != ' ' do continue
				if ui_measure_text(fmt.ctprintf("%s", remaining[:i]), size) > max_width do break
				take = i
			}
			if take == 0 do take = len(remaining) // single unbreakable run
		}
		buf[count] = remaining[:take]
		count += 1
		remaining = take < len(remaining) ? remaining[take + 1:] : ""
	}
	return
}

// Persistent desktop HUD labels are deliberately terse. Full modifier, risk,
// and reward prose belongs to transient previews and menus, not the live world.
hud_location_text :: proc(run: ^Run) -> string {
	if run == nil do return ""
	return fmt.tprintf(
		"Dungeon %d/%d · %s%s",
		run.depth,
		DUNGEON_DEPTH,
		THEMES[run.theme_index].name,
		run.dark_floor ? " · Dark" : "",
	)
}

hud_floor_text :: proc(run: ^Run) -> string {
	if run == nil do return ""
	plan := run_floor_plan(run)
	label := fmt.tprintf(
		"Threat %d · %s · %s",
		plan.threat_level,
		RUN_MODIFIERS[run.modifier].name,
		ENCOUNTER_TEMPLATES[plan.encounter].title,
	)
	if plan.has_boss do label = fmt.tprintf("%s · Boss", label)
	return label
}

@(private = "file")
draw_overlay :: proc(view: ^View, app: ^App, assets: ^Assets) {
	presentation := ui_begin_presentation()
	defer ui_end_presentation()
	run := &app.run
	// Mobile's authored resource cluster owns this corner. Desktop uses two
	// fixed, non-wrapping lines so the live world is not covered by run prose.
	if !view.mobile_mode {
		ui_draw_text(fmt.ctprintf("%s", hud_location_text(run)), 8, 8, 16, COLOR_TITLE)
		// The detail line yields to the engaged boss bar's centered name band.
		if !run.boss_engaged {
			ui_draw_text(fmt.ctprintf("%s", hud_floor_text(run)), 8, 27, 12, COLOR_TEXT_DIM)
		}
		if app.dev_controls {
			ui_draw_text("Arch Rogue " + VERSION, 8, 70, 18, COLOR_TEXT)
			rl.DrawFPS(i32(presentation.width) - 100, 8)
			ui_draw_text(
				fmt.ctprintf(
					"%s | depth %v%s | seed %x | tile %v",
					ARCHETYPES[run.player.archetype].name, run.depth,
					run.dark_floor ? " (DARK)" : "", run.seed,
					view.hovered_valid ? fmt.tprintf("%v,%v", view.hovered.x, view.hovered.y) : "-",
				),
				8, 92, 18, COLOR_TEXT,
			)
		}
	}

	draw_boss_bar(app)
	draw_arrival_card(app)

	prompt_y := i32(presentation.height) - 142
	prompt_center_x := presentation.width * .5
	if view.mobile_mode && view.mobile_layout_valid {
		primary := mobile_rect_to_design(view.mobile_layout.interact)
		gameplay := mobile_rect_to_design(view.mobile_layout.gameplay_rect)
		prompt_y = i32(primary.y) - 34
		prompt_center_x = gameplay.x + gameplay.width * .5
	}
	prompt := interact_prompt(run)
	if prompt != "" {
		prompt_label := prompt
		if view.mobile_mode && player_interaction_advertised(run) {
			prompt_label = fmt.tprintf("A%s", prompt[1:])
		}
		label := fmt.ctprintf("%s", prompt_label)
		width := ui_measure_text(label, 22)
		ui_draw_text(label, i32(prompt_center_x)-width/2, prompt_y, 22, COLOR_HOVER)
	}
	preview := stairs_preview(run)
	if preview != "" {
		// Wrapped lines grow upward from just above the prompt.
		lines: [4]string
		line_count := wrap_text_lines(preview, 15, i32(presentation.width) - 120, &lines)
		base_y := prompt_y - 5 - i32(line_count) * 19
		for i in 0 ..< line_count {
			label := fmt.ctprintf("%s", lines[i])
			width := ui_measure_text(label, 15)
			ui_draw_text(label, i32(prompt_center_x)-width/2, base_y + i32(i) * 19, 15, COLOR_TEXT_DIM)
		}
	}

	draw_player_hud(view, app, assets)
	if app.minimap_visible && (!view.mobile_mode || view.mobile_layout_valid) {
		minimap_card := minimap_design_rect()
		if view.mobile_mode && view.mobile_layout_valid {
			minimap_card = mobile_rect_to_design(view.mobile_layout.minimap)
		}
		draw_minimap(app, assets, minimap_card)
	}
	if run.player.memory_tokens > 0 && !app.inventory_open && !app.character_open && !app.shop_open {
		rect := memory_token_prompt_rect()
		if view.mobile_mode && view.mobile_layout_valid {
			scale := max(f32(.001), ui_presentation().scale)
			gameplay := &view.mobile_layout.gameplay_rect
			physical := Mobile_Rect{
				gameplay.x,
				gameplay.y,
				min(gameplay.width, rect.width * scale),
				min(gameplay.height, rect.height * scale),
			}
			rect = mobile_rect_to_design(physical)
		}
		asset := ui_chrome_asset(assets, .Hud_Panel)
		if !draw_ui_chrome(asset, rect) {
			rl.DrawRectangleRec(rect, rl.Fade(rl.Color{13,11,19,255}, .94))
			rl.DrawRectangleLinesEx(rect, 1, COLOR_TITLE)
		}
		glyph := ui_ouroboros_glyph(assets)
		_ = draw_ui_glyph(glyph, {rect.x+10,rect.y+12,26,26})
		ui_draw_text(fmt.ctprintf("+%v Memory",run.player.memory_tokens),i32(rect.x+43),i32(rect.y+8),16,COLOR_TITLE)
		ui_draw_text("Open Disciplines",i32(rect.x+43),i32(rect.y+28),12,COLOR_TEXT)
	}

	if app.dev_controls && !view.mobile_mode {
		ui_draw_text(
			"Arrows: move | LMB: move + melee | 1-4: actions | 5/6: potions | E: interact | I: bag | C: character | Esc: pause",
			8, i32(presentation.height) - 28, 16, COLOR_TEXT_DIM,
		)
		ui_draw_text("DEV  N: descend   R: reroll run   B: boss arena", 8, 114, 14, rl.Fade(COLOR_HOVER, 0.72))
	}
}

// MX.4 non-blocking arrival treatment: a centered depth/theme title that
// holds while arrival_timer runs and fades over its last stretch. Sits below
// the boss-bar band (y 36-80).
@(private = "file")
draw_arrival_card :: proc(app: ^App) {
	run := &app.run
	if run.arrival_timer <= 0 do return
	presentation := ui_presentation()
	alpha := clamp(run.arrival_timer / ARRIVAL_FADE_SECONDS, 0, 1)
	theme := THEMES[run.theme_index]
	title := fmt.ctprintf("Depth %v/%v", run.depth, DUNGEON_DEPTH)
	title_width := ui_measure_text(title, 30)
	ui_draw_text(title, i32(presentation.width*.5)-title_width/2, 104, 30, rl.Fade(COLOR_TITLE, alpha))
	sub := fmt.ctprintf("%s · %s", theme.name, theme.flavor)
	sub_width := ui_measure_text(sub, 16)
	ui_draw_text(sub, i32(presentation.width*.5)-sub_width/2, 140, 16, rl.Fade(rl.Color(theme.accent), alpha))
}

@(private = "file")
minimap_design_rect :: proc() -> rl.Rectangle {
	return {ui_design_width()-f32(MINIMAP_CARD_WIDTH)-18,18,f32(MINIMAP_CARD_WIDTH),f32(MINIMAP_CARD_HEIGHT)}
}

// Input consumes physical coordinates while rendering happens inside the
// fitted 1280x720 UI camera. Keeping both from one design rect prevents drift.
minimap_rect :: proc(app: ^App) -> rl.Rectangle {
	_ = app
	presentation := ui_presentation()
	design := minimap_design_rect()
	return {design.x*presentation.scale,design.y*presentation.scale,design.width*presentation.scale,design.height*presentation.scale}
}

@(private = "file")
draw_minimap_diamond :: proc(center: Vec2, half_w, half_h: f32, color: rl.Color) {
	top := rl.Vector2{center.x,center.y-half_h}
	right := rl.Vector2{center.x+half_w,center.y}
	bottom := rl.Vector2{center.x,center.y+half_h}
	left := rl.Vector2{center.x-half_w,center.y}
	rl.DrawTriangle(top,left,bottom,color)
	rl.DrawTriangle(top,bottom,right,color)
}

@(private = "file")
draw_minimap_marker_arrow :: proc(anchor, center: Vec2, color: rl.Color) {
	points := minimap_edge_arrow_vertices(anchor,center)
	// Raylib's screen-space triangle winding is opposite mathematical y-up.
	rl.DrawTriangle(rl.Vector2(points[0]),rl.Vector2(points[2]),rl.Vector2(points[1]),rl.Fade(color,235.0/255.0))
}

@(private = "file")
draw_minimap_marker_glyph :: proc(assets: ^Assets, kind: Minimap_Marker_Kind, pos: Vec2, world_time: f32) {
	ink := rl.Color(MINIMAP_INK_COLOR)
	switch kind {
	case .Bar:
		color := rl.Color(MINIMAP_BAR_COLOR)
		body := rl.Rectangle{pos.x-2.5,pos.y-1.5,5,5}
		rl.DrawRectangleRec({body.x-1,body.y-1,body.width+2,body.height+2},ink)
		rl.DrawRectangleRec(body,color)
		rl.DrawRectangleV(rl.Vector2{body.x,body.y-1},rl.Vector2{body.width,1},rl.Color(MINIMAP_GOLD_BRIGHT))
		rl.DrawRectangleV(rl.Vector2{body.x+body.width,body.y+1},rl.Vector2{1,2},color)
	case .Garden:
		color := rl.Color(MINIMAP_GARDEN_COLOR)
		dark := rl.Color{u8(max(0,int(color.r)-60)),u8(max(0,int(color.g)-60)),u8(max(0,int(color.b)-60)),255}
		highlight := rl.Color{u8(min(255,int(color.r)+50)),u8(min(255,int(color.g)+50)),u8(min(255,int(color.b)+50)),255}
		rl.DrawLineEx(rl.Vector2(pos),rl.Vector2(pos+Vec2{0,3}),1,dark)
		rl.DrawCircleV(rl.Vector2(pos+Vec2{0,-1}),4,ink)
		rl.DrawCircleV(rl.Vector2(pos+Vec2{0,-1}),3,color)
		rl.DrawCircleV(rl.Vector2(pos+Vec2{-1,-2}),1,highlight)
	case .Relic:
		pulse := visual_triangle_wave(world_time,1.8)
		gold := rl.Color(MINIMAP_GOLD_BRIGHT)
		arm := 4+pulse*2
		rl.BeginBlendMode(.ADDITIVE)
		rl.DrawCircleV(rl.Vector2(pos),8+pulse*2,rl.Fade(gold,.10+.08*pulse))
		rl.DrawCircleV(rl.Vector2(pos),5+pulse,rl.Fade(gold,.18+.12*pulse))
		rl.EndBlendMode()
		rl.DrawLineEx(rl.Vector2(pos-Vec2{arm,0}),rl.Vector2(pos+Vec2{arm,0}),1,gold)
		rl.DrawLineEx(rl.Vector2(pos-Vec2{0,arm}),rl.Vector2(pos+Vec2{0,arm}),1,gold)
		rl.DrawCircleV(rl.Vector2(pos),1.5,{255,250,232,255})
	case .Stairs:
		stairs := &assets.world[.Stairs]
		frame_count := max(1,stairs.frame_count)
		frame := world_sprite_frame_index(frame_count,stairs.fps,stairs.ping_pong,world_time)
		swell := frame_count > 1 && stairs.fps > 0 ? f32(frame)/f32(frame_count-1) : visual_triangle_wave(world_time,1.68)
		base := rl.Color{58,34,86,255}
		color := rl.Color(MINIMAP_STAIRS_COLOR)
		glow := rl.Color{
			u8(f32(base.r)+(f32(color.r)-f32(base.r))*swell),
			u8(f32(base.g)+(f32(color.g)-f32(base.g))*swell),
			u8(f32(base.b)+(f32(color.b)-f32(base.b))*swell),255,
		}
		rl.DrawCircleV(rl.Vector2(pos),4,ink)
		rl.DrawCircleV(rl.Vector2(pos),2,glow)
		rl.DrawCircleLinesV(rl.Vector2(pos),3,rl.Color(MINIMAP_GOLD_BRIGHT))
		if swell >= .65 do rl.DrawCircleV(rl.Vector2(pos),1,{226,196,255,255})
	}
}

@(private = "file")
draw_minimap_block :: proc(center: Vec2, half_w, half_h, lift: f32, color: rl.Color) {
	top_color := color
	left_color := rl.Color{u8(f32(color.r)*.68),u8(f32(color.g)*.68),u8(f32(color.b)*.68),color.a}
	right_color := rl.Color{u8(f32(color.r)*.52),u8(f32(color.g)*.52),u8(f32(color.b)*.52),color.a}
	top := rl.Vector2{center.x,center.y-half_h-lift}
	right := rl.Vector2{center.x+half_w,center.y-lift}
	bottom := rl.Vector2{center.x,center.y+half_h-lift}
	left := rl.Vector2{center.x-half_w,center.y-lift}
	ground_left := left+rl.Vector2{0,lift}
	ground_right := right+rl.Vector2{0,lift}
	ground_bottom := bottom+rl.Vector2{0,lift}
	rl.DrawTriangle(left,ground_left,ground_bottom,left_color)
	rl.DrawTriangle(left,ground_bottom,bottom,left_color)
	rl.DrawTriangle(bottom,ground_bottom,ground_right,right_color)
	rl.DrawTriangle(bottom,ground_right,right,right_color)
	rl.DrawTriangle(top,left,bottom,top_color)
	rl.DrawTriangle(top,bottom,right,top_color)
}

// Player-centered isometric card. Desktop uses a fixed card while mobile takes
// its compact safe-area layout rectangle. Zoom changes map detail, not card
// dimensions; guidance uses a target beacon or viewport-edge
// direction arrow without revealing the route through unexplored terrain.
@(private = "file")
draw_minimap :: proc(app: ^App, assets: ^Assets, card: rl.Rectangle) {
	run := &app.run
	theme := &THEMES[run.theme_index]
	panel := ui_chrome_asset(assets,.Hud_Panel)
	if !draw_ui_chrome(panel,card) {
		rl.DrawRectangleRec(card,rl.Fade(rl.BLACK,.72))
		rl.DrawRectangleLinesEx(card,1,rl.Fade(rl.WHITE,.22))
	}
	viewport := rl.Rectangle{card.x+8,card.y+7,card.width-16,card.height-14}
	if content,ok:=ui_chrome_content_rect(panel,card);ok do viewport=content
	center := Vec2{viewport.x+viewport.width*.5,viewport.y+viewport.height*.5}
	physical_scale := ui_presentation().scale
	rl.BeginScissorMode(
		i32(viewport.x*physical_scale),i32(viewport.y*physical_scale),
		max(1,i32(viewport.width*physical_scale)),max(1,i32(viewport.height*physical_scale)),
	)
	defer rl.EndScissorMode()

	half_w := MINIMAP_BASE_HALF_STEP_X*app.minimap_zoom
	half_h := MINIMAP_BASE_HALF_STEP_Y*app.minimap_zoom
	dark := run.dark_floor
	for depth in 0 ..< MAP_W+MAP_H-1 {
		x_min := max(0,depth-(MAP_H-1))
		x_max := min(MAP_W-1,depth)
		for x in x_min ..= x_max {
			y := depth-x
			vis := run.visible[x][y]
			known := dark ? vis : run.explored[x][y]
			if !known do continue
			pos := minimap_project_relative(
				Vec2{f32(x)+.5-run.player.pos.x,f32(y)+.5-run.player.pos.y},
				center,
				app.minimap_zoom,
			)
			color: rl.Color
			tile := run.dungeon.tiles[x][y]
			switch tile {
			case .Wall:
				color=rl.Color(theme.wall_edge)
			case .Floor,.Open_Door:
				color=rl.Color(theme.floor_edge)
				switch special_room_interior_kind(&run.dungeon,x,y) {
				case .Shop: color={225,190,92,255}
				case .Bar: color={196,116,72,255}
				case .Garden: color={108,178,98,255}
				case .None, .Quest, .Hall_Of_Unlost_Echoes:
					// World actors/furnishings identify these rooms without map spoilers.
				}
			case .Closed_Door:
				color=COLOR_DOOR_TOP
			case .Stairs:
				color=rl.Color(theme.stair)
			}
			if !vis do color=fog_dim(color,true)
			if tile==.Wall || tile==.Closed_Door {
				draw_minimap_block(pos,half_w,half_h,max(f32(1),half_h*1.6),color)
			} else {
				draw_minimap_diamond(pos,half_w,half_h,color)
			}
		}
	}

	marker_half_extents := Vec2{
		max(f32(0),viewport.width*.5-MINIMAP_MARKER_EDGE_INSET),
		max(f32(0),viewport.height*.5-MINIMAP_MARKER_EDGE_INSET),
	}
	markers := minimap_markers(run)
	for i in 0..<markers.count {
		marker := markers.items[i]
		projected := minimap_project_relative(marker.world_pos-run.player.pos,center,app.minimap_zoom)
		anchor,clamped := minimap_clamp_to_bounds(projected,center,marker_half_extents)
		color := marker.kind == .Bar ? rl.Color(MINIMAP_BAR_COLOR) : marker.kind == .Garden ? rl.Color(MINIMAP_GARDEN_COLOR) : rl.Color(MINIMAP_STAIRS_COLOR)
		if clamped do draw_minimap_marker_arrow(anchor,center,color)
		else do draw_minimap_marker_glyph(assets,marker.kind,anchor,f32(app.tick)*SIM_DT)
	}

	// Draw guidance after landmarks, matching pygame so an active stairs target
	// remains visibly distinguished from the ordinary discovered-stairs glyph.
	if story_content_enabled(run) {
		target, enabled := story_route_target(run)
		if enabled {
			projected := minimap_project_relative(target-run.player.pos,center,app.minimap_zoom)
			anchor, clamped := minimap_clamp_to_bounds(projected,center,marker_half_extents)
			if clamped do draw_minimap_marker_arrow(anchor,center,rl.Color(MINIMAP_GOLD_BRIGHT))
			else do draw_minimap_marker_glyph(assets,.Relic,anchor,f32(app.tick)*SIM_DT)
		}
	}

	player_color := rl.Color(MINIMAP_PLAYER_COLOR)
	rl.DrawCircleV(rl.Vector2(center),MINIMAP_PLAYER_RADIUS+1,rl.Color(MINIMAP_INK_COLOR))
	rl.DrawCircleV(rl.Vector2(center),MINIMAP_PLAYER_RADIUS,player_color)
	if tick_end,shown := minimap_player_tick_end(center,run.player.facing,app.minimap_zoom); shown {
		rl.DrawLineEx(rl.Vector2(center),rl.Vector2(tick_end),1,rl.Fade(player_color,220.0/255.0))
	}
}

@(private = "file")
draw_player_hud :: proc(view: ^View, app: ^App, assets: ^Assets) {
	if view != nil && view.mobile_mode && view.mobile_layout_valid {
		draw_mobile_player_hud(view, app, assets)
		return
	}
	sw := ui_design_width()
	sh := ui_design_height()

	// Keep the dungeon visible to the bottom edge. The authored pygame action
	// dock now floats independently at bottom center instead of sitting inside a
	// full-width HUD panel.
	dock_size := rl.Vector2{390, 81}
	dock_rect := rl.Rectangle{
		sw*.5-dock_size.x*.5,
		sh-dock_size.y-10,
		dock_size.x,
		dock_size.y,
	}
	draw_action_bar(app, assets, dock_rect)

	resource_rect := rl.Rectangle{18, sh-63-18, 240, 63}
	draw_player_resources(&app.run.player, assets, resource_rect)

	right_panel := rl.Rectangle{sw-224-18, sh-120-18, 224, 120}
	draw_player_item_panel(&app.run.player, assets, right_panel)
}

@(private = "file")
mobile_rect_to_design :: proc(rect: Mobile_Rect) -> rl.Rectangle {
	scale := max(f32(.001), ui_presentation().scale)
	return {rect.x / scale, rect.y / scale, rect.width / scale, rect.height / scale}
}

@(private = "file")
draw_mobile_button :: proc(rect: Mobile_Rect, label: cstring, accent: rl.Color = COLOR_TITLE) {
	design := mobile_rect_to_design(rect)
	rl.DrawRectangleRounded(design, .25, 8, rl.Fade(rl.Color{12,10,17,255}, .82))
	rl.DrawRectangleRoundedLinesEx(design, .25, 8, 2, rl.Fade(accent, .82))
	font := i32(clamp(design.height * .28, f32(11), f32(22)))
	width := ui_measure_text(label, font)
	ui_draw_text(label, i32(design.x + (design.width-f32(width))*.5), i32(design.y+(design.height-f32(font))*.5), font, accent)
}

@(private = "file")
draw_mobile_resource :: proc(
	asset: ^Mobile_Hud_Asset,
	rect: Mobile_Rect,
	ratio: f32,
	color: rl.Color,
	label: cstring,
) {
	design := mobile_rect_to_design(rect)
	inner := Mobile_Rect{
		rect.x + rect.width * .18,
		rect.y + rect.height * .13,
		max(f32(1), rect.width * .64),
		max(f32(1), rect.height * .74),
	}
	inner_design := mobile_rect_to_design(inner)
	rl.DrawRectangleRounded(inner_design, .35, 8, rl.Fade(rl.Color{5,4,8,255}, .90))
	fill := mobile_resource_fill_rect(inner, ratio)
	if fill.height > 0 {
		rl.BeginScissorMode(i32(fill.x), i32(fill.y), max(1, i32(fill.width)), max(1, i32(fill.height)))
		rl.DrawRectangleRounded(inner_design, .35, 8, color)
		shine := inner_design
		shine.width = max(f32(1), shine.width * .28)
		rl.DrawRectangleRounded(shine, .35, 8, rl.Fade(rl.WHITE, .18))
		rl.EndScissorMode()
	}
	if asset != nil && asset.valid {
		rl.DrawTexturePro(
			asset.tex,
			{0, 0, f32(asset.size[0]), f32(asset.size[1])},
			design,
			{0, 0},
			0,
			rl.WHITE,
		)
	} else {
		rl.DrawRectangleRoundedLinesEx(design, .16, 8, 1, rl.Fade(COLOR_TITLE, .72))
	}
	font := i32(clamp(design.width * .30, f32(7), f32(11)))
	width := ui_measure_text(label, font)
	ui_draw_text(
		label,
		i32(design.x + (design.width - f32(width)) * .5),
		i32(inner_design.y + 2),
		font,
		rl.WHITE,
	)
}

@(private = "file")
draw_mobile_joystick :: proc(assets: ^Assets, rect: Mobile_Rect, vector: Vec2) {
	if assets == nil do return
	design := mobile_rect_to_design(rect)
	base := mobile_hud_asset(assets, .Joystick_Base)
	if base.valid {
		rl.DrawTexturePro(base.tex, {0,0,f32(base.size[0]),f32(base.size[1])}, design, {0,0}, 0, rl.Fade(rl.WHITE,.88))
	} else {
		center := rl.Vector2{design.x+design.width*.5,design.y+design.height*.5}
		rl.DrawCircleV(center,min(design.width,design.height)*.5,rl.Fade(rl.Color{10,9,15,255},.48))
		rl.DrawCircleLinesV(center,min(design.width,design.height)*.5,rl.Fade(COLOR_TITLE,.58))
	}
	knob_size := min(design.width, design.height) * .62
	travel := min(design.width, design.height) * .22
	knob_rect := rl.Rectangle{
		design.x + (design.width-knob_size)*.5 + vector.x*travel,
		design.y + (design.height-knob_size)*.5 + vector.y*travel,
		knob_size,
		knob_size,
	}
	knob := mobile_hud_asset(assets, .Joystick_Knob)
	if knob.valid {
		rl.DrawTexturePro(knob.tex, {0,0,f32(knob.size[0]),f32(knob.size[1])}, knob_rect, {0,0}, 0, rl.Fade(rl.WHITE,.94))
	} else {
		center := rl.Vector2{knob_rect.x+knob_rect.width*.5,knob_rect.y+knob_rect.height*.5}
		rl.DrawCircleV(center,knob_rect.width*.34,rl.Color{36,34,42,230})
		rl.DrawCircleLinesV(center,knob_rect.width*.34,COLOR_TITLE)
	}
}

@(private = "file")
draw_mobile_hud_button :: proc(
	assets: ^Assets,
	rect: Mobile_Rect,
	label: cstring,
	accent: rl.Color,
	emphasized := false,
) {
	design := mobile_rect_to_design(rect)
	frame := action_slot_frame(assets)
	if frame.valid {
		rl.DrawTexturePro(frame.tex,{0,0,f32(frame.size[0]),f32(frame.size[1])},design,{0,0},0,rl.WHITE)
	} else {
		rl.DrawRectangleRounded(design,.2,6,rl.Fade(rl.Color{12,10,17,255},.88))
		rl.DrawRectangleRoundedLinesEx(design,.2,6,1,rl.Fade(accent,.72))
	}
	inset := design.width * .18
	inner := rl.Rectangle{design.x+inset,design.y+inset,design.width-inset*2,design.height-inset*2}
	rl.DrawRectangleRounded(inner,.22,6,rl.Fade(rl.Color{5,4,8,255},.56))
	if emphasized do rl.DrawRectangleRoundedLinesEx(inner,.22,6,2,rl.Fade(accent,.90))
	font := i32(clamp(design.height*.24,f32(10),f32(18)))
	for font > 9 && ui_measure_text(label,font) > i32(design.width*.72) do font -= 1
	width := ui_measure_text(label,font)
	x := i32(design.x+(design.width-f32(width))*.5)
	y := i32(design.y+(design.height-f32(font))*.5)
	ui_draw_text(label,x+1,y+1,font,rl.Fade(rl.BLACK,.92))
	ui_draw_text(label,x,y,font,accent)
}

@(private = "file")
draw_mobile_action_slot :: proc(app:^App,assets:^Assets,rect:Mobile_Rect,slot:int) {
	if app==nil||assets==nil||slot<1||slot>ACTION_SLOT_COUNT do return
	design:=mobile_rect_to_design(rect)
	player:=&app.run.player
	timers:=[6]f32{player.bighit_timer,player.bolt_timer,player.class_skill_timer,player.dash_timer,player.potion_timer,player.potion_timer}
	beast:=living_spirit_beast(&app.run)
	if player.archetype==.Ranger&&beast!=nil do timers[2]=0
	frame:=action_slot_frame(assets)
	if frame.valid {
		rl.DrawTexturePro(frame.tex,{0,0,f32(frame.size[0]),f32(frame.size[1])},design,{0,0},0,rl.WHITE)
	} else {
		rl.DrawRectangleRounded(design,.2,6,rl.Fade(COLOR_ROW,.9))
		rl.DrawRectangleRoundedLinesEx(design,.2,6,1,COLOR_TEXT_DIM)
	}
	icon:=action_icon_for_slot(assets,player.archetype,slot)
	if slot==3&&player.archetype==.Ranger&&beast!=nil do icon=ranger_spirit_beast_action_icon(assets,beast.command==.Attack)
	ready:=timers[slot-1]<=0
	switch slot {
	case 1: ready=ready&&!bighit_charging(player)&&player.stamina>=BIGHIT_STAMINA_COST
	case 2: ready=ready&&!bighit_charging(player)&&player.mana>=f32(player_bolt_mana_cost(player))
	case 3: ready=ready&&!bighit_charging(player)&&(beast!=nil||player.mana>=player_class_skill_mana_cost(player))
	case 4: ready=ready&&(!bighit_charging(player)||!bighit_committed(player))&&player.stamina>=f32(player_dash_stamina_cost(player))
	case 5: ready=ready&&player.heal_potions>0&&player.hp<player.max_hp
	case 6: ready=ready&&player.mana_potions>0&&player.mana<f32(player.max_mana)
	}
	if slot==4&&app_story_soul_hunt_active(app) do ready=player.dash_timer<=0
	pad:=design.width*.12
	if icon.valid {
		icon_tint := rl.WHITE
		if !ready do icon_tint = rl.Fade(rl.WHITE,.35)
		rl.DrawTexturePro(icon.tex,{0,0,f32(icon.size[0]),f32(icon.size[1])},{design.x+pad,design.y+pad,design.width-pad*2,design.height-pad*2},{0,0},0,icon_tint)
	}
	if timer:=timers[slot-1];timer>0 {
		rl.DrawRectangleRounded(design,.2,6,rl.Fade(rl.BLACK,.56))
		text:=fmt.ctprintf("%.1f",timer);font:=i32(clamp(design.height*.22,f32(10),f32(18)))
		ui_draw_text(text,i32(design.x+(design.width-f32(ui_measure_text(text,font)))*.5),i32(design.y+(design.height-f32(font))*.5),font,COLOR_TEXT)
	}
	if slot==1&&bighit_charging(player) {
		progress:=clamp(1-player.bighit_charge/BIGHIT_CHARGE_TIME,0,1)
		charge_color:=bighit_committed(player)?rl.Color{230,92,65,255}:COLOR_TITLE
		fill:=design;fill.y+=design.height*(1-progress);fill.height*=progress
		rl.DrawRectangleRec(fill,rl.Fade(charge_color,.48))
	}
	count:cstring
	if slot==5 do count=fmt.ctprintf("x%v",player.heal_potions)
	if slot==6 do count=fmt.ctprintf("x%v",player.mana_potions)
	if count!=nil do ui_draw_text(count,i32(design.x+4),i32(design.y+design.height-15),11,rl.WHITE)
}

@(private = "file")
draw_mobile_player_hud :: proc(view:^View,app:^App,assets:^Assets) {
	layout:=&view.mobile_layout
	player:=&app.run.player
	bar_frame:=mobile_hud_asset(assets,.Status_Bar_Frame)
	draw_mobile_resource(bar_frame,layout.resource_bars[0],f32(player.xp)/f32(max(player.next_xp,1)),{210,176,82,255},"XP")
	draw_mobile_resource(bar_frame,layout.resource_bars[1],f32(max(player.hp,0))/f32(max(player.max_hp,1)),{186,54,44,255},"H")
	draw_mobile_resource(bar_frame,layout.resource_bars[2],player.mana/f32(max(player.max_mana,1)),{62,110,200,255},"M")
	draw_mobile_resource(bar_frame,layout.resource_bars[3],player.stamina/f32(max(player.max_stamina,1)),{92,160,70,255},"S")
	gameplay_controls_visible:=app.mode==.Playing&&!app.death_pending&&!app.inventory_open&&
		!app.character_open&&!app.shop_open&&!app_play_modal_open(app)
	if !gameplay_controls_visible do return
	draw_mobile_joystick(assets,layout.joystick,view.mobile_joystick_vector)
	if app_story_soul_hunt_active(app) {
		draw_mobile_action_slot(app,assets,layout.action_slots[3],4)
		if app.mobile_utility_open do draw_mobile_hud_button(assets,layout.pause,"MENU",COLOR_TEXT)
		draw_mobile_hud_button(assets,layout.interact,"A",COLOR_TITLE,app.mobile_utility_open)
		return
	}
	for i in 0..<len(layout.action_slots) do draw_mobile_action_slot(app,assets,layout.action_slots[i],i+1)

	interaction_available:=player_interaction_available(&app.run)
	interaction_advertised:=player_interaction_advertised(&app.run)
	utility_open:=app.mobile_utility_open&&!interaction_available
	if utility_open {
		draw_mobile_hud_button(assets,layout.inventory,"BAG",COLOR_TEXT)
		draw_mobile_hud_button(assets,layout.character,"CHAR",COLOR_TEXT)
		draw_mobile_hud_button(assets,layout.pause,"MENU",COLOR_TEXT)
	}
	primary_accent:=interaction_advertised?COLOR_HOVER:COLOR_TITLE
	draw_mobile_hud_button(assets,layout.interact,"A",primary_accent,interaction_advertised||utility_open)
}

@(private = "file")
draw_player_resources :: proc(player: ^Player, assets: ^Assets, rect: rl.Rectangle) {
	level_bar := rl.Rectangle{rect.x, rect.y, rect.width, 12}
	health_bar := rl.Rectangle{rect.x, rect.y+14, rect.width, 18}
	mana_bar := rl.Rectangle{rect.x, rect.y+35, 180, 13}
	stamina_bar := rl.Rectangle{rect.x, rect.y+50, 180, 13}

	draw_framed_hud_bar(assets, level_bar, f32(player.xp)/f32(max(player.next_xp, 1)), rl.Color{235,205,120,255})
	draw_player_resource_value(level_bar, fmt.ctprintf("%v  %v/%v", player.level, player.xp, player.next_xp), 9)
	draw_framed_hud_bar(assets, health_bar, f32(player.hp)/f32(max(player.max_hp, 1)), rl.Color{186,54,44,255})
	draw_player_resource_value(health_bar, fmt.ctprintf("%v / %v", max(player.hp, 0), player.max_hp), 11)
	draw_framed_hud_bar(assets, mana_bar, player.mana/f32(max(player.max_mana, 1)), rl.Color{62,110,200,255})
	draw_player_resource_value(mana_bar, fmt.ctprintf("%v / %v", int(player.mana), player.max_mana), 9)
	draw_framed_hud_bar(assets, stamina_bar, player.stamina/f32(max(player.max_stamina, 1)), rl.Color{92,160,70,255})
	draw_player_resource_value(stamina_bar, fmt.ctprintf("%v / %v", int(player.stamina), player.max_stamina), 9)
}

@(private = "file")
draw_player_resource_value :: proc(bar: rl.Rectangle, value: cstring, font_size: i32) {
	x := i32(bar.x+bar.width)-ui_measure_text(value, font_size)-7
	y := i32(bar.y+(bar.height-f32(font_size))*.5)
	ui_draw_text(value, x, y, font_size, COLOR_TEXT)
}

@(private = "file")
draw_player_item_panel :: proc(player: ^Player, assets: ^Assets, rect: rl.Rectangle) {
	content := draw_player_hud_panel(assets, rect)
	draw_player_stat_row(content, 0, "GOLD", fmt.ctprintf("%v", player.gold), rl.Color{235,205,120,255})
	draw_player_stat_row(content, 1, "BAG", fmt.ctprintf("%v / %v", player.bag_count, BAG_CAPACITY), COLOR_TEXT)
	draw_player_stat_row(content, 2, "HEALTH POTION", fmt.ctprintf("%v / %v", player.heal_potions, POTION_CAPACITY), rl.Color{224,82,68,255})
	draw_player_stat_row(content, 3, "MANA POTION", fmt.ctprintf("%v / %v", player.mana_potions, POTION_CAPACITY), rl.Color{92,142,235,255})
}

@(private = "file")
draw_player_hud_panel :: proc(assets: ^Assets, rect: rl.Rectangle) -> rl.Rectangle {
	panel := ui_chrome_asset(assets, .Hud_Panel)
	if !draw_ui_chrome(panel, rect) {
		rl.DrawRectangleRec(rect, rl.Fade(rl.Color{13,11,19,255}, .92))
		rl.DrawRectangleLinesEx(rect, 1, rl.Fade(COLOR_TITLE, .55))
	}
	if safe, ok := ui_chrome_content_rect(panel, rect); ok do return safe
	return {rect.x+14, rect.y+9, rect.width-28, rect.height-18}
}


@(private = "file")
draw_player_stat_row :: proc(content: rl.Rectangle, row: int, label, value: cstring, value_color: rl.Color) {
	y := i32(content.y)+4+i32(row)*20
	x := i32(content.x)+3
	right := i32(content.x+content.width)-3
	ui_draw_text(label, x, y, 13, COLOR_TEXT_DIM)
	ui_draw_text(value, right-ui_measure_text(value, 13), y, 13, value_color)
}

@(private = "file")
draw_action_bar :: proc(app: ^App, assets: ^Assets, dock_rect: rl.Rectangle) {
	player := &app.run.player
	timers := [6]f32{player.bighit_timer,player.bolt_timer,player.class_skill_timer,player.dash_timer,player.potion_timer,player.potion_timer}
	beast := living_spirit_beast(&app.run)
	if player.archetype == .Ranger && beast != nil do timers[2]=0

	if !draw_ui_chrome(ui_chrome_asset(assets, .Hud_Dock), dock_rect) {
		rl.DrawRectangleRounded(dock_rect, .12, 8, rl.Fade(rl.Color{13,11,19,255}, .92))
		rl.DrawRectangleRoundedLinesEx(dock_rect, .12, 8, 1, rl.Fade(COLOR_TITLE, .55))
	}
	slot_size: i32 = 48
	slot_gap: i32 = 10
	total_width := i32(ACTION_SLOT_COUNT)*slot_size+i32(ACTION_SLOT_COUNT-1)*slot_gap
	x := i32(dock_rect.x+(dock_rect.width-f32(total_width))*.5)
	y := i32(dock_rect.y+14)
	for slot in 1 ..= ACTION_SLOT_COUNT {
		bx := x+i32(slot-1)*(slot_size+slot_gap)
		icon := action_icon_for_slot(assets,player.archetype,slot)
		if slot == 3 && player.archetype == .Ranger && beast != nil {
			icon = ranger_spirit_beast_action_icon(assets,beast.command==.Attack)
		}
		frame := action_slot_frame(assets)
		if frame.valid {
			rl.DrawTexturePro(frame.tex,{0,0,f32(frame.size[0]),f32(frame.size[1])},{f32(bx),f32(y),48,48},{0,0},0,rl.WHITE)
		} else {
			rl.DrawRectangle(bx,y,48,48,rl.Fade(COLOR_ROW,.9))
			rl.DrawRectangleLines(bx,y,48,48,COLOR_TEXT_DIM)
		}
		ready := timers[slot-1] <= 0
		switch slot {
		case 1: ready = ready && !bighit_charging(player) && player.stamina >= BIGHIT_STAMINA_COST
		case 2: ready = ready && !bighit_charging(player) && player.mana >= f32(player_bolt_mana_cost(player))
		case 3: ready = ready && !bighit_charging(player) && (beast != nil || player.mana >= player_class_skill_mana_cost(player))
		case 4: ready = ready && (!bighit_charging(player) || !bighit_committed(player)) && player.stamina >= f32(player_dash_stamina_cost(player))
		case 5: ready = ready && player.heal_potions > 0 && player.hp < player.max_hp
		case 6: ready = ready && player.mana_potions > 0 && player.mana < f32(player.max_mana)
		}
		if icon.valid {
			icon_tint := rl.WHITE
			if !ready do icon_tint = rl.Fade(rl.WHITE,.35)
			rl.DrawTexturePro(icon.tex,{0,0,f32(icon.size[0]),f32(icon.size[1])},{f32(bx+5),f32(y+5),38,38},{0,0},0,icon_tint)
		} else {
			ui_draw_text(fmt.ctprintf("%v",slot),bx+18,y+13,18,COLOR_TEXT)
		}
		if timer := timers[slot-1]; timer > 0 {
			rl.DrawRectangle(bx+4,y+4,40,40,rl.Fade(rl.BLACK,.56))
			ui_draw_text(fmt.ctprintf("%.1f",timer),bx+11,y+17,12,COLOR_TEXT)
		}
		if slot == 1 && bighit_charging(player) {
			progress := clamp(1-player.bighit_charge/BIGHIT_CHARGE_TIME,0,1)
			charge_color := bighit_committed(player) ? rl.Color{230,92,65,255} : COLOR_TITLE
			rl.DrawRectangle(bx+4,y+40-i32(36*progress),40,i32(36*progress),rl.Fade(charge_color,.48))
			ui_draw_text("HOLD",bx+9,y+18,10,COLOR_TEXT)
		}
		ui_draw_text(fmt.ctprintf("%v",slot),bx+3,y+2,10,COLOR_TITLE)
	}
}

@(private = "file")
draw_framed_hud_bar :: proc(assets: ^Assets, rect: rl.Rectangle, frac: f32, color: rl.Color) {
	frame := ui_chrome_asset(assets, .Hud_Bar)
	if !draw_ui_chrome(frame, rect) {
		rl.DrawRectangleRec(rect, rl.Fade(rl.BLACK, .55))
		fill := rect
		fill.width *= clamp(frac, 0, 1)
		rl.DrawRectangleRec(fill, color)
		rl.DrawRectangleLinesEx(rect, 1, rl.Fade(rl.WHITE, .25))
		return
	}
	content := rl.Rectangle{rect.x+4, rect.y+3, max(f32(1), rect.width-8), max(f32(1), rect.height-6)}
	if safe, ok := ui_chrome_content_rect(frame, rect); ok do content = safe
	rl.DrawRectangleRec(content, rl.Fade(rl.BLACK, .58))
	fill := content
	fill.width *= clamp(frac, 0, 1)
	rl.DrawRectangleRec(fill, color)
}

// Big top-center bar with nameplate while a boss is engaged.
@(private = "file")
draw_boss_bar :: proc(app: ^App) {
	if !app.run.boss_engaged do return
	for &enemy in app.run.enemies {
		if enemy.role != .Boss || enemy.hp <= 0 do continue
		sw := i32(ui_design_width())
		w: i32 = 420
		x := sw / 2 - w / 2
		y: i32 = 64
		name := fmt.ctprintf("%s", enemy_display_name(&enemy))
		ui_draw_text_fitted_centered(name, sw / 2, y - 24, 20, 14, sw - 80, rl.Color(enemy.color))
		frac := clamp(f32(enemy.hp) / f32(max(enemy.max_hp, 1)), 0, 1)
		rl.DrawRectangle(x, y, w, 12, rl.Fade(rl.BLACK, 0.65))
		rl.DrawRectangle(x, y, i32(f32(w) * frac), 12, rl.Color(enemy.color))
		rl.DrawRectangleLines(x, y, w, 12, rl.Fade(rl.WHITE, 0.4))
		return
	}
}

@(private = "file")
draw_victory_overlay :: proc(app: ^App,assets:^Assets) {
	presentation:=ui_begin_presentation()
	defer ui_end_presentation()
	rl.DrawRectangleRec({0,0,presentation.width,presentation.height},rl.Fade(rl.Color{8,6,12,255},.78))
	panel:=rl.Rectangle{presentation.width*.5-380,presentation.height*.5-140,760,280}
	draw_menu_panel_chrome(assets,panel)
	title_text := "THE GATE FALLS"
	if app.run.story_runtime.initialized {
		if verb, ok := story_verb_from_resolution(app.run.story.flags.gate); ok {
			title_text = story_ending_for(app.run.story.archetype,verb).title
		}
	}
	title := fmt.ctprintf("%s",title_text)
	title_size: i32 = 44
	for title_size > 28 && ui_measure_text(title,title_size) > i32(panel.width)-64 do title_size -= 2
	ui_draw_text(title,i32(presentation.width*.5)-ui_measure_text(title,title_size)/2,i32(panel.y+42),title_size,COLOR_TITLE)
	p:=&app.run.player
	inner_width:=i32(panel.width)-64
	summary:=fmt.ctprintf("The tyrant is dead. Depth %v conquered  -  level %v  -  %v kills  -  %v gold",app.run.depth,p.level,app.run.kills,p.gold)
	ui_draw_text_fitted_centered(summary,i32(presentation.width*.5),i32(panel.y+126),20,14,inner_width,COLOR_TEXT)
	draw_run_ledger_lines(app,presentation.width,i32(panel.y+152),inner_width)
	hint:cstring="R / Esc / click: choose another archetype"
	ui_draw_text_fitted_centered(hint,i32(presentation.width*.5),i32(panel.y+206),20,14,inner_width,COLOR_TEXT_DIM)
}

// The MX.5 run ledger under both end-of-run summaries: modifier, counters,
// and the last notable finds (state_overlay.py rows, concise Odin layout).
@(private = "file")
draw_run_ledger_lines :: proc(app: ^App, width: f32, y: i32, max_width: i32) {
	run := &app.run
	ledger := fmt.ctprintf(
		"%s · shrines %v · secrets %v · traps sprung %v · challenges %v · bars %v/%v",
		RUN_MODIFIERS[run.modifier].name, run.shrines_used, run.secrets_opened,
		run.traps_triggered, run.challenge_rooms_cleared, run.bars_toasted, run.bars_visited,
	)
	ui_draw_text_fitted_centered(ledger, i32(width*.5), y, 16, 12, max_width, COLOR_TEXT_DIM)
	if run.notable_count > 0 {
		notable: string
		start := max(0, run.notable_count - 3)
		for i in start ..< run.notable_count {
			entry := run.notable_loot[i]
			label := fmt.tprintf("%s %s", RARITIES[entry.rarity].name, entry.name)
			notable = notable == "" ? label : fmt.tprintf("%s, %s", notable, label)
		}
		line := fmt.ctprintf("Notable: %s", notable)
		ui_draw_text_fitted_centered(line, i32(width*.5), y+22, 16, 12, max_width, COLOR_TEXT_DIM)
	}
}

@(private = "file")
draw_death_overlay :: proc(app: ^App,assets:^Assets) {
	presentation:=ui_begin_presentation()
	defer ui_end_presentation()
	rl.DrawRectangleRec({0,0,presentation.width,presentation.height},rl.Fade(rl.Color{10,4,6,255},.72))
	panel:=rl.Rectangle{presentation.width*.5-350,presentation.height*.5-125,700,250}
	draw_menu_panel_chrome(assets,panel)
	title:cstring="YOU HAVE FALLEN"
	inner_width:=i32(panel.width)-64
	ui_draw_text(title,i32(presentation.width*.5)-ui_measure_text(title,40)/2,i32(panel.y+38),40,rl.Color{200,60,50,255})
	summary:=fmt.ctprintf("Depth %v reached  -  level %v  -  %v kills  -  %v gold",app.run.depth,app.run.player.level,app.run.kills,app.run.player.gold)
	ui_draw_text_fitted_centered(summary,i32(presentation.width*.5),i32(panel.y+116),20,14,inner_width,COLOR_TEXT)
	draw_run_ledger_lines(app,presentation.width,i32(panel.y+140),inner_width)
	hint:cstring="R / Esc / click: choose another archetype"
	ui_draw_text_fitted_centered(hint,i32(presentation.width*.5),i32(panel.y+192),20,14,inner_width,COLOR_TEXT_DIM)
}
