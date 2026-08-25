package archrogue

// Persistent Acolyte spirits and the Ranger Spirit Beast. This module is
// deliberately raylib-free: summons and companion AI are fixed-step gameplay
// state, while assets/rendering only consume the fields below.

import "core:math"

FAMILIAR_BASE_HP                 :: 20
FAMILIAR_BASE_DAMAGE             :: 6
FAMILIAR_BASE_SPEED              :: f32(3.2)
FAMILIAR_ATTACK_RANGE            :: f32(1.25)
FAMILIAR_ATTACK_COOLDOWN         :: f32(0.85)
FAMILIAR_AGGRO_RANGE             :: f32(7.0)
FAMILIAR_FOLLOW_DISTANCE         :: f32(1.6)
FAMILIAR_ATTACK_ANIMATION_TIME   :: f32(0.42)
FAMILIAR_MOVE_COLLISION_RADIUS   :: f32(0.22)
FAMILIAR_OWNER_SEPARATION        :: f32(0.45)
FAMILIAR_WALK_ANIM_SCALE_FLOOR  :: f32(0.25)

SPIRIT_CALL_MANA_COST        :: f32(14.0)
SPIRIT_CALL_COOLDOWN         :: f32(3.2)
SPIRIT_CALL_SPAWN_RADIUS     :: f32(0.9)
SPIRIT_CALL_MAX_FAMILIARS    :: 3
SPIRIT_CALL_SPAWN_SEPARATION :: FAMILIAR_MOVE_COLLISION_RADIUS * 2

SPIRIT_BEAST_BASE_HP           :: 60
SPIRIT_BEAST_BASE_DAMAGE       :: 12
SPIRIT_BEAST_BASE_SPEED        :: f32(3.55)
SPIRIT_BEAST_ATTACK_COOLDOWN   :: f32(0.86)
SPIRIT_BEAST_AGGRO_RANGE       :: f32(8.0)
SPIRIT_BEAST_FOLLOW_DISTANCE   :: f32(1.8)
SPIRIT_BEAST_RETURN_DISTANCE   :: f32(0.9)
SPIRIT_BEAST_COLLISION_RADIUS  :: f32(0.24)
SPIRIT_BEAST_MIN_SPAWN_DISTANCE :: f32(0.45)
SPIRIT_BEAST_MANA_FRACTION     :: f32(0.5)
SPIRIT_BEAST_REPLACE_COOLDOWN  :: f32(60.0)

// Non-story petting (interactions.py:58-83): a short soothing ritual that
// heals the beast, doubled once per acquired Beast-path degree.
SPIRIT_BEAST_PET_RANGE    :: f32(1.5)
SPIRIT_BEAST_PET_HEAL     :: 2
SPIRIT_BEAST_PET_COOLDOWN :: f32(2.0)
SPIRIT_BEAST_PET_SECONDS  :: f32(0.8)

Familiar_Kind :: enum u8 {
	Wisp,
	Crow,
	Spirit_Beast,
	Bar_Dancer,
	Soulless_Clanker,
	String,
}

// 4.8.7 immortal Bar Dancer (combat/familiars.py:58-65): the depth-10 reward
// for toasting every bar the run generated. Class-independent, so her numbers
// live here rather than scaling with any discipline path; `unkillable` (HP
// floors at 1 and regenerates) is what makes her immortal.
BAR_DANCER_HP     :: 46
BAR_DANCER_DAMAGE :: 7
BAR_DANCER_SPEED  :: f32(3.5)
BAR_DANCER_ACCENT :: [4]u8{224, 126, 72, 255}

SOULLESS_CLANKER_HP              :: 38
SOULLESS_CLANKER_DAMAGE          :: 8
SOULLESS_CLANKER_SPEED           :: f32(2.65)
SOULLESS_CLANKER_ATTACK_COOLDOWN :: f32(0.9)

STRING_HP              :: 34
STRING_DAMAGE          :: 7
STRING_SPEED           :: f32(3.15)
STRING_ATTACK_COOLDOWN :: f32(0.85)

Familiar_Command :: enum u8 {
	Attack,
	Follow,
}

// `spirit_rank` is inert at rank zero, the current M8 baseline. Keeping it on
// the actor lets M9 disciplines activate the already-ported stat steps without
// replacing the runtime model or changing saves later.
Familiar :: struct {
	entity_id:         u32, // stable for presentation and future network identity
	kind:              Familiar_Kind,
	command:           Familiar_Command,
	spirit_rank:       int,
	pos:               Vec2,
	prev_pos:          Vec2,
	facing:            Vec2,
	move_dir:          Vec2,
	hp:                int,
	max_hp:            int,
	damage:            int,
	speed:             f32,
	attack_range:      f32,
	attack_cooldown:   f32,
	attack_timer:      f32,
	attack_anim_timer: f32,
	pet_cooldown:      f32,
	pet_anim_timer:    f32, // while > 0 the familiar is fully suspended
	anim_time:         f32,
	regen_progress:    f32,
	moving:            bool,
	champion:          bool,
	unkillable:        bool,
	lifesteal:         bool, // set when the Blood siphon ladder is non-zero at Spirit Call
}

