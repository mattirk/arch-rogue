package archrogue_tests

// Headless M9 discipline-tree tests. The table is the only progression source
// of truth; UI code only selects stable IDs and calls these pure rules.

import "core:strings"
import "core:testing"
import ar "../src"

PROGRESSION_EPS :: 1e-5

Discipline_Aggregate :: struct {
	count:   int,
	melee:   int,
	spell:   int,
	armor:   int,
	hp:      int,
	mana:    int,
	stamina: int,
	speed:   f32,
}

@(private = "file")
progression_test_player :: proc(archetype: ar.Archetype_Id, tokens := 0) -> ar.Player {
	return ar.Player{
		archetype = archetype,
		hp = 70,
		max_hp = 100,
		mana = 20,
		max_mana = 40,
		stamina = 40,
		max_stamina = 80,
		level = 1,
		memory_tokens = tokens,
	}
}

@(private = "file")
progression_state_equal :: proc(a, b: ^ar.Player) -> bool {
	return a.memory_tokens == b.memory_tokens &&
		a.acquired_disciplines == b.acquired_disciplines &&
		a.discipline_melee_bonus == b.discipline_melee_bonus &&
		a.discipline_spell_bonus == b.discipline_spell_bonus &&
		a.discipline_armor_bonus == b.discipline_armor_bonus &&
		abs(a.discipline_speed_bonus-b.discipline_speed_bonus) < PROGRESSION_EPS &&
		a.discipline_combo_melee_applied == b.discipline_combo_melee_applied &&
		a.discipline_combo_spell_applied == b.discipline_combo_spell_applied &&
		a.discipline_combo_hp_applied == b.discipline_combo_hp_applied &&
		a.hp == b.hp && a.max_hp == b.max_hp &&
		abs(a.mana-b.mana) < PROGRESSION_EPS && a.max_mana == b.max_mana &&
		abs(a.stamina-b.stamina) < PROGRESSION_EPS && a.max_stamina == b.max_stamina &&
		a.precision_rank == b.precision_rank
}

@(test)
m9_discipline_table_is_complete_structured_and_unique :: proc(t: ^testing.T) {
	testing.expectf(t, len(ar.DISCIPLINES) == ar.DISCIPLINE_COUNT, "discipline table has %v rows, want %v", len(ar.DISCIPLINES), ar.DISCIPLINE_COUNT)

	for id in ar.Discipline_Id {
		def := ar.DISCIPLINES[id]
		testing.expectf(t, def.key != "" && def.name != "" && def.description != "", "%v has missing canonical text", id)
		testing.expectf(t, def.degree >= 1 && def.degree <= ar.DISCIPLINE_DEGREES, "%v has invalid degree %v", id, def.degree)
		testing.expectf(t, ar.DISCIPLINE_PATH_DEFS[def.path].archetype == def.archetype, "%v path/archetype mismatch", id)
		for other_i in 0 ..< int(id) {
			other := ar.Discipline_Id(other_i)
			testing.expectf(t, ar.DISCIPLINES[other].key != def.key, "%v and %v duplicate key %v", other, id, def.key)
		}
		looked_up, found := ar.discipline_by_key(def.key)
		testing.expectf(t, found && looked_up == id, "stable key %v did not round-trip", def.key)
	}

	for archetype in ar.Archetype_Id {
		archetype_count := 0
		for id in ar.Discipline_Id {
			if ar.DISCIPLINES[id].archetype == archetype do archetype_count += 1
		}
		testing.expectf(t, archetype_count == 20, "%v has %v nodes, want 20", archetype, archetype_count)

		for column in 0 ..< ar.DISCIPLINE_PATHS_PER_ARCHETYPE {
			path, found := ar.discipline_path_at(archetype, column)
			testing.expectf(t, found && ar.DISCIPLINE_PATH_DEFS[path].archetype == archetype, "%v column %v has an invalid path", archetype, column)
			previous: ar.Discipline_Id
			for degree in 1 ..= ar.DISCIPLINE_DEGREES {
				id, node_found := ar.discipline_at(path, degree)
				testing.expectf(t, node_found, "%v degree %v is missing", path, degree)
				if !node_found do continue
				def := ar.DISCIPLINES[id]
				testing.expectf(t, def.archetype == archetype && def.path == path && int(def.degree) == degree, "%v degree %v points to the wrong node", path, degree)
				if degree == 1 {
					testing.expectf(t, !def.has_prerequisite, "%v root unexpectedly has a prerequisite", id)
				} else {
					testing.expectf(t, def.has_prerequisite && def.prerequisite == previous, "%v prerequisite is not the previous path node", id)
				}
				previous = id
			}
		}
	}
}

