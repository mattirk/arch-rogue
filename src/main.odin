package archrogue

import "base:runtime"
import "core:fmt"
import "core:strings"
import rl "../vendor/raylib"

VERSION :: "6.0.0-alpha.24"

// Spiral-of-death guard: clamp huge frame gaps (debugger pause, window drag).
MAX_FRAME_DT :: 0.25

MAX_GAMEPADS :: 4

Controller_Runtime :: struct {
	gamepad:       int,
	left_stick:    Controller_Stick_State,
	right_stick:   Controller_Stick_State,
	menu_stick:    Controller_Menu_Stick_State,
	triggers:      [Controller_Trigger]Controller_Trigger_State,
	aim_mode:      bool,
	right_aim_this_frame: bool,
	// Arrow movement claims aim ownership from the mouse, exactly like
	// aim_mode does for pads: a parked cursor then neither aims abilities nor
	// turns the idle character until the mouse moves or clicks again.
	keyboard_aim:  bool,
}

@(rodata)
RAYLIB_GAMEPAD_BUTTONS := [Controller_Button]rl.GamepadButton{
	.A=.RIGHT_FACE_DOWN,.B=.RIGHT_FACE_RIGHT,.X=.RIGHT_FACE_LEFT,.Y=.RIGHT_FACE_UP,
	.Left_Bumper=.LEFT_TRIGGER_1,.Right_Bumper=.RIGHT_TRIGGER_1,
	.Back=.MIDDLE_LEFT,.Start=.MIDDLE_RIGHT,.Left_Stick=.LEFT_THUMB,.Right_Stick=.RIGHT_THUMB,
	.Dpad_Up=.LEFT_FACE_UP,.Dpad_Down=.LEFT_FACE_DOWN,.Dpad_Left=.LEFT_FACE_LEFT,.Dpad_Right=.LEFT_FACE_RIGHT,
}

@(rodata)
RAYLIB_GAMEPAD_TRIGGER_AXES := [Controller_Trigger]rl.GamepadAxis{
	.Left=.LEFT_TRIGGER,
	.Right=.RIGHT_TRIGGER,
}

@(rodata)
RAYLIB_GAMEPAD_TRIGGER_BUTTONS := [Controller_Trigger]rl.GamepadButton{
	.Left=.LEFT_TRIGGER_2,
	.Right=.RIGHT_TRIGGER_2,
}

controller_raylib_trigger_sample :: proc(gamepad: int, trigger: Controller_Trigger) -> f32 {
	axis := RAYLIB_GAMEPAD_TRIGGER_AXES[trigger]
	axis_available := int(rl.GetGamepadAxisCount(i32(gamepad))) > int(axis)
	axis_value: f32
	if axis_available do axis_value = rl.GetGamepadAxisMovement(i32(gamepad),axis)
	button_down := rl.IsGamepadButtonDown(i32(gamepad),RAYLIB_GAMEPAD_TRIGGER_BUTTONS[trigger])
	return controller_trigger_sample(axis_available,axis_value,button_down)
}

collect_controller_intent :: proc(app:^App,state:^Controller_Runtime,intent:^Intent) {
	state.right_aim_this_frame = false
	pad:=-1
	if app.options.controller_enabled {
		for candidate in 0..<MAX_GAMEPADS {
			if rl.IsGamepadAvailable(i32(candidate)) {pad=candidate;break}
		}
	}
	if pad<0 {
		// Reset the pad-local latches, but keyboard aim ownership is keyboard
		// state that merely rides in this runtime: it must survive the frames
		// without a pad (a plain state^={} here wiped it every frame, handing
		// ability aim back to the parked cursor).
		keyboard_aim := state.keyboard_aim
		state^={}
		state.keyboard_aim = keyboard_aim
		return
	}
	state.gamepad=pad
	if app.mode == .Controls && app.controls_capture {
		for button in Controller_Button {
			if rl.IsGamepadButtonReleased(i32(pad),RAYLIB_GAMEPAD_BUTTONS[button]) &&
				controller_button_command(&app.options.gamepad_mapping,button,.Gameplay)==.Ability_1 {
				intent.action1_released = true
			}
		}
		for button in Controller_Button {
			if rl.IsGamepadButtonPressed(i32(pad),RAYLIB_GAMEPAD_BUTTONS[button]) {
				intent.remap_button = button
				intent.remap_button_valid = true
				return
			}
		}
		for trigger in Controller_Trigger {
			raw:=controller_raylib_trigger_sample(pad,trigger)
			edge := controller_resolve_trigger(raw,&state.triggers[trigger])
			if edge == .Released && controller_trigger_command(&app.options.gamepad_mapping,trigger)==.Ability_1 {
				intent.action1_released = true
			}
			if edge==.Pressed {
				intent.remap_trigger = trigger
				intent.remap_trigger_valid = true
				return
			}
		}
		return
	}
	gameplay:=app.mode==.Playing&&!app.inventory_open&&!app.character_open&&!app.shop_open&&
		!app_play_modal_open(app)
	ctx:=gameplay?Controller_Context.Gameplay:.Menu
	left_raw:=Vec2{rl.GetGamepadAxisMovement(i32(pad),.LEFT_X),rl.GetGamepadAxisMovement(i32(pad),.LEFT_Y)}
	left:=controller_resolve_stick(left_raw,&state.left_stick)
	if left != {} do state.aim_mode = true
	if gameplay {
		// Sticks steer by screen compass like the mobile joystick: convert the
		// screen-space deflection into tile space before the sim sees it.
		if left!={} do intent.move=screen_stick_to_tile_vector(left)
		right_raw:=Vec2{rl.GetGamepadAxisMovement(i32(pad),.RIGHT_X),rl.GetGamepadAxisMovement(i32(pad),.RIGHT_Y)}
		right:=controller_resolve_stick(right_raw,&state.right_stick)
		if right!={} {
			state.aim_mode = true
			state.right_aim_this_frame = true
			intent.aim=controller_snap_aim(&app.run,screen_stick_to_tile_vector(right))
			intent.aim_live=true
		}
	} else {
		if command:=controller_resolve_menu_stick(left,&state.menu_stick);command!=.None {
			intent_apply_command(intent,command,false)
		}
	}
	for button in Controller_Button {
		if rl.IsGamepadButtonPressed(i32(pad),RAYLIB_GAMEPAD_BUTTONS[button]) {
			state.aim_mode = true
			intent_apply_command(intent,controller_button_command(&app.options.gamepad_mapping,button,ctx),gameplay)
		}
		if rl.IsGamepadButtonReleased(i32(pad),RAYLIB_GAMEPAD_BUTTONS[button]) &&
			controller_button_command(&app.options.gamepad_mapping,button,.Gameplay)==.Ability_1 {
			intent.action1_released=true
		}
	}
	for trigger in Controller_Trigger {
		raw:=controller_raylib_trigger_sample(pad,trigger)
		edge:=controller_resolve_trigger(raw,&state.triggers[trigger])
		if edge==.Pressed {
			state.aim_mode = true
			// Non-playing menus discard gameplay trigger presses. Overlays keep
			// them because they still live in Playing and remapped toggle actions
			// must be able to close the surface they opened.
			if app.mode == .Playing {
				intent_apply_command(intent,controller_trigger_command(&app.options.gamepad_mapping,trigger),gameplay)
			}
		} else if edge==.Released&&controller_trigger_command(&app.options.gamepad_mapping,trigger)==.Ability_1 {
			intent.action1_released=true
		}
	}
	if gameplay && state.aim_mode && intent.aim == {} {
		intent.aim = controller_snap_aim(&app.run,app.run.player.facing)
	}
}

merge_gameplay_intent :: proc(dst:^Intent,src:Intent) {
	if dst.move=={} do dst.move=src.move
	if dst.aim=={} do dst.aim=src.aim
	dst.aim_live=dst.aim_live||src.aim_live
	dst.mouse_walk=src.mouse_walk
	dst.mouse_press=src.mouse_press
	dst.mouse_press_aim=src.mouse_press_aim
	dst.mouse_released=src.mouse_released
	dst.mouse_target=src.mouse_target
	for i in 0..<4 do dst.actions[i]=dst.actions[i]||src.actions[i]
	dst.action1_released=dst.action1_released||src.action1_released
	dst.interact=dst.interact||src.interact
	dst.use_heal=dst.use_heal||src.use_heal
	dst.use_mana=dst.use_mana||src.use_mana
	dst.toggle_inventory=dst.toggle_inventory||src.toggle_inventory
	dst.back=dst.back||src.back
	// Minimap commands were already resolved contextually before this merge.
	// Desktop_Input intentionally excludes them, preventing additive wheel deltas.
}

APP_DATA_DIRECTORY_NAME :: "arch-rogue"
ANDROID_APP_DATA_DIRECTORY_NAME :: "arch-rogue-v6"

Storage_Paths :: struct {
	directory: string,
	options:   string,
	profile:   string,
	run:       string,
}

storage_paths_destroy :: proc(paths:^Storage_Paths) {
	if paths==nil do return
	delete(paths.directory);delete(paths.options);delete(paths.profile);delete(paths.run)
	paths^={}
}

storage_artifact_path :: proc(primary,suffix:string) -> string {
	return fmt.aprintf("%s.%s",primary,suffix)
}

storage_max_bytes :: proc(kind:Persistence_Document_Kind)->int {
	switch kind {case .Options:return PERSISTENCE_OPTIONS_MAX_BYTES;case .Profile:return PERSISTENCE_PROFILE_MAX_BYTES;case .Run:return PERSISTENCE_RUN_MAX_BYTES}
	return 0
}

storage_quarantine_file :: proc(path:string) -> bool {
	if !storage_file_exists(path) do return true
	quarantine:=fmt.aprintf("%s.corrupt-%d",path,platform_tick_us())
	defer delete(quarantine)
	return storage_replace_write_through(path,quarantine)&&storage_sync_parent(path)
}

storage_write_document_durable :: proc(primary:string,kind:Persistence_Document_Kind,data:[]byte)->bool {
	if primary==""||len(data)==0 do return false
	_,identity,status:=persistence_document_probe(kind,data)
	delete(identity)
	if status!=.Valid&&status!=.Migrated do return false
	tmp:=storage_artifact_path(primary,"tmp");defer delete(tmp)
	bak:=storage_artifact_path(primary,"bak");defer delete(bak)
	_=storage_remove_file(tmp)
	if !storage_write_synced(tmp,data) do return false
	if existing,read_status:=storage_read_bounded(primary,storage_max_bytes(kind));read_status==.Valid {
		_,old_identity,old_status:=persistence_document_probe(kind,existing)
		delete(old_identity);delete(existing)
		if old_status==.Valid||old_status==.Migrated {
			_=storage_remove_file(bak)
			if !storage_replace_write_through(primary,bak)||!storage_sync_parent(primary) {_=storage_remove_file(tmp);return false}
		} else if !storage_quarantine_file(primary) {
			_=storage_remove_file(tmp);return false
		}
	} else if read_status==.Oversize||read_status==.Corrupt {
		if !storage_quarantine_file(primary) {_=storage_remove_file(tmp);return false}
	}
	if !storage_replace_write_through(tmp,primary) do return false
	return storage_sync_parent(primary)
}

Storage_Candidate :: struct {
	path:string,
	data:[]byte,
	revision:u64,
	identity:string,
	status:Persistence_Decode_Status,
	present:bool,
}

storage_candidate_destroy :: proc(candidate:^Storage_Candidate) {
	if candidate==nil do return
	delete(candidate.path);delete(candidate.data);delete(candidate.identity);candidate^={}
}

