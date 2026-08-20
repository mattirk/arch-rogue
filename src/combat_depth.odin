package archrogue

// M8 combat depth: typed damage, statuses, equipment-derived action costs,
// the four player action slots, and the Rogue lure trap. This stays entirely
// raylib-free so every rule is exercised by the headless suite.

import "core:math"
import "core:math/linalg"

story_effect_clamped :: proc(
	run: ^Run,
	id: Story_Effect_Id,
	minimum, maximum: f32,
) -> f32 {
	if run == nil || !run.story_runtime.initialized do return 0
	return clamp(story_effect(&run.story, id), minimum, maximum)
}

story_player_damage_bonus :: proc(run: ^Run, spell := false) -> f32 {
	damage := story_effect_clamped(run, .Damage_Bonus, 0, .35)
	relic := story_effect_clamped(run, .Relic_Power, 0, .35)
	relic_weight: f32 = spell ? 1 : .6
	return min(f32(.55), damage + relic * relic_weight)
}

story_apply_player_damage :: proc(run: ^Run, damage: int, spell := false) -> int {
	bonus := story_player_damage_bonus(run, spell)
	if bonus <= 0 do return max(1, damage)
	return max(1, int(math.round(f32(damage) * (1 + bonus))))
}

story_apply_blood_price :: proc(run: ^Run, label := "Blood price") -> int {
	if run == nil || run.player.hp <= 1 do return 0
	price := story_effect_clamped(run, .Blood_Price, 0, .35)
	if price <= 0 do return 0
	cost := max(1, min(10, int(math.round(f32(run.player.max_hp) * (.015 + price * .18)))))
	actual := min(cost, run.player.hp - 1)
	if actual <= 0 do return 0
	run.player.hp -= actual
	run.story_runtime.blood_paid += actual
	append(&run.numbers, Damage_Number{pos = run.player.pos, value = actual, kind = .Damage_Taken})
	append(&run.numbers, Damage_Number{pos = run.player.pos, kind = .Text, text = label})
	return actual
}

AMBUSH_BELL_PLANT_RANGE :: 4.35
AMBUSH_BELL_ARM_TIME :: 0.34
AMBUSH_BELL_LIFETIME :: 6.0
AMBUSH_BELL_LURE_RADIUS :: 6.0
AMBUSH_BELL_TRIGGER_RADIUS :: 0.95
AMBUSH_BELL_DAMAGE_RADIUS :: 1.85

Ambush_Bell :: struct {
	entity_id:       u64,
	pos:             Vec2,
	lifetime:        f32,
	arm_timer:       f32,
	armed_announced: bool, // presentation latch; emits Bell_Arm exactly once
	lure_radius:     f32,
	trigger_radius:  f32,
	damage_radius:   f32,
	primary_damage:  int,
	splash_damage:   int,
	smoke_duration:  f32,
	// MX.3 tuning snapshot (ambush_bell.py:50-157): geometry, statuses, snares,
	// and refunds freeze at cast; only the live crit/damage chain reads the
	// build at detonation time.
	status:              Status_Kind,
	has_status:          bool,
	status_duration:     f32,
	primary_snare:       f32,
	splash_snare:        f32,
	expired_scale:       f32,
	kill_cooldown_floor: f32,
	kill_mana_refund:    int,
	facing_mult:         f32,
	facing_crit_bonus:   f32,
}

// Cast-time tuning table (ambush_bell.py:50-157). Every trap/shadow node
// stacks independently; the clamps are pygame's construction bounds.
ambush_bell_tuning :: proc(player: ^Player) -> (bell: Ambush_Bell, plant_range: f32) {
	bell = Ambush_Bell{
		lifetime = AMBUSH_BELL_LIFETIME,
		arm_timer = AMBUSH_BELL_ARM_TIME,
		lure_radius = AMBUSH_BELL_LURE_RADIUS,
		trigger_radius = AMBUSH_BELL_TRIGGER_RADIUS,
		damage_radius = AMBUSH_BELL_DAMAGE_RADIUS,
		smoke_duration = 0.52,
		expired_scale = 0.55,
		facing_mult = 1.18,
		facing_crit_bonus = 0.12,
	}
	plant_range = AMBUSH_BELL_PLANT_RANGE
	primary := 20 + player.level*3 +
		ARCHETYPES[player.archetype].melee_bonus + player.discipline_melee_bonus +
		max(0, (ARCHETYPES[player.archetype].spell_bonus + player.discipline_spell_bonus)/2)
	splash_ratio: f32 = 0.48

	if player_has_discipline(player, .Rogue_Smoke) do bell.smoke_duration += 0.22
	if player_has_discipline(player, .Rogue_Night_Veil) do bell.smoke_duration += 0.16
	if player_has_discipline(player, .Rogue_Umbral) do bell.smoke_duration += 0.18
	if player_has_skill_bonus(player, .Dash_Tempo) do bell.smoke_duration += 0.06
	// Foxstep's Ambush Bell potency (ambush_bell.py:132-133).
	if player_has_class_skill_bonus(player) && player.archetype == .Rogue do primary += 2

	if player_has_discipline(player, .Rogue_Trap_Craft) {
		bell.arm_timer -= 0.04
		bell.lifetime += 0.35
		bell.lure_radius += 0.35
		primary += 1
	}
	if player_has_discipline(player, .Rogue_Venom) {
		bell.status, bell.has_status = .Poisoned, true
		bell.status_duration = max(bell.status_duration, 2.2)
		primary += 2
	}
	if player_has_discipline(player, .Rogue_Venom_Trap) {
		bell.status, bell.has_status = .Poisoned, true
		bell.status_duration = max(bell.status_duration, 2.45)
		splash_ratio += 0.02
	}
	if player_has_discipline(player, .Rogue_Bear_Trap) {
		bell.trigger_radius += 0.05
		primary += 4
		bell.primary_snare = max(bell.primary_snare, 1.05)
		bell.facing_mult += 0.06
	}
	if player_has_discipline(player, .Rogue_Trap_Master) {
		bell.lure_radius += 0.45
		bell.damage_radius += 0.16
		primary += 3
		splash_ratio += 0.05
		bell.expired_scale += 0.08
		bell.facing_crit_bonus += 0.03
		if bell.has_status do bell.status_duration += 0.35
		if bell.primary_snare > 0 do bell.splash_snare = max(bell.splash_snare, 0.45)
	}
	if player_has_discipline(player, .Rogue_Ambush_Engineer) {
		bell.arm_timer -= 0.05
		plant_range += 0.20
		bell.lure_radius += 0.25
		bell.damage_radius += 0.14
		primary += 5
		splash_ratio += 0.03
		bell.expired_scale += 0.04
		bell.facing_mult += 0.04
		bell.facing_crit_bonus += 0.04
		bell.kill_cooldown_floor = 1.05
		bell.kill_mana_refund = 4
		if bell.has_status do bell.status_duration += 0.35
		if bell.primary_snare > 0 {
			bell.primary_snare += 0.25
			bell.splash_snare = max(bell.splash_snare, 0.70)
		}
	}

	bell.primary_damage = max(8, primary)
	plant_range = min(4.75, plant_range)
	bell.arm_timer = max(0.22, bell.arm_timer)
	bell.lifetime = min(7.0, bell.lifetime)
	bell.lure_radius = min(7.05, bell.lure_radius)
	bell.trigger_radius = min(1.08, bell.trigger_radius)
	bell.damage_radius = min(2.35, bell.damage_radius)
	bell.splash_damage = max(5, int(f32(bell.primary_damage) * splash_ratio))
	bell.smoke_duration = min(1.25, bell.smoke_duration)
	bell.expired_scale = min(0.72, bell.expired_scale)
	return bell, plant_range
}

