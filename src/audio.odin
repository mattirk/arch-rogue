package archrogue

// Authored sound-effect playback and the live background-music mixer.
// Missing or invalid files degrade to silence; gameplay never depends on audio.

import "core:fmt"
import "core:sync"
import rl "../vendor/raylib"

Audio_Cue :: enum {
	Swing,
	Hit,
	Hurt,
	Bolt,
	Pickup,
	Potion,
	Level_Up,
	Stairs,
	Death,
	Door,
	Start,
	Ui_Navigate,
	Ui_Confirm,
	Ui_Back,
	Bell,
	Boss,
	Victory,
	Drink,
	Trap,
	Shrine,
	Secret,
}

Audio_Cue_Usage :: enum {
	Runtime,
	Future_Emitter,
}

@(rodata)
AUDIO_CUE_KEYS := [Audio_Cue]string{
	.Swing       = "swing",
	.Hit         = "hit",
	.Hurt        = "hurt",
	.Bolt        = "bolt",
	.Pickup      = "pickup",
	.Potion      = "potion",
	.Level_Up    = "levelup",
	.Stairs      = "stairs",
	.Death       = "death",
	.Door        = "door",
	.Start       = "start",
	.Ui_Navigate = "ui_nav",
	.Ui_Confirm  = "ui_confirm",
	.Ui_Back     = "ui_back",
	.Bell        = "bell",
	.Boss        = "boss",
	.Victory     = "victory",
	.Drink       = "drink",
	.Trap        = "trap",
	.Shrine      = "shrine",
	.Secret      = "secret",
}

@(rodata)
AUDIO_CUE_FILES := [Audio_Cue]string{
	.Swing       = "swing.wav",
	.Hit         = "hit.wav",
	.Hurt        = "hurt.wav",
	.Bolt        = "bolt.wav",
	.Pickup      = "pickup.wav",
	.Potion      = "potion.wav",
	.Level_Up    = "levelup.wav",
	.Stairs      = "stairs.wav",
	.Death       = "death.wav",
	.Door        = "door.wav",
	.Start       = "start.wav",
	.Ui_Navigate = "ui_nav.wav",
	.Ui_Confirm  = "ui_confirm.wav",
	.Ui_Back     = "ui_back.wav",
	.Bell        = "bell.wav",
	.Boss        = "boss.wav",
	.Victory     = "victory.wav",
	.Drink       = "drink.wav",
	.Trap        = "trap.wav",
	.Shrine      = "shrine.wav",
	.Secret      = "secret.wav",
}

@(rodata)
AUDIO_CUE_USAGE := [Audio_Cue]Audio_Cue_Usage{
	.Swing       = .Runtime,
	.Hit         = .Runtime,
	.Hurt        = .Runtime,
	.Bolt        = .Runtime,
	.Pickup      = .Runtime,
	.Potion      = .Runtime,
	.Level_Up    = .Runtime,
	.Stairs      = .Runtime,
	.Death       = .Runtime,
	.Door        = .Runtime,
	.Start       = .Runtime,
	.Ui_Navigate = .Runtime,
	.Ui_Confirm  = .Runtime,
	.Ui_Back     = .Runtime,
	.Bell        = .Runtime,
	.Boss        = .Runtime,
	.Victory     = .Runtime,
	.Drink       = .Runtime,
	.Trap        = .Runtime, // MX.5: live trap/shrine/secret systems emit them
	.Shrine      = .Runtime,
	.Secret      = .Runtime,
}

// Kept as a compatibility table for code/tests that address simulation SFX by
// filename. New platform/UI call sites should use Audio_Cue + audio_play_cue.
@(rodata)
SFX_FILES := [Sfx_Kind]string{
	.Swing    = "swing",
	.Hit      = "hit",
	.Hurt     = "hurt",
	.Bolt     = "bolt",
	.Pickup   = "pickup",
	.Potion   = "potion",
	.Level_Up = "levelup",
	.Stairs   = "stairs",
	.Death    = "death",
	.Door     = "door",
	.Start    = "start",
	.Bell     = "bell",
	.Boss     = "boss",
	.Victory  = "victory",
	.Drink    = "drink",
	.Trap     = "trap",
	.Shrine   = "shrine",
	.Secret   = "secret",
}

MUSIC_MAX_ASSETS  :: 16
MUSIC_SAMPLE_RATE :: 48_000
MUSIC_CHANNELS    :: 2
MUSIC_SAMPLE_SIZE :: 16

