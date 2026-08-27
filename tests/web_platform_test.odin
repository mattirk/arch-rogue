package archrogue_tests

// MX-web — headless contracts for the platform-neutral pieces the web target
// leans on: boot-config defaults shared by every entry point, the capture
// parsers that back both desktop env toggles and web query parameters, the
// storage artifact naming reused as IndexedDB keys, and the fixed-step
// clamp/discard behavior the browser tab-return path depends on.

import "core:os"
import "core:strings"
import "core:testing"
import ar "../src"

@(test)
mx_web_boot_config_defaults_match_the_platform_contract :: proc(t: ^testing.T) {
	config := ar.game_boot_config_default()
	testing.expect(t, config.window_width == 1280 && config.window_height == 720, "default canvas is 1280x720")
	testing.expect(t, config.shot_frame == 40, "screenshot harness defaults to frame 40")
	testing.expect(t, config.mx7_theme == -1 && config.mx7_dark == -1, "theme/dark overrides default to unset")
	testing.expect(t, config.dev_lighting == -1, "lighting override defaults to unset")
	testing.expect(t, config.perf_warmup == 120 && config.perf_frames == 600, "perf windows default to 120/600")
	testing.expect(t, config.capture_direction == ar.Vec2{1, 1}, "capture direction defaults to south")
	testing.expect(t, !config.dev_play && !config.mx7_perf_enabled && !config.mx_save_perf_enabled, "dev/perf modes default off")
	testing.expect(t, config.seed == 0 && config.shot_path == "", "seed and shot path are caller-provided")
}

@(test)
mx_web_capture_parsers_accept_the_documented_vocabulary :: proc(t: ^testing.T) {
	testing.expect(t, ar.mx7_capture_scenario_from_env("crowd") == .Crowd, "mx7 crowd scenario parses")
	testing.expect(t, ar.mx7_capture_scenario_from_env("nonsense") == .None, "unknown mx7 scenario is inert")
	testing.expect(t, ar.mx6_capture_scenario_from_env("boss_cast") == .Boss_Cast, "mx6 boss_cast parses")
	testing.expect(t, ar.mx6_capture_scenario_from_env("miniboss") == .Miniboss, "mx6 miniboss parses")
	testing.expect(t, ar.mx_story_capture_scenario_from_env("relic_choices") == .Relic_Choices, "story scenario parses")
	testing.expect(t, ar.mx_save_capture_scenario_from_env("recovery") == .Recovery, "save scenario parses")
	direction, ok := ar.mx6_capture_direction_from_env("north-west")
	testing.expect(t, ok && direction == ar.Vec2{-1, 0}, "direction names map to tile-space vectors")
	archetype, archetype_ok := ar.dev_archetype_from_env("arcanist")
	testing.expect(t, archetype_ok && archetype == .Arcanist, "archetype names parse")
	index_archetype, index_ok := ar.dev_archetype_from_env("4")
	testing.expect(t, index_ok && index_archetype == .Ranger, "archetype ordinals parse")
	_, bad_ok := ar.dev_archetype_from_env("paladin")
	testing.expect(t, !bad_ok, "unknown archetype is rejected")
}

@(test)
mx_web_storage_artifact_names_stay_stable_for_indexeddb_keys :: proc(t: ^testing.T) {
	// The web backend stores these exact strings as IndexedDB keys; the
	// tmp/bak artifact scheme is what makes desktop recovery logic reusable.
	tmp := ar.storage_artifact_path("/save/run.json", "tmp")
	defer delete(tmp)
	bak := ar.storage_artifact_path("/save/run.json", "bak")
	defer delete(bak)
	testing.expect(t, tmp == "/save/run.json.tmp", "tmp artifact naming is stable")
	testing.expect(t, bak == "/save/run.json.bak", "bak artifact naming is stable")
	testing.expect(t, ar.storage_max_bytes(.Options) == ar.PERSISTENCE_OPTIONS_MAX_BYTES, "options cap mapping")
	testing.expect(t, ar.storage_max_bytes(.Profile) == ar.PERSISTENCE_PROFILE_MAX_BYTES, "profile cap mapping")
	testing.expect(t, ar.storage_max_bytes(.Run) == ar.PERSISTENCE_RUN_MAX_BYTES, "run cap mapping")
}

