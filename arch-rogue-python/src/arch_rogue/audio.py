# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
#
# AI Provenance & Liability Notice:
# This repository contains code generated, assisted, or refactored by Artificial
# Intelligence models. Provided strictly "AS IS" under Apache 2.0 with no warranty
# of clean IP provenance or non-infringement; downstream users assume all legal
# and financial risk and should perform their own compliance audits.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import math
import random
import struct
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

import pygame

SAMPLE_RATE = 22050
SFX_AMPLITUDE = 3600
MUSIC_AMPLITUDE = 2300
MUSIC_CACHE_LIMIT = 6
MUSIC_WORKER_IDLE_SECONDS = 5.0


@dataclass(frozen=True)
class MusicProfile:
    seed: int
    archetype_name: str
    theme_name: str
    modifier_name: str
    depth: int = 1
    mood: str = "run"


@dataclass(frozen=True, slots=True)
class MusicTrackSpec:
    tempo: float
    steps: int
    steps_per_beat: int
    step_seconds: float
    total_samples: int
    loop_seconds: float

    @property
    def beats_per_loop(self) -> int:
        return self.steps // self.steps_per_beat


@dataclass(frozen=True, slots=True)
class MusicTiming:
    total_beats: float
    loop_beat: float
    beat_index: int
    beat_phase: float
    phrase_index: int


class _MusicGenerationCancelled(Exception):
    """Internal cooperative-cancellation signal for PCM synthesis."""


@dataclass(frozen=True, slots=True)
class _MusicGenerationJob:
    serial: int
    key: int
    profile: MusicProfile
    cancelled: threading.Event


@dataclass(frozen=True, slots=True)
class _MusicGenerationResult:
    serial: int
    key: int
    frames: bytes | None
    failed: bool = False


