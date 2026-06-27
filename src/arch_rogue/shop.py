# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

import math

from .constants import MAX_INVENTORY
from .models import FloatingText, Item, Shopkeeper


class ShopMixin:
    def nearby_shopkeeper(self, radius: float = 1.35) -> Shopkeeper | None:
        nearby = [
            shopkeeper
            for shopkeeper in self.shopkeepers
            if math.hypot(shopkeeper.x - self.player.x, shopkeeper.y - self.player.y)
            < radius
        ]
        return min(
            nearby,
            key=lambda shopkeeper: math.hypot(
                shopkeeper.x - self.player.x, shopkeeper.y - self.player.y
            ),
            default=None,
        )

    def item_value(self, item: Item) -> int:
        if item.slot == "potion":
            return max(8, item.heal // 2)
        if item.slot == "mana_potion":
            return max(8, item.mana // 2)
        if item.slot == "identify":
            return 18
        rarity_bonus = {
            "Common": 0,
            "Magic": 18,
            "Rare": 42,
            "Unique": 80,
            "Legendary": 125,
            "Cursed": 56,
        }.get(item.rarity, 0)
        return max(
            5,
            12
            + rarity_bonus
            + item.power * 5
            + item.defense * 6
            + len(item.affixes) * 7,
        )

    def shop_price(self, shopkeeper: Shopkeeper, item: Item) -> int:
        return max(1, int(round(self.item_value(item) * shopkeeper.sell_multiplier)))

    def shop_buyback_value(self, shopkeeper: Shopkeeper, item: Item) -> int:
        return max(1, int(round(self.item_value(item) * shopkeeper.buy_multiplier)))

    def open_shop(self, shopkeeper: Shopkeeper) -> None:
        shopkeeper.met = True
        self.active_shopkeeper = shopkeeper
        self.shop_open = True
        self.shop_mode = "buy"
        self.shop_cursor = 0
        self.inventory_open = False
        self.character_menu_open = False
        self.floaters.append(
            FloatingText(
                f"{shopkeeper.name}: trade",
                shopkeeper.x,
                shopkeeper.y - 0.55,
                (225, 190, 92),
                ttl=1.0,
            )
        )

    def close_shop(self) -> None:
        self.shop_open = False
        self.active_shopkeeper = None
        self.shop_cursor = 0

    def shop_entries(self) -> list[Item]:
        if self.active_shopkeeper is None:
            return []
        return (
            self.active_shopkeeper.inventory
            if self.shop_mode == "buy"
            else self.player.inventory
        )

    def clamp_shop_cursor(self) -> None:
        entries = self.shop_entries()
        if not entries:
            self.shop_cursor = 0
        else:
            self.shop_cursor = max(0, min(self.shop_cursor, len(entries) - 1))

    def cycle_shop_mode(self) -> None:
        self.shop_mode = "sell" if self.shop_mode == "buy" else "buy"
        self.shop_cursor = 0

    def move_shop_selection(self, delta: int) -> None:
        entries = self.shop_entries()
        if not entries:
            self.shop_cursor = 0
            return
        self.shop_cursor = (self.shop_cursor + delta) % len(entries)

    def transact_shop_selection(self) -> bool:
        shopkeeper = self.active_shopkeeper
        if shopkeeper is None:
            return False
        entries = self.shop_entries()
        if not entries:
            return False
        self.clamp_shop_cursor()
        item = entries[self.shop_cursor]
        if self.shop_mode == "buy":
            price = self.shop_price(shopkeeper, item)
            if self.player.gold < price:
                self.floaters.append(
                    FloatingText(
                        "Need more gold",
                        self.player.x,
                        self.player.y - 0.45,
                        (235, 210, 120),
                        ttl=1.0,
                    )
                )
                return False
            if len(self.player.inventory) >= MAX_INVENTORY:
                self.floaters.append(
                    FloatingText(
                        "Inventory full",
                        self.player.x,
                        self.player.y - 0.45,
                        (235, 210, 120),
                        ttl=1.0,
                    )
                )
                return False
            shopkeeper.inventory.remove(item)
            self.player.inventory.append(item)
            self.player.gold -= price
            self.floaters.append(
                FloatingText(
                    f"Bought {item.display_name}",
                    self.player.x,
                    self.player.y - 0.45,
                    (210, 230, 180),
                    ttl=1.0,
                )
            )
        else:
            value = self.shop_buyback_value(shopkeeper, item)
            self.player.inventory.remove(item)
            shopkeeper.inventory.append(item)
            self.player.gold += value
            self.floaters.append(
                FloatingText(
                    f"Sold {item.display_name}",
                    self.player.x,
                    self.player.y - 0.45,
                    (225, 190, 92),
                    ttl=1.0,
                )
            )
        self.clamp_shop_cursor()
        self.play_sfx("pickup")
        self.save_run()
        return True
