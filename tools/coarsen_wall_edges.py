#!/usr/bin/env python3
"""Transfer generated stone microtexture only to the two rear wall edges.

The generator's framing and background are not production geometry. Sample
its stone band in edge coordinates and transfer bounded luminance detail;
preserve the source sprites' alpha, raised slab, mortar and variant decoration.
"""
import argparse
import math
from pathlib import Path

from PIL import Image


def coarsen(source, detail, variant):
    result = source.copy()
    pixels = result.load()
    art = detail.load()
    assert detail.size == (1254, 1254), "unexpected generated reference framing"

    def sample(side, along, depth):
        # Measured rear apex and half-span in the generated reference.
        x = round(628 + side * along * 484 / 196)
        y = round(136 + (along / 2 + depth + 2) * 484 / 196)
        color = art[x, y]
        assert min(color[:3]) < 220, "sample crossed into generated background"
        return sum(color[:3]) / 3

    for side in (-1, 1):
        for along in range(8, 185):
            x = 256 + side * along
            edge = 56 + along / 2
            # Deterministic small offsets avoid identical wear on every tile.
            reference_along = 12 + (along + variant * 11) % 164
            for y in range(math.ceil(edge), math.ceil(edge) + 12):
                depth = y - edge
                local = sample(side, reference_along, depth)
                average = sum(sample(side, reference_along + shift, depth)
                              for shift in (-6, -3, 0, 3, 6)) / 5
                grain = max(-28, min(22, (local - average) * 1.7))
                fade = min(1, (12 - depth) / 5)
                delta = round(grain * fade)
                color = pixels[x, y]
                pixels[x, y] = tuple(max(0, min(255, c + delta)) for c in color[:3]) + (color[3],)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("detail", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error("use a separate source directory to avoid accumulating texture")
    args.output.mkdir(parents=True, exist_ok=True)
    with Image.open(args.detail) as detail:
        for number in range(401, 411):
            name = f"wall_{number}.png"
            with Image.open(args.source / name) as source:
                coarsen(source, detail, number - 403).save(args.output / name)


if __name__ == "__main__":
    main()
