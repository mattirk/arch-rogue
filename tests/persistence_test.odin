package archrogue_tests

import "core:encoding/json"
import "core:fmt"
import "core:os"
import filepath "core:path/filepath"
import "core:strings"
import "core:testing"
import "core:time"
import ar "../src"

@(private="file")
mx_save_start_app :: proc(seed:u64)->ar.App {
	app:ar.App
	ar.app_init(&app,seed)
	profile_id:=fmt.aprintf("profile-%d",seed)
	ar.profile_init(&app.profile,profile_id)
	delete(profile_id)
	ar.app_apply(&app,ar.Intent{menu_index=int(ar.Title_Action.New_Run),menu_index_valid=true,confirm=true})
	ar.app_apply(&app,ar.Intent{confirm=true})
	// Commit the mandatory omen so both continuation branches run ordinary sim.
	ar.app_story_panel_reveal(&app)
	ar.app_apply(&app,ar.Intent{confirm=true})
	app.persistence_request=.None
	return app
}

@(private="file")
mx_save_destroy_app :: proc(app:^ar.App) {
	if app==nil do return
	ar.run_destroy(&app.run)
	ar.profile_destroy(&app.profile)
}

@(private="file")
mx_save_temp_paths :: proc(t:^testing.T)->(ar.Storage_Paths,bool) {
	dir,dir_err:=os.make_directory_temp("","arch-rogue-mx-save-*",context.allocator)
	testing.expect(t,dir_err==nil)
	if dir_err!=nil do return {},false
	options,options_err:=filepath.join([]string{dir,"options.json"},context.allocator)
	profile,profile_err:=filepath.join([]string{dir,"profile.json"},context.allocator)
	run,run_err:=filepath.join([]string{dir,"run.json"},context.allocator)
	if options_err!=nil||profile_err!=nil||run_err!=nil {
		testing.expect(t,false,"temporary persistence paths must be constructible")
		delete(options);delete(profile);delete(run)
		_=os.remove_all(dir);delete(dir)
		return {},false
	}
	return {directory=dir,options=options,profile=profile,run=run},true
}

@(private="file")
mx_save_cleanup_paths :: proc(paths:^ar.Storage_Paths) {
	if paths==nil do return
	if paths.directory!="" do _=os.remove_all(paths.directory)
	ar.storage_paths_destroy(paths)
}

@(private="file")
mx_save_cleanup_coordinator :: proc(coordinator:^ar.Persistence_Coordinator) {
	if coordinator==nil do return
	ar.save_worker_shutdown(&coordinator.worker)
	mx_save_cleanup_paths(&coordinator.paths)
	coordinator^={}
}

@(private="file")
mx_save_corrupt_artifact_count :: proc(directory:string)->int {
	files,read_err:=os.read_all_directory_by_path(directory,context.allocator)
	if read_err!=nil do return 0
	defer os.file_info_slice_delete(files,context.allocator)
	count:=0
	for file in files do if strings.contains(file.fullpath,".corrupt-") do count+=1
	return count
}

@(private="file")
mx_save_store_options :: proc(t:^testing.T,path:string,options:ar.Options,revision:u64)->bool {
	data,encoded:=ar.persistence_encode_options(options,revision,"2026-08-17T10:00:00Z")
	testing.expect(t,encoded)
	if !encoded do return false
	defer delete(data)
	stored:=ar.storage_write_document_durable(path,.Options,data)
	testing.expect(t,stored)
	return stored
}

@(private="file")
mx_save_store_profile :: proc(t:^testing.T,path:string,profile:^ar.Profile_State,revision:u64)->bool {
	data,encoded:=ar.persistence_encode_profile(profile,revision,"2026-08-17T10:00:00Z")
	testing.expect(t,encoded)
	if !encoded do return false
	defer delete(data)
	stored:=ar.storage_write_document_durable(path,.Profile,data)
	testing.expect(t,stored)
	return stored
}

@(private="file")
mx_save_store_run :: proc(t:^testing.T,path:string,app:^ar.App,revision:u64)->bool {
	data,encoded:=ar.persistence_encode_run(app,revision,"2026-08-17T10:00:00Z")
	testing.expect(t,encoded)
	if !encoded do return false
	defer delete(data)
	stored:=ar.storage_write_document_durable(path,.Run,data)
	testing.expect(t,stored)
	return stored
}

@(private="file")
mx_save_recovery_status :: proc(path:string,kind:ar.Persistence_Document_Kind)->ar.Persistence_Decode_Status {
	data,status:=ar.storage_recover_document(path,kind)
	delete(data)
	return status
}

@(private="file")
mx_save_profile_run_count :: proc(profile:^ar.Profile_State,run_id:string)->int {
	if profile==nil do return 0
	count:=0
	for record in profile.chronicle {if record.run_id==run_id do count+=1}
	return count
}

@(private="file")
mx_save_profile_has_ending :: proc(profile:^ar.Profile_State,ending_id:string)->bool {
	if profile==nil do return false
	for i in 0..<profile.discovered_ending_count {if profile.discovered_endings[i]==ending_id do return true}
	return false
}

@(private="file")
MX_Save_Terminal_Recovery_Point :: enum {
	Before_Marker,
	After_Marker,
	After_Profile_Write,
	Before_Run_Deletion,
}

