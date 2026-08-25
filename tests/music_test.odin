package archrogue_tests

// Headless music-model tests per SOUND.md: the composer document, the
// screen -> mix selector, and the director's boot intro, alternate cycles,
// phase-locked crossfades, and the pure music-master DSP. Device playback stays
// in the real-device soak and web smoke harnesses.

import "core:os"
import "core:fmt"
import "core:testing"
import ar "../src"

@(test)
music_mixes_document_parses_and_references_real_files :: proc(t: ^testing.T) {
	data, read_err := os.read_entire_file_from_path(ar.MUSIC_MIXES_DOCUMENT_PATH, context.allocator)
	if read_err != nil {
		testing.expect(t, false, "assets/audio/bgm/mixes.json missing")
		return
	}
	defer delete(data)
	library, ok := ar.music_library_parse(data)
	defer ar.music_library_destroy(&library)
	testing.expect(t, ok && library.loaded, "mixes.json must parse")
	testing.expect(t, library.loop_ms == 19200, "loop_ms must match the authored 19200")
	testing.expect(t, library.crossfade_ms == 1000, "the document default crossfade must be 1 second")
	testing.expect(t, library.has_boot && library.boot.mix == "menu_boot", "boot must arm the menu_boot intro")
	testing.expect(t, abs(library.boot.length_scale - 0.5) < 1e-5, "boot intro must run at 50% length")

	menu := ar.music_library_mix(&library, "menu")
	if menu == nil {
		testing.expect(t, false, "menu mix must exist")
		return
	}
	testing.expect(t, len(menu.tracks) == 3, "menu must keep all three authored stems independently controllable")
	if len(menu.tracks) == 3 {
		testing.expect(t, menu.tracks[0].file == "ambience_grim_bass.ogg", "menu must include the grim bass stem")
		testing.expect(t, menu.tracks[1].file == "ambience_strings.ogg", "menu strings must remain independent")
		testing.expect(t, menu.tracks[2].file == "beat_low.ogg", "menu must include the low beat stem")
	}
	strings_alternate := false
	for track in menu.tracks {
		if track.file == "ambience_strings.ogg" do strings_alternate = track.alternate
	}
	testing.expect(t, strings_alternate, "ambience_strings must alternate per Loop cycle")

	dungeon := ar.music_library_mix(&library, "dungeon")
	if dungeon == nil {
		testing.expect(t, false, "dungeon mix must exist")
		return
	}
	testing.expect(t, dungeon.crossfade_ms == 1000, "transitions into dungeon must crossfade for 1 second")
	testing.expect(t, len(dungeon.tracks) == 9, "dungeon must expose all nine live stems")
	if len(dungeon.tracks) == 9 {
		testing.expect(t, dungeon.tracks[0].file == "ambience_grim_bass.ogg" && dungeon.tracks[0].condition == .Always,
			"dungeon grim bass must remain outside spatial-room ducking")
		testing.expect(t, dungeon.tracks[1].file == "beat_low.ogg" && dungeon.tracks[1].condition == .Always,
			"dungeon low beat must remain outside spatial-room ducking")
		testing.expect(t,
			dungeon.tracks[2].file == "lead_harp.ogg" && dungeon.tracks[2].condition == .Dungeon_Default_Music &&
			dungeon.tracks[2].alternate,
			"the original dungeon harp must alternate within the default spatial stem group",
		)
		testing.expect(t,
			dungeon.tracks[3].file == "lead_harp_two.ogg" && dungeon.tracks[3].condition == .Dungeon_Quest_Music,
			"the second harp must use the Quest proximity stem group",
		)
		testing.expect(t, dungeon.tracks[4].file == "lead_pad.ogg" && dungeon.tracks[4].condition == .Dungeon_Default_Music,
			"the dungeon pad must use the default spatial stem group")
		testing.expect(t, dungeon.tracks[5].file == "ambience_strings.ogg" && dungeon.tracks[5].condition == .Dungeon_Default_Music,
			"the dungeon strings must use the default spatial stem group")
		testing.expect(t,
			dungeon.tracks[6].file == "lead_glorious_horn.ogg" && dungeon.tracks[6].condition == .Dungeon_Elite_Music &&
			dungeon.tracks[6].volume == 0.7,
			"the elite horn must use its proximity stem group at 70% volume",
		)
		testing.expect(t,
			dungeon.tracks[7].file == "bar_guitar.ogg" && dungeon.tracks[7].condition == .Dungeon_String_Guitar_Music &&
			dungeon.tracks[7].volume == 0.8,
			"Bar guitar must use String's dedicated proximity envelope with reduced pre-saturation gain",
		)
		testing.expect(t,
			dungeon.tracks[8].file == "bar_melody_flute.ogg" && dungeon.tracks[8].condition == .Dungeon_Bar_Music &&
			dungeon.tracks[8].volume == 0.85 && dungeon.tracks[8].alternate,
			"Bar flute must use the shared Bar envelope at 85% authored gain and alternate each Loop cycle",
		)
	}

	boss := ar.music_library_mix(&library, "boss")
	if boss == nil {
		testing.expect(t, false, "boss mix must exist")
		return
	}
	testing.expect(t, boss.crossfade_ms == 1000, "transitions into boss must crossfade for 1 second")
	testing.expect(t, len(boss.tracks) == 4, "boss must expose all four live stems")
	if len(boss.tracks) == 4 {
		testing.expect(t, boss.tracks[0].file == "ambience_grim_bass.ogg", "boss must include grim bass")
		testing.expect(t, boss.tracks[1].file == "beat_high.ogg", "boss must include the high beat")
		testing.expect(t, boss.tracks[2].file == "lead_grim_horn.ogg", "boss must include grim horn")
		testing.expect(t, boss.tracks[3].file == "ambience_choir.ogg" && boss.tracks[3].condition == .Boss_Choir,
			"waiting boss mix must carry the phase-locked conditional choir")
	}
	battle := ar.music_library_mix(&library, "boss_battle")
	if battle == nil {
		testing.expect(t, false, "boss_battle mix must exist")
		return
	}
	testing.expect(t, battle.crossfade_ms == 1000, "transitions into the active battle must crossfade for 1 second")
	testing.expect(t, len(battle.tracks) == 7,
		"boss battle must expose bass, beat, Alasin, choir, and all three guitar tiers")
	if len(battle.tracks) == 7 {
		testing.expect(t, battle.tracks[0].file == "ambience_grim_bass.ogg", "boss battle must include grim bass")
		testing.expect(t, battle.tracks[1].file == "beat_high.ogg", "boss battle must include the high beat")
		testing.expect(t, battle.tracks[2].file == "ambience_alasin.ogg" && battle.tracks[2].condition == .Always,
			"boss battle must play Alasin continuously")
		testing.expect(t, battle.tracks[3].file == "ambience_choir.ogg" && battle.tracks[3].condition == .Boss_Choir,
			"boss battle must retain the same phase-locked conditional choir")
		testing.expect(t,
			battle.tracks[4].file == "lead_guitar_low.ogg" && battle.tracks[4].condition == .Boss_Guitar_Low &&
			battle.tracks[4].volume == 0.6375,
			"boss battle low guitar must carry its runtime condition at 63.75% volume",
		)
		testing.expect(t,
			battle.tracks[5].file == "lead_guitar_mid.ogg" && battle.tracks[5].condition == .Boss_Guitar_Mid &&
			battle.tracks[5].volume == 0.6375,
			"boss battle mid guitar must carry its runtime condition at 63.75% volume",
		)
		testing.expect(t,
			battle.tracks[6].file == "lead_guitar_high.ogg" && battle.tracks[6].condition == .Boss_Guitar_High &&
			battle.tracks[6].volume == 0.6375,
			"boss battle high guitar must carry its runtime condition at 63.75% volume",
		)
	}
	// Boss Battle and Dungeon share only grim bass. All nine incoming Dungeon
	// slots plus six outgoing-only battle slots must coexist for the 1-second
	// return crossfade, even though several dynamic stems may be gated.
	testing.expect(t, ar.MUSIC_MAX_SLOTS >= 15, "Boss Battle/Dungeon crossfade must fit all fifteen unique slots")
	testing.expect(t, ar.MUSIC_MAX_ASSETS >= 16, "the PCM cache must fit all sixteen unique authored assets")

	for mix in library.mixes {
		for track in mix.tracks {
			path := fmt.aprintf("assets/audio/bgm/%s", track.file)
			file_data, file_err := os.read_entire_file_from_path(path, context.allocator)
			testing.expectf(t, file_err == nil, "referenced track %s must exist on disk", track.file)
			if file_err == nil do delete(file_data)
			delete(path)
			testing.expect(t, track.volume >= 0 && track.volume <= 1, "track volume must be in range")
		}
	}

	boot := ar.music_library_mix(&library, "menu_boot")
	if boot == nil {
		testing.expect(t, false, "menu_boot mix must exist")
		return
	}
	testing.expect(t, len(boot.tracks) == 1 && boot.tracks[0].file == "beat_low.ogg",
		"the intro must carry beat_low alone")
}

