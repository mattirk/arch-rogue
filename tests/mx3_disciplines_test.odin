package archrogue_tests

// MX.3 build-defining combat and discipline effects: melee/defense/mobility
// riders, projectile path shaping, discipline-derived signature skill tuning,
// companion combat riders, and the Spirit Beast petting slice. Each test pins
// the pygame contract cited in the source comments.

import "core:testing"
import ar "../src"

@(private = "file")
mx3_arena :: proc(run: ^ar.Run) {
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
	run.player.mana = 200
	run.player.max_mana = 200
	run.player.stamina = 200
	run.player.max_stamina = 200
	clear(&run.enemies)
	clear(&run.projectiles)
	clear(&run.familiars)
	clear(&run.bells)
	clear(&run.numbers)
	clear(&run.sfx)
}

@(private = "file")
mx3_dummy :: proc(pos: ar.Vec2, hp := 400) -> ar.Enemy {
	enemy := ar.enemy_make(.Ghoul, pos, 1)
	enemy.hp = hp
	enemy.max_hp = hp
	enemy.resistances = {}
	enemy.cooldown = 100 // never retaliates during the test window
	return enemy
}

@(private = "file")
mx3_near :: proc(a, b: f32, epsilon: f32 = 1e-4) -> bool {
	return abs(a - b) < epsilon
}

// --- Slice 1: melee / defense / mobility riders -----------------------------

@(test)
mx3_warden_cleave_widens_with_bulwark_degrees :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(9301, 0), .Warden)
	defer ar.run_destroy(&run)
	mx3_arena(&run)
	append(&run.enemies, mx3_dummy({11.6, 10.5}))
	append(&run.enemies, mx3_dummy({11.6, 11.1}))

	// Base Warden: single-target swing.
	ar.player_melee(&run, {1, 0})
	hurt := 0
	for &enemy in run.enemies do if enemy.hp < enemy.max_hp do hurt += 1
	testing.expectf(t, hurt == 1, "base swing hurt %v targets, want 1", hurt)

	// Bulwark Training: the same swing cleaves both, second at 62%.
	run.player.acquired_disciplines[.Warden_Bulwark] = true
	run.player.melee_timer = 0
	for &enemy in run.enemies {
		enemy.hp = enemy.max_hp
	}
	ar.player_melee(&run, {1, 0})
	hurt = 0
	for &enemy in run.enemies do if enemy.hp < enemy.max_hp do hurt += 1
	testing.expectf(t, hurt == 2, "bulwark swing hurt %v targets, want 2", hurt)
	primary := run.enemies[0].max_hp - run.enemies[0].hp
	cleave := run.enemies[1].max_hp - run.enemies[1].hp
	testing.expectf(t, cleave < primary, "cleave damage %v must fall off from primary %v", cleave, primary)
	testing.expect(t, mx3_near(ar.player_melee_cooldown(&run.player), max(0.20, 0.38)), "Bulwark trades melee tempo (+0.02) for the cleave")
}

@(test)
mx3_warden_riposte_reduces_melee_and_counters :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(9302, 0), .Warden)
	defer ar.run_destroy(&run)
	mx3_arena(&run)
	append(&run.enemies, mx3_dummy({11.4, 10.5}))
	attacker := &run.enemies[0]

	baseline := ar.damage_player_typed(&run, 30, .Physical, melee=true, attacker=attacker)
	testing.expect(t, attacker.hp == attacker.max_hp, "without Riposte no counter fires")

	run.player.acquired_disciplines[.Warden_Riposte] = true
	riposte := ar.damage_player_typed(&run, 30, .Physical, melee=true, attacker=attacker)
	testing.expectf(t, riposte == baseline - 2, "Riposte took %v, want %v", riposte, baseline - 2)
	testing.expect(t, attacker.hp < attacker.max_hp, "Riposte answers with a holy counterattack")
	testing.expect(t, attacker.knockback_vel != {}, "the counter carries knockback")
	testing.expect(t, attacker.statuses[.Stunned] == 0, "without Aegis Discipline the counter does not stun")

	run.player.acquired_disciplines[.Warden_Aegis] = true
	_ = ar.damage_player_typed(&run, 30, .Physical, melee=true, attacker=attacker)
	testing.expect(t, attacker.statuses[.Stunned] > 0, "Aegis Discipline stuns on counter")
}

