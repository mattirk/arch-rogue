from __future__ import annotations

import math
import random
from typing import NamedTuple, cast

import pygame

from .dungeon import MAP_H, MAP_W, Dungeon
from .models import (
    Archetype,
    Color,
    DungeonTheme,
    Enemy,
    FloatingText,
    Item,
    Player,
    Projectile,
    RunModifier,
    RunStats,
    SecretCache,
    Shrine,
    Tile,
    Trap,
)
from .sprites import PixelSpriteAtlas

SCREEN_WIDTH = 2560
SCREEN_HEIGHT = 1440
FPS = 60
WORLD_SCALE = 2
TILE_W = 64 * WORLD_SCALE
TILE_H = 32 * WORLD_SCALE
MAX_INVENTORY = 9
DUNGEON_DEPTH = 10
UI_SCALE = 2
PLAYER_HIT_RADIUS = 0.42
ENEMY_HIT_RADIUS = 0.42
LARGE_ENEMY_HIT_RADIUS = 0.52
BOSS_HIT_RADIUS = 0.64
PLAYER_MELEE_RANGE = 1.55
PLAYER_MELEE_ARC_DOT = 0.05
PLAYER_PROJECTILE_HIT_RADIUS = 0.54
ENEMY_PROJECTILE_HIT_RADIUS = 0.52
WALK_ANIMATION_RATE = 0.8

SlashEffect = tuple[float, float, float, float, float]


class EnemyDefinition(NamedTuple):
    name: str
    kind: str
    max_hp: int
    speed: float
    damage: int
    xp: int
    attack_range: float
    attack_cooldown: float
    aggro_range: float
    color: Color
    weight: int


class EquipmentDefinition(NamedTuple):
    name: str
    slot: str
    value: int


ENEMY_DEFINITIONS = (
    EnemyDefinition(
        "Cultist", "ranged", 34, 2.0, 8, 18, 5.4, 1.45, 8.0, (125, 75, 170), 22
    ),
    EnemyDefinition(
        "Bone Imp", "ranged", 26, 3.0, 6, 16, 4.6, 1.0, 8.0, (190, 130, 215), 18
    ),
    EnemyDefinition(
        "Venom Skitter", "melee", 30, 3.6, 7, 15, 0.95, 0.72, 9.5, (110, 185, 95), 16
    ),
    EnemyDefinition(
        "Crypt Brute", "melee", 82, 1.75, 17, 32, 1.35, 1.35, 8.0, (155, 105, 74), 14
    ),
    EnemyDefinition(
        "Ghoul", "melee", 42, 2.7, 10, 20, 1.05, 0.95, 8.0, (160, 68, 68), 22
    ),
    EnemyDefinition(
        "Grave Archer", "ranged", 38, 2.25, 9, 21, 5.8, 1.35, 9.0, (120, 145, 105), 8
    ),
)

FINAL_ROOM_ENEMY_DEFINITIONS = ENEMY_DEFINITIONS + (
    EnemyDefinition(
        "Gate Warden", "melee", 72, 2.1, 14, 34, 1.2, 1.0, 8.0, (190, 92, 54), 24
    ),
)

WEAPON_DEFINITIONS = (
    EquipmentDefinition("Iron Sword", "weapon", 5),
    EquipmentDefinition("Hunter Axe", "weapon", 7),
    EquipmentDefinition("Runed Saber", "weapon", 6),
    EquipmentDefinition("Ash Pike", "weapon", 8),
    EquipmentDefinition("Grave Knife", "weapon", 4),
)

ARMOR_DEFINITIONS = (
    EquipmentDefinition("Leather Jerkin", "armor", 2),
    EquipmentDefinition("Warden Mail", "armor", 4),
    EquipmentDefinition("Chain Vest", "armor", 3),
    EquipmentDefinition("Boneweave Mantle", "armor", 3),
    EquipmentDefinition("Pilgrim's Plate", "armor", 5),
)

TRAP_DEFINITIONS = (
    ("Spike Trap", 14, 22),
    ("Rune Trap", 13, 21),
    ("Poison Needle", 10, 18),
)
SHRINE_TYPES = (
    "Mending Shrine",
    "Insight Shrine",
    "War Shrine",
    "Haste Shrine",
    "Fortune Shrine",
)
SECRET_TYPES = ("Hidden Cache", "Cursed Reliquary", "Sealed Armory")
HUMANOID_ENEMY_NAMES = (
    "Bone Imp",
    "Cultist",
    "Crypt Brute",
    "Gate Warden",
    "Ghoul",
    "Grave Archer",
)

ARCHETYPES = (
    Archetype(
        "Warden",
        "Durable melee fighter with reliable armor and stamina.",
        max_hp=120,
        max_mana=38,
        max_stamina=112,
        speed=4.45,
        melee_bonus=3,
        armor_bonus=2,
    ),
    Archetype(
        "Rogue",
        "Fast striker who trades durability for speed and burst damage.",
        max_hp=92,
        max_mana=42,
        max_stamina=126,
        speed=5.25,
        melee_bonus=5,
    ),
    Archetype(
        "Arcanist",
        "Fragile caster with stronger bolts and novas.",
        max_hp=86,
        max_mana=78,
        max_stamina=94,
        speed=4.35,
        spell_bonus=9,
    ),
    Archetype(
        "Acolyte",
        "Dark priest with balanced defenses and potent rites.",
        max_hp=102,
        max_mana=62,
        max_stamina=98,
        speed=4.4,
        melee_bonus=1,
        spell_bonus=5,
        armor_bonus=1,
    ),
    Archetype(
        "Ranger",
        "Mobile marksman with strong stamina and hybrid damage.",
        max_hp=98,
        max_mana=48,
        max_stamina=120,
        speed=4.95,
        melee_bonus=3,
        spell_bonus=2,
    ),
)

DUNGEON_THEMES = (
    DungeonTheme(
        "Crypt of Ash",
        "charred halls and emberlit stairs",
        floor=(52, 47, 42),
        floor_edge=(72, 66, 60),
        wall_top=(45, 42, 49),
        wall_left=(31, 29, 36),
        wall_right=(24, 23, 30),
        wall_edge=(58, 55, 66),
        stair=(230, 188, 90),
        accent=(240, 145, 65),
    ),
    DungeonTheme(
        "Fungal Catacombs",
        "damp stone, pale spores, and hidden growths",
        floor=(42, 53, 42),
        floor_edge=(65, 82, 59),
        wall_top=(34, 51, 45),
        wall_left=(24, 38, 34),
        wall_right=(20, 31, 32),
        wall_edge=(60, 84, 70),
        stair=(166, 210, 116),
        accent=(110, 185, 95),
    ),
    DungeonTheme(
        "Violet Reliquary",
        "occult vaults humming with void rites",
        floor=(45, 39, 58),
        floor_edge=(78, 65, 103),
        wall_top=(42, 34, 58),
        wall_left=(30, 24, 44),
        wall_right=(25, 20, 38),
        wall_edge=(76, 60, 112),
        stair=(205, 140, 235),
        accent=(160, 86, 230),
    ),
    DungeonTheme(
        "Sunken Bastion",
        "flood-stained battlements and drowned reliquaries",
        floor=(39, 52, 58),
        floor_edge=(60, 82, 92),
        wall_top=(36, 49, 55),
        wall_left=(25, 36, 43),
        wall_right=(20, 31, 38),
        wall_edge=(64, 88, 99),
        stair=(112, 190, 205),
        accent=(86, 188, 215),
    ),
    DungeonTheme(
        "Frozen Ossuary",
        "blue-lit bone vaults where frost silences footsteps",
        floor=(46, 53, 62),
        floor_edge=(76, 91, 110),
        wall_top=(43, 50, 63),
        wall_left=(30, 36, 48),
        wall_right=(24, 30, 42),
        wall_edge=(88, 107, 132),
        stair=(168, 215, 235),
        accent=(128, 206, 242),
    ),
)

RUN_MODIFIERS = (
    RunModifier(
        "Blood Moon",
        "Enemies are tougher and hit harder, but loot is richer.",
        1.18,
        2,
        1.0,
        0.07,
    ),
    RunModifier(
        "Restless Depths", "More enemies wake from farther away.", 1.08, 1, 2.0, 0.02
    ),
    RunModifier(
        "Treasure Draught",
        "The dungeon yields more equipment and rare caches.",
        1.0,
        0,
        0.0,
        0.14,
    ),
    RunModifier(
        "Trap-Laced",
        "Hazards are more common, but shrines answer more often.",
        1.0,
        0,
        0.5,
        0.05,
        0.16,
    ),
    RunModifier(
        "Thin Veil",
        "The tyrant's guard is alert, but hidden caches are easier to find.",
        1.06,
        1,
        1.0,
        0.08,
        0.04,
    ),
    RunModifier(
        "Starved Depths",
        "Loot is scarcer, but enemies are slightly weakened.",
        0.92,
        -1,
        -0.5,
        -0.08,
        0.0,
    ),
)


