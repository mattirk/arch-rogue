package archrogue_tests

// STEAM.md S1/S2 coverage: the achievement catalogue contract, the evaluation
// funnel, profile schema-2 aggregates and their v1 migration, the run schema-2
// migration, the durable offline queue, and the facade driven end to end
// against an injected fake flat-API symbol table (the rewrite's equivalent of
// pygame's fake-SDK suite; the real library remains a manual verification).

import "core:encoding/json"
import "core:fmt"
import "core:os"
import filepath "core:path/filepath"
import "core:strings"
import "core:sync"
import "core:testing"
import ar "../src"

// --- Fixtures ----------------------------------------------------------------

@(private="file")
steam_start_app :: proc(seed:u64)->ar.App {
	app:ar.App
	ar.app_init(&app,seed)
	profile_id:=fmt.aprintf("steam-profile-%d",seed)
	ar.profile_init(&app.profile,profile_id)
	delete(profile_id)
	ar.app_apply(&app,ar.Intent{menu_index=int(ar.Title_Action.New_Run),menu_index_valid=true,confirm=true})
	ar.app_apply(&app,ar.Intent{confirm=true})
	ar.app_story_panel_reveal(&app)
	ar.app_apply(&app,ar.Intent{confirm=true})
	app.persistence_request=.None
	return app
}

@(private="file")
steam_destroy_app :: proc(app:^ar.App) {
	if app==nil do return
	ar.run_destroy(&app.run)
	ar.profile_destroy(&app.profile)
}

@(private="file")
steam_temp_dir :: proc(t:^testing.T)->(string,bool) {
	dir,err:=os.make_directory_temp("","arch-rogue-steam-*",context.allocator)
	testing.expect(t,err==nil,"temp dir must be creatable")
	return dir,err==nil
}

@(private="file")
steam_expected_api_ids := [39]string{
	"ACH_DEPTH_3","ACH_DEPTH_5","ACH_DEPTH_8","ACH_DEPTH_10",
	"ACH_FIRST_CLEAR","ACH_CLEARS_10","ACH_CLEAR_HARD","ACH_CLEAR_HELL",
	"ACH_CLEAR_WARDEN","ACH_CLEAR_ROGUE","ACH_CLEAR_ARCANIST","ACH_CLEAR_ACOLYTE","ACH_CLEAR_RANGER",
	"ACH_CLEAR_EVERY_ARCHETYPE",
	"ACH_BOSS_ASH_GALLOWS","ACH_BOSS_MYCELIAL_MATRON","ACH_BOSS_RIME_CHANTER","ACH_BOSS_VOID_SENTINEL","ACH_BOSS_GATE_TYRANT",
	"ACH_BOSS_BESTIARY",
	"ACH_GATE_AID","ACH_GATE_BARGAIN","ACH_GATE_DEFY","ACH_GATE_ALL_ANSWERS",
	"ACH_THEMES_ALL","ACH_MODIFIERS_ALL","ACH_LEGENDARY_10",
	"ACH_SECRETS_25","ACH_SHRINES_20","ACH_KILLS_1000","ACH_RUNS_50",
	"ACH_COOP_RUN","ACH_COOP_CLEAR",
	"ACH_DEPTH_1_DEATH","ACH_DRY_CLEAR","ACH_BAR_PILGRIM",
	"ACH_WALLFACER","ACH_ELITE_HUNTER","ACH_CHALLENGER",
}

@(private="file")
steam_literal_in_domain :: proc(fact:ar.Achievement_Fact,literal:string)->bool {
	switch fact {
	case .Victory_Difficulties:
		for id in ar.DIFFICULTY_SAVE_IDS do if id==literal do return true
	case .Victory_Archetypes:
		for id in ar.ARCHETYPE_SAVE_IDS do if id==literal do return true
	case .Bosses_Defeated:
		for id in ar.BOSS_SAVE_IDS do if id==literal do return true
	case .Story_Verbs:
		for id in ar.STORY_VERB_SAVE_IDS do if id==literal do return true
	case .Themes_Seen:
		for id in ar.THEME_SAVE_IDS do if id==literal do return true
	case .Modifiers_Seen:
		for id in ar.MODIFIER_SAVE_IDS do if id==literal do return true
	case .Uniques_Seen:
		for def in ar.UNIQUE_DEFS do if def.icon==literal do return true
	case .None,.Best_Depth,.Clears,.Runs_Started,.Lifetime_Kills,.Lifetime_Secrets,
		.Lifetime_Shrines,.Lifetime_Wall_Touches,.Coop_Clears,.Run_Is_Death,
		.Run_Is_Victory,.Run_Depth,.Run_Potions_Used,.Run_Elites_Killed,
		.Run_Challenge_Rooms,.Run_Bar_Pilgrim,.Run_Coop:
	}
	return false
}

// --- Catalogue contract ------------------------------------------------------

@(test)
steam_app_id_is_pinned :: proc(t:^testing.T) {
	// The shipped binary carries the App ID; a debug edit must not reach a
	// depot (pygame docs/steam.md kept the same guard).
	testing.expect_value(t,ar.STEAM_APP_ID,5031380)
}

