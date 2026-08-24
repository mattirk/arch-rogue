package archrogue_tests

// MX.5 — interactables, secrets, uniques, and reward payoff.

import "core:testing"
import ar "../src"

@(private = "file")
mx5_run :: proc(seed: u64, archetype: ar.Archetype_Id) -> ar.Run {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(seed, 0), archetype)
	return run
}

@(test)
all_thirteen_uniques_construct_faithfully :: proc(t: ^testing.T) {
	weapons, armors := 0, 0
	for &def in ar.UNIQUE_DEFS {
		rng := ar.rng_make(ar.derive_seed(77, 0), 3)
		item := ar.make_unique_from_def(&rng, &def)
		testing.expectf(t, item.rarity == .Unique, "%v must be Unique", def.name)
		testing.expectf(t, item.name == def.name && item.icon == def.icon, "%v identity fields", def.name)
		testing.expectf(t, item.affix_count == 3, "%v carries three display affixes", def.name)
		testing.expectf(t, item.unique_effect == def.effect, "%v carries its hook", def.name)
		testing.expect(t, item.power == def.power && item.defense == def.defense, "authored stats survive (no rolled-gear clamp)")
		if def.has_skill_bonus {
			testing.expectf(t, item.skill_bonuses[def.skill_bonus], "%v skill bonus set", def.name)
		}
		if def.slot == .Weapon do weapons += 1
		if def.slot == .Armor do armors += 1
	}
	testing.expect(t, weapons == 7 && armors == 6, "seven weapons and six armors")

	// Floors 1-3 draw from the weapon pool only (UNIQUE_ARMOR_MIN_DEPTH).
	rng := ar.rng_make(ar.derive_seed(5, 0), 7)
	for _ in 0 ..< 40 {
		item := ar.make_unique(&rng, .Warden, 1)
		testing.expect(t, item.kind == .Weapon, "no unique armor above depth 4")
	}
	// The 72% archetype bias favors the class anchor when one exists.
	matches := 0
	for _ in 0 ..< 60 {
		if ar.make_unique(&rng, .Arcanist, 1).name == "Splinter Star" do matches += 1
	}
	testing.expectf(t, matches > 30, "archetype bias should dominate (got %v/60)", matches)
}

@(test)
unique_stat_hooks_apply :: proc(t: ^testing.T) {
	run := mx5_run(41, .Warden)
	defer ar.run_destroy(&run)
	player := &run.player

	// Unarmed/unarmored baselines so the starter gear doesn't skew the math.
	player.has_weapon = false
	player.has_armor = false
	base_melee := ar.player_melee_damage(player)
	base_armor := ar.player_armor(player)
	base_resist := ar.player_typed_resistance(player, .Arcane)

	ember_rng := ar.rng_make(1, 1)
	player.weapon = ar.make_unique_from_def(&ember_rng, &ar.UNIQUE_DEFS[0]) // Emberbrand
	player.has_weapon = true
	testing.expect(t, ar.player_melee_damage(player) == base_melee + 4 + 36, "embers on hit adds +4 over the authored 36 power")

	player.armor = ar.make_unique_from_def(&ember_rng, &ar.UNIQUE_DEFS[3]) // Oathwall Carapace
	player.has_armor = true
	testing.expect(t, ar.player_armor(player) == base_armor + 27 + 3, "oathwall aegis adds +3 armor")
	testing.expect(t, ar.player_typed_resistance(player, .Arcane) > base_resist, "oathwall aegis wards every channel")

	player.armor = ar.make_unique_from_def(&ember_rng, &ar.UNIQUE_DEFS[8]) // Blizzard Mantle
	frost := ar.player_typed_resistance(player, .Frost)
	arcane := ar.player_typed_resistance(player, .Arcane)
	testing.expect(t, frost > arcane, "glacial ward adds frost-specific resistance")

	player.weapon = ar.make_unique_from_def(&ember_rng, &ar.UNIQUE_DEFS[9]) // Blood Psalm
	testing.expect(t, ar.player_lifesteal(player) >= 0.14 + 0.06, "sanguine echo deepens lifesteal")

	player.armor = ar.make_unique_from_def(&ember_rng, &ar.UNIQUE_DEFS[10]) // Choir of Bone
	testing.expect(t, ar.player_thorns(player) >= 4 + 2, "grave chorus barbs the thorns total")
}

