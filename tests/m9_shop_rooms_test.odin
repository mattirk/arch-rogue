package archrogue_tests

// Headless M9 parity tests: deterministic special-room planning, sealed-room
// invariants, shop stock/economy math, atomic trades, and flavor-refuge rules.

import "core:testing"
import ar "../src"

@(private = "file")
closed_doors_on_room_perimeter :: proc(d: ^ar.Dungeon, room: ar.Room) -> (count: int) {
	for x in room.x ..< room.x + room.w {
		if d.tiles[x][room.y] == .Closed_Door do count += 1
		if d.tiles[x][room.y + room.h - 1] == .Closed_Door do count += 1
	}
	for y in room.y + 1 ..< room.y + room.h - 1 {
		if d.tiles[room.x][y] == .Closed_Door do count += 1
		if d.tiles[room.x + room.w - 1][y] == .Closed_Door do count += 1
	}
	return count
}

@(private = "file")
closed_door_count :: proc(d: ^ar.Dungeon) -> (count: int) {
	for x in 0 ..< ar.MAP_W {
		for y in 0 ..< ar.MAP_H {
			if d.tiles[x][y] == .Closed_Door do count += 1
		}
	}
	return count
}

@(test)
m9_special_rooms_are_deterministic_distinct_and_sealed :: proc(t: ^testing.T) {
	SAMPLES :: 240
	shop_count, bar_count, garden_count := 0, 0, 0
	no_special_floor_seen := false
	for seed_i in 1 ..= SAMPLES {
		seed := u64(seed_i)
		a_rng := ar.rng_make(ar.derive_seed(seed, 1))
		b_rng := ar.rng_make(ar.derive_seed(seed, 1))
		a, a_ok := ar.dungeon_generate(&a_rng)
		b, b_ok := ar.dungeon_generate(&b_rng)
		testing.expectf(t, a_ok && b_ok, "generation failed for seed %v", seed_i)
		if !a_ok || !b_ok do continue
		testing.expectf(t, a == b, "special-room plan changed between identical seed %v runs", seed_i)

		occupied: [ar.MAX_ROOMS_CAP]bool
		for special in ar.special_rooms(&a) {
			testing.expectf(t, special.room_index > 0 && special.room_index < a.room_count - 1, "%v used excluded room %v", special.kind, special.room_index)
			testing.expectf(t, !occupied[special.room_index], "room %v received two special kinds", special.room_index)
			occupied[special.room_index] = true
			room := a.rooms_buf[special.room_index]
			testing.expectf(t, closed_doors_on_room_perimeter(&a, room) > 0, "%v room %v was not sealed", special.kind, special.room_index)

			center := ar.room_center(room)
			at_point := ar.special_room_kind_at_point(&a, f32(center.x) + 0.5, f32(center.y) + 0.5)
			at_tile := ar.special_room_interior_kind(&a, center.x, center.y)
			testing.expectf(t, at_point == special.kind && at_tile == special.kind, "%v room queries disagree", special.kind)
			testing.expect(t, ar.special_room_kind_for_room(&a, special.room_index) == special.kind, "room-index query lost its kind")
			found_room, found_index, found := ar.dungeon_room_at_point(&a, f32(center.x) + 0.5, f32(center.y) + 0.5)
			testing.expect(t, found && found_index == special.room_index && found_room^ == room, "point-to-room query returned the wrong chamber")
			found_special, found_special_ok := ar.special_room_at_point(&a, f32(center.x) + 0.5, f32(center.y) + 0.5)
			testing.expect(t, found_special_ok && found_special.kind == special.kind, "point-to-special query returned the wrong room")

			switch special.kind {
			case .Shop:
				shop_count += 1
				testing.expect(t, ar.special_room_is_safe(special.kind), "shop must use safe population")
			case .Bar:
				bar_count += 1
				testing.expect(t, ar.special_room_is_flavor(special.kind) && !ar.special_room_is_safe(special.kind), "bar must retain ordinary population")
			case .Garden:
				garden_count += 1
				testing.expect(t, ar.special_room_is_flavor(special.kind) && !ar.special_room_is_safe(special.kind), "garden must retain ordinary population")
			case .None:
				testing.expect(t, false, "stored special room cannot have kind None")
			case .Quest, .Hall_Of_Unlost_Echoes:
				testing.expect(t, false, "non-story generation emitted a story room")
			}
		}

		if a.special_room_count == 0 {
			no_special_floor_seen = true
			testing.expectf(t, closed_door_count(&a) > 0, "seed %v bypassed the anti-doorless fallback", seed_i)
		}
	}

	// Broad deterministic smoke bounds catch a missing/always-on roll without
	// coupling the suite to one exact PCG sample sequence.
	testing.expectf(t, shop_count >= 150 && shop_count <= 215, "shop appeared %v/%v times; expected about 75%%", shop_count, SAMPLES)
	testing.expectf(t, bar_count >= 85 && bar_count <= 155, "bar appeared %v/%v times; expected about 50%%", bar_count, SAMPLES)
	testing.expectf(t, garden_count >= 85 && garden_count <= 155, "garden appeared %v/%v times; expected about 50%%", garden_count, SAMPLES)
	testing.expect(t, no_special_floor_seen, "sample set never exercised the anti-doorless fallback")
}

