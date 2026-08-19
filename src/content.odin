package archrogue

// Data tables ported from arch_rogue/content/. Compile-time constants: typo
// in a field is a build error, and there is nothing to parse at startup.

Archetype_Id :: enum {
	Warden,
	Rogue,
	Arcanist,
	Acolyte,
	Ranger,
}

Archetype_Def :: struct {
	name:        string,
	sprite:      string, // baked sprite directory under assets/actors/
	blurb:       string,
	max_hp:      int,
	max_mana:    int,
	max_stamina: int,
	speed:       f32, // authored move rating; player_speed maps it onto 2.8 tiles/s
	melee_bonus: int,
	spell_bonus: int,
	armor_bonus: int,
}

// Shared class-skill/readability accents (combat/class_skills.py). Keeping the
// palette beside the archetype table gives simulation events, the HUD, and the
// renderer one typed source without importing a platform color type.
@(rodata)
ARCHETYPE_SKILL_COLORS := [Archetype_Id][4]u8{
	.Warden   = {235, 205, 120, 255},
	.Rogue    = {170, 230, 150, 255},
	.Arcanist = {120, 210, 255, 255},
	.Acolyte  = {220, 95, 140, 255},
	.Ranger   = {150, 215, 105, 255},
}

// --- Dungeon themes (ported from content/archetypes.py DUNGEON_THEMES) -----

Theme :: struct {
	name:       string,
	flavor:     string,
	floor:      [4]u8,
	floor_edge: [4]u8,
	wall_top:   [4]u8,
	wall_left:  [4]u8,
	wall_right: [4]u8,
	wall_edge:  [4]u8,
	stair:      [4]u8,
	accent:     [4]u8,
}

@(rodata)
THEMES := [8]Theme {
	{
		name = "Crypt of Ash", flavor = "charred halls and emberlit stairs",
		floor = {52, 47, 42, 255}, floor_edge = {72, 66, 60, 255},
		wall_top = {45, 42, 49, 255}, wall_left = {31, 29, 36, 255},
		wall_right = {24, 23, 30, 255}, wall_edge = {58, 55, 66, 255},
		stair = {230, 188, 90, 255}, accent = {240, 145, 65, 255},
	},
	{
		name = "Fungal Catacombs", flavor = "damp stone, pale spores, and hidden growths",
		floor = {42, 53, 42, 255}, floor_edge = {65, 82, 59, 255},
		wall_top = {34, 51, 45, 255}, wall_left = {24, 38, 34, 255},
		wall_right = {20, 31, 32, 255}, wall_edge = {60, 84, 70, 255},
		stair = {166, 210, 116, 255}, accent = {110, 185, 95, 255},
	},
	{
		name = "Violet Reliquary", flavor = "occult vaults humming with void rites",
		floor = {45, 39, 58, 255}, floor_edge = {78, 65, 103, 255},
		wall_top = {42, 34, 58, 255}, wall_left = {30, 24, 44, 255},
		wall_right = {25, 20, 38, 255}, wall_edge = {76, 60, 112, 255},
		stair = {205, 140, 235, 255}, accent = {160, 86, 230, 255},
	},
	{
		name = "Sunken Bastion", flavor = "flood-stained battlements and drowned reliquaries",
		floor = {39, 52, 58, 255}, floor_edge = {60, 82, 92, 255},
		wall_top = {36, 49, 55, 255}, wall_left = {25, 36, 43, 255},
		wall_right = {20, 31, 38, 255}, wall_edge = {64, 88, 99, 255},
		stair = {112, 190, 205, 255}, accent = {86, 188, 215, 255},
	},
	{
		name = "Frozen Ossuary", flavor = "blue-lit bone vaults where frost silences footsteps",
		floor = {46, 53, 62, 255}, floor_edge = {76, 91, 110, 255},
		wall_top = {43, 50, 63, 255}, wall_left = {30, 36, 48, 255},
		wall_right = {24, 30, 42, 255}, wall_edge = {88, 107, 132, 255},
		stair = {168, 215, 235, 255}, accent = {128, 206, 242, 255},
	},
	{
		name = "Obsidian Foundry", flavor = "molten channels, hammering echoes, and ember-lit machinery",
		floor = {55, 43, 38, 255}, floor_edge = {92, 62, 48, 255},
		wall_top = {49, 38, 35, 255}, wall_left = {34, 25, 25, 255},
		wall_right = {28, 21, 22, 255}, wall_edge = {118, 68, 44, 255},
		stair = {245, 132, 72, 255}, accent = {245, 104, 52, 255},
	},
	{
		name = "Moonlit Aquifer", flavor = "silver pools, echoing wells, and pale drowned altars",
		floor = {37, 49, 62, 255}, floor_edge = {62, 82, 106, 255},
		wall_top = {35, 45, 59, 255}, wall_left = {24, 33, 46, 255},
		wall_right = {19, 28, 39, 255}, wall_edge = {84, 116, 150, 255},
		stair = {176, 206, 232, 255}, accent = {145, 184, 232, 255},
	},
	{
		name = "Thornbound Vault", flavor = "root-split masonry, green witchlight, and hungry brambles",
		floor = {41, 50, 38, 255}, floor_edge = {62, 82, 52, 255},
		wall_top = {38, 47, 35, 255}, wall_left = {26, 34, 25, 255},
		wall_right = {22, 29, 21, 255}, wall_edge = {78, 103, 64, 255},
		stair = {158, 214, 106, 255}, accent = {126, 214, 92, 255},
	},
}

// --- Loot & progression (ported from content/equipment.py, models.py,
// --- population.py) --------------------------------------------------------

Rarity :: enum {
	Common,
	Magic,
	Rare,
	Unique,
	Legendary,
	Cursed,
	Unidentified, // presentation-only profile; the hidden item keeps its real tier
}