class AudioSystem:
    """Procedural audio manager for SFX and run-specific chiptune music."""

    def __init__(self, *, music_cache_limit: int = MUSIC_CACHE_LIMIT) -> None:
        self.available = False
        self.sfx_cache: dict[str, pygame.mixer.Sound] = {}
        self.music_cache: OrderedDict[int, pygame.mixer.Sound] = OrderedDict()
        self.music_cache_limit = max(1, int(music_cache_limit))
        self.music_channel: pygame.mixer.Channel | None = None
        self.current_music_seed: int | None = None
        self._music_transport_key: int | None = None
        self._music_transport_started_at = 0.0
        self._music_transport_spec: MusicTrackSpec | None = None
        self._music_transport_uses_explicit_clock: bool | None = None
        self.suspended = False
        self._suspended_at = 0.0
        # PCM synthesis is pure Python and may take hundreds of milliseconds.
        # A single daemon worker coalesces rapid profile changes. It never calls
        # pygame: Sound construction and channel ownership stay on this object's
        # owner thread when play_run_music() promotes a completed byte buffer.
        self._music_worker_lock = threading.Lock()
        self._music_worker_wakeup = threading.Event()
        self._music_worker_stop = threading.Event()
        self._music_worker: threading.Thread | None = None
        self._music_job_serial = 0
        self._music_desired_key: int | None = None
        self._music_queued_job: _MusicGenerationJob | None = None
        self._music_active_job: _MusicGenerationJob | None = None
        self._music_ready_result: _MusicGenerationResult | None = None
        self._music_generation_failed_key: int | None = None

    def initialize(self, headless: bool) -> bool:
        if headless:
            self.available = False
            return False
        try:
            mixer_format = pygame.mixer.get_init()
            if mixer_format and mixer_format != (SAMPLE_RATE, -16, 1):
                pygame.mixer.quit()
                mixer_format = None
            if not mixer_format:
                pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=1)
            pygame.mixer.set_num_channels(max(8, pygame.mixer.get_num_channels()))
            self.music_channel = pygame.mixer.Channel(
                pygame.mixer.get_num_channels() - 1
            )
        except pygame.error:
            self.available = False
            return False
        self.available = True
        return True

    def play_sfx(self, name: str, enabled: bool = True) -> bool:
        if self.suspended:
            return self.available
        if not enabled or not self.available:
            return self.available
        try:
            sound = self.sfx_cache.get(name)
            if sound is None:
                frequency = {
                    "start": 330,
                    "pickup": 660,
                    "hit": 190,
                    "damage": 150,
                    "trap": 96,
                    "bell": 744,
                    "secret": 612,
                    "shrine": 520,
                    "drink": 285,
                    "boss": 88,
                    "stairs": 430,
                    "victory": 784,
                    "death": 120,
                }.get(name, 440)
                duration = 0.16 if name in {"boss", "victory", "death", "bell"} else 0.08
                sound = self.make_tone(frequency, duration)
                self.sfx_cache[name] = sound
            sound.play()
        except pygame.error:
            self.available = False
        return self.available

    def make_tone(self, frequency: int, duration: float) -> pygame.mixer.Sound:
        sample_count = max(1, int(SAMPLE_RATE * duration))
        frames = bytearray()
        for index in range(sample_count):
            fade = 1.0 - index / sample_count
            value = int(
                math.sin(math.tau * frequency * index / SAMPLE_RATE)
                * SFX_AMPLITUDE
                * fade
            )
            frames.extend(struct.pack("<h", value))
        return pygame.mixer.Sound(buffer=bytes(frames))

    def music_track_spec(self, profile: MusicProfile) -> MusicTrackSpec:
        if profile.mood == "menu":
            tempo = 58.0
            steps = 16
            steps_per_beat = 1
        else:
            depth = max(1, profile.depth)
            base_tempo = 74 + (profile.seed % 4) * 3
            tempo = float(min(138, base_tempo + (depth - 1) * 4))
            steps = 32
            steps_per_beat = 2
        step_seconds = 60.0 / tempo / steps_per_beat
        total_samples = int(steps * step_seconds * SAMPLE_RATE)
        return MusicTrackSpec(
            tempo=tempo,
            steps=steps,
            steps_per_beat=steps_per_beat,
            step_seconds=step_seconds,
            total_samples=total_samples,
            loop_seconds=total_samples / SAMPLE_RATE,
        )

    def _clock_value(self, now: float | None) -> float:
        return time.monotonic() if now is None else float(now)

    def _reset_music_transport(
        self, profile: MusicProfile, now: float, uses_explicit_clock: bool
    ) -> None:
        self._music_transport_key = self._profile_seed(profile)
        self._music_transport_started_at = now
        self._music_transport_spec = self.music_track_spec(profile)
        self._music_transport_uses_explicit_clock = uses_explicit_clock

    def _sync_music_transport(
        self, profile: MusicProfile, now: float, uses_explicit_clock: bool
    ) -> None:
        if (
            self._music_transport_key != self._profile_seed(profile)
            or self._music_transport_uses_explicit_clock != uses_explicit_clock
        ):
            self._reset_music_transport(profile, now, uses_explicit_clock)

    def music_timing(
        self, profile: MusicProfile | None, now: float | None = None
    ) -> MusicTiming:
        if profile is None:
            return MusicTiming(0.0, 0.0, 0, 0.0, 0)
        uses_explicit_clock = now is not None
        clock = self._clock_value(now)
        self._sync_music_transport(profile, clock, uses_explicit_clock)
        spec = self._music_transport_spec or self.music_track_spec(profile)
        beat_seconds = spec.loop_seconds / max(1, spec.beats_per_loop)
        total_beats = max(0.0, clock - self._music_transport_started_at) / beat_seconds
        loop_beat = total_beats % spec.beats_per_loop
        beat_index = int(total_beats)
        return MusicTiming(
            total_beats=total_beats,
            loop_beat=loop_beat,
            beat_index=beat_index,
            beat_phase=total_beats - beat_index,
            phrase_index=beat_index // 4,
        )

    def current_music_timing(self, now: float | None = None) -> MusicTiming:
        spec = self._music_transport_spec
        uses_explicit_clock = now is not None
        if (
            self._music_transport_key is None
            or spec is None
            or self._music_transport_uses_explicit_clock != uses_explicit_clock
        ):
            return MusicTiming(0.0, 0.0, 0, 0.0, 0)
        clock = self._clock_value(now)
        beat_seconds = spec.loop_seconds / max(1, spec.beats_per_loop)
        total_beats = max(0.0, clock - self._music_transport_started_at) / beat_seconds
        loop_beat = total_beats % spec.beats_per_loop
        beat_index = int(total_beats)
        return MusicTiming(
            total_beats=total_beats,
            loop_beat=loop_beat,
            beat_index=beat_index,
            beat_phase=total_beats - beat_index,
            phrase_index=beat_index // 4,
        )

    def _cached_music(self, music_key: int) -> pygame.mixer.Sound | None:
        sound = self.music_cache.get(music_key)
        if sound is not None:
            self.music_cache.move_to_end(music_key)
        return sound

    def _cache_music(self, music_key: int, sound: pygame.mixer.Sound) -> None:
        self.music_cache.pop(music_key, None)
        self.music_cache[music_key] = sound
        while len(self.music_cache) > self.music_cache_limit:
            self.music_cache.popitem(last=False)

    def _request_music_generation(
        self, profile: MusicProfile, music_key: int
    ) -> None:
        worker_to_start: threading.Thread | None = None
        with self._music_worker_lock:
            if (
                self._music_desired_key == music_key
                and self._music_generation_failed_key == music_key
            ):
                return
            if self._music_desired_key == music_key and any(
                candidate is not None and candidate.key == music_key
                for candidate in (
                    self._music_queued_job,
                    self._music_active_job,
                    self._music_ready_result,
                )
            ):
                return

            self._music_job_serial += 1
            if self._music_queued_job is not None:
                self._music_queued_job.cancelled.set()
            if self._music_active_job is not None:
                self._music_active_job.cancelled.set()
            self._music_ready_result = None
            self._music_generation_failed_key = None
            self._music_desired_key = music_key
            self._music_queued_job = _MusicGenerationJob(
                self._music_job_serial,
                music_key,
                profile,
                threading.Event(),
            )
            if self._music_worker is None or not self._music_worker.is_alive():
                worker_to_start = threading.Thread(
                    target=self._music_worker_main,
                    name="arch-rogue-music",
                    daemon=True,
                )
                self._music_worker = worker_to_start

        if worker_to_start is not None:
            try:
                worker_to_start.start()
            except RuntimeError:
                # A failed worker startup leaves audio usable. The current track
                # continues (or the game remains silent) until another profile
                # change gives synthesis a fresh opportunity.
                with self._music_worker_lock:
                    queued = self._music_queued_job
                    self._music_queued_job = None
                    self._music_worker = None
                    if queued is not None and queued.key == music_key:
                        self._music_ready_result = _MusicGenerationResult(
                            queued.serial,
                            queued.key,
                            None,
                            failed=True,
                        )
                return
        self._music_worker_wakeup.set()

    def _music_worker_main(self) -> None:
        current_thread = threading.current_thread()
        worker_job_serial: int | None = None
        try:
            while not self._music_worker_stop.is_set():
                if not self._music_worker_wakeup.wait(MUSIC_WORKER_IDLE_SECONDS):
                    with self._music_worker_lock:
                        if self._music_queued_job is None:
                            if self._music_worker is current_thread:
                                self._music_worker = None
                            return
                    continue
                if self._music_worker_stop.is_set():
                    return

                with self._music_worker_lock:
                    job = self._music_queued_job
                    self._music_queued_job = None
                    self._music_worker_wakeup.clear()
                    if job is not None:
                        self._music_active_job = job
                if job is None:
                    continue
                worker_job_serial = job.serial

                try:
                    frames = self._synthesize_music_pcm(
                        job.profile, job.cancelled.is_set
                    )
                    result = _MusicGenerationResult(job.serial, job.key, frames)
                except _MusicGenerationCancelled:
                    result = None
                except Exception:
                    # Generation failure is local to this profile. Do not disable
                    # the mixer or replace a still-playing prior track.
                    result = _MusicGenerationResult(
                        job.serial,
                        job.key,
                        None,
                        failed=True,
                    )

                with self._music_worker_lock:
                    if (
                        self._music_active_job is not None
                        and self._music_active_job.serial == job.serial
                    ):
                        self._music_active_job = None
                    if (
                        result is not None
                        and not job.cancelled.is_set()
                        and self._music_desired_key == job.key
                        and self._music_job_serial == job.serial
                    ):
                        self._music_ready_result = result
                    if self._music_queued_job is not None:
                        self._music_worker_wakeup.set()
        finally:
            with self._music_worker_lock:
                if self._music_worker is current_thread:
                    self._music_worker = None
                if (
                    self._music_active_job is not None
                    and self._music_active_job.serial == worker_job_serial
                ):
                    self._music_active_job = None

    def _promote_ready_music(
        self, music_key: int
    ) -> pygame.mixer.Sound | None:
        with self._music_worker_lock:
            result = self._music_ready_result
            if result is None or result.key != music_key:
                return None
            self._music_ready_result = None
            if result.failed or result.frames is None:
                self._music_generation_failed_key = music_key
                return None
            frames = result.frames

        # This method is reached only from sync_music()/play_run_music() on the
        # game thread. The worker deliberately returns bytes, never SDL objects.
        sound = pygame.mixer.Sound(buffer=frames)
        self._cache_music(music_key, sound)
        return sound

    def _cancel_music_generation(self) -> None:
        with self._music_worker_lock:
            if (
                self._music_desired_key is None
                and self._music_queued_job is None
                and self._music_active_job is None
                and self._music_ready_result is None
                and self._music_generation_failed_key is None
            ):
                return
            self._music_job_serial += 1
            if self._music_queued_job is not None:
                self._music_queued_job.cancelled.set()
            if self._music_active_job is not None:
                self._music_active_job.cancelled.set()
            self._music_queued_job = None
            self._music_ready_result = None
            self._music_desired_key = None
            self._music_generation_failed_key = None

    def clear_memory_caches(self) -> None:
        """Release rebuildable audio data after an Android low-memory signal."""

        self._cancel_music_generation()
        self.sfx_cache.clear()
        self.music_cache.clear()

    def shutdown(self) -> None:
        """Stop background synthesis without waiting on normal track duration."""

        self._cancel_music_generation()
        self._music_worker_stop.set()
        self._music_worker_wakeup.set()
        worker = self._music_worker
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=0.25)

    def play_run_music(
        self,
        profile: MusicProfile,
        enabled: bool = True,
        now: float | None = None,
    ) -> bool:
        uses_explicit_clock = now is not None
        clock = self._clock_value(now)
        self._sync_music_transport(profile, clock, uses_explicit_clock)
        if self.suspended:
            return self.available
        if not enabled or not self.available:
            self._stop_music_output()
            return self.available
        try:
            music_key = self._profile_seed(profile)
            if self.current_music_seed == music_key and self.music_channel:
                if self.music_channel.get_busy():
                    if self._music_desired_key is not None:
                        self._cancel_music_generation()
                    return self.available
            sound = self._cached_music(music_key)
            if sound is None:
                sound = self._promote_ready_music(music_key)
            if sound is None:
                self._request_music_generation(profile, music_key)
                return self.available
            self._cancel_music_generation()
            channel = self.music_channel or sound.play(loops=-1)
            if self.music_channel:
                self.music_channel.play(sound, loops=-1, fade_ms=650)
            self.music_channel = channel
            self.current_music_seed = music_key
            # A newly-started Sound channel always begins at its downbeat. Sample
            # the clock after synthesis/channel startup so generation time cannot
            # create an immediate animation offset.
            started_at = self._clock_value(now)
            self._reset_music_transport(profile, started_at, uses_explicit_clock)
        except pygame.error:
            self.available = False
        return self.available

    def _stop_music_output(self) -> None:
        self._cancel_music_generation()
        if self.music_channel:
            try:
                self.music_channel.fadeout(300)
            except pygame.error:
                self.available = False
        self.current_music_seed = None

    def stop_music(self) -> None:
        self._stop_music_output()
        self._music_transport_key = None
        self._music_transport_started_at = 0.0
        self._music_transport_spec = None
        self._music_transport_uses_explicit_clock = None

    def suspend(self) -> None:
        if self.suspended:
            return
        self.suspended = True
        self._suspended_at = time.monotonic()
        self._cancel_music_generation()
        if not self.available:
            return
        try:
            pygame.mixer.pause()
        except pygame.error:
            self.available = False

    def resume(self) -> None:
        if not self.suspended:
            return
        paused_for = max(0.0, time.monotonic() - self._suspended_at)
        self.suspended = False
        self._suspended_at = 0.0
        if self._music_transport_uses_explicit_clock is False:
            self._music_transport_started_at += paused_for
        if not self.available:
            return
        try:
            pygame.mixer.unpause()
        except pygame.error:
            self.available = False

    def sync_music(
        self,
        profile: MusicProfile | None,
        enabled: bool,
        now: float | None = None,
    ) -> bool:
        if profile is None:
            self.stop_music()
            return self.available
        return self.play_run_music(profile, enabled, now)

    def generate_run_track(self, profile: MusicProfile) -> pygame.mixer.Sound:
        """Synchronously build a Sound for tools and compatibility callers."""

        return pygame.mixer.Sound(buffer=self._synthesize_run_track_pcm(profile))

    def _synthesize_music_pcm(
        self,
        profile: MusicProfile,
        cancelled: Callable[[], bool] | None = None,
    ) -> bytes:
        if profile.mood == "menu":
            return self._synthesize_static_menu_pcm(cancelled)
        return self._synthesize_run_track_pcm(profile, cancelled)

    def _synthesize_run_track_pcm(
        self,
        profile: MusicProfile,
        cancelled: Callable[[], bool] | None = None,
    ) -> bytes:
        self._raise_if_music_generation_cancelled(cancelled)
        rng = random.Random(self._profile_seed(profile))
        depth = max(1, profile.depth)
        dread = min(1.0, 0.42 + (depth - 1) / 11.0)
        theme_dread = (
            0.08
            if any(
                word in profile.theme_name
                for word in ("Crypt", "Violet", "Frozen", "Obsidian", "Thornbound")
            )
            else 0.0
        )
        dread = min(1.0, dread + theme_dread)
        spec = self.music_track_spec(profile)
        steps = spec.steps
        step_seconds = spec.step_seconds
        total_samples = spec.total_samples
        samples = [0] * total_samples

        root = rng.choice((55.0, 61.74, 65.41, 73.42, 82.41))
        dark_scale = [0, 1, 3, 5, 6, 8, 10, 12]
        lead_choices = (0, 1, 3, 6, 8, 10, 12, 13, 15)
        motif = [rng.choice(lead_choices) + rng.choice((0, 0, 12)) for _ in range(8)]
        counter = [
            rng.choice((1, 3, 6, 10, 13)) + rng.choice((12, 12, 24)) for _ in range(8)
        ]
        bass_pattern = [0, 0, -1, 0, 6, 0, 3, 1, 0, 0, 10, 6, 0, 3, 1, -1]
        duty = rng.choice((0.10, 0.125, 0.18))
        riff_duty = 0.12 if dread < 0.72 else 0.09

        for step in range(steps):
            self._raise_if_music_generation_cancelled(cancelled)
            start = int(step * step_seconds * SAMPLE_RATE)
            length = int(step_seconds * SAMPLE_RATE)
            phrase = step // 16
            note_index = step % 8
            bass_degree = bass_pattern[step % len(bass_pattern)] - 12
            chug_degree = bass_pattern[step % len(bass_pattern)] - 24
            lead_degree = motif[note_index]
            if phrase % 2 == 1 and step % 8 == 0:
                lead_degree += 1
            harmony_degree = counter[(note_index + phrase) % len(counter)]
            drone_degree = -12 + (6 if phrase % 4 == 2 else 0)

            if step % 16 == 0:
                self._mix_triangle(
                    samples,
                    start,
                    length * 16,
                    self._degree_to_freq(root, drone_degree),
                    0.13 + dread * 0.05,
                )
                self._mix_sine(
                    samples,
                    start,
                    length * 16,
                    self._degree_to_freq(root, drone_degree + 1),
                    0.030 + dread * 0.018,
                    release=0.98,
                )
            if step % 16 == 8:
                self._mix_sine(
                    samples,
                    start,
                    length * 8,
                    self._degree_to_freq(root, -6),
                    0.038 + dread * 0.020,
                    release=0.92,
                )
            if step % 8 in (0, 3) or rng.random() < 0.08 + dread * 0.08:
                self._mix_square(
                    samples,
                    start,
                    max(1, int(length * 0.82)),
                    self._degree_to_freq(root, lead_degree),
                    0.15 + dread * 0.045,
                    duty,
                )
            if step % 8 in (2, 6):
                self._mix_square(
                    samples,
                    start,
                    length * 2,
                    self._degree_to_freq(root, harmony_degree),
                    0.060 + dread * 0.025,
                    0.125,
                )
            if step % 2 == 0:
                self._mix_triangle(
                    samples,
                    start,
                    length * 3,
                    self._degree_to_freq(root, bass_degree),
                    0.19 + dread * 0.08,
                )
            if step % 4 in (0, 2) or (dread > 0.70 and step % 4 == 3):
                self._mix_overdriven_square(
                    samples,
                    start,
                    max(1, int(length * (0.55 + dread * 0.18))),
                    self._degree_to_freq(root, chug_degree),
                    0.11 + dread * 0.15,
                    riff_duty,
                    drive=2.4 + dread * 2.5,
                    release=0.16,
                )
            if dread > 0.64 and step % 8 in (5, 7):
                self._mix_overdriven_square(
                    samples,
                    start,
                    max(1, int(length * 0.35)),
                    self._degree_to_freq(root, chug_degree + rng.choice(dark_scale)),
                    0.045 + dread * 0.05,
                    0.10,
                    drive=2.8 + dread * 2.4,
                    release=0.12,
                )
            if step % 8 == 0:
                self._mix_noise(
                    samples,
                    start,
                    max(1, int(length * 1.45)),
                    0.20 + dread * 0.16,
                    rng,
                    low=True,
                )
            elif step % 8 == 4:
                self._mix_noise(
                    samples,
                    start,
                    max(1, int(length * 0.9)),
                    0.12 + dread * 0.10,
                    rng,
                    low=True,
                )
            elif step % 8 in (3, 7):
                self._mix_noise(
                    samples,
                    start,
                    max(1, length // 7),
                    0.035 + dread * 0.045,
                    rng,
                    low=False,
                )
            if step % 16 == 15:
                self._mix_static_hiss(
                    samples, start, max(1, length // 2), 0.020 + dread * 0.020
                )

        return self._samples_to_pcm(samples, cancelled)

    def generate_static_menu_track(self) -> pygame.mixer.Sound:
        """Synchronously build the menu Sound for compatibility callers."""

        return pygame.mixer.Sound(buffer=self._synthesize_static_menu_pcm())

    def _synthesize_static_menu_pcm(
        self, cancelled: Callable[[], bool] | None = None
    ) -> bytes:
        self._raise_if_music_generation_cancelled(cancelled)
        spec = self.music_track_spec(
            MusicProfile(0xA11CE, "Menu", "Main Menu", "Quiet", depth=0, mood="menu")
        )
        steps = spec.steps
        step_seconds = spec.step_seconds
        total_samples = spec.total_samples
        samples = [0] * total_samples

        root = 110.0
        chord_degrees = (
            (0, 3, 7),
            (-2, 3, 7),
            (0, 5, 10),
            (-4, 2, 7),
        )
        bass_degrees = (-12, -14, -12, -16)
        bell_degrees = (17, 15, 19, 17, 15, 12, 17, 10)

        for step in range(steps):
            self._raise_if_music_generation_cancelled(cancelled)
            start = int(step * step_seconds * SAMPLE_RATE)
            length = int(step_seconds * SAMPLE_RATE)
            phrase = step // 4
            chord = chord_degrees[phrase % len(chord_degrees)]

            if step % 4 == 0:
                self._mix_triangle(
                    samples,
                    start,
                    length * 4,
                    self._degree_to_freq(
                        root, bass_degrees[phrase % len(bass_degrees)]
                    ),
                    0.10,
                )
            if step % 4 in (0, 2):
                for degree in chord:
                    self._mix_sine(
                        samples,
                        start,
                        length * 4,
                        self._degree_to_freq(root, degree),
                        0.045,
                        release=0.95,
                    )
            if step % 4 == 2:
                self._mix_sine(
                    samples,
                    start,
                    length * 2,
                    self._degree_to_freq(
                        root, bell_degrees[(step // 4) % len(bell_degrees)]
                    ),
                    0.04,
                    release=0.70,
                )
            if step == 12:
                self._mix_static_hiss(samples, start, length, 0.018)

        return self._samples_to_pcm(samples, cancelled)

    def _samples_to_pcm(
        self,
        samples: list[int],
        cancelled: Callable[[], bool] | None = None,
    ) -> bytes:
        total_samples = len(samples)
        frames = bytearray()
        fade_samples = min(total_samples // 10, SAMPLE_RATE)
        for chunk_start in range(0, total_samples, 2048):
            self._raise_if_music_generation_cancelled(cancelled)
            chunk_end = min(total_samples, chunk_start + 2048)
            for index in range(chunk_start, chunk_end):
                value = samples[index]
                fade = 1.0
                if index < fade_samples:
                    fade = index / fade_samples
                elif index > total_samples - fade_samples:
                    fade = (total_samples - index) / fade_samples
                clipped = max(-32767, min(32767, int(value * fade)))
                frames.extend(struct.pack("<h", clipped))
        return bytes(frames)

    @staticmethod
    def _raise_if_music_generation_cancelled(
        cancelled: Callable[[], bool] | None,
    ) -> None:
        if cancelled is not None and cancelled():
            raise _MusicGenerationCancelled

    def _profile_seed(self, profile: MusicProfile) -> int:
        text = f"{profile.seed}:{profile.archetype_name}:{profile.theme_name}:{profile.modifier_name}:{profile.depth}:{profile.mood}"
        value = 2166136261
        for char in text:
            value ^= ord(char)
            value = (value * 16777619) & 0xFFFFFFFF
        return value

    def _degree_to_freq(self, root: float, semitones: int) -> float:
        return root * (2 ** (semitones / 12.0))

    def _mix_square(
        self,
        samples: list[int],
        start: int,
        length: int,
        frequency: float,
        volume: float,
        duty: float,
    ) -> None:
        end = min(len(samples), start + length)
        if end <= start:
            return
        length = max(1, length)
        attack = max(1, int(length * 0.04))
        decay = max(1, length - attack)
        amplitude = MUSIC_AMPLITUDE * volume
        phase = 0.0
        phase_step = frequency / SAMPLE_RATE
        for index in range(start, end):
            local = index - start
            if local < attack:
                env = local / attack
            else:
                env = 1.0 - (local - attack) / decay * 4.0
                if env <= 0.0:
                    break
            value = amplitude if phase < duty else -amplitude
            samples[index] += int(value * env)
            phase += phase_step
            if phase >= 1.0:
                phase -= 1.0

    def _mix_overdriven_square(
        self,
        samples: list[int],
        start: int,
        length: int,
        frequency: float,
        volume: float,
        duty: float,
        drive: float,
        release: float,
    ) -> None:
        end = min(len(samples), start + length)
        if end <= start:
            return
        length = max(1, length)
        attack = max(1, int(length * 0.04))
        decay = max(1, length - attack)
        release_scale = 1.0 / max(0.01, release)
        amplitude = MUSIC_AMPLITUDE * volume
        phase = 0.0
        octave_phase = 0.0
        phase_step = frequency / SAMPLE_RATE
        octave_step = phase_step * 2.0
        for index in range(start, end):
            local = index - start
            if local < attack:
                env = local / attack
            else:
                env = 1.0 - (local - attack) / decay * release_scale
                if env <= 0.0:
                    break
            raw = 1.0 if phase < duty else -1.0
            overtone = 0.45 if octave_phase < duty else -0.45
            value = math.tanh((raw + overtone) * drive)
            samples[index] += int(value * amplitude * env)
            phase += phase_step
            octave_phase += octave_step
            if phase >= 1.0:
                phase -= 1.0
            if octave_phase >= 1.0:
                octave_phase -= 1.0

    def _mix_triangle(
        self,
        samples: list[int],
        start: int,
        length: int,
        frequency: float,
        volume: float,
    ) -> None:
        end = min(len(samples), start + length)
        if end <= start:
            return
        length = max(1, length)
        attack = max(1, int(length * 0.04))
        decay = max(1, length - attack)
        amplitude = MUSIC_AMPLITUDE * volume
        phase = 0.0
        phase_step = frequency / SAMPLE_RATE
        for index in range(start, end):
            local = index - start
            if local < attack:
                env = local / attack
            else:
                env = 1.0 - (local - attack) / decay * 2.2222222222
                if env <= 0.0:
                    break
            value = 4.0 * abs(phase - 0.5) - 1.0
            samples[index] += int(value * amplitude * env)
            phase += phase_step
            if phase >= 1.0:
                phase -= 1.0

    def _mix_sine(
        self,
        samples: list[int],
        start: int,
        length: int,
        frequency: float,
        volume: float,
        release: float = 0.75,
    ) -> None:
        end = min(len(samples), start + length)
        if end <= start:
            return
        length = max(1, length)
        attack = max(1, int(length * 0.04))
        decay = max(1, length - attack)
        release_scale = 1.0 / max(0.01, release)
        amplitude = MUSIC_AMPLITUDE * volume
        phase = (start * frequency / SAMPLE_RATE) % 1.0
        phase_step = frequency / SAMPLE_RATE
        for index in range(start, end):
            local = index - start
            if local < attack:
                env = local / attack
            else:
                env = 1.0 - (local - attack) / decay * release_scale
                if env <= 0.0:
                    break
            samples[index] += int(math.sin(math.tau * phase) * amplitude * env)
            phase += phase_step
            if phase >= 1.0:
                phase -= 1.0

    def _mix_static_hiss(
        self, samples: list[int], start: int, length: int, volume: float
    ) -> None:
        end = min(len(samples), start + length)
        amplitude = MUSIC_AMPLITUDE * volume
        value = 0.0
        for index in range(start, end):
            local = index - start
            if local % 16 == 0:
                value = amplitude if (local // 16) % 2 == 0 else -amplitude
            env = 1.0 - local / max(1, length)
            samples[index] += int(value * env)

    def _mix_noise(
        self,
        samples: list[int],
        start: int,
        length: int,
        volume: float,
        rng: random.Random,
        low: bool = False,
    ) -> None:
        end = min(len(samples), start + length)
        amplitude = MUSIC_AMPLITUDE * volume
        hold = 10 if low else 3
        value = 0.0
        for index in range(start, end):
            local = index - start
            if local % hold == 0:
                value = rng.uniform(-amplitude, amplitude)
            env = 1.0 - local / max(1, length)
            samples[index] += int(value * env)
