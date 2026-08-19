package archrogue_tests

// M8 companion and precision seams. These tests keep the summon simulation
// raylib-free and exercise it through the same Run state used by gameplay.

import "core:math"
import "core:testing"
import ar "../src"

COMPANION_TEST_EPS :: f32(1e-4)

@(private = "file")
companion_test_prepare_arena :: proc(run: ^ar.Run) {
	for x in 0 ..< ar.MAP_W {
		for y in 0 ..< ar.MAP_H {
			run.dungeon.tiles[x][y] = .Wall
		}
	}
	for x in 6 ..= 16 {
		for y in 6 ..= 14 {
			run.dungeon.tiles[x][y] = .Floor
		}
	}
	run.dungeon.special_room_count = 0
	run.dungeon.bar_furnishings = {}
	run.dungeon.hall_furnishings = {}
	run.dungeon.solid_props = {}
	run.dungeon.stairs = {0, 0}
	run.player.pos = {10.5, 10.5}
	run.player.prev_pos = run.player.pos
	clear(&run.enemies)
	clear(&run.projectiles)
	clear(&run.familiars)
	clear(&run.bells)
	clear(&run.numbers)
	clear(&run.ground_items)
	clear(&run.sfx)
}

@(test)
acolyte_spirit_call_cost_cooldown_recast_and_descent :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(801, 0), .Acolyte)
	defer ar.run_destroy(&run)

	mana_cost := ar.player_class_skill_mana_cost(&run.player)
	cooldown := ar.player_class_skill_cooldown(&run.player)
	mana_before := run.player.mana
	ok := ar.player_cast_spirit_call(&run)
	testing.expect(t, ok, "fresh Acolyte should cast Spirit Call")
	testing.expectf(t, len(run.familiars) == 1, "rank-zero Spirit Call made %v familiars, want 1", len(run.familiars))
	testing.expectf(t, abs(run.player.mana - (mana_before - mana_cost)) < COMPANION_TEST_EPS, "Spirit Call mana %.3f, want %.3f", run.player.mana, mana_before - mana_cost)
	testing.expectf(t, abs(run.player.class_skill_timer - cooldown) < COMPANION_TEST_EPS, "Spirit Call cooldown %.3f, want %.3f", run.player.class_skill_timer, cooldown)
	if len(run.familiars) == 0 do return
	testing.expect(t, run.familiars[0].kind == .Wisp, "rank-zero Spirit Call should summon a Wisp")

	// Recasting replaces the host and restores its health; it never stacks it.
	run.familiars[0].hp = 1
	run.player.class_skill_timer = 0
	mana_before = run.player.mana
	ok = ar.player_cast_spirit_call(&run)
	testing.expect(t, ok, "ready Acolyte should be able to recast Spirit Call")
	testing.expectf(t, len(run.familiars) == 1, "recast stacked the host: got %v familiars", len(run.familiars))
	testing.expectf(t, abs(run.player.mana - (mana_before - mana_cost)) < COMPANION_TEST_EPS, "recast did not pay the normal mana cost")
	if len(run.familiars) == 0 do return
	testing.expect(t, run.familiars[0].hp == run.familiars[0].max_hp, "recast should recreate the host at full health")

	ar.run_descend(&run)
	testing.expect(t, len(run.familiars) == 0, "familiars must not cross a floor descent")
}

