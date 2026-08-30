package archrogue

// Raylib-free presentation policy shared by the GPU renderer and headless tests.
// These values affect only how authoritative Run visibility/state is shown;
// simulation sight, collision, combat, saves, and future network state stay
// completely independent of them.

import "core:math"

// Static floor art commonly has four rotated variants. A linear coordinate
// expression creates obvious diagonal bands after modulo-four selection, so
// hash the floor identity and both tile axes instead. The result is stable for
// a generated floor but changes with the run, depth, or regeneration epoch.
VISUAL_FLOOR_VARIANT_SALT :: u64(0x464C4F4F525F5641)

visual_floor_variant :: proc(seed: u64, depth: int, epoch: u32, x, y: int) -> int {
	floor_key := (u64(depth) << 32) | u64(epoch)
	coordinate_key := (u64(x) << 32) | u64(y)
	floor_seed := derive_seed(derive_seed(seed, VISUAL_FLOOR_VARIANT_SALT), floor_key)
	return int(u32(splitmix64(floor_seed ~ splitmix64(coordinate_key))))
}

// Pygame 3.16 ambient model: theme-tinted light floors darken continuously
// from depth 1 to the final floor. Dark floors keep a fixed near-black wash;
// their lantern and LOS mask provide the local light.
VISUAL_AMBIENT_TINT_RATIO :: f32(0.35)
VISUAL_AMBIENT_LIGHT_LEVEL :: f32(0.36)
VISUAL_AMBIENT_DARK_LEVEL :: f32(0.10)
VISUAL_AMBIENT_DEPTH_PEAK :: f32(1.60)
VISUAL_AMBIENT_DEPTH_FLOOR :: f32(0.50)

visual_ambient_depth_factor :: proc(depth: int) -> f32 {
	d := clamp(depth, 1, DUNGEON_DEPTH)
	span := max(1, DUNGEON_DEPTH - 1)
	t := f32(d - 1) / f32(span)
	return VISUAL_AMBIENT_DEPTH_PEAK - t * (VISUAL_AMBIENT_DEPTH_PEAK - VISUAL_AMBIENT_DEPTH_FLOOR)
}

visual_ambient_level :: proc(depth: int, dark_floor: bool) -> f32 {
	if dark_floor do return VISUAL_AMBIENT_DARK_LEVEL
	return VISUAL_AMBIENT_LIGHT_LEVEL * visual_ambient_depth_factor(depth)
}

visual_theme_ambient :: proc(theme: ^Theme, depth: int, dark_floor: bool) -> [4]u8 {
	if theme == nil do return {0, 0, 0, 255}
	level := visual_ambient_level(depth, dark_floor)
	result := [4]u8{0, 0, 0, 255}
	for channel in 0 ..< 3 {
		tinted := 255.0 + (f32(theme.accent[channel]) - 255.0) * VISUAL_AMBIENT_TINT_RATIO
		result[channel] = u8(clamp(tinted * level, 0, 255))
	}
	return result
}

// Pygame 4.10.1 revelation field. A remembered/visible tile's target is based
// on Euclidean distance to the nearest unknown in-bounds tile. Out-of-bounds
// neighbors count as known so map-edge walls do not carry permanent fog.
VISUAL_FOG_FALLOFF_START :: f32(0.55)
VISUAL_FOG_FALLOFF_SPAN :: f32(1.70)
VISUAL_FOG_EASE_RATE :: f32(9.0)
VISUAL_FOG_DRAW_EPSILON :: f32(0.004)
VISUAL_FOG_FINISH_EPSILON :: f32(0.02)

visual_fog_target :: proc(mask: ^[MAP_W][MAP_H]bool, x, y: int) -> f32 {
	if mask == nil || !dungeon_in_bounds(x, y) || !mask^[x][y] do return 0
	nearest_sq := 6 // the authored search stops after sqrt(5), where V is ~1
	for dy in -2 ..= 2 {
		for dx in -2 ..= 2 {
			distance_sq := dx * dx + dy * dy
			if distance_sq == 0 || distance_sq > 5 || distance_sq >= nearest_sq do continue
			nx, ny := x + dx, y + dy
			if dungeon_in_bounds(nx, ny) && !mask^[nx][ny] do nearest_sq = distance_sq
		}
	}
	if nearest_sq > 5 do return 1
	distance := math.sqrt(f32(nearest_sq))
	return clamp((distance - VISUAL_FOG_FALLOFF_START) / VISUAL_FOG_FALLOFF_SPAN, f32(0), f32(1))
}

