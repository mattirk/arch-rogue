from __future__ import annotations

import math
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame  # noqa: F401  (required to initialize pygame subsystems in tests)

from arch_rogue.content import ARCHETYPES
from arch_rogue.dungeon import MAP_H, MAP_W
from arch_rogue.game import Game
from arch_rogue.models import AmbushBell, Enemy, Projectile, Tile


def _make_melee_enemy(x: float, y: float, attack_range: float = 4.0) -> Enemy:
    return Enemy(
        "Test Dummy",
        "melee",
        x,
        y,
        200,
        200,
        1.0,
        6,
        12,
        attack_range,
        1.0,
    )


class EnemyLineOfSightTests(unittest.TestCase):
    def make_game(self, tmpdir, archetype_index=0, seed=4242) -> Game:
        game = Game(
            screen_size=(960, 600),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.rng.seed(seed)
        game.restart(ARCHETYPES[archetype_index])
        if game.story_intro_pending:
            self.assertTrue(game.choose_story_relic_path(0))
        game.active_cutscene = None
        return game

    def open_patch(self, game: Game, cx: int, cy: int, radius: int = 5) -> None:
        for tx in range(cx - radius, cx + radius + 1):
            for ty in range(cy - radius, cy + radius + 1):
                if game.dungeon.in_bounds(tx, ty):
                    game.dungeon.tiles[tx][ty] = Tile.FLOOR

    def test_dungeon_line_of_sight_blocked_and_clear(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            dungeon = game.dungeon
            cx, cy = int(game.player.x), int(game.player.y)
            self.assertGreater(MAP_W - cx, 6)
            # Player and target sit on floor with two wall tiles between them.
            dungeon.tiles[cx][cy] = Tile.FLOOR
            dungeon.tiles[cx + 3][cy] = Tile.FLOOR
            dungeon.tiles[cx + 1][cy] = Tile.WALL
            dungeon.tiles[cx + 2][cy] = Tile.WALL
            x0, y0 = cx + 0.5, cy + 0.5
            x1, y1 = cx + 3.5, cy + 0.5
            self.assertFalse(dungeon.line_of_sight(x0, y0, x1, y1))
            dungeon.tiles[cx + 1][cy] = Tile.FLOOR
            dungeon.tiles[cx + 2][cy] = Tile.FLOOR
            self.assertTrue(dungeon.line_of_sight(x0, y0, x1, y1))

            dungeon.tiles[cx + 1][cy] = Tile.CLOSED_DOOR
            self.assertFalse(dungeon.line_of_sight(x0, y0, x1, y1))
            dungeon.tiles[cx + 1][cy] = Tile.OPEN_DOOR
            self.assertTrue(dungeon.line_of_sight(x0, y0, x1, y1))

    def test_dungeon_line_of_sight_blocks_closed_diagonal_corner(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            dungeon = game.dungeon
            cx, cy = int(game.player.x), int(game.player.y)
            self.assertGreater(MAP_W - cx, 3)
            self.assertGreater(MAP_H - cy, 3)
            dungeon.tiles[cx][cy] = Tile.FLOOR
            dungeon.tiles[cx + 1][cy + 1] = Tile.FLOOR
            dungeon.tiles[cx + 1][cy] = Tile.WALL
            dungeon.tiles[cx][cy + 1] = Tile.WALL
            start = (cx + 0.5, cy + 0.5)
            target = (cx + 1.5, cy + 1.5)

            self.assertFalse(dungeon.line_of_sight(*start, *target))

            dungeon.tiles[cx + 1][cy] = Tile.FLOOR
            self.assertTrue(dungeon.line_of_sight(*start, *target))

    def test_enemy_cannot_melee_through_wall(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            dungeon = game.dungeon
            cx, cy = int(game.player.x), int(game.player.y)
            self.assertGreater(MAP_W - cx, 6)
            game.player.x = cx + 0.5
            game.player.y = cy + 0.5
            dungeon.tiles[cx][cy] = Tile.FLOOR
            dungeon.tiles[cx + 3][cy] = Tile.FLOOR
            dungeon.tiles[cx + 1][cy] = Tile.WALL
            dungeon.tiles[cx + 2][cy] = Tile.WALL
            enemy = _make_melee_enemy(cx + 3.5, cy + 0.5, attack_range=4.0)
            enemy.attack_timer = 0.0
            game.enemies = [enemy]

            hp_before = game.player.hp
            # Distance ~3 <= attack_range, so without a LOS check the enemy
            # would melee the player this frame. The wall must block it.
            game.update_enemies(0.1)
            self.assertEqual(game.player.hp, hp_before)
            self.assertEqual(enemy.attack_timer, 0.0)

            # Clear the wall -> LOS restored -> the enemy now lands its hit.
            dungeon.tiles[cx + 1][cy] = Tile.FLOOR
            dungeon.tiles[cx + 2][cy] = Tile.FLOOR
            enemy.attack_timer = 0.0
            game.update_enemies(0.1)
            self.assertLess(game.player.hp, hp_before)

    def test_enemy_cannot_melee_through_closed_diagonal_corner(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            dungeon = game.dungeon
            cx, cy = int(game.player.x), int(game.player.y)
            game.player.x, game.player.y = cx + 0.5, cy + 0.5
            dungeon.tiles[cx][cy] = Tile.FLOOR
            dungeon.tiles[cx + 1][cy + 1] = Tile.FLOOR
            dungeon.tiles[cx + 1][cy] = Tile.WALL
            dungeon.tiles[cx][cy + 1] = Tile.WALL
            enemy = _make_melee_enemy(cx + 1.5, cy + 1.5, attack_range=2.0)
            enemy.speed = 0.0
            game.enemies = [enemy]

            hp_before = game.player.hp
            game.update_enemies(0.1)
            self.assertEqual(game.player.hp, hp_before)
            self.assertEqual(enemy.attack_timer, 0.0)

            dungeon.tiles[cx + 1][cy] = Tile.FLOOR
            game.update_enemies(0.1)
            self.assertLess(game.player.hp, hp_before)

    def test_player_melee_cannot_hit_through_wall_or_closed_door(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            cx, cy = int(game.player.x), int(game.player.y)
            self.open_patch(game, cx, cy)
            game.player.x, game.player.y = cx + 0.8, cy + 0.5
            game.player.facing_x, game.player.facing_y = 1.0, 0.0
            enemy = _make_melee_enemy(cx + 2.2, cy + 0.5)
            game.enemies = [enemy]

            for blocker in (Tile.WALL, Tile.CLOSED_DOOR):
                with self.subTest(blocker=blocker):
                    enemy.hp = enemy.max_hp
                    game.dungeon.tiles[cx + 1][cy] = blocker
                    game.player.melee_timer = 0.0
                    game.player.stamina = game.player.max_stamina

                    self.assertEqual(game.enemies_in_melee_arc(), [])
                    game.player_melee_attack()
                    self.assertEqual(enemy.hp, enemy.max_hp)

            game.dungeon.tiles[cx + 1][cy] = Tile.OPEN_DOOR
            game.player.melee_timer = 0.0
            game.player.stamina = game.player.max_stamina
            game.player_melee_attack()
            self.assertLess(enemy.hp, enemy.max_hp)

    def test_player_nova_and_chain_effects_cannot_cross_walls(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, archetype_index=2)
            cx, cy = int(game.player.x), int(game.player.y)
            self.open_patch(game, cx, cy)
            game.player.x, game.player.y = cx + 0.5, cy + 0.5
            game.dungeon.tiles[cx + 1][cy] = Tile.WALL
            visible = _make_melee_enemy(cx - 0.5, cy + 0.5)
            source = _make_melee_enemy(cx + 0.7, cy + 0.5)
            hidden = _make_melee_enemy(cx + 2.2, cy + 0.5)
            game.enemies = [visible, source, hidden]
            game.player.class_skill_timer = 0.0
            game.player.mana = game.player.max_mana

            game.player_cast_nova()

            self.assertLess(visible.hp, visible.max_hp)
            self.assertLess(source.hp, source.max_hp)
            self.assertEqual(hidden.hp, hidden.max_hp)

            visible.hp = visible.max_hp
            source.hp = source.max_hp
            hidden.hp = hidden.max_hp
            game.enemies = [source, hidden]
            game.player.skill_upgrades.append("arcanist_chain_lightning")
            projectile = Projectile(
                source.x,
                source.y,
                1.0,
                0.0,
                30,
                "player",
                (92, 170, 255),
            )
            game._maybe_chain_lightning(projectile, source)
            game._apply_chain_proc(source, 9)
            self.assertEqual(hidden.hp, hidden.max_hp)

            game.dungeon.tiles[cx + 1][cy] = Tile.FLOOR
            game._maybe_chain_lightning(projectile, source)
            game._apply_chain_proc(source, 9)
            self.assertLess(hidden.hp, hidden.max_hp)

    def test_projectiles_cannot_tunnel_through_walls(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            cx, cy = int(game.player.x), int(game.player.y)
            self.open_patch(game, cx, cy)
            game.player.x, game.player.y = cx + 0.5, cy + 0.5
            enemy = _make_melee_enemy(cx + 3.5, cy + 0.5)
            game.enemies = [enemy]
            game.familiars = []
            game.dungeon.tiles[cx + 1][cy] = Tile.WALL

            game.projectiles = [
                Projectile(
                    game.player.x,
                    game.player.y,
                    6.0,
                    0.0,
                    25,
                    "player",
                    (92, 170, 255),
                )
            ]
            game.update_projectiles(0.5)
            self.assertEqual(game.projectiles, [])
            self.assertEqual(enemy.hp, enemy.max_hp)

            hp_before = game.player.hp
            game.projectiles = [
                Projectile(
                    enemy.x,
                    enemy.y,
                    -6.0,
                    0.0,
                    25,
                    "enemy",
                    (235, 90, 80),
                )
            ]
            game.update_projectiles(0.5)
            self.assertEqual(game.projectiles, [])
            self.assertEqual(game.player.hp, hp_before)

            game.dungeon.tiles[cx + 1][cy] = Tile.FLOOR
            game.projectiles = [
                Projectile(
                    game.player.x,
                    game.player.y,
                    6.0,
                    0.0,
                    25,
                    "player",
                    (92, 170, 255),
                )
            ]
            game.update_projectiles(0.5)
            self.assertLess(enemy.hp, enemy.max_hp)

            hp_before = game.player.hp
            game.projectiles = [
                Projectile(
                    cx + 3.5,
                    cy + 0.5,
                    -6.0,
                    0.0,
                    25,
                    "enemy",
                    (235, 90, 80),
                )
            ]
            game.update_projectiles(0.5)
            self.assertLess(game.player.hp, hp_before)

    def test_short_projectile_step_cannot_cross_closed_diagonal_corner(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            cx, cy = int(game.player.x), int(game.player.y)
            self.open_patch(game, cx, cy)
            game.dungeon.tiles[cx + 1][cy] = Tile.WALL
            game.dungeon.tiles[cx][cy + 1] = Tile.WALL
            game.projectiles = [
                Projectile(
                    cx + 0.9,
                    cy + 0.9,
                    3.0,
                    3.0,
                    10,
                    "player",
                    (92, 170, 255),
                )
            ]
            game.enemies = []

            game.update_projectiles(0.05)

            self.assertEqual(game.projectiles, [])

    def test_direct_enemy_attack_methods_require_clear_line_of_sight(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            cx, cy = int(game.player.x), int(game.player.y)
            self.open_patch(game, cx, cy)
            game.player.x, game.player.y = cx + 0.8, cy + 0.5
            enemy = _make_melee_enemy(cx + 2.2, cy + 0.5, attack_range=2.0)
            game.enemies = [enemy]
            game.projectiles = []
            game.dungeon.tiles[cx + 1][cy] = Tile.WALL
            hp_before = game.player.hp

            game.enemy_melee(enemy)
            game.enemy_cast(enemy, -1.0, 0.0)

            self.assertEqual(game.player.hp, hp_before)
            self.assertEqual(game.projectiles, [])
            self.assertEqual(enemy.attack_timer, 0.0)

            game.dungeon.tiles[cx + 1][cy] = Tile.FLOOR
            game.enemy_melee(enemy)
            game.enemy_cast(enemy, -1.0, 0.0)
            self.assertLess(game.player.hp, hp_before)
            self.assertEqual(len(game.projectiles), 1)

            game.projectiles.clear()
            enemy.x = game.player.x + enemy.attack_range + 1.0
            enemy.y = game.player.y
            game.enemy_cast(enemy, -1.0, 0.0)
            self.assertEqual(game.projectiles, [])

    def test_enemy_revalidates_los_after_moving_toward_lure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            cx, cy = int(game.player.x), int(game.player.y)
            self.open_patch(game, cx, cy)
            game.player.x, game.player.y = cx + 0.5, cy + 0.5
            game.dungeon.tiles[cx + 1][cy] = Tile.WALL
            enemy = _make_melee_enemy(cx + 1.5, cy + 1.5, attack_range=4.0)
            enemy.speed = 4.0
            enemy.attack_timer = 0.0
            bell = AmbushBell(
                x=enemy.x,
                y=enemy.y - 0.3,
                lifetime=5.0,
                arm_timer=0.0,
                lure_radius=6.0,
                trigger_radius=0.01,
                damage_radius=1.5,
                primary_damage=30,
                splash_damage=12,
                max_lifetime=5.0,
                max_arm_timer=0.0,
                armed_announced=True,
            )
            game.enemies = [enemy]
            game.ambush_bells = [bell]
            self.assertTrue(
                game.dungeon.line_of_sight(
                    enemy.x, enemy.y, game.player.x, game.player.y
                )
            )
            hp_before = game.player.hp
            start_y = enemy.y

            game.update_enemies(0.05)

            self.assertLess(enemy.y, start_y)
            self.assertFalse(
                game.dungeon.line_of_sight(
                    enemy.x, enemy.y, game.player.x, game.player.y
                )
            )
            self.assertEqual(game.player.hp, hp_before)
            self.assertEqual(enemy.attack_timer, 0.0)

    def test_enemy_los_runs_only_when_an_attack_is_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            enemy = _make_melee_enemy(
                game.player.x + 1.0,
                game.player.y,
                attack_range=1.5,
            )
            enemy.aggro_range = 20.0
            enemy.speed = 0.0
            game.enemies = [enemy]

            with patch.object(game.dungeon, "line_of_sight", return_value=True) as los:
                enemy.attack_timer = 0.8
                game.update_enemies(0.1)
                los.assert_not_called()

                enemy.x = game.player.x + 4.0
                enemy.attack_timer = 0.0
                game.update_enemies(0.1)
                los.assert_not_called()

                enemy.x = game.player.x + 1.0
                enemy.attack_timer = 0.0
                game.update_enemies(0.1)
                los.assert_called_once()
                self.assertGreater(enemy.attack_timer, 0.0)

    def test_melee_enemy_attacks_when_inside_range_even_above_stop_distance(
        self,
    ) -> None:
        """Regression: enemy should not idle just inside attack range.

        With the old ``elif`` movement/attack coupling, an enemy that ended
        a frame slightly inside ``attack_range`` but still above the movement
        stop distance would move a tiny step instead of attacking, appearing
        to stand idle. The attack decision must be independent of the
        movement stop distance once the enemy is within melee reach.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            cx, cy = int(game.player.x), int(game.player.y)
            self.open_patch(game, cx, cy)
            game.player.x, game.player.y = cx + 0.5, cy + 0.5
            # attack_range=1.5 gives a stop distance of ~1.38, so 1.45 is
            # inside attack range but above the movement stop distance.
            enemy = _make_melee_enemy(cx + 1.95, cy + 0.5, attack_range=1.5)
            enemy.attack_timer = 0.0
            enemy.aggro_range = 20.0
            game.enemies = [enemy]

            hp_before = game.player.hp
            game.update_enemies(0.05)
            self.assertLess(game.player.hp, hp_before)
            self.assertGreater(enemy.attack_timer, 0.0)
            self.assertEqual(enemy.telegraph, "melee")

    def test_melee_enemy_closes_and_hits_slowly_retreating_player(self) -> None:
        """A melee enemy must land a hit on a player walking away slowly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            cx, cy = int(game.player.x), int(game.player.y)
            self.open_patch(game, cx, cy, radius=12)
            game.player.x, game.player.y = cx + 0.5, cy + 0.5
            enemy = _make_melee_enemy(cx + 5.0, cy + 0.5, attack_range=1.05)
            enemy.speed = 1.56
            enemy.aggro_range = 20.0
            game.enemies = [enemy]
            game.familiars = []
            game.projectiles = []

            hp_before = game.player.hp
            dt = 1.0 / 60.0
            player_speed = 1.4  # slower than the enemy
            for frame in range(300):
                # Move the player directly away from the enemy at partial speed
                # for the first 120 frames, then stop so the enemy can close.
                if frame < 120:
                    dx = game.player.x - enemy.x
                    dy = game.player.y - enemy.y
                    dist = math.hypot(dx, dy)
                    if dist > 0.001:
                        px, py = dx / dist, dy / dist
                        game.move_actor(
                            game.player,
                            px * player_speed * dt,
                            py * player_speed * dt,
                        )
                game.update_enemies(dt)
                if game.player.hp < hp_before:
                    break
            self.assertLess(game.player.hp, hp_before)


if __name__ == "__main__":
    unittest.main()
