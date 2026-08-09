from __future__ import annotations

import math
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame

from arch_rogue.constants import (
    ACTOR_GROUND_DEPTH_OFFSET,
    ACTOR_MOVE_COLLISION_RADIUS,
    GRAPHICS_TIER_VALUES,
)
from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game
from arch_rogue.models import Tile


class PlayerWallContactTests(unittest.TestCase):
    ROOM_MIN = 30
    ROOM_MAX = 34
    STEP = 0.01

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        root = Path(self.tempdir.name)
        self.game = Game(
            screen_size=(960, 540),
            headless=True,
            save_path=root / "run.json",
        )
        self.game.options_path = root / "options.json"
        self.game.restart(ARCHETYPES[0])
        if self.game.story_intro_pending:
            self.assertTrue(self.game.choose_story_relic_path(0))
        self.game.active_cutscene = None
        self.game.enemies = []
        self.game.shopkeepers = []
        self.game.story_guests = []
        self.game.idle_npcs = []
        self.game.dungeon.stairs = (2, 2)
        self.game.dungeon.solid_furnishing_boxes = ()
        self._prepare_square_room()

    def tearDown(self) -> None:
        pygame.quit()

    def _prepare_square_room(self) -> None:
        dungeon = self.game.dungeon
        for x in range(self.ROOM_MIN - 1, self.ROOM_MAX + 1):
            for y in range(self.ROOM_MIN - 1, self.ROOM_MAX + 1):
                dungeon.tiles[x][y] = Tile.WALL
        for x in range(self.ROOM_MIN, self.ROOM_MAX):
            for y in range(self.ROOM_MIN, self.ROOM_MAX):
                dungeon.tiles[x][y] = Tile.FLOOR

    def _prepare_large_render_room(self) -> None:
        """Keep genuine foreground walls away from north-contact render probes."""

        dungeon = self.game.dungeon
        # Bar barrels, soul-hall furnishings and shop gold stacks are drawn from
        # the dungeon's randomly placed special rooms, not from any of the actor
        # lists the test empties. One landing inside the probe room painted a
        # barrel over most of the player body -- 84% of it in the run that
        # caught this -- and failed the occlusion assertion for a prop the test
        # never asked for.
        dungeon.special_rooms = []
        dungeon.refresh_solid_furnishing_tiles()
        room_max = 40
        for x in range(self.ROOM_MIN - 1, room_max + 1):
            for y in range(self.ROOM_MIN - 1, room_max + 1):
                dungeon.tiles[x][y] = Tile.WALL
        for x in range(self.ROOM_MIN, room_max):
            for y in range(self.ROOM_MIN, room_max):
                dungeon.tiles[x][y] = Tile.FLOOR
        # Reveal *only* the prepared room. restart() reveals whatever surrounds
        # the randomly generated start position, and any of that still left in
        # the set draws real dungeon geometry into this scene -- which is how a
        # run could occasionally find a wall painted over the player body and
        # fail the occlusion assertion below for reasons the test never set up.
        self.game.revealed_tiles.clear()
        for x in range(self.ROOM_MIN - 2, room_max + 2):
            for y in range(self.ROOM_MIN - 2, room_max + 2):
                self.game.revealed_tiles.add((x, y))

    def _activate_native_zoom(self, zoom: float) -> None:
        """Pin a zoom these tests can read back off ``game.screen``.

        Production draws the world through ``_render_world_target``, which pins
        the render-scale bucket and, whenever the zoom sits *between* buckets,
        redirects the draw into an offscreen layer that is composited to the
        display afterwards. These tests call ``draw_world_objects`` directly, so
        they only line up with ``game.screen`` when the zoom is exactly a bucket
        (residual 1.0, no layer) and the bucket is actually activated. Without
        the activation the draw used whichever bucket the last render left
        pinned, which put the sprite rect off-screen often enough to make the
        whole test flake -- 54 failures across 15 isolated runs before this.
        """

        bucket = self.game.world_render_scale_bucket(zoom)
        self.assertAlmostEqual(bucket, zoom, places=6)
        self.game.set_view_zoom(zoom)
        self.game._activate_world_render_scale(bucket)

    def _draw_world_capturing_player_blit(
        self,
    ) -> tuple[pygame.Surface, pygame.Rect]:
        """Draw a frame and return the body sprite ``draw_player`` actually blit.

        ``_last_sprite_blit`` is a one-slot scratch register, and its own comment
        says ``draw_world_objects`` reads it "right after draw_player/draw_enemy".
        Reading it once the whole frame has finished is a stale read: the wall
        ghost pass that runs after the actor loop re-blits actor sprites through
        the same helper, so what is left in the register can be a rotated,
        differently sized sprite positioned somewhere else entirely -- observed
        as a 196x207 rect at x=-1056 while the player's own body was a 137x188
        rect at x=419. That put the probe outside the surface and raised
        IndexError, which is what made this test flake (54 subtest failures
        across 15 isolated runs). Capture at the same moment the production code
        does instead.
        """

        captured: list[tuple[pygame.Surface, pygame.Rect]] = []
        real_draw_player = self.game.draw_player

        def spy(player) -> None:
            real_draw_player(player)
            blit = self.game._last_sprite_blit
            if player is self.game.player and blit is not None:
                captured.append(blit)

        self.game.draw_player = spy  # type: ignore[method-assign]
        try:
            self.game.draw_world_objects()
        finally:
            del self.game.draw_player
        self.assertEqual(len(captured), 1)
        return captured[0]

    def _opaque_player_pixel_counts(
        self, blit: tuple[pygame.Surface, pygame.Rect]
    ) -> tuple[int, int]:
        sprite, rect = blit
        self.assertTrue(
            self.game.screen.get_rect().contains(rect),
            f"player body sprite {rect} left the {self.game.screen.get_size()} "
            "surface; the probe below can only compare on-screen pixels",
        )
        colorkey = sprite.get_colorkey()
        matched = 0
        opaque = 0
        for sy in range(sprite.get_height()):
            for sx in range(sprite.get_width()):
                pixel = sprite.get_at((sx, sy))
                if pixel.a != 255:
                    continue
                if (
                    colorkey is not None
                    and tuple(pixel[:3]) == tuple(colorkey[:3])
                ):
                    continue
                opaque += 1
                screen_pixel = self.game.screen.get_at((rect.x + sx, rect.y + sy))
                if tuple(screen_pixel[:3]) == tuple(pixel[:3]):
                    matched += 1
        return matched, opaque

    def _walk_until_blocked(
        self,
        dx: float,
        dy: float,
    ) -> tuple[float, float]:
        player = self.game.player
        player.x = player.y = 32.0
        for _ in range(1000):
            before = (player.x, player.y)
            self.game.move_actor(player, dx * self.STEP, dy * self.STEP)
            if (player.x, player.y) == before:
                break
        else:
            self.fail("player did not reach the room perimeter")
        return player.x, player.y

    def test_player_wall_contacts_are_consistent_in_every_graphics_tier(
        self,
    ) -> None:
        directions = {
            "north": (-1.0, -1.0),
            "north-east": (0.0, -1.0),
            "east": (1.0, -1.0),
            "south-east": (1.0, 0.0),
            "south": (1.0, 1.0),
            "south-west": (0.0, 1.0),
            "west": (-1.0, 1.0),
            "north-west": (-1.0, 0.0),
        }
        baseline: dict[str, tuple[float, float]] = {}

        for tier_index, tier in enumerate(GRAPHICS_TIER_VALUES):
            self.game.set_graphics_tier(tier)
            # Collision is world-space: representative viewport zoom changes
            # must not alter the final contact point either.
            self.game.view_zoom = (0.7, 1.0, 1.4)[tier_index]
            for direction, (dx, dy) in directions.items():
                with self.subTest(tier=tier, direction=direction):
                    x, y = self._walk_until_blocked(dx, dy)
                    if dx < 0.0:
                        self.assertGreaterEqual(x, self.ROOM_MIN)
                        self.assertLessEqual(
                            x + ACTOR_GROUND_DEPTH_OFFSET - self.ROOM_MIN,
                            ACTOR_GROUND_DEPTH_OFFSET + self.STEP + 1e-9,
                        )
                    elif dx > 0.0:
                        expected_x = (
                            self.ROOM_MAX - ACTOR_MOVE_COLLISION_RADIUS
                        )
                        self.assertGreaterEqual(
                            x,
                            expected_x - self.STEP - 1e-9,
                        )
                        self.assertLess(x, expected_x + 1e-9)
                    else:
                        self.assertAlmostEqual(x, 32.0)
                    if dy < 0.0:
                        self.assertGreaterEqual(y, self.ROOM_MIN)
                        self.assertLessEqual(
                            y + ACTOR_GROUND_DEPTH_OFFSET - self.ROOM_MIN,
                            ACTOR_GROUND_DEPTH_OFFSET + self.STEP + 1e-9,
                        )
                    elif dy > 0.0:
                        expected_y = (
                            self.ROOM_MAX - ACTOR_MOVE_COLLISION_RADIUS
                        )
                        self.assertGreaterEqual(
                            y,
                            expected_y - self.STEP - 1e-9,
                        )
                        self.assertLess(y, expected_y + 1e-9)
                    else:
                        self.assertAlmostEqual(y, 32.0)
                    self.assertTrue(self.game.dungeon.is_floor(x, y))

                    endpoint = (x, y)
                    if direction in baseline:
                        self.assertEqual(endpoint, baseline[direction])
                    else:
                        baseline[direction] = endpoint

                    # Repeated input cannot carry the logical actor point into
                    # the wall, including at the room's diagonal north corner.
                    for _ in range(8):
                        self.game.move_actor(
                            self.game.player,
                            dx * self.STEP,
                            dy * self.STEP,
                        )
                    self.assertEqual(
                        (self.game.player.x, self.game.player.y),
                        endpoint,
                    )

    def test_relief_is_player_wall_only_and_preserves_other_clearance(self) -> None:
        dungeon = self.game.dungeon

        # The generic square probe remains symmetric. Player movement opts into
        # the visual-depth relief at the one movement seam.
        self.assertTrue(
            dungeon.blocked_for_radius(
                self.ROOM_MIN + self.STEP,
                32.0,
                ACTOR_MOVE_COLLISION_RADIUS,
                block_stairs=True,
            )
        )
        self.assertFalse(
            dungeon.blocked_for_radius(
                self.ROOM_MIN + self.STEP,
                32.0,
                ACTOR_MOVE_COLLISION_RADIUS,
                block_stairs=True,
                wall_depth_relief=ACTOR_GROUND_DEPTH_OFFSET,
            )
        )

        # Screen-south approaches keep the established full radius.
        for direction, (dx, dy) in {
            "south": (1.0, 1.0),
            "south-east": (1.0, 0.0),
            "south-west": (0.0, 1.0),
        }.items():
            with self.subTest(direction=direction):
                x, y = self._walk_until_blocked(dx, dy)
                expected = (
                    self.ROOM_MAX - ACTOR_MOVE_COLLISION_RADIUS
                )
                if dx > 0.0:
                    self.assertLess(x, expected + 1e-9)
                    self.assertGreaterEqual(x, expected - self.STEP - 1e-9)
                if dy > 0.0:
                    self.assertLess(y, expected + 1e-9)
                    self.assertGreaterEqual(y, expected - self.STEP - 1e-9)

        # Closed doors are not wall art and retain their full collision depth.
        self.game.dungeon.tiles[32][self.ROOM_MIN - 1] = Tile.CLOSED_DOOR
        x, y = self._walk_until_blocked(0.0, -1.0)
        expected_door_y = self.ROOM_MIN + ACTOR_MOVE_COLLISION_RADIUS
        self.assertAlmostEqual(x, 32.0)
        self.assertGreaterEqual(y, expected_door_y - self.STEP - 1e-9)
        self.assertLess(y, expected_door_y + self.STEP + 1e-9)

        # The existing radius still fits comfortably in a one-tile corridor.
        for corridor_y in range(self.ROOM_MIN, self.ROOM_MAX):
            dungeon.tiles[29][corridor_y] = Tile.WALL
            dungeon.tiles[30][corridor_y] = Tile.FLOOR
            dungeon.tiles[31][corridor_y] = Tile.WALL
        self.assertFalse(
            dungeon.blocked_for_radius(
                30.5,
                32.0,
                ACTOR_MOVE_COLLISION_RADIUS,
                block_stairs=True,
                wall_depth_relief=ACTOR_GROUND_DEPTH_OFFSET,
            )
        )

    def test_visible_feet_depth_is_limited_to_relieved_wall_contact(self) -> None:
        player = self.game.player
        dungeon = self.game.dungeon

        for direction, (dx, dy) in {
            "north": (-1.0, -1.0),
            "north-east": (0.0, -1.0),
            "north-west": (-1.0, 0.0),
        }.items():
            with self.subTest(direction=direction):
                x, y = self._walk_until_blocked(dx, dy)
                self.assertTrue(
                    dungeon.footprint_wall_depth_relief_tiles(
                        x,
                        y,
                        ACTOR_MOVE_COLLISION_RADIUS,
                        ACTOR_GROUND_DEPTH_OFFSET,
                    )
                )
                contact_walls = dungeon.footprint_wall_depth_relief_tiles(
                    x,
                    y,
                    ACTOR_MOVE_COLLISION_RADIUS,
                    ACTOR_GROUND_DEPTH_OFFSET,
                )
                contacted_wall_depth = max(
                    wx + wy + 1.02 for wx, wy in contact_walls
                )
                self.assertEqual(
                    self.game._player_painter_depth(player),
                    max(
                        x + y,
                        math.nextafter(contacted_wall_depth, math.inf),
                    ),
                )

        # Open ground and the three opposite approaches retain their exact
        # historical logical depth, limiting the painter change to the seam
        # introduced by north-wall collision relief.
        player.x = player.y = 32.0
        self.assertEqual(self.game._player_painter_depth(player), 64.0)
        for direction, (dx, dy) in {
            "south": (1.0, 1.0),
            "south-east": (1.0, 0.0),
            "south-west": (0.0, 1.0),
        }.items():
            with self.subTest(direction=direction):
                x, y = self._walk_until_blocked(dx, dy)
                self.assertFalse(
                    dungeon.footprint_wall_depth_relief_tiles(
                        x,
                        y,
                        ACTOR_MOVE_COLLISION_RADIUS,
                        ACTOR_GROUND_DEPTH_OFFSET,
                    )
                )
                self.assertAlmostEqual(
                    self.game._player_painter_depth(player),
                    x + y,
                )

        # At the east/west room corners one footprint corner uses north-wall
        # relief, but that contacted wall is already behind the logical player
        # depth. Do not apply a blanket feet offset: it would reorder the
        # adjacent genuine foreground wall and weaken its established ghosting.
        for direction, (dx, dy) in {
            "east": (1.0, -1.0),
            "west": (-1.0, 1.0),
        }.items():
            with self.subTest(direction=direction):
                x, y = self._walk_until_blocked(dx, dy)
                self.assertTrue(
                    dungeon.footprint_wall_depth_relief_tiles(
                        x,
                        y,
                        ACTOR_MOVE_COLLISION_RADIUS,
                        ACTOR_GROUND_DEPTH_OFFSET,
                    )
                )
                self.assertEqual(
                    self.game._player_painter_depth(player),
                    x + y,
                )

    def test_player_stays_visible_while_sliding_across_north_wall_edges(
        self,
    ) -> None:
        self._prepare_large_render_room()
        game = self.game
        player = game.player
        for collection_name in (
            "items",
            "traps",
            "shrines",
            "secrets",
            "familiars",
            "projectiles",
            "slashes",
            "impact_effects",
        ):
            getattr(game, collection_name).clear()

        # Probe both exposed face orientations, both sides of the next
        # wall-tile seam, and the shared diagonal corner. The old logical-depth
        # sort lost opaque body pixels near .0/.9 along either wall edge.
        contacts = {
            "north-west-start": (self.ROOM_MIN + self.STEP, 34.0),
            "north-west-end": (self.ROOM_MIN + self.STEP, 34.9),
            "north-east-start": (34.0, self.ROOM_MIN + self.STEP),
            "north-east-end": (34.9, self.ROOM_MIN + self.STEP),
            "north-corner": (
                self.ROOM_MIN + self.STEP,
                self.ROOM_MIN + self.STEP,
            ),
        }

        for tier_index, tier in enumerate(GRAPHICS_TIER_VALUES):
            game.set_graphics_tier(tier)
            self._activate_native_zoom((1.0, 1.0, 1.4)[tier_index])
            for contact, (x, y) in contacts.items():
                self.assertFalse(
                    game.dungeon.blocked_for_radius(
                        x,
                        y,
                        ACTOR_MOVE_COLLISION_RADIUS,
                        block_stairs=True,
                        wall_depth_relief=ACTOR_GROUND_DEPTH_OFFSET,
                    )
                )
                self.assertTrue(
                    game.dungeon.footprint_wall_depth_relief_tiles(
                        x,
                        y,
                        ACTOR_MOVE_COLLISION_RADIUS,
                        ACTOR_GROUND_DEPTH_OFFSET,
                    )
                )
                for animation_frame in range(3):
                    with self.subTest(
                        tier=tier,
                        contact=contact,
                        animation_frame=animation_frame,
                    ):
                        player.x, player.y = x, y
                        player.moving = True
                        player.anim_time = animation_frame * 0.09
                        game.snap_camera_to_player()
                        game._frame_cache = {}
                        game._actor_ghost_weights = {}
                        game.screen.fill((6, 6, 9))
                        blit = self._draw_world_capturing_player_blit()

                        matched, opaque = self._opaque_player_pixel_counts(blit)
                        self.assertGreater(opaque, 0)
                        self.assertEqual(matched, opaque)
                        # Full visibility comes from correct painter order, not
                        # from weakening the through-wall ghost thresholds.
                        self.assertEqual(game._frame_actor_ghost_blits, 0)

    def test_north_contact_keeps_genuine_foreground_wall_ghosting(self) -> None:
        self._prepare_large_render_room()
        game = self.game
        player = game.player
        player.x = self.ROOM_MIN + self.STEP
        player.y = 34.0
        # This diagonal wall is genuinely screen-south of the contacted north
        # face and overlaps the player body, so it must still paint afterward
        # and use the established silhouette rather than being reordered.
        foreground_wall = (31, 35)
        game.dungeon.tiles[foreground_wall[0]][foreground_wall[1]] = Tile.WALL
        game.revealed_tiles.add(foreground_wall)
        game.snap_camera_to_player()
        game._frame_cache = {}
        game._actor_ghost_weights = {}
        for _ in range(8):
            game.screen.fill((6, 6, 9))
            game.draw_world_objects()

        self.assertTrue(
            game.dungeon.footprint_wall_depth_relief_tiles(
                player.x,
                player.y,
                ACTOR_MOVE_COLLISION_RADIUS,
                ACTOR_GROUND_DEPTH_OFFSET,
            )
        )
        self.assertEqual(game._frame_actor_ghost_blits, 1)


if __name__ == "__main__":
    unittest.main()