visual_fog_ease :: proc(current, target, dt: f32) -> f32 {
	if dt <= 0 do return current
	blend := 1 - math.exp(-VISUAL_FOG_EASE_RATE * dt)
	value := current + (target - current) * blend
	if abs(target - value) <= VISUAL_FOG_FINISH_EPSILON do return target
	return value
}

visual_live_visibility_ease :: proc(current: f32, visible: bool, dt: f32) -> f32 {
	// Loss of LOS is an information boundary and must be immediate. Reveals may
	// ease open so the edge still rolls smoothly as the player advances.
	if !visible do return 0
	return visual_fog_ease(current, 1, dt)
}

visual_triangle_wave :: proc(time, period: f32) -> f32 {
	if period <= 0 do return 0
	phase := time/period-math.floor(time/period)
	return phase <= .5 ? phase*2 : (1-phase)*2
}

visual_idle_clip_time :: proc(world_time: f32, stable_id: u32 = 0) -> f32 {
	// Render-only phase offset keeps crowds from breathing in lockstep while
	// locomotion/action clocks remain deterministic simulation state.
	return world_time + f32(stable_id % 17) * .137
}

// The Lossless Soul has authored Walk and Dance clips but no Idle clip. Before
// a verdict, Waiting deliberately holds Dance frame zero between ambient
// gestures. Once armed as an ally, the same looping Dance clip becomes its idle
// animation so settling the Mistbound result cannot leave the NPC frozen.
visual_lossless_soul_clip :: proc(
	armed, moving, dancing: bool,
	anim_time, world_time: f32,
) -> (clip: Clip_Kind, clip_time: f32) {
	if moving do return .Walk,anim_time
	if dancing do return .Dance,anim_time
	if armed do return .Dance,world_time
	return .Dance,0
}

VISUAL_MINIBOSS_FOIL_PERIOD :: f32(3.4)

visual_miniboss_effect_enabled :: proc(role: Enemy_Role) -> bool {
	return role == .Miniboss
}

visual_miniboss_effect_phase :: proc(stable_id: u32) -> f32 {
	return f32(stable_id % 23) / 23
}

visual_miniboss_foil_progress :: proc(world_time: f32, stable_id: u32) -> f32 {
	phase := world_time / VISUAL_MINIBOSS_FOIL_PERIOD + visual_miniboss_effect_phase(stable_id)
	return phase - math.floor(phase)
}

// MX.6 combat-readability geometry. All helpers use raylib-free world-pixel
// offsets so the renderer only translates plans into draw calls.

Visual_Aim_Cone :: struct {
	valid:              bool,
	center_offset:      Vec2,
	direction:          Vec2,
	angle_degrees:      f32,
	inner_radius:       f32,
	outer_radius:       f32,
	half_angle_degrees: f32,
}

visual_iso_direction :: proc(tile_direction: Vec2) -> Vec2 {
	screen := Vec2{
		tile_direction.x - tile_direction.y,
		(tile_direction.x + tile_direction.y) * .5,
	}
	length := math.hypot(screen.x, screen.y)
	return length > 1e-5 ? screen / length : Vec2{}
}

visual_aim_cone :: proc(facing: Vec2) -> Visual_Aim_Cone {
	direction := visual_iso_direction(facing)
	if direction == {} do return {}
	return {
		valid = true,
		center_offset = direction * 14 + Vec2{0, -8 + direction.y * 6},
		direction = direction,
		angle_degrees = math.atan2(direction.y, direction.x) * 180 / math.PI,
		inner_radius = 16,
		outer_radius = 60.5,
		half_angle_degrees = .21 * 180 / math.PI,
	}
}

Visual_Enemy_Telegraph_Kind :: enum u8 {
	None,
	Melee,
	Bolt,
	Fan,
	Nova,
}

