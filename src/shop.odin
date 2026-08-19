package archrogue

// Deterministic M9 shop stock and atomic economy operations. This file is
// raylib-free; app/input/UI layers only select a row and present the result.

import "core:math"

SHOP_STOCK_CAPACITY :: 32
SHOP_SELL_MULTIPLIER :: 1.15
SHOP_BUY_MULTIPLIER :: 0.45

@(rodata)
SHOPKEEPER_NAMES := [5]string{
	"Mirel Coin-Candle",
	"Old Brass Venn",
	"Sister Ledger",
	"Korrin the Barter-Saint",
	"Pell of the Locked Shelf",
}

Shopkeeper :: struct {
	pos:             Vec2,
	prev_pos:        Vec2,
	home:            Vec2,
	motion:          Room_Npc_Motion,
	name:            string,
	role:            string,
	stock:           [SHOP_STOCK_CAPACITY]Item,
	stock_count:     int,
	buy_multiplier:  f64,
	sell_multiplier: f64,
	met:             bool,
}

Shop_Transaction_Result :: enum {
	Success,
	Invalid_Selection,
	Insufficient_Gold,
	Inventory_Full,
	Shop_Full,
}

Shop_Transaction :: struct {
	result: Shop_Transaction_Result,
	item:   Item,
	gold:   int,
}

shopkeeper_make :: proc(seed: u64, depth: int, room: Room, room_index := -1) -> Shopkeeper {
	geometry := u64(room.x) | u64(room.y) << 8 | u64(room.w) << 16 | u64(room.h) << 24
	rng := rng_make(derive_seed(seed, geometry ~ u64(depth)), stream = 7)
	center := room_center(room)
	home := Vec2{f32(center.x) + 0.5, f32(center.y) + 0.5}
	motion_seed := derive_seed(seed,geometry~u64(depth)~0x53484F504D4F544E)
	keeper := Shopkeeper{
		pos = home,
		prev_pos = home,
		home = home,
		motion = room_npc_motion_make(home,room_index,motion_seed,.Shopkeeper),
		name = SHOPKEEPER_NAMES[rng_below(&rng, len(SHOPKEEPER_NAMES))],
		role = "Allied Shopkeeper",
		buy_multiplier = SHOP_BUY_MULTIPLIER,
		sell_multiplier = SHOP_SELL_MULTIPLIER,
	}

	shop_stock_append(&keeper, Item{kind = .Heal_Potion, name = "Minor Healing Potion", icon = ICON_HEAL_POTION})
	shop_stock_append(&keeper, Item{kind = .Mana_Potion, name = "Lesser Mana Potion", icon = ICON_MANA_POTION})
	shop_stock_append(&keeper, Item{kind = .Identify_Scroll, name = "Scroll of Identify", icon = ICON_IDENTIFY_SCROLL})
	shop_stock_append(&keeper, Item{kind = .Remove_Curse_Scroll, name = "Scroll of Remove Curse", icon = ICON_REMOVE_CURSE_SCROLL, rarity = .Magic})
	shop_stock_append(&keeper, make_equipment(&rng, .Weapon, .Magic))
	shop_stock_append(&keeper, make_equipment(&rng, .Armor, .Magic))
	if depth >= 3 || rng_chance(&rng, 0.35) {
		shop_stock_append(&keeper, make_loot(&rng, {}).item)
	}
	return keeper
}

shop_sign_position :: proc(keeper: ^Shopkeeper) -> Vec2 {
	if keeper == nil do return {}
	return {keeper.home.x + 0.9, keeper.home.y}
}

@(private = "file")
shop_stock_append :: proc(keeper: ^Shopkeeper, item: Item) -> bool {
	if keeper == nil || keeper.stock_count >= SHOP_STOCK_CAPACITY do return false
	keeper.stock[keeper.stock_count] = item
	keeper.stock_count += 1
	return true
}

@(private = "file")
shop_stock_remove :: proc(keeper: ^Shopkeeper, index: int) {
	for i in index ..< keeper.stock_count - 1 {
		keeper.stock[i] = keeper.stock[i + 1]
	}
	keeper.stock_count -= 1
	keeper.stock[keeper.stock_count] = {}
}

