#+build freestanding
package archrogue

// Web (Emscripten/WebAssembly) platform entry. The browser shell drives the
// shared game phases from requestAnimationFrame through ar_web_tick; boot waits
// for asynchronous IndexedDB hydration without ASYNCIFY by polling a flag from
// the frame callback. Persistence reuses the shared document/recovery logic
// against an in-memory mirror whose writes flush asynchronously to IndexedDB;
// browsers do not guarantee final writes on tab close, so lifecycle checkpoints
// are best-effort by design.

import "base:runtime"
import "core:fmt"
import "core:strconv"
import "core:strings"
import rl "../vendor/raylib"

// ---------------------------------------------------------------------------
// Emscripten libc and JS-library bridge. Symbols resolve at the emcc link.

@(default_calling_convention = "c")
foreign {
	memalign           :: proc(alignment, size: uint) -> rawptr ---
	@(link_name = "free")
	web_libc_free      :: proc(ptr: rawptr) ---
	emscripten_get_now :: proc() -> f64 ---

	// web/library_archrogue.js
	ar_js_console_log        :: proc(level: i32, ptr: rawptr, length: i32) ---
	ar_js_utc_rfc3339        :: proc(buffer: rawptr, capacity: i32) -> i32 ---
	ar_js_unix_ms            :: proc() -> f64 ---
	ar_js_canvas_width       :: proc() -> i32 ---
	ar_js_canvas_height      :: proc() -> i32 ---
	ar_js_query_param        :: proc(name_ptr: rawptr, name_len: i32, buffer: rawptr, capacity: i32) -> i32 ---
	ar_js_request_fullscreen :: proc(enable: i32) ---
	ar_js_storage_hydrate    :: proc() ---
	ar_js_storage_put        :: proc(key_ptr: rawptr, key_len: i32, data_ptr: rawptr, data_len: i32) ---
	ar_js_storage_delete     :: proc(key_ptr: rawptr, key_len: i32) ---
	ar_js_pack_request       :: proc(name_ptr: rawptr, name_len: i32) ---
	ar_js_boot_complete      :: proc() ---
	ar_js_boot_failed        :: proc(message_ptr: rawptr, message_len: i32) ---
	ar_js_game_ended         :: proc() ---
}

// ---------------------------------------------------------------------------
// Context: Emscripten dlmalloc-backed allocator plus a fixed temp arena. The
// Odin wasm page allocator must never run here; Emscripten's sbrk owns memory
// growth and the heap is pinned (fixed INITIAL_MEMORY, growth disabled).

@(private = "file")
web_allocator_proc :: proc(
	allocator_data: rawptr,
	mode: runtime.Allocator_Mode,
	size, alignment: int,
	old_memory: rawptr,
	old_size: int,
	location := #caller_location,
) -> ([]byte, runtime.Allocator_Error) {
	switch mode {
	case .Alloc, .Alloc_Non_Zeroed:
		if size <= 0 do return nil, nil
		ptr := memalign(uint(max(alignment, 16)), uint(size))
		if ptr == nil do return nil, .Out_Of_Memory
		bytes := ([^]byte)(ptr)[:size]
		if mode == .Alloc do runtime.mem_zero(raw_data(bytes), size)
		return bytes, nil
	case .Free:
		if old_memory != nil do web_libc_free(old_memory)
		return nil, nil
	case .Resize, .Resize_Non_Zeroed:
		if size <= 0 {
			if old_memory != nil do web_libc_free(old_memory)
			return nil, nil
		}
		ptr := memalign(uint(max(alignment, 16)), uint(size))
		if ptr == nil do return nil, .Out_Of_Memory
		bytes := ([^]byte)(ptr)[:size]
		if mode == .Resize && size > old_size {
			runtime.mem_zero(raw_data(bytes[old_size:]), size - old_size)
		}
		if old_memory != nil {
			runtime.mem_copy_non_overlapping(raw_data(bytes), old_memory, min(size, old_size))
			web_libc_free(old_memory)
		}
		return bytes, nil
	case .Free_All:
		return nil, .Mode_Not_Implemented
	case .Query_Features:
		set := (^runtime.Allocator_Mode_Set)(old_memory)
		if set != nil {
			set^ = {.Alloc, .Alloc_Non_Zeroed, .Free, .Resize, .Resize_Non_Zeroed, .Query_Features}
		}
		return nil, nil
	case .Query_Info:
		return nil, .Mode_Not_Implemented
	}
	return nil, nil
}

