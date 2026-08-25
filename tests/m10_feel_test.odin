package archrogue_tests

// Headless M10 movement/action cadence coverage. These tests exercise only
// deterministic simulation state; no raylib window, textures, or audio.

import "core:math"
import "core:testing"
import ar "../src"

@(private = "file")
m10_near :: proc(a, b: f32, epsilon: f32 = 1e-5) -> bool {
	return abs(a - b) < epsilon
}

@(private = "file")
m10_prepare_arena :: proc(run: ^ar.Run, archetype := ar.Archetype_Id.Warden) {
	ar.run_start(run, ar.derive_seed(10100, 0), archetype)
	for x in 0 ..< ar.MAP_W {
		for y in 0 ..< ar.MAP_H do run.dungeon.tiles[x][y] = .Wall
	}
	for x in 10 ..= 22 {
		for y in 8 ..= 18 do run.dungeon.tiles[x][y] = .Floor
	}
	run.dungeon.special_room_count = 0
	run.dungeon.bar_furnishings = {}
	run.dungeon.stairs = {21, 17}
	run.player.pos = {14.5, 12.5}
	run.player.prev_pos = run.player.pos
	run.player.facing = {1, 0}
	clear(&run.enemies)
	clear(&run.projectiles)
	clear(&run.familiars)
	clear(&run.bells)
	clear(&run.numbers)
	clear(&run.ground_items)
	clear(&run.sfx)
	clear(&run.feel)
}

@(test)
m10_walk_phase_helper_matches_pygame_cadence_and_floor :: proc(t: ^testing.T) {
	full := ar.walk_animation_advance(.1, 2.8, .28, .28)
	testing.expectf(t, m10_near(full, .224), "full player cadence %.6f, want .224", full)

	partial := ar.walk_animation_advance(.1, 2.8, .028, .28)
	testing.expectf(t, m10_near(partial, .056), "10%% motion must retain the 25%% cadence floor, got %.6f", partial)
	testing.expect(t, ar.walk_animation_advance(.1, 2.8, 0, .28) == 0, "blocked motion must not advance walk phase")

	slow_enemy := ar.walk_animation_advance(.1, .88, .088, .088)
	testing.expectf(t, m10_near(slow_enemy, .176), "slow enemy cadence must clamp to 2.2, got %.6f", slow_enemy)
}

@(test)
m10_camera_constants_and_exponential_follow_match_pygame :: proc(t:^testing.T) {
	testing.expect(t,m10_near(ar.CAMERA_FOLLOW_RATE,14))
	testing.expect(t,m10_near(ar.CAMERA_FOCUS_Y,.48))
	testing.expect(t,m10_near(ar.OPTIONS_VIEW_ZOOM_DEFAULT,1.3))
	testing.expect(t,m10_near(ar.OPTIONS_VIEW_ZOOM_MIN,.8125))
	testing.expect(t,m10_near(ar.OPTIONS_VIEW_ZOOM_MAX,4.0))
	expected:=f32(1-math.exp(f32(-14.0/60.0)))
	testing.expect(t,m10_near(ar.camera_follow_fraction(ar.SIM_DT),expected))
	testing.expect(t,ar.camera_follow_fraction(0)==0)
	clip_time:=ar.normalized_action_clip_time(.99,8,12)
	testing.expect(t,int(clip_time*12)==7,"normalized action playback must reach the authored final frame")
	testing.expect(t,ar.normalized_action_clip_time(.5,0,12)==0)
}

