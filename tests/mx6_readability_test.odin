package archrogue_tests

// MX.6 — deterministic combat readability. These tests keep presentation
// policy raylib-free while driving public simulation entry points for every
// action path that can be reached headlessly.

import "core:math"
import "core:testing"
import ar "../src"

MX6_EPS :: f32(1e-4)

@(private = "file")
mx6_near :: proc(a, b: f32, epsilon: f32 = MX6_EPS) -> bool {
	return abs(a - b) <= epsilon
}

@(private = "file")
mx6_prepare_arena :: proc(run: ^ar.Run, archetype: ar.Archetype_Id, seed: u64 = 9600) {
	ar.run_start(run, ar.derive_seed(seed, 0), archetype)
	for x in 0 ..< ar.MAP_W {
		for y in 0 ..< ar.MAP_H do run.dungeon.tiles[x][y] = .Wall
	}
	for x in 6 ..= 22 {
		for y in 6 ..= 16 do run.dungeon.tiles[x][y] = .Floor
	}
	run.dungeon.room_count = 0
	run.dungeon.special_room_count = 0
	run.dungeon.bar_furnishings = {}
	run.dungeon.solid_props = {}
	run.dungeon.stairs = {21, 15}
	run.dungeon.boss_arena = false
	run.boss_engaged = false
	clear(&run.sealed)
	run.nav = {}
	run.floor_epoch += 1

	run.player.pos = {10.5, 10.5}
	run.player.prev_pos = run.player.pos
	run.player.facing = {1, 0}
	run.player.hp = 500
	run.player.max_hp = 500
	run.player.mana = 200
	run.player.max_mana = 200
	run.player.stamina = 200
	run.player.max_stamina = 200
	clear(&run.enemies)
	clear(&run.projectiles)
	clear(&run.familiars)
	clear(&run.bells)
	clear(&run.numbers)
	clear(&run.ground_items)
	clear(&run.sfx)
	clear(&run.feel)
	clear(&run.traps)
	clear(&run.shrines)
	clear(&run.secrets)
}

@(private = "file")
mx6_dummy :: proc(pos: ar.Vec2, hp: int = 400) -> ar.Enemy {
	enemy := ar.enemy_make(.Ghoul, pos, 1)
	enemy.hp = hp
	enemy.max_hp = hp
	enemy.resistances = {}
	enemy.cooldown = 100
	return enemy
}

@(private = "file")
mx6_event_count :: proc(run: ^ar.Run, kind: ar.Feel_Kind) -> int {
	if run == nil do return 0
	count := 0
	for event in run.feel do if event.kind == kind do count += 1
	return count
}

@(private = "file")
mx6_event_phase_count :: proc(run: ^ar.Run, kind: ar.Feel_Kind, phase: ar.Feel_Phase) -> int {
	if run == nil do return 0
	count := 0
	for event in run.feel do if event.kind == kind && event.phase == phase do count += 1
	return count
}

@(private = "file")
mx6_first_event :: proc(run: ^ar.Run, kind: ar.Feel_Kind) -> ^ar.Feel_Event {
	if run == nil do return nil
	for &event in run.feel do if event.kind == kind do return &event
	return nil
}

@(test)
mx6_miniboss_foil_policy_excludes_elites_and_is_deterministic :: proc(t: ^testing.T) {
	testing.expect(t, !ar.visual_miniboss_effect_enabled(.Normal), "normal enemies must not receive the Oathbound treatment")
	testing.expect(t, !ar.visual_miniboss_effect_enabled(.Elite), "elites must not receive the Oathbound treatment")
	testing.expect(t, ar.visual_miniboss_effect_enabled(.Miniboss), "minibosses must receive the Oathbound treatment")
	testing.expect(t, !ar.visual_miniboss_effect_enabled(.Boss), "boss presentation remains separate from the Oathbound treatment")

	start := ar.visual_miniboss_foil_progress(2.5, 17)
	repeat := ar.visual_miniboss_foil_progress(2.5, 17)
	wrapped := ar.visual_miniboss_foil_progress(2.5 + ar.VISUAL_MINIBOSS_FOIL_PERIOD, 17)
	other := ar.visual_miniboss_foil_progress(2.5, 18)
	testing.expect(t, mx6_near(start, repeat) && mx6_near(start, wrapped),
		"miniboss foil phase must be deterministic and periodic")
	testing.expect(t, !mx6_near(start, other), "stable ids must stagger miniboss foil sweeps")
}

@(test)
mx6_continuous_aim_survives_sprite_row_quantization :: proc(t: ^testing.T) {
	straight := ar.Vec2{1, 0}
	fine_aim := ar.Vec2{1, .12}
	testing.expect(t, ar.sprite_row_for_facing(straight) == ar.sprite_row_for_facing(fine_aim),
		"nearby continuous aims should intentionally share one quantized sprite row")

	straight_cone := ar.visual_aim_cone(straight)
	fine_cone := ar.visual_aim_cone(fine_aim)
	testing.expect(t, straight_cone.valid && fine_cone.valid, "non-zero aim must produce readable cones")
	testing.expect(t, straight_cone.direction != fine_cone.direction,
		"cone geometry must use continuous aim rather than the sprite row")
	testing.expectf(t, abs(straight_cone.angle_degrees - fine_cone.angle_degrees) > 5,
		"continuous aim angles collapsed to %.3f and %.3f", straight_cone.angle_degrees, fine_cone.angle_degrees)
	testing.expect(t, mx6_near(straight_cone.inner_radius, 16) && mx6_near(straight_cone.outer_radius, 60.5),
		"aim cone radii changed")
	testing.expect(t, mx6_near(straight_cone.half_angle_degrees, .21 * 180 / math.PI),
		"aim cone half-angle must preserve the authored continuous arc")
	testing.expect(t, !ar.visual_aim_cone({}).valid, "zero aim must not invent a telegraph")
}

@(test)
mx6_enemy_pending_actions_classify_every_attack_family :: proc(t: ^testing.T) {
	enemy := ar.enemy_make(.Ghoul, {}, 1)
	enemy.ranged = false
	testing.expect(t, ar.enemy_action_kind_for_pending(&enemy, ar.PENDING_BASE_ATTACK) == .Attack,
		"base melee must classify as Attack")
	enemy.ranged = true
	testing.expect(t, ar.enemy_action_kind_for_pending(&enemy, ar.PENDING_BASE_ATTACK) == .Cast,
		"base ranged attack must classify as Cast")
	testing.expect(t, ar.enemy_action_kind_for_pending(&enemy, ar.PENDING_LEGACY_MELEE) == .Attack,
		"legacy close-band melee must override a ranged base profile")
	testing.expect(t, ar.enemy_action_kind_for_pending(&enemy, ar.PENDING_LEGACY_CAST) == .Cast,
		"legacy cast-band fan must classify as Cast")

	enemy.ranged = false
	enemy.ability_count = 1
	enemy.abilities[0] = .Gate_Strike
	testing.expect(t, ar.enemy_action_kind_for_pending(&enemy, 0) == .Attack,
		"Strike abilities must classify as Attack")
	enemy.abilities[0] = .Arcane_Lance
	testing.expect(t, ar.enemy_action_kind_for_pending(&enemy, 0) == .Cast,
		"Bolt abilities must classify as Cast")
	enemy.abilities[0] = .Frost_Fan
	testing.expect(t, ar.enemy_action_kind_for_pending(&enemy, 0) == .Cast,
		"Fan abilities must classify as Cast")
	enemy.abilities[0] = .Ember_Nova
	testing.expect(t, ar.enemy_action_kind_for_pending(&enemy, 0) == .Cast,
		"Nova abilities must classify as Cast")
	testing.expect(t, ar.enemy_action_kind_for_pending(nil, 0) == .None, "nil enemy classification must be inert")
}