@(private="file")
mx_save_expect_terminal_recovery :: proc(t:^testing.T,point:MX_Save_Terminal_Recovery_Point) {
	paths,paths_ok:=mx_save_temp_paths(t)
	if !paths_ok do return
	coordinator:=ar.Persistence_Coordinator{paths=paths,ready=true}
	defer mx_save_cleanup_coordinator(&coordinator)

	source:=mx_save_start_app(0xF100+u64(point))
	defer mx_save_destroy_app(&source)
	recovered:ar.App
	ar.app_init(&recovered,0xF200+u64(point))
	defer mx_save_destroy_app(&recovered)

	run_id:=strings.clone(source.run.run_id)
	defer delete(run_id)
	source.options.fullscreen=false
	source.options.audio_enabled=false
	source.run.kills=7
	before_marker:=point==.Before_Marker
	profile_precommitted:=point==.After_Profile_Write||point==.Before_Run_Deletion

	if !mx_save_store_options(t,coordinator.paths.options,source.options,3) do return
	if before_marker {
		if !mx_save_store_profile(t,coordinator.paths.profile,&source.profile,5) do return
		if !mx_save_store_run(t,coordinator.paths.run,&source,7) do return
		ar.app_request_terminal(&source,.Death)
		source.run.ended_at_utc=strings.clone("2026-08-17T10:05:00Z")
	} else {
		ar.app_request_terminal(&source,.Death)
		source.run.ended_at_utc=strings.clone("2026-08-17T10:05:00Z")
		switch point {
		case .After_Marker,.After_Profile_Write:
			source.run.finalization=.Terminal_Marker
		case .Before_Run_Deletion:
			source.run.finalization=.Profile_Committed
		case .Before_Marker:
		}
		if profile_precommitted {
			record:=ar.chronicle_record_from_run(&source.run,.Fallen)
			testing.expect(t,ar.profile_finalize_record(&source.profile,&record))
			ar.chronicle_record_destroy(&record)
		}
		if !mx_save_store_profile(t,coordinator.paths.profile,&source.profile,5) do return
		if !mx_save_store_run(t,coordinator.paths.run,&source,7) do return
	}
	source.persistence_request=.None
	coordinator.options_revision=3
	coordinator.profile_revision=5
	coordinator.run_revision=7

	target:^ar.App=&source
	if !before_marker {
		profile_data,profile_status:=ar.storage_recover_document(coordinator.paths.profile,.Profile)
		testing.expect(t,profile_status==.Valid)
		if profile_status!=.Valid {delete(profile_data);return}
		loaded_profile,profile_revision,profile_decoded:=ar.persistence_decode_profile(profile_data)
		delete(profile_data)
		testing.expect(t,profile_decoded==.Valid)
		if profile_decoded!=.Valid {ar.profile_destroy(&loaded_profile);return}
		recovered.profile=loaded_profile
		coordinator.profile_revision=profile_revision

		run_data,run_status:=ar.storage_recover_document(coordinator.paths.run,.Run)
		testing.expect(t,run_status==.Valid)
		if run_status!=.Valid {delete(run_data);return}
		document,run_decoded:=ar.persistence_decode_run(run_data)
		delete(run_data)
		testing.expect(t,run_decoded==.Valid)
		if run_decoded!=.Valid {ar.run_document_destroy(&document);return}
		installed:=ar.app_install_run_document(&recovered,&document)
		ar.run_document_destroy(&document)
		testing.expect(t,installed)
		if !installed do return
		coordinator.run_revision=recovered.run.revision
		target=&recovered
	}

	target.active_run_available=true
	target.mode=.Save_Wait
	target.persistence_request=.Finalize_Death
	ar.persistence_process_request(&coordinator,target)
	testing.expect(t,target.persistence_request==.None&&target.persistence_error==.None)
	testing.expect(t,target.mode==.Dead&&!target.active_run_available)

	profile_data,profile_status:=ar.storage_recover_document(coordinator.paths.profile,.Profile)
	testing.expect(t,profile_status==.Valid)
	if profile_status==.Valid {
		final_profile,_,decoded:=ar.persistence_decode_profile(profile_data)
		testing.expect(t,decoded==.Valid)
		if decoded==.Valid {
			testing.expect(t,len(final_profile.chronicle)==1)
			testing.expect(t,mx_save_profile_run_count(&final_profile,run_id)==1,"terminal recovery must commit exactly one Chronicle record")
			testing.expect(t,final_profile.lifetime_started==1&&final_profile.lifetime_descents==1)
			testing.expect(t,final_profile.lifetime_kills==7)
		}
		ar.profile_destroy(&final_profile)
	}
	delete(profile_data)

	options_data,options_status:=ar.storage_recover_document(coordinator.paths.options,.Options)
	testing.expect(t,options_status==.Valid)
	if options_status==.Valid {
		options,_,revision,decoded:=ar.persistence_decode_options(options_data)
		testing.expect(t,decoded==.Valid&&revision==3)
		testing.expect(t,!options.fullscreen&&!options.audio_enabled,"terminal finalization must preserve the options domain")
	}
	delete(options_data)

	testing.expect(t,mx_save_recovery_status(coordinator.paths.run,.Run)==.Missing)
	tmp:=ar.storage_artifact_path(coordinator.paths.run,"tmp");defer delete(tmp)
	bak:=ar.storage_artifact_path(coordinator.paths.run,"bak");defer delete(bak)
	testing.expect(t,!ar.storage_file_exists(coordinator.paths.run)&&!ar.storage_file_exists(tmp)&&!ar.storage_file_exists(bak))
}

