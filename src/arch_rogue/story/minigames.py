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

"""Deterministic, Pygame-free state machines for the 4.9.x mini-games.

The host advances these models and applies inputs.  Multiplayer guests receive
absolute snapshots and submit instance-scoped ready intents or
``instance/revision/cell`` play intents, so simultaneous confirmations and
delayed taps remain harmless.  No game judges sub-frame rhythm; the shortest
garden target remains visible long enough for ordinary Internet latency.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

from ..constants import SHARED_SIGIL_NAMES

STORY_MINI_GAME = "story"
GARDEN_MINI_GAME = "garden"
SOUL_MINI_GAME = "soul"
MINI_GAME_KINDS = frozenset((STORY_MINI_GAME, GARDEN_MINI_GAME, SOUL_MINI_GAME))

MINI_GAME_TITLES = {
    STORY_MINI_GAME: "Bind the Page",
    GARDEN_MINI_GAME: "Wake the Moonbloom",
    SOUL_MINI_GAME: "Mirror the Unlost",
}

MINI_GAME_INSTRUCTIONS = {
    STORY_MINI_GAME: "Remember the lit runes, then repeat them in order.",
    GARDEN_MINI_GAME: "Touch each waking bloom before its light folds shut.",
    SOUL_MINI_GAME: "Turn two seals at a time and reunite every mirrored pair.",
}

_STORY_SIGILS = ("key", "clock", "sun", "moon", "sword", "shield")
_GARDEN_SIGILS = (
    "sun",
    "moon",
    "star",
    "flame",
    "serpent",
    "ouroboros",
    "phoenix",
    "dragon",
    "cross",
)
_SOUL_SIGILS = ("infinity", "key", "clock", "moon", "phoenix", "ouroboros")
_ALLOWED_SIGILS = frozenset(SHARED_SIGIL_NAMES)

MINI_GAME_TIME_LIMITS = {
    STORY_MINI_GAME: 7.5,
    GARDEN_MINI_GAME: 9.0,
    SOUL_MINI_GAME: 12.0,
}
_RESULT_SECONDS = 1.25
_GARDEN_TARGET_SECONDS = 1.55
_SOUL_MISMATCH_SECONDS = 0.68


@dataclass
class MiniGameState:
    """One complete authoritative mini-game session.

    ``context`` is an opaque, host-owned continuation token (the selected
    story choice index for Bind the Page).  It is replicated only because an
    absolute snapshot is convenient for reconnects; clients never execute it.
    """

    instance_id: int
    kind: str
    seed: int
    context: str = ""
    origin_player_id: str = "p1"
    phase: str = "ready"
    required_player_ids: list[str] = field(default_factory=lambda: ["p1"])
    ready_player_ids: list[str] = field(default_factory=list)
    revision: int = 0
    elapsed: float = 0.0
    time_left: float = 0.0
    goal: int = 0
    score: int = 0
    mistakes: int = 0
    board: list[str] = field(default_factory=list)
    sequence: list[int] = field(default_factory=list)
    step: int = 0
    active_cell: int = -1
    target_time: float = 0.0
    revealed: list[int] = field(default_factory=list)
    matched: list[int] = field(default_factory=list)
    lock_time: float = 0.0
    outcome: str = ""
    result_time: float = 0.0
    last_cell: int = -1
    last_correct: bool = False
    last_player_id: str = ""
    feedback_time: float = 0.0
    contributions: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a compact absolute snapshot safe for the wire."""

        return {
            "id": int(self.instance_id),
            "kind": self.kind,
            "seed": int(self.seed),
            "context": self.context[:32],
            "origin": self.origin_player_id[:32],
            "phase": self.phase,
            "required": [
                player_id[:32] for player_id in self.required_player_ids[:4]
            ],
            "ready": [player_id[:32] for player_id in self.ready_player_ids[:4]],
            "rev": int(self.revision),
            "elapsed": round(max(0.0, self.elapsed), 3),
            "left": round(max(0.0, self.time_left), 3),
            "goal": int(self.goal),
            "score": int(self.score),
            "mistakes": int(self.mistakes),
            "board": list(self.board),
            "sequence": [int(cell) for cell in self.sequence],
            "step": int(self.step),
            "active": int(self.active_cell),
            "target": round(max(0.0, self.target_time), 3),
            "revealed": [int(cell) for cell in self.revealed],
            "matched": [int(cell) for cell in self.matched],
            "lock": round(max(0.0, self.lock_time), 3),
            "outcome": self.outcome,
            "result": round(max(0.0, self.result_time), 3),
            "last": int(self.last_cell),
            "correct": bool(self.last_correct),
            "last_player": self.last_player_id[:32],
            "feedback": round(max(0.0, self.feedback_time), 3),
            "contrib": {
                str(player_id)[:32]: max(0, int(value))
                for player_id, value in self.contributions.items()
                if value
            },
        }

    @classmethod
    def from_dict(cls, data: Any) -> "MiniGameState | None":
        """Defensively ingest one host snapshot.

        Asset names are allowlisted rather than trusted from the network.  A
        malformed snapshot clears the guest mirror instead of reaching the
        renderer with unbounded lists or arbitrary UI keys.
        """

        if not isinstance(data, dict):
            return None
        kind = str(data.get("kind", ""))
        if kind not in MINI_GAME_KINDS:
            return None
        try:
            instance_id = int(data.get("id", 0))
            seed = int(data.get("seed", 0))
            revision = int(data.get("rev", 0))
        except (TypeError, ValueError):
            return None
        if instance_id <= 0 or revision < 0:
            return None
        board_data = data.get("board", [])
        if not isinstance(board_data, list) or not 1 <= len(board_data) <= 12:
            return None
        board = [str(name) for name in board_data]
        if any(name not in _ALLOWED_SIGILS for name in board):
            return None

        def cells(key: str, cap: int = 12) -> list[int]:
            values = data.get(key, [])
            if not isinstance(values, list):
                return []
            result: list[int] = []
            for value in values[:cap]:
                try:
                    cell = int(value)
                except (TypeError, ValueError):
                    continue
                if 0 <= cell < len(board):
                    result.append(cell)
            return result

        phase = str(data.get("phase", "preview"))
        if phase not in ("ready", "preview", "play", "result"):
            phase = "preview"
        outcome = str(data.get("outcome", ""))
        if outcome not in ("", "won", "lost"):
            outcome = ""
        raw_origin_player_id = data.get("origin", "p1")
        origin_player_id = (
            raw_origin_player_id[:32]
            if isinstance(raw_origin_player_id, str) and raw_origin_player_id
            else "p1"
        )

        def player_ids(key: str) -> list[str]:
            values = data.get(key, [])
            if not isinstance(values, list):
                return []
            result: list[str] = []
            for value in values[:4]:
                if not isinstance(value, str):
                    continue
                player_id = value[:32]
                if player_id and player_id not in result:
                    result.append(player_id)
            return result

        required_player_ids = player_ids("required") or [origin_player_id]
        if origin_player_id not in required_player_ids:
            required_player_ids.insert(0, origin_player_id)
            del required_player_ids[4:]
        ready_player_ids = [
            player_id
            for player_id in player_ids("ready")
            if player_id in required_player_ids
        ]
        if phase != "ready":
            # Older schema-5 saves did not carry readiness fields. Once a
            # session reached preview/play/result, every captured participant
            # is canonically ready regardless of payload version.
            ready_player_ids = list(required_player_ids)
        elif all(
            player_id in ready_player_ids for player_id in required_player_ids
        ):
            # Confirmation transitions atomically. Canonicalize a redundant
            # all-ready shape instead of leaving a modal with no remaining
            # action after defensive ingestion.
            phase = "preview"
        contributions_data = data.get("contrib", {})
        contributions: dict[str, int] = {}
        if isinstance(contributions_data, dict):
            for raw_key, raw_value in list(contributions_data.items())[:4]:
                try:
                    value = max(0, int(raw_value))
                except (TypeError, ValueError):
                    continue
                if value:
                    contributions[str(raw_key)[:32]] = value

        def bounded_float(key: str, maximum: float) -> float:
            try:
                value = float(data.get(key, 0.0))
            except (TypeError, ValueError):
                return 0.0
            if not math.isfinite(value):
                return 0.0
            return max(0.0, min(maximum, value))

        try:
            state = cls(
                instance_id=instance_id,
                kind=kind,
                seed=seed,
                context=str(data.get("context", ""))[:32],
                origin_player_id=origin_player_id,
                phase=phase,
                required_player_ids=required_player_ids,
                ready_player_ids=ready_player_ids,
                revision=revision,
                elapsed=bounded_float("elapsed", 30.0),
                time_left=bounded_float("left", 20.0),
                goal=max(1, min(12, int(data.get("goal", 1)))),
                score=max(0, min(12, int(data.get("score", 0)))),
                mistakes=max(0, min(99, int(data.get("mistakes", 0)))),
                board=board,
                sequence=cells("sequence"),
                step=max(0, min(12, int(data.get("step", 0)))),
                active_cell=int(data.get("active", -1)),
                target_time=bounded_float("target", 3.0),
                revealed=cells("revealed", 2),
                matched=cells("matched"),
                lock_time=bounded_float("lock", 2.0),
                outcome=outcome,
                result_time=bounded_float("result", 2.0),
                last_cell=int(data.get("last", -1)),
                last_correct=bool(data.get("correct", False)),
                last_player_id=str(data.get("last_player", ""))[:32],
                feedback_time=bounded_float("feedback", 1.0),
                contributions=contributions,
            )
        except (TypeError, ValueError):
            return None
        # A result without an outcome can never finalize, while an outcome in
        # An outcome in ready/preview/play disables both input and timeout
        # resolution. Reject inconsistent shapes so a corrupt save or peer
        # snapshot cannot hold the full-screen modal open forever.
        if (state.phase == "result") != (state.outcome in ("won", "lost")):
            return None
        if state.active_cell not in range(len(board)):
            state.active_cell = -1
        if state.last_cell not in range(len(board)):
            state.last_cell = -1
        state.step = min(state.step, len(state.sequence))
        return state


