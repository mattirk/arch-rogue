package archrogue

// Simulation: player movement/combat, enemy AI, projectiles, damage.
// Raylib-free; every proc here runs headless under odin test.

import "core:fmt"
import "core:math"
import "core:math/linalg"
import "core:strings"

INTERACT_STAIRS_RADIUS :: 1.35
ATTACK_SWING_SECONDS :: 0.45 // attack clip playback window per swing
// 2026-08 feel feedback: a basic swing opens with a movement plant and a
// connected swing freezes the sim for a beat. Deliberate deviations from the
// pygame game, which let swings happen mid-stride with no impact pause. The
// plant must stay under the 0.20 s melee cooldown floor so held attacks keep
// a walk phase between swings.
MELEE_COMMIT_SECONDS :: 0.14 // plant window: walk input ignored, aim facing held
HITSTOP_HIT_TICKS :: 2 // sim ticks swallowed when a basic swing connects
HITSTOP_HEAVY_TICKS :: 4 // a beat longer when the swing crits or kills
HIT_FLASH_SECONDS :: 0.25
DAMAGE_NUMBER_SECONDS :: 0.9
ENEMY_PROJECTILE_TTL :: 1.8
PLAYER_PROJECTILE_HIT_RADIUS :: 0.54 // player bolts vs enemies (constants.py)
PLAYER_HIT_RADIUS :: 0.42
ENEMY_HIT_RADIUS :: 0.42
LARGE_ENEMY_HIT_RADIUS :: 0.52
ENEMY_PROJECTILE_HIT_RADIUS :: 0.52 // enemy bolts vs the player
ENEMY_SEPARATION_RADIUS :: 0.55
PLAYER_MOVE_SPEED :: 2.8
// Facing keeps the last *committed* movement heading when locomotion stops:
// a direction must be held this long to become the stop heading, so the 1-2
// single-axis ticks from staggered two-arrow releases (or stick spring-back)
// cannot rotate a diagonal walk's facing at the stop edge.
HEADING_COMMIT_SECONDS :: f32(0.12)
HEADING_TURN_COS :: f32(0.86) // ~30 degrees: any 45-degree 8-way step restarts the hold
ARCHETYPE_MOVE_RATING_BASELINE :: 3.5
WALK_ANIMATION_RATE :: 0.8
WALK_ANIM_SPEED_FLOOR :: 2.2
WALK_ANIM_SPEED_CEIL :: 3.6
WALK_ANIM_RUNTIME_SCALE_FLOOR :: 0.25

// Authored action clips use their own elapsed clock. Locomotion anim_time is
// deliberately independent so beginning an attack never snaps the walk cycle.
PLAYER_ATTACK_ACTION_SECONDS :: 0.20
PLAYER_BIG_HIT_CAST_SECONDS :: 0.90
PLAYER_BIG_HIT_ATTACK_SECONDS :: 0.26
PLAYER_BOLT_ACTION_SECONDS :: 0.24
PLAYER_DASH_ACTION_SECONDS :: 0.22
PLAYER_CLASS_ACTION_SECONDS :: 0.32
PLAYER_BELL_ACTION_SECONDS :: 0.28
PLAYER_BEAST_COMMAND_ACTION_SECONDS :: 0.18
ENEMY_ATTACK_ACTION_SECONDS :: 0.22

PICKUP_RADIUS :: 1.0 // interactions.py nearby_item radius; pickup is E-driven
BAG_CAPACITY :: 12

Affix :: struct {
	kind: Affix_Kind,
}

Item :: struct {
	kind:        Item_Kind,
	name:        string, // static content string, never allocated
	icon:        string, // baked icon key ("" = procedural marker)
	rarity:      Rarity,
	power:       int, // aggregate base + rolled affix power
	defense:     int, // aggregate base + rolled affix defense
	attack_speed: f32,
	cast_speed:   f32,
	move_speed:   f32,
	thorns:       int,
	lifesteal:    f32,
	proc_chance:  f32,
	damage_type:  Damage_Type,
	typed:        bool,
	skill_bonuses: [Skill_Bonus]bool,
	proc_effect:   Proc_Effect, // first effect, retained for display/legacy items
	proc_effects:  [Proc_Effect]bool, // every rolled proc affix (tags union)
	cursed:        bool,
	unidentified:  bool,
	unique_effect: Unique_Effect, // MX.5 named-unique bespoke hook, .None otherwise
	affixes:     [3]Affix,
	affix_count: int,
}

Ground_Item :: struct {
	entity_id: u64,
	item: Item,
	pos:  Vec2,
}

Inventory_Sort_Mode :: enum {
	Type,
	Rarity,
	Power,
}

item_power :: proc(item: Item) -> int {
	return item.power
}

item_defense :: proc(item: Item) -> int {
	return item.defense
}

item_display_name :: proc(item: Item) -> string {
	if !item.unidentified do return item.name
	return item.kind == .Weapon ? "Unidentified Weapon" : "Unidentified Armor"
}

item_visible_rarity :: proc(item: Item) -> Rarity {
	return item.unidentified ? .Unidentified : item.rarity
}

item_has_bonus :: proc(item: ^Item, bonus: Skill_Bonus) -> bool {
	return item.skill_bonuses[bonus]
}

item_has_proc_effect :: proc(item: ^Item, effect: Proc_Effect) -> bool {
	return item != nil && (item.proc_effect == effect || item.proc_effects[effect])
}

Visual_Action :: enum {
	None,
	Attack,
	Cast,
	Dash,
	Pet,
	Die,
	Dead,
}

Player :: struct {
	archetype:    Archetype_Id,
	pos:          Vec2, // tile space; feet/contact point
	prev_pos:     Vec2, // last sim tick, for render interpolation
	facing:       Vec2, // tile-space direction, last nonzero move or aim
	moving:       bool,
	heading_stable: Vec2, // movement heading held >= HEADING_COMMIT_SECONDS in this burst
	heading_hold:   f32,  // seconds the current movement direction has been held
	anim_time:    f32,
	sim_elapsed:  f32, // fixed-step run-local clock for deterministic story NPC motion
	guidance_idle_elapsed: f32, // resets on movement/activation; drives the floor-light crest
	guidance_wave_active: bool,
	visual_action: Visual_Action,
	action_time:   f32, // elapsed seconds in the current authored action clip
	action_duration: f32,
	hp:           int,
	max_hp:       int,
	mana:         f32,
	max_mana:     int,
	stamina:      f32,
	max_stamina:  int,
	melee_timer:  f32,
	bolt_timer:   f32,
	dash_timer:   f32,
	class_skill_timer: f32,
	bighit_timer: f32,
	bighit_charge: f32, // remaining charge time; 0 when idle
	time_skip_timer: f32,
	swing_timer:  f32, // attack clip playback remaining
	melee_commit_timer: f32, // basic-swing plant window remaining (rides the save like swing_timer)
	potion_timer: f32,
	hit_flash:    f32,
	hit_flash_duration: f32,
	level:        int,
	xp:           int,
	next_xp:      int,
	gold:         int,
	heal_potions: int,
	mana_potions: int,
	weapon:       Item,
	armor:        Item,
	has_weapon:   bool,
	has_armor:    bool,
	bag:          [BAG_CAPACITY]Item,
	bag_count:    int,
	statuses:     [Status_Kind]f32,
	poison_tick:  f32,
	shrine_move_bonus: f32, // Haste Shrine stride blessing; permanent, capped 0.09
	memory_tokens: int,
	acquired_disciplines: [Discipline_Id]bool,
	discipline_melee_bonus: int, // node bonuses plus applied path-completion bonus
	discipline_spell_bonus: int, // node bonuses plus applied path-completion bonus
	discipline_armor_bonus: int,
	discipline_speed_bonus: f32, // authored rating; converted to movement at 25%
	discipline_combo_melee_applied: int,
	discipline_combo_spell_applied: int,
	discipline_combo_hp_applied: int,
	precision_rank: u8, // M8 compatibility seam; live rank derives from disciplines
}

// Effective stats: archetype base + level + equipment (models.py formulas).

player_melee_damage :: proc(p: ^Player) -> int {
	dmg := PLAYER_BASE_MELEE + p.level * PLAYER_LEVEL_DAMAGE + ARCHETYPES[p.archetype].melee_bonus + p.discipline_melee_bonus
	if p.has_weapon {
		dmg += item_power(p.weapon)
		if p.weapon.cursed do dmg += 3
		if p.weapon.unique_effect == .Embers_On_Hit do dmg += 4 // models.py:1132
	}
	return dmg
}

player_spell_damage :: proc(p: ^Player, base: int) -> int {
	return base + p.level * PLAYER_LEVEL_DAMAGE + ARCHETYPES[p.archetype].spell_bonus + p.discipline_spell_bonus
}

player_armor :: proc(p: ^Player) -> int {
	armor := ARCHETYPES[p.archetype].armor_bonus + p.discipline_armor_bonus
	if p.has_armor {
		armor += item_defense(p.armor)
		if p.armor.cursed do armor -= 1
		// models.py:1160-1163 armor-slot unique riders.
		if p.armor.unique_effect == .Steadfast_Bulwark do armor += 2
		if p.armor.unique_effect == .Oathwall_Aegis do armor += 3
	}
	return max(0, armor)
}

player_speed :: proc(p: ^Player) -> f32 {
	bonus := (ARCHETYPES[p.archetype].speed - ARCHETYPE_MOVE_RATING_BASELINE) /
		ARCHETYPE_MOVE_RATING_BASELINE
	bonus += p.discipline_speed_bonus * 0.25
	if p.has_weapon do bonus += p.weapon.move_speed
	if p.has_armor do bonus += p.armor.move_speed
	bonus += p.shrine_move_bonus // Haste Shrine channel (costs.py:141)
	speed := PLAYER_MOVE_SPEED * (1 + clamp(bonus, -0.25, 0.30))
	if p.statuses[.Chilled] > 0 do speed *= 0.82
	return speed
}

// Phase advance for a tick that actually displaced an actor. The base cadence
// follows authored actor speed, while actual/planned displacement accounts for
// analog input, charge slows, Time Skip, status slows, and wall sliding. A
// moving actor retains the pygame 25% cadence floor; a blocked actor gets zero.
walk_animation_advance :: proc(
	dt, actor_speed, actual_distance, planned_full_distance: f32,
) -> f32 {
	if dt <= 0 || actual_distance <= 0 || planned_full_distance <= 0 do return 0
	cadence := clamp(actor_speed, f32(WALK_ANIM_SPEED_FLOOR), f32(WALK_ANIM_SPEED_CEIL))
	runtime_scale := clamp(
		actual_distance / planned_full_distance,
		f32(WALK_ANIM_RUNTIME_SCALE_FLOOR),
		f32(1),
	)
	return dt * WALK_ANIMATION_RATE * cadence * runtime_scale
}

player_clear_visual_action :: proc(player: ^Player) {
	if player == nil do return
	player.visual_action = .None
	player.action_time = 0
	player.action_duration = 0
}

// Matches pygame's action clock contract: a new pose restarts at frame zero;
// retriggering the same live pose extends it without snapping the clip back.
player_start_visual_action :: proc(
	player: ^Player,
	action: Visual_Action,
	duration: f32,
) {
	if player == nil do return
	if action == .None || duration <= 0 {
		player_clear_visual_action(player)
		return
	}
	if player.visual_action != action || player.action_duration <= 0 ||
		player.action_time >= player.action_duration {
		player.action_time = 0
		player.action_duration = duration
	} else {
		player.action_duration = max(player.action_duration, player.action_time + duration)
	}
	player.visual_action = action
}

player_visual_action_progress :: proc(player: ^Player) -> f32 {
	if player == nil || player.visual_action == .None || player.action_duration <= 0 do return 0
	return clamp(player.action_time / player.action_duration, f32(0), f32(1))
}

player_tick_visual_action :: proc(player: ^Player, dt: f32) {
	if player == nil || dt <= 0 || player.visual_action == .None {
		return
	}
	if player.visual_action == .Dead {
		player.action_time += dt
		return
	}
	player.action_time += dt
	if player.action_time < player.action_duration do return
	if player.visual_action == .Die {
		player.visual_action = .Dead
		player.action_time = 0
		player.action_duration = 0
		return
	}
	player_clear_visual_action(player)
}

player_lifesteal :: proc(p: ^Player) -> f32 {
	total: f32
	if p.has_weapon do total += p.weapon.lifesteal
	if p.has_armor do total += p.armor.lifesteal
	if total <= 0 && ((p.has_weapon && item_has_proc_effect(&p.weapon, .Lifesteal)) ||
		(p.has_armor && item_has_proc_effect(&p.armor, .Lifesteal))) {
		total = .08
	}
	// Blood Pact grants additional lifesteal on top of gear (equipment.py:106-114);
	// Blood Psalm's sanguine echo deepens the drain (equipment.py:110-111).
	if player_has_discipline(p, .Acolyte_Blood_Pact) do total += 0.03
	if player_has_unique_effect(p, .Sanguine_Echo) do total += 0.06
	return clamp(total, 0, 0.24)
}

player_thorns :: proc(p: ^Player) -> int {
	total := 0
	if p.has_weapon do total += p.weapon.thorns
	if p.has_armor do total += p.armor.thorns
	if total <= 0 && ((p.has_weapon && item_has_proc_effect(&p.weapon, .Thorns)) ||
		(p.has_armor && item_has_proc_effect(&p.armor, .Thorns))) {
		total = 3
	}
	// Choir of Bone's grave chorus barbs every reflection (equipment.py:120-121).
	if player_has_unique_effect(p, .Grave_Chorus) do total += 2
	return total
}

AI_State :: enum {
	Idle,
	Chase,
	Windup,
}

Enemy_Action_Kind :: enum u8 {
	None,
	Attack,
	Cast,
}

Enemy_Role :: enum {
	Normal,
	Elite,
	Miniboss,
	Boss,
}

Story_Combat_Target_Kind :: enum u8 {
	None,
	Guest,
	Soul,
}

Story_Combat_Target :: struct {
	kind:        Story_Combat_Target_Kind,
	guest_index: int,
	pos:         Vec2,
}

// Instance stats are copied from content at spawn and then modified by depth
// scaling, elite modifiers, and boss makers; ticks never read the def tables.
Enemy :: struct {
	entity_id:       u32, // stable within a run; piercing projectiles remember hits
	kind:            Enemy_Kind,
	boss_id:         Boss_Id, // sprite/def source when role == .Boss
	name:            string, // display override (boss titles); "" = kind name
	role:            Enemy_Role,
	elite_mod:       int, // ELITE_MODIFIERS index, -1 = none
	final_boss:      bool,
	challenge_boss:  bool, // MX.4 challenge_room guardian; clear is tracked, never seals stairs
	big:             bool, // 2x2 boss footprint
	pos:             Vec2,
	prev_pos:        Vec2,
	facing:          Vec2,
	hp:              int,
	max_hp:          int,
	damage:          int,
	xp:              int,
	speed:           f32,
	aggro_range:     f32,
	attack_range:    f32,
	attack_cd_s:     f32, // base recovery between attacks
	ranged:          bool,
	color:           [4]u8,
	damage_type:     Damage_Type,
	resistances:     [Damage_Type]f32,
	statuses:        [Status_Kind]f32,
	poison_tick:     f32,
	knockback_vel:   Vec2,
	abilities:       [2]Ability_Id,
	ability_count:   int,
	ability_cds:     [2]f32,
	pending_ability: int, // committed windup action: slot index, PENDING_BASE_ATTACK, or PENDING_LEGACY_CAST
	last_ability:    int, // last authored slot fired (boss rotation memory); -1 = none
	action_kind:     Enemy_Action_Kind, // fired semantic retained through recovery
	action_timer:    f32, // remaining authored recovery-pose window
	action_duration: f32,
	windup_aim:      Vec2, // target direction snapshotted when the tell begins
	tactic:          Enemy_Tactic,
	alert_timer:     f32, // seconds of target memory left once out of aggro
	memory:          Vec2, // last noticed target position
	strafe_sign:     f32, // sticky lateral preference; 0 = underived
	yield_timer:     f32, // giving way to a closer packmate
	nav_latch:       f32, // stay on the nav field after a stalled advance
	stuck_probe:     Vec2,
	stuck_probe_timer: f32,
	ai:              AI_State,
	windup:          f32,
	windup_duration: f32,
	action_time:     f32, // elapsed seconds in the committed windup
	cooldown:        f32,
	anim_time:       f32,
	hit_flash:       f32,
	hit_flash_duration: f32,
	moving:          bool,
	story_scaled:    bool,
	difficulty_scaled: bool,
	story_target_kind: Story_Combat_Target_Kind,
	story_target_index: int,
}

