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

from __future__ import annotations

import math
import random

import pygame

from .constants import LIGHT_SHADE_DOWNSAMPLE_LONG, RUN_CYCLE_FRAMES, RUN_FRAME_RATE, TILE_H
from .lighting import bake_normal_map
from .models import Color

bone_color = (214, 202, 176)


class PixelSpriteAtlas:
    """Procedural pixel-art sprites and cached animation frames.

    The prototype keeps its art source in code so it can run without an
    external asset pipeline. Sprites are authored at a higher detail
    resolution (more sub-pixel shading, rim light, eye glow, armor plates),
    outlined, then scaled with nearest-neighbor filtering for a chunky
    dark-fantasy look.

    Sprite scale is grounded in dungeon geometry: actors target an on-screen
    height of roughly ``ACTOR_TARGET_H`` pixels (tied to ``TILE_H``) so they
    read correctly against the isometric floor diamond instead of dwarfing it.
    Runtime code should use the frame helpers for animated actors/objects
    while the legacy dictionaries remain available for static call sites and
    tests.
    """

    # On-screen target height for a standing humanoid, tied to tile geometry.
    # TILE_H is the iso floor diamond height; a humanoid ~1.15x that reads
    # as standing on the tile without towering over the dungeon.
    ACTOR_TARGET_H = round(TILE_H * 1.15)
    # Raw actor art is authored at 26x34; scale lands it near the target.
    RAW_ACTOR_W = 26
    RAW_ACTOR_H = 34
    ACTOR_SCALE = max(2, round(ACTOR_TARGET_H / RAW_ACTOR_H))
    # Props (items, traps, bolts) are smaller and use a separate scale.
    PROP_SCALE = max(2, round(TILE_H / 32))

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
        "Gate Tyrant": (190, 120, 240),
    }
    # Boss encounter accents drive the eye/rune glow tint on the gate tyrant
    # sprite. Keyed by damage type so each floor guardian gets a distinct hue
    # while the final boss uses the dungeon theme accent.
    BOSS_ACCENTS: dict[str, Color] = {
        "fire": (255, 132, 74),
        "frost": (150, 220, 250),
        "poison": (148, 226, 96),
        "arcane": (172, 130, 246),
        "shadow": (196, 110, 168),
        "holy": (252, 232, 150),
        "physical": (235, 188, 120),
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
            "Gate Tyrant": self._gate_tyrant(),
        }
        raw_items = {
            "potion": self._potion(),
            "mana_potion": self._mana_potion(),
            "identify": self._scroll(),
            "weapon": self._weapon(),
            "armor": self._armor(),
            "story_relic": self._story_relic(),
        }
        raw_projectiles = {
            "player": self._blue_bolt(),
            "enemy": self._void_bolt(),
        }
        # Per-archetype player bolt sprites so each class fires a distinct
        # projectile shape (arrows for Ranger, daggers for Rogue, etc.). The
        # Arcanist reuses the default arcane bolt.
        raw_player_bolts = {
            "Warden": self._guard_bolt(),
            "Rogue": self._throwing_dagger(),
            "Arcanist": self._blue_bolt(),
            "Acolyte": self._spirit_bolt(),
            "Ranger": self._arrow_bolt(),
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
        self.player_bolts = {
            name: self._scale_prop(surface)
            for name, surface in raw_player_bolts.items()
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
        self.player_bolt_animation_frames = {
            name: self._projectile_animation_frames(sprite)
            for name, sprite in self.player_bolts.items()
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
        self.shop_sign_sprite = self._scale_prop(self._shop_sign())
        # Gold-coin stack props scattered on the shop floor (size 1-3). Each
        # size is seeded to match the approved preview sprites so the in-game
        # look is identical to the reviewed gold_stacks PNGs.
        self.gold_stack_sprites = {
            size: self._scale_prop(self._gold_stack(size)) for size in (1, 2, 3)
        }
        # Milestone 3.15 — two familiar sprite states: a small wisp before
        # any Spirit skill is chosen, and a big owl once the Acolyte commits to
        # Spirit Call. Authored at 14x18 (small) and 26x34 (big). The owl is
        # scaled a touch smaller than the default prop scale so the big
        # familiar reads as a companion rather than a full-size actor.
        familiar_raw = {
            0: self._familiar_wisp(),
            1: self._familiar_owl(),
        }
        familiar_scales = {0: self.PROP_SCALE, 1: max(2, self.PROP_SCALE - 1)}
        self.familiar_sprites = {
            variant: self._scale(
                self._outline_surface(surface, (18, 14, 20)), familiar_scales[variant]
            )
            for variant, surface in familiar_raw.items()
        }
        # Note: no per-frame glow ellipse is added here. The familiar's
        # ground shadow is drawn separately in RenderingEffectsMixin.draw_familiar
        # via draw_shadow(), matching the player sprite's shadow. Adding a glow
        # ellipse here would stack a second, sharper shadow under the sprite.
        self.familiar_animation_frames = {
            variant: self._prop_animation_frames(sprite)
            for variant, sprite in self.familiar_sprites.items()
        }

    # ------------------------------------------------------------------
    # Low-level surface helpers
    # ------------------------------------------------------------------
    def _surface(self, w: int, h: int) -> pygame.Surface:
        return pygame.Surface((w, h), pygame.SRCALPHA)

    def _rect(
        self, surface: pygame.Surface, x: int, y: int, w: int, h: int, color: Color
    ) -> None:
        pygame.draw.rect(surface, color, (x, y, w, h))

    def _dot(self, surface: pygame.Surface, x: int, y: int, color: Color) -> None:
        self._rect(surface, x, y, 1, 1, color)

    def _hline(
        self, surface: pygame.Surface, x: int, y: int, w: int, color: Color
    ) -> None:
        self._rect(surface, x, y, w, 1, color)

    def _vline(
        self, surface: pygame.Surface, x: int, y: int, h: int, color: Color
    ) -> None:
        self._rect(surface, x, y, 1, h, color)

    def _outline_surface(
        self, surface: pygame.Surface, outline: Color = (11, 10, 14)
    ) -> pygame.Surface:
        """Add a one-pixel silhouette outline before scaling."""
        try:
            source = surface.convert_alpha()
        except pygame.error:
            source = surface.copy()
        w, h = source.get_width(), source.get_height()
        outlined = self._surface(w + 2, h + 2)
        outline_rgba = (*outline, 255)
        for x in range(w):
            for y in range(h):
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
                    if 0 <= px < w + 2 and 0 <= py < h + 2:
                        if outlined.get_at((px, py)).a == 0:
                            outlined.set_at((px, py), outline_rgba)
        outlined.blit(source, (1, 1))
        return outlined

    def _scale(
        self, surface: pygame.Surface, scale: int | None = None
    ) -> pygame.Surface:
        factor = scale or self.ACTOR_SCALE
        scaled = pygame.transform.scale(
            surface, (surface.get_width() * factor, surface.get_height() * factor)
        )
        try:
            return scaled.convert_alpha()
        except pygame.error:
            return scaled

    def _scale_actor(self, surface: pygame.Surface) -> pygame.Surface:
        return self._scale(self._outline_surface(surface), self.ACTOR_SCALE)

    def _scale_prop(self, surface: pygame.Surface) -> pygame.Surface:
        return self._scale(
            self._outline_surface(surface, (18, 14, 20)), self.PROP_SCALE
        )

    # ------------------------------------------------------------------
    # Frame composition helpers
    # ------------------------------------------------------------------
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
            # BLEND_RGB_ADD (not RGBA) keeps the transparent padding around
            # the sprite at alpha 0 so the tint cannot leak as a tinted box.
            frame.blit(flash, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
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
        unit = self.ACTOR_SCALE
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

    # ------------------------------------------------------------------
    # Multi-band pose animation
    # ------------------------------------------------------------------
    # The pose system slices each actor sprite into five vertical bands
    # (cap, head, torso, hip, legs, feet) and offsets them per-frame to
    # produce richer movement: breathing, stride sway, footfall lift,
    # attack windup/recoil, cast levitation, hit stagger, dash lean.
    # Band boundaries are expressed as fractions of sprite height so the
    # same pose code works for humanoids and non-humanoids alike.
    BAND_FRAC = (
        0.00,  # cap (hair/helmet top)
        0.16,  # head
        0.34,  # torso
        0.58,  # hip
        0.82,  # legs
        1.00,  # feet
    )
    # Each band borrows this many source rows from the band below it when it
    # is blitted, so a small per-band vertical offset (breathing, walk lift)
    # never reveals a transparent seam between the sliced sections. Actor art is
    # nearest-neighbour scaled, so every pixel is fully opaque or fully
    # transparent: the borrowed rows are idempotent when adjacent bands are
    # aligned and only fill the gap when they separate. Keep this >= the max
    # adjacent-band dy delta used by any pose below.
    BAND_OVERLAP = 1

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

        width = sprite.get_width()
        height = sprite.get_height()
        base_x = side_pad
        base_y = top_pad
        hand_light = self._shade(accent, 70)

        # Band boundaries in pixels.
        bands = [round(height * f) for f in self.BAND_FRAC]
        # bands: [cap_end, head_end, torso_end, hip_end, legs_end, feet_end]
        # Slice indices: 0..cap, cap..head, head..torso, torso..hip, hip..legs, legs..feet

        def blit_band(
            y0: int,
            y1: int,
            dx: int = 0,
            dy: int = 0,
            alpha: int = 255,
            overlap: int = 0,
        ) -> None:
            if y1 <= y0:
                return
            # Extend the source downward by ``overlap`` rows (clamped to the
            # sprite) so a band that sits above the next band after a vertical
            # offset still draws the neighbor's top pixels into the seam
            # instead of leaving transparent gaps.
            src_y1 = min(y1 + overlap, height)
            rect = pygame.Rect(0, y0, width, src_y1 - y0)
            if alpha >= 255:
                frame.blit(sprite, (base_x + dx, base_y + y0 + dy), rect)
                return
            band = pygame.Surface(rect.size, pygame.SRCALPHA)
            band.blit(sprite, (0, 0), rect)
            band.set_alpha(alpha)
            frame.blit(band, (base_x + dx, base_y + y0 + dy))

        def blit_pose(
            *,
            cap_dx: int = 0,
            cap_dy: int = 0,
            head_dx: int = 0,
            head_dy: int = 0,
            torso_dx: int = 0,
            torso_dy: int = 0,
            hip_dx: int = 0,
            hip_dy: int = 0,
            legs_dx: int = 0,
            legs_dy: int = 0,
            feet_dx: int = 0,
            feet_dy: int = 0,
        ) -> None:
            blit_band(0, bands[0], cap_dx, cap_dy, overlap=self.BAND_OVERLAP)
            blit_band(bands[0], bands[1], head_dx, head_dy, overlap=self.BAND_OVERLAP)
            blit_band(bands[1], bands[2], torso_dx, torso_dy, overlap=self.BAND_OVERLAP)
            blit_band(bands[2], bands[3], hip_dx, hip_dy, overlap=self.BAND_OVERLAP)
            blit_band(bands[3], bands[4], legs_dx, legs_dy, overlap=self.BAND_OVERLAP)
            blit_band(bands[4], height, feet_dx, feet_dy)

        if state == "idle":
            # 6-frame breathing: a gentle unified vertical bob of the upper
            # body (cap/head/torso/hip rise and fall together) with a subtle
            # 1px chest counter-motion, while the legs lag a hair and the feet
            # stay planted. Adjacent bands never separate by more than one
            # pixel, so ``BAND_OVERLAP`` hides the seam entirely and the sliced
            # sprite reads as one continuous body while standing still.
            i = index % 6
            bob = (0, -1, -2, -1, 0, 1)
            chest = (0, 0, 1, 0, 0, -1)
            legs_lag = (0, 0, -1, 0, 0, 1)
            blit_pose(
                cap_dy=bob[i],
                head_dy=bob[i],
                torso_dy=bob[i] + chest[i],
                hip_dy=bob[i],
                legs_dy=legs_lag[i],
                feet_dy=0,
            )

        elif state == "run":
            # 12-frame grounded walk cycle. The upper body (cap/head/torso)
            # stays stable and leads subtly into the stride while the hips and
            # legs drive the motion: feet swing forward and lift on the footfall
            # pulse, hips counter-rotate against the torso, and the whole pose
            # stays planted instead of floating. Offsets are kept small and
            # phase-locked to the whole-body bob in RenderingActorMixin.
            n = RUN_CYCLE_FRAMES
            i = index % n
            stride = math.sin(i / n * math.tau)  # -1..1 forward/back sway
            footfall = 0.5 - 0.5 * math.cos(i / n * math.tau)  # 0..1 lift pulse
            lift = round(footfall * 2.4)
            blit_pose(
                cap_dx=round(stride * 0.25),
                head_dx=round(stride * 0.35),
                torso_dx=round(stride * 0.6),
                torso_dy=round(-footfall * 0.3),
                hip_dx=round(-stride * 0.5),
                hip_dy=round(lift * 0.3),
                legs_dx=round(-stride * 1.2),
                legs_dy=round(lift * 0.5),
                feet_dx=round(stride * 1.8),
                feet_dy=-lift,
            )

        elif state == "attack":
            # 6-frame: anticipation (lean back), strike (lunge forward),
            # recovery (settle). Torso leads, hips trail, feet brace.
            phase = (0, 1, 2, 3, 4, 5)[index % 6]
            if phase <= 1:
                # windup: lean back, raise weapon
                wind = -2 - phase
                blit_pose(
                    cap_dx=round(wind * 0.4),
                    head_dx=round(wind * 0.6),
                    torso_dx=wind,
                    torso_dy=-1,
                    hip_dx=round(-wind * 0.3),
                    feet_dx=round(-wind * 0.5),
                )
            elif phase <= 3:
                # strike: lunge forward
                strike = (phase - 1) * 3
                blit_pose(
                    cap_dx=round(strike * 0.5),
                    head_dx=round(strike * 0.7),
                    torso_dx=strike,
                    torso_dy=1 if phase == 3 else 0,
                    hip_dx=round(strike * 0.4),
                    legs_dx=round(strike * 0.3),
                    feet_dx=round(-strike * 0.2),
                )
            else:
                # recovery: settle back
                rec = 2 - (phase - 3)
                blit_pose(
                    cap_dx=round(rec * 0.4),
                    head_dx=round(rec * 0.6),
                    torso_dx=rec,
                    hip_dx=round(-rec * 0.3),
                    feet_dx=round(-rec * 0.4),
                )

        elif state == "cast":
            # 6-frame: levitate, arms raise, hands glow. Whole body rises
            # smoothly; cap/head lift most, feet barely leave ground.
            n = 6
            i = index % n
            lev = (0, -1, -2, -3, -2, -1)[i]
            pulse = (0.0, -0.5, -1.0, -1.25, -0.75, -0.25)[i]
            blit_pose(
                cap_dy=lev,
                head_dy=round(lev * 0.9),
                torso_dy=round(lev * 0.7),
                hip_dy=round(lev * 0.4),
                legs_dy=round(lev * 0.15),
                feet_dy=round(lev * 0.05),
            )
            raw_w = max(1, width // self.ACTOR_SCALE)
            raw_h = max(1, height // self.ACTOR_SCALE)
            self._draw_scaled_rect(
                frame,
                (base_x, base_y),
                raw_w * 0.36,
                raw_h * 0.30 + pulse,
                5.2,
                0.55,
                hand_light,
                90,
            )

        elif state == "hit":
            # 4-frame stagger: recoil backward, head whips, torso follows,
            # feet brace against the blow.
            recoil = (-4, 3, 1, 0)[index % 4]
            blit_pose(
                cap_dx=round(recoil * 0.7),
                cap_dy=1 if index % 4 == 0 else 0,
                head_dx=round(recoil * 0.9),
                head_dy=1 if index % 4 == 0 else 0,
                torso_dx=recoil,
                hip_dx=round(recoil * 0.5),
                legs_dx=round(-recoil * 0.3),
                feet_dx=round(-recoil * 0.2),
            )

        elif state == "dash":
            # 4-frame: strong forward lean, body stretches, feet kick back.
            lean = (3, 5, 4, 2)[index % 4]
            blit_pose(
                cap_dx=round(lean * 0.6),
                cap_dy=-1,
                head_dx=round(lean * 0.8),
                head_dy=-1,
                torso_dx=lean,
                torso_dy=-1,
                hip_dx=round(lean * 0.7),
                hip_dy=-1,
                legs_dx=round(lean * 0.5),
                feet_dx=round(-lean * 0.4),
                feet_dy=1,
            )

        else:
            blit_pose()

        if tint is not None:
            tint_color, tint_alpha = tint
            flash = pygame.Surface(frame.get_size(), pygame.SRCALPHA)
            flash.fill((*tint_color, tint_alpha))
            # BLEND_RGB_ADD (not RGBA) so the tint only brightens the sprite's
            # opaque pixels; the transparent padding around the sprite keeps
            # alpha 0 instead of becoming a semi-transparent tinted box.
            frame.blit(flash, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
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
                for frame in range(6)
            ],
            "run": [
                self._actor_pose_frame(sprite, accent, "run", frame, hostile=hostile)
                for frame in range(RUN_CYCLE_FRAMES)
            ],
            "attack": [
                self._actor_pose_frame(
                    sprite,
                    accent,
                    "attack",
                    frame,
                    hostile=hostile,
                    tint=(accent, 8 + frame * 5),
                )
                for frame in range(6)
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
                    tint=(cast_glow, (16, 30, 42, 22, 16, 8)[frame]),
                    glow=(cast_glow, (30, 50, 70, 90, 60, 36)[frame]),
                )
                for frame in range(6)
            ],
            "hit": [
                self._actor_pose_frame(
                    sprite,
                    accent,
                    "hit",
                    frame,
                    hostile=hostile,
                    tint=(hit_color, (80, 56, 30, 14)[frame]),
                )
                for frame in range(4)
            ],
            "dash": [
                self._actor_pose_frame(
                    sprite,
                    accent,
                    "dash",
                    frame,
                    hostile=hostile,
                    tint=(accent, (30, 40, 24, 16)[frame]),
                )
                for frame in range(4)
            ],
        }

    def _item_animation_frames(self, sprite: pygame.Surface) -> list[pygame.Surface]:
        return [
            self._frame_surface(sprite, stretch=1.0),
            self._frame_surface(sprite, stretch=1.04, tilt=-2.0),
            self._frame_surface(sprite, stretch=1.02, tilt=1.0),
            self._frame_surface(sprite, stretch=0.98, tilt=2.0),
            self._frame_surface(sprite, stretch=1.0, tilt=-1.0),
            self._frame_surface(sprite, stretch=1.03, tilt=1.5),
        ]

    def _projectile_animation_frames(
        self, sprite: pygame.Surface
    ) -> list[pygame.Surface]:
        return [
            self._frame_surface(sprite, stretch=1.0),
            self._frame_surface(sprite, stretch=1.06, tint=((120, 220, 255), 32)),
            self._frame_surface(sprite, stretch=0.96),
            self._frame_surface(sprite, stretch=1.04, tint=((180, 240, 255), 20)),
        ]

    def _prop_animation_frames(
        self, sprite: pygame.Surface, glow: Color | None = None
    ) -> list[pygame.Surface]:
        glow_data = (glow, 36) if glow is not None else None
        return [
            self._frame_surface(sprite, stretch=1.0, glow=glow_data),
            self._frame_surface(sprite, stretch=1.02, tilt=-1.5, glow=glow_data),
            self._frame_surface(sprite, stretch=1.0, glow=glow_data),
            self._frame_surface(sprite, stretch=1.01, tilt=1.0, glow=glow_data),
            self._frame_surface(sprite, stretch=0.99, tilt=-1.0, glow=glow_data),
            self._frame_surface(sprite, stretch=1.02, tilt=1.5, glow=glow_data),
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
        phase = anim_time * RUN_FRAME_RATE if state == "run" else elapsed * 5.0
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
            return "Gate Tyrant"
        return "Ghoul"

    def boss_sprite_key(self, damage_type: str = "") -> str:
        """Unused placeholder for future per-theme boss sprite variants; today all
        4-tile bosses share the Gate Tyrant silhouette and are tinted via aura."""
        return "Gate Tyrant"

    def enemy_frame(
        self, name: str, kind: str, state: str, anim_time: float, elapsed: float
    ) -> pygame.Surface:
        key = self.enemy_key(name, kind)
        states = self.enemy_animation_frames.get(
            key, self.enemy_animation_frames["Ghoul"]
        )
        frames = states.get(state, states["idle"])
        phase = (
            anim_time * RUN_FRAME_RATE
            if state == "run"
            else elapsed * (4.3 if kind == "boss" else 5.0)
        )
        if state in ("attack", "cast", "hit"):
            phase = elapsed * 13.0
        return self._frame_from(frames, phase)

    def boss_frame(
        self, state: str, anim_time: float, elapsed: float
    ) -> pygame.Surface:
        """Animation frame for the shared 4-tile Gate Tyrant boss sprite."""
        states = self.enemy_animation_frames["Gate Tyrant"]
        frames = states.get(state, states["idle"])
        phase = anim_time * RUN_FRAME_RATE if state == "run" else elapsed * 4.3
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

    def projectile_frame(
        self, owner: str, elapsed: float, archetype: str = ""
    ) -> pygame.Surface:
        if owner == "player" and archetype in self.player_bolt_animation_frames:
            frames = self.player_bolt_animation_frames[archetype]
            return self._frame_from(frames, elapsed, rate=12.0)
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

    def familiar_frame(self, variant: int, elapsed: float) -> pygame.Surface:
        """Animation frame for a summoned familiar (Milestone 3.15).

        ``variant`` selects one of the two familiar states: 0 = small wisp
        (pre-skill) or 1 = big owl (post Spirit Call). Falls back to the base
        wisp if an unknown variant is requested.
        """
        frames = self.familiar_animation_frames.get(
            variant, self.familiar_animation_frames[0]
        )
        return self._frame_from(frames, elapsed, rate=3.4)

    # Milestone 3.16 - normal maps. A parallel cache keyed by sprite surface
    # identity (surfaces are built once in __init__ and never recreated, so
    # id() is a stable key). Baked lazily on first request so the cost is only
    # paid when the lighting + normal-map tiers are on. The bake is a pure
    # function of the source pixels (alpha silhouette + luminance -> Sobel), so
    # it is deterministic and applies to every sprite and tile surface.
    def normal_map_for(self, surface: pygame.Surface) -> pygame.Surface | None:
        if not getattr(self, "_normal_maps_enabled", True):
            return None
        cache = getattr(self, "_normal_map_cache", None)
        if cache is None:
            cache = {}
            self._normal_map_cache = cache
        key = id(surface)
        cached = cache.get(key)
        if cached is not None:
            return cached
        try:
            # Bake at the lit-shade downsample size so the one-time bake
            # cost is ~1k px/sprite (not ~25k) and the normal aligns with
            # the downsampled working size used by apply_lit_shading.
            w, h = surface.get_width(), surface.get_height()
            long_side = max(w, h)
            if long_side > LIGHT_SHADE_DOWNSAMPLE_LONG:
                f = LIGHT_SHADE_DOWNSAMPLE_LONG / long_side
                src = pygame.transform.scale(
                    surface, (max(1, int(w * f)), max(1, int(h * f)))
                )
            else:
                src = surface
            normal = bake_normal_map(src)
            normal = normal.convert_alpha()
        except pygame.error:
            normal = None
        cache[key] = normal
        return normal

    # ------------------------------------------------------------------
    # Color helpers
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # Detailed humanoid base
    # ------------------------------------------------------------------
    # Authored at 26x34 (vs the old 18x24). The extra pixels buy rim light,
    # armor plate shading, eye glow, belt/strap detail, and boot definition.
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
        s = self._surface(self.RAW_ACTOR_W, self.RAW_ACTOR_H)
        leather = (70, 48, 40)
        shadow = (38, 30, 36)
        body_lo = self._shade(body, -34)
        body_dk = self._shade(body, -52)
        head_hi = self._shade(head, 26)
        head_lo = self._shade(head, -22)
        trim_hi = self._shade(trim, 30)
        trim_lo = self._shade(trim, -28)

        # --- Head/helmet block ---
        self._rect(s, 8, 2, 10, 9, outline)
        self._rect(s, 9, 3, 8, 8, head)
        self._rect(s, 9, 3, 8, 1, head_hi)  # helmet rim light
        self._rect(s, 9, 10, 8, 1, head_lo)  # jaw shadow
        # eyes (glowing)
        self._rect(s, 10, 6, 2, 1, eye)
        self._rect(s, 14, 6, 2, 1, eye)
        self._dot(s, 10, 6, self._shade(eye, 60))
        self._dot(s, 14, 6, self._shade(eye, 60))
        # brow shadow
        self._hline(s, 9, 5, 8, shadow)
        # nose/mouth hint
        self._vline(s, 12, 8, 2, head_lo)

        # --- Torso (chest plate) ---
        self._rect(s, 6, 11, 14, 12, outline)
        self._rect(s, 7, 11, 12, 12, body)
        self._rect(s, 8, 12, 10, 10, body_hi)  # lit chest
        self._rect(s, 7, 11, 12, 1, trim_hi)  # shoulder yoke
        self._rect(s, 7, 22, 12, 1, trim_lo)  # belt line
        # center seam / sternum
        self._vline(s, 12, 12, 10, body_lo)
        # side shading
        self._vline(s, 7, 12, 10, body_dk)
        self._vline(s, 18, 12, 10, body_dk)
        # strap detail
        self._vline(s, 10, 12, 10, trim)
        self._vline(s, 15, 12, 10, trim_lo)
        # chest emblem dot
        self._dot(s, 12, 16, trim_hi)
        self._dot(s, 13, 16, trim_hi)

        # --- Arms (upper, along torso sides) ---
        self._rect(s, 4, 12, 3, 9, outline)
        self._rect(s, 19, 12, 3, 9, outline)
        self._rect(s, 5, 12, 2, 9, body_lo)
        self._rect(s, 19, 12, 2, 9, body_dk)
        # gauntlet cuffs
        self._rect(s, 4, 19, 3, 2, trim)
        self._rect(s, 19, 19, 3, 2, trim_lo)
        # hands
        self._rect(s, 5, 21, 2, 2, head)
        self._rect(s, 19, 21, 2, 2, head_lo)

        # --- Hips / belt ---
        self._rect(s, 7, 23, 12, 3, outline)
        self._rect(s, 8, 23, 10, 3, leather)
        self._rect(s, 8, 23, 10, 1, self._shade(leather, 28))
        self._rect(s, 12, 23, 2, 3, trim_hi)  # buckle

        # --- Legs ---
        self._rect(s, 7, 26, 4, 6, outline)
        self._rect(s, 15, 26, 4, 6, outline)
        self._rect(s, 8, 26, 3, 6, body_lo)
        self._rect(s, 15, 26, 3, 6, body_dk)
        # knee plate
        self._rect(s, 8, 28, 3, 1, trim)
        self._rect(s, 15, 28, 3, 1, trim_lo)

        # --- Boots ---
        self._rect(s, 7, 32, 5, 2, outline)
        self._rect(s, 14, 32, 5, 2, outline)
        self._rect(s, 8, 32, 4, 2, leather)
        self._rect(s, 15, 32, 4, 2, self._shade(leather, -12))
        self._hline(s, 8, 33, 4, self._shade(leather, 24))
        self._hline(s, 15, 33, 4, self._shade(leather, 12))

        # --- Cape/cloak hint behind shoulders ---
        self._rect(s, 5, 11, 2, 10, self._shade(outline, 18))
        self._rect(s, 19, 11, 2, 10, self._shade(outline, 8))

        if weapon:
            # sword held in right hand, pointing up
            self._vline(s, 21, 6, 14, weapon)
            self._vline(s, 22, 6, 14, self._shade(weapon, 30))
            self._hline(s, 20, 19, 4, self._shade(weapon, -20))  # crossguard
            self._dot(s, 21, 5, self._shade(weapon, 60))  # pommel
        return s

    # ------------------------------------------------------------------
    # Player archetypes
    # ------------------------------------------------------------------
    def _warden(self) -> pygame.Surface:
        s = self._humanoid_base(
            (215, 158, 105),  # head/helmet bronze
            (45, 93, 164),  # body blue
            (76, 140, 220),  # body_hi
            (154, 168, 178),  # trim steel
            (19, 24, 35),
            (40, 35, 32),
            (220, 226, 218),  # weapon silver
        )
        # Warden flourishes: full helm visor, shield on left arm, gold trim
        steel = (154, 168, 178)
        steel_hi = (205, 214, 220)
        gold = (235, 205, 112)
        blue = (30, 58, 116)
        # visor slit
        self._hline(s, 10, 6, 6, (12, 14, 20))
        # shield on left arm
        self._rect(s, 2, 14, 4, 8, (35, 43, 56))
        self._rect(s, 3, 15, 3, 6, steel)
        self._rect(s, 3, 15, 3, 1, steel_hi)
        self._rect(s, 4, 17, 1, 3, gold)
        self._dot(s, 4, 16, gold)
        # shoulder pauldrons
        self._rect(s, 5, 11, 3, 2, steel)
        self._rect(s, 18, 11, 3, 2, self._shade(steel, -20))
        self._dot(s, 6, 11, steel_hi)
        self._dot(s, 19, 11, steel)
        # gold belt buckle
        self._rect(s, 12, 23, 2, 2, gold)
        # blue tabard
        self._rect(s, 9, 12, 6, 11, blue)
        self._vline(s, 11, 12, 11, self._shade(blue, 30))
        self._hline(s, 9, 22, 6, gold)
        return s

    def _rogue_player(self) -> pygame.Surface:
        s = self._humanoid_base(
            (205, 145, 98),
            (42, 55, 58),
            (68, 92, 82),
            (92, 170, 118),
            (17, 20, 22),
            (210, 245, 185),
            (205, 210, 198),
        )
        dark = (24, 26, 30)
        green = (92, 170, 118)
        # hood cowl
        self._rect(s, 8, 2, 10, 4, dark)
        self._rect(s, 9, 3, 8, 2, (35, 38, 42))
        self._hline(s, 9, 5, 8, green)
        # mask band
        self._hline(s, 9, 7, 8, dark)
        # dagger sheaths
        self._vline(s, 4, 14, 6, (116, 74, 39))
        self._vline(s, 21, 14, 6, (116, 74, 39))
        self._dot(s, 4, 13, (205, 210, 198))
        self._dot(s, 21, 13, (205, 210, 198))
        # leather straps across chest
        self._hline(s, 7, 14, 12, (58, 62, 66))
        self._hline(s, 7, 18, 12, (58, 62, 66))
        # green sash
        self._hline(s, 7, 23, 12, green)
        # belt pouches
        self._rect(s, 9, 24, 2, 2, (58, 62, 66))
        self._rect(s, 15, 24, 2, 2, (58, 62, 66))
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
        arcane = (116, 220, 245)
        arcane_hi = (200, 245, 255)
        dark = (32, 36, 92)
        # pointed hat
        self._rect(s, 9, 0, 8, 3, dark)
        self._rect(s, 10, 0, 6, 2, arcane)
        self._dot(s, 13, 0, arcane_hi)
        # hat brim
        self._hline(s, 7, 3, 12, dark)
        # robe lower (longer than base legs)
        self._rect(s, 6, 26, 14, 6, dark)
        self._rect(s, 7, 26, 12, 6, (52, 42, 130))
        self._vline(s, 12, 26, 6, arcane)
        # glowing runes on robe
        self._dot(s, 9, 28, arcane_hi)
        self._dot(s, 15, 28, arcane_hi)
        self._dot(s, 12, 30, arcane_hi)
        # staff with crystal
        self._vline(s, 22, 4, 26, (88, 62, 138))
        self._rect(s, 21, 2, 4, 3, arcane)
        self._dot(s, 22, 2, arcane_hi)
        self._dot(s, 23, 3, arcane_hi)
        # arcane orb in left hand
        self._dot(s, 5, 21, arcane_hi)
        self._dot(s, 6, 22, arcane)
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
        blood = (210, 84, 116)
        blood_hi = (255, 95, 130)
        dark = (42, 18, 34)
        # hood
        self._rect(s, 8, 2, 10, 4, dark)
        self._rect(s, 9, 3, 8, 2, (62, 26, 38))
        self._hline(s, 9, 5, 8, blood)
        # face markings (blood streak)
        self._vline(s, 12, 6, 4, blood_hi)
        # robe lower
        self._rect(s, 6, 26, 14, 6, dark)
        self._rect(s, 7, 26, 12, 6, (62, 26, 38))
        self._vline(s, 12, 26, 6, blood)
        # sacrificial dagger
        self._vline(s, 21, 12, 10, (120, 74, 52))
        self._dot(s, 21, 11, blood_hi)
        # blood chalice in left hand
        self._rect(s, 4, 20, 3, 3, (120, 74, 52))
        self._dot(s, 5, 21, blood_hi)
        # bone rosary
        self._dot(s, 9, 14, (235, 225, 200))
        self._dot(s, 11, 15, (235, 225, 200))
        self._dot(s, 13, 14, (235, 225, 200))
        return s

    def _ranger_player(self) -> pygame.Surface:
        s = self._humanoid_base(
            (205, 150, 104),
            (54, 94, 58),
            (88, 145, 72),
            (176, 138, 70),
            (20, 28, 22),
            (225, 240, 175),
            (216, 226, 222),
        )
        leather = (116, 74, 39)
        green = (88, 145, 72)
        # hood
        self._rect(s, 8, 2, 10, 4, (70, 50, 34))
        self._rect(s, 9, 3, 8, 2, (94, 68, 40))
        self._hline(s, 9, 5, 8, green)
        # quiver on back
        self._rect(s, 4, 12, 3, 6, leather)
        self._vline(s, 5, 10, 4, (216, 226, 222))
        self._vline(s, 6, 10, 4, (216, 226, 222))
        # bow in right hand
        self._vline(s, 22, 6, 16, leather)
        self._vline(s, 23, 8, 12, (216, 226, 222))  # bowstring
        # leather chest straps
        self._hline(s, 7, 15, 12, leather)
        self._hline(s, 7, 19, 12, leather)
        # boot toe caps
        self._hline(s, 7, 33, 3, leather)
        self._hline(s, 16, 33, 3, leather)
        return s

    # ------------------------------------------------------------------
    # Enemies
    # ------------------------------------------------------------------
    def _ghoul(self) -> pygame.Surface:
        s = self._humanoid_base(
            (118, 154, 94),
            (118, 154, 94),
            (161, 189, 116),
            (95, 54, 59),
            (31, 20, 22),
            (238, 226, 126),
        )
        flesh = (161, 189, 116)
        flesh_lo = (78, 112, 70)
        blood = (95, 54, 59)
        # tattered hood
        self._rect(s, 8, 2, 10, 3, flesh_lo)
        # sunken eyes (bigger, glowing)
        self._rect(s, 10, 6, 2, 1, (238, 226, 126))
        self._rect(s, 14, 6, 2, 1, (238, 226, 126))
        # jagged mouth
        self._hline(s, 10, 9, 6, blood)
        self._vline(s, 11, 9, 1, flesh)
        self._vline(s, 13, 9, 1, flesh)
        self._vline(s, 15, 9, 1, flesh)
        # exposed ribs
        self._vline(s, 9, 14, 5, flesh_lo)
        self._vline(s, 12, 14, 5, flesh_lo)
        self._vline(s, 15, 14, 5, flesh_lo)
        # clawed hands
        self._vline(s, 4, 22, 2, blood)
        self._vline(s, 21, 22, 2, blood)
        # bloody feet
        self._hline(s, 7, 33, 4, blood)
        self._hline(s, 15, 33, 4, blood)
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
        purple = (205, 79, 230)
        purple_hi = (255, 190, 255)
        dark = (22, 18, 33)
        # hood
        self._rect(s, 8, 2, 10, 5, dark)
        self._rect(s, 9, 3, 8, 3, (42, 25, 70))
        self._hline(s, 9, 5, 8, purple)
        # glowing eyes
        self._dot(s, 11, 6, purple_hi)
        self._dot(s, 15, 6, purple_hi)
        # robe lower
        self._rect(s, 6, 26, 14, 6, dark)
        self._rect(s, 7, 26, 12, 6, (42, 25, 70))
        self._vline(s, 12, 26, 6, purple)
        # sigil on chest
        self._dot(s, 12, 16, purple_hi)
        self._dot(s, 11, 17, purple)
        self._dot(s, 13, 17, purple)
        # dagger
        self._vline(s, 21, 12, 8, (120, 74, 52))
        self._dot(s, 21, 11, purple_hi)
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
        bone = (214, 202, 176)
        bone_lo = (160, 148, 124)
        purple = (190, 130, 215)
        glow = (120, 245, 255)
        # horned skull
        self._rect(s, 7, 0, 3, 3, bone)
        self._rect(s, 16, 0, 3, 3, bone)
        self._dot(s, 8, 0, bone_lo)
        self._dot(s, 17, 0, bone_lo)
        # eye sockets (deep glow)
        self._rect(s, 10, 5, 2, 2, (30, 22, 36))
        self._rect(s, 14, 5, 2, 2, (30, 22, 36))
        self._dot(s, 10, 5, glow)
        self._dot(s, 14, 5, glow)
        # rib cage
        self._hline(s, 8, 14, 10, bone_lo)
        self._hline(s, 8, 17, 10, bone_lo)
        self._hline(s, 8, 20, 10, bone_lo)
        self._vline(s, 12, 13, 9, bone)
        # bony claws
        self._vline(s, 4, 21, 3, bone)
        self._vline(s, 21, 21, 3, bone)
        # spiky tail
        self._vline(s, 22, 24, 6, purple)
        self._dot(s, 22, 30, glow)
        return s

    def _crypt_brute(self) -> pygame.Surface:
        s = self._surface(30, 36)
        outline = (29, 23, 22)
        hide = (155, 105, 74)
        hide_hi = (198, 143, 94)
        hide_lo = (98, 66, 52)
        iron = (126, 132, 128)
        iron_hi = (170, 176, 172)
        dark = (58, 46, 43)
        eye = (250, 110, 70)
        # massive head
        self._rect(s, 8, 2, 14, 10, outline)
        self._rect(s, 9, 3, 12, 9, hide)
        self._rect(s, 9, 3, 12, 1, hide_hi)
        # horns
        self._rect(s, 6, 0, 3, 4, dark)
        self._rect(s, 21, 0, 3, 4, dark)
        self._dot(s, 7, 0, hide_lo)
        self._dot(s, 22, 0, hide_lo)
        # eyes
        self._rect(s, 11, 6, 3, 2, eye)
        self._rect(s, 16, 6, 3, 2, eye)
        self._dot(s, 11, 6, self._shade(eye, 60))
        self._dot(s, 16, 6, self._shade(eye, 60))
        # tusks
        self._vline(s, 11, 10, 3, bone_color)
        self._vline(s, 18, 10, 3, bone_color)
        # broad torso
        self._rect(s, 4, 12, 22, 14, outline)
        self._rect(s, 6, 12, 18, 14, hide)
        self._rect(s, 8, 13, 14, 12, hide_hi)
        # iron shoulder plates
        self._rect(s, 3, 12, 4, 4, iron)
        self._rect(s, 23, 12, 4, 4, self._shade(iron, -28))
        self._dot(s, 4, 13, iron_hi)
        self._dot(s, 24, 13, iron)
        # chest straps
        self._hline(s, 6, 18, 18, dark)
        self._hline(s, 6, 22, 18, dark)
        # gut plate
        self._rect(s, 11, 20, 8, 4, iron)
        self._dot(s, 14, 22, iron_hi)
        # arms
        self._rect(s, 1, 13, 4, 10, outline)
        self._rect(s, 25, 13, 4, 10, outline)
        self._rect(s, 2, 13, 3, 10, hide_lo)
        self._rect(s, 25, 13, 3, 10, self._shade(hide_lo, -16))
        # clawed hands
        self._rect(s, 1, 22, 4, 3, dark)
        self._rect(s, 25, 22, 4, 3, dark)
        self._vline(s, 2, 24, 2, eye)
        self._vline(s, 27, 24, 2, eye)
        # legs
        self._rect(s, 8, 26, 6, 8, outline)
        self._rect(s, 16, 26, 6, 8, outline)
        self._rect(s, 9, 26, 4, 8, hide_lo)
        self._rect(s, 17, 26, 4, 8, self._shade(hide_lo, -16))
        # feet
        self._rect(s, 7, 34, 7, 2, outline)
        self._rect(s, 16, 34, 7, 2, outline)
        return s

    def _venom_skitter(self) -> pygame.Surface:
        s = self._surface(28, 22)
        outline = (24, 40, 24)
        body = (74, 138, 72)
        hi = (128, 218, 104)
        lo = (44, 95, 54)
        venom = (192, 246, 88)
        eye = (255, 236, 120)
        # abdomen
        self._rect(s, 8, 6, 14, 10, outline)
        self._rect(s, 9, 6, 12, 10, body)
        self._rect(s, 11, 7, 8, 5, hi)
        self._hline(s, 9, 14, 12, lo)
        # cephalothorax
        self._rect(s, 4, 8, 6, 6, outline)
        self._rect(s, 5, 8, 5, 6, body)
        # eyes (cluster)
        self._dot(s, 5, 9, eye)
        self._dot(s, 7, 9, eye)
        self._dot(s, 6, 10, eye)
        self._dot(s, 8, 10, eye)
        # fangs
        self._vline(s, 4, 13, 3, venom)
        self._vline(s, 6, 13, 3, venom)
        # legs (8, jointed)
        leg_pts = [
            (3, 7, 1, 4),
            (3, 9, 0, 7),
            (3, 11, 1, 10),
            (4, 13, 2, 13),
            (22, 7, 26, 4),
            (22, 9, 27, 7),
            (22, 11, 26, 10),
            (21, 13, 25, 13),
        ]
        for x1, y1, x2, y2 in leg_pts:
            pygame.draw.line(s, outline, (x1, y1), (x2, y2), 1)
            pygame.draw.line(s, lo, (x1, y1), (x2, y2), 1)
        # venom drip
        self._vline(s, 14, 16, 3, venom)
        self._dot(s, 14, 19, venom)
        # abdomen markings
        self._dot(s, 12, 9, venom)
        self._dot(s, 16, 11, venom)
        self._dot(s, 14, 12, eye)
        return s

    def _grave_archer(self) -> pygame.Surface:
        s = self._humanoid_base(
            (116, 105, 76),
            (86, 116, 72),
            (145, 164, 98),
            (58, 43, 31),
            (26, 31, 25),
            (225, 218, 145),
            (216, 226, 222),
        )
        leather = (116, 74, 39)
        cloth = (58, 43, 31)
        # hood
        self._rect(s, 8, 2, 10, 4, cloth)
        self._rect(s, 9, 3, 8, 2, (94, 68, 40))
        # bandit mask
        self._hline(s, 9, 7, 8, cloth)
        # bow
        self._vline(s, 22, 6, 18, leather)
        self._vline(s, 23, 8, 14, (216, 226, 222))
        # quiver
        self._rect(s, 4, 12, 3, 6, leather)
        self._vline(s, 5, 10, 4, (216, 226, 222))
        # tattered cloak
        self._rect(s, 5, 11, 2, 12, self._shade(cloth, 12))
        self._rect(s, 19, 11, 2, 12, self._shade(cloth, 6))
        # arrow nocked
        self._vline(s, 21, 10, 10, (216, 226, 222))
        self._dot(s, 21, 9, (225, 218, 145))
        return s

    def _ash_hound(self) -> pygame.Surface:
        s = self._surface(30, 20)
        outline = (30, 22, 20)
        fur = (112, 62, 46)
        fur_hi = (165, 92, 64)
        fur_lo = (74, 40, 30)
        ash = (185, 86, 54)
        ember = (255, 160, 66)
        eye = (255, 224, 120)
        # body
        self._rect(s, 6, 7, 16, 8, outline)
        self._rect(s, 7, 7, 14, 8, fur)
        self._rect(s, 8, 7, 12, 2, fur_hi)
        self._hline(s, 7, 14, 14, fur_lo)
        # head
        self._rect(s, 18, 4, 8, 8, outline)
        self._rect(s, 19, 4, 7, 8, fur)
        self._rect(s, 19, 4, 7, 1, fur_hi)
        # ears (pointed, ash)
        self._rect(s, 18, 2, 2, 3, ash)
        self._rect(s, 24, 2, 2, 3, ash)
        # eye
        self._rect(s, 22, 6, 2, 1, eye)
        self._dot(s, 22, 6, self._shade(eye, 60))
        # snout
        self._rect(s, 25, 8, 2, 2, fur_lo)
        # fangs
        self._vline(s, 24, 10, 2, ember)
        self._vline(s, 26, 10, 2, ember)
        # legs
        self._rect(s, 7, 14, 3, 5, outline)
        self._rect(s, 12, 14, 3, 5, outline)
        self._rect(s, 16, 14, 3, 5, outline)
        self._rect(s, 20, 14, 3, 5, outline)
        self._rect(s, 8, 14, 2, 5, fur_lo)
        self._rect(s, 13, 14, 2, 5, fur_lo)
        self._rect(s, 17, 14, 2, 5, fur_lo)
        self._rect(s, 21, 14, 2, 5, fur_lo)
        # tail (curled, ember-tipped)
        self._vline(s, 4, 6, 4, fur)
        self._vline(s, 3, 4, 3, fur_lo)
        self._dot(s, 3, 3, ember)
        # ember cracks along body
        self._dot(s, 10, 9, ember)
        self._dot(s, 14, 11, ember)
        self._dot(s, 18, 9, ember)
        return s

    def _rune_sentinel(self) -> pygame.Surface:
        s = self._surface(28, 34)
        outline = (28, 30, 38)
        stone = (88, 98, 112)
        stone_hi = (142, 155, 168)
        stone_lo = (54, 62, 76)
        rune = (116, 220, 245)
        rune_hi = (200, 245, 255)
        dark = (42, 46, 56)
        # head (stone block)
        self._rect(s, 9, 2, 10, 8, outline)
        self._rect(s, 10, 3, 8, 7, stone)
        self._rect(s, 10, 3, 8, 1, stone_hi)
        # glowing rune-face
        self._hline(s, 12, 6, 4, rune)
        self._vline(s, 13, 5, 3, rune)
        self._dot(s, 12, 6, rune_hi)
        self._dot(s, 15, 6, rune_hi)
        # shoulders (broad slab)
        self._rect(s, 4, 10, 20, 4, outline)
        self._rect(s, 6, 10, 16, 4, stone)
        self._rect(s, 6, 10, 16, 1, stone_hi)
        # torso pillar
        self._rect(s, 7, 14, 14, 12, outline)
        self._rect(s, 8, 14, 12, 12, stone)
        self._rect(s, 9, 14, 10, 12, stone_hi)
        # central rune groove
        self._vline(s, 13, 15, 10, rune)
        self._dot(s, 13, 17, rune_hi)
        self._dot(s, 13, 22, rune_hi)
        # side runes
        self._vline(s, 10, 16, 6, rune)
        self._vline(s, 17, 16, 6, self._shade(rune, -42))
        # arms (slabs)
        self._rect(s, 2, 14, 4, 10, outline)
        self._rect(s, 22, 14, 4, 10, outline)
        self._rect(s, 3, 14, 3, 10, dark)
        self._rect(s, 23, 14, 3, 10, dark)
        # legs (pillars)
        self._rect(s, 8, 26, 5, 8, outline)
        self._rect(s, 15, 26, 5, 8, outline)
        self._rect(s, 9, 26, 4, 8, stone_lo)
        self._rect(s, 16, 26, 4, 8, dark)
        # base
        self._rect(s, 7, 33, 7, 1, outline)
        self._rect(s, 15, 33, 7, 1, outline)
        return s

    def _plague_toad(self) -> pygame.Surface:
        s = self._surface(30, 24)
        outline = (24, 38, 30)
        body = (84, 132, 66)
        body_hi = (128, 172, 88)
        belly = (144, 172, 86)
        spot = (192, 226, 74)
        eye = (236, 210, 96)
        # body (squat)
        self._rect(s, 5, 8, 20, 12, outline)
        self._rect(s, 6, 8, 18, 12, body)
        self._rect(s, 7, 8, 16, 3, body_hi)
        self._rect(s, 9, 14, 12, 5, belly)
        # eye stalks
        self._rect(s, 7, 3, 4, 6, outline)
        self._rect(s, 19, 3, 4, 6, outline)
        self._rect(s, 8, 4, 2, 3, eye)
        self._rect(s, 20, 4, 2, 3, eye)
        self._dot(s, 8, 4, (255, 236, 140))
        self._dot(s, 20, 4, (255, 236, 140))
        # warts (spots)
        self._dot(s, 10, 10, spot)
        self._dot(s, 14, 9, spot)
        self._dot(s, 18, 11, spot)
        self._dot(s, 12, 12, spot)
        self._dot(s, 16, 13, spot)
        # legs
        self._rect(s, 3, 16, 5, 4, outline)
        self._rect(s, 22, 16, 5, 4, outline)
        self._rect(s, 4, 16, 4, 4, body)
        self._rect(s, 23, 16, 4, 4, body)
        # webbed feet
        self._hline(s, 2, 20, 6, outline)
        self._hline(s, 22, 20, 6, outline)
        # poison drip from mouth
        self._vline(s, 14, 20, 3, spot)
        self._dot(s, 14, 23, spot)
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
        steel = (126, 132, 128)
        steel_hi = (182, 178, 160)
        rust = (190, 92, 54)
        glow = (120, 245, 255)
        # great helm (no visor slit, just eye glow)
        self._rect(s, 8, 2, 10, 8, (24, 22, 24))
        self._rect(s, 9, 3, 8, 7, steel)
        self._rect(s, 9, 3, 8, 1, steel_hi)
        # glowing visor slit
        self._hline(s, 10, 6, 6, glow)
        self._dot(s, 10, 6, self._shade(glow, 60))
        self._dot(s, 15, 6, self._shade(glow, 60))
        # plume
        self._vline(s, 12, 0, 2, rust)
        self._vline(s, 13, 0, 3, rust)
        # breastplate
        self._rect(s, 7, 11, 12, 12, (32, 34, 42))
        self._rect(s, 8, 11, 10, 12, steel)
        self._rect(s, 9, 11, 8, 12, steel_hi)
        # rust streaks
        self._vline(s, 10, 14, 6, rust)
        self._vline(s, 15, 16, 5, self._shade(rust, -20))
        # tattered cloak
        self._rect(s, 5, 11, 2, 14, (42, 38, 42))
        self._rect(s, 19, 11, 2, 14, (32, 30, 34))
        # rusted greaves
        self._rect(s, 7, 26, 4, 6, (32, 34, 42))
        self._rect(s, 15, 26, 4, 6, (32, 34, 42))
        self._rect(s, 8, 26, 3, 6, self._shade(steel, -20))
        self._rect(s, 16, 26, 3, 6, self._shade(steel, -30))
        # greatsword
        self._vline(s, 22, 4, 22, steel_hi)
        self._vline(s, 23, 4, 22, steel)
        self._hline(s, 20, 25, 6, (190, 132, 58))
        return s

    def _gate_warden(self) -> pygame.Surface:
        s = self._crypt_brute()
        gold = (255, 202, 90)
        gold_hi = (255, 235, 150)
        gold_lo = (171, 105, 48)
        red = (235, 65, 48)
        # gilded helm
        self._rect(s, 9, 3, 12, 2, gold)
        self._rect(s, 9, 3, 12, 1, gold_hi)
        # crown horns
        self._rect(s, 6, 0, 3, 4, gold_lo)
        self._rect(s, 21, 0, 3, 4, gold_lo)
        self._dot(s, 7, 0, gold_hi)
        self._dot(s, 22, 0, gold_hi)
        # glowing rage eyes
        self._rect(s, 11, 6, 3, 2, red)
        self._rect(s, 16, 6, 3, 2, red)
        # gilded chest plate
        self._rect(s, 8, 13, 14, 2, gold)
        self._rect(s, 11, 20, 8, 4, gold_lo)
        self._rect(s, 12, 20, 6, 4, gold)
        self._dot(s, 14, 22, gold_hi)
        # gilded shoulders
        self._rect(s, 3, 12, 4, 4, gold_lo)
        self._rect(s, 23, 12, 4, 4, gold_lo)
        self._dot(s, 4, 13, gold_hi)
        self._dot(s, 24, 13, gold)
        # gilded weapon (greataxe)
        self._vline(s, 27, 4, 18, gold_lo)
        self._rect(s, 24, 6, 4, 8, gold)
        self._rect(s, 25, 6, 2, 8, gold_hi)
        return s

    def _gate_tyrant(self) -> pygame.Surface:
        """A towering 4-tile boss: crowned helm, plague horns, rune-glow eyes,
        segmented plate, a dragging greatblade, and a tattered cloak. Authored
        at 40x52 (roughly 1.5x a normal actor) so the scaled sprite reads as a
        hulking gatekeeper towering over regular enemies."""
        s = self._surface(40, 52)
        outline = (15, 11, 14)
        plate = (74, 70, 84)
        plate_hi = (122, 116, 134)
        plate_lo = (44, 40, 54)
        plate_dk = (28, 24, 34)
        iron = (96, 92, 104)
        iron_hi = (160, 154, 168)
        gold = (212, 168, 84)
        gold_hi = (250, 220, 132)
        gold_lo = (140, 102, 44)
        cloak = (54, 36, 52)
        cloak_hi = (78, 52, 74)
        bone = bone_color
        # eye/rune glow is painted with the boss accent at tint time, but a
        # default arcane violet reads well untinted.
        glow = (180, 120, 240)
        glow_hi = (220, 170, 255)

        # --- Tattered cloak behind the body ---
        self._rect(s, 4, 18, 32, 22, outline)
        self._rect(s, 5, 19, 30, 20, cloak)
        self._rect(s, 6, 19, 28, 3, cloak_hi)  # cloak shoulder light
        # ragged hem
        for x in range(5, 35, 3):
            self._rect(s, x, 38, 2, 3, cloak_hi)
            self._dot(s, x, 41, outline)

        # --- Head: crowned great-helm ---
        self._rect(s, 13, 2, 14, 12, outline)
        self._rect(s, 14, 3, 12, 11, plate)
        self._rect(s, 14, 3, 12, 2, plate_hi)  # helm rim light
        self._rect(s, 14, 13, 12, 1, plate_lo)  # jaw guard
        # brow visor slit
        self._hline(s, 14, 8, 12, plate_dk)
        # glowing eyes through the visor
        self._rect(s, 16, 9, 3, 2, glow)
        self._rect(s, 21, 9, 3, 2, glow)
        self._dot(s, 16, 9, glow_hi)
        self._dot(s, 21, 9, glow_hi)
        # crown / plague horns
        self._rect(s, 10, 0, 3, 5, gold_lo)
        self._rect(s, 27, 0, 3, 5, gold_lo)
        self._rect(s, 11, 0, 1, 4, gold)
        self._rect(s, 28, 0, 1, 4, gold)
        self._dot(s, 11, 0, gold_hi)
        self._dot(s, 28, 0, gold_hi)
        # central crown spike
        self._rect(s, 19, 0, 2, 3, gold)
        self._dot(s, 19, 0, gold_hi)
        # cheek tusk bones
        self._vline(s, 13, 11, 3, bone)
        self._vline(s, 27, 11, 3, bone)

        # --- Torso: segmented plate ---
        self._rect(s, 9, 14, 22, 18, outline)
        self._rect(s, 10, 15, 20, 17, plate)
        self._rect(s, 12, 16, 16, 14, plate_hi)  # lit chest
        self._rect(s, 10, 15, 20, 1, iron_hi)  # shoulder yoke
        self._rect(s, 10, 31, 20, 1, plate_dk)  # belt shadow
        # center seam + runic brand
        self._vline(s, 19, 16, 14, plate_lo)
        self._rect(s, 17, 20, 6, 3, plate_dk)  # rune recess
        self._rect(s, 18, 21, 4, 1, glow)  # glowing rune
        self._dot(s, 19, 21, glow_hi)
        # side shading
        self._vline(s, 10, 16, 14, plate_dk)
        self._vline(s, 29, 16, 14, plate_dk)
        # chest emblem (gold sigil)
        self._rect(s, 17, 25, 6, 3, gold_lo)
        self._rect(s, 18, 25, 4, 3, gold)
        self._dot(s, 19, 26, gold_hi)
        self._dot(s, 20, 26, gold_hi)
        # strap detail
        self._vline(s, 13, 16, 14, iron)
        self._vline(s, 26, 16, 14, plate_lo)

        # --- Pauldrons (big spiked shoulders) ---
        self._rect(s, 5, 14, 6, 6, outline)
        self._rect(s, 29, 14, 6, 6, outline)
        self._rect(s, 6, 15, 5, 5, iron)
        self._rect(s, 29, 15, 5, 5, plate_lo)
        self._dot(s, 7, 16, iron_hi)
        self._dot(s, 30, 16, iron)
        # shoulder spikes
        self._vline(s, 7, 11, 4, gold_lo)
        self._vline(s, 32, 11, 4, gold_lo)
        self._dot(s, 7, 11, gold_hi)
        self._dot(s, 32, 11, gold_hi)

        # --- Arms ---
        self._rect(s, 4, 20, 4, 12, outline)
        self._rect(s, 32, 20, 4, 12, outline)
        self._rect(s, 5, 20, 3, 12, plate_lo)
        self._rect(s, 33, 20, 3, 12, plate_dk)
        # gauntlet cuffs
        self._rect(s, 4, 29, 4, 3, gold_lo)
        self._rect(s, 32, 29, 4, 3, gold_lo)
        self._hline(s, 4, 30, 4, gold)
        self._hline(s, 32, 30, 4, gold)
        # clawed hands
        self._rect(s, 4, 32, 4, 3, outline)
        self._rect(s, 32, 32, 4, 3, outline)
        self._vline(s, 5, 34, 2, glow)
        self._vline(s, 34, 34, 2, glow)

        # --- Hips / belt ---
        self._rect(s, 10, 32, 20, 4, outline)
        self._rect(s, 11, 33, 18, 3, plate_dk)
        self._rect(s, 11, 33, 18, 1, plate_lo)
        self._rect(s, 18, 33, 4, 3, gold)  # buckle
        self._dot(s, 19, 34, gold_hi)

        # --- Legs (greaves) ---
        self._rect(s, 11, 36, 7, 12, outline)
        self._rect(s, 22, 36, 7, 12, outline)
        self._rect(s, 12, 36, 6, 12, plate_lo)
        self._rect(s, 22, 36, 6, 12, plate_dk)
        # knee plates
        self._rect(s, 12, 40, 6, 2, iron)
        self._rect(s, 22, 40, 6, 2, plate_lo)
        self._dot(s, 14, 41, iron_hi)
        self._dot(s, 24, 41, iron)
        # shin runic glow
        self._vline(s, 14, 43, 4, glow)
        self._vline(s, 25, 43, 4, glow)

        # --- Boots ---
        self._rect(s, 10, 48, 8, 4, outline)
        self._rect(s, 22, 48, 8, 4, outline)
        self._rect(s, 11, 48, 6, 4, plate_dk)
        self._rect(s, 23, 48, 6, 4, cloak)
        self._hline(s, 11, 50, 6, plate_lo)
        self._hline(s, 23, 50, 6, plate_dk)

        # --- Greatblade (dragged in right hand, towering above the helm) ---
        self._vline(s, 38, 4, 36, iron)  # shaft
        self._vline(s, 37, 4, 36, plate_lo)
        self._rect(s, 35, 6, 5, 16, outline)  # blade
        self._rect(s, 36, 6, 3, 16, iron_hi)
        self._rect(s, 36, 6, 1, 16, glow_hi)  # edge gleam
        self._hline(s, 34, 22, 7, gold_lo)  # crossguard
        self._hline(s, 34, 23, 7, gold)
        self._dot(s, 38, 24, gold_hi)  # pommel
        return s

    # ------------------------------------------------------------------
    # Items
    # ------------------------------------------------------------------
    def _potion(self) -> pygame.Surface:
        s = self._surface(16, 20)
        outline = (32, 22, 30)
        glass = (154, 210, 222)
        glass_hi = (205, 238, 245)
        liquid = (210, 54, 82)
        liquid_hi = (245, 110, 130)
        cork = (116, 74, 39)
        cork_hi = (160, 110, 60)
        shine = (238, 235, 208)
        # cork
        self._rect(s, 6, 1, 4, 3, cork)
        self._hline(s, 6, 1, 4, cork_hi)
        # neck
        self._rect(s, 5, 4, 6, 2, outline)
        self._rect(s, 6, 4, 4, 2, glass)
        # body
        self._rect(s, 3, 6, 10, 12, outline)
        self._rect(s, 4, 6, 8, 12, glass)
        self._rect(s, 4, 10, 8, 8, liquid)
        self._rect(s, 4, 10, 8, 1, liquid_hi)
        # shine
        self._vline(s, 5, 7, 4, shine)
        self._dot(s, 10, 7, glass_hi)
        return s

    def _mana_potion(self) -> pygame.Surface:
        s = self._potion()
        liquid = (54, 102, 210)
        liquid_hi = (105, 165, 255)
        self._rect(s, 4, 10, 8, 8, liquid)
        self._rect(s, 4, 10, 8, 1, liquid_hi)
        return s

    def _scroll(self) -> pygame.Surface:
        s = self._surface(18, 16)
        paper = (224, 207, 166)
        paper_hi = (245, 235, 200)
        edge = (132, 91, 52)
        edge_lo = (90, 60, 34)
        rune = (92, 70, 145)
        rune_hi = (160, 130, 220)
        # rolled ends
        self._rect(s, 1, 3, 3, 10, edge)
        self._rect(s, 14, 3, 3, 10, edge)
        self._vline(s, 1, 3, 10, edge_lo)
        self._vline(s, 16, 3, 10, edge_lo)
        # paper
        self._rect(s, 3, 4, 12, 8, paper)
        self._hline(s, 3, 4, 12, paper_hi)
        # runes
        self._hline(s, 6, 6, 6, rune)
        self._hline(s, 5, 9, 8, rune)
        self._hline(s, 7, 11, 4, rune)
        self._dot(s, 6, 6, rune_hi)
        self._dot(s, 11, 9, rune_hi)
        return s

    def _weapon(self) -> pygame.Surface:
        s = self._surface(16, 18)
        blade = (216, 226, 222)
        blade_hi = (248, 252, 242)
        blade_lo = (128, 141, 148)
        guard = (190, 132, 58)
        guard_hi = (235, 178, 78)
        grip = (78, 46, 32)
        # blade
        self._rect(s, 8, 1, 2, 9, blade)
        self._vline(s, 9, 1, 9, blade_hi)
        self._vline(s, 7, 2, 8, blade_lo)
        self._hline(s, 7, 1, 4, blade_hi)  # tip
        # crossguard
        self._rect(s, 5, 9, 8, 2, guard)
        self._hline(s, 5, 9, 8, guard_hi)
        # grip
        self._rect(s, 8, 11, 2, 5, grip)
        self._vline(s, 8, 11, 5, self._shade(grip, 20))
        # pommel
        self._rect(s, 7, 16, 4, 1, guard)
        self._dot(s, 8, 16, guard_hi)
        return s

    def _armor(self) -> pygame.Surface:
        s = self._surface(16, 18)
        outline = (36, 36, 42)
        leather = (99, 66, 46)
        plate = (145, 155, 160)
        plate_hi = (205, 214, 210)
        plate_lo = (95, 102, 106)
        # shoulders
        self._rect(s, 3, 2, 10, 3, outline)
        self._rect(s, 4, 2, 8, 3, leather)
        self._hline(s, 4, 2, 8, self._shade(leather, 28))
        # chestplate
        self._rect(s, 2, 5, 12, 10, outline)
        self._rect(s, 3, 5, 10, 10, plate)
        self._rect(s, 4, 5, 8, 10, plate_hi)
        # center seam
        self._vline(s, 7, 6, 8, plate_lo)
        # fluting
        self._vline(s, 5, 6, 8, plate_lo)
        self._vline(s, 10, 6, 8, plate_lo)
        # belt
        self._rect(s, 3, 14, 10, 2, outline)
        self._rect(s, 4, 14, 8, 2, leather)
        self._dot(s, 7, 14, plate_hi)
        return s

    def _story_relic(self) -> pygame.Surface:
        # The story relic: an octahedron cut gem (top + bottom pyramids meeting
        # at a visible equator) with four facet zones shaded lit-to-dark so it
        # reads as a faceted stone rather than a flat diamond. Authored at low
        # resolution in a neutral stone-gem palette; the atlas adds the dark
        # silhouette outline and nearest-neighbor upscale, and the live renderer
        # tint it with the per-story accent (see draw_story_relic) so the same
        # sprite recolors for each story without re-authoring art.
        s = self._surface(18, 24)
        top = (9, 1)
        left = (1, 12)
        right = (17, 12)
        bottom = (9, 23)
        center = (9, 12)
        facet_ul = (202, 199, 188)  # lit upper-left
        facet_ur = (150, 148, 140)  # mid upper-right
        facet_bl = (115, 113, 108)  # mid-dark lower-left
        facet_br = (84, 83, 79)  # darkest lower-right
        pygame.draw.polygon(s, facet_ul, [top, left, center])
        pygame.draw.polygon(s, facet_ur, [top, center, right])
        pygame.draw.polygon(s, facet_bl, [center, left, bottom])
        pygame.draw.polygon(s, facet_br, [center, bottom, right])
        # Bright lit ridge along the upper-left edge — the gem's specular edge.
        pygame.draw.line(s, (246, 240, 220), top, left)
        # Specular pinpricks on the lit facet.
        self._dot(s, 6, 8, (255, 251, 232))
        self._dot(s, 7, 7, (255, 251, 232))
        return s

    def _blue_bolt(self) -> pygame.Surface:
        s = self._surface(16, 12)
        core = (240, 250, 255)
        mid = (86, 215, 255)
        outer = (68, 170, 255)
        tail = (36, 92, 190)
        # tail
        self._rect(s, 0, 5, 4, 2, tail)
        self._dot(s, 0, 4, tail)
        self._dot(s, 0, 7, tail)
        # outer
        self._rect(s, 3, 4, 10, 4, outer)
        # mid
        self._rect(s, 5, 3, 7, 6, mid)
        # core
        self._rect(s, 7, 4, 4, 4, core)
        self._dot(s, 12, 5, core)
        self._dot(s, 13, 6, mid)
        return s

    def _void_bolt(self) -> pygame.Surface:
        s = self._surface(16, 12)
        core = (255, 220, 255)
        mid = (210, 83, 238)
        outer = (119, 54, 184)
        tail = (54, 30, 102)
        self._rect(s, 0, 5, 4, 2, tail)
        self._dot(s, 0, 4, tail)
        self._dot(s, 0, 7, tail)
        self._rect(s, 3, 4, 10, 4, outer)
        self._rect(s, 5, 3, 7, 6, mid)
        self._rect(s, 7, 4, 4, 4, core)
        self._dot(s, 12, 5, core)
        self._dot(s, 13, 6, mid)
        return s

    def _guard_bolt(self) -> pygame.Surface:
        # Warden — a holy hammer of light with a bright leading head and a
        # golden trailing shaft.
        s = self._surface(16, 12)
        core = (255, 250, 220)
        mid = (255, 220, 130)
        outer = (235, 180, 80)
        tail = (160, 120, 50)
        # shaft trail
        self._rect(s, 0, 5, 8, 2, tail)
        self._rect(s, 3, 5, 5, 2, outer)
        self._rect(s, 5, 5, 3, 2, mid)
        self._dot(s, 0, 4, tail)
        self._dot(s, 0, 7, tail)
        # shield/hammer head
        self._rect(s, 8, 3, 5, 6, outer)
        self._rect(s, 9, 4, 4, 4, mid)
        self._rect(s, 10, 5, 3, 2, core)
        self._dot(s, 13, 5, core)
        self._dot(s, 13, 6, core)
        # holy glints above/below the head
        self._dot(s, 11, 3, core)
        self._dot(s, 11, 8, core)
        return s

    def _throwing_dagger(self) -> pygame.Surface:
        # Rogue — a slim throwing dagger with a poisoned blade.
        s = self._surface(16, 12)
        steel = (220, 225, 230)
        steel_hi = (245, 248, 252)
        steel_lo = (150, 155, 160)
        handle = (90, 60, 40)
        poison = (150, 220, 110)
        # handle (left)
        self._rect(s, 2, 5, 5, 2, handle)
        self._dot(s, 1, 5, handle)
        self._dot(s, 1, 6, handle)
        # guard
        self._vline(s, 6, 4, 4, handle)
        self._dot(s, 6, 3, handle)
        # blade (right, pointing)
        self._rect(s, 7, 5, 7, 2, steel)
        self._rect(s, 7, 4, 5, 1, steel_hi)
        self._rect(s, 7, 7, 5, 1, steel_lo)
        self._rect(s, 12, 5, 2, 2, steel_hi)
        self._dot(s, 14, 5, steel_hi)
        self._dot(s, 14, 6, steel_hi)
        # poison glint on the blade
        self._dot(s, 10, 5, poison)
        self._dot(s, 9, 6, poison)
        return s

    def _spirit_bolt(self) -> pygame.Surface:
        # Acolyte — a dark wraith bolt with a skull-like leading head and
        # trailing shadow wisps.
        s = self._surface(16, 12)
        core = (255, 210, 230)
        mid = (210, 83, 238)
        outer = (119, 54, 184)
        tail = (54, 30, 102)
        shadow = (30, 18, 40)
        blood = (220, 80, 110)
        # trailing wisps
        self._rect(s, 0, 5, 8, 2, tail)
        self._rect(s, 2, 4, 4, 1, outer)
        self._rect(s, 2, 7, 4, 1, outer)
        self._dot(s, 0, 4, tail)
        self._dot(s, 0, 7, tail)
        # skull head
        self._rect(s, 8, 3, 6, 6, outer)
        self._rect(s, 9, 4, 5, 4, mid)
        self._rect(s, 10, 5, 4, 2, core)
        # eye sockets
        self._dot(s, 11, 5, shadow)
        self._dot(s, 12, 5, shadow)
        # crimson veins
        self._dot(s, 13, 4, blood)
        self._dot(s, 13, 7, blood)
        return s

    def _arrow_bolt(self) -> pygame.Surface:
        # Ranger — a feathered arrow with a steel head.
        s = self._surface(16, 12)
        tip = (220, 225, 230)
        tip_hi = (245, 248, 252)
        shaft = (150, 110, 70)
        shaft_hi = (180, 140, 90)
        fletch = (180, 215, 130)
        fletch_lo = (120, 170, 80)
        # fletching (left)
        self._rect(s, 0, 4, 4, 1, fletch)
        self._rect(s, 0, 7, 4, 1, fletch)
        self._rect(s, 1, 5, 3, 1, fletch_lo)
        self._rect(s, 1, 6, 3, 1, fletch_lo)
        self._dot(s, 0, 5, fletch)
        self._dot(s, 0, 6, fletch)
        # shaft
        self._rect(s, 3, 5, 9, 2, shaft)
        self._hline(s, 3, 5, 9, shaft_hi)
        # arrowhead (right)
        self._rect(s, 11, 4, 2, 1, tip)
        self._rect(s, 11, 7, 2, 1, tip)
        self._rect(s, 12, 5, 2, 2, tip)
        self._dot(s, 14, 5, tip_hi)
        self._dot(s, 14, 6, tip_hi)
        return s

    def _slash(self) -> pygame.Surface:
        s = self._surface(22, 14)
        pale = (255, 252, 210)
        gold = (235, 174, 74)
        gold_hi = (255, 240, 174)
        dark = (146, 90, 42)
        # arc trail
        self._rect(s, 2, 9, 4, 2, dark)
        self._rect(s, 5, 7, 4, 2, gold)
        self._rect(s, 8, 5, 4, 2, pale)
        self._rect(s, 11, 3, 4, 2, gold_hi)
        self._rect(s, 14, 2, 3, 2, pale)
        self._rect(s, 17, 1, 2, 1, gold_hi)
        # bright core
        self._hline(s, 6, 8, 9, pale)
        self._dot(s, 13, 4, pale)
        self._dot(s, 18, 2, pale)
        return s

    # ------------------------------------------------------------------
    # Traps
    # ------------------------------------------------------------------
    def _spike_trap(self) -> pygame.Surface:
        s = self._surface(20, 14)
        dark = (35, 26, 28)
        iron = (128, 132, 130)
        iron_hi = (180, 184, 182)
        edge = (205, 75, 58)
        # base plate
        self._rect(s, 3, 6, 14, 6, dark)
        self._rect(s, 4, 7, 12, 4, (58, 48, 48))
        self._hline(s, 3, 6, 14, edge)
        # spikes (triangles)
        for x in (4, 9, 14):
            pygame.draw.polygon(s, iron, [(x, 6), (x + 2, 1), (x + 4, 6)])
            pygame.draw.polygon(s, iron_hi, [(x + 1, 6), (x + 2, 2), (x + 3, 6)])
        # blood
        self._dot(s, 6, 5, edge)
        self._dot(s, 11, 5, edge)
        self._dot(s, 16, 5, edge)
        return s

    def _rune_trap(self) -> pygame.Surface:
        s = self._surface(20, 14)
        dark = (28, 23, 36)
        rune = (174, 108, 245)
        rune_hi = (220, 160, 255)
        self._rect(s, 3, 6, 14, 6, dark)
        self._rect(s, 5, 7, 10, 4, (44, 35, 62))
        # central sigil
        self._vline(s, 9, 3, 6, rune)
        self._hline(s, 7, 5, 6, rune)
        self._dot(s, 9, 5, rune_hi)
        self._dot(s, 7, 8, rune_hi)
        self._dot(s, 12, 8, rune_hi)
        return s

    def _poison_trap(self) -> pygame.Surface:
        s = self._surface(20, 14)
        dark = (24, 38, 30)
        poison = (130, 220, 90)
        poison_hi = (192, 246, 88)
        needle = (150, 158, 136)
        self._rect(s, 3, 6, 14, 6, dark)
        self._rect(s, 4, 7, 12, 4, (42, 70, 42))
        # needles
        for x in (5, 10, 15):
            self._vline(s, x, 2, 6, needle)
            self._dot(s, x, 1, poison_hi)
        # puddles
        self._dot(s, 7, 11, poison)
        self._dot(s, 12, 11, poison)
        self._dot(s, 10, 12, poison_hi)
        return s

    # ------------------------------------------------------------------
    # Props
    # ------------------------------------------------------------------
    def _shrine(self, active: bool = True) -> pygame.Surface:
        s = self._surface(20, 26)
        stone = (66, 60, 70) if active else (54, 54, 60)
        stone_hi = (110, 100, 116) if active else (78, 78, 84)
        edge = (235, 205, 110) if active else (116, 116, 124)
        glow = (255, 235, 158) if active else (96, 96, 106)
        # base
        self._rect(s, 3, 20, 14, 4, (28, 25, 31))
        self._rect(s, 4, 20, 12, 4, stone)
        self._hline(s, 4, 20, 12, stone_hi)
        # pillar
        self._rect(s, 7, 6, 6, 16, (28, 25, 31))
        self._rect(s, 8, 6, 4, 16, stone)
        self._vline(s, 8, 6, 16, stone_hi)
        # capital
        self._rect(s, 5, 4, 10, 3, edge)
        self._hline(s, 5, 4, 10, self._shade(edge, 30))
        # offering bowl
        self._rect(s, 8, 8, 4, 2, edge)
        self._dot(s, 9, 8, glow)
        self._dot(s, 10, 8, glow)
        if active:
            # floating glow motes
            self._dot(s, 6, 10, glow)
            self._dot(s, 13, 12, glow)
            self._dot(s, 9, 14, glow)
        return s

    def _secret_cache(self) -> pygame.Surface:
        s = self._surface(18, 16)
        wood = (90, 56, 34)
        wood_hi = (130, 84, 50)
        gold = (210, 162, 74)
        gold_hi = (245, 205, 120)
        dark = (30, 22, 20)
        # chest body
        self._rect(s, 2, 7, 14, 8, dark)
        self._rect(s, 3, 7, 12, 8, wood)
        self._hline(s, 3, 7, 12, wood_hi)
        # lid
        self._rect(s, 2, 4, 14, 4, dark)
        self._rect(s, 3, 4, 12, 4, wood)
        self._hline(s, 3, 4, 12, wood_hi)
        # bands
        self._vline(s, 5, 4, 11, dark)
        self._vline(s, 12, 4, 11, dark)
        # lock
        self._rect(s, 8, 8, 2, 3, gold)
        self._dot(s, 8, 8, gold_hi)
        # gold spilling
        self._dot(s, 6, 6, gold_hi)
        self._dot(s, 11, 6, gold)
        self._dot(s, 9, 3, gold_hi)
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
        gold_hi = (255, 235, 150)
        dark_gold = (148, 98, 40)
        wood = (92, 58, 34)
        beard = (84, 52, 36)
        apron = (48, 66, 72)
        blue_hi = (86, 116, 124)
        red = (158, 54, 42)
        # cap
        self._rect(s, 8, 1, 10, 3, dark_gold)
        self._hline(s, 8, 1, 10, gold)
        self._dot(s, 12, 1, gold_hi)
        # brim
        self._hline(s, 7, 4, 12, dark_gold)
        # beard (bushy)
        self._rect(s, 9, 7, 8, 4, beard)
        self._hline(s, 9, 7, 8, self._shade(beard, 20))
        self._vline(s, 12, 10, 3, beard)
        # gold-trimmed coat
        self._hline(s, 7, 12, 12, gold)
        self._hline(s, 7, 22, 12, gold)
        # apron
        self._rect(s, 8, 14, 10, 8, apron)
        self._vline(s, 12, 14, 8, blue_hi)
        # pouches
        self._rect(s, 7, 16, 2, 3, wood)
        self._rect(s, 17, 16, 2, 3, wood)
        self._dot(s, 8, 16, gold)
        self._dot(s, 18, 16, gold)
        # coin purse
        self._rect(s, 4, 18, 3, 3, red)
        self._dot(s, 5, 18, gold_hi)
        # walking staff
        self._vline(s, 22, 6, 22, wood)
        self._rect(s, 21, 4, 4, 3, gold)
        self._dot(s, 22, 4, gold_hi)
        return s

    def _shop_sign(self) -> pygame.Surface:
        # Hanging coin shop sign: a wooden plank suspended by two short
        # chains from a bracket beam, with a gold merchant coin in relief.
        s = self._surface(20, 26)
        wood = (110, 78, 50)
        wood_hi = (150, 110, 72)
        wood_dark = (74, 50, 34)
        wood_edge = (40, 26, 18)
        chain = (170, 165, 158)
        chain_dark = (90, 86, 80)
        gold = (245, 205, 92)
        gold_hi = (255, 232, 150)
        gold_dark = (180, 140, 50)
        # bracket beam above the board
        self._rect(s, 3, 2, 14, 2, wood_dark)
        self._hline(s, 3, 2, 14, wood)
        # two short chains down to the board
        for cx in (6, 13):
            self._dot(s, cx, 4, chain)
            self._dot(s, cx, 5, chain_dark)
            self._dot(s, cx, 6, chain)
        # wooden plank board with beveled edges
        bx, by, bw, bh = 3, 7, 14, 15
        self._rect(s, bx, by, bw, bh, wood)
        self._hline(s, bx, by, bw, wood_hi)
        self._hline(s, bx, by + bh - 1, bw, wood_edge)
        self._vline(s, bx, by, bh, wood_edge)
        self._vline(s, bx + bw - 1, by, bh, wood_edge)
        # gold coin motif in relief
        cx, cy = bx + bw // 2, by + bh // 2
        pygame.draw.circle(s, gold_dark, (cx, cy), 5)
        pygame.draw.circle(s, gold, (cx, cy), 4)
        pygame.draw.circle(s, gold_hi, (cx - 1, cy - 1), 2)
        # merchant mark glyph
        self._hline(s, cx - 3, cy - 1, 6, gold_dark)
        self._hline(s, cx - 3, cy + 1, 6, gold_dark)
        self._dot(s, cx, cy, gold_hi)
        return s

    def _story_guest(self, active: bool = True) -> pygame.Surface:
        # Quest NPC template: a wide-brimmed traveler's hat, distinct head/face
        # with glowing sigil eyes, a separate torso cloak with a clasp, arms
        # drawn as distinct sleeves with hands (not merged into the body), two
        # separate legs, and boots. Authored at the shared 26x34 actor canvas
        # so it scales and outlines alongside the player/enemy humanoids.
        # `active` is the violet quest-giver palette; `resolved` desaturates to
        # grey so a settled guest reads as spent.
        s = self._surface(self.RAW_ACTOR_W, self.RAW_ACTOR_H)
        outline = (22, 16, 28) if active else (24, 20, 26)
        # Muted traveler-robe palette (dusty mauve) so the guest reads as a
        # normal humanoid NPC, not a neon-glowing quest marker. The faint
        # violet sigil eyes are the only magical cue, kept dim.
        hat = (58, 48, 76) if active else (52, 48, 56)
        hat_hi = (92, 78, 116) if active else (82, 78, 88)
        hat_lo = (40, 32, 56) if active else (34, 32, 38)
        band = (200, 168, 92) if active else (150, 140, 120)  # gold hat band
        band_hi = (235, 200, 120) if active else (180, 170, 150)
        face = (206, 168, 128) if active else (142, 132, 122)
        face_hi = (232, 196, 156) if active else (170, 158, 148)
        face_lo = (150, 116, 88) if active else (100, 92, 86)
        cloak = (78, 64, 96) if active else (62, 58, 70)
        cloak_hi = (116, 98, 138) if active else (94, 90, 104)
        cloak_lo = (54, 44, 70) if active else (42, 40, 50)
        trim = (154, 168, 178) if active else (110, 110, 120)
        trim_hi = (205, 214, 220) if active else (150, 150, 160)
        sigil = (170, 150, 200) if active else (138, 136, 146)
        sigil_hi = (200, 180, 225) if active else (160, 158, 168)
        leather = (70, 48, 40)
        shadow = (38, 30, 36)

        # --- Hat: wide brim + crown + band ---
        # Crown rises above the brim.
        self._rect(s, 9, 0, 8, 5, outline)
        self._rect(s, 10, 1, 6, 4, hat)
        self._rect(s, 10, 1, 6, 1, hat_hi)  # lit crown top
        # Brim (wider than the head so it reads as a hat, not a helm).
        self._rect(s, 3, 4, 20, 2, outline)
        self._rect(s, 4, 4, 18, 1, hat_hi)  # lit brim top
        self._rect(s, 4, 5, 18, 1, hat_lo)  # brim underside shadow
        # Band around the crown base, with a small buckle.
        self._rect(s, 10, 3, 6, 1, band)
        self._dot(s, 12, 3, band_hi)
        self._dot(s, 13, 3, band_hi)

        # --- Head / face ---
        self._rect(s, 8, 6, 10, 6, outline)
        self._rect(s, 9, 6, 8, 6, face)
        self._rect(s, 9, 6, 8, 1, face_hi)  # brow lit
        self._hline(s, 9, 7, 8, shadow)  # brow shadow under hat
        # glowing sigil eyes
        self._dot(s, 11, 8, sigil_hi)
        self._dot(s, 15, 8, sigil_hi)
        self._dot(s, 11, 8, sigil)
        self._dot(s, 15, 8, sigil)
        # nose / mouth hint
        self._vline(s, 12, 9, 2, face_lo)
        # jaw shadow
        self._hline(s, 9, 11, 8, face_lo)

        # --- Torso (cloak chest) ---
        self._rect(s, 6, 12, 14, 11, outline)
        self._rect(s, 7, 12, 12, 11, cloak)
        self._rect(s, 8, 13, 10, 10, cloak_hi)  # lit chest
        self._vline(s, 12, 13, 10, cloak_lo)  # center seam
        self._vline(s, 7, 13, 10, cloak_lo)  # side shade
        self._vline(s, 18, 13, 10, cloak_lo)  # side shade
        # shoulder yoke + belt line
        self._hline(s, 7, 12, 12, trim_hi)
        self._hline(s, 7, 22, 12, trim)
        # clasp / sigil at the collar
        self._dot(s, 12, 13, sigil)
        self._dot(s, 11, 14, sigil_hi)
        self._dot(s, 13, 14, sigil_hi)

        # --- Arms: distinct sleeves beside the torso, with hands ---
        self._rect(s, 3, 13, 4, 9, outline)
        self._rect(s, 19, 13, 4, 9, outline)
        self._rect(s, 4, 13, 3, 9, cloak_lo)
        self._rect(s, 20, 13, 3, 9, cloak_lo)
        # cuffs
        self._rect(s, 3, 20, 4, 2, trim)
        self._rect(s, 19, 20, 4, 2, trim)
        # hands
        self._rect(s, 4, 22, 2, 2, face)
        self._rect(s, 20, 22, 2, 2, face_lo)

        # --- Hips / belt ---
        self._rect(s, 7, 23, 12, 2, outline)
        self._rect(s, 8, 23, 10, 2, leather)
        self._hline(s, 8, 23, 10, self._shade(leather, 28))
        self._dot(s, 12, 23, band_hi)  # buckle

        # --- Legs: two distinct legs with a gap between them ---
        self._rect(s, 8, 25, 4, 6, outline)
        self._rect(s, 14, 25, 4, 6, outline)
        self._rect(s, 9, 25, 3, 6, cloak_lo)
        self._rect(s, 15, 25, 3, 6, cloak_lo)
        # knee patches
        self._rect(s, 9, 27, 3, 1, trim)
        self._rect(s, 15, 27, 3, 1, trim)

        # --- Boots ---
        self._rect(s, 7, 31, 5, 2, outline)
        self._rect(s, 14, 31, 5, 2, outline)
        self._rect(s, 8, 31, 4, 2, leather)
        self._rect(s, 15, 31, 4, 2, self._shade(leather, -12))
        self._hline(s, 8, 32, 4, self._shade(leather, 24))
        self._hline(s, 15, 32, 4, self._shade(leather, 12))
        return s

    # ------------------------------------------------------------------
    # Gold-coin stack prop (shop floor scatter)
    # ------------------------------------------------------------------
    _GOLD_STACK_SEEDS: dict[int, int] = {1: 101, 2: 505, 3: 808}

    def _gold_stack(self, size: int) -> pygame.Surface:
        """Procedural gold-coin stack prop (size 1=small, 2=medium, 3=large).

        Coins are layered with a struck rim, lit rim ring, inset face with an
        upper highlight crescent and a central emblem so each disc reads as a
        distinct coin. A ground-contact shadow grounds the stack on the shop
        floor. Each size is seeded to reproduce the reviewed preview sprite
        exactly (see gold_stacks/gold_stack_0{1,5,8}_size{1,2,3}.png).
        """
        rim_lo = (74, 48, 10)
        rim = (108, 74, 18)
        rim_ring = (168, 120, 30)
        face = (224, 176, 52)
        face_lo = (170, 124, 36)
        face_hi = (252, 224, 124)
        shine = (255, 248, 206)
        emblem = (255, 240, 170)
        base_shadow = (28, 20, 14)

        rng = random.Random(self._GOLD_STACK_SEEDS.get(size, 101))

        if size == 1:
            stack_coins = rng.randint(2, 3)
            coin_w, coin_h = 7, 3
            canvas_w, canvas_h = 16, 14
            scatter = 0
        elif size == 2:
            stack_coins = rng.randint(3, 4)
            coin_w, coin_h = 9, 4
            canvas_w, canvas_h = 20, 16
            scatter = rng.choice([0, 1])
        else:  # size == 3
            stack_coins = rng.randint(5, 6)
            coin_w, coin_h = 11, 5
            canvas_w, canvas_h = 24, 22
            scatter = rng.choice([1, 2])

        s = self._surface(canvas_w, canvas_h)

        def coin(cx: int, cy: int, w: int, h: int) -> None:
            rect = pygame.Rect(cx - w // 2, cy - h // 2, w, h)
            pygame.draw.ellipse(s, rim_lo, rect.inflate(2, 2))
            pygame.draw.ellipse(s, rim, rect)
            pygame.draw.ellipse(s, rim_ring, rect.inflate(-1, -1))
            face_rect = rect.inflate(-3, -3)
            if face_rect.w <= 0 or face_rect.h <= 0:
                return
            pygame.draw.ellipse(s, face_lo, face_rect)
            hi_rect = pygame.Rect(
                face_rect.x, face_rect.y, face_rect.w, max(1, (face_rect.h + 1) // 2)
            )
            pygame.draw.ellipse(s, face, hi_rect)
            top_rect = pygame.Rect(
                face_rect.x + 1,
                face_rect.y,
                max(1, face_rect.w - 2),
                max(1, face_rect.h // 2),
            )
            pygame.draw.ellipse(s, face_hi, top_rect)
            if w >= 9 and face_rect.h >= 3:
                ex, ey = face_rect.centerx, face_rect.centery
                pygame.draw.rect(s, emblem, (ex, ey - 1, 1, 2))
                pygame.draw.rect(s, emblem, (ex - 1, ey, 1, 1))
                pygame.draw.rect(s, emblem, (ex + 1, ey, 1, 1))
            elif face_rect.w >= 3:
                pygame.draw.rect(
                    s, emblem, (face_rect.centerx, face_rect.centery, 1, 1)
                )

        def sparkle(x: int, y: int) -> None:
            pygame.draw.rect(s, shine, (x, y, 1, 1))
            pygame.draw.rect(s, shine, (x - 1, y, 1, 1))
            pygame.draw.rect(s, shine, (x + 1, y, 1, 1))
            pygame.draw.rect(s, shine, (x, y - 1, 1, 1))
            pygame.draw.rect(s, shine, (x, y + 1, 1, 1))

        base_cx = canvas_w // 2
        base_y = canvas_h - 3
        shadow_w = coin_w + 2 + scatter * 2
        pygame.draw.ellipse(
            s, base_shadow, pygame.Rect(base_cx - shadow_w // 2, base_y, shadow_w, 2)
        )

        # Stack coins bottom-up, spaced ~half a face height so the dark rim of
        # each lower coin shows as a crisp separator band.
        coin_thickness = max(1, round(coin_h * 0.5))
        top_cy = base_y - 1
        for i in range(stack_coins):
            cy = base_y - 1 - i * coin_thickness
            jitter = rng.randint(-1, 1) if size >= 2 else 0
            cx = base_cx + jitter
            coin(cx, cy, coin_w, coin_h)
            sep_w = coin_w - 2
            pygame.draw.rect(s, rim_lo, (cx - sep_w // 2, cy + coin_h // 2, sep_w, 1))
            if i < stack_coins - 1:
                pygame.draw.rect(
                    s, rim_ring, (cx - sep_w // 2, cy - coin_h // 2, sep_w, 1)
                )
            top_cy = cy

        # Top coin gets a brighter face + sparkle to read as the stack top.
        coin(base_cx, top_cy, coin_w, coin_h)
        sparkle(base_cx - coin_w // 4, top_cy - coin_h // 2 - 1)

        # Larger tiers scatter a few fallen coins for silhouette variety.
        for _ in range(scatter):
            side = rng.choice([-1, 1])
            fx = base_cx + side * (coin_w // 2 + rng.randint(1, 2))
            fy = base_y - rng.randint(0, 1)
            coin(fx, fy, coin_w - 2, max(2, coin_h - 1))
            sparkle(fx - 1, fy - 1)

        return s

    def gold_stack_sprite(self, size: int) -> pygame.Surface:
        return self.gold_stack_sprites.get(size, self.gold_stack_sprites[1])

    # ------------------------------------------------------------------
    # Milestone 3.15 — familiar (summoned spirit ally) sprite states.
    # Two states: a small wisp (pre-skill) and a big owl (post Spirit Call).
    # ------------------------------------------------------------------
    def _familiar_wisp(self) -> pygame.Surface:
        s = self._surface(14, 18)
        teal = (130, 230, 220)
        teal_hi = (200, 250, 245)
        teal_lo = (70, 165, 165)
        glow = (120, 245, 255)
        dark = (24, 48, 54)
        # roundish ghostly head
        self._rect(s, 3, 2, 8, 8, teal)
        self._rect(s, 4, 1, 6, 10, teal)
        self._rect(s, 2, 3, 10, 5, teal_hi)  # lit band
        # tapering wispy tail
        self._rect(s, 4, 10, 6, 3, teal_lo)
        self._rect(s, 5, 13, 4, 2, teal_lo)
        self._rect(s, 6, 15, 2, 2, teal_lo)
        # glowing eyes
        self._rect(s, 5, 5, 1, 2, dark)
        self._rect(s, 8, 5, 1, 2, dark)
        self._dot(s, 5, 5, glow)
        self._dot(s, 8, 5, glow)
        # tiny halo mote
        self._dot(s, 7, 0, glow)
        return s

    def _familiar_owl(self) -> pygame.Surface:
        # Big owl spirit (the post-Spirit-Call familiar state). A round
        # feathered body, two big eye discs, ear tufts, a small gold beak, and
        # the spirit-glow eyes that mark every Acolyte summon.
        s = self._surface(26, 34)
        bone = (224, 218, 196)
        bone_hi = (245, 240, 220)
        bone_lo = (170, 162, 138)
        feather = (150, 142, 116)  # darker feather tone for body shading
        gold = (235, 200, 110)
        gold_hi = (255, 225, 150)
        glow = (190, 250, 255)
        glow_deep = (90, 210, 235)
        dark = (26, 28, 32)
        # ear tufts
        pygame.draw.polygon(s, bone_lo, [(6, 6), (10, 6), (8, 0)])
        pygame.draw.polygon(s, bone_lo, [(16, 6), (20, 6), (18, 0)])
        # body (oval)
        pygame.draw.ellipse(s, bone_lo, (3, 5, 20, 27))
        # lit breast
        pygame.draw.ellipse(s, bone, (7, 13, 12, 17))
        # feather shading bands across the breast
        self._hline(s, 7, 21, 12, feather)
        self._hline(s, 7, 25, 12, feather)
        # big eye discs (lighter than the body so they read as owl eyes)
        pygame.draw.circle(s, bone, (10, 14), 4)
        pygame.draw.circle(s, bone, (16, 14), 4)
        # glowing spirit eyes
        pygame.draw.circle(s, dark, (10, 14), 3)
        pygame.draw.circle(s, dark, (16, 14), 3)
        pygame.draw.circle(s, glow_deep, (10, 14), 2)
        pygame.draw.circle(s, glow_deep, (16, 14), 2)
        self._dot(s, 10, 14, glow)
        self._dot(s, 16, 14, glow)
        # beak
        pygame.draw.polygon(s, gold, [(12, 17), (14, 17), (13, 20)])
        self._dot(s, 13, 19, gold_hi)
        # feet
        self._rect(s, 9, 31, 3, 2, gold)
        self._rect(s, 14, 31, 3, 2, gold)
        return s
