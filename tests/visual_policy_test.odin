package archrogue_tests

// Headless contracts for presentation math. The renderer consumes these pure
// helpers, while authoritative LOS and deterministic simulation remain in Run.

import "core:testing"
import ar "../src"

@(private = "file")
visual_near :: proc(a, b: f32, epsilon: f32 = 1e-4) -> bool {
	return abs(a - b) <= epsilon
}

@(test)
visual_ambient_darkens_with_depth_without_changing_dark_floor_level :: proc(t: ^testing.T) {
	depth_1 := ar.visual_ambient_level(1, false)
	depth_5 := ar.visual_ambient_level(5, false)
	depth_10 := ar.visual_ambient_level(ar.DUNGEON_DEPTH, false)
	testing.expectf(t, visual_near(depth_1, .576), "depth-1 ambient %.4f, want .576", depth_1)
	testing.expectf(t, visual_near(depth_10, .18), "depth-10 ambient %.4f, want .18", depth_10)
	testing.expect(t, depth_1 > depth_5 && depth_5 > depth_10, "normal floors must darken monotonically")
	for depth in 1 ..= ar.DUNGEON_DEPTH {
		testing.expect(t, visual_near(ar.visual_ambient_level(depth, true), .10), "dark-floor ambient must remain lantern-driven")
	}
	ambient := ar.visual_theme_ambient(&ar.THEMES[2], ar.DUNGEON_DEPTH, false)
	testing.expect(t, ambient[0] < ambient[2], "violet theme ambient must retain its authored color cast")
}

@(test)
visual_revelation_field_matches_pygame_falloff_and_los_holes :: proc(t: ^testing.T) {
	mask: [ar.MAP_W][ar.MAP_H]bool
	for x in 10 ..= 20 {
		for y in 10 ..= 20 do mask[x][y] = true
	}
	edge := ar.visual_fog_target(&mask, 10, 15)
	one_in := ar.visual_fog_target(&mask, 11, 15)
	deep := ar.visual_fog_target(&mask, 15, 15)
	testing.expectf(t, visual_near(edge, (1-.55)/1.7), "frontier value %.4f differs from authored falloff", edge)
	testing.expect(t, edge < one_in && one_in < deep && visual_near(deep, 1), "field must rise continuously into explored space")
	mask[15][15] = false
	testing.expect(t, ar.visual_fog_target(&mask, 15, 15) == 0, "unexplored/LOS-blocked tile must remain black")
	testing.expect(t, ar.visual_fog_target(nil, 15, 15) == 0, "nil mask must be safe")
}

@(test)
visual_fog_easing_is_frame_rate_independent :: proc(t: ^testing.T) {
	one_step := ar.visual_fog_ease(0, 1, .25)
	many_steps: f32
	for _ in 0 ..< 15 do many_steps = ar.visual_fog_ease(many_steps, 1, 1.0/60.0)
	testing.expectf(t, visual_near(one_step, many_steps, .021), "equivalent wall time diverged: %.4f vs %.4f", one_step, many_steps)
	testing.expect(t, ar.visual_fog_ease(.3, 1, 0) == .3, "zero dt must not move presentation state")
	testing.expect(t, ar.visual_live_visibility_ease(1,false,ar.SIM_DT)==0, "lost LOS must conceal light immediately")
	testing.expect(t, ar.visual_live_visibility_ease(0,true,ar.SIM_DT)>0, "new LOS should ease open")
}

