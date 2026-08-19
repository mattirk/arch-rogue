package archrogue_tests

// MX-android — pure lifecycle and fixed-step contracts. Platform callbacks are
// reduced to declarative effects so tests need no Activity, window, audio device,
// renderer, wall clock, or raylib linkage.

import "core:math"
import "core:testing"
import ar "../src"

@(private = "file")
mx_android_expect_suspend_effects :: proc(t: ^testing.T, result: ar.Mobile_Lifecycle_Result) {
	testing.expect(t, ar.Mobile_Lifecycle_Effect.Cancel_Touches in result.effects, "suspend must cancel touch ownership")
	testing.expect(t, ar.Mobile_Lifecycle_Effect.Clear_Play_Input in result.effects, "suspend must clear latched app input")
	testing.expect(t, ar.Mobile_Lifecycle_Effect.Freeze_Simulation in result.effects, "suspend must freeze fixed-step simulation")
	testing.expect(t, ar.Mobile_Lifecycle_Effect.Pause_Audio in result.effects, "suspend must pause audio")
	testing.expect(t, ar.Mobile_Lifecycle_Effect.Reset_Accumulator in result.effects, "suspend must discard accumulated frame time")
}

@(test)
mx_android_pause_requests_one_bounded_checkpoint_and_resume_veil :: proc(t: ^testing.T) {
	state := ar.mobile_lifecycle_init(.Playing)
	testing.expect(t, ar.mobile_lifecycle_interactive(&state))

	paused := ar.mobile_lifecycle_reduce(&state, .Pause, true, .Playing)
	mx_android_expect_suspend_effects(t, paused)
	testing.expect(t, ar.Mobile_Lifecycle_Effect.Request_Checkpoint in paused.effects, "live descent must request a checkpoint")
	testing.expect(t, ar.Mobile_Lifecycle_Effect.Flush_Checkpoint_Bounded in paused.effects, "background flush must be bounded")
	testing.expect(t, state.suspended && !ar.mobile_lifecycle_interactive(&state))
	testing.expect(t, state.resume_return == .Playing && state.resume_veil_due)

	// Home/recents often emits focus loss and Stop after Pause. They are one
	// suspension boundary and must not duplicate saves, releases, or audio work.
	focus_lost := ar.mobile_lifecycle_reduce(&state, .Focus_Lost, true, .Playing)
	stopped := ar.mobile_lifecycle_reduce(&state, .Stop, true, .Playing)
	testing.expect(t, focus_lost.effects == {}, "focus loss after Pause must be idempotent")
	testing.expect(t, stopped.effects == {}, "Stop after Pause must be idempotent")

	// Resume alone is insufficient while focus is still absent.
	resumed_without_focus := ar.mobile_lifecycle_reduce(&state, .Resume, true, .Playing)
	testing.expect(t, resumed_without_focus.effects == {} && state.suspended)
	resumed := ar.mobile_lifecycle_reduce(&state, .Focus_Gained, true, .Playing)
	testing.expect(t, resumed.effects == {
		ar.Mobile_Lifecycle_Effect.Reset_Accumulator,
		ar.Mobile_Lifecycle_Effect.Refresh_Insets,
		ar.Mobile_Lifecycle_Effect.Show_Resume_Veil,
	}, "resume must preserve the audio device and return through the continue veil")
	testing.expect(t, ar.Mobile_Lifecycle_Effect.Request_Checkpoint not_in resumed.effects)
	testing.expect(t, resumed.resume_return == .Playing)
	testing.expect(t, !state.suspended && ar.mobile_lifecycle_interactive(&state))

	// A later background cycle is a new boundary and may request one new save.
	paused_again := ar.mobile_lifecycle_reduce(&state, .Pause, true, .Playing)
	testing.expect(t, ar.Mobile_Lifecycle_Effect.Request_Checkpoint in paused_again.effects)
}

