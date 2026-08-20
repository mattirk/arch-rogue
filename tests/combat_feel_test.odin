package archrogue_tests

// 2026-08 combat-feel pass: the basic-swing plant window (commit-stop), the
// connected-swing impact freeze (hitstop), and the restored player-as-mover
// half of combat/movement.py:293-375 contact resolution, whose absence let
// the player ram and walk over wall-pinned enemies.

import "core:testing"
import "core:math"
import ar "../src"

@(private = "file")
feel_arena :: proc(run: ^ar.Run, seed: u64) {
	ar.run_start(run, ar.derive_seed(seed, 0), .Warden)
	for x in 0 ..< ar.MAP_W {
		for y in 0 ..< ar.MAP_H do run.dungeon.tiles[x][y] = .Wall
	}
	for x in 6 ..= 18 {
		for y in 6 ..= 16 do run.dungeon.tiles[x][y] = .Floor
	}
	run.dungeon.bar_furnishings = {}
	run.hitstop_ticks = 0
	run.player.pos = {10.5, 10.5}
	run.player.prev_pos = run.player.pos
	run.player.facing = {1, 0}
	run.player.hp = 500
	run.player.max_hp = 500
	run.player.stamina = 200
	run.player.max_stamina = 200
	clear(&run.enemies)
	clear(&run.projectiles)
	clear(&run.familiars)
	clear(&run.bells)
	clear(&run.numbers)
	clear(&run.sfx)
	clear(&run.traps)
	clear(&run.shrines)
	clear(&run.secrets)
	clear(&run.ground_items)
}

// An inert body: zero aggro keeps it Idle, zero speed keeps it parked even
// after damage alerts it. Contact and separation ignore both stats.
@(private = "file")
feel_grunt :: proc(pos: ar.Vec2) -> ar.Enemy {
	return ar.Enemy{
		name = "Feel Grunt", pos = pos, prev_pos = pos, facing = {-1, 0},
		hp = 200, max_hp = 200, damage = 0, speed = 0,
		aggro_range = 0, attack_range = 1.2, attack_cd_s = 1.0,
		ai = .Idle,
	}
}

@(private = "file")
feel_gap :: proc(a, b: ar.Vec2) -> f32 {
	d := a - b
	return math.hypot(d.x, d.y)
}

@(test)
feel_player_cannot_walk_over_wall_pinned_enemy :: proc(t: ^testing.T) {
	run: ar.Run
	feel_arena(&run, 9401)
	defer ar.run_destroy(&run)
	// The arena's east wall starts at x=19; the grunt gets shoved against it
	// and can absorb no more separation. Before the player-side contact half
	// was restored, four seconds of walking ended standing on top of it.
	append(&run.enemies, feel_grunt({18.5, 11.5}))
	run.player.pos = {16.5, 11.5}
	run.player.prev_pos = run.player.pos
	for _ in 0 ..< 240 do ar.sim_tick(&run, {1, 0})
	contact := f32(ar.PLAYER_HIT_RADIUS) + ar.ENEMY_HIT_RADIUS
	gap := feel_gap(run.player.pos, run.enemies[0].pos)
	testing.expect(t, gap >= contact - 0.03, "the player must stop at body contact instead of walking over the pinned enemy")
	testing.expect(t, run.player.pos.x < run.enemies[0].pos.x, "the player must stay on the near side of the pinned enemy")
}

@(test)
feel_dash_never_lands_inside_an_enemy_body :: proc(t: ^testing.T) {
	run: ar.Run
	feel_arena(&run, 9402)
	defer ar.run_destroy(&run)
	append(&run.enemies, feel_grunt({12.5, 10.5}))
	start := run.player.pos
	testing.expect(t, ar.player_dash(&run, {1, 0}), "the test dash must fire")
	testing.expect(t, run.player.pos != start, "the dash must move the player")
	contact := f32(ar.PLAYER_HIT_RADIUS) + ar.ENEMY_HIT_RADIUS
	gap := feel_gap(run.player.pos, run.enemies[0].pos)
	testing.expect(t, gap >= contact - 0.03, "a dash may pass through a body but never terminate inside it")
}

@(test)
feel_basic_swing_plants_the_player :: proc(t: ^testing.T) {
	run: ar.Run
	feel_arena(&run, 9403)
	defer ar.run_destroy(&run)
	// Guard the tuning invariant: the plant must expire before the fastest
	// melee cooldown (0.20 floor) or held attacks would never walk again.
	testing.expect(t, f32(ar.MELEE_COMMIT_SECONDS) < 0.20, "plant window must stay under the melee cooldown floor")
	ar.player_melee(&run, {1, 0}) // a whiff commits exactly like a hit
	testing.expect(t, run.player.melee_commit_timer > 0, "a swing must open its plant window")
	planted := run.player.pos
	locked_ticks := 0
	for run.player.melee_commit_timer > 0 && locked_ticks <= 60 {
		ar.sim_tick(&run, {0, 1})
		locked_ticks += 1
	}
	testing.expect(t, locked_ticks > 1 && locked_ticks <= 60, "the plant must span several ticks and expire")
	testing.expect(t, run.player.pos == planted, "walk input during the plant window must not move the player")
	testing.expect(t, run.player.facing == ar.Vec2{1, 0}, "the plant window must hold the swing's aim facing")
	ar.sim_tick(&run, {0, 1})
	testing.expect(t, run.player.pos != planted, "movement must resume once the plant expires")
}

@(test)
feel_connected_swing_freezes_the_sim :: proc(t: ^testing.T) {
	run: ar.Run
	feel_arena(&run, 9404)
	defer ar.run_destroy(&run)
	append(&run.enemies, feel_grunt({11.5, 10.5}))
	ar.player_melee(&run, {1, 0})
	testing.expect(t, run.enemies[0].hp < 200, "the swing must connect")
	testing.expect(t, run.hitstop_ticks == ar.HITSTOP_HIT_TICKS, "a connected non-lethal swing queues the standard freeze")
	cooldown := run.player.melee_timer
	enemy_before := run.enemies[0].pos
	for _ in 0 ..< ar.HITSTOP_HIT_TICKS do ar.sim_tick(&run, {0, 1})
	testing.expect(t, run.player.pos == ar.Vec2{10.5, 10.5}, "frozen ticks must not move the player")
	testing.expect(t, run.enemies[0].pos == enemy_before, "frozen ticks must not integrate enemy knockback")
	testing.expect(t, run.player.melee_timer == cooldown, "frozen ticks must not advance combat clocks")
	testing.expect(t, run.hitstop_ticks == 0, "the freeze must last exactly its queued ticks")
	ar.sim_tick(&run, {0, 1})
	testing.expect(t, run.player.melee_timer < cooldown, "combat clocks must resume the tick after the freeze")
}

@(test)
feel_lethal_swing_freezes_longer :: proc(t: ^testing.T) {
	run: ar.Run
	feel_arena(&run, 9405)
	defer ar.run_destroy(&run)
	dying := feel_grunt({11.5, 10.5})
	dying.hp = 1
	append(&run.enemies, dying)
	ar.player_melee(&run, {1, 0})
	testing.expect(t, run.enemies[0].hp <= 0, "the 1 hp grunt must die to the swing")
	testing.expect(t, run.hitstop_ticks == ar.HITSTOP_HEAVY_TICKS, "a killing swing holds the freeze a beat longer")
}
