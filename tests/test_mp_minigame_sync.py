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

"""Host-authoritative co-op transport for the 4.9.x story mini-games."""

from __future__ import annotations

import os
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import Mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game
from arch_rogue.models import SpecialRoom
from arch_rogue.net import sync
from arch_rogue.net.messages import IntentMessage
from arch_rogue.net.mixin import MpSession
from arch_rogue.net.protocol import ROLE_HOST, ROLE_JOIN
from arch_rogue.story.minigames import (
    STORY_MINI_GAME,
    create_mini_game,
    encode_mini_game_intent,
    encode_mini_game_ready_intent,
)


def _make_game(tmpdir: str) -> Game:
    game = Game(
        screen_size=(640, 360),
        headless=True,
        save_path=Path(tmpdir) / "run.json",
    )
    game.options_path = Path(tmpdir) / "options.json"
    game.restart(ARCHETYPES[0])
    game.story_intro_pending = False
    game.active_cutscene = None
    game.active_mini_game = None
    return game


def _bind(game: Game, role: str) -> MpSession:
    player_id = "p1" if role == ROLE_HOST else "p2"
    session = MpSession(
        role=role,
        started=True,
        player_id=player_id,
        partner_player_id="p2" if role == ROLE_HOST else "p1",
    )
    game.mp_session = session
    game.mp_active = True
    game.mp_role = role
    game.local_player_id = player_id
    game.player.player_id = player_id
    game.players = [game.player]
    return session


