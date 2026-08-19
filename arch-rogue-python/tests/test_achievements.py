"""The achievement funnel: catalogue integrity, trigger evaluation, and the two
run-end paths that feed it (single-player/host via ``finalize_run``, co-op joiner
via ``mp_record_local_result``)."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from arch_rogue import achievements, steam
from arch_rogue.content import ARCHETYPES, BOSS_DEFINITIONS, DUNGEON_THEMES
from arch_rogue.content.difficulty import DIFFICULTY_PROFILES
from arch_rogue.content.progression import RUN_MODIFIERS
from arch_rogue.models import RunStats
from arch_rogue.net.mixin import NetMixin
from arch_rogue.options import OptionsMixin
from arch_rogue.run_flow import RunFlowMixin


class _Player:
    def __init__(self, class_name: str = "Warden", player_id: int = 0) -> None:
        self.class_name = class_name
        self.player_id = player_id


class _RunEndGame(OptionsMixin, NetMixin, RunFlowMixin):
    """Only the state the run-end path touches, so the funnel is testable
    without standing up a window, a dungeon and a network session."""

    def __init__(self, *, depth: int = 10, difficulty: str = "Medium") -> None:
        self.meta_progress = self.default_meta_progress()
        self.run_history: list[dict] = []
        self.run_stats = RunStats()
        self.floor_plan: list = []
        self.current_depth = depth
        self.elapsed = 42.0
        self.difficulty_name = difficulty
        # Hell is otherwise filtered out of the selectable profiles, and a Hell
        # clear is exactly what one of these tests is about.
        self.hell_unlocked = True
        self.run_modifier = RUN_MODIFIERS[0]
        self.player = _Player()
        self.players = [self.player]
        self.local_player_id = 0
        self.mp_active = False
        self.saves = 0

    def save_options(self) -> None:
        self.saves += 1


class _SteamStub:
    """Stands in for the process-wide integration; records what was unlocked."""

    def __init__(self) -> None:
        self.unlocked: list[str] = []
        self.stats: dict[str, int | float] = {}

    def unlock(self, achievement_id: str) -> bool:
        self.unlocked.append(achievement_id)
        return True

    def set_stat(self, name: str, value: int | float) -> bool:
        self.stats[name] = value
        return True


class _SteamStubMixin:
    def setUp(self) -> None:
        super().setUp()
        self.steam_stub = _SteamStub()
        steam._INTEGRATION = self.steam_stub
        self.addCleanup(setattr, steam, "_INTEGRATION", None)


class CatalogueTests(unittest.TestCase):
    """The JSON is mirrored into Steamworks App Admin by hand, so drift between
    it and the game's content is exactly what these tests exist to catch."""

    def setUp(self) -> None:
        self.entries = achievements.load_catalogue()

    def test_catalogue_is_a_sensible_size_with_unique_ids(self):
        # Valve's guidance and our own §3 target: enough to shape a completion
        # arc, few enough to author icons for.
        self.assertGreaterEqual(len(self.entries), 25)
        self.assertLessEqual(len(self.entries), 40)
        ids = [entry.id for entry in self.entries]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_achievement_has_an_id_name_and_description(self):
        for entry in self.entries:
            with self.subTest(entry.id):
                self.assertTrue(entry.id.startswith("ACH_"))
                self.assertTrue(entry.name.strip())
                self.assertTrue(entry.description.strip())

    def test_every_trigger_reads_only_facts_the_funnel_builds(self):
        """A trigger naming a fact that build_facts never populates would be an
        achievement no player could ever earn, and nothing else would notice."""

        for entry in self.entries:
            for fact in achievements.trigger_fact_names(entry.trigger):
                with self.subTest(achievement=entry.id, fact=fact):
                    self.assertIn(fact, achievements.KNOWN_FACTS)

    def test_every_fact_the_funnel_builds_is_actually_populated(self):
        facts = achievements.build_facts({}, {})
        for name in achievements.KNOWN_FACTS:
            with self.subTest(name):
                self.assertIn(name, facts)

    def test_boss_literals_match_the_boss_definitions(self):
        names = {boss.name for boss in BOSS_DEFINITIONS}
        for literal in self._literals_for("bosses_defeated"):
            with self.subTest(literal):
                self.assertIn(literal, names)

    def test_archetype_literals_match_the_archetypes(self):
        names = {archetype.name for archetype in ARCHETYPES}
        for literal in self._literals_for("clears_by_archetype"):
            with self.subTest(literal):
                self.assertIn(literal, names)

    def test_theme_literals_match_the_dungeon_themes(self):
        names = {theme.name for theme in DUNGEON_THEMES}
        for literal in self._literals_for("themes_seen"):
            with self.subTest(literal):
                self.assertIn(literal, names)

    def test_difficulty_literals_match_the_difficulty_profiles(self):
        names = {profile.name for profile in DIFFICULTY_PROFILES}
        for literal in self._literals_for("clears_by_difficulty"):
            with self.subTest(literal):
                self.assertIn(literal, names)

    def test_modifier_literals_match_the_run_modifiers(self):
        names = {modifier.name for modifier in RUN_MODIFIERS}
        for literal in self._literals_for("modifiers_seen"):
            with self.subTest(literal):
                self.assertIn(literal, names)

    def test_every_boss_and_archetype_has_its_own_achievement(self):
        boss_literals = self._literals_for("bosses_defeated")
        for boss in BOSS_DEFINITIONS:
            with self.subTest(boss.name):
                self.assertIn(boss.name, boss_literals)
        archetype_literals = self._literals_for("clears_by_archetype")
        for archetype in ARCHETYPES:
            with self.subTest(archetype.name):
                self.assertIn(archetype.name, archetype_literals)

    def _literals_for(self, set_name: str) -> set[str]:
        found: set[str] = set()
        for entry in self.entries:
            for trigger in self._flatten(entry.trigger):
                if trigger.get("set") != set_name:
                    continue
                wanted = trigger.get("contains")
                if isinstance(wanted, str):
                    found.add(wanted)
                for value in trigger.get("contains_all", []) or []:
                    found.add(str(value))
        return found

    def _flatten(self, trigger):
        clauses = trigger.get("all_of")
        if isinstance(clauses, list):
            for clause in clauses:
                yield from self._flatten(clause)
            return
        yield trigger


