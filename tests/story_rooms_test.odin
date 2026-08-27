package archrogue_tests

// MX-story foundation: deterministic Quest/Hall planning, safe sealed chambers,
// Hall furnishing reservations, and the mandatory undamped Hall mist bank.

import "core:testing"
import ar "../src"

@(private = "file")
story_room_perimeter_doors :: proc(d: ^ar.Dungeon, room: ar.Room) -> (count: int) {
	for x in room.x ..< room.x + room.w {
		if d.tiles[x][room.y] == .Closed_Door do count += 1
		if d.tiles[x][room.y + room.h - 1] == .Closed_Door do count += 1
	}
	for y in room.y + 1 ..< room.y + room.h - 1 {
		if d.tiles[room.x][y] == .Closed_Door do count += 1
		if d.tiles[room.x + room.w - 1][y] == .Closed_Door do count += 1
	}
	return
}

@(private = "file")
story_kind_order :: proc(kind: ar.Special_Room_Kind) -> int {
	if kind == .Shop do return 0
	if kind == .Quest do return 1
	if kind == .Bar do return 2
	if kind == .Garden do return 3
	if kind == .Hall_Of_Unlost_Echoes do return 4
	return -1
}

@(private = "file")
story_generate :: proc(seed: u64, opts := ar.Dungeon_Options{}) -> (d: ar.Dungeon, ok: bool) {
	rng := ar.rng_make(ar.derive_seed(seed, 1))
	return ar.dungeon_generate(&rng, opts)
}

@(test)
story_special_room_art_registry_maps_authored_floors_walls_and_hall_props :: proc(t: ^testing.T) {
	floor_cases := [5]struct{kind: ar.Special_Room_Kind, key: ar.World_Key}{
		{.Shop,.Shop_Floor},
		{.Bar,.Bar_Floor},
		{.Garden,.Garden_Floor},
		{.Quest,.Quest_Floor},
		{.Hall_Of_Unlost_Echoes,.Lossless_Soul_Floor},
	}
	for fixture in floor_cases {
		key, found := ar.special_room_floor_world_key(fixture.kind)
		testing.expectf(t, found && key == fixture.key, "%v floor maps to %v/%v, want %v", fixture.kind, key, found, fixture.key)
		testing.expectf(t, ar.WORLD_KEY_NAMES[key] != "", "%v floor has no baked world key", fixture.kind)
	}
	_, none_floor := ar.special_room_floor_world_key(.None)
	testing.expect(t, !none_floor, "ordinary rooms must retain the base floor")

	wall_cases := [4]struct{kind: ar.Special_Room_Kind, left, right: ar.World_Key}{
		{.Bar,.Bar_Wall_L,.Bar_Wall_R},
		{.Garden,.Garden_Wall_L,.Garden_Wall_R},
		{.Quest,.Quest_Wall_L,.Quest_Wall_R},
		{.Hall_Of_Unlost_Echoes,.Lossless_Soul_Wall_L,.Lossless_Soul_Wall_R},
	}
	for fixture in wall_cases {
		left, left_found := ar.special_room_wall_world_key(fixture.kind,true)
		right, right_found := ar.special_room_wall_world_key(fixture.kind,false)
		testing.expectf(t, left_found && left == fixture.left, "%v left wall mapping changed", fixture.kind)
		testing.expectf(t, right_found && right == fixture.right, "%v right wall mapping changed", fixture.kind)
	}
	_, shop_wall := ar.special_room_wall_world_key(.Shop,true)
	testing.expect(t, !shop_wall, "shop must retain the base dungeon wall")

	testing.expect(t, ar.PROP_KEY_NAMES[.Lossless_Soul_Mirror] == "lossless_room_mirror", "Hall mirror prop key changed")
	testing.expect(t, ar.PROP_KEY_NAMES[.Lossless_Soul_Chimes] == "lossless_room_chimes", "Hall chimes prop key changed")
	testing.expect(t, ar.PROP_KEY_NAMES[.Lossless_Soul_Brazier] == "lossless_room_brazier", "Hall brazier prop key changed")
	testing.expect(t, ar.PROP_KEY_NAMES[.Lossless_Soul_Reliquary] == "lossless_room_reliquary", "Hall reliquary prop key changed")
	testing.expect(t, ar.STORY_RELIC_WORLD_ICON_HEIGHT == 20, "world relic icon scale changed")
}

