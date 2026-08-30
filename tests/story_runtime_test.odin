package archrogue_tests

// MX-story App, modal minigame, and world-space Soul hunt acceptance. All tests are raylib-free.

import "core:testing"
import ar "../src"

@(private = "file")
story_runtime_start_app :: proc(app: ^ar.App, seed: u64, archetype: ar.Archetype_Id) {
	ar.app_init(app, seed)
	app.select_index = int(archetype)
	_ = ar.app_apply(app, ar.Intent{confirm=true}) // Title -> Select
	_ = ar.app_apply(app, ar.Intent{confirm=true}) // Select -> Playing + omen
}

@(private = "file")
story_runtime_reveal_and_confirm :: proc(app: ^ar.App, row := 0) {
	ar.app_story_panel_reveal(app)
	_ = ar.app_apply(app, ar.Intent{menu_index=row,menu_index_valid=true,confirm=true})
}

@(private = "file")
story_runtime_advance_to_play :: proc(state: ^ar.Story_Minigame_State) {
	_ = ar.story_minigame_confirm_ready(state)
	for state.phase == .Preview do _ = ar.story_minigame_tick(state,.25)
}

@(private = "file")
story_runtime_stage_soul_question :: proc(
	app: ^ar.App,
	seed: u64,
	archetype := ar.Archetype_Id.Rogue,
) -> (origin: ar.Vec2, room_index: int, ok: bool) {
	story_runtime_start_app(app,seed,archetype)
	ar.app_story_close_panel(app)
	app.run.depth=7
	room_index=min(1,app.run.dungeon.room_count-1)
	if room_index<0 do return
	app.run.dungeon.special_room_count=1
	app.run.dungeon.special_rooms_buf[0]={.Hall_Of_Unlost_Echoes,room_index}
	index:=app.run.depth-1
	app.run.story_runtime.soul={}
	app.run.story_runtime.hall={}
	app.run.story_runtime.hall_ledgers[index]={}
	app.run.story_runtime.soul_games[index]={}
	app.run.story_runtime.relic_records[index].committed=true
	app.run.story_runtime.requests={}
	ar.story_populate_floor(&app.run)
	if !app.run.story_runtime.soul.present do return
	origin=app.run.player.pos
	ok=ar.app_story_open_lossless_soul(app)
	return
}

@(private = "file")
story_runtime_advance_soul_hunt_to_play :: proc(app:^ar.App) -> bool {
	if app==nil||!ar.app_story_soul_hunt_active(app) do return false
	app.story_soul_hunt_music_ready=true
	for _ in 0..<16 {
		if app.story_minigame.phase!=.Preview do break
		_=ar.story_soul_hunt_tick(app,{},.25)
	}
	return app.story_minigame.phase==.Play&&app.story_minigame.active_cell>=0
}

@(private = "file")
story_runtime_win_soul_hunt :: proc(app:^ar.App) -> bool {
	if !story_runtime_advance_soul_hunt_to_play(app) do return false
	for _ in 0..<128 {
		if app.story_minigame.phase!=.Play do break
		if app.story_minigame.active_cell<0 {
			_=ar.story_soul_hunt_tick(app,{},.25)
			continue
		}
		target,active:=ar.story_soul_hunt_target_position(&app.story_minigame)
		if !active do return false
		app.run.player.pos=target
		app.run.player.prev_pos=target
		app.run.player.dash_timer=0
		if !ar.story_soul_hunt_dash(app,ar.STORY_SOUL_HUNT_START-target) do return false
	}
	return app.story_minigame.phase==.Result&&app.story_minigame.outcome==.Won&&
		app.story_minigame.score==app.story_minigame.goal
}