@(test)
m9_shop_stock_is_replayable_and_has_canonical_wares :: proc(t: ^testing.T) {
	room := ar.Room{10, 12, 8, 8}
	a := ar.shopkeeper_make(8128, 1, room)
	b := ar.shopkeeper_make(8128, 1, room)
	testing.expect(t, a == b, "same floor seed/depth/room must replay identical stock")
	testing.expect(t, a.stock_count == 6 || a.stock_count == 7, "early shop must contain six mandatory wares and at most one bonus roll")
	testing.expect(t, a.stock[0].kind == .Heal_Potion, "first mandatory ware must be a healing potion")
	testing.expect(t, a.stock[1].kind == .Mana_Potion, "second mandatory ware must be a mana potion")
	testing.expect(t, a.stock[2].kind == .Identify_Scroll, "identify scroll must always be stocked")
	testing.expect(t, a.stock[3].kind == .Remove_Curse_Scroll, "remove-curse scroll must always be stocked")
	testing.expect(t, a.stock[4].kind == .Weapon && a.stock[4].rarity == .Magic, "shop must stock a Magic weapon")
	testing.expect(t, a.stock[5].kind == .Armor && a.stock[5].rarity == .Magic, "shop must stock Magic armor")

	deep := ar.shopkeeper_make(8128, 3, room)
	testing.expect(t, deep.stock_count == 7, "depth three and below must add a generic loot roll")
	center := ar.room_center(room)
	home := ar.Vec2{f32(center.x) + 0.5, f32(center.y) + 0.5}
	testing.expect(t, deep.pos == home && deep.prev_pos == home && deep.home == home, "shopkeeper must initialize at room center without interpolation history")
	fixed_sign := ar.shop_sign_position(&deep)
	testing.expect(t, fixed_sign == ar.Vec2{home.x + 0.9, home.y}, "shop sign home anchor changed")
	deep.pos += ar.Vec2{2,1}
	testing.expect(t, ar.shop_sign_position(&deep) == fixed_sign, "shop sign must not follow the wandering keeper")
}

@(test)
m9_shop_values_use_python_ties_to_even :: proc(t: ^testing.T) {
	testing.expect(t, ar.item_shop_value(ar.Item{kind = .Heal_Potion}) == 17, "35-point healing potion value must floor to 17")
	testing.expect(t, ar.item_shop_value(ar.Item{kind = .Mana_Potion}) == 12, "24-point mana potion value must be 12")
	testing.expect(t, ar.item_shop_value(ar.Item{kind = .Identify_Scroll}) == 18, "identify scroll value changed")
	testing.expect(t, ar.item_shop_value(ar.Item{kind = .Remove_Curse_Scroll}) == 34, "remove-curse value changed")
	gear := ar.Item{kind = .Weapon, rarity = .Rare, power = 3, defense = 2, affix_count = 2}
	testing.expect(t, ar.item_shop_value(gear) == 95, "gear value must include rarity, stats, and seven gold per affix")

	testing.expect(t, ar.round_to_even(34.5) == 34, "lower even tie must stay down")
	testing.expect(t, ar.round_to_even(11.5) == 12, "lower odd tie must round up")
	testing.expect(t, ar.round_to_even(-12.5) == -12, "negative ties must also round to even")
	thirty_gold := ar.Item{kind = .Armor, rarity = .Common, defense = 3}
	testing.expect(t, ar.item_shop_value(thirty_gold) == 30, "test fixture no longer has value 30")
	testing.expect(t, ar.shop_price(nil, thirty_gold) == 34, "30 * 1.15 must match Python round(34.5)")
	testing.expect(t, ar.shop_buyback_value(nil, thirty_gold) == 14, "30 * 0.45 must match Python round(13.5)")
}

