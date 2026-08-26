package archrogue_tests

// Headless contract for semantic SFX v2. This validates the typed bank
// registry, committed manifest, and every PCM variant without an audio device.

import "core:encoding/json"
import "core:fmt"
import "core:math"
import "core:os"
import "core:strings"
import "core:testing"
import ar "../src"

@(private = "file")
audio_u16_le :: proc(data: []u8, offset: int) -> u16 {
	return u16(data[offset]) | u16(data[offset + 1]) << 8
}

@(private = "file")
audio_u32_le :: proc(data: []u8, offset: int) -> u32 {
	return u32(data[offset]) |
		u32(data[offset + 1]) << 8 |
		u32(data[offset + 2]) << 16 |
		u32(data[offset + 3]) << 24
}

@(private = "file")
audio_i16_le :: proc(data: []u8, offset: int) -> i32 {
	value := i32(audio_u16_le(data,offset))
	if value >= 0x8000 do value -= 0x10000
	return value
}

@(private = "file")
audio_peak_window_ms :: proc(wav: []u8) -> int {
	if len(wav) < 44 do return -1
	payload_bytes := min(int(audio_u32_le(wav,40)),len(wav)-44)
	frame_count := payload_bytes/4 // stereo PCM16
	window_frames := 480 // 10 ms at 48 kHz
	best_energy: i64 = -1
	best_frame := 0
	for start:=0;start<frame_count;start+=window_frames {
		finish := min(start+window_frames,frame_count)
		energy: i64
		for frame in start..<finish {
			offset := 44+frame*4
			left := i64(audio_i16_le(wav,offset))
			right := i64(audio_i16_le(wav,offset+2))
			mid := left+right
			energy += mid*mid
		}
		if energy > best_energy {best_energy,best_frame=energy,start}
	}
	return best_frame*1000/48000
}

@(private = "file")
audio_near :: proc(a, b: f32) -> bool {
	return math.abs(a - b) < .0001
}

@(private = "file")
audio_priority_value :: proc(name: string) -> u8 {
	switch name {
	case "low":      return 2
	case "medium":   return 6
	case "high":     return 10
	case "critical": return 15
	}
	return 0
}