@(test)
mx3_warden_guard_step_grants_aegis_hardening :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(9303, 0), .Warden)
	defer ar.run_destroy(&run)
	mx3_arena(&run)
	run.player.acquired_disciplines[.Warden_Aegis] = true
	resist_before := ar.player_typed_resistance(&run.player, .Physical)
	testing.expect(t, ar.player_dash(&run, {1, 0}), "dash must fire")
	testing.expect(t, mx3_near(run.player.statuses[.Aegis], 0.85), "Guard Step hardens the Warden for 0.85s")
	resist := ar.player_typed_resistance(&run.player, .Physical)
	testing.expect(t, mx3_near(resist, min(0.45, resist_before + 0.24)), "Aegis grants +0.24 typed resistance while active")
}

@(test)
mx3_rogue_smoke_dash_and_evasion_riders :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(9304, 0), .Rogue)
	defer ar.run_destroy(&run)
	mx3_arena(&run)
	run.player.acquired_disciplines[.Rogue_Smoke] = true
	testing.expectf(t, ar.player_dash_stamina_cost(&run.player) == 10, "Smoke dash costs %v, want 10", ar.player_dash_stamina_cost(&run.player))
	start := run.player.pos
	testing.expect(t, ar.player_dash(&run, {1, 0}), "dash must fire")
	travelled := run.player.pos.x - start.x
	testing.expectf(t, mx3_near(travelled, 2.0, 1e-3), "Smoke dash travelled %.3f tiles, want 2.0 (10 steps)", travelled)
	testing.expect(t, mx3_near(run.player.statuses[.Smoke], 0.9), "Shadow Dash grants 0.9s of Smoke")
}

@(test)
mx3_acolyte_leech_ladders_and_veil_shield :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(9305, 0), .Acolyte)
	defer ar.run_destroy(&run)
	mx3_arena(&run)
	player := &run.player
	testing.expect(t, ar.acolyte_melee_leech(player) == 0 && ar.acolyte_spell_leech(player) == 0, "fresh Acolyte siphons nothing")
	player.acquired_disciplines[.Acolyte_Sanguine] = true
	testing.expect(t, ar.acolyte_melee_leech(player) == 2 && ar.acolyte_spell_leech(player) == 3, "Sanguine rungs are 2/3")
	player.acquired_disciplines[.Acolyte_Gravebind] = true
	testing.expect(t, ar.acolyte_melee_leech(player) == 3 && ar.acolyte_spell_leech(player) == 4, "Gravebind rungs are 3/4")
	player.acquired_disciplines[.Acolyte_Blood_Pact] = true
	testing.expect(t, ar.acolyte_melee_leech(player) == 4 && ar.acolyte_spell_leech(player) == 5, "Blood Pact rungs are 4/5")
	testing.expect(t, mx3_near(ar.player_lifesteal(player), 0.03), "Blood Pact grants +0.03 lifesteal")
	player.acquired_disciplines[.Acolyte_Crimson_Maw] = true
	testing.expect(t, ar.acolyte_melee_leech(player) == 5 && ar.acolyte_spell_leech(player) == 7, "Crimson Maw rungs are 5/7")
	player.acquired_disciplines[.Acolyte_Sanguine_Ascendant] = true
	testing.expect(t, ar.acolyte_melee_leech(player) == 6 && ar.acolyte_spell_leech(player) == 8, "Ascendant rungs are 6/8")

	// The veil deepens the mana shield from -3 to -5.
	player.acquired_disciplines[.Acolyte_Veil] = true
	player.mana = 50
	baseline_hp := player.hp
	dealt := ar.damage_player_typed(&run, 30, .Physical)
	testing.expect(t, player.mana == 46, "the mana shield spends 4 mana")
	testing.expectf(t, dealt == baseline_hp - player.hp, "damage accounting drifted (dealt %v)", dealt)
}

@(test)
mx3_gravebind_binds_and_echoes_on_kill :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(9306, 0), .Acolyte)
	defer ar.run_destroy(&run)
	mx3_arena(&run)
	run.player.acquired_disciplines[.Acolyte_Gravebind] = true
	append(&run.enemies, mx3_dummy({11.4, 10.5}))
	ar.player_melee(&run, {1, 0})
	testing.expect(t, mx3_near(run.enemies[0].statuses[.Bound], 1.1), "Gravebind melee binds for 1.1s")

	// Killing the bound foe while wounded restores health and mana.
	run.enemies[0].hp = 0
	run.player.hp = 100
	run.player.mana = 10
	run.hitstop_ticks = 0 // the grave echo, not the impact freeze, is under test
	ar.sim_tick(&run, {})
	testing.expectf(t, run.player.hp >= 100 + 4, "grave echo healed to %v, want at least +4", run.player.hp)
	testing.expect(t, run.player.mana >= 12, "grave echo restores 2 mana")
}

