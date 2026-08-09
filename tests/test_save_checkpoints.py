from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game
from arch_rogue.models import Enemy, Item
from arch_rogue.save_system import (
    RUN_CHECKPOINT_MAX_SECONDS,
    RUN_CHECKPOINT_QUIET_SECONDS,
    RUN_CHECKPOINT_RETRY_SECONDS,
)


def make_game(tmpdir: str) -> Game:
    game = Game(
        screen_size=(760, 520),
        headless=True,
        save_path=Path(tmpdir) / "run.json",
    )
    game.options_path = Path(tmpdir) / "options.json"
    game.rng.seed(20260727)
    game.restart(ARCHETYPES[0])
    if game.story_intro_pending:
        game.choose_story_relic_path(0)
    game.active_cutscene = None
    game.story_intro_pending = False
    game.state = "playing"
    game.reset_run_checkpoint()
    return game


def make_enemy(game: Game, *, kind: str = "melee") -> Enemy:
    return Enemy(
        "Checkpoint Target",
        kind,
        game.player.x + 0.8,
        game.player.y,
        1,
        1,
        0.0,
        0,
        1,
        1.0,
        1.0,
    )


class SaveCheckpointTests(unittest.TestCase):
    def test_routine_kill_marks_checkpoint_without_writing_in_kill_frame(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            before = game.save_path.read_bytes()
            enemy = make_enemy(game)
            game.enemies = [enemy]

            with patch.object(game, "save_run", wraps=game.save_run) as save_run:
                game.kill_enemy(enemy)
                save_run.assert_not_called()

            self.assertTrue(game._run_checkpoint_pending)
            self.assertEqual(game.save_path.read_bytes(), before)
            self.assertEqual(game.run_stats.kills, 1)

    def test_repeated_requests_debounce_but_keep_a_hard_deadline(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.elapsed = 10.0
            self.assertTrue(game.request_run_checkpoint())
            self.assertEqual(game._run_checkpoint_pending_since, 10.0)
            self.assertEqual(
                game._run_checkpoint_due_at,
                10.0 + RUN_CHECKPOINT_QUIET_SECONDS,
            )

            for elapsed in (11.0, 12.0, 13.0, 14.0, 15.0, 16.0):
                game.elapsed = elapsed
                self.assertTrue(game.request_run_checkpoint())

            hard_deadline = 10.0 + RUN_CHECKPOINT_MAX_SECONDS
            self.assertEqual(game._run_checkpoint_due_at, hard_deadline)
            with patch.object(game, "save_run", return_value=True) as save_run:
                game.elapsed = hard_deadline - 0.001
                self.assertFalse(game.service_run_checkpoint())
                save_run.assert_not_called()

                game.elapsed = hard_deadline
                self.assertTrue(game.service_run_checkpoint())
                save_run.assert_called_once_with()

    def test_force_save_flushes_pending_state_immediately_and_compactly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            enemy = make_enemy(game)
            game.enemies = [enemy]
            game.kill_enemy(enemy)
            game.player.gold = 9876
            game.player.inventory.append(Item("Mørk Token", "relic"))
            self.assertTrue(game._run_checkpoint_pending)

            self.assertTrue(game.save_run())

            self.assertFalse(game._run_checkpoint_pending)
            raw = game.save_path.read_text(encoding="utf-8")
            saved = json.loads(raw)
            self.assertEqual(saved["run_stats"]["kills"], 1)
            self.assertEqual(saved["player"]["gold"], 9876)
            self.assertEqual(saved["player"]["inventory"][-1]["name"], "Mørk Token")
            self.assertNotIn("\n", raw)
            self.assertLess(len(raw), len(json.dumps(saved, indent=2)))

    def test_update_services_a_due_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.enemies.clear()
            game.elapsed = 20.0
            self.assertTrue(game.request_run_checkpoint())
            game.elapsed = game._run_checkpoint_due_at - 0.01

            with patch.object(game, "save_run", wraps=game.save_run) as save_run:
                game.update(0.02)

            save_run.assert_called_once_with()
            self.assertFalse(game._run_checkpoint_pending)

    def test_exit_force_save_ignores_pending_checkpoint_deadline(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.elapsed = 30.0
            game.player.gold = 4321
            self.assertTrue(game.request_run_checkpoint())
            self.assertGreater(game._run_checkpoint_due_at, game.elapsed)
            game.request_exit_confirmation()

            self.assertTrue(game.save_run())

            saved = json.loads(game.save_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["player"]["gold"], 4321)
            self.assertFalse(game._run_checkpoint_pending)

    def test_boss_kill_remains_an_immediate_critical_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            boss = make_enemy(game, kind="miniboss")
            game.enemies = [boss]

            with (
                patch.object(game, "save_run", return_value=True) as save_run,
                patch.object(game, "request_run_checkpoint") as request_checkpoint,
            ):
                game.kill_enemy(boss)

            save_run.assert_called_once_with()
            request_checkpoint.assert_not_called()

    def test_failed_force_save_stays_dirty_and_retries_after_backoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            game.elapsed = 4.0

            with patch("arch_rogue.save_system.os.fsync", side_effect=OSError("full")):
                self.assertFalse(game.save_run())

            self.assertIn("full", game.last_save_error)
            self.assertTrue(game._run_checkpoint_pending)
            self.assertEqual(
                game._run_checkpoint_due_at,
                4.0 + RUN_CHECKPOINT_RETRY_SECONDS,
            )
            game.elapsed = game._run_checkpoint_due_at
            self.assertTrue(game.service_run_checkpoint())
            self.assertFalse(game._run_checkpoint_pending)

    def test_delete_save_discards_pending_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_game(tmpdir)
            self.assertTrue(game.request_run_checkpoint())

            game.delete_save()

            self.assertFalse(game._run_checkpoint_pending)
            self.assertFalse(game.save_path.exists())


if __name__ == "__main__":
    unittest.main()