@(test)
semantic_audio_manifest_and_wavs_are_complete :: proc(t: ^testing.T) {
	data, read_err := os.read_entire_file_from_path("assets/audio/sfx/manifest.json", context.allocator)
	if read_err != nil {
		testing.expect(t, false, "assets/audio/sfx/manifest.json is missing")
		return
	}
	defer delete(data)

	value, parse_err := json.parse(data)
	testing.expect(t, parse_err == nil, "audio manifest does not parse")
	if parse_err != nil do return
	defer json.destroy_value(value)

	root := value.(json.Object)
	testing.expect(t, int(root["format_version"].(json.Float)) == 2, "semantic SFX manifest must remain v2")
	format := root["audio_format"].(json.Object)
	testing.expect(t, int(format["sample_rate"].(json.Float)) == 48000, "SFX must remain 48 kHz")
	testing.expect(t, int(format["sample_size_bits"].(json.Float)) == 16, "SFX must remain 16-bit")
	testing.expect(t, int(format["channels"].(json.Float)) == 2, "SFX must remain stereo")
	testing.expect(t, format["codec"].(json.String) == "pcm_s16le", "SFX codec contract changed")

	banks := root["banks"].(json.Object)
	testing.expectf(t, len(banks) == len(ar.SFX_BANK_DEFS), "manifest has %v banks, registry has %v", len(banks), len(ar.SFX_BANK_DEFS))
	// Public source snapshots intentionally contain no licensed WAVs. Preserve
	// full metadata validation there and reject partial injections; private and
	// release CI additionally run tools/sfx_bundle.py verify for strict hashes.
	licensed_sfx_present := os.exists("assets/audio/sfx/ui_navigate_01.wav")
	file_count := 0
	for bank in ar.Sfx_Bank {
		def := ar.SFX_BANK_DEFS[bank]
		testing.expectf(t, len(def.key) > 0, "bank %v has an empty key", bank)
		testing.expectf(t, 1 <= def.variant_count && def.variant_count <= ar.SFX_MAX_VARIANTS, "%v has invalid variant count %v", def.key, def.variant_count)
		for other in ar.Sfx_Bank {
			if int(other) <= int(bank) do continue
			testing.expectf(t, def.key != ar.SFX_BANK_DEFS[other].key, "duplicate SFX bank key %v", def.key)
		}

		entry_value, found := banks[def.key]
		testing.expectf(t, found, "SFX bank %v is missing from manifest", def.key)
		if !found do continue
		entry := entry_value.(json.Object)
		files := entry["files"].(json.Array)
		testing.expectf(t, len(files) == int(def.variant_count), "%v variant count differs from registry", def.key)
		testing.expectf(t, audio_near(f32(entry["gain"].(json.Float)), def.gain), "%v gain differs from registry", def.key)
		pitch := entry["pitch_range"].(json.Array)
		testing.expectf(t, len(pitch) == 2 && audio_near(f32(pitch[0].(json.Float)), def.pitch_min) && audio_near(f32(pitch[1].(json.Float)), def.pitch_max), "%v pitch differs from registry", def.key)
		testing.expectf(t, audio_near(f32(entry["cooldown_ms"].(json.Float)) / 1000, def.cooldown_s), "%v cooldown differs from registry", def.key)
		testing.expectf(t, int(entry["polyphony"].(json.Float)) == int(def.polyphony), "%v polyphony differs from registry", def.key)
		testing.expectf(t, audio_priority_value(entry["priority"].(json.String)) == def.priority, "%v priority differs from registry", def.key)
		testing.expectf(t, entry["spatial"].(json.Boolean) == def.spatial, "%v spatial policy differs from registry", def.key)

		for file_value, variant in files {
			file_count += 1
			file_entry := file_value.(json.Object)
			expected_file := fmt.aprintf("%s_%02d.wav", def.key, variant + 1)
			file := file_entry["file"].(json.String)
			testing.expectf(t, file == expected_file, "%v variant filename differs from registry", def.key)
			testing.expectf(t, len(file_entry["sha256"].(json.String)) == 64, "%v has no bake checksum", file)
			duration_ms := file_entry["duration_ms"].(json.Float)
			testing.expectf(t, duration_ms > 0, "%v has invalid duration", file)
			max_duration_ms := entry["max_duration_ms"].(json.Float)
			testing.expectf(t, max_duration_ms == 800 || max_duration_ms == 2500,
				"%v has an invalid runtime duration policy", def.key)
			testing.expectf(t, duration_ms <= max_duration_ms,
				"%v exceeds its %.0f ms runtime SFX cap", file, max_duration_ms)

			path := fmt.aprintf("assets/audio/sfx/%s", file)
			if !licensed_sfx_present {
				testing.expectf(t, !os.exists(path), "public/no-SFX mode found a partial licensed asset: %v", path)
				delete(expected_file)
				delete(path)
				continue
			}
			wav, wav_err := os.read_entire_file_from_path(path, context.allocator)
			testing.expectf(t, wav_err == nil, "%v references missing WAV %v", def.key, path)
			if wav_err != nil {
				delete(expected_file)
				delete(path)
				continue
			}
			valid_header := len(wav) >= 44 &&
				wav[0] == 'R' && wav[1] == 'I' && wav[2] == 'F' && wav[3] == 'F' &&
				wav[8] == 'W' && wav[9] == 'A' && wav[10] == 'V' && wav[11] == 'E' &&
				wav[12] == 'f' && wav[13] == 'm' && wav[14] == 't' && wav[15] == ' ' &&
				wav[36] == 'd' && wav[37] == 'a' && wav[38] == 't' && wav[39] == 'a'
			testing.expectf(t, valid_header, "%v is not a canonical PCM WAV", path)
			if valid_header {
				testing.expectf(t, audio_u32_le(wav, 4) + 8 == u32(len(wav)), "%v RIFF length is malformed", path)
				testing.expectf(t, audio_u16_le(wav, 20) == 1, "%v must contain PCM", path)
				testing.expectf(t, audio_u16_le(wav, 22) == 2, "%v must be stereo", path)
				testing.expectf(t, audio_u32_le(wav, 24) == 48000, "%v must be 48 kHz", path)
				testing.expectf(t, audio_u16_le(wav, 34) == 16, "%v must be 16-bit", path)
				testing.expectf(t, audio_u32_le(wav, 40) + 44 == u32(len(wav)), "%v PCM payload is malformed", path)
				testing.expectf(t, int(file_entry["byte_size"].(json.Float)) == len(wav), "%v byte size differs from manifest", path)
				if def.key == "warden_time_skip" {
					peak_ms := audio_peak_window_ms(wav)
					testing.expectf(t,300<=peak_ms&&peak_ms<=340,
						"%v principal impact is at %v ms, want 300-340 ms cast alignment",path,peak_ms)
				}
			}
			delete(wav)
			delete(expected_file)
			delete(path)
		}
	}
	testing.expectf(t, file_count == int(root["file_count"].(json.Float)), "manifest file_count %v differs from enumerated %v", root["file_count"], file_count)
}