@(test)
mx_android_focus_loss_without_live_descent_has_no_save_or_veil :: proc(t: ^testing.T) {
	state := ar.mobile_lifecycle_init(.Title)
	lost := ar.mobile_lifecycle_reduce(&state, .Focus_Lost, false, .Title)
	mx_android_expect_suspend_effects(t, lost)
	testing.expect(t, ar.Mobile_Lifecycle_Effect.Request_Checkpoint not_in lost.effects)
	testing.expect(t, ar.Mobile_Lifecycle_Effect.Flush_Checkpoint_Bounded not_in lost.effects)
	testing.expect(t, !state.resume_veil_due)

	gained := ar.mobile_lifecycle_reduce(&state, .Focus_Gained, false, .Title)
	testing.expect(t, ar.Mobile_Lifecycle_Effect.Refresh_Insets in gained.effects)
	testing.expect(t, ar.Mobile_Lifecycle_Effect.Show_Resume_Veil not_in gained.effects, "title/menu focus restore needs no run veil")
	testing.expect(t, gained.resume_return == .Title)
}

@(test)
mx_android_surface_loss_recreates_graphics_once_after_all_resume_gates :: proc(t: ^testing.T) {
	state := ar.mobile_lifecycle_init(.Playing)
	lost := ar.mobile_lifecycle_reduce(&state, .Surface_Lost, true, .Playing)
	mx_android_expect_suspend_effects(t, lost)
	testing.expect(t, ar.Mobile_Lifecycle_Effect.Invalidate_Graphics in lost.effects)
	testing.expect(t, state.resources_lost && !state.surface_ready)

	// Screen lock may add Pause while the surface is already gone. Neither it nor
	// a duplicate surface callback may repeat the checkpoint/invalidation edge.
	pause := ar.mobile_lifecycle_reduce(&state, .Pause, true, .Playing)
	lost_again := ar.mobile_lifecycle_reduce(&state, .Surface_Lost, true, .Playing)
	testing.expect(t, pause.effects == {})
	testing.expect(t, lost_again.effects == {})

	// Focus/Activity resume while the surface is absent must remain frozen.
	resume := ar.mobile_lifecycle_reduce(&state, .Resume, true, .Playing)
	testing.expect(t, resume.effects == {} && state.suspended)
	restored := ar.mobile_lifecycle_reduce(&state, .Surface_Restored, true, .Playing)
	testing.expect(t, restored.effects == {
		ar.Mobile_Lifecycle_Effect.Recreate_Graphics,
		ar.Mobile_Lifecycle_Effect.Refresh_Insets,
		ar.Mobile_Lifecycle_Effect.Reset_Accumulator,
		ar.Mobile_Lifecycle_Effect.Show_Resume_Veil,
	}, "surface restore must rebuild graphics without touching the audio device")
	testing.expect(t, !state.resources_lost && state.surface_ready && !state.suspended)

	duplicate_restore := ar.mobile_lifecycle_reduce(&state, .Surface_Restored, true, .Playing)
	testing.expect(t, duplicate_restore.effects == {}, "duplicate surface restore must not recreate resources")
}

@(test)
mx_android_repeated_suspend_resume_preserves_process_audio :: proc(t: ^testing.T) {
	state := ar.mobile_lifecycle_init(.Playing)
	for _ in 0 ..< 8 {
		paused := ar.mobile_lifecycle_reduce(&state, .Pause, true, .Playing)
		mx_android_expect_suspend_effects(t, paused)

		resumed := ar.mobile_lifecycle_reduce(&state, .Resume, true, .Playing)
		testing.expect(t, resumed.effects == {
			ar.Mobile_Lifecycle_Effect.Reset_Accumulator,
			ar.Mobile_Lifecycle_Effect.Refresh_Insets,
			ar.Mobile_Lifecycle_Effect.Show_Resume_Veil,
		}, "every resume cycle must leave the process-owned audio device intact")
		testing.expect(t, ar.mobile_lifecycle_interactive(&state))
	}
	testing.expect(t, state.generation == 16, "each suspend and resume boundary must advance once")
}

