package archrogue_tests

// Headless two-seat simulation (MULTIPLAYER.md M3): explicit ownership,
// targeting, credit, fallen-seat rules, and the archived co-op defects.

import "core:math"
import "core:testing"
import ar "../src"

@(private = "file")
coop_arena :: proc(run: ^ar.Run, a: ar.Archetype_Id = .Warden, b: ar.Archetype_Id = .Rogue) {
	ar.run_start_coop(run, 0xC0FFEE, {a, b}, .Medium)
	for x in 0 ..< ar.MAP_W {
		for y in 0 ..< ar.MAP_H do run.dungeon.tiles[x][y] = .Wall
	}
	for x in 4 ..= 30 {
		for y in 4 ..= 20 do run.dungeon.tiles[x][y] = .Floor
	}
	run.dungeon.stairs = {28, 18}
	for slot in 0 ..< ar.MAX_PLAYERS {
		run.players[slot].pos = {8.5 + f32(slot) * 2, 10.5}
		run.players[slot].prev_pos = run.players[slot].pos
		run.players[slot].facing = {1, 0}
	}
	clear(&run.enemies)
	clear(&run.projectiles)
	clear(&run.familiars)
	clear(&run.bells)
	clear(&run.numbers)
	clear(&run.ground_items)
	clear(&run.traps)
	clear(&run.shrines)
	clear(&run.secrets)
	clear(&run.sfx)
	run.has_shopkeeper = false
	run.ambient_residents = {}
	clear(&run.story_runtime.guests)
	run.dungeon.boss_arena = false
}

@(private = "file")
add_enemy :: proc(run: ^ar.Run, pos: ar.Vec2, hp := 30) -> ^ar.Enemy {
	enemy := ar.enemy_make(.Ghoul, pos, 1)
	enemy.hp = hp
	enemy.max_hp = hp
	ar.enemy_ensure_id(run, &enemy)
	append(&run.enemies, enemy)
	return &run.enemies[len(run.enemies) - 1]
}

@(private = "file")
tick_moves :: proc(run: ^ar.Run, a, b: ar.Vec2, ticks := 1) {
	inputs: [ar.MAX_PLAYERS]ar.Player_Tick_Input
	inputs[0] = {move = a, max_move_step = -1}
	inputs[1] = {move = b, max_move_step = -1}
	for _ in 0 ..< ticks do ar.sim_tick_players(run, inputs)
}

@(test)
coop_start_seats_both_players_on_one_world :: proc(t: ^testing.T) {
	solo: ar.Run
	defer ar.run_destroy(&solo)
	ar.run_start(&solo, 0xC0FFEE, .Warden, .Medium)
	coop: ar.Run
	defer ar.run_destroy(&coop)
	ar.run_start_coop(&coop, 0xC0FFEE, {.Warden, .Ranger}, .Medium)
	testing.expect_value(t, coop.player_count, 2)
	testing.expect_value(t, solo.player_count, 1)
	// The host seat and the floor are identical to the solo start.
	testing.expect(t, coop.dungeon.tiles == solo.dungeon.tiles, "co-op floor differs from solo floor")
	testing.expect_value(t, coop.players[0].pos, solo.players[0].pos)
	testing.expect_value(t, coop.players[1].archetype, ar.Archetype_Id.Ranger)
	testing.expect(t, coop.players[1].pos != coop.players[0].pos, "seats stack on one tile")
	testing.expect(t, !ar.blocked_for_radius(&coop.dungeon, coop.players[1].pos.x, coop.players[1].pos.y, block_stairs = true))
	testing.expect_value(t, coop.players[1].raise_charges, 1)
}

