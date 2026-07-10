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

from ..models import EliteModifier, RunModifier, Discipline, DisciplineUpgrade

RUN_MODIFIERS = (
    RunModifier(
        "Blood Moon",
        "Enemies are tougher and hit harder, but loot is richer.",
        1.18,
        2,
        1.0,
        0.07,
    ),
    RunModifier(
        "Restless Depths", "More enemies wake from farther away.", 1.08, 1, 2.0, 0.02
    ),
    RunModifier(
        "Treasure Draught",
        "The dungeon yields more equipment and rare caches.",
        1.0,
        0,
        0.0,
        0.14,
    ),
    RunModifier(
        "Trap-Laced",
        "Hazards are more common, but shrines answer more often.",
        1.0,
        0,
        0.5,
        0.05,
        0.16,
    ),
    RunModifier(
        "Thin Veil",
        "The tyrant's guard is alert, but hidden caches are easier to find.",
        1.06,
        1,
        1.0,
        0.08,
        0.04,
    ),
    RunModifier(
        "Starved Depths",
        "Loot is scarcer, but enemies are slightly weakened.",
        0.92,
        -1,
        -0.5,
        -0.08,
        0.0,
    ),
    RunModifier(
        "Elite Hunt",
        "More elites and minibosses stalk the halls, carrying better spoils.",
        1.10,
        1,
        1.0,
        0.10,
        0.02,
    ),
    RunModifier(
        "Cursed Bargains",
        "Cursed gear and risky events are more common, but rewards spike higher.",
        1.04,
        0,
        0.5,
        0.16,
        0.04,
    ),
)


# --- Disciplines -------------------------------------------------------------
#
# Each archetype owns a route-based discipline tree with five degrees of depth.
# A discipline belongs to a named path (route) and may require one or more prior
# disciplines before it can be chosen. Paths let players commit to a playstyle
# (e.g. a "Bulwark" tank route versus a "Riposte" counter route on the Warden)
# while shared degree-1 disciplines keep early progression open.
#
# `DISCIPLINES` is the source of truth. `DISCIPLINE_UPGRADES` is derived from it so
# older code paths and saves that reference flat upgrade keys keep working: the
# legacy key is preserved as `Discipline.key`, and the derived `DisciplineUpgrade`
# carries the same bonuses. New disciplines added below expand the tree without
# breaking save compatibility because `player.skill_upgrades` only stores keys.
#
# Migration: a small `LEGACY_DISCIPLINE_KEYS` map rewrites obsolete keys from prior
# milestones onto their current node key so old saves resume cleanly.