@(test)
visual_wall_ghost_rejects_grazes_and_ramps_real_occlusion :: proc(t: ^testing.T) {
	testing.expect(t, ar.visual_ghost_coverage_contribution(.25, .9) == 0, "same-depth wall must not ghost")
	testing.expect(t, ar.visual_ghost_coverage_contribution(1, .02) == 0, "2%% corner graze must not ghost")
	covered := ar.visual_ghost_coverage_contribution(1, .70)
	target := ar.visual_ghost_target(covered)
	testing.expectf(t, visual_near(covered, .70), "full-depth coverage %.3f, want .70", covered)
	testing.expect(t, target > 0 && target < 1, "meaningful partial cover must yield a partial ghost")
	testing.expect(t, ar.visual_ghost_target(.90) == 1, "fully swallowed actor must reach full ghost")
	eased := ar.visual_ghost_ease(0, 1, 1.0/60.0)
	testing.expect(t, eased > .25 && eased < .30, "60 Hz ghost fade should match pygame's ~28%% pull")
	testing.expect(t,ar.VISUAL_RELIC_GHOST_SPRITE_ALPHA>ar.VISUAL_GHOST_SPRITE_ALPHA&&ar.VISUAL_RELIC_GHOST_SPRITE_ALPHA<=1,
		"small relic ghosts must remain more legible than actors without exceeding valid alpha")
	testing.expect(t,ar.VISUAL_RELIC_GHOST_AURA_ALPHA>ar.VISUAL_GHOST_AURA_ALPHA&&ar.VISUAL_RELIC_GHOST_AURA_ALPHA<=1,
		"relic wall aura must be stronger than the actor aura without exceeding valid alpha")
}

@(test)
visual_idle_clock_animates_without_touching_locomotion_phase :: proc(t: ^testing.T) {
	testing.expect(t,ar.visual_idle_clip_time(1,4)>ar.visual_idle_clip_time(.5,4),"idle render clock must advance with world time")
	testing.expect(t,ar.visual_idle_clip_time(1,4)!=ar.visual_idle_clip_time(1,5),"stable actor IDs should de-sync idle phases")
	clip,clip_time:=ar.visual_lossless_soul_clip(false,false,false,3,4)
	testing.expect(t,clip==.Dance&&clip_time==0,"unresolved waiting Soul must retain its deliberate still pose")
	clip,clip_time=ar.visual_lossless_soul_clip(true,false,false,3,4)
	testing.expect(t,clip==.Dance&&clip_time==4,"armed Soul must loop its only idle-capable clip after Mistbound")
	_,next_time:=ar.visual_lossless_soul_clip(true,false,false,3,5)
	testing.expect(t,next_time>clip_time,"armed Soul idle animation must advance with the world presentation clock")
	clip,clip_time=ar.visual_lossless_soul_clip(true,true,false,3,4)
	testing.expect(t,clip==.Walk&&clip_time==3,"armed Soul locomotion must retain its simulation animation clock")
	clip,clip_time=ar.visual_lossless_soul_clip(false,false,true,3,4)
	testing.expect(t,clip==.Dance&&clip_time==3,"explicit pre-verdict gestures must retain their simulation animation clock")
	testing.expect(t,ar.VISUAL_WALL_PAINTER_DEPTH_OFFSET>1,"walls/doors must deterministically paint after same-tile actors")
}

@(test)
visual_mist_parting_scales_with_speed_and_stays_bounded :: proc(t: ^testing.T) {
	testing.expect(t, ar.visual_mist_falloff(0) == 1, "parting must be full strength at the actor's feet")
	edge_sq := ar.VISUAL_MIST_CLEAR_RADIUS * ar.VISUAL_MIST_CLEAR_RADIUS
	testing.expect(t, ar.visual_mist_falloff(edge_sq) == 0, "parting must vanish at the authored radius")
	testing.expect(t, ar.visual_mist_falloff(edge_sq * 4) == 0, "far cells must stay untouched")
	mid := ar.visual_mist_falloff(edge_sq * .25)
	testing.expect(t, mid > 0 && mid < 1, "falloff must ramp continuously inside the radius")
	stand := ar.visual_mist_clear_target(1, 0)
	walk := ar.visual_mist_clear_target(1, 1)
	testing.expectf(t, visual_near(stand, ar.VISUAL_MIST_STAND_CLEAR), "standing parting %.3f", stand)
	testing.expectf(t, visual_near(walk, ar.VISUAL_MIST_WALK_CLEAR), "walking parting %.3f", walk)
	testing.expect(t, walk > stand, "movement must part more mist than presence alone")
	testing.expect(t, ar.visual_mist_speed_norm(ar.PLAYER_MOVE_SPEED) == 1, "reference walk speed must map to a full wake")
	testing.expect(t, ar.visual_mist_speed_norm(99) == 1, "dash bursts must not overdrive the wake")
}

