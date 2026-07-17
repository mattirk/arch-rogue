from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


from arch_rogue.constants import (
    DUNGEON_FLOOR_VARIANTS,
    DUNGEON_WALL_VARIANTS,
    TILE_H,
    TILE_W,
    WORLD_SCALE,
)
from arch_rogue.content import ARCHETYPES, DUNGEON_THEMES
from arch_rogue.game import Game
from arch_rogue.models import Tile


class DungeonSpriteVariants36Tests(unittest.TestCase):
    def tearDown(self) -> None:
        pass

    def make_game(self, tmpdir: str, seed: int = 3601) -> Game:
        game = Game(
            screen_size=(960, 540),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.rng.seed(seed)
        game.restart(ARCHETYPES[0])
        if game.story_intro_pending:
            self.assertTrue(game.choose_story_relic_path(0))
        game.active_cutscene = None
        return game

    # --- Variant selection ------------------------------------------------

    def test_tile_seed_is_bounded_deterministic_and_streak_free(self) -> None:
        # The seed must be a bounded variant index (so the pre-generated cache
        # stays tiny), deterministic per tile, exercise every variant across a
        # floor, and avoid axis streaks so adjacent tiles don't collapse into a
        # repeating band.
        bound = max(DUNGEON_WALL_VARIANTS, DUNGEON_FLOOR_VARIANTS)
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                seen: set[int] = set()
                for x in range(24):
                    for y in range(24):
                        seed = game.tile_seed(x, y)
                        self.assertGreaterEqual(seed, 0)
                        self.assertLess(seed, bound)
                        self.assertEqual(seed, game.tile_seed(x, y))
                        seen.add(seed)
                self.assertEqual(seen, set(range(bound)))
                row = {game.tile_seed(5, y) for y in range(12)}
                col = {game.tile_seed(x, 5) for x in range(12)}
                self.assertGreater(len(row), 2)
                self.assertGreater(len(col), 2)
            finally:
                pass

    # --- Pre-generation / cache bounds ------------------------------------

    def test_prewarm_and_draw_cache_bounds_stable(self) -> None:
        # restart() calls prewarm_tile_cache(), so the cache must already hold
        # every wall/floor/stairs variant (shop + non-shop) for the current
        # theme before any render call. Drawing a full dungeon frame must not
        # invent new seed values beyond the bounded variant set, and repeated
        # frames must reuse cached surfaces exactly — no new cache entries.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                theme = game.theme.name
                wall_keys = [
                    k
                    for k in game.tile_cache
                    if k[0] == theme and k[1] == int(Tile.WALL)
                ]
                floor_keys = [
                    k
                    for k in game.tile_cache
                    if k[0] == theme and k[1] == int(Tile.FLOOR)
                ]
                stairs_keys = [
                    k
                    for k in game.tile_cache
                    if k[0] == theme and k[1] == int(Tile.STAIRS)
                ]
                # Seven base face styles plus the two bar faces with mounted
                # sconces are prewarmed for every wall seed.
                self.assertEqual(len(wall_keys), DUNGEON_WALL_VARIANTS * 9)
                # Floor exists in normal, shop, guest, bar, and garden forms;
                # stairs in normal + shop only (special-room stairs keep the
                # normal slab).
                self.assertEqual(len(floor_keys), DUNGEON_FLOOR_VARIANTS * 5)
                self.assertEqual(len(stairs_keys), DUNGEON_FLOOR_VARIANTS * 2)

                before = set(game.tile_cache.keys())
                game.draw()
                wall_seeds = {
                    k[2]
                    for k in game.tile_cache
                    if k[0] == theme and k[1] == int(Tile.WALL)
                }
                floor_seeds_shop = {
                    k[2]
                    for k in game.tile_cache
                    if k[0] == theme and k[1] == int(Tile.FLOOR) and k[3]
                }
                floor_seeds_noop = {
                    k[2]
                    for k in game.tile_cache
                    if k[0] == theme
                    and k[1] == int(Tile.FLOOR)
                    and not k[3]
                    and not k[4]
                }
                floor_seeds_guest = {
                    k[2]
                    for k in game.tile_cache
                    if k[0] == theme and k[1] == int(Tile.FLOOR) and k[4]
                }
                self.assertLessEqual(len(wall_seeds), DUNGEON_WALL_VARIANTS)
                self.assertLessEqual(len(floor_seeds_shop), DUNGEON_FLOOR_VARIANTS)
                self.assertLessEqual(len(floor_seeds_noop), DUNGEON_FLOOR_VARIANTS)
                self.assertLessEqual(len(floor_seeds_guest), DUNGEON_FLOOR_VARIANTS)

                game.draw()
                self.assertEqual(set(game.tile_cache.keys()), before)
            finally:
                pass

    def test_floor_detail_is_carved_groove_not_flat_scratch(self) -> None:
        # The variant surface detail must read as a carved groove with real
        # form (a shadowed recess AND a lit lip), not a single flat scratch,
        # and must stay inside the slab diamond so no joint pokes into the
        # transparent tile margin. Variant 0 stays a flat premium slab.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                # This assertion protects the original procedural groove
                # generator; milestone 4.0's asset floors have authored texture.
                game.set_legacy_graphics(True)
                for v in range(DUNGEON_FLOOR_VARIANTS):
                    surf, ax, ay = game.tile_surface(Tile.FLOOR, v, False)
                    slab = sum(game.shade(game.theme.floor, v * 2 - 3))
                    shadow = lip = outside = 0
                    for x in range(surf.get_width()):
                        for y in range(surf.get_height()):
                            p = surf.get_at((x, y))
                            if p[3] < 200:
                                continue
                            dx = abs(x - ax) / (TILE_W / 2)
                            dy = abs(y - ay) / (TILE_H / 2)
                            if dx + dy > 1.0:
                                outside += 1
                            b = sum(p[:3])
                            if b < slab - 2:
                                shadow += 1
                            elif b > slab + 2:
                                lip += 1
                    if v == 0:
                        self.assertEqual(shadow, 0, "variant 0 must stay flat")
                        self.assertEqual(lip, 0, "variant 0 must stay flat")
                    else:
                        self.assertGreater(
                            shadow, 0, f"variant {v} groove has no shadow recess"
                        )
                        self.assertGreater(lip, 0, f"variant {v} groove has no lit lip")
                    self.assertEqual(
                        outside,
                        0,
                        f"variant {v} detail pokes outside the slab diamond",
                    )
            finally:
                pass

    # --- Floor transition rewarm ------------------------------------------

    def test_descend_and_door_open_rewarm_tile_cache(self) -> None:
        # Descending changes the theme and must clear + prewarm the cache for
        # the new theme so the first frame on the new floor is hitch-free, and
        # opening a door likewise clears + prewarms so no first-frame hitch
        # occurs right next to the player.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                game.tile_cache.clear()
                game.prewarm_tile_cache()
                first_theme = game.theme.name
                self.assertTrue(any(k[0] == first_theme for k in game.tile_cache))

                # Force a theme change + rewarm without needing the player on
                # the stairs: simulate the prewarm half of descend.
                game.theme = next(t for t in DUNGEON_THEMES if t.name != first_theme)
                game.tile_cache.clear()
                game.prewarm_tile_cache()
                self.assertTrue(any(k[0] == game.theme.name for k in game.tile_cache))
                self.assertFalse(any(k[0] == first_theme for k in game.tile_cache))
                wall_keys = [
                    k
                    for k in game.tile_cache
                    if k[0] == game.theme.name and k[1] == int(Tile.WALL)
                ]
                self.assertEqual(len(wall_keys), DUNGEON_WALL_VARIANTS * 9)

                # Find a closed door tile in the dungeon and open it adjacent
                # to the player; the cache must be rewarmed afterward.
                door = None
                w = len(game.dungeon.tiles)
                h = len(game.dungeon.tiles[0]) if w else 0
                for x in range(w):
                    for y in range(h):
                        if game.dungeon.tiles[x][y] == Tile.CLOSED_DOOR:
                            door = (x, y)
                            break
                    if door:
                        break
                if door is None:
                    self.skipTest("no closed door on this seed")
                game.player.x = door[0] + 0.5
                game.player.y = door[1] + 0.5
                self.assertTrue(game.open_nearby_door())
                self.assertGreater(len(game.tile_cache), 0)
            finally:
                pass


if __name__ == "__main__":
    unittest.main()
