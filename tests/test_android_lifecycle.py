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

import pygame

from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game
from arch_rogue.mobile import application_storage_directory


def make_mobile_game(tmpdir: str) -> Game:
    game = Game(
        screen_size=(1280, 720),
        headless=True,
        save_path=Path(tmpdir) / "run.json",
        mobile=True,
        safe_insets=(0, 0, 0, 0),
    )
    game.options_path = Path(tmpdir) / "options.json"
    game.rng.seed(2026)
    game.restart(ARCHETYPES[2])
    if game.story_intro_pending:
        game.choose_story_relic_path(0)
    game.active_cutscene = None
    return game


class AndroidLifecycleTests(unittest.TestCase):
    def test_background_event_saves_run_and_pauses_audio(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir)
            self.assertEqual(game.state, "playing")
            game.player.gold = 4242
            with patch.object(game.audio, "suspend") as suspend:
                event = pygame.event.Event(getattr(pygame, "APP_WILLENTERBACKGROUND", -20))
                self.assertTrue(game.handle_mobile_lifecycle_event(event))
                suspend.assert_called_once_with()
            self.assertTrue(game.mobile_suspended)
            self.assertTrue(game.mobile_audio_focus_paused)
            self.assertEqual(game.state, "confirm_exit")
            self.assertTrue(game.save_path.exists())
            saved = json.loads(game.save_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["player"]["gold"], 4242)

    def test_foreground_event_clears_suspension_without_auto_resume_audio(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir)
            game.handle_mobile_lifecycle_event(
                pygame.event.Event(getattr(pygame, "APP_WILLENTERBACKGROUND", -20))
            )
            self.assertTrue(game.mobile_audio_focus_paused)
            with patch.object(game.audio, "resume") as resume:
                game.handle_mobile_lifecycle_event(
                    pygame.event.Event(getattr(pygame, "APP_DIDENTERFOREGROUND", -23))
                )
                resume.assert_not_called()
            self.assertFalse(game.mobile_suspended)
            self.assertTrue(game.mobile_audio_focus_paused)

    def test_resume_audio_focus_after_cancel(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir)
            game.handle_mobile_lifecycle_event(
                pygame.event.Event(getattr(pygame, "APP_WILLENTERBACKGROUND", -20))
            )
            game.cancel_exit_confirmation()
            self.assertFalse(game.mobile_audio_focus_paused)

    def test_terminating_event_attempts_final_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir)
            game.state = "playing"
            game.player.gold = 99
            with patch.object(game, "save_run", return_value=True) as save_run:
                game.handle_mobile_lifecycle_event(
                    pygame.event.Event(getattr(pygame, "APP_TERMINATING", -24))
                )
                save_run.assert_called_once_with()

    def test_low_memory_clears_caches_without_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir)
            game._world_layer = pygame.Surface((10, 10))
            game.handle_mobile_lifecycle_event(
                pygame.event.Event(getattr(pygame, "APP_LOWMEMORY", -25))
            )
            self.assertIsNone(game._world_layer)

    def test_suspended_update_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir)
            elapsed_before = game.elapsed
            game.handle_mobile_lifecycle_event(
                pygame.event.Event(getattr(pygame, "APP_WILLENTERBACKGROUND", -20))
            )
            game.update(0.1)
            self.assertEqual(game.elapsed, elapsed_before)


class AndroidStorageTests(unittest.TestCase):
    def test_pref_path_used_on_android(self) -> None:
        captured: dict[str, str] = {}

        def fake_pref_path(org: str, app: str) -> str:
            captured["org"] = org
            captured["app"] = app
            return "/data/data/org.archrogue/files"

        with patch.object(pygame.system, "get_pref_path", side_effect=fake_pref_path):
            path = application_storage_directory(mobile=True)
        self.assertEqual(path, Path("/data/data/org.archrogue/files"))
        self.assertEqual(captured["app"], "Arch Rogue")

    def test_home_directory_used_on_desktop(self) -> None:
        self.assertEqual(application_storage_directory(mobile=False), Path.home())


class InterruptedRunRecoveryTests(unittest.TestCase):
    def test_compatible_tmp_save_is_promoted_on_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir)
            game.player.gold = 5050
            self.assertTrue(game.save_run())
            saved = game.save_path.read_text(encoding="utf-8")
            game.save_path.unlink()
            tmp = Path(f"{game.save_path}.tmp")
            tmp.write_text(saved, encoding="utf-8")
            loaded = Game(
                screen_size=(1280, 720),
                headless=True,
                save_path=game.save_path,
                mobile=True,
            )
            loaded.options_path = game.options_path
            self.assertTrue(loaded.recover_interrupted_run_save())
            self.assertTrue(loaded.recovered_interrupted_run)
            self.assertTrue(loaded.save_path.exists())
            self.assertFalse(tmp.exists())
            loaded.rng.seed(2026)
            self.assertTrue(loaded.load_run())
            self.assertEqual(loaded.player.gold, 5050)

    def test_save_exists_recovers_interrupted_tmp(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir)
            game.player.gold = 303
            self.assertTrue(game.save_run())
            payload = game.save_path.read_text(encoding="utf-8")
            game.save_path.unlink()
            tmp = Path(f"{game.save_path}.tmp")
            tmp.write_text(payload, encoding="utf-8")
            fresh = Game(
                screen_size=(1280, 720),
                headless=True,
                save_path=game.save_path,
                mobile=True,
            )
            fresh.options_path = game.options_path
            self.assertTrue(fresh.save_exists())
            self.assertTrue(fresh.save_path.exists())
            self.assertFalse(tmp.exists())


if __name__ == "__main__":
    unittest.main()