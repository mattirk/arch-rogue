#+build !freestanding
package archrogue

// Steamworks facade (STEAM.md S1): a thin runtime binding over the flat C API,
// loaded with core:dynlib so one binary serves every distribution. With the
// library and a running client it initializes; absent either, the game behaves
// identically to a build with no Steam code. All Steamworks traffic happens on
// the main thread's frame pump; the save worker and the simulation never touch
// this file. Android compiles the same file but every entry point no-ops.
//
// The exact surface mirrors the archived pygame facade
// (arch-rogue-python/src/arch_rogue/steam.py): init (InitFlat preferred),
// shutdown, per-frame RunCallbacks, RestartAppIfNecessary (DRM-free stance,
// kept), ISteamUserStats achievements/stats with batched StoreStats, and a
// durable offline unlock queue replayed on the next connected session.
// Version-suffixed accessors are probed newest-first from a data table so an
// SDK bump degrades loudly (status names the failing step), never silently.

import "core:dynlib"
import "core:encoding/json"
import "core:fmt"
import "core:os"
import filepath "core:path/filepath"
import "core:strconv"
import "core:strings"

// The shipped binary needs the App ID at runtime for RestartAppIfNecessary and
// init; deployment configuration cannot supply it. Pinned by a test so a debug
// edit cannot reach a depot. Override per-run with ARCH_ROGUE_STEAM_APPID.
STEAM_APP_ID :: 5031380

STEAM_QUEUE_FILE_NAME :: "steam_queue.json"
STEAM_QUEUE_SCHEMA_VERSION :: 1
STEAM_QUEUE_MAX_BYTES :: 64 * 1024
STEAM_QUEUE_MAX_ENTRIES :: 256
STEAM_RETRY_FRAMES :: 300 // ~5 s at 60 fps between failed replay attempts

Steam_Status :: enum u8 {
	Inactive,        // startup not attempted (or Android)
	Disabled_Env,    // ARCH_ROGUE_NO_STEAM=1
	Library_Missing, // no steam_api shared library found
	Symbols_Missing, // library present, a required flat-API symbol absent
	Init_Failed,     // SteamAPI init returned failure (client not running, ...)
	Interface_Missing, // init succeeded but no ISteamUserStats accessor bound
	Ready,
}

Steam_Symbol_Resolver :: #type proc(user: rawptr, name: string) -> rawptr

Steam_Api :: struct {
	init_flat:      proc "c" (err: ^[1024]u8) -> i32,
	init_legacy:    proc "c" () -> bool,
	shutdown:       proc "c" (),
	run_callbacks:  proc "c" (),
	restart_app:    proc "c" (app_id: u32) -> bool,
	user_stats:     proc "c" () -> rawptr,
	friends:        proc "c" () -> rawptr,
	set_achievement:proc "c" (self: rawptr, name: cstring) -> bool,
	get_achievement:proc "c" (self: rawptr, name: cstring, achieved: ^bool) -> bool,
	store_stats:    proc "c" (self: rawptr) -> bool,
	set_stat_i32:   proc "c" (self: rawptr, name: cstring, value: i32) -> bool,
	request_current_stats: proc "c" (self: rawptr) -> bool, // absent in SDK >= 1.61 (auto-requested)
	set_rich_presence: proc "c" (self: rawptr, key: cstring, value: cstring) -> bool,
}

Steam_Queue_Entry :: struct {
	kind:  string, // "achievement" | "stat"
	id:    string,
	value: i64,
}

Steam_Queue_File :: struct {
	schema_version: int,
	entries:        [dynamic]Steam_Queue_Entry,
}

Steam_State :: struct {
	status:          Steam_Status,
	failing_symbol:  string, // static probe-table name; never freed
	app_id:          u32,
	lib:             dynlib.Library,
	api:             Steam_Api,
	user_stats:      rawptr,
	friends:         rawptr,
	queue_path:      string, // allocator-owned
	queue:           [dynamic]Steam_Queue_Entry, // entry strings allocator-owned
	store_pending:   bool,
	reconciled:      bool,
	retry_frames:    int,
	status_logged:   bool,
}