// The music master bus uses an intentionally audible, allocation-free tape
// stage before a stereo-linked zero-lookahead peak limiter. The authored stems
// are quiet enough that subtle drive stayed nearly linear, so this stage uses
// strong pre-drive, asymmetric soft saturation for even/odd harmonics, and a
// one-pole high-frequency rolloff. A DC blocker removes the bias produced by
// the asymmetric transfer. The limiter's instantaneous attack catches the
// current sample and returns to unity over roughly 100 ms without adding delay.
MUSIC_SATURATION_DRIVE          :: f32(4.00)
MUSIC_SATURATION_MIX            :: f32(1.00)
MUSIC_TAPE_BIAS                 :: f32(0.08)
MUSIC_TAPE_OUTPUT_GAIN          :: f32(0.55)
MUSIC_TAPE_TONE_ALPHA           :: f32(0.65)
MUSIC_TAPE_DC_BLOCK_COEFFICIENT :: f32(0.9987)
MUSIC_LIMITER_CEILING           :: f32(0.8912509)
MUSIC_LIMITER_RELEASE_PER_FRAME :: f32(0.00020831)

Music_Master_DSP :: struct {
	tape_tone_left:      f32,
	tape_tone_right:     f32,
	tape_dc_input_left:  f32,
	tape_dc_input_right: f32,
	tape_dc_output_left: f32,
	tape_dc_output_right: f32,
	limiter_gain:        f32,
}

// Each authored OGG is decoded once into its own immutable PCM layer. The
// callback mixes these layers live, so the director retains independent gain
// control without asking several Vorbis decoders to refill under raylib's
// global audio mutex.
Music_PCM_Asset :: struct {
	file:  string, // borrowed from the music library
	wave:  rl.Wave,
	ready: bool,
}

Audio :: struct {
	sounds:      [Audio_Cue]rl.Sound,
	loaded:      bit_set[Audio_Cue],
	ready:       bool,
	enabled:     bool,
	suspended:   bool,
	initialized: bool,

	music_library:          Music_Library,
	music_assets:           [MUSIC_MAX_ASSETS]Music_PCM_Asset,
	music_asset_count:      int,
	music_loop_frames:      u32,
	music_stream:           rl.AudioStream,
	music_stream_loaded:    bool,
	music_stream_started:   bool,
	music_stream_paused:    bool,
	music_stage:            Music_Stage,
	music_stage_valid:      bool,
	music_target_gain_bits:       [MUSIC_MAX_ASSETS]u32, // atomically published f32 values
	music_published_gains:        [MUSIC_MAX_ASSETS]f32, // render-thread write cache
	music_published_valid:        [MUSIC_MAX_ASSETS]bool,
	music_callback_gains:         [MUSIC_MAX_ASSETS]f32, // audio callback owns while playing
	music_master_target_bits:     u32,                   // atomically published post-DSP user gain
	music_master_published_gain:  f32,                   // render-thread write cache
	music_master_published_valid: bool,
	music_callback_master_gain:   f32,                   // audio callback owns while playing
	music_master_dsp:             Music_Master_DSP,      // audio callback owns while playing
	music_cursor_frame:           u32,                   // atomic next frame to render
	music_reference_frame:  u32,                   // atomic start of audible device block
	music_callback_count:   u32,                   // atomic health telemetry
	music_active_layers:    int,
	music_recovery_count:   int,
	music_recovery_logged:  bool,
}

// raylib's AudioCallback has no user-data pointer. Only one Audio instance owns
// the process audio device; this pointer is installed before playback and
// cleared after UnloadAudioStream has synchronized with the callback.
@(private = "file")
audio_music_callback_audio: ^Audio

audio_loaded_cue_count :: proc(audio: ^Audio) -> (count: int) {
	if audio == nil do return
	for cue in Audio_Cue {
		if cue in audio.loaded do count += 1
	}
	return
}

// Resource readiness is independent of the user's enabled preference.
audio_ready_for_playback :: proc(audio: ^Audio) -> bool {
	return audio != nil && audio.ready && !audio.suspended && audio_loaded_cue_count(audio) > 0
}

audio_cue_for_sfx :: proc(kind: Sfx_Kind) -> Audio_Cue {
	switch kind {
	case .Swing:    return .Swing
	case .Hit:      return .Hit
	case .Hurt:     return .Hurt
	case .Bolt:     return .Bolt
	case .Pickup:   return .Pickup
	case .Potion:   return .Potion
	case .Level_Up: return .Level_Up
	case .Stairs:   return .Stairs
	case .Death:    return .Death
	case .Door:     return .Door
	case .Start:    return .Start
	case .Bell:     return .Bell
	case .Boss:     return .Boss
	case .Victory:  return .Victory
	case .Drink:    return .Drink
	case .Trap:     return .Trap
	case .Shrine:   return .Shrine
	case .Secret:   return .Secret
	}
	return .Swing
}

// Pure semantic routing shared by the raw platform bridge and headless tests.
// A frame emits at most one menu cue, with Back taking precedence just as it
// does in the reducer/navigation flow.
audio_cue_for_intent :: proc(intent: Intent) -> (Audio_Cue, bool) {
	if intent.back do return .Ui_Back, true
	if intent.confirm do return .Ui_Confirm, true
	if intent.menu_delta != 0 || intent.menu_horizontal != 0 || intent.tab {
		return .Ui_Navigate, true
	}
	return {}, false
}