@(test)
music_selector_maps_screens_to_mixes :: proc(t: ^testing.T) {
	app: ar.App
	ar.app_init(&app, ar.derive_seed(60, 0))
	defer ar.run_destroy(&app.run)
	ar.run_start(&app.run, app.seed, .Warden)

	app.mode = .Title
	testing.expect(t, ar.music_mix_for(&app) == ar.MUSIC_MIX_MENU, "title must play the menu mix")
	app.mode = .Chronicle
	testing.expect(t, ar.music_mix_for(&app) == ar.MUSIC_MIX_MENU, "chronicle stays on the menu mix")

	app.mode = .Playing
	app.story_panel = {}
	testing.expect(t, ar.music_mix_for(&app) == ar.MUSIC_MIX_DUNGEON, "an ordinary floor plays the dungeon mix")

	for !ar.run_floor_plan(&app.run).has_boss && app.run.depth < ar.DUNGEON_DEPTH do ar.run_descend(&app.run)
	testing.expect(t, ar.boss_alive(&app.run), "the generated boss floor must contain a living boss")
	testing.expect(t, !app.run.boss_engaged, "the boss floor must begin before engagement")
	testing.expect(t, ar.music_mix_for(&app) == ar.MUSIC_MIX_BOSS, "a waiting floor boss plays the boss-level mix")
	app.run.boss_engaged = true
	testing.expect(t, ar.music_mix_for(&app) == ar.MUSIC_MIX_BOSS_BATTLE, "arena engagement starts the boss-battle mix")
	for &enemy in app.run.enemies do if enemy.role == .Boss do enemy.hp = 0
	testing.expect(t, ar.music_mix_for(&app) == ar.MUSIC_MIX_DUNGEON, "defeating the boss returns to the dungeon mix")

	app.story_panel.active = true
	testing.expect(t, ar.music_mix_for(&app) == ar.MUSIC_MIX_MENU, "a story modal switches from gameplay to the menu mix")
	app.story_panel = {}
	app.story_minigame = {active = true, kind = .Wake_The_Moonbloom}
	testing.expect(t, ar.music_mix_for(&app) == ar.MUSIC_MIX_DUNGEON,
		"the Garden minigame must retain spatial Dungeon music")
	app.story_minigame.kind = .Bind_The_Page
	testing.expect(t, ar.music_mix_for(&app) == ar.MUSIC_MIX_MENU,
		"non-Garden minigames remain score-changing story modals")
	app.story_minigame = {}

	app.mode = .Paused
	testing.expect(t, ar.music_mix_for(&app) == ar.MUSIC_MIX_DUNGEON, "pause keeps the run's mix")
	app.mode = .Options
	app.options_return = .Paused
	testing.expect(t, ar.music_mix_for(&app) == ar.MUSIC_MIX_DUNGEON, "options over a run keeps the run's mix")
	app.options_return = .Title
	testing.expect(t, ar.music_mix_for(&app) == ar.MUSIC_MIX_MENU, "options from the title keeps the menu mix")

	app.mode = .Dead
	testing.expect(t, ar.music_mix_for(&app) == ar.MUSIC_MIX_MENU, "death returns to the menu mix")
}

