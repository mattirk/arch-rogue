package archrogue

// Host -> joiner world snapshots. Every snapshot carries absolute state, never
// deltas: the fast section (actors, vitals, transient presentation) is always
// complete, and each slow section is sent whole whenever its content hash
// changes plus a periodic full refresh. Dropping or coalescing any snapshot
// therefore cannot lose a spawn, removal, pickup, or tile edit.

import "core:encoding/json"
import "core:hash"
import np "net_protocol"

COOP_MAX_ENEMIES     :: 256
COOP_MAX_PROJECTILES :: 256
COOP_MAX_FAMILIARS   :: 32
COOP_MAX_BELLS       :: 8
COOP_MAX_NUMBERS     :: 128
COOP_MAX_FEEL        :: 128
COOP_MAX_SFX         :: 128
COOP_MAX_GUESTS      :: 32
COOP_SLOW_REFRESH    :: 60 // snapshots between unconditional slow refreshes

Coop_Slow_Section :: enum u8 {
	Player0,
	Player1,
	Ground,
	Tiles,
	Interactables,
	Shop,
	Story,
	Scalars,
}

Coop_Joiner_Event :: enum u8 {
	None,
	Open_Shop, // the joiner's own interact reached the shopkeeper
}

// Run facts the joiner presents but never simulates.
Coop_Run_Scalars :: struct {
	depth:            int,
	difficulty:       Difficulty_Id,
	kills:            int,
	boss_engaged:     bool,
	tyrant_dead:      bool,
	victory:          bool,
	dark_floor:       bool,
	theme_index:      int,
	traps_triggered:  int,
	shrines_used:     int,
	secrets_opened:   int,
	bars_visited:     int,
	bars_toasted:     int,
	challenge_rooms_cleared: int,
	refuge:           Refuge_State,
	defeated_bosses:  [Boss_Id]bool,
	notable_loot:     [MAX_NOTABLE_LOOT]Notable_Loot,
	notable_count:    int,
	modifier:         Run_Modifier_Id,
	potions_used:     int,
	elites_killed:    int,
	sealed:           [dynamic]Sealed_Tile,
}

Coop_Interactables :: struct {
	traps:   [dynamic]Trap,
	shrines: [dynamic]Shrine,
	secrets: [dynamic]Secret,
}

Coop_Shop :: struct {
	has_shopkeeper: bool,
	shopkeeper:     Shopkeeper,
}

Coop_Story :: struct {
	guests:  [dynamic]Story_Guest,
	soul:    Lossless_Soul,
	relic:   Story_Relic_Echo,
}

// ------------------------------------------------------------------ encode --

@(private = "file")
w_vec :: proc(w: ^np.Json_Writer, v: Vec2) {
	np.jw_elem_f32(w, v.x)
	np.jw_elem_f32(w, v.y)
}

@(private = "file")
w_bool :: proc(w: ^np.Json_Writer, b: bool) {
	np.jw_elem_int(w, b ? 1 : 0)
}

@(private = "file")
w_f :: proc(w: ^np.Json_Writer, f: f32) {
	np.jw_elem_f32(w, f)
}

@(private = "file")
w_i :: proc(w: ^np.Json_Writer, i: int) {
	np.jw_elem_int(w, i64(i))
}

PLAYER_FAST_FIELDS :: 42 + len(Status_Kind)

@(private = "file")
encode_player_fast :: proc(w: ^np.Json_Writer, p: ^Player) {
	np.jw_begin_array(w)
	w_vec(w, p.pos)
	w_vec(w, p.facing)
	w_bool(w, p.moving)
	w_f(w, p.anim_time)
	w_i(w, int(p.visual_action))
	w_f(w, p.action_time)
	w_f(w, p.action_duration)
	w_i(w, p.hp)
	w_i(w, p.max_hp)
	w_f(w, p.mana)
	w_i(w, p.max_mana)
	w_f(w, p.stamina)
	w_i(w, p.max_stamina)
	w_f(w, p.hit_flash)
	w_f(w, p.hit_flash_duration)
	w_f(w, p.bighit_charge)
	w_f(w, p.swing_timer)
	w_f(w, p.melee_commit_timer)
	w_f(w, p.melee_timer)
	w_f(w, p.bolt_timer)
	w_f(w, p.dash_timer)
	w_f(w, p.class_skill_timer)
	w_f(w, p.bighit_timer)
	w_f(w, p.time_skip_timer)
	w_f(w, p.potion_timer)
	w_i(w, p.level)
	w_i(w, p.xp)
	w_i(w, p.next_xp)
	w_i(w, p.gold)
	w_i(w, p.heal_potions)
	w_i(w, p.mana_potions)
	w_i(w, p.raise_charges)
	w_i(w, p.memory_tokens)
	w_f(w, p.guidance_idle_elapsed)
	w_f(w, p.sim_elapsed)
	w_vec(w, p.heading_stable)
	w_f(w, p.heading_hold)
	w_f(w, p.poison_tick)
	w_f(w, p.shrine_move_bonus)
	for s in Status_Kind do w_f(w, p.statuses[s])
	np.jw_end_array(w)
}

