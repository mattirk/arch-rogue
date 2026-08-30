package archrogue

// Ambient dungeon mist: a shader-driven ground-fog layer that drifts through
// explored space and parts around moving actors. The CPU owns only a per-tile
// disturbance field (parting + tile-space displacement + visibility) uploaded
// on the same diagonal lattice as the visibility masks; the fragment shader
// adds the drifting domain-warped noise body, so uploads stay tiny and the
// look stays smooth at any zoom. Behavior knobs live in visuals.odin where
// the headless suite pins them; this file is pure raylib plumbing.

import "core:math"
import rl "../vendor/raylib"

Mist_Field :: struct {
	thin:         [MAP_W][MAP_H]f32, // 0 = undisturbed mist, 1 = fully parted
	push:         [MAP_W][MAP_H][2]f32, // tile-space displacement of the noise field
	zone:         [MAP_W][MAP_H]f32, // seeded per-room mist banks (visual_mist_zones)
	pixels:       [VISUAL_LATTICE_SIZE][VISUAL_LATTICE_SIZE]rl.Color, // [row][column]
	texture:      rl.Texture2D,
	shader:       rl.Shader,
	loc_time:     i32,
	loc_color:    i32,
	ready:        bool,
	shader_ok:    bool,
	shader_tried: bool,
	field_ready:  bool, // at least one update since the last reset
	soul_hunt:    bool, // alternate chamber field; reset before returning to the dungeon
	seed:         u64,
	depth:        int,
	floor_epoch:  u32,
}

// Cool pale mist; the alpha channel is the master opacity. Drawn inside the
// world pass, so the multiply lightmap lights it like everything else: bright
// around the lantern, dim in explored memory, black past the LOS frontier.
MIST_COLOR :: [4]f32{0.66, 0.71, 0.82, 0.42}

// R,G = push encoded around 127, B = parting, A = visibility. Tile coords are
// reconstructed from the lattice UVs exactly as visual_mask_upload lays sites
// out: site u = x - y (offset by u_lattice.y), v = x + y.
@(private = "file")
MIST_SHADER_FS :: `#version 330
in vec2 fragTexCoord;
in vec4 fragColor;
out vec4 finalColor;

uniform sampler2D texture0;
uniform float u_time;
uniform vec2 u_lattice;   // (VISUAL_LATTICE_SIZE, VISUAL_LATTICE_OFFSET)
uniform float u_push_max; // tile-unit range of the RG push encoding
uniform vec4 u_color;     // mist rgb, master opacity in a

float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

float vnoise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    float a = hash(i);
    float b = hash(i + vec2(1.0, 0.0));
    float c = hash(i + vec2(0.0, 1.0));
    float d = hash(i + vec2(1.0, 1.0));
    return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}

float fbm(vec2 p) {
    float v = 0.0;
    float amp = 0.5;
    for (int i = 0; i < 4; i++) {
        v += amp * vnoise(p);
        p = p * 2.03 + vec2(17.7, 9.2);
        amp *= 0.5;
    }
    return v;
}

void main() {
    vec4 field = texture(texture0, fragTexCoord);
    float vis = field.a;
    if (vis <= 0.004) { finalColor = vec4(0.0); return; }

    float iu = fragTexCoord.x * u_lattice.x - 0.5;
    float iv = fragTexCoord.y * u_lattice.x - 0.5;
    float du = iu - u_lattice.y;
    vec2 tile = vec2((iv + 1.0 + du) * 0.5, (iv + 1.0 - du) * 0.5);

    // Actors shove the noise body around; the gates (parting, visibility)
    // stay put so a wake swirls without leaking past the LOS frontier.
    vec2 push = (field.rg * 2.0 - 1.0) * u_push_max;
    float part = field.b;
    vec2 p = tile - push;

    // Tile-space wind along (w, -w) drifts screen-horizontally in iso view.
    vec2 wind = vec2(0.050, -0.034);
    float t = u_time;

    float banks = fbm(p * 0.55 + wind * t);
    float warp  = fbm(p * 1.4 - wind * t * 0.7 + banks * 1.35);
    float mist  = fbm(p * 2.3 + vec2(warp * 1.25, warp * 0.9) + wind * t * 1.6);

    float body = smoothstep(0.38, 0.85, banks * 0.62 + mist * 0.58);
    float haze = 0.07 + 0.06 * mist;
    float breathe = 0.90 + 0.10 * sin(t * 0.35 + banks * 6.2831);

    float density = clamp(haze + body, 0.0, 1.0) * breathe;
    density *= (1.0 - part) * vis;

    vec3 rgb = u_color.rgb * (0.82 + 0.30 * mist);
    finalColor = vec4(rgb, density * u_color.a) * fragColor;
}
`

