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

import random
from typing import Any

from .constants import DUNGEON_DEPTH
from .content import (
    DUNGEON_THEMES,
    STORY_BACKSTORIES,
    STORY_DILEMMAS,
    STORY_FACTIONS,
    STORY_GUEST_TEMPLATES,
    STORY_LOCATION_MOTIFS,
    STORY_RELICS,
)
from .models import Color, StoryBeat, StoryChoice, StoryGuest, StoryState

BASE_STORY_EFFECTS: dict[str, float] = {
    "enemy_pressure": 0.0,
    "loot_bonus": 0.0,
    "trap_bonus": 0.0,
    "shrine_bonus": 0.0,
    "secret_bonus": 0.0,
    "curse_bonus": 0.0,
    "xp_bonus": 0.0,
    "boss_pressure": 0.0,
    "damage_resist": 0.0,
    "healing_echo": 0.0,
    "relic_power": 0.0,
    "blood_price": 0.0,
    "damage_bonus": 0.0,
    "hunter_pressure": 0.0,
}


class StoryEngine:
    """Composes a replayable dark-fantasy storyline from the static corpus."""

    @staticmethod
    def generate(
        seed: int,
        archetype_name: str,
        run_number: int,
        starting_theme_name: str,
        run_modifier_name: str,
    ) -> StoryState:
        rng = random.Random(seed)
        backstory_pool = STORY_BACKSTORIES.get(archetype_name) or tuple(
            entry for entries in STORY_BACKSTORIES.values() for entry in entries
        )
        backstory = rng.choice(backstory_pool)
        faction = rng.choice(STORY_FACTIONS)
        rival_pool = [candidate for candidate in STORY_FACTIONS if candidate != faction]
        rival = rng.choice(rival_pool)
        relic = rng.choice(STORY_RELICS)
        dilemmas = _cycle_sample(rng, STORY_DILEMMAS, DUNGEON_DEPTH)
        themes = _theme_sequence(rng, starting_theme_name, run_modifier_name)
        motifs = {motif.theme_name: motif for motif in STORY_LOCATION_MOTIFS}

        beats: list[StoryBeat] = []
        for depth in range(1, DUNGEON_DEPTH + 1):
            dilemma = dilemmas[depth - 1]
            theme_name = themes[depth - 1]
            motif = motifs.get(theme_name, rng.choice(STORY_LOCATION_MOTIFS))
            guest_template = rng.choice(STORY_GUEST_TEMPLATES)
            guest_name = rng.choice(guest_template.names)
            motive = rng.choice(guest_template.motives)
            depth_scale = min(0.035, depth * 0.0025)
            choices = [
                StoryChoice(
                    "aid",
                    "Aid",
                    dilemma.aid,
                    f"{dilemma.aid_outcome}; {rival.name} loses a little ground.",
                    {
                        "enemy_pressure": -0.055 - depth_scale,
                        "shrine_bonus": 0.050 + depth_scale,
                        "secret_bonus": 0.030 + depth_scale / 2,
                        "damage_resist": 0.035 + depth_scale / 2,
                        "healing_echo": 0.025 + depth_scale / 2,
                    },
                    ["mercy", "witness"],
                ),
                StoryChoice(
                    "bargain",
                    "Bargain",
                    dilemma.bargain,
                    f"{dilemma.bargain_outcome}; {faction.name} marks the bargain.",
                    {
                        "loot_bonus": 0.075 + depth_scale,
                        "trap_bonus": 0.045 + depth_scale / 2,
                        "curse_bonus": 0.035 + depth_scale / 2,
                        "relic_power": 0.040 + depth_scale / 2,
                        "blood_price": 0.025 + depth_scale / 2,
                    },
                    ["bargain", "marked"],
                ),
                StoryChoice(
                    "defy",
                    "Defy",
                    dilemma.defy,
                    f"{dilemma.defy_outcome}; the gate tyrant hears the insult.",
                    {
                        "enemy_pressure": 0.075 + depth_scale,
                        "xp_bonus": 0.055 + depth_scale / 2,
                        "boss_pressure": 0.040 + depth_scale / 2,
                        "damage_bonus": 0.045 + depth_scale / 2,
                        "hunter_pressure": 0.045 + depth_scale / 2,
                    },
                    ["defiance", "wrath"],
                ),
            ]
            summary = (
                f"Among {motif.image}, where {motif.danger}, the air tightens around "
                f"a {guest_template.role.lower()} who {motive}. {dilemma.setup.capitalize()} "
                f"as {faction.epithet} advance their design and {rival.name} shadows "
                f"the edges of the room. The chamber remembers the {backstory.title.lower()}: "
                f"{backstory.wound}. Every torch leans toward {relic.name}, {relic.form}."
            )
            dialogue = (
                f"{guest_name} speaks in a {guest_template.voice} voice: "
                f"'{backstory.secret}. {relic.temptation}. If mercy guides you, "
                f"{dilemma.aid}; if hunger answers, {dilemma.bargain}; if wrath takes "
                f"the floor, {dilemma.defy}. Choose, and the next halls will answer "
                f"in steel, mercy, or debt.'"
            )
            beats.append(
                StoryBeat(
                    depth=depth,
                    title=dilemma.title,
                    summary=summary,
                    theme_name=theme_name,
                    guest_name=guest_name,
                    guest_role=guest_template.role,
                    guest_motive=motive,
                    dialogue=dialogue,
                    choices=choices,
                )
            )

        title = f"{backstory.title} and the {relic.name}"
        player_backstory = (
            f"{archetype_name} — {backstory.title}: {backstory.wound}; "
            f"{backstory.oath}. Secret: {backstory.secret}."
        )
        objective = (
            f"Recover {relic.name}, {relic.form}, before {faction.name} use it to "
            f"{faction.agenda}. The rival {rival.name} know the taboo: {faction.taboo}."
        )
        log = [
            f"Run {run_number} story seed {seed}",
            player_backstory,
            objective,
        ]
        return StoryState(
            seed=seed,
            title=title,
            player_backstory=player_backstory,
            objective=objective,
            antagonist=faction.epithet.title(),
            faction=faction.name,
            rival_faction=rival.name,
            relic_name=relic.name,
            relic_form=relic.form,
            relic_temptation=relic.temptation,
            beats=beats,
            accent=faction.color,
            effects=dict(BASE_STORY_EFFECTS),
            log=log,
        )