@(test)
mx6_enemy_windup_telegraphs_cover_every_attack_family_and_count_down :: proc(t:^testing.T) {
	enemy:=ar.enemy_make(.Ghoul,{},1)
	enemy.attack_range=1.25
	ar.enemy_begin_windup(&enemy,.5,ar.PENDING_BASE_ATTACK,{3,4})
	melee:=ar.visual_enemy_telegraph(&enemy)
	testing.expect(t,melee.valid&&melee.kind==.Melee,"base melee windup must produce a directional melee tell")
	testing.expect(t,mx6_near(melee.aim.x,.6)&&mx6_near(melee.aim.y,.8),"telegraph must retain normalized committed aim")
	testing.expect(t,melee.progress==0&&!melee.imminent,"a fresh windup must begin at zero progress without an impact warning")
	testing.expect(t,ar.VISUAL_ENEMY_TELEGRAPH_WALL_ALPHA>=.35&&ar.VISUAL_ENEMY_TELEGRAPH_WALL_ALPHA<=.5,
		"through-wall telegraph trace must remain prominent but subordinate to the normal tell")

	enemy.windup=.2
	late:=ar.visual_enemy_telegraph(&enemy)
	testing.expect(t,late.progress>melee.progress&&late.imminent,"the tell must grow urgent and mark the final attack window")

	enemy.ranged=true
	enemy.attack_range=5
	ranged:=ar.visual_enemy_telegraph(&enemy)
	testing.expect(t,ranged.kind==.Bolt&&mx6_near(ranged.attack_range,5),"base ranged windup must show its projectile lane")
	enemy.big=true
	fan:=ar.visual_enemy_telegraph(&enemy)
	testing.expect(t,fan.kind==.Fan&&fan.projectile_count==3&&fan.spread>0,"large base casters must expose their three-projectile fan")

	enemy.big=false
	enemy.ranged=false
	enemy.ability_count=1
	enemy.pending_ability=0
	abilities:=[4]ar.Ability_Id{.Gate_Strike,.Arcane_Lance,.Frost_Fan,.Ember_Nova}
	kinds:=[4]ar.Visual_Enemy_Telegraph_Kind{.Melee,.Bolt,.Fan,.Nova}
	for ability,index in abilities {
		enemy.abilities[0]=ability
		plan:=ar.visual_enemy_telegraph(&enemy)
		testing.expectf(t,plan.valid&&plan.kind==kinds[index],"%v telegraph classified as %v, want %v",ability,plan.kind,kinds[index])
	}
	enemy.pending_ability=ar.PENDING_LEGACY_CAST
	legacy:=ar.visual_enemy_telegraph(&enemy)
	testing.expect(t,legacy.kind==.Fan&&legacy.projectile_count==3&&legacy.attack_range>=4,"legacy boss casts must retain a readable fan tell")

	enemy.ai=.Chase
	testing.expect(t,!ar.visual_enemy_telegraph(&enemy).valid,"non-windup enemies must not leak attack tells")
	testing.expect(t,!ar.visual_enemy_telegraph(nil).valid,"nil telegraph input must be inert")
}

@(test)
mx6_authored_enemy_commits_emit_their_semantic_actions :: proc(t: ^testing.T) {
	abilities := [4]ar.Ability_Id{.Gate_Strike, .Arcane_Lance, .Frost_Fan, .Ember_Nova}
	kinds := [4]ar.Enemy_Action_Kind{.Attack, .Cast, .Cast, .Cast}
	feel_kinds := [4]ar.Feel_Kind{.Slash, .Cast, .Cast, .Nova}
	projectile_counts := [4]int{0, 1, 5, 0}

	for ability, index in abilities {
		run: ar.Run
		mx6_prepare_arena(&run, .Warden, 9610 + u64(index))
		run.player.has_armor = false
		enemy_pos := index == 0 || index == 3 ? ar.Vec2{12.0, 10.5} : ar.Vec2{14.5, 10.5}
		enemy := ar.enemy_make(.Ghoul, enemy_pos, 1)
		enemy.damage = 24
		enemy.ability_count = 1
		enemy.abilities[0] = ability
		ar.enemy_begin_windup(&enemy, 0, 0, run.player.pos - enemy.pos)
		append(&run.enemies, enemy)
		hp_before := run.player.hp

		ar.sim_tick(&run, {})
		testing.expectf(t, run.enemies[0].action_kind == kinds[index],
			"%v committed as %v, want %v", ability, run.enemies[0].action_kind, kinds[index])
		testing.expect(t, run.enemies[0].pending_ability == ar.PENDING_BASE_ATTACK,
			"a committed authored slot must reset pending state")
		testing.expectf(t, mx6_event_count(&run, feel_kinds[index]) == 1,
			"%v emitted %v %v events, want one", ability, mx6_event_count(&run, feel_kinds[index]), feel_kinds[index])
		testing.expectf(t, len(run.projectiles) == projectile_counts[index],
			"%v left %v projectiles, want %v", ability, len(run.projectiles), projectile_counts[index])
		if ability == .Gate_Strike || ability == .Ember_Nova {
			testing.expectf(t, run.player.hp < hp_before, "%v must damage an in-range player", ability)
		}
		for projectile in run.projectiles do testing.expect(t, projectile.visual == .Enemy_Void,
			"authored enemy projectiles must use Enemy_Void")
		ar.run_destroy(&run)
	}
}

@(test)
mx6_committed_enemy_action_outlives_pending_then_expires_on_its_own_clock :: proc(t: ^testing.T) {
	run: ar.Run
	mx6_prepare_arena(&run, .Warden, 9620)
	defer ar.run_destroy(&run)
	run.player.has_armor = false
	enemy := ar.enemy_make(.Ghoul, {11.45, 10.5}, 1)
	enemy.damage = 8
	enemy.ability_count = 1
	enemy.abilities[0] = .Gate_Strike
	ar.enemy_begin_windup(&enemy, 0, 0, {-1, 0})
	append(&run.enemies, enemy)

	ar.sim_tick(&run, {})
	testing.expect(t, run.enemies[0].pending_ability == ar.PENDING_BASE_ATTACK,
		"commit must reset the pending slot immediately")
	testing.expect(t, run.enemies[0].action_kind == .Attack,
		"the committed semantic action must survive that reset")
	testing.expect(t, mx6_near(run.enemies[0].action_timer, ar.ENEMY_ATTACK_ACTION_SECONDS) &&
		mx6_near(run.enemies[0].action_duration, ar.ENEMY_ATTACK_ACTION_SECONDS),
		"commit must start the independent recovery-pose clock")
	testing.expect(t, ar.enemy_action_progress(&run.enemies[0]) == 0,
		"a newly committed action starts at frame zero")

	for _ in 0 ..< 6 do ar.sim_tick(&run, {})
	testing.expect(t, run.enemies[0].action_kind == .Attack && run.enemies[0].action_timer > 0,
		"the action must persist through early cooldown recovery")
	testing.expect(t, ar.enemy_action_progress(&run.enemies[0]) > 0,
		"the retained action clock must advance")
	testing.expect(t, run.enemies[0].pending_ability == ar.PENDING_BASE_ATTACK,
		"pending state must remain independently reset")

	for _ in 0 ..< 10 do ar.sim_tick(&run, {})
	testing.expect(t, run.enemies[0].action_kind == .None && run.enemies[0].action_timer == 0,
		"the semantic action must expire after its own 0.22s window")
	testing.expect(t, run.enemies[0].cooldown > 0.5,
		"action expiry must not wait for or erase the longer attack recovery")
	testing.expect(t, ar.enemy_action_progress(&run.enemies[0]) == 0,
		"expired actions expose no residual clip progress")
}