Familiar_Stats :: struct {
	hp:              int,
	damage:          int,
	speed:           f32,
	attack_cooldown: f32,
	count:           int,
	kind:            Familiar_Kind,
	champion:        bool,
	unkillable:      bool,
}

familiar_alive :: proc(familiar: ^Familiar) -> bool {
	return familiar != nil && familiar.hp > 0
}

// Full pygame Spirit-path ramp, exposed now so M9 only needs to supply the
// acquired degree. Rank zero is the fresh Acolyte's small wisp.
spirit_call_stats :: proc(spirit_rank: int) -> Familiar_Stats {
	rank := clamp(spirit_rank, 0, 5)
	stats := Familiar_Stats{
		hp = FAMILIAR_BASE_HP,
		damage = FAMILIAR_BASE_DAMAGE,
		speed = FAMILIAR_BASE_SPEED,
		attack_cooldown = FAMILIAR_ATTACK_COOLDOWN,
		count = 1,
		kind = .Wisp,
	}
	if rank >= 1 {
		stats.hp += 12
		stats.damage += 2
		stats.kind = .Crow
	}
	if rank >= 2 do stats.hp += 10
	if rank >= 3 {
		stats.damage += 2
		stats.count += 1
	}
	if rank >= 4 {
		stats.hp += 24
		stats.damage += 4
		stats.champion = true
	}
	if rank >= 5 {
		stats.hp += 16
		stats.count += 1
		stats.unkillable = true
	}
	return stats
}

// Full Beast-path stat ramp. Rank zero is the fresh Ranger's beast; the
// equipment bonus is an explicit input so this helper stays content/UI-free.
spirit_beast_stats :: proc(beast_rank: int, equipment_bonus := false) -> Familiar_Stats {
	rank := clamp(beast_rank, 0, 5)
	stats := Familiar_Stats{
		hp = SPIRIT_BEAST_BASE_HP,
		damage = SPIRIT_BEAST_BASE_DAMAGE,
		speed = SPIRIT_BEAST_BASE_SPEED,
		attack_cooldown = SPIRIT_BEAST_ATTACK_COOLDOWN,
		count = 1,
		kind = .Spirit_Beast,
	}
	if rank >= 1 {
		stats.hp += 14
		stats.damage += 2
	}
	if rank >= 2 {
		stats.hp += 8
		stats.damage += 2
		stats.attack_cooldown -= 0.08
	}
	if rank >= 3 {
		stats.hp += 18
		stats.damage += 3
		stats.speed += 0.15
	}
	if rank >= 4 {
		stats.hp += 14
		stats.damage += 3
		stats.speed += 0.10
		stats.attack_cooldown -= 0.05
	}
	if rank >= 5 {
		stats.hp += 24
		stats.damage += 4
		stats.speed += 0.10
		stats.attack_cooldown -= 0.07
		stats.champion = true
	}
	if equipment_bonus {
		stats.hp += 12
		stats.damage += 2
	}
	stats.attack_cooldown = max(0.52, stats.attack_cooldown)
	return stats
}

@(private = "file")
make_familiar :: proc(stats: Familiar_Stats, pos, facing: Vec2, spirit_rank: int, command := Familiar_Command.Attack) -> Familiar {
	return Familiar{
		kind = stats.kind,
		command = command,
		spirit_rank = clamp(spirit_rank, 0, 5),
		pos = pos,
		prev_pos = pos,
		facing = facing,
		move_dir = facing,
		hp = stats.hp,
		max_hp = stats.hp,
		damage = stats.damage,
		speed = stats.speed,
		attack_range = FAMILIAR_ATTACK_RANGE,
		attack_cooldown = stats.attack_cooldown,
		champion = stats.champion,
		unkillable = stats.unkillable,
	}
}

