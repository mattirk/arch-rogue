package archrogue

// Gameplay wire codec for co-op (protocol v4): joiner intents, host snapshots,
// and chunked world checkpoints. Encoders write compact positional arrays
// with net_protocol's writer; decoders run strict JSON validation first and
// then range-check every field before anything touches a Run. Both clients
// are the same release (D3), so these layouts change with the game.

import "core:encoding/base64"
import "core:encoding/json"
import "core:fmt"
import "core:math"
import "core:strings"
import np "net_protocol"

// ------------------------------------------------------------------ intent --

COOP_MAX_BATCH_COMMANDS :: 16
COOP_MAX_BATCH_ACTIONS  :: 16

Coop_Command :: struct {
	seq:        u32,
	move:       Vec2, // unit-clamped stick/keys/mouse direction
	max_step:   f32,  // < 0: ordinary full step
	auto_melee: bool,
	aim:        Vec2,
	aim_live:   bool,
	// Local-only (never encoded): action edges ordered with this step, so
	// live prediction and replay apply the same plant/dash at the same step.
	melee:      bool,
	melee_aim:  Vec2,
	dash:       bool,
	dash_aim:   Vec2,
}

coop_predict_step :: proc(cmd: Coop_Command) -> Predict_Step {
	return {
		move = cmd.move, max_move_step = cmd.max_step, auto_melee = cmd.auto_melee,
		melee = cmd.melee, melee_aim = cmd.melee_aim, dash = cmd.dash, dash_aim = cmd.dash_aim,
	}
}

Coop_Action_Kind :: enum u8 {
	None,
	Melee,
	Big_Hit_Begin,
	Big_Hit_Release,
	Bolt,
	Class_Skill,
	Dash,
	Potion_Heal,
	Potion_Mana,
	Interact,
	Equip,
	Drop,
	Sort,
	Discipline,
	Shop_Buy,
	Shop_Sell,
}

// One-shot action edge. `at` is the command step it is ordered with: the host
// applies it immediately before resolving that step. Inventory/shop edges
// carry the bag/stock index plus an item fingerprint so a stale or re-sorted
// view can never act on a different item.
Coop_Action :: struct {
	id:    u32,
	at:    u32,
	kind:  Coop_Action_Kind,
	aim:   Vec2,
	index: i32,
	arg:   i32,
	check: u32,
}

Coop_Pause_Reason :: enum u8 {
	Host_Menu,   // host inventory/character/shop/options
	Host_Story,  // host-owned story modal or minigame
	Joiner_Shop, // joiner trading pauses the shared dungeon
	Partner_Lost, // reconnect hold
}

Coop_Pause :: bit_set[Coop_Pause_Reason; u8]

@(private = "file")
quant_unit :: proc(v: f32) -> i64 {
	if math.is_nan(v) do return 0
	return i64(math.round(clamp(v, -1, 1) * 127))
}

@(private = "file")
dequant_unit :: proc(n: i64) -> f32 {
	return clamp(f32(n) / 127, -1, 1)
}

@(private = "file")
quant_vec :: proc(v: Vec2) -> (x, y: i64) {
	l := math.hypot(v.x, v.y)
	u := v
	if l > 1 do u = v / l
	return quant_unit(u.x), quant_unit(u.y)
}