@(test)
mx6_enemy_and_familiar_missing_clip_policies_are_explicit :: proc(t: ^testing.T) {
	enemy := ar.Enemy{role = .Normal, action_kind = .Attack, action_timer = .1, action_duration = .22}
	testing.expect(t, ar.visual_enemy_pose(&enemy, false, false) == .Locomotion,
		"ordinary missing attack clip must fall back to locomotion")
	testing.expect(t, ar.visual_enemy_pose(&enemy, true, false) == .Attack,
		"ordinary authored attack clip must be selected")
	enemy.action_kind = .Cast
	testing.expect(t, ar.visual_enemy_pose(&enemy, true, false) == .Locomotion,
		"ordinary cast must not alias an attack clip when Cast is missing")
	testing.expect(t, ar.visual_enemy_pose(&enemy, false, true) == .Cast,
		"ordinary authored Cast clip must be selected")

	enemy.role = .Boss
	testing.expect(t, ar.visual_enemy_pose(&enemy, true, false) == .Attack,
		"boss Cast explicitly reuses its authored attack sheet")
	testing.expect(t, ar.visual_enemy_pose(&enemy, true, true) == .Attack,
		"boss Cast must prefer attack even if a cast clip is present")
	testing.expect(t, ar.visual_enemy_pose(&enemy, false, true) == .Locomotion,
		"boss Cast with no attack sheet must remain visible through locomotion")
	enemy.action_timer = 0
	testing.expect(t, ar.visual_enemy_pose(&enemy, true, true) == .Locomotion,
		"expired semantic actions cannot pin a pose")

	// Wisp/Crow sheets currently omit Attack; their gameplay clock still runs,
	// but the visual policy deliberately refuses a missing clip. Spirit Beast has
	// an authored Attack clip and reads the same independent clock.
	testing.expect(t, !ar.visual_familiar_uses_attack_pose(ar.FAMILIAR_ATTACK_ANIMATION_TIME, false),
		"Wisp/Crow missing-attack policy must fall back")
	testing.expect(t, ar.visual_familiar_uses_attack_pose(ar.FAMILIAR_ATTACK_ANIMATION_TIME, true),
		"Spirit Beast authored attack must use its attack clock")
	testing.expect(t, !ar.visual_familiar_uses_attack_pose(0, true),
		"an authored clip must not play after its independent clock expires")
}

@(test)
mx6_projectile_render_age_tracks_the_interpolated_fixed_step :: proc(t: ^testing.T) {
	age: f32 = f32(ar.SIM_DT) * 5
	previous := age - f32(ar.SIM_DT)
	alphas := [5]f32{0, .25, .5, .75, 1}
	for alpha in alphas {
		expected := previous + (age - previous) * alpha
		actual := ar.visual_projectile_render_age(age, alpha)
		repeated := ar.visual_projectile_render_age(age, alpha)
		testing.expectf(t, mx6_near(actual, expected),
			"alpha %.2f produced age %.6f, want %.6f", alpha, actual, expected)
		testing.expect(t, actual == repeated, "equal projectile age inputs must be deterministic")
	}
	testing.expect(t, ar.visual_projectile_render_age(age, 0) == previous,
		"alpha zero must use the previous authoritative visual age")
	testing.expect(t, ar.visual_projectile_render_age(age, 1) == age,
		"alpha one must use the current authoritative visual age")

	young_age: f32 = f32(ar.SIM_DT) * .5
	testing.expect(t, ar.visual_projectile_render_age(young_age, 0) == 0,
		"a projectile younger than one fixed step cannot render with negative age")
	testing.expectf(t, mx6_near(ar.visual_projectile_render_age(young_age, .5), young_age * .5),
		"young projectile age must interpolate from its clamped zero-age origin")
	testing.expect(t, ar.visual_projectile_render_age(young_age, 1) == young_age,
		"young projectile must still reach its current age at alpha one")
	testing.expect(t, ar.visual_projectile_render_age(age, -1) == previous &&
		ar.visual_projectile_render_age(age, 2) == age,
		"render alpha must clamp without extrapolating visual age")
}

@(test)
mx6_isometric_radials_project_tile_circles_coherently :: proc(t: ^testing.T) {
	radius_tiles: f32 = 3.5
	progress: f32 = .4
	scaled_radius := radius_tiles * progress
	root_two := math.sqrt(f32(2))
	radii := ar.visual_iso_radial_radii(radius_tiles, progress)
	testing.expectf(t, mx6_near(radii.x, scaled_radius * f32(ar.TILE_HALF_W) * root_two),
		"horizontal radial radius %.4f does not match tile-circle projection", radii.x)
	testing.expectf(t, mx6_near(radii.y, scaled_radius * f32(ar.TILE_HALF_H) * root_two),
		"vertical radial radius %.4f does not match tile-circle projection", radii.y)
	testing.expectf(t, mx6_near(radii.x / radii.y, f32(ar.TILE_HALF_W) / f32(ar.TILE_HALF_H)),
		"projected radial axes must retain the isometric 2:1 ratio")

	component := scaled_radius / root_two
	horizontal_tile := ar.Vec2{component, -component}
	vertical_tile := ar.Vec2{component, component}
	horizontal := ar.visual_iso_radial_offset(radius_tiles, progress, 0)
	vertical := ar.visual_iso_radial_offset(radius_tiles, progress, f32(math.PI) * .5)
	expected_horizontal := ar.world_from_tile(horizontal_tile)
	expected_vertical := ar.world_from_tile(vertical_tile)
	testing.expect(t, mx6_near(horizontal.x, radii.x) && mx6_near(horizontal.y, 0),
		"zero-angle radial endpoint must lie on the positive horizontal axis")
	testing.expect(t, mx6_near(vertical.x, 0) && mx6_near(vertical.y, radii.y),
		"quarter-turn radial endpoint must lie on the positive vertical axis")
	testing.expect(t, mx6_near(horizontal.x, expected_horizontal.x) && mx6_near(horizontal.y, expected_horizontal.y),
		"horizontal radial endpoint must agree with world_from_tile")
	testing.expect(t, mx6_near(vertical.x, expected_vertical.x) && mx6_near(vertical.y, expected_vertical.y),
		"vertical radial endpoint must agree with world_from_tile")

	angle: f32 = .63
	cosine, sine := math.cos(angle), math.sin(angle)
	expected_tile := ar.Vec2{
		component * (cosine + sine),
		component * (sine - cosine),
	}
	offset := ar.visual_iso_radial_offset(radius_tiles, progress, angle)
	expected_offset := ar.world_from_tile(expected_tile)
	testing.expect(t, mx6_near(offset.x, expected_offset.x) && mx6_near(offset.y, expected_offset.y),
		"arbitrary radial endpoint must remain the projection of a tile-space circle")
	testing.expect(t, ar.visual_iso_radial_radii(radius_tiles, -1) == ar.Vec2{} &&
		ar.visual_iso_radial_offset(radius_tiles, -1, angle) == ar.Vec2{},
		"negative radial progress must clamp to zero")
	full := ar.visual_iso_radial_radii(radius_tiles, 2)
	testing.expect(t, mx6_near(full.x, radius_tiles * f32(ar.TILE_HALF_W) * root_two) &&
		mx6_near(full.y, radius_tiles * f32(ar.TILE_HALF_H) * root_two),
		"radial progress must clamp at the full tile-space radius")
}