@(private = "file")
spirit_call_spawn_valid :: proc(run: ^Run, pos: Vec2, chosen: []Vec2) -> bool {
	if blocked_for_radius(
		&run.dungeon,
		pos.x,
		pos.y,
		FAMILIAR_MOVE_COLLISION_RADIUS,
		block_stairs = true,
	) {
		return false
	}
	if !line_of_sight(&run.dungeon, run.player.pos.x, run.player.pos.y, pos.x, pos.y) do return false

	minimum_gap_sq := SPIRIT_CALL_SPAWN_SEPARATION * SPIRIT_CALL_SPAWN_SEPARATION
	for other in chosen {
		delta := pos - other
		if delta.x * delta.x + delta.y * delta.y < minimum_gap_sq do return false
	}
	// Recasts replace class summons, but the run-reward Bar Dancer remains.
	for &familiar in run.familiars {
		if familiar.kind != .Bar_Dancer || familiar.hp <= 0 do continue
		delta := pos - familiar.pos
		if delta.x * delta.x + delta.y * delta.y < minimum_gap_sq do return false
	}
	return true
}

@(private = "file")
spirit_call_spawn_positions :: proc(run: ^Run, count: int) -> (positions: [SPIRIT_CALL_MAX_FAMILIARS]Vec2, found: bool) {
	if run == nil || count <= 0 || count > len(positions) do return {}, false
	angle_offsets := [8]f32{
		0,
		math.PI / 4,
		-math.PI / 4,
		math.PI / 2,
		-math.PI / 2,
		3 * math.PI / 4,
		-3 * math.PI / 4,
		math.PI,
	}
	distances := [5]f32{SPIRIT_CALL_SPAWN_RADIUS, 0.65, 1.15, 0.45, 1.4}

	for index in 0 ..< count {
		base_angle := f32(index) / f32(count) * (2 * math.PI) + 0.7
		placed := false
		for distance in distances {
			for offset in angle_offsets {
				angle := base_angle + offset
				candidate := run.player.pos + Vec2{math.cos(angle), math.sin(angle)} * distance
				if !spirit_call_spawn_valid(run, candidate, positions[:index]) do continue
				positions[index] = candidate
				placed = true
				break
			}
			if placed do break
		}

		// Irregular rooms can block every orbit sample. Search nearby floor centers
		// deterministically before rejecting the cast; no gameplay RNG is consumed.
		if !placed {
			tile_x, tile_y := int(run.player.pos.x), int(run.player.pos.y)
			for radius in 1 ..= 3 {
				for offset_y in -radius ..= radius {
					for offset_x in -radius ..= radius {
						if max(abs(offset_x), abs(offset_y)) != radius do continue
						candidate := Vec2{f32(tile_x + offset_x) + 0.5, f32(tile_y + offset_y) + 0.5}
						if !spirit_call_spawn_valid(run, candidate, positions[:index]) do continue
						positions[index] = candidate
						placed = true
						break
					}
					if placed do break
				}
				if placed do break
			}
		}
		if !placed do return {}, false
	}
	return positions, true
}

player_cast_spirit_call :: proc(run: ^Run) -> bool {
	if run == nil do return false
	return player_cast_spirit_call_rank(run, discipline_path_rank(&run.player, .Acolyte_Spirit))
}

player_cast_spirit_call_rank :: proc(run: ^Run, spirit_rank: int) -> bool {
	if run == nil do return false
	player := &run.player
	if player.archetype != .Acolyte do return false
	mana_cost := player_class_skill_mana_cost(player)
	if player.class_skill_timer > 0 || player.mana < mana_cost do return false

	stats := spirit_call_stats(spirit_rank)
	spawn_positions, found := spirit_call_spawn_positions(run, stats.count)
	if !found do return false
	player.mana -= mana_cost
	player.class_skill_timer = player_class_skill_cooldown(player)
	player_start_visual_action(player,.Cast,PLAYER_CLASS_ACTION_SECONDS)
	feel_emit(
		run,.Summon,player.pos,ARCHETYPE_SKILL_COLORS[.Acolyte],.48,.82,
		phase=.Origin,style=.Acolyte,priority=.High,
	)
	clear_summoned_familiars(run) // recasting recreates and fully refreshes the host

	for index in 0 ..< stats.count {
		pos := spawn_positions[index]
		familiar_stats := stats
		// Crow Lord marks only the lead familiar as champion.
		familiar_stats.champion = stats.champion && index == 0
		familiar := make_familiar(familiar_stats, pos, player.facing, spirit_rank)
		run.next_familiar_id += 1
		if run.next_familiar_id == 0 do run.next_familiar_id = 1
		familiar.entity_id = run.next_familiar_id
		familiar.lifesteal = acolyte_spell_leech(player) > 0
		append(&run.familiars, familiar)
		feel_emit(
			run,.Summon,pos,ARCHETYPE_SKILL_COLORS[.Acolyte],.40,.46,
			phase=.Arrival,style=.Acolyte,priority=.High,
		)
	}
	append(&run.numbers, Damage_Number{pos = player.pos, kind = .Text, text = "Spirit Call"})
	sfx_emit(run, .Acolyte_Spirit_Call, player.pos, spatial = true)
	return true
}