@(test)
achievement_catalogue_matches_app_admin_contract :: proc(t:^testing.T) {
	testing.expect_value(t,len(ar.Achievement_Id),39)
	index:=0
	for id in ar.Achievement_Id {
		def:=ar.ACHIEVEMENT_DEFS[id]
		testing.expect(t,def.api_id==steam_expected_api_ids[index],
			fmt.tprintf("%v api id %s must match authored order entry %s",id,def.api_id,steam_expected_api_ids[index]))
		testing.expect(t,strings.has_prefix(def.api_id,"ACH_"),"api ids carry the ACH_ prefix contract")
		testing.expect(t,def.title!="","every achievement carries its App Admin title")
		testing.expect(t,def.description!="","every achievement carries its App Admin description")
		testing.expect(t,def.condition_count>=1&&def.condition_count<=len(def.conditions),"condition count bounded")
		for other in ar.Achievement_Id {
			if other!=id&&ar.ACHIEVEMENT_DEFS[other].api_id==def.api_id {
				testing.fail_now(t,"duplicate achievement api id")
			}
		}
		index+=1
	}
}

@(test)
achievement_triggers_read_real_facts_and_content :: proc(t:^testing.T) {
	profile:ar.Profile_State
	ar.profile_init(&profile,"contract")
	defer ar.profile_destroy(&profile)
	facts:=ar.Achievement_Facts{profile=&profile}
	for id in ar.Achievement_Id {
		def:=ar.ACHIEVEMENT_DEFS[id]
		for i in 0..<def.condition_count {
			condition:=def.conditions[i]
			testing.expect(t,condition.op!=.None,"conditions declare an operation")
			testing.expect(t,condition.fact!=.None,"conditions name a fact")
			switch condition.op {
			case .Counter_At_Least,.Counter_At_Most:
				// Counter facts must be readable; run facts only with a run.
				run_facts:=ar.Run_Terminal_Facts{depth=1}
				with_run:=ar.Achievement_Facts{profile=&profile,has_run=true,run=run_facts}
				_,ok:=ar.achievement_counter(&with_run,condition.fact)
				testing.expect(t,ok,fmt.tprintf("%v counter fact %v must be readable",id,condition.fact))
			case .Set_Contains:
				testing.expect(t,steam_literal_in_domain(condition.fact,condition.literal),
					fmt.tprintf("%v literal %q must exist in the %v content table",id,condition.literal,condition.fact))
			case .Set_Complete,.Set_Size_At_Least:
				ids,_,ok:=ar.achievement_set(&facts,condition.fact)
				testing.expect(t,ok,fmt.tprintf("%v set fact %v must be readable",id,condition.fact))
				if condition.op==.Set_Size_At_Least {
					testing.expect(t,condition.threshold<=len(ids),"size threshold within set capacity")
				}
			case .Flag_Set:
				// Flags evaluate without error by construction.
			case .None:
			}
		}
	}
	// Hidden flags are part of the authored App Admin contract: exactly the
	// six spoiler achievements (the four Gate answers, the depth-1 death,
	// and the Bar pilgrimage) are hidden.
	hidden_expected:=[6]ar.Achievement_Id{.Gate_Aid,.Gate_Bargain,.Gate_Defy,.Gate_All_Answers,.Depth_1_Death,.Bar_Pilgrim}
	for id in ar.Achievement_Id {
		expected:=false
		for hidden_id in hidden_expected do if id==hidden_id do expected=true
		testing.expect(t,ar.ACHIEVEMENT_DEFS[id].hidden==expected,
			fmt.tprintf("%v hidden flag must match the authored catalogue",id))
	}
	// Set capacities are the completion targets: pin them to the content tables.
	testing.expect_value(t,len(profile.victory_archetype_ids),len(ar.Archetype_Id))
	testing.expect_value(t,len(profile.victory_difficulty_ids),len(ar.Difficulty_Id))
	testing.expect_value(t,len(profile.lifetime_boss_ids),len(ar.Boss_Id))
	testing.expect_value(t,len(profile.story_verb_ids),len(ar.Story_Choice_Verb))
	testing.expect_value(t,len(profile.theme_ids_seen),len(ar.THEMES))
	testing.expect_value(t,len(profile.modifier_ids_seen),len(ar.Run_Modifier_Id))
	testing.expect_value(t,len(profile.unique_item_ids_seen),len(ar.UNIQUE_DEFS))
}

// --- Evaluation --------------------------------------------------------------

