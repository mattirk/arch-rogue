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

# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

import math
import random
import re
from bisect import bisect_right
from typing import Any

from ..content import (
    BOSS_MIRROR_OMEN_LINES,
    BOSS_OMEN_LINES,
    RUE_DEATH_LINES,
    STORY_ARCS,
    STORY_CRISIS_ECHOES,
    STORY_ENDING_FORSAKEN_CODAS,
    STORY_ENDING_ROAD_CODAS,
    STORY_ENDINGS,
    STORY_GATE_CHOICES,
    STORY_LOCATION_MOTIFS,
    STORY_ROAD_LINES,
)
from ..models import (
    FloatingText,
    IdleNpc,
    Item,
    Room,
    SecretCache,
    Shrine,
    SpecialRoom,
    StoryGuest,
)
from .engine import (
    StoryEngine,
    clamp_story_effect,
    record_story_choice,
    record_unanswered_story_beat,
    story_beat_for_depth,
    story_beat_index_for_depth,
    story_effect,
    story_guest_from_beat,
    story_road,
)
from .minigames import (
    GARDEN_MINI_GAME,
    MINI_GAME_KINDS,
    SOUL_MINI_GAME,
    STORY_MINI_GAME,
    MiniGameState,
    apply_mini_game_input,
    confirm_mini_game_ready,
    create_mini_game,
    update_mini_game,
)
from .quest_assets import ActiveQuestCutscene, RuntimeDialogueChoice, format_asset_text