ENEMY_FAST_FIELDS :: 34 + len(Status_Kind)

@(private = "file")
encode_enemy :: proc(w: ^np.Json_Writer, e: ^Enemy) {
	np.jw_begin_array(w)
	w_i(w, int(e.entity_id))
	w_i(w, int(e.kind))
	w_i(w, int(e.boss_id))
	w_i(w, int(e.role))
	w_i(w, e.elite_mod + 1)
	flags := 0
	if e.final_boss do flags |= 1
	if e.big do flags |= 2
	if e.challenge_boss do flags |= 4
	if e.moving do flags |= 8
	if e.ranged do flags |= 16
	w_i(w, flags)
	w_vec(w, e.pos)
	w_vec(w, e.facing)
	w_i(w, e.hp)
	w_i(w, e.max_hp)
	w_i(w, int(e.ai))
	w_f(w, e.windup)
	w_f(w, e.windup_duration)
	w_f(w, e.action_time)
	w_i(w, int(e.action_kind))
	w_f(w, e.action_timer)
	w_f(w, e.action_duration)
	w_i(w, e.pending_ability + 3)
	w_f(w, e.anim_time)
	w_f(w, e.hit_flash)
	w_f(w, e.hit_flash_duration)
	w_i(w, int(e.target_slot))
	w_vec(w, e.windup_aim)
	w_i(w, e.ability_count)
	w_i(w, int(e.abilities[0]))
	w_i(w, int(e.abilities[1]))
	w_f(w, e.attack_range)
	w_i(w, int(e.damage_type))
	w_vec(w, e.knockback_vel)
	w_i(w, int(e.color[0]) << 16 | int(e.color[1]) << 8 | int(e.color[2]))
	for s in Status_Kind do w_f(w, e.statuses[s])
	np.jw_end_array(w)
}

@(private = "file")
encode_npc :: proc(w: ^np.Json_Writer, pos: Vec2, m: ^Room_Npc_Motion) {
	np.jw_begin_array(w)
	w_vec(w, pos)
	w_vec(w, m.facing)
	w_vec(w, m.target)
	w_f(w, m.anim_time)
	w_i(w, int(m.state))
	flags := 0
	if m.moving do flags |= 1
	if m.holding do flags |= 2
	if m.dancing do flags |= 4
	w_i(w, flags)
	w_f(w, m.state_elapsed)
	w_f(w, m.state_duration)
	np.jw_end_array(w)
}

Coop_Snapshot_Input :: struct {
	seq:         u64,
	pause:       Coop_Pause,
	ack:         u32, // contiguous resolved joiner command step
	actions_ack: u32, // highest resolved joiner action id
	sfx:         []Sfx_Event,
	events:      []Coop_Joiner_Event,
	slow:        bit_set[Coop_Slow_Section],
}