@(test)
achievement_retroactive_and_run_evaluation :: proc(t:^testing.T) {
	profile:ar.Profile_State
	ar.profile_init(&profile,"veteran")
	defer ar.profile_destroy(&profile)
	profile.best_depth=10
	profile.lifetime_victories=1
	profile.lifetime_started=3

	newly:[len(ar.Achievement_Id)]ar.Achievement_Id
	count:=ar.achievements_evaluate(&profile,false,{},&newly)
	granted:=make(map[ar.Achievement_Id]bool);defer delete(granted)
	for i in 0..<count do granted[newly[i]]=true
	testing.expect(t,granted[.Depth_3]&&granted[.Depth_5]&&granted[.Depth_8]&&granted[.Depth_10],
		"retroactive startup evaluation grants the whole depth ladder")
	testing.expect(t,granted[.First_Clear],"retroactive first clear")
	testing.expect(t,!granted[.Runs_50]&&!granted[.Clears_10],"unmet thresholds stay locked")
	testing.expect(t,!granted[.Depth_1_Death]&&!granted[.Dry_Clear],"run-fact conditions fail closed without a run")

	// Mark the depth ladder granted; re-evaluation must skip the cache.
	for id in ([4]ar.Achievement_Id{.Depth_3,.Depth_5,.Depth_8,.Depth_10}) {
		testing.expect(t,ar.profile_mark_achievement_granted(&profile,ar.ACHIEVEMENT_DEFS[id].api_id))
	}
	count=ar.achievements_evaluate(&profile,false,{},&newly)
	for i in 0..<count {
		testing.expect(t,newly[i]!=.Depth_3&&newly[i]!=.Depth_10,"granted cache is idempotent")
	}

	// A terminal run supplies the run-fact family.
	run_facts:=ar.Run_Terminal_Facts{
		outcome=.Victory,depth=10,potions_used=0,elites_killed=12,
		challenge_rooms_cleared=3,bar_pilgrim=true,
	}
	count=ar.achievements_evaluate(&profile,true,run_facts,&newly)
	clear(&granted)
	for i in 0..<count do granted[newly[i]]=true
	testing.expect(t,granted[.Dry_Clear],"victory with zero potions grants Sober Descent")
	testing.expect(t,granted[.Elite_Hunter]&&granted[.Challenger]&&granted[.Bar_Pilgrim],"run counters grant")
	testing.expect(t,!granted[.Depth_1_Death],"death-only achievement stays locked on victory")

	death_facts:=ar.Run_Terminal_Facts{outcome=.Fallen,depth=1,potions_used=2}
	count=ar.achievements_evaluate(&profile,true,death_facts,&newly)
	clear(&granted)
	for i in 0..<count do granted[newly[i]]=true
	testing.expect(t,granted[.Depth_1_Death],"depth-1 death grants That Was Fast")
	testing.expect(t,!granted[.Dry_Clear],"potion use blocks Sober Descent")
}

@(test)
achievement_coop_pair_stays_dormant :: proc(t:^testing.T) {
	// STEAM.md decision 1: the pair is authored but unearnable until the MP
	// milestone supplies co-op facts before release.
	profile:ar.Profile_State
	ar.profile_init(&profile,"maxed")
	defer ar.profile_destroy(&profile)
	profile.best_depth=10
	profile.lifetime_victories=100
	profile.lifetime_started=100
	profile.lifetime_kills=100000
	run_facts:=ar.Run_Terminal_Facts{outcome=.Victory,depth=10,bar_pilgrim=true,elites_killed=99,challenge_rooms_cleared=9}
	newly:[len(ar.Achievement_Id)]ar.Achievement_Id
	count:=ar.achievements_evaluate(&profile,true,run_facts,&newly)
	for i in 0..<count {
		testing.expect(t,newly[i]!=.Coop_Run&&newly[i]!=.Coop_Clear,"co-op achievements cannot fire without MP facts")
	}
}

@(test)
achievement_set_completion_paths :: proc(t:^testing.T) {
	profile:ar.Profile_State
	ar.profile_init(&profile,"collector")
	defer ar.profile_destroy(&profile)
	for id in ar.ARCHETYPE_SAVE_IDS do _=ar.profile_string_set_add(profile.victory_archetype_ids[:],&profile.victory_archetype_count,id)
	for id in ar.BOSS_SAVE_IDS do _=ar.profile_string_set_add(profile.lifetime_boss_ids[:],&profile.lifetime_boss_count,id)
	for id in ar.STORY_VERB_SAVE_IDS do _=ar.profile_string_set_add(profile.story_verb_ids[:],&profile.story_verb_count,id)
	for i in 0..<10 do _=ar.profile_string_set_add(profile.unique_item_ids_seen[:],&profile.unique_seen_count,ar.UNIQUE_DEFS[i].icon)
	newly:[len(ar.Achievement_Id)]ar.Achievement_Id
	count:=ar.achievements_evaluate(&profile,false,{},&newly)
	granted:=make(map[ar.Achievement_Id]bool);defer delete(granted)
	for i in 0..<count do granted[newly[i]]=true
	testing.expect(t,granted[.Clear_Every_Archetype],"all archetype victories complete the set")
	testing.expect(t,granted[.Boss_Bestiary],"full bestiary completes")
	testing.expect(t,granted[.Gate_All_Answers],"all verbs complete")
	testing.expect(t,granted[.Legendary_10],"ten distinct uniques satisfy the hoard")
	testing.expect(t,!granted[.Themes_All],"partial theme set stays locked")
}

