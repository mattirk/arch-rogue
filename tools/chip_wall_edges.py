#!/usr/bin/env python3
"""Cut subtle chips from the two rear silhouettes of normalized wall sprites.

Run after coarsen_wall_edges.py, using separate input/output directories.
Only removes pixels: all surviving artwork, including edge texture, is kept.
"""
import argparse
import math
from pathlib import Path
import random

from PIL import Image


def chip(source, variant):
    result = source.copy()
    rng = random.Random(0x57414C4C + variant)
    for side in (-1, 1):
        for slot in range(6):
            center = 22 + slot * 28 + rng.randrange(-4, 5)
            width = rng.randrange(5, 10)
            peak = rng.choice((2, 2, 3))
            skew = rng.choice((-1, 0, 1))
            for offset in range(-width // 2, width // 2 + 1):
                along = center + offset
                x = 256 + side * along
                # A shallow stepped wedge, occasionally asymmetric, rather
                # than a rectangular notch or uniform sawtooth silhouette.
                depth = max(1, peak - abs(offset - skew) // 2)
                for y in range(math.ceil(56 + along / 2), math.ceil(56 + along / 2) + depth):
                    result.putpixel((x, y), (0, 0, 0, 0))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error("source and output must differ")
    args.output.mkdir(parents=True, exist_ok=True)
    for number in range(401, 411):
        name = f"wall_{number}.png"
        with Image.open(args.source / name) as source:
            chip(source, number).save(args.output / name)


if __name__ == "__main__":
    main()
