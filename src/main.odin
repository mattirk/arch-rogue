package archrogue

import "base:runtime"
import "core:fmt"
import "core:math"
import "core:os"
import filepath "core:path/filepath"
import "core:strconv"
import "core:strings"
import "core:time"
import "core:thread"
import chan "core:sync/chan"
import rl "../vendor/raylib"

VERSION :: "6.0.0-alpha.21"

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
}

@(rodata)
RAYLIB_GAMEPAD_BUTTONS := [Controller_Button]rl.GamepadButton{
	.A=.RIGHT_FACE_DOWN,.B=.RIGHT_FACE_RIGHT,.X=.RIGHT_FACE_LEFT,.Y=.RIGHT_FACE_UP,
	.Left_Bumper=.LEFT_TRIGGER_1,.Right_Bumper=.RIGHT_TRIGGER_1,
	.Back=.MIDDLE_LEFT,.Start=.MIDDLE_RIGHT,.Left_Stick=.LEFT_THUMB,.Right_Stick=.RIGHT_THUMB,
	.Dpad_Up=.LEFT_FACE_UP,.Dpad_Down=.LEFT_FACE_DOWN,.Dpad_Left=.LEFT_FACE_LEFT,.Dpad_Right=.LEFT_FACE_RIGHT,
}

collect_controller_intent :: proc(app:^App,state:^Controller_Runtime,intent:^Intent) {
	state.right_aim_this_frame = false
	if !app.options.controller_enabled {
		state^={}
		return
	}
	pad:=-1
	for candidate in 0..<MAX_GAMEPADS {
		if rl.IsGamepadAvailable(i32(candidate)) {pad=candidate;break}
	}
	if pad<0 {
		state^={}
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
			axis:=trigger==.Left?rl.GamepadAxis.LEFT_TRIGGER:rl.GamepadAxis.RIGHT_TRIGGER
			raw:=rl.GetGamepadAxisMovement(i32(pad),axis)
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
		if left!={} do intent.move=left
		right_raw:=Vec2{rl.GetGamepadAxisMovement(i32(pad),.RIGHT_X),rl.GetGamepadAxisMovement(i32(pad),.RIGHT_Y)}
		right:=controller_resolve_stick(right_raw,&state.right_stick)
		if right!={} {
			state.aim_mode = true
			state.right_aim_this_frame = true
			intent.aim=controller_snap_aim(&app.run,right)
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
		axis:=trigger==.Left?rl.GamepadAxis.LEFT_TRIGGER:rl.GamepadAxis.RIGHT_TRIGGER
		raw:=rl.GetGamepadAxisMovement(i32(pad),axis)
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

storage_ensure_directory :: proc(directory:string)->bool {
	if directory=="" do return false
	when ARCH_ROGUE_ANDROID {
		// NativeActivity's internalDataPath already exists. Bionic's mkdir wrapper
		// avoids both core:os mkdir_all's SELinux-denied `/` walk and Odin's raw
		// legacy mkdir syscall, which Android's seccomp policy rejects.
		created:=platform_android_create_private_directory(directory)
		ready:=os.is_directory(directory)
		if !created&&!ready {
			platform_log(fmt.tprintf("ARCH_ROGUE_STORAGE_ERROR libc mkdir failed path=%s",directory))
			return false
		}
		return ready
	} else {
		// Odin's os.mkdir_all reports .Exist when every path component already
		// exists. That is the normal second-launch case, not a persistence failure.
		mkdir_err:=os.mkdir_all(directory)
		ready:=os.is_directory(directory)
		if mkdir_err!=nil&&!ready do return false
		return ready
	}
}

storage_paths_from_directory :: proc(directory:string) -> (paths:Storage_Paths,ok:bool) {
	if directory=="" do return {},false
	owned_directory:=strings.clone(directory)
	options,options_err:=filepath.join([]string{owned_directory,"options.json"},context.allocator)
	profile,profile_err:=filepath.join([]string{owned_directory,"profile.json"},context.allocator)
	run,run_err:=filepath.join([]string{owned_directory,"run.json"},context.allocator)
	if options_err!=nil||profile_err!=nil||run_err!=nil {
		delete(owned_directory);delete(options);delete(profile);delete(run);return {},false
	}
	return {directory=owned_directory,options=options,profile=profile,run=run},true
}

platform_storage_paths :: proc() -> (paths:Storage_Paths,ok:bool) {
	data_dir:string
	when ARCH_ROGUE_ANDROID {
		data_dir=platform_android_internal_data_path()
		if data_dir=="" {
			platform_log("ARCH_ROGUE_STORAGE_ERROR NativeActivity internalDataPath is unavailable")
			return {},false
		}
		platform_log(fmt.tprintf("ARCH_ROGUE_STORAGE_ROOT path=%s",data_dir))
	} else {
		data_err:os.Error
		data_dir,data_err=os.user_data_dir(context.allocator)
		if data_err!=nil do return {},false
	}
	defer delete(data_dir)
	directory_name:=ARCH_ROGUE_ANDROID?ANDROID_APP_DATA_DIRECTORY_NAME:APP_DATA_DIRECTORY_NAME
	directory,join_err:=filepath.join([]string{data_dir,directory_name},context.allocator)
	if join_err!=nil do return {},false
	if !storage_ensure_directory(directory) {delete(directory);return {},false}
	options,options_err:=filepath.join([]string{directory,"options.json"},context.allocator)
	profile,profile_err:=filepath.join([]string{directory,"profile.json"},context.allocator)
	run,run_err:=filepath.join([]string{directory,"run.json"},context.allocator)
	if options_err!=nil||profile_err!=nil||run_err!=nil {
		delete(directory);delete(options);delete(profile);delete(run);return {},false
	}
	when ARCH_ROGUE_ANDROID do platform_log(fmt.tprintf("ARCH_ROGUE_STORAGE_READY path=%s",directory))
	return {directory=directory,options=options,profile=profile,run=run},true
}

platform_legacy_options_path :: proc() -> string {
	when ARCH_ROGUE_ANDROID do return ""
	config_dir,config_err:=os.user_config_dir(context.allocator)
	if config_err!=nil do return ""
	defer delete(config_dir)
	dir,join_err:=filepath.join([]string{config_dir,"arch-rogue-raylib"},context.allocator)
	if join_err!=nil do return ""
	defer delete(dir)
	path,path_err:=filepath.join([]string{dir,"options.json"},context.allocator)
	if path_err!=nil do return ""
	return path
}

storage_artifact_path :: proc(primary,suffix:string) -> string {
	return fmt.aprintf("%s.%s",primary,suffix)
}

storage_file_exists :: proc(path:string) -> bool {
	info,err:=os.stat(path,context.allocator)
	if err!=nil do return false
	os.file_info_delete(info,context.allocator)
	return true
}

storage_remove_file :: proc(path:string) -> bool {
	when ARCH_ROGUE_ANDROID do return platform_android_remove_file(path)
	return os.remove(path)==nil
}

storage_read_bounded :: proc(path:string,max_bytes:int) -> ([]byte,Persistence_Decode_Status) {
	info,stat_err:=os.stat(path,context.allocator)
	if stat_err!=nil do return nil,.Missing
	size:=info.size
	os.file_info_delete(info,context.allocator)
	if size<0||size>i64(max_bytes) do return nil,.Oversize
	when ARCH_ROGUE_ANDROID {
		data:=make([]byte,int(size),context.allocator)
		if !platform_android_read_file_exact(path,data) {
			delete(data)
			return nil,.Corrupt
		}
		return data,.Valid
	} else {
		data,read_err:=os.read_entire_file_from_path(path,context.allocator)
		if read_err!=nil do return nil,.Corrupt
		return data,.Valid
	}
}

storage_max_bytes :: proc(kind:Persistence_Document_Kind)->int {
	switch kind {case .Options:return PERSISTENCE_OPTIONS_MAX_BYTES;case .Profile:return PERSISTENCE_PROFILE_MAX_BYTES;case .Run:return PERSISTENCE_RUN_MAX_BYTES}
	return 0
}

storage_sync_parent :: proc(path:string)->bool {
	when ARCH_ROGUE_ANDROID {
		return platform_android_sync_directory(filepath.dir(path))
	} else when ODIN_OS==.Windows {
		// Windows directory handles require backup-semantics flags. Each metadata
		// replacement below instead uses MOVEFILE_WRITE_THROUGH.
		return true
	} else {
		parent:=filepath.dir(path)
		directory,open_err:=os.open(parent)
		if open_err!=nil do return false
		ok:=os.sync(directory)==nil
		if close_err:=os.close(directory);close_err!=nil do ok=false
		return ok
	}
}


storage_write_synced :: proc(path:string,data:[]byte)->bool {
	when ARCH_ROGUE_ANDROID {
		ok:=platform_android_write_file_synced(path,data)
		if ok do ok=storage_sync_parent(path)
		if !ok do _=storage_remove_file(path)
		return ok
	} else {
		file,open_err:=os.create(path)
		if open_err!=nil do return false
		written,write_err:=os.write(file,data)
		ok:=write_err==nil&&written==len(data)&&os.flush(file)==nil&&os.sync(file)==nil
		if close_err:=os.close(file);close_err!=nil do ok=false
		if ok do ok=storage_sync_parent(path)
		if !ok do _=storage_remove_file(path)
		return ok
	}
}

storage_quarantine_file :: proc(path:string) -> bool {
	if !storage_file_exists(path) do return true
	quarantine:=fmt.aprintf("%s.corrupt-%d",path,time.tick_now())
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

Save_Worker :: struct {
	jobs:chan.Chan(Save_Job),
	completions:chan.Chan(Save_Completion),
	thread:^thread.Thread,
	ready:bool,
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

save_worker_batch_add :: proc(batch:^[3]Save_Job,count:^int,job:Save_Job) {
	pending:=job
	if batch==nil||count==nil {save_job_destroy(&pending);return}
	for i in 0..<count^ {
		if batch[i].kind!=pending.kind do continue
		if pending.revision>=batch[i].revision {
			save_job_destroy(&batch[i])
			batch[i]=pending
		} else do save_job_destroy(&pending)
		return
	}
	if count^>=len(batch^) {save_job_destroy(&pending);return}
	batch[count^]=pending
	count^+=1
}

save_worker_process_job :: proc(worker:^Save_Worker,job:^Save_Job) {
	if worker==nil||job==nil do return
	worker_allocator:=context.allocator
	if job.allocator.procedure!=nil do context.allocator=job.allocator
	encoded:=job.data
	encoded_owned:=false
	encode_ok:=len(encoded)>0
	if job.kind==.Run&&job.run_payload!=nil {
		encoded,encode_ok=persistence_encode_run_payload(job.run_payload,job.run_id,job.revision,job.written_at_utc)
		encoded_owned=true
	}
	success:=encode_ok&&storage_write_document_durable(job.path,job.kind,encoded)
	if encoded_owned do delete(encoded,job.allocator)
	_=chan.send(worker.completions,Save_Completion{kind=job.kind,revision=job.revision,success=success})
	save_job_destroy(job)
	context.allocator=worker_allocator
}

save_worker_loop :: proc(worker:^Save_Worker) {
	if worker==nil do return
	for {
		job,ok:=chan.recv(worker.jobs)
		if !ok do return
		if job.stop {save_job_destroy(&job);return}
		// One local slot per document domain. A burst retains the newest revision
		// of each domain without re-enqueueing into the worker's own bounded queue.
		batch:[3]Save_Job
		batch_count:=0
		save_worker_batch_add(&batch,&batch_count,job)
		stop_after_batch:=false
		for {
			next,has_next:=chan.try_recv(worker.jobs);if !has_next do break
			if next.stop {
				save_job_destroy(&next)
				stop_after_batch=true
				break
			}
			save_worker_batch_add(&batch,&batch_count,next)
		}
		for i in 0..<batch_count do save_worker_process_job(worker,&batch[i])
		if stop_after_batch do return
	}
}

save_worker_init :: proc(worker:^Save_Worker)->bool {
	if worker==nil do return false
	jobs,jobs_err:=chan.create(chan.Chan(Save_Job),8,context.allocator)
	completions,completion_err:=chan.create(chan.Chan(Save_Completion),16,context.allocator)
	if jobs_err!=.None||completion_err!=.None {if jobs.impl!=nil do chan.destroy(jobs);if completions.impl!=nil do chan.destroy(completions);return false}
	worker.jobs=jobs;worker.completions=completions;worker.ready=true
	worker.thread=thread.create_and_start_with_poly_data(worker,save_worker_loop)
	return worker.thread!=nil
}

// Takes ownership of data whether enqueueing succeeds or fails. Job data is
// copied to the process heap before crossing threads; test and arena allocators
// remain confined to the producer thread that owns them.
save_worker_enqueue :: proc(worker:^Save_Worker,kind:Persistence_Document_Kind,path:string,data:[]byte,revision:u64)->bool {
	source_allocator:=context.allocator
	allocator:=runtime.heap_allocator()
	owned_data:=make([]byte,len(data),allocator)
	copy(owned_data,data)
	delete(data,source_allocator)
	job:=Save_Job{
		kind=kind,path=strings.clone(path,allocator),data=owned_data,
		revision=revision,allocator=allocator,
	}
	if worker!=nil&&worker.ready&&len(owned_data)>0&&chan.try_send(worker.jobs,job) do return true
	// Never evict a different document domain from the bounded queue. The caller
	// keeps that domain dirty and retries after backoff.
	save_job_destroy(&job);return false
}

save_worker_enqueue_run :: proc(
	worker:^Save_Worker,
	path,run_id,written_at_utc:string,
	payload:^Run_Save_Payload,
	revision:u64,
)->bool {
	allocator:=runtime.heap_allocator()
	job:=Save_Job{
		kind=.Run,path=strings.clone(path,allocator),revision=revision,
		run_id=strings.clone(run_id,allocator),written_at_utc=strings.clone(written_at_utc,allocator),
		run_payload=payload,allocator=allocator,
	}
	if worker!=nil&&worker.ready&&run_id!=""&&chan.try_send(worker.jobs,job) do return true
	save_job_destroy(&job)
	return false
}

save_worker_shutdown :: proc(worker:^Save_Worker) {
	if worker==nil||!worker.ready do return
	_=chan.send(worker.jobs,Save_Job{stop=true})
	thread.join(worker.thread);thread.destroy(worker.thread)
	for {job,ok:=chan.try_recv(worker.jobs);if !ok do break;save_job_destroy(&job)}
	chan.close(worker.jobs);chan.close(worker.completions)
	chan.destroy(worker.jobs);chan.destroy(worker.completions)
	worker^={}
}

Persistence_Coordinator :: struct {
	paths:Storage_Paths,
	worker:Save_Worker,
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

persistence_utc_now :: proc()->string {
	value,ok:=time.time_to_rfc3339(time.now(),include_nanos=true,allocator=context.allocator)
	if !ok do return "1970-01-01T00:00:00Z"
	return value
}

persistence_new_profile_id :: proc(seed:u64)->string {
	source:=fmt.aprintf("arch-rogue:%016x:%d",seed,time.tick_now());defer delete(source)
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
	snapshot_begin:=time.tick_now()
	defer {
		elapsed:=time.duration_milliseconds(time.tick_diff(snapshot_begin,time.tick_now()))
		coordinator.run_snapshot_count+=1
		coordinator.run_snapshot_total_ms+=elapsed
		coordinator.run_snapshot_max_ms=max(coordinator.run_snapshot_max_ms,elapsed)
	}
	persistence_prepare_run_identity(app)
	run_ensure_persisted_entity_ids(&app.run)
	revision:=max(coordinator.run_revision+1,app.run.revision+1)
	written:=persistence_utc_now();defer delete(written)
	allocator:=runtime.heap_allocator()
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
		completion,ok:=chan.try_recv(coordinator.worker.completions);if !ok do break
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

persistence_drain_worker :: proc(coordinator:^Persistence_Coordinator)->bool {
	if coordinator==nil||!coordinator.ready do return false
	save_worker_shutdown(&coordinator.worker)
	coordinator.run_write_in_flight=false
	return save_worker_init(&coordinator.worker)
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
		if status==.Valid {
			loaded,revision,decoded:=persistence_decode_profile(data)
			if decoded==.Valid {
				profile_destroy(&app.profile)
				app.profile=loaded
				coordinator.profile_revision=revision
				coordinator.profile_blocked=false
				app.profile_save_damaged=false
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

persistence_restore_active_run :: proc(coordinator:^Persistence_Coordinator,app:^App)->(bool,Persistence_Error_Kind) {
	if coordinator==nil||app==nil do return false,.Load
	data,status:=storage_recover_document(coordinator.paths.run,.Run)
	if status!=.Valid&&status!=.Migrated {
		delete(data)
		app.active_run_damaged=status!=.Missing
		return false,status==.Future?.Future:.Load
	}
	document,decoded:=persistence_decode_run(data);delete(data)
	if decoded!=.Valid||document.payload.terminal!=.Active||!app_install_run_document(app,&document) {
		run_document_destroy(&document)
		app.active_run_damaged=true
		return false,.Corrupt
	}
	run_document_destroy(&document)
	coordinator.run_revision=app.run.revision
	app.active_run_available=true
	app.active_run_damaged=false
	return true,.None
}

persistence_finalize_terminal :: proc(coordinator:^Persistence_Coordinator,app:^App,request:Persistence_Request)->bool {
	if coordinator==nil||app==nil||coordinator.run_write_in_flight do return false
	if app.run.ended_at_utc=="" do app.run.ended_at_utc=persistence_utc_now()
	app.run.finalization=.Terminal_Marker
	if !persistence_write_run_sync(coordinator,app) do return false
	outcome:=app.run.terminal==.Victory?Chronicle_Outcome.Victory:Chronicle_Outcome.Fallen
	record:=chronicle_record_from_run(&app.run,outcome);defer chronicle_record_destroy(&record)
	_=profile_finalize_record(&app.profile,&record)
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
		restored,error_kind:=persistence_restore_active_run(coordinator,app)
		if !restored {persistence_fail_request(app,request,error_kind,.Title);return}
		app.persistence_request=.None;app.persistence_error=.None;app.mode=.Resume_Veil
		app.run_dirty=false;app.run_critical=false
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
			restored,error_kind:=persistence_restore_active_run(coordinator,app)
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

// Lifecycle checkpointing bypasses Save_Wait's presentation gate. It snapshots
// the latest frozen fixed tick, coalesces behind any older run write, and waits
// only for the caller's bounded budget; the worker remains alive on timeout.
persistence_flush_for_suspend :: proc(
	coordinator:^Persistence_Coordinator,
	app:^App,
	budget:time.Duration=250*time.Millisecond,
)->bool {
	if coordinator==nil||app==nil||!coordinator.ready||app.run.run_id==""||app.run.terminal!=.Active do return false
	app.run_dirty=true
	app.run_critical=true
	app.run_dirty_serial+=1
	start:=time.tick_now()
	for {
		persistence_poll_completions(coordinator,app)
		if !coordinator.run_write_in_flight&&app.run_dirty {
			_=persistence_enqueue_run(coordinator,app)
		}
		if !coordinator.run_write_in_flight&&!app.run_dirty do return true
		if time.tick_diff(start,time.tick_now())>=budget do return false
		time.sleep(2*time.Millisecond)
	}
}

persistence_coordinator_init :: proc(coordinator:^Persistence_Coordinator,app:^App,seed:u64)->bool {
	if coordinator==nil||app==nil do return false
	paths,paths_ok:=platform_storage_paths();if !paths_ok do return false
	coordinator.paths=paths;coordinator.ready=true
	if !save_worker_init(&coordinator.worker) {storage_paths_destroy(&coordinator.paths);coordinator.ready=false;return false}

	profile_existed:=false
	profile_data,profile_status:=storage_recover_document(coordinator.paths.profile,.Profile)
	if profile_status==.Valid {
		profile,revision,decoded:=persistence_decode_profile(profile_data)
		if decoded==.Valid {
			app.profile=profile;coordinator.profile_revision=revision;profile_existed=true
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
	if !coordinator.profile_blocked&&(profile_status==.Missing||(!profile_existed&&legacy_hell)) do _=persistence_write_profile_sync(coordinator,app)
	if !coordinator.options_blocked&&(options_status==.Missing||options_status==.Migrated) do _=persistence_write_options_sync(coordinator,app)

	run_data,run_status:=storage_recover_document(coordinator.paths.run,.Run)
	if run_status==.Valid {
		document,decoded:=persistence_decode_run(run_data)
		if decoded==.Valid {
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
	if .Apply_Window in effects && !ARCH_ROGUE_ANDROID {
		borderless:=rl.IsWindowState({.BORDERLESS_WINDOWED_MODE})
		if borderless!=app.options.fullscreen do rl.ToggleBorderlessWindowed()
	}
	if .Apply_FPS in effects do rl.SetTargetFPS(i32(frame_rate_cap_target(app.options.frame_rate_cap)))
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

// Dev-only MX.6 screenshot staging. The harness lives in the platform entry
// point so ordinary simulation and renderer APIs stay free of capture concerns.
@(private = "file")
MX6_Capture_Scenario :: enum u8 {
	None,
	Melee,
	Big_Hit,
	Bolt,
	Class_Skill,
	Dash,
	Enemy_Base_Melee,
	Enemy_Base_Ranged,
	Enemy_Strike,
	Enemy_Bolt,
	Enemy_Fan,
	Enemy_Nova,
	Boss_Attack,
	Boss_Cast,
	Familiar_Wisp,
	Familiar_Crow,
	Familiar_Beast,
	Fow_Nova,
}

@(private = "file")
dev_archetype_from_env :: proc(value:string) -> (Archetype_Id,bool) {
	switch value {
	case "warden":   return .Warden,true
	case "rogue":    return .Rogue,true
	case "arcanist": return .Arcanist,true
	case "acolyte":  return .Acolyte,true
	case "ranger":   return .Ranger,true
	}
	if index,ok:=strconv.parse_int(value);ok && 0<=index && index<len(Archetype_Id) {
		return Archetype_Id(index),true
	}
	return {},false
}

MX_Story_Capture_Scenario :: enum u8 {
	None,
	Omen_Initial,
	Relic_Choices,
	Guest,
	Soul,
	Ending,
}

mx_story_capture_scenario_from_env :: proc(value: string) -> MX_Story_Capture_Scenario {
	switch value {
	case "omen_initial":  return .Omen_Initial
	case "relic_choices": return .Relic_Choices
	case "guest":         return .Guest
	case "soul":          return .Soul
	case "ending":        return .Ending
	}
	return .None
}

MX_Save_Capture_Scenario :: enum u8 {
	None,
	Empty,
	Populated,
	Victories,
	Fallen,
	Recovery,
	Abandon,
}

mx_save_capture_scenario_from_env :: proc(value:string)->MX_Save_Capture_Scenario {
	switch value {
	case "empty":return .Empty
	case "populated":return .Populated
	case "victories":return .Victories
	case "fallen":return .Fallen
	case "recovery":return .Recovery
	case "abandon":return .Abandon
	}
	return .None
}

@(private = "file")
mx6_capture_scenario_from_env :: proc(value:string) -> MX6_Capture_Scenario {
	switch value {
	case "melee":              return .Melee
	case "big_hit":            return .Big_Hit
	case "bolt":               return .Bolt
	case "class":              return .Class_Skill
	case "dash":               return .Dash
	case "enemy_base_melee":   return .Enemy_Base_Melee
	case "enemy_base_ranged":  return .Enemy_Base_Ranged
	case "enemy_strike":       return .Enemy_Strike
	case "enemy_bolt":         return .Enemy_Bolt
	case "enemy_fan":          return .Enemy_Fan
	case "enemy_nova":         return .Enemy_Nova
	case "boss_attack":        return .Boss_Attack
	case "boss_cast":          return .Boss_Cast
	case "familiar_wisp":      return .Familiar_Wisp
	case "familiar_crow":      return .Familiar_Crow
	case "familiar_beast":     return .Familiar_Beast
	case "fow_nova":           return .Fow_Nova
	}
	return .None
}

@(private = "file")
mx6_capture_direction_from_env :: proc(value:string) -> (Vec2,bool) {
	// Names are screen-space; vectors are tile-space before isometric projection.
	switch value {
	case "south":      return { 1, 1},true
	case "south-east": return { 1, 0},true
	case "east":       return { 1,-1},true
	case "north-east": return { 0,-1},true
	case "north":      return {-1,-1},true
	case "north-west": return {-1, 0},true
	case "west":       return {-1, 1},true
	case "south-west": return { 0, 1},true
	}
	return {},false
}

@(private = "file")
mx6_capture_unit :: proc(direction:Vec2) -> Vec2 {
	length:=math.hypot(direction.x,direction.y)
	return length>1e-5?direction/length:Vec2{1,1}/math.sqrt(f32(2))
}

@(private = "file")
mx6_capture_place :: proc(
	run:^Run,
	origin,direction:Vec2,
	distance,radius:f32,
) -> (Vec2,bool) {
	if run==nil do return {},false
	unit:=mx6_capture_unit(direction)
	// Step inward deterministically if a small room or furnishing clips the ideal
	// composition. No gameplay RNG is consumed by capture placement.
	for step in 0..<16 {
		d:=distance-f32(step)*.08
		if d<.55 do break
		candidate:=origin+unit*d
		if blocked_for_radius(&run.dungeon,candidate.x,candidate.y,radius,block_stairs=true) do continue
		if !line_of_sight(&run.dungeon,origin.x,origin.y,candidate.x,candidate.y) do continue
		return candidate,true
	}
	return origin,false
}

@(private = "file")
mx6_capture_reset :: proc(app:^App,direction:Vec2) -> Vec2 {
	run:=&app.run
	restore_sealed(&run.dungeon,run.sealed[:])
	clear(&run.sealed)
	clear(&run.enemies)
	clear(&run.projectiles)
	clear(&run.familiars)
	clear(&run.bells)
	clear(&run.numbers)
	clear(&run.ground_items)
	clear(&run.sfx)
	clear_feel_events(run)
	clear(&run.traps)
	clear(&run.shrines)
	clear(&run.secrets)
	run.nav={}
	run.boss_engaged=false
	// Artificial first-room bosses must not be recovered into a generated final
	// arena by the encounter watchdog during the one-step real commit below.
	run.dungeon.boss_arena=false
	run.arrival_timer=0
	run.wall_face_timer=0
	run.wall_touches=0
	run.shop_requested=false
	run.refuge={}

	app.death_pending=false
	app.death_timer=0
	app.inventory_open=false
	app.character_open=false
	app.shop_open=false
	app_clear_play_input(app)

	player:=&run.player
	player.pos=run_spawn_point(run)
	player.prev_pos=player.pos
	player.facing=mx6_capture_unit(direction)
	player.moving=false
	player.hp=player.max_hp
	player.mana=f32(player.max_mana)
	player.stamina=f32(player.max_stamina)
	player.melee_timer=0
	player.bolt_timer=0
	player.dash_timer=0
	player.class_skill_timer=0
	player.bighit_timer=0
	player.bighit_charge=0
	player.time_skip_timer=0
	player.swing_timer=0
	player.potion_timer=0
	player.hit_flash=0
	player.hit_flash_duration=0
	player.statuses={}
	player.poison_tick=0
	player_clear_visual_action(player)
	return player.facing
}

@(private = "file")
mx6_capture_shift_player :: proc(run:^Run,direction:Vec2,distance:f32) {
	if run==nil do return
	candidate:=run.player.pos+mx6_capture_unit(direction)*distance
	if blocked_for_radius(
		&run.dungeon,candidate.x,candidate.y,ACTOR_MOVE_COLLISION_RADIUS,block_stairs=true,
	) {
		return
	}
	run.player.pos=candidate
	run.player.prev_pos=candidate
}

@(private = "file")
mx6_capture_enemy :: proc(
	run:^Run,
	kind:Enemy_Kind,
	pos,facing:Vec2,
	pending:int,
	ability:Ability_Id={},
	has_ability:=false,
) {
	enemy:=enemy_make(kind,pos,run.depth)
	enemy.prev_pos=pos
	enemy.facing=facing
	enemy.aggro_range=max(enemy.aggro_range,f32(12))
	enemy.cooldown=0
	if has_ability {
		enemy.ability_count=1
		enemy.abilities[0]=ability
	}
	enemy_ensure_id(run,&enemy)
	enemy_begin_windup(&enemy,0,pending,facing)
	append(&run.enemies,enemy)
	// The public fixed-step path commits the windup, emits semantic effects and
	// creates real projectiles/damage. Follow-up ticks reach a readable action
	// frame while the freshly emitted feel events remain unaged.
	for _ in 0..<5 do sim_tick(run,{})
}

@(private = "file")
mx6_capture_boss :: proc(run:^Run,pos,facing:Vec2,ability:Ability_Id) {
	def:=BOSS_DEFS[Boss_Id.Gate_Tyrant]
	boss:=Enemy{
		kind=.Ghoul,
		boss_id=.Gate_Tyrant,
		name=def.name,
		role=.Boss,
		elite_mod=-1,
		final_boss=def.final_boss,
		big=true,
		pos=pos,
		prev_pos=pos,
		facing=facing,
		hp=def.max_hp,
		max_hp=def.max_hp,
		damage=def.damage,
		xp=def.xp,
		speed=def.speed,
		aggro_range=def.aggro_range,
		attack_range=def.attack_range,
		attack_cd_s=def.attack_cooldown,
		ranged=def.attack_range>=2,
		color=def.color,
		damage_type=def.damage_type,
		abilities={ability,ability},
		ability_count=1,
		pending_ability=PENDING_BASE_ATTACK,
		last_ability=-1,
	}
	enemy_ensure_id(run,&boss)
	enemy_begin_windup(&boss,0,0,facing)
	append(&run.enemies,boss)
	run.boss_engaged=true
	for _ in 0..<5 do sim_tick(run,{})
}

@(private = "file")
mx6_capture_familiar :: proc(run:^Run,direction:Vec2,kind:Familiar_Kind) {
	spawned:=false
	switch kind {
	case .Wisp:
		spawned=player_cast_spirit_call_rank(run,0)
	case .Crow:
		spawned=player_cast_spirit_call_rank(run,1)
	case .Spirit_Beast:
		spawned=player_cast_spirit_beast_rank(run,0)
	case .Bar_Dancer:
	}
	if !spawned || len(run.familiars)==0 do return

	// The summon was only the public construction path; isolate the requested
	// attack/fallback moment before driving companion AI against a real target.
	clear(&run.numbers)
	clear(&run.sfx)
	clear_feel_events(run)
	player_clear_visual_action(&run.player)
	familiar:=&run.familiars[0]
	facing:=mx6_capture_unit(direction)
	if pos,ok:=mx6_capture_place(run,run.player.pos,facing,.78,FAMILIAR_MOVE_COLLISION_RADIUS);ok {
		familiar.pos=pos
		familiar.prev_pos=pos
	}
	familiar.facing=facing
	familiar.move_dir=facing
	familiar.command=.Attack
	familiar.attack_timer=0
	familiar.attack_anim_timer=0
	familiar.moving=false

	target_pos,ok:=mx6_capture_place(run,familiar.pos,facing,.82,ACTOR_MOVE_COLLISION_RADIUS)
	if !ok do return
	target:=enemy_make(.Ghoul,target_pos,run.depth)
	target.prev_pos=target_pos
	target.facing=-facing
	target.hp=max(target.hp,200)
	target.max_hp=target.hp
	target.cooldown=100
	target.aggro_range=0
	enemy_ensure_id(run,&target)
	append(&run.enemies,target)
	tick_familiars_dt(run,.01)
	tick_familiars_dt(run,.10)
}

@(private = "file")
mx6_stage_capture :: proc(app:^App,view:^View,scenario:MX6_Capture_Scenario,direction:Vec2) {
	if app==nil || view==nil || app.mode!=.Playing || scenario==.None do return
	run:=&app.run
	facing:=mx6_capture_reset(app,direction)
	player:=&run.player
	if .Enemy_Base_Melee<=scenario && scenario<=.Boss_Cast {
		mx6_capture_shift_player(run,facing,.45)
	}

	switch scenario {
	case .Melee:
		player_melee(run,facing)
		player_tick_visual_action(player,.08)
	case .Big_Hit:
		if player_big_hit_begin(run,facing) {
			player_big_hit_fire(run)
			player_tick_visual_action(player,.10)
		}
	case .Bolt:
		if player_cast_bolt(run,facing) {
			for _ in 0..<5 do sim_tick(run,{})
		}
	case .Class_Skill:
		if player_cast_class_skill(run,facing) {
			player_tick_visual_action(player,.12)
		}
	case .Dash:
		if player_dash(run,facing) do player_tick_visual_action(player,.08)
	case .Enemy_Base_Melee:
		if pos,ok:=mx6_capture_place(run,player.pos,-facing,1.15,ACTOR_MOVE_COLLISION_RADIUS);ok {
			mx6_capture_enemy(run,.Gate_Warden,pos,facing,PENDING_BASE_ATTACK)
		}
	case .Enemy_Base_Ranged:
		if pos,ok:=mx6_capture_place(run,player.pos,-facing,1.85,ACTOR_MOVE_COLLISION_RADIUS);ok {
			mx6_capture_enemy(run,.Grave_Archer,pos,facing,PENDING_BASE_ATTACK)
		}
	case .Enemy_Strike:
		if pos,ok:=mx6_capture_place(run,player.pos,-facing,1.15,ACTOR_MOVE_COLLISION_RADIUS);ok {
			mx6_capture_enemy(run,.Gate_Warden,pos,facing,0,.Gate_Strike,true)
		}
	case .Enemy_Bolt:
		if pos,ok:=mx6_capture_place(run,player.pos,-facing,2.25,ACTOR_MOVE_COLLISION_RADIUS);ok {
			mx6_capture_enemy(run,.Cultist,pos,facing,0,.Arcane_Lance,true)
		}
	case .Enemy_Fan:
		if pos,ok:=mx6_capture_place(run,player.pos,-facing,2.25,ACTOR_MOVE_COLLISION_RADIUS);ok {
			mx6_capture_enemy(run,.Grave_Archer,pos,facing,0,.Frost_Fan,true)
		}
	case .Enemy_Nova:
		if pos,ok:=mx6_capture_place(run,player.pos,-facing,1.75,ACTOR_MOVE_COLLISION_RADIUS);ok {
			mx6_capture_enemy(run,.Plague_Toad,pos,facing,0,.Ember_Nova,true)
		}
	case .Boss_Attack:
		if pos,ok:=mx6_capture_place(run,player.pos,-facing,1.40,BOSS_MOVE_RADIUS);ok {
			mx6_capture_boss(run,pos,facing,.Gate_Strike)
		}
	case .Boss_Cast:
		if pos,ok:=mx6_capture_place(run,player.pos,-facing,2.25,BOSS_MOVE_RADIUS);ok {
			// Semantic Cast deliberately resolves through the boss Attack sheet.
			mx6_capture_boss(run,pos,facing,.Shadow_Volley)
		}
	case .Familiar_Wisp:
		mx6_capture_familiar(run,facing,.Wisp)
	case .Familiar_Crow:
		mx6_capture_familiar(run,facing,.Crow)
	case .Familiar_Beast:
		mx6_capture_familiar(run,facing,.Spirit_Beast)
	case .Fow_Nova:
		// Put the caster beside the first room's north-west wall. The live-LOS
		// shader must clip this wide ring at the room boundary even with lighting
		// disabled; reveal-mode comparison intentionally bypasses the clip.
		room:=run.dungeon.rooms_buf[0]
		player.pos={f32(room.x)+1.2,f32(room.y)+1.2}
		player.prev_pos=player.pos
		player.facing={-1,-1}/math.sqrt(f32(2))
		feel_emit(
			run,.Nova,player.pos,ARCHETYPE_SKILL_COLORS[.Arcanist],.48,3.8,
			direction=player.facing,style=.Arcanist,priority=.High,
		)
		// Half-life makes the projected ring cross both adjacent walls, turning
		// this into a real per-fragment FOW test instead of an origin-only check.
		run.feel[len(run.feel)-1].remaining=.24
	case .None:
	}

	player.prev_pos=player.pos
	player.moving=false
	run.arrival_timer=0
	refresh_visibility(run)
	view_center_on(view,world_from_tile(player.pos))
}

MX7_Capture_Scenario :: enum u8 {
	None,
	Baseline,
	Door,
	Stairs,
	Shop,
	Bar,
	Garden,
	Boss,
	Crowd,
	Loot,
	Trap,
	Shrine,
	Secret,
	Fow,
}

mx7_capture_scenario_from_env :: proc(value: string) -> MX7_Capture_Scenario {
	switch value {
	case "baseline": return .Baseline
	case "door": return .Door
	case "stairs": return .Stairs
	case "shop": return .Shop
	case "bar": return .Bar
	case "garden": return .Garden
	case "boss": return .Boss
	case "crowd": return .Crowd
	case "loot": return .Loot
	case "trap": return .Trap
	case "shrine": return .Shrine
	case "secret": return .Secret
	case "fow": return .Fow
	}
	return .None
}

@(private = "file")
mx7_capture_room :: proc(run: ^Run, scenario: MX7_Capture_Scenario) -> (room: Room, room_index: int) {
	if run == nil || run.dungeon.room_count == 0 do return {},-1
	kind := Special_Room_Kind.None
	#partial switch scenario {
	case .Shop: kind = .Shop
	case .Bar: kind = .Bar
	case .Garden: kind = .Garden
	case:
	}
	if kind != .None {
		if special,found := special_room_for_kind(&run.dungeon,kind); found && 0 <= special.room_index && special.room_index < run.dungeon.room_count {
			return run.dungeon.rooms_buf[special.room_index],special.room_index
		}
	}
	if scenario == .Boss || scenario == .Stairs {
		room_index = run.dungeon.room_count-1
	} else {
		room_index = min(1,run.dungeon.room_count-1)
	}
	return run.dungeon.rooms_buf[room_index],room_index
}

@(private = "file")
mx7_force_special_room :: proc(run: ^Run, kind: Special_Room_Kind, room_index: int) -> bool {
	if run == nil || room_index < 0 || room_index >= run.dungeon.room_count do return false
	room := run.dungeon.rooms_buf[room_index]
	center := room_center(room)
	// Capture-only authored chamber: close the full perimeter around the existing
	// interior and leave one west-facing doorway. This cannot affect real floors.
	for x in room.x..<room.x+room.w {
		run.dungeon.tiles[x][room.y] = .Wall
		run.dungeon.tiles[x][room.y+room.h-1] = .Wall
	}
	for y in room.y..<room.y+room.h {
		run.dungeon.tiles[room.x][y] = .Wall
		run.dungeon.tiles[room.x+room.w-1][y] = .Wall
	}
	run.dungeon.tiles[room.x][center.y] = .Closed_Door
	run.dungeon.special_rooms_buf = {}
	run.dungeon.special_rooms_buf[0] = {kind,room_index}
	run.dungeon.special_room_count = 1
	run.dungeon.bar_furnishings = {}
	run.dungeon.shop_gold = {}
	plan_bar_furnishings(&run.dungeon)
	plan_shop_gold(&run.dungeon)
	run.has_shopkeeper = false
	run.shopkeeper = {}
	if kind == .Shop {
		run.shopkeeper = shopkeeper_make(run.seed,run.depth,room,room_index)
		run.has_shopkeeper = true
	}
	room_npc_initialize_ambient_residents(run)
	return true
}

@(private = "file")
mx7_clear_dynamic_world :: proc(run: ^Run) {
	if run == nil do return
	clear(&run.enemies)
	clear(&run.projectiles)
	clear(&run.familiars)
	clear(&run.bells)
	clear(&run.numbers)
	clear(&run.ground_items)
	clear(&run.traps)
	clear(&run.shrines)
	clear(&run.secrets)
	clear_feel_events(run)
	clear(&run.sfx)
	run.dungeon.solid_props = {}
	run.next_enemy_id = 0
	run.next_familiar_id = 0
	run.boss_engaged = false
}

@(private = "file")
mx7_stage_crowd :: proc(run: ^Run, center: Vec2) -> int {
	if run == nil do return 0
	clear(&run.enemies)
	kinds := [8]Enemy_Kind{.Ghoul,.Grave_Archer,.Cultist,.Gate_Warden,.Crypt_Brute,.Plague_Toad,.Ash_Hound,.Bone_Imp}
	offsets := [12]Vec2{{-2,-1},{-1,-2},{0,-2},{1,-2},{2,-1},{2,0},{2,1},{1,2},{0,2},{-1,2},{-2,1},{-2,0}}
	for offset,i in offsets {
		pos := center+offset
		if blocked_for_radius(&run.dungeon,pos.x,pos.y,ACTOR_MOVE_COLLISION_RADIUS,block_stairs=true) do continue
		enemy := enemy_make(kinds[i%len(kinds)],pos,run.depth)
		enemy.prev_pos = pos
		enemy.cooldown = 100
		enemy_ensure_id(run,&enemy)
		append(&run.enemies,enemy)
	}
	loot_rng := rng_make(derive_seed(run.seed,0x50455246),stream=11)
	for offset in ([4]Vec2{{-.6,-.6},{.6,-.6},{-.6,.6},{.6,.6}}) do append(&run.ground_items,make_loot(&loot_rng,center+offset,run=run))
	return len(run.enemies)
}

@(private = "file")
mx7_stage_dressing :: proc(run: ^Run, scenario: MX7_Capture_Scenario, center: Vec2) {
	if run == nil do return
	#partial switch scenario {
	case .Loot:
		clear(&run.ground_items)
		loot_rng := rng_make(derive_seed(run.seed,0x4D5837),stream=11)
		for offset in ([5]Vec2{{-.8,0},{.8,0},{0,-.8},{0,.8},{.7,.7}}) {
			append(&run.ground_items,make_loot(&loot_rng,center+offset,run=run))
		}
	case .Trap:
		clear(&run.traps)
		offsets := [3]Vec2{{-.8,.25},{.8,.25},{0,-.85}}
		for kind in Trap_Kind {
			append(&run.traps,Trap{pos=center+offsets[int(kind)],kind=kind,damage=18,active=true,revealed=true,reveal_progress=1})
		}
	case .Shrine:
		clear(&run.shrines)
		append(&run.shrines,Shrine{pos=center+{.8,0},kind=.Twilight})
	case .Secret:
		clear(&run.secrets)
		append(&run.secrets,Secret{pos=center+{.8,0},kind=.Hidden_Cache,revealed=true})
	case .Crowd:
		_ = mx7_stage_crowd(run,center)
	case:
	}
}

mx7_stage_capture :: proc(app: ^App, view: ^View, scenario: MX7_Capture_Scenario, theme_index: int, dark_override: int, open_door := false) -> bool {
	if app == nil || view == nil || app.mode != .Playing || scenario == .None do return false
	run := &app.run
	if 0 <= theme_index && theme_index < len(THEMES) do run.theme_index = theme_index
	if dark_override >= 0 do run.dark_floor = dark_override != 0
	run.arrival_timer = 0
	app.inventory_open,app.character_open,app.shop_open = false,false,false
	app.story_minigame = {}
	app_story_close_panel(app)
	room,room_index := mx7_capture_room(run,scenario)
	if room_index < 0 do return false
	mx7_clear_dynamic_world(run)
	if scenario == .Shop && !mx7_force_special_room(run,.Shop,room_index) do return false
	if scenario == .Bar && !mx7_force_special_room(run,.Bar,room_index) do return false
	if scenario == .Garden && !mx7_force_special_room(run,.Garden,room_index) do return false
	center_tile := room_center(room)
	center := Vec2{f32(center_tile.x)+.5,f32(center_tile.y)+.5}
	player_pos := center+Vec2{-1.2,.8}
	if scenario == .Stairs {
		s := run.dungeon.stairs
		center = {f32(s.x)+.5,f32(s.y)+.5}
		player_pos = center+{-2,0}
	} else if scenario == .Fow {
		player_pos = {f32(room.x)+1.2,f32(room.y)+1.2}
		center = player_pos
	} else if scenario == .Door {
		found_door := false
		for x in 0..<MAP_W {
			for y in 0..<MAP_H {
				kind := run.dungeon.tiles[x][y]
				if kind != .Closed_Door && kind != .Open_Door do continue
				if open_door do run.dungeon.tiles[x][y] = .Open_Door
				else do run.dungeon.tiles[x][y] = .Closed_Door
				center = {f32(x)+.5,f32(y)+.5}
				spots := [4]Vec2{{f32(x)+1.5,f32(y)+.5},{f32(x)-.5,f32(y)+.5},{f32(x)+.5,f32(y)+1.5},{f32(x)+.5,f32(y)-.5}}
				for spot in spots {
					if !blocked_for_radius(&run.dungeon,spot.x,spot.y,ACTOR_MOVE_COLLISION_RADIUS,block_stairs=true) {
						player_pos=spot
						found_door=true
						break
					}
				}
				if !found_door do continue
				break
			}
			if found_door do break
		}
		if !found_door do return false
	}
	if blocked_for_radius(&run.dungeon,player_pos.x,player_pos.y,ACTOR_MOVE_COLLISION_RADIUS,block_stairs=true) {
		player_pos = center
	}
	run.player.pos = player_pos
	run.player.prev_pos = player_pos
	run.player.facing = {1,0}
	run.player.moving = false
	if scenario == .Boss do mx6_capture_boss(run,center,{-1,0},.Shadow_Volley)
	mx7_stage_dressing(run,scenario,center)
	if scenario == .Fow {
		feel_emit(run,.Nova,player_pos,ARCHETYPE_SKILL_COLORS[.Arcanist],.48,3.8,direction={-1,-1},style=.Arcanist,priority=.High)
		run.feel[len(run.feel)-1].remaining = .24
	}
	refresh_visibility(run)
	// Baselines model a previously visited stairs tile so normal and dark cards
	// both exercise the persistent off-viewport guidance arrow.
	if scenario == .Baseline {
		s := run.dungeon.stairs
		if dungeon_in_bounds(s.x,s.y) do run.explored[s.x][s.y] = true
	}
	view_center_on(view,world_from_tile(center))
	return true
}

mx7_stage_perf :: proc(app: ^App, view: ^View, theme_index: int, dark_override: int) -> bool {
	if app == nil || view == nil || app.mode != .Playing do return false
	run := &app.run
	if 0 <= theme_index && theme_index < len(THEMES) do run.theme_index = theme_index
	if dark_override >= 0 do run.dark_floor = dark_override != 0
	mx7_clear_dynamic_world(run)
	// Dedicated synthetic 16×16 arena guarantees the visible workload rather
	// than inheriting generated special rooms, doors, or furnishings.
	run.dungeon.special_rooms_buf = {}
	run.dungeon.special_room_count = 0
	run.dungeon.bar_furnishings = {}
	run.dungeon.shop_gold = {}
	run.has_shopkeeper = false
	run.shopkeeper = {}
	run.ambient_residents = {}
	for x in 0..<MAP_W do for y in 0..<MAP_H do run.dungeon.tiles[x][y]=.Wall
	arena := Room{24,24,16,16}
	run.dungeon.room_count=1
	run.dungeon.rooms_buf[0]=arena
	for x in arena.x+1..<arena.x+arena.w-1 do for y in arena.y+1..<arena.y+arena.h-1 do run.dungeon.tiles[x][y]=.Floor
	run.dungeon.stairs={arena.x+arena.w-2,arena.y+arena.h-2}
	run.dungeon.tiles[run.dungeon.stairs.x][run.dungeon.stairs.y]=.Stairs
	center_tile := room_center(arena)
	center := Vec2{f32(center_tile.x)+.5,f32(center_tile.y)+.5}
	run.player.pos = center
	run.player.prev_pos = center
	run.player.facing = {1,0}
	run.player.moving = false
	run.player.hp = run.player.max_hp
	run.arrival_timer = 0
	if mx7_stage_crowd(run,center) != 12 do return false
	// Fixed persistent visual load is refreshed after each simulation pass.
	mx7_perf_refresh_visuals(run)
	append(&run.shrines,Shrine{pos=center+{2.3,0},kind=.Twilight})
	append(&run.traps,Trap{pos=center+{-2.3,0},kind=.Rune,damage=18,active=true,revealed=true,reveal_progress=1})
	refresh_visibility(run)
	view_center_on(view,world_from_tile(center))
	return true
}

mx7_perf_refresh_visuals :: proc(run: ^Run) {
	if run == nil do return
	center := run.player.pos
	clear(&run.projectiles)
	clear(&run.numbers)
	clear_feel_events(run)
	for i in 0..<24 {
		angle := f32(i)*math.TAU/24
		direction := Vec2{math.cos(angle),math.sin(angle)}
		pos := center+direction*(1+f32(i%3)*.45)
		append(&run.projectiles,Projectile{pos=pos,prev_pos=pos,vel=direction,visual=Projectile_Visual(i%len(Projectile_Visual)),visual_age=f32(i)*.07,damage=1,ttl=100,color=DAMAGE_TYPE_COLORS[Damage_Type(i%len(Damage_Type))]})
		feel_emit(run,Feel_Kind(i%(len(Feel_Kind)-1)),pos,DAMAGE_TYPE_COLORS[Damage_Type(i%len(Damage_Type))],100,.55,direction={1,0})
		append(&run.numbers,Damage_Number{pos=pos,value=10+i,kind=.Damage_Dealt,damage_type=Damage_Type(i%len(Damage_Type))})
	}
}

mx_story_stage_capture :: proc(app: ^App, scenario: MX_Story_Capture_Scenario) -> bool {
	if app == nil || app.mode != .Playing || scenario == .None do return false
	app.inventory_open,app.character_open,app.shop_open = false,false,false
	app.story_minigame = {}
	app_story_close_panel(app)

	switch scenario {
	case .Omen_Initial:
		beat := story_current_beat(&app.run)
		if beat == nil do return false
		app.run.story.relic = .Asterion_Nail
		if !app_story_open_omen(app) do return false
		app.story_panel.node_elapsed = 0
	case .Relic_Choices:
		beat := story_current_beat(&app.run)
		if beat == nil do return false
		app.run.story.relic = .Crown_Of_Antlers_And_Teeth
		if !app_story_open_omen(app) do return false
		app_story_panel_reveal(app)
		app.story_panel.choice_cursor = 1
	case .Guest:
		guest_index := -1
		for guest, index in app.run.story_runtime.guests {
			if guest.role == .Antlered_Hunter && guest.variant == 2 {
				guest_index = index
				break
			}
		}
		if guest_index < 0 do return false
		guest := &app.run.story_runtime.guests[guest_index]
		guest.witness = false
		guest.resolved = false
		if !app_story_open_guest_dialogue(app,guest_index) do return false
		app_story_panel_reveal(app)
		app.story_panel.choice_cursor = 2
	case .Soul:
		app.run.depth = 7
		room_index := min(1,app.run.dungeon.room_count-1)
		if room_index < 0 do return false
		app.run.dungeon.special_room_count = 1
		app.run.dungeon.special_rooms_buf[0] = {.Hall_Of_Unlost_Echoes,room_index}
		app.run.story_runtime.soul = {}
		app.run.story_runtime.hall = {}
		index := app.run.depth-1
		app.run.story_runtime.hall_ledgers[index] = {}
		app.run.story_runtime.soul_games[index] = {valid=true,room_index=room_index,outcome=.Won}
		story_populate_floor(&app.run)
		if !app.run.story_runtime.soul.present || !app_story_open_lossless_soul(app) do return false
		app_story_panel_reveal(app)
		app.story_panel.choice_cursor = 1
	case .Ending:
		app.run.story.flags.gate = .Unresolved
		if !story_record_gate_choice(&app.run.story,.Aid) do return false
		app.run.story_runtime.epilogue_stage = .Ending
		if !app_story_open_epilogue(app) do return false
		app_story_panel_reveal(app)
	case .None:
		return false
	}
	return app.story_panel.active && !app.story_minigame.active
}

mx_save_stage_capture :: proc(app:^App,scenario:MX_Save_Capture_Scenario)->bool {
	if app==nil||scenario==.None do return false
	profile_destroy(&app.profile)
	profile_init(&app.profile,"mx-save-capture")
	app.chronicle={archetype_filter=-1,difficulty_filter=-1,focus=.Timeline}
	app.active_run_damaged=false;app.active_run_available=false;app.confirm_index=0
	if scenario==.Recovery {app.active_run_damaged=true;app.mode=.Recovery;return true}
	if scenario==.Abandon {app.active_run_available=true;app.mode=.Abandon_Confirm;return true}
	if scenario!=.Empty {
		for i in 0..<14 {
			victory:=i%3==0
			run_id:=fmt.aprintf("capture-run-%02d",i)
			record:=Chronicle_Record{
				record_schema_version=CHRONICLE_RECORD_SCHEMA_VERSION,
				run_id=run_id,outcome=victory?.Victory:.Fallen,
				archetype=Archetype_Id(i%len(Archetype_Id)),difficulty=Difficulty_Id(i%len(Difficulty_Id)),
				seed=u64(0xA700+i),deepest_floor=1+i%DUNGEON_DEPTH,
				started_at_utc="2026-08-17T18:00:00Z",ended_at_utc="2026-08-17T18:42:00Z",
				active_ticks=u64((12+i*4)*SIM_HZ*60),final_level=2+i%9,kills=8+i*7,
				traps_triggered=i%5,shrines_used=1+i%4,secrets_opened=i%3,
				bars_visited=3,bars_toasted=i%4,challenge_rooms_cleared=i%2,
				run_modifier=Run_Modifier_Id(i%len(Run_Modifier_Id)),
				cause_of_death=victory?"":"void_sentinel",
				story_relic_id="Asterion_Nail",story_ending_id=victory?"the_held_door":"",
			}
			record.visited_theme_ids[0]="crypt_of_ash";record.visited_theme_count=1
			record.defeated_boss_ids[0]="ash_gallows";record.defeated_boss_count=1
			record.notable_items[0]={item_id="asterion_nail",display_name="Asterion Nail",rarity=.Unique};record.notable_count=1
			_=profile_finalize_record(&app.profile,&record)
			delete(run_id)
		}
	}
	app.chronicle.outcome=.All
	if scenario==.Victories do app.chronicle.outcome=.Victories
	if scenario==.Fallen do app.chronicle.outcome=.Fallen
	app.mode=.Chronicle
	return true
}

@(private = "file")
mx7_perf_percentile :: proc(samples: []f32, fraction: f32) -> f32 {
	if len(samples) == 0 do return 0
	index := clamp(int(math.ceil(fraction*f32(len(samples))))-1,0,len(samples)-1)
	return samples[index]
}

main :: proc() {
	window_width,window_height := 1280,720
	if value := os.get_env("ARCH_ROGUE_CAPTURE_WIDTH",context.temp_allocator); value != "" {
		if parsed,ok := strconv.parse_int(value); ok do window_width = clamp(parsed,640,7680)
	}
	if value := os.get_env("ARCH_ROGUE_CAPTURE_HEIGHT",context.temp_allocator); value != "" {
		if parsed,ok := strconv.parse_int(value); ok do window_height = clamp(parsed,480,4320)
	}
	when ARCH_ROGUE_ANDROID {
		// Zero requests raylib's physical NativeWindow dimensions instead of a
		// scaled 1280x720 framebuffer. Android owns one fullscreen surface.
		rl.SetConfigFlags({.FULLSCREEN_MODE})
		rl.InitWindow(0,0,"Arch Rogue " + VERSION)
	} else {
		rl.SetConfigFlags({.WINDOW_RESIZABLE})
		rl.InitWindow(i32(window_width), i32(window_height), "Arch Rogue " + VERSION)
		rl.SetWindowMinSize(640,480)
	}
	defer rl.CloseWindow()
	rl.SetExitKey(.KEY_NULL) // ESC navigates, it does not quit

	// Dev hooks: ARCH_ROGUE_SEED pins the run seed for repro; ARCH_ROGUE_ZOOM
	// sets initial zoom; ARCH_ROGUE_SHOT saves a screenshot (path relative to
	// cwd) at frame 40 and exits. ARCH_ROGUE_PLAY skips archetype select, with
	// ARCH_ROGUE_ARCHETYPE optionally selecting its class first. Capture staging
	// remains inert unless one of the dedicated MX capture variables names a scenario.
	seed := u64(time.now()._nsec)
	if env := os.get_env("ARCH_ROGUE_SEED", context.temp_allocator); env != "" {
		if v, seed_ok := strconv.parse_u64(env); seed_ok do seed = v
	}
	shot_path := os.get_env("ARCH_ROGUE_SHOT", context.allocator)
	shot_frame := 40
	if env := os.get_env("ARCH_ROGUE_SHOT_FRAME", context.temp_allocator); env != "" {
		if v, frame_ok := strconv.parse_int(env); frame_ok do shot_frame = v
	}
	capture_scenario:=mx6_capture_scenario_from_env(os.get_env("ARCH_ROGUE_MX6_CAPTURE",context.temp_allocator))
	mx7_capture_scenario:=mx7_capture_scenario_from_env(os.get_env("ARCH_ROGUE_MX7_CAPTURE",context.temp_allocator))
	mx_story_capture_scenario:=mx_story_capture_scenario_from_env(os.get_env("ARCH_ROGUE_MX_STORY_CAPTURE",context.temp_allocator))
	mx_save_capture_scenario:=mx_save_capture_scenario_from_env(os.get_env("ARCH_ROGUE_MX_SAVE_CAPTURE",context.temp_allocator))
	mx7_theme:=-1
	if value:=os.get_env("ARCH_ROGUE_CAPTURE_THEME",context.temp_allocator);value!="" {
		if parsed,ok:=strconv.parse_int(value);ok do mx7_theme=parsed
	}
	mx7_dark:=-1
	if value:=os.get_env("ARCH_ROGUE_CAPTURE_DARK",context.temp_allocator);value!="" {
		if parsed,ok:=strconv.parse_int(value);ok do mx7_dark=parsed
	}
	mx7_open_door:=os.get_env("ARCH_ROGUE_CAPTURE_DOOR",context.temp_allocator)=="open"
	mx7_perf_enabled:=os.get_env("ARCH_ROGUE_MX7_PERF",context.temp_allocator)!=""
	mx_save_perf_enabled:=os.get_env("ARCH_ROGUE_MX_SAVE_PERF",context.temp_allocator)!=""
	perf_enabled:=mx7_perf_enabled||mx_save_perf_enabled
	if (mx_story_capture_scenario != .None || mx_save_capture_scenario != .None) &&
		(int(rl.GetScreenWidth()) != window_width || int(rl.GetScreenHeight()) != window_height) {
		fmt.eprintln("UI_CAPTURE_ERROR requested window dimensions were not honored")
		return
	}
	perf_warmup:=120
	perf_frames:=600
	if value:=os.get_env("ARCH_ROGUE_PERF_WARMUP",context.temp_allocator);value!="" {
		if parsed,ok:=strconv.parse_int(value);ok do perf_warmup=max(0,parsed)
	}
	if value:=os.get_env("ARCH_ROGUE_PERF_FRAMES",context.temp_allocator);value!="" {
		if parsed,ok:=strconv.parse_int(value);ok do perf_frames=max(1,parsed)
	}
	capture_direction:=Vec2{1,1}
	if direction,ok:=mx6_capture_direction_from_env(os.get_env("ARCH_ROGUE_CAPTURE_DIR",context.temp_allocator));ok {
		capture_direction=direction
	}

	assets: Assets
	assets_load(&assets)
	defer assets_unload(&assets)
	audio: Audio
	audio_init(&audio)
	defer audio_shutdown(&audio)

	app: App
	app_init(&app, seed)
	platform:Platform_Runtime
	platform_runtime_init(&platform,app.mode)
	if platform.mobile do app.input_modality=.Touch
	persistence:Persistence_Coordinator
	perf_storage_directory:string
	defer {
		if perf_storage_directory!="" {
			_=os.remove_all(perf_storage_directory)
			delete(perf_storage_directory)
		}
	}
	dev_play_enabled:=os.get_env("ARCH_ROGUE_PLAY",context.temp_allocator)!=""
	normal_persistence_enabled:=capture_scenario==.None&&mx7_capture_scenario==.None&&mx_story_capture_scenario==.None&&mx_save_capture_scenario==.None&&
		!mx7_perf_enabled&&shot_path==""&&!dev_play_enabled
	if mx_save_perf_enabled {
		directory,directory_err:=os.make_directory_temp("","arch-rogue-mx-save-perf-*",context.allocator)
		if directory_err!=nil {
			fmt.eprintln("MX_SAVE_PERF_ERROR temporary storage unavailable")
			return
		}
		perf_storage_directory=directory
		paths,paths_ok:=storage_paths_from_directory(perf_storage_directory)
		if !paths_ok {
			fmt.eprintln("MX_SAVE_PERF_ERROR temporary paths unavailable")
			return
		}
		persistence={paths=paths,ready=true}
		if !save_worker_init(&persistence.worker) {
			storage_paths_destroy(&persistence.paths)
			persistence={}
			fmt.eprintln("MX_SAVE_PERF_ERROR save worker unavailable")
			return
		}
	} else if normal_persistence_enabled {
		persistence_ready:=persistence_coordinator_init(&persistence,&app,seed)
		if !persistence_ready&&os.get_env("ARCH_ROGUE_SAVE_TRACE",context.temp_allocator)!="" {
			fmt.eprintln("MX_SAVE_TRACE persistence coordinator initialization failed")
		}
	}
	if app.profile.profile_id=="" {
		profile_id:=persistence_new_profile_id(seed);profile_init(&app.profile,profile_id);delete(profile_id)
	}
	defer profile_destroy(&app.profile)
	defer run_destroy(&app.run)
	defer persistence_coordinator_destroy(&persistence)
	if capture_scenario!=.None || mx7_capture_scenario!=.None || mx_story_capture_scenario!=.None || mx_save_capture_scenario!=.None || perf_enabled {
		// Validation profiles are complete and ephemeral: persisted user graphics,
		// accessibility, difficulty, and zoom cannot change acceptance workloads.
		app.options.fullscreen=false
		if mx_save_capture_scenario!=.None&&window_width==3840&&window_height==2160 do app.options.fullscreen=true
		app.options.audio_enabled=false
		app.options.view_zoom=OPTIONS_VIEW_ZOOM_DEFAULT
		if capture_scenario!=.None {
			app.options.mist_enabled=false
		}
		if mx7_capture_scenario!=.None || mx_story_capture_scenario!=.None || mx_save_capture_scenario!=.None {
			app.options.lighting_enabled=true
			app.options.mist_enabled=false
			app.options.minimap_visible=true
		}
		if perf_enabled {
			app.options.lighting_enabled=true
			app.options.mist_enabled=true
			app.options.minimap_visible=false
			app.options.difficulty=.Medium
		}
		if capture_scenario!=.None {
			if value:=os.get_env("ARCH_ROGUE_LIGHTING",context.temp_allocator);value!="" do app.options.lighting_enabled=value!="0"
		}
	}
	app.minimap_visible=app.options.minimap_visible
	view: View
	view_init(&view)
	platform_bind_view_layout(&platform,&view)
	if platform.mobile&&!view_mobile_shader_preflight(&view) do platform_log("ARCH_ROGUE_ANDROID_ERROR required GLES shaders failed preflight")
	defer view_shutdown(&view)
	controller: Controller_Runtime
	apply_platform_effects(&app,&view,&audio,{.Apply_Window,.Apply_FPS,.Apply_Zoom,.Apply_Audio})
	if perf_enabled do rl.SetTargetFPS(0)
	if capture_scenario==.None && mx7_capture_scenario==.None && mx_story_capture_scenario==.None && mx_save_capture_scenario==.None && !perf_enabled {
		if env := os.get_env("ARCH_ROGUE_ZOOM", context.temp_allocator); env != "" {
			if v, zoom_ok := strconv.parse_f32(env); zoom_ok do view_apply_base_zoom(&view,v,clamp_to_options=false)
		}
	}
	if os.get_env("ARCH_ROGUE_REVEAL", context.temp_allocator) != "" {
		app.dev_reveal = true
	}
	// Unpersisted A/B hook for benchmarks and screenshot comparisons.
	if !perf_enabled && os.get_env("ARCH_ROGUE_MIST", context.temp_allocator) == "0" {
		app.options.mist_enabled = false
	}
	if os.get_env("ARCH_ROGUE_DEV", context.temp_allocator) != "" {
		app.dev_controls = true
	}
	if os.get_env("ARCH_ROGUE_PLAY", context.temp_allocator) != "" {
		_ = app_apply(&app, Intent{confirm = true}) // Title -> Select
		if archetype,ok:=dev_archetype_from_env(os.get_env("ARCH_ROGUE_ARCHETYPE",context.temp_allocator));ok {
			app.select_index=int(archetype)
		}
		if app_apply(&app, Intent{confirm = true}) { // Select -> Playing
			assets_activate_player(&assets,app.run.player.archetype)
			view_center_on(&view, world_from_tile(run_spawn_point(&app.run)))
		}
		// Dev: start deeper / spawn at the stairs room (boss arenas).
		if env := os.get_env("ARCH_ROGUE_DEPTH", context.temp_allocator); env != "" {
			if v, depth_ok := strconv.parse_int(env); depth_ok {
				for app.run.depth < v do run_descend(&app.run)
				view_center_on(&view, world_from_tile(run_spawn_point(&app.run)))
			}
		}
		// Dev: open a panel immediately for UI screenshots. ARCH_ROGUE_BAG=n
		// copies up to n shopkeeper stock items into the bag so item rows and
		// the selected-item panel can be captured without playing to loot.
		switch os.get_env("ARCH_ROGUE_OPEN", context.temp_allocator) {
		case "inventory": app.inventory_open = true
		case "character": app.character_open = true
		case "shop": app.shop_open = true
		}
		if env := os.get_env("ARCH_ROGUE_BAG", context.temp_allocator); env != "" {
			if count, bag_ok := strconv.parse_int(env); bag_ok && app.run.has_shopkeeper {
				keeper := &app.run.shopkeeper
				player := &app.run.player
				for i in 0 ..< min(count, keeper.stock_count) {
					if player.bag_count >= BAG_CAPACITY do break
					player.bag[player.bag_count] = keeper.stock[i]
					player.bag_count += 1
				}
			}
		}
		if perf_enabled {
			if app.story_panel.active {
				app_story_panel_reveal(&app)
				_=app_apply(&app,Intent{confirm=true})
			}
			// Raw dev descent queues the target floor's omen. Profiling needs an
			// active crowded floor, not a frozen modal, so discard only the pending
			// presentation request after retaining the generated story state.
			app.run.story_runtime.requests={}
			app_story_runtime_reset(&app)
			if !mx7_stage_perf(&app,&view,mx7_theme,mx7_dark) {
				fmt.eprintln("MX7_PERF_ERROR staging failed")
				return
			}
			app.minimap_visible=false
		}
		if os.get_env("ARCH_ROGUE_SPAWN", context.temp_allocator) == "stairs" {
			s := app.run.dungeon.stairs
			spots := [4]Vec2{
				{f32(s.x) - 2.5, f32(s.y) + 0.5},
				{f32(s.x) + 0.5, f32(s.y) - 2.5},
				{f32(s.x) + 3.5, f32(s.y) + 0.5},
				{f32(s.x) + 0.5, f32(s.y) + 3.5},
			}
			for spot in spots {
				if !blocked_for_radius(&app.run.dungeon, spot.x, spot.y, block_stairs = true) {
					app.run.player.pos = spot
					app.run.player.prev_pos = spot
					view_center_on(&view, world_from_tile(spot))
					break
				}
			}
		}
	}

	// Sim advances in fixed SIM_DT steps; rendering runs at display rate and
	// interpolates between the last two sim states.
	fixed_step:Mobile_Fixed_Step_State
	frame_count := 0
	perf_samples := make([dynamic]f32,0,perf_frames)
	defer delete(perf_samples)
	perf_resources_ready := true
	capture_stage_ok := true
	for !app.quit_requested {
		if platform.mobile {
			lifecycle_result:=platform_reduce_android_events(&platform,&app)
			platform_apply_lifecycle_result(
				&platform,lifecycle_result,&app,&view,&assets,&audio,&controller,&persistence,&fixed_step,
			)
			if platform.lifecycle.destroyed {
				app.quit_requested=true
				continue
			}
			if !mobile_lifecycle_interactive(&platform.lifecycle) {
				persistence_update_scheduler(&persistence,&app,rl.GetTime())
				platform_wait_suspended(&platform)
				free_all(context.temp_allocator)
				continue
			}
		}
		if rl.WindowShouldClose()&&app.mode!=.Save_Wait&&app.mode!=.Save_Error {
			live_run:=platform_live_descent(&app)
			if platform.mobile {
				if persistence.ready&&live_run do _=persistence_flush_for_suspend(&persistence,&app)
				app.quit_requested=true
				continue
			} else if persistence.ready&&live_run {
				app.persistence_request=.Save_Quit;app.persistence_return=.Paused;app.mode=.Save_Wait
				persistence.save_wait_presented=false
				app_clear_play_input(&app)
			} else {
				app.quit_requested=true
				continue
			}
		}
		raw_frame_dt := rl.GetFrameTime()
		frame_dt := min(raw_frame_dt, f32(MAX_FRAME_DT))
		fixed_capture := capture_scenario != .None || mx7_capture_scenario != .None || mx_story_capture_scenario != .None || mx_save_capture_scenario != .None
		if fixed_capture do frame_dt = SIM_DT
		if platform.resume_gate do frame_dt=0

		view_update(&view, frame_dt)
		mode_was := app.mode
		shop_was_open := app.shop_open
		intent: Intent
		resume_gate_was:=platform.resume_gate
		if !fixed_capture do intent = platform_collect_intent(&platform,&app,&view,&controller)
		if resume_gate_was&&!platform.resume_gate&&app.mode==.Playing do audio_resume(&audio)
		if cue, has_cue := audio_cue_for_intent(intent); has_cue do audio_play_cue(&audio,cue)
		if app_apply(&app, intent) {
			if mode_was == .Select && app.mode == .Playing {
				assets_activate_player(&assets,app.run.player.archetype)
			}
			view_center_on(&view, world_from_tile(run_spawn_point(&app.run)))
		}
		if platform.mobile&&!platform.resume_gate&&mode_was!=.Playing&&app.mode==.Playing do audio_resume(&audio)
		if app.mode==.Save_Wait&&mode_was!=.Save_Wait {
			persistence.save_wait_presented=false
			if !persistence.ready do persistence_fail_request(&app,app.persistence_request,.Write,app.persistence_return)
		}
		if shop_was_open != app.shop_open do view_clear_menu_click(&view)
		if mode_was != app.mode && (mode_was == .Select || app.mode == .Select) {
			view_clear_menu_click(&view)
		}
		if card(app.platform_effects)>0 {
			effects:=app.platform_effects
			apply_platform_effects(&app,&view,&audio,effects)
			if .Save_Options in effects&&persistence.ready do _=persistence_enqueue_options(&persistence,&app)
			app.platform_effects={}
		}
		if mx_save_perf_enabled&&frame_count==perf_warmup {
			persistence.run_snapshot_count=0
			persistence.run_snapshot_total_ms=0
			persistence.run_snapshot_max_ms=0
		}
		if mx_save_perf_enabled&&frame_count>=perf_warmup&&(frame_count-perf_warmup)%60==0&&
			!persistence.run_write_in_flight {
			app.run_dirty=true
			app.run_critical=true
			app.run_dirty_serial+=1
		}
		persistence_update_scheduler(&persistence,&app,rl.GetTime())
		if app.mode==.Resume_Veil&&mode_was!=.Resume_Veil {
			assets_activate_player(&assets,app.run.player.archetype)
			view_center_on(&view,world_from_tile(app.run.player.pos))
			controller={}
			view_clear_menu_click(&view)
		}

		if fixed_capture {
			app_tick(&app)
			mobile_fixed_step_reset(&fixed_step)
		} else {
			simulation_enabled:=!platform.resume_gate&&(!platform.mobile||mobile_lifecycle_interactive(&platform.lifecycle))
			steps:=mobile_fixed_step_advance(&fixed_step,frame_dt,SIM_DT,f32(MAX_FRAME_DT),simulation_enabled)
			for _ in 0..<steps do app_tick(&app)
		}
		persistence_update_scheduler(&persistence,&app,rl.GetTime())
		if perf_enabled do mx7_perf_refresh_visuals(&app.run)
		alpha := fixed_capture ? f32(1) : fixed_step.accumulator / SIM_DT
		// Modal/non-playing states freeze at the latest authoritative pose.
		// Otherwise a >60 Hz renderer repeatedly interpolates the final movement
		// segment while the inventory, death, or victory overlay pauses the sim.
		if app.mode != .Playing || app.inventory_open || app.character_open || app.shop_open ||
			app_play_modal_open(&app) {
			alpha = 1
		}
		audio_drain(&audio, &app.run)

		if app.mode == .Playing && !app.inventory_open && !app.character_open && !app.shop_open &&
			!app_play_modal_open(&app) {
			player := &app.run.player
			pos := player.prev_pos + (player.pos - player.prev_pos) * alpha
			view_follow(&view, world_from_tile(pos), frame_dt)
		}

		// Stage on the exact frame that will be captured, after ordinary simulation
		// and immediately before rendering, so transient action/effect state is fresh.
		if shot_path!="" && frame_count+1==shot_frame {
			if capture_scenario!=.None do mx6_stage_capture(&app,&view,capture_scenario,capture_direction)
			if mx7_capture_scenario!=.None do capture_stage_ok=mx7_stage_capture(&app,&view,mx7_capture_scenario,mx7_theme,mx7_dark,mx7_open_door)
			if mx_story_capture_scenario!=.None do capture_stage_ok=mx_story_stage_capture(&app,mx_story_capture_scenario)
			if mx_save_capture_scenario!=.None do capture_stage_ok=mx_save_stage_capture(&app,mx_save_capture_scenario)
			if !capture_stage_ok {
				fmt.eprintln("CAPTURE_ERROR staging failed")
				break
			}
			alpha=1
		}
		draw_frame(&view, &app, &assets, alpha)
		if platform.mobile&&!platform.ready_marker_emitted {
			mist_shader_ready:=view.mist!=nil&&view.mist.ready&&view.mist.shader_ok
			if assets_ready(&assets)&&view.effect_mask_shader_ready&&mist_shader_ready&&persistence.ready&&audio_loaded_cue_count(&audio)>0 {
				platform.ready_marker_emitted=true
				platform_log(fmt.tprintf(
					"ARCH_ROGUE_READY version=%s native=%dx%d assets=%d shaders=2/2 storage=ok audio=%d",
					VERSION,platform.metrics.surface_width,platform.metrics.surface_height,
					assets_loaded_texture_count(&assets),audio_loaded_cue_count(&audio),
				))
			}
		}
		if app.mode==.Save_Wait do persistence.save_wait_presented=true

		frame_count += 1
		if perf_enabled && frame_count > perf_warmup {
			mist_ready := view.mist != nil && view.mist.ready && view.mist.shader_ok && view.mist.field_ready
			perf_resources_ready = perf_resources_ready && view.lighting_ready && view.effect_mask_shader_ready && mist_ready
			append(&perf_samples,raw_frame_dt*1000)
			if len(perf_samples) >= perf_frames {
				for i in 1..<len(perf_samples) {
					value:=perf_samples[i]
					j:=i
					for j>0 && perf_samples[j-1]>value {
						perf_samples[j]=perf_samples[j-1]
						j-=1
					}
					perf_samples[j]=value
				}
				total:f32
				for sample in perf_samples do total+=sample
				mean:=total/f32(len(perf_samples))
				p95:=mx7_perf_percentile(perf_samples[:],.95)
				p99:=mx7_perf_percentile(perf_samples[:],.99)
				max_ms:=perf_samples[len(perf_samples)-1]
				if mx_save_perf_enabled {
					_=persistence_drain_worker(&persistence)
					saved_data,saved_status:=storage_recover_document(persistence.paths.run,.Run)
					save_valid:=false
					if saved_status==.Valid {
						document,decoded:=persistence_decode_run(saved_data)
						save_valid=decoded==.Valid&&document.payload.terminal==.Active
						run_document_destroy(&document)
					}
					delete(saved_data)
					snapshot_mean:=persistence.run_snapshot_count>0?persistence.run_snapshot_total_ms/f64(persistence.run_snapshot_count):f64(0)
					mist_ready=view.mist!=nil&&view.mist.ready&&view.mist.shader_ok&&view.mist.field_ready
					mist_allocated:=view.mist!=nil
					mist_texture_ready:=mist_allocated&&view.mist.ready
					mist_shader_ready:=mist_allocated&&view.mist.shader_ok
					mist_field_ready:=mist_allocated&&view.mist.field_ready
					fmt.printf("MX_SAVE_PERF {{\"frames\":%d,\"mean_ms\":%.3f,\"p95_ms\":%.3f,\"p99_ms\":%.3f,\"max_ms\":%.3f,\"mean_fps\":%.2f,\"snapshot_count\":%d,\"snapshot_mean_ms\":%.3f,\"snapshot_max_ms\":%.3f,\"save_valid\":%v,\"lighting_ready\":%v,\"effect_ready\":%v,\"mist_ready\":%v,\"mist_allocated\":%v,\"mist_texture_ready\":%v,\"mist_shader_ready\":%v,\"mist_field_ready\":%v,\"mist_enabled\":%v,\"modal_open\":%v,\"mode\":\"%v\",\"resources_ready\":%v}}\n",
						len(perf_samples),mean,p95,p99,max_ms,mean>0?1000/mean:f32(0),
						persistence.run_snapshot_count,snapshot_mean,persistence.run_snapshot_max_ms,
						save_valid,view.lighting_ready,view.effect_mask_shader_ready,mist_ready,
						mist_allocated,mist_texture_ready,mist_shader_ready,mist_field_ready,
						app.options.mist_enabled,app_play_modal_open(&app),app.mode,perf_resources_ready)
				} else {
					fmt.printf("MX7_PERF {{\"frames\":%d,\"mean_ms\":%.3f,\"p95_ms\":%.3f,\"p99_ms\":%.3f,\"max_ms\":%.3f,\"mean_fps\":%.2f,\"resources_ready\":%v}}\n",len(perf_samples),mean,p95,p99,max_ms,mean>0?1000/mean:f32(0),perf_resources_ready)
				}
				break
			}
		}
		if shot_path != "" && frame_count == shot_frame && capture_stage_ok {
			rl.TakeScreenshot(strings.clone_to_cstring(shot_path, context.temp_allocator))
			break
		}

		free_all(context.temp_allocator)
	}
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
		if rl.IsKeyPressed(.UP)||rl.IsKeyPressed(.W) do intent.menu_delta-=1
		if rl.IsKeyPressed(.DOWN)||rl.IsKeyPressed(.S) do intent.menu_delta+=1
		if rl.IsKeyPressed(.ENTER)||rl.IsKeyPressed(.KP_ENTER) do intent.confirm=true
		if rl.IsKeyPressed(.R) {intent.menu_index=int(Title_Action.Resume);intent.menu_index_valid=true;intent.confirm=true}
		if rl.IsKeyPressed(.N) {intent.menu_index=int(Title_Action.New_Run);intent.menu_index_valid=true;intent.confirm=true}
		if rl.IsKeyPressed(.C) {intent.menu_index=int(Title_Action.Chronicle);intent.menu_index_valid=true;intent.confirm=true}
		if rl.IsKeyPressed(.O) {intent.menu_index=int(Title_Action.Options);intent.menu_index_valid=true;intent.confirm=true}
		if rl.IsKeyPressed(.Q) {intent.menu_index=int(Title_Action.Quit);intent.menu_index_valid=true;intent.confirm=true}
		if rl.IsKeyPressed(.ESCAPE) do intent.back=true
	case .Select:
		if mouse_moved {
			if index, found := select_slot_at(app,mouse); found {
				intent.menu_index = index
				intent.menu_index_valid = true
			}
		}
		if rl.IsMouseButtonPressed(.LEFT) {
			current_index, current_found := select_slot_at(app, mouse)
			design_mouse := ui_screen_to_design(mouse)
			previous_region_hit := view.archetype_click_rect_valid &&
				rl.CheckCollisionPointRec(design_mouse, view.archetype_click_rect)
			index, found, confirm := desktop_resolve_reflow_menu_click(
				&view.menu_click,
				.Archetype,
				current_index,
				current_found,
				previous_region_hit,
				rl.GetTime(),
			)
			if found {
				intent.menu_index = index
				intent.menu_index_valid = true
				intent.confirm = confirm
				intent.pointer_confirm = confirm
				if confirm {
					view.archetype_click_rect_valid = false
				} else {
					view.archetype_click_rect = select_slot_rect(app, index)
					view.archetype_click_rect_valid = true
				}
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
				if rl.IsKeyPressed(.LEFT)||rl.IsKeyPressed(.A) do intent.menu_horizontal-=1
				if rl.IsKeyPressed(.RIGHT)||rl.IsKeyPressed(.D) do intent.menu_horizontal+=1
				if rl.IsKeyPressed(.UP)||rl.IsKeyPressed(.W) do intent.menu_delta-=1
				if rl.IsKeyPressed(.DOWN)||rl.IsKeyPressed(.S) do intent.menu_delta+=1
			} else {
				if rl.IsKeyPressed(.UP)||rl.IsKeyPressed(.W)||rl.IsKeyPressed(.LEFT)||rl.IsKeyPressed(.A) do intent.menu_delta-=1
				if rl.IsKeyPressed(.DOWN)||rl.IsKeyPressed(.S)||rl.IsKeyPressed(.RIGHT)||rl.IsKeyPressed(.D) do intent.menu_delta+=1
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
			if rl.IsKeyPressed(.LEFT)||rl.IsKeyPressed(.A) do intent.menu_horizontal-=1
			if rl.IsKeyPressed(.RIGHT)||rl.IsKeyPressed(.D) do intent.menu_horizontal+=1
			if rl.IsKeyPressed(.UP)||rl.IsKeyPressed(.W) do intent.menu_delta-=1
			if rl.IsKeyPressed(.DOWN)||rl.IsKeyPressed(.S) do intent.menu_delta+=1
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
			if rl.IsKeyPressed(.LEFT)||rl.IsKeyPressed(.A) do intent.menu_horizontal-=1
			if rl.IsKeyPressed(.RIGHT)||rl.IsKeyPressed(.D) do intent.menu_horizontal+=1
			if rl.IsKeyPressed(.UP)||rl.IsKeyPressed(.W) do intent.menu_delta-=1
			if rl.IsKeyPressed(.DOWN)||rl.IsKeyPressed(.S)||rl.IsKeyPressed(.X) do intent.menu_delta+=1
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
			if rl.IsKeyPressed(.W) || rl.IsKeyPressed(.UP) do intent.menu_delta -= 1
			if rl.IsKeyPressed(.X) || rl.IsKeyPressed(.DOWN) do intent.menu_delta += 1
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
				aim = arrow_aim
				if !controller.right_aim_this_frame do intent.aim = {}
			}
		raw := Desktop_Input{
			left = rl.IsKeyDown(.A) || rl.IsKeyDown(.LEFT),
			right = rl.IsKeyDown(.D) || rl.IsKeyDown(.RIGHT),
			up = rl.IsKeyDown(.W) || rl.IsKeyDown(.UP),
			down = rl.IsKeyDown(.S) || rl.IsKeyDown(.DOWN),
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

		if app.dev_controls {
			if rl.IsKeyPressed(.N) do intent.descend = true
			if rl.IsKeyPressed(.R) do intent.new_run = true
			if rl.IsKeyPressed(.B) do intent.boss_floor = true
		}
	case .Paused:
		if mouse_moved {if index,found:=pause_row_at(mouse);found {intent.menu_index=index;intent.menu_index_valid=true}}
		if rl.IsMouseButtonPressed(.LEFT) {if index,found:=pause_row_at(mouse);found {intent.menu_index=index;intent.menu_index_valid=true;intent.confirm=true;intent.pointer_confirm=true}}
		if rl.IsKeyPressed(.UP)||rl.IsKeyPressed(.W) do intent.menu_delta-=1
		if rl.IsKeyPressed(.DOWN)||rl.IsKeyPressed(.S) do intent.menu_delta+=1
		if rl.IsKeyPressed(.ENTER)||rl.IsKeyPressed(.KP_ENTER) do intent.confirm=true
		if rl.IsKeyPressed(.ESCAPE)||rl.IsKeyPressed(.BACKSPACE) do intent.back=true
	case .Options:
		if mouse_moved {if index,found:=options_row_at(app,mouse);found {intent.menu_index=index;intent.menu_index_valid=true}}
		if rl.IsMouseButtonPressed(.LEFT) {if index,found:=options_row_at(app,mouse);found {intent.menu_index=index;intent.menu_index_valid=true;intent.confirm=true}}
		if rl.IsKeyPressed(.UP)||rl.IsKeyPressed(.W) do intent.menu_delta-=1
		if rl.IsKeyPressed(.DOWN)||rl.IsKeyPressed(.S) do intent.menu_delta+=1
		if rl.IsKeyPressed(.LEFT)||rl.IsKeyPressed(.A) do intent.menu_horizontal-=1
		if rl.IsKeyPressed(.RIGHT)||rl.IsKeyPressed(.D) do intent.menu_horizontal+=1
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
			if rl.IsKeyPressed(.UP)||rl.IsKeyPressed(.W) do intent.menu_delta-=1
			if rl.IsKeyPressed(.DOWN)||rl.IsKeyPressed(.S) do intent.menu_delta+=1
			if rl.IsKeyPressed(.LEFT)||rl.IsKeyPressed(.A) do intent.menu_horizontal-=1
			if rl.IsKeyPressed(.RIGHT)||rl.IsKeyPressed(.D) do intent.menu_horizontal+=1
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
		if rl.IsKeyPressed(.UP)||rl.IsKeyPressed(.W)||rl.IsKeyPressed(.PAGE_UP) do intent.menu_delta-=1
		if rl.IsKeyPressed(.DOWN)||rl.IsKeyPressed(.S)||rl.IsKeyPressed(.PAGE_DOWN) do intent.menu_delta+=1
		if rl.IsKeyPressed(.LEFT)||rl.IsKeyPressed(.A) do intent.menu_horizontal-=1
		if rl.IsKeyPressed(.RIGHT)||rl.IsKeyPressed(.D) do intent.menu_horizontal+=1
		if rl.IsKeyPressed(.TAB) do intent.tab=true
		if rl.IsKeyPressed(.ENTER)||rl.IsKeyPressed(.KP_ENTER) do intent.confirm=true
		if rl.IsKeyPressed(.ESCAPE)||rl.IsKeyPressed(.BACKSPACE) do intent.back=true
	case .Abandon_Confirm:
		if mouse_moved {if index,found:=choice_overlay_row_at(mouse,2);found {intent.menu_index=index;intent.menu_index_valid=true}}
		if rl.IsMouseButtonPressed(.LEFT) {if index,found:=choice_overlay_row_at(mouse,2);found {intent.menu_index=index;intent.menu_index_valid=true;intent.confirm=true}}
		if rl.IsKeyPressed(.UP)||rl.IsKeyPressed(.W) do intent.menu_delta-=1
		if rl.IsKeyPressed(.DOWN)||rl.IsKeyPressed(.S) do intent.menu_delta+=1
		if rl.IsKeyPressed(.ENTER)||rl.IsKeyPressed(.KP_ENTER) do intent.confirm=true
		if rl.IsKeyPressed(.ESCAPE)||rl.IsKeyPressed(.BACKSPACE) do intent.back=true
	case .Recovery, .Save_Error:
		if mouse_moved {if index,found:=choice_overlay_row_at(mouse,3);found {intent.menu_index=index;intent.menu_index_valid=true}}
		if rl.IsMouseButtonPressed(.LEFT) {if index,found:=choice_overlay_row_at(mouse,3);found {intent.menu_index=index;intent.menu_index_valid=true;intent.confirm=true}}
		if rl.IsKeyPressed(.UP)||rl.IsKeyPressed(.W) do intent.menu_delta-=1
		if rl.IsKeyPressed(.DOWN)||rl.IsKeyPressed(.S) do intent.menu_delta+=1
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