@(private = "file")
web_allocator :: proc() -> runtime.Allocator {
	return {procedure = web_allocator_proc, data = nil}
}

// Frame-scoped temp arena; free_all at the end of each game_frame resets it.
WEB_TEMP_ARENA_BYTES :: 8 * 1024 * 1024

@(private = "file")
Web_Temp_Arena :: struct {
	offset:    int,
	high_mark: int,
	buffer:    [WEB_TEMP_ARENA_BYTES]u8,
}

@(private = "file")
web_temp_arena: Web_Temp_Arena

@(private = "file")
web_temp_allocator_proc :: proc(
	allocator_data: rawptr,
	mode: runtime.Allocator_Mode,
	size, alignment: int,
	old_memory: rawptr,
	old_size: int,
	location := #caller_location,
) -> ([]byte, runtime.Allocator_Error) {
	arena := (^Web_Temp_Arena)(allocator_data)
	switch mode {
	case .Alloc, .Alloc_Non_Zeroed, .Resize, .Resize_Non_Zeroed:
		if size <= 0 do return nil, nil
		aligned := (arena.offset + alignment - 1) & ~(alignment - 1)
		if aligned + size > len(arena.buffer) do return nil, .Out_Of_Memory
		bytes := arena.buffer[aligned:aligned+size]
		arena.offset = aligned + size
		arena.high_mark = max(arena.high_mark, arena.offset)
		if mode == .Alloc || mode == .Resize {
			runtime.mem_zero(raw_data(bytes), size)
		}
		if (mode == .Resize || mode == .Resize_Non_Zeroed) && old_memory != nil {
			runtime.mem_copy_non_overlapping(raw_data(bytes), old_memory, min(size, old_size))
		}
		return bytes, nil
	case .Free:
		return nil, nil
	case .Free_All:
		arena.offset = 0
		return nil, nil
	case .Query_Features:
		set := (^runtime.Allocator_Mode_Set)(old_memory)
		if set != nil {
			set^ = {.Alloc, .Alloc_Non_Zeroed, .Free, .Free_All, .Resize, .Resize_Non_Zeroed, .Query_Features}
		}
		return nil, nil
	case .Query_Info:
		return nil, .Mode_Not_Implemented
	}
	return nil, nil
}

@(private = "file")
web_temp_allocator :: proc() -> runtime.Allocator {
	return {procedure = web_temp_allocator_proc, data = &web_temp_arena}
}

@(private = "file")
web_context_value: runtime.Context

@(private = "file")
web_context_ready: bool

// ---------------------------------------------------------------------------
// Platform seam implementations shared code calls into.

platform_web_console_log :: proc(message: string) {
	if len(message) == 0 do return
	ar_js_console_log(1, raw_data(message), i32(len(message)))
}

// Machine-readable perf report lines; the browser harness reads the console.
platform_report_line :: proc(line: string) {
	platform_web_console_log(line)
}

platform_now_utc_rfc3339 :: proc() -> string {
	buffer: [48]u8
	length := ar_js_utc_rfc3339(&buffer[0], i32(len(buffer)))
	if length <= 0 do return strings.clone("1970-01-01T00:00:00Z")
	return strings.clone(string(buffer[:length]))
}

platform_tick_us :: proc() -> u64 {
	return u64(emscripten_get_now() * 1000)
}

platform_tick_ms_f64 :: proc() -> f64 {
	return emscripten_get_now()
}

// Persistence jobs never cross a thread on web; the ambient allocator owns them.
platform_save_allocator :: proc() -> runtime.Allocator {
	return context.allocator
}

web_apply_fullscreen :: proc(enable: bool) {
	ar_js_request_fullscreen(enable ? 1 : 0)
}

// ---------------------------------------------------------------------------
// Storage: byte-identical documents in an in-memory mirror keyed by the same
// path strings the desktop uses, hydrated once from IndexedDB before boot and
// flushed to IndexedDB asynchronously on every mutation. The shared durable
// write/recovery/quarantine logic runs unchanged against these primitives.

@(private = "file")
web_store: map[string][]byte

@(private = "file")
web_store_hydrated: bool

@(private = "file")
web_store_set :: proc(key: string, data: []byte) {
	if previous, exists := &web_store[key]; exists {
		delete(previous^)
		previous^ = data
		return
	}
	web_store[strings.clone(key)] = data
}