@(test)
floor_descent_resets_actions_and_restores_quarter_resources :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(811, 0), .Acolyte)
	defer ar.run_destroy(&run)

	run.player.mana = 1
	run.player.stamina = 2
	run.player.melee_timer = 1
	run.player.bolt_timer = 2
	run.player.dash_timer = 3
	run.player.class_skill_timer = 4
	run.player.time_skip_timer = 5
	run.player.bighit_timer = 6
	run.player.bighit_charge = .4
	run.player.swing_timer = .3
	run.player.hit_flash = 1
	run.player.potion_timer = .7

	want_mana := min(f32(run.player.max_mana), f32(1) + f32(run.player.max_mana) * .25)
	want_stamina := min(f32(run.player.max_stamina), f32(2) + f32(run.player.max_stamina) * .25)
	ar.run_descend(&run)

	testing.expect(t, run.player.melee_timer == 0 && run.player.bolt_timer == 0, "descent must clear melee and bolt recoveries")
	testing.expect(t, run.player.dash_timer == 0 && run.player.class_skill_timer == 0, "descent must clear dash and class recoveries")
	testing.expect(t, run.player.time_skip_timer == 0 && run.player.bighit_timer == 0, "descent must clear Time Skip and Big Hit recoveries")
	testing.expect(t, run.player.bighit_charge == 0 && run.player.swing_timer == 0, "descent must cancel transient action state")
	testing.expect(t, run.player.hit_flash == 0, "descent must clear transient hit flash")
	testing.expect(t, abs(run.player.mana - want_mana) < COMPANION_TEST_EPS && abs(run.player.stamina - want_stamina) < COMPANION_TEST_EPS, "descent must restore 25% of max mana and stamina")
	testing.expect(t, abs(run.player.potion_timer - .7) < COMPANION_TEST_EPS, "descent must preserve the potion cooldown")
}

@(test)
spirit_rank_helper_ports_crow_and_host_count_steps :: proc(t: ^testing.T) {
	rank_zero := ar.spirit_call_stats(0)
	testing.expect(t, rank_zero.kind == .Wisp && rank_zero.count == 1, "rank zero should be one Wisp")
	testing.expect(t, rank_zero.hp == 20 && rank_zero.damage == 6, "rank-zero Wisp stats should be 20 hp / 6 damage")

	rank_one := ar.spirit_call_stats(1)
	testing.expect(t, rank_one.kind == .Crow && rank_one.count == 1, "rank one should replace the Wisp with one Crow")
	testing.expect(t, rank_one.hp == 32 && rank_one.damage == 8, "rank-one Crow stats should be 32 hp / 8 damage")

	rank_three := ar.spirit_call_stats(3)
	testing.expect(t, rank_three.kind == .Crow && rank_three.count == 2, "rank three should summon two Crows")
	testing.expect(t, rank_three.hp == 42 && rank_three.damage == 10, "rank-three Crow stats should be 42 hp / 10 damage")

	rank_five := ar.spirit_call_stats(5)
	testing.expect(t, rank_five.kind == .Crow && rank_five.count == 3, "rank five should summon three Crows")
	testing.expect(t, rank_five.hp == 82 && rank_five.damage == 14, "rank-five Crow stats should be 82 hp / 14 damage")
	testing.expect(t, rank_five.champion && rank_five.unkillable, "rank five should enable champion and unkillable host traits")
	testing.expect(t, ar.spirit_call_stats(99) == rank_five, "Spirit rank should clamp at five")

	run: ar.Run
	ar.run_start(&run, ar.derive_seed(802, 0), .Acolyte)
	defer ar.run_destroy(&run)
	ok := ar.player_cast_spirit_call_rank(&run, 3)
	testing.expect(t, ok, "rank-three Spirit Call should cast")
	testing.expectf(t, len(run.familiars) == 2, "rank-three cast made %v familiars, want 2", len(run.familiars))
	for familiar in run.familiars {
		testing.expect(t, familiar.kind == .Crow && familiar.spirit_rank == 3, "rank-three host should contain rank-three Crows")
	}
}

