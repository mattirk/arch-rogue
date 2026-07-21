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

"""``arch_rogue.combat`` package.

Milestone 4.5 Phase 2: the previous monolithic ``CombatMixin`` (``combat.py``)
has been split into focused submixins, one per combat subsystem. Each submodule
exposes a ``_<Name>CombatMixin`` and contributes its methods to ``CombatMixin``
via multiple inheritance. Method bodies and signatures are unchanged from the
pre-split module; behavior is bit-for-bit identical. The submixins share state
through ``self.`` exactly as the single mixin did.

Submodule map:

- :mod:`.equipment`     — damage-type colors, equipment stat totals, proc/unique rolls, lifesteal, thorns.
- :mod:`.statuses`      — player/enemy status effects, slow factors, locomotion scales, mitigation.
- :mod:`.aim`           — controller aim snap, analog/keyboard/mouse aim, facing.
- :mod:`.disciplines`   — discipline tree progression, combo/cross-path state, grants.
- :mod:`.class_skills`  — class-skill dispatch metadata (kind/cast/bonus/color tables).
- :mod:`.costs`         — stamina/mana/cooldown getters, time-skip, dash costs.
- :mod:`.player`        — player damage intake, thorns reflect, per-frame update, garden healing.
- :mod:`.movement`      — actor movement, locomotion, animation phases, hit radii, contacts.
- :mod:`.enemies`       — enemy AI update, melee swing, spell cast.
- :mod:`.projectiles`   — projectile sim, homing, chain lightning, acolyte leech, traps.
- :mod:`.attacks`       — player melee/bolt/nova/time-skip casts.
- :mod:`.ambush_bell`   — Rogue Ambush Bell subsystem.
- :mod:`.familiars`     — Acolyte familiars and Ranger Spirit Beast.
- :mod:`.mobility`      — player dash and melee-arc targeting helpers.
- :mod:`.damage`        — damage application primitives, lifesteal, chain proc, kill rewards, hit flash.
- :mod:`.story_hooks`   — story-gated combat damage multiplier and HP-cost hooks (read story state via ``story_runtime``).

Phase 3 will pull shared helpers into ``combat/_utils.py``, centralize
damage-type/resistance lookups in ``combat/damage_types.py``, and tighten
type hints. Phase 4 will add opt-in ARPG improvements (``DamageContext``,
unified resistance table, crit refactor, attack-speed getter, knockback
fields, telegraph helper, ``ClassSkill`` registry).

Preserves the historical public surface::

    from arch_rogue.combat import CombatMixin
"""

from .aim import _AimCombatMixin
from .ambush_bell import _AmbushBellCombatMixin
from .attacks import _AttacksCombatMixin
from .class_skills import _ClassSkillsCombatMixin
from .costs import _CostsCombatMixin
from .damage import _DamageCombatMixin
from .disciplines import _DisciplinesCombatMixin
from .enemies import _EnemiesCombatMixin
from .equipment import _EquipmentCombatMixin
from .familiars import _FamiliarsCombatMixin
from .mobility import _MobilityCombatMixin
from .movement import _MovementCombatMixin
from .player import _PlayerCombatMixin
from .projectiles import _ProjectilesCombatMixin
from .statuses import _StatusesCombatMixin
from .story_hooks import _StoryHooksCombatMixin


class CombatMixin(
    _EquipmentCombatMixin,
    _StatusesCombatMixin,
    _AimCombatMixin,
    _DisciplinesCombatMixin,
    _ClassSkillsCombatMixin,
    _CostsCombatMixin,
    _PlayerCombatMixin,
    _MovementCombatMixin,
    _EnemiesCombatMixin,
    _ProjectilesCombatMixin,
    _AttacksCombatMixin,
    _AmbushBellCombatMixin,
    _FamiliarsCombatMixin,
    _MobilityCombatMixin,
    _StoryHooksCombatMixin,
    _DamageCombatMixin,
):
    """Composition root for all combat subsystems.

    Inherits every combat method from the focused submixins in
    :mod:`arch_rogue.combat`. No methods are defined here; extend an
    individual submodule to add or change combat behavior.
    """


__all__ = ["CombatMixin"]