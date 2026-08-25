package archrogue

// Raylib-free M9 settings and difficulty policy. The platform shell owns
// loading/saving and applies display/audio effects; this module only provides
// canonical values and deterministic normalization/cycling helpers.

import "core:math"

Difficulty_Id :: enum u8 {
	Easy,
	Medium,
	Hard,
	Hell,
}

DEFAULT_DIFFICULTY :: Difficulty_Id.Medium
HELL_DIFFICULTY    :: Difficulty_Id.Hell

Difficulty_Profile :: struct {
	name:                             string,
	description:                      string,
	enemy_hp_multiplier:              f32,
	enemy_damage_multiplier:          f32,
	enemy_damage_bonus:               int,
	enemy_speed_multiplier:           f32,
	enemy_attack_cooldown_multiplier: f32,
	enemy_aggro_bonus:                f32,
	enemy_count_bonus:                int,
	enemy_extra_chance:               f32,
	elite_bonus:                      f32,
	miniboss_bonus:                   f32,
	trap_chance_bonus:                f32,
	trap_damage_multiplier:           f32,
	loot_chance_bonus:                f32,
	shrine_chance_bonus:              f32,
}

@(rodata)
DIFFICULTY_PROFILES := [Difficulty_Id]Difficulty_Profile{
	.Easy = {
		name = "Easy",
		description = "Still dangerous: tougher enemies, real ambush pressure, and fewer safety nets.",
		enemy_hp_multiplier = 1.76,
		enemy_damage_multiplier = 1.64,
		enemy_damage_bonus = 1,
		enemy_speed_multiplier = 1.08,
		enemy_attack_cooldown_multiplier = 0.90,
		enemy_aggro_bonus = 0.60,
		enemy_count_bonus = 0,
		enemy_extra_chance = 0.35,
		elite_bonus = 0.03,
		miniboss_bonus = 0.015,
		trap_chance_bonus = 0.05,
		trap_damage_multiplier = 1.50,
		loot_chance_bonus = 0.0,
		shrine_chance_bonus = 0.0,
	},
	.Medium = {
		name = "Medium",
		description = "Default: severe pressure with doubled monster durability, damage, traps, and room threats.",
		enemy_hp_multiplier = 2.36,
		enemy_damage_multiplier = 2.30,
		enemy_damage_bonus = 2,
		enemy_speed_multiplier = 1.14,
		enemy_attack_cooldown_multiplier = 0.82,
		enemy_aggro_bonus = 1.40,
		enemy_count_bonus = 1,
		enemy_extra_chance = 0.70,
		elite_bonus = 0.05,
		miniboss_bonus = 0.03,
		trap_chance_bonus = 0.10,
		trap_damage_multiplier = 2.20,
		loot_chance_bonus = -0.08,
		shrine_chance_bonus = -0.04,
	},
	.Hard = {
		name = "Hard",
		description = "Brutal density, crushing hits, relentless attacks, and scarce recovery.",
		enemy_hp_multiplier = 2.85,
		enemy_damage_multiplier = 2.60,
		enemy_damage_bonus = 5,
		enemy_speed_multiplier = 1.18,
		enemy_attack_cooldown_multiplier = 0.74,
		enemy_aggro_bonus = 2.50,
		enemy_count_bonus = 2,
		enemy_extra_chance = 0.75,
		elite_bonus = 0.16,
		miniboss_bonus = 0.085,
		trap_chance_bonus = 0.25,
		trap_damage_multiplier = 2.55,
		loot_chance_bonus = -0.13,
		shrine_chance_bonus = -0.065,
	},
	.Hell = {
		name = "Hell",
		description = "Unlocked after a clear: overwhelming density, constant elites, lethal traps, and no mercy.",
		enemy_hp_multiplier = 3.80,
		enemy_damage_multiplier = 3.30,
		enemy_damage_bonus = 8,
		enemy_speed_multiplier = 1.30,
		enemy_attack_cooldown_multiplier = 0.60,
		enemy_aggro_bonus = 4.75,
		enemy_count_bonus = 3,
		enemy_extra_chance = 0.90,
		elite_bonus = 0.30,
		miniboss_bonus = 0.17,
		trap_chance_bonus = 0.42,
		trap_damage_multiplier = 3.35,
		loot_chance_bonus = -0.20,
		shrine_chance_bonus = -0.12,
	},
}

