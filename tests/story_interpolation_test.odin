package archrogue_tests

// Fixed-step interpolation contract for story-friendly actors.

import "core:testing"
import ar "../src"

@(test)
story_interpolation_spawn_and_regeneration_collapse_history :: proc(t:^testing.T) {
	run:ar.Run
	ar.run_start(&run,ar.derive_seed(61401,0),.Ranger)
	defer ar.run_destroy(&run)
	guest:=ar.story_current_guest(&run)
	testing.expect(t,guest!=nil&&guest.prev_pos==guest.pos,"spawned guest must not streak from zero")
	if guest==nil do return
	guest.prev_pos={-100,-100}
	ar.run_regenerate_floor(&run,false)
	guest=ar.story_current_guest(&run)
	testing.expect(t,guest!=nil&&guest.prev_pos==guest.pos,"same-floor regeneration must collapse guest interpolation")
}

@(test)
story_interpolation_snapshot_precedes_ambient_and_ally_motion :: proc(t:^testing.T) {
	run:ar.Run
	ar.run_start(&run,ar.derive_seed(61402,0),.Warden)
	defer ar.run_destroy(&run)
	guest:=ar.story_current_guest(&run)
	if guest==nil {testing.expect(t,false,"fixture lost guest");return}
	start:=guest.pos
	guest.motion.target=ar.Vec2{start.x+1,start.y}
	ar.story_snapshot_friendly_npc_positions(&run)
	ar.story_tick_friendly_npc_movement(&run,2,.25)
	testing.expect(t,guest.prev_pos==start,"ambient movement must retain the fixed-tick start")
	if guest.pos!=start do testing.expect(t,guest.prev_pos!=guest.pos,"moving guest needs a nonzero interpolation segment")

	guest.resolved=true
	guest.ally=true
	guest.max_hp=30
	guest.hp=30
	guest.motion.home=start
	guest.prev_pos=guest.pos
	// A snapshot after an out-of-band teleport collapses it before the next tick.
	guest.pos=ar.Vec2{start.x+.5,start.y+.5}
	ar.story_snapshot_friendly_npc_positions(&run)
	testing.expect(t,guest.prev_pos==guest.pos,"tick-start snapshot must collapse pre-tick teleports")
}

@(test)
room_npc_interpolation_snapshots_shop_and_ambient_segments :: proc(t:^testing.T) {
	run:ar.Run
	ar.run_start(&run,ar.derive_seed(61403,0),.Warden)
	defer ar.run_destroy(&run)
	room:=run.dungeon.rooms_buf[0]
	run.shopkeeper=ar.shopkeeper_make(run.seed,run.depth,room,0)
	run.has_shopkeeper=true
	run.player.pos={0,0}
	start:=run.shopkeeper.pos
	run.shopkeeper.motion.target=start+ar.Vec2{.5,0}
	ar.room_npc_motion_set_moving(&run.shopkeeper.motion,true)
	ar.room_npc_snapshot_live_positions(&run)
	ar.room_npc_tick_live(&run,.25,.25)
	testing.expect(t,run.shopkeeper.prev_pos==start,"shop snapshot must retain the fixed-tick start")
	if run.shopkeeper.pos!=start {
		mid:=ar.room_npc_interpolated_position(run.shopkeeper.prev_pos,run.shopkeeper.pos,.5)
		expected:=run.shopkeeper.prev_pos+(run.shopkeeper.pos-run.shopkeeper.prev_pos)*.5
		testing.expect(t,mid==expected&&mid!=run.shopkeeper.prev_pos&&mid!=run.shopkeeper.pos,"room NPC interpolation must land inside the live segment")
	}
}
