"""Milestone 3.4 — Story Cutscene Refactor.

Validates the data-driven quest cutscene pipeline: the new schema_version 2
stage asset (props, lights, ambient, curtains, proscenium, footlights),
backward compatibility with schema_version 1, the polished narrator card,
and the hot-path safety of the stage renderer (no per-frame allocations of
the static layers, which are cached).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


from arch_rogue.game import ARCHETYPES, Game
from arch_rogue.quest_assets import (
    AmbientEffectAsset,
    CurtainAsset,
    StageAsset,
    StageLightAsset,
    StagePropAsset,
    load_quest_cutscene_library,
)


class StoryCutscene34Tests(unittest.TestCase):
    def tearDown(self) -> None:
        pass

    def make_game(
        self,
        tmpdir: str,
        seed: int = 3401,
        size: tuple[int, int] = (960, 600),
    ) -> Game:
        game = Game(
            screen_size=size,
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.rng.seed(seed)
        game.restart(ARCHETYPES[2])
        return game

    # --- Schema / asset pipeline -------------------------------------------

    def test_schema_versions_load_correctly(self) -> None:
        # schema_version 2: full stage dressing.
        library = load_quest_cutscene_library()
        self.assertIn("story_guest_omen", library)
        self.assertIn("story_guest_dialogue", library)
        for cutscene in library.values():
            self.assertIsInstance(cutscene.stage, StageAsset)

        omen = library["story_guest_omen"]
        stage = omen.stage
        self.assertEqual(stage.backdrop, "omen")
        self.assertTrue(stage.proscenium)
        self.assertTrue(stage.footlights)
        self.assertIsInstance(stage.curtain, CurtainAsset)
        self.assertEqual(stage.curtain.side, "both")
        self.assertGreater(stage.curtain.gather, 0.0)
        self.assertGreaterEqual(len(stage.props), 4)
        self.assertGreaterEqual(len(stage.lights), 3)
        self.assertGreaterEqual(len(stage.ambient), 1)
        # Props are frozen dataclasses with normalized coordinates.
        for prop in stage.props:
            self.assertIsInstance(prop, StagePropAsset)
            self.assertTrue(0.0 <= prop.x <= 1.0)
            self.assertTrue(0.0 <= prop.y <= 1.0)
            self.assertGreater(prop.scale, 0.0)
        for light in stage.lights:
            self.assertIsInstance(light, StageLightAsset)
            self.assertIn(light.kind, ("spot", "cone", "wash", "beam"))
            self.assertTrue(0.0 <= light.intensity <= 1.0)
        for effect in stage.ambient:
            self.assertIsInstance(effect, AmbientEffectAsset)
            self.assertIn(
                effect.kind,
                ("mote", "dust", "ember", "spark", "leaf", "snow", "ash"),
            )
            self.assertGreaterEqual(effect.count, 0)

        # schema_version 1: no stage block, falls back to default StageAsset.
        legacy_json = {
            "schema_version": 1,
            "cutscenes": [
                {
                    "id": "legacy_scene",
                    "title": "Legacy",
                    "trigger": "manual",
                    "actors": [{"id": "player", "name": "Player", "sprite": "player"}],
                    "animations": [],
                    "dialogue": {
                        "start": "n",
                        "nodes": [{"id": "n", "speaker": "narrator", "text": "hi"}],
                    },
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "legacy.json"
            path.write_text(json.dumps(legacy_json), encoding="utf-8")
            legacy_library = load_quest_cutscene_library(path)
        self.assertIn("legacy_scene", legacy_library)
        scene = legacy_library["legacy_scene"]
        self.assertIsInstance(scene.stage, StageAsset)
        self.assertEqual(scene.stage.props, ())
        self.assertEqual(scene.stage.lights, ())
        self.assertEqual(scene.stage.ambient, ())
        self.assertTrue(scene.stage.proscenium)

    # --- Runtime pipeline --------------------------------------------------

    def test_cutscene_renders_and_caches_static_layers(self) -> None:
        from arch_rogue.rendering.story_overlays import RenderingStoryOverlayMixin

        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                # Intro omen cutscene: render once to populate the cache.
                game.reveal_active_cutscene_narration()
                game.draw()
                cache = RenderingStoryOverlayMixin._STAGE_CACHE
                snapshot = dict(cache)
                self.assertTrue(snapshot, "stage layer cache should be populated")
                # Render several more frames; static layers should be reused
                # and the cutscene should not error.
                for _ in range(8):
                    game.update_active_cutscene(1 / 60)
                    game.draw()
                # The cache should not grow unboundedly for static layers.
                self.assertLessEqual(len(cache), len(snapshot) + 4)
                # The cached surfaces should be the same objects (no rebuild).
                for key, surface in snapshot.items():
                    if key in cache:
                        self.assertIs(cache[key], surface)

                # Guest dialogue cutscene: render frames without error.
                self.assertTrue(game.choose_story_relic_path(0))
                guest = game.story_guests[0]
                self.assertTrue(
                    game.start_quest_cutscene("story_guest_dialogue", guest)
                )
                game.reveal_active_cutscene_narration()
                for _ in range(8):
                    game.update_active_cutscene(1 / 60)
                    game.draw()
            finally:
                pass

    def test_asset_cutscene_background_and_compact_geometry(self) -> None:
        for size in ((960, 540), (640, 480)):
            with self.subTest(size=size), tempfile.TemporaryDirectory() as tmpdir:
                game = self.make_game(tmpdir, size=size)
                game.set_legacy_graphics(False)
                game.ui_scale = 1
                game.rebuild_fonts()
                game.reveal_active_cutscene_narration()
                game.draw()

                screen = game.screen.get_rect()
                panel = game._cutscene_panel_rect
                content = game._cutscene_content_rect
                stage = game._cutscene_stage_rect
                narrator = game._cutscene_narrator_rect
                choices = game._cutscene_choice_rects
                self.assertTrue(game._cutscene_background_asset_used)
                self.assertTrue(game._cutscene_panel_asset_used)
                self.assertIn(
                    "cutscene.background",
                    {key[0] for key in game.ui_assets._render_cache},
                )
                self.assertTrue(screen.contains(panel))
                self.assertLess(panel.width, screen.width)
                self.assertLess(panel.height, screen.height)
                self.assertTrue(panel.contains(content))
                self.assertTrue(content.contains(stage))
                self.assertTrue(content.contains(narrator))
                self.assertTrue(all(content.contains(choice) for choice in choices))
                self.assertLessEqual(stage.bottom, narrator.y)
                if choices:
                    self.assertLessEqual(narrator.bottom, choices[0].y)
                    self.assertTrue(
                        all(
                            first.bottom <= second.y
                            for first, second in zip(choices, choices[1:])
                        )
                    )

                game.set_legacy_graphics(True)
                game.draw()
                self.assertFalse(game._cutscene_background_asset_used)
                self.assertFalse(game._cutscene_panel_asset_used)

    def test_cutscene_save_restore_preserves_active_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                self.assertTrue(game.save_run())
                saved = json.loads(game.save_path.read_text(encoding="utf-8"))
                self.assertEqual(
                    saved["active_cutscene"]["asset_id"], "story_guest_omen"
                )
                loaded = Game(
                    screen_size=(960, 600),
                    headless=True,
                    save_path=game.save_path,
                )
                self.assertTrue(loaded.load_run(), loaded.last_load_error)
                self.assertIsNotNone(loaded.active_cutscene)
                assert loaded.active_cutscene is not None
                self.assertEqual(loaded.active_cutscene.asset_id, "story_guest_omen")
                asset = loaded.active_cutscene_asset()
                self.assertIsNotNone(asset)
                assert asset is not None
                self.assertGreater(len(asset.stage.props), 0)
            finally:
                pass


if __name__ == "__main__":
    unittest.main()
