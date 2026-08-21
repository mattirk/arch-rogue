package archrogue

// Procedural dungeon floors, ported from the pygame generator
// (arch_rogue/dungeon.py): walled 72x72 grid, 8-14 padded rooms carved and
// chained with L-shaped 2-wide corridors, stairs in the last room, and a door
// pass that can seal side rooms behind closed doors. Boss floors reserve the
// final room as a large arena. Special rooms are assigned to distinct eligible
// side rooms and sealed before the ordinary door pass.
//
// Deliberate simplifications vs the pygame version:
// - No wall_depth_relief / stair sprite-perspective offsets: the rewrite
//   renders geometry centered on its logical tiles, so the compensation
//   layer (backlog cleanup item) never gets ported.
// - Solid furnishing collision comes with the special-room render integration.

import "core:math"

MAP_W :: 72
MAP_H :: 72
MIN_ROOM_COUNT :: 8
MAX_ROOM_COUNT :: 14
MAX_ROOMS_CAP :: 16 // fixed storage bound; generation never exceeds it

BOSS_ARENA_MIN_W :: 10
BOSS_ARENA_MIN_H :: 10
BOSS_ARENA_MAX_W :: 14
BOSS_ARENA_MAX_H :: 13

ACTOR_MOVE_COLLISION_RADIUS :: 0.27
STAIR_COLLISION_INSET :: 0.15

Tile_Kind :: enum u8 {
	Wall,
	Floor,
	Stairs,
	Closed_Door,
	Open_Door,
}

Room :: struct {
	x, y, w, h: int,
}

room_center :: proc(room: Room) -> [2]int {
	return {room.x + room.w / 2, room.y + room.h / 2}
}

room_intersects :: proc(a, b: Room, padding: int) -> bool {
	return !(a.x + a.w + padding < b.x ||
		b.x + b.w + padding < a.x ||
		a.y + a.h + padding < b.y ||
		b.y + b.h + padding < a.y)
}

room_random_point :: proc(room: Room, rng: ^Pcg32) -> Vec2 {
	return {
		f32(rng_range(rng, room.x + 1, room.x + room.w - 1)) + 0.5,
		f32(rng_range(rng, room.y + 1, room.y + room.h - 1)) + 0.5,
	}
}

// Fixed-size value type: comparable with ==, no allocator, trivially copied
// into save states and (later) multiplayer floor sync.
Dungeon :: struct {
	tiles:             [MAP_W][MAP_H]Tile_Kind,
	rooms_buf:         [MAX_ROOMS_CAP]Room,
	room_count:        int,
	special_rooms_buf: [MAX_SPECIAL_ROOMS]Special_Room,
	special_room_count: int,
	bar_furnishings:   Bar_Furnishing_Layout,
	hall_furnishings:  Hall_Furnishing_Layout,
	shop_gold:         Shop_Gold_Layout, // cosmetic, deterministic, walk-through
	solid_props:       Solid_Prop_Layout, // MX.5 shrines/caches: furniture, not decals
	special_room_plan: Special_Room_Plan_Trace,
	stairs:            [2]int,
	boss_arena:        bool,
}

dungeon_rooms :: proc(d: ^Dungeon) -> []Room {
	return d.rooms_buf[:d.room_count]
}

// Everything dungeon_generate authored, ignoring the furniture registry that
// population fills in afterwards. Floor *geometry* is a pure function of the
// seed and depth; which tiles population then reserves is not (shrine odds
// read difficulty, for one), so equality of maps is asked for separately.
dungeon_geometry_equal :: proc(a, b: ^Dungeon) -> bool {
	if a == nil || b == nil do return a == b
	lhs, rhs := a^, b^
	lhs.solid_props, rhs.solid_props = {}, {}
	return lhs == rhs
}