coop_encode_snapshot :: proc(app: ^App, input: Coop_Snapshot_Input, allocator := context.allocator) -> []byte {
	run := &app.run
	// Stable identities let the guest match projectiles across snapshots (the
	// same ids the save document uses).
	run_ensure_persisted_entity_ids(run)
	w: np.Json_Writer
	np.jw_init(&w, allocator)
	np.jw_begin(&w)
	np.jw_str(&w, "t", "snapshot")
	np.jw_u64s(&w, "sq", input.seq)
	np.jw_u64s(&w, "tk", run.active_ticks)
	np.jw_u64s(&w, "hm", u64(max(app.net_now_ms, 0))) // host monotonic ms for joiner timelines
	np.jw_int(&w, "ep", i64(run.floor_epoch))
	np.jw_int(&w, "pz", i64(transmute(u8)input.pause))
	np.jw_int(&w, "ack", i64(input.ack))
	np.jw_int(&w, "aa", i64(input.actions_ack))
	np.jw_int(&w, "hs", i64(run.hitstop_ticks))
	np.jw_f32(&w, "at", run.arrival_timer)
	np.jw_f32(&w, "wf", run.wall_face_timer)
	np.jw_int(&w, "wx", i64(run.wall_face_tile.x))
	np.jw_int(&w, "wy", i64(run.wall_face_tile.y))

	np.jw_begin_array_key(&w, "p")
	for slot in 0 ..< MAX_PLAYERS do encode_player_fast(&w, &run.players[slot])
	np.jw_end_array(&w)

	np.jw_begin_array_key(&w, "e")
	for &e in run.enemies {
		if e.hp <= 0 do continue
		encode_enemy(&w, &e)
	}
	np.jw_end_array(&w)

	np.jw_begin_array_key(&w, "pr")
	for &p in run.projectiles {
		np.jw_begin_array(&w)
		np.jw_elem_int(&w, i64(p.entity_id & 0x1F_FFFF_FFFF_FFFF))
		w_vec(&w, p.pos)
		w_vec(&w, p.vel)
		w_i(&w, int(p.visual))
		w_f(&w, p.visual_age)
		w_i(&w, int(p.damage_type))
		w_bool(&w, p.from_player)
		w_i(&w, int(p.owner_slot))
		w_f(&w, p.ttl)
		w_i(&w, int(p.color[0]) << 16 | int(p.color[1]) << 8 | int(p.color[2]))
		np.jw_end_array(&w)
	}
	np.jw_end_array(&w)

	np.jw_begin_array_key(&w, "fa")
	for &f in run.familiars {
		np.jw_begin_array(&w)
		w_i(&w, int(f.entity_id))
		w_i(&w, int(f.kind))
		w_i(&w, int(f.owner_slot))
		w_vec(&w, f.pos)
		w_vec(&w, f.facing)
		w_i(&w, f.hp)
		w_i(&w, f.max_hp)
		w_f(&w, f.attack_anim_timer)
		w_f(&w, f.pet_anim_timer)
		w_f(&w, f.anim_time)
		flags := 0
		if f.moving do flags |= 1
		if f.champion do flags |= 2
		if f.unkillable do flags |= 4
		w_i(&w, flags)
		w_i(&w, int(f.command))
		np.jw_end_array(&w)
	}
	np.jw_end_array(&w)

	np.jw_begin_array_key(&w, "bl")
	for &b in run.bells {
		np.jw_begin_array(&w)
		w_vec(&w, b.pos)
		w_f(&w, b.arm_timer)
		w_f(&w, b.lifetime)
		w_i(&w, int(b.owner_slot))
		w_f(&w, b.lure_radius)
		w_f(&w, b.trigger_radius)
		w_f(&w, b.damage_radius)
		np.jw_end_array(&w)
	}
	np.jw_end_array(&w)

	np.jw_begin_array_key(&w, "nu")
	for &n in run.numbers {
		np.jw_begin_array(&w)
		w_vec(&w, n.pos)
		w_i(&w, n.value)
		w_f(&w, n.age)
		w_i(&w, int(n.kind))
		w_i(&w, int(n.damage_type))
		np.jw_elem_str(&w, n.text)
		np.jw_end_array(&w)
	}
	np.jw_end_array(&w)

	np.jw_begin_array_key(&w, "fe")
	for &f in run.feel {
		np.jw_begin_array(&w)
		w_i(&w, int(f.kind))
		w_i(&w, int(f.phase))
		w_i(&w, int(f.style))
		w_i(&w, int(f.visibility))
		w_i(&w, int(f.priority))
		w_vec(&w, f.pos)
		w_vec(&w, f.direction)
		w_i(&w, int(f.color[0]) << 24 | int(f.color[1]) << 16 | int(f.color[2]) << 8 | int(f.color[3]))
		w_f(&w, f.remaining)
		w_f(&w, f.duration)
		w_f(&w, f.radius)
		flags := 0
		if f.heavy do flags |= 1
		if f.engulf_room do flags |= 2
		w_i(&w, flags)
		np.jw_end_array(&w)
	}
	np.jw_end_array(&w)

	np.jw_begin_array_key(&w, "sx")
	for &e in input.sfx {
		np.jw_begin_array(&w)
		w_i(&w, int(e.kind))
		w_i(&w, int(e.bank))
		w_vec(&w, e.pos)
		w_bool(&w, e.spatial)
		np.jw_elem_int(&w, i64(e.emitter_id & 0x1F_FFFF_FFFF_FFFF))
		np.jw_end_array(&w)
	}
	np.jw_end_array(&w)

	np.jw_begin_array_key(&w, "ev")
	for e in input.events do w_i(&w, int(e))
	np.jw_end_array(&w)

	np.jw_begin_array_key(&w, "np")
	encode_npc(&w, run.shopkeeper.pos, &run.shopkeeper.motion)
	for i in 0 ..< run.ambient_residents.count {
		r := &run.ambient_residents.items[i]
		encode_npc(&w, r.pos, &r.motion)
	}
	np.jw_end_array(&w)
	np.jw_begin_array_key(&w, "gu")
	for &g in run.story_runtime.guests {
		np.jw_begin_array(&w)
		w_vec(&w, g.pos)
		w_vec(&w, g.motion.facing)
		w_f(&w, g.motion.anim_time)
		w_i(&w, int(g.motion.state))
		w_bool(&w, g.motion.moving)
		w_i(&w, g.hp)
		np.jw_end_array(&w)
	}
	np.jw_end_array(&w)
	soul := &run.story_runtime.soul
	np.jw_begin_array_key(&w, "so")
	w_vec(&w, soul.pos)
	w_vec(&w, soul.motion.facing)
	w_f(&w, soul.motion.anim_time)
	w_i(&w, int(soul.motion.state))
	w_bool(&w, soul.motion.moving)
	w_i(&w, soul.hp)
	np.jw_end_array(&w)

	if input.slow != {} {
		np.jw_begin_obj_key(&w, "sl")
		for section in input.slow {
			bytes := coop_slow_section_json(run, section, context.temp_allocator)
			if bytes != nil do np.jw_raw(&w, COOP_SLOW_KEYS[section], bytes)
		}
		np.jw_end(&w)
	}
	np.jw_end(&w)
	return np.jw_bytes(&w)
}