player_has_cursed_equipment :: proc(player: ^Player) -> bool {
	return (player.has_weapon && player.weapon.cursed) || (player.has_armor && player.armor.cursed)
}

player_has_skill_bonus :: proc(player: ^Player, bonus: Skill_Bonus) -> bool {
	return (player.has_weapon && item_has_bonus(&player.weapon, bonus)) ||
		(player.has_armor && item_has_bonus(&player.armor, bonus))
}

// Slot-agnostic bespoke-hook dispatcher (equipment.py equipped_unique_effect).
player_has_unique_effect :: proc(player: ^Player, effect: Unique_Effect) -> bool {
	return (player.has_weapon && player.weapon.unique_effect == effect) ||
		(player.has_armor && player.armor.unique_effect == effect)
}

// The archetype's canonical class-skill gear bonus (class_skills.py
// bonus_term matching). MX.5 uniques fill the four formerly-empty classes.
player_has_class_skill_bonus :: proc(player: ^Player) -> bool {
	switch player.archetype {
	case .Warden: return player_has_skill_bonus(player, .Time_Skip_Ward)
	case .Rogue: return player_has_skill_bonus(player, .Ambush_Potency)
	case .Arcanist:
		return player_has_skill_bonus(player, .Nova_Ward) || player_has_skill_bonus(player, .Nova_Radius)
	case .Acolyte: return player_has_skill_bonus(player, .Spirit_Call_Ward)
	case .Ranger: return player_has_skill_bonus(player, .Spirit_Beast_Bond)
	}
	return false
}

player_has_bolt_bonus :: proc(player: ^Player) -> bool {
	return player_has_skill_bonus(player, .Bolt_Shard) || player_has_skill_bonus(player, .Bolt_Pierce)
}

player_attack_speed :: proc(player: ^Player) -> f32 {
	total: f32
	if player.has_weapon do total += player.weapon.attack_speed
	if player.has_armor do total += player.armor.attack_speed
	return clamp(total, -0.20, 0.35)
}

player_cast_speed :: proc(player: ^Player) -> f32 {
	total: f32
	if player.has_weapon do total += player.weapon.cast_speed
	if player.has_armor do total += player.armor.cast_speed
	return clamp(total, -0.20, 0.35)
}

player_melee_stamina_cost :: proc(player: ^Player) -> int {
	cost := player.archetype == .Rogue ? 9 : 12
	if player_has_discipline(player, .Rogue_Precision) do cost -= 2
	if player_has_skill_bonus(player, .Melee_Force) || player_has_skill_bonus(player, .Melee_Tempo) do cost -= 1
	if player_has_cursed_equipment(player) do cost += 1
	return max(5, cost)
}

player_melee_cooldown :: proc(player: ^Player) -> f32 {
	cooldown: f32 = player.archetype == .Rogue ? 0.30 : 0.36
	// Bulwark Training trades tempo for the wider cleave (costs.py:156).
	if player_has_discipline(player, .Warden_Bulwark) do cooldown += 0.02
	if player_has_skill_bonus(player, .Melee_Force) || player_has_skill_bonus(player, .Melee_Tempo) do cooldown -= 0.03
	return max(0.20, cooldown * (1 - player_attack_speed(player)))
}

player_bolt_mana_cost :: proc(player: ^Player) -> int {
	cost := (player.archetype == .Arcanist || player.archetype == .Ranger) ? 7 : 10
	if player.archetype == .Arcanist && player_has_discipline(player, .Arcanist_Charge) do cost -= 1
	if player_has_bolt_bonus(player) do cost -= 1
	if player_has_cursed_equipment(player) do cost += 1
	return max(4, cost)
}

player_bolt_cooldown :: proc(player: ^Player) -> f32 {
	cooldown: f32 = (player.archetype == .Arcanist || player.archetype == .Ranger) ? 0.38 : 0.48
	if player_has_bolt_bonus(player) do cooldown -= 0.04
	return max(0.22, cooldown * (1 - player_cast_speed(player)))
}

player_class_skill_mana_cost :: proc(player: ^Player) -> f32 {
	if player.archetype == .Ranger do return f32(player.max_mana) * 0.5
	cost: f32 = (player.archetype == .Arcanist || player.archetype == .Acolyte) ? 14 : 18
	if player_has_discipline(player, .Acolyte_Veil) do cost -= 2
	if player.archetype == .Warden && player_has_discipline(player, .Warden_Ward) do cost -= 1
	if player_has_class_skill_bonus(player) do cost -= 1
	if player_has_cursed_equipment(player) do cost += 2
	return max(f32(8), cost)
}

player_class_skill_cooldown :: proc(player: ^Player) -> f32 {
	if player.archetype == .Ranger do return 60
	cooldown: f32 = player.archetype == .Arcanist ? 2.65 : 3.2
	if player.archetype == .Warden && player_has_discipline(player, .Warden_Ward) do cooldown -= 0.3
	if player_has_class_skill_bonus(player) do cooldown -= 0.18
	return max(1.85, cooldown * (1 - player_cast_speed(player) * 0.75))
}

player_dash_stamina_cost :: proc(player: ^Player) -> int {
	cost := (player.archetype == .Rogue || player.archetype == .Ranger) ? 12 : 18
	if player_has_discipline(player, .Rogue_Smoke) do cost -= 2
	if player_has_skill_bonus(player, .Dash_Tempo) || player_has_skill_bonus(player, .Dash_Guard) do cost -= 2
	return max(8, cost)
}

player_dash_cooldown :: proc(player: ^Player) -> f32 {
	cooldown: f32 = player.archetype == .Ranger ? 0.62 : 0.85
	if player_has_skill_bonus(player, .Dash_Tempo) do cooldown -= 0.08
	return max(0.48, cooldown)
}

player_weapon_damage_type :: proc(player: ^Player) -> Damage_Type {
	if player.has_weapon do return player.weapon.typed ? player.weapon.damage_type : .Physical
	switch player.archetype {
	case .Arcanist: return .Arcane
	case .Acolyte: return .Shadow
	case .Warden, .Rogue, .Ranger: return .Physical
	}
	return .Physical
}

player_bolt_damage_type :: proc(player: ^Player) -> Damage_Type {
	if player.has_weapon && player.weapon.typed {
		t := player.weapon.damage_type
		if t == .Fire || t == .Frost || t == .Poison || t == .Arcane || t == .Shadow do return t
	}
	switch player.archetype {
	case .Warden: return .Holy
	case .Arcanist: return .Arcane
	case .Acolyte: return .Shadow
	case .Rogue: return player_has_discipline(player, .Rogue_Venom) ? .Poison : .Physical
	case .Ranger: return .Physical
	}
	return .Physical
}

player_typed_resistance :: proc(player: ^Player, damage_type: Damage_Type) -> f32 {
	resistance: f32
	if player.has_armor {
		armor := &player.armor
		resistance += f32(item_defense(armor^)) * 0.006
		armor_type := armor.typed ? armor.damage_type : Damage_Type.Physical
		if armor_type == damage_type do resistance += 0.08
		for i in 0 ..< armor.affix_count {
			#partial switch armor.affixes[i].kind {
			case .Grounded:
				if damage_type == .Arcane do resistance += 0.12
			case .Sealed:
				if damage_type == .Shadow || damage_type == .Poison do resistance += 0.10
			}
		}
	}
	if player.statuses[.Aegis] > 0 do resistance += 0.24
	// Temporal Aegis: reduced damage while Time Skip runs (player.py:88-93).
	if player.archetype == .Warden && player.time_skip_timer > 0 &&
		player_has_discipline(player, .Warden_Unyielding) {
		resistance += 0.20
	}
	// MX.5 unique wards (player.py:78-82 + damage_types.py PLAYER_RESIST_UNIQUES).
	if player_has_unique_effect(player, .Oathwall_Aegis) do resistance += 0.06
	if damage_type == .Frost && player_has_unique_effect(player, .Glacial_Ward) do resistance += 0.15
	return clamp(resistance, 0, 0.45)
}

