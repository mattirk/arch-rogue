package archrogue

// Raylib-free special-room planning data, derived furnishings, and refuge rules.
// Story-room application/rendering remains outside this foundation.

import "core:math"

MAX_SPECIAL_ROOMS :: 5
HALL_OF_UNLOST_ECHOES_NAME :: "Hall of Unlost Echoes"

Special_Room_Kind :: enum u8 {
	None,
	Shop,
	Bar,
	Garden,
	Quest,
	Hall_Of_Unlost_Echoes,
}

Special_Room :: struct {
	kind:       Special_Room_Kind,
	room_index: int,
}

ROOM_NPC_RADIUS :: f32(0.27)
ROOM_NPC_INTERACTION_HOLD_RANGE :: f32(1.45)
MAX_AMBIENT_ROOM_RESIDENTS :: 5

SOULLESS_CLANKER_INTERACT_RANGE :: f32(1.35)
STRING_INTERACT_RANGE            :: f32(1.35)

Room_Npc_Motion_State :: enum u8 {
	Waiting,
	Moving,
	Holding,
	Dancing,
}

Room_Npc_Profile_Id :: enum u8 {
	Shopkeeper,
	Bar_Dancer,
	Garden_Frog,
	Story_Guest,
	Lossless_Soul,
	Soulless_Clanker,
	String,
}

Room_Npc_Profile :: struct {
	speed:         f32,
	leash:         f32,
	dance_chance:  f32,
	rest_min:      f32,
	rest_max:      f32,
	dance_min:     f32,
	dance_max:     f32,
}

// Shared deterministic room-resident state. The seed is immutable after
// construction; each decision creates a private local RNG from that seed, the
// decision ordinal, and fixed simulation time. No Run gameplay stream is used.
Room_Npc_Motion :: struct {
	home:             Vec2,
	target:           Vec2,
	facing:           Vec2,
	seed:             u64,
	room_index:       int,
	profile:          Room_Npc_Profile_Id,
	decision_index:   int,
	phrase_index:     int, // compatibility name for deterministic decision phase
	fixed_elapsed:    f32,
	decision_elapsed: f32,
	decision_delay:   f32,
	state_elapsed:    f32,
	state_duration:   f32,
	anim_time:        f32,
	state:            Room_Npc_Motion_State,
	moving:           bool,
	holding:          bool,
	dancing:          bool,
}

// Kept as an alias for callers/tests from the first story-only implementation.
Story_Npc_Motion :: Room_Npc_Motion

Ambient_Room_Npc_Kind :: enum u8 {
	Bar_Dancer,
	Garden_Frog,
	Soulless_Clanker,
	String,
}

Ambient_Room_Npc :: struct {
	active:   bool,
	kind:     Ambient_Room_Npc_Kind,
	pos:      Vec2,
	prev_pos: Vec2,
	motion:   Room_Npc_Motion,
}

Ambient_Room_Npc_Set :: struct {
	items: [MAX_AMBIENT_ROOM_RESIDENTS]Ambient_Room_Npc,
	count: int,
}

Special_Room_Plan_Trace :: struct {
	quest_requested:      bool,
	quest_placed:         bool,
	hall_enabled:         bool,
	hall_roll_evaluated:  bool,
	hall_roll_passed:     bool,
	hall_force_requested: bool,
	hall_placed:          bool,
}

MAX_BAR_FURNISHINGS :: 8
MAX_BAR_CANDIDATES  :: 128
MAX_SHOP_GOLD_STACKS :: 12
MAX_SHOP_GOLD_CANDIDATES :: 90
SHOP_GOLD_VARIANT_COUNT :: 5
SHOP_GOLD_VARIANT_SALT :: u64(0x4A17C0DE)
SHOP_GOLD_EXTRA_SALT :: u64(0x71D6B295)

Shop_Gold_Stack :: struct {
	tile: [2]int,
	size: u8,
	variant: u8,
}

Shop_Gold_Layout :: struct {
	stacks: [MAX_SHOP_GOLD_STACKS]Shop_Gold_Stack,
	count: int,
}

shop_gold_count_for_candidates :: proc(candidate_count: int) -> int {
	if candidate_count <= 0 do return 0
	base_count := max(3,min(8,candidate_count/3))
	return min(candidate_count,max(base_count,max(5,min(12,candidate_count/2))))
}

shop_gold_size_scale :: proc(size: u8) -> f32 {
	switch size {
	case 1: return .72
	case 2: return .92
	case 3: return 1.14
	}
	return 1
}

shop_gold_draw_info :: proc(stack: Shop_Gold_Stack) -> (feet: Vec2, depth: f32, prop_index: int, scale: f32) {
	feet = {f32(stack.tile.x)+.5,f32(stack.tile.y)+.5}
	depth = f32(stack.tile.x+stack.tile.y)+.5
	prop_index = int(Prop_Key.Gold_Stack_1)+int(stack.variant)%SHOP_GOLD_VARIANT_COUNT
	scale = shop_gold_size_scale(stack.size)
	return
}

Bar_Furnishing_Kind :: enum u8 {
	Barrel,
	Table,
}

Bar_Furnishing_Layout :: struct {
	tiles:        [MAX_BAR_FURNISHINGS][2]int,
	kinds:        [MAX_BAR_FURNISHINGS]Bar_Furnishing_Kind,
	count:        int,
	barrel_count: int,
	table_count:  int,
}

MAX_HALL_FURNISHINGS :: 4

Hall_Furnishing_Kind :: enum u8 {
	Mirror,
	Chimes,
	Brazier,
	Reliquary,
}

Hall_Furnishing_Layout :: struct {
	tiles: [MAX_HALL_FURNISHINGS][2]int,
	kinds: [MAX_HALL_FURNISHINGS]Hall_Furnishing_Kind,
	count: int,
}

special_rooms :: proc(d: ^Dungeon) -> []Special_Room {
	if d == nil do return nil
	return d.special_rooms_buf[:d.special_room_count]
}

special_room_for_kind :: proc(d: ^Dungeon, kind: Special_Room_Kind) -> (room: ^Special_Room, found: bool) {
	if d == nil || kind == .None do return nil, false
	for i in 0 ..< d.special_room_count {
		if d.special_rooms_buf[i].kind == kind do return &d.special_rooms_buf[i], true
	}
	return nil, false
}

