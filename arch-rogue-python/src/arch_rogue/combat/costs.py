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
"""Resource cost and cooldown getters: melee/bolt stamina+mana+cooldowns, class-skill mana+cooldown, time-skip factor/duration, enemy time scale, dash cost+cooldown, big-hit trio."""
# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

from ._utils import (
    BIGHIT_CANCEL_COOLDOWN,
    BIGHIT_CHARGE_TIME,
    BIGHIT_COOLDOWN,
    BIGHIT_STAMINA_COST,
)

# 5.0 mana economy: idle regen no longer refills any pool in well under half a
# minute (4.x refilled every class in 8-12 s, which made the Lesser Mana
# Potion pointless). The Arcanist keeps a small innate edge; deeper recovery
# is a Discipline-tree choice — Nova/Ward degree-one nodes for the Arcanist,
# Veil/Curse degree-one nodes for the Acolyte — so committed casters can build
# back toward a sustained casting loop while everyone else shops for potions.
PLAYER_STAMINA_REGEN = 30.0
RANGER_STAMINA_REGEN = 38.0
RANGER_SNARE_STAMINA_BONUS = 4.0
PLAYER_MANA_REGEN = 2.5
ARCANIST_MANA_REGEN = 3.5
MANA_REGEN_UPGRADES: dict[str, float] = {
    "arcanist_focus": 2.5,
    "arcanist_ward": 1.5,
    "acolyte_veil": 2.0,
    "acolyte_curse": 1.5,
}


# 5.0 speed rework ("make buffs real, capped"): player locomotion still runs
# on the fixed PLAYER_MOVE_SPEED base, but every speed source the game SHOWS
# now feeds one real, clamped multiplier instead of the inert ``player.speed``
# stat: the archetype's speed rating (relative to the 3.5 baseline), the
# equipment ``move_speed`` affixes, the Rogue/Ranger discipline speed nodes
# (rescaled — their ratings were authored for the 3.25-3.95 stat scale), and
# the Haste Shrine's capped stride blessing. The total clamp matches the
# [-0.25, 0.30] window multiplayer prediction already budgets for
# (net/sync._PREDICTION_EQUIPMENT_SPEED_CAP == 1.30), so co-op needs no new
# ceiling and old saves cannot smuggle in unbounded stacks.
ARCHETYPE_MOVE_RATING_BASELINE = 3.5
DISCIPLINE_SPEED_TO_MOVE = 0.25
HASTE_SHRINE_MOVE_BONUS = 0.03
HASTE_SHRINE_MOVE_BONUS_CAP = 0.09
PLAYER_MOVE_BONUS_MIN = -0.25
PLAYER_MOVE_BONUS_MAX = 0.30


def archetype_move_bonus(speed_rating: float) -> float:
    """Move-speed fraction contributed by an archetype's speed rating."""

    baseline = ARCHETYPE_MOVE_RATING_BASELINE
    return (float(speed_rating) - baseline) / baseline


def player_recovery_rates(actor) -> tuple[float, float]:
    """(stamina/s, mana/s) for a player-shaped actor.

    Shared by the local simulation (combat/player.update_player) and the
    host-side co-op partner simulation (net/mixin._mp_update_remote_player)
    so the two can never drift apart.
    """

    stamina = (
        RANGER_STAMINA_REGEN
        if actor.class_name == "Ranger"
        else PLAYER_STAMINA_REGEN
    )
    if actor.has_upgrade("ranger_snare"):
        stamina += RANGER_SNARE_STAMINA_BONUS
    mana = (
        ARCANIST_MANA_REGEN
        if actor.class_name == "Arcanist"
        else PLAYER_MANA_REGEN
    )
    for key, bonus in MANA_REGEN_UPGRADES.items():
        if actor.has_upgrade(key):
            mana += bonus
    return stamina, mana