enemy_damage_after_resistance :: proc(enemy: ^Enemy, raw: int, damage_type: Damage_Type) -> int {
	resistance := clamp(enemy.resistances[damage_type], -0.35, 0.70)
	damage := max(1, int(math.round(f32(raw) * (1 - resistance))))
	if damage_type == .Arcane && enemy.statuses[.Chilled] > 0 {
		damage = max(1, int(math.round(f32(damage) * 1.18)))
	}
	return damage
}

enemy_apply_status :: proc(enemy: ^Enemy, status: Status_Kind, duration: f32) {
	if enemy == nil || enemy.hp <= 0 || duration <= 0 do return
	adjusted := duration
	if status == .Poisoned && enemy.resistances[.Poison] >= 0.55 do adjusted *= 0.55
	enemy.statuses[status] = max(enemy.statuses[status], adjusted)
	if status == .Poisoned && enemy.poison_tick <= 0 do enemy.poison_tick = 1
	if status == .Stunned && enemy.ai == .Windup {
		enemy.ai = .Chase
		enemy.windup = 0
		enemy.pending_ability = PENDING_BASE_ATTACK
	}
}

player_apply_status :: proc(player: ^Player, status: Status_Kind, duration: f32) {
	if player == nil || duration <= 0 do return
	player.statuses[status] = max(player.statuses[status], duration)
	if status == .Poisoned && player.poison_tick <= 0 do player.poison_tick = 1
}

enemy_status_move_factor :: proc(enemy: ^Enemy) -> f32 {
	factor: f32 = 1
	for status in Status_Kind {
		if enemy.statuses[status] > 0 do factor *= STATUS_DEFS[status].move_factor
	}
	return factor
}

// Stutter Step deepens the slow; the factor reads live every tick while the
// duration is snapshotted at cast (costs.py:226-256).
time_skip_factor :: proc(player: ^Player) -> f32 {
	return player_has_discipline(player, .Warden_Stone_Aegis) ? 0.3 : TIME_SKIP_FACTOR
}

time_skip_duration :: proc(player: ^Player) -> f32 {
	duration: f32 = TIME_SKIP_DURATION
	if player_has_discipline(player, .Warden_Ward) do duration += 0.5
	if player_has_discipline(player, .Warden_Bulwark_Wave) do duration += 1.0
	return duration
}

enemy_sim_dt :: proc(run: ^Run) -> f32 {
	remaining := run.player.time_skip_timer
	if remaining <= 0 do return SIM_DT
	factor := time_skip_factor(&run.player)
	scale := factor
	if remaining < SIM_DT {
		scale = 1 - (1 - factor) * remaining / SIM_DT
	}
	return SIM_DT * scale
}

tick_combat_statuses :: proc(run: ^Run) {
	player := &run.player
	if player.statuses[.Poisoned] > 0 {
		player.poison_tick -= SIM_DT
		if player.poison_tick <= 0 {
			damage := max(1, run.depth / 3 + 1)
			player.hp -= damage
			run.last_damage_source="poison"
			mark_player_hit_flash(player,damage)
			append(&run.numbers, Damage_Number{pos=player.pos, value=damage, kind=.Damage_Taken, damage_type=.Poison})
			feel_emit_player_hurt(run,damage)
			player.poison_tick += 1
		}
	}
	for status in Status_Kind do player.statuses[status] = max(0, player.statuses[status] - SIM_DT)
	if player.statuses[.Poisoned] <= 0 do player.poison_tick = 0

	for &enemy in run.enemies {
		if enemy.hp <= 0 do continue
		if enemy.statuses[.Poisoned] > 0 {
			enemy.poison_tick -= SIM_DT
			if enemy.poison_tick <= 0 {
				damage := max(1, int(2 + f32(player.level) * 0.35))
				enemy.hp -= damage
				mark_enemy_hit_flash(&enemy)
				append(&run.numbers, Damage_Number{pos=enemy.pos, value=damage, kind=.Damage_Dealt, damage_type=.Poison})
				feel_emit_enemy_hit(run,&enemy,.Poison)
				enemy.poison_tick += 1
			}
		}
		for status in Status_Kind do enemy.statuses[status] = max(0, enemy.statuses[status] - SIM_DT)
		if enemy.statuses[.Poisoned] <= 0 do enemy.poison_tick = 0
	}
}

// Beastmark: already-snared prey takes more from every mitigated player-side
// hit, Spirit Beast bites included (statuses.py:114-117).
beastmark_snare_amp :: proc(run: ^Run, enemy: ^Enemy, damage: int) -> int {
	if !player_has_discipline(&run.player, .Ranger_Beastmark) || enemy.statuses[.Snared] <= 0 do return damage
	return int(math.round(f32(damage) * 1.22))
}

damage_enemy_typed :: proc(run: ^Run, enemy: ^Enemy, raw: int, damage_type: Damage_Type) -> int {
	if enemy == nil || enemy.hp <= 0 do return 0
	damage := enemy_damage_after_resistance(enemy, max(1, raw), damage_type)
	damage = beastmark_snare_amp(run, enemy, damage)
	enemy.hp -= damage
	mark_enemy_hit_flash(enemy)
	alert_enemy(run, enemy, run.player.pos) // damage engages and wakes the pack
	append(&run.sfx, Sfx_Kind.Hit)
	append(&run.numbers, Damage_Number{pos=enemy.pos, value=damage, kind=.Damage_Dealt, damage_type=damage_type})
	feel_emit_enemy_hit(run,enemy,damage_type)
	return damage
}

damage_enemy_direct :: proc(run: ^Run, enemy: ^Enemy, raw: int, damage_type: Damage_Type) -> int {
	if enemy == nil || enemy.hp <= 0 do return 0
	damage := max(1, raw)
	enemy.hp -= damage
	mark_enemy_hit_flash(enemy)
	alert_enemy(run, enemy, run.player.pos) // damage engages and wakes the pack
	append(&run.sfx, Sfx_Kind.Hit)
	append(&run.numbers, Damage_Number{pos=enemy.pos, value=damage, kind=.Damage_Dealt, damage_type=damage_type})
	feel_emit_enemy_hit(run,enemy,damage_type)
	return damage
}

