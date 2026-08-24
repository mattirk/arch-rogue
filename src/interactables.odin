package archrogue

// MX.5 — traps, shrines, and secret caches, ported from
// content/interactables.py + population.py + interactions.py +
// combat/projectiles.py + game.py update_secrets. Placement rolls live on
// their own RNG stream so pre-MX.5 seeds keep their enemy layouts.
// Raylib-free (hard rule 2).

INTERACTABLE_STREAM :: 10 // next free stream after the run plan's 9

// --- Traps ------------------------------------------------------------------

Trap_Kind :: enum u8 {
	Spike,
	Rune,
	Needle,
}

Trap_Def :: struct {
	name:        string,
	min_damage:  int,
	max_damage:  int,
	detail:      string, // interaction-hint detail (TRAP_HINTS)
	hint_color:  [4]u8, // prompt/floater identity
	draw_color:  [4]u8, // plate render identity (effects.py draw_trap)
	trigger_text: string, // static floater; the amount shows as a damage number
}

@(rodata)
TRAP_DEFS := [Trap_Kind]Trap_Def{
	.Spike = {
		name = "Spike Trap", min_damage = 14, max_damage = 22,
		detail = "Pressure plate; step away fast.",
		hint_color = {245, 95, 70, 255}, draw_color = {205, 75, 58, 255},
		trigger_text = "Spike Trap!",
	},
	.Rune = {
		name = "Rune Trap", min_damage = 13, max_damage = 21,
		detail = "Arcane sigil; avoid the glow.",
		hint_color = {180, 120, 245, 255}, draw_color = {160, 86, 230, 255},
		trigger_text = "Rune Trap!",
	},
	.Needle = {
		name = "Poison Needle", min_damage = 10, max_damage = 18,
		detail = "Needle trigger; keep distance.",
		hint_color = {120, 210, 110, 255}, draw_color = {110, 185, 95, 255},
		trigger_text = "Poison Needle!",
	},
}

// Traps spawn invisible; `revealed` flips permanently within reveal range and
// `reveal_progress` ramps 0→1 (dt*6 linear) for the materialize fade.
// Triggering clears `active`; spent traps stay in the array, undrawn.
Trap :: struct {
	entity_id:       u64,
	pos:             Vec2,
	kind:            Trap_Kind,
	damage:          int, // difficulty/depth-scaled at spawn
	active:          bool,
	revealed:        bool,
	reveal_progress: f32,
}

TRAP_REVEAL_RADIUS :: 1.35
TRAP_TRIGGER_RADIUS :: 0.55
TRAP_REVEAL_RATE :: 6.0 // full materialize in 1/6 s

// projectiles.py update_traps: reveal → fade → trigger, one pass, so a dash
// onto a hidden plate still shows it the same tick it fires.
tick_traps :: proc(run: ^Run, dt: f32) {
	player := &run.player
	for &trap in run.traps {
		if !trap.active do continue
		delta := trap.pos - player.pos
		distance_sq := delta.x * delta.x + delta.y * delta.y
		if player.hp > 0 && !trap.revealed &&
			distance_sq <= TRAP_REVEAL_RADIUS * TRAP_REVEAL_RADIUS {
			trap.revealed = true
		}
		if trap.revealed && trap.reveal_progress < 1 {
			trap.reveal_progress = min(1, trap.reveal_progress + dt * TRAP_REVEAL_RATE)
		}
		if player.hp <= 0 || distance_sq > TRAP_TRIGGER_RADIUS * TRAP_TRIGGER_RADIUS do continue
		trap.active = false
		def := &TRAP_DEFS[trap.kind]
		// Trap damage cannot be evaded (player.py:118 source=="trap").
		_ = damage_player_typed(run, trap.damage, .Physical, evadable = false, source_id = "trap")
		run.traps_triggered += 1
		append(&run.numbers, Damage_Number{pos = player.pos, kind = .Text, text = def.trigger_text})
		feel_emit(run, .Burst, trap.pos, def.hint_color, 0.46, 0.58)
		sfx_emit(run, sfx_trap_bank(trap.kind), trap.pos, spatial = true, emitter_id = trap.entity_id)
	}
}

