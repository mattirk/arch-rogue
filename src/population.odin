package archrogue

import "core:math"

@(rodata)
SORN_TYRANT_TITLES := [8]string{
	"Sorn Voss, Ashen Gate Tyrant",
	"Sorn Voss, Mycelial Gate Tyrant",
	"Sorn Voss, Voidbound Gate Tyrant",
	"Sorn Voss, Drowned Gate Tyrant",
	"Sorn Voss, Rimebound Gate Tyrant",
	"Sorn Voss, Forgeheart Gate Tyrant",
	"Sorn Voss, Moon-Drowned Gate Tyrant",
	"Sorn Voss, Thorn-Crowned Gate Tyrant",
}

// Shared with the MX.5 interactable placement in interactables.odin.
population_room_point :: proc(d: ^Dungeon, room: Room, rng: ^Pcg32) -> Vec2 {
	point := room_random_point(room,rng)
	if !special_room_placement_reserved_occupies_tile(d,int(point.x),int(point.y)) do return point
	for y in room.y+1 ..< room.y+room.h-1 {
		for x in room.x+1 ..< room.x+room.w-1 {
			if !special_room_placement_reserved_occupies_tile(d,x,y) do return {f32(x)+.5,f32(y)+.5}
		}
	}
	return point
}

// Floor population, ported from population.py: every room except the spawn
// room rolls 1-3 enemies with depth adjustments, the stairs room gets one
// extra, and the MX.4 floor plan's encounter template and run modifier press
// on counts, elite/miniboss odds, stats, and loot before difficulty scaling.

populate_floor :: proc(run: ^Run) {
	// Separate streams from the layout RNG so future population changes never
	// reshuffle dungeon geometry for a given seed. The loot stream persists in
	// the run because kill drops keep consuming it after spawn.
	rng := rng_make(derive_seed(run.seed, u64(run.depth)), stream = 1)
	run.loot_rng = rng_make(derive_seed(run.seed, u64(run.depth)), stream = 2)
	run.combat_rng = rng_make(derive_seed(run.seed, u64(run.depth)), stream = 5)

	plan := run_floor_plan(run)
	encounter := ENCOUNTER_TEMPLATES[plan.encounter]
	mod := RUN_MODIFIERS[run.modifier]

	clear(&run.enemies)
	clear(&run.projectiles)
	clear(&run.familiars)
	clear(&run.bells)
	clear(&run.numbers)
	clear(&run.ground_items)
	clear(&run.traps)
	clear(&run.shrines)
	clear(&run.secrets)

	// Interactables settle first (on their own stream, so pre-MX.5 enemy
	// layouts are untouched): shrines and caches reserve their tiles as room
	// furniture, and the actor/loot placement below then routes around them.
	populate_interactables(run)

	rooms := dungeon_rooms(&run.dungeon)
	for room, room_index in rooms {
		if room_index == 0 do continue // spawn room stays safe
		final_room := room_index == len(rooms) - 1
		safe_room := special_room_is_safe(special_room_kind_for_room(&run.dungeon, room_index))
		count := rng_range(&rng, 1, 4)
		if run.depth <= 2 {
			count = max(1, count - 1)
		} else if run.depth >= 8 {
			count += 2
		} else if run.depth >= 6 {
			count += 1
		}
		enemy_pressure := story_effect_clamped(run, .Enemy_Pressure, -.35, .45)
		if enemy_pressure > 0 && rng_chance(&rng, enemy_pressure) {
			count += 1
		} else if enemy_pressure < 0 && rng_chance(&rng, abs(enemy_pressure)) {
			count = max(1, count - 1)
		}
		if final_room do count += 1
		count = max(1, count + encounter.enemy_bonus)
		count = difficulty_enemy_count(count, run.difficulty, rng_f32(&rng))

		for _ in 0 ..< count {
			kind := pick_enemy_kind(&rng, final_room)
			pos := population_room_point(&run.dungeon,room,&rng)
			enemy := enemy_make(kind, pos, run.depth)
			apply_run_modifier_stats(&enemy, &mod)
			apply_story_enemy_stats(run, &enemy)
			apply_enemy_difficulty(&enemy, run.difficulty)
			if rng_chance(&rng, difficulty_elite_chance(elite_chance(run.depth, encounter.elite_bonus + mod.elite_chance_bonus), run.difficulty)) {
				apply_elite(&enemy, rng_below(&rng, len(ELITE_MODIFIERS)))
			}
			// Shop rooms are safe, but consume the same actor rolls so later rooms
			// stay deterministic when the presentation/content inside shops grows.
			if !safe_room {
				enemy_ensure_id(run, &enemy)
				append(&run.enemies, enemy)
			}
		}

		// Oathbound minibosses prowl deeper side rooms (population.py).
		if room_index > 3 && !final_room && rng_chance(&rng, difficulty_miniboss_chance(miniboss_chance(run.depth, mod.miniboss_chance_bonus), run.difficulty)) {
			miniboss := enemy_make(pick_enemy_kind(&rng, false), population_room_point(&run.dungeon,room,&rng), run.depth)
			apply_run_modifier_stats(&miniboss, &mod)
			apply_story_enemy_stats(run, &miniboss)
			apply_enemy_difficulty(&miniboss, run.difficulty)
			promote_miniboss(&miniboss, THEMES[run.theme_index].accent)
			if !safe_room {
				enemy_ensure_id(run, &miniboss)
				append(&run.enemies, miniboss)
			}
		}

		// Exploration loot on the floor itself. Modifier and encounter pressure
		// join inside the pygame clamp, before the 0.33 room multiplier
		// (population.py:135-153 order).
		loot_bonus := story_effect_clamped(run, .Loot_Bonus, -.2, .35)
		loot_base := 0.68 + mod.loot_bonus + encounter.loot_bonus + loot_bonus
		loot_chance := difficulty_loot_chance(loot_base, run.difficulty) * ROOM_LOOT_CHANCE
		if rng_chance(&rng, loot_chance) {
			append(&run.ground_items, make_loot(&rng, population_room_point(&run.dungeon,room,&rng), mod.curse_chance_bonus, run))
		}
	}

	// challenge_room guarantees one challenge-role Oathbound in a random
	// non-boss-floor room and tracks its clear (population.py:232-245).
	// Guardian floors (3/6/9/10) suppress it, so it only fires on ordinary
	// depths that drew the template.
	if encounter.guaranteed_miniboss && !plan.has_boss && len(rooms) > 3 {
		spawn_challenge_boss(run, &rng, &mod)
	}

	if plan.has_boss {
		spawn_floor_boss(run, &mod)
	}
	spawn_story_pressure_hunters(run, &rng, &mod)
}