class CatalogueValidationTests(unittest.TestCase):
    """A malformed catalogue must fail loudly at load, never ship a dead
    achievement, and never take the game down with it at runtime."""

    def _write(self, text: str) -> Path:
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        asset = Path(tempdir.name) / "achievements.json"
        asset.write_text(text, encoding="utf-8")
        return asset

    def test_trigger_naming_no_predicate_is_rejected(self):
        asset = self._write(
            '{"version": 1, "achievements": [{"id": "ACH_X", '
            '"trigger": {"counter": "clears"}}]}'
        )
        with self.assertRaises(ValueError):
            achievements.load_catalogue(asset)

    def test_missing_trigger_is_rejected(self):
        asset = self._write('{"version": 1, "achievements": [{"id": "ACH_X"}]}')
        with self.assertRaises(ValueError):
            achievements.load_catalogue(asset)

    def test_duplicate_ids_are_rejected(self):
        entry = '{"id": "ACH_X", "trigger": {"counter": "clears", "at_least": 1}}'
        asset = self._write(f'{{"version": 1, "achievements": [{entry}, {entry}]}}')
        with self.assertRaises(ValueError):
            achievements.load_catalogue(asset)

    def test_unsupported_version_is_rejected(self):
        asset = self._write('{"version": 99, "achievements": []}')
        with self.assertRaises(ValueError):
            achievements.load_catalogue(asset)

    def test_a_broken_catalogue_degrades_to_no_achievements(self):
        with mock.patch.object(
            achievements, "load_catalogue", side_effect=ValueError("boom")
        ):
            with mock.patch.object(achievements, "_CATALOGUE", None):
                self.assertEqual(achievements.catalogue(), ())