storage_recover_document :: proc(primary:string,kind:Persistence_Document_Kind)->([]byte,Persistence_Decode_Status) {
	paths:=[3]string{primary,storage_artifact_path(primary,"tmp"),storage_artifact_path(primary,"bak")}
	defer {delete(paths[1]);delete(paths[2])}
	candidates:[3]Storage_Candidate
	future_seen:=false;invalid_seen:=false;conflict:=false;best:=-1
	defer for &candidate in candidates do storage_candidate_destroy(&candidate)
	for path,index in paths {
		candidates[index].path=strings.clone(path)
		data,read_status:=storage_read_bounded(path,storage_max_bytes(kind))
		if read_status==.Missing do continue
		candidates[index].present=true
		if read_status!=.Valid {candidates[index].status=read_status;invalid_seen=true;continue}
		revision,identity,status:=persistence_document_probe(kind,data)
		candidates[index].data=data;candidates[index].revision=revision;candidates[index].identity=identity;candidates[index].status=status
		if status==.Future {future_seen=true;continue}
		if status!=.Valid&&status!=.Migrated {invalid_seen=true;continue}
		if best>=0&&kind==.Run&&candidates[best].identity!=identity {invalid_seen=true;conflict=true;continue}
		if best<0||revision>candidates[best].revision {best=index;continue}
		if revision==candidates[best].revision&&string(candidates[best].data)!=string(data) {
			invalid_seen=true;conflict=true
		}
	}
	if conflict do return nil,.Corrupt
	if best<0 {
		if future_seen do return nil,.Future
		if invalid_seen do return nil,.Corrupt
		return nil,.Missing
	}
	selected:=&candidates[best]
	result:=make([]byte,len(selected.data));copy(result,selected.data)
	if best!=0 {
		primary_valid:=candidates[0].status==.Valid||candidates[0].status==.Migrated
		if candidates[0].present&&!primary_valid&&!storage_quarantine_file(primary) {delete(result);return nil,.Corrupt}
		if !storage_write_document_durable(primary,kind,result) {delete(result);return nil,.Corrupt}
	}
	return result,selected.status
}

storage_remove_run :: proc(paths:^Storage_Paths)->bool {
	if paths==nil do return false
	tmp:=storage_artifact_path(paths.run,"tmp");defer delete(tmp)
	bak:=storage_artifact_path(paths.run,"bak");defer delete(bak)
	ok:=true
	removed:=false
	artifacts:=[3]string{paths.run,tmp,bak}
	for path in artifacts {
		if storage_file_exists(path) {
			if !storage_remove_file(path) do ok=false
			else do removed=true
		}
	}
	if removed&&!storage_sync_parent(paths.run) do ok=false
	return ok
}

Save_Job :: struct {
	kind:             Persistence_Document_Kind,
	path:             string,
	data:             []byte,
	revision:         u64,
	run_id:           string,
	written_at_utc:   string,
	run_payload: ^Run_Save_Payload,
	allocator:   runtime.Allocator,
	stop:        bool,
}

Save_Completion :: struct {
	kind:Persistence_Document_Kind,
	revision:u64,
	success:bool,
}

save_job_destroy :: proc(job:^Save_Job) {
	if job==nil do return
	allocator:=job.allocator
	if allocator.procedure==nil do allocator=context.allocator
	delete(job.path,allocator)
	delete(job.data,allocator)
	delete(job.run_id,allocator)
	delete(job.written_at_utc,allocator)
	if job.run_payload!=nil {
		run_save_payload_destroy(job.run_payload,allocator)
		free(job.run_payload,allocator)
	}
	job^={}
}

Persistence_Coordinator :: struct {
	paths:Storage_Paths,
	worker:Save_Worker,
	steam:^Steam_State, // terminal finalization feeds the achievement funnel
	ready:bool,
	options_revision:u64,
	profile_revision:u64,
	run_revision:u64,
	options_blocked:bool,
	profile_blocked:bool,
	run_write_in_flight:bool,
	seen_dirty_serial:u64,
	dirty_first:f64,
	dirty_last:f64,
	retry_at:f64,
	run_snapshot_count:u64,
	run_snapshot_total_ms:f64,
	run_snapshot_max_ms:f64,
	save_wait_presented:bool,
}

persistence_utc_now :: proc() -> string {
	return platform_now_utc_rfc3339()
}

persistence_new_profile_id :: proc(seed:u64)->string {
	source:=fmt.aprintf("arch-rogue:%016x:%d",seed,platform_tick_us());defer delete(source)
	hashed:=persistence_sha256(transmute([]byte)(source))
	if len(hashed)<32 do return fmt.aprintf("local-%016x",seed)
	result:=strings.clone(hashed[:32]);delete(hashed);return result
}

persistence_coordinator_destroy :: proc(coordinator:^Persistence_Coordinator) {
	if coordinator==nil do return
	save_worker_shutdown(&coordinator.worker)
	storage_paths_destroy(&coordinator.paths)
	coordinator^={}
}

persistence_write_profile_sync :: proc(coordinator:^Persistence_Coordinator,app:^App)->bool {
	if coordinator==nil||app==nil||!coordinator.ready||coordinator.profile_blocked do return false
	revision:=max(coordinator.profile_revision+1,app.profile.revision)
	if revision==0 do revision=1
	written:=persistence_utc_now();defer delete(written)
	data,ok:=persistence_encode_profile(&app.profile,revision,written)
	if !ok do return false
	defer delete(data)
	if !storage_write_document_durable(coordinator.paths.profile,.Profile,data) do return false
	coordinator.profile_revision=revision;app.profile.revision=revision
	return true
}

persistence_write_options_sync :: proc(coordinator:^Persistence_Coordinator,app:^App)->bool {
	if coordinator==nil||app==nil||!coordinator.ready||coordinator.options_blocked do return false
	revision:=coordinator.options_revision+1;if revision==0 do revision=1
	written:=persistence_utc_now();defer delete(written)
	data,ok:=persistence_encode_options(app.options,revision,written)
	if !ok do return false
	defer delete(data)
	if !storage_write_document_durable(coordinator.paths.options,.Options,data) do return false
	coordinator.options_revision=revision
	return true
}

persistence_prepare_run_identity :: proc(app:^App) {
	if app==nil do return
	if app.run.run_id=="" do app.run.run_id=profile_begin_run(&app.profile,app.run.seed)
	if app.run.started_at_utc=="" do app.run.started_at_utc=persistence_utc_now()
}

persistence_write_run_sync :: proc(coordinator:^Persistence_Coordinator,app:^App)->bool {
	if coordinator==nil||app==nil||!coordinator.ready do return false
	persistence_prepare_run_identity(app)
	revision:=max(coordinator.run_revision+1,app.run.revision+1)
	written:=persistence_utc_now();defer delete(written)
	data,ok:=persistence_encode_run(app,revision,written)
	if !ok do return false
	defer delete(data)
	if !storage_write_document_durable(coordinator.paths.run,.Run,data) do return false
	coordinator.run_revision=revision;app.run.revision=revision
	app.active_run_available=app.run.terminal==.Active
	return true
}

persistence_enqueue_run :: proc(coordinator:^Persistence_Coordinator,app:^App)->bool {
	if coordinator==nil||app==nil||!coordinator.ready||coordinator.run_write_in_flight do return false
	snapshot_begin:=platform_tick_ms_f64()
	defer {
		elapsed:=platform_tick_ms_f64()-snapshot_begin
		coordinator.run_snapshot_count+=1
		coordinator.run_snapshot_total_ms+=elapsed
		coordinator.run_snapshot_max_ms=max(coordinator.run_snapshot_max_ms,elapsed)
	}
	persistence_prepare_run_identity(app)
	run_ensure_persisted_entity_ids(&app.run)
	revision:=max(coordinator.run_revision+1,app.run.revision+1)
	written:=persistence_utc_now();defer delete(written)
	allocator:=platform_save_allocator()
	payload:=new(Run_Save_Payload,allocator)
	payload^=run_save_payload_clone_from_app(app,allocator)
	if !run_payload_validate(payload) {run_save_payload_destroy(payload,allocator);free(payload,allocator);return false}
	if !save_worker_enqueue_run(&coordinator.worker,coordinator.paths.run,app.run.run_id,written,payload,revision) do return false
	app.run.revision=revision;coordinator.run_write_in_flight=true
	app.run_dirty=false;app.run_critical=false
	coordinator.dirty_first=0;coordinator.dirty_last=0
	return true
}

persistence_enqueue_options :: proc(coordinator:^Persistence_Coordinator,app:^App)->bool {
	if coordinator==nil||app==nil||!coordinator.ready||coordinator.options_blocked do return false
	revision:=coordinator.options_revision+1;if revision==0 do revision=1
	written:=persistence_utc_now();defer delete(written)
	data,ok:=persistence_encode_options(app.options,revision,written)
	if !ok do return false
	if !save_worker_enqueue(&coordinator.worker,.Options,coordinator.paths.options,data,revision) do return false
	coordinator.options_revision=revision
	return true
}

persistence_poll_completions :: proc(coordinator:^Persistence_Coordinator,app:^App) {
	if coordinator==nil||app==nil||!coordinator.worker.ready do return
	for {
		completion,ok:=save_worker_try_completion(&coordinator.worker);if !ok do break
		switch completion.kind {
		case .Options:
			if completion.success do coordinator.options_revision=max(coordinator.options_revision,completion.revision)
		case .Profile:
			if completion.success do coordinator.profile_revision=max(coordinator.profile_revision,completion.revision)
		case .Run:
			coordinator.run_write_in_flight=false
			if completion.success {
				coordinator.run_revision=max(coordinator.run_revision,completion.revision)
				app.active_run_available=app.run.terminal==.Active
			} else {
				app.run_dirty=true;coordinator.retry_at=rl.GetTime()+1.0
			}
		}
	}
}

persistence_quarantine_run :: proc(coordinator:^Persistence_Coordinator)->bool {
	if coordinator==nil do return false
	tmp:=storage_artifact_path(coordinator.paths.run,"tmp");defer delete(tmp)
	bak:=storage_artifact_path(coordinator.paths.run,"bak");defer delete(bak)
	ok:=true
	artifacts:=[3]string{coordinator.paths.run,tmp,bak}
	for path in artifacts {if storage_file_exists(path)&&!storage_quarantine_file(path) do ok=false}
	return ok
}

persistence_quarantine_document :: proc(primary:string)->bool {
	if primary=="" do return false
	tmp:=storage_artifact_path(primary,"tmp");defer delete(tmp)
	bak:=storage_artifact_path(primary,"bak");defer delete(bak)
	ok:=true
	artifacts:=[3]string{primary,tmp,bak}
	for path in artifacts {if storage_file_exists(path)&&!storage_quarantine_file(path) do ok=false}
	return ok
}

persistence_recover_documents :: proc(coordinator:^Persistence_Coordinator,app:^App)->bool {
	if coordinator==nil||app==nil do return false
	if app.profile_save_damaged {
		data,status:=storage_recover_document(coordinator.paths.profile,.Profile)
		if status==.Valid||status==.Migrated {
			loaded,revision,decoded:=persistence_decode_profile(data)
			if decoded==.Valid||decoded==.Migrated {
				profile_destroy(&app.profile)
				app.profile=loaded
				coordinator.profile_revision=revision
				coordinator.profile_blocked=false
				app.profile_save_damaged=false
				if decoded==.Migrated do _=persistence_write_profile_sync(coordinator,app)
			}
		}
		delete(data)
	}
	if app.options_save_damaged {
		data,status:=storage_recover_document(coordinator.paths.options,.Options)
		if status==.Valid||status==.Migrated {
			loaded,_,revision,decoded:=persistence_decode_options(data,app.profile.hell_unlocked)
			if decoded==.Valid||decoded==.Migrated {
				app.options=loaded
				options_normalize(&app.options,app.profile.hell_unlocked)
				coordinator.options_revision=revision
				coordinator.options_blocked=false
				app.options_save_damaged=false
			}
		}
		delete(data)
	}
	return !app.profile_save_damaged&&!app.options_save_damaged
}

