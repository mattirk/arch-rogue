#!/usr/bin/env python3
"""Deterministically import the curated Action RPG SFX Pack runtime banks."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = ROOT / "build" / "action-rpg-sfx-pack"
DEFAULT_OUTPUT = ROOT / "assets" / "audio" / "sfx"
SAMPLE_RATE = 48_000
CHANNELS = 2
SAMPLE_SIZE_BITS = 16
PLAYER_ACTION_SFX_MAX_SECONDS = 0.8
OTHER_SFX_MAX_SECONDS = 2.5
SFX_CAP_FADE_SECONDS = 0.40
PLAYER_ACTION_BANKS = {
    "melee_swing_warden", "melee_swing_rogue", "melee_swing_arcanist", "melee_swing_acolyte", "melee_swing_ranger",
    "big_hit_charge", "big_hit_release", "dash_cloth_light", "dash_armored", "dash_arcane", "dash_occult", "shield_block",
    "bow_release_light", "bow_release_heavy", "arrow_volley", "physical_throw", "warden_guard_bolt",
    "arcane_cast", "fire_cast", "frost_cast", "shadow_cast",
    "warden_time_skip", "rogue_bell_cast", "rogue_bell_detonate", "rogue_stealth", "arcanist_nova", "acolyte_spirit_call",
    "ranger_beast_summon", "ranger_beast_command",
}

# Publisher paths are intentionally literal. Do not reconstruct these names from
# patterns: the pack contains misspellings and inconsistent trailing underscores.
BANK_SOURCES: dict[str, tuple[str, ...]] = {
    "ui_navigate": (
        "UI/UI_Tick_Tap_Short_01_01.wav", "UI/UI_Tick_Tap_Short_01_02.wav", "UI/UI_Tick_Tap_Short_01_03.wav",
    ),
    "ui_confirm": (
        "UI/UI_Hit_Button_Wooden_Tap_Paper_Flap_01_01.wav", "UI/UI_Hit_Button_Wooden_Tap_Paper_Flap_01_02_.wav", "UI/UI_Hit_Button_Wooden_Tap_Paper_Flap_01_03.wav",
    ),
    "ui_back": (
        "UI/UI_Tap_Hard_Deep_Short_01_01.wav", "UI/UI_Tap_Hard_Deep_Short_01_02.wav", "UI/UI_Tap_Hard_Deep_Short_01_03.wav",
    ),
    "ui_reject": ("UI/UI_Hit_Deep_01.wav",),
    "ui_equip": ("UI/UI_Tap_Hard_Hit_Metal_01_01.wav", "UI/UI_Tap_Hard_Hit_Metal_01_02.wav"),
    "ui_purchase": (
        "UI/UI_Hit_Bright_Tone_Short_01_01.wav", "UI/UI_Hit_Bright_Tone_Short_01_02.wav", "UI/UI_Hit_Bright_Tone_Short_01_03.wav",
    ),
    "run_start": (
        "Notification/Notification_Thud_Deep_Impact_Metal_Sweep_01_01.wav", "Notification/Notification_Thud_Deep_Impact_Metal_Sweep_01_02.wav",
    ),
    "level_up": (
        "Notification/Notification_Whoosh_Thud_Deep_Impact_Upward_Bright_Tone_Chime_01_01.wav", "Notification/Notification_Whoosh_Thud_Deep_Impact_Upward_Bright_Tone_Chime_01_02.wav",
    ),
    "victory": (
        "Notification/Notification_Whoosh_Cinematic_Rise_Airy_Bell_Impact_01_01.wav", "Notification/Notification_Whoosh_Cinematic_Rise_Airy_Bell_Impact_01_02.wav", "Notification/Notification_Whoosh_Cinematic_Rise_Airy_Bell_Impact_01_03_.wav",
    ),
    "story_consequence": (
        "Notification/Notification_Thud_Deep_Impact_Metal_Sweep_02_01.wav", "Notification/Notification_Thud_Deep_Impact_Metal_Sweep_02_02.wav", "Notification/Notification_Thud_Deep_Impact_Metal_Sweep_02_03.wav",
    ),
    "relic_recovered": (
        "Notification/Notification_Impact_Hit_Harp_Dark_Tune_01_01.wav", "Notification/Notification_Impact_Hit_Harp_Dark_Tune_01_02.wav",
    ),
    "epilogue_bell": ("UI/UI_Hit_Deep_Bell_01.wav",),
    "melee_swing_warden": (
        "Combat/Melee_Weapon_Swing_Heavy_Thud_Metal_Friction_01_01.wav", "Combat/Melee_Weapon_Swing_Heavy_Thud_Metal_Friction_01_02_.wav", "Combat/Melee_Weapon_Swing_Heavy_Thud_Metal_Friction_01_03.wav",
    ),
    "melee_swing_rogue": (
        "Combat/Melee_Weapon_Swing_Sharp_Metal_Friction_Small_Short_01_01.wav", "Combat/Melee_Weapon_Swing_Sharp_Metal_Friction_Small_Short_01_02.wav", "Combat/Melee_Weapon_Swing_Sharp_Metal_Friction_Small_Short_01_03.wav",
    ),
    "melee_swing_arcanist": (
        "Combat/Melee_Weapon_Swing_Simple_Small_Short_01_01.wav", "Combat/Melee_Weapon_Swing_Simple_Small_Short_01_02.wav", "Combat/Melee_Weapon_Swing_Simple_Small_Short_01_03.wav",
    ),
    "melee_swing_acolyte": (
        "Combat/Melee_Barehand_Combat_Swing_01_01.wav", "Combat/Melee_Barehand_Combat_Swing_01_02.wav", "Combat/Melee_Barehand_Combat_Swing_01_03.wav",
    ),
    "melee_swing_ranger": (
        "Combat/Melee_Weapon_Swing_Sharp_Metal_Friction_Small_Short_02_01.wav", "Combat/Melee_Weapon_Swing_Sharp_Metal_Friction_Small_Short_02_02.wav", "Combat/Melee_Weapon_Swing_Sharp_Metal_Friction_Small_Short_02_03.wav",
    ),
    "big_hit_charge": (
        "Designed Skill/Designed_Skill_Magic_Sword_Long_Rise_Metal_Scrap_Friction_01_01.wav", "Designed Skill/Designed_Skill_Magic_Sword_Long_Rise_Metal_Scrap_Friction_01_02.wav", "Designed Skill/Designed_Skill_Magic_Sword_Long_Rise_Metal_Scrap_Friction_01_03.wav",
    ),
    "big_hit_release": (
        "Combat/Melee_Weapon_Swing_Heavy_Deep_Slow_Hard_01_01.wav", "Combat/Melee_Weapon_Swing_Heavy_Deep_Slow_Hard_01_02.wav",
    ),
    "dash_cloth_light": (
        "Movement/Whoosh_Dodge_Cloth_Movement_Light_01_01.wav", "Movement/Whoosh_Dodge_Cloth_Movement_Light_01_02.wav", "Movement/Whoosh_Dodge_Cloth_Movement_Light_01_03.wav",
    ),
    "dash_armored": (
        "Movement/Whoosh_Dodge_Hard_Cloth_Movement_Metal_Heavy_01_01.wav", "Movement/Whoosh_Dodge_Hard_Cloth_Movement_Metal_Heavy_01_02.wav", "Movement/Whoosh_Dodge_Hard_Cloth_Movement_Metal_Heavy_01_03.wav",
    ),
    "dash_arcane": (
        "Movement/Whoosh_Dodge_Cloth_Movement_Fabric_Flap_Magical_Glowing_01_01.wav", "Movement/Whoosh_Dodge_Cloth_Movement_Fabric_Flap_Magical_Glowing_01_02.wav", "Movement/Whoosh_Dodge_Cloth_Movement_Fabric_Flap_Magical_Glowing_01_03.wav",
    ),
    "dash_occult": (
        "Movement/Whoosh_Dodge_Cloth_Movement_Heavy_Shimmer_Tail_01_01.wav", "Movement/Whoosh_Dodge_Cloth_Movement_Heavy_Shimmer_Tail_01_02.wav", "Movement/Whoosh_Dodge_Cloth_Movement_Heavy_Shimmer_Tail_01_03.wav",
    ),
    "shield_block": (
        "Combat/Melee_Shield_Metal_Movement_Impact_01_01.wav", "Combat/Melee_Shield_Metal_Movement_Impact_01_02.wav", "Combat/Melee_Shield_Metal_Movement_Impact_01_03.wav",
    ),
    "player_hurt_light": (
        "Impact/Impact_Combat_Thud_Hit_Deep_01_01.wav", "Impact/Impact_Combat_Thud_Hit_Deep_01_02.wav", "Impact/Impact_Combat_Thud_Hit_Deep_01_03.wav",
    ),
    "player_hurt_heavy": (
        "Impact/Impact_Combat_Hit_Blood_Spill_Splash_Bone_Crack_01_01.wav", "Impact/Impact_Combat_Hit_Blood_Spill_Splash_Bone_Crack_01_02.wav", "Impact/Impact_Combat_Hit_Blood_Spill_Splash_Bone_Crack_01_03.wav",
    ),
    "player_death": (
        "Impact/Impact_Combat_Gore_Crack_Blood_Spill_02_01.wav", "Impact/Impact_Combat_Gore_Crack_Blood_Spill_02_02.wav", "Impact/Impact_Combat_Gore_Crack_Blood_Spill_02_03.wav",
    ),
    "bow_release_light": (
        "Combat/Ranged_Bow_Release_Arrow_Launch_Crispy_Sharp_Short_01_01.wav", "Combat/Ranged_Bow_Release_Arrow_Launch_Crispy_Sharp_Short_01_02.wav", "Combat/Ranged_Bow_Release_Arrow_Launch_Crispy_Sharp_Short_01_03.wav",
    ),
    "bow_release_heavy": (
        "Combat/Ranged_Bow_Release_Arrow_Launch_Heavy_Shimmer_01_01.wav", "Combat/Ranged_Bow_Release_Arrow_Launch_Heavy_Shimmer_01_02.wav", "Combat/Ranged_Bow_Release_Arrow_Launch_Heavy_Shimmer_01_03.wav",
    ),
    "arrow_volley": (
        "Combat/Ranged_Arrow_Whiz_Multiple_Shots_Impact_01_01.wav", "Combat/Ranged_Arrow_Whiz_Multiple_Shots_Impact_01_02.wav", "Combat/Ranged_Arrow_Whiz_Multiple_Shots_Impact_01_03.wav",
    ),
    "physical_throw": (
        "Combat/Ranged_Weapon_Throw_Cloth_Movement_Whiz_Sharp_01_01.wav", "Combat/Ranged_Weapon_Throw_Cloth_Movement_Whiz_Sharp_01_02.wav", "Combat/Ranged_Weapon_Throw_Cloth_Movement_Whiz_Sharp_01_03.wav",
    ),
    "warden_guard_bolt": (
        "Combat/Ranged_Weapon_Throw_Cloth_Movement_Whiz_Sharp_01_01.wav", "Combat/Ranged_Weapon_Throw_Cloth_Movement_Whiz_Sharp_01_02.wav", "Combat/Ranged_Weapon_Throw_Cloth_Movement_Whiz_Sharp_01_03.wav",
    ),

    "arcane_cast": (
        "Combat/Ranged_Magic_Cast_Shimmer_Arcane_Flanger_01_01.wav", "Combat/Ranged_Magic_Cast_Shimmer_Arcane_Flanger_01_02.wav", "Combat/Ranged_Magic_Cast_Shimmer_Arcane_Flanger_01_03.wav",
    ),
    "fire_cast": (
        "Combat/Ranged_Magic_Fire_Sell_Cast_01_01.wav", "Combat/Ranged_Magic_Fire_Sell_Cast_01_02.wav", "Combat/Ranged_Magic_Fire_Sell_Cast_01_03.wav",
    ),
    "frost_cast": (
        "Combat/Ranged_Magic_Swing_Shimmer_Ring_01_01.wav", "Combat/Ranged_Magic_Swing_Shimmer_Ring_01_02.wav", "Combat/Ranged_Magic_Swing_Shimmer_Ring_01_03.wav",
    ),
    "shadow_cast": (
        "Combat/Ranged_Magic_Swing_Long_Tail_01_01.wav", "Combat/Ranged_Magic_Swing_Long_Tail_01_02_.wav", "Combat/Ranged_Magic_Swing_Long_Tail_01_03.wav",
    ),
    "warden_time_skip": (
        "Designed Skill/Designed_Skill_Magic_Shield_Rise_Reverse_Thud_Magic_Spell_End_01_01.wav", "Designed Skill/Designed_Skill_Magic_Shield_Rise_Reverse_Thud_Magic_Spell_End_01_02.wav", "Designed Skill/Designed_Skill_Magic_Shield_Rise_Reverse_Thud_Magic_Spell_End_01_03.wav",
    ),
    "rogue_bell_cast": ("UI/UI_Bell_Hit_01_01.wav",),
    "rogue_bell_detonate": ("UI/UI_Bell_Hit_Delay_01_01.wav",),
    "rogue_stealth": (
        "Designed Skill/Designed_Skill_Invisible_Stealth_Airy_Heavy_Deep_01_01.wav", "Designed Skill/Designed_Skill_Invisible_Stealth_Airy_Heavy_Deep_01_02.wav", "Designed Skill/Designed_Skill_Invisible_Stealth_Airy_Heavy_Deep_01_03.wav",
    ),
    "arcanist_nova": (
        "Designed Skill/Designed_Skill_Magic_Shield_Shimmer_Energy_Pulse_01_01.wav", "Designed Skill/Designed_Skill_Magic_Shield_Shimmer_Energy_Pulse_01_02_.wav", "Designed Skill/Designed_Skill_Magic_Shield_Shimmer_Energy_Pulse_01_03.wav",
    ),
    "acolyte_spirit_call": (
        "Designed Skill/Designed_Skill_Rise_And_Hit_Roar_Chime_Deep_Bright_Tone_Glide_Dreamy_01_01.wav", "Designed Skill/Designed_Skill_Rise_And_Hit_Roar_Chime_Deep_Bright_Tone_Glide_Dreamy_01_02.wav", "Designed Skill/Designed_Skill_Rise_And_Hit_Roar_Chime_Deep_Bright_Tone_Glide_Dreamy_01_03.wav",
    ),
    "ranger_beast_summon": (
        "Movement/Whoosh_Dodge_Heavy_Deep_Cloth_Movement_Hard_Slow_01_01.wav", "Movement/Whoosh_Dodge_Heavy_Deep_Cloth_Movement_Hard_Slow_01_02.wav", "Movement/Whoosh_Dodge_Heavy_Deep_Cloth_Movement_Hard_Slow_01_03.wav",
    ),
    "ranger_beast_command": ("UI/UI_Tap_Hard_Hit_Wooden_01_01.wav", "UI/UI_Tap_Hard_Hit_Wooden_01_02.wav"),
    "impact_generic": (
        "Impact/Impact_Combat_Hit_Crispy_Crack_Short_01_01.wav", "Impact/Impact_Combat_Hit_Crispy_Crack_Short_01_02.wav", "Impact/Impact_Combat_Hit_Crispy_Crack_Short_01_03.wav",
    ),
    "impact_flesh": (
        "Impact/Impact_Combat_Hit_Blood_Splash_Crack_Short_01_01.wav", "Impact/Impact_Combat_Hit_Blood_Splash_Crack_Short_01_02.wav", "Impact/Impact_Combat_Hit_Blood_Splash_Crack_Short_01_03.wav",
    ),
    "impact_armor": (
        "Impact/Impact_Combat_Hit_Cut_Metal_Scrap_Gore_Blood_Spill_01_01.wav", "Impact/Impact_Combat_Hit_Cut_Metal_Scrap_Gore_Blood_Spill_01_02.wav", "Impact/Impact_Combat_Hit_Cut_Metal_Scrap_Gore_Blood_Spill_01_03.wav",
    ),
    "impact_heavy": (
        "Impact/Impact_Combat_Thud_Hit_Deep_01_01.wav", "Impact/Impact_Combat_Thud_Hit_Deep_01_02.wav", "Impact/Impact_Combat_Thud_Hit_Deep_01_03.wav",
    ),
    "impact_lethal": (
        "Impact/Impact_Combat_Gore_Blood_Spill_Splash_01_01.wav", "Impact/Impact_Combat_Gore_Blood_Spill_Splash_01_02.wav", "Impact/Impact_Combat_Gore_Blood_Spill_Splash_01_03.wav",
    ),
    "impact_bone_lethal": (
        "Impact/Impact_Combat_Gore_Crack_Blood_Spill_01_01.wav", "Impact/Impact_Combat_Gore_Crack_Blood_Spill_01_02.wav", "Impact/Impact_Combat_Gore_Crack_Blood_Spill_01_03.wav",
    ),
    "coin_pickup_light": (
        "Foley/Foley_Coin_Drop_Impact_Light_01_01.wav", "Foley/Foley_Coin_Drop_Impact_Light_01_02.wav", "Foley/Foley_Coin_Drop_Impact_Light_01_03.wav",
    ),
    "coin_pickup_medium": (
        "Foley/Foley_Coin_Drop_Impact_Medium_01_01.wav", "Foley/Foley_Coin_Drop_Impact_Medium_01_02.wav", "Foley/Foley_Coin_Drop_Impact_Medium_01_03.wav",
    ),
    "item_pickup_common": (
        "UI/UI_Hit_Bright_Tone_Short_01_01.wav", "UI/UI_Hit_Bright_Tone_Short_01_02.wav", "UI/UI_Hit_Bright_Tone_Short_01_03.wav",
    ),
    "item_pickup_rare": ("UI/UI_Tap_Button_Chime_Bright_01_01.wav", "UI/UI_Tap_Button_Chime_Bright_01_02.wav"),
    "item_pickup_unique": (
        "Notification/Notification_Impact_Hit_Harp_Dark_Tune_01_01.wav", "Notification/Notification_Impact_Hit_Harp_Dark_Tune_01_02.wav",
    ),
    "item_pickup_cursed": (
        "Notification/Notification_Cinematic_Hit_Metal_Drops_Dark_Tune_Drum_Hollow_01_01.wav", "Notification/Notification_Cinematic_Hit_Metal_Drops_Dark_Tune_Drum_Hollow_01_02.wav", "Notification/Notification_Cinematic_Hit_Metal_Drops_Dark_Tune_Drum_Hollow_01_03.wav",
    ),
    "item_drop": (
        "Foley/Foley_Wooden_Pile_Impact_Debris_01_01.wav", "Foley/Foley_Wooden_Pile_Impact_Debris_01_02.wav", "Foley/Foley_Wooden_Pile_Impact_Debris_01_03.wav",
    ),
    "potion_drink": (
        "Foley/Foley_Potion_Glass_Bottle_Cork_Open_Drinking_01_01.wav", "Foley/Foley_Potion_Glass_Bottle_Cork_Open_Drinking_01_02.wav", "Foley/Foley_Potion_Glass_Bottle_Cork_Open_Drinking_01_03.wav",
    ),
    "bar_toast": (
        "Foley/Foley_Potion_Glass_Bottle_Liquid_Flow_Deep_Glass_Imapct_02_01.wav", "Foley/Foley_Potion_Glass_Bottle_Liquid_Flow_Deep_Glass_Imapct_02_02.wav", "Foley/Foley_Potion_Glass_Bottle_Liquid_Flow_Deep_Glass_Imapct_02_03.wav",
    ),
    "enemy_attack_light": (
        "Combat/Melee_Barehand_Combat_Swing_02_01.wav", "Combat/Melee_Barehand_Combat_Swing_02_02.wav", "Combat/Melee_Barehand_Combat_Swing_02_03.wav",
    ),
    "enemy_attack_brute": (
        "Combat/Melee_Weapon_Swing_Heavy_Deep_Slow_02_01.wav", "Combat/Melee_Weapon_Swing_Heavy_Deep_Slow_02_02.wav", "Combat/Melee_Weapon_Swing_Heavy_Deep_Slow_02_03.wav",
    ),
    "enemy_attack_armored": (
        "Combat/Melee_Weapon_Swing_Heavy_Thud_Metal_Friction_Dark_01_01.wav", "Combat/Melee_Weapon_Swing_Heavy_Thud_Metal_Friction_Dark_01_02.wav", "Combat/Melee_Weapon_Swing_Heavy_Thud_Metal_Friction_Dark_01_03.wav",
    ),
    "enemy_bow_release": (
        "Combat/Ranged_Bowstring_Launch_Snap_Thud_Short_01_01.wav", "Combat/Ranged_Bowstring_Launch_Snap_Thud_Short_01_02.wav", "Combat/Ranged_Bowstring_Launch_Snap_Thud_Short_01_03.wav",
    ),
    "enemy_arcane_cast": (
        "Combat/Ranged_Magic_Cast_Shimmer_Arcane_Flanger_01_01.wav", "Combat/Ranged_Magic_Cast_Shimmer_Arcane_Flanger_01_02.wav", "Combat/Ranged_Magic_Cast_Shimmer_Arcane_Flanger_01_03.wav",
    ),
    "enemy_poison_cast": (
        "Combat/Ranged_Magic_Swing_Bright_Vibe_Chirping_Shimmer_01_01.wav", "Combat/Ranged_Magic_Swing_Bright_Vibe_Chirping_Shimmer_01_02.wav", "Combat/Ranged_Magic_Swing_Bright_Vibe_Chirping_Shimmer_01_03.wav",
    ),
    "boss_engage": ("Notification/Notification_Cinematic_Hit_Cymbal_Rise_Deep_Hit_Scraps_Big_01_01.wav",),
    "boss_defeat": (
        "Notification/Notification_Whoosh_Thud_Deep_Impact_Upward_Bright_Tone_Chime_01_01.wav", "Notification/Notification_Whoosh_Thud_Deep_Impact_Upward_Bright_Tone_Chime_01_02.wav",
    ),
    "ash_gallows_cleave": (
        "Combat/Melee_Weapon_Swing_Heavy_Deep_Slow_Metal_Friction_Hard_01_01.wav", "Combat/Melee_Weapon_Swing_Heavy_Deep_Slow_Metal_Friction_Hard_01_02.wav",
    ),
    "ash_gallows_nova": (
        "Designed Skill/Designed_Skill_Explode_Shield_Hit_Hard_Flame_Fire_Burst_Loop_01_01.wav", "Designed Skill/Designed_Skill_Explode_Shield_Hit_Hard_Flame_Fire_Burst_Loop_01_02.wav", "Designed Skill/Designed_Skill_Explode_Shield_Hit_Hard_Flame_Fire_Burst_Loop_01_03.wav",
    ),
    "mycelial_spore_volley": (
        "Designed Skill/Designed_Skill_Magic_Arrowws_Whiz_Arroww_Launch_Multiple_Shots_Arcane_Projectile_01_01.wav", "Designed Skill/Designed_Skill_Magic_Arrowws_Whiz_Arroww_Launch_Multiple_Shots_Arcane_Projectile_01_02.wav", "Designed Skill/Designed_Skill_Magic_Arrowws_Whiz_Arroww_Launch_Multiple_Shots_Arcane_Projectile_01_03.wav",
    ),
    "rime_frost_fan": (
        "Combat/Ranged_Magic_Swing_Shimmer_Ring_Hard_01_01.wav", "Combat/Ranged_Magic_Swing_Shimmer_Ring_Hard_01_02.wav",
    ),
    "void_arcane_lance": (
        "Combat/Ranged_Magic_Fire_Projectile_Deep_Hard_01_01.wav", "Combat/Ranged_Magic_Fire_Projectile_Deep_Hard_01_02.wav",
    ),
    "gate_tyrant_strike": (
        "Combat/Melee_Weapon_Swing_Heavy_Thud_Metal_Friction_Dark_Hard_01_01.wav", "Combat/Melee_Weapon_Swing_Heavy_Thud_Metal_Friction_Dark_Hard_01_02.wav",
    ),
    "gate_tyrant_volley": (
        "Designed Skill/Designed_Skill_Magic_Arrowws_Whiz_Arroww_Launch_Multiple_Shots_Arcane_Projectile_01_01.wav", "Designed Skill/Designed_Skill_Magic_Arrowws_Whiz_Arroww_Launch_Multiple_Shots_Arcane_Projectile_01_02.wav", "Designed Skill/Designed_Skill_Magic_Arrowws_Whiz_Arroww_Launch_Multiple_Shots_Arcane_Projectile_01_03.wav",
    ),
    "door_open": (
        "Foley/Foley_Mechanical_Wooden_Lock_Hard_Open_01_01.wav", "Foley/Foley_Mechanical_Wooden_Lock_Hard_Open_01_02.wav", "Foley/Foley_Mechanical_Wooden_Lock_Hard_Open_01_03.wav",
    ),
    "lock_denied": (
        "Foley/Foley_Mechanical_Lock_Wooden_Metal_Impact_Hit_01_01.wav", "Foley/Foley_Mechanical_Lock_Wooden_Metal_Impact_Hit_01_02.wav", "Foley/Foley_Mechanical_Lock_Wooden_Metal_Impact_Hit_01_03.wav",
    ),
    "boss_gate_close": (
        "Foley/Foley_Stone_Gate_Drag_Friction_Impact_Heavy_Heavy_Long_01_01.wav", "Foley/Foley_Stone_Gate_Drag_Friction_Impact_Heavy_Heavy_Long_01_02.wav", "Foley/Foley_Stone_Gate_Drag_Friction_Impact_Heavy_Heavy_Long_01_03.wav",
    ),
    "boss_gate_open": (
        "Foley/Foley_Stone_Gate_Drag_Friction_Heavy_Short_01_01.wav", "Foley/Foley_Stone_Gate_Drag_Friction_Heavy_Short_01_02.wav", "Foley/Foley_Stone_Gate_Drag_Friction_Heavy_Short_01_03.wav",
    ),
    "stairs_descend": (
        "Foley/Foley_Stone_Gate_Drag_Friction_Light_Short_02_01.wav", "Foley/Foley_Stone_Gate_Drag_Friction_Light_Short_02_02.wav", "Foley/Foley_Stone_Gate_Drag_Friction_Light_Short_02_03.wav",
    ),
    "trap_spike": (
        "Foley/Foley_Trap_Metal_Spike_Sharp_Mechanical_Hit_Pierce_01_01.wav", "Foley/Foley_Trap_Metal_Spike_Sharp_Mechanical_Hit_Pierce_01_02.wav", "Foley/Foley_Trap_Metal_Spike_Sharp_Mechanical_Hit_Pierce_01_03.wav",
    ),
    "trap_rune": (
        "Designed Skill/Designed_Skill_Magic_Shield_Deep_Impact_Skill_Cast_01_01.wav", "Designed Skill/Designed_Skill_Magic_Shield_Deep_Impact_Skill_Cast_01_02.wav", "Designed Skill/Designed_Skill_Magic_Shield_Deep_Impact_Skill_Cast_01_03.wav",
    ),
    "trap_needle": (
        "Foley/Foley_Trap_Metal_Spike_Sharp_Hit_Pierce_01_01.wav", "Foley/Foley_Trap_Metal_Spike_Sharp_Hit_Pierce_01_02.wav", "Foley/Foley_Trap_Metal_Spike_Sharp_Hit_Pierce_01_03.wav",
    ),
    "shrine_mending": (
        "Designed Skill/Designed_Skill_Magic_Shield_Shimmer_Energy_Pulse_01_01.wav", "Designed Skill/Designed_Skill_Magic_Shield_Shimmer_Energy_Pulse_01_02_.wav", "Designed Skill/Designed_Skill_Magic_Shield_Shimmer_Energy_Pulse_01_03.wav",
    ),
    "shrine_insight": ("UI/UI_Bell_Sweep_Bright_Tone_Delay_01_01.wav", "UI/UI_Bell_Sweep_Bright_Tone_Delay_01_03.wav"),
    "shrine_war": (
        "Designed Skill/Designed_Skill_Rise_And_Hit_Roar_Chime_Deep_Bright_Tone_01_01.wav", "Designed Skill/Designed_Skill_Rise_And_Hit_Roar_Chime_Deep_Bright_Tone_01_02.wav", "Designed Skill/Designed_Skill_Rise_And_Hit_Roar_Chime_Deep_Bright_Tone_01_03.wav",
    ),
    "shrine_haste": (
        "Notification/Notification_Whoosh_Cinematic_Rise_Airy_Bell_Impact_01_01.wav", "Notification/Notification_Whoosh_Cinematic_Rise_Airy_Bell_Impact_01_02.wav", "Notification/Notification_Whoosh_Cinematic_Rise_Airy_Bell_Impact_01_03_.wav",
    ),
    "shrine_fortune": ("UI/UI_Tap_Button_Chime_Bright_01_01.wav", "UI/UI_Tap_Button_Chime_Bright_01_02.wav"),
    "shrine_oath": (
        "Designed Skill/Designed_Skill_Magic_Sword_Long_Rise_Metal_Scrap_Friction_01_01.wav", "Designed Skill/Designed_Skill_Magic_Sword_Long_Rise_Metal_Scrap_Friction_01_02.wav", "Designed Skill/Designed_Skill_Magic_Sword_Long_Rise_Metal_Scrap_Friction_01_03.wav",
    ),
    "shrine_twilight": (
        "Notification/Notification_Impact_Hit_Harp_Dark_Tune_01_01.wav", "Notification/Notification_Impact_Hit_Harp_Dark_Tune_01_02.wav",
    ),
    "secret_unlock": (
        "Foley/Foley_Mechanical_Unlock_Metal_Short_01_01.wav", "Foley/Foley_Mechanical_Unlock_Metal_Short_01_02.wav", "Foley/Foley_Mechanical_Unlock_Metal_Short_01_03.wav",
    ),
    "step_boot_hard": (
        "Steps/Steps_Boots_Hard_Ground_01_01.wav", "Steps/Steps_Boots_Hard_Ground_01_02.wav", "Steps/Steps_Boots_Hard_Ground_01_03.wav",
    ),
    "step_boot_hard_light": (
        "Steps/Steps_Boots_Hard_Ground_Light_01_01.wav", "Steps/Steps_Boots_Hard_Ground_Light_01_02.wav", "Steps/Steps_Boots_Hard_Ground_Light_01_03.wav",
    ),
    "step_boot_dirt": (
        "Steps/Steps_Boots_Medium_Dirt_01_01.wav", "Steps/Steps_Boots_Medium_Dirt_01_02.wav", "Steps/Steps_Boots_Medium_Dirt_01_03.wav",
    ),
    "step_boot_dirt_light": (
        "Steps/Steps_Boots_Light_Dirt_01_01.wav", "Steps/Steps_Boots_Light_Dirt_01_02.wav", "Steps/Steps_Boots_Light_Dirt_01_03.wav",
    ),
    "step_boot_grass": (
        "Steps/Steps_Boots_Grass_Dirt_Light_01_01.wav", "Steps/Steps_Boots_Grass_Dirt_Light_01_02.wav", "Steps/Steps_Boots_Grass_Dirt_Light_01_03.wav",
    ),
    "step_armor_light": (
        "Steps/Steps_Armored_Metal_Plate_Hard_Thud_Light_01_01.wav", "Steps/Steps_Armored_Metal_Plate_Hard_Thud_Light_01_02.wav", "Steps/Steps_Armored_Metal_Plate_Hard_Thud_Light_01_03.wav",
    ),
    "step_armor_medium": (
        "Steps/Steps_Armored_Metal_Plate_Hard_Thud_Medium_01_01.wav", "Steps/Steps_Armored_Metal_Plate_Hard_Thud_Medium_01_02.wav", "Steps/Steps_Armored_Metal_Plate_Hard_Thud_Medium_01_03.wav",
    ),
    "step_armor_heavy": (
        "Steps/Steps_Armored_Metal_Plate_Hard_Thud_Heavy_01_01.wav", "Steps/Steps_Armored_Metal_Plate_Hard_Thud_Heavy_01_02.wav", "Steps/Steps_Armored_Metal_Plate_Hard_Thud_Heavy_01_03.wav",
    ),
    "step_creature_heavy": (
        "Steps/Steps_Hollow_Heavy_Hard_Thud_01_01.wav", "Steps/Steps_Hollow_Heavy_Hard_Thud_01_02.wav", "Steps/Steps_Hollow_Heavy_Hard_Thud_01_03.wav",
    ),
}

# Starting points from SFX.md, with conservative additions for banks that did
# not have a numeric recommendation.
GAINS: dict[str, float] = {
    "ui_navigate": 0.38, "ui_confirm": 0.52, "ui_back": 0.48, "ui_reject": 0.55, "ui_equip": 0.50, "ui_purchase": 0.52,
    "run_start": 0.70, "level_up": 0.78, "victory": 0.82, "story_consequence": 0.70, "relic_recovered": 0.72, "epilogue_bell": 0.72,
    "melee_swing_warden": 0.72, "melee_swing_rogue": 0.66, "melee_swing_arcanist": 0.64, "melee_swing_acolyte": 0.66, "melee_swing_ranger": 0.66,
    "big_hit_charge": 0.64, "big_hit_release": 0.76, "dash_cloth_light": 0.58, "dash_armored": 0.64, "dash_arcane": 0.60, "dash_occult": 0.60,
    "shield_block": 0.76, "player_hurt_light": 0.42, "player_hurt_heavy": 0.40, "player_death": 0.48,
    "bow_release_light": 0.64, "bow_release_heavy": 0.70, "arrow_volley": 0.68, "physical_throw": 0.64,
    "warden_guard_bolt": 0.64, "arcane_cast": 0.68, "fire_cast": 0.68, "frost_cast": 0.68, "shadow_cast": 0.64,
    "warden_time_skip": 0.72, "rogue_bell_cast": 0.68, "rogue_bell_detonate": 0.72, "rogue_stealth": 0.64, "arcanist_nova": 0.72,
    "acolyte_spirit_call": 0.70, "ranger_beast_summon": 0.68, "ranger_beast_command": 0.44,
    "impact_generic": 0.39, "impact_flesh": 0.38, "impact_armor": 0.38, "impact_heavy": 0.40, "impact_lethal": 0.40, "impact_bone_lethal": 0.39,
    "coin_pickup_light": 0.62, "coin_pickup_medium": 0.66, "item_pickup_common": 0.52, "item_pickup_rare": 0.60,
    "item_pickup_unique": 0.72, "item_pickup_cursed": 0.66, "item_drop": 0.50, "potion_drink": 0.72, "bar_toast": 0.64,
    "enemy_attack_light": 0.58, "enemy_attack_brute": 0.68, "enemy_attack_armored": 0.66, "enemy_bow_release": 0.60,
    "enemy_arcane_cast": 0.58, "enemy_poison_cast": 0.58, "boss_engage": 0.78, "boss_defeat": 0.78,
    "ash_gallows_cleave": 0.74, "ash_gallows_nova": 0.76, "mycelial_spore_volley": 0.68, "rime_frost_fan": 0.70,
    "void_arcane_lance": 0.72, "gate_tyrant_strike": 0.76, "gate_tyrant_volley": 0.70,
    "door_open": 0.70, "lock_denied": 0.66, "boss_gate_close": 0.74, "boss_gate_open": 0.70, "stairs_descend": 0.66,
    "trap_spike": 0.76, "trap_rune": 0.72, "trap_needle": 0.68, "shrine_mending": 0.62, "shrine_insight": 0.68,
    "shrine_war": 0.72, "shrine_haste": 0.68, "shrine_fortune": 0.60, "shrine_oath": 0.68, "shrine_twilight": 0.66, "secret_unlock": 0.66,
    "step_boot_hard": 0.36, "step_boot_hard_light": 0.32, "step_boot_dirt": 0.36, "step_boot_dirt_light": 0.32, "step_boot_grass": 0.32,
    "step_armor_light": 0.36, "step_armor_medium": 0.39, "step_armor_heavy": 0.43, "step_creature_heavy": 0.50,
}

LEGACY_WAVS = {
    "bell.wav", "bolt.wav", "boss.wav", "death.wav", "door.wav", "drink.wav", "hit.wav", "hurt.wav", "levelup.wav",
    "pickup.wav", "potion.wav", "secret.wav", "shrine.wav", "stairs.wav", "start.wav", "swing.wav", "trap.wav",
    "ui_back.wav", "ui_confirm.wav", "ui_nav.wav", "victory.wav",
}
MUSICAL_BANKS = {
    "ui_purchase", "run_start", "level_up", "victory", "story_consequence", "relic_recovered", "epilogue_bell",
    "rogue_bell_cast", "rogue_bell_detonate", "boss_engage", "boss_defeat", "item_pickup_common", "item_pickup_rare",
    "item_pickup_unique", "item_pickup_cursed", "shrine_insight", "shrine_haste", "shrine_fortune", "shrine_twilight",
}
NON_SPATIAL_BANKS = {
    "ui_navigate", "ui_confirm", "ui_back", "ui_reject", "ui_equip", "ui_purchase", "run_start", "level_up", "victory",
    "story_consequence", "relic_recovered", "epilogue_bell", "player_hurt_light", "player_hurt_heavy", "player_death",
    "warden_time_skip", "rogue_bell_cast", "rogue_bell_detonate", "rogue_stealth", "arcanist_nova", "acolyte_spirit_call",
    "ranger_beast_summon", "ranger_beast_command", "coin_pickup_light", "coin_pickup_medium", "item_pickup_common",
    "item_pickup_rare", "item_pickup_unique", "item_pickup_cursed", "potion_drink", "bar_toast", "boss_engage", "boss_defeat",
}
CRITICAL_BANKS = {"ui_reject", "player_hurt_light", "player_hurt_heavy", "player_death", "lock_denied", "trap_spike", "trap_rune", "trap_needle"}
HIGH_BANKS = {
    "run_start", "level_up", "victory", "story_consequence", "relic_recovered", "epilogue_bell", "big_hit_charge", "big_hit_release",
    "shield_block", "warden_guard_bolt", "warden_time_skip", "rogue_bell_cast", "rogue_bell_detonate", "rogue_stealth", "arcanist_nova", "acolyte_spirit_call",
    "ranger_beast_summon", "boss_engage", "boss_defeat", "ash_gallows_cleave", "ash_gallows_nova", "mycelial_spore_volley",
    "rime_frost_fan", "void_arcane_lance", "gate_tyrant_strike", "gate_tyrant_volley", "boss_gate_close", "boss_gate_open",
}

@dataclass(frozen=True)
class WavInfo:
    duration_ms: int
    frame_count: int
    byte_size: int
    sha256: str


def expected_names() -> set[str]:
    return {f"{key}_{index:02d}.wav" for key, paths in BANK_SOURCES.items() for index in range(1, len(paths) + 1)}


def validate_definition() -> None:
    if set(BANK_SOURCES) != set(GAINS):
        missing_gains = sorted(set(BANK_SOURCES) - set(GAINS))
        extra_gains = sorted(set(GAINS) - set(BANK_SOURCES))
        raise ValueError(f"bank/gain mismatch: missing={missing_gains}, extra={extra_gains}")

    invalid = [key for key in BANK_SOURCES if not re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)*", key)]
    if invalid:
        raise ValueError(f"invalid bank keys: {invalid}")
    if any(not paths for paths in BANK_SOURCES.values()):
        raise ValueError("every bank must contain at least one source")


def validate_inputs(source: Path) -> None:
    if not source.is_dir():
        raise FileNotFoundError(f"source directory not found: {source}")
    missing = sorted({relative for paths in BANK_SOURCES.values() for relative in paths if not (source / relative).is_file()})
    if missing:
        raise FileNotFoundError("missing mapped source WAVs:\n  " + "\n  ".join(missing))


def validate_existing_output(output: Path) -> None:
    if not output.exists():
        return
    expected = expected_names()
    existing = {path.relative_to(output).as_posix() for path in output.rglob("*.wav")}
    unmanaged = sorted(existing - expected - LEGACY_WAVS)
    if unmanaged:
        raise RuntimeError("unmanaged WAVs in output directory:\n  " + "\n  ".join(unmanaged))


def source_duration_seconds(source: Path) -> float:
    try:
        with wave.open(os.fspath(source), "rb") as wav:
            return wav.getnframes() / wav.getframerate()
    except (EOFError, wave.Error) as error:
        raise RuntimeError(f"invalid source WAV {source}: {error}") from error


def convert(ffmpeg: str, bank: str, source: Path, destination: Path) -> None:
    command = [
        ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", os.fspath(source),
        "-map_metadata", "-1", "-vn", "-ac", str(CHANNELS), "-ar", str(SAMPLE_RATE),
    ]
    max_seconds = PLAYER_ACTION_SFX_MAX_SECONDS if bank in PLAYER_ACTION_BANKS else OTHER_SFX_MAX_SECONDS
    if source_duration_seconds(source) > max_seconds:
        fade_start = max_seconds - SFX_CAP_FADE_SECONDS
        command.extend([
            "-af", f"afade=t=out:st={fade_start:.3f}:d={SFX_CAP_FADE_SECONDS:.3f}",
            "-t", f"{max_seconds:.3f}",
        ])
    command.extend([
        "-c:a", "pcm_s16le", "-fflags", "+bitexact", "-flags:a", "+bitexact", os.fspath(destination),
    ])
    completed = subprocess.run(command, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "ffmpeg failed without an error message"
        raise RuntimeError(f"conversion failed for {source}: {detail}")


def inspect_wav(path: Path) -> WavInfo:
    try:
        with wave.open(os.fspath(path), "rb") as wav:
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            sample_rate = wav.getframerate()
            compression = wav.getcomptype()
            frame_count = wav.getnframes()
    except (EOFError, wave.Error) as error:
        raise RuntimeError(f"invalid WAV {path}: {error}") from error
    if channels != CHANNELS or sample_width * 8 != SAMPLE_SIZE_BITS or sample_rate != SAMPLE_RATE or compression != "NONE":
        raise RuntimeError(
            f"unexpected format for {path}: channels={channels}, bits={sample_width * 8}, "
            f"rate={sample_rate}, compression={compression}"
        )
    if frame_count <= 0:
        raise RuntimeError(f"empty WAV: {path}")
    data = path.read_bytes()
    return WavInfo(
        duration_ms=(frame_count * 1000 + SAMPLE_RATE // 2) // SAMPLE_RATE,
        frame_count=frame_count,
        byte_size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )


def bank_policy(key: str) -> dict[str, object]:
    if key in CRITICAL_BANKS:
        priority = "critical"
    elif key in HIGH_BANKS or key.startswith(("melee_", "bow_", "arcane_", "fire_", "frost_", "shadow_")):
        priority = "high"
    elif key.startswith("step_"):
        priority = "low"
    else:
        priority = "medium"

    if key == "ui_navigate":
        cooldown_ms = 50
    elif key.startswith("ui_"):
        cooldown_ms = 80
    elif key.startswith("step_"):
        cooldown_ms = 90
    elif key.startswith("impact_"):
        cooldown_ms = 25
    elif key.startswith("player_hurt_"):
        cooldown_ms = 120
    elif key.startswith("enemy_"):
        cooldown_ms = 45
    elif key.startswith("trap_"):
        cooldown_ms = 120
    else:
        cooldown_ms = 40

    if key.startswith("step_"):
        polyphony = 4
    elif key.startswith("impact_"):
        polyphony = 3
    elif key.startswith("enemy_"):
        polyphony = 3
    elif key in CRITICAL_BANKS or key.startswith("ui_"):
        polyphony = 1
    else:
        polyphony = 2

    pitch = [1.0, 1.0] if key in MUSICAL_BANKS else [0.97, 1.03]
    max_duration = PLAYER_ACTION_SFX_MAX_SECONDS if key in PLAYER_ACTION_BANKS else OTHER_SFX_MAX_SECONDS
    return {
        "cooldown_ms": cooldown_ms,
        "max_duration_ms": round(max_duration * 1000),
        "gain": GAINS[key],
        "pitch_range": pitch,
        "polyphony": polyphony,
        "priority": priority,
        "spatial": key not in NON_SPATIAL_BANKS,
    }


def build_manifest(infos: dict[str, list[tuple[str, WavInfo]]]) -> dict[str, object]:
    banks: dict[str, object] = {}
    total_bytes = 0
    total_duration_ms = 0
    for key in sorted(BANK_SOURCES):
        files = []
        for filename, info in infos[key]:
            total_bytes += info.byte_size
            total_duration_ms += info.duration_ms
            files.append({
                "byte_size": info.byte_size,
                "duration_ms": info.duration_ms,
                "file": filename,
                "frame_count": info.frame_count,
                "sha256": info.sha256,
            })
        banks[key] = {**bank_policy(key), "files": files}
    return {
        "audio_format": {
            "channels": CHANNELS,
            "codec": "pcm_s16le",
            "sample_rate": SAMPLE_RATE,
            "sample_size_bits": SAMPLE_SIZE_BITS,
        },
        "banks": banks,
        "file_count": sum(len(paths) for paths in BANK_SOURCES.values()),
        "format_version": 2,
        "total_duration_ms": total_duration_ms,
        "total_runtime_bytes": total_bytes,
    }


def promote(temp_output: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for path in output.rglob("*.wav"):
        path.unlink()
    for path in sorted(temp_output.glob("*.wav")):
        os.replace(path, output / path.name)
    os.replace(temp_output / "manifest.json", output / "manifest.json")
    remaining = sorted(path.relative_to(output).as_posix() for path in output.rglob("*.wav") if path.name not in expected_names())
    if remaining:
        raise RuntimeError("unmanaged WAVs remained after promotion: " + ", ".join(remaining))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="publisher pack root")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="flat runtime SFX directory")
    parser.add_argument("--ffmpeg", default="ffmpeg", help="ffmpeg executable")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    validate_definition()
    validate_inputs(source)
    validate_existing_output(output)
    if shutil.which(args.ffmpeg) is None:
        raise FileNotFoundError(f"ffmpeg executable not found: {args.ffmpeg}")

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".action-rpg-sfx-", dir=output.parent) as temporary:
        temp_output = Path(temporary)
        infos: dict[str, list[tuple[str, WavInfo]]] = {}
        for key in sorted(BANK_SOURCES):
            bank_infos = []
            for index, relative in enumerate(BANK_SOURCES[key], start=1):
                filename = f"{key}_{index:02d}.wav"
                destination = temp_output / filename
                convert(args.ffmpeg, key, source / relative, destination)
                bank_infos.append((filename, inspect_wav(destination)))
            infos[key] = bank_infos

        generated = {path.name for path in temp_output.glob("*.wav")}
        if generated != expected_names():
            missing = sorted(expected_names() - generated)
            extra = sorted(generated - expected_names())
            raise RuntimeError(f"generated WAV mismatch: missing={missing}, extra={extra}")

        manifest = build_manifest(infos)
        (temp_output / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        promote(temp_output, output)

    print(
        f"Imported {manifest['file_count']} WAV files across {len(BANK_SOURCES)} banks; "
        f"total runtime bytes: {manifest['total_runtime_bytes']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