special_room_at_room_index :: proc(d: ^Dungeon, room_index: int) -> (room: ^Special_Room, found: bool) {
	if d == nil || room_index < 0 || room_index >= d.room_count do return nil, false
	for i in 0 ..< d.special_room_count {
		if d.special_rooms_buf[i].room_index == room_index do return &d.special_rooms_buf[i], true
	}
	return nil, false
}

room_contains_point :: proc(room: Room, x, y: f32) -> bool {
	tx, ty := int(math.floor(x)), int(math.floor(y))
	return room.x <= tx && tx < room.x + room.w && room.y <= ty && ty < room.y + room.h
}

// Return stable pointers into Dungeon's fixed room buffers. These are pure
// lookups: callers can populate/render special rooms without duplicating the
// room-boundary rules or allocating temporary collections.
dungeon_room_at_point :: proc(d: ^Dungeon, x, y: f32) -> (room: ^Room, room_index: int, found: bool) {
	if d == nil do return nil, -1, false
	for i in 0 ..< d.room_count {
		if room_contains_point(d.rooms_buf[i], x, y) do return &d.rooms_buf[i], i, true
	}
	return nil, -1, false
}

special_room_at_point :: proc(d: ^Dungeon, x, y: f32) -> (room: ^Special_Room, found: bool) {
	_, room_index, in_room := dungeon_room_at_point(d, x, y)
	if !in_room do return nil, false
	return special_room_at_room_index(d, room_index)
}

special_room_kind_for_room :: proc(d: ^Dungeon, room_index: int) -> Special_Room_Kind {
	room, found := special_room_at_room_index(d, room_index)
	return found ? room.kind : .None
}

room_contains_interior_tile :: proc(room: Room, x, y: int) -> bool {
	return room.x < x && x < room.x + room.w - 1 && room.y < y && y < room.y + room.h - 1
}

special_room_kind_at_point :: proc(d: ^Dungeon, x, y: f32) -> Special_Room_Kind {
	room, found := special_room_at_point(d, x, y)
	return found ? room.kind : .None
}

// Rendering uses the themed floor only inside the sealed perimeter. Door and
// wall tiles retain their own art; stairs are accepted for completeness even
// though the first/last-room exclusion keeps them out of M9 special rooms.
special_room_interior_kind :: proc(d: ^Dungeon, x, y: int) -> Special_Room_Kind {
	if d == nil || !dungeon_in_bounds(x, y) do return .None
	#partial switch d.tiles[x][y] {
	case .Floor, .Stairs:
	case:
		return .None
	}
	for special in special_rooms(d) {
		if special.room_index < 0 || special.room_index >= d.room_count do continue
		if room_contains_interior_tile(d.rooms_buf[special.room_index], x, y) do return special.kind
	}
	return .None
}

special_room_kind_name :: proc(kind: Special_Room_Kind) -> string {
	switch kind {
	case .None:                  return "None"
	case .Shop:                  return "Shop"
	case .Bar:                   return "Bar"
	case .Garden:                return "Garden"
	case .Quest:                 return "Quest"
	case .Hall_Of_Unlost_Echoes: return HALL_OF_UNLOST_ECHOES_NAME
	}
	return "Unknown"
}

special_room_is_safe :: proc(kind: Special_Room_Kind) -> bool {
	return kind == .Shop || kind == .Quest || kind == .Hall_Of_Unlost_Echoes
}

special_room_is_flavor :: proc(kind: Special_Room_Kind) -> bool {
	return kind == .Bar || kind == .Garden || kind == .Hall_Of_Unlost_Echoes
}

special_room_is_healing_refuge :: proc(kind: Special_Room_Kind) -> bool {
	return kind == .Bar || kind == .Garden
}

// The floor tile a doorway opens onto. Furniture must never claim one, or the
// door behind it becomes impassable. Shared with MX.5 shrine/cache placement.
tile_is_door_front :: proc(d: ^Dungeon, room: Room, tile: [2]int) -> bool {
	for x in room.x ..< room.x + room.w {
		if d.tiles[x][room.y] == .Closed_Door || d.tiles[x][room.y] == .Open_Door {
			if tile.x == x && tile.y == room.y+1 do return true
		}
		if d.tiles[x][room.y+room.h-1] == .Closed_Door || d.tiles[x][room.y+room.h-1] == .Open_Door {
			if tile.x == x && tile.y == room.y+room.h-2 do return true
		}
	}
	for y in room.y+1 ..< room.y + room.h-1 {
		if d.tiles[room.x][y] == .Closed_Door || d.tiles[room.x][y] == .Open_Door {
			if tile.x == room.x+1 && tile.y == y do return true
		}
		if d.tiles[room.x+room.w-1][y] == .Closed_Door || d.tiles[room.x+room.w-1][y] == .Open_Door {
			if tile.x == room.x+room.w-2 && tile.y == y do return true
		}
	}
	return false
}

hall_furnishing_ideal_tile :: proc(room: Room, kind: Hall_Furnishing_Kind) -> [2]int {
	center := room_center(room)
	switch kind {
	case .Mirror:
		return {center.x, room.y + 1}
	case .Chimes:
		return {max(room.x + 1, center.x - 2), room.y + 1}
	case .Brazier:
		return {room.x + 2, room.y + 2}
	case .Reliquary:
		return {room.x + room.w - 3, room.y + room.h / 2}
	}
	return center
}

hall_furnishing_avoids_door_front :: proc(d: ^Dungeon, room: Room, tile: [2]int) -> bool {
	if d == nil || tile_is_door_front(d, room, tile) do return false
	for y in room.y + 1 ..< room.y + room.h - 1 {
		for x in room.x + 1 ..< room.x + room.w - 1 {
			front := [2]int{x, y}
			if !tile_is_door_front(d, room, front) do continue
			// Solid hall blocks sit slightly north-west on their anchor. Keep the
			// east/south/south-east clearance used by the pygame hall as well as
			// the immediate door-front tile itself.
			east := [2]int{front.x + 1, front.y}
			south := [2]int{front.x, front.y + 1}
			south_east := [2]int{front.x + 1, front.y + 1}
			if tile == east || tile == south || tile == south_east do return false
		}
	}
	return true
}

@(private = "file")
hall_blocked_contains :: proc(blocked: [][2]int, tile: [2]int) -> bool {
	for reserved in blocked do if reserved == tile do return true
	return false
}

@(private = "file")
hall_layout_contains :: proc(layout: ^Hall_Furnishing_Layout, tile: [2]int) -> bool {
	if layout == nil do return false
	for i in 0 ..< layout.count do if layout.tiles[i] == tile do return true
	return false
}