@(test)
mx_story_runtime_new_run_opens_mandatory_omen_and_pauses_sim :: proc(t:^testing.T) {
	app:ar.App
	story_runtime_start_app(&app,ar.derive_seed(520101,0),.Acolyte)
	defer ar.run_destroy(&app.run)

	testing.expect(t,app.mode==.Playing&&ar.app_play_modal_open(&app),"new story run must open a modal")
	testing.expect(t,app.story_panel.kind==.Omen&&app.story_panel.node==.Relic_Choice&&app.story_panel.mandatory,"depth-one omen must be mandatory")
	testing.expect(t,ar.app_story_current_speaker(&app)=="Nim Rue","omen narrator must be Nim Rue")
	testing.expect(t,ar.app_story_panel_full_narration(&app)!="","omen must own composed narration")
	testing.expect(t,ar.app_story_panel_visible_narration(&app)=="","typewriter must begin unrevealed")

	app.run.player.bolt_timer=1
	before:=app.story_panel.node_elapsed
	ar.app_tick(&app)
	testing.expect(t,app.run.player.bolt_timer==1&&app.story_panel.node_elapsed>before,"story modal clock must advance while gameplay clocks freeze")
	_ = ar.app_apply(&app,ar.Intent{back=true})
	testing.expect(t,app.story_panel.active,"mandatory omen must ignore Back")

	_ = ar.app_apply(&app,ar.Intent{confirm=true})
	testing.expect(t,app.story_panel.active&&ar.app_story_panel_narration_complete(&app),"first confirm must reveal narration")
	choices:=ar.app_story_panel_choices(&app)
	testing.expect(t,choices.count==3,"omen must expose Aid/Bargain/Defy")
	_ = ar.app_apply(&app,ar.Intent{confirm=true})
	testing.expect(t,!app.story_panel.active&&app.run.story_runtime.relic_records[0].committed,"second confirm must commit one relic path")
}

