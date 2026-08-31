package archrogue_tests

// First-boot Clanker decision and the story-off run shape. The question runs
// once per clean options document; its answer flips options.story_enabled.
// Story Off suppresses narrative delivery while retaining rooms, relics, and
// deterministic minigames.

import "core:testing"
import ar "../src"

@(test)
story_decision_pending_only_while_clean_options_lack_an_answer :: proc(t:^testing.T) {
	app:ar.App
	ar.app_init(&app,4241)
	defer ar.run_destroy(&app.run)
	testing.expect(t,ar.app_story_decision_pending(&app),"fresh defaults owe the first-boot question")
	app.options.story_decided=true
	testing.expect(t,!ar.app_story_decision_pending(&app),"an answered question never returns")
	app.options.story_decided=false
	app.options_save_damaged=true
	testing.expect(t,!ar.app_story_decision_pending(&app),"damaged options defer to the recovery flow")
	app.options_save_damaged=false
	app.profile_save_damaged=true
	testing.expect(t,!ar.app_story_decision_pending(&app),"damaged profile defers to the recovery flow")
}

@(test)
story_decision_no_mutes_story_and_walks_off_to_title :: proc(t:^testing.T) {
	app:ar.App
	ar.app_init(&app,4242)
	defer ar.run_destroy(&app.run)
	ar.app_begin_story_decision(&app)
	testing.expect(t,app.mode==.Story_Decision&&app.story_decision_phase==.Ask)
	testing.expect(t,ar.music_hold_boot_intro(&app),"the open question must hold the boot intro loop")

	// Horizontal navigation wraps between Yes (0) and No (1).
	_=ar.app_apply(&app,{menu_horizontal=1})
	testing.expect(t,app.story_decision_index==1)
	_=ar.app_apply(&app,{menu_horizontal=1})
	testing.expect(t,app.story_decision_index==0)

	// A pointer press lands index and confirm together, like the title rows.
	_=ar.app_apply(&app,{menu_index=1,menu_index_valid=true,confirm=true})
	testing.expect(t,app.story_decision_phase==.Depart&&!app.story_decision_yes)
	testing.expect(t,string(ar.story_decision_notice(false))=="Story mode disabled. Enable it anytime in Options.",
		"the No departure must explain how to restore story mode")
	testing.expect(t,!app.options.story_enabled&&app.options.story_decided,"the decision must land in options")
	testing.expect(t,.Save_Options in app.platform_effects,"the decision must persist immediately")
	testing.expect(t,app.ui_sfx_override&&app.ui_sfx_bank==.Soulless_Clanker,"the machine answers in its own voice")
	testing.expect(t,!ar.music_hold_boot_intro(&app),"the decision must release the intro hold for the menu hand-off")

	// The farewell walk hands over to the Title on its own clock (2.8 s at 60 Hz).
	for _ in 0..<200 do ar.app_tick(&app)
	testing.expect(t,app.mode==.Title,"the walk-off must end at the title screen")
	testing.expect(t,!ar.music_hold_boot_intro(&app))
}

@(test)
story_decision_yes_keeps_story_and_confirm_skips_the_walk :: proc(t:^testing.T) {
	app:ar.App
	ar.app_init(&app,4243)
	defer ar.run_destroy(&app.run)
	app.options.story_enabled=false // a stale value must be overwritten by Yes
	ar.app_begin_story_decision(&app)
	_=ar.app_apply(&app,{confirm=true}) // default cursor is Yes
	testing.expect(t,app.story_decision_yes&&app.options.story_enabled&&app.options.story_decided)
	testing.expect(t,string(ar.story_decision_notice(true))=="Story mode enabled. Change it anytime in Options.",
		"the Yes departure must explain that the choice remains configurable")
	testing.expect(t,app.mode==.Story_Decision&&app.story_decision_phase==.Depart)
	_=ar.app_apply(&app,{confirm=true})
	testing.expect(t,app.mode==.Title,"confirm during the walk-off must skip to the title")
}

