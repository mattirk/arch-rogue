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

from ..models import Archetype, DungeonTheme

ARCHETYPES = (
    Archetype(
        "Warden",
        "Durable melee fighter with reliable armor and stamina.",
        max_hp=120,
        max_mana=38,
        max_stamina=112,
        speed=3.35,
        melee_bonus=3,
        armor_bonus=2,
    ),
    Archetype(
        "Rogue",
        "Fast striker who trades durability for speed and burst damage.",
        max_hp=92,
        max_mana=42,
        max_stamina=126,
        speed=3.95,
        melee_bonus=5,
    ),
    Archetype(
        "Arcanist",
        "Fragile caster with stronger bolts and novas.",
        max_hp=86,
        max_mana=78,
        max_stamina=94,
        speed=3.25,
        spell_bonus=9,
    ),
    Archetype(
        "Acolyte",
        "Dark priest with balanced defenses and potent rites.",
        max_hp=102,
        max_mana=62,
        max_stamina=98,
        speed=3.30,
        melee_bonus=1,
        spell_bonus=5,
        armor_bonus=1,
    ),
    Archetype(
        "Ranger",
        "Mobile marksman with strong stamina and hybrid damage.",
        max_hp=98,
        max_mana=48,
        max_stamina=120,
        speed=3.70,
        melee_bonus=3,
        spell_bonus=2,
    ),
)

DUNGEON_THEMES = (
    DungeonTheme(
        "Crypt of Ash",
        "charred halls and emberlit stairs",
        floor=(52, 47, 42),
        floor_edge=(72, 66, 60),
        wall_top=(45, 42, 49),
        wall_left=(31, 29, 36),
        wall_right=(24, 23, 30),
        wall_edge=(58, 55, 66),
        stair=(230, 188, 90),
        accent=(240, 145, 65),
    ),
    DungeonTheme(
        "Fungal Catacombs",
        "damp stone, pale spores, and hidden growths",
        floor=(42, 53, 42),
        floor_edge=(65, 82, 59),
        wall_top=(34, 51, 45),
        wall_left=(24, 38, 34),
        wall_right=(20, 31, 32),
        wall_edge=(60, 84, 70),
        stair=(166, 210, 116),
        accent=(110, 185, 95),
    ),
    DungeonTheme(
        "Violet Reliquary",
        "occult vaults humming with void rites",
        floor=(45, 39, 58),
        floor_edge=(78, 65, 103),
        wall_top=(42, 34, 58),
        wall_left=(30, 24, 44),
        wall_right=(25, 20, 38),
        wall_edge=(76, 60, 112),
        stair=(205, 140, 235),
        accent=(160, 86, 230),
    ),
    DungeonTheme(
        "Sunken Bastion",
        "flood-stained battlements and drowned reliquaries",
        floor=(39, 52, 58),
        floor_edge=(60, 82, 92),
        wall_top=(36, 49, 55),
        wall_left=(25, 36, 43),
        wall_right=(20, 31, 38),
        wall_edge=(64, 88, 99),
        stair=(112, 190, 205),
        accent=(86, 188, 215),
    ),
    DungeonTheme(
        "Frozen Ossuary",
        "blue-lit bone vaults where frost silences footsteps",
        floor=(46, 53, 62),
        floor_edge=(76, 91, 110),
        wall_top=(43, 50, 63),
        wall_left=(30, 36, 48),
        wall_right=(24, 30, 42),
        wall_edge=(88, 107, 132),
        stair=(168, 215, 235),
        accent=(128, 206, 242),
    ),
    DungeonTheme(
        "Obsidian Foundry",
        "molten channels, hammering echoes, and ember-lit machinery",
        floor=(55, 43, 38),
        floor_edge=(92, 62, 48),
        wall_top=(49, 38, 35),
        wall_left=(34, 25, 25),
        wall_right=(28, 21, 22),
        wall_edge=(118, 68, 44),
        stair=(245, 132, 72),
        accent=(245, 104, 52),
    ),
    DungeonTheme(
        "Moonlit Aquifer",
        "silver pools, echoing wells, and pale drowned altars",
        floor=(37, 49, 62),
        floor_edge=(62, 82, 106),
        wall_top=(35, 45, 59),
        wall_left=(24, 33, 46),
        wall_right=(19, 28, 39),
        wall_edge=(84, 116, 150),
        stair=(176, 206, 232),
        accent=(145, 184, 232),
    ),
    DungeonTheme(
        "Thornbound Vault",
        "root-split masonry, green witchlight, and hungry brambles",
        floor=(41, 50, 38),
        floor_edge=(62, 82, 52),
        wall_top=(38, 47, 35),
        wall_left=(26, 34, 25),
        wall_right=(22, 29, 21),
        wall_edge=(78, 103, 64),
        stair=(158, 214, 106),
        accent=(126, 214, 92),
    ),
)
