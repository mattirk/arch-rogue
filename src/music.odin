package archrogue

// Background-music model per SOUND.md: the mixes.json library, the
// screen -> mix selector, and the director state machine that owns the Loop
// clock, the boot intro, per-cycle alternate slots, and crossfade envelopes.
// This file is raylib-free; audio.odin mixes slot states as independent PCM layers.

import "core:encoding/json"
import "core:strings"
import "core:math"

MUSIC_DEFAULT_CROSSFADE_MS              :: f64(1000)
MUSIC_ELITE_HORN_FULL_DISTANCE_TILES    :: f32(4)
MUSIC_ELITE_HORN_SILENT_DISTANCE_TILES  :: f32(12)
MUSIC_ELITE_HORN_ATTACK_SECONDS         :: f32(0.5)
MUSIC_ELITE_HORN_RELEASE_SECONDS        :: f32(2)
MUSIC_QUEST_HARP_SILENT_DISTANCE_TILES :: f32(8)
MUSIC_QUEST_HARP_FADE_SECONDS          :: f32(0.5)
MUSIC_BAR_SILENT_DISTANCE_TILES        :: f32(8)
MUSIC_BAR_FADE_SECONDS                 :: f32(0.5)
MUSIC_GARDEN_SILENT_DISTANCE_TILES     :: f32(8)
MUSIC_GARDEN_FADE_SECONDS              :: f32(0.5)
MUSIC_BOSS_CHOIR_FADE_SECONDS          :: f32(0.5)
MUSIC_MAX_SLOTS                        :: 15
MUSIC_MIXES_DOCUMENT_PATH              :: "assets/audio/bgm/mixes.json"

MUSIC_MIX_MENU        :: "menu"
MUSIC_MIX_DUNGEON     :: "dungeon"
MUSIC_MIX_BOSS        :: "boss"
MUSIC_MIX_BOSS_BATTLE :: "boss_battle"

Music_Effect_Kind :: enum u8 {
	Gain,
	Low_Pass,
	Reverb,
}

Music_Effect :: struct {
	kind:  Music_Effect_Kind,
	value: f32,
}

Music_Track_Condition :: enum u8 {
	Always,
	Boss_Guitar_Low,
	Boss_Guitar_Mid,
	Boss_Guitar_High,
	Boss_Choir,
	Dungeon_Default_Music,
	Dungeon_Elite_Music,
	Dungeon_Quest_Music,
	Dungeon_Bar_Music,
	Dungeon_String_Guitar_Music,
}

Music_Boss_Guitar_Tier :: enum u8 {
	Low,
	Mid,
	High,
}

Music_Runtime_State :: struct {
	boss_guitar_tier:        Music_Boss_Guitar_Tier,
	boss_choir_gain:         f32,
	dungeon_elite_horn_gain: f32,
	dungeon_quest_harp_gain: f32,
	dungeon_bar_gain:           f32,
	dungeon_garden_gain:        f32,
	dungeon_string_guitar_gain: f32,
}

Music_Mix_Track :: struct {
	file:      string, // file name under assets/audio/bgm/
	volume:    f32,    // authored slot balance 0..1
	mute:      bool,   // authored mute: slot declared, contributes silence
	alternate: bool,   // audible on even Loop cycles, silent on odd ones
	condition: Music_Track_Condition,
	effects:   []Music_Effect, // parsed now, applied from M-SND-4 on
}

Music_Mix :: struct {
	name:         string,
	crossfade_ms: f64, // resolved incoming-transition duration
	tracks:       []Music_Mix_Track,
}

Music_Boot :: struct {
	mix:          string,
	length_scale: f32,
}

Music_Library :: struct {
	loaded:       bool,
	loop_ms:      f64,
	crossfade_ms: f64,
	boot:         Music_Boot,
	has_boot:     bool,
	mixes:        []Music_Mix,
}

// --- mixes.json parsing ------------------------------------------------------