@(test)
story_decision_options_row_toggles_next_run_story :: proc(t:^testing.T) {
	app:ar.App
	ar.app_init(&app,4244)
	defer ar.run_destroy(&app.run)
	ar.app_enter_options(&app,.Title)
	app.options_index=10
	_=ar.app_apply(&app,{confirm=true})
	testing.expect(t,!app.options.story_enabled,"row 10 must toggle the story layer")
	testing.expect(t,.Save_Options in app.platform_effects)
	_=ar.app_apply(&app,{confirm=true})
	testing.expect(t,app.options.story_enabled)
	app.options_index=11
	_=ar.app_apply(&app,{confirm=true})
	testing.expect(t,app.mode==.Title,"row 11 must remain the return row")
}

@(test)
story_disabled_run_keeps_gameplay_content_and_claims_victory_at_the_gate :: proc(t:^testing.T) {
	run:ar.Run
	ar.run_start(&run,ar.derive_seed(77001,0),.Warden,.Medium,false)
	defer ar.run_destroy(&run)
	testing.expect(t,!run.story_runtime.initialized,"story off must keep narrative delivery disabled")
	testing.expect(t,ar.story_content_enabled(&run),"story off must retain the shared gameplay-content runtime")
	testing.expect(t,!run.story_runtime.requests.omen,"ordinary story-off floors must not queue omen panels")
	quest,quest_found:=ar.special_room_for_kind(&run.dungeon,.Quest)
	guest:=ar.story_current_guest(&run)
	testing.expect(t,quest_found&&guest!=nil,"story-off floors must retain Quest rooms and their NPCs")
	if quest_found&&guest!=nil {
		_,room_index,found:=ar.dungeon_room_at_point(&run.dungeon,guest.pos.x,guest.pos.y)
		testing.expect(t,found&&room_index==quest.room_index,"story-off NPC must remain inside its Quest room")
		testing.expect(t,guest.resolved&&!guest.ally&&guest.alive,
			"story-off NPC must be a friendly non-interactive idler")
		run.player.pos=guest.pos
		run.player.prev_pos=guest.pos
		ar.refresh_visibility(&run)
		testing.expect(t,ar.story_nearby_guest(&run)==nil,
			"story-off idler must not offer narrative dialogue")
	}
	testing.expect(t,run.story_runtime.relic.present&&run.story_runtime.relic.guidance,
		"story off must place an Aid relic")
	_,enabled:=ar.story_route_target(&run)
	testing.expect(t,!enabled&&!run.player.guidance_wave_active&&len(run.story_runtime.guidance_path)==0,
		"story-off guidance must stay hidden until the first relic is recovered")

	// The final stairs still claim victory directly instead of opening the epilogue.
	run.depth=ar.DUNGEON_DEPTH
	ar.run_regenerate_floor(&run,boss_arena=true)
	for &enemy in run.enemies do enemy.hp=0
	stairs:=run.dungeon.stairs
	run.player.pos={f32(stairs.x)+.5,f32(stairs.y)+.5}
	floor_changed:=ar.player_interact(&run)
	testing.expect(t,!floor_changed&&run.victory,"story-off final stairs must claim victory directly")
	testing.expect(t,!run.story_runtime.requests.epilogue,"story off must never queue the epilogue")
}

@(test)
story_disabled_runs_keep_bar_garden_and_moonbloom :: proc(t:^testing.T) {
	bar_seen,garden_seen:=false,false
	garden_seed:u64
	for seed in 1..=64 {
		run:ar.Run
		ar.run_start(&run,u64(seed),.Warden,.Medium,false)
		_,has_bar:=ar.special_room_for_kind(&run.dungeon,.Bar)
		_,has_garden:=ar.special_room_for_kind(&run.dungeon,.Garden)
		bar_seen=bar_seen||has_bar
		garden_seen=garden_seen||has_garden
		if has_garden&&garden_seed==0 do garden_seed=u64(seed)
		ar.run_destroy(&run)
	}
	testing.expect(t,bar_seen&&garden_seen,"story-off generation must retain Bar and Garden rolls")
	if garden_seed==0 do return

	app:ar.App
	ar.app_init(&app,78001)
	defer ar.run_destroy(&app.run)
	ar.run_start(&app.run,garden_seed,.Warden,.Medium,false)
	app.mode=.Playing
	frog_pos:ar.Vec2
	frog_found:=false
	for i in 0..<app.run.ambient_residents.count {
		frog:=&app.run.ambient_residents.items[i]
		if frog.active&&frog.kind==.Garden_Frog {frog_pos=frog.pos;frog_found=true;break}
	}
	testing.expect(t,frog_found,"story-off Garden must retain its frog")
	if !frog_found do return
	app.run.player.pos=frog_pos
	app.run.player.prev_pos=frog_pos
	ar.refresh_visibility(&app.run)
	testing.expect(t,ar.story_request_garden_moonbloom(&app.run),"story-off frog must request Moonbloom")
	testing.expect(t,ar.app_story_process_requests(&app),"story-off Moonbloom request must open its minigame")
	testing.expect(t,app.story_minigame.active&&app.story_minigame.kind==.Wake_The_Moonbloom&&!app.story_panel.active,
		"Moonbloom must run without a narrative panel")
}

