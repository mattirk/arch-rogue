package archrogue_tests

// Headless tests for the raylib-free files (hard rule 2): no window needed.

import "core:crypto/hash"
import "core:encoding/hex"
import "core:encoding/json"
import "core:fmt"
import "core:os"
import "core:testing"
import ar "../src"

@(test)
iso_round_trip :: proc(t: ^testing.T) {
	points := [?]ar.Vec2{{0, 0}, {1, 0}, {0, 1}, {7, 3}, {15.5, 20.25}, {-4, 9}}
	for p in points {
		w := ar.world_from_tile(p)
		back := ar.tile_from_world(w)
		testing.expectf(
			t,
			abs(back.x - p.x) < 1e-4 && abs(back.y - p.y) < 1e-4,
			"round trip %v -> %v -> %v",
			p, w, back,
		)
	}
}

@(test)
rng_streams :: proc(t: ^testing.T) {
	a := ar.rng_make(7)
	b := ar.rng_make(7)
	c := ar.rng_make(8)
	same_seed_matches := true
	other_seed_differs := false
	for _ in 0 ..< 32 {
		x := ar.rng_next(&a)
		same_seed_matches = same_seed_matches && x == ar.rng_next(&b)
		other_seed_differs = other_seed_differs || x != ar.rng_next(&c)
	}
	testing.expect(t, same_seed_matches, "same seed must replay identically")
	testing.expect(t, other_seed_differs, "different seeds should diverge")

	r := ar.rng_make(99)
	for _ in 0 ..< 1000 {
		v := ar.rng_range(&r, 6, 13)
		testing.expect(t, v >= 6 && v < 13, "rng_range out of bounds")
		f := ar.rng_f32(&r)
		testing.expect(t, f >= 0 && f < 1, "rng_f32 out of bounds")
	}
}

@(test)
dungeon_generation_is_deterministic :: proc(t: ^testing.T) {
	rng1 := ar.rng_make(ar.derive_seed(42, 3))
	rng2 := ar.rng_make(ar.derive_seed(42, 3))
	d1, ok1 := ar.dungeon_generate(&rng1)
	d2, ok2 := ar.dungeon_generate(&rng2)
	testing.expect(t, ok1 && ok2, "generation failed")
	testing.expect(t, d1 == d2, "same seed must produce identical dungeons")

	rng3 := ar.rng_make(ar.derive_seed(43, 3))
	d3, ok3 := ar.dungeon_generate(&rng3)
	testing.expect(t, ok3, "generation failed")
	testing.expect(t, d1 != d3, "different seeds should differ")
}

// Every non-wall tile must be reachable from the spawn room, treating closed
// doors as passable (they open). Covers normal and boss floors over many
// seeds — the door-seal pass must never wall off a corridor for good.
@(test)
floors_fully_connected :: proc(t: ^testing.T) {
	for seed_i in 1 ..= 24 {
		seed := u64(seed_i)
		boss := seed_i % 4 == 0
		rng := ar.rng_make(ar.derive_seed(seed, 1))
		d, ok := ar.dungeon_generate(&rng, {boss_arena = boss})
		testing.expectf(t, ok, "generation failed for seed %v (boss=%v)", seed, boss)
		if !ok do continue

		visited: [ar.MAP_W][ar.MAP_H]bool
		queue: [ar.MAP_W * ar.MAP_H][2]int
		head, tail := 0, 0
		start := ar.room_center(ar.dungeon_rooms(&d)[0])
		visited[start.x][start.y] = true
		queue[tail] = start
		tail += 1
		dirs := [4][2]int{{1, 0}, {-1, 0}, {0, 1}, {0, -1}}
		for head < tail {
			p := queue[head]
			head += 1
			for dir in dirs {
				n := p + dir
				if !ar.dungeon_in_bounds(n.x, n.y) || visited[n.x][n.y] do continue
				if d.tiles[n.x][n.y] == .Wall do continue
				visited[n.x][n.y] = true
				queue[tail] = n
				tail += 1
			}
		}

		unreachable := 0
		for x in 0 ..< ar.MAP_W {
			for y in 0 ..< ar.MAP_H {
				if d.tiles[x][y] != .Wall && !visited[x][y] do unreachable += 1
			}
		}
		testing.expectf(t, unreachable == 0, "seed %v (boss=%v): %v unreachable tiles", seed, boss, unreachable)
		testing.expect(t, visited[d.stairs.x][d.stairs.y], "stairs unreachable")
		testing.expectf(
			t,
			d.room_count >= ar.MIN_ROOM_COUNT && d.room_count <= ar.MAX_ROOMS_CAP,
			"room count %v out of range",
			d.room_count,
		)
		if boss {
			last := ar.dungeon_rooms(&d)[d.room_count - 1]
			testing.expect(t, ar.room_is_boss_arena(last), "boss floor generated without an arena-sized final room")
		}
	}
}

// A closed door must be a real doorway: wall on both flanking sides along
// one axis, walkable floor through it on the other. Anything else means the
// seal pass painted doors onto the wrong perimeter tiles.
@(test)
doors_are_proper_doorways :: proc(t: ^testing.T) {
	for seed_i in 1 ..= 24 {
		rng := ar.rng_make(ar.derive_seed(u64(seed_i), 1))
		d, ok := ar.dungeon_generate(&rng)
		if !ok do continue
		door_count := 0
		for x in 0 ..< ar.MAP_W {
			for y in 0 ..< ar.MAP_H {
				if d.tiles[x][y] != .Closed_Door do continue
				door_count += 1
				wall :: ar.Tile_Kind.Wall
				h_flanks_walled := d.tiles[x - 1][y] == wall && d.tiles[x + 1][y] == wall
				v_flanks_walled := d.tiles[x][y - 1] == wall && d.tiles[x][y + 1] == wall
				h_through := ar.is_walkable(&d, f32(x) - 0.5, f32(y) + 0.5) && ar.is_walkable(&d, f32(x) + 1.5, f32(y) + 0.5)
				v_through := ar.is_walkable(&d, f32(x) + 0.5, f32(y) - 0.5) && ar.is_walkable(&d, f32(x) + 0.5, f32(y) + 1.5)
				proper := (h_flanks_walled && v_through) || (v_flanks_walled && h_through)
				testing.expectf(t, proper, "seed %v: door at %v,%v is not a proper doorway", seed_i, x, y)
			}
		}
		testing.expectf(t, door_count > 0, "seed %v generated a floor with no doors", seed_i)
	}
}

// All eight tile-space directions must land on their manifest sheet rows
// (0 south, 1 south-east, 2 east, 3 north-east, 4 north, 5 north-west,
// 6 west, 7 south-west) after the screen-space projection.
@(test)
facing_maps_to_sheet_rows :: proc(t: ^testing.T) {
	cases := [8]struct {
		facing: ar.Vec2,
		row:    int,
	}{
		{{1, 1}, 0}, // screen south
		{{1, 0}, 1}, // screen south-east
		{{1, -1}, 2}, // screen east
		{{0, -1}, 3}, // screen north-east
		{{-1, -1}, 4}, // screen north
		{{-1, 0}, 5}, // screen north-west
		{{-1, 1}, 6}, // screen west
		{{0, 1}, 7}, // screen south-west
	}
	for c in cases {
		got := ar.sprite_row_for_facing(c.facing)
		testing.expectf(t, got == c.row, "facing %v: got row %v, want %v", c.facing, got, c.row)
	}
}

@(test)
archetype_table_complete :: proc(t: ^testing.T) {
	for id in ar.Archetype_Id {
		def := ar.ARCHETYPES[id]
		testing.expectf(t, def.name != "" && def.sprite != "", "%v missing name/sprite", id)
		testing.expectf(t, def.speed > 0 && def.max_hp > 0 && def.max_stamina > 0, "%v has zeroed stats", id)
	}
}

@(test)
starter_loadouts_and_move_ratings_match_pygame :: proc(t: ^testing.T) {
	weapon_power := [ar.Archetype_Id]int{.Warden=3, .Rogue=6, .Arcanist=1, .Acolyte=2, .Ranger=5}
	armor_defense := [ar.Archetype_Id]int{.Warden=3, .Rogue=1, .Arcanist=1, .Acolyte=2, .Ranger=2}
	expected_speed := [ar.Archetype_Id]f32{.Warden=2.68, .Rogue=3.16, .Arcanist=2.6, .Acolyte=2.64, .Ranger=2.96}
	for archetype in ar.Archetype_Id {
		run: ar.Run
		ar.run_start(&run, ar.derive_seed(4100+u64(archetype), 0), archetype)
		testing.expect(t, run.player.has_weapon && run.player.has_armor, "every class needs its mundane starting equipment")
		testing.expectf(t, run.player.weapon.power == weapon_power[archetype], "%v starter weapon power changed", archetype)
		testing.expectf(t, run.player.armor.defense == armor_defense[archetype], "%v starter armor changed", archetype)
		testing.expectf(t, abs(ar.player_speed(&run.player)-expected_speed[archetype]) < 1e-4, "%v speed %.3f, want %.3f", archetype, ar.player_speed(&run.player), expected_speed[archetype])
		ar.run_destroy(&run)
	}

	rogue := ar.Player{archetype=.Rogue, has_weapon=true, has_armor=true}
	rogue.weapon.move_speed = .28
	rogue.armor.move_speed = .28
	testing.expect(t, abs(ar.player_speed(&rogue)-3.64) < 1e-4, "archetype and gear movement bonuses must share the +30% cap")
	rogue.statuses[.Chilled] = 1
	testing.expect(t, abs(ar.player_speed(&rogue)-3.64*.82) < 1e-4, "Chill must multiply after the shared movement cap")
}

