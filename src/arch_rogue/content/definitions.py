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


class StoryDilemmaTemplate(NamedTuple):
    title: str
    setup: str
    aid: str
    bargain: str
    defy: str
    aid_outcome: str
    bargain_outcome: str
    defy_outcome: str


class StoryLocationMotif(NamedTuple):
    theme_name: str
    image: str
    danger: str

