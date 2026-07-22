# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
#
# AI Provenance & Liability Notice:
# This repository contains code generated, assisted, or refactored by Artificial
# Intelligence models. Provided strictly "AS IS" under Apache 2.0 with no warranty
# of clean IP provenance or non-infringement; downstream users assume all legal
# and financial risk and should perform their own compliance audits.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

import math
import random
from collections.abc import Callable

from .constants import (
    DUNGEON_DEPTH,
    LIGHT_BAR_WALL_ELEVATION,
    LIGHT_SHRINE_INTENSITY,
    LIGHT_SHRINE_RADIUS,
    LIGHT_STAIRS_COLOR,
    LIGHT_STAIRS_INTENSITY,
    LIGHT_STAIRS_RADIUS,
    LIGHT_TORCH_COLOR,
    LIGHT_TORCH_INTENSITY,
    LIGHT_TORCH_RADIUS,
)
from .content import (
    AFFIX_DEFINITIONS,
    ARMOR_DEFINITIONS,
    ELITE_MODIFIERS,
    ENEMY_DEFINITIONS,
    FINAL_ROOM_ENEMY_DEFINITIONS,
    RARITY_AFFIX_COUNTS,
    RARITY_AFFIX_ROLL_RANGES,
    SECRET_TYPES,
    SHRINE_HINTS,
    SHRINE_TYPES,
    TRAP_DEFINITIONS,
    UNIQUE_ITEM_DEFINITIONS,
    WEAPON_DEFINITIONS,
    AffixDefinition,
    EnemyDefinition,
    UniqueItemDefinition,
)
from .models import (
    Color,
    Enemy,
    IdleNpc,
    Item,
    LightSource,
    Room,
    SecretCache,
    Shopkeeper,
    Shrine,
    SpecialRoom,
    Tile,
    Trap,
)

SpecialRoomHandler = Callable[[SpecialRoom, Room], None]


