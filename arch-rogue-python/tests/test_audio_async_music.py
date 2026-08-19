from __future__ import annotations

import hashlib
import os
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from arch_rogue.audio import AudioSystem, MusicProfile  # noqa: E402


def wait_until(predicate: object, timeout: float = 1.5) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if callable(predicate) and predicate():
            return True
        time.sleep(0.005)
    return False


class AsyncMusicTests(unittest.TestCase):
    @staticmethod
    def make_profile(*, depth: int = 3, seed: int = 7) -> MusicProfile:
        return MusicProfile(
            seed,
            "Rogue",
            "Obsidian Vault",
            "Cursed",
            depth=depth,
        )

    @staticmethod
    def make_audible_audio() -> AudioSystem:
        audio = AudioSystem()
        audio.available = True
        audio.music_channel = mock.Mock()
        audio.music_channel.get_busy.return_value = False
        return audio

    def test_cache_miss_returns_immediately_and_promotes_on_owner_thread(
        self,
    ) -> None:
        audio = self.make_audible_audio()
        self.addCleanup(audio.shutdown)
        profile = self.make_profile()
        synthesis_started = threading.Event()
        release_synthesis = threading.Event()
        synthesis_thread: list[int] = []
        owner_thread = threading.get_ident()
        sound = mock.Mock()

        def slow_synthesis(
            _profile: MusicProfile, _cancelled: object = None
        ) -> bytes:
            synthesis_thread.append(threading.get_ident())
            synthesis_started.set()
            release_synthesis.wait(1.0)
            return b"\x00\x00" * 32

        def make_sound(*, buffer: bytes) -> mock.Mock:
            self.assertEqual(threading.get_ident(), owner_thread)
            self.assertEqual(buffer, b"\x00\x00" * 32)
            return sound

        with (
            mock.patch.object(
                audio, "_synthesize_music_pcm", side_effect=slow_synthesis
            ),
            mock.patch("arch_rogue.audio.pygame.mixer.Sound", side_effect=make_sound),
        ):
            started_at = time.perf_counter()
            self.assertTrue(audio.play_run_music(profile))
            call_ms = (time.perf_counter() - started_at) * 1000.0
            self.assertLess(call_ms, 50.0)
            self.assertTrue(synthesis_started.wait(0.5))
            audio.music_channel.play.assert_not_called()

            release_synthesis.set()
            self.assertTrue(
                wait_until(lambda: audio._music_ready_result is not None)
            )
            self.assertTrue(audio.play_run_music(profile))

        self.assertEqual(len(synthesis_thread), 1)
        self.assertNotEqual(synthesis_thread[0], owner_thread)
        audio.music_channel.play.assert_called_once_with(
            sound, loops=-1, fade_ms=650
        )

    def test_profile_change_discards_stale_completed_generation(self) -> None:
        audio = self.make_audible_audio()
        self.addCleanup(audio.shutdown)
        first = self.make_profile(depth=1)
        latest = self.make_profile(depth=8)
        first_started = threading.Event()
        release_first = threading.Event()
        generated_depths: list[int] = []
        promoted_frames: list[bytes] = []

        def coalesced_synthesis(
            profile: MusicProfile, _cancelled: object = None
        ) -> bytes:
            generated_depths.append(profile.depth)
            if profile.depth == first.depth:
                first_started.set()
                release_first.wait(1.0)
            return bytes((profile.depth, 0)) * 16

        def make_sound(*, buffer: bytes) -> mock.Mock:
            promoted_frames.append(buffer)
            return mock.Mock()

        with (
            mock.patch.object(
                audio, "_synthesize_music_pcm", side_effect=coalesced_synthesis
            ),
            mock.patch("arch_rogue.audio.pygame.mixer.Sound", side_effect=make_sound),
        ):
            audio.play_run_music(first)
            self.assertTrue(first_started.wait(0.5))
            audio.play_run_music(latest)
            release_first.set()
            latest_key = audio._profile_seed(latest)
            self.assertTrue(
                wait_until(
                    lambda: (
                        audio._music_ready_result is not None
                        and audio._music_ready_result.key == latest_key
                    )
                )
            )
            audio.play_run_music(latest)

        self.assertEqual(generated_depths, [first.depth, latest.depth])
        self.assertEqual(promoted_frames, [bytes((latest.depth, 0)) * 16])

    def test_return_to_current_track_cancels_unneeded_transition_job(self) -> None:
        audio = self.make_audible_audio()
        self.addCleanup(audio.shutdown)
        current = self.make_profile(depth=2)
        detour = self.make_profile(depth=7)
        audio.current_music_seed = audio._profile_seed(current)
        audio.music_channel.get_busy.return_value = True
        synthesis_started = threading.Event()
        cancellation_seen = threading.Event()

        def cancellable_synthesis(
            _profile: MusicProfile, cancelled: object
        ) -> bytes:
            synthesis_started.set()
            while callable(cancelled) and not cancelled():
                time.sleep(0.002)
            cancellation_seen.set()
            return b"stale"

        with mock.patch.object(
            audio, "_synthesize_music_pcm", side_effect=cancellable_synthesis
        ):
            audio.play_run_music(detour)
            self.assertTrue(synthesis_started.wait(0.5))
            audio.play_run_music(current)
            self.assertTrue(cancellation_seen.wait(0.5))

        self.assertIsNone(audio._music_desired_key)
        self.assertIsNone(audio._music_ready_result)
        audio.music_channel.play.assert_not_called()

    def test_generation_failure_keeps_prior_track_and_does_not_retry_spin(
        self,
    ) -> None:
        audio = self.make_audible_audio()
        self.addCleanup(audio.shutdown)
        profile = self.make_profile()
        audio.current_music_seed = 12345
        generation_calls = 0

        def failed_synthesis(
            _profile: MusicProfile, _cancelled: object = None
        ) -> bytes:
            nonlocal generation_calls
            generation_calls += 1
            raise ValueError("synthetic test failure")

        with mock.patch.object(
            audio, "_synthesize_music_pcm", side_effect=failed_synthesis
        ):
            audio.play_run_music(profile)
            self.assertTrue(
                wait_until(lambda: audio._music_ready_result is not None)
            )
            self.assertTrue(audio.play_run_music(profile))
            self.assertTrue(audio.play_run_music(profile))

        self.assertTrue(audio.available)
        self.assertEqual(audio.current_music_seed, 12345)
        self.assertEqual(generation_calls, 1)
        audio.music_channel.play.assert_not_called()

    def test_music_disabled_never_starts_background_generation(self) -> None:
        audio = self.make_audible_audio()
        self.addCleanup(audio.shutdown)

        with mock.patch.object(audio, "_request_music_generation") as request:
            self.assertTrue(audio.play_run_music(self.make_profile(), enabled=False))

        request.assert_not_called()
        self.assertIsNone(audio._music_worker)


