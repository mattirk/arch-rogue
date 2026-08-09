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

from typing import NamedTuple

from ..models import Color


class InteractionHint(NamedTuple):
    title: str
    detail: str
    color: Color


class RarityProfile(NamedTuple):
    color: Color
    icon: str
    weight: int


class EnemyAbility(NamedTuple):
    """One authored enemy attack, dispatched through the windup/commit seam.

    ``effect`` is one of "strike" (single-target melee hitscan), "bolt"
    (single projectile), "fan" (``projectile_count`` bolts across ``spread``),
    or "nova" (radial LOS-checked burst around the caster). Zero values mean
    "inherit from the enemy": ``attack_range`` falls back to the enemy's base
    range, ``windup`` to the per-kind default. ``cooldown`` is the ability's
    own rotation timer, independent of the enemy's global ``attack_cooldown``
    recovery gate.
    """

    key: str
    effect: str
    damage_multiplier: float = 1.0
    attack_range: float = 0.0
    min_range: float = 0.0
    windup: float = 0.0
    cooldown: float = 0.0
    projectile_speed: float = 6.0
    projectile_count: int = 1
    spread: float = 0.28
    status_effect: str = ""
    status_duration: float = 0.0


class Tactic(NamedTuple):
    """Per-role movement doctrine for the enemy AI.

    ``preferred_range``/``min_range`` define the kite band for ranged roles
    (zero = melee: close to contact). ``strafe_bias`` curves the approach /
    drifts sideways while the attack cooldown recovers. ``hold_anchor`` roles
    stand their post until the target closes inside ``preferred_range``.
    ``reposition_for_los`` roles sidestep for a firing line instead of
    standing blocked (bounded probe, only when otherwise attack-eligible).
    """

    key: str
    preferred_range: float = 0.0
    min_range: float = 0.0
    strafe_bias: float = 0.0
    hold_anchor: bool = False
    reposition_for_los: bool = False


class EnemyDefinition(NamedTuple):
    name: str
    kind: str
    max_hp: int
    speed: float
    damage: int
    xp: int
    attack_range: float
    attack_cooldown: float
    aggro_range: float
    color: Color
    weight: int
    # 4.8.9 machine intelligence: optional per-type overrides. ``tactic``
    # overrides the role-derived movement doctrine; ``abilities`` lists
    # authored EnemyAbility keys (empty = synthesized default from ``kind``,
    # which reproduces the pre-4.8.9 behavior exactly).
    tactic: str = ""
    abilities: tuple[str, ...] = ()


class EncounterTemplate(NamedTuple):
    key: str
    title: str
    risk: str
    reward: str
    enemy_bonus: int = 0
    elite_bonus: float = 0.0
    trap_bonus: float = 0.0
    loot_bonus: float = 0.0
    secret_bonus: float = 0.0
    guaranteed_miniboss: bool = False
    challenge_room: bool = False


class BossDefinition(NamedTuple):
    key: str
    name: str
    subtitle: str
    theme_names: tuple[str, ...]
    damage_type: str
    max_hp: int
    speed: float
    damage: int
    xp: int
    attack_range: float
    attack_cooldown: float
    aggro_range: float
    color: Color
    telegraph: str
    loot_hook: str
    final_boss: bool = False
    # 4.8.9 machine intelligence: authored EnemyAbility keys making the
    # telegraph flavor mechanical. Empty = the legacy melee/cast band only.
    abilities: tuple[str, ...] = ()


class DifficultyProfile(NamedTuple):
    name: str
    description: str
    enemy_hp_multiplier: float
    enemy_damage_multiplier: float
    enemy_damage_bonus: int
    enemy_speed_multiplier: float
    enemy_attack_cooldown_multiplier: float
    enemy_aggro_bonus: float
    enemy_count_bonus: int
    enemy_extra_chance: float
    elite_bonus: float
    miniboss_bonus: float
    trap_chance_bonus: float
    trap_damage_multiplier: float
    loot_chance_bonus: float
    shrine_chance_bonus: float


class EquipmentDefinition(NamedTuple):
    name: str
    slot: str
    value: int


class StoryBackstory(NamedTuple):
    title: str
    wound: str
    oath: str
    secret: str


class StoryArc(NamedTuple):
    """One archetype's canonical throughline (4.9).

    The three legacy backstory rolls are chapters of this single life: the
    roll picks which chapter title colors the run, while ``wound``/``oath``/
    ``secret`` stay fixed so every run of an archetype tells the same story.
    Budgets (see build/story/50-cutscene-style.md): wound <=90, oath <=80,
    secret <=90. The secret never renders before depth 5.
    """

    wound: str
    oath: str
    secret: str
    chapters: tuple[str, ...]


class StoryTetherBeat(NamedTuple):
    """One fixed appearance of an archetype's tether NPC (depths 1/5/9)."""

    motive: str
    speech: str


class StoryCrisisChoice(NamedTuple):
    """Authored verb text for the depth-9 tether crisis."""

    intent: str
    outcome: str


class StoryTether(NamedTuple):
    """The recurring NPC bound to one archetype's storyline.

    ``role`` matches an existing guest template role so sprites and voice
    metadata keep working; ``name`` is fixed instead of rolled.
    """

    role: str
    name: str
    meet: StoryTetherBeat
    reveal: StoryTetherBeat
    crisis: StoryTetherBeat
    crisis_choices: dict[str, StoryCrisisChoice]


class StoryEnding(NamedTuple):
    """One authored ending: archetype x final gate verb."""

    title: str
    body: str


class StoryFaction(NamedTuple):
    name: str
    epithet: str
    agenda: str
    taboo: str
    color: Color


class StoryRelic(NamedTuple):
    name: str
    form: str
    temptation: str
    doom: str


class StoryGuestTemplate(NamedTuple):
    role: str
    names: tuple[str, ...]
    motives: tuple[str, ...]
    voice: str
    # 4.9: one spoken line per motive (parallel arrays). The beat dialogue is
    # the guest actually speaking (<=90 chars, quoted) instead of a narrated
    # paragraph. Default keeps older constructions valid.
    speeches: tuple[str, ...] = ()


class StoryDilemmaTemplate(NamedTuple):
    title: str
    setup: str
    aid: str
    bargain: str
    defy: str
    aid_outcome: str
    bargain_outcome: str
    defy_outcome: str
    # 4.9.x "more revealing": one plain-spoken sentence (<=110) stating what
    # is actually going on — the myth shown, not riddled. Rendered after the
    # stake in omens and the story panel.
    truth: str = ""


class StoryLocationMotif(NamedTuple):
    theme_name: str
    image: str
    danger: str