// Newest-first accessor probe tables (SDK 1.60-era names). An SDK bump extends
// these; a full miss surfaces as Interface_Missing rather than a silent no-op.
@(rodata)
STEAM_USER_STATS_ACCESSORS := [3]string{
	"SteamAPI_SteamUserStats_v013",
	"SteamAPI_SteamUserStats_v012",
	"SteamAPI_SteamUserStats_v011",
}

@(rodata)
STEAM_FRIENDS_ACCESSORS := [2]string{
	"SteamAPI_SteamFriends_v018",
	"SteamAPI_SteamFriends_v017",
}

steam_library_names :: proc() -> []string {
	when ODIN_OS == .Windows {
		@(static, rodata) names := [1]string{"steam_api64.dll"}
	} else when ODIN_OS == .Darwin {
		@(static, rodata) names := [1]string{"libsteam_api.dylib"}
	} else {
		@(static, rodata) names := [1]string{"libsteam_api.so"}
	}
	return names[:]
}

// Search order: beside the executable, the working directory, then the
// build/steam/sdk dev drop the pygame plan established.
@(private = "file")
steam_load_library :: proc(state: ^Steam_State) -> bool {
	for name in steam_library_names() {
		candidates: [3]string
		count := 0
		exe_dir := len(os.args) > 0 ? filepath.dir(os.args[0]) : ""
		defer delete(exe_dir)
		if exe_dir != "" {
			if joined, err := filepath.join([]string{exe_dir, name}, context.temp_allocator); err == nil {
				candidates[count] = joined; count += 1
			}
		}
		candidates[count] = name; count += 1
		if joined, err := filepath.join([]string{"build", "steam", "sdk", name}, context.temp_allocator); err == nil {
			candidates[count] = joined; count += 1
		}
		for i in 0 ..< count {
			if !os.exists(candidates[i]) && !strings.contains(candidates[i], "/") && !strings.contains(candidates[i], "\\") {
				// bare name: let the loader search system paths
			} else if !os.exists(candidates[i]) {
				continue
			}
			if lib, ok := dynlib.load_library(candidates[i], global_symbols=false); ok {
				state.lib = lib
				return true
			}
		}
	}
	return false
}

@(private = "file")
steam_dynlib_resolver :: proc(user: rawptr, name: string) -> rawptr {
	state := (^Steam_State)(user)
	if state == nil do return nil
	address, found := dynlib.symbol_address(state.lib, name)
	if !found do return nil
	return address
}

@(private = "file")
steam_probe :: proc(resolver: Steam_Symbol_Resolver, user: rawptr, names: []string) -> rawptr {
	for name in names {
		if address := resolver(user, name); address != nil do return address
	}
	return nil
}