@(test)
music_boss_guitar_tiers_follow_player_health_exclusively :: proc(t: ^testing.T) {
	testing.expect(t, ar.music_boss_guitar_for_health(100, 100) == .Low, "full health must use low guitar")
	testing.expect(t, ar.music_boss_guitar_for_health(75, 100) == .Low, "exactly 75% must remain low")
	testing.expect(t, ar.music_boss_guitar_for_health(74, 100) == .Mid, "below 75% must use mid guitar")
	testing.expect(t, ar.music_boss_guitar_for_health(30, 100) == .Mid, "exactly 30% must remain mid")
	testing.expect(t, ar.music_boss_guitar_for_health(29, 100) == .High, "below 30% must use high guitar")
	testing.expect(t, ar.music_boss_guitar_for_health(0, 100) == .High, "lethal health is in the high tier before terminal music wins")
	testing.expect(t, ar.music_boss_guitar_for_health(1, 0) == .Low, "invalid max health must fail safely to low")

	tracks := [3]ar.Music_Mix_Track{
		{condition = .Boss_Guitar_Low},
		{condition = .Boss_Guitar_Mid},
		{condition = .Boss_Guitar_High},
	}
	for tier in ar.Music_Boss_Guitar_Tier {
		audible := 0
		for track in tracks {
			if ar.music_track_runtime_gain(track, {boss_guitar_tier = tier}) > 0 do audible += 1
		}
		testing.expectf(t, audible == 1, "tier %v must enable exactly one guitar, got %d", tier, audible)
	}
}

@(test)
music_boss_choir_fades_in_strictly_below_half_boss_health :: proc(t: ^testing.T) {
	run: ar.Run
	defer delete(run.enemies)
	run.player.hp = 1
	run.player.max_hp = 100
	append(&run.enemies, ar.Enemy{role = .Boss, hp = 100, max_hp = 100})

	testing.expect(t, ar.music_boss_choir_gain(&run) == 0, "full boss health must keep the choir muted")
	run.enemies[0].hp = 50
	testing.expect(t, ar.music_boss_choir_gain(&run) == 0, "exactly 50% boss health must remain muted")
	run.enemies[0].hp = 49
	testing.expect(t, ar.music_boss_choir_gain(&run) == 1, "below 50% boss health must target full choir")
	run.enemies[0].hp = 0
	testing.expect(t, ar.music_boss_choir_gain(&run) == 0, "a defeated boss must fade the choir out")
	run.enemies[0] = {role = .Normal, hp = 1, max_hp = 100}
	testing.expect(t, ar.music_boss_choir_gain(&run) == 0, "low-health ordinary enemies must not trigger boss choir")

	track := ar.Music_Mix_Track{condition = .Boss_Choir}
	testing.expect(t, ar.music_track_runtime_gain(track, {}) == 0, "boss choir must be runtime-muted by default")
	testing.expect(t, ar.music_track_runtime_gain(track, {boss_choir_gain = 0.5}) == 0.5,
		"boss choir condition must preserve the fade envelope")
}