def _cycle_sample(rng: random.Random, values: tuple[Any, ...], count: int) -> list[Any]:
    if len(values) >= count:
        return rng.sample(list(values), count)
    sampled: list[Any] = []
    while len(sampled) < count:
        chunk = list(values)
        rng.shuffle(chunk)
        sampled.extend(chunk)
    return sampled[:count]


def _theme_sequence(
    rng: random.Random, starting_theme_name: str, run_modifier_name: str
) -> list[str]:
    known_themes = [theme.name for theme in DUNGEON_THEMES]
    start = (
        starting_theme_name
        if starting_theme_name in known_themes
        else rng.choice(known_themes)
    )
    sequence = [start]
    modifier_biases = {
        "Blood Moon": ("Crypt of Ash", "Violet Reliquary"),
        "Trap-Laced": ("Obsidian Foundry", "Thornbound Vault"),
        "Treasure Draught": ("Violet Reliquary", "Moonlit Aquifer"),
        "Thin Veil": ("Frozen Ossuary", "Moonlit Aquifer"),
        "Cursed Bargains": ("Thornbound Vault", "Violet Reliquary"),
        "Elite Hunt": ("Sunken Bastion", "Obsidian Foundry"),
    }
    bias = modifier_biases.get(run_modifier_name, ())
    while len(sequence) < DUNGEON_DEPTH:
        if bias and rng.random() < 0.45:
            sequence.append(rng.choice(bias))
        else:
            sequence.append(rng.choice(known_themes))
    return sequence


def story_beat_index_for_depth(story: StoryState | None, depth: int) -> int | None:
    if story is None:
        return None
    for index, beat in enumerate(story.beats):
        if beat.depth == depth:
            return index
    return None


