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

"""Deterministic mini-game engines and their story/runtime continuations."""

from __future__ import annotations

import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game
from arch_rogue.models import IdleNpc, SpecialRoom
from arch_rogue.story import (
    GARDEN_MINI_GAME,
    MINI_GAME_TIME_LIMITS,
    SOUL_MINI_GAME,
    STORY_MINI_GAME,
    MiniGameState,
    apply_mini_game_input,
    confirm_mini_game_ready,
    create_mini_game,
    update_mini_game,
)


def _advance_to_play(state) -> None:
    if state.phase == "ready":
        for player_id in state.required_player_ids:
            confirm_mini_game_ready(state, player_id)
    for _ in range(32):
        if state.phase == "play":
            return
        update_mini_game(state, 0.25)
    raise AssertionError("mini-game preview did not finish")


class MiniGameEngineTests(unittest.TestCase):
    def test_ready_phase_is_untimed_and_requires_every_participant(self) -> None:
        state = create_mini_game(
            STORY_MINI_GAME,
            instance_id=41,
            seed=902,
            required_player_ids=["p1", "p2"],
        )
        self.assertEqual(state.phase, "ready")
        self.assertEqual(state.required_player_ids, ["p1", "p2"])
        before = state.to_dict()
        self.assertFalse(update_mini_game(state, 4.0))
        self.assertEqual(state.to_dict(), before)

        self.assertFalse(confirm_mini_game_ready(state, "stranger"))
        self.assertTrue(confirm_mini_game_ready(state, "p1"))
        revision = state.revision
        self.assertEqual(state.phase, "ready")
        self.assertEqual(state.ready_player_ids, ["p1"])
        self.assertFalse(confirm_mini_game_ready(state, "p1"))
        self.assertEqual(state.revision, revision)
        self.assertFalse(update_mini_game(state, 1.0))
        self.assertEqual(state.phase, "ready")

        self.assertTrue(confirm_mini_game_ready(state, "p2"))
        self.assertEqual(state.phase, "preview")
        self.assertEqual(state.ready_player_ids, ["p1", "p2"])
        self.assertEqual(state.revision, revision + 1)

    def test_story_sequence_is_deterministic_and_revision_safe(self) -> None:
        first = create_mini_game(
            STORY_MINI_GAME, instance_id=1, seed=90210, depth=9
        )
        second = create_mini_game(
            STORY_MINI_GAME, instance_id=2, seed=90210, depth=9
        )
        self.assertEqual(first.board, second.board)
        self.assertEqual(first.sequence, second.sequence)
        _advance_to_play(first)
        self.assertEqual(first.time_left, 7.5)
        self.assertEqual(
            first.time_left,
            MINI_GAME_TIME_LIMITS[STORY_MINI_GAME],
        )

        revision = first.revision
        wrong = (first.sequence[0] + 1) % len(first.board)
        self.assertTrue(
            apply_mini_game_input(
                first,
                cell=wrong,
                player_id="p1",
                expected_revision=revision,
            )
        )
        mistakes = first.mistakes
        # A delayed duplicate is harmless, not a second mistake.
        self.assertFalse(
            apply_mini_game_input(
                first,
                cell=wrong,
                player_id="p1",
                expected_revision=revision,
            )
        )
        self.assertEqual(first.mistakes, mistakes)

        while first.phase == "play":
            contributor = "p1" if first.step % 2 == 0 else "p2"
            self.assertTrue(
                apply_mini_game_input(
                    first,
                    cell=first.sequence[first.step],
                    player_id=contributor,
                    expected_revision=first.revision,
                )
            )
        self.assertEqual(first.outcome, "won")
        self.assertGreater(first.contributions["p1"], 0)
        self.assertGreater(first.contributions["p2"], 0)

    def test_garden_and_soul_can_be_completed_by_two_players(self) -> None:
        garden = create_mini_game(
            GARDEN_MINI_GAME, instance_id=3, seed=404, depth=6
        )
        _advance_to_play(garden)
        self.assertEqual(garden.time_left, 9.0)
        while garden.phase == "play":
            player_id = "p1" if garden.score % 2 == 0 else "p2"
            self.assertTrue(
                apply_mini_game_input(
                    garden,
                    cell=garden.active_cell,
                    player_id=player_id,
                    expected_revision=garden.revision,
                )
            )
        self.assertEqual(garden.outcome, "won")
        self.assertEqual(sum(garden.contributions.values()), garden.goal)

        soul = create_mini_game(
            SOUL_MINI_GAME, instance_id=4, seed=505, depth=8
        )
        _advance_to_play(soul)
        self.assertEqual(soul.time_left, 12.0)
        pairs: dict[str, list[int]] = {}
        for index, sigil in enumerate(soul.board):
            pairs.setdefault(sigil, []).append(index)
        for pair_index, (first, second) in enumerate(pairs.values()):
            self.assertTrue(
                apply_mini_game_input(
                    soul,
                    cell=first,
                    player_id="p1",
                    expected_revision=soul.revision,
                )
            )
            self.assertTrue(
                apply_mini_game_input(
                    soul,
                    cell=second,
                    player_id="p2" if pair_index % 2 else "p1",
                    expected_revision=soul.revision,
                )
            )
        self.assertEqual(soul.outcome, "won")
        self.assertEqual(len(soul.matched), len(soul.board))

    def test_snapshot_round_trip_is_bounded_and_rejects_locking_phases(
        self,
    ) -> None:
        state = create_mini_game(
            STORY_MINI_GAME, instance_id=8, seed=606, depth=8
        )
        for phase, outcome in (
            ("ready", ""),
            ("preview", ""),
            ("play", ""),
            ("result", "won"),
        ):
            with self.subTest(phase=phase):
                state.phase = phase
                state.outcome = outcome
                restored = MiniGameState.from_dict(state.to_dict())
                self.assertIsNotNone(restored)
                assert restored is not None
                self.assertEqual(restored.context, state.context)
                self.assertEqual(restored.phase, phase)
                self.assertEqual(restored.outcome, outcome)

        legacy = state.to_dict()
        legacy.pop("required")
        legacy.pop("ready")
        legacy["phase"] = "preview"
        legacy["outcome"] = ""
        restored = MiniGameState.from_dict(legacy)
        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertEqual(restored.phase, "preview")
        self.assertEqual(restored.required_player_ids, ["p1"])
        self.assertEqual(restored.ready_player_ids, ["p1"])

        malformed = state.to_dict()
        malformed["phase"] = "result"
        malformed["outcome"] = ""
        self.assertIsNone(MiniGameState.from_dict(malformed))
        malformed["phase"] = "play"
        malformed["outcome"] = "lost"
        self.assertIsNone(MiniGameState.from_dict(malformed))

        bounded = state.to_dict()
        bounded["phase"] = "play"
        bounded["outcome"] = ""
        bounded["left"] = float("inf")
        bounded["lock"] = float("nan")
        restored = MiniGameState.from_dict(bounded)
        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertEqual(restored.time_left, 0.0)
        self.assertEqual(restored.lock_time, 0.0)