@(private = "file")
MIST_SHADER_FS_GLES2 :: `#version 100
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif
varying vec2 fragTexCoord;
varying vec4 fragColor;

uniform sampler2D texture0;
uniform float u_time;
uniform vec2 u_lattice;
uniform float u_push_max;
uniform vec4 u_color;

float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

float vnoise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    float a = hash(i);
    float b = hash(i + vec2(1.0, 0.0));
    float c = hash(i + vec2(0.0, 1.0));
    float d = hash(i + vec2(1.0, 1.0));
    return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}

float fbm(vec2 p) {
    float v = 0.0;
    float amp = 0.5;
    for (int i = 0; i < 4; i++) {
        v += amp * vnoise(p);
        p = p * 2.03 + vec2(17.7, 9.2);
        amp *= 0.5;
    }
    return v;
}

void main() {
    vec4 field = texture2D(texture0, fragTexCoord);
    float vis = field.a;
    if (vis <= 0.004) { gl_FragColor = vec4(0.0); return; }
    float iu = fragTexCoord.x * u_lattice.x - 0.5;
    float iv = fragTexCoord.y * u_lattice.x - 0.5;
    float du = iu - u_lattice.y;
    vec2 tile = vec2((iv + 1.0 + du) * 0.5, (iv + 1.0 - du) * 0.5);
    vec2 push = (field.rg * 2.0 - 1.0) * u_push_max;
    float part = field.b;
    vec2 p = tile - push;
    vec2 wind = vec2(0.050, -0.034);
    float t = u_time;
    float banks = fbm(p * 0.55 + wind * t);
    float warp = fbm(p * 1.4 - wind * t * 0.7 + banks * 1.35);
    float mist = fbm(p * 2.3 + vec2(warp * 1.25, warp * 0.9) + wind * t * 1.6);
    float body = smoothstep(0.38, 0.85, banks * 0.62 + mist * 0.58);
    float haze = 0.07 + 0.06 * mist;
    float breathe = 0.90 + 0.10 * sin(t * 0.35 + banks * 6.2831);
    float density = clamp(haze + body, 0.0, 1.0) * breathe;
    density *= (1.0 - part) * vis;
    vec3 rgb = u_color.rgb * (0.82 + 0.30 * mist);
    gl_FragColor = vec4(rgb, density * u_color.a) * fragColor;
}
`

// WebGL2 (OpenGL ES 3.0) port of the GLES2 variant above.
@(private = "file")
MIST_SHADER_FS_ES3 :: `#version 300 es
precision highp float;
in vec2 fragTexCoord;
in vec4 fragColor;
out vec4 finalColor;

uniform sampler2D texture0;
uniform float u_time;
uniform vec2 u_lattice;
uniform float u_push_max;
uniform vec4 u_color;

float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

float vnoise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    float a = hash(i);
    float b = hash(i + vec2(1.0, 0.0));
    float c = hash(i + vec2(0.0, 1.0));
    float d = hash(i + vec2(1.0, 1.0));
    return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}

float fbm(vec2 p) {
    float v = 0.0;
    float amp = 0.5;
    for (int i = 0; i < 4; i++) {
        v += amp * vnoise(p);
        p = p * 2.03 + vec2(17.7, 9.2);
        amp *= 0.5;
    }
    return v;
}

void main() {
    vec4 field = texture(texture0, fragTexCoord);
    float vis = field.a;
    if (vis <= 0.004) { finalColor = vec4(0.0); return; }
    float iu = fragTexCoord.x * u_lattice.x - 0.5;
    float iv = fragTexCoord.y * u_lattice.x - 0.5;
    float du = iu - u_lattice.y;
    vec2 tile = vec2((iv + 1.0 + du) * 0.5, (iv + 1.0 - du) * 0.5);
    vec2 push = (field.rg * 2.0 - 1.0) * u_push_max;
    float part = field.b;
    vec2 p = tile - push;
    vec2 wind = vec2(0.050, -0.034);
    float t = u_time;
    float banks = fbm(p * 0.55 + wind * t);
    float warp = fbm(p * 1.4 - wind * t * 0.7 + banks * 1.35);
    float mist = fbm(p * 2.3 + vec2(warp * 1.25, warp * 0.9) + wind * t * 1.6);
    float body = smoothstep(0.38, 0.85, banks * 0.62 + mist * 0.58);
    float haze = 0.07 + 0.06 * mist;
    float breathe = 0.90 + 0.10 * sin(t * 0.35 + banks * 6.2831);
    float density = clamp(haze + body, 0.0, 1.0) * breathe;
    density *= (1.0 - part) * vis;
    vec3 rgb = u_color.rgb * (0.82 + 0.30 * mist);
    finalColor = vec4(rgb, density * u_color.a) * fragColor;
}
`