@(private = "file")
hall_furnishing_candidate_valid :: proc(
	d: ^Dungeon,
	room: Room,
	tile: [2]int,
	blocked: [][2]int,
	layout: ^Hall_Furnishing_Layout,
) -> bool {
	if d == nil || !room_contains_interior_tile(room, tile.x, tile.y) do return false
	if !dungeon_in_bounds(tile.x, tile.y) do return false
	#partial switch d.tiles[tile.x][tile.y] {
	case .Floor, .Stairs:
	case:
		return false
	}
	if hall_blocked_contains(blocked, tile) || hall_layout_contains(layout, tile) do return false
	if solid_prop_occupies_tile(d, tile.x, tile.y) do return false
	// The Lossless Soul starts at the Hall actor anchor. Furnishings may reserve
	// nearby tiles, but must not make that live resident spawn inside collision.
	if special_room_actor_occupies_tile(d,tile.x,tile.y) do return false
	return hall_furnishing_avoids_door_front(d, room, tile)
}

@(private = "file")
hall_pick_furnishing_tile :: proc(
	d: ^Dungeon,
	room: Room,
	ideal: [2]int,
	blocked: [][2]int,
	layout: ^Hall_Furnishing_Layout,
) -> (tile: [2]int, found: bool) {
	tile = ideal
	best_distance := 0
	for y in room.y + 1 ..< room.y + room.h - 1 {
		for x in room.x + 1 ..< room.x + room.w - 1 {
			candidate := [2]int{x, y}
			if !hall_furnishing_candidate_valid(d, room, candidate, blocked, layout) do continue
			dx, dy := x - ideal.x, y - ideal.y
			distance := dx * dx + dy * dy
			if !found || distance < best_distance ||
			   (distance == best_distance && (y < tile.y || (y == tile.y && x < tile.x))) {
				tile, best_distance, found = candidate, distance, true
			}
		}
	}
	return
}

// Deterministic nearest-free fallback for callers that need to preview or
// reconcile one Hall block. Ties are resolved by (distance, y, x), matching the
// pygame layout. If every interior tile is blocked, ideal is returned with
// found=false so callers can decline the impossible placement safely.
hall_furnishing_fallback_tile :: proc(
	d: ^Dungeon,
	room: Room,
	ideal: [2]int,
	blocked: [][2]int = nil,
) -> (tile: [2]int, found: bool) {
	return hall_pick_furnishing_tile(d, room, ideal, blocked, nil)
}

plan_hall_furnishings :: proc(d: ^Dungeon, blocked: [][2]int = nil) {
	if d == nil do return
	d.hall_furnishings = {}
	special, found := special_room_for_kind(d, .Hall_Of_Unlost_Echoes)
	if !found || special.room_index < 0 || special.room_index >= d.room_count do return
	room := d.rooms_buf[special.room_index]
	kinds := [MAX_HALL_FURNISHINGS]Hall_Furnishing_Kind{
		.Mirror, .Chimes, .Brazier, .Reliquary,
	}
	for kind in kinds {
		ideal := hall_furnishing_ideal_tile(room, kind)
		tile, available := hall_pick_furnishing_tile(d, room, ideal, blocked, &d.hall_furnishings)
		if !available do continue
		i := d.hall_furnishings.count
		d.hall_furnishings.tiles[i] = tile
		d.hall_furnishings.kinds[i] = kind
		d.hall_furnishings.count += 1
	}
}

hall_furnishing_layout :: proc(d: ^Dungeon) -> Hall_Furnishing_Layout {
	if d == nil do return {}
	return d.hall_furnishings
}

hall_furnishing_occupies_tile :: proc(d: ^Dungeon, x, y: int) -> bool {
	if d == nil do return false
	tile := [2]int{x, y}
	for i in 0 ..< d.hall_furnishings.count {
		if d.hall_furnishings.tiles[i] == tile do return true
	}
	return false
}

@(private = "file")
bar_shuffle_tiles :: proc(tiles: [][2]int, rng: ^Pcg32) {
	if len(tiles)<2 do return
	for i:=len(tiles)-1;i>0;i-=1 {
		j:=rng_below(rng,i+1)
		tiles[i],tiles[j]=tiles[j],tiles[i]
	}
}

@(private = "file")
bar_layout_contains_near :: proc(layout: ^Bar_Furnishing_Layout, tile: [2]int) -> bool {
	for i in 0..<layout.count {
		placed:=layout.tiles[i]
		if max(abs(tile.x-placed.x),abs(tile.y-placed.y))<2 do return true
	}
	return false
}

@(private = "file")
bar_pick_furnishings :: proc(
	layout: ^Bar_Furnishing_Layout,
	pool: [][2]int,
	desired: int,
	kind: Bar_Furnishing_Kind,
) -> int {
	added:=0
	for tile in pool {
		if layout.count>=MAX_BAR_FURNISHINGS||added>=desired do break
		if bar_layout_contains_near(layout,tile) do continue
		layout.tiles[layout.count]=tile
		layout.kinds[layout.count]=kind
		layout.count+=1
		added+=1
	}
	return added
}