@(test)
unique_combat_hooks_fire :: proc(t: ^testing.T) {
	run := mx5_run(43, .Rogue)
	defer ar.run_destroy(&run)
	player := &run.player
	rng := ar.rng_make(9, 2)

	// Emberbrand guarantees the ignite rider on non-fire hits.
	player.weapon = ar.make_unique_from_def(&rng, &ar.UNIQUE_DEFS[0])
	player.weapon.unidentified = false
	player.has_weapon = true
	clear(&run.enemies)
	victim := ar.enemy_make(.Ghoul, player.pos + {2, 0}, 1)
	victim.resistances = {}
	ar.enemy_ensure_id(&run, &victim)
	append(&run.enemies, victim)
	_ = ar.player_damage_enemy(&run, &run.enemies[0], 10, .Physical)
	testing.expect(t, run.enemies[0].statuses[.Burning] > 0, "embers on hit must ignite")

	// Foxstep Leathers vanish on dash.
	player.armor = ar.make_unique_from_def(&rng, &ar.UNIQUE_DEFS[6])
	player.has_armor = true
	player.statuses[.Smoke] = 0
	player.stamina = f32(player.max_stamina)
	player.dash_timer = 0
	testing.expect(t, ar.player_dash(&run, {1, 0}), "dash must fire")
	testing.expect(t, player.statuses[.Smoke] > 0, "vanish on dash grants Smoke")

	// Nightglass smoke crits: eligible rolls eventually land at x1.80.
	player.weapon = ar.make_unique_from_def(&rng, &ar.UNIQUE_DEFS[5])
	player.statuses[.Smoke] = 5
	landed := false
	for _ in 0 ..< 64 {
		critical, multiplier := ar.maybe_smoke_crit(&run, false, 1)
		if critical {
			landed = true
			testing.expect(t, multiplier == 1.80, "smoke crit multiplier is 1.80")
			break
		}
	}
	testing.expect(t, landed, "smoke crit must land within 64 eligible swings")
	player.statuses[.Smoke] = 0
	critical, _ := ar.maybe_smoke_crit(&run, false, 1)
	testing.expect(t, !critical, "no smoke, no smoke crit")

	// Glacial ward / pack pursuit punish melee attackers.
	player.armor = ar.make_unique_from_def(&rng, &ar.UNIQUE_DEFS[8]) // Blizzard Mantle
	attacker := &run.enemies[0]
	attacker.hp = attacker.max_hp
	_ = ar.damage_player_typed(&run, 10, .Physical, melee = true, attacker = attacker, evadable = false)
	testing.expect(t, attacker.statuses[.Chilled] > 0, "glacial ward chills melee attackers")
	player.armor = ar.make_unique_from_def(&rng, &ar.UNIQUE_DEFS[12]) // Beastlord Harness
	_ = ar.damage_player_typed(&run, 10, .Physical, melee = true, attacker = attacker, evadable = false)
	testing.expect(t, attacker.statuses[.Snared] > 0, "pack pursuit snares melee attackers")
}

