"""Deterministic combat broad-phase regression tests."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from arch_rogue.combat._utils import BOSS_FOOTPRINT_HIT_RADIUS
from arch_rogue.combat.movement import _MovementCombatMixin
from arch_rogue.combat.spatial import EnemySpatialIndex
from arch_rogue.constants import PLAYER_HIT_RADIUS
from arch_rogue.models import Enemy, Player


def make_enemy(
    x: float,
    y: float,
    name: str,
    *,
    size: int = 1,
) -> Enemy:
    return Enemy(
        name,
        "melee",
        x,
        y,
        20,
        20,
        1.0,
        3,
        8,
        1.1,
        1.0,
        size=size,
    )


class OpenDungeon:
    @staticmethod
    def blocked_for_radius(
        _x: float,
        _y: float,
        _radius: float = 0.27,
        *,
        block_stairs: bool = False,
        wall_depth_relief: float = 0.0,
    ) -> bool:
        return False


class MovementHarness(_MovementCombatMixin):
    FRIENDLY_NPC_RADIUS = 0.34

    def __init__(self, enemies: list[Enemy], players: list[Player]) -> None:
        self.enemies = enemies
        self.players = players
        self.shopkeepers: list[object] = []
        self.dungeon = OpenDungeon()

    def active_players(self) -> list[Player]:
        return self.players

    @staticmethod
    def iter_friendly_npcs():
        return iter(())

    @staticmethod
    def iter_npc_allies():
        return iter(())


class EnemySpatialIndexTests(unittest.TestCase):
    def test_candidates_preserve_source_order_across_cells(self) -> None:
        first = make_enemy(2.1, 1.0, "first")
        outside = make_enemy(8.0, 8.0, "outside")
        second = make_enemy(0.2, 1.0, "second")
        third = make_enemy(1.9, 2.1, "third")
        enemies = [first, outside, second, third]

        index = EnemySpatialIndex(enemies)

        self.assertEqual(
            index.candidates(1.5, 1.5, 2.0),
            [first, second, third],
        )

    def test_update_moves_actor_without_changing_order(self) -> None:
        first = make_enemy(8.0, 8.0, "first")
        second = make_enemy(0.5, 0.5, "second")
        enemies = [first, second]
        index = EnemySpatialIndex(enemies)

        first.x = 0.75
        first.y = 0.75
        index.update(first)

        self.assertEqual(index.candidates(0.5, 0.5, 0.8), [first, second])
        self.assertEqual(index.candidates(8.0, 8.0, 0.5), [])

    def test_collection_change_requires_rebuild(self) -> None:
        enemies = [make_enemy(1.0, 1.0, "first")]
        index = EnemySpatialIndex(enemies)
        self.assertTrue(index.matches(enemies))

        enemies.append(make_enemy(2.0, 2.0, "second"))

        self.assertFalse(index.matches(enemies))
        self.assertFalse(index.matches(list(enemies)))

    def test_negative_coordinates_use_floor_cells(self) -> None:
        enemy = make_enemy(-0.1, -0.1, "negative")
        index = EnemySpatialIndex([enemy])

        self.assertEqual(index.candidates(-0.2, -0.2, 0.2), [enemy])
        self.assertEqual(index.candidates(0.5, 0.5, 0.1), [])

    def test_candidate_entries_can_resume_source_order_after_a_shove(self) -> None:
        first = make_enemy(0.0, 0.0, "first")
        second = make_enemy(0.1, 0.1, "second")
        third = make_enemy(0.2, 0.2, "third")
        index = EnemySpatialIndex([first, second, third])

        self.assertEqual(
            index.candidate_entries(0.0, 0.0, 1.0, after_order=0),
            [(1, second), (2, third)],
        )


class SpatialContactIntegrationTests(unittest.TestCase):
    @staticmethod
    def dense_roster(first: Enemy, second: Enemy) -> list[Enemy]:
        distant = [
            make_enemy(30.0 + index, 30.0, f"distant-{index}")
            for index in range(58)
        ]
        return [first, second, *distant]

    def test_player_shove_requeries_later_enemies_at_new_position(self) -> None:
        first = make_enemy(-0.1, 0.0, "first", size=2)
        second = make_enemy(2.05, 0.0, "second", size=2)
        player = Player(0.0, 0.0)
        harness = MovementHarness(self.dense_roster(first, second), [player])

        harness.resolve_actor_contacts(player)

        expected_x = second.x - (
            PLAYER_HIT_RADIUS + BOSS_FOOTPRINT_HIT_RADIUS
        )
        self.assertAlmostEqual(player.x, expected_x)

    def test_player_contact_precedes_enemy_query_for_enemy_mover(self) -> None:
        actor = make_enemy(0.0, 0.0, "actor", size=2)
        later_enemy = make_enemy(2.05, 0.0, "later", size=2)
        player = Player(-0.1, 0.0)
        harness = MovementHarness(self.dense_roster(actor, later_enemy), [player])

        harness.resolve_actor_contacts(actor)

        expected_x = later_enemy.x - BOSS_FOOTPRINT_HIT_RADIUS * 2.0
        self.assertAlmostEqual(actor.x, expected_x)

    def test_small_roster_uses_canonical_full_list_without_an_index(self) -> None:
        enemies = [
            make_enemy(float(index), 0.0, f"enemy-{index}")
            for index in range(59)
        ]
        harness = MovementHarness(enemies, [])

        candidates = harness.nearby_enemies(0.0, 0.0, 0.1)

        self.assertIs(candidates, enemies)
        self.assertIsNone(getattr(harness, "_enemy_spatial_index", None))

    def test_large_roster_activates_local_index(self) -> None:
        enemies = [
            make_enemy(float(index), 0.0, f"enemy-{index}")
            for index in range(60)
        ]
        harness = MovementHarness(enemies, [])

        candidates = harness.nearby_enemies(0.0, 0.0, 0.1)

        self.assertEqual(candidates, [enemies[0]])
        self.assertIsNotNone(harness._enemy_spatial_index)


if __name__ == "__main__":
    unittest.main()