COOP_SLOW_KEYS := [Coop_Slow_Section]string{
	.Player0       = "p0",
	.Player1       = "p1",
	.Ground        = "gi",
	.Tiles         = "tl",
	.Interactables = "it",
	.Shop          = "sk",
	.Story         = "st",
	.Scalars       = "rn",
}

@(private = "file")
marshal_compact :: proc(value: $T, allocator := context.allocator) -> []byte {
	data, err := json.marshal(value, coop_checkpoint_json_options(), allocator)
	if err != nil do return nil
	return data
}

coop_slow_section_json :: proc(run: ^Run, section: Coop_Slow_Section, allocator := context.allocator) -> []byte {
	switch section {
	case .Player0: return marshal_compact(run.players[0], allocator)
	case .Player1: return marshal_compact(run.players[1], allocator)
	case .Ground:  return marshal_compact(run.ground_items, allocator)
	case .Tiles:
		// One digit per tile, column-major like the array, as a JSON string.
		buf := make([]byte, MAP_W * MAP_H + 2, allocator)
		buf[0] = '"'
		i := 1
		for x in 0 ..< MAP_W {
			for y in 0 ..< MAP_H {
				buf[i] = byte('0' + int(run.dungeon.tiles[x][y]))
				i += 1
			}
		}
		buf[i] = '"'
		return buf
	case .Interactables:
		return marshal_compact(Coop_Interactables{run.traps, run.shrines, run.secrets}, allocator)
	case .Shop:
		return marshal_compact(Coop_Shop{run.has_shopkeeper, run.shopkeeper}, allocator)
	case .Story:
		return marshal_compact(Coop_Story{run.story_runtime.guests, run.story_runtime.soul, run.story_runtime.relic}, allocator)
	case .Scalars:
		return marshal_compact(coop_run_scalars(run), allocator)
	}
	return nil
}

coop_run_scalars :: proc(run: ^Run) -> Coop_Run_Scalars {
	return {
		depth = run.depth, difficulty = run.difficulty, kills = run.kills,
		boss_engaged = run.boss_engaged, tyrant_dead = run.tyrant_dead, victory = run.victory,
		dark_floor = run.dark_floor, theme_index = run.theme_index,
		traps_triggered = run.traps_triggered, shrines_used = run.shrines_used,
		secrets_opened = run.secrets_opened, bars_visited = run.bars_visited,
		bars_toasted = run.bars_toasted, challenge_rooms_cleared = run.challenge_rooms_cleared,
		refuge = run.refuge, defeated_bosses = run.defeated_bosses,
		notable_loot = run.notable_loot, notable_count = run.notable_count,
		modifier = run.modifier, potions_used = run.potions_used, elites_killed = run.elites_killed,
		sealed = run.sealed,
	}
}