// MX.4 run-modifier stat pass: applied right after enemy_make's depth scaling
// and before difficulty, mirroring _apply_run_modifier's multiplication order
// (base × modifier × depth × difficulty).
apply_run_modifier_stats :: proc(enemy: ^Enemy, mod: ^Run_Modifier) {
	if enemy == nil do return
	enemy.max_hp = max(1, int(f32(enemy.max_hp) * mod.enemy_hp_mult))
	enemy.hp = enemy.max_hp
	enemy.damage = max(1, enemy.damage + mod.enemy_damage_bonus)
	enemy.aggro_range = max(0, enemy.aggro_range + mod.enemy_aggro_bonus)
}

apply_story_enemy_stats :: proc(run: ^Run, enemy: ^Enemy) {
	if run == nil || enemy == nil || enemy.story_scaled do return
	pressure := story_effect_clamped(run, .Enemy_Pressure, -.25, .35)
	boss_pressure: f32
	if enemy.role == .Boss do boss_pressure = story_effect_clamped(run, .Boss_Pressure, 0, .35)
	hp_multiplier := 1 + clamp(pressure * .55, f32(-.12), f32(.22)) + boss_pressure
	old_max_hp := max(1, enemy.max_hp)
	old_hp := enemy.hp
	enemy.max_hp = max(1, int(f32(old_max_hp) * hp_multiplier))
	if old_hp > 0 {
		enemy.hp = old_hp == old_max_hp ? enemy.max_hp : max(1, int(f32(old_hp) * f32(enemy.max_hp) / f32(old_max_hp)))
	} else {
		enemy.hp = old_hp
	}
	damage_bonus := 0
	if pressure > 0 do damage_bonus += int(pressure * 8)
	if enemy.role == .Boss do damage_bonus += int(boss_pressure * 10)
	if enemy.difficulty_scaled && damage_bonus > 0 {
		damage_bonus = int(math.round(f32(damage_bonus) * difficulty_profile(run.difficulty).enemy_damage_multiplier))
	}
	enemy.damage = max(1, enemy.damage + damage_bonus)
	enemy.aggro_range = max(0, enemy.aggro_range + max(f32(0), pressure))
	enemy.story_scaled = true
}

