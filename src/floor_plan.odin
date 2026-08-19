package archrogue

// MX.4 — the authored descent plan, ported from run_flow.py / progression.py /
// enemies.py. One run modifier and a deterministic ten-depth Floor_Plan are
// rolled at run start on their own derived RNG stream; per-depth theme and
// darkness reuse the exact stream-3/stream-4 derivations the floor generator
// used before MX.4, so a given seed keeps its pre-plan floors and the darkness
// determinism guarantees hold. Raylib-free (hard rule 2).

import "core:fmt"

// --- Run modifiers (progression.py RUN_MODIFIERS) --------------------------

Run_Modifier_Id :: enum {
	Blood_Moon,
	Restless_Depths,
	Treasure_Draught,
	Trap_Laced,
	Thin_Veil,
	Starved_Depths,
	Elite_Hunt,
	Cursed_Bargains,
}

// pygame keys the extra effects off the modifier *name* at scattered call
// sites (population.py:1520-1527, :187, :1763); here they are explicit data.
// trap/shrine/secret pressure is carried now and wired when MX.5 lands the
// live trap/shrine/secret systems.
Run_Modifier :: struct {
	name:                  string,
	description:           string,
	enemy_hp_mult:         f32,
	enemy_damage_bonus:    int,
	enemy_aggro_bonus:     f32,
	loot_bonus:            f32,
	trap_bonus:            f32,
	elite_chance_bonus:    f32, // Elite Hunt
	miniboss_chance_bonus: f32, // Elite Hunt
	shrine_chance_bonus:   f32, // Trap-Laced (MX.5)
	curse_chance_bonus:    f32, // Cursed Bargains
}

@(rodata)
RUN_MODIFIERS := [Run_Modifier_Id]Run_Modifier{
	.Blood_Moon = {
		name = "Blood Moon",
		description = "Enemies are tougher and hit harder, but loot is richer.",
		enemy_hp_mult = 1.18, enemy_damage_bonus = 2, enemy_aggro_bonus = 1.0, loot_bonus = 0.07,
	},
	.Restless_Depths = {
		name = "Restless Depths",
		description = "More enemies wake from farther away.",
		enemy_hp_mult = 1.08, enemy_damage_bonus = 1, enemy_aggro_bonus = 2.0, loot_bonus = 0.02,
	},
	.Treasure_Draught = {
		name = "Treasure Draught",
		description = "The dungeon yields more equipment and rare caches.",
		enemy_hp_mult = 1.0, loot_bonus = 0.14,
	},
	.Trap_Laced = {
		name = "Trap-Laced",
		description = "Hazards are more common, but shrines answer more often.",
		enemy_hp_mult = 1.0, enemy_aggro_bonus = 0.5, loot_bonus = 0.05, trap_bonus = 0.16,
		shrine_chance_bonus = 0.08,
	},
	.Thin_Veil = {
		name = "Thin Veil",
		description = "The tyrant's guard is alert, but hidden caches are easier to find.",
		enemy_hp_mult = 1.06, enemy_damage_bonus = 1, enemy_aggro_bonus = 1.0, loot_bonus = 0.08, trap_bonus = 0.04,
	},
	.Starved_Depths = {
		name = "Starved Depths",
		description = "Loot is scarcer, but enemies are slightly weakened.",
		enemy_hp_mult = 0.92, enemy_damage_bonus = -1, enemy_aggro_bonus = -0.5, loot_bonus = -0.08,
	},
	.Elite_Hunt = {
		name = "Elite Hunt",
		description = "More elites and minibosses stalk the halls, carrying better spoils.",
		enemy_hp_mult = 1.10, enemy_damage_bonus = 1, enemy_aggro_bonus = 1.0, loot_bonus = 0.10, trap_bonus = 0.02,
		elite_chance_bonus = 0.08, miniboss_chance_bonus = 0.035,
	},
	.Cursed_Bargains = {
		name = "Cursed Bargains",
		description = "Cursed gear and risky events are more common, but rewards spike higher.",
		enemy_hp_mult = 1.04, enemy_aggro_bonus = 0.5, loot_bonus = 0.16, trap_bonus = 0.04,
		curse_chance_bonus = 0.08,
	},
}