@(test)
m9_discipline_numeric_summaries_cover_every_authored_bonus :: proc(t: ^testing.T) {
	for id in ar.Discipline_Id {
		def := ar.DISCIPLINES[id]
		expected := [ar.Discipline_Stat_Kind]f32{
			.Health = f32(def.max_hp_bonus),
			.Mana = f32(def.max_mana_bonus),
			.Stamina = f32(def.max_stamina_bonus),
			.Melee = f32(def.melee_bonus),
			.Spell = f32(def.spell_bonus),
			.Armor = f32(def.armor_bonus),
			.Move_Speed = def.speed_bonus * 25,
		}
		expected_count := 0
		for amount in expected {
			if amount != 0 do expected_count += 1
		}

		bonuses, count := ar.discipline_stat_bonuses(def)
		testing.expectf(t, count == expected_count && count > 0, "%v numeric summary has %v rows, want %v", id, count, expected_count)
		seen: [ar.Discipline_Stat_Kind]bool
		for bonus in bonuses[:count] {
			testing.expectf(t, !seen[bonus.kind], "%v numeric summary repeats %v", id, bonus.kind)
			seen[bonus.kind] = true
			testing.expectf(t, abs(bonus.amount-expected[bonus.kind]) < PROGRESSION_EPS, "%v %v displays %.3f, want %.3f", id, bonus.kind, bonus.amount, expected[bonus.kind])
		}
		for amount, kind in expected {
			testing.expectf(t, seen[kind] == (amount != 0), "%v numeric summary coverage differs for %v", id, kind)
		}
	}
}

@(test)
m9_discipline_stats_match_canonical_aggregate :: proc(t: ^testing.T) {
	expected := [ar.Archetype_Id]Discipline_Aggregate{
		.Warden = {20, 17, 25, 30, 132, 64, 76, 0},
		.Rogue = {20, 53, 21, 0, 10, 0, 140, .59},
		.Arcanist = {20, 0, 55, 13, 32, 232, 0, 0},
		.Acolyte = {20, 15, 68, 8, 58, 172, 0, 0},
		.Ranger = {20, 42, 33, 0, 18, 0, 170, .74},
	}
	actual: [ar.Archetype_Id]Discipline_Aggregate
	for id in ar.Discipline_Id {
		def := ar.DISCIPLINES[id]
		sum := &actual[def.archetype]
		sum.count += 1
		sum.melee += def.melee_bonus
		sum.spell += def.spell_bonus
		sum.armor += def.armor_bonus
		sum.hp += def.max_hp_bonus
		sum.mana += def.max_mana_bonus
		sum.stamina += def.max_stamina_bonus
		sum.speed += def.speed_bonus
	}
	for archetype in ar.Archetype_Id {
		got, want := actual[archetype], expected[archetype]
		testing.expectf(t, got.count == want.count, "%v node count %v, want %v", archetype, got.count, want.count)
		testing.expectf(t, got.melee == want.melee && got.spell == want.spell && got.armor == want.armor, "%v offense/armor aggregate changed: %v", archetype, got)
		testing.expectf(t, got.hp == want.hp && got.mana == want.mana && got.stamina == want.stamina, "%v pool aggregate changed: %v", archetype, got)
		testing.expectf(t, abs(got.speed-want.speed) < PROGRESSION_EPS, "%v speed aggregate %.3f, want %.3f", archetype, got.speed, want.speed)
	}
}

