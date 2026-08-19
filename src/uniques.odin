package archrogue

// MX.5 — the 13 named unique items, ported from content/equipment.py
// UNIQUE_ITEM_DEFINITIONS. Authored flat stats (never rolled, never clamped by
// make_equipment's rolled-gear caps), three display affixes, a skill bonus,
// a proc rider, and one bespoke unique_effect hook wired across the combat
// procs. Raylib-free.

// Bespoke hooks; effect sites live in sim.odin / combat_depth.odin.
Unique_Effect :: enum u8 {
	None,
	Embers_On_Hit,     // +4 melee damage, ignite proc guaranteed
	Chill_On_Hit,      // chill proc guaranteed
	Steadfast_Bulwark, // +2 armor
	Oathwall_Aegis,    // +3 armor, +0.06 typed resistance (all channels)
	Counter_Smite,     // Warden riposte counter += max(3, level/2+2)
	Smoke_Crits,       // 30% crit at x1.80 while Smoke holds
	Vanish_On_Dash,    // dash grants 0.8s Smoke
	Splinter_Storm,    // bolt fan merges ±0.10
	Sky_Volley,        // bolt fan merges ±0.22
	Glacial_Ward,      // +0.15 frost resist; melee attackers chilled 1.2s
	Pack_Pursuit,      // melee attackers snared 1.0s
	Sanguine_Echo,     // +0.06 lifesteal
	Grave_Chorus,      // +2 thorns
}

// Display strings match the pygame unique_effect phrases.
@(rodata)
UNIQUE_EFFECT_NAMES := [Unique_Effect]string{
	.None = "",
	.Embers_On_Hit = "embers on hit",
	.Chill_On_Hit = "chill on hit",
	.Steadfast_Bulwark = "steadfast bulwark",
	.Oathwall_Aegis = "oathwall aegis",
	.Counter_Smite = "counter smite",
	.Smoke_Crits = "smoke crits",
	.Vanish_On_Dash = "vanish on dash",
	.Splinter_Storm = "splinter storm",
	.Sky_Volley = "sky volley",
	.Glacial_Ward = "glacial ward",
	.Pack_Pursuit = "pack pursuit",
	.Sanguine_Echo = "sanguine echo",
	.Grave_Chorus = "grave chorus",
}

Unique_Def :: struct {
	name:            string,
	icon:            string, // baked assets/world item key
	archetype:       Archetype_Id,
	any_archetype:   bool, // pygame "Any": excluded from the archetype pool
	slot:            Item_Kind,
	power:           int,
	defense:         int,
	affixes:         [3]Affix_Kind, // display identity; stats stay authored
	damage_type:     Damage_Type,
	typed:           bool,
	skill_bonus:     Skill_Bonus,
	has_skill_bonus: bool,
	proc_effect:     Proc_Effect,
	effect:          Unique_Effect,
	attack_speed:    f32,
	cast_speed:      f32,
	move_speed:      f32,
	thorns:          int,
	lifesteal:       f32,
	proc_chance:     f32,
}