// Bind the flat-API surface through an injectable resolver (tests supply a
// fake symbol table). Returns false with status/failing_symbol set when a
// required symbol is missing; optional symbols may stay nil.
steam_bind :: proc(state: ^Steam_State, resolver: Steam_Symbol_Resolver, user: rawptr) -> bool {
	if state == nil || resolver == nil do return false
	require :: proc(state: ^Steam_State, resolver: Steam_Symbol_Resolver, user: rawptr, name: string) -> rawptr {
		address := resolver(user, name)
		if address == nil && state.failing_symbol == "" {
			state.failing_symbol = name
		}
		return address
	}
	state.failing_symbol = ""
	state.api.init_flat = cast(proc "c" (^[1024]u8) -> i32)(resolver(user, "SteamAPI_InitFlat"))
	state.api.init_legacy = cast(proc "c" () -> bool)(resolver(user, "SteamAPI_Init"))
	if state.api.init_flat == nil && state.api.init_legacy == nil && state.failing_symbol == "" {
		state.failing_symbol = "SteamAPI_InitFlat"
	}
	state.api.shutdown = cast(proc "c" ())(require(state, resolver, user, "SteamAPI_Shutdown"))
	state.api.run_callbacks = cast(proc "c" ())(require(state, resolver, user, "SteamAPI_RunCallbacks"))
	state.api.restart_app = cast(proc "c" (u32) -> bool)(resolver(user, "SteamAPI_RestartAppIfNecessary"))
	state.api.set_achievement = cast(proc "c" (rawptr, cstring) -> bool)(require(state, resolver, user, "SteamAPI_ISteamUserStats_SetAchievement"))
	state.api.get_achievement = cast(proc "c" (rawptr, cstring, ^bool) -> bool)(require(state, resolver, user, "SteamAPI_ISteamUserStats_GetAchievement"))
	state.api.store_stats = cast(proc "c" (rawptr) -> bool)(require(state, resolver, user, "SteamAPI_ISteamUserStats_StoreStats"))
	state.api.set_stat_i32 = cast(proc "c" (rawptr, cstring, i32) -> bool)(require(state, resolver, user, "SteamAPI_ISteamUserStats_SetStatInt32"))
	state.api.request_current_stats = cast(proc "c" (rawptr) -> bool)(resolver(user, "SteamAPI_ISteamUserStats_RequestCurrentStats"))
	state.api.set_rich_presence = cast(proc "c" (rawptr, cstring, cstring) -> bool)(resolver(user, "SteamAPI_ISteamFriends_SetRichPresence"))
	state.api.user_stats = cast(proc "c" () -> rawptr)(steam_probe(resolver, user, STEAM_USER_STATS_ACCESSORS[:]))
	state.api.friends = cast(proc "c" () -> rawptr)(steam_probe(resolver, user, STEAM_FRIENDS_ACCESSORS[:]))
	if state.api.user_stats == nil && state.failing_symbol == "" {
		state.failing_symbol = STEAM_USER_STATS_ACCESSORS[0]
	}
	if (state.api.init_flat == nil && state.api.init_legacy == nil) ||
		state.api.shutdown == nil || state.api.run_callbacks == nil ||
		state.api.set_achievement == nil || state.api.get_achievement == nil ||
		state.api.store_stats == nil || state.api.set_stat_i32 == nil ||
		state.api.user_stats == nil {
		state.status = .Symbols_Missing
		return false
	}
	return true
}

// Init through the bound API and resolve interfaces. Split from steam_startup
// so tests can drive it against an injected fake table.
steam_initialize :: proc(state: ^Steam_State) -> (request_quit: bool) {
	if state == nil do return false
	if state.api.restart_app != nil && state.api.restart_app(state.app_id) {
		// Valve contract: a bare download relaunches through Steam; quit now.
		state.status = .Inactive
		return true
	}
	initialized := false
	if state.api.init_flat != nil {
		err_msg: [1024]u8
		initialized = state.api.init_flat(&err_msg) == 0
	} else if state.api.init_legacy != nil {
		initialized = state.api.init_legacy()
	}
	if !initialized {
		state.status = .Init_Failed
		return false
	}
	state.user_stats = state.api.user_stats()
	if state.api.friends != nil do state.friends = state.api.friends()
	if state.user_stats == nil {
		state.status = .Interface_Missing
		return false
	}
	if state.api.request_current_stats != nil {
		_ = state.api.request_current_stats(state.user_stats)
	}
	state.status = .Ready
	return false
}

steam_env_disabled :: proc() -> bool {
	value := os.get_env("ARCH_ROGUE_NO_STEAM", context.temp_allocator)
	return value == "1" || value == "true"
}

steam_env_app_id :: proc() -> u32 {
	value := os.get_env("ARCH_ROGUE_STEAM_APPID", context.temp_allocator)
	if value != "" {
		if parsed, ok := strconv.parse_u64(value); ok && parsed > 0 && parsed <= u64(max(u32)) {
			return u32(parsed)
		}
	}
	return STEAM_APP_ID
}