Dungeon_Options :: struct {
	boss_arena:      bool,
	story_rooms:     bool, // enable ordinary MX-story flavor planning (Hall roll)
	quest_requested: bool, // story-beat floor: reserve one sealed Quest room
	force_hall:      bool, // story guarantee: override a failed Hall roll
}

dungeon_generate :: proc(rng: ^Pcg32, opts := Dungeon_Options{}) -> (d: Dungeon, ok: bool) {
	retries := opts.boss_arena ? 30 : 20
	attempts := opts.boss_arena ? 260 : 180
	for _ in 0 ..< retries {
		d = Dungeon{boss_arena = opts.boss_arena} // tiles zero-value is all Wall
		for _ in 0 ..< attempts {
			reserving_final_arena := opts.boss_arena && d.room_count >= MIN_ROOM_COUNT - 1
			w, h: int
			if reserving_final_arena {
				w = rng_range(rng, BOSS_ARENA_MIN_W, BOSS_ARENA_MAX_W + 1)
				h = rng_range(rng, BOSS_ARENA_MIN_H, BOSS_ARENA_MAX_H + 1)
			} else {
				w = rng_range(rng, 6, 13)
				h = rng_range(rng, 6, 12)
			}
			room := Room{rng_range(rng, 2, MAP_W - w - 2), rng_range(rng, 2, MAP_H - h - 2), w, h}
			collides := false
			for existing in dungeon_rooms(&d) {
				if room_intersects(room, existing, 2) {
					collides = true
					break
				}
			}
			if collides do continue
			carve_room(&d, room)
			if d.room_count > 0 {
				connect(&d, rng, room_center(d.rooms_buf[d.room_count - 1]), room_center(room))
			}
			d.rooms_buf[d.room_count] = room
			d.room_count += 1
			if opts.boss_arena {
				if d.room_count >= MIN_ROOM_COUNT && room_is_boss_arena(room) do break
			} else if d.room_count >= MAX_ROOM_COUNT {
				break
			}
		}
		if d.room_count >= MIN_ROOM_COUNT {
			if opts.boss_arena && !room_is_boss_arena(d.rooms_buf[d.room_count - 1]) do continue
			d.stairs = room_center(d.rooms_buf[d.room_count - 1])
			d.tiles[d.stairs.x][d.stairs.y] = .Stairs
			place_doors(&d, rng, opts)
			// Story actors are authored for their dedicated sealed rooms. Retry the
			// floor rather than letting population fall back into an ordinary room.
			if opts.quest_requested && !d.special_room_plan.quest_placed do continue
			if opts.force_hall && !d.special_room_plan.hall_placed do continue
			return d, true
		}
	}
	return d, false
}

room_is_boss_arena :: proc(room: Room) -> bool {
	return room.w >= BOSS_ARENA_MIN_W && room.h >= BOSS_ARENA_MIN_H
}

@(private = "file")
carve_room :: proc(d: ^Dungeon, room: Room) {
	for x in room.x ..< room.x + room.w {
		for y in room.y ..< room.y + room.h {
			d.tiles[x][y] = .Floor
		}
	}
}

@(private = "file")
connect :: proc(d: ^Dungeon, rng: ^Pcg32, a, b: [2]int) {
	if rng_f32(rng) < 0.5 {
		carve_h(d, a.x, b.x, a.y)
		carve_v(d, a.y, b.y, b.x)
	} else {
		carve_v(d, a.y, b.y, a.x)
		carve_h(d, a.x, b.x, b.y)
	}
}

@(private = "file")
carve_h :: proc(d: ^Dungeon, x1, x2, y: int) {
	for x in min(x1, x2) ..= max(x1, x2) {
		carve_corridor_tile(d, x, y)
	}
}

@(private = "file")
carve_v :: proc(d: ^Dungeon, y1, y2, x: int) {
	for y in min(y1, y2) ..= max(y1, y2) {
		carve_corridor_tile(d, x, y)
	}
}