DISCIPLINES: tuple[Discipline, ...] = (
    # === Warden ===
    # Degree 1 — shared foundation.
    Discipline(
        "warden_bulwark",
        "Warden",
        "Bulwark Training",
        "Melee bashes cleave wider and armor improves.",
        degree=1,
        path="Bulwark",
        prerequisites=(),
        melee_bonus=1,
        armor_bonus=2,
        max_hp_bonus=10,
        tags=("Guard",),
    ),
    Discipline(
        "warden_riposte",
        "Warden",
        "Riposte Guard",
        "Taking melee hits costs less health and fuels counterattacks.",
        degree=1,
        path="Riposte",
        prerequisites=(),
        melee_bonus=2,
        armor_bonus=1,
        tags=("Counter",),
    ),
    # Degree 2 — path commitments.
    Discipline(
        "warden_aegis",
        "Warden",
        "Aegis Discipline",
        "Guard Step briefly hardens the Warden and Shield Bash staggers enemies.",
        degree=2,
        path="Bulwark",
        prerequisites=("warden_bulwark",),
        armor_bonus=1,
        max_stamina_bonus=8,
        tags=("Guard",),
    ),
    Discipline(
        "warden_counter",
        "Warden",
        "Counter Stance",
        "Riposte strikes stagger attackers and grant brief stamina surge.",
        degree=2,
        path="Riposte",
        prerequisites=("warden_riposte",),
        melee_bonus=2,
        max_stamina_bonus=6,
        tags=("Counter",),
    ),
    # Degree 3 — cross-path specialist nodes.
    Discipline(
        "warden_bulwark_ward",
        "Warden",
        "Warden's Ward",
        "Bulwark bashes reach farther and steady allies near the Warden.",
        degree=3,
        path="Bulwark",
        prerequisites=("warden_aegis",),
        armor_bonus=2,
        max_hp_bonus=12,
        tags=("Guard",),
    ),
    Discipline(
        "warden_riposte_edge",
        "Warden",
        "Riposte Edge",
        "Counterattacks deal bonus damage to staggered foes.",
        degree=3,
        path="Riposte",
        prerequisites=("warden_counter",),
        melee_bonus=3,
        armor_bonus=1,
        tags=("Counter",),
    ),
    # Degree 4 — keystone choices. These are the cross-path modifier nodes:
    # committing deep into one path amplifies the other path's tagged
    # skills, so a hybrid Warden feels the synergy.
    Discipline(
        "warden_iron_vow",
        "Warden",
        "Iron Vow",
        "Armor mastery: heavy hits glance and stamina holds under pressure.",
        degree=4,
        path="Bulwark",
        prerequisites=("warden_bulwark_ward",),
        armor_bonus=3,
        max_stamina_bonus=12,
        max_hp_bonus=14,
        tags=("Guard",),
        cross_path_tags=("Counter",),
        cross_path_bonus_melee=1,
    ),
    Discipline(
        "warden_reckoning",
        "Warden",
        "Reckoning",
        "Every counter echoes as a Guard Bolt and refunds mana.",
        degree=4,
        path="Riposte",
        prerequisites=("warden_riposte_edge",),
        melee_bonus=4,
        spell_bonus=2,
        max_mana_bonus=10,
        tags=("Counter",),
        cross_path_tags=("Guard",),
        cross_path_bonus_melee=1,
    ),
    # Degree 5 — capstone.
    Discipline(
        "warden_unbreakable",
        "Warden",
        "Unbreakable Bulwark",
        "Below half health the Warden hardens and bashes clear surrounding foes.",
        degree=5,
        path="Bulwark",
        prerequisites=("warden_iron_vow",),
        armor_bonus=4,
        max_hp_bonus=24,
        max_stamina_bonus=10,
    ),
    Discipline(
        "warden_final_reckoning",
        "Warden",
        "Final Reckoning",
        "Counters execute wounded elites and refresh Guard Step.",
        degree=5,
        path="Riposte",
        prerequisites=("warden_reckoning",),
        melee_bonus=5,
        spell_bonus=3,
        max_stamina_bonus=10,
    ),
    # --- Warden: Vow path (holy smite and oath magic) ---
    Discipline(
        "warden_smite",
        "Warden",
        "Smite Oath",
        "Guard Bolt flares with holy light and burns the undead.",
        degree=1,
        path="Vow",
        prerequisites=(),
        spell_bonus=2,
        max_mana_bonus=8,
        tags=("Holy",),
    ),
    Discipline(
        "warden_ward",
        "Warden",
        "Temporal Sigil",
        "Time Skip costs less mana, cools down faster, and lasts a beat longer.",
        degree=1,
        path="Time",
        prerequisites=(),
        armor_bonus=2,
        max_hp_bonus=8,
        tags=("Time",),
    ),
    Discipline(
        "warden_judgment",
        "Warden",
        "Judgment",
        "Smite chains to a second foe and marks them for counters.",
        degree=2,
        path="Vow",
        prerequisites=("warden_smite",),
        spell_bonus=3,
        max_mana_bonus=8,
        tags=("Holy",),
    ),
    Discipline(
        "warden_bulwark_wave",
        "Warden",
        "Time Skip",
        "Time Skip lasts longer and its cast pulse staggers foes caught in the ring.",
        degree=2,
        path="Time",
        prerequisites=("warden_ward",),
        armor_bonus=2,
        max_stamina_bonus=8,
        tags=("Time",),
    ),
    Discipline(
        "warden_consecrate",
        "Warden",
        "Consecration",
        "Holy ground burns foes that stand in the Warden's wake.",
        degree=3,
        path="Vow",
        prerequisites=("warden_judgment",),
        spell_bonus=4,
        max_mana_bonus=10,
        tags=("Holy",),
    ),
    Discipline(
        "warden_stone_aegis",
        "Warden",
        "Stutter Step",
        "Time Skip slows enemies harder while it lasts.",
        degree=3,
        path="Time",
        prerequisites=("warden_bulwark_wave",),
        armor_bonus=3,
        max_hp_bonus=12,
        tags=("Time",),
    ),
    Discipline(
        "warden_divine_wrath",
        "Warden",
        "Divine Wrath",
        "Smite erupts in a holy nova that stuns nearby foes.",
        degree=4,
        path="Vow",
        prerequisites=("warden_consecrate",),
        spell_bonus=5,
        max_mana_bonus=12,
        tags=("Holy",),
        # Deep Holy pick that amplifies Counter-tagged riposte skills.
        cross_path_tags=("Counter",),
        cross_path_bonus_spell=1,
    ),
    Discipline(
        "warden_unyielding",
        "Warden",
        "Temporal Aegis",
        "While Time Skip is active the Warden takes reduced damage.",
        degree=4,
        path="Time",
        prerequisites=("warden_stone_aegis",),
        armor_bonus=4,
        max_hp_bonus=16,
        max_stamina_bonus=10,
        tags=("Time",),
        # Deep Time pick that amplifies Guard-tagged bulwark skills.
        cross_path_tags=("Guard",),
        cross_path_bonus_melee=1,
    ),
    Discipline(
        "warden_avatar_of_light",
        "Warden",
        "Avatar of Light",
        "The Warden becomes a beacon: smites heal allies and blind foes.",
        degree=5,
        path="Vow",
        prerequisites=("warden_divine_wrath",),
        spell_bonus=6,
        max_mana_bonus=16,
        max_hp_bonus=12,
    ),
    Discipline(
        "warden_eternal_wall",
        "Warden",
        "Eternal Moment",
        "Kills while Time Skip is active refund much of the slot's cooldown.",
        degree=5,
        path="Time",
        prerequisites=("warden_unyielding",),
        armor_bonus=5,
        max_hp_bonus=24,
        max_stamina_bonus=12,
    ),
    # === Rogue ===
    Discipline(
        "rogue_precision",
        "Rogue",
        "Killing Precision",
        "Crits are deadlier and quick strikes cost less stamina.",
        degree=1,
        path="Precision",
        prerequisites=(),
        melee_bonus=3,
        max_stamina_bonus=8,
        tags=("Critical",),
    ),
    Discipline(
        "rogue_smoke",
        "Rogue",
        "Smoke Step",
        "Evasion improves after using movement skills.",
        degree=1,
        path="Shadow",
        prerequisites=(),
        speed_bonus=0.15,
        max_stamina_bonus=10,
        tags=("Stealth",),
    ),
    Discipline(
        "rogue_venom",
        "Rogue",
        "Venomcraft",
        "Backstabs and knife fans poison wounded targets.",
        degree=2,
        path="Precision",
        prerequisites=("rogue_precision",),
        melee_bonus=1,
        max_stamina_bonus=6,
        tags=("Critical",),
    ),
    Discipline(
        "rogue_shadowstep",
        "Rogue",
        "Shadowstep",
        "Ambush Bell grants a longer smoke window and Shadow Dash costs less.",
        degree=2,
        path="Shadow",
        prerequisites=("rogue_smoke",),
        speed_bonus=0.10,
        max_stamina_bonus=8,
        tags=("Stealth",),
    ),
    Discipline(
        "rogue_executioner",
        "Rogue",
        "Executioner",
        "Crits on poisoned foes deal killing blow damage.",
        degree=3,
        path="Precision",
        prerequisites=("rogue_venom",),
        melee_bonus=4,
        max_stamina_bonus=6,
        tags=("Critical",),
    ),
    Discipline(
        "rogue_night_veil",
        "Rogue",
        "Night Veil",
        "Standing in smoke regenerates stamina and grants dodge.",
        degree=3,
        path="Shadow",
        prerequisites=("rogue_shadowstep",),
        speed_bonus=0.08,
        max_stamina_bonus=12,
        tags=("Stealth",),
    ),
    Discipline(
        "rogue_crimson_edge",
        "Rogue",
        "Crimson Edge",
        "Killing blows refresh crit chance and bleed poisoned targets.",
        degree=4,
        path="Precision",
        prerequisites=("rogue_executioner",),
        melee_bonus=5,
        max_hp_bonus=10,
        tags=("Critical",),
        # A deep Precision pick that amplifies Stealth-tagged skills, so a
        # hybrid Rogue feels the cross-path payoff.
        cross_path_tags=("Stealth",),
        cross_path_bonus_melee=1,
    ),
    Discipline(
        "rogue_phantom",
        "Rogue",
        "Phantom",
        "Shadow Dash leaves a decoy that draws enemy attacks.",
        degree=4,
        path="Shadow",
        prerequisites=("rogue_night_veil",),
        speed_bonus=0.12,
        max_stamina_bonus=10,
        tags=("Stealth",),
        cross_path_tags=("Critical",),
        cross_path_bonus_melee=1,
    ),
    Discipline(
        "rogue_deathmark",
        "Rogue",
        "Deathmark",
        "Marked foes fall to a single backstab chain.",
        degree=5,
        path="Precision",
        prerequisites=("rogue_crimson_edge",),
        melee_bonus=6,
        max_stamina_bonus=10,
    ),
    Discipline(
        "rogue_umbral",
        "Rogue",
        "Umbral Form",
        "Become briefly untouchable after each Shadow Dash.",
        degree=5,
        path="Shadow",
        prerequisites=("rogue_phantom",),
        speed_bonus=0.14,
        max_stamina_bonus=12,
    ),
    # --- Rogue: Traps path (Ambush Bell action-skill upgrades) ---
    Discipline(
        "rogue_trap_craft",
        "Rogue",
        "Bellwright's Hand",
        "Ambush Bell arms faster, lasts longer, and lures from farther away.",
        degree=1,
        path="Traps",
        prerequisites=(),
        melee_bonus=2,
        spell_bonus=1,
        max_stamina_bonus=6,
        tags=("Trap",),
    ),
    Discipline(
        "rogue_marksman",
        "Rogue",
        "Marksman",
        "Knife Fan reaches farther and crits from range.",
        degree=1,
        path="Marksman",
        prerequisites=(),
        melee_bonus=2,
        max_stamina_bonus=8,
        tags=("Aim",),
    ),
    Discipline(
        "rogue_venom_trap",
        "Rogue",
        "Venom Chime",
        "Ambush Bell dagger bursts poison foes caught in the snap.",
        degree=2,
        path="Traps",
        prerequisites=("rogue_trap_craft",),
        spell_bonus=2,
        max_stamina_bonus=6,
        tags=("Trap",),
    ),
    Discipline(
        "rogue_sharpshot",
        "Rogue",
        "Sharpshot",
        "Backstabs from range deal bonus damage and refund stamina.",
        degree=2,
        path="Marksman",
        prerequisites=("rogue_marksman",),
        melee_bonus=3,
        max_stamina_bonus=8,
        tags=("Aim",),
    ),
    Discipline(
        "rogue_bear_trap",
        "Rogue",
        "Iron Clapper",
        "Ambush Bell clamps the first foe with a snare and hits lured prey harder.",
        degree=3,
        path="Traps",
        prerequisites=("rogue_venom_trap",),
        melee_bonus=3,
        spell_bonus=2,
        max_stamina_bonus=6,
        tags=("Trap",),
    ),
    Discipline(
        "rogue_deadeye",
        "Rogue",
        "Deadeye",
        "Crits from range pierce and apply a stacking mark.",
        degree=3,
        path="Marksman",
        prerequisites=("rogue_sharpshot",),
        melee_bonus=4,
        max_stamina_bonus=6,
        tags=("Aim",),
    ),
    Discipline(
        "rogue_trap_master",
        "Rogue",
        "Resonant Lure",
        "Ambush Bell pulls wider, splashes harder, and catches nearby foes in the snare.",
        degree=4,
        path="Traps",
        prerequisites=("rogue_bear_trap",),
        melee_bonus=4,
        spell_bonus=3,
        max_stamina_bonus=8,
        tags=("Trap",),
        # Deep Trap pick that amplifies Critical-tagged precision skills.
        cross_path_tags=("Critical",),
        cross_path_bonus_melee=1,
    ),
    Discipline(
        "rogue_eagle_eye",
        "Rogue",
        "Eagle Eye",
        "Marked foes take extra crit damage and reveal hidden secrets.",
        degree=4,
        path="Marksman",
        prerequisites=("rogue_deadeye",),
        melee_bonus=5,
        max_stamina_bonus=8,
        tags=("Aim",),
        # Deep Aim pick that amplifies Stealth-tagged shadow skills.
        cross_path_tags=("Stealth",),
        cross_path_bonus_melee=1,
    ),
    Discipline(
        "rogue_ambush_engineer",
        "Rogue",
        "Cursed Bellwright",
        "Ambush Bell gains a sharper snap and successful ambush kills hasten the next bell.",
        degree=5,
        path="Traps",
        prerequisites=("rogue_trap_master",),
        melee_bonus=5,
        spell_bonus=4,
        max_stamina_bonus=10,
    ),
    Discipline(
        "rogue_assassin",
        "Rogue",
        "Assassin",
        "Marked foes die to a single perfect shot from any range.",
        degree=5,
        path="Marksman",
        prerequisites=("rogue_eagle_eye",),
        melee_bonus=6,
        max_stamina_bonus=10,
    ),
    # === Arcanist ===
    Discipline(
        "arcanist_splinter",
        "Arcanist",
        "Splintered Arcana",
        "Arc Bolt throws an extra shard.",
        degree=1,
        path="Bolt",
        prerequisites=(),
        spell_bonus=3,
        max_mana_bonus=10,
        tags=("Arcane",),
    ),
    Discipline(
        "arcanist_focus",
        "Arcanist",
        "Deep Focus",
        "Mana recovers faster and novas reach farther.",
        degree=1,
        path="Nova",
        prerequisites=(),
        spell_bonus=2,
        max_mana_bonus=14,
        tags=("Frost",),
    ),
    Discipline(
        "arcanist_permafrost",
        "Arcanist",
        "Permafrost Sigils",
        "Frost Nova chills longer and Arc Bolt exploits chilled foes.",
        degree=2,
        path="Nova",
        prerequisites=("arcanist_focus",),
        spell_bonus=2,
        max_mana_bonus=8,
        tags=("Frost",),
    ),
    Discipline(
        "arcanist_overload",
        "Arcanist",
        "Arc Overload",
        "Bolts split on impact and pierce the first foe.",
        degree=2,
        path="Bolt",
        prerequisites=("arcanist_splinter",),
        spell_bonus=3,
        max_mana_bonus=8,
        tags=("Arcane",),
    ),
    Discipline(
        "arcanist_glacial",
        "Arcanist",
        "Glacial Tide",
        "Frost Nova freezes chilled foes in place briefly.",
        degree=3,
        path="Nova",
        prerequisites=("arcanist_permafrost",),
        spell_bonus=3,
        max_mana_bonus=10,
        tags=("Frost",),
    ),
    Discipline(
        "arcanist_pierce",
        "Arcanist",
        "Piercing Arc",
        "Bolts pierce two foes and ricochet toward elites.",
        degree=3,
        path="Bolt",
        prerequisites=("arcanist_overload",),
        spell_bonus=4,
        max_mana_bonus=8,
        tags=("Arcane",),
    ),
    Discipline(
        "arcanist_blizzard",
        "Arcanist",
        "Blizzard Heart",
        "Standing in chilled air grants mana shield and faster casts.",
        degree=4,
        path="Nova",
        prerequisites=("arcanist_glacial",),
        spell_bonus=4,
        max_mana_bonus=14,
        armor_bonus=1,
        tags=("Frost",),
        # Deep Frost pick that amplifies Arcane-tagged bolt skills.
        cross_path_tags=("Arcane",),
        cross_path_bonus_spell=1,
    ),
    Discipline(
        "arcanist_storm",
        "Arcanist",
        "Storm Sigil",
        "Bolts chain lightning between nearby foes.",
        degree=4,
        path="Bolt",
        prerequisites=("arcanist_pierce",),
        spell_bonus=5,
        max_mana_bonus=12,
        tags=("Arcane",),
        cross_path_tags=("Frost",),
        cross_path_bonus_spell=1,
    ),
    Discipline(
        "arcanist_absolute_zero",
        "Arcanist",
        "Absolute Zero",
        "Frost Nova freezes the floor, slowing all enemies in range.",
        degree=5,
        path="Nova",
        prerequisites=("arcanist_blizzard",),
        spell_bonus=5,
        max_mana_bonus=16,
    ),
    Discipline(
        "arcanist_arc_tyrant",
        "Arcanist",
        "Arc Tyrant",
        "Bolts seek elites and overload on kill, refilling mana.",
        degree=5,
        path="Bolt",
        prerequisites=("arcanist_storm",),
        spell_bonus=6,
        max_mana_bonus=14,
    ),
    # --- Arcanist: Storm path (lightning and chain magic) ---
    Discipline(
        "arcanist_charge",
        "Arcanist",
        "Static Charge",
        "Arc Bolt builds a charge that discharges on the next cast.",
        degree=1,
        path="Storm",
        prerequisites=(),
        spell_bonus=2,
        max_mana_bonus=10,
        tags=("Storm",),
    ),
    Discipline(
        "arcanist_ward",
        "Arcanist",
        "Arcane Ward",
        "A mana shield absorbs hits and reflects arcane damage.",
        degree=1,
        path="Ward",
        prerequisites=(),
        armor_bonus=1,
        max_mana_bonus=12,
        tags=("Shield",),
    ),
    Discipline(
        "arcanist_chain_lightning",
        "Arcanist",
        "Chain Lightning",
        "Bolts arc between up to three foes, weakening each.",
        degree=2,
        path="Storm",
        prerequisites=("arcanist_charge",),
        spell_bonus=3,
        max_mana_bonus=8,
        tags=("Storm",),
    ),
    Discipline(
        "arcanist_ward_mend",
        "Arcanist",
        "Warding Mend",
        "The ward heals the Arcanist when it absorbs a hit.",
        degree=2,
        path="Ward",
        prerequisites=("arcanist_ward",),
        armor_bonus=2,
        max_mana_bonus=10,
        max_hp_bonus=8,
        tags=("Shield",),
    ),
    Discipline(
        "arcanist_tempest",
        "Arcanist",
        "Tempest",
        "A storm front lingers, repeatedly striking foes in range.",
        degree=3,
        path="Storm",
        prerequisites=("arcanist_chain_lightning",),
        spell_bonus=4,
        max_mana_bonus=10,
        tags=("Storm",),
    ),
    Discipline(
        "arcanist_ward_overload",
        "Arcanist",
        "Ward Overload",
        "A depleted ward detonates, damaging nearby foes.",
        degree=3,
        path="Ward",
        prerequisites=("arcanist_ward_mend",),
        armor_bonus=2,
        spell_bonus=2,
        max_mana_bonus=12,
        tags=("Shield",),
    ),
    Discipline(
        "arcanist_storm_caller",
        "Arcanist",
        "Stormcaller",
        "Tempests grow into a full storm that hunts elites.",
        degree=4,
        path="Storm",
        prerequisites=("arcanist_tempest",),
        spell_bonus=5,
        max_mana_bonus=12,
        tags=("Storm",),
        # Deep Storm pick that amplifies Frost-tagged nova skills.
        cross_path_tags=("Frost",),
        cross_path_bonus_spell=1,
    ),
    Discipline(
        "arcanist_aegis",
        "Arcanist",
        "Arcane Aegis",
        "The ward becomes permanent and reflects spells.",
        degree=4,
        path="Ward",
        prerequisites=("arcanist_ward_overload",),
        armor_bonus=3,
        max_mana_bonus=14,
        max_hp_bonus=10,
        tags=("Shield",),
        # Deep Shield pick that amplifies Arcane-tagged bolt skills.
        cross_path_tags=("Arcane",),
        cross_path_bonus_spell=1,
    ),
    Discipline(
        "arcanist_world_storm",
        "Arcanist",
        "World Storm",
        "The storm engulfs the floor, striking every foe each beat.",
        degree=5,
        path="Storm",
        prerequisites=("arcanist_storm_caller",),
        spell_bonus=6,
        max_mana_bonus=16,
    ),
    Discipline(
        "arcanist_eternal_aegis",
        "Arcanist",
        "Eternal Aegis",
        "The aegis cannot be broken and shields allies near the Arcanist.",
        degree=5,
        path="Ward",
        prerequisites=("arcanist_aegis",),
        armor_bonus=4,
        max_mana_bonus=18,
        max_hp_bonus=14,
    ),
    # === Acolyte ===
    Discipline(
        "acolyte_sanguine",
        "Acolyte",
        "Sanguine Rite",
        "Blood skills leech more life at close range.",
        degree=1,
        path="Blood",
        prerequisites=(),
        melee_bonus=1,
        spell_bonus=2,
        max_hp_bonus=8,
        tags=("Blood",),
    ),
    Discipline(
        "acolyte_veil",
        "Acolyte",
        "Veil of Ash",
        "Mana shields blunt harsher blows.",
        degree=1,
        path="Veil",
        prerequisites=(),
        armor_bonus=1,
        max_mana_bonus=8,
        tags=("Veil",),
    ),
    Discipline(
        "acolyte_gravebind",
        "Acolyte",
        "Gravebind Covenant",
        "Blood Rite and Spirit Bolt bind foes, and kills echo more life into the Acolyte.",
        degree=2,
        path="Blood",
        prerequisites=("acolyte_sanguine",),
        spell_bonus=2,
        max_hp_bonus=6,
        max_mana_bonus=6,
        tags=("Blood",),
    ),
    Discipline(
        "acolyte_ashen",
        "Acolyte",
        "Ashen Ward",
        "Veil of Ash reflects damage and cleanses status on use.",
        degree=2,
        path="Veil",
        prerequisites=("acolyte_veil",),
        armor_bonus=2,
        max_mana_bonus=10,
        tags=("Veil",),
    ),
    Discipline(
        "acolyte_blood_pact",
        "Acolyte",
        "Blood Pact",
        "Spend health to cast when mana runs dry; lifesteal intensifies.",
        degree=3,
        path="Blood",
        prerequisites=("acolyte_gravebind",),
        spell_bonus=3,
        max_hp_bonus=10,
        tags=("Blood",),
    ),
    Discipline(
        "acolyte_spirit_host",
        "Acolyte",
        "Spirit Host",
        "Spirit Bolt summons a brief wraith that harries foes.",
        degree=3,
        path="Veil",
        prerequisites=("acolyte_ashen",),
        spell_bonus=3,
        max_mana_bonus=10,
        tags=("Veil",),
    ),
    Discipline(
        "acolyte_crimson_maw",
        "Acolyte",
        "Crimson Maw",
        "Blood skills devour weak foes, healing the Acolyte massively.",
        degree=4,
        path="Blood",
        prerequisites=("acolyte_blood_pact",),
        spell_bonus=4,
        max_hp_bonus=14,
        melee_bonus=2,
        tags=("Blood",),
        # Deep Blood pick that amplifies Veil-tagged shield skills.
        cross_path_tags=("Veil",),
        cross_path_bonus_spell=1,
    ),
    Discipline(
        "acolyte_grave_chorus",
        "Acolyte",
        "Grave Chorus",
        "Wraiths persist longer and shield the Acolyte when struck.",
        degree=4,
        path="Veil",
        prerequisites=("acolyte_spirit_host",),
        spell_bonus=4,
        max_mana_bonus=14,
        armor_bonus=2,
        tags=("Veil",),
        # Deep Veil pick that amplifies Blood-tagged rite skills.
        cross_path_tags=("Blood",),
        cross_path_bonus_spell=1,
    ),
    Discipline(
        "acolyte_sanguine_ascendant",
        "Acolyte",
        "Sanguine Ascendant",
        "Below half health, blood skills cost no mana and leech doubles.",
        degree=5,
        path="Blood",
        prerequisites=("acolyte_crimson_maw",),
        spell_bonus=5,
        max_hp_bonus=20,
        melee_bonus=3,
        tags=("Blood",),
    ),
    Discipline(
        "acolyte_undying_veil",
        "Acolyte",
        "Undying Veil",
        "Once per floor, a fatal blow is absorbed by the veil.",
        degree=5,
        path="Veil",
        prerequisites=("acolyte_grave_chorus",),
        spell_bonus=5,
        max_mana_bonus=16,
        armor_bonus=3,
        tags=("Veil",),
    ),
    # --- Acolyte: Spirit path (summoning and wraith control) ---
    Discipline(
        "acolyte_spirit_call",
        "Acolyte",
        "Spirit Call",
        "Summon a wisp familiar that follows you and harries foes; it grows into a watchful owl as your Spirit deepens.",
        degree=1,
        path="Spirit",
        prerequisites=(),
        spell_bonus=2,
        max_mana_bonus=8,
        tags=("Spirit",),
    ),
    Discipline(
        "acolyte_curse",
        "Acolyte",
        "Hex",
        "Spirit Bolt curses foes, weakening their attacks.",
        degree=1,
        path="Curse",
        prerequisites=(),
        spell_bonus=2,
        max_mana_bonus=8,
        tags=("Curse",),
    ),
    Discipline(
        "acolyte_wraith_host",
        "Acolyte",
        "Owl Companion",
        "The owl familiar persists, growing heartier and harrying foes at your side.",
        degree=2,
        path="Spirit",
        prerequisites=("acolyte_spirit_call",),
        spell_bonus=3,
        max_mana_bonus=8,
        tags=("Spirit",),
    ),
    Discipline(
        "acolyte_decay",
        "Acolyte",
        "Decay",
        "Cursed foes rot, losing health each second.",
        degree=2,
        path="Curse",
        prerequisites=("acolyte_curse",),
        spell_bonus=3,
        max_mana_bonus=8,
        tags=("Curse",),
    ),
    Discipline(
        "acolyte_bone_legion",
        "Acolyte",
        "Twin Owls",
        "Call a second owl to fight beside the Acolyte, striking harder than the first.",
        degree=3,
        path="Spirit",
        prerequisites=("acolyte_wraith_host",),
        spell_bonus=4,
        max_mana_bonus=10,
        melee_bonus=2,
        tags=("Spirit",),
    ),
    Discipline(
        "acolyte_fragility",
        "Acolyte",
        "Fragility",
        "Cursed foes take increased damage from all sources.",
        degree=3,
        path="Curse",
        prerequisites=("acolyte_decay",),
        spell_bonus=4,
        max_mana_bonus=10,
        tags=("Curse",),
    ),
    Discipline(
        "acolyte_wraith_lord",
        "Acolyte",
        "Owl Lord",
        "A champion owl guards the Acolyte, taunting foes with greater presence and size.",
        degree=4,
        path="Spirit",
        prerequisites=("acolyte_bone_legion",),
        spell_bonus=5,
        max_mana_bonus=12,
        melee_bonus=3,
        tags=("Spirit",),
        # Deep Spirit pick that amplifies Curse-tagged debuff skills.
        cross_path_tags=("Curse",),
        cross_path_bonus_spell=1,
    ),
    Discipline(
        "acolyte_doom",
        "Acolyte",
        "Doom",
        "Cursed foes are marked for death, exploding on death.",
        degree=4,
        path="Curse",
        prerequisites=("acolyte_fragility",),
        spell_bonus=5,
        max_mana_bonus=12,
        tags=("Curse",),
        # Deep Curse pick that amplifies Spirit-tagged summon skills.
        cross_path_tags=("Spirit",),
        cross_path_bonus_spell=1,
    ),
    Discipline(
        "acolyte_legion_eternal",
        "Acolyte",
        "Eternal Owls",
        "The owl host becomes unkillable and a third owl joins the vigil.",
        degree=5,
        path="Spirit",
        prerequisites=("acolyte_wraith_lord",),
        spell_bonus=6,
        max_mana_bonus=16,
        melee_bonus=4,
    ),
    Discipline(
        "acolyte_eternal_doom",
        "Acolyte",
        "Eternal Doom",
        "Doom spreads to nearby foes on death, cursing the survivors.",
        degree=5,
        path="Curse",
        prerequisites=("acolyte_doom",),
        spell_bonus=6,
        max_mana_bonus=16,
    ),
    # === Ranger ===
    Discipline(
        "ranger_snare",
        "Ranger",
        "Barbed Snares",
        "Control skills delay enemies longer.",
        degree=1,
        path="Control",
        prerequisites=(),
        spell_bonus=2,
        max_stamina_bonus=8,
        tags=("Control",),
    ),
    Discipline(
        "ranger_volley",
        "Ranger",
        "Volley Drills",
        "Multishot spreads into a wider fan.",
        degree=1,
        path="Volley",
        prerequisites=(),
        melee_bonus=1,
        spell_bonus=2,
        tags=("Volley",),
    ),
    Discipline(
        "ranger_beastmark",
        "Ranger",
        "Beastmark Pursuit",
        "Vault refreshes momentum and marked shots hit controlled enemies harder.",
        degree=2,
        path="Control",
        prerequisites=("ranger_snare",),
        melee_bonus=1,
        speed_bonus=0.12,
        max_stamina_bonus=6,
        tags=("Control",),
    ),
    Discipline(
        "ranger_rapid",
        "Ranger",
        "Rapid Volley",
        "Multishot fires an extra arrow and reloads faster.",
        degree=2,
        path="Volley",
        prerequisites=("ranger_volley",),
        melee_bonus=2,
        spell_bonus=2,
        max_stamina_bonus=6,
        tags=("Volley",),
    ),
    Discipline(
        "ranger_thornfield",
        "Ranger",
        "Thornfield",
        "Snares grow thorns, damaging foes that struggle in them.",
        degree=3,
        path="Control",
        prerequisites=("ranger_beastmark",),
        spell_bonus=3,
        max_stamina_bonus=8,
        tags=("Control",),
    ),
    Discipline(
        "ranger_piercing_volley",
        "Ranger",
        "Piercing Volley",
        "Arrows pierce the first foe and seek marked targets.",
        degree=3,
        path="Volley",
        prerequisites=("ranger_rapid",),
        melee_bonus=3,
        spell_bonus=3,
        tags=("Volley",),
    ),
    Discipline(
        "ranger_hunter_drive",
        "Ranger",
        "Hunter's Drive",
        "Vault resets attack cooldowns and grants a brief speed surge.",
        degree=4,
        path="Control",
        prerequisites=("ranger_thornfield",),
        speed_bonus=0.14,
        max_stamina_bonus=12,
        melee_bonus=2,
        tags=("Control",),
        # Deep Control pick that amplifies Beast-tagged companion skills.
        cross_path_tags=("Beast",),
        cross_path_bonus_melee=1,
    ),
    Discipline(
        "ranger_storm_volley",
        "Ranger",
        "Storm Volley",
        "Multishot arcs into a storm that hits all foes in a cone.",
        degree=4,
        path="Volley",
        prerequisites=("ranger_piercing_volley",),
        melee_bonus=4,
        spell_bonus=4,
        max_stamina_bonus=8,
        tags=("Volley",),
        # Deep Volley pick that amplifies Survival-tagged field skills.
        cross_path_tags=("Survival",),
        cross_path_bonus_melee=1,
    ),
    Discipline(
        "ranger_wild_domination",
        "Ranger",
        "Wild Domination",
        "Marked foes are rooted and struck by a beast companion.",
        degree=5,
        path="Control",
        prerequisites=("ranger_hunter_drive",),
        spell_bonus=5,
        max_stamina_bonus=14,
        speed_bonus=0.10,
        tags=("Control",),
    ),
    Discipline(
        "ranger_sky_quiver",
        "Ranger",
        "Sky Quiver",
        "Multishot becomes a relentless barrage while standing still.",
        degree=5,
        path="Volley",
        prerequisites=("ranger_storm_volley",),
        melee_bonus=5,
        spell_bonus=5,
        max_stamina_bonus=10,
        tags=("Volley",),
    ),
    # --- Ranger: Beast path (companion taming and pack tactics) ---
    Discipline(
        "ranger_beast_bond",
        "Ranger",
        "Beast Bond",
        "A wolf companion joins the Ranger and harries foes.",
        degree=1,
        path="Beast",
        prerequisites=(),
        melee_bonus=2,
        max_stamina_bonus=8,
        tags=("Beast",),
    ),
    Discipline(
        "ranger_survival",
        "Ranger",
        "Survivalist",
        "The Ranger regenerates stamina faster and resists traps.",
        degree=1,
        path="Survival",
        prerequisites=(),
        max_hp_bonus=8,
        max_stamina_bonus=10,
        tags=("Survival",),
    ),
    Discipline(
        "ranger_pack_tactics",
        "Ranger",
        "Pack Tactics",
        "The companion strikes marked foes and shares dodge chance.",
        degree=2,
        path="Beast",
        prerequisites=("ranger_beast_bond",),
        melee_bonus=3,
        max_stamina_bonus=6,
        tags=("Beast",),
    ),
    Discipline(
        "ranger_camouflage",
        "Ranger",
        "Camouflage",
        "Standing still grants stealth and a guaranteed first strike.",
        degree=2,
        path="Survival",
        prerequisites=("ranger_survival",),
        speed_bonus=0.10,
        max_stamina_bonus=8,
        tags=("Survival",),
    ),
    Discipline(
        "ranger_alpha",
        "Ranger",
        "Alpha",
        "The companion becomes a dire wolf that knocks foes back.",
        degree=3,
        path="Beast",
        prerequisites=("ranger_pack_tactics",),
        melee_bonus=4,
        max_stamina_bonus=8,
        tags=("Beast",),
    ),
    Discipline(
        "ranger_pathfinder",
        "Ranger",
        "Pathfinder",
        "The Ranger reveals secrets and shrines on the floor.",
        degree=3,
        path="Survival",
        prerequisites=("ranger_camouflage",),
        spell_bonus=2,
        max_stamina_bonus=10,
        tags=("Survival",),
    ),
    Discipline(
        "ranger_spirit_companion",
        "Ranger",
        "Spirit Companion",
        "The dire wolf becomes a spirit beast that strikes through foes.",
        degree=4,
        path="Beast",
        prerequisites=("ranger_alpha",),
        melee_bonus=5,
        spell_bonus=2,
        max_stamina_bonus=10,
        tags=("Beast",),
        # Deep Beast pick that amplifies Volley-tagged ranged skills.
        cross_path_tags=("Volley",),
        cross_path_bonus_melee=1,
    ),
    Discipline(
        "ranger_ambush",
        "Ranger",
        "Ambush",
        "First strikes from stealth deal massive bonus damage.",
        degree=4,
        path="Survival",
        prerequisites=("ranger_pathfinder",),
        melee_bonus=4,
        speed_bonus=0.12,
        max_stamina_bonus=12,
        tags=("Survival",),
        # Deep Survival pick that amplifies Control-tagged snare skills.
        cross_path_tags=("Control",),
        cross_path_bonus_melee=1,
    ),
    Discipline(
        "ranger_primal_lord",
        "Ranger",
        "Primal Lord",
        "The spirit beast becomes a primal champion that mauls elites.",
        degree=5,
        path="Beast",
        prerequisites=("ranger_spirit_companion",),
        melee_bonus=6,
        spell_bonus=3,
        max_stamina_bonus=12,
    ),
    Discipline(
        "ranger_ghost_step",
        "Ranger",
        "Ghost Step",
        "The Ranger becomes untargetable while moving and dodges traps.",
        degree=5,
        path="Survival",
        prerequisites=("ranger_ambush",),
        speed_bonus=0.16,
        max_stamina_bonus=14,
        max_hp_bonus=10,
    ),
)


