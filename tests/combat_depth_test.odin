package archrogue_tests

// Headless M8 parity tests: typed combat, status rules, affix content,
// independent action clocks, cursed/unknown equipment, and split RNG streams.

import "core:testing"
import "core:math"
import ar "../src"

@(private = "file")
near_f32 :: proc(a, b: f32, epsilon: f32 = 1e-5) -> bool {
	return abs(a - b) < epsilon
}

@(private = "file")
m8_prepare_arena :: proc(run: ^ar.Run) {
	for x in 0 ..< ar.MAP_W {
		for y in 0 ..< ar.MAP_H do run.dungeon.tiles[x][y] = .Wall
	}
	for x in 6 ..= 18 {
		for y in 6 ..= 16 do run.dungeon.tiles[x][y] = .Floor
	}
	run.player.pos = {10.5, 10.5}
	run.player.prev_pos = run.player.pos
	run.player.facing = {1, 0}
	clear(&run.enemies)
	clear(&run.projectiles)
	clear(&run.familiars)
	clear(&run.bells)
	clear(&run.numbers)
	clear(&run.ground_items)
	clear(&run.sfx)
}

@(test)
m8_affix_table_is_complete_and_slot_legal :: proc(t: ^testing.T) {
	testing.expectf(t, len(ar.AFFIX_DEFS) == 35, "affix table has %v rows, want 35", len(ar.AFFIX_DEFS))
	weapon_count, armor_count := 0, 0
	for kind in ar.Affix_Kind {
		def := ar.AFFIX_DEFS[kind]
		testing.expectf(t, def.name != "", "%v has no display name", kind)
		testing.expectf(t, def.weapon || def.armor, "%v is eligible for no equipment slot", kind)
		if def.weapon do weapon_count += 1
		if def.armor do armor_count += 1
	}
	testing.expectf(t, weapon_count == 24, "weapon-eligible affixes %v, want 24", weapon_count)
	testing.expectf(t, armor_count == 23, "armor-eligible affixes %v, want 23", armor_count)

	balanced := ar.AFFIX_DEFS[.Balanced]
	testing.expect(t, balanced.weapon && !balanced.armor, "Balanced must be weapon-only")
	testing.expect(t, balanced.power == ar.Stat_Range{1, 3}, "Balanced power range changed")
	testing.expect(t, balanced.attack_speed == ar.Stat_Range{.04, .08}, "Balanced attack-speed range changed")
	testing.expect(t, balanced.has_bonus && balanced.skill_bonus == .Dash_Tempo, "Balanced must grant Dash tempo")

	storm := ar.AFFIX_DEFS[.Storm_Touched]
	testing.expect(t, storm.typed && storm.damage_type == .Arcane, "Storm-Touched must be arcane")
	testing.expect(t, storm.cast_speed == ar.Stat_Range{.04, .08}, "Storm-Touched cast-speed range changed")
	testing.expect(t, storm.proc_chance == ar.Stat_Range{.16, .26} && storm.proc_effect == .Chain, "Storm-Touched chain proc changed")
	testing.expect(t, storm.has_bonus && storm.skill_bonus == .Bolt_Shard, "Storm-Touched must grant a bolt shard")

	light := ar.AFFIX_DEFS[.Light]
	testing.expect(t, light.armor && !light.weapon, "Light must be armor-only")
	testing.expect(t, light.attack_speed == ar.Stat_Range{.02, .05}, "Light attack-speed range changed")
	testing.expect(t, light.move_speed == ar.Stat_Range{.03, .06}, "Light move-speed range changed")

	cinders := ar.AFFIX_DEFS[.Of_Cinders]
	testing.expect(t, cinders.weapon && cinders.armor, "of Cinders must roll on both slots")
	testing.expect(t, cinders.defense == ar.Stat_Range{-2, -1}, "of Cinders defense tradeoff changed")
	testing.expect(t, cinders.cast_speed == ar.Stat_Range{.03, .07}, "of Cinders cast-speed range changed")
	testing.expect(t, cinders.typed && cinders.damage_type == .Fire && cinders.proc_effect == .Ignite, "of Cinders fire identity changed")

	alacrity := ar.AFFIX_DEFS[.Of_Alacrity]
	testing.expect(t, alacrity.attack_speed == ar.Stat_Range{.04, .08}, "of Alacrity attack speed changed")
	testing.expect(t, alacrity.cast_speed == ar.Stat_Range{.04, .08}, "of Alacrity cast speed changed")
	testing.expect(t, alacrity.move_speed == ar.Stat_Range{.02, .05}, "of Alacrity move speed changed")
}

