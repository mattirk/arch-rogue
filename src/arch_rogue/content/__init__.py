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

from .archetypes import ARCHETYPES, DUNGEON_THEMES
from .definitions import (
    BossDefinition,
    DifficultyProfile,
    EncounterTemplate,
    EnemyDefinition,
    EquipmentDefinition,
    InteractionHint,
    RarityProfile,
    StoryBackstory,
    StoryDilemmaTemplate,
    StoryFaction,
    StoryGuestTemplate,
    StoryLocationMotif,
    StoryRelic,
)
from .difficulty import (
    DEFAULT_DIFFICULTY_NAME,
    DIFFICULTY_PROFILES,
    HELL_DIFFICULTY_NAME,
)
from .enemies import (
    BOSS_DEFINITIONS,
    ENCOUNTER_TEMPLATES,
    ENEMY_DEFINITIONS,
    FINAL_ROOM_ENEMY_DEFINITIONS,
    HUMANOID_ENEMY_NAMES,
)
from .equipment import (
    AFFIX_DEFINITIONS,
    ARMOR_DEFINITIONS,
    RARITY_AFFIX_COUNTS,
    RARITY_AFFIX_ROLL_RANGES,
    RARITY_PROFILES,
    UNIQUE_ITEM_DEFINITIONS,
    WEAPON_DEFINITIONS,
    AffixDefinition,
    UniqueItemDefinition,
)
from .interactables import (
    SECRET_HINTS,
    SECRET_TYPES,
    SHRINE_HINTS,
    SHRINE_TYPES,
    TRAP_DEFINITIONS,
    TRAP_HINTS,
)
from .progression import (
    COMBO_BONUS_PER_STEP_MAX_HP,
    COMBO_BONUS_PER_STEP_MELEE,
    COMBO_BONUS_PER_STEP_SPELL,
    COMPLETED_PATH_BONUS_MAX_HP,
    COMPLETED_PATH_BONUS_MELEE,
    COMPLETED_PATH_BONUS_SPELL,
    ELITE_MODIFIERS,
    LEGACY_DISCIPLINE_KEYS,
    MAX_COMMITTED_PATHS,
    RUN_MODIFIERS,
    DISCIPLINES,
    DISCIPLINE_UPGRADES,
    path_progress,
    combo_bonus,
    combo_bonus_preview,
    combo_bonus_steps,
    committed_paths,
    completed_path_bonus,
    completed_paths,
    cross_path_tag_bonus,
    is_path_locked,
    migrate_discipline_keys,
    discipline_path_nodes,
    discipline_paths_for_archetype,
    discipline_by_key,
    disciplines_for_archetype,
    max_discipline_degree,
)
from .story_corpus import (
    STORY_BACKSTORIES,
    STORY_CORPUS,
    STORY_DILEMMAS,
    STORY_FACTIONS,
    STORY_GUEST_TEMPLATES,
    STORY_LOCATION_MOTIFS,
    STORY_RELICS,
)

__all__ = [
    "AFFIX_DEFINITIONS",
    "ARCHETYPES",
    "ARMOR_DEFINITIONS",
    "AffixDefinition",
    "BOSS_DEFINITIONS",
    "BossDefinition",
    "DEFAULT_DIFFICULTY_NAME",
    "DIFFICULTY_PROFILES",
    "DUNGEON_THEMES",
    "DifficultyProfile",
    "COMBO_BONUS_PER_STEP_MAX_HP",
    "COMBO_BONUS_PER_STEP_MELEE",
    "COMBO_BONUS_PER_STEP_SPELL",
    "COMPLETED_PATH_BONUS_MAX_HP",
    "COMPLETED_PATH_BONUS_MELEE",
    "COMPLETED_PATH_BONUS_SPELL",
    "ELITE_MODIFIERS",
    "ENCOUNTER_TEMPLATES",
    "ENEMY_DEFINITIONS",
    "EncounterTemplate",
    "EnemyDefinition",
    "EquipmentDefinition",
    "FINAL_ROOM_ENEMY_DEFINITIONS",
    "HELL_DIFFICULTY_NAME",
    "HUMANOID_ENEMY_NAMES",
    "InteractionHint",
    "LEGACY_DISCIPLINE_KEYS",
    "MAX_COMMITTED_PATHS",
    "RARITY_AFFIX_COUNTS",
    "RARITY_AFFIX_ROLL_RANGES",
    "RARITY_PROFILES",
    "RUN_MODIFIERS",
    "RarityProfile",
    "SECRET_HINTS",
    "SECRET_TYPES",
    "SHRINE_HINTS",
    "SHRINE_TYPES",
    "DISCIPLINE_UPGRADES",
    "DISCIPLINES",
    "path_progress",
    "committed_paths",
    "is_path_locked",
    "STORY_BACKSTORIES",
    "STORY_CORPUS",
    "STORY_DILEMMAS",
    "STORY_FACTIONS",
    "STORY_GUEST_TEMPLATES",
    "STORY_LOCATION_MOTIFS",
    "STORY_RELICS",
    "StoryBackstory",
    "StoryDilemmaTemplate",
    "StoryFaction",
    "StoryGuestTemplate",
    "StoryLocationMotif",
    "StoryRelic",
    "combo_bonus",
    "combo_bonus_preview",
    "combo_bonus_steps",
    "completed_path_bonus",
    "completed_paths",
    "cross_path_tag_bonus",
    "migrate_discipline_keys",
    "discipline_path_nodes",
    "discipline_paths_for_archetype",
    "discipline_by_key",
    "disciplines_for_archetype",
    "max_discipline_degree",
    "TRAP_DEFINITIONS",
    "TRAP_HINTS",
    "UNIQUE_ITEM_DEFINITIONS",
    "UniqueItemDefinition",
    "WEAPON_DEFINITIONS",
]