// Walking into a wall must stop at the collision radius and never tunnel;
// the free axis keeps sliding.
@(test)
player_movement_collides_and_slides :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(11, 0), .Warden)
	defer ar.run_destroy(&run)
	room := ar.dungeon_rooms(&run.dungeon)[0]

	// Start inside the spawn room and push straight west into its wall.
	clear(&run.enemies)
	run.player.pos = {f32(room.x) + 1.5, f32(room.y) + 1.5}
	run.player.prev_pos = run.player.pos
	for _ in 0 ..< 240 {
		ar.sim_tick(&run, {-1, 0})
		p := run.player.pos
		testing.expectf(
			t,
			!ar.blocked_for_radius(&run.dungeon, p.x, p.y, block_stairs = true),
			"player ended up inside geometry at %v",
			p,
		)
	}
	// Wall column sits at room.x - 1, so x should have stopped near
	// room.x + radius (floor starts at room.x).
	wall_stop := run.player.pos.x - f32(room.x)
	max_gap := ar.ACTOR_MOVE_COLLISION_RADIUS + ar.player_speed(&run.player)*ar.SIM_DT
	testing.expectf(t, wall_stop >= ar.ACTOR_MOVE_COLLISION_RADIUS && wall_stop <= max_gap+.001, "expected to stop within one fixed step of wall, got x=%v (room.x=%v)", run.player.pos.x, room.x)

	// Diagonal into the same wall: x stays clamped, y keeps sliding.
	y_before := run.player.pos.y
	for _ in 0 ..< 30 {
		ar.sim_tick(&run, {-1, 1})
	}
	testing.expect(t, run.player.pos.y > y_before + 0.5, "expected to slide along the wall")
}

// Find an open, LOS-clear position near the player at one of the cardinal
// offsets; returns false if the room is too cramped.
@(private = "file")
open_spot_near_player :: proc(run: ^ar.Run, reach: f32) -> (pos: ar.Vec2, found: bool) {
	offsets := [4]ar.Vec2{{reach, 0}, {0, reach}, {-reach, 0}, {0, -reach}}
	for off in offsets {
		c := run.player.pos + off
		if ar.blocked_for_radius(&run.dungeon, c.x, c.y) do continue
		if !ar.line_of_sight(&run.dungeon, run.player.pos.x, run.player.pos.y, c.x, c.y) do continue
		return c, true
	}
	return pos, false
}

@(test)
population_is_deterministic_and_spares_spawn_room :: proc(t: ^testing.T) {
	a, b: ar.Run
	ar.run_start(&a, ar.derive_seed(21, 0), .Warden)
	ar.run_start(&b, ar.derive_seed(21, 0), .Warden)
	defer ar.run_destroy(&a)
	defer ar.run_destroy(&b)
	testing.expect(t, len(a.enemies) > 0, "floors must spawn enemies")
	testing.expect(t, len(a.enemies) == len(b.enemies), "same seed, same enemy count")
	for i in 0 ..< min(len(a.enemies), len(b.enemies)) {
		same := a.enemies[i].kind == b.enemies[i].kind && a.enemies[i].pos == b.enemies[i].pos
		testing.expect(t, same, "same seed must spawn identical enemies")
	}
	spawn_room := ar.dungeon_rooms(&a.dungeon)[0]
	for &enemy in a.enemies {
		tx, ty := int(enemy.pos.x), int(enemy.pos.y)
		inside :=
			tx >= spawn_room.x && tx < spawn_room.x + spawn_room.w &&
			ty >= spawn_room.y && ty < spawn_room.y + spawn_room.h
		testing.expect(t, !inside, "spawn room must stay safe")
	}
}

@(test)
melee_enemy_chases_and_strikes :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(11, 0), .Warden)
	defer ar.run_destroy(&run)
	clear(&run.enemies)
	spot, found := open_spot_near_player(&run, 2.2)
	testing.expect(t, found, "no open spot near player")
	if !found do return
	append(&run.enemies, ar.enemy_make(.Ghoul, spot, 1))

	hp_before := run.player.hp
	dist_before := abs(spot.x - run.player.pos.x) + abs(spot.y - run.player.pos.y)
	aggroed := false
	for _ in 0 ..< 240 {
		ar.sim_tick(&run, {})
		if len(run.enemies) > 0 && run.enemies[0].ai != .Idle do aggroed = true
	}
	testing.expect(t, aggroed, "ghoul never aggroed")
	enemy := run.enemies[0]
	dist_after := abs(enemy.pos.x - run.player.pos.x) + abs(enemy.pos.y - run.player.pos.y)
	testing.expect(t, dist_after < dist_before, "ghoul must close the distance")
	testing.expectf(t, run.player.hp < hp_before, "ghoul should have landed a strike (hp %v)", run.player.hp)
}

@(test)
player_melee_kills_and_grants_xp :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(11, 0), .Warden)
	defer ar.run_destroy(&run)
	clear(&run.enemies)
	spot, found := open_spot_near_player(&run, 1.0)
	testing.expect(t, found, "no open spot near player")
	if !found do return
	append(&run.enemies, ar.enemy_make(.Ghoul, spot, 1))
	aim := spot - run.player.pos

	dmg_per_swing := ar.player_melee_damage(&run.player)
	ar.player_melee(&run, aim)
	first_hp := run.enemies[0].hp
	first_damage := 42 - first_hp
	testing.expectf(t, first_damage >= dmg_per_swing - 3 && first_damage <= dmg_per_swing + 4, "first swing damage %v outside pygame's -3..+4 roll", first_damage)
	ar.player_melee(&run, aim) // still on cooldown: no-op
	testing.expect(t, run.enemies[0].hp == first_hp, "cooldown must gate swings")

	for run.enemies[0].hp > 0 {
		run.player.melee_timer = 0
		run.player.stamina = 100
		ar.player_melee(&run, aim)
	}
	run.hitstop_ticks = 0 // the sweep, not the killing swing's freeze, is under test
	ar.sim_tick(&run, {}) // sweep the corpse
	testing.expect(t, len(run.enemies) == 0, "dead ghoul must be removed")
	testing.expect(t, run.player.xp == ar.ENEMY_DEFS[.Ghoul].xp, "kill must grant xp")
	testing.expect(t, len(run.numbers) > 0, "damage numbers must spawn")
}

@(test)
ranged_enemy_fires_and_hits :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(11, 0), .Warden)
	defer ar.run_destroy(&run)
	clear(&run.enemies)
	spot, found := open_spot_near_player(&run, 2.8) // inside kite band and range
	testing.expect(t, found, "no open spot near player")
	if !found do return
	append(&run.enemies, ar.enemy_make(.Bone_Imp, spot, 1))
	run.enemies[0].ai = .Chase

	hp_before := run.player.hp
	fired := false
	for _ in 0 ..< 180 {
		ar.sim_tick(&run, {})
		if len(run.projectiles) > 0 do fired = true
	}
	testing.expect(t, fired, "bone imp never fired")
	testing.expectf(t, run.player.hp < hp_before, "bolt should have hit the player (hp %v)", run.player.hp)
}

@(test)
projectile_dies_on_walls :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(11, 0), .Warden)
	defer ar.run_destroy(&run)
	clear(&run.enemies)
	append(&run.projectiles, ar.Projectile{
		pos = run.player.pos, prev_pos = run.player.pos,
		vel = {-6, 0}, damage = 5, from_player = true, ttl = 3,
	})
	for _ in 0 ..< 180 {
		ar.sim_tick(&run, {})
	}
	testing.expect(t, len(run.projectiles) == 0, "projectile must die on the wall")
}

@(test)
core_bolt_spawns_one_projectile :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(11, 0), .Rogue)
	defer ar.run_destroy(&run)
	clear(&run.enemies)
	ar.player_skill(&run, {1, 0})
	testing.expectf(t, len(run.projectiles) == 1, "unupgraded core bolt must spawn one projectile, got %v", len(run.projectiles))
	testing.expect(t, run.player.bolt_timer > 0, "bolt must go on cooldown")
	ar.player_skill(&run, {1, 0}) // on cooldown: no-op
	testing.expect(t, len(run.projectiles) == 1, "cooldown must gate the bolt")
}

@(test)
xp_levels_up_with_growth :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(11, 0), .Warden)
	defer ar.run_destroy(&run)
	base := ar.ARCHETYPES[.Warden]

	run.player.hp = 50 // level-up must fully heal the grown pool
	ar.player_gain_xp(&run, ar.XP_BASE)
	p := &run.player
	testing.expectf(t, p.level == 2, "level %v, want 2", p.level)
	testing.expect(t, p.next_xp == 150, "next_xp should be 150")
	testing.expect(t, p.xp == 0, "xp overflow should carry (none here)")
	testing.expect(t, p.max_hp == base.max_hp + ar.LEVEL_HP_GAIN && p.hp == p.max_hp, "hp must grow and refill")
	testing.expect(t, p.max_mana == base.max_mana + ar.LEVEL_MANA_GAIN, "mana pool must grow")
	testing.expect(t, p.max_stamina == base.max_stamina + ar.LEVEL_STAMINA_GAIN, "stamina pool must grow")
}

@(test)
depth_scaling_matches_pygame_curve :: proc(t: ^testing.T) {
	shallow := ar.enemy_make(.Ghoul, {10, 10}, 1)
	testing.expect(t, shallow.max_hp == 42 && shallow.damage == 10, "depth 1 must be unscaled")

	deep := ar.enemy_make(.Ghoul, {10, 10}, 6)
	// hp: 42 * (1 + 5*0.045 + 1*0.05) = 42 * 1.275 = 53.55 -> 53
	// damage: 10 + (6-4)/2 + (6-5) = 12
	testing.expectf(t, deep.max_hp == 53, "depth 6 hp %v, want 53", deep.max_hp)
	testing.expectf(t, deep.damage == 12, "depth 6 damage %v, want 12", deep.damage)
}