@(test)
m8_enemy_damage_types_resistances_and_elites :: proc(t: ^testing.T) {
	expected_types := [ar.Enemy_Kind]ar.Damage_Type{
		.Ghoul = .Shadow,
		.Venom_Skitter = .Poison,
		.Bone_Imp = .Frost,
		.Grave_Archer = .Physical,
		.Cultist = .Arcane,
		.Crypt_Brute = .Physical,
		.Ash_Hound = .Fire,
		.Rune_Sentinel = .Arcane,
		.Plague_Toad = .Poison,
		.Hollow_Knight = .Physical,
		.Gate_Warden = .Holy,
	}
	expected_resistances := [ar.Enemy_Kind][7]f32{
		// Physical, Fire, Frost, Poison, Arcane, Holy, Shadow.
		.Ghoul = {0, 0, 0, 0, 0, -.15, .18},
		.Venom_Skitter = {0, -.18, 0, .45, 0, 0, 0},
		.Bone_Imp = {0, 0, .22, 0, 0, -.10, 0},
		.Grave_Archer = {.10, 0, 0, -.08, 0, 0, 0},
		.Cultist = {0, 0, 0, 0, .24, 0, .12},
		.Crypt_Brute = {.24, 0, 0, 0, -.10, 0, 0},
		.Ash_Hound = {0, .34, -.18, 0, 0, 0, 0},
		.Rune_Sentinel = {.10, 0, 0, 0, .38, 0, 0},
		.Plague_Toad = {0, -.12, 0, .38, 0, 0, 0},
		.Hollow_Knight = {.18, 0, 0, 0, 0, 0, .12},
		.Gate_Warden = {.20, 0, 0, 0, 0, .28, -.12},
	}

	for kind in ar.Enemy_Kind {
		enemy := ar.enemy_make(kind, {}, 1)
		testing.expectf(t, enemy.damage_type == expected_types[kind], "%v deals %v, want %v", kind, enemy.damage_type, expected_types[kind])
		for damage_type in ar.Damage_Type {
			testing.expectf(
				t,
				near_f32(enemy.resistances[damage_type], expected_resistances[kind][int(damage_type)]),
				"%v resistance to %v is %.3f, want %.3f",
				kind, damage_type, enemy.resistances[damage_type], expected_resistances[kind][int(damage_type)],
			)
		}
	}

	ironbound := ar.enemy_make(.Ghoul, {}, 1)
	ar.apply_elite(&ironbound, 1)
	testing.expect(t, ironbound.role == .Elite && ironbound.elite_mod == 1, "Ironbound must carry elite identity")
	testing.expect(t, near_f32(ironbound.resistances[.Physical], .32), "Ironbound physical resistance changed")

	venomous := ar.enemy_make(.Ghoul, {}, 1)
	ar.apply_elite(&venomous, 2)
	testing.expect(t, venomous.damage_type == .Poison, "Venomous elite must deal poison damage")
	testing.expect(t, near_f32(venomous.resistances[.Poison], .40), "Venomous elite poison resistance changed")
	high_poison := ar.enemy_make(.Venom_Skitter, {}, 1)
	ar.apply_elite(&high_poison, 2)
	testing.expect(t, near_f32(high_poison.resistances[.Poison], .45), "elite overlay must not lower an innate resistance")

	runed := ar.enemy_make(.Ghoul, {}, 1)
	ar.apply_elite(&runed, 3)
	testing.expect(t, runed.damage_type == .Arcane, "Runed elite must deal arcane damage")
	testing.expect(t, near_f32(runed.resistances[.Arcane], .34), "Runed elite arcane resistance changed")
}

@(test)
m8_resistance_math_matches_the_canonical_curve :: proc(t: ^testing.T) {
	enemy := ar.enemy_make(.Venom_Skitter, {}, 1)
	testing.expect(t, ar.enemy_damage_after_resistance(&enemy, 20, .Poison) == 11, "45% resistance should reduce 20 to 11")
	testing.expect(t, ar.enemy_damage_after_resistance(&enemy, 20, .Fire) == 24, "-18% resistance should increase 20 to 24")
	enemy.resistances[.Physical] = 2
	testing.expect(t, ar.enemy_damage_after_resistance(&enemy, 20, .Physical) == 6, "enemy resistance must clamp at 70%")
	enemy.resistances[.Physical] = -2
	testing.expect(t, ar.enemy_damage_after_resistance(&enemy, 20, .Physical) == 27, "enemy vulnerability must clamp at -35%")
	enemy.statuses[.Chilled] = 1
	testing.expect(t, ar.enemy_damage_after_resistance(&enemy, 20, .Arcane) == 24, "chilled targets should take 18% more arcane damage")

	player := ar.Player{archetype = .Rogue}
	player.has_armor = true
	player.armor = ar.Item{
		kind = .Armor,
		defense = 10,
		typed = true,
		damage_type = .Frost,
		affixes = {{kind = .Grounded}, {}, {}},
		affix_count = 1,
	}
	testing.expect(t, near_f32(ar.player_typed_resistance(&player, .Physical), .06), "armor's base typed resistance changed")
	testing.expect(t, near_f32(ar.player_typed_resistance(&player, .Frost), .14), "matching armor damage type must add 8%")
	testing.expect(t, near_f32(ar.player_typed_resistance(&player, .Arcane), .18), "Grounded must add 12% arcane resistance")
	player.statuses[.Aegis] = 1
	testing.expect(t, near_f32(ar.player_typed_resistance(&player, .Arcane), .42), "Aegis must add 24% resistance")
}