class TriggerEvaluationTests(unittest.TestCase):
    def _achievement(self, trigger) -> achievements.Achievement:
        return achievements.Achievement("ACH_T", "T", "d", False, trigger)

    def test_counter_at_least(self):
        entry = self._achievement({"counter": "clears", "at_least": 3})
        self.assertFalse(entry.is_satisfied_by({"clears": 2}))
        self.assertTrue(entry.is_satisfied_by({"clears": 3}))

    def test_counter_at_most_treats_a_missing_fact_as_zero(self):
        entry = self._achievement({"counter": "run.potions_used", "at_most": 0})
        self.assertTrue(entry.is_satisfied_by({}))
        self.assertFalse(entry.is_satisfied_by({"run.potions_used": 1}))

    def test_set_contains(self):
        entry = self._achievement({"set": "clears_by_difficulty", "contains": "Hell"})
        self.assertFalse(entry.is_satisfied_by({"clears_by_difficulty": ["Hard"]}))
        self.assertTrue(
            entry.is_satisfied_by({"clears_by_difficulty": ["Hard", "Hell"]})
        )

    def test_set_contains_all_needs_every_entry(self):
        entry = self._achievement({"set": "bosses_defeated", "contains_all": ["a", "b"]})
        self.assertFalse(entry.is_satisfied_by({"bosses_defeated": ["a"]}))
        self.assertTrue(entry.is_satisfied_by({"bosses_defeated": ["b", "a", "c"]}))

    def test_set_size_at_least(self):
        entry = self._achievement({"set": "legendary_loot_seen", "size_at_least": 2})
        self.assertFalse(entry.is_satisfied_by({"legendary_loot_seen": ["x"]}))
        self.assertTrue(entry.is_satisfied_by({"legendary_loot_seen": ["x", "y"]}))

    def test_all_of_requires_every_clause(self):
        entry = self._achievement(
            {
                "all_of": [
                    {"set": "run.outcome", "contains": "victory"},
                    {"counter": "run.potions_used", "at_most": 0},
                ]
            }
        )
        self.assertFalse(
            entry.is_satisfied_by({"run.outcome": "victory", "run.potions_used": 2})
        )
        self.assertFalse(
            entry.is_satisfied_by({"run.outcome": "death", "run.potions_used": 0})
        )
        self.assertTrue(
            entry.is_satisfied_by({"run.outcome": "victory", "run.potions_used": 0})
        )

    def test_story_verbs_are_derived_from_the_ledger_endings(self):
        facts = achievements.build_facts(
            {"story": {"endings": ["Warden:defy", "Rogue:aid"]}}
        )
        self.assertEqual(facts["story_verbs"], {"defy", "aid"})


class EvaluateTests(_SteamStubMixin, unittest.TestCase):
    def test_newly_satisfied_achievements_unlock_and_are_remembered(self):
        progress = {"clears": 1, "best_depth": 10}
        newly = achievements.evaluate(progress)
        self.assertIn("ACH_FIRST_CLEAR", newly)
        self.assertIn("ACH_FIRST_CLEAR", self.steam_stub.unlocked)
        self.assertIn("ACH_FIRST_CLEAR", progress["achievements"])

    def test_a_second_evaluation_does_not_re_unlock(self):
        progress = {"clears": 1, "best_depth": 10}
        achievements.evaluate(progress)
        self.steam_stub.unlocked.clear()
        self.assertEqual(achievements.evaluate(progress), [])
        self.assertEqual(self.steam_stub.unlocked, [])

    def test_stats_are_published_on_every_evaluation(self):
        achievements.evaluate({"clears": 4, "best_depth": 7, "runs_started": 20})
        self.assertEqual(self.steam_stub.stats["clears"], 4)
        self.assertEqual(self.steam_stub.stats["best_depth"], 7)
        self.assertEqual(self.steam_stub.stats["runs_started"], 20)

    def test_run_scoped_triggers_stay_silent_without_a_run(self):
        newly = achievements.evaluate({})
        self.assertNotIn("ACH_DEPTH_1_DEATH", newly)


