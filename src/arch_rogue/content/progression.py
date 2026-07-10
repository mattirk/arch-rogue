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

from ..models import EliteModifier, RunModifier, SkillNode, SkillUpgrade

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


# --- Skill tree -------------------------------------------------------------
#
# Each archetype owns a route-based skill tree with five tiers of depth. A node
# belongs to a named branch (route) and may require one or more prior nodes
# before it can be chosen. Branches let players commit to a playstyle (e.g. a
# "Bulwark" tank route versus a "Riposte" counter route on the Warden) while
# shared tier-1 nodes keep early progression open.
#
# `SKILL_NODES` is the source of truth. `SKILL_UPGRADES` is derived from it so
# older code paths and saves that reference flat upgrade keys keep working: the
# legacy key is preserved as `SkillNode.key`, and the derived `SkillUpgrade`
# carries the same bonuses. New nodes added below expand the tree without
# breaking save compatibility because `player.skill_upgrades` only stores keys.
#
# Migration: a small `LEGACY_SKILL_KEYS` map rewrites obsolete keys from prior
# milestones onto their current node key so old saves resume cleanly.

SKILL_NODES: tuple[SkillNode, ...] = (
    # === Warden ===
    # Tier 1 — shared foundation.
    SkillNode(
        "warden_bulwark",
        "Warden",
        "Bulwark Training",
        "Melee bashes cleave wider and armor improves.",
        tier=1,
        branch="Bulwark",
        prerequisites=(),
        melee_bonus=1,
        armor_bonus=2,
        max_hp_bonus=10,
        tags=("Guard",),
    ),
    SkillNode(
        "warden_riposte",
        "Warden",
        "Riposte Guard",
        "Taking melee hits costs less health and fuels counterattacks.",
        tier=1,
        branch="Riposte",
        prerequisites=(),
        melee_bonus=2,
        armor_bonus=1,
        tags=("Counter",),
    ),
    # Tier 2 — branch commitments.
    SkillNode(
        "warden_aegis",
        "Warden",
        "Aegis Discipline",
        "Guard Step briefly hardens the Warden and Shield Bash staggers enemies.",
        tier=2,
        branch="Bulwark",
        prerequisites=("warden_bulwark",),
        armor_bonus=1,
        max_stamina_bonus=8,
        tags=("Guard",),
    ),
    SkillNode(
        "warden_counter",
        "Warden",
        "Counter Stance",
        "Riposte strikes stagger attackers and grant brief stamina surge.",
        tier=2,
        branch="Riposte",
        prerequisites=("warden_riposte",),
        melee_bonus=2,
        max_stamina_bonus=6,
        tags=("Counter",),
    ),
    # Tier 3 — cross-branch specialist nodes.
    SkillNode(
        "warden_bulwark_ward",
        "Warden",
        "Warden's Ward",
        "Bulwark bashes reach farther and steady allies near the Warden.",
        tier=3,
        branch="Bulwark",
        prerequisites=("warden_aegis",),
        armor_bonus=2,
        max_hp_bonus=12,
        tags=("Guard",),
    ),
    SkillNode(
        "warden_riposte_edge",
        "Warden",
        "Riposte Edge",
        "Counterattacks deal bonus damage to staggered foes.",
        tier=3,
        branch="Riposte",
        prerequisites=("warden_counter",),
        melee_bonus=3,
        armor_bonus=1,
        tags=("Counter",),
    ),
    # Tier 4 — keystone choices. These are the cross-branch modifier nodes:
    # committing deep into one branch amplifies the other branch's tagged
    # skills, so a hybrid Warden feels the synergy.
    SkillNode(
        "warden_iron_vow",
        "Warden",
        "Iron Vow",
        "Armor mastery: heavy hits glance and stamina holds under pressure.",
        tier=4,
        branch="Bulwark",
        prerequisites=("warden_bulwark_ward",),
        armor_bonus=3,
        max_stamina_bonus=12,
        max_hp_bonus=14,
        tags=("Guard",),
        cross_branch_tags=("Counter",),
        cross_branch_bonus_melee=1,
    ),
    SkillNode(
        "warden_reckoning",
        "Warden",
        "Reckoning",
        "Every counter echoes as a Guard Bolt and refunds mana.",
        tier=4,
        branch="Riposte",
        prerequisites=("warden_riposte_edge",),
        melee_bonus=4,
        spell_bonus=2,
        max_mana_bonus=10,
        tags=("Counter",),
        cross_branch_tags=("Guard",),
        cross_branch_bonus_melee=1,
    ),
    # Tier 5 — capstone.
    SkillNode(
        "warden_unbreakable",
        "Warden",
        "Unbreakable Bulwark",
        "Below half health the Warden hardens and bashes clear surrounding foes.",
        tier=5,
        branch="Bulwark",
        prerequisites=("warden_iron_vow",),
        armor_bonus=4,
        max_hp_bonus=24,
        max_stamina_bonus=10,
    ),
    SkillNode(
        "warden_final_reckoning",
        "Warden",
        "Final Reckoning",
        "Counters execute wounded elites and refresh Guard Step.",
        tier=5,
        branch="Riposte",
        prerequisites=("warden_reckoning",),
        melee_bonus=5,
        spell_bonus=3,
        max_stamina_bonus=10,
    ),
    # --- Warden: Vow branch (holy smite and oath magic) ---
    SkillNode(
        "warden_smite",
        "Warden",
        "Smite Oath",
        "Guard Bolt flares with holy light and burns the undead.",
        tier=1,
        branch="Vow",
        prerequisites=(),
        spell_bonus=2,
        max_mana_bonus=8,
        tags=("Holy",),
    ),
    SkillNode(
        "warden_ward",
        "Warden",
        "Temporal Sigil",
        "Time Skip costs less mana, cools down faster, and lasts a beat longer.",
        tier=1,
        branch="Time",
        prerequisites=(),
        armor_bonus=2,
        max_hp_bonus=8,
        tags=("Time",),
    ),
    SkillNode(
        "warden_judgment",
        "Warden",
        "Judgment",
        "Smite chains to a second foe and marks them for counters.",
        tier=2,
        branch="Vow",
        prerequisites=("warden_smite",),
        spell_bonus=3,
        max_mana_bonus=8,
        tags=("Holy",),
    ),
    SkillNode(
        "warden_bulwark_wave",
        "Warden",
        "Time Skip",
        "Time Skip lasts longer and its cast pulse staggers foes caught in the ring.",
        tier=2,
        branch="Time",
        prerequisites=("warden_ward",),
        armor_bonus=2,
        max_stamina_bonus=8,
        tags=("Time",),
    ),
    SkillNode(
        "warden_consecrate",
        "Warden",
        "Consecration",
        "Holy ground burns foes that stand in the Warden's wake.",
        tier=3,
        branch="Vow",
        prerequisites=("warden_judgment",),
        spell_bonus=4,
        max_mana_bonus=10,
        tags=("Holy",),
    ),
    SkillNode(
        "warden_stone_aegis",
        "Warden",
        "Stutter Step",
        "Time Skip slows enemies harder while it lasts.",
        tier=3,
        branch="Time",
        prerequisites=("warden_bulwark_wave",),
        armor_bonus=3,
        max_hp_bonus=12,
        tags=("Time",),
    ),
    SkillNode(
        "warden_divine_wrath",
        "Warden",
        "Divine Wrath",
        "Smite erupts in a holy nova that stuns nearby foes.",
        tier=4,
        branch="Vow",
        prerequisites=("warden_consecrate",),
        spell_bonus=5,
        max_mana_bonus=12,
        tags=("Holy",),
        # Deep Holy pick that amplifies Counter-tagged riposte skills.
        cross_branch_tags=("Counter",),
        cross_branch_bonus_spell=1,
    ),
    SkillNode(
        "warden_unyielding",
        "Warden",
        "Temporal Aegis",
        "While Time Skip is active the Warden takes reduced damage.",
        tier=4,
        branch="Time",
        prerequisites=("warden_stone_aegis",),
        armor_bonus=4,
        max_hp_bonus=16,
        max_stamina_bonus=10,
        tags=("Time",),
        # Deep Time pick that amplifies Guard-tagged bulwark skills.
        cross_branch_tags=("Guard",),
        cross_branch_bonus_melee=1,
    ),
    SkillNode(
        "warden_avatar_of_light",
        "Warden",
        "Avatar of Light",
        "The Warden becomes a beacon: smites heal allies and blind foes.",
        tier=5,
        branch="Vow",
        prerequisites=("warden_divine_wrath",),
        spell_bonus=6,
        max_mana_bonus=16,
        max_hp_bonus=12,
    ),
    SkillNode(
        "warden_eternal_wall",
        "Warden",
        "Eternal Moment",
        "Kills while Time Skip is active refund much of the slot's cooldown.",
        tier=5,
        branch="Time",
        prerequisites=("warden_unyielding",),
        armor_bonus=5,
        max_hp_bonus=24,
        max_stamina_bonus=12,
    ),
    # === Rogue ===
    SkillNode(
        "rogue_precision",
        "Rogue",
        "Killing Precision",
        "Crits are deadlier and quick strikes cost less stamina.",
        tier=1,
        branch="Precision",
        prerequisites=(),
        melee_bonus=3,
        max_stamina_bonus=8,
        tags=("Critical",),
    ),
    SkillNode(
        "rogue_smoke",
        "Rogue",
        "Smoke Step",
        "Evasion improves after using movement skills.",
        tier=1,
        branch="Shadow",
        prerequisites=(),
        speed_bonus=0.15,
        max_stamina_bonus=10,
        tags=("Stealth",),
    ),
    SkillNode(
        "rogue_venom",
        "Rogue",
        "Venomcraft",
        "Backstabs and knife fans poison wounded targets.",
        tier=2,
        branch="Precision",
        prerequisites=("rogue_precision",),
        melee_bonus=1,
        max_stamina_bonus=6,
        tags=("Critical",),
    ),
    SkillNode(
        "rogue_shadowstep",
        "Rogue",
        "Shadowstep",
        "Ambush Bell grants a longer smoke window and Shadow Dash costs less.",
        tier=2,
        branch="Shadow",
        prerequisites=("rogue_smoke",),
        speed_bonus=0.10,
        max_stamina_bonus=8,
        tags=("Stealth",),
    ),
    SkillNode(
        "rogue_executioner",
        "Rogue",
        "Executioner",
        "Crits on poisoned foes deal killing blow damage.",
        tier=3,
        branch="Precision",
        prerequisites=("rogue_venom",),
        melee_bonus=4,
        max_stamina_bonus=6,
        tags=("Critical",),
    ),
    SkillNode(
        "rogue_night_veil",
        "Rogue",
        "Night Veil",
        "Standing in smoke regenerates stamina and grants dodge.",
        tier=3,
        branch="Shadow",
        prerequisites=("rogue_shadowstep",),
        speed_bonus=0.08,
        max_stamina_bonus=12,
        tags=("Stealth",),
    ),
    SkillNode(
        "rogue_crimson_edge",
        "Rogue",
        "Crimson Edge",
        "Killing blows refresh crit chance and bleed poisoned targets.",
        tier=4,
        branch="Precision",
        prerequisites=("rogue_executioner",),
        melee_bonus=5,
        max_hp_bonus=10,
        tags=("Critical",),
        # A deep Precision pick that amplifies Stealth-tagged skills, so a
        # hybrid Rogue feels the cross-branch payoff.
        cross_branch_tags=("Stealth",),
        cross_branch_bonus_melee=1,
    ),
    SkillNode(
        "rogue_phantom",
        "Rogue",
        "Phantom",
        "Shadow Dash leaves a decoy that draws enemy attacks.",
        tier=4,
        branch="Shadow",
        prerequisites=("rogue_night_veil",),
        speed_bonus=0.12,
        max_stamina_bonus=10,
        tags=("Stealth",),
        cross_branch_tags=("Critical",),
        cross_branch_bonus_melee=1,
    ),
    SkillNode(
        "rogue_deathmark",
        "Rogue",
        "Deathmark",
        "Marked foes fall to a single backstab chain.",
        tier=5,
        branch="Precision",
        prerequisites=("rogue_crimson_edge",),
        melee_bonus=6,
        max_stamina_bonus=10,
    ),
    SkillNode(
        "rogue_umbral",
        "Rogue",
        "Umbral Form",
        "Become briefly untouchable after each Shadow Dash.",
        tier=5,
        branch="Shadow",
        prerequisites=("rogue_phantom",),
        speed_bonus=0.14,
        max_stamina_bonus=12,
    ),
    # --- Rogue: Traps branch (Ambush Bell action-skill upgrades) ---
    SkillNode(
        "rogue_trap_craft",
        "Rogue",
        "Bellwright's Hand",
        "Ambush Bell arms faster, lasts longer, and lures from farther away.",
        tier=1,
        branch="Traps",
        prerequisites=(),
        melee_bonus=2,
        spell_bonus=1,
        max_stamina_bonus=6,
        tags=("Trap",),
    ),
    SkillNode(
        "rogue_marksman",
        "Rogue",
        "Marksman",
        "Knife Fan reaches farther and crits from range.",
        tier=1,
        branch="Marksman",
        prerequisites=(),
        melee_bonus=2,
        max_stamina_bonus=8,
        tags=("Aim",),
    ),
    SkillNode(
        "rogue_venom_trap",
        "Rogue",
        "Venom Chime",
        "Ambush Bell dagger bursts poison foes caught in the snap.",
        tier=2,
        branch="Traps",
        prerequisites=("rogue_trap_craft",),
        spell_bonus=2,
        max_stamina_bonus=6,
        tags=("Trap",),
    ),
    SkillNode(
        "rogue_sharpshot",
        "Rogue",
        "Sharpshot",
        "Backstabs from range deal bonus damage and refund stamina.",
        tier=2,
        branch="Marksman",
        prerequisites=("rogue_marksman",),
        melee_bonus=3,
        max_stamina_bonus=8,
        tags=("Aim",),
    ),
    SkillNode(
        "rogue_bear_trap",
        "Rogue",
        "Iron Clapper",
        "Ambush Bell clamps the first foe with a snare and hits lured prey harder.",
        tier=3,
        branch="Traps",
        prerequisites=("rogue_venom_trap",),
        melee_bonus=3,
        spell_bonus=2,
        max_stamina_bonus=6,
        tags=("Trap",),
    ),
    SkillNode(
        "rogue_deadeye",
        "Rogue",
        "Deadeye",
        "Crits from range pierce and apply a stacking mark.",
        tier=3,
        branch="Marksman",
        prerequisites=("rogue_sharpshot",),
        melee_bonus=4,
        max_stamina_bonus=6,
        tags=("Aim",),
    ),
    SkillNode(
        "rogue_trap_master",
        "Rogue",
        "Resonant Lure",
        "Ambush Bell pulls wider, splashes harder, and catches nearby foes in the snare.",
        tier=4,
        branch="Traps",
        prerequisites=("rogue_bear_trap",),
        melee_bonus=4,
        spell_bonus=3,
        max_stamina_bonus=8,
        tags=("Trap",),
        # Deep Trap pick that amplifies Critical-tagged precision skills.
        cross_branch_tags=("Critical",),
        cross_branch_bonus_melee=1,
    ),
    SkillNode(
        "rogue_eagle_eye",
        "Rogue",
        "Eagle Eye",
        "Marked foes take extra crit damage and reveal hidden secrets.",
        tier=4,
        branch="Marksman",
        prerequisites=("rogue_deadeye",),
        melee_bonus=5,
        max_stamina_bonus=8,
        tags=("Aim",),
        # Deep Aim pick that amplifies Stealth-tagged shadow skills.
        cross_branch_tags=("Stealth",),
        cross_branch_bonus_melee=1,
    ),
    SkillNode(
        "rogue_ambush_engineer",
        "Rogue",
        "Cursed Bellwright",
        "Ambush Bell gains a sharper snap and successful ambush kills hasten the next bell.",
        tier=5,
        branch="Traps",
        prerequisites=("rogue_trap_master",),
        melee_bonus=5,
        spell_bonus=4,
        max_stamina_bonus=10,
    ),
    SkillNode(
        "rogue_assassin",
        "Rogue",
        "Assassin",
        "Marked foes die to a single perfect shot from any range.",
        tier=5,
        branch="Marksman",
        prerequisites=("rogue_eagle_eye",),
        melee_bonus=6,
        max_stamina_bonus=10,
    ),
    # === Arcanist ===
    SkillNode(
        "arcanist_splinter",
        "Arcanist",
        "Splintered Arcana",
        "Arc Bolt throws an extra shard.",
        tier=1,
        branch="Bolt",
        prerequisites=(),
        spell_bonus=3,
        max_mana_bonus=10,
        tags=("Arcane",),
    ),
    SkillNode(
        "arcanist_focus",
        "Arcanist",
        "Deep Focus",
        "Mana recovers faster and novas reach farther.",
        tier=1,
        branch="Nova",
        prerequisites=(),
        spell_bonus=2,
        max_mana_bonus=14,
        tags=("Frost",),
    ),
    SkillNode(
        "arcanist_permafrost",
        "Arcanist",
        "Permafrost Sigils",
        "Frost Nova chills longer and Arc Bolt exploits chilled foes.",
        tier=2,
        branch="Nova",
        prerequisites=("arcanist_focus",),
        spell_bonus=2,
        max_mana_bonus=8,
        tags=("Frost",),
    ),
    SkillNode(
        "arcanist_overload",
        "Arcanist",
        "Arc Overload",
        "Bolts split on impact and pierce the first foe.",
        tier=2,
        branch="Bolt",
        prerequisites=("arcanist_splinter",),
        spell_bonus=3,
        max_mana_bonus=8,
        tags=("Arcane",),
    ),
    SkillNode(
        "arcanist_glacial",
        "Arcanist",
        "Glacial Tide",
        "Frost Nova freezes chilled foes in place briefly.",
        tier=3,
        branch="Nova",
        prerequisites=("arcanist_permafrost",),
        spell_bonus=3,
        max_mana_bonus=10,
        tags=("Frost",),
    ),
    SkillNode(
        "arcanist_pierce",
        "Arcanist",
        "Piercing Arc",
        "Bolts pierce two foes and ricochet toward elites.",
        tier=3,
        branch="Bolt",
        prerequisites=("arcanist_overload",),
        spell_bonus=4,
        max_mana_bonus=8,
        tags=("Arcane",),
    ),
    SkillNode(
        "arcanist_blizzard",
        "Arcanist",
        "Blizzard Heart",
        "Standing in chilled air grants mana shield and faster casts.",
        tier=4,
        branch="Nova",
        prerequisites=("arcanist_glacial",),
        spell_bonus=4,
        max_mana_bonus=14,
        armor_bonus=1,
        tags=("Frost",),
        # Deep Frost pick that amplifies Arcane-tagged bolt skills.
        cross_branch_tags=("Arcane",),
        cross_branch_bonus_spell=1,
    ),
    SkillNode(
        "arcanist_storm",
        "Arcanist",
        "Storm Sigil",
        "Bolts chain lightning between nearby foes.",
        tier=4,
        branch="Bolt",
        prerequisites=("arcanist_pierce",),
        spell_bonus=5,
        max_mana_bonus=12,
        tags=("Arcane",),
        cross_branch_tags=("Frost",),
        cross_branch_bonus_spell=1,
    ),
    SkillNode(
        "arcanist_absolute_zero",
        "Arcanist",
        "Absolute Zero",
        "Frost Nova freezes the floor, slowing all enemies in range.",
        tier=5,
        branch="Nova",
        prerequisites=("arcanist_blizzard",),
        spell_bonus=5,
        max_mana_bonus=16,
    ),
    SkillNode(
        "arcanist_arc_tyrant",
        "Arcanist",
        "Arc Tyrant",
        "Bolts seek elites and overload on kill, refilling mana.",
        tier=5,
        branch="Bolt",
        prerequisites=("arcanist_storm",),
        spell_bonus=6,
        max_mana_bonus=14,
    ),
    # --- Arcanist: Storm branch (lightning and chain magic) ---
    SkillNode(
        "arcanist_charge",
        "Arcanist",
        "Static Charge",
        "Arc Bolt builds a charge that discharges on the next cast.",
        tier=1,
        branch="Storm",
        prerequisites=(),
        spell_bonus=2,
        max_mana_bonus=10,
        tags=("Storm",),
    ),
    SkillNode(
        "arcanist_ward",
        "Arcanist",
        "Arcane Ward",
        "A mana shield absorbs hits and reflects arcane damage.",
        tier=1,
        branch="Ward",
        prerequisites=(),
        armor_bonus=1,
        max_mana_bonus=12,
        tags=("Shield",),
    ),
    SkillNode(
        "arcanist_chain_lightning",
        "Arcanist",
        "Chain Lightning",
        "Bolts arc between up to three foes, weakening each.",
        tier=2,
        branch="Storm",
        prerequisites=("arcanist_charge",),
        spell_bonus=3,
        max_mana_bonus=8,
        tags=("Storm",),
    ),
    SkillNode(
        "arcanist_ward_mend",
        "Arcanist",
        "Warding Mend",
        "The ward heals the Arcanist when it absorbs a hit.",
        tier=2,
        branch="Ward",
        prerequisites=("arcanist_ward",),
        armor_bonus=2,
        max_mana_bonus=10,
        max_hp_bonus=8,
        tags=("Shield",),
    ),
    SkillNode(
        "arcanist_tempest",
        "Arcanist",
        "Tempest",
        "A storm front lingers, repeatedly striking foes in range.",
        tier=3,
        branch="Storm",
        prerequisites=("arcanist_chain_lightning",),
        spell_bonus=4,
        max_mana_bonus=10,
        tags=("Storm",),
    ),
    SkillNode(
        "arcanist_ward_overload",
        "Arcanist",
        "Ward Overload",
        "A depleted ward detonates, damaging nearby foes.",
        tier=3,
        branch="Ward",
        prerequisites=("arcanist_ward_mend",),
        armor_bonus=2,
        spell_bonus=2,
        max_mana_bonus=12,
        tags=("Shield",),
    ),
    SkillNode(
        "arcanist_storm_caller",
        "Arcanist",
        "Stormcaller",
        "Tempests grow into a full storm that hunts elites.",
        tier=4,
        branch="Storm",
        prerequisites=("arcanist_tempest",),
        spell_bonus=5,
        max_mana_bonus=12,
        tags=("Storm",),
        # Deep Storm pick that amplifies Frost-tagged nova skills.
        cross_branch_tags=("Frost",),
        cross_branch_bonus_spell=1,
    ),
    SkillNode(
        "arcanist_aegis",
        "Arcanist",
        "Arcane Aegis",
        "The ward becomes permanent and reflects spells.",
        tier=4,
        branch="Ward",
        prerequisites=("arcanist_ward_overload",),
        armor_bonus=3,
        max_mana_bonus=14,
        max_hp_bonus=10,
        tags=("Shield",),
        # Deep Shield pick that amplifies Arcane-tagged bolt skills.
        cross_branch_tags=("Arcane",),
        cross_branch_bonus_spell=1,
    ),
    SkillNode(
        "arcanist_world_storm",
        "Arcanist",
        "World Storm",
        "The storm engulfs the floor, striking every foe each beat.",
        tier=5,
        branch="Storm",
        prerequisites=("arcanist_storm_caller",),
        spell_bonus=6,
        max_mana_bonus=16,
    ),
    SkillNode(
        "arcanist_eternal_aegis",
        "Arcanist",
        "Eternal Aegis",
        "The aegis cannot be broken and shields allies near the Arcanist.",
        tier=5,
        branch="Ward",
        prerequisites=("arcanist_aegis",),
        armor_bonus=4,
        max_mana_bonus=18,
        max_hp_bonus=14,
    ),
    # === Acolyte ===
    SkillNode(
        "acolyte_sanguine",
        "Acolyte",
        "Sanguine Rite",
        "Blood skills leech more life at close range.",
        tier=1,
        branch="Blood",
        prerequisites=(),
        melee_bonus=1,
        spell_bonus=2,
        max_hp_bonus=8,
        tags=("Blood",),
    ),
    SkillNode(
        "acolyte_veil",
        "Acolyte",
        "Veil of Ash",
        "Mana shields blunt harsher blows.",
        tier=1,
        branch="Veil",
        prerequisites=(),
        armor_bonus=1,
        max_mana_bonus=8,
        tags=("Veil",),
    ),
    SkillNode(
        "acolyte_gravebind",
        "Acolyte",
        "Gravebind Covenant",
        "Blood Rite and Spirit Bolt bind foes, and kills echo more life into the Acolyte.",
        tier=2,
        branch="Blood",
        prerequisites=("acolyte_sanguine",),
        spell_bonus=2,
        max_hp_bonus=6,
        max_mana_bonus=6,
        tags=("Blood",),
    ),
    SkillNode(
        "acolyte_ashen",
        "Acolyte",
        "Ashen Ward",
        "Veil of Ash reflects damage and cleanses status on use.",
        tier=2,
        branch="Veil",
        prerequisites=("acolyte_veil",),
        armor_bonus=2,
        max_mana_bonus=10,
        tags=("Veil",),
    ),
    SkillNode(
        "acolyte_blood_pact",
        "Acolyte",
        "Blood Pact",
        "Spend health to cast when mana runs dry; lifesteal intensifies.",
        tier=3,
        branch="Blood",
        prerequisites=("acolyte_gravebind",),
        spell_bonus=3,
        max_hp_bonus=10,
        tags=("Blood",),
    ),
    SkillNode(
        "acolyte_spirit_host",
        "Acolyte",
        "Spirit Host",
        "Spirit Bolt summons a brief wraith that harries foes.",
        tier=3,
        branch="Veil",
        prerequisites=("acolyte_ashen",),
        spell_bonus=3,
        max_mana_bonus=10,
        tags=("Veil",),
    ),
    SkillNode(
        "acolyte_crimson_maw",
        "Acolyte",
        "Crimson Maw",
        "Blood skills devour weak foes, healing the Acolyte massively.",
        tier=4,
        branch="Blood",
        prerequisites=("acolyte_blood_pact",),
        spell_bonus=4,
        max_hp_bonus=14,
        melee_bonus=2,
        tags=("Blood",),
        # Deep Blood pick that amplifies Veil-tagged shield skills.
        cross_branch_tags=("Veil",),
        cross_branch_bonus_spell=1,
    ),
    SkillNode(
        "acolyte_grave_chorus",
        "Acolyte",
        "Grave Chorus",
        "Wraiths persist longer and shield the Acolyte when struck.",
        tier=4,
        branch="Veil",
        prerequisites=("acolyte_spirit_host",),
        spell_bonus=4,
        max_mana_bonus=14,
        armor_bonus=2,
        tags=("Veil",),
        # Deep Veil pick that amplifies Blood-tagged rite skills.
        cross_branch_tags=("Blood",),
        cross_branch_bonus_spell=1,
    ),
    SkillNode(
        "acolyte_sanguine_ascendant",
        "Acolyte",
        "Sanguine Ascendant",
        "Below half health, blood skills cost no mana and leech doubles.",
        tier=5,
        branch="Blood",
        prerequisites=("acolyte_crimson_maw",),
        spell_bonus=5,
        max_hp_bonus=20,
        melee_bonus=3,
        tags=("Blood",),
    ),
    SkillNode(
        "acolyte_undying_veil",
        "Acolyte",
        "Undying Veil",
        "Once per floor, a fatal blow is absorbed by the veil.",
        tier=5,
        branch="Veil",
        prerequisites=("acolyte_grave_chorus",),
        spell_bonus=5,
        max_mana_bonus=16,
        armor_bonus=3,
        tags=("Veil",),
    ),
    # --- Acolyte: Spirit branch (summoning and wraith control) ---
    SkillNode(
        "acolyte_spirit_call",
        "Acolyte",
        "Spirit Call",
        "Summon a wisp familiar that follows you and harries foes; it grows into a watchful owl as your Spirit deepens.",
        tier=1,
        branch="Spirit",
        prerequisites=(),
        spell_bonus=2,
        max_mana_bonus=8,
        tags=("Spirit",),
    ),
    SkillNode(
        "acolyte_curse",
        "Acolyte",
        "Hex",
        "Spirit Bolt curses foes, weakening their attacks.",
        tier=1,
        branch="Curse",
        prerequisites=(),
        spell_bonus=2,
        max_mana_bonus=8,
        tags=("Curse",),
    ),
    SkillNode(
        "acolyte_wraith_host",
        "Acolyte",
        "Owl Companion",
        "The owl familiar persists, growing heartier and harrying foes at your side.",
        tier=2,
        branch="Spirit",
        prerequisites=("acolyte_spirit_call",),
        spell_bonus=3,
        max_mana_bonus=8,
        tags=("Spirit",),
    ),
    SkillNode(
        "acolyte_decay",
        "Acolyte",
        "Decay",
        "Cursed foes rot, losing health each second.",
        tier=2,
        branch="Curse",
        prerequisites=("acolyte_curse",),
        spell_bonus=3,
        max_mana_bonus=8,
        tags=("Curse",),
    ),
    SkillNode(
        "acolyte_bone_legion",
        "Acolyte",
        "Twin Owls",
        "Call a second owl to fight beside the Acolyte, striking harder than the first.",
        tier=3,
        branch="Spirit",
        prerequisites=("acolyte_wraith_host",),
        spell_bonus=4,
        max_mana_bonus=10,
        melee_bonus=2,
        tags=("Spirit",),
    ),
    SkillNode(
        "acolyte_fragility",
        "Acolyte",
        "Fragility",
        "Cursed foes take increased damage from all sources.",
        tier=3,
        branch="Curse",
        prerequisites=("acolyte_decay",),
        spell_bonus=4,
        max_mana_bonus=10,
        tags=("Curse",),
    ),
    SkillNode(
        "acolyte_wraith_lord",
        "Acolyte",
        "Owl Lord",
        "A champion owl guards the Acolyte, taunting foes with greater presence and size.",
        tier=4,
        branch="Spirit",
        prerequisites=("acolyte_bone_legion",),
        spell_bonus=5,
        max_mana_bonus=12,
        melee_bonus=3,
        tags=("Spirit",),
        # Deep Spirit pick that amplifies Curse-tagged debuff skills.
        cross_branch_tags=("Curse",),
        cross_branch_bonus_spell=1,
    ),
    SkillNode(
        "acolyte_doom",
        "Acolyte",
        "Doom",
        "Cursed foes are marked for death, exploding on death.",
        tier=4,
        branch="Curse",
        prerequisites=("acolyte_fragility",),
        spell_bonus=5,
        max_mana_bonus=12,
        tags=("Curse",),
        # Deep Curse pick that amplifies Spirit-tagged summon skills.
        cross_branch_tags=("Spirit",),
        cross_branch_bonus_spell=1,
    ),
    SkillNode(
        "acolyte_legion_eternal",
        "Acolyte",
        "Eternal Owls",
        "The owl host becomes unkillable and a third owl joins the vigil.",
        tier=5,
        branch="Spirit",
        prerequisites=("acolyte_wraith_lord",),
        spell_bonus=6,
        max_mana_bonus=16,
        melee_bonus=4,
    ),
    SkillNode(
        "acolyte_eternal_doom",
        "Acolyte",
        "Eternal Doom",
        "Doom spreads to nearby foes on death, cursing the survivors.",
        tier=5,
        branch="Curse",
        prerequisites=("acolyte_doom",),
        spell_bonus=6,
        max_mana_bonus=16,
    ),
    # === Ranger ===
    SkillNode(
        "ranger_snare",
        "Ranger",
        "Barbed Snares",
        "Control skills delay enemies longer.",
        tier=1,
        branch="Control",
        prerequisites=(),
        spell_bonus=2,
        max_stamina_bonus=8,
        tags=("Control",),
    ),
    SkillNode(
        "ranger_volley",
        "Ranger",
        "Volley Drills",
        "Multishot spreads into a wider fan.",
        tier=1,
        branch="Volley",
        prerequisites=(),
        melee_bonus=1,
        spell_bonus=2,
        tags=("Volley",),
    ),
    SkillNode(
        "ranger_beastmark",
        "Ranger",
        "Beastmark Pursuit",
        "Vault refreshes momentum and marked shots hit controlled enemies harder.",
        tier=2,
        branch="Control",
        prerequisites=("ranger_snare",),
        melee_bonus=1,
        speed_bonus=0.12,
        max_stamina_bonus=6,
        tags=("Control",),
    ),
    SkillNode(
        "ranger_rapid",
        "Ranger",
        "Rapid Volley",
        "Multishot fires an extra arrow and reloads faster.",
        tier=2,
        branch="Volley",
        prerequisites=("ranger_volley",),
        melee_bonus=2,
        spell_bonus=2,
        max_stamina_bonus=6,
        tags=("Volley",),
    ),
    SkillNode(
        "ranger_thornfield",
        "Ranger",
        "Thornfield",
        "Snares grow thorns, damaging foes that struggle in them.",
        tier=3,
        branch="Control",
        prerequisites=("ranger_beastmark",),
        spell_bonus=3,
        max_stamina_bonus=8,
        tags=("Control",),
    ),
    SkillNode(
        "ranger_piercing_volley",
        "Ranger",
        "Piercing Volley",
        "Arrows pierce the first foe and seek marked targets.",
        tier=3,
        branch="Volley",
        prerequisites=("ranger_rapid",),
        melee_bonus=3,
        spell_bonus=3,
        tags=("Volley",),
    ),
    SkillNode(
        "ranger_hunter_drive",
        "Ranger",
        "Hunter's Drive",
        "Vault resets attack cooldowns and grants a brief speed surge.",
        tier=4,
        branch="Control",
        prerequisites=("ranger_thornfield",),
        speed_bonus=0.14,
        max_stamina_bonus=12,
        melee_bonus=2,
        tags=("Control",),
        # Deep Control pick that amplifies Beast-tagged companion skills.
        cross_branch_tags=("Beast",),
        cross_branch_bonus_melee=1,
    ),
    SkillNode(
        "ranger_storm_volley",
        "Ranger",
        "Storm Volley",
        "Multishot arcs into a storm that hits all foes in a cone.",
        tier=4,
        branch="Volley",
        prerequisites=("ranger_piercing_volley",),
        melee_bonus=4,
        spell_bonus=4,
        max_stamina_bonus=8,
        tags=("Volley",),
        # Deep Volley pick that amplifies Survival-tagged field skills.
        cross_branch_tags=("Survival",),
        cross_branch_bonus_melee=1,
    ),
    SkillNode(
        "ranger_wild_domination",
        "Ranger",
        "Wild Domination",
        "Marked foes are rooted and struck by a beast companion.",
        tier=5,
        branch="Control",
        prerequisites=("ranger_hunter_drive",),
        spell_bonus=5,
        max_stamina_bonus=14,
        speed_bonus=0.10,
        tags=("Control",),
    ),
    SkillNode(
        "ranger_sky_quiver",
        "Ranger",
        "Sky Quiver",
        "Multishot becomes a relentless barrage while standing still.",
        tier=5,
        branch="Volley",
        prerequisites=("ranger_storm_volley",),
        melee_bonus=5,
        spell_bonus=5,
        max_stamina_bonus=10,
        tags=("Volley",),
    ),
    # --- Ranger: Beast branch (companion taming and pack tactics) ---
    SkillNode(
        "ranger_beast_bond",
        "Ranger",
        "Beast Bond",
        "A wolf companion joins the Ranger and harries foes.",
        tier=1,
        branch="Beast",
        prerequisites=(),
        melee_bonus=2,
        max_stamina_bonus=8,
        tags=("Beast",),
    ),
    SkillNode(
        "ranger_survival",
        "Ranger",
        "Survivalist",
        "The Ranger regenerates stamina faster and resists traps.",
        tier=1,
        branch="Survival",
        prerequisites=(),
        max_hp_bonus=8,
        max_stamina_bonus=10,
        tags=("Survival",),
    ),
    SkillNode(
        "ranger_pack_tactics",
        "Ranger",
        "Pack Tactics",
        "The companion strikes marked foes and shares dodge chance.",
        tier=2,
        branch="Beast",
        prerequisites=("ranger_beast_bond",),
        melee_bonus=3,
        max_stamina_bonus=6,
        tags=("Beast",),
    ),
    SkillNode(
        "ranger_camouflage",
        "Ranger",
        "Camouflage",
        "Standing still grants stealth and a guaranteed first strike.",
        tier=2,
        branch="Survival",
        prerequisites=("ranger_survival",),
        speed_bonus=0.10,
        max_stamina_bonus=8,
        tags=("Survival",),
    ),
    SkillNode(
        "ranger_alpha",
        "Ranger",
        "Alpha",
        "The companion becomes a dire wolf that knocks foes back.",
        tier=3,
        branch="Beast",
        prerequisites=("ranger_pack_tactics",),
        melee_bonus=4,
        max_stamina_bonus=8,
        tags=("Beast",),
    ),
    SkillNode(
        "ranger_pathfinder",
        "Ranger",
        "Pathfinder",
        "The Ranger reveals secrets and shrines on the floor.",
        tier=3,
        branch="Survival",
        prerequisites=("ranger_camouflage",),
        spell_bonus=2,
        max_stamina_bonus=10,
        tags=("Survival",),
    ),
    SkillNode(
        "ranger_spirit_companion",
        "Ranger",
        "Spirit Companion",
        "The dire wolf becomes a spirit beast that strikes through foes.",
        tier=4,
        branch="Beast",
        prerequisites=("ranger_alpha",),
        melee_bonus=5,
        spell_bonus=2,
        max_stamina_bonus=10,
        tags=("Beast",),
        # Deep Beast pick that amplifies Volley-tagged ranged skills.
        cross_branch_tags=("Volley",),
        cross_branch_bonus_melee=1,
    ),
    SkillNode(
        "ranger_ambush",
        "Ranger",
        "Ambush",
        "First strikes from stealth deal massive bonus damage.",
        tier=4,
        branch="Survival",
        prerequisites=("ranger_pathfinder",),
        melee_bonus=4,
        speed_bonus=0.12,
        max_stamina_bonus=12,
        tags=("Survival",),
        # Deep Survival pick that amplifies Control-tagged snare skills.
        cross_branch_tags=("Control",),
        cross_branch_bonus_melee=1,
    ),
    SkillNode(
        "ranger_primal_lord",
        "Ranger",
        "Primal Lord",
        "The spirit beast becomes a primal champion that mauls elites.",
        tier=5,
        branch="Beast",
        prerequisites=("ranger_spirit_companion",),
        melee_bonus=6,
        spell_bonus=3,
        max_stamina_bonus=12,
    ),
    SkillNode(
        "ranger_ghost_step",
        "Ranger",
        "Ghost Step",
        "The Ranger becomes untargetable while moving and dodges traps.",
        tier=5,
        branch="Survival",
        prerequisites=("ranger_ambush",),
        speed_bonus=0.16,
        max_stamina_bonus=14,
        max_hp_bonus=10,
    ),
)