Rarity_Profile :: struct {
	name:      string,
	color:     [4]u8,
	affixes:   int, // affix count (RARITY_AFFIX_COUNTS)
	roll_lo:   f32, // affix roll multiplier range (RARITY_AFFIX_ROLL_RANGES)
	roll_hi:   f32,
}

@(rodata)
RARITIES := [Rarity]Rarity_Profile {
	.Common = {name = "Common", color = {215, 210, 190, 255}, affixes = 0, roll_lo = 0, roll_hi = 0},
	.Magic = {name = "Magic", color = {115, 175, 255, 255}, affixes = 1, roll_lo = 0.80, roll_hi = 1.00},
	.Rare = {name = "Rare", color = {245, 215, 90, 255}, affixes = 2, roll_lo = 1.00, roll_hi = 1.25},
	.Unique = {name = "Unique", color = {240, 145, 65, 255}, affixes = 3, roll_lo = 1.35, roll_hi = 1.65},
	.Legendary = {name = "Legendary", color = {255, 112, 82, 255}, affixes = 3, roll_lo = 1.25, roll_hi = 1.55},
	.Cursed = {name = "Cursed", color = {214, 92, 150, 255}, affixes = 2, roll_lo = 1.45, roll_hi = 1.75},
	.Unidentified = {name = "Unidentified", color = {170, 170, 185, 255}},
}

Equipment_Base :: struct {
	name:  string,
	value: int, // power for weapons, defense for armor
	icon:  string, // baked item icon key (assets/world/manifest.json items)
}

@(rodata)
WEAPON_BASES := [5]Equipment_Base{
	{"Iron Sword", 5, "named.iron_sword"},
	{"Hunter Axe", 7, "named.hunter_axe"},
	{"Runed Saber", 6, "named.runed_saber"},
	{"Ash Pike", 7, "named.ash_pike"},
	{"Grave Knife", 4, "named.grave_knife"},
}

@(rodata)
ARMOR_BASES := [5]Equipment_Base{
	{"Leather Jerkin", 2, "named.leather_jerkin"},
	{"Warden Mail", 4, "named.warden_mail"},
	{"Chain Vest", 3, "named.chain_vest"},
	{"Boneweave Mantle", 3, "named.boneweave_mantle"},
	{"Pilgrim's Plate", 4, "named.pilgrims_plate"},
}

// The pygame run always starts with mundane class gear. These deliberately
// use their starter values rather than the similarly named random-loot bases.
@(rodata)
STARTER_WEAPONS := [Archetype_Id]Equipment_Base{
	.Warden = {"Warden Arming Sword", 3, "weapon"},
	.Rogue = {"Twin Fang Knife", 6, "weapon"},
	.Arcanist = {"Runed Wand", 1, "weapon"},
	.Acolyte = {"Pilgrim Censer", 2, "weapon"},
	.Ranger = {"Yew Longbow", 5, "weapon"},
}

@(rodata)
STARTER_ARMORS := [Archetype_Id]Equipment_Base{
	.Warden = {"Warden Mail", 3, "named.warden_mail"},
	.Rogue = {"Shadow Jerkin", 1, "armor"},
	.Arcanist = {"Apprentice Mantle", 1, "armor"},
	.Acolyte = {"Boneweave Mantle", 2, "named.boneweave_mantle"},
	.Ranger = {"Trail Leathers", 2, "armor"},
}

ICON_HEAL_POTION :: "potion"
ICON_MANA_POTION :: "mana_potion"
ICON_IDENTIFY_SCROLL :: "identify"
ICON_REMOVE_CURSE_SCROLL :: "remove_curse"

Damage_Type :: enum {
	Physical,
	Fire,
	Frost,
	Poison,
	Arcane,
	Holy,
	Shadow,
}

@(rodata)
DAMAGE_TYPE_NAMES := [Damage_Type]string{
	.Physical = "physical", .Fire = "fire", .Frost = "frost",
	.Poison = "poison", .Arcane = "arcane", .Holy = "holy", .Shadow = "shadow",
}

@(rodata)
DAMAGE_TYPE_COLORS := [Damage_Type][4]u8{
	.Physical = {255, 210, 120, 255}, .Fire = {255, 132, 74, 255},
	.Frost = {126, 206, 242, 255}, .Poison = {126, 214, 92, 255},
	.Arcane = {160, 118, 245, 255}, .Holy = {235, 205, 120, 255},
	.Shadow = {214, 92, 150, 255},
}

Status_Kind :: enum {
	Poisoned,
	Chilled,
	Burning,
	Snared,
	Bound,
	Stunned,
	Smoke,
	Aegis,
}

Status_Def :: struct {
	name:        string,
	damage_type: Damage_Type,
	move_factor: f32,
	color:       [4]u8,
}

@(rodata)
STATUS_DEFS := [Status_Kind]Status_Def{
	.Poisoned = {"poisoned", .Poison, 1.0, {126, 214, 92, 255}},
	.Chilled = {"chilled", .Frost, 0.58, {126, 206, 242, 255}},
	.Burning = {"burning", .Fire, 1.0, {255, 132, 74, 255}},
	.Snared = {"snared", .Physical, 0.45, {150, 215, 105, 255}},
	.Bound = {"bound", .Shadow, 0.62, {214, 92, 150, 255}},
	.Stunned = {"stunned", .Holy, 1.0, {235, 205, 120, 255}},
	.Smoke = {"smoke", .Shadow, 1.0, {170, 170, 185, 255}},
	.Aegis = {"aegis", .Holy, 1.0, {235, 205, 120, 255}},
}