@(test)
m9_shop_transactions_are_atomic :: proc(t: ^testing.T) {
	room := ar.Room{10, 12, 8, 8}

	poor_keeper := ar.shopkeeper_make(44, 1, room)
	poor := ar.Player{gold = 0}
	poor_keeper_before, poor_before := poor_keeper, poor
	failed := ar.shop_buy(&poor_keeper, &poor, 0)
	testing.expect(t, failed.result == .Insufficient_Gold, "unaffordable purchase returned the wrong result")
	testing.expect(t, poor_keeper == poor_keeper_before && poor == poor_before, "failed purchase partially mutated inventories")

	keeper := ar.shopkeeper_make(44, 1, room)
	buyer := ar.Player{gold = 100}
	price := ar.shop_price(&keeper, keeper.stock[0])
	stock_before := keeper.stock_count
	bought := ar.shop_buy(&keeper, &buyer, 0)
	testing.expect(t, bought.result == .Success && bought.gold == price, "valid purchase failed")
	testing.expect(t, keeper.stock_count == stock_before - 1, "purchase did not remove one stock row")
	testing.expect(t, buyer.gold == 100 - price && buyer.heal_potions == 1, "potion purchase did not update player atomically")

	full_keeper := ar.shopkeeper_make(55, 1, room)
	full := ar.Player{gold = 10000, bag_count = ar.BAG_CAPACITY}
	for i in 0 ..< ar.BAG_CAPACITY do full.bag[i] = ar.Item{kind = .Weapon, name = "Packed"}
	full_keeper_before, full_before := full_keeper, full
	blocked := ar.shop_buy(&full_keeper, &full, 4)
	testing.expect(t, blocked.result == .Inventory_Full, "equipment purchase must respect the fixed bag capacity")
	testing.expect(t, full_keeper == full_keeper_before && full == full_before, "full-bag purchase partially mutated state")

	seller_keeper := ar.shopkeeper_make(66, 1, room)
	seller := ar.Player{bag_count = 1}
	seller.bag[0] = ar.Item{kind = .Armor, name = "Mail", rarity = .Common, defense = 3}
	buyback := ar.shop_buyback_value(&seller_keeper, seller.bag[0])
	stock_before = seller_keeper.stock_count
	sold := ar.shop_sell_bag(&seller_keeper, &seller, 0)
	testing.expect(t, sold.result == .Success && sold.gold == buyback, "valid sale failed")
	testing.expect(t, seller.bag_count == 0 && seller.gold == buyback, "sale did not remove the bag row and pay its value")
	testing.expect(t, seller_keeper.stock_count == stock_before + 1, "sold item did not enter shop stock")

	packed_keeper := ar.shopkeeper_make(77, 1, room)
	packed_keeper.stock_count = ar.SHOP_STOCK_CAPACITY
	packed_seller := ar.Player{bag_count = 1}
	packed_seller.bag[0] = ar.Item{kind = .Weapon, name = "Spare Sword", power = 2}
	packed_keeper_before, packed_seller_before := packed_keeper, packed_seller
	shop_full := ar.shop_sell_bag(&packed_keeper, &packed_seller, 0)
	testing.expect(t, shop_full.result == .Shop_Full, "bounded shop must reject inventory overflow")
	testing.expect(t, packed_keeper == packed_keeper_before && packed_seller == packed_seller_before, "failed sale partially mutated state")
}

@(test)
m9_bar_and_garden_refuge_formulas_match_pygame :: proc(t: ^testing.T) {
	garden_state: ar.Refuge_State
	garden_player := ar.Player{hp = 50, max_hp = 100, stamina = 100, max_stamina = 100}
	first := ar.refuge_tick(.Garden, &garden_state, &garden_player, 2.5)
	testing.expect(t, first.healed == 0 && garden_player.hp == 50, "garden healed before five seconds")
	second := ar.refuge_tick(.Garden, &garden_state, &garden_player, 2.5)
	testing.expect(t, second.healed == 6 && garden_player.hp == 56, "garden heal must be max(2, max_hp/25 + 2)")
	_ = ar.refuge_tick(.None, &garden_state, &garden_player, 1)
	testing.expect(t, garden_state.heal_accumulator == 0, "leaving a refuge must discard partial heal time")

	bar_state: ar.Refuge_State
	bar_player := ar.Player{hp = 50, max_hp = 100, stamina = 100, max_stamina = 100}
	bar_first := ar.refuge_tick(.Bar, &bar_state, &bar_player, 1)
	testing.expect(t, bar_first.stamina_sapped == 100 && bar_player.stamina == 0, "untapped bar must sap 130 stamina per second down to zero")
	bar_second := ar.refuge_tick(.Bar, &bar_state, &bar_player, 4)
	testing.expect(t, bar_second.healed == 3 && bar_player.hp == 53, "bar heal must be max(1, max_hp/50 + 1)")
	testing.expect(t, ar.bar_drink(&bar_state, &bar_player), "first tapped-barrel drink must succeed")
	testing.expect(t, bar_state.bar_toasted && bar_player.hp == 58 && bar_player.stamina == 10, "toast must restore 5 HP and 10 stamina")
	testing.expect(t, !ar.bar_drink(&bar_state, &bar_player), "a bar's toast must be single-use")
	stamina_before := bar_player.stamina
	_ = ar.refuge_tick(.Bar, &bar_state, &bar_player, 1)
	testing.expect(t, bar_player.stamina == stamina_before, "toasted bar must stop sapping stamina")

	barrel := [2]int{4, 7}
	center := ar.Vec2{4.5, 7.5}
	testing.expect(t, ar.barrel_in_drink_range(center + ar.Vec2{1.34, 0}, barrel), "adjacent barrel should be in range")
	testing.expect(t, !ar.barrel_in_drink_range(center + ar.Vec2{1.36, 0}, barrel), "barrel range must remain below 1.35 tiles")
}
