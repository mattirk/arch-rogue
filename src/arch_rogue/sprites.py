from __future__ import annotations

import pygame

from .models import Color

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
        self.enemies["Bone Imp"] = self.enemies["Cultist"].copy()
        self.enemies["Crypt Brute"] = self.enemies["Gate Warden"].copy()
        self.enemies["Venom Skitter"] = self.enemies["Ghoul"].copy()
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