damage_player_typed :: proc(run: ^Run, raw: int, damage_type: Damage_Type, melee := false, attacker: ^Enemy = nil, evadable := true, source_id := "") -> int {
	player := &run.player
	if player.hp <= 0 do return 0
	evade: f32
	// Trap damage cannot be evaded (player.py:118 source=="trap").
	if evadable && player.archetype == .Rogue {
		evade = player_has_discipline(player, .Rogue_Smoke) ? 0.18 : 0.12
		if player.statuses[.Smoke] > 0 do evade += 0.22
	}
	if evade > 0 && rng_chance(&run.combat_rng, evade) {
		append(&run.numbers, Damage_Number{pos=player.pos, kind=.Text, text="Evade"})
		return 0
	}
	warden_melee_guard := melee && player.archetype == .Warden ? 2 : 0
	damage := max(1, raw - player_armor(player) - warden_melee_guard)
	damage = max(1, int(math.round(f32(damage) * (1 - player_typed_resistance(player, damage_type)))))
	if melee && player_has_discipline(player, .Warden_Riposte) do damage = max(1, damage - 2)
	if player.archetype == .Acolyte && player.mana >= 4 {
		player.mana -= 4
		shield := player_has_discipline(player, .Acolyte_Veil) ? 5 : 3
		damage = max(1, damage - shield)
	}
	if resist := story_effect_clamped(run, .Damage_Resist, 0, .35); resist > 0 {
		damage = max(1, int(math.round(f32(damage) * (1 - resist))))
	}
	if player_has_cursed_equipment(player) && (damage_type == .Shadow || damage_type == .Poison) do damage += 1
	player.hp -= damage
	if source_id!="" do run.last_damage_source=source_id
	else if attacker!=nil do run.last_damage_source=persistence_enemy_source_id(attacker)
	else do run.last_damage_source="hostile_magic"
	mark_player_hit_flash(player,damage)
	append(&run.sfx, Sfx_Kind.Hurt)
	append(&run.numbers, Damage_Number{pos=player.pos, value=damage, kind=.Damage_Taken, damage_type=damage_type})
	feel_emit_player_hurt(run,damage)
	// Riposte Guard: a taken melee hit answers with a holy counterattack, and
	// with Aegis Discipline the counter also stuns (player.py:158-180).
	if melee && attacker != nil && attacker.hp > 0 && player_has_discipline(player, .Warden_Riposte) {
		counter := max(2, player.level + ARCHETYPES[player.archetype].armor_bonus + player.discipline_armor_bonus)
		// Reckoner's Brand deepens the answer (player.py:166-167).
		if player_has_unique_effect(player, .Counter_Smite) do counter += max(3, player.level / 2 + 2)
		_ = damage_enemy_typed(run, attacker, counter, .Holy)
		if player_has_discipline(player, .Warden_Aegis) do enemy_apply_status(attacker, .Stunned, 0.35)
		if dir := linalg.normalize0(attacker.pos - player.pos); dir != {} {
			enemy_start_knockback(run, attacker, dir * KNOCKBACK_SPEED)
		}
	}
	// Melee retaliation statuses from the unique armors (player.py:186-192).
	if melee && attacker != nil && attacker.hp > 0 && damage > 0 {
		if player_has_unique_effect(player, .Glacial_Ward) do enemy_apply_status(attacker, .Chilled, 1.2)
		if player_has_unique_effect(player, .Pack_Pursuit) do enemy_apply_status(attacker, .Snared, 1.0)
	}
	return damage
}

roll_equipped_proc :: proc(run: ^Run, effect: Proc_Effect) -> bool {
	items := [2]^Item{run.player.has_weapon ? &run.player.weapon : nil, run.player.has_armor ? &run.player.armor : nil}
	for item in items {
		if !item_has_proc_effect(item, effect) do continue
		if item.proc_chance <= 0 || item.proc_chance >= 1 do return true
		if rng_chance(&run.combat_rng, item.proc_chance) do return true
	}
	return false
}

@(private = "file")
try_chain_proc :: proc(run: ^Run, source: ^Enemy, damage: int) {
	best: ^Enemy
	best_distance := f32(3.75)
	for &candidate in run.enemies {
		if candidate.hp <= 0 || &candidate == source do continue
		delta := candidate.pos - source.pos
		distance := math.hypot(delta.x, delta.y)
		if distance >= best_distance do continue
		if !line_of_sight(&run.dungeon, source.pos.x, source.pos.y, candidate.pos.x, candidate.pos.y) do continue
		best, best_distance = &candidate, distance
	}
	if best != nil do _ = damage_enemy_direct(run, best, max(1, damage / 3), .Arcane)
}

player_damage_enemy :: proc(
	run: ^Run,
	enemy: ^Enemy,
	raw: int,
	damage_type: Damage_Type,
	status := Status_Kind.Poisoned,
	has_status := false,
	status_duration: f32 = 0,
) -> int {
	if enemy == nil || enemy.hp <= 0 do return 0
	damage := enemy_damage_after_resistance(enemy, max(1, raw), damage_type)
	damage = beastmark_snare_amp(run, enemy, damage)
	proc_damage := 0
	// Emberbrand/Frostwake guarantee their procs (damage.py:87-99); the roll
	// short-circuits behind the unique check.
	if (player_has_unique_effect(&run.player, .Embers_On_Hit) || roll_equipped_proc(run, .Ignite)) && damage_type != .Fire {
		proc_damage += max(1, run.player.level / 2 + 2)
		enemy_apply_status(enemy, .Burning, 1.1)
	}
	if player_has_unique_effect(&run.player, .Chill_On_Hit) || roll_equipped_proc(run, .Chill) || (has_status && status == .Chilled) {
		enemy_apply_status(enemy, .Chilled, max(status_duration, f32(1)))
	}
	if roll_equipped_proc(run, .Poison) || roll_equipped_proc(run, .Bleed) {
		enemy_apply_status(enemy, .Poisoned, max(status_duration, f32(1.4)))
	}
	if has_status && status != .Chilled do enemy_apply_status(enemy, status, status_duration)
	if enemy.statuses[.Burning] > 0 && damage_type == .Fire do proc_damage += max(1, run.player.level / 3 + 1)
	damage = max(1, damage + proc_damage)
	enemy.hp -= damage
	mark_enemy_hit_flash(enemy)
	alert_enemy(run, enemy, run.player.pos) // damage engages and wakes the pack
	append(&run.sfx, Sfx_Kind.Hit)
	append(&run.numbers, Damage_Number{pos=enemy.pos, value=damage, kind=.Damage_Dealt, damage_type=damage_type})
	feel_emit_enemy_hit(run,enemy,damage_type)
	if roll_equipped_proc(run, .Chain) do try_chain_proc(run, enemy, damage)
	if ratio := player_lifesteal(&run.player); ratio > 0 && run.player.hp < run.player.max_hp {
		heal := min(run.player.max_hp - run.player.hp, max(1, int(f32(damage) * ratio)))
		run.player.hp += heal
		append(&run.numbers, Damage_Number{pos=run.player.pos, value=heal, kind=.Heal})
	}
	return damage
}

rogue_crit_profile :: proc(rank: u8) -> (chance, multiplier: f32) {
	switch clamp(int(rank), 0, 5) {
	case 1: return .15, 1.60
	case 2: return .20, 1.75
	case 3: return .28, 1.95
	case 4: return .34, 2.10
	case 5: return .40, 2.25
	case: return 0, 1
	}
}

rogue_crit_poison_duration :: proc(rank: u8) -> f32 {
	return rank >= 2 ? 2.2 : 1.2
}

roll_rogue_crit :: proc(run: ^Run, chance_scale: f32 = 1) -> (critical: bool, multiplier: f32) {
	if run.player.archetype != .Rogue do return false, 1
	chance, mult := rogue_crit_profile(player_precision_rank(&run.player))
	if chance <= 0 do return false, 1
	return rng_chance(&run.combat_rng, min(1, chance * chance_scale)), mult
}

// Nightglass Daggers: a missed crit re-rolls at 30% for x1.80 while Smoke
// holds (attacks.py:102-114). The roll is consumed only when eligible.
maybe_smoke_crit :: proc(run: ^Run, critical: bool, multiplier: f32) -> (bool, f32) {
	if critical do return critical, multiplier
	if !player_has_unique_effect(&run.player, .Smoke_Crits) do return critical, multiplier
	if run.player.statuses[.Smoke] <= 0 do return critical, multiplier
	if !rng_chance(&run.combat_rng, 0.30) do return critical, multiplier
	return true, 1.80
}

