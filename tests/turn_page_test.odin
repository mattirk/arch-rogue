package archrogue_tests

import "core:encoding/json"
import "core:math"
import "core:testing"
import ar "../src"

turn_page_test_start :: proc(depth: int, seed: u64=9707) -> ar.App {
	app:ar.App
	ar.app_init(&app,seed)
	ar.run_start(&app.run,seed,.Rogue,.Medium,false)
	app.mode=.Playing;app.run.depth=depth
	ar.run_regenerate_floor(&app.run,false)
	app.run.story_runtime.requests={}
	_=ar.app_story_start_bind_the_page(&app,.Aid)
	return app
}
turn_page_test_reveal :: proc(app: ^ar.App) {
	for _ in 0..<100 {
		if app.story_minigame.phase!=.Preview do return
		_=ar.turn_page_tick(app,{},ar.SIM_DT)
	}
}
@(test)
turn_page_analog_walk_uses_actual_distance_for_animation :: proc(t: ^testing.T) {
	for magnitude in ([2]f32{1,.25}) {
		app:=turn_page_test_start(5)
		defer ar.run_destroy(&app.run)
		turn_page_test_reveal(&app)
		before:=app.run.player.pos;phase:=app.run.player.anim_time
		direction:=ar.turn_page_center(app.turn_page.route[1])-before
		_=ar.turn_page_tick(&app,direction*magnitude,ar.SIM_DT)
		delta:=app.run.player.pos-before
		distance:=math.hypot(delta.x,delta.y)
		expected:=ar.walk_animation_advance(ar.SIM_DT,ar.PLAYER_MOVE_SPEED,distance,ar.PLAYER_MOVE_SPEED*ar.SIM_DT)
		testing.expect(t,app.run.player.moving&&!app.turn_page.fall_active)
		testing.expect(t,abs(app.run.player.anim_time-phase-expected)<.000001,"manuscript walking must use the same distance-scaled cadence as dungeon walking")
	}
}

turn_page_test_solve_page :: proc(app: ^ar.App, t: ^testing.T) {
	page_number:=app.story_minigame.score
	turn_page_test_reveal(app)
	aligned_step:=-1
	for _ in 0..<1000 {
		if app.story_minigame.score!=page_number||app.story_minigame.outcome!=.None do return
		step:=app.story_minigame.step
		if step!=aligned_step {
			ar.turn_page_move(app,ar.turn_page_center(app.turn_page.route[step])-app.run.player.pos,false)
			aligned_step=step
		}
		next:=step+1
		if app.turn_page.gaps[next] {
			// Align to the current cell with actual movement, then dash. A full
			// supported takeoff footprint must fit every generated route.
			center:=ar.turn_page_center(app.turn_page.route[step])
			ar.turn_page_move(app,center-app.run.player.pos,false)
			app.run.player.dash_timer=0
			aim:=ar.turn_page_center(app.turn_page.route[next+1])-app.run.player.pos
			testing.expect(t,ar.turn_page_dash(app,aim))
		} else {
			aim:=ar.turn_page_center(app.turn_page.route[next])-app.run.player.pos
			distance:=math.hypot(aim.x,aim.y)
			ar.turn_page_move(app,aim*min(f32(1),.04/max(distance,f32(.001))),false)
		}
		if app.turn_page.fall_active {testing.expectf(t,false,"solvable route fell at page %d step %d",page_number,step);return}
	}
	testing.expect(t,false,"route failed to reach its seal")
}

@(test)
turn_page_routes_replay_and_fit_swept_player_with_reachable_gaps :: proc(t: ^testing.T) {
	for depth in ([3]int{5,8,9}) {
		for seed in 0..<300 {
			for page in 0..<ar.turn_page_profile(depth,0).pages {
				a:=ar.turn_page_generate(u64(seed),depth,page)
				b:=ar.turn_page_generate(u64(seed),depth,page)
				testing.expect(t,a==b&&ar.turn_page_route_valid(&a))
				app:ar.App
				app.turn_page=a;app.story_minigame={active=true,kind=.Bind_The_Page,phase=.Play,seed=u64(seed),depth=depth,score=page,goal=ar.turn_page_profile(depth,0).pages,time_left=40}
				app.run.player.pos=ar.turn_page_center(a.route[0])
				turn_page_test_solve_page(&app,t)
				testing.expect(t,app.story_minigame.score==page+1)
				ar.run_destroy(&app.run)
			}
		}
	}
}