coop_encode_intent :: proc(commands: []Coop_Command, actions: []Coop_Action, pause: Coop_Pause, allocator := context.allocator) -> []byte {
	w: np.Json_Writer
	np.jw_init(&w, allocator)
	np.jw_begin(&w)
	np.jw_str(&w, "t", "intent")
	np.jw_int(&w, "pz", i64(transmute(u8)pause))
	np.jw_begin_array_key(&w, "c")
	for c in commands {
		np.jw_begin_array(&w)
		np.jw_elem_int(&w, i64(c.seq))
		mx, my := quant_vec(c.move)
		ax, ay := quant_vec(c.aim)
		np.jw_elem_int(&w, mx)
		np.jw_elem_int(&w, my)
		np.jw_elem_int(&w, c.max_step < 0 ? -1 : i64(math.round(min(c.max_step, 2) * 1000)))
		flags: i64 = 0
		if c.auto_melee do flags |= 1
		if c.aim_live do flags |= 2
		np.jw_elem_int(&w, flags)
		np.jw_elem_int(&w, ax)
		np.jw_elem_int(&w, ay)
		np.jw_end_array(&w)
	}
	np.jw_end_array(&w)
	np.jw_begin_array_key(&w, "a")
	for a in actions {
		np.jw_begin_array(&w)
		ax, ay := quant_vec(a.aim)
		np.jw_elem_int(&w, i64(a.id))
		np.jw_elem_int(&w, i64(a.at))
		np.jw_elem_int(&w, i64(a.kind))
		np.jw_elem_int(&w, ax)
		np.jw_elem_int(&w, ay)
		np.jw_elem_int(&w, i64(a.index))
		np.jw_elem_int(&w, i64(a.arg))
		np.jw_elem_int(&w, i64(a.check))
		np.jw_end_array(&w)
	}
	np.jw_end_array(&w)
	np.jw_end(&w)
	return np.jw_bytes(&w)
}

@(private = "file")
arr_int :: proc(arr: json.Array, i: int, lo, hi: i64) -> (i64, bool) {
	if i >= len(arr) do return 0, false
	n, ok := arr[i].(json.Integer)
	if !ok || n < lo || n > hi do return 0, false
	return i64(n), true
}

@(private = "file")
arr_f32 :: proc(arr: json.Array, i: int, lo, hi: f32) -> (f32, bool) {
	if i >= len(arr) do return 0, false
	f: f64
	#partial switch v in arr[i] {
	case json.Integer: f = f64(v)
	case json.Float: f = f64(v)
	case: return 0, false
	}
	if math.is_nan(f) || f < f64(lo) || f > f64(hi) do return 0, false
	return f32(f), true
}

@(private = "file")
arr_bool :: proc(arr: json.Array, i: int) -> (bool, bool) {
	n, ok := arr_int(arr, i, 0, 1)
	return n == 1, ok
}

@(private = "file")
sub_array :: proc(v: json.Value, max_len: int) -> (json.Array, bool) {
	arr, ok := v.(json.Array)
	if !ok || len(arr) > max_len do return nil, false
	return arr, true
}