// Dedup-insert a symmetric ±angle pair into a sorted bolt fan (attacks.py's
// sorted-set merge, kept within the five-slot guard's 8-wide buffer).
merge_fan_pair :: proc(angles: ^[8]f32, count: ^int, spread: f32) {
	merge := [2]f32{-spread, spread}
	outer: for extra in merge {
		if count^ >= len(angles) do return
		for i in 0 ..< count^ do if abs(angles[i] - extra) < 1e-4 do continue outer
		insert := count^
		for i in 0 ..< count^ do if extra < angles[i] {insert = i; break}
		for j := count^; j > insert; j -= 1 do angles[j] = angles[j - 1]
		angles[insert] = extra
		count^ += 1
	}
}

bighit_charging :: proc(player: ^Player) -> bool {return player.bighit_charge > 0}

bighit_committed :: proc(player: ^Player) -> bool {
	if !bighit_charging(player) do return false
	return 1 - player.bighit_charge / BIGHIT_CHARGE_TIME >= BIGHIT_COMMIT_FRACTION
}

player_big_hit_begin :: proc(run: ^Run, aim: Vec2) -> bool {
	player := &run.player
	if bighit_charging(player) || player.bighit_timer > 0 || player.stamina < BIGHIT_STAMINA_COST do return false
	if aim != {} do player.facing = linalg.normalize0(aim)
	player.stamina -= BIGHIT_STAMINA_COST
	player.bighit_charge = BIGHIT_CHARGE_TIME
	player.swing_timer = BIGHIT_CHARGE_TIME
	player_start_visual_action(player,.Cast,PLAYER_BIG_HIT_CAST_SECONDS)
	return true
}

player_big_hit_release :: proc(player: ^Player) -> bool {
	if !bighit_charging(player) || bighit_committed(player) do return false
	player.bighit_charge = 0
	player.bighit_timer = max(player.bighit_timer, f32(BIGHIT_CANCEL_COOLDOWN))
	player.swing_timer = 0
	if player.visual_action == .Cast do player_clear_visual_action(player)
	return true
}

@(private = "file")
enemy_in_arc :: proc(run: ^Run, enemy: ^Enemy, facing: Vec2, reach: f32) -> (matches: bool, distance: f32, direction: Vec2) {
	to := enemy.pos - run.player.pos
	distance = math.hypot(to.x, to.y)
	extra := max(0, enemy_hit_radius(enemy) - ENEMY_HIT_RADIUS)
	if distance > reach + extra do return false, distance, {}
	direction = distance < 0.001 ? facing : to / distance
	if linalg.dot(direction, facing) <= PLAYER_MELEE_ARC_DOT do return false, distance, direction
	if !line_of_sight(&run.dungeon, run.player.pos.x, run.player.pos.y, enemy.pos.x, enemy.pos.y) do return false, distance, direction
	return true, distance, direction
}

player_big_hit_fire :: proc(run: ^Run) {
	player := &run.player
	player.bighit_charge = 0
	player.bighit_timer = BIGHIT_COOLDOWN
	player.swing_timer = ATTACK_SWING_SECONDS
	player_start_visual_action(player,.Attack,PLAYER_BIG_HIT_ATTACK_SECONDS)
	facing := linalg.normalize0(player.facing)
	primary: ^Enemy
	primary_distance := max(f32)
	for &enemy in run.enemies {
		if enemy.hp <= 0 do continue
		matches, distance, _ := enemy_in_arc(run, &enemy, facing, PLAYER_MELEE_RANGE)
		if matches && distance < primary_distance {
			primary, primary_distance = &enemy, distance
		}
	}
	strike_pos := player.pos+facing*.9
	if primary != nil do strike_pos=(player.pos+primary.pos)*.5
	feel_emit_slash(run,strike_pos,player.facing,heavy=true)
	append(&run.sfx,Sfx_Kind.Swing)
	total := 0
	for &enemy in run.enemies {
		if enemy.hp <= 0 do continue
		matches, _, direction := enemy_in_arc(run, &enemy, facing, PLAYER_MELEE_RANGE)
		if !matches do continue
		damage := int(f32(player_melee_damage(player)) * BIGHIT_DAMAGE_MULT) + rng_range(&run.combat_rng, -4, 7)
		if player_has_skill_bonus(player, .Melee_Force) || player_has_skill_bonus(player, .Melee_Tempo) do damage += 2
		if &enemy != primary && player.archetype != .Warden do damage = max(1, int(f32(damage) * BIGHIT_CLEAVE_FACTOR))
		critical, multiplier := roll_rogue_crit(run, 2)
		if critical {
			damage = int(f32(damage) * multiplier)
			append(&run.numbers, Damage_Number{pos=enemy.pos, kind=.Text, text="Critical"})
		}
		damage = story_apply_player_damage(run, damage)
		_ = player_damage_enemy(run, &enemy, damage, player_weapon_damage_type(player))
		total += damage
		throw_tiles: f32 = player.archetype == .Ranger ? BIGHIT_THROW_TILES_RANGER : BIGHIT_THROW_TILES
		if enemy.big do throw_tiles *= BIGHIT_BOSS_THROW_FACTOR
		if &enemy == primary || player.archetype == .Warden {
			enemy_start_knockback(run, &enemy, direction * (throw_tiles * 10))
			if player.archetype == .Arcanist do enemy_apply_status(&enemy, .Chilled, 2.5)
			if player.archetype == .Ranger && &enemy == primary do enemy_apply_status(&enemy, .Snared, 1.75)
		}
	}
	if player.archetype == .Acolyte && total > 0 {
		heal := min(player.max_hp - player.hp, max(1, total / 4))
		player.hp += heal
		if heal > 0 do append(&run.numbers, Damage_Number{pos=player.pos, value=heal, kind=.Heal})
	}
}

tick_big_hit :: proc(run: ^Run) {
	player := &run.player
	if player.bighit_charge <= 0 do return
	player.bighit_charge -= SIM_DT
	if player.bighit_charge <= 0 do player_big_hit_fire(run)
}

