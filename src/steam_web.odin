#+build freestanding
package archrogue

// Web stub for the Steamworks facade: the browser build has no Steam surface,
// so the shared call sites in main.odin compile against these no-ops.

Steam_Status :: enum u8 {
	Inactive,
	Disabled_Env,
	Library_Missing,
	Symbols_Missing,
	Init_Failed,
	Interface_Missing,
	Ready,
}

Steam_State :: struct {
	status: Steam_Status,
}

steam_startup :: proc(state: ^Steam_State, storage_dir: string) -> (request_quit: bool) {
	if state != nil do state.status = .Inactive
	return false
}

steam_shutdown :: proc(state: ^Steam_State) {
	if state != nil do state^ = {}
}

steam_frame :: proc(state: ^Steam_State, profile: ^Profile_State) {
}

steam_queue_achievement :: proc(state: ^Steam_State, api_id: string) -> bool {
	return false
}

steam_publish_stats :: proc(state: ^Steam_State, profile: ^Profile_State) {
}
