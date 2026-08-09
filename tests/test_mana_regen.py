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

"""5.0 mana economy: slow idle regen, Discipline-tree recovery, potion value."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from arch_rogue.combat.costs import (
    ARCANIST_MANA_REGEN,
    MANA_REGEN_UPGRADES,
    PLAYER_MANA_REGEN,
    player_recovery_rates,
)
from arch_rogue.content import ARCHETYPES, DISCIPLINES
from arch_rogue.game import Game


def _actor(class_name: str, upgrades: list[str] | None = None) -> SimpleNamespace:
    keys = list(upgrades or [])
    return SimpleNamespace(
        class_name=class_name,
        has_upgrade=lambda key, _keys=keys: key in _keys,
    )


class ManaRegenRateTests(unittest.TestCase):
    def test_base_rates_no_longer_trivialize_potions(self) -> None:
        # A 24-mana Lesser Mana Potion must be worth several seconds of idle
        # regen for every class (4.x refilled whole pools in 8-12 s).
        for archetype in ARCHETYPES:
            with self.subTest(archetype=archetype.name):
                _stamina, mana = player_recovery_rates(_actor(archetype.name))
                self.assertGreaterEqual(24 / mana, 6.0)
                self.assertGreaterEqual(archetype.max_mana / mana, 15.0)

    def test_arcanist_keeps_a_small_innate_edge(self) -> None:
        self.assertGreater(ARCANIST_MANA_REGEN, PLAYER_MANA_REGEN)
        _stamina, arcanist = player_recovery_rates(_actor("Arcanist"))
        _stamina, warden = player_recovery_rates(_actor("Warden"))
        self.assertEqual(arcanist, ARCANIST_MANA_REGEN)
        self.assertEqual(warden, PLAYER_MANA_REGEN)

    def test_discipline_choices_restore_a_casting_loop(self) -> None:
        # Both regen nodes stacked bring the Arcanist back near the 4.x pace
        # (8/s base then); the Acolyte builds a mid-tier loop.
        _s, arcanist_full = player_recovery_rates(
            _actor("Arcanist", ["arcanist_focus", "arcanist_ward"])
        )
        self.assertAlmostEqual(arcanist_full, 3.5 + 2.5 + 1.5)
        _s, acolyte_full = player_recovery_rates(
            _actor("Acolyte", ["acolyte_veil", "acolyte_curse"])
        )
        self.assertAlmostEqual(acolyte_full, 2.5 + 2.0 + 1.5)
        # Cross-class keys never leak (an Acolyte cannot take Arcanist nodes,
        # but the helper itself must also not care about unknown keys).
        _s, unrelated = player_recovery_rates(
            _actor("Rogue", ["arcanist_focus", "acolyte_veil"])
        )
        self.assertAlmostEqual(unrelated, PLAYER_MANA_REGEN + 2.5 + 2.0)

    def test_every_regen_upgrade_is_a_real_degree_one_discipline(self) -> None:
        by_key = {node.key: node for node in DISCIPLINES}
        for key in MANA_REGEN_UPGRADES:
            with self.subTest(node=key):
                self.assertIn(key, by_key)
                node = by_key[key]
                self.assertEqual(node.degree, 1)
                self.assertIn(node.archetype, ("Arcanist", "Acolyte"))
                # The player-facing copy must claim the recovery effect.
                description = node.description.lower()
                self.assertTrue(
                    any(
                        phrase in description
                        for phrase in ("recover", "return", "seeps back", "trickles back")
                    ),
                    f"{key} description does not mention mana recovery: "
                    f"{node.description!r}",
                )


class ManaRegenSimulationTests(unittest.TestCase):
    def test_update_player_applies_the_shared_rates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = Game(
                screen_size=(820, 540),
                headless=True,
                save_path=Path(tmpdir) / "run.json",
            )
            game.options_path = Path(tmpdir) / "options.json"
            game.rng.seed(4101)
            game.restart(ARCHETYPES[2])  # Arcanist
            if game.story_intro_pending:
                self.assertTrue(game.choose_story_relic_path(0))
            game.active_cutscene = None

            game.player.mana = 10.0
            game.update_player(1.0)
            expected = 10.0 + player_recovery_rates(game.player)[1]
            self.assertAlmostEqual(game.player.mana, expected, places=4)

            game.player.skill_upgrades.append("arcanist_focus")
            game.player.mana = 10.0
            game.update_player(1.0)
            boosted = 10.0 + player_recovery_rates(game.player)[1]
            self.assertAlmostEqual(game.player.mana, boosted, places=4)
            self.assertGreater(boosted, expected)


if __name__ == "__main__":
    unittest.main()
