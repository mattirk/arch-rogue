from __future__ import annotations

import pygame

from .models import Color


class PixelSpriteAtlas:
    """Procedural JRPG-style pixel sprites for all gameplay entities.

    The game intentionally keeps art source in code for now so it remains easy to
    run without an asset pipeline. Sprites are authored at tiny resolutions and
    scaled with nearest-neighbor filtering for a chunky pixel-art look.
    """

    SCALE = 6

    def __init__(self) -> None:
        self.player_sprites = {
            "Warden": self._scale(self._warden()),
            "Rogue": self._scale(self._rogue_player()),
            "Arcanist": self._scale(self._arcanist_player()),
            "Acolyte": self._scale(self._acolyte_player()),
            "Ranger": self._scale(self._ranger_player()),
        }
        self.player = self.player_sprites["Warden"]
        self.enemies = {
            "Ghoul": self._scale(self._ghoul()),
            "Cultist": self._scale(self._cultist()),
            "Bone Imp": self._scale(self._bone_imp()),
            "Crypt Brute": self._scale(self._crypt_brute()),
            "Venom Skitter": self._scale(self._venom_skitter()),
            "Grave Archer": self._scale(self._grave_archer()),
            "Ash Hound": self._scale(self._ash_hound()),
            "Rune Sentinel": self._scale(self._rune_sentinel()),
            "Plague Toad": self._scale(self._plague_toad()),
            "Hollow Knight": self._scale(self._hollow_knight()),
            "Gate Warden": self._scale(self._gate_warden()),
        }
        self.items = {
            "potion": self._scale(self._potion()),
            "mana_potion": self._scale(self._mana_potion()),
            "identify": self._scale(self._scroll()),
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

    def _scale(
        self, surface: pygame.Surface, scale: int | None = None
    ) -> pygame.Surface:
        factor = scale or self.SCALE
        return pygame.transform.scale(
            surface, (surface.get_width() * factor, surface.get_height() * factor)
        )

    def _humanoid_base(
        self,
        head: Color,
        body: Color,
        body_hi: Color,
        trim: Color,
        outline: Color,
        eye: Color,
        weapon: Color | None = None,
    ) -> pygame.Surface:
        s = self._surface(18, 24)
        leather = (70, 48, 40)
        shadow = (38, 30, 36)
        self._rect(s, 5, 2, 8, 7, outline)
        self._rect(s, 6, 3, 6, 6, head)
        self._rect(s, 6, 5, 1, 1, eye)
        self._rect(s, 11, 5, 1, 1, eye)
        self._rect(s, 7, 7, 4, 1, shadow)
        self._rect(s, 3, 9, 12, 10, outline)
        self._rect(s, 5, 9, 8, 10, body)
        self._rect(s, 7, 10, 4, 7, body_hi)
        self._rect(s, 4, 11, 2, 6, trim)
        self._rect(s, 12, 11, 2, 6, trim)
        self._rect(s, 5, 19, 3, 3, leather)
        self._rect(s, 10, 19, 3, 3, leather)
        self._rect(s, 4, 22, 4, 2, outline)
        self._rect(s, 10, 22, 4, 2, outline)
        self._rect(s, 5, 10, 8, 1, trim)
        self._rect(s, 6, 16, 6, 1, trim)
        self._dot(s, 8, 13, (235, 210, 120))
        self._dot(s, 9, 13, (235, 210, 120))
        if weapon:
            self._rect(s, 14, 7, 1, 11, weapon)
            self._rect(s, 15, 5, 1, 4, weapon)
            self._rect(s, 13, 15, 3, 1, weapon)
        return s

    def _warden(self) -> pygame.Surface:
        s = self._humanoid_base(
            (215, 158, 105),
            (45, 93, 164),
            (76, 140, 220),
            (154, 168, 178),
            (19, 24, 35),
            (40, 35, 32),
            (220, 226, 218),
        )
        self._rect(s, 6, 2, 6, 2, (62, 43, 35))
        self._rect(s, 5, 10, 8, 1, (108, 82, 50))
        self._rect(s, 4, 15, 10, 1, (30, 58, 116))
        self._rect(s, 6, 16, 6, 1, (235, 205, 112))
        self._rect(s, 2, 12, 4, 6, (96, 104, 112))
        self._rect(s, 3, 13, 2, 4, (220, 226, 218))
        return s

    def _rogue_player(self) -> pygame.Surface:
        s = self._humanoid_base(
            (205, 145, 98),
            (42, 55, 58),
            (68, 92, 82),
            (92, 170, 118),
            (17, 20, 22),
            (210, 245, 185),
        )
        self._rect(s, 5, 2, 8, 3, (35, 38, 42))
        self._rect(s, 4, 5, 10, 2, (24, 26, 30))
        self._rect(s, 2, 11, 4, 2, (80, 94, 88))
        self._rect(s, 12, 11, 4, 2, (80, 94, 88))
        self._rect(s, 2, 14, 4, 1, (205, 210, 198))
        self._rect(s, 12, 14, 4, 1, (205, 210, 198))
        self._rect(s, 6, 16, 6, 1, (92, 170, 118))
        self._dot(s, 8, 12, (235, 215, 130))
        return s

    def _arcanist_player(self) -> pygame.Surface:
        s = self._humanoid_base(
            (196, 150, 116),
            (42, 46, 110),
            (72, 86, 190),
            (116, 220, 245),
            (18, 20, 42),
            (170, 235, 255),
            (116, 220, 245),
        )
        self._rect(s, 4, 2, 10, 2, (52, 42, 130))
        self._rect(s, 5, 1, 8, 1, (116, 220, 245))
        self._rect(s, 15, 6, 1, 12, (88, 62, 138))
        self._rect(s, 14, 5, 3, 2, (116, 220, 245))
        self._dot(s, 16, 4, (240, 255, 255))
        self._rect(s, 7, 13, 4, 4, (92, 125, 230))
        self._dot(s, 9, 14, (240, 255, 255))
        return s

    def _acolyte_player(self) -> pygame.Surface:
        s = self._humanoid_base(
            (185, 132, 104),
            (80, 30, 54),
            (132, 42, 82),
            (210, 84, 116),
            (24, 14, 24),
            (255, 160, 190),
            (210, 84, 116),
        )
        self._rect(s, 5, 2, 8, 3, (42, 18, 34))
        self._rect(s, 6, 3, 6, 1, (210, 84, 116))
        self._rect(s, 3, 15, 12, 2, (48, 18, 34))
        self._rect(s, 8, 11, 2, 5, (235, 195, 150))
        self._rect(s, 8, 10, 2, 1, (210, 84, 116))
        self._rect(s, 14, 8, 1, 10, (120, 74, 52))
        self._rect(s, 13, 7, 3, 2, (210, 84, 116))
        self._dot(s, 15, 6, (255, 190, 210))
        return s

    def _ranger_player(self) -> pygame.Surface:
        s = self._humanoid_base(
            (205, 150, 104),
            (54, 94, 58),
            (88, 145, 72),
            (176, 138, 70),
            (20, 28, 22),
            (225, 240, 175),
        )
        self._rect(s, 5, 2, 8, 2, (70, 50, 34))
        self._rect(s, 4, 4, 10, 1, (94, 68, 40))
        self._rect(s, 14, 5, 1, 14, (116, 74, 39))
        self._rect(s, 15, 6, 1, 2, (216, 226, 222))
        self._rect(s, 15, 16, 1, 2, (216, 226, 222))
        self._rect(s, 3, 12, 3, 1, (116, 74, 39))
        self._rect(s, 11, 12, 4, 1, (116, 74, 39))
        self._rect(s, 7, 16, 4, 1, (176, 138, 70))
        return s

    def _ghoul(self) -> pygame.Surface:
        s = self._humanoid_base(
            (118, 154, 94),
            (118, 154, 94),
            (161, 189, 116),
            (95, 54, 59),
            (31, 20, 22),
            (238, 226, 126),
        )
        self._rect(s, 2, 17, 2, 1, (202, 202, 162))
        self._rect(s, 14, 17, 2, 1, (202, 202, 162))
        self._rect(s, 7, 16, 1, 2, (56, 35, 38))
        self._rect(s, 10, 16, 1, 2, (56, 35, 38))
        self._dot(s, 12, 10, (95, 54, 59))
        return s

    def _cultist(self) -> pygame.Surface:
        s = self._humanoid_base(
            (44, 29, 54),
            (78, 44, 132),
            (123, 76, 183),
            (184, 138, 218),
            (22, 18, 33),
            (255, 190, 255),
            (205, 79, 230),
        )
        self._rect(s, 5, 4, 1, 4, (54, 31, 92))
        self._rect(s, 12, 4, 1, 4, (42, 25, 70))
        self._dot(s, 15, 8, (255, 220, 255))
        self._dot(s, 13, 9, (255, 220, 255))
        return s

    def _bone_imp(self) -> pygame.Surface:
        s = self._humanoid_base(
            (214, 202, 176),
            (130, 82, 156),
            (190, 130, 215),
            (94, 60, 122),
            (30, 22, 36),
            (120, 245, 255),
            (210, 160, 230),
        )
        self._rect(s, 4, 2, 2, 3, (214, 202, 176))
        self._rect(s, 12, 2, 2, 3, (214, 202, 176))
        self._rect(s, 6, 8, 6, 1, (62, 42, 76))
        self._rect(s, 2, 10, 3, 2, (96, 60, 118))
        self._rect(s, 13, 10, 3, 2, (96, 60, 118))
        return s

    def _crypt_brute(self) -> pygame.Surface:
        s = self._surface(21, 25)
        outline = (29, 23, 22)
        hide = (155, 105, 74)
        hide_hi = (198, 143, 94)
        iron = (126, 132, 128)
        dark = (58, 46, 43)
        eye = (250, 110, 70)
        self._rect(s, 5, 2, 10, 7, outline)
        self._rect(s, 6, 3, 8, 6, hide)
        self._rect(s, 7, 5, 2, 1, eye)
        self._rect(s, 12, 5, 2, 1, eye)
        self._rect(s, 2, 9, 17, 10, outline)
        self._rect(s, 4, 9, 13, 10, hide)
        self._rect(s, 7, 10, 7, 6, hide_hi)
        self._rect(s, 3, 11, 4, 7, iron)
        self._rect(s, 14, 11, 4, 7, iron)
        self._rect(s, 6, 19, 4, 4, dark)
        self._rect(s, 11, 19, 4, 4, dark)
        self._rect(s, 5, 23, 5, 2, outline)
        self._rect(s, 11, 23, 5, 2, outline)
        self._rect(s, 7, 13, 7, 1, (98, 66, 52))
        self._rect(s, 9, 15, 3, 2, iron)
        return s

    def _venom_skitter(self) -> pygame.Surface:
        s = self._surface(20, 16)
        outline = (24, 40, 24)
        body = (74, 138, 72)
        hi = (128, 218, 104)
        venom = (192, 246, 88)
        eye = (255, 236, 120)
        self._rect(s, 5, 5, 10, 6, outline)
        self._rect(s, 6, 5, 8, 6, body)
        self._rect(s, 8, 6, 4, 3, hi)
        for x1, x2, y in (
            (3, 6, 5),
            (2, 6, 8),
            (3, 6, 11),
            (14, 17, 5),
            (14, 18, 8),
            (14, 17, 11),
        ):
            self._rect(s, min(x1, x2), y, abs(x2 - x1) + 1, 1, outline)
        self._rect(s, 7, 4, 2, 1, eye)
        self._rect(s, 11, 4, 2, 1, eye)
        self._rect(s, 9, 10, 2, 3, venom)
        self._dot(s, 4, 7, venom)
        self._dot(s, 16, 7, venom)
        return s

    def _grave_archer(self) -> pygame.Surface:
        s = self._humanoid_base(
            (116, 105, 76),
            (86, 116, 72),
            (145, 164, 98),
            (58, 43, 31),
            (26, 31, 25),
            (225, 218, 145),
        )
        self._rect(s, 14, 6, 1, 13, (116, 74, 39))
        self._rect(s, 15, 7, 1, 2, (216, 226, 222))
        self._rect(s, 15, 16, 1, 2, (216, 226, 222))
        self._rect(s, 3, 14, 3, 1, (116, 74, 39))
        self._dot(s, 9, 12, (235, 210, 120))
        return s

    def _ash_hound(self) -> pygame.Surface:
        s = self._surface(21, 15)
        outline = (30, 22, 20)
        fur = (112, 62, 46)
        ash = (185, 86, 54)
        ember = (255, 160, 66)
        eye = (255, 224, 120)
        self._rect(s, 4, 5, 11, 6, outline)
        self._rect(s, 5, 5, 9, 5, fur)
        self._rect(s, 12, 3, 5, 5, outline)
        self._rect(s, 13, 4, 4, 4, fur)
        self._rect(s, 16, 5, 1, 1, eye)
        self._rect(s, 2, 6, 3, 3, outline)
        self._rect(s, 1, 7, 2, 1, ash)
        self._rect(s, 6, 10, 2, 4, outline)
        self._rect(s, 12, 10, 2, 4, outline)
        self._rect(s, 6, 11, 2, 2, fur)
        self._rect(s, 12, 11, 2, 2, fur)
        self._rect(s, 8, 4, 4, 1, ash)
        self._dot(s, 8, 7, ember)
        self._dot(s, 11, 8, ember)
        self._rect(s, 15, 2, 2, 1, ash)
        return s

    def _rune_sentinel(self) -> pygame.Surface:
        s = self._surface(20, 24)
        outline = (28, 30, 38)
        stone = (88, 98, 112)
        stone_hi = (142, 155, 168)
        rune = (116, 220, 245)
        dark = (42, 46, 56)
        self._rect(s, 6, 2, 8, 6, outline)
        self._rect(s, 7, 3, 6, 5, stone)
        self._rect(s, 8, 5, 4, 1, rune)
        self._rect(s, 3, 9, 14, 10, outline)
        self._rect(s, 5, 9, 10, 10, stone)
        self._rect(s, 7, 10, 6, 7, stone_hi)
        self._rect(s, 2, 11, 4, 6, dark)
        self._rect(s, 14, 11, 4, 6, dark)
        self._rect(s, 7, 19, 3, 4, dark)
        self._rect(s, 11, 19, 3, 4, dark)
        self._rect(s, 6, 23, 4, 1, outline)
        self._rect(s, 11, 23, 4, 1, outline)
        self._rect(s, 9, 12, 2, 4, rune)
        self._dot(s, 7, 14, rune)
        self._dot(s, 12, 14, rune)
        return s

    def _plague_toad(self) -> pygame.Surface:
        s = self._surface(21, 17)
        outline = (24, 38, 30)
        body = (84, 132, 66)
        belly = (144, 172, 86)
        spot = (192, 226, 74)
        eye = (236, 210, 96)
        self._rect(s, 4, 5, 13, 8, outline)
        self._rect(s, 5, 5, 11, 7, body)
        self._rect(s, 7, 8, 7, 4, belly)
        self._rect(s, 5, 3, 4, 4, outline)
        self._rect(s, 12, 3, 4, 4, outline)
        self._rect(s, 6, 4, 2, 2, eye)
        self._rect(s, 13, 4, 2, 2, eye)
        self._rect(s, 2, 11, 4, 2, outline)
        self._rect(s, 15, 11, 4, 2, outline)
        self._dot(s, 9, 6, spot)
        self._dot(s, 13, 8, spot)
        self._dot(s, 6, 10, spot)
        self._rect(s, 8, 14, 5, 1, outline)
        return s

    def _hollow_knight(self) -> pygame.Surface:
        s = self._humanoid_base(
            (182, 178, 160),
            (74, 78, 86),
            (126, 132, 128),
            (190, 92, 54),
            (24, 22, 24),
            (120, 245, 255),
            (216, 226, 222),
        )
        self._rect(s, 4, 2, 2, 2, (216, 226, 222))
        self._rect(s, 12, 2, 2, 2, (216, 226, 222))
        self._rect(s, 6, 5, 6, 1, (120, 245, 255))
        self._rect(s, 3, 12, 12, 1, (32, 34, 42))
        self._rect(s, 7, 15, 4, 2, (190, 92, 54))
        return s

    def _gate_warden(self) -> pygame.Surface:
        s = self._crypt_brute()
        self._rect(s, 7, 3, 7, 5, (171, 105, 48))
        self._rect(s, 8, 4, 5, 2, (230, 156, 72))
        self._rect(s, 8, 5, 5, 1, (235, 65, 48))
        self._rect(s, 8, 11, 6, 5, (171, 105, 48))
        self._rect(s, 9, 12, 4, 3, (255, 202, 90))
        self._rect(s, 17, 4, 1, 14, (230, 156, 72))
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
        self._rect(s, 4, 7, 4, 1, (205, 238, 245))
        self._dot(s, 8, 6, shine)
        return s

    def _mana_potion(self) -> pygame.Surface:
        s = self._potion()
        self._rect(s, 4, 8, 4, 4, (54, 102, 210))
        self._rect(s, 5, 10, 2, 1, (105, 165, 255))
        return s

    def _scroll(self) -> pygame.Surface:
        s = self._surface(14, 12)
        paper = (224, 207, 166)
        edge = (132, 91, 52)
        rune = (92, 70, 145)
        self._rect(s, 2, 2, 10, 8, edge)
        self._rect(s, 3, 2, 8, 8, paper)
        self._rect(s, 1, 3, 2, 6, edge)
        self._rect(s, 11, 3, 2, 6, edge)
        self._rect(s, 5, 4, 4, 1, rune)
        self._rect(s, 4, 6, 6, 1, rune)
        self._rect(s, 6, 8, 3, 1, rune)
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
        self._rect(s, 5, 8, 4, 1, (95, 102, 106))
        self._dot(s, 4, 6, hi)
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