class Game:
    def __init__(
        self,
        screen_size: tuple[int, int] | None = None,
        headless: bool = False,
    ) -> None:
        pygame.init()
        pygame.display.set_caption("Arch Rogue - Prototype 3")
        if screen_size is None:
            display_info = pygame.display.Info()
            screen_size = (display_info.current_w, display_info.current_h)
        flags = pygame.HIDDEN if headless else pygame.NOFRAME
        self.screen = pygame.display.set_mode(screen_size, flags)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 24 * UI_SCALE)
        self.small_font = pygame.font.Font(None, 19 * UI_SCALE)
        self.big_font = pygame.font.Font(None, 56 * UI_SCALE)
        self.sprites = PixelSpriteAtlas()
        self.tile_cache: dict[
            tuple[str, int, int], tuple[pygame.Surface, int, int]
        ] = {}
        self.rng = random.Random()
        self.running = True
        self.inventory_open = False
        self.show_help = False
        self.run_stats = RunStats()
        self.state = "archetype_select"
        self.elapsed = 0.0
        self.selected_archetype = ARCHETYPES[0]
        self.theme = DUNGEON_THEMES[0]
        self.run_modifier = RUN_MODIFIERS[0]
        self.run_number = 0
        self.current_depth = 1

    def restart(self, archetype: Archetype | None = None) -> None:
        self.run_number += 1
        if archetype:
            self.selected_archetype = archetype
        self.current_depth = 1
        self.run_modifier = self.rng.choice(RUN_MODIFIERS)
        self.theme = self.rng.choice(DUNGEON_THEMES)
        self.tile_cache.clear()
        self.dungeon = Dungeon(self.rng)
        start_x, start_y = self.dungeon.rooms[0].center
        self.player = Player(
            start_x + 0.5,
            start_y + 0.5,
            class_name=self.selected_archetype.name,
            max_hp=self.selected_archetype.max_hp,
            hp=self.selected_archetype.max_hp,
            max_mana=self.selected_archetype.max_mana,
            mana=self.selected_archetype.max_mana,
            max_stamina=self.selected_archetype.max_stamina,
            stamina=self.selected_archetype.max_stamina,
            speed=self.selected_archetype.speed,
            melee_bonus=self.selected_archetype.melee_bonus,
            spell_bonus=self.selected_archetype.spell_bonus,
            armor_bonus=self.selected_archetype.armor_bonus,
        )
        self.enemies: list[Enemy] = []
        self.items: list[Item] = []
        self.projectiles: list[Projectile] = []
        self.traps: list[Trap] = []
        self.shrines: list[Shrine] = []
        self.secrets: list[SecretCache] = []
        self.floaters: list[FloatingText] = []
        self.slashes: list[SlashEffect] = []
        self.run_stats = RunStats()
        self.inventory_open = False
        self.show_help = False
        self.elapsed = 0.0
        self.state = "playing"
        self._populate_dungeon()

    def descend_to_next_depth(self) -> None:
        if self.current_depth >= DUNGEON_DEPTH:
            self.state = "victory"
            return
        self.current_depth += 1
        self.theme = self.rng.choice(DUNGEON_THEMES)
        self.tile_cache.clear()
        self.dungeon = Dungeon(self.rng)
        start_x, start_y = self.dungeon.rooms[0].center
        self.player.x = start_x + 0.5
        self.player.y = start_y + 0.5
        self.player.melee_timer = 0.0
        self.player.bolt_timer = 0.0
        self.player.dash_timer = 0.0
        self.player.nova_timer = 0.0
        self.player.stamina = min(
            self.player.max_stamina,
            self.player.stamina + self.player.max_stamina * 0.25,
        )
        self.player.mana = min(
            self.player.max_mana, self.player.mana + self.player.max_mana * 0.25
        )
        self.enemies = []
        self.items = []
        self.projectiles = []
        self.traps = []
        self.shrines = []
        self.secrets = []
        self.floaters = []
        self.slashes = []
        self.inventory_open = False
        self.show_help = False
        self._populate_dungeon()
        self.floaters.append(
            FloatingText(
                f"Depth {self.current_depth}/{DUNGEON_DEPTH}",
                self.player.x,
                self.player.y - 0.5,
                self.theme.accent,
                ttl=1.5,
            )
        )

    def _populate_dungeon(self) -> None:
        final_room_index = len(self.dungeon.rooms) - 1
        for room_index, room in enumerate(self.dungeon.rooms[1:], start=1):
            is_final_room = room_index == final_room_index
            count = self.rng.randrange(1, 4)
            if is_final_room:
                count += 1
            for _ in range(count):
                self.enemies.append(
                    self._make_enemy(
                        *room.random_point(self.rng), final_room=is_final_room
                    )
                )

            if is_final_room and self.current_depth == DUNGEON_DEPTH:
                bx, by = room.center
                self.enemies.append(self._make_boss(bx + 0.5, by + 0.5))

            if self.rng.random() < max(0.25, 0.68 + self.run_modifier.loot_bonus):
                self.items.append(self._make_loot(*room.random_point(self.rng)))
            if (
                room_index > 1
                and self.rng.random() < 0.24 + self.run_modifier.trap_bonus
            ):
                tx, ty = room.random_point(self.rng)
                kind, min_damage, max_damage = self.rng.choice(TRAP_DEFINITIONS)
                self.traps.append(
                    Trap(tx, ty, kind, self.rng.randrange(min_damage, max_damage + 1))
                )
            shrine_chance = 0.18 + (
                0.08 if self.run_modifier.name == "Trap-Laced" else 0.0
            )
            if room_index > 2 and self.rng.random() < shrine_chance:
                sx, sy = room.random_point(self.rng)
                self.shrines.append(Shrine(sx, sy, self.rng.choice(SHRINE_TYPES)))
            if (
                room_index > 2
                and not is_final_room
                and self.rng.random() < 0.16 + self.run_modifier.loot_bonus
            ):
                cx, cy = room.random_point(self.rng)
                self.secrets.append(
                    SecretCache(
                        cx,
                        cy,
                        self.rng.choice(SECRET_TYPES),
                    )
                )

        if self.rng.random() < 0.45 + self.run_modifier.loot_bonus:
            room = self.rng.choice(self.dungeon.rooms[2:-1])
            cx, cy = room.random_point(self.rng)
            self.secrets.append(SecretCache(cx, cy, "Lost Cartographer's Stash"))

        sx, sy = self.dungeon.rooms[0].random_point(self.rng)
        self.items.append(
            Item("Minor Healing Potion", "potion", heal=35, rarity="Common", x=sx, y=sy)
        )

    def _apply_run_modifier(self, enemy: Enemy) -> Enemy:
        enemy.max_hp = max(1, int(enemy.max_hp * self.run_modifier.enemy_hp_multiplier))
        enemy.hp = enemy.max_hp
        enemy.damage += self.run_modifier.enemy_damage_bonus
        enemy.aggro_range += self.run_modifier.enemy_aggro_bonus
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

    def _make_enemy(self, x: float, y: float, final_room: bool = False) -> Enemy:
        definition = self._weighted_enemy_definition(final_room)
        return self._apply_run_modifier(
            Enemy(
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
        )

    def _make_boss(self, x: float, y: float) -> Enemy:
        boss_titles = {
            "Crypt of Ash": "Ashen Gate Tyrant",
            "Fungal Catacombs": "Mycelial Gate Tyrant",
            "Violet Reliquary": "Voidbound Gate Tyrant",
            "Sunken Bastion": "Drowned Gate Tyrant",
            "Frozen Ossuary": "Rimebound Gate Tyrant",
        }
        return self._apply_run_modifier(
            Enemy(
                boss_titles.get(self.theme.name, "Dread Gate Tyrant"),
                "boss",
                x,
                y,
                210,
                210,
                1.65,
                18,
                90,
                1.45,
                1.15,
                aggro_range=12.0,
                color=self.theme.accent,
            )
        )

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
        if roll > 0.96 - self.run_modifier.loot_bonus:
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
        self._apply_affixes(
            item, 0 if rarity == "Common" else 1 if rarity == "Magic" else 2
        )
        item.unidentified = rarity != "Common" and self.rng.random() < 0.45
        return item

    def _apply_affixes(self, item: Item, count: int) -> None:
        weapon_affixes = [
            ("Serrated", 3, 0),
            ("Cruel", 5, 0),
            ("Balanced", 2, 0),
            ("Frostbitten", 4, 0),
            ("Zealous", 3, 1),
        ]
        armor_affixes = [
            ("Reinforced", 0, 2),
            ("Stalwart", 0, 3),
            ("Light", 0, 1),
            ("Sealed", 0, 4),
            ("Thorned", 1, 2),
        ]
        utility_affixes = [
            ("of the Fox", 1, 1),
            ("of Warding", 0, 2),
            ("of Force", 2, 0),
            ("of the Deep", 0, 3),
            ("of Ember", 3, 0),
        ]
        pool = weapon_affixes if item.slot == "weapon" else armor_affixes
        pool = pool + utility_affixes
        for name, power, defense in self.rng.sample(pool, k=min(count, len(pool))):
            item.affixes.append(name)
            item.power += power
            item.defense += defense

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
        )

    def run(self) -> None:
        while self.running:
            dt = min(self.clock.tick(FPS) / 1000.0, 0.05)
            self.handle_events()
            if self.state == "playing":
                self.update(dt)
            self.draw()
        pygame.quit()

    def handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif self.state == "archetype_select":
                    select_limit = min(len(ARCHETYPES), 9)
                    if pygame.K_1 <= event.key < pygame.K_1 + select_limit:
                        self.restart(ARCHETYPES[event.key - pygame.K_1])
                    elif event.key in (pygame.K_RIGHT, pygame.K_DOWN):
                        index = (ARCHETYPES.index(self.selected_archetype) + 1) % len(
                            ARCHETYPES
                        )
                        self.selected_archetype = ARCHETYPES[index]
                    elif event.key in (pygame.K_LEFT, pygame.K_UP):
                        index = (ARCHETYPES.index(self.selected_archetype) - 1) % len(
                            ARCHETYPES
                        )
                        self.selected_archetype = ARCHETYPES[index]
                    elif event.key == pygame.K_RETURN:
                        self.restart(self.selected_archetype)
                elif (
                    event.key in (pygame.K_h, pygame.K_SLASH)
                    and self.state != "archetype_select"
                ):
                    self.show_help = not self.show_help
                elif event.key == pygame.K_i and self.state == "playing":
                    self.inventory_open = not self.inventory_open
                elif event.key == pygame.K_r and self.state != "playing":
                    self.show_help = False
                    self.inventory_open = False
                    self.state = "archetype_select"
                elif event.key == pygame.K_e and self.state == "playing":
                    self.interact()
                elif event.key == pygame.K_q and self.state == "playing":
                    self.use_first_potion()
                elif event.key == pygame.K_SPACE and self.state == "playing":
                    self.update_player_aim()
                    self.player_melee_attack()
                elif event.key == pygame.K_f and self.state == "playing":
                    self.update_player_aim()
                    self.player_cast_bolt()
                elif event.key == pygame.K_c and self.state == "playing":
                    self.player_cast_nova()
                elif (
                    event.key in (pygame.K_LSHIFT, pygame.K_RSHIFT)
                    and self.state == "playing"
                ):
                    self.update_player_aim()
                    self.player_dash()
                elif pygame.K_1 <= event.key <= pygame.K_9 and self.state == "playing":
                    self.use_inventory_slot(event.key - pygame.K_1)
            elif event.type == pygame.MOUSEBUTTONDOWN and self.state == "playing":
                if event.button == 1:
                    self.face_player_toward_screen_point(*event.pos)
                    if self.enemy_in_melee_arc():
                        self.player_melee_attack()

    def update(self, dt: float) -> None:
        self.elapsed += dt
        self.update_player_aim()
        self.update_player(dt)
        self.update_enemies(dt)
        self.update_projectiles(dt)
        self.update_traps(dt)
        self.update_secrets()
        self.update_floaters(dt)
        self.slashes = [
            (x, y, ttl - dt, dx, dy)
            for x, y, ttl, dx, dy in self.slashes
            if ttl - dt > 0
        ]

        if self.player.hp <= 0:
            self.state = "dead"

    def update_player_aim(self) -> None:
        keys = pygame.key.get_pressed()
        dx = float(keys[pygame.K_RIGHT]) - float(keys[pygame.K_LEFT])
        dy = float(keys[pygame.K_DOWN]) - float(keys[pygame.K_UP])
        if dx or dy:
            length = math.hypot(dx, dy)
            self.player.facing_x = dx / length
            self.player.facing_y = dy / length
        else:
            self.face_player_toward_screen_point(*pygame.mouse.get_pos())

    def face_player_toward_screen_point(self, sx: int, sy: int) -> tuple[float, float]:
        target_x, target_y = self.screen_to_world(sx, sy)
        dx = target_x - self.player.x
        dy = target_y - self.player.y
        distance = math.hypot(dx, dy)
        if distance > 0.05:
            self.player.facing_x = dx / distance
            self.player.facing_y = dy / distance
        return dx, dy

    def update_player(self, dt: float) -> None:
        self.player.moving = False
        if pygame.mouse.get_pressed()[0]:
            dx, dy = self.face_player_toward_screen_point(*pygame.mouse.get_pos())
            distance = math.hypot(dx, dy)
            if distance > 0.18:
                self.move_actor(
                    self.player,
                    (dx / distance) * self.player.speed * dt,
                    (dy / distance) * self.player.speed * dt,
                )
            if self.enemy_in_melee_arc():
                self.player_melee_attack()

        self.player.melee_timer = max(0.0, self.player.melee_timer - dt)
        self.player.bolt_timer = max(0.0, self.player.bolt_timer - dt)
        self.player.dash_timer = max(0.0, self.player.dash_timer - dt)
        self.player.nova_timer = max(0.0, self.player.nova_timer - dt)
        self.player.stamina = min(
            self.player.max_stamina, self.player.stamina + 30 * dt
        )
        self.player.mana = min(self.player.max_mana, self.player.mana + 5 * dt)

    def move_actor(self, actor: Player | Enemy, dx: float, dy: float) -> None:
        old_x, old_y = actor.x, actor.y
        new_x = actor.x + dx
        if not self.dungeon.blocked_for_radius(new_x, actor.y):
            actor.x = new_x
        new_y = actor.y + dy
        if not self.dungeon.blocked_for_radius(actor.x, new_y):
            actor.y = new_y
        self.resolve_actor_contacts(actor)

        actual_dx = actor.x - old_x
        actual_dy = actor.y - old_y
        distance = math.hypot(actual_dx, actual_dy)
        if distance > 0.0001:
            actor.moving = True
            target_x = actual_dx / distance
            target_y = actual_dy / distance
            blend = 0.38
            smoothed_x = actor.move_x * (1.0 - blend) + target_x * blend
            smoothed_y = actor.move_y * (1.0 - blend) + target_y * blend
            smoothed_length = math.hypot(smoothed_x, smoothed_y)
            if smoothed_length > 0.001:
                actor.move_x = smoothed_x / smoothed_length
                actor.move_y = smoothed_y / smoothed_length
            else:
                actor.move_x = target_x
                actor.move_y = target_y
            actor.anim_time += distance * WALK_ANIMATION_RATE

    def actor_hit_radius(self, actor: Player | Enemy) -> float:
        if isinstance(actor, Player):
            return PLAYER_HIT_RADIUS
        return self.enemy_hit_radius(actor)

    def enemy_hit_radius(self, enemy: Enemy) -> float:
        if enemy.kind == "boss":
            return BOSS_HIT_RADIUS
        if enemy.name in ("Gate Warden", "Crypt Brute"):
            return LARGE_ENEMY_HIT_RADIUS
        return ENEMY_HIT_RADIUS

    def contact_distance(self, enemy: Enemy) -> float:
        return PLAYER_HIT_RADIUS + self.enemy_hit_radius(enemy)

    def resolve_actor_contacts(self, actor: Player | Enemy) -> None:
        others: list[Player | Enemy]
        if isinstance(actor, Player):
            others = list(self.enemies)
        else:
            others = [
                self.player,
                *(enemy for enemy in self.enemies if enemy is not actor),
            ]

        for other in others:
            dx = actor.x - other.x
            dy = actor.y - other.y
            distance = math.hypot(dx, dy)
            min_distance = self.actor_hit_radius(actor) + self.actor_hit_radius(other)
            if distance >= min_distance:
                continue

            if distance > 0.001:
                nx, ny = dx / distance, dy / distance
            else:
                nx, ny = -actor.facing_x, -actor.facing_y
                if math.hypot(nx, ny) <= 0.001:
                    nx, ny = 1.0, 0.0

            target_x = other.x + nx * min_distance
            target_y = other.y + ny * min_distance
            if not self.dungeon.blocked_for_radius(target_x, actor.y):
                actor.x = target_x
            if not self.dungeon.blocked_for_radius(actor.x, target_y):
                actor.y = target_y

    def update_enemies(self, dt: float) -> None:
        for enemy in self.enemies:
            enemy.moving = False
            enemy.attack_timer = max(0.0, enemy.attack_timer - dt)
            dx = self.player.x - enemy.x
            dy = self.player.y - enemy.y
            distance = math.hypot(dx, dy)
            if distance > enemy.aggro_range:
                continue
            nx, ny = (dx / distance, dy / distance) if distance > 0.001 else (0.0, 0.0)
            if distance > 0.001:
                enemy.facing_x = nx
                enemy.facing_y = ny

            if enemy.kind == "boss":
                if distance > enemy.attack_range:
                    self.move_actor(enemy, nx * enemy.speed * dt, ny * enemy.speed * dt)
                if 2.0 < distance <= 6.0 and enemy.attack_timer <= 0:
                    self.enemy_cast(enemy, nx, ny)
                elif distance <= enemy.attack_range and enemy.attack_timer <= 0:
                    self.enemy_melee(enemy)
            elif enemy.kind == "ranged":
                if 3.5 < distance:
                    self.move_actor(enemy, nx * enemy.speed * dt, ny * enemy.speed * dt)
                elif distance < 2.5:
                    self.move_actor(
                        enemy, -nx * enemy.speed * dt, -ny * enemy.speed * dt
                    )
                if distance <= enemy.attack_range and enemy.attack_timer <= 0:
                    self.enemy_cast(enemy, nx, ny)
            else:
                if distance > enemy.attack_range:
                    self.move_actor(enemy, nx * enemy.speed * dt, ny * enemy.speed * dt)
                elif enemy.attack_timer <= 0:
                    self.enemy_melee(enemy)

    def enemy_melee(self, enemy: Enemy) -> None:
        enemy.attack_timer = enemy.attack_cooldown
        raw = enemy.damage + self.rng.randrange(-2, 3)
        amount = max(1, raw - self.player.armor())
        self.player.hp -= amount
        self.run_stats.damage_taken += amount
        self.floaters.append(
            FloatingText(
                f"-{amount}", self.player.x, self.player.y - 0.2, (235, 90, 80)
            )
        )
        self.slashes.append(
            (
                (enemy.x + self.player.x) * 0.5,
                (enemy.y + self.player.y) * 0.5,
                0.14,
                enemy.facing_x,
                enemy.facing_y,
            )
        )

    def enemy_cast(self, enemy: Enemy, nx: float, ny: float) -> None:
        enemy.attack_timer = enemy.attack_cooldown
        self.projectiles.append(
            Projectile(
                enemy.x,
                enemy.y,
                nx * 6.0,
                ny * 6.0,
                enemy.damage,
                "enemy",
                (180, 80, 220),
                ttl=1.8,
            )
        )

    def update_projectiles(self, dt: float) -> None:
        kept: list[Projectile] = []
        for projectile in self.projectiles:
            if not projectile.update(dt, self.dungeon):
                continue
            if projectile.owner == "player":
                hit = self.first_enemy_near(
                    projectile.x, projectile.y, PLAYER_PROJECTILE_HIT_RADIUS
                )
                if hit:
                    self.damage_enemy(
                        hit,
                        projectile.damage,
                        knockback_from=(projectile.vx, projectile.vy),
                    )
                    continue
            else:
                if (
                    math.hypot(
                        projectile.x - self.player.x, projectile.y - self.player.y
                    )
                    < ENEMY_PROJECTILE_HIT_RADIUS
                ):
                    amount = max(1, projectile.damage - self.player.armor())
                    self.player.hp -= amount
                    self.run_stats.damage_taken += amount
                    self.floaters.append(
                        FloatingText(
                            f"-{amount}",
                            self.player.x,
                            self.player.y - 0.2,
                            (235, 90, 80),
                        )
                    )
                    continue
            kept.append(projectile)
        self.projectiles = kept

    def update_traps(self, _dt: float) -> None:
        for trap in self.traps:
            if not trap.active:
                continue
            if math.hypot(trap.x - self.player.x, trap.y - self.player.y) > 0.55:
                continue
            trap.active = False
            amount = max(1, trap.damage - self.player.armor())
            self.player.hp -= amount
            self.run_stats.traps_triggered += 1
            self.run_stats.damage_taken += amount
            self.floaters.append(
                FloatingText(
                    f"{trap.kind}! -{amount}",
                    self.player.x,
                    self.player.y - 0.2,
                    (245, 95, 70),
                    ttl=1.2,
                )
            )

    def update_secrets(self) -> None:
        for secret in self.secrets:
            if secret.revealed or secret.opened:
                continue
            if math.hypot(secret.x - self.player.x, secret.y - self.player.y) < 1.55:
                secret.revealed = True
                self.floaters.append(
                    FloatingText(
                        "Secret found",
                        secret.x,
                        secret.y - 0.3,
                        self.theme.accent,
                        ttl=1.2,
                    )
                )

    def update_floaters(self, dt: float) -> None:
        for floater in self.floaters:
            floater.update(dt)
        self.floaters = [floater for floater in self.floaters if floater.ttl > 0]

    def player_melee_attack(self) -> None:
        if self.player.melee_timer > 0 or self.player.stamina < 12:
            return
        self.player.melee_timer = 0.36
        self.player.stamina -= 12
        target = self.enemy_in_melee_arc()
        if target:
            tx = (self.player.x + target.x) * 0.5
            ty = (self.player.y + target.y) * 0.5
        else:
            tx = self.player.x + self.player.facing_x * 0.9
            ty = self.player.y + self.player.facing_y * 0.9
        self.slashes.append((tx, ty, 0.18, self.player.facing_x, self.player.facing_y))
        if target:
            damage = self.player.melee_damage() + self.rng.randrange(-3, 5)
            self.damage_enemy(
                target,
                damage,
                knockback_from=(self.player.facing_x, self.player.facing_y),
            )

    def player_cast_bolt(self) -> None:
        if self.player.bolt_timer > 0 or self.player.mana < 10:
            return
        self.player.bolt_timer = 0.48
        self.player.mana -= 10
        self.projectiles.append(
            Projectile(
                self.player.x,
                self.player.y,
                self.player.facing_x * 9.0,
                self.player.facing_y * 9.0,
                14 + self.player.level * 2 + self.player.spell_bonus,
                "player",
                (70, 165, 255),
                ttl=1.4,
            )
        )

    def player_cast_nova(self) -> None:
        if self.player.nova_timer > 0 or self.player.mana < 18:
            return
        self.player.nova_timer = 3.2
        self.player.mana -= 18
        hits = 0
        for enemy in list(self.enemies):
            dx = enemy.x - self.player.x
            dy = enemy.y - self.player.y
            distance = math.hypot(dx, dy)
            if distance <= 2.45:
                hits += 1
                damage = (
                    10
                    + self.player.level * 2
                    + self.player.spell_bonus
                    + self.rng.randrange(0, 5)
                )
                direction = (
                    (dx / distance, dy / distance)
                    if distance > 0.001
                    else (self.player.facing_x, self.player.facing_y)
                )
                self.damage_enemy(enemy, damage, knockback_from=direction)
        self.floaters.append(
            FloatingText(
                f"Arc Nova{f' x{hits}' if hits else ''}",
                self.player.x,
                self.player.y - 0.5,
                (120, 210, 255),
                ttl=0.9,
            )
        )
        for angle in (0.0, math.pi / 2, math.pi, math.pi * 1.5):
            self.slashes.append(
                (
                    self.player.x + math.cos(angle) * 0.9,
                    self.player.y + math.sin(angle) * 0.9,
                    0.18,
                    math.cos(angle),
                    math.sin(angle),
                )
            )

    def player_dash(self) -> None:
        if self.player.dash_timer > 0 or self.player.stamina < 18:
            return
        self.player.dash_timer = 0.85
        self.player.stamina -= 18
        for _ in range(8):
            self.move_actor(
                self.player,
                self.player.facing_x * 0.20,
                self.player.facing_y * 0.20,
            )
        self.floaters.append(
            FloatingText(
                "Dash", self.player.x, self.player.y - 0.4, (235, 210, 120), ttl=0.45
            )
        )

    def enemy_in_melee_arc(self) -> Enemy | None:
        best: Enemy | None = None
        best_distance = 999.0
        for enemy in self.enemies:
            dx = enemy.x - self.player.x
            dy = enemy.y - self.player.y
            distance = math.hypot(dx, dy)
            if distance > PLAYER_MELEE_RANGE or distance < 0.001:
                continue
            dot = (dx / distance) * self.player.facing_x + (
                dy / distance
            ) * self.player.facing_y
            if dot > PLAYER_MELEE_ARC_DOT and distance < best_distance:
                best = enemy
                best_distance = distance
        return best

    def first_enemy_near(self, x: float, y: float, radius: float) -> Enemy | None:
        for enemy in self.enemies:
            hit_radius = radius + self.enemy_hit_radius(enemy) - ENEMY_HIT_RADIUS
            if math.hypot(enemy.x - x, enemy.y - y) <= hit_radius:
                return enemy
        return None

    def damage_enemy(
        self, enemy: Enemy, amount: int, knockback_from: tuple[float, float]
    ) -> None:
        enemy.hp -= amount
        self.floaters.append(
            FloatingText(f"-{amount}", enemy.x, enemy.y - 0.2, (255, 210, 120))
        )
        kx, ky = knockback_from
        length = math.hypot(kx, ky)
        if length > 0.001:
            self.move_actor(enemy, (kx / length) * 0.16, (ky / length) * 0.16)
        if enemy.hp <= 0:
            self.kill_enemy(enemy)

    def kill_enemy(self, enemy: Enemy) -> None:
        if enemy not in self.enemies:
            return
        self.enemies.remove(enemy)
        self.run_stats.kills += 1
        if enemy.kind == "boss":
            self.run_stats.boss_killed = True
            drop_x, drop_y = self.drop_position_near(enemy.x, enemy.y)
            self.items.append(self._make_unique(drop_x, drop_y))
            self.floaters.append(
                FloatingText(
                    "Gate seal broken",
                    enemy.x,
                    enemy.y - 0.5,
                    self.theme.accent,
                    ttl=1.6,
                )
            )
        if self.player.gain_xp(enemy.xp):
            self.floaters.append(
                FloatingText(
                    "LEVEL UP",
                    self.player.x,
                    self.player.y - 0.6,
                    (120, 230, 150),
                    ttl=1.4,
                )
            )
        if self.rng.random() < 0.45:
            drop_x, drop_y = self.drop_position_near(enemy.x, enemy.y)
            self.items.append(self._make_loot(drop_x, drop_y))

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

    def player_near_stairs(self) -> bool:
        return (
            math.hypot(
                self.player.x - self.dungeon.stairs[0] - 0.5,
                self.player.y - self.dungeon.stairs[1] - 0.5,
            )
            < 1.0
        )

    def interact(self) -> None:
        if self.player_near_stairs():
            if self.current_depth < DUNGEON_DEPTH:
                self.descend_to_next_depth()
                return
            if self.boss_alive():
                self.floaters.append(
                    FloatingText(
                        "The gate is sealed by its tyrant",
                        self.player.x,
                        self.player.y - 0.5,
                        self.theme.accent,
                        ttl=1.2,
                    )
                )
                return
            self.state = "victory"
            return
        secret = self.nearby_secret()
        if secret:
            self.open_secret(secret)
            return
        shrine = self.nearby_shrine()
        if shrine:
            self.activate_shrine(shrine)
            return
        nearest = self.nearby_item()
        if nearest:
            if len(self.player.inventory) >= MAX_INVENTORY:
                self.floaters.append(
                    FloatingText(
                        "Inventory full",
                        self.player.x,
                        self.player.y - 0.4,
                        (235, 210, 120),
                    )
                )
                return
            self.items.remove(nearest)
            self.player.inventory.append(nearest)
            self.run_stats.loot_picked_up += 1
            self.floaters.append(
                FloatingText(
                    f"Picked up {nearest.display_name}",
                    self.player.x,
                    self.player.y - 0.4,
                    (210, 230, 180),
                    ttl=1.2,
                )
            )

    def nearby_item(self) -> Item | None:
        nearby = [
            item
            for item in self.items
            if math.hypot(item.x - self.player.x, item.y - self.player.y) < 1.0
        ]
        return min(
            nearby,
            key=lambda item: math.hypot(item.x - self.player.x, item.y - self.player.y),
            default=None,
        )

    def nearby_secret(self) -> SecretCache | None:
        nearby = [
            secret
            for secret in self.secrets
            if secret.revealed
            and not secret.opened
            and math.hypot(secret.x - self.player.x, secret.y - self.player.y) < 1.1
        ]
        return min(
            nearby,
            key=lambda secret: math.hypot(
                secret.x - self.player.x, secret.y - self.player.y
            ),
            default=None,
        )

    def open_secret(self, secret: SecretCache) -> None:
        secret.opened = True
        self.run_stats.secrets_opened += 1
        if secret.kind == "Cursed Reliquary" and self.rng.random() < 0.55:
            self.enemies.append(self._make_enemy(secret.x + 0.3, secret.y + 0.3))
            message = "Reliquary wakes a guardian"
        else:
            drops = 2 if "Stash" in secret.kind or secret.kind == "Sealed Armory" else 1
            for _ in range(drops):
                if secret.kind == "Sealed Armory":
                    self.items.append(
                        self._make_equipment(
                            self.rng.choice(("weapon", "armor")),
                            "Magic",
                            secret.x,
                            secret.y,
                        )
                    )
                else:
                    self.items.append(self._make_loot(secret.x, secret.y))
            message = f"Opened {secret.kind}"
        self.floaters.append(
            FloatingText(message, secret.x, secret.y - 0.3, self.theme.accent, ttl=1.4)
        )

    def boss_alive(self) -> bool:
        return any(enemy.kind == "boss" for enemy in self.enemies)

    def boss_enemy(self) -> Enemy | None:
        return next((enemy for enemy in self.enemies if enemy.kind == "boss"), None)

    def nearby_shrine(self) -> Shrine | None:
        nearby = [
            shrine
            for shrine in self.shrines
            if not shrine.used
            and math.hypot(shrine.x - self.player.x, shrine.y - self.player.y) < 1.15
        ]
        return min(
            nearby,
            key=lambda shrine: math.hypot(
                shrine.x - self.player.x, shrine.y - self.player.y
            ),
            default=None,
        )

    def activate_shrine(self, shrine: Shrine) -> None:
        shrine.used = True
        self.run_stats.shrines_used += 1
        if shrine.kind == "Mending Shrine":
            self.player.hp = self.player.max_hp
            self.player.mana = self.player.max_mana
            message = "Shrine restored you"
        elif shrine.kind == "Insight Shrine":
            identified = self.identify_all_items()
            message = (
                f"Shrine revealed {identified} item{'s' if identified != 1 else ''}"
            )
        elif shrine.kind == "War Shrine":
            leveled = self.player.gain_xp(25)
            self.player.stamina = self.player.max_stamina
            message = "War Shrine grants focus"
            if leveled:
                message = "War Shrine grants a level"
        elif shrine.kind == "Haste Shrine":
            self.player.stamina = self.player.max_stamina
            self.player.dash_timer = 0.0
            self.player.speed += 0.18
            message = "Haste Shrine quickens your stride"
        else:
            self.items.append(self._make_loot(self.player.x, self.player.y))
            self.items.append(
                self._make_loot(self.player.x + 0.25, self.player.y + 0.25)
            )
            message = "Fortune Shrine spills offerings"
        self.floaters.append(
            FloatingText(
                message, self.player.x, self.player.y - 0.5, (245, 215, 120), ttl=1.3
            )
        )

    def use_inventory_slot(self, index: int) -> None:
        if index >= len(self.player.inventory):
            return
        item = self.player.inventory.pop(index)
        if item.slot == "potion":
            self.drink_potion(item)
            return
        if item.slot == "mana_potion":
            self.drink_mana_potion(item)
            return
        if item.slot == "identify":
            self.identify_first_item()
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

    def use_first_potion(self) -> None:
        for index, item in enumerate(self.player.inventory):
            if item.slot == "potion":
                _ = self.player.inventory.pop(index)
                self.drink_potion(item)
                return
        self.floaters.append(
            FloatingText(
                "No potion", self.player.x, self.player.y - 0.4, (235, 210, 120)
            )
        )

    def drink_potion(self, item: Item) -> None:
        self.run_stats.potions_used += 1
        old_hp = self.player.hp
        self.player.hp = min(self.player.max_hp, self.player.hp + item.heal)
        healed = self.player.hp - old_hp
        self.floaters.append(
            FloatingText(
                f"+{healed}", self.player.x, self.player.y - 0.4, (105, 230, 125)
            )
        )

    def drink_mana_potion(self, item: Item) -> None:
        self.run_stats.potions_used += 1
        old_mana = self.player.mana
        self.player.mana = min(self.player.max_mana, self.player.mana + item.mana)
        restored = int(self.player.mana - old_mana)
        self.floaters.append(
            FloatingText(
                f"+{restored} mana", self.player.x, self.player.y - 0.4, (105, 165, 255)
            )
        )

    def identify_first_item(self) -> None:
        for item in self.player.inventory:
            if item.unidentified:
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

    def world_to_iso(self, x: float, y: float) -> tuple[float, float]:
        return (x - y) * TILE_W / 2, (x + y) * TILE_H / 2

    def camera_iso(self) -> tuple[float, float]:
        return self.world_to_iso(self.player.x, self.player.y)

    def world_to_screen(self, x: float, y: float) -> tuple[int, int]:
        iso_x, iso_y = self.world_to_iso(x, y)
        cam_x, cam_y = self.camera_iso()
        width, height = self.screen.get_size()
        return int(iso_x - cam_x + width * 0.5), int(iso_y - cam_y + height * 0.48)

    def screen_to_world(self, sx: int, sy: int) -> tuple[float, float]:
        cam_x, cam_y = self.camera_iso()
        width, height = self.screen.get_size()
        iso_x = sx - width * 0.5 + cam_x
        iso_y = sy - height * 0.48 + cam_y
        x = iso_y / TILE_H + iso_x / TILE_W
        y = iso_y / TILE_H - iso_x / TILE_W
        return x, y

    def visible_bounds(self) -> tuple[int, int, int, int]:
        radius = 22
        min_x = max(0, int(self.player.x) - radius)
        max_x = min(MAP_W - 1, int(self.player.x) + radius)
        min_y = max(0, int(self.player.y) - radius)
        max_y = min(MAP_H - 1, int(self.player.y) + radius)
        return min_x, max_x, min_y, max_y

    def draw(self) -> None:
        self.screen.fill((10, 10, 14))
        if self.state == "archetype_select":
            self.draw_archetype_select()
            pygame.display.flip()
            return
        self.draw_dungeon()
        self.draw_world_objects()
        self.draw_ui()
        if self.inventory_open:
            self.draw_inventory()
        if self.show_help:
            self.draw_help_overlay()
        if self.state != "playing":
            self.draw_state_overlay()
        pygame.display.flip()

    def draw_dungeon(self) -> None:
        min_x, max_x, min_y, max_y = self.visible_bounds()
        for s in range(min_x + min_y, max_x + max_y + 1):
            for x in range(min_x, max_x + 1):
                y = s - x
                if min_y <= y <= max_y and self.dungeon.in_bounds(x, y):
                    self.draw_tile(x, y, self.dungeon.tiles[x][y])

    def draw_tile(self, x: int, y: int, tile: Tile) -> None:
        sx, sy = self.world_to_screen(x + 0.5, y + 0.5)
        seed = self.tile_seed(x, y)
        surface, anchor_x, anchor_y = self.tile_surface(tile, seed)
        self.screen.blit(surface, (sx - anchor_x, sy - anchor_y))

    def tile_seed(self, x: int, y: int) -> int:
        return (x * 1103515245 + y * 12345) & 31

    def shade(self, color: Color, amount: int) -> Color:
        return (
            max(0, min(255, color[0] + amount)),
            max(0, min(255, color[1] + amount)),
            max(0, min(255, color[2] + amount)),
        )

    def mix(self, a: Color, b: Color, ratio: float) -> Color:
        return (
            int(a[0] * (1.0 - ratio) + b[0] * ratio),
            int(a[1] * (1.0 - ratio) + b[1] * ratio),
            int(a[2] * (1.0 - ratio) + b[2] * ratio),
        )

    def tile_surface(self, tile: Tile, seed: int) -> tuple[pygame.Surface, int, int]:
        key = (self.theme.name, int(tile), seed)
        cached = self.tile_cache.get(key)
        if cached:
            return cached

        margin = 4 * WORLD_SCALE
        wall_h = 48 * WORLD_SCALE if tile == Tile.WALL else 0
        width = TILE_W + margin * 2
        height = TILE_H + wall_h + margin * 2
        surface = pygame.Surface((width, height), pygame.SRCALPHA)
        anchor_x = width // 2
        anchor_y = margin + wall_h + TILE_H // 2
        sx, sy = anchor_x, anchor_y
        top = (sx, sy - TILE_H // 2)
        right = (sx + TILE_W // 2, sy)
        bottom = (sx, sy + TILE_H // 2)
        left = (sx - TILE_W // 2, sy)

        if tile == Tile.WALL:
            self.draw_wall_tile_surface(
                surface, sx, sy, top, right, bottom, left, wall_h, seed
            )
        else:
            self.draw_floor_tile_surface(
                surface, sx, sy, top, right, bottom, left, tile, seed
            )

        cached = (surface.convert_alpha(), anchor_x, anchor_y)
        self.tile_cache[key] = cached
        return cached

    def draw_wall_tile_surface(
        self,
        surface: pygame.Surface,
        sx: int,
        sy: int,
        top: tuple[int, int],
        right: tuple[int, int],
        bottom: tuple[int, int],
        left: tuple[int, int],
        wall_h: int,
        seed: int,
    ) -> None:
        cap_top = (top[0], top[1] - wall_h)
        cap_right = (right[0], right[1] - wall_h)
        cap_bottom = (bottom[0], bottom[1] - wall_h)
        cap_left = (left[0], left[1] - wall_h)

        top_color = self.shade(self.theme.wall_top, 10 + seed % 7)
        left_color = self.shade(self.theme.wall_left, -4)
        right_color = self.shade(self.theme.wall_right, -20)
        edge_color = self.shade(self.theme.wall_edge, 8)
        mortar = self.mix(edge_color, (210, 205, 190), 0.18)
        crack = self.shade(self.theme.wall_right, -32)
        moss = self.mix(self.theme.accent, (35, 70, 43), 0.55)

        # The tile diamond is the floor-plane footprint. Draw the wall upward from
        # that footprint so actors read as moving between walls, not on top of them.
        pygame.draw.polygon(surface, left_color, [cap_left, cap_bottom, bottom, left])
        pygame.draw.polygon(
            surface, right_color, [cap_right, cap_bottom, bottom, right]
        )
        pygame.draw.polygon(
            surface, top_color, [cap_top, cap_right, cap_bottom, cap_left]
        )

        pygame.draw.lines(
            surface,
            edge_color,
            True,
            [cap_top, cap_right, cap_bottom, cap_left],
            WORLD_SCALE,
        )
        pygame.draw.line(
            surface, self.shade(edge_color, -12), cap_left, left, WORLD_SCALE
        )
        pygame.draw.line(
            surface, self.shade(edge_color, -28), cap_right, right, WORLD_SCALE
        )
        pygame.draw.line(
            surface, self.shade(edge_color, -48), cap_bottom, bottom, WORLD_SCALE
        )
        pygame.draw.line(
            surface, self.shade(edge_color, -42), left, bottom, WORLD_SCALE
        )
        pygame.draw.line(
            surface, self.shade(edge_color, -54), bottom, right, WORLD_SCALE
        )

        # Top cap seams stay high above the walking plane, avoiding the roof illusion.
        pygame.draw.line(
            surface,
            mortar,
            (sx - 28 * WORLD_SCALE, cap_bottom[1] - 5 * WORLD_SCALE),
            (sx + 2 * WORLD_SCALE, cap_top[1] + 12 * WORLD_SCALE),
            max(1, WORLD_SCALE),
        )
        pygame.draw.line(
            surface,
            mortar,
            (sx - 2 * WORLD_SCALE, cap_top[1] + 12 * WORLD_SCALE),
            (sx + 30 * WORLD_SCALE, cap_bottom[1] - 4 * WORLD_SCALE),
            max(1, WORLD_SCALE),
        )

        # Face courses descend from the raised cap to the floor footprint.
        face_start = cap_bottom[1] + 18 * WORLD_SCALE
        for row, offset in enumerate((0, 28, 56)):
            y_face = face_start + offset * WORLD_SCALE
            if y_face >= bottom[1] - 4 * WORLD_SCALE:
                continue
            pygame.draw.line(
                surface,
                self.shade(mortar, -28),
                (sx - 29 * WORLD_SCALE, y_face),
                (sx, y_face + 14 * WORLD_SCALE),
                max(1, WORLD_SCALE),
            )
            pygame.draw.line(
                surface,
                self.shade(mortar, -40),
                (sx, y_face + 14 * WORLD_SCALE),
                (sx + 29 * WORLD_SCALE, y_face),
                max(1, WORLD_SCALE),
            )
            joint = (-19 if (seed + row) & 1 else -8) * WORLD_SCALE
            pygame.draw.line(
                surface,
                self.shade(mortar, -34),
                (sx + joint, y_face - 8 * WORLD_SCALE),
                (sx + joint + 9 * WORLD_SCALE, y_face - 3 * WORLD_SCALE),
                max(1, WORLD_SCALE),
            )
            joint = (13 if (seed + row) & 2 else 23) * WORLD_SCALE
            pygame.draw.line(
                surface,
                self.shade(mortar, -44),
                (sx + joint, y_face - 2 * WORLD_SCALE),
                (sx + joint - 9 * WORLD_SCALE, y_face + 3 * WORLD_SCALE),
                max(1, WORLD_SCALE),
            )

        if seed & 3:
            pygame.draw.line(
                surface,
                crack,
                (sx + (8 - seed % 14) * WORLD_SCALE, cap_bottom[1] + 22 * WORLD_SCALE),
                (sx + (2 - seed % 10) * WORLD_SCALE, cap_bottom[1] + 48 * WORLD_SCALE),
                max(1, WORLD_SCALE),
            )
        if 8 <= seed <= 15 or seed > 27:
            pygame.draw.rect(
                surface,
                moss,
                (
                    sx - 27 * WORLD_SCALE,
                    bottom[1] - 8 * WORLD_SCALE,
                    (5 + seed % 5) * WORLD_SCALE,
                    2 * WORLD_SCALE,
                ),
            )

    def draw_floor_tile_surface(
        self,
        surface: pygame.Surface,
        sx: int,
        sy: int,
        top: tuple[int, int],
        right: tuple[int, int],
        bottom: tuple[int, int],
        left: tuple[int, int],
        tile: Tile,
        seed: int,
    ) -> None:
        is_stairs = tile == Tile.STAIRS
        base = self.theme.stair if is_stairs else self.theme.floor
        edge = self.theme.accent if is_stairs else self.theme.floor_edge
        slab_color = self.shade(base, (seed % 7) - 3)
        inner_edge = self.shade(edge, -18)
        groove = self.shade(base, -24)
        highlight = self.shade(base, 20)
        pebble = self.mix(edge, base, 0.45)

        pygame.draw.polygon(surface, slab_color, [top, right, bottom, left])
        pygame.draw.lines(surface, edge, True, [top, right, bottom, left], WORLD_SCALE)

        inset_top = (sx, sy - 20 * WORLD_SCALE)
        inset_right = (sx + 40 * WORLD_SCALE, sy)
        inset_bottom = (sx, sy + 20 * WORLD_SCALE)
        inset_left = (sx - 40 * WORLD_SCALE, sy)
        pygame.draw.lines(
            surface,
            inner_edge,
            True,
            [inset_top, inset_right, inset_bottom, inset_left],
            max(1, WORLD_SCALE),
        )
        pygame.draw.line(
            surface,
            groove,
            (sx - 28 * WORLD_SCALE, sy - 6 * WORLD_SCALE),
            (sx + 6 * WORLD_SCALE, sy + 11 * WORLD_SCALE),
            max(1, WORLD_SCALE),
        )
        pygame.draw.line(
            surface,
            self.shade(groove, 8),
            (sx - 2 * WORLD_SCALE, sy - 15 * WORLD_SCALE),
            (sx + 29 * WORLD_SCALE, sy + 1 * WORLD_SCALE),
            max(1, WORLD_SCALE),
        )
        pygame.draw.line(
            surface,
            highlight,
            (sx - 32 * WORLD_SCALE, sy - 2 * WORLD_SCALE),
            (sx - 13 * WORLD_SCALE, sy - 11 * WORLD_SCALE),
            max(1, WORLD_SCALE),
        )

        for index in range(2):
            px = sx + (((seed >> (index * 2)) & 15) - 7) * 5 * WORLD_SCALE
            py = sy + (((seed >> (index + 1)) & 7) - 3) * 4 * WORLD_SCALE
            pygame.draw.rect(
                surface,
                self.shade(pebble, -8 + index * 10),
                (px, py, max(1, 2 * WORLD_SCALE), max(1, WORLD_SCALE)),
            )

        if is_stairs:
            for step, width in ((-2, 18), (5, 12), (12, 6)):
                pygame.draw.line(
                    surface,
                    self.theme.stair,
                    (sx - width * WORLD_SCALE, sy + step * WORLD_SCALE),
                    (sx + width * WORLD_SCALE, sy + step * WORLD_SCALE),
                    3 * WORLD_SCALE,
                )
            pygame.draw.line(
                surface,
                self.theme.accent,
                (sx - 20 * WORLD_SCALE, sy - 8 * WORLD_SCALE),
                (sx + 20 * WORLD_SCALE, sy - 8 * WORLD_SCALE),
                WORLD_SCALE,
            )
            pygame.draw.circle(
                surface,
                self.theme.accent,
                (sx, sy - 16 * WORLD_SCALE),
                max(2, 2 * WORLD_SCALE),
            )

    def draw_world_objects(self) -> None:
        drawables: list[tuple[float, str, object]] = []
        for item in self.items:
            drawables.append((item.x + item.y, "item", item))
        for trap in self.traps:
            drawables.append((trap.x + trap.y - 0.02, "trap", trap))
        for shrine in self.shrines:
            drawables.append((shrine.x + shrine.y, "shrine", shrine))
        for secret in self.secrets:
            if secret.revealed and not secret.opened:
                drawables.append((secret.x + secret.y, "secret", secret))
        for projectile in self.projectiles:
            drawables.append((projectile.x + projectile.y, "projectile", projectile))
        for enemy in self.enemies:
            drawables.append((enemy.x + enemy.y, "enemy", enemy))
        drawables.append((self.player.x + self.player.y, "player", self.player))
        for slash in self.slashes:
            x, y, _ttl, _dx, _dy = slash
            drawables.append((x + y + 0.05, "slash", slash))

        self.draw_aim_cone()

        for _depth, kind, obj in sorted(drawables, key=lambda entry: entry[0]):
            if kind == "item":
                self.draw_item(cast(Item, obj))
            elif kind == "trap":
                self.draw_trap(cast(Trap, obj))
            elif kind == "shrine":
                self.draw_shrine(cast(Shrine, obj))
            elif kind == "secret":
                self.draw_secret(cast(SecretCache, obj))
            elif kind == "projectile":
                self.draw_projectile(cast(Projectile, obj))
            elif kind == "enemy":
                self.draw_enemy(cast(Enemy, obj))
            elif kind == "player":
                self.draw_player(cast(Player, obj))
            elif kind == "slash":
                self.draw_slash(cast(SlashEffect, obj))

        for floater in self.floaters:
            sx, sy = self.world_to_screen(floater.x, floater.y)
            alpha = max(0, min(255, int(255 * floater.ttl)))
            surface = self.font.render(floater.text, True, floater.color)
            surface.set_alpha(alpha)
            self.screen.blit(
                surface, surface.get_rect(center=(sx, sy - 34 * WORLD_SCALE))
            )

    def draw_shadow(
        self,
        x: float,
        y: float,
        width: int,
        height: int,
        moving: bool = False,
        lift: float = 0.0,
    ) -> None:
        sx, sy = self.world_to_screen(x, y)
        pulse = 0.5 + 0.5 * math.sin(self.elapsed * 12.0)
        squash = pulse * 1.4 if moving else 0.0
        scaled_w = max(1, round((width + squash * 3 + lift) * WORLD_SCALE))
        scaled_h = max(1, round((height - squash - lift * 0.32) * WORLD_SCALE))
        shadow = pygame.Surface((scaled_w, scaled_h), pygame.SRCALPHA)
        alpha = 92 if moving else 78
        pygame.draw.ellipse(shadow, (0, 0, 0, alpha), shadow.get_rect())
        pygame.draw.ellipse(
            shadow,
            (0, 0, 0, alpha // 2),
            shadow.get_rect().inflate(-scaled_w // 4, -scaled_h // 3),
        )
        self.screen.blit(
            shadow,
            shadow.get_rect(center=(sx, sy + 10 * WORLD_SCALE)),
        )

    def walk_offsets(self, actor: Player | Enemy) -> tuple[int, int]:
        sway, bob, _lean, _stretch = self.actor_animation(actor)
        return round(sway), round(bob)

    def actor_animation(
        self, actor: Player | Enemy
    ) -> tuple[float, float, float, float]:
        if actor.moving:
            phase = actor.anim_time * math.tau
            footfall = 0.5 - 0.5 * math.cos(phase * 2.0)
            stride = math.sin(phase)
            bob = 0.8 + footfall * 2.4
            sway = stride * 1.45
            forward_lean = 1.25 if actor.speed >= 3.0 else 0.85
            lean = forward_lean + math.sin(phase - 0.35) * 0.35
            stretch = 1.0 + footfall * 0.012
            return sway, bob, lean, stretch
        idle = math.sin(self.elapsed * 2.2 + actor.x * 0.7 + actor.y * 0.4)
        return 0.0, idle * 0.8, idle * 0.35, 1.0

    def iso_screen_direction(self, dx: float, dy: float) -> tuple[float, float]:
        screen_dx = (dx - dy) * TILE_W / 2
        screen_dy = (dx + dy) * TILE_H / 2
        length = math.hypot(screen_dx, screen_dy)
        if length <= 0.001:
            return 1.0, 0.0
        return screen_dx / length, screen_dy / length

    def draw_movement_trail(
        self, actor: Player | Enemy, color: Color, size: int = 2
    ) -> None:
        if not actor.moving:
            return
        sx, sy = self.world_to_screen(actor.x, actor.y)
        vx, vy = self.iso_screen_direction(actor.move_x, actor.move_y)
        phase = abs(math.sin(actor.anim_time * math.tau))
        px_perp = -vy
        for step, alpha in ((1, 92), (2, 58), (3, 30)):
            offset = math.sin(actor.anim_time * math.tau + step) * 3 * WORLD_SCALE
            px = sx - int(vx * (7 + step * 8) * WORLD_SCALE + px_perp * offset)
            py = sy + int(8 * WORLD_SCALE) - int(vy * (3 + step * 5) * WORLD_SCALE)
            dust = pygame.Surface(
                (size * (5 + step) * WORLD_SCALE, size * 2 * WORLD_SCALE),
                pygame.SRCALPHA,
            )
            pygame.draw.ellipse(
                dust,
                (*color, int(alpha * (0.55 + phase * 0.45))),
                dust.get_rect(),
            )
            pygame.draw.rect(
                dust,
                (*self.shade(color, 35), max(18, alpha // 3)),
                dust.get_rect().inflate(
                    -dust.get_width() // 2, -dust.get_height() // 2
                ),
            )
            self.screen.blit(dust, dust.get_rect(center=(px, py)))

    def is_humanoid(self, actor: Player | Enemy) -> bool:
        if isinstance(actor, Player):
            return True
        return actor.kind == "boss" or actor.name in HUMANOID_ENEMY_NAMES

    def humanoid_run_scale(self, actor: Player | Enemy) -> float:
        if isinstance(actor, Player):
            return 1.0
        if actor.kind == "boss":
            return 1.24
        if actor.name in ("Gate Warden", "Crypt Brute"):
            return 1.12
        if actor.name == "Bone Imp":
            return 0.82
        return 0.96

    def humanoid_limb_palette(
        self, actor: Player | Enemy, hostile: bool = False
    ) -> tuple[Color, Color, Color, Color]:
        if isinstance(actor, Player):
            return (44, 75, 132), (154, 168, 178), (74, 48, 39), (19, 24, 35)
        if actor.kind == "boss":
            return (
                self.theme.accent,
                self.shade(self.theme.accent, 35),
                (50, 34, 45),
                (28, 18, 24),
            )
        palettes: dict[str, tuple[Color, Color, Color, Color]] = {
            "Cultist": ((78, 44, 132), (184, 138, 218), (38, 28, 54), (22, 18, 33)),
            "Grave Archer": ((86, 116, 72), (145, 164, 98), (58, 43, 31), (26, 31, 25)),
            "Gate Warden": (
                (171, 105, 48),
                (126, 132, 128),
                (58, 46, 43),
                (29, 23, 22),
            ),
            "Crypt Brute": (
                (155, 105, 74),
                (126, 132, 128),
                (58, 46, 43),
                (29, 23, 22),
            ),
            "Bone Imp": ((150, 92, 180), (210, 160, 230), (64, 42, 76), (30, 22, 36)),
            "Ghoul": ((118, 154, 94), (161, 189, 116), (72, 55, 47), (31, 20, 22)),
        }
        return palettes.get(
            actor.name,
            ((135, 80, 76), (180, 110, 92), (64, 42, 38), (28, 20, 22))
            if hostile
            else ((90, 90, 110), (135, 135, 150), (55, 45, 50), (25, 25, 30)),
        )

    def draw_jointed_limb(
        self,
        points: tuple[tuple[float, float], tuple[float, float], tuple[float, float]],
        color: Color,
        outline: Color,
        width: int,
        alpha: int = 255,
    ) -> None:
        rounded_points = tuple((round(x), round(y)) for x, y in points)
        surface = self.screen
        min_x = 0
        min_y = 0
        if alpha < 255:
            min_x = min(point[0] for point in rounded_points) - width * 3
            min_y = min(point[1] for point in rounded_points) - width * 3
            max_x = max(point[0] for point in rounded_points) + width * 3
            max_y = max(point[1] for point in rounded_points) + width * 3
            surface = pygame.Surface((max_x - min_x, max_y - min_y), pygame.SRCALPHA)
            rounded_points = tuple((x - min_x, y - min_y) for x, y in rounded_points)
        pygame.draw.lines(
            surface, outline, False, rounded_points, width + max(1, WORLD_SCALE)
        )
        pygame.draw.lines(surface, color, False, rounded_points, width)
        for point in rounded_points:
            pygame.draw.circle(surface, color, point, max(1, width // 2))
        if surface is not self.screen:
            surface.set_alpha(alpha)
            self.screen.blit(surface, (min_x, min_y))

    def draw_humanoid_run_layer(
        self,
        actor: Player | Enemy,
        anchor_x: float,
        anchor_bottom: float,
        layer: str,
        hostile: bool = False,
    ) -> None:
        if not self.is_humanoid(actor):
            return
        scale = WORLD_SCALE * self.humanoid_run_scale(actor)
        vx, vy = self.iso_screen_direction(actor.move_x, actor.move_y)
        px, py = -vy, vx
        phase = actor.anim_time * math.tau
        moving_amount = 1.0 if actor.moving else 0.12
        torso_color, limb_color, boot_color, outline = self.humanoid_limb_palette(
            actor, hostile
        )
        if layer == "back":
            torso_color = self.shade(torso_color, -32)
            limb_color = self.shade(limb_color, -30)
            boot_color = self.shade(boot_color, -26)
            alpha = 210
        else:
            alpha = 255

        hip_y = anchor_bottom - 18.0 * scale
        shoulder_y = anchor_bottom - 39.0 * scale
        hip_width = 4.6 * scale
        shoulder_width = 5.4 * scale
        stride = 12.0 * scale * moving_amount
        arm_stride = 9.5 * scale * moving_amount
        leg_len = 17.5 * scale
        arm_len = 14.0 * scale
        line_w = max(2, round(2.2 * scale))

        torso_top = (anchor_x + vx * 2.0 * scale, shoulder_y)
        torso_bottom = (anchor_x - vx * 1.5 * scale, hip_y)
        if layer == "back":
            pygame.draw.line(
                self.screen,
                outline,
                (round(torso_top[0]), round(torso_top[1])),
                (round(torso_bottom[0]), round(torso_bottom[1])),
                line_w + WORLD_SCALE,
            )
            pygame.draw.line(
                self.screen,
                self.shade(torso_color, -18),
                (round(torso_top[0]), round(torso_top[1])),
                (round(torso_bottom[0]), round(torso_bottom[1])),
                line_w,
            )

        for side in (-1, 1):
            side_is_front_layer = side > 0
            if (layer == "front") != side_is_front_layer:
                continue
            phase_offset = 0.0 if side > 0 else math.pi
            leg_swing = math.sin(phase + phase_offset)
            lift = (
                (0.5 - 0.5 * math.cos(phase + phase_offset))
                * 4.5
                * scale
                * moving_amount
            )
            knee_bend = lift * 0.7 + abs(leg_swing) * 1.3 * scale * moving_amount
            hip = (
                anchor_x + px * side * hip_width,
                hip_y + py * side * hip_width * 0.25,
            )
            knee = (
                hip[0] + vx * leg_swing * stride * 0.46 + px * side * 1.7 * scale,
                hip[1]
                + leg_len * 0.48
                + vy * leg_swing * stride * 0.16
                - knee_bend * 0.38,
            )
            foot = (
                hip[0] + vx * leg_swing * stride + px * side * 2.8 * scale,
                hip[1] + leg_len + vy * leg_swing * stride * 0.26 - lift,
            )
            self.draw_jointed_limb(
                (hip, knee, foot), limb_color, outline, line_w, alpha
            )
            foot_tip = (foot[0] + vx * 4.2 * scale, foot[1] + vy * 1.8 * scale)
            pygame.draw.line(
                self.screen,
                outline,
                (round(foot[0]), round(foot[1])),
                (round(foot_tip[0]), round(foot_tip[1])),
                line_w + WORLD_SCALE,
            )
            pygame.draw.line(
                self.screen,
                boot_color,
                (round(foot[0]), round(foot[1])),
                (round(foot_tip[0]), round(foot_tip[1])),
                line_w,
            )

        for side in (-1, 1):
            side_is_front_layer = side > 0
            if (layer == "front") != side_is_front_layer:
                continue
            phase_offset = 0.0 if side > 0 else math.pi
            leg_swing = math.sin(phase + phase_offset)
            arm_swing = -leg_swing
            shoulder = (
                anchor_x + px * side * shoulder_width,
                shoulder_y + py * side * shoulder_width * 0.2,
            )
            elbow = (
                shoulder[0]
                + vx * arm_swing * arm_stride * 0.50
                + px * side * 1.1 * scale,
                shoulder[1] + arm_len * 0.42 + vy * arm_swing * arm_stride * 0.14,
            )
            hand = (
                shoulder[0] + vx * arm_swing * arm_stride - px * side * 1.5 * scale,
                shoulder[1] + arm_len + vy * arm_swing * arm_stride * 0.22,
            )
            self.draw_jointed_limb(
                (shoulder, elbow, hand), torso_color, outline, max(2, line_w - 1), alpha
            )

    def draw_sprite_direction_cue(
        self,
        sx: int,
        sy: int,
        dx: float,
        dy: float,
        color: Color,
        hostile: bool = False,
    ) -> None:
        vx, vy = self.iso_screen_direction(dx, dy)
        scale = WORLD_SCALE
        chest_x = sx + int(vx * 12 * scale)
        chest_y = sy - 42 * scale + int(vy * 5 * scale)
        foot_x = sx + int(vx * 10 * scale)
        foot_y = sy - 9 * scale + int(vy * 4 * scale)
        dark = (30, 24, 30) if hostile else (25, 33, 44)
        pygame.draw.rect(
            self.screen,
            dark,
            (chest_x - 3 * scale, chest_y - 3 * scale, 6 * scale, 6 * scale),
        )
        pygame.draw.rect(
            self.screen,
            color,
            (chest_x - 2 * scale, chest_y - 2 * scale, 4 * scale, 4 * scale),
        )
        pygame.draw.line(
            self.screen,
            color,
            (sx, sy - 20 * scale),
            (foot_x, foot_y),
            max(1, scale),
        )
        pygame.draw.rect(
            self.screen,
            color,
            (foot_x - 2 * scale, foot_y - scale, 4 * scale, 2 * scale),
        )

    def blit_sprite(
        self,
        sprite: pygame.Surface,
        x: float,
        y: float,
        y_offset: float = 0.0,
        facing_x: float = 1.0,
        x_offset: float = 0.0,
        stretch: float = 1.0,
        lean: float = 0.0,
        alpha: int = 255,
    ) -> tuple[int, int]:
        sx, sy = self.world_to_screen(x, y)
        turned_sprite = (
            pygame.transform.flip(sprite, True, False) if facing_x < 0 else sprite
        )
        if abs(stretch - 1.0) > 0.018:
            turned_sprite = pygame.transform.scale(
                turned_sprite,
                (
                    max(1, round(turned_sprite.get_width() / stretch)),
                    max(1, round(turned_sprite.get_height() * stretch)),
                ),
            )
        if abs(lean) > 1.85:
            turned_sprite = pygame.transform.rotate(
                turned_sprite, -lean if facing_x >= 0 else lean
            )
        if alpha < 255:
            turned_sprite = turned_sprite.copy()
            turned_sprite.set_alpha(alpha)
        rect = turned_sprite.get_rect(
            midbottom=(
                round(sx + x_offset * WORLD_SCALE),
                round(sy + y_offset * WORLD_SCALE),
            )
        )
        self.screen.blit(turned_sprite, rect)
        return rect.centerx, sy

    def draw_player(self, player: Player) -> None:
        sway, bob, lean, stretch = self.actor_animation(player)
        self.draw_shadow(player.x, player.y, 34, 13, moving=player.moving, lift=bob)
        self.draw_movement_trail(player, (145, 130, 98), size=2)
        if player.moving:
            self.blit_sprite(
                self.sprites.player,
                player.x - player.move_x * 0.035,
                player.y - player.move_y * 0.035,
                y_offset=8 - bob,
                facing_x=player.facing_x,
                x_offset=sway,
                stretch=1.0,
                lean=0.0,
                alpha=52,
            )
        sx, sy = self.blit_sprite(
            self.sprites.player,
            player.x,
            player.y,
            y_offset=6.0 - bob,
            facing_x=player.facing_x,
            x_offset=sway,
            stretch=1.0,
            lean=0.0,
        )

    def draw_aim_cone(self) -> None:
        sx, sy = self.world_to_screen(self.player.x, self.player.y)
        vx, vy = self.iso_screen_direction(self.player.facing_x, self.player.facing_y)
        px, py = -vy, vx
        origin = (
            sx + int(vx * 14 * WORLD_SCALE),
            sy - 8 * WORLD_SCALE + int(vy * 6 * WORLD_SCALE),
        )
        tip = (
            origin[0] + int(vx * 108 * WORLD_SCALE),
            origin[1] + int(vy * 108 * WORLD_SCALE),
        )
        left = (
            origin[0] + int(vx * 74 * WORLD_SCALE + px * 36 * WORLD_SCALE),
            origin[1] + int(vy * 74 * WORLD_SCALE + py * 36 * WORLD_SCALE),
        )
        right = (
            origin[0] + int(vx * 74 * WORLD_SCALE - px * 36 * WORLD_SCALE),
            origin[1] + int(vy * 74 * WORLD_SCALE - py * 36 * WORLD_SCALE),
        )
        points = [origin, left, tip, right]
        blur_pad = 14 * WORLD_SCALE
        min_x = min(point[0] for point in points) - blur_pad
        max_x = max(point[0] for point in points) + blur_pad
        min_y = min(point[1] for point in points) - blur_pad
        max_y = max(point[1] for point in points) + blur_pad
        overlay = pygame.Surface((max_x - min_x, max_y - min_y), pygame.SRCALPHA)
        local_points = [(x - min_x, y - min_y) for x, y in points]

        glow = pygame.Surface(overlay.get_size(), pygame.SRCALPHA)
        pygame.draw.polygon(glow, (92, 170, 255, 24), local_points)
        local_tip = (tip[0] - min_x, tip[1] - min_y)
        blur_size = (
            max(1, glow.get_width() // 4),
            max(1, glow.get_height() // 4),
        )
        glow = pygame.transform.smoothscale(glow, blur_size)
        glow = pygame.transform.smoothscale(glow, overlay.get_size())
        overlay.blit(glow, (0, 0))

        pygame.draw.polygon(overlay, (92, 170, 255, 34), local_points)
        pygame.draw.circle(overlay, (225, 245, 255, 120), local_tip, 2 * WORLD_SCALE)
        self.screen.blit(overlay, (min_x, min_y))

    def draw_enemy(self, enemy: Enemy) -> None:
        fallback = (
            self.sprites.enemies["Gate Warden"]
            if enemy.kind == "boss"
            else self.sprites.enemies["Ghoul"]
        )
        sprite = self.sprites.enemies.get(enemy.name, fallback)
        shadow_w = (
            44 if enemy.kind == "boss" else 38 if enemy.name == "Gate Warden" else 32
        )
        sway, bob, lean, stretch = self.actor_animation(enemy)
        if enemy.kind == "boss":
            stretch += math.sin(self.elapsed * 3.4) * 0.025
            lean += math.sin(self.elapsed * 2.1) * 1.0
        self.draw_shadow(enemy.x, enemy.y, shadow_w, 12, moving=enemy.moving, lift=bob)
        self.draw_movement_trail(enemy, (120, 84, 68), size=2)
        if enemy.moving:
            self.blit_sprite(
                sprite,
                enemy.x - enemy.move_x * 0.03,
                enemy.y - enemy.move_y * 0.03,
                y_offset=8.0 - bob,
                facing_x=enemy.facing_x,
                x_offset=sway,
                stretch=1.0,
                lean=0.0,
                alpha=42,
            )
        sx, sy = self.blit_sprite(
            sprite,
            enemy.x,
            enemy.y,
            y_offset=6.0 - bob,
            facing_x=enemy.facing_x,
            x_offset=sway,
            stretch=1.0,
            lean=0.0,
        )
        bar_w = (
            46 if enemy.kind == "boss" else 34 if enemy.name == "Gate Warden" else 28
        ) * WORLD_SCALE
        fill_w = int(bar_w * max(0, enemy.hp) / enemy.max_hp)
        bar_h = 4 * WORLD_SCALE
        bar_y = sy - sprite.get_height() - 2 * WORLD_SCALE
        pygame.draw.rect(
            self.screen, (40, 10, 10), (sx - bar_w // 2, bar_y, bar_w, bar_h)
        )
        pygame.draw.rect(
            self.screen, (215, 62, 52), (sx - bar_w // 2, bar_y, fill_w, bar_h)
        )
        if enemy.kind == "boss":
            pulse = 0.5 + 0.5 * math.sin(self.elapsed * 4.2)
            aura = pygame.Surface((70 * WORLD_SCALE, 28 * WORLD_SCALE), pygame.SRCALPHA)
            pygame.draw.ellipse(
                aura,
                (*self.theme.accent, int(26 + pulse * 34)),
                aura.get_rect(),
                max(1, WORLD_SCALE),
            )
            self.screen.blit(aura, aura.get_rect(center=(sx, sy - 18 * WORLD_SCALE)))

    def draw_item(self, item: Item) -> None:
        sx, sy = self.world_to_screen(item.x, item.y)
        rarity_color = {
            "Common": (210, 205, 180),
            "Magic": (105, 165, 255),
            "Rare": (245, 210, 80),
            "Unique": (240, 145, 65),
            "Unidentified": (170, 170, 185),
        }.get(item.visible_rarity, (220, 220, 220))
        sprite = self.sprites.items.get(item.slot, self.sprites.items["potion"])
        pulse = 0.65 + 0.35 * math.sin(self.elapsed * 4.0 + item.x + item.y)
        rare_scale = 1.25 if item.visible_rarity in ("Rare", "Unique") else 1.0
        glow = pygame.Surface(
            (int(42 * rare_scale) * WORLD_SCALE, int(20 * rare_scale) * WORLD_SCALE),
            pygame.SRCALPHA,
        )
        pygame.draw.ellipse(
            glow, (*rarity_color, int(55 + 45 * pulse)), glow.get_rect()
        )
        pygame.draw.ellipse(
            glow,
            (*self.shade(rarity_color, 45), int(22 + 30 * pulse)),
            glow.get_rect().inflate(-glow.get_width() // 3, -glow.get_height() // 3),
        )
        self.screen.blit(glow, glow.get_rect(center=(sx, sy + WORLD_SCALE)))
        bob = int(math.sin(self.elapsed * 3.2 + item.x * 0.7) * 2 * WORLD_SCALE)
        if item.visible_rarity in ("Magic", "Rare", "Unique", "Unidentified"):
            for index in range(3 if item.visible_rarity == "Unique" else 2):
                angle = (
                    self.elapsed * (2.4 + index * 0.7) + item.x + index * math.tau / 3
                )
                sparkle_x = sx + int(math.cos(angle) * (11 + index * 4) * WORLD_SCALE)
                sparkle_y = (
                    sy - int((8 + math.sin(angle * 1.7) * 5) * WORLD_SCALE) - bob
                )
                sparkle_alpha = int(95 + 95 * (0.5 + 0.5 * math.sin(angle * 2.0)))
                pygame.draw.line(
                    self.screen,
                    (*rarity_color, sparkle_alpha),
                    (sparkle_x - 2 * WORLD_SCALE, sparkle_y),
                    (sparkle_x + 2 * WORLD_SCALE, sparkle_y),
                    max(1, WORLD_SCALE),
                )
                pygame.draw.line(
                    self.screen,
                    (*rarity_color, sparkle_alpha),
                    (sparkle_x, sparkle_y - 2 * WORLD_SCALE),
                    (sparkle_x, sparkle_y + 2 * WORLD_SCALE),
                    max(1, WORLD_SCALE),
                )
        item_sprite = sprite
        tilt = math.sin(self.elapsed * 2.8 + item.y) * 3.0
        if item.visible_rarity in ("Rare", "Unique"):
            item_sprite = pygame.transform.rotate(sprite, tilt)
        rect = item_sprite.get_rect(midbottom=(sx, sy + 4 * WORLD_SCALE - bob))
        self.screen.blit(item_sprite, rect)
        if math.hypot(item.x - self.player.x, item.y - self.player.y) < 1.0:
            label = self.small_font.render(
                f"E: {item.display_name}", True, rarity_color
            )
            self.screen.blit(
                label, label.get_rect(center=(sx, rect.top - 10 * WORLD_SCALE))
            )

    def draw_trap(self, trap: Trap) -> None:
        if not trap.active:
            return
        sx, sy = self.world_to_screen(trap.x, trap.y)
        color = {
            "Spike Trap": (205, 75, 58),
            "Rune Trap": (160, 86, 230),
            "Poison Needle": (110, 185, 95),
        }.get(trap.kind, (205, 75, 58))
        pulse = 0.5 + 0.5 * math.sin(self.elapsed * 5.4 + trap.x)
        wobble = math.sin(self.elapsed * 3.7 + trap.y) * 2 * WORLD_SCALE
        points = [
            (sx, sy - int((10 + pulse * 2) * WORLD_SCALE)),
            (sx + 16 * WORLD_SCALE + int(wobble), sy),
            (sx, sy + int((10 + pulse * 2) * WORLD_SCALE)),
            (sx - 16 * WORLD_SCALE + int(wobble), sy),
        ]
        warning = pygame.Surface((42 * WORLD_SCALE, 22 * WORLD_SCALE), pygame.SRCALPHA)
        pygame.draw.ellipse(warning, (*color, int(22 + pulse * 28)), warning.get_rect())
        self.screen.blit(warning, warning.get_rect(center=(sx, sy + WORLD_SCALE)))
        pygame.draw.lines(self.screen, color, True, points, max(1, WORLD_SCALE))
        pygame.draw.lines(
            self.screen, self.shade(color, 45), True, points, max(1, WORLD_SCALE)
        )
        pygame.draw.circle(self.screen, color, (sx, sy), max(2, 2 * WORLD_SCALE))
        pygame.draw.circle(
            self.screen, self.shade(color, 45), (sx, sy), max(1, WORLD_SCALE)
        )

    def draw_secret(self, secret: SecretCache) -> None:
        sx, sy = self.world_to_screen(secret.x, secret.y)
        color = self.theme.accent
        pulse = 0.55 + 0.45 * math.sin(self.elapsed * 5.0 + secret.x)
        glow = pygame.Surface((34 * WORLD_SCALE, 18 * WORLD_SCALE), pygame.SRCALPHA)
        pygame.draw.ellipse(glow, (*color, int(34 + 46 * pulse)), glow.get_rect())
        self.screen.blit(glow, glow.get_rect(center=(sx, sy + 2 * WORLD_SCALE)))
        pygame.draw.rect(
            self.screen,
            (35, 28, 24),
            (
                sx - 8 * WORLD_SCALE,
                sy - 8 * WORLD_SCALE,
                16 * WORLD_SCALE,
                10 * WORLD_SCALE,
            ),
        )
        pygame.draw.rect(
            self.screen,
            color,
            (
                sx - 8 * WORLD_SCALE,
                sy - 8 * WORLD_SCALE,
                16 * WORLD_SCALE,
                10 * WORLD_SCALE,
            ),
            max(1, WORLD_SCALE),
        )
        if math.hypot(secret.x - self.player.x, secret.y - self.player.y) < 1.1:
            label = self.small_font.render(f"E: {secret.kind}", True, color)
            self.screen.blit(label, label.get_rect(center=(sx, sy - 25 * WORLD_SCALE)))

    def draw_shrine(self, shrine: Shrine) -> None:
        sx, sy = self.world_to_screen(shrine.x, shrine.y)
        color = (92, 92, 100) if shrine.used else (235, 205, 110)
        pulse = 0.6 + 0.4 * math.sin(self.elapsed * 3.0 + shrine.x)
        glow = pygame.Surface((50 * WORLD_SCALE, 28 * WORLD_SCALE), pygame.SRCALPHA)
        pygame.draw.ellipse(glow, (*color, int(42 + 48 * pulse)), glow.get_rect())
        pygame.draw.ellipse(
            glow,
            (*self.shade(color, 38), int(20 + 32 * pulse)),
            glow.get_rect().inflate(-glow.get_width() // 3, -glow.get_height() // 3),
        )
        self.screen.blit(glow, glow.get_rect(center=(sx, sy)))
        if not shrine.used:
            for index in range(3):
                angle = self.elapsed * 1.8 + shrine.x + index * math.tau / 3
                mote_x = sx + int(math.cos(angle) * 17 * WORLD_SCALE)
                mote_y = sy - int((16 + math.sin(angle) * 6) * WORLD_SCALE)
                pygame.draw.circle(
                    self.screen,
                    self.shade(color, 35),
                    (mote_x, mote_y),
                    max(1, WORLD_SCALE),
                )
        pygame.draw.rect(
            self.screen,
            (48, 42, 50),
            (
                sx - 7 * WORLD_SCALE,
                sy - 24 * WORLD_SCALE,
                14 * WORLD_SCALE,
                25 * WORLD_SCALE,
            ),
        )
        pygame.draw.rect(
            self.screen,
            color,
            (
                sx - 4 * WORLD_SCALE,
                sy - 19 * WORLD_SCALE,
                8 * WORLD_SCALE,
                6 * WORLD_SCALE,
            ),
        )
        if (
            not shrine.used
            and math.hypot(shrine.x - self.player.x, shrine.y - self.player.y) < 1.15
        ):
            label = self.small_font.render(f"E: {shrine.kind}", True, color)
            self.screen.blit(label, label.get_rect(center=(sx, sy - 38 * WORLD_SCALE)))

    def draw_projectile(self, projectile: Projectile) -> None:
        sx, sy = self.world_to_screen(projectile.x, projectile.y)
        sprite = self.sprites.projectiles.get(
            projectile.owner, self.sprites.projectiles["enemy"]
        )
        vx, vy = self.iso_screen_direction(projectile.vx, projectile.vy)
        color = (70, 165, 255) if projectile.owner == "player" else (210, 83, 238)
        px, py = -vy, vx
        flicker = 0.5 + 0.5 * math.sin(self.elapsed * 18.0 + projectile.x)
        for step, alpha in ((1, 136), (2, 92), (3, 54), (4, 26)):
            trail = pygame.Surface((10 * WORLD_SCALE, 5 * WORLD_SCALE), pygame.SRCALPHA)
            pygame.draw.ellipse(trail, (*color, alpha), trail.get_rect())
            side = math.sin(self.elapsed * 12.0 + step) * 2 * WORLD_SCALE
            self.screen.blit(
                trail,
                trail.get_rect(
                    center=(
                        sx - int(vx * step * 9 * WORLD_SCALE + px * side),
                        sy
                        - 12 * WORLD_SCALE
                        - int(vy * step * 9 * WORLD_SCALE + py * side),
                    )
                ),
            )
        pygame.draw.circle(
            self.screen,
            (*self.shade(color, 45), int(72 + flicker * 72)),
            (sx, sy - 12 * WORLD_SCALE),
            max(3, int((3 + flicker * 2) * WORLD_SCALE)),
        )
        angle = -math.degrees(math.atan2(vy, vx))
        sprite = pygame.transform.rotate(
            sprite, angle + math.sin(self.elapsed * 20.0) * 4
        )
        rect = sprite.get_rect(center=(sx, sy - 12 * WORLD_SCALE))
        self.screen.blit(sprite, rect)

    def draw_slash(self, slash: SlashEffect) -> None:
        x, y, ttl, dx, dy = slash
        sx, sy = self.world_to_screen(x, y)
        life = max(0.0, min(1.0, ttl / 0.18))
        sprite = self.sprites.slash.copy()
        if dx < 0:
            sprite = pygame.transform.flip(sprite, True, False)
        if life < 0.7:
            grow = 1.0 + (0.7 - life) * 0.25
            sprite = pygame.transform.scale(
                sprite,
                (int(sprite.get_width() * grow), int(sprite.get_height() * grow)),
            )
        sprite.set_alpha(max(0, min(255, int(255 * life))))
        vx, vy = self.iso_screen_direction(dx, dy)
        px, py = -vy, vx
        center = (
            sx + int(vx * (1.0 - life) * 12 * WORLD_SCALE),
            sy - 18 * WORLD_SCALE + int(vy * (1.0 - life) * 6 * WORLD_SCALE),
        )
        for index, alpha in enumerate((92, 54, 26)):
            arc_offset = (index + 1) * 7 * WORLD_SCALE
            pygame.draw.line(
                self.screen,
                (255, 235, 170, int(alpha * life)),
                (
                    center[0] - int(vx * arc_offset + px * 8 * WORLD_SCALE),
                    center[1] - int(vy * arc_offset + py * 4 * WORLD_SCALE),
                ),
                (
                    center[0] + int(vx * arc_offset + px * 8 * WORLD_SCALE),
                    center[1] + int(vy * arc_offset + py * 4 * WORLD_SCALE),
                ),
                max(1, WORLD_SCALE),
            )
        rect = sprite.get_rect(center=center)
        self.screen.blit(sprite, rect)
        spark_alpha = max(0, min(255, int(180 * life)))
        for side in (-1, 1):
            pygame.draw.line(
                self.screen,
                (255, 252, 210, spark_alpha),
                center,
                (
                    center[0]
                    + int((vx * 16 + px * side * 10) * WORLD_SCALE * (1.0 - life)),
                    center[1]
                    + int((vy * 8 + py * side * 6) * WORLD_SCALE * (1.0 - life)),
                ),
                max(1, WORLD_SCALE),
            )

    def ui(self, value: int) -> int:
        return value * UI_SCALE

    def draw_ui(self) -> None:
        width, height = self.screen.get_size()
        panel_h = self.ui(112)
        margin = self.ui(22)
        panel = pygame.Rect(0, height - panel_h, width, panel_h)
        pygame.draw.rect(self.screen, (14, 14, 18), panel)
        pygame.draw.line(
            self.screen,
            (75, 65, 54),
            (0, height - panel_h),
            (width, height - panel_h),
            self.ui(2),
        )

        self.draw_bar(
            margin,
            height - self.ui(92),
            self.ui(230),
            self.ui(20),
            self.player.hp,
            self.player.max_hp,
            (185, 46, 46),
            "HP",
        )
        self.draw_bar(
            margin,
            height - self.ui(64),
            self.ui(230),
            self.ui(16),
            self.player.mana,
            self.player.max_mana,
            (54, 102, 210),
            "Mana",
        )
        self.draw_bar(
            margin,
            height - self.ui(40),
            self.ui(230),
            self.ui(16),
            self.player.stamina,
            self.player.max_stamina,
            (216, 170, 66),
            "Stamina",
        )

        weapon = (
            self.player.equipment["weapon"].name
            if self.player.equipment["weapon"]
            else "Training Sword"
        )
        armor = (
            self.player.equipment["armor"].name
            if self.player.equipment["armor"]
            else "Cloth"
        )
        lines = [
            self.player.class_name,
            f"Level {self.player.level}  XP {self.player.xp}/{self.player.next_xp}",
            f"Weapon: {weapon}  Damage: {self.player.melee_damage()}",
            f"Armor: {armor}  DR: {self.player.armor()}",
        ]
        for i, line in enumerate(lines):
            text = self.small_font.render(line, True, (220, 215, 200))
            self.screen.blit(
                text, (self.ui(280), height - self.ui(100) + i * self.ui(24))
            )

        self.draw_run_header()
        self.draw_boss_bar()

        objective = (
            "Objective: find the stairs to descend deeper"
            if self.current_depth < DUNGEON_DEPTH
            else "Objective: defeat the gate tyrant, then reach the stairs"
        )
        nearby_shrine = self.nearby_shrine()
        nearby_secret = self.nearby_secret()
        nearby_item = self.nearby_item()
        if self.player_near_stairs():
            if self.current_depth < DUNGEON_DEPTH:
                objective = (
                    f"E: Descend to depth {self.current_depth + 1}/{DUNGEON_DEPTH}"
                )
            else:
                objective = (
                    "Gate sealed: defeat the tyrant"
                    if self.boss_alive()
                    else "E: Descend the stairs"
                )
        elif nearby_secret:
            objective = f"E: Open {nearby_secret.kind}"
        elif nearby_shrine:
            objective = f"E: Use {nearby_shrine.kind}"
        elif nearby_item:
            objective = f"E: Pick up {nearby_item.display_name}"
        text = self.font.render(objective, True, self.theme.accent)
        self.screen.blit(
            text, (width - text.get_width() - self.ui(24), height - self.ui(98))
        )
        skill_line = (
            f"Skills: Space Slash | F Bolt {self.player.bolt_timer:.1f}s | "
            f"C Nova {self.player.nova_timer:.1f}s | Shift Dash {self.player.dash_timer:.1f}s"
        )
        control_lines = [
            "Hold Left Mouse to move/aim and slash nearby enemies | E interact | I inventory | Q potion | H help",
            skill_line,
        ]
        for i, controls in enumerate(control_lines):
            text = self.small_font.render(controls, True, (170, 165, 155))
            self.screen.blit(
                text,
                (
                    width - text.get_width() - self.ui(24),
                    height - self.ui(54) + i * self.ui(22),
                ),
            )

    def draw_run_header(self) -> None:
        title = f"Run {self.run_number}: Depth {self.current_depth}/{DUNGEON_DEPTH} — {self.theme.name}"
        modifier = (
            f"Modifier: {self.run_modifier.name} — {self.run_modifier.description}"
        )
        title_surface = self.font.render(title, True, self.theme.accent)
        modifier_surface = self.small_font.render(modifier, True, (205, 200, 190))
        self.screen.blit(title_surface, (self.ui(20), self.ui(18)))
        self.screen.blit(modifier_surface, (self.ui(20), self.ui(48)))

    def draw_boss_bar(self) -> None:
        boss = self.boss_enemy()
        if not boss:
            return
        width, _height = self.screen.get_size()
        bar_w = self.ui(520)
        bar_h = self.ui(16)
        x = (width - bar_w) // 2
        y = self.ui(22)
        fill = int(bar_w * max(0, boss.hp) / boss.max_hp)
        pygame.draw.rect(self.screen, (28, 10, 14), (x, y, bar_w, bar_h))
        pygame.draw.rect(self.screen, self.theme.accent, (x, y, fill, bar_h))
        pygame.draw.rect(self.screen, (190, 160, 115), (x, y, bar_w, bar_h), self.ui(1))
        label = self.small_font.render(boss.name, True, (245, 235, 215))
        self.screen.blit(label, label.get_rect(center=(width // 2, y - self.ui(9))))

    def draw_bar(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        value: float,
        max_value: float,
        color: Color,
        label: str,
    ) -> None:
        pygame.draw.rect(self.screen, (35, 32, 35), (x, y, w, h))
        fill = int(w * max(0.0, min(1.0, value / max_value)))
        pygame.draw.rect(self.screen, color, (x, y, fill, h))
        pygame.draw.rect(self.screen, (95, 88, 82), (x, y, w, h), self.ui(1))
        text = self.small_font.render(
            f"{label} {int(value)}/{int(max_value)}", True, (245, 240, 230)
        )
        self.screen.blit(text, text.get_rect(center=(x + w // 2, y + h // 2)))

    def draw_inventory(self) -> None:
        width, _height = self.screen.get_size()
        box = pygame.Rect(width - self.ui(430), self.ui(40), self.ui(390), self.ui(320))
        pygame.draw.rect(self.screen, (18, 17, 22), box)
        pygame.draw.rect(self.screen, (105, 90, 68), box, self.ui(2))
        title = self.font.render("Inventory (1-9 equip/use)", True, (235, 220, 180))
        self.screen.blit(title, (box.x + self.ui(18), box.y + self.ui(16)))
        if not self.player.inventory:
            empty = self.small_font.render("Empty", True, (170, 165, 155))
            self.screen.blit(empty, (box.x + self.ui(20), box.y + self.ui(58)))
        for index, item in enumerate(self.player.inventory):
            y = box.y + self.ui(58) + index * self.ui(28)
            color = {
                "Common": (215, 210, 190),
                "Magic": (115, 175, 255),
                "Rare": (245, 215, 90),
                "Unique": (240, 145, 65),
                "Unidentified": (170, 170, 185),
            }.get(item.visible_rarity, (220, 220, 220))
            text = self.small_font.render(
                f"{index + 1}. [{item.visible_rarity}] {item.label}", True, color
            )
            self.screen.blit(text, (box.x + self.ui(20), y))
        equipment = [
            f"Weapon: {self.player.equipment['weapon'].label if self.player.equipment['weapon'] else 'Training Sword (+0 dmg)'}",
            f"Armor: {self.player.equipment['armor'].label if self.player.equipment['armor'] else 'Cloth (+0 armor)'}",
        ]
        for i, line in enumerate(equipment):
            text = self.small_font.render(line, True, (210, 205, 190))
            self.screen.blit(
                text, (box.x + self.ui(20), box.y + self.ui(250) + i * self.ui(26))
            )

    def draw_help_overlay(self) -> None:
        width, height = self.screen.get_size()
        box = pygame.Rect(
            self.ui(42),
            self.ui(90),
            min(self.ui(620), width - self.ui(84)),
            self.ui(390),
        )
        panel = pygame.Surface(box.size, pygame.SRCALPHA)
        panel.fill((12, 12, 18, 226))
        self.screen.blit(panel, box)
        pygame.draw.rect(self.screen, self.theme.accent, box, self.ui(2))
        lines = [
            "Run Guide (H to close)",
            "Goal: defeat the gate tyrant in the final room, then use E on the stairs.",
            "Mouse: hold left button to move and aim; slash triggers when enemies are close.",
            "Skills: Space slash, F bolt, C arc nova, Shift dash.",
            "Resources: stamina powers slash/dash; mana powers bolt/nova and regenerates slowly.",
            "Inventory: E picks up; I opens inventory; 1-9 equips or uses listed items; Q drinks a potion.",
            "Discovery: unidentified gear needs scrolls, Insight Shrines, or equipping to reveal.",
            "Hazards: traps are single-use but dangerous; shrines and secrets can swing a run.",
        ]
        for index, line in enumerate(lines):
            font = self.font if index == 0 else self.small_font
            color = self.theme.accent if index == 0 else (222, 218, 205)
            text = font.render(line, True, color)
            self.screen.blit(
                text, (box.x + self.ui(22), box.y + self.ui(20) + index * self.ui(42))
            )

    def draw_archetype_select(self) -> None:
        width, height = self.screen.get_size()
        title = self.big_font.render("Choose Your Archetype", True, (235, 220, 180))
        self.screen.blit(title, title.get_rect(center=(width // 2, self.ui(145))))
        subtitle = self.font.render(
            "Each new run rolls a dungeon theme, modifier, boss, secrets, and loot.",
            True,
            (195, 190, 180),
        )
        self.screen.blit(subtitle, subtitle.get_rect(center=(width // 2, self.ui(205))))
        columns = min(3, len(ARCHETYPES))
        gap = self.ui(32)
        card_w = min(
            self.ui(390), (width - self.ui(80) - gap * (columns - 1)) // columns
        )
        card_h = self.ui(210)
        total_w = card_w * columns + gap * (columns - 1)
        start_x = (width - total_w) // 2
        start_y = self.ui(270)
        row_gap = self.ui(30)
        for index, archetype in enumerate(ARCHETYPES):
            row = index // columns
            col = index % columns
            x = start_x + col * (card_w + gap)
            y = start_y + row * (card_h + row_gap)
            box = pygame.Rect(x, y, card_w, card_h)
            is_selected = archetype == self.selected_archetype
            border = self.theme.accent if is_selected else (105, 90, 68)
            pygame.draw.rect(self.screen, (18, 17, 22), box)
            pygame.draw.rect(self.screen, border, box, self.ui(3 if is_selected else 2))
            name = self.font.render(
                f"{index + 1}. {archetype.name}", True, (235, 220, 180)
            )
            self.screen.blit(name, (x + self.ui(18), y + self.ui(18)))
            desc = self.small_font.render(archetype.description, True, (190, 185, 175))
            self.screen.blit(desc, (x + self.ui(18), y + self.ui(58)))
            stats = [
                f"HP {archetype.max_hp}  Mana {archetype.max_mana}",
                f"Stamina {archetype.max_stamina}  Speed {archetype.speed:.2f}",
                f"Melee +{archetype.melee_bonus}  Spell +{archetype.spell_bonus}  DR +{archetype.armor_bonus}",
            ]
            for line_index, stat in enumerate(stats):
                text = self.small_font.render(stat, True, (220, 215, 200))
                self.screen.blit(
                    text,
                    (x + self.ui(18), y + self.ui(102) + line_index * self.ui(28)),
                )
        prompt = self.font.render(
            f"Press 1-{min(len(ARCHETYPES), 9)} or Enter to begin",
            True,
            (235, 205, 120),
        )
        self.screen.blit(
            prompt, prompt.get_rect(center=(width // 2, height - self.ui(150)))
        )

    def draw_state_overlay(self) -> None:
        width, height = self.screen.get_size()
        overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 165))
        self.screen.blit(overlay, (0, 0))
        if self.state == "victory":
            title = "Dungeon Cleared"
            subtitle = f"You survived all {DUNGEON_DEPTH} depths and broke the gate. Press R to choose a new run."
            color = (235, 205, 120)
        else:
            title = "You Died"
            subtitle = f"The dungeon claims another {self.player.class_name}. Press R to choose again."
            color = (225, 75, 65)
        title_surface = self.big_font.render(title, True, color)
        subtitle_surface = self.font.render(subtitle, True, (230, 225, 210))
        center_y = height // 2 - self.ui(68)
        self.screen.blit(
            title_surface, title_surface.get_rect(center=(width // 2, center_y))
        )
        self.screen.blit(
            subtitle_surface,
            subtitle_surface.get_rect(center=(width // 2, center_y + self.ui(58))),
        )
        summary_lines = self.run_summary_lines()
        for index, line in enumerate(summary_lines):
            text = self.small_font.render(line, True, (212, 207, 190))
            self.screen.blit(
                text,
                text.get_rect(
                    center=(width // 2, center_y + self.ui(112) + index * self.ui(28))
                ),
            )

    def run_summary_lines(self) -> list[str]:
        minutes = int(self.elapsed // 60)
        seconds = int(self.elapsed % 60)
        return [
            f"Time {minutes:02d}:{seconds:02d}  Depth {self.current_depth}/{DUNGEON_DEPTH}  Modifier {self.run_modifier.name}",
            f"Kills {self.run_stats.kills}  Boss {'defeated' if self.run_stats.boss_killed else 'alive'}  Damage taken {self.run_stats.damage_taken}",
            f"Loot {self.run_stats.loot_picked_up}  Potions {self.run_stats.potions_used}  Shrines {self.run_stats.shrines_used}",
            f"Secrets {self.run_stats.secrets_opened}  Traps triggered {self.run_stats.traps_triggered}",
        ]


def main() -> None:
    Game().run()