Visual_Enemy_Telegraph :: struct {
	valid:            bool,
	kind:             Visual_Enemy_Telegraph_Kind,
	aim:              Vec2,
	attack_range:     f32,
	spread:           f32,
	projectile_count: int,
	progress:         f32,
	imminent:         bool,
	large:            bool,
}

// Classify the committed attack while it is winding up. The renderer uses this
// plan to draw an honest directional or radial tell without consulting mutable
// gameplay state of its own.
visual_enemy_telegraph :: proc(enemy: ^Enemy) -> Visual_Enemy_Telegraph {
	if enemy == nil || enemy.hp <= 0 || enemy.ai != .Windup do return {}

	aim := enemy.windup_aim
	if aim == {} do aim = enemy.facing
	length := math.hypot(aim.x, aim.y)
	if length <= 1e-5 do return {}
	aim /= length

	result := Visual_Enemy_Telegraph{
		valid = true,
		kind = .Melee,
		aim = aim,
		attack_range = max(f32(.85), enemy.attack_range),
		projectile_count = 1,
		large = enemy.big || enemy.role == .Miniboss || enemy.role == .Boss,
	}
	if enemy.windup_duration > 0 {
		result.progress = clamp(1-enemy.windup/enemy.windup_duration,f32(0),f32(1))
	} else {
		result.progress = 1
	}
	result.imminent = enemy.windup_duration <= 0 ||
		enemy.windup <= min(f32(.28),enemy.windup_duration*f32(.65))

	pending := enemy.pending_ability
	if pending >= 0 && pending < enemy.ability_count {
		ability := ABILITY_DEFS[enemy.abilities[pending]]
		if ability.attack_range > 0 do result.attack_range = ability.attack_range
		result.spread = ability.spread
		result.projectile_count = max(1,ability.proj_count)
		switch ability.effect {
		case .Strike: result.kind = .Melee
		case .Bolt:   result.kind = .Bolt
		case .Fan:    result.kind = .Fan
		case .Nova:   result.kind = .Nova
		}
		return result
	}

	if pending == PENDING_LEGACY_CAST {
		result.kind = .Fan
		result.attack_range = max(f32(4),result.attack_range)
		result.spread = .28
		result.projectile_count = 3
	} else if pending != PENDING_LEGACY_MELEE && enemy.ranged {
		result.kind = enemy.big ? .Fan : .Bolt
		if enemy.big {
			result.spread = .28
			result.projectile_count = 3
		}
	}
	return result
}

// A tile-space circle projects to an axis-aligned world-space ellipse. The
// returned Vec2 stores horizontal radius in x and vertical radius in y.
visual_iso_radial_radii :: proc(radius_tiles, progress: f32) -> Vec2 {
	scaled_radius := max(f32(0), radius_tiles) * clamp(progress, f32(0), f32(1))
	root_two := math.sqrt(f32(2))
	return {
		scaled_radius * f32(TILE_HALF_W) * root_two,
		scaled_radius * f32(TILE_HALF_H) * root_two,
	}
}

// angle_radians parameterizes the projected ellipse from its horizontal axis.
// The tile-space basis remains circular: horizontal is (1,-1)/sqrt(2), while
// vertical is (1,1)/sqrt(2), so every endpoint agrees with world_from_tile.
visual_iso_radial_offset :: proc(radius_tiles, progress, angle_radians: f32) -> Vec2 {
	scaled_radius := max(f32(0), radius_tiles) * clamp(progress, f32(0), f32(1))
	component := scaled_radius / math.sqrt(f32(2))
	cosine := math.cos(angle_radians)
	sine := math.sin(angle_radians)
	return world_from_tile({
		component * (cosine + sine),
		component * (sine - cosine),
	})
}

// Engulf-room Nova flashes advance one Manhattan tile per fixed simulation
// step. Reached tiles share the event's bounded life fade; unreached tiles stay
// dark, so this remains deterministic and independent of render frame rate.
visual_nova_room_flash_strength :: proc(event: ^Feel_Event, tile_pos: Vec2) -> f32 {
	if event == nil || event.kind != .Nova || !event.engulf_room || event.duration <= 0 do return 0
	manhattan_distance := abs(tile_pos.x - event.pos.x) + abs(tile_pos.y - event.pos.y)
	elapsed := max(f32(0), event.duration - event.remaining)
	if elapsed / f32(SIM_DT) < manhattan_distance do return 0
	return feel_life(event)
}