@(test)
semantic_sfx_routing_and_dispatch_gate_are_stable :: proc(t: ^testing.T) {
	testing.expect(t, audio_near(ar.SFX_PLAYER_STEP_INTERVAL_SECONDS, .98), "player footsteps must retain the chosen 980 ms interval")
	testing.expect(t, audio_near(ar.SFX_ENEMY_STEP_INTERVAL_SECONDS, .84), "enemy heavy footsteps must retain the chosen 840 ms interval")
	testing.expect(t, audio_near(ar.SFX_MASTER_OUTPUT_GAIN, .50), "100% SFX must remain capped at half the former master output")
	step_run: ar.Run
	for theme in 0 ..< len(ar.THEMES) {
		step_run.theme_index = theme
		testing.expectf(t, ar.audio_player_step_bank(&step_run) == .Step_Boot_Grass,
			"theme %v changed the universal player grass-footstep bank", theme)
	}
	testing.expect(t, ar.sfx_player_melee_bank(.Warden) == .Melee_Swing_Warden)
	testing.expect(t, ar.sfx_player_melee_bank(.Rogue) == .Melee_Swing_Rogue)
	testing.expect(t, ar.sfx_player_dash_bank(.Arcanist) == .Dash_Arcane)
	testing.expect(t, ar.sfx_player_dash_bank(.Acolyte) == .Dash_Occult)
	testing.expect(t, ar.sfx_item_pickup_bank(.Legendary) == .Item_Pickup_Unique)
	testing.expect(t, ar.sfx_item_pickup_bank(.Cursed) == .Item_Pickup_Cursed)
	testing.expect(t, ar.sfx_trap_bank(.Needle) == .Trap_Needle)
	testing.expect(t, ar.sfx_shrine_bank(.Twilight) == .Shrine_Twilight)
	testing.expect(t, ar.sfx_ability_bank(.Arcane_Lance) == .Void_Arcane_Lance)

	warden_run: ar.Run
	ar.run_start(&warden_run, ar.derive_seed(90201, 0), .Warden)
	clear(&warden_run.sfx)
	warden_run.player.mana = f32(warden_run.player.max_mana)
	testing.expect(t, ar.player_cast_bolt(&warden_run, {1, 0}), "Warden Guard Bolt must cast")
	testing.expect(t, len(warden_run.sfx) > 0 && warden_run.sfx[len(warden_run.sfx)-1].bank == .Warden_Guard_Bolt,
		"Warden Guard Bolt must emit its projectile-first semantic bank")
	clear(&warden_run.sfx)
	warden_run.player.mana = f32(warden_run.player.max_mana)
	testing.expect(t,ar.player_cast_class_skill(&warden_run,{1,0}),"Warden Time Skip must cast")
	testing.expect(t,len(warden_run.sfx)>0&&warden_run.sfx[len(warden_run.sfx)-1].bank==.Warden_Time_Skip&&
		!warden_run.sfx[len(warden_run.sfx)-1].spatial,
		"Warden Time Skip must emit its authored non-spatial bank")
	ar.run_destroy(&warden_run)

	arcanist_run: ar.Run
	ar.run_start(&arcanist_run, ar.derive_seed(90202, 0), .Arcanist)
	clear(&arcanist_run.sfx)
	arcanist_run.player.mana = f32(arcanist_run.player.max_mana)
	testing.expect(t, ar.player_cast_bolt(&arcanist_run, {1, 0}), "Arcanist Arc Bolt must cast")
	testing.expect(t, len(arcanist_run.sfx) > 0 && arcanist_run.sfx[len(arcanist_run.sfx)-1].bank == .Shadow_Cast,
		"Arcanist Arc Bolt must emit the same semantic bank as Acolyte Spirit Bolt")
	ar.run_destroy(&arcanist_run)

	core_count := 0
	for bank in ar.Sfx_Bank {
		fallback := ar.audio_sfx_fallback_bank(bank)
		testing.expectf(t, ar.audio_sfx_bank_is_core(fallback), "%v fallback %v is not staged core", bank, fallback)
		testing.expectf(t, ar.audio_sfx_fallback_bank(fallback) == fallback, "%v fallback does not terminate at %v", bank, fallback)
		if ar.audio_sfx_bank_is_core(bank) {
			core_count += 1
			testing.expectf(t, fallback == bank, "core bank %v must be a fallback fixed point", bank)
		} else {
			testing.expectf(t, fallback != bank, "lazy bank %v has no semantic fallback", bank)
		}
	}
	testing.expect(t, core_count == 29, "web core SFX set changed without updating the pack contract")

	audio_source, audio_source_err := os.read_entire_file_from_path("src/audio.odin", context.allocator)
	testing.expect(t, audio_source_err == nil, "audio source is missing")
	if audio_source_err == nil {
		defer delete(audio_source)
		text := string(audio_source)
		testing.expect(t, strings.contains(text, "if loaded.loaded[variant] do continue"), "web SFX upgrades must skip already-loaded core variants")
		testing.expect(t, strings.contains(text, "audio_sfx_load_bank(audio, bank, log_missing = true)"), "web adoption must retry the shared idempotent bank loader")
	}

	got, ok := ar.audio_cue_for_intent(ar.Intent{back=true, confirm=true})
	testing.expect(t, ok && got == .Ui_Back, "Back must own semantic UI-bank priority")
	got, ok = ar.audio_cue_for_intent(ar.Intent{confirm=true})
	testing.expect(t, ok && got == .Ui_Confirm, "Confirm must route to its semantic UI bank")
	got, ok = ar.audio_cue_for_intent(ar.Intent{menu_horizontal=1})
	testing.expect(t, ok && got == .Ui_Navigate, "navigation must route to its semantic UI bank")
	_, quiet := ar.audio_cue_for_transition(ar.Intent{confirm=true}, .Select, .Playing)
	testing.expect(t, !quiet, "Select -> Playing must leave Run_Start as the sole bank")

	run: ar.Run
	for i in 0 ..< ar.MAX_SFX_EVENTS_PER_FRAME + 8 do ar.sfx_emit(&run, .Impact_Generic, emitter_id=u64(i))
	testing.expect(t, len(run.sfx) == ar.MAX_SFX_EVENTS_PER_FRAME, "semantic SFX queue must be bounded")
	ar.sfx_stop_bank(&run, .Big_Hit_Charge)
	testing.expect(t, len(run.sfx) == ar.MAX_SFX_EVENTS_PER_FRAME, "stop controls must preserve the queue bound")
	testing.expect(t, run.sfx[len(run.sfx)-1].kind == .Stop_Bank && run.sfx[len(run.sfx)-1].bank == .Big_Hit_Charge,
		"stop controls must replace a queued play when the frame queue is saturated")
	defer delete(run.sfx)

	// Dispatch remains headless because every playback entry returns before
	// touching raylib when the audio device is not ready.
	audio: ar.Audio
	testing.expect(t, !ar.audio_any_cue_playing(&audio))
	ar.audio_set_volume(&audio, .5)
	testing.expect(t, audio_near(audio.sfx_gain, .25) && audio.enabled,
		"50% SFX must resolve to one quarter of the former master output")
	ar.audio_set_enabled(&audio, false)
	testing.expect(t, audio.sfx_gain == 0 && !audio.enabled)
	for bank in ar.Sfx_Bank do ar.audio_play_bank(&audio, bank)
	ar.audio_drain(&audio, &run)
	testing.expect(t, len(run.sfx) == 0, "audio_drain must clear safely while silent")
}