@(test)
turn_page_preview_pause_and_menu_keep_dungeon_frozen :: proc(t: ^testing.T) {
	app:=turn_page_test_start(9)
	defer ar.run_destroy(&app.run)
	pos:=app.run.player.pos;dungeon:=app.run.dungeon;explored:=app.run.explored
	rng:=app.run.combat_rng;loot_rng:=app.run.loot_rng;clock:=app.run.active_ticks
	ar.app_apply(&app,ar.Intent{move={1,0},aim={0,1},aim_live=true,actions={false,false,false,true}})
	ar.app_tick(&app)
	testing.expect(t,app.run.player.pos==pos&&app.run.player.facing==ar.Vec2{0,1}&&app.run.player.dash_timer==0)
	testing.expect(t,!ar.app_play_modal_open(&app))
	testing.expect(t,app.run.dungeon==dungeon&&app.run.explored==explored&&app.run.combat_rng==rng&&app.run.loot_rng==loot_rng&&app.run.active_ticks==clock)
	ar.app_apply(&app,ar.Intent{back=true})
	state:=app.story_minigame;page:=app.turn_page;player:=ar.turn_page_capture_player(&app.run.player)
	for _ in 0..<30 do ar.app_tick(&app)
	testing.expect(t,app.mode==.Paused&&app.story_minigame==state&&app.turn_page==page&&ar.turn_page_capture_player(&app.run.player)==player)
}

@(test)
turn_page_walk_allows_small_lateral_drift_and_still_detects_wrong_steps :: proc(t:^testing.T) {
	for side in ([2]f32{-1,1}) {
		app:=turn_page_test_start(5)
		defer ar.run_destroy(&app.run)
		turn_page_test_reveal(&app)
		start:=app.run.player.pos
		forward:=ar.turn_page_center(app.turn_page.route[1])-start
		lateral:=ar.Vec2{-forward.y,forward.x}*side
		ar.turn_page_move(&app,lateral*.30,false)
		testing.expect(t,!app.turn_page.fall_active&&app.story_minigame.mistakes==0,"small drift within a safe tile must not fall")
		testing.expect(t,math.hypot((app.run.player.pos-start).x,(app.run.player.pos-start).y)>.29)
		ar.turn_page_move(&app,forward*.90,false)
		testing.expect(t,!app.turn_page.fall_active&&app.story_minigame.step==1,"off-center walking must reach the next tile safely")
		ar.turn_page_move(&app,start-app.run.player.pos,false)
		// Back at the start, the opposite longitudinal neighbor is always wrong.
		ar.turn_page_move(&app,-forward*.80,false)
		testing.expect(t,app.turn_page.fall_active&&app.story_minigame.mistakes==1,"committing to a wrong tile must still fall once")
	}
}

@(test)
turn_page_offcenter_dashes_brake_on_supported_landings :: proc(t:^testing.T) {
	for gap in ([2]bool{false,true}) do for side in ([2]f32{-1,1}) {
		app:=turn_page_test_start(8)
		defer ar.run_destroy(&app.run)
		if gap {app.story_minigame.score=1;ar.turn_page_begin_page(&app)}
		turn_page_test_reveal(&app)
		takeoff:=gap?1:0;landing_step:=gap?3:1
		ar.turn_page_move(&app,ar.turn_page_center(app.turn_page.route[takeoff])-app.run.player.pos,false)
		landing:=ar.turn_page_center(app.turn_page.route[landing_step])
		forward:=(landing-app.run.player.pos)/f32(gap?2:1)
		lateral:=ar.Vec2{-forward.y,forward.x}*side
		ar.turn_page_move(&app,lateral*.25,false)
		testing.expect(t,!app.turn_page.fall_active)
		testing.expect(t,ar.turn_page_dash(&app,forward))
		testing.expect(t,!app.turn_page.fall_active&&app.story_minigame.mistakes==0&&app.story_minigame.step==landing_step,"off-center dash must stop on its next supported landing")
		delta:=app.run.player.pos-landing
		along:=delta.x*forward.x+delta.y*forward.y
		across:=delta.x*lateral.x+delta.y*lateral.y
		testing.expect(t,along>=-.001&&along<=.041&&abs(across-.25)<.001,"dash must brake at the center plane while preserving lateral placement")
	}
}