Visual_Enemy_Pose :: enum u8 {
	Locomotion,
	Attack,
	Cast,
}

visual_enemy_pose :: proc(enemy: ^Enemy, has_attack, has_cast: bool) -> Visual_Enemy_Pose {
	if enemy == nil || enemy.action_kind == .None || enemy.action_timer <= 0 do return .Locomotion
	switch enemy.action_kind {
	case .Attack:
		return has_attack ? Visual_Enemy_Pose.Attack : Visual_Enemy_Pose.Locomotion
	case .Cast:
		// Pygame deliberately keeps every boss ability on its authored attack
		// sheet. Ordinary casters use Cast only when that action was authored;
		// their cast-origin cue remains the geometry fallback otherwise.
		if enemy.role == .Boss do return has_attack ? Visual_Enemy_Pose.Attack : Visual_Enemy_Pose.Locomotion
		return has_cast ? Visual_Enemy_Pose.Cast : Visual_Enemy_Pose.Locomotion
	case .None:
	}
	return .Locomotion
}

visual_familiar_uses_attack_pose :: proc(attack_timer: f32, has_attack: bool) -> bool {
	return attack_timer > 0 && has_attack
}

VISUAL_PROJECTILE_FRAME_COUNT :: 4
VISUAL_PROJECTILE_FPS :: f32(12)
VISUAL_PROJECTILE_TRAIL_COUNT :: 4

Visual_Projectile_Trail :: struct {
	offset: Vec2,
	alpha:  f32,
	radius: f32,
}

// visual_age is authoritative at projectile.pos. Rendering interpolates from
// prev_pos to pos, so its presentation clock must interpolate over that same
// fixed step rather than advance one step beyond the projectile.
visual_projectile_render_age :: proc(visual_age, alpha: f32) -> f32 {
	previous_age := max(f32(0), visual_age - f32(SIM_DT))
	t := clamp(alpha, f32(0), f32(1))
	if t <= 0 do return previous_age
	if t >= 1 do return visual_age
	return previous_age + (visual_age - previous_age) * t
}

visual_projectile_frame :: proc(age: f32) -> int {
	if age <= 0 do return 0
	return int(age * VISUAL_PROJECTILE_FPS) % VISUAL_PROJECTILE_FRAME_COUNT
}

visual_projectile_rotation :: proc(velocity: Vec2) -> f32 {
	direction := visual_iso_direction(velocity)
	if direction == {} do return 0
	return math.atan2(direction.y, direction.x) * 180 / math.PI
}

visual_projectile_trails :: proc(velocity: Vec2, age: f32) -> [VISUAL_PROJECTILE_TRAIL_COUNT]Visual_Projectile_Trail {
	result: [VISUAL_PROJECTILE_TRAIL_COUNT]Visual_Projectile_Trail
	direction := visual_iso_direction(velocity)
	if direction == {} do return result
	perpendicular := Vec2{-direction.y, direction.x}
	alphas := [VISUAL_PROJECTILE_TRAIL_COUNT]f32{136.0/255.0,92.0/255.0,54.0/255.0,26.0/255.0}
	for i in 0 ..< VISUAL_PROJECTILE_TRAIL_COUNT {
		step := f32(i + 1)
		side := math.sin(age * 12 + step) * 2
		result[i] = {
			offset = -direction * (step * 9) - perpendicular * side,
			alpha = alphas[i],
			radius = 3.5 - f32(i) * .45,
		}
	}
	return result
}

Visual_Slash_Sample :: struct {
	valid:        bool,
	direction:    Vec2,
	perpendicular: Vec2,
	center_offset: Vec2,
	scale:        f32,
	alpha:        f32,
}

visual_slash_sample :: proc(event: ^Feel_Event) -> Visual_Slash_Sample {
	if event == nil || event.kind != .Slash do return {}
	life := feel_life(event)
	direction := visual_iso_direction(event.direction)
	if direction == {} do direction = {1, 0}
	growth: f32 = 1
	if life < .7 do growth += (.7 - life) * .25
	travel := 1 - life
	return {
		valid = true,
		direction = direction,
		perpendicular = {-direction.y, direction.x},
		center_offset = {direction.x * travel * 12, -18 + direction.y * travel * 6},
		scale = growth * (event.heavy ? f32(1.18) : f32(1)),
		alpha = life,
	}
}

