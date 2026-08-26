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
	profiles:=[7]ar.Room_Npc_Profile_Id{.Shopkeeper,.Bar_Dancer,.Garden_Frog,.Story_Guest,.Lossless_Soul,.Soulless_Clanker,.String}
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
		if profile != .Soulless_Clanker do testing.expectf(t,danced,"profile %v never entered explicit Dance",profile)
		else do testing.expect(t,!danced,"Clanker interaction gesture must never trigger as ambient motion")
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
	hall:=ar.Room{40,8,10,9}
	run.dungeon.room_count=3
	run.dungeon.rooms_buf[0]=bar
	run.dungeon.rooms_buf[1]=garden
	run.dungeon.rooms_buf[2]=hall
	room_npc_test_carve_room(&run.dungeon,bar)
	room_npc_test_carve_room(&run.dungeon,garden)
	room_npc_test_carve_room(&run.dungeon,hall)
	run.dungeon.special_rooms_buf[0]={.Bar,0}
	run.dungeon.special_rooms_buf[1]={.Garden,1}
	run.dungeon.special_rooms_buf[2]={.Hall_Of_Unlost_Echoes,2}
	run.dungeon.special_room_count=3
	ar.plan_bar_furnishings(&run.dungeon)
	ar.room_npc_initialize_ambient_residents(&run)
	testing.expect(t,run.ambient_residents.count==5,"Bar, Garden, and Hall must fill the five-resident ambient capacity")
	bar_count,string_count,frog_count,clanker_count:=0,0,0,0
	for i in 0..<run.ambient_residents.count {
		resident:=run.ambient_residents.items[i]
		testing.expect(t,resident.active&&resident.prev_pos==resident.pos,"resident initialization must collapse interpolation history")
		switch resident.kind {
		case .Bar_Dancer:       bar_count+=1
		case .Garden_Frog:      frog_count+=1
		case .Soulless_Clanker: clanker_count+=1
		case .String:           string_count+=1
		}
	}
	testing.expect(t,bar_count==1&&string_count==1&&frog_count==2&&clanker_count==1,
		"ambient resident kinds no longer match special-room actor layouts")
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
soulless_clanker_spawns_in_hall_and_clanks_on_interaction :: proc(t:^testing.T) {
	run:=room_npc_test_run(.Hall_Of_Unlost_Echoes,71045)
	defer ar.run_destroy(&run)
	testing.expect(t,run.ambient_residents.count==1,"Hall must contain one ambient Soulless Clanker")
	clanker:=&run.ambient_residents.items[0]
	testing.expect(t,clanker.active&&clanker.kind==.Soulless_Clanker,"Hall resident must be the Soulless Clanker")
	hall:=run.dungeon.rooms_buf[0]
	center:=ar.room_center(hall)
	testing.expect(t,int(clanker.pos.x)!=center.x,"Clanker must not overlap the Lossless Soul center anchor")
	run.player.pos=clanker.pos+ar.Vec2{.5,0}
	run.player.prev_pos=run.player.pos
	testing.expect(t,ar.interact_prompt(&run)=="E: greet the Soulless Clanker","Clanker prompt must identify the NPC")
	clanker_pos:=clanker.pos
	_ = ar.player_interact(&run)
	testing.expect(t,!clanker.active,"greeting must retire the room-resident Clanker")
	testing.expect(t,len(run.familiars)==1&&run.familiars[0].kind==.Soulless_Clanker,"greeting must create exactly one Clanker familiar")
	joined:=&run.familiars[0]
	testing.expect(t,joined.pos==clanker_pos&&joined.prev_pos==clanker_pos,"Clanker familiar must inherit the resident position without interpolation drift")
	testing.expect(t,joined.max_hp==ar.SOULLESS_CLANKER_HP&&joined.damage==ar.SOULLESS_CLANKER_DAMAGE,"Clanker familiar must receive its authored combat stats")
	testing.expect(t,len(run.numbers)==1&&run.numbers[0].text=="Clank, clank, clank!","interaction must emit the exact Clanker line")
	testing.expect(t,len(run.sfx)==1&&run.sfx[0].bank==.Soulless_Clanker&&run.sfx[0].spatial,"interaction must emit the spatial Clanker SFX")
	testing.expect(t,ar.interact_prompt(&run)=="","joined Clanker must no longer advertise the room interaction")

	run.player.pos=clanker_pos+ar.Vec2{3,0}
	follow_start:=joined.pos
	ar.tick_familiars_dt(&run,.5)
	testing.expect(t,joined.pos.x>follow_start.x,"joined Clanker must follow the player")
	enemy:=ar.enemy_make(.Ghoul,joined.pos+ar.Vec2{.8,0},1)
	enemy.hp=100
	enemy.max_hp=100
	enemy.cooldown=999
	append(&run.enemies,enemy)
	ar.tick_familiars_dt(&run,.01)
	testing.expect(t,run.enemies[0].hp<100&&joined.attack_anim_timer>0,"joined Clanker must attack a nearby enemy")
}

