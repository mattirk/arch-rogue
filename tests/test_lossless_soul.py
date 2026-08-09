"""Lossless Soul hall: placement, population, assets, dialogue, and saves."""

from __future__ import annotations

import copy
import os
import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys_path_root = Path(__file__).resolve().parents[1] / "src"
import sys

sys.path.insert(0, str(sys_path_root))

from arch_rogue.constants import TILE_W
from arch_rogue.content import ARCHETYPES
from arch_rogue.dungeon import (
    LOSSLESS_SOUL_ROOM_KIND,
    SOLID_FURNISHING_ANCHOR_KEYS,
    SPECIAL_ROOM_DEFINITIONS,
    Dungeon,
)
from arch_rogue.game import Game
from arch_rogue.models import LightSource, Tile
from arch_rogue.population import PopulationMixin
from arch_rogue.story import load_quest_cutscene_library

PROP_ANCHOR_KEYS = (
    "soul_mirror",
    "soul_chimes",
    "soul_brazier",
    "soul_reliquary",
)


def _room_contains(room, x: float, y: float) -> bool:
    return room.x <= x < room.x + room.w and room.y <= y < room.y + room.h


class _SoulPopulationHarness(PopulationMixin):
    def __init__(self, dungeon: Dungeon) -> None:
        self.dungeon = dungeon
        self.idle_npcs = []
        self.enemies: list[SimpleNamespace] = []
        self.items: list[SimpleNamespace] = []
        self.traps: list[SimpleNamespace] = []
        self.shrines: list[SimpleNamespace] = []
        self.secrets: list[SimpleNamespace] = []
        self.shopkeepers: list[SimpleNamespace] = []
        self.story_guests: list[SimpleNamespace] = []
        self.familiars: list[SimpleNamespace] = []
        self.player: SimpleNamespace | None = None
        self.rng = random.Random(0)


