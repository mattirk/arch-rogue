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
	// boot intro. Each ten-second cycle covers Menu→Dungeon (both proximity
	// stems)→Boss→Boss Battle (Alasin, all guitar tiers, and choir)→Dungeon.
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
	seen_glorious_zero, seen_glorious_half, seen_glorious_full := false, false, false
	seen_quest_zero, seen_quest_half, seen_quest_full := false, false, false
	seen_choir_zero, seen_choir_half, seen_choir_full := false, false, false
	glorious_gain, quest_harp_gain, bar_gain, choir_gain: f32

	for {
		now_ms := f64(time.tick_now()._nsec) / 1e6
		elapsed_ms := now_ms - start_ms
		if elapsed_ms >= f64(seconds) * 1000 do break
		dt_ms := max(0, now_ms - previous_ms)
		previous_ms = now_ms
		segment_ms := int(elapsed_ms) % 10_000
		desired := ar.MUSIC_MIX_MENU
		runtime: ar.Music_Runtime_State
		glorious_target, quest_harp_target, bar_target, choir_target: f32
		tier_elapsed_ms := 0
		if segment_ms >= 1_000 && segment_ms < 2_500 {
			desired = ar.MUSIC_MIX_DUNGEON
			if segment_ms >= 2_000 {
				glorious_target = 1
				quest_harp_target = 1
			} else if segment_ms >= 1_500 {
				glorious_target = 0.5
				quest_harp_target = 0.5
			}
		} else if segment_ms >= 2_500 && segment_ms < 4_000 {
			desired = ar.MUSIC_MIX_BOSS
		} else if segment_ms >= 4_000 && segment_ms < 8_500 {
			desired = ar.MUSIC_MIX_BOSS_BATTLE
			if segment_ms >= 5_000 do choir_target = 1
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
			runtime.boss_guitar_tier = .High
			glorious_target = 1
			quest_harp_target = 1
			if segment_ms >= 9_000 do bar_target = 1
		}
		glorious_fade := glorious_target < glorious_gain ? ar.MUSIC_ELITE_HORN_RELEASE_SECONDS : ar.MUSIC_ELITE_HORN_ATTACK_SECONDS
		glorious_gain = ar.music_gain_slew(
			glorious_gain,
			glorious_target,
			f32(dt_ms / 1000),
			glorious_fade,
		)
		quest_harp_gain = ar.music_gain_slew(
			quest_harp_gain,
			quest_harp_target,
			f32(dt_ms / 1000),
			ar.MUSIC_QUEST_HARP_FADE_SECONDS,
		)
		bar_gain = ar.music_gain_slew(
			bar_gain,
			bar_target,
			f32(dt_ms / 1000),
			ar.MUSIC_BAR_FADE_SECONDS,
		)
		choir_gain = ar.music_gain_slew(
			choir_gain,
			choir_target,
			f32(dt_ms / 1000),
			ar.MUSIC_BOSS_CHOIR_FADE_SECONDS,
		)
		runtime.boss_choir_gain = choir_gain
		runtime.dungeon_elite_horn_gain = glorious_gain
		runtime.dungeon_quest_harp_gain = quest_harp_gain
		runtime.dungeon_bar_gain = bar_gain

		reference_ms := ar.audio_music_reference_phase_ms(&audio, &director)
		ar.music_director_update(&director, &audio.music_library, desired, dt_ms, reference_ms)
		ar.audio_music_update(&audio, &director, 1, runtime)

		streams := ar.audio_music_loaded_stream_count(&audio)
		max_streams = max(max_streams, streams)
		layers := ar.audio_music_active_layer_count(&audio)
		max_layers = max(max_layers, layers)
		if desired == ar.MUSIC_MIX_DUNGEON {
			if runtime.dungeon_elite_horn_gain <= 0.0005 && runtime.dungeon_quest_harp_gain <= 0.0005 && layers == 5 {
				seen_glorious_zero = true
				seen_quest_zero = true
			}
			if abs(runtime.dungeon_elite_horn_gain - 0.5) < 0.001 &&
			   abs(runtime.dungeon_quest_harp_gain - 0.5) < 0.001 && layers == 7 {
				seen_glorious_half = true
				seen_quest_half = true
			}
			if runtime.dungeon_elite_horn_gain == 1 && runtime.dungeon_quest_harp_gain == 1 && layers == 7 {
				seen_glorious_full = true
				seen_quest_full = true
			}
		}
		if desired == ar.MUSIC_MIX_BOSS_BATTLE {
			if segment_ms >= 4_600 && runtime.boss_choir_gain <= 0.0005 && layers == 4 do seen_choir_zero = true
			if 0.4 < runtime.boss_choir_gain && runtime.boss_choir_gain < 0.6 && layers == 5 do seen_choir_half = true
			if runtime.boss_choir_gain == 1 && layers == 5 do seen_choir_full = true
		}
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
		max_layers == 11 && int(callback_count) > seconds * 20 && frames > seconds * 40 &&
		guitar_exclusivity_failures == 0 && seen_low && seen_mid && seen_high &&
		seen_glorious_zero && seen_glorious_half && seen_glorious_full &&
		seen_quest_zero && seen_quest_half && seen_quest_full &&
		seen_choir_zero && seen_choir_half && seen_choir_full
	fmt.printf(
		"AUDIO_SOAK {{\"seconds\":%d,\"frames\":%d,\"max_streams\":%d,\"max_layers\":%d,\"callbacks\":%d,\"recoveries\":%d,\"stalls\":%d,\"guitar_exclusivity_failures\":%d,\"seen_low\":%v,\"seen_mid\":%v,\"seen_high\":%v,\"seen_glorious_zero\":%v,\"seen_glorious_half\":%v,\"seen_glorious_full\":%v,\"seen_quest_zero\":%v,\"seen_quest_half\":%v,\"seen_quest_full\":%v,\"seen_choir_zero\":%v,\"seen_choir_half\":%v,\"seen_choir_full\":%v,\"passed\":%v}}\n",
		seconds, frames, max_streams, max_layers, callback_count, audio.music_recovery_count, stalls,
		guitar_exclusivity_failures, seen_low, seen_mid, seen_high,
		seen_glorious_zero, seen_glorious_half, seen_glorious_full,
		seen_quest_zero, seen_quest_half, seen_quest_full,
		seen_choir_zero, seen_choir_half, seen_choir_full, passed,
	)
	if !passed do os.exit(1)
}