@(test)
mx_save_sha256_matches_fips_vectors :: proc(t:^testing.T) {
	vectors := [?]struct{source, expected: string}{
		{"", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"},
		{"abc", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"},
		{
			"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq",
			"248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1",
		},
		{
			"abcdefghbcdefghicdefghijdefghijkefghijklfghijklmghijklmn" +
				"hijklmnoijklmnopjklmnopqklmnopqrlmnopqrsmnopqrstnopqrstu",
			"cf5b16a778af8380036ce59e7b0492370b249b11e8f07a51afac45037afee9d1",
		},
	}
	for vector in vectors {
		actual := ar.persistence_sha256(transmute([]byte)(vector.source))
		testing.expectf(t, actual == vector.expected, "persistence checksum mismatch: expected %s, got %s", vector.expected, actual)
		delete(actual)
	}
}

@(test)
mx_save_legacy_options_migrate_hell_to_profile_seam :: proc(t:^testing.T) {
	legacy:=ar.legacy_options_default()
	legacy.fullscreen=false
	legacy.frame_rate_cap=.FPS_120
	legacy.view_zoom=3.25
	legacy.difficulty=.Hell
	legacy.hell_unlocked=true
	legacy.audio_enabled=false
	data,marshal_err:=json.marshal(legacy,allocator=context.allocator)
	testing.expect(t,marshal_err==nil)
	defer delete(data)
	options,legacy_hell,revision,status:=ar.persistence_decode_options(data)
	testing.expect(t,status==.Migrated&&legacy_hell&&revision==0)
	testing.expect(t,!options.fullscreen&&options.frame_rate_cap==.FPS_120&&options.difficulty==.Hell&&!options.audio_enabled)

	profile:ar.Profile_State
	ar.profile_init(&profile,"legacy-profile")
	defer ar.profile_destroy(&profile)
	if legacy_hell do profile.hell_unlocked=true
	testing.expect(t,profile.hell_unlocked,"legacy Hell unlock must have a one-way profile import seam")
}

@(test)
mx_save_options_envelope_is_semantic_checksummed_and_future_safe :: proc(t:^testing.T) {
	options:=ar.options_default()
	options.difficulty=.Hard
	_=ar.controller_remap_button(&options.gamepad_mapping,.X,.Ability_6)
	data,ok:=ar.persistence_encode_options(options,42,"2026-08-17T10:00:00Z")
	testing.expect(t,ok)
	defer delete(data)
	text:=string(data)
	testing.expect(t,strings.contains(text,"\"difficulty_id\": \"hard\""))
	testing.expect(t,strings.contains(text,"\"command_id\": \"ability_6\""))
	testing.expect(t,!strings.contains(text,"hell_unlocked"))
	loaded,_,revision,status:=ar.persistence_decode_options(data)
	testing.expect(t,status==.Valid&&revision==42&&loaded==options)

	document:ar.Options_Document
	parse_err:=json.unmarshal(data,&document)
	testing.expect(t,parse_err==nil)
	document.payload.fullscreen=!document.payload.fullscreen // stale checksum
	tampered,tamper_err:=json.marshal(document,ar.persistence_json_options(),allocator=context.allocator)
	testing.expect(t,tamper_err==nil)
	_,_,_,tamper_status:=ar.persistence_decode_options(tampered)
	testing.expect(t,tamper_status==.Corrupt,"payload mutation must be caught by SHA-256")
	delete(tampered)
	document.schema_version=ar.OPTIONS_DOCUMENT_SCHEMA_VERSION+1
	future,future_err:=json.marshal(document,ar.persistence_json_options(),allocator=context.allocator)
	testing.expect(t,future_err==nil)
	_,_,_,future_status:=ar.persistence_decode_options(future)
	testing.expect(t,future_status==.Future,"future options must be preserved as incompatible")
	delete(future)
	delete(document.game_release);delete(document.document_id);delete(document.written_at_utc);delete(document.payload_sha256)
	ar.options_payload_destroy(&document.payload)
}

@(test)
mx_save_profile_chronicle_deduplicates_retains_512_and_keeps_lifetime_totals :: proc(t:^testing.T) {
	profile:ar.Profile_State
	ar.profile_init(&profile,"retention-profile")
	defer ar.profile_destroy(&profile)
	for i in 0..<ar.CHRONICLE_MAX_RECORDS+1 {
		run_id:=fmt.aprintf("run-%04d",i)
		record:=ar.Chronicle_Record{
			record_schema_version=ar.CHRONICLE_RECORD_SCHEMA_VERSION,
			run_id=run_id,
			outcome=i%2==0?.Victory:.Fallen,
			archetype=ar.Archetype_Id(i%len(ar.Archetype_Id)),
			difficulty=ar.Difficulty_Id(i%len(ar.Difficulty_Id)),
			deepest_floor=1+i%ar.DUNGEON_DEPTH,
			final_level=1+i%12,
			kills=i,
		}
		testing.expect(t,ar.profile_finalize_record(&profile,&record))
		delete(run_id)
	}
	testing.expect(t,len(profile.chronicle)==ar.CHRONICLE_MAX_RECORDS)
	testing.expect(t,profile.lifetime_descents==u64(ar.CHRONICLE_MAX_RECORDS+1))
	testing.expect(t,profile.chronicle[0].run_id=="run-0001","oldest rich record must be pruned first")
	before:=profile.lifetime_descents
	testing.expect(t,!ar.profile_finalize_record(&profile,&profile.chronicle[len(profile.chronicle)-1]))
	testing.expect(t,profile.lifetime_descents==before,"duplicate run_id must not inflate lifetime totals")

	view:=ar.Chronicle_View_State{outcome=.Victories,archetype_filter=-1,difficulty_filter=-1}
	victories:=ar.chronicle_filtered_count(&profile,&view)
	testing.expect(t,victories>0&&victories<ar.CHRONICLE_MAX_RECORDS)
	newest:=ar.chronicle_record_at(&profile,&view,0)
	testing.expect(t,newest!=nil&&newest.outcome==.Victory,"queries must be newest-first")
}

@(test)
mx_save_busy_run_round_trip_restores_danger_story_and_rng :: proc(t:^testing.T) {
	source:=mx_save_start_app(0x5A7E)
	defer mx_save_destroy_app(&source)
	source.run.started_at_utc=strings.clone("2026-08-17T10:00:00Z")
	source.run.player.hp=max(2,source.run.player.max_hp-7)
	source.run.player.mana-=3
	source.run.player.bighit_charge=.41
	if len(source.run.enemies)>0 {
		enemy:=&source.run.enemies[0]
		enemy.windup=.33;enemy.windup_duration=.6;enemy.pending_ability=ar.PENDING_BASE_ATTACK
		enemy.windup_aim={1,0}
	}
	_=ar.player_cast_bolt(&source.run,{1,0})
	if len(source.run.traps)>0 {source.run.traps[0].revealed=true;source.run.traps[0].reveal_progress=.72}
	source.run.explored[int(source.run.player.pos.x)][int(source.run.player.pos.y)]=true
	loot_before,combat_before:=source.run.loot_rng,source.run.combat_rng
	data,encoded:=ar.persistence_encode_run(&source,9,"2026-08-17T10:01:00Z")
	testing.expect(t,encoded,"busy run must encode")
	defer delete(data)
	for projectile in source.run.projectiles do testing.expect(t,projectile.entity_id!=0)
	for trap in source.run.traps do testing.expect(t,trap.entity_id!=0)

	document,status:=ar.persistence_decode_run(data)
	testing.expect(t,status==.Valid&&document.revision==9)
	defer ar.run_document_destroy(&document)
	restored:ar.App
	ar.app_init(&restored,999)
	defer ar.run_destroy(&restored.run)
	testing.expect(t,ar.app_install_run_document(&restored,&document))
	testing.expect(t,restored.run.run_id==source.run.run_id&&restored.run.seed==source.run.seed)
	testing.expect(t,restored.run.player.hp==source.run.player.hp&&restored.run.player.bighit_charge==source.run.player.bighit_charge)
	testing.expect(t,len(restored.run.enemies)==len(source.run.enemies)&&len(restored.run.projectiles)==len(source.run.projectiles))
	testing.expect(t,restored.run.loot_rng==loot_before&&restored.run.combat_rng==combat_before)
	testing.expect(t,restored.run.visible[int(restored.run.player.pos.x)][int(restored.run.player.pos.y)])
	testing.expect(t,len(restored.run.sfx)==0&&len(restored.run.numbers)==0&&len(restored.run.feel)==0,"presentation queues must be rebuilt, not restored")
	if len(restored.run.enemies)>0 do testing.expect(t,restored.run.enemies[0].windup==source.run.enemies[0].windup,"committed enemy danger was cancelled")

	source.mode=.Playing;restored.mode=.Playing
	source.mouse_input_blocked=false;restored.mouse_input_blocked=false
	for _ in 0..<180 {ar.app_tick(&source);ar.app_tick(&restored)}
	testing.expect(t,restored.run.player.pos==source.run.player.pos&&restored.run.player.hp==source.run.player.hp)
	testing.expect(t,restored.run.loot_rng==source.run.loot_rng&&restored.run.combat_rng==source.run.combat_rng,"restored continuation drifted in RNG")
	testing.expect(t,len(restored.run.enemies)==len(source.run.enemies)&&len(restored.run.projectiles)==len(source.run.projectiles))
}

@(test)
mx_save_failed_restore_never_partially_mutates_app :: proc(t:^testing.T) {
	app:=mx_save_start_app(0xBAD5A7E)
	defer mx_save_destroy_app(&app)
	seed,depth,pos:=app.run.seed,app.run.depth,app.run.player.pos
	malformed:string="{\"schema_version\":1,\"run_id\":\"broken\"}"
	document,status:=ar.persistence_decode_run(transmute([]byte)(malformed))
	defer ar.run_document_destroy(&document)
	testing.expect(t,status==.Corrupt)
	testing.expect(t,!ar.app_install_run_document(&app,&document))
	testing.expect(t,app.run.seed==seed&&app.run.depth==depth&&app.run.player.pos==pos)
}

@(test)
mx_save_storage_prefers_highest_valid_temp_and_keeps_backup :: proc(t:^testing.T) {
	dir,dir_err:=os.make_directory_temp("","arch-rogue-mx-save-*",context.allocator)
	testing.expect(t,dir_err==nil)
	if dir_err!=nil do return
	defer {_=os.remove_all(dir);delete(dir)}
	path,path_err:=filepath.join([]string{dir,"options.json"},context.allocator)
	testing.expect(t,path_err==nil)
	if path_err!=nil do return
	defer delete(path)
	first:=ar.options_default();first.fullscreen=false
	first_data,first_ok:=ar.persistence_encode_options(first,1,"2026-08-17T10:00:00Z")
	testing.expect(t,first_ok)
	defer delete(first_data)
	testing.expect(t,ar.storage_write_document_durable(path,.Options,first_data))
	second:=first;second.audio_enabled=false
	second_data,second_ok:=ar.persistence_encode_options(second,2,"2026-08-17T10:01:00Z")
	testing.expect(t,second_ok)
	defer delete(second_data)
	tmp:=ar.storage_artifact_path(path,"tmp");defer delete(tmp)
	testing.expect(t,ar.storage_write_synced(tmp,second_data))
	recovered,status:=ar.storage_recover_document(path,.Options)
	testing.expect(t,status==.Valid)
	defer delete(recovered)
	loaded,_,revision,decoded:=ar.persistence_decode_options(recovered)
	testing.expect(t,decoded==.Valid&&revision==2&&!loaded.audio_enabled)
	bak:=ar.storage_artifact_path(path,"bak");defer delete(bak)
	testing.expect(t,ar.storage_file_exists(bak),"promotion must retain a last-known-good backup")
}

@(test)
mx_save_title_resume_abandon_and_veil_freeze_lifecycle :: proc(t:^testing.T) {
	app:ar.App
	ar.app_init(&app,71)
	defer ar.run_destroy(&app.run)
	testing.expect(t,app.title_index==int(ar.Title_Action.New_Run))
	app.title_index=int(ar.Title_Action.Resume)
	ar.app_apply(&app,ar.Intent{confirm=true})
	testing.expect(t,app.mode==.Title,"disabled Resume must not enter a load state")
	app.active_run_available=true
	ar.app_apply(&app,ar.Intent{confirm=true})
	testing.expect(t,app.mode==.Save_Wait&&app.persistence_request==.Resume)
	app.mode=.Title;app.persistence_request=.None;app.title_index=int(ar.Title_Action.New_Run)
	ar.app_apply(&app,ar.Intent{confirm=true})
	testing.expect(t,app.mode==.Abandon_Confirm,"New Run must not overwrite an active descent")
	ar.app_apply(&app,ar.Intent{menu_index=1,menu_index_valid=true,confirm=true})
	testing.expect(t,app.mode==.Save_Wait&&app.persistence_request==.Abandon)
	coordinator:=ar.Persistence_Coordinator{ready=true}
	ar.persistence_update_scheduler(&coordinator,&app,0)
	testing.expect(t,app.mode==.Save_Wait&&app.persistence_request==.Abandon,"critical save must wait until the progress overlay has rendered once")

	app.mode=.Resume_Veil
	app.run.arrival_timer=1
	app.run.wall_face_timer=1
	ar.app_tick(&app)
	testing.expect(t,app.run.arrival_timer==1&&app.run.wall_face_timer==1,"continue veil must freeze restored presentation and simulation")
	ar.app_apply(&app,ar.Intent{confirm=true})
	testing.expect(t,app.mode==.Playing)
}

@(test)
mx_save_terminal_finalization_recovers_idempotently_at_each_commit_boundary :: proc(t:^testing.T) {
	mx_save_expect_terminal_recovery(t,.Before_Marker)
	mx_save_expect_terminal_recovery(t,.After_Marker)
	mx_save_expect_terminal_recovery(t,.After_Profile_Write)
	mx_save_expect_terminal_recovery(t,.Before_Run_Deletion)
}

@(test)
mx_save_profile_merge_unions_progress_without_duplicate_runs :: proc(t:^testing.T) {
	destination:ar.Profile_State
	ar.profile_init(&destination,"local-profile")
	defer ar.profile_destroy(&destination)
	incoming:ar.Profile_State
	ar.profile_init(&incoming,"cloud-profile")

	local_shared:=ar.Chronicle_Record{
		record_schema_version=ar.CHRONICLE_RECORD_SCHEMA_VERSION,
		run_id="run-shared",outcome=.Fallen,deepest_floor=3,kills=2,
	}
	local_only:=ar.Chronicle_Record{
		record_schema_version=ar.CHRONICLE_RECORD_SCHEMA_VERSION,
		run_id="run-local",outcome=.Fallen,deepest_floor=4,kills=4,
	}
	cloud_shared:=ar.Chronicle_Record{
		record_schema_version=ar.CHRONICLE_RECORD_SCHEMA_VERSION,
		run_id="run-shared",outcome=.Victory,deepest_floor=9,kills=99,
	}
	cloud_only:=ar.Chronicle_Record{
		record_schema_version=ar.CHRONICLE_RECORD_SCHEMA_VERSION,
		run_id="run-cloud",outcome=.Fallen,deepest_floor=8,kills=8,
	}
	testing.expect(t,ar.profile_finalize_record(&destination,&local_shared))
	testing.expect(t,ar.profile_finalize_record(&destination,&local_only))
	testing.expect(t,ar.profile_finalize_record(&incoming,&cloud_shared))
	testing.expect(t,ar.profile_finalize_record(&incoming,&cloud_only))
	ar.profile_record_ending(&destination,"ending-local")
	ar.profile_record_ending(&incoming,"ending-local")
	ar.profile_record_ending(&incoming,"ending-cloud")

	destination.run_sequence=4
	destination.lifetime_started=10
	destination.lifetime_descents=5
	destination.lifetime_victories=1
	destination.lifetime_kills=40
	destination.best_depth=4
	incoming.hell_unlocked=true
	incoming.run_sequence=7
	incoming.lifetime_started=9
	incoming.lifetime_descents=9
	incoming.lifetime_victories=3
	incoming.lifetime_kills=30
	incoming.best_depth=8

	ar.profile_merge(&destination,&incoming)
	testing.expect(t,destination.profile_id=="local-profile","merge must preserve the local profile identity")
	testing.expect(t,destination.hell_unlocked&&destination.run_sequence==7)
	testing.expect(t,destination.lifetime_started==10&&destination.lifetime_descents==9)
	testing.expect(t,destination.lifetime_victories==3&&destination.lifetime_kills==40&&destination.best_depth==8)
	testing.expect(t,destination.discovered_ending_count==2)
	testing.expect(t,mx_save_profile_has_ending(&destination,"ending-local")&&mx_save_profile_has_ending(&destination,"ending-cloud"))
	testing.expect(t,len(destination.chronicle)==3)
	testing.expect(t,mx_save_profile_run_count(&destination,"run-shared")==1)
	testing.expect(t,mx_save_profile_run_count(&destination,"run-local")==1)
	testing.expect(t,mx_save_profile_run_count(&destination,"run-cloud")==1)

	ar.profile_destroy(&incoming)
	testing.expect(t,mx_save_profile_run_count(&destination,"run-cloud")==1,"merged records must own their strings")
	data,encoded:=ar.persistence_encode_profile(&destination,12,"2026-08-17T10:00:00Z")
	testing.expect(t,encoded)
	if !encoded do return
	defer delete(data)
	loaded,revision,status:=ar.persistence_decode_profile(data)
	defer ar.profile_destroy(&loaded)
	testing.expect(t,status==.Valid&&revision==12)
	testing.expect(t,loaded.profile_id=="local-profile"&&len(loaded.chronicle)==3)
	testing.expect(t,mx_save_profile_run_count(&loaded,"run-shared")==1)
}

@(test)
mx_save_profile_size_budget_accepts_limit_rejects_overflow_and_preserves_primary :: proc(t:^testing.T) {
	profile:ar.Profile_State
	ar.profile_init(&profile,"budget-profile")
	defer ar.profile_destroy(&profile)
	ar.profile_record_ending(&profile,"ending-budget")
	encoded,ok:=ar.persistence_encode_profile(&profile,22,"2026-08-17T10:00:00Z")
	testing.expect(t,ok&&len(encoded)<ar.PERSISTENCE_PROFILE_MAX_BYTES)
	if !ok||len(encoded)>=ar.PERSISTENCE_PROFILE_MAX_BYTES {delete(encoded);return}
	defer delete(encoded)

	at_limit:=make([]byte,ar.PERSISTENCE_PROFILE_MAX_BYTES)
	defer delete(at_limit)
	for i in 0..<len(at_limit) do at_limit[i]=u8(' ')
	copy(at_limit,encoded)
	loaded,revision,status:=ar.persistence_decode_profile(at_limit)
	testing.expect(t,status==.Valid&&revision==22)
	if status==.Valid do testing.expect(t,loaded.profile_id=="budget-profile")
	ar.profile_destroy(&loaded)

	over_limit:=make([]byte,ar.PERSISTENCE_PROFILE_MAX_BYTES+1)
	defer delete(over_limit)
	for i in 0..<len(over_limit) do over_limit[i]=u8(' ')
	copy(over_limit,encoded)
	over_profile,_,over_status:=ar.persistence_decode_profile(over_limit)
	ar.profile_destroy(&over_profile)
	testing.expect(t,over_status==.Oversize)

	paths,paths_ok:=mx_save_temp_paths(t)
	if !paths_ok do return
	defer mx_save_cleanup_paths(&paths)
	testing.expect(t,ar.storage_write_document_durable(paths.profile,.Profile,at_limit))
	testing.expect(t,!ar.storage_write_document_durable(paths.profile,.Profile,over_limit))
	recovered,recovery_status:=ar.storage_recover_document(paths.profile,.Profile)
	defer delete(recovered)
	testing.expect(t,recovery_status==.Valid)
	persisted,persisted_revision,persisted_status:=ar.persistence_decode_profile(recovered)
	defer ar.profile_destroy(&persisted)
	testing.expect(t,persisted_status==.Valid&&persisted_revision==22&&persisted.profile_id=="budget-profile")
}

@(test)
mx_save_storage_recovers_interrupted_artifacts_and_rejects_split_brain :: proc(t:^testing.T) {
	paths,paths_ok:=mx_save_temp_paths(t)
	if !paths_ok do return
	defer mx_save_cleanup_paths(&paths)
	first:=ar.options_default()
	first.fullscreen=false
	first.audio_enabled=false
	second:=first
	second.audio_enabled=true

	// A torn newer temp must not displace the valid primary.
	testing.expect(t,mx_save_store_options(t,paths.options,first,4))
	tmp:=ar.storage_artifact_path(paths.options,"tmp")
	defer delete(tmp)
	torn_temp:string="{\"schema_version\":"
	testing.expect(t,ar.storage_write_synced(tmp,transmute([]byte)(torn_temp)))
	recovered,status:=ar.storage_recover_document(paths.options,.Options)
	testing.expect(t,status==.Valid)
	options,_,revision,decoded:=ar.persistence_decode_options(recovered)
	delete(recovered)
	testing.expect(t,decoded==.Valid&&revision==4&&!options.audio_enabled)

	// A completed backup is promotable when the primary never landed.
	backup_path,backup_path_err:=filepath.join([]string{paths.directory,"backup-only.json"},context.allocator)
	testing.expect(t,backup_path_err==nil)
	if backup_path_err!=nil do return
	defer delete(backup_path)
	backup:=ar.storage_artifact_path(backup_path,"bak")
	defer delete(backup)
	backup_data,backup_encoded:=ar.persistence_encode_options(second,9,"2026-08-17T10:09:00Z")
	testing.expect(t,backup_encoded)
	if !backup_encoded do return
	defer delete(backup_data)
	testing.expect(t,ar.storage_write_synced(backup,backup_data))
	recovered,status=ar.storage_recover_document(backup_path,.Options)
	testing.expect(t,status==.Valid&&ar.storage_file_exists(backup_path))
	options,_,revision,decoded=ar.persistence_decode_options(recovered)
	delete(recovered)
	testing.expect(t,decoded==.Valid&&revision==9&&options.audio_enabled)

	// A valid backup also repairs a corrupt primary.
	damaged_path,damaged_path_err:=filepath.join([]string{paths.directory,"damaged-primary.json"},context.allocator)
	testing.expect(t,damaged_path_err==nil)
	if damaged_path_err!=nil do return
	defer delete(damaged_path)
	damaged_backup:=ar.storage_artifact_path(damaged_path,"bak")
	defer delete(damaged_backup)
	damaged_primary:string="not-json"
	testing.expect(t,ar.storage_write_synced(damaged_path,transmute([]byte)(damaged_primary)))
	testing.expect(t,ar.storage_write_synced(damaged_backup,backup_data))
	recovered,status=ar.storage_recover_document(damaged_path,.Options)
	testing.expect(t,status==.Valid)
	options,_,revision,decoded=ar.persistence_decode_options(recovered)
	delete(recovered)
	testing.expect(t,decoded==.Valid&&revision==9&&options.audio_enabled)

	// Equal revisions with different valid payloads are ambiguous and must not win by filename order.
	split_path,split_path_err:=filepath.join([]string{paths.directory,"split-brain.json"},context.allocator)
	testing.expect(t,split_path_err==nil)
	if split_path_err!=nil do return
	defer delete(split_path)
	testing.expect(t,mx_save_store_options(t,split_path,first,12))
	split_tmp:=ar.storage_artifact_path(split_path,"tmp")
	defer delete(split_tmp)
	split_data,split_encoded:=ar.persistence_encode_options(second,12,"2026-08-17T10:12:00Z")
	testing.expect(t,split_encoded)
	if !split_encoded do return
	defer delete(split_data)
	testing.expect(t,ar.storage_write_synced(split_tmp,split_data))
	recovered,status=ar.storage_recover_document(split_path,.Options)
	delete(recovered)
	testing.expect(t,status==.Corrupt)
}

@(test)
mx_save_run_recovery_rejects_artifacts_from_another_descent :: proc(t:^testing.T) {
	paths,paths_ok:=mx_save_temp_paths(t)
	if !paths_ok do return
	defer mx_save_cleanup_paths(&paths)
	first:=mx_save_start_app(0xA001)
	defer mx_save_destroy_app(&first)
	second:=mx_save_start_app(0xA002)
	defer mx_save_destroy_app(&second)
	first_id:=strings.clone(first.run.run_id)
	defer delete(first_id)
	testing.expect(t,mx_save_store_run(t,paths.run,&first,1))
	second_data,encoded:=ar.persistence_encode_run(&second,2,"2026-08-17T10:02:00Z")
	testing.expect(t,encoded)
	if !encoded do return
	defer delete(second_data)
	tmp:=ar.storage_artifact_path(paths.run,"tmp")
	defer delete(tmp)
	testing.expect(t,ar.storage_write_synced(tmp,second_data))

	recovered,status:=ar.storage_recover_document(paths.run,.Run)
	delete(recovered)
	testing.expect(t,status==.Corrupt,"run artifacts from different run IDs must never be combined")
	primary,read_status:=ar.storage_read_bounded(paths.run,ar.PERSISTENCE_RUN_MAX_BYTES)
	testing.expect(t,read_status==.Valid)
	if read_status!=.Valid {delete(primary);return}
	document,decoded:=ar.persistence_decode_run(primary)
	delete(primary)
	testing.expect(t,decoded==.Valid&&document.run_id==first_id,"ambiguous recovery must preserve the existing primary")
	ar.run_document_destroy(&document)
}

@(test)
mx_save_corruption_is_isolated_between_options_profile_and_run :: proc(t:^testing.T) {
	paths,paths_ok:=mx_save_temp_paths(t)
	if !paths_ok do return
	defer mx_save_cleanup_paths(&paths)
	app:=mx_save_start_app(0xD04A1)
	defer mx_save_destroy_app(&app)
	options:=ar.options_default()
	options.fullscreen=false
	options.audio_enabled=false
	app.profile.hell_unlocked=true

	options_data,options_ok:=ar.persistence_encode_options(options,2,"2026-08-17T10:00:00Z")
	profile_data,profile_ok:=ar.persistence_encode_profile(&app.profile,3,"2026-08-17T10:00:00Z")
	run_data,run_ok:=ar.persistence_encode_run(&app,4,"2026-08-17T10:00:00Z")
	testing.expect(t,options_ok&&profile_ok&&run_ok)
	if !options_ok||!profile_ok||!run_ok {delete(options_data);delete(profile_data);delete(run_data);return}
	defer {delete(options_data);delete(profile_data);delete(run_data)}
	testing.expect(t,ar.storage_write_document_durable(paths.options,.Options,options_data))
	testing.expect(t,ar.storage_write_document_durable(paths.profile,.Profile,profile_data))
	testing.expect(t,ar.storage_write_document_durable(paths.run,.Run,run_data))
	corrupt_text:string="{broken"
	corrupt:=transmute([]byte)(corrupt_text)

	testing.expect(t,ar.storage_write_synced(paths.options,corrupt))
	testing.expect(t,mx_save_recovery_status(paths.options,.Options)==.Corrupt)
	testing.expect(t,mx_save_recovery_status(paths.profile,.Profile)==.Valid)
	testing.expect(t,mx_save_recovery_status(paths.run,.Run)==.Valid)
	testing.expect(t,ar.storage_write_document_durable(paths.options,.Options,options_data))

	testing.expect(t,ar.storage_write_synced(paths.profile,corrupt))
	testing.expect(t,mx_save_recovery_status(paths.profile,.Profile)==.Corrupt)
	testing.expect(t,mx_save_recovery_status(paths.options,.Options)==.Valid)
	testing.expect(t,mx_save_recovery_status(paths.run,.Run)==.Valid)
	testing.expect(t,ar.storage_write_document_durable(paths.profile,.Profile,profile_data))

	testing.expect(t,ar.storage_write_synced(paths.run,corrupt))
	testing.expect(t,mx_save_recovery_status(paths.run,.Run)==.Corrupt)
	testing.expect(t,mx_save_recovery_status(paths.options,.Options)==.Valid)
	testing.expect(t,mx_save_recovery_status(paths.profile,.Profile)==.Valid)
	testing.expect(t,ar.storage_write_document_durable(paths.run,.Run,run_data))

	recovered_options,options_status:=ar.storage_recover_document(paths.options,.Options)
	loaded_options,_,options_revision,options_decoded:=ar.persistence_decode_options(recovered_options)
	delete(recovered_options)
	testing.expect(t,options_status==.Valid&&options_decoded==.Valid&&options_revision==2)
	testing.expect(t,!loaded_options.fullscreen&&!loaded_options.audio_enabled)
	recovered_profile,profile_status:=ar.storage_recover_document(paths.profile,.Profile)
	loaded_profile,profile_revision,profile_decoded:=ar.persistence_decode_profile(recovered_profile)
	delete(recovered_profile)
	testing.expect(t,profile_status==.Valid&&profile_decoded==.Valid&&profile_revision==3)
	testing.expect(t,loaded_profile.profile_id==app.profile.profile_id&&loaded_profile.hell_unlocked)
	ar.profile_destroy(&loaded_profile)
	recovered_run,run_status:=ar.storage_recover_document(paths.run,.Run)
	loaded_run,run_decoded:=ar.persistence_decode_run(recovered_run)
	delete(recovered_run)
	testing.expect(t,run_status==.Valid&&run_decoded==.Valid)
	testing.expect(t,loaded_run.run_id==app.run.run_id&&loaded_run.payload.seed==app.run.seed)
	ar.run_document_destroy(&loaded_run)

	// With no valid backup left, profile/options corruption must gate title
	// actions and require an explicit quarantine before fresh defaults are saved.
	corrupt_before:=mx_save_corrupt_artifact_count(paths.directory)
	testing.expect(t,ar.storage_write_synced(paths.options,corrupt))
	testing.expect(t,ar.storage_write_synced(paths.profile,corrupt))
	coordinator:=ar.Persistence_Coordinator{
		paths=paths,ready=true,options_revision=2,profile_revision=3,
		options_blocked=true,profile_blocked=true,
	}
	app.profile_save_damaged=true
	app.options_save_damaged=true
	app.mode=.Title
	app.title_index=int(ar.Title_Action.New_Run)
	_=ar.app_apply(&app,ar.Intent{confirm=true})
	testing.expect(t,app.mode==.Recovery,"damaged profile/options must be reported before starting another run")
	_=ar.app_apply(&app,ar.Intent{menu_index=1,menu_index_valid=true,confirm=true})
	testing.expect(t,app.mode==.Save_Wait&&app.persistence_request==.Quarantine_Documents)
	ar.persistence_process_request(&coordinator,&app)
	testing.expect(t,app.mode==.Title&&app.persistence_request==.None)
	testing.expect(t,!app.profile_save_damaged&&!app.options_save_damaged)
	testing.expect(t,!coordinator.profile_blocked&&!coordinator.options_blocked)
	testing.expect(t,mx_save_recovery_status(paths.options,.Options)==.Valid)
	testing.expect(t,mx_save_recovery_status(paths.profile,.Profile)==.Valid)
	testing.expect(t,mx_save_corrupt_artifact_count(paths.directory)>=corrupt_before+2,"explicit quarantine must preserve both invalid primaries")
	// Paths are still owned by the outer cleanup; prevent a second owner here.
	coordinator.paths={}
}

@(test)
mx_save_abandon_removes_all_run_artifacts_without_chronicle_or_backup_resurrection :: proc(t:^testing.T) {
	paths,paths_ok:=mx_save_temp_paths(t)
	if !paths_ok do return
	coordinator:=ar.Persistence_Coordinator{paths=paths,ready=true,profile_revision=4,run_revision=2}
	defer mx_save_cleanup_coordinator(&coordinator)
	app:=mx_save_start_app(0xABAD01)
	defer mx_save_destroy_app(&app)
	app.profile.hell_unlocked=true
	testing.expect(t,mx_save_store_profile(t,coordinator.paths.profile,&app.profile,4))
	testing.expect(t,mx_save_store_run(t,coordinator.paths.run,&app,1))
	app.run.player.hp=max(1,app.run.player.hp-1)
	testing.expect(t,mx_save_store_run(t,coordinator.paths.run,&app,2))
	bak:=ar.storage_artifact_path(coordinator.paths.run,"bak")
	defer delete(bak)
	tmp:=ar.storage_artifact_path(coordinator.paths.run,"tmp")
	defer delete(tmp)
	tmp_data,tmp_encoded:=ar.persistence_encode_run(&app,3,"2026-08-17T10:03:00Z")
	testing.expect(t,tmp_encoded)
	if !tmp_encoded do return
	defer delete(tmp_data)
	testing.expect(t,ar.storage_write_synced(tmp,tmp_data))
	testing.expect(t,ar.storage_file_exists(bak)&&ar.storage_file_exists(tmp))

	app.mode=.Save_Wait
	app.persistence_request=.Abandon
	ar.persistence_process_request(&coordinator,&app)
	testing.expect(t,app.persistence_request==.None&&app.persistence_error==.None)
	testing.expect(t,app.mode==.Select&&!app.active_run_available&&app.run.run_id=="")
	testing.expect(t,len(app.profile.chronicle)==0&&app.profile.lifetime_descents==0,"abandonment must not become a Chronicle death")
	testing.expect(t,!ar.storage_file_exists(coordinator.paths.run)&&!ar.storage_file_exists(tmp)&&!ar.storage_file_exists(bak))
	testing.expect(t,mx_save_recovery_status(coordinator.paths.run,.Run)==.Missing,"deleted run backups must not resurrect an abandoned descent")

	profile_data,profile_status:=ar.storage_recover_document(coordinator.paths.profile,.Profile)
	testing.expect(t,profile_status==.Valid)
	if profile_status==.Valid {
		profile,revision,decoded:=ar.persistence_decode_profile(profile_data)
		testing.expect(t,decoded==.Valid&&revision==4&&profile.hell_unlocked)
		testing.expect(t,len(profile.chronicle)==0)
		ar.profile_destroy(&profile)
	}
	delete(profile_data)
}

@(test)
mx_save_abandon_after_relaunch_restores_the_checkpoint_before_tombstoning :: proc(t:^testing.T) {
	paths,paths_ok:=mx_save_temp_paths(t)
	if !paths_ok do return
	coordinator:=ar.Persistence_Coordinator{paths=paths,ready=true,run_revision=1}
	defer mx_save_cleanup_coordinator(&coordinator)

	source:=mx_save_start_app(0xABAD02)
	defer mx_save_destroy_app(&source)
	testing.expect(t,mx_save_store_run(t,coordinator.paths.run,&source,1))

	// Startup intentionally discovers only the active slot; the Run itself remains
	// unloaded until Resume. Discarding from the title must still tombstone that
	// persisted identity before deleting every recoverable artifact.
	restarted:ar.App
	ar.app_init(&restarted,0xABAD03)
	defer ar.run_destroy(&restarted.run)
	restarted.active_run_available=true
	restarted.mode=.Title
	restarted.title_index=int(ar.Title_Action.New_Run)
	_=ar.app_apply(&restarted,ar.Intent{confirm=true})
	testing.expect(t,restarted.mode==.Abandon_Confirm&&restarted.run.run_id=="")
	_=ar.app_apply(&restarted,ar.Intent{menu_index=1,menu_index_valid=true,confirm=true})
	testing.expect(t,restarted.mode==.Save_Wait&&restarted.persistence_request==.Abandon)
	coordinator.save_wait_presented=true
	ar.persistence_update_scheduler(&coordinator,&restarted,0)

	testing.expect(t,restarted.persistence_request==.None&&restarted.persistence_error==.None)
	testing.expect(t,restarted.mode==.Select&&!restarted.active_run_available&&restarted.run.run_id=="")
	testing.expect(t,mx_save_recovery_status(coordinator.paths.run,.Run)==.Missing,"discarded relaunch checkpoint must not survive or resurrect")
	_=ar.app_apply(&restarted,ar.Intent{confirm=true})
	testing.expect(t,restarted.mode==.Playing&&restarted.run.run_id!="","discard must continue directly into a new descent")
}

@(test)
mx_save_worker_encodes_an_owned_fixed_tick_snapshot :: proc(t:^testing.T) {
	// Coalescing is per document domain: preserve first-seen domain order while
	// retaining only the newest revision within each slot.
	batch:[3]ar.Save_Job
	batch_count:=0
	ar.save_worker_batch_add(&batch,&batch_count,ar.Save_Job{kind=.Options,revision=1})
	ar.save_worker_batch_add(&batch,&batch_count,ar.Save_Job{kind=.Run,revision=4})
	ar.save_worker_batch_add(&batch,&batch_count,ar.Save_Job{kind=.Options,revision=3})
	ar.save_worker_batch_add(&batch,&batch_count,ar.Save_Job{kind=.Profile,revision=2})
	ar.save_worker_batch_add(&batch,&batch_count,ar.Save_Job{kind=.Run,revision=1})
	testing.expect(t,batch_count==3)
	testing.expect(t,batch[0].kind==.Options&&batch[0].revision==3)
	testing.expect(t,batch[1].kind==.Run&&batch[1].revision==4)
	testing.expect(t,batch[2].kind==.Profile&&batch[2].revision==2)
	for i in 0..<batch_count do ar.save_job_destroy(&batch[i])

	paths,paths_ok:=mx_save_temp_paths(t)
	if !paths_ok do return
	coordinator:=ar.Persistence_Coordinator{paths=paths,ready=true}
	if !ar.save_worker_init(&coordinator.worker) {
		testing.expect(t,false,"save worker must start")
		mx_save_cleanup_paths(&coordinator.paths)
		return
	}
	defer mx_save_cleanup_coordinator(&coordinator)
	app:=mx_save_start_app(0xC01A5CE)
	defer mx_save_destroy_app(&app)

	app.run.player.hp=max(2,app.run.player.max_hp-9)
	app.run.kills=17
	snapshotted_hp:=app.run.player.hp
	snapshotted_kills:=app.run.kills

	// Queue all three document domains in one burst. Coalescing a run must never
	// evict an independent options or profile write.
	queued_options:=app.options
	queued_options.audio_enabled=!queued_options.audio_enabled
	options_data,options_encoded:=ar.persistence_encode_options(queued_options,2,"2026-08-17T10:02:00Z")
	profile_data,profile_encoded:=ar.persistence_encode_profile(&app.profile,3,"2026-08-17T10:03:00Z")
	testing.expect(t,options_encoded&&profile_encoded)
	if options_encoded do testing.expect(t,ar.save_worker_enqueue(&coordinator.worker,.Options,coordinator.paths.options,options_data,2))
	else do delete(options_data)
	if profile_encoded do testing.expect(t,ar.save_worker_enqueue(&coordinator.worker,.Profile,coordinator.paths.profile,profile_data,3))
	else do delete(profile_data)
	testing.expect(t,ar.persistence_enqueue_run(&coordinator,&app))
	snapshotted_revision:=app.run.revision

	// This mutation happens while JSON encoding and disk I/O may still be active.
	// The writer must see only the owned state captured at enqueue time.
	app.run.player.hp=1
	app.run.kills=999
	testing.expect(t,ar.persistence_drain_worker(&coordinator))

	options_stored,options_status:=ar.storage_recover_document(coordinator.paths.options,.Options)
	if options_status==.Valid {
		loaded,_,revision,decoded:=ar.persistence_decode_options(options_stored)
		testing.expect(t,decoded==.Valid&&revision==2&&loaded.audio_enabled==queued_options.audio_enabled)
		testing.expect(t,len(options_stored)<=ar.PERSISTENCE_OPTIONS_MAX_BYTES)
		testing.expect(t,!strings.contains(string(options_stored),coordinator.paths.directory),"options must never serialize a machine-local path")
	} else do testing.expect(t,false,"cross-domain options job must survive run coalescing")
	delete(options_stored)
	profile_stored,profile_status:=ar.storage_recover_document(coordinator.paths.profile,.Profile)
	if profile_status==.Valid {
		loaded,revision,decoded:=ar.persistence_decode_profile(profile_stored)
		testing.expect(t,decoded==.Valid&&revision==3&&loaded.profile_id==app.profile.profile_id)
		testing.expect(t,len(profile_stored)<=ar.PERSISTENCE_PROFILE_MAX_BYTES)
		testing.expect(t,!strings.contains(string(profile_stored),coordinator.paths.directory),"profile must never serialize a machine-local path")
		ar.profile_destroy(&loaded)
	} else do testing.expect(t,false,"cross-domain profile job must survive run coalescing")
	delete(profile_stored)

	data,status:=ar.storage_recover_document(coordinator.paths.run,.Run)
	defer delete(data)
	testing.expect(t,status==.Valid)
	if status!=.Valid do return
	testing.expect(t,len(data)<=ar.PERSISTENCE_RUN_MAX_BYTES)
	testing.expect(t,!strings.contains(string(data),coordinator.paths.directory),"run must never serialize a machine-local path")
	document,decoded:=ar.persistence_decode_run(data)
	defer ar.run_document_destroy(&document)
	testing.expect(t,decoded==.Valid&&document.revision==snapshotted_revision)
	if decoded==.Valid {
		testing.expect(t,document.payload.player.hp==snapshotted_hp)
		testing.expect(t,document.payload.kills==snapshotted_kills)
		testing.expect(t,document.payload.player.hp!=app.run.player.hp&&document.payload.kills!=app.run.kills)
	}
}

@(test)
mx_save_explicit_exit_waits_for_inflight_checkpoint_without_blocking_the_loop :: proc(t:^testing.T) {
	paths,paths_ok:=mx_save_temp_paths(t)
	if !paths_ok do return
	coordinator:=ar.Persistence_Coordinator{paths=paths,ready=true}
	if !ar.save_worker_init(&coordinator.worker) {
		testing.expect(t,false,"save worker must start")
		mx_save_cleanup_paths(&coordinator.paths)
		return
	}
	defer mx_save_cleanup_coordinator(&coordinator)
	app:=mx_save_start_app(0xE71A5)
	defer mx_save_destroy_app(&app)

	// Save & Return arrives while the new-run checkpoint is still owned by the
	// worker. Scheduler polling must keep returning to the render loop until that
	// write completes, then commit the latest authoritative state synchronously.
	testing.expect(t,ar.persistence_enqueue_run(&coordinator,&app))
	app.run.kills=31
	app.mode=.Save_Wait
	app.persistence_request=.Save_Return_Title
	app.persistence_return=.Paused
	coordinator.save_wait_presented=true
	for attempt in 0..<1000 {
		ar.persistence_update_scheduler(&coordinator,&app,f64(attempt)/60)
		if app.mode==.Title do break
		time.sleep(time.Millisecond)
	}
	testing.expect(t,app.mode==.Title&&app.persistence_request==.None,"Save & Return must leave the progress overlay after the worker completes")
	data,status:=ar.storage_recover_document(coordinator.paths.run,.Run)
	if status==.Valid {
		document,decoded:=ar.persistence_decode_run(data)
		testing.expect(t,decoded==.Valid&&document.payload.kills==31)
		ar.run_document_destroy(&document)
	} else do testing.expect(t,false,"Save & Return must leave a valid checkpoint")
	delete(data)

	// Save & Quit follows the same non-blocking path and exits only after a newer
	// fixed-tick state reaches the primary run document.
	app.mode=.Playing
	app.run.kills=47
	app.run_dirty=true
	app.run_critical=true
	app.run_dirty_serial+=1
	testing.expect(t,ar.persistence_enqueue_run(&coordinator,&app))
	app.mode=.Save_Wait
	app.persistence_request=.Save_Quit
	app.persistence_return=.Paused
	coordinator.save_wait_presented=true
	for attempt in 0..<1000 {
		ar.persistence_update_scheduler(&coordinator,&app,f64(attempt)/60)
		if app.quit_requested do break
		time.sleep(time.Millisecond)
	}
	testing.expect(t,app.quit_requested&&app.persistence_request==.None,"Save & Quit must finish after the worker completes")
	data,status=ar.storage_recover_document(coordinator.paths.run,.Run)
	if status==.Valid {
		document,decoded:=ar.persistence_decode_run(data)
		testing.expect(t,decoded==.Valid&&document.payload.kills==47)
		ar.run_document_destroy(&document)
	} else do testing.expect(t,false,"Save & Quit must leave a valid checkpoint")
	delete(data)
}

@(test)
mx_save_existing_storage_directory_remains_available_on_second_launch :: proc(t:^testing.T) {
	data_root,root_err:=os.make_directory_temp("","arch-rogue-mx-save-relaunch-*",context.allocator)
	testing.expect(t,root_err==nil)
	if root_err!=nil do return
	defer {_=os.remove_all(data_root);delete(data_root)}

	directory,join_err:=filepath.join([]string{data_root,ar.APP_DATA_DIRECTORY_NAME},context.allocator)
	testing.expect(t,join_err==nil)
	if join_err!=nil do return
	defer delete(directory)

	testing.expect(t,ar.storage_ensure_directory(directory),"first launch must create the save directory")
	testing.expect(t,ar.storage_ensure_directory(directory),"second launch must accept the existing save directory")
	paths,paths_ok:=ar.storage_paths_from_directory(directory)
	testing.expect(t,paths_ok&&paths.directory==directory,"existing storage must still produce usable document paths")
	if paths_ok do ar.storage_paths_destroy(&paths)
}
