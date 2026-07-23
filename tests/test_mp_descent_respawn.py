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

"""4.7 co-op descent rules.

A fallen player respawns at the start of the next floor when the survivor
descends, and the every-living-player-near-the-stairs gate applies only on
Hell difficulty — lower difficulties let either living player descend alone.
"""

import math
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from arch_rogue.content import ARCHETYPES, HELL_DIFFICULTY_NAME
from arch_rogue.game import Game
from arch_rogue.net import sync
from arch_rogue.net.mixin import MpSession
from arch_rogue.net.protocol import ROLE_HOST


def _make_host_game_with_partner(tmpdir: str) -> Game:
    game = Game(
        screen_size=(640, 360),
        headless=True,
        save_path=Path(tmpdir) / "run.json",
    )
    game.options_path = Path(tmpdir) / "options.json"
    game.restart(ARCHETYPES[0])
    game.story_intro_pending = False
    game.active_cutscene = None
    session = MpSession(role=ROLE_HOST)
    session.started = True
    session.player_id = "p1"
    game.mp_session = session
    game.mp_active = True
    game.mp_role = ROLE_HOST
    game.local_player_id = "p1"
    game.player.player_id = "p1"
    partner = sync.build_player_from_full(
        game, {"player_id": "p2", "x": game.player.x, "y": game.player.y}
    )
    game.players = [game.player, partner]
    return game


def _move_to_stairs(game: Game, player) -> None:
    stairs_x, stairs_y = game.dungeon.stairs
    player.x = stairs_x + 0.5
    player.y = stairs_y + 0.5


class DeadPartnerRespawnTests(unittest.TestCase):
    def test_dead_partner_respawns_on_next_floor_at_half_health(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_host_game_with_partner(tmpdir)
            partner = game.players[1]
            partner.hp = 0
            partner.death_anim_time = 3.0
            partner.status_effects = {"poison": 4.0}
            depth_before = game.current_depth
            game.descend_to_next_depth()
            self.assertEqual(game.current_depth, depth_before + 1)
            self.assertEqual(partner.hp, partner.max_hp // 2)
            self.assertEqual(partner.status_effects, {})
            self.assertEqual(partner.death_anim_time, 0.0)
            self.assertLess(
                math.hypot(
                    partner.x - game.player.x, partner.y - game.player.y
                ),
                3.0,
            )

    def test_host_actor_is_placed_when_joiner_triggers_descent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_host_game_with_partner(tmpdir)
            host_actor = game.players[0]
            joiner_actor = game.players[1]
            depth_before = game.current_depth
            with game.acting_as_player(joiner_actor):
                game.descend_to_next_depth()
            self.assertEqual(game.current_depth, depth_before + 1)
            start_x, start_y = game.dungeon.rooms[0].center
            self.assertLess(
                math.hypot(
                    joiner_actor.x - start_x - 0.5, joiner_actor.y - start_y - 0.5
                ),
                0.1,
            )
            self.assertLess(
                math.hypot(
                    host_actor.x - joiner_actor.x, host_actor.y - joiner_actor.y
                ),
                3.0,
            )


class StairsGateTests(unittest.TestCase):
    def test_lower_difficulties_allow_a_lone_living_player_to_descend(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_host_game_with_partner(tmpdir)
            partner = game.players[1]
            _move_to_stairs(game, game.player)
            partner.x = game.player.x + 8.0
            partner.y = game.player.y + 8.0
            depth_before = game.current_depth
            game.interact()
            self.assertEqual(game.current_depth, depth_before + 1)

    def test_hell_requires_every_living_player_near_the_stairs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_host_game_with_partner(tmpdir)
            game.hell_unlocked = True
            game.difficulty_name = HELL_DIFFICULTY_NAME
            partner = game.players[1]
            _move_to_stairs(game, game.player)
            partner.x = game.player.x + 8.0
            partner.y = game.player.y + 8.0
            depth_before = game.current_depth
            game.interact()
            self.assertEqual(game.current_depth, depth_before)
            _move_to_stairs(game, partner)
            game.interact()
            self.assertEqual(game.current_depth, depth_before + 1)

    def test_hell_ignores_the_dead_when_gating_the_stairs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_host_game_with_partner(tmpdir)
            game.hell_unlocked = True
            game.difficulty_name = HELL_DIFFICULTY_NAME
            partner = game.players[1]
            partner.hp = 0
            partner.x = game.player.x + 8.0
            partner.y = game.player.y + 8.0
            _move_to_stairs(game, game.player)
            depth_before = game.current_depth
            game.interact()
            self.assertEqual(game.current_depth, depth_before + 1)
            self.assertEqual(partner.hp, partner.max_hp // 2)


if __name__ == "__main__":
    unittest.main()
