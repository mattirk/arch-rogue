# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
#
# AI Provenance & Liability Notice:
# This repository contains code generated, assisted, or refactored by Artificial
# Intelligence models. Provided strictly "AS IS" under Apache 2.0 with no warranty
# of clean IP provenance or non-infringement; downstream users assume all legal
# and financial risk and should perform their own compliance audits.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""5.0 speed rework: every displayed speed source feeds real locomotion.

Player ground speed = PLAYER_MOVE_SPEED * (1 + player_move_speed()), where
the bonus folds the archetype rating, equipment ``move_speed`` affixes, the
Rogue/Ranger discipline speed nodes (rescaled), and the Haste Shrine's capped
blessing into one channel clamped to [-0.25, 0.30] — the exact window
multiplayer prediction budgets for (_PREDICTION_EQUIPMENT_SPEED_CAP = 1.30).
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame

from arch_rogue.combat.costs import (
    ARCHETYPE_MOVE_RATING_BASELINE,
    DISCIPLINE_SPEED_TO_MOVE,
    HASTE_SHRINE_MOVE_BONUS,
    HASTE_SHRINE_MOVE_BONUS_CAP,
    PLAYER_MOVE_BONUS_MAX,
    PLAYER_MOVE_BONUS_MIN,
    archetype_move_bonus,
)
from arch_rogue.content import (
    ARCHETYPES,
    ARCHETYPE_SPEED_BY_NAME,
    DISCIPLINE_SPEED_BONUS_BY_KEY,
)
from arch_rogue.game import Game
from arch_rogue.models import Item, Shrine
from arch_rogue.net import sync


def make_game(tmpdir: str, archetype_index: int = 0, seed: int = 5001) -> Game:
    game = Game(
        screen_size=(820, 540),
        headless=True,
        save_path=Path(tmpdir) / "run.json",
    )
    game.options_path = Path(tmpdir) / "options.json"
    game.rng.seed(seed)
    game.restart(ARCHETYPES[archetype_index])
    if game.story_intro_pending:
        assert game.choose_story_relic_path(0)
    game.active_cutscene = None
    return game