// Revealed-only warning for the prompt line (interactions.py:796-812).
nearby_trap_warning :: proc(run: ^Run) -> ^Trap {
	nearest: ^Trap
	nearest_sq := f32(TRAP_REVEAL_RADIUS * TRAP_REVEAL_RADIUS)
	for &trap in run.traps {
		if !trap.active || !trap.revealed do continue
		delta := trap.pos - run.player.pos
		distance_sq := delta.x * delta.x + delta.y * delta.y
		if distance_sq < nearest_sq {
			nearest = &trap
			nearest_sq = distance_sq
		}
	}
	return nearest
}

// --- Shrines ----------------------------------------------------------------

Shrine_Kind :: enum u8 {
	Mending,
	Insight,
	War,
	Haste,
	Fortune,
	Oath,
	Twilight,
}

Shrine_Def :: struct {
	name:    string,
	detail:  string, // SHRINE_HINTS detail
	color:   [4]u8, // prompt, floater, and static-light identity
	message: string, // activation floater (static)
}

@(rodata)
SHRINE_DEFS := [Shrine_Kind]Shrine_Def{
	.Mending = {
		name = "Mending Shrine", detail = "Restores health and mana.",
		color = {105, 230, 125, 255}, message = "Shrine restored you",
	},
	.Insight = {
		name = "Insight Shrine", detail = "Reveals unidentified inventory gear.",
		color = {145, 205, 255, 255}, message = "Shrine revealed your gear",
	},
	.War = {
		name = "War Shrine", detail = "Grants combat focus and XP.",
		color = {245, 170, 90, 255}, message = "War Shrine grants focus",
	},
	.Haste = {
		name = "Haste Shrine", detail = "Refreshes stamina and quickens movement.",
		color = {235, 220, 95, 255}, message = "Haste Shrine quickens your stride",
	},
	.Fortune = {
		name = "Fortune Shrine", detail = "Spills extra offerings and loot.",
		color = {245, 215, 90, 255}, message = "Fortune Shrine spills offerings",
	},
	.Oath = {
		name = "Oath Shrine", detail = "Attempts to grant a class upgrade.",
		color = {190, 150, 245, 255}, message = "Oath Shrine grants a new technique",
	},
	.Twilight = {
		name = "Twilight Shrine", detail = "Trades blood for a unique relic.",
		color = {214, 92, 150, 255}, message = "Twilight Shrine trades blood for a relic",
	},
}

Shrine :: struct {
	entity_id: u64,
	pos:  Vec2,
	kind: Shrine_Kind,
	used: bool,
}

SHRINE_INTERACT_RADIUS :: 1.15
SHRINE_LIGHT_RADIUS :: 2.3
SHRINE_LIGHT_INTENSITY :: 0.55

// One permanent, capped stride blessing channel (costs.py:63-64).
HASTE_SHRINE_MOVE_BONUS :: 0.03
HASTE_SHRINE_MOVE_BONUS_CAP :: 0.09

nearby_shrine :: proc(run: ^Run) -> ^Shrine {
	nearest: ^Shrine
	nearest_sq := f32(SHRINE_INTERACT_RADIUS * SHRINE_INTERACT_RADIUS)
	for &shrine in run.shrines {
		if shrine.used do continue
		delta := shrine.pos - run.player.pos
		distance_sq := delta.x * delta.x + delta.y * delta.y
		if distance_sq < nearest_sq {
			nearest = &shrine
			nearest_sq = distance_sq
		}
	}
	return nearest
}