@(private = "file")
web_store_remove :: proc(key: string) {
	if stored_key, value, exists := map_entry_key_value_erase(&web_store, key); exists {
		delete(stored_key)
		delete(value)
	}
}

// map helper: erase returning ownership of stored key and value.
@(private = "file")
map_entry_key_value_erase :: proc(store: ^map[string][]byte, key: string) -> (stored_key: string, value: []byte, existed: bool) {
	existing_key, existing_value := delete_key(store, key)
	if existing_key == "" && existing_value == nil do return "", nil, false
	return existing_key, existing_value, true
}

storage_ensure_directory :: proc(directory: string) -> bool {
	return directory != ""
}

platform_storage_paths :: proc() -> (paths: Storage_Paths, ok: bool) {
	return {
		directory = strings.clone("/save"),
		options = strings.clone("/save/options.json"),
		profile = strings.clone("/save/profile.json"),
		run = strings.clone("/save/run.json"),
	}, true
}

platform_legacy_options_path :: proc() -> string {
	return ""
}

storage_file_exists :: proc(path: string) -> bool {
	return path in web_store
}

storage_remove_file :: proc(path: string) -> bool {
	web_store_remove(path)
	ar_js_storage_delete(raw_data(path), i32(len(path)))
	return true
}

storage_read_bounded :: proc(path: string, max_bytes: int) -> ([]byte, Persistence_Decode_Status) {
	data, exists := web_store[path]
	if !exists do return nil, .Missing
	if len(data) > max_bytes do return nil, .Oversize
	owned := make([]byte, len(data))
	copy(owned, data)
	return owned, .Valid
}

storage_sync_parent :: proc(path: string) -> bool {
	// IndexedDB has no directory metadata; per-key puts are self-contained.
	return true
}

storage_write_synced :: proc(path: string, data: []byte) -> bool {
	owned := make([]byte, len(data))
	copy(owned, data)
	web_store_set(path, owned)
	ar_js_storage_put(raw_data(path), i32(len(path)), raw_data(data), i32(len(data)))
	return true
}

storage_replace_write_through :: proc(source, destination: string) -> bool {
	data, exists := web_store[source]
	if !exists do return false
	moved := make([]byte, len(data))
	copy(moved, data)
	web_store_set(destination, moved)
	web_store_remove(source)
	ar_js_storage_put(raw_data(destination), i32(len(destination)), raw_data(moved), i32(len(moved)))
	ar_js_storage_delete(raw_data(source), i32(len(source)))
	return true
}

@(export)
ar_web_store_hydrate_entry :: proc "c" (key_ptr: [^]u8, key_len: i32, data_ptr: [^]u8, data_len: i32) {
	context = web_context_value
	if key_len <= 0 || data_len < 0 do return
	key := string(key_ptr[:key_len])
	data := make([]byte, int(data_len))
	if data_len > 0 do copy(data, data_ptr[:data_len])
	web_store_set(key, data)
}

@(export)
ar_web_store_hydrate_done :: proc "c" () {
	context = web_context_value
	web_store_hydrated = true
}

// ---------------------------------------------------------------------------
// Save worker: same API as the desktop thread worker, processed synchronously.
// Durability beyond the mirror is the asynchronous IndexedDB flush issued by
// the storage primitives above.

Save_Worker :: struct {
	completions: [dynamic]Save_Completion,
	ready:       bool,
}

save_worker_init :: proc(worker: ^Save_Worker) -> bool {
	if worker == nil do return false
	worker.completions = make([dynamic]Save_Completion, 0, 8)
	worker.ready = true
	return true
}

save_worker_enqueue :: proc(worker: ^Save_Worker, kind: Persistence_Document_Kind, path: string, data: []byte, revision: u64) -> bool {
	source_allocator := context.allocator
	if worker == nil || !worker.ready || len(data) == 0 {
		delete(data, source_allocator)
		return false
	}
	success := storage_write_document_durable(path, kind, data)
	delete(data, source_allocator)
	append(&worker.completions, Save_Completion{kind = kind, revision = revision, success = success})
	return true
}

