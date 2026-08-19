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

"""The single achievement funnel: gameplay facts in, Steam unlocks out.

Gameplay code never calls :func:`arch_rogue.steam.unlock_achievement` directly.
It records what happened into ``meta_progress`` and then calls
:func:`evaluate_run_end` once, at the run-end choke point. Everything else --
which achievements those facts satisfy, which have already been granted, and
whether Steam is even present -- is decided here. That keeps unlock conditions
out of combat and story code, and it means the multiplayer joiner (which never
reaches ``finalize_run``) can share the exact same path.

The catalogue lives in ``assets/achievements.json`` so the ids, names and
descriptions mirrored into Steamworks App Admin sit in one reviewable file.
Triggers there are declarative; this module interprets them against a flat fact
table built from lifetime ``meta_progress`` plus the run that just ended.

Unlocks are idempotent by design. Steam ignores a repeat unlock, and the locally
granted ids are remembered in ``meta_progress["achievements"]`` so a player who
has cleared forty runs does not push forty redundant calls per run end. That
local list is a cache, never the authority: Steam owns the real state, and
deleting the options file only means the next qualifying run re-grants
everything the player has already earned.
"""

from __future__ import annotations

import json
import logging
from importlib import resources
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import steam

LOGGER = logging.getLogger(__name__)

CATALOGUE_FILENAME = "achievements.json"
CATALOGUE_VERSION = 1

# Steam stats mirrored on every run end. Cheap once the plumbing exists, and they
# are what progress-bar achievements and the store page's "players who..." stats
# read from. Maps the Steam stat API name to a fact name.
STAT_FACTS: dict[str, str] = {
    "runs_started": "runs_started",
    "clears": "clears",
    "best_depth": "best_depth",
    "lifetime_kills": "lifetime_kills",
}


class Achievement:
    """One catalogue entry: the Steam-side identity plus its trigger."""

    __slots__ = ("id", "name", "description", "hidden", "trigger")

    def __init__(
        self,
        achievement_id: str,
        name: str,
        description: str,
        hidden: bool,
        trigger: Mapping[str, Any],
    ) -> None:
        self.id = achievement_id
        self.name = name
        self.description = description
        self.hidden = hidden
        self.trigger = trigger

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Achievement {self.id}>"

    def is_satisfied_by(self, facts: Mapping[str, Any]) -> bool:
        return _matches(self.trigger, facts)


def _parse_achievement(data: Any) -> Achievement:
    if not isinstance(data, dict):
        raise ValueError("Each achievement must be an object")
    achievement_id = str(data.get("id", "")).strip()
    if not achievement_id:
        raise ValueError("Achievement is missing an id")
    trigger = data.get("trigger")
    if not isinstance(trigger, dict) or not trigger:
        raise ValueError(f"Achievement {achievement_id} is missing a trigger")
    _validate_trigger(trigger, achievement_id)
    return Achievement(
        achievement_id,
        str(data.get("name", achievement_id)),
        str(data.get("description", "")),
        bool(data.get("hidden", False)),
        trigger,
    )


def _validate_trigger(trigger: Mapping[str, Any], achievement_id: str) -> None:
    """Reject a malformed trigger at load time rather than mid-run.

    A trigger that silently never matches is worse than a crash on a developer's
    machine: it ships, and the achievement is simply unobtainable.
    """

    if "all_of" in trigger:
        clauses = trigger.get("all_of")
        if not isinstance(clauses, list) or not clauses:
            raise ValueError(f"Achievement {achievement_id}: all_of must be a list")
        for clause in clauses:
            if not isinstance(clause, dict):
                raise ValueError(f"Achievement {achievement_id}: bad all_of clause")
            _validate_trigger(clause, achievement_id)
        return
    if "counter" in trigger:
        if not any(key in trigger for key in ("at_least", "at_most")):
            raise ValueError(
                f"Achievement {achievement_id}: counter needs at_least or at_most"
            )
        return
    if "set" in trigger:
        if not any(
            key in trigger for key in ("contains", "contains_all", "size_at_least")
        ):
            raise ValueError(
                f"Achievement {achievement_id}: set needs contains, "
                "contains_all or size_at_least"
            )
        return
    raise ValueError(f"Achievement {achievement_id}: unrecognised trigger")