@(test)
mx_story_capture_staging_uses_reachable_production_panel_states :: proc(t: ^testing.T) {
	testing.expect(t,ar.mx_story_capture_scenario_from_env("omen_initial")==.Omen_Initial,"omen capture parser changed")
	testing.expect(t,ar.mx_story_capture_scenario_from_env("relic_choices")==.Relic_Choices,"relic capture parser changed")
	testing.expect(t,ar.mx_story_capture_scenario_from_env("guest")==.Guest,"guest capture parser changed")
	testing.expect(t,ar.mx_story_capture_scenario_from_env("soul")==.Soul,"Soul capture parser changed")
	testing.expect(t,ar.mx_story_capture_scenario_from_env("mistbound")==.Mistbound,"Mistbound capture parser changed")
	testing.expect(t,ar.mx_story_capture_scenario_from_env("ending")==.Ending,"ending capture parser changed")
	testing.expect(t,ar.mx_story_capture_scenario_from_env("decision_ask")==.Decision_Ask,"decision ask capture parser changed")
	testing.expect(t,ar.mx_story_capture_scenario_from_env("decision_depart")==.Decision_Depart,"decision depart capture parser changed")
	testing.expect(t,ar.mx_story_capture_scenario_from_env("unknown")==.None,"unknown capture scenario must stay inert")

	fixtures := [6]struct {
		scenario:  ar.MX_Story_Capture_Scenario,
		archetype: ar.Archetype_Id,
	}{
		{.Omen_Initial,.Acolyte},
		{.Relic_Choices,.Acolyte},
		{.Guest,.Ranger},
		{.Soul,.Warden},
		{.Mistbound,.Rogue},
		{.Ending,.Arcanist},
	}
	for fixture in fixtures {
		app: ar.App
		story_runtime_start_app(&app,ar.derive_seed(520199+u64(fixture.scenario),0),fixture.archetype)
		ok := ar.mx_story_stage_capture(&app,fixture.scenario)
		if fixture.scenario==.Mistbound {
			testing.expectf(t,ok&&ar.app_story_soul_hunt_active(&app)&&!app.story_panel.active,
				"%v capture did not stage the world-space hunt",fixture.scenario)
		} else {
			testing.expectf(t,ok&&app.story_panel.active&&!app.story_minigame.active,
				"%v capture did not stage a panel",fixture.scenario)
		}
		identity := ar.app_story_art_identity(&app)
		switch fixture.scenario {
		case .Omen_Initial:
			testing.expect(t,app.story_panel.kind==.Omen&&app.story_panel.node==.Relic_Choice&&!ar.app_story_panel_narration_complete(&app),"initial omen capture must retain the typewriter state")
			testing.expect(t,identity.has_motif&&identity.has_relic&&identity.relic==.Asterion_Nail,"initial omen capture art identity changed")
		case .Relic_Choices:
			choices:=ar.app_story_panel_choices(&app)
			testing.expect(t,ar.app_story_panel_narration_complete(&app)&&choices.count==3&&app.story_panel.choice_cursor==1,"relic capture must reveal three choices")
			testing.expect(t,identity.has_motif&&identity.has_relic&&identity.relic==.Crown_Of_Antlers_And_Teeth,"relic capture art identity changed")
		case .Guest:
			testing.expect(t,identity.has_guest&&identity.guest_role==.Antlered_Hunter&&identity.guest_variant==2,"guest capture must use Sable's authored portrait/backdrop")
			testing.expect(t,ar.app_story_current_speaker(&app)=="Sable of the Moon-Hunt"&&ar.app_story_panel_narration_complete(&app),"guest capture text fixture changed")
		case .Soul:
			choices:=ar.app_story_panel_choices(&app)
			testing.expect(t,app.story_panel.kind==.Soul&&app.story_panel.node==.Soul_Reflection&&choices.count==3,"Soul capture must expose all three verdicts without opening the minigame")
		case .Mistbound:
			_,ghost_active:=ar.story_soul_hunt_target_position(&app.story_minigame)
			testing.expect(t,app.story_minigame.phase==.Play&&ghost_active&&app.options.mist_enabled,
				"Mistbound capture must stage a visible ghost inside full chamber mist")
		case .Ending:
			choices:=ar.app_story_panel_choices(&app)
			testing.expect(t,app.story_panel.node==.Epilogue_Ending&&identity.has_ending&&identity.ending_verb==.Aid&&choices.count==1,"ending capture must use the Arcanist Aid ending and page action")
		case .Decision_Ask,.Decision_Depart: // menu-scene captures, staged below without a run
		case .None:
		}
		ar.run_destroy(&app.run)
	}

	// The first-boot decision stages from any mode and needs no run.
	{
		app: ar.App
		ar.app_init(&app,7301)
		testing.expect(t,ar.mx_story_stage_capture(&app,.Decision_Ask)&&app.mode==.Story_Decision&&
			app.story_decision_phase==.Ask&&app.options.mist_enabled,"decision ask capture must stage the question scene")
		testing.expect(t,ar.mx_story_stage_capture(&app,.Decision_Depart)&&app.story_decision_phase==.Depart&&
			!app.story_decision_yes&&app.story_decision_timer>0,"decision depart capture must stage the walk-off")
		ar.run_destroy(&app.run)
	}
}

@(test)
mx_story_runtime_each_floor_has_quest_guest_and_hall_by_seven :: proc(t:^testing.T) {
	run:ar.Run
	ar.run_start(&run,ar.derive_seed(520102,0),.Warden)
	defer ar.run_destroy(&run)
	hall_seen:=false
	for depth in 1..=ar.STORY_BEAT_COUNT {
		testing.expectf(t,run.depth==depth,"expected depth %v, got %v",depth,run.depth)
		quest,has_quest:=ar.special_room_for_kind(&run.dungeon,.Quest)
		guest:=ar.story_current_guest(&run)
		testing.expectf(t,has_quest&&guest!=nil,"story depth %v lost its Quest/guest",depth)
		if guest!=nil&&has_quest {
			_,room_index,found:=ar.dungeon_room_at_point(&run.dungeon,guest.pos.x,guest.pos.y)
			testing.expectf(t,found&&room_index==quest.room_index,"depth %v guest did not use the Quest room",depth)
		}
		_,has_hall:=ar.special_room_for_kind(&run.dungeon,.Hall_Of_Unlost_Echoes)
		hall_seen=hall_seen||has_hall
		if depth>=7 do testing.expect(t,hall_seen,"story must guarantee a Hall no later than depth seven")
		if depth==ar.STORY_BEAT_COUNT do break
		if !run.story_runtime.relic_records[depth-1].committed do testing.expect(t,ar.story_commit_relic_path(&run,.Aid),"fixture relic path failed")
		if guest!=nil&&!guest.resolved do testing.expect(t,ar.story_resolve_guest_choice(&run,guest,.Aid),"fixture guest choice failed")
		ar.run_descend(&run)
	}
}