// --- Terminal facts into aggregates -----------------------------------------

@(test)
profile_terminal_facts_update_aggregates :: proc(t:^testing.T) {
	profile:ar.Profile_State
	ar.profile_init(&profile,"aggregates")
	defer ar.profile_destroy(&profile)

	record:ar.Chronicle_Record
	record.outcome=.Victory
	record.difficulty=.Hard
	record.archetype=.Ranger
	record.run_modifier=.Blood_Moon
	record.secrets_opened=3
	record.shrines_used=2
	record.defeated_boss_ids[0]=strings.clone("gate_tyrant")
	record.defeated_boss_count=1
	record.visited_theme_ids[0]=strings.clone("crypt_of_ash")
	record.visited_theme_count=1
	record.notable_items[0]={item_id=strings.clone("named.emberbrand"),display_name=strings.clone("Emberbrand"),rarity=.Unique}
	record.notable_items[1]={item_id=strings.clone("common.sword"),display_name=strings.clone("Sword"),rarity=.Rare}
	record.notable_count=2
	defer ar.chronicle_record_destroy(&record)

	facts:=ar.Run_Terminal_Facts{outcome=.Victory,wall_touches=7,gate_verb=.Defy,gate_verb_valid=true}
	ar.profile_apply_terminal_facts(&profile,&record,&facts)
	ar.profile_apply_terminal_facts(&profile,&record,&facts) // union sets stay deduplicated

	testing.expect(t,ar.profile_string_set_contains(profile.victory_difficulty_ids[:],profile.victory_difficulty_count,"hard"))
	testing.expect(t,ar.profile_string_set_contains(profile.victory_archetype_ids[:],profile.victory_archetype_count,"ranger"))
	testing.expect(t,ar.profile_string_set_contains(profile.lifetime_boss_ids[:],profile.lifetime_boss_count,"gate_tyrant"))
	testing.expect(t,ar.profile_string_set_contains(profile.theme_ids_seen[:],profile.theme_seen_count,"crypt_of_ash"))
	testing.expect(t,ar.profile_string_set_contains(profile.modifier_ids_seen[:],profile.modifier_seen_count,"blood_moon"))
	testing.expect(t,ar.profile_string_set_contains(profile.story_verb_ids[:],profile.story_verb_count,"defy"))
	testing.expect_value(t,profile.victory_difficulty_count,1)
	testing.expect_value(t,profile.unique_seen_count,1)
	testing.expect(t,ar.profile_string_set_contains(profile.unique_item_ids_seen[:],profile.unique_seen_count,"named.emberbrand"))
	testing.expect_value(t,profile.lifetime_secrets,u64(6)) // applied twice by design of this test
	testing.expect_value(t,profile.lifetime_wall_touches,u64(14))
}

// --- Profile schema v2 + migration ------------------------------------------

@(test)
profile_v2_round_trip_preserves_steam_aggregates :: proc(t:^testing.T) {
	profile:ar.Profile_State
	ar.profile_init(&profile,"roundtrip")
	profile.lifetime_secrets=25
	profile.lifetime_wall_touches=100
	_=ar.profile_string_set_add(profile.victory_difficulty_ids[:],&profile.victory_difficulty_count,"hell")
	_=ar.profile_string_set_add(profile.granted_achievement_ids[:],&profile.granted_achievement_count,"ACH_DEPTH_3")
	data,encoded:=ar.persistence_encode_profile(&profile,4,"2026-08-21T10:00:00Z")
	testing.expect(t,encoded)
	decoded,revision,status:=ar.persistence_decode_profile(data)
	delete(data)
	testing.expect_value(t,status,ar.Persistence_Decode_Status.Valid)
	testing.expect_value(t,revision,u64(4))
	testing.expect(t,ar.profile_string_set_contains(decoded.victory_difficulty_ids[:],decoded.victory_difficulty_count,"hell"))
	testing.expect(t,ar.profile_achievement_granted(&decoded,"ACH_DEPTH_3"))
	testing.expect_value(t,decoded.lifetime_secrets,u64(25))
	testing.expect_value(t,decoded.lifetime_wall_touches,u64(100))
	ar.profile_destroy(&decoded)
	ar.profile_destroy(&profile)
}

