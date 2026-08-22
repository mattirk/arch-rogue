package archrogue_tests

// Headless music-model tests per SOUND.md: the composer document, the
// screen -> mix selector, and the director's boot intro, alternate cycles,
// and phase-locked crossfades. Playback (the raylib live mixer) stays untested
// here; the real-device soak and web smoke harness cover it end to end.

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
	testing.expect(t, library.crossfade_ms == 1500, "the document default crossfade must stay at 1500 ms")
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
	testing.expect(t, dungeon.crossfade_ms == 500, "transitions into dungeon must crossfade for 500 ms")
	testing.expect(t, len(dungeon.tracks) == 5, "dungeon must expose all five live stems")
	if len(dungeon.tracks) == 5 {
		testing.expect(t, dungeon.tracks[0].file == "ambience_grim_bass.ogg", "dungeon must include grim bass")
		testing.expect(t, dungeon.tracks[1].file == "beat_low.ogg", "dungeon must include the low beat")
		testing.expect(t, dungeon.tracks[2].file == "lead_harp.ogg", "dungeon must include harp")
		testing.expect(t, dungeon.tracks[3].file == "lead_pad.ogg", "dungeon must include pad")
		testing.expect(t, dungeon.tracks[4].file == "ambience_strings.ogg", "dungeon must include strings")
	}

	boss := ar.music_library_mix(&library, "boss")
	if boss == nil {
		testing.expect(t, false, "boss mix must exist")
		return
	}
	testing.expect(t, boss.crossfade_ms == 500, "transitions into boss must crossfade for 500 ms")
	testing.expect(t, len(boss.tracks) == 3, "boss must expose all three live stems")
	if len(boss.tracks) == 3 {
		testing.expect(t, boss.tracks[0].file == "ambience_grim_bass.ogg", "boss must include grim bass")
		testing.expect(t, boss.tracks[1].file == "beat_high.ogg", "boss must include the high beat")
		testing.expect(t, boss.tracks[2].file == "lead_grim_horn.ogg", "boss must include grim horn")
	}
	battle := ar.music_library_mix(&library, "boss_battle")
	if battle == nil {
		testing.expect(t, false, "boss_battle mix must exist")
		return
	}
	testing.expect(t, battle.crossfade_ms == 500, "transitions into the active battle must crossfade for 500 ms")
	testing.expect(t, len(battle.tracks) == 5, "boss battle must expose bass, beat, and all three guitar tiers")
	if len(battle.tracks) == 5 {
		testing.expect(t, battle.tracks[0].file == "ambience_grim_bass.ogg", "boss battle must include grim bass")
		testing.expect(t, battle.tracks[1].file == "beat_high.ogg", "boss battle must include the high beat")
		testing.expect(t, battle.tracks[2].file == "lead_guitar_low.ogg" && battle.tracks[2].condition == .Boss_Guitar_Low,
			"boss battle low guitar must carry its runtime condition")
		testing.expect(t, battle.tracks[3].file == "lead_guitar_mid.ogg" && battle.tracks[3].condition == .Boss_Guitar_Mid,
			"boss battle mid guitar must carry its runtime condition")
		testing.expect(t, battle.tracks[4].file == "lead_guitar_high.ogg" && battle.tracks[4].condition == .Boss_Guitar_High,
			"boss battle high guitar must carry its runtime condition")
	}
	// Boss Battle and Dungeon share only grim bass. All five incoming Dungeon
	// slots plus four outgoing-only battle slots must coexist for the 500 ms
	// return crossfade, even though only one guitar tier is audible.
	testing.expect(t, ar.MUSIC_MAX_SLOTS >= 9, "Boss Battle/Dungeon crossfade must fit all nine unique slots")

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
	testing.expect(t, ar.music_mix_for(&app) == ar.MUSIC_MIX_CUTSCENE, "a story modal owns the cutscene mix")
	app.story_panel = {}

	app.mode = .Paused
	testing.expect(t, ar.music_mix_for(&app) == ar.MUSIC_MIX_DUNGEON, "pause keeps the run's mix")
	app.mode = .Options
	app.options_return = .Paused
	testing.expect(t, ar.music_mix_for(&app) == ar.MUSIC_MIX_DUNGEON, "options over a run keeps the run's mix")
	app.options_return = .Title
	testing.expect(t, ar.music_mix_for(&app) == ar.MUSIC_MIX_MENU, "options from the title keeps the menu mix")

	app.mode = .Dead
	testing.expect(t, ar.music_mix_for(&app) == ar.MUSIC_MIX_CUTSCENE, "death plays the cutscene mix")
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
