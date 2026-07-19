from __future__ import annotations

import json
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

from arch_rogue.constants import (
    DUNGEON_WALL_VARIANTS,
    LIGHT_BAR_WALL_ELEVATION,
    LIGHT_SHADE_DOWNSAMPLE_LONG,
    TILE_H,
    TILE_W,
    WORLD_SCALE,
)
from arch_rogue.content import (
    ARCHETYPES,
    BOSS_DEFINITIONS,
    ENEMY_DEFINITIONS,
    FINAL_ROOM_ENEMY_DEFINITIONS,
)
from arch_rogue.game import Game
from arch_rogue.models import Room, Tile
from arch_rogue.sprite_assets import (
    BAR_WALL_SCONCE_DIRECTION_BY_FACE,
    GOLD_STACK_ASSET_KEYS,
    AssetSpriteLibrary,
    DIRECTIONS,
    SpriteAtlas,
)


class SpriteAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode((64, 64), pygame.HIDDEN)

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def make_game(self, tmpdir: str, size: tuple[int, int] = (960, 540)) -> Game:
        game = Game(
            screen_size=size,
            headless=True,
            save_path=Path(tmpdir) / "run.json",
        )
        game.options_path = Path(tmpdir) / "options.json"
        game.set_legacy_graphics(False)
        game.rng.seed(4000)
        game.restart(ARCHETYPES[0])
        if game.story_intro_pending:
            self.assertTrue(game.choose_story_relic_path(0))
        game.active_cutscene = None
        return game

    def test_manifest_covers_runtime_visual_roster(self) -> None:
        library = AssetSpriteLibrary()
        self.assertTrue(library.available, library.load_error)
        manifest = library.manifest
        self.assertEqual(manifest["format_version"], 1)
        self.assertEqual(tuple(manifest["directions"]), DIRECTIONS)

        for archetype in ARCHETYPES:
            for direction in DIRECTIONS:
                frame = library.resolve_actor(
                    archetype.name, "run", direction, 0.22
                )
                self.assertIsNotNone(frame, (archetype.name, direction))
                if frame is None:
                    continue
                self.assertEqual(frame.key[3], direction)
        for definition in (*ENEMY_DEFINITIONS, *FINAL_ROOM_ENEMY_DEFINITIONS):
            frame = library.resolve_actor(
                definition.name, "idle", "south", 0.0, kind=definition.kind
            )
            self.assertIsNotNone(frame, definition.name)
        for definition in BOSS_DEFINITIONS:
            frame = library.resolve_actor(
                definition.name, "idle", "south", 0.0, kind="boss"
            )
            self.assertIsNotNone(frame, definition.name)

        self.assertEqual(
            set(manifest["items"]),
            {"potion", "mana_potion", "identify", "weapon", "armor", "story_relic"},
        )
        required_props = {
            "trap_spike",
            "trap_rune",
            "trap_poison",
            "shrine",
            "secret_cache",
            "shop_sign",
            "ambush_bell",
            "bar_wall_sconce_south_east",
            "bar_wall_sconce_south_west",
            *GOLD_STACK_ASSET_KEYS,
        }
        self.assertTrue(required_props.issubset(manifest["props"]))
        for prop in required_props:
            self.assertIsNotNone(library.resolve_prop(prop), prop)

        atlas = SpriteAtlas()
        for side, direction in BAR_WALL_SCONCE_DIRECTION_BY_FACE.items():
            key = f"bar_wall_sconce_{direction.replace('-', '_')}"
            entry = manifest["props"][key]
            self.assertEqual(tuple(entry["source_canvas"]), (68, 68))
            self.assertEqual(entry["reference_height"], 47)
            self.assertEqual(entry["target_height"], 84)
            source = library._source_surface(entry["path"])
            self.assertIsNotNone(source)
            assert source is not None
            self.assertEqual(source.get_size(), (68, 68))
            bounds = source.get_bounding_rect(min_alpha=1)
            self.assertGreater(bounds.width, 0)
            self.assertGreater(bounds.height, 0)
            frame = atlas.bar_wall_sconce_visual(side)
            self.assertIsNotNone(frame)
            assert frame is not None
            self.assertTrue(frame.is_asset)
            self.assertEqual(frame.key[1], key)

        directional_doors = {
            f"door_{state}_{direction.replace('-', '_')}"
            for state in ("open", "closed")
            for direction in DIRECTIONS
        }
        special_walls = {
            f"wall_{kind}_{side}"
            for kind in ("quest_room", "bar", "garden")
            for side in ("left", "right")
        }
        required_world = {
            "floor",
            "wall",
            "stairs",
            "door_open",
            "door_closed",
            "shop_floor",
            "quest_floor",
            "bar_floor",
            "garden_floor",
            *directional_doors,
            *special_walls,
        }
        self.assertTrue(required_world.issubset(manifest["world"]))
        for state in ("open", "closed"):
            entries = {
                direction: manifest["world"][
                    f"door_{state}_{direction.replace('-', '_')}"
                ]
                for direction in DIRECTIONS
            }
            for first, opposite in (
                ("north", "south"),
                ("east", "west"),
                ("north-east", "south-west"),
                ("north-west", "south-east"),
            ):
                self.assertEqual(
                    entries[first]["path"],
                    entries[opposite]["path"],
                    (state, first, opposite),
                )
            self.assertTrue(
                all(
                    entry["path"]
                    in {
                        f"world/door_{state}_left.png",
                        f"world/door_{state}_right.png",
                    }
                    for entry in entries.values()
                )
            )

        world_kwargs = {
            "target_canvas": (360, 440),
            "target_anchor": (180, 340),
            "tint": (104, 106, 118),
            "accent": (150, 88, 176),
            "variant": 0,
        }
        for key in directional_doors | special_walls:
            self.assertIsNotNone(
                library.resolve_world(key, **world_kwargs),
                key,
            )

    def test_archetype_idle_and_run_assets_are_complete_and_well_formed(self) -> None:
        library = AssetSpriteLibrary()
        player_entries = {
            entry["name"]: entry
            for entry in library.manifest["actors"].values()
            if entry.get("category") == "player"
        }
        self.assertEqual(
            set(player_entries),
            {archetype.name for archetype in ARCHETYPES},
        )

        for archetype in ARCHETYPES:
            entry = player_entries[archetype.name]
            source_canvas = tuple(entry["source_canvas"])
            for state in ("idle", "run"):
                directions = entry["clips"][state]["directions"]
                self.assertEqual(
                    set(directions),
                    set(DIRECTIONS),
                    (archetype.name, state),
                )
                for direction, frame_paths in directions.items():
                    expected_frames = 4 if state == "idle" else 6
                    if (archetype.name, state, direction) == (
                        "Arcanist",
                        "run",
                        "south",
                    ):
                        expected_frames = 8
                    with self.subTest(
                        archetype=archetype.name,
                        state=state,
                        direction=direction,
                    ):
                        self.assertEqual(len(frame_paths), expected_frames)
                        surfaces = [
                            library._source_surface(path) for path in frame_paths
                        ]
                        self.assertNotIn(None, surfaces)
                        decoded = [surface for surface in surfaces if surface is not None]
                        self.assertEqual(len(decoded), expected_frames)
                        unique_frame_count = len(
                            {
                                pygame.image.tobytes(surface, "RGBA")
                                for surface in decoded
                            }
                        )
                        expected_unique_frames = expected_frames
                        self.assertEqual(
                            unique_frame_count,
                            expected_unique_frames,
                        )
                        for surface in decoded:
                            self.assertEqual(surface.get_size(), source_canvas)
                            bounds = surface.get_bounding_rect(min_alpha=1)
                            self.assertGreater(bounds.width, 0)
                            self.assertGreater(bounds.height, 0)
                            self.assertGreaterEqual(bounds.left, 1)
                            self.assertGreaterEqual(bounds.top, 1)
                            self.assertLessEqual(bounds.right, surface.get_width() - 1)
                            self.assertLessEqual(bounds.bottom, surface.get_height() - 1)

    def test_archetype_stage_act_assets_are_complete_and_animated(self) -> None:
        library = AssetSpriteLibrary()
        for archetype in ARCHETYPES:
            slug = archetype.name.casefold()
            entry = library.manifest["actors"][slug]
            clip = entry["clips"]["act"]
            self.assertEqual(clip["fps"], 4.0, archetype.name)
            self.assertTrue(clip["loop"], archetype.name)
            self.assertEqual(set(clip["directions"]), {"south"}, archetype.name)

            paths = clip["directions"]["south"]
            self.assertEqual(
                paths,
                [
                    f"actors/{slug}/animations/act/south/frame_{index:03d}.png"
                    for index in range(8)
                ],
            )
            surfaces = [library._source_surface(path) for path in paths]
            self.assertNotIn(None, surfaces, archetype.name)
            decoded = [surface for surface in surfaces if surface is not None]
            self.assertEqual(len(decoded), 8)
            self.assertEqual(
                len({pygame.image.tobytes(surface, "RGBA") for surface in decoded}),
                8,
                archetype.name,
            )
            for surface in decoded:
                self.assertEqual(surface.get_size(), tuple(entry["source_canvas"]))
                bounds = surface.get_bounding_rect(min_alpha=1)
                self.assertGreater(bounds.width, 0)
                self.assertGreater(bounds.height, 0)
                self.assertGreaterEqual(bounds.left, 1)
                self.assertGreaterEqual(bounds.top, 1)
                self.assertLessEqual(bounds.right, surface.get_width() - 1)
                self.assertLessEqual(bounds.bottom, surface.get_height() - 1)

            resolved = [
                library.resolve_actor(archetype.name, "act", "south", clip_time)
                for clip_time in (0.0, 0.26, 0.51, 0.76)
            ]
            self.assertNotIn(None, resolved, archetype.name)
            frames = [frame for frame in resolved if frame is not None]
            self.assertTrue(all(frame.is_asset for frame in frames))
            self.assertEqual(
                {frame.key[1:4] for frame in frames},
                {(slug, "act", "south")},
            )
            self.assertEqual({frame.key[4] for frame in frames}, {0, 1, 2, 3})

            # The clip is intentionally south-only. Other directions preserve
            # the library's existing static-rotation fallback.
            fallback = library.resolve_actor(archetype.name, "act", "east", 0.0)
            self.assertIsNotNone(fallback)
            assert fallback is not None
            self.assertEqual(fallback.key[1:4], (slug, "rotation", "east"))

    def test_gate_warden_reviewed_animation_set_is_complete_and_wired(self) -> None:
        library = AssetSpriteLibrary()
        entry = library.manifest["actors"]["gate_warden"]
        self.assertEqual(entry["name"], "Gate Warden")
        self.assertEqual(tuple(entry["source_canvas"]), (208, 208))
        self.assertEqual(tuple(entry["source_anchor"]), (104.0, 156.0))
        contracts = {
            "idle": (5.0, True, 4),
            "run": (9.0, True, 6),
            "attack": (12.0, False, 8),
        }
        self.assertEqual(set(entry["clips"]), set(contracts))

        for state, (fps, looping, frame_count) in contracts.items():
            clip = entry["clips"][state]
            self.assertEqual(clip["fps"], fps)
            self.assertEqual(clip["loop"], looping)
            self.assertEqual(set(clip["directions"]), set(DIRECTIONS))
            for direction, paths in clip["directions"].items():
                with self.subTest(state=state, direction=direction):
                    self.assertEqual(
                        paths,
                        [
                            f"actors/gate_warden/animations/{state}/{direction}/"
                            f"frame_{index:03d}.png"
                            for index in range(frame_count)
                        ],
                    )
                    surfaces = [library._source_surface(path) for path in paths]
                    self.assertNotIn(None, surfaces)
                    decoded = [surface for surface in surfaces if surface is not None]
                    self.assertEqual(len(decoded), frame_count)
                    self.assertEqual(
                        len(
                            {
                                pygame.image.tobytes(surface, "RGBA")
                                for surface in decoded
                            }
                        ),
                        frame_count,
                    )
                    for surface in decoded:
                        self.assertEqual(surface.get_size(), (208, 208))
                        bounds = surface.get_bounding_rect(min_alpha=1)
                        self.assertGreater(bounds.width, 0)
                        self.assertGreater(bounds.height, 0)

        attack_frames = [
            library.resolve_actor(
                "Gate Warden",
                "attack",
                "west",
                99.0,
                kind="brute",
                clip_progress=progress,
            )
            for progress in (0.0, 0.5, 1.0)
        ]
        self.assertNotIn(None, attack_frames)
        resolved = [frame for frame in attack_frames if frame is not None]
        self.assertTrue(all(frame.is_asset for frame in resolved))
        self.assertEqual(
            [frame.key[1:] for frame in resolved],
            [
                ("gate_warden", "attack", "west", 0),
                ("gate_warden", "attack", "west", 4),
                ("gate_warden", "attack", "west", 7),
            ],
        )

    def test_spirit_beast_assets_are_complete_and_state_addressable(self) -> None:
        library = AssetSpriteLibrary()
        entry = library.manifest["actors"]["spirit_beast"]
        self.assertEqual(entry["name"], "Spirit Beast")
        self.assertIn("spirit_beast", entry["aliases"])
        self.assertIn("Spirit Beast", entry["aliases"])
        self.assertEqual(entry["category"], "familiar")
        self.assertEqual(tuple(entry["source_canvas"]), (184, 184))
        self.assertEqual(tuple(entry["source_anchor"]), (92.0, 127.0))
        self.assertEqual(entry["reference_height"], 76)
        self.assertEqual(entry["target_height"], 126)
        self.assertEqual(set(entry["rotations"]), set(DIRECTIONS))
        self.assertEqual(set(entry["clips"]), {"idle", "walk", "attack", "pet"})

        for direction, path in entry["rotations"].items():
            rotation = library._source_surface(path)
            self.assertIsNotNone(rotation, direction)
            assert rotation is not None
            self.assertEqual(rotation.get_size(), (184, 184))
            self.assertGreater(rotation.get_bounding_rect(min_alpha=1).height, 0)

        state_sequences: dict[str, set[tuple[bytes, ...]]] = {}
        for state in ("idle", "walk", "attack", "pet"):
            clip = entry["clips"][state]
            self.assertEqual(clip["loop"], state not in ("attack", "pet"))
            self.assertEqual(set(clip["directions"]), set(DIRECTIONS))
            sequences: set[tuple[bytes, ...]] = set()
            for direction, frame_paths in clip["directions"].items():
                with self.subTest(state=state, direction=direction):
                    self.assertEqual(
                        frame_paths,
                        [
                            f"actors/spirit_beast/animations/{state}/{direction}/"
                            f"frame_{index:03d}.png"
                            for index in range(8)
                        ],
                    )
                    surfaces = [library._source_surface(path) for path in frame_paths]
                    self.assertNotIn(None, surfaces)
                    decoded = [surface for surface in surfaces if surface is not None]
                    self.assertEqual(len(decoded), 8)
                    sequence = tuple(
                        pygame.image.tobytes(surface, "RGBA") for surface in decoded
                    )
                    self.assertEqual(len(set(sequence)), 8)
                    sequences.add(sequence)
                    for surface in decoded:
                        self.assertEqual(surface.get_size(), (184, 184))
                        bounds = surface.get_bounding_rect(min_alpha=1)
                        self.assertGreater(bounds.width, 0)
                        self.assertGreater(bounds.height, 0)
                        self.assertGreaterEqual(bounds.left, 1)
                        self.assertGreaterEqual(bounds.top, 1)
                        self.assertLessEqual(bounds.right, 183)
                        self.assertLessEqual(bounds.bottom, 183)

                    resolved = library.resolve_actor(
                        "Spirit Beast",
                        state,
                        direction,
                        0.25,
                        clip_progress=0.5 if state in ("attack", "pet") else None,
                    )
                    self.assertIsNotNone(resolved)
                    assert resolved is not None
                    self.assertEqual(resolved.key[1:4], ("spirit_beast", state, direction))
            self.assertEqual(len(sequences), 8)
            state_sequences[state] = sequences
        self.assertNotEqual(state_sequences["idle"], state_sequences["walk"])
        self.assertNotEqual(state_sequences["walk"], state_sequences["attack"])
        self.assertNotEqual(state_sequences["attack"], state_sequences["pet"])

        atlas = SpriteAtlas()
        for state, kwargs in (
            ("idle", {}),
            ("walk", {"moving": True}),
            ("attack", {"attacking": True, "attack_progress": 0.5}),
            ("pet", {"petting": True, "pet_progress": 0.5}),
        ):
            frame = atlas.familiar_visual(
                2,
                0.25,
                direction="south",
                kind="spirit_beast",
                **kwargs,
            )
            self.assertTrue(frame.is_asset)
            self.assertEqual(frame.key[1:3], ("spirit_beast", state))

    def test_friendly_npc_dance_clips_are_complete_and_beat_addressable(self) -> None:
        library = AssetSpriteLibrary()
        contracts = {
            "shopkeeper": "Shopkeeper",
            "story_guest": "Story Guest",
        }

        for slug, actor_name in contracts.items():
            entry = library.manifest["actors"][slug]
            self.assertEqual(tuple(entry["source_canvas"]), (180, 180))
            self.assertEqual(tuple(entry["source_anchor"]), (90.0, 135.0))
            self.assertEqual(entry["reference_height"], 89)
            self.assertEqual(entry["target_height"], 176)
            self.assertEqual(set(entry["clips"]), {"idle", "run", "dance"})

            for state, folder, frame_count in (
                ("idle", "idle", 8),
                ("run", "walk", 8),
                ("dance", "dance", 16),
            ):
                clip = entry["clips"][state]
                self.assertTrue(clip["loop"])
                self.assertEqual(clip["fps"], 8.0)
                self.assertEqual(set(clip["directions"]), set(DIRECTIONS))
                for direction, frame_paths in clip["directions"].items():
                    with self.subTest(actor=slug, state=state, direction=direction):
                        self.assertEqual(
                            frame_paths,
                            [
                                f"actors/{slug}/animations/{folder}/{direction}/"
                                f"frame_{index:03d}.png"
                                for index in range(frame_count)
                            ],
                        )
                        surfaces = [
                            library._source_surface(path) for path in frame_paths
                        ]
                        self.assertNotIn(None, surfaces)
                        decoded = [
                            surface for surface in surfaces if surface is not None
                        ]
                        self.assertEqual(len(decoded), frame_count)
                        self.assertEqual(
                            len(
                                {
                                    pygame.image.tobytes(surface, "RGBA")
                                    for surface in decoded
                                }
                            ),
                            frame_count,
                        )
                        for surface in decoded:
                            self.assertEqual(surface.get_size(), (180, 180))
                            bounds = surface.get_bounding_rect(min_alpha=1)
                            self.assertGreater(bounds.width, 0)
                            self.assertGreater(bounds.height, 0)
                            self.assertGreaterEqual(bounds.left, 1)
                            self.assertGreaterEqual(bounds.top, 1)
                            self.assertLessEqual(bounds.right, 179)
                            self.assertLessEqual(bounds.bottom, 179)

                        start = library.resolve_actor(
                            actor_name,
                            state,
                            direction,
                            99.0,
                            loop_progress=0.0,
                        )
                        midpoint = library.resolve_actor(
                            actor_name,
                            state,
                            direction,
                            0.0,
                            loop_progress=0.5,
                        )
                        wrapped = library.resolve_actor(
                            actor_name,
                            state,
                            direction,
                            0.0,
                            loop_progress=1.0,
                        )
                        self.assertIsNotNone(start)
                        self.assertIsNotNone(midpoint)
                        self.assertIsNotNone(wrapped)
                        assert start is not None
                        assert midpoint is not None
                        assert wrapped is not None
                        self.assertEqual(start.key[2:5], (state, direction, 0))
                        self.assertEqual(
                            midpoint.key[2:5], (state, direction, frame_count // 2)
                        )
                        self.assertEqual(wrapped.key[2:5], (state, direction, 0))

        atlas = SpriteAtlas()
        shop_idle = atlas.shopkeeper_visual(
            0.0, direction="north-east", clip_progress=0.5
        )
        shop_walk = atlas.shopkeeper_visual(
            0.0, direction="west", moving=True, clip_progress=0.5
        )
        guest_idle = atlas.story_guest_visual(
            0.0, direction="south-west", clip_progress=0.5
        )
        guest_walk = atlas.story_guest_visual(
            0.0, direction="north", moving=True, clip_progress=0.5
        )
        shop_dance = atlas.shopkeeper_visual(
            0.0, direction="south", dancing=True, clip_progress=0.5
        )
        guest_dance = atlas.story_guest_visual(
            0.0, direction="east", dancing=True, clip_progress=0.5
        )
        for frame, state, direction in (
            (shop_idle, "idle", "north-east"),
            (shop_walk, "run", "west"),
            (guest_idle, "idle", "south-west"),
            (guest_walk, "run", "north"),
            (shop_dance, "dance", "south"),
            (guest_dance, "dance", "east"),
        ):
            self.assertTrue(frame.is_asset)
            self.assertEqual(frame.key[2:4], (state, direction))

    def test_bar_dancer_assets_are_distinct_complete_and_beat_addressable(self) -> None:
        library = AssetSpriteLibrary()
        entry = library.manifest["actors"]["bar_dancer"]
        self.assertEqual(entry["name"], "Bar Dancer")
        self.assertEqual(entry["category"], "npc")
        self.assertEqual(entry["aliases"], ["Bar Dancer", "bar_dancer"])
        self.assertNotIn("bar", entry["aliases"])
        self.assertIn(
            "bar", library.manifest["actors"]["story_guest"]["aliases"]
        )
        self.assertEqual(tuple(entry["source_canvas"]), (244, 244))
        self.assertEqual(tuple(entry["source_anchor"]), (122.0, 183.0))
        self.assertEqual(entry["reference_height"], 119)
        self.assertEqual(entry["target_height"], 176)
        self.assertEqual(set(entry["clips"]), {"run", "dance"})

        rotation_paths = entry["rotations"]
        self.assertEqual(set(rotation_paths), set(DIRECTIONS))
        rotations: dict[str, pygame.Surface] = {}
        for direction, path in rotation_paths.items():
            self.assertEqual(path, f"actors/bar_dancer/rotations/{direction}.png")
            surface = library._source_surface(path)
            self.assertIsNotNone(surface)
            assert surface is not None
            rotations[direction] = surface
        self.assertEqual(
            len(
                {
                    pygame.image.tobytes(surface, "RGBA")
                    for surface in rotations.values()
                }
            ),
            8,
        )
        for surface in rotations.values():
            self.assertEqual(surface.get_size(), (244, 244))
            bounds = surface.get_bounding_rect(min_alpha=1)
            self.assertGreater(bounds.width, 0)
            self.assertGreater(bounds.height, 0)
            self.assertGreaterEqual(bounds.left, 1)
            self.assertGreaterEqual(bounds.top, 1)
            self.assertLessEqual(bounds.right, 243)
            self.assertLessEqual(bounds.bottom, 243)

        story_south = library._source_surface(
            library.manifest["actors"]["story_guest"]["rotations"]["south"]
        )
        self.assertIsNotNone(story_south)
        assert story_south is not None
        self.assertNotEqual(rotations["south"].get_size(), story_south.get_size())

        clip_sequences: dict[str, dict[str, bytes]] = {}
        for state, folder in (("run", "walk"), ("dance", "dance")):
            clip = entry["clips"][state]
            self.assertTrue(clip["loop"])
            self.assertEqual(clip["fps"], 8.0)
            self.assertEqual(set(clip["directions"]), set(DIRECTIONS))
            direction_sequences: dict[str, bytes] = {}
            for direction, frame_paths in clip["directions"].items():
                with self.subTest(state=state, direction=direction):
                    self.assertEqual(
                        frame_paths,
                        [
                            f"actors/bar_dancer/animations/{folder}/{direction}/"
                            f"frame_{index:03d}.png"
                            for index in range(8)
                        ],
                    )
                    surfaces = [
                        library._source_surface(path) for path in frame_paths
                    ]
                    self.assertNotIn(None, surfaces)
                    decoded = [
                        surface for surface in surfaces if surface is not None
                    ]
                    self.assertEqual(len(decoded), 8)
                    direction_sequences[direction] = b"".join(
                        pygame.image.tobytes(surface, "RGBA")
                        for surface in decoded
                    )
                    self.assertEqual(
                        len(
                            {
                                pygame.image.tobytes(surface, "RGBA")
                                for surface in decoded
                            }
                        ),
                        8,
                    )
                    for surface in decoded:
                        self.assertEqual(surface.get_size(), (244, 244))
                        bounds = surface.get_bounding_rect(min_alpha=1)
                        self.assertGreater(bounds.width, 0)
                        self.assertGreater(bounds.height, 0)
                        self.assertGreaterEqual(bounds.left, 1)
                        self.assertGreaterEqual(bounds.top, 1)
                        self.assertLessEqual(bounds.right, 243)
                        self.assertLessEqual(bounds.bottom, 243)

                    for progress, frame_index in (
                        (0.0, 0),
                        (0.25, 2),
                        (0.5, 4),
                        (0.75, 6),
                        (1.0, 0),
                    ):
                        frame = library.resolve_actor(
                            "Bar Dancer",
                            state,
                            direction,
                            99.0,
                            loop_progress=progress,
                        )
                        self.assertIsNotNone(frame)
                        assert frame is not None
                        self.assertEqual(
                            frame.key[2:5], (state, direction, frame_index)
                        )
            self.assertEqual(len(set(direction_sequences.values())), 8)
            clip_sequences[state] = direction_sequences

        self.assertTrue(
            all(
                clip_sequences["run"][direction]
                != clip_sequences["dance"][direction]
                for direction in DIRECTIONS
            )
        )

        atlas = SpriteAtlas()
        idle = atlas.bar_dancer_visual(0.0, direction="north-east")
        walking = atlas.bar_dancer_visual(
            0.0, direction="west", moving=True, clip_progress=0.5
        )
        dancing = atlas.bar_dancer_visual(
            0.0, direction="south", dancing=True, clip_progress=0.5
        )
        self.assertTrue(idle.is_asset)
        self.assertEqual(idle.key[1:4], ("bar_dancer", "rotation", "north-east"))
        self.assertTrue(walking.is_asset)
        self.assertEqual(walking.key[1:5], ("bar_dancer", "run", "west", 4))
        self.assertTrue(dancing.is_asset)
        self.assertEqual(dancing.key[1:5], ("bar_dancer", "dance", "south", 4))

        with tempfile.TemporaryDirectory() as tmpdir:
            fallback_atlas = SpriteAtlas(asset_root=Path(tmpdir))
            fallback_idle = fallback_atlas.bar_dancer_visual(
                0.0, clip_progress=0.5
            )
            fallback_walk = fallback_atlas.bar_dancer_visual(
                0.0, moving=True, clip_progress=0.5
            )
            fallback_dance = fallback_atlas.bar_dancer_visual(
                0.0, dancing=True, clip_progress=0.5
            )
        self.assertFalse(fallback_idle.is_asset)
        self.assertFalse(fallback_walk.is_asset)
        self.assertFalse(fallback_dance.is_asset)
        self.assertEqual(fallback_idle.key[-1], "idle")
        self.assertEqual(fallback_walk.key[-1], "run")
        self.assertEqual(fallback_dance.key[-1], "dance")
        fallback_pixels = {
            pygame.image.tobytes(frame.surface, "RGBA")
            for frame in (fallback_idle, fallback_walk, fallback_dance)
        }
        self.assertEqual(len(fallback_pixels), 3)

    def test_garden_frog_assets_are_complete_and_beat_addressable(self) -> None:
        library = AssetSpriteLibrary()
        entry = library.manifest["actors"]["garden_frog"]
        self.assertEqual(entry["name"], "Garden Frog")
        self.assertEqual(entry["category"], "npc")
        self.assertEqual(tuple(entry["source_canvas"]), (240, 240))
        self.assertEqual(tuple(entry["source_anchor"]), (120.0, 180.0))
        self.assertEqual(entry["reference_height"], 129)
        self.assertEqual(entry["target_height"], 96)
        self.assertEqual(set(entry["clips"]), {"run", "dance"})

        rotation_paths = entry["rotations"]
        self.assertEqual(set(rotation_paths), set(DIRECTIONS))
        rotations = []
        for direction, path in rotation_paths.items():
            self.assertEqual(path, f"actors/garden_frog/rotations/{direction}.png")
            surface = library._source_surface(path)
            self.assertIsNotNone(surface)
            assert surface is not None
            rotations.append(surface)
        self.assertEqual(
            len({pygame.image.tobytes(surface, "RGBA") for surface in rotations}),
            8,
        )

        for state, folder in (("run", "walk"), ("dance", "dance")):
            clip = entry["clips"][state]
            self.assertTrue(clip["loop"])
            self.assertEqual(clip["fps"], 8.0)
            self.assertEqual(set(clip["directions"]), set(DIRECTIONS))
            for direction, frame_paths in clip["directions"].items():
                with self.subTest(state=state, direction=direction):
                    self.assertEqual(
                        frame_paths,
                        [
                            f"actors/garden_frog/animations/{folder}/{direction}/"
                            f"frame_{index:03d}.png"
                            for index in range(8)
                        ],
                    )
                    surfaces = [
                        library._source_surface(path) for path in frame_paths
                    ]
                    self.assertNotIn(None, surfaces)
                    decoded = [
                        surface for surface in surfaces if surface is not None
                    ]
                    self.assertEqual(len(decoded), 8)
                    self.assertEqual(
                        len(
                            {
                                pygame.image.tobytes(surface, "RGBA")
                                for surface in decoded
                            }
                        ),
                        8,
                    )
                    if state == "dance":
                        self.assertEqual(
                            len(
                                {
                                    pygame.image.tobytes(decoded[index], "RGBA")
                                    for index in (0, 2, 4, 6)
                                }
                            ),
                            4,
                        )
                    for surface in decoded:
                        self.assertEqual(surface.get_size(), (240, 240))
                        bounds = surface.get_bounding_rect(min_alpha=1)
                        self.assertGreater(bounds.width, 0)
                        self.assertGreater(bounds.height, 0)
                        self.assertGreaterEqual(bounds.left, 1)
                        self.assertGreaterEqual(bounds.top, 1)
                        self.assertLessEqual(bounds.right, 239)
                        self.assertLessEqual(bounds.bottom, 239)

                    for progress, frame_index in (
                        (0.0, 0),
                        (0.25, 2),
                        (0.5, 4),
                        (0.75, 6),
                        (1.0, 0),
                    ):
                        frame = library.resolve_actor(
                            "Garden Frog",
                            state,
                            direction,
                            99.0,
                            loop_progress=progress,
                        )
                        self.assertIsNotNone(frame)
                        assert frame is not None
                        self.assertEqual(
                            frame.key[2:5], (state, direction, frame_index)
                        )

        north_walk = entry["clips"]["run"]["directions"]["north"]
        north_dance = entry["clips"]["dance"]["directions"]["north"]
        for walk_path, dance_path in zip(north_walk, north_dance, strict=True):
            walk_surface = library._source_surface(walk_path)
            dance_surface = library._source_surface(dance_path)
            self.assertIsNotNone(walk_surface)
            self.assertIsNotNone(dance_surface)
            assert walk_surface is not None and dance_surface is not None
            self.assertEqual(
                pygame.image.tobytes(dance_surface, "RGBA"),
                pygame.image.tobytes(walk_surface, "RGBA"),
            )

        for surface in rotations:
            self.assertEqual(surface.get_size(), (240, 240))
            bounds = surface.get_bounding_rect(min_alpha=1)
            self.assertGreater(bounds.width, 0)
            self.assertGreater(bounds.height, 0)
            self.assertGreaterEqual(bounds.left, 1)
            self.assertGreaterEqual(bounds.top, 1)
            self.assertLessEqual(bounds.right, 239)
            self.assertLessEqual(bounds.bottom, 239)

        atlas = SpriteAtlas()
        idle = atlas.garden_frog_visual(0.0, direction="north-east")
        walking = atlas.garden_frog_visual(
            0.0, direction="west", moving=True, clip_progress=0.5
        )
        dancing = atlas.garden_frog_visual(
            0.0, direction="south", dancing=True, clip_progress=0.5
        )
        self.assertTrue(idle.is_asset)
        self.assertEqual(idle.key[2:4], ("rotation", "north-east"))
        self.assertTrue(walking.is_asset)
        self.assertEqual(walking.key[2:5], ("run", "west", 4))
        self.assertTrue(dancing.is_asset)
        self.assertEqual(dancing.key[2:5], ("dance", "south", 4))

    def test_action_progress_does_not_override_looping_movement_clips(self) -> None:
        library = AssetSpriteLibrary()
        early = library.resolve_actor(
            "Warden",
            "dash",
            "south",
            0.35,
            clip_progress=0.0,
        )
        late = library.resolve_actor(
            "Warden",
            "dash",
            "south",
            0.35,
            clip_progress=0.95,
        )
        self.assertIsNotNone(early)
        self.assertIsNotNone(late)
        assert early is not None and late is not None
        self.assertEqual(early.key, late.key)
        self.assertEqual(early.key[2], "run")

    def test_legacy_player_actions_use_local_time_and_progress(self) -> None:
        atlas = SpriteAtlas(legacy_graphics=True)
        states = atlas.legacy.player_animation_frames["Warden"]

        for state in ("attack", "cast", "hit", "dash"):
            with self.subTest(state=state):
                frames = states[state]
                first = atlas.player_visual(
                    "Warden",
                    state,
                    37.0,
                    1.0,
                    action_time=0.0,
                )
                same_local_start = atlas.player_visual(
                    "Warden",
                    state,
                    37.0,
                    9.0,
                    action_time=0.0,
                )
                midpoint = atlas.player_visual(
                    "Warden",
                    state,
                    37.0,
                    91.0,
                    action_time=8.0,
                    action_progress=0.5,
                )
                final = atlas.player_visual(
                    "Warden",
                    state,
                    37.0,
                    123.0,
                    action_time=12.0,
                    action_progress=1.0,
                )

                self.assertFalse(first.is_asset)
                self.assertIs(first.surface, frames[0])
                self.assertIs(same_local_start.surface, frames[0])
                self.assertIs(midpoint.surface, frames[len(frames) // 2])
                self.assertIs(final.surface, frames[-1])

    def test_legacy_enemy_and_boss_actions_use_local_time_and_progress(self) -> None:
        atlas = SpriteAtlas(legacy_graphics=True)
        actors = (
            ("Ghoul", "melee", "Ghoul"),
            ("Gate Tyrant", "boss", "Gate Tyrant"),
        )

        for name, kind, frame_key in actors:
            with self.subTest(actor=name):
                frames = atlas.legacy.enemy_animation_frames[frame_key]["attack"]
                first = atlas.enemy_visual(
                    name,
                    kind,
                    "attack",
                    41.0,
                    1.0,
                    action_time=0.0,
                )
                same_local_start = atlas.enemy_visual(
                    name,
                    kind,
                    "attack",
                    41.0,
                    9.0,
                    action_time=0.0,
                )
                next_frame = atlas.enemy_visual(
                    name,
                    kind,
                    "attack",
                    41.0,
                    73.0,
                    action_time=0.1,
                )
                midpoint = atlas.enemy_visual(
                    name,
                    kind,
                    "attack",
                    41.0,
                    101.0,
                    action_time=8.0,
                    action_progress=0.5,
                )

                self.assertFalse(first.is_asset)
                self.assertIs(first.surface, frames[0])
                self.assertIs(same_local_start.surface, frames[0])
                self.assertIs(next_frame.surface, frames[1])
                self.assertIs(midpoint.surface, frames[len(frames) // 2])

        boss_frames = atlas.legacy.enemy_animation_frames["Gate Tyrant"]["cast"]
        boss_start = atlas.boss_frame(
            "cast",
            29.0,
            1.0,
            action_time=0.0,
        )
        boss_final = atlas.boss_frame(
            "cast",
            29.0,
            77.0,
            action_time=6.0,
            action_progress=1.0,
        )
        self.assertIs(boss_start, boss_frames[0])
        self.assertIs(boss_final, boss_frames[-1])

    def test_arcanist_action_clips_are_complete_non_looping_and_wired(self) -> None:
        library = AssetSpriteLibrary()
        arcanist = library.manifest["actors"]["arcanist"]
        clips = arcanist["clips"]

        for state, expected_fps in (("attack", 12.0), ("cast", 10.0)):
            clip = clips[state]
            self.assertEqual(clip["fps"], expected_fps)
            self.assertFalse(clip["loop"])
            self.assertEqual(set(clip["directions"]), set(DIRECTIONS))

            for direction in DIRECTIONS:
                with self.subTest(state=state, direction=direction):
                    frame_count = (
                        9 if state == "attack" and direction == "north" else 7
                    )
                    frame_paths = clip["directions"][direction]
                    self.assertEqual(
                        frame_paths,
                        [
                            f"actors/arcanist/animations/{state}/{direction}/"
                            f"frame_{index:03d}.png"
                            for index in range(frame_count)
                        ],
                    )
                    surfaces = [
                        library._source_surface(path) for path in frame_paths
                    ]
                    self.assertNotIn(None, surfaces)
                    decoded = [
                        surface for surface in surfaces if surface is not None
                    ]
                    self.assertEqual(len(decoded), frame_count)
                    self.assertEqual(
                        len(
                            {
                                pygame.image.tobytes(surface, "RGBA")
                                for surface in decoded
                            }
                        ),
                        7,
                    )
                    for surface in decoded:
                        self.assertEqual(surface.get_size(), (196, 196))
                        bounds = surface.get_bounding_rect(min_alpha=1)
                        self.assertGreater(bounds.width, 0)
                        self.assertGreater(bounds.height, 0)
                        self.assertGreaterEqual(bounds.left, 1)
                        self.assertGreaterEqual(bounds.top, 1)
                        self.assertLessEqual(bounds.right, 195)
                        self.assertLessEqual(bounds.bottom, 195)

                    start = library.resolve_actor(
                        "Arcanist",
                        state,
                        direction,
                        0.0,
                        clip_progress=0.0,
                    )
                    midpoint = library.resolve_actor(
                        "Arcanist",
                        state,
                        direction,
                        0.0,
                        clip_progress=0.5,
                    )
                    end = library.resolve_actor(
                        "Arcanist",
                        state,
                        direction,
                        0.0,
                        clip_progress=1.0,
                    )
                    self.assertIsNotNone(start)
                    self.assertIsNotNone(midpoint)
                    self.assertIsNotNone(end)
                    assert start is not None and midpoint is not None and end is not None
                    self.assertEqual(start.key[2:5], (state, direction, 0))
                    self.assertEqual(
                        midpoint.key[2:5],
                        (state, direction, frame_count // 2),
                    )
                    self.assertEqual(
                        end.key[2:5],
                        (state, direction, frame_count - 1),
                    )

        north_attack = [
            library._source_surface(path)
            for path in clips["attack"]["directions"]["north"]
        ]
        self.assertNotIn(None, north_attack)
        north_pixels = [
            pygame.image.tobytes(surface, "RGBA")
            for surface in north_attack
            if surface is not None
        ]
        self.assertEqual(north_pixels[0], north_pixels[1])
        self.assertEqual(north_pixels[0], north_pixels[-1])

    def test_arcanist_skills_select_authored_action_clips(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            arcanist = next(
                archetype for archetype in ARCHETYPES if archetype.name == "Arcanist"
            )
            game.restart(arcanist)
            if game.story_intro_pending:
                self.assertTrue(game.choose_story_relic_path(0))
            game.active_cutscene = None
            game.player.facing_x = -1.0
            game.player.facing_y = -1.0

            game.player.melee_timer = 0.0
            game.player.stamina = game.player.max_stamina
            game.player_melee_attack()
            self.assertEqual(game.player_visual_state(game.player), "attack")
            attack = game.sprites.player_visual(
                "Arcanist",
                "attack",
                0.0,
                game.elapsed,
                direction="north",
                action_time=0.1,
                action_progress=0.5,
            )
            self.assertTrue(attack.is_asset)
            self.assertEqual(attack.key[1:5], ("arcanist", "attack", "north", 4))

            for skill_name, cast_skill in (
                ("Arc Bolt", game.player_cast_bolt),
                ("Frost Nova", game.player_cast_nova),
            ):
                with self.subTest(skill=skill_name):
                    game.reset_transient_visuals()
                    game.player.mana = game.player.max_mana
                    game.player.bolt_timer = 0.0
                    game.player.class_skill_timer = 0.0
                    cast_skill()
                    self.assertEqual(game.player_visual_state(game.player), "cast")
                    cast = game.sprites.player_visual(
                        "Arcanist",
                        "cast",
                        0.0,
                        game.elapsed,
                        direction="north",
                        action_time=0.12,
                        action_progress=0.5,
                    )
                    self.assertTrue(cast.is_asset)
                    self.assertEqual(
                        cast.key[1:5],
                        ("arcanist", "cast", "north", 3),
                    )

    def test_rogue_action_clips_are_complete_non_looping_and_wired(self) -> None:
        library = AssetSpriteLibrary()
        rogue = library.manifest["actors"]["rogue"]
        clips = rogue["clips"]

        for state, expected_fps in (("attack", 12.0), ("cast", 10.0)):
            clip = clips[state]
            self.assertEqual(clip["fps"], expected_fps)
            self.assertFalse(clip["loop"])
            self.assertEqual(set(clip["directions"]), set(DIRECTIONS))

            for direction in DIRECTIONS:
                with self.subTest(state=state, direction=direction):
                    frame_paths = clip["directions"][direction]
                    self.assertEqual(
                        frame_paths,
                        [
                            f"actors/rogue/animations/{state}/{direction}/"
                            f"frame_{index:03d}.png"
                            for index in range(7)
                        ],
                    )
                    surfaces = [
                        library._source_surface(path) for path in frame_paths
                    ]
                    self.assertNotIn(None, surfaces)
                    decoded = [
                        surface for surface in surfaces if surface is not None
                    ]
                    self.assertEqual(len(decoded), 7)
                    self.assertEqual(
                        len(
                            {
                                pygame.image.tobytes(surface, "RGBA")
                                for surface in decoded
                            }
                        ),
                        7,
                    )
                    for surface in decoded:
                        self.assertEqual(surface.get_size(), (244, 244))
                        bounds = surface.get_bounding_rect(min_alpha=1)
                        self.assertGreater(bounds.width, 0)
                        self.assertGreater(bounds.height, 0)
                        self.assertGreaterEqual(bounds.left, 1)
                        self.assertGreaterEqual(bounds.top, 1)
                        self.assertLessEqual(bounds.right, 243)
                        self.assertLessEqual(bounds.bottom, 243)

                    start = library.resolve_actor(
                        "Rogue",
                        state,
                        direction,
                        0.0,
                        clip_progress=0.0,
                    )
                    midpoint = library.resolve_actor(
                        "Rogue",
                        state,
                        direction,
                        0.0,
                        clip_progress=0.5,
                    )
                    end = library.resolve_actor(
                        "Rogue",
                        state,
                        direction,
                        0.0,
                        clip_progress=1.0,
                    )
                    self.assertIsNotNone(start)
                    self.assertIsNotNone(midpoint)
                    self.assertIsNotNone(end)
                    assert start is not None and midpoint is not None and end is not None
                    self.assertEqual(start.key[2:5], (state, direction, 0))
                    self.assertEqual(midpoint.key[2:5], (state, direction, 3))
                    self.assertEqual(end.key[2:5], (state, direction, 6))

    def test_rogue_skills_select_authored_action_clips(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            rogue = next(
                archetype for archetype in ARCHETYPES if archetype.name == "Rogue"
            )
            game.restart(rogue)
            if game.story_intro_pending:
                self.assertTrue(game.choose_story_relic_path(0))
            game.active_cutscene = None
            game.player.facing_x = -1.0
            game.player.facing_y = -1.0

            game.player.melee_timer = 0.0
            game.player.stamina = game.player.max_stamina
            game.player_melee_attack()
            self.assertEqual(game.player_visual_state(game.player), "attack")
            attack = game.sprites.player_visual(
                "Rogue",
                "attack",
                0.0,
                game.elapsed,
                direction="north",
                action_time=0.1,
                action_progress=0.5,
            )
            self.assertTrue(attack.is_asset)
            self.assertEqual(attack.key[1:5], ("rogue", "attack", "north", 3))

            for skill_name, cast_skill in (
                ("Knife Fan", game.player_cast_bolt),
                ("Ambush Bell", game.player_cast_ambush_bell),
            ):
                with self.subTest(skill=skill_name):
                    game.reset_transient_visuals()
                    game.player.mana = game.player.max_mana
                    game.player.bolt_timer = 0.0
                    game.player.class_skill_timer = 0.0
                    cast_skill()
                    self.assertEqual(game.player_visual_state(game.player), "cast")
                    cast = game.sprites.player_visual(
                        "Rogue",
                        "cast",
                        0.0,
                        game.elapsed,
                        direction="north",
                        action_time=0.12,
                        action_progress=0.5,
                    )
                    self.assertTrue(cast.is_asset)
                    self.assertEqual(
                        cast.key[1:5],
                        ("rogue", "cast", "north", 3),
                    )

    def test_ranger_refresh_uses_reviewed_high_resolution_contract(self) -> None:
        library = AssetSpriteLibrary()
        ranger = library.manifest["actors"]["ranger"]

        self.assertEqual(tuple(ranger["source_canvas"]), (256, 256))
        self.assertEqual(tuple(ranger["source_anchor"]), (128.0, 212.0))
        self.assertEqual(ranger["reference_height"], 165)
        self.assertEqual(ranger["target_height"], 184)

        rotation_paths = ranger["rotations"]
        self.assertEqual(set(rotation_paths), set(DIRECTIONS))
        rotations = [
            library._source_surface(rotation_paths[direction])
            for direction in DIRECTIONS
        ]
        self.assertNotIn(None, rotations)
        decoded = [surface for surface in rotations if surface is not None]
        self.assertEqual(len(decoded), 8)
        self.assertEqual(
            len({pygame.image.tobytes(surface, "RGBA") for surface in decoded}),
            8,
        )
        for surface in decoded:
            self.assertEqual(surface.get_size(), (256, 256))

    def test_ranger_action_clips_are_complete_non_looping_and_wired(self) -> None:
        library = AssetSpriteLibrary()
        ranger = library.manifest["actors"]["ranger"]
        clips = ranger["clips"]
        expected_clips = {
            "attack": ("hit", 12.0, 6),
            "cast": ("cast", 10.0, 6),
            "pet": ("pet", 10.0, 8),
        }

        self.assertNotIn("hit", clips)
        for state, (folder, expected_fps, frame_count) in expected_clips.items():
            clip = clips[state]
            self.assertEqual(clip["fps"], expected_fps)
            self.assertFalse(clip["loop"])
            self.assertEqual(set(clip["directions"]), set(DIRECTIONS))

            for direction, frame_paths in clip["directions"].items():
                with self.subTest(state=state, direction=direction):
                    self.assertEqual(len(frame_paths), frame_count)
                    expected_prefix = (
                        f"actors/ranger/animations/{folder}/{direction}/"
                    )
                    self.assertTrue(
                        all(path.startswith(expected_prefix) for path in frame_paths)
                    )
                    surfaces = [library._source_surface(path) for path in frame_paths]
                    self.assertNotIn(None, surfaces)
                    decoded = [surface for surface in surfaces if surface is not None]
                    self.assertEqual(len(decoded), frame_count)
                    self.assertEqual(
                        len(
                            {
                                pygame.image.tobytes(surface, "RGBA")
                                for surface in decoded
                            }
                        ),
                        frame_count,
                    )
                    for surface in decoded:
                        self.assertEqual(surface.get_size(), (256, 256))
                        bounds = surface.get_bounding_rect(min_alpha=1)
                        self.assertGreaterEqual(bounds.left, 1)
                        self.assertGreaterEqual(bounds.top, 1)
                        self.assertLessEqual(bounds.right, 255)
                        self.assertLessEqual(bounds.bottom, 255)

                    start = library.resolve_actor(
                        "Ranger",
                        state,
                        direction,
                        0.0,
                        clip_progress=0.0,
                    )
                    end = library.resolve_actor(
                        "Ranger",
                        state,
                        direction,
                        0.0,
                        clip_progress=1.0,
                    )
                    self.assertIsNotNone(start)
                    self.assertIsNotNone(end)
                    assert start is not None and end is not None
                    self.assertEqual(start.key[2:5], (state, direction, 0))
                    self.assertEqual(
                        end.key[2:5], (state, direction, frame_count - 1)
                    )

    def test_ranger_skills_select_authored_action_clips(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.restart(ARCHETYPES[4])
            if game.story_intro_pending:
                self.assertTrue(game.choose_story_relic_path(0))
            game.active_cutscene = None
            game.player.facing_x = 0.0
            game.player.facing_y = 1.0

            game.player.melee_timer = 0.0
            game.player.stamina = game.player.max_stamina
            game.player_melee_attack()
            self.assertEqual(game.player_visual_state(game.player), "attack")
            attack = game.sprites.player_visual(
                "Ranger",
                "attack",
                0.0,
                game.elapsed,
                direction="south",
                action_time=0.1,
                action_progress=0.5,
            )
            self.assertTrue(attack.is_asset)
            self.assertEqual(attack.key[2], "attack")

            for skill_name, cast_skill in (
                ("Multishot", game.player_cast_bolt),
                ("Spirit Beast", game.player_cast_class_skill),
            ):
                with self.subTest(skill=skill_name):
                    game.reset_transient_visuals()
                    game.player.mana = game.player.max_mana
                    game.player.bolt_timer = 0.0
                    game.player.class_skill_timer = 0.0
                    cast_skill()
                    self.assertEqual(game.player_visual_state(game.player), "cast")
                    cast = game.sprites.player_visual(
                        "Ranger",
                        "cast",
                        0.0,
                        game.elapsed,
                        direction="south",
                        action_time=0.12,
                        action_progress=0.5,
                    )
                    self.assertTrue(cast.is_asset)
                    self.assertEqual(cast.key[2], "cast")

    def test_repaired_walks_have_clear_lower_body_motion(self) -> None:
        library = AssetSpriteLibrary()
        player_entries = {
            entry["name"]: entry
            for entry in library.manifest["actors"].values()
            if entry.get("category") == "player"
        }
        repaired_directions = (
            ("Warden", "south", 350),
            ("Ranger", "north", 350),
            ("Arcanist", "north", 200),
            ("Acolyte", "south", 350),
            ("Acolyte", "east", 350),
            ("Acolyte", "north", 350),
            ("Acolyte", "west", 350),
        )

        for archetype, direction, minimum_change in repaired_directions:
            with self.subTest(archetype=archetype, direction=direction):
                paths = player_entries[archetype]["clips"]["run"]["directions"][
                    direction
                ]
                surfaces = [library._source_surface(path) for path in paths]
                self.assertNotIn(None, surfaces)
                decoded = [surface for surface in surfaces if surface is not None]
                self.assertEqual(len(decoded), 6)

                bounds = decoded[0].get_bounding_rect(min_alpha=1)
                for surface in decoded[1:]:
                    bounds.union_ip(surface.get_bounding_rect(min_alpha=1))
                lower_body_y = round(bounds.top + bounds.height * 0.65)
                masks = [
                    pygame.mask.from_surface(
                        surface.subsurface(
                            (
                                0,
                                lower_body_y,
                                surface.get_width(),
                                surface.get_height() - lower_body_y,
                            )
                        ),
                        1,
                    )
                    for surface in decoded
                ]
                silhouette_changes = []
                for first_index, first in enumerate(masks):
                    for second in masks[first_index + 1 :]:
                        shared = first.overlap_area(second, (0, 0))
                        silhouette_changes.append(
                            first.count() + second.count() - 2 * shared
                        )
                self.assertGreaterEqual(
                    max(silhouette_changes),
                    minimum_change,
                    (archetype, direction, max(silhouette_changes)),
                )

    def test_gold_stack_variants_are_complete_distinct_and_cached(self) -> None:
        library = AssetSpriteLibrary()
        prop_frames = []
        for key in GOLD_STACK_ASSET_KEYS:
            frame = library.resolve_prop(key)
            self.assertIsNotNone(frame, key)
            assert frame is not None
            bounds = frame.surface.get_bounding_rect(min_alpha=1)
            self.assertGreaterEqual(bounds.top, 1, key)
            self.assertLessEqual(bounds.bottom, frame.surface.get_height() - 1, key)
            prop_frames.append(frame)
        self.assertEqual(
            len({pygame.image.tobytes(frame.surface, "RGBA") for frame in prop_frames}),
            len(GOLD_STACK_ASSET_KEYS),
        )

        atlas = SpriteAtlas()
        variants = [
            atlas.gold_stack_visual(2, index)
            for index in range(len(GOLD_STACK_ASSET_KEYS))
        ]
        for index, frame in enumerate(variants):
            self.assertTrue(frame.is_asset)
            self.assertIs(frame, atlas.gold_stack_visual(2, index))
        self.assertEqual(
            len({pygame.image.tobytes(frame.surface, "RGBA") for frame in variants}),
            len(GOLD_STACK_ASSET_KEYS),
        )

    def test_directional_doors_and_special_walls_use_dedicated_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.door_tile_cache.clear()
            game.sprites.assets.clear_derived_caches()
            with mock.patch.object(
                game.sprites,
                "world_tile_surface",
                wraps=game.sprites.world_tile_surface,
            ) as resolve_world:
                door = game.door_tile_surface(
                    Tile.CLOSED_DOOR, 0, "north-east"
                )
            dedicated_calls = [
                call
                for call in resolve_world.call_args_list
                if call.args and call.args[0] == "door_closed_north_east"
            ]
            self.assertEqual(len(dedicated_calls), 1)
            self.assertEqual(resolve_world.call_count, 1)
            self.assertFalse(dedicated_calls[0].kwargs.get("mirror", False))
            self.assertGreater(door[0].get_bounding_rect(min_alpha=1).height, 0)

            entry = game.sprites.assets.manifest["world"].pop(
                "door_closed_north_west"
            )
            try:
                game.door_tile_cache.clear()
                game.sprites.assets.clear_derived_caches()
                with mock.patch.object(
                    game.sprites,
                    "world_tile_surface",
                    wraps=game.sprites.world_tile_surface,
                ) as resolve_world:
                    fallback_door = game.door_tile_surface(
                        Tile.CLOSED_DOOR, 0, "north-west"
                    )
                self.assertEqual(resolve_world.call_count, 2)
                self.assertEqual(resolve_world.call_args_list[-1].args[0], "door_closed")
                self.assertFalse(resolve_world.call_args_list[-1].kwargs["mirror"])
                self.assertGreater(
                    fallback_door[0].get_bounding_rect(min_alpha=1).height, 0
                )
            finally:
                game.sprites.assets.manifest["world"][
                    "door_closed_north_west"
                ] = entry
                game.sprites.assets.clear_derived_caches()

            game.tile_cache.clear()
            game.sprites.assets.clear_derived_caches()
            with mock.patch.object(
                game.sprites.assets,
                "_decorate_special_wall",
                wraps=game.sprites.assets._decorate_special_wall,
            ) as decorate:
                special, _, _ = game.tile_surface(
                    Tile.WALL, 0, wall_face_style="bar:left"
                )
            self.assertEqual(decorate.call_args.args[1], None)
            generic, _, _ = game.tile_surface(Tile.WALL, 0)
            self.assertNotEqual(
                pygame.image.tobytes(special, "RGBA"),
                pygame.image.tobytes(generic, "RGBA"),
            )

            entry = game.sprites.assets.manifest["world"].pop("wall_bar_left")
            try:
                game.tile_cache.clear()
                game.sprites.assets.clear_derived_caches()
                with mock.patch.object(
                    game.sprites.assets,
                    "_decorate_special_wall",
                    wraps=game.sprites.assets._decorate_special_wall,
                ) as decorate:
                    fallback, _, _ = game.tile_surface(
                        Tile.WALL, 0, wall_face_style="bar:left"
                    )
                self.assertEqual(decorate.call_args.args[1], "bar:left")
                self.assertGreater(fallback.get_bounding_rect(min_alpha=1).height, 0)
            finally:
                game.sprites.assets.manifest["world"]["wall_bar_left"] = entry
                game.sprites.assets.clear_derived_caches()

    def test_bar_wall_sconces_render_assets_and_procedural_fallback(self) -> None:
        def changed_bounds(
            plain: pygame.Surface, mounted: pygame.Surface
        ) -> pygame.Rect:
            points = [
                (x, y)
                for x in range(plain.get_width())
                for y in range(plain.get_height())
                if plain.get_at((x, y)) != mounted.get_at((x, y))
            ]
            self.assertTrue(points)
            left = min(point[0] for point in points)
            top = min(point[1] for point in points)
            right = max(point[0] for point in points) + 1
            bottom = max(point[1] for point in points) + 1
            return pygame.Rect(left, top, right - left, bottom - top)

        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            self.assertEqual(
                game.actor_sprite_direction(0.0, 1.0),
                BAR_WALL_SCONCE_DIRECTION_BY_FACE["left"],
            )
            self.assertEqual(
                game.actor_sprite_direction(1.0, 0.0),
                BAR_WALL_SCONCE_DIRECTION_BY_FACE["right"],
            )
            wall_h = 48 * WORLD_SCALE
            self.assertEqual(LIGHT_BAR_WALL_ELEVATION, 0.50)
            for side, direction in (("left", -1), ("right", 1)):
                game.tile_cache.clear()
                plain, anchor_x, anchor_y = game.tile_surface(
                    Tile.WALL, 0, wall_face_style=f"bar:{side}"
                )
                mounted, _, _ = game.tile_surface(
                    Tile.WALL,
                    0,
                    wall_face_style=f"bar:{side}",
                    bar_wall_light_side=side,
                )
                changed = changed_bounds(plain, mounted)
                mount = (
                    anchor_x + direction * TILE_W // 4,
                    anchor_y
                    - round(LIGHT_BAR_WALL_ELEVATION * TILE_H)
                    + TILE_H // 4,
                )
                former_mount_y = anchor_y - wall_h // 2 + TILE_H // 4
                self.assertGreater(mount[1], former_mount_y)
                self.assertLess(mount[1], anchor_y)
                self.assertTrue(changed.inflate(4, 4).collidepoint(mount), side)

            game.tile_cache.clear()
            with mock.patch.object(
                game.sprites, "bar_wall_sconce_visual", return_value=None
            ):
                plain, anchor_x, anchor_y = game.tile_surface(
                    Tile.WALL, 1, wall_face_style="bar:left"
                )
                fallback, _, _ = game.tile_surface(
                    Tile.WALL,
                    1,
                    wall_face_style="bar:left",
                    bar_wall_light_side="left",
                )
            changed = changed_bounds(plain, fallback)
            mount = (
                anchor_x - TILE_W // 4,
                anchor_y
                - round(LIGHT_BAR_WALL_ELEVATION * TILE_H)
                + TILE_H // 4,
            )
            former_mount_y = anchor_y - wall_h // 2 + TILE_H // 4
            self.assertGreater(mount[1], former_mount_y)
            self.assertLess(mount[1], anchor_y)
            self.assertTrue(changed.inflate(4, 4).collidepoint(mount))

            game.tile_cache.clear()
            game.prewarm_tile_cache()
            for seed in range(DUNGEON_WALL_VARIANTS):
                for side in ("left", "right"):
                    key = (
                        game.theme.name,
                        int(Tile.WALL),
                        seed,
                        False,
                        False,
                        False,
                        False,
                        f"bar:{side}",
                        side,
                    )
                    self.assertIn(key, game.tile_cache)

    def test_world_reference_width_controls_authored_tile_footprint(self) -> None:
        library = AssetSpriteLibrary()
        kwargs = {
            "target_canvas": (360, 440),
            "target_anchor": (180, 340),
            "tint": (104, 106, 118),
            "accent": (150, 88, 176),
            "variant": 0,
        }
        regular = library.resolve_world("wall", **kwargs)
        self.assertIsNotNone(regular)
        assert regular is not None
        entry = library.manifest["world"]["wall"]
        entry["reference_width"] = 80
        try:
            library.clear_derived_caches()
            narrowed = library.resolve_world("wall", **kwargs)
            self.assertIsNotNone(narrowed)
            assert narrowed is not None
            self.assertLess(
                narrowed[0].get_bounding_rect(min_alpha=1).width,
                regular[0].get_bounding_rect(min_alpha=1).width,
            )
        finally:
            entry.pop("reference_width", None)
            library.clear_derived_caches()

    def test_door_direction_follows_all_room_boundary_sides(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.dungeon.rooms = [Room(10, 10, 5, 5)]
            expected = {
                (12, 10): "north",
                (14, 10): "north-east",
                (14, 12): "east",
                (14, 14): "south-east",
                (12, 14): "south",
                (10, 14): "south-west",
                (10, 12): "west",
                (10, 10): "north-west",
            }
            self.assertEqual(
                {
                    position: game.door_render_direction(*position)
                    for position in expected
                },
                expected,
            )

    def test_directional_animation_and_resolved_frames_are_cached(self) -> None:
        atlas = SpriteAtlas()
        self.assertTrue(atlas.modern_graphics_active, atlas.assets.load_error)
        east = atlas.player_visual(
            "Warden", "run", 0.0, 0.0, direction="east"
        )
        east_again = atlas.player_visual(
            "Warden", "run", 0.0, 0.0, direction="east"
        )
        east_later = atlas.player_visual(
            "Warden", "run", 0.28, 0.28, direction="east"
        )
        west = atlas.player_visual(
            "Warden", "run", 0.0, 0.0, direction="west"
        )
        self.assertTrue(east.is_asset)
        self.assertIs(east.surface, east_again.surface)
        self.assertNotEqual(east.key, east_later.key)
        self.assertNotEqual(east.key, west.key)
        attack_start = atlas.player_visual(
            "Warden",
            "attack",
            0.0,
            0.0,
            direction="south",
            action_time=0.0,
            action_progress=0.0,
        )
        attack_recovery = atlas.player_visual(
            "Warden",
            "attack",
            0.0,
            0.0,
            direction="south",
            action_time=0.19,
            action_progress=0.95,
        )
        self.assertEqual(attack_start.key[-1], 0)
        self.assertEqual(attack_recovery.key[-1], 5)
        self.assertGreater(east.surface.get_height(), TILE_H)
        self.assertGreaterEqual(east.anchor[0], 0)
        self.assertGreaterEqual(east.anchor[1], 0)
        preview = atlas.item_preview("weapon", 36)
        self.assertIs(preview, atlas.item_preview("weapon", 36))
        wisp_idle = atlas.familiar_visual(0, 0.0, moving=False)
        wisp_idle_later = atlas.familiar_visual(0, 0.25, moving=False)
        self.assertNotEqual(wisp_idle.key, wisp_idle_later.key)
        stats = atlas.cache_stats()
        self.assertLessEqual(stats["resolved_frames"], 320)
        self.assertLessEqual(stats["actor_resolution_keys"], 512)
        self.assertEqual(stats["missing_resources"], 0)

    def test_player_action_ttl_drives_the_full_authored_clip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.set_player_action_visual("attack", 0.20)
            game.update_visual_effects(0.19)
            resolved_frames = []
            resolve_player_visual = game.sprites.player_visual

            def capture_frame(*args, **kwargs):
                frame = resolve_player_visual(*args, **kwargs)
                resolved_frames.append(frame)
                return frame

            with mock.patch.object(
                game.sprites,
                "player_visual",
                side_effect=capture_frame,
            ) as player_visual:
                game.draw_player(game.player)
            self.assertAlmostEqual(game.player_action_duration, 0.20)
            self.assertAlmostEqual(game.player_action_elapsed, 0.19)
            self.assertAlmostEqual(
                player_visual.call_args.kwargs["action_progress"],
                0.95,
            )
            self.assertEqual(resolved_frames[-1].key[-1], 5)
            game.update_visual_effects(0.02)
            self.assertEqual(game.player_action_state, "")
            self.assertEqual(game.player_action_duration, 0.0)

    def test_invalid_library_and_missing_actor_frame_fall_back_independently(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            atlas = SpriteAtlas(asset_root=Path(tmpdir))
            self.assertFalse(atlas.modern_graphics_active)
            fallback = atlas.player_visual("Warden", "idle", 0.0, 0.0)
            self.assertFalse(fallback.is_asset)

        atlas = SpriteAtlas()
        warden = atlas.assets.manifest["actors"]["warden"]
        warden["clips"] = {}
        warden["rotations"] = {"south": "actors/warden/missing.png"}
        with mock.patch.object(
            atlas.assets,
            "_resource",
            wraps=atlas.assets._resource,
        ) as resource:
            with self.assertLogs("arch_rogue.sprite_assets", level="WARNING"):
                fallback = atlas.player_visual("Warden", "idle", 0.0, 0.0)
            fallback_again = atlas.player_visual("Warden", "idle", 0.0, 0.0)
        unaffected = atlas.player_visual("Rogue", "idle", 0.0, 0.0)
        self.assertFalse(fallback.is_asset)
        self.assertFalse(fallback_again.is_asset)
        self.assertEqual(resource.call_count, 1)
        self.assertTrue(unaffected.is_asset)

    def test_malformed_manifest_shape_disables_assets_without_escaping(self) -> None:
        malformed = {
            "format_version": 1,
            "actors": {
                "broken": {
                    "source_anchor": [32, 48],
                    "reference_height": 48,
                    "target_height": 96,
                    "rotations": list(DIRECTIONS),
                }
            },
            "items": {},
            "props": {},
            "world": {},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "manifest.json").write_text(
                json.dumps(malformed),
                encoding="utf-8",
            )
            library = AssetSpriteLibrary(root)
        self.assertFalse(library.available)
        self.assertIn("rotation map", library.load_error)

        malformed["actors"] = {}
        malformed["items"] = {
            "broken": {
                "path": "items/missing.png",
                "aliases": None,
            }
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "manifest.json").write_text(
                json.dumps(malformed),
                encoding="utf-8",
            )
            library = AssetSpriteLibrary(root)
        self.assertFalse(library.available)
        self.assertIn("alias list", library.load_error)

    def test_partial_actor_clip_uses_matching_rotation_fallback(self) -> None:
        manifest = json.loads(json.dumps(AssetSpriteLibrary().manifest))
        manifest["actors"]["warden"]["clips"]["run"]["directions"].pop("east")
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "manifest.json").write_text(
                json.dumps(manifest),
                encoding="utf-8",
            )
            partial = AssetSpriteLibrary(root)
        self.assertTrue(partial.available, partial.load_error)

        atlas = SpriteAtlas()
        directions = atlas.assets.manifest["actors"]["warden"]["clips"]["run"][
            "directions"
        ]
        removed = directions.pop("east")
        try:
            frame = atlas.player_visual(
                "Warden", "run", 0.0, 0.0, direction="east"
            )
            self.assertTrue(frame.is_asset)
            self.assertEqual(frame.key[2], "rotation")
            self.assertEqual(frame.key[3], "east")
        finally:
            directions["east"] = removed
            atlas.assets.clear_derived_caches()

    def test_modern_world_preserves_canonical_canvases_and_legacy_toggle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            margin = 4 * WORLD_SCALE
            flat_size = (TILE_W + margin * 2, TILE_H + margin * 2)
            stair_size = (TILE_W + margin * 2, TILE_W + margin * 2)
            tall_size = (
                TILE_W + margin * 2,
                TILE_H + 48 * WORLD_SCALE + margin * 2,
            )
            floor, floor_x, floor_y = game.tile_surface(Tile.FLOOR, 0)
            wall, wall_x, wall_y = game.tile_surface(Tile.WALL, 0)
            stairs, stairs_x, stairs_y = game.tile_surface(Tile.STAIRS, 0)
            closed = game.door_tile_surface(Tile.CLOSED_DOOR, 0, "left")
            opened = game.door_tile_surface(Tile.OPEN_DOOR, 0, "left")
            self.assertEqual(floor.get_size(), flat_size)
            self.assertEqual(stairs.get_size(), stair_size)
            self.assertEqual(wall.get_size(), tall_size)
            self.assertEqual((floor_x, floor_y), (flat_size[0] // 2, margin + TILE_H // 2))
            self.assertEqual(
                (stairs_x, stairs_y),
                (stair_size[0] // 2, margin + TILE_W * 5 // 8),
            )
            self.assertEqual((wall_x, wall_y), (tall_size[0] // 2, margin + 48 * WORLD_SCALE + TILE_H // 2))
            self.assertEqual(closed[0].get_size(), tall_size)
            self.assertEqual(opened[0].get_size(), tall_size)
            self.assertNotEqual(
                pygame.image.tobytes(closed[0], "RGBA"),
                pygame.image.tobytes(opened[0], "RGBA"),
            )
            for surface in (floor, wall, stairs, closed[0], opened[0]):
                bounds = surface.get_bounding_rect(min_alpha=1)
                self.assertGreaterEqual(bounds.left, 2)
                self.assertGreaterEqual(bounds.top, 2)
                self.assertLessEqual(bounds.right, surface.get_width() - 2)
                self.assertLessEqual(bounds.bottom, surface.get_height() - 2)

            asset_player = game.sprites.player_visual("Warden", "idle", 0.0, 0.0)
            self.assertTrue(asset_player.is_asset)
            north = game.door_tile_surface(Tile.CLOSED_DOOR, 0, "north")[0]
            south = game.door_tile_surface(Tile.CLOSED_DOOR, 0, "south")[0]
            north_west = game.door_tile_surface(
                Tile.CLOSED_DOOR, 0, "north-west"
            )[0]
            south_east = game.door_tile_surface(
                Tile.CLOSED_DOOR, 0, "south-east"
            )[0]
            east = game.door_tile_surface(Tile.CLOSED_DOOR, 0, "east")[0]
            west = game.door_tile_surface(Tile.CLOSED_DOOR, 0, "west")[0]
            north_east = game.door_tile_surface(
                Tile.CLOSED_DOOR, 0, "north-east"
            )[0]
            south_west = game.door_tile_surface(
                Tile.CLOSED_DOOR, 0, "south-west"
            )[0]
            for paired in (south, north_west, south_east):
                self.assertIs(north, paired)
            for paired in (west, north_east, south_west):
                self.assertIs(east, paired)
            self.assertIsNot(north, east)
            self.assertEqual(
                len(game.door_tile_cache),
                2 * DUNGEON_WALL_VARIANTS * 2,
            )
            game.set_legacy_graphics(True)
            legacy_player = game.sprites.player_visual("Warden", "idle", 0.0, 0.0)
            self.assertFalse(legacy_player.is_asset)
            self.assertGreater(len(game.tile_cache), 0)
            self.assertEqual(
                len(game.door_tile_cache),
                2 * DUNGEON_WALL_VARIANTS * 2,
            )
            self.assertIs(
                game.door_tile_surface(Tile.CLOSED_DOOR, 0, "north-west")[0],
                game.door_tile_surface(Tile.CLOSED_DOOR, 0, "left")[0],
            )

    def test_graphics_option_scrolls_persists_and_stays_out_of_run_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir, (640, 480))
            game.set_legacy_graphics(True)
            options = json.loads(game.options_path.read_text(encoding="utf-8"))
            self.assertEqual(options["schema_version"], 4)
            self.assertTrue(options["legacy_graphics"])
            game.legacy_graphics = False
            self.assertTrue(game.load_options())
            self.assertTrue(game.legacy_graphics)
            self.assertTrue(game.sprites.legacy_graphics)

            run_data = game.serialize_run_state()
            self.assertEqual(run_data["version"], 5)
            self.assertNotIn("legacy_graphics", run_data)
            self.assertNotIn("sprite", json.dumps(run_data).casefold())
            self.assertTrue(run_data["enemies"])
            self.assertNotIn("locomotion_anim_scale", run_data["enemies"][0])
            self.assertNotIn(
                "pending_locomotion_scale", run_data["enemies"][0]
            )
            self.assertNotIn(
                "pending_locomotion_anim_scale", run_data["enemies"][0]
            )

            game.state = "options"
            game.ui_scale = 4
            game.rebuild_fonts()
            game.options_cursor = game.OPTIONS_ROW_BACK
            game.options_scroll = 0
            game.draw()
            self.assertGreater(game.options_scroll, 0)
            self.assertLessEqual(
                game._options_visible_range[0], game.OPTIONS_ROW_BACK
            )
            self.assertGreater(
                game._options_visible_range[1], game.OPTIONS_ROW_BACK
            )
            self.assertTrue(game.screen.get_rect().contains(game._options_row_viewport))
            self.assertGreater(game._options_row_font_height, 0)
            self.assertLessEqual(game._options_row_font_height, 28)
            self.assertTrue(
                game.screen.get_rect().contains(game._options_selected_row_rect)
            )
            self.assertGreaterEqual(
                game._options_selected_row_rect.height,
                game._options_row_font_height,
            )

    def test_normal_map_cache_is_bounded_and_identity_safe(self) -> None:
        atlas = SpriteAtlas()
        first_surface = pygame.Surface((16, 16), pygame.SRCALPHA)
        first_surface.fill((120, 100, 140, 255))
        first_normal = atlas.normal_map_for(first_surface)
        self.assertIsNotNone(first_normal)
        self.assertIs(atlas.normal_map_for(first_surface), first_normal)

        surfaces = [first_surface]
        for index in range(321):
            width = 12 + index % 17
            height = 13 + index % 19
            surface = pygame.Surface((width, height), pygame.SRCALPHA)
            surfaces.append(surface)
            pygame.draw.rect(
                surface,
                (80 + index % 120, 100, 140, 255),
                (1, 1, width - 2, height - 2),
            )
            normal = atlas.normal_map_for(surface)
            self.assertIsNotNone(normal)
            if normal is None:
                continue
            long_side = max(width, height)
            if long_side > LIGHT_SHADE_DOWNSAMPLE_LONG:
                factor = LIGHT_SHADE_DOWNSAMPLE_LONG / long_side
                expected = (
                    max(1, int(width * factor)),
                    max(1, int(height * factor)),
                )
            else:
                expected = (width, height)
            self.assertEqual(normal.get_size(), expected)

        self.assertLessEqual(atlas.cache_stats()["normal_maps"], 320)
        rebuilt = atlas.normal_map_for(first_surface)
        self.assertIsNotNone(rebuilt)
        self.assertIsNot(rebuilt, first_normal)
        self.assertIs(atlas.normal_map_for(first_surface), rebuilt)

    def test_full_modern_frame_renders_without_resource_misses(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            game = self.make_game(tmpdir)
            game.draw()
            self.assertTrue(game.sprites.modern_graphics_active)
            self.assertEqual(game.sprites.cache_stats()["missing_resources"], 0)
            self.assertGreater(len(game.tile_cache), 0)
            self.assertGreater(len(game.door_tile_cache), 0)


if __name__ == "__main__":
    unittest.main()