@(test)
profile_v1_document_migrates_and_seeds_aggregates :: proc(t:^testing.T) {
	profile:ar.Profile_State
	ar.profile_init(&profile,"legacy")
	defer ar.profile_destroy(&profile)
	profile.lifetime_victories=1
	profile.best_depth=10
	record:ar.Chronicle_Record
	record.record_schema_version=ar.CHRONICLE_RECORD_SCHEMA_VERSION
	record.run_id=strings.clone("legacy-run-1")
	record.outcome=.Victory
	record.difficulty=.Hell
	record.archetype=.Warden
	record.run_modifier=.Elite_Hunt
	record.secrets_opened=4
	record.shrines_used=5
	record.deepest_floor=10
	record.defeated_boss_ids[0]=strings.clone("gate_tyrant")
	record.defeated_boss_count=1
	record.visited_theme_ids[0]=strings.clone("gate_of_night")
	record.visited_theme_count=1
	ending:=ar.STORY_ENDINGS[ar.Archetype_Id.Warden][ar.Story_Choice_Verb.Aid]
	record.story_ending_id=strings.clone(ending.slug)
	append(&profile.chronicle,record)

	// Render the v1 document exactly as alpha.23 would have written it: the
	// v2 payload marshal dropped onto the retained v1 shape (unknown fields
	// skip), hashed over that v1 marshal.
	v2_payload:=ar.profile_payload_from_profile(&profile)
	v2_bytes,v2_ok:=ar.persistence_marshal(v2_payload)
	testing.expect(t,v2_ok)
	v1_payload:ar.Profile_Payload_V1
	testing.expect(t,json.unmarshal(v2_bytes,&v1_payload)==nil)
	delete(v2_bytes)
	v1_bytes,v1_ok:=ar.persistence_marshal(v1_payload)
	testing.expect(t,v1_ok)
	hash:=ar.persistence_sha256(v1_bytes)
	delete(v1_bytes)
	document:=ar.Profile_Document_V1{
		schema_version=ar.PROFILE_DOCUMENT_SCHEMA_V1,
		game_release="6.0.0-alpha.20",
		document_id="legacy",
		revision=7,
		written_at_utc="2026-08-17T10:00:00Z",
		payload_sha256=hash,
		payload=v1_payload,
	}
	doc_bytes,doc_ok:=ar.persistence_marshal(document)
	delete(hash)
	// json.unmarshal allocated fresh strings for the fixture payload; free
	// them through the same ownership registry the decoder uses.
	fixture_owner:=ar.Profile_State{
		profile_id=v1_payload.profile_id,
		discovered_endings=v1_payload.discovered_endings,
		discovered_ending_count=v1_payload.discovered_ending_count,
		chronicle=v1_payload.chronicle,
		owns_strings=true,
	}
	ar.profile_destroy(&fixture_owner)
	testing.expect(t,doc_ok)

	migrated,revision,status:=ar.persistence_decode_profile(doc_bytes)
	delete(doc_bytes)
	testing.expect_value(t,status,ar.Persistence_Decode_Status.Migrated)
	testing.expect_value(t,revision,u64(7))
	defer ar.profile_destroy(&migrated)
	testing.expect(t,ar.profile_string_set_contains(migrated.victory_difficulty_ids[:],migrated.victory_difficulty_count,"hell"),
		"migration seeds victory difficulties from retained records")
	testing.expect(t,ar.profile_string_set_contains(migrated.victory_archetype_ids[:],migrated.victory_archetype_count,"warden"))
	testing.expect(t,ar.profile_string_set_contains(migrated.lifetime_boss_ids[:],migrated.lifetime_boss_count,"gate_tyrant"))
	testing.expect(t,ar.profile_string_set_contains(migrated.theme_ids_seen[:],migrated.theme_seen_count,"gate_of_night"))
	testing.expect(t,ar.profile_string_set_contains(migrated.modifier_ids_seen[:],migrated.modifier_seen_count,"elite_hunt"))
	testing.expect(t,ar.profile_string_set_contains(migrated.story_verb_ids[:],migrated.story_verb_count,"aid"),
		"gate verb derives from the recorded ending slug")
	testing.expect_value(t,migrated.lifetime_secrets,u64(4))
	testing.expect_value(t,migrated.lifetime_shrines,u64(5))
	testing.expect_value(t,migrated.granted_achievement_count,0)
}

// --- Run schema v2 + migration ----------------------------------------------

@(test)
run_v2_round_trip_preserves_steam_run_facts :: proc(t:^testing.T) {
	app:=steam_start_app(0x51EA0)
	defer steam_destroy_app(&app)
	app.run.potions_used=3
	app.run.elites_killed=11
	data,encoded:=ar.persistence_encode_run(&app,2,"2026-08-21T10:00:00Z")
	testing.expect(t,encoded)
	document,status:=ar.persistence_decode_run(data)
	delete(data)
	testing.expect_value(t,status,ar.Persistence_Decode_Status.Valid)
	testing.expect_value(t,document.payload.potions_used,3)
	testing.expect_value(t,document.payload.elites_killed,11)
	ar.run_document_destroy(&document)
}