@(private = "file")
Music_Effect_DTO :: struct {
	kind:  string,
	value: f32,
}

@(private = "file")
Music_Track_DTO :: struct {
	file:      string,
	volume:    f32,
	mute:      bool,
	alternate: bool,
	condition: string,
	effects:   []Music_Effect_DTO,
}

@(private = "file")
Music_Mix_DTO :: struct {
	crossfade_ms: f64,
	tracks:       []Music_Track_DTO,
}

@(private = "file")
Music_Boot_DTO :: struct {
	mix:          string,
	length_scale: f32,
}

@(private = "file")
Music_Document_DTO :: struct {
	format_version: int,
	loop_ms:        f64,
	crossfade_ms:   f64,
	boot:           Music_Boot_DTO,
	mixes:          map[string]Music_Mix_DTO,
}

@(private = "file")
music_document_destroy :: proc(document: ^Music_Document_DTO) {
	for name, mix in document.mixes {
		for &track in mix.tracks {
			for &effect in track.effects do delete(effect.kind)
			delete(track.effects)
			delete(track.condition)
			delete(track.file)
		}
		delete(mix.tracks)
		delete(name)
	}
	delete(document.mixes)
	delete(document.boot.mix)
	document^ = {}
}

@(private = "file")
music_effect_kind_parse :: proc(id: string) -> (Music_Effect_Kind, bool) {
	switch id {
	case "gain":     return .Gain, true
	case "low_pass": return .Low_Pass, true
	case "reverb":   return .Reverb, true
	}
	return .Gain, false
}

@(private = "file")
music_track_condition_parse :: proc(id: string) -> (Music_Track_Condition, bool) {
	switch id {
	case "":                   return .Always, true
	case "boss_guitar_low":    return .Boss_Guitar_Low, true
	case "boss_guitar_mid":    return .Boss_Guitar_Mid, true
	case "boss_guitar_high":   return .Boss_Guitar_High, true
	case "boss_choir":         return .Boss_Choir, true
	case "dungeon_default_music": return .Dungeon_Default_Music, true
	case "dungeon_elite_music":   return .Dungeon_Elite_Music, true
	case "dungeon_quest_music":        return .Dungeon_Quest_Music, true
	case "dungeon_bar_music":          return .Dungeon_Bar_Music, true
	case "dungeon_string_guitar_music": return .Dungeon_String_Guitar_Music, true
	}
	return .Always, false
}

// Parse the composer-authored mix document. A malformed document yields an
// unloaded library (the director then holds authored silence), matching the
// missing-asset-degrades-to-silence rule; individual unknown effect kinds are
// dropped rather than failing the document.
music_library_parse :: proc(data: []byte) -> (library: Music_Library, ok: bool) {
	document: Music_Document_DTO
	if err := json.unmarshal(data, &document); err != nil do return {}, false
	defer music_document_destroy(&document)
	if document.format_version != 1 do return {}, false
	if !(document.loop_ms > 0) || math.is_inf(document.loop_ms) do return {}, false
	if document.crossfade_ms < 0 || math.is_inf(document.crossfade_ms) do return {}, false
	for _, mix_dto in document.mixes {
		if mix_dto.crossfade_ms < 0 || math.is_inf(mix_dto.crossfade_ms) do return {}, false
		for track_dto in mix_dto.tracks {
			if _, condition_ok := music_track_condition_parse(track_dto.condition); !condition_ok do return {}, false
		}
	}

	library.loop_ms = document.loop_ms
	library.crossfade_ms = document.crossfade_ms > 0 ? document.crossfade_ms : MUSIC_DEFAULT_CROSSFADE_MS
	library.mixes = make([]Music_Mix, len(document.mixes))
	mix_index := 0
	for name, mix_dto in document.mixes {
		mix := &library.mixes[mix_index]
		mix.name = strings.clone(name)
		mix.crossfade_ms = mix_dto.crossfade_ms > 0 ? mix_dto.crossfade_ms : library.crossfade_ms
		mix.tracks = make([]Music_Mix_Track, len(mix_dto.tracks))
		for track_dto, track_index in mix_dto.tracks {
			track := &mix.tracks[track_index]
			track.file = strings.clone(track_dto.file)
			track.volume = clamp(track_dto.volume, 0, 1)
			track.mute = track_dto.mute
			track.alternate = track_dto.alternate
			track.condition, _ = music_track_condition_parse(track_dto.condition)
			if len(track_dto.effects) > 0 {
				effects := make([dynamic]Music_Effect, 0, len(track_dto.effects))
				for effect_dto in track_dto.effects {
					if kind, kind_ok := music_effect_kind_parse(effect_dto.kind); kind_ok {
						append(&effects, Music_Effect{kind, effect_dto.value})
					}
				}
				track.effects = effects[:]
			}
		}
		mix_index += 1
	}
	if document.boot.mix != "" {
		library.has_boot = true
		library.boot.mix = strings.clone(document.boot.mix)
		library.boot.length_scale = clamp(document.boot.length_scale, 0.01, 1)
	}
	library.loaded = true
	return library, true
}

