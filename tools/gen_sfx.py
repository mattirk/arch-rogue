#!/usr/bin/env python3
"""One-off SFX bake: synthesizes the authored sound set into assets/audio/.

Stdlib-only (wave + math). These are authored assets in the pipeline sense:
the runtime only ever loads .wav files from assets/audio/ and can be handed
better takes later without a code change. Mono 16-bit 22050 Hz, short and
dry. This bake intentionally defines no background-music policy or slots.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import struct
import wave
from pathlib import Path

RATE = 22050
OUT = Path(__file__).resolve().parent.parent / "assets" / "audio"

rng = random.Random(6)  # deterministic bake
manifest_cues: dict[str, dict[str, object]] = {}


def env(t: float, dur: float, attack: float = 0.004, power: float = 3.0) -> float:
    if t < attack:
        return t / attack
    rest = (t - attack) / max(dur - attack, 1e-6)
    return max(0.0, (1.0 - rest)) ** power


def render(name: str, dur: float, sample, *, usage: str = "runtime") -> None:
    n = int(dur * RATE)
    lowpass = 0.0
    frames = bytearray()
    for i in range(n):
        t = i / RATE
        v = sample(t)
        # gentle one-pole lowpass to take the digital edge off
        lowpass += 0.55 * (v - lowpass)
        v = max(-1.0, min(1.0, lowpass))
        frames += struct.pack("<h", int(v * 32767 * 0.85))
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.wav"
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(RATE)
        f.writeframes(bytes(frames))
    manifest_cues[name] = {
        "duration_ms": round(n * 1000 / RATE),
        "file": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "usage": usage,
    }
    print(f"  {name}.wav  {dur*1000:.0f} ms")


def noise() -> float:
    return rng.uniform(-1.0, 1.0)


def main() -> None:
    print("baking sfx")

    render("swing", 0.10, lambda t:
        noise() * 0.5 * env(t, 0.10, power=2.0))

    render("hit", 0.14, lambda t:
        (noise() * 0.45 + math.sin(2 * math.pi * 95 * t) * 0.6) * env(t, 0.14))

    render("hurt", 0.18, lambda t:
        (noise() * 0.3 + math.sin(2 * math.pi * 68 * t) * 0.7) * env(t, 0.18))

    render("bolt", 0.13, lambda t:
        math.sin(2 * math.pi * (900 - 4200 * t) * t) * 0.55 * env(t, 0.13, power=2.0))

    def pickup(t: float) -> float:
        f = 660.0 if t < 0.05 else 880.0
        return math.sin(2 * math.pi * f * t) * 0.4 * env(t, 0.11, power=1.5)
    render("pickup", 0.11, pickup)

    render("potion", 0.20, lambda t:
        math.sin(2 * math.pi * (220 + 900 * t) * t) * 0.4 * env(t, 0.20, power=1.5))

    def levelup(t: float) -> float:
        notes = (523.25, 659.25, 783.99)
        idx = min(int(t / 0.095), 2)
        local = t - idx * 0.095
        return math.sin(2 * math.pi * notes[idx] * t) * 0.42 * env(local, 0.14, power=1.5)
    render("levelup", 0.42, levelup)

    render("stairs", 0.38, lambda t:
        (noise() * 0.35 + math.sin(2 * math.pi * 58 * t) * 0.5) * env(t, 0.38, power=1.6))

    render("death", 0.55, lambda t:
        (math.sin(2 * math.pi * (190 - 250 * t) * t) * 0.6 + noise() * 0.25) * env(t, 0.55, power=1.4))

    render("door", 0.16, lambda t:
        (noise() * 0.4 + math.sin(2 * math.pi * 130 * t) * 0.3) * env(t, 0.16, power=2.0))

    # M10 semantic cues. These intentionally modest placeholder takes can be
    # replaced file-for-file when the final audio direction is available.
    def start(t: float) -> float:
        notes = (196.00, 246.94, 293.66)
        idx = min(int(t / 0.13), len(notes) - 1)
        local = t - idx * 0.13
        return math.sin(2 * math.pi * notes[idx] * t) * 0.38 * env(local, 0.18, power=1.4)
    render("start", 0.48, start)

    render("ui_nav", 0.045, lambda t:
        math.sin(2 * math.pi * 720 * t) * 0.28 * env(t, 0.045, attack=0.001, power=2.0))

    def ui_confirm(t: float) -> float:
        frequency = 620.0 if t < 0.055 else 880.0
        local = t if t < 0.055 else t - 0.055
        return math.sin(2 * math.pi * frequency * t) * 0.32 * env(local, 0.075, power=1.8)
    render("ui_confirm", 0.13, ui_confirm)

    render("ui_back", 0.11, lambda t:
        math.sin(2 * math.pi * (560 - 1900 * t) * t) * 0.30 * env(t, 0.11, power=1.8))

    render("bell", 0.72, lambda t:
        (math.sin(2 * math.pi * 392 * t) * 0.34
         + math.sin(2 * math.pi * 784 * t) * 0.20
         + math.sin(2 * math.pi * 1176 * t) * 0.10) * env(t, 0.72, power=1.15))

    render("boss", 0.66, lambda t:
        (math.sin(2 * math.pi * (74 - 18 * t) * t) * 0.52
         + noise() * 0.18) * env(t, 0.66, attack=0.02, power=1.1))

    def victory(t: float) -> float:
        notes = (392.00, 493.88, 587.33, 783.99)
        idx = min(int(t / 0.18), len(notes) - 1)
        local = t - idx * 0.18
        return math.sin(2 * math.pi * notes[idx] * t) * 0.37 * env(local, 0.26, power=1.2)
    render("victory", 0.90, victory)

    render("drink", 0.30, lambda t:
        (math.sin(2 * math.pi * (115 + 32 * math.sin(2 * math.pi * 9 * t)) * t) * 0.30
         + noise() * 0.12) * env(t, 0.30, attack=0.008, power=1.6))

    render("trap", 0.20, lambda t:
        (noise() * 0.52 + math.sin(2 * math.pi * 145 * t) * 0.24)
        * env(t, 0.20, attack=0.001, power=2.4), usage="future_emitter")

    render("shrine", 0.72, lambda t:
        (math.sin(2 * math.pi * 329.63 * t) * 0.25
         + math.sin(2 * math.pi * 493.88 * t) * 0.20) * env(t, 0.72, attack=0.04, power=1.1),
        usage="future_emitter")

    def secret(t: float) -> float:
        frequency = 523.25 if t < 0.14 else 783.99
        local = t if t < 0.14 else t - 0.14
        return math.sin(2 * math.pi * frequency * t) * 0.31 * env(local, 0.24, power=1.3)
    render("secret", 0.42, secret, usage="future_emitter")

    manifest = {
        "channels": 1,
        "cues": manifest_cues,
        "format_version": 1,
        "sample_rate": RATE,
        "sample_size_bits": 16,
    }
    manifest_path = OUT / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    print(f"wrote {len(manifest_cues)} cues and {manifest_path}")


if __name__ == "__main__":
    main()