@(test)
m10_player_phase_uses_actual_displacement_and_blocked_input_stops :: proc(t: ^testing.T) {
	run: ar.Run
	m10_prepare_arena(&run)
	defer ar.run_destroy(&run)

	// A free full input follows the live player speed through actual/planned
	// displacement while retaining the fixed 2.8 authored cadence base.
	before := run.player.pos
	ar.sim_tick(&run, {1, 0})
	delta := run.player.pos - before
	distance := math.hypot(delta.x, delta.y)
	expected := ar.walk_animation_advance(
		ar.SIM_DT,
		ar.PLAYER_MOVE_SPEED,
		distance,
		ar.PLAYER_MOVE_SPEED * ar.SIM_DT,
	)
	testing.expect(t, run.player.moving, "free player input must report real movement")
	testing.expectf(t, m10_near(run.player.anim_time, expected), "player phase %.6f, want %.6f from actual displacement", run.player.anim_time, expected)

	// Park exactly at the west-wall collision radius. Held input remains useful
	// for facing, but cannot fake a walk pose or consume a walk frame.
	run.player.pos = {10 + ar.ACTOR_MOVE_COLLISION_RADIUS, 12.5}
	run.player.prev_pos = run.player.pos
	run.player.anim_time = 7.25
	blocked_pos := run.player.pos
	ar.sim_tick(&run, {-1, 0})
	testing.expect(t, run.player.pos == blocked_pos, "wall probe unexpectedly allowed blocked input")
	testing.expect(t, !run.player.moving, "blocked input must not select the walk pose")
	testing.expect(t, run.player.anim_time == 7.25, "blocked input must preserve walk phase")
}

@(test)
m10_player_wall_slide_and_analog_input_scale_phase :: proc(t: ^testing.T) {
	run: ar.Run
	m10_prepare_arena(&run)
	defer ar.run_destroy(&run)
	run.player.pos = {10 + ar.ACTOR_MOVE_COLLISION_RADIUS, 12.5}
	run.player.prev_pos = run.player.pos

	before := run.player.pos
	ar.sim_tick(&run, {-1, 1})
	delta := run.player.pos - before
	distance := math.hypot(delta.x, delta.y)
	expected := ar.walk_animation_advance(ar.SIM_DT, ar.PLAYER_MOVE_SPEED, distance, ar.PLAYER_MOVE_SPEED * ar.SIM_DT)
	testing.expect(t, delta.x == 0 && delta.y > 0, "diagonal input must slide along the west wall")
	testing.expectf(t, m10_near(run.player.anim_time, expected), "wall-slide cadence ignored actual displacement")

	// Half stick deflection halves ground speed and therefore walk phase.
	run.player.pos = {14.5, 12.5}
	run.player.prev_pos = run.player.pos
	run.player.anim_time = 0
	before = run.player.pos
	ar.sim_tick_limited(&run, {.5, 0}, -1)
	delta = run.player.pos - before
	distance = math.hypot(delta.x, delta.y)
	expected = ar.walk_animation_advance(ar.SIM_DT, ar.PLAYER_MOVE_SPEED, distance, ar.PLAYER_MOVE_SPEED * ar.SIM_DT)
	testing.expectf(t, m10_near(run.player.anim_time, expected), "analog cadence ignored actual/planned ratio")
}

@(test)
m10_enemy_phase_includes_status_and_time_skip_scale :: proc(t: ^testing.T) {
	run: ar.Run
	m10_prepare_arena(&run)
	defer ar.run_destroy(&run)
	run.player.pos = {11.5, 12.5}
	run.player.time_skip_timer = ar.TIME_SKIP_DURATION
	enemy := ar.enemy_make(.Ghoul, {17.5, 12.5}, 1)
	enemy.ai = .Chase
	enemy.cooldown = 2
	enemy.statuses[.Chilled] = 1
	append(&run.enemies, enemy)

	before := run.enemies[0].pos
	ar.sim_tick(&run, {})
	delta := run.enemies[0].pos - before
	distance := math.hypot(delta.x, delta.y)
	expected := ar.walk_animation_advance(
		ar.SIM_DT,
		run.enemies[0].speed,
		distance,
		run.enemies[0].speed * ar.SIM_DT,
	)
	testing.expect(t, run.enemies[0].moving && distance > 0, "slowed enemy did not chase")
	testing.expectf(t, m10_near(run.enemies[0].anim_time, expected), "enemy phase %.6f, want %.6f from status/Time Skip displacement", run.enemies[0].anim_time, expected)
	// .58 Chill * .40 Time Skip is below .25; cadence must remain legible.
	floor_advance := ar.SIM_DT * ar.WALK_ANIMATION_RATE * max(ar.WALK_ANIM_SPEED_FLOOR, run.enemies[0].speed) * ar.WALK_ANIM_RUNTIME_SCALE_FLOOR
	testing.expectf(t, m10_near(run.enemies[0].anim_time, floor_advance), "overlapping slows must retain the 25%% cadence floor")
}

