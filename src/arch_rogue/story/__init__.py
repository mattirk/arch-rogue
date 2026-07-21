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

"""Story / quest / friendly-NPC runtime package.

Re-exports the public API of the story engine, the story runtime mixin, the
friendly-NPC runtime mixin, and the quest cutscene asset library so callers can
import everything from ``arch_rogue.story`` regardless of which submodule owns
the implementation.

Note: this package takes over the ``arch_rogue.story`` name that previously
resolved to the standalone ``story.py`` module; the package ``__init__.py`` is
itself the backward-compatibility facade for the old ``from arch_rogue.story
import ...`` import path.
"""

from __future__ import annotations

from .engine import (
    BASE_STORY_EFFECTS,
    StoryEngine,
    clamp_story_effect,
    record_story_choice,
    record_unanswered_story_beat,
    story_beat_for_depth,
    story_beat_from_dict,
    story_beat_index_for_depth,
    story_beat_to_dict,
    story_choice_from_dict,
    story_choice_to_dict,
    story_effect,
    story_guest_from_beat,
    story_guest_from_dict,
    story_guest_to_dict,
    story_state_from_dict,
    story_state_to_dict,
)
from .npc_runtime import FriendlyNpcMotion, FriendlyNpcRuntimeMixin
from .quest_assets import (
    ActiveQuestCutscene,
    AmbientEffectAsset,
    CurtainAsset,
    CutsceneActorAsset,
    DialogueChoiceAsset,
    DialogueNodeAsset,
    QuestCutsceneAsset,
    RuntimeDialogueChoice,
    SpriteAnimationAsset,
    SpriteAnimationFrameAsset,
    StageAsset,
    StageLightAsset,
    StagePropAsset,
    format_asset_text,
    load_quest_cutscene_library,
)
from .runtime import StoryRuntimeMixin

__all__ = [
    "ActiveQuestCutscene",
    "AmbientEffectAsset",
    "BASE_STORY_EFFECTS",
    "CurtainAsset",
    "CutsceneActorAsset",
    "DialogueChoiceAsset",
    "DialogueNodeAsset",
    "FriendlyNpcMotion",
    "FriendlyNpcRuntimeMixin",
    "QuestCutsceneAsset",
    "RuntimeDialogueChoice",
    "SpriteAnimationAsset",
    "SpriteAnimationFrameAsset",
    "StageAsset",
    "StageLightAsset",
    "StagePropAsset",
    "StoryEngine",
    "StoryRuntimeMixin",
    "clamp_story_effect",
    "format_asset_text",
    "load_quest_cutscene_library",
    "record_story_choice",
    "record_unanswered_story_beat",
    "story_beat_for_depth",
    "story_beat_from_dict",
    "story_beat_index_for_depth",
    "story_beat_to_dict",
    "story_choice_from_dict",
    "story_choice_to_dict",
    "story_effect",
    "story_guest_from_beat",
    "story_guest_from_dict",
    "story_guest_to_dict",
    "story_state_from_dict",
    "story_state_to_dict",
]