@(test)
m8_statuses_refresh_resist_slow_and_break_windup :: proc(t: ^testing.T) {
	enemy := ar.enemy_make(.Ghoul, {}, 1)
	ar.enemy_apply_status(&enemy, .Chilled, 2)
	ar.enemy_apply_status(&enemy, .Chilled, 1)
	testing.expect(t, near_f32(enemy.statuses[.Chilled], 2), "a shorter status application must not truncate the active one")
	ar.enemy_apply_status(&enemy, .Chilled, 3)
	testing.expect(t, near_f32(enemy.statuses[.Chilled], 3), "a longer status application must refresh to its maximum")

	enemy.resistances[.Poison] = .55
	ar.enemy_apply_status(&enemy, .Poisoned, 2)
	testing.expect(t, near_f32(enemy.statuses[.Poisoned], 1.1), "55%+ poison resistance must shorten poison duration by 45%")
	testing.expect(t, near_f32(enemy.poison_tick, 1), "first poison application must arm the one-second tick")

	enemy.statuses[.Snared] = 1
	enemy.statuses[.Bound] = 1
	testing.expect(t, near_f32(ar.enemy_status_move_factor(&enemy), .58 * .45 * .62), "slow factors must compose multiplicatively")

	enemy.ai = .Windup
	enemy.windup = .4
	enemy.pending_ability = 0
	ar.enemy_apply_status(&enemy, .Stunned, .3)
	testing.expect(t, enemy.ai == .Chase, "stun must break an enemy windup")
	testing.expect(t, enemy.windup == 0 && enemy.pending_ability == -1, "stun must clear the pending strike")
}