# Obsolete keys from earlier milestones mapped onto their current node key.
# Used by `migrate_discipline_keys` so older saves resume against the new tree.
LEGACY_DISCIPLINE_KEYS: dict[str, str] = {
    # No renames yet — all original keys are preserved as node keys — but the
    # table is in place so future migrations stay save-compatible.
}


def migrate_discipline_keys(keys: list[str]) -> list[str]:
    """Rewrite obsolete discipline keys from older saves onto current node keys.

    Unknown keys are dropped so a save referencing a removed node does not
    poison the run; the player simply loses that upgrade on resume.
    """
    valid = {node.key for node in DISCIPLINES}
    migrated: list[str] = []
    for key in keys:
        canonical = LEGACY_DISCIPLINE_KEYS.get(str(key), str(key))
        if canonical in valid and canonical not in migrated:
            migrated.append(canonical)
    return migrated


def discipline_by_key(key: str) -> Discipline | None:
    for node in DISCIPLINES:
        if node.key == key:
            return node
    return None


def disciplines_for_archetype(archetype: str) -> tuple[Discipline, ...]:
    return tuple(node for node in DISCIPLINES if node.archetype == archetype)


def discipline_paths_for_archetype(archetype: str) -> tuple[str, ...]:
    """Discipline Path names in first-seen order, used to lay out the tree columns."""
    paths: list[str] = []
    for node in DISCIPLINES:
        if node.archetype != archetype:
            continue
        if node.path not in paths:
            paths.append(node.path)
    return tuple(paths)