coop_slow_section_hash :: proc(run: ^Run, section: Coop_Slow_Section) -> u64 {
	bytes := coop_slow_section_json(run, section, context.temp_allocator)
	return hash.fnv64a(bytes)
}

// ------------------------------------------------------------------ decode --

Coop_Snapshot_Header :: struct {
	seq:         u64,
	tick:        u64,
	epoch:       u32,
	pause:       Coop_Pause,
	ack:         u32,
	actions_ack: u32,
	host_ms:     u64,
}

coop_decode_snapshot_header :: proc(obj: json.Object) -> (h: Coop_Snapshot_Header, ok: bool) {
	h.seq = np.read_u64s(obj, "sq") or_return
	h.tick = np.read_u64s(obj, "tk") or_return
	h.epoch = u32(np.read_int(obj, "ep", 0, i64(max(u32))) or_return)
	pz := np.read_int(obj, "pz", 0, 255) or_return
	h.pause = transmute(Coop_Pause)u8(pz)
	h.ack = u32(np.read_int(obj, "ack", 0, i64(max(u32))) or_return)
	h.actions_ack = u32(np.read_int(obj, "aa", 0, i64(max(u32))) or_return)
	h.host_ms = np.read_u64s(obj, "hm") or_return
	return h, true
}

@(private = "file")
ai :: proc(arr: json.Array, i: ^int, lo, hi: i64, ok: ^bool) -> int {
	defer i^ += 1
	if !ok^ || i^ >= len(arr) {
		ok^ = false
		return 0
	}
	n, is_int := arr[i^].(json.Integer)
	if !is_int || n < lo || n > hi {
		ok^ = false
		return 0
	}
	return int(n)
}

@(private = "file")
af :: proc(arr: json.Array, i: ^int, lo, hi: f32, ok: ^bool) -> f32 {
	defer i^ += 1
	if !ok^ || i^ >= len(arr) {
		ok^ = false
		return 0
	}
	f: f64
	#partial switch v in arr[i^] {
	case json.Integer: f = f64(v)
	case json.Float: f = f64(v)
	case:
		ok^ = false
		return 0
	}
	if f != f || f < f64(lo) || f > f64(hi) {
		ok^ = false
		return 0
	}
	return f32(f)
}

@(private = "file")
av :: proc(arr: json.Array, i: ^int, ok: ^bool) -> Vec2 {
	x := af(arr, i, -1000, 1000, ok)
	y := af(arr, i, -1000, 1000, ok)
	return {x, y}
}

@(private = "file")
ab :: proc(arr: json.Array, i: ^int, ok: ^bool) -> bool {
	return ai(arr, i, 0, 1, ok) == 1
}

T_MAX :: f32(1_000_000) // generous bound for timers/clocks

