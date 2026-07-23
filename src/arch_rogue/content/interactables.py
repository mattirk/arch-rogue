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

from .definitions import InteractionHint


TRAP_DEFINITIONS = (
    ("Spike Trap", 14, 22),
    ("Rune Trap", 13, 21),
    ("Poison Needle", 10, 18),
)

SHRINE_TYPES = (
    "Mending Shrine",
    "Insight Shrine",
    "War Shrine",
    "Haste Shrine",
    "Fortune Shrine",
    "Oath Shrine",
    "Twilight Shrine",
)
SECRET_TYPES = (
    "Hidden Cache",
    "Cursed Reliquary",
    "Sealed Armory",
    "Forgotten Skill Altar",
    "Moonlit Bargain",
)

SHRINE_HINTS: dict[str, InteractionHint] = {
    "Mending Shrine": InteractionHint(
        "Mending Shrine", "Restores health and mana.", (105, 230, 125)
    ),
    "Insight Shrine": InteractionHint(
        "Insight Shrine", "Reveals unidentified inventory gear.", (145, 205, 255)
    ),
    "War Shrine": InteractionHint(
        "War Shrine", "Grants combat focus and XP.", (245, 170, 90)
    ),
    "Haste Shrine": InteractionHint(
        "Haste Shrine", "Refreshes stamina and quickens movement.", (235, 220, 95)
    ),
    "Fortune Shrine": InteractionHint(
        "Fortune Shrine", "Spills extra offerings and loot.", (245, 215, 90)
    ),
    "Oath Shrine": InteractionHint(
        "Oath Shrine", "Attempts to grant a class upgrade.", (190, 150, 245)
    ),
    "Twilight Shrine": InteractionHint(
        "Twilight Shrine", "Trades blood for a unique relic.", (214, 92, 150)
    ),
    "Vigil Shrine": InteractionHint(
        "Vigil Shrine", "Grants another Raise for a fallen ally.", (240, 228, 160)
    ),
}

SECRET_HINTS: dict[str, InteractionHint] = {
    "Hidden Cache": InteractionHint(
        "Hidden Cache", "Open for a concealed reward.", (235, 205, 120)
    ),
    "Cursed Reliquary": InteractionHint(
        "Cursed Reliquary", "May awaken a guardian for reward.", (214, 92, 150)
    ),
    "Sealed Armory": InteractionHint(
        "Sealed Armory", "Contains equipment choices.", (245, 215, 90)
    ),
    "Forgotten Skill Altar": InteractionHint(
        "Forgotten Skill Altar", "Deepens your class build.", (145, 205, 255)
    ),
    "Moonlit Bargain": InteractionHint(
        "Moonlit Bargain", "Costs blood for rare gear.", (214, 92, 150)
    ),
}

TRAP_HINTS: dict[str, InteractionHint] = {
    "Spike Trap": InteractionHint(
        "Spike Trap", "Pressure plate; step away fast.", (245, 95, 70)
    ),
    "Rune Trap": InteractionHint(
        "Rune Trap", "Arcane sigil; avoid the glow.", (180, 120, 245)
    ),
    "Poison Needle": InteractionHint(
        "Poison Needle", "Needle trigger; keep distance.", (120, 210, 110)
    ),
}

