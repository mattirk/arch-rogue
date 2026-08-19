package archrogue_tests

// MX.2 combat correctness: boss ability selection, tactical doctrines,
// routing/stuck recovery, knockback physics, and elite identity. Each test
// pins the pygame contract the port was written against.

import "core:testing"
import "core:math"
import ar "../src"

@(private = "file")
mx2_arena :: proc(run: ^ar.Run) {
	for x in 0 ..< ar.MAP_W {
		for y in 0 ..< ar.MAP_H do run.dungeon.tiles[x][y] = .Wall
	}
	for x in 6 ..= 18 {
		for y in 6 ..= 16 do run.dungeon.tiles[x][y] = .Floor
	}
	run.dungeon.bar_furnishings = {}
	run.player.pos = {10.5, 10.5}
	run.player.prev_pos = run.player.pos
	run.player.facing = {1, 0}
	run.player.hp = 500
	run.player.max_hp = 500
	clear(&run.enemies)
	clear(&run.projectiles)
	clear(&run.familiars)
	clear(&run.bells)
	clear(&run.numbers)
	clear(&run.sfx)
}

@(private = "file")
mx2_make_tyrant :: proc(pos: ar.Vec2) -> ar.Enemy {
	return ar.Enemy{
		role = .Boss, big = true, boss_id = .Gate_Tyrant,
		name = "Dread Gate Tyrant", final_boss = true,
		pos = pos, prev_pos = pos, facing = {1, 0},
		hp = 242, max_hp = 242, damage = 21, speed = 1.15,
		aggro_range = 16, attack_range = 1.9, attack_cd_s = 0.6,
		damage_type = .Shadow,
		abilities = {.Gate_Strike, .Shadow_Volley}, ability_count = 2,
		pending_ability = ar.PENDING_BASE_ATTACK, last_ability = -1,
		ai = .Chase,
	}
}

@(private = "file")
mx2_distance :: proc(a, b: ar.Vec2) -> f32 {
	d := a - b
	return math.hypot(d.x, d.y)
}

@(private = "file")
mx2_near :: proc(a, b: f32, epsilon: f32 = 1e-4) -> bool {
	return abs(a - b) < epsilon
}

@(test)
mx2_boss_selector_covers_every_band_and_rotates :: proc(t: ^testing.T) {
	tyrant := mx2_make_tyrant({0, 0})

	choice, slot := ar.select_boss_attack(&tyrant, 1.0)
	testing.expect(t, choice == .Ability && slot == 0, "close range must pick Gate Strike")
	choice, slot = ar.select_boss_attack(&tyrant, 4.0)
	testing.expect(t, choice == .Ability && slot == 1, "cast band must pick Shadow Volley")
	choice, slot = ar.select_boss_attack(&tyrant, 6.0)
	testing.expect(t, choice == .Ability && slot == 1, "the six-tile inherited reach is inclusive")
	choice, _ = ar.select_boss_attack(&tyrant, 1.95)
	testing.expect(t, choice == .None, "the authored 1.9..2.0 dead band closes distance instead")
	choice, _ = ar.select_boss_attack(&tyrant, 6.5)
	testing.expect(t, choice == .None, "beyond six tiles the Tyrant advances")

	tyrant.ability_cds = {5, 5}
	choice, _ = ar.select_boss_attack(&tyrant, 4.0)
	testing.expect(t, choice == .Legacy_Cast, "all-on-cooldown in the cast band falls back to the legacy fan")
	choice, _ = ar.select_boss_attack(&tyrant, 1.0)
	testing.expect(t, choice == .Legacy_Melee, "all-on-cooldown in reach falls back to legacy melee")

	// Overlapping bands rotate away from the last authored ability (soft rule).
	gallows := mx2_make_tyrant({0, 0})
	gallows.abilities = {.Ember_Cleave, .Ember_Nova}
	gallows.attack_range = 1.85
	choice, slot = ar.select_boss_attack(&gallows, 1.5)
	testing.expect(t, choice == .Ability && slot == 0, "fresh rotation starts in authored order")
	gallows.last_ability = 0
	choice, slot = ar.select_boss_attack(&gallows, 1.5)
	testing.expect(t, choice == .Ability && slot == 1, "rotation must prefer the slot not fired last")
	gallows.ability_cds[1] = 3
	choice, slot = ar.select_boss_attack(&gallows, 1.5)
	testing.expect(t, choice == .Ability && slot == 0, "a lone eligible slot repeats rather than idling")
}