// Starting a run already owns the authored Start cue. Suppress the generic
// confirmation for that transition so reducers can finish before any new UI
// sound begins and the opening cue is not doubled.
audio_cue_for_transition :: proc(intent: Intent, mode_before, mode_after: App_Mode) -> (Audio_Cue, bool) {
	cue, has_cue := audio_cue_for_intent(intent)
	if has_cue && cue == .Ui_Confirm && mode_before == .Select && mode_after == .Playing {
		return {}, false
	}
	return cue, has_cue
}

audio_init :: proc(audio: ^Audio) {
	if audio == nil do return
	// A repeated device init must not leak buffers or reset the saved SFX option.
	enabled := audio.enabled
	suspended := audio.suspended
	if !audio.initialized do enabled = true
	if audio.ready do audio_shutdown(audio)

	// Web decodes music during game boot, before the user gesture. Preserve that
	// device-independent PCM while resetting the device-backed audio state so the
	// unlock frame can create Web Audio immediately, while transient activation
	// is still valid.
	when ARCH_ROGUE_WEB {
		preloaded_library := audio.music_library
		preloaded_assets := audio.music_assets
		preloaded_asset_count := audio.music_asset_count
		preloaded_loop_frames := audio.music_loop_frames
		audio^ = Audio{
			enabled = enabled,
			suspended = suspended,
			initialized = true,
		}
		audio.music_library = preloaded_library
		audio.music_assets = preloaded_assets
		audio.music_asset_count = preloaded_asset_count
		audio.music_loop_frames = preloaded_loop_frames
	} else {
		audio^ = Audio{
			enabled = enabled,
			suspended = suspended,
			initialized = true,
		}
	}

	// A NativeActivity can enter main more than once while Android retains the
	// process. Reuse the process-owned backend left by a prior activity instead
	// of attempting to initialize a second device.
	if !rl.IsAudioDeviceReady() do rl.InitAudioDevice()
	if !rl.IsAudioDeviceReady() {
		platform_log(fmt.tprint("audio: no device, running silent"))
		return
	}
	audio.ready = true

	for cue in Audio_Cue {
		path := fmt.ctprintf("assets/audio/sfx/%s", AUDIO_CUE_FILES[cue])
		// Android assets live behind AAssetManager and are not POSIX paths, so
		// raylib FileExists() always reports false for a valid packaged cue.
		// LoadSound() already uses raylib's asset-aware file-data callback.
		when !ARCH_ROGUE_ANDROID {
			if !rl.FileExists(path) {
				platform_log(fmt.tprintf("audio: missing cue %s (%s)", AUDIO_CUE_KEYS[cue], path))
				continue
			}
		}
		sound := rl.LoadSound(path)
		if !rl.IsSoundValid(sound) {
			platform_log(fmt.tprintf("audio: invalid cue %s (%s)", AUDIO_CUE_KEYS[cue], path))
			continue
		}
		rl.SetSoundVolume(sound, 0.8)
		audio.sounds[cue] = sound
		audio.loaded += {cue}
	}
	when ARCH_ROGUE_WEB {
		audio_music_create_mixer(audio)
	} else {
		audio_music_load_library(audio)
	}
}

// This setting gates SFX at dispatch instead of changing raylib's master
// volume. Future music therefore remains independent from the Audio cues option.
audio_set_enabled :: proc(audio: ^Audio, enabled: bool) {
	audio.enabled = enabled
}

// Lazy web asset adoption waits for a quiet authored-SFX window. The query is
// intentionally independent of the enabled preference: a cue dispatched just
// before that option changed must still be allowed to finish.
audio_any_cue_playing :: proc(audio: ^Audio) -> bool {
	if audio == nil || !audio.ready do return false
	for cue in Audio_Cue {
		if cue not_in audio.loaded do continue
		sound := audio.sounds[cue]
		if rl.IsSoundValid(sound) && rl.IsSoundPlaying(sound) do return true
	}
	return false
}

audio_suspend :: proc(audio: ^Audio) {
	if audio == nil || audio.suspended do return
	audio.suspended = true
	if !audio.ready do return
	for cue in Audio_Cue {
		if cue not_in audio.loaded do continue
		sound := audio.sounds[cue]
		if rl.IsSoundValid(sound) && rl.IsSoundPlaying(sound) do rl.StopSound(sound)
	}
	audio_music_suspend(audio)
}

audio_resume :: proc(audio: ^Audio) {
	if audio == nil do return
	audio.suspended = false
}