class MidRunFunnelTests(_SteamStubMixin, unittest.TestCase):
    """Milestones pop when earned, not at the eventual run end.

    Regression cover for the first hardware test with a real SDK: reaching
    depth 3 and killing the Mycelial Matron produced nothing, because
    evaluation only ran at death/victory and startup.
    """

    def test_reaching_a_depth_grants_its_achievement_immediately(self):
        game = _RunEndGame(depth=3)
        game.record_midrun_achievement_progress()
        self.assertIn("ACH_DEPTH_3", self.steam_stub.unlocked)
        self.assertEqual(game.meta_progress["best_depth"], 3)
        self.assertEqual(game.saves, 1)

    def test_a_boss_kill_grants_its_achievement_immediately(self):
        game = _RunEndGame(depth=2)
        game.run_stats.defeated_bosses = ["Mycelial Matron"]
        game.record_midrun_achievement_progress()
        self.assertIn("ACH_BOSS_MYCELIAL_MATRON", self.steam_stub.unlocked)
        self.assertIn("Mycelial Matron", game.meta_progress["bosses_defeated"])

    def test_ten_elites_grant_the_hunter_achievement_at_the_tenth_kill(self):
        game = _RunEndGame(depth=2)
        game.run_stats.elites_killed = 10
        game.record_midrun_achievement_progress()
        self.assertIn("ACH_ELITE_HUNTER", self.steam_stub.unlocked)

    def test_outcome_dependent_achievements_cannot_fire_mid_run(self):
        # Depth 1, all bars toasted, in co-op: every outcome-shaped trigger's
        # raw ingredients present, none may fire without an actual outcome.
        game = _RunEndGame(depth=1)
        game.mp_active = True
        game.run_stats.bars_visited = 1
        game.run_stats.bars_toasted = 1
        game.record_midrun_achievement_progress()
        for premature in ("ACH_DEPTH_1_DEATH", "ACH_COOP_RUN", "ACH_BAR_PILGRIM"):
            self.assertNotIn(premature, self.steam_stub.unlocked)

    def test_the_same_ingredients_do_fire_once_the_run_ends(self):
        game = _RunEndGame(depth=1)
        game.run_stats.bars_visited = 1
        game.run_stats.bars_toasted = 1
        game.record_midrun_achievement_progress()
        game.finalize_run("death")
        self.assertIn("ACH_DEPTH_1_DEATH", self.steam_stub.unlocked)
        self.assertIn("ACH_BAR_PILGRIM", self.steam_stub.unlocked)

    def test_no_change_means_no_disk_write(self):
        game = _RunEndGame(depth=3)
        game.record_midrun_achievement_progress()
        saves_after_first = game.saves
        game.record_midrun_achievement_progress()
        self.assertEqual(game.saves, saves_after_first)

    def test_run_end_does_not_regrant_what_mid_run_already_granted(self):
        game = _RunEndGame(depth=3)
        game.record_midrun_achievement_progress()
        self.steam_stub.unlocked.clear()
        game.finalize_run("death")
        self.assertNotIn("ACH_DEPTH_3", self.steam_stub.unlocked)


class WallFacerTests(_SteamStubMixin, unittest.TestCase):
    """Wall Facer counts hidden-face-wall touches across the whole ledger and
    pops at the wall on the hundredth, not at the eventual run end."""

    def test_the_hundredth_touch_grants_wall_facer_at_the_wall(self):
        game = _RunEndGame(depth=2)
        for _ in range(99):
            game.record_wall_face_touch()
        self.assertNotIn("ACH_WALLFACER", self.steam_stub.unlocked)
        game.record_wall_face_touch()
        self.assertIn("ACH_WALLFACER", self.steam_stub.unlocked)
        self.assertEqual(game.meta_progress["lifetime_wall_touches"], 100)

    def test_every_touch_is_persisted(self):
        # Unlike the mid-run milestone fold-in, each touch changes the lifetime
        # counter, so each one must land on disk to survive a crash.
        game = _RunEndGame(depth=2)
        game.record_wall_face_touch()
        game.record_wall_face_touch()
        self.assertEqual(game.saves, 2)

    def test_the_counter_survives_a_ledger_round_trip(self):
        game = _RunEndGame()
        progress = game.normalize_meta_progress({"lifetime_wall_touches": 61})
        self.assertEqual(progress["lifetime_wall_touches"], 61)