player_cast_bolt :: proc(run: ^Run, aim: Vec2) -> bool {
	player := &run.player
	if bighit_charging(player) do return false
	cost := player_bolt_mana_cost(player)
	if player.bolt_timer > 0 || player.mana < f32(cost) do return false
	if aim != {} do player.facing = linalg.normalize0(aim)
	player.mana -= f32(cost)
	player.bolt_timer = player_bolt_cooldown(player)
	player.swing_timer = .24
	player_start_visual_action(player,.Cast,PLAYER_BOLT_ACTION_SECONDS)
	feel_emit(
		run,.Cast,player.pos,ARCHETYPE_SKILL_COLORS[player.archetype],.28,.34,
		direction=player.facing,style=feel_style_for_archetype(player.archetype),priority=.High,
	)
	damage := player_spell_damage(player, BOLT_BASE_DAMAGE)
	if player_has_bolt_bonus(player) do damage += 2
	if player.archetype == .Acolyte do damage += max(0, player.max_hp - player.hp) / 12
	damage = story_apply_player_damage(run, damage, spell = true)
	_ = story_apply_blood_price(run, "Bolt blood price")
	type := player_bolt_damage_type(player)

	// Fan tiers are class-authored (attacks.py:445-471); the equipment fan
	// merges its own pair into whatever the disciplines built, capped like
	// pygame's five-slot guard, dedup'd and kept sorted.
	angles: [8]f32
	count := 1
	if player.archetype == .Ranger {
		switch {
		case player_has_discipline(player, .Ranger_Storm_Volley):
			angles, count = {-0.28, -0.12, 0, 0.12, 0.28, 0, 0, 0}, 5
		case player_has_discipline(player, .Ranger_Rapid):
			angles, count = {-0.20, -0.06, 0.06, 0.20, 0, 0, 0, 0}, 4
		case player_has_discipline(player, .Ranger_Volley):
			angles, count = {-0.16, 0, 0.16, 0, 0, 0, 0, 0}, 3
		}
	} else if player.archetype == .Arcanist {
		switch {
		case player_has_discipline(player, .Arcanist_Overload):
			angles, count = {-0.12, 0, 0.12, 0, 0, 0, 0, 0}, 3
		case player_has_discipline(player, .Arcanist_Splinter):
			angles, count = {-0.06, 0.06, 0, 0, 0, 0, 0, 0}, 2
		}
	}
	if player_has_bolt_bonus(player) && count < 5 {
		merge_fan_pair(&angles, &count, 0.18)
	}
	// Named-unique fans widen further (attacks.py:466-469): Splinter Star's
	// tight storm pair and Skyfang's sky volley.
	if player_has_unique_effect(player, .Splinter_Storm) && count < 5 {
		merge_fan_pair(&angles, &count, 0.10)
	}
	if player_has_unique_effect(player, .Sky_Volley) && count < 5 {
		merge_fan_pair(&angles, &count, 0.22)
	}

	pierce := 0
	if player.archetype == .Arcanist {
		if player_has_discipline(player, .Arcanist_Pierce) do pierce = 2
		else if player_has_discipline(player, .Arcanist_Overload) do pierce = 1
	}
	if player.archetype == .Ranger && player_has_discipline(player, .Ranger_Piercing_Volley) do pierce = max(pierce, 1)
	if player_has_skill_bonus(player, .Bolt_Pierce) do pierce = max(pierce, 1)

	homing: f32
	if player_has_discipline(player, .Arcanist_Arc_Tyrant) do homing = 0.85
	if player_has_discipline(player, .Ranger_Sky_Quiver) do homing = 0.75

	// Single status rider per cast (attacks.py:487-503).
	status: Status_Kind
	has_status := false
	duration: f32
	if type == .Poison || player_has_discipline(player, .Rogue_Venom) {
		status, has_status, duration = .Poisoned, true, 2.0
	} else if type == .Frost {
		status, has_status, duration = .Chilled, true, 1.4
	} else if player_has_discipline(player, .Acolyte_Gravebind) {
		status, has_status, duration = .Bound, true, 1.2
	} else if player_has_discipline(player, .Ranger_Snare) {
		status, has_status, duration = .Snared, true, 1.1
	}

	ttl: f32 = player_has_discipline(player, .Arcanist_Splinter) ? 1.55 : BOLT_TTL
	storm_chain := player.archetype == .Arcanist &&
		(player_has_discipline(player, .Arcanist_Chain_Lightning) ||
			player_has_discipline(player, .Arcanist_Tempest) ||
			player_has_discipline(player, .Arcanist_Storm_Caller) ||
			player_has_discipline(player, .Arcanist_World_Storm))
	if storm_chain do run.storm_cast_counter += 1

	for i in 0 ..< count {
		angle := angles[i]
		dir := vec_rotate(player.facing, angle)
		append(&run.projectiles, Projectile{
			pos=player.pos, prev_pos=player.pos, vel=dir*BOLT_SPEED,
			damage=abs(angle) <= 0.001 ? damage : max(1, damage-4), damage_type=type,
			status=status, has_status=has_status, status_duration=duration,
			pierce=pierce, homing=homing,
			storm_chain=storm_chain, storm_cast=run.storm_cast_counter,
			visual=projectile_visual_for_archetype(player.archetype),
			from_player=true, ttl=ttl, color=DAMAGE_TYPE_COLORS[type],
		})
	}
	append(&run.sfx, Sfx_Kind.Bolt)
	return true
}

player_dash :: proc(run: ^Run, aim: Vec2) -> bool {
	player := &run.player
	if bighit_charging(player) {
		if bighit_committed(player) do return false
		_ = player_big_hit_release(player)
	}
	cost := player_dash_stamina_cost(player)
	if player.dash_timer > 0 || player.stamina < f32(cost) do return false
	if aim != {} do player.facing = linalg.normalize0(aim)
	player.stamina -= f32(cost)
	player.dash_timer = player_dash_cooldown(player)
	start := player.pos
	steps := player.archetype == .Ranger ? 11 : 8
	if player_has_discipline(player, .Rogue_Smoke) do steps += 2
	if player_has_skill_bonus(player, .Dash_Tempo) || player_has_skill_bonus(player, .Dash_Guard) do steps += 1
	for _ in 0 ..< steps do slide_move(&run.dungeon, &player.pos, player.facing * 0.20, block_stairs=true)
	resolve_player_enemy_contacts(run) // a dash may pass through but never land inside a body
	player.prev_pos = player.pos
	player.melee_commit_timer = 0 // dashing cancels a swing's plant window
	player.swing_timer = .22
	player_start_visual_action(player,.Dash,PLAYER_DASH_ACTION_SECONDS)
	style := feel_style_for_archetype(player.archetype)
	color := ARCHETYPE_SKILL_COLORS[player.archetype]
	feel_emit(run,.Dash,start,color,.24,.34,player.facing,phase=.Start,style=style,priority=.High)
	feel_emit(run,.Dash,player.pos,color,.26,.42,player.facing,phase=.End,style=style,priority=.High)
	// Dash riders (mobility.py:82-95): Shadow Dash smoke, Guard Step's brief
	// Aegis hardening, and the Vault stamina/Multishot refund.
	if player.archetype == .Rogue && player_has_discipline(player, .Rogue_Smoke) {
		player_apply_status(player, .Smoke, 0.9)
	}
	// Foxstep Leathers vanish regardless of class (mobility.py:84-85).
	if player_has_unique_effect(player, .Vanish_On_Dash) {
		player_apply_status(player, .Smoke, 0.8)
	}
	if player.archetype == .Warden && (player_has_discipline(player, .Warden_Aegis) ||
		player_has_skill_bonus(player, .Dash_Guard)) {
		player_apply_status(player, .Aegis, 0.85)
	}
	if player_has_discipline(player, .Ranger_Beastmark) {
		player.stamina = min(f32(player.max_stamina), player.stamina + 8)
		player.bolt_timer = min(player.bolt_timer, 0.12)
	}
	return true
}

@(private = "file")
cast_time_skip :: proc(run: ^Run) -> bool {
	player := &run.player
	cost := player_class_skill_mana_cost(player)
	if player.class_skill_timer > 0 || player.mana < cost do return false
	player.mana -= cost
	player.class_skill_timer = player_class_skill_cooldown(player)
	player.time_skip_timer = time_skip_duration(player)
	player_start_visual_action(player,.Cast,PLAYER_CLASS_ACTION_SECONDS)
	feel_emit(
		run,.Time_Skip,player.pos,ARCHETYPE_SKILL_COLORS[.Warden],.62,3.2,
		direction=player.facing,style=.Warden,priority=.High,
	)
	// The Time Skip cast pulse briefly stuns and delays nearby foes
	// (attacks.py:697-717): no damage, no procs, just the stagger.
	if player_has_discipline(player, .Warden_Bulwark_Wave) {
		for &enemy in run.enemies {
			if enemy.hp <= 0 do continue
			delta := enemy.pos - player.pos
			if math.hypot(delta.x, delta.y) > 2.6 do continue
			if !line_of_sight(&run.dungeon, player.pos.x, player.pos.y, enemy.pos.x, enemy.pos.y) do continue
			enemy_apply_status(&enemy, .Stunned, 0.35)
			enemy.cooldown = max(enemy.cooldown, 0.45)
		}
	}
	append(&run.numbers, Damage_Number{pos=player.pos, kind=.Text, text="Time Skip"})
	return true
}