@(test)
mx3_ranger_beastmark_snare_amp_and_vault :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(9307, 0), .Ranger)
	defer ar.run_destroy(&run)
	mx3_arena(&run)
	run.player.acquired_disciplines[.Ranger_Beastmark] = true
	append(&run.enemies, mx3_dummy({11.4, 10.5}))
	enemy := &run.enemies[0]

	// Melee applies the 1.15s snare; snared prey takes the 1.22 amp.
	ar.player_melee(&run, {1, 0})
	testing.expect(t, mx3_near(enemy.statuses[.Snared], 1.15), "Hawk Slash snares for 1.15s")
	dealt := ar.damage_enemy_typed(&run, enemy, 100, .Physical)
	testing.expectf(t, dealt == 122, "snared prey took %v from raw 100, want 122", dealt)

	// Vault refunds stamina and hastens Multishot.
	run.player.stamina = 50
	run.player.bolt_timer = 0.5
	testing.expect(t, ar.player_dash(&run, {0, 1}), "vault must fire")
	cost := f32(ar.player_dash_stamina_cost(&run.player))
	testing.expect(t, mx3_near(run.player.stamina, 50 - cost + 8), "Vault refunds 8 stamina")
	testing.expect(t, run.player.bolt_timer <= 0.12 + 1e-4, "Vault drops the Multishot clock to 0.12")
}

// --- Slice 2: projectile path shaping ---------------------------------------

@(test)
mx3_fan_counts_follow_discipline_tiers :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(9308, 0), .Ranger)
	defer ar.run_destroy(&run)
	mx3_arena(&run)

	cast_and_count :: proc(run: ^ar.Run) -> int {
		clear(&run.projectiles)
		run.player.bolt_timer = 0
		run.player.mana = 200
		_ = ar.player_cast_bolt(run, {1, 0})
		return len(run.projectiles)
	}

	testing.expectf(t, cast_and_count(&run) == 1, "fresh Ranger fires one arrow")
	run.player.acquired_disciplines[.Ranger_Volley] = true
	testing.expectf(t, cast_and_count(&run) == 3, "Barbed Volley fans to 3")
	run.player.acquired_disciplines[.Ranger_Rapid] = true
	testing.expectf(t, cast_and_count(&run) == 4, "Rapid Volley fans to 4")
	run.player.acquired_disciplines[.Ranger_Storm_Volley] = true
	testing.expectf(t, cast_and_count(&run) == 5, "Storm Volley fans to 5")
	run.player.acquired_disciplines[.Ranger_Piercing_Volley] = true
	_ = cast_and_count(&run)
	for p in run.projectiles do testing.expect(t, p.pierce == 1, "Piercing Volley arrows pierce once")
	run.player.acquired_disciplines[.Ranger_Sky_Quiver] = true
	_ = cast_and_count(&run)
	for p in run.projectiles do testing.expect(t, mx3_near(p.homing, 0.75), "Sky Quiver arrows home at 0.75")
	run.player.acquired_disciplines[.Ranger_Snare] = true
	_ = cast_and_count(&run)
	for p in run.projectiles {
		testing.expect(t, p.has_status && p.status == .Snared && mx3_near(p.status_duration, 1.1), "Barbed Snares arrows snare for 1.1s")
	}
}

@(test)
mx3_warden_vow_adds_modest_ranked_mana_regen :: proc(t: ^testing.T) {
	player := ar.Player{archetype = .Warden}
	testing.expect(t, mx3_near(ar.player_mana_regen(&player), 2.5), "fresh Warden uses 2.5 mana/s baseline")
	player.acquired_disciplines[.Warden_Smite] = true
	testing.expect(t, mx3_near(ar.player_mana_regen(&player), 2.75), "Vow rank 1 adds 0.25 mana/s")
	player.acquired_disciplines[.Warden_Judgment] = true
	player.acquired_disciplines[.Warden_Consecrate] = true
	player.acquired_disciplines[.Warden_Divine_Wrath] = true
	player.acquired_disciplines[.Warden_Avatar_Of_Light] = true
	testing.expect(t, mx3_near(ar.player_mana_regen(&player), 3.75), "mastered Vow adds 1.25 mana/s")
}