class _CostsCombatMixin:
    def player_attack_speed(self) -> float:
        """Clamped attack-speed stat from equipment (range [-0.20, 0.35]).

        Single source of truth for melee haste: ``melee_cooldown`` consumes
        it and it is the seam future disciplines/affixes hook into to speed
        up attack visuals without touching every attack method.
        """
        return max(-0.20, min(0.35, self.equipment_stat_total("attack_speed")))

    def player_cast_speed(self) -> float:
        """Clamped cast-speed stat from equipment (range [-0.20, 0.35])."""
        return max(-0.20, min(0.35, self.equipment_stat_total("cast_speed")))

    def player_move_speed(self) -> float:
        """Total move-speed multiplier bonus, clamped to [-0.25, 0.30].

        Single source of truth for ground speed (5.0): consumed by
        ``update_player``, the host's co-op partner sim, and the joiner's
        prediction, all of which run with ``self.player`` pointing at the
        actor being simulated. Folds archetype rating, equipment affixes,
        discipline speed nodes, and the Haste Shrine blessing into the one
        clamped channel multiplayer prediction budgets for.
        """

        from ..content import (
            ARCHETYPE_SPEED_BY_NAME,
            DISCIPLINE_SPEED_BONUS_BY_KEY,
        )

        actor = self.player
        bonus = self.equipment_stat_total("move_speed")
        rating = ARCHETYPE_SPEED_BY_NAME.get(actor.class_name)
        if rating is not None:
            bonus += archetype_move_bonus(rating)
        for key in actor.skill_upgrades:
            node_speed = DISCIPLINE_SPEED_BONUS_BY_KEY.get(key)
            if node_speed:
                bonus += node_speed * DISCIPLINE_SPEED_TO_MOVE
        bonus += getattr(actor, "shrine_move_bonus", 0.0)
        return max(PLAYER_MOVE_BONUS_MIN, min(PLAYER_MOVE_BONUS_MAX, bonus))

    def melee_stamina_cost(self) -> int:
        cost = 9 if self.player.class_name == "Rogue" else 12
        if self.player.has_upgrade("rogue_precision"):
            cost -= 2
        if self.equipment_skill_bonus("Melee"):
            cost -= 1
        if any(
            item is not None and item.cursed for item in self.player.equipment.values()
        ):
            cost += 1
        return max(5, cost)

    def melee_cooldown(self) -> float:
        cooldown = 0.30 if self.player.class_name == "Rogue" else 0.36
        if self.player.has_upgrade("warden_bulwark"):
            cooldown += 0.02
        if self.equipment_skill_bonus("Melee"):
            cooldown -= 0.03
        attack_speed = self.player_attack_speed()
        cooldown *= 1.0 - attack_speed
        return max(0.20, cooldown)

    def bolt_mana_cost(self) -> int:
        cost = 7 if self.player.class_name in ("Arcanist", "Ranger") else 10
        # Storm Degree 1 makes Arc Bolt the path's efficient, repeatable
        # lightning action. Deeper Storm nodes then add bounded chain jumps.
        if self.player.class_name == "Arcanist" and self.player.has_upgrade(
            "arcanist_charge"
        ):
            cost -= 1
        if self.equipment_skill_bonus("Bolt"):
            cost -= 1
        if any(
            item is not None and item.cursed for item in self.player.equipment.values()
        ):
            cost += 1
        return max(4, cost)

    def bolt_cooldown(self) -> float:
        cooldown = 0.38 if self.player.class_name in ("Arcanist", "Ranger") else 0.48
        if self.equipment_skill_bonus("Bolt"):
            cooldown -= 0.04
        cast_speed = self.player_cast_speed()
        cooldown *= 1.0 - cast_speed
        return max(0.22, cooldown)

    def class_skill_mana_cost(self) -> int | float:
        """Mana cost for the archetype class skill bound to hotkey 3."""
        if self.player.class_name == "Ranger":
            # Summoning Spirit Beast always costs exactly half of the current
            # maximum mana. Commands issued while it is alive are free.
            return self.player.max_mana * 0.5
        cost = 14 if self.player.class_name in ("Arcanist", "Acolyte") else 18
        if self.player.has_upgrade("acolyte_veil"):
            cost -= 2
        # Warden Time path Degree 1 (Temporal Sigil) discounts the class-skill budget.
        if self.player.class_name == "Warden" and self.player.has_upgrade("warden_ward"):
            cost -= 1
        if self.equipment_class_skill_bonus():
            cost -= 1
        if any(
            item is not None and item.cursed for item in self.player.equipment.values()
        ):
            cost += 2
        return max(8, cost)

    def class_skill_cooldown(self) -> float:
        """Cooldown before an absent archetype class summon can be used again."""
        if self.player.class_name == "Ranger":
            # This gates replacement summons only; a living Spirit Beast can
            # still receive free return/attack commands while the timer runs.
            return 60.0
        cooldown = 2.65 if self.player.class_name == "Arcanist" else 3.2
        # Warden Time path Degree 1 (Temporal Sigil) cools the class skill faster.
        if self.player.class_name == "Warden" and self.player.has_upgrade("warden_ward"):
            cooldown -= 0.3
        if self.equipment_class_skill_bonus():
            cooldown -= 0.18
        cast_speed = self.player_cast_speed()
        cooldown *= 1.0 - cast_speed * 0.75
        return max(1.85, cooldown)

    def time_skip_factor(self) -> float:
        """Enemy simulation speed while Time Skip is active (lower = slower)."""
        # Milestone 3.18.1 — Time path Degree 3 (Stutter Step) deepens the slow.
        if self.player.has_upgrade("warden_stone_aegis"):
            return 0.3
        return 0.4

    def time_skip_duration(self) -> float:
        """How long Time Skip slows enemies, in seconds."""
        duration = 3.0
        # Time path scaling (Degree 1 Temporal Sigil, Degree 2 Time Skip).
        if self.player.has_upgrade("warden_ward"):
            duration += 0.5
        if self.player.has_upgrade("warden_bulwark_wave"):
            duration += 1.0
        if self.equipment_class_skill_bonus("Time Skip duration"):
            duration += 0.5
        return duration

    def enemy_time_scale(
        self, dt: float = 0.0, *, remaining: float | None = None
    ) -> float:
        """Average enemy simulation multiplier across this update interval."""
        ttl = self.player.time_skip_timer if remaining is None else remaining
        if ttl <= 0.0:
            return 1.0
        factor = self.time_skip_factor()
        if dt > 0.0 and ttl < dt:
            active_fraction = max(0.0, min(1.0, ttl / dt))
            return 1.0 - (1.0 - factor) * active_fraction
        return factor

    def dash_stamina_cost(self) -> int:
        cost = 12 if self.player.class_name in ("Rogue", "Ranger") else 18
        if self.player.has_upgrade("rogue_smoke"):
            cost -= 2
        if self.equipment_skill_bonus("Dash"):
            cost -= 2
        return max(8, cost)

    def dash_cooldown(self) -> float:
        cooldown = 0.62 if self.player.class_name == "Ranger" else 0.85
        if self.equipment_skill_bonus("Dash tempo"):
            cooldown -= 0.08
        return max(0.48, cooldown)

    # Big Hit is deliberately flat across archetypes and gear in v1: charge
    # time, cost, and cooldown are the balance levers we want to feel out
    # before disciplines or attack-speed affixes are allowed to bend them.
    def bighit_stamina_cost(self) -> int:
        return BIGHIT_STAMINA_COST

    def bighit_cooldown(self) -> float:
        return BIGHIT_COOLDOWN

    def bighit_cancel_cooldown(self) -> float:
        return BIGHIT_CANCEL_COOLDOWN

    def bighit_charge_time(self) -> float:
        return BIGHIT_CHARGE_TIME
