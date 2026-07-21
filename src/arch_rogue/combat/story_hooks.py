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
"""Story-gated combat damage and HP-cost hooks.

These three helpers are called exclusively from the ``combat/`` package
(attacks, ambush_bell, familiars) and implement combat operations -- a
player damage multiplier and an HP-cost payment -- that are gated by run
story state. They read story state via ``self.story_effect_value(...)`` and
``self.story_state`` (both owned by :mod:`arch_rogue.story_runtime`); no
story-runtime behavior lives here.
"""
# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

from ..models import FloatingText


class _StoryHooksCombatMixin:
    def story_player_damage_bonus(self, spell: bool = False) -> float:
        damage = self.story_effect_value("damage_bonus", 0.0, 0.35)
        relic = self.story_effect_value("relic_power", 0.0, 0.35)
        relic_weight = 1.0 if spell else 0.6
        return min(0.55, damage + relic * relic_weight)

    def apply_story_player_damage(self, damage: int, spell: bool = False) -> int:
        bonus = self.story_player_damage_bonus(spell=spell)
        if bonus <= 0:
            return max(1, damage)
        return max(1, int(round(damage * (1.0 + bonus))))

    def apply_story_blood_price(self, reason: str) -> int:
        price = self.story_effect_value("blood_price", 0.0, 0.35)
        if price <= 0 or self.player.hp <= 1:
            return 0
        cost = max(
            1,
            min(10, int(round(self.player.max_hp * (0.015 + price * 0.18)))),
        )
        actual = min(cost, self.player.hp - 1)
        if actual <= 0:
            return 0
        self.player.hp -= actual
        self.run_stats.damage_taken += actual
        self.floaters.append(
            FloatingText(
                f"{reason.title()} blood price -{actual}",
                self.player.x,
                self.player.y - 0.55,
                self.story_state.accent if self.story_state else (190, 60, 85),
                ttl=1.0,
            )
        )
        self.add_impact(
            self.player.x,
            self.player.y,
            self.story_state.accent if self.story_state else (190, 60, 85),
            ttl=0.36,
            radius=0.42,
            kind="blood",
        )
        return actual
