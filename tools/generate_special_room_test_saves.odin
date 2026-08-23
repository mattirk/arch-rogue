package main

import "core:fmt"
import "core:os"
import "core:strings"
import ar "../src"

TEST_TIMESTAMP :: "2026-08-23T00:00:00Z"
MAX_SEED_ATTEMPTS :: 1024

Save_Scenario :: struct {
	kind:       ar.Special_Room_Kind,
	name:       string,
	seed_start: u64,
	path:       string,
}

walkable_room_position :: proc(run: ^ar.Run, room: ar.Room) -> (ar.Vec2, bool) {
	if run == nil do return {}, false
	for y in room.y + 1 ..< room.y + room.h - 1 {
		for x in room.x + 1 ..< room.x + room.w - 1 {
			#partial switch run.dungeon.tiles[x][y] {
			case .Floor, .Stairs:
			case:
				continue
			}
			if ar.special_room_reserved_occupies_tile(&run.dungeon, x, y) do continue
			occupied := false
			for i in 0 ..< run.ambient_residents.count {
				resident := &run.ambient_residents.items[i]
				if resident.active && int(resident.pos.x) == x && int(resident.pos.y) == y {
					occupied = true
					break
				}
			}
			if !occupied do return {f32(x) + 0.5, f32(y) + 0.5}, true
		}
	}
	return {}, false
}

clear_combat_hazards :: proc(run: ^ar.Run) {
	if run == nil do return
	clear(&run.enemies)
	clear(&run.projectiles)
	clear(&run.familiars)
	clear(&run.bells)
	clear(&run.numbers)
	clear(&run.ground_items)
	clear(&run.traps)
	clear(&run.shrines)
	clear(&run.secrets)
	clear(&run.sfx)
	run.dungeon.solid_props = {}
	run.boss_engaged = false
}

room_gain :: proc(run: ^ar.Run, kind: ar.Special_Room_Kind) -> f32 {
	switch kind {
	case .Bar:    return ar.music_dungeon_bar_gain(run)
	case .Garden: return ar.music_dungeon_garden_gain(run)
	case .None, .Shop, .Quest, .Hall_Of_Unlost_Echoes:
	}
	return 0
}

generate_save :: proc(scenario: Save_Scenario) -> bool {
	for attempt in 0 ..< MAX_SEED_ATTEMPTS {
		seed := scenario.seed_start + u64(attempt)
		app: ar.App
		ar.app_init(&app, seed)
		ar.run_start(&app.run, seed, .Warden, .Medium)

		special, found := ar.special_room_for_kind(&app.run.dungeon, scenario.kind)
		if !found || special.room_index < 0 || special.room_index >= app.run.dungeon.room_count {
			ar.run_destroy(&app.run)
			continue
		}
		room := app.run.dungeon.rooms_buf[special.room_index]
		clear_combat_hazards(&app.run)
		position, positioned := walkable_room_position(&app.run, room)
		if !positioned {
			ar.run_destroy(&app.run)
			continue
		}

		app.run.player.pos = position
		app.run.player.prev_pos = position
		app.run.player.facing = {}
		delete(app.run.run_id)
		delete(app.run.started_at_utc)
		app.run.run_id = strings.clone(fmt.tprintf("%s-test-seed-%d", scenario.name, seed))
		app.run.started_at_utc = strings.clone(TEST_TIMESTAMP)
		app.mode = .Playing
		ar.refresh_visibility(&app.run)

		if room_gain(&app.run, scenario.kind) != 1 {
			fmt.eprintf("%s candidate did not reach full room music gain\n", scenario.name)
			ar.run_destroy(&app.run)
			continue
		}
		if scenario.kind == .Bar && app.run.dungeon.bar_furnishings.count == 0 {
			fmt.eprintln("Bar candidate unexpectedly has no furnishings")
			ar.run_destroy(&app.run)
			continue
		}
		if scenario.kind == .Garden && app.run.ambient_residents.count == 0 {
			fmt.eprintln("Garden candidate unexpectedly has no residents")
			ar.run_destroy(&app.run)
			continue
		}

		data, encoded := ar.persistence_encode_run(&app, 1, TEST_TIMESTAMP)
		if !encoded {
			fmt.eprintf("failed to encode %s test save\n", scenario.name)
			ar.run_destroy(&app.run)
			return false
		}
		document, status := ar.persistence_decode_run(data)
		if status != .Valid {
			fmt.eprintf("generated %s save failed production decode validation\n", scenario.name)
			ar.run_document_destroy(&document)
			delete(data)
			ar.run_destroy(&app.run)
			return false
		}
		loaded: ar.App
		ar.app_init(&loaded, seed)
		installed := ar.app_install_run_document(&loaded, &document)
		decoded_special, decoded_found := ar.special_room_for_kind(&loaded.run.dungeon, scenario.kind)
		decoded_gain := room_gain(&loaded.run, scenario.kind)
		contents_valid := scenario.kind == .Bar ? loaded.run.dungeon.bar_furnishings.count > 0 :
			loaded.run.ambient_residents.count > 0
		valid := installed && decoded_found && decoded_special.room_index == special.room_index &&
			decoded_gain == 1 && contents_valid
		ar.run_document_destroy(&document)
		ar.run_destroy(&loaded.run)
		if !valid {
			fmt.eprintf("generated %s save lost its room or music position after decode\n", scenario.name)
			delete(data)
			ar.run_destroy(&app.run)
			return false
		}

		directory := scenario.path[:strings.last_index(scenario.path, "/")]
		if err := os.make_directory(directory); err != nil && !os.is_directory(directory) {
			fmt.eprintln("failed to create ", directory)
			delete(data)
			ar.run_destroy(&app.run)
			return false
		}
		if err := os.write_entire_file(scenario.path, data); err != nil {
			fmt.eprintln("failed to write ", scenario.path)
			delete(data)
			ar.run_destroy(&app.run)
			return false
		}
		delete(data)

		fmt.println("wrote ", scenario.path)
		fmt.printf("kind=%s seed=%d depth=%d room=%d player=(%.1f, %.1f) gain=%.1f\n",
			scenario.name, seed, app.run.depth, special.room_index, position.x, position.y,
			room_gain(&app.run, scenario.kind))
		ar.run_destroy(&app.run)
		return true
	}
	fmt.eprintf("failed to find a real %s room in %d deterministic seeds\n", scenario.name, MAX_SEED_ATTEMPTS)
	return false
}

main :: proc() {
	scenarios := [2]Save_Scenario{
		{kind = .Bar, name = "bar", seed_start = 0xBAA000, path = "build/bar-test-save/run.json"},
		{kind = .Garden, name = "garden", seed_start = 0x6A2D000, path = "build/garden-test-save/run.json"},
	}
	for scenario in scenarios {
		if !generate_save(scenario) do os.exit(1)
	}
}
