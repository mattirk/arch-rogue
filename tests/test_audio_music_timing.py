from __future__ import annotations

import os
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest import mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from arch_rogue.audio import (  # noqa: E402
    SAMPLE_RATE,
    AudioSystem,
    MusicProfile,
    MusicTiming,
    MusicTrackSpec,
)


class MusicTrackSpecTests(unittest.TestCase):
    def test_music_value_objects_are_frozen(self) -> None:
        spec = MusicTrackSpec(
            tempo=120.0,
            steps=32,
            steps_per_beat=2,
            step_seconds=0.25,
            total_samples=SAMPLE_RATE * 8,
            loop_seconds=8.0,
        )
        timing = MusicTiming(
            total_beats=5.25,
            loop_beat=5.25,
            beat_index=5,
            beat_phase=0.25,
            phrase_index=1,
        )

        self.assertEqual(spec.beats_per_loop, 16)
        self.assertEqual(
            timing,
            MusicTiming(
                total_beats=5.25,
                loop_beat=5.25,
                beat_index=5,
                beat_phase=0.25,
                phrase_index=1,
            ),
        )
        with self.assertRaises(FrozenInstanceError):
            setattr(spec, "tempo", 90.0)
        with self.assertRaises(FrozenInstanceError):
            setattr(timing, "beat_index", 6)

    def test_run_tempo_formula_scales_with_depth_and_caps(self) -> None:
        audio = AudioSystem()
        depths = (-3, 0, 1, 2, 5, 20)

        for seed in range(4):
            for depth in depths:
                with self.subTest(seed=seed, depth=depth):
                    profile = MusicProfile(
                        seed,
                        "Rogue",
                        "Crypt",
                        "Cursed",
                        depth=depth,
                    )
                    expected = float(
                        min(
                            138,
                            74
                            + (seed % 4) * 3
                            + (max(1, depth) - 1) * 4,
                        )
                    )
                    self.assertEqual(audio.music_track_spec(profile).tempo, expected)

    def test_run_spec_is_exactly_32_eighth_notes_and_16_beats(self) -> None:
        audio = AudioSystem()
        profile = MusicProfile(2, "Arcanist", "Violet", "Arcane", depth=4)
        spec = audio.music_track_spec(profile)
        expected_step_seconds = 60.0 / spec.tempo / 2
        expected_samples = int(32 * expected_step_seconds * SAMPLE_RATE)

        self.assertIsInstance(spec, MusicTrackSpec)
        self.assertEqual(spec.steps, 32)
        self.assertEqual(spec.steps_per_beat, 2)
        self.assertEqual(spec.beats_per_loop, 16)
        self.assertAlmostEqual(spec.step_seconds, expected_step_seconds)
        self.assertEqual(spec.total_samples, expected_samples)
        self.assertEqual(spec.loop_seconds, expected_samples / SAMPLE_RATE)
        self.assertLess(
            abs(spec.loop_seconds - 32 * spec.step_seconds),
            1.0 / SAMPLE_RATE,
        )

        self.assertEqual(
            audio.music_timing(profile, now=0.0),
            MusicTiming(0.0, 0.0, 0, 0.0, 0),
        )
        wrapped = audio.music_timing(profile, now=spec.loop_seconds)
        self.assertAlmostEqual(wrapped.total_beats, 16.0)
        self.assertAlmostEqual(wrapped.loop_beat, 0.0)
        self.assertEqual(wrapped.beat_index, 16)
        self.assertAlmostEqual(wrapped.beat_phase, 0.0)
        self.assertEqual(wrapped.phrase_index, 4)

    def test_menu_spec_is_static_58_bpm_16_beat_loop(self) -> None:
        audio = AudioSystem()
        profile = MusicProfile(
            0xA11CE,
            "Menu",
            "Main Menu",
            "Quiet",
            depth=99,
            mood="menu",
        )
        spec = audio.music_track_spec(profile)
        expected_step_seconds = 60.0 / 58.0
        expected_samples = int(16 * expected_step_seconds * SAMPLE_RATE)

        self.assertEqual(spec.tempo, 58.0)
        self.assertEqual(spec.steps, 16)
        self.assertEqual(spec.steps_per_beat, 1)
        self.assertEqual(spec.beats_per_loop, 16)
        self.assertAlmostEqual(spec.step_seconds, expected_step_seconds)
        self.assertEqual(spec.total_samples, expected_samples)
        self.assertEqual(spec.loop_seconds, expected_samples / SAMPLE_RATE)