music_library_destroy :: proc(library: ^Music_Library) {
	if library == nil do return
	for &mix in library.mixes {
		for &track in mix.tracks {
			delete(track.file)
			delete(track.effects)
		}
		delete(mix.tracks)
		delete(mix.name)
	}
	delete(library.mixes)
	delete(library.boot.mix)
	library^ = {}
}

music_library_mix :: proc(library: ^Music_Library, name: string) -> ^Music_Mix {
	if library == nil do return nil
	for &mix in library.mixes {
		if mix.name == name do return &mix
	}
	return nil
}

// --- screen -> mix selection -------------------------------------------------

music_boss_guitar_for_health :: proc(hp, max_hp: int) -> Music_Boss_Guitar_Tier {
	if max_hp <= 0 do return .Low
	scaled_hp := clamp(hp, 0, max_hp) * 100
	if scaled_hp < max_hp * 30 do return .High
	if scaled_hp < max_hp * 75 do return .Mid
	return .Low
}

music_elite_horn_gain_for_distance :: proc(distance: f32) -> f32 {
	span := MUSIC_ELITE_HORN_SILENT_DISTANCE_TILES - MUSIC_ELITE_HORN_FULL_DISTANCE_TILES
	progress := clamp(
		(MUSIC_ELITE_HORN_SILENT_DISTANCE_TILES - max(distance, 0)) / span,
		0,
		1,
	)
	// Smoothstep has zero slope at silence and full volume, so ordinary movement
	// across either boundary cannot introduce a gain discontinuity.
	return progress * progress * (3 - 2 * progress)
}

music_dungeon_elite_horn_gain :: proc(run: ^Run) -> f32 {
	if run == nil do return 0
	nearest_distance_squared := MUSIC_ELITE_HORN_SILENT_DISTANCE_TILES * MUSIC_ELITE_HORN_SILENT_DISTANCE_TILES
	for &enemy in run.enemies {
		if enemy.hp <= 0 || enemy.role != .Elite do continue
		delta := enemy.pos - run.player.pos
		distance_squared := delta.x * delta.x + delta.y * delta.y
		nearest_distance_squared = min(nearest_distance_squared, distance_squared)
	}
	return music_elite_horn_gain_for_distance(math.sqrt(nearest_distance_squared))
}

music_quest_harp_gain_for_distance :: proc(distance: f32) -> f32 {
	progress := clamp(
		1 - max(distance, 0) / MUSIC_QUEST_HARP_SILENT_DISTANCE_TILES,
		0,
		1,
	)
	return progress * progress * (3 - 2 * progress)
}