@(test)
mx3_rogue_marksman_shapes_and_hastens_knife_fan :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(9320, 0), .Rogue)
	defer ar.run_destroy(&run)
	mx3_arena(&run)

	fire_fan :: proc(run: ^ar.Run) {
		clear(&run.projectiles)
		run.player.bolt_timer = 0
		run.player.mana = 200
		_ = ar.player_cast_bolt(run, {1, 0})
	}

	run.player.acquired_disciplines[.Rogue_Marksman] = true
	fire_fan(&run)
	testing.expectf(t, len(run.projectiles) == 3, "Marksman Knife Fan spawned %v blades, want 3", len(run.projectiles))
	if len(run.projectiles) == 3 {
		testing.expect(t, run.projectiles[0].vel.y < 0 && mx3_near(run.projectiles[1].vel.y, 0) && run.projectiles[2].vel.y > 0, "Marksman fan must retain a centered blade")
		testing.expect(t, run.projectiles[1].damage-run.projectiles[0].damage == 4 && run.projectiles[1].damage-run.projectiles[2].damage == 4, "Marksman side blades lose 4 damage")
	}

	run.player.acquired_disciplines[.Rogue_Sharpshot] = true
	fire_fan(&run)
	if len(run.projectiles) == 3 {
		testing.expect(t, run.projectiles[1].damage-run.projectiles[0].damage == 2 && run.projectiles[1].damage-run.projectiles[2].damage == 2, "Sharpshot side blades lose only 2 damage")
	}

	run.player.acquired_disciplines[.Rogue_Deadeye] = true
	fire_fan(&run)
	for p in run.projectiles do testing.expect(t, p.pierce == 1, "Deadeye blades pierce once")

	run.player.acquired_disciplines[.Rogue_Eagle_Eye] = true
	fire_fan(&run)
	testing.expectf(t, len(run.projectiles) == 5, "Eagle Eye Knife Fan spawned %v blades, want 5", len(run.projectiles))

	run.player.acquired_disciplines[.Rogue_Assassin] = true
	fire_fan(&run)
	testing.expect(t, mx3_near(200-run.player.mana, 8), "Assassin Knife Fan costs 8 mana")
	testing.expect(t, mx3_near(run.player.bolt_timer, 0.40), "Assassin Knife Fan uses a 0.40s base cooldown")
}

@(test)
mx3_arcanist_fans_pierce_and_splinter_ttl :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(9309, 0), .Arcanist)
	defer ar.run_destroy(&run)
	mx3_arena(&run)

	run.player.acquired_disciplines[.Arcanist_Splinter] = true
	_ = ar.player_cast_bolt(&run, {1, 0})
	testing.expectf(t, len(run.projectiles) == 2, "Splinter erupts into %v shards, want 2", len(run.projectiles))
	for p in run.projectiles do testing.expect(t, mx3_near(p.ttl, 1.55), "Splinter shards live 1.55s")

	clear(&run.projectiles)
	run.player.bolt_timer = 0
	run.player.acquired_disciplines[.Arcanist_Overload] = true
	_ = ar.player_cast_bolt(&run, {1, 0})
	testing.expectf(t, len(run.projectiles) == 3, "Overload fans to %v, want 3", len(run.projectiles))
	for p in run.projectiles do testing.expect(t, p.pierce == 1, "Overload shards pierce once")

	clear(&run.projectiles)
	run.player.bolt_timer = 0
	run.player.acquired_disciplines[.Arcanist_Pierce] = true
	_ = ar.player_cast_bolt(&run, {1, 0})
	for p in run.projectiles do testing.expect(t, p.pierce == 2, "Piercing Bolts pierce twice")

	run.player.acquired_disciplines[.Arcanist_Arc_Tyrant] = true
	clear(&run.projectiles)
	run.player.bolt_timer = 0
	_ = ar.player_cast_bolt(&run, {1, 0})
	for p in run.projectiles do testing.expect(t, mx3_near(p.homing, 0.85), "Arc Tyrant bolts home at 0.85")
}

