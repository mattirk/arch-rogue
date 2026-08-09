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

from .definitions import (
    BossDefinition,
    EncounterTemplate,
    EnemyAbility,
    EnemyDefinition,
    Tactic,
)

# ---------------------------------------------------------------------------
# 4.8.9 machine intelligence: authored abilities and per-role tactics.
#
# Abilities dispatch through the enemy windup/commit seam; an enemy with no
# authored ability list synthesizes a default strike/bolt from its stat
# columns, reproducing pre-4.8.9 behavior exactly. The reserved keys "melee"
# and "cast" name those synthesized defaults and must not be used here.
# ---------------------------------------------------------------------------

ENEMY_ABILITIES = (
    # Ash Gallows Knight — "ember scars before heavy swings"
    EnemyAbility(
        "ember_cleave",
        "strike",
        damage_multiplier=1.45,
        windup=0.55,
        cooldown=4.5,
    ),
    EnemyAbility(
        "ember_nova",
        "nova",
        damage_multiplier=0.8,
        attack_range=2.6,
        windup=0.45,
        cooldown=6.5,
    ),
    # Mycelial Matron — "controls space with poison bolts and rooting spores"
    EnemyAbility(
        "spore_volley",
        "fan",
        damage_multiplier=0.75,
        min_range=2.0,
        windup=0.55,
        cooldown=5.0,
        projectile_count=4,
        spread=0.42,
        status_effect="poisoned",
        status_duration=1.6,
    ),
    # Rime Chanter — "chill volleys punish straight-line approaches"
    EnemyAbility(
        "frost_fan",
        "fan",
        damage_multiplier=0.65,
        min_range=2.0,
        windup=0.55,
        cooldown=6.0,
        projectile_count=5,
        spread=0.55,
        status_effect="chilled",
        status_duration=1.2,
    ),
    # Voidbound Rune Sentinel — "slow arcane lances with a violet tell"
    EnemyAbility(
        "arcane_lance",
        "bolt",
        damage_multiplier=1.6,
        min_range=2.0,
        windup=0.7,
        cooldown=5.5,
        projectile_speed=8.5,
    ),
    # Dread Gate Tyrant — "alternating melee pressure and shadow casts"
    EnemyAbility(
        "gate_strike",
        "strike",
        damage_multiplier=1.3,
        windup=0.4,
        cooldown=3.2,
    ),
    EnemyAbility(
        "shadow_volley",
        "fan",
        damage_multiplier=0.9,
        min_range=2.0,
        windup=0.45,
        cooldown=4.2,
        projectile_count=3,
        spread=0.3,
    ),
)

ABILITY_INDEX = {ability.key: ability for ability in ENEMY_ABILITIES}

# Movement doctrine per Enemy.role (population's name→trait table). Roles not
# listed fall back to the kind defaults below, which carry the pre-4.8.9
# literals (ranged kite band 2.5–3.5, melee direct close). Boss-family roles
# (floor_boss/boss/challenge_boss) never reach this table — the boss branch
# owns their ranges.
TACTICS = {
    "bruiser": Tactic("bruiser"),
    "mauler": Tactic("mauler"),
    # Guards close directly like bruisers. (An earlier hold-the-post doctrine
    # left damaged guards standing statue-still just outside melee reach —
    # a provoked enemy must always be coming for the player.)
    "guard": Tactic("guard"),
    "flanker": Tactic("flanker", strafe_bias=0.55),
    "skirmisher": Tactic(
        "skirmisher",
        preferred_range=3.0,
        min_range=2.0,
        strafe_bias=0.65,
        reposition_for_los=True,
    ),
    "caster": Tactic(
        "caster",
        preferred_range=3.8,
        min_range=2.2,
        reposition_for_los=True,
    ),
    "marksman": Tactic(
        "marksman",
        preferred_range=4.6,
        min_range=2.8,
        reposition_for_los=True,
    ),
    "artillery": Tactic(
        "artillery",
        preferred_range=3.4,
        min_range=2.6,
        reposition_for_los=True,
    ),
    # hold_anchor (ranged only): stop advancing the moment the target is
    # inside attack range — a sentinel plants itself where it can already
    # fire instead of closing all the way to its preferred band. It never
    # holds where it cannot attack, so it can never stall.
    "sentinel": Tactic(
        "sentinel",
        preferred_range=4.2,
        min_range=2.0,
        hold_anchor=True,
        reposition_for_los=True,
    ),
}

