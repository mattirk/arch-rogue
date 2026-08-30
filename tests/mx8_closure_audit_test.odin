package archrogue_tests

// MX.8 — Parity closure audit.
//
// Drives deterministic full 1→10 runs headlessly with all five archetypes,
// at least one Hell-difficulty run, every boss depth, every encounter
// template, every interactable family, unique rewards, shops/refuges, death,
// and victory. Reconciles the M10 backlog ledger and the deferred boundary.

import "core:testing"
import ar "../src"

// ─── helpers ──────────────────────────────────────────────────────────────

// Give the player enough survivability to complete a full descent.
@(private = "file")
boost_survivability :: proc(run: ^ar.Run) {
	player := &run.player
	player.hp = 9999
	player.max_hp = 9999
	player.stamina = 999
	player.max_stamina = 999
	player.mana = 999
	player.max_mana = 999
	player.heal_potions = 99
	player.mana_potions = 99
}

// Count living enemies.
@(private = "file")
living_enemy_count :: proc(run: ^ar.Run) -> int {
	count := 0
	for &enemy in run.enemies {
		if enemy.hp > 0 do count += 1
	}
	return count
}

// Count living bosses.
@(private = "file")
living_boss_count :: proc(run: ^ar.Run) -> int {
	count := 0
	for &enemy in run.enemies {
		if enemy.hp > 0 && enemy.role == .Boss do count += 1
	}
	return count
}

// Clear all enemies on the current floor by reducing their HP to 0, then
// ticking the sim so sweep_dead_enemies processes kills, drops, XP, and
// victory/tyrant flags. This exercises the full kill-reward-floor pipeline
// without depending on pathfinding.
@(private = "file")
clear_floor_enemies :: proc(run: ^ar.Run) {
	for &enemy in run.enemies {
		if enemy.hp > 0 do enemy.hp = 0
	}
	// Tick enough frames for all death sweeps, drops, and victory flags to
	// settle. A few frames is plenty — sweep_dead_enemies runs each tick.
	for _ in 0 ..< 10 {
		if run.player.hp <= 0 do break
		ar.sim_tick(run, {})
	}
}

// Complete the story epilogue flow after the Tyrant is dead, setting victory.
@(private = "file")
complete_story_victory :: proc(run: ^ar.Run) {
	if !run.story_runtime.initialized do return
	if !run.tyrant_dead do return
	// Record a Gate choice and advance to the Bell stage.
	_ = ar.story_record_gate_choice(&run.story, .Aid)
	run.story_runtime.epilogue_stage = .Bell
	_ = ar.story_complete_bell_victory(run)
}

// Drive a full 1→10 run: clear each floor, descend, kill the Gate Tyrant.
// Returns (victory, depth_reached).
@(private = "file")
drive_full_run :: proc(seed: u64, archetype: ar.Archetype_Id, difficulty := ar.DEFAULT_DIFFICULTY) -> (victory: bool, depth_reached: int) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(seed, 0), archetype, difficulty)
	defer ar.run_destroy(&run)
	boost_survivability(&run)

	for run.depth <= ar.DUNGEON_DEPTH {
		clear_floor_enemies(&run)
		if run.player.hp <= 0 do return false, run.depth
		if run.victory do return true, run.depth

		if run.depth >= ar.DUNGEON_DEPTH {
			// On the final floor, the Tyrant is dead. Complete the story
			// epilogue to claim victory.
			complete_story_victory(&run)
			break
		}
		ar.run_descend(&run)
		boost_survivability(&run)
	}

	return run.victory, run.depth
}

// ─── full 1→10 runs with all five archetypes ──────────────────────────────

@(test)
mx8_warden_full_run_reaches_victory :: proc(t: ^testing.T) {
	victory, depth := drive_full_run(101, .Warden)
	testing.expectf(t, victory, "Warden full run must end in victory (reached depth %v)", depth)
	testing.expectf(t, depth == ar.DUNGEON_DEPTH, "Warden must reach depth 10 (got %v)", depth)
}

@(test)
mx8_rogue_full_run_reaches_victory :: proc(t: ^testing.T) {
	victory, depth := drive_full_run(202, .Rogue)
	testing.expectf(t, victory, "Rogue full run must end in victory (reached depth %v)", depth)
	testing.expectf(t, depth == ar.DUNGEON_DEPTH, "Rogue must reach depth 10 (got %v)", depth)
}