@(private = "file")
mist_shader_source :: proc() -> cstring {
	when ARCH_ROGUE_ANDROID do return cstring(MIST_SHADER_FS_GLES2)
	when ARCH_ROGUE_WEB do return cstring(MIST_SHADER_FS_ES3)
	return cstring(MIST_SHADER_FS)
}

@(private = "file")
ensure_mist_resources :: proc(view: ^View) -> ^Mist_Field {
	if view.mist == nil do view.mist = new(Mist_Field)
	mist := view.mist
	if !mist.ready {
		img := rl.GenImageColor(VISUAL_LATTICE_SIZE, VISUAL_LATTICE_SIZE, rl.BLANK)
		mist.texture = rl.LoadTextureFromImage(img)
		rl.UnloadImage(img)
		if rl.IsTextureValid(mist.texture) {
			rl.SetTextureFilter(mist.texture, .BILINEAR)
			rl.SetTextureWrap(mist.texture, .CLAMP)
			mist.ready = true
		}
	}
	if !mist.shader_tried {
		mist.shader_tried = true
		mist.shader = rl.LoadShaderFromMemory(nil, mist_shader_source())
		if rl.IsShaderValid(mist.shader) {
			mist.loc_time = rl.GetShaderLocation(mist.shader, "u_time")
			mist.loc_color = rl.GetShaderLocation(mist.shader, "u_color")
			lattice := [2]f32{f32(VISUAL_LATTICE_SIZE), f32(VISUAL_LATTICE_OFFSET)}
			rl.SetShaderValue(mist.shader, rl.GetShaderLocation(mist.shader, "u_lattice"), &lattice, .VEC2)
			push_max := f32(VISUAL_MIST_PUSH_MAX)
			rl.SetShaderValue(mist.shader, rl.GetShaderLocation(mist.shader, "u_push_max"), &push_max, .FLOAT)
			mist.shader_ok = true
		}
	}
	return mist.ready && mist.shader_ok ? mist : nil
}

mist_shutdown :: proc(mist: ^Mist_Field) {
	if mist == nil do return
	if mist.ready do rl.UnloadTexture(mist.texture)
	if mist.shader_ok do rl.UnloadShader(mist.shader)
	free(mist)
}

mist_shader_preflight :: proc(view:^View)->bool {
	return ensure_mist_resources(view)!=nil
}

@(private = "file")
mist_reset_field :: proc(mist: ^Mist_Field, run: ^Run) {
	mist.thin = {}
	mist.push = {}
	mist.soul_hunt = false
	mist.seed = run.seed
	mist.depth = run.depth
	mist.floor_epoch = run.floor_epoch
	visual_mist_zones(
		&run.dungeon,
		visual_mist_zone_seed(run.seed, run.depth, run.floor_epoch),
		&mist.zone,
	)
}