Affix_Kind :: enum {
	Serrated,
	Cruel,
	Balanced,
	Frostbitten,
	Zealous,
	Vampiric,
	Storm_Touched,
	Ember_Veined,
	Venomous,
	Quickened,
	Rune_Cut,
	Grave_Hungering,
	Reinforced,
	Stalwart,
	Light,
	Sealed,
	Thorned,
	Grounded,
	Regal,
	Fleet,
	Mirror_Barbed,
	Hexwoven,
	Focused,
	Of_The_Fox,
	Of_Warding,
	Of_Force,
	Of_The_Deep,
	Of_Ember,
	Of_Cinders,
	Of_The_Moon,
	Of_Thorns,
	Of_Alacrity,
	Of_The_Occult,
	Of_The_Hunt,
	Of_Siphons,
}

Skill_Bonus :: enum {
	Dash_Tempo,
	Melee_Force,
	Bolt_Shard,
	Bolt_Pierce,
	Melee_Tempo,
	Nova_Ward,
	Blood_Leech,
	// MX.5 named-unique bonuses (equipment.py skill_bonus strings).
	Dash_Guard,
	Time_Skip_Ward,
	Ambush_Potency,
	Nova_Radius,
	Spirit_Call_Ward,
	Spirit_Beast_Bond,
}

@(rodata)
SKILL_BONUS_NAMES := [Skill_Bonus]string{
	.Dash_Tempo = "Dash tempo", .Melee_Force = "Melee force",
	.Bolt_Shard = "Bolt shard", .Bolt_Pierce = "Bolt pierce",
	.Melee_Tempo = "Melee tempo", .Nova_Ward = "Nova ward",
	.Blood_Leech = "Blood leech",
	.Dash_Guard = "Dash guard", .Time_Skip_Ward = "Time Skip ward",
	.Ambush_Potency = "Ambush Bell potency", .Nova_Radius = "Nova radius",
	.Spirit_Call_Ward = "Spirit Call ward", .Spirit_Beast_Bond = "Spirit Beast bond",
}

Proc_Effect :: enum {
	None,
	Bleed,
	Chill,
	Chain,
	Ignite,
	Poison,
	Lifesteal,
	Thorns,
}

@(rodata)
PROC_EFFECT_NAMES := [Proc_Effect]string{
	.None = "", .Bleed = "bleed", .Chill = "chill", .Chain = "chain",
	.Ignite = "ignite", .Poison = "poison", .Lifesteal = "lifesteal",
	.Thorns = "thorns",
}

Stat_Range :: struct {lo, hi: f32}

Affix_Def :: struct {
	name:         string,
	weapon:       bool,
	armor:        bool,
	power:        Stat_Range,
	defense:      Stat_Range,
	attack_speed: Stat_Range,
	cast_speed:   Stat_Range,
	move_speed:   Stat_Range,
	thorns:       Stat_Range,
	lifesteal:    Stat_Range,
	proc_chance:  Stat_Range,
	typed:        bool,
	damage_type:  Damage_Type,
	skill_bonus:  Skill_Bonus,
	has_bonus:    bool,
	proc_effect:  Proc_Effect,
}