save_worker_enqueue_run :: proc(
	worker: ^Save_Worker,
	path, run_id, written_at_utc: string,
	payload: ^Run_Save_Payload,
	revision: u64,
) -> bool {
	allocator := platform_save_allocator()
	defer {
		if payload != nil {
			run_save_payload_destroy(payload, allocator)
			free(payload, allocator)
		}
	}
	if worker == nil || !worker.ready || run_id == "" || payload == nil do return false
	encoded, encode_ok := persistence_encode_run_payload(payload, run_id, revision, written_at_utc)
	success := encode_ok && storage_write_document_durable(path, .Run, encoded)
	if encode_ok do delete(encoded)
	append(&worker.completions, Save_Completion{kind = .Run, revision = revision, success = success})
	return true
}

save_worker_shutdown :: proc(worker: ^Save_Worker) {
	if worker == nil || !worker.ready do return
	delete(worker.completions)
	worker^ = {}
}

save_worker_try_completion :: proc(worker: ^Save_Worker) -> (Save_Completion, bool) {
	if worker == nil || !worker.ready || len(worker.completions) == 0 do return {}, false
	completion := worker.completions[0]
	ordered_remove(&worker.completions, 0)
	return completion, true
}

persistence_drain_worker :: proc(coordinator: ^Persistence_Coordinator) -> bool {
	// Writes are synchronous into the mirror; nothing is in flight to drain.
	return coordinator != nil && coordinator.ready
}

// Best-effort lifecycle checkpoint: snapshot and write synchronously into the
// mirror and issue the asynchronous IndexedDB put. The browser may still tear
// the page down before the transaction commits; that limitation is documented
// rather than papered over.
persistence_flush_for_suspend :: proc(coordinator: ^Persistence_Coordinator, app: ^App) -> bool {
	if coordinator == nil || app == nil || !coordinator.ready || app.run.run_id == "" || app.run.terminal != .Active do return false
	app.run_dirty = true
	app.run_critical = true
	app.run_dirty_serial += 1
	persistence_poll_completions(coordinator, app)
	if !coordinator.run_write_in_flight && app.run_dirty {
		_ = persistence_enqueue_run(coordinator, app)
	}
	persistence_poll_completions(coordinator, app)
	return !coordinator.run_write_in_flight && !app.run_dirty
}

// ---------------------------------------------------------------------------
// Browser lifecycle bridge.

@(private = "file")
web_visibility_resume_pending: bool

web_consume_visibility_resume :: proc() -> bool {
	pending := web_visibility_resume_pending
	web_visibility_resume_pending = false
	return pending
}

@(export)
ar_web_set_visible :: proc "c" (visible: i32) {
	context = web_context_value
	if !web_context_ready do return
	if visible != 0 {
		web_visibility_resume_pending = true
		return
	}
	if web_runtime != nil && web_runtime.persistence.ready && platform_live_descent(&web_runtime.app) {
		flushed := persistence_flush_for_suspend(&web_runtime.persistence, &web_runtime.app)
		platform_log(fmt.tprintf("ARCH_ROGUE_SUSPEND_CHECKPOINT durable=%v revision=%d", flushed, web_runtime.app.run.revision))
	}
}

@(export)
ar_web_pagehide :: proc "c" () {
	ar_web_set_visible(0)
}

@(export)
ar_web_resize :: proc "c" (width, height: i32) {
	context = web_context_value
	if !web_context_ready || web_runtime == nil do return
	rl.SetWindowSize(max(width, 1), max(height, 1))
}

@(private = "file")
web_audio_unlock_pending: bool

// Deliberately deferred: creating the audio device synchronously inside the
// gesture callback tramples the GLFW keyboard hooks (miniaudio re-registers
// input listeners mid-dispatch) and leaves the keyboard dead. The gesture only
// arms a flag; game_frame initializes audio on the next requestAnimationFrame
// tick, which still holds the browser's transient user activation.
@(export)
ar_web_audio_unlock :: proc "c" () {
	context = web_context_value
	if !web_context_ready do return
	web_audio_unlock_pending = true
}

web_consume_audio_unlock :: proc() -> bool {
	pending := web_audio_unlock_pending
	web_audio_unlock_pending = false
	return pending
}

// ---------------------------------------------------------------------------
// Boot configuration from URL query parameters. This mirrors the desktop env
// contract for the deterministic profiling harness; ordinary players load with
// no parameters and defaults apply.

@(private = "file")
web_query_param :: proc(name: string, buffer: []u8) -> string {
	length := ar_js_query_param(raw_data(name), i32(len(name)), raw_data(buffer), i32(len(buffer)))
	if length <= 0 do return ""
	return string(buffer[:length])
}