@(test)
music_dungeon_elite_horn_uses_absolute_distance_and_smooth_gain :: proc(t: ^testing.T) {
	run: ar.Run
	defer delete(run.enemies)
	run.player.pos = {}
	append(&run.enemies, ar.Enemy{role = .Elite, hp = 10, max_hp = 10, pos = {12, 0}})

	testing.expect(t, ar.music_dungeon_elite_horn_gain(&run) == 0,
		"horn must begin at 0% twelve tiles from the nearest elite")
	run.enemies[0].pos = {10, 0}
	testing.expect(t, abs(ar.music_dungeon_elite_horn_gain(&run) - 0.15625) < 1e-5,
		"horn must follow the smooth absolute-distance curve without room or LOS gates")
	run.enemies[0].pos = {8, 0}
	testing.expect(t, abs(ar.music_dungeon_elite_horn_gain(&run) - 0.5) < 1e-5,
		"eight tiles must be the 50% midpoint of the smooth curve")
	run.enemies[0].pos = {4, 0}
	testing.expect(t, ar.music_dungeon_elite_horn_gain(&run) == 1,
		"four tiles or fewer must reach 100%")

	run.enemies[0].role = .Normal
	testing.expect(t, ar.music_dungeon_elite_horn_gain(&run) == 0, "ordinary enemies must not trigger the horn")
	run.enemies[0].role = .Elite
	run.enemies[0].hp = 0
	testing.expect(t, ar.music_dungeon_elite_horn_gain(&run) == 0, "a defeated elite must mute the horn target")
	run.enemies[0] = {role = .Elite, hp = 10, max_hp = 10, pos = {12, 0}}
	append(&run.enemies, ar.Enemy{role = .Elite, hp = 10, max_hp = 10, pos = {4, 0}})
	testing.expect(t, ar.music_dungeon_elite_horn_gain(&run) == 1,
		"the nearest living elite anywhere on the floor must control the gain")

	near_silent := ar.music_elite_horn_gain_for_distance(11.99)
	testing.expect(t, near_silent > 0 && near_silent < 0.001,
		"the curve must leave silence continuously instead of snapping in")
	track := ar.Music_Mix_Track{condition = .Dungeon_Elite_Music}
	testing.expect(t, ar.music_track_runtime_gain(track, {}) == 0, "the glorious horn must be runtime-muted by default")
	testing.expect(t, ar.music_track_runtime_gain(track, {dungeon_elite_horn_gain = 0.5}) == 0.5,
		"the runtime gate must preserve intermediate distance gain")
}

@(test)
music_dungeon_quest_harp_follows_room_distance_and_reaches_full_inside :: proc(t: ^testing.T) {
	run: ar.Run
	run.dungeon.room_count = 2
	run.dungeon.rooms_buf[1] = {20, 20, 10, 8}
	run.dungeon.special_room_count = 1
	run.dungeon.special_rooms_buf[0] = {.Quest, 1}

	run.player.pos = {12, 24}
	testing.expect(t, ar.music_dungeon_quest_harp_gain(&run) == 0,
		"second harp must begin at 0% eight tiles from the Quest room")
	run.player.pos = {16, 24}
	testing.expect(t, abs(ar.music_dungeon_quest_harp_gain(&run) - 0.5) < 1e-5,
		"second harp must reach 50% four tiles from the Quest room")
	run.player.pos = {20.5, 24}
	testing.expect(t, ar.music_dungeon_quest_harp_gain(&run) == 1,
		"second harp must reach 100% inside the Quest room")

	original := ar.Music_Mix_Track{condition = .Dungeon_Default_Music}
	second := ar.Music_Mix_Track{condition = .Dungeon_Quest_Music}
	runtime := ar.Music_Runtime_State{dungeon_quest_harp_gain = 1}
	testing.expect(t, ar.music_track_runtime_gain(original, runtime) == 1 &&
		ar.music_track_runtime_gain(second, runtime) == 1,
		"both dungeon harps must publish 100% gain inside the Quest room when no higher-priority room is near")
	run.dungeon.special_room_count = 0
	testing.expect(t, ar.music_dungeon_quest_harp_gain(&run) == 0,
		"floors without a Quest room must keep the second harp muted")
}