@(test)
acolyte_wisp_relocates_when_authored_orbit_hits_wall :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(812, 0), .Acolyte)
	defer ar.run_destroy(&run)
	companion_test_prepare_arena(&run)
	for x in 0 ..< ar.MAP_W do for y in 0 ..< ar.MAP_H do run.dungeon.tiles[x][y] = .Wall
	run.dungeon.tiles[10][10] = .Floor
	run.dungeon.tiles[10][11] = .Floor
	run.player.mana = f32(run.player.max_mana)
	run.player.class_skill_timer = 0

	naive_angle := f32(0.7)
	naive := run.player.pos + ar.Vec2{math.cos(naive_angle), math.sin(naive_angle)} * ar.SPIRIT_CALL_SPAWN_RADIUS
	testing.expect(t, ar.blocked_for_radius(
		&run.dungeon, naive.x, naive.y, ar.FAMILIAR_MOVE_COLLISION_RADIUS, block_stairs = true,
	), "test setup must block the Wisp's authored orbit position")

	ok := ar.player_cast_spirit_call_rank(&run, 0)
	testing.expect(t, ok && len(run.familiars) == 1, "Wisp should relocate to nearby valid floor")
	if len(run.familiars) == 0 do return
	wisp := run.familiars[0]
	testing.expect(t, wisp.kind == .Wisp, "rank-zero safe spawn must remain a Wisp")
	testing.expect(t, !ar.blocked_for_radius(
		&run.dungeon, wisp.pos.x, wisp.pos.y, ar.FAMILIAR_MOVE_COLLISION_RADIUS, block_stairs = true,
	), "Wisp spawned inside wall or reserved geometry")
}

@(test)
acolyte_crows_all_relocate_when_authored_orbits_hit_walls :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(813, 0), .Acolyte)
	defer ar.run_destroy(&run)
	companion_test_prepare_arena(&run)
	stats := ar.spirit_call_stats(5)
	for index in 0 ..< stats.count {
		angle := f32(index) / f32(stats.count) * (2 * math.PI) + 0.7
		naive := run.player.pos + ar.Vec2{math.cos(angle), math.sin(angle)} * ar.SPIRIT_CALL_SPAWN_RADIUS
		run.dungeon.tiles[int(naive.x)][int(naive.y)] = .Wall
	}
	run.player.mana = f32(run.player.max_mana)
	run.player.class_skill_timer = 0

	ok := ar.player_cast_spirit_call_rank(&run, 5)
	testing.expect(t, ok, "three-Crow Spirit Call should find alternate floor positions")
	testing.expectf(t, len(run.familiars) == stats.count, "safe Crow summon made %v familiars, want %v", len(run.familiars), stats.count)
	for familiar, index in run.familiars {
		testing.expect(t, familiar.kind == .Crow, "safe rank-five spawn changed familiar kind")
		testing.expectf(t, !ar.blocked_for_radius(
			&run.dungeon, familiar.pos.x, familiar.pos.y, ar.FAMILIAR_MOVE_COLLISION_RADIUS, block_stairs = true,
		), "Crow %v spawned inside wall or reserved geometry at %v", index, familiar.pos)
		for other in 0 ..< index {
			delta := familiar.pos - run.familiars[other].pos
			testing.expect(t,
				delta.x * delta.x + delta.y * delta.y >= ar.SPIRIT_CALL_SPAWN_SEPARATION * ar.SPIRIT_CALL_SPAWN_SEPARATION,
				"safe Crow spawns must not overlap",
			)
		}
	}
}

@(test)
acolyte_spirit_call_safe_spawn_failure_spends_nothing :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(814, 0), .Acolyte)
	defer ar.run_destroy(&run)
	companion_test_prepare_arena(&run)
	for x in 0 ..< ar.MAP_W do for y in 0 ..< ar.MAP_H do run.dungeon.tiles[x][y] = .Wall
	run.dungeon.tiles[10][10] = .Floor
	run.player.mana = f32(run.player.max_mana)
	run.player.class_skill_timer = 0
	mana_before := run.player.mana
	timer_before := run.player.class_skill_timer

	ok := ar.player_cast_spirit_call_rank(&run, 5)
	testing.expect(t, !ok, "Spirit Call must fail rather than spawn a Crow inside sealed geometry")
	testing.expect(t, len(run.familiars) == 0, "failed safe spawn created a familiar")
	testing.expect(t, run.player.mana == mana_before, "failed safe spawn spent mana")
	testing.expect(t, run.player.class_skill_timer == timer_before, "failed safe spawn started cooldown")
}