@(private = "file")
spawn_story_pressure_hunters :: proc(run: ^Run, rng: ^Pcg32, mod: ^Run_Modifier) {
	pressure := story_effect_clamped(run, .Hunter_Pressure, 0, .35)
	rooms := dungeon_rooms(&run.dungeon)
	if pressure <= 0 || len(rooms) <= 2 do return
	candidate_count := len(rooms) > 3 ? len(rooms) - 3 : len(rooms) - 1
	candidate_start := len(rooms) > 3 ? 2 : 1
	count := min(4, 1 + int(pressure / .14))
	if rng_chance(rng, min(f32(.75), pressure * 1.5)) do count += 1
	for _ in 0 ..< count {
		room_index := candidate_start + rng_below(rng, candidate_count)
		room := rooms[room_index]
		hunter := enemy_make(pick_enemy_kind(rng, true), population_room_point(&run.dungeon, room, rng), run.depth)
		apply_run_modifier_stats(&hunter, mod)
		apply_story_enemy_stats(run, &hunter)
		apply_enemy_difficulty(&hunter, run.difficulty)
		if rng_chance(rng, difficulty_elite_chance(elite_chance(run.depth), run.difficulty)) {
			apply_elite(&hunter, rng_below(rng, len(ELITE_MODIFIERS)))
		}
		hunter.name = "Story-Marked Hunter"
		hunter.role = .Elite
		hunter.elite_mod = -1
		hunter.max_hp = max(1, int(f32(hunter.max_hp) * 1.28))
		hunter.hp = hunter.max_hp
		hunter.damage += max(1, run.depth / 2)
		hunter.xp += 14 + run.depth * 2
		hunter.aggro_range += 2.5
		hunter.color = run.story.accent
		if !special_room_is_safe(special_room_kind_for_room(&run.dungeon, room_index)) {
			enemy_ensure_id(run, &hunter)
			append(&run.enemies, hunter)
		}
	}
}

// pygame picks rooms[2:-1]; Odin additionally skips safe special rooms
// because populate discards enemies there, which would break the guarantee.
@(private = "file")
spawn_challenge_boss :: proc(run: ^Run, rng: ^Pcg32, mod: ^Run_Modifier) {
	rooms := dungeon_rooms(&run.dungeon)
	candidate_count := 0
	for room_index in 2 ..< len(rooms) - 1 {
		if !special_room_is_safe(special_room_kind_for_room(&run.dungeon, room_index)) do candidate_count += 1
	}
	if candidate_count == 0 do return
	pick := rng_below(rng, candidate_count)
	for room_index in 2 ..< len(rooms) - 1 {
		if special_room_is_safe(special_room_kind_for_room(&run.dungeon, room_index)) do continue
		if pick > 0 {
			pick -= 1
			continue
		}
		// Challenge guardians draw from the stronger final-room pool, like
		// pygame's _make_miniboss(final_room=True).
		champion := enemy_make(pick_enemy_kind(rng, true), population_room_point(&run.dungeon, rooms[room_index], rng), run.depth)
		apply_run_modifier_stats(&champion, mod)
		apply_story_enemy_stats(run, &champion)
		apply_enemy_difficulty(&champion, run.difficulty)
		promote_miniboss(&champion, THEMES[run.theme_index].accent)
		champion.challenge_boss = true
		enemy_ensure_id(run, &champion)
		append(&run.enemies, champion)
		return
	}
}

apply_enemy_difficulty :: proc(enemy: ^Enemy, difficulty: Difficulty_Id) {
	if enemy == nil do return
	stats := difficulty_apply_enemy_stats({
		hp = enemy.max_hp,
		damage = enemy.damage,
		speed = enemy.speed,
		attack_cooldown = enemy.attack_cd_s,
		aggro_range = enemy.aggro_range,
	}, difficulty)
	enemy.max_hp = stats.hp
	enemy.hp = stats.hp
	enemy.damage = stats.damage
	enemy.speed = stats.speed
	enemy.attack_cd_s = stats.attack_cooldown
	enemy.aggro_range = stats.aggro_range
	enemy.difficulty_scaled = true
}