coop_decode_player_fast :: proc(v: json.Value, p: ^Player) -> bool {
	arr, is_arr := v.(json.Array)
	if !is_arr || len(arr) != PLAYER_FAST_FIELDS do return false
	ok := true
	i := 0
	q: Player = p^
	q.pos = av(arr, &i, &ok)
	q.facing = av(arr, &i, &ok)
	q.moving = ab(arr, &i, &ok)
	q.anim_time = af(arr, &i, 0, T_MAX, &ok)
	q.visual_action = Visual_Action(ai(arr, &i, 0, i64(len(Visual_Action) - 1), &ok))
	q.action_time = af(arr, &i, 0, T_MAX, &ok)
	q.action_duration = af(arr, &i, 0, T_MAX, &ok)
	q.hp = ai(arr, &i, -1_000_000, 1_000_000, &ok)
	q.max_hp = ai(arr, &i, 1, 1_000_000, &ok)
	q.mana = af(arr, &i, -T_MAX, T_MAX, &ok)
	q.max_mana = ai(arr, &i, 0, 1_000_000, &ok)
	q.stamina = af(arr, &i, -T_MAX, T_MAX, &ok)
	q.max_stamina = ai(arr, &i, 0, 1_000_000, &ok)
	q.hit_flash = af(arr, &i, 0, 10, &ok)
	q.hit_flash_duration = af(arr, &i, 0, 10, &ok)
	q.bighit_charge = af(arr, &i, -10, 100, &ok)
	q.swing_timer = af(arr, &i, -10, 100, &ok)
	q.melee_commit_timer = af(arr, &i, -10, 100, &ok)
	q.melee_timer = af(arr, &i, -10, 1000, &ok)
	q.bolt_timer = af(arr, &i, -10, 1000, &ok)
	q.dash_timer = af(arr, &i, -10, 1000, &ok)
	q.class_skill_timer = af(arr, &i, -10, 1000, &ok)
	q.bighit_timer = af(arr, &i, -10, 1000, &ok)
	q.time_skip_timer = af(arr, &i, -10, 1000, &ok)
	q.potion_timer = af(arr, &i, -10, 1000, &ok)
	q.level = ai(arr, &i, 0, 10_000, &ok)
	q.xp = ai(arr, &i, -1_000_000_000, 1_000_000_000, &ok)
	q.next_xp = ai(arr, &i, 0, 1_000_000_000, &ok)
	q.gold = ai(arr, &i, -1_000_000_000, 1_000_000_000, &ok)
	q.heal_potions = ai(arr, &i, 0, 1000, &ok)
	q.mana_potions = ai(arr, &i, 0, 1000, &ok)
	q.raise_charges = ai(arr, &i, 0, 1000, &ok)
	q.memory_tokens = ai(arr, &i, 0, 10_000, &ok)
	q.guidance_idle_elapsed = af(arr, &i, 0, T_MAX, &ok)
	q.sim_elapsed = af(arr, &i, 0, T_MAX * 100, &ok)
	q.heading_stable = av(arr, &i, &ok)
	q.heading_hold = af(arr, &i, 0, T_MAX, &ok)
	q.poison_tick = af(arr, &i, -10, 100, &ok)
	q.shrine_move_bonus = af(arr, &i, -10, 10, &ok)
	for s in Status_Kind do q.statuses[s] = af(arr, &i, 0, 10_000, &ok)
	if !ok do return false
	p^ = q
	return true
}

// Decodes one compact enemy into `e`, preserving any fields the tuple does
// not carry (names and static stats from the checkpoint).
coop_decode_enemy :: proc(arr: json.Array, e: ^Enemy) -> bool {
	if len(arr) != ENEMY_FAST_FIELDS do return false
	ok := true
	i := 0
	q := e^
	q.entity_id = u32(ai(arr, &i, 1, i64(max(u32)), &ok))
	q.kind = Enemy_Kind(ai(arr, &i, 0, i64(len(Enemy_Kind) - 1), &ok))
	q.boss_id = Boss_Id(ai(arr, &i, 0, i64(len(Boss_Id) - 1), &ok))
	q.role = Enemy_Role(ai(arr, &i, 0, i64(len(Enemy_Role) - 1), &ok))
	q.elite_mod = ai(arr, &i, 0, i64(len(ELITE_MODIFIERS)), &ok) - 1
	flags := ai(arr, &i, 0, 31, &ok)
	q.final_boss, q.big, q.challenge_boss = flags & 1 != 0, flags & 2 != 0, flags & 4 != 0
	q.moving, q.ranged = flags & 8 != 0, flags & 16 != 0
	q.pos = av(arr, &i, &ok)
	q.facing = av(arr, &i, &ok)
	q.hp = ai(arr, &i, -1_000_000, 10_000_000, &ok)
	q.max_hp = ai(arr, &i, 1, 10_000_000, &ok)
	q.ai = AI_State(ai(arr, &i, 0, i64(len(AI_State) - 1), &ok))
	q.windup = af(arr, &i, -10, 100, &ok)
	q.windup_duration = af(arr, &i, -10, 100, &ok)
	q.action_time = af(arr, &i, -10, T_MAX, &ok)
	q.action_kind = Enemy_Action_Kind(ai(arr, &i, 0, i64(len(Enemy_Action_Kind) - 1), &ok))
	q.action_timer = af(arr, &i, -10, 100, &ok)
	q.action_duration = af(arr, &i, -10, 100, &ok)
	q.pending_ability = ai(arr, &i, 0, 5, &ok) - 3
	q.anim_time = af(arr, &i, 0, T_MAX, &ok)
	q.hit_flash = af(arr, &i, 0, 10, &ok)
	q.hit_flash_duration = af(arr, &i, 0, 10, &ok)
	q.target_slot = u8(ai(arr, &i, 0, MAX_PLAYERS - 1, &ok))
	q.windup_aim = av(arr, &i, &ok)
	q.ability_count = ai(arr, &i, 0, 2, &ok)
	q.abilities[0] = Ability_Id(ai(arr, &i, 0, i64(len(Ability_Id) - 1), &ok))
	q.abilities[1] = Ability_Id(ai(arr, &i, 0, i64(len(Ability_Id) - 1), &ok))
	q.attack_range = af(arr, &i, 0, 100, &ok)
	q.damage_type = Damage_Type(ai(arr, &i, 0, i64(len(Damage_Type) - 1), &ok))
	q.knockback_vel = av(arr, &i, &ok)
	rgb := ai(arr, &i, 0, 0xFFFFFF, &ok)
	q.color = {u8(rgb >> 16), u8(rgb >> 8), u8(rgb), 255}
	for s in Status_Kind do q.statuses[s] = af(arr, &i, 0, 10_000, &ok)
	if !ok do return false
	e^ = q
	return true
}