class StoryRuntimeMixin:
    # Narrator typewriter speed multiplier (milestone 3.11). Higher values
    # make the narrator read faster; delays are divided by this factor.
    CUTSCENE_NARRATION_SPEED = 2.25

    # Bind the Page punctuates three authored turning points without making
    # every floor opening feel like a toll booth. Garden/Soul completion lives
    # on SpecialRoom.state, while the story outcome lives with story flags.
    _STORY_MINI_GAME_DEPTHS = frozenset((5, 8, 9))
    _GARDEN_MINI_GAME_STATE_KEY = "garden_mini_game_outcome"
    _SOUL_MINI_GAME_STATE_KEY = "soul_mini_game_outcome"
    # Slightly more forgiving than ordinary greetings because the frogs keep
    # dancing and wandering while the player approaches them.
    GARDEN_FROG_TALK_RANGE = 1.35

    def start_story_mode(self) -> None:
        # A fresh descent cannot inherit a modal or its instance namespace.
        # Saved runs restore their active model after this initialization.
        self.active_mini_game = None
        self._mini_game_instance_counter = 0
        self.mini_game_cursor = 0
        self.story_seed = self.rng.randrange(1, 2**31)
        self.story_state = StoryEngine.generate(
            self.story_seed,
            self.selected_archetype.name,
            self.run_number,
            self.theme.name,
            self.run_modifier.name,
        )
        self.story_guests = []
        self.idle_npcs = []
        self.story_gate_verb = ""
        # Milestone 3.15 - familiars are reset with the rest of the run state
        # when story mode (re)starts. The field always exists on Game.
        self.familiars = []
        self.light_sources = []
        self.lights = []
        self._apply_story_theme_for_current_depth()

    # --- cooperative cutscene mini-games --------------------------------

    def _mini_game_is_joiner(self) -> bool:
        checker = getattr(self, "mp_is_joiner", None)
        return bool(checker()) if callable(checker) else False

    def _next_mini_game_instance_id(self) -> int:
        active = getattr(self, "active_mini_game", None)
        active_id = active.instance_id if isinstance(active, MiniGameState) else 0
        counter = max(
            0,
            int(getattr(self, "_mini_game_instance_counter", 0)),
            active_id,
        )
        counter += 1
        self._mini_game_instance_counter = counter
        return counter

    def _mini_game_seed(self, kind: str, instance_id: int, context: str) -> int:
        """Return a stable seed without consuming the gameplay RNG stream."""

        kind_salt = {
            STORY_MINI_GAME: 0x51A7_0A11,
            GARDEN_MINI_GAME: 0x6A2D_4E11,
            SOUL_MINI_GAME: 0x50A1_EC40,
        }[kind]
        context_salt = 0
        for char in context[:32]:
            context_salt = (context_salt * 131 + ord(char)) & 0x7FFF_FFFF
        seed = (
            int(getattr(self, "story_seed", 1)) * 65_537
            + int(getattr(self, "run_number", 1)) * 7_919
            + int(getattr(self, "current_depth", 1)) * 4_099
            + instance_id * 257
            + context_salt
        ) ^ kind_salt
        return (seed & 0x7FFF_FFFF) or 1

    def start_mini_game(
        self,
        kind: str,
        *,
        context: str = "",
        origin_player_id: str = "",
    ) -> bool:
        """Start one host-authoritative mini-game if no modal is already live."""

        if (
            kind not in MINI_GAME_KINDS
            or getattr(self, "active_mini_game", None) is not None
            or self._mini_game_is_joiner()
        ):
            return False
        instance_id = self._next_mini_game_instance_id()
        player = getattr(self, "player", None)
        origin = origin_player_id or getattr(player, "player_id", "p1")
        required_player_ids: list[str] = []
        active_players = getattr(self, "active_players", None)
        players = tuple(active_players()) if callable(active_players) else ()
        for participant in players:
            player_id = str(getattr(participant, "player_id", ""))[:32]
            if player_id and player_id not in required_player_ids:
                required_player_ids.append(player_id)
        session = getattr(self, "mp_session", None)
        if (
            getattr(self, "mp_active", False)
            and session is not None
            and bool(getattr(session, "started", False))
        ):
            for value in (
                getattr(session, "player_id", ""),
                getattr(session, "partner_player_id", ""),
            ):
                player_id = str(value)[:32]
                if player_id and player_id not in required_player_ids:
                    required_player_ids.append(player_id)
        self.active_mini_game = create_mini_game(
            kind,
            instance_id=instance_id,
            seed=self._mini_game_seed(kind, instance_id, context),
            depth=int(getattr(self, "current_depth", 1)),
            context=context[:32],
            origin_player_id=str(origin or "p1"),
            required_player_ids=required_player_ids,
        )
        self.mini_game_cursor = 0
        # App lifecycle saves made during the guide/preview must retain the
        # selected continuation and cannot reopen a once-only room game.
        self.save_run()
        return True

    def submit_mini_game_ready(self, player_id: str) -> bool:
        """Record one host-authoritative ready confirmation."""

        state = getattr(self, "active_mini_game", None)
        if not isinstance(state, MiniGameState) or self._mini_game_is_joiner():
            return False
        changed = confirm_mini_game_ready(state, str(player_id or "")[:32])
        if changed:
            self.save_run()
        return changed

    def confirm_active_mini_game_ready(self) -> bool:
        """Confirm readiness through the local player's Interact action."""

        state = getattr(self, "active_mini_game", None)
        if not isinstance(state, MiniGameState) or state.phase != "ready":
            return False
        if self._mini_game_is_joiner():
            sender = getattr(self, "mp_queue_mini_game_ready", None)
            return bool(sender()) if callable(sender) else False
        local_player = getattr(self, "local_player", None)
        player = (
            local_player()
            if callable(local_player)
            else getattr(self, "player", None)
        )
        return self.submit_mini_game_ready(
            getattr(player, "player_id", "p1"),
        )

    def submit_mini_game_cell(
        self,
        cell: int,
        player_id: str,
        expected_revision: int,
    ) -> bool:
        """Apply a revision-stamped press on the host.

        Fallen co-op players remain valid contributors: the dungeon is paused
        and these games deliberately give a defeated guest something to do.
        """

        state = getattr(self, "active_mini_game", None)
        if not isinstance(state, MiniGameState) or self._mini_game_is_joiner():
            return False
        player_id = str(player_id or "")[:32]
        active_players = getattr(self, "active_players", None)
        players = tuple(active_players()) if callable(active_players) else ()
        valid_ids = {
            str(getattr(player, "player_id", ""))
            for player in players
            if player is not None
        }
        if valid_ids and player_id not in valid_ids:
            return False
        return apply_mini_game_input(
            state,
            cell=int(cell),
            player_id=player_id or "p1",
            expected_revision=int(expected_revision),
        )

    def activate_mini_game_cell(self, cell: int) -> bool:
        """Local tap/click/controller entry point for one board cell."""

        state = getattr(self, "active_mini_game", None)
        if not isinstance(state, MiniGameState):
            return False
        try:
            cell = int(cell)
        except (TypeError, ValueError):
            return False
        if not 0 <= cell < len(state.board):
            return False
        if self._mini_game_is_joiner():
            sender = getattr(self, "mp_queue_mini_game_cell", None)
            return bool(sender(cell)) if callable(sender) else False
        local_player = getattr(self, "local_player", None)
        player = local_player() if callable(local_player) else getattr(self, "player", None)
        return self.submit_mini_game_cell(
            cell,
            getattr(player, "player_id", "p1"),
            state.revision,
        )

    def update_active_mini_game(
        self, dt: float, *, authoritative: bool = True
    ) -> bool:
        """Advance the active model and finalize after its result card expires."""

        state = getattr(self, "active_mini_game", None)
        if not isinstance(state, MiniGameState):
            return False
        authoritative = bool(authoritative) and not self._mini_game_is_joiner()
        result_finished = update_mini_game(
            state,
            dt,
            authoritative=authoritative,
        )
        if result_finished and authoritative:
            return self.finalize_active_mini_game()
        return False

    def _mini_game_special_room(
        self, state: MiniGameState, expected_kind: str
    ) -> SpecialRoom | None:
        dungeon = getattr(self, "dungeon", None)
        if dungeon is None:
            return None
        room_index = -1
        prefix, separator, value = state.context.partition(":")
        if separator and prefix == "room":
            try:
                room_index = int(value)
            except ValueError:
                room_index = -1
        for special in getattr(dungeon, "special_rooms", ()):
            if special.kind == expected_kind and (
                room_index < 0 or special.room_index == room_index
            ):
                return special
        finder = getattr(dungeon, "special_room_for_kind", None)
        return finder(expected_kind) if callable(finder) else None

    def _story_mini_game_outcome(self, depth: int | None = None) -> str:
        story = getattr(self, "story_state", None)
        if story is None:
            return ""
        target_depth = int(
            getattr(self, "current_depth", 1) if depth is None else depth
        )
        prefix = f"{target_depth}:minigame:{STORY_MINI_GAME}:"
        for flag in story.flags:
            if flag.startswith(prefix):
                outcome = flag.removeprefix(prefix)
                if outcome in ("won", "lost"):
                    return outcome
        return ""

    def _record_story_mini_game_outcome(self, outcome: str) -> bool:
        story = getattr(self, "story_state", None)
        if story is None or self._story_mini_game_outcome():
            return False
        story.flags.append(
            f"{self.current_depth}:minigame:{STORY_MINI_GAME}:{outcome}"
        )
        story.log.append(
            f"Depth {self.current_depth}: Bind the Page — {outcome}."
        )
        del story.log[:-12]
        return True

    def _mini_game_reward_players(self) -> tuple[Any, ...]:
        active_players = getattr(self, "active_players", None)
        if callable(active_players):
            players = tuple(player for player in active_players() if player is not None)
            if players:
                return players
        player = getattr(self, "player", None)
        return (player,) if player is not None else ()

    def _grant_mini_game_reward(self, kind: str) -> None:
        """Grant the mini-game's party-wide restorative or permanent boon."""

        labels = {
            STORY_MINI_GAME: "Pagebound: life restored, edge sharpened",
            GARDEN_MINI_GAME: "Moonbloom: life and focus deepen",
            SOUL_MINI_GAME: "Unlost echo: arcana deepened",
        }
        colors = {
            STORY_MINI_GAME: (202, 166, 245),
            GARDEN_MINI_GAME: (150, 220, 130),
            SOUL_MINI_GAME: (120, 214, 205),
        }
        for player in self._mini_game_reward_players():
            if kind == STORY_MINI_GAME:
                player.hp = player.max_hp
                player.melee_bonus += 1
            elif kind == GARDEN_MINI_GAME:
                player.max_hp += 5
                if player.hp > 0:
                    player.hp = min(player.max_hp, player.hp + 5)
                player.max_mana += 5
                player.mana = min(player.max_mana, player.mana + 5)
            else:
                player.max_mana += 5
                player.mana = min(player.max_mana, player.mana + 5)
                player.spell_bonus += 1
            self.floaters.append(
                FloatingText(
                    labels[kind],
                    player.x,
                    player.y - 0.6,
                    colors[kind],
                    ttl=1.4,
                )
            )
        self.play_sfx("shrine")

    @staticmethod
    def _story_choice_from_mini_game_context(context: str) -> int | None:
        prefix, separator, value = context.partition(":")
        if not separator or prefix != "choice":
            return None
        try:
            return int(value)
        except ValueError:
            return None

    def finalize_active_mini_game(self) -> bool:
        """Persist one outcome, grant its reward once, and continue the story."""

        state = getattr(self, "active_mini_game", None)
        if (
            not isinstance(state, MiniGameState)
            or state.outcome not in ("won", "lost")
            or self._mini_game_is_joiner()
        ):
            return False

        outcome = state.outcome
        continuation: int | None = None
        marker_added = False
        special: SpecialRoom | None = None
        if state.kind == STORY_MINI_GAME:
            marker_added = self._record_story_mini_game_outcome(outcome)
            continuation = self._story_choice_from_mini_game_context(state.context)
        elif state.kind == GARDEN_MINI_GAME:
            special = self._mini_game_special_room(state, "garden")
            if special is not None and not special.state.get(
                self._GARDEN_MINI_GAME_STATE_KEY
            ):
                special.state[self._GARDEN_MINI_GAME_STATE_KEY] = outcome
                marker_added = True
        elif state.kind == SOUL_MINI_GAME:
            special = self._mini_game_special_room(state, "lossless_soul")
            if special is not None and not special.state.get(
                self._SOUL_MINI_GAME_STATE_KEY
            ):
                special.state[self._SOUL_MINI_GAME_STATE_KEY] = outcome
                marker_added = True
        else:
            return False

        # Clear before calling continuations: their save snapshots must not
        # resurrect a completed result, and a second finalize becomes a no-op.
        self.active_mini_game = None
        self.mini_game_cursor = 0
        if marker_added and outcome == "won":
            self._grant_mini_game_reward(state.kind)

        if state.kind == STORY_MINI_GAME:
            if continuation is not None:
                self._commit_story_relic_path(continuation)
            else:
                # A malformed old/local save still releases the modal. The
                # recorded outcome lets the player select a path again without
                # farming another reward.
                self.save_run()
            return True

        if state.kind == SOUL_MINI_GAME:
            if getattr(self, "active_cutscene", None) is None:
                self.start_quest_cutscene("lossless_soul_reflection")
            self.set_active_cutscene_node("reflection")
        self.save_run()
        return True

    def current_story_beat(self) -> Any:
        return story_beat_for_depth(self.story_state, self.current_depth)

    def story_effect_value(
        self, key: str, minimum: float = -1.0, maximum: float = 1.0
    ) -> float:
        return clamp_story_effect(story_effect(self.story_state, key), minimum, maximum)

    def story_header_line(self) -> str:
        if self.story_state is None:
            return "Story: unwritten"
        beat = self.current_story_beat()
        if beat is None:
            return f"Story: {self.story_state.title}"
        status = "resolved" if beat.resolved_choice else "unresolved"
        return f"Story: {self.story_state.title} · {beat.title} ({status})"

    def story_choice_preview(self, choice_key: str) -> str:
        previews = {
            "aid": "mercy wards, heals, and reveals",
            "bargain": "relic power for blood and curses",
            "defy": "damage, XP, and hunters",
        }
        return previews.get(choice_key, "the dungeon answers")

    def story_choices_hint(self, guest: StoryGuest) -> str:
        # <=48 chars: the mobile prompt shows two 24-char lines and silently
        # drops the rest, so the hint is a key legend, not a summary.
        entries = [
            f"{index + 1} {choice.label}"
            for index, choice in enumerate(guest.choices[:3])
        ]
        return " · ".join(entries) + " · E hear plea"

    def current_story_road(self) -> str:
        """The run's Road (witness/debtor/defiant/forsaken) at this depth."""
        return story_road(self.story_state, self.current_depth)

    def _omen_extra_line(self) -> str:
        """Boss office foreshadow (boss floors) or the road clause (later acts)."""
        plan = self.current_floor_plan()
        boss_key = plan.boss_key if plan is not None else ""
        if boss_key:
            archetype = getattr(
                self.player, "class_name", self.selected_archetype.name
            )
            return BOSS_MIRROR_OMEN_LINES.get(
                (boss_key, archetype), BOSS_OMEN_LINES.get(boss_key, "")
            )
        return STORY_ROAD_LINES.get(self.current_story_road(), "")

    def _omen_body(self, beat) -> str:
        """The floor omen: title, scene, stake, reveal — <=345 chars.

        345 = five narrator lines at the tracked 22 px font (~70 chars per
        line). The card guarantees four lines and usually shows five; on the
        smallest windows the completed narration tail-follows, so the reveal
        sentence stays visible and only the title line scrolls off.

        4.9.x "more revealing": the dilemma's plain-spoken truth sentence
        rides after the stake, and boss floors keep the stake with the office
        foreshadow taking the truth's slot. Assembly drops parts from the end
        whenever the budget would break, so the surface can never overflow
        its guaranteed four visible lines at choice time.
        """
        if beat is None:
            return "The dungeon waits in silence."
        summary = str(beat.summary)
        scene, separator, stake = summary.partition(". ")
        scene = f"{scene}." if separator else summary
        truth = str(getattr(beat, "truth", ""))
        plan = self.current_floor_plan()
        # No "Depth N" prefix: the cutscene header and HUD already carry the
        # depth (recap ban) — the beat title alone keeps the ink for the
        # reveal sentence. Depth 1 opens with Rue's one-line greeting; the
        # separate prologue screen is gone (too much text before play).
        parts = [f"{beat.title}.", scene]
        if self.current_depth == 1:
            parts.insert(0, self.rue_greeting_line())
        if stake:
            parts.append(stake)
        if plan is not None and plan.boss_key:
            parts.append(self._omen_extra_line())
        else:
            if truth:
                parts.append(truth)
            road_line = STORY_ROAD_LINES.get(self.current_story_road(), "")
            if road_line:
                parts.append(road_line)
        body = ""
        for part in parts:
            if not part:
                continue
            candidate = f"{body} {part}".strip()
            if body and len(candidate) > 345:
                break
            body = candidate
        return body

    def rue_greeting_line(self) -> str:
        """Nim Rue opens the ledger entry; across runs she remembers."""
        pages = int(self.meta_progress.get("runs_started", 0)) if hasattr(
            self, "meta_progress"
        ) else 0
        clears = int(self.meta_progress.get("clears", 0)) if hasattr(
            self, "meta_progress"
        ) else 0
        if pages <= 1:
            return "A fresh page. — N. Rue, for the Worms."
        if clears > 0:
            return f"Page {pages}. One entry finished. I still reread it. — N. Rue."
        return f"Page {pages}. I have written you before. — N. Rue."

    def story_death_line(self) -> str:
        """Rue's one line on the death screen, shaded by the run's road."""
        road = self.current_story_road()
        return RUE_DEATH_LINES.get(road, RUE_DEATH_LINES["unwritten"])

    def story_crisis_verb(self) -> str:
        """The depth-9 tether crisis outcome, if the run reached it."""
        if self.story_state is None:
            return ""
        for flag in self.story_state.flags:
            if flag.startswith("crisis:"):
                return flag.removeprefix("crisis:")
        return ""

    def story_name_known(self, name_key: str) -> bool:
        return (
            self.story_state is not None
            and f"name:{name_key}" in self.story_state.flags
        )

    def _story_ending_context(self, archetype_name: str) -> dict[str, str]:
        """The epilogue node's text, keyed by the chosen gate verb.

        Empty strings until the Gate has been answered; the epilogue node is
        the only template that reads these keys.
        """
        verb = str(getattr(self, "story_gate_verb", ""))
        endings = STORY_ENDINGS.get(archetype_name, {})
        ending = endings.get(verb)
        if ending is None:
            return {"ending_title": "", "ending_body": "", "ending_coda": ""}
        road = self.current_story_road()
        coda_parts = [
            STORY_CRISIS_ECHOES.get(archetype_name, {}).get(
                self.story_crisis_verb(), ""
            )
        ]
        if road == "forsaken":
            coda_parts.append(STORY_ENDING_FORSAKEN_CODAS.get(archetype_name, ""))
        else:
            coda_parts.append(STORY_ENDING_ROAD_CODAS.get(road, ""))
        if verb == "aid" and self.story_name_known("liss"):
            coda_parts.append(
                "He asks the door to wait. The door — for the first time in a "
                "hundred years — waits."
            )
        return {
            "ending_title": ending.title,
            "ending_body": ending.body,
            "ending_coda": " ".join(part for part in coda_parts if part),
        }

    def quest_cutscene_context(self, guest: StoryGuest | None = None) -> dict[str, str]:
        beat = self.current_story_beat()
        story = self.story_state
        active_guest = guest or self.current_story_guest_for_depth()
        if active_guest is None:
            active_guest = self.nearby_story_guest()
        motif = next(
            (
                candidate
                for candidate in STORY_LOCATION_MOTIFS
                if beat is not None and candidate.theme_name == beat.theme_name
            ),
            None,
        )
        location_image = (
            motif.image
            if motif is not None
            else (beat.theme_name.lower() if beat is not None else "unlit stone")
        )
        location_danger = (
            motif.danger if motif is not None else "the dungeon listens for hesitation"
        )
        guest_name = active_guest.name if active_guest else "Unknown Guest"
        guest_role = active_guest.role if active_guest else "Guest"
        guest_motive = active_guest.motive if active_guest else "waits for a choice"
        guest_dialogue = (
            active_guest.dialogue
            if active_guest
            else (beat.dialogue if beat else "The guest waits for an answer.")
        )
        cinematic_narration = self._omen_body(beat)
        archetype_name = getattr(
            self.player, "class_name", self.selected_archetype.name
        )
        arc = STORY_ARCS.get(archetype_name)
        context = {
            "rue_greeting": self.rue_greeting_line(),
            "oath_line": f"Your oath: {arc.oath[0].lower()}{arc.oath[1:]}"
            if arc
            else "Your oath waits below.",
            "omen_body": cinematic_narration,
            "road": self.current_story_road(),
            "road_line": STORY_ROAD_LINES.get(self.current_story_road(), ""),
            "boss_line": self._omen_extra_line(),
            **self._story_ending_context(archetype_name),
            "depth": str(self.current_depth),
            "player_class": getattr(
                self.player, "class_name", self.selected_archetype.name
            ),
            "story_title": story.title if story else "Unwritten Descent",
            "player_backstory": story.player_backstory
            if story
            else "An unnamed exile descends.",
            "objective": story.objective if story else "Survive the dungeon.",
            "antagonist": story.antagonist if story else "Gate Tyrant",
            "faction": story.faction if story else "the dungeon",
            "rival_faction": story.rival_faction if story else "the rival faction",
            "relic_name": story.relic_name if story else "Nameless Relic",
            "relic_form": story.relic_form if story else "a relic",
            "relic_temptation": story.relic_temptation
            if story
            else "it wants to be used",
            "location_image": location_image,
            "location_danger": location_danger,
            "cinematic_narration": cinematic_narration,
            "beat_title": beat.title if beat else "Unwritten Beat",
            "beat_summary": beat.summary if beat else "The floor waits in silence.",
            "beat_dialogue": beat.dialogue
            if beat
            else "The guest waits for an answer.",
            "guest_name": guest_name,
            "guest_role": guest_role,
            "guest_motive": guest_motive,
            "guest_dialogue": guest_dialogue,
        }
        context.update(self._lossless_soul_cutscene_context(story))
        return {key: " ".join(str(value).split()) for key, value in context.items()}

    def _lossless_soul_cutscene_context(self, story) -> dict[str, str]:
        """Keys for the Hall of Unlost Echoes, tailored to the run so far.

        The keeper recalls the player's most recent *finished* story turning —
        an unanswered beat is a memory she refuses to invent — and, once the
        hall's mirror has been answered, phrases what she now keeps.
        """
        resolved_beats = [
            beat
            for beat in (story.beats if story is not None else [])
            if beat.resolved_choice and beat.resolved_choice != "unanswered"
        ]
        last_beat = resolved_beats[-1] if resolved_beats else None
        if last_beat is not None:
            soul_memory_line = (
                f"“Your last finished turning — '{last_beat.title}'. "
                f"It says: {last_beat.outcome}”"
            )
            soul_prompt = (
                "“I keep what you refuse to lose. What shall I do with it?”"
            )
        else:
            soul_memory_line = (
                "“You have finished nothing yet. My father counted "
                "everything except me. Then only me.”"
            )
            soul_prompt = "“What shall I do with the memory you carry now?”"
        soul_room = self._lossless_soul_room_at_player()
        soul_choice = (
            str(soul_room.state.get("soul_choice", "")) if soul_room else ""
        )
        soul_kept_line = {
            "preserve": (
                "The hall keeps your memory whole — pain and all. "
                "Nothing of you fades here."
            ),
            "release": (
                "Your memory rests here lightly. It remains, yet it no "
                "longer rules your next turning."
            ),
            "refuse": (
                "You kept your history your own. "
                "The mirror holds no copy of you."
            ),
        }.get(soul_choice, "The chimes hold their breath, waiting for your answer.")
        if soul_choice in ("preserve", "release") and self.story_name_known("liss"):
            soul_kept_line = (
                f"{soul_kept_line} …My name is Liss Voss. Keep that too. "
                "Names open what they love — say mine at the door, not his."
            )
        return {
            "soul_memory_line": soul_memory_line,
            "soul_prompt": soul_prompt,
            "soul_kept_line": soul_kept_line,
        }

    def start_quest_cutscene(
        self, asset_id: str, guest: StoryGuest | None = None
    ) -> bool:
        asset = self.quest_cutscenes.get(asset_id)
        if asset is None:
            return False
        active_guest = guest or self.current_story_guest_for_depth()
        self.active_cutscene = ActiveQuestCutscene(
            asset_id=asset.id,
            node_id=asset.start_node,
            guest_depth=active_guest.depth if active_guest else self.current_depth,
            guest_beat_index=active_guest.beat_index if active_guest else -1,
            context=self.quest_cutscene_context(active_guest),
        )
        # Reset transient navigation when a new cutscene begins.
        self.cutscene_cursor = 0
        self.reset_active_cutscene_narration_scroll()
        return True

    def close_active_cutscene(self) -> None:
        self.active_cutscene = None
        self.cutscene_cursor = 0
        self.reset_active_cutscene_narration_scroll()

    def reset_active_cutscene_narration_scroll(self) -> None:
        self.cutscene_narration_scroll = 0
        self.cutscene_narration_follow_tail = True
        self.cutscene_scroll_axis_direction = 0
        self.cutscene_scroll_axis_repeat = 0.0

    def scroll_active_cutscene_narration(self, delta: int) -> bool:
        """Scroll completed narration without affecting dialogue choices."""
        if self.active_cutscene is None or not self.active_cutscene_narration_complete():
            return False
        scroll_max = max(
            0,
            int(getattr(self, "_cutscene_narration_scroll_max", 0)),
        )
        if scroll_max <= 0:
            self.cutscene_narration_scroll = 0
            self.cutscene_narration_follow_tail = True
            return False
        current = (
            scroll_max
            if getattr(self, "cutscene_narration_follow_tail", True)
            else max(
                0,
                min(int(getattr(self, "cutscene_narration_scroll", 0)), scroll_max),
            )
        )
        target = max(0, min(current + int(delta), scroll_max))
        self.cutscene_narration_scroll = target
        self.cutscene_narration_follow_tail = False
        return target != current

    def update_active_cutscene_scroll_input(self, dt: float) -> None:
        """Edge/repeat scrolling for the otherwise-unused cutscene right stick."""
        scroll_max = int(getattr(self, "_cutscene_narration_scroll_max", 0))
        if (
            self.active_cutscene is None
            or not self.active_cutscene_narration_complete()
            or scroll_max <= 0
        ):
            self.cutscene_scroll_axis_direction = 0
            self.cutscene_scroll_axis_repeat = 0.0
            return
        _x, y = self.input.right_vec()
        direction = 1 if y > 0.55 else -1 if y < -0.55 else 0
        previous = int(getattr(self, "cutscene_scroll_axis_direction", 0))
        if direction == 0:
            self.cutscene_scroll_axis_direction = 0
            self.cutscene_scroll_axis_repeat = 0.0
            return
        if direction != previous:
            self.scroll_active_cutscene_narration(direction * 2)
            self.cutscene_scroll_axis_direction = direction
            self.cutscene_scroll_axis_repeat = 0.32
            return
        repeat = max(0.0, float(self.cutscene_scroll_axis_repeat) - max(0.0, dt))
        if repeat <= 0.0:
            self.scroll_active_cutscene_narration(direction)
            repeat = 0.10
        self.cutscene_scroll_axis_repeat = repeat

    def active_cutscene_asset(self) -> Any:
        if self.active_cutscene is None:
            return None
        return self.quest_cutscenes.get(self.active_cutscene.asset_id)

    def active_cutscene_node(self) -> Any:
        asset = self.active_cutscene_asset()
        if asset is None or self.active_cutscene is None:
            return None
        return asset.nodes.get(self.active_cutscene.node_id)

    def active_cutscene_guest(self) -> StoryGuest | None:
        if self.active_cutscene is None:
            return None
        if self.active_cutscene.guest_beat_index >= 0:
            for guest in self.story_guests:
                if (
                    guest.depth == self.active_cutscene.guest_depth
                    and guest.beat_index == self.active_cutscene.guest_beat_index
                ):
                    return guest
        return self.nearby_story_guest() or self.current_story_guest_for_depth()

    def active_cutscene_text(self) -> str:
        node = self.active_cutscene_node()
        if node is None or self.active_cutscene is None:
            return ""
        # start_quest_cutscene/set_active_cutscene_node snapshot the complete
        # formatting context. Rebuilding it every rendered frame repeatedly walks
        # story/guest state even though narration is immutable within the node.
        context = self.active_cutscene.context
        if not context:
            context = self.quest_cutscene_context(self.active_cutscene_guest())
        return format_asset_text(node.text, context)

    def cutscene_narration_char_delay(self, char: str) -> float:
        speed = self.CUTSCENE_NARRATION_SPEED
        if char == "\n":
            return 0.18 / speed
        if char in ".!?":
            return 0.25 / speed
        if char in ";:":
            return 0.16 / speed
        if char in ",\u2014":
            return 0.10 / speed
        if char.isspace():
            return 0.012 / speed
        return 0.026 / speed

    def _cutscene_narration_timeline(self, narration: str) -> tuple[float, ...]:
        """Return cached cumulative reveal times for one immutable narration."""

        cache = getattr(self, "_cutscene_narration_timeline_cache", None)
        if not isinstance(cache, dict):
            cache = {}
            self._cutscene_narration_timeline_cache = cache
        cached = cache.get(narration)
        if cached is not None:
            return cached
        elapsed = 0.0
        timeline: list[float] = []
        for char in narration:
            elapsed += self.cutscene_narration_char_delay(char)
            timeline.append(elapsed)
        cached = tuple(timeline)
        if len(cache) >= 32:
            cache.clear()
        cache[narration] = cached
        return cached

    def active_cutscene_narration_duration(self, text: str | None = None) -> float:
        narration = self.active_cutscene_text() if text is None else text
        if not narration:
            return 0.0
        timeline = self._cutscene_narration_timeline(narration)
        return timeline[-1] if timeline else 0.0

    def active_cutscene_narration_char_count(self, text: str | None = None) -> int:
        if self.active_cutscene is None:
            return 0
        narration = self.active_cutscene_text() if text is None else text
        if not narration:
            return 0
        elapsed = max(0.0, self.active_cutscene.node_elapsed)
        return bisect_right(self._cutscene_narration_timeline(narration), elapsed)

    def active_cutscene_narration_snapshot(self) -> tuple[str, str, bool, float]:
        """Return narration text, visible slice, completion, and progress.

        Rendering consumes all four values together; calculating them here keeps
        the typewriter delay scan to once per frame instead of three times.
        """
        narration = self.active_cutscene_text()
        if not narration:
            return "", "", True, 1.0
        char_count = self.active_cutscene_narration_char_count(narration)
        complete = char_count >= len(narration)
        progress = min(1.0, char_count / len(narration))
        return narration, narration[:char_count], complete, progress

    def active_cutscene_visible_text(self) -> str:
        return self.active_cutscene_narration_snapshot()[1]

    def active_cutscene_narration_complete(self) -> bool:
        return self.active_cutscene_narration_snapshot()[2]

    def active_cutscene_narration_progress(self) -> float:
        return self.active_cutscene_narration_snapshot()[3]

    def active_cutscene_current_sentence_text(self) -> str:
        narration = self.active_cutscene_text()
        if not narration:
            return ""
        char_count = self.active_cutscene_narration_char_count(narration)
        if char_count <= 0:
            return ""
        cursor = min(char_count, len(narration))
        start = 0
        for mark in (". ", "! ", "? ", "\n"):
            found = narration.rfind(mark, 0, cursor)
            if found >= 0:
                start = max(start, found + len(mark))
        end_candidates = [
            found
            for mark in (".", "!", "?", "\n")
            if (found := narration.find(mark, cursor)) >= 0
        ]
        end = min(end_candidates) if end_candidates else len(narration)
        return narration[start:end].strip()

    def reveal_active_cutscene_narration(self) -> None:
        if self.active_cutscene is None:
            return
        self.cutscene_narration_follow_tail = True
        self.active_cutscene.node_elapsed = max(
            self.active_cutscene.node_elapsed,
            self.active_cutscene_narration_duration() + 0.05,
        )

    def active_cutscene_speaker_name(self) -> str:
        asset = self.active_cutscene_asset()
        node = self.active_cutscene_node()
        if asset is None or node is None or self.active_cutscene is None:
            return "Nim Rue"
        if node.speaker == "narrator":
            # 4.9: the narrator is a person — Nim Rue, mirror-scribe of the
            # Scriptorium, writing the run as a rationed ledger entry.
            return "Nim Rue"
        actor = asset.actors.get(node.speaker)
        if actor is None:
            return node.speaker.title()
        context = self.active_cutscene.context
        if not context:
            context = self.quest_cutscene_context(self.active_cutscene_guest())
        return format_asset_text(actor.name, context)

    def active_cutscene_choices(self) -> list[RuntimeDialogueChoice]:
        node = self.active_cutscene_node()
        if node is None:
            return []
        if node.choice_source == "story_relic_options":
            return [
                RuntimeDialogueChoice(
                    label=label,
                    detail=detail,
                    action="choose_story_relic_path",
                    choice_key=choice_key,
                    source_index=index,
                )
                for index, (choice_key, label, detail) in enumerate(
                    self.story_relic_choice_options()
                )
            ]
        if node.choice_source == "story_guest_choices":
            guest = self.active_cutscene_guest()
            if guest is None:
                return []
            return [
                RuntimeDialogueChoice(
                    label=choice.label,
                    detail=f"{choice.intent} ({self.story_choice_preview(choice.key)})",
                    action="resolve_story_choice",
                    choice_key=choice.key,
                    source_index=index,
                )
                for index, choice in enumerate(guest.choices[:3])
            ]
        if node.choice_source == "story_gate_options":
            return [
                RuntimeDialogueChoice(
                    label=label,
                    detail=detail,
                    action="choose_gate_verb",
                    choice_key=choice_key,
                    source_index=index,
                )
                for index, (choice_key, label, detail) in enumerate(
                    STORY_GATE_CHOICES
                )
            ]
        context = (
            {**self.active_cutscene.context}
            if self.active_cutscene is not None
            else self.quest_cutscene_context()
        )
        return [
            RuntimeDialogueChoice(
                label=format_asset_text(choice.label, context),
                detail=format_asset_text(choice.detail, context),
                next_node=choice.next_node,
                action=choice.action,
                choice_key=choice.choice_key,
                source_index=index,
            )
            for index, choice in enumerate(node.choices)
        ]

    def set_active_cutscene_node(self, node_id: str) -> bool:
        asset = self.active_cutscene_asset()
        if asset is None or self.active_cutscene is None or node_id not in asset.nodes:
            return False
        self.active_cutscene.node_id = node_id
        self.active_cutscene.node_elapsed = 0.0
        self.cutscene_cursor = 0
        self.active_cutscene.context = self.quest_cutscene_context(
            self.active_cutscene_guest()
        )
        self.reset_active_cutscene_narration_scroll()
        return True

    def advance_active_cutscene(self) -> bool:
        if self.active_cutscene is None:
            return False
        if not self.active_cutscene_narration_complete():
            self.reveal_active_cutscene_narration()
            return True
        choices = self.active_cutscene_choices()
        if len(choices) == 1 and choices[0].next_node and not choices[0].action:
            return self.set_active_cutscene_node(choices[0].next_node)
        if not choices:
            self.close_active_cutscene()
            return True
        return False

    def choose_active_cutscene_option(self, choice_index: int) -> bool:
        if (
            self.active_cutscene is None
            or getattr(self, "active_mini_game", None) is not None
        ):
            return False
        choices = self.active_cutscene_choices()
        if not (0 <= choice_index < len(choices)):
            return False
        choice = choices[choice_index]
        if choice.action == "choose_story_relic_path":
            return self.choose_story_relic_path(choice.source_index)
        if choice.action == "choose_gate_verb":
            return self.choose_story_gate_verb(choice.choice_key)
        if choice.action == "complete_victory":
            self.close_active_cutscene()
            self.complete_story_victory()
            return True
        if choice.action == "resolve_story_choice":
            guest = self.active_cutscene_guest()
            if guest is None:
                return False
            resolved = self.resolve_story_choice(guest, choice.source_index)
            if resolved:
                self.close_active_cutscene()
            return resolved
        if choice.action in (
            "lossless_preserve",
            "lossless_release",
            "lossless_refuse",
        ):
            choice_key = choice.action.removeprefix("lossless_")
            if not self.resolve_lossless_soul_choice(choice_key):
                return False
            # Refusal ends the audience at once; the other answers move to the
            # "settled" node, whose context snapshot now reflects the choice.
            if choice_key == "refuse" or not self.set_active_cutscene_node(
                "settled"
            ):
                self.close_active_cutscene()
            return True
        if choice.action == "close":
            self.close_active_cutscene()
            return True
        if choice.next_node:
            return self.set_active_cutscene_node(choice.next_node)
        self.close_active_cutscene()
        return True

    def update_active_cutscene(self, dt: float) -> None:
        if self.active_cutscene is None:
            return
        self.active_cutscene.elapsed += dt
        self.active_cutscene.node_elapsed += dt

    def story_relic_choice_options(self) -> list[tuple[str, str, str]]:
        beat = self.current_story_beat()
        if self.story_state is None or beat is None:
            return self.default_story_relic_choice_options()
        base_seed = self.story_relic_choice_text_seed(beat)
        cache = getattr(self, "_story_relic_choice_options_cache", None)
        if not isinstance(cache, dict):
            cache = {}
            self._story_relic_choice_options_cache = cache
        cache_key = (base_seed, beat.title, beat.guest_name)
        cached = cache.get(cache_key)
        if cached is not None:
            return list(cached)

        key_salts = {"aid": 11_117, "bargain": 65_537, "defy": 104_729}
        options = tuple(
            self.story_relic_choice_option_for_key(
                key, beat, random.Random(base_seed + key_salts[key])
            )
            for key in self.story_relic_choice_key_order(beat)
        )
        if len(cache) >= 32:
            cache.clear()
        cache[cache_key] = options
        return list(options)

    def story_relic_choice_key_order(self, beat: Any) -> list[str]:
        keys = ["aid", "bargain", "defy"]
        rng = random.Random(self.story_relic_choice_text_seed(beat) ^ 0xA511E9B3)
        rng.shuffle(keys)
        if keys == ["aid", "bargain", "defy"]:
            keys = ["bargain", "defy", "aid"]
        return keys

    def default_story_relic_choice_options(self) -> list[tuple[str, str, str]]:
        return [
            (
                "aid",
                "Offer a gentle vow",
                "promise to carry the guest's burden before your own",
            ),
            (
                "bargain",
                "Whisper a hidden bargain",
                "ask the dungeon to answer in riddles, debts, and signs",
            ),
            (
                "defy",
                "Refuse the omen",
                "turn from the guest's terms and trust your own path",
            ),
        ]

    def story_relic_choice_text_seed(self, beat: Any) -> int:
        parts = [
            str(self.story_seed),
            str(self.run_number),
            str(self.current_depth),
            beat.title,
            beat.guest_name,
            beat.guest_role,
        ]
        if self.story_state is not None:
            parts.extend(
                (
                    self.story_state.title,
                    self.story_state.faction,
                    self.story_state.rival_faction,
                    self.story_state.relic_name,
                )
            )
        seed = 2_166_136_261
        for char in "|".join(parts):
            seed ^= ord(char)
            seed = (seed * 16_777_619) & 0xFFFFFFFF
        return seed

    def story_relic_choice_option_for_key(
        self, choice_key: str, beat: Any, rng: random.Random
    ) -> tuple[str, str, str]:
        choice = next(
            (candidate for candidate in beat.choices if candidate.key == choice_key),
            None,
        )
        if choice is None:
            return next(
                option
                for option in self.default_story_relic_choice_options()
                if option[0] == choice_key
            )
        guest = self.story_choice_short_name(beat.guest_name)
        role = self.safe_story_choice_text(beat.guest_role.lower(), "guest")
        relic = self.safe_story_choice_text(
            self.story_state.relic_name
            if self.story_state is not None
            else "the relic",
            "the relic",
        )
        faction = self.safe_story_choice_text(
            self.story_state.faction if self.story_state is not None else "the dungeon",
            "the dungeon",
        )
        antagonist = self.safe_story_choice_text(
            self.story_state.antagonist
            if self.story_state is not None
            else "the tyrant",
            "the tyrant",
        )
        motive = self.short_story_choice_clause(beat.guest_motive, 36)
        title = self.safe_story_choice_text(beat.title, "this omen")
        intent = self.short_story_choice_clause(choice.intent, 48)
        label_templates = {
            "aid": (
                "Keep {guest}'s vow",
                "Mercy for the {role}",
                "Answer {guest} kindly",
                "Carry {guest}'s plea",
                "Honor the {role}",
            ),
            "bargain": (
                "Name {guest}'s price",
                "Trade a sealed vow",
                "Speak in owed terms",
                "Bind {relic}'s debt",
                "Ask the {role}'s price",
            ),
            "defy": (
                "Refuse {guest}'s terms",
                "Break the old demand",
                "Challenge {antagonist}'s claim",
                "Trust your own oath",
                "Deny the {role}'s omen",
            ),
        }
        detail_templates = {
            "aid": (
                "{intent}; remember {motive}",
                "answer {guest} as {role}: {intent}",
                "set {relic} toward mercy: {intent}",
                "let {title} end in witness: {intent}",
            ),
            "bargain": (
                "{intent}; weigh it against {faction}",
                "answer {guest} with measured terms: {intent}",
                "bind {relic} to a price: {intent}",
                "let {title} become debt: {intent}",
            ),
            "defy": (
                "{intent}; keep {relic} in your own hands",
                "answer {guest} with iron restraint: {intent}",
                "set your oath against {antagonist}: {intent}",
                "let {title} break before you: {intent}",
            ),
        }
        format_values = {
            "guest": guest,
            "role": role,
            "relic": relic,
            "faction": faction,
            "antagonist": antagonist,
            "motive": motive,
            "title": title,
            "intent": intent,
        }
        label = rng.choice(label_templates[choice_key]).format(**format_values)
        detail = rng.choice(detail_templates[choice_key]).format(**format_values)
        return (
            choice_key,
            self.short_story_choice_clause(label, 34),
            self.short_story_choice_clause(detail, 92),
        )

    def story_choice_short_name(self, name: str) -> str:
        safe_name = self.safe_story_choice_text(name, "the guest")
        parts = safe_name.split()
        if len(parts) > 2:
            safe_name = " ".join(parts[:2])
        return safe_name

    def safe_story_choice_text(self, text: str, fallback: str) -> str:
        result = " ".join(str(text).replace("\n", " ").split())
        replacements = {
            "unguarded": "alone",
            "guarded": "watched",
            "guardian": "warden",
            "guidance": "counsel",
            "guiding": "veiled",
            "guide": "shape",
            "light": "sign",
            "beacon": "sign",
            "lantern": "taper",
            "trail": "trace",
        }
        for term, replacement in replacements.items():
            result = re.sub(term, replacement, result, flags=re.IGNORECASE)
        result = " ".join(result.split()).strip(" ;:,.—")
        return result or fallback

    def short_story_choice_clause(self, text: str, limit: int) -> str:
        safe = self.safe_story_choice_text(text, "the guest's plea")
        if len(safe) <= limit:
            return safe
        shortened = safe[: max(1, limit - 1)].rsplit(" ", 1)[0].strip(" ;:,.—")
        return f"{shortened}…" if shortened else safe[:limit]

    def story_relic_choice_traits(self, choice_key: str) -> tuple[bool, bool]:
        traits = {
            "aid": (True, False),
            "bargain": (True, True),
            "defy": (False, True),
        }
        return traits.get(choice_key, (True, False))

    def story_relic_choice_label(self) -> str:
        for key, label, _detail in self.story_relic_choice_options():
            if key == self.story_relic_choice_key:
                return label
        return "unbound"

    def current_story_guest_for_depth(self) -> StoryGuest | None:
        return next(
            (
                guest
                for guest in self.story_guests
                if guest.depth == self.current_depth and not guest.resolved
            ),
            None,
        )

    def current_story_relic(self) -> Item | None:
        return next((item for item in self.items if item.slot == "story_relic"), None)

    def story_relic_target_position(self) -> tuple[float, float] | None:
        relic = self.current_story_relic()
        if relic is not None:
            return relic.x, relic.y
        if not self.story_relic_collected:
            return self.story_relic_position
        return None

    def begin_story_level_intro(self) -> None:
        beat = self.current_story_beat()
        guest = self.current_story_guest_for_depth()
        self.story_relic_depth = self.current_depth
        self.story_relic_choice_key = ""
        self.story_relic_position = None
        self.story_relic_collected = False
        self.story_relic_guidance_enabled = False
        self.story_relic_guarded = False
        self.items = [item for item in self.items if item.slot != "story_relic"]
        self.story_intro_pending = beat is not None and guest is not None
        if self.story_intro_pending:
            # Every floor — including depth 1 — opens straight on the omen
            # choice. Rue's ledger greeting rides as the omen's first line on
            # depth 1 only; identity and objective live on the archetype
            # select screen and the story panel (recap ban).
            self.start_quest_cutscene("story_guest_omen", guest)
        else:
            self.close_active_cutscene()

    def story_intro_lines(self) -> list[str]:
        # Fallback overlay only (the omen cutscene is preferred); mirrors the
        # omen body, which already carries Rue's greeting on depth 1.
        if self.story_state is None:
            return []
        beat = self.current_story_beat()
        if beat is None:
            return []
        return [f"Depth {beat.depth}.", self._omen_body(beat)]

    def choose_story_relic_path(self, choice_index: int) -> bool:
        options = self.story_relic_choice_options()
        if not self.story_intro_pending or not (0 <= choice_index < len(options)):
            return False
        if (
            self.current_depth in self._STORY_MINI_GAME_DEPTHS
            and not self._story_mini_game_outcome()
        ):
            # Keep the chosen continuation opaque inside the authoritative
            # model. The relic, guard, flags, and guidance path are committed
            # only after the short result card — wins and losses both proceed.
            return self.start_mini_game(
                STORY_MINI_GAME,
                context=f"choice:{choice_index}",
                origin_player_id=getattr(self.player, "player_id", "p1"),
            )
        return self._commit_story_relic_path(choice_index)

    def _commit_story_relic_path(self, choice_index: int) -> bool:
        """Commit a validated story choice after any required page binding."""

        options = self.story_relic_choice_options()
        if not self.story_intro_pending or not (0 <= choice_index < len(options)):
            return False
        choice_key, choice_label, _detail = options[choice_index]
        guidance_enabled, guarded = self.story_relic_choice_traits(choice_key)
        guest = self.current_story_guest_for_depth()
        if guest is None:
            self.story_intro_pending = False
            return False
        relic_x, relic_y = self.story_relic_location_for_choice(choice_key, guest)
        self.items = [item for item in self.items if item.slot != "story_relic"]
        relic_name = (
            f"{guest.name}'s Echo of {self.story_state.relic_name}"
            if self.story_state is not None
            else "Guest Relic Echo"
        )
        self.items.append(
            Item(
                relic_name,
                "story_relic",
                rarity="Unique",
                x=relic_x,
                y=relic_y,
                affixes=[
                    "Story Relic",
                    choice_label,
                    "Guiding Light" if guidance_enabled else "No Guiding Light",
                    "Guarded" if guarded else "Unguarded",
                ],
                unique_effect="guides the guest's plea"
                if guidance_enabled
                else "the guest's light has gone silent",
            )
        )
        self.story_relic_depth = self.current_depth
        self.story_relic_choice_key = choice_key
        self.story_relic_position = (relic_x, relic_y)
        self.story_relic_collected = False
        self.story_relic_guidance_enabled = guidance_enabled
        self.story_relic_guarded = guarded
        if guarded:
            self.spawn_story_relic_guard(relic_x, relic_y)
        self.story_intro_pending = False
        self.close_active_cutscene()
        if self.story_state is not None:
            self.story_state.flags.append(f"{self.current_depth}:relic:{choice_key}")
            self.story_state.log.append(
                f"Depth {self.current_depth}: {choice_label} — the guest relic surfaced"
                f" {'with a guiding light' if guidance_enabled else 'without a guiding light'}"
                f" {'and a guardian' if guarded else 'and no guardian'}."
            )
            del self.story_state.log[:-12]
        self.floaters.append(
            FloatingText(
                f"{choice_label}: "
                f"{'follow the relic trail' if guidance_enabled else 'find the relic without a trail'}",
                self.player.x,
                self.player.y - 0.6,
                self.story_state.accent if self.story_state else self.theme.accent,
                ttl=1.8,
            )
        )
        self.play_sfx("shrine")
        self.save_run()
        return True

    def story_relic_location_for_choice(
        self, choice_key: str, guest: StoryGuest
    ) -> tuple[float, float]:
        quest_room = self.dungeon.special_room_for_kind("quest_room")
        if quest_room is not None and 0 <= quest_room.room_index < len(
            self.dungeon.rooms
        ):
            cx, cy = self.dungeon.rooms[quest_room.room_index].center
            return self.drop_position_near(cx + 0.5, cy + 0.5, exclude_origin=True)
        if choice_key == "aid":
            # Place the relic on an adjacent tile to the quest NPC, not on the
            # NPC's own tile, so the two sprites never stack.
            return self.drop_position_near(guest.x, guest.y, exclude_origin=True)
        if choice_key == "bargain":
            if self.secrets:
                secret = min(
                    self.secrets,
                    key=lambda candidate: math.hypot(
                        candidate.x - guest.x, candidate.y - guest.y
                    ),
                )
                secret.revealed = True
                return self.drop_position_near(secret.x, secret.y)
            side_rooms = self.dungeon.rooms[2:-1] or self.dungeon.rooms[1:]
            room = max(
                side_rooms,
                key=lambda candidate: math.hypot(
                    candidate.center[0] + 0.5 - self.player.x,
                    candidate.center[1] + 0.5 - self.player.y,
                ),
            )
            x, y = room.random_point(self.rng)
            return self.drop_position_near(x, y)
        final_room = self.dungeon.rooms[-1]
        x, y = final_room.random_point(self.rng)
        return self.drop_position_near(x, y)

    def spawn_story_relic_guard(self, relic_x: float, relic_y: float) -> None:
        offsets = (
            (1.8, 0.0),
            (-1.8, 0.0),
            (0.0, 1.8),
            (0.0, -1.8),
            (1.4, 1.4),
            (-1.4, 1.4),
            (1.4, -1.4),
            (-1.4, -1.4),
        )
        guard_x, guard_y = relic_x, relic_y
        for ox, oy in offsets:
            candidate_x, candidate_y = relic_x + ox, relic_y + oy
            if not self.dungeon.blocked_for_radius(
                candidate_x, candidate_y, radius=0.28
            ):
                guard_x, guard_y = candidate_x, candidate_y
                break
        guard = self._make_story_hunter(guard_x, guard_y, prefix="Relic Guardian")
        guard.kind = "miniboss"
        guard.name = f"Relic Guardian {guard.name.split(' ', 2)[-1]}"
        guard.elite_modifier = "Relic Guardian"
        guard.telegraph = "bound to the guest relic by the opening story choice"
        guard.max_hp = max(1, int(guard.max_hp * 1.45))
        guard.hp = guard.max_hp
        guard.damage += 3 + self.current_depth // 2
        guard.xp += 24 + self.current_depth * 2
        guard.aggro_range += 3.0
        guard.color = self.story_state.accent if self.story_state else self.theme.accent
        self.enemies.append(guard)

    def story_mechanics_summary(self) -> str:
        if self.story_state is None:
            return ""
        forces: list[str] = []
        resist = self.story_effect_value("damage_resist", 0.0, 0.35)
        if resist > 0:
            forces.append(f"Mercy ward -{int(round(resist * 100))}% damage")
        healing = self.story_effect_value("healing_echo", 0.0, 1.0)
        if healing > 0:
            forces.append(f"Echo heals {int(round(min(1.0, healing) * 100))}% on kills")
        relic = self.story_effect_value("relic_power", 0.0, 0.35)
        if relic > 0:
            forces.append(f"Relic power +{int(round(relic * 100))}% spell force")
        blood = self.story_effect_value("blood_price", 0.0, 0.35)
        if blood > 0:
            forces.append("Blood price drains HP on spells")
        damage = self.story_effect_value("damage_bonus", 0.0, 0.35)
        if damage > 0:
            forces.append(f"Defiance +{int(round(damage * 100))}% damage")
        hunters = self.story_effect_value("hunter_pressure", 0.0, 0.35)
        if hunters > 0:
            forces.append("Hunters stalk each new floor")
        pressure = self.story_effect_value("enemy_pressure", -0.35, 0.45)
        if abs(pressure) >= 0.01:
            direction = "more" if pressure > 0 else "fewer"
            forces.append(f"{direction} enemies {int(round(abs(pressure) * 100))}%")
        loot = self.story_effect_value("loot_bonus", 0.0, 0.35)
        if loot > 0:
            forces.append(f"loot +{int(round(loot * 100))}%")
        traps = self.story_effect_value("trap_bonus", 0.0, 0.28)
        if traps > 0:
            forces.append(f"traps +{int(round(traps * 100))}%")
        return " · ".join(forces[:7])

    def story_panel_lines(self) -> list[str]:
        if self.story_state is None:
            return []
        lines = [
            self.story_state.title,
            f"Goal: {self.story_state.objective}",
        ]
        beat = self.current_story_beat()
        if beat is not None:
            status = beat.resolved_choice or "awaiting choice"
            lines.append(f"Depth {beat.depth}: {beat.title} — {status}")
            lines.append(beat.summary)
            if getattr(beat, "truth", ""):
                lines.append(beat.truth)
            if beat.outcome:
                lines.append(f"Outcome: {beat.outcome}")
            else:
                lines.append(beat.dialogue)
                guest = self.nearby_story_guest()
                if guest is not None:
                    choice_details = [
                        f"{index + 1} {choice.label}: {choice.intent} ({self.story_choice_preview(choice.key)})"
                        for index, choice in enumerate(guest.choices[:3])
                    ]
                    lines.append("Choices: " + " · ".join(choice_details))
        mechanics = self.story_mechanics_summary()
        if self.story_intro_pending:
            lines.append(
                "Guest relic: choose 1-3 to bind its first location before the level begins."
            )
        elif self.story_relic_choice_key and not self.story_relic_collected:
            cues = (
                "follow the guiding light"
                if self.story_relic_guidance_enabled
                else "no guiding light; search from the choice clue"
            )
            guard = (
                "guarded by a relic guardian"
                if self.story_relic_guarded
                else "unguarded"
            )
            lines.append(
                f"Guest relic: {self.story_relic_choice_label()} — {cues}; {guard}."
            )
        elif self.story_relic_collected:
            lines.append("Guest relic: recovered; the guest's plea is clearer.")
        if mechanics:
            lines.append(f"Story forces: {mechanics}")
        elif self.story_state.log:
            lines.append(self.story_state.log[-1])
        return lines

    def resolve_unanswered_story_beat(self) -> str:
        if self.story_state is None:
            return ""
        beat_index = story_beat_index_for_depth(self.story_state, self.current_depth)
        beat = self.current_story_beat()
        if beat is None or beat_index is None or beat.resolved_choice:
            return ""
        if not record_unanswered_story_beat(self.story_state, self.current_depth):
            return ""
        for guest in self.story_guests:
            if guest.depth == self.current_depth and guest.beat_index == beat_index:
                guest.resolved = True
                guest.resolved_choice = "unanswered"
        return f"{beat.guest_name} was forsaken; hunters stir below"

    def _apply_story_theme_for_current_depth(self) -> None:
        plan = self.current_floor_plan()
        if plan is not None:
            self.apply_floor_plan_for_current_depth()
            return
        beat = self.current_story_beat()
        if beat is not None:
            self.theme = self.theme_by_name(beat.theme_name)
            self.run_music_theme = self.theme.name

    def _populate_story_guest(
        self,
        special_room: SpecialRoom | None = None,
        room: Room | None = None,
    ) -> None:
        if self.story_state is None:
            return
        beat_index = story_beat_index_for_depth(self.story_state, self.current_depth)
        if beat_index is None:
            return
        beat = self.story_state.beats[beat_index]
        if beat.resolved_choice:
            return
        if any(
            guest.depth == self.current_depth and guest.beat_index == beat_index
            for guest in self.story_guests
        ):
            return
        available_rooms = self.dungeon.rooms[1:-1] or self.dungeon.rooms[:1]
        if not available_rooms:
            return
        if room is None:
            special_room = self.dungeon.special_room_for_kind("quest_room")
            if special_room is not None and 0 <= special_room.room_index < len(
                self.dungeon.rooms
            ):
                room = self.dungeon.rooms[special_room.room_index]
        if room is not None:
            cx, cy = room.center
            x, y = cx + 0.5, cy + 0.5
        else:
            fallback_room = available_rooms[
                (self.current_depth + beat_index) % len(available_rooms)
            ]
            x, y = fallback_room.random_point(self.rng)
        if special_room is not None:
            special_room.anchor_points["guest"] = [int(x), int(y)]
            tile = [int(x), int(y)]
            if tile not in special_room.reserved_tiles:
                special_room.reserved_tiles.append(tile)
        self.story_guests.append(
            story_guest_from_beat(self.story_state, beat_index, x, y)
        )

    def nearby_story_guest(self) -> StoryGuest | None:
        nearby = [
            guest
            for guest in self.story_guests
            if not guest.resolved
            and guest.depth == self.current_depth
            and math.hypot(guest.x - self.player.x, guest.y - self.player.y) < 1.25
        ]
        return min(
            nearby,
            key=lambda guest: math.hypot(
                guest.x - self.player.x, guest.y - self.player.y
            ),
            default=None,
        )

    def mark_story_guest_met(self, guest: StoryGuest) -> None:
        if not guest.met:
            guest.met = True
            self.run_stats.guests_met += 1

    def talk_to_story_guest(self, guest: StoryGuest) -> None:
        self.mark_story_guest_met(guest)
        if self.start_quest_cutscene("story_guest_dialogue", guest):
            return
        self.floaters.append(
            FloatingText(
                f"{guest.role}: choose 1-3",
                guest.x,
                guest.y - 0.55,
                guest.color,
                ttl=1.4,
            )
        )
        self.floaters.append(
            FloatingText(
                guest.motive[:42],
                guest.x,
                guest.y - 0.2,
                (225, 215, 190),
                ttl=1.4,
            )
        )

    # --- garden frog dance ---------------------------------------------

    def garden_frog_special_room(
        self, frog: IdleNpc
    ) -> SpecialRoom | None:
        """Return the Garden currently hosting ``frog``, if any."""

        dungeon = getattr(self, "dungeon", None)
        if dungeon is None or getattr(frog, "kind", "") != "garden_frog":
            return None
        special = dungeon.special_room_at_point(frog.x, frog.y)
        if special is None or special.kind != "garden":
            return None
        return special

    def nearby_garden_frog(self) -> IdleNpc | None:
        """Closest dancing frog who can open an unplayed Garden interlude."""

        dungeon = getattr(self, "dungeon", None)
        player = getattr(self, "player", None)
        if dungeon is None or player is None:
            return None
        nearby: list[IdleNpc] = []
        for frog in getattr(self, "idle_npcs", ()):
            if (
                frog.kind != "garden_frog"
                or not frog.alive
                or math.hypot(frog.x - player.x, frog.y - player.y)
                >= self.GARDEN_FROG_TALK_RANGE
            ):
                continue
            special = self.garden_frog_special_room(frog)
            if (
                special is None
                or special.state.get(self._GARDEN_MINI_GAME_STATE_KEY)
            ):
                continue
            line_of_sight = getattr(dungeon, "line_of_sight", None)
            if callable(line_of_sight) and not line_of_sight(
                player.x,
                player.y,
                frog.x,
                frog.y,
            ):
                continue
            nearby.append(frog)
        return min(
            nearby,
            key=lambda frog: math.hypot(
                frog.x - player.x,
                frog.y - player.y,
            ),
            default=None,
        )

    @staticmethod
    def garden_frog_hint_detail(frog: IdleNpc) -> str:
        return f"{frog.role} · wake the moonbloom together."

    def talk_to_garden_frog(self, frog: IdleNpc | None = None) -> bool:
        """Start the Garden interlude by hailing either resident frog."""

        frog = frog or self.nearby_garden_frog()
        player = getattr(self, "player", None)
        dungeon = getattr(self, "dungeon", None)
        if (
            frog is None
            or player is None
            or dungeon is None
            or not frog.alive
            or not any(
                candidate is frog
                for candidate in getattr(self, "idle_npcs", ())
            )
            or math.hypot(frog.x - player.x, frog.y - player.y)
            >= self.GARDEN_FROG_TALK_RANGE
        ):
            return False
        special = self.garden_frog_special_room(frog)
        if (
            special is None
            or special.state.get(self._GARDEN_MINI_GAME_STATE_KEY)
        ):
            return False
        line_of_sight = getattr(dungeon, "line_of_sight", None)
        if callable(line_of_sight) and not line_of_sight(
            player.x,
            player.y,
            frog.x,
            frog.y,
        ):
            return False
        return self.start_mini_game(
            GARDEN_MINI_GAME,
            context=f"room:{special.room_index}",
            origin_player_id=getattr(player, "player_id", "p1"),
        )

    # --- lossless soul audience -----------------------------------------
    # The keeper of the Hall of Unlost Echoes offers one reflection per hall.
    # Her outcome lives on the hosting ``SpecialRoom.state`` (serialized with
    # the dungeon), while the lasting mark goes to the story flags/effects.
    _LOSSLESS_SOUL_CHOICE_EFFECTS = {
        "preserve": (
            "healing_echo",
            0.05,
            "The Lossless Soul preserves your memory whole.",
        ),
        "release": (
            "enemy_pressure",
            -0.04,
            "The Lossless Soul lets your memory rest lightly.",
        ),
        "refuse": (
            "",
            0.0,
            "You refuse the mirror; your history stays your own.",
        ),
    }

    def _lossless_soul_room_at_player(self):
        dungeon = getattr(self, "dungeon", None)
        player = getattr(self, "player", None)
        if dungeon is None or player is None:
            return None
        special = dungeon.special_room_at_point(player.x, player.y)
        if special is not None and special.kind == "lossless_soul":
            return special
        # A remote descender may initiate the host-owned audience. Once the
        # acting_as_player context exits, choices still belong to that hall.
        active = getattr(self, "active_cutscene", None)
        if active is not None and active.asset_id == "lossless_soul_reflection":
            return dungeon.special_room_for_kind("lossless_soul")
        mini_game = getattr(self, "active_mini_game", None)
        if isinstance(mini_game, MiniGameState) and mini_game.kind == SOUL_MINI_GAME:
            return self._mini_game_special_room(mini_game, "lossless_soul")
        return None

    def nearby_lossless_soul(self) -> IdleNpc | None:
        player = getattr(self, "player", None)
        if player is None:
            return None
        nearby = [
            npc
            for npc in getattr(self, "idle_npcs", [])
            if npc.kind == "lossless_soul"
            and math.hypot(npc.x - player.x, npc.y - player.y) < 1.25
        ]
        return min(
            nearby,
            key=lambda npc: math.hypot(npc.x - player.x, npc.y - player.y),
            default=None,
        )

    def lossless_soul_hint_detail(self, npc: IdleNpc) -> str:
        special = self.lossless_soul_special_room(npc)
        if special is not None and special.state.get("soul_choice"):
            return "The hall already keeps your answer · hear it again."
        if special is not None and not special.state.get(
            self._SOUL_MINI_GAME_STATE_KEY
        ):
            return "Mirror the unlost seals together · then choose what she keeps."
        return "She keeps every memory whole · speak of what you carry."

    def talk_to_lossless_soul(self, npc: IdleNpc) -> None:
        special = self.lossless_soul_special_room(npc)
        if special is not None and not special.state.get("soul_met"):
            special.state["soul_met"] = True
        if not self.start_quest_cutscene("lossless_soul_reflection"):
            return
        if special is not None and special.state.get("soul_choice"):
            self.set_active_cutscene_node("settled")
            return
        if special is not None and not special.state.get(
            self._SOUL_MINI_GAME_STATE_KEY
        ):
            self.start_mini_game(
                SOUL_MINI_GAME,
                context=f"room:{special.room_index}",
                origin_player_id=getattr(self.player, "player_id", "p1"),
            )

    def resolve_lossless_soul_choice(self, choice_key: str) -> bool:
        entry = self._LOSSLESS_SOUL_CHOICE_EFFECTS.get(choice_key)
        if entry is None:
            return False
        effect_key, amount, log_line = entry
        special = self._lossless_soul_room_at_player()
        if special is not None and not special.state.get(
            self._SOUL_MINI_GAME_STATE_KEY
        ):
            # Covers a pre-mini-game save restored directly into the reflection
            # node: the mirror still happens before its authored choices.
            self.start_mini_game(
                SOUL_MINI_GAME,
                context=f"room:{special.room_index}",
                origin_player_id=getattr(self.player, "player_id", "p1"),
            )
            return False
        if special is not None:
            special.state["soul_choice"] = choice_key
            # 4.8.10: once her reflection is answered the keeper takes up her
            # ward-bolts for the rest of the run. Aggression derives from
            # ``soul_choice`` (re-derived on load), so no new story state.
            for npc in self.idle_npcs:
                if (
                    npc.kind == "lossless_soul"
                    and self.lossless_soul_special_room(npc) is special
                ):
                    self.make_npc_combat_ally(
                        npc, greeter_id=self.player.player_id
                    )
                    break
        story = self.story_state
        if story is not None:
            story.flags.append(f"{self.current_depth}:soul:{choice_key}")
            if effect_key:
                story.effects[effect_key] = (
                    story.effects.get(effect_key, 0.0) + amount
                )
            story.log.append(log_line)
            del story.log[:-12]
        # Act III: trusting the keeper reveals who she is. Refusal never does.
        if choice_key in ("preserve", "release") and self.current_depth >= 7:
            self.learn_story_name(
                "liss",
                "Her name is Liss Voss. The hall never lost it.",
                "Liss Voss — the hall never lost her name.",
            )
        keeper = self.nearby_lossless_soul()
        if keeper is not None:
            self.add_impact(
                keeper.x,
                keeper.y,
                keeper.color,
                ttl=0.58,
                radius=0.7,
                kind="burst",
            )
            self.floaters.append(
                FloatingText(
                    log_line,
                    keeper.x,
                    keeper.y - 0.65,
                    keeper.color,
                    ttl=1.5,
                )
            )
        self.play_sfx("shrine")
        self.save_run()
        return True

    def resolve_story_choice(self, guest: StoryGuest, choice_index: int) -> bool:
        if guest.resolved or not (0 <= choice_index < len(guest.choices)):
            return False
        choice = guest.choices[choice_index]
        self.mark_story_guest_met(guest)
        guest.resolved = True
        guest.resolved_choice = choice.key
        # 4.8.10: a guest whose dialogue resolved fights beside the party.
        # Aggression derives from ``resolved`` (re-derived on load).
        self.make_npc_combat_ally(guest, greeter_id=self.player.player_id)
        if self.story_state is not None:
            record_story_choice(self.story_state, guest.depth, choice)
        self._record_story_choice_milestones(guest, choice)
        self.run_stats.story_choices += 1
        self._apply_story_choice_reward(guest, choice.key)
        self.floaters.append(
            FloatingText(
                f"{choice.label}: story changed",
                guest.x,
                guest.y - 0.65,
                guest.color,
                ttl=1.5,
            )
        )
        self.add_impact(
            guest.x, guest.y, guest.color, ttl=0.58, radius=0.7, kind="burst"
        )
        if (
            self.active_cutscene is not None
            and self.active_cutscene.guest_depth == guest.depth
            and self.active_cutscene.guest_beat_index == guest.beat_index
        ):
            self.close_active_cutscene()
        self.play_sfx("shrine")
        self.save_run()
        return True

    def _record_story_choice_milestones(self, guest: StoryGuest, choice) -> None:
        """Fixed-depth story consequences layered on the ordinary verb resolve.

        Depth 5: the archetype's secret surfaces (recap ban means it never
        printed at run start — the reveal is earned). Depth 8: refusing the
        Toll-Keeper's offer with the right verb spends his true name into the
        run. Depth 9: the tether crisis outcome is flagged for the ending.
        """
        story = self.story_state
        if story is None:
            return
        archetype = getattr(self.player, "class_name", self.selected_archetype.name)
        if guest.depth == 5:
            arc = STORY_ARCS.get(archetype)
            if arc is not None:
                story.log.append(f"Remembered: {arc.secret}")
                del story.log[:-12]
        if guest.depth == 8 and (
            choice.key == "defy"
            or (choice.key == "aid" and archetype == "Acolyte")
        ):
            self.learn_story_name(
                "sorn",
                "His pride cracks. Sorn Voss — the name, spent and spoken.",
                "Sorn Voss. The name costs a memory.",
            )
        if guest.depth == 9:
            story.flags.append(f"crisis:{choice.key}")

    def learn_story_name(
        self, name_key: str, log_line: str, floater_text: str
    ) -> None:
        """Learn a true name; names have weight, so one memory pays for it.

        The cost is visible: an older story-log line blanks to "———". The
        name flag feeds the Tyrant fight and the ending.
        """
        story = self.story_state
        if story is None or f"name:{name_key}" in story.flags:
            return
        story.flags.append(f"name:{name_key}")
        for index, entry in enumerate(story.log[:-1]):
            if entry and entry != "———":
                story.log[index] = "———"
                break
        story.log.append(log_line)
        del story.log[:-12]
        self.floaters.append(
            FloatingText(
                floater_text,
                self.player.x,
                self.player.y - 0.7,
                story.accent,
                ttl=2.0,
            )
        )

    def spawn_gate_gathering(self) -> None:
        """4.9.3: the depth-10 antechamber roll-call.

        Everyone the player Aided on the way down stands near the entry as a
        silent witness (idle NPCs reusing the story-guest art — the generic
        kind falls back to it). The Forsaken road gets an empty room and one
        line instead.
        """
        story = self.story_state
        if story is None or self.current_depth < 10:
            return
        aided = [
            beat
            for beat in story.beats
            if beat.depth < 10 and beat.resolved_choice == "aid"
        ]
        room = self.dungeon.rooms[0] if self.dungeon.rooms else None
        if room is None:
            return
        cx, cy = room.center
        cx, cy = cx + 0.5, cy + 0.5
        offsets = (
            (-1.7, -1.1),
            (1.7, -1.1),
            (-2.3, 0.4),
            (2.3, 0.4),
            (-1.2, 1.5),
            (1.2, 1.5),
            (0.0, -2.0),
            (0.0, 2.1),
            (-2.6, -0.6),
        )
        spawned = 0
        for beat, (ox, oy) in zip(aided, offsets):
            x, y = self.drop_position_near(cx + ox, cy + oy)
            self.idle_npcs.append(
                IdleNpc(
                    x,
                    y,
                    kind="gathering",
                    name=beat.guest_name,
                    role=beat.guest_role,
                    color=story.accent,
                )
            )
            spawned += 1
        if spawned:
            self.floaters.append(
                FloatingText(
                    "The aided stand at the door.",
                    self.player.x,
                    self.player.y - 1.1,
                    story.accent,
                    ttl=2.4,
                )
            )
        elif self.current_story_road() == "forsaken":
            self.floaters.append(
                FloatingText(
                    "You wanted to walk alone. The room agrees.",
                    self.player.x,
                    self.player.y - 1.1,
                    (170, 162, 178),
                    ttl=2.4,
                )
            )

    def story_victory_line(self) -> str:
        """The victory screen's one-line ending stamp."""
        verb = str(getattr(self, "story_gate_verb", ""))
        archetype = getattr(self.player, "class_name", self.selected_archetype.name)
        ending = STORY_ENDINGS.get(archetype, {}).get(verb)
        if ending is None:
            return ""
        return f"{ending.title} — the Ledger finally holds a finished entry."

    # --- the Tenth Bell: gate verb and epilogue (4.9.3) -------------------

    def begin_story_epilogue(self) -> bool:
        """Open the Gate's last question at the depth-10 stairs.

        Returns False when the epilogue cannot run (no story, no asset, or
        already answered) so the caller falls through to plain victory.
        """
        if self.story_state is None:
            return False
        if getattr(self, "story_gate_verb", ""):
            return False
        if "story_epilogue" not in self.quest_cutscenes:
            return False
        return self.start_quest_cutscene("story_epilogue")

    def choose_story_gate_verb(self, verb: str) -> bool:
        if verb not in ("aid", "bargain", "defy"):
            return False
        self.story_gate_verb = verb
        story = self.story_state
        archetype = getattr(self.player, "class_name", self.selected_archetype.name)
        ending = STORY_ENDINGS.get(archetype, {}).get(verb)
        if story is not None:
            story.flags.append(f"gate:{verb}")
            if ending is not None:
                story.log.append(f"The Tenth Bell: {ending.title}.")
                del story.log[:-12]
        self.play_sfx("shrine")
        return self.set_active_cutscene_node("ending")

    def _apply_story_choice_reward(self, guest: StoryGuest, choice_key: str) -> None:
        if choice_key == "aid":
            self.player.hp = min(
                self.player.max_hp, self.player.hp + max(16, self.player.max_hp // 5)
            )
            self.player.mana = min(
                self.player.max_mana,
                self.player.mana + max(10, self.player.max_mana // 4),
            )
            self.player.stamina = self.player.max_stamina
            revealed = 0
            for secret in sorted(
                self.secrets,
                key=lambda secret: math.hypot(secret.x - guest.x, secret.y - guest.y),
            ):
                if secret.opened or secret.revealed:
                    continue
                if math.hypot(secret.x - guest.x, secret.y - guest.y) > 7.0:
                    continue
                secret.revealed = True
                revealed += 1
                if revealed >= 2:
                    break
            if revealed == 0:
                cache_x, cache_y = self.drop_position_near(guest.x, guest.y)
                self.secrets.append(
                    SecretCache(cache_x, cache_y, "Mercy-Sealed Cache", revealed=True)
                )
            self.shrines.append(Shrine(guest.x, guest.y, "Mending Shrine"))
        elif choice_key == "bargain":
            blood_price = self.story_effect_value("blood_price", 0.0, 0.35)
            cost = max(
                6,
                min(22, int(round(self.player.max_hp * (0.08 + blood_price * 0.45)))),
            )
            previous_hp = self.player.hp
            self.player.hp = max(1, self.player.hp - cost)
            self.run_stats.damage_taken += previous_hp - self.player.hp
            item = self._make_equipment(
                self.rng.choice(("weapon", "armor")),
                "Rare",
                guest.x,
                guest.y,
            )
            self._empower_story_relic_item(item, guaranteed=True)
            self._clamp_rolled_equipment(item)
            self.items.append(item)
        elif choice_key == "defy":
            leveled = self.player.gain_xp(24 + self.current_depth * 3)
            if leveled:
                self.grant_memory_token(reason="story defiance")
            spawn_x, spawn_y = self.drop_position_near(guest.x, guest.y)
            self.enemies.append(
                self._make_story_hunter(spawn_x, spawn_y, prefix="Story-Marked")
            )