class MusicCacheTests(unittest.TestCase):
    def test_music_cache_is_bounded_lru(self) -> None:
        audio = AudioSystem(music_cache_limit=3)
        sounds = [mock.Mock() for _ in range(4)]
        for key, sound in enumerate(sounds[:3]):
            audio._cache_music(key, sound)

        self.assertIs(audio._cached_music(0), sounds[0])
        audio._cache_music(3, sounds[3])

        self.assertEqual(list(audio.music_cache), [2, 0, 3])
        self.assertNotIn(1, audio.music_cache)

    def test_low_memory_clears_caches_and_cancels_pending_pcm(self) -> None:
        audio = AudioSystem()
        self.addCleanup(audio.shutdown)
        audio.available = True
        audio.music_channel = mock.Mock()
        audio.music_channel.get_busy.return_value = False
        audio.sfx_cache["hit"] = mock.Mock()
        audio.music_cache[123] = mock.Mock()
        synthesis_started = threading.Event()
        cancellation_seen = threading.Event()

        def cancellable_synthesis(
            _profile: MusicProfile, cancelled: object
        ) -> bytes:
            synthesis_started.set()
            while callable(cancelled) and not cancelled():
                time.sleep(0.002)
            cancellation_seen.set()
            return b"stale"

        with mock.patch.object(
            audio, "_synthesize_music_pcm", side_effect=cancellable_synthesis
        ):
            audio.play_run_music(AsyncMusicTests.make_profile())
            self.assertTrue(synthesis_started.wait(0.5))
            audio.clear_memory_caches()
            self.assertTrue(cancellation_seen.wait(0.5))

        self.assertEqual(audio.sfx_cache, {})
        self.assertEqual(audio.music_cache, {})
        self.assertIsNone(audio._music_desired_key)
        self.assertIsNone(audio._music_ready_result)


class MusicPcmCompatibilityTests(unittest.TestCase):
    def test_async_pcm_matches_pre_optimization_tracks_exactly(self) -> None:
        audio = AudioSystem()
        run_frames = audio._synthesize_run_track_pcm(
            AsyncMusicTests.make_profile(depth=1)
        )
        menu_frames = audio._synthesize_static_menu_pcm()

        self.assertEqual(
            hashlib.sha256(run_frames).hexdigest(),
            "357ca2a25726b7f0ab1637c5218f53d520b5f672f57d58790e32400b617d4dae",
        )
        self.assertEqual(
            hashlib.sha256(menu_frames).hexdigest(),
            "373388b6692d0f6f1cd48c3a8b65a8066d10c3f94bad79a48d45ce05352be2f5",
        )


if __name__ == "__main__":
    unittest.main()
