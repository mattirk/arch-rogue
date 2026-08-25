package archrogue

// Authored sound-effect playback and the live background-music mixer.
// Missing or invalid files degrade to silence; gameplay never depends on audio.

import "core:fmt"
import "core:math"
import "core:sync"
import rl "../vendor/raylib"

SFX_MAX_VARIANTS :: 3
SFX_VOICE_CAP_DESKTOP :: 24
SFX_VOICE_CAP_CONSTRAINED :: 16
SFX_FOOTSTEP_TRACKERS :: 256
SFX_PLAYER_STEP_INTERVAL_SECONDS :: f32(0.98)
SFX_ENEMY_STEP_INTERVAL_SECONDS  :: f32(0.84)
SFX_MASTER_OUTPUT_GAIN           :: f32(0.50)

Sfx_Bank_Def :: struct {
	key:          string,
	variant_count: u8,
	gain:         f32,
	pitch_min:    f32,
	pitch_max:    f32,
	cooldown_s:   f32,
	priority:     u8,
	polyphony:    u8,
	spatial:      bool,
	max_distance: f32,
}

// Metadata mirrors manifest v2; filenames are always <key>_NN.wav. Spatial
// banks use a conservative ten-tile falloff with limited stereo separation.
@(rodata)
SFX_BANK_DEFS := [Sfx_Bank]Sfx_Bank_Def{
	.Ui_Navigate={key="ui_navigate",variant_count=3,gain=0.38,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.05,priority=6,polyphony=1,spatial=false,max_distance=0},
	.Ui_Confirm={key="ui_confirm",variant_count=3,gain=0.52,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.08,priority=6,polyphony=1,spatial=false,max_distance=0},
	.Ui_Back={key="ui_back",variant_count=3,gain=0.48,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.08,priority=6,polyphony=1,spatial=false,max_distance=0},
	.Ui_Reject={key="ui_reject",variant_count=1,gain=0.55,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.08,priority=15,polyphony=1,spatial=false,max_distance=0},
	.Ui_Equip={key="ui_equip",variant_count=2,gain=0.5,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.08,priority=6,polyphony=1,spatial=false,max_distance=0},
	.Ui_Purchase={key="ui_purchase",variant_count=3,gain=0.52,pitch_min=1.0,pitch_max=1.0,cooldown_s=0.08,priority=6,polyphony=1,spatial=false,max_distance=0},
	.Run_Start={key="run_start",variant_count=2,gain=0.7,pitch_min=1.0,pitch_max=1.0,cooldown_s=0.04,priority=10,polyphony=2,spatial=false,max_distance=0},
	.Level_Up={key="level_up",variant_count=2,gain=0.78,pitch_min=1.0,pitch_max=1.0,cooldown_s=0.04,priority=10,polyphony=2,spatial=false,max_distance=0},
	.Victory={key="victory",variant_count=3,gain=0.82,pitch_min=1.0,pitch_max=1.0,cooldown_s=0.04,priority=10,polyphony=2,spatial=false,max_distance=0},
	.Story_Consequence={key="story_consequence",variant_count=3,gain=0.7,pitch_min=1.0,pitch_max=1.0,cooldown_s=0.04,priority=10,polyphony=2,spatial=false,max_distance=0},
	.Relic_Recovered={key="relic_recovered",variant_count=2,gain=0.72,pitch_min=1.0,pitch_max=1.0,cooldown_s=0.04,priority=10,polyphony=2,spatial=false,max_distance=0},
	.Epilogue_Bell={key="epilogue_bell",variant_count=1,gain=0.72,pitch_min=1.0,pitch_max=1.0,cooldown_s=0.04,priority=10,polyphony=2,spatial=false,max_distance=0},
	.Melee_Swing_Warden={key="melee_swing_warden",variant_count=3,gain=0.72,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=10,polyphony=2,spatial=true,max_distance=10},
	.Melee_Swing_Rogue={key="melee_swing_rogue",variant_count=3,gain=0.66,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=10,polyphony=2,spatial=true,max_distance=10},
	.Melee_Swing_Arcanist={key="melee_swing_arcanist",variant_count=3,gain=0.64,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=10,polyphony=2,spatial=true,max_distance=10},
	.Melee_Swing_Acolyte={key="melee_swing_acolyte",variant_count=3,gain=0.66,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=10,polyphony=2,spatial=true,max_distance=10},
	.Melee_Swing_Ranger={key="melee_swing_ranger",variant_count=3,gain=0.66,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=10,polyphony=2,spatial=true,max_distance=10},
	.Big_Hit_Charge={key="big_hit_charge",variant_count=3,gain=0.64,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=10,polyphony=2,spatial=true,max_distance=10},
	.Big_Hit_Release={key="big_hit_release",variant_count=2,gain=0.76,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=10,polyphony=2,spatial=true,max_distance=10},
	.Dash_Cloth_Light={key="dash_cloth_light",variant_count=3,gain=0.58,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=6,polyphony=2,spatial=true,max_distance=10},
	.Dash_Armored={key="dash_armored",variant_count=3,gain=0.64,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=6,polyphony=2,spatial=true,max_distance=10},
	.Dash_Arcane={key="dash_arcane",variant_count=3,gain=0.6,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=6,polyphony=2,spatial=true,max_distance=10},
	.Dash_Occult={key="dash_occult",variant_count=3,gain=0.6,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=6,polyphony=2,spatial=true,max_distance=10},
	.Shield_Block={key="shield_block",variant_count=3,gain=0.76,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=10,polyphony=2,spatial=true,max_distance=10},
	.Player_Hurt_Light={key="player_hurt_light",variant_count=3,gain=0.42,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.12,priority=15,polyphony=1,spatial=false,max_distance=0},
	.Player_Hurt_Heavy={key="player_hurt_heavy",variant_count=3,gain=0.40,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.12,priority=15,polyphony=1,spatial=false,max_distance=0},
	.Player_Death={key="player_death",variant_count=3,gain=0.48,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=15,polyphony=1,spatial=false,max_distance=0},
	.Bow_Release_Light={key="bow_release_light",variant_count=3,gain=0.64,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=10,polyphony=2,spatial=true,max_distance=10},
	.Bow_Release_Heavy={key="bow_release_heavy",variant_count=3,gain=0.7,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=10,polyphony=2,spatial=true,max_distance=10},
	.Arrow_Volley={key="arrow_volley",variant_count=3,gain=0.68,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=6,polyphony=2,spatial=true,max_distance=10},
	.Physical_Throw={key="physical_throw",variant_count=3,gain=0.64,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=6,polyphony=2,spatial=true,max_distance=10},
	.Warden_Guard_Bolt={key="warden_guard_bolt",variant_count=3,gain=0.64,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=10,polyphony=2,spatial=true,max_distance=10},
	.Arcane_Cast={key="arcane_cast",variant_count=3,gain=0.68,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=10,polyphony=2,spatial=true,max_distance=10},
	.Fire_Cast={key="fire_cast",variant_count=3,gain=0.68,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=10,polyphony=2,spatial=true,max_distance=10},
	.Frost_Cast={key="frost_cast",variant_count=3,gain=0.68,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=10,polyphony=2,spatial=true,max_distance=10},
	.Shadow_Cast={key="shadow_cast",variant_count=3,gain=0.64,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=10,polyphony=2,spatial=true,max_distance=10},
	.Warden_Time_Skip={key="warden_time_skip",variant_count=3,gain=0.72,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=10,polyphony=2,spatial=false,max_distance=0},
	.Rogue_Bell_Cast={key="rogue_bell_cast",variant_count=1,gain=0.68,pitch_min=1.0,pitch_max=1.0,cooldown_s=0.04,priority=10,polyphony=2,spatial=false,max_distance=0},
	.Rogue_Bell_Detonate={key="rogue_bell_detonate",variant_count=1,gain=0.72,pitch_min=1.0,pitch_max=1.0,cooldown_s=0.04,priority=10,polyphony=2,spatial=false,max_distance=0},
	.Rogue_Stealth={key="rogue_stealth",variant_count=3,gain=0.64,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=10,polyphony=2,spatial=false,max_distance=0},
	.Arcanist_Nova={key="arcanist_nova",variant_count=3,gain=0.72,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=10,polyphony=2,spatial=false,max_distance=0},
	.Acolyte_Spirit_Call={key="acolyte_spirit_call",variant_count=3,gain=0.7,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=10,polyphony=2,spatial=false,max_distance=0},
	.Ranger_Beast_Summon={key="ranger_beast_summon",variant_count=3,gain=0.68,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=10,polyphony=2,spatial=false,max_distance=0},
	.Ranger_Beast_Command={key="ranger_beast_command",variant_count=2,gain=0.44,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=6,polyphony=2,spatial=false,max_distance=0},
	.Impact_Generic={key="impact_generic",variant_count=3,gain=0.39,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.025,priority=6,polyphony=3,spatial=true,max_distance=10},
	.Impact_Flesh={key="impact_flesh",variant_count=3,gain=0.38,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.025,priority=6,polyphony=3,spatial=true,max_distance=10},
	.Impact_Armor={key="impact_armor",variant_count=3,gain=0.38,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.025,priority=6,polyphony=3,spatial=true,max_distance=10},
	.Impact_Heavy={key="impact_heavy",variant_count=3,gain=0.40,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.025,priority=6,polyphony=3,spatial=true,max_distance=10},
	.Impact_Lethal={key="impact_lethal",variant_count=3,gain=0.40,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.025,priority=6,polyphony=3,spatial=true,max_distance=10},
	.Impact_Bone_Lethal={key="impact_bone_lethal",variant_count=3,gain=0.39,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.025,priority=6,polyphony=3,spatial=true,max_distance=10},
	.Coin_Pickup_Light={key="coin_pickup_light",variant_count=3,gain=0.62,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=6,polyphony=2,spatial=false,max_distance=0},
	.Coin_Pickup_Medium={key="coin_pickup_medium",variant_count=3,gain=0.66,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=6,polyphony=2,spatial=false,max_distance=0},
	.Item_Pickup_Common={key="item_pickup_common",variant_count=3,gain=0.52,pitch_min=1.0,pitch_max=1.0,cooldown_s=0.04,priority=6,polyphony=2,spatial=false,max_distance=0},
	.Item_Pickup_Rare={key="item_pickup_rare",variant_count=2,gain=0.6,pitch_min=1.0,pitch_max=1.0,cooldown_s=0.04,priority=6,polyphony=2,spatial=false,max_distance=0},
	.Item_Pickup_Unique={key="item_pickup_unique",variant_count=2,gain=0.72,pitch_min=1.0,pitch_max=1.0,cooldown_s=0.04,priority=6,polyphony=2,spatial=false,max_distance=0},
	.Item_Pickup_Cursed={key="item_pickup_cursed",variant_count=3,gain=0.66,pitch_min=1.0,pitch_max=1.0,cooldown_s=0.04,priority=6,polyphony=2,spatial=false,max_distance=0},
	.Item_Drop={key="item_drop",variant_count=3,gain=0.5,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=6,polyphony=2,spatial=true,max_distance=10},
	.Potion_Drink={key="potion_drink",variant_count=3,gain=0.72,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=6,polyphony=2,spatial=false,max_distance=0},
	.Bar_Toast={key="bar_toast",variant_count=3,gain=0.64,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=6,polyphony=2,spatial=false,max_distance=0},
	.Soulless_Clanker={key="soulless_clanker",variant_count=3,gain=0.7,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=6,polyphony=2,spatial=true,max_distance=10},
	.Enemy_Attack_Light={key="enemy_attack_light",variant_count=3,gain=0.58,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.045,priority=6,polyphony=3,spatial=true,max_distance=10},
	.Enemy_Attack_Brute={key="enemy_attack_brute",variant_count=3,gain=0.68,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.045,priority=6,polyphony=3,spatial=true,max_distance=10},
	.Enemy_Attack_Armored={key="enemy_attack_armored",variant_count=3,gain=0.66,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.045,priority=6,polyphony=3,spatial=true,max_distance=10},
	.Enemy_Bow_Release={key="enemy_bow_release",variant_count=3,gain=0.6,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.045,priority=6,polyphony=3,spatial=true,max_distance=10},
	.Enemy_Arcane_Cast={key="enemy_arcane_cast",variant_count=3,gain=0.58,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.045,priority=6,polyphony=3,spatial=true,max_distance=10},
	.Enemy_Poison_Cast={key="enemy_poison_cast",variant_count=3,gain=0.58,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.045,priority=6,polyphony=3,spatial=true,max_distance=10},
	.Boss_Engage={key="boss_engage",variant_count=1,gain=0.78,pitch_min=1.0,pitch_max=1.0,cooldown_s=0.04,priority=10,polyphony=2,spatial=false,max_distance=0},
	.Boss_Defeat={key="boss_defeat",variant_count=2,gain=0.78,pitch_min=1.0,pitch_max=1.0,cooldown_s=0.04,priority=10,polyphony=2,spatial=false,max_distance=0},
	.Ash_Gallows_Cleave={key="ash_gallows_cleave",variant_count=2,gain=0.74,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=10,polyphony=2,spatial=true,max_distance=10},
	.Ash_Gallows_Nova={key="ash_gallows_nova",variant_count=3,gain=0.76,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=10,polyphony=2,spatial=true,max_distance=10},
	.Mycelial_Spore_Volley={key="mycelial_spore_volley",variant_count=3,gain=0.68,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=10,polyphony=2,spatial=true,max_distance=10},
	.Rime_Frost_Fan={key="rime_frost_fan",variant_count=2,gain=0.7,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=10,polyphony=2,spatial=true,max_distance=10},
	.Void_Arcane_Lance={key="void_arcane_lance",variant_count=2,gain=0.72,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=10,polyphony=2,spatial=true,max_distance=10},
	.Gate_Tyrant_Strike={key="gate_tyrant_strike",variant_count=2,gain=0.76,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=10,polyphony=2,spatial=true,max_distance=10},
	.Gate_Tyrant_Volley={key="gate_tyrant_volley",variant_count=3,gain=0.7,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=10,polyphony=2,spatial=true,max_distance=10},
	.Door_Open={key="door_open",variant_count=3,gain=0.7,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=6,polyphony=2,spatial=true,max_distance=10},
	.Lock_Denied={key="lock_denied",variant_count=3,gain=0.66,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=15,polyphony=1,spatial=true,max_distance=10},
	.Boss_Gate_Close={key="boss_gate_close",variant_count=3,gain=0.74,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=10,polyphony=2,spatial=true,max_distance=10},
	.Boss_Gate_Open={key="boss_gate_open",variant_count=3,gain=0.7,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=10,polyphony=2,spatial=true,max_distance=10},
	.Stairs_Descend={key="stairs_descend",variant_count=3,gain=0.66,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=6,polyphony=2,spatial=true,max_distance=10},
	.Trap_Spike={key="trap_spike",variant_count=3,gain=0.76,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.12,priority=15,polyphony=1,spatial=true,max_distance=10},
	.Trap_Rune={key="trap_rune",variant_count=3,gain=0.72,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.12,priority=15,polyphony=1,spatial=true,max_distance=10},
	.Trap_Needle={key="trap_needle",variant_count=3,gain=0.68,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.12,priority=15,polyphony=1,spatial=true,max_distance=10},
	.Shrine_Mending={key="shrine_mending",variant_count=3,gain=0.62,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=6,polyphony=2,spatial=true,max_distance=10},
	.Shrine_Insight={key="shrine_insight",variant_count=2,gain=0.68,pitch_min=1.0,pitch_max=1.0,cooldown_s=0.04,priority=6,polyphony=2,spatial=true,max_distance=10},
	.Shrine_War={key="shrine_war",variant_count=3,gain=0.72,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=6,polyphony=2,spatial=true,max_distance=10},
	.Shrine_Haste={key="shrine_haste",variant_count=3,gain=0.68,pitch_min=1.0,pitch_max=1.0,cooldown_s=0.04,priority=6,polyphony=2,spatial=true,max_distance=10},
	.Shrine_Fortune={key="shrine_fortune",variant_count=2,gain=0.6,pitch_min=1.0,pitch_max=1.0,cooldown_s=0.04,priority=6,polyphony=2,spatial=true,max_distance=10},
	.Shrine_Oath={key="shrine_oath",variant_count=3,gain=0.68,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=6,polyphony=2,spatial=true,max_distance=10},
	.Shrine_Twilight={key="shrine_twilight",variant_count=2,gain=0.66,pitch_min=1.0,pitch_max=1.0,cooldown_s=0.04,priority=6,polyphony=2,spatial=true,max_distance=10},
	.Secret_Unlock={key="secret_unlock",variant_count=3,gain=0.66,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.04,priority=6,polyphony=2,spatial=true,max_distance=10},
	.Step_Boot_Hard={key="step_boot_hard",variant_count=3,gain=0.36,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.09,priority=2,polyphony=4,spatial=true,max_distance=10},
	.Step_Boot_Hard_Light={key="step_boot_hard_light",variant_count=3,gain=0.32,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.09,priority=2,polyphony=4,spatial=true,max_distance=10},
	.Step_Boot_Dirt={key="step_boot_dirt",variant_count=3,gain=0.36,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.09,priority=2,polyphony=4,spatial=true,max_distance=10},
	.Step_Boot_Dirt_Light={key="step_boot_dirt_light",variant_count=3,gain=0.32,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.09,priority=2,polyphony=4,spatial=true,max_distance=10},
	.Step_Boot_Grass={key="step_boot_grass",variant_count=3,gain=0.12,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.09,priority=2,polyphony=4,spatial=true,max_distance=10},
	.Step_Armor_Light={key="step_armor_light",variant_count=3,gain=0.36,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.09,priority=2,polyphony=4,spatial=true,max_distance=10},
	.Step_Armor_Medium={key="step_armor_medium",variant_count=3,gain=0.39,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.09,priority=2,polyphony=4,spatial=true,max_distance=10},
	.Step_Armor_Heavy={key="step_armor_heavy",variant_count=3,gain=0.43,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.09,priority=2,polyphony=4,spatial=true,max_distance=10},
	.Step_Creature_Heavy={key="step_creature_heavy",variant_count=3,gain=0.5,pitch_min=0.97,pitch_max=1.03,cooldown_s=0.09,priority=2,polyphony=4,spatial=true,max_distance=10},
}