// pygame "smite"/"smoke"/"snare" proc riders have no proc implementation in
// either engine; the matching bespoke unique_effect hooks carry those
// identities instead, so the proc field is .None here.
@(rodata)
UNIQUE_DEFS := [13]Unique_Def{
	{
		name = "Emberbrand", icon = "named.emberbrand", any_archetype = true,
		slot = .Weapon, power = 36,
		affixes = {.Serrated, .Of_Force, .Ember_Veined},
		damage_type = .Fire, typed = true,
		skill_bonus = .Melee_Force, has_skill_bonus = true,
		proc_effect = .Ignite, effect = .Embers_On_Hit,
		attack_speed = 0.05, proc_chance = 1.0,
	},
	{
		name = "Frostwake", icon = "named.frostwake", any_archetype = true,
		slot = .Weapon, power = 30,
		affixes = {.Frostbitten, .Balanced, .Of_The_Moon},
		damage_type = .Frost, typed = true,
		skill_bonus = .Bolt_Shard, has_skill_bonus = true,
		proc_effect = .Chill, effect = .Chill_On_Hit,
		attack_speed = 0.05, cast_speed = 0.05, proc_chance = 1.0,
	},
	{
		name = "Bulwark of the First Gate", icon = "named.bulwark_first_gate", any_archetype = true,
		slot = .Armor, defense = 24,
		affixes = {.Reinforced, .Of_Warding, .Thorned},
		damage_type = .Holy, typed = true,
		skill_bonus = .Dash_Guard, has_skill_bonus = true,
		proc_effect = .Thorns, effect = .Steadfast_Bulwark,
		thorns = 5,
	},
	{
		name = "Oathwall Carapace", icon = "named.oathwall_carapace", archetype = .Warden,
		slot = .Armor, defense = 27,
		affixes = {.Reinforced, .Thorned, .Of_Warding},
		damage_type = .Holy, typed = true,
		skill_bonus = .Time_Skip_Ward, has_skill_bonus = true,
		proc_effect = .Thorns, effect = .Oathwall_Aegis,
		thorns = 6,
	},
	{
		name = "Reckoner's Brand", icon = "named.reckoners_brand", archetype = .Warden,
		slot = .Weapon, power = 33,
		affixes = {.Zealous, .Of_Force, .Quickened},
		damage_type = .Holy, typed = true,
		skill_bonus = .Melee_Force, has_skill_bonus = true,
		effect = .Counter_Smite,
		attack_speed = 0.10, proc_chance = 0.45,
	},
	{
		name = "Nightglass Daggers", icon = "named.nightglass_daggers", archetype = .Rogue,
		slot = .Weapon, power = 30,
		affixes = {.Venomous, .Quickened, .Vampiric},
		damage_type = .Poison, typed = true,
		skill_bonus = .Melee_Tempo, has_skill_bonus = true,
		proc_effect = .Poison, effect = .Smoke_Crits,
		attack_speed = 0.16, move_speed = 0.04, lifesteal = 0.06, proc_chance = 0.60,
	},
	{
		name = "Foxstep Leathers", icon = "named.foxstep_leathers", archetype = .Rogue,
		slot = .Armor, defense = 15,
		affixes = {.Fleet, .Of_The_Fox, .Light},
		damage_type = .Physical,
		skill_bonus = .Ambush_Potency, has_skill_bonus = true,
		effect = .Vanish_On_Dash,
		attack_speed = 0.06, move_speed = 0.12, proc_chance = 0.35,
	},
	{
		name = "Splinter Star", icon = "named.splinter_star", archetype = .Arcanist,
		slot = .Weapon, power = 24,
		affixes = {.Storm_Touched, .Rune_Cut, .Of_Alacrity},
		damage_type = .Arcane, typed = true,
		skill_bonus = .Bolt_Shard, has_skill_bonus = true,
		proc_effect = .Chain, effect = .Splinter_Storm,
		cast_speed = 0.16, proc_chance = 0.55,
	},
	{
		name = "Blizzard Mantle", icon = "named.blizzard_mantle", archetype = .Arcanist,
		slot = .Armor, defense = 18,
		affixes = {.Focused, .Grounded, .Of_The_Moon},
		damage_type = .Frost, typed = true,
		skill_bonus = .Nova_Radius, has_skill_bonus = true,
		proc_effect = .Chill, effect = .Glacial_Ward,
		cast_speed = 0.12, proc_chance = 0.45,
	},
	{
		name = "Blood Psalm", icon = "named.blood_psalm", archetype = .Acolyte,
		slot = .Weapon, power = 27,
		affixes = {.Grave_Hungering, .Of_Siphons, .Of_The_Occult},
		damage_type = .Shadow, typed = true,
		skill_bonus = .Blood_Leech, has_skill_bonus = true,
		proc_effect = .Lifesteal, effect = .Sanguine_Echo,
		cast_speed = 0.07, lifesteal = 0.14,
	},
	{
		name = "Choir of Bone", icon = "named.choir_of_bone", archetype = .Acolyte,
		slot = .Armor, defense = 18,
		affixes = {.Hexwoven, .Of_Siphons, .Mirror_Barbed},
		damage_type = .Shadow, typed = true,
		skill_bonus = .Spirit_Call_Ward, has_skill_bonus = true,
		proc_effect = .Thorns, effect = .Grave_Chorus,
		cast_speed = 0.08, thorns = 4, lifesteal = 0.05,
	},
	{
		name = "Skyfang Bow", icon = "named.skyfang_bow", archetype = .Ranger,
		slot = .Weapon, power = 30,
		affixes = {.Quickened, .Of_The_Hunt, .Serrated},
		damage_type = .Physical,
		skill_bonus = .Bolt_Shard, has_skill_bonus = true,
		proc_effect = .Bleed, effect = .Sky_Volley,
		attack_speed = 0.14, move_speed = 0.05, proc_chance = 0.45,
	},
	{
		name = "Beastlord Harness", icon = "named.beastlord_harness", archetype = .Ranger,
		slot = .Armor, defense = 18,
		affixes = {.Fleet, .Of_The_Hunt, .Of_Thorns},
		damage_type = .Physical,
		skill_bonus = .Spirit_Beast_Bond, has_skill_bonus = true,
		effect = .Pack_Pursuit,
		move_speed = 0.11, thorns = 3, proc_chance = 0.35,
	},
}