def max_discipline_degree(archetype: str) -> int:
    return max(
        (node.degree for node in DISCIPLINES if node.archetype == archetype),
        default=0,
    )


# --- Milestone 3.7: path commitment limit -----------------------------------
#
# A player may commit to at most MAX_COMMITTED_PATHS discipline-tree paths per
# run. Committing to a path means acquiring any node in it (in practice the
# degree-1 entry node, since higher degrees chain from it). Once the limit is
# hit, every node in the remaining uncommitted paths becomes locked so the
# player is forced to specialize into two routes. Already-committed paths keep
# progressing even if an older save somehow acquired nodes in 3+ paths; the
# lock only blocks *new* commitments.

#: Maximum number of discipline paths a single run may commit to.
MAX_COMMITTED_PATHS: int = 2


def committed_paths(acquired: set[str], archetype: str) -> tuple[str, ...]:
    """Discipline Path names the player has acquired at least one node in.

    Order follows `discipline_paths_for_archetype` so the result is stable for
    rendering and save comparisons.
    """
    committed: list[str] = []
    for path in discipline_paths_for_archetype(archetype):
        nodes = discipline_path_nodes(archetype, path)
        if any(node.key in acquired for node in nodes):
            committed.append(path)
    return tuple(committed)


def is_path_locked(acquired: set[str], archetype: str, path: str) -> bool:
    """True if `path` cannot receive new nodes under the commitment limit.

    A path is locked when the player has already committed to
    `MAX_COMMITTED_PATHS` paths and `path` is not one of them. Paths
    the player has already started remain open regardless of how many there
    are, so legacy saves that pre-date the limit can still progress their
    existing routes.
    """
    committed = committed_paths(acquired, archetype)
    if len(committed) < MAX_COMMITTED_PATHS:
        return False
    return path not in committed


