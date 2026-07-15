from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame

from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game
from arch_rogue.models import (
    Item,
    SecretCache,
    Shopkeeper,
    Shrine,
    StoryGuest,
    Trap,
)


class SoftShadow38Tests(unittest.TestCase):
    def make_game(self, tmpdir: str, seed: int = 3801) -> Game:
        game = Game(
            screen_size=(960, 540),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.rng.seed(seed)
        game.restart(ARCHETYPES[0])
        if game.story_intro_pending:
            self.assertTrue(game.choose_story_relic_path(0))
        game.active_cutscene = None
        return game

    def test_soft_shadow_template_is_cached_per_quantized_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                # Same size must return the identical cached surface object.
                first = game._soft_shadow_template(64)
                second = game._soft_shadow_template(64)
                self.assertIs(first, second)

                # Different sizes return distinct surfaces but all are valid
                # radial-alpha patches with a transparent border and a denser
                # core (soft contact shadow, not a hard ellipse).
                small = game._soft_shadow_template(24)
                large = game._soft_shadow_template(128)
                self.assertIsNot(small, first)
                self.assertIsNot(large, first)
                self.assertGreater(small.get_width(), 0)
                self.assertGreater(large.get_width(), 0)

                # Corners must be fully transparent (radial falloff to zero).
                self.assertEqual(small.get_at((0, 0))[3], 0)
                self.assertEqual(large.get_at((0, 0))[3], 0)
                # Center must be the densest point of the gradient.
                cx = cy = large.get_width() // 2
                center_alpha = large.get_at((cx, cy))[3]
                edge_alpha = large.get_at((cx, 2))[3]
                self.assertGreater(center_alpha, edge_alpha)
                self.assertGreater(center_alpha, 0)

                # Quantization: sizes within the same 4px bucket share one
                # template, keeping the cache small as lift/bob jitters sizes.
                bucket_a = game._soft_shadow_template(60)
                bucket_b = game._soft_shadow_template(61)
                self.assertIs(bucket_a, bucket_b)
            finally:
                pass

    def test_draw_shadow_applied_consistently_to_all_actors_and_props(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                # Instrument draw_shadow to record every caller so we can
                # confirm player, enemy, shopkeeper, story guest, loot, trap,
                # shrine, and secret all ground through the soft contact shadow.
                seen: list[str] = []
                original = game.draw_shadow

                def record_shadow(
                    x: float,
                    y: float,
                    width: int,
                    height: int,
                    moving: bool = False,
                    lift: float = 0.0,
                ) -> None:
                    seen.append(f"{width}x{height}")
                    original(x, y, width, height, moving=moving, lift=lift)

                game.draw_shadow = record_shadow  # type: ignore[assignment]
                try:
                    px, py = game.player.x, game.player.y
                    enemy = game.enemies[0]
                    enemy.x = px + 1.0
                    enemy.y = py
                    game.shopkeepers.append(
                        Shopkeeper(px - 1.0, py, "Keeper", "Wanderer", inventory=[])
                    )
                    game.story_guests.append(
                        StoryGuest(
                            px + 0.5,
                            py + 0.5,
                            game.current_depth,
                            0,
                            "Mira of the Veil",
                            "Exiled Witness",
                            "asks for a merciful answer",
                            "The guest waits beneath a violet oath.",
                            [],
                            color=(190, 150, 245),
                            met=True,
                        )
                    )
                    game.items.append(
                        Item(
                            "Loot Sword",
                            "weapon",
                            power=1,
                            rarity="Magic",
                            x=px,
                            y=py - 0.8,
                        )
                    )
                    game.traps.append(Trap(px + 0.8, py - 0.5, "Spike Trap", 1))
                    game.shrines.append(Shrine(px - 0.8, py + 0.5, "Mending Shrine"))
                    game.secrets.append(
                        SecretCache(
                            px - 0.5,
                            py - 0.5,
                            "Hidden Cache",
                            revealed=True,
                        )
                    )

                    game.draw_world_objects()
                finally:
                    game.draw_shadow = original  # type: ignore[assignment]

                # Each entity type must have grounded itself via draw_shadow.
                self.assertTrue(any(s == "34x13" for s in seen))  # player
                self.assertTrue(
                    any(s.endswith("x12") for s in seen)
                )  # enemy/shopkeeper
                self.assertTrue(any(s == "26x11" for s in seen))  # story guest / secret
                self.assertTrue(any(s == "22x9" for s in seen))  # loot item
                self.assertTrue(any(s == "28x11" for s in seen))  # trap
                self.assertTrue(any(s == "30x12" for s in seen))  # shrine
            finally:
                pass


if __name__ == "__main__":
    unittest.main()