visual_knockback_samples :: proc(event: ^Feel_Event) -> [2]Vec2 {
	if event == nil || event.kind != .Knockback_Travel do return {}
	direction := event.direction
	length := math.hypot(direction.x, direction.y)
	if length <= 1e-5 do return {event.pos, event.pos}
	direction /= length
	return {
		event.pos + direction * (event.radius * .35),
		event.pos + direction * (event.radius * .70),
	}
}

// Pygame 4.9 actor-through-wall policy. Rectangle overlap is weighted by how
// far the occluder lies in front, tiny grazes are discarded, and summed cover
// ramps into a continuous target before render-time temporal easing.
VISUAL_GHOST_MIN_DEPTH_GAP :: f32(0.25)
VISUAL_GHOST_FULL_DEPTH_GAP :: f32(1.00)
VISUAL_GHOST_MIN_CLIP_COVERAGE :: f32(0.02)
VISUAL_GHOST_COVERAGE_RAMP_START :: f32(0.45)
VISUAL_GHOST_COVERAGE_RAMP_FULL :: f32(0.90)
VISUAL_GHOST_WEIGHT_FLOOR :: f32(0.15)
VISUAL_GHOST_EASE_RATE :: f32(20.0)
VISUAL_GHOST_SPRITE_ALPHA :: f32(112.0 / 255.0)
VISUAL_GHOST_AURA_ALPHA :: f32(96.0 / 255.0)
VISUAL_RELIC_GHOST_SPRITE_ALPHA :: f32(0.78)
VISUAL_RELIC_GHOST_AURA_ALPHA :: f32(0.58)
VISUAL_WALL_PAINTER_DEPTH_OFFSET :: f32(1.02)

visual_ghost_coverage_contribution :: proc(depth_gap, clip_fraction: f32) -> f32 {
	if depth_gap <= VISUAL_GHOST_MIN_DEPTH_GAP || clip_fraction <= VISUAL_GHOST_MIN_CLIP_COVERAGE do return 0
	span := VISUAL_GHOST_FULL_DEPTH_GAP - VISUAL_GHOST_MIN_DEPTH_GAP
	depth_weight := clamp((depth_gap - VISUAL_GHOST_MIN_DEPTH_GAP) / span, f32(0), f32(1))
	return depth_weight * clamp(clip_fraction, f32(0), f32(1))
}

visual_ghost_target :: proc(weighted_coverage: f32) -> f32 {
	span := VISUAL_GHOST_COVERAGE_RAMP_FULL - VISUAL_GHOST_COVERAGE_RAMP_START
	return clamp((weighted_coverage - VISUAL_GHOST_COVERAGE_RAMP_START) / span, f32(0), f32(1))
}

visual_ghost_ease :: proc(current, target, dt: f32) -> f32 {
	if dt <= 0 do return current
	blend := 1 - math.exp(-VISUAL_GHOST_EASE_RATE * dt)
	return current + (target - current) * blend
}

// Ambient dungeon mist. The renderer keeps a per-tile disturbance field
// (parting + tile-space displacement) that actors stamp as they move; a
// fragment shader supplies the drifting noise body. These knobs are the whole
// behavioral contract: how far presence parts the mist, how hard wakes shove
// it, and how long a carved trail lingers before the mist seeps back.
VISUAL_MIST_CLEAR_RADIUS :: f32(1.15) // tiles an actor's presence parts
VISUAL_MIST_REFERENCE_SPEED :: f32(PLAYER_MOVE_SPEED) // speed of a full-strength wake
VISUAL_MIST_STAND_CLEAR :: f32(0.30) // parting from standing presence
VISUAL_MIST_WALK_CLEAR :: f32(0.95) // parting at reference walk speed
VISUAL_MIST_STAMP_RATE :: f32(14.0) // approach rate toward a stamp target
VISUAL_MIST_RECOVER_RATE :: f32(0.42) // refill; tau ~2.4 s keeps wakes lingering
VISUAL_MIST_PUSH_RADIAL :: f32(0.14) // tiles of outward shove from presence
VISUAL_MIST_PUSH_WAKE :: f32(0.50) // tiles of along-motion shove at reference speed
VISUAL_MIST_PUSH_DECAY_RATE :: f32(1.1) // displaced mist settles; tau ~0.9 s
VISUAL_MIST_PUSH_MAX :: f32(0.80) // tiles; also the RG texture encode range
VISUAL_MIST_MEMORY_LEVEL :: f32(0.50) // mist strength over explored-but-unseen tiles
VISUAL_MIST_INTERIOR_LEVEL :: f32(0.25) // ordinary special interiors keep most mist out; Hall is exempt