// --- Encounter templates (enemies.py ENCOUNTER_TEMPLATES) ------------------

Encounter_Id :: enum {
	Standard,
	Elite_Pack,
	Ambush,
	Hazard_Cache,
	Treasure_Room,
	Challenge_Room,
}

Encounter_Template :: struct {
	title:               string,
	risk:                string,
	reward:              string,
	enemy_bonus:         int,
	elite_bonus:         f32,
	trap_bonus:          f32, // carried for MX.5
	loot_bonus:          f32,
	secret_bonus:        f32, // carried for MX.5
	guaranteed_miniboss: bool,
}

@(rodata)
ENCOUNTER_TEMPLATES := [Encounter_Id]Encounter_Template{
	.Standard = {
		title = "Hostile Patrols", risk = "mixed patrols", reward = "steady loot",
	},
	.Elite_Pack = {
		title = "Elite Pack", risk = "named elites with bright telegraphs", reward = "rare gear chance",
		enemy_bonus = 1, elite_bonus = 0.16, loot_bonus = 0.08,
	},
	.Ambush = {
		title = "Ruin Ambush", risk = "extra fast enemies near side doors", reward = "more XP",
		enemy_bonus = 2, elite_bonus = 0.05, trap_bonus = 0.06,
	},
	.Hazard_Cache = {
		title = "Hazard Cache", risk = "traps guard obvious rewards", reward = "extra cache odds",
		trap_bonus = 0.18, loot_bonus = 0.10, secret_bonus = 0.09,
	},
	.Treasure_Room = {
		title = "Treasure Room", risk = "tempting loot draws guardians", reward = "better loot",
		enemy_bonus = 1, elite_bonus = 0.08, loot_bonus = 0.22, secret_bonus = 0.08,
	},
	.Challenge_Room = {
		title = "Challenge Room", risk = "optional boss-marked room", reward = "class upgrade or rare gear",
		enemy_bonus = 1, elite_bonus = 0.12, loot_bonus = 0.14, guaranteed_miniboss = true,
	},
}

// --- The plan ---------------------------------------------------------------

MAX_RISK_TAGS :: 5

Floor_Plan :: struct {
	depth:        int, // 1-based, matches Run.depth
	theme_index:  int,
	threat_level: int,
	encounter:    Encounter_Id,
	risk_tags:    [MAX_RISK_TAGS]string, // static strings only
	risk_count:   int,
	reward_hint:  string,
	boss:         Boss_Id,
	has_boss:     bool,
	dark:         bool,
}

// Run-level plan stream: constant salt (like visuals' 0x4D495354 "MIST"),
// stream 9 per the core_rng allocation table.
FLOOR_PLAN_SALT :: 0x504C414E // "PLAN"
FLOOR_PLAN_STREAM :: 9

@(private = "file")
plan_add_risk :: proc(entry: ^Floor_Plan, tag: string) {
	// pygame truncates to the first five tags; appending past the cap is the
	// same as slicing at the end because tag order is fixed.
	if entry.risk_count >= MAX_RISK_TAGS do return
	entry.risk_tags[entry.risk_count] = tag
	entry.risk_count += 1
}

// Themed guardian pick (population.py via run_flow.py:255-262). Every theme is
// covered by exactly one non-final boss, so the draw is deterministic today;
// the roll stays for the day the roster gains overlapping haunts.
@(private = "file")
plan_boss_for_theme :: proc(rng: ^Pcg32, theme_index: int) -> Boss_Id {
	candidates: [4]Boss_Id
	count := 0
	for id in Boss_Id {
		def := BOSS_DEFS[id]
		if def.final_boss do continue
		if def.themes[0] == theme_index || def.themes[1] == theme_index {
			candidates[count] = id
			count += 1
		}
	}
	if count == 0 {
		for id in Boss_Id {
			if !BOSS_DEFS[id].final_boss {
				candidates[count] = id
				count += 1
			}
		}
	}
	return candidates[rng_below(rng, count)]
}