MUSIC_MAX_ASSETS  :: 16
MUSIC_SAMPLE_RATE :: 48_000
MUSIC_CHANNELS    :: 2
MUSIC_SAMPLE_SIZE :: 16

// The music master bus uses an intentionally audible, allocation-free tape
// stage before a stereo-linked zero-lookahead peak limiter. The authored stems
// are quiet enough that subtle drive stayed nearly linear, so this stage uses
// strong pre-drive, asymmetric soft saturation for even/odd harmonics, and a
// one-pole high-frequency rolloff. A DC blocker removes the bias produced by
// the asymmetric transfer. The limiter's instantaneous attack catches the
// current sample and returns to unity over roughly 100 ms without adding delay.
MUSIC_SATURATION_DRIVE          :: f32(3.00)
MUSIC_SATURATION_MIX            :: f32(0.50)
MUSIC_TAPE_BIAS                 :: f32(0.08)
MUSIC_TAPE_OUTPUT_GAIN          :: f32(0.55)
MUSIC_TAPE_TONE_ALPHA           :: f32(0.65)
MUSIC_TAPE_DC_BLOCK_COEFFICIENT :: f32(0.9987)
MUSIC_LIMITER_CEILING           :: f32(0.8912509)
MUSIC_LIMITER_RELEASE_PER_FRAME :: f32(0.00020831)