difficulty_is_valid :: proc(difficulty: Difficulty_Id) -> bool {
	i := int(difficulty)
	return i >= 0 && i < len(Difficulty_Id)
}

// A malformed value, or persisted Hell before its first-clear unlock, falls
// back to Medium just like OptionsMixin.sanitize_difficulty_name.
difficulty_normalize :: proc(difficulty: Difficulty_Id, hell_unlocked: bool) -> Difficulty_Id {
	if !difficulty_is_valid(difficulty) do return DEFAULT_DIFFICULTY
	if difficulty == .Hell && !hell_unlocked do return DEFAULT_DIFFICULTY
	return difficulty
}

difficulty_profile :: proc(difficulty: Difficulty_Id) -> Difficulty_Profile {
	normalized := difficulty
	if !difficulty_is_valid(normalized) do normalized = DEFAULT_DIFFICULTY
	return DIFFICULTY_PROFILES[normalized]
}


// Cycles one row in either direction. Hell is absent, rather than merely
// skipped after selection, until the first clear unlocks it.
difficulty_cycle :: proc(difficulty: Difficulty_Id, hell_unlocked: bool, direction: int = 1) -> Difficulty_Id {
	current := difficulty_normalize(difficulty, hell_unlocked)
	if direction == 0 do return current
	count := hell_unlocked ? len(Difficulty_Id) : len(Difficulty_Id) - 1
	delta := direction > 0 ? 1 : -1
	index := ((int(current) + delta) % count + count) % count
	return Difficulty_Id(index)
}

Difficulty_Enemy_Stats :: struct {
	hp:              int,
	damage:          int,
	speed:           f32,
	attack_cooldown: f32,
	aggro_range:     f32,
}

// Apply difficulty after depth/run/story modifiers have produced the base
// spawn stats. HP truncates, damage rounds before the flat bonus, and cooldown
// has the same 0.35-second floor as the Pygame implementation.
difficulty_apply_enemy_stats :: proc(stats: Difficulty_Enemy_Stats, difficulty: Difficulty_Id) -> Difficulty_Enemy_Stats {
	profile := difficulty_profile(difficulty)
	result := stats
	result.hp = max(1, int(f32(result.hp) * profile.enemy_hp_multiplier))
	result.damage = max(
		1,
		int(math.round(f32(result.damage) * profile.enemy_damage_multiplier)) +
			profile.enemy_damage_bonus,
	)
	result.speed *= profile.enemy_speed_multiplier
	result.attack_cooldown = max(
		f32(0.35),
		result.attack_cooldown * profile.enemy_attack_cooldown_multiplier,
	)
	result.aggro_range += profile.enemy_aggro_bonus
	return result
}

// Count bonus is applied before the independent one-enemy probability roll.
difficulty_enemy_count :: proc(base_count: int, difficulty: Difficulty_Id, extra_roll: f32) -> int {
	profile := difficulty_profile(difficulty)
	count := max(1, base_count + profile.enemy_count_bonus)
	if extra_roll < profile.enemy_extra_chance do count += 1
	return count
}

difficulty_elite_chance :: proc(base_chance: f32, difficulty: Difficulty_Id) -> f32 {
	return clamp(base_chance + difficulty_profile(difficulty).elite_bonus, f32(0), f32(0.55))
}

difficulty_miniboss_chance :: proc(base_chance: f32, difficulty: Difficulty_Id) -> f32 {
	return clamp(base_chance + difficulty_profile(difficulty).miniboss_bonus, f32(0), f32(0.22))
}

difficulty_trap_chance :: proc(base_chance: f32, difficulty: Difficulty_Id) -> f32 {
	return clamp(base_chance + difficulty_profile(difficulty).trap_chance_bonus, f32(0.04), f32(0.70))
}

difficulty_trap_damage :: proc(raw_damage: int, difficulty: Difficulty_Id) -> int {
	return max(
		1,
		int(math.round(f32(raw_damage) * difficulty_profile(difficulty).trap_damage_multiplier)),
	)
}