// Decodes an intent batch into caller-provided buffers. Malformed batches are
// rejected whole; nothing is partially applied.
coop_decode_intent :: proc(data: []byte, commands: ^[dynamic]Coop_Command, actions: ^[dynamic]Coop_Action) -> (pause: Coop_Pause, ok: bool) {
	if np.json_validate(data) != .None do return {}, false
	obj, root, parsed := np.json_parse_object(data, context.temp_allocator)
	if !parsed do return {}, false
	defer json.destroy_value(root, context.temp_allocator)
	pz := np.read_int(obj, "pz", 0, 255) or_return
	pause = transmute(Coop_Pause)u8(pz)
	cs := np.read_array(obj, "c", COOP_MAX_BATCH_COMMANDS) or_return
	as := np.read_array(obj, "a", COOP_MAX_BATCH_ACTIONS) or_return
	base_c, base_a := len(commands), len(actions)
	for v in cs {
		arr := sub_array(v, 7) or_return
		c: Coop_Command
		c.seq = u32(arr_int(arr, 0, 1, i64(max(u32))) or_return)
		mx := arr_int(arr, 1, -127, 127) or_return
		my := arr_int(arr, 2, -127, 127) or_return
		step := arr_int(arr, 3, -1, 2000) or_return
		flags := arr_int(arr, 4, 0, 3) or_return
		ax := arr_int(arr, 5, -127, 127) or_return
		ay := arr_int(arr, 6, -127, 127) or_return
		c.move = {dequant_unit(mx), dequant_unit(my)}
		c.max_step = step < 0 ? -1 : f32(step) / 1000
		c.auto_melee = flags & 1 != 0
		c.aim_live = flags & 2 != 0
		c.aim = {dequant_unit(ax), dequant_unit(ay)}
		append(commands, c)
	}
	for v in as {
		arr, arr_ok := sub_array(v, 8)
		if !arr_ok {
			resize(commands, base_c)
			return {}, false
		}
		a: Coop_Action
		fields_ok := true
		id, at, kind, ax, ay, index, arg, check: i64
		id, fields_ok = arr_int(arr, 0, 1, i64(max(u32)))
		if fields_ok do at, fields_ok = arr_int(arr, 1, 0, i64(max(u32)))
		if fields_ok do kind, fields_ok = arr_int(arr, 2, 1, i64(len(Coop_Action_Kind) - 1))
		if fields_ok do ax, fields_ok = arr_int(arr, 3, -127, 127)
		if fields_ok do ay, fields_ok = arr_int(arr, 4, -127, 127)
		if fields_ok do index, fields_ok = arr_int(arr, 5, -1, 255)
		if fields_ok do arg, fields_ok = arr_int(arr, 6, -1, 1024)
		if fields_ok do check, fields_ok = arr_int(arr, 7, 0, i64(max(u32)))
		if !fields_ok {
			resize(commands, base_c)
			resize(actions, base_a)
			return {}, false
		}
		a.id, a.at, a.kind = u32(id), u32(at), Coop_Action_Kind(kind)
		a.aim = {dequant_unit(ax), dequant_unit(ay)}
		a.index, a.arg, a.check = i32(index), i32(arg), u32(check)
		append(actions, a)
	}
	return pause, true
}

// Stable item fingerprint for index-validated inventory and shop actions.
coop_item_check :: proc(item: Item) -> u32 {
	h: u32 = 2166136261
	mix :: proc(h: ^u32, v: u32) {
		for i in 0 ..< 4 {
			h^ ~= (v >> (u32(i) * 8)) & 0xff
			h^ *= 16777619
		}
	}
	mix(&h, u32(item.kind))
	mix(&h, u32(item.rarity))
	mix(&h, u32(item.power))
	mix(&h, u32(item.defense))
	mix(&h, u32(item.cursed ? 1 : 0) | u32(item.unidentified ? 2 : 0))
	for b in transmute([]byte)item.name {
		h ~= u32(b)
		h *= 16777619
	}
	return h
}

// -------------------------------------------------------------- checkpoint --

// The world checkpoint reuses the save payload conversion (human decision
// 2026-10-09) plus the co-op seat data the solo document omits.
Coop_Checkpoint :: struct {
	payload:      Run_Save_Payload,
	partner:      Player,
	player_count: int,
	navs_valid:   bool,
}

COOP_CHECKPOINT_CHUNK_BYTES :: 160 * 1024 // base64 text per message
COOP_CHECKPOINT_MAX_BYTES   :: 4 * 1024 * 1024
COOP_CHECKPOINT_MAX_CHUNKS  :: 32

coop_checkpoint_json_options :: proc() -> json.Marshal_Options {
	return {use_enum_names = true}
}

// Serialize the host's run as a compact checkpoint document.
coop_checkpoint_encode :: proc(app: ^App, allocator := context.allocator) -> ([]byte, bool) {
	run_ensure_persisted_entity_ids(&app.run)
	checkpoint := Coop_Checkpoint{
		payload = run_save_payload_from_app(app),
		partner = app.run.players[1],
		player_count = app.run.player_count,
	}
	// Fog and discovery are per-client presentation; never ship the host's.
	checkpoint.payload.explored = {}
	data, err := json.marshal(checkpoint, coop_checkpoint_json_options(), allocator)
	return data, err == nil
}

Coop_Checkpoint_Chunk :: struct {
	id:    u64,
	index: int,
	count: int,
	total: int,
	sum:   string, // sha256 hex of the raw document; borrows the message
	epoch: u32,
	data:  string, // base64 text; borrows the message
}