Music_Master_DSP :: struct {
	tape_tone_left:      f32,
	tape_tone_right:     f32,
	tape_dc_input_left:  f32,
	tape_dc_input_right: f32,
	tape_dc_output_left: f32,
	tape_dc_output_right: f32,
	limiter_gain:        f32,
}

// Each authored OGG is decoded once into its own immutable PCM layer. The
// callback mixes these layers live, so the director retains independent gain
// control without asking several Vorbis decoders to refill under raylib's
// global audio mutex.
Music_PCM_Asset :: struct {
	file:  string, // borrowed from the music library
	wave:  rl.Wave,
	ready: bool,
}

Sfx_Loaded_Bank :: struct {
	sounds:       [SFX_MAX_VARIANTS]rl.Sound,
	loaded:       [SFX_MAX_VARIANTS]bool,
	loaded_count: u8,
	next_variant:    u8,
	last_play_s:     f64,
	last_emitter_id: u64,
}

Sfx_Active_Voice :: struct {
	active:      bool,
	bank:        Sfx_Bank, // resolved loaded bank
	source_bank: Sfx_Bank, // semantic bank that requested this voice
	variant:     u8,
	priority:    u8,
	serial:      u64,
}

Sfx_Footstep_Tracker :: struct {
	valid:      bool,
	emitter_id: u64,
	phase:      i64,
}

Audio :: struct {
	sfx_banks:  [Sfx_Bank]Sfx_Loaded_Bank,
	voices:     [SFX_VOICE_CAP_DESKTOP]Sfx_Active_Voice,
	voice_serial: u64,
	footsteps:  [SFX_FOOTSTEP_TRACKERS]Sfx_Footstep_Tracker,
	player_step_phase: i64,
	player_step_valid: bool,
	ready:       bool,
	enabled:     bool,
	sfx_gain:    f32,
	suspended:   bool,
	initialized: bool,

	music_library:          Music_Library,
	music_assets:           [MUSIC_MAX_ASSETS]Music_PCM_Asset,
	music_asset_count:      int,
	music_loop_frames:      u32,
	music_stream:           rl.AudioStream,
	music_stream_loaded:    bool,
	music_stream_started:   bool,
	music_stream_paused:    bool,
	music_stage:            Music_Stage,
	music_stage_valid:      bool,
	music_target_gain_bits:       [MUSIC_MAX_ASSETS]u32, // atomically published f32 values
	music_published_gains:        [MUSIC_MAX_ASSETS]f32, // render-thread write cache
	music_published_valid:        [MUSIC_MAX_ASSETS]bool,
	music_callback_gains:         [MUSIC_MAX_ASSETS]f32, // audio callback owns while playing
	music_master_target_bits:     u32,                   // atomically published post-DSP user gain
	music_master_published_gain:  f32,                   // render-thread write cache
	music_master_published_valid: bool,
	music_callback_master_gain:   f32,                   // audio callback owns while playing
	music_master_dsp:             Music_Master_DSP,      // audio callback owns while playing
	music_cursor_frame:           u32,                   // atomic next frame to render
	music_reference_frame:  u32,                   // atomic start of audible device block
	music_callback_count:   u32,                   // atomic health telemetry
	music_active_layers:    int,
	music_recovery_count:   int,
	music_recovery_logged:  bool,
}

// raylib's AudioCallback has no user-data pointer. Only one Audio instance owns
// the process audio device; this pointer is installed before playback and
// cleared after UnloadAudioStream has synchronized with the callback.
@(private = "file")
audio_music_callback_audio: ^Audio

audio_loaded_cue_count :: proc(audio: ^Audio) -> (count: int) {
	if audio == nil do return
	for bank in Sfx_Bank do count += int(audio.sfx_banks[bank].loaded_count)
	return
}

// Resource readiness is independent of the user's enabled preference.
audio_ready_for_playback :: proc(audio: ^Audio) -> bool {
	return audio != nil && audio.ready && !audio.suspended && audio_loaded_cue_count(audio) > 0
}

// Pure semantic routing shared by the raw platform bridge and headless tests.
// A frame emits at most one menu bank, with Back taking reducer priority.
audio_cue_for_intent :: proc(intent: Intent) -> (Sfx_Bank, bool) {
	if intent.back do return .Ui_Back, true
	if intent.confirm do return .Ui_Confirm, true
	if intent.menu_delta != 0 || intent.menu_horizontal != 0 || intent.tab {
		return .Ui_Navigate, true
	}
	return {}, false
}

// Starting a run owns Run_Start, so Select -> Playing suppresses Ui_Confirm.
audio_cue_for_transition :: proc(intent: Intent, mode_before, mode_after: App_Mode) -> (Sfx_Bank, bool) {
	bank, has_bank := audio_cue_for_intent(intent)
	if has_bank && bank == .Ui_Confirm && mode_before == .Select && mode_after == .Playing {
		return {}, false
	}
	return bank, has_bank
}

@(private = "file")
audio_sfx_gain :: proc(def: Sfx_Bank_Def) -> f32 { return def.gain > 0 ? def.gain : .78 }
@(private = "file")
audio_sfx_pitch_min :: proc(def: Sfx_Bank_Def) -> f32 { return def.pitch_min > 0 ? def.pitch_min : .96 }
@(private = "file")
audio_sfx_pitch_max :: proc(def: Sfx_Bank_Def) -> f32 { return def.pitch_max > 0 ? def.pitch_max : 1.04 }
@(private = "file")
audio_sfx_cooldown :: proc(def: Sfx_Bank_Def) -> f64 { return def.cooldown_s > 0 ? f64(def.cooldown_s) : .018 }
@(private = "file")
audio_sfx_priority :: proc(def: Sfx_Bank_Def) -> u8 { return def.priority > 0 ? def.priority : 6 }
@(private = "file")
audio_sfx_polyphony :: proc(def: Sfx_Bank_Def) -> int { return def.polyphony > 0 ? int(def.polyphony) : min(3, int(def.variant_count)) }
@(private = "file")
audio_sfx_distance :: proc(def: Sfx_Bank_Def) -> f32 { return def.max_distance > 0 ? def.max_distance : 10 }