@(test)
m8_enemy_attacks_keep_committed_hits_aim_type_and_variance :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(7331, 0), .Rogue)
	defer ar.run_destroy(&run)
	m8_prepare_arena(&run)
	run.player.has_armor = false
	run.player.hp = 200
	run.player.max_hp = 200

	// A committed base swing lands after the player leaves its reach.
	enemy := ar.enemy_make(.Ghoul, {10.5,10.5}, 1)
	enemy.damage_type = .Physical
	enemy.ai = .Windup
	enemy.windup = 0
	enemy.pending_ability = -1
	enemy.windup_aim = {1,0}
	append(&run.enemies, enemy)
	rng_copy := run.combat_rng
	expected := enemy.damage + ar.rng_range(&rng_copy,-2,3)
	run.player.pos = {16.5,10.5}
	hp_before := run.player.hp
	ar.sim_tick(&run,{})
	testing.expectf(t, hp_before-run.player.hp == expected, "committed base melee dealt %v, want %v", hp_before-run.player.hp, expected)

	// Authored strikes round first, roll the same variance, inherit their
	// owner's type, and likewise cannot be walked out of during the tell.
	m8_prepare_arena(&run)
	run.player.has_armor = false
	run.player.hp = 200
	enemy = ar.enemy_make(.Gate_Warden,{10.5,10.5},1)
	enemy.damage = 19
	enemy.damage_type = .Shadow
	enemy.abilities[0] = .Gate_Strike
	enemy.ability_count = 1
	enemy.pending_ability = 0
	enemy.ai = .Windup
	enemy.windup = 0
	enemy.windup_aim = {1,0}
	append(&run.enemies,enemy)
	rng_copy = run.combat_rng
	expected = int(math.round(f32(enemy.damage)*ar.ABILITY_DEFS[.Gate_Strike].dmg_mult)) + ar.rng_range(&rng_copy,-2,3)
	run.player.pos = {16.5,10.5}
	hp_before = run.player.hp
	ar.sim_tick(&run,{})
	testing.expectf(t, hp_before-run.player.hp == expected, "committed authored strike dealt %v, want %v", hp_before-run.player.hp, expected)
	testing.expect(t, run.numbers[len(run.numbers)-1].damage_type == .Shadow, "authored strike must inherit the enemy's damage type")

	// Bolt and fan tells snapshot aim; moving during the windup does not bend
	// the projectile toward the player's new position.
	m8_prepare_arena(&run)
	run.player.pos = {10.5,14.5}
	enemy = ar.enemy_make(.Rune_Sentinel,{10.5,10.5},1)
	enemy.abilities[0] = .Arcane_Lance
	enemy.ability_count = 1
	enemy.pending_ability = 0
	enemy.ai = .Windup
	enemy.windup = 0
	enemy.windup_aim = {1,0}
	append(&run.enemies,enemy)
	ar.sim_tick(&run,{})
	testing.expect(t, len(run.projectiles) == 1, "committed lance must fire without rechecking its target line")
	if len(run.projectiles) == 1 {
		testing.expect(t, run.projectiles[0].vel.x > 8.4 && abs(run.projectiles[0].vel.y) < 1e-5, "committed lance must retain its snapshotted aim")
		testing.expect(t, near_f32(run.projectiles[0].ttl, ar.ENEMY_PROJECTILE_TTL-ar.SIM_DT), "enemy bolts must use pygame's 1.8-second lifetime")
	}

	// Novas intentionally check the live radius, but use rounded damage and
	// their own per-victim variance once the player remains inside it.
	m8_prepare_arena(&run)
	run.player.has_armor = false
	run.player.hp = 200
	enemy = ar.enemy_make(.Ash_Hound,{10.5,10.5},1)
	enemy.damage = 17
	enemy.damage_type = .Fire
	enemy.abilities[0] = .Ember_Nova
	enemy.ability_count = 1
	enemy.pending_ability = 0
	enemy.ai = .Windup
	enemy.windup = 0
	enemy.windup_aim = {1,0}
	append(&run.enemies,enemy)
	rng_copy = run.combat_rng
	expected = int(math.round(f32(enemy.damage)*ar.ABILITY_DEFS[.Ember_Nova].dmg_mult)) + ar.rng_range(&rng_copy,-2,3)
	run.player.pos = {11.5,10.5}
	hp_before = run.player.hp
	ar.sim_tick(&run,{})
	testing.expectf(t, hp_before-run.player.hp == expected, "nova dealt %v, want rounded+variance %v", hp_before-run.player.hp, expected)
}

@(test)
m8_canonical_bolt_cost_cooldown_type_and_single_shot :: proc(t: ^testing.T) {
	expected_costs := [ar.Archetype_Id]int{
		.Warden = 10, .Rogue = 10, .Arcanist = 7, .Acolyte = 10, .Ranger = 7,
	}
	expected_cooldowns := [ar.Archetype_Id]f32{
		.Warden = .48, .Rogue = .48, .Arcanist = .38, .Acolyte = .48, .Ranger = .38,
	}
	expected_types := [ar.Archetype_Id]ar.Damage_Type{
		.Warden = .Holy, .Rogue = .Physical, .Arcanist = .Arcane, .Acolyte = .Shadow, .Ranger = .Physical,
	}
	for archetype in ar.Archetype_Id {
		player := ar.Player{archetype = archetype}
		testing.expectf(t, ar.player_bolt_mana_cost(&player) == expected_costs[archetype], "%v bolt cost changed", archetype)
		testing.expectf(t, near_f32(ar.player_bolt_cooldown(&player), expected_cooldowns[archetype]), "%v bolt cooldown changed", archetype)
		testing.expectf(t, ar.player_bolt_damage_type(&player) == expected_types[archetype], "%v bolt damage type changed", archetype)
	}

	run: ar.Run
	ar.run_start(&run, ar.derive_seed(8008, 0), .Arcanist)
	defer ar.run_destroy(&run)
	clear(&run.enemies)
	clear(&run.projectiles)
	run.player.mana = f32(run.player.max_mana)
	mana_before := run.player.mana
	testing.expect(t, ar.player_cast_bolt(&run, {1, 0}), "fresh Arcanist bolt should cast")
	testing.expectf(t, len(run.projectiles) == 1, "canonical bolt spawned %v projectiles, want one", len(run.projectiles))
	testing.expect(t, near_f32(mana_before - run.player.mana, 7), "canonical Arcanist bolt must cost 7 mana")
	testing.expect(t, near_f32(run.player.bolt_timer, .38), "canonical Arcanist bolt must start a .38s cooldown")
	if len(run.projectiles) == 1 {
		bolt := run.projectiles[0]
		testing.expect(t, bolt.from_player && bolt.damage_type == .Arcane, "canonical Arc Bolt must be an arcane player projectile")
		testing.expect(t, near_f32(bolt.ttl, ar.BOLT_TTL), "canonical bolt TTL changed")
	}
}

