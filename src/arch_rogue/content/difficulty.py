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

from .definitions import DifficultyProfile


DEFAULT_DIFFICULTY_NAME = "Hard"
HELL_DIFFICULTY_NAME = "Hell"
DIFFICULTY_PROFILES = (
    DifficultyProfile(
        "Easy",
        "Still dangerous: tougher enemies, real ambush pressure, and fewer safety nets.",
        enemy_hp_multiplier=1.76,
        enemy_damage_multiplier=1.64,
        enemy_damage_bonus=1,
        enemy_speed_multiplier=1.08,
        enemy_attack_cooldown_multiplier=0.90,
        enemy_aggro_bonus=0.60,
        enemy_count_bonus=0,
        enemy_extra_chance=0.35,
        elite_bonus=0.03,
        miniboss_bonus=0.015,
        trap_chance_bonus=0.05,
        trap_damage_multiplier=1.50,
        loot_chance_bonus=0.0,
        shrine_chance_bonus=0.0,
    ),
    DifficultyProfile(
        "Medium",
        "Severe pressure with doubled monster durability, damage, traps, and room threats.",
        enemy_hp_multiplier=2.36,
        enemy_damage_multiplier=2.30,
        enemy_damage_bonus=2,
        enemy_speed_multiplier=1.14,
        enemy_attack_cooldown_multiplier=0.82,
        enemy_aggro_bonus=1.40,
        enemy_count_bonus=1,
        enemy_extra_chance=0.70,
        elite_bonus=0.05,
        miniboss_bonus=0.03,
        trap_chance_bonus=0.10,
        trap_damage_multiplier=2.20,
        loot_chance_bonus=-0.08,
        shrine_chance_bonus=-0.04,
    ),
    DifficultyProfile(
        "Hard",
        "Default: brutal density, crushing hits, relentless attacks, and scarce recovery.",
        enemy_hp_multiplier=2.85,
        enemy_damage_multiplier=2.60,
        enemy_damage_bonus=5,
        enemy_speed_multiplier=1.18,
        enemy_attack_cooldown_multiplier=0.74,
        enemy_aggro_bonus=2.50,
        enemy_count_bonus=2,
        enemy_extra_chance=0.75,
        elite_bonus=0.16,
        miniboss_bonus=0.085,
        trap_chance_bonus=0.25,
        trap_damage_multiplier=2.55,
        loot_chance_bonus=-0.13,
        shrine_chance_bonus=-0.065,
    ),
    DifficultyProfile(
        "Hell",
        "Unlocked after a clear: overwhelming density, constant elites, lethal traps, and no mercy.",
        enemy_hp_multiplier=3.80,
        enemy_damage_multiplier=3.30,
        enemy_damage_bonus=8,
        enemy_speed_multiplier=1.30,
        enemy_attack_cooldown_multiplier=0.60,
        enemy_aggro_bonus=4.75,
        enemy_count_bonus=3,
        enemy_extra_chance=0.90,
        elite_bonus=0.30,
        miniboss_bonus=0.17,
        trap_chance_bonus=0.42,
        trap_damage_multiplier=3.35,
        loot_chance_bonus=-0.20,
        shrine_chance_bonus=-0.12,
    ),
)