def _matches(trigger: Mapping[str, Any], facts: Mapping[str, Any]) -> bool:
    clauses = trigger.get("all_of")
    if isinstance(clauses, list):
        return all(
            isinstance(clause, dict) and _matches(clause, facts) for clause in clauses
        )

    counter_name = trigger.get("counter")
    if isinstance(counter_name, str):
        value = _counter(facts, counter_name)
        minimum = trigger.get("at_least")
        if minimum is not None and value < int(minimum):
            return False
        maximum = trigger.get("at_most")
        if maximum is not None and value > int(maximum):
            return False
        return True

    set_name = trigger.get("set")
    if isinstance(set_name, str):
        values = _string_set(facts, set_name)
        wanted = trigger.get("contains")
        if wanted is not None and str(wanted) not in values:
            return False
        wanted_all = trigger.get("contains_all")
        if isinstance(wanted_all, list) and not {
            str(entry) for entry in wanted_all
        }.issubset(values):
            return False
        size = trigger.get("size_at_least")
        if size is not None and len(values) < int(size):
            return False
        return True

    return False


def _counter(facts: Mapping[str, Any], name: str) -> int:
    try:
        return int(facts.get(name, 0) or 0)
    except (TypeError, ValueError):
        return 0


def _string_set(facts: Mapping[str, Any], name: str) -> set[str]:
    values = facts.get(name)
    if isinstance(values, (set, frozenset)):
        return {str(value) for value in values}
    if isinstance(values, (list, tuple)):
        return {str(value) for value in values}
    if isinstance(values, str):
        return {values}
    return set()


def load_catalogue(asset_path: str | Path | None = None) -> tuple[Achievement, ...]:
    """Parse the achievement catalogue, raising on a malformed file."""

    if asset_path is None:
        asset_text = (
            resources.files("arch_rogue.assets")
            .joinpath(CATALOGUE_FILENAME)
            .read_text(encoding="utf-8")
        )
    else:
        asset_text = Path(asset_path).read_text(encoding="utf-8")
    raw = json.loads(asset_text)
    if not isinstance(raw, dict):
        raise ValueError("Achievement catalogue root must be an object")
    if int(raw.get("version", 0)) != CATALOGUE_VERSION:
        raise ValueError("Unsupported achievement catalogue version")
    entries = raw.get("achievements")
    if not isinstance(entries, list) or not entries:
        raise ValueError("Achievement catalogue must contain an achievements list")

    achievements: list[Achievement] = []
    seen: set[str] = set()
    for entry in entries:
        achievement = _parse_achievement(entry)
        if achievement.id in seen:
            raise ValueError(f"Duplicate achievement id {achievement.id}")
        seen.add(achievement.id)
        achievements.append(achievement)
    return tuple(achievements)


_CATALOGUE: tuple[Achievement, ...] | None = None


def catalogue() -> tuple[Achievement, ...]:
    """The process-wide catalogue, parsed once.

    A broken catalogue must not take the game down with it -- achievements are a
    storefront nicety, not gameplay -- so a parse failure is logged and degrades
    to "no achievements" for the session.
    """

    global _CATALOGUE
    if _CATALOGUE is None:
        try:
            _CATALOGUE = load_catalogue()
        except (OSError, ValueError, json.JSONDecodeError) as error:
            LOGGER.warning("Could not load the achievement catalogue: %s", error)
            _CATALOGUE = ()
    return _CATALOGUE


# ------------------------------------------------------------------ fact table

# Lifetime meta_progress keys exposed to triggers as counters and as sets. Listed
# explicitly rather than mirroring the whole dict so a trigger naming a fact that
# does not exist is a test failure, not a silently-never-unlocking achievement.
META_COUNTER_FACTS = (
    "runs_started",
    "clears",
    "best_depth",
    "coop_clears",
    "lifetime_kills",
    "lifetime_secrets",
    "lifetime_shrines",
    "lifetime_wall_touches",
)
META_SET_FACTS = (
    "bosses_defeated",
    "themes_seen",
    "modifiers_seen",
    "legendary_loot_seen",
    "clears_by_difficulty",
    "clears_by_archetype",
)
RUN_COUNTER_FACTS = (
    "run.depth",
    "run.kills",
    "run.secrets_opened",
    "run.shrines_used",
    "run.elites_killed",
    "run.minibosses_killed",
    "run.challenge_rooms_cleared",
    "run.potions_used",
    "run.damage_taken",
    "run.floors_cleared",
    "run.bars_visited",
    "run.bars_toasted",
)
RUN_SET_FACTS = ("run.outcome", "run.difficulty", "run.archetype", "run.flags")
# Not read straight off meta_progress: build_facts derives these.
DERIVED_SET_FACTS = ("story_verbs",)

