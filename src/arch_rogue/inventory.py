# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
#
# AI Provenance & Liability Notice:
# This repository contains code generated, assisted, or refactored by Artificial
# Intelligence models. Provided strictly "AS IS" under Apache 2.0 with no warranty
# of clean IP provenance or non-infringement; downstream users assume all legal
# and financial risk and should perform their own compliance audits.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

from .constants import MAX_INVENTORY
from .content import discipline_by_key
from .models import FloatingText, Item

ARCHETYPE_BUILD_TAGS: dict[str, tuple[str, ...]] = {
    "Warden": ("melee", "guard", "ward", "holy", "thorns"),
    "Rogue": ("critical", "poison", "stealth", "dash", "attack_speed"),
    "Arcanist": ("arcane", "bolt", "nova", "frost", "cast_speed"),
    "Acolyte": ("shadow", "blood", "lifesteal", "spirit", "curse"),
    "Ranger": ("volley", "control", "beast", "movement", "attack_speed"),
}

AFFIX_TAG_LABELS: dict[str, str] = {
    # Display labels for affix tag chips. The icons themselves are drawn
    # procedurally by MenuBaseMixin.draw_tag_icon, so these are text-only.
    "armor": "armor",
    "arcane": "arcane",
    "attack_speed": "atk speed",
    "beast": "beast",
    "bleed": "bleed",
    "blood": "blood",
    "bolt": "bolt",
    "cast_speed": "cast speed",
    "control": "control",
    "counter": "counter",
    "critical": "crit",
    "curse": "curse",
    "dash": "dash",
    "fire": "fire",
    "frost": "frost",
    "guard": "guard",
    "holy": "holy",
    "knockback": "knockback",
    "legendary": "legendary",
    "lifesteal": "lifesteal",
    "melee": "melee",
    "movement": "movement",
    "nova": "nova",
    "physical": "physical",
    "poison": "poison",
    "proc": "proc",
    "retaliate": "retaliate",
    "risk": "risk",
    "shadow": "shadow",
    "spell": "spell",
    "spirit": "spirit",
    "stealth": "stealth",
    "survival": "survival",
    "thorns": "thorns",
    "volley": "volley",
    "ward": "ward",
}


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
            if item.attack_speed:
                tags.append(f"{item.attack_speed:+.0%} attack")
            if item.cast_speed:
                tags.append(f"{item.cast_speed:+.0%} cast")
            if item.move_speed:
                tags.append(f"{item.move_speed:+.0%} move")
            if item.thorns:
                tags.append(f"{item.thorns} thorns")
            if item.lifesteal:
                tags.append(f"{item.lifesteal:.0%} leech")
            build_hint = self.item_build_relevance_hint(item)
            if build_hint:
                tags.append(build_hint)
            detail = f" · {' · '.join(tags)}" if tags else ""
            sign = "+" if delta > 0 else ""
            return f"{sign}{delta} {stat} vs equipped{tradeoff}{detail}"
        return "Use from inventory"

    def item_build_tags(self, item: Item) -> set[str]:
        tags = {tag.lower() for tag in item.affix_tags}
        if item.damage_type and item.damage_type != "physical":
            tags.add(item.damage_type.lower())
        if item.proc_effect:
            tags.add(item.proc_effect.lower())
            tags.add("proc")
        if item.attack_speed:
            tags.add("attack_speed")
        if item.cast_speed:
            tags.add("cast_speed")
        if item.move_speed:
            tags.add("movement")
        if item.thorns:
            tags.add("thorns")
        if item.lifesteal:
            tags.add("lifesteal")
        skill_text = item.skill_bonus.lower()
        for keyword, tag in (
            ("bolt", "bolt"),
            ("nova", "nova"),
            ("dash", "dash"),
            ("melee", "melee"),
            ("blood", "blood"),
            ("ward", "ward"),
            ("guard", "guard"),
        ):
            if keyword in skill_text:
                tags.add(tag)
        return tags

    def player_build_tags(self) -> set[str]:
        tags = set(ARCHETYPE_BUILD_TAGS.get(self.player.class_name, ()))
        for key in self.player.skill_upgrades:
            node = discipline_by_key(key)
            if node is None:
                continue
            if node.path:
                tags.add(node.path.lower())
            tags.update(tag.lower() for tag in node.tags)
        return tags

    def item_build_relevance_hint(self, item: Item) -> str:
        if item.unidentified or item.slot not in ("weapon", "armor"):
            return ""
        item_tags = self.item_build_tags(item)
        if not item_tags:
            return ""
        matches = sorted(item_tags & self.player_build_tags())
        if matches:
            labels = [AFFIX_TAG_LABELS.get(tag, tag) for tag in matches[:2]]
            return f"Build: supports {'/'.join(labels)}"
        equipped = self.player.equipment.get(item.slot)
        current = 0
        incoming = item.power if item.slot == "weapon" else item.defense
        if equipped is not None:
            current = equipped.power if item.slot == "weapon" else equipped.defense
        if incoming >= current + (5 if item.slot == "weapon" else 3):
            return "Build: raw-stat upgrade"
        return "Build: off-path tech"

    def item_affix_tag_chips(self, item: Item) -> list[str]:
        """Ordered affix tags to render as procedural icon chips in the HUD."""
        if item.unidentified and item.slot in ("weapon", "armor"):
            return []
        # Surface damage-type and proc identity first so the chip row leads
        # with the most build-relevant signal, then sort the rest for stability.
        tags = self.item_build_tags(item)
        priority = []
        for preferred in (item.damage_type.lower(), item.proc_effect.lower(), "proc"):
            if preferred and preferred in tags and preferred not in priority:
                priority.append(preferred)
        rest = sorted(tags - set(priority))
        return (priority + rest)[:6]

    def item_affix_tooltip_lines(self, item: Item) -> list[str]:
        if item.unidentified and item.slot in ("weapon", "armor"):
            return ["Affixes hidden until identified."]
        lines: list[str] = []
        if item.affixes:
            lines.append(f"Affixes: {', '.join(item.affixes)}")
        stat_bits: list[str] = []
        if item.attack_speed:
            stat_bits.append(f"{item.attack_speed:+.0%} attack speed")
        if item.cast_speed:
            stat_bits.append(f"{item.cast_speed:+.0%} cast speed")
        if item.move_speed:
            stat_bits.append(f"{item.move_speed:+.0%} movement")
        if item.thorns:
            stat_bits.append(f"{item.thorns} thorns")
        if item.lifesteal:
            stat_bits.append(f"{item.lifesteal:.0%} lifesteal")
        if item.proc_effect:
            chance = (
                f" {int(round(item.proc_chance * 100))}%"
                if 0.0 < item.proc_chance < 1.0
                else ""
            )
            stat_bits.append(f"{item.proc_effect}{chance}")
        if stat_bits:
            lines.append("Stats: " + " · ".join(stat_bits))
        return lines

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
            "Legendary": 5,
            "Unidentified": 6,
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
        if self.mp_is_joiner():
            self.mp_queue_action("drop_slot", str(index))
            return
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
        if self.mp_is_joiner():
            self.mp_queue_action("use_slot", str(index))
            return
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
        if self.player.class_name == "Ranger":
            self._refresh_active_spirit_beast()
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

    def scroll_story_panel(self, delta: int) -> None:
        """4.2.2: scroll the quest info panel's story text by ``delta`` lines.

        The renderer publishes ``_story_panel_scroll_max`` for the current
        wrap/geometry each frame, so the offset is clamped against the last
        drawn panel; it re-clamps on draw when the text or window changes.
        """
        if not self.quest_info_visible:
            return
        maximum = max(0, int(getattr(self, "_story_panel_scroll_max", 0)))
        self.story_panel_scroll = max(
            0, min(int(self.story_panel_scroll) + delta, maximum)
        )

    def scroll_licenses(self, delta: int) -> None:
        """4.3.17 WS-G: scroll the About screen's Open Source Licenses text.

        The renderer publishes ``_licenses_scroll_max`` for the current wrap/
        geometry each frame, so the offset is clamped against the last drawn
        section and re-clamps on draw when the text or window changes.
        """

        maximum = max(0, int(getattr(self, "_licenses_scroll_max", 0)))
        self.licenses_scroll = max(
            0, min(int(self.licenses_scroll) + delta, maximum)
        )

    def toggle_quest_info_visibility(self) -> None:
        self.quest_info_visible = not self.quest_info_visible
        # 4.2.2: reopening the panel always starts from the top of the text.
        self.story_panel_scroll = 0
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
        if self.mp_is_joiner():
            self.mp_queue_action("potion_hp")
            return
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
        if self.mp_is_joiner():
            self.mp_queue_action("potion_mana")
            return
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