@(test)
m8_dash_cancels_only_an_uncommitted_big_hit :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(8108, 0), .Warden)
	defer ar.run_destroy(&run)
	clear(&run.enemies)

	run.player.stamina = f32(run.player.max_stamina)
	stamina_before := run.player.stamina
	testing.expect(t, ar.player_big_hit_begin(&run, {1, 0}), "fresh Big Hit should begin charging")
	testing.expect(t, near_f32(stamina_before - run.player.stamina, ar.BIGHIT_STAMINA_COST), "Big Hit must spend its stamina on press")
	testing.expect(t, !ar.bighit_committed(&run.player), "a fresh Big Hit must still be cancellable")
	testing.expect(t, ar.player_dash(&run, {1, 0}), "dash should cancel an uncommitted charge and execute")
	testing.expect(t, !ar.bighit_charging(&run.player), "dash must clear the uncommitted charge")
	testing.expect(t, near_f32(run.player.bighit_timer, ar.BIGHIT_CANCEL_COOLDOWN), "cancelled Big Hit must use its short cooldown")
	testing.expect(t, near_f32(run.player.dash_timer, ar.player_dash_cooldown(&run.player)), "the cancelling dash must start its own cooldown")

	run.player.bighit_timer = 0
	run.player.dash_timer = 0
	run.player.stamina = f32(run.player.max_stamina)
	testing.expect(t, ar.player_big_hit_begin(&run, {1, 0}), "second Big Hit should begin")
	run.player.bighit_charge = ar.BIGHIT_CHARGE_TIME * (1 - ar.BIGHIT_COMMIT_FRACTION) - .001
	testing.expect(t, ar.bighit_committed(&run.player), "half-charged Big Hit must commit")
	charge_before := run.player.bighit_charge
	testing.expect(t, !ar.player_big_hit_release(&run.player), "release must not cancel a committed Big Hit")
	testing.expect(t, !ar.player_dash(&run, {1, 0}), "dash must be refused after Big Hit commits")
	testing.expect(t, near_f32(run.player.bighit_charge, charge_before), "refused dash must leave committed charge intact")
	testing.expect(t, run.player.dash_timer == 0, "refused dash must not start its timer")

	run.player.bighit_charge = ar.SIM_DT * .5
	ar.tick_big_hit(&run)
	testing.expect(t, !ar.bighit_charging(&run.player), "completed charge must fire")
	testing.expect(t, near_f32(run.player.bighit_timer, ar.BIGHIT_COOLDOWN), "completed Big Hit must pay the full cooldown")
}

@(test)
m8_time_skip_slows_only_enemy_clocks :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(8158, 0), .Warden)
	defer ar.run_destroy(&run)
	m8_prepare_arena(&run)
	enemy := ar.enemy_make(.Ghoul, {15.5, 10.5}, 1)
	enemy.cooldown = 1
	enemy.ability_count = 1
	enemy.ability_cds[0] = 1
	append(&run.enemies, enemy)

	mana_before := run.player.mana
	testing.expect(t, ar.player_cast_class_skill(&run, {1, 0}), "fresh Warden should cast Time Skip")
	testing.expect(t, near_f32(mana_before-run.player.mana, 18), "Time Skip must cost 18 mana")
	testing.expect(t, near_f32(run.player.class_skill_timer, 3.2) && near_f32(run.player.time_skip_timer, 3), "Time Skip timers changed")
	ar.sim_tick(&run, {})
	testing.expect(t, near_f32(run.player.class_skill_timer, 3.2-ar.SIM_DT) && near_f32(run.player.time_skip_timer, 3-ar.SIM_DT), "player clocks must advance at full time")
	testing.expect(t, near_f32(run.enemies[0].cooldown, 1-ar.SIM_DT*ar.TIME_SKIP_FACTOR), "enemy recovery must run at 40% time")
	testing.expect(t, near_f32(run.enemies[0].ability_cds[0], 1-ar.SIM_DT*ar.TIME_SKIP_FACTOR), "enemy ability recovery must run at 40% time")
}