@(private = "file")
web_boot_config :: proc() -> Game_Boot_Config {
	config := game_boot_config_default()
	config.window_width = max(int(ar_js_canvas_width()), 320)
	config.window_height = max(int(ar_js_canvas_height()), 240)
	config.seed = u64(ar_js_unix_ms()) * 1_000_003 + u64(emscripten_get_now() * 1000)
	buffer: [128]u8
	if value := web_query_param("seed", buffer[:]); value != "" {
		if parsed, ok := strconv.parse_u64(value); ok do config.seed = parsed
	}
	config.dev_play = web_query_param("play", buffer[:]) != ""
	if archetype, ok := dev_archetype_from_env(web_query_param("archetype", buffer[:])); ok {
		config.dev_archetype = archetype
		config.dev_archetype_valid = true
	}
	if value := web_query_param("depth", buffer[:]); value != "" {
		if parsed, ok := strconv.parse_int(value); ok do config.dev_depth = parsed
	}
	config.mx7_perf_enabled = web_query_param("mx7_perf", buffer[:]) != ""
	if value := web_query_param("perf_frames", buffer[:]); value != "" {
		if parsed, ok := strconv.parse_int(value); ok do config.perf_frames = max(1, parsed)
	}
	if value := web_query_param("perf_warmup", buffer[:]); value != "" {
		if parsed, ok := strconv.parse_int(value); ok do config.perf_warmup = max(0, parsed)
	}
	if value := web_query_param("theme", buffer[:]); value != "" {
		if parsed, ok := strconv.parse_int(value); ok do config.mx7_theme = parsed
	}
	if value := web_query_param("dark", buffer[:]); value != "" {
		if parsed, ok := strconv.parse_int(value); ok do config.mx7_dark = parsed
	}
	config.dev_reveal = web_query_param("reveal", buffer[:]) != ""
	return config
}

// ---------------------------------------------------------------------------
// Boot state machine driven from requestAnimationFrame; no ASYNCIFY anywhere.

@(private = "file")
Web_Boot_State :: enum u8 {
	Awaiting_Storage,
	Running,
	Stopped,
}

@(private = "file")
web_boot_state: Web_Boot_State

@(private = "file")
web_runtime: ^Game_Runtime

@(export)
ar_web_boot :: proc "c" () -> i32 {
	context = runtime.default_context()
	context.allocator = web_allocator()
	context.temp_allocator = web_temp_allocator()
	web_context_value = context
	web_context_ready = true
	#force_no_inline runtime._startup_runtime()
	web_store = make(map[string][]byte)
	web_pack_adoptions = make([dynamic]Web_Pack_Adoption_Job, 0, 3)
	ar_js_storage_hydrate()
	return 1
}

@(export)
ar_web_tick :: proc "c" () -> i32 {
	context = web_context_value
	switch web_boot_state {
	case .Awaiting_Storage:
		if !web_store_hydrated do return 1
		web_runtime = new(Game_Runtime)
		if !game_init(web_runtime, web_boot_config()) {
			message := "game_init failed"
			ar_js_boot_failed(raw_data(message), i32(len(message)))
			web_pack_adoptions_shutdown()
			free(web_runtime)
			web_runtime = nil
			web_boot_state = .Stopped
			return 0
		}
		web_boot_state = .Running
		ar_js_boot_complete()
		platform_log(fmt.tprintf(
			"ARCH_ROGUE_READY version=%s web=%dx%d assets=%d storage=%v",
			VERSION, rl.GetScreenWidth(), rl.GetScreenHeight(),
			assets_loaded_texture_count(&web_runtime.assets), web_runtime.persistence.ready,
		))
	case .Running:
		perf_active := web_runtime.perf_enabled && web_runtime.frame_count > web_runtime.config.perf_warmup
		busy_begin := perf_active ? emscripten_get_now() : 0
		keep_running := game_frame(web_runtime)
		if perf_active {
			append(&web_busy_samples, f32(emscripten_get_now() - busy_begin))
		}
		if !keep_running {
			web_report_perf_extras(web_runtime)
			web_pack_adoptions_shutdown()
			game_shutdown(web_runtime)
			free(web_runtime)
			web_runtime = nil
			web_boot_state = .Stopped
			ar_js_game_ended()
			return 0
		}
	case .Stopped:
		return 0
	}
	return 1
}