# Kind fallbacks preserving the pre-4.8.9 inline literals exactly.
DEFAULT_RANGED_TACTIC = Tactic("ranged", preferred_range=3.5, min_range=2.5)
DEFAULT_MELEE_TACTIC = Tactic("melee")


ENEMY_DEFINITIONS = (
    EnemyDefinition(
        "Cultist", "ranged", 34, 1.16, 8, 18, 5.4, 1.45, 8.0, (125, 75, 170), 22
    ),
    EnemyDefinition(
        "Bone Imp", "ranged", 26, 1.72, 6, 16, 4.6, 1.0, 8.0, (190, 130, 215), 18
    ),
    EnemyDefinition(
        "Venom Skitter", "melee", 30, 2.08, 7, 15, 0.95, 0.72, 9.5, (110, 185, 95), 16
    ),
    EnemyDefinition(
        "Crypt Brute", "melee", 82, 1.00, 17, 32, 1.35, 1.35, 8.0, (155, 105, 74), 14
    ),
    EnemyDefinition(
        "Ghoul", "melee", 42, 1.56, 10, 20, 1.05, 0.95, 8.0, (160, 68, 68), 22
    ),
    EnemyDefinition(
        "Grave Archer", "ranged", 38, 1.28, 9, 21, 5.8, 1.35, 9.0, (120, 145, 105), 8
    ),
    EnemyDefinition(
        "Ash Hound", "melee", 34, 1.92, 9, 19, 0.95, 0.82, 9.0, (185, 86, 54), 14
    ),
    EnemyDefinition(
        "Rune Sentinel", "ranged", 66, 0.88, 13, 30, 5.2, 1.7, 8.5, (116, 220, 245), 8
    ),
    EnemyDefinition(
        "Plague Toad", "ranged", 54, 1.08, 11, 25, 4.2, 1.55, 7.5, (144, 172, 86), 10
    ),
    EnemyDefinition(
        "Hollow Knight", "melee", 58, 1.40, 13, 29, 1.15, 1.05, 8.5, (126, 132, 128), 9
    ),
)

FINAL_ROOM_ENEMY_DEFINITIONS = ENEMY_DEFINITIONS + (
    EnemyDefinition(
        "Gate Warden", "melee", 72, 1.20, 14, 34, 1.2, 1.0, 8.0, (190, 92, 54), 24
    ),
)

ENCOUNTER_TEMPLATES = (
    EncounterTemplate(
        "standard",
        "Hostile Patrols",
        "mixed patrols",
        "steady loot",
    ),
    EncounterTemplate(
        "elite_pack",
        "Elite Pack",
        "named elites with bright telegraphs",
        "rare gear chance",
        enemy_bonus=1,
        elite_bonus=0.16,
        loot_bonus=0.08,
    ),
    EncounterTemplate(
        "ambush",
        "Ruin Ambush",
        "extra fast enemies near side doors",
        "more XP",
        enemy_bonus=2,
        elite_bonus=0.05,
        trap_bonus=0.06,
    ),
    EncounterTemplate(
        "hazard_cache",
        "Hazard Cache",
        "traps guard obvious rewards",
        "extra cache odds",
        trap_bonus=0.18,
        loot_bonus=0.10,
        secret_bonus=0.09,
    ),
    EncounterTemplate(
        "treasure_room",
        "Treasure Room",
        "tempting loot draws guardians",
        "better loot",
        enemy_bonus=1,
        elite_bonus=0.08,
        loot_bonus=0.22,
        secret_bonus=0.08,
    ),
    EncounterTemplate(
        "challenge_room",
        "Challenge Room",
        "optional boss-marked room",
        "class upgrade or rare gear",
        enemy_bonus=1,
        elite_bonus=0.12,
        loot_bonus=0.14,
        guaranteed_miniboss=True,
        challenge_room=True,
    ),
)