// Cache Pygame's request for 2-4 barrels plus 2-4 standing tables once when
// the floor is generated. Its greedy spacing pass may place fewer in a cramped
// room. Collision and population query this fixed layout in hot loops, so no
// candidate scan or RNG work reaches a simulation frame.
plan_shop_gold :: proc(d: ^Dungeon) {
	if d == nil do return
	d.shop_gold = {}
	special,found := special_room_for_kind(d,.Shop)
	if !found || special.room_index < 0 || special.room_index >= d.room_count do return
	room := d.rooms_buf[special.room_index]
	keeper := room_center(room)
	sign := [2]int{keeper.x+1,keeper.y}
	candidates: [MAX_SHOP_GOLD_CANDIDATES][2]int
	candidate_count := 0
	for x in room.x+1 ..< room.x+room.w-1 {
		for y in room.y+1 ..< room.y+room.h-1 {
			tile := [2]int{x,y}
			if tile == keeper || tile == sign || !dungeon_in_bounds(x,y) do continue
			kind := d.tiles[x][y]
			if kind != .Floor && kind != .Stairs do continue
			if candidate_count < len(candidates) {
				candidates[candidate_count] = tile
				candidate_count += 1
			}
		}
	}
	if candidate_count == 0 do return
	base_count := max(3,min(8,candidate_count/3))
	target_count := shop_gold_count_for_candidates(candidate_count)
	seed := u64(room.x*73856093) ~ u64(room.y*19349663) ~ u64(room.w*83492791) ~ u64(room.h*22345761)
	base_rng := rng_make(splitmix64(seed),stream=9)
	stride := max(1,candidate_count/base_count)
	start := rng_below(&base_rng,stride)
	chosen: [MAX_SHOP_GOLD_CANDIDATES]bool
	for i:=start; i<candidate_count && d.shop_gold.count<base_count; i+=stride {
		stack := &d.shop_gold.stacks[d.shop_gold.count]
		stack.tile = candidates[i]
		chosen[i] = true
		d.shop_gold.count += 1
	}
	// Keep the evenly spaced prefix, then deterministically fill the denser MX.7
	// target from unclaimed room tiles without touching gameplay RNG.
	extras: [MAX_SHOP_GOLD_CANDIDATES]int
	extra_count := 0
	for i in 0..<candidate_count do if !chosen[i] {
		extras[extra_count] = i
		extra_count += 1
	}
	extra_rng := rng_make(splitmix64(seed~SHOP_GOLD_EXTRA_SALT),stream=9)
	for i:=extra_count-1; i>0; i-=1 {
		j := rng_below(&extra_rng,i+1)
		extras[i],extras[j] = extras[j],extras[i]
	}
	for i in 0..<extra_count {
		if d.shop_gold.count >= target_count || d.shop_gold.count >= MAX_SHOP_GOLD_STACKS do break
		d.shop_gold.stacks[d.shop_gold.count].tile = candidates[extras[i]]
		d.shop_gold.count += 1
	}
	sizes := [8]u8{2,1,3,2,1,3,2,1}
	for i:=len(sizes)-1; i>0; i-=1 {
		j := rng_below(&base_rng,i+1)
		sizes[i],sizes[j] = sizes[j],sizes[i]
	}
	variant_rng := rng_make(splitmix64(seed~SHOP_GOLD_VARIANT_SALT),stream=9)
	variants := [SHOP_GOLD_VARIANT_COUNT]u8{0,1,2,3,4}
	for i:=len(variants)-1; i>0; i-=1 {
		j := rng_below(&variant_rng,i+1)
		variants[i],variants[j] = variants[j],variants[i]
	}
	for i in 0..<d.shop_gold.count {
		d.shop_gold.stacks[i].size = sizes[i%len(sizes)]
		d.shop_gold.stacks[i].variant = variants[i%len(variants)]
	}
}

shop_gold_occupies_tile :: proc(d: ^Dungeon, x,y: int) -> bool {
	if d == nil do return false
	for i in 0..<d.shop_gold.count {
		tile := d.shop_gold.stacks[i].tile
		if tile.x == x && tile.y == y do return true
	}
	return false
}

shop_sign_occupies_tile :: proc(d: ^Dungeon, x,y: int) -> bool {
	if d == nil do return false
	special,found := special_room_for_kind(d,.Shop)
	if !found || special.room_index < 0 || special.room_index >= d.room_count do return false
	center := room_center(d.rooms_buf[special.room_index])
	return x == center.x+1 && y == center.y
}

plan_bar_furnishings :: proc(d: ^Dungeon) {
	if d==nil do return
	d.bar_furnishings={}
	special,found:=special_room_for_kind(d,.Bar)
	if !found do return
	room:=d.rooms_buf[special.room_index]
	actor_layout:=special_room_actor_layout(d,.Bar)
	wall_pool,table_pool,all_pool:[MAX_BAR_CANDIDATES][2]int
	wall_count,table_count,all_count:=0,0,0
	for y in room.y+1..<room.y+room.h-1 {
		for x in room.x+1..<room.x+room.w-1 {
			tile:=[2]int{x,y}
			// Both resident anchors stay clear, and doorway fronts remain an open aisle.
			actor_tile:=false
			for i in 0..<actor_layout.count do if tile==actor_layout.tiles[i] {actor_tile=true;break}
			if actor_tile||tile_is_door_front(d,room,tile) do continue
			if all_count<MAX_BAR_CANDIDATES {
				all_pool[all_count]=tile
				all_count+=1
			}
			wall_adjacent:=x==room.x+1||x==room.x+room.w-2||y==room.y+1||y==room.y+room.h-2
			if wall_adjacent {
				if wall_count<MAX_BAR_CANDIDATES {wall_pool[wall_count]=tile;wall_count+=1}
			} else if table_count<MAX_BAR_CANDIDATES {
				table_pool[table_count]=tile
				table_count+=1
			}
		}
	}
	seed:=u64(room.x)|u64(room.y)<<8|u64(room.w)<<16|u64(room.h)<<24|u64(special.room_index)<<32
	rng:=rng_make(splitmix64(seed~0xBA55),stream=8)
	bar_shuffle_tiles(wall_pool[:wall_count],&rng)
	bar_shuffle_tiles(table_pool[:table_count],&rng)
	bar_shuffle_tiles(all_pool[:all_count],&rng)
	desired:=2+min(2,max(0,(room.w-2)*(room.h-2))/28)
	layout:=&d.bar_furnishings
	barrels:=bar_pick_furnishings(layout,wall_pool[:wall_count],desired,.Barrel)
	if barrels<desired do barrels+=bar_pick_furnishings(layout,all_pool[:all_count],desired-barrels,.Barrel)
	layout.barrel_count=barrels
	tables:=bar_pick_furnishings(layout,table_pool[:table_count],desired,.Table)
	if tables<desired do tables+=bar_pick_furnishings(layout,all_pool[:all_count],desired-tables,.Table)
	layout.table_count=tables
	// Entry zero is the deterministic tapped barrel used by interaction code.
	if layout.barrel_count>1 {
		tapped:=rng_below(&rng,layout.barrel_count)
		layout.tiles[0],layout.tiles[tapped]=layout.tiles[tapped],layout.tiles[0]
		layout.kinds[0],layout.kinds[tapped]=layout.kinds[tapped],layout.kinds[0]
	}
}

bar_furnishing_layout :: proc(d: ^Dungeon) -> Bar_Furnishing_Layout {
	if d==nil do return {}
	return d.bar_furnishings
}

bar_furnishing_occupies_tile :: proc(d: ^Dungeon, x,y: int) -> bool {
	layout := bar_furnishing_layout(d)
	for i in 0..<layout.count {
		if layout.tiles[i].x == x && layout.tiles[i].y == y do return true
	}
	return false
}

MAX_SPECIAL_ROOM_ACTORS :: 2