PENDING_BASE_ATTACK :: -1
PENDING_LEGACY_CAST :: -2 // boss cast-band fallback: 3-bolt fan regardless of melee classification
PENDING_LEGACY_MELEE :: -3 // boss close-band fallback, even for a ranged base profile

// Elite prefixes and the Oathbound miniboss title compose at read time so
// rank stays a plain enum and saves never carry derived strings. The result
// may live in the temp allocator; callers must not retain it across frames.
enemy_display_name :: proc(enemy: ^Enemy) -> string {
	base := enemy.name != "" ? enemy.name : ENEMY_DEFS[enemy.kind].name
	if enemy.role == .Miniboss do return fmt.tprintf("Oathbound %s", base)
	if enemy.role == .Elite && enemy.elite_mod >= 0 && enemy.elite_mod < len(ELITE_MODIFIERS) {
		return fmt.tprintf("%s %s", ELITE_MODIFIERS[enemy.elite_mod].name, base)
	}
	return base
}

// combat/movement.py melee_stop_distance: close to touching, never past reach.
melee_stop_distance :: proc(enemy: ^Enemy) -> f32 {
	contact := f32(PLAYER_HIT_RADIUS) + enemy_hit_radius(enemy)
	return min(enemy.attack_range, max(contact + 0.02, enemy.attack_range - 0.12))
}

// combat/enemies.py _enemy_strafe_sign: sticky, derived from tile parity,
// flipped only by collision feedback. Deterministic — no RNG.
enemy_strafe_sign :: proc(enemy: ^Enemy) -> f32 {
	if enemy.strafe_sign == 0 {
		enemy.strafe_sign = (int(enemy.pos.x) + int(enemy.pos.y)) % 2 == 0 ? 1.0 : -1.0
	}
	return enemy.strafe_sign
}

enemy_move_radius :: proc(enemy: ^Enemy) -> f32 {
	return enemy.big ? BOSS_MOVE_RADIUS : ACTOR_MOVE_COLLISION_RADIUS
}

enemy_hit_radius :: proc(enemy: ^Enemy) -> f32 {
	if enemy.big do return BOSS_HIT_RADIUS
	if enemy.kind == .Gate_Warden || enemy.kind == .Crypt_Brute do return LARGE_ENEMY_HIT_RADIUS
	return ENEMY_HIT_RADIUS
}

enemy_start_knockback :: proc(run: ^Run, enemy: ^Enemy, velocity: Vec2) {
	if enemy == nil || velocity == {} do return
	enemy.knockback_vel = velocity
	speed := math.hypot(velocity.x, velocity.y)
	direction := speed > 0 ? velocity / speed : Vec2{}
	// One launch event describes the complete exponential travel. The renderer
	// derives fixed 35%/70% samples, so even a lethal throw remains readable
	// after the authoritative enemy has been swept this tick.
	feel_emit(
		run,.Knockback_Travel,enemy.pos,enemy.color,.38,speed/f32(KNOCKBACK_DECAY_RATE),direction,
		priority=speed >= KNOCKBACK_CHAIN_MIN_SPEED ? Feel_Priority.High : Feel_Priority.Normal,
		heavy=speed >= KNOCKBACK_CHAIN_MIN_SPEED,
	)
}

boss_alive :: proc(run: ^Run) -> bool {
	for &enemy in run.enemies {
		if enemy.role == .Boss && enemy.hp > 0 do return true
	}
	return false
}

story_enemy_combat_target :: proc(run: ^Run, enemy: ^Enemy) -> (target: Story_Combat_Target) {
	if run == nil || enemy == nil || run.player.hp <= 0 do return
	player_delta := run.player.pos - enemy.pos
	best_sq := player_delta.x * player_delta.x + player_delta.y * player_delta.y
	guest_limit := min(len(run.story_runtime.guests), STORY_BEAT_COUNT)
	for i in 0 ..< guest_limit {
		guest := &run.story_runtime.guests[i]
		if guest.depth != run.depth || guest.witness || !guest.resolved || !guest.ally || !guest.alive || guest.hp <= 0 do continue
		delta := guest.pos - enemy.pos
		distance_sq := delta.x * delta.x + delta.y * delta.y
		if distance_sq < best_sq {
			best_sq = distance_sq
			target = {kind = .Guest, guest_index = i, pos = guest.pos}
		}
	}
	soul := &run.story_runtime.soul
	if soul.present && soul.armed && soul.alive && soul.hp > 0 {
		delta := soul.pos - enemy.pos
		distance_sq := delta.x * delta.x + delta.y * delta.y
		if distance_sq < best_sq do target = {kind = .Soul, guest_index = -1, pos = soul.pos}
	}
	return
}

@(private = "file")
story_combat_target_alive :: proc(run: ^Run, target: Story_Combat_Target) -> bool {
	switch target.kind {
	case .Guest:
		if target.guest_index < 0 || target.guest_index >= len(run.story_runtime.guests) do return false
		guest := &run.story_runtime.guests[target.guest_index]
		return guest.depth == run.depth && guest.ally && guest.alive && guest.hp > 0 && !guest.witness
	case .Soul:
		soul := &run.story_runtime.soul
		return soul.present && soul.armed && soul.alive && soul.hp > 0
	case .None:
	}
	return false
}

@(private = "file")
story_damage_combat_target :: proc(run: ^Run, target: Story_Combat_Target, raw: int) -> int {
	if !story_combat_target_alive(run, target) do return 0
	damage := max(1, raw)
	pos := target.pos
	fallen := false
	switch target.kind {
	case .Guest:
		guest := &run.story_runtime.guests[target.guest_index]
		guest.hp -= damage
		pos = guest.pos
		if guest.hp <= 0 {
			guest.hp = 0
			guest.alive = false
			guest.ally = false
			fallen = true
		}
	case .Soul:
		soul := &run.story_runtime.soul
		soul.hp -= damage
		pos = soul.pos
		if soul.hp <= 0 {
			soul.hp = 0
			soul.alive = false
			soul.present = false
			fallen = true
		}
	case .None:
		return 0
	}
	append(&run.numbers, Damage_Number{pos = pos, value = damage, kind = .Damage_Taken})
	append(&run.sfx, Sfx_Kind.Hurt)
	if fallen {
		append(&run.numbers, Damage_Number{pos = pos, kind = .Text, text = "Story ally falls"})
		append(&run.sfx, Sfx_Kind.Death)
	}
	return damage
}

@(private = "file")
story_projectile_target :: proc(run: ^Run, pos: Vec2) -> (target: Story_Combat_Target, found: bool) {
	guest_limit := min(len(run.story_runtime.guests), STORY_BEAT_COUNT)
	for i in 0 ..< guest_limit {
		guest := &run.story_runtime.guests[i]
		if guest.depth != run.depth || guest.witness || !guest.ally || !guest.alive || guest.hp <= 0 do continue
		delta := guest.pos - pos
		if delta.x * delta.x + delta.y * delta.y >= ENEMY_PROJECTILE_HIT_RADIUS * ENEMY_PROJECTILE_HIT_RADIUS do continue
		if !line_of_sight(&run.dungeon, pos.x, pos.y, guest.pos.x, guest.pos.y) do continue
		return {kind = .Guest, guest_index = i, pos = guest.pos}, true
	}
	soul := &run.story_runtime.soul
	if soul.present && soul.armed && soul.alive && soul.hp > 0 {
		delta := soul.pos - pos
		if delta.x * delta.x + delta.y * delta.y < ENEMY_PROJECTILE_HIT_RADIUS * ENEMY_PROJECTILE_HIT_RADIUS &&
			line_of_sight(&run.dungeon, pos.x, pos.y, soul.pos.x, soul.pos.y) {
			return {kind = .Soul, guest_index = -1, pos = soul.pos}, true
		}
	}
	return {}, false
}

Projectile_Visual :: enum u8 {
	Enemy_Void,
	Warden_Guard,
	Rogue_Dagger,
	Arcanist_Arc,
	Acolyte_Spirit,
	Ranger_Arrow,
}

projectile_visual_for_archetype :: proc(archetype: Archetype_Id) -> Projectile_Visual {
	switch archetype {
	case .Warden:   return .Warden_Guard
	case .Rogue:    return .Rogue_Dagger
	case .Arcanist: return .Arcanist_Arc
	case .Acolyte:  return .Acolyte_Spirit
	case .Ranger:   return .Ranger_Arrow
	}
	return .Enemy_Void
}

Projectile :: struct {
	entity_id:   u64,
	pos:         Vec2,
	prev_pos:    Vec2,
	vel:         Vec2, // tiles per second
	visual:      Projectile_Visual,
	visual_age:  f32, // fixed-step presentation clock; never sampled from wall time
	damage:      int,
	damage_type: Damage_Type,
	status:      Status_Kind,
	has_status:  bool,
	status_duration: f32,
	pierce:      int,
	hit_enemy_ids: [4]u32,
	hit_enemy_count: int,
	from_player: bool,
	owner_id:    u64, // 0 is the player; enemies use their stable entity id
	ttl:         f32,
	color:       [4]u8,
	// MX.3 path shaping: homing strength (projectiles.py:263-313) and the
	// per-cast shared Storm chain charge — every shard of one cast carries the
	// same cast id, and the first impact spends the charge for all of them.
	homing:      f32,
	storm_chain: bool,
	storm_cast:  u32,
}

enemy_ensure_id :: proc(run: ^Run, enemy: ^Enemy) -> u32 {
	if enemy.entity_id == 0 {
		run.next_enemy_id += 1
		if run.next_enemy_id == 0 do run.next_enemy_id = 1
		enemy.entity_id = run.next_enemy_id
	}
	return enemy.entity_id
}

// Sound events the sim emits; the audio layer drains them each frame.
// Raylib-free by design (hard rule 2).
Sfx_Kind :: enum {
	Swing,
	Hit,
	Hurt,
	Bolt,
	Pickup,
	Potion,
	Level_Up,
	Stairs,
	Death,
	Door,
	Start,
	Bell,
	Boss,
	Victory,
	Drink,
	Trap,
	Shrine,
	Secret,
}

Number_Kind :: enum {
	Damage_Dealt,
	Damage_Taken,
	Heal,
	Garden_Heal,
	Bar_Heal,
	Gold,
	Text,
}

Damage_Number :: struct {
	pos:   Vec2,
	value: int,
	age:   f32,
	kind:  Number_Kind,
	damage_type: Damage_Type,
	text:  string, // static string for .Text (e.g. "LEVEL UP!", item names)
}

player_spawn :: proc(run: ^Run, archetype: Archetype_Id) -> Player {
	def := ARCHETYPES[archetype]
	pos := run_spawn_point(run)
	player := Player{
		archetype = archetype,
		pos = pos,
		prev_pos = pos,
		facing = {1, 1},
		hp = def.max_hp,
		max_hp = def.max_hp,
		mana = f32(def.max_mana),
		max_mana = def.max_mana,
		stamina = f32(def.max_stamina),
		max_stamina = def.max_stamina,
		level = 1,
		next_xp = XP_BASE,
		heal_potions = 1, // one starter flask
	}
	weapon := STARTER_WEAPONS[archetype]
	player.weapon = Item{
		kind = .Weapon,
		name = weapon.name,
		icon = weapon.icon,
		rarity = .Common,
		power = weapon.value,
	}
	player.has_weapon = true
	armor := STARTER_ARMORS[archetype]
	player.armor = Item{
		kind = .Armor,
		name = armor.name,
		icon = armor.icon,
		rarity = .Common,
		defense = armor.value,
	}
	player.has_armor = true
	return player
}

// models.py gain_xp: overflow carries, each level is x1.5, level-ups fully
// restore the grown pools.
player_gain_xp :: proc(run: ^Run, amount: int) {
	p := &run.player
	p.xp += amount
	for p.xp >= p.next_xp {
		p.xp -= p.next_xp
		p.level += 1
		p.next_xp = int(f32(p.next_xp) * XP_GROWTH)
		p.max_hp += LEVEL_HP_GAIN
		p.hp = p.max_hp
		p.max_mana += LEVEL_MANA_GAIN
		p.mana = f32(p.max_mana)
		p.max_stamina += LEVEL_STAMINA_GAIN
		p.stamina = f32(p.max_stamina)
		p.memory_tokens += 1
		append(&run.numbers, Damage_Number{pos = p.pos, kind = .Text, text = "LEVEL UP!"})
		append(&run.sfx, Sfx_Kind.Level_Up)
	}
}

player_use_potion :: proc(run: ^Run, kind: Item_Kind) {
	p := &run.player
	if p.potion_timer > 0 do return
	#partial switch kind {
	case .Heal_Potion:
		if p.heal_potions <= 0 || p.hp >= p.max_hp do return
		p.heal_potions -= 1
		healed := min(HEAL_POTION_AMOUNT, p.max_hp - p.hp)
		p.hp += healed
		append(&run.numbers, Damage_Number{pos = p.pos, kind = .Heal, value = healed})
	case .Mana_Potion:
		if p.mana_potions <= 0 || p.mana >= f32(p.max_mana) do return
		p.mana_potions -= 1
		p.mana = min(f32(p.max_mana), p.mana + MANA_POTION_AMOUNT)
	}
	run.potions_used += 1
	p.potion_timer = POTION_COOLDOWN
	append(&run.sfx, Sfx_Kind.Potion)
}

// Equip the bag item at index, swapping any currently equipped piece back
// into the same bag slot.
equip_from_bag :: proc(p: ^Player, index: int) {
	if index < 0 || index >= p.bag_count do return
	item := p.bag[index]
	#partial switch item.kind {
	case .Weapon:
		if p.has_weapon && p.weapon.cursed do return
		item.unidentified = false
		if p.has_weapon {
			p.bag[index] = p.weapon
		} else {
			bag_remove(p, index)
		}
		p.weapon = item
		p.has_weapon = true
	case .Armor:
		if p.has_armor && p.armor.cursed do return
		item.unidentified = false
		if p.has_armor {
			p.bag[index] = p.armor
		} else {
			bag_remove(p, index)
		}
		p.armor = item
		p.has_armor = true
	case .Identify_Scroll:
		_ = identify_best_bag_item(p)
		bag_remove(p, index) // consumed even when nothing can be identified
	case .Remove_Curse_Scroll:
		if remove_player_curse(p) do bag_remove(p, index)
	}
}

identify_best_bag_item :: proc(p: ^Player) -> bool {
	best := -1
	best_score := min(int)
	for &item, i in p.bag {
		if i >= p.bag_count do break
		if !item.unidentified do continue
		score := inventory_power_score(item)
		if score > best_score || (score == best_score && best >= 0 && strings.compare(item_display_name(item), item_display_name(p.bag[best])) > 0) {
			best, best_score = i, score
		}
	}
	if best < 0 do return false
	p.bag[best].unidentified = false
	return true
}

cleanse_item :: proc(item: ^Item) {
	if item == nil || !item.cursed do return
	item.cursed = false
	item.rarity = .Rare
	if item.kind == .Weapon {
		item.move_speed += 0.03
	} else if item.kind == .Armor {
		item.cast_speed += 0.03
		item.move_speed += 0.04
	}
}