// The depth-ten Tyrant receives a second, authored post-scaling pass after
// depth and difficulty. This is intentionally stronger than an ordinary floor
// boss: it is the run's final encounter, not another themed guardian.
apply_final_boss_scaling :: proc(enemy: ^Enemy) {
	if enemy == nil do return
	enemy.max_hp = max(1, int(f32(enemy.max_hp) * FINAL_BOSS_HP_MULT))
	enemy.hp = enemy.max_hp
	enemy.damage += FINAL_BOSS_DAMAGE_BONUS
	enemy.attack_cd_s = max(FINAL_BOSS_COOLDOWN_MIN, enemy.attack_cd_s * FINAL_BOSS_COOLDOWN_MULT)
	enemy.attack_range = max(enemy.attack_range, FINAL_BOSS_ATTACK_RANGE_MIN)
	enemy.aggro_range = FINAL_BOSS_AGGRO_RANGE
	enemy.speed = max(enemy.speed, FINAL_BOSS_SPEED_MIN)
}

// Boss floors put their guardian in the arena (the stairs room). The guardian
// identity comes from the floor plan (MX.4): depths 3/6/9 carry a themed
// floor boss, depth 10 the Gate Tyrant renamed by the floor's theme.
@(private = "file")
spawn_floor_boss :: proc(run: ^Run, mod: ^Run_Modifier) {
	arena := run.dungeon.rooms_buf[run.dungeon.room_count - 1]
	center := room_center(arena)

	boss: Enemy
	if run.depth >= DUNGEON_DEPTH {
		boss = make_boss(.Gate_Tyrant, run.depth, TYRANT_TITLES[run.theme_index])
		apply_run_modifier_stats(&boss, mod)
		apply_story_enemy_stats(run, &boss)
		apply_enemy_difficulty(&boss, run.difficulty)
		apply_final_boss_scaling(&boss)
		if story_true_name_known(&run.story, .Sorn) {
			boss.name = SORN_TYRANT_TITLES[run.theme_index]
			boss.max_hp = max(1, int(f32(boss.max_hp) * .88))
		}
		if story_true_name_known(&run.story, .Liss) do boss.max_hp = max(1, int(f32(boss.max_hp) * .94))
		boss.hp = boss.max_hp
		boss.damage_type = (run.theme_index == 2 || run.theme_index == 7) ? .Shadow : .Physical
	} else {
		boss = make_boss(run_floor_plan(run).boss, run.depth, "")
		apply_run_modifier_stats(&boss, mod)
		apply_story_enemy_stats(run, &boss)
		apply_enemy_difficulty(&boss, run.difficulty)
		// Floor bosses are hulking gatekeepers (population.py _make_floor_boss).
		boss.max_hp = int(f32(boss.max_hp) * FLOOR_BOSS_HP_MULT)
		boss.hp = boss.max_hp
		boss.damage += FLOOR_BOSS_DAMAGE_BONUS
		boss.attack_cd_s = max(0.55, boss.attack_cd_s * 0.82)
		boss.attack_range = max(boss.attack_range, 1.85)
		boss.aggro_range += 3.0
		boss.speed = max(boss.speed, 1.05)
	}

	// Park the boss near the arena center, off the stair shaft.
	spots := [5]Vec2{
		{f32(center.x) + 2.0, f32(center.y) + 0.5},
		{f32(center.x) - 1.5, f32(center.y) + 1.5},
		{f32(center.x) + 0.5, f32(center.y) + 2.0},
		{f32(center.x) + 0.5, f32(center.y) - 1.5},
		{f32(center.x) + 2.5, f32(center.y) + 2.5},
	}
	for spot in spots {
		if !blocked_for_radius(&run.dungeon, spot.x, spot.y, BOSS_MOVE_RADIUS) {
			boss.pos = spot
			boss.prev_pos = spot
			break
		}
	}
	enemy_ensure_id(run, &boss)
	append(&run.enemies, boss)
}