// The complete pygame AFFIX_DEFINITIONS table. Each non-zero stat range is
// rolled independently, then scaled by the item's rarity multiplier.
@(rodata)
AFFIX_DEFS := [Affix_Kind]Affix_Def{
	.Serrated = {name="Serrated", weapon=true, power={2,4}, proc_chance={.16,.26}, proc_effect=.Bleed},
	.Cruel = {name="Cruel", weapon=true, power={4,6}},
	.Balanced = {name="Balanced", weapon=true, power={1,3}, attack_speed={.04,.08}, skill_bonus=.Dash_Tempo, has_bonus=true},
	.Frostbitten = {name="Frostbitten", weapon=true, power={2,4}, proc_chance={.22,.34}, typed=true, damage_type=.Frost, proc_effect=.Chill},
	.Zealous = {name="Zealous", weapon=true, power={2,4}, defense={0,1}, typed=true, damage_type=.Holy, skill_bonus=.Melee_Force, has_bonus=true},
	.Vampiric = {name="Vampiric", weapon=true, power={2,4}, lifesteal={.05,.08}, typed=true, damage_type=.Shadow, proc_effect=.Lifesteal},
	.Storm_Touched = {name="Storm-Touched", weapon=true, power={3,5}, cast_speed={.04,.08}, proc_chance={.16,.26}, typed=true, damage_type=.Arcane, skill_bonus=.Bolt_Shard, has_bonus=true, proc_effect=.Chain},
	.Ember_Veined = {name="Ember-Veined", weapon=true, power={3,5}, proc_chance={.22,.34}, typed=true, damage_type=.Fire, proc_effect=.Ignite},
	.Venomous = {name="Venomous", weapon=true, power={2,4}, attack_speed={.02,.05}, proc_chance={.24,.38}, typed=true, damage_type=.Poison, proc_effect=.Poison},
	.Quickened = {name="Quickened", weapon=true, power={1,2}, attack_speed={.07,.12}, skill_bonus=.Melee_Tempo, has_bonus=true},
	.Rune_Cut = {name="Rune-Cut", weapon=true, power={2,4}, cast_speed={.05,.10}, typed=true, damage_type=.Arcane, skill_bonus=.Bolt_Pierce, has_bonus=true},
	.Grave_Hungering = {name="Grave-Hungering", weapon=true, power={3,5}, lifesteal={.06,.10}, typed=true, damage_type=.Shadow, skill_bonus=.Blood_Leech, has_bonus=true, proc_effect=.Lifesteal},
	.Reinforced = {name="Reinforced", armor=true, defense={2,4}},
	.Stalwart = {name="Stalwart", armor=true, defense={3,5}},
	.Light = {name="Light", armor=true, defense={1,2}, attack_speed={.02,.05}, move_speed={.03,.06}, skill_bonus=.Dash_Tempo, has_bonus=true},
	.Sealed = {name="Sealed", armor=true, defense={3,5}, typed=true, damage_type=.Shadow, skill_bonus=.Nova_Ward, has_bonus=true},
	.Thorned = {name="Thorned", armor=true, power={0,1}, defense={1,3}, thorns={2,4}, proc_effect=.Thorns},
	.Grounded = {name="Grounded", armor=true, defense={3,5}, cast_speed={.02,.05}, typed=true, damage_type=.Arcane, skill_bonus=.Nova_Ward, has_bonus=true},
	.Regal = {name="Regal", armor=true, power={1,2}, defense={2,4}, typed=true, damage_type=.Holy, skill_bonus=.Melee_Force, has_bonus=true},
	.Fleet = {name="Fleet", armor=true, defense={1,2}, move_speed={.05,.10}, skill_bonus=.Dash_Tempo, has_bonus=true},
	.Mirror_Barbed = {name="Mirror-Barbed", armor=true, defense={2,4}, thorns={3,6}, typed=true, damage_type=.Arcane, proc_effect=.Thorns},
	.Hexwoven = {name="Hexwoven", armor=true, defense={2,4}, cast_speed={.04,.08}, typed=true, damage_type=.Shadow, skill_bonus=.Blood_Leech, has_bonus=true},
	.Focused = {name="Focused", armor=true, defense={1,3}, cast_speed={.06,.12}},
	.Of_The_Fox = {name="of the Fox", weapon=true, armor=true, power={1,2}, defense={1,2}, attack_speed={.03,.07}, move_speed={.03,.07}, skill_bonus=.Dash_Tempo, has_bonus=true},
	.Of_Warding = {name="of Warding", weapon=true, armor=true, defense={2,4}, skill_bonus=.Nova_Ward, has_bonus=true},
	.Of_Force = {name="of Force", weapon=true, armor=true, power={2,4}, skill_bonus=.Melee_Force, has_bonus=true},
	.Of_The_Deep = {name="of the Deep", weapon=true, armor=true, defense={2,4}, proc_chance={.14,.24}, typed=true, damage_type=.Frost, proc_effect=.Chill},
	.Of_Ember = {name="of Ember", weapon=true, armor=true, power={2,4}, proc_chance={.16,.28}, typed=true, damage_type=.Fire, proc_effect=.Ignite},
	.Of_Cinders = {name="of Cinders", weapon=true, armor=true, power={3,5}, defense={-2,-1}, cast_speed={.03,.07}, proc_chance={.20,.32}, typed=true, damage_type=.Fire, proc_effect=.Ignite},
	.Of_The_Moon = {name="of the Moon", weapon=true, armor=true, power={1,2}, defense={2,4}, cast_speed={.03,.07}, proc_chance={.18,.30}, typed=true, damage_type=.Frost, proc_effect=.Chill},
	.Of_Thorns = {name="of Thorns", weapon=true, armor=true, defense={1,3}, thorns={2,5}, proc_effect=.Thorns},
	.Of_Alacrity = {name="of Alacrity", weapon=true, armor=true, attack_speed={.04,.08}, cast_speed={.04,.08}, move_speed={.02,.05}},
	.Of_The_Occult = {name="of the Occult", weapon=true, armor=true, power={1,3}, cast_speed={.05,.10}, typed=true, damage_type=.Shadow, skill_bonus=.Blood_Leech, has_bonus=true},
	.Of_The_Hunt = {name="of the Hunt", weapon=true, armor=true, power={1,3}, move_speed={.03,.07}, skill_bonus=.Bolt_Shard, has_bonus=true},
	.Of_Siphons = {name="of Siphons", weapon=true, armor=true, power={1,3}, lifesteal={.04,.08}, typed=true, damage_type=.Shadow, proc_effect=.Lifesteal},
}

Item_Kind :: enum {
	Heal_Potion,
	Mana_Potion,
	Identify_Scroll,
	Remove_Curse_Scroll,
	Weapon,
	Armor,
}

HEAL_POTION_AMOUNT :: 35 // Minor Healing Potion
MANA_POTION_AMOUNT :: 24 // Lesser Mana Potion
POTION_COOLDOWN :: 0.5

// Progression (models.py gain_xp): 100 xp to level 2, x1.5 per level,
// +12 max hp (full heal), +5 mana, +5 stamina.
XP_BASE :: 100
XP_GROWTH :: 1.5
LEVEL_HP_GAIN :: 12
LEVEL_MANA_GAIN :: 5
LEVEL_STAMINA_GAIN :: 5

PLAYER_BASE_MELEE :: 10 // 10 + level*2 + melee_bonus + weapon power
PLAYER_LEVEL_DAMAGE :: 2

// Drops (combat/damage.py + population.py, 4.9.23 tuning).
KILL_DROP_CHANCE :: 0.28
ROOM_LOOT_CHANCE :: 0.33
GOLD_MIN :: 4
GOLD_MAX :: 10 // randrange(4, 11)

// Depth scaling (_apply_run_modifier): gentle surface ramp, steeper past 5.
depth_hp_multiplier :: proc(depth: int) -> f32 {
	return 1.0 + f32(max(0, depth - 1)) * 0.045 + f32(max(0, depth - 5)) * 0.05
}

depth_damage_bonus :: proc(depth: int) -> int {
	return max(0, depth - 4) / 2 + max(0, depth - 5)
}

Enemy_Kind :: enum {
	Ghoul,
	Venom_Skitter,
	Bone_Imp,
	Grave_Archer,
	Cultist,
	Crypt_Brute,
	Ash_Hound,
	Rune_Sentinel,
	Plague_Toad,
	Hollow_Knight,
	Gate_Warden, // final-room guard, never in the open pool
}

