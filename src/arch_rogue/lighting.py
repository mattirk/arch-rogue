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
from typing import Callable

import pygame

from .constants import (
    DARK_LEVEL_LIGHT_RADIUS,
    DUNGEON_DEPTH,
    LIGHT_AMBIENT_DARK_LEVEL,
    LIGHT_AMBIENT_DEPTH_FLOOR,
    LIGHT_AMBIENT_DEPTH_PEAK,
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
    """Convert a world-tile light radius to a half-res sprite radius.

    The light buffer is half-resolution, so light sprites are sized in
    half-res pixels to match (a full-res sprite would be clipped to the
    buffer and waste fill/blit work). A world-space circle projects to a
    screen ellipse under the iso transform; a screen circle of this radius
    reads as the same reach in the dominant directions.
    """
    return max(4, int(world_radius * TILE_W * 0.46 / LIGHT_BUFFER_SCALE))


def hashable_color(color: Color) -> Color:
    """Normalize a color to a hashable 3-int tuple.

    Light colors flow in from several sources (save JSON, combat, themes). JSON
    round-trips tuples to lists and ``pygame.Color`` is itself unhashable, so any
    of those used directly as a dict cache key raises ``TypeError: unhashable
    type``. Normalizing here keeps the lighting caches robust regardless of how
    a color arrived, without changing the rendered values.
    """
    if type(color) is tuple:
        return color
    return (int(color[0]), int(color[1]), int(color[2]))


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
        # Lantern/torch flicker is always on when the lighting model is on.
        return self.lighting_enabled()

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

    def _ambient_depth_factor(self) -> float:
        # Light-floor ambient brightness vs depth: 1.6x at the surface (depth 1)
        # fading to 0.5x at the deepest floor, so the dungeon gets gradually
        # darker as you descend. A separate axis from the dark-floor flag
        # (lantern-only visibility / no fog-of-war memory), which is untouched.
        depth = max(1, self.current_depth)
        span = max(1, DUNGEON_DEPTH - 1)
        t = (depth - 1) / span
        return LIGHT_AMBIENT_DEPTH_PEAK - t * (
            LIGHT_AMBIENT_DEPTH_PEAK - LIGHT_AMBIENT_DEPTH_FLOOR
        )

    def _ambient_level(self) -> float:
        if self.is_current_floor_dark():
            # Dark floors keep a constant near-black ambient regardless of depth;
            # the lantern drives visibility. The dark-floor logic is intact.
            return LIGHT_AMBIENT_DARK_LEVEL
        # Light floor (fog-of-war memory): brighter near the surface, darker
        # deeper. The memory/reveal behavior and sight radius are unchanged.
        return LIGHT_AMBIENT_LIGHT_LEVEL * self._ambient_depth_factor()

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
        """Return (radius_scale, intensity_scale) flicker for a light this frame.

        The radius is constant (1.0) so the light sprite is built once and
        never snaps between size buckets; only the brightness modulates,
        applied as a continuous multiply in the compositing loop (no
        quantized stepping). A single slow sine keeps the lantern breathing
        smoothly rather than flickering.
        """
        if not light.flicker or not self.flicker_enabled():
            return 1.0, 1.0
        t = self.elapsed + light.flicker_seed * 0.37
        # ~0.25 Hz; centered just under 1.0 so the pulse dims and recovers
        # smoothly without clamping at full brightness.
        rad = 1.0
        inten = 0.92 + LIGHT_FLICKER_INTENSITY_AMP * math.sin(t * 1.6)
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
        self, radius_px: int, color: Color
    ) -> pygame.Surface:
        # One smooth radial gradient per (quantized radius, color), cached.
        # Always full intensity; brightness is modulated continuously in the
        # compositing loop (copy -> multiply -> add), so the sprite never
        # rebuilds for flicker or fade and the brightness never steps.
        radius_px = max(4, (int(radius_px) // 8) * 8)
        color = hashable_color(color)
        key = (radius_px, color)
        cache = getattr(self, "_light_sprite_cache", None)
        if cache is None:
            cache = {}
            self._light_sprite_cache = cache
        cached = cache.get(key)
        if cached is not None:
            return cached
        sprite_size = radius_px * 2 + 2
        # Build the gradient at a bounded resolution: one filled circle per
        # pixel-radius (1px bands -> no visible banding at this resolution),
        # then bilinear-smoothscale up to the sprite size. The upscale
        # interpolates the bands into a continuous gradient, so there are no
        # visible rings/ellipses. Build cost is bounded and paid once.
        build_size = min(sprite_size, 160)
        build_r = build_size // 2
        grad = pygame.Surface((build_size, build_size), pygame.SRCALPHA)
        cx = cy = build_size // 2
        peak = (
            max(0, min(255, int(color[0]))),
            max(0, min(255, int(color[1]))),
            max(0, min(255, int(color[2]))),
        )
        for r in range(build_r, 0, -1):
            falloff = 1.0 - (r / max(1, build_r))
            falloff = falloff * falloff
            c = (
                int(peak[0] * falloff),
                int(peak[1] * falloff),
                int(peak[2] * falloff),
                int(255 * falloff),
            )
            pygame.draw.circle(grad, c, (cx, cy), r)
        if build_size < sprite_size:
            sprite = pygame.transform.smoothscale(grad, (sprite_size, sprite_size))
        else:
            sprite = grad
        try:
            sprite = sprite.convert_alpha()
        except pygame.error:
            pass
        cache[key] = sprite
        return sprite

    def _flicker_scratch(self, w: int, h: int) -> pygame.Surface:
        # One reusable scratch per sprite size for the smooth flicker path
        # (copy -> multiply -> add). Sizes are stable per light, so this
        # stays tiny (one per flickering light size).
        cache = getattr(self, "_flicker_scratch_cache", None)
        if cache is None:
            cache = {}
            self._flicker_scratch_cache = cache
        s = cache.get((w, h))
        if s is None:
            s = pygame.Surface((w, h), pygame.SRCALPHA)
            try:
                s = s.convert_alpha()
            except pygame.error:
                pass
            cache[(w, h)] = s
        return s

    # --- ambient stamping -------------------------------------------
    def _shade_params(self) -> tuple[float, Callable[[float, float], tuple[int, int]]]:
        # Lighting is applied to the smaller of the world layer / display (see
        # RenderingBaseMixin._render_world_view). When shading the display
        # post-composite (zoomed out / native) positions use the zoom-aware
        # ``world_to_display`` and sprite sizes scale by ``view_zoom``; when
        # shading the layer pre-composite (zoomed in) positions use the
        # zoom-unaware ``world_to_screen`` at native world scale, exactly like
        # the original path. Returns (effective_zoom, projection_callable).
        if getattr(self, "_shade_post_composite", True):
            return getattr(self, "view_zoom", 1.0), self.world_to_display
        return 1.0, self.world_to_screen

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
        # A tile's buffer footprint depends on which surface we shade: display
        # pixels shrink with zoom (post-composite) while layer pixels stay at
        # native world scale (pre-composite). Scale the stamp rect by the
        # effective zoom to keep the fog-of-war fill aligned with the tiles.
        eff_zoom, project = self._shade_params()
        tile_w_px = max(1, int(TILE_W * eff_zoom) // scale)
        min_x, max_x, min_y, max_y = self.visible_bounds()
        revealed = self.revealed_tiles
        for x in range(min_x, max_x + 1):
            for y in range(min_y, max_y + 1):
                if (x, y) not in revealed:
                    continue
                sx, sy = project(x + 0.5, y + 0.5)
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
        # Every light shares one smooth cached sprite per (radius, color)
        # and modulates brightness with a continuous copy->multiply->add
        # pass: no per-intensity rebuilds, no radius stepping, smooth fades
        # and flicker. The extra copy/multiply is cheap (half-res sprites) and
        # only the on-screen lights run.
        #
        # Sprite size tracks the shaded surface: display pixels (post-composite,
        # zoomed out) scale by view_zoom so a light covers the same world area
        # at any zoom; layer pixels (pre-composite, zoomed in) stay at native
        # world scale. The radial sprite cache quantizes to 8px buckets, so the
        # few extra entries per zoom level are bounded and cleared on floor
        # change. At zoom 1.0 this is the original sprite size.
        scale = LIGHT_BUFFER_SCALE
        eff_zoom, project = self._shade_params()
        lights = self._collect_frame_lights()
        for light in lights:
            factor = light.intensity * light.life
            if factor <= 0.0:
                continue
            if light.flicker and self.flicker_enabled():
                _, int_scale = self._flicker(light)
                factor *= int_scale
            factor = max(0.0, min(1.0, factor))
            if factor <= 0.0:
                continue
            sprite = self._radial_light_sprite(
                int(light_radius_px(light.radius) * eff_zoom), light.color
            )
            scratch = self._flicker_scratch(
                sprite.get_width(), sprite.get_height()
            )
            scratch.blit(sprite, (0, 0))
            f = max(0, min(255, int(255 * factor)))
            scratch.fill((f, f, f, 255), special_flags=pygame.BLEND_RGBA_MULT)
            sx, sy = project(light.x, light.y)
            bx = sx // scale - sprite.get_width() // 2
            by = sy // scale - sprite.get_height() // 2
            buffer.blit(scratch, (bx, by), special_flags=pygame.BLEND_RGBA_ADD)

        # 3) Smoothscale the half-res buffer up to the screen and multiply.
        scratch = self._light_scratch(screen_w, screen_h)
        pygame.transform.smoothscale(buffer, (screen_w, screen_h), scratch)
        self.screen.blit(scratch, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

    # --- lit-actor shading (feature 6) ------------------------------
    def apply_lit_shading(
        self,
        sprite: pygame.Surface,
        base_sprite: pygame.Surface,
        world_x: float,
        world_y: float,
    ) -> pygame.Surface:
        """Return ``sprite`` tinted by a Lambertian term from the dominant light.

        The tint is computed ONCE per (base sprite, light-direction bucket,
        distance bucket, light color, frame size) from the BASE sprite's stable
        baked normal map and cached, then applied (a copy + a single
        ``BLEND_RGB_MULT`` blit) to whichever animation frame is showing. Because
        the tint comes from the base sprite (not each animation frame's own
        normal map), the shading is identical across animation frames and the
        actor no longer flickers as its pose animates. Skipped on the
        LIGHTING_OFF tier and when normal maps are disabled.
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
        reach = max(0.5, dominant.radius)
        dist_bucket = min(3, int(dist / reach * 4))
        tint_map = self._lit_tint_map(
            base_sprite,
            sprite.get_width(),
            sprite.get_height(),
            dominant,
            bucket,
            dist_bucket,
        )
        if tint_map is None:
            return sprite
        result = sprite.copy()
        result.blit(tint_map, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
        try:
            result = result.convert_alpha()
        except pygame.error:
            pass
        return result

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

    def _lit_tint_map(
        self,
        base_sprite: pygame.Surface,
        out_w: int,
        out_h: int,
        light: LightSource,
        bucket: int,
        dist_bucket: int,
    ) -> pygame.Surface | None:
        """A stable per-pixel tint multiplier for BLEND_RGB_MULT.

        Built once per (base sprite, light-direction bucket, distance bucket,
        light color, output size) from the BASE sprite's baked normal map and
        cached. Using the base sprite (not each animation frame's normal map)
        keeps the shading identical across animation frames so actors do not
        flicker as they animate. The per-pixel work runs only on a cache miss.
        """
        key = (id(base_sprite), bucket, dist_bucket, hashable_color(light.color), out_w, out_h)
        cache = getattr(self, "_lit_shade_cache", None)
        if cache is None:
            cache = {}
            self._lit_shade_cache = cache
        cached = cache.get(key)
        if cached is not None:
            return cached

        normal = self.sprites.normal_map_for(base_sprite)
        if normal is None:
            cache[key] = None
            return None

        bw, bh = base_sprite.get_width(), base_sprite.get_height()
        long_side = max(bw, bh)
        if long_side > LIGHT_SHADE_DOWNSAMPLE_LONG:
            f = LIGHT_SHADE_DOWNSAMPLE_LONG / long_side
            sw = max(1, int(bw * f))
            sh = max(1, int(bh * f))
            small_normal = pygame.transform.scale(normal, (sw, sh))
        else:
            sw, sh = bw, bh
            small_normal = normal

        # Representative light direction for the bucket. Bucket 0 means the
        # actor is on top of the light (no horizontal direction) -> only the
        # front bias lights it; otherwise use the bucket's center angle.
        if bucket == 0:
            ldx = ldy = 0.0
        else:
            angle = (bucket + 0.5) / LIGHT_DIRECTION_BUCKETS * math.tau - math.pi
            ldx = math.cos(angle)
            ldy = math.sin(angle)
        ldz = LIGHT_SHADE_BIAS_Z
        light_color = light.color
        atten = max(0.0, 1.0 - (dist_bucket + 0.5) / 4.0)
        intensity = light.intensity

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

        # Scale the base-sized tint to the frame's output size (cast frames are
        # larger than the base). The sprite itself is never scaled here.
        tint_full = pygame.transform.smoothscale(tint, (out_w, out_h))
        try:
            tint_full = tint_full.convert_alpha()
        except pygame.error:
            pass
        cache[key] = tint_full
        return tint_full

    def reset_lighting_caches(self) -> None:
        # Called on floor/theme change alongside ``tile_cache.clear``; bounds
        # the lit-actor tint cache and invalidates any sized buffers.
        self._lit_shade_cache = {}
        self._light_sprite_cache = {}
        self._flicker_scratch_cache = {}
        self._light_buffer_surface = None
        self._light_scratch_surface = None
        cache = getattr(self, "_frame_cache", None)
        if isinstance(cache, dict):
            cache.pop("frame_lights", None)