persistence_quarantine_documents :: proc(coordinator:^Persistence_Coordinator,app:^App)->bool {
	if coordinator==nil||app==nil do return false
	ok:=true
	if app.profile_save_damaged {
		if persistence_quarantine_document(coordinator.paths.profile) {
			coordinator.profile_blocked=false
			app.profile_save_damaged=false
			if !persistence_write_profile_sync(coordinator,app) {
				coordinator.profile_blocked=true
				app.profile_save_damaged=true
				ok=false
			}
		} else do ok=false
	}
	if app.options_save_damaged {
		if persistence_quarantine_document(coordinator.paths.options) {
			coordinator.options_blocked=false
			app.options_save_damaged=false
			options_normalize(&app.options,app.profile.hell_unlocked)
			if !persistence_write_options_sync(coordinator,app) {
				coordinator.options_blocked=true
				app.options_save_damaged=true
				ok=false
			}
		} else do ok=false
	}
	return ok&&!app.profile_save_damaged&&!app.options_save_damaged
}

persistence_fail_request :: proc(app:^App,request:Persistence_Request,error_kind:Persistence_Error_Kind,return_mode:App_Mode) {
	if app==nil do return
	app.failed_request=request;app.persistence_request=.None;app.persistence_error=error_kind
	app.persistence_return=return_mode;app.confirm_index=0;app.mode=.Save_Error
}

persistence_restore_active_run :: proc(coordinator:^Persistence_Coordinator,app:^App)->(restored:bool,migrated:bool,error:Persistence_Error_Kind) {
	if coordinator==nil||app==nil do return false,false,.Load
	data,status:=storage_recover_document(coordinator.paths.run,.Run)
	if status!=.Valid&&status!=.Migrated {
		delete(data)
		app.active_run_damaged=status!=.Missing
		return false,false,status==.Future?.Future:.Load
	}
	document,decoded:=persistence_decode_run(data);delete(data)
	if (decoded!=.Valid&&decoded!=.Migrated)||document.payload.terminal!=.Active||!app_install_run_document(app,&document) {
		run_document_destroy(&document)
		app.active_run_damaged=true
		return false,false,.Corrupt
	}
	run_document_destroy(&document)
	coordinator.run_revision=app.run.revision
	app.active_run_available=true
	app.active_run_damaged=false
	return true,decoded==.Migrated,.None
}

// The one achievement funnel (STEAM.md S2): evaluate against the granted
// cache, durably queue the Steam push first, and only then mark the cache, so
// a failed queue write re-evaluates later instead of losing an unlock. On
// platforms without a queue (web, Android) nothing is cached and evaluation
// simply repeats — reconciliation on a Steam desktop covers cloud-moved
// profiles. Returns true when the profile changed and needs a write.
persistence_apply_achievements :: proc(coordinator:^Persistence_Coordinator,app:^App,has_run:bool,facts:Run_Terminal_Facts)->bool {
	if coordinator==nil||app==nil do return false
	newly:[len(Achievement_Id)]Achievement_Id
	count:=achievements_evaluate(&app.profile,has_run,facts,&newly)
	changed:=false
	for i in 0..<count {
		def:=ACHIEVEMENT_DEFS[newly[i]]
		if coordinator.steam!=nil&&steam_queue_achievement(coordinator.steam,def.api_id) {
			if profile_mark_achievement_granted(&app.profile,def.api_id) do changed=true
		}
	}
	return changed
}

persistence_finalize_terminal :: proc(coordinator:^Persistence_Coordinator,app:^App,request:Persistence_Request)->bool {
	if coordinator==nil||app==nil||coordinator.run_write_in_flight do return false
	if app.run.ended_at_utc=="" do app.run.ended_at_utc=persistence_utc_now()
	app.run.finalization=.Terminal_Marker
	if !persistence_write_run_sync(coordinator,app) do return false
	outcome:=app.run.terminal==.Victory?Chronicle_Outcome.Victory:Chronicle_Outcome.Fallen
	record:=chronicle_record_from_run(&app.run,outcome);defer chronicle_record_destroy(&record)
	facts:=run_terminal_facts(&app.run,outcome)
	// Aggregates apply only on the first finalization of this run_id, so
	// crash-recovery replay cannot double-count; the achievement evaluation
	// itself is idempotent through the granted cache either way.
	if profile_finalize_record(&app.profile,&record) {
		profile_apply_terminal_facts(&app.profile,&record,&facts)
	}
	_=persistence_apply_achievements(coordinator,app,true,facts)
	steam_publish_stats(coordinator.steam,&app.profile)
	app.profile.revision=max(app.profile.revision,coordinator.profile_revision+1)
	if !persistence_write_profile_sync(coordinator,app) do return false
	app.run.finalization=.Profile_Committed
	if !storage_remove_run(&coordinator.paths) do return false
	app.active_run_available=false;app.active_run_damaged=false
	app.run_dirty=false;app.run_critical=false;app.persistence_request=.None
	return true
}

persistence_process_request :: proc(coordinator:^Persistence_Coordinator,app:^App) {
	if coordinator==nil||app==nil||app.persistence_request==.None do return
	request:=app.persistence_request
	switch request {
	case .Resume:
		if coordinator.run_write_in_flight do return
		restored,migrated,error_kind:=persistence_restore_active_run(coordinator,app)
		if !restored {persistence_fail_request(app,request,error_kind,.Title);return}
		app.persistence_request=.None;app.persistence_error=.None;app.mode=.Resume_Veil
		app.run_dirty=false;app.run_critical=false
		// A schema-migrated run rewrites promptly so the on-disk document
		// upgrades to the current version without waiting for gameplay.
		if migrated do app_mark_run_dirty(app)
	case .Save_Checkpoint:
		app.persistence_request=.None
		if !persistence_write_profile_sync(coordinator,app) {
			persistence_fail_request(app,request,.Write,.Playing);return
		}
		if !persistence_enqueue_run(coordinator,app) do app.run_dirty=true
	case .Save_Return_Title, .Save_Quit:
		if coordinator.run_write_in_flight do return
		if !persistence_write_run_sync(coordinator,app) {
			persistence_fail_request(app,request,.Write,.Paused);return
		}
		app.persistence_request=.None;app.persistence_error=.None
		if request==.Save_Quit do app.quit_requested=true
		else do app.mode=.Title
	case .Abandon:
		if coordinator.run_write_in_flight do return
		// Startup discovers an active slot without loading its full Run. Restore the
		// durable identity before writing the abandoned marker so discarding works
		// without a preceding Resume and remains crash-safe before artifact removal.
		// Loaded runs and retries retain their in-memory marker state.
		if app.run.run_id=="" {
			restored,_,error_kind:=persistence_restore_active_run(coordinator,app)
			if !restored {persistence_fail_request(app,request,error_kind,.Title);return}
		}
		app.run.terminal=.Abandoned
		if !persistence_write_run_sync(coordinator,app)||!storage_remove_run(&coordinator.paths) {
			persistence_fail_request(app,request,.Remove,.Title);return
		}
		app.active_run_available=false;app.active_run_damaged=false;app.persistence_request=.None
		run_destroy(&app.run);app.run={};app.mode=.Select
	case .Recover_Run:
		if coordinator.run_write_in_flight do return
		data,status:=storage_recover_document(coordinator.paths.run,.Run);delete(data)
		if status==.Valid||status==.Migrated {
			app.active_run_available=true;app.active_run_damaged=false;app.persistence_request=.None;app.mode=.Title
		} else {
			persistence_fail_request(app,request,status==.Future?.Future:.Corrupt,.Recovery)
		}
	case .Quarantine_Run:
		if coordinator.run_write_in_flight do return
		if !persistence_quarantine_run(coordinator) {persistence_fail_request(app,request,.Remove,.Recovery);return}
		app.active_run_available=false;app.active_run_damaged=false;app.persistence_request=.None;app.mode=.Select
	case .Recover_Documents:
		if !persistence_recover_documents(coordinator,app) {
			persistence_fail_request(app,request,.Corrupt,.Recovery);return
		}
		app.persistence_request=.None;app.persistence_error=.None;app.mode=.Title
	case .Quarantine_Documents:
		if !persistence_quarantine_documents(coordinator,app) {
			persistence_fail_request(app,request,.Remove,.Recovery);return
		}
		app.persistence_request=.None;app.persistence_error=.None;app.mode=.Title
	case .Finalize_Death, .Finalize_Victory:
		if coordinator.run_write_in_flight do return
		return_mode:=request==.Finalize_Victory?App_Mode.Victory:App_Mode.Dead
		was_waiting:=app.mode==.Save_Wait
		if !persistence_finalize_terminal(coordinator,app,request) {
			persistence_fail_request(app,request,.Write,return_mode)
		} else if was_waiting {
			app.mode=return_mode
		}
	case .None:
	}
}

persistence_update_scheduler :: proc(coordinator:^Persistence_Coordinator,app:^App,now:f64) {
	if coordinator==nil||app==nil||!coordinator.ready do return
	persistence_poll_completions(coordinator,app)
	if app.mode==.Save_Wait&&!coordinator.save_wait_presented do return
	persistence_process_request(coordinator,app)
	if app.persistence_request!=.None||app.mode==.Save_Wait||app.mode==.Save_Error do return
	if !app.run_dirty||app.run.run_id==""||app.run.terminal!=.Active do return
	if app.run_dirty_serial!=coordinator.seen_dirty_serial {
		coordinator.seen_dirty_serial=app.run_dirty_serial
		if coordinator.dirty_first==0 do coordinator.dirty_first=now
		coordinator.dirty_last=now
	}
	if coordinator.run_write_in_flight||now<coordinator.retry_at do return
	quiet:=coordinator.dirty_last>0&&now-coordinator.dirty_last>=1.5
	deadline:=coordinator.dirty_first>0&&now-coordinator.dirty_first>=6.0
	if app.run_critical||quiet||deadline do _=persistence_enqueue_run(coordinator,app)
}

persistence_coordinator_init :: proc(coordinator:^Persistence_Coordinator,app:^App,seed:u64)->bool {
	if coordinator==nil||app==nil do return false
	paths,paths_ok:=platform_storage_paths();if !paths_ok do return false
	coordinator.paths=paths;coordinator.ready=true
	if !save_worker_init(&coordinator.worker) {storage_paths_destroy(&coordinator.paths);coordinator.ready=false;return false}

	profile_existed:=false
	profile_migrated:=false
	profile_data,profile_status:=storage_recover_document(coordinator.paths.profile,.Profile)
	if profile_status==.Valid||profile_status==.Migrated {
		profile,revision,decoded:=persistence_decode_profile(profile_data)
		if decoded==.Valid||decoded==.Migrated {
			app.profile=profile;coordinator.profile_revision=revision;profile_existed=true
			profile_migrated=decoded==.Migrated
		} else {
			coordinator.profile_blocked=true;app.profile_save_damaged=true
		}
	} else if profile_status==.Future||profile_status==.Corrupt||profile_status==.Oversize {
		coordinator.profile_blocked=true;app.profile_save_damaged=true
	}
	delete(profile_data)
	if app.profile.profile_id=="" {
		id:=persistence_new_profile_id(seed);profile_init(&app.profile,id);delete(id)
	}

	options_data,options_status:=storage_recover_document(coordinator.paths.options,.Options)
	if options_status==.Missing {
		legacy_path:=platform_legacy_options_path()
		if legacy_path!="" {options_data,options_status=storage_read_bounded(legacy_path,PERSISTENCE_OPTIONS_MAX_BYTES);delete(legacy_path)}
	}
	legacy_hell:=false
	if options_status==.Valid||options_status==.Migrated {
		loaded,import_hell,revision,decoded:=persistence_decode_options(options_data,app.profile.hell_unlocked)
		if decoded==.Valid||decoded==.Migrated {
			app.options=loaded;legacy_hell=import_hell;coordinator.options_revision=revision
			if decoded==.Migrated do options_status=.Migrated
		} else if decoded==.Future||decoded==.Corrupt||decoded==.Oversize {
			coordinator.options_blocked=true;app.options_save_damaged=true
		}
	} else if options_status==.Future||options_status==.Corrupt||options_status==.Oversize {
		coordinator.options_blocked=true;app.options_save_damaged=true
	}
	delete(options_data)
	if !profile_existed&&legacy_hell do app.profile.hell_unlocked=true
	options_normalize(&app.options,app.profile.hell_unlocked)
	if !coordinator.profile_blocked&&(profile_status==.Missing||profile_migrated||(!profile_existed&&legacy_hell)) do _=persistence_write_profile_sync(coordinator,app)
	if !coordinator.options_blocked&&(options_status==.Missing||options_status==.Migrated) do _=persistence_write_options_sync(coordinator,app)

	run_data,run_status:=storage_recover_document(coordinator.paths.run,.Run)
	if run_status==.Valid||run_status==.Migrated {
		document,decoded:=persistence_decode_run(run_data)
		if decoded==.Valid||decoded==.Migrated {
			coordinator.run_revision=document.revision
			if document.payload.terminal==.Active {
				app.active_run_available=true
			} else if document.payload.terminal==.Abandoned {
				_=storage_remove_run(&coordinator.paths)
			} else if app_install_run_document(app,&document) {
				request:=app.run.terminal==.Victory?Persistence_Request.Finalize_Victory:Persistence_Request.Finalize_Death
				_=persistence_finalize_terminal(coordinator,app,request)
				run_destroy(&app.run);app.run={}
			}
		} else do app.active_run_damaged=true
		run_document_destroy(&document)
	} else if run_status==.Future||run_status==.Corrupt||run_status==.Oversize {
		app.active_run_damaged=true
	}
	delete(run_data)
	return true
}