@(private = "file")
make_boss :: proc(id: Boss_Id, depth: int, title: string) -> Enemy {
	def := BOSS_DEFS[id]
	hp := max(1, int(f32(def.max_hp) * depth_hp_multiplier(depth)))
	boss := Enemy{
		kind = .Ghoul, // unused for bosses; sprite comes from boss_id
		boss_id = id,
		name = title != "" ? title : def.name,
		role = .Boss,
		elite_mod = -1,
		final_boss = def.final_boss,
		big = true,
		facing = {1, 1},
		hp = hp,
		max_hp = hp,
		damage = def.damage + depth_damage_bonus(depth),
		xp = def.xp,
		speed = def.speed,
		aggro_range = def.aggro_range,
		attack_range = def.attack_range,
		attack_cd_s = def.attack_cooldown,
		ranged = def.attack_range >= 2.0,
		color = def.color,
		damage_type = def.damage_type,
		abilities = def.abilities,
		ability_count = def.ability_count,
		pending_ability = PENDING_BASE_ATTACK,
		last_ability = -1,
	}
	if id == .Gate_Tyrant {
		boss.resistances[.Physical] = 0.30
		boss.resistances[.Shadow] = 0.34
		boss.resistances[.Holy] = -0.15
	} else {
		boss.resistances[def.damage_type] = 0.45
		boss.resistances[.Physical] = max(boss.resistances[.Physical], 0.25)
		boss.resistances[.Holy] = -0.15
	}
	return boss
}

make_miniboss :: proc(rng: ^Pcg32, pos: Vec2, depth: int, accent: [4]u8 = {214, 176, 120, 255}) -> Enemy {
	enemy := enemy_make(pick_enemy_kind(rng, false), pos, depth)
	promote_miniboss(&enemy, accent)
	return enemy
}

// MX.2.5: an Oathbound miniboss keeps its base kind name (the "Oathbound"
// title composes in enemy_display_name) and wears the theme accent, matching
// population.py _make_miniboss.
promote_miniboss :: proc(enemy: ^Enemy, accent: [4]u8) {
	enemy.role = .Miniboss
	enemy.max_hp = int(f32(enemy.max_hp) * MINIBOSS_HP_MULT)
	enemy.hp = enemy.max_hp
	enemy.damage += MINIBOSS_DAMAGE_BONUS
	enemy.xp += MINIBOSS_XP_BONUS
	enemy.aggro_range += 2.0
	enemy.color = accent
}

apply_elite :: proc(enemy: ^Enemy, mod_index: int) {
	m := ELITE_MODIFIERS[mod_index]
	enemy.role = .Elite
	enemy.elite_mod = mod_index
	enemy.max_hp = max(1, int(f32(enemy.max_hp) * m.hp_mult))
	enemy.hp = enemy.max_hp
	enemy.damage += m.damage_bonus
	enemy.speed *= m.speed_mult
	enemy.xp += m.xp_bonus
	enemy.aggro_range += m.aggro_bonus
	switch mod_index {
	case 1: // Ironbound
		enemy.resistances[.Physical] = max(enemy.resistances[.Physical], 0.32)
	case 2: // Venomous
		enemy.damage_type = .Poison
		enemy.resistances[.Poison] = max(enemy.resistances[.Poison], 0.40)
	case 3: // Runed
		enemy.damage_type = .Arcane
		enemy.resistances[.Arcane] = max(enemy.resistances[.Arcane], 0.34)
	case 0:
	}
	// MX.2.5: modifier palette shift and doctrine reassignment. A Frenzied or
	// Venomous elite fights as a flanker, Ironbound holds as a guard — which
	// deliberately drops a ranged elite to the default band (enemy_tactic).
	enemy.color = elite_shift_color(enemy.color, m.color_shift)
	if m.has_tactic do enemy.tactic = m.tactic
}