@(test)
m9_every_discipline_has_explicit_effect_coverage :: proc(t: ^testing.T) {
	untracked, stats_only, partial, deferred, fully := 0, 0, 0, 0, 0
	for id in ar.Discipline_Id {
		coverage := ar.DISCIPLINES[id].effect_coverage
		mechanic := ar.DISCIPLINE_MECHANICS[id]
		switch coverage {
		case .Untracked: untracked += 1
		case .Stats_Only:
			stats_only += 1
			testing.expectf(t, mechanic.kind == .None && mechanic.text == "", "%v is stats-only but has a bespoke mechanic summary", id)
		case .Partially_Wired: partial += 1
		case .Deferred: deferred += 1
		case .Fully_Wired:
			fully += 1
			testing.expectf(t, mechanic.kind != .None && mechanic.text != "", "%v is fully wired but lacks a mechanic summary", id)
			testing.expectf(t, strings.contains(mechanic.text, "  "), "%v mechanic summary must separate its effect name from values", id)
			has_number := false
			for character in mechanic.text {
				if character >= '0' && character <= '9' {
					has_number = true
					break
				}
			}
			testing.expectf(t, has_number, "%v mechanic summary must expose numeric behavior", id)
		}
	}
	// MX.3 wired every formerly Deferred/Partially_Wired node; the ledger must
	// stay clean so a regressing edit is caught by count, not by playtest.
	testing.expectf(t, untracked == 0, "%v disciplines have untracked effects", untracked)
	testing.expectf(t, stats_only == 28, "stats-only coverage has %v rows, want 28", stats_only)
	testing.expectf(t, partial == 0, "partially-wired coverage has %v rows, want 0", partial)
	testing.expectf(t, deferred == 0, "deferred coverage has %v rows, want 0", deferred)
	testing.expectf(t, fully == 72, "fully-wired coverage has %v rows, want 72", fully)
	warden_reach := ar.DISCIPLINE_MECHANICS[.Warden_Bulwark_Ward].text
	warden_stun := ar.DISCIPLINE_MECHANICS[.Warden_Aegis].text
	testing.expect(t, strings.contains(warden_reach, "4 targets") && strings.contains(warden_reach, "1.90 tiles"), "Warden's Ward must expose cleave width and reach")
	testing.expect(t, strings.contains(warden_stun, "0.35s") && strings.contains(warden_stun, "STUN"), "Aegis Lore must expose its stun duration")
}

@(test)
m9_level_boundaries_award_one_memory_token_each :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(9101, 0), .Warden)
	defer ar.run_destroy(&run)
	testing.expect(t, run.player.memory_tokens == 0, "fresh runs must not start with a memory token")
	ar.player_gain_xp(&run, 250) // 100 for level 2, then 150 for level 3.
	testing.expectf(t, run.player.level == 3, "250 XP reached level %v, want 3", run.player.level)
	testing.expectf(t, run.player.memory_tokens == 2, "two crossed level boundaries granted %v tokens", run.player.memory_tokens)
	testing.expect(t, run.player.xp == 0 && run.player.next_xp == 225, "XP overflow/growth changed while granting tokens")
}

@(test)
m9_discipline_acquisition_is_atomic_and_enforces_two_paths :: proc(t: ^testing.T) {
	player := progression_test_player(.Warden)

	before := player
	result := ar.discipline_try_acquire(&player, .Rogue_Precision)
	testing.expect(t, result == .Wrong_Archetype && progression_state_equal(&player, &before), "wrong-archetype rejection mutated progression")

	result = ar.discipline_try_acquire(&player, .Warden_Aegis)
	testing.expect(t, result == .Prerequisite_Locked && progression_state_equal(&player, &before), "prerequisite rejection mutated progression")

	result = ar.discipline_try_acquire(&player, .Warden_Bulwark)
	testing.expect(t, result == .No_Tokens && progression_state_equal(&player, &before), "no-token rejection mutated progression")

	player.memory_tokens = 3
	result = ar.discipline_try_acquire(&player, .Warden_Bulwark)
	testing.expect(t, result == .Acquired, "first path root should be acquirable")
	testing.expect(t, player.memory_tokens == 2 && player.acquired_disciplines[.Warden_Bulwark], "successful acquisition did not spend exactly one token")
	testing.expect(t, player.discipline_melee_bonus == 1 && player.discipline_armor_bonus == 2, "Bulwark Training stat bonuses changed")
	testing.expect(t, player.max_hp == 110 && player.hp == 80, "max-HP acquisition must grow current HP by the same amount")

	before = player
	result = ar.discipline_try_acquire(&player, .Warden_Bulwark)
	testing.expect(t, result == .Already_Chosen && progression_state_equal(&player, &before), "duplicate rejection mutated progression")

	testing.expect(t, ar.discipline_state(&player, .Warden_Aegis) == .Available, "acquiring a root must unlock degree 2")
	result = ar.discipline_try_acquire(&player, .Warden_Riposte)
	testing.expect(t, result == .Acquired, "second path root should remain available")
	testing.expect(t, ar.discipline_committed_path_count(&player) == 2, "two acquired roots should commit two paths")
	testing.expect(t, ar.discipline_state(&player, .Warden_Smite) == .Path_Locked, "third path should render as sealed")

	before = player
	result = ar.discipline_try_acquire(&player, .Warden_Smite)
	testing.expect(t, result == .Path_Locked && progression_state_equal(&player, &before), "third-path rejection mutated progression")
	// Already-committed paths remain legal after the limit is reached.
	result = ar.discipline_try_acquire(&player, .Warden_Aegis)
	testing.expect(t, result == .Acquired, "path limit must not block progress in a committed path")
}