def path_progress(acquired: set[str], archetype: str, path: str) -> int:
    """Number of nodes acquired in a single path (0 if none)."""
    nodes = discipline_path_nodes(archetype, path)
    return sum(1 for node in nodes if node.key in acquired)


# --- Milestone 3.3: skill points, cross-path tags, and combo bonuses ----------
#
# Two layers of bonus reward committing to a discipline tree:
#
# 1. Completed-path bonus (depth): finishing any single path grants a flat
#    bonus per completed path. This rewards going deep into a route, even if
#    the player only commits to one path.
#
# 2. Combo bonus (breadth): completing 2+ paths grants a cumulative combo
#    bonus on top of the per-node effects; the bonus scales by the number of
#    completed paths beyond the first. With four paths per archetype the
#    combo can reach three steps.
#
# Cross-path interactions let one path's nodes modify skills in another
# path via shared tags. Acquiring a node with `cross_path_tags` boosts the
# effective rank of every acquired node carrying one of those tags.
#
# All lookups here are O(nodes) with no per-frame allocations: callers pass the
# player's acquired-key set once and receive plain ints/tuples back.

# Completed-path bonus: a flat reward per finished path (depth). Applied
# once per completed path, so finishing two paths grants twice this.
COMPLETED_PATH_BONUS_MELEE: int = 1
COMPLETED_PATH_BONUS_SPELL: int = 1
COMPLETED_PATH_BONUS_MAX_HP: int = 6