@(test)
coop_each_seat_moves_by_its_own_input_and_world_ticks_once :: proc(t: ^testing.T) {
	run: ar.Run
	defer ar.run_destroy(&run)
	coop_arena(&run)
	enemy := add_enemy(&run, {25.5, 18.5})
	enemy.cooldown = 1
	before0, before1 := run.players[0].pos, run.players[1].pos
	tick_moves(&run, {1, 0}, {0, 1}, 10)
	d0 := run.players[0].pos - before0
	d1 := run.players[1].pos - before1
	testing.expect(t, d0.x > 0.3 && abs(d0.y) < 1e-4, "host did not move east")
	testing.expect(t, d1.y > 0.3 && abs(d1.x) < 1e-4, "joiner did not move south")
	// Enemy clocks advance once per tick, not once per seat.
	testing.expect(t, math.abs(run.enemies[0].cooldown - (1 - 10 * f32(ar.SIM_DT))) < 1e-4, "enemy clock double-ticked")
}

@(test)
coop_enemies_target_nearest_living_seat_with_hysteresis :: proc(t: ^testing.T) {
	run: ar.Run
	defer ar.run_destroy(&run)
	coop_arena(&run)
	run.players[0].pos = {6.5, 10.5}
	run.players[1].pos = {20.5, 10.5}
	_ = add_enemy(&run, {18.5, 10.5})
	tick_moves(&run, {}, {}, 1)
	testing.expect_value(t, run.enemies[0].target_slot, u8(1))
	// A marginally closer host does not steal aggro...
	run.enemies[0].pos = {13.0, 10.5}
	tick_moves(&run, {}, {}, 1)
	testing.expect_value(t, run.enemies[0].target_slot, u8(1))
	// ...but a fallen target hands the enemy to the survivor.
	run.players[1].hp = 0
	tick_moves(&run, {}, {}, 1)
	testing.expect_value(t, run.enemies[0].target_slot, u8(0))
}

@(test)
coop_kill_credit_goes_to_the_last_hitter :: proc(t: ^testing.T) {
	run: ar.Run
	defer ar.run_destroy(&run)
	coop_arena(&run)
	enemy := add_enemy(&run, {11.3, 10.5}, hp = 1)
	_ = enemy
	xp0, gold0 := run.players[0].xp, run.players[0].gold
	run.players[1].stamina = 100
	ar.player_melee(&run, 1, {1, 0})
	testing.expect(t, run.enemies[0].hp <= 0, "joiner melee missed")
	tick_moves(&run, {}, {}, 10) // past the impact hitstop
	testing.expect_value(t, len(run.enemies), 0)
	testing.expect(t, run.players[1].xp > 0 && run.players[1].gold > 0, "joiner was not credited")
	testing.expect_value(t, run.players[0].xp, xp0)
	testing.expect_value(t, run.players[0].gold, gold0)
}

@(test)
coop_projectiles_credit_their_shooter :: proc(t: ^testing.T) {
	run: ar.Run
	defer ar.run_destroy(&run)
	coop_arena(&run, .Warden, .Arcanist)
	_ = add_enemy(&run, {16.5, 10.5}, hp = 1)
	run.players[1].mana = 100
	testing.expect(t, ar.player_cast_bolt(&run, 1, {1, 0}))
	testing.expect_value(t, run.projectiles[0].owner_slot, u8(1))
	tick_moves(&run, {}, {}, 60)
	testing.expect_value(t, len(run.enemies), 0)
	testing.expect(t, run.players[1].xp > 0, "shooter was not credited")
	testing.expect_value(t, run.players[0].xp, 0)
}

@(test)
coop_dead_host_does_not_stop_the_partner :: proc(t: ^testing.T) {
	run: ar.Run
	defer ar.run_destroy(&run)
	coop_arena(&run)
	run.players[0].hp = 0
	_ = add_enemy(&run, {14.5, 12.5})
	before := run.players[1].pos
	enemy_before := run.enemies[0].pos
	tick_moves(&run, {1, 0}, {0, 1}, 20)
	testing.expect(t, run.players[1].pos.y > before.y + 0.5, "living joiner frozen")
	testing.expect(t, run.players[0].pos == ar.Vec2{8.5, 10.5}, "fallen host moved")
	testing.expect(t, run.enemies[0].pos != enemy_before, "world stopped with the host")
	testing.expect_value(t, run.enemies[0].target_slot, u8(1))
	// The fallen seat cannot interact.
	testing.expect(t, !ar.player_interact(&run, 0))
}

