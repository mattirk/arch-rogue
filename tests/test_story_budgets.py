"""4.9 "Story that makes some sense" — budgets and structure.

The text budgets from build/story/50-cutscene-style.md are a contract, not a
style suggestion: a cutscene choice node shows ~2 lines (~210 chars), choice
labels truncate at 34 chars and details at 92, and the mobile interaction
prompt silently drops anything past ~48. These tests walk real seeds so any
corpus or composition change that breaks a surface fails CI, plus cover the
4.9 structure: tether floors, pinned dilemmas, roads, the name economy, the
guaranteed Hall, and the Tenth Bell epilogue.
"""

from __future__ import annotations

import os
import random
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from arch_rogue.constants import DUNGEON_DEPTH
from arch_rogue.content import (
    STORY_ARCS,
    STORY_DILEMMAS,
    STORY_ENDINGS,
    STORY_GATE_CHOICES,
    STORY_GUEST_TEMPLATES,
    STORY_TETHERS,
    TYRANT_OFFERS,
)
from arch_rogue.dungeon import LOSSLESS_SOUL_ROOM_KIND, Dungeon
from arch_rogue.game import ARCHETYPES, Game
from arch_rogue.story import StoryEngine, load_quest_cutscene_library, story_road
from arch_rogue.story.quest_assets import format_asset_text

# 4.9.x: at the 22 px narration font with letter tracking (~70 chars/line)
# the narrator card guarantees four lines and usually shows five, so a
# choice node fits ~345 chars; on the smallest windows the completed
# narration tail-follows, keeping the final (reveal) sentence visible.
CHOICE_NODE_BUDGET = 345
OMEN_BODY_BUDGET = 345
CHOICE_LABEL_BUDGET = 34
CHOICE_DETAIL_BUDGET = 92
PROMPT_DETAIL_BUDGET = 48

ENGINE_SEEDS = (7, 424242, 90210, 31337, 2026)
ARCHETYPE_NAMES = tuple(arc.name for arc in ARCHETYPES)


class StoryBudgetCorpusTests(unittest.TestCase):
    """Pure-engine checks: no Game construction, every archetype x seed."""

    def test_corpus_source_strings_fit_budgets(self) -> None:
        for name, arc in STORY_ARCS.items():
            self.assertLessEqual(len(arc.wound), 90, name)
            self.assertLessEqual(len(arc.oath), 80, name)
            self.assertLessEqual(len(arc.secret), 90, name)
            self.assertEqual(len(arc.chapters), 3, name)
        for dilemma in STORY_DILEMMAS:
            self.assertLessEqual(len(dilemma.setup), 90, dilemma.title)
            # 4.9.x "more revealing": every dilemma states its truth plainly.
            self.assertTrue(dilemma.truth, dilemma.title)
            self.assertLessEqual(len(dilemma.truth), 110, dilemma.title)
            for clause in (dilemma.aid, dilemma.bargain, dilemma.defy):
                self.assertLessEqual(len(clause), 40, dilemma.title)
            for outcome in (
                dilemma.aid_outcome,
                dilemma.bargain_outcome,
                dilemma.defy_outcome,
            ):
                self.assertLessEqual(len(outcome), 70, dilemma.title)
        for template in STORY_GUEST_TEMPLATES:
            self.assertEqual(
                len(template.speeches), len(template.motives), template.role
            )
            for speech in template.speeches:
                self.assertLessEqual(len(speech), 160, template.role)
        for tether in STORY_TETHERS.values():
            for beat in (tether.meet, tether.reveal, tether.crisis):
                self.assertLessEqual(len(beat.speech), 180, tether.name)
        for archetype, offer in TYRANT_OFFERS.items():
            self.assertLessEqual(len(offer), 180, archetype)
        for key, label, detail in STORY_GATE_CHOICES:
            self.assertIn(key, ("aid", "bargain", "defy"))
            self.assertLessEqual(len(label), CHOICE_LABEL_BUDGET)
            self.assertLessEqual(len(detail), CHOICE_DETAIL_BUDGET)

    def test_engine_composition_fits_budgets_across_seeds(self) -> None:
        for seed in ENGINE_SEEDS:
            for archetype in ARCHETYPE_NAMES:
                story = StoryEngine.generate(
                    seed, archetype, 1, "Crypt of Ash", "Blood Moon"
                )
                self.assertLessEqual(len(story.player_backstory), 200)
                self.assertLessEqual(len(story.objective), 110)
                for beat in story.beats:
                    context = f"{archetype}/{seed}/D{beat.depth}"
                    self.assertLessEqual(len(beat.summary), 220, context)
                    self.assertLessEqual(len(beat.truth), 110, context)
                    self.assertLessEqual(len(beat.dialogue), 180, context)
                    for choice in beat.choices:
                        self.assertLessEqual(len(choice.intent), 40, context)
                        self.assertLessEqual(len(choice.outcome), 70, context)

    def test_tether_floors_and_pinned_dilemmas(self) -> None:
        for seed in ENGINE_SEEDS:
            for archetype in ARCHETYPE_NAMES:
                tether = STORY_TETHERS[archetype]
                story = StoryEngine.generate(
                    seed, archetype, 1, "Crypt of Ash", "Blood Moon"
                )
                beats = {beat.depth: beat for beat in story.beats}
                for depth in (1, 5, 9):
                    self.assertEqual(beats[depth].guest_name, tether.name)
                    self.assertEqual(beats[depth].guest_role, tether.role)
                self.assertEqual(beats[5].title, "The Door That Remembers")
                self.assertEqual(beats[8].title, "The Gate's Confession")
                self.assertEqual(beats[9].title, "The Last Guest's Mask")
                # Depth 8: the Toll-Keeper borrows the guest's mouth.
                self.assertEqual(beats[8].dialogue, TYRANT_OFFERS[archetype])
                # Depth 9 carries the authored crisis verbs.
                crisis = tether.crisis_choices
                for choice in beats[9].choices:
                    self.assertEqual(
                        choice.intent, crisis[choice.key].intent
                    )
                # The player backstory never leaks the secret before depth 5.
                self.assertNotIn(
                    STORY_ARCS[archetype].secret, story.player_backstory
                )

    def test_story_road_derivation(self) -> None:
        story = StoryEngine.generate(7, "Warden", 1, "Crypt of Ash", "")
        self.assertEqual(story_road(story, 1), "unwritten")
        for beat in story.beats[:3]:
            beat.resolved_choice = "aid"
        self.assertEqual(story_road(story, 4), "witness")
        for beat in story.beats[:3]:
            beat.resolved_choice = "defy"
        self.assertEqual(story_road(story, 4), "defiant")
        for beat in story.beats[:3]:
            beat.resolved_choice = "unanswered"
        self.assertEqual(story_road(story, 4), "forsaken")
        # Before the first act break there is no road to read.
        self.assertEqual(story_road(story, 3), "unwritten")

    def test_endings_exist_for_every_archetype_and_verb(self) -> None:
        for archetype in ARCHETYPE_NAMES:
            for verb in ("aid", "bargain", "defy"):
                ending = STORY_ENDINGS[archetype][verb]
                self.assertTrue(ending.title)
                self.assertLessEqual(len(ending.body), 340, ending.title)