# Obsolete keys from earlier milestones mapped onto their current node key.
# Used by `migrate_skill_keys` so older saves resume against the new tree.
LEGACY_SKILL_KEYS: dict[str, str] = {
    # No renames yet — all original keys are preserved as node keys — but the
    # table is in place so future migrations stay save-compatible.
}


def migrate_skill_keys(keys: list[str]) -> list[str]:
    """Rewrite obsolete skill keys from older saves onto current node keys.

    Unknown keys are dropped so a save referencing a removed node does not
    poison the run; the player simply loses that upgrade on resume.
    """
    valid = {node.key for node in SKILL_NODES}
    migrated: list[str] = []
    for key in keys:
        canonical = LEGACY_SKILL_KEYS.get(str(key), str(key))
        if canonical in valid and canonical not in migrated:
            migrated.append(canonical)
    return migrated


def skill_node_by_key(key: str) -> SkillNode | None:
    for node in SKILL_NODES:
        if node.key == key:
            return node
    return None


def skill_nodes_for_archetype(archetype: str) -> tuple[SkillNode, ...]:
    return tuple(node for node in SKILL_NODES if node.archetype == archetype)


def skill_branches_for_archetype(archetype: str) -> tuple[str, ...]:
    """Branch names in first-seen order, used to lay out the tree columns."""
    branches: list[str] = []
    for node in SKILL_NODES:
        if node.archetype != archetype:
            continue
        if node.branch not in branches:
            branches.append(node.branch)
    return tuple(branches)


