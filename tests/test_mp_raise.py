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

"""4.7 co-op Raise.

Each player carries one Raise per descent: reviving the fallen partner to
half health with the celebratory "act" flourish (the Ranger pets instead).
Charges never refresh between floors; rare co-op Vigil Shrines grant more.
"""

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game
from arch_rogue.models import Shrine
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


def _fell(player) -> None:
    player.hp = 0
    player.death_anim_time = 2.5
    player.status_effects = {"poison": 3.0}


class RaisePartnerTests(unittest.TestCase):
    def test_interact_raises_dead_partner_to_half_health(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_host_game_with_partner(tmpdir)
            partner = game.players[1]
            _fell(partner)
            partner.x = game.player.x + 1.0
            partner.y = game.player.y
            game.interact()
            self.assertEqual(partner.hp, partner.max_hp // 2)
            self.assertEqual(partner.status_effects, {})
            self.assertEqual(partner.death_anim_time, 0.0)
            self.assertEqual(game.player.raise_charges, 0)
            # The raiser (a non-Ranger, local to the host) plays the "act"
            # flourish through the Game-global pose fields.
            self.assertEqual(game.player_action_state, "act")
            self.assertGreater(game.player_action_ttl, 0.0)

    def test_ranger_raiser_plays_the_pet_clip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_host_game_with_partner(tmpdir)
            game.player.class_name = "Ranger"
            partner = game.players[1]
            _fell(partner)
            partner.x = game.player.x + 1.0
            partner.y = game.player.y
            game.interact()
            self.assertEqual(partner.hp, partner.max_hp // 2)
            self.assertEqual(game.player_action_state, "pet")

    def test_raise_is_spent_and_out_of_range_corpse_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_host_game_with_partner(tmpdir)
            partner = game.players[1]
            _fell(partner)
            partner.x = game.player.x + 8.0
            partner.y = game.player.y
            self.assertIsNone(game.nearby_raisable_partner())
            partner.x = game.player.x + 1.0
            game.player.raise_charges = 0
            self.assertIsNone(game.nearby_raisable_partner())
            game.interact()
            self.assertEqual(partner.hp, 0)

    def test_joiner_actor_can_raise_the_host_through_acting(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_host_game_with_partner(tmpdir)
            host_actor = game.players[0]
            joiner_actor = game.players[1]
            _fell(host_actor)
            joiner_actor.x = host_actor.x + 1.0
            joiner_actor.y = host_actor.y
            with game.acting_as_player(joiner_actor):
                game.interact()
            self.assertEqual(host_actor.hp, host_actor.max_hp // 2)
            self.assertEqual(joiner_actor.raise_charges, 0)
            self.assertEqual(host_actor.raise_charges, 1)
            # The joiner's pose lands on its actor fields, not the globals.
            self.assertEqual(joiner_actor.action_state, "act")

    def test_charges_survive_descent_and_do_not_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_host_game_with_partner(tmpdir)
            partner = game.players[1]
            _fell(partner)
            partner.x = game.player.x + 1.0
            partner.y = game.player.y
            game.interact()
            self.assertEqual(game.player.raise_charges, 0)
            game.descend_to_next_depth()
            self.assertEqual(game.player.raise_charges, 0)
            self.assertEqual(partner.raise_charges, 1)

    def test_vigil_shrine_grants_another_raise(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_host_game_with_partner(tmpdir)
            game.player.raise_charges = 0
            shrine = Shrine(game.player.x, game.player.y, "Vigil Shrine")
            game.shrines.append(shrine)
            game.activate_shrine(shrine)
            self.assertEqual(game.player.raise_charges, 1)
            self.assertTrue(shrine.used)

    def test_raise_charges_replicate_in_both_sync_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_host_game_with_partner(tmpdir)
            partner = game.players[1]
            partner.raise_charges = 2
            fast = sync.player_fast_dict(game, partner)
            self.assertEqual(fast["raises"], 2)
            partner.raise_charges = 1
            sync.apply_player_fast(game, partner, fast)
            self.assertEqual(partner.raise_charges, 2)
            full = sync.player_full_dict(game, partner)
            self.assertEqual(full["raise_charges"], 2)
            rebuilt = sync.build_player_from_full(game, full)
            self.assertEqual(rebuilt.raise_charges, 2)


class ActClipResolutionTests(unittest.TestCase):
    def test_act_clip_replays_south_frames_for_every_facing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_host_game_with_partner(tmpdir)
            assets = game.sprites.assets
            frame = assets.resolve_actor("Warden", "act", "east", 0.0)
            self.assertIsNotNone(frame)
            self.assertEqual(frame.key[2], "act")
            seconds = assets.actor_clip_seconds("Warden", "act")
            self.assertIsNotNone(seconds)
            self.assertGreater(seconds, 0.0)


if __name__ == "__main__":
    unittest.main()
