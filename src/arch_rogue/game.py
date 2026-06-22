from __future__ import annotations

import json
import math
import random
import struct
from pathlib import Path
from typing import Any

import pygame

from . import __version__
from .constants import (
    BOSS_HIT_RADIUS,
    DUNGEON_DEPTH,
    ENEMY_HIT_RADIUS,
    ENEMY_PROJECTILE_HIT_RADIUS,
    FPS,
    LARGE_ENEMY_HIT_RADIUS,
    MAX_INVENTORY,
    PLAYER_HIT_RADIUS,
    PLAYER_MELEE_ARC_DOT,
    PLAYER_MELEE_RANGE,
    PLAYER_PROJECTILE_HIT_RADIUS,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    TILE_H,
    TILE_W,
    UI_SCALE,
    WALK_ANIMATION_RATE,
    SlashEffect,
)
from .content import (
    ARCHETYPES,
    ARMOR_DEFINITIONS,
    DUNGEON_THEMES,
    ENEMY_DEFINITIONS,
    FINAL_ROOM_ENEMY_DEFINITIONS,
    RUN_MODIFIERS,
    SECRET_TYPES,
    SHRINE_TYPES,
    TRAP_DEFINITIONS,
    WEAPON_DEFINITIONS,
    EnemyDefinition,
)
from .dungeon import MAP_H, MAP_W, Dungeon
from .menus import MenuRenderer
from .models import (
    Archetype,
    Color,
    Enemy,
    FloatingText,
    Item,
    Player,
    Projectile,
    RunStats,
    SecretCache,
    Shrine,
    Trap,
)
from .rendering import RenderingMixin
from .save_system import SaveLoadMixin
from .sprites import PixelSpriteAtlas