// ---------------------------------------------------------------------------
// Lazy asset packs: the JS bridge verifies and materializes one file per RAF.
// Successful callbacks transfer owned actor names into this queue; game_frame
// adopts at most one actor after SFX drain, and only while authored audio is
// quiet. Current packs contain at most five actors; keep the bridge bound at
// eight so malformed or future manifests cannot grow an unbounded callback.

@(private = "file")
WEB_PACK_ACTOR_CAP :: 8

@(private = "file")
Web_Pack_Status :: enum u8 {
	Absent,
	Fetching,
	Adopting,
	Resident,
	Failed,
}

@(private = "file")
Web_Pack_Adoption_Job :: struct {
	name:        string,
	actors:      [WEB_PACK_ACTOR_CAP]string,
	actor_count: int,
	next_actor:  int,
}

@(private = "file")
web_packs: map[string]Web_Pack_Status

@(private = "file")
web_pack_adoptions: [dynamic]Web_Pack_Adoption_Job

@(private = "file")
web_pack_set :: proc(name: string, status: Web_Pack_Status) {
	if existing, exists := &web_packs[name]; exists {
		existing^ = status
		return
	}
	web_packs[strings.clone(name)] = status
}

@(private = "file")
web_pack_adoption_job_destroy :: proc(job: ^Web_Pack_Adoption_Job) {
	if job == nil do return
	delete(job.name)
	for index in 0 ..< job.actor_count do delete(job.actors[index])
	job^ = {}
}

@(private = "file")
web_pack_adoptions_shutdown :: proc() {
	for &job in web_pack_adoptions do web_pack_adoption_job_destroy(&job)
	delete(web_pack_adoptions)
	web_pack_adoptions = nil
}

@(private = "file")
web_pack_request :: proc(name: string) {
	status := web_packs[name] or_else .Absent
	if status == .Fetching || status == .Adopting || status == .Resident do return
	web_pack_set(name, .Fetching)
	ar_js_pack_request(raw_data(name), i32(len(name)))
}

web_packs_on_run_start :: proc(archetype: Archetype_Id) {
	web_pack_request(fmt.tprintf("archetype-%s", ARCHETYPES[archetype].sprite))
	web_pack_request("social")
	web_pack_request("bosses")
}

web_pack_adoptions_tick :: proc(rt: ^Game_Runtime) {
	if rt == nil || len(web_pack_adoptions) == 0 || audio_any_cue_playing(&rt.audio) do return
	job := &web_pack_adoptions[0]
	if job.next_actor < job.actor_count {
		actor_index := job.next_actor
		app := &rt.app
		active_valid := app.run.run_id != "" || app.mode == .Playing || app.mode == .Resume_Veil
		assets_web_adopt_actors(
			&rt.assets,
			job.actors[actor_index:actor_index+1],
			app.run.player.archetype,
			active_valid,
		)
		job.next_actor += 1
	}
	if job.next_actor < job.actor_count do return

	web_pack_set(job.name, .Resident)
	platform_log(fmt.tprintf("ARCH_ROGUE_WEB_PACK resident name=%s actors=%d", job.name, job.actor_count))
	web_pack_adoption_job_destroy(job)
	ordered_remove(&web_pack_adoptions, 0)
}

@(export)
ar_web_pack_loaded :: proc "c" (name_ptr: [^]u8, name_len: i32, actors_ptr: [^]u8, actors_len: i32, ok: i32) {
	context = web_context_value
	if !web_context_ready || name_len <= 0 || web_boot_state != .Running || web_runtime == nil do return
	name := string(name_ptr[:name_len])
	if ok == 0 {
		web_pack_set(name, .Failed)
		platform_log(fmt.tprintf("ARCH_ROGUE_WEB_PACK failed name=%s", name))
		return
	}

	job := Web_Pack_Adoption_Job{name = strings.clone(name)}
	rest := actors_len > 0 ? string(actors_ptr[:actors_len]) : ""
	for len(rest) > 0 && job.actor_count < len(job.actors) {
		comma := strings.index_byte(rest, ',')
		if comma < 0 {
			job.actors[job.actor_count] = strings.clone(rest)
			job.actor_count += 1
			break
		}
		job.actors[job.actor_count] = strings.clone(rest[:comma])
		job.actor_count += 1
		rest = rest[comma+1:]
	}
	append(&web_pack_adoptions, job)
	web_pack_set(name, .Adopting)
	platform_log(fmt.tprintf("ARCH_ROGUE_WEB_PACK adopting name=%s actors=%d", name, job.actor_count))
}