item_shop_value :: proc(item: Item) -> int {
	switch item.kind {
	case .Heal_Potion:
		return max(8, HEAL_POTION_AMOUNT / 2)
	case .Mana_Potion:
		return max(8, MANA_POTION_AMOUNT / 2)
	case .Identify_Scroll:
		return 18
	case .Remove_Curse_Scroll:
		return 34
	case .Weapon, .Armor:
	}

	rarity_bonus := 0
	switch item.rarity {
	case .Common:       rarity_bonus = 0
	case .Magic:        rarity_bonus = 18
	case .Rare:         rarity_bonus = 42
	case .Unique:       rarity_bonus = 80
	case .Legendary:    rarity_bonus = 125
	case .Cursed:       rarity_bonus = 56
	case .Unidentified: rarity_bonus = 0 // presentation-only; generated items retain their true tier
	}
	return max(5, 12 + rarity_bonus + item.power * 5 + item.defense * 6 + item.affix_count * 7)
}

// Python's round uses ties-to-even. Keeping the multiplication in f64 also
// preserves its ordinary binary-float behavior for the source multipliers.
round_to_even :: proc(value: f64) -> int {
	if value < 0 do return -round_to_even(-value)
	lower := int(math.floor(value))
	fraction := value - f64(lower)
	if fraction > 0.5 do return lower + 1
	if fraction < 0.5 do return lower
	return (lower & 1) == 0 ? lower : lower + 1
}

shop_price :: proc(keeper: ^Shopkeeper, item: Item) -> int {
	multiplier := SHOP_SELL_MULTIPLIER
	if keeper != nil && keeper.sell_multiplier > 0 do multiplier = keeper.sell_multiplier
	return max(1, round_to_even(f64(item_shop_value(item)) * multiplier))
}

shop_buyback_value :: proc(keeper: ^Shopkeeper, item: Item) -> int {
	multiplier := SHOP_BUY_MULTIPLIER
	if keeper != nil && keeper.buy_multiplier > 0 do multiplier = keeper.buy_multiplier
	return max(1, round_to_even(f64(item_shop_value(item)) * multiplier))
}

shop_buy :: proc(keeper: ^Shopkeeper, player: ^Player, stock_index: int) -> Shop_Transaction {
	if keeper == nil || player == nil || stock_index < 0 || stock_index >= keeper.stock_count {
		return {result = .Invalid_Selection}
	}
	item := keeper.stock[stock_index]
	price := shop_price(keeper, item)
	if player.gold < price {
		return {result = .Insufficient_Gold, item = item, gold = price}
	}
	needs_bag := item.kind != .Heal_Potion && item.kind != .Mana_Potion
	if needs_bag && player.bag_count >= BAG_CAPACITY {
		return {result = .Inventory_Full, item = item, gold = price}
	}

	// All validation is complete before the first mutation.
	shop_stock_remove(keeper, stock_index)
	#partial switch item.kind {
	case .Heal_Potion:
		player.heal_potions += 1
	case .Mana_Potion:
		player.mana_potions += 1
	case .Identify_Scroll, .Remove_Curse_Scroll, .Weapon, .Armor:
		player.bag[player.bag_count] = item
		player.bag_count += 1
	}
	player.gold -= price
	return {result = .Success, item = item, gold = price}
}

shop_sell_bag :: proc(keeper: ^Shopkeeper, player: ^Player, bag_index: int) -> Shop_Transaction {
	if keeper == nil || player == nil || bag_index < 0 || bag_index >= player.bag_count {
		return {result = .Invalid_Selection}
	}
	item := player.bag[bag_index]
	value := shop_buyback_value(keeper, item)
	if keeper.stock_count >= SHOP_STOCK_CAPACITY {
		return {result = .Shop_Full, item = item, gold = value}
	}

	// Capacity is validated before either inventory changes.
	_ = shop_stock_append(keeper, item)
	for i in bag_index ..< player.bag_count - 1 {
		player.bag[i] = player.bag[i + 1]
	}
	player.bag_count -= 1
	player.bag[player.bag_count] = {}
	player.gold += value
	return {result = .Success, item = item, gold = value}
}