@(test)
mx6_engulf_room_nova_flash_advances_as_a_bounded_manhattan_wave :: proc(t: ^testing.T) {
	event := ar.Feel_Event{
		kind = .Nova,
		pos = {10, 10},
		duration = .48,
		remaining = .48,
		engulf_room = true,
	}
	testing.expect(t, ar.visual_nova_room_flash_strength(&event, event.pos) == 1,
		"engulf-room Nova must reach its origin immediately at full event life")
	testing.expect(t, ar.visual_nova_room_flash_strength(&event, {11, 10}) == 0,
		"adjacent tile must stay dark before the first wave step arrives")

	event.remaining = event.duration - f32(ar.SIM_DT) * 2.5
	axis_strength := ar.visual_nova_room_flash_strength(&event, {12, 10})
	diagonal_strength := ar.visual_nova_room_flash_strength(&event, {11, 11})
	testing.expect(t, mx6_near(axis_strength, ar.feel_life(&event)) && mx6_near(diagonal_strength, axis_strength),
		"equal Manhattan distances must receive the same reached-wave strength")
	testing.expect(t, ar.visual_nova_room_flash_strength(&event, {12, 11}) == 0,
		"a Manhattan-distance-three tile must remain dark before wave arrival")

	event.remaining = event.duration * .5
	half_life := ar.visual_nova_room_flash_strength(&event, {12, 10})
	event.remaining = event.duration * .25
	quarter_life := ar.visual_nova_room_flash_strength(&event, {12, 10})
	testing.expect(t, mx6_near(half_life, .5) && mx6_near(quarter_life, .25) && quarter_life < half_life,
		"reached room tiles must fade with bounded event life")
	testing.expect(t, half_life >= 0 && half_life <= 1 && quarter_life >= 0 && quarter_life <= 1,
		"room flash strength must stay in the unit interval")

	event.engulf_room = false
	testing.expect(t, ar.visual_nova_room_flash_strength(&event, event.pos) == 0,
		"ordinary Nova must not invent an engulf-room flash")
	event.engulf_room = true
	event.kind = .Cast
	testing.expect(t, ar.visual_nova_room_flash_strength(&event, event.pos) == 0 &&
		ar.visual_nova_room_flash_strength(nil, event.pos) == 0,
		"non-Nova and nil events must be inert")
}

@(test)
mx6_projectile_styles_frames_trails_and_projection_are_deterministic :: proc(t: ^testing.T) {
	expected := [ar.Archetype_Id]ar.Projectile_Visual{
		.Warden = .Warden_Guard,
		.Rogue = .Rogue_Dagger,
		.Arcanist = .Arcanist_Arc,
		.Acolyte = .Acolyte_Spirit,
		.Ranger = .Ranger_Arrow,
	}
	seen: [ar.Projectile_Visual]bool
	for archetype in ar.Archetype_Id {
		visual := ar.projectile_visual_for_archetype(archetype)
		testing.expectf(t, visual == expected[archetype], "%v mapped to %v", archetype, visual)
		testing.expect(t, visual != .Enemy_Void, "player projectile cannot use the enemy silhouette")
		testing.expectf(t, !seen[visual], "%v projectile silhouette is not distinct", archetype)
		seen[visual] = true

		run: ar.Run
		mx6_prepare_arena(&run, archetype, 9630 + u64(int(archetype)))
		testing.expectf(t, ar.player_cast_bolt(&run, {1, .12}), "%v bolt must cast", archetype)
		testing.expect(t, len(run.projectiles) > 0, "successful bolt must create a projectile")
		for projectile in run.projectiles do testing.expect(t, projectile.visual == visual,
			"gameplay projectile must carry its class silhouette")
		cast_event := mx6_first_event(&run, .Cast)
		testing.expect(t, cast_event != nil && cast_event.style == ar.feel_style_for_archetype(archetype),
			"successful bolt must emit its class Cast event")
		ar.run_destroy(&run)
	}

	// The base ranged commit goes through the real simulation and tags every
	// enemy-owned bolt with the separate void silhouette.
	run: ar.Run
	mx6_prepare_arena(&run, .Warden, 9640)
	defer ar.run_destroy(&run)
	imp := ar.enemy_make(.Bone_Imp, {14.5, 10.5}, 1)
	ar.enemy_begin_windup(&imp, 0, ar.PENDING_BASE_ATTACK, {-1, 0})
	append(&run.enemies, imp)
	ar.sim_tick(&run, {})
	testing.expect(t, len(run.projectiles) == 1, "base ranged commit must create one bolt")
	for projectile in run.projectiles do testing.expect(t, projectile.visual == .Enemy_Void,
		"enemy bolt must remain visually distinct from all five player styles")

	testing.expect(t, ar.VISUAL_PROJECTILE_FRAME_COUNT == 4 && mx6_near(ar.VISUAL_PROJECTILE_FPS, 12),
		"projectile raster must remain four frames at 12 FPS")
	frame_step := f32(1) / ar.VISUAL_PROJECTILE_FPS
	testing.expect(t, ar.visual_projectile_frame(0) == 0)
	testing.expect(t, ar.visual_projectile_frame(frame_step * .99) == 0)
	testing.expect(t, ar.visual_projectile_frame(frame_step * 1.01) == 1)
	testing.expect(t, ar.visual_projectile_frame(frame_step * 3.01) == 3)
	testing.expect(t, ar.visual_projectile_frame(frame_step * 4.01) == 0,
		"the four-frame projectile cycle must wrap")

	trails_a := ar.visual_projectile_trails({1, 0}, .25)
	trails_b := ar.visual_projectile_trails({1, 0}, .25)
	trails_shifted := ar.visual_projectile_trails({1, 0}, .35)
	testing.expect(t, trails_a == trails_b, "trail plans must be deterministic for equal age and velocity")
	testing.expect(t, trails_a != trails_shifted, "fixed visual age must animate the deterministic side weave")
	direction := ar.visual_iso_direction({1, 0})
	for trail, index in trails_a {
		along := trail.offset.x * direction.x + trail.offset.y * direction.y
		testing.expectf(t, mx6_near(along, -9 * f32(index + 1)),
			"trail %v sits %.3f px along flight, want %.3f", index, along, -9 * f32(index + 1))
		if index > 0 {
			testing.expect(t, trail.alpha < trails_a[index - 1].alpha && trail.radius < trails_a[index - 1].radius,
				"successive trail samples must fade and narrow")
		}
	}
	expected_angle := math.atan2(f32(.5), f32(1)) * f32(180) / f32(math.PI)
	testing.expectf(t, mx6_near(ar.visual_projectile_rotation({1, 0}), expected_angle),
		"projectile rotation must use projected isometric direction")
	testing.expect(t, mx6_near(ar.visual_projectile_rotation({1, 0}), ar.visual_aim_cone({1, 0}).angle_degrees),
		"aim cone and projectile must agree in projected space")
	testing.expect(t, ar.visual_projectile_rotation({}) == 0, "stationary projectile rotation must be safe")
}