@(test)
mx_android_low_memory_drops_only_reconstructible_caches :: proc(t: ^testing.T) {
	state := ar.mobile_lifecycle_init(.Paused)
	before := state
	result := ar.mobile_lifecycle_reduce(&state, .Low_Memory, true, .Paused)
	testing.expect(t, result.effects == {ar.Mobile_Lifecycle_Effect.Drop_Reconstructible_Caches})
	testing.expect(t, state.focused == before.focused)
	testing.expect(t, state.resumed == before.resumed)
	testing.expect(t, state.surface_ready == before.surface_ready)
	testing.expect(t, state.destroyed == before.destroyed)
	testing.expect(t, state.suspended == before.suspended)
	testing.expect(t, state.resources_lost == before.resources_lost)
	testing.expect(t, state.resume_return == before.resume_return)
	testing.expect(t, state.generation == before.generation + 1)
	testing.expect(t, ar.Mobile_Lifecycle_Effect.Request_Checkpoint not_in result.effects, "low memory must not invent persistence work")
}

@(test)
mx_android_activity_destroy_is_terminal_and_idempotent :: proc(t: ^testing.T) {
	state := ar.mobile_lifecycle_init(.Options)
	destroyed := ar.mobile_lifecycle_reduce(&state, .Destroy, true, .Options)
	mx_android_expect_suspend_effects(t, destroyed)
	testing.expect(t, ar.Mobile_Lifecycle_Effect.Request_Checkpoint in destroyed.effects)
	testing.expect(t, ar.Mobile_Lifecycle_Effect.Flush_Checkpoint_Bounded in destroyed.effects)
	testing.expect(t, ar.Mobile_Lifecycle_Effect.Invalidate_Graphics in destroyed.effects, "direct destroy must not rely on a prior surface callback")
	testing.expect(t, state.destroyed && state.resources_lost && !ar.mobile_lifecycle_interactive(&state))
	testing.expect(t, state.resume_return == .Options, "resume veil must remember the nested app surface")

	destroyed_again := ar.mobile_lifecycle_reduce(&state, .Destroy, true, .Options)
	testing.expect(t, destroyed_again.effects == {}, "duplicate activity destruction must be side-effect free")
	_ = ar.mobile_lifecycle_reduce(&state, .Surface_Restored, true, .Options)
	_ = ar.mobile_lifecycle_reduce(&state, .Resume, true, .Options)
	_ = ar.mobile_lifecycle_reduce(&state, .Focus_Gained, true, .Options)
	testing.expect(t, !ar.mobile_lifecycle_interactive(&state), "destroyed activity must never become interactive again")
}

@(test)
mx_android_fixed_step_freezes_resets_and_discards_stale_resume_dt :: proc(t: ^testing.T) {
	state := ar.Mobile_Fixed_Step_State{accumulator = .008}
	steps := ar.mobile_fixed_step_advance(&state, .5, .01, .05, false)
	testing.expect(t, steps == 0 && state.accumulator == 0, "suspended frames must neither tick nor retain time")

	ar.mobile_fixed_step_reset(&state, discard_next_dt = true)
	testing.expect(t, state.accumulator == 0 && state.discard_next_dt)
	steps = ar.mobile_fixed_step_advance(&state, .25, .01, .05, true)
	testing.expect(t, steps == 0 && state.accumulator == 0 && !state.discard_next_dt, "first post-resume frame time must be discarded")

	steps = ar.mobile_fixed_step_advance(&state, .021, .01, .05, true)
	testing.expect(t, steps == 2, "fresh frame time must resume fixed 10ms steps")
	testing.expectf(t, math.abs(state.accumulator - .001) < 1e-5, "accumulator was %.6f, want .001", state.accumulator)

	state = {}
	steps = ar.mobile_fixed_step_advance(&state, .5, .01, .025, true)
	testing.expect(t, steps == 2, "frame clamp must bound catch-up work")
	testing.expectf(t, math.abs(state.accumulator - .005) < 1e-5, "clamped remainder was %.6f", state.accumulator)

	before := state.accumulator
	steps = ar.mobile_fixed_step_advance(&state, -1, .01, .025, true)
	testing.expect(t, steps == 0 && state.accumulator == before, "negative frame time must not advance simulation")
}
