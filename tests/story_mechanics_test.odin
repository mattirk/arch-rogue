package archrogue_tests

// MX-story world consequences and interaction-priority regression coverage.

import "core:testing"
import ar "../src"

@(private = "file")
story_mechanics_run :: proc(seed:u64)->ar.Run {
	run:ar.Run
	ar.run_start(&run,ar.derive_seed(seed,0),.Warden)
	return run
}

@(test)
story_mechanics_relic_paths_are_separate_from_guest_choices :: proc(t:^testing.T) {
	run:=story_mechanics_run(61001)
	defer ar.run_destroy(&run)
	guest:=ar.story_current_guest(&run)
	testing.expect(t,guest!=nil,"fixture lost story guest")
	before:=run.story.beats[0].resolution
	testing.expect(t,ar.story_commit_relic_path(&run,.Bargain),"Bargain relic path must commit")
	record:=run.story_runtime.relic_records[0]
	testing.expect(t,record.path==.Bargain&&record.guidance&&record.guardian,"Bargain relic path traits changed")
	testing.expect(t,run.story.beats[0].resolution==before,"opening relic choice must not resolve the later guest dilemma")
	if guest!=nil do testing.expect(t,ar.story_resolve_guest_choice(&run,guest,.Aid),"guest Aid choice must resolve independently")
	testing.expect(t,run.story.beats[0].resolution==.Aid&&run.story_runtime.choices_resolved==1,"guest choice did not reach StoryEngine")
}

@(test)
story_mechanics_guidance_wave_starts_at_player_on_activation :: proc(t:^testing.T) {
	run:=story_mechanics_run(61009)
	defer ar.run_destroy(&run)
	run.player.guidance_idle_elapsed=19
	ar.story_set_guidance_wave_active(&run,true)
	testing.expect(t,run.player.guidance_wave_active&&run.player.guidance_idle_elapsed==0,"new guidance inherited stale idle time instead of starting at the player")
	run.player.guidance_idle_elapsed=2
	ar.story_set_guidance_wave_active(&run,true)
	testing.expect(t,run.player.guidance_idle_elapsed==2,"already-active guidance restarted without movement")
	ar.story_set_guidance_wave_active(&run,false)
	testing.expect(t,!run.player.guidance_wave_active&&run.player.guidance_idle_elapsed==0,"disabled guidance retained its crest clock")
}

@(test)
story_mechanics_relic_collection_and_aid_streak_control_guidance :: proc(t:^testing.T) {
	run:=story_mechanics_run(61002)
	defer ar.run_destroy(&run)
	testing.expect(t,ar.story_commit_relic_path(&run,.Aid),"Aid relic path failed")
	run.player.pos=run.story_runtime.relic.position
	testing.expect(t,ar.story_relic_nearby(&run)&&ar.story_request_relic_collection(&run),"nearby relic must win interaction priority")
	testing.expect(t,ar.story_collect_relic_echo(&run),"relic request must collect once")
	target,enabled:=ar.story_route_target(&run)
	stairs:=ar.Vec2{f32(run.dungeon.stairs.x)+.5,f32(run.dungeon.stairs.y)+.5}
	testing.expect(t,enabled&&target==stairs,"intact Aid streak must extend guidance to stairs")

	run.depth=2
	run.story_runtime.relic_records[1]={committed=true,path=.Bargain,collected=true,guidance=true,guidance_to_stairs=true}
	_,enabled=ar.story_route_target(&run)
	testing.expect(t,!enabled,"one Bargain must permanently break Aid-only stairs guidance")

	// Missing any earlier Aid relic also breaks the extension. Recovering a
	// later relic must not restore the arrow after the player left one behind.
	run.story_runtime.relic_records[0].collected=false
	run.story_runtime.relic_records[1].path=.Aid
	run.story_runtime.relic={depth=2,collected=true,guidance=true,guidance_to_stairs=true}
	_,enabled=ar.story_route_target(&run)
	testing.expect(t,!enabled,"a missed earlier relic must permanently break stairs guidance")
}