@(test)
mx_story_runtime_modal_minigames_are_deterministic_and_winnable :: proc(t:^testing.T) {
	run:ar.Run
	ar.run_start(&run,ar.derive_seed(520103,0),.Rogue)
	defer ar.run_destroy(&run)

	kinds:=[2]ar.Story_Minigame_Kind{.Bind_The_Page,.Wake_The_Moonbloom}
	for kind in kinds {
		a:=ar.story_create_minigame(&run,kind,3,.Aid,kind==.Bind_The_Page)
		// Reset only the instance counter so this probes deterministic construction
		// from the same run/depth/instance namespace.
		run.story_runtime.minigame_counter-=1
		b:=ar.story_create_minigame(&run,kind,3,.Aid,kind==.Bind_The_Page)
		testing.expectf(t,a.seed==b.seed&&a.board==b.board&&a.sequence==b.sequence,"%v board did not replay",kind)
		story_runtime_advance_to_play(&a)
		switch kind {
		case .Bind_The_Page:
			for i in 0..<a.sequence_count do testing.expect(t,ar.story_minigame_press(&a,a.sequence[i],a.revision),"Bind input rejected")
		case .Wake_The_Moonbloom:
			for a.phase==.Play do testing.expect(t,ar.story_minigame_press(&a,a.active_cell,a.revision),"Moonbloom target rejected")
		case .Mirror_The_Unlost,.None:
		}
		testing.expectf(t,a.phase==.Result&&a.outcome==.Won&&a.score==a.goal,"%v did not reach Won",kind)
	}
}

@(test)
mx_story_runtime_soul_hunt_profiles_scale_by_verdict_and_replay :: proc(t:^testing.T) {
	fixtures:=[3]struct {
		verdict:ar.Story_Soul_Verdict,
		goal:int,
		time_limit:f32,
		ghost_seconds:f32,
	}{
		{.Preserve,6,ar.STORY_SOUL_HUNT_TIME_LIMIT_SECONDS,.92},
		{.Release,8,ar.STORY_SOUL_HUNT_TIME_LIMIT_SECONDS,.72},
		{.Refuse,12,ar.STORY_SOUL_HUNT_TIME_LIMIT_SECONDS,.54},
	}
	run:ar.Run
	ar.run_start(&run,ar.derive_seed(520105,0),.Rogue)
	defer ar.run_destroy(&run)
	for fixture in fixtures {
		profile:=ar.story_soul_hunt_profile(fixture.verdict)
		testing.expectf(t,profile.goal==fixture.goal&&profile.time_limit==fixture.time_limit&&
			profile.ghost_seconds==fixture.ghost_seconds,
			"%v Soul hunt profile changed",fixture.verdict)
		run.story_runtime.hall.verdict=fixture.verdict
		a:=ar.story_create_minigame(&run,.Mirror_The_Unlost,3,{},{})
		run.story_runtime.minigame_counter-=1
		b:=ar.story_create_minigame(&run,.Mirror_The_Unlost,3,{},{})
		testing.expectf(t,a.seed==b.seed&&a.goal==b.goal&&a.time_left==b.time_left&&a.board_count==b.board_count,
			"%v Soul hunt construction did not replay",fixture.verdict)
		testing.expect(t,a.phase==.Preview&&a.goal==profile.goal&&a.time_left==profile.time_limit&&
			a.board_count==ar.STORY_SOUL_HUNT_SITE_COUNT,"Soul hunt did not adopt its verdict profile")
	}
}

