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

"""4.7.12 co-op kill credit and refuge-room tests.

Delayed kills (projectiles in flight, poison ticks, familiar bites) must
credit XP and gold to the player who caused them — not whoever
``self.player`` happens to be during the host's update loop — and refuge
flavor rooms (garden heal, bar heal + stamina sap) must tick for the
partner's actor the same as for the host's own.
"""

from __future__ import annotations

import os
import tempfile
import types
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from arch_rogue.content import ARCHETYPES
from arch_rogue.dungeon import BAR_ROOM_KIND, GARDEN_ROOM_KIND
from arch_rogue.game import Game
from arch_rogue.models import Familiar, Projectile
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
    session.partner_connected = True
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


def _frail_enemy_near(game: Game, x: float, y: float):
    """Park an existing spawned enemy at (x, y) with 1 HP, no retaliation."""

    enemy = game.enemies[0]
    enemy.x = x
    enemy.y = y
    enemy.hp = 1
    enemy.attack_timer = 99.0
    enemy.statuses = {}
    return enemy


class ProjectileKillCreditTests(unittest.TestCase):
    def test_partner_bolt_kill_grants_partner_xp_and_gold(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_host_game_with_partner(tmpdir)
            partner = game.players[1]
            enemy = _frail_enemy_near(game, game.player.x + 1.0, game.player.y)
            enemy.xp = 10
            host_xp, host_gold = game.player.xp, game.player.gold
            partner_gold = partner.gold
            game.projectiles = [
                Projectile(
                    enemy.x,
                    enemy.y,
                    0.0,
                    0.0,
                    50,
                    "player",
                    (220, 220, 220),
                    owner_id="p2",
                )
            ]
            game.update_projectiles(1 / 60)
            self.assertFalse(enemy.alive)
            self.assertGreater(partner.xp, 0)
            self.assertGreater(partner.gold, partner_gold)
            self.assertEqual(game.player.xp, host_xp)
            self.assertEqual(game.player.gold, host_gold)
            # Acting context unwound cleanly.
            self.assertIs(game.player, game.players[0])

    def test_fallen_shooter_defers_credit_instead_of_reviving(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_host_game_with_partner(tmpdir)
            partner = game.players[1]
            partner.hp = 0
            enemy = _frail_enemy_near(game, game.player.x + 1.0, game.player.y)
            enemy.xp = 500  # enough to level whoever gets the credit
            game.projectiles = [
                Projectile(
                    enemy.x,
                    enemy.y,
                    0.0,
                    0.0,
                    50,
                    "player",
                    (220, 220, 220),
                    owner_id="p2",
                )
            ]
            game.update_projectiles(1 / 60)
            self.assertFalse(enemy.alive)
            # The corpse gained nothing (a level-up refill would revive it);
            # the host inherits the credit.
            self.assertEqual(partner.xp, 0)
            self.assertEqual(partner.hp, 0)
            self.assertGreater(game.player.xp + (game.player.level - 1), 0)


class PoisonKillCreditTests(unittest.TestCase):
    def test_partner_poison_tick_kill_credits_partner(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_host_game_with_partner(tmpdir)
            partner = game.players[1]
            enemy = _frail_enemy_near(game, game.player.x + 1.0, game.player.y)
            enemy.xp = 10
            enemy.statuses = {"poisoned": 2.0, "_poison_tick": 0.01}
            enemy.last_player_hit_id = "p2"
            host_xp = game.player.xp
            game.update_enemy_statuses(0.05)
            self.assertFalse(enemy.alive)
            self.assertGreater(partner.xp, 0)
            self.assertEqual(game.player.xp, host_xp)
            self.assertIs(game.player, game.players[0])


class FamiliarKillCreditTests(unittest.TestCase):
    def test_partner_familiar_kill_credits_the_summoner(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_host_game_with_partner(tmpdir)
            partner = game.players[1]
            enemy = _frail_enemy_near(game, game.player.x + 1.0, game.player.y)
            enemy.xp = 10
            game.familiars = [
                Familiar(
                    enemy.x - 0.8,
                    enemy.y,
                    30,
                    30,
                    12,
                    3.2,
                    1.25,
                    0.85,
                    owner_id="p2",
                )
            ]
            host_xp = game.player.xp
            game.update_familiars(1 / 60)
            self.assertFalse(enemy.alive)
            self.assertGreater(partner.xp, 0)
            self.assertEqual(game.player.xp, host_xp)


class RemoteRefugeRoomTests(unittest.TestCase):
    def _room(self, kind: str):
        return types.SimpleNamespace(kind=kind)

    def test_partner_heals_in_garden_without_host_glow(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_host_game_with_partner(tmpdir)
            partner = game.players[1]
            partner.hp = partner.max_hp - 20
            hp_before = partner.hp
            game.dungeon.special_room_at_point = (
                lambda x, y: self._room(GARDEN_ROOM_KIND)
            )
            game.garden_heal_glow = 0.0
            with game.acting_as_player(partner):
                game._mp_update_remote_player(partner, 5.5, 0.0, 0.0)
            self.assertGreater(partner.hp, hp_before)
            # The greenish aura is the local player's screen effect only.
            self.assertEqual(game.garden_heal_glow, 0.0)

    def test_partner_bar_time_heals_slowly_and_saps_stamina(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_host_game_with_partner(tmpdir)
            partner = game.players[1]
            partner.hp = partner.max_hp - 20
            partner.stamina = partner.max_stamina
            hp_before = partner.hp
            game.dungeon.special_room_at_point = (
                lambda x, y: self._room(BAR_ROOM_KIND)
            )
            with game.acting_as_player(partner):
                game._mp_update_remote_player(partner, 5.5, 0.0, 0.0)
            self.assertEqual(
                partner.hp - hp_before, max(1, partner.max_hp // 50 + 1)
            )
            self.assertEqual(partner.stamina, 0.0)

    def test_host_and_partner_accumulators_are_independent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_host_game_with_partner(tmpdir)
            partner = game.players[1]
            game.player.garden_heal_accumulator = 4.7
            partner.garden_heal_accumulator = 0.0
            partner.hp = partner.max_hp - 20
            game.dungeon.special_room_at_point = (
                lambda x, y: self._room(GARDEN_ROOM_KIND)
            )
            hp_before = partner.hp
            with game.acting_as_player(partner):
                game.update_refuge_room_effects(0.5)
            # The partner's half second does not ride the host's 4.7 bank.
            self.assertEqual(partner.hp, hp_before)
            self.assertEqual(game.player.garden_heal_accumulator, 4.7)


if __name__ == "__main__":
    unittest.main()