// MX.2 tactical doctrines, ported 1:1 from content/enemies.py TACTICS. The
// doctrine is a separate axis from Enemy_Role rank: it decides range bands and
// movement style, never reward math.
Enemy_Tactic :: enum u8 {
	Bruiser,
	Mauler,
	Guard,
	Flanker,
	Skirmisher,
	Caster,
	Marksman,
	Artillery,
	Sentinel,
}

Tactic_Def :: struct {
	preferred_range:    f32,
	min_range:          f32,
	strafe_bias:        f32,
	hold_anchor:        bool,
	reposition_for_los: bool,
}

@(rodata)
TACTIC_DEFS := [Enemy_Tactic]Tactic_Def {
	.Bruiser    = {},
	.Mauler     = {},
	.Guard      = {},
	.Flanker    = {strafe_bias = 0.55},
	.Skirmisher = {preferred_range = 3.0, min_range = 2.0, strafe_bias = 0.65, reposition_for_los = true},
	.Caster     = {preferred_range = 3.8, min_range = 2.2, reposition_for_los = true},
	.Marksman   = {preferred_range = 4.6, min_range = 2.8, reposition_for_los = true},
	.Artillery  = {preferred_range = 3.4, min_range = 2.6, reposition_for_los = true},
	.Sentinel   = {preferred_range = 4.2, min_range = 2.0, hold_anchor = true, reposition_for_los = true},
}

// A ranged enemy whose doctrine carries no band (an elite override to
// flanker/guard) falls back here and deliberately loses strafe/reposition,
// exactly like pygame's enemy_tactic resolution.
DEFAULT_RANGED_TACTIC :: Tactic_Def{preferred_range = RANGED_PREFERRED_RANGE, min_range = RANGED_MIN_RANGE}

Enemy_Def :: struct {
	name:            string,
	sprite:          string,
	ranged:          bool,
	max_hp:          int,
	speed:           f32, // tiles per second
	damage:          int,
	xp:              int,
	attack_range:    f32,
	attack_cooldown: f32,
	aggro_range:     f32,
	color:           [4]u8,
	damage_type:     Damage_Type,
	weight:          int, // spawn weight
	final_room_only: bool, // FINAL_ROOM_ENEMY_DEFINITIONS extras
	tactic:          Enemy_Tactic,
}

// Starter roster rows ported 1:1 from content/enemies.py ENEMY_DEFINITIONS.
@(rodata)
ENEMY_DEFS := [Enemy_Kind]Enemy_Def {
	.Ghoul = {
		name = "Ghoul", sprite = "ghoul", max_hp = 42, speed = 1.56,
		damage = 10, xp = 20, attack_range = 1.05, attack_cooldown = 0.95,
		aggro_range = 8.0, color = {160, 68, 68, 255}, damage_type = .Shadow, weight = 22,
		tactic = .Mauler,
	},
	.Venom_Skitter = {
		name = "Venom Skitter", sprite = "venom_skitter", max_hp = 30, speed = 2.08,
		damage = 7, xp = 15, attack_range = 0.95, attack_cooldown = 0.72,
		aggro_range = 9.5, color = {110, 185, 95, 255}, damage_type = .Poison, weight = 16,
		tactic = .Flanker,
	},
	.Bone_Imp = {
		name = "Bone Imp", sprite = "bone_imp", ranged = true, max_hp = 26, speed = 1.72,
		damage = 6, xp = 16, attack_range = 4.6, attack_cooldown = 1.0,
		aggro_range = 8.0, color = {190, 130, 215, 255}, damage_type = .Frost, weight = 18,
		tactic = .Skirmisher,
	},
	.Grave_Archer = {
		name = "Grave Archer", sprite = "grave_archer", ranged = true, max_hp = 38, speed = 1.28,
		damage = 9, xp = 21, attack_range = 5.8, attack_cooldown = 1.35,
		aggro_range = 9.0, color = {120, 145, 105, 255}, damage_type = .Physical, weight = 8,
		tactic = .Marksman,
	},
	.Cultist = {
		name = "Cultist", sprite = "cultist", ranged = true, max_hp = 34, speed = 1.16,
		damage = 8, xp = 18, attack_range = 5.4, attack_cooldown = 1.45,
		aggro_range = 8.0, color = {125, 75, 170, 255}, damage_type = .Arcane, weight = 22,
		tactic = .Caster,
	},
	.Crypt_Brute = {
		name = "Crypt Brute", sprite = "crypt_brute", max_hp = 82, speed = 1.00,
		damage = 17, xp = 32, attack_range = 1.35, attack_cooldown = 1.35,
		aggro_range = 8.0, color = {155, 105, 74, 255}, damage_type = .Physical, weight = 14,
		tactic = .Bruiser,
	},
	.Ash_Hound = {
		name = "Ash Hound", sprite = "ash_hound", max_hp = 34, speed = 1.92,
		damage = 9, xp = 19, attack_range = 0.95, attack_cooldown = 0.82,
		aggro_range = 9.0, color = {185, 86, 54, 255}, damage_type = .Fire, weight = 14,
		tactic = .Flanker,
	},
	.Rune_Sentinel = {
		name = "Rune Sentinel", sprite = "rune_sentinel", ranged = true, max_hp = 66, speed = 0.88,
		damage = 13, xp = 30, attack_range = 5.2, attack_cooldown = 1.7,
		aggro_range = 8.5, color = {116, 220, 245, 255}, damage_type = .Arcane, weight = 8,
		tactic = .Sentinel,
	},
	.Plague_Toad = {
		name = "Plague Toad", sprite = "plague_toad", ranged = true, max_hp = 54, speed = 1.08,
		damage = 11, xp = 25, attack_range = 4.2, attack_cooldown = 1.55,
		aggro_range = 7.5, color = {144, 172, 86, 255}, damage_type = .Poison, weight = 10,
		tactic = .Artillery,
	},
	.Hollow_Knight = {
		name = "Hollow Knight", sprite = "hollow_knight", max_hp = 58, speed = 1.40,
		damage = 13, xp = 29, attack_range = 1.15, attack_cooldown = 1.05,
		aggro_range = 8.5, color = {126, 132, 128, 255}, damage_type = .Physical, weight = 9,
		tactic = .Guard,
	},
	.Gate_Warden = {
		name = "Gate Warden", sprite = "gate_warden", max_hp = 72, speed = 1.20,
		damage = 14, xp = 34, attack_range = 1.2, attack_cooldown = 1.0,
		aggro_range = 8.0, color = {190, 92, 54, 255}, damage_type = .Holy, weight = 24, final_room_only = true,
		tactic = .Guard,
	},
}