@(test)
mx6_player_slashes_land_at_contact_or_forward_whiff :: proc(t: ^testing.T) {
	run: ar.Run
	mx6_prepare_arena(&run, .Warden, 9645)
	defer ar.run_destroy(&run)

	whiff := ar.player_slash_origin(&run, {1, 0})
	testing.expect(t, mx6_near(whiff.x, run.player.pos.x + .9) && mx6_near(whiff.y, run.player.pos.y),
		"a whiffed player slash must read 0.9 tile forward")

	target := mx6_dummy({11.7, 10.5})
	append(&run.enemies, target)
	contact := ar.player_slash_origin(&run, {1, 0})
	want := (run.player.pos + run.enemies[0].pos) * .5
	testing.expect(t, contact == want, "a targeted player slash must land at the nearest contact midpoint")

	ar.player_melee(&run, {1, 0})
	slash := mx6_first_event(&run, .Slash)
	testing.expect(t, slash != nil && slash.pos == want, "base melee must emit its slash at contact")
	clear(&run.feel)
	run.enemies[0].hp = run.enemies[0].max_hp
	ar.player_big_hit_fire(&run)
	slash = mx6_first_event(&run, .Slash)
	testing.expect(t, slash != nil && slash.pos == want && slash.heavy,
		"Big Hit must share the contact point and retain its heavy envelope")
}

@(test)
mx6_slash_envelope_and_knockback_samples_match_authored_ratios :: proc(t: ^testing.T) {
	slash := ar.Feel_Event{
		kind = .Slash,
		direction = {1, -1},
		duration = 1,
		remaining = 1,
		radius = .42,
	}
	start := ar.visual_slash_sample(&slash)
	testing.expect(t, start.valid && mx6_near(start.alpha, 1) && mx6_near(start.scale, 1),
		"fresh slash starts opaque at base scale")
	testing.expect(t, mx6_near(start.center_offset.x, 0) && mx6_near(start.center_offset.y, -18),
		"fresh slash starts at the actor")

	slash.remaining = .5
	middle := ar.visual_slash_sample(&slash)
	testing.expect(t, mx6_near(middle.alpha, .5), "slash alpha follows remaining life")
	testing.expectf(t, mx6_near(middle.scale, 1.05), "half-life slash scale %.3f, want 1.05", middle.scale)
	testing.expect(t, mx6_near(middle.center_offset.x, 6) && mx6_near(middle.center_offset.y, -18),
		"slash must travel six projected pixels by half life")

	slash.remaining = 0
	finish := ar.visual_slash_sample(&slash)
	testing.expect(t, finish.alpha == 0 && finish.scale > middle.scale,
		"slash must continue growing while fading away")
	testing.expect(t, mx6_near(finish.center_offset.x, 12), "slash travel caps at twelve projected pixels")

	slash.remaining = .5
	slash.heavy = true
	heavy := ar.visual_slash_sample(&slash)
	testing.expectf(t, mx6_near(heavy.scale, 1.05 * 1.18),
		"heavy slash scale %.3f, want the 1.18 multiplier", heavy.scale)

	knockback := ar.Feel_Event{
		kind = .Knockback_Travel,
		pos = {3, 4},
		direction = {3, 4},
		radius = 10,
	}
	samples := ar.visual_knockback_samples(&knockback)
	first_distance := math.hypot(samples[0].x - knockback.pos.x, samples[0].y - knockback.pos.y)
	second_distance := math.hypot(samples[1].x - knockback.pos.x, samples[1].y - knockback.pos.y)
	testing.expectf(t, mx6_near(first_distance, knockback.radius * .35),
		"first knockback sample %.3f, want 35%%", first_distance)
	testing.expectf(t, mx6_near(second_distance, knockback.radius * .70),
		"second knockback sample %.3f, want 70%%", second_distance)
	testing.expect(t, mx6_near(second_distance, first_distance * 2),
		"70%% sample must be exactly twice the 35%% sample")
}

@(test)
mx6_dash_time_skip_and_nova_emit_semantic_events :: proc(t: ^testing.T) {
	run: ar.Run
	mx6_prepare_arena(&run, .Warden, 9650)
	start := run.player.pos
	testing.expect(t, ar.player_dash(&run, {1, 0}), "Warden dash must succeed")
	testing.expect(t, mx6_event_count(&run, .Dash) == 2 &&
		mx6_event_phase_count(&run, .Dash, .Start) == 1 && mx6_event_phase_count(&run, .Dash, .End) == 1,
		"dash must emit one start and one end envelope")
	testing.expect(t, run.feel[0].pos == start && run.feel[1].pos == run.player.pos && run.feel[0].style == .Warden,
		"dash endpoints must preserve start, arrival, and class style")

	clear(&run.feel)
	run.player.class_skill_timer = 0
	testing.expect(t, ar.player_cast_class_skill(&run, {1, 0}), "Time Skip must cast")
	time_skip := mx6_first_event(&run, .Time_Skip)
	testing.expect(t, time_skip != nil && time_skip.style == .Warden && time_skip.priority == .High,
		"Time Skip must emit its Warden high-priority envelope")
	if time_skip != nil {
		testing.expect(t, mx6_near(time_skip.duration, .62) && mx6_near(time_skip.radius, 3.2),
			"Time Skip envelope changed")
	}
	ar.run_destroy(&run)

	run = {}
	mx6_prepare_arena(&run, .Arcanist, 9651)
	defer ar.run_destroy(&run)
	testing.expect(t, ar.player_cast_class_skill(&run, {1, 0}), "Nova must cast")
	nova := mx6_first_event(&run, .Nova)
	testing.expect(t, nova != nil && nova.style == .Arcanist && nova.priority == .High,
		"Nova must emit its Arcanist envelope")
	if nova != nil {
		testing.expect(t, mx6_near(nova.duration, .48) && mx6_near(nova.radius, ar.nova_radius(&run.player)),
			"Nova event must carry gameplay radius and authored duration")
	}
}