class BossNameplateTests(_SteamStubMixin, unittest.TestCase):
    """Boss achievements must key on definition names, not nameplates.

    Found on hardware: the Mycelial Matron died under her story nameplate
    ("<antagonist> Mycelial Matron"), the ledger recorded that string, and the
    achievement's exact set-membership check never matched — even after the
    run ended. The themed final boss ("Voidbound Gate Tyrant") never matched
    at all.
    """

    def test_a_story_decorated_boss_kill_grants_the_achievement(self):
        game = _RunEndGame(depth=4)
        game.run_stats.defeated_bosses = ["the Toll-Keeper Mycelial Matron"]
        game.finalize_run("death")
        self.assertIn("ACH_BOSS_MYCELIAL_MATRON", self.steam_stub.unlocked)
        self.assertIn("Mycelial Matron", game.meta_progress["bosses_defeated"])
        # The ledger holds the canonical name, not the nameplate.
        self.assertNotIn(
            "the Toll-Keeper Mycelial Matron", game.meta_progress["bosses_defeated"]
        )

    def test_the_themed_final_boss_grants_the_tyrant_achievement(self):
        game = _RunEndGame(depth=10)
        game.run_stats.defeated_bosses = ["Sorn Voss, Moon-Drowned Gate Tyrant"]
        game.finalize_run("victory")
        self.assertIn("ACH_BOSS_GATE_TYRANT", self.steam_stub.unlocked)

    def test_mid_run_fold_in_canonicalises_too(self):
        game = _RunEndGame(depth=4)
        game.run_stats.defeated_bosses = ["the Toll-Keeper Mycelial Matron"]
        game.record_midrun_achievement_progress()
        self.assertIn("ACH_BOSS_MYCELIAL_MATRON", self.steam_stub.unlocked)

    def test_a_ledger_written_before_the_fix_heals_on_load(self):
        # The hardware Deck has "the Toll-Keeper Mycelial Matron" persisted.
        # normalize_meta_progress canonicalises it, and the startup evaluation
        # then grants what the decorated entry withheld.
        game = _RunEndGame()
        progress = game.normalize_meta_progress(
            {"bosses_defeated": ["the Toll-Keeper Mycelial Matron"]}
        )
        self.assertEqual(progress["bosses_defeated"], ["Mycelial Matron"])
        newly = achievements.evaluate(progress)
        self.assertIn("ACH_BOSS_MYCELIAL_MATRON", newly)

    def test_named_minibosses_pass_through_unchanged(self):
        game = _RunEndGame(depth=4)
        game.run_stats.defeated_bosses = ["Oathbound Guardian"]
        game.finalize_run("death")
        self.assertIn("Oathbound Guardian", game.meta_progress["bosses_defeated"])