difficulty_loot_chance :: proc(base_chance: f32, difficulty: Difficulty_Id) -> f32 {
	return clamp(base_chance + difficulty_profile(difficulty).loot_chance_bonus, f32(0.12), f32(0.88))
}

difficulty_shrine_chance :: proc(base_chance: f32, difficulty: Difficulty_Id) -> f32 {
	return clamp(base_chance + difficulty_profile(difficulty).shrine_chance_bonus, f32(0.04), f32(0.46))
}

Frame_Rate_Cap :: enum u8 {
	FPS_30,
	FPS_60,
	FPS_90,
	FPS_120,
	Unlimited,
}

DEFAULT_FRAME_RATE_CAP :: Frame_Rate_Cap.FPS_60

@(rodata)
FRAME_RATE_CAP_TARGETS := [Frame_Rate_Cap]int{
	.FPS_30 = 30,
	.FPS_60 = 60,
	.FPS_90 = 90,
	.FPS_120 = 120,
	.Unlimited = 0,
}

@(rodata)
FRAME_RATE_CAP_LABELS := [Frame_Rate_Cap]string{
	.FPS_30 = "30 FPS",
	.FPS_60 = "60 FPS",
	.FPS_90 = "90 FPS",
	.FPS_120 = "120 FPS",
	.Unlimited = "Unlimited",
}

// Camera zoom is inverse to viewing height: smaller values show more world.
// Default to a wider 1.3 view, retain the 4.0 close-view cap, and allow a
// 0.8125 high/wide view that spans roughly twice the former 1.625 minimum.
OPTIONS_VIEW_ZOOM_DEFAULT :: f32(1.3)
OPTIONS_VIEW_ZOOM_MIN     :: f32(0.8125)
OPTIONS_VIEW_ZOOM_MAX     :: f32(4.0)
OPTIONS_VIEW_ZOOM_STEP    :: f32(1.12)

// SFX and music use the same discrete 0-100% master scale. Persisting an enum
// instead of a float keeps malformed saves recognizable and makes every menu
// adjustment exactly ten percentage points.
Audio_Volume :: enum u8 {
	Off,
	Percent_10,
	Percent_20,
	Percent_30,
	Percent_40,
	Percent_50,
	Percent_60,
	Percent_70,
	Percent_80,
	Percent_90,
	Full,
}

@(rodata)
AUDIO_VOLUME_FACTORS := [Audio_Volume]f32{
	.Off = 0, .Percent_10 = .1, .Percent_20 = .2, .Percent_30 = .3,
	.Percent_40 = .4, .Percent_50 = .5, .Percent_60 = .6, .Percent_70 = .7,
	.Percent_80 = .8, .Percent_90 = .9, .Full = 1,
}

DEFAULT_SFX_VOLUME   :: Audio_Volume.Percent_50
DEFAULT_MUSIC_VOLUME :: Audio_Volume.Full

audio_volume_normalize :: proc(volume: Audio_Volume, fallback: Audio_Volume = .Full) -> Audio_Volume {
	i := int(volume)
	if i < 0 || i >= len(Audio_Volume) do return fallback
	return volume
}

audio_volume_cycle :: proc(volume: Audio_Volume, direction: int = 1) -> Audio_Volume {
	current := audio_volume_normalize(volume)
	if direction == 0 do return current
	delta := direction > 0 ? 1 : -1
	count := len(Audio_Volume)
	return Audio_Volume(((int(current) + delta) % count + count) % count)
}

audio_volume_factor :: proc(volume: Audio_Volume) -> f32 {
	return AUDIO_VOLUME_FACTORS[audio_volume_normalize(volume)]
}

audio_volume_percent :: proc(volume: Audio_Volume) -> int {
	return int(audio_volume_normalize(volume)) * 10
}

Options :: struct {
	fullscreen:        bool,
	frame_rate_cap:    Frame_Rate_Cap,
	view_zoom:         f32,
	difficulty:        Difficulty_Id,
	controller_enabled: bool,
	gamepad_mapping:    Controller_Mapping,
	audio_enabled:      bool, // compatibility mirror: sfx_volume != Off
	sfx_volume:         Audio_Volume,
	music_volume:       Audio_Volume,
	lighting_enabled:   bool,
	mist_enabled:       bool,
	minimap_visible:    bool,
}