apply_platform_effects :: proc(app:^App,view:^View,audio:^Audio,effects:bit_set[Platform_Effect]) {
	when ARCH_ROGUE_WEB {
		// Fullscreen is the browser Fullscreen API on the canvas; it needs the
		// user's transient activation, which an option-row click still holds by
		// the time this effect runs inside the same requestAnimationFrame turn.
		if .Apply_Window in effects do web_apply_fullscreen(app.options.fullscreen)
		// No Apply_FPS: SetTargetFPS busy-waits inside EndDrawing, which would
		// burn a browser thread. requestAnimationFrame owns presentation pacing
		// and the fixed-step accumulator keeps simulation at 60 Hz regardless.
	} else {
		if .Apply_Window in effects && !ARCH_ROGUE_ANDROID {
			borderless:=rl.IsWindowState({.BORDERLESS_WINDOWED_MODE})
			if borderless!=app.options.fullscreen do rl.ToggleBorderlessWindowed()
		}
		if .Apply_FPS in effects do rl.SetTargetFPS(i32(frame_rate_cap_target(app.options.frame_rate_cap)))
	}
	if .Apply_Zoom in effects do view_apply_base_zoom(view,app.options.view_zoom)
	if .Apply_Audio in effects do audio_set_enabled(audio,app.options.audio_enabled)
	// Save_Options is consumed by the MX-save coordinator after platform effects.
}

platform_bind_view_layout :: proc(runtime:^Platform_Runtime,view:^View) {
	if runtime==nil||view==nil do return
	view.mobile_mode=runtime.mobile
	view.mobile_layout=runtime.layout
	view.mobile_layout_valid=runtime.mobile&&runtime.layout_status==.Valid
	view.mobile_joystick_vector=runtime.touch.joystick_vector
}

platform_rebuild_graphics :: proc(runtime:^Platform_Runtime,view:^View,assets:^Assets,app:^App) {
	if runtime==nil||view==nil||assets==nil||app==nil do return
	target:=view.camera.target
	base_zoom:=view.base_zoom
	view_shutdown(view)
	assets_unload(assets)
	assets_load(assets)
	view_init(view)
	if runtime.mobile&&!view_mobile_shader_preflight(view) do platform_log("ARCH_ROGUE_ANDROID_ERROR required GLES shaders failed after surface restore")
	view.camera.target=target
	view_apply_base_zoom(view,base_zoom)
	platform_bind_view_layout(runtime,view)
	if app.run.run_id!="" {
		assets_activate_player(assets,app.run.player.archetype)
		// A continue veil intentionally freezes frame dt at zero. Rehydrate the
		// CPU-authored masks now so the first restored lightmap is not all black.
		visual_mask_sync(&view.visible_mask,app,false,1)
		visual_mask_sync(&view.explored_mask,app,true,1)
	}
	runtime.graphics_reload_due=false
	platform_log(fmt.tprintf(
		"ARCH_ROGUE_GRAPHICS_RESTORED assets=%d shaders=%v masks=%v/%v",
		assets_loaded_texture_count(assets),view.effect_mask_shader_ready,
		view.visible_mask.ready,view.explored_mask.ready,
	))
}

platform_apply_lifecycle_result :: proc(
	runtime:^Platform_Runtime,
	result:Mobile_Lifecycle_Result,
	app:^App,
	view:^View,
	assets:^Assets,
	audio:^Audio,
	controller:^Controller_Runtime,
	persistence:^Persistence_Coordinator,
	fixed_step:^Mobile_Fixed_Step_State,
) {
	if runtime==nil||app==nil do return
	if .Cancel_Touches in result.effects {
		cancelled:=mobile_touch_cancel_all(&runtime.touch)
		if cancelled.intent.action1_released do _=app_apply(app,cancelled.intent)
		app.mobile_guard={}
		app.mobile_utility_open=false
		if view!=nil do view.mobile_joystick_vector={}
	}
	if .Clear_Play_Input in result.effects {
		app_clear_play_input(app)
		if controller!=nil do controller^={}
		clear(&app.run.sfx)
	}
	if .Pause_Audio in result.effects do audio_suspend(audio)
	if .Request_Checkpoint in result.effects && platform_live_descent(app) {
		app.run_dirty=true
		app.run_critical=true
	}
	if .Flush_Checkpoint_Bounded in result.effects && platform_live_descent(app) {
		flushed:=persistence_flush_for_suspend(persistence,app)
		platform_log(fmt.tprintf("ARCH_ROGUE_SUSPEND_CHECKPOINT durable=%v revision=%d",flushed,app.run.revision))
	}
	if .Invalidate_Graphics in result.effects do runtime.graphics_reload_due=true
	if .Refresh_Insets in result.effects {
		_=platform_refresh_mobile_layout(runtime)
		platform_bind_view_layout(runtime,view)
	}
	if .Recreate_Graphics in result.effects || (runtime.graphics_reload_due&&mobile_lifecycle_interactive(&runtime.lifecycle)) {
		platform_rebuild_graphics(runtime,view,assets,app)
	}

	if .Drop_Reconstructible_Caches in result.effects && view!=nil {
		view.ghost_weights={}
		view.ghost_weight_count=0
		view_clear_menu_click(view)
	}
	if .Reset_Accumulator in result.effects do mobile_fixed_step_reset(fixed_step,discard_next_dt=true)
	if .Show_Resume_Veil in result.effects {
		runtime.resume_gate=true
		runtime.resume_return=result.resume_return
		app.mode=.Resume_Veil
	}
}

// Explicit runtime phases shared by every platform entry. Desktop and Android
// run game_init + game_frame inside a blocking loop; the web entry drives the
// same three phases from browser requestAnimationFrame. Production web builds
// must not use ASYNCIFY, so no phase may block on presentation or IO timing.

Dev_Open_Panel :: enum u8 {
	None,
	Inventory,
	Character,
	Shop,
}

Game_Boot_Config :: struct {
	window_width:              int,
	window_height:             int,
	seed:                      u64,
	shot_path:                 string,
	shot_frame:                int,
	capture_scenario:          MX6_Capture_Scenario,
	mx7_capture_scenario:      MX7_Capture_Scenario,
	mx_story_capture_scenario: MX_Story_Capture_Scenario,
	mx_save_capture_scenario:  MX_Save_Capture_Scenario,
	mx7_theme:                 int,
	mx7_dark:                  int,
	mx7_open_door:             bool,
	mx7_perf_enabled:          bool,
	mx_save_perf_enabled:      bool,
	perf_warmup:               int,
	perf_frames:               int,
	capture_direction:         Vec2,
	dev_play:                  bool,
	dev_archetype:             Archetype_Id,
	dev_archetype_valid:       bool,
	dev_depth:                 int,
	dev_open:                  Dev_Open_Panel,
	dev_bag:                   int,
	dev_spawn_stairs:          bool,
	dev_zoom:                  f32,
	dev_zoom_valid:            bool,
	dev_reveal:                bool,
	dev_controls:              bool,
	dev_mist_off:              bool,
	dev_lighting:              int,
	save_trace:                bool,
	smoke_frames:              int, // >0: draw N frames, then exit 0 (depot smoke gate)
	perf_storage_directory:    string,
}

game_boot_config_default :: proc() -> Game_Boot_Config {
	return {
		window_width = 1280,
		window_height = 720,
		shot_frame = 40,
		mx7_theme = -1,
		mx7_dark = -1,
		dev_lighting = -1,
		perf_warmup = 120,
		perf_frames = 600,
		capture_direction = {1, 1},
	}
}

Game_Runtime :: struct {
	config:               Game_Boot_Config,
	assets:               Assets,
	audio:                Audio,
	app:                  App,
	platform:             Platform_Runtime,
	persistence:          Persistence_Coordinator,
	steam:                Steam_State,
	view:                 View,
	controller:           Controller_Runtime,
	music:                Music_Director,
	fixed_step:           Mobile_Fixed_Step_State,
	frame_count:          int,
	fixed_capture:        bool,
	perf_enabled:         bool,
	perf_samples:         [dynamic]f32,
	perf_resources_ready: bool,
	capture_stage_ok:     bool,
	running:              bool,
}

