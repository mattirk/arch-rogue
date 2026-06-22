from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import IntEnum
from typing import cast

import pygame

SCREEN_WIDTH = 2560
SCREEN_HEIGHT = 1440
FPS = 60
WORLD_SCALE = 2
TILE_W = 64 * WORLD_SCALE
TILE_H = 32 * WORLD_SCALE
MAP_W = 72
MAP_H = 72
MAX_INVENTORY = 9
UI_SCALE = 2

Color = tuple[int, int, int]


class Tile(IntEnum):
    WALL = 0
    FLOOR = 1
    STAIRS = 2


@dataclass(frozen=True)
class Room:
    x: int
    y: int
    w: int
    h: int

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.w // 2, self.y + self.h // 2

    def intersects(self, other: "Room", padding: int = 1) -> bool:
        return not (
            self.x + self.w + padding < other.x
            or other.x + other.w + padding < self.x
            or self.y + self.h + padding < other.y
            or other.y + other.h + padding < self.y
        )

    def random_point(self, rng: random.Random) -> tuple[float, float]:
        return rng.randrange(self.x + 1, self.x + self.w - 1) + 0.5, rng.randrange(
            self.y + 1, self.y + self.h - 1
        ) + 0.5


@dataclass
class Item:
    name: str
    slot: str
    power: int = 0
    defense: int = 0
    heal: int = 0
    rarity: str = "Common"
    x: float = 0.0
    y: float = 0.0

    @property
    def label(self) -> str:
        if self.slot == "potion":
            return f"{self.name} (+{self.heal} HP)"
        if self.slot == "weapon":
            return f"{self.name} (+{self.power} dmg)"
        if self.slot == "armor":
            return f"{self.name} (+{self.defense} armor)"
        return self.name


@dataclass
class FloatingText:
    text: str
    x: float
    y: float
    color: Color
    ttl: float = 0.9

    def update(self, dt: float) -> None:
        self.ttl -= dt
        self.y -= dt * 0.8


@dataclass
class Projectile:
    x: float
    y: float
    vx: float
    vy: float
    damage: int
    owner: str
    color: Color
    ttl: float = 1.6
    radius: float = 0.18

    def update(self, dt: float, dungeon: "Dungeon") -> bool:
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.ttl -= dt
        return self.ttl > 0 and dungeon.is_floor(self.x, self.y)


@dataclass
class Enemy:
    name: str
    kind: str
    x: float
    y: float
    max_hp: int
    hp: int
    speed: float
    damage: int
    xp: int
    attack_range: float
    attack_cooldown: float
    attack_timer: float = 0.0
    aggro_range: float = 8.0
    color: Color = (170, 70, 65)
    facing_x: float = 1.0
    facing_y: float = 0.0
    moving: bool = False
    move_x: float = 1.0
    move_y: float = 0.0
    anim_time: float = 0.0

    @property
    def alive(self) -> bool:
        return self.hp > 0


@dataclass
class Player:
    x: float
    y: float
    max_hp: int = 110
    hp: int = 110
    max_mana: int = 45
    mana: float = 45
    max_stamina: int = 100
    stamina: float = 100
    speed: float = 4.6
    level: int = 1
    xp: int = 0
    next_xp: int = 60
    facing_x: float = 1.0
    facing_y: float = 0.0
    moving: bool = False
    move_x: float = 1.0
    move_y: float = 0.0
    anim_time: float = 0.0
    melee_timer: float = 0.0
    bolt_timer: float = 0.0
    inventory: list[Item] = field(default_factory=list)
    equipment: dict[str, Item | None] = field(
        default_factory=lambda: {"weapon": None, "armor": None}
    )

    def melee_damage(self) -> int:
        weapon = self.equipment.get("weapon")
        return 12 + self.level * 2 + (weapon.power if weapon else 0)

    def armor(self) -> int:
        armor = self.equipment.get("armor")
        return armor.defense if armor else 0

    def gain_xp(self, amount: int) -> bool:
        self.xp += amount
        if self.xp < self.next_xp:
            return False
        self.xp -= self.next_xp
        self.level += 1
        self.next_xp = int(self.next_xp * 1.45)
        self.max_hp += 12
        self.hp = self.max_hp
        self.max_mana += 5
        self.mana = self.max_mana
        self.max_stamina += 5
        self.stamina = self.max_stamina
        return True