@(private = "file")
mist_stamp_actor :: proc(mist: ^Mist_Field, feet, velocity: Vec2, scale, dt: f32) {
	speed := math.sqrt(velocity.x * velocity.x + velocity.y * velocity.y)
	speed_norm := visual_mist_speed_norm(speed)
	blend := visual_mist_stamp_blend(dt)
	cx, cy := int(feet.x), int(feet.y)
	reach := int(math.ceil(VISUAL_MIST_CLEAR_RADIUS * scale)) + 1
	for dy in -reach ..= reach {
		for dx in -reach ..= reach {
			x, y := cx + dx, cy + dy
			if !dungeon_in_bounds(x, y) do continue
			offset := Vec2{f32(x) + 0.5 - feet.x, f32(y) + 0.5 - feet.y}
			dist_sq := offset.x * offset.x + offset.y * offset.y
			falloff := visual_mist_falloff(dist_sq / (scale * scale))
			if falloff <= 0 do continue
			target := visual_mist_clear_target(falloff, speed_norm)
			mist.thin[x][y] = visual_mist_approach(mist.thin[x][y], target, dt)
			shove := visual_mist_push_target(offset, velocity, falloff)
			mist.push[x][y] = visual_mist_push_clamp(mist.push[x][y] + shove * blend)
		}
	}
}

@(private = "file")
mist_site_sample :: proc(view: ^View, app: ^App, iu, iv: int) -> [4]f32 {
	if iu < 0 || iu >= VISUAL_LATTICE_SIZE || iv < 0 || iv >= VISUAL_LATTICE_SIZE do return {}
	u := iu - VISUAL_LATTICE_OFFSET
	if ((u + iv) & 1) != 0 do return {}
	x := (u + iv) / 2
	y := (iv - u) / 2
	if !dungeon_in_bounds(x, y) do return {}
	mist := view.mist
	if mist.soul_hunt {
		room := STORY_SOUL_HUNT_ROOM
		if x <= room.x || x >= room.x+room.w-1 || y <= room.y || y >= room.y+room.h-1 do return {}
		push := mist.push[x][y]
		return {push.x, push.y, mist.thin[x][y], 1}
	}
	vis := view.visible_mask.values[x][y]
	if !app.run.dark_floor {
		vis = max(vis, view.explored_mask.values[x][y] * VISUAL_MIST_MEMORY_LEVEL)
	}
	vis *= mist.zone[x][y]
	push := mist.push[x][y]
	return {push.x, push.y, mist.thin[x][y], vis}
}

@(private = "file")
mist_upload :: proc(view: ^View, app: ^App) {
	mist := view.mist
	for iv in 0 ..< VISUAL_LATTICE_SIZE {
		for iu in 0 ..< VISUAL_LATTICE_SIZE {
			u := iu - VISUAL_LATTICE_OFFSET
			sample: [4]f32
			if ((u + iv) & 1) == 0 {
				sample = mist_site_sample(view, app, iu, iv)
			} else {
				sample = (
					mist_site_sample(view, app, iu-1, iv) +
					mist_site_sample(view, app, iu+1, iv) +
					mist_site_sample(view, app, iu, iv-1) +
					mist_site_sample(view, app, iu, iv+1)
				) * .25
			}
			mist.pixels[iv][iu] = {
				visual_mist_push_encode(sample[0]),
				visual_mist_push_encode(sample[1]),
				u8(clamp(sample[2] * 255 + .5, 0, 255)),
				u8(clamp(sample[3] * 255 + .5, 0, 255)),
			}
		}
	}
	rl.UpdateTexture(mist.texture, raw_data(mist.pixels[:]))
	mist.field_ready = true
}

mist_update :: proc(view: ^View, app: ^App, alpha: f32) {
	mist := ensure_mist_resources(view)
	if mist == nil do return
	run := &app.run
	if mist.soul_hunt || mist.seed != run.seed || mist.depth != run.depth || mist.floor_epoch != run.floor_epoch {
		mist_reset_field(mist, run)
	}
	// Visibility gating rides the same eased masks lighting uses; keep them
	// fresh here when the lighting compositor (their usual owner) is off.
	if !app.options.lighting_enabled {
		visual_mask_sync(&view.visible_mask, app, false, view.frame_dt)
		if !run.dark_floor do visual_mask_sync(&view.explored_mask, app, true, view.frame_dt)
	}

	dt := view.frame_dt
	for x in 0 ..< MAP_W {
		for y in 0 ..< MAP_H {
			mist.thin[x][y] = visual_mist_recover(mist.thin[x][y], dt)
			mist.push[x][y] = visual_mist_push_decay(mist.push[x][y], dt)
		}
	}

	player := &run.player
	feet := player.prev_pos + (player.pos - player.prev_pos) * alpha
	mist_stamp_actor(mist, feet, (player.pos - player.prev_pos) / SIM_DT, 1, dt)
	for &enemy in run.enemies {
		if !app.dev_reveal && !tile_pos_visible(app, enemy.pos) do continue
		efeet := enemy.prev_pos + (enemy.pos - enemy.prev_pos) * alpha
		mist_stamp_actor(mist, efeet, (enemy.pos - enemy.prev_pos) / SIM_DT, enemy.big ? 1.6 : 1, dt)
	}
	for &familiar in run.familiars {
		if !app.dev_reveal && !tile_pos_visible(app, familiar.pos) do continue
		ffeet := familiar.prev_pos + (familiar.pos - familiar.prev_pos) * alpha
		mist_stamp_actor(mist, ffeet, (familiar.pos - familiar.prev_pos) / SIM_DT, 0.7, dt)
	}
	for &p in run.projectiles {
		if !app.dev_reveal && !tile_pos_visible(app, p.pos) do continue
		pfeet := p.prev_pos + (p.pos - p.prev_pos) * alpha
		mist_stamp_actor(mist, pfeet, (p.pos - p.prev_pos) / SIM_DT, 0.45, dt)
	}

	mist_upload(view, app)
}