@(test)
mx6_spirit_hosts_keep_attack_clocks_when_missing_clips_and_beast_commands_emit :: proc(t: ^testing.T) {
	for rank in 0 ..= 1 {
		run: ar.Run
		mx6_prepare_arena(&run, .Acolyte, 9660 + u64(rank))
		testing.expectf(t, ar.player_cast_spirit_call_rank(&run, rank), "Spirit Call rank %v must cast", rank)
		expected_kind := rank == 0 ? ar.Familiar_Kind.Wisp : ar.Familiar_Kind.Crow
		testing.expect(t, len(run.familiars) == 1 && run.familiars[0].kind == expected_kind,
			"rank zero summons Wisp and rank one summons Crow")
		testing.expect(t, mx6_event_phase_count(&run, .Summon, .Origin) == 1 &&
			mx6_event_phase_count(&run, .Summon, .Arrival) == 1,
			"Spirit Call must emit origin and familiar arrival")

		target := mx6_dummy(run.familiars[0].pos + ar.Vec2{.8, 0})
		append(&run.enemies, target)
		anim_before := run.familiars[0].anim_time
		ar.tick_familiars_dt(&run, .01)
		testing.expect(t, run.enemies[0].hp < run.enemies[0].max_hp, "summoned host must attack")
		testing.expect(t, mx6_near(run.familiars[0].attack_anim_timer, ar.FAMILIAR_ATTACK_ANIMATION_TIME),
			"host gameplay attack clock must start even without an authored Attack clip")
		testing.expect(t, run.familiars[0].attack_timer > run.familiars[0].attack_anim_timer,
			"attack cooldown and visual attack clock must remain independent")
		testing.expect(t, run.familiars[0].anim_time == anim_before,
			"attacking in place must not consume locomotion phase")
		testing.expect(t, !ar.visual_familiar_uses_attack_pose(run.familiars[0].attack_anim_timer, false),
			"Wisp/Crow clock must fall back when the Attack clip is absent")
		ar.tick_familiars_dt(&run, .10)
		testing.expect(t, mx6_near(run.familiars[0].attack_anim_timer, ar.FAMILIAR_ATTACK_ANIMATION_TIME - .10),
			"host attack animation clock must decay by dt")
		ar.run_destroy(&run)
	}

	run: ar.Run
	mx6_prepare_arena(&run, .Ranger, 9665)
	defer ar.run_destroy(&run)
	testing.expect(t, ar.player_cast_spirit_beast_rank(&run, 0), "Spirit Beast must summon")
	testing.expect(t, mx6_event_phase_count(&run, .Summon, .Origin) == 1 &&
		mx6_event_phase_count(&run, .Summon, .Arrival) == 1,
		"Spirit Beast summon must emit origin and arrival")
	beast := ar.living_spirit_beast(&run)
	testing.expect(t, beast != nil, "living Spirit Beast must be discoverable")
	if beast == nil do return
	target := mx6_dummy(beast.pos + ar.Vec2{.8, 0})
	append(&run.enemies, target)
	anim_before := beast.anim_time
	ar.tick_familiars_dt(&run, .01)
	testing.expect(t, mx6_near(beast.attack_anim_timer, ar.FAMILIAR_ATTACK_ANIMATION_TIME) &&
		ar.visual_familiar_uses_attack_pose(beast.attack_anim_timer, true),
		"Spirit Beast must drive its authored attack clip from the independent clock")
	testing.expect(t, beast.anim_time == anim_before, "Spirit Beast bite must not advance walk phase")

	clear(&run.feel)
	testing.expect(t, ar.player_cast_spirit_beast_rank(&run, 0),
		"a living beast must accept a free command despite replacement cooldown")
	testing.expect(t, beast.command == .Follow && beast.attack_anim_timer == 0,
		"return command must cancel only the beast attack pose")
	command := mx6_first_event(&run, .Command)
	testing.expect(t, command != nil && command.style == .Ranger && command.priority == .High,
		"Spirit Beast command must emit the Ranger command envelope")
}

@(test)
mx6_ambush_bell_plants_arms_once_and_detonates :: proc(t: ^testing.T) {
	run: ar.Run
	mx6_prepare_arena(&run, .Rogue, 9670)
	defer ar.run_destroy(&run)
	testing.expect(t, ar.player_cast_class_skill(&run, {1, 0}), "Ambush Bell must plant")
	testing.expect(t, len(run.bells) == 1, "successful cast must own one bell")
	testing.expect(t, mx6_event_count(&run, .Cast) == 1 &&
		mx6_event_phase_count(&run, .Bell_Plant, .Origin) == 1,
		"plant path must emit cast and Bell_Plant origin")

	clear(&run.feel)
	arm_time := run.bells[0].arm_timer
	ar.tick_ambush_bells(&run, arm_time - .01)
	testing.expect(t, !run.bells[0].armed_announced && mx6_event_count(&run, .Bell_Arm) == 0,
		"bell must not announce before crossing the arm threshold")
	ar.tick_ambush_bells(&run, .02)
	testing.expect(t, run.bells[0].armed_announced && mx6_event_count(&run, .Bell_Arm) == 1,
		"crossing the threshold must announce exactly once")
	ar.tick_ambush_bells(&run, 0)
	ar.tick_ambush_bells(&run, .10)
	testing.expect(t, mx6_event_count(&run, .Bell_Arm) == 1,
		"armed bell must not repeat its announcement on later or zero-dt ticks")

	victim := mx6_dummy(run.bells[0].pos)
	append(&run.enemies, victim)
	ar.tick_ambush_bells(&run, 0)
	testing.expect(t, len(run.bells) == 0, "armed bell must detonate on a target crossing")
	testing.expect(t, mx6_event_phase_count(&run, .Bell_Detonate, .Triggered) == 1,
		"triggered detonation must carry the Triggered phase")

	// A restored/pre-armed bell is also required to announce on the first zero-dt
	// policy pass, then latch just like one that crossed from a positive timer.
	clear(&run.enemies)
	clear(&run.bells)
	clear(&run.feel)
	append(&run.bells, ar.Ambush_Bell{
		pos = {12.5, 10.5},
		lifetime = 1,
		arm_timer = 0,
		lure_radius = 2,
		trigger_radius = .8,
		damage_radius = 1,
	})
	ar.tick_ambush_bells(&run, 0)
	testing.expect(t, run.bells[0].armed_announced && mx6_event_count(&run, .Bell_Arm) == 1,
		"pre-armed zero-dt bell must announce once")
	ar.tick_ambush_bells(&run, 0)
	testing.expect(t, mx6_event_count(&run, .Bell_Arm) == 1,
		"pre-armed zero-dt policy pass must remain idempotent")
}

@(test)
mx6_ranked_deaths_preserve_body_envelopes_and_semantic_payoffs :: proc(t: ^testing.T) {
	run: ar.Run
	mx6_prepare_arena(&run, .Warden, 9680)
	defer ar.run_destroy(&run)
	combat_before := run.combat_rng
	loot_before := run.loot_rng
	accent := [4]u8{210, 90, 240, 255}
	enemy := mx6_dummy({12, 10})
	enemy.color = {90, 80, 70, 255}

	ar.feel_emit_enemy_death(&run, &enemy, accent)
	testing.expect(t, len(run.feel) == 1 && run.feel[0].kind == .Death,
		"normal death emits only its body envelope")
	testing.expect(t, mx6_near(run.feel[0].duration, .58) && mx6_near(run.feel[0].radius, .56),
		"normal body envelope changed")

	clear(&run.feel)
	enemy.role = .Elite
	ar.feel_emit_enemy_death(&run, &enemy, accent)
	testing.expect(t, len(run.feel) == 2 && run.feel[0].kind == .Death && run.feel[1].kind == .Elite_Death,
		"elite death must preserve body then add Elite_Death")
	testing.expect(t, mx6_near(run.feel[0].duration, .66) && mx6_near(run.feel[0].radius, .68) &&
		mx6_near(run.feel[1].duration, .48), "elite death envelopes changed")

	clear(&run.feel)
	enemy.role = .Miniboss
	ar.feel_emit_enemy_death(&run, &enemy, accent)
	testing.expect(t, len(run.feel) == 2 && run.feel[0].kind == .Death && run.feel[1].kind == .Miniboss_Death,
		"miniboss death must preserve body then add Miniboss_Death")
	testing.expect(t, mx6_near(run.feel[0].duration, .74) && mx6_near(run.feel[0].radius, .80) &&
		run.feel[1].color == accent, "miniboss body/accent envelope changed")

	clear(&run.feel)
	enemy.role = .Boss
	enemy.big = true
	ar.feel_emit_enemy_death(&run, &enemy, accent)
	testing.expect(t, len(run.feel) == 3 && run.feel[0].kind == .Death &&
		run.feel[1].kind == .Boss_Payoff && run.feel[2].kind == .Screen_Flash,
		"boss death must preserve body, payoff, and flash order")
	testing.expect(t, mx6_near(run.feel[0].duration, .82) && mx6_near(run.feel[0].radius, 1.05),
		"boss body death envelope must not be shortened by the rank event")
	testing.expect(t, mx6_near(run.feel[1].duration, .72) && mx6_near(run.feel[1].radius, .96) &&
		run.feel[1].priority == .Critical, "big boss payoff envelope changed")
	testing.expect(t, run.feel[2].visibility == .World && run.feel[2].priority == .Critical,
		"boss screen flash remains LOS-scoped and critical")
	testing.expect(t, run.combat_rng == combat_before && run.loot_rng == loot_before,
		"ranked presentation envelopes must consume no gameplay RNG")
}