game_init :: proc(rt: ^Game_Runtime, boot: Game_Boot_Config) -> bool {
	rt.config = boot
	config := &rt.config
	when ARCH_ROGUE_ANDROID {
		// Zero requests raylib's physical NativeWindow dimensions instead of a
		// scaled 1280x720 framebuffer. Android owns one fullscreen surface.
		rl.SetConfigFlags({.FULLSCREEN_MODE})
		rl.InitWindow(0,0,"Arch Rogue " + VERSION)
	} else when ARCH_ROGUE_WEB {
		// The shell owns canvas CSS size; the boot config carries the initial
		// framebuffer size and later browser resizes flow through SetWindowSize.
		rl.InitWindow(i32(config.window_width), i32(config.window_height), "Arch Rogue " + VERSION)
	} else {
		rl.SetConfigFlags({.WINDOW_RESIZABLE})
		rl.InitWindow(i32(config.window_width), i32(config.window_height), "Arch Rogue " + VERSION)
		rl.SetWindowMinSize(640,480)
	}
	rl.SetExitKey(.KEY_NULL) // ESC navigates, it does not quit

	if (config.mx_story_capture_scenario != .None || config.mx_save_capture_scenario != .None) &&
		(int(rl.GetScreenWidth()) != config.window_width || int(rl.GetScreenHeight()) != config.window_height) {
		platform_log("UI_CAPTURE_ERROR requested window dimensions were not honored")
		rl.CloseWindow()
		return false
	}

	assets_load(&rt.assets)
	when ARCH_ROGUE_WEB {
		// Browser audio contexts start suspended until a user gesture. The web
		// entry initializes audio from the first gesture callback instead.
	} else {
		audio_init(&rt.audio)
	}

	app_init(&rt.app, config.seed)
	platform_runtime_init(&rt.platform, rt.app.mode)
	if rt.platform.mobile do rt.app.input_modality = .Touch

	rt.fixed_capture = config.capture_scenario != .None || config.mx7_capture_scenario != .None ||
		config.mx_story_capture_scenario != .None || config.mx_save_capture_scenario != .None
	rt.perf_enabled = config.mx7_perf_enabled || config.mx_save_perf_enabled
	normal_persistence_enabled := !rt.fixed_capture && !config.mx7_perf_enabled &&
		!config.mx_save_perf_enabled && config.shot_path == "" && !config.dev_play
	if config.mx_save_perf_enabled {
		when ARCH_ROGUE_WEB {
			platform_log("MX_SAVE_PERF_ERROR unsupported on web")
			game_init_fail_before_view(rt)
			return false
		} else {
			paths, paths_ok := storage_paths_from_directory(config.perf_storage_directory)
			if config.perf_storage_directory == "" || !paths_ok {
				platform_log("MX_SAVE_PERF_ERROR temporary paths unavailable")
				game_init_fail_before_view(rt)
				return false
			}
			rt.persistence = {paths = paths, ready = true}
			if !save_worker_init(&rt.persistence.worker) {
				storage_paths_destroy(&rt.persistence.paths)
				rt.persistence = {}
				platform_log("MX_SAVE_PERF_ERROR save worker unavailable")
				game_init_fail_before_view(rt)
				return false
			}
		}
	} else if normal_persistence_enabled {
		persistence_ready := persistence_coordinator_init(&rt.persistence, &rt.app, config.seed)
		if !persistence_ready && config.save_trace {
			platform_log("MX_SAVE_TRACE persistence coordinator initialization failed")
		}
	}
	if rt.app.profile.profile_id == "" {
		profile_id := persistence_new_profile_id(config.seed)
		profile_init(&rt.app.profile, profile_id)
		delete(profile_id)
	}
	rt.persistence.steam = &rt.steam
	if rt.persistence.ready {
		// DRM-free stance kept from pygame: a bare download relaunches through
		// Steam via RestartAppIfNecessary, which surfaces here as a quit.
		if steam_startup(&rt.steam, rt.persistence.paths.directory) {
			rt.app.quit_requested = true
		}
		// Retroactive first-Steam-launch grants: a veteran profile earns its
		// achievements at startup, not after one more run.
		if persistence_apply_achievements(&rt.persistence, &rt.app, false, {}) {
			_ = persistence_write_profile_sync(&rt.persistence, &rt.app)
		}
	}
	when ARCH_ROGUE_WEB {
		// Browser fullscreen is transient and gesture-gated; never restore it
		// from persisted options at boot. The user re-enters it via the shell
		// button or the options row.
		rt.app.options.fullscreen = false
	}
	if rt.fixed_capture || rt.perf_enabled {
		// Validation profiles are complete and ephemeral: persisted user graphics,
		// accessibility, difficulty, and zoom cannot change acceptance workloads.
		rt.app.options.fullscreen = false
		if config.mx_save_capture_scenario != .None && config.window_width == 3840 && config.window_height == 2160 {
			rt.app.options.fullscreen = true
		}
		rt.app.options.audio_enabled = false
		rt.app.options.view_zoom = OPTIONS_VIEW_ZOOM_DEFAULT
		if config.capture_scenario != .None {
			rt.app.options.mist_enabled = false
		}
		if config.mx7_capture_scenario != .None || config.mx_story_capture_scenario != .None ||
			config.mx_save_capture_scenario != .None {
			rt.app.options.lighting_enabled = true
			rt.app.options.mist_enabled = false
			rt.app.options.minimap_visible = true
		}
		if rt.perf_enabled {
			rt.app.options.lighting_enabled = true
			rt.app.options.mist_enabled = true
			rt.app.options.minimap_visible = false
			rt.app.options.difficulty = .Medium
		}
		if config.capture_scenario != .None && config.dev_lighting >= 0 {
			rt.app.options.lighting_enabled = config.dev_lighting != 0
		}
	}
	rt.app.minimap_visible = rt.app.options.minimap_visible
	view_init(&rt.view)
	platform_bind_view_layout(&rt.platform, &rt.view)
	if rt.platform.mobile && !view_mobile_shader_preflight(&rt.view) {
		platform_log("ARCH_ROGUE_ANDROID_ERROR required GLES shaders failed preflight")
	}
	rt.controller = {}
	apply_platform_effects(&rt.app, &rt.view, &rt.audio, {.Apply_Window, .Apply_FPS, .Apply_Zoom, .Apply_Audio})
	if rt.perf_enabled {
		rl.SetTargetFPS(0)
		when !ARCH_ROGUE_WEB {
			// Desktop performance evidence must include a real gameplay mix, not
			// finish before the 9.6-second one-stream boot intro hands off.
			rt.audio.music_library.has_boot = false
		}
	}
	if !rt.fixed_capture && !rt.perf_enabled && config.dev_zoom_valid {
		view_apply_base_zoom(&rt.view, config.dev_zoom, clamp_to_options = false)
	}
	if config.dev_reveal do rt.app.dev_reveal = true
	// Unpersisted A/B hook for benchmarks and screenshot comparisons.
	if !rt.perf_enabled && config.dev_mist_off do rt.app.options.mist_enabled = false
	if config.dev_controls do rt.app.dev_controls = true
	if config.dev_play {
		_ = app_apply(&rt.app, Intent{confirm = true}) // Title -> Select
		if config.dev_archetype_valid {
			rt.app.select_index = int(config.dev_archetype)
		}
		if app_apply(&rt.app, Intent{confirm = true}) { // Select -> Playing
			assets_activate_player(&rt.assets, rt.app.run.player.archetype)
			view_center_on(&rt.view, world_from_tile(run_spawn_point(&rt.app.run)))
		}
		// Dev: start deeper / spawn at the stairs room (boss arenas).
		if config.dev_depth > 0 {
			for rt.app.run.depth < config.dev_depth do run_descend(&rt.app.run)
			view_center_on(&rt.view, world_from_tile(run_spawn_point(&rt.app.run)))
		}
		// Dev: open a panel immediately for UI screenshots. dev_bag copies up to
		// n shopkeeper stock items into the bag so item rows and the selected-item
		// panel can be captured without playing to loot.
		switch config.dev_open {
		case .Inventory: rt.app.inventory_open = true
		case .Character: rt.app.character_open = true
		case .Shop: rt.app.shop_open = true
		case .None:
		}
		if config.dev_bag > 0 && rt.app.run.has_shopkeeper {
			keeper := &rt.app.run.shopkeeper
			player := &rt.app.run.player
			for i in 0 ..< min(config.dev_bag, keeper.stock_count) {
				if player.bag_count >= BAG_CAPACITY do break
				player.bag[player.bag_count] = keeper.stock[i]
				player.bag_count += 1
			}
		}
		if rt.perf_enabled {
			if rt.app.story_panel.active {
				app_story_panel_reveal(&rt.app)
				_ = app_apply(&rt.app, Intent{confirm = true})
			}
			// Raw dev descent queues the target floor's omen. Profiling needs an
			// active crowded floor, not a frozen modal, so discard only the pending
			// presentation request after retaining the generated story state.
			rt.app.run.story_runtime.requests = {}
			app_story_runtime_reset(&rt.app)
			if !mx7_stage_perf(&rt.app, &rt.view, config.mx7_theme, config.mx7_dark) {
				platform_log("MX7_PERF_ERROR staging failed")
				game_init_fail_after_view(rt)
				return false
			}
			rt.app.minimap_visible = false
		}
		if config.dev_spawn_stairs {
			s := rt.app.run.dungeon.stairs
			spots := [4]Vec2{
				{f32(s.x) - 2.5, f32(s.y) + 0.5},
				{f32(s.x) + 0.5, f32(s.y) - 2.5},
				{f32(s.x) + 3.5, f32(s.y) + 0.5},
				{f32(s.x) + 0.5, f32(s.y) + 3.5},
			}
			for spot in spots {
				if !blocked_for_radius(&rt.app.run.dungeon, spot.x, spot.y, block_stairs = true) {
					rt.app.run.player.pos = spot
					rt.app.run.player.prev_pos = spot
					view_center_on(&rt.view, world_from_tile(spot))
					break
				}
			}
		}
	}

	// Sim advances in fixed SIM_DT steps; rendering runs at display rate and
	// interpolates between the last two sim states.
	rt.fixed_step = {}
	rt.frame_count = 0
	rt.perf_samples = make([dynamic]f32, 0, config.perf_frames)
	rt.perf_resources_ready = true
	rt.capture_stage_ok = true
	rt.running = true
	return true
}

@(private = "file")
game_init_fail_before_view :: proc(rt: ^Game_Runtime) {
	persistence_coordinator_destroy(&rt.persistence)
	run_destroy(&rt.app.run)
	profile_destroy(&rt.app.profile)
	game_shutdown_audio(rt)
	assets_unload(&rt.assets)
	rl.CloseWindow()
}

@(private = "file")
game_init_fail_after_view :: proc(rt: ^Game_Runtime) {
	view_shutdown(&rt.view)
	persistence_coordinator_destroy(&rt.persistence)
	run_destroy(&rt.app.run)
	profile_destroy(&rt.app.profile)
	game_shutdown_audio(rt)
	assets_unload(&rt.assets)
	rl.CloseWindow()
}

@(private = "file")
game_shutdown_audio :: proc(rt: ^Game_Runtime) {
	when ARCH_ROGUE_WEB {
		// Audio initializes lazily on the first browser gesture and may never
		// have been created; there is no meaningful device teardown on web.
		if rt.audio.ready do audio_shutdown(&rt.audio)
	} else {
		audio_shutdown(&rt.audio)
	}
}