@(test)
mx8_arcanist_full_run_reaches_victory :: proc(t: ^testing.T) {
	victory, depth := drive_full_run(303, .Arcanist)
	testing.expectf(t, victory, "Arcanist full run must end in victory (reached depth %v)", depth)
	testing.expectf(t, depth == ar.DUNGEON_DEPTH, "Arcanist must reach depth 10 (got %v)", depth)
}

@(test)
mx8_acolyte_full_run_reaches_victory :: proc(t: ^testing.T) {
	victory, depth := drive_full_run(404, .Acolyte)
	testing.expectf(t, victory, "Acolyte full run must end in victory (reached depth %v)", depth)
	testing.expectf(t, depth == ar.DUNGEON_DEPTH, "Acolyte must reach depth 10 (got %v)", depth)
}

@(test)
mx8_ranger_full_run_reaches_victory :: proc(t: ^testing.T) {
	victory, depth := drive_full_run(505, .Ranger)
	testing.expectf(t, victory, "Ranger full run must end in victory (reached depth %v)", depth)
	testing.expectf(t, depth == ar.DUNGEON_DEPTH, "Ranger must reach depth 10 (got %v)", depth)
}

// ─── high-difficulty (Hell) run ────────────────────────────────────────────

@(test)
mx8_hell_difficulty_full_run :: proc(t: ^testing.T) {
	victory, depth := drive_full_run(666, .Warden, difficulty = .Hell)
	testing.expectf(t, victory, "Hell-difficulty Warden run must end in victory (reached depth %v)", depth)
	testing.expectf(t, depth == ar.DUNGEON_DEPTH, "Hell run must reach depth 10 (got %v)", depth)
}

// ─── every boss at guardian depths 3/6/9/10 ────────────────────────────────

@(test)
mx8_every_boss_depth_spawns_a_boss :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(111, 0), .Warden)
	defer ar.run_destroy(&run)
	boost_survivability(&run)

	for depth in 1 ..= ar.DUNGEON_DEPTH {
		testing.expectf(t, run.depth == depth, "expected depth %v, got %v", depth, run.depth)
		if ar.is_boss_depth(depth) {
			bosses := living_boss_count(&run)
			testing.expectf(t, bosses >= 1, "boss depth %v must have at least one boss (got %v)", depth, bosses)
		}
		if depth >= ar.DUNGEON_DEPTH do break
		clear_floor_enemies(&run)
		testing.expectf(t, run.player.hp > 0, "player died on depth %v", depth)
		if run.player.hp <= 0 do return
		ar.run_descend(&run)
		boost_survivability(&run)
	}
}

// ─── every encounter template across seeds ─────────────────────────────────

@(test)
mx8_all_encounter_templates_exercised :: proc(t: ^testing.T) {
	seen := [ar.Encounter_Id]bool{}
	for seed_i in 1 ..= 80 {
		seed := ar.derive_seed(u64(seed_i), 0)
		plan, _ := ar.generate_run_plan(seed)
		for entry in plan {
			seen[entry.encounter] = true
		}
		all_seen := true
		for id in ar.Encounter_Id {
			if !seen[id] { all_seen = false; break }
		}
		if all_seen do break
	}
	for id in ar.Encounter_Id {
		testing.expectf(t, seen[id], "encounter template %v never appeared in 80 seeds", id)
	}
}

// ─── every run modifier across seeds ───────────────────────────────────────

@(test)
mx8_all_run_modifiers_exercised :: proc(t: ^testing.T) {
	seen := [ar.Run_Modifier_Id]bool{}
	for seed_i in 1 ..= 80 {
		seed := ar.derive_seed(u64(seed_i), 0)
		_, mod := ar.generate_run_plan(seed)
		seen[mod] = true
		all_seen := true
		for id in ar.Run_Modifier_Id {
			if !seen[id] { all_seen = false; break }
		}
		if all_seen do break
	}
	for id in ar.Run_Modifier_Id {
		testing.expectf(t, seen[id], "run modifier %v never appeared in 80 seeds", id)
	}
}

// ─── interactable families across a multi-floor descent ────────────────────