def skill_tree_max_tier(archetype: str) -> int:
    return max(
        (node.tier for node in SKILL_NODES if node.archetype == archetype),
        default=0,
    )


# --- Milestone 3.7: branch commitment limit ---------------------------------
#
# A player may commit to at most MAX_COMMITTED_BRANCHES skill-tree branches per
# run. Committing to a branch means acquiring any node in it (in practice the
# tier-1 entry node, since higher tiers chain from it). Once the limit is hit,
# every node in the remaining uncommitted branches becomes locked so the player
# is forced to specialize into two routes. Already-committed branches keep
# progressing even if an older save somehow acquired nodes in 3+ branches; the
# lock only blocks *new* commitments.

#: Maximum number of branches a single run may commit to.
MAX_COMMITTED_BRANCHES: int = 2


def committed_branches(acquired: set[str], archetype: str) -> tuple[str, ...]:
    """Branch names the player has acquired at least one node in.

    Order follows `skill_branches_for_archetype` so the result is stable for
    rendering and save comparisons.
    """
    committed: list[str] = []
    for branch in skill_branches_for_archetype(archetype):
        nodes = skill_branch_nodes(archetype, branch)
        if any(node.key in acquired for node in nodes):
            committed.append(branch)
    return tuple(committed)


def is_branch_locked(acquired: set[str], archetype: str, branch: str) -> bool:
    """True if `branch` cannot receive new nodes under the commitment limit.

    A branch is locked when the player has already committed to
    `MAX_COMMITTED_BRANCHES` branches and `branch` is not one of them. Branches
    the player has already started remain open regardless of how many there
    are, so legacy saves that pre-date the limit can still progress their
    existing routes.
    """
    committed = committed_branches(acquired, archetype)
    if len(committed) < MAX_COMMITTED_BRANCHES:
        return False
    return branch not in committed