coop_decode_npc :: proc(v: json.Value, pos: ^Vec2, m: ^Room_Npc_Motion) -> bool {
	arr, is_arr := v.(json.Array)
	if !is_arr || len(arr) != 11 do return false
	ok := true
	i := 0
	p := av(arr, &i, &ok)
	facing := av(arr, &i, &ok)
	target := av(arr, &i, &ok)
	anim := af(arr, &i, 0, T_MAX, &ok)
	state := ai(arr, &i, 0, i64(len(Room_Npc_Motion_State) - 1), &ok)
	flags := ai(arr, &i, 0, 7, &ok)
	elapsed := af(arr, &i, 0, T_MAX, &ok)
	duration := af(arr, &i, 0, T_MAX, &ok)
	if !ok do return false
	pos^ = p
	m.facing, m.target, m.anim_time = facing, target, anim
	m.state = Room_Npc_Motion_State(state)
	m.moving, m.holding, m.dancing = flags & 1 != 0, flags & 2 != 0, flags & 4 != 0
	m.state_elapsed, m.state_duration = elapsed, duration
	return true
}

// Projectiles, familiars, bells, numbers, feel and sfx decode into fresh
// lists the caller swaps in only after the whole snapshot validated.
coop_decode_projectile :: proc(v: json.Value) -> (p: Projectile, ok: bool) {
	arr, is_arr := v.(json.Array)
	if !is_arr || len(arr) != 12 do return {}, false
	ok = true
	i := 0
	p.entity_id = u64(ai(arr, &i, 0, 0x1F_FFFF_FFFF_FFFF, &ok))
	p.pos = av(arr, &i, &ok)
	p.vel = av(arr, &i, &ok)
	p.visual = Projectile_Visual(ai(arr, &i, 0, i64(len(Projectile_Visual) - 1), &ok))
	p.visual_age = af(arr, &i, 0, T_MAX, &ok)
	p.damage_type = Damage_Type(ai(arr, &i, 0, i64(len(Damage_Type) - 1), &ok))
	p.from_player = ab(arr, &i, &ok)
	p.owner_slot = u8(ai(arr, &i, 0, MAX_PLAYERS - 1, &ok))
	p.ttl = af(arr, &i, -10, 1000, &ok)
	rgb := ai(arr, &i, 0, 0xFFFFFF, &ok)
	p.color = {u8(rgb >> 16), u8(rgb >> 8), u8(rgb), 255}
	p.prev_pos = p.pos
	return
}

coop_decode_familiar :: proc(v: json.Value, f: ^Familiar) -> bool {
	arr, is_arr := v.(json.Array)
	if !is_arr || len(arr) != 14 do return false
	ok := true
	i := 0
	q := f^
	q.entity_id = u32(ai(arr, &i, 0, i64(max(u32)), &ok))
	q.kind = Familiar_Kind(ai(arr, &i, 0, i64(len(Familiar_Kind) - 1), &ok))
	q.owner_slot = u8(ai(arr, &i, 0, MAX_PLAYERS - 1, &ok))
	q.pos = av(arr, &i, &ok)
	q.facing = av(arr, &i, &ok)
	q.hp = ai(arr, &i, -1_000_000, 1_000_000, &ok)
	q.max_hp = ai(arr, &i, 0, 1_000_000, &ok)
	q.attack_anim_timer = af(arr, &i, -10, 100, &ok)
	q.pet_anim_timer = af(arr, &i, -10, 100, &ok)
	q.anim_time = af(arr, &i, 0, T_MAX, &ok)
	flags := ai(arr, &i, 0, 7, &ok)
	q.moving, q.champion, q.unkillable = flags & 1 != 0, flags & 2 != 0, flags & 4 != 0
	q.command = Familiar_Command(ai(arr, &i, 0, i64(len(Familiar_Command) - 1), &ok))
	if !ok do return false
	f^ = q
	return true
}