@(test)
music_dungeon_bar_flute_stays_room_bound_while_guitar_follows_string :: proc(t: ^testing.T) {
	run: ar.Run
	defer delete(run.familiars)
	run.dungeon.room_count = 2
	run.dungeon.rooms_buf[1] = {20, 20, 10, 8}
	run.dungeon.special_room_count = 1
	run.dungeon.special_rooms_buf[0] = {.Bar, 1}
	run.ambient_residents.count = 1
	run.ambient_residents.items[0] = {active = true, kind = .String}

	// Before recruitment active resident String uses the exact Bar-room envelope
	// used by the flute and by ordinary Dungeon-layer ducking.
	run.player.pos = {12, 24}
	testing.expect(t, ar.music_dungeon_bar_gain(&run) == 0 && ar.music_dungeon_string_guitar_gain(&run) == 0,
		"unrecruited Bar stems must be silent eight tiles from the room")
	run.player.pos = {16, 24}
	testing.expect(t, abs(ar.music_dungeon_bar_gain(&run) - 0.5) < 1e-5 &&
		abs(ar.music_dungeon_string_guitar_gain(&run) - 0.5) < 1e-5,
		"unrecruited guitar and flute must share the Bar midpoint")
	run.player.pos = {20.5, 24}
	testing.expect(t, ar.music_dungeon_bar_gain(&run) == 1 && ar.music_dungeon_string_guitar_gain(&run) == 1,
		"unrecruited guitar and flute must be full inside the Bar")

	bar_runtime := ar.Music_Runtime_State{
		dungeon_bar_gain = 1,
		dungeon_string_guitar_gain = 1,
		dungeon_elite_horn_gain = 1,
		dungeon_quest_harp_gain = 1,
	}
	testing.expect(t, ar.music_track_runtime_gain({file = "ambience_grim_bass.ogg", condition = .Always}, bar_runtime) == 1,
		"grim bass must remain full inside the Bar")
	testing.expect(t, ar.music_track_runtime_gain({file = "beat_low.ogg", condition = .Always}, bar_runtime) == 1,
		"low beat must remain full inside the Bar")
	testing.expect(t, ar.music_track_runtime_gain({condition = .Dungeon_Default_Music}, bar_runtime) == 0,
		"ordinary Dungeon stems must be fully ducked inside the Bar")
	testing.expect(t, ar.music_track_runtime_gain({condition = .Dungeon_Elite_Music}, bar_runtime) == 0,
		"the elite horn must be fully ducked inside the Bar")
	testing.expect(t, ar.music_track_runtime_gain({condition = .Dungeon_Quest_Music}, bar_runtime) == 0,
		"the Quest harp must be fully ducked inside the Bar")
	testing.expect(t, ar.music_track_runtime_gain({condition = .Dungeon_Bar_Music}, bar_runtime) == 1,
		"the Bar flute must be full inside the room")
	testing.expect(t, ar.music_track_runtime_gain({condition = .Dungeon_String_Guitar_Music}, bar_runtime) == 1,
		"the unrecruited guitar must be full inside the room")

	// Once String is recruited, only the guitar uses the same 4-full/12-silent
	// smoothstep curve as the elite horn. Room membership and LOS are irrelevant.
	run.player.pos = {}
	run.ambient_residents.items[0].active = false
	append(&run.familiars, ar.Familiar{kind = .String, hp = 10, max_hp = 10, pos = {12, 0}})
	testing.expect(t, ar.music_dungeon_bar_gain(&run) == 0 && ar.music_dungeon_string_guitar_gain(&run) == 0,
		"String's guitar must be silent at twelve tiles without carrying Bar proximity")
	run.familiars[0].pos = {10, 0}
	testing.expect(t, abs(ar.music_dungeon_string_guitar_gain(&run) - 0.15625) < 1e-5,
		"String's guitar must reuse the elite smoothstep curve")
	run.familiars[0].pos = {8, 0}
	testing.expect(t, abs(ar.music_dungeon_string_guitar_gain(&run) - 0.5) < 1e-5,
		"String's guitar must reach 50% at eight tiles")
	run.familiars[0].pos = {4, 0}
	testing.expect(t, ar.music_dungeon_string_guitar_gain(&run) == 1,
		"String's guitar must be full at four tiles or fewer")

	string_runtime := ar.Music_Runtime_State{
		dungeon_string_guitar_gain = 1,
		dungeon_elite_horn_gain = 1,
		dungeon_quest_harp_gain = 1,
	}
	testing.expect(t, ar.music_track_runtime_gain({condition = .Dungeon_String_Guitar_Music}, string_runtime) == 1,
		"recruited String must carry only the guitar")
	testing.expect(t, ar.music_track_runtime_gain({condition = .Dungeon_Bar_Music}, string_runtime) == 0,
		"String proximity must not carry the Bar flute")
	testing.expect(t, ar.music_track_runtime_gain({condition = .Dungeon_Default_Music}, string_runtime) == 1 &&
		ar.music_track_runtime_gain({condition = .Dungeon_Elite_Music}, string_runtime) == 1 &&
		ar.music_track_runtime_gain({condition = .Dungeon_Quest_Music}, string_runtime) == 1,
		"String proximity must not carry Bar-room ducking")

	// A dead recruited String is no longer a guitar source; the retired resident
	// must not make the instrument teleport back to the Bar.
	run.familiars[0].hp = 0
	run.player.pos = {20.5, 24}
	testing.expect(t, ar.music_dungeon_bar_gain(&run) == 1 && ar.music_dungeon_string_guitar_gain(&run) == 0,
		"dead recruited String must stop the guitar without changing Bar flute proximity")
	run.dungeon.special_room_count = 0
	testing.expect(t, ar.music_dungeon_bar_gain(&run) == 0 && ar.music_dungeon_string_guitar_gain(&run) == 0,
		"without a living String or Bar both Bar instruments must be silent")
}

