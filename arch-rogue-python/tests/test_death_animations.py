# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
#
# AI Provenance & Liability Notice:
# This repository contains code generated, assisted, or refactored by Artificial
# Intelligence models. Provided strictly "AS IS" under Apache 2.0 with no warranty
# of clean IP provenance or non-infringement; downstream users assume all legal
# and financial risk and should perform their own compliance audits.
#
# Player death visuals: one-shot "die" clip then looping "dead" corpse idle.
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

ARCHETYPE_SLUGS = ("warden", "rogue", "arcanist", "acolyte", "ranger")


class DeathAnimationTests(unittest.TestCase):
    def make_game(self, tmpdir: str, archetype_index: int = 0) -> Game:
        game = Game(
            screen_size=(960, 600),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.rng.seed(4801)
        game.restart(ARCHETYPES[archetype_index])
        if game.story_intro_pending:
            self.assertTrue(game.choose_story_relic_path(0))
        game.active_cutscene = None
        game.enemies = []
        game.projectiles = []
        game.traps = []
        return game

    def test_archetype_death_clips_are_complete_and_well_formed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            manifest = game.sprites.assets.manifest
            root = Path(game.sprites.assets.root)
            for slug in ARCHETYPE_SLUGS:
                entry = manifest["actors"][slug]
                clips = entry["clips"]
                for clip_name, loops in (("die", False), ("dead", True)):
                    self.assertIn(clip_name, clips, f"{slug} missing {clip_name}")
                    clip = clips[clip_name]
                    self.assertEqual(
                        bool(clip.get("loop", True)),
                        loops,
                        f"{slug} {clip_name} loop flag",
                    )
                    directions = clip["directions"]
                    # Death clips are authored for a single direction only.
                    self.assertEqual(sorted(directions), ["south"])
                    frames = directions["south"]
                    self.assertGreaterEqual(len(frames), 4)
                    for frame in frames:
                        self.assertTrue(
                            (root / frame).is_file(), f"missing frame {frame}"
                        )

    def test_single_direction_clip_falls_back_across_facings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            assets = game.sprites.assets
            for direction in ("east", "north-west", "south"):
                frame = assets.resolve_actor("Warden", "die", direction, 0.0)
                self.assertIsNotNone(frame)
                # The south-only clip is reused for every facing instead of
                # dropping to a static rotation frame.
                self.assertEqual(frame.key[2], "die")
                self.assertEqual(frame.key[3], "south")

    def test_die_clip_advances_and_clamps_then_dead_loops(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            assets = game.sprites.assets
            seconds = assets.actor_clip_seconds("Warden", "die")
            self.assertIsNotNone(seconds)
            first = assets.resolve_actor("Warden", "die", "south", 0.0)
            late = assets.resolve_actor("Warden", "die", "south", seconds * 4.0)
            self.assertNotEqual(first.key, late.key)
            # Non-looping: far beyond the end it stays clamped on the last frame.
            later = assets.resolve_actor("Warden", "die", "south", seconds * 9.0)
            self.assertEqual(late.key, later.key)
            # The corpse idle loops back to its first frame.
            dead_seconds = assets.actor_clip_seconds("Warden", "dead")
            wrapped = assets.resolve_actor("Warden", "dead", "south", dead_seconds)
            start = assets.resolve_actor("Warden", "dead", "south", 0.0)
            self.assertEqual(wrapped.key, start.key)

    def test_player_visual_state_prefers_death_over_everything(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.player.hp = 0
            game.player_hit_flash = 0.2
            game.player_action_state = "attack"
            game.player_action_ttl = 0.2
            game.player.death_anim_time = 0.0
            self.assertEqual(game.player_visual_state(game.player), "die")
            die_seconds = game.player_death_clip_seconds(game.player)
            game.player.death_anim_time = die_seconds + 0.05
            self.assertEqual(game.player_visual_state(game.player), "dead")

    def test_death_timer_accrues_and_overlay_is_held_for_the_clip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.story_intro_pending = False
            game.active_cutscene = None
            game.state = "playing"
            game.player.hp = 0
            game.update(0.016)
            # The run does not end on the death frame: the die clip plays
            # first while the world keeps simulating around the corpse.
            self.assertEqual(game.state, "playing")
            self.assertTrue(game.player_death_sequence_started)
            self.assertGreater(game.player.death_anim_time, 0.0)
            delay = game._death_overlay_delay(game.player)
            for _ in range(int(delay / 0.1) + 3):
                if game.state != "playing":
                    break
                game.update(0.1)
            self.assertEqual(game.state, "dead")
            self.assertEqual(game.run_stats.cause_of_death, "unknown dungeon violence")

    def test_alive_player_keeps_death_timer_reset(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.player.death_anim_time = 3.0
            game.advance_animation_phases(0.016)
            self.assertEqual(game.player.death_anim_time, 0.0)
            self.assertEqual(game.player_visual_state(game.player), "idle")


if __name__ == "__main__":
    unittest.main()
