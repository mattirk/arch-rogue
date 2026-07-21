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

"""Sprite and UI-asset pipeline package.

Re-exports the public names of the procedural sprite atlas, the runtime asset
library/atlas, and the UI asset library so callers can import everything from
``arch_rogue.sprites`` regardless of which submodule owns the implementation.
"""

from __future__ import annotations

from .library import (
    BAR_WALL_SCONCE_DIRECTION_BY_FACE,
    DIRECTIONS,
    GOLD_STACK_ASSET_KEYS,
    STAGE_PROP_ASSET_KEYS,
    AssetSpriteLibrary,
    ResolvedSpriteFrame,
    SpriteAtlas,
)
from .procedural import PixelSpriteAtlas
from .ui_assets import UiAssetLibrary

__all__ = [
    "AssetSpriteLibrary",
    "BAR_WALL_SCONCE_DIRECTION_BY_FACE",
    "DIRECTIONS",
    "GOLD_STACK_ASSET_KEYS",
    "PixelSpriteAtlas",
    "ResolvedSpriteFrame",
    "STAGE_PROP_ASSET_KEYS",
    "SpriteAtlas",
    "UiAssetLibrary",
]