living_spirit_beast :: proc(run: ^Run) -> ^Familiar {
	for &familiar in run.familiars {
		if familiar.kind == .Spirit_Beast && familiar.hp > 0 do return &familiar
	}
	return nil
}

spirit_beast_pet_heal :: proc(player: ^Player) -> int {
	return SPIRIT_BEAST_PET_HEAL << uint(discipline_path_rank(player, .Ranger_Beast))
}

// Readiness (interactions.py:340-364): Ranger only, beast alive and off its
// petting cooldown, strictly within range, LOS-connected.
nearby_pettable_spirit_beast :: proc(run: ^Run) -> ^Familiar {
	if run.player.archetype != .Ranger do return nil
	beast := living_spirit_beast(run)
	if beast == nil || beast.pet_cooldown > 0 do return nil
	delta := beast.pos - run.player.pos
	if delta.x * delta.x + delta.y * delta.y >= SPIRIT_BEAST_PET_RANGE * SPIRIT_BEAST_PET_RANGE do return nil
	if !line_of_sight(&run.dungeon, run.player.pos.x, run.player.pos.y, beast.pos.x, beast.pos.y) do return nil
	return beast
}

// The petting slice (interactions.py:386-430): paired pose — the Ranger and
// the beast face each other and both stand still for the clip — plus the
// doubled heal, the cooldown, and the floater.
pet_spirit_beast :: proc(run: ^Run) -> bool {
	beast := nearby_pettable_spirit_beast(run)
	if beast == nil do return false
	player := &run.player
	direction := beast.pos - player.pos
	if n := math.hypot(direction.x, direction.y); n > 0.001 {
		unit := direction / n
		player.facing = unit
		beast.facing = -unit
		beast.move_dir = -unit
	}
	heal := min(beast.max_hp - beast.hp, spirit_beast_pet_heal(player))
	beast.hp += heal
	beast.pet_cooldown = SPIRIT_BEAST_PET_COOLDOWN
	beast.pet_anim_timer = SPIRIT_BEAST_PET_SECONDS
	beast.attack_anim_timer = 0
	beast.moving = false
	player.moving = false
	player_start_visual_action(player, .Pet, SPIRIT_BEAST_PET_SECONDS)
	if heal > 0 do append(&run.numbers, Damage_Number{pos = beast.pos, value = heal, kind = .Heal})
	append(&run.numbers, Damage_Number{pos = beast.pos, kind = .Text, text = "Pet"})
	return true
}

refresh_active_spirit_beast :: proc(run: ^Run, beast_rank: int, equipment_bonus := false) {
	if run == nil do return
	beast := living_spirit_beast(run)
	if beast == nil do return
	stats := spirit_beast_stats(beast_rank, equipment_bonus)
	hp_gain := max(0, stats.hp - beast.max_hp)
	beast.max_hp = stats.hp
	beast.hp = min(beast.max_hp, beast.hp + hp_gain)
	beast.damage = stats.damage
	beast.speed = stats.speed
	beast.attack_cooldown = stats.attack_cooldown
	beast.champion = stats.champion
	beast.spirit_rank = clamp(beast_rank, 0, 5)
}

spirit_beast_next_command :: proc(run: ^Run) -> (command: Familiar_Command, available: bool) {
	beast := living_spirit_beast(run)
	if beast == nil do return {}, false
	return beast.command == .Follow ? .Attack : .Follow, true
}

@(private = "file")
spirit_beast_spawn_valid :: proc(run: ^Run, pos: Vec2) -> bool {
	delta := pos - run.player.pos
	if delta.x * delta.x + delta.y * delta.y < SPIRIT_BEAST_MIN_SPAWN_DISTANCE * SPIRIT_BEAST_MIN_SPAWN_DISTANCE {
		return false
	}
	if blocked_for_radius(&run.dungeon, pos.x, pos.y, SPIRIT_BEAST_COLLISION_RADIUS) do return false
	return line_of_sight(&run.dungeon, run.player.pos.x, run.player.pos.y, pos.x, pos.y)
}