@(test)
coop_level_up_never_revives_a_fallen_seat :: proc(t: ^testing.T) {
	run: ar.Run
	defer ar.run_destroy(&run)
	coop_arena(&run)
	run.players[1].hp = 0
	level := run.players[1].level
	ar.player_gain_xp(&run, 1, 10_000)
	testing.expect(t, run.players[1].level > level)
	testing.expect_value(t, run.players[1].hp, 0)
}

@(test)
coop_raise_spends_the_raisers_charge :: proc(t: ^testing.T) {
	run: ar.Run
	defer ar.run_destroy(&run)
	coop_arena(&run)
	run.players[1].hp = 0
	run.players[1].pos = run.players[0].pos + {1, 0}
	testing.expect_value(t, ar.nearby_raisable_partner(&run, 0), 1)
	testing.expect(t, ar.interact_prompt(&run, 0) != "")
	_ = ar.player_interact(&run, 0)
	testing.expect_value(t, run.players[1].hp, max(1, run.players[1].max_hp / 2))
	testing.expect_value(t, run.players[0].raise_charges, 0)
	testing.expect_value(t, run.players[1].raise_charges, 1)
	// No charge left: a second fall cannot be raised by the same seat.
	run.players[1].hp = 0
	testing.expect_value(t, ar.nearby_raisable_partner(&run, 0), -1)
	// Out of range never raises.
	run.players[0].raise_charges = 1
	run.players[1].pos = run.players[0].pos + {3, 0}
	testing.expect_value(t, ar.nearby_raisable_partner(&run, 0), -1)
	// Solo has no partner to raise.
	solo: ar.Run
	defer ar.run_destroy(&solo)
	ar.run_start(&solo, 1, .Warden)
	testing.expect_value(t, ar.nearby_raisable_partner(&solo, 0), -1)
}

@(test)
coop_vigil_shrine_grants_the_activator_one_raise :: proc(t: ^testing.T) {
	run: ar.Run
	defer ar.run_destroy(&run)
	coop_arena(&run)
	append(&run.shrines, ar.Shrine{pos = run.players[1].pos + {.5, 0}, kind = .Vigil})
	shrine := ar.nearby_shrine(&run, 1)
	testing.expect(t, shrine != nil)
	ar.activate_shrine(&run, 1, shrine)
	testing.expect_value(t, run.players[1].raise_charges, 2)
	testing.expect_value(t, run.players[0].raise_charges, 1)
}

@(test)
coop_vigil_shrines_never_generate_in_solo :: proc(t: ^testing.T) {
	coop_seen := false
	for seed in u64(1) ..= 60 {
		run: ar.Run
		ar.run_start(&run, seed, .Warden, .Easy)
		for _ in 1 ..< 6 {
			for shrine in run.shrines do testing.expect(t, shrine.kind != .Vigil, "solo rolled a Vigil Shrine")
			ar.run_descend(&run)
		}
		ar.run_destroy(&run)
		coop: ar.Run
		ar.run_start_coop(&coop, seed, {.Warden, .Rogue}, .Easy)
		for _ in 1 ..< 6 {
			for shrine in coop.shrines do if shrine.kind == .Vigil do coop_seen = true
			ar.run_descend(&coop)
		}
		ar.run_destroy(&coop)
	}
	testing.expect(t, coop_seen, "co-op never rolled a Vigil Shrine in 60 seeds")
}

