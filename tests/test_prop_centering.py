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

"""5.0 prop centering: standing props rest centered on the floor art.

The 4.9.15/4.9.16 wall-contact work let the player press right up against
furnishings, which exposed that standing props rendered well north of the
floor diamond they stand on: their manifest anchors rode the sprite's bottom
edge instead of the base-diamond axis. Since 5.0 the anchors mark the base
axis and the draw sites add FLOOR_ART_CONTACT_Y_OFFSET /
SPECIAL_FLOOR_ART_CONTACT_Y_OFFSET, so ``blit_resolved_sprite`` places the
base axis exactly on the visible floor diamond center.

The centering guarantee is asserted in two composable halves:

1. every standing-prop manifest ``source_anchor`` equals the base-diamond
   axis measured from the master PNG's alpha silhouette, and
2. the floor-contact constants equal the authored floors' visible diamond
   centers through the real tile pipeline.

``blit_resolved_sprite`` pins the resolved anchor to
``tile_center + contact_offset`` by construction, so (1) + (2) imply the
prop base rests on the floor diamond center. A coarse end-to-end draw check
guards the composition against draw-site regressions.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from arch_rogue.constants import (
    FLOOR_ART_CONTACT_Y_OFFSET,
    SPECIAL_FLOOR_ART_CONTACT_Y_OFFSET,
)
from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game
from arch_rogue.models import Tile

ASSET_ROOT = (
    Path(__file__).resolve().parents[1] / "src" / "arch_rogue" / "assets" / "sprites"
)

# Standing props drawn base-centered on dungeon floor tiles. Trap plates keep
# their bottom-edge anchors (rendering/effects.draw_trap recenters them on the
# actor ground line explicitly) and wall-mounted art (shop_sign, sconces) never
# claims a floor tile.
STANDING_PROP_KEYS = (
    "lossless_room_mirror",
    "lossless_room_chimes",
    "lossless_room_brazier",
    "lossless_room_reliquary",
    "bar_barrel",
    "bar_table",
    "gold_stack",
    "gold_stack_02",
    "gold_stack_03",
    "gold_stack_04",
    "gold_stack_05",
    "shrine",
    "secret_cache",
)


def _alpha_row_widths(surface: pygame.Surface) -> list[int]:
    width, height = surface.get_size()
    widths = []
    for ry in range(height):
        left = right = None
        for rx in range(width):
            if surface.get_at((rx, ry)).a > 8:
                if left is None:
                    left = rx
                right = rx
        widths.append(0 if left is None else right - left + 1)
    return widths


def _base_diamond_axis(surface: pygame.Surface) -> int:
    """Bottom-up: the row where the base diamond's edge stops widening.

    The isometric 2:1 slope adds ~4 px per master row, so genuine base rows
    grow by >= 2 px; noise rows (embers, sparks) below 15% of the peak width
    are ignored when locating the south tip.
    """

    widths = _alpha_row_widths(surface)
    peak = max(widths)
    noise = max(2, peak * 0.15)
    bottom = None
    for ry in range(len(widths) - 1, -1, -1):
        if widths[ry] >= noise:
            bottom = ry
            break
    assert bottom is not None
    axis = bottom
    for ry in range(bottom - 1, -1, -1):
        if widths[ry] < noise:
            break
        if widths[ry] >= widths[ry + 1] + 2:
            axis = ry
        else:
            break
    return axis


class PropAnchorTests(unittest.TestCase):
    """Half 1: manifest anchors mark the measured base-diamond axis."""

    def test_standing_prop_anchors_equal_the_measured_base_axis(self) -> None:
        manifest = json.loads((ASSET_ROOT / "manifest.json").read_text())
        for key in STANDING_PROP_KEYS:
            with self.subTest(prop=key):
                entry = manifest["props"][key]
                master = pygame.image.load(str(ASSET_ROOT / entry["path"]))
                axis = _base_diamond_axis(master)
                self.assertLessEqual(
                    abs(float(entry["source_anchor"][1]) - axis),
                    2.0,
                    f"{key}: manifest anchor {entry['source_anchor'][1]} vs "
                    f"measured base axis {axis}",
                )


class PropCenteringTests(unittest.TestCase):
    """Half 2 + composition through the real pipeline."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.game = Game(
            screen_size=(960, 600),
            headless=True,
            save_path=Path(cls._tmp.name) / "prop-centering.json",
        )
        cls.game.options_path = Path(cls._tmp.name) / "prop-centering-opt.json"
        cls.game.rng.seed(3001)
        cls.game.restart(ARCHETYPES[2])
        cls.tx, cls.ty = int(cls.game.player.x), int(cls.game.player.y)
        cls.game.camera_x = cls.tx + 0.5
        cls.game.camera_y = cls.ty + 0.5
        cls.sx, cls.sy = cls.game.world_to_screen(cls.tx + 0.5, cls.ty + 0.5)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def _screen_rows(self) -> list[int]:
        shot = self.game.screen
        black = pygame.mask.from_threshold(shot, (0, 0, 0), (25, 25, 25, 255))
        black.invert()
        rects = black.get_bounding_rects()
        self.assertTrue(rects, "nothing drawn")
        y0 = min(r.top for r in rects)
        y1 = max(r.bottom - 1 for r in rects)
        return [y0, y1]

    def _floor_midpoint(self, special_floor_kind: str | None) -> int:
        surface, ax, ay = self.game.tile_surface(
            Tile.FLOOR,
            self.game.tile_seed(self.tx, self.ty),
            special_floor_kind=special_floor_kind,
        )
        self.game.screen.fill((0, 0, 0))
        self.game.screen.blit(surface, (self.sx - ax, self.sy - ay))
        north, south = self._screen_rows()
        return (north + south) // 2

    def test_floor_art_contact_offsets_match_the_authored_floors(self) -> None:
        wps = self.game.world_pixel_scale
        generic = self._floor_midpoint(None) - self.sy
        self.assertLessEqual(
            abs(generic - round(FLOOR_ART_CONTACT_Y_OFFSET * wps)), 2, generic
        )
        for kind in ("lossless_soul", "bar", "shop"):
            with self.subTest(floor=kind):
                midpoint = self._floor_midpoint(kind) - self.sy
                self.assertLessEqual(
                    abs(
                        midpoint
                        - round(SPECIAL_FLOOR_ART_CONTACT_Y_OFFSET * wps)
                    ),
                    3,
                    midpoint,
                )

    def test_drawn_props_extend_south_of_the_floor_center(self) -> None:
        """Composition guard: the base straddles the floor diamond center.

        With the anchor on the base axis and the contact offset applied, the
        drawn sprite's south extent must land clearly south of the floor
        midpoint (the base's bottom half) yet inside the floor diamond. The
        pre-5.0 bottom-edge anchors put the entire sprite at or north of the
        midpoint, which this rejects.
        """

        wps = self.game.world_pixel_scale
        special_mid = self.sy + round(SPECIAL_FLOOR_ART_CONTACT_Y_OFFSET * wps)
        generic_mid = self.sy + round(FLOOR_ART_CONTACT_Y_OFFSET * wps)
        floor_south = self.sy + round(16 * wps)  # tile diamond half-height
        shrine = SimpleNamespace(
            x=self.tx + 0.5, y=self.ty + 0.5, kind="Fortune Shrine", used=False
        )
        secret = SimpleNamespace(
            x=self.tx + 0.5,
            y=self.ty + 0.5,
            kind="Hidden Cache",
            opened=False,
            revealed=True,
        )
        cases = (
            (
                "soul_mirror",
                special_mid,
                lambda: self.game.draw_lossless_soul_prop(
                    "soul_mirror", self.tx, self.ty
                ),
            ),
            (
                "soul_reliquary",
                special_mid,
                lambda: self.game.draw_lossless_soul_prop(
                    "soul_reliquary", self.tx, self.ty
                ),
            ),
            (
                "bar_barrel",
                special_mid,
                lambda: self.game.draw_bar_prop("bar_barrel_1", self.tx, self.ty),
            ),
            (
                "bar_table",
                special_mid,
                lambda: self.game.draw_bar_prop("bar_table_1", self.tx, self.ty),
            ),
            # The gold pile mound is only ~6 px tall at this zoom, so its
            # south extent sits ON the midpoint rather than past it; the
            # anchor half of the guarantee still covers it.
            (
                "gold_stack",
                special_mid - 3,
                lambda: self.game.draw_gold_stack(self.tx, self.ty, 3, 0),
            ),
            ("shrine", generic_mid, lambda: self.game.draw_shrine(shrine)),
            ("secret", generic_mid, lambda: self.game.draw_secret(secret)),
        )
        for label, floor_mid, draw in cases:
            with self.subTest(prop=label):
                self.game.screen.fill((0, 0, 0))
                draw()
                _, south = self._screen_rows()
                self.assertGreater(
                    south,
                    floor_mid + 1,
                    f"{label}: south extent {south - self.sy:+d} does not "
                    "reach past the floor diamond center — the base no longer "
                    "straddles its tile",
                )
                self.assertLessEqual(
                    south,
                    floor_south + 2,
                    f"{label}: south extent {south - self.sy:+d} spills past "
                    "the floor diamond's south tip",
                )


if __name__ == "__main__":
    unittest.main()