game_frame :: proc(rt: ^Game_Runtime) -> bool {
	if !rt.running do return false
	config := &rt.config
	app := &rt.app
	if app.quit_requested {
		rt.running = false
		return false
	}
	if rt.platform.mobile {
		lifecycle_result := platform_reduce_android_events(&rt.platform, app)
		platform_apply_lifecycle_result(
			&rt.platform, lifecycle_result, app, &rt.view, &rt.assets, &rt.audio,
			&rt.controller, &rt.persistence, &rt.fixed_step,
		)
		if rt.platform.lifecycle.destroyed {
			app.quit_requested = true
			return true
		}
		if !mobile_lifecycle_interactive(&rt.platform.lifecycle) {
			persistence_update_scheduler(&rt.persistence, app, rl.GetTime())
			platform_wait_suspended(&rt.platform)
			free_all(context.temp_allocator)
			return true
		}
	}
	when ARCH_ROGUE_WEB {
		if web_consume_audio_unlock() && !rt.audio.ready {
			audio_init(&rt.audio)
			audio_set_enabled(&rt.audio, app.options.audio_enabled)
		}
		if web_consume_visibility_resume() {
			// requestAnimationFrame stops while the tab is hidden. Discard the
			// stale frame gap so the fixed-step accumulator cannot catch-up
			// spiral past MAX_FRAME_DT on tab return.
			mobile_fixed_step_reset(&rt.fixed_step, discard_next_dt = true)
		}
	}
	when !ARCH_ROGUE_WEB {
		// raylib's web WindowShouldClose yields via emscripten_sleep, which is
		// forbidden without ASYNCIFY. Browsers close tabs, not windows: the web
		// quit path is the in-game state machine plus pagehide checkpoints.
		if rl.WindowShouldClose() && app.mode != .Save_Wait && app.mode != .Save_Error {
			live_run := platform_live_descent(app)
			if rt.platform.mobile {
				if rt.persistence.ready && live_run do _ = persistence_flush_for_suspend(&rt.persistence, app)
				app.quit_requested = true
				return true
			} else if rt.persistence.ready && live_run {
				app.persistence_request = .Save_Quit
				app.persistence_return = .Paused
				app.mode = .Save_Wait
				rt.persistence.save_wait_presented = false
				app_clear_play_input(app)
			} else {
				app.quit_requested = true
				return true
			}
		}
	}
	raw_frame_dt := rl.GetFrameTime()
	frame_dt := min(raw_frame_dt, f32(MAX_FRAME_DT))
	if rt.fixed_capture do frame_dt = SIM_DT
	if rt.platform.resume_gate do frame_dt = 0

	view_update(&rt.view, frame_dt)
	mode_was := app.mode
	shop_was_open := app.shop_open
	intent: Intent
	resume_gate_was := rt.platform.resume_gate
	if !rt.fixed_capture do intent = platform_collect_intent(&rt.platform, app, &rt.view, &rt.controller)
	if resume_gate_was && !rt.platform.resume_gate && app.mode == .Playing do audio_resume(&rt.audio)
	if app_apply(app, intent) {
		if mode_was == .Select && app.mode == .Playing {
			assets_activate_player(&rt.assets, app.run.player.archetype)
		}
		view_center_on(&rt.view, world_from_tile(run_spawn_point(&app.run)))
	}
	// Reducers can generate a floor or rebuild presentation resources. Start
	// ordinary UI cues only after that work has completed.
	if cue, has_cue := audio_cue_for_transition(intent, mode_was, app.mode); has_cue do audio_play_cue(&rt.audio, cue)
	if rt.platform.mobile && !rt.platform.resume_gate && mode_was != .Playing && app.mode == .Playing do audio_resume(&rt.audio)
	if app.mode == .Save_Wait && mode_was != .Save_Wait {
		rt.persistence.save_wait_presented = false
		if !rt.persistence.ready do persistence_fail_request(app, app.persistence_request, .Write, app.persistence_return)
	}
	if shop_was_open != app.shop_open do view_clear_menu_click(&rt.view)
	if mode_was != app.mode && (mode_was == .Select || app.mode == .Select) {
		view_clear_menu_click(&rt.view)
	}
	when ARCH_ROGUE_WEB {
		// Entering a run is the fetch point for the lazy web asset packs: the
		// chosen archetype's full clips, social-room actors, and boss sheets
		// stream in behind procedural fallbacks and adopt on arrival.
		if mode_was != app.mode && app.mode == .Playing && (mode_was == .Select || mode_was == .Resume_Veil) {
			web_packs_on_run_start(app.run.player.archetype)
		}
	}
	if card(app.platform_effects) > 0 {
		effects := app.platform_effects
		apply_platform_effects(app, &rt.view, &rt.audio, effects)
		if .Save_Options in effects && rt.persistence.ready do _ = persistence_enqueue_options(&rt.persistence, app)
		app.platform_effects = {}
	}
	if config.mx_save_perf_enabled && rt.frame_count == config.perf_warmup {
		rt.persistence.run_snapshot_count = 0
		rt.persistence.run_snapshot_total_ms = 0
		rt.persistence.run_snapshot_max_ms = 0
	}
	if config.mx_save_perf_enabled && rt.frame_count >= config.perf_warmup &&
		(rt.frame_count - config.perf_warmup) % 60 == 0 && !rt.persistence.run_write_in_flight {
		app.run_dirty = true
		app.run_critical = true
		app.run_dirty_serial += 1
	}
	persistence_update_scheduler(&rt.persistence, app, rl.GetTime())
	if app.mode == .Resume_Veil && mode_was != .Resume_Veil {
		assets_activate_player(&rt.assets, app.run.player.archetype)
		view_center_on(&rt.view, world_from_tile(app.run.player.pos))
		rt.controller = {}
		view_clear_menu_click(&rt.view)
	}

	if rt.fixed_capture {
		app_tick(app)
		mobile_fixed_step_reset(&rt.fixed_step)
	} else {
		simulation_enabled := !rt.platform.resume_gate && (!rt.platform.mobile || mobile_lifecycle_interactive(&rt.platform.lifecycle))
		steps := mobile_fixed_step_advance(&rt.fixed_step, frame_dt, SIM_DT, f32(MAX_FRAME_DT), simulation_enabled)
		for _ in 0 ..< steps do app_tick(app)
	}
	persistence_update_scheduler(&rt.persistence, app, rl.GetTime())
	steam_frame(&rt.steam, &app.profile)
	if rt.perf_enabled do mx7_perf_refresh_visuals(&app.run)
	alpha := rt.fixed_capture ? f32(1) : rt.fixed_step.accumulator / SIM_DT
	// Modal/non-playing states freeze at the latest authoritative pose.
	// Otherwise a >60 Hz renderer repeatedly interpolates the final movement
	// segment while the inventory, death, or victory overlay pauses the sim.
	if app.mode != .Playing || app.inventory_open || app.character_open || app.shop_open ||
		app_play_modal_open(app) {
		alpha = 1
	}
	audio_drain(&rt.audio, &app.run)
	// The Loop advances on presentation frames, never sim ticks: music keeps
	// playing through menus and pause, starts at audio-ready (the web gesture
	// gate), and freezes while suspended. The clock is disciplined by the live
	// PCM mixer's callback cursor so boundary events land on audible frames.
	music_runtime := music_runtime_state_for(app)
	if rt.audio.ready && !rt.audio.suspended {
		reference_ms := audio_music_reference_phase_ms(&rt.audio, &rt.music)
		music_director_update(&rt.music, &rt.audio.music_library, music_mix_for(app), f64(frame_dt) * 1000, reference_ms)
	}
	audio_music_update(
		&rt.audio,
		&rt.music,
		MUSIC_VOLUME_FACTORS[music_volume_normalize(app.options.music_volume)],
		music_runtime,
	)
	when ARCH_ROGUE_WEB {
		// Pack callbacks only queue ownership. Adopt one actor in a quiet SFX
		// window so the main-thread miniaudio callback is never starved mid-cue.
		web_pack_adoptions_tick(rt)
	}

	if app.mode == .Playing && !app.inventory_open && !app.character_open && !app.shop_open &&
		!app_play_modal_open(app) {
		player := &app.run.player
		pos := player.prev_pos + (player.pos - player.prev_pos) * alpha
		view_follow(&rt.view, world_from_tile(pos), frame_dt)
	}

	// Stage on the exact frame that will be captured, after ordinary simulation
	// and immediately before rendering, so transient action/effect state is fresh.
	if config.shot_path != "" && rt.frame_count + 1 == config.shot_frame {
		if config.capture_scenario != .None do mx6_stage_capture(app, &rt.view, config.capture_scenario, config.capture_direction)
		if config.mx7_capture_scenario != .None do rt.capture_stage_ok = mx7_stage_capture(app, &rt.view, config.mx7_capture_scenario, config.mx7_theme, config.mx7_dark, config.mx7_open_door)
		if config.mx_story_capture_scenario != .None do rt.capture_stage_ok = mx_story_stage_capture(app, config.mx_story_capture_scenario)
		if config.mx_save_capture_scenario != .None do rt.capture_stage_ok = mx_save_stage_capture(app, config.mx_save_capture_scenario)
		if !rt.capture_stage_ok {
			platform_log("CAPTURE_ERROR staging failed")
			rt.running = false
			return false
		}
		alpha = 1
	}
	draw_frame(&rt.view, app, &rt.assets, alpha)
	if rt.platform.mobile && !rt.platform.ready_marker_emitted {
		mist_shader_ready := rt.view.mist != nil && rt.view.mist.ready && rt.view.mist.shader_ok
		if assets_ready(&rt.assets) && rt.view.effect_mask_shader_ready && mist_shader_ready && rt.persistence.ready && audio_loaded_cue_count(&rt.audio) > 0 {
			rt.platform.ready_marker_emitted = true
			platform_log(fmt.tprintf(
				"ARCH_ROGUE_READY version=%s native=%dx%d assets=%d shaders=2/2 storage=ok audio=%d",
				VERSION, rt.platform.metrics.surface_width, rt.platform.metrics.surface_height,
				assets_loaded_texture_count(&rt.assets), audio_loaded_cue_count(&rt.audio),
			))
		}
	}
	if app.mode == .Save_Wait do rt.persistence.save_wait_presented = true

	rt.frame_count += 1
	if rt.perf_enabled && rt.frame_count > config.perf_warmup {
		mist_ready := rt.view.mist != nil && rt.view.mist.ready && rt.view.mist.shader_ok && rt.view.mist.field_ready
		rt.perf_resources_ready = rt.perf_resources_ready && rt.view.lighting_ready && rt.view.effect_mask_shader_ready && mist_ready
		when !ARCH_ROGUE_WEB {
			music_ready := rt.audio.ready &&
				audio_music_loaded_stream_count(&rt.audio) == 1 &&
				audio_music_active_layer_count(&rt.audio) > 0 &&
				audio_music_callback_service_count(&rt.audio) > 0 &&
				rt.audio.music_recovery_count == 0
			rt.perf_resources_ready = rt.perf_resources_ready && music_ready
		}
		append(&rt.perf_samples, raw_frame_dt * 1000)
		if len(rt.perf_samples) >= config.perf_frames {
			game_report_perf(rt)
			rt.running = false
			return false
		}
	}
	if config.shot_path != "" && rt.frame_count == config.shot_frame && rt.capture_stage_ok {
		rl.TakeScreenshot(strings.clone_to_cstring(config.shot_path, context.temp_allocator))
		rt.running = false
		return false
	}

	free_all(context.temp_allocator)
	return true
}

@(private = "file")
game_report_perf :: proc(rt: ^Game_Runtime) {
	config := &rt.config
	app := &rt.app
	for i in 1 ..< len(rt.perf_samples) {
		value := rt.perf_samples[i]
		j := i
		for j > 0 && rt.perf_samples[j-1] > value {
			rt.perf_samples[j] = rt.perf_samples[j-1]
			j -= 1
		}
		rt.perf_samples[j] = value
	}
	total: f32
	long_frames := 0
	for sample in rt.perf_samples {
		total += sample
		// The web acceptance gate bounds frame intervals at two 60 Hz vsync
		// periods rather than a raw p95 threshold.
		if sample > 33.34 do long_frames += 1
	}
	mean := total / f32(len(rt.perf_samples))
	p95 := mx7_perf_percentile(rt.perf_samples[:], .95)
	p99 := mx7_perf_percentile(rt.perf_samples[:], .99)
	max_ms := rt.perf_samples[len(rt.perf_samples)-1]
	if config.mx_save_perf_enabled {
		_ = persistence_drain_worker(&rt.persistence)
		saved_data, saved_status := storage_recover_document(rt.persistence.paths.run, .Run)
		save_valid := false
		if saved_status == .Valid {
			document, decoded := persistence_decode_run(saved_data)
			save_valid = decoded == .Valid && document.payload.terminal == .Active
			run_document_destroy(&document)
		}
		delete(saved_data)
		snapshot_mean := rt.persistence.run_snapshot_count > 0 ? rt.persistence.run_snapshot_total_ms / f64(rt.persistence.run_snapshot_count) : f64(0)
		mist_allocated := rt.view.mist != nil
		mist_texture_ready := mist_allocated && rt.view.mist.ready
		mist_shader_ready := mist_allocated && rt.view.mist.shader_ok
		mist_field_ready := mist_allocated && rt.view.mist.field_ready
		mist_ready := mist_allocated && rt.view.mist.ready && rt.view.mist.shader_ok && rt.view.mist.field_ready
		report := fmt.tprintf("MX_SAVE_PERF {{\"frames\":%d,\"mean_ms\":%.3f,\"p95_ms\":%.3f,\"p99_ms\":%.3f,\"max_ms\":%.3f,\"mean_fps\":%.2f,\"snapshot_count\":%d,\"snapshot_mean_ms\":%.3f,\"snapshot_max_ms\":%.3f,\"save_valid\":%v,\"lighting_ready\":%v,\"effect_ready\":%v,\"mist_ready\":%v,\"mist_allocated\":%v,\"mist_texture_ready\":%v,\"mist_shader_ready\":%v,\"mist_field_ready\":%v,\"mist_enabled\":%v,\"modal_open\":%v,\"mode\":\"%v\",\"resources_ready\":%v}}",
			len(rt.perf_samples), mean, p95, p99, max_ms, mean > 0 ? 1000/mean : f32(0),
			rt.persistence.run_snapshot_count, snapshot_mean, rt.persistence.run_snapshot_max_ms,
			save_valid, rt.view.lighting_ready, rt.view.effect_mask_shader_ready, mist_ready,
			mist_allocated, mist_texture_ready, mist_shader_ready, mist_field_ready,
			app.options.mist_enabled, app_play_modal_open(app), app.mode, rt.perf_resources_ready)
		platform_report_line(report)
	} else {
		report := fmt.tprintf("MX7_PERF {{\"frames\":%d,\"mean_ms\":%.3f,\"p95_ms\":%.3f,\"p99_ms\":%.3f,\"max_ms\":%.3f,\"mean_fps\":%.2f,\"long_frames_33ms\":%d,\"music_mix\":\"%s\",\"music_streams\":%d,\"music_layers\":%d,\"music_callbacks\":%d,\"music_recoveries\":%d,\"resources_ready\":%v}}",
			len(rt.perf_samples), mean, p95, p99, max_ms, mean > 0 ? 1000/mean : f32(0), long_frames,
			rt.music.active_mix, audio_music_loaded_stream_count(&rt.audio),
			audio_music_active_layer_count(&rt.audio), audio_music_callback_service_count(&rt.audio),
			rt.audio.music_recovery_count, rt.perf_resources_ready)
		platform_report_line(report)
	}
}