class Dungeon:
    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.tiles: list[list[Tile]] = []
        self.rooms: list[Room] = []
        self.stairs: tuple[int, int] = (0, 0)
        self.generate()

    def generate(self) -> None:
        for _ in range(20):
            self.tiles = [[Tile.WALL for _ in range(MAP_H)] for _ in range(MAP_W)]
            self.rooms = []
            for _attempt in range(180):
                w = self.rng.randrange(6, 13)
                h = self.rng.randrange(6, 12)
                x = self.rng.randrange(2, MAP_W - w - 2)
                y = self.rng.randrange(2, MAP_H - h - 2)
                room = Room(x, y, w, h)
                if any(room.intersects(existing, padding=2) for existing in self.rooms):
                    continue
                self._carve_room(room)
                if self.rooms:
                    self._connect(self.rooms[-1].center, room.center)
                self.rooms.append(room)
                if len(self.rooms) >= 14:
                    break
            if len(self.rooms) >= 8:
                self.stairs = self.rooms[-1].center
                sx, sy = self.stairs
                self.tiles[sx][sy] = Tile.STAIRS
                return
        raise RuntimeError("Could not generate a valid dungeon")

    def _carve_room(self, room: Room) -> None:
        for x in range(room.x, room.x + room.w):
            for y in range(room.y, room.y + room.h):
                self.tiles[x][y] = Tile.FLOOR

    def _connect(self, a: tuple[int, int], b: tuple[int, int]) -> None:
        ax, ay = a
        bx, by = b
        if self.rng.random() < 0.5:
            self._carve_h(ax, bx, ay)
            self._carve_v(ay, by, bx)
        else:
            self._carve_v(ay, by, ax)
            self._carve_h(ax, bx, by)

    def _carve_h(self, x1: int, x2: int, y: int) -> None:
        for x in range(min(x1, x2), max(x1, x2) + 1):
            self._carve_corridor_tile(x, y)

    def _carve_v(self, y1: int, y2: int, x: int) -> None:
        for y in range(min(y1, y2), max(y1, y2) + 1):
            self._carve_corridor_tile(x, y)

    def _carve_corridor_tile(self, x: int, y: int) -> None:
        for ox, oy in ((0, 0), (1, 0), (0, 1)):
            tx, ty = x + ox, y + oy
            if 1 <= tx < MAP_W - 1 and 1 <= ty < MAP_H - 1:
                self.tiles[tx][ty] = Tile.FLOOR

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < MAP_W and 0 <= y < MAP_H

    def is_floor(self, x: float, y: float) -> bool:
        tx, ty = int(x), int(y)
        return self.in_bounds(tx, ty) and self.tiles[tx][ty] != Tile.WALL

    def blocked_for_radius(self, x: float, y: float, radius: float = 0.27) -> bool:
        for ox in (-radius, radius):
            for oy in (-radius, radius):
                if not self.is_floor(x + ox, y + oy):
                    return True
        return False


