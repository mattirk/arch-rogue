from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

    def rendered_projectile_frame_time(
        self, game: Game, projectile: Projectile
    ) -> float:
        with mock.patch.object(
            game.sprites,
            "projectile_frame",
            wraps=game.sprites.projectile_frame,
        ) as projectile_frame:
            game.draw_projectile(projectile)
        return float(projectile_frame.call_args.args[1])

    def test_modern_aim_cone_is_stronger_and_legacy_render_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.player.facing_x, game.player.facing_y = 1.0, 0.0

            game.set_legacy_graphics(True)
            game.draw_aim_cone()
            self.assertEqual(len(game._aim_cone_cache), 1)
            legacy_entry = next(iter(game._aim_cone_cache.values()))
            legacy_overlay, legacy_x, legacy_y, legacy_w, legacy_h = legacy_entry
            legacy_bytes = self.surface_bytes(legacy_overlay)
            legacy_alpha = legacy_bytes[3::4]
            game.draw_aim_cone()
            self.assertIs(
                next(iter(game._aim_cone_cache.values()))[0], legacy_overlay
            )

            game.set_legacy_graphics(False)
            self.assertTrue(game.sprites.modern_graphics_active)
            self.assertEqual(game._aim_cone_cache, {})
            game.draw_aim_cone()
            modern_entry = next(iter(game._aim_cone_cache.values()))
            modern_overlay, modern_x, modern_y, modern_w, modern_h = modern_entry
            modern_bytes = self.surface_bytes(modern_overlay)
            modern_alpha = modern_bytes[3::4]

            self.assertEqual(
                (modern_x, modern_y, modern_w, modern_h),
                (legacy_x, legacy_y, legacy_w, legacy_h),
            )
            self.assertGreater(sum(modern_alpha), sum(legacy_alpha) * 1.8)
            self.assertGreater(max(modern_alpha), max(legacy_alpha))
            game.draw_aim_cone()
            self.assertIs(
                next(iter(game._aim_cone_cache.values()))[0], modern_overlay
            )

            game.set_legacy_graphics(True)
            game.draw_aim_cone()
            restored_entry = next(iter(game._aim_cone_cache.values()))
            self.assertEqual(restored_entry[1:], legacy_entry[1:])
            self.assertEqual(self.surface_bytes(restored_entry[0]), legacy_bytes)

    def test_projectile_animation_cadence_ignores_travel_direction(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            open_dungeon = mock.Mock()
            open_dungeon.is_floor.return_value = True
            spawn_x, spawn_y = game.player.x, game.player.y
            forward = Projectile(
                spawn_x, spawn_y, 4.0, -1.5, 1, "player", (70, 165, 255)
            )
            reverse = Projectile(
                spawn_x, spawn_y, -4.0, 1.5, 1, "player", (70, 165, 255)
            )
            steps = (0.04, 0.07, 0.13)

            for dt in steps:
                self.assertTrue(forward.update(dt, open_dungeon))
                self.assertTrue(reverse.update(dt, open_dungeon))

            self.assertNotEqual((forward.x, forward.y), (reverse.x, reverse.y))
            game.elapsed = 2.0
            forward_frame_time = self.rendered_projectile_frame_time(game, forward)
            game.elapsed = 47.0
            reverse_frame_time = self.rendered_projectile_frame_time(game, reverse)

            expected_time = sum(steps)
            self.assertAlmostEqual(forward.anim_time, expected_time)
            self.assertAlmostEqual(reverse.anim_time, expected_time)
            self.assertAlmostEqual(forward_frame_time, reverse_frame_time)
            self.assertAlmostEqual(forward_frame_time, expected_time)

    def test_homing_turns_do_not_change_projectile_animation_cadence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            open_dungeon = mock.Mock()
            open_dungeon.is_floor.return_value = True
            target = game.enemies[0]
            game.enemies = [target]
            homing = Projectile(
                target.x - 2.0,
                target.y,
                0.0,
                -6.0,
                1,
                "player",
                (70, 165, 255),
                homing=1.0,
            )
            straight = Projectile(
                target.x - 2.0,
                target.y,
                0.0,
                -6.0,
                1,
                "player",
                (70, 165, 255),
            )
            steps = (0.04, 0.06, 0.08)

            for dt in steps:
                game._steer_homing_projectile(homing, dt)
                self.assertTrue(homing.update(dt, open_dungeon))
                self.assertTrue(straight.update(dt, open_dungeon))

            self.assertGreater(homing.vx, 0.0)
            self.assertGreater(homing.x, straight.x)
            self.assertGreater(homing.y, straight.y)
            game.elapsed = 8.5
            homing_frame_time = self.rendered_projectile_frame_time(game, homing)
            straight_frame_time = self.rendered_projectile_frame_time(game, straight)

            expected_time = sum(steps)
            self.assertAlmostEqual(homing.anim_time, expected_time)
            self.assertAlmostEqual(straight.anim_time, expected_time)
            self.assertAlmostEqual(homing_frame_time, straight_frame_time)
            self.assertAlmostEqual(homing_frame_time, expected_time)

    def test_projectile_frame_stays_fixed_without_simulation_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            open_dungeon = mock.Mock()
            open_dungeon.is_floor.return_value = True
            projectile = Projectile(
                game.player.x,
                game.player.y,
                3.0,
                1.0,
                1,
                "player",
                (70, 165, 255),
            )
            self.assertTrue(projectile.update(0.19, open_dungeon))
            paused_anim_time = projectile.anim_time
            paused_position = (projectile.x, projectile.y)

            game.elapsed = 1.0
            before_time = self.rendered_projectile_frame_time(game, projectile)
            before_frame = game.sprites.projectile_frame(
                projectile.owner,
                before_time,
                archetype=projectile.archetype,
            )
            game.elapsed = 99.75
            after_time = self.rendered_projectile_frame_time(game, projectile)
            after_frame = game.sprites.projectile_frame(
                projectile.owner,
                after_time,
                archetype=projectile.archetype,
            )

            self.assertEqual(projectile.anim_time, paused_anim_time)
            self.assertEqual((projectile.x, projectile.y), paused_position)
            self.assertAlmostEqual(before_time, after_time)
            self.assertEqual(
                self.surface_bytes(before_frame), self.surface_bytes(after_frame)
            )

    def test_hit_reactions_use_their_own_local_progress(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            enemy = game.enemies[0]
            enemy_id = id(enemy)
            game.player_hit_flash = 0.22
            game.player_hit_flash_duration = 0.22
            game.enemy_hit_flashes[enemy_id] = 0.22
            game.enemy_hit_flash_durations[enemy_id] = 0.22

            def rendered_progress() -> tuple[float, float]:
                with mock.patch.object(
                    game.sprites,
                    "player_visual",
                    wraps=game.sprites.player_visual,
                ) as player_visual, mock.patch.object(
                    game.sprites,
                    "enemy_visual",
                    wraps=game.sprites.enemy_visual,
                ) as enemy_visual:
                    game.draw_player(game.player)
                    game.draw_enemy(enemy)
                return (
                    float(player_visual.call_args.kwargs["action_progress"]),
                    float(enemy_visual.call_args.kwargs["action_progress"]),
                )

            self.assertEqual(rendered_progress(), (0.0, 0.0))
            game.update_visual_effects(0.11)
            player_progress, enemy_progress = rendered_progress()
            self.assertAlmostEqual(player_progress, 0.5, places=5)
            self.assertAlmostEqual(enemy_progress, 0.5, places=5)

    def test_sprite_atlas_exposes_cached_animation_frames(
        self,
    ) -> None:
        pygame.init()
        pygame.display.set_mode((64, 64), pygame.HIDDEN)
        atlas = PixelSpriteAtlas()
        actor_states = {"idle", "walk", "attack", "cast", "hit", "dash"}

        for archetype in ARCHETYPES:
            states = atlas.player_animation_frames[archetype.name]
            self.assertTrue(actor_states.issubset(states))
            for state in actor_states:
                self.assertGreaterEqual(len(states[state]), 3)
                self.assert_surface(states[state][0])
            base = atlas.player_sprites[archetype.name]
            for state in ("idle", "walk", "attack", "hit", "dash"):
                self.assertTrue(
                    all(frame.get_size() == base.get_size() for frame in states[state])
                )
            self.assertGreater(
                len({self.surface_bytes(frame) for frame in states["walk"]}), 1
            )
            self.assertNotEqual(
                self.surface_bytes(base), self.surface_bytes(states["attack"][1])
            )
            self.assert_surface(atlas.player_frame(archetype.name, "walk", 0.25, 0.5))

        for definition in FINAL_ROOM_ENEMY_DEFINITIONS:
            key = atlas.enemy_key(f"Runed {definition.name}", definition.kind)
            self.assertEqual(key, definition.name)
            states = atlas.enemy_animation_frames[key]
            self.assertTrue(actor_states.issubset(states))
            base = atlas.enemies[key]
            for state in actor_states:
                self.assertGreaterEqual(len(states[state]), 3)
                self.assert_surface(states[state][0])
            for state in ("idle", "walk", "attack", "hit", "dash"):
                self.assertTrue(
                    all(frame.get_size() == base.get_size() for frame in states[state])
                )
            self.assertGreater(
                len({self.surface_bytes(frame) for frame in states["walk"]}), 1
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

            finally:
                pass

    def test_visual_effect_timers_cleanup_without_save_schema_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            try:
                # Enemy walk animation must advance via the dedicated phase
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


if __name__ == "__main__":
    unittest.main()
