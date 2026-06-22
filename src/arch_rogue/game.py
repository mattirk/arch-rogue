from __future__ import annotations

import math
import random
from typing import cast

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
UI_SCALE = 2
PLAYER_HIT_RADIUS = 0.42
ENEMY_HIT_RADIUS = 0.42
LARGE_ENEMY_HIT_RADIUS = 0.52
BOSS_HIT_RADIUS = 0.64
PLAYER_MELEE_RANGE = 1.55
PLAYER_MELEE_ARC_DOT = 0.05
PLAYER_PROJECTILE_HIT_RADIUS = 0.54
ENEMY_PROJECTILE_HIT_RADIUS = 0.52

SlashEffect = tuple[float, float, float, float, float]

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
        max_hp=82,
        max_mana=72,
        max_stamina=92,
        speed=4.35,
        spell_bonus=8,
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
)


class Game:
    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption("Arch Rogue - Prototype 3")
        display_info = pygame.display.Info()
        self.screen = pygame.display.set_mode(
            (display_info.current_w, display_info.current_h), pygame.NOFRAME
        )
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
        self.state = "archetype_select"
        self.elapsed = 0.0
        self.selected_archetype = ARCHETYPES[0]
        self.theme = DUNGEON_THEMES[0]
        self.run_modifier = RUN_MODIFIERS[0]
        self.run_number = 0

    def restart(self, archetype: Archetype | None = None) -> None:
        self.run_number += 1
        if archetype:
            self.selected_archetype = archetype
        self.theme = self.rng.choice(DUNGEON_THEMES)
        self.tile_cache.clear()
        self.run_modifier = self.rng.choice(RUN_MODIFIERS)
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
        self.inventory_open = False
        self.state = "playing"
        self._populate_dungeon()

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

            if is_final_room:
                bx, by = room.center
                self.enemies.append(self._make_boss(bx + 0.5, by + 0.5))

            if self.rng.random() < 0.68 + self.run_modifier.loot_bonus:
                self.items.append(self._make_loot(*room.random_point(self.rng)))
            if (
                room_index > 1
                and self.rng.random() < 0.24 + self.run_modifier.trap_bonus
            ):
                tx, ty = room.random_point(self.rng)
                self.traps.append(
                    Trap(
                        tx,
                        ty,
                        self.rng.choice(["Spike Trap", "Rune Trap"]),
                        self.rng.randrange(14, 23),
                    )
                )
            shrine_chance = 0.18 + (
                0.08 if self.run_modifier.name == "Trap-Laced" else 0.0
            )
            if room_index > 2 and self.rng.random() < shrine_chance:
                sx, sy = room.random_point(self.rng)
                self.shrines.append(
                    Shrine(
                        sx,
                        sy,
                        self.rng.choice(
                            ["Mending Shrine", "Insight Shrine", "War Shrine"]
                        ),
                    )
                )
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
                        self.rng.choice(["Hidden Cache", "Cursed Reliquary"]),
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

    def _make_enemy(self, x: float, y: float, final_room: bool = False) -> Enemy:
        if final_room and self.rng.random() < 0.35:
            return self._apply_run_modifier(
                Enemy(
                    "Gate Warden",
                    "melee",
                    x,
                    y,
                    72,
                    72,
                    2.1,
                    14,
                    34,
                    1.2,
                    1.0,
                    color=(190, 92, 54),
                )
            )
        roll = self.rng.random()
        if roll < 0.24:
            enemy = Enemy(
                "Cultist",
                "ranged",
                x,
                y,
                34,
                34,
                2.0,
                8,
                18,
                5.4,
                1.45,
                color=(125, 75, 170),
            )
        elif roll < 0.42:
            enemy = Enemy(
                "Bone Imp",
                "ranged",
                x,
                y,
                26,
                26,
                3.0,
                6,
                16,
                4.6,
                1.0,
                color=(190, 130, 215),
            )
        elif roll < 0.58:
            enemy = Enemy(
                "Venom Skitter",
                "melee",
                x,
                y,
                30,
                30,
                3.6,
                7,
                15,
                0.95,
                0.72,
                aggro_range=9.5,
                color=(110, 185, 95),
            )
        elif roll < 0.72:
            enemy = Enemy(
                "Crypt Brute",
                "melee",
                x,
                y,
                82,
                82,
                1.75,
                17,
                32,
                1.35,
                1.35,
                color=(155, 105, 74),
            )
        else:
            enemy = Enemy(
                "Ghoul",
                "melee",
                x,
                y,
                42,
                42,
                2.7,
                10,
                20,
                1.05,
                0.95,
                color=(160, 68, 68),
            )
        return self._apply_run_modifier(enemy)

    def _make_boss(self, x: float, y: float) -> Enemy:
        boss_titles = {
            "Crypt of Ash": "Ashen Gate Tyrant",
            "Fungal Catacombs": "Mycelial Gate Tyrant",
            "Violet Reliquary": "Voidbound Gate Tyrant",
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
            name, base_power = self.rng.choice(
                [("Iron Sword", 5), ("Hunter Axe", 7), ("Runed Saber", 6)]
            )
            item = Item(name, "weapon", power=base_power, rarity=rarity, x=x, y=y)
        else:
            name, base_defense = self.rng.choice(
                [("Leather Jerkin", 2), ("Warden Mail", 4), ("Chain Vest", 3)]
            )
            item = Item(name, "armor", defense=base_defense, rarity=rarity, x=x, y=y)
        self._apply_affixes(
            item, 0 if rarity == "Common" else 1 if rarity == "Magic" else 2
        )
        item.unidentified = rarity != "Common" and self.rng.random() < 0.45
        return item

    def _apply_affixes(self, item: Item, count: int) -> None:
        weapon_affixes = [("Serrated", 3, 0), ("Cruel", 5, 0), ("Balanced", 2, 0)]
        armor_affixes = [("Reinforced", 0, 2), ("Stalwart", 0, 3), ("Light", 0, 1)]
        utility_affixes = [
            ("of the Fox", 1, 1),
            ("of Warding", 0, 2),
            ("of Force", 2, 0),
        ]
        pool = weapon_affixes if item.slot == "weapon" else armor_affixes
        pool = pool + utility_affixes
        for name, power, defense in self.rng.sample(pool, k=min(count, len(pool))):
            item.affixes.append(name)
            item.power += power
            item.defense += defense

    def _make_unique(self, x: float, y: float) -> Item:
        if self.rng.random() < 0.55:
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
                    if pygame.K_1 <= event.key <= pygame.K_3:
                        self.restart(ARCHETYPES[event.key - pygame.K_1])
                    elif event.key == pygame.K_RETURN:
                        self.restart(self.selected_archetype)
                elif event.key == pygame.K_i and self.state == "playing":
                    self.inventory_open = not self.inventory_open
                elif event.key == pygame.K_r and self.state != "playing":
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
            actor.move_x = actual_dx / distance
            actor.move_y = actual_dy / distance
            actor.anim_time += distance * 4.8

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
        if enemy.kind == "boss":
            self.items.append(self._make_unique(enemy.x, enemy.y))
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
            self.items.append(self._make_loot(enemy.x, enemy.y))

    def interact(self) -> None:
        if (
            math.hypot(
                self.player.x - self.dungeon.stairs[0] - 0.5,
                self.player.y - self.dungeon.stairs[1] - 0.5,
            )
            < 1.0
        ):
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
        if secret.kind == "Cursed Reliquary" and self.rng.random() < 0.55:
            self.enemies.append(self._make_enemy(secret.x + 0.3, secret.y + 0.3))
            message = "Reliquary wakes a guardian"
        else:
            drops = 2 if "Stash" in secret.kind else 1
            for _ in range(drops):
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
        if shrine.kind == "Mending Shrine":
            self.player.hp = self.player.max_hp
            self.player.mana = self.player.max_mana
            message = "Shrine restored you"
        elif shrine.kind == "Insight Shrine":
            identified = self.identify_all_items()
            message = (
                f"Shrine revealed {identified} item{'s' if identified != 1 else ''}"
            )
        else:
            leveled = self.player.gain_xp(25)
            self.player.stamina = self.player.max_stamina
            message = "War Shrine grants focus"
            if leveled:
                message = "War Shrine grants a level"
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
        old_hp = self.player.hp
        self.player.hp = min(self.player.max_hp, self.player.hp + item.heal)
        healed = self.player.hp - old_hp
        self.floaters.append(
            FloatingText(
                f"+{healed}", self.player.x, self.player.y - 0.4, (105, 230, 125)
            )
        )

    def drink_mana_potion(self, item: Item) -> None:
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
        self, x: float, y: float, width: int, height: int, moving: bool = False
    ) -> None:
        sx, sy = self.world_to_screen(x, y)
        squash = 1 + int(moving and math.sin(self.elapsed * 18.0) > 0)
        scaled_w = (width + squash * 2) * WORLD_SCALE
        scaled_h = max(1, (height - squash) * WORLD_SCALE)
        shadow = pygame.Surface((scaled_w, scaled_h), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 95), shadow.get_rect())
        self.screen.blit(
            shadow,
            shadow.get_rect(center=(sx, sy + 10 * WORLD_SCALE)),
        )

    def walk_offsets(self, actor: Player | Enemy) -> tuple[int, int]:
        if not actor.moving:
            return 0, 0
        bob = int(abs(math.sin(actor.anim_time * math.tau)) * 3)
        sway = int(math.sin(actor.anim_time * math.tau) * 2)
        return sway, bob

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
        for step, alpha in ((1, 86), (2, 48)):
            px = sx - int(vx * (7 + step * 8) * WORLD_SCALE)
            py = sy + int(8 * WORLD_SCALE) - int(vy * (3 + step * 5) * WORLD_SCALE)
            dust = pygame.Surface(
                (size * 5 * WORLD_SCALE, size * 2 * WORLD_SCALE), pygame.SRCALPHA
            )
            pygame.draw.rect(
                dust,
                (*color, int(alpha * (0.55 + phase * 0.45))),
                dust.get_rect(),
            )
            self.screen.blit(dust, dust.get_rect(center=(px, py)))

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
        y_offset: int = 0,
        facing_x: float = 1.0,
        x_offset: int = 0,
    ) -> tuple[int, int]:
        sx, sy = self.world_to_screen(x, y)
        turned_sprite = (
            pygame.transform.flip(sprite, True, False) if facing_x < 0 else sprite
        )
        rect = turned_sprite.get_rect(
            midbottom=(sx + x_offset * WORLD_SCALE, sy + y_offset * WORLD_SCALE)
        )
        self.screen.blit(turned_sprite, rect)
        return rect.centerx, sy

    def draw_player(self, player: Player) -> None:
        sway, bob = self.walk_offsets(player)
        self.draw_shadow(player.x, player.y, 34, 13, moving=player.moving)
        self.draw_movement_trail(player, (145, 130, 98), size=2)
        sx, sy = self.blit_sprite(
            self.sprites.player,
            player.x,
            player.y,
            y_offset=6 - bob,
            facing_x=player.facing_x,
            x_offset=sway,
        )
        cue_dx = player.move_x if player.moving else player.facing_x
        cue_dy = player.move_y if player.moving else player.facing_y
        self.draw_sprite_direction_cue(
            sx, sy - bob * WORLD_SCALE, cue_dx, cue_dy, (92, 170, 255)
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
        sway, bob = self.walk_offsets(enemy)
        self.draw_shadow(enemy.x, enemy.y, shadow_w, 12, moving=enemy.moving)
        self.draw_movement_trail(enemy, (120, 84, 68), size=2)
        sx, sy = self.blit_sprite(
            sprite,
            enemy.x,
            enemy.y,
            y_offset=6 - bob,
            facing_x=enemy.facing_x,
            x_offset=sway,
        )
        cue_dx = enemy.move_x if enemy.moving else enemy.facing_x
        cue_dy = enemy.move_y if enemy.moving else enemy.facing_y
        self.draw_sprite_direction_cue(
            sx, sy - bob * WORLD_SCALE, cue_dx, cue_dy, (245, 92, 76), hostile=True
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
        glow = pygame.Surface((38 * WORLD_SCALE, 18 * WORLD_SCALE), pygame.SRCALPHA)
        pygame.draw.ellipse(
            glow, (*rarity_color, int(55 + 45 * pulse)), glow.get_rect()
        )
        self.screen.blit(glow, glow.get_rect(center=(sx, sy + WORLD_SCALE)))
        bob = int(math.sin(self.elapsed * 3.2 + item.x * 0.7) * 2 * WORLD_SCALE)
        rect = sprite.get_rect(midbottom=(sx, sy + 4 * WORLD_SCALE - bob))
        self.screen.blit(sprite, rect)
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
        color = (205, 75, 58) if trap.kind == "Spike Trap" else (160, 86, 230)
        points = [
            (sx, sy - 10 * WORLD_SCALE),
            (sx + 16 * WORLD_SCALE, sy),
            (sx, sy + 10 * WORLD_SCALE),
            (sx - 16 * WORLD_SCALE, sy),
        ]
        pygame.draw.lines(self.screen, color, True, points, max(1, WORLD_SCALE))
        pygame.draw.circle(self.screen, color, (sx, sy), max(2, 2 * WORLD_SCALE))

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
        glow = pygame.Surface((42 * WORLD_SCALE, 24 * WORLD_SCALE), pygame.SRCALPHA)
        pygame.draw.ellipse(glow, (*color, int(42 + 48 * pulse)), glow.get_rect())
        self.screen.blit(glow, glow.get_rect(center=(sx, sy)))
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
        for step, alpha in ((1, 120), (2, 72), (3, 38)):
            trail = pygame.Surface((8 * WORLD_SCALE, 4 * WORLD_SCALE), pygame.SRCALPHA)
            pygame.draw.rect(trail, (*color, alpha), trail.get_rect())
            self.screen.blit(
                trail,
                trail.get_rect(
                    center=(
                        sx - int(vx * step * 9 * WORLD_SCALE),
                        sy - 12 * WORLD_SCALE - int(vy * step * 9 * WORLD_SCALE),
                    )
                ),
            )
        angle = -math.degrees(math.atan2(vy, vx))
        sprite = pygame.transform.rotate(sprite, angle)
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
        rect = sprite.get_rect(
            center=(
                sx + int(vx * (1.0 - life) * 12 * WORLD_SCALE),
                sy - 18 * WORLD_SCALE + int(vy * (1.0 - life) * 6 * WORLD_SCALE),
            )
        )
        self.screen.blit(sprite, rect)

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

        objective = "Objective: defeat the gate tyrant, then reach the stairs"
        nearby_shrine = self.nearby_shrine()
        nearby_secret = self.nearby_secret()
        if (
            math.hypot(
                self.player.x - self.dungeon.stairs[0] - 0.5,
                self.player.y - self.dungeon.stairs[1] - 0.5,
            )
            < 1.0
        ):
            objective = (
                "Gate sealed: defeat the tyrant"
                if self.boss_alive()
                else "E: Descend the stairs"
            )
        elif nearby_secret:
            objective = f"E: Open {nearby_secret.kind}"
        elif nearby_shrine:
            objective = f"E: Use {nearby_shrine.kind}"
        text = self.font.render(objective, True, self.theme.accent)
        self.screen.blit(
            text, (width - text.get_width() - self.ui(24), height - self.ui(98))
        )
        skill_line = (
            f"Skills: Space Slash | F Bolt {self.player.bolt_timer:.1f}s | "
            f"C Nova {self.player.nova_timer:.1f}s | Shift Dash {self.player.dash_timer:.1f}s"
        )
        control_lines = [
            "Hold Left Mouse to move/aim and slash nearby enemies | E interact | I inventory | Q potion",
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
        title = f"Run {self.run_number}: {self.theme.name}"
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
        card_w = self.ui(390)
        card_h = self.ui(250)
        gap = self.ui(32)
        total_w = card_w * len(ARCHETYPES) + gap * (len(ARCHETYPES) - 1)
        start_x = (width - total_w) // 2
        y = self.ui(295)
        for index, archetype in enumerate(ARCHETYPES):
            x = start_x + index * (card_w + gap)
            box = pygame.Rect(x, y, card_w, card_h)
            pygame.draw.rect(self.screen, (18, 17, 22), box)
            pygame.draw.rect(self.screen, (105, 90, 68), box, self.ui(2))
            name = self.font.render(
                f"{index + 1}. {archetype.name}", True, (235, 220, 180)
            )
            self.screen.blit(name, (x + self.ui(20), y + self.ui(22)))
            desc = self.small_font.render(archetype.description, True, (190, 185, 175))
            self.screen.blit(desc, (x + self.ui(20), y + self.ui(66)))
            stats = [
                f"HP {archetype.max_hp}  Mana {archetype.max_mana}",
                f"Stamina {archetype.max_stamina}  Speed {archetype.speed:.2f}",
                f"Melee +{archetype.melee_bonus}  Spell +{archetype.spell_bonus}  DR +{archetype.armor_bonus}",
            ]
            for line_index, stat in enumerate(stats):
                text = self.small_font.render(stat, True, (220, 215, 200))
                self.screen.blit(
                    text,
                    (x + self.ui(20), y + self.ui(118) + line_index * self.ui(32)),
                )
        prompt = self.font.render("Press 1-3 to begin", True, (235, 205, 120))
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
            subtitle = "The tyrant is dead and the stairs are open. Press R to choose a new run."
            color = (235, 205, 120)
        else:
            title = "You Died"
            subtitle = f"The dungeon claims another {self.player.class_name}. Press R to choose again."
            color = (225, 75, 65)
        title_surface = self.big_font.render(title, True, color)
        subtitle_surface = self.font.render(subtitle, True, (230, 225, 210))
        self.screen.blit(
            title_surface, title_surface.get_rect(center=(width // 2, height // 2 - 40))
        )
        self.screen.blit(
            subtitle_surface,
            subtitle_surface.get_rect(center=(width // 2, height // 2 + 18)),
        )


def main() -> None:
    Game().run()