// Corridors carve 2 wide (the tile plus east and south neighbors) so actors
// with real collision radii fit through every hallway.
@(private = "file")
carve_corridor_tile :: proc(d: ^Dungeon, x, y: int) {
	offsets := [3][2]int{{0, 0}, {1, 0}, {0, 1}}
	for off in offsets {
		tx, ty := x + off.x, y + off.y
		if 1 <= tx && tx < MAP_W - 1 && 1 <= ty && ty < MAP_H - 1 {
			d.tiles[tx][ty] = .Floor
		}
	}
}

// --- Door pass -------------------------------------------------------------

MAX_DOORWAYS_PER_ROOM :: 24

Doorways :: struct {
	buf:   [MAX_DOORWAYS_PER_ROOM][2]int,
	count: int,
}

// Special rooms claim distinct eligible side rooms first, then every side room
// keeps pygame's ordinary 24% sealing roll. The anti-doorless fallback remains
// only for floors where both systems miss.
@(private = "file")
place_doors :: proc(d: ^Dungeon, rng: ^Pcg32, opts: Dungeon_Options) {
	if d.room_count < 3 do return
	doorways_by_room: [MAX_ROOMS_CAP]Doorways
	eligible: [MAX_ROOMS_CAP]int
	eligible_count := 0
	for room_index in 1 ..< d.room_count - 1 {
		doorways := doorways_for_room(d, d.rooms_buf[room_index])
		doorways_by_room[room_index] = doorways
		if doorways.count > 0 {
			eligible[eligible_count] = room_index
			eligible_count += 1
		}
	}

	plan_special_rooms(d, eligible[:eligible_count], &doorways_by_room, opts)
	sealed_any := d.special_room_count > 0
	fallback_room: Room
	fallback_doors: Doorways
	has_fallback := false
	for room_index in 1 ..< d.room_count - 1 {
		room := d.rooms_buf[room_index]
		doorways := doorways_by_room[room_index]
		if doorways.count == 0 do continue
		if !has_fallback {
			fallback_room = room
			fallback_doors = doorways
			has_fallback = true
		}
		if rng_f32(rng) < 0.24 {
			seal_room_with_doors(d, room, doorways)
			sealed_any = true
		}
	}
	// Keep a valid floor from becoming completely doorless when every special
	// room and ordinary roll misses.
	if !sealed_any && has_fallback {
		seal_room_with_doors(d, fallback_room, fallback_doors)
	}
	// Derived dressing sees final door geometry and consumes no dungeon/gameplay RNG.
	plan_bar_furnishings(d)
	plan_hall_furnishings(d)
	plan_shop_gold(d)
}

// A stable geometry fingerprint drives the special-room stream. It deliberately
// does not consume the layout/ordinary-door stream: adding presentation or
// population inside a flavor room cannot reshuffle the dungeon around it.
@(private = "file")
special_room_layout_seed :: proc(d: ^Dungeon) -> u64 {
	seed := u64(d.stairs.x) * 73856093 ~ u64(d.stairs.y) * 19349663 ~ u64(d.room_count) * 83492791
	for room, room_index in dungeon_rooms(d) {
		part := u64(room.x) | u64(room.y) << 8 | u64(room.w) << 16 | u64(room.h) << 24
		seed = splitmix64(seed ~ part ~ u64(room_index) * 0x9E3779B97F4A7C15)
	}
	return seed
}

