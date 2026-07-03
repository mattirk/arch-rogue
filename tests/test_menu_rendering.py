from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game


class MenuRenderingTests(unittest.TestCase):
    def tearDown(self) -> None:
        pass

    def test_core_menus_and_overlays_render(self) -> None:
        # Smoke test that every navigable menu and run-state overlay renders
        # without error: title/options/about (pre-run), archetype select (with a
        # sprite per archetype), and help/inventory/death overlays (in-run).
        with tempfile.TemporaryDirectory() as tmpdir:
            game = Game(
                screen_size=(640, 480),
                headless=True,
                save_path=Path(tmpdir) / "run.json",
            )
            game.options_path = Path(tmpdir) / "options.json"
            try:
                # --- Pre-run title-level menus ---
                self.assertEqual(game.state, "title")
                game.draw_title_menu()
                game.state = "options"
                game.audio_enabled = False
                game.draw_options_menu()
                game.state = "about"
                game.draw_about_screen()

                # --- Archetype select exposes a sprite per archetype ---
                game.state = "archetype_select"
                for archetype in ARCHETYPES:
                    self.assertIn(archetype.name, game.sprites.player_sprites)
                    sprite = game.sprites.player_sprites[archetype.name]
                    self.assertGreater(sprite.get_width(), 0)
                    self.assertGreater(sprite.get_height(), 0)
                    game.selected_archetype = archetype
                    game.draw_archetype_select()

                # --- In-run overlays render after a run begins ---
                game.rng.seed(1001)
                game.restart(ARCHETYPES[0])
                if game.story_intro_pending:
                    self.assertTrue(game.choose_story_relic_path(0))
                game.active_cutscene = None
                game.show_help = True
                game.draw_help_overlay()
                game.inventory_open = True
                game.draw_inventory()
                game.state = "dead"
                game.draw_state_overlay()
            finally:
                pass


if __name__ == "__main__":
    unittest.main()