@(test)
run_v1_document_migrates_with_zeroed_counters :: proc(t:^testing.T) {
	app:=steam_start_app(0x51EA1)
	defer steam_destroy_app(&app)
	app.run.kills=5
	app.run.potions_used=9 // must NOT leak into the v1 fixture
	data,encoded:=ar.persistence_encode_run(&app,3,"2026-08-21T10:00:00Z")
	testing.expect(t,encoded)
	v2_document,v2_status:=ar.persistence_decode_run(data)
	delete(data)
	testing.expect_value(t,v2_status,ar.Persistence_Decode_Status.Valid)

	v2_bytes,v2_ok:=ar.persistence_marshal(v2_document.payload)
	testing.expect(t,v2_ok)
	v1_payload:ar.Run_Save_Payload_V1
	testing.expect(t,json.unmarshal(v2_bytes,&v1_payload)==nil)
	delete(v2_bytes)
	v1_bytes,v1_ok:=ar.persistence_marshal(v1_payload)
	testing.expect(t,v1_ok)
	hash:=ar.persistence_sha256(v1_bytes)
	delete(v1_bytes)
	v1_document:=ar.Run_Document_V1{
		schema_version=ar.RUN_DOCUMENT_SCHEMA_V1,
		game_release="6.0.0-alpha.23",
		document_id=v2_document.run_id,
		run_id=v2_document.run_id,
		revision=3,
		written_at_utc="2026-08-21T10:00:00Z",
		payload_sha256=hash,
		payload=v1_payload,
	}
	doc_bytes,doc_ok:=ar.persistence_marshal(v1_document)
	delete(hash)
	testing.expect(t,doc_ok)
	// Free the fixture payload through the ownership registry.
	reclaimed:=ar.run_payload_from_v1(&v1_payload)
	ar.run_save_payload_destroy(&reclaimed)
	ar.run_document_destroy(&v2_document)

	migrated,status:=ar.persistence_decode_run(doc_bytes)
	delete(doc_bytes)
	testing.expect_value(t,status,ar.Persistence_Decode_Status.Migrated)
	testing.expect_value(t,migrated.schema_version,ar.RUN_DOCUMENT_SCHEMA_VERSION)
	testing.expect_value(t,migrated.payload.kills,5)
	testing.expect_value(t,migrated.payload.potions_used,0)
	testing.expect_value(t,migrated.payload.elites_killed,0)
	testing.expect(t,migrated.payload.terminal==.Active)
	ar.run_document_destroy(&migrated)
}

// --- Offline queue -----------------------------------------------------------

@(test)
steam_queue_survives_restart_and_dedupes :: proc(t:^testing.T) {
	dir,ok:=steam_temp_dir(t)
	if !ok do return
	defer {_=os.remove_all(dir);delete(dir)}
	state:ar.Steam_State
	ar.steam_attach_queue(&state,dir)
	testing.expect(t,ar.steam_queue_achievement(&state,"ACH_DEPTH_3"))
	testing.expect(t,ar.steam_queue_achievement(&state,"ACH_FIRST_CLEAR"))
	testing.expect(t,ar.steam_queue_achievement(&state,"ACH_DEPTH_3"),"duplicate queueing reports success without a second entry")
	testing.expect_value(t,len(state.queue),2)
	queue_path,join_err:=filepath.join([]string{dir,ar.STEAM_QUEUE_FILE_NAME},context.allocator)
	testing.expect(t,join_err==nil)
	defer delete(queue_path)
	testing.expect(t,os.exists(queue_path),"queue writes durably beside the primaries")
	ar.steam_shutdown(&state)

	reloaded:ar.Steam_State
	ar.steam_attach_queue(&reloaded,dir)
	testing.expect_value(t,len(reloaded.queue),2)
	testing.expect(t,reloaded.queue[0].id=="ACH_DEPTH_3")
	ar.steam_shutdown(&reloaded)

	// A corrupt queue file degrades to an empty queue; reconciliation against
	// the granted cache covers the loss.
	testing.expect(t,os.write_entire_file(queue_path,transmute([]byte)string("{not json"))==nil)
	corrupt:ar.Steam_State
	ar.steam_attach_queue(&corrupt,dir)
	testing.expect_value(t,len(corrupt.queue),0)
	ar.steam_shutdown(&corrupt)
}

// --- Facade against a fake flat-API table ------------------------------------

// Flat Steam callbacks do not carry user data, so this fake necessarily uses
// file-global state. Serialize its tests: Odin runs tests concurrently, and a
// parallel fake_reset would otherwise rewrite another test's active session.
@(private="file") fake_api_mutex:sync.Mutex
@(private="file") fake_run_callbacks_count:int
@(private="file") fake_store_count:int
@(private="file") fake_store_result:bool
@(private="file") fake_set_count:int
@(private="file") fake_set_names:[16][64]u8
@(private="file") fake_set_name_lens:[16]int
@(private="file") fake_stat_count:int
@(private="file") fake_achieved_response:bool
@(private="file") fake_init_count:int

@(private="file")
fake_copy_name :: proc "c" (name:cstring,slot:int) {
	if slot<0||slot>=16 do return
	length:=0
	raw:=([^]u8)(rawptr(name))
	for raw[length]!=0&&length<63 {
		fake_set_names[slot][length]=raw[length]
		length+=1
	}
	fake_set_name_lens[slot]=length
}