spirit_beast_spawn_position :: proc(run: ^Run) -> (pos: Vec2, found: bool) {
	angle_offsets := [8]f32{
		0,
		math.PI / 4,
		-math.PI / 4,
		math.PI / 2,
		-math.PI / 2,
		3 * math.PI / 4,
		-3 * math.PI / 4,
		math.PI,
	}
	distances := [4]f32{0.9, 1.15, 0.65, 1.4}
	for distance in distances {
		for offset in angle_offsets {
			angle := 0.7 + offset
			candidate := run.player.pos + Vec2{math.cos(angle), math.sin(angle)} * distance
			if spirit_beast_spawn_valid(run, candidate) do return candidate, true
		}
	}

	// Cramped/corrupt maps fall back to nearby floor centers, but resources
	// are not committed unless one is radius-clear and LOS-connected.
	tile_x, tile_y := int(run.player.pos.x), int(run.player.pos.y)
	for radius in 1 ..= 3 {
		for offset_y in -radius ..= radius {
			for offset_x in -radius ..= radius {
				if max(abs(offset_x), abs(offset_y)) != radius do continue
				candidate := Vec2{f32(tile_x + offset_x) + 0.5, f32(tile_y + offset_y) + 0.5}
				if spirit_beast_spawn_valid(run, candidate) do return candidate, true
			}
		}
	}
	return {}, false
}

// Fresh-game entry point. A living beast turns slot 3 into a free command,
// regardless of its replacement timer or the Ranger's current mana.
player_cast_spirit_beast :: proc(run: ^Run) -> bool {
	// Beastlord Harness feeds the equipment bond (familiars.py:143-145).
	return player_cast_spirit_beast_rank(
		run,
		discipline_path_rank(&run.player, .Ranger_Beast),
		player_has_skill_bonus(&run.player, .Spirit_Beast_Bond),
	)
}

player_cast_spirit_beast_rank :: proc(run: ^Run, beast_rank: int, equipment_bonus := false) -> bool {
	player := &run.player
	if player.archetype != .Ranger do return false

	if beast := living_spirit_beast(run); beast != nil {
		beast.command = beast.command == .Follow ? .Attack : .Follow
		if beast.command == .Follow do beast.attack_anim_timer = 0
		text := beast.command == .Attack ? "Spirit Beast: Attack" : "Spirit Beast: Return"
		append(&run.numbers, Damage_Number{pos = beast.pos, kind = .Text, text = text})
		feel_emit(
			run,.Command,beast.pos,ARCHETYPE_SKILL_COLORS[.Ranger],.28,.34,
			direction=beast.facing,style=.Ranger,priority=.High,
		)
		sfx_emit(run, .Ranger_Beast_Command, beast.pos, spatial = true, emitter_id = u64(beast.entity_id))
		player_start_visual_action(player,.Cast,PLAYER_BEAST_COMMAND_ACTION_SECONDS)
		return true
	}

	mana_cost := player_class_skill_mana_cost(player)
	if player.class_skill_timer > 0 || player.mana < mana_cost do return false
	spawn, found := spirit_beast_spawn_position(run)
	if !found do return false

	stats := spirit_beast_stats(beast_rank, equipment_bonus)
	player.mana -= mana_cost
	player.class_skill_timer = SPIRIT_BEAST_REPLACE_COOLDOWN
	player_start_visual_action(player,.Cast,PLAYER_CLASS_ACTION_SECONDS)
	feel_emit(
		run,.Summon,player.pos,ARCHETYPE_SKILL_COLORS[.Ranger],.48,.82,
		phase=.Origin,style=.Ranger,priority=.High,
	)
	clear_summoned_familiars(run)
	beast := make_familiar(stats, spawn, player.facing, beast_rank)
	run.next_familiar_id += 1
	if run.next_familiar_id == 0 do run.next_familiar_id = 1
	beast.entity_id = run.next_familiar_id
	append(&run.familiars, beast)
	feel_emit(
		run,.Summon,spawn,ARCHETYPE_SKILL_COLORS[.Ranger],.40,.46,
		phase=.Arrival,style=.Ranger,priority=.High,
	)
	append(&run.numbers, Damage_Number{pos = player.pos, kind = .Text, text = "Spirit Beast"})
	sfx_emit(run, .Ranger_Beast_Summon, spawn, spatial = true, emitter_id = u64(beast.entity_id))
	return true
}

familiar_take_damage :: proc(familiar: ^Familiar, amount: int) {
	if familiar == nil || familiar.hp <= 0 do return
	damage := max(1, amount)
	if familiar.unkillable {
		familiar.hp = max(1, familiar.hp - damage)
	} else {
		familiar.hp -= damage
	}
}