// run_flow.py generate_floor_plan: depth 1 standard, guardian depths 3/6/9
// authored challenge_room, every other depth (including 10) a uniform draw;
// threat = 1 + depth/2 (+1 on guardian depths), capped at 10.
generate_run_plan :: proc(seed: u64) -> (plan: [DUNGEON_DEPTH]Floor_Plan, modifier: Run_Modifier_Id) {
	plan_rng := rng_make(derive_seed(seed, FLOOR_PLAN_SALT), stream = FLOOR_PLAN_STREAM)
	modifier = Run_Modifier_Id(rng_below(&plan_rng, len(Run_Modifier_Id)))
	mod := RUN_MODIFIERS[modifier]

	previous_theme := -1
	for depth in 1 ..= DUNGEON_DEPTH {
		entry := &plan[depth - 1]
		entry.depth = depth

		// Theme (never repeating the previous floor, run_flow.py rule) and
		// darkness (depths 1-4 light, 5+ coin flip) keep their pre-MX.4
		// per-depth streams so recorded seeds replay identically.
		theme_rng := rng_make(derive_seed(seed, u64(depth)), stream = 4)
		if depth == 1 {
			entry.theme_index = rng_below(&theme_rng, len(THEMES))
		} else {
			pick := rng_below(&theme_rng, len(THEMES) - 1)
			if pick >= previous_theme do pick += 1
			entry.theme_index = pick
		}
		previous_theme = entry.theme_index
		dark_rng := rng_make(derive_seed(seed, u64(depth)), stream = 3)
		entry.dark = depth >= 5 && rng_chance(&dark_rng, 0.5)

		if depth == 1 {
			entry.encounter = .Standard
		} else if is_boss_depth(depth) && depth != DUNGEON_DEPTH {
			entry.encounter = .Challenge_Room
		} else {
			entry.encounter = Encounter_Id(rng_below(&plan_rng, len(Encounter_Id)))
		}
		encounter := ENCOUNTER_TEMPLATES[entry.encounter]
		threat := 1 + depth / 2

		// Tag order is authored (run_flow.py:239-266) and capped at five.
		plan_add_risk(entry, encounter.risk)
		if entry.dark do plan_add_risk(entry, "darkness")
		if depth >= 5 do plan_add_risk(entry, "escalating damage")
		if mod.trap_bonus > 0.08 || encounter.trap_bonus > 0.12 do plan_add_risk(entry, "heavy traps")
		if modifier == .Elite_Hunt || encounter.elite_bonus >= 0.12 do plan_add_risk(entry, "elite pressure")

		entry.reward_hint = encounter.reward
		if is_boss_depth(depth) {
			entry.has_boss = true
			if depth == DUNGEON_DEPTH {
				entry.boss = .Gate_Tyrant
				entry.reward_hint = "gate relic and clear record"
				plan_add_risk(entry, "final boss")
			} else {
				entry.boss = plan_boss_for_theme(&plan_rng, entry.theme_index)
				def := BOSS_DEFS[entry.boss]
				entry.reward_hint = def.loot_hook
				plan_add_risk(entry, def.subtitle)
				threat += 1
			}
		}
		entry.threat_level = min(10, threat)
	}
	return
}

// Current-depth plan entry; dev descend can push depth past the plan, so the
// last authored floor keeps answering.
run_floor_plan :: proc(run: ^Run) -> ^Floor_Plan {
	return &run.plan[clamp(run.depth, 1, DUNGEON_DEPTH) - 1]
}

// --- Player-facing text (models.py FloorPlan.preview / floor_plan_summary).
// Temp-allocator strings: compose each frame, never retain.

floor_plan_preview :: proc(plan: ^Floor_Plan) -> string {
	risks := plan.risk_count > 0 ? plan.risk_tags[0] : "unknown risks"
	for i in 1 ..< plan.risk_count {
		risks = fmt.tprintf("%s, %s", risks, plan.risk_tags[i])
	}
	out := fmt.tprintf("Threat %d: %s", plan.threat_level, risks)
	if plan.has_boss do out = fmt.tprintf("%s · boss sign", out)
	if plan.dark do out = fmt.tprintf("%s · dark level", out)
	if plan.reward_hint != "" do out = fmt.tprintf("%s · reward: %s", out, plan.reward_hint)
	return out
}

floor_plan_summary :: proc(plan: ^Floor_Plan) -> string {
	return fmt.tprintf("%s · %s", ENCOUNTER_TEMPLATES[plan.encounter].title, floor_plan_preview(plan))
}