@(private = "file")
music_point_room_distance :: proc(position: Vec2, room: Room) -> f32 {
	left, top := f32(room.x), f32(room.y)
	right, bottom := f32(room.x + room.w), f32(room.y + room.h)
	dx, dy: f32
	if position.x < left {
		dx = left - position.x
	} else if position.x > right {
		dx = position.x - right
	}
	if position.y < top {
		dy = top - position.y
	} else if position.y > bottom {
		dy = position.y - bottom
	}
	return math.hypot(dx, dy)
}

@(private = "file")
music_special_room_gain :: proc(run: ^Run, kind: Special_Room_Kind, silent_distance: f32) -> f32 {
	if run == nil || silent_distance <= 0 do return 0
	special, found := special_room_for_kind(&run.dungeon, kind)
	if !found || special.room_index < 0 || special.room_index >= run.dungeon.room_count do return 0
	room := run.dungeon.rooms_buf[special.room_index]
	distance := music_point_room_distance(run.player.pos, room)
	progress := clamp(1 - max(distance, 0) / silent_distance, 0, 1)
	return progress * progress * (3 - 2 * progress)
}

music_dungeon_quest_harp_gain :: proc(run: ^Run) -> f32 {
	return music_special_room_gain(run, .Quest, MUSIC_QUEST_HARP_SILENT_DISTANCE_TILES)
}

music_dungeon_bar_gain :: proc(run: ^Run) -> f32 {
	return music_special_room_gain(run, .Bar, MUSIC_BAR_SILENT_DISTANCE_TILES)
}

music_dungeon_string_guitar_gain :: proc(run: ^Run) -> f32 {
	if run == nil do return 0
	if guitarist := living_string(run); guitarist != nil {
		delta := guitarist.pos - run.player.pos
		return music_elite_horn_gain_for_distance(math.hypot(delta.x, delta.y))
	}
	for i in 0..<run.ambient_residents.count {
		resident:=&run.ambient_residents.items[i]
		if resident.active && resident.kind==.String do return music_dungeon_bar_gain(run)
	}
	return 0
}

music_dungeon_garden_gain :: proc(run: ^Run) -> f32 {
	return music_special_room_gain(run, .Garden, MUSIC_GARDEN_SILENT_DISTANCE_TILES)
}

music_gain_slew :: proc(current, target, dt, full_scale_seconds: f32) -> f32 {
	to := clamp(target, 0, 1)
	from := clamp(current, 0, 1)
	if full_scale_seconds <= 0 do return to
	max_step := max(dt, 0) / full_scale_seconds
	if to > from do return min(to, from + max_step)
	return max(to, from - max_step)
}

music_boss_choir_gain :: proc(run: ^Run) -> f32 {
	if run == nil do return 0
	for &enemy in run.enemies {
		if enemy.role != .Boss || enemy.hp <= 0 || enemy.max_hp <= 0 do continue
		if enemy.hp * 2 < enemy.max_hp do return 1
	}
	return 0
}

music_runtime_state_for :: proc(
	app: ^App,
	dungeon_conditions_enabled: bool = true,
	boss_conditions_enabled: bool = true,
) -> Music_Runtime_State {
	if app == nil do return {}
	elite_horn_gain, quest_harp_gain, bar_gain, garden_gain, string_guitar_gain, boss_choir_gain: f32
	if dungeon_conditions_enabled {
		elite_horn_gain = music_dungeon_elite_horn_gain(&app.run)
		quest_harp_gain = music_dungeon_quest_harp_gain(&app.run)
		bar_gain = music_dungeon_bar_gain(&app.run)
		garden_gain = music_dungeon_garden_gain(&app.run)
		string_guitar_gain = music_dungeon_string_guitar_gain(&app.run)
	}
	if boss_conditions_enabled do boss_choir_gain = music_boss_choir_gain(&app.run)
	return {
		boss_guitar_tier        = music_boss_guitar_for_health(app.run.player.hp, app.run.player.max_hp),
		boss_choir_gain         = boss_choir_gain,
		dungeon_elite_horn_gain = elite_horn_gain,
		dungeon_quest_harp_gain = quest_harp_gain,
		dungeon_bar_gain           = bar_gain,
		dungeon_garden_gain        = garden_gain,
		dungeon_string_guitar_gain = string_guitar_gain,
	}
}