game_shutdown :: proc(rt: ^Game_Runtime) {
	view_shutdown(&rt.view)
	delete(rt.perf_samples)
	rt.perf_samples = nil
	steam_shutdown(&rt.steam)
	persistence_coordinator_destroy(&rt.persistence)
	run_destroy(&rt.app.run)
	profile_destroy(&rt.app.profile)
	game_shutdown_audio(rt)
	assets_unload(&rt.assets)
	rl.CloseWindow()
	rt.running = false
}

// Translate raw input into sim intents; the sim never sees raylib.
collect_intent :: proc(app: ^App, view: ^View, controller: ^Controller_Runtime) -> (intent: Intent) {
	mouse := rl.GetMousePosition()
	mouse_delta := rl.GetMouseDelta()
	mouse_moved := mouse_delta.x != 0 || mouse_delta.y != 0
	mouse_used := mouse_moved || rl.IsMouseButtonPressed(.LEFT) || rl.IsMouseButtonDown(.LEFT)
	ctrl_down := rl.IsKeyDown(.LEFT_CONTROL) || rl.IsKeyDown(.RIGHT_CONTROL)
	collect_controller_intent(app,controller,&intent)
	if mouse_used && !controller.right_aim_this_frame {
		controller.aim_mode = false
		controller.keyboard_aim = false
		if app.mode == .Playing do intent.aim = {}
	}
	intent.toggle_fullscreen = rl.IsKeyPressed(.F11)
	// Pygame observes KEYUP across every modal. Keep the keyboard release beside
	// the already-global controller release so pause/options cannot trap a charge.
	intent.action1_released = intent.action1_released || rl.IsKeyReleased(.ONE)

	// Pygame reserves plain wheel for contextual panels. The viewport changes
	// only under Ctrl; an unmodified wheel over the visible minimap adjusts its
	// own scale instead.
	wheel := rl.GetMouseWheelMove()
	if app.mode == .Playing && wheel != 0 {
		if ctrl_down {
			view_zoom_at_cursor(view, wheel)
			app.options.view_zoom=view.base_zoom
			app_mark_options_changed(app)
		} else if app.minimap_visible && !app.inventory_open && !app.character_open && !app.shop_open &&
			rl.CheckCollisionPointRec(mouse, minimap_rect(app)) {
			// Preserve multi-notch wheel events; fractional touchpad deltas still
			// advance one step in their direction.
			intent.minimap_zoom = int(wheel)
			if intent.minimap_zoom == 0 do intent.minimap_zoom = wheel > 0 ? 1 : -1
		}
	}

	switch app.mode {
	case .Title:
		if mouse_moved {
			if index,found:=title_row_at(mouse);found {intent.menu_index=index;intent.menu_index_valid=true}
		}
		if rl.IsMouseButtonPressed(.LEFT) {
			if index,found:=title_row_at(mouse);found {intent.menu_index=index;intent.menu_index_valid=true;intent.confirm=true}
		}
		if rl.IsKeyPressed(.UP) do intent.menu_delta-=1
		if rl.IsKeyPressed(.DOWN) do intent.menu_delta+=1
		if rl.IsKeyPressed(.ENTER)||rl.IsKeyPressed(.KP_ENTER) do intent.confirm=true
		if rl.IsKeyPressed(.R) {intent.menu_index=int(Title_Action.Resume);intent.menu_index_valid=true;intent.confirm=true}
		if rl.IsKeyPressed(.N) {intent.menu_index=int(Title_Action.New_Run);intent.menu_index_valid=true;intent.confirm=true}
		if rl.IsKeyPressed(.C) {intent.menu_index=int(Title_Action.Chronicle);intent.menu_index_valid=true;intent.confirm=true}
		if rl.IsKeyPressed(.O) {intent.menu_index=int(Title_Action.Options);intent.menu_index_valid=true;intent.confirm=true}
		if rl.IsKeyPressed(.Q) {intent.menu_index=int(Title_Action.Quit);intent.menu_index_valid=true;intent.confirm=true}
		if rl.IsKeyPressed(.ESCAPE) do intent.back=true
	case .Select:
		if rl.IsMouseButtonPressed(.LEFT) {
			if index, found := select_slot_at(app, mouse); found {
				click_intent := desktop_archetype_click_intent(app.select_index, index)
				intent.menu_index = click_intent.menu_index
				intent.menu_index_valid = click_intent.menu_index_valid
				intent.confirm = intent.confirm || click_intent.confirm
				intent.pointer_confirm = intent.pointer_confirm || click_intent.pointer_confirm
			}
		}
		if rl.IsKeyPressed(.UP) || rl.IsKeyPressed(.LEFT) do intent.menu_delta -= 1
		if rl.IsKeyPressed(.DOWN) || rl.IsKeyPressed(.RIGHT) do intent.menu_delta += 1
		if rl.IsKeyPressed(.ENTER) || rl.IsKeyPressed(.KP_ENTER) {
			intent.confirm = true
		}
		select_keys := [5]rl.KeyboardKey{.ONE, .TWO, .THREE, .FOUR, .FIVE}
		for key, index in select_keys {
			if rl.IsKeyPressed(key) {
				intent.menu_index = index
				intent.menu_index_valid = true
				intent.confirm = true
			}
		}
		if rl.IsKeyPressed(.BACKSPACE) || rl.IsKeyPressed(.ESCAPE) do intent.back = true
	case .Playing:
		// Story panels and minigames own the complete desktop input context. Return
		// before any gameplay/menu toggles so no movement, attacks, zoom, or
		// inventory action can leak through the paused live scene.
		if app_play_modal_open(app) {
			if app_story_minigame_active(app) {
				if rl.IsKeyPressed(.LEFT) do intent.menu_horizontal-=1
				if rl.IsKeyPressed(.RIGHT) do intent.menu_horizontal+=1
				if rl.IsKeyPressed(.UP) do intent.menu_delta-=1
				if rl.IsKeyPressed(.DOWN) do intent.menu_delta+=1
			} else {
				if rl.IsKeyPressed(.UP)||rl.IsKeyPressed(.LEFT) do intent.menu_delta-=1
				if rl.IsKeyPressed(.DOWN)||rl.IsKeyPressed(.RIGHT) do intent.menu_delta+=1
			}
			if rl.IsKeyPressed(.ENTER)||rl.IsKeyPressed(.KP_ENTER)||rl.IsKeyPressed(.SPACE)||rl.IsKeyPressed(.E) do intent.confirm=true
			if rl.IsKeyPressed(.ESCAPE)||rl.IsKeyPressed(.BACKSPACE) do intent.back=true

			hit:=story_modal_hit_test(app,int(rl.GetScreenWidth()),int(rl.GetScreenHeight()),Vec2(mouse))
			if hit.kind==.Choice||hit.kind==.Minigame_Cell {
				intent.menu_index=hit.index
				intent.menu_index_valid=true
			}
			if rl.IsMouseButtonPressed(.LEFT)&&hit.kind!=.None {
				intent.pointer_confirm=true
			}
			return intent
		}
		if ctrl_down && rl.IsKeyPressed(.M) do intent.toggle_minimap = true
		if rl.IsKeyPressed(.I) do intent.toggle_inventory = true
		if rl.IsKeyPressed(.C) do intent.open_character = true
			if app.character_open {
				if rl.IsMouseButtonPressed(.LEFT) {
					if tab, found := character_tab_at(mouse); found {
						intent.character_tab = tab
						intent.character_tab_valid = true
					}
				}
				if rl.IsKeyPressed(.TAB) do intent.tab=true
			if rl.IsKeyPressed(.ONE) {
				intent.character_tab = .Overview
				intent.character_tab_valid = true
			}
			if rl.IsKeyPressed(.TWO) {
				intent.character_tab = .Disciplines
				intent.character_tab_valid = true
			}
			// 1/2 are absolute tabs; directions enter and traverse the 4x5
			// discipline grid. This closes the pygame desktop sheet's otherwise
			// mouse/controller-only horizontal-navigation gap.
			if rl.IsKeyPressed(.LEFT) do intent.menu_horizontal-=1
			if rl.IsKeyPressed(.RIGHT) do intent.menu_horizontal+=1
			if rl.IsKeyPressed(.UP) do intent.menu_delta-=1
			if rl.IsKeyPressed(.DOWN) do intent.menu_delta+=1
			if mouse_moved && app.character_tab==.Disciplines {
				if index,found:=discipline_cell_at(mouse);found {intent.menu_index=index;intent.menu_index_valid=true}
			}
			if rl.IsMouseButtonPressed(.LEFT)&&app.character_tab==.Disciplines {
				if index,found:=discipline_cell_at(mouse);found {intent.menu_index=index;intent.menu_index_valid=true;intent.confirm=true}
			}
			if rl.IsKeyPressed(.ENTER)||rl.IsKeyPressed(.KP_ENTER) do intent.confirm=true
			if rl.IsKeyPressed(.ESCAPE) do intent.back=true
			return intent
		}
		if !app.inventory_open && !app.shop_open && app.run.player.memory_tokens > 0 &&
			rl.IsMouseButtonPressed(.LEFT) &&
			rl.CheckCollisionPointRec(ui_screen_to_design(mouse), memory_token_prompt_rect()) {
			intent.open_disciplines = true
			return intent
		}
			if app.shop_open {
				if rl.IsMouseButtonPressed(.LEFT) {
					if mode, found := shop_mode_at(mouse); found {
						if mode != app.shop_mode {
							intent.tab = true
							view_clear_menu_click(view)
						}
					}
				}
				if rl.IsKeyPressed(.TAB) do intent.tab=true
			if rl.IsKeyPressed(.LEFT) do intent.menu_horizontal-=1
			if rl.IsKeyPressed(.RIGHT) do intent.menu_horizontal+=1
			if rl.IsKeyPressed(.UP) do intent.menu_delta-=1
			if rl.IsKeyPressed(.DOWN) do intent.menu_delta+=1
			if mouse_moved {if index,found:=shop_row_at(app,mouse);found {intent.menu_index=index;intent.menu_index_valid=true}}
			if rl.IsMouseButtonPressed(.LEFT) {
				if index,found:=shop_row_at(app,mouse);found {
					intent.menu_index=index
					intent.menu_index_valid=true
					click_context := app.shop_mode == .Buy ? Menu_Click_Context.Shop_Buy : Menu_Click_Context.Shop_Sell
					intent.confirm=menu_mouse_double_clicked(view,click_context,index)
				}
			}
			if rl.IsKeyPressed(.ENTER)||rl.IsKeyPressed(.KP_ENTER)||rl.IsKeyPressed(.E) do intent.confirm=true
			if rl.IsKeyPressed(.ESCAPE)||rl.IsKeyPressed(.BACKSPACE)||rl.IsKeyPressed(.Q) do intent.back=true
			return intent
		}
		if app.inventory_open {
			if mouse_moved {
				if index, found := inventory_row_at(app, mouse); found {
					intent.menu_index = index
					intent.menu_index_valid = true
				}
			}
			if rl.IsMouseButtonPressed(.LEFT) {
				if sort_mode, found := inventory_sort_mode_at(mouse); found {
					intent.inv_sort_mode = sort_mode
					intent.inv_sort_valid = true
				} else if index, row_found := inventory_row_at(app, mouse); row_found {
					intent.menu_index = index
					intent.menu_index_valid = true
					intent.confirm = menu_mouse_double_clicked(view, .Inventory, index)
				}
			}
			if rl.IsKeyPressed(.UP) do intent.menu_delta -= 1
			if rl.IsKeyPressed(.DOWN) do intent.menu_delta += 1
			if rl.IsKeyPressed(.PAGE_UP) do intent.menu_delta -= 5
			if rl.IsKeyPressed(.PAGE_DOWN) do intent.menu_delta += 5
			if rl.IsKeyPressed(.HOME) && app.run.player.bag_count > 0 {
				intent.menu_index = 0
				intent.menu_index_valid = true
			}
			if rl.IsKeyPressed(.END) && app.run.player.bag_count > 0 {
				intent.menu_index = app.run.player.bag_count - 1
				intent.menu_index_valid = true
			}
			if rl.IsKeyPressed(.ENTER) || rl.IsKeyPressed(.KP_ENTER) || rl.IsKeyPressed(.E) {
				intent.confirm = true
			}
			if rl.IsKeyPressed(.DELETE) || rl.IsKeyPressed(.BACKSPACE) {
				intent.inv_drop = true
			}
			if rl.IsKeyPressed(.TAB) do intent.inv_cycle_sort = 1
			if rl.IsKeyPressed(.S) do intent.inv_sort = true
			inventory_keys := [9]rl.KeyboardKey{
				.ONE, .TWO, .THREE, .FOUR, .FIVE, .SIX, .SEVEN, .EIGHT, .NINE,
			}
			shift_down := rl.IsKeyDown(.LEFT_SHIFT) || rl.IsKeyDown(.RIGHT_SHIFT)
			for key, index in inventory_keys {
				if rl.IsKeyPressed(key) && index < app.run.player.bag_count {
					intent.menu_index = index
					intent.menu_index_valid = true
					if shift_down {
						intent.inv_drop = true
					} else {
						intent.confirm = true
					}
				}
			}
			if rl.IsKeyPressed(.ESCAPE) do intent.back = true
			return intent
		}

		mouse_tile := tile_from_world(Vec2(rl.GetScreenToWorld2D(mouse, view.camera)))
		aim := mouse_tile - app.run.player.pos
		arrow_aim := desktop_move_vector(
			rl.IsKeyDown(.LEFT), rl.IsKeyDown(.RIGHT),
			rl.IsKeyDown(.UP), rl.IsKeyDown(.DOWN),
		)
		if arrow_aim != {} {
			controller.keyboard_aim = true
			aim = arrow_aim
			if !controller.right_aim_this_frame do intent.aim = {}
		} else if controller.keyboard_aim {
			// Keyboard owns aim: drop the parked cursor's direction so
			// abilities and idle facing fall back to the retained heading.
			aim = {}
		}
		raw := Desktop_Input{
			left = rl.IsKeyDown(.LEFT),
			right = rl.IsKeyDown(.RIGHT),
			up = rl.IsKeyDown(.UP),
			down = rl.IsKeyDown(.DOWN),
			aim = aim,
			mouse_left = rl.IsMouseButtonDown(.LEFT),
			mouse_left_pressed = rl.IsMouseButtonPressed(.LEFT),
			mouse_press_aim = mouse_tile - app.run.player.pos,
			mouse_right = rl.IsMouseButtonDown(.RIGHT),
			mouse_target = mouse_tile,
			abilities = {
				rl.IsKeyPressed(.ONE), rl.IsKeyPressed(.TWO),
				rl.IsKeyPressed(.THREE), rl.IsKeyPressed(.FOUR),
				rl.IsKeyPressed(.FIVE), rl.IsKeyPressed(.SIX),
			},
			ability1_released = rl.IsKeyReleased(.ONE),
			interact = rl.IsKeyPressed(.E),
			inventory = intent.toggle_inventory,
			tab = rl.IsKeyPressed(.TAB),
			back = rl.IsKeyPressed(.ESCAPE),
		}
		desktop_intent:=desktop_gameplay_intent(raw, app.run.player.archetype)
		merge_gameplay_intent(&intent,desktop_intent)
		// Only an actively pointed device may own idle facing downstream. The
		// controller's passive snap-aim fallback stays non-live on purpose, and
		// a parked cursor no longer steals the last keyboard/pad heading.
		if mouse_used || arrow_aim != {} do intent.aim_live = true

		if app.dev_controls {
			if rl.IsKeyPressed(.N) do intent.descend = true
			if rl.IsKeyPressed(.R) do intent.new_run = true
			if rl.IsKeyPressed(.B) do intent.boss_floor = true
		}
	case .Paused:
		if mouse_moved {if index,found:=pause_row_at(mouse);found {intent.menu_index=index;intent.menu_index_valid=true}}
		if rl.IsMouseButtonPressed(.LEFT) {if index,found:=pause_row_at(mouse);found {intent.menu_index=index;intent.menu_index_valid=true;intent.confirm=true;intent.pointer_confirm=true}}
		if rl.IsKeyPressed(.UP) do intent.menu_delta-=1
		if rl.IsKeyPressed(.DOWN) do intent.menu_delta+=1
		if rl.IsKeyPressed(.ENTER)||rl.IsKeyPressed(.KP_ENTER) do intent.confirm=true
		if rl.IsKeyPressed(.ESCAPE)||rl.IsKeyPressed(.BACKSPACE) do intent.back=true
	case .Options:
		if mouse_moved {if index,found:=options_row_at(app,mouse);found {intent.menu_index=index;intent.menu_index_valid=true}}
		if rl.IsMouseButtonPressed(.LEFT) {if index,found:=options_row_at(app,mouse);found {intent.menu_index=index;intent.menu_index_valid=true;intent.confirm=true}}
		if rl.IsKeyPressed(.UP) do intent.menu_delta-=1
		if rl.IsKeyPressed(.DOWN) do intent.menu_delta+=1
		if rl.IsKeyPressed(.LEFT) do intent.menu_horizontal-=1
		if rl.IsKeyPressed(.RIGHT) do intent.menu_horizontal+=1
		if rl.IsKeyPressed(.ENTER)||rl.IsKeyPressed(.KP_ENTER) do intent.confirm=true
		if rl.IsKeyPressed(.ESCAPE)||rl.IsKeyPressed(.BACKSPACE)||rl.IsKeyPressed(.O) do intent.back=true
	case .Controls:
		if !app.controls_capture && mouse_moved {
			if index,found:=controls_row_at(app,mouse);found {intent.menu_index=index;intent.menu_index_valid=true}
		}
		if !app.controls_capture && rl.IsMouseButtonPressed(.LEFT) {
			if index,found:=controls_row_at(app,mouse);found {intent.menu_index=index;intent.menu_index_valid=true;intent.confirm=true}
		}
		if !app.controls_capture {
			if rl.IsKeyPressed(.UP) do intent.menu_delta-=1
			if rl.IsKeyPressed(.DOWN) do intent.menu_delta+=1
			if rl.IsKeyPressed(.LEFT) do intent.menu_horizontal-=1
			if rl.IsKeyPressed(.RIGHT) do intent.menu_horizontal+=1
			if rl.IsKeyPressed(.ENTER)||rl.IsKeyPressed(.KP_ENTER) do intent.confirm=true
		}
		if rl.IsKeyPressed(.ESCAPE)||rl.IsKeyPressed(.BACKSPACE) do intent.back=true
	case .Chronicle:
		if mouse_moved {
			if index,found:=chronicle_card_at(app,mouse);found {intent.menu_index=index;intent.menu_index_valid=true}
		}
		if rl.IsMouseButtonPressed(.LEFT) {
			if focus,found:=chronicle_filter_at(mouse);found {
				app.chronicle.focus=focus
				intent.menu_horizontal=1
			} else if index,card_found:=chronicle_card_at(app,mouse);card_found {
				intent.menu_index=index;intent.menu_index_valid=true;intent.confirm=true
			}
		}
		if wheel!=0 {intent.menu_delta=-int(wheel);if intent.menu_delta==0 do intent.menu_delta=wheel>0?-1:1}
		if rl.IsKeyPressed(.UP)||rl.IsKeyPressed(.PAGE_UP) do intent.menu_delta-=1
		if rl.IsKeyPressed(.DOWN)||rl.IsKeyPressed(.PAGE_DOWN) do intent.menu_delta+=1
		if rl.IsKeyPressed(.LEFT) do intent.menu_horizontal-=1
		if rl.IsKeyPressed(.RIGHT) do intent.menu_horizontal+=1
		if rl.IsKeyPressed(.TAB) do intent.tab=true
		if rl.IsKeyPressed(.ENTER)||rl.IsKeyPressed(.KP_ENTER) do intent.confirm=true
		if rl.IsKeyPressed(.ESCAPE)||rl.IsKeyPressed(.BACKSPACE) do intent.back=true
	case .Abandon_Confirm:
		if mouse_moved {if index,found:=choice_overlay_row_at(mouse,2);found {intent.menu_index=index;intent.menu_index_valid=true}}
		if rl.IsMouseButtonPressed(.LEFT) {if index,found:=choice_overlay_row_at(mouse,2);found {intent.menu_index=index;intent.menu_index_valid=true;intent.confirm=true}}
		if rl.IsKeyPressed(.UP) do intent.menu_delta-=1
		if rl.IsKeyPressed(.DOWN) do intent.menu_delta+=1
		if rl.IsKeyPressed(.ENTER)||rl.IsKeyPressed(.KP_ENTER) do intent.confirm=true
		if rl.IsKeyPressed(.ESCAPE)||rl.IsKeyPressed(.BACKSPACE) do intent.back=true
	case .Recovery, .Save_Error:
		if mouse_moved {if index,found:=choice_overlay_row_at(mouse,3);found {intent.menu_index=index;intent.menu_index_valid=true}}
		if rl.IsMouseButtonPressed(.LEFT) {if index,found:=choice_overlay_row_at(mouse,3);found {intent.menu_index=index;intent.menu_index_valid=true;intent.confirm=true}}
		if rl.IsKeyPressed(.UP) do intent.menu_delta-=1
		if rl.IsKeyPressed(.DOWN) do intent.menu_delta+=1
		if rl.IsKeyPressed(.ENTER)||rl.IsKeyPressed(.KP_ENTER) do intent.confirm=true
		if rl.IsKeyPressed(.ESCAPE)||rl.IsKeyPressed(.BACKSPACE) do intent.back=true
	case .Save_Wait:
	case .Resume_Veil:
		if rl.IsKeyPressed(.ENTER)||rl.IsKeyPressed(.KP_ENTER)||rl.IsKeyPressed(.SPACE)||rl.IsMouseButtonPressed(.LEFT) {
			intent.confirm=true;intent.pointer_confirm=rl.IsMouseButtonPressed(.LEFT)
		}
	case .Dead, .Victory:
		if rl.IsKeyPressed(.R) || rl.IsKeyPressed(.ESCAPE) ||
			rl.IsKeyPressed(.BACKSPACE) || rl.IsMouseButtonPressed(.LEFT) {
			intent.back = true
		}
	}
	return intent
}