@(test)
turn_page_wrong_step_and_dash_cannot_skip_or_double_count_fall :: proc(t: ^testing.T) {
	app:=turn_page_test_start(8)
	defer ar.run_destroy(&app.run)
	turn_page_test_reveal(&app)
	start:=app.run.player.pos
	forward:=ar.turn_page_center(app.turn_page.route[1])-start
	testing.expect(t,ar.turn_page_dash(&app,-forward))
	testing.expect(t,app.turn_page.fall_active&&app.story_minigame.mistakes==1&&app.story_minigame.step==0)
	for _ in 0..<20 {_=ar.turn_page_dash(&app,forward);_=ar.turn_page_tick(&app,forward,ar.SIM_DT)}
	testing.expect(t,app.story_minigame.mistakes==1&&app.turn_page.fall_active)
	for _ in 0..<90 do _=ar.turn_page_tick(&app,{},ar.SIM_DT)
	testing.expect(t,!app.turn_page.fall_active&&app.run.player.pos==start&&app.story_minigame.step==0)
}

@(test)
turn_page_fallen_tiles_block_repeated_walking_and_dashing :: proc(t:^testing.T) {
	for seed in 0..<8 {
		app:=turn_page_test_start(5,u64(seed))
		defer ar.run_destroy(&app.run)
		turn_page_test_reveal(&app)
		start:=app.run.player.pos
		forward:=ar.turn_page_center(app.turn_page.route[1])-start
		ar.turn_page_move(&app,-forward*.8,false)
		testing.expect(t,app.turn_page.fall_active&&app.story_minigame.mistakes==1,"an intact wrong tile must still collapse")
		fallen:=app.turn_page.fall_cell
		for _ in 0..<100 do _=ar.turn_page_tick(&app,{},ar.SIM_DT)
		testing.expect(t,!app.turn_page.fall_active&&app.turn_page.tiles[fallen.x][fallen.y]==.Gone)
		for _ in 0..<90 do _=ar.turn_page_tick(&app,-forward,ar.SIM_DT)
		edge:=app.run.player.pos
		testing.expect(t,!app.run.player.moving&&edge!=start,"held movement should approach the hole, then stop")
		testing.expect(t,ar.turn_page_dash(&app,-forward))
		ar.turn_page_move(&app,-forward*20,false)
		testing.expect(t,app.run.player.pos==edge&&!app.turn_page.fall_active&&app.story_minigame.mistakes==1,"neither walking nor dashing may enter a fallen tile or charge another mistake")
		testing.expect(t,app.turn_page.tiles[fallen.x][fallen.y]==.Gone&&!ar.turn_page_sweep_touches_cell(edge,edge,fallen),"the footprint must stay clear of the persistent hole")
		ar.turn_page_move(&app,start-edge,false)
		ar.turn_page_move(&app,forward,false)
		testing.expect(t,!app.turn_page.fall_active&&app.story_minigame.step==1,"the player must be able to move away and resume the route")
	}
}

@(test)
turn_page_authored_gaps_block_walking_but_allow_supported_dashes :: proc(t:^testing.T) {
	app:=turn_page_test_start(8)
	defer ar.run_destroy(&app.run)
	app.story_minigame.score=1;ar.turn_page_begin_page(&app);turn_page_test_reveal(&app)
	ar.turn_page_move(&app,ar.turn_page_center(app.turn_page.route[1])-app.run.player.pos,false)
	gap:=app.turn_page.route[2];forward:=ar.turn_page_center(gap)-app.run.player.pos
	for _ in 0..<60 do _=ar.turn_page_tick(&app,forward,ar.SIM_DT)
	testing.expect(t,!app.turn_page.fall_active&&app.story_minigame.mistakes==0&&app.story_minigame.step==1,"walking must stop at an authored gap")
	testing.expect(t,!ar.turn_page_sweep_touches_cell(app.run.player.pos,app.run.player.pos,gap))
	testing.expect(t,ar.turn_page_dash(&app,forward))
	testing.expect(t,!app.turn_page.fall_active&&app.story_minigame.step==3&&app.turn_page.tiles[gap.x][gap.y]==.Gone,"a dash from the blocked edge must still cross the marked gap")
}