audio_shutdown :: proc(audio: ^Audio) {
	if audio == nil do return
	audio_music_shutdown(audio)
	if audio.ready {
		for cue in Audio_Cue {
			if cue not_in audio.loaded do continue
			sound := audio.sounds[cue]
			if rl.IsSoundValid(sound) {
				rl.StopSound(sound)
				rl.UnloadSound(sound)
			}
		}
		// Android 17's AAudio callback can outlive miniaudio's teardown just long
		// enough to lock an already-destroyed mutex. Keep the backend process-owned:
		// a same-process NativeActivity relaunch reuses it, while process death lets
		// Android reclaim it. The game-owned sound buffers are still released above.
		when !ARCH_ROGUE_ANDROID {
			rl.CloseAudioDevice()
		}
	}
	audio.sounds = {}
	audio.loaded = {}
	audio.ready = false
}

audio_play_cue :: proc(audio: ^Audio, cue: Audio_Cue) {
	if audio == nil || !audio.ready || !audio.enabled || audio.suspended || cue not_in audio.loaded do return
	sound := audio.sounds[cue]
	if rl.IsSoundValid(sound) do rl.PlaySound(sound)
}

// Compatibility entry point for the raylib-free simulation event queue.
audio_play :: proc(audio: ^Audio, kind: Sfx_Kind) {
	audio_play_cue(audio, audio_cue_for_sfx(kind))
}

// --- live background-music mixing -------------------------------------------
// The raylib-free Music_Director owns phase and per-track envelopes. This layer
// decodes each authored OGG once, then mixes the independent PCM stems from one
// audio callback. Playback therefore performs no file I/O or codec work and is
// not serviced by the render loop.

@(private = "file")
audio_music_store_u32 :: proc "contextless" (destination: ^u32, value: u32) {
	when ARCH_ROGUE_WEB {
		// Keep one implementation surface while avoiding Wasm atomics: the web
		// audio callback and game frame execute on the same browser thread.
		_ = sync.Atomic_Memory_Order.Relaxed
		destination^ = value
	} else {
		sync.atomic_store_explicit(destination, value, .Release)
	}
}

@(private = "file")
audio_music_load_u32 :: proc "contextless" (source: ^u32) -> u32 {
	when ARCH_ROGUE_WEB {
		return source^
	} else {
		return sync.atomic_load_explicit(source, .Acquire)
	}
}

@(private = "file")
audio_music_add_u32 :: proc "contextless" (destination: ^u32, value: u32) {
	when ARCH_ROGUE_WEB {
		destination^ += value
	} else {
		sync.atomic_add_explicit(destination, value, .Relaxed)
	}
}

@(private = "file")
audio_music_store_gain :: proc "contextless" (destination: ^u32, value: f32) {
	audio_music_store_u32(destination, transmute(u32)value)
}

@(private = "file")
audio_music_load_gain :: proc "contextless" (source: ^u32) -> f32 {
	return transmute(f32)audio_music_load_u32(source)
}

audio_music_master_dsp_reset :: proc "contextless" (dsp: ^Music_Master_DSP) {
	if dsp == nil do return
	dsp^ = {limiter_gain = 1}
}

// Biased softsign saturation remains monotonic at any input level. Subtracting
// the zero-input response keeps exact silence at zero while retaining the
// asymmetry that gives the fully wet stage an audible tape-like even harmonic.
audio_music_saturate_sample :: proc "contextless" (sample: f32) -> f32 {
	driven := sample * MUSIC_SATURATION_DRIVE + MUSIC_TAPE_BIAS
	shaped := driven / (1 + abs(driven))
	bias_floor := MUSIC_TAPE_BIAS / (1 + abs(MUSIC_TAPE_BIAS))
	wet := (shaped - bias_floor) * MUSIC_TAPE_OUTPUT_GAIN
	return sample + (wet - sample) * MUSIC_SATURATION_MIX
}

// A cheap stateful tone stage precedes the waveshaper, approximating tape's
// high-frequency softening. The post-shaper DC blocker protects bass headroom
// from the deliberate transfer asymmetry without introducing lookahead.
audio_music_tape_frame :: proc "contextless" (
	dsp: ^Music_Master_DSP,
	left, right: f32,
) -> (tape_left, tape_right: f32) {
	if dsp == nil do return
	dsp.tape_tone_left += (left - dsp.tape_tone_left) * MUSIC_TAPE_TONE_ALPHA
	dsp.tape_tone_right += (right - dsp.tape_tone_right) * MUSIC_TAPE_TONE_ALPHA
	shaped_left := audio_music_saturate_sample(dsp.tape_tone_left)
	shaped_right := audio_music_saturate_sample(dsp.tape_tone_right)
	tape_left = shaped_left - dsp.tape_dc_input_left + MUSIC_TAPE_DC_BLOCK_COEFFICIENT * dsp.tape_dc_output_left
	tape_right = shaped_right - dsp.tape_dc_input_right + MUSIC_TAPE_DC_BLOCK_COEFFICIENT * dsp.tape_dc_output_right
	dsp.tape_dc_input_left = shaped_left
	dsp.tape_dc_input_right = shaped_right
	dsp.tape_dc_output_left = tape_left
	dsp.tape_dc_output_right = tape_right
	return
}

