package archrogue_tests

// Deterministic fixed-step room-resident movement, dance, collision, and
// interaction contracts. These tests exercise the shared component directly;
// no renderer, wall clock, or gameplay RNG participates.

import "core:testing"
import ar "../src"

@(private = "file")
room_npc_test_carve_room :: proc(d: ^ar.Dungeon, room: ar.Room) {
	for x in room.x+1 ..< room.x+room.w-1 {
		for y in room.y+1 ..< room.y+room.h-1 do d.tiles[x][y]=.Floor
	}
}

@(private = "file")
room_npc_test_run :: proc(kind: ar.Special_Room_Kind, seed := u64(71001)) -> ar.Run {
	run:ar.Run
	run.seed=seed
	run.depth=1
	for x in 0..<ar.MAP_W do for y in 0..<ar.MAP_H do run.dungeon.tiles[x][y]=.Wall
	room:=ar.Room{10,10,10,9}
	run.dungeon.room_count=1
	run.dungeon.rooms_buf[0]=room
	room_npc_test_carve_room(&run.dungeon,room)
	run.dungeon.stairs={1,1}
	run.dungeon.special_rooms_buf[0]={kind,0}
	run.dungeon.special_room_count=1
	if kind==.Bar do ar.plan_bar_furnishings(&run.dungeon)
	if kind==.Shop do ar.plan_shop_gold(&run.dungeon)
	run.player.pos={2.5,2.5}
	run.player.prev_pos=run.player.pos
	run.loot_rng=ar.rng_make(ar.derive_seed(seed,1),stream=2)
	run.combat_rng=ar.rng_make(ar.derive_seed(seed,1),stream=5)
	if kind==.Shop {
		run.shopkeeper=ar.shopkeeper_make(seed,1,room,0)
		run.has_shopkeeper=true
	}
	ar.room_npc_initialize_ambient_residents(&run)
	return run
}

@(test)
room_npc_same_seed_replays_and_never_consumes_gameplay_rng :: proc(t:^testing.T) {
	a:=room_npc_test_run(.Bar,71011)
	b:=room_npc_test_run(.Bar,71011)
	defer ar.run_destroy(&a)
	defer ar.run_destroy(&b)
	loot_before,combat_before:=a.loot_rng,a.combat_rng
	moved,danced:=false,false
	room:=a.dungeon.rooms_buf[0]
	for tick in 1..=3600 {
		elapsed:=f32(tick)*ar.SIM_DT
		ar.room_npc_snapshot_live_positions(&a)
		ar.room_npc_snapshot_live_positions(&b)
		ar.room_npc_tick_live(&a,elapsed,ar.SIM_DT)
		ar.room_npc_tick_live(&b,elapsed,ar.SIM_DT)
		testing.expectf(t,a.ambient_residents==b.ambient_residents,"same-seed room motion diverged at fixed tick %v",tick)
		resident:=&a.ambient_residents.items[0]
		moved=moved||resident.pos!=resident.motion.home
		danced=danced||resident.motion.dancing
		testing.expect(t,ar.room_contains_interior_tile(room,int(resident.pos.x),int(resident.pos.y)),"resident left the strict room interior")
		testing.expect(t,!ar.blocked_for_radius(&a.dungeon,resident.pos.x,resident.pos.y,ar.ROOM_NPC_RADIUS),"resident entered furnishing or wall collision")
		profile:=ar.room_npc_profile(resident.motion.profile)
		delta:=resident.pos-resident.motion.home
		testing.expect(t,delta.x*delta.x+delta.y*delta.y<=(profile.leash+.05)*(profile.leash+.05),"resident exceeded its profile leash")
	}
	testing.expect(t,moved&&danced,"Bar resident must exhibit both deterministic wandering and explicit dance")
	testing.expect(t,a.loot_rng==loot_before&&a.combat_rng==combat_before,"room motion consumed a gameplay RNG stream")
}

@(test)
room_npc_profiles_all_walk_and_dance_without_leaving_the_room :: proc(t:^testing.T) {
	run:=room_npc_test_run(.Garden,71021)
	defer ar.run_destroy(&run)
	center_tile:=ar.room_center(run.dungeon.rooms_buf[0])
	home:=ar.Vec2{f32(center_tile.x)+.5,f32(center_tile.y)+.5}
	profiles:=[5]ar.Room_Npc_Profile_Id{.Shopkeeper,.Bar_Dancer,.Garden_Frog,.Story_Guest,.Lossless_Soul}
	for profile,i in profiles {
		pos:=home
		motion:=ar.room_npc_motion_make(home,0,ar.derive_seed(run.seed,u64(i+1)*0xA11CE),profile)
		moved,danced:=false,false
		for tick in 1..=9000 {
			ar.room_npc_motion_tick(&run,&pos,&motion,false,false,f32(tick)*ar.SIM_DT,ar.SIM_DT)
			moved=moved||pos!=home
			danced=danced||motion.dancing
			testing.expectf(t,ar.room_contains_interior_tile(run.dungeon.rooms_buf[0],int(pos.x),int(pos.y)),"profile %v escaped its room",profile)
		}
		testing.expectf(t,moved,"profile %v never walked",profile)
		testing.expectf(t,danced,"profile %v never entered explicit Dance",profile)
	}
}