@(test)
unique_fan_and_class_skill_hooks :: proc(t: ^testing.T) {
	run := mx5_run(47, .Arcanist)
	defer ar.run_destroy(&run)
	player := &run.player
	rng := ar.rng_make(3, 4)

	// Splinter Star: Bolt_Shard pair (±0.18) + splinter storm pair (±0.10).
	player.weapon = ar.make_unique_from_def(&rng, &ar.UNIQUE_DEFS[7])
	player.weapon.unidentified = false
	player.has_weapon = true
	clear(&run.projectiles)
	player.mana = f32(player.max_mana)
	player.bolt_timer = 0
	testing.expect(t, ar.player_cast_bolt(&run, {1, 0}), "bolt must cast")
	testing.expectf(t, len(run.projectiles) == 5, "splinter storm fan should fill five slots (got %v)", len(run.projectiles))

	// Blizzard Mantle: both Nova queries fire (+0.25 +0.35).
	base := ar.nova_radius(player)
	player.armor = ar.make_unique_from_def(&rng, &ar.UNIQUE_DEFS[8])
	player.has_armor = true
	widened := ar.nova_radius(player)
	testing.expectf(t, abs(widened - base - 0.60) < 1e-4, "Nova radius bonus totals +0.60 (got %v)", widened - base)
	testing.expect(t, ar.player_class_skill_mana_cost(player) < 14, "class-skill gear bonus trims the cost")

	// Bulwark of the First Gate: Dash guard cost break + Warden Aegis rider.
	warden := mx5_run(48, .Warden)
	defer ar.run_destroy(&warden)
	base_cost := ar.player_dash_stamina_cost(&warden.player)
	warden.player.armor = ar.make_unique_from_def(&rng, &ar.UNIQUE_DEFS[2])
	warden.player.armor.unidentified = false
	warden.player.has_armor = true
	testing.expect(t, ar.player_dash_stamina_cost(&warden.player) == base_cost - 2, "Dash guard trims dash stamina")
	warden.player.stamina = f32(warden.player.max_stamina)
	warden.player.dash_timer = 0
	testing.expect(t, ar.player_dash(&warden, {1, 0}), "warden dash must fire")
	testing.expect(t, warden.player.statuses[.Aegis] > 0, "Dash guard hardens the Warden's dash")

	// Beastlord Harness feeds the spirit-beast equipment bond.
	bonded := ar.spirit_beast_stats(0, true)
	plain := ar.spirit_beast_stats(0, false)
	testing.expect(t, bonded.hp == plain.hp + 12 && bonded.damage == plain.damage + 2, "bond adds +12 hp / +2 damage")
}

@(test)
traps_reveal_trigger_and_count :: proc(t: ^testing.T) {
	run := mx5_run(51, .Warden)
	defer ar.run_destroy(&run)
	clear(&run.traps)
	clear(&run.enemies)
	spot := run.player.pos + {3, 0}
	append(&run.traps, ar.Trap{pos = spot, kind = .Spike, damage = 12, active = true})

	ar.tick_traps(&run, ar.SIM_DT)
	testing.expect(t, !run.traps[0].revealed, "distant traps stay hidden")

	run.player.pos = spot + {1.2, 0}
	ar.tick_traps(&run, ar.SIM_DT)
	testing.expect(t, run.traps[0].revealed, "closing within 1.35 reveals the plate")
	testing.expect(t, run.traps[0].reveal_progress > 0 && run.traps[0].reveal_progress < 1, "materialize fade ramps")
	for _ in 0 ..< 12 do ar.tick_traps(&run, ar.SIM_DT)
	testing.expect(t, run.traps[0].reveal_progress == 1, "fade completes in about a sixth of a second")

	hp_before := run.player.hp
	run.player.pos = spot + {0.3, 0}
	ar.tick_traps(&run, ar.SIM_DT)
	testing.expect(t, !run.traps[0].active, "stepping on the plate spends it")
	testing.expect(t, run.player.hp < hp_before, "the trap must wound")
	testing.expect(t, run.traps_triggered == 1, "the run ledger counts the trigger")
	has_cue := false
	for cue in run.sfx do if cue.bank == .Trap_Spike {
		has_cue = cue.spatial && cue.pos == spot
	}
	testing.expect(t, has_cue, "triggering emits spatial Trap_Spike at the trap")

	hp_mid := run.player.hp
	ar.tick_traps(&run, ar.SIM_DT)
	testing.expect(t, run.player.hp == hp_mid, "a spent trap never fires again")
}

