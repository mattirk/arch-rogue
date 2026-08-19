from __future__ import annotations

import math
import os
import sys
import tempfile
import unittest
from pathlib import Path

import pygame

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


from arch_rogue.constants import (
    DUNGEON_FLOOR_VARIANTS,
    DUNGEON_HD_WALL_VARIANTS,
    DUNGEON_WALL_VARIANTS,
    TILE_H,
    TILE_W,
)
from arch_rogue.content import ARCHETYPES, DUNGEON_THEMES
from arch_rogue.game import Game
from arch_rogue.models import Tile


class DungeonSpriteVariants36Tests(unittest.TestCase):
    def make_game(self, tmpdir: str, seed: int = 3601) -> Game:
        game = Game(
            screen_size=(960, 540),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
            eager_tile_prewarm=True,
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.rng.seed(seed)
        game.restart(ARCHETYPES[0])
        if game.story_intro_pending:
            self.assertTrue(game.choose_story_relic_path(0))
        game.active_cutscene = None
        return game

    @staticmethod
    def wall_variants(game: Game) -> int:
        # HD ships ten authored wall masters; Modern/Legacy keep four.
        return (
            DUNGEON_HD_WALL_VARIANTS
            if game._hd_world_graphics_selected()
            else DUNGEON_WALL_VARIANTS
        )

    # --- Variant selection ------------------------------------------------

    def test_tile_seed_is_bounded_deterministic_and_streak_free(self) -> None:
        # The seed must be a bounded variant index (so the pre-generated cache
        # stays tiny), deterministic per tile, exercise every variant across a
        # floor, and avoid axis streaks so adjacent tiles don't collapse into a
        # repeating band.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            # HD spreads the raw seed over the lcm of both family sizes so
            # each family's fold stays uniform; consumers fold before caching.
            bound = math.lcm(self.wall_variants(game), DUNGEON_FLOOR_VARIANTS)
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
                self.assertGreater(
                    sum(
                        game.tile_seed(x, y) != game.tile_seed(x + 4, y)
                        for x in range(12)
                        for y in range(16)
                    ),
                    96,
                    "variant layout repeats exactly every four tiles on x",
                )
                self.assertGreater(
                    sum(
                        game.tile_seed(x, y) != game.tile_seed(x, y + 4)
                        for x in range(16)
                        for y in range(12)
                    ),
                    96,
                    "variant layout repeats exactly every four tiles on y",
                )
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
                # Nine base face styles (plain plus quest/bar/garden/soul left
                # and right) plus the two bar faces with mounted sconces are
                # prewarmed for every wall seed.
                self.assertEqual(len(wall_keys), self.wall_variants(game) * 11)
                # Floor exists in normal, shop, guest, bar, garden, and soul
                # hall forms.
                # Stairs prewarm frame zero for every normal/shop variant, then
                # the remaining pulse frames only for this floor's actual stair
                # seed so animation starts hitch-free without multiplying memory.
                self.assertEqual(len(floor_keys), DUNGEON_FLOOR_VARIANTS * 6)
                stair_frame_count = game.sprites.world_tile_animation_frame_count(
                    "stairs"
                )
                self.assertEqual(
                    len(stairs_keys),
                    DUNGEON_FLOOR_VARIANTS * 2 + stair_frame_count - 1,
                )

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
                self.assertLessEqual(len(wall_seeds), self.wall_variants(game))
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

    def test_authored_stairs_composite_matching_floor_underlay_once(self) -> None:
        class StubWorldSprites:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def world_tile_surface(
                self,
                key: str,
                *,
                target_canvas: tuple[int, int],
                target_anchor: tuple[int, int],
                tint: tuple[int, int, int],
                accent: tuple[int, int, int],
                variant: int,
                mirror: bool = False,
                wall_face_style: str | None = None,
                animation_frame: int = 0,
                render_scale_bucket: float = 1.0,
            ) -> tuple[pygame.Surface, int, int]:
                self.calls.append(
                    {
                        "key": key,
                        "target_canvas": target_canvas,
                        "target_anchor": target_anchor,
                        "tint": tint,
                        "accent": accent,
                        "variant": variant,
                        "mirror": mirror,
                        "wall_face_style": wall_face_style,
                        "animation_frame": animation_frame,
                        "render_scale_bucket": render_scale_bucket,
                    }
                )
                surface = pygame.Surface(target_canvas, pygame.SRCALPHA)
                if key == "floor":
                    surface.set_at((2, 2), (11, 22, 33, 255))
                    surface.set_at((10, 10), (44, 55, 66, 255))
                elif key == "stairs":
                    surface.set_at((10, 10), (201, 31, 41, 255))
                return surface, target_anchor[0], target_anchor[1]

        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                sprites = StubWorldSprites()
                object.__setattr__(game, "sprites", sprites)
                game.tile_cache.clear()

                first = game.tile_surface(Tile.STAIRS, 3, False)
                surface, anchor_x, anchor_y = first
                self.assertEqual(tuple(surface.get_at((2, 2))), (11, 22, 33, 255))
                self.assertEqual(tuple(surface.get_at((10, 10))), (201, 31, 41, 255))
                self.assertEqual([call["key"] for call in sprites.calls], ["stairs", "floor"])
                self.assertEqual(sprites.calls[0]["target_canvas"], sprites.calls[1]["target_canvas"])
                self.assertEqual(sprites.calls[0]["target_anchor"], sprites.calls[1]["target_anchor"])
                self.assertEqual(sprites.calls[0]["variant"], sprites.calls[1]["variant"])
                self.assertEqual(sprites.calls[0]["tint"], game.theme.floor)
                self.assertEqual(sprites.calls[1]["tint"], game.theme.floor)
                self.assertEqual((anchor_x, anchor_y), sprites.calls[0]["target_anchor"])

                second = game.tile_surface(Tile.STAIRS, 3, False)
                self.assertIs(second, first)
                self.assertEqual(len(sprites.calls), 2)
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
                self.assertEqual(len(wall_keys), self.wall_variants(game) * 11)

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

    def test_hidden_wall_face_interaction(self) -> None:
        # Touching a worn wall (HD master wall_403, variant index 2) with the
        # interact key plays the one-shot ``wall_face`` animation on that tile.
        # The interaction is deliberately hidden: no interaction hint may ever
        # advertise it.
        from arch_rogue.constants import DUNGEON_HD_WALL_VARIANTS as HD_WALLS

        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.assertTrue(game._hd_world_graphics_selected())
            self.assertGreater(
                game.sprites.world_tile_animation_frame_count("wall_face"), 1
            )
            target = None
            width = len(game.dungeon.tiles)
            height = len(game.dungeon.tiles[0]) if width else 0
            for x in range(width):
                for y in range(height):
                    if (
                        game.dungeon.tiles[x][y] != Tile.WALL
                        or game.tile_seed(x, y) % HD_WALLS
                        != game.SECRET_FACE_WALL_VARIANT
                    ):
                        continue
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nx, ny = x + dx, y + dy
                        if (
                            game.dungeon.in_bounds(nx, ny)
                            and game.dungeon.tiles[nx][ny] == Tile.FLOOR
                        ):
                            target = (x, y, nx, ny)
                            break
                    if target:
                        break
                if target:
                    break
            self.assertIsNotNone(target)
            wx, wy, px, py = target
            game.player.x, game.player.y = px + 0.5, py + 0.5
            self.assertEqual(game.nearby_secret_face_wall(), (wx, wy))
            hint = game.current_interaction_hint()
            if hint is not None:
                self.assertNotIn("wall", " ".join(str(part) for part in hint).lower())
            game.ui_elapsed = 0.0
            self.assertTrue(game.touch_secret_face_wall())
            first_frame = game.wall_face_tile_frame(wx, wy)
            self.assertGreaterEqual(first_frame, 1)
            surface = game.tile_surface(
                Tile.WALL,
                game.tile_seed(wx, wy),
                wall_face_frame=first_frame,
            )
            self.assertIsNotNone(surface[0])
            # Other walls stay untouched while the animation runs.
            self.assertEqual(game.wall_face_tile_frame(wx + 1, wy + 1), 0)
            game.ui_elapsed = 10.0
            self.assertEqual(game.wall_face_tile_frame(wx, wy), 0)
            self.assertIsNone(getattr(game, "_wall_face_anim", None))


if __name__ == "__main__":
    unittest.main()