@(test)
m9_completed_paths_apply_only_the_canonical_combo_delta :: proc(t: ^testing.T) {
	player := progression_test_player(.Warden, 10)
	bulwark := [5]ar.Discipline_Id{
		.Warden_Bulwark, .Warden_Aegis, .Warden_Bulwark_Ward,
		.Warden_Iron_Vow, .Warden_Unbreakable,
	}
	riposte := [5]ar.Discipline_Id{
		.Warden_Riposte, .Warden_Counter, .Warden_Riposte_Edge,
		.Warden_Reckoning, .Warden_Final_Reckoning,
	}
	for id in bulwark do testing.expectf(t, ar.discipline_try_acquire(&player, id) == .Acquired, "%v failed", id)
	bonus := ar.discipline_combo_bonus(&player)
	testing.expect(t, bonus == ar.Discipline_Combo_Bonus{1, 1, 6}, "one completed path must grant (1,1,6)")
	testing.expect(t, player.discipline_combo_melee_applied == 1 && player.discipline_combo_spell_applied == 1 && player.discipline_combo_hp_applied == 6, "first combo total was not applied")
	testing.expect(t, player.max_hp == 166 && player.hp == 136, "first path direct HP plus combo delta changed")

	for id in riposte do testing.expectf(t, ar.discipline_try_acquire(&player, id) == .Acquired, "%v failed", id)
	bonus = ar.discipline_combo_bonus(&player)
	testing.expect(t, bonus == ar.Discipline_Combo_Bonus{4, 4, 20}, "two completed paths must grant (4,4,20)")
	testing.expect(t, player.discipline_combo_melee_applied == 4 && player.discipline_combo_spell_applied == 4 && player.discipline_combo_hp_applied == 20, "second combo total was not applied as a delta")
	testing.expect(t, player.max_hp == 180 && player.hp == 150, "second path must add only the +14 HP combo delta")
	testing.expect(t, player.memory_tokens == 0, "ten nodes should spend ten tokens")
}

@(test)
m9_speed_and_cross_path_metadata_match_pygame_behavior :: proc(t: ^testing.T) {
	rogue := progression_test_player(.Rogue, 1)
	before_speed := ar.player_speed(&rogue)
	testing.expect(t, ar.discipline_try_acquire(&rogue, .Rogue_Smoke) == .Acquired, "Smoke Step failed")
	after_speed := ar.player_speed(&rogue)
	testing.expectf(t, abs((after_speed-before_speed)-ar.PLAYER_MOVE_SPEED*.15*.25) < PROGRESSION_EPS, "discipline speed rating used the wrong 25%% conversion: %.5f", after_speed-before_speed)

	warden := progression_test_player(.Warden, 5)
	warden_nodes := [5]ar.Discipline_Id{.Warden_Riposte, .Warden_Bulwark, .Warden_Aegis, .Warden_Bulwark_Ward, .Warden_Iron_Vow}
	for id in warden_nodes {
		testing.expectf(t, ar.discipline_try_acquire(&warden, id) == .Acquired, "%v failed", id)
	}
	cross := ar.discipline_cross_path_bonus(&warden)
	testing.expect(t, cross == ar.Discipline_Cross_Path_Bonus{1, 0}, "Iron Vow should report one Counter-tag melee bonus")
	// Canonical Pygame exposes this query but does not add it to Player stats.
	testing.expect(t, warden.discipline_melee_bonus == 3, "cross-path query must not silently mutate effective stats")
}