@(private="file") fake_init_flat :: proc "c" (err:^[1024]u8)->i32 {fake_init_count+=1;return 0}
@(private="file") fake_shutdown :: proc "c" () {}
@(private="file") fake_run_callbacks :: proc "c" () {fake_run_callbacks_count+=1}
@(private="file") fake_restart :: proc "c" (app_id:u32)->bool {return false}
@(private="file") fake_user_stats_accessor :: proc "c" ()->rawptr {return rawptr(uintptr(0xBEEF))}
@(private="file") fake_set_achievement :: proc "c" (self:rawptr,name:cstring)->bool {
	if fake_set_count<16 do fake_copy_name(name,fake_set_count)
	fake_set_count+=1
	return true
}
@(private="file") fake_get_achievement :: proc "c" (self:rawptr,name:cstring,achieved:^bool)->bool {
	achieved^=fake_achieved_response
	return true
}
@(private="file") fake_store_stats :: proc "c" (self:rawptr)->bool {fake_store_count+=1;return fake_store_result}
@(private="file") fake_set_stat :: proc "c" (self:rawptr,name:cstring,value:i32)->bool {fake_stat_count+=1;return true}

@(private="file")
fake_reset :: proc() {
	fake_run_callbacks_count=0;fake_store_count=0;fake_store_result=true
	fake_set_count=0;fake_stat_count=0;fake_achieved_response=true;fake_init_count=0
	fake_set_names={};fake_set_name_lens={}
}

@(private="file")
fake_set_name_at :: proc(slot:int)->string {
	if slot<0||slot>=16 do return ""
	return string(fake_set_names[slot][:fake_set_name_lens[slot]])
}

@(private="file")
fake_resolver :: proc(user:rawptr,name:string)->rawptr {
	switch name {
	case "SteamAPI_InitFlat": return rawptr(fake_init_flat)
	case "SteamAPI_Shutdown": return rawptr(fake_shutdown)
	case "SteamAPI_RunCallbacks": return rawptr(fake_run_callbacks)
	case "SteamAPI_RestartAppIfNecessary": return rawptr(fake_restart)
	case "SteamAPI_SteamUserStats_v013": return rawptr(fake_user_stats_accessor)
	case "SteamAPI_ISteamUserStats_SetAchievement": return rawptr(fake_set_achievement)
	case "SteamAPI_ISteamUserStats_GetAchievement": return rawptr(fake_get_achievement)
	case "SteamAPI_ISteamUserStats_StoreStats": return rawptr(fake_store_stats)
	case "SteamAPI_ISteamUserStats_SetStatInt32": return rawptr(fake_set_stat)
	}
	return nil
}

@(private="file")
fake_resolver_without_set :: proc(user:rawptr,name:string)->rawptr {
	if name=="SteamAPI_ISteamUserStats_SetAchievement" do return nil
	return fake_resolver(user,name)
}

@(test)
steam_facade_ready_flow_drains_queue :: proc(t:^testing.T) {
	sync.mutex_lock(&fake_api_mutex)
	defer sync.mutex_unlock(&fake_api_mutex)
	fake_reset()
	dir,ok:=steam_temp_dir(t)
	if !ok do return
	defer {_=os.remove_all(dir);delete(dir)}
	profile:ar.Profile_State
	ar.profile_init(&profile,"facade")
	defer ar.profile_destroy(&profile)

	state:ar.Steam_State
	state.app_id=ar.STEAM_APP_ID
	ar.steam_attach_queue(&state,dir)
	testing.expect(t,ar.steam_queue_achievement(&state,"ACH_DEPTH_3"))
	testing.expect(t,ar.steam_bind(&state,fake_resolver,nil),"full fake table binds")
	testing.expect(t,!ar.steam_initialize(&state),"fake init requests no restart")
	testing.expect_value(t,state.status,ar.Steam_Status.Ready)
	testing.expect_value(t,fake_init_count,1)

	state.status_logged=true // keep the shared test log quiet
	ar.steam_frame(&state,&profile)
	testing.expect(t,fake_run_callbacks_count>0,"the pump runs callbacks")
	testing.expect_value(t,len(state.queue),0)
	testing.expect(t,fake_set_count>=1,"queued unlock reached SetAchievement")
	testing.expect(t,fake_set_name_at(0)=="ACH_DEPTH_3")
	testing.expect(t,fake_store_count>=1,"StoreStats confirms the batch")
	testing.expect(t,fake_stat_count>=4,"the four authored stats publish on reconcile")
	ar.steam_shutdown(&state)
}

@(test)
steam_facade_keeps_queue_until_store_confirms :: proc(t:^testing.T) {
	sync.mutex_lock(&fake_api_mutex)
	defer sync.mutex_unlock(&fake_api_mutex)
	fake_reset()
	fake_store_result=false
	dir,ok:=steam_temp_dir(t)
	if !ok do return
	defer {_=os.remove_all(dir);delete(dir)}
	profile:ar.Profile_State
	ar.profile_init(&profile,"unconfirmed")
	defer ar.profile_destroy(&profile)
	state:ar.Steam_State
	ar.steam_attach_queue(&state,dir)
	testing.expect(t,ar.steam_queue_achievement(&state,"ACH_FIRST_CLEAR"))
	testing.expect(t,ar.steam_bind(&state,fake_resolver,nil))
	_=ar.steam_initialize(&state)
	state.status_logged=true
	ar.steam_frame(&state,&profile)
	testing.expect_value(t,len(state.queue),1)
	testing.expect(t,state.retry_frames>0,"failed store backs off before retrying")
	ar.steam_shutdown(&state)
}