@(private = "file")
plan_special_rooms :: proc(
	d: ^Dungeon,
	eligible: []int,
	doorways_by_room: ^[MAX_ROOMS_CAP]Doorways,
	opts: Dungeon_Options,
) {
	d.special_rooms_buf = {}
	d.special_room_count = 0
	d.special_room_plan = {
		quest_requested = opts.quest_requested,
		hall_enabled = opts.story_rooms || opts.quest_requested || opts.force_hall,
		hall_force_requested = opts.force_hall,
	}
	if len(eligible) == 0 do return

	candidates_for_next :: proc(d: ^Dungeon, eligible: []int) -> (candidates: [MAX_ROOMS_CAP]int, count: int) {
		for room_index in eligible {
			if room_index <= 0 || room_index >= d.room_count - 1 do continue
			if special_room_kind_for_room(d, room_index) != .None do continue
			candidates[count] = room_index
			count += 1
		}
		return
	}
	place :: proc(
		d: ^Dungeon,
		kind: Special_Room_Kind,
		room_index: int,
		doorways_by_room: ^[MAX_ROOMS_CAP]Doorways,
	) {
		if d.special_room_count >= MAX_SPECIAL_ROOMS do return
		d.special_rooms_buf[d.special_room_count] = {kind = kind, room_index = room_index}
		d.special_room_count += 1
		seal_room_with_doors(d, d.rooms_buf[room_index], doorways_by_room[room_index])
	}

	// Keep the established Shop/Bar/Garden stream and append Hall to it. Quest
	// uses its own layout-derived stream, so merely requesting story content does
	// not consume one of those historical rolls.
	flavor_rng := rng_make(special_room_layout_seed(d), stream = 6)
	guest_rng := rng_make(special_room_layout_seed(d), stream = 7)

	// Shop (75%).
	candidates, candidate_count := candidates_for_next(d, eligible)
	if candidate_count == 0 do return
	if rng_chance(&flavor_rng, 0.75) {
		place(d, .Shop, candidates[rng_below(&flavor_rng, candidate_count)], doorways_by_room)
	}

	// Quest (mandatory when the story floor requests one).
	if opts.quest_requested {
		candidates, candidate_count = candidates_for_next(d, eligible)
		if candidate_count > 0 {
			place(d, .Quest, candidates[rng_below(&guest_rng, candidate_count)], doorways_by_room)
			d.special_room_plan.quest_placed = true
		}
	}

	// Existing flavor rooms retain their exact roll/pick draw order whenever no
	// Quest room is requested.
	for kind in ([2]Special_Room_Kind{.Bar, .Garden}) {
		candidates, candidate_count = candidates_for_next(d, eligible)
		if candidate_count == 0 do return
		if !rng_chance(&flavor_rng, 0.50) do continue
		place(d, kind, candidates[rng_below(&flavor_rng, candidate_count)], doorways_by_room)
	}

	// Hall (50%) belongs to story-floor planning. A force request overrides only
	// a failed result: the roll is always consumed first so guarantee activation
	// cannot shift stream state. Non-story calls stop above and stay M9-identical.
	if !d.special_room_plan.hall_enabled do return
	candidates, candidate_count = candidates_for_next(d, eligible)
	if candidate_count == 0 do return
	d.special_room_plan.hall_roll_evaluated = true
	d.special_room_plan.hall_roll_passed = rng_chance(&flavor_rng, 0.50)
	if !d.special_room_plan.hall_roll_passed && !opts.force_hall do return
	place(d, .Hall_Of_Unlost_Echoes, candidates[rng_below(&flavor_rng, candidate_count)], doorways_by_room)
	d.special_room_plan.hall_placed = true
}

// One doorway per entrance run: the run's middle tile, matching the pygame
// generator so sealed rooms keep exactly one door per corridor opening.
@(private = "file")
doorways_for_room :: proc(d: ^Dungeon, room: Room) -> (doors: Doorways) {
	scan_edge(d, room, {room.x + 1, room.y}, {1, 0}, room.w - 2, &doors)
	scan_edge(d, room, {room.x + 1, room.y + room.h - 1}, {1, 0}, room.w - 2, &doors)
	scan_edge(d, room, {room.x, room.y + 1}, {0, 1}, room.h - 2, &doors)
	scan_edge(d, room, {room.x + room.w - 1, room.y + 1}, {0, 1}, room.h - 2, &doors)
	return doors
}

