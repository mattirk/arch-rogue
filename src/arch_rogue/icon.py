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

"""Bundled game icon/logo loading.

The Arch Rogue logo is the octahedron relic, shipped as PNG assets in
``arch_rogue.assets.icons`` at several sizes (see ``gen_icon_assets.py``).
These helpers load them via :mod:`importlib.resources` so the icons resolve
both under a normal install and inside the pygbag/Pyodide web bundle.
"""

from __future__ import annotations

import io
from importlib import resources
from typing import Iterable

import pygame

# Sizes shipped under arch_rogue/assets/icons/.
ICON_SIZES: tuple[int, ...] = (16, 32, 64, 128, 256, 512)

# Module-level caches of loaded icon surfaces. ``_icon_cache`` holds the
# raw bundled icons keyed by size; ``_scaled_cache`` holds title-logo surfaces
# scaled to a requested height (keyed by height). Loading is cheap but the
# title screen and window icon both ask for one every Game construction;
# caching avoids re-reading the PNG.
_icon_cache: dict[int, pygame.Surface] = {}
_scaled_cache: dict[int, pygame.Surface] = {}


def _nearest_size(size: int) -> int:
    if size in ICON_SIZES:
        return size
    return min(ICON_SIZES, key=lambda s: abs(s - size))


def icon_sizes() -> tuple[int, ...]:
    return ICON_SIZES


def load_icon(size: int) -> pygame.Surface | None:
    """Return the bundled icon at the nearest available size, or ``None`` if
    the assets are not present (e.g. running from a source tree before the
    icon generator has been run)."""
    size = _nearest_size(size)
    cached = _icon_cache.get(size)
    if cached is not None:
        return cached
    try:
        data = (
            resources.files("arch_rogue.assets")
            .joinpath("icons", f"icon_{size}.png")
            .read_bytes()
        )
    except (FileNotFoundError, ModuleNotFoundError, OSError):
        return None
    try:
        surface = pygame.image.load(io.BytesIO(data))
    except pygame.error:
        return None
    try:
        surface = surface.convert_alpha()
    except pygame.error:
        pass
    _icon_cache[size] = surface
    return surface


def title_logo(height: int) -> pygame.Surface | None:
    """Return the logo scaled to the requested pixel height (cached by size).

    Used by menus for the branded title crest. The source is the 128px icon
    (sharp enough for typical crest sizes, small enough to scale cheaply).
    Returns ``None`` if the bundled assets are unavailable.
    """
    source = load_icon(128)
    if source is None:
        return None
    if height <= 0:
        return source
    cached = _scaled_cache.get(height)
    if cached is not None:
        return cached
    scale = height / source.get_height()
    new_w = max(1, int(source.get_width() * scale))
    new_h = max(1, int(source.get_height() * scale))
    scaled = pygame.transform.smoothscale(source, (new_w, new_h))
    _scaled_cache[height] = scaled
    return scaled


def available_sizes(paths: Iterable | None = None) -> list[int]:
    """Sizes actually present on disk (best-effort), mainly for diagnostics."""
    present: list[int] = []
    try:
        root = resources.files("arch_rogue.assets").joinpath("icons")
        for size in ICON_SIZES:
            if root.joinpath(f"icon_{size}.png").is_file():
                present.append(size)
    except (FileNotFoundError, ModuleNotFoundError, OSError):
        pass
    return present
