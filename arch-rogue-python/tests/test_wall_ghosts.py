from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame

from arch_rogue.constants import GRAPHICS_TIER_VALUES
from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game
from arch_rogue.models import Familiar, Tile


class WallGhostTests(unittest.TestCase):
    """Players and enemies faintly shine through occluding walls.

    After the depth-sorted world pass, each player/enemy sprite overlapped by
    a wall or door drawn after it is re-blitted in place at low alpha, so a
    barely-visible silhouette survives behind the tall isometric wall art.
    """

    def make_game(self, tmpdir: str, seed: int = 4901) -> Game:
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

    def test_ghost_blits_when_wall_drawn_in_front_of_actors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            px, py = int(game.player.x), int(game.player.y)
            # A wall one tile screen-south of the player draws after them in
            # painter order and its tall prism swallows the sprite.
            self.assertTrue(game.dungeon.in_bounds(px + 1, py + 1))
            game.dungeon.tiles[px + 1][py + 1] = Tile.WALL
            game.revealed_tiles.add((px + 1, py + 1))
            # Park an enemy beside the player behind its own wall so the enemy
            # path is exercised too (adjacent, so sight and LOS both hold).
            if game.enemies:
                enemy = game.enemies[0]
                enemy.x = px + 1.5
                enemy.y = py + 0.5
                if game.dungeon.in_bounds(px + 2, py + 1):
                    game.dungeon.tiles[px + 2][py + 1] = Tile.WALL
                    game.revealed_tiles.add((px + 2, py + 1))

            game.draw_world_objects()
            self.assertGreaterEqual(game._frame_actor_ghost_blits, 1)

    def test_no_ghost_blits_in_open_ground(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            px, py = int(game.player.x), int(game.player.y)
            # Carve every wall/door near the player so nothing drawn after the
            # player overlaps the sprite; the ghost pass must stay idle.
            game.enemies.clear()
            for tx in range(px - 5, px + 6):
                for ty in range(py - 5, py + 6):
                    if game.dungeon.in_bounds(tx, ty):
                        game.dungeon.tiles[tx][ty] = Tile.FLOOR

            game.draw_world_objects()
            self.assertEqual(game._frame_actor_ghost_blits, 0)

    def test_closed_and_open_doors_keep_player_visible_when_occluding(self) -> None:
        for door_tile in (Tile.CLOSED_DOOR, Tile.OPEN_DOOR):
            with (
                self.subTest(door_tile=door_tile),
                tempfile.TemporaryDirectory() as tmpdir,
            ):
                game = self.make_game(tmpdir)
                px, py = int(game.player.x), int(game.player.y)
                game.enemies.clear()
                for tx in range(px - 5, px + 6):
                    for ty in range(py - 5, py + 6):
                        if game.dungeon.in_bounds(tx, ty):
                            game.dungeon.tiles[tx][ty] = Tile.FLOOR

                self.assertTrue(game.dungeon.in_bounds(px + 1, py + 1))
                game.dungeon.tiles[px + 1][py + 1] = door_tile
                game.revealed_tiles.add((px + 1, py + 1))

                game.draw_world_objects()
                self.assertEqual(game._frame_actor_ghost_blits, 1)

    def test_player_shines_through_every_open_door_crossing(self) -> None:
        for graphics_tier in GRAPHICS_TIER_VALUES:
            for axis, direction in (("y", "north"), ("x", "west")):
                with (
                    self.subTest(graphics_tier=graphics_tier, axis=axis),
                    tempfile.TemporaryDirectory() as tmpdir,
                ):
                    game = self.make_game(tmpdir)
                    game.set_graphics_tier(graphics_tier)
                    game.enemies.clear()
                    game.familiars.clear()
                    px, py = int(game.player.x), int(game.player.y)
                    door_x, door_y = px + 2, py + 2
                    for tx in range(px - 7, px + 12):
                        for ty in range(py - 7, py + 12):
                            if game.dungeon.in_bounds(tx, ty):
                                game.dungeon.tiles[tx][ty] = Tile.FLOOR
                                game.revealed_tiles.add((tx, ty))

                    game.dungeon.tiles[door_x][door_y] = Tile.CLOSED_DOOR
                    game.revealed_tiles.add((door_x, door_y))

                    def place_player(progress: float) -> None:
                        game.player.x = (
                            door_x + 0.5 if axis == "y" else door_x + progress
                        )
                        game.player.y = (
                            door_y + progress if axis == "y" else door_y + 0.5
                        )
                        game.player.moving = True
                        game.snap_camera_to_player()
                        game._frame_cache = {}

                    # A shut door cannot be traversed and must not activate the
                    # opened-passage override at the same painter-depth seam.
                    place_player(0.5)
                    game._actor_ghost_weights = {}
                    with patch.object(
                        game, "door_render_direction", return_value=direction
                    ):
                        game.draw_world_objects()
                    self.assertEqual(game._frame_actor_ghost_blits, 0)

                    self.assertTrue(game.dungeon.open_door(door_x, door_y))
                    self.assertEqual(
                        game.dungeon.tiles[door_x][door_y], Tile.OPEN_DOOR
                    )

                    with patch.object(
                        game, "door_render_direction", return_value=direction
                    ):
                        for travel in ("northbound", "southbound"):
                            game._actor_ghost_weights = {}
                            steps = (
                                range(10, -1, -1)
                                if travel == "northbound"
                                else range(11)
                            )
                            crossing_states: list[int] = []
                            for frame, step in enumerate(steps):
                                progress = step / 10.0
                                place_player(progress)
                                game.player.anim_time = frame * 0.08
                                game.draw_world_objects()
                                if progress <= 0.5:
                                    crossing_states.append(
                                        game._frame_actor_ghost_blits
                                    )
                            self.assertEqual(
                                crossing_states,
                                [1] * len(crossing_states),
                                (
                                    f"{graphics_tier} {axis}-axis {travel} "
                                    f"lost the player in the opened doorway"
                                ),
                            )

                        # Just screen-south of the painter seam the player
                        # naturally draws over the door and needs no override.
                        game._actor_ghost_weights = {}
                        place_player(0.6)
                        game.draw_world_objects()
                        self.assertEqual(game._frame_actor_ghost_blits, 0)

    def test_familiar_ghosts_through_walls_like_other_actors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            px, py = int(game.player.x), int(game.player.y)
            # Open ground everywhere near the player, so the familiar's own
            # wall is the only occluder and the single ghost is attributable
            # to it (the wall sits too far east to overlap the player).
            game.enemies.clear()
            for tx in range(px - 5, px + 6):
                for ty in range(py - 5, py + 6):
                    if game.dungeon.in_bounds(tx, ty):
                        game.dungeon.tiles[tx][ty] = Tile.FLOOR
            game.familiars.append(
                Familiar(
                    px + 2.5,
                    py + 0.5,
                    max_hp=10,
                    hp=10,
                    damage=1,
                    speed=3.0,
                    attack_range=1.0,
                    attack_cooldown=1.0,
                )
            )
            self.assertTrue(game.dungeon.in_bounds(px + 3, py + 1))
            game.dungeon.tiles[px + 3][py + 1] = Tile.WALL
            game.revealed_tiles.add((px + 3, py + 1))

            game.draw_world_objects()
            self.assertEqual(game._frame_actor_ghost_blits, 1)

    def test_ghost_pass_only_triggers_on_overlapping_front_occluders(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            sprite = pygame.Surface((40, 60), pygame.SRCALPHA)
            sprite.fill((200, 180, 120, 255))
            rect = sprite.get_rect(topleft=(100, 100))
            marker = object()
            actor = [(5.0, marker, sprite, rect)]
            overlapping = pygame.Rect(90, 90, 200, 200)
            distant = pygame.Rect(1000, 1000, 50, 50)

            def fresh_pass(occluders: list) -> int:
                # Each case is judged in isolation: drop the per-actor eased
                # weight carried between frames.
                game._actor_ghost_weights = {}
                return game._draw_actor_wall_ghosts(actor, occluders)

            # A wall drawn before the actor never covers it: no ghost.
            self.assertEqual(fresh_pass([(1.0, overlapping)]), 0)
            # A wall drawn after the actor and covering it ghosts once.
            self.assertEqual(fresh_pass([(9.0, overlapping)]), 1)
            # A wall drawn after the actor but elsewhere on screen: no ghost.
            self.assertEqual(fresh_pass([(9.0, distant)]), 0)
            # A wall barely after the actor in depth is a side wall flipping
            # across the painter boundary — suppressed even at full overlap,
            # so crossing a wall's diagonal never pops the effect.
            self.assertEqual(fresh_pass([(5.1, overlapping)]), 0)
            # A far-front wall that only grazes a corner of the sprite rect
            # (about 1% coverage) stays suppressed, so animation-frame rect
            # jitter at the graze boundary never flashes the aura.
            graze = pygame.Rect(135, 155, 200, 200)
            self.assertEqual(fresh_pass([(9.0, graze)]), 0)
            # The eased weight decays smoothly instead of cutting out: after
            # sustained full occlusion, one no-occluder frame still ghosts
            # (fading), and the weight then drains over the following frames.
            game._actor_ghost_weights = {}
            for _ in range(12):
                game._draw_actor_wall_ghosts(actor, [(9.0, overlapping)])
            self.assertEqual(game._draw_actor_wall_ghosts(actor, []), 1)
            for _ in range(24):
                game._draw_actor_wall_ghosts(actor, [])
            self.assertEqual(game._draw_actor_wall_ghosts(actor, []), 0)

    def _stage_open_ground_with_wall(
        self, game: Game
    ) -> tuple[int, int]:
        """Carve open floor around the player and plant one revealed wall
        two tiles screen-south of the spawn tile. Returns the wall tile."""

        px, py = int(game.player.x), int(game.player.y)
        wx, wy = px + 2, py + 2
        game.enemies.clear()
        for tx in range(px - 5, px + 9):
            for ty in range(py - 5, py + 9):
                if game.dungeon.in_bounds(tx, ty):
                    game.dungeon.tiles[tx][ty] = Tile.FLOOR
        self.assertTrue(game.dungeon.in_bounds(wx, wy))
        game.dungeon.tiles[wx][wy] = Tile.WALL
        game.revealed_tiles.add((wx, wy))
        return wx, wy

    def _spy_on_aura(self, game: Game) -> list[bool]:
        """Record whether each ghost draw actually produced an aura."""

        seen: list[bool] = []
        original = game._actor_ghost_aura

        def spy(width: int, height: int, gain: float = 1.0):
            result = original(width, height, gain)
            seen.append(result is not None)
            return result

        game._actor_ghost_aura = spy  # type: ignore[assignment]
        return seen

    def _draw_at_depth(
        self, game: Game, wx: int, wy: int, d: float
    ) -> None:
        """Place the player d diagonal rows screen-north of wall (wx, wy),
        column-aligned, and draw one world frame."""

        game.player.x = wx + 0.5 - d / 2.0
        game.player.y = wy + 0.5 - d / 2.0
        game.snap_camera_to_player()
        game._frame_cache = {}
        game.draw_world_objects()

    def test_approach_from_north_fades_in_once_without_flicker(self) -> None:
        # Regression: the binary trigger flashed the aura on/off while
        # walking toward a wall screen-south of the actor. The occlusion
        # weight must activate exactly once along the approach and never
        # drop back out.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            wx, wy = self._stage_open_ground_with_wall(game)
            aura_seen = self._spy_on_aura(game)
            ghost_states: list[int] = []
            aura_states: list[int] = []
            steps = [5.0 - index * 0.1 for index in range(41)]  # 5.0 -> 1.0
            for d in steps:
                aura_seen.clear()
                self._draw_at_depth(game, wx, wy, d)
                ghost_states.append(1 if game._frame_actor_ghost_blits else 0)
                aura_states.append(1 if any(aura_seen) else 0)

            for states in (ghost_states, aura_states):
                self.assertEqual(states[0], 0)
                self.assertEqual(states[-1], 1)
                transitions = sum(
                    1
                    for previous, current in zip(states, states[1:])
                    if previous != current
                )
                self.assertEqual(transitions, 1)

    def test_graze_band_stays_quiet_across_animation_frames(self) -> None:
        # Regression: right where a wall south of the actor first grazes the
        # sprite rect, per-frame animation jitter used to toggle the overlap
        # and strobe the aura. In the graze band the aura must stay off for
        # every animation frame; deep behind the wall it must stay on.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            wx, wy = self._stage_open_ground_with_wall(game)
            aura_seen = self._spy_on_aura(game)
            game.player.moving = True
            for d, expected in ((4.45, False), (1.4, True)):
                results = []
                for frame in range(12):
                    game.player.anim_time = frame * 0.09
                    aura_seen.clear()
                    self._draw_at_depth(game, wx, wy, d)
                    results.append(any(aura_seen))
                self.assertEqual(
                    results,
                    [expected] * len(results),
                    f"aura unstable at approach depth {d}: {results}",
                )

    def test_ghost_aura_is_a_cached_radial_ellipse(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            # Same quantized bucket returns the identical cached surface.
            first = game._actor_ghost_aura(120, 200)
            second = game._actor_ghost_aura(125, 205)
            self.assertIs(first, second)
            other = game._actor_ghost_aura(200, 120)
            self.assertIsNot(other, first)
            self.assertEqual(first.get_size(), (112, 192))

            # The aura is an additive glow: black corners add no light, the
            # core is the brightest point, and the rim fades toward black.
            width, height = first.get_size()
            self.assertEqual(first.get_at((0, 0))[:3], (0, 0, 0))
            self.assertEqual(
                first.get_at((width - 1, height - 1))[:3], (0, 0, 0)
            )
            core = sum(first.get_at((width // 2, height // 2))[:3])
            rim = sum(first.get_at((width // 2, 4))[:3])
            self.assertGreater(core, rim)
            self.assertGreater(core, 0)

            # Occlusion-weight fade: a half-gain aura is dimmer than full
            # gain, and zero gain draws nothing at all.
            dimmed = game._actor_ghost_aura(120, 200, 0.5)
            self.assertIsNotNone(dimmed)
            self.assertIsNot(dimmed, first)
            dim_core = sum(dimmed.get_at((width // 2, height // 2))[:3])
            self.assertLess(dim_core, core)
            self.assertGreater(dim_core, 0)
            self.assertIsNone(game._actor_ghost_aura(120, 200, 0.0))


if __name__ == "__main__":
    unittest.main()