// One detector and one envelope preserve the stereo image. Attack is
// instantaneous because there is intentionally no lookahead; saturation ahead
// of the limiter softens the transient edge that this zero-latency choice can
// otherwise expose.
audio_music_limit_frame :: proc "contextless" (
	dsp: ^Music_Master_DSP,
	left, right: f32,
) -> (limited_left, limited_right: f32) {
	if dsp == nil do return
	gain := dsp.limiter_gain
	if gain <= 0 || gain > 1 do gain = 1
	gain += (1 - gain) * MUSIC_LIMITER_RELEASE_PER_FRAME
	peak := max(abs(left), abs(right))
	if peak > MUSIC_LIMITER_CEILING {
		gain = min(gain, MUSIC_LIMITER_CEILING / peak)
	}
	dsp.limiter_gain = gain
	limited_left = clamp(left * gain, -MUSIC_LIMITER_CEILING, MUSIC_LIMITER_CEILING)
	limited_right = clamp(right * gain, -MUSIC_LIMITER_CEILING, MUSIC_LIMITER_CEILING)
	return
}

@(private = "file")
audio_music_asset_index_for :: proc(audio: ^Audio, file: string) -> (int, bool) {
	if audio == nil do return 0, false
	for index in 0 ..< audio.music_asset_count {
		if audio.music_assets[index].file == file do return index, true
	}
	return 0, false
}

// Runs under raylib's audio-device mutex. It must never allocate, log, decode,
// call back into raylib, or read mutable game state. Per-layer gains and the
// common Loop cursor are the only cross-thread values and are atomic on native
// targets (the web audio callback and game frame share one browser thread).
@(private = "file")
audio_music_mix_callback :: proc "c" (buffer_data: rawptr, frames: u32) #no_bounds_check {
	output := cast([^]f32)buffer_data
	frame_count := int(frames)
	sample_count := frame_count * MUSIC_CHANNELS
	for sample_index in 0 ..< sample_count do output[sample_index] = 0

	audio := audio_music_callback_audio
	if audio == nil || audio.music_loop_frames == 0 || frame_count <= 0 do return
	cursor := int(audio_music_load_u32(&audio.music_cursor_frame))
	loop_frames := int(audio.music_loop_frames)
	// Report the start of the device block, not its already-rendered end. This
	// keeps hard musical boundaries from firing one callback period early.
	audio_music_store_u32(&audio.music_reference_frame, u32(cursor))
	// Snapshot all atomic controls before mixing. A frame may publish new gains
	// concurrently, but one callback block always uses one tightly sampled set.
	target_gains: [MUSIC_MAX_ASSETS]f32
	for asset_index in 0 ..< audio.music_asset_count {
		target_gains[asset_index] = audio_music_load_gain(&audio.music_target_gain_bits[asset_index])
	}

	master_target := clamp(audio_music_load_gain(&audio.music_master_target_bits), 0, 1)
	master_gain := audio.music_callback_master_gain
	master_step := (master_target - master_gain) / f32(frame_count)

	for asset_index in 0 ..< audio.music_asset_count {
		asset := &audio.music_assets[asset_index]
		if !asset.ready || asset.wave.data == nil do continue
		target_gain := target_gains[asset_index]
		gain := audio.music_callback_gains[asset_index]
		if target_gain == 0 && gain == 0 do continue
		gain_step := (target_gain - gain) / f32(frame_count)
		source := cast([^]i16)asset.wave.data
		source_cursor := cursor
		for frame_index in 0 ..< frame_count {
			gain += gain_step
			source_index := source_cursor * MUSIC_CHANNELS
			output_index := frame_index * MUSIC_CHANNELS
			output[output_index] += f32(source[source_index]) * (gain / 32768.0)
			output[output_index + 1] += f32(source[source_index + 1]) * (gain / 32768.0)
			source_cursor += 1
			if source_cursor >= loop_frames do source_cursor = 0
		}
		audio.music_callback_gains[asset_index] = target_gain
	}

	// Process the summed music bus before applying the user's volume preference,
	// so changing that option does not change saturation or limiter behavior.
	for frame_index in 0 ..< frame_count {
		output_index := frame_index * MUSIC_CHANNELS
		left, right := audio_music_tape_frame(
			&audio.music_master_dsp,
			output[output_index],
			output[output_index + 1],
		)
		left, right = audio_music_limit_frame(&audio.music_master_dsp, left, right)
		master_gain += master_step
		output[output_index] = left * master_gain
		output[output_index + 1] = right * master_gain
	}
	audio.music_callback_master_gain = master_target
	cursor = (cursor + frame_count) % loop_frames
	audio_music_store_u32(&audio.music_cursor_frame, u32(cursor))
	audio_music_add_u32(&audio.music_callback_count, 1)
}