def create_mini_game(
    kind: str,
    *,
    instance_id: int,
    seed: int,
    depth: int = 1,
    context: str = "",
    origin_player_id: str = "p1",
    required_player_ids: tuple[str, ...] | list[str] = (),
) -> MiniGameState:
    """Build one deterministic board at difficulty appropriate to ``depth``."""

    if kind not in MINI_GAME_KINDS:
        raise ValueError(f"unknown mini-game kind {kind!r}")
    origin_player_id = str(origin_player_id or "p1")[:32]
    required: list[str] = []
    for value in required_player_ids[:4]:
        player_id = str(value)[:32]
        if player_id and player_id not in required:
            required.append(player_id)
    if origin_player_id not in required:
        required.insert(0, origin_player_id)
        del required[4:]
    rng = random.Random(int(seed))
    if kind == STORY_MINI_GAME:
        board = list(_STORY_SIGILS)
        rng.shuffle(board)
        length = min(6, 3 + max(0, int(depth) - 1) // 3)
        sequence: list[int] = []
        for _ in range(length):
            cell = rng.randrange(len(board))
            # Back-to-back repeats are valid memory-game grammar, but a run of
            # identical flashes reads like one long pulse on a small screen.
            # Keep the sequence varied without consuming any global game RNG.
            if sequence and cell == sequence[-1]:
                cell = (cell + 1 + rng.randrange(len(board) - 1)) % len(board)
            sequence.append(cell)
        return MiniGameState(
            instance_id=instance_id,
            kind=kind,
            seed=seed,
            context=context,
            origin_player_id=origin_player_id,
            required_player_ids=required,
            goal=length,
            board=board,
            sequence=sequence,
        )
    if kind == GARDEN_MINI_GAME:
        board = list(_GARDEN_SIGILS)
        rng.shuffle(board)
        state = MiniGameState(
            instance_id=instance_id,
            kind=kind,
            seed=seed,
            context=context,
            origin_player_id=origin_player_id,
            required_player_ids=required,
            goal=min(8, 6 + max(0, int(depth) - 1) // 5),
            board=board,
        )
        state.active_cell = _next_garden_cell(state)
        state.target_time = _GARDEN_TARGET_SECONDS
        return state

    pair_count = 3 if int(depth) < 8 else 4
    chosen = rng.sample(_SOUL_SIGILS, k=pair_count)
    board = chosen * 2
    rng.shuffle(board)
    return MiniGameState(
        instance_id=instance_id,
        kind=kind,
        seed=seed,
        context=context,
        origin_player_id=origin_player_id,
        required_player_ids=required,
        goal=pair_count,
        board=board,
    )


def confirm_mini_game_ready(state: MiniGameState, player_id: str) -> bool:
    """Record one participant's start confirmation.

    Confirmations are idempotent and not revision-stamped. Both players can
    therefore confirm against the same snapshot without the first ready press
    invalidating the second.
    """

    if state.phase != "ready" or state.outcome:
        return False
    player_id = str(player_id or "")[:32]
    if (
        not player_id
        or player_id not in state.required_player_ids
        or player_id in state.ready_player_ids
    ):
        return False
    state.ready_player_ids.append(player_id)
    state.revision += 1
    if all(
        required in state.ready_player_ids
        for required in state.required_player_ids
    ):
        state.phase = "preview"
        state.elapsed = 0.0
    return True


def preview_duration(state: MiniGameState) -> float:
    if state.kind == STORY_MINI_GAME:
        return 0.55 * len(state.sequence) + 0.55
    return 0.85


def preview_cell(state: MiniGameState) -> int:
    """The story rune currently shown during memorization, or ``-1``."""

    if state.kind != STORY_MINI_GAME or state.phase != "preview":
        return -1
    index = int(max(0.0, state.elapsed - 0.30) / 0.55)
    pulse = (max(0.0, state.elapsed - 0.30) % 0.55) < 0.38
    if pulse and 0 <= index < len(state.sequence):
        return state.sequence[index]
    return -1


def update_mini_game(
    state: MiniGameState, dt: float, *, authoritative: bool = True
) -> bool:
    """Advance timers; return ``True`` once the result card has finished.

    Guests call this with ``authoritative=False`` for smooth countdown and
    feedback animation only.  They never advance phases, targets, or outcomes.
    """

    dt = max(0.0, min(float(dt), 0.25))
    if state.phase == "ready":
        return False
    state.feedback_time = max(0.0, state.feedback_time - dt)
    if not authoritative:
        if state.phase == "preview":
            state.elapsed += dt
        elif state.phase == "play":
            state.time_left = max(0.0, state.time_left - dt)
            state.target_time = max(0.0, state.target_time - dt)
            state.lock_time = max(0.0, state.lock_time - dt)
        elif state.phase == "result":
            state.result_time = max(0.0, state.result_time - dt)
        return False

    if state.phase == "preview":
        state.elapsed += dt
        if state.elapsed >= preview_duration(state):
            state.phase = "play"
            state.elapsed = 0.0
            state.time_left = MINI_GAME_TIME_LIMITS[state.kind]
            state.revision += 1
        return False

    if state.phase == "play":
        state.elapsed += dt
        state.time_left = max(0.0, state.time_left - dt)
        if state.kind == GARDEN_MINI_GAME:
            state.target_time = max(0.0, state.target_time - dt)
            if state.target_time <= 0.0 and not state.outcome:
                state.mistakes += 1
                state.active_cell = _next_garden_cell(state)
                state.target_time = _garden_target_seconds(state)
                state.last_cell = -1
                state.last_correct = False
                state.feedback_time = 0.28
                state.revision += 1
        elif state.kind == SOUL_MINI_GAME and state.lock_time > 0.0:
            state.lock_time = max(0.0, state.lock_time - dt)
            if state.lock_time <= 0.0:
                state.revealed.clear()
                state.revision += 1
        if state.time_left <= 0.0 and not state.outcome:
            _finish(state, state.score >= state.goal)
        return False

    if state.phase == "result":
        state.result_time = max(0.0, state.result_time - dt)
        return state.result_time <= 0.0
    return False


def apply_mini_game_input(
    state: MiniGameState,
    *,
    cell: int,
    player_id: str,
    expected_revision: int,
) -> bool:
    """Validate and apply one host-side cell selection.

    Returns whether the authoritative state changed.  Stale, duplicate, locked,
    or out-of-range presses are intentionally silent and penalty-free.
    """

    if (
        state.phase != "play"
        or state.outcome
        or expected_revision != state.revision
        or not 0 <= int(cell) < len(state.board)
    ):
        return False
    cell = int(cell)
    player_id = str(player_id or "p2")[:32]
    if state.kind == STORY_MINI_GAME:
        return _apply_story_input(state, cell, player_id)
    if state.kind == GARDEN_MINI_GAME:
        return _apply_garden_input(state, cell, player_id)
    return _apply_soul_input(state, cell, player_id)


def _apply_story_input(
    state: MiniGameState, cell: int, player_id: str
) -> bool:
    expected = state.sequence[state.step] if state.step < len(state.sequence) else -1
    correct = cell == expected
    _record_press(state, cell, player_id, correct)
    if correct:
        state.step += 1
        state.score = state.step
        _credit(state, player_id)
        if state.step >= state.goal:
            _finish(state, True)
    else:
        state.mistakes += 1
        state.time_left = max(0.0, state.time_left - 0.65)
    state.revision += 1
    return True


def _apply_garden_input(
    state: MiniGameState, cell: int, player_id: str
) -> bool:
    correct = cell == state.active_cell
    _record_press(state, cell, player_id, correct)
    if correct:
        state.score += 1
        _credit(state, player_id)
        if state.score >= state.goal:
            _finish(state, True)
        else:
            state.active_cell = _next_garden_cell(state)
            state.target_time = _garden_target_seconds(state)
    else:
        state.mistakes += 1
        state.time_left = max(0.0, state.time_left - 0.45)
    state.revision += 1
    return True


def _apply_soul_input(
    state: MiniGameState, cell: int, player_id: str
) -> bool:
    if state.lock_time > 0.0 or cell in state.matched or cell in state.revealed:
        return False
    if not state.revealed:
        state.revealed.append(cell)
        _record_press(state, cell, player_id, True)
        state.revision += 1
        return True

    first = state.revealed[0]
    state.revealed.append(cell)
    correct = state.board[first] == state.board[cell]
    _record_press(state, cell, player_id, correct)
    if correct:
        state.matched.extend((first, cell))
        state.revealed.clear()
        state.score += 1
        _credit(state, player_id)
        if state.score >= state.goal:
            _finish(state, True)
    else:
        state.mistakes += 1
        state.lock_time = _SOUL_MISMATCH_SECONDS
    state.revision += 1
    return True


def _record_press(
    state: MiniGameState, cell: int, player_id: str, correct: bool
) -> None:
    state.last_cell = cell
    state.last_player_id = player_id
    state.last_correct = bool(correct)
    state.feedback_time = 0.42


def _credit(state: MiniGameState, player_id: str) -> None:
    state.contributions[player_id] = state.contributions.get(player_id, 0) + 1


def _finish(state: MiniGameState, won: bool) -> None:
    if state.outcome:
        return
    state.outcome = "won" if won else "lost"
    state.phase = "result"
    state.result_time = _RESULT_SECONDS
    state.active_cell = -1
    state.target_time = 0.0
    state.lock_time = 0.0
    state.revision += 1


def _garden_target_seconds(state: MiniGameState) -> float:
    # The final bloom is quicker, but never twitchier than ordinary network
    # latency permits.  A 1.15 s floor leaves ample room at 100-200 ms RTT.
    return max(1.15, _GARDEN_TARGET_SECONDS - state.score * 0.055)


def _next_garden_cell(state: MiniGameState) -> int:
    salt = state.score * 131 + state.mistakes * 313 + state.revision * 17
    rng = random.Random(state.seed ^ 0x6A2D_4E11 ^ salt)
    candidate = rng.randrange(max(1, len(state.board)))
    if len(state.board) > 1 and candidate == state.active_cell:
        candidate = (candidate + 1 + rng.randrange(len(state.board) - 1)) % len(
            state.board
        )
    return candidate


def encode_mini_game_intent(state: MiniGameState, cell: int) -> str:
    """Compact target payload for the existing multiplayer intent envelope."""

    return f"{state.instance_id}:{state.revision}:{int(cell)}"


def encode_mini_game_ready_intent(state: MiniGameState) -> str:
    """Compact instance-scoped ready target for the existing intent envelope."""

    return f"{state.instance_id}:ready"


def decode_mini_game_ready_intent(target: Any) -> int | None:
    """Parse a bounded ``instance:ready`` target."""

    if not isinstance(target, str) or len(target) > 48:
        return None
    parts = target.split(":")
    if len(parts) != 2 or parts[1] != "ready":
        return None
    try:
        instance_id = int(parts[0])
    except (TypeError, ValueError):
        return None
    return instance_id if instance_id > 0 else None


def decode_mini_game_intent(target: Any) -> tuple[int, int, int] | None:
    """Parse a bounded ``instance:revision:cell`` target."""

    if not isinstance(target, str) or len(target) > 48:
        return None
    parts = target.split(":")
    if len(parts) != 3:
        return None
    try:
        instance_id, revision, cell = (int(part) for part in parts)
    except (TypeError, ValueError):
        return None
    if instance_id <= 0 or revision < 0 or not 0 <= cell < 12:
        return None
    return instance_id, revision, cell
