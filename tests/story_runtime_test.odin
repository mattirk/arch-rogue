package archrogue_tests

// MX-story App/modal and minigame acceptance. All tests are raylib-free.

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
	testing.expect(t,ar.mx_story_capture_scenario_from_env("ending")==.Ending,"ending capture parser changed")
	testing.expect(t,ar.mx_story_capture_scenario_from_env("unknown")==.None,"unknown capture scenario must stay inert")

	fixtures := [5]struct {
		scenario:  ar.MX_Story_Capture_Scenario,
		archetype: ar.Archetype_Id,
	}{
		{.Omen_Initial,.Acolyte},
		{.Relic_Choices,.Acolyte},
		{.Guest,.Ranger},
		{.Soul,.Warden},
		{.Ending,.Arcanist},
	}
	for fixture in fixtures {
		app: ar.App
		story_runtime_start_app(&app,ar.derive_seed(520199+u64(fixture.scenario),0),fixture.archetype)
		ok := ar.mx_story_stage_capture(&app,fixture.scenario)
		testing.expectf(t,ok&&app.story_panel.active&&!app.story_minigame.active,"%v capture did not stage a panel",fixture.scenario)
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
		case .Ending:
			choices:=ar.app_story_panel_choices(&app)
			testing.expect(t,app.story_panel.node==.Epilogue_Ending&&identity.has_ending&&identity.ending_verb==.Aid&&choices.count==1,"ending capture must use the Arcanist Aid ending and page action")
		case .None:
		}
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
mx_story_runtime_all_three_minigames_are_deterministic_and_winnable :: proc(t:^testing.T) {
	run:ar.Run
	ar.run_start(&run,ar.derive_seed(520103,0),.Rogue)
	defer ar.run_destroy(&run)

	for kind in ar.Story_Minigame_Kind {
		if kind==.None do continue
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
		case .Mirror_The_Unlost:
			for sigil in ar.Story_Sigil_Id {
				first,second:=-1,-1
				for cell in 0..<a.board_count {
					if a.board[cell]!=sigil do continue
					if first<0 do first=cell
					else {second=cell;break}
				}
				if first>=0&&second>=0 {
					testing.expect(t,ar.story_minigame_press(&a,first,a.revision),"Mirror first seal rejected")
					testing.expect(t,ar.story_minigame_press(&a,second,a.revision),"Mirror pair rejected")
				}
				if a.phase==.Result do break
			}
		case .None:
		}
		testing.expectf(t,a.phase==.Result&&a.outcome==.Won&&a.score==a.goal,"%v did not reach Won",kind)
	}
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