@(test)
mx6_priority_saturation_replaces_only_oldest_lower_priority_for_boss_payoff :: proc(t: ^testing.T) {
	run: ar.Run
	mx6_prepare_arena(&run, .Warden, 9685)
	defer ar.run_destroy(&run)
	combat_before := run.combat_rng
	loot_before := run.loot_rng

	for index in 0 ..< ar.MAX_FEEL_EVENTS {
		ar.feel_emit(&run, .Hit, {f32(index), 0}, {255, 255, 255, 255}, 1, .1, priority = .Normal)
	}
	ar.feel_emit(&run, .Boss_Payoff, {-1, 0}, {255, 0, 0, 255}, .72, .96, priority = .Critical)
	testing.expect(t, len(run.feel) == ar.MAX_FEEL_EVENTS, "saturated queue must stay bounded")
	testing.expect(t, run.feel[0].kind == .Boss_Payoff && run.feel[0].pos.x == -1,
		"Boss_Payoff must replace the oldest lower-priority event")
	testing.expect(t, run.feel[1].kind == .Hit && run.feel[1].pos.x == 1 &&
		run.feel[len(run.feel) - 1].pos.x == f32(ar.MAX_FEEL_EVENTS - 1),
		"replacement must preserve every later event and its order")

	ar.feel_emit(&run, .Slash, {-2, 0}, {255, 255, 255, 255}, 1, .1, priority = .Normal)
	testing.expect(t, mx6_event_count(&run, .Slash) == 0,
		"equal-priority saturation remains drop-new rather than displacing history")

	clear(&run.feel)
	for index in 0 ..< ar.MAX_FEEL_EVENTS {
		ar.feel_emit(&run, .Screen_Flash, {f32(index), 0}, {255, 255, 255, 255}, 1, 0, priority = .Critical)
	}
	ar.feel_emit(&run, .Boss_Payoff, {-3, 0}, {255, 0, 0, 255}, .72, .96, priority = .Critical)
	testing.expect(t, mx6_event_count(&run, .Boss_Payoff) == 0 && run.feel[0].pos.x == 0,
		"Boss_Payoff must preserve a queue already saturated by equal critical events")
	testing.expect(t, run.combat_rng == combat_before && run.loot_rng == loot_before,
		"queue pressure and replacement must consume no gameplay RNG")
}

@(test)
mx6_visibility_light_profiles_and_lifetime_are_scoped :: proc(t: ^testing.T) {
	world := ar.Feel_Event{visibility = .World}
	local := ar.Feel_Event{visibility = .Player_Local}
	global := ar.Feel_Event{visibility = .Global}
	testing.expect(t, !ar.feel_event_visible(&world, false, false), "hidden world event must remain hidden")
	testing.expect(t, ar.feel_event_visible(&world, true, false), "visible world event must render")
	testing.expect(t, ar.feel_event_visible(&world, false, true), "developer reveal may expose world events")
	testing.expect(t, ar.feel_event_visible(&local, false, false) && ar.feel_event_visible(&global, false, false),
		"player-local and global feedback must not depend on source LOS")
	testing.expect(t, !ar.feel_event_visible(nil, true, true), "nil visibility query must be safe")

	event := ar.Feel_Event{kind = .Cast, duration = .28, remaining = .28}
	profile := ar.feel_light_profile(&event)
	testing.expect(t, profile.enabled && mx6_near(profile.radius, 2.1) && mx6_near(profile.intensity, .85) &&
		mx6_near(profile.duration, .28) && mx6_near(profile.lift, 12), "Cast light profile changed")
	testing.expect(t, mx6_near(ar.feel_light_life(&event, profile), 1), "fresh light starts at full life")
	event.remaining = .14
	testing.expect(t, mx6_near(ar.feel_light_life(&event, profile), .5), "light life follows profile duration")
	event.remaining = 0
	testing.expect(t, ar.feel_light_life(&event, profile) == 0, "expired light must clamp to zero")

	event = ar.Feel_Event{kind = .Summon, phase = .Origin}
	origin := ar.feel_light_profile(&event)
	event.phase = .Arrival
	arrival := ar.feel_light_profile(&event)
	testing.expect(t, origin.radius > arrival.radius && origin.duration > arrival.duration,
		"summon origin must read wider/longer than arrival")

	event = ar.Feel_Event{kind = .Bell_Detonate, phase = .Triggered}
	triggered := ar.feel_light_profile(&event)
	event.phase = .Expired
	expired := ar.feel_light_profile(&event)
	testing.expect(t, triggered.radius > expired.radius && triggered.intensity > expired.intensity &&
		mx6_near(triggered.duration, .42) && mx6_near(expired.duration, .34),
		"triggered bell detonation must outshine expiration without outliving either carrier")

	event.kind = .Elite_Death
	elite := ar.feel_light_profile(&event)
	event.kind = .Miniboss_Death
	miniboss := ar.feel_light_profile(&event)
	event.kind = .Boss_Payoff
	boss := ar.feel_light_profile(&event)
	testing.expect(t, elite.radius < miniboss.radius && miniboss.radius < boss.radius &&
		elite.intensity < miniboss.intensity && miniboss.intensity < boss.intensity,
		"ranked death lights must escalate monotonically")

	event.kind = .Slash
	unlit := ar.feel_light_profile(&event)
	testing.expect(t, !unlit.enabled && ar.feel_light_life(&event, unlit) == 0,
		"ordinary slash raster must not invent a light")
}