def branch_progress(acquired: set[str], archetype: str, branch: str) -> int:
    """Number of nodes acquired in a single branch (0 if none)."""
    nodes = skill_branch_nodes(archetype, branch)
    return sum(1 for node in nodes if node.key in acquired)


# --- Milestone 3.3: skill points, cross-branch tags, and combo bonuses -------
#
# Two layers of bonus reward committing to a skill tree:
#
# 1. Completed-branch bonus (depth): finishing any single branch grants a flat
#    bonus per completed branch. This rewards going deep into a route, even if
#    the player only commits to one path.
#
# 2. Combo bonus (breadth): completing 2+ branches grants a cumulative combo
#    bonus on top of the per-node effects; the bonus scales by the number of
#    completed branches beyond the first. With four branches per archetype the
#    combo can reach three steps.
#
# Cross-branch interactions let one branch's nodes modify skills in another
# branch via shared tags. Acquiring a node with `cross_branch_tags` boosts the
# effective rank of every acquired node carrying one of those tags.
#
# All lookups here are O(nodes) with no per-frame allocations: callers pass the
# player's acquired-key set once and receive plain ints/tuples back.

# Completed-branch bonus: a flat reward per finished branch (depth). Applied
# once per completed branch, so finishing two branches grants twice this.
COMPLETED_BRANCH_BONUS_MELEE: int = 1
COMPLETED_BRANCH_BONUS_SPELL: int = 1
COMPLETED_BRANCH_BONUS_MAX_HP: int = 6

