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
"""Discipline tree progression: available-discipline queries, discipline state, choose/grant discipline, combo-bonus deltas, combo/cross-path state, preview."""
# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

from ..content import (
    DISCIPLINE_UPGRADES,
    combo_bonus,
    completed_paths,
    cross_path_tag_bonus,
    is_path_locked,
    discipline_by_key,
    disciplines_for_archetype,
)
from ..models import (
    FloatingText,
)


class _DisciplinesCombatMixin:
    def skill_names(self) -> tuple[str, str, str, str]:
        names = {
            "Warden": ("Shield Bash", "Guard Bolt", "Time Skip", "Guard Step"),
            "Rogue": ("Backstab", "Knife Fan", "Ambush Bell", "Shadow Dash"),
            "Arcanist": ("Mage Strike", "Arc Bolt", "Frost Nova", "Blink"),
            "Acolyte": ("Blood Rite", "Spirit Bolt", "Spirit Call", "Dark Step"),
            "Ranger": ("Hawk Slash", "Multishot", "Spirit Beast", "Vault"),
        }
        return names.get(self.player.class_name, ("Slash", "Bolt", "Nova", "Dash"))
    def available_disciplines(self) -> list:
        """Disciplines the player can choose right now.

        A discipline is available when it belongs to the player's archetype, is not
        yet acquired, every prerequisite discipline has already been acquired, and
        its path has not been locked by the two-path commitment limit
        (Milestone 3.7). Degree-1 disciplines are always available until taken, unless
        their path is locked.
        """
        acquired = set(self.player.skill_upgrades)
        choices: list = []
        for node in disciplines_for_archetype(self.player.class_name):
            if node.key in acquired:
                continue
            if is_path_locked(acquired, node.archetype, node.path):
                continue
            if all(prereq in acquired for prereq in node.prerequisites):
                choices.append(node)
        return choices

    def discipline_state(self, node) -> str:
        """Return one of "chosen", "available", "path_locked", "locked".

        "path_locked" (Milestone 3.7) marks disciplines whose path is sealed by
        the two-path commitment limit and is distinct from "locked" so the
        menu can render the two reasons differently.
        """
        acquired = set(self.player.skill_upgrades)
        if node.key in acquired:
            return "chosen"
        if is_path_locked(acquired, node.archetype, node.path):
            return "path_locked"
        if all(prereq in acquired for prereq in node.prerequisites):
            return "available"
        return "locked"

    def choose_discipline(self, key: str, reason: str = "chosen") -> bool:
        """Apply a specific discipline by key, spending one mastery token.

        Returns False (without spending a point) if the discipline is unknown, belongs
        to another archetype, is already acquired, has unmet prerequisites, is
        in a path locked by the commitment limit, or the player has no mastery
        tokens to spend.
        """
        if self.mp_is_joiner():
            # Disciplines are player-owned; the host validates and applies the
            # choice, and the result returns through the next snapshot.
            self.mp_queue_action("choose_discipline", key)
            return False
        node = discipline_by_key(key)
        if node is None or node.archetype != self.player.class_name:
            return False
        if node.key in self.player.skill_upgrades:
            return False
        if not all(
            prereq in self.player.skill_upgrades for prereq in node.prerequisites
        ):
            return False
        if is_path_locked(
            set(self.player.skill_upgrades), node.archetype, node.path
        ):
            return False
        if self.player.mastery_tokens <= 0:
            return False
        self.player.mastery_tokens -= 1
        self._apply_discipline(node, reason)
        self._apply_combo_bonus_delta(node)
        return True

    def grant_mastery_token(self, amount: int = 1, reason: str = "reward") -> None:
        """Award mastery tokens from run rewards (shrines, altars, story)."""
        if amount <= 0:
            return
        self.player.mastery_tokens += amount
        self.floaters.append(
            FloatingText(
                f"+{amount} Mastery Token{'s' if amount != 1 else ''}",
                self.player.x,
                self.player.y - 0.6,
                self.skill_color(),
                ttl=1.6,
            )
        )

    def _apply_discipline(self, node, reason: str) -> None:
        self.player.skill_upgrades.append(node.key)
        self.player.melee_bonus += node.melee_bonus
        self.player.spell_bonus += node.spell_bonus
        self.player.armor_bonus += node.armor_bonus
        self.player.max_hp += node.max_hp_bonus
        self.player.hp = min(self.player.max_hp, self.player.hp + node.max_hp_bonus)
        self.player.max_mana += node.max_mana_bonus
        self.player.mana = min(
            self.player.max_mana, self.player.mana + node.max_mana_bonus
        )
        self.player.max_stamina += node.max_stamina_bonus
        self.player.stamina = min(
            self.player.max_stamina, self.player.stamina + node.max_stamina_bonus
        )
        self.player.speed += node.speed_bonus
        self.run_stats.upgrades_chosen += 1
        self.floaters.append(
            FloatingText(
                f"{node.name}: {reason}",
                self.player.x,
                self.player.y - 0.65,
                self.skill_color(),
                ttl=1.8,
            )
        )
        if node.archetype == "Ranger" and node.path == "Beast":
            self._refresh_active_spirit_beast()

    def _apply_combo_bonus_delta(self, node) -> None:
        """Apply the combo-bonus delta caused by acquiring `node`.

        Called after a discipline is chosen. If the acquisition completed a new
        path and pushed the player into a higher combo tier, the delta is
        applied to the player's derived stats so the bonus is felt immediately.
        """
        acquired = set(self.player.skill_upgrades)
        melee, spell, max_hp = combo_bonus(acquired, self.player.class_name)
        # Track the cumulative combo bonus already applied so we only apply the
        # delta on changes. Stored on the player as a private attribute.
        prev = getattr(self.player, "_combo_applied", (0, 0, 0))
        d_melee = melee - prev[0]
        d_spell = spell - prev[1]
        d_hp = max_hp - prev[2]
        if d_melee or d_spell or d_hp:
            self.player.melee_bonus += d_melee
            self.player.spell_bonus += d_spell
            self.player.max_hp += d_hp
            self.player.hp = min(self.player.max_hp, self.player.hp + d_hp)
        self.player._combo_applied = (melee, spell, max_hp)

    def combo_state(self) -> tuple[tuple[str, ...], int, int, int]:
        """Return (completed_paths, melee_bonus, spell_bonus, max_hp_bonus).

        Cheap O(nodes) lookup with no per-frame allocations beyond the returned
        tuple; safe to call from the hot path or the character sheet.
        """
        acquired = set(self.player.skill_upgrades)
        done = completed_paths(acquired, self.player.class_name)
        melee, spell, max_hp = combo_bonus(acquired, self.player.class_name)
        return (done, melee, spell, max_hp)

    def cross_path_bonus_state(self) -> tuple[int, int]:
        """Return (melee, spell) bonus from acquired cross-path modifiers."""
        return cross_path_tag_bonus(set(self.player.skill_upgrades))

    def combo_preview(self, node) -> tuple[int, int, int]:
        """Combo bonus if `node` were acquired next (for sheet hover preview)."""
        from ..content import combo_bonus_preview

        return combo_bonus_preview(
            set(self.player.skill_upgrades), self.player.class_name, node.key
        )

    def grant_discipline(self, reason: str = "level up") -> bool:
        """Grant a random available discipline, respecting discipline tree prerequisites.

        Used by shrines/altars/story rewards. These are bonus grants that do
        NOT spend the player's banked mastery tokens (level-up tokens are spent
        by the player via `choose_discipline`). Falls back to the flat
        `DISCIPLINE_UPGRADES` pool only if the discipline tree yields no available disciplines.
        """
        choices = self.available_disciplines()
        if not choices:
            legacy_choices = [
                upgrade
                for upgrade in DISCIPLINE_UPGRADES
                if upgrade.archetype == self.player.class_name
                and upgrade.key not in self.player.skill_upgrades
            ]
            if not legacy_choices:
                return False
            upgrade = self.rng.choice(legacy_choices)
            node = discipline_by_key(upgrade.key)
            if node is not None:
                self._apply_discipline(node, reason)
                self._apply_combo_bonus_delta(node)
                return True
            return False
        node = self.rng.choice(choices)
        self._apply_discipline(node, reason)
        self._apply_combo_bonus_delta(node)
        return True