# Combo bonus per completed path beyond the first. Two completed paths
# grant one step; three grant two steps; four grant three steps. Each step adds
# this much melee and spell bonus on top of the per-node and completed-path
# totals.
COMBO_BONUS_PER_STEP_MELEE: int = 2
COMBO_BONUS_PER_STEP_SPELL: int = 2
# Each completed path also grants a small flat max-HP bonus so tankier builds
# that commit to two defensive paths feel the combo payoff.
COMBO_BONUS_PER_STEP_MAX_HP: int = 8


def discipline_path_nodes(archetype: str, path: str) -> tuple[Discipline, ...]:
    """All nodes belonging to a specific (archetype, path) pair."""
    return tuple(
        node
        for node in DISCIPLINES
        if node.archetype == archetype and node.path == path
    )


def completed_paths(acquired: set[str], archetype: str) -> tuple[str, ...]:
    """Discipline Path names whose every node has been acquired, in first-seen order."""
    done: list[str] = []
    for path in discipline_paths_for_archetype(archetype):
        nodes = discipline_path_nodes(archetype, path)
        if nodes and all(node.key in acquired for node in nodes):
            done.append(path)
    return tuple(done)


def combo_bonus_steps(completed_count: int) -> int:
    """Number of combo bonus steps for a completed-path count.

    Two completed paths yield one step; each additional completed path
    adds another step. Fewer than two completed paths yields no combo.
    With four paths per archetype the combo can reach three steps.
    """
    if completed_count < 2:
        return 0
    return completed_count - 1