@(test)
mx6_light_profile_durations_are_carrier_safe :: proc(t: ^testing.T) {
	events := [6]ar.Feel_Event{
		{kind = .Dash, phase = .Start, duration = .24, remaining = .24},
		{kind = .Dash, phase = .End, duration = .26, remaining = .26},
		{kind = .Bell_Plant, phase = .Origin, duration = .30, remaining = .30},
		{kind = .Bell_Arm, duration = .24, remaining = .24},
		{kind = .Bell_Detonate, phase = .Triggered, duration = .44, remaining = .44},
		{kind = .Bell_Detonate, phase = .Expired, duration = .34, remaining = .34},
	}
	expected := [6]f32{.24, .26, .30, .24, .42, .34}
	for &event, index in events {
		profile := ar.feel_light_profile(&event)
		testing.expectf(t, profile.enabled, "%v/%v carrier unexpectedly has no light", event.kind, event.phase)
		testing.expectf(t, mx6_near(profile.duration, expected[index]),
			"%v/%v light duration %.3f, want %.3f", event.kind, event.phase, profile.duration, expected[index])
		testing.expectf(t, profile.duration <= event.duration,
			"%v/%v light duration %.3f outlives %.3f carrier", event.kind, event.phase, profile.duration, event.duration)
	}

	start := ar.feel_light_profile(&events[0])
	finish := ar.feel_light_profile(&events[1])
	testing.expect(t, start.radius == finish.radius && start.intensity == finish.intensity && start.lift == finish.lift,
		"Dash phases may differ in duration only; established light shape must stay unchanged")
}

@(test)
mx6_feel_compaction_is_stable_and_every_operation_is_rng_free :: proc(t: ^testing.T) {
	run: ar.Run
	mx6_prepare_arena(&run, .Warden, 9690)
	defer ar.run_destroy(&run)
	combat_before := run.combat_rng
	loot_before := run.loot_rng

	ar.feel_emit(&run, .Hit, {1, 0}, {255, 255, 255, 255}, .10, .1)
	ar.feel_emit(&run, .Cast, {2, 0}, {255, 255, 255, 255}, .50, .1)
	ar.feel_emit(&run, .Blood, {3, 0}, {255, 255, 255, 255}, .15, .1)
	ar.feel_emit(&run, .Nova, {4, 0}, {255, 255, 255, 255}, .60, .1)
	ar.tick_feel_events(&run, .20)
	testing.expect(t, len(run.feel) == 2, "two expired events must compact away")
	testing.expect(t, run.feel[0].kind == .Cast && run.feel[0].pos.x == 2 &&
		run.feel[1].kind == .Nova && run.feel[1].pos.x == 4,
		"stable compaction must preserve survivor painter order")
	testing.expect(t, mx6_near(run.feel[0].remaining, .30) && mx6_near(run.feel[1].remaining, .40),
		"survivor lifetimes must decrement exactly once")

	ar.tick_feel_events(&run, 0)
	testing.expect(t, len(run.feel) == 2 && run.feel[0].kind == .Cast && run.feel[1].kind == .Nova,
		"zero-dt compaction pass must be inert")
	ar.clear_feel_events(&run)

	enemy := mx6_dummy({12, 10})
	enemy.role = .Elite
	ar.feel_emit_enemy_hit(&run, &enemy, .Physical)
	ar.feel_emit_enemy_cast(&run, &enemy)
	ar.feel_emit_enemy_nova(&run, &enemy, 2.6)
	ar.feel_emit_enemy_slash(&run, enemy.pos, {-1, 0}, enemy.color)
	ar.feel_emit_player_hurt(&run, 20)
	ar.feel_emit_enemy_death(&run, &enemy, {220, 80, 210, 255})
	ar.enemy_start_knockback(&run, &enemy, {4, 0})
	ar.tick_feel_events(&run, .05)
	ar.clear_feel_events(&run)
	testing.expect(t, len(run.feel) == 0, "clear must empty the presentation queue")
	testing.expect(t, run.combat_rng == combat_before && run.loot_rng == loot_before,
		"emit, helper, knockback-envelope, tick, compaction, and clear operations must consume no combat/loot RNG")
}

@(test)
mx6_ranged_boss_close_legacy_melee_hits_without_spawning_a_bolt :: proc(t: ^testing.T) {
	run: ar.Run
	mx6_prepare_arena(&run, .Warden, 9700)
	defer ar.run_destroy(&run)
	run.player.has_armor = false
	boss := ar.enemy_make(.Bone_Imp, {11.5, 10.5}, 1)
	boss.role = .Boss
	boss.big = false
	boss.ranged = true
	boss.ability_count = 0
	boss.attack_range = 1.9
	boss.aggro_range = 20
	boss.damage = 30
	boss.ai = .Chase
	boss.cooldown = 0
	append(&run.enemies, boss)

	choice, _ := ar.select_boss_attack(&run.enemies[0], 1.0)
	testing.expect(t, choice == .Legacy_Melee, "close ranged boss must select legacy melee fallback")
	hp_before := run.player.hp
	ar.sim_tick(&run, {})
	testing.expect(t, run.enemies[0].ai == .Windup &&
		run.enemies[0].pending_ability == ar.PENDING_LEGACY_MELEE,
		"boss chase must preserve the explicit legacy-melee pending classification")
	testing.expect(t, len(run.projectiles) == 0 && run.player.hp == hp_before,
		"windup itself must neither fire nor damage")

	run.enemies[0].windup = 0
	ar.sim_tick(&run, {})
	testing.expect(t, run.player.hp < hp_before, "committed close legacy melee must damage the player")
	testing.expect(t, len(run.projectiles) == 0, "ranged base profile must not leak a bolt into legacy melee")
	testing.expect(t, run.enemies[0].action_kind == .Attack &&
		run.enemies[0].pending_ability == ar.PENDING_BASE_ATTACK,
		"legacy melee commit must retain Attack while resetting pending state")
	slash := mx6_first_event(&run, .Slash)
	testing.expect(t, slash != nil && slash.style == .Enemy,
		"legacy melee commit must emit the enemy slash envelope")
}

@(test)
mx6_lethal_big_hit_keeps_knockback_travel_after_corpse_sweep :: proc(t: ^testing.T) {
	run: ar.Run
	mx6_prepare_arena(&run, .Warden, 9710)
	defer ar.run_destroy(&run)
	victim_pos := ar.Vec2{11.5, 10.5}
	victim := mx6_dummy(victim_pos, 1)
	victim.xp = 0
	append(&run.enemies, victim)

	testing.expect(t, ar.player_big_hit_begin(&run, {1, 0}), "Big Hit must begin charging")
	// Preserve the public charge path while advancing directly to its deterministic
	// final fixed step; the same tick fires, sweeps the corpse, and leaves feel.
	run.player.bighit_charge = ar.SIM_DT * .5
	ar.sim_tick(&run, {})
	testing.expect(t, len(run.enemies) == 0, "lethal Big Hit victim must be swept this tick")
	testing.expect(t, mx6_event_count(&run, .Death) == 1,
		"corpse sweep must still emit the body death envelope")
	knockback := mx6_first_event(&run, .Knockback_Travel)
	testing.expect(t, knockback != nil, "lethal throw must retain Knockback_Travel after the enemy is gone")
	if knockback != nil {
		testing.expect(t, knockback.pos == victim_pos && knockback.heavy && knockback.priority == .High,
			"lethal Big Hit must preserve launch origin and heavy priority")
		testing.expectf(t, mx6_near(knockback.radius, ar.BIGHIT_THROW_TILES),
			"knockback travel radius %.3f, want v0/decay = %.3f", knockback.radius, ar.BIGHIT_THROW_TILES)
		samples := ar.visual_knockback_samples(knockback)
		testing.expect(t, samples[0].x > victim_pos.x && samples[1].x > samples[0].x,
			"post-sweep envelope must still reconstruct forward travel samples")
	}
}
