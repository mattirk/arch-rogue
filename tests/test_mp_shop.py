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

"""4.7.12 co-op shop and story-guest interaction tests.

The joiner runs its own local shop UI and ships ``shop_open``/``shop_buy``/
``shop_sell`` intents; the host pauses the shared simulation while the
partner trades and opens the story-guest dialogue itself when the partner
hails a guest. Headless host-side games with a synthetic partner actor,
mirroring ``test_mp_raise``.
"""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game
from arch_rogue.models import Item, Shopkeeper, StoryChoice, StoryGuest
from arch_rogue.net import sync
from arch_rogue.net.mixin import MpSession
from arch_rogue.net.protocol import ROLE_HOST, ROLE_JOIN


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


def _place_keeper(game: Game, actor) -> Shopkeeper:
    keeper = Shopkeeper(
        x=actor.x + 1.0,
        y=actor.y,
        name="Vend",
        role="Trader",
        inventory=[Item("Small Potion", "potion", heal=30)],
    )
    game.shopkeepers.append(keeper)
    return keeper


class RemoteInteractShopGuardTests(unittest.TestCase):
    def test_remote_interact_near_keeper_never_opens_host_shop(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_host_game_with_partner(tmpdir)
            partner = game.players[1]
            partner.x = game.player.x + 6.0
            _place_keeper(game, partner)
            with game.acting_as_player(partner):
                game.interact()
            self.assertFalse(game.shop_open)
            self.assertIsNone(game.active_shopkeeper)

    def test_remote_interact_on_shop_sign_never_opens_host_shop(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_host_game_with_partner(tmpdir)
            partner = game.players[1]
            partner.x = game.player.x + 6.0
            keeper = _place_keeper(game, partner)
            sign = Item(
                "Shop sign", "shop_sign", x=partner.x + 0.4, y=partner.y
            )
            keeper.x = partner.x + 2.0  # out of keeper radius, sign in reach
            game.items.append(sign)
            with game.acting_as_player(partner):
                game.interact()
            self.assertFalse(game.shop_open)
            # The sign is scenery, never picked up.
            self.assertIn(sign, game.items)

    def test_host_interact_still_opens_its_own_shop(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_host_game_with_partner(tmpdir)
            keeper = _place_keeper(game, game.player)
            game.interact()
            self.assertTrue(game.shop_open)
            self.assertIs(game.active_shopkeeper, keeper)


class RemoteShopActionTests(unittest.TestCase):
    def test_shop_open_marks_keeper_met_without_host_ui(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_host_game_with_partner(tmpdir)
            partner = game.players[1]
            keeper = _place_keeper(game, partner)
            with game.acting_as_player(partner):
                game._mp_remote_shop_action("shop_open", str(game.shopkeepers.index(keeper)))
            self.assertTrue(keeper.met)
            self.assertFalse(game.shop_open)

    def test_shop_buy_transfers_item_and_gold_on_partner_actor(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_host_game_with_partner(tmpdir)
            partner = game.players[1]
            keeper = _place_keeper(game, partner)
            item = keeper.inventory[0]
            price = game.shop_price(keeper, item)
            partner.gold = price + 5
            host_gold = game.player.gold
            with game.acting_as_player(partner):
                game._mp_remote_shop_action(
                    "shop_buy", f"{game.shopkeepers.index(keeper)}:0:{item.display_name[:40]}"
                )
            self.assertIn(item, partner.inventory)
            self.assertNotIn(item, keeper.inventory)
            self.assertEqual(partner.gold, 5)
            self.assertEqual(game.player.gold, host_gold)

    def test_shop_sell_pays_the_partner(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_host_game_with_partner(tmpdir)
            partner = game.players[1]
            keeper = _place_keeper(game, partner)
            item = Item("Old Blade", "weapon", power=3)
            partner.inventory.append(item)
            partner.gold = 0
            with game.acting_as_player(partner):
                game._mp_remote_shop_action(
                    "shop_sell", f"{game.shopkeepers.index(keeper)}:0:{item.display_name[:40]}"
                )
            self.assertIn(item, keeper.inventory)
            self.assertNotIn(item, partner.inventory)
            self.assertEqual(partner.gold, game.shop_buyback_value(keeper, item))

    def test_stale_name_out_of_range_and_bad_target_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_host_game_with_partner(tmpdir)
            partner = game.players[1]
            keeper = _place_keeper(game, partner)
            partner.gold = 999
            with game.acting_as_player(partner):
                ki = game.shopkeepers.index(keeper)
                game._mp_remote_shop_action("shop_buy", f"{ki}:0:Wrong Name")
                game._mp_remote_shop_action("shop_buy", f"{ki}:7:Small Potion")
                game._mp_remote_shop_action("shop_buy", "junk")
                game._mp_remote_shop_action("shop_buy", None)
            self.assertEqual(len(keeper.inventory), 1)
            self.assertEqual(partner.gold, 999)
            keeper.x = partner.x + 9.0
            with game.acting_as_player(partner):
                game._mp_remote_shop_action("shop_buy", f"{game.shopkeepers.index(keeper)}:0:Small Potion")
            self.assertEqual(len(keeper.inventory), 1)


class RemotePauseTests(unittest.TestCase):
    def test_partner_shop_pauses_host_and_still_resolves_trades(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_host_game_with_partner(tmpdir)
            partner = game.players[1]
            keeper = _place_keeper(game, partner)
            item = keeper.inventory[0]
            partner.gold = game.shop_price(keeper, item)
            session = game.mp_session
            session.remote_pause_reason = "shop"
            session.remote_pause_at = time.monotonic()
            session.intent_actions.append(
                ("shop_buy", f"{game.shopkeepers.index(keeper)}:0:{item.display_name[:40]}", 0.0, 0.0)
            )
            session.intent_actions.append(("melee", None, 1.0, 0.0))
            self.assertEqual(game.mp_remote_pause_reason(), "shop")
            host_x = game.player.x
            game.elapsed = 10.0
            game.update(1 / 60)
            # The trade resolved during the paused frame...
            self.assertIn(item, partner.inventory)
            self.assertEqual(partner.gold, 0)
            # ...while the melee stays queued for the resume and the host
            # actor did not advance.
            self.assertEqual(list(session.intent_actions), [("melee", None, 1.0, 0.0)])
            self.assertEqual(game.player.x, host_x)

    def test_stale_partner_pause_expires(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_host_game_with_partner(tmpdir)
            session = game.mp_session
            session.remote_pause_reason = "shop"
            session.remote_pause_at = time.monotonic() - 5.0
            self.assertEqual(game.mp_remote_pause_reason(), "")


class RemoteStoryGuestTests(unittest.TestCase):
    def test_remote_interact_opens_story_dialogue_on_the_host(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_host_game_with_partner(tmpdir)
            partner = game.players[1]
            partner.x = game.player.x + 6.0
            guest = StoryGuest(
                x=partner.x + 0.8,
                y=partner.y,
                depth=game.current_depth,
                beat_index=0,
                name="Wanderer",
                role="Guest",
                motive="testing",
                dialogue="hello",
                choices=[
                    StoryChoice("aid", "Aid", "help", "aided"),
                    StoryChoice("press", "Press", "push", "pressed"),
                    StoryChoice("dismiss", "Dismiss", "leave", "left"),
                ],
            )
            game.story_guests.append(guest)
            with game.acting_as_player(partner):
                game.interact()
            self.assertTrue(guest.met)
            # The modal opens host-side (cutscene when authored content
            # resolves, floater prompt otherwise) and pauses the shared run
            # through the existing snapshot pause reason.
            if game.active_cutscene is None:
                self.assertTrue(
                    any("choose 1-3" in f.text for f in game.floaters)
                )


class JoinerLocalShopTests(unittest.TestCase):
    def _make_joiner_game(self, tmpdir: str) -> Game:
        game = Game(
            screen_size=(640, 360),
            headless=True,
            save_path=Path(tmpdir) / "join_run.json",
        )
        game.options_path = Path(tmpdir) / "join_options.json"
        game.restart(ARCHETYPES[0])
        game.story_intro_pending = False
        game.active_cutscene = None
        session = MpSession(role=ROLE_JOIN)
        session.started = True
        session.partner_connected = True
        game.mp_session = session
        game.mp_active = True
        game.mp_role = ROLE_JOIN
        game.local_player_id = "p2"
        game.player.player_id = "p2"
        host_actor = sync.build_player_from_full(
            game, {"player_id": "p1", "x": game.player.x, "y": game.player.y}
        )
        game.players = [host_actor, game.player]
        return game

    def test_joiner_interact_opens_local_shop_and_reports_pause(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self._make_joiner_game(tmpdir)
            keeper = _place_keeper(game, game.player)
            game.interact()
            self.assertTrue(game.shop_open)
            self.assertIs(game.active_shopkeeper, keeper)
            self.assertEqual(game.mp_local_pause_reason(), "shop")
            game.close_shop()
            self.assertEqual(game.mp_local_pause_reason(), "")

    def test_joiner_update_closes_shop_when_out_of_range(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self._make_joiner_game(tmpdir)
            keeper = _place_keeper(game, game.player)
            game.open_shop(keeper)
            game.mp_update_joiner(1 / 60)
            self.assertTrue(game.shop_open)
            keeper.x = game.player.x + 9.0
            game.mp_update_joiner(1 / 60)
            self.assertFalse(game.shop_open)


class ShopInventorySyncTests(unittest.TestCase):
    def test_slow_snapshot_replicates_keeper_inventories(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_host_game_with_partner(tmpdir)
            keeper = _place_keeper(game, game.player)
            state = sync.build_snapshot_state(game, include_slow=True)
            self.assertEqual(len(state["slow"]["shop_inv"]), len(game.shopkeepers))
            # A trade changes the world-length change signal, forcing an
            # immediate slow payload.
            before = sync.world_list_lengths(game)
            keeper.inventory.pop()
            self.assertNotEqual(before, sync.world_list_lengths(game))
            # Applying the pre-trade payload restores the keeper list in
            # place, as the joiner's open shop UI requires.
            held = keeper.inventory
            sync.apply_snapshot_state(game, state)
            self.assertIs(keeper.inventory, held)
            self.assertEqual(
                [item.name for item in keeper.inventory], ["Small Potion"]
            )


if __name__ == "__main__":
    unittest.main()