def completed_path_bonus(acquired: set[str], archetype: str) -> tuple[int, int, int]:
    """Return (melee, spell, max_hp) bonus for completing individual paths.

    This is the depth reward: a flat bonus per finished path, applied even if
    only one path is complete. Distinct from the combo bonus (breadth).
    """
    count = len(completed_paths(acquired, archetype))
    if count <= 0:
        return (0, 0, 0)
    return (
        count * COMPLETED_PATH_BONUS_MELEE,
        count * COMPLETED_PATH_BONUS_SPELL,
        count * COMPLETED_PATH_BONUS_MAX_HP,
    )


def combo_bonus(acquired: set[str], archetype: str) -> tuple[int, int, int]:
    """Return (melee, spell, max_hp) combo bonus for the acquired node set.

    Combines the completed-path depth bonus and the multi-path combo
    breadth bonus into a single total so callers apply one delta.
    """
    completed = completed_paths(acquired, archetype)
    count = len(completed)
    if count <= 0:
        return (0, 0, 0)
    depth_melee, depth_spell, depth_hp = (
        count * COMPLETED_PATH_BONUS_MELEE,
        count * COMPLETED_PATH_BONUS_SPELL,
        count * COMPLETED_PATH_BONUS_MAX_HP,
    )
    steps = combo_bonus_steps(count)
    combo_melee = steps * COMBO_BONUS_PER_STEP_MELEE
    combo_spell = steps * COMBO_BONUS_PER_STEP_SPELL
    combo_hp = steps * COMBO_BONUS_PER_STEP_MAX_HP
    return (
        depth_melee + combo_melee,
        depth_spell + combo_spell,
        depth_hp + combo_hp,
    )