Special_Room_Actor_Layout :: struct {
	tiles: [MAX_SPECIAL_ROOM_ACTORS][2]int,
	count: int,
}

// Fixed actor anchors seed live resident positions and reserve initial
// population placement. They are deliberately not movement/nav collision:
// once an actor wanders, its old anchor must not remain as a ghost obstacle.
special_room_actor_layout :: proc(d: ^Dungeon, kind: Special_Room_Kind) -> (layout: Special_Room_Actor_Layout) {
	if d==nil do return
	special,found:=special_room_for_kind(d,kind)
	if !found do return
	room:=d.rooms_buf[special.room_index]
	center:=room_center(room)
	switch kind {
	case .Shop,.Quest:
		layout.tiles[0]=center
		layout.count=1
	case .Bar:
		// The dancer keeps the established center anchor. String plays far enough
		// west that both residents have distinct interaction radii.
		layout.tiles[0]=center
		string_anchor:=[2]int{max(room.x+1,center.x-2),center.y}
		if string_anchor==center do string_anchor={min(room.x+room.w-2,center.x+1),center.y}
		layout.tiles[1]=string_anchor
		layout.count=layout.tiles[0]==layout.tiles[1]?1:2
	case .Hall_Of_Unlost_Echoes:
		// The Lossless Soul keeps the center anchor. The Clanker stands far
		// enough west that each resident owns a distinct interaction radius.
		layout.tiles[0]=center
		layout.tiles[1]={max(room.x+1,center.x-2),center.y}
		layout.count=layout.tiles[0]==layout.tiles[1]?1:2
	case .Garden:
		layout.tiles[0]={max(room.x+1,center.x-1),center.y}
		layout.tiles[1]={min(room.x+room.w-2,center.x+1),center.y}
		layout.count=layout.tiles[0]==layout.tiles[1]?1:2
	case .None:
	}
	return
}

special_room_actor_occupies_tile :: proc(d: ^Dungeon, x,y: int) -> bool {
	for kind in ([5]Special_Room_Kind{.Shop,.Bar,.Garden,.Quest,.Hall_Of_Unlost_Echoes}) {
		layout:=special_room_actor_layout(d,kind)
		for i in 0..<layout.count {
			if layout.tiles[i].x==x&&layout.tiles[i].y==y do return true
		}
	}
	return false
}

// Physical room geometry only. Live actor positions are presentation/
// interaction state rather than static nav blockers.
special_room_reserved_occupies_tile :: proc(d: ^Dungeon, x,y: int) -> bool {
	return bar_furnishing_occupies_tile(d,x,y)||hall_furnishing_occupies_tile(d,x,y)||
		solid_prop_occupies_tile(d,x,y)
}

// Actor homes and cosmetic Shop dressing still reserve the generation-time
// enemy/loot pass, but remain walk-through after the floor has been populated.
special_room_placement_reserved_occupies_tile :: proc(d: ^Dungeon, x,y: int) -> bool {
	return special_room_reserved_occupies_tile(d,x,y) || special_room_actor_occupies_tile(d,x,y) ||
		shop_sign_occupies_tile(d,x,y) || shop_gold_occupies_tile(d,x,y)
}

room_npc_profile :: proc(id: Room_Npc_Profile_Id) -> Room_Npc_Profile {
	switch id {
	case .Shopkeeper:
		return {speed=.38,leash=2.35,dance_chance=.10,rest_min=1.15,rest_max=2.25,dance_min=1.4,dance_max=2.4}
	case .Bar_Dancer:
		return {speed=.72,leash=3.6,dance_chance=.64,rest_min=.35,rest_max=.9,dance_min=1.55,dance_max=3.0}
	case .Garden_Frog:
		return {speed=.48,leash=2.75,dance_chance=.34,rest_min=.65,rest_max=1.65,dance_min=.9,dance_max=1.8}
	case .Story_Guest:
		return {speed=.76,leash=3.4,dance_chance=.14,rest_min=.8,rest_max=1.75,dance_min=1.15,dance_max=2.05}
	case .Lossless_Soul:
		return {speed=.64,leash=3.35,dance_chance=.28,rest_min=.55,rest_max=1.35,dance_min=1.25,dance_max=2.35}
	case .Soulless_Clanker:
		return {speed=.36,leash=1.15,dance_chance=0,rest_min=1.4,rest_max=2.8,dance_min=.8,dance_max=1.1}
	case .String:
		return {speed=.42,leash=1.4,dance_chance=.88,rest_min=.25,rest_max=.65,dance_min=1.8,dance_max=3.4}
	}
	return {}
}

room_npc_motion_make :: proc(pos: Vec2, room_index: int, seed: u64, profile: Room_Npc_Profile_Id) -> Room_Npc_Motion {
	return {
		home=pos,target=pos,facing={1,1},seed=seed,room_index=room_index,profile=profile,
		phrase_index=-1,decision_delay=.18,
	}
}

@(private = "file")
room_npc_set_state :: proc(motion: ^Room_Npc_Motion, state: Room_Npc_Motion_State) {
	if motion == nil do return
	changed := motion.state != state
	motion.state = state
	motion.moving = state == .Moving
	motion.holding = state == .Holding
	motion.dancing = state == .Dancing
	if changed {
		motion.state_elapsed = 0
		motion.state_duration = 0
		motion.anim_time = 0
	}
}

room_npc_motion_wait :: proc(motion: ^Room_Npc_Motion, pos: Vec2) {
	if motion == nil do return
	motion.target = pos
	room_npc_set_state(motion,.Waiting)
}

room_npc_motion_hold :: proc(motion: ^Room_Npc_Motion, pos, focus: Vec2) {
	if motion == nil do return
	motion.target = pos
	motion.decision_elapsed = 0
	motion.decision_delay = .18
	room_npc_set_state(motion,.Holding)
	room_npc_face(pos,focus,&motion.facing)
}

room_npc_motion_set_moving :: proc(motion: ^Room_Npc_Motion, moving: bool) {
	if motion == nil do return
	if moving do room_npc_set_state(motion,.Moving)
	else do room_npc_set_state(motion,.Waiting)
}

room_npc_motion_gesture :: proc(motion: ^Room_Npc_Motion, pos: Vec2, duration: f32) {
	if motion == nil do return
	motion.target = pos
	room_npc_set_state(motion,.Dancing)
	motion.state_duration = max(duration,f32(.1))
}