// Rolled gear hard caps keep every unique a strict upgrade (equipment.py:669);
// unique armor waits for depth 4 so its 15-27 defense cannot trivialize the
// surface floors (UNIQUE_ARMOR_MIN_DEPTH).
UNIQUE_ARMOR_MIN_DEPTH :: 4

make_unique_from_def :: proc(rng: ^Pcg32, def: ^Unique_Def) -> Item {
	item := Item{
		kind = def.slot,
		name = def.name,
		icon = def.icon,
		rarity = .Unique,
		power = def.power,
		defense = def.defense,
		attack_speed = def.attack_speed,
		cast_speed = def.cast_speed,
		move_speed = def.move_speed,
		thorns = def.thorns,
		lifesteal = def.lifesteal,
		proc_chance = def.proc_chance,
		damage_type = def.damage_type,
		typed = def.typed,
		proc_effect = def.proc_effect,
		unique_effect = def.effect,
		affix_count = 3,
		unidentified = rng_chance(rng, 0.35),
	}
	for kind, i in def.affixes do item.affixes[i] = {kind}
	if def.has_skill_bonus do item.skill_bonuses[def.skill_bonus] = true
	if def.proc_effect != .None do item.proc_effects[def.proc_effect] = true
	return item
}

// population.py _make_unique: floors 1-3 draw weapons only; a matching
// archetype unique wins 72% of draws when one exists.
make_unique :: proc(rng: ^Pcg32, archetype: Archetype_Id, depth: int) -> Item {
	pool: [len(UNIQUE_DEFS)]int
	pool_count := 0
	archetype_pool: [len(UNIQUE_DEFS)]int
	archetype_count := 0
	for &def, i in UNIQUE_DEFS {
		if depth < UNIQUE_ARMOR_MIN_DEPTH && def.slot == .Armor do continue
		pool[pool_count] = i
		pool_count += 1
		if !def.any_archetype && def.archetype == archetype {
			archetype_pool[archetype_count] = i
			archetype_count += 1
		}
	}
	// Same draw shape on both branches (one f32 + one pick), like pygame.
	bias := rng_f32(rng)
	index: int
	if archetype_count > 0 && bias < 0.72 {
		index = archetype_pool[rng_below(rng, archetype_count)]
	} else {
		index = pool[rng_below(rng, pool_count)]
	}
	return make_unique_from_def(rng, &UNIQUE_DEFS[index])
}

// Kill-reward placement (population.py drop_position_near): deterministic
// first-fit ring that avoids the stairs mouth and blocked tiles.
drop_position_near :: proc(run: ^Run, origin: Vec2) -> Vec2 {
	offsets := [9]Vec2{
		{0, 0}, {1.15, 0}, {-1.15, 0}, {0, 1.15}, {0, -1.15},
		{1.15, 1.15}, {-1.15, 1.15}, {1.15, -1.15}, {-1.15, -1.15},
	}
	stairs := Vec2{f32(run.dungeon.stairs.x) + 0.5, f32(run.dungeon.stairs.y) + 0.5}
	for offset in offsets {
		pos := origin + offset
		delta := pos - stairs
		if delta.x * delta.x + delta.y * delta.y < 1.05 * 1.05 do continue
		if blocked_for_radius(&run.dungeon, pos.x, pos.y, 0.22) do continue
		return pos
	}
	return origin
}

// Notable loot: a deduplicated ring of the run's best finds (run_flow.py
// record_notable_loot, ring of 8, last three shown in the summaries).
MAX_NOTABLE_LOOT :: 8

Notable_Loot :: struct {
	rarity: Rarity,
	item_id: string, // stable icon/content key; name is the bounded fallback
	name:    string, // static content string
}

record_notable_loot :: proc(run: ^Run, item: Item) {
	if run == nil do return
	interesting := item.cursed
	#partial switch item.rarity {
	case .Rare, .Unique, .Legendary, .Cursed: interesting = true
	}
	if !interesting do return
	if item.rarity==.Unique||item.rarity==.Legendary do run.critical_save_requested=true
	// Recorded by true identity (pygame's unidentified-label quirk would
	// store "Unidentified Unidentified Weapon"; the reconciled ledger keeps
	// the real find).
	item_id := item.icon
	if item_id == "" do item_id = item.name
	entry := Notable_Loot{rarity = item.rarity, item_id = item_id, name = item.name}
	for i in 0 ..< run.notable_count {
		if run.notable_loot[i] == entry do return
	}
	if run.notable_count < MAX_NOTABLE_LOOT {
		run.notable_loot[run.notable_count] = entry
		run.notable_count += 1
		return
	}
	for i in 0 ..< MAX_NOTABLE_LOOT - 1 do run.notable_loot[i] = run.notable_loot[i + 1]
	run.notable_loot[MAX_NOTABLE_LOOT - 1] = entry
}