@(test)
shrines_grant_their_bargains :: proc(t: ^testing.T) {
	run := mx5_run(53, .Warden)
	defer ar.run_destroy(&run)
	player := &run.player
	clear(&run.shrines)
	clear(&run.ground_items)

	// Mending restores both pools. Prompt punctuation must stay inside the
	// default raylib font's glyph range rather than rendering as a question mark.
	player.hp = 1
	player.mana = 0
	append(&run.shrines, ar.Shrine{pos = player.pos, kind = .Mending})
	testing.expect(t, ar.interact_prompt(&run) == "E: Mending Shrine - Restores health and mana.", "Mending prompt uses an ASCII-safe separator")
	shrine := &run.shrines[0]
	ar.activate_shrine(&run, shrine)
	testing.expect(t, player.hp == player.max_hp && player.mana == f32(player.max_mana), "Mending restores fully")
	testing.expect(t, shrine.used, "shrines are one-use")
	before := player.hp
	ar.activate_shrine(&run, shrine)
	testing.expect(t, player.hp == before && run.shrines_used == 1, "a used shrine is inert")

	// Insight reveals the bag.
	player.bag[0] = ar.Item{kind = .Weapon, name = "Test Blade", rarity = .Rare, unidentified = true}
	player.bag_count = 1
	insight := ar.Shrine{pos = player.pos, kind = .Insight}
	ar.activate_shrine(&run, &insight)
	testing.expect(t, !player.bag[0].unidentified, "Insight identifies carried gear")

	// War grants xp and focus.
	xp := player.xp
	player.stamina = 0
	war := ar.Shrine{pos = player.pos, kind = .War}
	ar.activate_shrine(&run, &war)
	testing.expect(t, player.xp == xp + 25 || player.level > 1, "War grants 25 xp")
	testing.expect(t, player.stamina == f32(player.max_stamina), "War refills stamina")

	// Haste: capped permanent stride blessing through the real channel.
	speed_before := ar.player_speed(player)
	for _ in 0 ..< 4 {
		haste := ar.Shrine{pos = player.pos, kind = .Haste}
		ar.activate_shrine(&run, &haste)
	}
	testing.expect(t, player.shrine_move_bonus == 0.09, "stride blessing caps at 0.09")
	testing.expect(t, ar.player_speed(player) > speed_before, "the blessing reaches locomotion")

	// Fortune spills two offerings.
	drops := len(run.ground_items)
	fortune := ar.Shrine{pos = player.pos, kind = .Fortune}
	ar.activate_shrine(&run, &fortune)
	testing.expect(t, len(run.ground_items) == drops + 2, "Fortune spills two drops")

	// Oath grants a free technique without touching the token purse.
	tokens := player.memory_tokens
	acquired_before := 0
	for id in ar.Discipline_Id do if player.acquired_disciplines[id] do acquired_before += 1
	oath := ar.Shrine{pos = player.pos, kind = .Oath}
	ar.activate_shrine(&run, &oath)
	acquired_after := 0
	for id in ar.Discipline_Id do if player.acquired_disciplines[id] do acquired_after += 1
	testing.expect(t, acquired_after == acquired_before + 1, "Oath grants one discipline")
	testing.expect(t, player.memory_tokens == tokens, "the Oath grant is token-free")

	// Twilight trades blood for a unique relic.
	player.hp = player.max_hp
	drops = len(run.ground_items)
	twilight := ar.Shrine{pos = player.pos, kind = .Twilight}
	ar.activate_shrine(&run, &twilight)
	testing.expect(t, player.hp < player.max_hp, "Twilight takes blood")
	testing.expect(t, len(run.ground_items) == drops + 1, "Twilight drops the relic")
	testing.expect(t, run.ground_items[len(run.ground_items)-1].item.rarity == .Unique, "the relic is a named Unique")
}