room_npc_face_toward :: proc(motion: ^Room_Npc_Motion, pos, focus: Vec2) {
	if motion == nil do return
	room_npc_face(pos,focus,&motion.facing)
}

room_npc_motion_cancel_dance :: proc(motion: ^Room_Npc_Motion, pos: Vec2) {
	if motion == nil do return
	if motion.dancing || motion.state == .Dancing do room_npc_motion_wait(motion,pos)
	motion.dancing = false
}

room_npc_interpolated_position :: proc(prev_pos, pos: Vec2, alpha: f32) -> Vec2 {
	return prev_pos+(pos-prev_pos)*clamp(alpha,f32(0),f32(1))
}

@(private = "file")
room_npc_face :: proc(origin, target: Vec2, facing: ^Vec2) {
	delta := target-origin
	distance := math.hypot(delta.x,delta.y)
	if distance > .001 do facing^ = delta/distance
}

@(private = "file")
room_npc_decision_rng :: proc(motion: ^Room_Npc_Motion) -> Pcg32 {
	fixed_tick := u64(max(0,int(math.floor(motion.fixed_elapsed*60+.5))))
	salt := u64(motion.decision_index+1)*0x9E3779B97F4A7C15 ~ fixed_tick*0xD1B54A32D192ED03
	return rng_make(derive_seed(motion.seed,salt),stream=19)
}

@(private = "file")
room_npc_waypoint :: proc(run: ^Run, motion: ^Room_Npc_Motion, current: Vec2, rng: ^Pcg32) -> Vec2 {
	if run == nil || motion == nil || motion.room_index < 0 || motion.room_index >= run.dungeon.room_count do return current
	room := run.dungeon.rooms_buf[motion.room_index]
	profile := room_npc_profile(motion.profile)
	candidates: [160]Vec2
	count := 0
	for y in room.y+1 ..< room.y+room.h-1 {
		for x in room.x+1 ..< room.x+room.w-1 {
			candidate := Vec2{f32(x)+.5,f32(y)+.5}
			if tile_is_door_front(&run.dungeon,room,{x,y}) do continue
			if math.hypot(candidate.x-motion.home.x,candidate.y-motion.home.y) > profile.leash do continue
			if math.hypot(candidate.x-current.x,candidate.y-current.y) < .55 do continue
			if math.hypot(candidate.x-run.player.pos.x,candidate.y-run.player.pos.y) < .7 do continue
			if blocked_for_radius(&run.dungeon,candidate.x,candidate.y,ROOM_NPC_RADIUS) do continue
			if count < len(candidates) {
				candidates[count] = candidate
				count += 1
			}
		}
	}
	if count == 0 do return current
	return candidates[rng_below(rng,count)]
}

@(private = "file")
room_npc_choose_action :: proc(run: ^Run, pos: ^Vec2, motion: ^Room_Npc_Motion) {
	profile := room_npc_profile(motion.profile)
	rng := room_npc_decision_rng(motion)
	motion.decision_index += 1
	motion.phrase_index = motion.decision_index-1
	motion.decision_elapsed = 0
	motion.decision_delay = profile.rest_min+(profile.rest_max-profile.rest_min)*rng_f32(&rng)
	if rng_chance(&rng,profile.dance_chance) {
		motion.target = pos^
		room_npc_set_state(motion,.Dancing)
		motion.state_duration = profile.dance_min+(profile.dance_max-profile.dance_min)*rng_f32(&rng)
		return
	}
	motion.target = room_npc_waypoint(run,motion,pos^,&rng)
	if math.hypot(motion.target.x-pos.x,motion.target.y-pos.y) > .05 {
		room_npc_set_state(motion,.Moving)
	} else {
		room_npc_set_state(motion,.Waiting)
	}
}

@(private = "file")
room_npc_step_toward :: proc(run: ^Run, pos: ^Vec2, motion: ^Room_Npc_Motion, target: Vec2, speed, dt: f32) -> bool {
	if run == nil || pos == nil || motion == nil || dt <= 0 || motion.room_index < 0 || motion.room_index >= run.dungeon.room_count do return false
	room := run.dungeon.rooms_buf[motion.room_index]
	delta := target-pos^
	distance := math.hypot(delta.x,delta.y)
	if distance <= .05 do return false
	direction := delta/distance
	motion.facing = direction
	step := min(distance,max(f32(0),speed)*dt)
	wanted := pos^+direction*step
	min_x := f32(room.x)+1+ROOM_NPC_RADIUS
	max_x := f32(room.x+room.w)-1-ROOM_NPC_RADIUS
	min_y := f32(room.y)+1+ROOM_NPC_RADIUS
	max_y := f32(room.y+room.h)-1-ROOM_NPC_RADIUS
	wanted.x = clamp(wanted.x,min_x,max_x)
	wanted.y = clamp(wanted.y,min_y,max_y)
	before := pos^
	if !blocked_for_radius(&run.dungeon,wanted.x,wanted.y,ROOM_NPC_RADIUS) {
		pos^ = wanted
	} else {
		x_only := Vec2{wanted.x,pos.y}
		if min_x <= x_only.x && x_only.x <= max_x && !blocked_for_radius(&run.dungeon,x_only.x,x_only.y,ROOM_NPC_RADIUS) do pos.x = x_only.x
		y_only := Vec2{pos.x,wanted.y}
		if min_y <= y_only.y && y_only.y <= max_y && !blocked_for_radius(&run.dungeon,y_only.x,y_only.y,ROOM_NPC_RADIUS) do pos.y = y_only.y
	}
	return math.hypot(pos.x-before.x,pos.y-before.y) > .0001
}