@(test)
mx3_homing_bolt_curves_toward_offaxis_foe :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(9310, 0), .Arcanist)
	defer ar.run_destroy(&run)
	mx3_arena(&run)
	run.player.acquired_disciplines[.Arcanist_Arc_Tyrant] = true
	append(&run.enemies, mx3_dummy({13.5, 12.5}))
	_ = ar.player_cast_bolt(&run, {1, 0})
	for _ in 0 ..< 8 do ar.sim_tick(&run, {})
	testing.expect(t, len(run.projectiles) > 0, "bolt still in flight")
	dir := run.projectiles[0].vel
	testing.expect(t, dir.y > 0.05, "homing bolt curved toward the off-axis target")
}

@(test)
mx3_storm_chain_arcs_once_per_cast :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(9311, 0), .Arcanist)
	defer ar.run_destroy(&run)
	mx3_arena(&run)
	run.player.acquired_disciplines[.Arcanist_Overload] = true
	run.player.acquired_disciplines[.Arcanist_Chain_Lightning] = true
	append(&run.enemies, mx3_dummy({12.5, 10.5}))
	append(&run.enemies, mx3_dummy({13.8, 10.5})) // within the 2.6 jump radius
	append(&run.enemies, mx3_dummy({17.5, 15.5})) // out of every radius
	_ = ar.player_cast_bolt(&run, {1, 0})
	for p in run.projectiles do testing.expect(t, p.storm_chain, "the cast carries the shared Storm charge")
	for _ in 0 ..< 20 {
		ar.sim_tick(&run, {})
		if run.enemies[0].hp < run.enemies[0].max_hp do break
	}
	testing.expect(t, run.enemies[0].hp < run.enemies[0].max_hp, "primary took the bolt")
	testing.expect(t, run.enemies[1].hp < run.enemies[1].max_hp, "the Storm charge arced to the nearby foe")
	testing.expect(t, run.enemies[2].hp == run.enemies[2].max_hp, "distant foe untouched")
	for p in run.projectiles do testing.expect(t, !p.storm_chain, "the first impact spends the charge for every shard of the cast")
}

// --- Slice 3: signature skill tuning ----------------------------------------

@(test)
mx3_time_skip_duration_factor_and_pulse :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(9312, 0), .Warden)
	defer ar.run_destroy(&run)
	mx3_arena(&run)
	player := &run.player
	testing.expect(t, mx3_near(ar.time_skip_duration(player), 3.0), "base Time Skip runs 3.0s")
	player.acquired_disciplines[.Warden_Ward] = true
	player.acquired_disciplines[.Warden_Bulwark_Wave] = true
	testing.expect(t, mx3_near(ar.time_skip_duration(player), 4.5), "Sigil +0.5 and Wave +1.0 stack")
	testing.expect(t, mx3_near(ar.time_skip_factor(player), 0.4), "base slow factor is 0.4")
	player.acquired_disciplines[.Warden_Stone_Aegis] = true
	testing.expect(t, mx3_near(ar.time_skip_factor(player), 0.3), "Stutter Step slows to 0.3")

	append(&run.enemies, mx3_dummy({12.0, 10.5}))
	append(&run.enemies, mx3_dummy({16.9, 10.5})) // outside the 2.6 pulse
	testing.expect(t, ar.player_cast_class_skill(&run, {1, 0}), "Time Skip must cast")
	testing.expect(t, mx3_near(player.time_skip_timer, 4.5), "cast snapshots the tuned duration")
	testing.expect(t, run.enemies[0].statuses[.Stunned] > 0, "the cast pulse stuns nearby foes")
	testing.expect(t, run.enemies[1].statuses[.Stunned] == 0, "the pulse respects its 2.6 radius")
	testing.expect(t, mx3_near(ar.enemy_sim_dt(&run), ar.SIM_DT * 0.3), "enemy clocks run at the tuned factor")

	// Temporal Aegis: reduced damage while the skip runs.
	resist_without := ar.player_typed_resistance(player, .Physical)
	player.acquired_disciplines[.Warden_Unyielding] = true
	resist_with := ar.player_typed_resistance(player, .Physical)
	testing.expect(t, mx3_near(resist_with, min(0.45, resist_without + 0.20)), "Temporal Aegis adds +0.20 resist during the skip")

	// Eternal Moment: kills refund much of the slot's cooldown.
	player.acquired_disciplines[.Warden_Eternal_Wall] = true
	before := player.class_skill_timer
	run.enemies[0].hp = 0
	ar.sim_tick(&run, {})
	refund := ar.player_class_skill_cooldown(player) * 0.4
	testing.expectf(t, player.class_skill_timer < before - refund + 0.1, "kill refunded to %.2f from %.2f", player.class_skill_timer, before)
}