class StoryBudgetSurfaceTests(unittest.TestCase):
    """Headless-Game checks: the composed cutscene surfaces in situ."""

    def make_game(self, tmpdir: str, seed: int = 4911, archetype_index: int = 0) -> Game:
        game = Game(
            screen_size=(960, 540),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.rng.seed(seed)
        game.restart(ARCHETYPES[archetype_index])
        return game

    def _assert_choice_rows_fit(self, game: Game) -> None:
        for choice in game.active_cutscene_choices():
            self.assertLessEqual(len(choice.label), CHOICE_LABEL_BUDGET, choice.label)
            self.assertLessEqual(len(choice.detail), CHOICE_DETAIL_BUDGET, choice.detail)

    def test_cutscene_choice_nodes_fit_the_two_line_window(self) -> None:
        library = load_quest_cutscene_library()
        for archetype_index in range(len(ARCHETYPES)):
            with tempfile.TemporaryDirectory() as tmpdir:
                game = self.make_game(
                    tmpdir, seed=6100 + archetype_index, archetype_index=archetype_index
                )
                # Depth 1 opens straight on the relic-choice omen; Rue's
                # greeting rides inside the budgeted omen body.
                assert game.active_cutscene is not None
                self.assertEqual(
                    game.active_cutscene.asset_id, "story_guest_omen"
                )
                self.assertLessEqual(
                    len(game.active_cutscene_text()), CHOICE_NODE_BUDGET
                )
                self._assert_choice_rows_fit(game)

                # The guest-dialogue node, formatted with live context.
                context = game.quest_cutscene_context(game.story_guests[0])
                dialogue_node = library["story_guest_dialogue"].nodes["choice"]
                self.assertLessEqual(
                    len(format_asset_text(dialogue_node.text, context)),
                    CHOICE_NODE_BUDGET,
                )
                # The soul reflection node with the same context.
                soul_node = library["lossless_soul_reflection"].nodes["reflection"]
                self.assertLessEqual(
                    len(format_asset_text(soul_node.text, context)),
                    CHOICE_NODE_BUDGET,
                )
                # The epilogue's gate question.
                gate_node = library["story_epilogue"].nodes["gate"]
                self.assertLessEqual(
                    len(format_asset_text(gate_node.text, context)),
                    CHOICE_NODE_BUDGET,
                )

    def test_omen_body_fits_on_boss_and_road_floors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            assert game.story_state is not None
            for beat in game.story_state.beats[:3]:
                beat.resolved_choice = "bargain"
            for depth in range(1, DUNGEON_DEPTH + 1):
                game.current_depth = depth
                if hasattr(game, "_frame_cache"):
                    game._frame_cache = {}
                beat = game.current_story_beat()
                body = game._omen_body(beat)
                self.assertLessEqual(
                    len(body), OMEN_BODY_BUDGET, f"depth {depth}: {body}"
                )
                self.assertIn(beat.title, body)

    def test_interaction_prompt_detail_survives_mobile_clamp(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            guest = game.story_guests[0]
            self.assertLessEqual(
                len(game.story_choices_hint(guest)), PROMPT_DETAIL_BUDGET
            )

    def test_epilogue_gate_verb_plays_ending_and_completes_victory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            assert game.story_state is not None
            game.story_state.flags.append("crisis:aid")
            game.current_depth = DUNGEON_DEPTH
            game.finish_final_descent()
            assert game.active_cutscene is not None
            self.assertEqual(game.active_cutscene.asset_id, "story_epilogue")
            self.assertEqual(game.active_cutscene.node_id, "gate")
            game.reveal_active_cutscene_narration()
            choices = game.active_cutscene_choices()
            self.assertEqual(
                [choice.choice_key for choice in choices],
                ["aid", "bargain", "defy"],
            )
            self.assertTrue(game.choose_active_cutscene_option(0))
            self.assertEqual(game.active_cutscene.node_id, "ending")
            ending = STORY_ENDINGS[game.player.class_name]["aid"]
            self.assertIn(ending.title, game.active_cutscene_text())
            game.reveal_active_cutscene_narration()
            self.assertTrue(game.advance_active_cutscene())
            self.assertEqual(game.active_cutscene.node_id, "bell")
            game.reveal_active_cutscene_narration()
            self.assertTrue(game.choose_active_cutscene_option(0))
            self.assertEqual(game.state, "victory")
            self.assertIn("gate:aid", game.story_state.flags)
            self.assertTrue(game.story_victory_line())
            endings = game.meta_progress.get("story", {}).get("endings", [])
            self.assertIn(f"{game.player.class_name}:aid", endings)

    def test_true_names_cost_a_memory_and_weigh_on_the_tyrant(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            assert game.story_state is not None
            log_before = list(game.story_state.log)
            self.assertGreaterEqual(len(log_before), 2)
            plain = game._make_boss(4.5, 4.5)
            game.learn_story_name("sorn", "Test line.", "Test floater.")
            self.assertIn("name:sorn", game.story_state.flags)
            self.assertIn("———", game.story_state.log)
            self.assertTrue(game.story_name_known("sorn"))
            # Learning twice never spends a second memory.
            blanked = game.story_state.log.count("———")
            game.learn_story_name("sorn", "Test line.", "Test floater.")
            self.assertEqual(game.story_state.log.count("———"), blanked)
            # The Tyrant spawns staggered once the name is known; same game,
            # same run modifiers, so the ratio is the authored 0.88.
            boss = game._make_boss(4.5, 4.5)
            self.assertIn("Sorn Voss", boss.name)
            self.assertNotIn("Sorn Voss", plain.name)
            self.assertLess(boss.max_hp, plain.max_hp)
            self.assertAlmostEqual(
                boss.max_hp / plain.max_hp, 0.88, delta=0.01
            )

    def test_soul_hall_guaranteed_by_depth_seven(self) -> None:
        rng = random.Random(99)
        forced = Dungeon(rng, force_soul_hall=True)
        self.assertIsNotNone(
            forced.special_room_for_kind(LOSSLESS_SOUL_ROOM_KIND)
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            assert game.story_state is not None
            game.story_state.flags = [
                flag
                for flag in game.story_state.flags
                if not flag.endswith(":hall")
            ]
            game.current_depth = 7
            self.assertTrue(game._force_soul_hall_now())
            game.story_state.flags.append("3:hall")
            self.assertFalse(game._force_soul_hall_now())

    def test_gate_gathering_spawns_the_aided(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            assert game.story_state is not None
            for beat in game.story_state.beats[:4]:
                beat.resolved_choice = "aid"
            game.current_depth = DUNGEON_DEPTH
            before = len(game.idle_npcs)
            game.spawn_gate_gathering()
            gathered = [
                npc for npc in game.idle_npcs if npc.kind == "gathering"
            ]
            self.assertEqual(len(gathered), 4)
            self.assertGreater(len(game.idle_npcs), before)
            names = {npc.name for npc in gathered}
            self.assertEqual(
                names,
                {
                    beat.guest_name
                    for beat in game.story_state.beats[:4]
                },
            )


if __name__ == "__main__":
    unittest.main()
