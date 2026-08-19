package archrogue

// MX.2.3: radius-limited navigation field ported from pygame combat/pathing.py.
// One field tracks the player (the only pursuit target); it is a unit-cost
// 8-connected BFS out to NAV_FIELD_RADIUS with a closed-corner rule, rebuilt
// when the player crosses a tile boundary, the refresh window lapses, or the
// floor regenerates. Enemies keep greedy straight-line motion whenever the
// field says the direct route is genuinely short and furnishing-free, so open
// rooms never read as grid-following. Deterministic — no RNG, no allocation.

import "core:math"

NAV_UNREACHED :: 255

Nav_Field :: struct {
	cost:        [MAP_W][MAP_H]u8,
	queue:       [MAP_W * MAP_H][2]u8, // BFS scratch, kept off the stack
	origin:      [2]int,
	age:         f32,
	floor_epoch: u32,
	built:       bool,
}

// pathing.py NEIGHBOR_OFFSETS, exact order: it is the candidate tie-breaker.
@(rodata)
NAV_NEIGHBORS := [8][2]int{{-1, -1}, {0, -1}, {1, -1}, {-1, 0}, {1, 0}, {-1, 1}, {0, 1}, {1, 1}}

@(private = "file")
nav_tile_open :: proc(d: ^Dungeon, x, y: int) -> bool {
	if !dungeon_in_bounds(x, y) do return false
	if !is_floor(d, f32(x) + 0.5, f32(y) + 0.5) do return false
	return !special_room_reserved_occupies_tile(d, x, y)
}

@(private = "file")
nav_probe_furnishing :: proc(d: ^Dungeon, p: Vec2) -> bool {
	return special_room_reserved_occupies_tile(d, int(p.x), int(p.y))
}

nav_field_refresh :: proc(run: ^Run, dt: f32) {
	nav := &run.nav
	nav.age += dt
	tile := [2]int{int(run.player.pos.x), int(run.player.pos.y)}
	if nav.built && nav.floor_epoch == run.floor_epoch && nav.origin == tile &&
		nav.age <= NAV_REFRESH_SECONDS {
		return
	}
	nav_field_build(run, tile)
}

@(private = "file")
nav_field_build :: proc(run: ^Run, origin: [2]int) {
	nav := &run.nav
	nav.origin = origin
	nav.age = 0
	nav.floor_epoch = run.floor_epoch
	nav.built = true
	for x in 0 ..< MAP_W {
		for y in 0 ..< MAP_H {
			nav.cost[x][y] = NAV_UNREACHED
		}
	}
	d := &run.dungeon
	if !dungeon_in_bounds(origin.x, origin.y) do return
	// The origin only needs standable floor; furnishing occupancy is legal
	// there (pathing.py builds fields for targets pressed against tables).
	if !is_floor(d, f32(origin.x) + 0.5, f32(origin.y) + 0.5) do return
	nav.cost[origin.x][origin.y] = 0
	head, tail := 0, 0
	nav.queue[tail] = {u8(origin.x), u8(origin.y)}
	tail += 1
	for head < tail {
		tx := int(nav.queue[head][0])
		ty := int(nav.queue[head][1])
		head += 1
		cost := int(nav.cost[tx][ty])
		if cost >= NAV_FIELD_RADIUS do continue
		for offset in NAV_NEIGHBORS {
			nx, ny := tx + offset[0], ty + offset[1]
			if !dungeon_in_bounds(nx, ny) do continue
			if nav.cost[nx][ny] != NAV_UNREACHED do continue
			if !nav_tile_open(d, nx, ny) do continue
			if offset[0] != 0 && offset[1] != 0 {
				// Closed-corner rule: a diagonal needs one open orthogonal side.
				if !is_floor(d, f32(nx) + 0.5, f32(ty) + 0.5) &&
					!is_floor(d, f32(tx) + 0.5, f32(ny) + 0.5) {
					continue
				}
			}
			nav.cost[nx][ny] = u8(cost + 1)
			nav.queue[tail] = {u8(nx), u8(ny)}
			tail += 1
		}
	}
}