@(test)
mx_story_runtime_soul_answer_teleports_into_nonmodal_hunt_and_freezes_floor :: proc(t:^testing.T) {
	app:ar.App
	origin,_,staged:=story_runtime_stage_soul_question(&app,ar.derive_seed(520106,0))
	defer ar.run_destroy(&app.run)
	testing.expect(t,staged&&app.story_panel.node==.Soul_Reflection&&!app.story_minigame.active,
		"Soul interaction must ask the verdict before starting the hunt")
	app.run.arrival_timer=2
	app.run.player.bolt_timer=1
	combat_rng:=app.run.combat_rng
	story_runtime_reveal_and_confirm(&app,1)
	testing.expect(t,app.run.story_runtime.hall.verdict==.Release&&ar.app_story_soul_hunt_active(&app),
		"Release answer did not start the Soul hunt")
	testing.expect(t,!app.story_panel.active&&!ar.app_play_modal_open(&app)&&app.run.player.pos==ar.STORY_SOUL_HUNT_START,
		"Soul hunt must teleport into world space without retaining a modal")
	testing.expect(t,app.story_minigame.sequence_count==2&&origin!=app.run.player.pos,
		"Soul hunt must retain a return coordinate before teleporting")

	elapsed:=app.story_minigame.elapsed
	wait_pos:=app.run.player.pos
	_=ar.app_apply(&app,ar.Intent{move={1,0},aim={0,-3},aim_live=true})
	ar.app_tick(&app)
	testing.expect(t,app.story_minigame.elapsed>elapsed,"world-space hunt clock did not advance")
	testing.expect(t,app.run.player.pos==wait_pos&&app.run.player.facing==ar.Vec2{0,-1},
		"Mistbound wait must accept live aim for facing while suppressing movement")
	testing.expect(t,app.run.arrival_timer==2&&app.run.player.bolt_timer==1&&app.run.combat_rng==combat_rng,
		"ordinary floor clocks or RNG advanced behind the Soul hunt")

	_=ar.app_apply(&app,ar.Intent{back=true})
	testing.expect(t,app.mode==.Paused&&ar.app_story_soul_hunt_active(&app),"Back must pause without abandoning the hunt")
	elapsed=app.story_minigame.elapsed
	time_left:=app.story_minigame.time_left
	ar.app_tick(&app)
	testing.expect(t,app.story_minigame.elapsed==elapsed&&app.story_minigame.time_left==time_left,
		"paused Soul hunt clocks must remain frozen")
	_=ar.app_apply(&app,ar.Intent{back=true})
	testing.expect(t,app.mode==.Playing&&ar.app_story_soul_hunt_active(&app),"Back from pause must resume the hunt")
}