// Enemy bolts query this before the player collision. It deliberately keeps
// host order, matching pygame's first-bodyguard-wins interception.
familiar_intercepting_projectile :: proc(run: ^Run, projectile_pos: Vec2, radius := f32(ENEMY_PROJECTILE_HIT_RADIUS)) -> ^Familiar {
	radius_sq := radius * radius
	for &familiar in run.familiars {
		if familiar.hp <= 0 do continue
		delta := projectile_pos - familiar.pos
		if delta.x * delta.x + delta.y * delta.y >= radius_sq do continue
		if !line_of_sight(&run.dungeon, projectile_pos.x, projectile_pos.y, familiar.pos.x, familiar.pos.y) do continue
		return &familiar
	}
	return nil
}

@(private = "file")
move_familiar :: proc(run: ^Run, familiar: ^Familiar, delta: Vec2) -> f32 {
	before := familiar.pos
	next_x := familiar.pos.x + delta.x
	if !blocked_for_radius(&run.dungeon, next_x, familiar.pos.y, FAMILIAR_MOVE_COLLISION_RADIUS) {
		familiar.pos.x = next_x
	}
	next_y := familiar.pos.y + delta.y
	if !blocked_for_radius(&run.dungeon, familiar.pos.x, next_y, FAMILIAR_MOVE_COLLISION_RADIUS) {
		familiar.pos.y = next_y
	}

	// Soft owner separation keeps a companion orbiting rather than occupying
	// the player's feet. Pygame applies this after wall probes as well.
	from_owner := familiar.pos - run.player.pos
	distance := math.hypot(from_owner.x, from_owner.y)
	if distance > 0.001 && distance < FAMILIAR_OWNER_SEPARATION {
		candidate := familiar.pos + from_owner / distance * (FAMILIAR_OWNER_SEPARATION - distance)
		if !blocked_for_radius(
			&run.dungeon,
			candidate.x,
			candidate.y,
			FAMILIAR_MOVE_COLLISION_RADIUS,
		) {
			familiar.pos = candidate
		}
	}
	return math.hypot(familiar.pos.x - before.x, familiar.pos.y - before.y)
}

@(private = "file")
advance_familiar_locomotion :: proc(familiar: ^Familiar, distance, dt: f32) {
	if distance <= 0 do return
	familiar.moving = true
	full_step := max(0.001, familiar.speed * dt)
	scale := clamp(distance / full_step, FAMILIAR_WALK_ANIM_SCALE_FLOOR, 1)
	familiar.anim_time += dt * scale
}

@(private = "file")
follow_player :: proc(run: ^Run, familiar: ^Familiar, dt: f32) {
	delta := run.player.pos - familiar.pos
	distance := math.hypot(delta.x, delta.y)
	follow_distance := FAMILIAR_FOLLOW_DISTANCE
	if familiar.kind == .Spirit_Beast {
		follow_distance = familiar.command == .Follow ? SPIRIT_BEAST_RETURN_DISTANCE : SPIRIT_BEAST_FOLLOW_DISTANCE
	}
	if distance <= follow_distance || distance <= 0.001 do return
	direction := delta / distance
	familiar.facing = direction
	familiar.move_dir = direction
	step := min(familiar.speed * dt, distance - follow_distance)
	moved := move_familiar(run, familiar, direction * step)
	advance_familiar_locomotion(familiar, moved, dt)
}

@(private = "file")
regenerate_familiar :: proc(familiar: ^Familiar, dt: f32) {
	if !familiar.unkillable || familiar.hp >= familiar.max_hp do return
	rate := max(1, familiar.max_hp / 8)
	familiar.regen_progress += f32(rate) * dt
	heal := int(familiar.regen_progress)
	if heal <= 0 do return
	familiar.regen_progress -= f32(heal)
	familiar.hp = min(familiar.max_hp, familiar.hp + heal)
}