@(test)
story_rooms_plan_is_deterministic_ordered_distinct_and_legacy_stable :: proc(t: ^testing.T) {
	testing.expect(t, ar.MAX_SPECIAL_ROOMS == 5, "special-room storage must hold all five kinds")

	// These are the pre-MX-story M9 outputs. A same-code comparison would miss a
	// deterministic-but-breaking stream shift, so keep representative fixtures.
	legacy := [12][3]ar.Special_Room{
		{{.Shop, 11}, {}, {}},
		{{.Shop, 6}, {.Bar, 2}, {}},
		{{.Shop, 8}, {.Bar, 11}, {}},
		{{.Shop, 10}, {.Garden, 1}, {}},
		{{.Bar, 8}, {.Garden, 4}, {}},
		{{.Shop, 3}, {}, {}},
		{{.Shop, 8}, {.Bar, 10}, {.Garden, 9}},
		{{.Garden, 6}, {}, {}},
		{{.Shop, 3}, {.Garden, 7}, {}},
		{{.Bar, 3}, {.Garden, 5}, {}},
		{{.Shop, 10}, {.Bar, 4}, {.Garden, 9}},
		{{.Shop, 10}, {.Bar, 1}, {.Garden, 4}},
	}
	legacy_counts := [12]int{1, 2, 2, 2, 2, 1, 3, 1, 2, 2, 3, 3}
	for seed_i in 1 ..= len(legacy) {
		d, ok := story_generate(u64(seed_i))
		testing.expectf(t, ok, "legacy dungeon generation failed for seed %v", seed_i)
		if !ok do continue
		expected_count := legacy_counts[seed_i - 1]
		testing.expectf(t, d.special_room_count == expected_count, "seed %v special count drifted", seed_i)
		for i in 0 ..< expected_count {
			testing.expectf(t, d.special_rooms_buf[i] == legacy[seed_i - 1][i], "seed %v special %v drifted", seed_i, i)
		}
		testing.expect(t, !d.special_room_plan.hall_enabled && !d.special_room_plan.hall_roll_evaluated, "ordinary generation unexpectedly enabled story Hall planning")
	}

	// Seed 7 exercises the full capacity and therefore the complete authored order.
	opts := ar.Dungeon_Options{story_rooms = true, quest_requested = true}
	a, a_ok := story_generate(7, opts)
	b, b_ok := story_generate(7, opts)
	testing.expect(t, a_ok && b_ok && a == b, "story-room floor must replay exactly")
	if !a_ok do return
	testing.expect(t, a.special_room_count == ar.MAX_SPECIAL_ROOMS, "fixture must exercise all five room kinds")
	occupied: [ar.MAX_ROOMS_CAP]bool
	previous_order := -1
	for i in 0 ..< a.special_room_count {
		special := a.special_rooms_buf[i]
		order := story_kind_order(special.kind)
		testing.expectf(t, order > previous_order, "special plan left Shop→Quest→Bar→Garden→Hall order at row %v", i)
		previous_order = order
		testing.expect(t, special.room_index > 0 && special.room_index < a.room_count - 1, "story special used first/final room")
		testing.expect(t, !occupied[special.room_index], "two special kinds claimed one room")
		occupied[special.room_index] = true
		testing.expect(t, story_room_perimeter_doors(&a, a.rooms_buf[special.room_index]) > 0, "special room was not sealed through a real doorway")
	}
	quest, has_quest := ar.special_room_for_kind(&a, .Quest)
	hall, has_hall := ar.special_room_for_kind(&a, .Hall_Of_Unlost_Echoes)
	testing.expect(t, has_quest && has_hall && quest.room_index != hall.room_index, "story floor lost Quest/Hall or overlapped them")
	testing.expect(t, ar.special_room_is_safe(.Quest) && ar.special_room_is_safe(.Hall_Of_Unlost_Echoes), "Quest and Hall must suppress hostile population")
	testing.expect(t, ar.special_room_is_flavor(.Hall_Of_Unlost_Echoes), "Hall must remain flavor-classified")
	testing.expect(t, !ar.special_room_is_healing_refuge(.Hall_Of_Unlost_Echoes), "Hall must not inherit Bar/Garden refuge healing")
	testing.expect(t, ar.special_room_kind_name(.Quest) == "Quest", "Quest kind name changed")
	testing.expect(t, ar.special_room_kind_name(.Hall_Of_Unlost_Echoes) == ar.HALL_OF_UNLOST_ECHOES_NAME, "Hall display name changed")
}