@(test)
mx_story_runtime_soul_hunt_walking_cannot_capture_but_dash_can :: proc(t:^testing.T) {
	app:ar.App
	_,_,staged:=story_runtime_stage_soul_question(&app,ar.derive_seed(520107,0))
	defer ar.run_destroy(&app.run)
	testing.expect(t,staged,"Soul question fixture failed")
	story_runtime_reveal_and_confirm(&app,0)
	testing.expect(t,story_runtime_advance_soul_hunt_to_play(&app),"Soul hunt did not reach Play")
	look_pos:=app.run.player.pos
	_=ar.app_apply(&app,ar.Intent{aim={-3,0},aim_live=true})
	ar.app_tick(&app)
	testing.expect(t,app.run.player.pos==look_pos&&app.run.player.facing==ar.Vec2{-1,0},
		"active Mistbound idle facing must follow live cursor aim")
	target,active:=ar.story_soul_hunt_target_position(&app.story_minigame)
	testing.expect(t,active,"Soul hunt did not reveal a ghost")
	target_cell:=app.story_minigame.active_cell
	app.run.player.pos=target-ar.Vec2{1.0,0}
	app.run.player.prev_pos=app.run.player.pos
	mistakes:=app.story_minigame.mistakes
	_=ar.story_soul_hunt_tick(&app,{1,0},.1)
	testing.expect(t,app.story_minigame.score==0&&app.story_minigame.active_cell==-1&&
		app.story_minigame.mistakes==mistakes+1,
		"walking into a ghost must dispel it as a miss before overlap")

	app.story_minigame.active_cell=target_cell
	app.story_minigame.target_time=ar.story_soul_hunt_profile(.Preserve).ghost_seconds
	app.story_minigame.lock_time=0
	app.run.player.pos=target-ar.Vec2{.2,0}
	app.run.player.prev_pos=app.run.player.pos
	dash:ar.Intent
	dash.aim={1,0}
	dash.aim_live=true
	dash.actions[3]=true
	_=ar.app_apply(&app,dash)
	testing.expect(t,app.story_minigame.score==1&&app.story_minigame.last_correct,
		"a dash through the same ghost must capture it")
	capture_sfx_found:=false
	for event in app.run.sfx do capture_sfx_found=capture_sfx_found||event.bank==.Mistbound_Ghost_Capture
	testing.expect(t,capture_sfx_found,"capturing a Mistbound ghost must emit its dedicated SFX")
}

@(test)
mx_story_runtime_soul_hunt_dash_sweeps_targets_and_blocked_dash_is_inert :: proc(t:^testing.T) {
	app:ar.App
	_,_,staged:=story_runtime_stage_soul_question(&app,ar.derive_seed(5201071,0))
	defer ar.run_destroy(&app.run)
	testing.expect(t,staged,"Soul question fixture failed")
	story_runtime_reveal_and_confirm(&app,0)
	testing.expect(t,story_runtime_advance_soul_hunt_to_play(&app),"Soul hunt did not reach Play")
	app.story_minigame.active_cell=9
	app.story_minigame.target_time=ar.story_soul_hunt_profile(.Preserve).ghost_seconds
	target,active:=ar.story_soul_hunt_target_position(&app.story_minigame)
	testing.expect(t,active,"dash sweep fixture lost its target")
	app.run.player.pos=target-ar.Vec2{1.3,0}
	app.run.player.prev_pos=app.run.player.pos
	app.run.player.dash_timer=0
	testing.expect(t,ar.story_soul_hunt_dash(&app,{1,0}),"crossing dash did not move")
	testing.expect(t,app.story_minigame.score==1&&app.run.player.pos.x>target.x,
		"dash segment must capture a target it crosses before overshooting")

	room:=ar.STORY_SOUL_HUNT_ROOM
	boundary:=ar.Vec2{f32(room.x+room.w-1)-.58,35}
	app.run.player.pos=boundary;app.run.player.prev_pos=boundary;app.run.player.dash_timer=0
	app.story_minigame.active_cell=9
	app.story_minigame.target_time=1
	score:=app.story_minigame.score
	testing.expect(t,!ar.story_soul_hunt_dash(&app,{1,0}),"edge-blocked zero-distance dash must be rejected")
	testing.expect(t,app.run.player.pos==boundary&&app.run.player.dash_timer==0&&app.story_minigame.score==score,
		"rejected dash must not spend cooldown or mutate capture state")
}

@(test)
mx_story_runtime_soul_hunt_platform_has_no_interior_obstacles :: proc(t:^testing.T) {
	room:=ar.STORY_SOUL_HUNT_ROOM
	for y in room.y+2..<room.y+room.h-2 {
		for x in room.x+2..<room.x+room.w-2 {
			testing.expectf(t,ar.story_soul_hunt_position_open({f32(x)+.5,f32(y)+.5}),
				"Mistbound platform interior unexpectedly blocked at (%v, %v)",x,y)
		}
	}
}