enemy_make :: proc(kind: Enemy_Kind, pos: Vec2, depth: int) -> Enemy {
	def := ENEMY_DEFS[kind]
	hp := max(1, int(f32(def.max_hp) * depth_hp_multiplier(depth)))
	enemy := Enemy{
		kind = kind,
		role = .Normal,
		elite_mod = -1,
		pending_ability = PENDING_BASE_ATTACK,
		last_ability = -1,
		tactic = def.tactic,
		pos = pos,
		prev_pos = pos,
		facing = {1, 1},
		hp = hp,
		max_hp = hp,
		damage = def.damage + depth_damage_bonus(depth),
		xp = def.xp,
		speed = def.speed,
		aggro_range = def.aggro_range,
		attack_range = def.attack_range,
		attack_cd_s = def.attack_cooldown,
		ranged = def.ranged,
		color = def.color,
		damage_type = def.damage_type,
	}
	switch kind {
	case .Cultist:
		enemy.resistances[.Arcane] = .24; enemy.resistances[.Shadow] = .12
	case .Bone_Imp:
		enemy.resistances[.Frost] = .22; enemy.resistances[.Holy] = -.10
	case .Venom_Skitter:
		enemy.resistances[.Poison] = .45; enemy.resistances[.Fire] = -.18
	case .Crypt_Brute:
		enemy.resistances[.Physical] = .24; enemy.resistances[.Arcane] = -.10
	case .Ghoul:
		enemy.resistances[.Shadow] = .18; enemy.resistances[.Holy] = -.15
	case .Grave_Archer:
		enemy.resistances[.Physical] = .10; enemy.resistances[.Poison] = -.08
	case .Ash_Hound:
		enemy.resistances[.Fire] = .34; enemy.resistances[.Frost] = -.18
	case .Rune_Sentinel:
		enemy.resistances[.Arcane] = .38; enemy.resistances[.Physical] = .10
	case .Plague_Toad:
		enemy.resistances[.Poison] = .38; enemy.resistances[.Fire] = -.12
	case .Hollow_Knight:
		enemy.resistances[.Physical] = .18; enemy.resistances[.Shadow] = .12
	case .Gate_Warden:
		enemy.resistances[.Physical] = .20; enemy.resistances[.Holy] = .28; enemy.resistances[.Shadow] = -.12
	}
	return enemy
}

// --- Loot rolls (population.py _make_loot / _make_equipment) ---------------

RARE_WEAPON_POWER_CAP :: 16
RARE_ARMOR_DEFENSE_CAP :: 12
RARE_WEAPON_POWER_CAP_SHALLOW :: 10
RARE_ARMOR_DEFENSE_CAP_SHALLOW :: 6
RARE_ROLL_DEPTH_GAIN_PER_FLOOR :: f32(0.03)
ORDINARY_UNIQUE_DROP_CHANCE :: f32(0.001)
ORDINARY_UNIQUE_LOOT_BONUS_SCALE :: f32(0.05)
ORDINARY_UNIQUE_DROP_CHANCE_CAP :: f32(0.025)

rare_primary_cap :: proc(slot: Item_Kind, depth: int) -> int {
	floor := clamp(depth, 1, DUNGEON_DEPTH)
	progress := floor - 1
	switch slot {
	case .Weapon:
		return RARE_WEAPON_POWER_CAP_SHALLOW + progress * (RARE_WEAPON_POWER_CAP - RARE_WEAPON_POWER_CAP_SHALLOW) / (DUNGEON_DEPTH - 1)
	case .Armor:
		return RARE_ARMOR_DEFENSE_CAP_SHALLOW + progress * (RARE_ARMOR_DEFENSE_CAP - RARE_ARMOR_DEFENSE_CAP_SHALLOW) / (DUNGEON_DEPTH - 1)
	case .Heal_Potion, .Mana_Potion, .Identify_Scroll, .Remove_Curse_Scroll:
		return 0
	}
	return 0
}

rare_roll_profile :: proc(depth: int) -> Rarity_Profile {
	profile := RARITIES[Rarity.Rare]
	depth_gain := f32(clamp(depth, 1, DUNGEON_DEPTH) - 1) * RARE_ROLL_DEPTH_GAIN_PER_FLOOR
	profile.roll_lo += depth_gain
	profile.roll_hi += depth_gain
	return profile
}

ordinary_unique_drop_chance :: proc(run: ^Run) -> f32 {
	if run == nil do return 0
	loot_bonus := RUN_MODIFIERS[run.modifier].loot_bonus + story_effect_clamped(run, .Loot_Bonus, 0, .25)
	return clamp(ORDINARY_UNIQUE_DROP_CHANCE + loot_bonus * ORDINARY_UNIQUE_LOOT_BONUS_SCALE, 0, ORDINARY_UNIQUE_DROP_CHANCE_CAP)
}