@(private = "file")
audio_sfx_voice_cap :: proc() -> int {
	when ARCH_ROGUE_WEB || ARCH_ROGUE_ANDROID do return SFX_VOICE_CAP_CONSTRAINED
	return SFX_VOICE_CAP_DESKTOP
}

@(private = "file")
audio_sfx_hash :: proc(value: u64) -> u64 {
	hash := (value ~ (value >> 30)) * 0xbf58476d1ce4e5b9
	hash = (hash ~ (hash >> 27)) * 0x94d049bb133111eb
	return hash ~ (hash >> 31)
}

// The web preload keeps exactly these banks. Every lazy bank maps directly to
// one of them, so fallback resolution is bounded to one step.
audio_sfx_bank_is_core :: proc(bank: Sfx_Bank) -> bool {
	#partial switch bank {
	case .Ui_Navigate, .Ui_Confirm, .Ui_Back, .Ui_Reject, .Ui_Equip, .Ui_Purchase,
	     .Run_Start, .Level_Up, .Victory, .Story_Consequence, .Relic_Recovered, .Epilogue_Bell,
	     .Player_Hurt_Light, .Player_Hurt_Heavy, .Player_Death,
	     .Melee_Swing_Arcanist, .Dash_Cloth_Light, .Warden_Guard_Bolt,
	     .Arcane_Cast, .Shadow_Cast, .Impact_Generic,
	     .Item_Pickup_Common, .Potion_Drink, .Enemy_Attack_Light, .Boss_Engage,
	     .Door_Open, .Trap_Spike, .Shrine_Mending, .Step_Boot_Grass:
		return true
	}
	return false
}

audio_sfx_fallback_bank :: proc(bank: Sfx_Bank) -> Sfx_Bank {
	#partial switch bank {
	case .Melee_Swing_Warden, .Melee_Swing_Rogue, .Melee_Swing_Acolyte, .Melee_Swing_Ranger:
		return .Melee_Swing_Arcanist
	case .Dash_Armored, .Dash_Arcane, .Dash_Occult:
		return .Dash_Cloth_Light
	case .Fire_Cast, .Frost_Cast, .Warden_Time_Skip, .Rogue_Bell_Cast,
	     .Rogue_Bell_Detonate, .Rogue_Stealth, .Arcanist_Nova, .Acolyte_Spirit_Call,
	     .Ranger_Beast_Summon, .Ranger_Beast_Command, .Enemy_Arcane_Cast, .Enemy_Poison_Cast:
		return .Arcane_Cast
	case .Big_Hit_Charge, .Big_Hit_Release, .Shield_Block, .Bow_Release_Light,
	     .Bow_Release_Heavy, .Arrow_Volley, .Physical_Throw, .Impact_Flesh,
	     .Impact_Armor, .Impact_Heavy, .Impact_Lethal, .Impact_Bone_Lethal:
		return .Impact_Generic
	case .Coin_Pickup_Light, .Coin_Pickup_Medium, .Item_Pickup_Rare,
	     .Item_Pickup_Unique, .Item_Pickup_Cursed, .Item_Drop:
		return .Item_Pickup_Common
	case .Bar_Toast:
		return .Potion_Drink
	case .Soulless_Clanker:
		return .Impact_Generic
	case .Enemy_Attack_Brute, .Enemy_Attack_Armored, .Enemy_Bow_Release:
		return .Enemy_Attack_Light
	case .Boss_Defeat, .Ash_Gallows_Cleave, .Ash_Gallows_Nova, .Mycelial_Spore_Volley,
	     .Rime_Frost_Fan, .Void_Arcane_Lance, .Gate_Tyrant_Strike, .Gate_Tyrant_Volley:
		return .Boss_Engage
	case .Lock_Denied, .Boss_Gate_Close, .Boss_Gate_Open, .Stairs_Descend, .Secret_Unlock:
		return .Door_Open
	case .Trap_Rune, .Trap_Needle:
		return .Trap_Spike
	case .Shrine_Insight, .Shrine_War, .Shrine_Haste, .Shrine_Fortune, .Shrine_Oath, .Shrine_Twilight:
		return .Shrine_Mending
	case .Step_Boot_Hard, .Step_Boot_Hard_Light, .Step_Boot_Dirt, .Step_Boot_Dirt_Light,
	     .Step_Armor_Light, .Step_Armor_Medium, .Step_Armor_Heavy, .Step_Creature_Heavy:
		return .Step_Boot_Grass
	}
	return bank
}

@(private = "file")
audio_sfx_load_bank :: proc(audio: ^Audio, bank: Sfx_Bank, log_missing: bool = true) {
	if audio == nil || !audio.ready do return
	def := SFX_BANK_DEFS[bank]
	loaded := &audio.sfx_banks[bank]
	for variant in 0 ..< min(int(def.variant_count), SFX_MAX_VARIANTS) {
		if loaded.loaded[variant] do continue
		path := fmt.ctprintf("assets/audio/sfx/%s_%02d.wav", def.key, variant + 1)
		// Android assets are loaded through raylib's AAssetManager callback.
		when !ARCH_ROGUE_ANDROID {
			if !rl.FileExists(path) {
				if log_missing do platform_log(fmt.tprintf("audio: missing SFX %s (%s)", def.key, path))
				continue
			}
		}
		sound := rl.LoadSound(path)
		if !rl.IsSoundValid(sound) {
			platform_log(fmt.tprintf("audio: invalid SFX %s (%s)", def.key, path))
			continue
		}
		loaded.sounds[variant] = sound
		loaded.loaded[variant] = true
		loaded.loaded_count += 1
	}
}

// Called only after the pack bridge has materialized every WAV into MEMFS.
// Returning false while the device is locked leaves the adoption item queued.
audio_web_adopt_sfx_bank :: proc(audio: ^Audio, key: string) -> bool {
	when !ARCH_ROGUE_WEB do return true
	if audio == nil || !audio.ready do return false
	for bank in Sfx_Bank {
		if SFX_BANK_DEFS[bank].key != key do continue
		audio_sfx_load_bank(audio, bank, log_missing = true)
		return true
	}
	platform_log(fmt.tprintf("audio: unknown web SFX bank %s", key))
	return true
}

audio_init :: proc(audio: ^Audio) {
	if audio == nil do return
	// A repeated device init must not leak buffers or reset the saved SFX option.
	enabled := audio.enabled
	sfx_gain := audio.sfx_gain
	suspended := audio.suspended
	if !audio.initialized {
		enabled = true
		sfx_gain = SFX_MASTER_OUTPUT_GAIN
	}
	if audio.ready do audio_shutdown(audio)

	// Web decodes music during game boot, before the user gesture. Preserve that
	// device-independent PCM while resetting the device-backed audio state so the
	// unlock frame can create Web Audio immediately, while transient activation
	// is still valid.
	when ARCH_ROGUE_WEB {
		preloaded_library := audio.music_library
		preloaded_assets := audio.music_assets
		preloaded_asset_count := audio.music_asset_count
		preloaded_loop_frames := audio.music_loop_frames
		audio^ = Audio{
			enabled = enabled,
			sfx_gain = sfx_gain,
			suspended = suspended,
			initialized = true,
		}
		audio.music_library = preloaded_library
		audio.music_assets = preloaded_assets
		audio.music_asset_count = preloaded_asset_count
		audio.music_loop_frames = preloaded_loop_frames
	} else {
		audio^ = Audio{
			enabled = enabled,
			sfx_gain = sfx_gain,
			suspended = suspended,
			initialized = true,
		}
	}

	// A NativeActivity can enter main more than once while Android retains the
	// process. Reuse the process-owned backend left by a prior activity instead
	// of attempting to initialize a second device.
	if !rl.IsAudioDeviceReady() do rl.InitAudioDevice()
	if !rl.IsAudioDeviceReady() {
		platform_log(fmt.tprint("audio: no device, running silent"))
		return
	}
	audio.ready = true

	for bank in Sfx_Bank {
		audio.sfx_banks[bank].last_play_s = -1000
		when ARCH_ROGUE_WEB {
			audio_sfx_load_bank(audio, bank, log_missing = false)
		} else {
			audio_sfx_load_bank(audio, bank)
		}
	}
	when ARCH_ROGUE_WEB {
		audio_music_create_mixer(audio)
	} else {
		audio_music_load_library(audio)
	}
}

