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
from arch_rogue.input import Command
from arch_rogue.mobile import (
    SafeInsets,
    build_mobile_layout,
    detect_mobile_runtime,
)


def make_mobile_game(
    tmpdir: str,
    size: tuple[int, int] = (1280, 720),
    insets: tuple[int, int, int, int] = (0, 0, 0, 0),
) -> Game:
    game = Game(
        screen_size=size,
        headless=True,
        save_path=Path(tmpdir) / "run.json",
        mobile=True,
        safe_insets=insets,
    )
    game.options_path = Path(tmpdir) / "options.json"
    game.rng.seed(2026)
    game.restart(ARCHETYPES[2])
    if game.story_intro_pending:
        game.choose_story_relic_path(0)
    game.active_cutscene = None
    return game


class MobileLayoutTests(unittest.TestCase):
    def test_safe_insets_coerce_and_clamp(self) -> None:
        self.assertEqual(SafeInsets.coerce(None), SafeInsets())
        self.assertEqual(SafeInsets.coerce((1, 2, 3, 4)), SafeInsets(1, 2, 3, 4))
        self.assertEqual(SafeInsets.coerce(SafeInsets(5, 6, 7, 8)), SafeInsets(5, 6, 7, 8))
        clamped = SafeInsets(120, 0, 120, 0).clamp_to(100, 50)
        self.assertEqual(clamped, SafeInsets(99, 0, 0, 0))
        clamped2 = SafeInsets(70, 8, 70, 8).clamp_to(100, 50)
        self.assertEqual(clamped2, SafeInsets(70, 8, 29, 8))
        with self.assertRaises(ValueError):
            SafeInsets.coerce((1, 2, 3))

    def test_layout_matrix_centers_viewport_and_keeps_rails_apart(self) -> None:
        for size, insets in (
            ((1280, 720), (0, 0, 0, 0)),
            ((2340, 1080), (90, 0, 18, 0)),
            ((2340, 1080), (18, 0, 90, 0)),
            ((1920, 1200), (0, 0, 0, 0)),
            ((1280, 960), (0, 0, 0, 0)),
        ):
            with self.subTest(size=size, insets=insets):
                layout = build_mobile_layout(size, insets)
                self.assertEqual(layout.display_rect.size, size)
                self.assertTrue(layout.safe_rect.contains(layout.left_rail))
                self.assertTrue(layout.safe_rect.contains(layout.right_rail))
                self.assertTrue(layout.safe_rect.contains(layout.world_viewport))
                self.assertFalse(layout.left_rail.colliderect(layout.world_viewport))
                self.assertFalse(layout.right_rail.colliderect(layout.world_viewport))
                self.assertEqual(layout.left_rail.width, layout.right_rail.width)
                self.assertEqual(layout.world_viewport.centerx, layout.safe_rect.centerx)
                self.assertEqual(len(layout.action_rects), 6)
                self.assertEqual(len(layout.resource_rects), 3)
                for first, second in zip(
                    layout.action_rects, layout.action_rects[1:]
                ):
                    self.assertFalse(first.colliderect(second))
                self.assertTrue(all(layout.safe_rect.contains(rect) for rect in layout.action_rects))
                self.assertTrue(layout.safe_rect.contains(layout.pause_rect))
                self.assertTrue(layout.safe_rect.contains(layout.interact_rect))

    def test_detect_mobile_runtime_env_override(self) -> None:
        old = os.environ.pop("ARCH_ROGUE_MOBILE", None)
        try:
            os.environ["ARCH_ROGUE_MOBILE"] = "1"
            self.assertTrue(detect_mobile_runtime())
            os.environ["ARCH_ROGUE_MOBILE"] = "no"
            self.assertFalse(detect_mobile_runtime())
        finally:
            if old is not None:
                os.environ["ARCH_ROGUE_MOBILE"] = old
            else:
                os.environ.pop("ARCH_ROGUE_MOBILE", None)


class MobileHudTests(unittest.TestCase):
    def test_mobile_hud_publishes_six_action_targets_and_resource_bars(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720), (42, 8, 18, 12))
            game.draw()
            self.assertEqual(len(game._hud_action_rects), 6)
            self.assertEqual(len(game._hud_resource_bar_rects), 3)
            layout = game.mobile_layout()
            self.assertEqual(game.mobile_safe_rect(), layout.safe_rect)
            self.assertEqual(game.mobile_world_viewport(), layout.world_viewport)
            ability_commands = {
                target.command
                for target in game._mobile_touch_targets
                if target.context == "gameplay"
                and target.command.startswith("ability_")
            }
            self.assertEqual(
                ability_commands,
                {
                    Command.ABILITY_1,
                    Command.ABILITY_2,
                    Command.ABILITY_3,
                    Command.ABILITY_4,
                    Command.ABILITY_5,
                    Command.ABILITY_6,
                },
            )
            self.assertIn(
                (Command.BACK, "Pause"),
                {(t.command, t.label) for t in game._mobile_touch_targets},
            )
            self.assertIn(
                (Command.INTERACT, "Interact"),
                {(t.command, t.label) for t in game._mobile_touch_targets},
            )

    def test_safe_insets_override_propagates_to_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (2340, 1080), (90, 0, 18, 0))
            self.assertEqual(game.mobile_safe_insets, SafeInsets(90, 0, 18, 0))
            layout = game.mobile_layout()
            self.assertEqual(layout.safe_rect.x, 90)
            self.assertEqual(layout.safe_rect.right, 2340 - 18)
            self.assertTrue(layout.left_rail.x >= layout.safe_rect.x)
            self.assertTrue(layout.right_rail.right <= layout.safe_rect.right)