BOSS_DEFINITIONS = (
    BossDefinition(
        "ash_gallows",
        "Ash Gallows Knight",
        "a shielded executioner who leaves ember scars before heavy swings",
        ("Crypt of Ash", "Obsidian Foundry"),
        "fire",
        132,
        1.04,
        17,
        62,
        1.35,
        1.05,
        10.5,
        (226, 104, 58),
        "ember cleave after a red-orange tell",
        "fire-forged rare weapon",
        abilities=("ember_cleave", "ember_nova"),
    ),
    BossDefinition(
        "mycelial_matron",
        "Mycelial Matron",
        "a spore witch that controls space with poison bolts and rooting spores",
        ("Fungal Catacombs", "Thornbound Vault"),
        "poison",
        122,
        0.94,
        15,
        58,
        4.9,
        1.22,
        11.0,
        (116, 196, 98),
        "spore volleys and poison pools",
        "sealed rare armor",
        abilities=("spore_volley",),
    ),
    BossDefinition(
        "rime_chanter",
        "Rime Chanter of the Ninth Bell",
        "a frost cultist whose chill volleys punish straight-line approaches",
        ("Frozen Ossuary", "Moonlit Aquifer"),
        "frost",
        118,
        0.99,
        14,
        60,
        5.2,
        1.12,
        11.5,
        (138, 212, 242),
        "wide frost fan after a pale tell",
        "frost-touched unique chance",
        abilities=("frost_fan",),
    ),
    BossDefinition(
        "void_sentinel",
        "Voidbound Rune Sentinel",
        "a reliquary construct that fires arcane bolts while its armor hums",
        ("Violet Reliquary", "Sunken Bastion"),
        "arcane",
        150,
        0.80,
        18,
        68,
        5.4,
        1.34,
        12.0,
        (166, 118, 246),
        "slow arcane lances with a violet tell",
        "runed legendary chance",
        abilities=("arcane_lance",),
    ),
    BossDefinition(
        "gate_tyrant",
        "Dread Gate Tyrant",
        "the final seal's tyrant with alternating melee pressure and shadow casts",
        (),
        "shadow",
        245,
        0.94,
        21,
        120,
        1.45,
        1.08,
        13.0,
        (214, 92, 150),
        "shadow casts and crushing gate strikes",
        "unique gate relic",
        final_boss=True,
        abilities=("gate_strike", "shadow_volley"),
    ),
)


def canonical_boss_name(recorded: str) -> str:
    """Map a boss's runtime nameplate back to its definition name.

    The nameplate a boss dies under is not the name in BOSS_DEFINITIONS:
    floor bosses spawn with the story antagonist prefixed ("the Toll-Keeper
    Mycelial Matron"), and the final boss is renamed outright by theme
    ("Voidbound Gate Tyrant") or by learned true name ("Sorn Voss, ...").
    The boss ledger in meta-progression and every boss achievement key on the
    definition names, so recording nameplates verbatim made the Matron
    achievement silently unearnable whenever a story was active -- which is
    every run. Found on hardware: the kill registered, the achievement never
    fired.

    Unrecognised names pass through unchanged; challenge-room guardians and
    named minibosses are recorded as themselves.
    """

    text = str(recorded)
    for definition in BOSS_DEFINITIONS:
        if definition.name in text:
            return definition.name
    # Themed and true-name titles replace the Tyrant's name completely rather
    # than decorating it, so substring matching cannot recover it.
    if "Gate Tyrant" in text:
        for definition in BOSS_DEFINITIONS:
            if definition.final_boss:
                return definition.name
    return text


HUMANOID_ENEMY_NAMES = (
    "Bone Imp",
    "Cultist",
    "Crypt Brute",
    "Gate Warden",
    "Ghoul",
    "Grave Archer",
    "Rune Sentinel",
    "Hollow Knight",
)