// SFX uses its own master gain at dispatch; music remains on the independent
// post-DSP master path. The boolean wrapper remains for headless/platform callers.
audio_set_volume :: proc(audio: ^Audio, level: f32) {
	if audio == nil do return
	// The user-facing 0-100% range is relative to the deliberately restrained
	// SFX bus. At 100%, authored bank gains reach half their former output.
	audio.sfx_gain = clamp(level, f32(0), f32(1)) * SFX_MASTER_OUTPUT_GAIN
	audio.enabled = audio.sfx_gain > 0
}

audio_set_enabled :: proc(audio: ^Audio, enabled: bool) {
	audio_set_volume(audio, enabled ? 1 : 0)
}

// Lazy web asset adoption waits for a quiet authored-SFX window. The query is
// intentionally independent of the enabled preference.
audio_any_cue_playing :: proc(audio: ^Audio) -> bool {
	if audio == nil || !audio.ready do return false
	for bank in Sfx_Bank {
		loaded := &audio.sfx_banks[bank]
		for variant in 0 ..< SFX_MAX_VARIANTS {
			if loaded.loaded[variant] && rl.IsSoundValid(loaded.sounds[variant]) && rl.IsSoundPlaying(loaded.sounds[variant]) do return true
		}
	}
	return false
}

@(private = "file")
audio_sfx_stop_all :: proc(audio: ^Audio) {
	if audio == nil || !audio.ready do return
	for bank in Sfx_Bank {
		loaded := &audio.sfx_banks[bank]
		for variant in 0 ..< SFX_MAX_VARIANTS {
			if !loaded.loaded[variant] do continue
			sound := loaded.sounds[variant]
			if rl.IsSoundValid(sound) && rl.IsSoundPlaying(sound) do rl.StopSound(sound)
		}
	}
	audio.voices = {}
}

audio_suspend :: proc(audio: ^Audio) {
	if audio == nil || audio.suspended do return
	audio.suspended = true
	if !audio.ready do return
	audio_sfx_stop_all(audio)
	audio_music_suspend(audio)
}

audio_resume :: proc(audio: ^Audio) {
	if audio == nil do return
	audio.suspended = false
}

audio_shutdown :: proc(audio: ^Audio) {
	if audio == nil do return
	audio_music_shutdown(audio)
	if audio.ready {
		audio_sfx_stop_all(audio)
		for bank in Sfx_Bank {
			loaded := &audio.sfx_banks[bank]
			for variant in 0 ..< SFX_MAX_VARIANTS {
				if loaded.loaded[variant] && rl.IsSoundValid(loaded.sounds[variant]) do rl.UnloadSound(loaded.sounds[variant])
			}
		}
		// Android keeps the process-owned backend across NativeActivity relaunch.
		when !ARCH_ROGUE_ANDROID do rl.CloseAudioDevice()
	}
	audio.sfx_banks = {}
	audio.voices = {}
	audio.ready = false
}

@(private = "file")
audio_sfx_refresh_voices :: proc(audio: ^Audio) {
	for &voice in audio.voices[:audio_sfx_voice_cap()] {
		if !voice.active do continue
		loaded := &audio.sfx_banks[voice.bank]
		variant := int(voice.variant)
		if variant >= SFX_MAX_VARIANTS || !loaded.loaded[variant] || !rl.IsSoundPlaying(loaded.sounds[variant]) do voice = {}
	}
}

@(private = "file")
audio_sfx_stop_voice :: proc(audio: ^Audio, index: int) {
	voice := &audio.voices[index]
	if !voice.active do return
	loaded := &audio.sfx_banks[voice.bank]
	variant := int(voice.variant)
	if variant < SFX_MAX_VARIANTS && loaded.loaded[variant] && rl.IsSoundValid(loaded.sounds[variant]) do rl.StopSound(loaded.sounds[variant])
	voice^ = {}
}

// Stop only voices started for this semantic bank. Keeping source_bank distinct
// from the resolved web fallback prevents canceling unrelated fallback sounds.
audio_stop_bank :: proc(audio: ^Audio, bank: Sfx_Bank) {
	if audio == nil || !audio.ready do return
	audio_sfx_refresh_voices(audio)
	for &voice, index in audio.voices[:audio_sfx_voice_cap()] {
		if voice.active && voice.source_bank == bank do audio_sfx_stop_voice(audio, index)
	}
}

@(private = "file")
audio_sfx_claim_voice :: proc(audio: ^Audio, bank: Sfx_Bank, priority: u8, polyphony: int) -> (int, bool) {
	cap := audio_sfx_voice_cap()
	free_index := -1
	bank_count := 0
	oldest_bank_index := -1
	oldest_bank_serial := max(u64)
	steal_index := -1
	steal_priority := max(u8)
	steal_serial := max(u64)
	for &voice, index in audio.voices[:cap] {
		if !voice.active {
			if free_index < 0 do free_index = index
			continue
		}
		if voice.bank == bank {
			bank_count += 1
			if voice.serial < oldest_bank_serial { oldest_bank_serial = voice.serial; oldest_bank_index = index }
		}
		if voice.priority <= priority && (voice.priority < steal_priority || (voice.priority == steal_priority && voice.serial < steal_serial)) {
			steal_priority = voice.priority
			steal_serial = voice.serial
			steal_index = index
		}
	}
	if bank_count >= polyphony && oldest_bank_index >= 0 {
		audio_sfx_stop_voice(audio, oldest_bank_index)
		return oldest_bank_index, true
	}
	if free_index >= 0 do return free_index, true
	if steal_index >= 0 {
		audio_sfx_stop_voice(audio, steal_index)
		return steal_index, true
	}
	return -1, false
}

audio_play_bank :: proc(
	audio: ^Audio,
	bank: Sfx_Bank,
	pos: Vec2 = {},
	spatial: bool = false,
	emitter_id: u64 = 0,
	listener_pos: Vec2 = {},
) {
	if audio == nil || !audio.ready || !audio.enabled || audio.suspended do return
	resolved_bank := bank
	if audio.sfx_banks[resolved_bank].loaded_count == 0 {
		resolved_bank = audio_sfx_fallback_bank(resolved_bank)
	}
	def := SFX_BANK_DEFS[resolved_bank]
	loaded := &audio.sfx_banks[resolved_bank]
	if loaded.loaded_count == 0 do return
	now := rl.GetTime()
	// Cooldown suppresses one emitter chattering, not distinct same-bank events
	// in a crowd; audio_drain deliberately performs no frame-kind dedup.
	if emitter_id == loaded.last_emitter_id && now - loaded.last_play_s < audio_sfx_cooldown(def) do return

	gain := audio_sfx_gain(def) * audio.sfx_gain
	pan := f32(0)
	use_spatial := spatial || def.spatial
	if use_spatial {
		delta := pos - listener_pos
		distance := f32(math.sqrt(f64(delta.x * delta.x + delta.y * delta.y)))
		max_distance := audio_sfx_distance(def)
		if distance >= max_distance do return
		gain *= clamp(1 - distance / max_distance, f32(.14), f32(1))
		pan = clamp((delta.x - delta.y) / max_distance * .35, f32(-.35), f32(.35))
	}

	audio_sfx_refresh_voices(audio)
	priority := audio_sfx_priority(def)
	voice_index, claimed := audio_sfx_claim_voice(audio, resolved_bank, priority, audio_sfx_polyphony(def))
	if !claimed do return

	variant := int(loaded.next_variant) % max(1, int(def.variant_count))
	for offset in 0 ..< int(def.variant_count) {
		candidate := (variant + offset) % int(def.variant_count)
		if loaded.loaded[candidate] { variant = candidate; break }
	}
	// A raylib Sound handle is one playback voice. Retire its previous serial if
	// round robin reaches it before IsSoundPlaying reports completion.
	for &voice, index in audio.voices[:audio_sfx_voice_cap()] {
		if index != voice_index && voice.active && voice.bank == resolved_bank && int(voice.variant) == variant do audio_sfx_stop_voice(audio, index)
	}

	audio.voice_serial += 1
	if audio.voice_serial == 0 do audio.voice_serial = 1
	hash := audio_sfx_hash(emitter_id ~ u64(resolved_bank) << 40 ~ audio.voice_serial)
	unit := f32(hash & 0xffff) / f32(0xffff)
	pitch_min, pitch_max := audio_sfx_pitch_min(def), audio_sfx_pitch_max(def)
	sound := loaded.sounds[variant]
	rl.SetSoundVolume(sound, gain)
	rl.SetSoundPitch(sound, pitch_min + (pitch_max - pitch_min) * unit)
	rl.SetSoundPan(sound, pan)
	rl.PlaySound(sound)
	loaded.next_variant = u8((variant + 1) % int(def.variant_count))
	loaded.last_play_s = now
	loaded.last_emitter_id = emitter_id
	audio.voices[voice_index] = {active=true,bank=resolved_bank,source_bank=bank,variant=u8(variant),priority=priority,serial=audio.voice_serial}
}