@(test)
ranger_beast_uses_half_mana_and_living_beast_commands_are_free :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(803, 0), .Ranger)
	defer ar.run_destroy(&run)

	mana_before := run.player.mana
	expected_cost := f32(run.player.max_mana) * ar.SPIRIT_BEAST_MANA_FRACTION
	ok := ar.player_cast_spirit_beast(&run)
	testing.expect(t, ok, "fresh Ranger should summon a Spirit Beast")
	testing.expectf(t, len(run.familiars) == 1, "Spirit Beast summon made %v familiars, want 1", len(run.familiars))
	testing.expectf(t, abs(run.player.mana - (mana_before - expected_cost)) < COMPANION_TEST_EPS, "Spirit Beast should cost half maximum mana")
	testing.expectf(t, abs(run.player.class_skill_timer - ar.SPIRIT_BEAST_REPLACE_COOLDOWN) < COMPANION_TEST_EPS, "Spirit Beast replacement cooldown should be 60 seconds")
	if len(run.familiars) == 0 do return
	beast := &run.familiars[0]
	testing.expect(t, beast.kind == .Spirit_Beast && beast.command == .Attack, "new Spirit Beast should begin in Attack mode")
	testing.expect(t, beast.hp == 60 && beast.damage == 12, "rank-zero Spirit Beast should have 60 hp / 12 damage")

	next, available := ar.spirit_beast_next_command(&run)
	testing.expect(t, available && next == .Follow, "Attack mode should advertise the free Return/Follow command")
	beast.hp = 1
	run.player.mana = 0
	timer_before := run.player.class_skill_timer
	ok = ar.player_cast_spirit_beast(&run)
	testing.expect(t, ok, "living Spirit Beast command should ignore mana and replacement cooldown")
	testing.expect(t, len(run.familiars) == 1 && run.familiars[0].command == .Follow, "first command should switch the beast to Follow")
	testing.expect(t, run.familiars[0].hp == 1, "commanding a living beast must not heal it")
	testing.expect(t, run.player.mana == 0 && run.player.class_skill_timer == timer_before, "living-beast command should spend no resource or cooldown")

	next, available = ar.spirit_beast_next_command(&run)
	testing.expect(t, available && next == .Attack, "Follow mode should advertise the free Attack command")
	ok = ar.player_cast_spirit_beast(&run)
	testing.expect(t, ok && run.familiars[0].command == .Attack, "second command should switch the beast back to Attack")
	testing.expect(t, run.familiars[0].hp == 1 && run.player.mana == 0, "repeated commands must remain free and must not heal")
}

@(test)
ranger_beast_safe_spawn_failure_spends_nothing :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(804, 0), .Ranger)
	defer ar.run_destroy(&run)

	for x in 0 ..< ar.MAP_W {
		for y in 0 ..< ar.MAP_H {
			run.dungeon.tiles[x][y] = .Wall
		}
	}
	run.player.pos = {20.5, 20.5}
	run.player.prev_pos = run.player.pos
	run.dungeon.tiles[20][20] = .Floor
	clear(&run.familiars)
	mana_before := run.player.mana
	timer_before := run.player.class_skill_timer

	ok := ar.player_cast_spirit_beast(&run)
	testing.expect(t, !ok, "Spirit Beast should fail when no radius-clear LOS spawn exists")
	testing.expect(t, len(run.familiars) == 0, "failed Spirit Beast cast should not create a familiar")
	testing.expect(t, run.player.mana == mana_before, "failed Spirit Beast cast should not spend mana")
	testing.expect(t, run.player.class_skill_timer == timer_before, "failed Spirit Beast cast should not start cooldown")
}