// Full desktop startup: env contract, library load, bind, restart check, init,
// and queue attach. Returns true when the process must exit so Steam can
// relaunch it. Safe to call when Steam is absent: the state simply records why
// it is inactive and every later call no-ops.
steam_startup :: proc(state: ^Steam_State, storage_dir: string) -> (request_quit: bool) {
	if state == nil do return false
	when ARCH_ROGUE_ANDROID {
		state.status = .Inactive
		return false
	} else {
		state.app_id = steam_env_app_id()
		steam_attach_queue(state, storage_dir)
		if steam_env_disabled() {
			state.status = .Disabled_Env
			return false
		}
		if !steam_load_library(state) {
			state.status = .Library_Missing
			return false
		}
		if !steam_bind(state, steam_dynlib_resolver, state) do return false
		return steam_initialize(state)
	}
}

steam_shutdown :: proc(state: ^Steam_State) {
	if state == nil do return
	if state.status == .Ready && state.api.shutdown != nil do state.api.shutdown()
	if state.lib != nil do _ = dynlib.unload_library(state.lib)
	steam_queue_destroy(state)
	delete(state.queue_path)
	state^ = {}
}

steam_status_line :: proc(state: ^Steam_State) -> string {
	if state == nil do return ""
	switch state.status {
	case .Inactive:        return "steam: inactive"
	case .Disabled_Env:    return "steam: disabled by ARCH_ROGUE_NO_STEAM"
	case .Library_Missing: return "steam: library not found (running without Steam)"
	case .Symbols_Missing: return fmt.tprintf("steam: missing symbol %s", state.failing_symbol)
	case .Init_Failed:     return "steam: SteamAPI init failed (client not running?)"
	case .Interface_Missing: return "steam: no ISteamUserStats accessor"
	case .Ready:           return fmt.tprintf("steam: initialised for app %d", state.app_id)
	}
	return ""
}

// --- Offline queue -----------------------------------------------------------
// Durable fast path for unlocks decided while Steam is unreachable. The
// granted cache in profile.json fronts Steam; reconciliation on the next Ready
// session re-pushes anything cached but never confirmed, so a lost queue file
// degrades to a slower path, never a lost unlock.

steam_queue_destroy :: proc(state: ^Steam_State) {
	if state == nil do return
	for &entry in state.queue {
		delete(entry.kind)
		delete(entry.id)
	}
	delete(state.queue)
	state.queue = nil
}

steam_attach_queue :: proc(state: ^Steam_State, storage_dir: string) {
	if state == nil || storage_dir == "" do return
	joined, err := filepath.join([]string{storage_dir, STEAM_QUEUE_FILE_NAME}, context.allocator)
	if err != nil do return
	delete(state.queue_path)
	state.queue_path = joined
	steam_queue_destroy(state)
	state.queue = make([dynamic]Steam_Queue_Entry, 0, 8)
	data, status := storage_read_bounded(state.queue_path, STEAM_QUEUE_MAX_BYTES)
	defer delete(data)
	if status != .Valid do return
	file: Steam_Queue_File
	if err2 := json.unmarshal(data, &file); err2 != nil do return
	defer delete(file.entries)
	if file.schema_version != STEAM_QUEUE_SCHEMA_VERSION {
		for &entry in file.entries {delete(entry.kind);delete(entry.id)}
		return
	}
	for &entry in file.entries {
		if (entry.kind == "achievement" || entry.kind == "stat") && entry.id != "" &&
			len(state.queue) < STEAM_QUEUE_MAX_ENTRIES {
			append(&state.queue, entry)
			entry = {}
		} else {
			delete(entry.kind)
			delete(entry.id)
		}
	}
}

steam_queue_write :: proc(state: ^Steam_State) -> bool {
	if state == nil || state.queue_path == "" do return false
	file := Steam_Queue_File{schema_version=STEAM_QUEUE_SCHEMA_VERSION, entries=state.queue}
	data, ok := persistence_marshal(file)
	if !ok do return false
	defer delete(data)
	tmp := storage_artifact_path(state.queue_path, "tmp")
	defer delete(tmp)
	_ = storage_remove_file(tmp)
	if !storage_write_synced(tmp, data) do return false
	if !storage_replace_write_through(tmp, state.queue_path) do return false
	return storage_sync_parent(state.queue_path)
}

