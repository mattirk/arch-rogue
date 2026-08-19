from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from arch_rogue.constants import DUNGEON_DEPTH
from arch_rogue.content import ARCHETYPES
from arch_rogue.dungeon import BOSS_ARENA_MIN_H, BOSS_ARENA_MIN_W, Dungeon, Tile
from arch_rogue.game import Game
from arch_rogue.sprites import DIRECTIONS


class BigBossesTests(unittest.TestCase):


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
                self.assertIn(game.door_render_direction(x, y), DIRECTIONS)

            # Kill the boss: doors restore.
            game.kill_enemy(fb)
            game.update_boss_encounter()
            self.assertFalse(game.boss_engaged)
            self.assertEqual(len(game.boss_sealed_tiles), 0)

    def test_boss_on_doorway_tile_is_freed_when_doors_seal(self) -> None:
        # Regression: the boss meets the player at the arena entrance the
        # moment the fight engages, so the seal turns the tile under the boss
        # into a CLOSED_DOOR. move_actor only validates destinations, leaving
        # the boss permanently frozen inside the spawned door.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.populate_floor(game, 3)
            fb = next(e for e in game.enemies if e.role == "floor_boss")
            room = game.dungeon.room_at(fb.x, fb.y)
            assert room is not None
            sealed = game.dungeon.seal_room_openings(room)
            game.dungeon.restore_tiles(sealed)
            doorway = next(
                (
                    (x, y)
                    for x, y, _tile in sealed
                    if game.dungeon.room_at(x + 0.5, y + 0.5) is room
                ),
                None,
            )
            self.assertIsNotNone(doorway)
            assert doorway is not None
            fb.x, fb.y = doorway[0] + 0.5, doorway[1] + 0.5

            cx, cy = room.center
            game.player.x = cx + 0.5
            game.player.y = cy + 0.5
            game.update_boss_encounter()
            self.assertTrue(game.boss_engaged)
            radius = 0.82 if fb.size >= 2 else 0.27
            self.assertFalse(
                game.dungeon.blocked_for_radius(fb.x, fb.y, radius)
            )

    def test_wide_probe_detects_thin_obstacle_under_center(self) -> None:
        # Regression: blocked_for_radius sampled only the four footprint
        # corners, and a 2x2 boss's corners sit 1.64 tiles apart — a
        # one-tile-thick obstacle under the center (a freshly sealed doorway
        # strip) passed undetected, so the seal-time nudge never ran and the
        # boss froze inside the door.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.populate_floor(game, 3)
            fb = next(e for e in game.enemies if e.role == "floor_boss")
            room = game.dungeon.room_at(fb.x, fb.y)
            assert room is not None
            cx, cy = room.center
            # Interior spot with all eight neighbors open, then a lone
            # CLOSED_DOOR under the probe center: corners all land on floor.
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    game.dungeon.tiles[cx + dx][cy + dy] = Tile.FLOOR
            game.dungeon.tiles[cx][cy] = Tile.CLOSED_DOOR
            try:
                self.assertTrue(
                    game.dungeon.blocked_for_radius(cx + 0.5, cy + 0.5, 0.82)
                )
            finally:
                game.dungeon.tiles[cx][cy] = Tile.FLOOR

    def test_boss_astride_two_wide_seal_seam_is_freed_when_doors_seal(
        self,
    ) -> None:
        # Regression: corridors are two tiles wide, so a boss meeting the
        # player mid-doorway stands astride the seam between the two sealed
        # tiles with all four footprint corners on open corridor/room floor.
        # The old corner-only probe reported the spot clear, skipped the
        # seal-time nudge, and left the boss buried in the new wall.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.populate_floor(game, 3)
            fb = next(e for e in game.enemies if e.role == "floor_boss")
            room = game.dungeon.room_at(fb.x, fb.y)
            assert room is not None
            sealed = game.dungeon.seal_room_openings(room)
            seam = None
            for x0, y0, _tile in sealed:
                for x1, y1, _tile1 in sealed:
                    if abs(x0 - x1) + abs(y0 - y1) != 1:
                        continue
                    px = (x0 + x1) / 2 + 0.5
                    py = (y0 + y1) / 2 + 0.5
                    corners_open = all(
                        game.dungeon.is_floor(px + ox, py + oy)
                        for ox in (-0.82, 0.82)
                        for oy in (-0.82, 0.82)
                    )
                    if corners_open:
                        seam = (px, py)
                        break
                if seam is not None:
                    break
            self.assertIsNotNone(
                seam, "no two-wide sealed opening with open corners found"
            )
            assert seam is not None
            # The fixed probe sees the sealed strip under the center.
            self.assertTrue(
                game.dungeon.blocked_for_radius(seam[0], seam[1], 0.82)
            )
            game.dungeon.restore_tiles(sealed)

            fb.x, fb.y = seam
            cx, cy = room.center
            game.player.x = cx + 0.5
            game.player.y = cy + 0.5
            game.update_boss_encounter()
            self.assertTrue(game.boss_engaged)
            self.assertFalse(
                game.dungeon.blocked_for_radius(fb.x, fb.y, 0.82)
            )

    def test_boss_shoved_onto_seal_mid_fight_recovers_next_frame(self) -> None:
        # Watchdog: body-contact shoves can walk the wide footprint onto
        # sealed geometry after the engage-frame nudge already ran; the
        # per-frame check must pull the boss back out instead of leaving it
        # frozen (move_actor only validates destinations).
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

            sx, sy, _tile = game.boss_sealed_tiles[0]
            fb.x, fb.y = sx + 0.5, sy + 0.5
            self.assertTrue(
                game.dungeon.blocked_for_radius(fb.x, fb.y, 0.82)
            )
            game.update_boss_encounter()
            self.assertFalse(
                game.dungeon.blocked_for_radius(fb.x, fb.y, 0.82)
            )

    def test_floor_guardian_blocks_solo_stairs_until_killed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.populate_floor(game, 3)
            guardian = next(
                enemy for enemy in game.enemies if enemy.role == "floor_boss"
            )
            stairs_x, stairs_y = game.dungeon.stairs
            game.player.x, game.player.y = stairs_x + 0.5, stairs_y + 0.5

            hint = game.current_interaction_hint()
            self.assertIsNotNone(hint)
            assert hint is not None
            self.assertEqual(hint[0], "!")
            self.assertEqual(hint[1], "Stairs sealed")
            game.interact()
            self.assertEqual(game.current_depth, 3)
            self.assertTrue(
                any("guardian" in floater.text for floater in game.floaters)
            )

            game.kill_enemy(guardian)
            self.assertFalse(game.stairs_guardian_alive())
            game.interact()
            self.assertEqual(game.current_depth, 4)

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
            # 4.8.9: park the authored ability rotation on cooldown so this
            # test keeps pinning the legacy fallback fan (the rotation has
            # its own coverage in test_enemy_tactics_and_abilities).
            for key in fb.ability_keys:
                fb.ability_timers[key] = 99.0
            game.update_enemies(0.05)
            # The boss commits to a cast windup (no projectile yet); the
            # 3-bolt fan fires after the shorter boss windup.
            self.assertGreater(fb.windup_time, 0.0)
            self.assertEqual(len(game.projectiles) - before, 0)
            for _ in range(10):
                game.update_enemies(0.05)
            # 4-tile bosses fire a 3-bolt fan.
            self.assertEqual(len(game.projectiles) - before, 3)

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