@(private = "file")
audio_music_stop_mixer :: proc(audio: ^Audio) {
	if audio == nil do return
	if audio.music_stream_loaded && rl.IsAudioStreamValid(audio.music_stream) {
		if audio.music_stream_started do rl.StopAudioStream(audio.music_stream)
		rl.UnloadAudioStream(audio.music_stream)
	}
	// UnloadAudioStream synchronizes with raylib's callback before returning, so
	// decoded layers can be released safely after this pointer is cleared.
	if audio_music_callback_audio == audio do audio_music_callback_audio = nil
	audio.music_stream = {}
	audio.music_stream_loaded = false
	audio.music_stream_started = false
	audio.music_stream_paused = false
	audio.music_stage_valid = false
	audio.music_active_layers = 0
	audio.music_target_gain_bits = {}
	audio.music_published_gains = {}
	audio.music_published_valid = {}
	audio.music_callback_gains = {}
	audio.music_master_target_bits = 0
	audio.music_master_published_gain = 0
	audio.music_master_published_valid = false
	audio.music_callback_master_gain = 0
	audio.music_master_dsp = {}
	audio.music_cursor_frame = 0
	audio.music_reference_frame = 0
	audio.music_callback_count = 0
}

@(private = "file")
audio_music_unload_assets :: proc(audio: ^Audio) {
	if audio == nil do return
	for index in 0 ..< audio.music_asset_count {
		asset := &audio.music_assets[index]
		if asset.wave.data != nil do rl.UnloadWave(asset.wave)
	}
	audio.music_assets = {}
	audio.music_asset_count = 0
	audio.music_loop_frames = 0
}

@(private = "file")
audio_music_preload_assets :: proc(audio: ^Audio) {
	if audio == nil do return
	expected_frames := u32(audio.music_library.loop_ms * f64(MUSIC_SAMPLE_RATE) / 1000 + 0.5)
	audio.music_loop_frames = expected_frames
	loaded_count := 0
	decoded_bytes := 0
	for mix in audio.music_library.mixes {
		for track in mix.tracks {
			if _, found := audio_music_asset_index_for(audio, track.file); found do continue
			if audio.music_asset_count >= MUSIC_MAX_ASSETS {
				platform_log(fmt.tprintf("music: PCM layer cache full, dropping %s", track.file))
				continue
			}
			asset := &audio.music_assets[audio.music_asset_count]
			audio.music_asset_count += 1
			asset.file = track.file
			path := fmt.ctprintf("assets/audio/bgm/%s", track.file)
			data_size: i32
			data := rl.LoadFileData(path, &data_size)
			if data == nil || data_size <= 0 {
				if data != nil do rl.UnloadFileData(data)
				platform_log(fmt.tprintf("music: missing track %s", track.file))
				continue
			}
			wave := rl.LoadWaveFromMemory(".ogg", data, data_size)
			rl.UnloadFileData(data)
			if !rl.IsWaveValid(wave) {
				platform_log(fmt.tprintf("music: invalid track %s", track.file))
				continue
			}
			if wave.sampleRate != MUSIC_SAMPLE_RATE || wave.sampleSize != MUSIC_SAMPLE_SIZE || wave.channels != MUSIC_CHANNELS {
				rl.WaveFormat(&wave, MUSIC_SAMPLE_RATE, MUSIC_SAMPLE_SIZE, MUSIC_CHANNELS)
			}
			if !rl.IsWaveValid(wave) || wave.sampleRate != MUSIC_SAMPLE_RATE || wave.sampleSize != MUSIC_SAMPLE_SIZE || wave.channels != MUSIC_CHANNELS {
				platform_log(fmt.tprintf("music: could not convert %s to 48 kHz stereo PCM16", track.file))
				if wave.data != nil do rl.UnloadWave(wave)
				continue
			}
			if wave.frameCount != expected_frames {
				platform_log(fmt.tprintf(
					"music: %s length %d frames, expected %d for %.0f ms; dropping track",
					track.file, wave.frameCount, expected_frames, audio.music_library.loop_ms,
				))
				rl.UnloadWave(wave)
				continue
			}
			asset.wave = wave
			asset.ready = true
			loaded_count += 1
			decoded_bytes += int(wave.frameCount * wave.channels * (wave.sampleSize / 8))
		}
	}
	platform_log(fmt.tprintf(
		"music: decoded %d/%d live stems (%d KiB PCM)",
		loaded_count, audio.music_asset_count, decoded_bytes / 1024,
	))
}

@(private = "file")
audio_music_create_mixer :: proc(audio: ^Audio) {
	if audio == nil || audio.music_loop_frames == 0 do return
	has_layer := false
	for index in 0 ..< audio.music_asset_count do has_layer = has_layer || audio.music_assets[index].ready
	if !has_layer do return
	stream := rl.LoadAudioStream(MUSIC_SAMPLE_RATE, 32, MUSIC_CHANNELS)
	if !rl.IsAudioStreamValid(stream) {
		platform_log(fmt.tprint("music: could not create live mixer stream"))
		return
	}
	audio.music_stream = stream
	audio.music_stream_loaded = true
	audio_music_master_dsp_reset(&audio.music_master_dsp)
	audio_music_callback_audio = audio
	rl.SetAudioStreamCallback(stream, audio_music_mix_callback)
}