// --- Elites, minibosses, bosses (content/progression.py + enemies.py) ------

Elite_Modifier :: struct {
	name:         string,
	hp_mult:      f32,
	damage_bonus: int,
	speed_mult:   f32,
	xp_bonus:     int,
	aggro_bonus:  f32,
	color_shift:  [3]int, // progression.py color_shift, channels clamped 35..255
	has_tactic:   bool, // doctrine override (progression.py role reassignment)
	tactic:       Enemy_Tactic,
}

@(rodata)
ELITE_MODIFIERS := [4]Elite_Modifier{
	{"Frenzied", 1.45, 3, 1.18, 12, 0, {45, -10, -10}, true, .Flanker},
	{"Ironbound", 1.95, 2, 0.86, 16, 0, {35, 24, -8}, true, .Guard},
	{"Venomous", 1.40, 5, 1.0, 14, 0, {-20, 42, -16}, true, .Flanker},
	{"Runed", 1.55, 4, 1.0, 18, 1.0, {-18, 30, 48}, false, .Bruiser},
}

// progression.py _shift_color: per-channel add, clamped into [35, 255].
elite_shift_color :: proc(color: [4]u8, shift: [3]int) -> [4]u8 {
	out := color
	for i in 0 ..< 3 {
		out[i] = u8(clamp(int(color[i]) + shift[i], 35, 255))
	}
	return out
}

// elite_chance / miniboss_chance (population.py). `bonus` carries the MX.4
// encounter-template and run-modifier pressure inside the pygame clamp, the
// same way population.py folds them into `base` before min/max.
elite_chance :: proc(depth: int, bonus := f32(0)) -> f32 {
	return clamp(0.06 + f32(depth) * 0.006 + bonus, 0, 0.55)
}

miniboss_chance :: proc(depth: int, bonus := f32(0)) -> f32 {
	return clamp(0.015 + f32(depth) * 0.006 + bonus, 0, 0.22)
}

MINIBOSS_HP_MULT :: 1.85
MINIBOSS_DAMAGE_BONUS :: 3
MINIBOSS_XP_BONUS :: 34
FLOOR_BOSS_HP_MULT :: 1.85
FLOOR_BOSS_DAMAGE_BONUS :: 6
FINAL_BOSS_HP_MULT :: 2.4
FINAL_BOSS_DAMAGE_BONUS :: 9
FINAL_BOSS_COOLDOWN_MULT :: 0.8
FINAL_BOSS_COOLDOWN_MIN :: 0.6
FINAL_BOSS_ATTACK_RANGE_MIN :: 1.9
FINAL_BOSS_AGGRO_RANGE :: 16.0
FINAL_BOSS_SPEED_MIN :: 1.15

DUNGEON_DEPTH :: 10

is_boss_depth :: proc(depth: int) -> bool {
	return depth == 3 || depth == 6 || depth == 9 || depth == DUNGEON_DEPTH
}

Ability_Effect :: enum {
	Strike, // single-target melee hitscan
	Bolt,   // single projectile
	Fan,    // projectile_count bolts across spread
	Nova,   // radial LOS-checked burst around the caster
}

Ability_Id :: enum {
	Ember_Cleave,
	Ember_Nova,
	Spore_Volley,
	Frost_Fan,
	Arcane_Lance,
	Gate_Strike,
	Shadow_Volley,
}

Ability_Def :: struct {
	key:          string,
	effect:       Ability_Effect,
	dmg_mult:     f32,
	attack_range: f32, // 0 = inherit the owner's base range
	min_range:    f32,
	windup:       f32,
	cooldown:     f32,
	proj_speed:   f32,
	proj_count:   int,
	spread:       f32, // full perpendicular fan width in tile-space velocity
	status:       Status_Kind,
	has_status:   bool,
	status_duration: f32,
}

// ENEMY_ABILITIES ported; status riders (poisoned/chilled) land with M8.
@(rodata)
ABILITY_DEFS := [Ability_Id]Ability_Def{
	.Ember_Cleave = {key = "ember_cleave", effect = .Strike, dmg_mult = 1.45, windup = 0.55, cooldown = 4.5, proj_speed = 6, proj_count = 1, spread = 0.28},
	.Ember_Nova = {key = "ember_nova", effect = .Nova, dmg_mult = 0.8, attack_range = 2.6, windup = 0.45, cooldown = 6.5, proj_speed = 6, proj_count = 1, spread = 0.28},
	.Spore_Volley = {key = "spore_volley", effect = .Fan, dmg_mult = 0.75, min_range = 2.0, windup = 0.55, cooldown = 5.0, proj_speed = 6, proj_count = 4, spread = 0.42, status = .Poisoned, has_status = true, status_duration = 1.6},
	.Frost_Fan = {key = "frost_fan", effect = .Fan, dmg_mult = 0.65, min_range = 2.0, windup = 0.55, cooldown = 6.0, proj_speed = 6, proj_count = 5, spread = 0.55, status = .Chilled, has_status = true, status_duration = 1.2},
	.Arcane_Lance = {key = "arcane_lance", effect = .Bolt, dmg_mult = 1.6, min_range = 2.0, windup = 0.7, cooldown = 5.5, proj_speed = 8.5, proj_count = 1, spread = 0.28},
	.Gate_Strike = {key = "gate_strike", effect = .Strike, dmg_mult = 1.3, windup = 0.4, cooldown = 3.2, proj_speed = 6, proj_count = 1, spread = 0.28},
	.Shadow_Volley = {key = "shadow_volley", effect = .Fan, dmg_mult = 0.9, min_range = 2.0, windup = 0.45, cooldown = 4.2, proj_speed = 6, proj_count = 3, spread = 0.3},
}