@(test)
m8_frost_nova_hits_only_its_los_radius :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(8168, 0), .Arcanist)
	defer ar.run_destroy(&run)
	m8_prepare_arena(&run)
	inside := ar.enemy_make(.Ghoul, {11.5, 10.5}, 1)
	outside := ar.enemy_make(.Ghoul, {13.5, 10.5}, 1)
	append(&run.enemies, inside)
	append(&run.enemies, outside)
	rng_copy := run.combat_rng
	expected := 10 + run.player.level*2 + ar.ARCHETYPES[.Arcanist].spell_bonus + ar.rng_range(&rng_copy, 0, 5)
	mana_before := run.player.mana

	testing.expect(t, ar.player_cast_class_skill(&run, {1, 0}), "fresh Arcanist should cast Frost Nova")
	testing.expect(t, near_f32(mana_before-run.player.mana, 14) && near_f32(run.player.class_skill_timer, 2.65), "Frost Nova cost/cooldown changed")
	testing.expectf(t, run.enemies[0].hp == inside.max_hp-expected, "Nova dealt %v, want %v", inside.max_hp-run.enemies[0].hp, expected)
	testing.expect(t, near_f32(run.enemies[0].statuses[.Chilled], 1.2), "Nova must chill for 1.2 seconds")
	testing.expect(t, run.enemies[1].hp == outside.max_hp, "Nova must not hit beyond 2.45 tiles")
}

@(test)
m8_ambush_bell_arms_lures_and_backstabs :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(8178, 0), .Rogue)
	defer ar.run_destroy(&run)
	m8_prepare_arena(&run)
	mana_before := run.player.mana
	clear(&run.sfx)
	testing.expect(t, ar.player_cast_class_skill(&run, {1, 0}), "fresh Rogue should cast Ambush Bell")
	testing.expect(t, near_f32(mana_before-run.player.mana, 18) && near_f32(run.player.class_skill_timer, 3.2), "Ambush Bell cost/cooldown changed")
	testing.expect(t, len(run.bells) == 1, "Ambush Bell must replace the active lure")
	bell_cues:=0
	for cue in run.sfx do if cue==.Bell do bell_cues+=1
	testing.expect(t,bell_cues==1,"placing an Ambush Bell must emit exactly one Bell cue")
	if len(run.bells) == 0 do return
	bell_pos := run.bells[0].pos
	testing.expect(t, near_f32(run.bells[0].arm_timer, .34) && near_f32(run.bells[0].lifetime, 6), "Ambush Bell arming/lifetime changed")

	enemy := ar.enemy_make(.Ghoul, bell_pos+ar.Vec2{2,0}, 1)
	append(&run.enemies, enemy)
	ar.tick_ambush_bells(&run, .34)
	lure, found := ar.ambush_lure_position(&run, &run.enemies[0])
	testing.expect(t, found && lure == bell_pos, "armed bell must lure a visible nonboss")
	boss := run.enemies[0]
	boss.role = .Boss
	_, boss_lured := ar.ambush_lure_position(&run, &boss)
	testing.expect(t, !boss_lured, "bosses must ignore Ambush Bell lure")

	run.enemies[0].pos = bell_pos + ar.Vec2{.5,0}
	run.enemies[0].prev_pos = run.enemies[0].pos
	run.enemies[0].facing = {-1,0}
	hp_before := run.enemies[0].hp
	clear(&run.sfx)
	ar.tick_ambush_bells(&run, 0)
	testing.expect(t, len(run.bells) == 0, "triggered bell must be consumed")
	testing.expectf(t, hp_before-run.enemies[0].hp == 35, "facing primary bell hit dealt %v, want 35", hp_before-run.enemies[0].hp)
	bell_cues=0
	for cue in run.sfx do if cue==.Bell do bell_cues+=1
	testing.expect(t,bell_cues==1,"detonating an Ambush Bell must emit exactly one Bell cue")
}

@(test)
m8_big_hit_warden_cleave_keeps_full_damage_and_throw :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(8188, 0), .Warden)
	defer ar.run_destroy(&run)
	m8_prepare_arena(&run)
	first := ar.enemy_make(.Ghoul, {11.3,10.5}, 1)
	second := ar.enemy_make(.Ghoul, {11.4,10.8}, 1)
	first.hp, first.max_hp = 999, 999
	second.hp, second.max_hp = 999, 999
	append(&run.enemies, first)
	append(&run.enemies, second)
	rng_copy := run.combat_rng
	base := ar.player_melee_damage(&run.player)*3
	expected_first := base + ar.rng_range(&rng_copy,-4,7)
	expected_second := base + ar.rng_range(&rng_copy,-4,7)

	ar.player_big_hit_fire(&run)
	testing.expect(t, 999-run.enemies[0].hp == expected_first && 999-run.enemies[1].hp == expected_second, "Warden Big Hit must cleave every target at full rolled damage")
	testing.expect(t, near_f32(math.hypot(run.enemies[0].knockback_vel.x,run.enemies[0].knockback_vel.y),20) && near_f32(math.hypot(run.enemies[1].knockback_vel.x,run.enemies[1].knockback_vel.y),20), "Warden Big Hit must throw every target two tiles")
}

