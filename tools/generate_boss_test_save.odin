package main

import "core:fmt"
import "core:os"
import "core:strings"
import ar "../src"

TEST_SEED :: u64(0xB0557E57)
TEST_DEPTH :: 3
TEST_RUN_ID :: "boss-test-depth-3"
TEST_TIMESTAMP :: "2026-08-23T00:00:00Z"

walkable_tile :: proc(tile: ar.Tile_Kind) -> bool {
	return tile != .Wall && tile != .Closed_Door
}

// Find a corridor cell immediately outside the final room. Entering the
// adjacent perimeter cell starts and seals the boss encounter normally.
pre_boss_position :: proc(run: ^ar.Run) -> (ar.Vec2, bool) {
	if run == nil || run.dungeon.room_count < 1 do return {}, false
	room := run.dungeon.rooms_buf[run.dungeon.room_count - 1]

	for x in room.x ..< room.x + room.w {
		candidates := [2][2]int{{x, room.y - 1}, {x, room.y + room.h}}
		for tile in candidates {
			inside_y := tile.y < room.y ? room.y : room.y + room.h - 1
			if walkable_tile(run.dungeon.tiles[tile.x][tile.y]) &&
				walkable_tile(run.dungeon.tiles[tile.x][inside_y]) {
				return {f32(tile.x) + 0.5, f32(tile.y) + 0.5}, true
			}
		}
	}
	for y in room.y ..< room.y + room.h {
		candidates := [2][2]int{{room.x - 1, y}, {room.x + room.w, y}}
		for tile in candidates {
			inside_x := tile.x < room.x ? room.x : room.x + room.w - 1
			if walkable_tile(run.dungeon.tiles[tile.x][tile.y]) &&
				walkable_tile(run.dungeon.tiles[inside_x][tile.y]) {
				return {f32(tile.x) + 0.5, f32(tile.y) + 0.5}, true
			}
		}
	}
	return {}, false
}

main :: proc() {
	app: ar.App
	ar.app_init(&app, TEST_SEED)
	defer ar.run_destroy(&app.run)
	ar.run_start(&app.run, TEST_SEED, .Warden, .Medium)
	for app.run.depth < TEST_DEPTH do ar.run_descend(&app.run)
	ar.player_gain_xp(&app.run, 250) // level 3, approximating two cleared floors
	app.run.player.heal_potions = 3

	position, found := pre_boss_position(&app.run)
	if !found {
		fmt.eprintln("failed to find the boss arena entrance")
		os.exit(1)
	}
	app.run.player.pos = position
	app.run.player.prev_pos = position
	app.run.player.facing = {}
	app.run.boss_engaged = false
	app.run.run_id = strings.clone(TEST_RUN_ID)
	app.run.started_at_utc = strings.clone(TEST_TIMESTAMP)
	app.mode = .Playing
	ar.refresh_visibility(&app.run)

	data, encoded := ar.persistence_encode_run(&app, 1, TEST_TIMESTAMP)
	if !encoded {
		fmt.eprintln("failed to encode the boss test save")
		os.exit(1)
	}
	defer delete(data)

	document, status := ar.persistence_decode_run(data)
	defer ar.run_document_destroy(&document)
	if status != .Valid {
		fmt.eprintln("generated save failed production decode validation")
		os.exit(1)
	}
	arena := document.payload.dungeon.rooms_buf[document.payload.dungeon.room_count - 1]
	inside_arena := arena.x <= int(document.payload.player.pos.x) && int(document.payload.player.pos.x) < arena.x + arena.w &&
		arena.y <= int(document.payload.player.pos.y) && int(document.payload.player.pos.y) < arena.y + arena.h
	alive_bosses := 0
	for enemy in document.payload.enemies do if enemy.role == .Boss && enemy.hp > 0 do alive_bosses += 1
	if inside_arena || document.payload.boss_engaged || alive_bosses != 1 {
		fmt.eprintln("generated save is not in a clean pre-boss state")
		os.exit(1)
	}

	if err := os.make_directory("build/boss-test-save"); err != nil && !os.is_directory("build/boss-test-save") {
		fmt.eprintln("failed to create build/boss-test-save")
		os.exit(1)
	}
	path := "build/boss-test-save/run.json"
	if err := os.write_entire_file(path, data); err != nil {
		fmt.eprintln("failed to write ", path)
		os.exit(1)
	}

	boss_name := "unknown boss"
	for &enemy in app.run.enemies {
		if enemy.role == .Boss {
			boss_name = ar.enemy_display_name(&enemy)
			break
		}
	}
	fmt.println("wrote ", path)
	fmt.printf("depth=%d boss=%s player=(%.1f, %.1f)\n", app.run.depth, boss_name, position.x, position.y)
}