@(test)
ambient_resident_set_is_fixed_capacity_and_comes_from_actor_layouts :: proc(t:^testing.T) {
	run:ar.Run
	run.seed=71031
	run.depth=2
	for x in 0..<ar.MAP_W do for y in 0..<ar.MAP_H do run.dungeon.tiles[x][y]=.Wall
	bar:=ar.Room{8,8,10,9}
	garden:=ar.Room{24,8,10,9}
	run.dungeon.room_count=2
	run.dungeon.rooms_buf[0]=bar
	run.dungeon.rooms_buf[1]=garden
	room_npc_test_carve_room(&run.dungeon,bar)
	room_npc_test_carve_room(&run.dungeon,garden)
	run.dungeon.special_rooms_buf[0]={.Bar,0}
	run.dungeon.special_rooms_buf[1]={.Garden,1}
	run.dungeon.special_room_count=2
	ar.plan_bar_furnishings(&run.dungeon)
	ar.room_npc_initialize_ambient_residents(&run)
	testing.expect(t,run.ambient_residents.count==ar.MAX_AMBIENT_ROOM_RESIDENTS,"Bar plus Garden must fill exactly one dancer and two frog slots")
	bar_count,frog_count:=0,0
	for i in 0..<run.ambient_residents.count {
		resident:=run.ambient_residents.items[i]
		testing.expect(t,resident.active&&resident.prev_pos==resident.pos,"resident initialization must collapse interpolation history")
		switch resident.kind {case .Bar_Dancer:bar_count+=1;case .Garden_Frog:frog_count+=1}
	}
	testing.expect(t,bar_count==1&&frog_count==2,"ambient resident kinds no longer match special-room actor layouts")
}

@(test)
ambient_residents_pause_for_hostiles_and_hold_to_face_interactions :: proc(t:^testing.T) {
	run:=room_npc_test_run(.Garden,71041)
	defer ar.run_destroy(&run)
	frog:=&run.ambient_residents.items[0]
	enemy:=ar.enemy_make(.Ghoul,ar.Vec2{frog.motion.home.x,frog.motion.home.y},1)
	enemy.hp=max(1,enemy.hp)
	append(&run.enemies,enemy)
	frog.motion.target=frog.pos+ar.Vec2{1,0}
	ar.room_npc_motion_set_moving(&frog.motion,true)
	before:=frog.pos
	ar.room_npc_snapshot_live_positions(&run)
	ar.room_npc_tick_live(&run,ar.SIM_DT,ar.SIM_DT)
	testing.expect(t,frog.pos==before&&!frog.motion.moving&&!frog.motion.dancing,"living room hostile must pause Garden motion and dance")

	run.enemies[0].hp=0
	run.player.pos=frog.pos+ar.Vec2{1,0}
	ar.room_npc_tick_live(&run,2*ar.SIM_DT,ar.SIM_DT)
	testing.expect(t,frog.motion.holding&&!frog.motion.moving&&!frog.motion.dancing,"nearby interaction must hold the frog in place")
	testing.expect(t,frog.motion.facing.x>.9&&abs(frog.motion.facing.y)<.1,"held resident must face the player")
}

@(test)
completed_garden_minigame_does_not_swallow_interact :: proc(t:^testing.T) {
	run:=room_npc_test_run(.Garden,71051)
	defer ar.run_destroy(&run)
	frog:=&run.ambient_residents.items[0]
	run.player.pos=frog.pos
	run.player.prev_pos=frog.pos
	run.story_runtime.garden_games[0]={valid=true,room_index=0,outcome=.Won}
	append(&run.ground_items,ar.Ground_Item{item=ar.Item{kind=.Heal_Potion,name="Fallback Flask"},pos=run.player.pos})
	before:=run.player.heal_potions
	_ = ar.player_interact(&run)
	testing.expect(t,run.player.heal_potions==before+1&&len(run.ground_items)==0,"completed Garden interaction must fall through to nearby loot")
}