coop_encode_checkpoint_chunks :: proc(id: u64, epoch: u32, raw: []byte, out: ^[dynamic][]byte, allocator := context.allocator) -> bool {
	if len(raw) == 0 || len(raw) > COOP_CHECKPOINT_MAX_BYTES do return false
	encoded := base64.encode(raw, allocator = context.temp_allocator)
	digest := np.sha256_digest(raw)
	hex := "0123456789abcdef"
	sum: [64]byte
	for b, i in digest {
		sum[i * 2] = hex[b >> 4]
		sum[i * 2 + 1] = hex[b & 0xf]
	}
	count := (len(encoded) + COOP_CHECKPOINT_CHUNK_BYTES - 1) / COOP_CHECKPOINT_CHUNK_BYTES
	if count > COOP_CHECKPOINT_MAX_CHUNKS do return false
	for i in 0 ..< count {
		start := i * COOP_CHECKPOINT_CHUNK_BYTES
		end := min(len(encoded), start + COOP_CHECKPOINT_CHUNK_BYTES)
		w: np.Json_Writer
		np.jw_init(&w, allocator)
		np.jw_begin(&w)
		np.jw_str(&w, "t", "checkpoint")
		np.jw_u64s(&w, "id", id)
		np.jw_int(&w, "i", i64(i))
		np.jw_int(&w, "n", i64(count))
		np.jw_int(&w, "sz", i64(len(raw)))
		np.jw_str(&w, "sum", string(sum[:]))
		np.jw_int(&w, "ep", i64(epoch))
		np.jw_str(&w, "d", encoded[start:end])
		np.jw_end(&w)
		append(out, np.jw_bytes(&w))
	}
	return true
}

coop_decode_checkpoint_chunk :: proc(obj: json.Object) -> (chunk: Coop_Checkpoint_Chunk, ok: bool) {
	chunk.id = np.read_u64s(obj, "id") or_return
	chunk.index = int(np.read_int(obj, "i", 0, COOP_CHECKPOINT_MAX_CHUNKS - 1) or_return)
	chunk.count = int(np.read_int(obj, "n", 1, COOP_CHECKPOINT_MAX_CHUNKS) or_return)
	chunk.total = int(np.read_int(obj, "sz", 1, COOP_CHECKPOINT_MAX_BYTES) or_return)
	chunk.sum = np.read_str(obj, "sum", 64) or_return
	chunk.epoch = u32(np.read_int(obj, "ep", 0, i64(max(u32))) or_return)
	chunk.data = np.read_str(obj, "d", COOP_CHECKPOINT_CHUNK_BYTES) or_return
	if chunk.index >= chunk.count || len(chunk.sum) != 64 do return {}, false
	return chunk, true
}

coop_checkpoint_verify :: proc(raw: []byte, sum: string) -> bool {
	digest := np.sha256_digest(raw)
	hex := "0123456789abcdef"
	if len(sum) != 64 do return false
	for b, i in digest {
		if sum[i * 2] != hex[b >> 4] || sum[i * 2 + 1] != hex[b & 0xf] do return false
	}
	return true
}

// Decode and validate a checkpoint document into a playable replica Run,
// written straight into the caller's destinations. Nothing is written unless
// every check passes.
//
// Deliberately not a by-value `Run` result: a 60 KB `Run` local that is both
// bulk-copied and then touched field by field makes LLVM's SROA scalarize the
// whole struct into hundreds of thousands of instructions, and InstCombine on
// the freestanding wasm32 target never finishes (observed 2026-10-11 as the
// public web lane timing out at the Odin -o:speed step).
// The checkpoint is a host-authored document and must clear the same strict
// validator as every control message before Odin's permissive core parser
// sees it: that parser has no depth limit and recurses into unknown keys, so
// a hash-correct document could otherwise overflow the joiner's stack
// (security audit 2026-10-11, finding 2). Limits sized for a full run save.
COOP_CHECKPOINT_JSON_LIMITS :: np.Json_Limits{
	max_bytes        = COOP_CHECKPOINT_MAX_BYTES,
	max_depth        = 24,
	max_values       = 2_000_000,
	max_string_bytes = 200 * 1024,
	max_key_bytes    = 64,
	max_object_keys  = 256,
}