// interactions.py activate_shrine, minus the multiplayer Vigil branch.
activate_shrine :: proc(run: ^Run, shrine: ^Shrine) {
	if run == nil || shrine == nil || shrine.used do return
	player := &run.player
	shrine.used = true
	run.shrines_used += 1
	def := &SHRINE_DEFS[shrine.kind]
	switch shrine.kind {
	case .Mending:
		player.hp = player.max_hp
		player.mana = f32(player.max_mana)
	case .Insight:
		for &item, i in player.bag {
			if i >= player.bag_count do break
			item.unidentified = false
		}
	case .War:
		player_gain_xp(run, 25)
		player.stamina = f32(player.max_stamina)
	case .Haste:
		player.stamina = f32(player.max_stamina)
		player.dash_timer = 0
		player.shrine_move_bonus = min(
			HASTE_SHRINE_MOVE_BONUS_CAP,
			player.shrine_move_bonus + HASTE_SHRINE_MOVE_BONUS,
		)
	case .Fortune:
		append(&run.ground_items, make_loot(&run.loot_rng, player.pos, RUN_MODIFIERS[run.modifier].curse_chance_bonus, run))
		append(&run.ground_items, make_loot(&run.loot_rng, player.pos + {0.25, 0.25}, RUN_MODIFIERS[run.modifier].curse_chance_bonus, run))
	case .Oath:
		if !grant_random_discipline(run) {
			append(&run.numbers, Damage_Number{pos = player.pos, kind = .Text, text = "Oath Shrine finds no path left"})
			feel_emit(run, .Burst, shrine.pos, def.color, 0.58, 0.68)
			sfx_emit(run, sfx_shrine_bank(shrine.kind), shrine.pos, spatial = true, emitter_id = shrine.entity_id)
			return
		}
	case .Twilight:
		player.hp = max(1, player.hp - max(5, player.max_hp / 10))
		relic := make_unique(&run.loot_rng, player.archetype, run.depth)
		append(&run.ground_items, Ground_Item{item = relic, pos = player.pos})
		record_notable_loot(run, relic)
	}
	append(&run.numbers, Damage_Number{pos = player.pos, kind = .Text, text = def.message})
	feel_emit(run, .Burst, shrine.pos, def.color, 0.58, 0.68)
	sfx_emit(run, sfx_shrine_bank(shrine.kind), shrine.pos, spatial = true, emitter_id = shrine.entity_id)
}

// Oath Shrine / Forgotten Skill Altar: one free eligible discipline, chosen
// uniformly (pygame grant_discipline). Token-free by design.
grant_random_discipline :: proc(run: ^Run) -> bool {
	player := &run.player
	available: [len(Discipline_Id)]Discipline_Id
	count := 0
	for id in Discipline_Id {
		if discipline_state(player, id) != .Available do continue
		available[count] = id
		count += 1
	}
	if count == 0 do return false
	pick := available[rng_below(&run.loot_rng, count)]
	player.memory_tokens += 1 // free grant: lend the token the acquire path spends
	result := run_try_acquire_discipline(run, pick)
	if result != .Acquired {
		player.memory_tokens -= 1
		return false
	}
	append(&run.numbers, Damage_Number{pos = player.pos, kind = .Text, text = DISCIPLINES[pick].name})
	return true
}

// --- Secrets ----------------------------------------------------------------

Secret_Kind :: enum u8 {
	Hidden_Cache,
	Cursed_Reliquary,
	Sealed_Armory,
	Skill_Altar,
	Moonlit_Bargain,
	Cartographer_Stash, // per-floor roll, not in the room table
}

Secret_Def :: struct {
	name:    string,
	detail:  string,
	color:   [4]u8, // {0,0,0,0} = theme accent at read time
	message: string, // open floater (static)
}

@(rodata)
SECRET_DEFS := [Secret_Kind]Secret_Def{
	.Hidden_Cache = {
		name = "Hidden Cache", detail = "Open for a concealed reward.",
		color = {235, 205, 120, 255}, message = "Opened Hidden Cache",
	},
	.Cursed_Reliquary = {
		name = "Cursed Reliquary", detail = "May awaken a guardian for reward.",
		color = {214, 92, 150, 255}, message = "Opened Cursed Reliquary",
	},
	.Sealed_Armory = {
		name = "Sealed Armory", detail = "Contains equipment choices.",
		color = {245, 215, 90, 255}, message = "Opened Sealed Armory",
	},
	.Skill_Altar = {
		name = "Forgotten Skill Altar", detail = "Deepens your class build.",
		color = {145, 205, 255, 255}, message = "Forgotten altar deepens your build",
	},
	.Moonlit_Bargain = {
		name = "Moonlit Bargain", detail = "Costs blood for rare gear.",
		color = {214, 92, 150, 255}, message = "Moonlit bargain takes blood for gear",
	},
	.Cartographer_Stash = {
		name = "Lost Cartographer's Stash", detail = "Open for a concealed reward.",
		color = {}, message = "Opened Lost Cartographer's Stash", // theme accent
	},
}