# Combo bonus per completed branch beyond the first. Two completed branches
# grant one step; three grant two steps; four grant three steps. Each step adds
# this much melee and spell bonus on top of the per-node and completed-branch
# totals.
COMBO_BONUS_PER_STEP_MELEE: int = 2
COMBO_BONUS_PER_STEP_SPELL: int = 2
# Each completed branch also grants a small flat max-HP bonus so tankier builds
# that commit to two defensive branches feel the combo payoff.
COMBO_BONUS_PER_STEP_MAX_HP: int = 8


def skill_branch_nodes(archetype: str, branch: str) -> tuple[SkillNode, ...]:
    """All nodes belonging to a specific (archetype, branch) pair."""
    return tuple(
        node
        for node in SKILL_NODES
        if node.archetype == archetype and node.branch == branch
    )


def completed_branches(acquired: set[str], archetype: str) -> tuple[str, ...]:
    """Branch names whose every node has been acquired, in first-seen order."""
    done: list[str] = []
    for branch in skill_branches_for_archetype(archetype):
        nodes = skill_branch_nodes(archetype, branch)
        if nodes and all(node.key in acquired for node in nodes):
            done.append(branch)
    return tuple(done)


def combo_bonus_steps(completed_count: int) -> int:
    """Number of combo bonus steps for a completed-branch count.

    Two completed branches yield one step; each additional completed branch
    adds another step. Fewer than two completed branches yields no combo.
    With four branches per archetype the combo can reach three steps.
    """
    if completed_count < 2:
        return 0
    return completed_count - 1