def story_beat_for_depth(story: StoryState | None, depth: int) -> StoryBeat | None:
    index = story_beat_index_for_depth(story, depth)
    if index is None or story is None:
        return None
    return story.beats[index]


def story_guest_from_beat(
    story: StoryState, beat_index: int, x: float, y: float
) -> StoryGuest:
    beat = story.beats[beat_index]
    return StoryGuest(
        x=x,
        y=y,
        depth=beat.depth,
        beat_index=beat_index,
        name=beat.guest_name,
        role=beat.guest_role,
        motive=beat.guest_motive,
        dialogue=beat.dialogue,
        choices=list(beat.choices),
        color=story.accent,
        resolved=bool(beat.resolved_choice),
        resolved_choice=beat.resolved_choice,
        met=bool(beat.resolved_choice),
    )


def record_story_choice(story: StoryState, depth: int, choice: StoryChoice) -> None:
    beat = story_beat_for_depth(story, depth)
    if beat is not None:
        beat.resolved_choice = choice.key
        beat.outcome = choice.outcome
    _add_story_effects(story, choice.effects)
    for flag in choice.flags:
        story.flags.append(f"{depth}:{flag}")
    story.log.append(f"Depth {depth}: {choice.label} — {choice.outcome}")
    del story.log[:-12]


def record_unanswered_story_beat(story: StoryState, depth: int) -> bool:
    beat = story_beat_for_depth(story, depth)
    if beat is None or beat.resolved_choice:
        return False
    beat.resolved_choice = "unanswered"
    beat.outcome = (
        f"{beat.guest_name}'s plea went unanswered; the dungeon takes the silence "
        "as permission to harden its next rooms."
    )
    _add_story_effects(
        story,
        {
            "enemy_pressure": 0.045,
            "trap_bonus": 0.035,
            "curse_bonus": 0.015,
            "boss_pressure": 0.025,
            "hunter_pressure": 0.040,
        },
    )
    story.flags.append(f"{depth}:unanswered")
    story.flags.append(f"{depth}:forsaken")
    story.log.append(f"Depth {depth}: Unanswered — {beat.outcome}")
    del story.log[:-12]
    return True


def _add_story_effects(story: StoryState, effects: dict[str, float]) -> None:
    for key, value in effects.items():
        story.effects[key] = round(story.effects.get(key, 0.0) + float(value), 4)


def story_effect(story: StoryState | None, key: str) -> float:
    if story is None:
        return 0.0
    return float(story.effects.get(key, 0.0))