@(test)
loot_rolls_deterministic_and_valid :: proc(t: ^testing.T) {
	a := ar.rng_make(ar.derive_seed(99, 5), 2)
	b := ar.rng_make(ar.derive_seed(99, 5), 2)
	for _ in 0 ..< 80 {
		ga := ar.make_loot(&a, {10, 10})
		gb := ar.make_loot(&b, {10, 10})
		testing.expect(t, ga.item == gb.item, "same stream must roll identical loot")

		item := ga.item
		allowance := ar.RARITIES[item.rarity].affixes
		testing.expectf(t, item.affix_count <= allowance, "%v affixes on %v %v", item.affix_count, item.rarity, item.name)
		for i in 0 ..< item.affix_count {
			def := ar.AFFIX_DEFS[item.affixes[i].kind]
			ok := (item.kind == .Weapon && def.weapon) || (item.kind == .Armor && def.armor)
			testing.expectf(t, ok, "affix %v illegal on %v", def.name, item.kind)
		}
		if item.kind == .Heal_Potion || item.kind == .Mana_Potion {
			testing.expect(t, item.rarity == .Common, "potions are Common")
		}
	}
}

@(test)
m8_action_hud_manifest_is_complete :: proc(t: ^testing.T) {
	data, read_err := os.read_entire_file_from_path("assets/hud/manifest.json", context.allocator)
	if read_err != nil {
		testing.expect(t, false, "committed canonical assets/hud/manifest.json is missing")
		return
	}
	defer delete(data)
	value, err := json.parse(data)
	testing.expect(t, err == nil, "action HUD manifest does not parse")
	if err != nil do return
	defer json.destroy_value(value)
	root := value.(json.Object)
	testing.expect(t, int(root["format_version"].(json.Float)) == 1, "action HUD manifest format changed")
	icons := root["icons"].(json.Object)
	testing.expectf(t, len(icons) == 24, "action HUD has %v icons, want 24", len(icons))
	for icon in ar.Action_Icon {
		if icon == .Invalid do continue
		key := ar.ACTION_ICON_KEYS[icon]
		entry, found := icons[key]
		testing.expectf(t, found, "action icon %v missing", key)
		if !found do continue
		obj := entry.(json.Object)
		size := obj["size"].(json.Array)
		expected_size := 32
		if icon == .Slot_Frame do expected_size = 159
		testing.expectf(
			t,
			len(size) == 2 && int(size[0].(json.Float)) == expected_size && int(size[1].(json.Float)) == expected_size,
			"%v must be %vx%v",
			key,
			expected_size,
			expected_size,
		)
		file := obj["file"].(json.String)
		path := fmt.aprintf("assets/hud/%s", file)
		png, png_err := os.read_entire_file_from_path(path, context.allocator)
		testing.expectf(t, png_err == nil && len(png) > 0, "%v references missing PNG %v", key, path)
		if png_err == nil do delete(png)
		delete(path)
	}
	loadouts := root["loadouts"].(json.Object)
	for name in ([5]string{"warden","rogue","arcanist","acolyte","ranger"}) {
		rows, found := loadouts[name]
		testing.expectf(t, found, "%v action loadout missing", name)
		if !found do continue
		row := rows.(json.Array)
		testing.expectf(t, len(row) == ar.ACTION_SLOT_COUNT, "%v loadout has %v slots", name, len(row))
		for key_value in row {
			key := key_value.(json.String)
			_, known := icons[key]
			testing.expectf(t, known, "%v loadout references unknown icon %v", name, key)
		}
	}
	variants := root["variants"].(json.Object)
	testing.expect(t, variants["ranger_spirit_beast_attack"].(json.String) == "hud.action.ranger.spirit_beast_angry", "Ranger attack-command variant changed")
}

@(test)
pickup_requires_interact_then_equips_and_bags :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(11, 0), .Warden)
	defer ar.run_destroy(&run)
	clear(&run.enemies)
	clear(&run.ground_items)

	sword := ar.Item{kind = .Weapon, name = "Iron Sword", power = 5}
	append(&run.ground_items, ar.Ground_Item{item = sword, pos = run.player.pos})
	starting_damage := ar.player_melee_damage(&run.player)
	starter_power := run.player.weapon.power
	starter_name := run.player.weapon.name
	ar.sim_tick(&run, {})
	testing.expect(t, run.player.weapon.name == starter_name, "walking over loot must not pick it up")
	testing.expect(t, len(run.ground_items) == 1, "loot must wait on the floor for E")
	_ = ar.player_interact(&run)
	testing.expect(t, run.player.weapon.name == starter_name && run.player.bag_count == 1, "E must put equipment in the bag for deliberate identification/equip")
	testing.expect(t, len(run.ground_items) == 0, "picked up item must leave the floor")
	ar.equip_from_bag(&run.player, 0)
	testing.expect(t, run.player.has_weapon, "using the bag row must equip the weapon")
	testing.expectf(
		t,
		ar.player_melee_damage(&run.player) == starting_damage - starter_power + 5,
		"weapon power must add to melee damage",
	)
	testing.expect(t, run.player.bag[0].name == starter_name, "starter weapon must swap into the bag")

	axe := ar.Item{kind = .Weapon, name = "Hunter Axe", power = 7}
	append(&run.ground_items, ar.Ground_Item{item = axe, pos = run.player.pos})
	_ = ar.player_interact(&run)
	testing.expect(t, run.player.bag_count == 2, "second weapon stays in the bag")

	// Equipping from the bag swaps the pieces.
	ar.equip_from_bag(&run.player, 1)
	testing.expect(t, run.player.weapon.name == "Hunter Axe", "bag weapon must equip")
	testing.expect(t, run.player.bag[1].name == "Iron Sword", "old weapon must land in the bag slot")
}

@(test)
potions_heal_capped_and_gated :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(11, 0), .Warden)
	defer ar.run_destroy(&run)
	p := &run.player
	p.heal_potions = 2
	p.hp = p.max_hp - 10 // less damage than one flask heals

	ar.player_use_potion(&run, .Heal_Potion)
	testing.expect(t, p.hp == p.max_hp, "heal must cap at max hp")
	testing.expect(t, p.heal_potions == 1, "flask must be consumed")

	ar.player_use_potion(&run, .Heal_Potion) // full hp: refuse to waste
	testing.expect(t, p.heal_potions == 1, "full-hp quaff must not consume")

	p.hp = 10
	p.potion_timer = 0 // cooldown from the successful quaff above
	ar.player_use_potion(&run, .Heal_Potion)
	first := p.hp
	testing.expect(t, first == 10 + ar.HEAL_POTION_AMOUNT, "heal amount ported (35)")
	ar.player_use_potion(&run, .Heal_Potion) // cooldown gate
	testing.expect(t, p.hp == first, "potion cooldown must gate chugging")
}

@(test)
lifesteal_heals_on_melee :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(11, 0), .Warden)
	defer ar.run_destroy(&run)
	clear(&run.enemies)
	spot, found := open_spot_near_player(&run, 1.0)
	testing.expect(t, found, "no open spot")
	if !found do return
	append(&run.enemies, ar.enemy_make(.Ghoul, spot, 1))

	run.player.weapon = ar.Item{kind = .Weapon, name = "Leech Blade", power = 2,
		lifesteal = 0.5, affixes = {{kind = .Vampiric}, {}, {}}, affix_count = 1}
	run.player.has_weapon = true
	run.player.hp = 50
	ar.player_melee(&run, spot - run.player.pos)
	testing.expectf(t, run.player.hp > 50, "lifesteal must heal on hit (hp %v)", run.player.hp)
}

// run_flow.py light_depths_for_run: depths 1-4 always light, 5+ coin flip.
@(test)
dark_floors_follow_run_flow_rule :: proc(t: ^testing.T) {
	saw_dark, saw_light := false, false
	for seed_i in 1 ..= 16 {
		run: ar.Run
		ar.run_start(&run, ar.derive_seed(u64(seed_i), 0), .Warden)
		defer ar.run_destroy(&run)
		for run.depth < 4 {
			testing.expectf(t, !run.dark_floor, "depth %v must be light (seed %v)", run.depth, seed_i)
			ar.run_descend(&run)
		}
		for run.depth < 9 {
			ar.run_descend(&run)
			if run.dark_floor do saw_dark = true
			if !run.dark_floor do saw_light = true
		}
	}
	testing.expect(t, saw_dark, "no dark floor rolled across 16 seeds")
	testing.expect(t, saw_light, "no light deep floor rolled across 16 seeds")

	// Determinism: same seed, same darkness pattern.
	a, b: ar.Run
	ar.run_start(&a, ar.derive_seed(5, 0), .Warden)
	ar.run_start(&b, ar.derive_seed(5, 0), .Warden)
	defer ar.run_destroy(&a)
	defer ar.run_destroy(&b)
	for a.depth < 10 {
		ar.run_descend(&a)
		ar.run_descend(&b)
		testing.expect(t, a.dark_floor == b.dark_floor, "darkness must be seed-stable")
	}
}

@(test)
sim_emits_sfx_events :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(11, 0), .Warden)
	defer ar.run_destroy(&run)
	clear(&run.enemies)
	clear(&run.sfx)

	ar.player_melee(&run, {1, 0})
	has_swing := false
	for e in run.sfx {
		if e.bank == .Melee_Swing_Warden {
			has_swing = e.spatial && e.pos == run.player.pos
		}
	}
	testing.expect(t, has_swing, "Warden melee must emit a spatial Melee_Swing_Warden at the player")

	clear(&run.sfx)
	run.player.hp = 50
	ar.player_use_potion(&run, .Heal_Potion)
	has_potion := false
	for e in run.sfx {
		if e.bank == .Potion_Drink {
			has_potion = !e.spatial
		}
	}
	testing.expect(t, has_potion, "potion must emit non-spatial Potion_Drink")

	clear(&run.sfx)
	ar.run_descend(&run) // dev descend does not emit; interact path does
	ar.damage_player(&run, 20)
	has_hurt := false
	for e in run.sfx {
		if e.bank == .Player_Hurt_Light {
			has_hurt = !e.spatial
		}
	}
	testing.expect(t, has_hurt, "taking 20 damage must emit non-spatial Player_Hurt_Light")
}