@(private = "file")
scan_edge :: proc(d: ^Dungeon, room: Room, start, step: [2]int, n: int, doors: ^Doorways) {
	run_start, run_len := 0, 0
	for i in 0 ..< n {
		p := start + step * i
		if is_room_entrance_tile(d, room, p.x, p.y) {
			if run_len == 0 do run_start = i
			run_len += 1
		} else if run_len > 0 {
			emit_doorway(doors, start + step * (run_start + run_len / 2))
			run_len = 0
		}
	}
	if run_len > 0 {
		emit_doorway(doors, start + step * (run_start + run_len / 2))
	}
}

@(private = "file")
emit_doorway :: proc(doors: ^Doorways, p: [2]int) {
	if doors.count < MAX_DOORWAYS_PER_ROOM {
		doors.buf[doors.count] = p
		doors.count += 1
	}
}

// A perimeter tile is an entrance if a corridor punched through it: floor
// with wall-run neighbors along the edge and open floor both inward and
// outward. Side tiles adjoining the stair shaft never qualify.
@(private = "file")
is_room_entrance_tile :: proc(d: ^Dungeon, room: Room, x, y: int) -> bool {
	if !dungeon_in_bounds(x, y) || d.tiles[x][y] != .Floor do return false

	side_a, side_b: [2]int
	if y == room.y || y == room.y + room.h - 1 {
		side_a, side_b = [2]int{x - 1, y}, [2]int{x + 1, y}
	} else if x == room.x || x == room.x + room.w - 1 {
		side_a, side_b = [2]int{x, y - 1}, [2]int{x, y + 1}
	} else {
		return false
	}
	for side in ([2][2]int{side_a, side_b}) {
		if !dungeon_in_bounds(side.x, side.y) || side == d.stairs do return false
	}

	inward, outward: [2]int
	switch {
	case x == room.x:
		inward, outward = [2]int{x + 1, y}, [2]int{x - 1, y}
	case x == room.x + room.w - 1:
		inward, outward = [2]int{x - 1, y}, [2]int{x + 1, y}
	case y == room.y:
		inward, outward = [2]int{x, y + 1}, [2]int{x, y - 1}
	case y == room.y + room.h - 1:
		inward, outward = [2]int{x, y - 1}, [2]int{x, y + 1}
	case:
		return false
	}
	for p in ([2][2]int{inward, outward}) {
		if !dungeon_in_bounds(p.x, p.y) || d.tiles[p.x][p.y] != .Floor do return false
	}
	return true
}

@(private = "file")
seal_room_with_doors :: proc(d: ^Dungeon, room: Room, doors: Doorways) {
	for x in room.x ..< room.x + room.w {
		seal_tile(d, doors, x, room.y)
		seal_tile(d, doors, x, room.y + room.h - 1)
	}
	for y in room.y + 1 ..< room.y + room.h - 1 {
		seal_tile(d, doors, room.x, y)
		seal_tile(d, doors, room.x + room.w - 1, y)
	}
}

@(private = "file")
seal_tile :: proc(d: ^Dungeon, doors: Doorways, x, y: int) {
	p := [2]int{x, y}
	for i in 0 ..< doors.count {
		if doors.buf[i] == p {
			d.tiles[x][y] = .Closed_Door
			return
		}
	}
	d.tiles[x][y] = .Wall
}

// --- Boss arena sealing (dungeon.py seal_room_openings) --------------------

Sealed_Tile :: struct {
	x, y: i16,
	tile: Tile_Kind,
}