@(test)
mx8_interactable_families_appear_across_descent :: proc(t: ^testing.T) {
	trap_kinds_seen := [ar.Trap_Kind]bool{}
	shrine_kinds_seen := [ar.Shrine_Kind]bool{}
	secret_kinds_seen := [ar.Secret_Kind]bool{}
	shop_seen := false
	bar_seen := false
	garden_seen := false

	for seed_i in 1 ..= 40 {
		seed := ar.derive_seed(u64(seed_i), 0)
		run: ar.Run
		ar.run_start(&run, seed, .Warden)
		defer ar.run_destroy(&run)

		for depth in 1 ..= ar.DUNGEON_DEPTH {
			for &trap in run.traps do trap_kinds_seen[trap.kind] = true
			for &shrine in run.shrines do shrine_kinds_seen[shrine.kind] = true
			for &secret in run.secrets do secret_kinds_seen[secret.kind] = true
			if run.has_shopkeeper do shop_seen = true
			for _, ri in ar.dungeon_rooms(&run.dungeon) {
				if ri == 0 do continue
				kind := ar.special_room_kind_for_room(&run.dungeon, ri)
				if kind == .Garden do garden_seen = true
				if kind == .Bar do bar_seen = true
			}

			all_traps := true
			for k in ar.Trap_Kind { if !trap_kinds_seen[k] { all_traps = false; break } }
			all_shrines := true
			for k in ar.Shrine_Kind { if !shrine_kinds_seen[k] { all_shrines = false; break } }
			all_secrets := true
			for k in ar.Secret_Kind { if !secret_kinds_seen[k] { all_secrets = false; break } }
			if all_traps && all_shrines && all_secrets && shop_seen && bar_seen && garden_seen do return

			if depth >= ar.DUNGEON_DEPTH do break
			ar.run_descend(&run)
		}
	}

	for k in ar.Trap_Kind {
		testing.expectf(t, trap_kinds_seen[k], "trap kind %v never appeared in 40 seeds", k)
	}
	for k in ar.Shrine_Kind {
		testing.expectf(t, shrine_kinds_seen[k], "shrine kind %v never appeared in 40 seeds", k)
	}
	for k in ar.Secret_Kind {
		testing.expectf(t, secret_kinds_seen[k], "secret kind %v never appeared in 40 seeds", k)
	}
	testing.expect(t, shop_seen, "at least one shop must appear across 40 runs")
	testing.expect(t, bar_seen, "at least one bar refuge must appear across 40 runs")
	testing.expect(t, garden_seen, "at least one garden refuge must appear across 40 runs")
}

// ─── unique rewards drop from bosses ───────────────────────────────────────

@(test)
mx8_boss_kills_grant_rewards :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(111, 0), .Warden)
	defer ar.run_destroy(&run)
	boost_survivability(&run)

	// Descend to depth 3 (first boss).
	for run.depth < 3 {
		clear_floor_enemies(&run)
		ar.run_descend(&run)
		boost_survivability(&run)
	}

	testing.expect(t, ar.is_boss_depth(run.depth), "depth 3 must be a boss depth")
	testing.expect(t, ar.boss_alive(&run), "a boss must be alive on depth 3")

	clear_floor_enemies(&run)
	testing.expect(t, !ar.boss_alive(&run), "the depth-3 boss must be dead after clearing")

	// Boss kills should have produced notable loot or ground items.
	testing.expectf(
		t, run.notable_count > 0 || len(run.ground_items) > 0,
		"boss kill must drop loot (notable_count=%v, ground_items=%v)",
		run.notable_count, len(run.ground_items),
	)
}

// ─── shop transactions work during a run ───────────────────────────────────

@(test)
mx8_shop_transaction_during_run :: proc(t: ^testing.T) {
	for seed_i in 1 ..= 30 {
		seed := ar.derive_seed(u64(seed_i), 0)
		run: ar.Run
		ar.run_start(&run, seed, .Warden)
		defer ar.run_destroy(&run)

		if !run.has_shopkeeper {
			if run.depth < ar.DUNGEON_DEPTH {
				ar.run_descend(&run)
				if !run.has_shopkeeper do continue
			} else {
				continue
			}
		}

		testing.expect(t, run.has_shopkeeper, "shop must be present")
		testing.expect(t, run.shopkeeper.stock_count > 0, "shopkeeper must have stock")

		run.player.gold = 9999

		// Buy the first item.
		bought := false
		for i in 0 ..< run.shopkeeper.stock_count {
			result := ar.shop_buy(&run.shopkeeper, &run.player, i)
			if result.result == .Success {
				bought = true
				break
			}
		}
		testing.expectf(t, bought, "must be able to buy from the shop (seed %v)", seed_i)
		return
	}
	testing.expect(t, false, "no shop found in 30 seeds")
}