@(test)
story_requested_rooms_never_fall_back_to_spawn_or_boss_rooms :: proc(t: ^testing.T) {
	arena_modes := [2]bool{false, true}
	for seed in 1 ..= 128 {
		for boss_arena in arena_modes {
			d, ok := story_generate(u64(seed), {
				boss_arena = boss_arena,
				story_rooms = true,
				quest_requested = true,
				force_hall = true,
			})
			testing.expectf(t, ok, "requested story rooms failed for seed %v (boss=%v)", seed, boss_arena)
			if !ok do continue
			quest, has_quest := ar.special_room_for_kind(&d, .Quest)
			hall, has_hall := ar.special_room_for_kind(&d, .Hall_Of_Unlost_Echoes)
			testing.expectf(t, has_quest && d.special_room_plan.quest_placed, "seed %v lost mandatory Quest room", seed)
			testing.expectf(t, has_hall && d.special_room_plan.hall_placed, "seed %v lost forced Hall", seed)
			if has_quest do testing.expect(t, quest.room_index > 0 && quest.room_index < d.room_count - 1, "Quest used spawn/final room")
			if has_hall do testing.expect(t, hall.room_index > 0 && hall.room_index < d.room_count - 1, "Hall used spawn/final room")
		}
	}
}

@(test)
story_hall_roll_is_normal_and_force_only_overrides_failure :: proc(t: ^testing.T) {
	evaluated, passed := 0, 0
	for seed in 1 ..= 240 {
		d, ok := story_generate(u64(seed), {story_rooms = true})
		if !ok || !d.special_room_plan.hall_roll_evaluated do continue
		evaluated += 1
		if d.special_room_plan.hall_roll_passed do passed += 1
		_, has_hall := ar.special_room_for_kind(&d, .Hall_Of_Unlost_Echoes)
		testing.expect(t, has_hall == d.special_room_plan.hall_roll_passed, "normal Hall placement disagreed with its 50% roll")
	}
	testing.expectf(t, evaluated >= 220, "too few observable Hall rolls: %v", evaluated)
	testing.expectf(t, passed >= 80 && passed <= 160, "Hall passed %v/%v rolls; expected about 50%%", passed, evaluated)

	// Seed 5 has a failed normal Hall roll. Force must consume and report that
	// same failed roll, preserve every earlier special-room decision, then place.
	normal, normal_ok := story_generate(5, {story_rooms = true, quest_requested = true})
	forced, forced_ok := story_generate(5, {story_rooms = true, quest_requested = true, force_hall = true})
	testing.expect(t, normal_ok && forced_ok, "force-override fixtures must generate")
	if !normal_ok || !forced_ok do return
	testing.expect(t, normal.special_room_plan.hall_roll_evaluated && !normal.special_room_plan.hall_roll_passed, "fixture no longer exercises a failed Hall roll")
	testing.expect(t, forced.special_room_plan.hall_roll_evaluated && !forced.special_room_plan.hall_roll_passed, "force skipped or replaced the normal Hall roll")
	testing.expect(t, forced.special_room_plan.hall_force_requested && forced.special_room_plan.hall_placed, "force did not override the failed roll")
	_, normal_hall := ar.special_room_for_kind(&normal, .Hall_Of_Unlost_Echoes)
	_, forced_hall := ar.special_room_for_kind(&forced, .Hall_Of_Unlost_Echoes)
	testing.expect(t, !normal_hall && forced_hall, "Hall force override did not change only placement")
	testing.expect(t, forced.special_room_count == normal.special_room_count + 1, "force changed more than the missing Hall")
	for i in 0 ..< normal.special_room_count {
		testing.expect(t, forced.special_rooms_buf[i] == normal.special_rooms_buf[i], "force perturbed an earlier Shop/Quest/Bar/Garden decision")
	}
}

