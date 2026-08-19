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
    ENEMY_BOSS_WINDUP,
    ENEMY_CAST_WINDUP,
    ENEMY_MELEE_WINDUP,
    KNOCKBACK_DECAY_RATE,
    KNOCKBACK_SPEED,
)
from arch_rogue.combat.damage import DamageContext
from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game
from arch_rogue.models import Enemy
from arch_rogue.save_system import _TRANSIENT_ENEMY_FIELDS


class EnemyKnockbackAndAttackWindupTests(unittest.TestCase):
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

    def _make_enemy(self, game: Game, hp: int = 200, kind: str = "melee") -> Enemy:
        return Enemy(
            "Target",
            kind,
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
    def test_enemy_transient_fields_default_to_zero(self) -> None:
        enemy = Enemy("X", "melee", 0.0, 0.0, 10, 10, 1.0, 1, 1, 1.0, 1.0)
        self.assertEqual(enemy.knockback_vx, 0.0)
        self.assertEqual(enemy.knockback_vy, 0.0)
        self.assertEqual(enemy.windup_time, 0.0)
        self.assertEqual(enemy.windup_duration, 0.0)
        self.assertEqual(enemy.windup_attack, "")
        self.assertEqual(enemy.windup_nx, 0.0)
        self.assertEqual(enemy.windup_ny, 0.0)

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
            self.assertAlmostEqual(enemy.knockback_vx, KNOCKBACK_SPEED)
            self.assertAlmostEqual(enemy.knockback_vy, 0.0)
            self.assertEqual(enemy.x, x_before)  # shove is applied in update_enemies

    def test_update_enemies_applies_and_decays_knockback_for_stunned_enemy(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            enemy = self._make_enemy(game)
            enemy.statuses["stunned"] = 1.0  # movement branch skips; knockback must not
            enemy.knockback_vx = KNOCKBACK_SPEED
            game.enemies = [enemy]
            x_before = enemy.x
            game.update_enemies(1.0 / 60.0)
            self.assertGreater(enemy.x, x_before)
            self.assertTrue(enemy.moving)
            self.assertLess(enemy.knockback_vx, KNOCKBACK_SPEED)
            self.assertGreater(enemy.knockback_vx, 0.0)

    def test_knockback_total_displacement_approximates_continuous_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            enemy = self._make_enemy(game)
            enemy.statuses["stunned"] = 5.0
            enemy.knockback_vx = KNOCKBACK_SPEED
            game.enemies = [enemy]
            start_x = enemy.x
            dt = 1.0 / 60.0
            for _ in range(240):
                game.update_enemies(dt)
            displacement = enemy.x - start_x
            expected = KNOCKBACK_SPEED / KNOCKBACK_DECAY_RATE
            self.assertGreater(displacement, 0.0)
            self.assertLess(displacement, expected * 1.6)
            self.assertAlmostEqual(enemy.knockback_vx, 0.0, places=2)

    def test_knockback_and_windup_fields_are_transient_not_saved(self) -> None:
        for name in (
            "knockback_vx",
            "knockback_vy",
            "windup_time",
            "windup_duration",
            "windup_attack",
            "windup_nx",
            "windup_ny",
        ):
            self.assertIn(name, _TRANSIENT_ENEMY_FIELDS, name)

    # ------------------------------------------------------------------
    # #6 Telegraph helper (pre-attack windup, locked)
    # ------------------------------------------------------------------
    def test_windup_duration_per_enemy_kind(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            melee = self._make_enemy(game, kind="melee")
            caster = self._make_enemy(game, kind="ranged")
            boss = self._make_enemy(game, kind="boss")
            self.assertEqual(game._enemy_windup_duration(melee), ENEMY_MELEE_WINDUP)
            self.assertEqual(game._enemy_windup_duration(caster), ENEMY_CAST_WINDUP)
            self.assertEqual(game._enemy_windup_duration(boss), ENEMY_BOSS_WINDUP)

    def test_commit_enemy_attack_starts_windup_with_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            enemy = self._make_enemy(game, kind="ranged")
            game._commit_enemy_attack(enemy, "cast", 0.6, -0.8)
            self.assertAlmostEqual(enemy.windup_time, ENEMY_CAST_WINDUP)
            self.assertAlmostEqual(enemy.windup_duration, ENEMY_CAST_WINDUP)
            self.assertEqual(enemy.windup_attack, "cast")
            self.assertAlmostEqual(enemy.windup_nx, 0.6)
            self.assertAlmostEqual(enemy.windup_ny, -0.8)
            # Commit is idempotent: a second commit while winding up is a no-op.
            game._commit_enemy_attack(enemy, "melee")
            self.assertEqual(enemy.windup_attack, "cast")

    def test_fire_committed_attack_melee_lands_and_cast_spawns_projectile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            enemy = self._make_enemy(game, kind="ranged")
            game.enemies = [enemy]
            game.projectiles.clear()
            game.player.hp = game.player.max_hp
            hp_before = game.player.hp

            # Locked melee fires through line_of_sight_confirmed=True.
            enemy.windup_attack = "melee"
            game._fire_committed_attack(enemy)
            self.assertLess(game.player.hp, hp_before)
            self.assertEqual(enemy.windup_attack, "")  # cleared after firing

            # Cast spawns a projectile along the committed direction.
            game.projectiles.clear()
            enemy.windup_attack = "cast"
            enemy.windup_nx = 1.0
            enemy.windup_ny = 0.0
            game._fire_committed_attack(enemy)
            self.assertEqual(len(game.projectiles), 1)
            self.assertGreater(game.projectiles[0].vx, 0.0)

    def test_update_enemies_commits_melee_to_windup_without_damaging(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            enemy = self._make_enemy(game)
            enemy.attack_timer = 0.0
            game.enemies = [enemy]
            hp_before = game.player.hp
            game.update_enemies(0.1)
            # Committed to a windup this frame; no damage yet.
            self.assertAlmostEqual(enemy.windup_time, ENEMY_MELEE_WINDUP)
            self.assertEqual(enemy.windup_attack, "melee")
            self.assertEqual(game.player.hp, hp_before)

    def test_committed_melee_attack_fires_after_windup(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            enemy = self._make_enemy(game)
            enemy.attack_timer = 0.0
            game.enemies = [enemy]
            game.player.hp = game.player.max_hp
            hp_before = game.player.hp
            # Commit on frame 1.
            game.update_enemies(0.1)
            self.assertAlmostEqual(enemy.windup_time, ENEMY_MELEE_WINDUP)
            # Advance past the windup -> the locked hit lands.
            for _ in range(8):
                game.update_enemies(0.1)
            self.assertLess(game.player.hp, hp_before)
            self.assertEqual(enemy.windup_time, 0.0)

    def test_stun_cancels_a_committed_windup(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            enemy = self._make_enemy(game)
            game._commit_enemy_attack(enemy, "melee")
            self.assertGreater(enemy.windup_time, 0.0)
            enemy.statuses["stunned"] = 5.0  # lasts the whole window so it can't re-commit
            game.enemies = [enemy]
            game.player.hp = game.player.max_hp
            hp_before = game.player.hp
            for _ in range(20):
                game.update_enemies(0.1)
            self.assertEqual(enemy.windup_time, 0.0)
            self.assertEqual(enemy.windup_attack, "")
            # Stun cancelled the windup before it fired -> no damage from that attack.
            self.assertEqual(game.player.hp, hp_before)

    def test_update_enemies_decays_windup_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            enemy = self._make_enemy(game)
            # windup_attack left empty so completion is a no-op (no fire); isolates decay.
            enemy.windup_time = ENEMY_MELEE_WINDUP
            enemy.windup_duration = ENEMY_MELEE_WINDUP
            enemy.attack_timer = 10.0  # not attack-ready -> no re-commit on completion
            game.enemies = [enemy]
            game.update_enemies(0.1)
            self.assertLess(enemy.windup_time, ENEMY_MELEE_WINDUP)
            for _ in range(20):
                game.update_enemies(0.1)
            self.assertEqual(enemy.windup_time, 0.0)

    def test_draw_windup_telegraph_no_op_when_zero_and_safe_when_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            enemy = self._make_enemy(game)
            sx, sy = 100, 100
            game.draw_windup_telegraph(enemy, sx, sy)  # windup_time 0 -> early return
            enemy.windup_time = ENEMY_MELEE_WINDUP
            enemy.windup_duration = ENEMY_MELEE_WINDUP
            game.draw_windup_telegraph(enemy, sx, sy)  # active -> draws without raising
            self.assertGreater(enemy.windup_time, 0.0)  # draw does not decay


if __name__ == "__main__":
    unittest.main()