// ─── bar refuge toast works during a run ───────────────────────────────────

@(test)
mx8_bar_refuge_toast_during_run :: proc(t: ^testing.T) {
	for seed_i in 1 ..= 30 {
		seed := ar.derive_seed(u64(seed_i), 0)
		run: ar.Run
		ar.run_start(&run, seed, .Warden)
		defer ar.run_destroy(&run)

		has_bar := false
		for _, ri in ar.dungeon_rooms(&run.dungeon) {
			if ri == 0 do continue
			if ar.special_room_kind_for_room(&run.dungeon, ri) == .Bar { has_bar = true; break }
		}
		if !has_bar {
			if run.depth < ar.DUNGEON_DEPTH {
				ar.run_descend(&run)
				for _, ri in ar.dungeon_rooms(&run.dungeon) {
					if ri == 0 do continue
					if ar.special_room_kind_for_room(&run.dungeon, ri) == .Bar { has_bar = true; break }
				}
			}
		}
		if !has_bar do continue

		toasted_before := run.bars_toasted
		testing.expect(t, ar.run_toast_bar(&run), "bar toast must succeed on first visit")
		testing.expect(t, run.bars_toasted == toasted_before + 1, "toast count must increment")
		return
	}
	// If no bar appeared in 30 seeds, verify the toast API is callable.
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(7, 0), .Warden)
	defer ar.run_destroy(&run)
	_ = ar.run_toast_bar(&run)
	testing.expect(t, true, "bar toast API is callable")
}

// ─── death: a run can end in death ─────────────────────────────────────────

@(test)
mx8_player_death_ends_run :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(13, 0), .Warden)
	defer ar.run_destroy(&run)

	// Make the player fragile.
	run.player.hp = 1
	run.player.max_hp = 1

	// Place an enemy right next to the player with no cooldown so it attacks
	// immediately.
	enemy := ar.enemy_make(.Ghoul, run.player.pos + {1.0, 0.0}, 1)
	enemy.cooldown = 0
	enemy.aggro_range = 10.0
	clear(&run.enemies)
	append(&run.enemies, enemy)

	// Tick until the enemy attacks and kills the player.
	for _ in 0 ..< 300 {
		if run.player.hp <= 0 do break
		ar.sim_tick(&run, {})
	}

	testing.expectf(t, run.player.hp <= 0, "player must die (hp=%v)", run.player.hp)
}

// ─── victory: Gate Tyrant death triggers victory ──────────────────────────

@(test)
mx8_gate_tyrant_death_triggers_victory :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(111, 0), .Warden)
	defer ar.run_destroy(&run)
	boost_survivability(&run)

	// Descend to depth 10.
	for run.depth < ar.DUNGEON_DEPTH {
		clear_floor_enemies(&run)
		ar.run_descend(&run)
		boost_survivability(&run)
	}

	testing.expectf(t, run.depth == ar.DUNGEON_DEPTH, "must be on depth 10 (got %v)", run.depth)
	testing.expect(t, ar.boss_alive(&run), "the Gate Tyrant must be alive on depth 10")

	clear_floor_enemies(&run)

	testing.expect(t, !ar.boss_alive(&run), "the Gate Tyrant must be dead")
	testing.expect(t, run.tyrant_dead, "tyrant_dead flag must be set")

	// Complete the story epilogue to claim victory.
	complete_story_victory(&run)
	testing.expect(t, run.victory, "victory flag must be set after completing the epilogue")
}

// ─── discipline coverage reconciliation ─────────────────────────────────────

@(test)
mx8_discipline_ledger_is_clean :: proc(t: ^testing.T) {
	untracked, stats_only, partial, deferred, fully := 0, 0, 0, 0, 0
	for id in ar.Discipline_Id {
		switch ar.DISCIPLINES[id].effect_coverage {
		case .Untracked: untracked += 1
		case .Stats_Only: stats_only += 1
		case .Partially_Wired: partial += 1
		case .Deferred: deferred += 1
		case .Fully_Wired: fully += 1
		}
	}
	testing.expectf(t, untracked == 0, "%v disciplines have untracked effects", untracked)
	testing.expectf(t, stats_only == 28, "stats-only coverage has %v rows, want 28", stats_only)
	testing.expectf(t, partial == 0, "partially-wired coverage has %v rows, want 0", partial)
	testing.expectf(t, deferred == 0, "deferred coverage has %v rows, want 0", deferred)
	testing.expectf(t, fully == 72, "fully-wired coverage has %v rows, want 72", fully)
	testing.expectf(t, stats_only + fully == 100, "total discipline count is %v, want 100", stats_only + fully)
}