// Fixed-step deterministic wandering. Interaction holds and hostile-room pauses
// interrupt both locomotion and dance, then schedule a fresh private decision.
room_npc_motion_tick :: proc(
	run: ^Run,
	pos: ^Vec2,
	motion: ^Room_Npc_Motion,
	interaction_hold, paused: bool,
	elapsed, dt: f32,
) {
	if run == nil || pos == nil || motion == nil || dt <= 0 do return
	motion.fixed_elapsed = max(motion.fixed_elapsed+dt,elapsed)
	if motion.room_index < 0 || motion.room_index >= run.dungeon.room_count {
		room_npc_motion_wait(motion,pos^)
		return
	}
	if paused {
		motion.target = pos^
		motion.decision_elapsed = 0
		motion.decision_delay = .25
		if interaction_hold {
			room_npc_set_state(motion,.Holding)
			room_npc_face(pos^,run.player.pos,&motion.facing)
		} else {
			room_npc_set_state(motion,.Waiting)
		}
		return
	}
	if interaction_hold {
		room_npc_motion_hold(motion,pos^,run.player.pos)
		return
	}
	if motion.state == .Holding {
		room_npc_set_state(motion,.Waiting)
		motion.decision_elapsed = 0
	}
	if motion.state == .Dancing {
		motion.state_elapsed += dt
		motion.anim_time += dt
		if motion.state_elapsed >= motion.state_duration {
			room_npc_set_state(motion,.Waiting)
			motion.decision_elapsed = 0
		}
		return
	}
	if motion.state != .Moving && math.hypot(motion.target.x-pos.x,motion.target.y-pos.y) > .05 {
		room_npc_set_state(motion,.Moving)
	}
	if motion.state == .Moving {
		profile := room_npc_profile(motion.profile)
		moved := room_npc_step_toward(run,pos,motion,motion.target,profile.speed,dt)
		if moved do motion.anim_time += dt
		if !moved || math.hypot(motion.target.x-pos.x,motion.target.y-pos.y) <= .05 {
			motion.target = pos^
			room_npc_set_state(motion,.Waiting)
			motion.decision_elapsed = 0
		}
		return
	}
	motion.decision_elapsed += dt
	if motion.decision_elapsed >= motion.decision_delay do room_npc_choose_action(run,pos,motion)
}

// Combat allies may return to their room home without re-entering ambient dance.
room_npc_motion_tick_toward :: proc(run: ^Run, pos: ^Vec2, motion: ^Room_Npc_Motion, target: Vec2, speed, elapsed, dt: f32) {
	if run == nil || pos == nil || motion == nil || dt <= 0 do return
	motion.fixed_elapsed = max(motion.fixed_elapsed+dt,elapsed)
	motion.dancing = false
	motion.target = target
	if math.hypot(target.x-pos.x,target.y-pos.y) <= .05 {
		room_npc_motion_wait(motion,pos^)
		return
	}
	room_npc_set_state(motion,.Moving)
	if room_npc_step_toward(run,pos,motion,target,speed,dt) {
		motion.anim_time += dt
	} else {
		room_npc_motion_wait(motion,pos^)
	}
}

room_has_living_hostile :: proc(run: ^Run, room_index: int) -> bool {
	if run == nil || room_index < 0 || room_index >= run.dungeon.room_count do return false
	room := run.dungeon.rooms_buf[room_index]
	for &enemy in run.enemies {
		if enemy.hp > 0 && room_contains_point(room,enemy.pos.x,enemy.pos.y) do return true
	}
	return false
}

room_npc_initialize_ambient_residents :: proc(run: ^Run) {
	if run == nil do return
	run.ambient_residents = {}
	kinds := [3]Special_Room_Kind{.Bar,.Garden,.Hall_Of_Unlost_Echoes}
	for special_kind in kinds {
		special, found := special_room_for_kind(&run.dungeon,special_kind)
		if !found || special.room_index < 0 || special.room_index >= run.dungeon.room_count do continue
		layout := special_room_actor_layout(&run.dungeon,special_kind)
		if special_kind == .Hall_Of_Unlost_Echoes && living_soulless_clanker(run) != nil do continue
		start := special_kind == .Hall_Of_Unlost_Echoes ? 1 : 0
		for i in start..<layout.count {
			kind: Ambient_Room_Npc_Kind
			profile: Room_Npc_Profile_Id
			switch special_kind {
			case .Bar:
				kind = i == 0 ? .Bar_Dancer : .String
				profile = i == 0 ? .Bar_Dancer : .String
				if kind == .String && living_string(run) != nil do continue
			case .Garden:
				kind,profile = .Garden_Frog,.Garden_Frog
			case .Hall_Of_Unlost_Echoes:
				kind,profile = .Soulless_Clanker,.Soulless_Clanker
			case .None,.Shop,.Quest:
				continue
			}
			if run.ambient_residents.count >= MAX_AMBIENT_ROOM_RESIDENTS do return
			tile := layout.tiles[i]
			pos := Vec2{f32(tile.x)+.5,f32(tile.y)+.5}
			salt := u64(run.depth)<<48 ~ u64(special.room_index+1)<<24 ~ u64(int(special_kind)+1)<<16 ~ u64(i+1)*0x9E37
			seed := derive_seed(run.seed,salt)
			index := run.ambient_residents.count
			run.ambient_residents.items[index] = {
				active=true,kind=kind,pos=pos,prev_pos=pos,
				motion=room_npc_motion_make(pos,special.room_index,seed,profile),
			}
			run.ambient_residents.count += 1
		}
	}
}

room_npc_snapshot_live_positions :: proc(run: ^Run) {
	if run == nil do return
	if run.has_shopkeeper do run.shopkeeper.prev_pos = run.shopkeeper.pos
	for i in 0..<run.ambient_residents.count {
		resident := &run.ambient_residents.items[i]
		if resident.active do resident.prev_pos = resident.pos
	}
}

room_npc_tick_live :: proc(run: ^Run, elapsed, dt: f32) {
	if run == nil do return
	if run.has_shopkeeper {
		keeper := &run.shopkeeper
		sign := shop_sign_position(keeper)
		hold := math.hypot(keeper.pos.x-run.player.pos.x,keeper.pos.y-run.player.pos.y) <= ROOM_NPC_INTERACTION_HOLD_RANGE ||
			math.hypot(sign.x-run.player.pos.x,sign.y-run.player.pos.y) < 1.35
		room_npc_motion_tick(run,&keeper.pos,&keeper.motion,hold,false,elapsed,dt)
	}
	for i in 0..<run.ambient_residents.count {
		resident := &run.ambient_residents.items[i]
		if !resident.active do continue
		hold := math.hypot(resident.pos.x-run.player.pos.x,resident.pos.y-run.player.pos.y) <= ROOM_NPC_INTERACTION_HOLD_RANGE &&
			line_of_sight(&run.dungeon,run.player.pos.x,run.player.pos.y,resident.pos.x,resident.pos.y)
		// An explicit interaction gesture must finish even while the player
		// remains in hold range; ordinary ambient gestures still yield to facing.
		if resident.kind == .Soulless_Clanker && resident.motion.dancing do hold = false
		paused := room_has_living_hostile(run,resident.motion.room_index)
		room_npc_motion_tick(run,&resident.pos,&resident.motion,hold,paused,elapsed,dt)
	}
}

// --- Solid interactable props (MX.5) ---------------------------------------