Secret :: struct {
	entity_id: u64,
	pos:      Vec2,
	kind:     Secret_Kind,
	revealed: bool,
	opened:   bool,
}

SECRET_REVEAL_RADIUS :: 1.55
SECRET_INTERACT_RADIUS :: 1.1

secret_color :: proc(run: ^Run, kind: Secret_Kind) -> [4]u8 {
	color := SECRET_DEFS[kind].color
	if color == {} do color = THEMES[run.theme_index].accent
	return color
}

// game.py update_secrets: instantaneous, permanent, no LOS check, no cue.
tick_secrets :: proc(run: ^Run) {
	for &secret in run.secrets {
		if secret.revealed || secret.opened do continue
		delta := secret.pos - run.player.pos
		if delta.x * delta.x + delta.y * delta.y < SECRET_REVEAL_RADIUS * SECRET_REVEAL_RADIUS {
			secret.revealed = true
			append(&run.numbers, Damage_Number{pos = secret.pos, kind = .Text, text = "Secret found"})
		}
	}
}

nearby_secret :: proc(run: ^Run) -> ^Secret {
	nearest: ^Secret
	nearest_sq := f32(SECRET_INTERACT_RADIUS * SECRET_INTERACT_RADIUS)
	for &secret in run.secrets {
		if !secret.revealed || secret.opened do continue
		delta := secret.pos - run.player.pos
		distance_sq := delta.x * delta.x + delta.y * delta.y
		if distance_sq < nearest_sq {
			nearest = &secret
			nearest_sq = distance_sq
		}
	}
	return nearest
}

// interactions.py open_secret. The Cursed Reliquary roll is consumed only for
// that kind (short-circuit preserved); all drops stack on the cache tile.
open_secret :: proc(run: ^Run, secret: ^Secret) {
	if run == nil || secret == nil || secret.opened do return
	player := &run.player
	secret.opened = true
	// An opened cache stops being drawn, so it frees its tile first — a woken
	// reliquary guardian must not spawn inside solid furniture.
	solid_prop_remove(&run.dungeon, {int(secret.pos.x), int(secret.pos.y)})
	run.secrets_opened += 1
	def := &SECRET_DEFS[secret.kind]
	curse_bonus := RUN_MODIFIERS[run.modifier].curse_chance_bonus
	woke_guardian := false
	switch secret.kind {
	case .Skill_Altar:
		// Return value deliberately ignored (unlike the Oath Shrine).
		_ = grant_random_discipline(run)
	case .Moonlit_Bargain:
		player.hp = max(1, player.hp - max(6, player.max_hp / 8))
		slot: Item_Kind = rng_chance(&run.loot_rng, 0.5) ? .Weapon : .Armor
		reward := make_equipment(&run.loot_rng, slot, .Rare, curse_bonus, run)
		append(&run.ground_items, Ground_Item{item = reward, pos = secret.pos})
		record_notable_loot(run, reward)
	case .Cursed_Reliquary:
		if rng_chance(&run.loot_rng, 0.55) {
			woke_guardian = true
			guardian := enemy_make(pick_enemy_kind(&run.loot_rng, true), secret.pos + {0.3, 0.3}, run.depth)
			mod := RUN_MODIFIERS[run.modifier]
			apply_run_modifier_stats(&guardian, &mod)
			apply_story_enemy_stats(run, &guardian)
			apply_enemy_difficulty(&guardian, run.difficulty)
			promote_miniboss(&guardian, THEMES[run.theme_index].accent)
			enemy_ensure_id(run, &guardian)
			append(&run.enemies, guardian)
			append(&run.numbers, Damage_Number{pos = secret.pos, kind = .Text, text = "Reliquary wakes a sworn guardian"})
		} else {
			append(&run.ground_items, make_loot(&run.loot_rng, secret.pos, curse_bonus, run))
		}
	case .Sealed_Armory:
		for _ in 0 ..< 2 {
			slot: Item_Kind = rng_chance(&run.loot_rng, 0.5) ? .Weapon : .Armor
			append(&run.ground_items, Ground_Item{item = make_equipment(&run.loot_rng, slot, .Magic, curse_bonus, run), pos = secret.pos})
		}
	case .Cartographer_Stash:
		for _ in 0 ..< 2 {
			append(&run.ground_items, make_loot(&run.loot_rng, secret.pos, curse_bonus, run))
		}
	case .Hidden_Cache:
		append(&run.ground_items, make_loot(&run.loot_rng, secret.pos, curse_bonus, run))
	}
	if !woke_guardian {
		append(&run.numbers, Damage_Number{pos = secret.pos, kind = .Text, text = def.message})
	}
	feel_emit(run, .Burst, secret.pos, secret_color(run, secret.kind), 0.52, 0.62)
	sfx_emit(run, .Secret_Unlock, secret.pos, spatial = true, emitter_id = secret.entity_id)
}

