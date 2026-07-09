# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
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

"""Milestone 3.16 — continuous multi-source colored lighting.

This module owns the lighting model that replaces the per-tile alpha falloff
(``run_flow.tile_visibility_alpha`` + ``rendering.world._alpha_tile_surface``)
with a continuous, multi-source, colored light buffer:

* :func:`bake_normal_map` derives a tangent-space normal map from any
  ``SRCALPHA`` sprite/tile surface by combining the alpha silhouette with the
  pixel luminance into a height map and running a 3x3 Sobel. It mirrors the
  SpriteIlluminator/Laigter "height from intensity" approach in code, with no
  external asset pipeline. It is deterministic (a pure function of the source
  pixels) so it can be unit-tested directly, and it applies to every sprite and
  tile surface because it only reads pixels.

* :class:`LightingMixin` is composed into :class:`arch_rogue.rendering.RenderingMixin`
  and supplies ``draw_lighting``, the per-frame entry point called between
  ``draw_world_objects`` and ``draw_ambient_depth_overlay``. Each frame it
  clears a reused half-resolution ``SRCALPHA`` buffer, stamps the theme-tinted
  ambient wash, blits cached radial light sprites with ``BLEND_RGBA_ADD`` for
  the player lantern / static torches & shrines / transient skill, projectile
  and impact pulses, then smoothscales the buffer up and composites it onto the
  screen with ``BLEND_RGBA_MULT``. No surface is allocated in the hot path: the
  buffer and the full-res scratch are reused, the radial sprites are cached, and
  the lit-actor tint results are cached per (sprite, dominant-light bucket).

The fog-of-war memory (``revealed_tiles``) and the sight/lantern reach
(``can_see_world_position`` / ``has_line_of_sight``) are untouched: the tile
draw pass still culls never-revealed / beyond-lantern tiles for terrain reveal,
it simply no longer quantizes their alpha. When the ``Lighting`` option is Off
the whole mixin short-circuits and the 3.8.0 per-tile alpha path is used
verbatim, preserving the previous look as a fallback (and as the web default).
"""

from __future__ import annotations

# pyright: reportAttributeAccessIssue=false
import math

import pygame

from .constants import (
    DARK_LEVEL_LIGHT_RADIUS,
    LIGHT_AMBIENT_DARK_LEVEL,
    LIGHT_AMBIENT_LIGHT_LEVEL,
    LIGHT_AMBIENT_TINT_RATIO,
    LIGHT_BUFFER_SCALE,
    LIGHT_DIRECTION_BUCKETS,
    LIGHT_FLICKER_INTENSITY_AMP,
    LIGHT_FLICKER_RADIUS_AMP,
    LIGHT_LANTERN_COLOR,
    LIGHT_LEVEL_SIGHT_RADIUS,
    LIGHT_SHADE_BIAS_Z,
    LIGHT_SHADE_DOWNSAMPLE_LONG,
    TILE_W,
)
from .models import Color, LightSource