@(test)
m9_precision_spirit_and_beast_use_acquired_path_rank :: proc(t: ^testing.T) {
	rogue := progression_test_player(.Rogue, 5)
	precision := [5]ar.Discipline_Id{
		.Rogue_Precision, .Rogue_Venom, .Rogue_Executioner,
		.Rogue_Crimson_Edge, .Rogue_Deathmark,
	}
	for id in precision do testing.expectf(t, ar.discipline_try_acquire(&rogue, id) == .Acquired, "%v failed", id)
	testing.expect(t, ar.discipline_path_rank(&rogue, .Rogue_Precision) == 5 && ar.player_precision_rank(&rogue) == 5, "Precision path did not feed the live crit rank")

	acolyte_run: ar.Run
	ar.run_start(&acolyte_run, ar.derive_seed(9102, 0), .Acolyte)
	defer ar.run_destroy(&acolyte_run)
	acolyte_run.player.memory_tokens = 3
	spirit_nodes := [3]ar.Discipline_Id{.Acolyte_Spirit_Call, .Acolyte_Wraith_Host, .Acolyte_Bone_Legion}
	for id in spirit_nodes {
		testing.expectf(t, ar.discipline_try_acquire(&acolyte_run.player, id) == .Acquired, "%v failed", id)
	}
	testing.expect(t, ar.player_cast_spirit_call(&acolyte_run), "ranked Spirit Call failed")
	spirit_stats := ar.spirit_call_stats(3)
	testing.expectf(t, len(acolyte_run.familiars) == spirit_stats.count, "rank-three Spirit Call spawned %v familiars, want %v", len(acolyte_run.familiars), spirit_stats.count)
	if len(acolyte_run.familiars) > 0 {
		testing.expect(t, acolyte_run.familiars[0].spirit_rank == 3 && acolyte_run.familiars[0].max_hp == spirit_stats.hp, "Spirit Call ignored acquired path rank")
	}

	ranger_run: ar.Run
	ar.run_start(&ranger_run, ar.derive_seed(9103, 0), .Ranger)
	defer ar.run_destroy(&ranger_run)
	ranger_run.player.memory_tokens = 5
	beast := [5]ar.Discipline_Id{
		.Ranger_Beast_Bond, .Ranger_Pack_Tactics, .Ranger_Alpha,
		.Ranger_Spirit_Companion, .Ranger_Primal_Lord,
	}
	for id in beast do testing.expectf(t, ar.discipline_try_acquire(&ranger_run.player, id) == .Acquired, "%v failed", id)
	testing.expect(t, ar.player_cast_spirit_beast(&ranger_run), "ranked Spirit Beast failed")
	beast_stats := ar.spirit_beast_stats(5)
	live := ar.living_spirit_beast(&ranger_run)
	testing.expect(t, live != nil, "Spirit Beast did not spawn")
	if live != nil {
		testing.expect(t, live.spirit_rank == 5 && live.max_hp == beast_stats.hp && live.champion, "Spirit Beast ignored acquired path rank")
	}
}

@(test)
m9_acquiring_beast_rank_refreshes_a_living_companion :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(9104, 0), .Ranger)
	defer ar.run_destroy(&run)
	testing.expect(t, ar.player_cast_spirit_beast(&run), "fresh rank-zero Spirit Beast failed")
	beast := ar.living_spirit_beast(&run)
	testing.expect(t, beast != nil, "fresh Spirit Beast did not spawn")
	if beast == nil do return
	beast.hp -= 10
	old_hp := beast.hp
	old_max_hp := beast.max_hp
	run.player.memory_tokens = 1
	result := ar.run_try_acquire_discipline(&run, .Ranger_Beast_Bond)
	testing.expect(t, result == .Acquired, "Beast Bond acquisition failed")
	beast = ar.living_spirit_beast(&run)
	want := ar.spirit_beast_stats(1)
	testing.expect(t, beast != nil && beast.spirit_rank == 1, "living beast rank was not refreshed")
	if beast != nil {
		hp_gain := want.hp - old_max_hp
		testing.expect(t, beast.max_hp == want.hp && beast.hp == old_hp+hp_gain, "refresh must preserve missing HP while adding the new maximum")
		testing.expect(t, beast.damage == want.damage && beast.speed == want.speed && beast.attack_cooldown == want.attack_cooldown, "refresh did not apply rank-one Beast stats")
	}
}
