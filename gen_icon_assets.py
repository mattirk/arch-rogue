"""Generate the Arch Rogue game logo/icon (the octahedron relic) as PNG
assets at the required sizes.

The logo is the octahedron cut-gem relic (the ``relic_02_octahedron`` design)
rendered as a warm-amber gem on a transparent background with a faint accent
halo. It is drawn *natively at each size* (not downscaled) so the silhouette
and outline stay crisp at 16/32px. Outputs land in
``src/arch_rogue/assets/icons/`` and are bundled as package data.

Run:  SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python gen_icon_assets.py
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import pygame

# Warm amber gem palette (coherent across facets, lit -> dark).
FACET_UL = (252, 222, 150)  # lit upper-left (brightest)
FACET_UR = (212, 176, 96)  # mid upper-right
FACET_BL = (162, 124, 60)  # mid-dark lower-left
FACET_BR = (116, 82, 38)  # darkest lower-right
EDGE_HI = (255, 245, 212)  # bright lit ridge
OUTLINE = (24, 16, 12)  # silhouette outline
HALO = (235, 205, 120)  # accent halo
SPEC = (255, 252, 232)  # specular pinprick


def clamp(v: int) -> int:
    return max(0, min(255, v))


def shade(c: tuple[int, int, int], n: int) -> tuple[int, int, int]:
    return (clamp(c[0] + n), clamp(c[1] + n), clamp(c[2] + n))


def draw_logo(size: int) -> pygame.Surface:
    """Draw the octahedron logo natively on a ``size`` x ``size`` canvas."""
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    cx = size / 2.0
    cy = size / 2.0
    # Geometry: a tall octahedron. Half-width a touch less than half-height so
    # the gem reads as a cut stone, not a square.
    hw = size * 0.34
    hh = size * 0.40
    top = (cx, cy - hh)
    right = (cx + hw, cy)
    bottom = (cx, cy + hh)
    left = (cx - hw, cy)
    center = (cx, cy)

    # Faint accent halo behind the gem (soft radial). Low alpha so it never
    # dominates at small sizes; gives the icon warmth without a hard ring.
    if size >= 32:
        halo_r = int(size * 0.46)
        for r in range(halo_r, 0, -2):
            t = r / halo_r
            a = int(34 * (1.0 - t) ** 2)
            if a <= 0:
                continue
            pygame.draw.circle(s, (*HALO, a), (int(cx), int(cy)), r)

    # Facets (filled), drawn back-to-front so the cut reads correctly.
    pygame.draw.polygon(s, FACET_UL, [top, left, center])
    pygame.draw.polygon(s, FACET_UR, [top, center, right])
    pygame.draw.polygon(s, FACET_BL, [center, left, bottom])
    pygame.draw.polygon(s, FACET_BR, [center, bottom, right])

    # Internal facet ridges (center -> each vertex) to read the cut at scale.
    ridge = shade(FACET_BR, 18)
    ridge_w = max(1, int(size * 0.012))
    for vertex in (top, right, bottom, left):
        pygame.draw.line(s, ridge, center, vertex, ridge_w)

    # Silhouette outline (thick enough to survive at small sizes).
    outline_w = max(1, int(size * 0.035))
    pygame.draw.polygon(s, OUTLINE, [top, right, bottom, left], outline_w)

    # Bright lit ridge along the upper-left edge (the gem's specular edge).
    edge_w = max(1, int(size * 0.020))
    pygame.draw.line(s, EDGE_HI, top, left, edge_w)

    # Specular pinpricks on the lit facet.
    if size >= 48:
        sp = max(1, int(size * 0.018))
        pygame.draw.circle(s, SPEC, (int(cx - hw * 0.34), int(cy - hh * 0.30)), sp)
        if size >= 128:
            pygame.draw.circle(
                s, SPEC, (int(cx - hw * 0.50), int(cy - hh * 0.18)), max(1, sp // 2)
            )

    return s


SIZES = (16, 32, 64, 128, 256, 512)


def main() -> None:
    pygame.init()
    pygame.display.set_mode((1, 1))
    out_dir = (
        Path(__file__).resolve().parent / "src" / "arch_rogue" / "assets" / "icons"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    for size in SIZES:
        surf = draw_logo(size)
        surf = surf.convert_alpha()
        path = out_dir / f"icon_{size}.png"
        pygame.image.save(surf, str(path))
        print(f"saved {path} ({size}x{size})")
    print(f"\n{len(SIZES)} icons written to {out_dir}")


if __name__ == "__main__":
    main()