// Compatibility name retained for platform callers while its type is semantic.
audio_play_cue :: proc(audio: ^Audio, bank: Sfx_Bank) { audio_play_bank(audio, bank) }

// --- live background-music mixing -------------------------------------------
// The raylib-free Music_Director owns phase and per-track envelopes. This layer
// decodes each authored OGG once, then mixes the independent PCM stems from one
// audio callback. Playback therefore performs no file I/O or codec work and is
// not serviced by the render loop.

@(private = "file")
audio_music_store_u32 :: proc "contextless" (destination: ^u32, value: u32) {
	when ARCH_ROGUE_WEB {
		// Keep one implementation surface while avoiding Wasm atomics: the web
		// audio callback and game frame execute on the same browser thread.
		_ = sync.Atomic_Memory_Order.Relaxed
		destination^ = value
	} else {
		sync.atomic_store_explicit(destination, value, .Release)
	}
}

@(private = "file")
audio_music_load_u32 :: proc "contextless" (source: ^u32) -> u32 {
	when ARCH_ROGUE_WEB {
		return source^
	} else {
		return sync.atomic_load_explicit(source, .Acquire)
	}
}

@(private = "file")
audio_music_add_u32 :: proc "contextless" (destination: ^u32, value: u32) {
	when ARCH_ROGUE_WEB {
		destination^ += value
	} else {
		sync.atomic_add_explicit(destination, value, .Relaxed)
	}
}

@(private = "file")
audio_music_store_gain :: proc "contextless" (destination: ^u32, value: f32) {
	audio_music_store_u32(destination, transmute(u32)value)
}

@(private = "file")
audio_music_load_gain :: proc "contextless" (source: ^u32) -> f32 {
	return transmute(f32)audio_music_load_u32(source)
}

audio_music_master_dsp_reset :: proc "contextless" (dsp: ^Music_Master_DSP) {
	if dsp == nil do return
	dsp^ = {limiter_gain = 1}
}

// Biased softsign saturation remains monotonic at any input level. Subtracting
// the zero-input response keeps exact silence at zero while retaining the
// asymmetry that gives the parallel tape stage an audible even harmonic.
audio_music_saturate_sample :: proc "contextless" (sample: f32) -> f32 {
	driven := sample * MUSIC_SATURATION_DRIVE + MUSIC_TAPE_BIAS
	shaped := driven / (1 + abs(driven))
	bias_floor := MUSIC_TAPE_BIAS / (1 + abs(MUSIC_TAPE_BIAS))
	wet := (shaped - bias_floor) * MUSIC_TAPE_OUTPUT_GAIN
	return sample + (wet - sample) * MUSIC_SATURATION_MIX
}

// A cheap stateful tone stage precedes the waveshaper, approximating tape's
// high-frequency softening. The post-shaper DC blocker protects bass headroom
// from the deliberate transfer asymmetry without introducing lookahead.
audio_music_tape_frame :: proc "contextless" (
	dsp: ^Music_Master_DSP,
	left, right: f32,
) -> (tape_left, tape_right: f32) {
	if dsp == nil do return
	dsp.tape_tone_left += (left - dsp.tape_tone_left) * MUSIC_TAPE_TONE_ALPHA
	dsp.tape_tone_right += (right - dsp.tape_tone_right) * MUSIC_TAPE_TONE_ALPHA
	shaped_left := audio_music_saturate_sample(dsp.tape_tone_left)
	shaped_right := audio_music_saturate_sample(dsp.tape_tone_right)
	tape_left = shaped_left - dsp.tape_dc_input_left + MUSIC_TAPE_DC_BLOCK_COEFFICIENT * dsp.tape_dc_output_left
	tape_right = shaped_right - dsp.tape_dc_input_right + MUSIC_TAPE_DC_BLOCK_COEFFICIENT * dsp.tape_dc_output_right
	dsp.tape_dc_input_left = shaped_left
	dsp.tape_dc_input_right = shaped_right
	dsp.tape_dc_output_left = tape_left
	dsp.tape_dc_output_right = tape_right
	return
}

// One detector and one envelope preserve the stereo image. Attack is
// instantaneous because there is intentionally no lookahead; saturation ahead
// of the limiter softens the transient edge that this zero-latency choice can
// otherwise expose.
audio_music_limit_frame :: proc "contextless" (
	dsp: ^Music_Master_DSP,
	left, right: f32,
) -> (limited_left, limited_right: f32) {
	if dsp == nil do return
	gain := dsp.limiter_gain
	if gain <= 0 || gain > 1 do gain = 1
	gain += (1 - gain) * MUSIC_LIMITER_RELEASE_PER_FRAME
	peak := max(abs(left), abs(right))
	if peak > MUSIC_LIMITER_CEILING {
		gain = min(gain, MUSIC_LIMITER_CEILING / peak)
	}
	dsp.limiter_gain = gain
	limited_left = clamp(left * gain, -MUSIC_LIMITER_CEILING, MUSIC_LIMITER_CEILING)
	limited_right = clamp(right * gain, -MUSIC_LIMITER_CEILING, MUSIC_LIMITER_CEILING)
	return
}

@(private = "file")
audio_music_asset_index_for :: proc(audio: ^Audio, file: string) -> (int, bool) {
	if audio == nil do return 0, false
	for index in 0 ..< audio.music_asset_count {
		if audio.music_assets[index].file == file do return index, true
	}
	return 0, false
}

// Runs under raylib's audio-device mutex. It must never allocate, log, decode,
// call back into raylib, or read mutable game state. Per-layer gains and the
// common Loop cursor are the only cross-thread values and are atomic on native
// targets (the web audio callback and game frame share one browser thread).
@(private = "file")
audio_music_mix_callback :: proc "c" (buffer_data: rawptr, frames: u32) #no_bounds_check {
	output := cast([^]f32)buffer_data
	frame_count := int(frames)
	sample_count := frame_count * MUSIC_CHANNELS
	for sample_index in 0 ..< sample_count do output[sample_index] = 0

	audio := audio_music_callback_audio
	if audio == nil || audio.music_loop_frames == 0 || frame_count <= 0 do return
	cursor := int(audio_music_load_u32(&audio.music_cursor_frame))
	loop_frames := int(audio.music_loop_frames)
	// Report the start of the device block, not its already-rendered end. This
	// keeps hard musical boundaries from firing one callback period early.
	audio_music_store_u32(&audio.music_reference_frame, u32(cursor))
	// Snapshot all atomic controls before mixing. A frame may publish new gains
	// concurrently, but one callback block always uses one tightly sampled set.
	target_gains: [MUSIC_MAX_ASSETS]f32
	for asset_index in 0 ..< audio.music_asset_count {
		target_gains[asset_index] = audio_music_load_gain(&audio.music_target_gain_bits[asset_index])
	}

	master_target := clamp(audio_music_load_gain(&audio.music_master_target_bits), 0, 1)
	master_gain := audio.music_callback_master_gain
	master_step := (master_target - master_gain) / f32(frame_count)

	for asset_index in 0 ..< audio.music_asset_count {
		asset := &audio.music_assets[asset_index]
		if !asset.ready || asset.wave.data == nil do continue
		target_gain := target_gains[asset_index]
		gain := audio.music_callback_gains[asset_index]
		if target_gain == 0 && gain == 0 do continue
		gain_step := (target_gain - gain) / f32(frame_count)
		source := cast([^]i16)asset.wave.data
		source_cursor := cursor
		for frame_index in 0 ..< frame_count {
			gain += gain_step
			source_index := source_cursor * MUSIC_CHANNELS
			output_index := frame_index * MUSIC_CHANNELS
			output[output_index] += f32(source[source_index]) * (gain / 32768.0)
			output[output_index + 1] += f32(source[source_index + 1]) * (gain / 32768.0)
			source_cursor += 1
			if source_cursor >= loop_frames do source_cursor = 0
		}
		audio.music_callback_gains[asset_index] = target_gain
	}

	// Process the summed music bus before applying the user's volume preference,
	// so changing that option does not change saturation or limiter behavior.
	for frame_index in 0 ..< frame_count {
		output_index := frame_index * MUSIC_CHANNELS
		left, right := audio_music_tape_frame(
			&audio.music_master_dsp,
			output[output_index],
			output[output_index + 1],
		)
		left, right = audio_music_limit_frame(&audio.music_master_dsp, left, right)
		master_gain += master_step
		output[output_index] = left * master_gain
		output[output_index + 1] = right * master_gain
	}
	audio.music_callback_master_gain = master_target
	cursor = (cursor + frame_count) % loop_frames
	audio_music_store_u32(&audio.music_cursor_frame, u32(cursor))
	audio_music_add_u32(&audio.music_callback_count, 1)
}