@(test)
music_dungeon_garden_ducks_every_non_core_stem_by_room_distance :: proc(t: ^testing.T) {
	run: ar.Run
	run.dungeon.room_count = 2
	run.dungeon.rooms_buf[1] = {20, 20, 10, 8}
	run.dungeon.special_room_count = 1
	run.dungeon.special_rooms_buf[0] = {.Garden, 1}

	run.player.pos = {12, 24}
	testing.expect(t, ar.music_dungeon_garden_gain(&run) == 0,
		"Garden ducking must begin from silence eight tiles from the room")
	run.player.pos = {16, 24}
	testing.expect(t, abs(ar.music_dungeon_garden_gain(&run) - 0.5) < 1e-5,
		"Garden ducking must reach its midpoint four tiles out")
	run.player.pos = {20.5, 24}
	testing.expect(t, ar.music_dungeon_garden_gain(&run) == 1,
		"Garden ducking must be full throughout the room")

	runtime := ar.Music_Runtime_State{
		dungeon_garden_gain = 1,
		dungeon_bar_gain = 1,
		dungeon_string_guitar_gain = 1,
		dungeon_elite_horn_gain = 1,
		dungeon_quest_harp_gain = 1,
	}
	testing.expect(t, ar.music_track_runtime_gain({file = "ambience_grim_bass.ogg", condition = .Always}, runtime) == 1,
		"grim bass must remain full inside the Garden")
	testing.expect(t, ar.music_track_runtime_gain({file = "beat_low.ogg", condition = .Always}, runtime) == 1,
		"low beat must remain full inside the Garden")
	testing.expect(t, ar.music_track_runtime_gain({condition = .Dungeon_Default_Music}, runtime) == 0,
		"ordinary Dungeon stems must be silent inside the Garden")
	testing.expect(t, ar.music_track_runtime_gain({condition = .Dungeon_Elite_Music}, runtime) == 0,
		"the elite horn must be silent inside the Garden")
	testing.expect(t, ar.music_track_runtime_gain({condition = .Dungeon_Quest_Music}, runtime) == 0,
		"the Quest harp must be silent inside the Garden")
	testing.expect(t, ar.music_track_runtime_gain({condition = .Dungeon_Bar_Music}, runtime) == 0,
		"Garden priority must silence the Bar flute even if proximity envelopes overlap")
	testing.expect(t, ar.music_track_runtime_gain({condition = .Dungeon_String_Guitar_Music}, runtime) == 0,
		"Garden priority must silence String's guitar even away from the Bar")

	run.dungeon.special_room_count = 0
	testing.expect(t, ar.music_dungeon_garden_gain(&run) == 0,
		"floors without a Garden must leave Dungeon layers unducked")
}

@(test)
music_elite_horn_runtime_gain_slews_abrupt_targets :: proc(t: ^testing.T) {
	app: ar.App
	defer delete(app.run.enemies)
	app.run.player.pos = {}
	append(&app.run.enemies, ar.Enemy{role = .Elite, hp = 10, max_hp = 10, pos = {4, 0}})
	state: ar.Music_Runtime_State
	ar.music_runtime_state_update(&state, &app, true, false, 0.1)
	testing.expect(t, abs(state.dungeon_elite_horn_gain - 0.2) < 1e-5,
		"the elite horn must retain its 500 ms proximity attack")

	state.dungeon_elite_horn_gain = 1
	app.run.enemies[0].hp = 0
	ar.music_runtime_state_update(&state, &app, true, false, 0.1)
	testing.expect(t, abs(state.dungeon_elite_horn_gain - 0.95) < 1e-5,
		"killing the elite must select the 2-second horn release")
	testing.expect(t, ar.music_gain_slew(0.4, 0.8, 0, ar.MUSIC_ELITE_HORN_ATTACK_SECONDS) == 0.4,
		"a suspended frame must freeze the gain envelope")
	testing.expect(t, ar.music_gain_slew(0, 0.3, 1, ar.MUSIC_ELITE_HORN_ATTACK_SECONDS) == 0.3,
		"the slew must clamp at a nearby target without overshoot")
}

@(test)
music_string_guitar_runtime_gain_uses_bar_fade_duration :: proc(t: ^testing.T) {
	app: ar.App
	defer delete(app.run.familiars)
	app.run.player.pos = {}
	append(&app.run.familiars, ar.Familiar{kind = .String, hp = 10, max_hp = 10, pos = {4, 0}})
	state: ar.Music_Runtime_State
	ar.music_runtime_state_update(&state, &app, true, false, 0.1)
	testing.expect(t, abs(state.dungeon_string_guitar_gain - 0.2) < 1e-5,
		"String's guitar must use the Bar envelope's 500 ms attack")
	testing.expect(t, state.dungeon_bar_gain == 0,
		"String's guitar attack must not create Bar-room ducking")

	state.dungeon_string_guitar_gain = 1
	app.run.familiars[0].pos = {12, 0}
	ar.music_runtime_state_update(&state, &app, true, false, 0.1)
	testing.expect(t, abs(state.dungeon_string_guitar_gain - 0.8) < 1e-5,
		"String's guitar must use the Bar envelope's 500 ms release")
}

@(test)
music_unknown_track_condition_rejects_document :: proc(t: ^testing.T) {
	document := transmute([]u8)string(`{
	  "format_version": 1,
	  "loop_ms": 1000,
	  "mixes": {"main": {"tracks": [{"file": "a.ogg", "volume": 1.0, "condition": "unknown"}]}}
	}`)
	library, ok := ar.music_library_parse(document)
	defer ar.music_library_destroy(&library)
	testing.expect(t, !ok, "an unknown runtime condition must reject the mix document")
}

