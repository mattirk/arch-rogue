"""Regression tests for stuck enemies (bar props, doorways, pack jams).

Three field reports: enemies wedged inside bar furnishings (spawned before the
solid boxes were placed, or nav giving up on the furnishing tile's walkable
inset strip); two enemies side by side both wedging into a one-tile doorway
(separation fan-out fighting the routed direction); and rear enemies stalled
behind a packmate so only the closest one ever attacks (the distance field
doesn't know about bodies — the stalled step now slides sideways).
"""

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

from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game
from arch_rogue.models import Enemy, Tile


def _make_enemy(
    x: float,
    y: float,
    *,
    kind: str = "melee",
    role: str = "bruiser",
    attack_range: float = 1.2,
    speed: float = 2.0,
    aggro_range: float = 24.0,
) -> Enemy:
    enemy = Enemy(
        "Test Dummy",
        kind,
        x,
        y,
        200,
        200,
        speed,
        6,
        12,
        attack_range,
        1.0,
        aggro_range=aggro_range,
    )
    enemy.role = role
    return enemy


class EnemyUnstuckTests(unittest.TestCase):
    def make_game(self, tmpdir: str, seed: int = 515) -> Game:
        game = Game(
            screen_size=(960, 600),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.rng.seed(seed)
        game.restart(ARCHETYPES[0])
        game.story_intro_pending = False
        game.close_active_cutscene()
        return game

    def make_game_with_furnishings(self, tmpdir: str) -> Game:
        """A game whose floor generated at least one solid furnishing box."""
        for seed in range(600, 700):
            game = self.make_game(tmpdir, seed=seed)
            if game.dungeon.solid_furnishing_boxes:
                return game
        self.fail("no seed in range produced solid furnishings")

    def _simulate(self, game: Game, seconds: float) -> None:
        dt = 1.0 / 60.0
        for _ in range(int(seconds / dt)):
            game.update_enemies(dt)

    def test_spawned_enemy_is_relocated_out_of_furnishing_box(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game_with_furnishings(tmpdir)
            ax, ay, bx, by = game.dungeon.solid_furnishing_boxes[0]
            trapped = _make_enemy((ax + bx) / 2.0, (ay + by) / 2.0)
            game.enemies.append(trapped)
            self.assertTrue(
                game.dungeon.blocked_for_radius(trapped.x, trapped.y, 0.27)
            )
            game._relocate_enemies_off_furnishings()
            self.assertFalse(
                game.dungeon.blocked_for_radius(trapped.x, trapped.y, 0.27),
                f"enemy still blocked at {trapped.x:.2f},{trapped.y:.2f}",
            )

    def test_nav_routes_off_a_furnishing_tile_strip(self) -> None:
        # Standing on a furnishing tile's walkable inset strip, the tile has
        # no field cost; nav must still route to a costed neighbor instead of
        # returning None (which left greedy movement grinding into the prop).
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game_with_furnishings(tmpdir)
            tile = next(iter(game.dungeon.solid_furnishing_tiles))
            room = game.dungeon.room_at(tile[0] + 0.5, tile[1] + 0.5)
            self.assertIsNotNone(room)
            assert room is not None
            # Stand the player on a different free tile of the same room (a
            # small hall's center can be the furnishing tile itself).
            for ty in range(room.y, room.y + room.h):
                for tx in range(room.x, room.x + room.w):
                    if (tx, ty) == tile:
                        continue
                    if (tx, ty) in game.dungeon.solid_furnishing_tiles:
                        continue
                    if abs(tx - tile[0]) + abs(ty - tile[1]) < 2:
                        continue
                    if not game.dungeon.blocked_for_radius(
                        tx + 0.5, ty + 0.5, 0.27
                    ):
                        game.player.x = tx + 0.5
                        game.player.y = ty + 0.5
                        break
                else:
                    continue
                break
            enemy = _make_enemy(tile[0] + 0.5, tile[1] + 0.5)
            game.enemies = [enemy]
            direction = game._enemy_nav_direction(enemy, game.player)
            self.assertIsNotNone(direction)
            assert direction is not None
            self.assertGreater(math.hypot(*direction), 0.9)

    def test_side_by_side_pair_funnels_through_a_doorway(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, seed=808)
            room = max(game.dungeon.rooms[1:-1], key=lambda r: r.w * r.h)
            self.assertGreaterEqual(room.w, 7)
            self.assertGreaterEqual(room.h, 5)
            # Carve a wall across the room with a single one-tile opening.
            wall_x = room.x + room.w // 2
            gap_y = room.y + room.h // 2
            for ty in range(room.y, room.y + room.h):
                game.dungeon.tiles[wall_x][ty] = (
                    Tile.FLOOR if ty == gap_y else Tile.WALL
                )
            game.dungeon.refresh_solid_furnishing_tiles()
            game.player.x = wall_x - 2.5
            game.player.y = gap_y + 0.5
            first = _make_enemy(wall_x + 2.5, gap_y - 0.5)
            second = _make_enemy(wall_x + 2.5, gap_y + 1.5)
            game.enemies = [first, second]
            game.ambush_bells = []
            self._simulate(game, 8.0)
            for label, enemy in (("first", first), ("second", second)):
                distance = math.hypot(
                    enemy.x - game.player.x, enemy.y - game.player.y
                )
                self.assertLessEqual(
                    distance,
                    enemy.attack_range + 0.35,
                    f"{label} enemy never made it through the doorway "
                    f"(at {enemy.x:.2f},{enemy.y:.2f}, distance {distance:.2f})",
                )

    def test_rear_enemy_flanks_a_blocking_packmate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, seed=909)
            room = max(game.dungeon.rooms[1:-1], key=lambda r: r.w * r.h)
            cx = room.x + room.w // 2 + 0.5
            cy = room.y + room.h // 2 + 0.5
            game.player.x = cx - 2.0
            game.player.y = cy
            # A slow blocker parked at melee range, a faster enemy directly
            # behind it on the same line.
            blocker = _make_enemy(cx - 0.9, cy, speed=0.4)
            rear = _make_enemy(cx + 1.6, cy, speed=2.4)
            game.enemies = [blocker, rear]
            game.ambush_bells = []
            self._simulate(game, 6.0)
            rear_distance = math.hypot(
                rear.x - game.player.x, rear.y - game.player.y
            )
            self.assertLessEqual(
                rear_distance,
                rear.attack_range + 0.35,
                f"rear enemy stayed stuck behind the blocker "
                f"(at {rear.x:.2f},{rear.y:.2f}, distance {rear_distance:.2f})",
            )


if __name__ == "__main__":
    unittest.main()