// Close actual exits on the room perimeter so nothing can leave: door tiles
// and corridor-connected floor openings become locked closed doors, with the
// previous tile recorded before mutation for exact restore_sealed rollback.
// Returns the number appended so the encounter can transactionally undo only
// this sealing attempt if it cannot place every required actor safely. Falls
// back to sealing the whole passable perimeter if no entrance is detected.
seal_room_openings :: proc(d: ^Dungeon, room: Room, sealed: ^[dynamic]Sealed_Tile) -> int {
	seal_tile :: proc(d: ^Dungeon, sealed: ^[dynamic]Sealed_Tile, x, y: int) {
		if !dungeon_in_bounds(x, y) do return
		tile := d.tiles[x][y]
		if tile != .Floor && tile != .Open_Door && tile != .Closed_Door do return
		for s in sealed {
			if int(s.x) == x && int(s.y) == y do return
		}
		append(sealed, Sealed_Tile{i16(x), i16(y), tile})
		d.tiles[x][y] = .Closed_Door
	}

	has_passable_outside :: proc(d: ^Dungeon, room: Room, x, y: int) -> bool {
		neighbors := [4][2]int{{x + 1, y}, {x - 1, y}, {x, y + 1}, {x, y - 1}}
		for n in neighbors {
			if !dungeon_in_bounds(n.x, n.y) do continue
			inside := room.x <= n.x && n.x < room.x + room.w && room.y <= n.y && n.y < room.y + room.h
			if inside do continue
			#partial switch d.tiles[n.x][n.y] {
			case .Floor, .Stairs, .Open_Door:
				return true
			}
		}
		return false
	}

	before := len(sealed)
	for x in room.x ..< room.x + room.w {
		for y_edge in ([2]int{room.y, room.y + room.h - 1}) {
			tile := d.tiles[x][y_edge]
			if tile == .Open_Door || tile == .Closed_Door || (tile == .Floor && has_passable_outside(d, room, x, y_edge)) {
				seal_tile(d, sealed, x, y_edge)
			}
		}
	}
	for y in room.y + 1 ..< room.y + room.h - 1 {
		for x_edge in ([2]int{room.x, room.x + room.w - 1}) {
			tile := d.tiles[x_edge][y]
			if tile == .Open_Door || tile == .Closed_Door || (tile == .Floor && has_passable_outside(d, room, x_edge, y)) {
				seal_tile(d, sealed, x_edge, y)
			}
		}
	}
	if len(sealed) == before {
		for x in room.x ..< room.x + room.w {
			seal_tile(d, sealed, x, room.y)
			seal_tile(d, sealed, x, room.y + room.h - 1)
		}
		for y in room.y + 1 ..< room.y + room.h - 1 {
			seal_tile(d, sealed, room.x, y)
			seal_tile(d, sealed, room.x + room.w - 1, y)
		}
	}
	return len(sealed) - before
}

restore_sealed :: proc(d: ^Dungeon, sealed: []Sealed_Tile) {
	for s in sealed {
		x, y := int(s.x), int(s.y)
		if dungeon_in_bounds(x, y) do d.tiles[x][y] = s.tile
	}
}

// --- Queries ---------------------------------------------------------------

dungeon_in_bounds :: proc(x, y: int) -> bool {
	return 0 <= x && x < MAP_W && 0 <= y && y < MAP_H
}

// Floor-like tiles stay transparent to line-of-sight and projectiles; the
// stair shaft is excluded from physical walkability below.
is_floor :: proc(d: ^Dungeon, x, y: f32) -> bool {
	tx, ty := int(x), int(y)
	if !dungeon_in_bounds(tx, ty) do return false
	#partial switch d.tiles[tx][ty] {
	case .Floor, .Stairs, .Open_Door:
		return true
	}
	return false
}

is_walkable :: proc(d: ^Dungeon, x, y: f32) -> bool {
	tx, ty := int(x), int(y)
	if !dungeon_in_bounds(tx, ty) do return false
	#partial switch d.tiles[tx][ty] {
	case .Floor, .Open_Door:
		return true
	}
	return false
}

// World-space AABB the player may not enter around the stair shaft, inset so
// actors can approach the masonry rim. Only the player's block_stairs probe
// uses this; LOS, projectiles, and enemies ignore it.
stair_footprint :: proc(d: ^Dungeon) -> (ax, ay, bx, by: f32) {
	sx, sy := f32(d.stairs.x), f32(d.stairs.y)
	return sx + STAIR_COLLISION_INSET, sy + STAIR_COLLISION_INSET,
		sx + 1 - STAIR_COLLISION_INSET, sy + 1 - STAIR_COLLISION_INSET
}