@(test)
title_flow_transitions :: proc(t: ^testing.T) {
	app: ar.App
	ar.app_init(&app, ar.derive_seed(11, 0))
	defer ar.run_destroy(&app.run)
	testing.expect(t, app.mode == .Title, "boot must land on the title screen")
	confirm := ar.Intent{confirm = true}
	mode_was := app.mode
	ar.app_apply(&app, confirm)
	cue, has_cue := ar.audio_cue_for_transition(confirm, mode_was, app.mode)
	testing.expect(t, app.mode == .Select, "Enter on title must open archetype select")
	testing.expect(t,has_cue&&cue==.Ui_Confirm,"Title -> Select must retain ordinary confirmation audio")
	ar.app_apply(&app, ar.Intent{back = true})
	testing.expect(t, app.mode == .Title, "Esc in select must return to title")
	ar.app_apply(&app, confirm)
	mode_was = app.mode
	ar.app_apply(&app, confirm)
	_, has_cue = ar.audio_cue_for_transition(confirm, mode_was, app.mode)
	testing.expect(t, app.mode == .Playing, "confirm twice must start a run")
	testing.expect(t,!has_cue,"Select -> Playing must suppress the generic confirmation cue")
	start_count:=0
	for queued in app.run.sfx {
		testing.expect(t,queued.bank==.Run_Start,"starting a run must not queue a second semantic cue")
		if queued.bank==.Run_Start {
			start_count+=1
			testing.expect(t,!queued.spatial,"Run_Start must be non-spatial")
		}
	}
	testing.expect(t,start_count==1,"starting a selected archetype must emit exactly one Run_Start cue")
}

@(test)
fog_of_war_is_ready_on_spawn_and_floor_transition :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(1011, 0), .Warden)
	defer ar.run_destroy(&run)
	px,py := int(run.player.pos.x),int(run.player.pos.y)
	testing.expect(t,run.visible[px][py]&&run.explored[px][py],"spawn frame must not render before visibility exists")
	first_epoch := run.floor_epoch
	ar.run_descend(&run)
	px,py = int(run.player.pos.x),int(run.player.pos.y)
	testing.expect(t,run.visible[px][py]&&run.explored[px][py],"floor transition must refresh visibility before its first frame")
	testing.expect(t,run.floor_epoch>first_epoch,"floor regeneration must invalidate presentation caches")
	same_depth_epoch := run.floor_epoch
	ar.run_regenerate_floor(&run,true)
	testing.expect(t,run.floor_epoch>same_depth_epoch,"same-depth boss reroll must also invalidate presentation caches")
}

// LOS-based fog: tiles in radius with line of sight become visible+explored;
// tiles behind walls stay dark even inside the radius; memory persists.
@(test)
fog_of_war_reveals_and_remembers :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(11, 0), .Warden)
	defer ar.run_destroy(&run)
	clear(&run.enemies)
	room := ar.dungeon_rooms(&run.dungeon)[0]

	// Stand against the west wall of the spawn room.
	run.player.pos = {f32(room.x) + 0.6, f32(room.y) + f32(room.h / 2) + 0.5}
	run.player.prev_pos = run.player.pos
	ar.sim_tick(&run, {})

	px, py := int(run.player.pos.x), int(run.player.pos.y)
	testing.expect(t, run.visible[px][py], "player tile must be visible")
	testing.expect(t, run.explored[px][py], "player tile must be explored")

	// The wall right beside is visible; solid rock two tiles beyond is not,
	// despite being inside the sight radius.
	testing.expect(t, run.visible[room.x - 1][py], "adjacent wall face must reveal")
	behind_x := room.x - 3
	if behind_x >= 0 {
		testing.expect(t, !run.visible[behind_x][py], "tiles behind walls must stay dark")
		testing.expect(t, !run.explored[behind_x][py], "unseen tiles must not enter memory")
	}

	// Memory persists after walking away.
	seen_x, seen_y := px, py
	run.player.pos = {f32(room.x) + f32(room.w) - 0.6, run.player.pos.y}
	run.player.prev_pos = run.player.pos
	ar.sim_tick(&run, {})
	testing.expect(t, run.explored[seen_x][seen_y], "explored memory must persist")
}

@(test)
route_to_stairs_connects :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(11, 0), .Warden)
	defer ar.run_destroy(&run)
	route: [1024][2]i16
	n := ar.route_to_stairs(&run, route[:])
	testing.expectf(t, n > 0, "route must exist on a connected floor")
	if n > 0 {
		testing.expect(t, int(route[0].x) == int(run.player.pos.x) && int(route[0].y) == int(run.player.pos.y), "route starts at the player")
		testing.expect(t, int(route[n - 1].x) == run.dungeon.stairs.x && int(route[n - 1].y) == run.dungeon.stairs.y, "route ends at the stairs")
	}
}

@(test)
populated_actor_ids_are_stable_and_namespaced_inputs :: proc(t:^testing.T) {
	run: ar.Run
	ar.run_start(&run,ar.derive_seed(707,0),.Acolyte)
	defer ar.run_destroy(&run)
	seen:[256]bool
	for &enemy in run.enemies {
		testing.expect(t,enemy.entity_id>0,"population must assign enemy IDs before rendering")
		if enemy.entity_id<len(seen) {
			testing.expect(t,!seen[enemy.entity_id],"enemy IDs must be unique within a run")
			seen[enemy.entity_id]=true
		}
	}
	run.player.mana=f32(run.player.max_mana)
	run.player.class_skill_timer=0
	if ar.player_cast_spirit_call(&run) {
		for &familiar in run.familiars do testing.expect(t,familiar.entity_id>0,"summoned familiar needs stable presentation identity")
	}
}

@(test)
enemy_roster_complete :: proc(t: ^testing.T) {
	for kind in ar.Enemy_Kind {
		def := ar.ENEMY_DEFS[kind]
		testing.expectf(t, def.name != "" && def.sprite != "", "%v missing name/sprite", kind)
		testing.expectf(t, def.max_hp > 0 && def.speed > 0 && def.weight > 0, "%v zeroed stats", kind)
	}
	testing.expect(t, ar.ENEMY_DEFS[.Gate_Warden].final_room_only, "Gate Warden guards only the final room")
	for id in ar.Boss_Id {
		def := ar.BOSS_DEFS[id]
		testing.expectf(t, def.name != "" && def.sprite != "" && def.ability_count > 0, "%v incomplete", id)
	}
}

@(test)
elite_and_miniboss_math :: proc(t: ^testing.T) {
	base := ar.enemy_make(.Ghoul, {10, 10}, 1) // 42 hp, 10 dmg, 20 xp
	elite := base
	ar.apply_elite(&elite, 0) // Frenzied: x1.45 hp, +3 dmg, x1.18 speed, +12 xp
	testing.expectf(t, elite.max_hp == 60, "Frenzied hp %v, want 60", elite.max_hp)
	testing.expect(t, elite.damage == 13 && elite.xp == 32, "Frenzied damage/xp off")
	testing.expect(t, abs(elite.speed - 1.56 * 1.18) < 1e-4, "Frenzied speed off")
	testing.expect(t, elite.role == .Elite, "role must be Elite")

	rng := ar.rng_make(7)
	mini := ar.make_miniboss(&rng, {10, 10}, 1)
	testing.expect(t, mini.role == .Miniboss, "role must be Miniboss")
	testing.expect(t, mini.max_hp > ar.ENEMY_DEFS[mini.kind].max_hp, "miniboss must be tougher")
}

@(test)
final_boss_post_scaling_matches_pygame :: proc(t: ^testing.T) {
	enemy := ar.Enemy{
		max_hp=101,hp=101,damage=7,attack_cd_s=.7,
		attack_range=1.45,aggro_range=23,speed=.94,
	}
	ar.apply_final_boss_scaling(&enemy)
	testing.expect(t, enemy.max_hp == 242 && enemy.hp == 242)
	testing.expect(t, enemy.damage == 16)
	testing.expect(t, abs(enemy.attack_cd_s - ar.FINAL_BOSS_COOLDOWN_MIN) < 1e-5)
	testing.expect(t, abs(enemy.attack_range - 1.9) < 1e-5)
	testing.expect(t, abs(enemy.aggro_range - 16) < 1e-5)
	testing.expect(t, abs(enemy.speed - 1.15) < 1e-5)
}

@(test)
boss_floors_spawn_guardians :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(11, 0), .Warden)
	defer ar.run_destroy(&run)
	for run.depth < 3 do ar.run_descend(&run)

	boss_count := 0
	for &enemy in run.enemies {
		if enemy.role != .Boss do continue
		boss_count += 1
		testing.expect(t, enemy.big, "floor boss must be 2x2")
		testing.expect(t, !enemy.final_boss, "depth 3 must not spawn the Tyrant")
		testing.expect(t, enemy.ability_count > 0, "boss must carry abilities")
		def := ar.BOSS_DEFS[enemy.boss_id]
		themed := def.themes[0] == run.theme_index || def.themes[1] == run.theme_index
		_ = themed // themed when possible; fallback is any non-final boss
	}
	testing.expectf(t, boss_count == 1, "depth 3 must have exactly one boss, got %v", boss_count)

	for run.depth < 10 do ar.run_descend(&run)
	tyrant_found := false
	for &enemy in run.enemies {
		if enemy.role == .Boss && enemy.final_boss {
			tyrant_found = true
			testing.expect(t, enemy.name == ar.TYRANT_TITLES[run.theme_index], "Tyrant must take the theme title")
		}
	}
	testing.expect(t, tyrant_found, "depth 10 must spawn the Gate Tyrant")
}