remove_player_curse :: proc(p: ^Player) -> bool {
	if p.has_weapon && p.weapon.cursed {
		cleanse_item(&p.weapon)
		return true
	}
	if p.has_armor && p.armor.cursed {
		cleanse_item(&p.armor)
		return true
	}
	best := -1
	best_score := min(int)
	for &item, i in p.bag {
		if i >= p.bag_count do break
		if !item.cursed do continue
		score := inventory_power_score(item)
		if score > best_score || (score == best_score && best >= 0 && strings.compare(item_display_name(item), item_display_name(p.bag[best])) > 0) {
			best, best_score = i, score
		}
	}
	if best < 0 do return false
	cleanse_item(&p.bag[best])
	return true
}

inventory_category :: proc(item: Item) -> int {
	switch item.kind {
	case .Weapon:       return 0
	case .Armor:        return 1
	case .Heal_Potion:  return 2
	case .Mana_Potion:  return 3
	case .Identify_Scroll: return 4
	case .Remove_Curse_Scroll: return 5
	}
	return 9
}

inventory_power_score :: proc(item: Item) -> int {
	switch item.kind {
	case .Weapon:       return item_power(item)
	case .Armor:        return item_defense(item)
	case .Heal_Potion:  return HEAL_POTION_AMOUNT
	case .Mana_Potion:  return int(MANA_POTION_AMOUNT)
	case .Identify_Scroll, .Remove_Curse_Scroll: return 0
	}
	return 0
}

rarity_sort_rank :: proc(item: Item) -> int {
	switch item_visible_rarity(item) {
	case .Common:       return 0
	case .Magic:        return 1
	case .Rare:         return 2
	case .Cursed:       return 3
	case .Unique:       return 4
	case .Legendary:    return 5
	case .Unidentified: return 6
	}
	return 0
}

@(private = "file")
inventory_item_before :: proc(a, b: Item, mode: Inventory_Sort_Mode) -> bool {
	category_a, category_b := inventory_category(a), inventory_category(b)
	rarity_a, rarity_b := rarity_sort_rank(a), rarity_sort_rank(b)
	power_a, power_b := inventory_power_score(a), inventory_power_score(b)

	switch mode {
	case .Rarity:
		if rarity_a != rarity_b do return rarity_a > rarity_b
		if category_a != category_b do return category_a < category_b
	case .Power:
		if category_a != category_b do return category_a < category_b
		if power_a != power_b do return power_a > power_b
	case .Type:
		if category_a != category_b do return category_a < category_b
		if rarity_a != rarity_b do return rarity_a > rarity_b
	}
	if power_a != power_b do return power_a > power_b
	if rarity_a != rarity_b do return rarity_a > rarity_b
	return strings.compare(a.name, b.name) < 0
}

// Twelve slots make insertion sort both simpler and cheaper than allocating a
// temporary slice. Equal items retain their previous order.
sort_bag :: proc(p: ^Player, mode: Inventory_Sort_Mode) {
	for i in 1 ..< p.bag_count {
		item := p.bag[i]
		j := i
		for j > 0 && inventory_item_before(item, p.bag[j - 1], mode) {
			p.bag[j] = p.bag[j - 1]
			j -= 1
		}
		p.bag[j] = item
	}
}

drop_from_bag :: proc(run: ^Run, index: int) -> bool {
	p := &run.player
	if index < 0 || index >= p.bag_count do return false
	item := p.bag[index]
	bag_remove(p, index)
	drop_pos := p.pos
	if p.facing != {} {
		candidate := p.pos + linalg.normalize0(p.facing) * 0.35
		if is_floor(&run.dungeon, candidate.x, candidate.y) do drop_pos = candidate
	}
	append(&run.ground_items, Ground_Item{item = item, pos = drop_pos})
	append(&run.numbers, Damage_Number{pos = p.pos, kind = .Text, text = item_display_name(item)})
	append(&run.sfx, Sfx_Kind.Pickup)
	return true
}

@(private = "file")
bag_remove :: proc(p: ^Player, index: int) {
	for i in index ..< p.bag_count - 1 {
		p.bag[i] = p.bag[i + 1]
	}
	p.bag_count -= 1
	p.bag[p.bag_count] = {}
}

// Pygame keeps every equipment pickup in the bag until the player chooses to
// identify/equip it. This is especially important for hidden curses.
@(private = "file")
try_take_item :: proc(p: ^Player, item: Item) -> bool {
	if p.bag_count >= BAG_CAPACITY do return false
	p.bag[p.bag_count] = item
	p.bag_count += 1
	return true
}

// --- Tick ------------------------------------------------------------------

sim_tick :: proc(run: ^Run, move: Vec2) {
	sim_tick_limited(run, move, -1)
}

// Fixed-step tick with an optional movement cap. Desktop click-to-walk uses
// this only for its final step into the 0.12-tile cursor dead zone; keyboard
// and every headless simulation caller pass -1 for the ordinary full step.
sim_tick_limited :: proc(run: ^Run, move: Vec2, max_move_step: f32, auto_melee := false) {
	// Impact freeze: a connected basic swing swallows whole sim ticks so every
	// combat clock pauses in step — a frozen tick is consumed, not simulated.
	// Interpolation spans collapse to the settled pose so render-alpha resets
	// cannot re-glide actors mid-freeze. Feel events tick outside the sim
	// (app_tick) and keep playing through the freeze.
	if run.hitstop_ticks > 0 {
		run.hitstop_ticks -= 1
		run.player.prev_pos = run.player.pos
		for &enemy in run.enemies do enemy.prev_pos = enemy.pos
		for &p in run.projectiles do p.prev_pos = p.pos
		for &f in run.familiars do f.prev_pos = f.pos
		room_npc_snapshot_live_positions(run)
		story_snapshot_friendly_npc_positions(run)
		return
	}
	enemy_dt := enemy_sim_dt(run) // sample Time Skip before its player clock advances
	tick_player(run, move, max_move_step)
	if run.player.moving do run.player.guidance_idle_elapsed = 0
	else do run.player.guidance_idle_elapsed += SIM_DT
	// Player input resolves before enemies, as it does in Game.update(). Empty
	// arcs do not spend stamina or begin a cooldown.
	if auto_melee && run.player.hp > 0 && enemy_in_melee_arc(run, run.player.facing) {
		player_melee(run, run.player.facing)
	}
	tick_player_clocks(run)
	tick_refuge(run)
	tick_big_hit(run) // source updates charge after decrementing the old cooldown
	tick_combat_statuses(run)
	run.player.sim_elapsed += SIM_DT
	room_npc_snapshot_live_positions(run)
	story_snapshot_friendly_npc_positions(run)
	room_npc_tick_live(run, run.player.sim_elapsed, SIM_DT)
	story_tick_friendly_npc_movement(run, run.player.sim_elapsed, SIM_DT)
	story_refresh_guidance_if_needed(run)
	refresh_visibility(run)
	tick_ambush_bells(run, SIM_DT)
	tick_enemies(run, enemy_dt)
	tick_ambush_bells(run, 0) // catch a lure crossing the trigger this tick
	tick_familiars(run)
	story_tick_friendly_npc_combat(run, SIM_DT)
	tick_projectiles(run)
	// Traps fire right after projectiles and secrets reveal right after, the
	// game.py:2111-2112 update order.
	tick_traps(run, SIM_DT)
	tick_secrets(run)
	tick_numbers(run)
	sweep_dead_enemies(run)
}

@(private = "file")
tick_refuge :: proc(run: ^Run) {
	kind := special_room_kind_at_point(&run.dungeon, run.player.pos.x, run.player.pos.y)
	result := refuge_tick(kind, &run.refuge, &run.player, SIM_DT)
	if result.healed > 0 {
		number_kind := kind == .Garden ? Number_Kind.Garden_Heal : Number_Kind.Bar_Heal
		append(&run.numbers, Damage_Number{pos=run.player.pos, value=result.healed, kind=number_kind})
	}
}

// Fog of war: LOS-based reveal within SIGHT_RADIUS. line_of_sight skips its
// endpoints, so wall tiles adjacent to lit floor reveal correctly while
// tiles BEHIND walls stay dark (the pygame fog-over-walls fix, by
// construction). `visible` is rebuilt every tick; `explored` accumulates
// (lit floors render the memory, dark floors ignore it).
refresh_visibility :: proc(run: ^Run) {
	run.visible = {}
	px, py := run.player.pos.x, run.player.pos.y
	cx, cy := int(px), int(py)
	reach := int(SIGHT_RADIUS) + 1

	// Pass 1: transparent tiles reveal by LOS to their centers. Closed doors
	// are opaque and join walls in pass 2; marching toward their center enters
	// the blocked tile before the final sample, so treating them as transparent
	// here leaves the closed-door sprite undiscovered.
	for y in max(0, cy - reach) ..= min(MAP_H - 1, cy + reach) {
		for x in max(0, cx - reach) ..= min(MAP_W - 1, cx + reach) {
			tile := run.dungeon.tiles[x][y]
			if tile == .Wall || tile == .Closed_Door do continue
			tx, ty := f32(x) + 0.5, f32(y) + 0.5
			dx, dy := tx - px, ty - py
			if dx * dx + dy * dy > SIGHT_RADIUS * SIGHT_RADIUS do continue
			if !line_of_sight(&run.dungeon, px, py, tx, ty) do continue
			run.visible[x][y] = true
			run.explored[x][y] = true
		}
	}
	if dungeon_in_bounds(cx, cy) {
		run.visible[cx][cy] = true
		run.explored[cx][cy] = true
	}

	// Pass 2: an opaque wall or closed door shows when any adjacent transparent
	// tile is visibly lit — the face you can see, never the space beyond it.
	for y in max(0, cy - reach - 1) ..= min(MAP_H - 1, cy + reach + 1) {
		for x in max(0, cx - reach - 1) ..= min(MAP_W - 1, cx + reach + 1) {
			tile := run.dungeon.tiles[x][y]
			if tile != .Wall && tile != .Closed_Door do continue
			neighbor_lit := false
			for dy in -1 ..= 1 {
				for dx in -1 ..= 1 {
					nx, ny := x + dx, y + dy
					if dx == 0 && dy == 0 || !dungeon_in_bounds(nx, ny) do continue
					neighbor := run.dungeon.tiles[nx][ny]
					if neighbor != .Wall && neighbor != .Closed_Door && run.visible[nx][ny] {
						neighbor_lit = true
					}
				}
			}
			if neighbor_lit {
				run.visible[x][y] = true
				run.explored[x][y] = true
			}
		}
	}
}

story_route_target :: proc(run: ^Run) -> (target: Vec2, enabled: bool) {
	if run == nil do return {}, false
	if !run.story_runtime.initialized {
		stairs := run.dungeon.stairs
		return {f32(stairs.x) + .5, f32(stairs.y) + .5}, true
	}
	relic := &run.story_runtime.relic
	if !relic.guidance do return {}, false
	if relic.present && !relic.collected do return relic.position, true
	if relic.collected && relic.guidance_to_stairs && story_aid_relic_streak_intact(run) {
		stairs := run.dungeon.stairs
		return {f32(stairs.x) + .5, f32(stairs.y) + .5}, true
	}
	return {}, false
}

@(private = "file")
story_refresh_guidance_if_needed :: proc(run: ^Run) {
	target, enabled := story_route_target(run)
	story_set_guidance_wave_active(run,enabled)
	if !enabled {
		if run != nil do clear(&run.story_runtime.guidance_path)
		return
	}
	player_tile := [2]int{int(run.player.pos.x), int(run.player.pos.y)}
	path := story_relic_guidance_path(run)
	if len(path) == 0 || path[0] != player_tile do _ = story_build_guidance_path(run, target)
}

// BFS route from the player to the stairs over passable tiles (closed doors
// count — they open). Story-aware callers use story_route_target and the
// runtime guidance path instead; this helper retains its legacy stairs contract.
route_to_stairs :: proc(run: ^Run, buf: [][2]i16) -> int {
	d := &run.dungeon
	start := [2]i16{i16(run.player.pos.x), i16(run.player.pos.y)}
	goal := [2]i16{i16(d.stairs.x), i16(d.stairs.y)}
	if !dungeon_in_bounds(int(start.x), int(start.y)) do return 0

	visited: [MAP_W][MAP_H]bool
	prev: [MAP_W][MAP_H][2]i16
	queue: [MAP_W * MAP_H][2]i16
	head, tail := 0, 0
	queue[tail] = start
	tail += 1
	visited[start.x][start.y] = true

	dirs := [4][2]i16{{1, 0}, {-1, 0}, {0, 1}, {0, -1}}
	found := false
	for head < tail {
		p := queue[head]
		head += 1
		if p == goal {
			found = true
			break
		}
		for dir in dirs {
			n := p + dir
			if !dungeon_in_bounds(int(n.x), int(n.y)) || visited[n.x][n.y] do continue
			if d.tiles[n.x][n.y] == .Wall do continue
			visited[n.x][n.y] = true
			prev[n.x][n.y] = p
			queue[tail] = n
			tail += 1
		}
	}
	if !found do return 0

	// Walk back goal -> start to measure, then fill forward.
	length := 1
	for p := goal; p != start; p = prev[p.x][p.y] {
		length += 1
	}
	if length > len(buf) do return 0
	i := length - 1
	for p := goal; ; p = prev[p.x][p.y] {
		buf[i] = p
		if p == start do break
		i -= 1
	}
	return length
}

// Axis-separated movement (try x, then y) slides along walls, exactly like
// the pygame move_actor. The player probe also blocks on the stair shaft.
@(private = "file")
tick_player :: proc(run: ^Run, move: Vec2, max_move_step: f32) {
	player := &run.player
	player.prev_pos = player.pos
	if player.hp <= 0 {
		player.moving = false
		return
	}

	player.moving = false
	// 2026-08 feel feedback: the front of a basic swing plants the player and
	// keeps the swing's aim facing, so hitting reads as its own action instead
	// of a drive-by (the pygame game imposed no such lock).
	if player.melee_commit_timer > 0 do return
	if move == {} {
		// Stop edge: if the final direction was only a sub-commit blip (key
		// release stagger, stick spring-back), restore the committed heading.
		if player.heading_stable != {} && player.heading_hold < HEADING_COMMIT_SECONDS {
			player.facing = player.heading_stable
		}
		player.heading_stable = {}
		player.heading_hold = 0
		return
	}
	magnitude := min(f32(1), math.hypot(move.x, move.y))
	if max_move_step >= 0 do magnitude = 1 // mouse target distance is not stick deflection
	dir := linalg.normalize0(move)
	// player.facing still holds the previous moving tick's direction here, so
	// it doubles as the reference for the heading-commit clock.
	if dir.x * player.facing.x + dir.y * player.facing.y >= HEADING_TURN_COS {
		player.heading_hold += SIM_DT
	} else {
		player.heading_hold = SIM_DT
	}
	if player.heading_hold >= HEADING_COMMIT_SECONDS do player.heading_stable = dir
	speed := player_speed(player)
	full_step := speed * SIM_DT
	step := full_step * magnitude
	if bighit_charging(player) do step *= 0.5
	if max_move_step >= 0 do step = min(step, max_move_step)
	before := player.pos
	slide_move(&run.dungeon, &player.pos, dir * step, block_stairs = true)
	// Contact resolution belongs to the move itself (pygame move_actor), so the
	// walk animation below sees the post-contact displacement.
	resolve_player_enemy_contacts(run)
	displacement := player.pos - before
	distance := math.hypot(displacement.x, displacement.y)
	player.moving = distance > 0
	player.anim_time += walk_animation_advance(
		SIM_DT,
		PLAYER_MOVE_SPEED,
		distance,
		PLAYER_MOVE_SPEED * SIM_DT,
	)
	// Keyboard/mouse steering always owns facing on the next update, even while
	// an action clip is playing (combat/player.py has no swing-facing lock).
	player.facing = dir
}