@(test)
story_hall_furnishings_are_deterministic_valid_and_solid :: proc(t: ^testing.T) {
	d, ok := story_generate(1, {story_rooms = true, quest_requested = true})
	testing.expect(t, ok, "Hall furnishing fixture must generate")
	if !ok do return
	hall, found := ar.special_room_for_kind(&d, .Hall_Of_Unlost_Echoes)
	testing.expect(t, found, "fixture must contain a Hall")
	if !found do return
	room := d.rooms_buf[hall.room_index]
	original := ar.hall_furnishing_layout(&d)
	testing.expect(t, original.count == ar.MAX_HALL_FURNISHINGS, "Hall must place mirror, chimes, brazier, and reliquary")
	for i in 0 ..< original.count {
		tile := original.tiles[i]
		testing.expect(t, original.kinds[i] == ar.Hall_Furnishing_Kind(i), "Hall furnishing order changed")
		testing.expect(t, ar.room_contains_interior_tile(room, tile.x, tile.y), "Hall furnishing escaped strict interior")
		testing.expect(t, ar.hall_furnishing_avoids_door_front(&d, room, tile), "Hall furnishing pinched a doorway")
		testing.expect(t, ar.hall_furnishing_occupies_tile(&d, tile.x, tile.y), "Hall layout lookup lost a furnishing")
		testing.expect(t, ar.special_room_reserved_occupies_tile(&d, tile.x, tile.y), "Hall furnishing was not added to solid reservation queries")
		testing.expect(t, ar.blocked_for_radius(&d, f32(tile.x) + .5, f32(tile.y) + .5), "Hall furnishing did not block actor movement")
		for j in 0 ..< i do testing.expect(t, original.tiles[j] != tile, "two Hall furnishings claimed one tile")
	}

	// Block the mirror's ideal anchor. It must slide to the deterministic nearest
	// legal tile and a repeated plan must produce the same complete layout.
	mirror_ideal := ar.hall_furnishing_ideal_tile(room, .Mirror)
	blocked := [1][2]int{mirror_ideal}
	fallback, fallback_ok := ar.hall_furnishing_fallback_tile(&d, room, mirror_ideal, blocked[:])
	testing.expect(t, fallback_ok && fallback != mirror_ideal, "blocked mirror ideal did not find a fallback")
	ar.plan_hall_furnishings(&d, blocked[:])
	blocked_layout := ar.hall_furnishing_layout(&d)
	testing.expect(t, blocked_layout.count == ar.MAX_HALL_FURNISHINGS, "one blocked ideal dropped a mandatory Hall furnishing")
	testing.expect(t, blocked_layout.kinds[0] == .Mirror && blocked_layout.tiles[0] == fallback, "mirror did not use nearest deterministic fallback")
	ar.plan_hall_furnishings(&d, blocked[:])
	testing.expect(t, ar.hall_furnishing_layout(&d) == blocked_layout, "Hall furnishing replanning was not deterministic")
}