def clamp_story_effect(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def story_choice_to_dict(choice: StoryChoice) -> dict[str, Any]:
    return {
        "key": choice.key,
        "label": choice.label,
        "intent": choice.intent,
        "outcome": choice.outcome,
        "effects": dict(choice.effects),
        "flags": list(choice.flags),
    }


def story_choice_from_dict(data: dict[str, Any]) -> StoryChoice:
    return StoryChoice(
        key=str(data.get("key", "aid")),
        label=str(data.get("label", "Aid")),
        intent=str(data.get("intent", "help the guest")),
        outcome=str(data.get("outcome", "the story changes")),
        effects={
            str(key): float(value) for key, value in data.get("effects", {}).items()
        },
        flags=[str(flag) for flag in data.get("flags", [])],
    )


def story_beat_to_dict(beat: StoryBeat) -> dict[str, Any]:
    return {
        "depth": beat.depth,
        "title": beat.title,
        "summary": beat.summary,
        "theme_name": beat.theme_name,
        "guest_name": beat.guest_name,
        "guest_role": beat.guest_role,
        "guest_motive": beat.guest_motive,
        "dialogue": beat.dialogue,
        "choices": [story_choice_to_dict(choice) for choice in beat.choices],
        "resolved_choice": beat.resolved_choice,
        "outcome": beat.outcome,
    }


def story_beat_from_dict(data: dict[str, Any]) -> StoryBeat:
    return StoryBeat(
        depth=int(data.get("depth", 1)),
        title=str(data.get("title", "Unnamed Beat")),
        summary=str(data.get("summary", "")),
        theme_name=str(data.get("theme_name", DUNGEON_THEMES[0].name)),
        guest_name=str(data.get("guest_name", "Unknown Guest")),
        guest_role=str(data.get("guest_role", "Guest")),
        guest_motive=str(data.get("guest_motive", "waits for a choice")),
        dialogue=str(data.get("dialogue", "")),
        choices=[story_choice_from_dict(choice) for choice in data.get("choices", [])],
        resolved_choice=str(data.get("resolved_choice", "")),
        outcome=str(data.get("outcome", "")),
    )


def story_state_to_dict(story: StoryState | None) -> dict[str, Any] | None:
    if story is None:
        return None
    return {
        "seed": story.seed,
        "title": story.title,
        "player_backstory": story.player_backstory,
        "objective": story.objective,
        "antagonist": story.antagonist,
        "faction": story.faction,
        "rival_faction": story.rival_faction,
        "relic_name": story.relic_name,
        "relic_form": story.relic_form,
        "relic_temptation": story.relic_temptation,
        "beats": [story_beat_to_dict(beat) for beat in story.beats],
        "accent": list(story.accent),
        "flags": list(story.flags),
        "effects": dict(story.effects),
        "log": list(story.log),
    }


def story_state_from_dict(data: dict[str, Any] | None) -> StoryState | None:
    if data is None:
        return None
    accent_data = data.get("accent", (190, 150, 245))
    accent: Color = (
        int(accent_data[0]),
        int(accent_data[1]),
        int(accent_data[2]),
    )
    return StoryState(
        seed=int(data.get("seed", 0)),
        title=str(data.get("title", "Unwritten Descent")),
        player_backstory=str(data.get("player_backstory", "")),
        objective=str(data.get("objective", "")),
        antagonist=str(data.get("antagonist", "Gate Tyrant")),
        faction=str(data.get("faction", "Unknown Faction")),
        rival_faction=str(data.get("rival_faction", "Unknown Rival")),
        relic_name=str(data.get("relic_name", "Nameless Relic")),
        relic_form=str(data.get("relic_form", "a relic")),
        relic_temptation=str(data.get("relic_temptation", "it wants to be used")),
        beats=[story_beat_from_dict(beat) for beat in data.get("beats", [])],
        accent=accent,
        flags=[str(flag) for flag in data.get("flags", [])],
        effects={
            **BASE_STORY_EFFECTS,
            **{
                str(key): float(value) for key, value in data.get("effects", {}).items()
            },
        },
        log=[str(entry) for entry in data.get("log", [])],
    )


def story_guest_to_dict(guest: StoryGuest) -> dict[str, Any]:
    return {
        "x": guest.x,
        "y": guest.y,
        "depth": guest.depth,
        "beat_index": guest.beat_index,
        "name": guest.name,
        "role": guest.role,
        "motive": guest.motive,
        "dialogue": guest.dialogue,
        "choices": [story_choice_to_dict(choice) for choice in guest.choices],
        "color": list(guest.color),
        "resolved": guest.resolved,
        "resolved_choice": guest.resolved_choice,
        "met": guest.met,
    }


def story_guest_from_dict(data: dict[str, Any]) -> StoryGuest:
    color_data = data.get("color", (190, 150, 245))
    color: Color = (int(color_data[0]), int(color_data[1]), int(color_data[2]))
    return StoryGuest(
        x=float(data.get("x", 0.0)),
        y=float(data.get("y", 0.0)),
        depth=int(data.get("depth", 1)),
        beat_index=int(data.get("beat_index", 0)),
        name=str(data.get("name", "Unknown Guest")),
        role=str(data.get("role", "Guest")),
        motive=str(data.get("motive", "waits for a choice")),
        dialogue=str(data.get("dialogue", "")),
        choices=[story_choice_from_dict(choice) for choice in data.get("choices", [])],
        color=color,
        resolved=bool(data.get("resolved", False)),
        resolved_choice=str(data.get("resolved_choice", "")),
        met=bool(data.get("met", data.get("resolved", False))),
    )