@(test)
story_disabled_bind_floor_runs_minigame_then_places_relic :: proc(t:^testing.T) {
	app:ar.App
	ar.app_init(&app,78002)
	defer ar.run_destroy(&app.run)
	ar.run_start(&app.run,ar.derive_seed(78002,0),.Rogue,.Medium,false)
	app.mode=.Playing
	app.run.depth=5
	ar.run_regenerate_floor(&app.run,boss_arena=false)
	testing.expect(t,app.run.story_runtime.requests.omen&&!app.run.story_runtime.relic.present,
		"story-off Bind floor must defer relic placement to the minigame")
	testing.expect(t,ar.app_story_process_requests(&app,include_omen=true),"story-off Bind request was not processed")
	testing.expect(t,app.story_minigame.active&&app.story_minigame.kind==.Bind_The_Page&&!app.story_panel.active,
		"Bind the Page must start directly without an omen panel")
	app.story_minigame.phase=.Result
	app.story_minigame.outcome=.Won
	testing.expect(t,ar.app_story_finalize_minigame(&app),"story-off Bind result did not finalize")
	testing.expect(t,app.run.story_runtime.relic.present&&app.run.story_runtime.relic_records[4].path==.Aid,
		"Bind completion must place the story-off Aid relic")
}

@(test)
story_disabled_hall_starts_and_finishes_soul_hunt_without_panels :: proc(t:^testing.T) {
	app:ar.App
	ar.app_init(&app,78003)
	defer ar.run_destroy(&app.run)
	ar.run_start(&app.run,ar.derive_seed(78003,0),.Acolyte,.Medium,false)
	app.mode=.Playing
	app.run.depth=7
	app.run.story_runtime.hall.seen=false
	ar.run_regenerate_floor(&app.run,boss_arena=false)
	_,has_hall:=ar.special_room_for_kind(&app.run.dungeon,.Hall_Of_Unlost_Echoes)
	testing.expect(t,has_hall&&app.run.story_runtime.soul.present,
		"story-off depth seven must guarantee a populated Soul room")
	if !app.run.story_runtime.soul.present do return
	app.run.player.pos=app.run.story_runtime.soul.pos
	app.run.player.prev_pos=app.run.player.pos
	ar.refresh_visibility(&app.run)
	testing.expect(t,ar.story_request_lossless_soul(&app.run),"story-off Soul must remain interactable")
	testing.expect(t,ar.app_story_process_requests(&app),"story-off Soul request did not start its hunt")
	testing.expect(t,app.run.story_runtime.hall.verdict==.Release&&ar.app_story_soul_hunt_active(&app)&&!app.story_panel.active,
		"Soul interaction must enter Chase the Mistbound directly")
	app.story_minigame.phase=.Result
	app.story_minigame.outcome=.Won
	testing.expect(t,ar.app_story_finalize_minigame(&app),"story-off Soul hunt result did not finalize")
	testing.expect(t,app.run.story_runtime.soul_games[6].outcome==.Won&&!app.story_panel.active,
		"story-off Soul hunt must finish without a settled-story panel")
}