// ---------------------------------------------------------------------------
// Harness instrumentation: a state probe for the browser smoke tests plus
// per-frame main-thread busy time and dynamic-heap measurement recorded
// against the pinned Emscripten heap by the profiling harness.

@(private = "file")
@(default_calling_convention = "c")
foreign {
	sbrk :: proc(increment: i32) -> rawptr ---
	@(link_name = "__heap_base")
	web_heap_base: u8
}

@(private = "file")
web_dynamic_heap_bytes :: proc() -> int {
	top := uintptr(sbrk(0))
	base := uintptr(&web_heap_base)
	if top <= base do return 0
	return int(top - base)
}

@(private = "file")
web_busy_samples: [dynamic]f32

@(private = "file")
web_probe_buffer: [1024]u8

@(export)
ar_web_smoke_probe :: proc "c" () -> [^]u8 {
	context = web_context_value
	mode := "boot"
	audio_ready := false
	audio_playing := false
	storage_ready := false
	resume_available := false
	run_active := false
	modal_open := false
	depth := 0
	frame_count := 0
	gamepad := false
	packs_resident := 0
	packs_adopting := 0
	if web_runtime != nil {
		mode = fmt.tprintf("%v", web_runtime.app.mode)
		audio_ready = web_runtime.audio.ready
		audio_playing = audio_any_cue_playing(&web_runtime.audio)
		storage_ready = web_runtime.persistence.ready
		resume_available = web_runtime.app.active_run_available
		run_active = web_runtime.app.run.run_id != ""
		modal_open = app_play_modal_open(&web_runtime.app)
		depth = web_runtime.app.run.depth
		frame_count = web_runtime.frame_count
		gamepad = bool(rl.IsGamepadAvailable(0))
	}
	for _, status in web_packs {
		if status == .Resident do packs_resident += 1
		if status == .Adopting do packs_adopting += 1
	}
	encoded := fmt.bprintf(
		web_probe_buffer[:len(web_probe_buffer)-1],
		"{{\"state\":\"%v\",\"mode\":\"%s\",\"audio_ready\":%v,\"audio_playing\":%v,\"storage_ready\":%v,\"resume_available\":%v,\"run_active\":%v,\"modal_open\":%v,\"depth\":%d,\"frame_count\":%d,\"gamepad\":%v,\"packs_resident\":%d,\"packs_adopting\":%d,\"screen_w\":%d,\"screen_h\":%d,\"heap_dynamic_bytes\":%d,\"hydrated\":%v}}",
		web_boot_state, mode, audio_ready, audio_playing, storage_ready, resume_available, run_active,
		modal_open, depth, frame_count, gamepad, packs_resident, packs_adopting,
		int(rl.GetScreenWidth()), int(rl.GetScreenHeight()),
		web_dynamic_heap_bytes(), web_store_hydrated,
	)
	web_probe_buffer[len(encoded)] = 0
	return raw_data(web_probe_buffer[:])
}

@(private = "file")
web_report_perf_extras :: proc(rt: ^Game_Runtime) {
	if len(web_busy_samples) == 0 do return
	for i in 1 ..< len(web_busy_samples) {
		value := web_busy_samples[i]
		j := i
		for j > 0 && web_busy_samples[j-1] > value {
			web_busy_samples[j] = web_busy_samples[j-1]
			j -= 1
		}
		web_busy_samples[j] = value
	}
	total: f32
	for sample in web_busy_samples do total += sample
	mean := total / f32(len(web_busy_samples))
	p95 := mx7_perf_percentile(web_busy_samples[:], .95)
	p99 := mx7_perf_percentile(web_busy_samples[:], .99)
	max_ms := web_busy_samples[len(web_busy_samples)-1]
	platform_report_line(fmt.tprintf(
		"MX_WEB_PERF {{\"busy_frames\":%d,\"busy_mean_ms\":%.3f,\"busy_p95_ms\":%.3f,\"busy_p99_ms\":%.3f,\"busy_max_ms\":%.3f,\"heap_dynamic_bytes\":%d,\"heap_initial_bytes\":%d,\"temp_arena_high_mark\":%d}}",
		len(web_busy_samples), mean, p95, p99, max_ms,
		web_dynamic_heap_bytes(), 268435456, web_temp_arena.high_mark,
	))
}
