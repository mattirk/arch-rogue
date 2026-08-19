package archrogue_tests

// MX.7 — world polish policy remains display-free: semantic minimap discovery,
// edge guidance geometry, and deterministic cosmetic Shop dressing.

import "core:math"
import "core:testing"
import ar "../src"

MX7_EPS :: f32(1e-4)

@(private = "file")
mx7_near :: proc(a,b: f32) -> bool {
	return abs(a-b) <= MX7_EPS
}

@(private = "file")
mx7_marker_index :: proc(markers: ar.Minimap_Marker_List, kind: ar.Minimap_Marker_Kind) -> int {
	for i in 0..<markers.count do if markers.items[i].kind == kind do return i
	return -1
}

@(private = "file")
mx7_marker_run :: proc(dark := false) -> (run: ar.Run) {
	run.dark_floor = dark
	run.dungeon.room_count = 3
	run.dungeon.rooms_buf[0] = {2,2,6,6}
	run.dungeon.rooms_buf[1] = {10,12,8,8}
	run.dungeon.rooms_buf[2] = {24,18,7,7}
	run.dungeon.special_room_count = 2
	run.dungeon.special_rooms_buf[0] = {.Bar,1}
	run.dungeon.special_rooms_buf[1] = {.Garden,2}
	run.dungeon.stairs = {28,22}
	return
}

@(test)
mx7_normal_minimap_markers_are_discovery_gated_and_persistent :: proc(t: ^testing.T) {
	run := mx7_marker_run()
	testing.expect(t,ar.minimap_markers(&run).count == 0,"undiscovered normal floor leaked semantic markers")

	// Any room-footprint tile discovers Bar/Garden; stairs uses its own tile.
	run.explored[10][12] = true
	run.explored[24][18] = true
	run.explored[run.dungeon.stairs.x][run.dungeon.stairs.y] = true
	markers := ar.minimap_markers(&run)
	testing.expect(t,markers.count == 3,"normal floor did not retain all discovered markers")
	bar_i := mx7_marker_index(markers,.Bar)
	garden_i := mx7_marker_index(markers,.Garden)
	stairs_i := mx7_marker_index(markers,.Stairs)
	testing.expect(t,bar_i >= 0 && garden_i >= 0 && stairs_i >= 0,"normal marker kinds changed")
	if bar_i >= 0 do testing.expect(t,markers.items[bar_i].world_pos == ar.Vec2{14.5,16.5},"Bar marker must target room center")
	if garden_i >= 0 do testing.expect(t,markers.items[garden_i].world_pos == ar.Vec2{27.5,21.5},"Garden marker must target room center")
	if stairs_i >= 0 do testing.expect(t,markers.items[stairs_i].world_pos == ar.Vec2{28.5,22.5},"stairs marker must target tile center")

	// Visibility can disappear without erasing ordinary-floor discovery.
	run.visible = {}
	testing.expect(t,ar.minimap_markers(&run).count == 3,"normal-floor markers forgot cumulative discovery")
}

@(test)
mx7_dark_minimap_refuges_are_live_only_but_seen_stairs_stick :: proc(t: ^testing.T) {
	run := mx7_marker_run(true)
	bar_center := ar.room_center(run.dungeon.rooms_buf[1])
	garden_center := ar.room_center(run.dungeon.rooms_buf[2])
	// Seeing a non-center room tile is deliberately insufficient on dark floors.
	run.visible[10][12] = true
	run.explored[10][12] = true
	testing.expect(t,mx7_marker_index(ar.minimap_markers(&run),.Bar) < 0,"dark Bar marker ignored center-live policy")

	run.visible[bar_center.x][bar_center.y] = true
	run.visible[garden_center.x][garden_center.y] = true
	run.visible[run.dungeon.stairs.x][run.dungeon.stairs.y] = true
	run.explored[run.dungeon.stairs.x][run.dungeon.stairs.y] = true
	markers := ar.minimap_markers(&run)
	testing.expect(t,markers.count == 3,"live dark-floor markers were not shown")

	run.visible = {}
	markers = ar.minimap_markers(&run)
	testing.expect(t,markers.count == 1 && markers.items[0].kind == .Stairs,"only once-seen stairs may persist on dark floors")
}

@(test)
mx7_minimap_clamp_and_arrow_preserve_direction :: proc(t: ^testing.T) {
	center := ar.Vec2{50,30}
	half := ar.Vec2{20,10}
	inside,inside_clamped := ar.minimap_clamp_to_bounds({55,35},center,half)
	testing.expect(t,!inside_clamped && inside == ar.Vec2{55,35},"inside marker was moved")

	east,east_clamped := ar.minimap_clamp_to_bounds({100,30},center,half)
	testing.expect(t,east_clamped && east == ar.Vec2{70,30},"east marker did not meet inset edge")
	diagonal,diagonal_clamped := ar.minimap_clamp_to_bounds({90,50},center,half)
	testing.expect(t,diagonal_clamped && diagonal == ar.Vec2{70,40},"diagonal marker did not preserve its center ray")

	arrow := ar.minimap_edge_arrow_vertices(east,center)
	testing.expect(t,arrow[0] == ar.Vec2{75,30},"edge-arrow tip length changed")
	testing.expect(t,arrow[1] == ar.Vec2{68,32} && arrow[2] == ar.Vec2{68,28},"edge-arrow base geometry changed")
}