// The chamber borrows the same drifting, actor-parted field as the dungeon,
// but gates it to the alternate room instead of consulting the saved floor's
// visibility and population. The render cache is discarded on return.
mist_update_soul_hunt :: proc(view: ^View, app: ^App, alpha: f32) {
	mist := ensure_mist_resources(view)
	if mist == nil || app == nil do return
	if !mist.soul_hunt {
		mist.thin = {}
		mist.push = {}
		mist.soul_hunt = true
		mist.field_ready = false
	}

	dt := view.frame_dt
	room := STORY_SOUL_HUNT_ROOM
	for x in room.x+1 ..< room.x+room.w-1 {
		for y in room.y+1 ..< room.y+room.h-1 {
			mist.thin[x][y] = visual_mist_recover(mist.thin[x][y], dt)
			mist.push[x][y] = visual_mist_push_decay(mist.push[x][y], dt)
		}
	}

	player := &app.run.player
	feet := player.prev_pos + (player.pos-player.prev_pos)*alpha
	mist_stamp_actor(mist,feet,(player.pos-player.prev_pos)/SIM_DT,1.15,dt)
	if ghost, active := story_soul_hunt_target_position(&app.story_minigame); active {
		// A small pocket makes the silhouette condense out of the bank instead
		// of reading as a sprite placed on top of it.
		mist_stamp_actor(mist,ghost,{},.72,dt)
	}
	mist_upload(view,app)
}

// The return dialogue freezes simulation, and Mist can be disabled mid-hunt,
// so invalidate the chamber texture immediately. Keep soul_hunt set: the next
// enabled chamber update starts from the cleared wake, while the next ordinary
// update performs a full dungeon reset.
mist_invalidate_soul_hunt :: proc(view:^View) {
	if view==nil||view.mist==nil||!view.mist.soul_hunt do return
	if view.mist.field_ready {
		view.mist.thin={}
		view.mist.push={}
	}
	view.mist.field_ready=false
}

// --- Menu mist ---------------------------------------------------------------
// The first-boot decision scene needs a thin bank without any Run: the same
// drifting-noise shader is fed a synthetic field texture whose alpha is a
// vertical density ramp (neutral push, no parting). Kept separate from the
// dungeon field so lattice uniforms and floor-reset logic never cross.

MENU_MIST_FIELD_SIZE :: 96
MENU_MIST_LATTICE    :: f32(26) // virtual tiles across the drawn rect; sets noise scale

Menu_Mist :: struct {
	texture:   rl.Texture2D,
	shader:    rl.Shader,
	loc_time:  i32,
	loc_color: i32,
	ready:     bool,
	shader_ok: bool,
	tried:     bool,
}