// Every Nova node widens the ring (attacks.py:549-564); a completed Nova path
// alongside a second mastered path lets the cast engulf the whole room.
nova_radius :: proc(player: ^Player) -> f32 {
	radius := NOVA_BASE_RADIUS + 0.55 * f32(discipline_path_rank(player, .Arcanist_Nova))
	if player_has_class_skill_bonus(player) do radius += .25
	// Blizzard Mantle's "Nova radius" matches both queries (attacks.py:560-563).
	if player_has_skill_bonus(player, .Nova_Radius) do radius += .35
	return radius
}

nova_engulfs_room :: proc(player: ^Player) -> bool {
	return discipline_path_rank(player, .Arcanist_Nova) >= DISCIPLINE_DEGREES &&
		discipline_completed_path_count(player) >= MAX_COMMITTED_DISCIPLINE_PATHS
}

@(private = "file")
cast_nova :: proc(run: ^Run) -> bool {
	player := &run.player
	cost := player_class_skill_mana_cost(player)
	if player.class_skill_timer > 0 || player.mana < cost do return false
	player.mana -= cost
	player.class_skill_timer = player_class_skill_cooldown(player)
	player_start_visual_action(player,.Cast,PLAYER_CLASS_ACTION_SECONDS)
	radius := nova_radius(player)
	room, engulf_room := room_at(&run.dungeon, player.pos.x, player.pos.y)
	engulf_room &&= nova_engulfs_room(player)
	feel_emit(
		run,.Nova,player.pos,ARCHETYPE_SKILL_COLORS[.Arcanist],.48,radius,
		direction=player.facing,style=.Arcanist,priority=.High,engulf_room=engulf_room,
	)
	chill_duration: f32 = player_has_discipline(player, .Arcanist_Permafrost) ? 1.9 : 1.2
	for &enemy in run.enemies {
		if enemy.hp <= 0 do continue
		delta := enemy.pos - player.pos
		distance := math.hypot(delta.x, delta.y)
		in_reach := distance <= radius
		if engulf_room && !in_reach {
			ex, ey := int(enemy.pos.x), int(enemy.pos.y)
			in_reach = ex >= room.x && ex < room.x + room.w && ey >= room.y && ey < room.y + room.h
		}
		if !in_reach || !line_of_sight(&run.dungeon, player.pos.x, player.pos.y, enemy.pos.x, enemy.pos.y) do continue
		// Discipline spell bonuses count here as in pygame's player.spell_bonus.
		damage := 10 + player.level*2 + ARCHETYPES[player.archetype].spell_bonus +
			player.discipline_spell_bonus + rng_range(&run.combat_rng, 0, 5)
		if player_has_class_skill_bonus(player) do damage += 2
		damage = story_apply_player_damage(run, damage, spell = true)
		_ = player_damage_enemy(run, &enemy, damage, .Frost, .Chilled, true, chill_duration)
		if distance > .001 do slide_move(&run.dungeon, &enemy.pos, delta/distance*.18)
	}
	append(&run.numbers, Damage_Number{pos=player.pos, kind=.Text, text="Frost Nova"})
	append(&run.sfx, Sfx_Kind.Bolt)
	return true
}

@(private = "file")
bell_placement :: proc(run: ^Run, plant_range: f32) -> Vec2 {
	dir := linalg.normalize0(run.player.facing)
	if dir == {} do dir = {1,0}
	for step := 16; step > 0; step -= 1 {
		candidate := run.player.pos + dir * (plant_range * f32(step)/16)
		if !blocked_for_radius(&run.dungeon, candidate.x, candidate.y, .22) &&
			line_of_sight(&run.dungeon, run.player.pos.x, run.player.pos.y, candidate.x, candidate.y) {
			return candidate
		}
	}
	return run.player.pos
}

@(private = "file")
cast_ambush_bell :: proc(run: ^Run) -> bool {
	player := &run.player
	cost := player_class_skill_mana_cost(player)
	if player.class_skill_timer > 0 || player.mana < cost do return false
	player.mana -= cost
	player.class_skill_timer = player_class_skill_cooldown(player)
	player_start_visual_action(player,.Cast,PLAYER_BELL_ACTION_SECONDS)
	bell, plant_range := ambush_bell_tuning(player)
	bell.pos = bell_placement(run, plant_range)
	clear(&run.bells)
	append(&run.bells, bell)
	feel_emit(
		run,.Cast,player.pos,ARCHETYPE_SKILL_COLORS[.Rogue],.30,.36,
		direction=player.facing,style=.Rogue,priority=.High,
	)
	feel_emit(
		run,.Bell_Plant,bell.pos,DAMAGE_TYPE_COLORS[.Shadow],.30,.34,
		phase=.Origin,style=.Rogue,priority=.High,
	)
	player_apply_status(player, .Smoke, bell.smoke_duration)
	append(&run.numbers, Damage_Number{pos=run.bells[0].pos, kind=.Text, text="Ambush Bell"})
	append(&run.sfx,Sfx_Kind.Bell)
	return true
}

// The cast's shared Storm charge arcs from the earliest Arc Bolt impact
// (projectiles.py:315-404). Tier, reach, and elite priority read live; the
// hop damage is a flat 55% of the impacting shard, no per-hop falloff.
storm_chain_tiers :: proc(player: ^Player) -> (jump_limit: int, jump_radius: f32, elite_priority: bool) {
	switch {
	case player_has_discipline(player, .Arcanist_World_Storm): return 4, 3.6, true
	case player_has_discipline(player, .Arcanist_Storm_Caller): return 3, 3.2, true
	case player_has_discipline(player, .Arcanist_Tempest): return 2, 2.8, false
	case player_has_discipline(player, .Arcanist_Chain_Lightning): return 1, 2.6, false
	}
	return 0, 0, false
}

resolve_storm_chain :: proc(run: ^Run, p: ^Projectile, primary: ^Enemy) {
	jump_limit, jump_radius, elite_priority := storm_chain_tiers(&run.player)
	if jump_limit <= 0 do return
	chain_damage := max(1, int(f32(p.damage) * 0.55))
	visited: [16]u32
	visited_count := 0
	for i in 0 ..< p.hit_enemy_count {
		visited[visited_count] = p.hit_enemy_ids[i]
		visited_count += 1
	}
	visited[visited_count] = enemy_ensure_id(run, primary)
	visited_count += 1
	source := primary
	for _ in 0 ..< jump_limit {
		best: ^Enemy
		best_elite := false
		best_distance := jump_radius
		for &candidate in run.enemies {
			if candidate.hp <= 0 || &candidate == source do continue
			candidate_id := enemy_ensure_id(run, &candidate)
			seen := false
			for j in 0 ..< visited_count do if visited[j] == candidate_id do seen = true
			if seen do continue
			delta := candidate.pos - source.pos
			distance := math.hypot(delta.x, delta.y)
			if distance >= jump_radius do continue
			if !line_of_sight(&run.dungeon, source.pos.x, source.pos.y, candidate.pos.x, candidate.pos.y) do continue
			elite := candidate.role != .Normal
			if elite_priority && elite != best_elite {
				if !elite do continue
			} else if best != nil && distance >= best_distance {
				continue
			}
			best, best_elite, best_distance = &candidate, elite, distance
		}
		if best == nil do break
		_ = damage_enemy_typed(run, best, chain_damage, p.damage_type)
		if p.has_status do enemy_apply_status(best, p.status, p.status_duration * 0.7)
		if dir := linalg.normalize0(best.pos - source.pos); dir != {} {
			enemy_start_knockback(run, best, dir * KNOCKBACK_SPEED)
		}
		if visited_count < len(visited) {
			visited[visited_count] = enemy_ensure_id(run, best)
			visited_count += 1
		}
		if p.hit_enemy_count < len(p.hit_enemy_ids) {
			p.hit_enemy_ids[p.hit_enemy_count] = enemy_ensure_id(run, best)
			p.hit_enemy_count += 1
		}
		source = best
	}
}