@(private = "file")
tick_player_clocks :: proc(run: ^Run) {
	player := &run.player
	player_tick_visual_action(player, SIM_DT)
	if player.hp <= 0 do return
	// Pygame attempts this frame's actions before advancing recovery clocks.
	// Keeping the same order makes held auto-melee cadence deterministic at the
	// cooldown boundary rather than firing one fixed tick early.
	player.melee_timer = max(0, player.melee_timer - SIM_DT)
	player.bolt_timer = max(0, player.bolt_timer - SIM_DT)
	player.dash_timer = max(0, player.dash_timer - SIM_DT)
	player.class_skill_timer = max(0, player.class_skill_timer - SIM_DT)
	player.bighit_timer = max(0, player.bighit_timer - SIM_DT)
	player.time_skip_timer = max(0, player.time_skip_timer - SIM_DT)
	player.swing_timer = max(0, player.swing_timer - SIM_DT)
	player.melee_commit_timer = max(0, player.melee_commit_timer - SIM_DT)
	player.potion_timer = max(0, player.potion_timer - SIM_DT)
	flash_duration := player.hit_flash_duration > 0 ? player.hit_flash_duration : f32(HIT_FLASH_SECONDS)
	player.hit_flash = max(0, player.hit_flash - SIM_DT / flash_duration)
	if player.hit_flash <= 0 do player.hit_flash_duration = 0
	stamina_regen: f32 = player.archetype == .Ranger ? RANGER_STAMINA_REGEN : PLAYER_STAMINA_REGEN
	mana_regen: f32 = player.archetype == .Arcanist ? ARCANIST_MANA_REGEN : PLAYER_MANA_REGEN
	// Discipline recovery riders (costs.py:39-79).
	if player_has_discipline(player, .Ranger_Snare) do stamina_regen += 4
	if player_has_discipline(player, .Arcanist_Focus) do mana_regen += 2.5
	if player_has_discipline(player, .Arcanist_Ward) do mana_regen += 1.5
	if player_has_discipline(player, .Acolyte_Veil) do mana_regen += 2.0
	if player_has_discipline(player, .Acolyte_Curse) do mana_regen += 1.5
	player.stamina = min(f32(player.max_stamina), player.stamina + stamina_regen * SIM_DT)
	player.mana = min(f32(player.max_mana), player.mana + mana_regen * SIM_DT)
}

@(private = "file")
pick_up_nearby_item :: proc(run: ^Run) -> bool {
	player := &run.player
	nearest := -1
	nearest_distance := max(f32)
	for &g, i in run.ground_items {
		d := g.pos - player.pos
		distance := math.hypot(d.x, d.y)
		if distance >= PICKUP_RADIUS || distance >= nearest_distance do continue
		nearest = i
		nearest_distance = distance
	}
	if nearest < 0 do return false

	g := &run.ground_items[nearest]
	switch g.item.kind {
		case .Heal_Potion:
			player.heal_potions += 1
		case .Mana_Potion:
			player.mana_potions += 1
		case .Weapon, .Armor, .Identify_Scroll, .Remove_Curse_Scroll:
			if !try_take_item(player, g.item) {
				append(&run.numbers, Damage_Number{pos = player.pos, kind = .Text, text = "Inventory full"})
				return false
			}
	}
	record_notable_loot(run, g.item) // interactions.py:665 manual pickup path
	append(&run.numbers, Damage_Number{pos = g.pos, kind = .Text, text = item_display_name(g.item)})
	append(&run.sfx, Sfx_Kind.Pickup)
	unordered_remove(&run.ground_items, nearest)
	return true
}

slide_move :: proc(d: ^Dungeon, pos: ^Vec2, delta: Vec2, block_stairs := false, radius: f32 = ACTOR_MOVE_COLLISION_RADIUS) {
	nx := pos.x + delta.x
	if !blocked_for_radius(d, nx, pos.y, radius, block_stairs = block_stairs) {
		pos.x = nx
	}
	ny := pos.y + delta.y
	if !blocked_for_radius(d, pos.x, ny, radius, block_stairs = block_stairs) {
		pos.y = ny
	}
}

@(private = "file")
tick_enemies :: proc(run: ^Run, dt: f32) {
	// Resolve entry against the authoritative arena before any boss AI can chase
	// through its doorway. The post-separation call below remains the watchdog.
	tick_boss_encounter(run)
	nav_field_refresh(run, dt)
	player := &run.player
	for &enemy in run.enemies {
		apply_story_enemy_stats(run, &enemy)
		enemy.prev_pos = enemy.pos
		enemy.moving = false
		if enemy.hp <= 0 do continue
		enemy.cooldown = max(0, enemy.cooldown - dt)
		enemy.action_timer = max(0, enemy.action_timer - dt)
		if enemy.action_timer <= 0 {
			enemy.action_kind = .None
			enemy.action_duration = 0
		}
		flash_duration := enemy.hit_flash_duration > 0 ? enemy.hit_flash_duration : f32(HIT_FLASH_SECONDS)
		enemy.hit_flash = max(0, enemy.hit_flash - dt / flash_duration)
		if enemy.hit_flash <= 0 do enemy.hit_flash_duration = 0
		for i in 0 ..< enemy.ability_count {
			enemy.ability_cds[i] = max(0, enemy.ability_cds[i] - dt)
		}
		enemy.nav_latch = max(0, enemy.nav_latch - dt)
		enemy.yield_timer = max(0, enemy.yield_timer - dt)
		if boss_waiting_for_arena_entry(run, &enemy) {
			// The guardian waits in its authored room until the player crosses the
			// threshold; lures, knockback, and early aggro cannot pull it outside.
			enemy.ai = .Idle
			enemy.windup = 0
			enemy.action_time = 0
			enemy.pending_ability = -1
			enemy.action_kind = .None
			enemy.action_timer = 0
			enemy.action_duration = 0
			enemy.knockback_vel = {}
			continue
		}
		knocked_back := enemy.knockback_vel != {}
		if knocked_back {
			// Heavy throws shove packmates along the arc before the mover
			// integrates; decay is exact exponential so displacement is v0/rate.
			chain_knockback_through_pack(run, &enemy, dt)
			slide_move(&run.dungeon, &enemy.pos, enemy.knockback_vel * dt, radius=enemy_move_radius(&enemy))
			enemy.knockback_vel *= math.exp(-f32(KNOCKBACK_DECAY_RATE) * dt)
			if math.hypot(enemy.knockback_vel.x, enemy.knockback_vel.y) < .01 do enemy.knockback_vel = {}
		}
		if knocked_back do continue
		if enemy.statuses[.Stunned] > 0 do continue

		// A committed tell owns the tick before any fresh player/ally target scan.
		// In particular, a story-targeted windup must keep advancing rather than
		// being intercepted forever by the ally-retarget branch below.
		if enemy.ai == .Windup {
			enemy.action_time += dt
			enemy.windup -= dt
			if enemy.windup <= 0 {
				enemy.windup = 0
				commit_enemy_attack(run, &enemy)
				enemy.ai = .Chase
				enemy.cooldown = enemy.attack_cd_s
			}
			continue
		}

		story_target := story_enemy_combat_target(run, &enemy)
		if story_target.kind != .None && tick_enemy_story_target(run, &enemy, story_target, dt) do continue
		enemy.story_target_kind = .None
		enemy.story_target_index = -1

		to_player := player.pos - enemy.pos
		dist := math.hypot(to_player.x, to_player.y)

		// Aggro is distance-only (pygame enemies.py): pursuit around corners is
		// deliberately ungated by LOS; only attacks trace a firing line.
		lure, lured := ambush_lure_position(run, &enemy)
		in_aggro := dist <= enemy.aggro_range || lured
		if in_aggro {
			alert_enemy(run, &enemy, player.pos)
		} else if enemy.ai == .Chase {
			// Out of aggro: drift toward the remembered position, then stand down.
			enemy.alert_timer = max(0, enemy.alert_timer - dt)
			toward_memory := enemy.memory - enemy.pos
			memory_distance := math.hypot(toward_memory.x, toward_memory.y)
			if enemy.alert_timer <= 0 || memory_distance <= ENEMY_MEMORY_ARRIVE_DISTANCE {
				enemy.ai = .Idle
				continue
			}
			drift := toward_memory / memory_distance
			enemy.facing = drift
			step := min(
				enemy.speed * dt * enemy_status_move_factor(&enemy),
				memory_distance - ENEMY_MEMORY_ARRIVE_DISTANCE * 0.5,
			)
			if step > 0 do _ = enemy_move(run, &enemy, drift * step)
			continue
		} else {
			continue
		}

		if dist > 1e-4 do enemy.facing = to_player / dist
		if lured {
			toward := lure - enemy.pos
			lure_distance := math.hypot(toward.x, toward.y)
			if lure_distance > .05 {
				enemy.facing = toward / lure_distance
				chase_step_to(run, &enemy, lure, dt)
			}
			continue
		}
		update_stuck_probe(run, &enemy, dist, dt)
		if enemy.role == .Boss {
			tick_boss_chase(run, &enemy, dist, dt)
		} else if try_start_ability(run, &enemy, dist) {
			// Non-boss authored abilities keep the fixed-order early gate.
		} else if enemy.ranged {
			tick_ranged_chase(run, &enemy, dist, dt)
		} else {
			tick_melee_chase(run, &enemy, dist, dt)
		}
	}
	separate_enemies(run)
	// Contact separation can still push a wide boss footprint into the seal; the
	// second pass restores it without delaying initial engagement until after AI.
	tick_boss_encounter(run)
	// Finalize locomotion after contact separation so `moving` and phase always
	// describe real ground displacement, never merely an attempted chase.
	for &enemy in run.enemies {
		if enemy.hp <= 0 {
			enemy.moving = false
			continue
		}
		delta := enemy.pos - enemy.prev_pos
		distance := math.hypot(delta.x, delta.y)
		enemy.moving = distance > 0
		enemy.anim_time += walk_animation_advance(
			SIM_DT,
			enemy.speed,
			distance,
			enemy.speed * SIM_DT,
		)
	}
}

@(private = "file")
tick_enemy_story_target :: proc(run: ^Run, enemy: ^Enemy, target: Story_Combat_Target, dt: f32) -> bool {
	if target.kind == .None || !story_combat_target_alive(run, target) do return false
	delta := target.pos - enemy.pos
	distance := math.hypot(delta.x, delta.y)
	if distance > enemy.aggro_range do return false
	alert_enemy(run, enemy, target.pos)
	if distance > .001 do enemy.facing = delta / distance
	if enemy.ai == .Windup do return true
	if enemy.ranged {
		tactic := enemy_tactic_def(enemy)
		if distance > tactic.preferred_range {
			step := min(enemy.speed * dt * enemy_status_move_factor(enemy), distance - tactic.preferred_range)
			if step > 0 do _ = enemy_move(run, enemy, enemy.facing * step)
		} else if distance < tactic.min_range {
			step := min(enemy.speed * dt * enemy_status_move_factor(enemy), tactic.min_range - distance)
			_ = enemy_move(run, enemy, -enemy.facing * step)
		}
		if distance <= enemy.attack_range && enemy.cooldown <= 0 &&
			line_of_sight(&run.dungeon, enemy.pos.x, enemy.pos.y, target.pos.x, target.pos.y) {
			enemy.story_target_kind = target.kind
			enemy.story_target_index = target.guest_index
			enemy_begin_windup(enemy, ENEMY_CAST_WINDUP, PENDING_BASE_ATTACK, target.pos - enemy.pos)
		}
	} else {
		stop := melee_stop_distance(enemy)
		if distance > stop {
			step := min(enemy.speed * dt * enemy_status_move_factor(enemy), distance - stop)
			if step > 0 do _ = enemy_move(run, enemy, enemy.facing * step)
		}
		if distance <= enemy.attack_range && enemy.cooldown <= 0 &&
			line_of_sight(&run.dungeon, enemy.pos.x, enemy.pos.y, target.pos.x, target.pos.y) {
			enemy.story_target_kind = target.kind
			enemy.story_target_index = target.guest_index
			enemy_begin_windup(enemy, ENEMY_MELEE_WINDUP, PENDING_BASE_ATTACK, target.pos - enemy.pos)
		}
	}
	return true
}

enemy_action_progress :: proc(enemy: ^Enemy) -> f32 {
	if enemy == nil || enemy.action_kind == .None || enemy.action_duration <= 0 do return 0
	return clamp(1 - enemy.action_timer / enemy.action_duration, f32(0), f32(1))
}

enemy_start_visual_action :: proc(enemy: ^Enemy, kind: Enemy_Action_Kind) {
	if enemy == nil || kind == .None do return
	enemy.action_kind = kind
	enemy.action_timer = ENEMY_ATTACK_ACTION_SECONDS
	enemy.action_duration = ENEMY_ATTACK_ACTION_SECONDS
}

enemy_action_kind_for_pending :: proc(enemy: ^Enemy, pending: int) -> Enemy_Action_Kind {
	if enemy == nil do return .None
	if pending >= 0 && pending < enemy.ability_count {
		effect := ABILITY_DEFS[enemy.abilities[pending]].effect
		return effect == .Strike ? Enemy_Action_Kind.Attack : Enemy_Action_Kind.Cast
	}
	if pending == PENDING_LEGACY_MELEE do return .Attack
	if pending == PENDING_LEGACY_CAST || enemy.ranged do return .Cast
	return .Attack
}

enemy_begin_windup :: proc(
	enemy: ^Enemy,
	duration: f32,
	pending_ability: int,
	aim: Vec2,
) {
	if enemy == nil do return
	enemy.ai = .Windup
	enemy.windup = max(0, duration)
	enemy.windup_duration = enemy.windup
	enemy.action_time = 0
	enemy.pending_ability = pending_ability
	enemy.windup_aim = linalg.normalize0(aim)
	if enemy.windup_aim != {} do enemy.facing = enemy.windup_aim
}

// Authored abilities fire ahead of the base attack whenever one is off
// cooldown and the target sits inside its range band.
@(private = "file")
try_start_ability :: proc(run: ^Run, enemy: ^Enemy, dist: f32) -> bool {
	if enemy.cooldown > 0 do return false
	for i in 0 ..< enemy.ability_count {
		if enemy.ability_cds[i] > 0 do continue
		ab := ABILITY_DEFS[enemy.abilities[i]]
		reach := ab.attack_range > 0 ? ab.attack_range : enemy.attack_range
		if dist > reach || dist < ab.min_range do continue
		if !enemy_sees_player(run, enemy) do continue
		duration := ab.windup > 0 ? ab.windup : (ab.effect == .Strike ? ENEMY_MELEE_WINDUP : ENEMY_CAST_WINDUP)
		enemy_begin_windup(enemy, duration, i, run.player.pos - enemy.pos)
		return true
	}
	return false
}

// content/enemies.py enemy_tactic: a ranged enemy whose doctrine carries no
// band (elite overrides to flanker/guard) drops to the default ranged band and
// loses strafe/reposition — an authored consequence, not an accident.
@(private = "file")
enemy_tactic_def :: proc(enemy: ^Enemy) -> Tactic_Def {
	t := TACTIC_DEFS[enemy.tactic]
	if enemy.ranged && t.preferred_range <= 0 do return DEFAULT_RANGED_TACTIC
	return t
}

@(private = "file")
enemy_move :: proc(run: ^Run, enemy: ^Enemy, delta: Vec2) -> f32 {
	before := enemy.pos
	slide_move(&run.dungeon, &enemy.pos, delta, radius = enemy_move_radius(enemy))
	step := enemy.pos - before
	moved := math.hypot(step.x, step.y)
	if moved > 0 do enemy.moving = true
	return moved
}