make_loot :: proc(rng: ^Pcg32, pos: Vec2, curse_bonus := f32(0), run: ^Run = nil, depth := 1) -> Ground_Item {
	roll := rng_f32(rng)
	if roll < 0.24 {
		return {item = {kind = .Heal_Potion, name = "Minor Healing Potion", icon = ICON_HEAL_POTION}, pos = pos}
	}
	if roll < 0.34 {
		return {item = {kind = .Mana_Potion, name = "Lesser Mana Potion", icon = ICON_MANA_POTION}, pos = pos}
	}
	if roll < 0.42 {
		return {item = {kind = .Identify_Scroll, name = "Scroll of Identify", icon = ICON_IDENTIFY_SCROLL}, pos = pos}
	}
	if roll < 0.455 {
		return {item = {kind = .Remove_Curse_Scroll, name = "Scroll of Remove Curse", icon = ICON_REMOVE_CURSE_SCROLL, rarity = .Magic}, pos = pos}
	}
	// Ordinary named Uniques are intentionally exceptional. Loot pressure can
	// widen the 0.1% jackpot modestly, while guaranteed Tyrant rewards remain
	// on their separate kill-reward path. Run-less callers cannot roll one.
	if run != nil && roll > 1 - ordinary_unique_drop_chance(run) {
		return {item = make_unique(rng, run.player.archetype, run.depth), pos = pos}
	}
	slot: Item_Kind = roll < 0.70 ? .Weapon : .Armor
	rarity: Rarity = rng_chance(rng, 0.34) ? .Rare : .Magic
	if rng_chance(rng, 0.20) do rarity = .Common
	item_depth := run != nil ? run.depth : depth
	return {item = make_equipment(rng, slot, rarity, curse_bonus, run, item_depth), pos = pos}
}

story_empower_equipment :: proc(run: ^Run, rng: ^Pcg32, item: ^Item, guaranteed := false) -> bool {
	if run == nil || rng == nil || item == nil || (item.kind != .Weapon && item.kind != .Armor) do return false
	if story_item_is_relic_touched(item) do return false
	relic_power := story_effect_clamped(run, .Relic_Power, 0, .35)
	if relic_power <= 0 do return false
	if !guaranteed && !rng_chance(rng, min(f32(.45), relic_power * 1.35)) do return false
	bonus := max(2, int(math.round(2 + relic_power * 14)))
	if item.kind == .Weapon {
		item.power += bonus
		item.name = "Relic-Touched Weapon"
	} else {
		item.defense += max(2, bonus / 2 + 1)
		item.name = "Relic-Touched Armor"
	}
	return true
}

make_equipment :: proc(rng: ^Pcg32, slot: Item_Kind, rarity: Rarity, curse_bonus := f32(0), run: ^Run = nil, depth := 1) -> Item {
	item: Item
	item.kind = slot
	item.rarity = rarity
	if slot == .Weapon {
		base := WEAPON_BASES[rng_below(rng, len(WEAPON_BASES))]
		item.name = base.name
		item.icon = base.icon
		item.power = base.value
	} else {
		base := ARMOR_BASES[rng_below(rng, len(ARMOR_BASES))]
		item.name = base.name
		item.icon = base.icon
		item.defense = base.value
	}
	item_depth := run != nil ? run.depth : depth
	roll_affixes(rng, &item, item_depth)
	// 8% base curse chance; run modifier and story curse pressure add directly.
	story_curse := run != nil ? story_effect_clamped(run, .Curse_Bonus, 0, .18) : f32(0)
	if rarity != .Common && rng_chance(rng, 0.08 + curse_bonus + story_curse) do apply_cursed_bargain(&item)
	if run != nil do _ = story_empower_equipment(run, rng, &item)
	item.unidentified = rarity != .Common && rng_chance(rng, 0.45)
	if rarity == .Rare {
		item.power = min(item.power, rare_primary_cap(.Weapon, item_depth))
		item.defense = min(item.defense, rare_primary_cap(.Armor, item_depth))
	} else {
		item.power = min(item.power, 7)
		item.defense = min(item.defense, 4)
	}
	return item
}