mx1_prepare_boss_entry_seam :: proc(run: ^ar.Run) -> (arena: ar.Room, seam: ar.Vec2) {
	ar.run_start(run, ar.derive_seed(1101, 0), .Warden)
	clear(&run.enemies)
	clear(&run.sealed)
	run.boss_engaged = false
	run.dungeon = {}

	arena = {10, 10, 12, 12}
	run.dungeon.rooms_buf[0] = arena
	run.dungeon.room_count = 1
	run.dungeon.boss_arena = true
	for x in arena.x ..< arena.x + arena.w {
		for y in arena.y ..< arena.y + arena.h do run.dungeon.tiles[x][y] = .Floor
	}
	run.dungeon.stairs = {16, 16}
	run.dungeon.tiles[16][16] = .Stairs

	// Two tiles of the west entrance reproduce the generated corridor seam.
	for x in 8 ..< arena.x {
		run.dungeon.tiles[x][arena.y + 5] = .Floor
		run.dungeon.tiles[x][arena.y + 6] = .Floor
	}
	run.dungeon.tiles[arena.x][arena.y + 6] = .Open_Door
	// Exercise exact restoration of every sealable source kind as well.
	run.dungeon.tiles[arena.x + 5][arena.y] = .Closed_Door
	run.dungeon.tiles[arena.x + arena.w - 1][arena.y + 6] = .Open_Door
	for x in arena.x + arena.w ..= arena.x + arena.w + 1 {
		run.dungeon.tiles[x][arena.y + 6] = .Floor
	}

	seam = {f32(arena.x) + 0.5, f32(arena.y) + 6.0}
	run.player.pos = seam
	run.player.prev_pos = seam
	boss := ar.enemy_make(.Ghoul, seam, 3)
	boss.role = .Boss
	boss.big = true
	boss.hp, boss.max_hp = 1000, 1000
	boss.xp = 0
	boss.statuses[.Stunned] = 10
	append(&run.enemies, boss)
	return
}

@(test)
boss_entry_seal_rescues_actors_and_restores_exact_exits :: proc(t: ^testing.T) {
	run: ar.Run
	arena, seam := mx1_prepare_boss_entry_seam(&run)
	defer ar.run_destroy(&run)

	ar.sim_tick(&run, {})
	testing.expect(t, run.boss_engaged, "entry seam must engage the arena")
	testing.expectf(t, len(run.sealed) == 4, "expected four exact openings, got %v", len(run.sealed))
	testing.expect(t, run.player.pos != seam, "player must be rescued from the newly sealed entry")
	testing.expect(t, run.enemies[0].pos != seam, "boss must be rescued from the newly sealed entry")
	testing.expect(
		t,
		!ar.blocked_for_radius(&run.dungeon, run.player.pos.x, run.player.pos.y, block_stairs = true),
		"player footprint overlaps sealed geometry after engagement",
	)
	testing.expect(
		t,
		!ar.blocked_for_radius(&run.dungeon, run.enemies[0].pos.x, run.enemies[0].pos.y, ar.BOSS_MOVE_RADIUS),
		"boss footprint overlaps sealed geometry after engagement",
	)
	gap := run.player.pos - run.enemies[0].pos
	minimum_gap := f32(0.42) + ar.BOSS_HIT_RADIUS + 0.12
	testing.expect(
		t,
		gap.x * gap.x + gap.y * gap.y >= minimum_gap * minimum_gap,
		"seal rescue must not stack the player and boss",
	)

	saw_floor, saw_open_entry, saw_closed, saw_open_exit := false, false, false, false
	for s in run.sealed {
		x, y := int(s.x), int(s.y)
		testing.expect(t, run.dungeon.tiles[x][y] == .Closed_Door, "every ledger entry must be sealed")
		if x == arena.x && y == arena.y + 5 {
			saw_floor = s.tile == .Floor
		} else if x == arena.x && y == arena.y + 6 {
			saw_open_entry = s.tile == .Open_Door
		} else if x == arena.x + 5 && y == arena.y {
			saw_closed = s.tile == .Closed_Door
		} else if x == arena.x + arena.w - 1 && y == arena.y + 6 {
			saw_open_exit = s.tile == .Open_Door
		} else {
			testing.expectf(t, false, "unexpected sealed tile %v,%v", x, y)
		}
	}
	testing.expect(t, saw_floor && saw_open_entry && saw_closed && saw_open_exit, "seal ledger lost an original exit kind")

	// Pygame's watchdog also rescues a wide boss shoved back onto the seal.
	sealed_x, sealed_y := int(run.sealed[0].x), int(run.sealed[0].y)
	run.enemies[0].pos = {f32(sealed_x) + 0.5, f32(sealed_y) + 0.5}
	run.enemies[0].prev_pos = run.enemies[0].pos
	ar.sim_tick(&run, {})
	testing.expect(
		t,
		!ar.blocked_for_radius(&run.dungeon, run.enemies[0].pos.x, run.enemies[0].pos.y, ar.BOSS_MOVE_RADIUS),
		"engaged boss must recover from sealed geometry on the next tick",
	)

	run.enemies[0].hp = 0
	ar.sim_tick(&run, {})
	testing.expect(t, !run.boss_engaged && len(run.sealed) == 0, "boss death must clear the seal ledger")
	testing.expect(t, run.dungeon.tiles[arena.x][arena.y + 5] == .Floor, "floor entrance did not restore")
	testing.expect(t, run.dungeon.tiles[arena.x][arena.y + 6] == .Open_Door, "open entry did not restore")
	testing.expect(t, run.dungeon.tiles[arena.x + 5][arena.y] == .Closed_Door, "pre-closed exit did not restore")
	testing.expect(t, run.dungeon.tiles[arena.x + arena.w - 1][arena.y + 6] == .Open_Door, "open exit did not restore")
}

@(test)
boss_rescue_avoids_ordinary_arena_enemies :: proc(t: ^testing.T) {
	run: ar.Run
	_, _ = mx1_prepare_boss_entry_seam(&run)
	defer ar.run_destroy(&run)

	occupied := [2]ar.Vec2{{11.5, 15.5}, {11.5, 17.5}}
	for position in occupied {
		enemy := ar.enemy_make(.Ghoul, position, 3)
		enemy.aggro_range = 0
		enemy.statuses[.Stunned] = 10
		append(&run.enemies, enemy)
	}

	ar.sim_tick(&run, {})
	testing.expect(t, run.boss_engaged, "occupied arena must still engage when safe rescue anchors remain")
	for position, offset in occupied {
		ordinary := &run.enemies[offset + 1]
		testing.expect(t, ordinary.pos == position, "rescue must not shove a stationary ordinary arena enemy")
		boss_gap := run.enemies[0].pos - ordinary.pos
		boss_minimum := ar.BOSS_HIT_RADIUS + ar.ENEMY_HIT_RADIUS + ar.BOSS_ARENA_CLEARANCE_PAD
		testing.expect(
			t,
			boss_gap.x * boss_gap.x + boss_gap.y * boss_gap.y >= boss_minimum * boss_minimum,
			"boss rescue must avoid every living arena enemy",
		)
		player_gap := run.player.pos - ordinary.pos
		player_minimum := ar.PLAYER_HIT_RADIUS + ar.ENEMY_HIT_RADIUS + ar.BOSS_ARENA_CLEARANCE_PAD
		testing.expect(
			t,
			player_gap.x * player_gap.x + player_gap.y * player_gap.y >= player_minimum * player_minimum,
			"player rescue must avoid every living arena enemy",
		)
	}
}

@(test)
boss_entry_seal_rolls_back_when_rescue_is_impossible :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(1102, 0), .Warden)
	defer ar.run_destroy(&run)
	clear(&run.enemies)
	clear(&run.sealed)
	run.boss_engaged = false
	run.dungeon = {}

	// A 3x3 room has no interior center that clears the wide boss footprint.
	arena := ar.Room{10, 10, 3, 3}
	run.dungeon.rooms_buf[0] = arena
	run.dungeon.room_count = 1
	for x in arena.x ..< arena.x + arena.w {
		for y in arena.y ..< arena.y + arena.h do run.dungeon.tiles[x][y] = .Floor
	}
	run.dungeon.tiles[9][11] = .Floor
	entry := ar.Vec2{10.5, 11.5}
	run.player.pos, run.player.prev_pos = entry, entry
	boss := ar.enemy_make(.Ghoul, entry, 3)
	boss.role = .Boss
	boss.big = true
	boss.hp, boss.max_hp = 1000, 1000
	boss.statuses[.Stunned] = 10
	append(&run.enemies, boss)

	ar.sim_tick(&run, {})
	testing.expect(t, !run.boss_engaged, "impossible actor rescue must abort engagement")
	testing.expect(t, len(run.sealed) == 0, "aborted engagement must not retain a partial seal")
	testing.expect(t, run.dungeon.tiles[10][11] == .Floor, "aborted engagement must restore the entry")
	testing.expect(t, run.player.pos == entry && run.enemies[0].pos == entry, "rollback must restore actor positions")
}