@(private = "file")
familiar_attack :: proc(run: ^Run, familiar: ^Familiar, enemy: ^Enemy) {
	if !line_of_sight(&run.dungeon, familiar.pos.x, familiar.pos.y, enemy.pos.x, enemy.pos.y) do return
	player := &run.player
	familiar.attack_timer = familiar.attack_cooldown
	familiar.attack_anim_timer = FAMILIAR_ATTACK_ANIMATION_TIME
	damage := familiar.damage + rng_range(&run.combat_rng, 0, 3)
	if familiar.kind == .Spirit_Beast {
		// Beast-only bite riders read live (familiars.py:663-709): Pack Tactics
		// mauls snared prey, Primal Lord punishes elite/miniboss/boss targets,
		// Spirit Companion converts the bite to arcane, and Alpha shoves.
		if player_has_discipline(player, .Ranger_Pack_Tactics) && enemy.statuses[.Snared] > 0 {
			damage = int(math.round(f32(damage) * 1.25))
		}
		if player_has_discipline(player, .Ranger_Primal_Lord) && enemy.role != .Normal {
			damage = int(math.round(f32(damage) * 1.35))
		}
		bite_type: Damage_Type = player_has_discipline(player, .Ranger_Spirit_Companion) ? .Arcane : .Physical
		damage_enemy_typed(run, enemy, max(1, damage), bite_type)
		if player_has_discipline(player, .Ranger_Alpha) && enemy.hp > 0 && familiar.facing != {} {
			slide_move(&run.dungeon, &enemy.pos, familiar.facing * 0.22)
		}
	} else {
		// The reveler and recruited room companions strike physically;
		// class-summoned spirit hosts remain shadow damage.
		physical := familiar.kind == .Bar_Dancer || familiar.kind == .Soulless_Clanker || familiar.kind == .String
		strike_type: Damage_Type = physical ? .Physical : .Shadow
		_ = damage_enemy_direct(run, enemy, max(1, damage), strike_type)
		if familiar.kind == .Soulless_Clanker {
			sfx_emit(run,.Soulless_Clanker,familiar.pos,spatial=true,emitter_id=u64(familiar.entity_id))
		}
	}
	// Blood-bound familiars siphon health to the Acolyte on every hit; the
	// ladder reads live so later Blood purchases deepen an existing host's
	// drain (familiars.py:711-726).
	if familiar.lifesteal && player.hp < player.max_hp {
		if leech := acolyte_spell_leech(player); leech > 0 {
			heal := min(player.max_hp - player.hp, leech)
			player.hp += heal
			append(&run.numbers, Damage_Number{pos=player.pos, value=heal, kind=.Heal})
		}
	}

	// Adjacent foes retaliate on their own recovery clock. This is how the
	// otherwise-untargeted companion host naturally takes melee damage.
	if enemy.hp > 0 && enemy.cooldown <= 0 {
		familiar_take_damage(familiar, max(1, enemy.damage / 2))
		enemy.cooldown = enemy.attack_cd_s * 0.6
	}
}

// The simulation uses this fixed-step wrapper. Tests may call the `_dt`
// variant to exercise exact approach/follow boundaries without a frame loop.
tick_familiars :: proc(run: ^Run) {
	tick_familiars_dt(run, SIM_DT)
}

tick_familiars_dt :: proc(run: ^Run, dt: f32) {
	if len(run.familiars) == 0 do return
	for &familiar in run.familiars {
		familiar.prev_pos = familiar.pos
		familiar.attack_timer = max(0, familiar.attack_timer - dt)
		familiar.attack_anim_timer = max(0, familiar.attack_anim_timer - dt)
		familiar.pet_cooldown = max(0, familiar.pet_cooldown - dt)
		familiar.moving = false
		if familiar.hp <= 0 do continue

		// Being petted suspends perception, attacks, and movement entirely
		// (familiars.py:515-518).
		if familiar.pet_anim_timer > 0 {
			familiar.pet_anim_timer = max(0, familiar.pet_anim_timer - dt)
			continue
		}

		if familiar.kind == .Spirit_Beast && familiar.command == .Follow {
			follow_player(run, &familiar, dt)
			regenerate_familiar(&familiar, dt)
			continue
		}

		aggro := familiar.kind == .Spirit_Beast ? SPIRIT_BEAST_AGGRO_RANGE : FAMILIAR_AGGRO_RANGE
		best_distance_sq := aggro * aggro
		target: ^Enemy
		for &enemy in run.enemies {
			if enemy.hp <= 0 do continue
			delta := enemy.pos - familiar.pos
			distance_sq := delta.x * delta.x + delta.y * delta.y
			if distance_sq >= best_distance_sq do continue
			if !line_of_sight(&run.dungeon, familiar.pos.x, familiar.pos.y, enemy.pos.x, enemy.pos.y) do continue
			best_distance_sq = distance_sq
			target = &enemy
		}

		if target != nil {
			delta := target.pos - familiar.pos
			distance := math.sqrt(best_distance_sq)
			if distance <= familiar.attack_range {
				if distance > 0.001 do familiar.facing = delta / distance
				if familiar.attack_timer <= 0 do familiar_attack(run, &familiar, target)
			} else if distance > 0.001 {
				direction := delta / distance
				familiar.facing = direction
				familiar.move_dir = direction
				step := min(familiar.speed * dt, distance - familiar.attack_range)
				moved := move_familiar(run, &familiar, direction * step)
				advance_familiar_locomotion(&familiar, moved, dt)
			}
		} else {
			follow_player(run, &familiar, dt)
		}
		regenerate_familiar(&familiar, dt)
	}
	cull_dead_familiars(run)
}