// combat/enemies.py _contact_packmate: the single nearest living packmate
// pressed within touching distance (+0.15 slack).
@(private = "file")
contact_packmate :: proc(run: ^Run, enemy: ^Enemy) -> ^Enemy {
	r := enemy_hit_radius(enemy)
	best: ^Enemy
	best_sq := f32(1e30)
	for &other in run.enemies {
		if &other == enemy || other.hp <= 0 do continue
		d := other.pos - enemy.pos
		d_sq := d.x * d.x + d.y * d.y
		reach := r + enemy_hit_radius(&other) + 0.15
		if d_sq > reach * reach || d_sq <= 1e-9 do continue
		if d_sq < best_sq {
			best_sq = d_sq
			best = &other
		}
	}
	return best
}

// Yield only to a packmate strictly closer to the player: distance is the
// whole arbitration rule, ties resolve through the perpendicular slide.
@(private = "file")
arm_yield_if_behind :: proc(run: ^Run, enemy: ^Enemy) {
	blocker := contact_packmate(run, enemy)
	if blocker == nil do return
	b := blocker.pos - run.player.pos
	m := enemy.pos - run.player.pos
	if b.x * b.x + b.y * b.y < m.x * m.x + m.y * m.y - 1e-6 {
		enemy.yield_timer = ENEMY_YIELD_SECONDS
	}
}

@(private = "file")
resolve_stalled_advance :: proc(run: ^Run, enemy: ^Enemy, n: Vec2, step: f32) {
	if step <= 0 do return
	sign := enemy_strafe_sign(enemy)
	perp := Vec2{-n.y, n.x}
	for attempt in ([2]f32{sign, -sign}) {
		moved := enemy_move(run, enemy, perp * (attempt * step))
		if moved > step * 0.25 {
			enemy.strafe_sign = attempt
			return
		}
	}
	enemy.strafe_sign = -sign
	arm_yield_if_behind(run, enemy)
}

// combat/enemies.py _advance_enemy: yielding consumes the whole step; a
// mostly-blocked advance latches onto the nav field and slides sideways.
@(private = "file")
advance_enemy :: proc(run: ^Run, enemy: ^Enemy, dir, n: Vec2, step: f32) {
	if step <= 0 do return
	if enemy.yield_timer > 0 {
		if blocker := contact_packmate(run, enemy); blocker != nil {
			away := linalg.normalize0(enemy.pos - blocker.pos)
			if away == {} do away = -n
			moved := enemy_move(run, enemy, away * step)
			if moved <= step * 0.25 do _ = enemy_move(run, enemy, -n * step)
			return
		}
		enemy.yield_timer = 0
	}
	moved := enemy_move(run, enemy, dir * step)
	if step > 0.02 && moved < step * 0.3 {
		enemy.nav_latch = NAV_STALL_LATCH_SECONDS
		resolve_stalled_advance(run, enemy, n, step - moved)
	}
}

// combat/enemies.py _update_stuck_probe: 0.9 s net-displacement watchdog.
@(private = "file")
update_stuck_probe :: proc(run: ^Run, enemy: ^Enemy, dist, dt: f32) {
	if dist <= enemy.attack_range || enemy.yield_timer > 0 {
		enemy.stuck_probe_timer = 0
		return
	}
	if enemy.stuck_probe_timer <= 0 {
		enemy.stuck_probe = enemy.pos
		enemy.stuck_probe_timer = ENEMY_STUCK_PROBE_SECONDS
		return
	}
	enemy.stuck_probe_timer -= dt
	if enemy.stuck_probe_timer > 0 do return
	net := enemy.pos - enemy.stuck_probe
	net_sq := net.x * net.x + net.y * net.y
	threshold := max(f32(0.12), enemy.speed * ENEMY_STUCK_PROBE_SECONDS * 0.25)
	if net_sq >= threshold * threshold do return
	if blocker := contact_packmate(run, enemy); blocker != nil {
		b := blocker.pos - run.player.pos
		m := enemy.pos - run.player.pos
		if b.x * b.x + b.y * b.y < m.x * m.x + m.y * m.y - 1e-6 {
			enemy.yield_timer = ENEMY_YIELD_SECONDS
			return
		}
	}
	enemy.nav_latch = NAV_STALL_LATCH_SECONDS
}

// combat/enemies.py _separation_adjusted_direction: bend a greedy approach
// away from the single nearest crowding packmate.
@(private = "file")
separation_adjusted_direction :: proc(run: ^Run, enemy: ^Enemy, n: Vec2) -> Vec2 {
	if len(run.enemies) <= 1 do return n
	r := enemy_hit_radius(enemy)
	best_sq := f32(1e30)
	away: Vec2
	found := false
	for &other in run.enemies {
		if &other == enemy || other.hp <= 0 do continue
		d := enemy.pos - other.pos
		d_sq := d.x * d.x + d.y * d.y
		limit := (r + enemy_hit_radius(&other)) * ENEMY_SEPARATION_FRACTION
		if d_sq < limit * limit && d_sq < best_sq {
			best_sq = d_sq
			away = d
			found = true
		}
	}
	if !found || best_sq <= 1e-9 do return n
	v := n + linalg.normalize0(away) * ENEMY_SEPARATION_BIAS
	out := linalg.normalize0(v)
	return out == {} ? n : out
}

@(private = "file")
flank_adjusted_direction :: proc(enemy: ^Enemy, n: Vec2, bias: f32) -> Vec2 {
	sign := enemy_strafe_sign(enemy)
	v := Vec2{n.x - n.y * bias * sign, n.y + n.x * bias * sign}
	out := linalg.normalize0(v)
	return out == {} ? n : out
}

// combat/enemies.py _reposition_for_line_of_sight: probe one tile out on each
// flank for a spot that both stands and sees; success consumes the tick.
@(private = "file")
reposition_for_line_of_sight :: proc(run: ^Run, enemy: ^Enemy, n: Vec2, dt: f32) -> bool {
	perp := Vec2{-n.y, n.x}
	sign := enemy_strafe_sign(enemy)
	for side in ([2]f32{sign, -sign}) {
		cand := enemy.pos + perp * side
		if blocked_for_radius(&run.dungeon, cand.x, cand.y, ACTOR_MOVE_COLLISION_RADIUS) do continue
		if !line_of_sight(&run.dungeon, cand.x, cand.y, run.player.pos.x, run.player.pos.y) do continue
		step := enemy.speed * dt * enemy_status_move_factor(enemy)
		moved := enemy_move(run, enemy, perp * (side * step))
		if moved <= step * 0.25 do enemy.strafe_sign = -sign
		return true
	}
	return false
}

// Branch D (combat/enemies.py:790-826): melee doctrines close to a stop
// distance, flankers curve in, greedy approaches fan around packmates.
@(private = "file")
tick_melee_chase :: proc(run: ^Run, enemy: ^Enemy, dist, dt: f32) {
	t := enemy_tactic_def(enemy)
	n := linalg.normalize0(run.player.pos - enemy.pos)
	stop := melee_stop_distance(enemy)
	if dist > stop {
		dir, routed := enemy_nav_direction(run, enemy)
		if !routed {
			dir = n
			if t.strafe_bias > 0 && dist > stop + 1.0 {
				dir = flank_adjusted_direction(enemy, dir, t.strafe_bias)
			}
			dir = separation_adjusted_direction(run, enemy, dir)
		}
		step := min(enemy.speed * dt * enemy_status_move_factor(enemy), dist - stop)
		advance_enemy(run, enemy, dir, n, step)
	}
	if dist <= enemy.attack_range && enemy.cooldown <= 0 && enemy_sees_player(run, enemy) {
		enemy_begin_windup(enemy, ENEMY_MELEE_WINDUP, PENDING_BASE_ATTACK, n)
	}
}

// Branch C (combat/enemies.py:723-789): the ranged doctrine core — advance,
// backpedal, cooldown strafe, and LOS repositioning are mutually exclusive.
@(private = "file")
tick_ranged_chase :: proc(run: ^Run, enemy: ^Enemy, dist, dt: f32) {
	t := enemy_tactic_def(enemy)
	n := linalg.normalize0(run.player.pos - enemy.pos)
	attack_ready := enemy.cooldown <= 0
	in_attack_range := dist <= enemy.attack_range
	los_checked := attack_ready && in_attack_range
	los_clear := los_checked && enemy_sees_player(run, enemy)
	move_step := enemy.speed * dt * enemy_status_move_factor(enemy)

	repositioned := false
	if los_checked && !los_clear && t.reposition_for_los {
		repositioned = reposition_for_line_of_sight(run, enemy, n, dt)
	}
	holding := t.hold_anchor && in_attack_range
	if repositioned {
		// sidestep consumed this tick's movement
	} else if dist > t.preferred_range {
		if !holding {
			dir, routed := enemy_nav_direction(run, enemy)
			if !routed do dir = separation_adjusted_direction(run, enemy, n)
			step := min(move_step, dist - t.preferred_range)
			advance_enemy(run, enemy, dir, n, step)
		}
	} else if dist < t.min_range {
		// Straight backpedal at full speed: no separation, no routing.
		step := min(move_step, t.min_range - dist)
		_ = enemy_move(run, enemy, -n * step)
	} else if t.strafe_bias > 0 && !attack_ready {
		sign := enemy_strafe_sign(enemy)
		step := move_step * t.strafe_bias
		moved := enemy_move(run, enemy, Vec2{-n.y, n.x} * (sign * step))
		if moved <= step * 0.25 do enemy.strafe_sign = -sign
	}

	if in_attack_range && attack_ready && los_clear {
		enemy_begin_windup(enemy, ENEMY_CAST_WINDUP, PENDING_BASE_ATTACK, n)
	}
}

// combat/abilities.py _ability_attack_range: authored range wins; boss bolt/fan
// abilities inherit at least the six-tile cast reach.
@(private = "file")
boss_ability_reach :: proc(enemy: ^Enemy, ab: ^Ability_Def) -> f32 {
	if ab.attack_range > 0 do return ab.attack_range
	if ab.effect == .Bolt || ab.effect == .Fan do return max(f32(BOSS_CAST_MAX_RANGE), enemy.attack_range)
	return enemy.attack_range
}

Boss_Attack_Choice :: enum {
	None,
	Ability,
	Legacy_Cast,
	Legacy_Melee,
}

// combat/abilities.py select_boss_attack: deterministic and RNG-free. Bands
// are strict below, inclusive above. The rotation is a soft preference for the
// first authored slot that is not the last one fired.
select_boss_attack :: proc(enemy: ^Enemy, dist: f32) -> (choice: Boss_Attack_Choice, slot: int) {
	candidates: [2]int
	count := 0
	for i in 0 ..< enemy.ability_count {
		if enemy.ability_cds[i] > 0 do continue
		ab := &ABILITY_DEFS[enemy.abilities[i]]
		if !(ab.min_range < dist && dist <= boss_ability_reach(enemy, ab)) do continue
		candidates[count] = i
		count += 1
	}
	if count > 0 {
		for i in 0 ..< count {
			if candidates[i] != enemy.last_ability do return .Ability, candidates[i]
		}
		return .Ability, candidates[0]
	}
	if BOSS_CAST_MIN_RANGE < dist && dist <= BOSS_CAST_MAX_RANGE do return .Legacy_Cast, -1
	if dist <= enemy.attack_range do return .Legacy_Melee, -1
	return .None, -1
}

// Branch B (combat/enemies.py:693-722): bosses ignore doctrine bands — close
// to melee stop, then commit whatever the selector chose with the pre-movement
// aim, so the tell points where the target stood when the decision was made.
@(private = "file")
tick_boss_chase :: proc(run: ^Run, enemy: ^Enemy, dist, dt: f32) {
	choice, slot := select_boss_attack(enemy, dist)
	aim := run.player.pos - enemy.pos
	stop := melee_stop_distance(enemy)
	if dist > stop {
		dir := separation_adjusted_direction(run, enemy, linalg.normalize0(aim))
		step := min(enemy.speed * dt * enemy_status_move_factor(enemy), dist - stop)
		_ = enemy_move(run, enemy, dir * step)
	}
	if choice == .None || enemy.cooldown > 0 do return
	if !enemy_sees_player(run, enemy) do return
	switch choice {
	case .Ability:
		ab := ABILITY_DEFS[enemy.abilities[slot]]
		duration := ab.windup > 0 ? ab.windup : f32(ENEMY_BOSS_WINDUP)
		enemy_begin_windup(enemy, duration, slot, aim)
	case .Legacy_Cast:
		enemy_begin_windup(enemy, ENEMY_BOSS_WINDUP, PENDING_LEGACY_CAST, aim)
	case .Legacy_Melee:
		enemy_begin_windup(enemy, ENEMY_BOSS_WINDUP, PENDING_LEGACY_MELEE, aim)
	case .None:
	}
}

@(private = "file")
chase_step_to :: proc(run: ^Run, enemy: ^Enemy, target: Vec2, dt: f32) {
	dir := linalg.normalize0(target - enemy.pos)
	before := enemy.pos
	slide_move(&run.dungeon, &enemy.pos, dir * (enemy.speed * dt * enemy_status_move_factor(enemy)), radius=enemy_move_radius(enemy))
	enemy.moving = enemy.pos != before
}

@(private = "file")
commit_enemy_attack :: proc(run: ^Run, enemy: ^Enemy) {
	if enemy.story_target_kind != .None {
		target := Story_Combat_Target{kind = enemy.story_target_kind, guest_index = enemy.story_target_index}
		if target.kind == .Guest && 0 <= target.guest_index && target.guest_index < len(run.story_runtime.guests) {
			target.pos = run.story_runtime.guests[target.guest_index].pos
		} else if target.kind == .Soul {
			target.pos = run.story_runtime.soul.pos
		}
		enemy.story_target_kind = .None
		enemy.story_target_index = -1
		if story_combat_target_alive(run, target) {
			enemy_start_visual_action(enemy, enemy.ranged ? .Cast : .Attack)
			if enemy.ranged {
				spawn_enemy_bolt(run, enemy, enemy.windup_aim, enemy.damage, ENEMY_BOLT_SPEED, 0, enemy.damage_type, {}, false, 0)
				append(&run.sfx, Sfx_Kind.Bolt)
			} else {
				raw := enemy.damage + rng_range(&run.combat_rng, -2, 3)
				_ = story_damage_combat_target(run, target, raw)
				feel_emit_enemy_slash(run, (enemy.pos + target.pos) * .5, enemy.windup_aim, enemy.color)
			}
			return
		}
	}
	aim := enemy.windup_aim
	if aim == {} do aim = linalg.normalize0(run.player.pos - enemy.pos)
	if aim == {} do aim = enemy.facing
	pending := enemy.pending_ability
	enemy_start_visual_action(enemy, enemy_action_kind_for_pending(enemy, pending))
	if pending >= 0 && pending < enemy.ability_count {
		idx := pending
		enemy.pending_ability = PENDING_BASE_ATTACK
		commit_ability(run, enemy, idx, aim)
		return
	}
	legacy_cast := pending == PENDING_LEGACY_CAST
	legacy_melee := pending == PENDING_LEGACY_MELEE
	enemy.pending_ability = PENDING_BASE_ATTACK
	if !legacy_melee && (enemy.ranged || legacy_cast) {
		feel_emit_enemy_cast(run, enemy, .36)
		status: Status_Kind
		has_status := false
		duration: f32
		if enemy.damage_type == .Frost {status, has_status, duration = .Chilled, true, .9}
		if enemy.big || legacy_cast {
			spreads := [3]f32{-0.28, 0, 0.28}
			for spread in spreads {
				spawn_enemy_bolt(run, enemy, aim, enemy.damage, ENEMY_BOLT_SPEED, spread, enemy.damage_type, status, has_status, duration)
			}
		} else {
			spawn_enemy_bolt(run, enemy, aim, enemy.damage, ENEMY_BOLT_SPEED, 0, enemy.damage_type, status, has_status, duration)
		}
		append(&run.sfx, Sfx_Kind.Bolt)
		return
	}
	// Once the tell starts, pygame commits the melee hit. Walking out during
	// the short windup does not silently cancel it; defensive actions counter it.
	feel_emit_enemy_slash(run, (enemy.pos + run.player.pos) * .5, aim, enemy.color)
	raw := enemy.damage + rng_range(&run.combat_rng, -2, 3)
	dealt := damage_player_typed(run, raw, enemy.damage_type, melee=true, attacker=enemy)
	if dealt > 0 && enemy.damage_type == .Poison do player_apply_status(&run.player, .Poisoned, 1.4)
	if dealt > 0 && enemy.damage_type == .Frost do player_apply_status(&run.player, .Chilled, .9)
	thorns := player_thorns(&run.player)
	if dealt > 0 && thorns > 0 {
		reflected := max(1, thorns + dealt / 8)
		_ = damage_enemy_direct(run, enemy, reflected, .Physical)
	}
}

