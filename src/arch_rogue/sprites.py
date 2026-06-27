from __future__ import annotations

import pygame

from .models import Color


class PixelSpriteAtlas:
    """Procedural pixel-art sprites and cached animation frames.

    The prototype still keeps its art source in code so it can run without an
    external asset pipeline. Sprites are authored at tiny resolutions, outlined,
    then scaled with nearest-neighbor filtering for a chunky dark-fantasy look.
    Runtime code should use the frame helpers for animated actors/objects while
    the legacy dictionaries remain available for static call sites and tests.
    """

    SCALE = 6

    PLAYER_ACCENTS: dict[str, Color] = {
        "Warden": (235, 205, 120),
        "Rogue": (170, 230, 150),
        "Arcanist": (120, 210, 255),
        "Acolyte": (220, 95, 140),
        "Ranger": (150, 215, 105),
    }
    ENEMY_ACCENTS: dict[str, Color] = {
        "Ghoul": (178, 212, 124),
        "Cultist": (205, 128, 245),
        "Bone Imp": (120, 245, 255),
        "Crypt Brute": (225, 155, 96),
        "Venom Skitter": (192, 246, 88),
        "Grave Archer": (225, 218, 145),
        "Ash Hound": (255, 160, 66),
        "Rune Sentinel": (116, 220, 245),
        "Plague Toad": (192, 226, 74),
        "Hollow Knight": (120, 245, 255),
        "Gate Warden": (255, 202, 90),
    }

    def __init__(self) -> None:
        raw_players = {
            "Warden": self._warden(),
            "Rogue": self._rogue_player(),
            "Arcanist": self._arcanist_player(),
            "Acolyte": self._acolyte_player(),
            "Ranger": self._ranger_player(),
        }
        raw_enemies = {
            "Ghoul": self._ghoul(),
            "Cultist": self._cultist(),
            "Bone Imp": self._bone_imp(),
            "Crypt Brute": self._crypt_brute(),
            "Venom Skitter": self._venom_skitter(),
            "Grave Archer": self._grave_archer(),
            "Ash Hound": self._ash_hound(),
            "Rune Sentinel": self._rune_sentinel(),
            "Plague Toad": self._plague_toad(),
            "Hollow Knight": self._hollow_knight(),
            "Gate Warden": self._gate_warden(),
        }
        raw_items = {
            "potion": self._potion(),
            "mana_potion": self._mana_potion(),
            "identify": self._scroll(),
            "weapon": self._weapon(),
            "armor": self._armor(),
        }
        raw_projectiles = {
            "player": self._blue_bolt(),
            "enemy": self._void_bolt(),
        }
        raw_traps = {
            "Spike Trap": self._spike_trap(),
            "Rune Trap": self._rune_trap(),
            "Poison Needle": self._poison_trap(),
        }

        self.player_sprites = {
            name: self._scale_actor(surface) for name, surface in raw_players.items()
        }
        self.player = self.player_sprites["Warden"]
        self.enemies = {
            name: self._scale_actor(surface) for name, surface in raw_enemies.items()
        }
        self.items = {
            slot: self._scale_prop(surface) for slot, surface in raw_items.items()
        }
        self.projectiles = {
            owner: self._scale_prop(surface)
            for owner, surface in raw_projectiles.items()
        }
        self.slash = self._scale_prop(self._slash())

        self.player_animation_frames = {
            name: self._actor_animation_frames(sprite, self.PLAYER_ACCENTS[name])
            for name, sprite in self.player_sprites.items()
        }
        self.enemy_animation_frames = {
            name: self._actor_animation_frames(
                sprite, self.ENEMY_ACCENTS.get(name, (225, 120, 100)), hostile=True
            )
            for name, sprite in self.enemies.items()
        }
        self.item_animation_frames = {
            slot: self._item_animation_frames(sprite)
            for slot, sprite in self.items.items()
        }
        self.item_rarity_animation_frames: dict[
            tuple[str, str], list[pygame.Surface]
        ] = {}
        rarity_tints: dict[str, tuple[Color, int]] = {
            "Rare": ((150, 200, 255), 18),
            "Unique": ((245, 218, 120), 20),
            "Legendary": ((255, 178, 92), 22),
            "Artifact": ((255, 210, 142), 24),
            "Unidentified": ((170, 120, 245), 20),
        }
        for slot, frames in self.item_animation_frames.items():
            for rarity, tint in rarity_tints.items():
                self.item_rarity_animation_frames[(slot, rarity)] = [
                    self._frame_surface(frame, tint=tint) for frame in frames
                ]
        self.projectile_animation_frames = {
            owner: self._projectile_animation_frames(sprite)
            for owner, sprite in self.projectiles.items()
        }

        self.trap_sprites = {
            kind: self._scale_prop(surface) for kind, surface in raw_traps.items()
        }
        self.trap_animation_frames = {
            kind: self._prop_animation_frames(sprite, glow=(245, 95, 70))
            for kind, sprite in self.trap_sprites.items()
        }
        self.shrine_sprites = {
            "active": self._scale_prop(self._shrine(active=True)),
            "used": self._scale_prop(self._shrine(active=False)),
        }
        self.shrine_animation_frames = {
            state: self._prop_animation_frames(
                sprite, glow=(235, 205, 110) if state == "active" else (110, 110, 120)
            )
            for state, sprite in self.shrine_sprites.items()
        }
        self.secret_sprites = {"cache": self._scale_prop(self._secret_cache())}
        self.secret_animation_frames = {
            "cache": self._prop_animation_frames(
                self.secret_sprites["cache"], glow=(210, 185, 120)
            )
        }
        self.story_guest_sprites = {
            "active": self._scale_actor(self._story_guest(active=True)),
            "resolved": self._scale_actor(self._story_guest(active=False)),
        }
        self.story_guest_animation_frames = {
            state: self._actor_animation_frames(
                sprite, (190, 150, 245) if state == "active" else (105, 100, 115)
            )
            for state, sprite in self.story_guest_sprites.items()
        }
        self.shopkeeper_sprite = self._scale_actor(self._shopkeeper())
        self.shopkeeper_animation_frames = self._actor_animation_frames(
            self.shopkeeper_sprite, (245, 205, 92)
        )

    def _surface(self, w: int, h: int) -> pygame.Surface:
        return pygame.Surface((w, h), pygame.SRCALPHA)

    def _rect(
        self, surface: pygame.Surface, x: int, y: int, w: int, h: int, color: Color
    ) -> None:
        pygame.draw.rect(surface, color, (x, y, w, h))

    def _dot(self, surface: pygame.Surface, x: int, y: int, color: Color) -> None:
        self._rect(surface, x, y, 1, 1, color)

    def _outline_surface(
        self, surface: pygame.Surface, outline: Color = (11, 10, 14)
    ) -> pygame.Surface:
        """Add a one-pixel silhouette outline before scaling."""
        try:
            source = surface.convert_alpha()
        except pygame.error:
            source = surface.copy()
        outlined = self._surface(source.get_width() + 2, source.get_height() + 2)
        outline_rgba = (*outline, 255)
        for x in range(source.get_width()):
            for y in range(source.get_height()):
                if source.get_at((x, y)).a <= 0:
                    continue
                for ox, oy in (
                    (-1, 0),
                    (1, 0),
                    (0, -1),
                    (0, 1),
                    (-1, -1),
                    (1, -1),
                    (-1, 1),
                    (1, 1),
                ):
                    px = x + 1 + ox
                    py = y + 1 + oy
                    if outlined.get_at((px, py)).a == 0:
                        outlined.set_at((px, py), outline_rgba)
        outlined.blit(source, (1, 1))
        return outlined

    def _scale(
        self, surface: pygame.Surface, scale: int | None = None
    ) -> pygame.Surface:
        factor = scale or self.SCALE
        scaled = pygame.transform.scale(
            surface, (surface.get_width() * factor, surface.get_height() * factor)
        )
        try:
            return scaled.convert_alpha()
        except pygame.error:
            return scaled

    def _scale_actor(self, surface: pygame.Surface) -> pygame.Surface:
        return self._scale(self._outline_surface(surface))

    def _scale_prop(self, surface: pygame.Surface) -> pygame.Surface:
        return self._scale(self._outline_surface(surface, (18, 14, 20)))

    def _frame_surface(
        self,
        sprite: pygame.Surface,
        *,
        stretch: float = 1.0,
        tilt: float = 0.0,
        top_pad: int = 0,
        side_pad: int = 0,
        tint: tuple[Color, int] | None = None,
        glow: tuple[Color, int] | None = None,
    ) -> pygame.Surface:
        frame = sprite
        if abs(stretch - 1.0) > 0.01:
            frame = pygame.transform.scale(
                frame,
                (
                    max(1, round(frame.get_width() / stretch)),
                    max(1, round(frame.get_height() * stretch)),
                ),
            )
        if abs(tilt) > 0.01:
            frame = pygame.transform.rotate(frame, tilt)

        if top_pad or side_pad or glow is not None:
            pad_x = side_pad or max(4, sprite.get_width() // 12)
            pad_top = top_pad or max(4, sprite.get_height() // 12)
            canvas = pygame.Surface(
                (frame.get_width() + pad_x * 2, frame.get_height() + pad_top),
                pygame.SRCALPHA,
            )
            if glow is not None:
                glow_color, glow_alpha = glow
                glow_rect = pygame.Rect(
                    0,
                    max(0, canvas.get_height() - sprite.get_height() // 3),
                    canvas.get_width(),
                    max(1, sprite.get_height() // 3),
                )
                pygame.draw.ellipse(canvas, (*glow_color, glow_alpha), glow_rect)
            canvas.blit(frame, (pad_x, pad_top))
            frame = canvas
        else:
            frame = frame.copy()

        if tint is not None:
            tint_color, tint_alpha = tint
            flash = pygame.Surface(frame.get_size(), pygame.SRCALPHA)
            flash.fill((*tint_color, tint_alpha))
            frame.blit(flash, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
        try:
            return frame.convert_alpha()
        except pygame.error:
            return frame

    def _draw_scaled_rect(
        self,
        surface: pygame.Surface,
        origin: tuple[int, int],
        x: float,
        y: float,
        w: float,
        h: float,
        color: Color,
        alpha: int = 255,
    ) -> None:
        unit = self.SCALE
        rect = pygame.Rect(
            origin[0] + round(x * unit),
            origin[1] + round(y * unit),
            max(1, round(w * unit)),
            max(1, round(h * unit)),
        )
        if alpha >= 255:
            pygame.draw.rect(surface, color, rect)
            return
        patch = pygame.Surface(rect.size, pygame.SRCALPHA)
        patch.fill((*color, alpha))
        surface.blit(patch, rect)

    def _actor_pose_frame(
        self,
        sprite: pygame.Surface,
        accent: Color,
        state: str,
        index: int,
        *,
        hostile: bool = False,
        tint: tuple[Color, int] | None = None,
        glow: tuple[Color, int] | None = None,
        top_pad: int = 0,
        side_pad: int = 0,
    ) -> pygame.Surface:
        frame = pygame.Surface(
            (sprite.get_width() + side_pad * 2, sprite.get_height() + top_pad),
            pygame.SRCALPHA,
        )
        if glow is not None:
            glow_color, glow_alpha = glow
            glow_rect = pygame.Rect(
                0,
                max(0, frame.get_height() - sprite.get_height() // 3),
                frame.get_width(),
                max(1, sprite.get_height() // 3),
            )
            pygame.draw.ellipse(frame, (*glow_color, glow_alpha), glow_rect)

        unit = self.SCALE
        width = sprite.get_width()
        height = sprite.get_height()
        raw_w = max(1, width // unit)
        raw_h = max(1, height // unit)
        head_y = round(height * 0.34)
        hip_y = round(height * 0.72)
        foot_y = round(height * 0.88)
        base_x = side_pad
        base_y = top_pad
        origin = (base_x, base_y)
        hand_light = self._shade(accent, 70)

        def blit_band(
            y0: int,
            y1: int,
            dx: int = 0,
            dy: int = 0,
            alpha: int = 255,
        ) -> None:
            if y1 <= y0:
                return
            rect = pygame.Rect(0, y0, width, y1 - y0)
            if alpha >= 255:
                frame.blit(sprite, (base_x + dx, base_y + y0 + dy), rect)
                return
            band = pygame.Surface(rect.size, pygame.SRCALPHA)
            band.blit(sprite, (0, 0), rect)
            band.set_alpha(alpha)
            frame.blit(band, (base_x + dx, base_y + y0 + dy))

        def blit_pose(
            *,
            head_dx: int = 0,
            head_dy: int = 0,
            torso_dx: int = 0,
            torso_dy: int = 0,
            hip_dx: int = 0,
            hip_dy: int = 0,
            foot_dx: int = 0,
            foot_dy: int = 0,
        ) -> None:
            blit_band(0, head_y, head_dx, head_dy)
            blit_band(head_y, hip_y, torso_dx, torso_dy)
            blit_band(hip_y, foot_y, hip_dx, hip_dy)
            blit_band(foot_y, height, foot_dx, foot_dy)

        if state == "idle":
            breath = (0, -1, -1, 0)[index % 4]
            blit_pose(torso_dy=breath, hip_dy=breath, foot_dy=breath)

        elif state == "run":
            body_shift = (-2, -1, 1, 2, 1, -1)[index % 6]
            lower_shift = (3, 2, -1, -3, -2, 1)[index % 6]
            lift = (0, -2, -3, 0, -2, -3)[index % 6]
            blit_pose(
                head_dx=round(body_shift * 0.45),
                torso_dx=body_shift,
                hip_dx=round(lower_shift * 0.65),
                hip_dy=round(lift * 0.45),
                foot_dx=lower_shift,
                foot_dy=lift,
            )

        elif state == "attack":
            windup = (-2, 2, 4, 1)[index % 4]
            recoil = (1, -1, -2, 0)[index % 4]
            blit_pose(
                head_dx=round(windup * 0.35),
                torso_dx=windup,
                torso_dy=-1 if index in (1, 2) else 0,
                hip_dx=recoil,
                foot_dx=-recoil,
            )

        elif state == "cast":
            pulse = (0, -1, -2, -1)[index % 4]
            blit_pose(head_dy=pulse, torso_dy=pulse, hip_dy=round(pulse * 0.45))
            cast_lift = (0.0, -0.75, -1.25, -0.55)[index % 4]

            self._draw_scaled_rect(
                frame,
                origin,
                raw_w * 0.36,
                raw_h * 0.36 + cast_lift,
                5.2,
                0.45,
                hand_light,
                82,
            )
        elif state == "hit":
            recoil = (-3, 2, 0)[index % 3]
            blit_pose(
                head_dx=round(recoil * 0.65),
                torso_dx=recoil,
                hip_dx=round(recoil * 0.45),
                foot_dx=round(-recoil * 0.25),
            )

        elif state == "dash":
            dash_shift = (4, 6, 2)[index % 3]
            blit_pose(
                head_dx=round(dash_shift * 0.45),
                torso_dx=dash_shift,
                hip_dx=round(dash_shift * 0.70),
                foot_dx=round(dash_shift * 0.90),
                torso_dy=-1,
                hip_dy=-1,
            )

        else:
            blit_pose()

        if tint is not None:
            tint_color, tint_alpha = tint
            flash = pygame.Surface(frame.get_size(), pygame.SRCALPHA)
            flash.fill((*tint_color, tint_alpha))
            frame.blit(flash, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
        try:
            return frame.convert_alpha()
        except pygame.error:
            return frame

    def _actor_animation_frames(
        self, sprite: pygame.Surface, accent: Color, hostile: bool = False
    ) -> dict[str, list[pygame.Surface]]:
        hit_color = (255, 92, 72) if hostile else (255, 245, 218)
        cast_glow = accent if not hostile else self._mix(accent, (255, 80, 80), 0.25)
        cast_top_pad = max(5, sprite.get_height() // 14)
        cast_side_pad = max(5, sprite.get_width() // 13)
        return {
            "idle": [
                self._actor_pose_frame(sprite, accent, "idle", frame, hostile=hostile)
                for frame in range(4)
            ],
            "run": [
                self._actor_pose_frame(sprite, accent, "run", frame, hostile=hostile)
                for frame in range(6)
            ],
            "attack": [
                self._actor_pose_frame(
                    sprite,
                    accent,
                    "attack",
                    frame,
                    hostile=hostile,
                    tint=(accent, 10 + frame * 6),
                )
                for frame in range(4)
            ],
            "cast": [
                self._actor_pose_frame(
                    sprite,
                    accent,
                    "cast",
                    frame,
                    hostile=hostile,
                    top_pad=cast_top_pad,
                    side_pad=cast_side_pad,
                    tint=(cast_glow, (18, 34, 46, 22)[frame]),
                    glow=(cast_glow, (34, 56, 76, 42)[frame]),
                )
                for frame in range(4)
            ],
            "hit": [
                self._actor_pose_frame(
                    sprite,
                    accent,
                    "hit",
                    frame,
                    hostile=hostile,
                    tint=(hit_color, (72, 48, 26)[frame]),
                )
                for frame in range(3)
            ],
            "dash": [
                self._actor_pose_frame(
                    sprite,
                    accent,
                    "dash",
                    frame,
                    hostile=hostile,
                    tint=(accent, (34, 44, 25)[frame]),
                )
                for frame in range(3)
            ],
        }

    def _item_animation_frames(self, sprite: pygame.Surface) -> list[pygame.Surface]:
        return [
            self._frame_surface(sprite, stretch=1.0),
            self._frame_surface(sprite, stretch=1.04, tilt=-2.0),
            self._frame_surface(sprite, stretch=1.0),
            self._frame_surface(sprite, stretch=0.98, tilt=2.0),
        ]

    def _projectile_animation_frames(
        self, sprite: pygame.Surface
    ) -> list[pygame.Surface]:
        return [
            self._frame_surface(sprite, stretch=1.0),
            self._frame_surface(sprite, stretch=1.04, tint=((120, 220, 255), 28)),
            self._frame_surface(sprite, stretch=0.98),
        ]

    def _prop_animation_frames(
        self, sprite: pygame.Surface, glow: Color | None = None
    ) -> list[pygame.Surface]:
        glow_data = (glow, 34) if glow is not None else None
        return [
            self._frame_surface(sprite, stretch=1.0, glow=glow_data),
            self._frame_surface(sprite, stretch=1.02, tilt=-1.5, glow=glow_data),
            self._frame_surface(sprite, stretch=1.0, glow=glow_data),
            self._frame_surface(sprite, stretch=0.99, tilt=1.5, glow=glow_data),
        ]

    def _frame_from(
        self, frames: list[pygame.Surface], phase: float, rate: float = 1.0
    ) -> pygame.Surface:
        if not frames:
            return self.player
        return frames[int(abs(phase) * rate) % len(frames)]

    def player_frame(
        self, class_name: str, state: str, anim_time: float, elapsed: float
    ) -> pygame.Surface:
        states = self.player_animation_frames.get(
            class_name, self.player_animation_frames["Warden"]
        )
        frames = states.get(state, states["idle"])
        phase = anim_time * 8.0 if state == "run" else elapsed * 5.0
        if state in ("attack", "cast", "hit", "dash"):
            phase = elapsed * 14.0
        return self._frame_from(frames, phase)

    def enemy_key(self, name: str, kind: str = "") -> str:
        if name in self.enemies:
            return name
        for candidate in sorted(self.enemies, key=len, reverse=True):
            if name.endswith(candidate):
                return candidate
        if kind == "boss":
            return "Gate Warden"
        return "Ghoul"

    def enemy_frame(
        self, name: str, kind: str, state: str, anim_time: float, elapsed: float
    ) -> pygame.Surface:
        key = self.enemy_key(name, kind)
        states = self.enemy_animation_frames.get(
            key, self.enemy_animation_frames["Ghoul"]
        )
        frames = states.get(state, states["idle"])
        phase = (
            anim_time * 8.0
            if state == "run"
            else elapsed * (4.3 if kind == "boss" else 5.0)
        )
        if state in ("attack", "cast", "hit"):
            phase = elapsed * 13.0
        return self._frame_from(frames, phase)

    def item_frame(
        self, slot: str, elapsed: float, rarity: str = "Common"
    ) -> pygame.Surface:
        frames = self.item_rarity_animation_frames.get(
            (slot, rarity),
            self.item_animation_frames.get(slot, self.item_animation_frames["potion"]),
        )
        return self._frame_from(frames, elapsed, rate=2.2)

    def projectile_frame(self, owner: str, elapsed: float) -> pygame.Surface:
        frames = self.projectile_animation_frames.get(
            owner, self.projectile_animation_frames["enemy"]
        )
        return self._frame_from(frames, elapsed, rate=12.0)

    def trap_frame(self, kind: str, elapsed: float) -> pygame.Surface:
        frames = self.trap_animation_frames.get(
            kind, self.trap_animation_frames["Spike Trap"]
        )
        return self._frame_from(frames, elapsed, rate=3.0)

    def shrine_frame(
        self, _kind: str, elapsed: float, used: bool = False
    ) -> pygame.Surface:
        state = "used" if used else "active"
        return self._frame_from(self.shrine_animation_frames[state], elapsed, rate=2.1)

    def secret_frame(self, elapsed: float) -> pygame.Surface:
        return self._frame_from(
            self.secret_animation_frames["cache"], elapsed, rate=2.0
        )

    def story_guest_frame(
        self, elapsed: float, resolved: bool = False
    ) -> pygame.Surface:
        state = "resolved" if resolved else "active"
        states = self.story_guest_animation_frames[state]
        return self._frame_from(states["idle"], elapsed, rate=3.2)

    def shopkeeper_frame(self, elapsed: float) -> pygame.Surface:
        return self._frame_from(
            self.shopkeeper_animation_frames["idle"], elapsed, rate=3.0
        )

    def _shade(self, color: Color, amount: int) -> Color:
        return (
            max(0, min(255, color[0] + amount)),
            max(0, min(255, color[1] + amount)),
            max(0, min(255, color[2] + amount)),
        )

    def _mix(self, a: Color, b: Color, ratio: float) -> Color:
        return (
            int(a[0] * (1.0 - ratio) + b[0] * ratio),
            int(a[1] * (1.0 - ratio) + b[1] * ratio),
            int(a[2] * (1.0 - ratio) + b[2] * ratio),
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
        self._rect(s, 2, 10, 4, 8, outline)
        self._rect(s, 12, 10, 4, 8, outline)
        self._rect(s, 3, 11, 3, 6, self._shade(body, -22))
        self._rect(s, 12, 11, 3, 6, self._shade(body, -28))
        self._rect(s, 3, 16, 2, 3, trim)
        self._rect(s, 13, 16, 2, 3, trim)
        self._rect(s, 3, 18, 2, 2, head)
        self._rect(s, 13, 18, 2, 2, self._shade(head, -12))
        self._rect(s, 4, 19, 1, 1, self._shade(head, 20))
        self._rect(s, 13, 19, 1, 1, self._shade(head, 10))
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
        self._dot(s, 7, 4, self._shade(head, 22))
        self._rect(s, 8, 6, 2, 1, self._shade(head, -26))
        self._rect(s, 4, 9, 3, 2, self._shade(trim, -24))
        self._rect(s, 11, 9, 3, 2, self._shade(trim, -24))
        self._rect(s, 5, 11, 1, 5, self._shade(body, -34))
        self._rect(s, 12, 11, 1, 5, self._shade(body, -34))
        self._rect(s, 7, 11, 1, 5, self._shade(body_hi, 28))
        self._rect(s, 10, 11, 1, 5, self._shade(body, -18))
        self._rect(s, 6, 18, 6, 1, self._shade(trim, -18))
        self._rect(s, 5, 20, 3, 1, self._shade(leather, 28))
        self._rect(s, 10, 20, 3, 1, self._shade(leather, 18))
        self._rect(s, 4, 23, 3, 1, self._shade(outline, 28))
        self._rect(s, 11, 23, 3, 1, self._shade(outline, 28))
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
        self._rect(s, 1, 11, 5, 8, (35, 43, 56))
        self._rect(s, 2, 12, 4, 6, (96, 104, 112))
        self._rect(s, 3, 13, 2, 4, (220, 226, 218))
        self._dot(s, 3, 12, (245, 238, 180))
        self._rect(s, 6, 1, 6, 1, (112, 122, 132))
        self._rect(s, 7, 2, 4, 1, (216, 226, 222))
        self._rect(s, 4, 8, 3, 1, (235, 205, 112))
        self._rect(s, 11, 8, 3, 1, (235, 205, 112))
        self._rect(s, 2, 10, 4, 1, (148, 156, 160))
        self._rect(s, 2, 16, 4, 1, (54, 64, 78))
        self._rect(s, 14, 6, 1, 10, (128, 141, 148))
        self._rect(s, 15, 4, 1, 3, (248, 252, 242))
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
        self._rect(s, 3, 9, 2, 8, (24, 26, 30))
        self._rect(s, 13, 9, 2, 8, (24, 26, 30))
        self._rect(s, 2, 11, 4, 2, (80, 94, 88))
        self._rect(s, 12, 11, 4, 2, (80, 94, 88))
        self._rect(s, 2, 14, 4, 1, (205, 210, 198))
        self._rect(s, 12, 14, 4, 1, (205, 210, 198))
        self._rect(s, 6, 16, 6, 1, (92, 170, 118))
        self._dot(s, 8, 12, (235, 215, 130))
        self._dot(s, 11, 12, (210, 245, 185))
        self._rect(s, 6, 3, 6, 1, (58, 62, 66))
        self._rect(s, 7, 4, 4, 1, (18, 20, 24))
        self._rect(s, 5, 17, 8, 2, (28, 32, 32))
        self._rect(s, 4, 18, 3, 1, (92, 170, 118))
        self._rect(s, 11, 18, 3, 1, (92, 170, 118))
        self._rect(s, 2, 13, 4, 1, (232, 232, 216))
        self._rect(s, 12, 13, 4, 1, (232, 232, 216))
        self._dot(s, 4, 12, (170, 230, 150))
        self._dot(s, 13, 12, (170, 230, 150))
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
        self._dot(s, 4, 10, (92, 210, 250))
        self._dot(s, 13, 17, (92, 210, 250))
        self._rect(s, 4, 18, 10, 1, (32, 36, 92))
        self._rect(s, 6, 11, 1, 4, (116, 220, 245))
        self._rect(s, 11, 11, 1, 4, (80, 170, 230))
        self._dot(s, 8, 16, (170, 235, 255))
        self._dot(s, 10, 16, (170, 235, 255))
        self._rect(s, 14, 4, 3, 1, (240, 255, 255))
        self._dot(s, 15, 8, (170, 235, 255))
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
        self._rect(s, 13, 15, 3, 3, (62, 26, 38))
        self._dot(s, 15, 6, (255, 190, 210))
        self._dot(s, 14, 16, (255, 95, 130))
        self._rect(s, 4, 17, 10, 2, (62, 20, 38))
        self._rect(s, 6, 18, 2, 1, (210, 84, 116))
        self._rect(s, 10, 18, 2, 1, (210, 84, 116))
        self._rect(s, 7, 12, 4, 1, (255, 196, 150))
        self._dot(s, 7, 14, (255, 95, 130))
        self._rect(s, 13, 13, 3, 1, (184, 74, 94))
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
        self._rect(s, 2, 8, 1, 6, (68, 44, 28))
        self._dot(s, 12, 11, (225, 240, 175))
        self._rect(s, 4, 3, 10, 1, (116, 90, 48))
        self._rect(s, 15, 8, 1, 7, (230, 226, 190))
        self._rect(s, 13, 4, 2, 7, (52, 64, 38))
        self._rect(s, 12, 5, 1, 1, (225, 240, 175))
        self._rect(s, 5, 15, 3, 1, (176, 138, 70))
        self._rect(s, 10, 15, 3, 1, (176, 138, 70))
        self._dot(s, 3, 7, (150, 215, 105))
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
        self._dot(s, 5, 6, (205, 236, 116))
        self._rect(s, 6, 11, 1, 5, (78, 112, 70))
        self._rect(s, 11, 11, 1, 5, (78, 112, 70))
        self._rect(s, 4, 16, 3, 1, (202, 202, 162))
        self._rect(s, 12, 16, 3, 1, (202, 202, 162))
        self._dot(s, 7, 12, (205, 236, 116))
        self._dot(s, 10, 14, (95, 54, 59))
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
        self._rect(s, 5, 18, 8, 2, (42, 25, 70))
        self._dot(s, 15, 8, (255, 220, 255))
        self._dot(s, 13, 9, (255, 220, 255))
        self._rect(s, 6, 2, 6, 1, (184, 138, 218))
        self._rect(s, 7, 6, 4, 1, (22, 18, 33))
        self._rect(s, 4, 17, 10, 2, (38, 28, 54))
        self._dot(s, 8, 13, (255, 190, 255))
        self._dot(s, 10, 13, (205, 79, 230))
        self._rect(s, 14, 12, 2, 1, (255, 190, 255))
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
        self._rect(s, 2, 6, 2, 2, (94, 60, 122))
        self._rect(s, 14, 6, 2, 2, (94, 60, 122))
        self._rect(s, 3, 5, 2, 1, (214, 202, 176))
        self._rect(s, 13, 5, 2, 1, (214, 202, 176))
        self._dot(s, 7, 12, (120, 245, 255))
        self._dot(s, 10, 12, (120, 245, 255))
        self._rect(s, 4, 18, 3, 1, (64, 42, 76))
        self._rect(s, 11, 18, 3, 1, (64, 42, 76))
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
        self._rect(s, 1, 12, 2, 4, (98, 66, 52))
        self._rect(s, 18, 12, 2, 4, (98, 66, 52))
        self._rect(s, 6, 2, 9, 1, (92, 62, 48))
        self._rect(s, 5, 8, 11, 1, (78, 52, 42))
        self._rect(s, 6, 11, 2, 6, iron)
        self._rect(s, 13, 11, 2, 6, self._shade(iron, -28))
        self._rect(s, 8, 17, 5, 1, (216, 166, 112))
        self._dot(s, 10, 12, (238, 190, 128))
        self._dot(s, 12, 15, eye)
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
        self._dot(s, 9, 5, (225, 255, 150))
        self._rect(s, 6, 10, 8, 1, (44, 95, 54))
        self._rect(s, 8, 4, 4, 1, (192, 246, 88))
        self._rect(s, 4, 12, 3, 1, venom)
        self._rect(s, 13, 12, 3, 1, venom)
        self._dot(s, 7, 7, (225, 255, 150))
        self._dot(s, 12, 7, (225, 255, 150))
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
        self._rect(s, 2, 9, 1, 6, (58, 43, 31))
        self._dot(s, 9, 12, (235, 210, 120))
        self._rect(s, 6, 4, 6, 1, (58, 43, 31))
        self._rect(s, 4, 17, 9, 1, (48, 52, 38))
        self._rect(s, 15, 9, 1, 7, (225, 218, 145))
        self._rect(s, 12, 6, 3, 1, (145, 164, 98))
        self._dot(s, 5, 13, (225, 218, 145))
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
        self._dot(s, 6, 4, ember)
        self._rect(s, 5, 4, 8, 1, (185, 86, 54))
        self._rect(s, 2, 5, 2, 1, ember)
        self._rect(s, 15, 8, 3, 1, (255, 160, 66))
        self._rect(s, 6, 13, 2, 1, ember)
        self._rect(s, 12, 13, 2, 1, ember)
        self._dot(s, 10, 6, (255, 224, 120))
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
        self._rect(s, 4, 7, 12, 1, (42, 46, 56))
        self._rect(s, 6, 8, 8, 1, (56, 62, 74))
        self._rect(s, 5, 13, 2, 4, (116, 220, 245))
        self._rect(s, 13, 13, 2, 4, self._shade(rune, -42))
        self._rect(s, 8, 18, 4, 1, (42, 46, 56))
        self._dot(s, 10, 4, (236, 255, 255))
        self._dot(s, 9, 15, (236, 255, 255))
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
        self._dot(s, 15, 10, spot)
        self._rect(s, 8, 14, 5, 1, outline)
        self._rect(s, 6, 6, 9, 1, self._shade(body, 24))
        self._rect(s, 3, 12, 4, 1, spot)
        self._rect(s, 14, 12, 4, 1, spot)
        self._dot(s, 8, 5, (255, 236, 140))
        self._dot(s, 12, 5, (255, 236, 140))
        self._dot(s, 11, 10, (88, 118, 58))
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
        self._rect(s, 14, 7, 1, 12, (216, 226, 222))
        self._rect(s, 5, 3, 8, 1, (182, 178, 160))
        self._rect(s, 4, 8, 10, 1, (42, 38, 42))
        self._rect(s, 6, 11, 1, 5, (182, 178, 160))
        self._rect(s, 11, 11, 1, 5, (94, 92, 92))
        self._rect(s, 15, 10, 1, 7, (248, 252, 242))
        self._dot(s, 9, 13, (120, 245, 255))
        return s

    def _gate_warden(self) -> pygame.Surface:
        s = self._crypt_brute()
        self._rect(s, 7, 3, 7, 5, (171, 105, 48))
        self._rect(s, 8, 4, 5, 2, (230, 156, 72))
        self._rect(s, 8, 5, 5, 1, (235, 65, 48))
        self._rect(s, 8, 11, 6, 5, (171, 105, 48))
        self._rect(s, 9, 12, 4, 3, (255, 202, 90))
        self._rect(s, 17, 4, 1, 14, (230, 156, 72))
        self._rect(s, 18, 3, 1, 3, (255, 202, 90))
        self._rect(s, 6, 9, 9, 1, (255, 202, 90))
        self._rect(s, 7, 14, 6, 1, (230, 156, 72))
        self._rect(s, 16, 7, 3, 2, (255, 202, 90))
        self._rect(s, 16, 15, 3, 1, (235, 65, 48))
        self._dot(s, 10, 13, (255, 235, 150))
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

    def _spike_trap(self) -> pygame.Surface:
        s = self._surface(18, 12)
        dark = (35, 26, 28)
        iron = (128, 132, 130)
        edge = (205, 75, 58)
        self._rect(s, 3, 4, 12, 5, dark)
        self._rect(s, 4, 5, 10, 3, (58, 48, 48))
        for x in (4, 8, 12):
            pygame.draw.polygon(s, iron, [(x, 4), (x + 2, 1), (x + 4, 4)])
        self._rect(s, 5, 8, 8, 1, edge)
        return s

    def _rune_trap(self) -> pygame.Surface:
        s = self._surface(18, 12)
        dark = (28, 23, 36)
        rune = (174, 108, 245)
        self._rect(s, 3, 4, 12, 5, dark)
        self._rect(s, 5, 5, 8, 3, (44, 35, 62))
        self._rect(s, 7, 4, 4, 1, rune)
        self._rect(s, 8, 5, 2, 3, rune)
        self._dot(s, 5, 6, (230, 190, 255))
        self._dot(s, 12, 6, (230, 190, 255))
        return s

    def _poison_trap(self) -> pygame.Surface:
        s = self._surface(18, 12)
        dark = (24, 38, 30)
        poison = (130, 220, 90)
        self._rect(s, 3, 4, 12, 5, dark)
        self._rect(s, 4, 5, 10, 3, (42, 70, 42))
        for x in (5, 9, 13):
            self._rect(s, x, 2, 1, 5, (150, 158, 136))
            self._dot(s, x, 1, poison)
        self._dot(s, 8, 8, poison)
        self._dot(s, 11, 8, poison)
        return s

    def _shrine(self, active: bool = True) -> pygame.Surface:
        s = self._surface(16, 20)
        stone = (66, 60, 70) if active else (54, 54, 60)
        edge = (235, 205, 110) if active else (116, 116, 124)
        glow = (255, 235, 158) if active else (96, 96, 106)
        self._rect(s, 5, 4, 6, 13, (28, 25, 31))
        self._rect(s, 6, 5, 4, 11, stone)
        self._rect(s, 4, 16, 8, 2, (34, 30, 36))
        self._rect(s, 5, 3, 6, 2, edge)
        self._rect(s, 7, 8, 2, 4, edge)
        self._dot(s, 8, 7, glow)
        if active:
            self._dot(s, 3, 7, glow)
            self._dot(s, 12, 11, glow)
        return s

    def _secret_cache(self) -> pygame.Surface:
        s = self._surface(16, 13)
        wood = (90, 56, 34)
        gold = (210, 162, 74)
        dark = (30, 22, 20)
        self._rect(s, 3, 5, 10, 6, dark)
        self._rect(s, 4, 5, 8, 5, wood)
        self._rect(s, 4, 4, 8, 2, gold)
        self._rect(s, 7, 6, 2, 3, gold)
        self._rect(s, 3, 10, 10, 1, dark)
        self._dot(s, 11, 6, (235, 205, 120))
        return s

    def _shopkeeper(self) -> pygame.Surface:
        s = self._humanoid_base(
            (205, 150, 104),
            (84, 52, 32),
            (138, 88, 42),
            (235, 190, 82),
            (24, 18, 15),
            (255, 235, 150),
        )
        gold = (245, 205, 92)
        dark_gold = (148, 98, 40)
        parchment = (226, 202, 142)
        wood = (92, 58, 34)
        beard = (84, 52, 36)
        apron = (48, 66, 72)
        blue_hi = (86, 116, 124)
        red = (158, 54, 42)
        self._rect(s, 5, 2, 8, 2, (70, 48, 32))
        self._rect(s, 4, 4, 10, 1, gold)
        self._rect(s, 6, 6, 6, 1, beard)
        self._rect(s, 7, 7, 4, 2, beard)
        self._rect(s, 4, 9, 10, 1, dark_gold)
        self._rect(s, 5, 10, 8, 1, gold)
        self._rect(s, 6, 11, 6, 6, apron)
        self._rect(s, 7, 12, 1, 4, blue_hi)
        self._rect(s, 10, 12, 1, 4, (32, 48, 54))
        self._rect(s, 8, 13, 2, 2, gold)
        self._dot(s, 9, 14, (255, 238, 150))
        self._rect(s, 6, 16, 6, 1, gold)
        self._rect(s, 2, 11, 4, 5, (58, 36, 26))
        self._rect(s, 12, 11, 4, 5, (58, 36, 26))
        self._rect(s, 3, 13, 2, 2, red)
        self._rect(s, 13, 13, 2, 2, red)
        self._dot(s, 4, 12, gold)
        self._dot(s, 13, 12, gold)
        self._rect(s, 13, 6, 4, 4, wood)
        self._rect(s, 14, 7, 2, 2, parchment)
        self._dot(s, 15, 8, gold)
        self._rect(s, 2, 16, 3, 3, (68, 42, 26))
        self._dot(s, 3, 17, gold)
        self._dot(s, 4, 17, (255, 238, 150))
        self._rect(s, 4, 18, 10, 1, (72, 42, 28))
        self._rect(s, 5, 19, 3, 1, gold)
        self._rect(s, 10, 19, 3, 1, gold)
        return s

    def _story_guest(self, active: bool = True) -> pygame.Surface:
        s = self._surface(18, 24)
        outline = (22, 16, 28)
        cloak = (86, 56, 120) if active else (62, 58, 70)
        cloak_hi = (132, 88, 180) if active else (94, 90, 104)
        face = (206, 168, 128) if active else (142, 132, 122)
        sigil = (220, 190, 255) if active else (138, 136, 146)
        self._rect(s, 5, 3, 8, 7, outline)
        self._rect(s, 6, 4, 6, 5, face)
        self._rect(s, 4, 8, 10, 13, outline)
        self._rect(s, 5, 8, 8, 12, cloak)
        self._rect(s, 7, 10, 4, 8, cloak_hi)
        self._rect(s, 3, 14, 3, 6, outline)
        self._rect(s, 12, 14, 3, 6, outline)
        self._rect(s, 6, 2, 6, 3, cloak)
        self._dot(s, 8, 13, sigil)
        self._dot(s, 9, 13, sigil)
        self._rect(s, 6, 21, 6, 2, outline)
        return s
