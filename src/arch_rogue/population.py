# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

import math

from .constants import DUNGEON_DEPTH
from .content import (
    ARMOR_DEFINITIONS,
    ELITE_MODIFIERS,
    ENEMY_DEFINITIONS,
    FINAL_ROOM_ENEMY_DEFINITIONS,
    SECRET_TYPES,
    SHRINE_TYPES,
    TRAP_DEFINITIONS,
    WEAPON_DEFINITIONS,
    EnemyDefinition,
)
from .models import Color, Enemy, Item, Room, SecretCache, Shopkeeper, Shrine, Trap


class PopulationMixin:
    def _populate_dungeon(self) -> None:
        final_room_index = len(self.dungeon.rooms) - 1
        floor_plan = self.current_floor_plan()
        encounter = self.encounter_template_by_key(
            floor_plan.encounter_key if floor_plan is not None else "standard"
        )
        difficulty = self.difficulty_profile()
        enemy_pressure = self.story_effect_value("enemy_pressure", -0.35, 0.45)
        loot_bonus = self.story_effect_value("loot_bonus", -0.2, 0.35)
        trap_bonus = self.story_effect_value("trap_bonus", -0.1, 0.28)
        shrine_bonus = self.story_effect_value("shrine_bonus", -0.1, 0.28)
        secret_bonus = self.story_effect_value("secret_bonus", -0.1, 0.28)
        hunter_pressure = self.story_effect_value("hunter_pressure", 0.0, 0.35)
        for room_index, room in enumerate(self.dungeon.rooms[1:], start=1):
            is_final_room = room_index == final_room_index
            count = self.rng.randrange(1, 4)
            if self.current_depth <= 2:
                count = max(1, count - 1)
            elif self.current_depth >= 7:
                count += 1
            if enemy_pressure > 0 and self.rng.random() < enemy_pressure:
                count += 1
            elif enemy_pressure < 0 and self.rng.random() < abs(enemy_pressure):
                count = max(1, count - 1)
            if is_final_room:
                count += 1
            count = max(1, count + difficulty.enemy_count_bonus + encounter.enemy_bonus)
            if self.rng.random() < difficulty.enemy_extra_chance:
                count += 1
            for _ in range(count):
                self.enemies.append(
                    self._make_enemy(
                        *room.random_point(self.rng),
                        final_room=is_final_room,
                        elite_bonus=encounter.elite_bonus,
                    )
                )

            if is_final_room and floor_plan is not None and floor_plan.boss_key:
                bx, by = room.center
                if self.current_depth == DUNGEON_DEPTH:
                    self.enemies.append(self._make_boss(bx + 0.5, by + 0.5))
                else:
                    self.enemies.append(
                        self._make_floor_boss(floor_plan.boss_key, bx + 0.5, by + 0.5)
                    )

            loot_chance = max(
                0.12,
                min(
                    0.88,
                    0.68
                    + self.run_modifier.loot_bonus
                    + loot_bonus
                    + difficulty.loot_chance_bonus
                    + encounter.loot_bonus,
                ),
            )
            # Loot is twice as rare: halve the final spawn probability.
            loot_chance *= 0.5
            if self.rng.random() < loot_chance:
                self.items.append(self._make_loot(*room.random_point(self.rng)))
            if (
                room_index > 3
                and not is_final_room
                and self.rng.random() < self.miniboss_chance()
            ):
                mx, my = room.random_point(self.rng)
                self.enemies.append(self._make_miniboss(mx, my))
            if room_index > 1 and self.rng.random() < max(
                0.04,
                min(
                    0.70,
                    0.24
                    + self.run_modifier.trap_bonus
                    + trap_bonus
                    + difficulty.trap_chance_bonus
                    + encounter.trap_bonus,
                ),
            ):
                tx, ty = room.random_point(self.rng)
                kind, min_damage, max_damage = self.rng.choice(TRAP_DEFINITIONS)
                depth_damage = max(0, self.current_depth - 3)
                raw_damage = (
                    self.rng.randrange(min_damage, max_damage + 1) + depth_damage
                )
                self.traps.append(
                    Trap(
                        tx,
                        ty,
                        kind,
                        max(
                            1,
                            int(round(raw_damage * difficulty.trap_damage_multiplier)),
                        ),
                    )
                )
            shrine_chance = (
                0.18
                + (0.08 if self.run_modifier.name == "Trap-Laced" else 0.0)
                + shrine_bonus
                + difficulty.shrine_chance_bonus
            )
            if room_index > 2 and self.rng.random() < max(
                0.04, min(0.46, shrine_chance)
            ):
                sx, sy = room.random_point(self.rng)
                self.shrines.append(Shrine(sx, sy, self.rng.choice(SHRINE_TYPES)))
            if (
                room_index > 2
                and not is_final_room
                and self.rng.random()
                < max(
                    0.03,
                    min(
                        0.48,
                        0.16
                        + self.run_modifier.loot_bonus
                        + secret_bonus
                        + encounter.secret_bonus,
                    ),
                )
            ):
                cx, cy = room.random_point(self.rng)
                self.secrets.append(
                    SecretCache(
                        cx,
                        cy,
                        self.rng.choice(SECRET_TYPES),
                    )
                )

        if (
            encounter.guaranteed_miniboss
            and (floor_plan is None or not floor_plan.boss_key)
            and len(self.dungeon.rooms) > 3
        ):
            room = self.rng.choice(self.dungeon.rooms[2:-1] or self.dungeon.rooms[1:])
            mx, my = room.random_point(self.rng)
            miniboss = self._make_miniboss(mx, my)
            miniboss.role = "challenge_boss"
            miniboss.telegraph = (
                "optional challenge room guardian with guaranteed reward"
            )
            self.enemies.append(miniboss)

        if self.rng.random() < max(
            0.10,
            min(
                0.72,
                0.45
                + self.run_modifier.loot_bonus
                + secret_bonus
                + difficulty.loot_chance_bonus * 0.5,
            ),
        ):
            room = self.rng.choice(self.dungeon.rooms[2:-1])
            cx, cy = room.random_point(self.rng)
            self.secrets.append(SecretCache(cx, cy, "Lost Cartographer's Stash"))

        if hunter_pressure > 0 and len(self.dungeon.rooms) > 2:
            hunter_rooms = self.dungeon.rooms[2:-1] or self.dungeon.rooms[1:]
            hunter_count = min(4, 1 + int(hunter_pressure / 0.14))
            if self.rng.random() < min(0.75, hunter_pressure * 1.5):
                hunter_count += 1
            for _ in range(hunter_count):
                room = self.rng.choice(hunter_rooms)
                hx, hy = room.random_point(self.rng)
                self.enemies.append(self._make_story_hunter(hx, hy))

        sx, sy = self.dungeon.rooms[0].random_point(self.rng)
        self.items.append(
            Item("Minor Healing Potion", "potion", heal=35, rarity="Common", x=sx, y=sy)
        )
        self._populate_shop_room()
        self._populate_story_guest()

    def _populate_shop_room(self) -> None:
        shop_index = self.dungeon.shop_room_index
        if shop_index is None or not (0 <= shop_index < len(self.dungeon.rooms)):
            return
        room = self.dungeon.rooms[shop_index]
        keeper_names = (
            "Mirel Coin-Candle",
            "Old Brass Venn",
            "Sister Ledger",
            "Korrin the Barter-Saint",
            "Pell of the Locked Shelf",
        )
        x, y = room.center
        shopkeeper = Shopkeeper(
            x + 0.5,
            y + 0.5,
            self.rng.choice(keeper_names),
            "Allied Shopkeeper",
            inventory=self._make_shop_inventory(room),
        )
        self.shopkeepers.append(shopkeeper)
        # Shop rooms should feel like a temporary refuge rather than another ambush.
        self.enemies = [
            enemy
            for enemy in self.enemies
            if not (
                room.x <= enemy.x < room.x + room.w
                and room.y <= enemy.y < room.y + room.h
            )
        ]
        self.traps = [
            trap
            for trap in self.traps
            if not (
                room.x <= trap.x < room.x + room.w
                and room.y <= trap.y < room.y + room.h
            )
        ]
        self.items.append(
            Item(
                "Shop Sign: Press E to trade",
                "shop_sign",
                rarity="Common",
                x=shopkeeper.x + 0.9,
                y=shopkeeper.y,
            )
        )

    def _make_shop_inventory(self, room: Room) -> list[Item]:
        stock: list[Item] = [
            Item("Minor Healing Potion", "potion", heal=35, rarity="Common"),
            Item("Lesser Mana Potion", "mana_potion", mana=24, rarity="Common"),
            Item("Scroll of Identify", "identify", rarity="Common"),
        ]
        stock.append(
            self._make_equipment(
                "weapon", "Magic", room.center[0] + 0.5, room.center[1] + 0.5
            )
        )
        stock.append(
            self._make_equipment(
                "armor", "Magic", room.center[0] + 0.5, room.center[1] + 0.5
            )
        )
        if self.current_depth >= 3 or self.rng.random() < 0.35:
            stock.append(self._make_loot(room.center[0] + 0.5, room.center[1] + 0.5))
        for item in stock:
            item.x = 0.0
            item.y = 0.0
        return stock

    def _apply_run_modifier(self, enemy: Enemy) -> Enemy:
        difficulty = self.difficulty_profile()
        depth_multiplier = 1.0 + max(0, self.current_depth - 1) * 0.045
        story_pressure = self.story_effect_value("enemy_pressure", -0.25, 0.35)
        story_multiplier = 1.0 + max(-0.12, min(0.22, story_pressure * 0.55))
        if enemy.kind == "boss":
            story_multiplier += self.story_effect_value("boss_pressure", 0.0, 0.35)
        enemy.max_hp = max(
            1,
            int(
                enemy.max_hp
                * self.run_modifier.enemy_hp_multiplier
                * depth_multiplier
                * story_multiplier
                * difficulty.enemy_hp_multiplier
            ),
        )
        enemy.hp = enemy.max_hp
        damage = enemy.damage + self.run_modifier.enemy_damage_bonus
        damage += max(0, self.current_depth - 4) // 2
        if story_pressure > 0:
            damage += int(story_pressure * 8)
        if enemy.kind == "boss":
            damage += int(self.story_effect_value("boss_pressure", 0.0, 0.35) * 10)
        enemy.damage = max(
            1,
            int(round(damage * difficulty.enemy_damage_multiplier))
            + difficulty.enemy_damage_bonus,
        )
        enemy.speed *= difficulty.enemy_speed_multiplier
        enemy.attack_cooldown = max(
            0.35,
            enemy.attack_cooldown * difficulty.enemy_attack_cooldown_multiplier,
        )
        enemy.aggro_range += (
            self.run_modifier.enemy_aggro_bonus
            + max(0.0, story_pressure)
            + difficulty.enemy_aggro_bonus
        )
        return enemy

    def _weighted_enemy_definition(self, final_room: bool = False) -> EnemyDefinition:
        definitions = FINAL_ROOM_ENEMY_DEFINITIONS if final_room else ENEMY_DEFINITIONS
        total_weight = sum(definition.weight for definition in definitions)
        roll = self.rng.randrange(total_weight)
        current = 0
        for definition in definitions:
            current += definition.weight
            if roll < current:
                return definition
        return definitions[-1]

    def _make_enemy(
        self, x: float, y: float, final_room: bool = False, elite_bonus: float = 0.0
    ) -> Enemy:
        definition = self._weighted_enemy_definition(final_room)
        enemy = Enemy(
            definition.name,
            definition.kind,
            x,
            y,
            definition.max_hp,
            definition.max_hp,
            definition.speed,
            definition.damage,
            definition.xp,
            definition.attack_range,
            definition.attack_cooldown,
            aggro_range=definition.aggro_range,
            color=definition.color,
        )
        self._assign_enemy_combat_traits(enemy)
        enemy = self._apply_run_modifier(enemy)
        if enemy.kind != "boss" and self.rng.random() < self.elite_chance(elite_bonus):
            self._apply_elite_modifier(enemy)
        return enemy

    def _assign_enemy_combat_traits(self, enemy: Enemy) -> None:
        base_name = enemy.name
        for prefix in ("Venomous", "Runed", "Ironbound", "Frenzied", "Oathbound"):
            base_name = base_name.replace(f"{prefix} ", "")
        traits: dict[str, tuple[str, str, dict[str, float]]] = {
            "Cultist": ("caster", "arcane", {"arcane": 0.24, "shadow": 0.12}),
            "Bone Imp": ("skirmisher", "frost", {"frost": 0.22, "holy": -0.10}),
            "Venom Skitter": ("flanker", "poison", {"poison": 0.45, "fire": -0.18}),
            "Crypt Brute": ("bruiser", "physical", {"physical": 0.24, "arcane": -0.10}),
            "Ghoul": ("mauler", "shadow", {"shadow": 0.18, "holy": -0.15}),
            "Grave Archer": (
                "marksman",
                "physical",
                {"physical": 0.10, "poison": -0.08},
            ),
            "Ash Hound": ("flanker", "fire", {"fire": 0.34, "frost": -0.18}),
            "Rune Sentinel": ("sentinel", "arcane", {"arcane": 0.38, "physical": 0.10}),
            "Plague Toad": ("artillery", "poison", {"poison": 0.38, "fire": -0.12}),
            "Hollow Knight": ("guard", "physical", {"physical": 0.18, "shadow": 0.12}),
            "Gate Warden": (
                "guard",
                "holy",
                {"physical": 0.20, "holy": 0.28, "shadow": -0.12},
            ),
        }
        role, damage_type, resistances = traits.get(
            base_name, ("bruiser", "physical", {"physical": 0.08})
        )
        enemy.role = role
        enemy.damage_type = damage_type
        enemy.resistances = dict(resistances)

    def elite_chance(self, bonus: float = 0.0) -> float:
        difficulty = self.difficulty_profile()
        base = 0.06 + self.current_depth * 0.006 + difficulty.elite_bonus + bonus
        if self.run_modifier.name == "Elite Hunt":
            base += 0.08
        return max(0.0, min(0.55, base))

    def miniboss_chance(self) -> float:
        difficulty = self.difficulty_profile()
        base = 0.015 + self.current_depth * 0.006 + difficulty.miniboss_bonus
        if self.run_modifier.name == "Elite Hunt":
            base += 0.035
        return max(0.0, min(0.22, base))

    def _shift_color(self, color: Color, shift: Color) -> Color:
        return (
            max(35, min(255, color[0] + shift[0])),
            max(35, min(255, color[1] + shift[1])),
            max(35, min(255, color[2] + shift[2])),
        )

    def _apply_elite_modifier(self, enemy: Enemy) -> None:
        modifier = self.rng.choice(ELITE_MODIFIERS)
        enemy.name = f"{modifier.name} {enemy.name}"
        enemy.elite_modifier = modifier.name
        enemy.telegraph = modifier.description
        enemy.max_hp = max(1, int(enemy.max_hp * modifier.hp_multiplier))
        enemy.hp = enemy.max_hp
        enemy.damage += modifier.damage_bonus
        enemy.speed *= modifier.speed_multiplier
        enemy.xp += modifier.xp_bonus
        enemy.aggro_range += 1.0 if modifier.name == "Runed" else 0.0
        if modifier.name == "Venomous":
            enemy.damage_type = "poison"
            enemy.resistances["poison"] = max(
                enemy.resistances.get("poison", 0.0), 0.40
            )
            enemy.role = "flanker"
        elif modifier.name == "Runed":
            enemy.damage_type = "arcane"
            enemy.resistances["arcane"] = max(
                enemy.resistances.get("arcane", 0.0), 0.34
            )
        elif modifier.name == "Ironbound":
            enemy.resistances["physical"] = max(
                enemy.resistances.get("physical", 0.0), 0.32
            )
            enemy.role = "guard"
        elif modifier.name == "Frenzied":
            enemy.role = "flanker"
        enemy.color = self._shift_color(enemy.color, modifier.color_shift)

    def _make_miniboss(self, x: float, y: float) -> Enemy:
        enemy = self._make_enemy(x, y, final_room=True)
        enemy.name = f"Oathbound {enemy.name}"
        enemy.kind = "miniboss"
        enemy.elite_modifier = enemy.elite_modifier or "Oathbound"
        enemy.telegraph = "large readable windups and guaranteed reward"
        enemy.max_hp = int(enemy.max_hp * 1.85)
        enemy.hp = enemy.max_hp
        enemy.damage += 3
        enemy.xp += 34
        enemy.aggro_range += 2.0
        enemy.color = self.theme.accent
        return enemy

    def _make_floor_boss(self, boss_key: str, x: float, y: float) -> Enemy:
        definition = self.boss_definition_by_key(boss_key)
        if definition is None or definition.final_boss:
            return self._make_miniboss(x, y)
        name = definition.name
        if self.story_state is not None:
            name = f"{self.story_state.antagonist} {name}"
        boss = Enemy(
            name,
            "miniboss",
            x,
            y,
            definition.max_hp,
            definition.max_hp,
            definition.speed,
            definition.damage,
            definition.xp,
            definition.attack_range,
            definition.attack_cooldown,
            aggro_range=definition.aggro_range,
            color=definition.color,
            elite_modifier="Floor Boss",
            telegraph=definition.telegraph,
            role="floor_boss",
            damage_type=definition.damage_type,
            size=2,
            resistances={
                definition.damage_type: 0.45,
                "physical": 0.25,
                "holy" if definition.damage_type != "holy" else "shadow": -0.15,
            },
        )
        boss = self._apply_run_modifier(boss)
        # Floor bosses are now hulking 4-tile gatekeepers: far more HP, harder
        # hits, faster recovery, and longer reach so they control the room.
        boss.max_hp = int(boss.max_hp * 1.85)
        boss.hp = boss.max_hp
        boss.damage += 6
        boss.attack_cooldown = max(0.55, boss.attack_cooldown * 0.82)
        boss.attack_range = max(boss.attack_range, 1.85)
        boss.aggro_range += 3.0
        boss.speed = max(boss.speed, 1.05)
        return boss

    def _make_story_hunter(
        self, x: float, y: float, prefix: str | None = None
    ) -> Enemy:
        enemy = self._make_enemy(x, y, final_room=True)
        story_prefix = prefix or "Story-Marked"
        if self.story_state is not None and prefix is None:
            story_prefix = f"{self.story_state.antagonist} Hunter"
        enemy.name = f"{story_prefix} {enemy.name}"
        enemy.elite_modifier = enemy.elite_modifier or "Story-Marked"
        enemy.telegraph = "drawn by unresolved oaths and defiant story choices"
        enemy.max_hp = max(1, int(enemy.max_hp * 1.28))
        enemy.hp = enemy.max_hp
        enemy.damage += max(1, self.current_depth // 2)
        enemy.xp += 14 + self.current_depth * 2
        enemy.aggro_range += 2.5
        enemy.color = self.story_state.accent if self.story_state else self.theme.accent
        return enemy

    def _make_boss(self, x: float, y: float) -> Enemy:
        boss_titles = {
            "Crypt of Ash": "Ashen Gate Tyrant",
            "Fungal Catacombs": "Mycelial Gate Tyrant",
            "Violet Reliquary": "Voidbound Gate Tyrant",
            "Sunken Bastion": "Drowned Gate Tyrant",
            "Frozen Ossuary": "Rimebound Gate Tyrant",
            "Obsidian Foundry": "Forgeheart Gate Tyrant",
            "Moonlit Aquifer": "Moon-Drowned Gate Tyrant",
            "Thornbound Vault": "Thorn-Crowned Gate Tyrant",
        }
        definition = self.boss_definition_by_key("gate_tyrant")
        boss_name = boss_titles.get(self.theme.name, "Dread Gate Tyrant")
        if self.story_state is not None:
            boss_name = f"{self.story_state.antagonist} {boss_name}"
        base_hp = definition.max_hp if definition is not None else 245
        boss = Enemy(
            boss_name,
            "boss",
            x,
            y,
            base_hp,
            base_hp,
            definition.speed if definition is not None else 1.32,
            definition.damage if definition is not None else 21,
            definition.xp if definition is not None else 120,
            definition.attack_range if definition is not None else 1.45,
            definition.attack_cooldown if definition is not None else 1.08,
            aggro_range=definition.aggro_range if definition is not None else 13.0,
            color=self.theme.accent,
            telegraph=definition.telegraph if definition is not None else "gate strike",
            role="boss",
            damage_type="shadow"
            if self.theme.name in ("Violet Reliquary", "Thornbound Vault")
            else "physical",
            size=2,
            resistances={"physical": 0.30, "shadow": 0.34, "holy": -0.15},
        )
        boss = self._apply_run_modifier(boss)
        # Final boss is a towering 4-tile tyrant: roughly triple the old HP,
        # much heavier hits, faster cooldowns, longer reach, and full room aggro
        # so the climactic fight is a real gate-seal encounter.
        boss.max_hp = int(boss.max_hp * 2.4)
        boss.hp = boss.max_hp
        boss.damage += 9
        boss.attack_cooldown = max(0.6, boss.attack_cooldown * 0.8)
        boss.attack_range = max(boss.attack_range, 1.9)
        boss.aggro_range = 16.0
        boss.speed = max(boss.speed, 1.15)
        return boss

    def _make_loot(self, x: float, y: float) -> Item:
        roll = self.rng.random()
        if roll < 0.24:
            return Item(
                "Minor Healing Potion", "potion", heal=35, rarity="Common", x=x, y=y
            )
        if roll < 0.34:
            return Item(
                "Lesser Mana Potion", "mana_potion", mana=24, rarity="Common", x=x, y=y
            )
        if roll < 0.42:
            return Item("Scroll of Identify", "identify", rarity="Common", x=x, y=y)
        loot_bonus = self.run_modifier.loot_bonus + self.story_effect_value(
            "loot_bonus", 0.0, 0.25
        )
        if roll > 0.985 - loot_bonus * 0.5:
            slot = "weapon" if self.rng.random() < 0.58 else "armor"
            return self._make_equipment(slot, "Legendary", x, y)
        if roll > 0.96 - loot_bonus:
            return self._make_unique(x, y)
        slot = "weapon" if roll < 0.70 else "armor"
        rarity = "Rare" if self.rng.random() < 0.34 else "Magic"
        if self.rng.random() < 0.20:
            rarity = "Common"
        return self._make_equipment(slot, rarity, x, y)

    def _make_equipment(self, slot: str, rarity: str, x: float, y: float) -> Item:
        if slot == "weapon":
            definition = self.rng.choice(WEAPON_DEFINITIONS)
            item = Item(
                definition.name,
                "weapon",
                power=definition.value,
                rarity=rarity,
                x=x,
                y=y,
            )
        else:
            definition = self.rng.choice(ARMOR_DEFINITIONS)
            item = Item(
                definition.name,
                "armor",
                defense=definition.value,
                rarity=rarity,
                x=x,
                y=y,
            )
        affix_count = (
            0
            if rarity == "Common"
            else 1
            if rarity == "Magic"
            else 3
            if rarity == "Legendary"
            else 2
        )
        self._apply_affixes(item, affix_count)
        if rarity == "Legendary":
            if item.slot == "weapon":
                item.power += 4
                item.proc_effect = item.proc_effect or "ignite"
                item.damage_type = (
                    item.damage_type if item.damage_type != "physical" else "fire"
                )
            else:
                item.defense += 3
                item.skill_bonus = item.skill_bonus or "Dash guard"
        curse_chance = (
            0.08
            + (0.08 if self.run_modifier.name == "Cursed Bargains" else 0.0)
            + self.story_effect_value("curse_bonus", 0.0, 0.18)
        )
        if rarity != "Common" and self.rng.random() < curse_chance:
            item.cursed = True
            item.rarity = "Cursed"
            item.affixes.append("Tempting Curse")
            if item.slot == "weapon":
                item.power += 4
            else:
                item.defense += 3
        self._empower_story_relic_item(item)
        item.unidentified = rarity != "Common" and self.rng.random() < 0.45
        return item

    def _empower_story_relic_item(self, item: Item, guaranteed: bool = False) -> None:
        relic_power = self.story_effect_value("relic_power", 0.0, 0.35)
        if relic_power <= 0 or item.slot not in ("weapon", "armor"):
            return
        if "Relic-Touched" in item.affixes:
            return
        if not guaranteed and self.rng.random() > min(0.45, relic_power * 1.35):
            return
        bonus = max(2, int(round(2 + relic_power * 14)))
        if item.slot == "weapon":
            item.power += bonus
        else:
            item.defense += max(2, bonus // 2 + 1)
        if "Relic-Touched" not in item.affixes:
            item.affixes.append("Relic-Touched")
        if self.story_state is not None and not item.unique_effect:
            item.unique_effect = f"echo of {self.story_state.relic_name}"

    def _apply_affixes(self, item: Item, count: int) -> None:
        weapon_affixes = [
            ("Serrated", 3, 0),
            ("Cruel", 5, 0),
            ("Balanced", 2, 0),
            ("Frostbitten", 4, 0),
            ("Zealous", 3, 1),
            ("Vampiric", 4, 0),
            ("Storm-Touched", 5, 0),
        ]
        armor_affixes = [
            ("Reinforced", 0, 2),
            ("Stalwart", 0, 3),
            ("Light", 0, 1),
            ("Sealed", 0, 4),
            ("Thorned", 1, 2),
            ("Grounded", 0, 4),
            ("Regal", 1, 3),
        ]
        utility_affixes = [
            ("of the Fox", 1, 1),
            ("of Warding", 0, 2),
            ("of Force", 2, 0),
            ("of the Deep", 0, 3),
            ("of Ember", 3, 0),
            ("of Cinders", 4, -1),
            ("of the Moon", 1, 3),
        ]
        pool = weapon_affixes if item.slot == "weapon" else armor_affixes
        pool = pool + utility_affixes
        for name, power, defense in self.rng.sample(pool, k=min(count, len(pool))):
            item.affixes.append(name)
            item.power += power
            item.defense += defense
            if name in ("Frostbitten", "of the Moon"):
                item.damage_type = "frost"
                item.proc_effect = item.proc_effect or "chill"
            elif name in ("of Ember", "of Cinders"):
                item.damage_type = "fire"
                item.proc_effect = item.proc_effect or "ignite"
            elif name == "Storm-Touched":
                item.damage_type = "arcane"
                item.skill_bonus = item.skill_bonus or "Bolt +1 shard"
            elif name == "Vampiric":
                item.damage_type = "shadow"
                item.proc_effect = item.proc_effect or "lifesteal"
            elif name == "Thorned":
                item.proc_effect = item.proc_effect or "thorns"
            elif name in ("Grounded", "Sealed"):
                item.skill_bonus = item.skill_bonus or "Nova ward"
            elif name in ("Balanced", "Light", "of the Fox"):
                item.skill_bonus = item.skill_bonus or "Dash tempo"
            elif name in ("Zealous", "Regal", "of Force"):
                item.skill_bonus = item.skill_bonus or "Melee force"

    def _make_unique(self, x: float, y: float) -> Item:
        unique_roll = self.rng.random()
        if unique_roll < 0.42:
            return Item(
                "Emberbrand",
                "weapon",
                power=12,
                rarity="Unique",
                x=x,
                y=y,
                affixes=["Serrated", "of Force"],
                unidentified=self.rng.random() < 0.35,
                unique_effect="embers on hit",
                damage_type="fire",
                skill_bonus="Melee force",
                proc_effect="ignite",
            )
        if unique_roll < 0.72:
            return Item(
                "Frostwake",
                "weapon",
                power=10,
                rarity="Unique",
                x=x,
                y=y,
                affixes=["Frostbitten", "Balanced"],
                unidentified=self.rng.random() < 0.35,
                unique_effect="chill on hit",
                damage_type="frost",
                skill_bonus="Bolt +1 shard",
                proc_effect="chill",
            )
        return Item(
            "Bulwark of the First Gate",
            "armor",
            defense=8,
            rarity="Unique",
            x=x,
            y=y,
            affixes=["Reinforced", "of Warding"],
            unidentified=self.rng.random() < 0.35,
            unique_effect="steadfast bulwark",
            damage_type="holy",
            skill_bonus="Dash guard",
            proc_effect="thorns",
        )

    def drop_position_near(self, x: float, y: float) -> tuple[float, float]:
        offsets = (
            (0.0, 0.0),
            (1.15, 0.0),
            (-1.15, 0.0),
            (0.0, 1.15),
            (0.0, -1.15),
            (1.15, 1.15),
            (-1.15, 1.15),
            (1.15, -1.15),
            (-1.15, -1.15),
        )
        stair_x, stair_y = self.dungeon.stairs[0] + 0.5, self.dungeon.stairs[1] + 0.5
        for ox, oy in offsets:
            px, py = x + ox, y + oy
            if math.hypot(px - stair_x, py - stair_y) < 1.05:
                continue
            if not self.dungeon.blocked_for_radius(px, py, radius=0.22):
                return px, py
        return x, y