music_runtime_state_update :: proc(
	state: ^Music_Runtime_State,
	app: ^App,
	dungeon_conditions_enabled: bool,
	boss_conditions_enabled: bool,
	dt: f32,
) {
	if state == nil do return
	target := music_runtime_state_for(app, dungeon_conditions_enabled, boss_conditions_enabled)
	state.boss_guitar_tier = target.boss_guitar_tier
	state.boss_choir_gain = music_gain_slew(
		state.boss_choir_gain,
		target.boss_choir_gain,
		dt,
		MUSIC_BOSS_CHOIR_FADE_SECONDS,
	)
	elite_horn_fade := target.dungeon_elite_horn_gain < state.dungeon_elite_horn_gain ? MUSIC_ELITE_HORN_RELEASE_SECONDS : MUSIC_ELITE_HORN_ATTACK_SECONDS
	state.dungeon_elite_horn_gain = music_gain_slew(
		state.dungeon_elite_horn_gain,
		target.dungeon_elite_horn_gain,
		dt,
		elite_horn_fade,
	)
	state.dungeon_quest_harp_gain = music_gain_slew(
		state.dungeon_quest_harp_gain,
		target.dungeon_quest_harp_gain,
		dt,
		MUSIC_QUEST_HARP_FADE_SECONDS,
	)
	state.dungeon_bar_gain = music_gain_slew(
		state.dungeon_bar_gain,
		target.dungeon_bar_gain,
		dt,
		MUSIC_BAR_FADE_SECONDS,
	)
	state.dungeon_garden_gain = music_gain_slew(
		state.dungeon_garden_gain,
		target.dungeon_garden_gain,
		dt,
		MUSIC_GARDEN_FADE_SECONDS,
	)
	state.dungeon_string_guitar_gain = music_gain_slew(
		state.dungeon_string_guitar_gain,
		target.dungeon_string_guitar_gain,
		dt,
		MUSIC_BAR_FADE_SECONDS,
	)
}

music_track_runtime_gain :: proc(track: Music_Mix_Track, runtime: Music_Runtime_State) -> f32 {
	switch track.condition {
	case .Always:              return 1
	case .Boss_Guitar_Low:     return runtime.boss_guitar_tier == .Low ? 1 : 0
	case .Boss_Guitar_Mid:     return runtime.boss_guitar_tier == .Mid ? 1 : 0
	case .Boss_Guitar_High:    return runtime.boss_guitar_tier == .High ? 1 : 0
	case .Boss_Choir: return clamp(runtime.boss_choir_gain, 0, 1)
	case .Dungeon_Default_Music, .Dungeon_Elite_Music, .Dungeon_Quest_Music, .Dungeon_Bar_Music, .Dungeon_String_Guitar_Music:
		// Spatial rooms are phase-locked stem groups inside the Dungeon mix, not
		// discrete top-level mixes. Only Bar-room proximity ducks ordinary layers;
		// recruited String carries the guitar alone. Garden retains final priority.
		spatial_duck := (1 - clamp(runtime.dungeon_bar_gain, 0, 1)) *
			(1 - clamp(runtime.dungeon_garden_gain, 0, 1))
		if track.condition == .Dungeon_Default_Music do return spatial_duck
		if track.condition == .Dungeon_Elite_Music do return clamp(runtime.dungeon_elite_horn_gain, 0, 1) * spatial_duck
		if track.condition == .Dungeon_Quest_Music do return clamp(runtime.dungeon_quest_harp_gain, 0, 1) * spatial_duck
		if track.condition == .Dungeon_Bar_Music do return clamp(runtime.dungeon_bar_gain, 0, 1) * (1 - clamp(runtime.dungeon_garden_gain, 0, 1))
		if track.condition == .Dungeon_String_Guitar_Music do return clamp(runtime.dungeon_string_guitar_gain, 0, 1) * (1 - clamp(runtime.dungeon_garden_gain, 0, 1))
		return 0
	}
	return 1
}