Boss_Id :: enum {
	Ash_Gallows,
	Mycelial_Matron,
	Rime_Chanter,
	Void_Sentinel,
	Gate_Tyrant,
}

Boss_Def :: struct {
	name:            string,
	subtitle:        string,
	sprite:          string,
	themes:          [2]int, // THEMES indices this boss haunts (-1 unused)
	max_hp:          int,
	speed:           f32,
	damage:          int,
	xp:              int,
	attack_range:    f32,
	attack_cooldown: f32,
	aggro_range:     f32,
	color:           [4]u8,
	damage_type:     Damage_Type,
	final_boss:      bool,
	abilities:       [2]Ability_Id,
	ability_count:   int,
	// Floor-plan reward hint (enemies.py loot_hook). The pygame "chance"
	// wording was stale — guardians guarantee a Rare (MX.5 contract) — so the
	// strings are reconciled here instead of ported verbatim.
	loot_hook:       string,
}

// BOSS_DEFINITIONS ported 1:1 (damage types join with M8).
@(rodata)
BOSS_DEFS := [Boss_Id]Boss_Def{
	.Ash_Gallows = {
		name = "Ash Gallows Knight",
		subtitle = "a shielded executioner who leaves ember scars before heavy swings",
		sprite = "ash_gallows_knight", themes = {0, 5},
		max_hp = 132, speed = 1.04, damage = 17, xp = 62,
		attack_range = 1.35, attack_cooldown = 1.05, aggro_range = 10.5,
		color = {226, 104, 58, 255}, damage_type = .Fire,
		abilities = {.Ember_Cleave, .Ember_Nova}, ability_count = 2,
		loot_hook = "fire-forged rare weapon",
	},
	.Mycelial_Matron = {
		name = "Mycelial Matron",
		subtitle = "a spore witch that controls space with poison bolts and rooting spores",
		sprite = "mycelial_matron", themes = {1, 7},
		max_hp = 122, speed = 0.94, damage = 15, xp = 58,
		attack_range = 4.9, attack_cooldown = 1.22, aggro_range = 11.0,
		color = {116, 196, 98, 255}, damage_type = .Poison,
		abilities = {.Spore_Volley, .Spore_Volley}, ability_count = 1,
		loot_hook = "sealed rare armor",
	},
	.Rime_Chanter = {
		name = "Rime Chanter of the Ninth Bell",
		subtitle = "a frost cultist whose chill volleys punish straight-line approaches",
		sprite = "rime_chanter", themes = {4, 6},
		max_hp = 118, speed = 0.99, damage = 14, xp = 60,
		attack_range = 5.2, attack_cooldown = 1.12, aggro_range = 11.5,
		color = {138, 212, 242, 255}, damage_type = .Frost,
		abilities = {.Frost_Fan, .Frost_Fan}, ability_count = 1,
		loot_hook = "frost-touched rare relic",
	},
	.Void_Sentinel = {
		name = "Voidbound Rune Sentinel",
		subtitle = "a reliquary construct that fires arcane bolts while its armor hums",
		sprite = "voidbound_rune_sentinel", themes = {2, 3},
		max_hp = 150, speed = 0.80, damage = 18, xp = 68,
		attack_range = 5.4, attack_cooldown = 1.34, aggro_range = 12.0,
		color = {166, 118, 246, 255}, damage_type = .Arcane,
		abilities = {.Arcane_Lance, .Arcane_Lance}, ability_count = 1,
		loot_hook = "runed rare armament",
	},
	.Gate_Tyrant = {
		name = "Dread Gate Tyrant",
		subtitle = "the final seal's tyrant with alternating melee pressure and shadow casts",
		sprite = "gate_tyrant", themes = {-1, -1},
		max_hp = 245, speed = 0.94, damage = 21, xp = 120,
		attack_range = 1.45, attack_cooldown = 1.08, aggro_range = 13.0,
		color = {214, 92, 150, 255}, damage_type = .Shadow, final_boss = true,
		abilities = {.Gate_Strike, .Shadow_Volley}, ability_count = 2,
		loot_hook = "unique gate relic", // depth 10 overrides with the clear-record hint
	},
}

// The Tyrant is renamed by the floor's theme (population.py _make_boss).
@(rodata)
TYRANT_TITLES := [8]string{
	"Ashen Gate Tyrant",     // Crypt of Ash
	"Mycelial Gate Tyrant",  // Fungal Catacombs
	"Voidbound Gate Tyrant", // Violet Reliquary
	"Drowned Gate Tyrant",   // Sunken Bastion
	"Rimebound Gate Tyrant", // Frozen Ossuary
	"Forgeheart Gate Tyrant", // Obsidian Foundry
	"Moon-Drowned Gate Tyrant", // Moonlit Aquifer
	"Thorn-Crowned Gate Tyrant", // Thornbound Vault
}

BOSS_MOVE_RADIUS :: 0.82 // BOSS_FOOTPRINT_MOVE_RADIUS
BOSS_HIT_RADIUS :: 0.92