@(test)
story_hall_chimes_hint_at_dash_capture :: proc(t: ^testing.T) {
	run: ar.Run
	defer ar.run_destroy(&run)
	chimes_tile := [2]int{5, 5}
	run.dungeon.tiles[5][5] = .Floor
	run.dungeon.tiles[5][6] = .Floor
	run.dungeon.hall_furnishings.count = 1
	run.dungeon.hall_furnishings.tiles[0] = chimes_tile
	run.dungeon.hall_furnishings.kinds[0] = .Chimes
	run.player.pos = {5.5, 6.5}
	run.player.prev_pos = run.player.pos

	testing.expect(
		t,
		ar.interact_prompt(&run) == "E: listen to the unlost chimes",
		"nearby Hall chimes must advertise their hint interaction",
	)
	testing.expect(t, !ar.player_interact(&run), "listening to Hall chimes must not change floors")
	hint_matches := len(run.numbers) == 1
	if hint_matches do hint_matches = run.numbers[0].text == ar.LOSSLESS_SOUL_CHIMES_HINT
	testing.expect(t, hint_matches, "Hall chimes must reveal the authored dash-capture hint")

	run.player.pos = {5.5, 7.2}
	run.player.prev_pos = run.player.pos
	testing.expect(t, ar.interact_prompt(&run) == "", "Hall chimes must not advertise beyond interaction range")
}

@(test)
story_hall_mist_is_mandatory_full_and_undamped :: proc(t: ^testing.T) {
	// Build a minimal isolated comparison: both rooms are special and receive the
	// same seeded roll sequence, but ordinary Quest is skipped/damped while Hall
	// is unconditionally stamped to a full bank.
	d: ar.Dungeon
	d.room_count = 2
	d.rooms_buf[0] = {6, 7, 8, 8}
	d.rooms_buf[1] = {24, 9, 8, 8}
	for room in ar.dungeon_rooms(&d) {
		for x in room.x ..< room.x + room.w {
			for y in room.y ..< room.y + room.h do d.tiles[x][y] = .Floor
		}
	}
	d.special_room_count = 2
	d.special_rooms_buf[0] = {.Quest, 0}
	d.special_rooms_buf[1] = {.Hall_Of_Unlost_Echoes, 1}

	zone: [ar.MAP_W][ar.MAP_H]f32
	ar.visual_mist_zones(&d, 0, &zone)
	quest_center := ar.room_center(d.rooms_buf[0])
	hall_center := ar.room_center(d.rooms_buf[1])
	testing.expect(t, zone[quest_center.x][quest_center.y] == 0, "ordinary special room was selected as a mist host")
	testing.expect(t, zone[hall_center.x][hall_center.y] == 1, "Hall did not retain a mandatory full-strength mist bank")
	for x in d.rooms_buf[1].x + 1 ..< d.rooms_buf[1].x + d.rooms_buf[1].w - 1 {
		for y in d.rooms_buf[1].y + 1 ..< d.rooms_buf[1].y + d.rooms_buf[1].h - 1 {
			testing.expect(t, zone[x][y] == 1, "Hall interior mist was damped below full strength")
		}
	}
}

@(test)
story_hall_flavor_classification_does_not_enable_refuge_healing :: proc(t: ^testing.T) {
	state := ar.Refuge_State{heal_accumulator = ar.REFUGE_HEAL_TICK_SECONDS - .1}
	player := ar.Player{hp = 40, max_hp = 100, stamina = 35, max_stamina = 100}
	result := ar.refuge_tick(.Hall_Of_Unlost_Echoes, &state, &player, 1)
	testing.expect(t, ar.special_room_is_flavor(.Hall_Of_Unlost_Echoes), "Hall classification must remain flavor-compatible")
	testing.expect(t, !ar.special_room_is_healing_refuge(.Hall_Of_Unlost_Echoes), "Hall must not be a healing refuge")
	testing.expect(t, result.healed == 0 && result.stamina_sapped == 0, "Hall inherited Bar/Garden refuge effects")
	testing.expect(t, player.hp == 40 && player.stamina == 35, "Hall refuge tick mutated player resources")
	testing.expect(t, state.heal_accumulator == 0, "non-healing Hall must discard stale refuge timing")
}
