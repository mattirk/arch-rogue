from __future__ import annotations

import math
import random
import struct
from dataclasses import dataclass

import pygame

SAMPLE_RATE = 22050
SFX_AMPLITUDE = 3600
MUSIC_AMPLITUDE = 2300


@dataclass(frozen=True)
class MusicProfile:
    seed: int
    archetype_name: str
    theme_name: str
    modifier_name: str
    depth: int = 1
    mood: str = "run"


class AudioSystem:
    """Procedural audio manager for SFX and run-specific chiptune music."""

    def __init__(self) -> None:
        self.available = False
        self.sfx_cache: dict[str, pygame.mixer.Sound] = {}
        self.music_cache: dict[int, pygame.mixer.Sound] = {}
        self.music_channel: pygame.mixer.Channel | None = None
        self.current_music_seed: int | None = None

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
                    "secret": 612,
                    "shrine": 520,
                    "boss": 88,
                    "stairs": 430,
                    "victory": 784,
                    "death": 120,
                }.get(name, 440)
                duration = 0.16 if name in {"boss", "victory", "death"} else 0.08
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

    def play_run_music(self, profile: MusicProfile, enabled: bool = True) -> bool:
        if not enabled or not self.available:
            self.stop_music()
            return self.available
        try:
            music_key = self._profile_seed(profile)
            if self.current_music_seed == music_key and self.music_channel:
                if self.music_channel.get_busy():
                    return self.available
            sound = self.music_cache.get(music_key)
            if sound is None:
                sound = (
                    self.generate_static_menu_track()
                    if profile.mood == "menu"
                    else self.generate_run_track(profile)
                )
                self.music_cache[music_key] = sound
            channel = self.music_channel or sound.play(loops=-1)
            if self.music_channel:
                self.music_channel.play(sound, loops=-1, fade_ms=650)
            self.music_channel = channel
            self.current_music_seed = music_key
        except pygame.error:
            self.available = False
        return self.available

    def stop_music(self) -> None:
        if self.music_channel:
            try:
                self.music_channel.fadeout(300)
            except pygame.error:
                self.available = False
        self.current_music_seed = None

    def sync_music(self, profile: MusicProfile | None, enabled: bool) -> bool:
        if profile is None:
            self.stop_music()
            return self.available
        return self.play_run_music(profile, enabled)

    def generate_run_track(self, profile: MusicProfile) -> pygame.mixer.Sound:
        rng = random.Random(self._profile_seed(profile))
        depth = max(1, profile.depth)
        metal = min(1.0, (depth - 1) / 9.0)
        base_tempo = 112 + (profile.seed % 4) * 4
        tempo = min(212, base_tempo + (depth - 1) * 9)
        steps = 64
        step_seconds = 60.0 / tempo / 2.0
        total_samples = int(steps * step_seconds * SAMPLE_RATE)
        samples = [0] * total_samples

        root = rng.choice((82.41, 92.50, 98.0, 110.0, 123.47))
        scale = [0, 2, 3, 5, 7, 10, 12]
        metal_scale = [0, 1, 3, 5, 6, 7, 10, 12]
        lead_scale = metal_scale if metal >= 0.35 else scale
        motif = [rng.choice(lead_scale) + rng.choice((0, 12, 12, 24)) for _ in range(8)]
        counter = [rng.choice(lead_scale) + rng.choice((12, 24)) for _ in range(8)]
        bass = [0, 0, 7, 0, 10, 7, 3, 5]
        metal_bass = [0, 0, 0, 6, 0, 0, 3, 1, 0, 0, 7, 6, 0, 3, 1, 0]
        duty = rng.choice((0.125, 0.25, 0.5))
        riff_duty = 0.18 if metal < 0.65 else 0.12

        for step in range(steps):
            start = int(step * step_seconds * SAMPLE_RATE)
            length = int(step_seconds * SAMPLE_RATE)
            phrase = step // 16
            note_index = step % 8
            lead_degree = motif[note_index] + (
                12 if phrase % 4 == 3 and step % 4 == 0 else 0
            )
            harmony_degree = counter[(note_index + phrase) % 8]
            bass_pattern = metal_bass if metal >= 0.28 else bass
            bass_degree = bass_pattern[step % len(bass_pattern)] - 18
            chug_degree = bass_pattern[step % len(bass_pattern)] - 24

            if step % 2 == 0 or rng.random() < 0.35 + metal * 0.25:
                self._mix_square(
                    samples,
                    start,
                    length,
                    self._degree_to_freq(root, lead_degree),
                    0.26 + metal * 0.08,
                    duty,
                )
            if step % 4 in (1, 3) or (metal > 0.55 and step % 4 == 2):
                self._mix_square(
                    samples,
                    start,
                    length,
                    self._degree_to_freq(root, harmony_degree),
                    0.14 + metal * 0.06,
                    0.25,
                )
            if step % 2 == 0:
                self._mix_triangle(
                    samples,
                    start,
                    length * 2,
                    self._degree_to_freq(root, bass_degree),
                    0.24 + metal * 0.08,
                )
            if metal > 0.15:
                self._mix_overdriven_square(
                    samples,
                    start,
                    max(1, int(length * (0.52 + metal * 0.22))),
                    self._degree_to_freq(root, chug_degree),
                    0.16 + metal * 0.19,
                    riff_duty,
                    drive=1.9 + metal * 2.2,
                    release=0.18,
                )
                if metal > 0.52 and step % 4 in (0, 3):
                    self._mix_overdriven_square(
                        samples,
                        start,
                        max(1, int(length * 0.44)),
                        self._degree_to_freq(root, chug_degree + 7),
                        0.08 + metal * 0.08,
                        0.14,
                        drive=2.4 + metal * 2.0,
                        release=0.14,
                    )
            if step % 4 == 0:
                self._mix_noise(
                    samples,
                    start,
                    max(1, length // 3),
                    0.28 + metal * 0.18,
                    rng,
                    low=True,
                )
            elif step % 4 == 2:
                self._mix_noise(
                    samples,
                    start,
                    max(1, length // 5),
                    0.18 + metal * 0.12,
                    rng,
                    low=False,
                )
            elif step % 2 == 1 and rng.random() < 0.45 + metal * 0.45:
                self._mix_noise(
                    samples,
                    start,
                    max(1, length // 8),
                    0.09 + metal * 0.10,
                    rng,
                    low=False,
                )
            if metal > 0.68 and step % 8 in (7,):
                self._mix_noise(
                    samples, start, max(1, length // 6), 0.24, rng, low=False
                )

        frames = bytearray()
        fade_samples = min(total_samples // 12, SAMPLE_RATE // 2)
        for index, value in enumerate(samples):
            fade = 1.0
            if index < fade_samples:
                fade = index / fade_samples
            elif index > total_samples - fade_samples:
                fade = (total_samples - index) / fade_samples
            clipped = max(-32767, min(32767, int(value * fade)))
            frames.extend(struct.pack("<h", clipped))
        return pygame.mixer.Sound(buffer=bytes(frames))

    def generate_static_menu_track(self) -> pygame.mixer.Sound:
        tempo = 58
        steps = 16
        step_seconds = 60.0 / tempo
        total_samples = int(steps * step_seconds * SAMPLE_RATE)
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

        frames = bytearray()
        fade_samples = min(total_samples // 10, SAMPLE_RATE)
        for index, value in enumerate(samples):
            fade = 1.0
            if index < fade_samples:
                fade = index / fade_samples
            elif index > total_samples - fade_samples:
                fade = (total_samples - index) / fade_samples
            clipped = max(-32767, min(32767, int(value * fade)))
            frames.extend(struct.pack("<h", clipped))
        return pygame.mixer.Sound(buffer=bytes(frames))

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
        amplitude = MUSIC_AMPLITUDE * volume
        for index in range(start, end):
            local = index - start
            env = self._pluck_envelope(local, length)
            phase = (local * frequency / SAMPLE_RATE) % 1.0
            value = amplitude if phase < duty else -amplitude
            samples[index] += int(value * env)

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
        amplitude = MUSIC_AMPLITUDE * volume
        for index in range(start, end):
            local = index - start
            env = self._pluck_envelope(local, length, release=release)
            phase = (local * frequency / SAMPLE_RATE) % 1.0
            raw = 1.0 if phase < duty else -1.0
            octave_phase = (local * frequency * 2.0 / SAMPLE_RATE) % 1.0
            overtone = 0.45 if octave_phase < duty else -0.45
            value = math.tanh((raw + overtone) * drive)
            samples[index] += int(value * amplitude * env)

    def _mix_triangle(
        self,
        samples: list[int],
        start: int,
        length: int,
        frequency: float,
        volume: float,
    ) -> None:
        end = min(len(samples), start + length)
        amplitude = MUSIC_AMPLITUDE * volume
        for index in range(start, end):
            local = index - start
            env = self._pluck_envelope(local, length, release=0.45)
            phase = (local * frequency / SAMPLE_RATE) % 1.0
            value = 4.0 * abs(phase - 0.5) - 1.0
            samples[index] += int(value * amplitude * env)

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
        amplitude = MUSIC_AMPLITUDE * volume
        for index in range(start, end):
            local = index - start
            env = self._pluck_envelope(local, length, release=release)
            value = math.sin(math.tau * frequency * index / SAMPLE_RATE)
            samples[index] += int(value * amplitude * env)

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

    def _pluck_envelope(self, index: int, length: int, release: float = 0.25) -> float:
        attack = max(1, int(length * 0.04))
        if index < attack:
            return index / attack
        progress = (index - attack) / max(1, length - attack)
        return max(0.0, 1.0 - progress * (1.0 / max(0.01, release)))
