# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
#
# AI Provenance & Liability Notice:
# This repository contains code generated, assisted, or refactored by Artificial
# Intelligence models. Provided strictly "AS IS" under Apache-2.0 with no warranty
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

"""Enemy ability and tactic resolution (4.8.9 machine intelligence).

Pure lookup helpers shared by the enemy AI in :mod:`arch_rogue.combat.enemies`.
Authored :class:`~arch_rogue.content.EnemyAbility` entries live in
``content/enemies.py`` (``ABILITY_INDEX``); the reserved ``windup_attack``
keys ``"melee"``/``"cast"`` name the defaults synthesized from an enemy's
stat columns and always dispatch to the legacy executors, so an enemy with
no authored ability list behaves exactly as it did before 4.8.9.
"""

from __future__ import annotations

from ..content import (
    ABILITY_INDEX,
    DEFAULT_MELEE_TACTIC,
    DEFAULT_RANGED_TACTIC,
    TACTICS,
    EnemyAbility,
    Tactic,
)
from ..models import Enemy

# Reserved keys for the synthesized default attacks. Never authored.
LEGACY_MELEE_KEY = "melee"
LEGACY_CAST_KEY = "cast"

# Legacy boss cast band, kept as the fallback when no authored ability is
# eligible so bosses are never left without an attack.
BOSS_CAST_MIN_RANGE = 2.0
BOSS_CAST_MAX_RANGE = 6.0

# Below half HP a boss encounter recovers its authored abilities faster —
# simple phase pressure without extra state.
BOSS_PHASE_HP_FRACTION = 0.5
BOSS_PHASE_COOLDOWN_FACTOR = 0.8


def enemy_tactic(enemy: Enemy) -> Tactic:
    """Movement doctrine for an enemy: authored override, role, then kind.

    Kind stays the behavioral axis (ranged enemies hold a band, melee close
    to contact); the tactic only parameterizes it. A ranged enemy whose role
    maps to a bandless (melee-shaped) tactic — e.g. the "bruiser" default on
    directly-constructed test enemies, or an elite roll that reassigns the
    role — falls back to the legacy ranged band so it never casts from
    point-blank contact.
    """
    tactic = TACTICS.get(enemy.tactic or enemy.role)
    if enemy.kind == "ranged":
        if tactic is None or tactic.preferred_range <= 0.0:
            return DEFAULT_RANGED_TACTIC
        return tactic
    if tactic is None:
        return DEFAULT_MELEE_TACTIC
    return tactic


def authored_abilities(enemy: Enemy) -> tuple[EnemyAbility, ...]:
    """The enemy's authored abilities, in rotation order. Unknown keys skip."""
    if not enemy.ability_keys:
        return ()
    return tuple(
        ABILITY_INDEX[key] for key in enemy.ability_keys if key in ABILITY_INDEX
    )


def ability_attack_range(enemy: Enemy, ability: EnemyAbility) -> float:
    """Effective reach of an ability on this enemy (0 = inherit).

    Projectile abilities on boss encounters inherit the legacy boss cast
    reach instead of the (usually melee-length) base attack range.
    """
    if ability.attack_range > 0.0:
        return ability.attack_range
    if ability.effect in ("bolt", "fan") and (
        enemy.kind == "boss" or enemy.is_boss_encounter
    ):
        return max(BOSS_CAST_MAX_RANGE, enemy.attack_range)
    return enemy.attack_range


def boss_phase_cooldown_factor(enemy: Enemy) -> float:
    if enemy.hp < enemy.max_hp * BOSS_PHASE_HP_FRACTION:
        return BOSS_PHASE_COOLDOWN_FACTOR
    return 1.0


def select_boss_attack(enemy: Enemy, distance: float) -> str | None:
    """Pick the boss attack key for this frame, or None when out of options.

    Authored abilities rotate: among the off-cooldown abilities whose range
    band covers ``distance``, prefer one that is not the last ability fired.
    With none eligible, fall back to the legacy band — cast at mid range,
    melee up close — so the boss keeps its pre-4.8.9 baseline pressure.
    Deterministic; consumes no RNG.
    """
    candidates = []
    for ability in authored_abilities(enemy):
        if enemy.ability_timers.get(ability.key, 0.0) > 0.0:
            continue
        if not (ability.min_range < distance <= ability_attack_range(enemy, ability)):
            continue
        candidates.append(ability.key)
    if candidates:
        for key in candidates:
            if key != enemy.last_ability:
                return key
        return candidates[0]
    if BOSS_CAST_MIN_RANGE < distance <= BOSS_CAST_MAX_RANGE:
        return LEGACY_CAST_KEY
    if distance <= enemy.attack_range:
        return LEGACY_MELEE_KEY
    return None
