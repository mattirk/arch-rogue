# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
#
# AI Provenance & Liability Notice:
# This repository contains code generated, assisted, or refactored by Artificial
# Intelligence models. Provided strictly "AS IS" under Apache 2.0 with no warranty
# of clean IP provenance or non-infringement; downstream users assume all legal
# and financial risk and should perform their own compliance audits.
#
# 4.8.7 bar toast pilgrimage: every bar taps one random barrel for a single
# drink; toasting every bar the run generated earns the immortal Bar Dancer
# familiar companion on the final depth.
from __future__ import annotations

import os
import random
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame  # noqa: F401  (required to initialize pygame subsystems in tests)

from arch_rogue.constants import DUNGEON_DEPTH
from arch_rogue.content import ARCHETYPES
from arch_rogue.dungeon import BAR_ROOM_KIND
from arch_rogue.game import Game
from arch_rogue.models import Enemy


class BarToastTestCase(unittest.TestCase):
    def make_game(self, tmpdir, seed=41) -> Game:
        game = Game(
            screen_size=(960, 600),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.rng.seed(seed)
        game.restart(ARCHETYPES[0])
        self.settle_intro(game)
        return game

    def settle_intro(self, game: Game) -> None:
        if game.story_intro_pending:
            self.assertTrue(game.choose_story_relic_path(0))
        if game.active_mini_game is not None:
            # Pilgrimage coverage is about floor/bar state. Resolve the
            # 4.9.1 turning-point interlude through its fail-forward path so
            # the helper can keep descending without claiming a win reward.
            game.active_mini_game.phase = "result"
            game.active_mini_game.outcome = "lost"
            game.active_mini_game.result_time = 0.0
            self.assertTrue(game.update_active_mini_game(0.01))
        game.active_cutscene = None

    def stand_next_to(self, game: Game, tile_x: int, tile_y: int) -> None:
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            x, y = tile_x + dx + 0.5, tile_y + dy + 0.5
            if not game.dungeon.blocked_for_radius(x, y, 0.2):
                game.player.x, game.player.y = x, y
                return
        self.fail(f"no free tile adjacent to ({tile_x}, {tile_y})")

    def drink_at_current_bar(self, game: Game) -> None:
        bar = game.dungeon.special_room_for_kind(BAR_ROOM_KIND)
        tapped = game.bar_tapped_barrel(bar)
        self.assertIsNotNone(tapped)
        _key, barrel_x, barrel_y = tapped
        self.stand_next_to(game, barrel_x, barrel_y)
        self.assertIsNotNone(game.nearby_tapped_bar_barrel())
        # 4.8.10: a bar regular standing within reach answers the interact
        # first (the Greet prompt outranks the drink); greet, then toast.
        while game.nearby_greetable_npc() is not None:
            game.interact()
        game.interact()

    def walk_run(self, game: Game, skip_first_bar: bool = False) -> int:
        """Descend to the final depth, drinking at each bar; returns bar count."""
        bars_seen = 0
        skipped = False
        for _ in range(DUNGEON_DEPTH - 1):
            if game.dungeon.special_room_for_kind(BAR_ROOM_KIND) is not None:
                bars_seen += 1
                if skip_first_bar and not skipped:
                    skipped = True
                else:
                    self.drink_at_current_bar(game)
            game.descend_to_next_depth()
            self.settle_intro(game)
        if game.dungeon.special_room_for_kind(BAR_ROOM_KIND) is not None:
            bars_seen += 1
            if not (skip_first_bar and not skipped):
                self.drink_at_current_bar(game)
        return bars_seen

    # --- tapped barrel -------------------------------------------------

    def test_every_bar_taps_one_deterministic_barrel(self) -> None:
        # Across seeds, every generated bar exposes exactly one tapped barrel,
        # it is one of the placed barrel anchors, and re-derivation is stable.
        from arch_rogue.dungeon import Dungeon
        from tests.test_flavor_rooms import _FlavorPopulationHarness

        bars_checked = 0
        for seed in range(60, 140):
            dungeon = Dungeon(random.Random(seed), guest_room=True)
            special = dungeon.special_room_for_kind(BAR_ROOM_KIND)
            if special is None:
                continue
            harness = _FlavorPopulationHarness(dungeon)
            harness._populate_bar_special_room(
                special, dungeon.rooms[special.room_index]
            )
            tapped = harness.bar_tapped_barrel(special)
            self.assertIsNotNone(tapped)
            key, tap_x, tap_y = tapped
            self.assertIn(key, harness._BAR_BARREL_ANCHORS)
            self.assertEqual(tuple(special.anchor(key)), (tap_x, tap_y))
            self.assertEqual(harness.bar_tapped_barrel(special), tapped)
            bars_checked += 1
        self.assertGreater(bars_checked, 10)

    def test_drink_is_offered_once_and_counts_the_toast(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            while game.dungeon.special_room_for_kind(BAR_ROOM_KIND) is None:
                game.descend_to_next_depth()
                self.settle_intro(game)
            bar = game.dungeon.special_room_for_kind(BAR_ROOM_KIND)
            tapped = game.bar_tapped_barrel(bar)
            _key, barrel_x, barrel_y = tapped
            self.stand_next_to(game, barrel_x, barrel_y)

            hint = game.current_interaction_hint()
            self.assertIsNotNone(hint)
            self.assertEqual(hint[1], "Drink from the tapped barrel")

            game.player.hp = max(1, game.player.hp - 20)
            hp_before = game.player.hp
            toasted_before = game.run_stats.bars_toasted
            game.interact()
            self.assertEqual(game.run_stats.bars_toasted, toasted_before + 1)
            self.assertTrue(bar.state.get("barrel_drunk"))
            self.assertGreater(game.player.hp, hp_before)
            # The single drink is spent: no further prompt, no second toast.
            self.assertIsNone(game.nearby_tapped_bar_barrel())
            game.interact()
            self.assertEqual(game.run_stats.bars_toasted, toasted_before + 1)

    def test_tapped_pick_and_counters_survive_save_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            while game.dungeon.special_room_for_kind(BAR_ROOM_KIND) is None:
                game.descend_to_next_depth()
                self.settle_intro(game)
            bar = game.dungeon.special_room_for_kind(BAR_ROOM_KIND)
            tapped = game.bar_tapped_barrel(bar)
            visited = game.run_stats.bars_visited
            self.drink_at_current_bar(game)
            game.save_run()

            loaded = Game(
                screen_size=(960, 600),
                headless=True,
                save_path=Path(tmpdir) / "run.json",
            )
            loaded.options_path = Path(tmpdir) / "options.json"
            self.assertTrue(loaded.load_run())
            # Loading never re-counts the persisted bar, keeps the drunk
            # state, and re-derives the identical tapped pick.
            self.assertEqual(loaded.run_stats.bars_visited, visited)
            self.assertEqual(loaded.run_stats.bars_toasted, 1)
            loaded_bar = loaded.dungeon.special_room_for_kind(BAR_ROOM_KIND)
            self.assertTrue(loaded_bar.state.get("barrel_drunk"))
            self.assertEqual(loaded.bar_tapped_barrel(loaded_bar), tapped)
            self.assertIsNone(loaded.nearby_tapped_bar_barrel())

    def test_tapped_barrel_carries_a_candle_light(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            while game.dungeon.special_room_for_kind(BAR_ROOM_KIND) is None:
                game.descend_to_next_depth()
                self.settle_intro(game)
            bar = game.dungeon.special_room_for_kind(BAR_ROOM_KIND)
            _key, tap_x, tap_y = game.bar_tapped_barrel(bar)
            taps = [
                source
                for source in game.light_sources
                if source.kind == "bar_tap"
            ]
            self.assertEqual(len(taps), 1)
            self.assertEqual((taps[0].x, taps[0].y), (tap_x + 0.5, tap_y + 0.5))

    # --- the immortal companion ----------------------------------------

    def test_toasting_every_bar_summons_immortal_dancer_at_final_depth(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            bars_seen = self.walk_run(game)
            self.assertGreater(bars_seen, 0, "seed 41 must roll bars")
            self.assertEqual(game.current_depth, DUNGEON_DEPTH)
            self.assertEqual(game.run_stats.bars_visited, bars_seen)
            self.assertEqual(game.run_stats.bars_toasted, bars_seen)

            dancers = [f for f in game.familiars if f.kind == "bar_dancer"]
            self.assertEqual(len(dancers), 1)
            dancer = dancers[0]
            self.assertTrue(dancer.unkillable)
            self.assertEqual(dancer.owner_id, game.player.player_id)
            self.assertEqual(game.familiar_damage_type(dancer), "physical")

            # Immortal: overwhelming damage floors at 1 HP and regen recovers.
            game._familiar_take_damage(dancer, 9999)
            self.assertEqual(dancer.hp, 1)
            self.assertTrue(dancer.alive)
            game.update_familiars(1.0)
            self.assertGreater(dancer.hp, 1)
            self.assertIn(dancer, game.familiars)

            # She fights on the shared familiar AI without crashing a frame.
            game.enemies.append(
                Enemy(
                    "Test Dummy",
                    "melee",
                    game.player.x + 1.0,
                    game.player.y,
                    40,
                    40,
                    1.0,
                    6,
                    10,
                    1.0,
                    1.0,
                )
            )
            for _ in range(90):
                game.update_familiars(1 / 60)

            # Never duplicated by a repeat call.
            game.maybe_summon_bar_dancer_companion()
            self.assertEqual(
                sum(1 for f in game.familiars if f.kind == "bar_dancer"), 1
            )

            # And she survives a save/load round trip on the final floor.
            game.save_run()
            loaded = Game(
                screen_size=(960, 600),
                headless=True,
                save_path=Path(tmpdir) / "run.json",
            )
            loaded.options_path = Path(tmpdir) / "options.json"
            self.assertTrue(loaded.load_run())
            restored = [f for f in loaded.familiars if f.kind == "bar_dancer"]
            self.assertEqual(len(restored), 1)
            self.assertTrue(restored[0].unkillable)

    def test_missing_one_bar_denies_the_dancer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            bars_seen = self.walk_run(game, skip_first_bar=True)
            self.assertGreater(bars_seen, 1)
            self.assertEqual(game.current_depth, DUNGEON_DEPTH)
            self.assertEqual(
                game.run_stats.bars_toasted, game.run_stats.bars_visited - 1
            )
            self.assertFalse(
                any(f.kind == "bar_dancer" for f in game.familiars)
            )

    def test_zero_bar_run_earns_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.familiars = []
            game.run_stats.bars_visited = 0
            game.run_stats.bars_toasted = 0
            game.maybe_summon_bar_dancer_companion()
            self.assertEqual(game.familiars, [])

    def test_final_depth_bar_completes_the_pact_on_the_spot(self) -> None:
        # A bar can roll on the gate tyrant's own floor: the completing drink
        # there summons the dancer immediately instead of never.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            while game.dungeon.special_room_for_kind(BAR_ROOM_KIND) is None:
                game.descend_to_next_depth()
                self.settle_intro(game)
            game.current_depth = DUNGEON_DEPTH
            self.drink_at_current_bar(game)
            self.assertEqual(
                sum(1 for f in game.familiars if f.kind == "bar_dancer"), 1
            )

    def test_dancer_familiar_uses_bar_dancer_art(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            familiar_frame = game.sprites.familiar_visual(
                0, 0.0, direction="south", moving=False, kind="bar_dancer"
            )
            dancer_frame = game.sprites.bar_dancer_visual(
                0.0, direction="south", moving=False, dancing=True
            )
            self.assertEqual(familiar_frame.is_asset, dancer_frame.is_asset)
            self.assertEqual(
                familiar_frame.surface.get_size(),
                dancer_frame.surface.get_size(),
            )


if __name__ == "__main__":
    unittest.main()