@(test)
familiar_ai_requires_los_then_follows_attacks_and_culls :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(805, 0), .Acolyte)
	defer ar.run_destroy(&run)
	companion_test_prepare_arena(&run)
	run.player.mana = f32(run.player.max_mana)
	run.player.class_skill_timer = 0
	testing.expect(t, ar.player_cast_spirit_call(&run), "arena Spirit Call should cast")
	if len(run.familiars) == 0 do return
	run.familiars[0].pos = run.player.pos
	run.familiars[0].prev_pos = run.player.pos

	enemy := ar.enemy_make(.Ghoul, {13.5, 10.5}, 1)
	enemy.hp = 999
	enemy.max_hp = 999
	enemy.cooldown = 999
	append(&run.enemies, enemy)
	run.dungeon.tiles[12][10] = .Wall
	enemy_hp := run.enemies[0].hp
	familiar_pos := run.familiars[0].pos
	ar.tick_familiars_dt(&run, 0.5)
	testing.expect(t, run.enemies[0].hp == enemy_hp, "familiar attacked an enemy through a wall")
	testing.expect(t, run.familiars[0].pos == familiar_pos, "blocked target should leave an in-range follower with its owner")

	run.dungeon.tiles[12][10] = .Floor
	for _ in 0 ..< 30 {
		ar.tick_familiars_dt(&run, 0.1)
	}
	testing.expect(t, run.enemies[0].hp < enemy_hp, "LOS-clear familiar did not pursue and attack its target")
	testing.expect(t, run.familiars[0].pos.x > familiar_pos.x, "attacking familiar did not approach its target")

	run.familiars[0].hp = 0
	ar.tick_familiars_dt(&run, 0.1)
	testing.expect(t, len(run.familiars) == 0, "dead familiar was not culled from the host")
}

@(test)
spirit_beast_follow_command_ignores_adjacent_enemies :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(806, 0), .Ranger)
	defer ar.run_destroy(&run)
	companion_test_prepare_arena(&run)
	run.player.mana = f32(run.player.max_mana)
	run.player.class_skill_timer = 0
	testing.expect(t, ar.player_cast_spirit_beast(&run), "arena Spirit Beast should cast")
	if len(run.familiars) == 0 do return

	beast := &run.familiars[0]
	beast.pos = {13.5, 10.5}
	beast.prev_pos = beast.pos
	beast.command = .Follow
	enemy := ar.enemy_make(.Ghoul, {13.8, 10.5}, 1)
	enemy.hp = 100
	enemy.max_hp = 100
	enemy.cooldown = 999
	append(&run.enemies, enemy)
	enemy_hp := run.enemies[0].hp
	start_x := beast.pos.x

	ar.tick_familiars_dt(&run, 0.1)
	testing.expect(t, run.familiars[0].pos.x < start_x, "Follow command did not move Spirit Beast toward its owner")
	testing.expect(t, run.enemies[0].hp == enemy_hp, "Follow command should ignore even an adjacent enemy")
}

@(test)
enemy_projectile_is_intercepted_by_familiar_before_player :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(807, 0), .Acolyte)
	defer ar.run_destroy(&run)
	companion_test_prepare_arena(&run)
	run.player.mana = f32(run.player.max_mana)
	run.player.class_skill_timer = 0
	testing.expect(t, ar.player_cast_spirit_call(&run), "arena Spirit Call should cast")
	if len(run.familiars) == 0 do return

	familiar_pos := run.familiars[0].pos
	testing.expect(t, ar.familiar_intercepting_projectile(&run, familiar_pos) != nil, "projectile overlap should find a living familiar")
	testing.expect(t, ar.familiar_intercepting_projectile(&run, familiar_pos + ar.Vec2{2, 0}) == nil, "far projectile should not find a familiar")
	familiar_hp := run.familiars[0].hp
	player_hp := run.player.hp
	append(&run.projectiles, ar.Projectile{
		pos = familiar_pos,
		prev_pos = familiar_pos,
		vel = {},
		damage = 5,
		damage_type = .Physical,
		from_player = false,
		ttl = 1,
	})

	ar.sim_tick(&run, {})
	testing.expect(t, len(run.projectiles) == 0, "intercepted enemy projectile should be consumed")
	testing.expect(t, run.familiars[0].hp == familiar_hp - 5, "intercepted projectile should damage the familiar")
	testing.expect(t, run.player.hp == player_hp, "familiar-intercepted projectile should not damage the player")
}