@(test)
mx2_tyrant_alternates_volley_and_strike_pressure :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(4242, 0), .Warden)
	defer ar.run_destroy(&run)
	mx2_arena(&run)
	tyrant := mx2_make_tyrant({14.5, 10.5}) // 4.0 tiles: inside the volley band
	append(&run.enemies, tyrant)

	boss := &run.enemies[0]
	for _ in 0 ..< 120 {
		if boss.ai == .Windup do break
		ar.sim_tick(&run, {})
	}
	testing.expect(t, boss.ai == .Windup, "the Tyrant must commit an attack from the cast band")
	testing.expectf(t, boss.pending_ability == 1, "cast-band commit is Shadow Volley, got slot %v", boss.pending_ability)
	for _ in 0 ..< 60 {
		if len(run.projectiles) > 0 do break
		ar.sim_tick(&run, {})
	}
	testing.expectf(t, len(run.projectiles) == 3, "Shadow Volley fires a 3-bolt fan, got %v", len(run.projectiles))
	testing.expect(t, boss.last_ability == 1, "firing must record the rotation memory")

	// Point-blank phase: the strike band takes over.
	clear(&run.projectiles)
	run.player.pos = boss.pos + {1.2, 0}
	run.player.prev_pos = run.player.pos
	for _ in 0 ..< 180 {
		if boss.ai == .Windup do break
		ar.sim_tick(&run, {})
	}
	testing.expect(t, boss.ai == .Windup, "the Tyrant must strike once the player closes in")
	testing.expectf(t, boss.pending_ability == 0, "close commit is Gate Strike, got slot %v", boss.pending_ability)

	// Below half health the rotation recycles at 0.8x cooldown, at fire time.
	boss.hp = boss.max_hp / 2 - 1
	boss.windup = 0
	ar.sim_tick(&run, {})
	strike := ar.ABILITY_DEFS[ar.Ability_Id.Gate_Strike]
	testing.expectf(
		t, mx2_near(boss.ability_cds[0], strike.cooldown * 0.8, 1e-3),
		"low-health cooldown %.3f, want %.3f", boss.ability_cds[0], strike.cooldown * 0.8,
	)
}

@(test)
mx2_ranged_doctrines_hold_their_bands :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(515, 0), .Warden)
	defer ar.run_destroy(&run)

	// Caster backpedals out of its 2.2 minimum band between shots.
	mx2_arena(&run)
	cultist := ar.enemy_make(.Cultist, {12.0, 10.5}, 1)
	cultist.ai = .Chase
	append(&run.enemies, cultist)
	for _ in 0 ..< 240 do ar.sim_tick(&run, {})
	d := mx2_distance(run.enemies[0].pos, run.player.pos)
	testing.expectf(t, d > 2.0, "caster must retreat toward its band, still at %.2f", d)

	// Sentinel holds its anchor: in range means no advance at all.
	mx2_arena(&run)
	sentinel := ar.enemy_make(.Rune_Sentinel, {15.6, 10.5}, 1)
	sentinel.ai = .Chase
	append(&run.enemies, sentinel)
	anchor := run.enemies[0].pos
	for _ in 0 ..< 45 do ar.sim_tick(&run, {})
	testing.expect(t, run.enemies[0].pos == anchor, "an in-range sentinel must not leave its anchor")
	testing.expect(t, len(run.projectiles) > 0 || run.player.hp < run.player.max_hp, "holding must not stop it firing")

	// Skirmisher strafes sideways while its cooldown recovers.
	mx2_arena(&run)
	imp := ar.enemy_make(.Bone_Imp, {13.0, 10.5}, 1)
	imp.ai = .Chase
	imp.cooldown = 5
	append(&run.enemies, imp)
	for _ in 0 ..< 40 do ar.sim_tick(&run, {})
	moved := run.enemies[0].pos
	testing.expectf(t, abs(moved.y - 10.5) > 0.15, "skirmisher must strafe laterally, y drift %.3f", abs(moved.y - 10.5))
	band := mx2_distance(moved, run.player.pos)
	testing.expectf(t, band > 1.9 && band < 3.4, "strafe must stay near the band, at %.2f", band)
}