@(private = "file")
roll_affixes :: proc(rng: ^Pcg32, item: ^Item, depth: int) {
	profile := item.rarity == .Rare ? rare_roll_profile(depth) : RARITIES[item.rarity]
	attempts := 0
	for item.affix_count < profile.affixes && attempts < 20 {
		attempts += 1
		kind := Affix_Kind(rng_below(rng, len(Affix_Kind)))
		def := AFFIX_DEFS[kind]
		if item.kind == .Weapon && !def.weapon do continue
		if item.kind == .Armor && !def.armor do continue
		duplicate := false
		for i in 0 ..< item.affix_count {
			if item.affixes[i].kind == kind do duplicate = true
		}
		if duplicate do continue

		apply_affix_roll(rng, item, kind, profile)
		item.affixes[item.affix_count] = {kind}
		item.affix_count += 1
	}
	item.proc_chance = min(item.proc_chance, 0.85)
	item.lifesteal = min(item.lifesteal, 0.22)
	item.attack_speed = clamp(item.attack_speed, -0.20, 0.36)
	item.cast_speed = clamp(item.cast_speed, -0.20, 0.36)
	item.move_speed = clamp(item.move_speed, -0.20, 0.28)
}

@(private = "file")
roll_affix_value :: proc(rng: ^Pcg32, stat: Stat_Range, profile: Rarity_Profile) -> f32 {
	if stat.lo == 0 && stat.hi == 0 do return 0
	base := stat.lo + (stat.hi - stat.lo) * rng_f32(rng)
	mult := profile.roll_lo + (profile.roll_hi - profile.roll_lo) * rng_f32(rng)
	return base * mult
}

@(private = "file")
roll_affix_int :: proc(rng: ^Pcg32, stat: Stat_Range, profile: Rarity_Profile) -> int {
	value := roll_affix_value(rng, stat, profile)
	if value == 0 do return 0
	return int(math.round(value))
}

@(private = "file")
apply_affix_roll :: proc(rng: ^Pcg32, item: ^Item, kind: Affix_Kind, profile: Rarity_Profile) {
	def := AFFIX_DEFS[kind]
	item.power += roll_affix_int(rng, def.power, profile)
	item.defense += roll_affix_int(rng, def.defense, profile)
	item.attack_speed += roll_affix_value(rng, def.attack_speed, profile)
	item.cast_speed += roll_affix_value(rng, def.cast_speed, profile)
	item.move_speed += roll_affix_value(rng, def.move_speed, profile)
	item.thorns += max(0, roll_affix_int(rng, def.thorns, profile))
	item.lifesteal += max(0, roll_affix_value(rng, def.lifesteal, profile))
	item.proc_chance += max(0, roll_affix_value(rng, def.proc_chance, profile))
	if def.typed {
		item.typed = true
		item.damage_type = def.damage_type
	}
	if def.has_bonus do item.skill_bonuses[def.skill_bonus] = true
	if def.proc_effect != .None {
		item.proc_effects[def.proc_effect] = true
		if item.proc_effect == .None do item.proc_effect = def.proc_effect
	}
}

apply_cursed_bargain :: proc(item: ^Item) {
	if item == nil || (item.kind != .Weapon && item.kind != .Armor) do return
	item.cursed = true
	item.rarity = .Cursed
	if item.kind == .Weapon {
		item.power += 4
		item.proc_chance = min(0.90, item.proc_chance + 0.08)
		item.attack_speed += 0.03
		item.move_speed -= 0.03
	} else {
		item.defense += 3
		item.thorns += 2
		item.cast_speed -= 0.03
		item.move_speed -= 0.04
	}
}

pick_enemy_kind :: proc(rng: ^Pcg32, final_room: bool) -> Enemy_Kind {
	total := 0
	for kind in Enemy_Kind {
		if ENEMY_DEFS[kind].final_room_only && !final_room do continue
		total += ENEMY_DEFS[kind].weight
	}
	roll := rng_below(rng, total)
	for kind in Enemy_Kind {
		if ENEMY_DEFS[kind].final_room_only && !final_room do continue
		roll -= ENEMY_DEFS[kind].weight
		if roll < 0 do return kind
	}
	return .Ghoul
}