@(test)
secrets_reveal_and_resolve :: proc(t: ^testing.T) {
	run := mx5_run(59, .Ranger)
	defer ar.run_destroy(&run)
	player := &run.player
	clear(&run.secrets)
	clear(&run.ground_items)
	clear(&run.enemies)

	spot := player.pos + {4, 0}
	append(&run.secrets, ar.Secret{pos = spot, kind = .Sealed_Armory})
	ar.tick_secrets(&run)
	testing.expect(t, !run.secrets[0].revealed, "distant secrets stay hidden")
	player.pos = spot + {1.2, 0}
	ar.tick_secrets(&run)
	testing.expect(t, run.secrets[0].revealed, "closing within 1.55 reveals the cache")

	ar.open_secret(&run, &run.secrets[0])
	testing.expect(t, run.secrets[0].opened && run.secrets_opened == 1, "opening marks and counts")
	testing.expect(t, len(run.ground_items) == 2, "the armory drops two pieces")
	for g in run.ground_items {
		testing.expect(t, g.item.kind == .Weapon || g.item.kind == .Armor, "armory drops are equipment")
	}

	// Moonlit Bargain: blood for a guaranteed Rare.
	clear(&run.ground_items)
	player.hp = player.max_hp
	moonlit := ar.Secret{pos = player.pos, kind = .Moonlit_Bargain, revealed = true}
	ar.open_secret(&run, &moonlit)
	testing.expect(t, player.hp < player.max_hp, "the bargain takes blood")
	testing.expect(t, len(run.ground_items) == 1, "the bargain pays one piece")
	testing.expect(t, run.ground_items[0].item.rarity == .Rare || run.ground_items[0].item.rarity == .Cursed, "the payment is Rare-class")

	// Cursed Reliquary: across seeds both the guardian and the loot branch
	// must be reachable.
	woke, paid := false, false
	for seed_i in 1 ..= 30 {
		trial := mx5_run(u64(600 + seed_i), .Ranger)
		defer ar.run_destroy(&trial)
		clear(&trial.enemies)
		clear(&trial.ground_items)
		reliquary := ar.Secret{pos = trial.player.pos + {2, 0}, kind = .Cursed_Reliquary, revealed = true}
		ar.open_secret(&trial, &reliquary)
		if len(trial.enemies) > 0 {
			woke = true
			testing.expect(t, trial.enemies[0].role == .Miniboss, "the woken guardian is an Oathbound")
		} else {
			paid = true
			testing.expect(t, len(trial.ground_items) == 1, "the failed wake still pays")
		}
		if woke && paid do break
	}
	testing.expect(t, woke && paid, "both reliquary branches must occur across seeds")

	// The stash pays double like the armory's count.
	clear(&run.ground_items)
	stash := ar.Secret{pos = player.pos, kind = .Cartographer_Stash, revealed = true}
	ar.open_secret(&run, &stash)
	testing.expect(t, len(run.ground_items) == 2, "the stash drops two finds")
}

@(test)
interactable_placement_is_deterministic_and_pressured :: proc(t: ^testing.T) {
	a := mx5_run(61, .Warden)
	b := mx5_run(61, .Warden)
	defer ar.run_destroy(&a)
	defer ar.run_destroy(&b)
	for a.depth < 6 {
		testing.expect(t, len(a.traps) == len(b.traps), "trap layouts must be seed-stable")
		testing.expect(t, len(a.shrines) == len(b.shrines), "shrine layouts must be seed-stable")
		testing.expect(t, len(a.secrets) == len(b.secrets), "secret layouts must be seed-stable")
		for trap, i in a.traps do testing.expect(t, trap == b.traps[i], "trap fields must match")
		for shrine, i in a.shrines do testing.expect(t, shrine == b.shrines[i], "shrine fields must match")
		for secret, i in a.secrets do testing.expect(t, secret == b.secrets[i], "secret fields must match")
		ar.run_descend(&a)
		ar.run_descend(&b)
	}

	// Any full descent must actually meet the systems the plan advertises.
	total_traps, total_shrines, total_secrets := 0, 0, 0
	for seed_i in 1 ..= 6 {
		run := mx5_run(u64(700 + seed_i), .Warden)
		defer ar.run_destroy(&run)
		for {
			total_traps += len(run.traps)
			total_shrines += len(run.shrines)
			total_secrets += len(run.secrets)
			if run.depth >= ar.DUNGEON_DEPTH do break
			ar.run_descend(&run)
		}
	}
	testing.expect(t, total_traps > 0 && total_shrines > 0 && total_secrets > 0, "floors must carry live interactables")
}

