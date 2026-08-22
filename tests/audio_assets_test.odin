package archrogue_tests

// Headless contract for the authored M10 SFX bake. This validates the
// semantic registry, committed manifest, and PCM headers without opening an
// audio device.

import "core:encoding/json"
import "core:fmt"
import "core:os"
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

@(test)
m10_audio_manifest_and_wavs_are_complete :: proc(t: ^testing.T) {
	data, read_err := os.read_entire_file_from_path("assets/audio/sfx/manifest.json", context.allocator)
	if read_err != nil {
		testing.expect(t, false, "assets/audio/sfx/manifest.json missing - run tools/gen_sfx.py")
		return
	}
	defer delete(data)

	value, parse_err := json.parse(data)
	testing.expect(t, parse_err == nil, "audio manifest does not parse")
	if parse_err != nil do return
	defer json.destroy_value(value)

	root := value.(json.Object)
	testing.expect(t, int(root["format_version"].(json.Float)) == 1, "audio manifest format changed")
	testing.expect(t, int(root["sample_rate"].(json.Float)) == 22050, "audio sample rate changed")
	testing.expect(t, int(root["sample_size_bits"].(json.Float)) == 16, "audio bit depth changed")
	testing.expect(t, int(root["channels"].(json.Float)) == 1, "audio channel count changed")
	cues := root["cues"].(json.Object)
	testing.expectf(t, len(cues) == len(ar.AUDIO_CUE_KEYS), "manifest has %v cues, registry has %v", len(cues), len(ar.AUDIO_CUE_KEYS))

	future_count := 0
	for cue in ar.Audio_Cue {
		key := ar.AUDIO_CUE_KEYS[cue]
		file := ar.AUDIO_CUE_FILES[cue]
		testing.expectf(t, len(key) > 0 && len(file) > 4, "cue %v has an empty key/file", cue)

		for other in ar.Audio_Cue {
			if int(other) <= int(cue) do continue
			testing.expectf(t, key != ar.AUDIO_CUE_KEYS[other], "duplicate audio key %v", key)
			testing.expectf(t, file != ar.AUDIO_CUE_FILES[other], "duplicate audio file %v", file)
		}

		entry_value, found := cues[key]
		testing.expectf(t, found, "audio cue %v missing from manifest", key)
		if !found do continue
		entry := entry_value.(json.Object)
		testing.expectf(t, entry["file"].(json.String) == file, "%v file differs from registry", key)
		testing.expectf(t, len(entry["sha256"].(json.String)) == 64, "%v has no bake checksum", key)
		testing.expectf(t, entry["duration_ms"].(json.Float) > 0, "%v has invalid duration", key)

		expected_usage := "runtime"
		if ar.AUDIO_CUE_USAGE[cue] == .Future_Emitter {
			expected_usage = "future_emitter"
			future_count += 1
		}
		testing.expectf(t, entry["usage"].(json.String) == expected_usage, "%v usage differs from registry", key)

		path := fmt.aprintf("assets/audio/sfx/%s", file)
		wav, wav_err := os.read_entire_file_from_path(path, context.allocator)
		testing.expectf(t, wav_err == nil, "%v references missing WAV %v", key, path)
		if wav_err != nil {
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
			testing.expectf(t, audio_u16_le(wav, 22) == 1, "%v must be mono", path)
			testing.expectf(t, audio_u32_le(wav, 24) == 22050, "%v must be 22050 Hz", path)
			testing.expectf(t, audio_u16_le(wav, 34) == 16, "%v must be 16-bit", path)
			testing.expectf(t, audio_u32_le(wav, 40) + 44 == u32(len(wav)), "%v PCM payload is malformed", path)
		}
		delete(wav)
		delete(path)
	}
	// MX.5 flipped trap/shrine/secret to runtime; every authored cue now has a
	// live emitter.
	testing.expect(t, future_count == 0, "no cue should await a future emitter")
}

@(test)
m10_sim_sfx_mapping_and_dispatch_gate_are_stable :: proc(t: ^testing.T) {
	expected := [ar.Sfx_Kind]ar.Audio_Cue{
		.Swing = .Swing, .Hit = .Hit, .Hurt = .Hurt, .Bolt = .Bolt,
		.Pickup = .Pickup, .Potion = .Potion, .Level_Up = .Level_Up,
		.Stairs = .Stairs, .Death = .Death, .Door = .Door,
		.Start = .Start, .Bell = .Bell, .Boss = .Boss, .Victory = .Victory,
		.Drink = .Drink, .Trap = .Trap, .Shrine = .Shrine, .Secret = .Secret,
	}
	for kind in ar.Sfx_Kind do testing.expect(t, ar.audio_cue_for_sfx(kind) == expected[kind])

	got,ok:=ar.audio_cue_for_intent(ar.Intent{back=true,confirm=true})
	testing.expect(t,ok&&got==.Ui_Back,"Back must own semantic UI-cue priority")
	got,ok=ar.audio_cue_for_intent(ar.Intent{confirm=true})
	testing.expect(t,ok&&got==.Ui_Confirm,"Confirm must route to its semantic UI cue")
	got,ok=ar.audio_cue_for_intent(ar.Intent{menu_horizontal=1})
	testing.expect(t,ok&&got==.Ui_Navigate,"navigation must route to its semantic UI cue")
	_,quiet:=ar.audio_cue_for_intent(ar.Intent{move={1,0},interact=true})
	testing.expect(t,!quiet,"ordinary gameplay intent must not emit a menu cue")

	got,ok=ar.audio_cue_for_transition(ar.Intent{confirm=true},.Title,.Select)
	testing.expect(t,ok&&got==.Ui_Confirm,"ordinary confirmation transitions must keep the UI cue")
	_,quiet=ar.audio_cue_for_transition(ar.Intent{confirm=true},.Select,.Playing)
	testing.expect(t,!quiet,"Select -> Playing must leave Start as the sole authored cue")
	got,ok=ar.audio_cue_for_transition(ar.Intent{menu_delta=1},.Playing,.Playing)
	testing.expect(t,ok&&got==.Ui_Navigate,"stable-mode navigation must retain its cue")

	// These calls remain headless because the dispatch gate returns before any
	// raylib function when the device is not ready.
	audio: ar.Audio
	testing.expect(t,!ar.audio_any_cue_playing(&audio),"an uninitialized audio registry cannot have a playing cue")
	ar.audio_set_enabled(&audio, false)
	testing.expect(t, !audio.enabled)
	for cue in ar.Audio_Cue do ar.audio_play_cue(&audio, cue)
	ar.audio_set_enabled(&audio, true)
	testing.expect(t, audio.enabled)
}