def combo_bonus_preview(
    acquired: set[str], archetype: str, pending_node_key: str
) -> tuple[int, int, int]:
    """Combo bonus if `pending_node_key` were also acquired.

    Used by the character sheet to preview the next combo tier when the player
    hovers a node that would complete another path.
    """
    if pending_node_key in acquired:
        return combo_bonus(acquired, archetype)
    preview = set(acquired)
    preview.add(pending_node_key)
    return combo_bonus(preview, archetype)


def cross_path_tag_bonus(acquired: set[str]) -> tuple[int, int]:
    """Total (melee, spell) bonus from acquired cross-path modifier nodes.

    A node with `cross_path_tags` boosts every acquired node carrying one of
    those tags. The bonus is applied once per matching (modifier node, tag)
    pair against each acquired node that carries the tag, so committing to a
    tag across paths compounds.
    """
    by_key = {node.key: node for node in DISCIPLINES}
    acquired_nodes = [by_key[k] for k in acquired if k in by_key]
    # Map tag -> list of (melee, spell) bonuses from acquired modifier nodes.
    tag_modifiers: dict[str, list[tuple[int, int]]] = {}
    for node in acquired_nodes:
        for tag in node.cross_path_tags:
            tag_modifiers.setdefault(tag, []).append(
                (node.cross_path_bonus_melee, node.cross_path_bonus_spell)
            )
    if not tag_modifiers:
        return (0, 0)
    total_melee = 0
    total_spell = 0
    for node in acquired_nodes:
        for tag in node.tags:
            for melee, spell in tag_modifiers.get(tag, ()):
                total_melee += melee
                total_spell += spell
    return (total_melee, total_spell)


# Backwards-compatible flat upgrade table derived from the discipline tree. Existing
# code paths (`grant_discipline`, `acquired_discipline_summaries`, save files) read
# from `DISCIPLINE_UPGRADES`; deriving it keeps that contract intact while the tree
# becomes the single source of truth for new progression code.
DISCIPLINE_UPGRADES: tuple[DisciplineUpgrade, ...] = tuple(
    DisciplineUpgrade(
        key=node.key,
        archetype=node.archetype,
        name=node.name,
        description=node.description,
        melee_bonus=node.melee_bonus,
        spell_bonus=node.spell_bonus,
        armor_bonus=node.armor_bonus,
        max_hp_bonus=node.max_hp_bonus,
        max_mana_bonus=node.max_mana_bonus,
        max_stamina_bonus=node.max_stamina_bonus,
        speed_bonus=node.speed_bonus,
    )
    for node in DISCIPLINES
)


ELITE_MODIFIERS = (
    EliteModifier(
        "Frenzied",
        "fast attacks with a red warning flash",
        hp_multiplier=1.25,
        damage_bonus=2,
        speed_multiplier=1.18,
        xp_bonus=12,
        color_shift=(45, -10, -10),
    ),
    EliteModifier(
        "Ironbound",
        "slow, armored pressure with a bronze tell",
        hp_multiplier=1.65,
        damage_bonus=1,
        speed_multiplier=0.86,
        xp_bonus=16,
        color_shift=(35, 24, -8),
    ),
    EliteModifier(
        "Venomous",
        "poisoned strikes and sickly green tells",
        hp_multiplier=1.20,
        damage_bonus=4,
        speed_multiplier=1.0,
        xp_bonus=14,
        color_shift=(-20, 42, -16),
    ),
    EliteModifier(
        "Runed",
        "longer aggro and brighter spell telegraphs",
        hp_multiplier=1.35,
        damage_bonus=3,
        speed_multiplier=1.0,
        xp_bonus=18,
        color_shift=(-18, 30, 48),
    ),
)