@(test)
shrines_and_caches_are_solid_room_furniture :: proc(t: ^testing.T) {
	checked_shrine, checked_secret := false, false
	for seed_i in 1 ..= 40 {
		run := mx5_run(u64(900 + seed_i), .Warden)
		defer ar.run_destroy(&run)
		for {
			for &shrine in run.shrines {
				checked_shrine = true
				tile := [2]int{int(shrine.pos.x), int(shrine.pos.y)}
				testing.expect(t, ar.blocked_for_radius(&run.dungeon, shrine.pos.x, shrine.pos.y),
					"a shrine tile must block movement")
				testing.expect(t, tile != run.dungeon.stairs, "a shrine must never seal the stairs")
				if _, index, in_room := ar.dungeon_room_at_point(&run.dungeon, shrine.pos.x, shrine.pos.y); in_room {
					room := ar.dungeon_rooms(&run.dungeon)[index]
					testing.expect(t, !ar.tile_is_door_front(&run.dungeon, room, tile),
						"a shrine must never seal a doorway")
				}
				for &enemy in run.enemies {
					testing.expect(t, int(enemy.pos.x) != tile.x || int(enemy.pos.y) != tile.y,
						"enemies must not spawn inside shrine furniture")
				}
				for &ground in run.ground_items {
					testing.expect(t, int(ground.pos.x) != tile.x || int(ground.pos.y) != tile.y,
						"loot must not spawn inside shrine furniture")
				}
			}
			for &secret in run.secrets {
				checked_secret = true
				testing.expect(t, ar.blocked_for_radius(&run.dungeon, secret.pos.x, secret.pos.y),
					"a sealed cache must block movement")
				testing.expect(t, [2]int{int(secret.pos.x), int(secret.pos.y)} != run.dungeon.stairs,
					"a cache must never seal the stairs")
			}
			// Furniture never stacks: one prop per tile.
			for &a, i in run.shrines {
				for &b, j in run.shrines {
					if i >= j do continue
					testing.expect(t, int(a.pos.x) != int(b.pos.x) || int(a.pos.y) != int(b.pos.y),
						"two shrines must not share a tile")
				}
				for &s in run.secrets {
					testing.expect(t, int(a.pos.x) != int(s.pos.x) || int(a.pos.y) != int(s.pos.y),
						"a shrine and a cache must not share a tile")
				}
			}
			if run.depth >= ar.DUNGEON_DEPTH do break
			ar.run_descend(&run)
		}
	}
	testing.expect(t, checked_shrine && checked_secret, "sample must cover both furniture kinds")

	// A used shrine keeps its tile; an opened cache gives its tile back.
	run := mx5_run(53, .Warden)
	defer ar.run_destroy(&run)
	clear(&run.shrines)
	clear(&run.secrets)
	spot := run.player.pos + {2, 0}
	tile := [2]int{int(spot.x), int(spot.y)}
	ar.solid_prop_add(&run.dungeon, tile)
	append(&run.shrines, ar.Shrine{pos = spot, kind = .Mending})
	ar.activate_shrine(&run, &run.shrines[0])
	testing.expect(t, ar.blocked_for_radius(&run.dungeon, spot.x, spot.y), "a spent shrine is still furniture")

	cache_spot := run.player.pos + {0, 2}
	ar.solid_prop_add(&run.dungeon, {int(cache_spot.x), int(cache_spot.y)})
	append(&run.secrets, ar.Secret{pos = cache_spot, kind = .Hidden_Cache, revealed = true})
	testing.expect(t, ar.blocked_for_radius(&run.dungeon, cache_spot.x, cache_spot.y), "a sealed cache blocks")
	ar.open_secret(&run, &run.secrets[0])
	testing.expect(t, !ar.solid_prop_occupies_tile(&run.dungeon, int(cache_spot.x), int(cache_spot.y)),
		"an opened cache stops being furniture")
}