@(test)
mx7_player_tick_projects_facing_through_isometric_space :: proc(t: ^testing.T) {
	center := ar.Vec2{40,20}
	_,shown := ar.minimap_player_tick_end(center,{},1)
	testing.expect(t,!shown,"zero facing drew a minimap tick")

	east,east_shown := ar.minimap_player_tick_end(center,{1,0},1)
	testing.expect(t,east_shown,"cardinal facing lost its tick")
	expected := ar.Vec2{4,2}/math.hypot(f32(4),f32(2))*ar.MINIMAP_PLAYER_TICK_REACH
	testing.expect(t,mx7_near(east.x-center.x,expected.x) && mx7_near(east.y-center.y,expected.y),"tick bypassed minimap projection")
	down,down_shown := ar.minimap_player_tick_end(center,{1,1},2.5)
	testing.expect(t,down_shown && mx7_near(down.x,center.x) && mx7_near(down.y,center.y+ar.MINIMAP_PLAYER_TICK_REACH),"diagonal facing should point straight down in iso space")

	app: ar.App
	app.run.player.pos={12.5,12.5}
	for x in 11..=13 do for y in 11..=13 do app.run.visible[x][y]=true
	testing.expect(t,ar.effect_fallback_compact_visible(&app,app.run.player.pos),"fully visible compact cue was rejected")
	app.run.visible[11][11]=false
	testing.expect(t,!ar.effect_fallback_compact_visible(&app,app.run.player.pos),"compact fallback accepted a footprint crossing LOS")
}

@(test)
mx7_floor_variants_are_seeded_without_coordinate_bands :: proc(t: ^testing.T) {
	seed := u64(0xA7C4_19D2_55E0_381B)
	first := ar.visual_floor_variant(seed,3,2,10,11)
	testing.expect(t,first == ar.visual_floor_variant(seed,3,2,10,11),"floor variant changed without regenerating the floor")

	counts: [4]int
	diagonal_mask: u8
	changed_on_next_floor := 0
	for x in 0..<16 {
		for y in 0..<16 {
			variant := ar.visual_floor_variant(seed,3,2,x,y) % 4
			counts[variant] += 1
			if x == y do diagonal_mask |= u8(1 << u32(variant))
			if ar.visual_floor_variant(seed,4,3,x,y) % 4 != variant do changed_on_next_floor += 1
		}
	}
	for count in counts do testing.expect(t,count >= 32 && count <= 96,"floor hash stopped distributing all four rotations")
	testing.expect(t,diagonal_mask == 0x0f,"floor rotations fell back into a constant diagonal generation band")
	testing.expect(t,changed_on_next_floor > 128,"floor rotation field did not change enough across generated floors")
}

@(test)
mx7_stairs_marker_uses_the_world_ping_pong_clock :: proc(t: ^testing.T) {
	fps := f32(8.333333)
	testing.expect(t,ar.world_sprite_frame_index(8,fps,true,0) == 0,"stairs pulse must begin at frame zero")
	testing.expect(t,ar.world_sprite_frame_index(8,fps,true,7/fps) == 7,"stairs pulse lost its forward apex")
	testing.expect(t,ar.world_sprite_frame_index(8,fps,true,8/fps) == 6,"stairs pulse did not ping-pong")
	testing.expect(t,ar.world_sprite_frame_index(8,fps,true,14/fps) == 0,"stairs pulse period changed")
	testing.expect(t,mx7_near(ar.visual_triangle_wave(0,1.68),0),"fallback stairs pulse must begin closed")
	testing.expect(t,mx7_near(ar.visual_triangle_wave(.84,1.68),1),"fallback stairs pulse must reach the same apex")
	testing.expect(t,mx7_near(ar.visual_triangle_wave(1.68,1.68),0),"fallback stairs pulse period changed")
}

@(test)
mx7_guiding_floor_wave_matches_pygame_crest :: proc(t: ^testing.T) {
	// Frame zero is the unchanged seeded floor; frames 1..8 select Pygame's
	// source-over glow overlays. The crest is three tiles wide and moves at 1.2/s.
	peak_time := f32(1.5)/ar.GUIDANCE_WAVE_TILES_PER_SECOND
	testing.expect(t,ar.guidance_wave_frame(0,5,8,peak_time,false) == 8,"guidance crest did not reach the full authored glow overlay")
	testing.expect(t,ar.guidance_wave_frame(1,5,8,peak_time,false) == 3,"guidance crest lost its triangular trailing edge")
	testing.expect(t,ar.guidance_wave_frame(2,5,8,peak_time,false) == 0,"guidance crest illuminated a tile ahead of itself")
	testing.expect(t,ar.guidance_wave_frame(0,5,8,peak_time,true) == 0,"guiding floor must remain calm while the player moves")
	wrap_time := f32(5+int(ar.GUIDANCE_WAVE_WINDOW_TILES))/ar.GUIDANCE_WAVE_TILES_PER_SECOND
	testing.expect(t,ar.guidance_wave_frame(0,5,8,wrap_time,false) == 0,"guidance crest did not wrap back to the player's feet")
}