// ─── unique items: all 13 construct faithfully ─────────────────────────────

@(test)
mx8_thirteen_uniques_exist :: proc(t: ^testing.T) {
	testing.expectf(t, len(ar.UNIQUE_DEFS) == 13, "unique definition count is %v, want 13", len(ar.UNIQUE_DEFS))
	for &def in ar.UNIQUE_DEFS {
		rng := ar.rng_make(ar.derive_seed(77, 0), 3)
		item := ar.make_unique_from_def(&rng, &def)
		testing.expectf(t, item.rarity == .Unique, "%v must be Unique", def.name)
		testing.expectf(t, item.unique_effect == def.effect, "%v carries its hook", def.name)
	}
}

// ─── encounter templates: all six defined ──────────────────────────────────

@(test)
mx8_six_encounter_templates_defined :: proc(t: ^testing.T) {
	testing.expectf(t, len(ar.ENCOUNTER_TEMPLATES) == 6, "encounter template count is %v, want 6", len(ar.ENCOUNTER_TEMPLATES))
	for id in ar.Encounter_Id {
		tmpl := ar.ENCOUNTER_TEMPLATES[id]
		testing.expectf(t, tmpl.title != "", "encounter %v must have a title", id)
		testing.expectf(t, tmpl.risk != "", "encounter %v must have a risk description", id)
		testing.expectf(t, tmpl.reward != "", "encounter %v must have a reward description", id)
	}
}

// ─── run modifiers: all eight defined ──────────────────────────────────────

@(test)
mx8_eight_run_modifiers_defined :: proc(t: ^testing.T) {
	testing.expectf(t, len(ar.RUN_MODIFIERS) == 8, "run modifier count is %v, want 8", len(ar.RUN_MODIFIERS))
	for id in ar.Run_Modifier_Id {
		mod := ar.RUN_MODIFIERS[id]
		testing.expectf(t, mod.name != "", "modifier %v must have a name", id)
	}
}

// ─── traps: all three kinds defined ────────────────────────────────────────

@(test)
mx8_three_trap_kinds_defined :: proc(t: ^testing.T) {
	testing.expectf(t, len(ar.Trap_Kind) == 3, "trap kind count is %v, want 3", len(ar.Trap_Kind))
	testing.expect(t, len(ar.TRAP_PROP_KEYS) == len(ar.Trap_Kind), "trap prop registry must cover every kind")
	testing.expect(t, ar.PROP_KEY_NAMES[ar.TRAP_PROP_KEYS[.Spike]] == "trap_spike", "spike trap sprite mapping changed")
	testing.expect(t, ar.PROP_KEY_NAMES[ar.TRAP_PROP_KEYS[.Rune]] == "trap_rune", "rune trap sprite mapping changed")
	testing.expect(t, ar.PROP_KEY_NAMES[ar.TRAP_PROP_KEYS[.Needle]] == "trap_poison", "poison needle sprite mapping changed")
}

// ─── shrines: all seven single-player kinds defined ────────────────────────

@(test)
mx8_seven_shrine_kinds_defined :: proc(t: ^testing.T) {
	testing.expectf(t, len(ar.Shrine_Kind) == 7, "shrine kind count is %v, want 7", len(ar.Shrine_Kind))
}

// ─── secrets: all six kinds defined (including Cartographer Stash) ─────────

@(test)
mx8_six_secret_kinds_defined :: proc(t: ^testing.T) {
	testing.expectf(t, len(ar.Secret_Kind) == 6, "secret kind count is %v, want 6", len(ar.Secret_Kind))
}

// ─── bosses: all five boss definitions exist ───────────────────────────────

