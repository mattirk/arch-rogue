"""Regressions for the offline wall bake: straight details and hidden RGB."""
import importlib.util
from pathlib import Path
import unittest

from PIL import Image, ImageDraw

spec = importlib.util.spec_from_file_location(
    "normalize_wall_assets", Path(__file__).resolve().parents[1] / "tools/normalize_wall_assets.py")
wall_bake = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wall_bake)


class WallNormalizationTest(unittest.TestCase):
    def test_straight_detail_survives_irregular_silhouette(self):
        source = Image.new("RGBA", (512, 512), (255, 0, 255, 0))
        draw = ImageDraw.Draw(source)
        draw.polygon([(259, 56), (453, 146), (453, 397), (259, 481),
                      (64, 397), (64, 146)], fill=(100, 110, 120, 255))
        # Deliberately jagged outline above a straight painted detail.
        for x in range(185, 235, 7):
            y = round(56 + abs(x - 259) * 90 / 195)
            draw.rectangle((x, y, x + 2, y + 6), fill=(255, 0, 255, 0))
        draw.rectangle((180, 140, 330, 143), fill=(200, 210, 220, 255))
        # Transparent chips at the joining faces must not become opaque RGB.
        draw.rectangle((64, 240, 68, 252), fill=(255, 0, 255, 0))
        image = wall_bake.normalize(source)
        rows = []
        for x in range(190, 321):
            rows.append(tuple(y for y in range(110, 160)
                              if image.getpixel((x, y))[:3] == (200, 210, 220)))
        self.assertTrue(rows[0])
        self.assertTrue(all(row == rows[0] for row in rows), "straight top detail was bent")
        colors = {color for _, color in image.getcolors(512 * 512)}
        self.assertNotIn((255, 0, 255, 255), colors, "transparent RGB became visible")


if __name__ == "__main__":
    unittest.main()