# ------------------------------------------------------------------
# Normal-map baking (feature 1)
# ------------------------------------------------------------------
def bake_normal_map(surface: pygame.Surface) -> pygame.Surface:
    """Derive a tangent-space normal map from an ``SRCALPHA`` surface.

    Height is a combination of the alpha silhouette (gross shape) and the pixel
    luminance (surface detail) — the order pixels are stamped into a sprite
    already encodes depth (later stamps overwrite earlier ones), and the final
    color's luminance carries that layering, so this reproduces the
    SpriteIlluminator/Laigter "height from intensity" mode without instrumenting
    every sprite builder. A 3x3 Sobel over the height field yields tangent-space
    gradients; the result is packed into RGB (``x=(r-128)/128``,
    ``y=(g-128)/128``, ``z=b/255``) with the source alpha preserved as the
    normal map's alpha so empty pixels stay empty.

    Purely a function of the source pixels, so it is deterministic and safe to
    call on any sprite or tile surface.
    """
    w, h = surface.get_width(), surface.get_height()
    if w <= 0 or h <= 0:
        return pygame.Surface((max(1, w), max(1, h)), pygame.SRCALPHA)

    # Sample alpha + luminance. ``array_alpha``/``array3d`` would be faster but
    # pull in numpy, which is not a project dependency, so use the surface's
    # locked pixel access. This only runs at atlas-build time / lazily on first
    # request (never per frame), so the cost is paid once per unique surface.
    try:
        surface.lock()
        heights = [0.0] * (w * h)
        has_alpha = surface.get_flags() & pygame.SRCALPHA
        for y in range(h):
            for x in range(w):
                c = surface.get_at((x, y))
                a = c.a if has_alpha else 255
                if a <= 0:
                    heights[y * w + x] = 0.0
                    continue
                # Silhouette contributes the gross height; luminance adds
                # readable surface relief on top.
                lum = (0.299 * c.r + 0.587 * c.g + 0.114 * c.b) / 255.0
                height = 0.62 * (a / 255.0) + 0.38 * lum
                heights[y * w + x] = height
    finally:
        if surface.get_locked():
            surface.unlock()

    normal = pygame.Surface((w, h), pygame.SRCALPHA)
    strength = 2.2  # emboss gain; tuned for readable relief on pixel art
    for y in range(h):
        for x in range(w):
            a = surface.get_at((x, y)).a if has_alpha else 255
            if a <= 0:
                continue
            # 3x3 Sobel on the height field with edge clamp.
            hl = heights[y * w + max(0, x - 1)]
            hr = heights[y * w + min(w - 1, x + 1)]
            hd = heights[max(0, y - 1) * w + x]
            hu = heights[min(h - 1, y + 1) * w + x]
            gx = (hr - hl) * strength
            gy = (hu - hd) * strength
            nx = -gx
            ny = -gy
            nz = 1.0
            inv = 1.0 / math.sqrt(nx * nx + ny * ny + nz * nz)
            nx *= inv
            ny *= inv
            nz *= inv
            r = int(max(0.0, min(1.0, nx * 0.5 + 0.5)) * 255)
            g = int(max(0.0, min(1.0, ny * 0.5 + 0.5)) * 255)
            b = int(max(0.0, min(1.0, nz)) * 255)
            normal.set_at((x, y), (r, g, b, a))
    return normal


def shade_color(base: Color, level: float) -> Color:
    """Scale a color by a 0..1 brightness (used for ambient levels)."""
    level = max(0.0, min(1.0, level))
    return (
        int(base[0] * level),
        int(base[1] * level),
        int(base[2] * level),
    )


def mix_color(a: Color, b: Color, ratio: float) -> Color:
    ratio = max(0.0, min(1.0, ratio))
    return (
        int(a[0] * (1.0 - ratio) + b[0] * ratio),
        int(a[1] * (1.0 - ratio) + b[1] * ratio),
        int(a[2] * (1.0 - ratio) + b[2] * ratio),
    )


def light_radius_px(world_radius: float) -> int:
    """Convert a world-tile light radius to a screen-space sprite radius.

    A world-space circle projects to a screen ellipse under the iso transform;
    a screen circle of this radius reads as the same reach in the dominant
    directions while staying cheap (one cached sprite per radius/color).
    """
    return max(4, int(world_radius * TILE_W * 0.46))


def quantize_direction(dx: float, dy: float) -> int:
    """Bucket a 2D light direction into ``LIGHT_DIRECTION_BUCKETS`` sectors.

    Returns 0 when there is no meaningful direction (actor on top of the light)
    so the lit-actor tint cache can treat that as a stable neutral bucket.
    """
    length = math.hypot(dx, dy)
    if length < 1e-3:
        return 0
    angle = math.atan2(dy, dx)
    bucket = int((angle + math.pi) / math.tau * LIGHT_DIRECTION_BUCKETS) % LIGHT_DIRECTION_BUCKETS
    return bucket


