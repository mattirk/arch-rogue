package archrogue

// Authored sound-effect playback. The runtime never synthesizes audio and
// missing/invalid files degrade to silence. Music deliberately has no slots or
// lifecycle here yet: incoming authored tracks will get their own specification.

import "core:fmt"
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

Audio :: struct {
	sounds:      [Audio_Cue]rl.Sound,
	loaded:      bit_set[Audio_Cue],
	ready:       bool,
	enabled:     bool,
	suspended:   bool,
	initialized: bool,
}

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
	audio^ = Audio{
		enabled = enabled,
		suspended = suspended,
		initialized = true,
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
		path := fmt.ctprintf("assets/audio/%s", AUDIO_CUE_FILES[cue])
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
}

audio_resume :: proc(audio: ^Audio) {
	if audio == nil do return
	audio.suspended = false
}

audio_shutdown :: proc(audio: ^Audio) {
	if audio == nil do return
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