// Mist claims a seeded subset of each floor's rooms and laps a few tiles out
// through openings, so stepping into a fogged chamber reads as a change of
// place instead of a global screen filter. Ordinary special rooms host, never
// fog; the Hall of Unlost Echoes is the deliberate exception and always banks.
VISUAL_MIST_ROOM_CHANCE :: f32(0.42)
VISUAL_MIST_BLEED_FALLOFF :: f32(0.62) // per-tile decay while lapping through openings
VISUAL_MIST_BLEED_PASSES :: 3
VISUAL_MIST_WALL_LAP :: f32(0.80) // banks read against bounding walls, not a tile short

visual_mist_zone_seed :: proc(seed: u64, depth: int, epoch: u32) -> u64 {
	return derive_seed(derive_seed(seed, 0x4D495354), (u64(depth) << 32) | u64(epoch))
}

@(private = "file")
visual_mist_zone_stamp_room :: proc(d: ^Dungeon, zone: ^[MAP_W][MAP_H]f32, room: Room) {
	for x in room.x ..< room.x + room.w {
		for y in room.y ..< room.y + room.h {
			if dungeon_in_bounds(x, y) && d.tiles[x][y] != .Wall do zone^[x][y] = 1
		}
	}
}

visual_mist_zones :: proc(d: ^Dungeon, seed: u64, zone: ^[MAP_W][MAP_H]f32) {
	zone^ = {}
	if d == nil || d.room_count <= 0 do return
	rng := rng_make(seed)
	misty_any := false
	for i in 0 ..< d.room_count {
		// Roll for every room, even hosts, so candidacy rules never reshuffle
		// which of the remaining rooms fog up on an already-seen floor.
		roll := rng_chance(&rng, VISUAL_MIST_ROOM_CHANCE)
		if special, is_special := special_room_at_room_index(d, i); is_special {
			if special.kind == .Hall_Of_Unlost_Echoes {
				misty_any = true
				visual_mist_zone_stamp_room(d, zone, d.rooms_buf[i])
			}
			continue
		}
		if !roll do continue
		misty_any = true
		visual_mist_zone_stamp_room(d, zone, d.rooms_buf[i])
	}
	if !misty_any {
		start := rng_below(&rng, d.room_count)
		for offset in 0 ..< d.room_count {
			i := (start + offset) % d.room_count
			if _, special := special_room_at_room_index(d, i); special do continue
			visual_mist_zone_stamp_room(d, zone, d.rooms_buf[i])
			break
		}
	}
	// Walls hold zero throughout the spread passes, so banks lap through
	// doorways and open corridor mouths but never tunnel through masonry.
	for _ in 0 ..< VISUAL_MIST_BLEED_PASSES {
		spread := zone^
		for x in 0 ..< MAP_W {
			for y in 0 ..< MAP_H {
				if d.tiles[x][y] == .Wall do continue
				best := spread[x][y]
				if x > 0 do best = max(best, spread[x-1][y] * VISUAL_MIST_BLEED_FALLOFF)
				if x < MAP_W-1 do best = max(best, spread[x+1][y] * VISUAL_MIST_BLEED_FALLOFF)
				if y > 0 do best = max(best, spread[x][y-1] * VISUAL_MIST_BLEED_FALLOFF)
				if y < MAP_H-1 do best = max(best, spread[x][y+1] * VISUAL_MIST_BLEED_FALLOFF)
				zone^[x][y] = best
			}
		}
	}
	for x in 0 ..< MAP_W {
		for y in 0 ..< MAP_H {
			if d.tiles[x][y] == .Wall {
				best := f32(0)
				if x > 0 && d.tiles[x-1][y] != .Wall do best = max(best, zone^[x-1][y])
				if x < MAP_W-1 && d.tiles[x+1][y] != .Wall do best = max(best, zone^[x+1][y])
				if y > 0 && d.tiles[x][y-1] != .Wall do best = max(best, zone^[x][y-1])
				if y < MAP_H-1 && d.tiles[x][y+1] != .Wall do best = max(best, zone^[x][y+1])
				zone^[x][y] = best * VISUAL_MIST_WALL_LAP
			} else {
				kind := special_room_interior_kind(d, x, y)
				if kind != .None && kind != .Hall_Of_Unlost_Echoes {
					zone^[x][y] *= VISUAL_MIST_INTERIOR_LEVEL
				}
			}
		}
	}
}