@(test)
mx2_pack_alert_and_memory_drift :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(616, 0), .Warden)
	defer ar.run_destroy(&run)
	mx2_arena(&run)
	spotter := ar.enemy_make(.Ghoul, {12.5, 10.5}, 1)
	sleeper := ar.enemy_make(.Ghoul, {15.5, 10.5}, 1)
	sleeper.aggro_range = 2 // never notices the player on its own
	append(&run.enemies, spotter)
	append(&run.enemies, sleeper)

	ar.sim_tick(&run, {})
	testing.expect(t, run.enemies[0].ai == .Chase, "the spotter engages on aggro")
	testing.expect(t, run.enemies[1].ai == .Chase, "one-hop pack alert must wake the packmate")
	testing.expect(t, run.enemies[1].memory == run.player.pos || mx2_distance(run.enemies[1].memory, run.player.pos) < 0.2,
		"the alerted packmate inherits the alerter's target position")

	// The player vanishes: the sleeper walks its memory, then stands down.
	run.player.pos = {6.5, 16.4}
	run.player.prev_pos = run.player.pos
	start := mx2_distance(run.enemies[1].pos, run.enemies[1].memory)
	for _ in 0 ..< 60 do ar.sim_tick(&run, {})
	mid := mx2_distance(run.enemies[1].pos, run.enemies[1].memory)
	testing.expectf(t, mid < start, "memory drift must close on the last noticed spot (%.2f -> %.2f)", start, mid)
	for _ in 0 ..< 300 do ar.sim_tick(&run, {})
	testing.expect(t, run.enemies[1].ai == .Idle, "an exhausted memory must stand the enemy down")
}

@(test)
mx2_nav_routes_walls_and_detours_furnishings :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(717, 0), .Warden)
	defer ar.run_destroy(&run)
	mx2_arena(&run)
	// Wall rib: direct west route blocked, open gap along the south edge.
	for y in 6 ..= 13 do run.dungeon.tiles[12][y] = .Wall
	run.player.pos = {10.5, 8.5}
	run.player.prev_pos = run.player.pos
	ghoul := ar.enemy_make(.Ghoul, {14.5, 8.5}, 1)
	ghoul.ai = .Chase
	append(&run.enemies, ghoul)

	ar.sim_tick(&run, {})
	_, routed := ar.enemy_nav_direction(&run, &run.enemies[0])
	testing.expect(t, routed, "a blocked pursuer must route on the nav field")
	closest := f32(99)
	for _ in 0 ..< 900 {
		ar.sim_tick(&run, {})
		closest = min(closest, mx2_distance(run.enemies[0].pos, run.player.pos))
	}
	testing.expectf(t, closest < 1.5, "the routed enemy must round the rib without stalling, closest %.2f", closest)

	// A solid furnishing on a clear straight line vetoes greedy motion.
	mx2_arena(&run)
	run.dungeon.bar_furnishings.tiles[0] = {12, 10}
	run.dungeon.bar_furnishings.kinds[0] = .Table
	run.dungeon.bar_furnishings.count = 1
	run.player.pos = {10.5, 10.5}
	run.player.prev_pos = run.player.pos
	blocked := ar.enemy_make(.Ghoul, {15.5, 10.5}, 1)
	blocked.ai = .Chase
	append(&run.enemies, blocked)
	// The furnishing probes look only 0.34/0.68 tiles ahead, so routing kicks
	// in as the enemy nears the table rather than from across the room.
	saw_routed := false
	closest = 99
	for _ in 0 ..< 900 {
		ar.sim_tick(&run, {})
		if _, near_route := ar.enemy_nav_direction(&run, &run.enemies[0]); near_route do saw_routed = true
		closest = min(closest, mx2_distance(run.enemies[0].pos, run.player.pos))
	}
	testing.expect(t, saw_routed, "approaching the furnishing must force field descent")
	testing.expectf(t, closest < 1.5, "the enemy must detour the table, closest %.2f", closest)
}