@(test)
mx_story_runtime_soul_hunt_returns_exactly_and_rewards_each_verdict_once :: proc(t:^testing.T) {
	fixtures:=[3]struct {
		verdict:ar.Story_Soul_Verdict,
		row:int,
		max_mana:int,
		spell_bonus:int,
		memory_tokens:int,
	}{
		{.Preserve,0,45,2,4},
		{.Release,1,45,3,4},
		{.Refuse,2,50,3,5},
	}
	for fixture,index in fixtures {
		app:ar.App
		origin,room_index,staged:=story_runtime_stage_soul_question(&app,ar.derive_seed(520108+u64(index),0))
		testing.expectf(t,staged,"%v Soul question fixture failed",fixture.verdict)
		app.run.player.max_mana=40
		app.run.player.mana=3
		app.run.player.discipline_spell_bonus=2
		app.run.player.memory_tokens=4
		app.run.player.dash_timer=.73
		story_runtime_reveal_and_confirm(&app,fixture.row)
		testing.expectf(t,app.run.story_runtime.hall.verdict==fixture.verdict,"%v verdict was not committed",fixture.verdict)
		testing.expectf(t,story_runtime_win_soul_hunt(&app),"%v Soul hunt did not reach Won",fixture.verdict)
		completed:=app.story_minigame
		testing.expect(t,ar.app_story_finalize_minigame(&app),"won Soul hunt did not finalize")
		ledger:=app.run.story_runtime.soul_games[app.run.depth-1]
		testing.expect(t,ledger.valid&&ledger.room_index==room_index&&ledger.outcome==.Won,
			"Soul hunt result did not commit to its per-depth ledger")
		testing.expect(t,app.run.player.pos==origin&&app.run.player.prev_pos==origin,
			"Soul hunt must return to the exact saved floor coordinate")
		testing.expect(t,app.run.player.dash_timer==.73,
			"Soul hunt must restore the real-floor dash cooldown instead of refreshing it")
		testing.expect(t,app.story_panel.active&&app.story_panel.node==.Soul_Settled&&!app.story_minigame.active,
			"Soul hunt completion must return to settled dialogue")
		testing.expectf(t,app.run.player.max_mana==fixture.max_mana&&app.run.player.mana==f32(fixture.max_mana)&&
			app.run.player.discipline_spell_bonus==fixture.spell_bonus&&app.run.player.memory_tokens==fixture.memory_tokens,
			"%v Soul hunt reward changed",fixture.verdict)

		app.story_minigame=completed
		max_mana:=app.run.player.max_mana
		spell_bonus:=app.run.player.discipline_spell_bonus
		memory_tokens:=app.run.player.memory_tokens
		testing.expect(t,ar.app_story_finalize_minigame(&app),"duplicate Soul result fixture did not finalize")
		testing.expect(t,app.run.player.max_mana==max_mana&&app.run.player.discipline_spell_bonus==spell_bonus&&
			app.run.player.memory_tokens==memory_tokens,"per-depth Soul ledger must suppress duplicate rewards")
		ar.run_destroy(&app.run)
	}
}

@(test)
mx_story_runtime_lost_soul_hunt_returns_without_reward :: proc(t:^testing.T) {
	app:ar.App
	origin,_,staged:=story_runtime_stage_soul_question(&app,ar.derive_seed(5201101,0))
	defer ar.run_destroy(&app.run)
	testing.expect(t,staged,"Soul question fixture failed")
	app.run.player.max_mana=40;app.run.player.mana=3
	app.run.player.discipline_spell_bonus=2;app.run.player.memory_tokens=4
	story_runtime_reveal_and_confirm(&app,2)
	app.story_minigame.phase=.Result;app.story_minigame.outcome=.Lost
	app.story_minigame.active_cell=-1;app.story_minigame.result_time=0
	testing.expect(t,ar.app_story_finalize_minigame(&app),"lost Soul hunt did not finalize")
	testing.expect(t,app.run.player.pos==origin&&app.run.player.max_mana==40&&app.run.player.mana==3&&
		app.run.player.discipline_spell_bonus==2&&app.run.player.memory_tokens==4,
		"lost Soul hunt must return without granting its verdict reward")
}