@(private = "file")
probe_hits_stair :: proc(d: ^Dungeon, x, y: f32) -> bool {
	ax, ay, bx, by := stair_footprint(d)
	return ax <= x && x < bx && ay <= y && y < by
}

// Whether a square footprint intersects physical dungeon geometry. Footprints
// wider than a tile (radius >= 0.5, the 2x2 bosses) also sample the middle of
// each axis so they cannot straddle a one-tile obstacle.
blocked_for_radius :: proc(
	d: ^Dungeon,
	x, y: f32,
	radius: f32 = ACTOR_MOVE_COLLISION_RADIUS,
	block_stairs := false,
) -> bool {
	offsets_buf := [3]f32{-radius, radius, 0}
	offsets := radius >= 0.5 ? offsets_buf[:3] : offsets_buf[:2]
	for ox in offsets {
		for oy in offsets {
			px, py := x + ox, y + oy
			if block_stairs && probe_hits_stair(d, px, py) do return true
			if special_room_reserved_occupies_tile(d,int(px),int(py)) do return true
			if !is_floor(d, px, py) do return true
		}
	}
	return false
}

// March the segment in 0.25-tile steps; endpoints are skipped so actors do
// not block themselves. Diagonal transitions reject closed corners formed by
// two touching orthogonal walls.
line_of_sight :: proc(d: ^Dungeon, x0, y0, x1, y1: f32) -> bool {
	dx := x1 - x0
	dy := y1 - y0
	distance := math.hypot(dx, dy)
	if distance < 1e-3 do return true
	steps := max(1, int(math.ceil(distance / 0.25)))
	inv := 1.0 / f32(steps)
	prev_tx, prev_ty := int(x0), int(y0)
	for i in 1 ..= steps {
		t := f32(i) * inv
		px := x0 + dx * t
		py := y0 + dy * t
		tx, ty := int(px), int(py)
		if tx != prev_tx && ty != prev_ty {
			horizontal_open := is_floor(d, f32(tx) + 0.5, f32(prev_ty) + 0.5)
			vertical_open := is_floor(d, f32(prev_tx) + 0.5, f32(ty) + 0.5)
			if !horizontal_open && !vertical_open do return false
		}
		if i < steps && !is_floor(d, px, py) do return false
		prev_tx, prev_ty = tx, ty
	}
	return true
}

open_door :: proc(d: ^Dungeon, x, y: int) -> bool {
	if !dungeon_in_bounds(x, y) || d.tiles[x][y] != .Closed_Door do return false
	d.tiles[x][y] = .Open_Door
	return true
}

nearby_closed_door :: proc(d: ^Dungeon, x, y: f32, radius: f32 = 1.15) -> (door: [2]int, found: bool) {
	cx, cy := int(x), int(y)
	best := max(f32)
	search := max(1, int(radius) + 1)
	for tx in cx - search ..= cx + search {
		for ty in cy - search ..= cy + search {
			if !dungeon_in_bounds(tx, ty) || d.tiles[tx][ty] != .Closed_Door do continue
			dist := math.hypot(f32(tx) + 0.5 - x, f32(ty) + 0.5 - y)
			if dist <= radius && dist < best {
				best = dist
				door = {tx, ty}
				found = true
			}
		}
	}
	return door, found
}

room_at :: proc(d: ^Dungeon, x, y: f32) -> (room: Room, found: bool) {
	tx, ty := int(x), int(y)
	for r in dungeon_rooms(d) {
		if r.x <= tx && tx < r.x + r.w && r.y <= ty && ty < r.y + r.h {
			return r, true
		}
	}
	return room, false
}