@(test)
m8_combined_proc_union_and_poison_ticks :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(8198, 0), .Warden)
	defer ar.run_destroy(&run)
	m8_prepare_arena(&run)
	run.player.has_weapon = true
	run.player.weapon = ar.Item{kind=.Weapon, name="Double proc", proc_chance=1}
	run.player.weapon.proc_effects[.Poison] = true
	run.player.weapon.proc_effects[.Chain] = true
	primary := ar.enemy_make(.Ghoul,{11.5,10.5},1)
	secondary := ar.enemy_make(.Rune_Sentinel,{12.5,10.5},1)
	append(&run.enemies, primary)
	append(&run.enemies, secondary)
	secondary_hp := run.enemies[1].hp

	dealt := ar.player_damage_enemy(&run,&run.enemies[0],9,.Physical)
	testing.expect(t, dealt == 9 && near_f32(run.enemies[0].statuses[.Poisoned],1.4), "poison proc from the union must apply for 1.4 seconds")
	testing.expect(t, secondary_hp-run.enemies[1].hp == 3, "chain must deal one-third direct damage without arcane mitigation")
	run.enemies[0].poison_tick = ar.SIM_DT*.5
	primary_hp := run.enemies[0].hp
	ar.tick_combat_statuses(&run)
	testing.expect(t, primary_hp-run.enemies[0].hp == 2, "level-one enemy poison tick must deal 2 direct damage")
	testing.expect(t, near_f32(run.enemies[0].poison_tick,1-ar.SIM_DT*.5), "enemy poison clock must keep its one-second cadence")

	run.depth = 6
	run.player.hp = run.player.max_hp
	ar.player_apply_status(&run.player,.Poisoned,1.2)
	run.player.poison_tick = ar.SIM_DT*.5
	player_hp := run.player.hp
	ar.tick_combat_statuses(&run)
	testing.expect(t, player_hp-run.player.hp == 3, "depth-six player poison tick must deal 3 direct damage")
}

@(test)
m8_action_timers_tick_independently :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(8208, 0), .Warden)
	defer ar.run_destroy(&run)
	clear(&run.enemies)
	clear(&run.projectiles)
	run.player.melee_timer = .7
	run.player.bolt_timer = 1.1
	run.player.dash_timer = 1.5
	run.player.class_skill_timer = 1.9
	run.player.bighit_timer = 2.3
	run.player.time_skip_timer = 2.7
	ar.sim_tick(&run, {})
	testing.expect(t, near_f32(run.player.melee_timer, .7 - ar.SIM_DT), "melee clock did not tick independently")
	testing.expect(t, near_f32(run.player.bolt_timer, 1.1 - ar.SIM_DT), "bolt clock did not tick independently")
	testing.expect(t, near_f32(run.player.dash_timer, 1.5 - ar.SIM_DT), "dash clock did not tick independently")
	testing.expect(t, near_f32(run.player.class_skill_timer, 1.9 - ar.SIM_DT), "class-skill clock did not tick independently")
	testing.expect(t, near_f32(run.player.bighit_timer, 2.3 - ar.SIM_DT), "Big Hit clock did not tick independently")
	testing.expect(t, near_f32(run.player.time_skip_timer, 2.7 - ar.SIM_DT), "Time Skip clock did not tick independently")
}