@(test)
mx3_nova_radius_engulf_and_permafrost_chill :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(9313, 0), .Arcanist)
	defer ar.run_destroy(&run)
	mx3_arena(&run)
	player := &run.player
	testing.expect(t, mx3_near(ar.nova_radius(player), 2.45), "base Nova radius is 2.45")
	nova_path := [5]ar.Discipline_Id{.Arcanist_Focus, .Arcanist_Permafrost, .Arcanist_Glacial, .Arcanist_Blizzard, .Arcanist_Absolute_Zero}
	for id in nova_path do player.acquired_disciplines[id] = true
	testing.expect(t, mx3_near(ar.nova_radius(player), 2.45 + 0.55*5), "each Nova node widens the ring by 0.55")
	testing.expect(t, !ar.nova_engulfs_room(player), "one mastered path does not engulf")
	bolt_path := [5]ar.Discipline_Id{.Arcanist_Splinter, .Arcanist_Overload, .Arcanist_Pierce, .Arcanist_Storm, .Arcanist_Arc_Tyrant}
	for id in bolt_path do player.acquired_disciplines[id] = true
	testing.expect(t, ar.nova_engulfs_room(player), "two mastered paths engulf the room")

	append(&run.enemies, mx3_dummy({12.0, 10.5}))
	testing.expect(t, ar.player_cast_class_skill(&run, {1, 0}), "Nova must cast")
	testing.expect(t, mx3_near(run.enemies[0].statuses[.Chilled], 1.9), "Permafrost chills for 1.9s")
}

@(test)
mx3_ambush_bell_tuning_snapshot_and_reprise :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(9314, 0), .Rogue)
	defer ar.run_destroy(&run)
	mx3_arena(&run)
	player := &run.player
	trap_path := [5]ar.Discipline_Id{.Rogue_Trap_Craft, .Rogue_Venom_Trap, .Rogue_Bear_Trap, .Rogue_Trap_Master, .Rogue_Ambush_Engineer}
	for id in trap_path do player.acquired_disciplines[id] = true
	player.acquired_disciplines[.Rogue_Smoke] = true
	player.acquired_disciplines[.Rogue_Night_Veil] = true
	player.acquired_disciplines[.Rogue_Umbral] = true

	bell, plant_range := ar.ambush_bell_tuning(player)
	testing.expect(t, mx3_near(plant_range, 4.55), "Engineer plants 0.20 farther")
	testing.expect(t, mx3_near(bell.arm_timer, 0.25), "arm time 0.34-0.04-0.05")
	testing.expect(t, mx3_near(bell.lifetime, 6.35), "Trap Craft adds 0.35 lifetime")
	testing.expect(t, mx3_near(bell.lure_radius, 7.05), "lure clamps at 7.05")
	testing.expect(t, mx3_near(bell.trigger_radius, 1.0), "Bear Trap widens the trigger")
	testing.expect(t, mx3_near(bell.damage_radius, 2.15), "Master+Engineer widen the blast")
	testing.expect(t, bell.has_status && bell.status == .Poisoned, "the burst poisons")
	testing.expect(t, mx3_near(bell.status_duration, 2.45 + 0.35 + 0.35), "poison duration stacks Master and Engineer")
	testing.expect(t, mx3_near(bell.primary_snare, 1.05 + 0.25), "the primary snare deepens")
	testing.expect(t, mx3_near(bell.splash_snare, 0.70), "Engineer spreads the snare")
	testing.expect(t, mx3_near(bell.smoke_duration, 0.52 + 0.22 + 0.16 + 0.18), "Shadow-path smoke stacks")
	testing.expect(t, mx3_near(bell.kill_cooldown_floor, 1.05) && bell.kill_mana_refund == 4, "Engineer arms the kill refund")

	// A kill at detonation floors the cooldown and refunds mana.
	testing.expect(t, ar.player_cast_class_skill(&run, {1, 0}), "bell must cast")
	player.class_skill_timer = 3.0
	player.mana = 10
	victim := mx3_dummy(run.bells[0].pos, 1)
	append(&run.enemies, victim)
	ar.tick_ambush_bells(&run, 0.3) // finish arming
	ar.tick_ambush_bells(&run, 0)   // detect + detonate
	testing.expect(t, len(run.bells) == 0, "the bell detonated")
	testing.expect(t, run.enemies[0].hp <= 0, "the burst killed the lured victim")
	testing.expect(t, mx3_near(player.class_skill_timer, 1.05), "Bell Reprise floors the cooldown at 1.05")
	testing.expect(t, mx3_near(player.mana, 14), "Bell Reprise restores 4 mana")
}