@(private = "file")
commit_ability :: proc(run: ^Run, enemy: ^Enemy, idx: int, aim: Vec2) {
	ab := ABILITY_DEFS[enemy.abilities[idx]]
	// Boss phase pressure: below half health the rotation recycles faster.
	// Applied at fire time only; running timers are never rewritten.
	phase: f32 = f32(enemy.hp) < f32(enemy.max_hp) * BOSS_PHASE_HP_FRACTION ? BOSS_PHASE_COOLDOWN_FACTOR : 1
	enemy.ability_cds[idx] = ab.cooldown * phase
	enemy.last_ability = idx
	dmg := max(1, int(math.round(f32(enemy.damage) * ab.dmg_mult)))
	reach := ab.attack_range > 0 ? ab.attack_range : enemy.attack_range

	switch ab.effect {
	case .Strike:
		feel_emit_enemy_slash(run, (enemy.pos + run.player.pos) * .5, aim, enemy.color)
		raw := dmg + rng_range(&run.combat_rng, -2, 3)
		dealt := damage_player_typed(run, raw, enemy.damage_type, melee=true, attacker=enemy)
		if dealt > 0 && ab.has_status do player_apply_status(&run.player, ab.status, ab.status_duration)
		thorns := player_thorns(&run.player)
		if dealt > 0 && thorns > 0 do _ = damage_enemy_direct(run, enemy, max(1, thorns+dealt/8), .Physical)
	case .Bolt:
		feel_emit_enemy_cast(run, enemy, .36)
		spawn_enemy_bolt(run, enemy, aim, dmg, ab.proj_speed, 0, enemy.damage_type, ab.status, ab.has_status, ab.status_duration)
		append(&run.sfx, Sfx_Kind.Bolt)
	case .Fan:
		feel_emit_enemy_cast(run, enemy, .36)
		count := max(1, ab.proj_count)
		for k in 0 ..< count {
			offset: f32 = 0
			if count > 1 {
				offset = ab.spread * (f32(k) / f32(count - 1) * 2 - 1)
			}
			spawn_enemy_bolt(run, enemy, aim, dmg, ab.proj_speed, offset, enemy.damage_type, ab.status, ab.has_status, ab.status_duration)
		}
		append(&run.sfx, Sfx_Kind.Bolt)
	case .Nova:
		feel_emit_enemy_nova(run, enemy, reach)
		to := run.player.pos - enemy.pos
		d := math.hypot(to.x, to.y)
		if d <= reach && enemy_sees_player(run, enemy) {
			raw := dmg + rng_range(&run.combat_rng, -2, 3)
			dealt := damage_player_typed(run, raw, enemy.damage_type)
			if dealt > 0 && ab.has_status do player_apply_status(&run.player, ab.status, ab.status_duration)
		}
		guest_limit := min(len(run.story_runtime.guests), STORY_BEAT_COUNT)
		for i in 0 ..< guest_limit {
			guest := &run.story_runtime.guests[i]
			if guest.depth != run.depth || guest.witness || !guest.ally || !guest.alive || guest.hp <= 0 do continue
			delta := guest.pos - enemy.pos
			if math.hypot(delta.x, delta.y) > reach || !line_of_sight(&run.dungeon, enemy.pos.x, enemy.pos.y, guest.pos.x, guest.pos.y) do continue
			_ = story_damage_combat_target(run, {kind = .Guest, guest_index = i, pos = guest.pos}, dmg + rng_range(&run.combat_rng, -2, 3))
		}
		soul := &run.story_runtime.soul
		if soul.present && soul.armed && soul.alive && soul.hp > 0 {
			delta := soul.pos - enemy.pos
			if math.hypot(delta.x, delta.y) <= reach && line_of_sight(&run.dungeon, enemy.pos.x, enemy.pos.y, soul.pos.x, soul.pos.y) {
				_ = story_damage_combat_target(run, {kind = .Soul, guest_index = -1, pos = soul.pos}, dmg + rng_range(&run.combat_rng, -2, 3))
			}
		}
		append(&run.sfx, Sfx_Kind.Bolt)
	}
}

@(private = "file")
spawn_enemy_bolt :: proc(
	run: ^Run, enemy: ^Enemy, aim: Vec2, dmg: int, speed: f32, spread_offset: f32,
	damage_type: Damage_Type, status: Status_Kind, has_status: bool, status_duration: f32,
) {
	dir := linalg.normalize0(aim)
	if dir == {} do return
	if spread_offset != 0 do dir += Vec2{-dir.y, dir.x} * spread_offset
	append(&run.projectiles, Projectile{
		owner_id = u64(enemy.entity_id),
		pos = enemy.pos,
		prev_pos = enemy.pos,
		vel = dir * (speed > 0 ? speed : ENEMY_BOLT_SPEED),
		damage = dmg,
		damage_type = damage_type,
		status = status,
		has_status = has_status,
		status_duration = status_duration,
		visual = .Enemy_Void,
		ttl = ENEMY_PROJECTILE_TTL,
		color = DAMAGE_TYPE_COLORS[damage_type],
	})
}

BOSS_ARENA_CLEARANCE_PAD :: f32(0.12)

// Keep the complete movement footprint within either the room's true bounds or
// its non-perimeter waiting band. Before engagement the inset keeps a guardian
// off open thresholds; after sealing, true bounds avoid snapping combat away
// from otherwise valid non-door edges while geometry rejects closed openings.
@(private = "file")
room_contains_arena_footprint :: proc(
	room: Room,
	position: Vec2,
	radius: f32,
	inset_perimeter: bool = false,
) -> bool {
	inset: f32 = inset_perimeter ? 1 : 0
	left := f32(room.x) + inset
	top := f32(room.y) + inset
	right := f32(room.x + room.w) - inset
	bottom := f32(room.y + room.h) - inset
	return position.x - radius >= left && position.x + radius <= right &&
		position.y - radius >= top && position.y + radius <= bottom
}

// Rescue destinations must be clear not only of geometry but of every living
// actor. This check is intentionally limited to teleport/rescue candidates so
// ordinary combat proximity never makes the boss watchdog teleport actors.
@(private = "file")
arena_rescue_candidate_clear :: proc(
	run: ^Run,
	candidate: Vec2,
	actor_radius: f32,
	ignored_enemy: ^Enemy = nil,
	avoid_player: bool = false,
) -> bool {
	if avoid_player {
		gap := candidate - run.player.pos
		minimum_gap := actor_radius + PLAYER_HIT_RADIUS + BOSS_ARENA_CLEARANCE_PAD
		if gap.x * gap.x + gap.y * gap.y < minimum_gap * minimum_gap do return false
	}
	for &enemy in run.enemies {
		if enemy.hp <= 0 || (ignored_enemy != nil && &enemy == ignored_enemy) do continue
		gap := candidate - enemy.pos
		minimum_gap := actor_radius + enemy_hit_radius(&enemy) + BOSS_ARENA_CLEARANCE_PAD
		if gap.x * gap.x + gap.y * gap.y < minimum_gap * minimum_gap do return false
	}
	return true
}

// Interior tile centers are deterministic rescue anchors. The nearest valid
// center wins; x/y scan order is the stable tie-breaker. Keeping the whole
// movement footprint inside clear geometry matters because movement validates
// only destinations—an actor starting inside a closed door cannot escape it.
@(private = "file")
find_boss_arena_safe_position :: proc(
	run: ^Run,
	room: Room,
	from: Vec2,
	geometry_radius: f32,
	actor_radius: f32,
	block_stairs: bool,
	ignored_enemy: ^Enemy = nil,
	avoid_player: bool = false,
	inset_perimeter: bool = false,
) -> (position: Vec2, found: bool) {
	best_distance_sq := max(f32)
	for x in room.x + 1 ..< room.x + room.w - 1 {
		for y in room.y + 1 ..< room.y + room.h - 1 {
			candidate := Vec2{f32(x) + 0.5, f32(y) + 0.5}
			if !room_contains_arena_footprint(
				room,
				candidate,
				geometry_radius,
				inset_perimeter,
			) {
				continue
			}
			if blocked_for_radius(
				&run.dungeon,
				candidate.x,
				candidate.y,
				geometry_radius,
				block_stairs = block_stairs,
			) {
				continue
			}
			if !arena_rescue_candidate_clear(
				run,
				candidate,
				actor_radius,
				ignored_enemy,
				avoid_player,
			) {
				continue
			}
			delta := candidate - from
			distance_sq := delta.x * delta.x + delta.y * delta.y
			if found && distance_sq >= best_distance_sq do continue
			position, found, best_distance_sq = candidate, true, distance_sq
		}
	}
	return
}

@(private = "file")
ensure_boss_safe_in_arena :: proc(
	run: ^Run,
	room: Room,
	boss: ^Enemy,
	inset_perimeter: bool = false,
) -> bool {
	if boss == nil do return false
	geometry_radius := enemy_move_radius(boss)
	if room_contains_arena_footprint(room, boss.pos, geometry_radius, inset_perimeter) &&
		!blocked_for_radius(&run.dungeon, boss.pos.x, boss.pos.y, geometry_radius) {
		return true
	}
	position, found := find_boss_arena_safe_position(
		run,
		room,
		boss.pos,
		geometry_radius,
		enemy_hit_radius(boss),
		false,
		ignored_enemy = boss,
		avoid_player = true,
		inset_perimeter = inset_perimeter,
	)
	if !found do return false
	boss.pos = position
	boss.prev_pos = position
	boss.knockback_vel = {}
	boss.moving = false
	return true
}

@(private = "file")
ensure_player_safe_in_arena :: proc(run: ^Run, room: Room, player: ^Player, boss: ^Enemy) -> bool {
	if player == nil || boss == nil do return false
	minimum_gap := PLAYER_HIT_RADIUS + enemy_hit_radius(boss) + BOSS_ARENA_CLEARANCE_PAD
	gap := player.pos - boss.pos
	safe := room_contains_point(room, player.pos.x, player.pos.y) &&
		!blocked_for_radius(&run.dungeon, player.pos.x, player.pos.y, PLAYER_HIT_RADIUS, block_stairs = true) &&
		gap.x * gap.x + gap.y * gap.y >= minimum_gap * minimum_gap
	if safe do return true
	position, found := find_boss_arena_safe_position(
		run,
		room,
		player.pos,
		PLAYER_HIT_RADIUS,
		PLAYER_HIT_RADIUS,
		true,
	)
	if !found do return false
	player.pos = position
	player.prev_pos = position
	player.moving = false
	return true
}

// Seal and actor rescue are one transaction. If a malformed/degenerate arena
// has no valid placement, restore every tile appended by this attempt and keep
// the encounter unengaged rather than marooning either actor in a closed door.
@(private = "file")
engage_boss_room :: proc(run: ^Run, room: Room, boss: ^Enemy) -> bool {
	if len(run.sealed) > 0 {
		restore_sealed(&run.dungeon, run.sealed[:])
		clear(&run.sealed)
	}
	sealed_start := len(run.sealed)
	sealed_count := seal_room_openings(&run.dungeon, room, &run.sealed)
	boss_pos, boss_prev := boss.pos, boss.prev_pos
	boss_moving, boss_knockback := boss.moving, boss.knockback_vel
	if !ensure_boss_safe_in_arena(run, room, boss) ||
		!ensure_player_safe_in_arena(run, room, &run.player, boss) {
		restore_sealed(&run.dungeon, run.sealed[sealed_start:sealed_start + sealed_count])
		resize(&run.sealed, sealed_start)
		boss.pos, boss.prev_pos = boss_pos, boss_prev
		boss.moving, boss.knockback_vel = boss_moving, boss_knockback
		refresh_visibility(run)
		return false
	}
	refresh_visibility(run)
	run.boss_engaged = true
	boss.ai = .Chase
	return true
}

@(private = "file")
unseal_failed_boss_arena :: proc(run: ^Run) {
	restore_sealed(&run.dungeon, run.sealed[:])
	clear(&run.sealed)
	run.boss_engaged = false
	refresh_visibility(run)
}

@(private = "file")
boss_encounter_room :: proc(run: ^Run, boss: ^Enemy) -> (room: Room, authoritative: bool, found: bool) {
	if run.dungeon.boss_arena && run.dungeon.room_count > 0 {
		return run.dungeon.rooms_buf[run.dungeon.room_count - 1], true, true
	}
	room, found = room_at(&run.dungeon, boss.pos.x, boss.pos.y)
	return room, false, found
}

@(private = "file")
boss_waiting_for_arena_entry :: proc(run: ^Run, boss: ^Enemy) -> bool {
	return boss != nil && boss.role == .Boss && boss.hp > 0 && !run.boss_engaged &&
		run.dungeon.boss_arena && run.dungeon.room_count > 0
}

// Boss encounters: the final authored room is authoritative from floor start,
// not only after engagement. The guardian is recovered there before AI runs;
// entering it seals its openings and the post-separation pass remains a
// watchdog for contact shoves onto the closed doors.
@(private = "file")
tick_boss_encounter :: proc(run: ^Run) {
	for &enemy in run.enemies {
		if enemy.role != .Boss || enemy.hp <= 0 do continue
		boss_room, authoritative, found := boss_encounter_room(run, &enemy)
		if !found do continue
		if run.boss_engaged {
			if !ensure_boss_safe_in_arena(run, boss_room, &enemy) do unseal_failed_boss_arena(run)
			return
		}
		if authoritative && !ensure_boss_safe_in_arena(
			run,
			boss_room,
			&enemy,
			inset_perimeter = true,
		) {
			return
		}
		if room_contains_point(boss_room, run.player.pos.x, run.player.pos.y) &&
			engage_boss_room(run, boss_room, &enemy) {
			append(&run.numbers, Damage_Number{pos = run.player.pos, kind = .Text, text = "The gate seals behind you..."})
			append(&run.sfx, Sfx_Kind.Door)
			append(&run.sfx, Sfx_Kind.Boss)
		}
		return
	}
}

@(private = "file")
enemy_sees_player :: proc(run: ^Run, enemy: ^Enemy) -> bool {
	return line_of_sight(
		&run.dungeon,
		enemy.pos.x, enemy.pos.y,
		run.player.pos.x, run.player.pos.y,
	)
}

// Pairwise push-apart so packs do not stack into one sprite, and enemies
// yield out of the player's footprint (the pygame resolve_actor_contacts
// includes the player). O(n^2) is fine at this population scale.
@(private = "file")
// MX.2.4: separation uses actual body radii per pairing instead of one fixed
// enemy radius. Pushes route through slide_move at each mover's own footprint
// radius, so walls stop them and the player (never pushed) cannot be shoved
// onto blocked stairs.
separate_enemies :: proc(run: ^Run) {
	for i in 0 ..< len(run.enemies) {
		if run.enemies[i].hp <= 0 do continue
		for j in i + 1 ..< len(run.enemies) {
			a := &run.enemies[i]
			b := &run.enemies[j]
			if b.hp <= 0 do continue
			min_dist := enemy_hit_radius(a) + enemy_hit_radius(b)
			delta := b.pos - a.pos
			dist := math.hypot(delta.x, delta.y)
			if dist >= min_dist || dist < 1e-4 do continue
			push := linalg.normalize0(delta) * ((min_dist - dist) * 0.5)
			slide_move(&run.dungeon, &a.pos, -push, radius = enemy_move_radius(a))
			slide_move(&run.dungeon, &b.pos, push, radius = enemy_move_radius(b))
		}
	}
	for &enemy in run.enemies {
		if enemy.hp <= 0 do continue
		min_dist := f32(PLAYER_HIT_RADIUS) + enemy_hit_radius(&enemy)
		delta := enemy.pos - run.player.pos
		dist := math.hypot(delta.x, delta.y)
		if dist >= min_dist || dist < 1e-4 do continue
		push := linalg.normalize0(delta) * (min_dist - dist)
		slide_move(&run.dungeon, &enemy.pos, push, radius = enemy_move_radius(&enemy))
	}
}