class MiniGameRuntimeTests(unittest.TestCase):
    def _game(self, seed: int = 2) -> Game:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        game = Game(
            screen_size=(820, 540),
            headless=True,
            save_path=Path(tmpdir.name) / "run.json",
        )
        game.options_path = Path(tmpdir.name) / "options.json"
        game.rng.seed(seed)
        game.restart(ARCHETYPES[0])
        return game

    def _garden_fixture(self) -> tuple[Game, SpecialRoom, list[IdleNpc]]:
        game = self._game()
        garden = game.dungeon.special_room_for_kind("garden")
        self.assertIsNotNone(garden, "fixture seed must contain a Garden")
        assert garden is not None
        game.story_intro_pending = False
        game.close_active_cutscene()
        game.active_mini_game = None
        frogs = [
            npc
            for npc in game.idle_npcs
            if npc.kind == "garden_frog"
            and game.garden_frog_special_room(npc) is garden
        ]
        self.assertEqual(len(frogs), 2)
        return game, garden, frogs

    def test_major_story_loss_continues_before_relic_commit(self) -> None:
        game = self._game()
        game.current_depth = 5
        game.story_guests[0].depth = 5
        game.story_intro_pending = True
        mana_before = game.player.mana = 7
        hp_before = game.player.hp = 9
        stamina_before = game.player.stamina = 11
        melee_before = game.player.melee_bonus
        self.assertTrue(game.choose_story_relic_path(0))
        state = game.active_mini_game
        self.assertIsNotNone(state)
        assert state is not None
        self.assertEqual(state.kind, STORY_MINI_GAME)
        self.assertTrue(game.story_intro_pending)
        self.assertIsNone(game.current_story_relic())

        state.phase = "result"
        state.outcome = "lost"
        state.result_time = 0.0
        self.assertTrue(game.update_active_mini_game(0.01))
        self.assertIsNone(game.active_mini_game)
        self.assertFalse(game.story_intro_pending)
        self.assertIsNotNone(game.current_story_relic())
        self.assertEqual(game.player.mana, mana_before)
        self.assertEqual(game.player.hp, hp_before)
        self.assertEqual(game.player.stamina, stamina_before)
        self.assertEqual(game.player.melee_bonus, melee_before)
        self.assertIn("5:minigame:story:lost", game.story_state.flags)
        self.assertFalse(game.finalize_active_mini_game())

    def test_solo_start_waits_for_interact_and_ready_state_round_trips(
        self,
    ) -> None:
        game = self._game()
        self.assertTrue(game.start_mini_game(STORY_MINI_GAME, context="choice:0"))
        state = game.active_mini_game
        self.assertIsNotNone(state)
        assert state is not None
        self.assertEqual(state.phase, "ready")
        self.assertEqual(state.required_player_ids, ["p1"])

        payload = copy.deepcopy(game.serialize_run_state())
        restored = self._game(seed=3)
        restored.restore_run_state(payload)
        active = restored.active_mini_game
        self.assertIsNotNone(active)
        assert active is not None
        self.assertEqual(active.phase, "ready")
        self.assertEqual(active.ready_player_ids, [])

        self.assertTrue(restored.confirm_active_mini_game_ready())
        self.assertEqual(active.phase, "preview")
        self.assertFalse(restored.confirm_active_mini_game_ready())

    def test_non_major_story_depth_commits_without_game(self) -> None:
        game = self._game()
        self.assertTrue(game.choose_story_relic_path(0))
        self.assertIsNone(game.active_mini_game)
        self.assertFalse(game.story_intro_pending)
        self.assertIsNotNone(game.current_story_relic())

    def test_either_garden_frog_starts_the_room_game(self) -> None:
        for frog_index in range(2):
            with self.subTest(frog_index=frog_index):
                game, garden, frogs = self._garden_fixture()
                frog = frogs[frog_index]
                game.player.x, game.player.y = frog.x, frog.y

                self.assertIs(game.nearby_garden_frog(), frog)
                hint = game.current_interaction_hint()
                self.assertIsNotNone(hint)
                assert hint is not None
                self.assertEqual(hint[0], "E")
                self.assertEqual(hint[1], f"Talk to {frog.name}")
                self.assertIn("Garden Dancer", hint[2])

                game.interact()
                state = game.active_mini_game
                self.assertIsNotNone(state)
                assert state is not None
                self.assertEqual(state.kind, GARDEN_MINI_GAME)
                self.assertEqual(state.context, f"room:{garden.room_index}")
                self.assertEqual(state.origin_player_id, "p1")

    def test_garden_frog_reward_is_once_then_yields_to_wanderer(self) -> None:
        game, garden, frogs = self._garden_fixture()
        first_frog, other_frog = frogs
        game.player.x, game.player.y = first_frog.x, first_frog.y
        game.interact()
        state = game.active_mini_game
        self.assertIsNotNone(state)
        assert state is not None
        max_hp_before = game.player.max_hp
        max_mana_before = game.player.max_mana
        game.player.hp = 40
        game.player.mana = 3
        state.phase = "result"
        state.outcome = "won"
        state.result_time = 0.0
        self.assertTrue(game.update_active_mini_game(0.01))
        rewarded = (
            game.player.hp,
            game.player.max_hp,
            game.player.mana,
            game.player.max_mana,
        )
        self.assertEqual(garden.state["garden_mini_game_outcome"], "won")
        self.assertEqual(
            rewarded,
            (45, max_hp_before + 5, 8, max_mana_before + 5),
        )

        game.player.x, game.player.y = other_frog.x, other_frog.y
        self.assertIsNone(game.nearby_garden_frog())
        self.assertFalse(game.talk_to_garden_frog(other_frog))
        self.assertEqual(
            (
                game.player.hp,
                game.player.max_hp,
                game.player.mana,
                game.player.max_mana,
            ),
            rewarded,
        )
        self.assertIsNone(game.active_mini_game)

        wanderer = next(
            (npc for npc in game.idle_npcs if npc.kind == "garden"),
            None,
        )
        if wanderer is None:
            wanderer = IdleNpc(
                x=other_frog.x,
                y=other_frog.y,
                kind="garden",
                name="Gardener Thistle",
                role="Wanderer",
                color=(150, 196, 132),
            )
            game.idle_npcs.append(wanderer)
        else:
            wanderer.x, wanderer.y = other_frog.x, other_frog.y
        hint = game.current_interaction_hint()
        self.assertIsNotNone(hint)
        assert hint is not None
        self.assertEqual(hint[1], f"Greet {wanderer.name}")

    def test_remote_actor_can_start_garden_game_through_either_frog(self) -> None:
        game, garden, frogs = self._garden_fixture()
        frog = frogs[1]
        remote = copy.deepcopy(game.player)
        remote.player_id = "p2"
        remote.x, remote.y = frog.x, frog.y
        game.player.x, game.player.y = frog.x + 3.0, frog.y
        game.mp_active = True
        game.mp_role = "host"
        game.players = [game.player, remote]
        game.local_player_id = "p1"

        with game.acting_as_player(remote):
            game.interact()

        state = game.active_mini_game
        self.assertIsNotNone(state)
        assert state is not None
        self.assertEqual(state.kind, GARDEN_MINI_GAME)
        self.assertEqual(state.context, f"room:{garden.room_index}")
        self.assertEqual(state.origin_player_id, "p2")
        self.assertEqual(set(state.required_player_ids), {"p1", "p2"})

    def test_garden_frog_prompt_wins_over_ranger_petting(self) -> None:
        game, _garden, frogs = self._garden_fixture()
        frog = frogs[0]
        game.player.x, game.player.y = frog.x, frog.y
        spirit_beast = Mock(name="Spirit Beast")

        with patch.object(
            game,
            "nearby_pettable_spirit_beast",
            return_value=spirit_beast,
        ):
            hint = game.current_interaction_hint()

        self.assertIsNotNone(hint)
        assert hint is not None
        self.assertEqual(hint[1], f"Talk to {frog.name}")

    def test_garden_central_light_no_longer_starts_the_game(self) -> None:
        game, garden, _frogs = self._garden_fixture()
        room = game.dungeon.rooms[garden.room_index]
        anchor = garden.anchor("npc", room.center)
        assert anchor is not None
        game.idle_npcs = [
            npc for npc in game.idle_npcs if npc.kind != "garden_frog"
        ]
        game.player.x, game.player.y = anchor[0] + 0.5, anchor[1] + 0.5

        game.interact()

        self.assertIsNone(game.active_mini_game)

    def test_remote_actor_starts_soul_game_and_party_reward_is_once(self) -> None:
        game = self._game()
        soul_room = game.dungeon.special_room_for_kind("lossless_soul")
        self.assertIsNotNone(soul_room, "fixture seed must contain a Soul hall")
        assert soul_room is not None
        keeper = next(npc for npc in game.idle_npcs if npc.kind == "lossless_soul")
        game.story_intro_pending = False
        game.close_active_cutscene()
        game.active_mini_game = None

        remote = copy.deepcopy(game.player)
        remote.player_id = "p2"
        remote.x, remote.y = keeper.x + 0.8, keeper.y
        game.mp_active = True
        game.mp_role = "host"
        game.players = [game.player, remote]
        game.local_player_id = "p1"
        max_mana_before = {
            game.player.player_id: game.player.max_mana,
            remote.player_id: remote.max_mana,
        }
        spell_before = {
            game.player.player_id: game.player.spell_bonus,
            remote.player_id: remote.spell_bonus,
        }
        game.player.mana = remote.mana = 0
        with game.acting_as_player(remote):
            game.interact()
        state = game.active_mini_game
        self.assertIsNotNone(state)
        assert state is not None
        self.assertEqual(state.kind, SOUL_MINI_GAME)
        self.assertEqual(state.origin_player_id, "p2")
        self.assertEqual(game.active_cutscene.asset_id, "lossless_soul_reflection")
        self.assertFalse(game.choose_active_cutscene_option(0))

        state.phase = "result"
        state.outcome = "won"
        state.result_time = 0.0
        self.assertTrue(game.update_active_mini_game(0.01))
        self.assertEqual(soul_room.state["soul_mini_game_outcome"], "won")
        for player in (game.player, remote):
            self.assertEqual(player.mana, 5)
            self.assertEqual(
                player.max_mana,
                max_mana_before[player.player_id] + 5,
            )
            self.assertEqual(
                player.spell_bonus,
                spell_before[player.player_id] + 1,
            )
        rewards = (
            game.player.mana,
            game.player.max_mana,
            game.player.spell_bonus,
            remote.mana,
            remote.max_mana,
            remote.spell_bonus,
        )
        self.assertFalse(game.finalize_active_mini_game())
        self.assertEqual(
            (
                game.player.mana,
                game.player.max_mana,
                game.player.spell_bonus,
                remote.mana,
                remote.max_mana,
                remote.spell_bonus,
            ),
            rewards,
        )
        # The host can resolve the remote-opened audience after acting_as_player
        # has restored self.player to p1.
        self.assertTrue(game.choose_active_cutscene_option(1))
        self.assertEqual(soul_room.state["soul_choice"], "release")

    def test_joiner_local_activation_uses_dedicated_net_helper(self) -> None:
        game = self._game()
        self.assertTrue(game.start_mini_game(STORY_MINI_GAME, context="choice:0"))
        assert game.active_mini_game is not None
        game.active_mini_game.phase = "play"
        sender = Mock(return_value=True)
        game.mp_active = True
        game.mp_role = "join"
        game.mp_queue_mini_game_cell = sender
        self.assertTrue(game.activate_mini_game_cell(2))
        sender.assert_called_once_with(2)

    def test_active_story_result_save_round_trip_continues_and_rewards_once(
        self,
    ) -> None:
        game = self._game()
        game.current_depth = 5
        game.story_guests[0].depth = 5
        game.story_intro_pending = True
        max_hp_before = game.player.max_hp
        melee_before = game.player.melee_bonus
        game.player.hp = 1
        game.player.mana = 0
        game.player.stamina = 0
        self.assertTrue(game.choose_story_relic_path(0))
        state = game.active_mini_game
        self.assertIsNotNone(state)
        assert state is not None
        state.phase = "result"
        state.outcome = "won"
        state.result_time = 0.0

        payload = copy.deepcopy(game.serialize_run_state())
        restored = self._game(seed=3)
        restored.restore_run_state(payload)
        active = restored.active_mini_game
        self.assertIsNotNone(active)
        assert active is not None
        self.assertEqual(active.context, "choice:0")
        self.assertEqual(active.outcome, "won")

        self.assertTrue(restored.update_active_mini_game(0.01))
        self.assertIsNone(restored.active_mini_game)
        self.assertFalse(restored.story_intro_pending)
        self.assertIsNotNone(restored.current_story_relic())
        rewarded = (
            restored.player.hp,
            restored.player.mana,
            restored.player.stamina,
            restored.player.melee_bonus,
        )
        self.assertEqual(rewarded, (max_hp_before, 0, 0, melee_before + 1))
        self.assertFalse(restored.finalize_active_mini_game())
        self.assertEqual(
            (
                restored.player.hp,
                restored.player.mana,
                restored.player.stamina,
                restored.player.melee_bonus,
            ),
            rewarded,
        )


if __name__ == "__main__":
    unittest.main()