@(test)
turn_page_hole_corners_block_before_committing_a_wrong_step :: proc(t:^testing.T) {
	for seed in 0..<8 {
		app:=turn_page_test_start(5,u64(seed))
		defer ar.run_destroy(&app.run)
		turn_page_test_reveal(&app)
		start:=app.run.player.pos
		forward:=ar.turn_page_center(app.turn_page.route[1])-start
		lateral:=ar.Vec2{-forward.y,forward.x}
		fallen:=app.turn_page.route[0]-[2]int{int(forward.x),int(forward.y)}
		app.turn_page.tiles[fallen.x][fallen.y]=.Gone
		ar.turn_page_move(&app,-forward+lateral,false)
		testing.expect(t,!app.turn_page.fall_active&&app.story_minigame.mistakes==0,"a blocked corner must not trigger an adjacent wrong tile in the rejected segment")
		testing.expect(t,!ar.turn_page_sweep_touches_cell(app.run.player.pos,app.run.player.pos,fallen))
		ar.turn_page_move(&app,start-app.run.player.pos,false)
		ar.turn_page_move(&app,lateral*.8,false)
		testing.expect(t,app.turn_page.fall_active&&app.story_minigame.mistakes==1,"a separate move onto intact wrong stone must still fall")
	}
}

@(test)
turn_page_obstructed_dash_cannot_leave_player_standing_over_a_gap :: proc(t:^testing.T) {
	app:=turn_page_test_start(8)
	defer ar.run_destroy(&app.run)
	app.story_minigame.score=1;ar.turn_page_begin_page(&app);turn_page_test_reveal(&app)
	ar.turn_page_move(&app,ar.turn_page_center(app.turn_page.route[1])-app.run.player.pos,false)
	gap:=app.turn_page.route[2];forward:=ar.turn_page_center(gap)-app.run.player.pos
	lateral:=ar.Vec2{-forward.y,forward.x}
	hole:=gap+[2]int{int(lateral.x),int(lateral.y)}
	app.turn_page.tiles[hole.x][hole.y]=.Gone
	testing.expect(t,ar.turn_page_dash(&app,forward+lateral*.45))
	testing.expect(t,app.turn_page.fall_active&&app.turn_page.fall_cell==gap&&app.story_minigame.mistakes==1,"an interrupted airborne dash must resolve its unsupported landing")
	testing.expect(t,app.turn_page.tiles[hole.x][hole.y]==.Gone,"the obstructing hole must not collapse again")
}

@(test)
turn_page_results_restore_exact_actions_clocks_and_reward_once :: proc(t: ^testing.T) {
	for won in ([2]bool{false,true}) {
		app:=turn_page_test_start(5)
		// Seed distinctive borrowed values in the frozen return snapshot.
		app.turn_page.return_player.facing={-.6,.8};app.turn_page.return_player.dash_timer=1.7
		app.turn_page.return_player.visual_action=.Dash;app.turn_page.return_player.action_time=.08
		app.turn_page.return_player.action_duration=.2;app.turn_page.return_player.sim_elapsed=137
		saved:=app.turn_page.return_player
		hp:=app.run.player.max_hp-7;app.run.player.hp=hp
		power:=app.run.player.discipline_melee_bonus
		if won {
			for _ in 0..<2 do turn_page_test_solve_page(&app,t)
		} else {turn_page_test_reveal(&app);app.story_minigame.time_left=.01;_=ar.turn_page_tick(&app,{},ar.SIM_DT)}
		testing.expect(t,ar.app_story_finalize_minigame(&app))
		testing.expect(t,ar.turn_page_capture_player(&app.run.player)==saved,"return must restore all borrowed player fields exactly")
		testing.expect(t,app.run.player.hp==(won?app.run.player.max_hp:hp)&&app.run.player.discipline_melee_bonus==power+(won?1:0))
		testing.expect(t,app.run.story_runtime.relic_records[4].committed&&app.run.story_runtime.relic_records[4].path==.Aid)
		testing.expect(t,!ar.app_story_finalize_minigame(&app)&&!ar.app_story_start_bind_the_page(&app,.Aid))
		ar.run_destroy(&app.run)
	}
}

