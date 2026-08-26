#+build !freestanding
package archrogue

// Desktop and Android platform entry: env-driven dev/capture configuration,
// OS-file storage primitives, the core:thread save worker, and the blocking
// frame loop over the shared game_init/game_frame/game_shutdown phases.

import "base:runtime"
import "core:fmt"
import "core:os"
import filepath "core:path/filepath"
import "core:strconv"
import "core:strings"
import "core:time"
import "core:thread"
import chan "core:sync/chan"

platform_now_utc_rfc3339 :: proc()->string {
	value,ok:=time.time_to_rfc3339(time.now(),include_nanos=true,allocator=context.allocator)
	if !ok do return "1970-01-01T00:00:00Z"
	return value
}

platform_tick_us :: proc()->u64 {
	return u64(time.tick_now()._nsec/1000)
}

platform_tick_ms_f64 :: proc()->f64 {
	return f64(time.tick_now()._nsec)/1e6
}

// Job payloads cross the save worker thread; test and arena allocators remain
// confined to the producer thread that owns them.
platform_save_allocator :: proc()->runtime.Allocator {
	return runtime.heap_allocator()
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

Save_Worker :: struct {
	jobs:chan.Chan(Save_Job),
	completions:chan.Chan(Save_Completion),
	thread:^thread.Thread,
	ready:bool,
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

persistence_drain_worker :: proc(coordinator:^Persistence_Coordinator)->bool {
	if coordinator==nil||!coordinator.ready do return false
	save_worker_shutdown(&coordinator.worker)
	coordinator.run_write_in_flight=false
	return save_worker_init(&coordinator.worker)
}

save_worker_try_completion :: proc(worker:^Save_Worker)->(Save_Completion,bool) {
	if worker==nil||!worker.ready do return {},false
	return chan.try_recv(worker.completions)
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

// Machine-readable perf report lines go to stdout; profiling scripts grep them.
platform_report_line :: proc(line: string) {
	fmt.printf("%s\n", line)
}

@(private = "file")
game_boot_config_from_env :: proc() -> Game_Boot_Config {
	config := game_boot_config_default()
	config.steam_deck = os.get_env("SteamDeck", context.temp_allocator) == "1"
	if value := os.get_env("ARCH_ROGUE_CAPTURE_WIDTH", context.temp_allocator); value != "" {
		if parsed, ok := strconv.parse_int(value); ok do config.window_width = clamp(parsed, 640, 7680)
	}
	if value := os.get_env("ARCH_ROGUE_CAPTURE_HEIGHT", context.temp_allocator); value != "" {
		if parsed, ok := strconv.parse_int(value); ok do config.window_height = clamp(parsed, 480, 4320)
	}
	// Dev hooks: ARCH_ROGUE_SEED pins the run seed for repro; ARCH_ROGUE_ZOOM
	// sets initial zoom; ARCH_ROGUE_SHOT saves a screenshot (path relative to
	// cwd) at frame 40 and exits. ARCH_ROGUE_PLAY skips archetype select, with
	// ARCH_ROGUE_ARCHETYPE optionally selecting its class first. Capture staging
	// remains inert unless one of the dedicated MX capture variables names a scenario.
	config.seed = u64(time.now()._nsec)
	if env := os.get_env("ARCH_ROGUE_SEED", context.temp_allocator); env != "" {
		if v, seed_ok := strconv.parse_u64(env); seed_ok do config.seed = v
	}
	config.shot_path = os.get_env("ARCH_ROGUE_SHOT", context.allocator)
	if env := os.get_env("ARCH_ROGUE_SHOT_FRAME", context.temp_allocator); env != "" {
		if v, frame_ok := strconv.parse_int(env); frame_ok do config.shot_frame = v
	}
	config.capture_scenario = mx6_capture_scenario_from_env(os.get_env("ARCH_ROGUE_MX6_CAPTURE", context.temp_allocator))
	config.mx7_capture_scenario = mx7_capture_scenario_from_env(os.get_env("ARCH_ROGUE_MX7_CAPTURE", context.temp_allocator))
	config.mx_story_capture_scenario = mx_story_capture_scenario_from_env(os.get_env("ARCH_ROGUE_MX_STORY_CAPTURE", context.temp_allocator))
	config.mx_save_capture_scenario = mx_save_capture_scenario_from_env(os.get_env("ARCH_ROGUE_MX_SAVE_CAPTURE", context.temp_allocator))
	if value := os.get_env("ARCH_ROGUE_CAPTURE_THEME", context.temp_allocator); value != "" {
		if parsed, ok := strconv.parse_int(value); ok do config.mx7_theme = parsed
	}
	if value := os.get_env("ARCH_ROGUE_CAPTURE_DARK", context.temp_allocator); value != "" {
		if parsed, ok := strconv.parse_int(value); ok do config.mx7_dark = parsed
	}
	config.mx7_open_door = os.get_env("ARCH_ROGUE_CAPTURE_DOOR", context.temp_allocator) == "open"
	config.mx7_perf_enabled = os.get_env("ARCH_ROGUE_MX7_PERF", context.temp_allocator) != ""
	config.mx_save_perf_enabled = os.get_env("ARCH_ROGUE_MX_SAVE_PERF", context.temp_allocator) != ""
	if value := os.get_env("ARCH_ROGUE_PERF_WARMUP", context.temp_allocator); value != "" {
		if parsed, ok := strconv.parse_int(value); ok do config.perf_warmup = max(0, parsed)
	}
	if value := os.get_env("ARCH_ROGUE_PERF_FRAMES", context.temp_allocator); value != "" {
		if parsed, ok := strconv.parse_int(value); ok do config.perf_frames = max(1, parsed)
	}
	if direction, ok := mx6_capture_direction_from_env(os.get_env("ARCH_ROGUE_CAPTURE_DIR", context.temp_allocator)); ok {
		config.capture_direction = direction
	}
	config.dev_play = os.get_env("ARCH_ROGUE_PLAY", context.temp_allocator) != ""
	if archetype, ok := dev_archetype_from_env(os.get_env("ARCH_ROGUE_ARCHETYPE", context.temp_allocator)); ok {
		config.dev_archetype = archetype
		config.dev_archetype_valid = true
	}
	if env := os.get_env("ARCH_ROGUE_DEPTH", context.temp_allocator); env != "" {
		if v, depth_ok := strconv.parse_int(env); depth_ok do config.dev_depth = v
	}
	switch os.get_env("ARCH_ROGUE_OPEN", context.temp_allocator) {
	case "inventory": config.dev_open = .Inventory
	case "character": config.dev_open = .Character
	case "shop": config.dev_open = .Shop
	}
	if env := os.get_env("ARCH_ROGUE_BAG", context.temp_allocator); env != "" {
		if count, bag_ok := strconv.parse_int(env); bag_ok do config.dev_bag = count
	}
	config.dev_spawn_stairs = os.get_env("ARCH_ROGUE_SPAWN", context.temp_allocator) == "stairs"
	if env := os.get_env("ARCH_ROGUE_ZOOM", context.temp_allocator); env != "" {
		if v, zoom_ok := strconv.parse_f32(env); zoom_ok {
			config.dev_zoom = v
			config.dev_zoom_valid = true
		}
	}
	config.dev_reveal = os.get_env("ARCH_ROGUE_REVEAL", context.temp_allocator) != ""
	config.dev_mist_off = os.get_env("ARCH_ROGUE_MIST", context.temp_allocator) == "0"
	config.dev_controls = os.get_env("ARCH_ROGUE_DEV", context.temp_allocator) != ""
	if value := os.get_env("ARCH_ROGUE_LIGHTING", context.temp_allocator); value != "" {
		config.dev_lighting = value != "0" ? 1 : 0
	}
	config.save_trace = os.get_env("ARCH_ROGUE_SAVE_TRACE", context.temp_allocator) != ""
	// Depot smoke gate (STEAM.md S5): ARCH_ROGUE_SMOKE_TEST=1 draws a few real
	// frames and exits 0, so a bundle that cannot reach its title screen fails
	// in CI instead of shipping. A numeric value overrides the frame count.
	if value := os.get_env("ARCH_ROGUE_SMOKE_TEST", context.temp_allocator); value != "" {
		config.smoke_frames = 5
		if parsed, ok := strconv.parse_int(value); ok && parsed > 1 do config.smoke_frames = parsed
	}
	return config
}

main :: proc() {
	config := game_boot_config_from_env()
	defer delete(config.shot_path)
	if config.mx_save_perf_enabled {
		directory, directory_err := os.make_directory_temp("", "arch-rogue-mx-save-perf-*", context.allocator)
		if directory_err != nil {
			fmt.eprintln("MX_SAVE_PERF_ERROR temporary storage unavailable")
			return
		}
		config.perf_storage_directory = directory
	}
	defer {
		if config.perf_storage_directory != "" {
			_ = os.remove_all(config.perf_storage_directory)
			delete(config.perf_storage_directory)
		}
	}
	// Game_Runtime embeds App and View (~300 KiB); keep it off the stack.
	rt := new(Game_Runtime)
	defer free(rt)
	if !game_init(rt, config) do return
	smoke_remaining := config.smoke_frames
	for game_frame(rt) {
		if config.smoke_frames > 0 {
			smoke_remaining -= 1
			if smoke_remaining <= 0 {
				platform_log("ARCH_ROGUE_SMOKE_TEST ok")
				rt.app.quit_requested = true
			}
		}
	}
	game_shutdown(rt)
}