class MiniGameSnapshotTests(unittest.TestCase):
    def test_fast_snapshot_is_absolute_and_pauses_the_host(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_game(tmpdir)
            _bind(game, ROLE_HOST)
            active = create_mini_game(
                STORY_MINI_GAME,
                instance_id=7,
                seed=91,
            )
            game.active_mini_game = active

            state = sync.build_snapshot_state(game, include_slow=False)

            self.assertEqual(state["mini_game"], active.to_dict())
            self.assertEqual(state["paused"], "minigame")
            active.revision += 1
            self.assertNotEqual(state["mini_game"], active.to_dict())

    def test_joiner_reconciles_same_instance_in_place_and_clears(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_game(tmpdir)
            _bind(game, ROLE_JOIN)
            current = create_mini_game(
                STORY_MINI_GAME,
                instance_id=8,
                seed=13,
            )
            game.active_mini_game = current
            incoming = create_mini_game(
                STORY_MINI_GAME,
                instance_id=8,
                seed=13,
            )
            incoming.phase = "play"
            incoming.revision = 4
            incoming.score = 2

            sync.apply_snapshot_state(
                game,
                {
                    "players": [],
                    "enemies": [],
                    "mini_game": incoming.to_dict(),
                },
            )

            self.assertIs(game.active_mini_game, current)
            self.assertEqual(current.revision, 4)
            self.assertEqual(current.score, 2)
            sync.apply_snapshot_state(
                game,
                {"players": [], "enemies": [], "mini_game": None},
            )
            self.assertIsNone(game.active_mini_game)

    def test_malformed_snapshot_clears_guest_mirror(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_game(tmpdir)
            _bind(game, ROLE_JOIN)
            game.active_mini_game = create_mini_game(
                STORY_MINI_GAME,
                instance_id=8,
                seed=13,
            )
            hostile = game.active_mini_game.to_dict()
            hostile["board"] = ["arbitrary.asset.key"]

            sync.apply_snapshot_state(
                game,
                {
                    "players": [],
                    "enemies": [],
                    "mini_game": hostile,
                },
            )

            self.assertIsNone(game.active_mini_game)

    def test_slow_snapshot_round_trips_garden_soul_outcomes_and_choice(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_game(tmpdir)
            _bind(game, ROLE_HOST)
            game.dungeon.special_rooms = [
                SpecialRoom(
                    room_index=1,
                    kind="garden",
                    state={"garden_mini_game_outcome": "won"},
                ),
                SpecialRoom(
                    room_index=2,
                    kind="lossless_soul",
                    state={
                        "soul_mini_game_outcome": "lost",
                        "soul_choice": "release",
                    },
                ),
            ]

            snapshot = sync.build_snapshot_state(game, include_slow=True)
            records = snapshot["slow"]["room_games"]

            self.assertEqual(records, [[1, "g", "w"], [2, "s", "l", "r"]])
            garden = SpecialRoom(room_index=1, kind="garden")
            soul = SpecialRoom(room_index=2, kind="lossless_soul")
            game.dungeon.special_rooms = [
                # Same room index but wrong kind must not intercept Garden.
                SpecialRoom(room_index=1, kind="lossless_soul"),
                garden,
                soul,
            ]
            sync.apply_snapshot_state(
                game,
                {
                    "players": [],
                    "enemies": [],
                    "slow": {"room_games": records},
                },
            )
            self.assertEqual(
                garden.state["garden_mini_game_outcome"],
                "won",
            )
            self.assertEqual(soul.state["soul_mini_game_outcome"], "lost")
            self.assertEqual(soul.state["soul_choice"], "release")
            self.assertEqual(game.dungeon.special_rooms[0].state, {})

    def test_slow_room_game_payload_is_bounded_and_rejects_hostile_values(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_game(tmpdir)
            _bind(game, ROLE_HOST)
            game.dungeon.special_rooms = [
                SpecialRoom(
                    room_index=index,
                    kind="garden",
                    state={"garden_mini_game_outcome": "won"},
                )
                for index in range(20)
            ]
            snapshot = sync.build_snapshot_state(game, include_slow=True)
            self.assertEqual(len(snapshot["slow"]["room_games"]), 8)

            garden = SpecialRoom(room_index=1, kind="garden")
            soul = SpecialRoom(room_index=2, kind="lossless_soul")
            game.dungeon.special_rooms = [garden, soul]
            sync.apply_snapshot_state(
                game,
                {
                    "players": [],
                    "enemies": [],
                    "slow": {
                        "room_games": [
                            ["1", "g", "w"],
                            [1, "s", "w", "p"],
                            [1, "g", ["w"]],
                            [1, "g", "w", "extra"],
                            [2, {}, "w", "p"],
                            [2, "s", "unknown", "unknown"],
                            [999, "g", "w"],
                            {"room": 1},
                            [1, "g", "w"],
                        ]
                    },
                },
            )
            # The ninth otherwise-valid record is beyond the hard cap.
            self.assertEqual(garden.state, {})
            self.assertEqual(soul.state, {})


class MiniGameIntentTests(unittest.TestCase):
    def test_fallen_joiner_can_send_ready_before_the_timer_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_game(tmpdir)
            _bind(game, ROLE_JOIN)
            sent: list[dict] = []
            game.mp_client = types.SimpleNamespace(
                send_message=lambda message, **_kwargs: sent.append(message) or True
            )
            active = create_mini_game(
                STORY_MINI_GAME,
                instance_id=10,
                seed=16,
                required_player_ids=["p1", "p2"],
            )
            game.active_mini_game = active
            game.player.hp = 0

            self.assertTrue(game.mp_queue_mini_game_ready())

            self.assertEqual(len(sent), 1)
            self.assertEqual(sent[0]["action"], "minigame")
            self.assertEqual(sent[0]["target"], "10:ready")
            self.assertEqual(sent[0]["pause"], "minigame")
            game.mp_client = None

    def test_host_waits_for_both_ready_confirmations(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_game(tmpdir)
            session = _bind(game, ROLE_HOST)
            partner = sync.build_player_from_full(
                game,
                {
                    "player_id": "p2",
                    "x": game.player.x,
                    "y": game.player.y,
                },
            )
            game.players.append(partner)
            self.assertTrue(game.start_mini_game(STORY_MINI_GAME))
            active = game.active_mini_game
            self.assertIsNotNone(active)
            assert active is not None
            self.assertEqual(active.required_player_ids, ["p1", "p2"])

            game._mp_on_intent(
                IntentMessage(
                    input_seq=1,
                    player_id="p2",
                    move_x=0.0,
                    move_y=0.0,
                    action="minigame",
                    target=encode_mini_game_ready_intent(active),
                    pause="minigame",
                ),
                time.monotonic(),
            )
            game.mp_apply_remote_intents(1 / 60, paused=True)

            self.assertEqual(active.phase, "ready")
            self.assertEqual(active.ready_player_ids, ["p2"])
            self.assertTrue(game.confirm_active_mini_game_ready())
            self.assertEqual(active.phase, "preview")
            self.assertEqual(set(active.ready_player_ids), {"p1", "p2"})

            # A delayed duplicate cannot become a board press after preview
            # begins, and an identity not stamped as the room partner is ignored.
            revision = active.revision
            session.intent_last_seq = 1
            for input_seq, player_id, target in (
                (2, "p2", f"{active.instance_id}:ready"),
                (3, "spoofed", f"{active.instance_id}:ready"),
                (4, "p2", f"{active.instance_id + 1}:ready"),
            ):
                game._mp_on_intent(
                    IntentMessage(
                        input_seq=input_seq,
                        player_id=player_id,
                        move_x=0.0,
                        move_y=0.0,
                        action="minigame",
                        target=target,
                        pause="minigame",
                    ),
                    time.monotonic(),
                )
            game.mp_apply_remote_intents(1 / 60, paused=True)
            self.assertEqual(active.phase, "preview")
            self.assertEqual(active.revision, revision)

    def test_fallen_joiner_can_send_immediate_revision_guarded_press(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_game(tmpdir)
            _bind(game, ROLE_JOIN)
            sent: list[dict] = []
            game.mp_client = types.SimpleNamespace(
                send_message=lambda message, **_kwargs: sent.append(message) or True
            )
            active = create_mini_game(
                STORY_MINI_GAME,
                instance_id=11,
                seed=17,
            )
            active.phase = "play"
            active.revision = 3
            game.active_mini_game = active
            game.player.hp = 0

            self.assertTrue(game.mp_queue_mini_game_cell(2))

            self.assertEqual(len(sent), 1)
            self.assertEqual(sent[0]["action"], "minigame")
            self.assertEqual(sent[0]["target"], "11:3:2")
            self.assertEqual(sent[0]["pause"], "minigame")
            game.mp_client = None

    def test_host_processes_press_while_paused_before_actor_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_game(tmpdir)
            session = _bind(game, ROLE_HOST)
            active = create_mini_game(
                STORY_MINI_GAME,
                instance_id=12,
                seed=23,
            )
            active.phase = "play"
            active.revision = 5
            game.active_mini_game = active
            game.submit_mini_game_cell = Mock(return_value=True)
            session.intent_actions.append(("melee", None, 1.0, 0.0))
            session.intent_move = (1.0, 0.0)
            message = IntentMessage(
                input_seq=1,
                player_id="p2",
                move_x=0.0,
                move_y=0.0,
                action="minigame",
                target=encode_mini_game_intent(active, 1),
                pause="minigame",
            )

            game._mp_on_intent(message, time.monotonic())
            game.mp_apply_remote_intents(1 / 60, paused=True)

            game.submit_mini_game_cell.assert_called_once_with(
                1,
                player_id="p2",
                expected_revision=5,
            )
            self.assertEqual(session.intent_move, (0.0, 0.0))
            self.assertEqual(list(session.intent_actions), [])

    def test_fallen_partner_press_changes_authoritative_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_game(tmpdir)
            _bind(game, ROLE_HOST)
            partner = sync.build_player_from_full(
                game,
                {
                    "player_id": "p2",
                    "x": game.player.x,
                    "y": game.player.y,
                },
            )
            partner.hp = 0
            game.players.append(partner)
            active = create_mini_game(
                STORY_MINI_GAME,
                instance_id=14,
                seed=29,
            )
            active.phase = "play"
            active.revision = 6
            game.active_mini_game = active
            expected_cell = active.sequence[0]
            game._mp_on_intent(
                IntentMessage(
                    input_seq=1,
                    player_id="p2",
                    move_x=0.0,
                    move_y=0.0,
                    action="minigame",
                    target=encode_mini_game_intent(active, expected_cell),
                    pause="minigame",
                ),
                time.monotonic(),
            )

            game.mp_apply_remote_intents(1 / 60, paused=True)

            self.assertEqual(active.step, 1)
            self.assertEqual(active.contributions, {"p2": 1})

    def test_ordered_guest_burst_rebases_until_host_state_intervenes(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_game(tmpdir)
            _bind(game, ROLE_HOST)
            partner = sync.build_player_from_full(
                game,
                {
                    "player_id": "p2",
                    "x": game.player.x,
                    "y": game.player.y,
                },
            )
            game.players.append(partner)
            active = create_mini_game(
                STORY_MINI_GAME,
                instance_id=18,
                seed=37,
                depth=9,
            )
            active.phase = "play"
            active.revision = 4
            game.active_mini_game = active
            wire_revision = active.revision

            def send(input_seq: int, cell: int) -> None:
                game._mp_on_intent(
                    IntentMessage(
                        input_seq=input_seq,
                        player_id="p2",
                        move_x=0.0,
                        move_y=0.0,
                        action="minigame",
                        target=(
                            f"{active.instance_id}:{wire_revision}:{cell}"
                        ),
                        pause="minigame",
                    ),
                    time.monotonic(),
                )

            # Both presses were made against one 15 Hz guest snapshot. The
            # host preserves their validated order instead of dropping the
            # second solely because the first advanced the revision.
            send(1, active.sequence[0])
            send(2, active.sequence[1])
            game.mp_apply_remote_intents(1 / 60, paused=True)
            self.assertEqual(active.step, 2)

            # The chain also spans transport frames while no host/timer state
            # has intervened.
            send(3, active.sequence[2])
            game.mp_apply_remote_intents(1 / 60, paused=True)
            self.assertEqual(active.step, 3)

            # Any independent authoritative mutation breaks the equality.
            active.revision += 1
            send(4, active.sequence[3])
            game.mp_apply_remote_intents(1 / 60, paused=True)
            self.assertEqual(active.step, 3)

    def test_wrong_instance_and_stale_combat_do_not_leak(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = _make_game(tmpdir)
            session = _bind(game, ROLE_HOST)
            active = create_mini_game(
                STORY_MINI_GAME,
                instance_id=20,
                seed=31,
            )
            active.phase = "play"
            active.revision = 2
            game.active_mini_game = active
            game.submit_mini_game_cell = Mock(return_value=False)
            game._mp_on_intent(
                IntentMessage(
                    input_seq=1,
                    player_id="p2",
                    move_x=0.0,
                    move_y=0.0,
                    action="minigame",
                    target="19:2:1",
                    pause="minigame",
                ),
                time.monotonic(),
            )
            game._mp_on_intent(
                IntentMessage(
                    input_seq=2,
                    player_id="p2",
                    move_x=1.0,
                    move_y=0.0,
                    action="melee",
                    target=None,
                    pause="minigame",
                ),
                time.monotonic(),
            )

            game.mp_apply_remote_intents(1 / 60, paused=True)

            game.submit_mini_game_cell.assert_not_called()
            self.assertEqual(session.intent_move, (0.0, 0.0))
            self.assertEqual(list(session.intent_actions), [])


if __name__ == "__main__":
    unittest.main()