class Game(SaveLoadMixin, RenderingMixin):
    def __init__(
        self,
        screen_size: tuple[int, int] | None = None,
        headless: bool = False,
        save_path: str | Path | None = None,
    ) -> None:
        pygame.init()
        pygame.display.set_caption(f"Arch Rogue {__version__}")
        self.save_path = (
            Path(save_path) if save_path else Path.home() / ".arch_rogue_run.json"
        )
        self.options_path = Path.home() / ".arch_rogue_options.json"
        self.audio_enabled = True
        self.music_enabled = False
        self.fullscreen = False
        self.ui_scale = UI_SCALE
        self.last_save_error = ""
        self.last_load_error = ""
        self.load_options()
        if screen_size is None:
            display_info = pygame.display.Info()
            screen_size = (display_info.current_w, display_info.current_h)
        self.windowed_size = screen_size
        self.screen = self.apply_display_mode(headless=headless)
        self.clock = pygame.time.Clock()
        self.rebuild_fonts()
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
        self.state = "title"
        self.audio_available = self.initialize_audio(headless)
        self.sound_cache: dict[str, pygame.mixer.Sound] = {}
        self.menus = MenuRenderer(self, ARCHETYPES, DUNGEON_DEPTH)

    def display_size(self) -> tuple[int, int]:
        try:
            sizes = pygame.display.get_desktop_sizes()
            if sizes:
                return sizes[0]
        except pygame.error:
            pass
        display_info = pygame.display.Info()
        return display_info.current_w, display_info.current_h

    def apply_display_mode(self, headless: bool = False) -> pygame.Surface:
        if headless:
            return pygame.display.set_mode(self.windowed_size, pygame.HIDDEN)
        if self.fullscreen:
            # Use SDL's scaled fullscreen path so the game surface is expanded to
            # the actual monitor instead of being placed unscaled in the top-left
            # when the requested logical size differs from the desktop mode.
            return pygame.display.set_mode(
                (SCREEN_WIDTH, SCREEN_HEIGHT), pygame.FULLSCREEN | pygame.SCALED
            )
        return pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)

    def rebuild_fonts(self) -> None:
        self.font = pygame.font.Font(None, 24 * self.ui_scale)
        self.small_font = pygame.font.Font(None, 19 * self.ui_scale)
        self.big_font = pygame.font.Font(None, 56 * self.ui_scale)

    def options_to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "audio_enabled": self.audio_enabled,
            "music_enabled": self.music_enabled,
            "fullscreen": self.fullscreen,
            "ui_scale": self.ui_scale,
        }

    def load_options(self) -> bool:
        try:
            data = json.loads(self.options_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        try:
            self.audio_enabled = bool(data.get("audio_enabled", True))
            self.music_enabled = bool(data.get("music_enabled", False))
            self.fullscreen = bool(data.get("fullscreen", False))
            self.ui_scale = max(1, min(4, int(data.get("ui_scale", UI_SCALE))))
        except (TypeError, ValueError):
            return False
        return True

    def save_options(self) -> bool:
        try:
            self.options_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = Path(f"{self.options_path}.tmp")
            tmp_path.write_text(
                json.dumps(self.options_to_dict(), indent=2), encoding="utf-8"
            )
            tmp_path.replace(self.options_path)
        except (OSError, TypeError, ValueError):
            return False
        return True

    def initialize_audio(self, headless: bool) -> bool:
        if headless:
            return False
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=22050, size=-16, channels=1)
        except pygame.error:
            return False
        return True

    def play_sfx(self, name: str) -> None:
        if not self.audio_enabled or not self.audio_available:
            return
        try:
            sound = self.sound_cache.get(name)
            if sound is None:
                frequency = {
                    "start": 330,
                    "pickup": 660,
                    "hit": 190,
                    "shrine": 520,
                    "stairs": 430,
                    "victory": 784,
                    "death": 120,
                }.get(name, 440)
                sound = self.make_tone(frequency, 0.08)
                self.sound_cache[name] = sound
            sound.play()
        except pygame.error:
            self.audio_available = False

    def make_tone(self, frequency: int, duration: float) -> pygame.mixer.Sound:
        sample_rate = 22050
        amplitude = 3600
        sample_count = max(1, int(sample_rate * duration))
        frames = bytearray()
        for index in range(sample_count):
            fade = 1.0 - index / sample_count
            value = int(
                math.sin(math.tau * frequency * index / sample_rate) * amplitude * fade
            )
            frames.extend(struct.pack("<h", value))
        return pygame.mixer.Sound(buffer=bytes(frames))

    def save_exists(self) -> bool:
        return self.save_path.exists()

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
        self.apply_starting_loadout()
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
        self.play_sfx("start")
        self.save_run()

    def descend_to_next_depth(self) -> None:
        if self.current_depth >= DUNGEON_DEPTH:
            self.state = "victory"
            self.play_sfx("victory")
            self.delete_save()
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
        self.play_sfx("stairs")
        self.save_run()

    def apply_starting_loadout(self) -> None:
        loadouts = {
            "Warden": (
                Item("Warden Arming Sword", "weapon", power=3, rarity="Common"),
                Item("Warden Mail", "armor", defense=3, rarity="Common"),
            ),
            "Rogue": (
                Item("Twin Fang Knife", "weapon", power=6, rarity="Common"),
                Item("Shadow Jerkin", "armor", defense=1, rarity="Common"),
            ),
            "Arcanist": (
                Item("Runed Wand", "weapon", power=1, rarity="Common"),
                Item("Apprentice Mantle", "armor", defense=1, rarity="Common"),
            ),
            "Acolyte": (
                Item("Pilgrim Censer", "weapon", power=2, rarity="Common"),
                Item("Boneweave Mantle", "armor", defense=2, rarity="Common"),
            ),
            "Ranger": (
                Item("Yew Longbow", "weapon", power=5, rarity="Common"),
                Item("Trail Leathers", "armor", defense=2, rarity="Common"),
            ),
        }
        weapon, armor = loadouts.get(self.player.class_name, loadouts["Warden"])
        self.player.equipment["weapon"] = weapon
        self.player.equipment["armor"] = armor

    def _populate_dungeon(self) -> None:
        final_room_index = len(self.dungeon.rooms) - 1
        for room_index, room in enumerate(self.dungeon.rooms[1:], start=1):
            is_final_room = room_index == final_room_index
            count = self.rng.randrange(1, 4)
            if self.current_depth <= 2:
                count = max(1, count - 1)
            elif self.current_depth >= 7:
                count += 1
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
                depth_damage = max(0, self.current_depth - 3)
                self.traps.append(
                    Trap(
                        tx,
                        ty,
                        kind,
                        self.rng.randrange(min_damage, max_damage + 1) + depth_damage,
                    )
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
        depth_multiplier = 1.0 + max(0, self.current_depth - 1) * 0.045
        enemy.max_hp = max(
            1,
            int(
                enemy.max_hp * self.run_modifier.enemy_hp_multiplier * depth_multiplier
            ),
        )
        enemy.hp = enemy.max_hp
        enemy.damage += (
            self.run_modifier.enemy_damage_bonus + max(0, self.current_depth - 4) // 2
        )
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
            elif event.type == pygame.VIDEORESIZE and not self.fullscreen:
                self.windowed_size = (max(640, event.w), max(480, event.h))
                self.screen = pygame.display.set_mode(
                    self.windowed_size, pygame.RESIZABLE
                )
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if self.state in ("options", "about"):
                        self.state = "title"
                    else:
                        if self.state == "playing":
                            self.save_run()
                        self.running = False
                elif self.state == "title":
                    if event.key in (pygame.K_RETURN, pygame.K_n):
                        self.state = "archetype_select"
                    elif event.key in (pygame.K_l, pygame.K_r) and self.save_exists():
                        self.load_run()
                    elif event.key == pygame.K_o:
                        self.state = "options"
                    elif event.key in (pygame.K_a, pygame.K_c):
                        self.state = "about"
                    elif event.key in (pygame.K_h, pygame.K_SLASH):
                        self.state = "about"
                elif self.state == "options":
                    if event.key == pygame.K_a:
                        self.audio_enabled = not self.audio_enabled
                        self.save_options()
                    elif event.key == pygame.K_m:
                        self.music_enabled = not self.music_enabled
                        self.save_options()
                    elif event.key == pygame.K_f:
                        if not self.fullscreen:
                            self.windowed_size = self.screen.get_size()
                        self.fullscreen = not self.fullscreen
                        self.screen = self.apply_display_mode()
                        self.save_options()
                    elif event.key in (pygame.K_EQUALS, pygame.K_PLUS):
                        self.ui_scale = min(4, self.ui_scale + 1)
                        self.rebuild_fonts()
                        self.save_options()
                    elif event.key in (pygame.K_MINUS, pygame.K_UNDERSCORE):
                        self.ui_scale = max(1, self.ui_scale - 1)
                        self.rebuild_fonts()
                        self.save_options()
                    elif event.key in (pygame.K_RETURN, pygame.K_BACKSPACE, pygame.K_o):
                        self.state = "title"
                elif self.state == "about":
                    if event.key in (
                        pygame.K_RETURN,
                        pygame.K_BACKSPACE,
                        pygame.K_a,
                        pygame.K_h,
                    ):
                        self.state = "title"
                elif self.state == "archetype_select":
                    if event.key == pygame.K_BACKSPACE:
                        self.state = "title"
                    else:
                        select_limit = min(len(ARCHETYPES), 9)
                        if pygame.K_1 <= event.key < pygame.K_1 + select_limit:
                            self.restart(ARCHETYPES[event.key - pygame.K_1])
                        elif event.key in (pygame.K_RIGHT, pygame.K_DOWN):
                            index = (
                                ARCHETYPES.index(self.selected_archetype) + 1
                            ) % len(ARCHETYPES)
                            self.selected_archetype = ARCHETYPES[index]
                        elif event.key in (pygame.K_LEFT, pygame.K_UP):
                            index = (
                                ARCHETYPES.index(self.selected_archetype) - 1
                            ) % len(ARCHETYPES)
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

        if self.player.hp <= 0 and self.state == "playing":
            self.state = "dead"
            self.play_sfx("death")
            self.delete_save()

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

    def skill_names(self) -> tuple[str, str, str, str]:
        names = {
            "Warden": ("Shield Bash", "Guard Bolt", "Bulwark Wave", "Guard Step"),
            "Rogue": ("Backstab", "Knife Fan", "Smoke Burst", "Shadow Dash"),
            "Arcanist": ("Mage Strike", "Arc Bolt", "Frost Nova", "Blink"),
            "Acolyte": ("Blood Rite", "Spirit Bolt", "Blood Nova", "Dark Step"),
            "Ranger": ("Hawk Slash", "Multishot", "Snare Nova", "Vault"),
        }
        return names.get(self.player.class_name, ("Slash", "Bolt", "Nova", "Dash"))

    def skill_color(self) -> Color:
        colors = {
            "Warden": (235, 205, 120),
            "Rogue": (170, 230, 150),
            "Arcanist": (120, 210, 255),
            "Acolyte": (220, 95, 140),
            "Ranger": (150, 215, 105),
        }
        return colors.get(self.player.class_name, (120, 210, 255))

    def melee_stamina_cost(self) -> int:
        return 9 if self.player.class_name == "Rogue" else 12

    def melee_cooldown(self) -> float:
        return 0.30 if self.player.class_name == "Rogue" else 0.36

    def bolt_mana_cost(self) -> int:
        return 7 if self.player.class_name in ("Arcanist", "Ranger") else 10

    def bolt_cooldown(self) -> float:
        return 0.38 if self.player.class_name in ("Arcanist", "Ranger") else 0.48

    def nova_mana_cost(self) -> int:
        return 14 if self.player.class_name in ("Arcanist", "Acolyte") else 18

    def nova_cooldown(self) -> float:
        return 2.65 if self.player.class_name == "Arcanist" else 3.2

    def dash_stamina_cost(self) -> int:
        return 12 if self.player.class_name in ("Rogue", "Ranger") else 18

    def dash_cooldown(self) -> float:
        return 0.62 if self.player.class_name == "Ranger" else 0.85

    def take_player_damage(self, raw_damage: int, source: str = "hit") -> int:
        if self.player.class_name == "Rogue" and self.rng.random() < 0.12:
            self.floaters.append(
                FloatingText(
                    "Evaded", self.player.x, self.player.y - 0.2, (170, 220, 170)
                )
            )
            return 0
        armor_bonus = (
            2 if self.player.class_name == "Warden" and source == "melee" else 0
        )
        amount = max(1, raw_damage - self.player.armor() - armor_bonus)
        if self.player.class_name == "Acolyte" and self.player.mana >= 4:
            self.player.mana -= 4
            amount = max(1, amount - 3)
        self.player.hp -= amount
        self.run_stats.damage_taken += amount
        return amount

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
        stamina_regen = 38 if self.player.class_name == "Ranger" else 30
        mana_regen = 8 if self.player.class_name == "Arcanist" else 5
        self.player.stamina = min(
            self.player.max_stamina, self.player.stamina + stamina_regen * dt
        )
        self.player.mana = min(self.player.max_mana, self.player.mana + mana_regen * dt)

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
        amount = self.take_player_damage(raw, source="melee")
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
                    amount = self.take_player_damage(
                        projectile.damage, source="projectile"
                    )
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
            amount = self.take_player_damage(trap.damage, source="trap")
            self.run_stats.traps_triggered += 1
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
        stamina_cost = self.melee_stamina_cost()
        if self.player.melee_timer > 0 or self.player.stamina < stamina_cost:
            return
        self.player.melee_timer = self.melee_cooldown()
        self.player.stamina -= stamina_cost
        target = self.enemy_in_melee_arc()
        if target:
            tx = (self.player.x + target.x) * 0.5
            ty = (self.player.y + target.y) * 0.5
        else:
            tx = self.player.x + self.player.facing_x * 0.9
            ty = self.player.y + self.player.facing_y * 0.9
        self.slashes.append((tx, ty, 0.18, self.player.facing_x, self.player.facing_y))
        if target:
            targets = [target]
            if self.player.class_name == "Warden":
                targets = self.enemies_in_melee_arc(reach_bonus=0.18)[:3]
            for index, enemy in enumerate(list(targets)):
                damage = self.player.melee_damage() + self.rng.randrange(-3, 5)
                if index > 0:
                    damage = max(1, int(damage * 0.62))
                if self.player.class_name == "Rogue" and self.rng.random() < 0.22:
                    damage = int(damage * 1.75)
                    self.floaters.append(
                        FloatingText(
                            "Critical", enemy.x, enemy.y - 0.45, (255, 225, 120)
                        )
                    )
                if self.player.class_name == "Warden":
                    enemy.attack_timer = max(enemy.attack_timer, 0.35)
                self.damage_enemy(
                    enemy,
                    damage,
                    knockback_from=(self.player.facing_x, self.player.facing_y),
                )
                if self.player.class_name == "Acolyte":
                    self.player.hp = min(self.player.max_hp, self.player.hp + 2)

    def player_cast_bolt(self) -> None:
        mana_cost = self.bolt_mana_cost()
        if self.player.bolt_timer > 0 or self.player.mana < mana_cost:
            return
        self.player.bolt_timer = self.bolt_cooldown()
        self.player.mana -= mana_cost
        damage = 14 + self.player.level * 2 + self.player.spell_bonus
        if self.player.class_name == "Acolyte":
            damage += max(0, self.player.max_hp - self.player.hp) // 12
        angles = [0.0]
        if self.player.class_name == "Ranger":
            angles = [-0.16, 0.0, 0.16]
        elif self.player.class_name == "Arcanist":
            angles = [-0.06, 0.06]
        for angle in angles:
            dx = self.player.facing_x * math.cos(
                angle
            ) - self.player.facing_y * math.sin(angle)
            dy = self.player.facing_x * math.sin(
                angle
            ) + self.player.facing_y * math.cos(angle)
            self.projectiles.append(
                Projectile(
                    self.player.x,
                    self.player.y,
                    dx * 9.0,
                    dy * 9.0,
                    damage if abs(angle) <= 0.001 else max(1, damage - 4),
                    "player",
                    (70, 165, 255),
                    ttl=1.4,
                )
            )

    def player_cast_nova(self) -> None:
        mana_cost = self.nova_mana_cost()
        if self.player.nova_timer > 0 or self.player.mana < mana_cost:
            return
        self.player.nova_timer = self.nova_cooldown()
        self.player.mana -= mana_cost
        hits = 0
        for enemy in list(self.enemies):
            dx = enemy.x - self.player.x
            dy = enemy.y - self.player.y
            distance = math.hypot(dx, dy)
            if distance <= (2.85 if self.player.class_name == "Arcanist" else 2.45):
                hits += 1
                damage = (
                    10
                    + self.player.level * 2
                    + self.player.spell_bonus
                    + self.rng.randrange(0, 5)
                )
                if self.player.class_name == "Ranger":
                    enemy.attack_timer = max(enemy.attack_timer, 0.8)
                if self.player.class_name == "Acolyte":
                    self.player.hp = min(self.player.max_hp, self.player.hp + 3)
                direction = (
                    (dx / distance, dy / distance)
                    if distance > 0.001
                    else (self.player.facing_x, self.player.facing_y)
                )
                self.damage_enemy(enemy, damage, knockback_from=direction)
        self.floaters.append(
            FloatingText(
                f"{self.skill_names()[2]}{f' x{hits}' if hits else ''}",
                self.player.x,
                self.player.y - 0.5,
                self.skill_color(),
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
        stamina_cost = self.dash_stamina_cost()
        if self.player.dash_timer > 0 or self.player.stamina < stamina_cost:
            return
        self.player.dash_timer = self.dash_cooldown()
        self.player.stamina -= stamina_cost
        steps = 11 if self.player.class_name == "Ranger" else 8
        for _ in range(steps):
            self.move_actor(
                self.player,
                self.player.facing_x * 0.20,
                self.player.facing_y * 0.20,
            )
        self.floaters.append(
            FloatingText(
                self.skill_names()[3],
                self.player.x,
                self.player.y - 0.4,
                self.skill_color(),
                ttl=0.45,
            )
        )

    def enemies_in_melee_arc(self, reach_bonus: float = 0.0) -> list[Enemy]:
        candidates: list[tuple[float, Enemy]] = []
        for enemy in self.enemies:
            dx = enemy.x - self.player.x
            dy = enemy.y - self.player.y
            distance = math.hypot(dx, dy)
            if distance > PLAYER_MELEE_RANGE + reach_bonus or distance < 0.001:
                continue
            dot = (dx / distance) * self.player.facing_x + (
                dy / distance
            ) * self.player.facing_y
            if dot > PLAYER_MELEE_ARC_DOT:
                candidates.append((distance, enemy))
        return [
            enemy for _distance, enemy in sorted(candidates, key=lambda entry: entry[0])
        ]

    def enemy_in_melee_arc(self) -> Enemy | None:
        enemies = self.enemies_in_melee_arc()
        return enemies[0] if enemies else None

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
        else:
            self.play_sfx("hit")

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
        self.save_run()

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
            self.play_sfx("victory")
            self.delete_save()
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
            self.play_sfx("pickup")
            self.save_run()

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
        self.play_sfx("pickup")
        self.save_run()

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
        self.play_sfx("shrine")
        self.save_run()

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
        self.save_run()

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
        self.play_sfx("pickup")
        self.save_run()

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
        self.play_sfx("pickup")
        self.save_run()

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


def main() -> None:
    Game().run()