class MoveSpeedBonusTests(unittest.TestCase):
    def test_archetype_ratings_map_to_honest_percentages(self) -> None:
        # The class-select "Move %" figures come straight from the ratings.
        self.assertAlmostEqual(
            archetype_move_bonus(ARCHETYPE_MOVE_RATING_BASELINE), 0.0
        )
        rogue = archetype_move_bonus(ARCHETYPE_SPEED_BY_NAME["Rogue"])
        arcanist = archetype_move_bonus(ARCHETYPE_SPEED_BY_NAME["Arcanist"])
        self.assertGreater(rogue, 0.10)
        self.assertLess(rogue, 0.15)
        self.assertLess(arcanist, 0.0)

    def test_rogue_outpaces_arcanist_on_the_ground(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            rogue = make_game(tmpdir, archetype_index=1)
            base = rogue.player_move_speed()
            self.assertAlmostEqual(
                base,
                archetype_move_bonus(ARCHETYPE_SPEED_BY_NAME["Rogue"]),
                places=6,
            )
        with tempfile.TemporaryDirectory() as tmpdir:
            arcanist = make_game(tmpdir, archetype_index=2)
            self.assertLess(arcanist.player_move_speed(), base)

    def test_discipline_speed_nodes_are_real_and_rescaled(self) -> None:
        self.assertEqual(len(DISCIPLINE_SPEED_BONUS_BY_KEY), 11)
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir, archetype_index=1)  # Rogue
            before = game.player_move_speed()
            game.player.skill_upgrades.append("rogue_shadowstep")
            after = game.player_move_speed()
            self.assertAlmostEqual(
                after - before,
                DISCIPLINE_SPEED_BONUS_BY_KEY["rogue_shadowstep"]
                * DISCIPLINE_SPEED_TO_MOVE,
                places=6,
            )

    def test_haste_shrine_blessing_is_capped(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            for _ in range(6):
                shrine = Shrine(game.player.x, game.player.y, "Haste Shrine")
                game.activate_shrine(shrine)
            self.assertAlmostEqual(
                game.player.shrine_move_bonus, HASTE_SHRINE_MOVE_BONUS_CAP
            )
            self.assertGreater(
                HASTE_SHRINE_MOVE_BONUS_CAP, HASTE_SHRINE_MOVE_BONUS
            )

    def test_total_bonus_clamps_to_the_prediction_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir, archetype_index=1)  # Rogue, fastest base
            game.player.equipment["armor"] = Item(
                "Foxstep Leathers", "armor", defense=15, rarity="Unique",
                move_speed=0.12,
            )
            game.player.equipment["weapon"] = Item(
                "Nightglass Daggers", "weapon", power=30, rarity="Unique",
                move_speed=0.04,
            )
            for key in DISCIPLINE_SPEED_BONUS_BY_KEY:
                if key.startswith("rogue_"):
                    game.player.skill_upgrades.append(key)
            game.player.shrine_move_bonus = HASTE_SHRINE_MOVE_BONUS_CAP
            self.assertEqual(game.player_move_speed(), PLAYER_MOVE_BONUS_MAX)
            # The multiplayer prediction ceiling stays valid.
            self.assertAlmostEqual(
                1.0 + PLAYER_MOVE_BONUS_MAX,
                sync._PREDICTION_EQUIPMENT_SPEED_CAP,
            )
            # Slows clamp on the other side.
            game.player.skill_upgrades.clear()
            game.player.shrine_move_bonus = 0.0
            game.player.equipment["armor"] = Item(
                "Leaden Shell", "armor", defense=2, rarity="Cursed",
                move_speed=-0.5,
            )
            game.player.equipment["weapon"] = None
            self.assertEqual(game.player_move_speed(), PLAYER_MOVE_BONUS_MIN)

    def test_ground_distance_actually_scales_with_the_bonus(self) -> None:
        # Same input, same dt, same seed (same dungeon): a Rogue covers more
        # floor than an Arcanist. Movement is injected through the analog
        # stick vector, which overrides keyboard state in update_player.
        def eastward_run_start(game: Game) -> tuple[float, float]:
            from arch_rogue.dungeon import MAP_H, MAP_W

            for y in range(MAP_H):
                for x in range(MAP_W - 4):
                    if all(
                        game.dungeon.is_floor(x + step + 0.5, y + 0.5)
                        for step in range(4)
                    ):
                        return x + 0.5, y + 0.5
            raise AssertionError("no eastward floor run found")

        distances = {}
        for label, index in (("rogue", 1), ("arcanist", 2)):
            with tempfile.TemporaryDirectory() as tmpdir:
                game = make_game(tmpdir, archetype_index=index, seed=5002)
                game.enemies = []
                game.player.x, game.player.y = eastward_run_start(game)
                game.input.left_vec = lambda: (1.0, 0.0)
                start_x = game.player.x
                for _ in range(15):
                    game.update_player(1 / 60)
                distances[label] = game.player.x - start_x
        self.assertGreater(distances["rogue"], 0.0)
        self.assertGreater(distances["rogue"], distances["arcanist"])


class ShrineMoveBonusPersistenceTests(unittest.TestCase):
    def test_save_roundtrip_and_old_save_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            shrine = Shrine(game.player.x, game.player.y, "Haste Shrine")
            game.activate_shrine(shrine)
            expected = game.player.shrine_move_bonus
            self.assertGreater(expected, 0.0)
            game.save_run()

            loaded = Game(
                screen_size=(820, 540),
                headless=True,
                save_path=game.save_path,
            )
            loaded.options_path = Path(tmpdir) / "options2.json"
            self.assertTrue(loaded.load_run())
            self.assertAlmostEqual(
                loaded.player.shrine_move_bonus, expected
            )

    def test_wire_payloads_replicate_the_blessing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.player.shrine_move_bonus = 0.06
            full = sync.player_full_dict(game, game.player)
            self.assertAlmostEqual(full["shrine_move_bonus"], 0.06)
            slow = sync.player_slow_dict(game, game.player)
            self.assertAlmostEqual(slow["shrine_move_bonus"], 0.06)

            game.player.shrine_move_bonus = 0.0
            sync.apply_player_slow(game, game.player, slow)
            self.assertAlmostEqual(game.player.shrine_move_bonus, 0.06)
            # Old-format payloads without the key leave the value untouched.
            sync.apply_player_slow(
                game, game.player, {"speed": game.player.speed}
            )
            self.assertAlmostEqual(game.player.shrine_move_bonus, 0.06)


if __name__ == "__main__":
    unittest.main()