class MusicTransportTests(unittest.TestCase):
    @staticmethod
    def make_profile(*, depth: int = 3, modifier: str = "Cursed") -> MusicProfile:
        return MusicProfile(
            7,
            "Rogue",
            "Obsidian Vault",
            modifier,
            depth=depth,
        )

    def test_music_timing_reports_phase_phrase_and_loop_position(self) -> None:
        audio = AudioSystem()
        profile = self.make_profile()
        spec = audio.music_track_spec(profile)
        beat_seconds = spec.loop_seconds / spec.beats_per_loop
        started_at = 100.0

        initial = audio.music_timing(profile, now=started_at)
        self.assertIsInstance(initial, MusicTiming)
        self.assertEqual(initial, MusicTiming(0.0, 0.0, 0, 0.0, 0))

        timing = audio.music_timing(
            profile,
            now=started_at + beat_seconds * 18.5,
        )
        self.assertAlmostEqual(timing.total_beats, 18.5, places=9)
        self.assertAlmostEqual(timing.loop_beat, 2.5, places=9)
        self.assertEqual(timing.beat_index, 18)
        self.assertAlmostEqual(timing.beat_phase, 0.5, places=9)
        self.assertEqual(timing.phrase_index, 4)

    def test_none_profile_and_uninitialized_transport_return_zero_timing(self) -> None:
        audio = AudioSystem()
        zero = MusicTiming(0.0, 0.0, 0, 0.0, 0)

        self.assertEqual(audio.music_timing(None, now=123.0), zero)
        self.assertEqual(audio.current_music_timing(now=456.0), zero)

    def test_muted_unavailable_audio_keeps_virtual_transport_running(self) -> None:
        audio = AudioSystem()
        profile = self.make_profile()
        spec = audio.music_track_spec(profile)
        beat_seconds = spec.loop_seconds / spec.beats_per_loop
        started_at = 250.0

        self.assertFalse(audio.available)
        self.assertFalse(audio.play_run_music(profile, enabled=True, now=started_at))
        checkpoint = started_at + beat_seconds * 3.25
        self.assertFalse(audio.play_run_music(profile, enabled=False, now=checkpoint))

        timing = audio.current_music_timing(now=checkpoint)
        self.assertAlmostEqual(timing.total_beats, 3.25, places=9)
        self.assertAlmostEqual(timing.loop_beat, 3.25, places=9)
        self.assertEqual(timing.beat_index, 3)
        self.assertAlmostEqual(timing.beat_phase, 0.25, places=9)
        self.assertEqual(audio.music_cache, {})
        self.assertIsNone(audio.music_channel)
        self.assertIsNone(audio.current_music_seed)

    def test_same_profile_sync_does_not_reset_transport(self) -> None:
        audio = AudioSystem()
        profile = self.make_profile()
        equivalent_profile = self.make_profile()
        spec = audio.music_track_spec(profile)
        beat_seconds = spec.loop_seconds / spec.beats_per_loop
        started_at = 400.0

        self.assertFalse(audio.sync_music(profile, enabled=False, now=started_at))
        resync_at = started_at + beat_seconds * 5.5
        self.assertFalse(
            audio.sync_music(equivalent_profile, enabled=False, now=resync_at)
        )

        timing = audio.current_music_timing(now=resync_at)
        self.assertAlmostEqual(timing.total_beats, 5.5, places=9)
        self.assertEqual(timing.beat_index, 5)
        self.assertAlmostEqual(timing.beat_phase, 0.5, places=9)

    def test_profile_change_resets_transport_at_explicit_time(self) -> None:
        audio = AudioSystem()
        first_profile = self.make_profile(depth=1)
        changed_profile = self.make_profile(depth=6)
        first_spec = audio.music_track_spec(first_profile)
        first_beat_seconds = first_spec.loop_seconds / first_spec.beats_per_loop
        started_at = 600.0

        self.assertFalse(
            audio.play_run_music(first_profile, enabled=False, now=started_at)
        )
        changed_at = started_at + first_beat_seconds * 7.75
        before_change = audio.current_music_timing(now=changed_at)
        self.assertAlmostEqual(before_change.total_beats, 7.75, places=9)

        self.assertFalse(
            audio.play_run_music(changed_profile, enabled=False, now=changed_at)
        )
        self.assertEqual(
            audio.current_music_timing(now=changed_at),
            MusicTiming(0.0, 0.0, 0, 0.0, 0),
        )

        changed_spec = audio.music_track_spec(changed_profile)
        changed_beat_seconds = changed_spec.loop_seconds / changed_spec.beats_per_loop
        after_change = audio.current_music_timing(
            now=changed_at + changed_beat_seconds * 2.25
        )
        self.assertAlmostEqual(after_change.total_beats, 2.25, places=9)
        self.assertEqual(after_change.beat_index, 2)
        self.assertAlmostEqual(after_change.beat_phase, 0.25, places=9)

    def test_audible_transport_stamps_downbeat_after_channel_start(self) -> None:
        audio = AudioSystem()
        profile = self.make_profile()
        music_key = audio._profile_seed(profile)
        audio.available = True
        audio.music_cache[music_key] = mock.Mock()
        audio.music_channel = mock.Mock()
        audio.music_channel.get_busy.return_value = False
        spec = audio.music_track_spec(profile)
        beat_seconds = spec.loop_seconds / spec.beats_per_loop

        with mock.patch(
            "arch_rogue.audio.time.monotonic",
            side_effect=(100.0, 100.25, 100.25 + beat_seconds * 2.5),
        ):
            self.assertTrue(audio.play_run_music(profile, enabled=True))
            downbeat = audio.current_music_timing()

        self.assertAlmostEqual(downbeat.total_beats, 2.5, places=9)
        self.assertEqual(downbeat.beat_index, 2)
        self.assertAlmostEqual(downbeat.beat_phase, 0.5, places=9)
        audio.music_channel.play.assert_called_once()

    def test_switching_clock_domains_restarts_virtual_transport(self) -> None:
        audio = AudioSystem()
        profile = self.make_profile()
        spec = audio.music_track_spec(profile)
        beat_seconds = spec.loop_seconds / spec.beats_per_loop

        audio.music_timing(profile, now=10.0)
        before_switch = audio.music_timing(
            profile, now=10.0 + beat_seconds * 3.0
        )
        self.assertAlmostEqual(before_switch.total_beats, 3.0, places=9)

        with mock.patch("arch_rogue.audio.time.monotonic", return_value=500.0):
            switched = audio.music_timing(profile)
        self.assertEqual(switched, MusicTiming(0.0, 0.0, 0, 0.0, 0))

    def test_syncing_no_profile_clears_transport(self) -> None:
        audio = AudioSystem()
        profile = self.make_profile()

        self.assertFalse(audio.sync_music(profile, enabled=False, now=800.0))
        self.assertFalse(audio.sync_music(None, enabled=False, now=900.0))
        self.assertEqual(
            audio.current_music_timing(now=1000.0),
            MusicTiming(0.0, 0.0, 0, 0.0, 0),
        )
        self.assertEqual(
            audio.music_timing(profile, now=1000.0),
            MusicTiming(0.0, 0.0, 0, 0.0, 0),
        )


if __name__ == "__main__":
    unittest.main()
