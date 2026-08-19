package archrogue_tests

// MX.4 — descent plan, encounters, and floor-to-floor pressure.

import "core:strings"
import "core:testing"
import ar "../src"

@(test)
floor_plan_is_deterministic_and_authored :: proc(t: ^testing.T) {
	for seed_i in 1 ..= 12 {
		seed := ar.derive_seed(u64(seed_i), 0)
		plan_a, mod_a := ar.generate_run_plan(seed)
		plan_b, mod_b := ar.generate_run_plan(seed)
		testing.expect(t, mod_a == mod_b, "same seed must roll the same run modifier")
		testing.expect(t, plan_a == plan_b, "same seed must produce an identical plan")

		testing.expect(t, plan_a[0].encounter == .Standard, "depth 1 is always standard")
		for depth in 1 ..= ar.DUNGEON_DEPTH {
			entry := plan_a[depth - 1]
			testing.expectf(t, entry.depth == depth, "plan entry %v carries depth %v", depth, entry.depth)
			if depth > 1 {
				testing.expectf(
					t, entry.theme_index != plan_a[depth-2].theme_index,
					"adjacent floors must not repeat a theme (seed %v depth %v)", seed_i, depth,
				)
			}
			if depth < 5 do testing.expect(t, !entry.dark, "depths 1-4 are always light")
			testing.expect(t, entry.has_boss == ar.is_boss_depth(depth), "boss sign must match the guardian depths")
			testing.expect(t, entry.risk_count >= 1 && entry.risk_count <= ar.MAX_RISK_TAGS, "risk tags stay within 1..5")
			// run_flow.py: threat = 1 + depth//2, +1 on guardian depths 3/6/9
			// (never 10), capped at 10.
			expected_threat := 1 + depth / 2
			if entry.has_boss && depth != ar.DUNGEON_DEPTH do expected_threat += 1
			testing.expectf(t, entry.threat_level == min(10, expected_threat), "threat at depth %v is %v", depth, entry.threat_level)
			if depth == 3 || depth == 6 || depth == 9 {
				testing.expect(t, entry.encounter == .Challenge_Room, "guardian depths are authored challenge rooms")
				def := ar.BOSS_DEFS[entry.boss]
				testing.expect(t, !def.final_boss, "guardian depths never draw the Tyrant")
				testing.expect(
					t, def.themes[0] == entry.theme_index || def.themes[1] == entry.theme_index,
					"guardians haunt their floor's theme",
				)
				testing.expect(t, entry.reward_hint == def.loot_hook, "guardian reward hint is the boss loot hook")
			}
		}
		final := plan_a[ar.DUNGEON_DEPTH - 1]
		testing.expect(t, final.boss == .Gate_Tyrant, "depth 10 is the Gate Tyrant")
		testing.expect(t, final.reward_hint == "gate relic and clear record", "depth 10 keeps the authored clear-record hint")
		testing.expect(t, final.risk_tags[final.risk_count-1] == "final boss" || final.risk_count == ar.MAX_RISK_TAGS, "depth 10 carries the final-boss tag unless truncated")
	}
}

@(test)
generated_floors_follow_the_plan :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(23, 0), .Warden)
	defer ar.run_destroy(&run)
	for {
		entry := run.plan[run.depth - 1]
		testing.expectf(t, run.theme_index == entry.theme_index, "floor theme must come from the plan (depth %v)", run.depth)
		testing.expectf(t, run.dark_floor == entry.dark, "floor darkness must come from the plan (depth %v)", run.depth)
		testing.expectf(t, ar.boss_alive(&run) == entry.has_boss, "guardian presence must match the plan (depth %v)", run.depth)
		if run.depth >= ar.DUNGEON_DEPTH do break
		ar.run_descend(&run)
	}
}

@(test)
run_modifier_stats_scale_enemies :: proc(t: ^testing.T) {
	base := ar.enemy_make(.Ghoul, {5, 5}, 4)
	pressed := base
	blood_moon := ar.RUN_MODIFIERS[ar.Run_Modifier_Id.Blood_Moon]
	ar.apply_run_modifier_stats(&pressed, &blood_moon)
	testing.expectf(t, pressed.max_hp == max(1, int(f32(base.max_hp) * 1.18)), "Blood Moon multiplies HP by 1.18 (got %v)", pressed.max_hp)
	testing.expect(t, pressed.hp == pressed.max_hp, "modifier pass refills HP")
	testing.expect(t, pressed.damage == base.damage + 2, "Blood Moon adds +2 damage")
	testing.expect(t, pressed.aggro_range == base.aggro_range + 1.0, "Blood Moon adds +1 aggro")

	weakened := base
	starved := ar.RUN_MODIFIERS[ar.Run_Modifier_Id.Starved_Depths]
	ar.apply_run_modifier_stats(&weakened, &starved)
	testing.expect(t, weakened.max_hp < base.max_hp, "Starved Depths weakens enemies")
	testing.expect(t, weakened.damage == max(1, base.damage - 1), "Starved Depths lowers damage")
}

@(test)
encounter_and_modifier_bonuses_raise_odds :: proc(t: ^testing.T) {
	// Elite Hunt and template pressure join inside the pygame clamp.
	testing.expect(t, ar.elite_chance(5, 0.16 + 0.08) > ar.elite_chance(5), "elite bonus raises the odds")
	testing.expect(t, ar.elite_chance(9, 10.0) == 0.55, "elite odds stay clamped at 0.55")
	testing.expect(t, ar.miniboss_chance(5, 0.035) > ar.miniboss_chance(5), "miniboss bonus raises the odds")
	testing.expect(t, ar.miniboss_chance(9, 10.0) == 0.22, "miniboss odds stay clamped at 0.22")
}