options_default :: proc() -> Options {
	return {
		fullscreen = true,
		frame_rate_cap = DEFAULT_FRAME_RATE_CAP,
		view_zoom = OPTIONS_VIEW_ZOOM_DEFAULT,
		difficulty = DEFAULT_DIFFICULTY,
		controller_enabled = true,
		gamepad_mapping = controller_default_mapping(),
		audio_enabled = true,
		sfx_volume = DEFAULT_SFX_VOLUME,
		music_volume = DEFAULT_MUSIC_VOLUME,
		lighting_enabled = true,
		mist_enabled = true,
		minimap_visible = true,
	}
}

frame_rate_cap_normalize :: proc(cap: Frame_Rate_Cap) -> Frame_Rate_Cap {
	i := int(cap)
	if i < 0 || i >= len(Frame_Rate_Cap) do return DEFAULT_FRAME_RATE_CAP
	return cap
}

frame_rate_cap_target :: proc(cap: Frame_Rate_Cap) -> int {
	return FRAME_RATE_CAP_TARGETS[frame_rate_cap_normalize(cap)]
}

frame_rate_cap_label :: proc(cap: Frame_Rate_Cap) -> string {
	return FRAME_RATE_CAP_LABELS[frame_rate_cap_normalize(cap)]
}

frame_rate_cap_cycle :: proc(cap: Frame_Rate_Cap, direction: int = 1) -> Frame_Rate_Cap {
	current := frame_rate_cap_normalize(cap)
	if direction == 0 do return current
	delta := direction > 0 ? 1 : -1
	count := len(Frame_Rate_Cap)
	return Frame_Rate_Cap(((int(current) + delta) % count + count) % count)
}

view_zoom_normalize :: proc(zoom: f32) -> f32 {
	if math.is_nan(zoom) || math.is_inf(zoom) do return OPTIONS_VIEW_ZOOM_DEFAULT
	return clamp(zoom, OPTIONS_VIEW_ZOOM_MIN, OPTIONS_VIEW_ZOOM_MAX)
}

view_zoom_cycle :: proc(zoom: f32, direction: int = 1) -> f32 {
	current := view_zoom_normalize(zoom)
	if direction == 0 do return current
	factor := direction > 0 ? OPTIONS_VIEW_ZOOM_STEP : 1 / OPTIONS_VIEW_ZOOM_STEP
	return view_zoom_normalize(current * factor)
}

options_normalize :: proc(options: ^Options, hell_unlocked := false) {
	options.frame_rate_cap = frame_rate_cap_normalize(options.frame_rate_cap)
	options.view_zoom = view_zoom_normalize(options.view_zoom)
	options.difficulty = difficulty_normalize(options.difficulty, hell_unlocked)
	options.sfx_volume = audio_volume_normalize(options.sfx_volume, DEFAULT_SFX_VOLUME)
	options.music_volume = audio_volume_normalize(options.music_volume, DEFAULT_MUSIC_VOLUME)
	options.audio_enabled = options.sfx_volume != .Off
	controller_mapping_normalize(&options.gamepad_mapping)
}

options_cycle_sfx_volume :: proc(options: ^Options, direction: int = 1) {
	if options == nil do return
	options.sfx_volume = audio_volume_cycle(options.sfx_volume, direction)
	options.audio_enabled = options.sfx_volume != .Off
}

options_cycle_music_volume :: proc(options: ^Options, direction: int = 1) {
	if options == nil do return
	options.music_volume = audio_volume_cycle(options.music_volume, direction)
}

options_cycle_frame_rate_cap :: proc(options: ^Options, direction: int = 1) {
	options.frame_rate_cap = frame_rate_cap_cycle(options.frame_rate_cap, direction)
}

options_cycle_view_zoom :: proc(options: ^Options, direction: int = 1) {
	options.view_zoom = view_zoom_cycle(options.view_zoom, direction)
}

options_cycle_difficulty :: proc(options: ^Options, direction: int = 1, hell_unlocked := false) {
	options.difficulty = difficulty_cycle(options.difficulty, hell_unlocked, direction)
}