// Load the composer document and decode every referenced OGG through raylib's
// asset-aware file reader. This works with Android's AAssetManager and the web
// preload filesystem without relying on POSIX paths. Decoding is deliberately
// separate from creating the device-backed mixer so web can finish this
// main-thread work before starting its main-thread audio callback.
@(private = "file")
audio_music_preload_library :: proc(audio: ^Audio) {
	if audio == nil do return
	audio_music_stop_mixer(audio)
	audio_music_unload_assets(audio)
	music_library_destroy(&audio.music_library)
	data_size: i32
	raw := rl.LoadFileData(MUSIC_MIXES_DOCUMENT_PATH, &data_size)
	if raw == nil || data_size <= 0 {
		if raw != nil do rl.UnloadFileData(raw)
		platform_log(fmt.tprintf("music: missing %s, staying silent", MUSIC_MIXES_DOCUMENT_PATH))
		return
	}
	defer rl.UnloadFileData(raw)
	library, ok := music_library_parse(raw[:data_size])
	if !ok {
		platform_log(fmt.tprintf("music: malformed %s, staying silent", MUSIC_MIXES_DOCUMENT_PATH))
		return
	}
	audio.music_library = library
	audio_music_preload_assets(audio)
	platform_log(fmt.tprintf(
		"music: library loaded (%d mixes, loop %.0f ms)",
		len(library.mixes), library.loop_ms,
	))
}

// Web calls this during ordinary game boot, before Web Audio is gesture-unlocked,
// so expensive OGG decoding cannot starve the first live callback.
audio_preload_music :: proc(audio: ^Audio) {
	audio_music_preload_library(audio)
}

@(private = "file")
audio_music_load_library :: proc(audio: ^Audio) {
	audio_music_preload_library(audio)
	audio_music_create_mixer(audio)
}

@(private = "file")
audio_music_publish_targets :: proc(
	audio: ^Audio,
	director: ^Music_Director,
	runtime: Music_Runtime_State,
) {
	gains: [MUSIC_MAX_ASSETS]f32
	for &state in director.slots {
		if !state.active do continue
		if asset_index, found := audio_music_asset_index_for(audio, state.file); found && audio.music_assets[asset_index].ready {
			runtime_gain := music_track_runtime_gain(state.authored, runtime)
			gains[asset_index] = clamp(state.volume * runtime_gain, 0, 1)
		}
		// Every PCM layer advances on the common callback cursor even while
		// inaudible, so an entering layer is already at state.seek_ms.
		state.start_pending = false
	}
	audio.music_active_layers = 0
	for asset_index in 0 ..< audio.music_asset_count {
		gain := gains[asset_index]
		if !audio.music_published_valid[asset_index] || abs(audio.music_published_gains[asset_index] - gain) > 0.0001 {
			audio_music_store_gain(&audio.music_target_gain_bits[asset_index], gain)
			audio.music_published_gains[asset_index] = gain
			audio.music_published_valid[asset_index] = true
		}
		if gain > 0.0005 do audio.music_active_layers += 1
	}
}

@(private = "file")
audio_music_publish_master :: proc(audio: ^Audio, master_volume: f32) {
	gain := clamp(master_volume, 0, 1)
	if !audio.music_master_published_valid || abs(audio.music_master_published_gain - gain) > 0.0001 {
		audio_music_store_gain(&audio.music_master_target_bits, gain)
		audio.music_master_published_gain = gain
		audio.music_master_published_valid = true
	}
}

@(private = "file")
audio_music_set_cursor :: proc(audio: ^Audio, phase_ms: f64) {
	if audio.music_loop_frames == 0 do return
	phase := max(phase_ms, 0)
	frame := u32(phase * f64(MUSIC_SAMPLE_RATE) / 1000 + 0.5)
	frame %= audio.music_loop_frames
	audio_music_store_u32(&audio.music_cursor_frame, frame)
	audio_music_store_u32(&audio.music_reference_frame, frame)
}

// Safe only while the callback stream is stopped or paused. It prevents a
// synthetic fade from the previous mix when playback starts or the boot epoch
// performs its authored hard reset.
@(private = "file")
audio_music_adopt_targets :: proc(audio: ^Audio) {
	for asset_index in 0 ..< audio.music_asset_count {
		audio.music_callback_gains[asset_index] = audio_music_load_gain(&audio.music_target_gain_bits[asset_index])
	}
	audio.music_callback_master_gain = clamp(audio_music_load_gain(&audio.music_master_target_bits), 0, 1)
	audio_music_master_dsp_reset(&audio.music_master_dsp)
}