coop_checkpoint_decode :: proc(raw: []byte, run: ^Run, panel: ^Story_Panel_State, minigame: ^Story_Minigame_State, cursor: ^int, turn_page: ^Turn_Page_State) -> bool {
	if !persistence_json_preflight(raw, COOP_CHECKPOINT_MAX_BYTES) do return false
	if err := np.json_validate(raw, COOP_CHECKPOINT_JSON_LIMITS); err != .None {
		platform_log(fmt.tprintf("[coop] checkpoint rejected by the strict validator: %v", err))
		return false
	}
	checkpoint := new(Coop_Checkpoint, context.temp_allocator)
	if err := json.unmarshal(raw, checkpoint); err != nil {
		run_save_payload_destroy(&checkpoint.payload)
		return false
	}
	if checkpoint.player_count != MAX_PLAYERS || !run_payload_validate(&checkpoint.payload) || !coop_player_valid(&checkpoint.partner) {
		run_save_payload_destroy(&checkpoint.payload)
		coop_player_destroy_strings(&checkpoint.partner)
		return false
	}
	turn_page^ = checkpoint.payload.turn_page
	run_take_payload_into(&checkpoint.payload, run, panel, minigame, cursor)
	run.players[1] = checkpoint.partner
	run.player_count = MAX_PLAYERS
	run_adopt_item_strings(run, &run.players[1].weapon)
	run_adopt_item_strings(run, &run.players[1].armor)
	for i in 0 ..< BAG_CAPACITY do run_adopt_item_strings(run, &run.players[1].bag[i])
	for slot in 0 ..< MAX_PLAYERS {
		p := &run.players[slot]
		p.prev_pos = p.pos
	}
	return true
}

coop_player_valid :: proc(p: ^Player) -> bool {
	if int(p.archetype) < 0 || int(p.archetype) >= len(Archetype_Id) do return false
	if p.bag_count < 0 || p.bag_count > BAG_CAPACITY do return false
	if !vec_finite(p.pos) || !vec_finite(p.facing) || !pos_on_map(p.pos) do return false
	if p.max_hp <= 0 || p.max_hp > 100_000 || p.hp > p.max_hp do return false
	return true
}

coop_player_destroy_strings :: proc(p: ^Player) {
	item_free :: proc(item: ^Item) {
		delete(item.name)
		delete(item.icon)
	}
	item_free(&p.weapon)
	item_free(&p.armor)
	for i in 0 ..< BAG_CAPACITY do item_free(&p.bag[i])
}

// Positions index tile arrays through the sim's own guards, but a host can
// only be trusted to keep them on the map it shipped.
pos_on_map :: proc(v: Vec2) -> bool {
	return v.x >= -1 && v.x <= f32(MAP_W) + 1 && v.y >= -1 && v.y <= f32(MAP_H) + 1
}

vec_finite :: proc(v: Vec2) -> bool {
	return !math.is_nan(v.x) && !math.is_nan(v.y) && !math.is_inf(v.x) && !math.is_inf(v.y) &&
		abs(v.x) < 10_000 && abs(v.y) < 10_000
}

// Joiner -> host: the adopted baseline; snapshots resume prediction after it.
coop_encode_checkpoint_ack :: proc(id: u64, allocator := context.allocator) -> []byte {
	w: np.Json_Writer
	np.jw_init(&w, allocator)
	np.jw_begin(&w)
	np.jw_str(&w, "t", "checkpoint_ack")
	np.jw_u64s(&w, "id", id)
	np.jw_end(&w)
	return np.jw_bytes(&w)
}

coop_encode_sync_request :: proc(allocator := context.allocator) -> []byte {
	return transmute([]byte)strings.clone(`{"t":"sync_request"}`, allocator)
}