@(private = "file")
ensure_menu_mist_resources :: proc(view: ^View) -> ^Menu_Mist {
	mist := &view.menu_mist
	if !mist.tried {
		mist.tried = true
		img := rl.GenImageColor(MENU_MIST_FIELD_SIZE, MENU_MIST_FIELD_SIZE, rl.BLANK)
		if img.data != nil {
			pixels := ([^]rl.Color)(img.data)
			for row in 0 ..< MENU_MIST_FIELD_SIZE {
				// Density ramps toward the rect's bottom edge like ground fog.
				v := f32(row) / f32(MENU_MIST_FIELD_SIZE - 1)
				alpha := u8(clamp(math.pow(v, f32(1.35))*255 + .5, 0, 255))
				for column in 0 ..< MENU_MIST_FIELD_SIZE {
					pixels[row*MENU_MIST_FIELD_SIZE+column] = {127, 127, 0, alpha}
				}
			}
			mist.texture = rl.LoadTextureFromImage(img)
			if rl.IsTextureValid(mist.texture) {
				rl.SetTextureFilter(mist.texture, .BILINEAR)
				rl.SetTextureWrap(mist.texture, .CLAMP)
				mist.ready = true
			}
		}
		rl.UnloadImage(img)
		mist.shader = rl.LoadShaderFromMemory(nil, mist_shader_source())
		if rl.IsShaderValid(mist.shader) {
			mist.loc_time = rl.GetShaderLocation(mist.shader, "u_time")
			mist.loc_color = rl.GetShaderLocation(mist.shader, "u_color")
			lattice := [2]f32{MENU_MIST_LATTICE, MENU_MIST_LATTICE*.5}
			rl.SetShaderValue(mist.shader, rl.GetShaderLocation(mist.shader, "u_lattice"), &lattice, .VEC2)
			push_max := f32(VISUAL_MIST_PUSH_MAX)
			rl.SetShaderValue(mist.shader, rl.GetShaderLocation(mist.shader, "u_push_max"), &push_max, .FLOAT)
			mist.shader_ok = true
		}
	}
	return mist.ready && mist.shader_ok ? mist : nil
}

// Screen/design-space band of drifting mist for menu scenes; no Run required.
menu_mist_draw :: proc(view: ^View, time: f32, dst: rl.Rectangle, opacity_scale: f32 = 1) {
	if view == nil do return
	mist := ensure_menu_mist_resources(view)
	if mist == nil do return
	t := time
	rl.SetShaderValue(mist.shader, mist.loc_time, &t, .FLOAT)
	color := MIST_COLOR
	color[3] = clamp(color[3]*opacity_scale, f32(0), f32(1))
	rl.SetShaderValue(mist.shader, mist.loc_color, &color, .VEC4)
	rl.BeginShaderMode(mist.shader)
	rl.DrawTexturePro(
		mist.texture,
		{0, 0, f32(MENU_MIST_FIELD_SIZE), f32(MENU_MIST_FIELD_SIZE)},
		dst,
		{0, 0}, 0, rl.WHITE,
	)
	rl.EndShaderMode()
}

menu_mist_shutdown :: proc(mist: ^Menu_Mist) {
	if mist == nil do return
	if mist.ready do rl.UnloadTexture(mist.texture)
	if mist.shader_ok do rl.UnloadShader(mist.shader)
	mist^ = {}
}

// Drawn inside the world camera after actors, before labels/numbers, so the
// mist reads as a layer the dungeon sits in while text stays crisp and the
// screen-space lightmap multiply still lights it.
mist_draw :: proc(view: ^View, time: f32, opacity_scale: f32 = 1) {
	mist := view.mist
	if mist == nil || !mist.ready || !mist.shader_ok || !mist.field_ready do return
	t := time
	rl.SetShaderValue(mist.shader, mist.loc_time, &t, .FLOAT)
	color := MIST_COLOR
	color[3] = clamp(color[3]*opacity_scale,f32(0),f32(1))
	rl.SetShaderValue(mist.shader, mist.loc_color, &color, .VEC4)
	dst := rl.Rectangle{
		-f32(VISUAL_LATTICE_OFFSET * TILE_HALF_W) - f32(TILE_HALF_W) * .5,
		f32(TILE_HALF_H) - f32(TILE_HALF_H) * .5,
		f32(VISUAL_LATTICE_SIZE * TILE_HALF_W),
		f32(VISUAL_LATTICE_SIZE * TILE_HALF_H),
	}
	rl.BeginShaderMode(mist.shader)
	rl.DrawTexturePro(
		mist.texture,
		{0, 0, f32(VISUAL_LATTICE_SIZE), f32(VISUAL_LATTICE_SIZE)},
		dst,
		{0, 0}, 0, rl.WHITE,
	)
	rl.EndShaderMode()
}
