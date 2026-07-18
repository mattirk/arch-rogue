"""Quest cutscene asset schema, compatibility, and layout regressions."""

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

from arch_rogue.game import ARCHETYPES, Game
from arch_rogue.quest_assets import (
    AmbientEffectAsset,
    CurtainAsset,
    StageAsset,
    StageLightAsset,
    StagePropAsset,
    load_quest_cutscene_library,
)


class CutsceneAssetTests(unittest.TestCase):
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
        self.assertGreaterEqual(len(stage.props), 9)
        props = {prop.id: prop for prop in stage.props}
        pillar_ids = {
            f"pillar_{side}_{depth}"
            for side in ("left", "right")
            for depth in ("far", "mid", "front")
        }
        self.assertTrue(pillar_ids.issubset(props))
        self.assertTrue(all(props[prop_id].kind == "pillar" for prop_id in pillar_ids))
        for depth in ("far", "mid", "front"):
            self.assertAlmostEqual(
                props[f"pillar_left_{depth}"].x
                + props[f"pillar_right_{depth}"].x,
                1.0,
            )
        self.assertLess(
            props["pillar_left_far"].y,
            props["pillar_left_mid"].y,
        )
        self.assertLess(
            props["pillar_left_mid"].y,
            props["pillar_left_front"].y,
        )
        self.assertEqual(props["pillar_right_mid"].x, omen.actors["guest"].x)
        self.assertGreater(
            props["pillar_right_mid"].y,
            max(actor.y for actor in omen.actors.values()),
        )
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
                narration_scrollbar = game._cutscene_narration_scrollbar_rect
                self.assertTrue(game._cutscene_background_asset_used)
                self.assertTrue(game._cutscene_panel_asset_used)
                self.assertTrue(game._cutscene_curtain_asset_used)
                self.assertTrue(game._cutscene_choice_asset_used)
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
                self.assertIsNotNone(narration_scrollbar)
                assert narration_scrollbar is not None
                self.assertTrue(narrator.contains(narration_scrollbar))
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
                self.assertFalse(game._cutscene_curtain_asset_used)
                self.assertFalse(game._cutscene_choice_asset_used)

    def test_authored_choice_text_padding_scales_without_changing_legacy(self) -> None:
        for size, scale in (((960, 540), 1), ((1920, 1080), 2)):
            with self.subTest(scale=scale), tempfile.TemporaryDirectory() as tmpdir:
                game = self.make_game(tmpdir, size=size)
                game.set_legacy_graphics(False)
                game.ui_scale = scale
                game.rebuild_fonts()
                game.reveal_active_cutscene_narration()
                with patch.object(
                    game,
                    "draw_cutscene_response_text",
                    wraps=game.draw_cutscene_response_text,
                ) as draw_text:
                    game.draw()

                self.assertEqual(
                    len(draw_text.call_args_list),
                    len(game._cutscene_choice_rects),
                )
                for choice_rect, call in zip(
                    game._cutscene_choice_rects,
                    draw_text.call_args_list,
                ):
                    local_choice_rect = choice_rect.move(
                        -game._cutscene_panel_rect.x,
                        -game._cutscene_panel_rect.y,
                    )
                    panel_content = game.ui_asset_content_rect(
                        "cutscene.choice.panel",
                        local_choice_rect,
                    )
                    self.assertIsNotNone(panel_content)
                    assert panel_content is not None
                    self.assertEqual(
                        call.args[3],
                        panel_content.inflate(-game.ui(8), -game.ui(4)),
                    )
                    self.assertTrue(call.kwargs["center_vertically"])

        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, size=(960, 540))
            game.set_legacy_graphics(True)
            game.ui_scale = 1
            game.rebuild_fonts()
            game.reveal_active_cutscene_narration()
            with patch.object(
                game,
                "draw_cutscene_response_text",
                wraps=game.draw_cutscene_response_text,
            ) as draw_text:
                game.draw()

            self.assertEqual(
                len(draw_text.call_args_list),
                len(game._cutscene_choice_rects),
            )
            for choice_rect, call in zip(
                game._cutscene_choice_rects,
                draw_text.call_args_list,
            ):
                local_choice_rect = choice_rect.move(
                    -game._cutscene_panel_rect.x,
                    -game._cutscene_panel_rect.y,
                )
                key_size = min(
                    game.ui(36),
                    local_choice_rect.height - game.ui(12),
                )
                key_right = local_choice_rect.x + game.ui(7) + key_size
                text_x = max(
                    key_right + game.ui(12),
                    local_choice_rect.x + game.ui(62),
                )
                self.assertFalse(call.kwargs["center_vertically"])
                self.assertEqual(
                    call.args[3],
                    pygame.Rect(
                        text_x,
                        local_choice_rect.y + game.ui(7),
                        max(
                            1,
                            local_choice_rect.right - text_x - game.ui(8),
                        ),
                        local_choice_rect.height - game.ui(14),
                    ),
                )


if __name__ == "__main__":
    unittest.main()