@(test)
familiar_attack_uses_combat_rng_without_mutating_loot_rng :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(808, 0), .Acolyte)
	defer ar.run_destroy(&run)
	companion_test_prepare_arena(&run)
	run.player.mana = f32(run.player.max_mana)
	run.player.class_skill_timer = 0
	testing.expect(t, ar.player_cast_spirit_call(&run), "arena Spirit Call should cast")
	if len(run.familiars) == 0 do return
	run.familiars[0].pos = run.player.pos
	run.familiars[0].prev_pos = run.player.pos
	enemy := ar.enemy_make(.Ghoul, {11.4, 10.5}, 1)
	enemy.hp = 100
	enemy.max_hp = 100
	enemy.cooldown = 999
	append(&run.enemies, enemy)

	loot_before := run.loot_rng
	combat_before := run.combat_rng
	ar.tick_familiars_dt(&run, 0.01)
	testing.expect(t, run.enemies[0].hp < 100, "familiar did not attack the in-range target")
	testing.expect(t, run.loot_rng == loot_before, "familiar combat consumed the deterministic loot stream")
	testing.expect(t, run.combat_rng != combat_before, "familiar damage roll did not consume the combat RNG stream")
}

@(test)
rogue_precision_rank_zero_is_inert_and_seeded_ranks_are_deterministic :: proc(t: ^testing.T) {
	cases := [?]struct {
		rank:       u8,
		chance:     f32,
		multiplier: f32,
	}{
		{0, 0, 1},
		{1, 0.15, 1.60},
		{2, 0.20, 1.75},
		{3, 0.28, 1.95},
		{4, 0.34, 2.10},
		{5, 0.40, 2.25},
	}
	for c in cases {
		chance, multiplier := ar.rogue_crit_profile(c.rank)
		testing.expectf(t, abs(chance - c.chance) < COMPANION_TEST_EPS, "precision rank %v chance %.3f, want %.3f", c.rank, chance, c.chance)
		testing.expectf(t, abs(multiplier - c.multiplier) < COMPANION_TEST_EPS, "precision rank %v multiplier %.3f, want %.3f", c.rank, multiplier, c.multiplier)
	}
	clamped_chance, clamped_multiplier := ar.rogue_crit_profile(255)
	testing.expect(t, abs(clamped_chance - f32(0.40)) < COMPANION_TEST_EPS && abs(clamped_multiplier - f32(2.25)) < COMPANION_TEST_EPS, "precision rank should clamp at five")
	testing.expect(t, ar.rogue_crit_poison_duration(1) == f32(1.2), "base Precision poison duration changed")
	testing.expect(t, ar.rogue_crit_poison_duration(2) == f32(2.2) && ar.rogue_crit_poison_duration(5) == f32(2.2), "Venom and its descendants must keep the longer poison rider")

	seed := ar.derive_seed(809, 0)
	run_a, run_b: ar.Run
	ar.run_start(&run_a, seed, .Rogue)
	defer ar.run_destroy(&run_a)
	ar.run_start(&run_b, seed, .Rogue)
	defer ar.run_destroy(&run_b)

	before := run_a.combat_rng
	critical, multiplier := ar.roll_rogue_crit(&run_a)
	testing.expect(t, !critical && multiplier == 1, "rank-zero Rogue precision should never crit")
	testing.expect(t, run_a.combat_rng == before, "inert rank-zero precision should not consume combat RNG")

	run_a.player.precision_rank = 1
	run_b.player.precision_rank = 1
	critical_a, multiplier_a := ar.roll_rogue_crit(&run_a, 10)
	critical_b, multiplier_b := ar.roll_rogue_crit(&run_b, 10)
	testing.expect(t, critical_a && critical_b, "100% scaled precision roll should crit")
	testing.expect(t, multiplier_a == f32(1.60) && multiplier_b == multiplier_a, "seeded rank-one roll should return its 1.60 multiplier")
	testing.expect(t, run_a.combat_rng == run_b.combat_rng, "same-seed precision rolls should advance identically")
}