// --- Placement (population.py:161-261) --------------------------------------

// Shrines and caches claim a whole tile, so their spot must be interior floor
// that nothing else reserves and that is not the stairs mouth. Consumes one
// room draw either way; a room with no legal tile simply gets no prop.
@(private = "file")
solid_prop_point :: proc(run: ^Run, room: Room, rng: ^Pcg32) -> (pos: Vec2, ok: bool) {
	d := &run.dungeon
	legal :: proc(d: ^Dungeon, room: Room, x, y: int) -> bool {
		if d.stairs.x == x && d.stairs.y == y do return false
		// A doorway's inner tile stays clear, or the door behind it seals.
		if tile_is_door_front(d, room, {x, y}) do return false
		if special_room_placement_reserved_occupies_tile(d, x, y) do return false
		return is_floor(d, f32(x) + 0.5, f32(y) + 0.5)
	}
	point := room_random_point(room, rng)
	if legal(d, room, int(point.x), int(point.y)) do return point, true
	for y in room.y + 1 ..< room.y + room.h - 1 {
		for x in room.x + 1 ..< room.x + room.w - 1 {
			if legal(d, room, x, y) do return {f32(x) + 0.5, f32(y) + 0.5}, true
		}
	}
	return {}, false
}

// Chances fold run-modifier + encounter pressure inside the pygame clamps,
// then the difficulty procs; secrets deliberately skip difficulty and read
// the modifier's *loot* bonus (population.py quirks preserved).
populate_interactables :: proc(run: ^Run) {
	rng := rng_make(derive_seed(run.seed, u64(run.depth)), stream = INTERACTABLE_STREAM)
	plan := run_floor_plan(run)
	encounter := ENCOUNTER_TEMPLATES[plan.encounter]
	mod := RUN_MODIFIERS[run.modifier]

	rooms := dungeon_rooms(&run.dungeon)
	for room, room_index in rooms {
		if room_index == 0 do continue
		final_room := room_index == len(rooms) - 1
		safe_room := special_room_is_safe(special_room_kind_for_room(&run.dungeon, room_index))

		if room_index > 1 {
			trap_base := 0.24 + mod.trap_bonus + encounter.trap_bonus +
				story_effect_clamped(run, .Trap_Bonus, -.1, .28)
			if rng_chance(&rng, difficulty_trap_chance(trap_base, run.difficulty)) {
				kind := Trap_Kind(rng_below(&rng, len(Trap_Kind)))
				def := &TRAP_DEFS[kind]
				raw := rng_range(&rng, def.min_damage, def.max_damage + 1) + max(0, run.depth - 3)
				trap := Trap{
					pos = population_room_point(&run.dungeon, room, &rng),
					kind = kind,
					damage = difficulty_trap_damage(raw, run.difficulty),
					active = true,
				}
				if !safe_room do append(&run.traps, trap)
			}
		}

		if room_index > 2 {
			shrine_base := 0.18 + mod.shrine_chance_bonus + story_effect_clamped(run, .Shrine_Bonus, -.1, .28)
			if rng_chance(&rng, difficulty_shrine_chance(shrine_base, run.difficulty)) {
				kind := Shrine_Kind(rng_below(&rng, len(Shrine_Kind)))
				// Reserve first: a drawn shrine is always a solid tile.
				if pos, ok := solid_prop_point(run, room, &rng);
					ok && solid_prop_add(&run.dungeon, {int(pos.x), int(pos.y)}) {
					append(&run.shrines, Shrine{pos = pos, kind = kind})
				}
			}
		}

		if room_index > 2 && !final_room {
			secret_chance := clamp(
				0.12 + mod.loot_bonus + encounter.secret_bonus +
					story_effect_clamped(run, .Secret_Bonus, -.1, .28),
				f32(0.03), f32(0.38),
			)
			if rng_chance(&rng, secret_chance) {
				kind := Secret_Kind(rng_below(&rng, len(Secret_Kind) - 1)) // stash excluded
				if pos, ok := solid_prop_point(run, room, &rng);
					ok && solid_prop_add(&run.dungeon, {int(pos.x), int(pos.y)}) {
					append(&run.secrets, Secret{pos = pos, kind = kind})
				}
			}
		}
	}

	// One Lost Cartographer's Stash roll per floor (population.py:246-261,
	// with the missing small-map guard added).
	stash_chance := clamp(
		0.36 + mod.loot_bonus + story_effect_clamped(run, .Secret_Bonus, -.1, .28) +
			difficulty_profile(run.difficulty).loot_chance_bonus * 0.5,
		f32(0.08), f32(0.60),
	)
	if len(rooms) > 3 && rng_chance(&rng, stash_chance) {
		room := rooms[2 + rng_below(&rng, len(rooms) - 3)]
		if pos, ok := solid_prop_point(run, room, &rng);
			ok && solid_prop_add(&run.dungeon, {int(pos.x), int(pos.y)}) {
			append(&run.secrets, Secret{pos = pos, kind = .Cartographer_Stash})
		}
	}
}