def completed_branch_bonus(acquired: set[str], archetype: str) -> tuple[int, int, int]:
    """Return (melee, spell, max_hp) bonus for completing individual branches.

    This is the depth reward: a flat bonus per finished branch, applied even if
    only one branch is complete. Distinct from the combo bonus (breadth).
    """
    count = len(completed_branches(acquired, archetype))
    if count <= 0:
        return (0, 0, 0)
    return (
        count * COMPLETED_BRANCH_BONUS_MELEE,
        count * COMPLETED_BRANCH_BONUS_SPELL,
        count * COMPLETED_BRANCH_BONUS_MAX_HP,
    )


def combo_bonus(acquired: set[str], archetype: str) -> tuple[int, int, int]:
    """Return (melee, spell, max_hp) combo bonus for the acquired node set.

    Combines the completed-branch depth bonus and the multi-branch combo
    breadth bonus into a single total so callers apply one delta.
    """
    completed = completed_branches(acquired, archetype)
    count = len(completed)
    if count <= 0:
        return (0, 0, 0)
    depth_melee, depth_spell, depth_hp = (
        count * COMPLETED_BRANCH_BONUS_MELEE,
        count * COMPLETED_BRANCH_BONUS_SPELL,
        count * COMPLETED_BRANCH_BONUS_MAX_HP,
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
    hovers a node that would complete another branch.
    """
    if pending_node_key in acquired:
        return combo_bonus(acquired, archetype)
    preview = set(acquired)
    preview.add(pending_node_key)
    return combo_bonus(preview, archetype)


def cross_branch_tag_bonus(acquired: set[str]) -> tuple[int, int]:
    """Total (melee, spell) bonus from acquired cross-branch modifier nodes.

    A node with `cross_branch_tags` boosts every acquired node carrying one of
    those tags. The bonus is applied once per matching (modifier node, tag)
    pair against each acquired node that carries the tag, so committing to a
    tag across branches compounds.
    """
    by_key = {node.key: node for node in SKILL_NODES}
    acquired_nodes = [by_key[k] for k in acquired if k in by_key]
    # Map tag -> list of (melee, spell) bonuses from acquired modifier nodes.
    tag_modifiers: dict[str, list[tuple[int, int]]] = {}
    for node in acquired_nodes:
        for tag in node.cross_branch_tags:
            tag_modifiers.setdefault(tag, []).append(
                (node.cross_branch_bonus_melee, node.cross_branch_bonus_spell)
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


# Backwards-compatible flat upgrade table derived from the skill tree. Existing
# code paths (`grant_skill_upgrade`, `acquired_skill_upgrades`, save files) read
# from `SKILL_UPGRADES`; deriving it keeps that contract intact while the tree
# becomes the single source of truth for new progression code.
SKILL_UPGRADES: tuple[SkillUpgrade, ...] = tuple(
    SkillUpgrade(
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
    for node in SKILL_NODES
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