@(test)
m10_enemy_windup_owns_duration_and_elapsed_clock :: proc(t: ^testing.T) {
	run: ar.Run
	m10_prepare_arena(&run)
	defer ar.run_destroy(&run)
	run.player.pos = {12.5, 12.5}
	enemy := ar.enemy_make(.Ghoul, {13.5, 12.5}, 1)
	enemy.ai = .Chase
	append(&run.enemies, enemy)

	// The eligible frame enters Windup at time zero; subsequent enemy-scaled
	// ticks advance the explicit elapsed clock used by authored clips.
	ar.sim_tick(&run, {})
	testing.expect(t, run.enemies[0].ai == .Windup, "melee enemy did not enter its attack windup")
	testing.expectf(t, m10_near(run.enemies[0].windup_duration, ar.ENEMY_MELEE_WINDUP), "windup duration was not captured")
	testing.expect(t, run.enemies[0].action_time == 0, "new windup must begin at action frame zero")
	ar.sim_tick(&run, {})
	testing.expectf(t, m10_near(run.enemies[0].action_time, ar.SIM_DT), "windup action clock did not advance")
	testing.expectf(t, m10_near(run.enemies[0].windup, ar.ENEMY_MELEE_WINDUP-ar.SIM_DT), "remaining windup clock diverged from elapsed time")

	ar.enemy_begin_windup(&run.enemies[0], .41, -1, {-1, 0})
	testing.expect(t, run.enemies[0].action_time == 0 && m10_near(run.enemies[0].windup_duration, .41), "re-entering Windup must reset elapsed time and duration")
}

@(test)
m10_player_visual_actions_have_local_elapsed_clocks :: proc(t: ^testing.T) {
	player := ar.Player{}
	ar.player_start_visual_action(&player, .Attack, ar.PLAYER_ATTACK_ACTION_SECONDS)
	ar.player_tick_visual_action(&player, .05)
	testing.expect(t, player.visual_action == .Attack && m10_near(player.action_time, .05), "attack action clock did not advance")

	// Same-state retrigger extends the remaining window without restarting it.
	ar.player_start_visual_action(&player, .Attack, ar.PLAYER_ATTACK_ACTION_SECONDS)
	testing.expect(t, m10_near(player.action_time, .05) && m10_near(player.action_duration, .25), "same action must extend without snapping to frame zero")
	ar.player_start_visual_action(&player, .Cast, ar.PLAYER_CLASS_ACTION_SECONDS)
	testing.expect(t, player.visual_action == .Cast && player.action_time == 0, "new action kind must restart its local clip")
	ar.player_tick_visual_action(&player, ar.PLAYER_CLASS_ACTION_SECONDS)
	testing.expect(t, player.visual_action == .None && player.action_time == 0 && player.action_duration == 0, "completed live action must clear")

	ar.player_start_visual_action(&player, .Die, .4)
	ar.player_tick_visual_action(&player, .4)
	testing.expect(t, player.visual_action == .Dead, "completed one-shot death must settle on the dead pose")
}

@(test)
m10_base_melee_starts_attack_clip_without_resetting_walk_phase :: proc(t: ^testing.T) {
	run: ar.Run
	m10_prepare_arena(&run)
	defer ar.run_destroy(&run)
	run.player.anim_time = 3.75
	run.player.stamina = 100
	run.player.melee_timer = 0

	ar.player_melee(&run, {1, 0})
	testing.expect(t, run.player.visual_action == .Attack && run.player.action_time == 0, "base melee did not start its explicit attack pose")
	testing.expectf(t, m10_near(run.player.action_duration, ar.PLAYER_ATTACK_ACTION_SECONDS), "base attack duration changed")
	testing.expect(t, run.player.anim_time == 3.75, "starting an action must not snap the locomotion phase")
	testing.expect(t, len(run.feel) == 1 && run.feel[0].kind == .Slash, "base melee must emit one slash presentation event")

	ar.sim_tick(&run, {})
	testing.expectf(t, m10_near(run.player.action_time, ar.SIM_DT), "live player action did not tick with simulation time")
}