@(test)
music_master_tape_saturation_is_audible_biased_and_monotonic :: proc(t: ^testing.T) {
	quiet := ar.audio_music_saturate_sample(0.1)
	positive := ar.audio_music_saturate_sample(1)
	negative := ar.audio_music_saturate_sample(-1)
	hot := ar.audio_music_saturate_sample(2)

	testing.expect(t, ar.MUSIC_SATURATION_DRIVE == 3, "music tape drive must remain at the approved lighter 3x level")
	testing.expect(t, ar.MUSIC_SATURATION_MIX == 0.5, "music tape stage must remain a 50/50 wet-dry blend")
	testing.expect(t, ar.audio_music_saturate_sample(0) == 0, "saturation must preserve exact silence")
	testing.expect(t, quiet > 0.10 && quiet < 0.12, "parallel tape saturation must gently color quiet authored stems")
	testing.expect(t, abs(negative) > positive && abs(positive + negative) > 0.03,
		"tape bias must make positive and negative saturation intentionally asymmetric")
	testing.expect(t, positive > quiet && hot > positive, "the softsign transfer curve must remain strictly monotonic")
	testing.expect(t, hot < 1.25, "hot sums must remain compressed before limiting with a 50% clean blend")

	dsp: ar.Music_Master_DSP
	ar.audio_music_master_dsp_reset(&dsp)
	left, right := ar.audio_music_tape_frame(&dsp, 0, 0)
	testing.expect(t, left == 0 && right == 0, "the stateful tape stage must preserve exact stereo silence")
}

@(test)
music_master_limiter_is_stereo_linked_bounded_and_releases :: proc(t: ^testing.T) {
	dsp: ar.Music_Master_DSP
	ar.audio_music_master_dsp_reset(&dsp)
	left, right := ar.audio_music_limit_frame(&dsp, 2, 1)

	testing.expect(t, abs(left) <= ar.MUSIC_LIMITER_CEILING && abs(right) <= ar.MUSIC_LIMITER_CEILING,
		"the zero-lookahead attack must catch the current stereo frame")
	testing.expect(t, abs(right * 2 - left) < 1e-5,
		"one linked gain must preserve the stereo image")
	reduced_gain := dsp.limiter_gain
	testing.expect(t, reduced_gain > 0 && reduced_gain < 1, "a hot frame must engage gain reduction")

	for _ in 0 ..< ar.MUSIC_SAMPLE_RATE do _, _ = ar.audio_music_limit_frame(&dsp, 0, 0)
	testing.expect(t, dsp.limiter_gain > reduced_gain && dsp.limiter_gain > 0.99 && dsp.limiter_gain <= 1,
		"silence must release smoothly back toward unity without overshoot")

	ar.audio_music_master_dsp_reset(&dsp)
	testing.expect(t, dsp.limiter_gain == 1, "hard mixer resets must clear prior gain reduction")
}

@(private = "file")
MUSIC_TEST_DOC :: `{
  "format_version": 1,
  "loop_ms": 1000,
  "boot": { "mix": "intro", "length_scale": 0.5 },
  "mixes": {
    "intro": { "tracks": [ { "file": "a.ogg", "volume": 1.0 } ] },
    "main": {
      "tracks": [
        { "file": "a.ogg", "volume": 1.0 },
        { "file": "b.ogg", "volume": 0.8, "alternate": true }
      ]
    },
    "other": { "crossfade_ms": 500, "tracks": [ { "file": "c.ogg", "volume": 1.0 } ] }
  }
}`

@(private = "file")
music_test_library :: proc(t: ^testing.T) -> ar.Music_Library {
	library, ok := ar.music_library_parse(transmute([]u8)string(MUSIC_TEST_DOC))
	testing.expect(t, ok, "test document must parse")
	return library
}

@(private = "file")
music_slot_for :: proc(director: ^ar.Music_Director, file: string) -> ^ar.Music_Slot {
	for &slot in director.slots {
		if slot.active && slot.file == file do return &slot
	}
	return nil
}

@(test)
music_boot_intro_hands_off_at_scaled_boundary :: proc(t: ^testing.T) {
	library := music_test_library(t)
	defer ar.music_library_destroy(&library)
	director: ar.Music_Director

	ar.music_director_update(&director, &library, "main", 0)
	testing.expect(t, director.stage == .Boot && director.active_mix == "intro", "the armed boot intro must start first")
	slot_a := music_slot_for(&director, "a.ogg")
	testing.expect(t, slot_a != nil && slot_a.start_pending && slot_a.seek_ms == 0, "the intro slot starts from zero")
	testing.expect(t, slot_a.volume == 1, "the intro enters at authored volume, not a fade")
	slot_a.start_pending = false // platform would consume the start

	ar.music_director_update(&director, &library, "main", 499)
	testing.expect(t, director.stage == .Boot, "the intro must hold below the scaled boundary")

	ar.music_director_update(&director, &library, "main", 2)
	testing.expect(t, director.stage == .Steady && director.active_mix == "main", "crossing 50% must hand off to the desired mix")
	testing.expect(t, director.clock_ms < 3, "the hand-off must reset the Loop epoch to zero")
	slot_a = music_slot_for(&director, "a.ogg")
	slot_b := music_slot_for(&director, "b.ogg")
	testing.expect(t, slot_a != nil && slot_a.start_pending && slot_a.seek_ms == 0,
		"a surviving slot must reseek to the new epoch or it desyncs")
	testing.expect(t, slot_b != nil && slot_b.start_pending && slot_b.seek_ms == 0 && slot_b.volume > 0.79,
		"the incoming slot starts hard from the loop top")
}