@(test)
visual_mist_recovery_is_frame_rate_independent_and_lingers :: proc(t: ^testing.T) {
	one_step := ar.visual_mist_recover(1, .5)
	many: f32 = 1
	for _ in 0 ..< 30 do many = ar.visual_mist_recover(many, .5 / 30)
	testing.expectf(t, visual_near(one_step, many, .002), "recovery diverged across frame rates: %.4f vs %.4f", one_step, many)
	testing.expect(t, ar.visual_mist_recover(.8, 0) == .8, "zero dt must not refill mist")
	testing.expect(t, ar.visual_mist_recover(1, 1) > .5, "a wake must still read one second later")
	testing.expect(t, ar.visual_mist_recover(1, 10) < .05, "mist must eventually seep back everywhere")
}

@(test)
visual_mist_stamps_only_deepen_and_pushes_stay_clamped :: proc(t: ^testing.T) {
	risen := ar.visual_mist_approach(.2, .8, ar.SIM_DT)
	testing.expect(t, risen > .2 && risen < .8, "stamps must ease toward their target without overshoot")
	testing.expect(t, ar.visual_mist_approach(.6, .3, ar.SIM_DT) == .6, "a weaker stamp must not close an existing wake")
	ahead := ar.visual_mist_push_target({1, 0}, {ar.PLAYER_MOVE_SPEED, 0}, 1)
	testing.expect(t, ahead.x > ar.VISUAL_MIST_PUSH_RADIAL, "mist ahead of motion must be shoved outward harder than by presence")
	still := ar.visual_mist_push_target({0, 1}, {0, 0}, 1)
	testing.expect(t, still.y > 0 && abs(still.x) < 1e-5, "presence alone must still displace radially")
	clamped := ar.visual_mist_push_clamp({9, 0})
	testing.expectf(t, visual_near(clamped.x, ar.VISUAL_MIST_PUSH_MAX), "push must clamp to the encode range, got %.3f", clamped.x)
	decayed := ar.visual_mist_push_decay({.4, -.4}, 10)
	testing.expect(t, abs(decayed.x) < .01 && abs(decayed.y) < .01, "displaced mist must settle back")
	round_trip := (f32(ar.visual_mist_push_encode(.25)) / 255 * 2 - 1) * ar.VISUAL_MIST_PUSH_MAX
	testing.expectf(t, visual_near(round_trip, .25, .01), "push encode round trip drifted: %.4f", round_trip)
}

@(test)
visual_mist_zones_cover_a_seeded_subset_of_rooms :: proc(t: ^testing.T) {
	rng := ar.rng_make(77)
	d, ok := ar.dungeon_generate(&rng)
	testing.expect(t, ok, "dungeon must generate")
	zone_a: [ar.MAP_W][ar.MAP_H]f32
	zone_b: [ar.MAP_W][ar.MAP_H]f32
	seed := ar.visual_mist_zone_seed(1234, 3, 0)
	ar.visual_mist_zones(&d, seed, &zone_a)
	ar.visual_mist_zones(&d, seed, &zone_b)
	testing.expect(t, zone_a == zone_b, "zones must be deterministic for a floor seed")
	misty, clear, open_tiles := 0, 0, 0
	for x in 0 ..< ar.MAP_W {
		for y in 0 ..< ar.MAP_H {
			value := zone_a[x][y]
			testing.expect(t, value >= 0 && value <= 1, "zone values must stay normalized")
			if d.tiles[x][y] == .Wall do continue
			open_tiles += 1
			if value > .9 do misty += 1
			if value < .05 do clear += 1
		}
	}
	testing.expect(t, open_tiles > 0 && misty > 0, "at least one chamber must hold mist")
	testing.expect(t, clear > 0, "mist must never blanket a whole floor")
	zone_next: [ar.MAP_W][ar.MAP_H]f32
	ar.visual_mist_zones(&d, ar.visual_mist_zone_seed(1234, 4, 0), &zone_next)
	testing.expect(t, zone_next != zone_a, "each floor must deal its own mist banks")
}