class PixelSpriteAtlas:
    """Procedural JRPG-style pixel sprites for all gameplay entities.

    The prototype intentionally keeps art source in code for now so the game remains
    easy to run without an asset pipeline. Sprites are authored at tiny resolutions
    and scaled with nearest-neighbor filtering for a chunky pixel-art look.
    """

    SCALE = 6

    def __init__(self) -> None:
        self.player = self._scale(self._warden())
        self.enemies = {
            "Ghoul": self._scale(self._ghoul()),
            "Cultist": self._scale(self._cultist()),
            "Gate Warden": self._scale(self._gate_warden()),
        }
        self.items = {
            "potion": self._scale(self._potion()),
            "weapon": self._scale(self._weapon()),
            "armor": self._scale(self._armor()),
        }
        self.projectiles = {
            "player": self._scale(self._blue_bolt()),
            "enemy": self._scale(self._void_bolt()),
        }
        self.slash = self._scale(self._slash())

    def _surface(self, w: int, h: int) -> pygame.Surface:
        return pygame.Surface((w, h), pygame.SRCALPHA)

    def _rect(
        self, surface: pygame.Surface, x: int, y: int, w: int, h: int, color: Color
    ) -> None:
        pygame.draw.rect(surface, color, (x, y, w, h))

    def _dot(self, surface: pygame.Surface, x: int, y: int, color: Color) -> None:
        self._rect(surface, x, y, 1, 1, color)

    def _line(
        self,
        surface: pygame.Surface,
        start: tuple[int, int],
        end: tuple[int, int],
        color: Color,
    ) -> None:
        pygame.draw.line(surface, color, start, end)

    def _scale(
        self, surface: pygame.Surface, scale: int | None = None
    ) -> pygame.Surface:
        factor = scale or self.SCALE
        return pygame.transform.scale(
            surface, (surface.get_width() * factor, surface.get_height() * factor)
        )

    def _warden(self) -> pygame.Surface:
        s = self._surface(18, 24)
        outline = (19, 24, 35)
        skin = (215, 158, 105)
        hair = (62, 43, 35)
        blue = (45, 93, 164)
        blue_hi = (76, 140, 220)
        steel = (154, 168, 178)
        steel_hi = (220, 226, 218)
        leather = (74, 48, 39)

        self._rect(s, 6, 2, 6, 2, hair)
        self._rect(s, 5, 4, 8, 5, outline)
        self._rect(s, 6, 4, 6, 5, skin)
        self._rect(s, 5, 5, 2, 2, hair)
        self._rect(s, 11, 5, 2, 2, hair)
        self._rect(s, 6, 10, 6, 2, steel)
        self._rect(s, 3, 11, 12, 8, outline)
        self._rect(s, 5, 11, 8, 8, blue)
        self._rect(s, 7, 12, 4, 6, blue_hi)
        self._rect(s, 3, 12, 3, 5, steel)
        self._rect(s, 12, 12, 3, 5, steel)
        self._rect(s, 13, 8, 2, 9, steel_hi)
        self._rect(s, 14, 6, 1, 4, steel_hi)
        self._rect(s, 5, 19, 3, 3, leather)
        self._rect(s, 10, 19, 3, 3, leather)
        self._rect(s, 4, 22, 4, 2, outline)
        self._rect(s, 10, 22, 4, 2, outline)
        self._rect(s, 7, 6, 1, 1, (40, 35, 32))
        self._rect(s, 10, 6, 1, 1, (40, 35, 32))
        self._rect(s, 8, 8, 2, 1, (170, 105, 78))
        self._rect(s, 5, 10, 8, 1, (108, 82, 50))
        self._rect(s, 4, 15, 10, 1, (30, 58, 116))
        self._rect(s, 6, 16, 6, 1, (235, 205, 112))
        self._rect(s, 4, 18, 2, 1, steel_hi)
        self._rect(s, 12, 18, 2, 1, steel_hi)
        self._rect(s, 8, 20, 2, 2, outline)
        self._rect(s, 3, 13, 1, 3, steel_hi)
        self._rect(s, 14, 13, 1, 3, (86, 91, 103))
        self._rect(s, 15, 9, 1, 8, (96, 104, 112))
        self._dot(s, 16, 7, steel_hi)
        return s

    def _ghoul(self) -> pygame.Surface:
        s = self._surface(18, 22)
        outline = (31, 20, 22)
        flesh = (118, 154, 94)
        flesh_hi = (161, 189, 116)
        rot = (95, 54, 59)
        cloth = (72, 55, 47)
        eye = (238, 226, 126)

        self._rect(s, 5, 3, 8, 6, outline)
        self._rect(s, 6, 4, 6, 5, flesh)
        self._rect(s, 8, 5, 2, 1, eye)
        self._rect(s, 3, 9, 12, 8, outline)
        self._rect(s, 5, 9, 8, 8, flesh)
        self._rect(s, 6, 10, 4, 3, flesh_hi)
        self._rect(s, 3, 11, 3, 7, flesh)
        self._rect(s, 12, 11, 3, 7, flesh)
        self._rect(s, 6, 15, 6, 3, rot)
        self._rect(s, 5, 18, 3, 3, cloth)
        self._rect(s, 10, 18, 3, 3, cloth)
        self._rect(s, 4, 21, 4, 1, outline)
        self._rect(s, 10, 21, 4, 1, outline)
        self._rect(s, 6, 6, 1, 1, eye)
        self._rect(s, 11, 6, 1, 1, eye)
        self._rect(s, 8, 8, 3, 1, (50, 29, 32))
        self._rect(s, 5, 12, 2, 1, flesh_hi)
        self._rect(s, 9, 13, 3, 1, (72, 102, 70))
        self._rect(s, 4, 14, 1, 4, (64, 102, 70))
        self._rect(s, 13, 14, 1, 4, (64, 102, 70))
        self._rect(s, 2, 17, 2, 1, (202, 202, 162))
        self._rect(s, 14, 17, 2, 1, (202, 202, 162))
        self._rect(s, 7, 16, 1, 2, (56, 35, 38))
        self._rect(s, 10, 16, 1, 2, (56, 35, 38))
        self._dot(s, 12, 10, rot)
        return s

    def _cultist(self) -> pygame.Surface:
        s = self._surface(18, 23)
        outline = (22, 18, 33)
        robe = (78, 44, 132)
        robe_hi = (123, 76, 183)
        trim = (184, 138, 218)
        face = (44, 29, 54)
        flame = (205, 79, 230)

        self._rect(s, 5, 2, 8, 7, outline)
        self._rect(s, 6, 3, 6, 6, robe)
        self._rect(s, 7, 6, 4, 2, face)
        self._rect(s, 3, 9, 12, 11, outline)
        self._rect(s, 5, 9, 8, 11, robe)
        self._rect(s, 7, 10, 4, 8, robe_hi)
        self._rect(s, 4, 12, 2, 5, trim)
        self._rect(s, 12, 12, 2, 5, trim)
        self._rect(s, 14, 8, 1, 4, flame)
        self._rect(s, 13, 10, 3, 2, flame)
        self._rect(s, 4, 20, 10, 2, outline)
        self._rect(s, 5, 4, 1, 4, (54, 31, 92))
        self._rect(s, 12, 4, 1, 4, (42, 25, 70))
        self._rect(s, 8, 7, 2, 1, (184, 138, 218))
        self._rect(s, 8, 12, 2, 2, trim)
        self._rect(s, 6, 15, 1, 4, trim)
        self._rect(s, 11, 15, 1, 4, (63, 39, 105))
        self._rect(s, 3, 17, 12, 1, (47, 32, 82))
        self._rect(s, 14, 6, 1, 2, (255, 175, 255))
        self._dot(s, 15, 8, (255, 220, 255))
        self._dot(s, 13, 9, (255, 220, 255))
        self._rect(s, 4, 21, 3, 1, trim)
        self._rect(s, 11, 21, 3, 1, trim)
        return s

    def _gate_warden(self) -> pygame.Surface:
        s = self._surface(20, 25)
        outline = (29, 23, 22)
        brass = (171, 105, 48)
        brass_hi = (230, 156, 72)
        steel = (126, 132, 128)
        dark = (58, 46, 43)
        eye = (235, 65, 48)

        self._rect(s, 6, 2, 8, 6, outline)
        self._rect(s, 7, 3, 6, 5, brass)
        self._rect(s, 8, 5, 4, 1, eye)
        self._rect(s, 3, 9, 14, 10, outline)
        self._rect(s, 5, 9, 10, 10, steel)
        self._rect(s, 7, 10, 6, 7, brass)
        self._rect(s, 8, 11, 4, 4, brass_hi)
        self._rect(s, 2, 10, 4, 6, steel)
        self._rect(s, 14, 10, 4, 6, steel)
        self._rect(s, 16, 6, 2, 12, brass_hi)
        self._rect(s, 17, 4, 1, 4, brass_hi)
        self._rect(s, 6, 19, 3, 4, dark)
        self._rect(s, 11, 19, 3, 4, dark)
        self._rect(s, 5, 23, 5, 2, outline)
        self._rect(s, 10, 23, 5, 2, outline)
        self._rect(s, 5, 1, 3, 2, brass_hi)
        self._rect(s, 12, 1, 3, 2, brass_hi)
        self._rect(s, 7, 6, 6, 1, (98, 48, 34))
        self._rect(s, 6, 10, 8, 1, (210, 148, 70))
        self._rect(s, 6, 14, 8, 1, (91, 98, 98))
        self._rect(s, 9, 12, 2, 3, (255, 202, 90))
        self._rect(s, 3, 16, 4, 2, (78, 84, 86))
        self._rect(s, 13, 16, 4, 2, (78, 84, 86))
        self._rect(s, 1, 11, 3, 5, dark)
        self._rect(s, 16, 12, 3, 5, brass)
        self._rect(s, 17, 13, 1, 3, brass_hi)
        self._dot(s, 9, 4, eye)
        self._dot(s, 11, 4, eye)
        return s

    def _potion(self) -> pygame.Surface:
        s = self._surface(12, 14)
        outline = (32, 22, 30)
        glass = (154, 210, 222)
        liquid = (210, 54, 82)
        cork = (116, 74, 39)
        shine = (238, 235, 208)
        self._rect(s, 5, 1, 2, 3, cork)
        self._rect(s, 4, 4, 4, 1, outline)
        self._rect(s, 3, 5, 6, 8, outline)
        self._rect(s, 4, 5, 4, 3, glass)
        self._rect(s, 4, 8, 4, 4, liquid)
        self._rect(s, 5, 6, 1, 2, shine)
        self._rect(s, 6, 2, 1, 2, (82, 49, 27))
        self._rect(s, 4, 7, 4, 1, (205, 238, 245))
        self._rect(s, 5, 10, 2, 1, (248, 96, 116))
        self._rect(s, 4, 12, 4, 1, (125, 28, 52))
        self._dot(s, 8, 6, shine)
        return s

    def _weapon(self) -> pygame.Surface:
        s = self._surface(14, 14)
        blade = (216, 226, 222)
        shade = (128, 141, 148)
        guard = (190, 132, 58)
        grip = (78, 46, 32)
        self._rect(s, 8, 1, 2, 7, blade)
        self._rect(s, 7, 3, 1, 5, shade)
        self._rect(s, 6, 8, 6, 2, guard)
        self._rect(s, 8, 10, 2, 3, grip)
        self._rect(s, 7, 13, 4, 1, guard)
        self._rect(s, 9, 1, 1, 7, (248, 252, 242))
        self._rect(s, 6, 4, 1, 3, blade)
        self._rect(s, 5, 8, 1, 1, (230, 178, 78))
        self._rect(s, 11, 8, 1, 1, (230, 178, 78))
        self._rect(s, 9, 11, 1, 2, (130, 82, 48))
        self._dot(s, 8, 12, (230, 178, 78))
        return s

    def _armor(self) -> pygame.Surface:
        s = self._surface(14, 14)
        outline = (36, 36, 42)
        leather = (99, 66, 46)
        plate = (145, 155, 160)
        hi = (205, 214, 210)
        self._rect(s, 3, 2, 8, 2, outline)
        self._rect(s, 2, 4, 10, 8, outline)
        self._rect(s, 4, 4, 6, 8, leather)
        self._rect(s, 5, 5, 4, 5, plate)
        self._rect(s, 6, 5, 2, 2, hi)
        self._rect(s, 3, 12, 8, 1, outline)
        self._rect(s, 4, 4, 1, 7, (60, 42, 34))
        self._rect(s, 9, 4, 1, 7, (63, 50, 44))
        self._rect(s, 5, 8, 4, 1, (95, 102, 106))
        self._rect(s, 6, 10, 2, 1, (200, 160, 80))
        self._dot(s, 4, 6, hi)
        self._dot(s, 9, 7, (82, 88, 94))
        return s

    def _blue_bolt(self) -> pygame.Surface:
        s = self._surface(14, 10)
        self._rect(s, 2, 4, 9, 2, (68, 170, 255))
        self._rect(s, 5, 2, 5, 6, (86, 215, 255))
        self._rect(s, 10, 3, 3, 4, (68, 170, 255))
        self._rect(s, 8, 4, 3, 2, (240, 250, 255))
        self._rect(s, 0, 3, 3, 1, (36, 92, 190))
        self._rect(s, 0, 6, 3, 1, (36, 92, 190))
        self._dot(s, 12, 5, (240, 250, 255))
        return s

    def _void_bolt(self) -> pygame.Surface:
        s = self._surface(14, 10)
        self._rect(s, 2, 4, 9, 2, (119, 54, 184))
        self._rect(s, 5, 2, 5, 6, (210, 83, 238))
        self._rect(s, 10, 3, 3, 4, (119, 54, 184))
        self._rect(s, 8, 4, 3, 2, (255, 190, 255))
        self._rect(s, 0, 3, 3, 1, (54, 30, 102))
        self._rect(s, 0, 6, 3, 1, (54, 30, 102))
        self._dot(s, 12, 5, (255, 220, 255))
        return s

    def _slash(self) -> pygame.Surface:
        s = self._surface(18, 12)
        pale = (255, 240, 174)
        gold = (225, 174, 74)
        self._rect(s, 2, 7, 4, 2, gold)
        self._rect(s, 5, 5, 4, 2, pale)
        self._rect(s, 8, 3, 4, 2, pale)
        self._rect(s, 11, 2, 3, 2, gold)
        self._rect(s, 14, 1, 2, 1, pale)
        self._rect(s, 3, 8, 5, 1, (146, 90, 42))
        self._rect(s, 6, 6, 7, 1, (255, 252, 210))
        self._dot(s, 13, 4, pale)
        self._dot(s, 16, 2, (255, 252, 210))
        return s