@(test)
turn_page_save_resume_replays_preview_traversal_fall_and_result :: proc(t: ^testing.T) {
	for phase in 0..<5 {
		app:=turn_page_test_start(9,u64(500+phase))
		app.run.run_id=ar.persistence_clone_string("turn-page-test")
		if phase>0 {
			turn_page_test_reveal(&app)
			if phase<4 do ar.turn_page_move(&app,ar.turn_page_center(app.turn_page.route[1])-app.run.player.pos,false)
		}
		if phase==2 {ar.turn_page_wrong(&app,{4,4});_=ar.turn_page_tick(&app,{},.25)}
		if phase==3 {app.story_minigame.time_left=.001;_=ar.turn_page_tick(&app,{},.1)}
		if phase==4 {
			forward:=ar.turn_page_center(app.turn_page.route[1])-app.run.player.pos
			ar.turn_page_move(&app,-forward*.8,false)
			for _ in 0..<100 do _=ar.turn_page_tick(&app,{},ar.SIM_DT)
		}
		bytes,ok:=ar.persistence_encode_run(&app,1,"2026-09-05T12:00:00Z")
		testing.expect(t,ok)
		document,status:=ar.persistence_decode_run(bytes);delete(bytes)
		testing.expect(t,status==.Valid)
		resumed:ar.App
		testing.expect(t,ar.app_install_run_document(&resumed,&document));ar.run_document_destroy(&document)
		testing.expect(t,resumed.turn_page==app.turn_page&&resumed.story_minigame==app.story_minigame)
		testing.expect(t,ar.visual_turn_page_motion_age(&resumed,1)==ar.visual_turn_page_motion_age(&app,1),"save/resume must keep the same manuscript pose")
		testing.expect(t,ar.turn_page_capture_player(&resumed.run.player)==ar.turn_page_capture_player(&app.run.player))
		if phase==4 {
			forward:=ar.turn_page_center(app.turn_page.route[1])-app.run.player.pos
			_=ar.turn_page_tick(&app,-forward,.25);_=ar.turn_page_tick(&resumed,-forward,.25)
			testing.expect(t,!resumed.turn_page.fall_active&&resumed.story_minigame.mistakes==1,"restored holes must retain their movement blocking")
			testing.expect(t,ar.turn_page_capture_player(&resumed.run.player)==ar.turn_page_capture_player(&app.run.player))
		}
		for _ in 0..<10 {_=ar.turn_page_tick(&app,{},ar.SIM_DT);_=ar.turn_page_tick(&resumed,{},ar.SIM_DT)}
		testing.expect(t,resumed.turn_page==app.turn_page&&resumed.story_minigame==app.story_minigame)
		testing.expect(t,ar.visual_turn_page_motion_age(&resumed,1)==ar.visual_turn_page_motion_age(&app,1),"save/resume must keep the same manuscript pose")
		ar.run_destroy(&app.run);ar.run_destroy(&resumed.run)
	}
}

@(test)
turn_page_schema_two_modal_migrates_without_coordinate_reinterpretation :: proc(t: ^testing.T) {
	app:=turn_page_test_start(5)
	defer ar.run_destroy(&app.run)
	ar.turn_page_restore_player(&app.run.player,app.turn_page.return_player)
	original:=app.run.player.pos
	app.turn_page={};app.story_minigame.phase=.Play;app.story_minigame.board_count=6
	app.story_minigame.sequence_count=4;app.story_minigame.sequence={2,3,1,5,0,0}
	ar.run_ensure_persisted_entity_ids(&app.run)
	payload:=ar.run_save_payload_from_app(&app)
	bytes,_:=ar.persistence_marshal(payload)
	legacy:ar.Run_Save_Payload_V2
	testing.expect(t,json.unmarshal(bytes,&legacy)==nil);delete(bytes)
	legacy_bytes,_:=ar.persistence_marshal(legacy);hash:=ar.persistence_sha256(legacy_bytes);delete(legacy_bytes)
	doc:=ar.Run_Document_V2{schema_version=2,game_release="6.0.0-alpha.26",document_id="legacy-page",run_id="legacy-page",payload_sha256=hash,payload=legacy}
	doc_bytes,_:=ar.persistence_marshal(doc);delete(hash)
	reclaimed:=ar.run_payload_from_v2(&legacy);ar.run_save_payload_destroy(&reclaimed)
	decoded,status:=ar.persistence_decode_run(doc_bytes);delete(doc_bytes)
	testing.expect(t,status==.Migrated)
	resumed:ar.App
	testing.expect(t,ar.app_install_run_document(&resumed,&decoded))
	ar.run_document_destroy(&decoded)
	testing.expect(t,resumed.turn_page.version==1&&resumed.turn_page.return_player.pos==original&&resumed.story_minigame.phase==.Preview&&resumed.story_minigame.has_continuation)
	ar.run_destroy(&resumed.run)
}

