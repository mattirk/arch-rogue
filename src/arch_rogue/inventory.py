# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

from .constants import MAX_INVENTORY
from .models import FloatingText, Item


class InventoryMixin:
    def item_decision_summary(self, item: Item) -> str:
        if item.slot == "story_relic":
            return "Story relic · collect it to clarify the guest's plea"
        if item.slot == "potion":
            missing = max(0, self.player.max_hp - self.player.hp)
            return f"Restores {item.heal} HP" + (
                f" · missing {missing}" if missing else " · save for later"
            )
        if item.slot == "mana_potion":
            missing = max(0, int(self.player.max_mana - self.player.mana))
            return f"Restores {item.mana} mana" + (
                f" · missing {missing}" if missing else " · save for later"
            )
        if item.slot == "identify":
            unidentified = sum(
                1 for entry in self.player.inventory if entry.unidentified
            )
            return "Reveals best unknown item" + (
                f" · {unidentified} unknown" if unidentified else " · none unknown"
            )
        if item.unidentified:
            return "Unknown stats · use to reveal or identify safely"
        if item.slot in ("weapon", "armor"):
            equipped = self.player.equipment.get(item.slot)
            current = 0
            incoming = item.power if item.slot == "weapon" else item.defense
            if equipped:
                current = equipped.power if item.slot == "weapon" else equipped.defense
            delta = incoming - current
            stat = "damage" if item.slot == "weapon" else "armor"
            tradeoff = " · cursed power" if item.cursed else ""
            tags: list[str] = []
            if item.damage_type and item.damage_type != "physical":
                tags.append(item.damage_type)
            if item.skill_bonus:
                tags.append(item.skill_bonus)
            if item.proc_effect:
                tags.append(item.proc_effect)
            detail = f" · {' · '.join(tags)}" if tags else ""
            sign = "+" if delta > 0 else ""
            return f"{sign}{delta} {stat} vs equipped{tradeoff}{detail}"
        return "Use from inventory"

    def inventory_category(self, item: Item) -> int:
        order = {
            "weapon": 0,
            "armor": 1,
            "potion": 2,
            "mana_potion": 3,
            "identify": 4,
        }
        return order.get(item.slot, 9)

    def inventory_power_score(self, item: Item) -> int:
        if item.slot == "weapon":
            return item.power
        if item.slot == "armor":
            return item.defense
        if item.slot == "potion":
            return item.heal
        if item.slot == "mana_potion":
            return item.mana
        return 0

    def inventory_rarity_rank(self, item: Item) -> int:
        return {
            "Common": 0,
            "Magic": 1,
            "Rare": 2,
            "Cursed": 3,
            "Unique": 4,
            "Unidentified": 5,
        }.get(item.visible_rarity, 0)

    def inventory_sort_key(self, item: Item) -> tuple[int, int, int, str]:
        if self.inventory_sort_mode == "rarity":
            return (
                -self.inventory_rarity_rank(item),
                self.inventory_category(item),
                -self.inventory_power_score(item),
                item.display_name,
            )
        if self.inventory_sort_mode == "power":
            return (
                self.inventory_category(item),
                -self.inventory_power_score(item),
                -self.inventory_rarity_rank(item),
                item.display_name,
            )
        return (
            self.inventory_category(item),
            -self.inventory_rarity_rank(item),
            -self.inventory_power_score(item),
            item.display_name,
        )

    def clamp_inventory_selection(self) -> None:
        count = len(self.player.inventory)
        if count <= 0:
            self.inventory_cursor = 0
            self.inventory_scroll = 0
            return
        self.inventory_cursor = max(0, min(self.inventory_cursor, count - 1))
        self.inventory_scroll = max(0, min(self.inventory_scroll, count - 1))

    def ensure_inventory_cursor_visible(self, visible_rows: int) -> None:
        self.clamp_inventory_selection()
        count = len(self.player.inventory)
        if count <= 0 or visible_rows <= 0:
            self.inventory_scroll = 0
            return
        visible_rows = max(1, min(visible_rows, count))
        if self.inventory_cursor < self.inventory_scroll:
            self.inventory_scroll = self.inventory_cursor
        elif self.inventory_cursor >= self.inventory_scroll + visible_rows:
            self.inventory_scroll = self.inventory_cursor - visible_rows + 1
        max_scroll = max(0, count - visible_rows)
        self.inventory_scroll = max(0, min(self.inventory_scroll, max_scroll))

    def set_inventory_selection(self, index: int, visible_rows: int = 0) -> None:
        if not self.player.inventory:
            self.inventory_cursor = 0
            self.inventory_scroll = 0
            return
        self.inventory_cursor = max(0, min(index, len(self.player.inventory) - 1))
        if visible_rows > 0:
            self.ensure_inventory_cursor_visible(visible_rows)
        else:
            self.clamp_inventory_selection()

    def move_inventory_selection(self, delta: int, visible_rows: int = 0) -> None:
        self.set_inventory_selection(self.inventory_cursor + delta, visible_rows)

    def use_selected_inventory_slot(self) -> None:
        self.clamp_inventory_selection()
        if self.player.inventory:
            self.use_inventory_slot(self.inventory_cursor)

    def drop_selected_inventory_slot(self) -> None:
        self.clamp_inventory_selection()
        if self.player.inventory:
            self.drop_inventory_slot(self.inventory_cursor)

    def sort_inventory(self) -> None:
        self.player.inventory.sort(key=self.inventory_sort_key)
        self.clamp_inventory_selection()
        self.floaters.append(
            FloatingText(
                f"Inventory sorted by {self.inventory_sort_mode}",
                self.player.x,
                self.player.y - 0.4,
                (210, 220, 235),
                ttl=0.9,
            )
        )
        self.save_run()

    def cycle_inventory_sort_mode(self) -> None:
        modes = ("type", "rarity", "power")
        current = (
            modes.index(self.inventory_sort_mode)
            if self.inventory_sort_mode in modes
            else 0
        )
        self.inventory_sort_mode = modes[(current + 1) % len(modes)]
        self.sort_inventory()

    def drop_inventory_slot(self, index: int) -> None:
        if index < 0 or index >= len(self.player.inventory):
            return
        item = self.player.inventory.pop(index)
        item.x, item.y = self.drop_position_near(self.player.x, self.player.y)
        self.items.append(item)
        self.floaters.append(
            FloatingText(
                f"Dropped {item.display_name}",
                self.player.x,
                self.player.y - 0.4,
                (235, 210, 120),
                ttl=1.0,
            )
        )
        self.play_sfx("pickup")
        self.clamp_inventory_selection()
        self.save_run()

    def use_inventory_slot(self, index: int) -> None:
        if index < 0 or index >= len(self.player.inventory):
            return
        item = self.player.inventory.pop(index)
        if item.slot == "potion":
            if not self.drink_potion(item):
                self.player.inventory.insert(index, item)
            self.clamp_inventory_selection()
            return
        if item.slot == "mana_potion":
            if not self.drink_mana_potion(item):
                self.player.inventory.insert(index, item)
            self.clamp_inventory_selection()
            return
        if item.slot == "identify":
            self.identify_first_item()
            self.clamp_inventory_selection()
            self.save_run()
            return
        if item.unidentified:
            item.unidentified = False
            self.floaters.append(
                FloatingText(
                    f"Identified {item.name}",
                    self.player.x,
                    self.player.y - 0.4,
                    (160, 220, 255),
                    ttl=1.2,
                )
            )
        old = self.player.equipment.get(item.slot)
        self.player.equipment[item.slot] = item
        if old and len(self.player.inventory) < MAX_INVENTORY:
            self.player.inventory.append(old)
        self.floaters.append(
            FloatingText(
                f"Equipped {item.display_name}",
                self.player.x,
                self.player.y - 0.4,
                (160, 220, 255),
                ttl=1.2,
            )
        )
        self.play_sfx("pickup")
        self.clamp_inventory_selection()
        self.save_run()

    def toggle_quest_info_visibility(self) -> None:
        self.quest_info_visible = not self.quest_info_visible
        label = "Quest info shown" if self.quest_info_visible else "Quest info hidden"
        color = (
            self.story_state.accent
            if self.story_state is not None and self.quest_info_visible
            else (170, 165, 155)
        )
        self.floaters.append(
            FloatingText(label, self.player.x, self.player.y - 0.4, color, ttl=0.9)
        )

    def use_first_potion(self) -> None:
        if self.player.hp >= self.player.max_hp:
            self.floaters.append(
                FloatingText(
                    "Already at full health",
                    self.player.x,
                    self.player.y - 0.4,
                    (235, 210, 120),
                )
            )
            return
        potions = [
            (index, item)
            for index, item in enumerate(self.player.inventory)
            if item.slot == "potion"
        ]
        if potions:
            missing = self.player.max_hp - self.player.hp
            index, item = min(potions, key=lambda entry: abs(entry[1].heal - missing))
            _ = self.player.inventory.pop(index)
            self.drink_potion(item)
            return
        self.floaters.append(
            FloatingText(
                "No potion", self.player.x, self.player.y - 0.4, (235, 210, 120)
            )
        )

    def use_first_mana_potion(self) -> None:
        if self.player.mana >= self.player.max_mana:
            self.floaters.append(
                FloatingText(
                    "Already at full mana",
                    self.player.x,
                    self.player.y - 0.4,
                    (235, 210, 120),
                )
            )
            return
        potions = [
            (index, item)
            for index, item in enumerate(self.player.inventory)
            if item.slot == "mana_potion"
        ]
        if potions:
            missing = self.player.max_mana - self.player.mana
            index, item = min(potions, key=lambda entry: abs(entry[1].mana - missing))
            _ = self.player.inventory.pop(index)
            self.drink_mana_potion(item)
            return
        self.floaters.append(
            FloatingText(
                "No mana potion",
                self.player.x,
                self.player.y - 0.4,
                (235, 210, 120),
            )
        )

    def drink_potion(self, item: Item) -> bool:
        if self.player.hp >= self.player.max_hp:
            self.floaters.append(
                FloatingText(
                    "Already at full health",
                    self.player.x,
                    self.player.y - 0.4,
                    (235, 210, 120),
                )
            )
            return False
        self.run_stats.potions_used += 1
        old_hp = self.player.hp
        self.player.hp = min(self.player.max_hp, self.player.hp + item.heal)
        healed = self.player.hp - old_hp
        self.floaters.append(
            FloatingText(
                f"+{healed}", self.player.x, self.player.y - 0.4, (105, 230, 125)
            )
        )
        self.play_sfx("pickup")
        self.save_run()
        return True

    def drink_mana_potion(self, item: Item) -> bool:
        if self.player.mana >= self.player.max_mana:
            self.floaters.append(
                FloatingText(
                    "Already at full mana",
                    self.player.x,
                    self.player.y - 0.4,
                    (235, 210, 120),
                )
            )
            return False
        self.run_stats.potions_used += 1
        old_mana = self.player.mana
        self.player.mana = min(self.player.max_mana, self.player.mana + item.mana)
        restored = int(self.player.mana - old_mana)
        self.floaters.append(
            FloatingText(
                f"+{restored} mana", self.player.x, self.player.y - 0.4, (105, 165, 255)
            )
        )
        self.play_sfx("pickup")
        self.save_run()
        return True

    def identify_first_item(self) -> None:
        unidentified = [item for item in self.player.inventory if item.unidentified]
        if unidentified:
            item = max(
                unidentified,
                key=lambda entry: (
                    self.inventory_rarity_rank(entry),
                    self.inventory_power_score(entry),
                    entry.display_name,
                ),
            )
            item.unidentified = False
            self.floaters.append(
                FloatingText(
                    f"Identified {item.name}",
                    self.player.x,
                    self.player.y - 0.4,
                    (160, 220, 255),
                )
            )
            return
        self.floaters.append(
            FloatingText(
                "Nothing to identify",
                self.player.x,
                self.player.y - 0.4,
                (235, 210, 120),
            )
        )

    def identify_all_items(self) -> int:
        count = 0
        for item in self.player.inventory:
            if item.unidentified:
                item.unidentified = False
                count += 1
        return count