class PopulationMixin:
    def _populate_dungeon(self) -> None:
        final_room_index = len(self.dungeon.rooms) - 1
        floor_plan = self.current_floor_plan()
        encounter = self.encounter_template_by_key(
            floor_plan.encounter_key if floor_plan is not None else "standard"
        )
        difficulty = self.difficulty_profile()
        enemy_pressure = self.story_effect_value("enemy_pressure", -0.35, 0.45)
        loot_bonus = self.story_effect_value("loot_bonus", -0.2, 0.35)
        trap_bonus = self.story_effect_value("trap_bonus", -0.1, 0.28)
        shrine_bonus = self.story_effect_value("shrine_bonus", -0.1, 0.28)
        secret_bonus = self.story_effect_value("secret_bonus", -0.1, 0.28)
        hunter_pressure = self.story_effect_value("hunter_pressure", 0.0, 0.35)
        for room_index, room in enumerate(self.dungeon.rooms[1:], start=1):
            is_final_room = room_index == final_room_index
            count = self.rng.randrange(1, 4)
            if self.current_depth <= 2:
                count = max(1, count - 1)
            elif self.current_depth >= 8:
                count += 2
            elif self.current_depth >= 6:
                count += 1
            if enemy_pressure > 0 and self.rng.random() < enemy_pressure:
                count += 1
            elif enemy_pressure < 0 and self.rng.random() < abs(enemy_pressure):
                count = max(1, count - 1)
            if is_final_room:
                count += 1
            count = max(1, count + difficulty.enemy_count_bonus + encounter.enemy_bonus)
            if self.rng.random() < difficulty.enemy_extra_chance:
                count += 1
            for _ in range(count):
                self.enemies.append(
                    self._make_enemy(
                        *room.random_point(self.rng),
                        final_room=is_final_room,
                        elite_bonus=encounter.elite_bonus,
                    )
                )

            if is_final_room and floor_plan is not None and floor_plan.boss_key:
                bx, by = room.center
                if self.current_depth == DUNGEON_DEPTH:
                    self.enemies.append(self._make_boss(bx + 0.5, by + 0.5))
                else:
                    self.enemies.append(
                        self._make_floor_boss(floor_plan.boss_key, bx + 0.5, by + 0.5)
                    )

            loot_chance = max(
                0.12,
                min(
                    0.88,
                    0.68
                    + self.run_modifier.loot_bonus
                    + loot_bonus
                    + difficulty.loot_chance_bonus
                    + encounter.loot_bonus,
                ),
            )
            # 4.2: loot drops are rarer across the board. The previous floor
            # spawn multiplier (0.5) already halved the base chance; trimming it
            # further to 0.42 makes exploration loot feel earned without starving
            # the player of drops entirely.
            loot_chance *= 0.42
            if self.rng.random() < loot_chance:
                self.items.append(self._make_loot(*room.random_point(self.rng)))
            if (
                room_index > 3
                and not is_final_room
                and self.rng.random() < self.miniboss_chance()
            ):
                mx, my = room.random_point(self.rng)
                self.enemies.append(self._make_miniboss(mx, my))
            if room_index > 1 and self.rng.random() < max(
                0.04,
                min(
                    0.70,
                    0.24
                    + self.run_modifier.trap_bonus
                    + trap_bonus
                    + difficulty.trap_chance_bonus
                    + encounter.trap_bonus,
                ),
            ):
                tx, ty = room.random_point(self.rng)
                kind, min_damage, max_damage = self.rng.choice(TRAP_DEFINITIONS)
                depth_damage = max(0, self.current_depth - 3)
                raw_damage = (
                    self.rng.randrange(min_damage, max_damage + 1) + depth_damage
                )
                self.traps.append(
                    Trap(
                        tx,
                        ty,
                        kind,
                        max(
                            1,
                            int(round(raw_damage * difficulty.trap_damage_multiplier)),
                        ),
                    )
                )
            shrine_chance = (
                0.18
                + (0.08 if self.run_modifier.name == "Trap-Laced" else 0.0)
                + shrine_bonus
                + difficulty.shrine_chance_bonus
            )
            if room_index > 2 and self.rng.random() < max(
                0.04, min(0.46, shrine_chance)
            ):
                sx, sy = room.random_point(self.rng)
                self.shrines.append(Shrine(sx, sy, self.rng.choice(SHRINE_TYPES)))
            if (
                room_index > 2
                and not is_final_room
                and self.rng.random()
                < max(
                    0.03,
                    min(
                        0.48,
                        0.16
                        + self.run_modifier.loot_bonus
                        + secret_bonus
                        + encounter.secret_bonus,
                    ),
                )
            ):
                cx, cy = room.random_point(self.rng)
                self.secrets.append(
                    SecretCache(
                        cx,
                        cy,
                        self.rng.choice(SECRET_TYPES),
                    )
                )

        if (
            encounter.guaranteed_miniboss
            and (floor_plan is None or not floor_plan.boss_key)
            and len(self.dungeon.rooms) > 3
        ):
            room = self.rng.choice(self.dungeon.rooms[2:-1] or self.dungeon.rooms[1:])
            mx, my = room.random_point(self.rng)
            miniboss = self._make_miniboss(mx, my)
            miniboss.role = "challenge_boss"
            miniboss.telegraph = (
                "optional challenge room guardian with guaranteed reward"
            )
            self.enemies.append(miniboss)

        if self.rng.random() < max(
            0.10,
            min(
                0.72,
                0.45
                + self.run_modifier.loot_bonus
                + secret_bonus
                + difficulty.loot_chance_bonus * 0.5,
            ),
        ):
            room = self.rng.choice(self.dungeon.rooms[2:-1])
            cx, cy = room.random_point(self.rng)
            self.secrets.append(SecretCache(cx, cy, "Lost Cartographer's Stash"))

        if hunter_pressure > 0 and len(self.dungeon.rooms) > 2:
            hunter_rooms = self.dungeon.rooms[2:-1] or self.dungeon.rooms[1:]
            hunter_count = min(4, 1 + int(hunter_pressure / 0.14))
            if self.rng.random() < min(0.75, hunter_pressure * 1.5):
                hunter_count += 1
            for _ in range(hunter_count):
                room = self.rng.choice(hunter_rooms)
                hx, hy = room.random_point(self.rng)
                self.enemies.append(self._make_story_hunter(hx, hy))

        sx, sy = self.dungeon.rooms[0].random_point(self.rng)
        self.items.append(
            Item("Minor Healing Potion", "potion", heal=35, rarity="Common", x=sx, y=sy)
        )
        self._populate_special_rooms()
        # Fallback for story floors generated without an assignable quest room.
        # If the quest-room handler already placed the guest, this is a no-op.
        self._populate_story_guest()
        # Milestone 3.16 - static light sources for the floor: shrines and
        # torches in flavor rooms. Deterministic, no RNG, so the shared
        # self.rng stream and thus loot and enemy rolls are unchanged.
        self._populate_light_sources()

    def _special_room_handlers(self) -> dict[str, SpecialRoomHandler]:
        handlers = getattr(self, "_special_room_population_handlers", None)
        if handlers is None:
            handlers = {
                "shop": self._populate_shop_special_room,
                "quest_room": self._populate_quest_room_special_room,
                "bar": self._populate_bar_special_room,
                "garden": self._populate_garden_special_room,
            }
            self._special_room_population_handlers = handlers
        return handlers

    def register_special_room_handler(
        self, kind: str, handler: SpecialRoomHandler
    ) -> None:
        self._special_room_handlers()[kind] = handler

    def _bar_wall_light_mounts(
        self, special_room: SpecialRoom, room: Room
    ) -> list[tuple[str, int, int]]:
        """Return one deterministic mount on each visible interior bar wall."""

        def nearest_wall(
            candidates: list[tuple[int, int]], target: float, axis: int
        ) -> tuple[int, int] | None:
            walls = [
                tile
                for tile in candidates
                if self.dungeon.in_bounds(*tile)
                and self.dungeon.tiles[tile[0]][tile[1]] == Tile.WALL
            ]
            if not walls:
                return None
            return min(walls, key=lambda tile: (abs(tile[axis] + 0.5 - target), tile))

        mounts: list[tuple[str, int, int]] = []
        left = nearest_wall(
            [(x, room.y) for x in range(room.x + 1, room.x + room.w - 1)],
            room.x + room.w / 2,
            0,
        )
        right = nearest_wall(
            [(room.x, y) for y in range(room.y + 1, room.y + room.h - 1)],
            room.y + room.h / 2,
            1,
        )
        for side, tile in (("left", left), ("right", right)):
            if tile is None:
                continue
            self._reserve_special_room_anchor(
                special_room, f"bar_wall_light_{side}", *tile
            )
            mounts.append((side, tile[0], tile[1]))
        return mounts

    @staticmethod
    def _static_light_key(light: LightSource) -> tuple[str, float, float, float]:
        return (
            light.kind,
            round(light.x, 2),
            round(light.y, 2),
            round(light.elevation, 2),
        )

    def _populate_light_sources(self) -> None:
        # Static floor lights: shrines, the garden's central witchlight, and two
        # elevated candle sconces on each bar's visible interior wall faces.
        if not hasattr(self, "light_sources"):
            self.light_sources = []
        existing = {self._static_light_key(src) for src in self.light_sources}

        def add(light: LightSource) -> None:
            key = self._static_light_key(light)
            if key not in existing:
                self.light_sources.append(light)
                existing.add(key)

        stairs_x, stairs_y = self.dungeon.stairs
        if self.dungeon.in_bounds(stairs_x, stairs_y):
            add(
                LightSource(
                    x=stairs_x + 0.5,
                    y=stairs_y + 0.5,
                    radius=LIGHT_STAIRS_RADIUS,
                    color=LIGHT_STAIRS_COLOR,
                    intensity=LIGHT_STAIRS_INTENSITY,
                    ttl=None,
                    flicker=False,
                    kind="stairs",
                )
            )

        for shrine in self.shrines:
            hint = SHRINE_HINTS.get(shrine.kind)
            color = hint.color if hint is not None else (235, 205, 110)
            add(
                LightSource(
                    x=shrine.x,
                    y=shrine.y,
                    radius=LIGHT_SHRINE_RADIUS,
                    color=color,
                    intensity=LIGHT_SHRINE_INTENSITY,
                    ttl=None,
                    flicker=False,
                    kind="shrine",
                )
            )
        room_count = len(self.dungeon.rooms)
        for special_room in getattr(self.dungeon, "special_rooms", []):
            if special_room.room_index not in range(room_count):
                continue
            if special_room.kind not in ("bar", "garden"):
                continue
            room = self.dungeon.rooms[special_room.room_index]
            if special_room.kind == "bar":
                for side, wall_x, wall_y in self._bar_wall_light_mounts(
                    special_room, room
                ):
                    if side == "left":
                        light_x, light_y = wall_x + 0.5, wall_y + 1.0
                    else:
                        light_x, light_y = wall_x + 1.0, wall_y + 0.5
                    add(
                        LightSource(
                            x=light_x,
                            y=light_y,
                            radius=LIGHT_TORCH_RADIUS,
                            color=LIGHT_TORCH_COLOR,
                            intensity=LIGHT_TORCH_INTENSITY,
                            ttl=None,
                            flicker=True,
                            flicker_seed=(
                                wall_x * 131
                                + wall_y * 17
                                + (0 if side == "left" else 977)
                            )
                            % 9973,
                            kind="bar_wall_light",
                            elevation=LIGHT_BAR_WALL_ELEVATION,
                        )
                    )
                continue

            cx, cy = room.center
            add(
                LightSource(
                    x=cx + 0.5,
                    y=cy + 0.5,
                    radius=LIGHT_TORCH_RADIUS,
                    color=(150, 220, 130),
                    intensity=LIGHT_TORCH_INTENSITY,
                    ttl=None,
                    flicker=True,
                    kind="torch",
                )
            )

    def _reconcile_static_light_sources(self) -> None:
        """Upgrade persisted floor lights, then idempotently backfill fixtures."""
        bar_center: tuple[float, float] | None = None
        special_room = self.dungeon.special_room_for_kind("bar")
        if special_room is not None and 0 <= special_room.room_index < len(
            self.dungeon.rooms
        ):
            cx, cy = self.dungeon.rooms[special_room.room_index].center
            bar_center = (cx + 0.5, cy + 0.5)

        retained: list[LightSource] = []
        for source in getattr(self, "light_sources", []):
            if source.kind == "bar_wall_light":
                continue
            if (
                bar_center is not None
                and source.kind == "torch"
                and abs(source.x - bar_center[0]) < 0.01
                and abs(source.y - bar_center[1]) < 0.01
            ):
                continue
            retained.append(source)
        self.light_sources = retained
        self._populate_light_sources()

    def _populate_special_rooms(self) -> None:
        for special_room in list(getattr(self.dungeon, "special_rooms", [])):
            if not (0 <= special_room.room_index < len(self.dungeon.rooms)):
                continue
            handler = self._special_room_handlers().get(special_room.kind)
            if handler is None:
                continue
            handler(special_room, self.dungeon.rooms[special_room.room_index])

    def _reconcile_bar_dancers(self) -> None:
        """Backfill one dedicated dancer per persisted bar without patron rolls."""
        for special_room in list(getattr(self.dungeon, "special_rooms", [])):
            if special_room.kind != "bar":
                continue
            if not (0 <= special_room.room_index < len(self.dungeon.rooms)):
                continue
            self._ensure_bar_dancer(
                special_room, self.dungeon.rooms[special_room.room_index]
            )

    def _reconcile_garden_frogs(self) -> None:
        """Backfill frogs in pre-4.1.13 saves without touching gameplay RNG."""
        for special_room in list(getattr(self.dungeon, "special_rooms", [])):
            if special_room.kind != "garden":
                continue
            if not (0 <= special_room.room_index < len(self.dungeon.rooms)):
                continue
            self._populate_garden_special_room(
                special_room,
                self.dungeon.rooms[special_room.room_index],
                include_wanderer=False,
            )

    def _room_contains_world_point(self, room: Room, x: float, y: float) -> bool:
        return room.x <= x < room.x + room.w and room.y <= y < room.y + room.h

    def _clear_room_hostiles_and_traps(self, room: Room) -> None:
        self.enemies = [
            enemy
            for enemy in self.enemies
            if not self._room_contains_world_point(room, enemy.x, enemy.y)
        ]
        self.traps = [
            trap
            for trap in self.traps
            if not self._room_contains_world_point(room, trap.x, trap.y)
        ]

    def _reserve_special_room_anchor(
        self, special_room: SpecialRoom, key: str, x: int, y: int
    ) -> None:
        tile = [int(x), int(y)]
        previous = special_room.anchor_points.get(key)
        previous_tile = (
            [int(previous[0]), int(previous[1])]
            if previous is not None and len(previous) >= 2
            else None
        )
        special_room.anchor_points[key] = tile.copy()
        if previous_tile is not None and previous_tile != tile:
            still_referenced = any(
                len(anchor) >= 2
                and [int(anchor[0]), int(anchor[1])] == previous_tile
                for anchor in special_room.anchor_points.values()
            )
            if not still_referenced:
                special_room.reserved_tiles = [
                    reserved
                    for reserved in special_room.reserved_tiles
                    if len(reserved) < 2
                    or [int(reserved[0]), int(reserved[1])] != previous_tile
                ]
        if tile not in special_room.reserved_tiles:
            special_room.reserved_tiles.append(tile)

    def _populate_shop_room(self) -> None:
        special_room = self.dungeon.special_room_for_kind("shop")
        if special_room is None:
            return
        if not (0 <= special_room.room_index < len(self.dungeon.rooms)):
            return
        self._populate_shop_special_room(
            special_room, self.dungeon.rooms[special_room.room_index]
        )

    def _populate_shop_special_room(
        self, special_room: SpecialRoom, room: Room
    ) -> None:
        keeper_names = (
            "Mirel Coin-Candle",
            "Old Brass Venn",
            "Sister Ledger",
            "Korrin the Barter-Saint",
            "Pell of the Locked Shelf",
        )
        x, y = room.center
        if any(
            self._room_contains_world_point(room, keeper.x, keeper.y)
            for keeper in self.shopkeepers
        ):
            return
        self._reserve_special_room_anchor(special_room, "shopkeeper", x, y)
        shopkeeper = Shopkeeper(
            x + 0.5,
            y + 0.5,
            self.rng.choice(keeper_names),
            "Allied Shopkeeper",
            inventory=self._make_shop_inventory(room),
        )
        self.shopkeepers.append(shopkeeper)
        # Shop rooms should feel like a temporary refuge rather than another ambush.
        self._clear_room_hostiles_and_traps(room)
        self.items.append(
            Item(
                "Shop Sign: Press E to trade",
                "shop_sign",
                rarity="Common",
                x=shopkeeper.x + 0.9,
                y=shopkeeper.y,
            )
        )
        self._reserve_special_room_anchor(
            special_room, "shop_sign", int(shopkeeper.x + 0.9), int(shopkeeper.y)
        )

    def _populate_quest_room_special_room(
        self, special_room: SpecialRoom, room: Room
    ) -> None:
        cx, cy = room.center
        self._reserve_special_room_anchor(special_room, "guest", cx, cy)
        self._clear_room_hostiles_and_traps(room)
        self._populate_story_guest(special_room, room)

    # --- flavor rooms: bar / garden -------------------------------------
    # These are appearance-only. They never clear hostiles or offer interaction.
    # Bars and gardens may host one traveler at 50%; every bar also receives one
    # dedicated dancer and every garden two frogs. Layout-seeded local RNG keeps
    # population deterministic without advancing the shared gameplay RNG.
    _BAR_NPC_NAMES = (
        "Barkeep Ossar",
        "Drunk Mabel",
        "Quiet Fenn",
        "Old Candle-Venn",
    )
    _BAR_DANCER_NAME = "Bar Dancer"
    _BAR_DANCER_ROLE = "Tavern Reveler"
    _BAR_DANCER_COLOR = (224, 126, 72)
    _GARDEN_NPC_NAMES = (
        "Gardener Thistle",
        "Wandering Pilgrim",
        "Hollow Friar",
        "Moss-Bound Wren",
    )
    _GARDEN_FROG_NAMES = (
        "Pip Croakleaf",
        "Moss-Hop",
        "Lady Ribbit",
        "Bogbell",
        "Thimble-Toad",
        "Dewdrop",
    )

    def _flavor_room_rng(self, special_room: SpecialRoom, salt: int) -> random.Random:
        # Include stable room geometry rather than only count/index; otherwise
        # many unrelated layouts repeat the same roll and skew far from 50%.
        room = self.dungeon.rooms[special_room.room_index]
        seed = ":".join(
            str(value)
            for value in (
                salt,
                special_room.room_index,
                len(self.dungeon.rooms),
                room.x,
                room.y,
                room.w,
                room.h,
            )
        )
        return random.Random(seed)

    def _populate_bar_special_room(self, special_room: SpecialRoom, room: Room) -> None:
        rng = self._flavor_room_rng(special_room, salt=0xB4B)
        spawn_wayfarer = rng.random() < 0.50
        wayfarer_name = rng.choice(self._BAR_NPC_NAMES) if spawn_wayfarer else ""
        existing = [
            npc
            for npc in self.idle_npcs
            if self._room_contains_world_point(room, npc.x, npc.y)
        ]
        if spawn_wayfarer and not any(npc.kind == "bar" for npc in existing):
            cx, cy = room.center
            self._reserve_special_room_anchor(special_room, "npc", cx, cy)
            self.idle_npcs.append(
                IdleNpc(
                    x=cx + 0.5,
                    y=cy + 0.5,
                    kind="bar",
                    name=wayfarer_name,
                    role="Wayfarer",
                    color=(214, 176, 120),
                )
            )
        self._ensure_bar_dancer(special_room, room)

    def _ensure_bar_dancer(
        self, special_room: SpecialRoom, room: Room
    ) -> None:
        room_dancers = [
            npc
            for npc in self.idle_npcs
            if npc.kind == "bar_dancer"
            and self._room_contains_world_point(room, npc.x, npc.y)
        ]
        retained = room_dancers[0] if room_dancers else None
        self.idle_npcs = [
            npc
            for npc in self.idle_npcs
            if not (
                npc.kind == "bar_dancer"
                and self._room_contains_world_point(room, npc.x, npc.y)
                and npc is not retained
            )
        ]
        if retained is not None:
            anchor = special_room.anchor("bar_dancer")
            if anchor is None:
                anchor = (math.floor(retained.x), math.floor(retained.y))
            self._reserve_special_room_anchor(
                special_room, "bar_dancer", anchor[0], anchor[1]
            )
            return

        rng = self._flavor_room_rng(special_room, salt=0xD4A)
        spawn_tiles = self._flavor_npc_spawn_tiles(
            special_room, room, rng, 1
        )
        if not spawn_tiles:
            return
        dancer_x, dancer_y = spawn_tiles[0]
        self._reserve_special_room_anchor(
            special_room, "bar_dancer", dancer_x, dancer_y
        )
        self.idle_npcs.append(
            IdleNpc(
                x=dancer_x + 0.5,
                y=dancer_y + 0.5,
                kind="bar_dancer",
                name=self._BAR_DANCER_NAME,
                role=self._BAR_DANCER_ROLE,
                color=self._BAR_DANCER_COLOR,
            )
        )

    def _flavor_npc_spawn_tiles(
        self,
        special_room: SpecialRoom,
        room: Room,
        rng: random.Random,
        count: int,
    ) -> list[tuple[int, int]]:
        occupied: set[tuple[int, int]] = set()
        collections = (
            getattr(self, "enemies", ()),
            getattr(self, "items", ()),
            getattr(self, "traps", ()),
            getattr(self, "shrines", ()),
            getattr(self, "secrets", ()),
            getattr(self, "shopkeepers", ()),
            getattr(self, "story_guests", ()),
            getattr(self, "idle_npcs", ()),
            getattr(self, "familiars", ()),
        )
        for collection in collections:
            for actor in collection:
                if self._room_contains_world_point(room, actor.x, actor.y):
                    occupied.add((math.floor(actor.x), math.floor(actor.y)))
        player = getattr(self, "player", None)
        if player is not None and self._room_contains_world_point(
            room, player.x, player.y
        ):
            occupied.add((math.floor(player.x), math.floor(player.y)))

        passable = [
            (x, y)
            for x in range(room.x + 1, room.x + room.w - 1)
            for y in range(room.y + 1, room.y + room.h - 1)
            if not self.dungeon.blocked_for_radius(x + 0.5, y + 0.5, 0.27)
        ]
        rng.shuffle(passable)
        cx, cy = room.center
        passable.sort(
            key=lambda tile: (tile[0] - cx) ** 2 + (tile[1] - cy) ** 2
        )
        candidates = [tile for tile in passable if tile not in occupied]
        reserved = {
            (int(tile[0]), int(tile[1]))
            for tile in special_room.reserved_tiles
            if len(tile) >= 2
        }
        preferred = [tile for tile in candidates if tile not in reserved]
        if len(preferred) < count:
            preferred.extend(tile for tile in candidates if tile in reserved)
        if len(preferred) < count:
            # Corrupt saves can theoretically occupy every interior tile. Keep
            # loading deterministic and preserve required flavor actors rather
            # than raising; normal generated floors always use clear candidates.
            preferred.extend(tile for tile in passable if tile not in preferred)
        return preferred[:count]

    def _populate_garden_special_room(
        self,
        special_room: SpecialRoom,
        room: Room,
        *,
        include_wanderer: bool = True,
    ) -> None:
        rng = self._flavor_room_rng(special_room, salt=0x6A6)
        cx, cy = room.center
        self._reserve_special_room_anchor(special_room, "npc", cx, cy)
        existing = [
            npc
            for npc in self.idle_npcs
            if self._room_contains_world_point(room, npc.x, npc.y)
        ]

        spawn_wanderer = rng.random() < 0.50
        wanderer_name = (
            rng.choice(self._GARDEN_NPC_NAMES) if spawn_wanderer else ""
        )
        if (
            include_wanderer
            and spawn_wanderer
            and not any(npc.kind == "garden" for npc in existing)
        ):
            self.idle_npcs.append(
                IdleNpc(
                    x=cx + 0.5,
                    y=cy + 0.5,
                    kind="garden",
                    name=wanderer_name,
                    role="Wanderer",
                    color=(150, 196, 132),
                )
            )

        frog_names = rng.sample(self._GARDEN_FROG_NAMES, k=2)
        room_frogs = [npc for npc in existing if npc.kind == "garden_frog"]
        retained: dict[int, IdleNpc] = {}
        retained_ids: set[int] = set()
        for index, name in enumerate(frog_names):
            frog = next(
                (
                    candidate
                    for candidate in room_frogs
                    if candidate.name == name and id(candidate) not in retained_ids
                ),
                None,
            )
            if frog is not None:
                retained[index] = frog
                retained_ids.add(id(frog))

        # Enforce the two deterministic frog slots when reconciling old or
        # partially inconsistent saves, while preserving moved valid frogs.
        self.idle_npcs = [
            npc
            for npc in self.idle_npcs
            if not (
                npc.kind == "garden_frog"
                and self._room_contains_world_point(room, npc.x, npc.y)
                and id(npc) not in retained_ids
            )
        ]
        missing_indexes = [index for index in range(2) if index not in retained]
        spawn_tiles = iter(
            self._flavor_npc_spawn_tiles(
                special_room, room, rng, len(missing_indexes)
            )
        )
        for index, name in enumerate(frog_names):
            anchor_key = f"garden_frog_{index}"
            frog = retained.get(index)
            if frog is not None:
                anchor = special_room.anchor(anchor_key)
                if anchor is None:
                    anchor = (math.floor(frog.x), math.floor(frog.y))
                self._reserve_special_room_anchor(
                    special_room, anchor_key, anchor[0], anchor[1]
                )
                continue

            frog_x, frog_y = next(spawn_tiles)
            self._reserve_special_room_anchor(
                special_room, anchor_key, frog_x, frog_y
            )
            self.idle_npcs.append(
                IdleNpc(
                    x=frog_x + 0.5,
                    y=frog_y + 0.5,
                    kind="garden_frog",
                    name=name,
                    role="Garden Dancer",
                    color=(116, 190, 92),
                )
            )

    def _make_shop_inventory(self, room: Room) -> list[Item]:
        stock: list[Item] = [
            Item("Minor Healing Potion", "potion", heal=35, rarity="Common"),
            Item("Lesser Mana Potion", "mana_potion", mana=24, rarity="Common"),
            Item("Scroll of Identify", "identify", rarity="Common"),
        ]
        stock.append(
            self._make_equipment(
                "weapon", "Magic", room.center[0] + 0.5, room.center[1] + 0.5
            )
        )
        stock.append(
            self._make_equipment(
                "armor", "Magic", room.center[0] + 0.5, room.center[1] + 0.5
            )
        )
        if self.current_depth >= 3 or self.rng.random() < 0.35:
            stock.append(self._make_loot(room.center[0] + 0.5, room.center[1] + 0.5))
        for item in stock:
            item.x = 0.0
            item.y = 0.0
        return stock

    def _apply_run_modifier(self, enemy: Enemy) -> Enemy:
        difficulty = self.difficulty_profile()
        depth_multiplier = 1.0 + max(0, self.current_depth - 1) * 0.045
        # Below level 5 the dungeon steepens: each depth past 5 adds an extra
        # 5% HP on top of the gentle surface scaling so deep floors hit harder.
        depth_multiplier += max(0, self.current_depth - 5) * 0.05
        story_pressure = self.story_effect_value("enemy_pressure", -0.25, 0.35)
        story_multiplier = 1.0 + max(-0.12, min(0.22, story_pressure * 0.55))
        if enemy.kind == "boss":
            story_multiplier += self.story_effect_value("boss_pressure", 0.0, 0.35)
        enemy.max_hp = max(
            1,
            int(
                enemy.max_hp
                * self.run_modifier.enemy_hp_multiplier
                * depth_multiplier
                * story_multiplier
                * difficulty.enemy_hp_multiplier
            ),
        )
        enemy.hp = enemy.max_hp
        damage = enemy.damage + self.run_modifier.enemy_damage_bonus
        damage += max(0, self.current_depth - 4) // 2
        # Below level 5 enemies hit noticeably harder: +1 damage per depth
        # past 5, on top of the slow depth-4 ramp.
        damage += max(0, self.current_depth - 5)
        if story_pressure > 0:
            damage += int(story_pressure * 8)
        if enemy.kind == "boss":
            damage += int(self.story_effect_value("boss_pressure", 0.0, 0.35) * 10)
        enemy.damage = max(
            1,
            int(round(damage * difficulty.enemy_damage_multiplier))
            + difficulty.enemy_damage_bonus,
        )
        enemy.speed *= difficulty.enemy_speed_multiplier
        enemy.attack_cooldown = max(
            0.35,
            enemy.attack_cooldown * difficulty.enemy_attack_cooldown_multiplier,
        )
        enemy.aggro_range += (
            self.run_modifier.enemy_aggro_bonus
            + max(0.0, story_pressure)
            + difficulty.enemy_aggro_bonus
            + max(0, self.current_depth - 5) * 0.25
        )
        return enemy

    def _weighted_enemy_definition(self, final_room: bool = False) -> EnemyDefinition:
        definitions = FINAL_ROOM_ENEMY_DEFINITIONS if final_room else ENEMY_DEFINITIONS
        total_weight = sum(definition.weight for definition in definitions)
        roll = self.rng.randrange(total_weight)
        current = 0
        for definition in definitions:
            current += definition.weight
            if roll < current:
                return definition
        return definitions[-1]

    def _make_enemy(
        self, x: float, y: float, final_room: bool = False, elite_bonus: float = 0.0
    ) -> Enemy:
        definition = self._weighted_enemy_definition(final_room)
        enemy = Enemy(
            definition.name,
            definition.kind,
            x,
            y,
            definition.max_hp,
            definition.max_hp,
            definition.speed,
            definition.damage,
            definition.xp,
            definition.attack_range,
            definition.attack_cooldown,
            aggro_range=definition.aggro_range,
            color=definition.color,
        )
        self._assign_enemy_combat_traits(enemy)
        enemy = self._apply_run_modifier(enemy)
        if enemy.kind != "boss" and self.rng.random() < self.elite_chance(elite_bonus):
            self._apply_elite_modifier(enemy)
        return enemy

    def _assign_enemy_combat_traits(self, enemy: Enemy) -> None:
        base_name = enemy.name
        for prefix in ("Venomous", "Runed", "Ironbound", "Frenzied", "Oathbound"):
            base_name = base_name.replace(f"{prefix} ", "")
        traits: dict[str, tuple[str, str, dict[str, float]]] = {
            "Cultist": ("caster", "arcane", {"arcane": 0.24, "shadow": 0.12}),
            "Bone Imp": ("skirmisher", "frost", {"frost": 0.22, "holy": -0.10}),
            "Venom Skitter": ("flanker", "poison", {"poison": 0.45, "fire": -0.18}),
            "Crypt Brute": ("bruiser", "physical", {"physical": 0.24, "arcane": -0.10}),
            "Ghoul": ("mauler", "shadow", {"shadow": 0.18, "holy": -0.15}),
            "Grave Archer": (
                "marksman",
                "physical",
                {"physical": 0.10, "poison": -0.08},
            ),
            "Ash Hound": ("flanker", "fire", {"fire": 0.34, "frost": -0.18}),
            "Rune Sentinel": ("sentinel", "arcane", {"arcane": 0.38, "physical": 0.10}),
            "Plague Toad": ("artillery", "poison", {"poison": 0.38, "fire": -0.12}),
            "Hollow Knight": ("guard", "physical", {"physical": 0.18, "shadow": 0.12}),
            "Gate Warden": (
                "guard",
                "holy",
                {"physical": 0.20, "holy": 0.28, "shadow": -0.12},
            ),
        }
        role, damage_type, resistances = traits.get(
            base_name, ("bruiser", "physical", {"physical": 0.08})
        )
        enemy.role = role
        enemy.damage_type = damage_type
        enemy.resistances = dict(resistances)

    def elite_chance(self, bonus: float = 0.0) -> float:
        difficulty = self.difficulty_profile()
        base = 0.06 + self.current_depth * 0.006 + difficulty.elite_bonus + bonus
        if self.run_modifier.name == "Elite Hunt":
            base += 0.08
        return max(0.0, min(0.55, base))

    def miniboss_chance(self) -> float:
        difficulty = self.difficulty_profile()
        base = 0.015 + self.current_depth * 0.006 + difficulty.miniboss_bonus
        if self.run_modifier.name == "Elite Hunt":
            base += 0.035
        return max(0.0, min(0.22, base))

    def _shift_color(self, color: Color, shift: Color) -> Color:
        return (
            max(35, min(255, color[0] + shift[0])),
            max(35, min(255, color[1] + shift[1])),
            max(35, min(255, color[2] + shift[2])),
        )

    def _apply_elite_modifier(self, enemy: Enemy) -> None:
        modifier = self.rng.choice(ELITE_MODIFIERS)
        enemy.name = f"{modifier.name} {enemy.name}"
        enemy.elite_modifier = modifier.name
        enemy.telegraph = modifier.description
        enemy.max_hp = max(1, int(enemy.max_hp * modifier.hp_multiplier))
        enemy.hp = enemy.max_hp
        enemy.damage += modifier.damage_bonus
        enemy.speed *= modifier.speed_multiplier
        enemy.xp += modifier.xp_bonus
        enemy.aggro_range += 1.0 if modifier.name == "Runed" else 0.0
        if modifier.name == "Venomous":
            enemy.damage_type = "poison"
            enemy.resistances["poison"] = max(
                enemy.resistances.get("poison", 0.0), 0.40
            )
            enemy.role = "flanker"
        elif modifier.name == "Runed":
            enemy.damage_type = "arcane"
            enemy.resistances["arcane"] = max(
                enemy.resistances.get("arcane", 0.0), 0.34
            )
        elif modifier.name == "Ironbound":
            enemy.resistances["physical"] = max(
                enemy.resistances.get("physical", 0.0), 0.32
            )
            enemy.role = "guard"
        elif modifier.name == "Frenzied":
            enemy.role = "flanker"
        enemy.color = self._shift_color(enemy.color, modifier.color_shift)

    def _make_miniboss(self, x: float, y: float) -> Enemy:
        enemy = self._make_enemy(x, y, final_room=True)
        enemy.name = f"Oathbound {enemy.name}"
        enemy.kind = "miniboss"
        enemy.elite_modifier = enemy.elite_modifier or "Oathbound"
        enemy.telegraph = "large readable windups and guaranteed reward"
        enemy.max_hp = int(enemy.max_hp * 1.85)
        enemy.hp = enemy.max_hp
        enemy.damage += 3
        enemy.xp += 34
        enemy.aggro_range += 2.0
        enemy.color = self.theme.accent
        return enemy

    def _make_floor_boss(self, boss_key: str, x: float, y: float) -> Enemy:
        definition = self.boss_definition_by_key(boss_key)
        if definition is None or definition.final_boss:
            return self._make_miniboss(x, y)
        name = definition.name
        if self.story_state is not None:
            name = f"{self.story_state.antagonist} {name}"
        boss = Enemy(
            name,
            "miniboss",
            x,
            y,
            definition.max_hp,
            definition.max_hp,
            definition.speed,
            definition.damage,
            definition.xp,
            definition.attack_range,
            definition.attack_cooldown,
            aggro_range=definition.aggro_range,
            color=definition.color,
            elite_modifier="Floor Boss",
            telegraph=definition.telegraph,
            role="floor_boss",
            damage_type=definition.damage_type,
            size=2,
            resistances={
                definition.damage_type: 0.45,
                "physical": 0.25,
                "holy" if definition.damage_type != "holy" else "shadow": -0.15,
            },
        )
        boss = self._apply_run_modifier(boss)
        # Floor bosses are now hulking 4-tile gatekeepers: far more HP, harder
        # hits, faster recovery, and longer reach so they control the room.
        boss.max_hp = int(boss.max_hp * 1.85)
        boss.hp = boss.max_hp
        boss.damage += 6
        boss.attack_cooldown = max(0.55, boss.attack_cooldown * 0.82)
        boss.attack_range = max(boss.attack_range, 1.85)
        boss.aggro_range += 3.0
        boss.speed = max(boss.speed, 1.05)
        return boss

    def _make_story_hunter(
        self, x: float, y: float, prefix: str | None = None
    ) -> Enemy:
        enemy = self._make_enemy(x, y, final_room=True)
        story_prefix = prefix or "Story-Marked"
        if self.story_state is not None and prefix is None:
            story_prefix = f"{self.story_state.antagonist} Hunter"
        enemy.name = f"{story_prefix} {enemy.name}"
        enemy.elite_modifier = enemy.elite_modifier or "Story-Marked"
        enemy.telegraph = "drawn by unresolved oaths and defiant story choices"
        enemy.max_hp = max(1, int(enemy.max_hp * 1.28))
        enemy.hp = enemy.max_hp
        enemy.damage += max(1, self.current_depth // 2)
        enemy.xp += 14 + self.current_depth * 2
        enemy.aggro_range += 2.5
        enemy.color = self.story_state.accent if self.story_state else self.theme.accent
        return enemy

    def _make_boss(self, x: float, y: float) -> Enemy:
        boss_titles = {
            "Crypt of Ash": "Ashen Gate Tyrant",
            "Fungal Catacombs": "Mycelial Gate Tyrant",
            "Violet Reliquary": "Voidbound Gate Tyrant",
            "Sunken Bastion": "Drowned Gate Tyrant",
            "Frozen Ossuary": "Rimebound Gate Tyrant",
            "Obsidian Foundry": "Forgeheart Gate Tyrant",
            "Moonlit Aquifer": "Moon-Drowned Gate Tyrant",
            "Thornbound Vault": "Thorn-Crowned Gate Tyrant",
        }
        definition = self.boss_definition_by_key("gate_tyrant")
        boss_name = boss_titles.get(self.theme.name, "Dread Gate Tyrant")
        if self.story_state is not None:
            boss_name = f"{self.story_state.antagonist} {boss_name}"
        base_hp = definition.max_hp if definition is not None else 245
        boss = Enemy(
            boss_name,
            "boss",
            x,
            y,
            base_hp,
            base_hp,
            definition.speed if definition is not None else 1.32,
            definition.damage if definition is not None else 21,
            definition.xp if definition is not None else 120,
            definition.attack_range if definition is not None else 1.45,
            definition.attack_cooldown if definition is not None else 1.08,
            aggro_range=definition.aggro_range if definition is not None else 13.0,
            color=self.theme.accent,
            telegraph=definition.telegraph if definition is not None else "gate strike",
            role="boss",
            damage_type="shadow"
            if self.theme.name in ("Violet Reliquary", "Thornbound Vault")
            else "physical",
            size=2,
            resistances={"physical": 0.30, "shadow": 0.34, "holy": -0.15},
        )
        boss = self._apply_run_modifier(boss)
        # Final boss is a towering 4-tile tyrant: roughly triple the old HP,
        # much heavier hits, faster cooldowns, longer reach, and full room aggro
        # so the climactic fight is a real gate-seal encounter.
        boss.max_hp = int(boss.max_hp * 2.4)
        boss.hp = boss.max_hp
        boss.damage += 9
        boss.attack_cooldown = max(0.6, boss.attack_cooldown * 0.8)
        boss.attack_range = max(boss.attack_range, 1.9)
        boss.aggro_range = 16.0
        boss.speed = max(boss.speed, 1.15)
        return boss

    def _make_loot(self, x: float, y: float) -> Item:
        roll = self.rng.random()
        if roll < 0.24:
            return Item(
                "Minor Healing Potion", "potion", heal=35, rarity="Common", x=x, y=y
            )
        if roll < 0.34:
            return Item(
                "Lesser Mana Potion", "mana_potion", mana=24, rarity="Common", x=x, y=y
            )
        if roll < 0.42:
            return Item("Scroll of Identify", "identify", rarity="Common", x=x, y=y)
        loot_bonus = self.run_modifier.loot_bonus + self.story_effect_value(
            "loot_bonus", 0.0, 0.25
        )
        # Legendary and unique drops are deliberately scarce: a tiny base window
        # plus a dampened loot_bonus so treasure buffs nudge the odds upward
        # without flooding runs with build-defining gear.
        if roll > 0.996 - loot_bonus * 0.20:
            slot = "weapon" if self.rng.random() < 0.58 else "armor"
            return self._make_equipment(slot, "Legendary", x, y)
        if roll > 0.988 - loot_bonus * 0.35:
            return self._make_unique(x, y)
        slot = "weapon" if roll < 0.70 else "armor"
        rarity = "Rare" if self.rng.random() < 0.34 else "Magic"
        if self.rng.random() < 0.20:
            rarity = "Common"
        return self._make_equipment(slot, rarity, x, y)

    def _make_equipment(self, slot: str, rarity: str, x: float, y: float) -> Item:
        if slot == "weapon":
            definition = self.rng.choice(WEAPON_DEFINITIONS)
            item = Item(
                definition.name,
                "weapon",
                power=definition.value,
                rarity=rarity,
                x=x,
                y=y,
            )
        else:
            definition = self.rng.choice(ARMOR_DEFINITIONS)
            item = Item(
                definition.name,
                "armor",
                defense=definition.value,
                rarity=rarity,
                x=x,
                y=y,
            )
        self._apply_affixes(item, RARITY_AFFIX_COUNTS.get(rarity, 1), rarity)
        if rarity == "Legendary":
            if item.slot == "weapon":
                item.power += 4
                item.proc_effect = item.proc_effect or "ignite"
                item.proc_chance = max(item.proc_chance, 0.35)
                item.damage_type = (
                    item.damage_type if item.damage_type != "physical" else "fire"
                )
                self._add_item_tags(item, ("legendary", "proc"))
            else:
                item.defense += 3
                item.skill_bonus = item.skill_bonus or "Dash guard"
                item.thorns += 2
                self._add_item_tags(item, ("legendary", "guard", "thorns"))
        curse_chance = (
            0.08
            + (0.08 if self.run_modifier.name == "Cursed Bargains" else 0.0)
            + self.story_effect_value("curse_bonus", 0.0, 0.18)
        )
        if rarity != "Common" and self.rng.random() < curse_chance:
            self._apply_cursed_bargain(item)
        self._empower_story_relic_item(item)
        item.unidentified = rarity != "Common" and self.rng.random() < 0.45
        return item

    def _empower_story_relic_item(self, item: Item, guaranteed: bool = False) -> None:
        relic_power = self.story_effect_value("relic_power", 0.0, 0.35)
        if relic_power <= 0 or item.slot not in ("weapon", "armor"):
            return
        if "Relic-Touched" in item.affixes:
            return
        if not guaranteed and self.rng.random() > min(0.45, relic_power * 1.35):
            return
        bonus = max(2, int(round(2 + relic_power * 14)))
        if item.slot == "weapon":
            item.power += bonus
        else:
            item.defense += max(2, bonus // 2 + 1)
        if "Relic-Touched" not in item.affixes:
            item.affixes.append("Relic-Touched")
        if self.story_state is not None and not item.unique_effect:
            item.unique_effect = f"echo of {self.story_state.relic_name}"

    def _roll_affix_float(self, base_range: tuple[float, float], rarity: str) -> float:
        if base_range == (0.0, 0.0):
            return 0.0
        rarity_range = RARITY_AFFIX_ROLL_RANGES.get(
            rarity, RARITY_AFFIX_ROLL_RANGES["Magic"]
        )
        base = self.rng.uniform(base_range[0], base_range[1])
        multiplier = self.rng.uniform(rarity_range[0], rarity_range[1])
        return base * multiplier

    def _roll_affix_int(self, base_range: tuple[float, float], rarity: str) -> int:
        value = self._roll_affix_float(base_range, rarity)
        if value == 0.0:
            return 0
        return int(round(value))

    def _add_item_tags(self, item: Item, tags: tuple[str, ...]) -> None:
        for tag in tags:
            normalized = tag.lower()
            if normalized not in item.affix_tags:
                item.affix_tags.append(normalized)

    def _append_skill_bonus(self, item: Item, bonus: str) -> None:
        if not bonus:
            return
        if not item.skill_bonus:
            item.skill_bonus = bonus
        elif bonus not in item.skill_bonus:
            item.skill_bonus = f"{item.skill_bonus} / {bonus}"

    def _apply_affix_definition(
        self, item: Item, affix: AffixDefinition, rarity: str
    ) -> None:
        item.affixes.append(affix.name)
        item.power += self._roll_affix_int(affix.power, rarity)
        item.defense += self._roll_affix_int(affix.defense, rarity)
        item.attack_speed += self._roll_affix_float(affix.attack_speed, rarity)
        item.cast_speed += self._roll_affix_float(affix.cast_speed, rarity)
        item.move_speed += self._roll_affix_float(affix.move_speed, rarity)
        item.thorns += max(0, self._roll_affix_int(affix.thorns, rarity))
        item.lifesteal += max(0.0, self._roll_affix_float(affix.lifesteal, rarity))
        item.proc_chance += max(0.0, self._roll_affix_float(affix.proc_chance, rarity))
        if affix.damage_type:
            item.damage_type = affix.damage_type
        self._append_skill_bonus(item, affix.skill_bonus)
        if affix.proc_effect and not item.proc_effect:
            item.proc_effect = affix.proc_effect
        self._add_item_tags(item, affix.tags)

    def _apply_affixes(self, item: Item, count: int, rarity: str | None = None) -> None:
        rarity = rarity or item.rarity
        pool = [affix for affix in AFFIX_DEFINITIONS if item.slot in affix.slots]
        for affix in self.rng.sample(pool, k=min(count, len(pool))):
            self._apply_affix_definition(item, affix, rarity)
        item.proc_chance = min(item.proc_chance, 0.85)
        item.lifesteal = min(item.lifesteal, 0.22)
        item.attack_speed = max(-0.20, min(item.attack_speed, 0.36))
        item.cast_speed = max(-0.20, min(item.cast_speed, 0.36))
        item.move_speed = max(-0.20, min(item.move_speed, 0.28))

    def _apply_cursed_bargain(self, item: Item) -> None:
        item.cursed = True
        item.rarity = "Cursed"
        if "Tempting Curse" not in item.affixes:
            item.affixes.append("Tempting Curse")
        self._add_item_tags(item, ("curse", "risk"))
        if item.slot == "weapon":
            item.power += 4
            item.proc_chance = min(0.90, item.proc_chance + 0.08)
            item.attack_speed += 0.03
            item.move_speed -= 0.03
        else:
            item.defense += 3
            item.thorns += 2
            item.cast_speed -= 0.03
            item.move_speed -= 0.04

    def _make_unique(self, x: float, y: float) -> Item:
        archetype_name = self.selected_archetype.name
        archetype_pool = [
            definition
            for definition in UNIQUE_ITEM_DEFINITIONS
            if definition.archetype == archetype_name
        ]
        if archetype_pool and self.rng.random() < 0.72:
            definition = self.rng.choice(archetype_pool)
        else:
            definition = self.rng.choice(UNIQUE_ITEM_DEFINITIONS)
        return self._make_unique_from_definition(definition, x, y)

    def _make_unique_from_definition(
        self, definition: UniqueItemDefinition, x: float, y: float
    ) -> Item:
        return Item(
            definition.name,
            definition.slot,
            power=definition.power,
            defense=definition.defense,
            rarity="Unique",
            x=x,
            y=y,
            affixes=list(definition.affixes),
            unidentified=self.rng.random() < 0.35,
            unique_effect=definition.unique_effect,
            damage_type=definition.damage_type,
            skill_bonus=definition.skill_bonus,
            proc_effect=definition.proc_effect,
            affix_tags=[tag.lower() for tag in definition.affix_tags],
            attack_speed=definition.attack_speed,
            cast_speed=definition.cast_speed,
            move_speed=definition.move_speed,
            thorns=definition.thorns,
            lifesteal=definition.lifesteal,
            proc_chance=definition.proc_chance,
        )

    def drop_position_near(
        self, x: float, y: float, exclude_origin: bool = False
    ) -> tuple[float, float]:
        offsets = (
            (0.0, 0.0),
            (1.15, 0.0),
            (-1.15, 0.0),
            (0.0, 1.15),
            (0.0, -1.15),
            (1.15, 1.15),
            (-1.15, 1.15),
            (1.15, -1.15),
            (-1.15, -1.15),
        )
        stair_x, stair_y = self.dungeon.stairs[0] + 0.5, self.dungeon.stairs[1] + 0.5
        for ox, oy in offsets:
            if exclude_origin and ox == 0.0 and oy == 0.0:
                # The caller wants the drop on an adjacent tile, not the origin
                # tile (e.g. the story relic must not stack on the quest NPC).
                continue
            px, py = x + ox, y + oy
            if math.hypot(px - stair_x, py - stair_y) < 1.05:
                continue
            if not self.dungeon.blocked_for_radius(px, py, radius=0.22):
                return px, py
        return x, y