KNOWN_FACTS = frozenset(
    META_COUNTER_FACTS
    + META_SET_FACTS
    + RUN_COUNTER_FACTS
    + RUN_SET_FACTS
    + DERIVED_SET_FACTS
)


def build_facts(
    meta_progress: Mapping[str, Any],
    run: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Flatten lifetime progress and the finished run into one fact table.

    ``run`` is the payload assembled by the run-end caller (see
    :func:`arch_rogue.run_flow.RunFlowMixin.build_achievement_run_facts`). When
    it is absent only lifetime facts are populated, so run-scoped triggers simply
    do not fire -- which is what we want when re-evaluating outside a run end.
    """

    facts: dict[str, Any] = {}
    for key in META_COUNTER_FACTS:
        facts[key] = _coerce_int(meta_progress.get(key))
    for key in META_SET_FACTS:
        facts[key] = _string_set(meta_progress, key)

    # The Ledger stores endings as "Archetype:verb"; triggers want the verb.
    story = meta_progress.get("story")
    endings = story.get("endings") if isinstance(story, dict) else None
    verbs: set[str] = set()
    if isinstance(endings, (list, tuple)):
        for entry in endings:
            text = str(entry)
            verb = text.split(":", 1)[1] if ":" in text else text
            if verb:
                verbs.add(verb)
    facts["story_verbs"] = verbs

    for key in RUN_COUNTER_FACTS:
        facts[key] = 0
    for key in RUN_SET_FACTS:
        facts[key] = set()
    if run:
        for key in RUN_COUNTER_FACTS:
            if key in run:
                facts[key] = _coerce_int(run.get(key))
        for key in RUN_SET_FACTS:
            if key in run:
                facts[key] = _string_set(run, key)
    return facts


def _coerce_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------- the funnel


def granted(meta_progress: Mapping[str, Any]) -> set[str]:
    return _string_set(meta_progress, "achievements")


def evaluate(
    meta_progress: dict[str, Any],
    run: Mapping[str, Any] | None = None,
) -> list[str]:
    """Grant every achievement the facts now satisfy; return the newly granted.

    Safe to call as often as we like: already-granted ids are skipped, and the
    Steam facade queues unlocks to disk when Steam is unreachable, so an offline
    session still lands its achievements on the next connected launch.
    """

    entries = catalogue()
    if not entries:
        return []
    facts = build_facts(meta_progress, run)
    already = granted(meta_progress)
    newly: list[str] = []
    for achievement in entries:
        if achievement.id in already:
            continue
        try:
            satisfied = achievement.is_satisfied_by(facts)
        except (TypeError, ValueError) as error:  # pragma: no cover - defensive
            LOGGER.warning("Bad trigger on %s: %s", achievement.id, error)
            continue
        if not satisfied:
            continue
        newly.append(achievement.id)
        already.add(achievement.id)
        steam.unlock_achievement(achievement.id)
    if newly:
        meta_progress["achievements"] = sorted(already)
    _publish_stats(facts)
    return newly


def _publish_stats(facts: Mapping[str, Any]) -> None:
    for stat_name, fact_name in STAT_FACTS.items():
        steam.set_stat(stat_name, _counter(facts, fact_name))


def describe(achievement_id: str) -> Achievement | None:
    """The catalogue entry for an id, for any future in-game achievement list."""

    for achievement in catalogue():
        if achievement.id == achievement_id:
            return achievement
    return None


def trigger_fact_names(trigger: Mapping[str, Any]) -> Iterable[str]:
    """Every fact name a trigger reads, used by the catalogue consistency test."""

    clauses = trigger.get("all_of")
    if isinstance(clauses, Sequence) and not isinstance(clauses, (str, bytes)):
        for clause in clauses:
            if isinstance(clause, dict):
                yield from trigger_fact_names(clause)
        return
    for key in ("counter", "set"):
        name = trigger.get(key)
        if isinstance(name, str):
            yield name