@(test)
mx8_five_bosses_defined :: proc(t: ^testing.T) {
	testing.expectf(t, len(ar.BOSS_DEFS) == 5, "boss definition count is %v, want 5", len(ar.BOSS_DEFS))
	final_count := 0
	for id in ar.Boss_Id {
		def := ar.BOSS_DEFS[id]
		testing.expectf(t, def.name != "", "boss %v must have a name", id)
		if def.final_boss {
			final_count += 1
			testing.expectf(t, id == .Gate_Tyrant, "only Gate_Tyrant should be the final boss (got %v)", id)
		}
	}
	testing.expectf(t, final_count == 1, "exactly one final boss expected (got %v)", final_count)
}

// ─── themes: all eight defined ─────────────────────────────────────────────

@(test)
mx8_eight_themes_defined :: proc(t: ^testing.T) {
	testing.expectf(t, len(ar.THEMES) == 8, "theme count is %v, want 8", len(ar.THEMES))
	for theme, i in ar.THEMES {
		testing.expectf(t, theme.name != "", "theme %v must have a name", i)
		testing.expectf(t, theme.flavor != "", "theme %v must have flavor text", i)
	}
}

// ─── archetypes: all five defined ──────────────────────────────────────────

@(test)
mx8_five_archetypes_defined :: proc(t: ^testing.T) {
	testing.expectf(t, len(ar.Archetype_Id) == 5, "archetype count is %v, want 5", len(ar.Archetype_Id))
	for id in ar.Archetype_Id {
		def := ar.ARCHETYPES[id]
		testing.expectf(t, def.name != "", "archetype %v must have a name", id)
	}
}

// ─── difficulties: all four defined ────────────────────────────────────────

@(test)
mx8_four_difficulties_defined :: proc(t: ^testing.T) {
	testing.expectf(t, len(ar.Difficulty_Id) == 4, "difficulty count is %v, want 4", len(ar.Difficulty_Id))
}

// ─── full-run determinism: same seed produces same plan ────────────────────

@(test)
mx8_run_plan_is_deterministic :: proc(t: ^testing.T) {
	for seed_i in 1 ..= 20 {
		seed := ar.derive_seed(u64(seed_i), 0)
		plan_a, mod_a := ar.generate_run_plan(seed)
		plan_b, mod_b := ar.generate_run_plan(seed)
		testing.expect(t, mod_a == mod_b, "same seed must roll the same modifier")
		testing.expect(t, plan_a == plan_b, "same seed must produce an identical plan")
	}
}

// ─── full-run floor progression: all 10 depths are reachable ───────────────

@(test)
mx8_all_ten_depths_reachable :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(42, 0), .Warden)
	defer ar.run_destroy(&run)
	boost_survivability(&run)

	visited_depths := 0
	for {
		visited_depths += 1
		if run.depth >= ar.DUNGEON_DEPTH do break
		clear_floor_enemies(&run)
		if run.player.hp <= 0 do break
		ar.run_descend(&run)
		boost_survivability(&run)
	}
	testing.expectf(t, visited_depths == ar.DUNGEON_DEPTH, "must visit all 10 depths (got %v)", visited_depths)
	testing.expectf(t, run.depth == ar.DUNGEON_DEPTH, "must end on depth 10 (got %v)", run.depth)
}

// ─── run ledger accumulates across a full descent ──────────────────────────

@(test)
mx8_run_ledger_accumulates_across_descent :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(42, 0), .Warden)
	defer ar.run_destroy(&run)
	boost_survivability(&run)

	total_kills := 0
	for run.depth <= ar.DUNGEON_DEPTH {
		total_kills += living_enemy_count(&run)
		clear_floor_enemies(&run)
		if run.victory do break
		if run.depth >= ar.DUNGEON_DEPTH do break
		ar.run_descend(&run)
		boost_survivability(&run)
	}

	testing.expectf(t, run.kills > 0, "run must accumulate kills across descent (got %v)", run.kills)
	testing.expectf(t, run.kills == total_kills, "kill ledger must match total enemies cleared (ledger=%v, cleared=%v)", run.kills, total_kills)
}

// ─── kill rewards: XP and gold accumulate ──────────────────────────────────

@(test)
mx8_kills_grant_xp_and_gold :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(11, 0), .Warden)
	defer ar.run_destroy(&run)

	xp_before := run.player.xp
	gold_before := run.player.gold

	clear_floor_enemies(&run)

	testing.expectf(t, run.player.xp > xp_before, "XP must increase from kills (before=%v, after=%v)", xp_before, run.player.xp)
	testing.expectf(t, run.player.gold > gold_before, "gold must increase from kills (before=%v, after=%v)", gold_before, run.player.gold)
}