// Quadratic presence falloff over the squared distance so per-cell stamping
// needs no square roots. dist_sq is pre-divided by the actor's scale^2.
visual_mist_falloff :: proc(dist_sq: f32) -> f32 {
	radius_sq :: VISUAL_MIST_CLEAR_RADIUS * VISUAL_MIST_CLEAR_RADIUS
	t := 1 - dist_sq / radius_sq
	if t <= 0 do return 0
	return t * t
}

visual_mist_speed_norm :: proc(speed: f32) -> f32 {
	return clamp(speed / VISUAL_MIST_REFERENCE_SPEED, f32(0), f32(1))
}

visual_mist_clear_target :: proc(falloff, speed_norm: f32) -> f32 {
	return falloff * (VISUAL_MIST_STAND_CLEAR + (VISUAL_MIST_WALK_CLEAR - VISUAL_MIST_STAND_CLEAR) * speed_norm)
}

visual_mist_stamp_blend :: proc(dt: f32) -> f32 {
	if dt <= 0 do return 0
	return 1 - math.exp(-VISUAL_MIST_STAMP_RATE * dt)
}

// Stamps only deepen the parting; refill is owned by visual_mist_recover so a
// slow frame can never snap an existing wake shut.
visual_mist_approach :: proc(current, target, dt: f32) -> f32 {
	if target <= current do return current
	return current + (target - current) * visual_mist_stamp_blend(dt)
}

visual_mist_recover :: proc(thin, dt: f32) -> f32 {
	if dt <= 0 do return thin
	return thin * math.exp(-VISUAL_MIST_RECOVER_RATE * dt)
}

visual_mist_push_decay :: proc(push: [2]f32, dt: f32) -> [2]f32 {
	if dt <= 0 do return push
	return push * math.exp(-VISUAL_MIST_PUSH_DECAY_RATE * dt)
}

// offset: cell center relative to actor feet (tiles); velocity in tiles/s.
// Presence shoves mist radially, motion adds an along-velocity wake.
visual_mist_push_target :: proc(offset, velocity: [2]f32, falloff: f32) -> [2]f32 {
	dist := math.sqrt(offset.x * offset.x + offset.y * offset.y)
	radial := dist > 1e-4 ? offset / dist : [2]f32{}
	speed := math.sqrt(velocity.x * velocity.x + velocity.y * velocity.y)
	speed_norm := visual_mist_speed_norm(speed)
	wake := speed > 1e-4 ? velocity / speed : [2]f32{}
	radial_strength := VISUAL_MIST_PUSH_RADIAL * (0.4 + 0.6 * speed_norm)
	return (radial * radial_strength + wake * (VISUAL_MIST_PUSH_WAKE * speed_norm)) * falloff
}

visual_mist_push_clamp :: proc(push: [2]f32) -> [2]f32 {
	max_sq :: VISUAL_MIST_PUSH_MAX * VISUAL_MIST_PUSH_MAX
	mag_sq := push.x * push.x + push.y * push.y
	if mag_sq <= max_sq do return push
	return push * (VISUAL_MIST_PUSH_MAX / math.sqrt(mag_sq))
}

visual_mist_push_encode :: proc(component: f32) -> u8 {
	normalized := clamp(component / VISUAL_MIST_PUSH_MAX, f32(-1), f32(1))
	return u8(clamp(normalized * 127.5 + 127.5, 0, 255))
}