@(test)
mx_story_runtime_legacy_and_malformed_mirror_states_normalize_safely :: proc(t:^testing.T) {
	app:ar.App
	story_runtime_start_app(&app,ar.derive_seed(520111,0),.Warden)
	defer ar.run_destroy(&app.run)
	ar.app_story_close_panel(&app)
	app.run.depth=7
	app.run.story_runtime.hall.verdict=.Unresolved
	app.run.player.dash_timer=.57
	app.story_minigame={active=true,kind=.Mirror_The_Unlost,phase=.Play,depth=7,board_count=6,goal=3,sequence_count=0,
		revealed_count=1}
	app.story_minigame.revealed[0]=4 // legacy revealed-card index, not encoded cooldown bits
	ar.app_story_normalize_soul_hunt_after_restore(&app)
	testing.expect(t,!app.story_minigame.active&&app.story_panel.active&&app.story_panel.node==.Soul_Reflection,
		"legacy pair board must resume at the Soul verdict instead of entering the world hunt")
	testing.expect(t,ar.app_play_modal_open(&app),"normalized legacy save must expose the Soul question as a modal")
	testing.expect(t,app.run.player.dash_timer==.57,
		"legacy pair-board revealed cells must not overwrite the persisted dungeon dash cooldown")

	app.story_panel={}
	app.run.story_runtime.hall.verdict=.Preserve
	app.run.story_runtime.hall.room_index=0
	testing.expect(t,ar.app_story_start_mirror_the_unlost(&app,0),"valid world-hunt fixture did not start")
	ar.app_story_normalize_soul_hunt_after_restore(&app)
	testing.expect(t,ar.app_story_soul_hunt_active(&app)&&!app.story_panel.active&&!ar.app_play_modal_open(&app),
		"valid world-hunt state must survive restore normalization")
	app.story_minigame.sequence[0]=int(0x7fc00000)
	ar.app_story_normalize_soul_hunt_after_restore(&app)
	testing.expect(t,!app.story_minigame.active&&app.story_panel.active&&app.story_panel.node==.Soul_Settled,
		"malformed current hunt must return safely without reopening the committed verdict")
	testing.expect(t,!ar.blocked_for_radius(&app.run.dungeon,app.run.player.pos.x,app.run.player.pos.y,
		ar.PLAYER_HIT_RADIUS,block_stairs=true),"malformed hunt recovery left the player outside the real floor")
}

@(test)
mx_story_runtime_gate_ending_and_bell_are_explicit_nodes :: proc(t:^testing.T) {
	app:ar.App
	story_runtime_start_app(&app,ar.derive_seed(520104,0),.Ranger)
	defer ar.run_destroy(&app.run)
	story_runtime_reveal_and_confirm(&app)

	app.run.depth=ar.DUNGEON_DEPTH
	app.run.tyrant_dead=true
	clear(&app.run.enemies)
	app.run.story_runtime.requests.epilogue=true
	_ = ar.app_story_process_requests(&app)
	testing.expect(t,app.story_panel.node==.Epilogue_Gate&&!app.run.victory,"epilogue must begin at the Gate question")

	story_runtime_reveal_and_confirm(&app,int(ar.Story_Choice_Verb.Aid))
	testing.expect(t,app.story_panel.node==.Epilogue_Ending&&app.run.story.flags.gate==.Aid,"Gate choice must select the archetype ending")
	story_runtime_reveal_and_confirm(&app)
	testing.expect(t,app.story_panel.node==.Epilogue_Bell&&!app.run.victory,"ending prose must precede the bell")
	story_runtime_reveal_and_confirm(&app)
	testing.expect(t,app.run.victory&&app.mode==.Victory&&app.run.story_runtime.epilogue_stage==.Completed,"only the bell must complete story victory")
}