class Game:
    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption("Arch Rogue - Prototype 1")
        self.screen = pygame.display.set_mode(
            (SCREEN_WIDTH, SCREEN_HEIGHT), pygame.RESIZABLE
        )
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 24 * UI_SCALE)
        self.small_font = pygame.font.Font(None, 19 * UI_SCALE)
        self.big_font = pygame.font.Font(None, 56 * UI_SCALE)
        self.sprites = PixelSpriteAtlas()
        self.rng = random.Random()
        self.running = True
        self.inventory_open = False
        self.state = "playing"
        self.elapsed = 0.0
        self.restart()

    def restart(self) -> None:
        self.dungeon = Dungeon(self.rng)
        start_x, start_y = self.dungeon.rooms[0].center
        self.player = Player(start_x + 0.5, start_y + 0.5)
        self.enemies: list[Enemy] = []
        self.items: list[Item] = []
        self.projectiles: list[Projectile] = []
        self.floaters: list[FloatingText] = []
        self.slashes: list[tuple[float, float, float]] = []
        self.inventory_open = False
        self.state = "playing"
        self._populate_dungeon()

    def _populate_dungeon(self) -> None:
        for room_index, room in enumerate(self.dungeon.rooms[1:], start=1):
            count = self.rng.randrange(1, 4)
            if room_index == len(self.dungeon.rooms) - 1:
                count += 2
            for _ in range(count):
                x, y = room.random_point(self.rng)
                if (
                    room_index == len(self.dungeon.rooms) - 1
                    and self.rng.random() < 0.45
                ):
                    enemy = Enemy(
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
                elif self.rng.random() < 0.35:
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
                self.enemies.append(enemy)

            if self.rng.random() < 0.7:
                self.items.append(self._make_loot(*room.random_point(self.rng)))

        sx, sy = self.dungeon.rooms[0].random_point(self.rng)
        self.items.append(
            Item("Minor Healing Potion", "potion", heal=35, rarity="Common", x=sx, y=sy)
        )

    def _make_loot(self, x: float, y: float) -> Item:
        roll = self.rng.random()
        if roll < 0.30:
            return Item(
                "Minor Healing Potion", "potion", heal=35, rarity="Common", x=x, y=y
            )
        if roll < 0.50:
            return Item("Iron Sword", "weapon", power=6, rarity="Magic", x=x, y=y)
        if roll < 0.68:
            return Item("Hunter Axe", "weapon", power=9, rarity="Rare", x=x, y=y)
        if roll < 0.84:
            return Item("Leather Jerkin", "armor", defense=3, rarity="Common", x=x, y=y)
        return Item("Warden Mail", "armor", defense=6, rarity="Magic", x=x, y=y)

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
                elif event.key == pygame.K_i:
                    self.inventory_open = not self.inventory_open
                elif event.key == pygame.K_r and self.state != "playing":
                    self.restart()
                elif event.key == pygame.K_e and self.state == "playing":
                    self.interact()
                elif event.key == pygame.K_q and self.state == "playing":
                    self.use_first_potion()
                elif event.key == pygame.K_SPACE and self.state == "playing":
                    self.player_melee_attack()
                elif event.key == pygame.K_f and self.state == "playing":
                    self.player_cast_bolt()
                elif pygame.K_1 <= event.key <= pygame.K_9 and self.state == "playing":
                    self.use_inventory_slot(event.key - pygame.K_1)
            elif event.type == pygame.MOUSEBUTTONDOWN and self.state == "playing":
                if event.button == 1:
                    self.player_melee_attack()
                elif event.button == 3:
                    self.player_cast_bolt()

    def update(self, dt: float) -> None:
        self.elapsed += dt
        self.update_player_aim()
        self.update_player(dt)
        self.update_enemies(dt)
        self.update_projectiles(dt)
        self.update_floaters(dt)
        self.slashes = [(x, y, ttl - dt) for x, y, ttl in self.slashes if ttl - dt > 0]

        if self.player.hp <= 0:
            self.state = "dead"

    def update_player_aim(self) -> None:
        wx, wy = self.screen_to_world(*pygame.mouse.get_pos())
        dx = wx - self.player.x
        dy = wy - self.player.y
        length = math.hypot(dx, dy)
        if length > 0.001:
            self.player.facing_x = dx / length
            self.player.facing_y = dy / length

    def update_player(self, dt: float) -> None:
        self.player.moving = False
        keys = pygame.key.get_pressed()
        dx = float(keys[pygame.K_d] or keys[pygame.K_RIGHT]) - float(
            keys[pygame.K_a] or keys[pygame.K_LEFT]
        )
        dy = float(keys[pygame.K_s] or keys[pygame.K_DOWN]) - float(
            keys[pygame.K_w] or keys[pygame.K_UP]
        )
        if dx or dy:
            length = math.hypot(dx, dy)
            dx /= length
            dy /= length
            self.move_actor(
                self.player, dx * self.player.speed * dt, dy * self.player.speed * dt
            )

        self.player.melee_timer = max(0.0, self.player.melee_timer - dt)
        self.player.bolt_timer = max(0.0, self.player.bolt_timer - dt)
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

        actual_dx = actor.x - old_x
        actual_dy = actor.y - old_y
        distance = math.hypot(actual_dx, actual_dy)
        if distance > 0.0001:
            actor.moving = True
            actor.move_x = actual_dx / distance
            actor.move_y = actual_dy / distance
            actor.anim_time += distance * 4.8

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

            if enemy.kind == "ranged":
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
                hit = self.first_enemy_near(projectile.x, projectile.y, 0.42)
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
                    < 0.45
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

    def update_floaters(self, dt: float) -> None:
        for floater in self.floaters:
            floater.update(dt)
        self.floaters = [floater for floater in self.floaters if floater.ttl > 0]

    def player_melee_attack(self) -> None:
        if self.player.melee_timer > 0 or self.player.stamina < 12:
            return
        self.player.melee_timer = 0.36
        self.player.stamina -= 12
        tx = self.player.x + self.player.facing_x * 0.9
        ty = self.player.y + self.player.facing_y * 0.9
        self.slashes.append((tx, ty, 0.16))
        target = self.enemy_in_melee_arc()
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
                14 + self.player.level * 2,
                "player",
                (70, 165, 255),
                ttl=1.4,
            )
        )

    def enemy_in_melee_arc(self) -> Enemy | None:
        best: Enemy | None = None
        best_distance = 999.0
        for enemy in self.enemies:
            dx = enemy.x - self.player.x
            dy = enemy.y - self.player.y
            distance = math.hypot(dx, dy)
            if distance > 1.35 or distance < 0.001:
                continue
            dot = (dx / distance) * self.player.facing_x + (
                dy / distance
            ) * self.player.facing_y
            if dot > 0.25 and distance < best_distance:
                best = enemy
                best_distance = distance
        return best

    def first_enemy_near(self, x: float, y: float, radius: float) -> Enemy | None:
        for enemy in self.enemies:
            if math.hypot(enemy.x - x, enemy.y - y) <= radius:
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
            self.state = "victory"
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
                    f"Picked up {nearest.name}",
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

    def use_inventory_slot(self, index: int) -> None:
        if index >= len(self.player.inventory):
            return
        item = self.player.inventory.pop(index)
        if item.slot == "potion":
            self.drink_potion(item)
            return
        old = self.player.equipment.get(item.slot)
        self.player.equipment[item.slot] = item
        if old and len(self.player.inventory) < MAX_INVENTORY:
            self.player.inventory.append(old)
        self.floaters.append(
            FloatingText(
                f"Equipped {item.name}",
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
        top = (sx, sy - TILE_H // 2)
        right = (sx + TILE_W // 2, sy)
        bottom = (sx, sy + TILE_H // 2)
        left = (sx - TILE_W // 2, sy)

        if tile == Tile.WALL:
            wall_h = 36 * WORLD_SCALE
            pygame.draw.polygon(self.screen, (45, 42, 49), [top, right, bottom, left])
            pygame.draw.polygon(
                self.screen,
                (31, 29, 36),
                [
                    left,
                    bottom,
                    (bottom[0], bottom[1] + wall_h),
                    (left[0], left[1] + wall_h),
                ],
            )
            pygame.draw.polygon(
                self.screen,
                (24, 23, 30),
                [
                    right,
                    bottom,
                    (bottom[0], bottom[1] + wall_h),
                    (right[0], right[1] + wall_h),
                ],
            )
            pygame.draw.lines(
                self.screen,
                (58, 55, 66),
                True,
                [top, right, bottom, left],
                WORLD_SCALE,
            )
            seed = (x * 928371 + y * 364479) & 7
            if seed in (1, 4, 6):
                pygame.draw.line(
                    self.screen,
                    (69, 65, 76),
                    (sx - 15 * WORLD_SCALE, sy - 9 * WORLD_SCALE),
                    (sx - 4 * WORLD_SCALE, sy - 14 * WORLD_SCALE),
                    WORLD_SCALE,
                )
                pygame.draw.line(
                    self.screen,
                    (22, 21, 28),
                    (sx + 10 * WORLD_SCALE, sy + 18 * WORLD_SCALE),
                    (sx + 2 * WORLD_SCALE, sy + wall_h - 5 * WORLD_SCALE),
                    WORLD_SCALE,
                )
            if seed in (2, 5):
                pygame.draw.rect(
                    self.screen,
                    (34, 54, 43),
                    (
                        sx - 24 * WORLD_SCALE,
                        sy + 18 * WORLD_SCALE,
                        6 * WORLD_SCALE,
                        2 * WORLD_SCALE,
                    ),
                )
                pygame.draw.rect(
                    self.screen,
                    (40, 68, 50),
                    (
                        sx + 13 * WORLD_SCALE,
                        sy + 8 * WORLD_SCALE,
                        5 * WORLD_SCALE,
                        2 * WORLD_SCALE,
                    ),
                )
            return

        base = (52, 47, 42) if tile == Tile.FLOOR else (76, 58, 36)
        edge = (72, 66, 60) if tile == Tile.FLOOR else (210, 150, 70)
        pygame.draw.polygon(self.screen, base, [top, right, bottom, left])
        pygame.draw.lines(
            self.screen, edge, True, [top, right, bottom, left], WORLD_SCALE
        )
        seed = (x * 1103515245 + y * 12345) & 15
        if seed in (0, 3, 7, 12):
            pygame.draw.line(
                self.screen,
                (38, 35, 33),
                (sx - 18 * WORLD_SCALE, sy - 2 * WORLD_SCALE),
                (sx - 6 * WORLD_SCALE, sy + 4 * WORLD_SCALE),
                WORLD_SCALE,
            )
        if seed in (2, 8, 14):
            pygame.draw.rect(
                self.screen,
                (71, 63, 54),
                (
                    sx + 8 * WORLD_SCALE,
                    sy - 6 * WORLD_SCALE,
                    3 * WORLD_SCALE,
                    2 * WORLD_SCALE,
                ),
            )
            pygame.draw.rect(
                self.screen,
                (43, 39, 36),
                (
                    sx + 15 * WORLD_SCALE,
                    sy + 7 * WORLD_SCALE,
                    2 * WORLD_SCALE,
                    2 * WORLD_SCALE,
                ),
            )
        if seed in (5, 10):
            pygame.draw.line(
                self.screen,
                (76, 68, 58),
                (sx - 4 * WORLD_SCALE, sy - 10 * WORLD_SCALE),
                (sx + 14 * WORLD_SCALE, sy - 2 * WORLD_SCALE),
                WORLD_SCALE,
            )
        if tile == Tile.STAIRS:
            pygame.draw.line(
                self.screen,
                (230, 188, 90),
                (sx - 18 * WORLD_SCALE, sy - 2 * WORLD_SCALE),
                (sx + 18 * WORLD_SCALE, sy - 2 * WORLD_SCALE),
                3 * WORLD_SCALE,
            )
            pygame.draw.line(
                self.screen,
                (230, 188, 90),
                (sx - 12 * WORLD_SCALE, sy + 5 * WORLD_SCALE),
                (sx + 12 * WORLD_SCALE, sy + 5 * WORLD_SCALE),
                3 * WORLD_SCALE,
            )
            pygame.draw.line(
                self.screen,
                (230, 188, 90),
                (sx - 6 * WORLD_SCALE, sy + 12 * WORLD_SCALE),
                (sx + 6 * WORLD_SCALE, sy + 12 * WORLD_SCALE),
                3 * WORLD_SCALE,
            )
            pygame.draw.line(
                self.screen,
                (255, 225, 132),
                (sx - 20 * WORLD_SCALE, sy - 8 * WORLD_SCALE),
                (sx + 20 * WORLD_SCALE, sy - 8 * WORLD_SCALE),
                WORLD_SCALE,
            )
            pygame.draw.circle(
                self.screen,
                (255, 214, 105),
                (sx, sy - 16 * WORLD_SCALE),
                max(2, 2 * WORLD_SCALE),
            )

    def draw_world_objects(self) -> None:
        drawables: list[tuple[float, str, object]] = []
        for item in self.items:
            drawables.append((item.x + item.y, "item", item))
        for projectile in self.projectiles:
            drawables.append((projectile.x + projectile.y, "projectile", projectile))
        for enemy in self.enemies:
            drawables.append((enemy.x + enemy.y, "enemy", enemy))
        drawables.append((self.player.x + self.player.y, "player", self.player))
        for x, y, ttl in self.slashes:
            drawables.append((x + y + 0.05, "slash", (x, y, ttl)))

        for _depth, kind, obj in sorted(drawables, key=lambda entry: entry[0]):
            if kind == "item":
                self.draw_item(cast(Item, obj))
            elif kind == "projectile":
                self.draw_projectile(cast(Projectile, obj))
            elif kind == "enemy":
                self.draw_enemy(cast(Enemy, obj))
            elif kind == "player":
                self.draw_player(cast(Player, obj))
            elif kind == "slash":
                self.draw_slash(cast(tuple[float, float, float], obj))

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
        self.draw_pixel_aim_marker(
            sx, sy - bob * WORLD_SCALE, player.facing_x, player.facing_y
        )

    def draw_pixel_aim_marker(self, sx: int, sy: int, dx: float, dy: float) -> None:
        # A tiny blocky weapon glint indicates facing without replacing the sprite art.
        end_x = sx + int(dx * 22 * WORLD_SCALE)
        end_y = sy - 34 * WORLD_SCALE + int(dy * 12 * WORLD_SCALE)
        pygame.draw.rect(
            self.screen,
            (238, 230, 190),
            (
                end_x - 2 * WORLD_SCALE,
                end_y - 2 * WORLD_SCALE,
                4 * WORLD_SCALE,
                4 * WORLD_SCALE,
            ),
        )
        pygame.draw.rect(
            self.screen,
            (86, 91, 103),
            (
                end_x - WORLD_SCALE,
                end_y - WORLD_SCALE,
                2 * WORLD_SCALE,
                2 * WORLD_SCALE,
            ),
        )

    def draw_enemy(self, enemy: Enemy) -> None:
        sprite = self.sprites.enemies.get(enemy.name, self.sprites.enemies["Ghoul"])
        shadow_w = 38 if enemy.name == "Gate Warden" else 32
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
        bar_w = (34 if enemy.name == "Gate Warden" else 28) * WORLD_SCALE
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
        }.get(item.rarity, (220, 220, 220))
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
            label = self.small_font.render(f"E: {item.name}", True, rarity_color)
            self.screen.blit(
                label, label.get_rect(center=(sx, rect.top - 10 * WORLD_SCALE))
            )

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

    def draw_slash(self, slash: tuple[float, float, float]) -> None:
        x, y, ttl = slash
        sx, sy = self.world_to_screen(x, y)
        life = max(0.0, min(1.0, ttl / 0.16))
        sprite = self.sprites.slash.copy()
        if self.player.facing_x < 0:
            sprite = pygame.transform.flip(sprite, True, False)
        if life < 0.7:
            grow = 1.0 + (0.7 - life) * 0.25
            sprite = pygame.transform.scale(
                sprite,
                (int(sprite.get_width() * grow), int(sprite.get_height() * grow)),
            )
        sprite.set_alpha(max(0, min(255, int(255 * life))))
        vx, vy = self.iso_screen_direction(self.player.facing_x, self.player.facing_y)
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
            "Warden",
            f"Level {self.player.level}  XP {self.player.xp}/{self.player.next_xp}",
            f"Weapon: {weapon}  Damage: {self.player.melee_damage()}",
            f"Armor: {armor}  DR: {self.player.armor()}",
        ]
        for i, line in enumerate(lines):
            text = self.small_font.render(line, True, (220, 215, 200))
            self.screen.blit(
                text, (self.ui(280), height - self.ui(100) + i * self.ui(24))
            )

        objective = "Objective: reach the stairs and press E"
        if (
            math.hypot(
                self.player.x - self.dungeon.stairs[0] - 0.5,
                self.player.y - self.dungeon.stairs[1] - 0.5,
            )
            < 1.0
        ):
            objective = "E: Descend the stairs"
        text = self.font.render(objective, True, (235, 205, 120))
        self.screen.blit(
            text, (width - text.get_width() - self.ui(24), height - self.ui(98))
        )
        control_lines = [
            "WASD move | Mouse aim | LMB/Space melee | RMB/F bolt",
            "E interact | I inventory | Q potion | R restart",
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
            }.get(item.rarity, (220, 220, 220))
            text = self.small_font.render(
                f"{index + 1}. [{item.rarity}] {item.label}", True, color
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

    def draw_state_overlay(self) -> None:
        width, height = self.screen.get_size()
        overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 165))
        self.screen.blit(overlay, (0, 0))
        if self.state == "victory":
            title = "Dungeon Cleared"
            subtitle = "You found the exit stairs. Press R to generate a new run."
            color = (235, 205, 120)
        else:
            title = "You Died"
            subtitle = "The dungeon claims another Warden. Press R to try again."
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