@(private = "file")
audio_music_stop_mixer :: proc(audio: ^Audio) {
	if audio == nil do return
	if audio.music_stream_loaded && rl.IsAudioStreamValid(audio.music_stream) {
		if audio.music_stream_started do rl.StopAudioStream(audio.music_stream)
		rl.UnloadAudioStream(audio.music_stream)
	}
	// UnloadAudioStream synchronizes with raylib's callback before returning, so
	// decoded layers can be released safely after this pointer is cleared.
	if audio_music_callback_audio == audio do audio_music_callback_audio = nil
	audio.music_stream = {}
	audio.music_stream_loaded = false
	audio.music_stream_started = false
	audio.music_stream_paused = false
	audio.music_stage_valid = false
	audio.music_active_layers = 0
	audio.music_target_gain_bits = {}
	audio.music_published_gains = {}
	audio.music_published_valid = {}
	audio.music_callback_gains = {}
	audio.music_master_target_bits = 0
	audio.music_master_published_gain = 0
	audio.music_master_published_valid = false
	audio.music_callback_master_gain = 0
	audio.music_master_dsp = {}
	audio.music_cursor_frame = 0
	audio.music_reference_frame = 0
	audio.music_callback_count = 0
}

@(private = "file")
audio_music_unload_assets :: proc(audio: ^Audio) {
	if audio == nil do return
	for index in 0 ..< audio.music_asset_count {
		asset := &audio.music_assets[index]
		if asset.wave.data != nil do rl.UnloadWave(asset.wave)
	}
	audio.music_assets = {}
	audio.music_asset_count = 0
	audio.music_loop_frames = 0
}

@(private = "file")
audio_music_preload_assets :: proc(audio: ^Audio) {
	if audio == nil do return
	expected_frames := u32(audio.music_library.loop_ms * f64(MUSIC_SAMPLE_RATE) / 1000 + 0.5)
	audio.music_loop_frames = expected_frames
	loaded_count := 0
	decoded_bytes := 0
	for mix in audio.music_library.mixes {
		for track in mix.tracks {
			if _, found := audio_music_asset_index_for(audio, track.file); found do continue
			if audio.music_asset_count >= MUSIC_MAX_ASSETS {
				platform_log(fmt.tprintf("music: PCM layer cache full, dropping %s", track.file))
				continue
			}
			asset := &audio.music_assets[audio.music_asset_count]
			audio.music_asset_count += 1
			asset.file = track.file
			path := fmt.ctprintf("assets/audio/bgm/%s", track.file)
			data_size: i32
			data := rl.LoadFileData(path, &data_size)
			if data == nil || data_size <= 0 {
				if data != nil do rl.UnloadFileData(data)
				platform_log(fmt.tprintf("music: missing track %s", track.file))
				continue
			}
			wave := rl.LoadWaveFromMemory(".ogg", data, data_size)
			rl.UnloadFileData(data)
			if !rl.IsWaveValid(wave) {
				platform_log(fmt.tprintf("music: invalid track %s", track.file))
				continue
			}
			if wave.sampleRate != MUSIC_SAMPLE_RATE || wave.sampleSize != MUSIC_SAMPLE_SIZE || wave.channels != MUSIC_CHANNELS {
				rl.WaveFormat(&wave, MUSIC_SAMPLE_RATE, MUSIC_SAMPLE_SIZE, MUSIC_CHANNELS)
			}
			if !rl.IsWaveValid(wave) || wave.sampleRate != MUSIC_SAMPLE_RATE || wave.sampleSize != MUSIC_SAMPLE_SIZE || wave.channels != MUSIC_CHANNELS {
				platform_log(fmt.tprintf("music: could not convert %s to 48 kHz stereo PCM16", track.file))
				if wave.data != nil do rl.UnloadWave(wave)
				continue
			}
			if wave.frameCount != expected_frames {
				platform_log(fmt.tprintf(
					"music: %s length %d frames, expected %d for %.0f ms; dropping track",
					track.file, wave.frameCount, expected_frames, audio.music_library.loop_ms,
				))
				rl.UnloadWave(wave)
				continue
			}
			asset.wave = wave
			asset.ready = true
			loaded_count += 1
			decoded_bytes += int(wave.frameCount * wave.channels * (wave.sampleSize / 8))
		}
	}
	platform_log(fmt.tprintf(
		"music: decoded %d/%d live stems (%d KiB PCM)",
		loaded_count, audio.music_asset_count, decoded_bytes / 1024,
	))
}

@(private = "file")
audio_music_create_mixer :: proc(audio: ^Audio) {
	if audio == nil || audio.music_loop_frames == 0 do return
	has_layer := false
	for index in 0 ..< audio.music_asset_count do has_layer = has_layer || audio.music_assets[index].ready
	if !has_layer do return
	stream := rl.LoadAudioStream(MUSIC_SAMPLE_RATE, 32, MUSIC_CHANNELS)
	if !rl.IsAudioStreamValid(stream) {
		platform_log(fmt.tprint("music: could not create live mixer stream"))
		return
	}
	audio.music_stream = stream
	audio.music_stream_loaded = true
	audio_music_master_dsp_reset(&audio.music_master_dsp)
	audio_music_callback_audio = audio
	rl.SetAudioStreamCallback(stream, audio_music_mix_callback)
}

// Load the composer document and decode every referenced OGG through raylib's
// asset-aware file reader. This works with Android's AAssetManager and the web
// preload filesystem without relying on POSIX paths. Decoding is deliberately
// separate from creating the device-backed mixer so web can finish this
// main-thread work before starting its main-thread audio callback.
@(private = "file")
audio_music_preload_library :: proc(audio: ^Audio) {
	if audio == nil do return
	audio_music_stop_mixer(audio)
	audio_music_unload_assets(audio)
	music_library_destroy(&audio.music_library)
	data_size: i32
	raw := rl.LoadFileData(MUSIC_MIXES_DOCUMENT_PATH, &data_size)
	if raw == nil || data_size <= 0 {
		if raw != nil do rl.UnloadFileData(raw)
		platform_log(fmt.tprintf("music: missing %s, staying silent", MUSIC_MIXES_DOCUMENT_PATH))
		return
	}
	defer rl.UnloadFileData(raw)
	library, ok := music_library_parse(raw[:data_size])
	if !ok {
		platform_log(fmt.tprintf("music: malformed %s, staying silent", MUSIC_MIXES_DOCUMENT_PATH))
		return
	}
	audio.music_library = library
	audio_music_preload_assets(audio)
	platform_log(fmt.tprintf(
		"music: library loaded (%d mixes, loop %.0f ms)",
		len(library.mixes), library.loop_ms,
	))
}

// Web calls this during ordinary game boot, before Web Audio is gesture-unlocked,
// so expensive OGG decoding cannot starve the first live callback.
audio_preload_music :: proc(audio: ^Audio) {
	audio_music_preload_library(audio)
}

@(private = "file")
audio_music_load_library :: proc(audio: ^Audio) {
	audio_music_preload_library(audio)
	audio_music_create_mixer(audio)
}

@(private = "file")
audio_music_publish_targets :: proc(
	audio: ^Audio,
	director: ^Music_Director,
	runtime: Music_Runtime_State,
) {
	gains: [MUSIC_MAX_ASSETS]f32
	for &state in director.slots {
		if !state.active do continue
		if asset_index, found := audio_music_asset_index_for(audio, state.file); found && audio.music_assets[asset_index].ready {
			runtime_gain := music_track_runtime_gain(state.authored, runtime)
			gains[asset_index] = clamp(state.volume * runtime_gain, 0, 1)
		}
		// Every PCM layer advances on the common callback cursor even while
		// inaudible, so an entering layer is already at state.seek_ms.
		state.start_pending = false
	}
	audio.music_active_layers = 0
	for asset_index in 0 ..< audio.music_asset_count {
		gain := gains[asset_index]
		if !audio.music_published_valid[asset_index] || abs(audio.music_published_gains[asset_index] - gain) > 0.0001 {
			audio_music_store_gain(&audio.music_target_gain_bits[asset_index], gain)
			audio.music_published_gains[asset_index] = gain
			audio.music_published_valid[asset_index] = true
		}
		if gain > 0.0005 do audio.music_active_layers += 1
	}
}