@(test)
pre_engagement_boss_is_confined_to_authoritative_final_arena :: proc(t: ^testing.T) {
	run: ar.Run
	arena, _ := mx1_prepare_boss_entry_seam(&run)
	defer ar.run_destroy(&run)

	decoy := ar.Room{30, 30, 7, 7}
	for x in decoy.x ..< decoy.x + decoy.w {
		for y in decoy.y ..< decoy.y + decoy.h do run.dungeon.tiles[x][y] = .Floor
	}
	run.dungeon.rooms_buf[0] = decoy
	run.dungeon.rooms_buf[1] = arena
	run.dungeon.room_count = 2

	outside := ar.Vec2{33.5, 33.5}
	run.player.pos, run.player.prev_pos = outside, outside
	run.enemies[0].pos, run.enemies[0].prev_pos = outside + ar.Vec2{1, 0}, outside + ar.Vec2{1, 0}
	run.enemies[0].ai = .Chase
	run.enemies[0].aggro_range = 100
	run.enemies[0].statuses[.Stunned] = 0

	ar.sim_tick(&run, {})
	testing.expect(t, ar.room_contains_point(arena, run.enemies[0].pos.x, run.enemies[0].pos.y), "pulled boss must recover into the final arena before AI")
	testing.expect(t, !run.boss_engaged && len(run.sealed) == 0, "player outside the real arena must not trigger a decoy seal")
	waiting := run.enemies[0].pos
	tarena_left := f32(arena.x + 1)
	tarena_right := f32(arena.x + arena.w - 1)
	tarena_top := f32(arena.y + 1)
	tarena_bottom := f32(arena.y + arena.h - 1)
	testing.expect(
		t,
		waiting.x-ar.BOSS_MOVE_RADIUS >= tarena_left && waiting.x+ar.BOSS_MOVE_RADIUS <= tarena_right &&
			waiting.y-ar.BOSS_MOVE_RADIUS >= tarena_top && waiting.y+ar.BOSS_MOVE_RADIUS <= tarena_bottom,
		"authoritative recovery must keep the complete boss footprint off the arena perimeter",
	)
	ar.sim_tick(&run, {})
	testing.expect(t, run.enemies[0].pos == waiting && run.enemies[0].ai == .Idle, "unengaged boss must wait instead of chasing out of the arena")

	// A center on an open perimeter tile is technically in the room, but the
	// wide footprint straddles its threshold and must be recovered before AI.
	threshold := ar.Vec2{f32(arena.x)+0.5, f32(arena.y)+5.5}
	run.enemies[0].pos, run.enemies[0].prev_pos = threshold, threshold
	ar.sim_tick(&run, {})
	waiting = run.enemies[0].pos
	testing.expect(
		t,
		waiting.x-ar.BOSS_MOVE_RADIUS >= tarena_left && waiting.x+ar.BOSS_MOVE_RADIUS <= tarena_right &&
			waiting.y-ar.BOSS_MOVE_RADIUS >= tarena_top && waiting.y+ar.BOSS_MOVE_RADIUS <= tarena_bottom,
		"boss centered on an open threshold must recover its full footprint into the arena",
	)

	run.player.pos = {f32(arena.x) + 2.5, f32(arena.y) + 2.5}
	run.player.prev_pos = run.player.pos
	ar.sim_tick(&run, {})
	testing.expect(t, run.boss_engaged && len(run.sealed) > 0, "entering the final arena must engage and seal it")
	for sealed in run.sealed {
		x, y := int(sealed.x), int(sealed.y)
		on_arena_edge := x == arena.x || x == arena.x + arena.w - 1 ||
			y == arena.y || y == arena.y + arena.h - 1
		testing.expect(t, on_arena_edge, "authoritative seal must use the final room perimeter")
		testing.expect(t, !ar.room_contains_point(decoy, f32(x), f32(y)), "decoy room must remain unsealed")
	}

	// Once sealed, a collision-valid position near a non-door edge remains legal;
	// the watchdog must not apply the stricter pre-engagement waiting inset.
	edge_position := ar.Vec2{f32(arena.x)+8.5, f32(arena.y)+0.9}
	run.enemies[0].pos, run.enemies[0].prev_pos = edge_position, edge_position
	run.enemies[0].statuses[.Stunned] = 10
	run.enemies[0].knockback_vel = {}
	run.player.pos, run.player.prev_pos = ar.Vec2{f32(arena.x)+2.5, f32(arena.y)+8.5}, ar.Vec2{f32(arena.x)+2.5, f32(arena.y)+8.5}
	testing.expect(
		t,
		!ar.blocked_for_radius(&run.dungeon, edge_position.x, edge_position.y, ar.BOSS_MOVE_RADIUS),
		"test setup requires a collision-valid non-door edge position",
	)
	ar.sim_tick(&run, {})
	testing.expect(t, run.enemies[0].pos == edge_position, "engaged watchdog must not snap a boss away from a valid non-door edge")
}

@(test)
boss_seal_gating_and_victory :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(11, 0), .Warden)
	defer ar.run_destroy(&run)
	for run.depth < 3 do ar.run_descend(&run)

	// March the player into the arena: the seal must close and lock.
	arena := ar.dungeon_rooms(&run.dungeon)[run.dungeon.room_count - 1]
	run.player.pos = {f32(arena.x) + 1.5, f32(arena.y) + 1.5}
	run.player.prev_pos = run.player.pos
	boss_pos := ar.Vec2{}
	for &enemy in run.enemies do if enemy.role == .Boss do boss_pos = enemy.pos
	clear(&run.sfx)
	ar.sim_tick(&run, {})
	testing.expect(t, run.boss_engaged, "entering the arena must engage the boss")
	has_boss_engage_cue:=false
	has_gate_close_cue:=false
	for cue in run.sfx {
		if cue.bank==.Boss_Engage {
			has_boss_engage_cue=!cue.spatial
		}
		if cue.bank==.Boss_Gate_Close {
			has_gate_close_cue=cue.spatial&&cue.pos==boss_pos
		}
	}
	testing.expect(t,has_boss_engage_cue,"arena engagement must emit non-spatial Boss_Engage")
	testing.expect(t,has_gate_close_cue,"arena engagement must emit spatial Boss_Gate_Close at the boss")
	testing.expect(t, len(run.sealed) > 0, "the seal must close at least one opening")
	for s in run.sealed {
		testing.expect(t, run.dungeon.tiles[s.x][s.y] == .Closed_Door, "sealed openings become locked doors")
	}

	// Stairs refuse while the guardian lives.
	s := run.dungeon.stairs
	run.player.pos = {f32(s.x) + 0.5, f32(s.y) + 1.5}
	depth_before := run.depth
	_ = ar.player_interact(&run)
	testing.expect(t, run.depth == depth_before, "stairs must refuse while the guardian lives")

	// Kill the boss: seal restores, stairs open.
	for &enemy in run.enemies {
		if enemy.role == .Boss {
			boss_pos = enemy.pos
			enemy.hp = 0
		}
	}
	clear(&run.sfx)
	ar.sim_tick(&run, {})
	testing.expect(t, !run.boss_engaged, "boss death must break the seal")
	has_boss_death_cue:=false
	has_gate_open_cue:=false
	for cue in run.sfx {
		if cue.bank==.Boss_Defeat {
			has_boss_death_cue=!cue.spatial
		}
		if cue.bank==.Boss_Gate_Open {
			has_gate_open_cue=cue.spatial&&cue.pos==boss_pos
		}
	}
	testing.expect(t,has_boss_death_cue,"boss death must emit non-spatial Boss_Defeat")
	testing.expect(t,has_gate_open_cue,"boss death must emit spatial Boss_Gate_Open at the boss")
	testing.expect(t, len(run.sealed) == 0, "sealed list must clear")
	testing.expect(t, ar.player_interact(&run), "stairs must open after the kill")
	testing.expect(t, run.depth == depth_before + 1, "descend must proceed")

	// Depth 10: killing the Tyrant and taking the stairs opens the authored
	// epilogue. Victory belongs exclusively to the final bell panel.
	for run.depth < 10 do ar.run_descend(&run)
	for &enemy in run.enemies {
		if enemy.role == .Boss do enemy.hp = 0
	}
	ar.sim_tick(&run, {})
	testing.expect(t, run.tyrant_dead, "the Tyrant's death must be recorded")
	s10 := run.dungeon.stairs
	run.player.pos = {f32(s10.x) + 0.5, f32(s10.y) + 1.5}
	run.player.prev_pos = run.player.pos
	clear(&run.sfx)
	_ = ar.player_interact(&run)
	testing.expect(t, run.story_runtime.requests.epilogue, "stairs after the Tyrant must request the epilogue")
	testing.expect(t, !run.victory, "final stairs must not bypass the authored epilogue")
	for cue in run.sfx do testing.expect(t, cue.bank != .Victory, "final stairs emitted Victory before the bell")

	testing.expect(t, ar.story_record_gate_choice(&run.story, .Aid), "the Gate choice must resolve before the bell")
	run.story_runtime.epilogue_stage = .Bell
	testing.expect(t, ar.story_complete_bell_victory(&run), "ringing the final bell must claim victory")
	has_victory_cue:=false
	for cue in run.sfx do if cue.bank==.Victory do has_victory_cue=!cue.spatial
	testing.expect(t,has_victory_cue,"the final bell must emit non-spatial Victory")
}

@(test)
new_runs_advance_seed_after_every_terminal_outcome :: proc(t: ^testing.T) {
	app: ar.App
	ar.app_init(&app, 0x5EED)
	defer ar.run_destroy(&app.run)

	outcomes := [3]ar.Run_Terminal_State{.Death, .Victory, .Abandoned}
	seeds: [4]u64
	for outcome, i in outcomes {
		ar.app_begin_new_run(&app, .Warden)
		seeds[i] = app.run.seed
		testing.expect(t, app.seed != app.run.seed, "starting a run must prepare a different seed for the next run")
		app.run.terminal = outcome
	}
	ar.app_begin_new_run(&app, .Warden)
	seeds[3] = app.run.seed

	for seed, i in seeds {
		for previous in 0 ..< i {
			testing.expectf(t, seed != seeds[previous], "run %v reused seed %v from run %v", i + 1, seed, previous + 1)
		}
	}
}