// combat/movement.py:293-375, the player-as-mover half of
// resolve_actor_contacts: a move never leaves the player overlapping an enemy
// body. The mover is placed back at contact distance along the pair normal,
// axis-separated against the same wall probe the move itself used, so walking
// neither shoves enemies nor climbs over a wall-pinned one. The enemy-as-mover
// half is separate_enemies above; the parity gap that let the player ram and
// stand on cornered enemies was this half missing (feedback 2026-08).
resolve_player_enemy_contacts :: proc(run: ^Run) {
	player := &run.player
	for &enemy in run.enemies {
		if enemy.hp <= 0 do continue
		min_dist := f32(PLAYER_HIT_RADIUS) + enemy_hit_radius(&enemy)
		delta := player.pos - enemy.pos
		dist_sq := delta.x * delta.x + delta.y * delta.y
		if dist_sq >= min_dist * min_dist do continue
		n: Vec2
		if dist_sq > 1e-6 {
			n = delta / math.sqrt(dist_sq)
		} else {
			// movement.py:341-344: stacked centers separate against the mover's
			// facing, east as the final fallback.
			n = -player.facing
			if math.hypot(n.x, n.y) <= 0.001 do n = {1, 0}
		}
		target := enemy.pos + n * min_dist
		if !blocked_for_radius(&run.dungeon, target.x, player.pos.y, block_stairs = true) {
			player.pos.x = target.x
		}
		if !blocked_for_radius(&run.dungeon, player.pos.x, target.y, block_stairs = true) {
			player.pos.y = target.y
		}
	}
}

// combat/enemies.py alert_enemy: engaging refreshes memory every frame; only
// the idle->engaged transition broadcasts, one hop, pure 4-tile circle.
alert_enemy :: proc(run: ^Run, enemy: ^Enemy, target: Vec2) {
	newly := enemy.ai == .Idle
	if enemy.ai != .Windup do enemy.ai = .Chase
	enemy.memory = target
	enemy.alert_timer = ENEMY_ALERT_MEMORY
	if !newly do return
	for &other in run.enemies {
		if &other == enemy || other.hp <= 0 || other.ai != .Idle do continue
		d := other.pos - enemy.pos
		if d.x * d.x + d.y * d.y <= f32(ENEMY_ALERT_RADIUS * ENEMY_ALERT_RADIUS) {
			other.ai = .Chase
			other.memory = target
			other.alert_timer = ENEMY_ALERT_MEMORY
		}
	}
}

// combat/enemies.py _chain_knockback_through_pack: heavy momentum passes to
// packmates in a forward cone at 0.85 transfer; 2x2 bosses never budge and a
// faster-moving packmate is never re-boosted. Physics only — no damage.
@(private = "file")
chain_knockback_through_pack :: proc(run: ^Run, enemy: ^Enemy, dt: f32) {
	speed := math.hypot(enemy.knockback_vel.x, enemy.knockback_vel.y)
	if speed < KNOCKBACK_CHAIN_MIN_SPEED do return
	n := enemy.knockback_vel / speed
	r := enemy_hit_radius(enemy)
	transferred := speed * KNOCKBACK_CHAIN_TRANSFER
	for &other in run.enemies {
		if &other == enemy || other.hp <= 0 || other.big do continue
		d := other.pos - enemy.pos
		dist := math.hypot(d.x, d.y)
		if dist > r + enemy_hit_radius(&other) + speed * dt do continue
		if dist > 0.001 && linalg.dot(d / dist, n) < KNOCKBACK_CHAIN_ARC_DOT do continue
		if math.hypot(other.knockback_vel.x, other.knockback_vel.y) >= transferred do continue
		enemy_start_knockback(run, &other, n * transferred)
	}
}

// Homing shards curve toward the nearest unhit foe in view; turn strength is
// the snapshotted per-cast homing factor (projectiles.py:263-313).
@(private = "file")
steer_homing_projectile :: proc(run: ^Run, p: ^Projectile) {
	best: ^Enemy
	best_distance_sq := f32(6.5 * 6.5)
	for &enemy in run.enemies {
		if enemy.hp <= 0 do continue
		enemy_id := enemy_ensure_id(run, &enemy)
		already_hit := false
		for hit_index in 0 ..< p.hit_enemy_count {
			if p.hit_enemy_ids[hit_index] == enemy_id do already_hit = true
		}
		if already_hit do continue
		d := enemy.pos - p.pos
		distance_sq := d.x * d.x + d.y * d.y
		if distance_sq >= best_distance_sq do continue
		if !line_of_sight(&run.dungeon, p.pos.x, p.pos.y, enemy.pos.x, enemy.pos.y) do continue
		best, best_distance_sq = &enemy, distance_sq
	}
	if best == nil do return
	speed := linalg.length(p.vel)
	current := linalg.normalize0(p.vel)
	desired := linalg.normalize0(best.pos - p.pos)
	if speed <= 0 || current == {} || desired == {} do return
	turn := p.homing * SIM_DT * 6.0
	blended := linalg.normalize0(current + (desired - current) * turn)
	if blended != {} do p.vel = blended * speed
}

@(private = "file")
tick_projectiles :: proc(run: ^Run) {
	player := &run.player
	#reverse for &p, i in run.projectiles {
		if p.from_player && p.homing > 0 do steer_homing_projectile(run, &p)
		p.prev_pos = p.pos
		p.pos += p.vel * SIM_DT
		p.visual_age += SIM_DT
		p.ttl -= SIM_DT

		remove := p.ttl <= 0 || !is_floor(&run.dungeon, p.pos.x, p.pos.y)
		if !remove {
			if p.from_player {
				for &enemy in run.enemies {
					if enemy.hp <= 0 do continue
					enemy_id := enemy_ensure_id(run, &enemy)
					already_hit := false
					for hit_index in 0 ..< p.hit_enemy_count {
						if p.hit_enemy_ids[hit_index] == enemy_id do already_hit = true
					}
					if already_hit do continue
					d := enemy.pos - p.pos
					hit_radius := PLAYER_PROJECTILE_HIT_RADIUS + enemy_hit_radius(&enemy) - ENEMY_HIT_RADIUS
					if math.hypot(d.x, d.y) <= hit_radius {
						_ = player_damage_enemy(run, &enemy, p.damage, p.damage_type, p.status, p.has_status, p.status_duration)
						// MX.2.4: projectiles nudge like melee (projectiles.py:102).
						if bolt_dir := linalg.normalize0(p.vel); bolt_dir != {} {
							enemy_start_knockback(run, &enemy, bolt_dir * KNOCKBACK_SPEED)
						}
						if player.archetype == .Acolyte && player.hp < player.max_hp {
							if leech := acolyte_spell_leech(player); leech > 0 {
								heal := min(player.max_hp - player.hp, leech)
								player.hp += heal
								append(&run.numbers, Damage_Number{pos=player.pos, value=heal, kind=.Heal})
							}
						}
						// The cast's one Storm charge is spent by the earliest
						// impact of any shard, chained or not (projectiles.py:99-104).
						if p.storm_chain {
							cast_id := p.storm_cast
							for &shard in run.projectiles {
								if shard.storm_chain && shard.storm_cast == cast_id do shard.storm_chain = false
							}
							resolve_storm_chain(run, &p, &enemy)
						}
						if p.pierce > 0 {
							if p.hit_enemy_count < len(p.hit_enemy_ids) {
								p.hit_enemy_ids[p.hit_enemy_count] = enemy_id
								p.hit_enemy_count += 1
							}
							p.pierce -= 1
							falloff: f32 = player.archetype == .Arcanist && player_has_discipline(player, .Arcanist_Storm) ? 0.82 : 0.70
							p.damage = max(1, int(f32(p.damage) * falloff))
						} else {
							remove = true
						}
						break
					}
				}
			} else {
				if familiar := familiar_intercepting_projectile(run, p.pos); familiar != nil {
					familiar_take_damage(familiar, p.damage)
					remove = true
				} else if story_target, found := story_projectile_target(run, p.pos); found {
					_ = story_damage_combat_target(run, story_target, p.damage)
					remove = true
				} else {
					d := player.pos - p.pos
					if math.hypot(d.x, d.y) <= ENEMY_PROJECTILE_HIT_RADIUS {
						dealt := damage_player_typed(run, p.damage, p.damage_type, source_id="enemy_projectile")
						if dealt > 0 && p.has_status do player_apply_status(player, p.status, p.status_duration)
						remove = true
					}
				}
			}
		}
		if remove do unordered_remove(&run.projectiles, i)
	}
}

@(private = "file")
tick_numbers :: proc(run: ^Run) {
	#reverse for &n, i in run.numbers {
		n.age += SIM_DT
		if n.age >= DAMAGE_NUMBER_SECONDS do unordered_remove(&run.numbers, i)
	}
}

// Kills pay out xp, gold, and a 28% loot roll from the floor's loot stream.
// Boss deaths break the arena seal; the Tyrant's death opens the way to
// victory (claimed at the stairs).
@(private = "file")
sweep_dead_enemies :: proc(run: ^Run) {
	#reverse for &enemy, i in run.enemies {
		if enemy.hp <= 0 {
			accent := THEMES[clamp(run.theme_index, 0, len(THEMES) - 1)].accent
			feel_emit_enemy_death(run, &enemy, accent)
			// Eternal Moment: kills during Time Skip refund ~40% of the slot's
			// cooldown, recomputed live (damage.py:265-275).
			if run.player.archetype == .Warden && run.player.time_skip_timer > 0 &&
				run.player.class_skill_timer > 0 &&
				player_has_discipline(&run.player, .Warden_Eternal_Wall) {
				run.player.class_skill_timer = max(0, run.player.class_skill_timer - player_class_skill_cooldown(&run.player) * 0.4)
			}
			// Grave echo: killing a still-bound foe while wounded restores
			// health and a sip of mana (damage.py:368-386).
			if run.player.archetype == .Acolyte && enemy.statuses[.Bound] > 0 &&
				player_has_discipline(&run.player, .Acolyte_Gravebind) {
				echo := min(run.player.max_hp - run.player.hp, 4 + run.depth / 2)
				if echo > 0 {
					run.player.hp += echo
					run.player.mana = min(f32(run.player.max_mana), run.player.mana + 2)
					append(&run.numbers, Damage_Number{pos = run.player.pos, value = echo, kind = .Heal})
					append(&run.numbers, Damage_Number{pos = enemy.pos, kind = .Text, text = "Grave echo"})
				}
			}
			xp_bonus := story_effect_clamped(run, .XP_Bonus, 0, .35)
			player_gain_xp(run, max(1, int(f32(enemy.xp) * (1 + xp_bonus))))
			healing_echo := story_effect_clamped(run, .Healing_Echo, 0, 1)
			if healing_echo > 0 && run.player.hp < run.player.max_hp &&
				rng_chance(&run.loot_rng, min(f32(1), healing_echo)) {
				healed := min(
					run.player.max_hp - run.player.hp,
					max(2, int(f32(enemy.xp) * .12) + run.depth / 2),
				)
				run.player.hp += healed
				run.player.mana = min(f32(run.player.max_mana), run.player.mana + f32(max(1, healed / 2)))
				append(&run.numbers, Damage_Number{pos = run.player.pos, value = healed, kind = .Heal})
				append(&run.numbers, Damage_Number{pos = run.player.pos, kind = .Text, text = "Story echo"})
			}
			gold := rng_range(&run.loot_rng, GOLD_MIN, GOLD_MAX + 1) + run.depth * 2
			if enemy.role == .Elite {gold += 8;run.elites_killed += 1}
			if enemy.role == .Miniboss || enemy.role == .Boss do gold += 18
			run.player.gold += gold
			append(&run.numbers, Damage_Number{pos = enemy.pos, kind = .Gold, value = gold})
			// MX.5 reward contract (damage.py:255-450): the Tyrant guarantees a
			// named Unique; floor guardians and every Oathbound/challenge
			// miniboss guarantee Rare equipment; the ordinary 28% roll below
			// stays independent for every rank.
			if enemy.role == .Boss || enemy.role == .Miniboss {
				run.critical_save_requested = true
				reward: Item
				if enemy.final_boss {
					reward = make_unique(&run.loot_rng, run.player.archetype, run.depth)
				} else {
					slot: Item_Kind = rng_chance(&run.loot_rng, 0.5) ? .Weapon : .Armor
					reward = make_equipment(&run.loot_rng, slot, .Rare, RUN_MODIFIERS[run.modifier].curse_chance_bonus, run)
				}
				append(&run.ground_items, Ground_Item{item = reward, pos = drop_position_near(run, enemy.pos)})
				record_notable_loot(run, reward)
			}
			if rng_chance(&run.loot_rng, KILL_DROP_CHANCE) {
				drop := make_loot(&run.loot_rng, enemy.pos, RUN_MODIFIERS[run.modifier].curse_chance_bonus, run)
				record_notable_loot(run, drop.item)
				append(&run.ground_items, drop)
			}
			if enemy.role == .Miniboss && enemy.challenge_boss {
				// The challenge_room guardian's clear is tracked run-wide
				// (damage.py:321-334).
				run.challenge_rooms_cleared += 1
				append(&run.numbers, Damage_Number{pos = enemy.pos, kind = .Text, text = "Challenge conquered"})
			}
			if enemy.role == .Boss {
				run.defeated_bosses[enemy.boss_id] = true
				restore_sealed(&run.dungeon, run.sealed[:])
				refresh_visibility(run)
				clear(&run.sealed)
				run.boss_engaged = false
				if enemy.final_boss do run.tyrant_dead = true
				append(&run.numbers, Damage_Number{pos = enemy.pos, kind = .Text, text = "The seal breaks!"})
				append(&run.sfx,Sfx_Kind.Boss)
			}
			run.kills += 1
			unordered_remove(&run.enemies, i)
		}
	}
}

// --- Damage ----------------------------------------------------------------

damage_player :: proc(run: ^Run, raw: int) {
	_ = damage_player_typed(run, raw, .Physical)
}

damage_enemy :: proc(run: ^Run, enemy: ^Enemy, dmg: int) {
	_ = damage_enemy_typed(run, enemy, dmg, .Physical)
}

// --- Player attacks --------------------------------------------------------

player_slash_origin :: proc(run: ^Run, facing: Vec2, reach: f32 = PLAYER_MELEE_RANGE) -> Vec2 {
	if run == nil do return {}
	face := linalg.normalize0(facing)
	if face == {} do face = {1,0}
	best: ^Enemy
	best_distance := max(f32)
	for &enemy in run.enemies {
		if enemy.hp <= 0 do continue
		to := enemy.pos-run.player.pos
		distance := math.hypot(to.x,to.y)
		extra := max(0,enemy_hit_radius(&enemy)-ENEMY_HIT_RADIUS)
		if distance > reach+extra || distance >= best_distance do continue
		direction := distance < 1e-3 ? face : to/distance
		if linalg.dot(direction,face) < PLAYER_MELEE_ARC_DOT do continue
		if !line_of_sight(&run.dungeon,run.player.pos.x,run.player.pos.y,enemy.pos.x,enemy.pos.y) do continue
		best,best_distance=&enemy,distance
	}
	if best != nil do return (run.player.pos+best.pos)*.5
	return run.player.pos+face*.9
}