@(private = "file")
audio_music_start_mixer :: proc(audio: ^Audio, phase_ms: f64) {
	audio_music_set_cursor(audio, phase_ms)
	audio_music_adopt_targets(audio)
	rl.PlayAudioStream(audio.music_stream)
	audio.music_stream_started = true
	audio.music_stream_paused = false
}

audio_music_loaded_stream_count :: proc(audio: ^Audio) -> int {
	if audio != nil && audio.music_stream_loaded && audio.music_stream_started do return 1
	return 0
}

audio_music_active_layer_count :: proc(audio: ^Audio) -> int {
	if audio == nil do return 0
	return audio.music_active_layers
}

audio_music_callback_service_count :: proc(audio: ^Audio) -> u32 {
	if audio == nil do return 0
	return audio_music_load_u32(&audio.music_callback_count)
}

// Publish the director's independent per-stem gains. The only raylib calls in
// steady playback are a cheap health query; decoding and buffer refills are no
// longer performed on the render thread.
audio_music_update :: proc(
	audio: ^Audio,
	director: ^Music_Director,
	master_volume: f32,
	runtime: Music_Runtime_State = {},
) {
	if audio == nil || director == nil || !audio.ready || !audio.music_stream_loaded do return
	phase_ms := music_phase_ms(director, &audio.music_library)
	start_phase_ms := phase_ms
	for state in director.slots {
		if state.active && state.start_pending {
			start_phase_ms = state.seek_ms
			break
		}
	}
	audio_music_publish_targets(audio, director, runtime)
	audio_music_publish_master(audio, master_volume)
	if master_volume <= 0 {
		if audio.music_stream_started {
			rl.StopAudioStream(audio.music_stream)
			audio.music_stream_started = false
			audio.music_stream_paused = false
		}
		audio.music_stage_valid = false
		return
	}
	if audio.suspended {
		audio_music_suspend(audio)
		return
	}

	if !audio.music_stream_started {
		audio_music_start_mixer(audio, start_phase_ms)
		audio.music_stage = director.stage
		audio.music_stage_valid = true
		return
	}

	// The boot hand-off resets the Loop epoch. Pause under raylib's audio lock,
	// reset the one shared cursor, then resume; ordinary mix changes never seek.
	if audio.music_stage_valid && audio.music_stage != director.stage {
		if !audio.music_stream_paused {
			rl.PauseAudioStream(audio.music_stream)
			audio.music_stream_paused = true
		}
		audio_music_set_cursor(audio, phase_ms)
		audio_music_adopt_targets(audio)
		rl.ResumeAudioStream(audio.music_stream)
		audio.music_stream_paused = false
	} else if audio.music_stream_paused {
		rl.ResumeAudioStream(audio.music_stream)
		audio.music_stream_paused = false
	}
	audio.music_stage = director.stage
	audio.music_stage_valid = true

	if !rl.IsAudioStreamPlaying(audio.music_stream) {
		if !audio.music_recovery_logged {
			platform_log(fmt.tprint("music: recovering stopped live mixer"))
			audio.music_recovery_logged = true
		}
		audio.music_recovery_count += 1
		audio_music_start_mixer(audio, phase_ms)
	}
}

// The callback cursor advances exactly as PCM is requested by the audio device,
// so it disciplines Loop boundaries without render-time or decoder jitter.
audio_music_reference_phase_ms :: proc(audio: ^Audio, director: ^Music_Director) -> f64 {
	if audio == nil || director == nil || !audio.ready || audio.suspended ||
	   !audio.music_stream_started || audio.music_stream_paused {
		return -1
	}
	frame := audio_music_load_u32(&audio.music_reference_frame)
	return f64(frame) * 1000 / f64(MUSIC_SAMPLE_RATE)
}

// Freeze the shared cursor for lifecycle suspension. Resume is deferred to the
// normal frame update, after the platform has restored interactivity.
audio_music_suspend :: proc(audio: ^Audio) {
	if audio == nil || !audio.music_stream_loaded || !audio.music_stream_started || audio.music_stream_paused do return
	rl.PauseAudioStream(audio.music_stream)
	audio.music_stream_paused = true
}

audio_music_shutdown :: proc(audio: ^Audio) {
	if audio == nil do return
	audio_music_stop_mixer(audio)
	audio_music_unload_assets(audio)
	music_library_destroy(&audio.music_library)
}

// Drain the sim's event queue, playing each kind at most once per frame so a
// multishot volley or crowd swing doesn't stack into a blowout.
audio_drain :: proc(audio: ^Audio, run: ^Run) {
	if run == nil do return
	if audio == nil || audio.suspended {
		clear(&run.sfx)
		return
	}
	seen: bit_set[Sfx_Kind]
	for kind in run.sfx {
		if kind in seen do continue
		seen += {kind}
		audio_play(audio, kind)
	}
	clear(&run.sfx)
}