// Durably queue one achievement unlock. Callers mark the profile's granted
// cache only after this succeeds, so a failed write re-evaluates later
// instead of losing the unlock (the pygame ordering, kept).
steam_queue_achievement :: proc(state: ^Steam_State, api_id: string) -> bool {
	if state == nil || api_id == "" || state.queue_path == "" do return false
	if len(state.queue) >= STEAM_QUEUE_MAX_ENTRIES do return false
	for entry in state.queue {
		if entry.kind == "achievement" && entry.id == api_id do return true
	}
	append(&state.queue, Steam_Queue_Entry{kind=strings.clone("achievement"), id=strings.clone(api_id)})
	return steam_queue_write(state)
}

// Stats are recomputed from the profile, so they queue non-durably: a lost
// stat write is republished on the next session anyway.
steam_publish_stats :: proc(state: ^Steam_State, profile: ^Profile_State) {
	if state == nil || profile == nil || state.status != .Ready do return
	for name in ACHIEVEMENT_STAT_NAMES {
		value, ok := achievement_stat_value(profile, name)
		if !ok do continue
		cname := strings.clone_to_cstring(name, context.temp_allocator)
		if state.api.set_stat_i32(state.user_stats, cname, value) do state.store_pending = true
	}
}

@(private = "file")
steam_reconcile_granted :: proc(state: ^Steam_State, profile: ^Profile_State) {
	if state == nil || profile == nil || state.status != .Ready || state.reconciled do return
	state.reconciled = true
	for i in 0 ..< clamp(profile.granted_achievement_count, 0, len(profile.granted_achievement_ids)) {
		api_id := profile.granted_achievement_ids[i]
		if api_id == "" do continue
		cname := strings.clone_to_cstring(api_id, context.temp_allocator)
		achieved := false
		if state.api.get_achievement(state.user_stats, cname, &achieved) && !achieved {
			if state.api.set_achievement(state.user_stats, cname) do state.store_pending = true
		}
	}
	steam_publish_stats(state, profile)
}

@(private = "file")
steam_drain_queue :: proc(state: ^Steam_State) {
	if state == nil || state.status != .Ready || len(state.queue) == 0 do return
	if state.retry_frames > 0 {
		state.retry_frames -= 1
		return
	}
	applied := 0
	for applied < len(state.queue) {
		entry := &state.queue[applied]
		cname := strings.clone_to_cstring(entry.id, context.temp_allocator)
		ok := false
		switch entry.kind {
		case "achievement":
			ok = state.api.set_achievement(state.user_stats, cname)
		case "stat":
			ok = state.api.set_stat_i32(state.user_stats, cname, i32(entry.value))
		}
		if !ok {
			state.retry_frames = STEAM_RETRY_FRAMES
			break
		}
		state.store_pending = true
		applied += 1
	}
	if applied == 0 do return
	// Entries dequeue only after StoreStats accepts the batch; a crash between
	// SetAchievement and the store re-applies from the queue (idempotent).
	if state.api.store_stats(state.user_stats) {
		state.store_pending = false
		for i in 0 ..< applied {
			delete(state.queue[i].kind)
			delete(state.queue[i].id)
		}
		remove_range(&state.queue, 0, applied)
		_ = steam_queue_write(state)
	} else {
		state.retry_frames = STEAM_RETRY_FRAMES
	}
}

// Per-frame pump from the desktop loop: callbacks, one-time reconciliation,
// queue replay, and the batched StoreStats. Never called from the simulation
// or the save worker.
steam_frame :: proc(state: ^Steam_State, profile: ^Profile_State) {
	if state == nil do return
	when ARCH_ROGUE_ANDROID {
		return
	} else {
		if !state.status_logged && state.status != .Inactive {
			state.status_logged = true
			platform_log(steam_status_line(state))
		}
		if state.status != .Ready do return
		state.api.run_callbacks()
		steam_reconcile_granted(state, profile)
		steam_drain_queue(state)
		if state.store_pending && len(state.queue) == 0 && state.retry_frames <= 0 {
			if state.api.store_stats(state.user_stats) do state.store_pending = false
			else do state.retry_frames = STEAM_RETRY_FRAMES
		}
	}
}