@(test)
story_mechanics_story_disabled_first_relic_unlocks_later_relic_guidance :: proc(t:^testing.T) {
	run:ar.Run
	ar.run_start(&run,ar.derive_seed(61010,0),.Warden,.Medium,false)
	defer ar.run_destroy(&run)
	target,enabled:=ar.story_route_target(&run)
	testing.expect(t,!enabled&&target=={}&&run.story_runtime.relic.present,
		"story-off depth one must not reveal its uncollected relic")
	run.player.pos=run.story_runtime.relic.position
	testing.expect(t,ar.story_collect_relic_echo(&run),"story-off relic must remain recoverable")
	target,enabled=ar.story_route_target(&run)
	stairs:=ar.Vec2{f32(run.dungeon.stairs.x)+.5,f32(run.dungeon.stairs.y)+.5}
	testing.expect(t,enabled&&target==stairs,"recovering the first story-off relic must reveal stairs guidance")

	ar.run_descend(&run)
	target,enabled=ar.story_route_target(&run)
	testing.expect(t,enabled&&target==run.story_runtime.relic.position,
		"an intact story-off streak must guide from the player to the next relic")
	path:=ar.story_relic_guidance_path(&run)
	testing.expect(t,run.player.guidance_wave_active&&len(path)>1,
		"later-floor relic guidance must build a visible world path")
	if len(path)>0 {
		player_tile:=[2]int{int(run.player.pos.x),int(run.player.pos.y)}
		relic_tile:=[2]int{int(run.story_runtime.relic.position.x),int(run.story_runtime.relic.position.y)}
		testing.expect(t,path[0]==player_tile&&path[len(path)-1]==relic_tile,
			"later-floor guidance path must connect the player and relic")
	}
	run.player.pos=run.story_runtime.relic.position
	testing.expect(t,ar.story_collect_relic_echo(&run),"guided later relic must remain recoverable")
	target,enabled=ar.story_route_target(&run)
	stairs=ar.Vec2{f32(run.dungeon.stairs.x)+.5,f32(run.dungeon.stairs.y)+.5}
	testing.expect(t,enabled&&target==stairs,
		"recovering a guided later relic must redirect guidance to its stairs")
}

@(test)
story_mechanics_story_disabled_missed_relic_breaks_guidance :: proc(t:^testing.T) {
	run:ar.Run
	ar.run_start(&run,ar.derive_seed(61011,0),.Warden,.Medium,false)
	defer ar.run_destroy(&run)
	run.player.pos=run.story_runtime.relic.position
	testing.expect(t,ar.story_collect_relic_echo(&run),"depth-one relic must unlock story-off guidance")
	ar.run_descend(&run)
	_,enabled:=ar.story_route_target(&run)
	testing.expect(t,enabled,"the unlocked arrow must guide to depth two's relic")

	// Leave depth two's relic behind. Depth three and every later floor must stay
	// unguided even if the player finds and recovers another relic unaided.
	ar.run_descend(&run)
	_,enabled=ar.story_route_target(&run)
	testing.expect(t,!enabled&&!run.player.guidance_wave_active&&len(run.story_runtime.guidance_path)==0,
		"leaving one guided relic undiscovered must remove the arrow")
	run.player.pos=run.story_runtime.relic.position
	testing.expect(t,ar.story_collect_relic_echo(&run),"later story-off relic must remain recoverable")
	_,enabled=ar.story_route_target(&run)
	testing.expect(t,!enabled,"one missed relic must permanently break story-off guidance")
}

@(test)
story_mechanics_guest_rewards_and_allies_are_consequential :: proc(t:^testing.T) {
	for verb in ar.Story_Choice_Verb {
		run:=story_mechanics_run(61100+u64(verb))
		guest:=ar.story_current_guest(&run)
		if guest==nil {testing.expect(t,false,"fixture lost guest");ar.run_destroy(&run);continue}
		hp_before:=run.player.hp
		xp_before:=run.player.xp
		enemies_before:=len(run.enemies)
		items_before:=len(run.ground_items)
		testing.expect(t,ar.story_resolve_guest_choice(&run,guest,verb),"guest choice failed")
		testing.expect(t,guest.resolved&&guest.ally&&guest.alive,"resolved guest must become a living ally")
		switch verb {
		case .Aid:
			testing.expect(t,run.player.hp>=hp_before&&len(run.shrines)>0,"Aid must restore and leave a mending refuge")
		case .Bargain:
			testing.expect(t,run.player.hp<=hp_before&&len(run.ground_items)>items_before,"Bargain must charge blood and pay equipment")
		case .Defy:
			testing.expect(t,run.player.xp>xp_before&&len(run.enemies)>enemies_before,"Defy must grant XP and call a hunter")
		}
		ar.run_destroy(&run)
	}
}

