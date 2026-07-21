from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from arch_rogue.combat._utils import (
    ENEMY_SWING_TELEGRAPH,
    KNOCKBACK_DECAY_RATE,
    KNOCKBACK_SPEED,
)
from arch_rogue.combat.damage import DamageContext
from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game
from arch_rogue.models import Enemy
from arch_rogue.save_system import _TRANSIENT_ENEMY_FIELDS


class CombatPhase4BatchCTests(unittest.TestCase):
    def make_game(
        self, tmpdir: str, archetype_index: int = 0, seed: int = 2202
    ) -> Game:
        game = Game(
            screen_size=(820, 540),
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

    def _make_enemy(self, game: Game, hp: int = 200) -> Enemy:
        return Enemy(
            "Target",
            "melee",
            game.player.x + 1.0,
            game.player.y,
            hp,
            hp,
            1.0,
            4,
            1,
            1.2,
            1.0,
        )

    # ------------------------------------------------------------------
    # #5 Knockback field on Enemy
    # ------------------------------------------------------------------
    def test_enemy_knockback_fields_default_to_zero(self) -> None:
        enemy = Enemy("X", "melee", 0.0, 0.0, 10, 10, 1.0, 1, 1, 1.0, 1.0)
        self.assertEqual(enemy.knockback_vx, 0.0)
        self.assertEqual(enemy.knockback_vy, 0.0)
        self.assertEqual(enemy.windup_time, 0.0)
        self.assertEqual(enemy.windup_duration, 0.0)

    def test_damage_enemy_sets_knockback_velocity_and_defers_shove(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            enemy = self._make_enemy(game)
            game.enemies = [enemy]
            x_before = enemy.x
            game.damage_enemy(
                DamageContext(
                    target=enemy,
                    amount=5,
                    damage_type="physical",
                    knockback_from=(1.0, 0.0),
                )
            )
            # Velocity is set; the shove itself is applied in update_enemies,
            # so the enemy has not moved yet this frame.
            self.assertAlmostEqual(enemy.knockback_vx, KNOCKBACK_SPEED)
            self.assertAlmostEqual(enemy.knockback_vy, 0.0)
            self.assertEqual(enemy.x, x_before)

    def test_update_enemies_applies_and_decays_knockback_for_stunned_enemy(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            enemy = self._make_enemy(game)
            enemy.statuses["stunned"] = 1.0  # movement branch skips; knockback must not
            enemy.knockback_vx = KNOCKBACK_SPEED
            enemy.knockback_vy = 0.0
            game.enemies = [enemy]
            x_before = enemy.x

            game.update_enemies(1.0 / 60.0)
            # Knockback stepped the enemy before the stunned skip.
            self.assertGreater(enemy.x, x_before)
            self.assertTrue(enemy.moving)
            # Velocity decayed exponentially.
            self.assertLess(enemy.knockback_vx, KNOCKBACK_SPEED)
            self.assertGreater(enemy.knockback_vx, 0.0)

    def test_knockback_total_displacement_approximates_continuous_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            enemy = self._make_enemy(game)
            enemy.statuses["stunned"] = 5.0  # keep movement branch off for many frames
            enemy.knockback_vx = KNOCKBACK_SPEED
            game.enemies = [enemy]
            start_x = enemy.x
            dt = 1.0 / 60.0
            for _ in range(240):  # 4s -> well past the ~0.1s decay timescale
                game.update_enemies(dt)
            displacement = enemy.x - start_x
            # Continuous limit is KNOCKBACK_SPEED / KNOCKBACK_DECAY_RATE (~0.16);
            # discrete integration at 60fps runs a little above that.
            expected = KNOCKBACK_SPEED / KNOCKBACK_DECAY_RATE
            self.assertGreater(displacement, 0.0)
            self.assertLess(displacement, expected * 1.6)
            self.assertAlmostEqual(enemy.knockback_vx, 0.0, places=2)

    def test_knockback_and_windup_fields_are_transient_not_saved(self) -> None:
        for name in ("knockback_vx", "knockback_vy", "windup_time", "windup_duration"):
            self.assertIn(name, _TRANSIENT_ENEMY_FIELDS, name)

    # ------------------------------------------------------------------
    # #6 Telegraph helper
    # ------------------------------------------------------------------
    def test_enemy_melee_sets_windup_telegraph(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            enemy = self._make_enemy(game)
            game.enemies = [enemy]
            game.player.hp = game.player.max_hp  # survive the hit
            game.enemy_melee(enemy, line_of_sight_confirmed=True)
            self.assertAlmostEqual(enemy.windup_time, ENEMY_SWING_TELEGRAPH)
            self.assertAlmostEqual(enemy.windup_duration, ENEMY_SWING_TELEGRAPH)

    def test_enemy_cast_sets_windup_telegraph(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            enemy = self._make_enemy(game)
            enemy.kind = "ranged"
            game.enemies = [enemy]
            game.projectiles.clear()
            game.enemy_cast(enemy, -1.0, 0.0, line_of_sight_confirmed=True)
            self.assertAlmostEqual(enemy.windup_time, ENEMY_SWING_TELEGRAPH)

    def test_update_enemies_decays_windup_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            enemy = self._make_enemy(game)
            enemy.statuses["stunned"] = 1.0  # skip movement so only decay runs
            enemy.windup_time = ENEMY_SWING_TELEGRAPH
            enemy.windup_duration = ENEMY_SWING_TELEGRAPH
            game.enemies = [enemy]
            game.update_enemies(0.1)
            self.assertLess(enemy.windup_time, ENEMY_SWING_TELEGRAPH)
            # enough frames -> reaches zero
            for _ in range(20):
                game.update_enemies(0.1)
            self.assertEqual(enemy.windup_time, 0.0)

    def test_draw_windup_telegraph_no_op_when_zero_and_safe_when_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            enemy = self._make_enemy(game)
            sx, sy = 100, 100
            # No active telegraph -> early return, no blit, no error.
            game.draw_windup_telegraph(enemy, sx, sy)
            # Active telegraph -> draws a fading ring without raising.
            enemy.windup_time = ENEMY_SWING_TELEGRAPH
            enemy.windup_duration = ENEMY_SWING_TELEGRAPH
            game.draw_windup_telegraph(enemy, sx, sy)
            self.assertGreater(enemy.windup_time, 0.0)  # draw does not decay


if __name__ == "__main__":
    unittest.main()