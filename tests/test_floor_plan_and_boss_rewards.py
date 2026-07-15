from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


from arch_rogue.constants import DUNGEON_DEPTH
from arch_rogue.content import ARCHETYPES, BOSS_DEFINITIONS, ENCOUNTER_TEMPLATES
from arch_rogue.dungeon import Dungeon
from arch_rogue.game import Game


class RunStructureBossesReplayability23Tests(unittest.TestCase):
    def tearDown(self) -> None:
        pass

    def make_game(self, tmpdir: str, seed: int = 2303) -> Game:
        game = Game(
            screen_size=(820, 540),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.meta_progress = game.default_meta_progress()
        game.run_history = []
        game.rng.seed(seed)
        game.restart(ARCHETYPES[0])
        if game.story_intro_pending:
            self.assertTrue(game.choose_story_relic_path(0))
        game.active_cutscene = None
        return game

    def test_floor_plan_paces_depths_and_survives_save_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                self.assertEqual(len(game.floor_plan), DUNGEON_DEPTH)
                self.assertEqual(
                    [plan.depth for plan in game.floor_plan],
                    list(range(1, DUNGEON_DEPTH + 1)),
                )

                boss_depths = {plan.depth for plan in game.floor_plan if plan.boss_key}
                self.assertEqual(boss_depths, {3, 6, 9, DUNGEON_DEPTH})
                self.assertEqual(game.floor_plan[-1].boss_key, "gate_tyrant")

                encounter_keys = {template.key for template in ENCOUNTER_TEMPLATES}
                boss_keys = {boss.key for boss in BOSS_DEFINITIONS}
                for plan in game.floor_plan:
                    self.assertIn(plan.encounter_key, encounter_keys)
                    self.assertGreaterEqual(plan.threat_level, 1)
                    self.assertIn("Threat", plan.preview)
                    if plan.boss_key:
                        self.assertIn(plan.boss_key, boss_keys)
                        self.assertIn("boss sign", plan.preview)

                summary = game.floor_plan_summary(game.current_floor_plan())
                self.assertIn("Threat", summary)
                self.assertIn("reward", summary)

                stair_x, stair_y = game.dungeon.stairs
                game.player.x = stair_x + 0.5
                game.player.y = stair_y + 0.5
                hint = game.current_interaction_hint()
                self.assertIsNotNone(hint)
                assert hint is not None
                self.assertIn("Next:", hint[2])

                # --- floor plan survives run save roundtrip ---
                game.current_depth = 6
                game.apply_floor_plan_for_current_depth()
                saved_plan = [game.floor_plan_to_dict(plan) for plan in game.floor_plan]
                self.assertTrue(game.save_run())

                loaded = Game(
                    screen_size=(820, 540),
                    headless=True,
                    save_path=Path(tmpdir) / "run.json",
                )
                loaded.options_path = Path(tmpdir) / "options.json"
                loaded.meta_progress = loaded.default_meta_progress()
                loaded.run_history = []
                self.assertTrue(loaded.load_run(), loaded.last_load_error)
                try:
                    loaded_plan = [
                        loaded.floor_plan_to_dict(plan) for plan in loaded.floor_plan
                    ]
                    self.assertEqual(loaded_plan, saved_plan)
                    self.assertEqual(loaded.current_depth, 6)
                    loaded_current_plan = loaded.current_floor_plan()
                    self.assertIsNotNone(loaded_current_plan)
                    assert loaded_current_plan is not None
                    self.assertEqual(loaded.theme.name, loaded_current_plan.theme_name)
                    self.assertTrue(loaded.floor_plan_summary())
                finally:
                    pass
            finally:
                pass

    def test_floor_bosses_drop_notable_rewards_and_record_mastery(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, seed=2323)
            try:
                game.current_depth = 3
                game.apply_floor_plan_for_current_depth()
                current_plan = game.current_floor_plan()
                self.assertIsNotNone(current_plan)
                assert current_plan is not None
                self.assertTrue(current_plan.boss_key)

                game.dungeon = Dungeon(game.rng)
                game.enemies.clear()
                game.items.clear()
                game.traps.clear()
                game.shrines.clear()
                game.secrets.clear()
                game._populate_dungeon()

                floor_bosses = [
                    enemy for enemy in game.enemies if enemy.role == "floor_boss"
                ]
                self.assertEqual(len(floor_bosses), 1)
                floor_boss = floor_bosses[0]
                self.assertEqual(floor_boss.kind, "miniboss")
                self.assertIn(floor_boss, game.enemies)

                game.kill_enemy(floor_boss)
                self.assertNotIn(floor_boss, game.enemies)
                self.assertIn(floor_boss.name, game.run_stats.defeated_bosses)
                self.assertGreaterEqual(game.run_stats.minibosses_killed, 1)
                self.assertGreaterEqual(game.run_stats.challenge_rooms_cleared, 1)
                self.assertTrue(game.run_stats.notable_loot)

                game.run_stats.cause_of_death = "trap poison damage"
                game.finalize_run("death")
                self.assertEqual(game.meta_progress["best_depth"], 3)
                self.assertIn(floor_boss.name, game.meta_progress["bosses_defeated"])
                self.assertEqual(game.run_history[-1]["outcome"], "death")
                self.assertEqual(game.run_history[-1]["cause"], "trap poison damage")

            finally:
                pass


if __name__ == "__main__":
    unittest.main()