// Combat constants ported from constants.py / combat/_utils.py.
PLAYER_MELEE_RANGE :: 1.55
PLAYER_MELEE_ARC_DOT :: 0.05
ENEMY_MELEE_WINDUP :: 0.35
ENEMY_CAST_WINDUP :: 0.5
ENEMY_BOLT_SPEED :: 6.0
RANGED_PREFERRED_RANGE :: 3.5 // kite band from DEFAULT_RANGED_TACTIC
RANGED_MIN_RANGE :: 2.5
SIGHT_RADIUS :: 4.0 // LIGHT_LEVEL_SIGHT_RADIUS == DARK_LEVEL_LIGHT_RADIUS

// MX.2 boss ability selection (combat/abilities.py).
ENEMY_BOSS_WINDUP :: 0.25
BOSS_CAST_MIN_RANGE :: 2.0
BOSS_CAST_MAX_RANGE :: 6.0 // also the inherited bolt/fan reach floor for bosses
BOSS_PHASE_HP_FRACTION :: 0.5
BOSS_PHASE_COOLDOWN_FACTOR :: 0.8

// MX.2 alertness, memory, and stall recovery (combat/_utils.py, enemies.py).
ENEMY_ALERT_MEMORY :: 4.0
ENEMY_ALERT_RADIUS :: 4.0
ENEMY_MEMORY_ARRIVE_DISTANCE :: 0.35
ENEMY_YIELD_SECONDS :: 0.55
ENEMY_STUCK_PROBE_SECONDS :: 0.9
ENEMY_SEPARATION_BIAS :: 0.35
ENEMY_SEPARATION_FRACTION :: 0.9

// MX.2 radius-limited navigation field (combat/pathing.py).
NAV_FIELD_RADIUS :: 24
NAV_REFRESH_SECONDS :: 0.5
NAV_DIRECT_COST :: 2
NAV_STALL_LATCH_SECONDS :: 0.8

// MX.2 knockback physics (combat/_utils.py, damage.py, enemies.py).
KNOCKBACK_SPEED :: 1.6
KNOCKBACK_DECAY_RATE :: 10.0
KNOCKBACK_CHAIN_MIN_SPEED :: 4.0
KNOCKBACK_CHAIN_TRANSFER :: 0.85
KNOCKBACK_CHAIN_ARC_DOT :: 0.35
PLAYER_STAMINA_REGEN :: 30.0
RANGER_STAMINA_REGEN :: 38.0
PLAYER_MANA_REGEN :: 2.5
ARCANIST_MANA_REGEN :: 3.5

BIGHIT_CHARGE_TIME :: 0.9
BIGHIT_COMMIT_FRACTION :: 0.5
BIGHIT_COOLDOWN :: 6.0
BIGHIT_CANCEL_COOLDOWN :: 1.5
BIGHIT_STAMINA_COST :: 20
BIGHIT_DAMAGE_MULT :: 3.0
BIGHIT_THROW_TILES :: 2.0
BIGHIT_THROW_TILES_RANGER :: 2.2
BIGHIT_BOSS_THROW_FACTOR :: 0.35
BIGHIT_CLEAVE_FACTOR :: 0.62

BOLT_BASE_DAMAGE :: 14
BOLT_SPEED :: 9.0
BOLT_TTL :: 1.4
NOVA_BASE_RADIUS :: 2.45
TIME_SKIP_FACTOR :: 0.4
TIME_SKIP_DURATION :: 3.0

@(rodata)
ACTION_NAMES := [Archetype_Id][4]string{
	.Warden = {"Bulwark Slam", "Guard Bolt", "Time Skip", "Guard Step"},
	.Rogue = {"Killing Blow", "Knife Fan", "Ambush Bell", "Shadow Dash"},
	.Arcanist = {"Force Slam", "Arc Bolt", "Frost Nova", "Blink"},
	.Acolyte = {"Blood Reap", "Spirit Bolt", "Spirit Call", "Dark Step"},
	.Ranger = {"Pinning Strike", "Multishot", "Spirit Beast", "Vault"},
}

@(rodata)
ARCHETYPE_COLORS := [Archetype_Id][4]u8{
	.Warden = {235, 205, 120, 255}, .Rogue = {170, 230, 150, 255},
	.Arcanist = {120, 210, 255, 255}, .Acolyte = {220, 95, 140, 255},
	.Ranger = {150, 215, 105, 255},
}

// Values ported 1:1 from content/archetypes.py.
@(rodata)
ARCHETYPES := [Archetype_Id]Archetype_Def {
	.Warden = {
		name = "Warden",
		sprite = "warden",
		blurb = "Durable melee fighter with reliable armor and stamina.",
		max_hp = 120, max_mana = 38, max_stamina = 112,
		speed = 3.35, melee_bonus = 3, armor_bonus = 2,
	},
	.Rogue = {
		name = "Rogue",
		sprite = "rogue",
		blurb = "Fast striker who trades durability for speed and burst damage.",
		max_hp = 92, max_mana = 42, max_stamina = 126,
		speed = 3.95, melee_bonus = 5,
	},
	.Arcanist = {
		name = "Arcanist",
		sprite = "arcanist",
		blurb = "Fragile caster with stronger bolts and novas.",
		max_hp = 86, max_mana = 78, max_stamina = 94,
		speed = 3.25, spell_bonus = 9,
	},
	.Acolyte = {
		name = "Acolyte",
		sprite = "acolyte",
		blurb = "Dark priest with balanced defenses and potent rites.",
		max_hp = 102, max_mana = 62, max_stamina = 98,
		speed = 3.30, melee_bonus = 1, spell_bonus = 5, armor_bonus = 1,
	},
	.Ranger = {
		name = "Ranger",
		sprite = "ranger",
		blurb = "Mobile marksman with strong stamina and hybrid damage.",
		max_hp = 98, max_mana = 48, max_stamina = 120,
		speed = 3.70, melee_bonus = 3, spell_bonus = 2,
	},
}