player_cast_class_skill :: proc(run: ^Run, aim: Vec2) -> bool {
	player := &run.player
	if bighit_charging(player) do return false
	if aim != {} do player.facing = linalg.normalize0(aim)
	fired := false
	switch player.archetype {
	case .Warden: fired = cast_time_skip(run)
	case .Rogue: fired = cast_ambush_bell(run)
	case .Arcanist: fired = cast_nova(run)
	case .Acolyte: fired = player_cast_spirit_call(run)
	case .Ranger: fired = player_cast_spirit_beast(run)
	}
	if fired do _ = story_apply_blood_price(run, "Class skill blood price")
	return fired
}

ambush_lure_position :: proc(run: ^Run, enemy: ^Enemy) -> (pos: Vec2, found: bool) {
	if enemy.role == .Boss do return {}, false
	best_distance := max(f32)
	for &bell in run.bells {
		if bell.arm_timer > 0 || bell.lifetime <= 0 do continue
		delta := bell.pos - enemy.pos
		distance := math.hypot(delta.x, delta.y)
		if distance > bell.lure_radius || distance >= best_distance do continue
		if !line_of_sight(&run.dungeon, enemy.pos.x, enemy.pos.y, bell.pos.x, bell.pos.y) do continue
		pos, found, best_distance = bell.pos, true, distance
	}
	return pos, found
}

// The primary hit reads the Precision ladder live at detonation
// (ambush_bell.py:354-389): flat adders, multipliers, then the bell crit
// table with the snapshotted facing bonuses.
@(private = "file")
bell_primary_damage :: proc(run: ^Run, bell: ^Ambush_Bell, enemy: ^Enemy, facing: bool) -> int {
	player := &run.player
	damage := bell.primary_damage
	if facing do damage = int(f32(damage) * bell.facing_mult) + 2
	if player_has_discipline(player, .Rogue_Precision) do damage += 3
	if player_has_discipline(player, .Rogue_Venom) do damage += 2
	if player_has_discipline(player, .Rogue_Executioner) do damage += enemy.statuses[.Poisoned] > 0 ? 5 : 3
	if player_has_discipline(player, .Rogue_Crimson_Edge) do damage = int(f32(damage) * 1.12)
	if player_has_discipline(player, .Rogue_Deathmark) do damage = int(f32(damage) * 1.20)
	crit_chance, crit_mult: f32
	switch {
	case player_has_discipline(player, .Rogue_Deathmark): crit_chance, crit_mult = 0.34, 2.15
	case player_has_discipline(player, .Rogue_Crimson_Edge): crit_chance, crit_mult = 0.28, 2.0
	case player_has_discipline(player, .Rogue_Executioner): crit_chance, crit_mult = 0.22, 1.9
	case player_has_discipline(player, .Rogue_Venom): crit_chance, crit_mult = 0.16, 1.75
	case player_has_discipline(player, .Rogue_Precision): crit_chance, crit_mult = 0.10, 1.6
	}
	if crit_chance > 0 {
		if facing do crit_chance += bell.facing_crit_bonus
		if rng_chance(&run.combat_rng, crit_chance) {
			damage = int(f32(damage) * crit_mult)
			append(&run.numbers, Damage_Number{pos=enemy.pos, kind=.Text, text="Bell Crit"})
		}
	}
	return story_apply_player_damage(run, damage)
}

@(private = "file")
detonate_bell :: proc(run: ^Run, bell: ^Ambush_Bell, primary: ^Enemy, expired: bool) {
	player := &run.player
	player_apply_status(player, .Smoke, bell.smoke_duration)
	radius := expired ? bell.damage_radius*.82 : bell.damage_radius
	feel_emit(
		run,.Bell_Detonate,bell.pos,DAMAGE_TYPE_COLORS[.Shadow],expired ? f32(.34) : f32(.44),radius,
		phase=expired ? Feel_Phase.Expired : Feel_Phase.Triggered,style=.Rogue,priority=.High,
	)
	kills := 0
	for &enemy in run.enemies {
		if enemy.hp <= 0 do continue
		delta := enemy.pos - bell.pos
		distance := math.hypot(delta.x, delta.y)
		if distance > radius || !line_of_sight(&run.dungeon, bell.pos.x, bell.pos.y, enemy.pos.x, enemy.pos.y) do continue
		damage: int
		snare: f32
		status_duration := bell.status_duration
		if &enemy == primary {
			facing := distance > .001 && linalg.dot(enemy.facing, -delta/distance) > .48
			damage = bell_primary_damage(run, bell, &enemy, facing)
			snare = bell.primary_snare
		} else {
			damage = bell.splash_damage
			if expired do damage = max(3, int(f32(damage)*bell.expired_scale))
			damage = story_apply_player_damage(run, damage)
			snare = bell.splash_snare
			status_duration *= 0.75
		}
		_ = player_damage_enemy(run, &enemy, damage, .Physical, bell.status, bell.has_status, status_duration)
		if snare > 0 do enemy_apply_status(&enemy, .Snared, snare)
		if enemy.hp <= 0 do kills += 1
	}
	// Bell Reprise: kills hasten the slot and restore mana (ambush_bell.py:431-456).
	if kills > 0 && (bell.kill_cooldown_floor > 0 || bell.kill_mana_refund > 0) {
		refunded := false
		if bell.kill_cooldown_floor > 0 && player.class_skill_timer > bell.kill_cooldown_floor {
			player.class_skill_timer = bell.kill_cooldown_floor
			refunded = true
		}
		if bell.kill_mana_refund > 0 && player.mana < f32(player.max_mana) {
			player.mana = min(f32(player.max_mana), player.mana + f32(bell.kill_mana_refund))
			refunded = true
		}
		if refunded do append(&run.numbers, Damage_Number{pos=player.pos, kind=.Text, text="Bell Reprise"})
	}
	append(&run.sfx, Sfx_Kind.Bell)
}

tick_ambush_bells :: proc(run: ^Run, dt: f32) {
	#reverse for &bell, i in run.bells {
		bell.arm_timer = max(0, bell.arm_timer-dt)
		if bell.arm_timer <= 0 && !bell.armed_announced {
			bell.armed_announced = true
			feel_emit(
				run,.Bell_Arm,bell.pos,DAMAGE_TYPE_COLORS[.Shadow],.24,.28,
				style=.Rogue,priority=.High,
			)
		}
		bell.lifetime -= dt
		primary: ^Enemy
		if bell.arm_timer <= 0 {
			best := bell.trigger_radius
			for &enemy in run.enemies {
				if enemy.hp <= 0 do continue
				delta := enemy.pos-bell.pos
				distance := math.hypot(delta.x,delta.y)
				if distance <= best && line_of_sight(&run.dungeon,bell.pos.x,bell.pos.y,enemy.pos.x,enemy.pos.y) {
					primary,best=&enemy,distance
				}
			}
		}
		if primary != nil || bell.lifetime <= 0 {
			detonate_bell(run,&bell,primary,bell.lifetime<=0)
			unordered_remove(&run.bells,i)
		}
	}
}