@(test)
story_mechanics_lossless_soul_verdicts_arm_keeper_and_liss :: proc(t:^testing.T) {
	run:=story_mechanics_run(61201)
	defer ar.run_destroy(&run)
	// Build a deterministic Hall fixture at act III without perturbing the story.
	run.depth=7
	run.dungeon.special_room_count=1
	run.dungeon.special_rooms_buf[0]={.Hall_Of_Unlost_Echoes,1}
	ar.story_populate_floor(&run)
	testing.expect(t,run.story_runtime.soul.present,"Hall must spawn the Lossless Soul")
	testing.expect(t,ar.story_resolve_lossless_soul(&run,.Preserve),"Soul Preserve verdict failed")
	testing.expect(t,run.story_runtime.soul.armed&&run.story_runtime.hall.verdict==.Preserve,"any settled verdict must arm the keeper")
	testing.expect(t,ar.story_true_name_known(&run.story,.Liss),"trusted act-III Soul verdict must reveal Liss")
	testing.expect(t,ar.story_effect(&run.story,.Healing_Echo)>.049,"Preserve must add its lasting healing echo")
	 testing.expect(t,!ar.story_resolve_lossless_soul(&run,.Release),"one Hall must not resolve twice")
}

@(test)
story_mechanics_floor_local_actors_do_not_leak_into_later_rooms :: proc(t:^testing.T) {
	run:=story_mechanics_run(61202)
	defer ar.run_destroy(&run)

	guest:=ar.story_current_guest(&run)
	quest,has_quest:=ar.special_room_for_kind(&run.dungeon,.Quest)
	testing.expect(t,guest!=nil&&has_quest,"story floor must place its guest in a Quest room")
	if guest!=nil&&has_quest {
		center:=ar.room_center(run.dungeon.rooms_buf[quest.room_index])
		expected:=ar.Vec2{f32(center.x)+.5,f32(center.y)+.5}
		testing.expect(t,guest.pos==expected&&guest.motion.room_index==quest.room_index,"guest fell back into an ordinary room")
		guest.resolved=true
		guest.ally=true
		guest.hp=max(guest.hp,1)
	}

	// Reproduce a Hall floor followed by a floor without one. The old Soul must
	// disappear instead of reusing its coordinates in the new dungeon.
	run.depth=7
	run.dungeon.special_room_count=1
	run.dungeon.special_rooms_buf[0]={.Hall_Of_Unlost_Echoes,1}
	ar.story_populate_floor(&run)
	testing.expect(t,run.story_runtime.soul.present,"Hall fixture did not spawn Soul")
	old_soul_pos:=run.story_runtime.soul.pos
	run.depth=8
	run.dungeon.special_room_count=0
	ar.story_populate_floor(&run)
	testing.expect(t,!run.story_runtime.soul.present,"prior-floor Soul leaked into a floor without a Hall")
	run.player.pos=old_soul_pos
	testing.expect(t,ar.story_nearby_lossless_soul(&run)==nil,"stale Soul remained interactable on the later floor")

	// A resolved guest from an earlier depth is historical state, not a hidden
	// combatant in the current floor's geometry.
	if guest!=nil {
		enemy:=ar.enemy_make(.Ghoul,guest.pos+ar.Vec2{1,0},run.depth)
		append(&run.enemies,enemy)
		guest_pos:=guest.pos
		enemy_hp:=run.enemies[len(run.enemies)-1].hp
		ar.story_tick_friendly_npc_combat(&run,1)
		testing.expect(t,guest.pos==guest_pos&&run.enemies[len(run.enemies)-1].hp==enemy_hp,"prior-floor guest moved or fought on the current floor")
	}
}

@(test)
story_mechanics_final_stairs_request_epilogue_without_legacy_victory :: proc(t:^testing.T) {
	run:=story_mechanics_run(61301)
	defer ar.run_destroy(&run)
	run.depth=ar.DUNGEON_DEPTH
	run.tyrant_dead=true
	clear(&run.enemies)
	s:=run.dungeon.stairs
	run.player.pos={f32(s.x)+.5,f32(s.y)+.5}
	testing.expect(t,ar.story_handle_final_stairs_request(&run),"story final stairs must consume interaction")
	testing.expect(t,run.story_runtime.requests.epilogue&&!run.victory,"final stairs must request epilogue, never grant victory")
	run.story_runtime.epilogue_stage=.Bell
	testing.expect(t,!ar.story_complete_bell_victory(&run),"bell cannot complete before the Gate is answered")
	testing.expect(t,ar.story_record_gate_choice(&run.story,.Defy),"Gate choice setup failed")
	testing.expect(t,ar.story_complete_bell_victory(&run)&&run.victory,"answered bell must complete victory")
}