// Pure app-state -> mix-name mapping (SOUND.md selection table).
music_mix_for :: proc(app: ^App) -> string {
	if app == nil do return MUSIC_MIX_MENU
	playing_mix :: proc(app: ^App) -> string {
		// Wake the Moonbloom is an in-room Garden interaction, not a score-changing
		// cutscene. Keep its spatial Dungeon layers so Garden remains bass + low beat.
		if app_story_minigame_active(app) && app.story_minigame.kind == .Wake_The_Moonbloom {
			return MUSIC_MIX_DUNGEON
		}
		if app_play_modal_open(app) do return MUSIC_MIX_MENU
		if run_floor_plan(&app.run).has_boss && boss_alive(&app.run) {
			if app.run.boss_engaged do return MUSIC_MIX_BOSS_BATTLE
			return MUSIC_MIX_BOSS
		}
		return MUSIC_MIX_DUNGEON
	}
	switch app.mode {
	case .Title, .Select, .Chronicle, .Abandon_Confirm, .Recovery:
		return MUSIC_MIX_MENU
	case .Playing, .Paused, .Resume_Veil:
		return playing_mix(app)
	case .Options, .Controls:
		return app.options_return == .Paused ? playing_mix(app) : MUSIC_MIX_MENU
	case .Save_Wait, .Save_Error:
		return app.persistence_return == .Paused ? playing_mix(app) : MUSIC_MIX_MENU
	case .Dead, .Victory:
		return MUSIC_MIX_MENU
	}
	return MUSIC_MIX_MENU
}

// --- director ----------------------------------------------------------------

Music_Stage :: enum u8 {
	Idle,   // library not started (device not ready / nothing loaded)
	Boot,   // authored intro: boot mix at scaled length, then hand-off
	Steady, // canonical Loop
}

Music_Slot :: struct {
	file:             string, // borrowed from the library; "" = free slot
	in_mix:           bool,   // member of the active mix
	active:           bool,   // platform should hold a stream for it
	volume:           f32,    // current envelope value (pre option master)
	target:           f32,
	fade_from:        f32,
	fade_elapsed_ms:  f64,
	fade_duration_ms: f64, // <= 0 snaps
	start_pending:    bool, // platform must apply this layer's entry phase
	seek_ms:          f64,
	authored:         Music_Mix_Track,
}

Music_Director :: struct {
	stage:      Music_Stage,
	active_mix: string,
	clock_ms:   f64, // ms since the current stage epoch (monotonic per stage)
	cycle:      int, // completed full cycles in Steady
	slots:      [MUSIC_MAX_SLOTS]Music_Slot,
}

music_phase_ms :: proc(director: ^Music_Director, library: ^Music_Library) -> f64 {
	if director == nil || library == nil || !library.loaded do return 0
	if director.stage != .Steady do return director.clock_ms
	// The monotonic cycle guard can leave the clock momentarily behind the
	// counted wrap after a backwards reference correction; never report a
	// negative phase for it.
	return max(0, director.clock_ms - f64(director.cycle) * library.loop_ms)
}

@(private = "file")
music_slot_effective_target :: proc(track: Music_Mix_Track, cycle: int) -> f32 {
	if track.mute do return 0
	if track.alternate && cycle % 2 == 1 do return 0
	return track.volume
}

@(private = "file")
music_find_slot :: proc(director: ^Music_Director, file: string) -> ^Music_Slot {
	for &slot in director.slots {
		if slot.active && slot.file == file do return &slot
	}
	return nil
}