@(test)
string_plays_in_bar_and_joins_as_a_guitar_familiar :: proc(t:^testing.T) {
	run:=room_npc_test_run(.Bar,71047)
	defer ar.run_destroy(&run)
	testing.expect(t,run.ambient_residents.count==2,"Bar must contain its dancer and String")
	guitarist:=&run.ambient_residents.items[1]
	testing.expect(t,guitarist.active&&guitarist.kind==.String,"second Bar resident must be String")
	bar_layout:=ar.special_room_actor_layout(&run.dungeon,.Bar)
	testing.expect(t,bar_layout.count==2&&guitarist.pos==ar.Vec2{f32(bar_layout.tiles[1].x)+.5,f32(bar_layout.tiles[1].y)+.5},
		"String must use the second reserved Bar actor anchor")
	for i in 0..<run.dungeon.bar_furnishings.count {
		testing.expect(t,run.dungeon.bar_furnishings.tiles[i]!=bar_layout.tiles[1],"Bar furnishing overlaps String's reserved anchor")
	}

	run.player.pos=guitarist.pos+ar.Vec2{.5,0}
	run.player.prev_pos=run.player.pos
	testing.expect(t,ar.interact_prompt(&run)=="E: greet String","String prompt must identify the guitarist")
	string_pos:=guitarist.pos
	expected_response:=ar.string_join_response(&run)
	_ = ar.player_interact(&run)
	testing.expect(t,!guitarist.active,"greeting must retire room-resident String")
	testing.expect(t,len(run.familiars)==1&&run.familiars[0].kind==.String,"greeting must create exactly one String familiar")
	joined:=&run.familiars[0]
	testing.expect(t,joined.pos==string_pos&&joined.prev_pos==string_pos,"String familiar must inherit the resident position")
	testing.expect(t,joined.max_hp==ar.STRING_HP&&joined.damage==ar.STRING_DAMAGE&&joined.speed==ar.STRING_SPEED,
		"String familiar must receive authored combat stats")
	testing.expect(t,len(run.numbers)==1&&run.numbers[0].text==expected_response,
		"String interaction must use the deterministic join-response table")
	testing.expect(t,len(ar.STRING_JOIN_RESPONSES)==6&&
		ar.STRING_JOIN_RESPONSES[0]=="A sour chord. String joins you."&&
		ar.STRING_JOIN_RESPONSES[1]=="A crooked melody joins your descent."&&
		ar.STRING_JOIN_RESPONSES[2]=="The dungeon inherits the next verse."&&
		ar.STRING_JOIN_RESPONSES[3]=="A minor key follows at your heels."&&
		ar.STRING_JOIN_RESPONSES[4]=="The next verse belongs to the dead."&&
		ar.STRING_JOIN_RESPONSES[5]=="No applause. String follows anyway.",
		"String join-response table changed")
	testing.expect(t,ar.interact_prompt(&run)=="","joined String must no longer advertise the room interaction")

	run.player.pos=string_pos+ar.Vec2{3,0}
	follow_start:=joined.pos
	ar.tick_familiars_dt(&run,.5)
	testing.expect(t,joined.pos.x>follow_start.x,"joined String must follow the player")
	enemy:=ar.enemy_make(.Ghoul,joined.pos+ar.Vec2{.8,0},1)
	enemy.hp,enemy.max_hp,enemy.cooldown=100,100,999
	append(&run.enemies,enemy)
	ar.tick_familiars_dt(&run,.01)
	testing.expect(t,run.enemies[0].hp<100&&joined.attack_anim_timer>0,"joined String must attack a nearby enemy")
	ar.clear_summoned_familiars(&run)
	testing.expect(t,len(run.familiars)==1&&run.familiars[0].kind==.String,"class summon recasts must not dismiss String")
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