coop_decode_bell :: proc(v: json.Value) -> (b: Ambush_Bell, ok: bool) {
	arr, is_arr := v.(json.Array)
	if !is_arr || len(arr) != 8 do return {}, false
	ok = true
	i := 0
	b.pos = av(arr, &i, &ok)
	b.arm_timer = af(arr, &i, -10, 1000, &ok)
	b.lifetime = af(arr, &i, -10, 10_000, &ok)
	b.owner_slot = u8(ai(arr, &i, 0, MAX_PLAYERS - 1, &ok))
	b.lure_radius = af(arr, &i, 0, 100, &ok)
	b.trigger_radius = af(arr, &i, 0, 100, &ok)
	b.damage_radius = af(arr, &i, 0, 100, &ok)
	b.armed_announced = true // the host owns the arm cue
	return
}

coop_decode_number :: proc(v: json.Value, intern: proc(s: string) -> string) -> (n: Damage_Number, ok: bool) {
	arr, is_arr := v.(json.Array)
	if !is_arr || len(arr) != 7 do return {}, false
	ok = true
	i := 0
	n.pos = av(arr, &i, &ok)
	n.value = ai(arr, &i, -10_000_000, 10_000_000, &ok)
	n.age = af(arr, &i, 0, 100, &ok)
	n.kind = Number_Kind(ai(arr, &i, 0, i64(len(Number_Kind) - 1), &ok))
	n.damage_type = Damage_Type(ai(arr, &i, 0, i64(len(Damage_Type) - 1), &ok))
	if ok {
		text, is_str := arr[6].(json.String)
		if !is_str || len(text) > 200 do return {}, false
		n.text = intern(string(text))
	}
	return
}

coop_decode_feel :: proc(v: json.Value) -> (f: Feel_Event, ok: bool) {
	arr, is_arr := v.(json.Array)
	if !is_arr || len(arr) != 14 do return {}, false
	ok = true
	i := 0
	f.kind = Feel_Kind(ai(arr, &i, 0, i64(len(Feel_Kind) - 1), &ok))
	f.phase = Feel_Phase(ai(arr, &i, 0, i64(len(Feel_Phase) - 1), &ok))
	f.style = Feel_Style(ai(arr, &i, 0, i64(len(Feel_Style) - 1), &ok))
	f.visibility = Feel_Visibility(ai(arr, &i, 0, i64(len(Feel_Visibility) - 1), &ok))
	f.priority = Feel_Priority(ai(arr, &i, 0, i64(len(Feel_Priority) - 1), &ok))
	f.pos = av(arr, &i, &ok)
	f.direction = av(arr, &i, &ok)
	rgba := ai(arr, &i, 0, 0xFFFFFFFF, &ok)
	f.color = {u8(rgba >> 24), u8(rgba >> 16), u8(rgba >> 8), u8(rgba)}
	f.remaining = af(arr, &i, -10, 1000, &ok)
	f.duration = af(arr, &i, 0, 1000, &ok)
	f.radius = af(arr, &i, 0, 1000, &ok)
	flags := ai(arr, &i, 0, 3, &ok)
	f.heavy, f.engulf_room = flags & 1 != 0, flags & 2 != 0
	return
}

coop_decode_sfx :: proc(v: json.Value) -> (e: Sfx_Event, ok: bool) {
	arr, is_arr := v.(json.Array)
	if !is_arr || len(arr) != 6 do return {}, false
	ok = true
	i := 0
	e.kind = Sfx_Event_Kind(ai(arr, &i, 0, i64(len(Sfx_Event_Kind) - 1), &ok))
	e.bank = Sfx_Bank(ai(arr, &i, 0, i64(len(Sfx_Bank) - 1), &ok))
	e.pos = av(arr, &i, &ok)
	e.spatial = ab(arr, &i, &ok)
	e.emitter_id = u64(ai(arr, &i, 0, 0x1F_FFFF_FFFF_FFFF, &ok))
	return
}