@(test)
player_death_enters_dead_mode :: proc(t: ^testing.T) {
	app: ar.App
	ar.app_init(&app, ar.derive_seed(11, 0))
	defer ar.run_destroy(&app.run)
	ar.app_apply(&app, ar.Intent{confirm = true}) // Title -> Select
	ar.app_apply(&app, ar.Intent{confirm = true}) // Warden, into Playing
	testing.expect(t, app.mode == .Playing, "confirm must start a run")
	// Normal death behavior begins only after the mandatory depth-one omen has
	// been read and committed; otherwise the story modal correctly owns input.
	ar.app_story_panel_reveal(&app)
	ar.app_apply(&app, ar.Intent{confirm = true})
	testing.expect(t, !app.story_panel.active, "death fixture must dismiss the mandatory opening omen")
	clear(&app.run.enemies)
	app.mobile_utility_open = true
	app.run.player.hp = 1
	ar.damage_player(&app.run, 50)
	ar.app_tick(&app)
	testing.expect(t, app.mode == .Playing && app.death_pending, "death must begin its authored presentation")
	testing.expect(t,!app.mobile_utility_open,"death must dismiss the transient mobile utility drawer")
	testing.expect(t, app.run.player.hit_flash == 0, "death presentation must clear the lethal-hit flash")
	death_cues:=0
	for cue in app.run.sfx do if cue.bank==.Player_Death {
		death_cues+=1
		testing.expect(t,!cue.spatial,"Player_Death must be non-spatial")
	}
	testing.expect(t,death_cues==1,"death must emit exactly one Player_Death cue")
	death_ticks := int(ar.PLAYER_DEATH_OVERLAY_DELAY/ar.SIM_DT)+2
	for _ in 0..<death_ticks do ar.app_tick(&app)
	testing.expect(t, app.mode == .Dead, "death summary must follow the die/dead presentation")
	death_cues=0
	for cue in app.run.sfx do if cue.bank==.Player_Death do death_cues+=1
	testing.expect(t,death_cues==1,"death presentation must not repeat its Player_Death cue")
	ar.app_apply(&app, ar.Intent{back = true})
	testing.expect(t, app.mode == .Title, "R/back/click from Dead must return to the title shell")
}

@(test)
interact_descends_on_stairs :: proc(t: ^testing.T) {
	run: ar.Run
	ar.run_start(&run, ar.derive_seed(11, 0), .Warden)
	defer ar.run_destroy(&run)

	// Standing far from the stairs, E does nothing.
	testing.expect(t, !ar.player_interact(&run), "interact away from stairs must not descend")
	testing.expect(t, run.depth == 1, "depth changed unexpectedly")

	// Park the player just outside the stair footprint and interact.
	s := run.dungeon.stairs
	candidates := [4]ar.Vec2{
		{f32(s.x) + 0.5, f32(s.y) + 1.5},
		{f32(s.x) + 0.5, f32(s.y) - 0.5},
		{f32(s.x) + 1.5, f32(s.y) + 0.5},
		{f32(s.x) - 0.5, f32(s.y) + 0.5},
	}
	placed := false
	for c in candidates {
		if !ar.blocked_for_radius(&run.dungeon, c.x, c.y, block_stairs = true) {
			run.player.pos = c
			placed = true
			break
		}
	}
	testing.expect(t, placed, "no open tile next to the stairs")
	testing.expect(t, ar.player_interact(&run), "interact next to stairs must descend")
	testing.expect(t, run.depth == 2, "depth should be 2 after descending")
	p := run.player.pos
	testing.expect(
		t,
		!ar.blocked_for_radius(&run.dungeon, p.x, p.y, block_stairs = true),
		"player must respawn on open floor after descending",
	)
}

@(test)
interact_opens_doors :: proc(t: ^testing.T) {
	// Find a seed whose first floor has a sealed room, then open one door.
	for seed_i in 1 ..= 60 {
		run: ar.Run
		ar.run_start(&run, ar.derive_seed(u64(seed_i), 0), .Warden)
		defer ar.run_destroy(&run)
		d := &run.dungeon
		for x in 0 ..< ar.MAP_W {
			for y in 0 ..< ar.MAP_H {
				if d.tiles[x][y] != .Closed_Door do continue
				// Stand on the walkable side of the door.
				neighbors := [4]ar.Vec2{
					{f32(x) - 0.5, f32(y) + 0.5},
					{f32(x) + 1.5, f32(y) + 0.5},
					{f32(x) + 0.5, f32(y) - 0.5},
					{f32(x) + 0.5, f32(y) + 1.5},
				}
				for n in neighbors {
					if ar.is_walkable(d, n.x, n.y) {
						run.player.pos = n
						run.player.prev_pos = n
						ar.sim_tick(&run, {})
						testing.expect(t, run.visible[x][y], "an adjacent closed door must be visible before it opens")
						testing.expect(t, run.explored[x][y], "a revealed closed door must persist in light-floor fog memory")
						testing.expect(t, ar.interact_prompt(&run) == "E: open door", "door prompt expected")
						testing.expect(t, !ar.player_interact(&run), "opening a door is not a floor change")
						testing.expectf(t, d.tiles[x][y] == .Open_Door, "door at %v,%v did not open", x, y)
						return
					}
				}
			}
		}
	}
	testing.expect(t, false, "no reachable closed door found across 60 seeds")
}

@(test)
door_sprite_face_matches_corridor_axis_and_state :: proc(t: ^testing.T) {
	// X-axis wall runs expose the left face; Y-axis runs expose the right.
	// This is easy to reverse in isometric space, which makes the adjacent wall
	// cover the panel and leaves an apparently missing/plain-wall door.
	testing.expect(t, ar.door_world_key(.Closed_Door,true,false) == .Door_Closed_L, "x-flanked closed door must use its left-face art")
	testing.expect(t, ar.door_world_key(.Open_Door,true,false) == .Door_Open_L, "x-flanked open door must use its left-face art")
	testing.expect(t, ar.door_world_key(.Closed_Door,false,true) == .Door_Closed_R, "y-flanked closed door must use its right-face art")
	testing.expect(t, ar.door_world_key(.Open_Door,false,true) == .Door_Open_R, "y-flanked open door must use its right-face art")
	// Corners/isolated seals follow pygame's deterministic left-face fallback.
	testing.expect(t, ar.door_world_key(.Closed_Door,true,true) == .Door_Closed_L, "ambiguous door face must use the left fallback")
}

@(private = "file")
actor_test_u32_be :: proc(data: []u8, offset: int) -> u32 {
	return u32(data[offset]) << 24 |
		u32(data[offset + 1]) << 16 |
		u32(data[offset + 2]) << 8 |
		u32(data[offset + 3])
}

@(private = "file")
actor_test_png_size :: proc(data: []u8) -> ([2]int, bool) {
	valid := len(data) >= 24 &&
		data[0] == 0x89 && data[1] == 'P' && data[2] == 'N' && data[3] == 'G' &&
		data[12] == 'I' && data[13] == 'H' && data[14] == 'D' && data[15] == 'R'
	if !valid do return {}, false
	return {int(actor_test_u32_be(data,16)),int(actor_test_u32_be(data,20))},true
}