player_melee :: proc(run: ^Run, aim: Vec2) {
	player := &run.player
	if bighit_charging(player) do return
	cost := player_melee_stamina_cost(player)
	if player.melee_timer > 0 || player.stamina < f32(cost) do return
	player.stamina -= f32(cost)
	player.melee_timer = player_melee_cooldown(player)
	player.melee_commit_timer = MELEE_COMMIT_SECONDS // whiffs commit too
	start_swing(player, aim)
	feel_emit_slash(run,player_slash_origin(run,player.facing),player.facing)
	append(&run.sfx, Sfx_Kind.Swing)

	strike_arc(run, player.facing, PLAYER_MELEE_RANGE, player_melee_damage(player), knockback = KNOCKBACK_SPEED)
}

// Compatibility seam for pre-M8 callers: slot 2 is now the shared core bolt.
player_skill :: proc(run: ^Run, aim: Vec2) {
	_ = player_cast_bolt(run, aim)
}

@(private = "file")
start_swing :: proc(player: ^Player, aim: Vec2) {
	if aim != {} do player.facing = linalg.normalize0(aim)
	player.swing_timer = ATTACK_SWING_SECONDS
	player_start_visual_action(player, .Attack, PLAYER_ATTACK_ACTION_SECONDS)
}

// The held-input gate asks whether any living enemy is inside pygame's wide
// facing arc; the actual base swing below selects only the nearest one.
enemy_in_melee_arc :: proc(run: ^Run, facing: Vec2) -> bool {
	if facing == {} do return false
	face := linalg.normalize0(facing)
	for &enemy in run.enemies {
		if enemy.hp <= 0 do continue
		to := enemy.pos - run.player.pos
		dist := math.hypot(to.x, to.y)
		extra := max(0, enemy_hit_radius(&enemy) - ENEMY_HIT_RADIUS)
		if dist > PLAYER_MELEE_RANGE + extra do continue
		dir := dist < 1e-3 ? face : to / dist
		if linalg.dot(dir, face) < PLAYER_MELEE_ARC_DOT do continue
		if !line_of_sight(&run.dungeon, run.player.pos.x, run.player.pos.y, enemy.pos.x, enemy.pos.y) do continue
		return true
	}
	return false
}

// Bulwark cleave tiers (attacks.py:143-152): each degree widens Shield Bash's
// reach and how many nearby foes the single swing can catch.
@(private = "file")
warden_cleave_profile :: proc(player: ^Player) -> (reach_bonus: f32, max_targets: int) {
	if player.archetype != .Warden do return 0, 1
	switch {
	case player_has_discipline(player, .Warden_Bulwark_Ward): return 0.35, 4
	case player_has_discipline(player, .Warden_Aegis): return 0.28, 3
	case player_has_discipline(player, .Warden_Bulwark): return 0.22, 2
	}
	return 0, 1
}

@(private = "file")
strike_arc :: proc(run: ^Run, facing: Vec2, reach: f32, dmg: int, knockback: f32) {
	player := &run.player
	reach_bonus, max_targets := warden_cleave_profile(player)
	// Nearest-first capture of up to max_targets arc matches (attacks.py:143-164).
	targets: [4]^Enemy
	target_dirs: [4]Vec2
	target_count := 0
	for &enemy in run.enemies {
		if enemy.hp <= 0 do continue
		to := enemy.pos - player.pos
		dist := math.hypot(to.x, to.y)
		extra := max(0, enemy_hit_radius(&enemy) - ENEMY_HIT_RADIUS)
		if dist > reach + reach_bonus + extra do continue
		dir := dist < 1e-3 ? facing : to / dist
		if linalg.dot(dir, facing) < PLAYER_MELEE_ARC_DOT do continue
		if !line_of_sight(&run.dungeon, player.pos.x, player.pos.y, enemy.pos.x, enemy.pos.y) do continue
		insert := target_count
		for j in 0 ..< target_count {
			to_j := targets[j].pos - player.pos
			if dist < math.hypot(to_j.x, to_j.y) {
				insert = j
				break
			}
		}
		if insert >= max_targets do continue
		last := min(target_count, max_targets - 1)
		for j := last; j > insert; j -= 1 {
			targets[j], target_dirs[j] = targets[j - 1], target_dirs[j - 1]
		}
		targets[insert], target_dirs[insert] = &enemy, dir
		target_count = min(target_count + 1, max_targets)
	}
	if target_count == 0 do return
	hit_damage := dmg + rng_range(&run.combat_rng,-3,5)
	if player_has_skill_bonus(player,.Melee_Force) || player_has_skill_bonus(player,.Melee_Tempo) do hit_damage += 2
	critical, multiplier := roll_rogue_crit(run)
	smoke_crit := false
	if !critical {
		critical, multiplier = maybe_smoke_crit(run, critical, multiplier)
		smoke_crit = critical
	}
	if critical {
		hit_damage = int(f32(hit_damage) * multiplier)
		append(&run.numbers, Damage_Number{pos=targets[0].pos, kind=.Text, text=smoke_crit ? "Smoke Crit" : "Critical"})
	}
	damage_type := player_weapon_damage_type(player)
	// One status rider per swing (attacks.py:176-196): Aegis Discipline's holy
	// stun, then the Arcanist/Acolyte/Ranger typed-damage chain.
	status := Status_Kind.Poisoned
	has_status := false
	status_duration: f32
	if player.archetype == .Warden && player_has_discipline(player, .Warden_Aegis) {
		damage_type = .Holy
		status, has_status, status_duration = .Stunned, true, 0.35
	} else if player.archetype == .Arcanist && player_has_discipline(player, .Arcanist_Permafrost) {
		status, has_status, status_duration = .Chilled, true, 1.0
	} else if player.archetype == .Acolyte && player_has_discipline(player, .Acolyte_Gravebind) {
		status, has_status, status_duration = .Bound, true, 1.1
	} else if player.archetype == .Ranger && player_has_discipline(player, .Ranger_Beastmark) {
		status, has_status, status_duration = .Snared, true, 1.15
	}
	precision_rank := player_precision_rank(player)
	melee_leech := player.archetype == .Acolyte ? acolyte_melee_leech(player) : 0
	killed := false
	for i in 0 ..< target_count {
		target, target_dir := targets[i], target_dirs[i]
		damage := i == 0 ? hit_damage : max(1, int(f32(hit_damage) * BIGHIT_CLEAVE_FACTOR))
		damage = story_apply_player_damage(run, damage)
		_ = player_damage_enemy(run,target,damage,damage_type,status,has_status,status_duration)
		if target.hp <= 0 do killed = true
		if melee_leech > 0 && player.hp < player.max_hp {
			heal := min(player.max_hp - player.hp, melee_leech)
			player.hp += heal
			append(&run.numbers, Damage_Number{pos=player.pos, value=heal, kind=.Heal})
		}
		if critical && precision_rank > 0 do enemy_apply_status(target,.Poisoned,rogue_crit_poison_duration(precision_rank))
		if player.archetype == .Warden do target.cooldown=max(target.cooldown,.35)
		// MX.2.4: ordinary melee knockback rides the same decaying velocity path as
		// Big Hit (v0/decay ≈ 0.16 tiles) instead of an instant teleport slide.
		if knockback > 0 && target_dir != {} do enemy_start_knockback(run, target, target_dir * knockback)
	}
	// Impact freeze (2026-08 feel feedback): one pulse per connected swing, a
	// beat longer when it crits or kills. max() so cleave targets never stack.
	pulse := critical || killed ? HITSTOP_HEAVY_TICKS : HITSTOP_HIT_TICKS
	run.hitstop_ticks = max(run.hitstop_ticks, pulse)
}

// --- Interaction -----------------------------------------------------------

player_near_stairs :: proc(run: ^Run) -> bool {
	s := run.dungeon.stairs
	dx := run.player.pos.x - (f32(s.x) + 0.5)
	dy := run.player.pos.y - (f32(s.y) + 0.5)
	return math.hypot(dx, dy) <= INTERACT_STAIRS_RADIUS
}

door_is_sealed :: proc(run: ^Run, door: [2]int) -> bool {
	if !run.boss_engaged do return false
	for s in run.sealed {
		if int(s.x) == door.x && int(s.y) == door.y do return true
	}
	return false
}

player_near_shop :: proc(run: ^Run) -> bool {
	if run == nil || !run.has_shopkeeper do return false
	keeper_delta := run.shopkeeper.pos - run.player.pos
	if math.hypot(keeper_delta.x, keeper_delta.y) < 1.35 do return true
	sign_delta := shop_sign_position(&run.shopkeeper) - run.player.pos
	return math.hypot(sign_delta.x, sign_delta.y) < 1.35
}

// Exact story-aware E priority: relic; doors; shop; stairs/final epilogue;
// unresolved guest; Lossless Soul; Garden frog; then ordinary world actions.
player_interact :: proc(run: ^Run) -> (floor_changed: bool) {
	run.shop_requested = false
	if story_request_relic_collection(run) do return false
	if door, found := nearby_closed_door(&run.dungeon, run.player.pos.x, run.player.pos.y); found {
		if door_is_sealed(run, door) {
			append(&run.numbers, Damage_Number{pos = run.player.pos, kind = .Text, text = "Sealed by the boss"})
			return false
		}
		open_door(&run.dungeon, door.x, door.y)
		refresh_visibility(run)
		append(&run.sfx, Sfx_Kind.Door)
		return false
	}
	if player_near_shop(run) {
		run.shopkeeper.met = true
		room_npc_motion_hold(&run.shopkeeper.motion,run.shopkeeper.pos,run.player.pos)
		run.shop_requested = true
		append(&run.numbers, Damage_Number{pos=run.shopkeeper.pos,kind=.Text,text="Trade"})
		return false
	}
	if player_near_stairs(run) {
		if is_boss_depth(run.depth) && boss_alive(run) {
			append(&run.numbers, Damage_Number{pos = run.player.pos, kind = .Text, text = "Defeat the guardian before descending."})
			return false
		}
		if run.depth >= DUNGEON_DEPTH {
			if run.story_runtime.initialized {
				_ = story_handle_final_stairs_request(run)
				return false
			}
			run.victory = true
			append(&run.sfx, Sfx_Kind.Victory)
			return false
		}
		append(&run.sfx, Sfx_Kind.Stairs)
		run_descend(run)
		return true
	}
	if story_request_guest_dialogue(run) do return false
	if story_request_lossless_soul(run) do return false
	// A completed Moonbloom game is no longer an interaction target; E must
	// continue down the chain to secrets, loot, petting, and wall touches.
	if story_request_garden_moonbloom(run) do return false
	// Secrets outrank shrines, both outrank the bar (interactions.py:499-682).
	if secret := nearby_secret(run); secret != nil {
		open_secret(run, secret)
		return false
	}
	if shrine := nearby_shrine(run); shrine != nil {
		activate_shrine(run, shrine)
		return false
	}
	if barrel, found := run_barrel_tile(run); found && !run.refuge.bar_toasted && barrel_in_drink_range(run.player.pos, barrel) {
		if run_toast_bar(run) {
			append(&run.numbers, Damage_Number{pos=run.player.pos,kind=.Text,text="A grim toast"})
			append(&run.sfx, Sfx_Kind.Drink)
		}
		return false
	}
	if pick_up_nearby_item(run) do return false
	// Petting sits second-to-last in the chain, mirroring pygame's suppression
	// list (interactions.py:366-384); the never-advertised wall-face touch is
	// dead last so it can never shadow a real interaction.
	if pet_spirit_beast(run) do return false
	_ = touch_secret_face_wall(run)
	return false
}

// Contextual prompt for the HUD; empty when nothing is in range.
interact_prompt :: proc(run: ^Run) -> string {
	if story_relic_nearby(run) do return "E: recover relic echo"
	if door, found := nearby_closed_door(&run.dungeon, run.player.pos.x, run.player.pos.y); found {
		if door_is_sealed(run, door) do return "Sealed by the boss"
		return "E: open door"
	}
	if player_near_shop(run) do return "E: trade"
	if player_near_stairs(run) {
		if is_boss_depth(run.depth) && boss_alive(run) {
			return "Slay the guardian first"
		}
		if run.depth >= DUNGEON_DEPTH {
			if run.story_runtime.initialized {
				if run.tyrant_dead do return "E: open the final epilogue"
				return "The Gate waits for the Tyrant's end"
			}
			return "E: claim victory"
		}
		return "E: descend"
	}
	if guest := story_nearby_guest(run); guest != nil do return fmt.tprintf("E: answer %s", guest.name)
	if soul := story_nearby_lossless_soul(run); soul != nil do return "E: speak with the Lossless Soul"
	if _, _, frog_nearby := story_nearby_garden_frog(run); frog_nearby {
		ledger := &run.story_runtime.garden_games[clamp(run.depth, 1, STORY_BEAT_COUNT) - 1]
		if ledger.outcome == .None do return "E: wake the moonbloom"
	}
	if secret := nearby_secret(run); secret != nil {
		def := &SECRET_DEFS[secret.kind]
		return fmt.tprintf("E: %s - %s", def.name, def.detail)
	}
	if shrine := nearby_shrine(run); shrine != nil {
		def := &SHRINE_DEFS[shrine.kind]
		return fmt.tprintf("E: %s - %s", def.name, def.detail)
	}
	if barrel, found := run_barrel_tile(run); found && !run.refuge.bar_toasted && barrel_in_drink_range(run.player.pos, barrel) {
		// One free ale per bar; the pilgrimage counter mirrors pygame's
		// "this toast makes it n/m" hint. Temp-allocator string, per frame.
		return fmt.tprintf("E: raise a toast (%d/%d this run)", run.bars_toasted + 1, run.bars_visited)
	}
	nearest := -1
	nearest_distance := max(f32)
	for &g, i in run.ground_items {
		d := g.pos - run.player.pos
		distance := math.hypot(d.x, d.y)
		if distance < PICKUP_RADIUS && distance < nearest_distance {
			nearest = i
			nearest_distance = distance
		}
	}
	if nearest >= 0 {
		return "E: pick up item"
	}
	if nearby_pettable_spirit_beast(run) != nil {
		return "E: pet your beast"
	}
	// A revealed plate warns without ever being interactable
	// (interactions.py:256-264 "!" hint).
	if trap := nearby_trap_warning(run); trap != nil {
		def := &TRAP_DEFS[trap.kind]
		return fmt.tprintf("! %s - %s", def.name, def.detail)
	}
	return ""
}

// Advertised interactions are the actionable prompts shared by desktop and
// mobile. Blocked stairs/doors and trap warnings remain informational.
player_interaction_advertised :: proc(run: ^Run) -> bool {
	prompt := interact_prompt(run)
	return len(prompt) >= 2 && prompt[0] == 'E' && prompt[1] == ':'
}

// The secret wall-face touch intentionally has no prompt, but the mobile A
// button must still reach the same final interaction fallback as desktop E.
player_interaction_available :: proc(run: ^Run) -> bool {
	if player_interaction_advertised(run) do return true
	_, found := nearby_secret_face_wall(run)
	return found
}

// Next-floor preview under the stairs prompt (interactions.py:156-180): the
// authored plan tells the truth about the coming theme, risks, and reward.
// Empty away from usable stairs. Temp-allocator string; render each frame.
stairs_preview :: proc(run: ^Run) -> string {
	if run.depth >= DUNGEON_DEPTH || !player_near_stairs(run) do return ""
	if run_floor_plan(run).has_boss && boss_alive(run) do return ""
	next := &run.plan[run.depth] // depth is 1-based: this is the depth+1 entry
	return fmt.tprintf("Next: %s · %s", THEMES[next.theme_index].name, floor_plan_summary(next))
}