@(test)
m8_cursed_unknown_and_scroll_semantics :: proc(t: ^testing.T) {
	bargain := ar.Item{
		kind = .Weapon,
		name = "Tempting Blade",
		rarity = .Rare,
		power = 5,
		attack_speed = .05,
		move_speed = .02,
		proc_chance = .10,
	}
	ar.apply_cursed_bargain(&bargain)
	testing.expect(t, bargain.cursed && bargain.rarity == .Cursed, "cursed bargain must mark the item and rarity")
	testing.expect(t, bargain.power == 9, "weapon bargain must add four power")
	testing.expect(t, near_f32(bargain.attack_speed, .08) && near_f32(bargain.move_speed, -.01), "weapon bargain handling tradeoff changed")
	testing.expect(t, near_f32(bargain.proc_chance, .18), "weapon bargain proc bonus changed")

	mystery := ar.Item{kind = .Weapon, name = "Hidden Saber", rarity = .Rare, power = 7, unidentified = true}
	testing.expect(t, ar.item_display_name(mystery) == "Unidentified Weapon", "unknown weapon name must stay hidden")
	testing.expect(t, ar.item_visible_rarity(mystery) == .Unidentified, "unknown rarity must stay hidden")
	carrier: ar.Player
	carrier.bag[0] = mystery
	carrier.bag_count = 1
	ar.equip_from_bag(&carrier, 0)
	testing.expect(t, carrier.has_weapon && carrier.weapon.name == "Hidden Saber", "unknown equipment must equip normally")
	testing.expect(t, !carrier.weapon.unidentified && carrier.bag_count == 0, "equipping must identify and remove the bag item")

	locked: ar.Player
	locked.weapon = bargain
	locked.has_weapon = true
	locked.bag[0] = ar.Item{kind = .Weapon, name = "Plain Sword", power = 3}
	locked.bag_count = 1
	ar.equip_from_bag(&locked, 0)
	testing.expect(t, locked.weapon.name == "Tempting Blade", "cursed equipped weapon must block replacement")
	testing.expect(t, locked.bag_count == 1 && locked.bag[0].name == "Plain Sword", "blocked replacement must stay in the bag")

	identifier: ar.Player
	identifier.bag[0] = ar.Item{kind = .Armor, name = "Weak Mystery", rarity = .Rare, defense = 2, unidentified = true}
	identifier.bag[1] = ar.Item{kind = .Weapon, name = "Strong Mystery", rarity = .Magic, power = 8, unidentified = true}
	identifier.bag[2] = ar.Item{kind = .Identify_Scroll, name = "Scroll of Identify"}
	identifier.bag_count = 3
	ar.equip_from_bag(&identifier, 2)
	testing.expect(t, identifier.bag_count == 2, "identify scroll must be consumed")
	testing.expect(t, identifier.bag[0].unidentified && !identifier.bag[1].unidentified, "identify must reveal the strongest unknown item")
	empty_identify: ar.Player
	empty_identify.bag[0] = ar.Item{kind = .Identify_Scroll, name = "Scroll of Identify"}
	empty_identify.bag_count = 1
	ar.equip_from_bag(&empty_identify, 0)
	testing.expect(t, empty_identify.bag_count == 0, "identify scroll is consumed even when nothing is unknown")

	no_curse: ar.Player
	no_curse.bag[0] = ar.Item{kind = .Remove_Curse_Scroll, name = "Scroll of Remove Curse"}
	no_curse.bag_count = 1
	ar.equip_from_bag(&no_curse, 0)
	testing.expect(t, no_curse.bag_count == 1, "scarce remove-curse scroll must survive when there is no target")

	cleanse: ar.Player
	cleanse.weapon = bargain
	cleanse.has_weapon = true
	cleanse.armor = ar.Item{kind = .Armor, name = "Cursed Mail", rarity = .Cursed, cursed = true}
	cleanse.has_armor = true
	cleanse.bag[0] = ar.Item{kind = .Remove_Curse_Scroll, name = "Scroll of Remove Curse"}
	cleanse.bag_count = 1
	ar.equip_from_bag(&cleanse, 0)
	testing.expect(t, !cleanse.weapon.cursed && cleanse.armor.cursed, "remove curse must prefer equipped weapon before armor")
	testing.expect(t, cleanse.weapon.rarity == .Rare && cleanse.weapon.power == 9, "cleansing must keep bargain power and return rolled gear to Rare")
	testing.expect(t, near_f32(cleanse.weapon.move_speed, .02), "cleansing must undo the weapon handling penalty")
	testing.expect(t, cleanse.bag_count == 0, "successful remove curse must consume its scroll")
}

@(test)
m8_combat_rng_is_deterministic_and_isolated_from_loot :: proc(t: ^testing.T) {
	a, b: ar.Run
	seed := ar.derive_seed(8308, 0)
	ar.run_start(&a, seed, .Rogue)
	ar.run_start(&b, seed, .Rogue)
	defer ar.run_destroy(&a)
	defer ar.run_destroy(&b)
	a.player.precision_rank = 5
	b.player.precision_rank = 5

	loot_reference := a.loot_rng
	for _ in 0 ..< 32 {
		crit_a, multiplier_a := ar.roll_rogue_crit(&a)
		crit_b, multiplier_b := ar.roll_rogue_crit(&b)
		testing.expect(t, crit_a == crit_b && multiplier_a == multiplier_b, "same-seed combat RNG must replay exactly")
	}
	testing.expect(t, ar.rng_next(&a.loot_rng) == ar.rng_next(&loot_reference), "combat rolls must not advance the loot stream")

	combat_reference := b.combat_rng
	for i in 0 ..< 24 do _ = ar.make_loot(&b.loot_rng, {f32(i), 0})
	testing.expect(t, ar.rng_next(&b.combat_rng) == ar.rng_next(&combat_reference), "loot rolls must not advance the combat stream")
}