@(private = "file")
music_free_slot :: proc(director: ^Music_Director) -> ^Music_Slot {
	for &slot in director.slots {
		if !slot.active do return &slot
	}
	return nil
}

@(private = "file")
music_crossfade_ms_for_mix :: proc(library: ^Music_Library, name: string) -> f64 {
	mix := music_library_mix(library, name)
	if mix != nil do return mix.crossfade_ms
	return library.crossfade_ms
}

@(private = "file")
music_slot_begin_fade :: proc(slot: ^Music_Slot, target: f32, duration_ms: f64, snap: bool) {
	slot.target = target
	if snap || duration_ms <= 0 {
		slot.volume = target
		slot.fade_from = target
		slot.fade_elapsed_ms = 0
		slot.fade_duration_ms = 0
		return
	}
	slot.fade_from = slot.volume
	slot.fade_elapsed_ms = 0
	slot.fade_duration_ms = duration_ms
}

@(private = "file")
music_constant_power_gain :: proc(from, to, progress: f32) -> f32 {
	angle := clamp(progress, 0, 1) * f32(math.PI) * 0.5
	cosine := math.cos(angle)
	sine := math.sin(angle)
	return math.sqrt(from * from * cosine * cosine + to * to * sine * sine)
}

// Enter a mix: reuse surviving slots (their envelopes carry over), introduce
// missing layers at the given phase, and fade or snap everything toward its
// authored balance. Slots leaving the mix fade to silence and are reclaimed by
// the update loop once inaudible. reseek_survivors marks a Loop epoch change
// (the boot hand-off resets it to zero), which the platform applies to the one
// shared mixer cursor.
@(private = "file")
music_enter_mix :: proc(
	director: ^Music_Director,
	library: ^Music_Library,
	name: string,
	phase_ms: f64,
	snap: bool,
	reseek_survivors := false,
) {
	director.active_mix = name
	fade_ms := music_crossfade_ms_for_mix(library, name)
	for &slot in director.slots do slot.in_mix = false
	mix := music_library_mix(library, name)
	if mix == nil do return // undefined name: authored silence
	for track in mix.tracks {
		slot := music_find_slot(director, track.file)
		if slot == nil {
			slot = music_free_slot(director)
			if slot == nil do continue // more tracks than slots: drop, never crash
			slot^ = {
				file = track.file,
				active = true,
				start_pending = true,
				seek_ms = phase_ms,
			}
		} else if reseek_survivors {
			slot.start_pending = true
			slot.seek_ms = phase_ms
		}
		slot.in_mix = true
		slot.authored = track
		music_slot_begin_fade(slot, music_slot_effective_target(track, director.cycle), fade_ms, snap)
	}
	for &slot in director.slots {
		if slot.active && !slot.in_mix {
			music_slot_begin_fade(&slot, 0, fade_ms, snap)
		}
	}
}