@(test)
steam_facade_reports_missing_symbol :: proc(t:^testing.T) {
	sync.mutex_lock(&fake_api_mutex)
	defer sync.mutex_unlock(&fake_api_mutex)
	fake_reset()
	state:ar.Steam_State
	testing.expect(t,!ar.steam_bind(&state,fake_resolver_without_set,nil))
	testing.expect_value(t,state.status,ar.Steam_Status.Symbols_Missing)
	testing.expect(t,state.failing_symbol=="SteamAPI_ISteamUserStats_SetAchievement",
		"status names the exact failing symbol for fast diagnosis")
}

@(test)
steam_reconciliation_repushes_cached_grants :: proc(t:^testing.T) {
	// A profile that granted offline (or on another device via cloud sync)
	// re-pushes anything Steam does not report as achieved.
	sync.mutex_lock(&fake_api_mutex)
	defer sync.mutex_unlock(&fake_api_mutex)
	fake_reset()
	fake_achieved_response=false
	dir,ok:=steam_temp_dir(t)
	if !ok do return
	defer {_=os.remove_all(dir);delete(dir)}
	profile:ar.Profile_State
	ar.profile_init(&profile,"reconcile")
	defer ar.profile_destroy(&profile)
	testing.expect(t,ar.profile_mark_achievement_granted(&profile,"ACH_DEPTH_3"))
	testing.expect(t,ar.profile_mark_achievement_granted(&profile,"ACH_FIRST_CLEAR"))
	state:ar.Steam_State
	ar.steam_attach_queue(&state,dir)
	testing.expect(t,ar.steam_bind(&state,fake_resolver,nil))
	_=ar.steam_initialize(&state)
	state.status_logged=true
	ar.steam_frame(&state,&profile)
	testing.expect(t,fake_set_count>=2,"both cached grants re-push when Steam lacks them")
	ar.steam_shutdown(&state)
}

@(test)
persistence_apply_achievements_marks_cache_only_after_queue :: proc(t:^testing.T) {
	dir,ok:=steam_temp_dir(t)
	if !ok do return
	defer {_=os.remove_all(dir);delete(dir)}
	app:ar.App
	ar.app_init(&app,0xACE)
	ar.profile_init(&app.profile,"funnel")
	defer steam_destroy_app(&app)
	app.profile.best_depth=3

	// Without an attached queue the grant is not cached, so it re-evaluates
	// later instead of being lost (web/Android and failed-write behavior).
	dry:ar.Steam_State
	coordinator:=ar.Persistence_Coordinator{steam=&dry}
	testing.expect(t,!ar.persistence_apply_achievements(&coordinator,&app,false,{}))
	testing.expect(t,!ar.profile_achievement_granted(&app.profile,"ACH_DEPTH_3"))

	// With a durable queue the grant caches and the queue holds the push.
	state:ar.Steam_State
	ar.steam_attach_queue(&state,dir)
	coordinator.steam=&state
	testing.expect(t,ar.persistence_apply_achievements(&coordinator,&app,false,{}))
	testing.expect(t,ar.profile_achievement_granted(&app.profile,"ACH_DEPTH_3"))
	testing.expect_value(t,len(state.queue),1)
	testing.expect(t,!ar.persistence_apply_achievements(&coordinator,&app,false,{}),"second evaluation is idempotent")
	ar.steam_shutdown(&state)
}

@(test)
profile_merge_unions_steam_aggregates :: proc(t:^testing.T) {
	left:ar.Profile_State
	ar.profile_init(&left,"left")
	defer ar.profile_destroy(&left)
	right:ar.Profile_State
	ar.profile_init(&right,"right")
	defer ar.profile_destroy(&right)
	_=ar.profile_string_set_add(left.victory_archetype_ids[:],&left.victory_archetype_count,"warden")
	_=ar.profile_string_set_add(right.victory_archetype_ids[:],&right.victory_archetype_count,"rogue")
	_=ar.profile_string_set_add(right.granted_achievement_ids[:],&right.granted_achievement_count,"ACH_CLEAR_ROGUE")
	left.lifetime_wall_touches=10
	right.lifetime_wall_touches=40
	ar.profile_merge(&left,&right)
	testing.expect(t,ar.profile_string_set_contains(left.victory_archetype_ids[:],left.victory_archetype_count,"warden"))
	testing.expect(t,ar.profile_string_set_contains(left.victory_archetype_ids[:],left.victory_archetype_count,"rogue"))
	testing.expect(t,ar.profile_achievement_granted(&left,"ACH_CLEAR_ROGUE"))
	testing.expect_value(t,left.lifetime_wall_touches,u64(40))
}