@(test)
turn_page_entire_persisted_dungeon_stays_frozen_during_play_and_pause :: proc(t: ^testing.T) {
	app:=turn_page_test_start(9)
	defer ar.run_destroy(&app.run)
	app.run.arrival_timer=1.3;app.run.wall_face_timer=.7
	before:=ar.run_save_payload_from_app(&app)
	before.turn_page={};before.story_minigame={}
	ar.turn_page_restore_player(&before.player,app.turn_page.return_player)
	before_bytes,_:=ar.persistence_marshal(before);defer delete(before_bytes)
	for _ in 0..<120 do ar.app_tick(&app)
	ar.app_apply(&app,ar.Intent{back=true})
	for _ in 0..<120 do ar.app_tick(&app)
	after:=ar.run_save_payload_from_app(&app)
	after.turn_page={};after.story_minigame={}
	ar.turn_page_restore_player(&after.player,app.turn_page.return_player)
	after_bytes,_:=ar.persistence_marshal(after);defer delete(after_bytes)
	testing.expect(t,string(before_bytes)==string(after_bytes),"all actors, RNG, dungeon, clocks, cooldowns, exploration and progression must remain frozen")
	testing.expect(t,app.run.arrival_timer==1.3&&app.run.wall_face_timer==.7)
}

@(test)
turn_page_sweep_detects_corner_grazes_and_saved_route_corruption :: proc(t: ^testing.T) {
	testing.expect(t,ar.turn_page_sweep_touches_cell({-.5,-.11},{1.5,-.11},{0,0}),"sweep must detect foot contact missed by endpoints")
	testing.expect(t,!ar.turn_page_sweep_touches_cell({-.5,-.13},{1.5,-.13},{0,0}))
	testing.expect(t,ar.turn_page_sweep_touches_cell({-.09,-.09},{-.08,-.08},{0,0}))
	app:=turn_page_test_start(8)
	defer ar.run_destroy(&app.run)
	payload:=ar.run_save_payload_from_app(&app)
	testing.expect(t,ar.turn_page_saved_state_valid(&payload))
	payload.turn_page.route[1]={-1000,0}
	testing.expect(t,!ar.turn_page_saved_state_valid(&payload))
	payload=ar.run_save_payload_from_app(&app);payload.story_minigame.step=1000
	testing.expect(t,!ar.turn_page_saved_state_valid(&payload))
}

@(test)
turn_page_mobile_utility_menu_and_controller_aim_use_world_input :: proc(t: ^testing.T) {
	app:=turn_page_test_start(5)
	defer ar.run_destroy(&app.run)
	ar.app_apply(&app,ar.Intent{toggle_mobile_utility=true})
	testing.expect(t,app.mobile_utility_open)
	ar.app_apply(&app,ar.Intent{aim={-1,0},aim_live=true})
	ar.app_tick(&app)
	testing.expect(t,app.run.player.facing==ar.Vec2{-1,0})
	ar.app_apply(&app,ar.Intent{back=true})
	testing.expect(t,app.mode==.Paused)
	layout,status:=ar.mobile_layout_build({surface_width=1280,surface_height=800,density=1,revision=1})
	testing.expect(t,status==.Valid)
	set:=ar.mobile_soul_hunt_target_set(&layout,{},true)
	testing.expect(t,set.count==3,"alternate world must expose only Dash, utility and Menu touch targets")
}

@(test)
turn_page_timeout_during_fall_finishes_animation_without_a_second_mistake :: proc(t: ^testing.T) {
 app:=turn_page_test_start(9)
 defer ar.run_destroy(&app.run)
 turn_page_test_reveal(&app)
 ar.turn_page_wrong(&app,{4,4});app.story_minigame.time_left=.01
 for _ in 0..<60 do _=ar.turn_page_tick(&app,{},ar.SIM_DT)
 testing.expect(t,app.story_minigame.outcome==.Lost&&app.story_minigame.mistakes==1)
 testing.expect(t,app.turn_page.tiles[4][4]==.Gone&&app.turn_page.fall_elapsed==ar.TURN_PAGE_FALL_SECONDS)
}

@(test)
turn_page_confirms_tile_entry_without_requiring_a_center_hit :: proc(t: ^testing.T) {
 app:=turn_page_test_start(5)
 defer ar.run_destroy(&app.run)
 turn_page_test_reveal(&app)
 direction:=ar.turn_page_center(app.turn_page.route[1])-app.run.player.pos
 ar.turn_page_move(&app,direction*.55,false)
 testing.expect(t,app.story_minigame.step==1&&!app.turn_page.fall_active)
}
