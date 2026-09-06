#!/usr/bin/env python3
"""Fit approved wall artwork to the runtime 2:1 prism (offline asset bake).

Input: a directory of the ten extracted, unrectified 512x512 RGBA wall PNGs.
Output: normalized PNGs in a separate directory. Never process output again.
No generated-service or staging paths are used by the game.
"""
import argparse
import math
from pathlib import Path

from PIL import Image


def normalize(source):
    source = source.convert("RGBA")
    assert source.size == (512, 512)
    pixels = source.load()
    bounds = source.getbbox()
    left, _, right, bottom = bounds
    center = (left + right - 1) / 2
    # Rounded silhouette pixels must not drive texture coordinates: doing so
    # bends straight features such as the raised slab. Fit the top with ONE
    # affine map, then map the two side faces below its front edges.
    source_top = 56
    source_top_front = 236
    source_half_width = (right - left - 1) / 2
    offsets = sorted(((dx, dy) for dx in range(-32, 33) for dy in range(-32, 33)),
                     key=lambda p: p[0] * p[0] + p[1] * p[1])

    def stone_sample(x, y):
        # The extracted image contains transparent chips. Their RGB is often
        # black; making those pixels opaque caused the reported edge spots.
        # Extend nearby real stone into the join plane instead of punching
        # gaps back into the corrected silhouette.
        if pixels[x, y][3] == 255:
            return pixels[x, y]
        for dx, dy in offsets:
            xx, yy = x + dx, y + dy
            if 0 <= xx < 512 and 0 <= yy < 512 and pixels[xx, yy][3] == 255:
                return pixels[xx, yy]
        raise ValueError(f"no opaque stone near {(x, y)}")
    output = Image.new("RGBA", source.size)
    target = output.load()
    for x in range(60, 453):
        # One wall spans 392 source pixels = 64 world pixels. Its top and
        # ground diamonds span 196 pixels = 32 world pixels vertically.
        distance = abs(x - 256)
        top = 56 + distance / 2
        face = 252 - distance / 2
        ground = 482 - distance / 2
        fraction = (x - 256) / 196
        sx = center + fraction * source_half_width
        seam = source_top_front - abs(fraction) * (source_top_front - source_top) / 2
        source_ground = bottom - 1 - abs(fraction) * 84
        for y in range(math.ceil(top), math.floor(ground) + 1):
            if y <= face:
                sy = source_top + (y - 56) * (source_top_front - source_top) / 196
            else:
                sy = seam + (y - face) / (ground - face) * (source_ground - seam)
            # Nearest sampling keeps the existing pixel clusters crisp.
            target[x, y] = stone_sample(round(sx), round(sy))
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error("source and output must differ; rectification is not idempotent")
    args.output.mkdir(parents=True, exist_ok=True)
    for number in range(401, 411):
        name = f"wall_{number}.png"
        with Image.open(args.source / name) as source:
            normalize(source).save(args.output / name)


if __name__ == "__main__":
    main()