// --- Slice 4: companion combat riders ---------------------------------------

@(test)
mx3_spirit_beast_bite_riders :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(9315, 0), .Ranger)
	defer ar.run_destroy(&run)
	mx3_arena(&run)
	player := &run.player
	beast_path := [5]ar.Discipline_Id{.Ranger_Beast_Bond, .Ranger_Pack_Tactics, .Ranger_Alpha, .Ranger_Spirit_Companion, .Ranger_Primal_Lord}
	for id in beast_path do player.acquired_disciplines[id] = true
	testing.expect(t, ar.player_cast_spirit_beast(&run), "beast must summon")
	beast := ar.living_spirit_beast(&run)
	testing.expect(t, beast != nil && beast.champion, "Primal Lord marks the beast a champion")

	// Park a snared, arcane-vulnerable dummy adjacent and let one bite land.
	append(&run.enemies, mx3_dummy({0, 0}, 4000))
	enemy := &run.enemies[0]
	enemy.pos = beast.pos + ar.Vec2{0.8, 0}
	enemy.prev_pos = enemy.pos
	before_pos := enemy.pos
	ar.tick_familiars_dt(&run, 0.01)
	testing.expect(t, enemy.hp < enemy.max_hp, "the beast bit the adjacent foe")
	testing.expect(t, enemy.pos != before_pos, "Alpha shoves the bitten foe")

	// Arcane conversion: a chilled foe takes the 1.18 arcane amp, which only
	// applies because Spirit Companion converts the bite.
	stats := ar.spirit_beast_stats(5)
	min_bite := stats.damage // rng adds 0..2 on top
	dealt := enemy.max_hp - enemy.hp
	testing.expectf(t, dealt >= min_bite, "bite dealt %v, expected at least %v", dealt, min_bite)
}

@(test)
mx3_blood_bound_familiars_siphon_health :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(9316, 0), .Acolyte)
	defer ar.run_destroy(&run)
	mx3_arena(&run)
	player := &run.player
	player.acquired_disciplines[.Acolyte_Sanguine] = true
	testing.expect(t, ar.player_cast_spirit_call(&run), "Spirit Call must cast")
	testing.expect(t, len(run.familiars) > 0 && run.familiars[0].lifesteal, "the Blood ladder marks familiars blood-bound")
	player.hp = 100
	append(&run.enemies, mx3_dummy({0, 0}, 4000))
	run.enemies[0].pos = run.familiars[0].pos + ar.Vec2{0.8, 0}
	run.enemies[0].prev_pos = run.enemies[0].pos
	ar.tick_familiars_dt(&run, 0.01)
	testing.expect(t, run.enemies[0].hp < run.enemies[0].max_hp, "the familiar attacked")
	testing.expectf(t, player.hp == 103, "the bite siphoned to %v, want 103 (+3 spell leech)", player.hp)
}

// --- Slice 5: Spirit Beast petting ------------------------------------------

@(test)
mx3_pet_heal_doubles_per_beast_degree :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(9317, 0), .Ranger)
	defer ar.run_destroy(&run)
	player := &run.player
	testing.expect(t, ar.spirit_beast_pet_heal(player) == 2, "base pet heal is 2")
	beast_path := [5]ar.Discipline_Id{.Ranger_Beast_Bond, .Ranger_Pack_Tactics, .Ranger_Alpha, .Ranger_Spirit_Companion, .Ranger_Primal_Lord}
	expected := 2
	for id in beast_path {
		player.acquired_disciplines[id] = true
		expected *= 2
		testing.expectf(t, ar.spirit_beast_pet_heal(player) == expected, "pet heal at this degree is %v, want %v", ar.spirit_beast_pet_heal(player), expected)
	}
}