// Advance the Loop clock and slot envelopes by one presentation frame.
// dt_ms comes from render frame time, never the fixed sim step: music keeps
// playing through menus and pauses, and freezes only while suspended (the
// platform simply stops calling this).
//
// reference_phase_ms (< 0 when unavailable) is the played position of a
// live stream, straight from the mixer. Wall frame time systematically runs
// ahead of it — playback starts one device/callback buffer after
// PlayMusicStream — so boundary events decided on wall time alone fire
// 50-100 ms before the music reaches them (the boot hand-off audibly cut
// the intro short). When a reference exists, the clock is re-disciplined to
// it every frame; corrections only move boundary decisions, never samples,
// so they are inaudible in themselves.
music_director_update :: proc(
	director: ^Music_Director,
	library: ^Music_Library,
	desired_mix: string,
	dt_ms: f64,
	reference_phase_ms: f64 = -1,
) {
	if director == nil || library == nil || !library.loaded do return

	if director.stage == .Idle {
		if library.has_boot {
			director.stage = .Boot
			director.clock_ms = 0
			director.cycle = 0
			music_enter_mix(director, library, library.boot.mix, 0, snap = true)
		} else {
			director.stage = .Steady
			director.clock_ms = 0
			director.cycle = 0
			music_enter_mix(director, library, desired_mix, 0, snap = true)
		}
	}

	// A valid reference owns the clock outright — it already contains every
	// elapsed audio frame, so adding wall dt on top would double-count.
	// Wall dt only advances the clock while no stream can report (silent
	// mixes, master volume off, the frame a seek is still pending).
	if reference_phase_ms >= 0 && director.stage != .Idle {
		switch director.stage {
		case .Idle:
		case .Boot:
			// The intro stream starts at zero, so its file position is the
			// clock. Trust it outright.
			director.clock_ms = reference_phase_ms
		case .Steady:
			// Steady phase wraps: correct by the shortest wrapped distance so
			// a reference sitting just past a loop boundary the clock has not
			// crossed yet still pulls forward, not a whole loop back.
			expected := director.clock_ms - f64(director.cycle) * library.loop_ms
			diff := reference_phase_ms - expected
			half := library.loop_ms * 0.5
			for diff > half do diff -= library.loop_ms
			for diff < -half do diff += library.loop_ms
			director.clock_ms = max(0, director.clock_ms + diff)
		}
	} else {
		director.clock_ms += max(dt_ms, 0)
	}

	switch director.stage {
	case .Idle:
	case .Boot:
		// The intro runs exactly one scaled cycle, ignoring the selector until
		// the boundary (the selector never names the boot mix, so a desired-mix
		// comparison here would abort the intro on its first frame). At the
		// boundary it hands off hard to whatever the selector wants right then,
		// resetting the Loop epoch and the shared PCM cursor to the loop top.
		boundary := library.loop_ms * f64(library.boot.length_scale)
		if director.clock_ms >= boundary {
			director.stage = .Steady
			director.clock_ms = 0
			director.cycle = 0
			music_enter_mix(director, library, desired_mix, 0, snap = true, reseek_survivors = true)
		}
	case .Steady:
		// Monotonic: a small backwards reference correction right after a
		// wrap must not re-fire the boundary toggles.
		cycle := max(director.cycle, int(director.clock_ms / library.loop_ms))
		cycle_changed := cycle != director.cycle
		director.cycle = cycle
		if desired_mix != director.active_mix {
			music_enter_mix(director, library, desired_mix, music_phase_ms(director, library), snap = false)
		} else if cycle_changed {
			// Loop wrap: alternate slots toggle hard, exactly at the boundary.
			for &slot in director.slots {
				if !slot.in_mix do continue
				target := music_slot_effective_target(slot.authored, cycle)
				if target != slot.target {
					music_slot_begin_fade(&slot, target, 0, snap = true)
				}
			}
		}
	}

	frame_dt_ms := max(dt_ms, 0)
	for &slot in director.slots {
		if !slot.active do continue
		if slot.fade_duration_ms <= 0 {
			slot.volume = slot.target
		} else {
			slot.fade_elapsed_ms = min(slot.fade_duration_ms, slot.fade_elapsed_ms + frame_dt_ms)
			progress := f32(slot.fade_elapsed_ms / slot.fade_duration_ms)
			slot.volume = music_constant_power_gain(slot.fade_from, slot.target, progress)
			if slot.fade_elapsed_ms >= slot.fade_duration_ms {
				slot.volume = slot.target
				slot.fade_from = slot.target
				slot.fade_elapsed_ms = 0
				slot.fade_duration_ms = 0
			}
		}
		// Reclaim slots that finished fading out of the mix. The platform
		// observes active=false and unloads the stream.
		if !slot.in_mix && slot.target == 0 && slot.volume <= 0.0005 {
			slot = {}
		}
	}
}