@(test)
story_enabled_default_still_initializes_the_story_runtime :: proc(t:^testing.T) {
	run:ar.Run
	ar.run_start(&run,ar.derive_seed(77002,0),.Warden)
	defer ar.run_destroy(&run)
	testing.expect(t,run.story_runtime.initialized,"the default run keeps the full story layer")
	testing.expect(t,run.story_runtime.requests.omen,"depth 1 owes its omen panel")
}

@(test)
story_disabled_run_survives_a_save_round_trip :: proc(t:^testing.T) {
	source:ar.App
	ar.app_init(&source,4245)
	defer ar.run_destroy(&source.run)
	source.options.story_enabled=false
	ar.app_begin_new_run(&source,.Warden)
	testing.expect(t,!source.run.story_runtime.initialized&&ar.story_content_enabled(&source.run))
	data,encoded:=ar.persistence_encode_run(&source,3,"2026-08-30T00:00:00Z")
	testing.expect(t,encoded,"story-off run must encode")
	defer delete(data)
	document,status:=ar.persistence_decode_run(data)
	testing.expect(t,status==.Valid,"story-off run must decode as valid")
	defer ar.run_document_destroy(&document)
	restored:ar.App
	ar.app_init(&restored,4246)
	defer ar.run_destroy(&restored.run)
	testing.expect(t,ar.app_install_run_document(&restored,&document))
	testing.expect(t,!restored.run.story_runtime.initialized,"restore must not resurrect narrative delivery")
	testing.expect(t,ar.story_content_enabled(&restored.run)&&restored.run.story_runtime.relic.present,
		"restore must retain story-off rooms, relics, and minigame state")
	quest,quest_found:=ar.special_room_for_kind(&restored.run.dungeon,.Quest)
	guest:=ar.story_current_guest(&restored.run)
	testing.expect(t,quest_found&&guest!=nil,"restore must retain the story-off Quest room and NPC")
	if quest_found&&guest!=nil {
		_,room_index,found:=ar.dungeon_room_at_point(&restored.run.dungeon,guest.pos.x,guest.pos.y)
		testing.expect(t,found&&room_index==quest.room_index&&guest.resolved&&!guest.ally&&guest.alive,
			"restored Quest NPC must remain a friendly non-interactive idler")
	}
}

@(test)
legacy_story_disabled_save_enables_content_without_rebuilding_floor :: proc(t:^testing.T) {
	source:ar.App
	ar.app_init(&source,4247)
	defer ar.run_destroy(&source.run)
	source.options.story_enabled=false
	ar.app_begin_new_run(&source,.Ranger)
	dungeon_before:=source.run.dungeon
	ar.story_run_destroy(&source.run) // exact pre-content-split Story Off shape
	testing.expect(t,!ar.story_content_enabled(&source.run),"legacy fixture must have an empty content runtime")
	data,encoded:=ar.persistence_encode_run(&source,4,"2026-08-30T00:00:00Z")
	testing.expect(t,encoded,"legacy story-off fixture must encode")
	defer delete(data)
	document,status:=ar.persistence_decode_run(data)
	testing.expect(t,status==.Valid,"legacy story-off fixture must decode")
	defer ar.run_document_destroy(&document)

	restored:ar.App
	ar.app_init(&restored,4248)
	defer ar.run_destroy(&restored.run)
	testing.expect(t,ar.app_install_run_document(&restored,&document),"legacy story-off fixture must install")
	testing.expect(t,!restored.run.story_runtime.initialized&&ar.story_content_enabled(&restored.run),
		"legacy restore must enable mechanics without enabling narrative")
	testing.expect(t,restored.run.dungeon==dungeon_before,
		"legacy content upgrade must not rebuild or mutate the saved floor")
	testing.expect(t,restored.run.story_runtime.relic.present,
		"legacy content upgrade must place the current floor relic")

	ar.run_descend(&restored.run)
	_,quest_found:=ar.special_room_for_kind(&restored.run.dungeon,.Quest)
	guest:=ar.story_current_guest(&restored.run)
	testing.expect(t,quest_found&&guest!=nil,
		"the first post-upgrade floor must resume story-off Quest generation")
	if guest!=nil {
		testing.expect(t,guest.resolved&&!guest.ally&&guest.alive,
			"the post-upgrade Quest NPC must be a friendly non-interactive idler")
	}
}
