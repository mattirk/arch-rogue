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

import pygame

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
        pygame.quit()

    def make_game(self, tmpdir: str, seed: int = 3401) -> Game:
        game = Game(
            screen_size=(960, 600),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.rng.seed(seed)
        game.restart(ARCHETYPES[2])
        return game

    # --- Schema / asset pipeline -------------------------------------------

    def test_schema_version_2_loads_with_full_stage_dressing(self) -> None:
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

    def test_schema_version_1_assets_still_load_with_default_stage(self) -> None:
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
            library = load_quest_cutscene_library(path)
        self.assertIn("legacy_scene", library)
        scene = library["legacy_scene"]
        # A schema_version 1 cutscene has no stage block, so it falls back to
        # the default StageAsset (empty dressing, proscenium/footlights on).
        self.assertIsInstance(scene.stage, StageAsset)
        self.assertEqual(scene.stage.props, ())
        self.assertEqual(scene.stage.lights, ())
        self.assertEqual(scene.stage.ambient, ())
        self.assertTrue(scene.stage.proscenium)

    def test_invalid_schema_version_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bad.json"
            path.write_text(json.dumps({"schema_version": 7, "cutscenes": []}))
            with self.assertRaises(ValueError):
                load_quest_cutscene_library(path)

    def test_invalid_stage_kind_values_are_rejected(self) -> None:
        base = {
            "schema_version": 2,
            "cutscenes": [
                {
                    "id": "s",
                    "title": "S",
                    "trigger": "manual",
                    "actors": [{"id": "player", "name": "P", "sprite": "player"}],
                    "animations": [],
                    "dialogue": {
                        "start": "n",
                        "nodes": [{"id": "n", "speaker": "narrator", "text": "x"}],
                    },
                }
            ],
        }
        for bad_stage in (
            {"stage": {"props": [{"id": "p", "kind": "fountain", "x": 0.5, "y": 0.5}]}},
            {
                "stage": {
                    "lights": [
                        {
                            "id": "l",
                            "kind": "flood",
                            "source_x": 0.5,
                            "source_y": 0.0,
                            "target_x": 0.5,
                            "target_y": 0.5,
                        }
                    ]
                }
            },
            {"stage": {"ambient": [{"kind": "rain"}]}},
            {"stage": {"curtain": {"side": "top"}}},
        ):
            payload = json.loads(json.dumps(base))
            payload["cutscenes"][0].update(bad_stage)
            with tempfile.TemporaryDirectory() as tmpdir:
                path = Path(tmpdir) / "bad.json"
                path.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_quest_cutscene_library(path)

    # --- Runtime pipeline --------------------------------------------------

    def test_active_cutscene_exposes_data_driven_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                self.assertTrue(game.story_intro_pending)
                self.assertIsNotNone(game.active_cutscene)
                asset = game.active_cutscene_asset()
                self.assertIsNotNone(asset)
                assert asset is not None
                self.assertGreater(len(asset.stage.props), 0)
                self.assertGreater(len(asset.stage.lights), 0)
                self.assertGreater(len(asset.stage.ambient), 0)
                self.assertEqual(asset.stage.curtain.side, "both")
            finally:
                pygame.quit()

    def test_cutscene_renders_without_error_across_many_frames(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                # Intro omen cutscene.
                game.reveal_active_cutscene_narration()
                for _ in range(30):
                    game.update_active_cutscene(1 / 60)
                    game.draw()
                # Guest dialogue cutscene.
                self.assertTrue(game.choose_story_relic_path(0))
                guest = game.story_guests[0]
                self.assertTrue(
                    game.start_quest_cutscene("story_guest_dialogue", guest)
                )
                game.reveal_active_cutscene_narration()
                for _ in range(30):
                    game.update_active_cutscene(1 / 60)
                    game.draw()
            finally:
                pygame.quit()

    def test_stage_static_layers_are_cached_across_frames(self) -> None:
        from arch_rogue.rendering.story_overlays import RenderingStoryOverlayMixin

        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                game.reveal_active_cutscene_narration()
                # Render once to populate the cache.
                game.draw()
                cache = RenderingStoryOverlayMixin._STAGE_CACHE
                snapshot = dict(cache)
                self.assertTrue(snapshot, "stage layer cache should be populated")
                # Render several more frames; static layers should be reused.
                for _ in range(20):
                    game.update_active_cutscene(1 / 60)
                    game.draw()
                # The cache should not grow unboundedly for static layers.
                self.assertLessEqual(len(cache), len(snapshot) + 4)
                # The cached surfaces should be the same objects (no rebuild).
                for key, surface in snapshot.items():
                    if key in cache:
                        self.assertIs(cache[key], surface)
            finally:
                pygame.quit()

    def test_narrator_card_renders_speaker_and_progress(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                captured: list[str] = []
                original = game.draw_ui_text

                def capture(surface, text, font, color, rect, *args, **kwargs):
                    captured.append(str(text))
                    return original(surface, text, font, color, rect, *args, **kwargs)

                game.draw_ui_text = capture
                try:
                    game.draw_quest_cutscene_overlay()
                finally:
                    game.draw_ui_text = original
                speaker = game.active_cutscene_speaker_name()
                self.assertTrue(any(speaker.upper() in line for line in captured))
            finally:
                pygame.quit()

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
                pygame.quit()


if __name__ == "__main__":
    unittest.main()