@(test)
coop_descent_rules_and_fallen_respawn :: proc(t: ^testing.T) {
	for difficulty in ([]ar.Difficulty_Id{.Medium, .Hell}) {
		run: ar.Run
		defer ar.run_destroy(&run)
		ar.run_start_coop(&run, 77, {.Warden, .Rogue}, difficulty)
		stairs := ar.Vec2{f32(run.dungeon.stairs.x) + .5, f32(run.dungeon.stairs.y) + .5}
		clear(&run.enemies)
		run.players[0].pos = stairs + {.4, 0}
		depth := run.depth
		changed := ar.player_interact(&run, 0)
		if difficulty == .Hell {
			// The living partner is far away: Hell refuses a solo descent.
			testing.expect(t, !changed && run.depth == depth, "Hell descended without the partner")
			run.players[1].hp = 0 // a fallen partner does not block it
			changed = ar.player_interact(&run, 0)
		}
		testing.expect(t, changed && run.depth == depth + 1, "descent failed")
		// The fallen partner rises at half health on the new floor.
		if difficulty == .Hell do testing.expect_value(t, run.players[1].hp, max(1, run.players[1].max_hp / 2))
		testing.expect(t, run.players[1].pos != run.players[0].pos)
	}
}

@(test)
coop_two_rangers_own_their_own_beasts :: proc(t: ^testing.T) {
	run: ar.Run
	defer ar.run_destroy(&run)
	coop_arena(&run, .Ranger, .Ranger)
	for slot in 0 ..< 2 {
		run.players[slot].mana = 100
		testing.expect(t, ar.player_cast_spirit_beast(&run, slot), "beast summon failed")
	}
	testing.expect_value(t, len(run.familiars), 2)
	beast0 := ar.living_spirit_beast(&run, 0)
	beast1 := ar.living_spirit_beast(&run, 1)
	testing.expect(t, beast0 != nil && beast1 != nil && beast0 != beast1)
	testing.expect_value(t, beast0.owner_slot, u8(0))
	testing.expect_value(t, beast1.owner_slot, u8(1))
	// Commanding (recasting) one beast leaves the other untouched.
	command1 := beast1.command
	run.players[0].mana = 100
	run.players[0].class_skill_timer = 0
	_ = ar.player_cast_spirit_beast(&run, 0)
	testing.expect_value(t, ar.living_spirit_beast(&run, 1).command, command1)
	testing.expect_value(t, len(run.familiars), 2)
}

@(test)
coop_boss_arena_entry_gathers_the_party :: proc(t: ^testing.T) {
	run: ar.Run
	defer ar.run_destroy(&run)
	ar.run_start_coop(&run, 9, {.Warden, .Rogue}, .Easy)
	for run.depth < 3 do ar.run_descend(&run)
	boss_found := false
	for &enemy in run.enemies do if enemy.role == .Boss do boss_found = true
	if !boss_found || !run.dungeon.boss_arena {
		return // seed without a depth-3 guardian arena; covered by other floors
	}
	room := run.dungeon.rooms_buf[run.dungeon.room_count - 1]
	center := ar.room_center(room)
	run.players[0].pos = {f32(center.x) + .5, f32(center.y) + .5}
	run.players[1].hp = 0 // fallen partner far away
	tick_moves(&run, {}, {}, 2)
	testing.expect(t, run.boss_engaged, "arena did not engage")
	p1 := run.players[1].pos
	testing.expect(t, room.x <= int(p1.x) && int(p1.x) < room.x + room.w && room.y <= int(p1.y) && int(p1.y) < room.y + room.h,
		"fallen partner was not gathered into the arena")
}


// ------------------------------------------------------ blocking and shoves --

@(test)
coop_players_block_each_other :: proc(t: ^testing.T) {
	run: ar.Run
	defer ar.run_destroy(&run)
	coop_arena(&run)
	run.players[0].pos = {10.5, 10.5}
	run.players[1].pos = {12.5, 10.5}
	for slot in 0 ..< 2 do run.players[slot].prev_pos = run.players[slot].pos
	// Seat 0 walks east into the stationary partner for two seconds.
	tick_moves(&run, {1, 0}, {}, 120)
	gap := run.players[1].pos.x - run.players[0].pos.x
	testing.expectf(t, gap >= 2 * ar.PLAYER_HIT_RADIUS - 0.01, "mover should stop at contact distance, gap %.3f", gap)
	testing.expectf(t, math.abs(run.players[1].pos.x - 12.5) < 0.01, "stationary partner must not be pushed by walking, x %.3f", run.players[1].pos.x)
	// A fallen partner is passable so Raise can reach the body.
	run.players[1].hp = 0
	tick_moves(&run, {1, 0}, {}, 90)
	testing.expectf(t, run.players[0].pos.x > 12.5, "living seat should walk through a fallen partner, x %.3f", run.players[0].pos.x)
}