@(test)
challenge_room_guarantees_marked_guardian :: proc(t: ^testing.T) {
	verified := false
	seed_loop: for seed_i in 1 ..= 60 {
		seed := ar.derive_seed(u64(seed_i), 0)
		plan, _ := ar.generate_run_plan(seed)
		for depth in 2 ..= 8 {
			entry := plan[depth - 1]
			if entry.has_boss || entry.encounter != .Challenge_Room do continue
			run: ar.Run
			ar.run_start(&run, seed, .Warden)
			defer ar.run_destroy(&run)
			for run.depth < depth do ar.run_descend(&run)

			champion_index := -1
			for &enemy, i in run.enemies {
				if enemy.challenge_boss {
					testing.expect(t, enemy.role == .Miniboss, "the challenge guardian is an Oathbound miniboss")
					champion_index = i
				}
			}
			testing.expectf(t, champion_index >= 0, "challenge_room must guarantee a marked guardian (seed %v depth %v)", seed_i, depth)
			if champion_index < 0 do continue seed_loop

			// Its clear is tracked run-wide once the sweep sees it die.
			run.enemies[champion_index].hp = 0
			ar.sim_tick(&run, {})
			testing.expect(t, run.challenge_rooms_cleared == 1, "clearing the guardian must count")
			verified = true
			break seed_loop
		}
	}
	testing.expect(t, verified, "no seed in 1..60 produced a testable challenge room")
}

@(test)
bar_ledger_survives_descent_and_summons_dancer :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(7, 0), .Warden)
	defer ar.run_destroy(&run)

	// The run-level toast ledger: one free ale per floor's refuge state.
	visited_before := run.bars_visited
	testing.expect(t, ar.run_toast_bar(&run), "first toast on a floor succeeds")
	testing.expect(t, !ar.run_toast_bar(&run), "the refuge state still gates one ale per bar")
	testing.expect(t, run.bars_toasted == 1, "toasts land in the run ledger")

	ar.run_descend(&run)
	testing.expect(t, run.bars_toasted == 1, "descending must not reset the toast ledger")
	testing.expect(t, run.bars_visited >= visited_before, "the visited tally only grows")
	testing.expect(t, !run.refuge.bar_toasted, "the per-floor refuge state does reset")

	// The pilgrimage reward: idempotent, immortal, and withheld while any
	// generated bar is untoasted.
	run.bars_visited = 3
	run.bars_toasted = 2
	testing.expect(t, !ar.maybe_summon_bar_dancer(&run), "an untoasted bar withholds the dancer")
	run.bars_toasted = 3
	testing.expect(t, ar.maybe_summon_bar_dancer(&run), "all bars toasted summons the dancer")
	testing.expect(t, !ar.maybe_summon_bar_dancer(&run), "the summon is idempotent")

	dancer_count := 0
	for &familiar in run.familiars {
		if familiar.kind == .Bar_Dancer {
			dancer_count += 1
			testing.expect(t, familiar.unkillable, "the dancer is immortal")
			testing.expect(t, familiar.max_hp == ar.BAR_DANCER_HP && familiar.damage == ar.BAR_DANCER_DAMAGE, "dancer stats match familiars.py")
			ar.familiar_take_damage(&familiar, 9999)
			testing.expect(t, familiar.hp == 1, "unkillable damage floors at 1 HP")
		}
	}
	testing.expect(t, dancer_count == 1, "exactly one dancer joins")

	// Class recasts replace summon slots, never the run reward.
	ar.clear_summoned_familiars(&run)
	testing.expect(t, len(run.familiars) == 1 && run.familiars[0].kind == .Bar_Dancer, "recasts must not dismiss the dancer")
}

@(test)
stairs_preview_tells_the_next_floor :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(31, 0), .Warden)
	defer ar.run_destroy(&run)
	stairs := run.dungeon.stairs
	run.player.pos = {f32(stairs.x) + 0.5, f32(stairs.y) + 0.5}
	preview := ar.stairs_preview(&run)
	next := run.plan[run.depth]
	testing.expect(t, preview != "", "usable stairs must preview the next floor")
	testing.expect(t, strings.contains(preview, ar.THEMES[next.theme_index].name), "the preview names the next theme")
	testing.expect(t, strings.contains(preview, "Threat"), "the preview carries the threat line")
	testing.expect(t, strings.contains(preview, next.reward_hint), "the preview carries the reward hint")

	// Away from the stairs there is nothing to preview.
	run.player.pos = ar.run_spawn_point(&run)
	testing.expect(t, ar.stairs_preview(&run) == "" || ar.player_near_stairs(&run), "no preview away from the stairs")
}

@(test)
descend_recovery_stays_a_quarter_pool :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(3, 0), .Warden)
	defer ar.run_destroy(&run)
	run.player.stamina = 0
	run.player.mana = 0
	ar.run_descend(&run)
	testing.expect(t, run.player.stamina == f32(run.player.max_stamina) * 0.25, "descent restores exactly a quarter stamina pool")
	testing.expect(t, run.player.mana == f32(run.player.max_mana) * 0.25, "descent restores exactly a quarter mana pool")
}
