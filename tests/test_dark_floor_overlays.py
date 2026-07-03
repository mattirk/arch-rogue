from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame

from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game


class GeneralCleanup25Tests(unittest.TestCase):
    def tearDown(self) -> None:
        pass

    def make_game(self, tmpdir: str, seed: int = 2505) -> Game:
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

    def test_dark_floor_draws_no_player_light_artifact_overlays(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                game.set_current_floor_dark(True)
                ellipse_calls = 0
                original_ellipse = pygame.draw.ellipse

                def count_ellipse(*args: Any, **kwargs: Any) -> pygame.Rect:
                    nonlocal ellipse_calls
                    ellipse_calls += 1
                    return original_ellipse(*args, **kwargs)

                pygame.draw.ellipse = cast(Any, count_ellipse)
                try:
                    game.draw_ambient_depth_overlay()
                    game.draw_darkness_overlay()
                finally:
                    pygame.draw.ellipse = original_ellipse  # type: ignore[assignment]

                self.assertEqual(ellipse_calls, 0)
                self.assertTrue(
                    game.can_see_world_position(game.player.x, game.player.y)
                )
            finally:
                pass


if __name__ == "__main__":
    unittest.main()