class MobileTouchTests(unittest.TestCase):
    def finger_event(self, event_type: int, x: float, y: float, key=(0, 0)) -> pygame.event.Event:
        return pygame.event.Event(event_type, touch_id=key[0], finger_id=key[1], x=x, y=y)

    def test_world_finger_capture_updates_aim_and_release_stops(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            game.draw()
            viewport = game.mobile_world_viewport()
            inside = (viewport.centerx / 1280.0, viewport.centery / 720.0)
            down = self.finger_event(pygame.FINGERDOWN, *inside)
            self.assertTrue(game.handle_mobile_finger_event(down))
            self.assertTrue(game._mobile_touch_world_active)
            self.assertEqual(game.aim_input_mode, "touch")
            self.assertEqual(game.active_mobile_world_touch(), (viewport.centerx, viewport.centery))
            up = self.finger_event(pygame.FINGERUP, *inside)
            self.assertTrue(game.handle_mobile_finger_event(up))
            self.assertFalse(game._mobile_touch_world_active)
            self.assertIsNone(game.active_mobile_world_touch())

    def test_skill_finger_dispatches_ability_without_world_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            game.draw()
            layout = game.mobile_layout()
            slot = layout.action_rects[1]
            coords = ((slot.centerx + 0.5) / 1280.0, (slot.centery + 0.5) / 720.0)
            bolt_calls = 0
            original = game.player_cast_bolt

            def cast_bolt() -> None:
                nonlocal bolt_calls
                bolt_calls += 1
                original()

            game.player_cast_bolt = cast_bolt  # type: ignore[assignment]
            down = self.finger_event(pygame.FINGERDOWN, *coords)
            self.assertTrue(game.handle_mobile_finger_event(down))
            self.assertEqual(bolt_calls, 1)
            self.assertFalse(game._mobile_touch_world_active)

    def test_world_and_skill_fingers_can_coexist(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            game.draw()
            layout = game.mobile_layout()
            viewport = layout.world_viewport
            world_coords = (viewport.centerx / 1280.0, viewport.centery / 720.0)
            slot = layout.action_rects[0]
            skill_coords = ((slot.centerx + 0.5) / 1280.0, (slot.centery + 0.5) / 720.0)
            world_down = self.finger_event(pygame.FINGERDOWN, *world_coords, key=(0, 1))
            skill_down = self.finger_event(pygame.FINGERDOWN, *skill_coords, key=(0, 2))
            self.assertTrue(game.handle_mobile_finger_event(world_down))
            self.assertTrue(game.handle_mobile_finger_event(skill_down))
            self.assertTrue(game._mobile_touch_world_active)
            melee_calls = 0
            original = game.player_melee_attack

            def melee() -> None:
                nonlocal melee_calls
                melee_calls += 1
                original()

            game.player_melee_attack = melee  # type: ignore[assignment]
            self.assertTrue(game.handle_mobile_finger_event(skill_down))
            self.assertEqual(melee_calls, 1)

    def test_opening_inventory_cancels_world_contact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            game.draw()
            layout = game.mobile_layout()
            inventory = next(
                rect for name, rect in layout.utility_rects if name == "inventory"
            )
            coords = ((inventory.centerx + 0.5) / 1280.0, (inventory.centery + 0.5) / 720.0)
            world = (layout.world_viewport.centerx / 1280.0, layout.world_viewport.centery / 720.0)
            self.assertTrue(game.handle_mobile_finger_event(self.finger_event(pygame.FINGERDOWN, *world)))
            self.assertTrue(game._mobile_touch_world_active)
            self.assertTrue(game.handle_mobile_finger_event(self.finger_event(pygame.FINGERDOWN, *coords, key=(0, 9))))
            self.assertTrue(game.inventory_open)
            self.assertFalse(game._mobile_touch_world_active)


class MobileBackAndPauseTests(unittest.TestCase):
    def test_android_back_pauses_base_gameplay(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            self.assertEqual(game.state, "playing")
            back = pygame.event.Event(pygame.KEYDOWN, key=getattr(pygame, "K_AC_BACK", -1), mod=0)
            consumed = False
            pygame.event.clear()
            pygame.event.post(back)
            for event in pygame.event.get():
                if event.type == pygame.KEYDOWN and event.key == getattr(pygame, "K_AC_BACK", -1):
                    game._dispatch_command(Command.BACK)
                    consumed = True
            self.assertTrue(consumed)
            self.assertEqual(game.state, "confirm_exit")

    def test_android_back_never_commits_story_intro_choice(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = make_mobile_game(tmpdir, (1280, 720))
            game.state = "playing"
            game.story_intro_pending = True
            game._dispatch_command(Command.BACK)
            self.assertEqual(game.state, "confirm_exit")
            self.assertTrue(game.story_intro_pending)


if __name__ == "__main__":
    unittest.main()