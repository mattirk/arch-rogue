from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import cast

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame

from arch_rogue.content import ARCHETYPES
from arch_rogue.game import Game
from arch_rogue.models import Color, Item
from arch_rogue.rendering.hud import HUD_ACTION_SKILL_ASSETS


class HudPolish25Tests(unittest.TestCase):
    def tearDown(self) -> None:
        pass

    def make_game(self, tmpdir: str, seed: int = 2505) -> Game:
        game = Game(
            screen_size=(900, 540),
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.ui_scale = 1
        game.rebuild_fonts()
        game.rng.seed(seed)
        game.restart(ARCHETYPES[2])
        if game.story_intro_pending:
            self.assertTrue(game.choose_story_relic_path(0))
        game.active_cutscene = None
        return game

    def surface_signature(self, surface: pygame.Surface) -> str:
        rgba = pygame.image.tobytes(surface, "RGBA")
        digest = hashlib.blake2s(rgba, digest_size=16).hexdigest()
        return f"{surface.get_width()}x{surface.get_height()}:{digest}"

    def test_hud_action_slots_action_bar_and_mana_hotkey(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                # --- action slots include skill and potion hotkeys ---
                game.player.inventory = [
                    Item("Minor Healing Potion", "potion", heal=35),
                    Item("Lesser Mana Potion", "mana_potion", mana=24),
                ]
                game.player.hp = game.player.max_hp - 12
                game.player.mana = game.player.max_mana - 10
                game.player.bolt_timer = game.bolt_cooldown() * 0.5

                slots = game.hud_action_slots()
                self.assertEqual(
                    [slot["hotkey"] for slot in slots],
                    ["1", "2", "3", "4", "5", "6"],
                )
                self.assertEqual(
                    [slot["kind"] for slot in slots],
                    [
                        "melee",
                        "bolt",
                        "nova",
                        "dash",
                        "health_potion",
                        "mana_potion",
                    ],
                )
                self.assertEqual(
                    [slot["asset"] for slot in slots],
                    [
                        *HUD_ACTION_SKILL_ASSETS["Arcanist"],
                        "hud.action.health_potion",
                        "hud.action.mana_potion",
                    ],
                )
                self.assertEqual(slots[-2]["count"], 1)
                self.assertEqual(slots[-1]["count"], 1)
                self.assertIn("s", game.hud_action_slot_status(slots[1]))
                self.assertEqual(game.hud_action_slot_status(slots[-2]), "x1")
                self.assertEqual(game.hud_action_slot_status(slots[-1]), "x1")

                # --- bottom action bar renders icons and cooldown overlays ---
                game.player.inventory = [
                    Item("Minor Healing Potion", "potion", heal=35),
                    Item("Lesser Mana Potion", "mana_potion", mana=24),
                ]
                game.player.hp = game.player.max_hp - 20
                game.player.mana = game.player.max_mana - 14
                game.player.class_skill_timer = game.class_skill_cooldown() * 0.4
                rect = pygame.Rect(70, 440, 760, 70)

                game.screen.fill((11, 12, 16))
                before = self.surface_signature(game.screen)
                game.draw_hud_action_bar(rect)
                after_ready = self.surface_signature(game.screen)
                self.assertNotEqual(before, after_ready)

                game.screen.fill((11, 12, 16))
                game.player.class_skill_timer = 0.0
                game.draw_hud_action_bar(rect)
                after_no_cooldown = self.surface_signature(game.screen)
                self.assertNotEqual(after_ready, after_no_cooldown)

                # --- 6 hotkey drinks mana potion without using health potion ---
                game.player.hp = game.player.max_hp - 30
                game.player.mana = game.player.max_mana - 20
                game.player.inventory = [
                    Item("Minor Healing Potion", "potion", heal=35),
                    Item("Lesser Mana Potion", "mana_potion", mana=24),
                ]

                pygame.event.post(
                    pygame.event.Event(pygame.KEYDOWN, key=pygame.K_6, mod=0)
                )
                game.handle_events()

                self.assertEqual(game.player.hp, game.player.max_hp - 30)
                self.assertEqual(game.player.mana, game.player.max_mana)
                self.assertEqual(
                    [item.slot for item in game.player.inventory], ["potion"]
                )
            finally:
                pass


    def test_action_icon_body_is_cached_and_invalidated(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            slots = game.hud_action_slots()
            slot = next(s for s in slots if s.get("kind") == "bolt")
            color = cast(Color, slot["color"])
            icon = str(slot.get("icon", ""))
            label = str(slot.get("label", ""))
            hotkey = str(slot.get("hotkey", ""))
            asset = str(slot.get("asset", ""))
            args = ((60, 60), color, True, color, icon, label, hotkey, asset)
            b1 = game._build_hud_action_icon_body(*args)
            b2 = game._build_hud_action_icon_body(*args)
            # Rebuild is deterministic.
            self.assertEqual(b1.get_size(), b2.get_size())
            # draw_hud_action_icon populates the cache; the cached body is
            # present so steady-state frames reuse it instead of rebuilding.
            rect = pygame.Rect(10, 10, 60, 60)
            game.screen.fill((0, 0, 0))
            game.draw_hud_action_icon(slot, rect)
            ready = game.hud_action_slot_ready(slot)
            border = color if ready else game.HUD_IRON
            cached = game._hud_icon_cache.get(
                (
                    rect.size,
                    color,
                    ready,
                    border,
                    icon,
                    asset,
                    label,
                    hotkey,
                    game.ui_scale,
                    game.asset_ui_active(),
                )
            )
            self.assertIsNotNone(cached)
            # rebuild_fonts (ui / font change) drops the cache so stale art is
            # never reused after fonts are replaced.
            game.rebuild_fonts()
            self.assertEqual(game._hud_icon_cache, {})

    def test_modern_icons_replace_skill_labels_and_legacy_labels_remain(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            slot = next(s for s in game.hud_action_slots() if s.get("kind") == "bolt")
            color = cast(Color, slot["color"])
            args = (
                (60, 60),
                color,
                True,
                color,
                str(slot["icon"]),
                str(slot["label"]),
                str(slot["hotkey"]),
                str(slot["asset"]),
            )

            game._ui_text_cache = {}
            game._build_hud_action_icon_body(*args)
            modern_texts = {key[1] for key in game._ui_text_cache}
            self.assertNotIn("Arc Bolt", modern_texts)
            self.assertIn("2", modern_texts)
            self.assertIn(
                "hud.action.arcanist.arc_bolt",
                {key[0] for key in game.ui_assets._render_cache},
            )

            game._ui_text_cache = {}
            missing_asset_args = (*args[:-1], "hud.action.missing")
            game._build_hud_action_icon_body(*missing_asset_args)
            partial_fallback_texts = {key[1] for key in game._ui_text_cache}
            self.assertIn("Arc Bolt", partial_fallback_texts)
            self.assertIn("2", partial_fallback_texts)

            game.set_legacy_graphics(True)
            game._ui_text_cache = {}
            builds = game.ui_assets.render_build_count
            game._build_hud_action_icon_body(*args)
            legacy_texts = {key[1] for key in game._ui_text_cache}
            self.assertIn("Arc Bolt", legacy_texts)
            self.assertIn("2", legacy_texts)
            self.assertEqual(game.ui_assets.render_build_count, builds)

    def test_every_archetype_action_slot_has_a_distinct_authored_asset(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            skill_assets: set[str] = set()
            for archetype in ARCHETYPES:
                game.restart(archetype)
                slots = game.hud_action_slots()
                expected = HUD_ACTION_SKILL_ASSETS[archetype.name]
                self.assertEqual(
                    tuple(str(slot["asset"]) for slot in slots[:4]), expected
                )
                skill_assets.update(expected)
            self.assertEqual(len(skill_assets), 20)

    def test_action_icon_cooldown_overlay_darkens_top(self) -> None:
        # The cached body must not swallow the per-frame cooldown overlay: with
        # a cooldown active the top of the icon is darkened relative to the
        # bottom, and without one it is not.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            slots = game.hud_action_slots()
            slot = next(s for s in slots if s.get("kind") == "bolt")
            cd = float(cast(int | float, slot["cooldown"]))
            rect = pygame.Rect(120, 120, 60, 60)
            slot["timer"] = cd * 0.5
            game.screen.fill((0, 0, 0))
            game.draw_hud_action_icon(slot, rect)
            top_cd = sum(game.screen.get_at((rect.centerx, rect.y + 6))[:3])
            bot_cd = sum(game.screen.get_at((rect.centerx, rect.bottom - 6))[:3])
            self.assertLess(top_cd, bot_cd)
            slot["timer"] = 0.0
            game.screen.fill((0, 0, 0))
            game.draw_hud_action_icon(slot, rect)
            top_ready = sum(game.screen.get_at((rect.centerx, rect.y + 6))[:3])
            self.assertGreater(top_ready, top_cd)


if __name__ == "__main__":
    unittest.main()