class FinalizeRunFunnelTests(_SteamStubMixin, unittest.TestCase):
    """The single-player and host path."""

    def test_a_clear_records_difficulty_and_archetype_and_unlocks(self):
        game = _RunEndGame(difficulty="Hell")
        game.player.class_name = "Ranger"
        game.finalize_run("victory")
        progress = game.meta_progress
        self.assertEqual(progress["clears"], 1)
        self.assertEqual(progress["best_depth"], 10)
        self.assertEqual(progress["clears_by_difficulty"], ["Hell"])
        self.assertEqual(progress["clears_by_archetype"], ["Ranger"])
        self.assertIn("ACH_FIRST_CLEAR", self.steam_stub.unlocked)
        self.assertIn("ACH_CLEAR_HELL", self.steam_stub.unlocked)
        self.assertIn("ACH_CLEAR_RANGER", self.steam_stub.unlocked)
        self.assertIn("ACH_DEPTH_10", self.steam_stub.unlocked)

    def test_a_death_still_records_depth_and_lifetime_totals(self):
        game = _RunEndGame(depth=4)
        game.run_stats.kills = 12
        game.run_stats.secrets_opened = 3
        game.run_stats.shrines_used = 2
        game.finalize_run("death")
        progress = game.meta_progress
        self.assertEqual(progress["clears"], 0)
        self.assertEqual(progress["best_depth"], 4)
        self.assertEqual(progress["lifetime_kills"], 12)
        self.assertEqual(progress["lifetime_secrets"], 3)
        self.assertEqual(progress["lifetime_shrines"], 2)
        self.assertEqual(progress["clears_by_difficulty"], [])
        self.assertIn("ACH_DEPTH_3", self.steam_stub.unlocked)
        self.assertNotIn("ACH_FIRST_CLEAR", self.steam_stub.unlocked)

    def test_lifetime_totals_accumulate_across_runs(self):
        game = _RunEndGame(depth=2)
        game.run_stats.kills = 5
        game.finalize_run("death")
        game.run_stats = RunStats()
        game.run_stats.kills = 7
        game.finalize_run("death")
        self.assertEqual(game.meta_progress["lifetime_kills"], 12)

    def test_dying_on_depth_one_is_its_own_achievement(self):
        game = _RunEndGame(depth=1)
        game.finalize_run("death")
        self.assertIn("ACH_DEPTH_1_DEATH", self.steam_stub.unlocked)

    def test_a_clear_with_potions_does_not_earn_the_dry_clear(self):
        game = _RunEndGame()
        game.run_stats.potions_used = 1
        game.finalize_run("victory")
        self.assertNotIn("ACH_DRY_CLEAR", self.steam_stub.unlocked)

    def test_a_clear_without_potions_earns_the_dry_clear(self):
        game = _RunEndGame()
        game.finalize_run("victory")
        self.assertIn("ACH_DRY_CLEAR", self.steam_stub.unlocked)

    def test_toasting_every_bar_the_run_rolled_earns_the_pilgrimage(self):
        game = _RunEndGame()
        game.run_stats.bars_visited = 3
        game.run_stats.bars_toasted = 3
        game.finalize_run("death")
        self.assertIn("ACH_BAR_PILGRIM", self.steam_stub.unlocked)

    def test_missing_one_bar_does_not_earn_the_pilgrimage(self):
        game = _RunEndGame()
        game.run_stats.bars_visited = 3
        game.run_stats.bars_toasted = 2
        game.finalize_run("death")
        self.assertNotIn("ACH_BAR_PILGRIM", self.steam_stub.unlocked)

    def test_a_run_with_no_bars_does_not_earn_the_pilgrimage(self):
        game = _RunEndGame()
        game.finalize_run("death")
        self.assertNotIn("ACH_BAR_PILGRIM", self.steam_stub.unlocked)

    def test_defeated_bosses_reach_the_lifetime_ledger(self):
        game = _RunEndGame()
        game.run_stats.defeated_bosses = ["Ash Gallows Knight"]
        game.finalize_run("death")
        self.assertIn("Ash Gallows Knight", game.meta_progress["bosses_defeated"])
        self.assertIn("ACH_BOSS_ASH_GALLOWS", self.steam_stub.unlocked)

    def test_the_run_history_entry_is_still_written(self):
        game = _RunEndGame()
        game.finalize_run("death")
        self.assertEqual(len(game.run_history), 1)
        self.assertEqual(game.run_history[0]["outcome"], "death")

    def test_a_host_clear_in_coop_counts_as_a_coop_clear(self):
        game = _RunEndGame()
        game.mp_active = True
        game.finalize_run("victory")
        self.assertEqual(game.meta_progress["coop_clears"], 1)
        self.assertIn("ACH_COOP_CLEAR", self.steam_stub.unlocked)
        self.assertIn("ACH_COOP_RUN", self.steam_stub.unlocked)

    def test_a_solo_clear_is_not_a_coop_clear(self):
        game = _RunEndGame()
        game.finalize_run("victory")
        self.assertEqual(game.meta_progress["coop_clears"], 0)
        self.assertNotIn("ACH_COOP_CLEAR", self.steam_stub.unlocked)