class LosslessSoulTests(unittest.TestCase):
    def test_definition_is_a_sealed_safe_flavor_hall(self) -> None:
        definition = SPECIAL_ROOM_DEFINITIONS[LOSSLESS_SOUL_ROOM_KIND]
        self.assertEqual(definition.display_name, "Hall of Unlost Echoes")
        self.assertEqual(definition.door_policy, "sealed")
        # Unlike bar/garden the hall hosts a dialogue NPC, so hostiles clear.
        self.assertEqual(definition.spawn_policy, "safe")
        self.assertIn("flavor", definition.tags)
        self.assertIn("soul", definition.tags)
        self.assertEqual(definition.placement.chance, 0.50)
        self.assertEqual(definition.placement.rng_stream, "flavor")

    def test_hall_spawns_around_50_percent_and_never_collides(self) -> None:
        found = 0
        total = 0
        for seed in range(40, 280):
            dungeon = Dungeon(random.Random(seed), guest_room=True)
            total += 1
            kinds = {room.kind for room in dungeon.special_rooms}
            if LOSSLESS_SOUL_ROOM_KIND in kinds:
                found += 1
            room_indexes = [room.room_index for room in dungeon.special_rooms]
            self.assertEqual(len(room_indexes), len(set(room_indexes)))
            self.assertNotIn(0, room_indexes)
            self.assertNotIn(len(dungeon.rooms) - 1, room_indexes)
        ratio = found / total
        self.assertGreater(ratio, 0.30, f"soul hall ratio {ratio:.2f} too low")
        self.assertLess(ratio, 0.70, f"soul hall ratio {ratio:.2f} too high")

    def test_population_places_one_keeper_and_furnishings(self) -> None:
        seed = next(
            candidate
            for candidate in range(1, 500)
            if Dungeon(
                random.Random(candidate), guest_room=True
            ).special_room_for_kind(LOSSLESS_SOUL_ROOM_KIND)
            is not None
        )
        dungeon = Dungeon(random.Random(seed), guest_room=True)
        special = dungeon.special_room_for_kind(LOSSLESS_SOUL_ROOM_KIND)
        assert special is not None
        room = dungeon.rooms[special.room_index]
        harness = _SoulPopulationHarness(dungeon)
        before = harness.rng.getstate()
        handler = harness._special_room_handlers()[LOSSLESS_SOUL_ROOM_KIND]
        handler(special, room)
        # Population never advances the shared gameplay RNG stream.
        self.assertEqual(harness.rng.getstate(), before)

        keepers = [npc for npc in harness.idle_npcs if npc.kind == "lossless_soul"]
        self.assertEqual(len(keepers), 1)
        self.assertEqual(keepers[0].name, "Lossless Soul")
        self.assertEqual(keepers[0].role, "Keeper of Unlost Memory")
        self.assertTrue(_room_contains(room, keepers[0].x, keepers[0].y))
        for key in PROP_ANCHOR_KEYS + ("lossless_soul",):
            anchor = special.anchor(key)
            self.assertIsNotNone(anchor, f"missing anchor {key}")
            assert anchor is not None
            self.assertTrue(_room_contains(room, anchor[0] + 0.5, anchor[1] + 0.5))
        # Furnishings and keeper never share a tile.
        anchors = [special.anchor(key) for key in PROP_ANCHOR_KEYS]
        self.assertNotIn(special.anchor("lossless_soul"), anchors)

        # Re-running the handler is idempotent.
        populated = [
            (npc.kind, npc.name, npc.x, npc.y) for npc in harness.idle_npcs
        ]
        handler(special, room)
        self.assertEqual(
            [(npc.kind, npc.name, npc.x, npc.y) for npc in harness.idle_npcs],
            populated,
        )

    def test_safe_spawn_policy_clears_hostiles_centrally(self) -> None:
        seed = next(
            candidate
            for candidate in range(1, 500)
            if Dungeon(
                random.Random(candidate), guest_room=True
            ).special_room_for_kind(LOSSLESS_SOUL_ROOM_KIND)
            is not None
        )
        dungeon = Dungeon(random.Random(seed), guest_room=True)
        special = dungeon.special_room_for_kind(LOSSLESS_SOUL_ROOM_KIND)
        assert special is not None
        room = dungeon.rooms[special.room_index]
        harness = _SoulPopulationHarness(dungeon)
        cx, cy = room.center
        harness.enemies = [SimpleNamespace(x=cx + 0.5, y=cy + 0.5)]
        harness.traps = [SimpleNamespace(x=cx + 1.5, y=cy + 0.5)]
        self.assertTrue(harness._run_special_room_handler(special, room))
        self.assertEqual(harness.enemies, [])
        self.assertEqual(harness.traps, [])

    def test_sprite_assets_are_complete_and_beat_addressable(self) -> None:
        game = self._make_game_with_soul_hall()
        try:
            library = game.sprites.assets
            entry = library.manifest["actors"]["lossless_soul"]
            self.assertEqual(entry["source_canvas"], [244, 244])
            self.assertEqual(entry["target_height"], 176)
            self.assertEqual(len(entry["rotations"]), 8)
            self.assertEqual(set(entry["clips"]), {"walk", "dance"})
            for clip_name, frame_count in (("walk", 6), ("dance", 8)):
                directions = entry["clips"][clip_name]["directions"]
                self.assertEqual(len(directions), 8)
                for frames in directions.values():
                    self.assertEqual(len(frames), frame_count)

            # Beat progress addresses dance frames deterministically.
            for progress, expected in ((0.0, 0), (0.25, 2), (0.5, 4), (0.75, 6)):
                frame = game.sprites.lossless_soul_visual(
                    0.0,
                    direction="south",
                    dancing=True,
                    clip_progress=progress,
                )
                self.assertTrue(frame.is_asset)
                self.assertEqual(frame.key[1], "lossless_soul")
                self.assertEqual(frame.key[2], "dance")
                self.assertEqual(frame.key[4], expected)

            # Furnishing sprites resolve from the manifest, and each block
            # prop reads as substantial furniture: the shared 128px pedestal
            # template scales so the base spans roughly 3/5 of the tile
            # diamond, anchored on the footprint center.
            for anchor_key in PROP_ANCHOR_KEYS:
                frame = game.sprites.lossless_soul_prop_visual(anchor_key)
                self.assertIsNotNone(frame, f"prop for {anchor_key} missing")
                assert frame is not None
                self.assertGreaterEqual(
                    frame.surface.get_width(),
                    int(TILE_W * 0.50),
                    f"{anchor_key} shrank back to the undersized 4.8.6 look",
                )
                self.assertLessEqual(
                    frame.surface.get_width(),
                    int(TILE_W * 0.75),
                    f"{anchor_key} overwhelms its floor tile",
                )

            # Distinct interior floor and wall-face art is registered.
            special = game.dungeon.special_room_for_kind(LOSSLESS_SOUL_ROOM_KIND)
            assert special is not None
            room = game.dungeon.rooms[special.room_index]
            interior_hits = sum(
                1
                for x in range(room.x + 1, room.x + room.w - 1)
                for y in range(room.y + 1, room.y + room.h - 1)
                if game.dungeon.tiles[x][y] == Tile.FLOOR
                and game.special_room_floor_kind(x, y) == LOSSLESS_SOUL_ROOM_KIND
            )
            self.assertGreater(interior_hits, 0)
            found_face = False
            for x in range(room.x - 1, room.x + room.w + 1):
                for y in range(room.y - 1, room.y + room.h + 1):
                    if not game.dungeon.in_bounds(x, y):
                        continue
                    if game.dungeon.tiles[x][y] != Tile.WALL:
                        continue
                    style = game.special_wall_faces(x, y)
                    if style and style.startswith("lossless_soul:"):
                        found_face = True
            self.assertTrue(found_face)
        finally:
            game._soul_tmpdir.cleanup()

    def test_dialogue_flow_tailors_to_story_and_persists_choice(self) -> None:
        game = self._make_game_with_soul_hall()
        try:
            special = game.dungeon.special_room_for_kind(LOSSLESS_SOUL_ROOM_KIND)
            assert special is not None
            keeper = next(
                npc for npc in game.idle_npcs if npc.kind == "lossless_soul"
            )
            game.story_intro_pending = False
            game.close_active_cutscene()
            game.player.x, game.player.y = keeper.x + 0.8, keeper.y

            hint = game.current_interaction_hint()
            self.assertIsNotNone(hint)
            assert hint is not None
            self.assertIn("Lossless Soul", hint[1])

            game.interact()
            self.assertIsNotNone(game.active_cutscene)
            assert game.active_cutscene is not None
            self.assertEqual(
                game.active_cutscene.asset_id, "lossless_soul_reflection"
            )
            self.assertEqual(game.active_cutscene.node_id, "reflection")
            # No beat resolved yet: her memory line admits it (4.9 voice —
            # the keeper is Liss Voss, though she doesn't say so yet).
            self.assertIn(
                "You have finished nothing yet",
                game.active_cutscene_text(),
            )
            labels = [c.label for c in game.active_cutscene_choices()]
            self.assertEqual(
                labels,
                ["Preserve it exactly", "Release its hold", "Refuse the mirror"],
            )

            # 4.9.1: the reflection choices unlock after the short Soul
            # interlude. A loss withholds its refill but never blocks the
            # existing Preserve / Release / Refuse audience.
            mini_game = game.active_mini_game
            self.assertIsNotNone(mini_game)
            assert mini_game is not None
            mini_game.phase = "result"
            mini_game.outcome = "lost"
            mini_game.result_time = 0.0
            self.assertTrue(game.update_active_mini_game(0.01))
            self.assertIsNone(game.active_mini_game)

            echo_before = game.story_state.effects.get("healing_echo", 0.0)
            self.assertTrue(game.choose_active_cutscene_option(0))
            self.assertEqual(special.state.get("soul_choice"), "preserve")
            self.assertTrue(special.state.get("soul_met"))
            self.assertEqual(game.active_cutscene.node_id, "settled")
            game.reveal_active_cutscene_narration()
            self.assertIn("keeps your memory whole", game.active_cutscene_text())
            self.assertIn(
                f"{game.current_depth}:soul:preserve", game.story_state.flags
            )
            self.assertAlmostEqual(
                game.story_state.effects.get("healing_echo", 0.0),
                echo_before + 0.05,
            )
            game.advance_active_cutscene()
            self.assertIsNone(game.active_cutscene)

            # Re-visiting an answered hall goes straight to the settled node.
            game.interact()
            assert game.active_cutscene is not None
            self.assertEqual(game.active_cutscene.node_id, "settled")
            game.close_active_cutscene()

            # The answered state and the keeper survive a save round trip.
            data = copy.deepcopy(game.serialize_run_state())
            with tempfile.TemporaryDirectory() as tmpdir:
                loaded = Game(
                    screen_size=(820, 540),
                    headless=True,
                    save_path=Path(tmpdir) / "soul.json",
                )
                loaded.options_path = Path(tmpdir) / "soul-opt.json"
                loaded.restore_run_state(data)
                restored = loaded.dungeon.special_room_for_kind(
                    LOSSLESS_SOUL_ROOM_KIND
                )
                assert restored is not None
                self.assertEqual(restored.state.get("soul_choice"), "preserve")
                self.assertEqual(
                    sum(npc.kind == "lossless_soul" for npc in loaded.idle_npcs),
                    1,
                )
        finally:
            game._soul_tmpdir.cleanup()

    def test_pre_4_8_6_save_backfills_keeper_and_furnishings(self) -> None:
        game = self._make_game_with_soul_hall()
        try:
            data = copy.deepcopy(game.serialize_run_state())
            data["idle_npcs"] = [
                npc
                for npc in data["idle_npcs"]
                if npc.get("kind") != "lossless_soul"
            ]
            soul_data = next(
                room
                for room in data["dungeon"]["special_rooms"]
                if room.get("kind") == LOSSLESS_SOUL_ROOM_KIND
            )
            removed = [
                soul_data["anchor_points"].pop(key)
                for key in PROP_ANCHOR_KEYS + ("lossless_soul",)
            ]
            soul_data["reserved_tiles"] = [
                tile
                for tile in soul_data["reserved_tiles"]
                if tile not in removed
            ]

            with tempfile.TemporaryDirectory() as tmpdir:
                loaded = Game(
                    screen_size=(820, 540),
                    headless=True,
                    save_path=Path(tmpdir) / "pre-soul.json",
                )
                loaded.options_path = Path(tmpdir) / "pre-soul-opt.json"
                loaded.restore_run_state(data)
                keepers = [
                    npc
                    for npc in loaded.idle_npcs
                    if npc.kind == "lossless_soul"
                ]
                self.assertEqual(len(keepers), 1)
                self.assertEqual(keepers[0].name, "Lossless Soul")
                restored = loaded.dungeon.special_room_for_kind(
                    LOSSLESS_SOUL_ROOM_KIND
                )
                assert restored is not None
                for key in PROP_ANCHOR_KEYS + ("lossless_soul",):
                    self.assertIsNotNone(restored.anchor(key))
                # Backfilled anchors feed the collision set too (the floor
                # may also carry bar furnishings in the same set).
                self.assertLessEqual(
                    {
                        tuple(restored.anchor(key))
                        for key in PROP_ANCHOR_KEYS
                    },
                    loaded.dungeon.solid_furnishing_tiles,
                )
        finally:
            game._soul_tmpdir.cleanup()

    def test_furnishing_tiles_block_movement_probes(self) -> None:
        # The solid-anchor registry covers population's placement lists.
        self.assertEqual(
            frozenset(PopulationMixin._LOSSLESS_SOUL_PROP_ANCHORS)
            | frozenset(PopulationMixin._BAR_BARREL_ANCHORS)
            | frozenset(PopulationMixin._BAR_TABLE_ANCHORS),
            SOLID_FURNISHING_ANCHOR_KEYS,
        )
        game = self._make_game_with_soul_hall()
        try:
            special = game.dungeon.special_room_for_kind(LOSSLESS_SOUL_ROOM_KIND)
            assert special is not None
            expected_tiles = set()
            for key in PROP_ANCHOR_KEYS:
                anchor = special.anchor(key)
                assert anchor is not None
                ax, ay = anchor
                expected_tiles.add((ax, ay))
                # Solid for every physical probe (player and enemy paths)...
                self.assertTrue(
                    game.dungeon.blocked_for_radius(ax + 0.5, ay + 0.5, 0.27),
                    f"{key} tile should block movement",
                )
                self.assertTrue(
                    game.dungeon.blocked_for_radius(
                        ax + 0.5, ay + 0.5, 0.27, block_stairs=True
                    ),
                    f"{key} tile should block the player probe",
                )
                # ...but transparent to LOS and projectiles.
                self.assertTrue(game.dungeon.is_floor(ax + 0.5, ay + 0.5))
                # The physical box is shifted north-west and inset (the
                # stairs treatment), aligning with the drawn pedestal as the
                # grounded player's feet meet it. Since 5.0 the pedestal art
                # anchors its base on the special-floor contact line (the
                # sprite sits ~7 logical px further south than 4.9), so the
                # box shift shrank with it (-0.21875 per axis): the box core
                # blocks, it reaches the tile's own north edge but no longer
                # spills into the north neighbor, and the tile's southern
                # strip stays walkable floor in front of the pedestal.
                self.assertTrue(
                    game.dungeon._probe_hits_solid_furnishing(
                        ax + 0.05, ay + 0.05
                    )
                )
                self.assertTrue(
                    game.dungeon._probe_hits_solid_furnishing(
                        ax + 0.45, ay + 0.05
                    ),
                    f"{key} box should cover the tile's north half",
                )
                self.assertFalse(
                    game.dungeon._probe_hits_solid_furnishing(
                        ax + 0.2, ay - 0.2
                    ),
                    f"{key} box should stay out of the north neighbor",
                )
                self.assertFalse(
                    game.dungeon._probe_hits_solid_furnishing(
                        ax + 0.5, ay + 0.7
                    ),
                    f"{key} south floor strip should stay walkable",
                )
                self.assertFalse(
                    game.dungeon._probe_hits_solid_furnishing(
                        ax + 0.5, ay - 0.5
                    ),
                    f"{key} north neighbor center should stay walkable",
                )
            # The hall's tiles are all present; the same floor may also
            # carry bar furnishings in the shared set.
            self.assertLessEqual(
                expected_tiles, game.dungeon.solid_furnishing_tiles
            )
            # The keeper's own tile stays walkable.
            keeper_anchor = special.anchor("lossless_soul")
            assert keeper_anchor is not None
            self.assertFalse(
                game.dungeon.blocked_for_radius(
                    keeper_anchor[0] + 0.5, keeper_anchor[1] + 0.5, 0.27
                )
            )
        finally:
            game._soul_tmpdir.cleanup()

    def test_each_furnishing_casts_a_static_memory_light(self) -> None:
        game = self._make_game_with_soul_hall()
        try:
            special = game.dungeon.special_room_for_kind(LOSSLESS_SOUL_ROOM_KIND)
            assert special is not None
            room = game.dungeon.rooms[special.room_index]

            def soul_lights():
                return [
                    src for src in game.light_sources if src.kind == "soul_prop"
                ]

            expected = set()
            for key in PROP_ANCHOR_KEYS:
                anchor = special.anchor(key)
                assert anchor is not None
                expected.add((anchor[0] + 0.5, anchor[1] + 0.5))
            self.assertEqual(
                {(src.x, src.y) for src in soul_lights()}, expected
            )
            brazier = special.anchor("soul_brazier")
            assert brazier is not None
            for src in soul_lights():
                # Only the brazier's flame flickers; the others hold steady.
                self.assertEqual(
                    src.flicker,
                    (src.x, src.y) == (brazier[0] + 0.5, brazier[1] + 0.5),
                )

            # Reconciliation is idempotent and migrates the pre-4.8.6 hall
            # torch (the brazier light before kind="soul_prop" existed).
            game.light_sources.append(
                LightSource(
                    x=room.x + 1.5,
                    y=room.y + 1.5,
                    radius=2.6,
                    color=(120, 214, 205),
                    intensity=0.62,
                    ttl=None,
                    flicker=True,
                    kind="torch",
                )
            )
            game._reconcile_static_light_sources()
            game._reconcile_static_light_sources()
            self.assertEqual(
                {(src.x, src.y) for src in soul_lights()}, expected
            )
            self.assertFalse(
                [
                    src
                    for src in game.light_sources
                    if src.kind == "torch"
                    and room.x <= src.x < room.x + room.w
                    and room.y <= src.y < room.y + room.h
                ],
                "legacy hall torch should be dropped on reconcile",
            )
        finally:
            game._soul_tmpdir.cleanup()

    def test_furnishings_never_stand_inside_a_doorway(self) -> None:
        halls = shifted = 0
        for seed in range(1, 400):
            dungeon = Dungeon(random.Random(seed), guest_room=True)
            special = dungeon.special_room_for_kind(LOSSLESS_SOUL_ROOM_KIND)
            if special is None:
                continue
            halls += 1
            room = dungeon.rooms[special.room_index]
            harness = _SoulPopulationHarness(dungeon)
            harness._populate_lossless_soul_special_room(special, room)
            # Independent derivation of the tiles just inside each doorway.
            door_fronts = set()
            for x in range(room.x, room.x + room.w):
                for y in range(room.y, room.y + room.h):
                    if dungeon.tiles[x][y] not in (
                        Tile.CLOSED_DOOR,
                        Tile.OPEN_DOOR,
                    ):
                        continue
                    for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                        tile = (x + ox, y + oy)
                        if (
                            room.x < tile[0] < room.x + room.w - 1
                            and room.y < tile[1] < room.y + room.h - 1
                        ):
                            door_fronts.add(tile)
            cx, _cy = room.center
            top = room.y + 1
            ideal = {
                "soul_mirror": (cx, top),
                "soul_chimes": (max(room.x + 1, cx - 2), top),
                "soul_brazier": (room.x + 2, room.y + 2),
                "soul_reliquary": (
                    room.x + room.w - 3,
                    room.y + room.h // 2,
                ),
            }
            seen = set()
            for key in PROP_ANCHOR_KEYS:
                anchor = special.anchor(key)
                assert anchor is not None
                self.assertNotIn(
                    anchor,
                    door_fronts,
                    f"seed {seed}: {key} walls off a doorway at {anchor}",
                )
                self.assertNotIn(anchor, seen, f"seed {seed}: {key} overlaps")
                seen.add(anchor)
                self.assertTrue(
                    _room_contains(room, anchor[0] + 0.5, anchor[1] + 0.5)
                )
                if anchor != ideal[key]:
                    shifted += 1
        self.assertGreater(halls, 50)
        # The sweep must actually exercise the slide-aside fallback.
        self.assertGreater(shifted, 0)

    def test_restore_moves_player_off_solid_furnishing_tile(self) -> None:
        game = self._make_game_with_soul_hall()
        try:
            special = game.dungeon.special_room_for_kind(LOSSLESS_SOUL_ROOM_KIND)
            assert special is not None
            mirror = special.anchor("soul_mirror")
            assert mirror is not None
            data = copy.deepcopy(game.serialize_run_state())
            # A save written while furnishing tiles were walkable can leave
            # the player standing inside a prop.
            data["player"]["x"] = mirror[0] + 0.5
            data["player"]["y"] = mirror[1] + 0.5

            with tempfile.TemporaryDirectory() as tmpdir:
                loaded = Game(
                    screen_size=(820, 540),
                    headless=True,
                    save_path=Path(tmpdir) / "stuck-soul.json",
                )
                loaded.options_path = Path(tmpdir) / "stuck-soul-opt.json"
                loaded.restore_run_state(data)
                player_tile = (int(loaded.player.x), int(loaded.player.y))
                self.assertNotIn(
                    player_tile, loaded.dungeon.solid_furnishing_tiles
                )
                self.assertFalse(
                    loaded.dungeon.blocked_for_radius(
                        loaded.player.x,
                        loaded.player.y,
                        0.27,
                        block_stairs=True,
                    )
                )
        finally:
            game._soul_tmpdir.cleanup()

    def test_cutscene_asset_declares_hall_stage(self) -> None:
        library = load_quest_cutscene_library()
        self.assertIn("lossless_soul_reflection", library)
        cutscene = library["lossless_soul_reflection"]
        self.assertEqual(cutscene.stage.backdrop, "lossless_soul")
        kinds = {prop.kind for prop in cutscene.stage.props}
        self.assertEqual(kinds, {"mirror", "chimes", "brazier", "reliquary"})
        self.assertEqual(cutscene.actors["soul"].sprite, "lossless_soul")
        node_ids = set(cutscene.nodes)
        self.assertEqual(node_ids, {"reflection", "settled"})
        actions = {
            choice.action for choice in cutscene.nodes["reflection"].choices
        }
        self.assertEqual(
            actions,
            {"lossless_preserve", "lossless_release", "lossless_refuse"},
        )

    def test_rendering_hall_and_cutscene_does_not_crash(self) -> None:
        game = self._make_game_with_soul_hall()
        try:
            special = game.dungeon.special_room_for_kind(LOSSLESS_SOUL_ROOM_KIND)
            assert special is not None
            room = game.dungeon.rooms[special.room_index]
            game.story_intro_pending = False
            game.close_active_cutscene()
            game.player.x = room.x + room.w / 2
            game.player.y = room.y + room.h / 2
            game.update_revealed_tiles()
            game.draw()
            frame = game.sprites.lossless_soul_visual(
                game.elapsed, dancing=True, clip_progress=0.0
            )
            self.assertTrue(frame.is_asset)
            keeper = next(
                npc for npc in game.idle_npcs if npc.kind == "lossless_soul"
            )
            game.player.x, game.player.y = keeper.x + 0.8, keeper.y
            game.interact()
            self.assertIsNotNone(game.active_cutscene)
            game.reveal_active_cutscene_narration()
            game.draw()
            game.close_active_cutscene()
        finally:
            game._soul_tmpdir.cleanup()

    # --- helpers --------------------------------------------------------

    def _make_game_with_soul_hall(self, *, seed: int = 3001) -> Game:
        tmp = tempfile.TemporaryDirectory()
        try:
            game = Game(
                screen_size=(960, 600),
                headless=True,
                save_path=Path(tmp.name) / f"soul-{seed}.json",
            )
            game.options_path = Path(tmp.name) / f"soul-opt-{seed}.json"
            game.rng.seed(seed)
            game.restart(ARCHETYPES[2])
            self.assertIsNotNone(
                game.dungeon.special_room_for_kind(LOSSLESS_SOUL_ROOM_KIND),
                f"seed {seed} no longer generates a soul hall on depth 1",
            )
            self.assertEqual(
                sum(npc.kind == "lossless_soul" for npc in game.idle_npcs), 1
            )
            game._soul_tmpdir = tmp  # type: ignore[attr-defined]
            return game
        except Exception:
            tmp.cleanup()
            raise


if __name__ == "__main__":
    unittest.main()
