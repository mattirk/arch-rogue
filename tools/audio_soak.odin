package main

// Real-device music soak using the production director and raylib playback.
// Run from the repository root:
//   odin run tools/audio_soak.odin -file -out:build/audio_soak
// Optional: ARCH_ROGUE_AUDIO_SOAK_SECONDS=60 (default 25, clamped 10..120).

import "core:fmt"
import "core:os"
import "core:strconv"
import "core:time"
import ar "../src"

main :: proc() {
	seconds := 25
	if text := os.get_env("ARCH_ROGUE_AUDIO_SOAK_SECONDS", context.temp_allocator); text != "" {
		if parsed, ok := strconv.parse_int(text); ok do seconds = clamp(parsed, 10, 120)
	}

	audio: ar.Audio
	ar.audio_init(&audio)
	defer ar.audio_shutdown(&audio)
	if !audio.ready || !audio.music_library.loaded {
		fmt.eprintln("AUDIO_SOAK failed: audio device or music library unavailable")
		os.exit(1)
	}

	// Exercise every music route without spending 9.6 seconds in the authored
	// boot intro. Each ten-second cycle covers Menu→Dungeon→Boss→Boss Battle,
	// all three health-driven guitar tiers, then Boss Battle→Dungeon.
	audio.music_library.has_boot = false
	director: ar.Music_Director
	start_ms := f64(time.tick_now()._nsec) / 1e6
	previous_ms := start_ms
	last_phase := f64(-1)
	last_progress_ms := start_ms
	max_streams := 0
	max_layers := 0
	callback_start := ar.audio_music_callback_service_count(&audio)
	frames := 0
	stalls := 0
	guitar_exclusivity_failures := 0
	seen_low, seen_mid, seen_high := false, false, false

	for {
		now_ms := f64(time.tick_now()._nsec) / 1e6
		elapsed_ms := now_ms - start_ms
		if elapsed_ms >= f64(seconds) * 1000 do break
		dt_ms := max(0, now_ms - previous_ms)
		previous_ms = now_ms
		segment_ms := int(elapsed_ms) % 10_000
		desired := ar.MUSIC_MIX_MENU
		runtime: ar.Music_Runtime_State
		tier_elapsed_ms := 0
		if segment_ms >= 1_000 && segment_ms < 2_500 {
			desired = ar.MUSIC_MIX_DUNGEON
		} else if segment_ms >= 2_500 && segment_ms < 4_000 {
			desired = ar.MUSIC_MIX_BOSS
		} else if segment_ms >= 4_000 && segment_ms < 8_500 {
			desired = ar.MUSIC_MIX_BOSS_BATTLE
			if segment_ms < 5_500 {
				runtime.boss_guitar_tier = .Low
				tier_elapsed_ms = segment_ms - 4_000
			} else if segment_ms < 7_000 {
				runtime.boss_guitar_tier = .Mid
				tier_elapsed_ms = segment_ms - 5_500
			} else {
				runtime.boss_guitar_tier = .High
				tier_elapsed_ms = segment_ms - 7_000
			}
		} else if segment_ms >= 8_500 {
			desired = ar.MUSIC_MIX_DUNGEON
		}

		reference_ms := ar.audio_music_reference_phase_ms(&audio, &director)
		ar.music_director_update(&director, &audio.music_library, desired, dt_ms, reference_ms)
		ar.audio_music_update(&audio, &director, 1, runtime)

		streams := ar.audio_music_loaded_stream_count(&audio)
		max_streams = max(max_streams, streams)
		max_layers = max(max_layers, ar.audio_music_active_layer_count(&audio))
		if desired == ar.MUSIC_MIX_BOSS_BATTLE && tier_elapsed_ms >= 600 {
			audible_guitars := 0
			for state in director.slots {
				if state.file != "lead_guitar_low.ogg" && state.file != "lead_guitar_mid.ogg" &&
				   state.file != "lead_guitar_high.ogg" {
					continue
				}
				gain := state.volume * ar.music_track_runtime_gain(state.authored, runtime)
				if gain <= 0.5 do continue
				audible_guitars += 1
				if state.file == "lead_guitar_low.ogg" do seen_low = true
				if state.file == "lead_guitar_mid.ogg" do seen_mid = true
				if state.file == "lead_guitar_high.ogg" do seen_high = true
			}
			if audible_guitars != 1 do guitar_exclusivity_failures += 1
		}
		phase := ar.audio_music_reference_phase_ms(&audio, &director)
		if phase >= 0 {
			if last_phase < 0 {
				last_progress_ms = now_ms
			} else {
				diff := phase - last_phase
				half_loop := audio.music_library.loop_ms * 0.5
				if diff > half_loop do diff -= audio.music_library.loop_ms
				if diff < -half_loop do diff += audio.music_library.loop_ms
				if abs(diff) >= 1 do last_progress_ms = now_ms
			}
			last_phase = phase
		}
		if now_ms - last_progress_ms > 500 {
			stalls += 1
			last_progress_ms = now_ms
		}
		frames += 1
		time.sleep(16 * time.Millisecond)
	}

	callback_count := ar.audio_music_callback_service_count(&audio) - callback_start
	passed := stalls == 0 && audio.music_recovery_count == 0 && max_streams == 1 &&
		max_layers == 7 && int(callback_count) > seconds * 20 && frames > seconds * 40 &&
		guitar_exclusivity_failures == 0 && seen_low && seen_mid && seen_high
	fmt.printf(
		"AUDIO_SOAK {{\"seconds\":%d,\"frames\":%d,\"max_streams\":%d,\"max_layers\":%d,\"callbacks\":%d,\"recoveries\":%d,\"stalls\":%d,\"guitar_exclusivity_failures\":%d,\"seen_low\":%v,\"seen_mid\":%v,\"seen_high\":%v,\"passed\":%v}}\n",
		seconds, frames, max_streams, max_layers, callback_count, audio.music_recovery_count, stalls,
		guitar_exclusivity_failures, seen_low, seen_mid, seen_high, passed,
	)
	if !passed do os.exit(1)
}