@(private = "file")
audio_music_publish_master :: proc(audio: ^Audio, master_volume: f32) {
	gain := clamp(master_volume, 0, 1)
	if !audio.music_master_published_valid || abs(audio.music_master_published_gain - gain) > 0.0001 {
		audio_music_store_gain(&audio.music_master_target_bits, gain)
		audio.music_master_published_gain = gain
		audio.music_master_published_valid = true
	}
}

@(private = "file")
audio_music_set_cursor :: proc(audio: ^Audio, phase_ms: f64) {
	if audio.music_loop_frames == 0 do return
	phase := max(phase_ms, 0)
	frame := u32(phase * f64(MUSIC_SAMPLE_RATE) / 1000 + 0.5)
	frame %= audio.music_loop_frames
	audio_music_store_u32(&audio.music_cursor_frame, frame)
	audio_music_store_u32(&audio.music_reference_frame, frame)
}

// Safe only while the callback stream is stopped or paused. It prevents a
// synthetic fade from the previous mix when playback starts or the boot epoch
// performs its authored hard reset.
@(private = "file")
audio_music_adopt_targets :: proc(audio: ^Audio) {
	for asset_index in 0 ..< audio.music_asset_count {
		audio.music_callback_gains[asset_index] = audio_music_load_gain(&audio.music_target_gain_bits[asset_index])
	}
	audio.music_callback_master_gain = clamp(audio_music_load_gain(&audio.music_master_target_bits), 0, 1)
	audio_music_master_dsp_reset(&audio.music_master_dsp)
}

@(private = "file")
audio_music_start_mixer :: proc(audio: ^Audio, phase_ms: f64) {
	audio_music_set_cursor(audio, phase_ms)
	audio_music_adopt_targets(audio)
	rl.PlayAudioStream(audio.music_stream)
	audio.music_stream_started = true
	audio.music_stream_paused = false
}

audio_music_loaded_stream_count :: proc(audio: ^Audio) -> int {
	if audio != nil && audio.music_stream_loaded && audio.music_stream_started do return 1
	return 0
}

audio_music_active_layer_count :: proc(audio: ^Audio) -> int {
	if audio == nil do return 0
	return audio.music_active_layers
}

audio_music_callback_service_count :: proc(audio: ^Audio) -> u32 {
	if audio == nil do return 0
	return audio_music_load_u32(&audio.music_callback_count)
}

// Publish the director's independent per-stem gains. The only raylib calls in
// steady playback are a cheap health query; decoding and buffer refills are no
// longer performed on the render thread.
audio_music_update :: proc(
	audio: ^Audio,
	director: ^Music_Director,
	master_volume: f32,
	runtime: Music_Runtime_State = {},
) {
	if audio == nil || director == nil || !audio.ready || !audio.music_stream_loaded do return
	phase_ms := music_phase_ms(director, &audio.music_library)
	start_phase_ms := phase_ms
	for state in director.slots {
		if state.active && state.start_pending {
			start_phase_ms = state.seek_ms
			break
		}
	}
	audio_music_publish_targets(audio, director, runtime)
	audio_music_publish_master(audio, master_volume)
	if master_volume <= 0 {
		if audio.music_stream_started {
			rl.StopAudioStream(audio.music_stream)
			audio.music_stream_started = false
			audio.music_stream_paused = false
		}
		audio.music_stage_valid = false
		return
	}
	if audio.suspended {
		audio_music_suspend(audio)
		return
	}

	if !audio.music_stream_started {
		audio_music_start_mixer(audio, start_phase_ms)
		audio.music_stage = director.stage
		audio.music_stage_valid = true
		return
	}

	// The boot hand-off resets the Loop epoch. Pause under raylib's audio lock,
	// reset the one shared cursor, then resume; ordinary mix changes never seek.
	if audio.music_stage_valid && audio.music_stage != director.stage {
		if !audio.music_stream_paused {
			rl.PauseAudioStream(audio.music_stream)
			audio.music_stream_paused = true
		}
		audio_music_set_cursor(audio, phase_ms)
		audio_music_adopt_targets(audio)
		rl.ResumeAudioStream(audio.music_stream)
		audio.music_stream_paused = false
	} else if audio.music_stream_paused {
		rl.ResumeAudioStream(audio.music_stream)
		audio.music_stream_paused = false
	}
	audio.music_stage = director.stage
	audio.music_stage_valid = true

	if !rl.IsAudioStreamPlaying(audio.music_stream) {
		if !audio.music_recovery_logged {
			platform_log(fmt.tprint("music: recovering stopped live mixer"))
			audio.music_recovery_logged = true
		}
		audio.music_recovery_count += 1
		audio_music_start_mixer(audio, phase_ms)
	}
}

// The callback cursor advances exactly as PCM is requested by the audio device,
// so it disciplines Loop boundaries without render-time or decoder jitter.
audio_music_reference_phase_ms :: proc(audio: ^Audio, director: ^Music_Director) -> f64 {
	if audio == nil || director == nil || !audio.ready || audio.suspended ||
	   !audio.music_stream_started || audio.music_stream_paused {
		return -1
	}
	frame := audio_music_load_u32(&audio.music_reference_frame)
	return f64(frame) * 1000 / f64(MUSIC_SAMPLE_RATE)
}

// Freeze the shared cursor for lifecycle suspension. Resume is deferred to the
// normal frame update, after the platform has restored interactivity.
audio_music_suspend :: proc(audio: ^Audio) {
	if audio == nil || !audio.music_stream_loaded || !audio.music_stream_started || audio.music_stream_paused do return
	rl.PauseAudioStream(audio.music_stream)
	audio.music_stream_paused = true
}

audio_music_shutdown :: proc(audio: ^Audio) {
	if audio == nil do return
	audio_music_stop_mixer(audio)
	audio_music_unload_assets(audio)
	music_library_destroy(&audio.music_library)
}

audio_player_step_bank :: proc(run: ^Run) -> Sfx_Bank {
	// One deliberately soft family keeps every archetype consistent across floor
	// themes while retaining all three authored grass variants.
	_ = run
	return .Step_Boot_Grass
}

@(private = "file")
audio_step_phase :: proc(anim_time, interval: f32) -> i64 {
	return i64(math.floor(f64(anim_time) / f64(interval)))
}

@(private = "file")
audio_drain_footsteps :: proc(audio: ^Audio, run: ^Run) {
	player := &run.player
	if player.moving && player.hp > 0 {
		phase := audio_step_phase(player.anim_time, SFX_PLAYER_STEP_INTERVAL_SECONDS)
		if !audio.player_step_valid || phase != audio.player_step_phase {
			audio.player_step_valid = true
			audio.player_step_phase = phase
			audio_play_bank(audio, audio_player_step_bank(run), player.pos, false, 1, player.pos)
		}
	} else {
		audio.player_step_valid = false
	}

	for &enemy in run.enemies {
		if !enemy.moving || enemy.hp <= 0 do continue
		phase := audio_step_phase(enemy.anim_time, SFX_ENEMY_STEP_INTERVAL_SECONDS)
		emitter_id := u64(enemy.entity_id) + 2
		tracker := &audio.footsteps[int(audio_sfx_hash(emitter_id) % SFX_FOOTSTEP_TRACKERS)]
		if tracker.valid && tracker.emitter_id == emitter_id && tracker.phase == phase do continue
		tracker^ = {valid=true,emitter_id=emitter_id,phase=phase}
		// Ordinary small enemies stay quiet enough for combat readability. Heavy
		// creatures and ranked enemies receive the authored creature tread.
		if enemy.kind == .Crypt_Brute || enemy.kind == .Rune_Sentinel || enemy.kind == .Hollow_Knight ||
			enemy.kind == .Gate_Warden || enemy.role != .Normal {
			audio_play_bank(audio, .Step_Creature_Heavy, enemy.pos, true, emitter_id, player.pos)
		}
	}
}

// Every semantic event is offered to the voice allocator in queue order. There
// is deliberately no same-bank frame dedup; cooldown/polyphony/priority are
// presentation policy, and the queue is always cleared even while silent.
audio_drain :: proc(audio: ^Audio, run: ^Run) {
	if run == nil do return
	defer clear(&run.sfx)
	if audio == nil || audio.suspended do return
	listener := run.player.pos
	for event in run.sfx {
		switch event.kind {
		case .Play:
			audio_play_bank(audio, event.bank, event.pos, event.spatial, event.emitter_id, listener)
		case .Stop_Bank:
			audio_stop_bank(audio, event.bank)
		}
	}
	audio_drain_footsteps(audio, run)
}