// --- The wall-face easter egg (interactions.py:686-733) ---------------------

// Wall tiles pick art variant (x*7 + y*13) % count in the renderer; variant 2
// is the worn wall_403 master whose face briefly forms when touched.
WALL_VARIANT_COUNT :: 10
SECRET_FACE_WALL_VARIANT :: 2
WALL_FACE_SECONDS :: 1.0 // authored frames 1..6 at 6 fps
WALL_FACE_TOUCH_RADIUS :: 1.15

wall_face_tile :: proc(x, y: int) -> bool {
	return (x * 7 + y * 13) % WALL_VARIANT_COUNT == SECRET_FACE_WALL_VARIANT
}

// 3x3 scan for the nearest face-bearing wall within touch range. Never
// advertised by any prompt; it sits last in the interact chain.
nearby_secret_face_wall :: proc(run: ^Run) -> (tile: [2]int, found: bool) {
	px, py := run.player.pos.x, run.player.pos.y
	cx, cy := int(px), int(py)
	best_sq := f32(WALL_FACE_TOUCH_RADIUS * WALL_FACE_TOUCH_RADIUS)
	for tx in cx - 1 ..= cx + 1 {
		for ty in cy - 1 ..= cy + 1 {
			if !dungeon_in_bounds(tx, ty) do continue
			if run.dungeon.tiles[tx][ty] != .Wall do continue
			if !wall_face_tile(tx, ty) do continue
			dx := f32(tx) + 0.5 - px
			dy := f32(ty) + 0.5 - py
			distance_sq := dx * dx + dy * dy
			if distance_sq <= best_sq {
				best_sq = distance_sq
				tile = {tx, ty}
				found = true
			}
		}
	}
	return
}

touch_secret_face_wall :: proc(run: ^Run) -> bool {
	tile, found := nearby_secret_face_wall(run)
	if !found do return false
	run.wall_face_tile = tile
	run.wall_face_timer = WALL_FACE_SECONDS
	run.wall_touches += 1
	return true
}
