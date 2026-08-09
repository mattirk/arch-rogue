from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from arch_rogue.constants import TRAP_REVEAL_RADIUS
from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game
from arch_rogue.models import Trap


class TrapRevealTests(unittest.TestCase):
    def make_game(self, tmpdir: str, seed: int = 4711) -> Game:
        game = Game(
            screen_size=(960, 540),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.rng.seed(seed)
        game.restart(ARCHETYPES[1])
        if game.story_intro_pending:
            self.assertTrue(game.choose_story_relic_path(0))
        game.active_cutscene = None
        return game

    def test_traps_spawn_hidden_and_old_save_payloads_stay_hidden(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            # Freshly populated floors never pre-reveal a trap.
            for trap in game.traps:
                self.assertFalse(trap.revealed)
                self.assertEqual(trap.reveal_progress, 0.0)
            # Pre-reveal save payloads (no revealed/reveal_progress keys) load
            # through Trap(**data) as hidden traps.
            legacy = Trap(
                **{"x": 3.0, "y": 4.0, "kind": "Rune Trap", "damage": 9, "active": True}
            )
            self.assertFalse(legacy.revealed)
            self.assertEqual(legacy.reveal_progress, 0.0)

    def test_update_reveals_only_within_radius_and_reveal_sticks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.traps.clear()
            px, py = game.player.x, game.player.y
            trap = Trap(px + TRAP_REVEAL_RADIUS + 0.4, py, "Spike Trap", 7)
            game.traps.append(trap)

            game.update_traps(0.05)
            self.assertFalse(trap.revealed)
            self.assertEqual(trap.reveal_progress, 0.0)

            # Enemies near the trap do not reveal it; only players do.
            if game.enemies:
                game.enemies[0].x = trap.x + 0.2
                game.enemies[0].y = trap.y
                game.update_traps(0.05)
                self.assertFalse(trap.revealed)

            game.player.x = trap.x - 1.0
            game.player.y = trap.y
            game.update_traps(0.05)
            self.assertTrue(trap.revealed)
            self.assertGreater(trap.reveal_progress, 0.0)

            # The materialize fade finishes quickly and clamps at 1.0.
            for _ in range(10):
                game.update_traps(0.05)
            self.assertEqual(trap.reveal_progress, 1.0)

            # Retreating does not re-hide a discovered trap.
            game.player.x = trap.x - 6.0
            game.update_traps(0.05)
            self.assertTrue(trap.revealed)
            self.assertEqual(trap.reveal_progress, 1.0)
            self.assertTrue(trap.active)

    def test_hint_warns_only_after_reveal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.traps.clear()
            px, py = game.player.x, game.player.y
            trap = Trap(px + 0.8, py, "Rune Trap", 13)
            game.traps.append(trap)

            # In range but not yet processed by update_traps: still hidden, so
            # the HUD must not announce it.
            self.assertIsNone(game.nearby_trap_warning())

            game.update_traps(0.0)
            self.assertTrue(trap.revealed)
            self.assertIs(game.nearby_trap_warning(), trap)

    def test_hidden_trap_still_fires_when_stepped_on(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.traps.clear()
            triggered_before = game.run_stats.traps_triggered
            trap = Trap(game.player.x, game.player.y, "Poison Needle", 6)
            game.traps.append(trap)

            game.update_traps(0.05)
            self.assertFalse(trap.active)
            self.assertTrue(trap.revealed)
            self.assertEqual(game.run_stats.traps_triggered, triggered_before + 1)


if __name__ == "__main__":
    unittest.main()