@(test)
mx2_knockback_velocity_chain_and_radii_separation :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(818, 0), .Warden)
	defer ar.run_destroy(&run)
	mx2_arena(&run)

	// Ordinary melee rides the decaying velocity path at v0 = 1.6.
	victim := ar.enemy_make(.Ghoul, {11.6, 10.5}, 1)
	append(&run.enemies, victim)
	ar.player_melee(&run, {1, 0})
	speed := math.hypot(run.enemies[0].knockback_vel.x, run.enemies[0].knockback_vel.y)
	testing.expectf(t, mx2_near(speed, ar.KNOCKBACK_SPEED, 1e-4), "melee knockback v0 %.3f, want 1.6", speed)

	// A heavy throw chains through the pack cone at 0.85 but never moves a 2x2 boss.
	mx2_arena(&run)
	thrown := ar.enemy_make(.Ghoul, {8.5, 14.5}, 1)
	thrown.knockback_vel = {20, 0}
	receiver := ar.enemy_make(.Ghoul, {9.5, 14.5}, 1)
	wall := mx2_make_tyrant({11.0, 14.5})
	wall.ai = .Idle
	append(&run.enemies, thrown)
	append(&run.enemies, receiver)
	append(&run.enemies, wall)
	ar.sim_tick(&run, {})
	chained := math.hypot(run.enemies[1].knockback_vel.x, run.enemies[1].knockback_vel.y)
	testing.expectf(t, chained > 10, "the packmate behind must inherit chained momentum, got %.2f", chained)
	testing.expect(t, run.enemies[2].knockback_vel == {}, "a 2x2 boss never budges from chained momentum")

	// Separation resolves with real radii: boss vs ghoul settles at ~1.34.
	mx2_arena(&run)
	crowd := ar.enemy_make(.Ghoul, {14.5, 14.5}, 1)
	crowd.aggro_range = 1
	boss := mx2_make_tyrant({15.0, 14.5})
	boss.ai = .Idle
	boss.aggro_range = 1
	append(&run.enemies, crowd)
	append(&run.enemies, boss)
	for _ in 0 ..< 3 do ar.sim_tick(&run, {})
	gap := mx2_distance(run.enemies[0].pos, run.enemies[1].pos)
	testing.expectf(t, gap > 1.2, "boss/ghoul separation must respect summed radii, gap %.2f", gap)
}

@(test)
mx2_elite_identity_names_palettes_and_doctrines :: proc(t: ^testing.T) {
	frenzied := ar.enemy_make(.Ghoul, {10, 10}, 1)
	ar.apply_elite(&frenzied, 0)
	testing.expectf(t, ar.enemy_display_name(&frenzied) == "Frenzied Ghoul", "elite prefix missing: %s", ar.enemy_display_name(&frenzied))
	testing.expect(t, frenzied.tactic == .Flanker, "a Frenzied elite fights as a flanker")
	testing.expect(t, frenzied.color == [4]u8{205, 58, 58, 255}, "Frenzied palette shift must apply")

	runed := ar.enemy_make(.Grave_Archer, {10, 10}, 1)
	ar.apply_elite(&runed, 3)
	testing.expect(t, runed.tactic == .Marksman, "Runed keeps the authored doctrine")

	ironbound := ar.enemy_make(.Grave_Archer, {10, 10}, 1)
	ar.apply_elite(&ironbound, 1)
	testing.expect(t, ironbound.tactic == .Guard, "Ironbound holds as a guard")

	mini := ar.enemy_make(.Ghoul, {10, 10}, 1)
	ar.promote_miniboss(&mini, {214, 176, 120, 255})
	testing.expectf(t, ar.enemy_display_name(&mini) == "Oathbound Ghoul", "miniboss title missing: %s", ar.enemy_display_name(&mini))
	testing.expect(t, mini.color == [4]u8{214, 176, 120, 255}, "the Oathbound accent must land")
}