// Shrines and sealed caches are room furniture: they own their whole tile, so
// actors walk around them and population never stacks anything on top. The
// registry lives on the Dungeon because collision (blocked_for_radius), the
// enemy route field, and spawn placement all query reserved tiles from there.
// Headroom for a shrine plus a cache in every room of the largest floor.
MAX_SOLID_PROPS :: 32

Solid_Prop_Layout :: struct {
	tiles: [MAX_SOLID_PROPS][2]int,
	count: int,
}

solid_prop_occupies_tile :: proc(d: ^Dungeon, x,y: int) -> bool {
	if d == nil do return false
	for i in 0 ..< d.solid_props.count {
		if d.solid_props.tiles[i].x == x && d.solid_props.tiles[i].y == y do return true
	}
	return false
}

solid_prop_add :: proc(d: ^Dungeon, tile: [2]int) -> bool {
	if d == nil || d.solid_props.count >= MAX_SOLID_PROPS do return false
	if solid_prop_occupies_tile(d, tile.x, tile.y) do return false
	d.solid_props.tiles[d.solid_props.count] = tile
	d.solid_props.count += 1
	return true
}

// An opened cache stops being drawn, so it must stop blocking in the same
// breath; shrines keep their tile whether or not they have been used.
solid_prop_remove :: proc(d: ^Dungeon, tile: [2]int) {
	if d == nil do return
	for i in 0 ..< d.solid_props.count {
		if d.solid_props.tiles[i] != tile do continue
		d.solid_props.tiles[i] = d.solid_props.tiles[d.solid_props.count-1]
		d.solid_props.count -= 1
		return
	}
}

@(private = "file")
bar_sconce_wall_coordinate :: proc(
	d: ^Dungeon,
	center, low, high, fixed: int,
	north_wall: bool,
) -> (coordinate: int, found: bool) {
	max_distance := max(center-low, high-center)
	for distance in 0 ..= max_distance {
		for side in ([2]int{1,-1}) {
			candidate := center + side*distance
			if candidate < low || candidate > high do continue
			x, y := fixed, candidate
			if north_wall do x, y = candidate, fixed
			// Door art owns the whole wall prism. Requiring a real wall here also
			// protects against any future pass-through opening kind, not only the
			// current open/closed door pair.
			if d.tiles[x][y] == .Wall do return candidate, true
		}
	}
	return
}

bar_sconce_positions :: proc(d: ^Dungeon) -> (positions: [2]Vec2, found: bool) {
	if d==nil do return
	special,has_bar:=special_room_for_kind(d,.Bar)
	if !has_bar do return
	room:=d.rooms_buf[special.room_index]
	center:=room_center(room)
	north_x,north_found:=bar_sconce_wall_coordinate(
		d,center.x,room.x+1,room.x+room.w-2,room.y,true,
	)
	west_y,west_found:=bar_sconce_wall_coordinate(
		d,center.y,room.y+1,room.y+room.h-2,room.x,false,
	)
	if !north_found || !west_found do return
	// Pull each mount off the block's center seam and onto its camera-visible
	// face. The opposing half-tile components move 16 world pixels sideways;
	// subtracting an eighth tile from both axes then lifts it 4 world pixels
	// toward the top of the face without changing that horizontal placement.
	positions[0]={f32(north_x)+.125,f32(room.y)+.625}
	positions[1]={f32(room.x)+.625,f32(west_y)+.125}
	return positions,true
}

// --- Bar / garden refuge behavior -----------------------------------------

REFUGE_HEAL_TICK_SECONDS :: 5.0
BAR_STAMINA_SAP_PER_SECOND :: 130.0
BAR_TAP_DRINK_RANGE :: 1.35
BAR_TAP_DRINK_HEAL :: 5
BAR_TAP_DRINK_STAMINA :: 10

Refuge_State :: struct {
	heal_accumulator: f32,
	bar_toasted:      bool,
}

Refuge_Tick_Result :: struct {
	healed:          int,
	stamina_sapped: f32,
}

// Called after ordinary stamina/mana recovery, matching pygame's update order.
// A fixed 60 Hz caller crosses at most one five-second threshold per call.
refuge_tick :: proc(
	kind: Special_Room_Kind,
	state: ^Refuge_State,
	player: ^Player,
	dt: f32,
) -> (result: Refuge_Tick_Result) {
	if state == nil || player == nil || player.hp <= 0 || dt <= 0 do return result

	if kind == .Bar && !state.bar_toasted {
		before := player.stamina
		player.stamina = max(0, player.stamina - BAR_STAMINA_SAP_PER_SECOND * dt)
		result.stamina_sapped = before - player.stamina
	}
	if !special_room_is_healing_refuge(kind) || player.hp >= player.max_hp {
		state.heal_accumulator = 0
		return result
	}

	state.heal_accumulator += dt
	if state.heal_accumulator < REFUGE_HEAL_TICK_SECONDS do return result
	state.heal_accumulator -= REFUGE_HEAL_TICK_SECONDS
	heal := kind == .Garden ? max(2, player.max_hp / 25 + 2) : max(1, player.max_hp / 50 + 1)
	result.healed = min(player.max_hp - player.hp, heal)
	player.hp += result.healed
	return result
}

bar_drink :: proc(state: ^Refuge_State, player: ^Player) -> bool {
	if state == nil || player == nil || state.bar_toasted || player.hp <= 0 do return false
	state.bar_toasted = true
	player.hp = min(player.max_hp, player.hp + BAR_TAP_DRINK_HEAL)
	player.stamina = min(f32(player.max_stamina), player.stamina + BAR_TAP_DRINK_STAMINA)
	return true
}

// MX.4 run-level toast: the per-floor Refuge_State gates one free ale per
// bar, while the Run ledger feeds the pilgrimage and the depth-10 dancer
// summon (interactions.py drink_from_bar_barrel).
run_toast_bar :: proc(run: ^Run) -> bool {
	if run == nil || !bar_drink(&run.refuge, &run.player) do return false
	run.bars_toasted += 1
	if run.depth >= DUNGEON_DEPTH do _ = maybe_summon_bar_dancer(run)
	return true
}

barrel_in_drink_range :: proc(player_pos: Vec2, barrel_tile: [2]int) -> bool {
	dx := player_pos.x - (f32(barrel_tile.x) + 0.5)
	dy := player_pos.y - (f32(barrel_tile.y) + 0.5)
	return math.hypot(dx, dy) < BAR_TAP_DRINK_RANGE
}
