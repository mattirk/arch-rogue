from __future__ import annotations

import math
import os
import random
import sys
import tempfile
import unittest
from collections import deque
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from arch_rogue.constants import DUNGEON_DEPTH, PLAYER_HIT_RADIUS
from arch_rogue.content import ARCHETYPES
from arch_rogue.dungeon import BOSS_ARENA_MIN_H, BOSS_ARENA_MIN_W, Dungeon, Tile
from arch_rogue.game import Game


class BigBossesTests(unittest.TestCase):
    def tearDown(self) -> None:
        pass

    def make_game(self, tmpdir: str, seed: int = 2323) -> Game:
        game = Game(
            screen_size=(820, 540),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.meta_progress = game.default_meta_progress()
        game.run_history = []
        game.rng.seed(seed)
        game.restart(ARCHETYPES[0])
        if game.story_intro_pending:
            self.assertTrue(game.choose_story_relic_path(0))
        game.active_cutscene = None
        return game

    def populate_floor(self, game: Game, depth: int) -> None:
        game.current_depth = depth
        game.apply_floor_plan_for_current_depth()
        game.dungeon = Dungeon(
            game.rng, boss_arena=game.current_floor_needs_boss_arena()
        )
        game.enemies.clear()
        game.items.clear()
        game.traps.clear()
        game.shrines.clear()
        game.secrets.clear()
        game.boss_engaged = False
        game.boss_sealed_tiles = []
        game.boss_sealed_room_index = None
        game._populate_dungeon()

    def test_floor_and_final_bosses_are_four_tile_and_harder(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            # Floor guardian on a boss floor.
            self.populate_floor(game, 3)
            floor_bosses = [e for e in game.enemies if e.role == "floor_boss"]
            self.assertEqual(len(floor_bosses), 1)
            fb = floor_bosses[0]
            self.assertEqual(fb.size, 2)
            self.assertEqual(game.enemy_hit_radius(fb), 0.92)
            self.assertGreater(fb.max_hp, 200)
            self.assertGreater(fb.damage, 20)
            self.assertGreaterEqual(fb.attack_range, 1.85)
            self.assertTrue(fb.is_boss_encounter)

            # Final gate tyrant.
            self.populate_floor(game, DUNGEON_DEPTH)
            final = [e for e in game.enemies if e.kind == "boss"]
            self.assertEqual(len(final), 1)
            tyrant = final[0]
            self.assertEqual(tyrant.size, 2)
            self.assertGreater(tyrant.max_hp, 600)
            self.assertGreater(tyrant.damage, 30)
            self.assertTrue(tyrant.is_boss_encounter)

    def test_melee_reach_extends_for_big_boss(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.populate_floor(game, 3)
            fb = next(e for e in game.enemies if e.role == "floor_boss")
            # Stand just outside the default melee range but within the boss's
            # extended reach (past its large silhouette). Face the boss.
            game.player.facing_x = 1.0
            game.player.facing_y = 0.0
            game.player.x = fb.x - 2.0
            game.player.y = fb.y
            hit = game.enemy_in_melee_arc()
            self.assertIs(hit, fb)

    def test_doors_seal_on_engage_and_reopen_on_death(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.populate_floor(game, 3)
            fb = next(e for e in game.enemies if e.role == "floor_boss")
            room = game.dungeon.room_at(fb.x, fb.y)
            self.assertIsNotNone(room)
            assert room is not None
            self.assertGreaterEqual(room.w, BOSS_ARENA_MIN_W)
            self.assertGreaterEqual(room.h, BOSS_ARENA_MIN_H)
            # Player outside the boss room: no seal yet.
            game.player.x = game.dungeon.rooms[0].center[0] + 0.5
            game.player.y = game.dungeon.rooms[0].center[1] + 0.5
            game.update_boss_encounter()
            self.assertFalse(game.boss_engaged)

            # Step into the boss room: doors seal.
            cx, cy = room.center
            game.player.x = cx + 0.5
            game.player.y = cy + 0.5
            game.update_boss_encounter()
            self.assertTrue(game.boss_engaged)
            self.assertGreater(len(game.boss_sealed_tiles), 0)
            for x, y, _tile in game.boss_sealed_tiles:
                self.assertEqual(game.dungeon.tiles[x][y], Tile.CLOSED_DOOR)

            # Kill the boss: doors restore.
            game.kill_enemy(fb)
            game.update_boss_encounter()
            self.assertFalse(game.boss_engaged)
            self.assertEqual(len(game.boss_sealed_tiles), 0)

    def test_boss_arena_seals_all_corridor_exits(self) -> None:
        for seed in (0, 1, 2, 9, 14):
            dungeon = Dungeon(random.Random(seed), boss_arena=True)
            room = dungeon.rooms[-1]
            sealed = dungeon.seal_room_openings(room)
            self.assertGreater(len(sealed), 0)
            perimeter = dungeon._room_perimeter(room)
            self.assertLess(len({(x, y) for x, y, _tile in sealed}), len(perimeter))

            start = room.center
            reachable = {start}
            frontier: deque[tuple[int, int]] = deque([start])
            escaped = False
            while frontier:
                x, y = frontier.popleft()
                if not (
                    room.x <= x < room.x + room.w and room.y <= y < room.y + room.h
                ):
                    escaped = True
                    break
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if (nx, ny) in reachable or not dungeon.in_bounds(nx, ny):
                        continue
                    if dungeon.tiles[nx][ny] in (Tile.WALL, Tile.CLOSED_DOOR):
                        continue
                    reachable.add((nx, ny))
                    frontier.append((nx, ny))
            self.assertFalse(escaped, f"boss arena leaked on seed {seed}")

    def test_boss_seal_repositions_player_from_doorway(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.populate_floor(game, 3)
            fb = next(e for e in game.enemies if e.role == "floor_boss")
            room = game.dungeon.room_at(fb.x, fb.y)
            self.assertIsNotNone(room)
            assert room is not None
            doorways = game.dungeon._door_candidates_for_room(room)
            self.assertGreater(len(doorways), 0)
            door_x, door_y = doorways[0]
            game.player.x = door_x + 0.5
            game.player.y = door_y + 0.5
            self.assertFalse(
                game.dungeon.blocked_for_radius(
                    game.player.x, game.player.y, PLAYER_HIT_RADIUS
                )
            )

            game.update_boss_encounter()

            self.assertTrue(game.boss_engaged)
            self.assertEqual(game.dungeon.tiles[door_x][door_y], Tile.CLOSED_DOOR)
            sealed = {(x, y) for x, y, _tile in game.boss_sealed_tiles}
            self.assertNotIn((int(game.player.x), int(game.player.y)), sealed)
            self.assertFalse(
                game.dungeon.blocked_for_radius(
                    game.player.x, game.player.y, PLAYER_HIT_RADIUS
                )
            )
            self.assertGreaterEqual(
                math.hypot(game.player.x - fb.x, game.player.y - fb.y),
                game.boss_arena_player_clearance(fb),
            )

            perimeter = [
                (x, y)
                for x in range(room.x, room.x + room.w)
                for y in range(room.y, room.y + room.h)
                if x in (room.x, room.x + room.w - 1)
                or y in (room.y, room.y + room.h - 1)
            ]
            still_walkable_perimeter = [
                (x, y)
                for x, y in perimeter
                if (x, y) not in sealed and game.dungeon.tiles[x][y] == Tile.FLOOR
            ]
            self.assertGreater(len(still_walkable_perimeter), 0)

    def test_boss_cast_fires_three_bolt_fan(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.populate_floor(game, 3)
            fb = next(e for e in game.enemies if e.role == "floor_boss")
            room = game.dungeon.room_at(fb.x, fb.y)
            assert room is not None
            cx, cy = room.center
            # Place player at mid-range inside the room so the boss casts.
            game.player.x = cx - 3.0
            game.player.y = cy + 0.5
            game.update_boss_encounter()
            self.assertTrue(game.boss_engaged)
            game.enemies = [fb]  # isolate so only the boss acts
            before = len(game.projectiles)
            fb.attack_timer = 0.0
            game.update_enemies(0.05)
            # 4-tile bosses fire a 3-bolt fan.
            self.assertEqual(len(game.projectiles) - before, 3)

    def test_sealed_doors_cannot_be_opened_mid_fight(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.populate_floor(game, 3)
            fb = next(e for e in game.enemies if e.role == "floor_boss")
            room = game.dungeon.room_at(fb.x, fb.y)
            assert room is not None
            cx, cy = room.center
            game.player.x = cx + 0.5
            game.player.y = cy + 0.5
            game.update_boss_encounter()
            self.assertTrue(game.boss_engaged)
            self.assertGreater(len(game.boss_sealed_tiles), 0)
            # Stand on a sealed door tile and try to open it: it must stay closed.
            sx, sy, _orig = game.boss_sealed_tiles[0]
            game.player.x = sx + 0.5
            game.player.y = sy + 0.5
            self.assertEqual(game.dungeon.tiles[sx][sy], Tile.CLOSED_DOOR)
            self.assertFalse(game.open_nearby_door())
            self.assertEqual(game.dungeon.tiles[sx][sy], Tile.CLOSED_DOOR)
            # The interaction hint reports the seal, not "Open door".
            hint = game.current_interaction_hint()
            self.assertIsNotNone(hint)
            assert hint is not None
            self.assertEqual(hint[1], "Sealed by the boss")

    def test_challenge_miniboss_is_not_treated_as_boss_encounter(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.populate_floor(game, 4)
            # Challenge-room minibosses keep size 1 and do not lock doors.
            for enemy in game.enemies:
                if enemy.role == "challenge_boss":
                    self.assertEqual(enemy.size, 1)
                    self.assertFalse(enemy.is_boss_encounter)
                    return
            # If no challenge miniboss spawned this seed, the invariant still
            # holds vacuously; assert no enemy is mis-flagged.
            self.assertFalse(
                any(e.is_boss_encounter and e.size == 1 for e in game.enemies)
            )

    def test_enemy_size_field_loads_from_old_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            self.make_game(tmpdir)
            # Simulate an old save dict that omits the new `size` field.
            old_enemy = {
                "name": "Ghoul",
                "kind": "melee",
                "x": 5.5,
                "y": 6.5,
                "max_hp": 30,
                "hp": 30,
                "speed": 1.5,
                "damage": 8,
                "xp": 18,
                "attack_range": 1.0,
                "attack_cooldown": 0.9,
            }
            from arch_rogue.models import Enemy

            enemy = Enemy(**old_enemy)
            self.assertEqual(enemy.size, 1)
            self.assertFalse(enemy.is_boss_encounter)


if __name__ == "__main__":
    unittest.main()