@(test)
kill_rewards_honor_the_contract :: proc(t: ^testing.T) {
	// A floor guardian (depth 3, role Boss, not final) guarantees Rare-class
	// equipment plus its gold; the ordinary roll stays independent.
	run := mx5_run(67, .Warden)
	defer ar.run_destroy(&run)
	for run.depth < 3 do ar.run_descend(&run)
	guardian_found := false
	for &enemy in run.enemies {
		if enemy.role == .Boss {
			guardian_found = true
			enemy.hp = 0
		}
	}
	testing.expect(t, guardian_found, "depth 3 must carry its guardian")
	clear(&run.ground_items)
	ar.sim_tick(&run, {})
	reward_found := false
	for g in run.ground_items {
		if (g.item.kind == .Weapon || g.item.kind == .Armor) &&
			(g.item.rarity == .Rare || g.item.rarity == .Cursed) {
			reward_found = true
		}
	}
	testing.expect(t, reward_found, "guardian kills must pay Rare-class equipment")
	testing.expect(t, run.notable_count > 0, "the reward lands in the notable ledger")

	// The Tyrant guarantees a named Unique.
	tyrant_run := mx5_run(71, .Ranger)
	defer ar.run_destroy(&tyrant_run)
	for tyrant_run.depth < ar.DUNGEON_DEPTH do ar.run_descend(&tyrant_run)
	for &enemy in tyrant_run.enemies {
		if enemy.role == .Boss && enemy.final_boss do enemy.hp = 0
	}
	clear(&tyrant_run.ground_items)
	ar.sim_tick(&tyrant_run, {})
	unique_found := false
	for g in tyrant_run.ground_items {
		if g.item.rarity == .Unique do unique_found = true
	}
	testing.expect(t, unique_found, "the Tyrant must drop a named Unique")

	// Notable ledger dedupes and caps at eight.
	ledger := mx5_run(73, .Warden)
	defer ar.run_destroy(&ledger)
	sample := ar.Item{kind = .Weapon, name = "Test Relic", rarity = .Rare}
	ar.record_notable_loot(&ledger, sample)
	ar.record_notable_loot(&ledger, sample)
	testing.expect(t, ledger.notable_count == 1, "duplicate finds record once")
	ar.record_notable_loot(&ledger, ar.Item{kind = .Weapon, name = "Common Stick", rarity = .Common})
	testing.expect(t, ledger.notable_count == 1, "commons never reach the ledger")
}

@(test)
wall_face_touch_animates_the_worn_wall :: proc(t: ^testing.T) {
	run := mx5_run(79, .Warden)
	defer ar.run_destroy(&run)

	// The variant hash is pure: hunt any face-bearing wall on the floor.
	found_tile: [2]int
	found := false
	search: for x in 0 ..< ar.MAP_W {
		for y in 0 ..< ar.MAP_H {
			if run.dungeon.tiles[x][y] != .Wall do continue
			if !ar.wall_face_tile(x, y) do continue
			// Needs adjacent walkable floor to stand on.
			for delta in ([4][2]int{{1, 0}, {-1, 0}, {0, 1}, {0, -1}}) {
				nx, ny := x + delta.x, y + delta.y
				if ar.dungeon_in_bounds(nx, ny) && run.dungeon.tiles[nx][ny] == .Floor {
					run.player.pos = {f32(nx) + 0.5, f32(ny) + 0.5}
					if ar.interact_prompt(&run)!="" do continue
					found_tile = {x, y}
					found = true
					break search
				}
			}
		}
	}
	if !found do return // pathological floor without a reachable face tile
	_ = found_tile
	testing.expect(t,!ar.player_interaction_advertised(&run),"worn wall must remain absent from the HUD prompt")
	testing.expect(t,ar.player_interaction_available(&run),"mobile A must preserve the hidden wall interaction path")
	testing.expect(t, ar.touch_secret_face_wall(&run), "touching the worn wall must trigger")
	// The touch binds to the *nearest* face wall, which may differ from the
	// tile the search found when two face tiles flank the same floor tile.
	testing.expect(t, ar.wall_face_tile(run.wall_face_tile.x, run.wall_face_tile.y), "the animation binds to a face-bearing wall")
	testing.expect(t, run.wall_face_timer > 0, "the transient clip clock runs")
	testing.expect(t, run.wall_touches == 1, "the touch ledger counts")
}