@(test)
mx_web_lazy_pack_source_contract_carries_actors_and_sfx :: proc(t: ^testing.T) {
	packer, packer_err := os.read_entire_file_from_path("tools/web_pack_assets.py", context.allocator)
	testing.expect(t, packer_err == nil, "web packer source is missing")
	if packer_err == nil {
		defer delete(packer)
		text := string(packer)
		testing.expect(t, strings.contains(text, "\"schema\": 2"), "ARPACK manifest schema must remain 2")
		testing.expect(t, strings.contains(text, "\"sfx-world\""), "remaining semantic SFX need a world pack")
		testing.expect(t, strings.contains(text, "\"sfx_banks\""), "pack metadata must carry SFX bank names")
		testing.expect(t, strings.contains(text, "\"core_sfx_banks\""), "manifest must identify staged banks that receive upgrades")
		testing.expect(t, strings.contains(text, "sorted((known - assigned) | CORE_SFX_BANKS)"), "sfx-world must upgrade every core bank")
		testing.expect(t, strings.contains(text, "if path != staged_core_sfx.get(bank)"), "packs must exclude each staged core path")
		testing.expect(t, strings.contains(text, "if path in packed_sfx_files"), "core staging must exclude lazy SFX WAVs")
		testing.expect(t, strings.contains(text, "\"soulless_clanker\"") && strings.contains(text, "\"string\""),
			"social actor pack must carry recruited room companions")
		testing.expect(t, strings.contains(text, "\"mistbound_ghost\""),
			"social actor pack must carry the Mistbound Chamber ghost")
	}

	web_entry, web_entry_err := os.read_entire_file_from_path("src/main_web.odin", context.allocator)
	testing.expect(t, web_entry_err == nil, "web entry source is missing")
	if web_entry_err == nil {
		defer delete(web_entry)
		text := string(web_entry)
		testing.expect(t, strings.contains(text, "WEB_PACK_ACTOR_CAP :: 12"),
			"web actor adoption capacity must retain headroom for the expanded social pack")
	}

	bridge, bridge_err := os.read_entire_file_from_path("web/library_archrogue.js", context.allocator)
	testing.expect(t, bridge_err == nil, "web pack bridge source is missing")
	if bridge_err == nil {
		defer delete(bridge)
		text := string(bridge)
		testing.expect(t, strings.contains(text, "materializeNextPackFile"), "pack files must retain RAF materialization")
		testing.expect(t, strings.contains(text, "(info.sfx_banks || []).join(',')"), "bridge must forward SFX-bank metadata")
		testing.expect(t, strings.contains(text, "sfxPointer, sfxBytes"), "wasm callback must receive SFX-bank CSV")
	}
}

@(test)
mx_web_tab_return_discards_the_hidden_gap_and_clamps_catchup :: proc(t: ^testing.T) {
	// requestAnimationFrame stops while a tab is hidden. On return the web
	// entry calls mobile_fixed_step_reset(discard_next_dt=true); the first
	// frame's huge dt must be discarded entirely, and any later spike must
	// clamp at max_frame_dt rather than catch-up spiraling.
	state: ar.Mobile_Fixed_Step_State
	steps := ar.mobile_fixed_step_advance(&state, 0.016, 0.01, 0.25, true)
	testing.expect(t, steps == 1, "steady frame advances one step")

	ar.mobile_fixed_step_reset(&state, discard_next_dt = true)
	steps = ar.mobile_fixed_step_advance(&state, 45.0, 0.01, 0.25, true)
	testing.expect(t, steps == 0, "the first frame after tab return is discarded")
	testing.expectf(t, state.accumulator == 0, "no hidden-tab time is retained, got %v", state.accumulator)

	steps = ar.mobile_fixed_step_advance(&state, 5.0, 0.01, 0.25, true)
	testing.expect(t, steps <= 25, "a later spike clamps at max_frame_dt worth of steps")
}