@(private = "file")
mx7_shop_dungeon :: proc(room: ar.Room) -> (d: ar.Dungeon) {
	d.room_count = 1
	d.rooms_buf[0] = room
	d.special_room_count = 1
	d.special_rooms_buf[0] = {.Shop,0}
	for x in room.x..<room.x+room.w {
		for y in room.y..<room.y+room.h do d.tiles[x][y] = .Floor
	}
	ar.plan_shop_gold(&d)
	return
}

@(test)
mx7_shop_gold_count_is_room_size_aware :: proc(t: ^testing.T) {
	for w in 6..=12 {
		for h in 6..=11 {
			d := mx7_shop_dungeon({8,9,w,h})
			candidates := (w-2)*(h-2)-2
			expected := ar.shop_gold_count_for_candidates(candidates)
			testing.expectf(t,d.shop_gold.count == expected,"%vx%v Shop got %v piles, expected %v",w,h,d.shop_gold.count,expected)
		}
	}
	small := mx7_shop_dungeon({8,9,6,6})
	large := mx7_shop_dungeon({8,9,12,11})
	testing.expect(t,small.shop_gold.count == 7 && large.shop_gold.count == 12,"generated Shop dressing must span 7..12 piles")
}

@(test)
mx7_shop_gold_is_valid_unique_and_deterministic :: proc(t: ^testing.T) {
	room := ar.Room{10,12,8,8}
	a := mx7_shop_dungeon(room)
	b := mx7_shop_dungeon(room)
	testing.expect(t,a.shop_gold == b.shop_gold,"Shop dressing changed for identical room geometry")
	keeper := ar.room_center(room)
	sign := [2]int{keeper.x+1,keeper.y}
	variants_seen: [ar.SHOP_GOLD_VARIANT_COUNT]bool
	for i in 0..<a.shop_gold.count {
		stack := a.shop_gold.stacks[i]
		testing.expect(t,ar.room_contains_interior_tile(room,stack.tile.x,stack.tile.y),"gold escaped the strict Shop interior")
		testing.expect(t,stack.tile != keeper && stack.tile != sign,"gold overlapped keeper/sign reservation")
		testing.expect(t,1 <= stack.size && stack.size <= 3,"gold size left authored bag")
		testing.expect(t,int(stack.variant) < ar.SHOP_GOLD_VARIANT_COUNT,"gold variant left five-asset range")
		if int(stack.variant) < len(variants_seen) do variants_seen[stack.variant] = true
		for j in 0..<i do testing.expect(t,a.shop_gold.stacks[j].tile != stack.tile,"two gold stacks claimed one tile")
	}
	for seen,index in variants_seen do testing.expectf(t,seen,"generated Shop omitted gold variant %v",index)
}

@(test)
mx7_shop_gold_reserves_placement_without_becoming_collision :: proc(t: ^testing.T) {
	d := mx7_shop_dungeon({10,12,8,8})
	testing.expect(t,d.shop_gold.count > 0,"fixture produced no Shop gold")
	tile := d.shop_gold.stacks[0].tile
	testing.expect(t,ar.shop_gold_occupies_tile(&d,tile.x,tile.y),"gold layout lookup lost its tile")
	testing.expect(t,ar.special_room_placement_reserved_occupies_tile(&d,tile.x,tile.y),"population may overlap cosmetic Shop dressing")
	testing.expect(t,!ar.special_room_reserved_occupies_tile(&d,tile.x,tile.y),"cosmetic gold became a movement/nav obstacle")
	center := ar.room_center(d.rooms_buf[0])
	testing.expect(t,ar.shop_sign_occupies_tile(&d,center.x+1,center.y),"Shop sign placement reservation missing")
	d.special_rooms_buf[0].room_index = ar.MAX_ROOMS_CAP
	testing.expect(t,!ar.shop_sign_occupies_tile(&d,center.x+1,center.y),"malformed Shop room index was not rejected")
}

@(test)
mx7_shop_gold_draw_contract_uses_pygame_depth_and_scales :: proc(t: ^testing.T) {
	for size in u8(1)..=u8(3) {
		stack := ar.Shop_Gold_Stack{tile={4,11},size=size,variant=4}
		feet,depth,prop_index,scale := ar.shop_gold_draw_info(stack)
		testing.expect(t,feet == ar.Vec2{4.5,11.5},"gold draw anchor changed")
		testing.expect(t,mx7_near(depth,15.5),"gold must sort at tile x+y+0.5")
		testing.expect(t,prop_index == int(ar.Prop_Key.Gold_Stack_1)+4,"gold draw did not use all five assets")
		expected := size == 1 ? f32(.72) : size == 2 ? f32(.92) : f32(1.14)
		testing.expect(t,mx7_near(scale,expected),"gold size scale diverged from authored dressing")
	}
}