@(test)
music_alternate_slot_toggles_each_cycle :: proc(t: ^testing.T) {
	library := music_test_library(t)
	defer ar.music_library_destroy(&library)
	director: ar.Music_Director

	ar.music_director_update(&director, &library, "main", 0)
	ar.music_director_update(&director, &library, "main", 501) // finish intro -> Steady cycle 0
	slot_b := music_slot_for(&director, "b.ogg")
	testing.expect(t, slot_b != nil && abs(slot_b.target - 0.8) < 1e-5, "cycle 0 plays the alternate slot")

	ar.music_director_update(&director, &library, "main", 1000) // into cycle 1
	testing.expect(t, slot_b.target == 0 && slot_b.volume == 0, "cycle 1 must mute the alternate slot hard")

	ar.music_director_update(&director, &library, "main", 1000) // into cycle 2
	testing.expect(t, abs(slot_b.target - 0.8) < 1e-5 && abs(slot_b.volume - 0.8) < 1e-5,
		"cycle 2 must restore the alternate slot hard")
	slot_a := music_slot_for(&director, "a.ogg")
	testing.expect(t, slot_a != nil && slot_a.volume == 1, "the steady slot must ride through the toggles")
}

@(test)
music_mix_switch_crossfades_in_phase :: proc(t: ^testing.T) {
	library := music_test_library(t)
	defer ar.music_library_destroy(&library)
	director: ar.Music_Director

	ar.music_director_update(&director, &library, "main", 0)
	ar.music_director_update(&director, &library, "main", 501)  // Steady, epoch 0
	ar.music_director_update(&director, &library, "main", 300)  // phase 300
	ar.music_director_update(&director, &library, "other", 0)   // switch

	slot_c := music_slot_for(&director, "c.ogg")
	testing.expect(t, slot_c != nil && slot_c.start_pending, "the incoming slot must start")
	testing.expectf(t, abs(slot_c.seek_ms - 300) < 1, "the incoming slot must join at the Loop phase, got %.1f", slot_c.seek_ms)
	testing.expect(t, slot_c.volume < 0.01, "a selector switch fades in instead of snapping")

	testing.expect(t, slot_c.fade_duration_ms == 500, "the incoming mix must supply its 500 ms crossfade")

	// Constant power reaches sqrt(1/2) on both sides at the 250 ms midpoint.
	ar.music_director_update(&director, &library, "other", 250)
	slot_a := music_slot_for(&director, "a.ogg")
	midpoint: f32 = 0.7071068
	testing.expect(t, slot_a != nil && abs(slot_a.volume - midpoint) < 0.02, "the outgoing slot must follow the cosine envelope")
	testing.expect(t, abs(slot_c.volume - midpoint) < 0.02, "the incoming slot must follow the sine envelope")
	testing.expect(t, abs(slot_a.volume * slot_a.volume + slot_c.volume * slot_c.volume - 1) < 0.02,
		"crossfade power must remain constant at the midpoint")

	// Finish at exactly 500 ms: the outgoing slot is reclaimed for the platform.
	ar.music_director_update(&director, &library, "other", 250)
	testing.expect(t, music_slot_for(&director, "a.ogg") == nil, "a fully faded slot must be reclaimed")
	testing.expect(t, abs(slot_c.volume - 1) < 1e-4, "the incoming slot must reach its authored volume")
}

@(test)
music_reference_clock_disciplines_boundaries :: proc(t: ^testing.T) {
	library := music_test_library(t)
	defer ar.music_library_destroy(&library)
	director: ar.Music_Director

	// Wall time runs ahead of the stream: the wall clock alone would cross
	// the 500 ms intro boundary here, but the stream has only played 430 ms,
	// so the hand-off must wait for the music.
	ar.music_director_update(&director, &library, "main", 0)
	ar.music_director_update(&director, &library, "main", 496, reference_phase_ms = 430)
	testing.expectf(t, director.stage == .Boot, "the hand-off must wait for the stream, clock %.1f", director.clock_ms)

	// The stream reaching the boundary fires it, regardless of wall dt.
	ar.music_director_update(&director, &library, "main", 1, reference_phase_ms = 500)
	testing.expect(t, director.stage == .Steady && director.active_mix == "main",
		"the stream position must own the hand-off")

	// Steady: the reference owns the clock; wall dt must not stack on top.
	ar.music_director_update(&director, &library, "main", 100, reference_phase_ms = 40)
	phase := ar.music_phase_ms(&director, &library)
	testing.expectf(t, abs(phase - 40) < 1, "phase must equal the reference, got %.1f", phase)

	// A reference just past a wrap the clock has not crossed pulls forward
	// through the boundary (wrapped shortest distance), and the alternate
	// toggle fires exactly once.
	for _ in 0 ..< 8 do ar.music_director_update(&director, &library, "main", 100, reference_phase_ms = -1)
	slot_b := music_slot_for(&director, "b.ogg")
	testing.expect(t, slot_b != nil && slot_b.target > 0, "still cycle 0 before the wrap")
	ar.music_director_update(&director, &library, "main", 16, reference_phase_ms = 10)
	testing.expect(t, director.cycle == 1 && slot_b.target == 0, "the wrapped reference must advance into cycle 1")
	// A tiny backwards reference right after the wrap must not re-toggle.
	ar.music_director_update(&director, &library, "main", 0, reference_phase_ms = 995)
	testing.expect(t, director.cycle == 1 && slot_b.target == 0, "a backwards wobble must not re-fire the boundary")
}