class LightingMixin:
    """Continuous colored lighting, composed into ``RenderingMixin``.

    All state is lazily initialised on first use so the mixin is safe to mix
    into ``Game`` even when lighting is disabled (the web/Off path never pays
    for the buffers).
    """

    # --- option accessors -------------------------------------------
    def lighting_enabled(self) -> bool:
        return bool(getattr(self, "_lighting_enabled", True))

    def lighting_normal_maps_active(self) -> bool:
        return bool(getattr(self, "_lighting_normal_maps", True)) and self.lighting_enabled()

    def flicker_enabled(self) -> bool:
        # Reduced Motion (accessibility) suppresses the lantern/torch flicker.
        return self.lighting_enabled() and not bool(
            getattr(self, "_reduced_motion", False)
        )

    # --- transient light emission (called from combat / add_impact) --
    def add_light(
        self,
        x: float,
        y: float,
        radius: float,
        color: Color,
        intensity: float = 1.0,
        ttl: float = 0.25,
        flicker: bool = False,
        kind: str = "",
    ) -> LightSource:
        light = LightSource(
            x=x,
            y=y,
            radius=radius,
            color=color,
            intensity=intensity,
            ttl=ttl,
            max_ttl=ttl,
            flicker=flicker,
            flicker_seed=int(abs(hash((round(x, 2), round(y, 2), kind))) % 9973),
            kind=kind,
        )
        self.lights.append(light)
        return light

    def update_lights(self, dt: float) -> None:
        # Decay transient lights and compact the list each frame. Static lights
        # (ttl None) are owned by ``self.light_sources`` and never decay here.
        lights = getattr(self, "lights", None)
        if not lights:
            return
        for light in lights:
            light.update(dt)
        self.lights = [light for light in lights if light.alive]

    # --- per-frame collection ---------------------------------------
    def _theme_light_color(self) -> Color:
        theme = self.theme
        return mix_color((255, 255, 255), theme.accent, LIGHT_AMBIENT_TINT_RATIO)

    def _ambient_level(self) -> float:
        return (
            LIGHT_AMBIENT_DARK_LEVEL
            if self.is_current_floor_dark()
            else LIGHT_AMBIENT_LIGHT_LEVEL
        )

    def _lantern_radius(self) -> float:
        # Identical reach on both floor types: dark floors use the lantern
        # radius, light floors use the (equal) sight radius, with the lantern
        # adding local warmth over the ambient wash.
        return (
            DARK_LEVEL_LIGHT_RADIUS
            if self.is_current_floor_dark()
            else LIGHT_LEVEL_SIGHT_RADIUS
        )

    def _flicker(self, light: LightSource) -> tuple[float, float]:
        """Return (radius_scale, intensity_scale) flicker for a light this frame."""
        if not light.flicker or not self.flicker_enabled():
            return 1.0, 1.0
        # Low-amplitude noise on radius/intensity for a lantern feel. Two
        # incoherent sines keep it from looking like a uniform pulse.
        t = self.elapsed + light.flicker_seed * 0.37
        # Slow pulsate (~0.5 Hz) so the lantern breathes rather than
        # flickers; two incoherent sines keep it from looking uniform.
        rad = 1.0 + LIGHT_FLICKER_RADIUS_AMP * math.sin(t * 3.0)
        inten = 1.0 + LIGHT_FLICKER_INTENSITY_AMP * math.sin(t * 2.2 + 1.7)
        return rad, inten

    def _collect_frame_lights(self) -> list[LightSource]:
        # Player lantern + static lights within the visible bounds + transient
        # pulses. Cached per frame so the lit-actor pass and the buffer pass
        # share one collection.
        cache = getattr(self, "_frame_cache", None)
        if cache is None:
            cache = {}
            self._frame_cache = cache
        cached = cache.get("frame_lights")
        if cached is not None:
            return cached  # type: ignore[return-value]

        lights: list[LightSource] = []
        # Player lantern: always present, warm, at the sight/lantern radius.
        lights.append(
            LightSource(
                x=self.player.x,
                y=self.player.y,
                radius=self._lantern_radius(),
                color=LIGHT_LANTERN_COLOR,
                intensity=1.0,
                ttl=None,
                flicker=True,
                kind="lantern",
            )
        )
        min_x, max_x, min_y, max_y = self.visible_bounds()
        for src in getattr(self, "light_sources", []):
            if not (min_x - 4 <= src.x <= max_x + 4 and min_y - 4 <= src.y <= max_y + 4):
                continue
            lights.append(src)
        lights.extend(getattr(self, "lights", []))
        cache["frame_lights"] = lights
        return lights

    # --- cached surfaces --------------------------------------------
    def _light_buffer(self, w: int, h: int) -> pygame.Surface:
        buf = getattr(self, "_light_buffer_surface", None)
        if buf is None or buf.get_width() != w or buf.get_height() != h:
            buf = pygame.Surface((w, h), pygame.SRCALPHA)
            self._light_buffer_surface = buf
            # The full-res scratch must match the screen, not the buffer; force
            # a rebuild on next composite.
            self._light_scratch_surface = None
        return buf

    def _light_scratch(self, w: int, h: int) -> pygame.Surface:
        scratch = getattr(self, "_light_scratch_surface", None)
        if scratch is None or scratch.get_width() != w or scratch.get_height() != h:
            scratch = pygame.Surface((w, h), pygame.SRCALPHA)
            self._light_scratch_surface = scratch
        return scratch

    def _radial_light_sprite(
        self, radius_px: int, color: Color, intensity: float
    ) -> pygame.Surface:
        # Quantize the radius to 16px buckets so the lantern/torch flicker
        # (a small per-frame radius change) does not bust the cache and trigger
        # a full radial-sprite rebuild every frame. Intensity is quantized too.
        radius_px = max(4, (int(radius_px) // 16) * 16)
        intensity_bucket = max(0, min(20, int(intensity * 20)))
        key = (radius_px, color, intensity_bucket)
        cache = getattr(self, "_light_sprite_cache", None)
        if cache is None:
            cache = {}
            self._light_sprite_cache = cache
        cached = cache.get(key)
        if cached is not None:
            return cached
        size = radius_px * 2 + 2
        sprite = pygame.Surface((size, size), pygame.SRCALPHA)
        cx = cy = size // 2
        peak = (
            max(0, min(255, int(color[0] * intensity))),
            max(0, min(255, int(color[1] * intensity))),
            max(0, min(255, int(color[2] * intensity))),
        )
        # Build the gradient with a bounded number of bands (not one per pixel)
        # so a cache miss rebuilds in well under a millisecond. Bands go from
        # outer (dim, quadratic falloff) to inner (peak); opaque overwrites put
        # the bright center on top. The outer band is near-black, which adds
        # nothing under BLEND_RGBA_ADD but keeps the disc opaque for the alpha.
        bands = min(radius_px, 48)
        for i in range(bands, 0, -1):
            r = max(1, int(radius_px * i / bands))
            falloff = 1.0 - (r / radius_px)
            falloff = falloff * falloff
            c = (
                int(peak[0] * falloff),
                int(peak[1] * falloff),
                int(peak[2] * falloff),
                255,
            )
            pygame.draw.circle(sprite, c, (cx, cy), r)
        try:
            sprite = sprite.convert_alpha()
        except pygame.error:
            pass
        cache[key] = sprite
        return sprite

    # --- ambient stamping -------------------------------------------
    def _stamp_ambient(self, buffer: pygame.Surface) -> None:
        theme_color = self._theme_light_color()
        level = self._ambient_level()
        if self.is_current_floor_dark():
            # Dark floor: a flat near-black themed wash across the whole buffer.
            buffer.fill((*shade_color(theme_color, level), 255))
            return
        # Light floor: the ambient wash fills only revealed tiles (fog-of-war
        # memory) so never-explored areas stay black. Stamped as half-res rects
        # over the visible bounds — rect fills, no surface allocations.
        buffer.fill((0, 0, 0, 0))
        ambient = (*shade_color(theme_color, level), 255)
        scale = LIGHT_BUFFER_SCALE
        min_x, max_x, min_y, max_y = self.visible_bounds()
        revealed = self.revealed_tiles
        tile_w_px = max(1, TILE_W // scale)
        for x in range(min_x, max_x + 1):
            for y in range(min_y, max_y + 1):
                if (x, y) not in revealed:
                    continue
                sx, sy = self.world_to_screen(x + 0.5, y + 0.5)
                rx = sx // scale - tile_w_px // 2
                ry = sy // scale - tile_w_px // 2
                buffer.fill(ambient, pygame.Rect(rx, ry, tile_w_px, tile_w_px))

    # --- the per-frame compositing entry point ----------------------
    def draw_lighting(self) -> None:
        if not self.lighting_enabled():
            return
        if self.state not in ("playing", "dead", "victory"):
            return
        screen_w, screen_h = self._screen_size()
        if screen_w <= 0 or screen_h <= 0:
            return
        buf_w = max(1, screen_w // LIGHT_BUFFER_SCALE)
        buf_h = max(1, screen_h // LIGHT_BUFFER_SCALE)
        buffer = self._light_buffer(buf_w, buf_h)

        # 1) Ambient base (theme-tinted; revealed-tile memory on light floors).
        self._stamp_ambient(buffer)

        # 2) Accumulate every active light additively into the buffer.
        scale = LIGHT_BUFFER_SCALE
        lights = self._collect_frame_lights()
        for light in lights:
            rad_scale, int_scale = self._flicker(light)
            life = light.life
            intensity = max(0.0, light.intensity * int_scale * life)
            if intensity <= 0.0:
                continue
            radius_px = light_radius_px(light.radius * rad_scale)
            sprite = self._radial_light_sprite(radius_px, light.color, intensity)
            sx, sy = self.world_to_screen(light.x, light.y)
            bx = sx // scale - sprite.get_width() // 2
            by = sy // scale - sprite.get_height() // 2
            buffer.blit(sprite, (bx, by), special_flags=pygame.BLEND_RGBA_ADD)

        # 3) Smoothscale the half-res buffer up to the screen and multiply.
        scratch = self._light_scratch(screen_w, screen_h)
        pygame.transform.smoothscale(buffer, (screen_w, screen_h), scratch)
        self.screen.blit(scratch, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

    # --- lit-actor shading (feature 6) ------------------------------
    def apply_lit_shading(
        self, sprite: pygame.Surface, world_x: float, world_y: float
    ) -> pygame.Surface:
        """Return ``sprite`` tinted by a Lambertian term from the dominant light.

        Computed on a downscaled copy of the sprite + its baked normal map so
        the per-pixel cost stays bounded (~``LIGHT_SHADE_DOWNSAMPLE_LONG``^2
        pixels), and cached per (sprite, dominant-light bucket) in a persistent
        cache that is cleared on floor change. Skipped entirely on the LIGHTING
       _OFF tier and when normal maps are disabled.
        """
        if not self.lighting_normal_maps_active():
            return sprite
        dominant = self._dominant_light(world_x, world_y)
        if dominant is None:
            return sprite
        light_dx = world_x - dominant.x
        light_dy = world_y - dominant.y
        bucket = quantize_direction(light_dx, light_dy)
        dist = math.hypot(light_dx, light_dy)
        # Distance bucket: how far the actor is through the light's reach.
        reach = max(0.5, dominant.radius)
        dist_bucket = min(3, int(dist / reach * 4))
        key = (id(sprite), bucket, dist_bucket)
        cache = getattr(self, "_lit_shade_cache", None)
        if cache is None:
            cache = {}
            self._lit_shade_cache = cache
        cached = cache.get(key)
        if cached is not None:
            return cached

        normal = self.sprites.normal_map_for(sprite)
        if normal is None:
            cache[key] = sprite
            return sprite

        shaded = self._compute_lit_shade(sprite, normal, light_dx, light_dy, dominant, dist)
        cache[key] = shaded
        return shaded

    def _dominant_light(self, x: float, y: float) -> LightSource | None:
        lights = self._collect_frame_lights()
        best: LightSource | None = None
        best_score = -1.0
        for light in lights:
            d = math.hypot(x - light.x, y - light.y)
            if d > light.radius:
                continue
            # Closer + brighter + more intense wins.
            score = light.intensity * light.life * (1.0 - d / max(light.radius, 0.5))
            if score > best_score:
                best_score = score
                best = light
        return best

    def _compute_lit_shade(
        self,
        sprite: pygame.Surface,
        normal: pygame.Surface,
        light_dx: float,
        light_dy: float,
        light: LightSource,
        dist: float,
    ) -> pygame.Surface:
        w, h = sprite.get_width(), sprite.get_height()
        if w <= 0 or h <= 0:
            return sprite
        # The sprite is NEVER scaled: we build a low-res TINT map from the
        # baked normal map, smoothscale only the tint up to full size, and
        # multiply it onto a full-res copy of the sprite. The sprite stays
        # pixel-crisp; only the shading is a soft directional gradient. Per-pixel
        # work is bounded to the downsample size, so this is cheap in pure
        # Python and only runs on a cache miss (player + bosses only).
        long_side = max(w, h)
        if long_side > LIGHT_SHADE_DOWNSAMPLE_LONG:
            f = LIGHT_SHADE_DOWNSAMPLE_LONG / long_side
            sw = max(1, int(w * f))
            sh = max(1, int(h * f))
            small_normal = pygame.transform.scale(normal, (sw, sh))
        else:
            sw, sh = w, h
            small_normal = normal

        slx, sly = self.world_to_screen(light.x, light.y)
        sax, say = self.world_to_screen(light.x + light_dx, light.y + light_dy)
        ddx = sax - slx
        ddy = say - sly
        dlen = math.hypot(ddx, ddy)
        if dlen > 1e-3:
            ldx = ddx / dlen
            ldy = ddy / dlen
        else:
            ldx = ldy = 0.0
        ldz = LIGHT_SHADE_BIAS_Z
        light_color = light.color
        reach = max(0.5, light.radius)
        atten = max(0.0, 1.0 - dist / reach)
        intensity = light.intensity

        # TINT map: per-pixel multiplier for BLEND_RGB_MULT. 255 = no change
        # (lit-facing side stays full bright, with a slight light-color tint);
        # lower values darken the shadow side. RGB-only blend keeps the sprite's
        # own alpha/silhouette exactly intact.
        tint = pygame.Surface((sw, sh), pygame.SRCALPHA)
        tint.fill((255, 255, 255, 255))
        try:
            small_normal.lock()
            tint.lock()
            for py in range(sh):
                for px in range(sw):
                    nc = small_normal.get_at((px, py))
                    if nc.a <= 0:
                        continue
                    nx = (nc.r / 255.0) * 2.0 - 1.0
                    ny = (nc.g / 255.0) * 2.0 - 1.0
                    nz = nc.b / 255.0
                    lambert = nx * ldx + ny * ldy + nz * ldz
                    if lambert < 0.0:
                        lambert = 0.0
                    elif lambert > 1.0:
                        lambert = 1.0
                    shade = (0.32 + 0.68 * lambert) * (0.45 + 0.55 * atten) * intensity
                    shade = max(0.0, min(1.25, shade))
                    tr = max(0, min(255, int(light_color[0] * shade)))
                    tg = max(0, min(255, int(light_color[1] * shade)))
                    tb = max(0, min(255, int(light_color[2] * shade)))
                    tint.set_at((px, py), (tr, tg, tb, 255))
        finally:
            if small_normal.get_locked():
                small_normal.unlock()
            if tint.get_locked():
                tint.unlock()

        tint_full = pygame.transform.smoothscale(tint, (w, h))
        result = sprite.copy()
        result.blit(tint_full, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
        try:
            result = result.convert_alpha()
        except pygame.error:
            pass
        return result

    def reset_lighting_caches(self) -> None:
        # Called on floor/theme change alongside ``tile_cache.clear``; bounds
        # the lit-actor tint cache and invalidates any sized buffers.
        self._lit_shade_cache = {}
        self._light_sprite_cache = {}
        self._light_buffer_surface = None
        self._light_scratch_surface = None
        cache = getattr(self, "_frame_cache", None)
        if isinstance(cache, dict):
            cache.pop("frame_lights", None)