@(test)
m10_big_ranged_fallback_retains_three_bolt_fan :: proc(t: ^testing.T) {
	run: ar.Run
	m10_prepare_arena(&run)
	defer ar.run_destroy(&run)
	run.player.pos = {18.5, 12.5}
	enemy := ar.enemy_make(.Bone_Imp, {12.5, 12.5}, 1)
	enemy.big = true
	enemy.role = .Boss
	enemy.ai = .Windup
	enemy.windup = 0
	enemy.windup_duration = ar.ENEMY_CAST_WINDUP
	enemy.pending_ability = -1
	enemy.windup_aim = {1, 0}
	append(&run.enemies, enemy)

	ar.sim_tick(&run, {})
	testing.expectf(t, len(run.projectiles) == 3, "big ranged fallback fired %v bolts, want 3", len(run.projectiles))
	if len(run.projectiles) == 3 {
		testing.expect(t, run.projectiles[0].vel.y < 0 && abs(run.projectiles[1].vel.y) < 1e-5 && run.projectiles[2].vel.y > 0, "boss fallback fan lost its -0.28/0/+0.28 spread")
	}
}

@(test)
m10_damage_feel_profiles_and_hit_flash_boundaries :: proc(t:^testing.T) {
	run:ar.Run
	m10_prepare_arena(&run)
	defer ar.run_destroy(&run)
	run.player.max_hp=100

	ar.feel_emit_player_hurt(&run,17)
	testing.expect(t,len(run.feel)==2)
	testing.expect(t,run.feel[0].kind==.Blood&&m10_near(run.feel[0].duration,.34)&&m10_near(run.feel[0].radius,.42))
	testing.expect(t,run.feel[1].kind==.Screen_Flash&&m10_near(run.feel[1].duration,.18))
	testing.expect(t,run.feel[1].color==[4]u8{105,24,28,255})
	clear(&run.feel)
	ar.feel_emit_player_hurt(&run,18)
	testing.expect(t,len(run.feel)==2&&m10_near(run.feel[1].duration,.30))
	testing.expect(t,run.feel[1].color==[4]u8{160,35,32,255})

	ar.mark_player_hit_flash(&run.player,17)
	testing.expect(t,m10_near(run.player.hit_flash_duration,.22))
	ar.mark_player_hit_flash(&run.player,18)
	testing.expect(t,m10_near(run.player.hit_flash_duration,.32))
	enemy:=ar.Enemy{role=.Normal}
	ar.mark_enemy_hit_flash(&enemy)
	testing.expect(t,m10_near(enemy.hit_flash_duration,.22))
	enemy.role=.Boss
	ar.mark_enemy_hit_flash(&enemy)
	testing.expect(t,m10_near(enemy.hit_flash_duration,.32))
}

@(test)
m10_death_feel_profiles_and_queue_do_not_touch_rng :: proc(t:^testing.T) {
	run:ar.Run
	m10_prepare_arena(&run)
	defer ar.run_destroy(&run)
	combat_before:=run.combat_rng
	loot_before:=run.loot_rng
	normal:=ar.Enemy{pos={12,12},color={90,80,70,255}}
	ar.feel_emit_enemy_death(&run,&normal,{200,100,50,255})
	testing.expect(t,len(run.feel)==1&&m10_near(run.feel[0].duration,.58)&&m10_near(run.feel[0].radius,.56))
	big:=normal
	big.big=true
	ar.feel_emit_enemy_death(&run,&big,{200,100,50,255})
	testing.expect(t,len(run.feel)==2&&m10_near(run.feel[1].radius,.86))
	boss:=big
	boss.role=.Boss
	ar.feel_emit_enemy_death(&run,&boss,{200,100,50,255})
	testing.expect(t,len(run.feel)==5)
	testing.expect(t,m10_near(run.feel[2].duration,.82)&&m10_near(run.feel[2].radius,1.05))
	testing.expect(t,run.feel[3].kind==.Boss_Payoff&&run.feel[4].kind==.Screen_Flash)
	testing.expect(t,run.feel[4].visibility==.World&&run.feel[4].priority==.Critical)
	testing.expect(t,run.combat_rng==combat_before&&run.loot_rng==loot_before)

	for _ in len(run.feel)..<ar.MAX_FEEL_EVENTS+20 do ar.feel_emit(&run,.Hit,{},{255,255,255,255},.1,.1)
	testing.expect(t,len(run.feel)==ar.MAX_FEEL_EVENTS,"feel queue must stay bounded")
	ar.clear_feel_events(&run)
	testing.expect(t,len(run.feel)==0)
}