class CoopJoinerFunnelTests(_SteamStubMixin, unittest.TestCase):
    """Regression cover for the pre-existing gap fixed in 4.9.21: the joining
    client never reaches finalize_run, because the host owns the run's ending,
    so before the fix a co-op clear updated nothing but the run history."""

    def _joiner(self, class_name: str = "Acolyte") -> _RunEndGame:
        game = _RunEndGame()
        game.mp_active = True
        game.player = _Player(class_name, player_id=1)
        game.players = [game.player]
        game.local_player_id = 1
        return game

    def test_a_joiner_clear_counts_toward_meta_progression(self):
        game = self._joiner()
        game.mp_record_local_result("victory")
        progress = game.meta_progress
        self.assertEqual(progress["clears"], 1)
        self.assertEqual(progress["coop_clears"], 1)
        self.assertEqual(progress["best_depth"], 10)
        self.assertEqual(progress["clears_by_archetype"], ["Acolyte"])

    def test_a_joiner_clear_unlocks_achievements(self):
        game = self._joiner("Rogue")
        game.mp_record_local_result("victory")
        self.assertIn("ACH_FIRST_CLEAR", self.steam_stub.unlocked)
        self.assertIn("ACH_COOP_CLEAR", self.steam_stub.unlocked)
        self.assertIn("ACH_CLEAR_ROGUE", self.steam_stub.unlocked)

    def test_a_joiner_death_records_depth_without_a_clear(self):
        game = self._joiner()
        game.current_depth = 6
        game.mp_record_local_result("death")
        self.assertEqual(game.meta_progress["clears"], 0)
        self.assertEqual(game.meta_progress["coop_clears"], 0)
        self.assertEqual(game.meta_progress["best_depth"], 6)
        self.assertIn("ACH_DEPTH_5", self.steam_stub.unlocked)

    def test_the_joiner_still_writes_its_multiplayer_run_history_entry(self):
        game = self._joiner()
        game.mp_record_local_result("victory")
        self.assertEqual(len(game.run_history), 1)
        self.assertTrue(game.run_history[0]["multiplayer"])


class MetaProgressSchemaTests(unittest.TestCase):
    """normalize_meta_progress has to tolerate every options file already in the
    wild, since the new keys did not exist before 4.9.21."""

    def setUp(self) -> None:
        self.options = _RunEndGame()

    def test_an_options_file_from_before_the_new_keys_is_upgraded(self):
        legacy = {"runs_started": 4, "clears": 2, "best_depth": 7}
        progress = self.options.normalize_meta_progress(legacy)
        self.assertEqual(progress["runs_started"], 4)
        self.assertEqual(progress["coop_clears"], 0)
        self.assertEqual(progress["lifetime_kills"], 0)
        self.assertEqual(progress["clears_by_difficulty"], [])
        self.assertEqual(progress["achievements"], [])

    def test_the_new_keys_survive_a_normalize_round_trip(self):
        progress = self.options.normalize_meta_progress(
            {
                "coop_clears": 3,
                "lifetime_kills": 900,
                "clears_by_archetype": ["Rogue", "Warden"],
                "achievements": ["ACH_FIRST_CLEAR"],
            }
        )
        self.assertEqual(progress["coop_clears"], 3)
        self.assertEqual(progress["lifetime_kills"], 900)
        self.assertEqual(progress["clears_by_archetype"], ["Rogue", "Warden"])
        self.assertEqual(progress["achievements"], ["ACH_FIRST_CLEAR"])

    def test_garbage_values_normalize_instead_of_raising(self):
        progress = self.options.normalize_meta_progress(
            {"coop_clears": "many", "achievements": "ACH_X", "lifetime_kills": -5}
        )
        self.assertEqual(progress["coop_clears"], 0)
        self.assertEqual(progress["achievements"], [])
        self.assertEqual(progress["lifetime_kills"], 0)

    def test_the_granted_list_is_not_truncated_at_the_catalogue_size(self):
        ids = [f"ACH_{index:03d}" for index in range(120)]
        progress = self.options.normalize_meta_progress({"achievements": ids})
        self.assertEqual(len(progress["achievements"]), 120)


if __name__ == "__main__":
    unittest.main()