// pathing.py enemy_nav_direction. routed=false means "go greedy": either the
// direct route is valid or routing has nothing better to offer. 2x2 bosses
// never tile-route. A stall latch (nav_latch) bypasses the greedy gates so a
// recently blocked enemy keeps descending the field.
enemy_nav_direction :: proc(run: ^Run, enemy: ^Enemy) -> (dir: Vec2, routed: bool) {
	if enemy.big do return {}, false
	nav := &run.nav
	if !nav.built || nav.floor_epoch != run.floor_epoch do return {}, false
	ex, ey := int(enemy.pos.x), int(enemy.pos.y)
	if !dungeon_in_bounds(ex, ey) do return {}, false
	d := &run.dungeon
	target := run.player.pos
	raw := nav.cost[ex][ey]
	cost := int(raw)
	if raw != NAV_UNREACHED && cost <= 0 do return {}, false
	if raw == NAV_UNREACHED {
		// Standing off-field (reserved strip): any costed neighbor routes us
		// back on, treating our own cost as effectively infinite.
		cost = NAV_FIELD_RADIUS + 1
	} else if enemy.nav_latch <= 0 {
		if cost <= NAV_DIRECT_COST do return {}, false
		estimate := max(abs(ex - nav.origin.x), abs(ey - nav.origin.y))
		if cost <= estimate {
			// Direct route is as short as the field: greedy, unless a solid
			// furnishing sits on the straight line just ahead.
			v := target - enemy.pos
			l := math.hypot(v.x, v.y)
			if l < 0.001 do return {}, false
			u := v / l
			if !nav_probe_furnishing(d, enemy.pos + u * 0.34) &&
				!nav_probe_furnishing(d, enemy.pos + u * 0.68) {
				return {}, false
			}
		}
	}

	Nav_Candidate :: struct {
		cost:    int,
		dist_sq: f32,
		center:  Vec2,
	}
	candidates: [8]Nav_Candidate
	count := 0
	for offset in NAV_NEIGHBORS {
		nx, ny := ex + offset[0], ey + offset[1]
		if !dungeon_in_bounds(nx, ny) do continue
		nc := nav.cost[nx][ny]
		if nc == NAV_UNREACHED || int(nc) >= cost do continue // strictly descending only
		if offset[0] != 0 && offset[1] != 0 {
			if !is_floor(d, f32(nx) + 0.5, f32(ey) + 0.5) &&
				!is_floor(d, f32(ex) + 0.5, f32(ny) + 0.5) {
				continue
			}
		}
		center := Vec2{f32(nx) + 0.5, f32(ny) + 0.5}
		to_target := center - target
		candidates[count] = {int(nc), to_target.x * to_target.x + to_target.y * to_target.y, center}
		count += 1
	}
	if count == 0 do return {}, false
	// Stable insertion sort by (cost, dist^2); neighbor order breaks ties.
	for i in 1 ..< count {
		key := candidates[i]
		j := i - 1
		for j >= 0 &&
			(candidates[j].cost > key.cost ||
					(candidates[j].cost == key.cost && candidates[j].dist_sq > key.dist_sq)) {
			candidates[j + 1] = candidates[j]
			j -= 1
		}
		candidates[j + 1] = key
	}
	chosen := candidates[0]
	best_cost := candidates[0].cost
	// Approach-probe only the cost-tied leaders; if all probe blocked, keep the
	// best-ranked one and let the stall slide grind past.
	for i in 0 ..< count {
		c := candidates[i]
		if c.cost != best_cost do break
		v := c.center - enemy.pos
		l := math.hypot(v.x, v.y)
		if l < 0.001 do continue
		probe := enemy.pos + (v / l) * 0.34
		if !blocked_for_radius(d, probe.x, probe.y, ACTOR_MOVE_COLLISION_RADIUS) {
			chosen = c
			break
		}
	}
	v := chosen.center - enemy.pos
	l := math.hypot(v.x, v.y)
	if l < 0.001 do return {}, false
	return v / l, true
}