// Recasting a class summon replaces the caster's own hosts. Recruited room
// companions and the Bar Dancer reward are not summon slots, so they survive.
clear_summoned_familiars :: proc(run: ^Run) {
	write := 0
	for read in 0 ..< len(run.familiars) {
		kind := run.familiars[read].kind
		if kind != .Bar_Dancer && kind != .Soulless_Clanker && kind != .String do continue
		if write != read do run.familiars[write] = run.familiars[read]
		write += 1
	}
	if write != len(run.familiars) do resize(&run.familiars, write)
}

// The all-bars-toasted summon (combat/familiars.py:192-241): idempotent, and
// callers gate it to depth 10 (arrival and the completing toast itself).
living_soulless_clanker :: proc(run: ^Run) -> ^Familiar {
	if run == nil do return nil
	for &familiar in run.familiars {
		if familiar.kind == .Soulless_Clanker && familiar.hp > 0 do return &familiar
	}
	return nil
}

soulless_clanker_join :: proc(run: ^Run, resident: ^Ambient_Room_Npc) -> bool {
	if run == nil || resident == nil || !resident.active || resident.kind != .Soulless_Clanker do return false
	if living_soulless_clanker(run) != nil do return false
	clanker := make_familiar(Familiar_Stats{
		hp=SOULLESS_CLANKER_HP,
		damage=SOULLESS_CLANKER_DAMAGE,
		speed=SOULLESS_CLANKER_SPEED,
		attack_cooldown=SOULLESS_CLANKER_ATTACK_COOLDOWN,
		count=1,
		kind=.Soulless_Clanker,
	},resident.pos,resident.motion.facing,0)
	run.next_familiar_id += 1
	if run.next_familiar_id == 0 do run.next_familiar_id = 1
	clanker.entity_id = run.next_familiar_id
	clanker.attack_anim_timer = FAMILIAR_ATTACK_ANIMATION_TIME
	append(&run.familiars,clanker)
	resident.active = false
	return true
}

living_string :: proc(run: ^Run) -> ^Familiar {
	if run == nil do return nil
	for &familiar in run.familiars {
		if familiar.kind == .String && familiar.hp > 0 do return &familiar
	}
	return nil
}

string_join :: proc(run: ^Run, resident: ^Ambient_Room_Npc) -> bool {
	if run == nil || resident == nil || !resident.active || resident.kind != .String do return false
	if living_string(run) != nil do return false
	guitarist := make_familiar(Familiar_Stats{
		hp=STRING_HP,
		damage=STRING_DAMAGE,
		speed=STRING_SPEED,
		attack_cooldown=STRING_ATTACK_COOLDOWN,
		count=1,
		kind=.String,
	},resident.pos,resident.motion.facing,0)
	run.next_familiar_id += 1
	if run.next_familiar_id == 0 do run.next_familiar_id = 1
	guitarist.entity_id = run.next_familiar_id
	guitarist.attack_anim_timer = FAMILIAR_ATTACK_ANIMATION_TIME
	append(&run.familiars,guitarist)
	resident.active = false
	return true
}

maybe_summon_bar_dancer :: proc(run: ^Run) -> bool {
	if run == nil do return false
	if run.bars_visited <= 0 || run.bars_toasted < run.bars_visited do return false
	for &familiar in run.familiars {
		if familiar.kind == .Bar_Dancer && familiar.hp > 0 do return false
	}
	pos, found := spirit_beast_spawn_position(run)
	if !found do pos = run.player.pos
	dancer := make_familiar(Familiar_Stats{
		hp = BAR_DANCER_HP,
		damage = BAR_DANCER_DAMAGE,
		speed = BAR_DANCER_SPEED,
		attack_cooldown = FAMILIAR_ATTACK_COOLDOWN,
		count = 1,
		kind = .Bar_Dancer,
		unkillable = true,
	}, pos, run.player.facing, 0)
	run.next_familiar_id += 1
	if run.next_familiar_id == 0 do run.next_familiar_id = 1
	dancer.entity_id = run.next_familiar_id
	append(&run.familiars, dancer)
	feel_emit(run, .Summon, pos, BAR_DANCER_ACCENT, 0.48, 0.72, phase=.Arrival, priority=.High)
	append(&run.numbers, Damage_Number{pos = run.player.pos, kind = .Text, text = "The Bar Dancer joins you: every bar toasted!"})
	return true
}

cull_dead_familiars :: proc(run: ^Run) {
	write := 0
	for read in 0 ..< len(run.familiars) {
		if run.familiars[read].hp <= 0 do continue
		if write != read do run.familiars[write] = run.familiars[read]
		write += 1
	}
	if write != len(run.familiars) do resize(&run.familiars, write)
}