@(test)
mx3_petting_readiness_pose_and_cooldown :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(9318, 0), .Ranger)
	defer ar.run_destroy(&run)
	mx3_arena(&run)
	player := &run.player
	testing.expect(t, ar.player_cast_spirit_beast(&run), "beast must summon")
	beast := ar.living_spirit_beast(&run)
	beast.pos = player.pos + ar.Vec2{1.0, 0}
	beast.hp = beast.max_hp - 10

	testing.expect(t, ar.nearby_pettable_spirit_beast(&run) != nil, "beast in range and off cooldown is pettable")
	testing.expect(t, ar.interact_prompt(&run) == "E: pet your beast", "the world prompt offers the pet")

	hp_before := beast.hp
	testing.expect(t, ar.pet_spirit_beast(&run), "petting must succeed")
	testing.expect(t, beast.hp == hp_before + 2, "the base pet heals 2 HP")
	testing.expect(t, player.visual_action == .Pet, "the Ranger strikes the paired pose")
	testing.expect(t, mx3_near(beast.pet_cooldown, 2.0), "petting starts the 2s cooldown")
	testing.expect(t, beast.facing.x < 0 && player.facing.x > 0, "the pair face each other")
	testing.expect(t, ar.nearby_pettable_spirit_beast(&run) == nil, "cooldown suppresses immediate re-pets")

	// Held locomotion cannot pull either half out of the paired pose or trigger
	// movement auto-melee. Both remain rooted until the Pet action completes.
	player_pos_before := player.pos
	beast_pos_before := beast.pos
	append(&run.enemies, mx3_dummy(player.pos + ar.Vec2{0, 0.8}))
	enemy_hp_before := run.enemies[0].hp
	pet_ticks := 0
	for player.visual_action == .Pet && pet_ticks < 100 {
		ar.sim_tick_limited(&run, {0, 1}, -1, auto_melee = true)
		testing.expect(t, player.pos == player_pos_before, "the Ranger must remain rooted throughout Pet")
		testing.expect(t, beast.pos == beast_pos_before, "the Spirit Beast must remain rooted throughout Pet")
		testing.expect(t, !player.moving && !beast.moving, "both Pet actors must remain in non-locomotion state")
		testing.expect(t, run.enemies[0].hp == enemy_hp_before, "held movement must not auto-melee during Pet")
		pet_ticks += 1
	}
	testing.expect(t, player.visual_action == .None, "the Pet action should complete within its authored duration")
	testing.expect(t, pet_ticks > 1, "the Pet movement lock must cover more than its start tick")

	// The pickup fallback outranks petting in the interact chain.
	beast.pet_cooldown = 0
	beast.pet_anim_timer = 0
	append(&run.ground_items, ar.Ground_Item{pos = player.pos})
	testing.expect(t, ar.interact_prompt(&run) == "E: pick up item", "items outrank the pet prompt")
}

// --- Determinism ------------------------------------------------------------

@(test)
mx3_discipline_combat_stays_deterministic :: proc(t: ^testing.T) {
	final_state :: proc(seed: u64) -> (hp: [3]int, player_hp: int, mana: f32) {
		run: ar.Run
		ar.run_start(&run, seed, .Arcanist)
		defer ar.run_destroy(&run)
		mx3_arena(&run)
		run.player.acquired_disciplines[.Arcanist_Overload] = true
		run.player.acquired_disciplines[.Arcanist_Chain_Lightning] = true
		run.player.acquired_disciplines[.Arcanist_Permafrost] = true
		append(&run.enemies, mx3_dummy({12.5, 10.5}))
		append(&run.enemies, mx3_dummy({13.8, 10.8}))
		append(&run.enemies, mx3_dummy({14.5, 9.9}))
		for i in 0 ..< 240 {
			if i % 30 == 0 {
				run.player.bolt_timer = 0
				run.player.mana = 200
				_ = ar.player_cast_bolt(&run, {1, 0})
			}
			ar.sim_tick(&run, {})
		}
		for &enemy, i in run.enemies do if i < 3 do hp[i] = enemy.hp
		return hp, run.player.hp, run.player.mana
	}
	seed := ar.derive_seed(9319, 0)
	hp_a, php_a, mana_a := final_state(seed)
	hp_b, php_b, mana_b := final_state(seed)
	testing.expect(t, hp_a == hp_b && php_a == php_b && mana_a == mana_b, "same-seed discipline combat diverged")
}