@(test)
coop_big_hit_shoves_partner_for_one_nonlethal_damage :: proc(t: ^testing.T) {
	run: ar.Run
	defer ar.run_destroy(&run)
	coop_arena(&run)
	run.players[0].pos = {10.5, 10.5}
	run.players[0].facing = {1, 0}
	run.players[1].pos = {11.5, 10.5}
	run.players[1].hp = 5
	for slot in 0 ..< 2 do run.players[slot].prev_pos = run.players[slot].pos
	start_x := run.players[1].pos.x
	testing.expect(t, ar.player_big_hit_begin(&run, 0, {1, 0}), "big hit should start")
	tick_moves(&run, {}, {}, int(ar.BIGHIT_CHARGE_TIME / ar.SIM_DT) + 2)
	testing.expectf(t, run.players[1].hp == 4, "partner takes exactly 1 damage, hp %d", run.players[1].hp)
	tick_moves(&run, {}, {}, 60)
	moved := run.players[1].pos.x - start_x
	testing.expectf(t, moved > 1.0 && moved < ar.BIGHIT_SHOVE_TILES + 0.2, "partner shoved along the swing, moved %.3f tiles", moved)
	testing.expect(t, run.players[0].hp == run.players[0].max_hp, "shover is unharmed")
	// Never lethal: at 1 HP the shove still displaces but deals nothing.
	run.players[0].pos = {10.5, 10.5}
	run.players[1].pos = {11.5, 10.5}
	run.players[1].hp = 1
	run.players[0].bighit_timer = 0
	run.players[0].stamina = f32(run.players[0].max_stamina)
	testing.expect(t, ar.player_big_hit_begin(&run, 0, {1, 0}))
	tick_moves(&run, {}, {}, int(ar.BIGHIT_CHARGE_TIME / ar.SIM_DT) + 2)
	testing.expectf(t, run.players[1].hp == 1, "shove must not kill a 1 HP partner, hp %d", run.players[1].hp)
}

@(test)
coop_big_hit_swaps_places_with_a_pinned_partner :: proc(t: ^testing.T) {
	run: ar.Run
	defer ar.run_destroy(&run)
	coop_arena(&run)
	// Tile (4,4) is the room's north-west corner: walls at x=3 and y=3.
	pinned := ar.Vec2{4.5, 4.5}
	shover := ar.Vec2{5.3, 5.3}
	run.players[1].pos = pinned
	run.players[0].pos = shover
	aim := ar.Vec2{-1, -1}
	run.players[0].facing = aim
	for slot in 0 ..< 2 do run.players[slot].prev_pos = run.players[slot].pos
	testing.expect(t, ar.player_big_hit_begin(&run, 0, aim))
	tick_moves(&run, {}, {}, int(ar.BIGHIT_CHARGE_TIME / ar.SIM_DT) + 2)
	// The corner cannot absorb a shove on either axis, so the pair traded places.
	d0 := run.players[0].pos - pinned
	d1 := run.players[1].pos - shover
	testing.expectf(t, math.hypot(d0.x, d0.y) < 0.35, "shover should now stand in the corner, pos %v", run.players[0].pos)
	testing.expectf(t, math.hypot(d1.x, d1.y) < 0.35, "pinned partner should now stand where the shover was, pos %v", run.players[1].pos)
	testing.expect(t, run.players[1].shove_vel == {}, "a swap carries no residual shove")
}
