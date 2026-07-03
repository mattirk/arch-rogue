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

from arch_rogue.content import ARCHETYPES, FINAL_ROOM_ENEMY_DEFINITIONS
from arch_rogue.game import Game
from arch_rogue.models import (
    ImpactEffect,
    Item,
    Projectile,
    SecretCache,
    Shrine,
    StoryGuest,
    Trap,
)
from arch_rogue.sprites import PixelSpriteAtlas


class GraphicsAnimation21Tests(unittest.TestCase):
    def tearDown(self) -> None:
        pass

    def make_game(self, tmpdir: str, seed: int = 2101) -> Game:
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

    def assert_surface(self, surface: pygame.Surface) -> None:
        self.assertGreater(surface.get_width(), 0)
        self.assertGreater(surface.get_height(), 0)

    def surface_bytes(self, surface: pygame.Surface) -> bytes:
        return pygame.image.tobytes(surface, "RGBA")

    def opaque_pixels(self, surface: pygame.Surface) -> int:
        return pygame.mask.from_surface(surface).count()

    def test_sprite_atlas_exposes_cached_animation_frames(
        self,
    ) -> None:
        pygame.init()
        pygame.display.set_mode((64, 64), pygame.HIDDEN)
        atlas = PixelSpriteAtlas()
        actor_states = {"idle", "run", "attack", "cast", "hit", "dash"}

        for archetype in ARCHETYPES:
            states = atlas.player_animation_frames[archetype.name]
            self.assertTrue(actor_states.issubset(states))
            for state in actor_states:
                self.assertGreaterEqual(len(states[state]), 3)
                self.assert_surface(states[state][0])
            base = atlas.player_sprites[archetype.name]
            for state in ("idle", "run", "attack", "hit", "dash"):
                self.assertTrue(
                    all(frame.get_size() == base.get_size() for frame in states[state])
                )
            self.assertGreater(
                len({self.surface_bytes(frame) for frame in states["run"]}), 1
            )
            self.assertNotEqual(
                self.surface_bytes(base), self.surface_bytes(states["attack"][1])
            )
            self.assert_surface(atlas.player_frame(archetype.name, "run", 0.25, 0.5))

        for definition in FINAL_ROOM_ENEMY_DEFINITIONS:
            key = atlas.enemy_key(f"Runed {definition.name}", definition.kind)
            self.assertEqual(key, definition.name)
            states = atlas.enemy_animation_frames[key]
            self.assertTrue(actor_states.issubset(states))
            base = atlas.enemies[key]
            for state in actor_states:
                self.assertGreaterEqual(len(states[state]), 3)
                self.assert_surface(states[state][0])
            for state in ("idle", "run", "attack", "hit", "dash"):
                self.assertTrue(
                    all(frame.get_size() == base.get_size() for frame in states[state])
                )
            self.assertGreater(
                len({self.surface_bytes(frame) for frame in states["run"]}), 1
            )
            self.assert_surface(
                atlas.enemy_frame(
                    f"Oathbound {definition.name}", definition.kind, "hit", 0.2, 0.4
                )
            )

        for slot in ("potion", "mana_potion", "identify", "weapon", "armor"):
            self.assertGreaterEqual(len(atlas.item_animation_frames[slot]), 4)
            self.assert_surface(atlas.item_frame(slot, 0.3, "Unique"))
        for trap_kind in ("Spike Trap", "Rune Trap", "Poison Needle"):
            self.assert_surface(atlas.trap_frame(trap_kind, 0.2))
        self.assert_surface(atlas.shrine_frame("Mending Shrine", 0.2))
        self.assert_surface(atlas.secret_frame(0.2))
        self.assert_surface(atlas.story_guest_frame(0.2))

    def test_world_rendering_handles_animated_visual_states(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                game.player.moving = True
                game.player.move_x = 1.0
                game.player.move_y = 0.0
                game.player.anim_time = 0.45
                game.player_hit_flash = 0.16
                game.set_player_action_visual("cast", 0.18)

                enemy = game.enemies[0]
                enemy.moving = True
                enemy.move_x = -1.0
                enemy.move_y = 0.25
                enemy.facing_x = -1.0
                enemy.anim_time = 0.35
                enemy.telegraph = "cast"
                enemy.attack_timer = enemy.attack_cooldown
                game.enemy_hit_flashes[id(enemy)] = 0.16

                game.items.append(
                    Item(
                        "Milestone Unique",
                        "weapon",
                        power=2,
                        rarity="Unique",
                        x=game.player.x + 0.5,
                        y=game.player.y,
                    )
                )
                game.traps.append(
                    Trap(game.player.x + 0.8, game.player.y, "Rune Trap", 1)
                )
                game.shrines.append(
                    Shrine(game.player.x, game.player.y + 0.8, "Haste Shrine")
                )
                game.secrets.append(
                    SecretCache(
                        game.player.x - 0.8,
                        game.player.y,
                        "Hidden Cache",
                        revealed=True,
                    )
                )
                game.story_guests.append(
                    StoryGuest(
                        game.player.x + 1.0,
                        game.player.y + 0.35,
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
                game.projectiles.append(
                    Projectile(
                        game.player.x,
                        game.player.y,
                        3.0,
                        1.0,
                        1,
                        "player",
                        (70, 165, 255),
                    )
                )
                game.slashes.append((game.player.x, game.player.y, 0.16, 1.0, 0.0))
                game.impact_effects.extend(
                    [
                        ImpactEffect(
                            game.player.x, game.player.y, (245, 95, 70), kind="blood"
                        ),
                        ImpactEffect(
                            game.player.x + 0.2,
                            game.player.y,
                            game.theme.accent,
                            kind="cast",
                        ),
                        ImpactEffect(
                            game.player.x - 0.2,
                            game.player.y,
                            game.theme.accent,
                            kind="death",
                        ),
                        ImpactEffect(
                            game.player.x,
                            game.player.y + 0.2,
                            game.skill_color(),
                            kind="dash",
                        ),
                    ]
                )

                game.draw()

                # Cooldown pips must only draw active progress: an all-zero
                # state leaves the HUD region untouched, while partial progress
                # paints visible pips. Reuses the same Game/floor since the pip
                # renderer only reads player timers and establishes its own
                # screen-fill baseline.
                game.screen.fill((17, 19, 23))
                before = self.surface_bytes(game.screen)

                game.player.melee_timer = 0.0
                game.player.bolt_timer = 0.0
                game.player.nova_timer = 0.0
                game.player.dash_timer = 0.0
                hud_bounds = pygame.Rect(320, 430, 280, 80)
                game.draw_hud_cooldown_pips(hud_bounds)
                self.assertEqual(before, self.surface_bytes(game.screen))

                game.player.bolt_timer = game.bolt_cooldown() * 0.5
                game.player.dash_timer = game.dash_cooldown() * 0.25
                game.draw_hud_cooldown_pips(hud_bounds)
                self.assertNotEqual(before, self.surface_bytes(game.screen))
            finally:
                pass

    def test_visual_effect_timers_cleanup_without_save_schema_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                # Enemy run animation must advance via the dedicated phase
                # accumulator rather than the old distance-based advance.
                enemy = game.enemies[0]
                enemy.moving = True
                enemy.anim_time = 0.0
                before = enemy.anim_time
                game.advance_animation_phases(0.0166)
                self.assertGreater(enemy.anim_time, before)

                # Visual effect timers must all decay and clear together without
                # touching the save schema.
                game.enemy_hit_flashes[id(enemy)] = 0.05
                game.player_hit_flash = 0.05
                game.set_player_action_visual("attack", 0.05)
                game.slashes.append((game.player.x, game.player.y, 0.05, 1.0, 0.0))
                game.add_impact(
                    game.player.x, game.player.y, game.skill_color(), ttl=0.05
                )

                game.update_visual_effects(0.10)

                self.assertEqual(game.enemy_hit_flashes, {})
                self.assertEqual(game.player_hit_flash, 0.0)
                self.assertEqual(game.player_action_state, "")
                self.assertEqual(game.player_action_ttl, 0.0)
                self.assertEqual(game.slashes, [])
                self.assertEqual(game.impact_effects, [])
            finally:
                pass

    def test_run_animation_advances_smoothly_under_dt_jitter(self) -> None:
        # The run cycle must advance monotonically without skipping frames
        # backward or stalling, even when per-frame dt jitters from frame-rate
        # variance. This guards against the movement-stutter regression where
        # anim_time was advanced by jittery per-frame distance.
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                player = game.player
                run_frames = game.sprites.player_animation_frames[player.class_name][
                    "run"
                ]
                self.assertGreaterEqual(len(run_frames), 8)

                # Simulate movement with alternating short/long dt (as real fps
                # varies) and record the selected frame index each frame.
                indices: list[int] = []
                for i in range(120):
                    dt = 0.0166 if i % 4 != 0 else 0.028
                    game.move_actor(player, player.speed * dt, 0.0)
                    game.advance_animation_phases(dt)
                    self.assertTrue(player.moving)
                    phase = player.anim_time * 8.0
                    idx = int(abs(phase)) % len(run_frames)
                    indices.append(idx)

                # The frame index must never go backward by more than one wrap
                # (i.e. no reverse skips). Forward steps of 0 or 1 are expected;
                # a single 28ms frame may occasionally skip one frame, but
                # never two or more.
                max_forward_skip = 0
                for a, b in zip(indices, indices[1:]):
                    delta = (b - a) % len(run_frames)
                    if delta != 0:
                        max_forward_skip = max(max_forward_skip, delta)
                self.assertLessEqual(max_forward_skip, 2)

                # The cycle must actually progress: not stuck on one frame.
                self.assertGreater(len(set(indices)), 1)
                # And it must cycle around (visit frame 0 more than once).
                self.assertGreater(indices.count(0), 1)
            finally:
                pass


if __name__ == "__main__":
    unittest.main()