@(test)
baked_manifest_is_valid :: proc(t: ^testing.T) {
	data, read_err := os.read_entire_file_from_path("assets/actors/manifest.json", context.allocator)
	if read_err != nil {
		testing.expect(t, false, "committed canonical assets/actors/manifest.json is missing")
		return
	}
	defer delete(data)
	value, err := json.parse(data)
	testing.expect(t, err == nil, "manifest does not parse")
	defer json.destroy_value(value)
	root := value.(json.Object)
	testing.expect(t,int(root["format"].(json.Float))==2,"actor pack format must enforce native cells")
	testing.expect(t,root["native_cells"].(json.Boolean),"actor pack must prohibit import resampling")
	actors := root["actors"].(json.Object)
	for name,entry in actors {
		obj:=entry.(json.Object)
		cell_value,has_cell:=obj["cell"]
		testing.expectf(t,has_cell,"%v must declare its native PixelLab cell",name)
		if !has_cell do continue
		cell:=int(cell_value.(json.Float))
		source_canvas:=obj["source_canvas"].(json.Array)
		testing.expectf(t,len(source_canvas)==2,"%v source canvas must be square",name)
		if len(source_canvas)!=2 do continue
		testing.expectf(t,int(source_canvas[0].(json.Float))==cell&&int(source_canvas[1].(json.Float))==cell,"%v was resampled during import",name)
		clips:=obj["clips"].(json.Object)
		for clip_name,clip_value in clips {
			clip:=clip_value.(json.Object)
			frames:=int(clip["frames"].(json.Float))
			rows:=int(clip["rows"].(json.Float))
			expected_rows:=clip_name=="preview_idle"?1:8
			testing.expectf(t,rows==expected_rows,"%v/%v rows %v, want %v",name,clip_name,rows,expected_rows)
			sha,has_sha:=clip["sha256"]
			expected_sha:=has_sha?string(sha.(json.String)):""
			testing.expectf(t,len(expected_sha)==64,"%v/%v lacks a sheet hash",name,clip_name)
			path:=fmt.aprintf("assets/actors/%s/%s.png",name,clip_name)
			png,png_err:=os.read_entire_file_from_path(path,context.allocator)
			testing.expectf(t,png_err==nil,"%v/%v native sheet is missing",name,clip_name)
			if png_err==nil {
				size,png_ok:=actor_test_png_size(png)
				testing.expectf(t,png_ok&&size==[2]int{frames*cell,rows*cell},"%v/%v dimensions %v do not preserve %vpx cells",name,clip_name,size,cell)
				digest:=hash.hash_bytes(.SHA256,png,context.allocator)
				encoded,encode_err:=hex.encode(digest,context.allocator)
				testing.expectf(t,encode_err==.None&&string(encoded)==expected_sha,"%v/%v sheet hash changed",name,clip_name)
				delete(encoded)
				delete(digest)
				delete(png)
			}
			delete(path)
		}
	}
	for id in ar.Archetype_Id {
		def := ar.ARCHETYPES[id]
		entry, found := actors[def.sprite]
		testing.expectf(t, found, "actor %v missing from bake", def.sprite)
		if !found do continue
		obj := entry.(json.Object)
		player_cell_value, has_player_cell := obj["cell"]
		testing.expectf(t, has_player_cell, "%v must declare its high-resolution cell", def.sprite)
		player_cell := has_player_cell ? int(player_cell_value.(json.Float)) : 0
		testing.expectf(t, player_cell == 256, "%v cell is %v, want original 256px", def.sprite, player_cell)
		testing.expectf(t, obj["canvas_world"].(json.Float) > 0, "%v canvas_world", def.sprite)
		clips := obj["clips"].(json.Object)
		preview_value, has_preview := clips["preview_idle"]
		testing.expectf(t,has_preview,"%v missing compact high-resolution carousel preview",def.sprite)
		if has_preview {
			preview_frames := int(preview_value.(json.Object)["frames"].(json.Float))
			preview_path := fmt.aprintf("assets/actors/%s/preview_idle.png",def.sprite)
			preview_png,preview_err := os.read_entire_file_from_path(preview_path,context.allocator)
			testing.expectf(t,preview_err==nil,"%v preview sheet is missing",def.sprite)
			if preview_err==nil {
				size,png_ok:=actor_test_png_size(preview_png)
				testing.expectf(t,png_ok&&size==[2]int{preview_frames*player_cell,player_cell},"%v compact preview dimensions %v, want %vx%v",def.sprite,size,preview_frames*player_cell,player_cell)
				delete(preview_png)
			}
			delete(preview_path)
		}
		for clip in ([6]string{"idle", "walk", "attack", "cast", "die", "dead"}) {
			clip_value, has := clips[clip]
			testing.expectf(t, has, "%v missing clip %v", def.sprite, clip)
			if !has do continue
			frames := int(clip_value.(json.Object)["frames"].(json.Float))
			testing.expectf(t,frames>0,"%v %v has no frames",def.sprite,clip)
			path:=fmt.aprintf("assets/actors/%s/%s.png",def.sprite,clip)
			png,png_err:=os.read_entire_file_from_path(path,context.allocator)
			testing.expectf(t,png_err==nil&&len(png)>0,"%v references missing PNG %v",def.sprite,path)
			if png_err==nil {
				size,png_ok:=actor_test_png_size(png)
				testing.expectf(t,png_ok,"%v is not a canonical PNG",path)
				if png_ok do testing.expectf(t,size==[2]int{frames*player_cell,8*player_cell},"%v dimensions %v do not match %v frames at %vpx",path,size,frames,player_cell)
				delete(png)
			}
			delete(path)
		}
		if id == .Ranger {
			pet_value, has_pet := clips["pet"]
			testing.expect(t,has_pet,"Ranger missing paired pet animation")
			if has_pet {
				pet_clip:=pet_value.(json.Object)
				pet_frames:=int(pet_clip["frames"].(json.Float))
				testing.expect(t,pet_frames==8&&!pet_clip["loop"].(json.Boolean),"Ranger pet must keep Pygame's eight-frame non-looping pose")
				pet_png,pet_err:=os.read_entire_file_from_path("assets/actors/ranger/pet.png",context.allocator)
				testing.expect(t,pet_err==nil,"Ranger pet sheet is missing")
				if pet_err==nil {
					size,png_ok:=actor_test_png_size(pet_png)
					testing.expectf(t,png_ok&&size==[2]int{pet_frames*player_cell,8*player_cell},"Ranger pet dimensions %v do not match %v frames at %vpx",size,pet_frames,player_cell)
					delete(pet_png)
				}
			}
		}
	}
	familiar_names := [3]string{"familiar_wisp", "familiar_crow", "spirit_beast"}
	for name in familiar_names {
		entry, found := actors[name]
		testing.expectf(t, found, "familiar %v missing from bake", name)
		if !found do continue
		familiar_obj := entry.(json.Object)
		familiar_cell_value, has_familiar_cell := familiar_obj["cell"]
		testing.expectf(t,has_familiar_cell,"%v must declare its native source cell",name)
		if has_familiar_cell {
			familiar_cell:=int(familiar_cell_value.(json.Float))
			source_canvas:=familiar_obj["source_canvas"].(json.Array)
			testing.expectf(t,len(source_canvas)==2&&int(source_canvas[0].(json.Float))==familiar_cell&&int(source_canvas[1].(json.Float))==familiar_cell,"%v familiar import was resampled",name)
		}
		clips := familiar_obj["clips"].(json.Object)
		for clip in ([2]string{"idle", "walk"}) {
			clip_value, has := clips[clip]
			testing.expectf(t, has, "%v missing clip %v", name, clip)
			if has do testing.expectf(t, int(clip_value.(json.Object)["frames"].(json.Float)) == 8, "%v %v must have eight frames", name, clip)
		}
		if name == "spirit_beast" {
			for clip in ([2]string{"attack", "pet"}) {
				clip_value, has := clips[clip]
				testing.expectf(t, has, "spirit_beast missing clip %v", clip)
				if has do testing.expectf(t, int(clip_value.(json.Object)["frames"].(json.Float)) == 8, "spirit_beast %v must have eight frames", clip)
			}
		}
	}
	special_actor_clips := [4]struct{name:string,clips:[]string}{
		{"shopkeeper",[]string{"idle","walk","dance"}},
		{"bar_dancer",[]string{"walk","dance"}},
		{"garden_frog",[]string{"walk","dance"}},
		{"string",[]string{"idle","walk","attack"}},
	}
	for expected in special_actor_clips {
		entry,found:=actors[expected.name]
		testing.expectf(t,found,"M9 special actor %v missing from bake",expected.name)
		if !found do continue
		clips:=entry.(json.Object)["clips"].(json.Object)
		for clip in expected.clips {
			clip_value,has:=clips[clip]
			testing.expectf(t,has,"%v missing clip %v",expected.name,clip)
			if !has do continue
			testing.expectf(t,int(clip_value.(json.Object)["frames"].(json.Float))>0,"%v %v has no frames",expected.name,clip)
			path:=fmt.aprintf("assets/actors/%s/%s.png",expected.name,clip)
			png,png_err:=os.read_entire_file_from_path(path,context.allocator)
			testing.expectf(t,png_err==nil&&len(png)>0,"%v references missing PNG %v",expected.name,path)
			if png_err==nil do delete(png)
			delete(path)
		}
	}
}

@(test)
prop_manifest_is_complete :: proc(t:^testing.T) {
	data,read_err:=os.read_entire_file_from_path("assets/props/manifest.json",context.allocator)
	if read_err!=nil {
		testing.expect(t,false,"committed canonical assets/props/manifest.json is missing")
		return
	}
	defer delete(data)
	value,err:=json.parse(data)
	testing.expect(t,err==nil,"prop manifest does not parse")
	if err!=nil do return
	defer json.destroy_value(value)
	root:=value.(json.Object)
	testing.expect(t,int(root["format"].(json.Float))==1,"prop manifest format changed")
	props:=root["props"].(json.Object)
	testing.expectf(t,len(props)==len(ar.Prop_Key),"prop manifest has %v entries, want %v",len(props),len(ar.Prop_Key))
	for key in ar.Prop_Key {
		name:=ar.PROP_KEY_NAMES[key]
		entry,found:=props[name]
		testing.expectf(t,found,"required prop %v missing",name)
		if !found do continue
		obj:=entry.(json.Object)
		testing.expectf(t,obj["world_height"].(json.Float)>0,"%v has invalid world height",name)
		path:=fmt.aprintf("assets/props/%s",obj["path"].(json.String))
		png,png_err:=os.read_entire_file_from_path(path,context.allocator)
		testing.expectf(t,png_err==nil&&len(png)>0,"%v references missing PNG %v",name,path)
		if png_err==nil do delete(png)
		delete(path)
	}
}

@(test)
collision_and_los_queries :: proc(t: ^testing.T) {
	rng := ar.rng_make(ar.derive_seed(7, 1))
	d, ok := ar.dungeon_generate(&rng)
	testing.expect(t, ok, "generation failed")

	c := ar.room_center(ar.dungeon_rooms(&d)[0])
	cx, cy := f32(c.x) + 0.5, f32(c.y) + 0.5
	testing.expect(t, !ar.blocked_for_radius(&d, cx, cy), "spawn room center should be open")
	testing.expect(t, ar.blocked_for_radius(&d, 0.5, 0.5), "map corner is solid rock")

	sx, sy := f32(d.stairs.x) + 0.5, f32(d.stairs.y) + 0.5
	testing.expect(t, ar.blocked_for_radius(&d, sx, sy, block_stairs = true), "stair shaft must block the player probe")
	testing.expect(t, !ar.blocked_for_radius(&d, sx, sy), "stairs stay open to generic probes (LOS/projectiles)")

	testing.expect(t, ar.line_of_sight(&d, cx, cy, cx, cy), "degenerate LOS should pass")
	testing.expect(t, ar.line_of_sight(&d, cx, cy, cx + 1, cy + 1), "LOS across open room interior")
	testing.expect(t, !ar.line_of_sight(&d, cx, cy, 0.5, 0.5), "LOS through solid rock must fail")
}
