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

from arch_rogue.combat._utils import ENEMY_ALERT_MEMORY, ENEMY_MELEE_WINDUP
from arch_rogue.combat.abilities import (
    boss_phase_cooldown_factor,
    enemy_tactic,
    select_boss_attack,
)
from arch_rogue.combat.damage import DamageContext
from arch_rogue.content import ABILITY_INDEX, ARCHETYPES, TACTICS
from arch_rogue.game import Game
from arch_rogue.models import Enemy, Tile
from arch_rogue.save_system import _TRANSIENT_ENEMY_FIELDS


def _make_enemy(
    x: float,
    y: float,
    *,
    kind: str = "melee",
    role: str = "bruiser",
    attack_range: float = 1.2,
    speed: float = 2.0,
    aggro_range: float = 20.0,
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


class EnemyTacticsAndAbilitiesTests(unittest.TestCase):
    def make_game(self, tmpdir, archetype_index=0, seed=515) -> Game:
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

    def open_patch(self, game: Game, cx: int, cy: int, radius: int = 8) -> None:
        for tx in range(cx - radius, cx + radius + 1):
            for ty in range(cy - radius, cy + radius + 1):
                if game.dungeon.in_bounds(tx, ty):
                    game.dungeon.tiles[tx][ty] = Tile.FLOOR

    # ------------------------------------------------------------------
    # A1: ability framework
    # ------------------------------------------------------------------
    def test_new_ai_fields_are_transient_not_saved(self) -> None:
        for name in (
            "ability_timers",
            "ai_state",
            "alert_timer",
            "nav_latch",
            "memory_x",
            "memory_y",
            "strafe_sign",
            "last_ability",
        ):
            self.assertIn(name, _TRANSIENT_ENEMY_FIELDS, name)
        # Identity fields DO persist.
        self.assertNotIn("tactic", _TRANSIENT_ENEMY_FIELDS)
        self.assertNotIn("ability_keys", _TRANSIENT_ENEMY_FIELDS)

    def test_authored_windup_overrides_per_kind_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            enemy = _make_enemy(game.player.x + 1.0, game.player.y)
            game._commit_enemy_attack(enemy, "melee")
            self.assertAlmostEqual(enemy.windup_time, ENEMY_MELEE_WINDUP)
            enemy.windup_time = 0.0
            enemy.windup_attack = ""
            game._commit_enemy_attack(enemy, "ember_cleave")
            self.assertAlmostEqual(
                enemy.windup_time, ABILITY_INDEX["ember_cleave"].windup
            )

    def test_ability_cooldowns_run_independently_of_global_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            enemy = _make_enemy(
                game.player.x + 1.0,
                game.player.y,
                kind="miniboss",
                role="floor_boss",
                attack_range=6.0,
            )
            enemy.ability_keys = ("gate_strike", "shadow_volley")
            game.enemies = [enemy]
            enemy.windup_attack = "gate_strike"
            game._fire_committed_attack(enemy)
            self.assertGreater(enemy.ability_timers["gate_strike"], 0.0)
            self.assertGreater(enemy.attack_timer, 0.0)
            self.assertNotIn("shadow_volley", enemy.ability_timers)
            # The spent ability is out of rotation; the other is selectable.
            self.assertEqual(select_boss_attack(enemy, 3.0), "shadow_volley")

    def test_boss_rotation_prefers_a_different_ability_than_last(self) -> None:
        enemy = _make_enemy(
            0.0, 0.0, kind="miniboss", role="floor_boss", attack_range=6.0
        )
        enemy.ability_keys = ("gate_strike", "shadow_volley")
        self.assertEqual(select_boss_attack(enemy, 3.0), "gate_strike")
        enemy.last_ability = "gate_strike"
        self.assertEqual(select_boss_attack(enemy, 3.0), "shadow_volley")
        enemy.last_ability = "shadow_volley"
        self.assertEqual(select_boss_attack(enemy, 3.0), "gate_strike")

    def test_boss_legacy_fallback_band_when_no_ability_eligible(self) -> None:
        enemy = _make_enemy(
            0.0, 0.0, kind="miniboss", role="floor_boss", attack_range=1.85
        )
        enemy.ability_keys = ("gate_strike", "shadow_volley")
        enemy.ability_timers = {"gate_strike": 9.0, "shadow_volley": 9.0}
        self.assertEqual(select_boss_attack(enemy, 4.0), "cast")
        self.assertEqual(select_boss_attack(enemy, 1.2), "melee")
        self.assertIsNone(select_boss_attack(enemy, 7.5))

    def test_boss_phase_pressure_scales_ability_cooldown_below_half_hp(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            enemy = _make_enemy(
                game.player.x + 1.0,
                game.player.y,
                kind="miniboss",
                role="floor_boss",
                attack_range=6.0,
            )
            enemy.ability_keys = ("gate_strike",)
            game.enemies = [enemy]
            self.assertEqual(boss_phase_cooldown_factor(enemy), 1.0)
            enemy.hp = enemy.max_hp // 2 - 1
            self.assertEqual(boss_phase_cooldown_factor(enemy), 0.8)
            enemy.windup_attack = "gate_strike"
            game._fire_committed_attack(enemy)
            self.assertAlmostEqual(
                enemy.ability_timers["gate_strike"],
                ABILITY_INDEX["gate_strike"].cooldown * 0.8,
            )

    def test_fan_ability_fires_projectile_count_with_status_rider(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            cx, cy = int(game.player.x), int(game.player.y)
            self.open_patch(game, cx, cy)
            enemy = _make_enemy(game.player.x + 3.0, game.player.y, kind="ranged")
            game.enemies = [enemy]
            game.projectiles.clear()
            game.enemy_cast(
                enemy,
                -1.0,
                0.0,
                ability=ABILITY_INDEX["frost_fan"],
                line_of_sight_confirmed=True,
            )
            frost_fan = ABILITY_INDEX["frost_fan"]
            self.assertEqual(len(game.projectiles), frost_fan.projectile_count)
            for projectile in game.projectiles:
                self.assertEqual(projectile.status_effect, "chilled")

    def test_nova_hits_in_radius_with_los_and_respects_walls(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            cx, cy = int(game.player.x), int(game.player.y)
            self.open_patch(game, cx, cy)
            game.player.x, game.player.y = cx + 0.5, cy + 0.5
            enemy = _make_enemy(cx + 2.0, cy + 0.5)
            game.enemies = [enemy]
            game.rng.seed(7)
            hp_before = game.player.hp
            game.enemy_nova(enemy, ABILITY_INDEX["ember_nova"])
            self.assertLess(game.player.hp, hp_before)

            game.player.hp = game.player.max_hp
            hp_before = game.player.hp
            game.dungeon.tiles[cx + 1][cy] = Tile.WALL
            game.enemy_nova(enemy, ABILITY_INDEX["ember_nova"])
            self.assertEqual(game.player.hp, hp_before)

            # Out of radius: untouched even with clear line of sight.
            game.dungeon.tiles[cx + 1][cy] = Tile.FLOOR
            enemy.x = cx + 6.0
            game.enemy_nova(enemy, ABILITY_INDEX["ember_nova"])
            self.assertEqual(game.player.hp, hp_before)

    # ------------------------------------------------------------------
    # A2: tactics
    # ------------------------------------------------------------------
    def test_marksman_holds_wide_kite_band(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            cx, cy = int(game.player.x), int(game.player.y)
            self.open_patch(game, cx, cy, radius=10)
            game.player.x, game.player.y = cx + 0.5, cy + 0.5
            enemy = _make_enemy(
                cx + 8.5, cy + 0.5, kind="ranged", role="marksman", attack_range=5.8
            )
            enemy.attack_timer = 999.0  # isolate movement
            game.enemies = [enemy]
            for _ in range(240):
                game.update_enemies(1.0 / 60.0)
            distance = math.hypot(
                enemy.x - game.player.x, enemy.y - game.player.y
            )
            self.assertAlmostEqual(
                distance, TACTICS["marksman"].preferred_range, delta=0.35
            )

    def test_default_role_ranged_enemy_keeps_legacy_band(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            cx, cy = int(game.player.x), int(game.player.y)
            self.open_patch(game, cx, cy, radius=10)
            game.player.x, game.player.y = cx + 0.5, cy + 0.5
            enemy = _make_enemy(
                cx + 7.5, cy + 0.5, kind="ranged", role="bruiser", attack_range=5.8
            )
            enemy.attack_timer = 999.0
            game.enemies = [enemy]
            for _ in range(240):
                game.update_enemies(1.0 / 60.0)
            distance = math.hypot(
                enemy.x - game.player.x, enemy.y - game.player.y
            )
            # Pre-4.8.9 literal: advance until 3.5.
            self.assertAlmostEqual(distance, 3.5, delta=0.35)

    def test_sentinel_plants_at_first_firing_position(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            cx, cy = int(game.player.x), int(game.player.y)
            self.open_patch(game, cx, cy, radius=10)
            game.player.x, game.player.y = cx + 0.5, cy + 0.5
            enemy = _make_enemy(
                cx + 8.5, cy + 0.5, kind="ranged", role="sentinel", attack_range=5.2
            )
            enemy.attack_timer = 999.0
            game.enemies = [enemy]
            for _ in range(240):
                game.update_enemies(1.0 / 60.0)
            distance = math.hypot(
                enemy.x - game.player.x, enemy.y - game.player.y
            )
            # Advances eagerly, then plants the moment the target is inside
            # attack range — well before closing to the preferred band.
            self.assertAlmostEqual(distance, 5.2, delta=0.4)
            self.assertGreater(
                distance, TACTICS["sentinel"].preferred_range + 0.4
            )
            # Inside min range it still gives ground.
            game.player.x = enemy.x - 1.0
            game.player.y = enemy.y
            for _ in range(60):
                game.update_enemies(1.0 / 60.0)
            self.assertGreater(
                math.hypot(enemy.x - game.player.x, enemy.y - game.player.y),
                1.2,
            )

    def test_guard_closes_directly_like_a_bruiser(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            cx, cy = int(game.player.x), int(game.player.y)
            self.open_patch(game, cx, cy, radius=10)
            game.player.x, game.player.y = cx + 0.5, cy + 0.5
            enemy = _make_enemy(cx + 6.5, cy + 0.5, role="guard")
            enemy.attack_timer = 999.0
            game.enemies = [enemy]
            # Regression (4.8.9 tuning): guards must never statue just
            # outside melee reach — an aggro'd guard comes for the player.
            for _ in range(240):
                game.update_enemies(1.0 / 60.0)
            self.assertLess(
                math.hypot(enemy.x - game.player.x, enemy.y - game.player.y),
                1.6,
            )

    def test_flanker_curves_off_the_direct_approach_vector(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            cx, cy = int(game.player.x), int(game.player.y)
            self.open_patch(game, cx, cy, radius=10)
            game.player.x, game.player.y = cx + 0.5, cy + 0.5
            enemy = _make_enemy(cx + 6.5, cy + 0.5, role="flanker")
            enemy.attack_timer = 999.0
            game.enemies = [enemy]
            for _ in range(30):
                game.update_enemies(1.0 / 60.0)
            # A bruiser on the same row would keep y fixed; the flanker curves.
            self.assertGreater(abs(enemy.y - (cy + 0.5)), 0.15)

    def test_skirmisher_strafes_in_band_while_attack_recovers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            cx, cy = int(game.player.x), int(game.player.y)
            self.open_patch(game, cx, cy, radius=10)
            game.player.x, game.player.y = cx + 0.5, cy + 0.5
            enemy = _make_enemy(
                cx + 3.0, cy + 0.5, kind="ranged", role="skirmisher", attack_range=4.6
            )
            enemy.attack_timer = 999.0  # cooldown recovering -> drift
            game.enemies = [enemy]
            start_y = enemy.y
            for _ in range(30):
                game.update_enemies(1.0 / 60.0)
            self.assertGreater(abs(enemy.y - start_y), 0.15)

    def test_reposition_for_los_sidesteps_when_wall_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            cx, cy = int(game.player.x), int(game.player.y)
            self.open_patch(game, cx, cy, radius=8)
            game.player.x, game.player.y = cx + 0.5, cy + 0.5
            game.dungeon.tiles[cx + 2][cy] = Tile.WALL
            enemy = _make_enemy(
                cx + 3.5, cy + 0.5, kind="ranged", role="marksman", attack_range=5.8
            )
            enemy.attack_timer = 0.0  # attack-eligible but wall-blocked
            game.enemies = [enemy]
            start_y = enemy.y
            for _ in range(20):
                game.update_enemies(1.0 / 60.0)
                if enemy.windup_time > 0.0:
                    break
            self.assertGreater(abs(enemy.y - start_y), 0.05)

    # ------------------------------------------------------------------
    # A3: movement (distance field)
    # ------------------------------------------------------------------
    def test_distance_field_routes_around_wall(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            cx, cy = int(game.player.x), int(game.player.y)
            self.open_patch(game, cx, cy, radius=8)
            game.player.x, game.player.y = cx + 0.5, cy + 0.5
            # Vertical wall between player and enemy, open ends above/below.
            for ty in range(cy - 3, cy + 4):
                game.dungeon.tiles[cx + 3][ty] = Tile.WALL
            enemy = _make_enemy(cx + 6.5, cy + 0.5, speed=2.5)
            enemy.attack_timer = 999.0
            game.enemies = [enemy]
            game.familiars = []
            reached = False
            for _ in range(600):
                game.update_enemies(1.0 / 30.0)
                if (
                    math.hypot(enemy.x - game.player.x, enemy.y - game.player.y)
                    < 1.5
                ):
                    reached = True
                    break
            self.assertTrue(
                reached,
                f"enemy stuck at ({enemy.x:.2f}, {enemy.y:.2f})",
            )

    def test_enemy_rounds_a_near_corner_instead_of_wall_pressing(self) -> None:
        """Regression: player just around a corner, two tiles away.

        There the 8-connected field cost EQUALS the Chebyshev estimate, so
        the straightness gate alone would pick the greedy step head-on into
        the wall face forever; the wall-stall latch must kick the enemy onto
        field descent.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            cx, cy = int(game.player.x), int(game.player.y)
            self.open_patch(game, cx, cy, radius=8)
            game.player.x, game.player.y = cx + 0.5, cy + 0.5
            game.dungeon.tiles[cx + 1][cy] = Tile.WALL
            enemy = _make_enemy(cx + 2.5, cy + 0.5, attack_range=1.05, speed=2.0)
            enemy.attack_timer = 999.0
            game.enemies = [enemy]
            game.familiars = []
            reached = False
            for _ in range(300):
                game.update_enemies(1.0 / 30.0)
                if (
                    math.hypot(enemy.x - game.player.x, enemy.y - game.player.y)
                    < 1.3
                ):
                    reached = True
                    break
            self.assertTrue(
                reached,
                f"enemy wall-pressed at ({enemy.x:.2f}, {enemy.y:.2f})",
            )

    # ------------------------------------------------------------------
    # A4: perception
    # ------------------------------------------------------------------
    def test_taking_damage_engages_beyond_aggro_range(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            cx, cy = int(game.player.x), int(game.player.y)
            self.open_patch(game, cx, cy, radius=10)
            game.player.x, game.player.y = cx + 0.5, cy + 0.5
            enemy = _make_enemy(cx + 6.5, cy + 0.5, aggro_range=3.0)
            game.enemies = [enemy]
            start_x = enemy.x
            game.update_enemies(0.1)
            self.assertEqual(enemy.ai_state, "")
            self.assertEqual(enemy.x, start_x)
            game.damage_enemy(
                DamageContext(target=enemy, amount=5, damage_type="physical")
            )
            self.assertEqual(enemy.ai_state, "engaged")
            for _ in range(30):
                game.update_enemies(1.0 / 60.0)
            self.assertLess(enemy.x, start_x)

    def test_engaging_alerts_idle_packmates_nearby(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            cx, cy = int(game.player.x), int(game.player.y)
            self.open_patch(game, cx, cy, radius=12)
            game.player.x, game.player.y = cx + 0.5, cy + 0.5
            near = _make_enemy(cx + 4.5, cy + 0.5, aggro_range=5.0)
            packmate = _make_enemy(cx + 6.5, cy + 0.5, aggro_range=2.0)
            far = _make_enemy(cx + 11.5, cy + 0.5, aggro_range=2.0)
            game.enemies = [near, packmate, far]
            game.update_enemies(0.05)
            self.assertEqual(near.ai_state, "engaged")
            self.assertEqual(packmate.ai_state, "engaged")
            self.assertEqual(far.ai_state, "")

    def test_target_memory_expires_and_enemy_stands_down(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            cx, cy = int(game.player.x), int(game.player.y)
            self.open_patch(game, cx, cy, radius=10)
            game.player.x, game.player.y = cx + 0.5, cy + 0.5
            enemy = _make_enemy(cx + 2.5, cy + 0.5, speed=0.05)
            enemy.attack_timer = 999.0
            game.enemies = [enemy]
            game.update_enemies(0.05)
            self.assertEqual(enemy.ai_state, "engaged")
            # Target vanishes far beyond aggro: memory keeps the enemy
            # drifting for ENEMY_ALERT_MEMORY seconds, then it stands down.
            game.player.x = cx + 40.5
            elapsed = 0.0
            while elapsed < ENEMY_ALERT_MEMORY - 0.2:
                game.update_enemies(0.1)
                elapsed += 0.1
            self.assertEqual(enemy.ai_state, "engaged")
            for _ in range(6):
                game.update_enemies(0.1)
            self.assertEqual(enemy.ai_state, "")

    def test_bosses_carry_authored_ability_keys_from_definitions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            boss = game._make_boss(10.5, 10.5)
            self.assertEqual(
                tuple(boss.ability_keys), ("gate_strike", "shadow_volley")
            )
            self.assertTrue(
                all(key in ABILITY_INDEX for key in boss.ability_keys)
            )

    def test_ranged_tactic_resolution_never_yields_bandless_doctrine(self) -> None:
        enemy = _make_enemy(0.0, 0.0, kind="ranged", role="flanker")
        tactic = enemy_tactic(enemy)
        self.assertGreater(tactic.preferred_range, 0.0)


if __name__ == "__main__":
    unittest.main()
