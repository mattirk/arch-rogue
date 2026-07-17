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
from dataclasses import dataclass
from typing import Iterator

from .audio import MusicTiming
from .models import IdleNpc, Room, Shopkeeper, StoryGuest

FriendlyNpc = Shopkeeper | StoryGuest | IdleNpc
NON_HUMANOID_FRIENDLY_NPC_KINDS = frozenset(("garden_frog",))


@dataclass(slots=True)
class FriendlyNpcMotion:
    actor: FriendlyNpc
    dungeon_token: int
    room_index: int | None
    home_x: float
    home_y: float
    target_x: float
    target_y: float
    seed: int
    facing_x: float = 1.0
    facing_y: float = 1.0
    moving: bool = False
    phrase_index: int = -1
    next_move_beat: float = 0.0


class FriendlyNpcRuntimeMixin:
    """Beat-driven, room-bound motion shared by friendly world NPCs."""

    FRIENDLY_NPC_SPEED = 0.76
    FRIENDLY_NPC_RADIUS = 0.27
    FRIENDLY_NPC_DANCE_BEATS = 4.0
    FRIENDLY_NPC_TRAVEL_BEATS = 2.0
    FRIENDLY_NPC_MIN_DANCE_BEATS = 2.0
    FRIENDLY_NPC_WAYPOINT_BEATS = 4.0

    def iter_friendly_npcs(self) -> Iterator[FriendlyNpc]:
        yield from getattr(self, "shopkeepers", ())
        yield from getattr(self, "story_guests", ())
        yield from getattr(self, "idle_npcs", ())

    def iter_friendly_humanoids(self) -> Iterator[FriendlyNpc]:
        """Yield friendly actors that use the humanoid NPC visual contract."""
        yield from getattr(self, "shopkeepers", ())
        yield from getattr(self, "story_guests", ())
        for npc in getattr(self, "idle_npcs", ()):
            if npc.kind not in NON_HUMANOID_FRIENDLY_NPC_KINDS:
                yield npc

    def reset_friendly_npc_runtime(self) -> None:
        self._friendly_npc_motions: dict[int, FriendlyNpcMotion] = {}

    def friendly_npc_music_timing(self) -> MusicTiming:
        profile = self.current_music_profile()
        audio = getattr(self, "audio", None)
        elapsed = float(getattr(self, "elapsed", 0.0))
        if audio is not None and profile is not None:
            audible = bool(
                getattr(self, "music_enabled", False)
                and audio.available
                and audio.current_music_seed is not None
            )
            return audio.music_timing(profile, None if audible else elapsed)

        # Cosmetic fallback for isolated tests or an incomplete run profile. The
        # normal game path always uses the exact procedural-track specification.
        total_beats = max(0.0, elapsed) * 2.0
        beat_index = int(total_beats)
        return MusicTiming(
            total_beats=total_beats,
            loop_beat=total_beats % 16.0,
            beat_index=beat_index,
            beat_phase=total_beats - beat_index,
            phrase_index=beat_index // 4,
        )

    def friendly_npc_animation_progress(self, moving: bool) -> float:
        timing = self.friendly_npc_music_timing()
        cycle_beats = (
            self.FRIENDLY_NPC_TRAVEL_BEATS
            if moving
            else self.FRIENDLY_NPC_DANCE_BEATS
        )
        return (timing.total_beats % cycle_beats) / cycle_beats

    def friendly_npc_dance_progress(self) -> float:
        return self.friendly_npc_animation_progress(False)

    def friendly_npc_beat_pulse(
        self, loop_progress: float, moving: bool
    ) -> tuple[float, float]:
        cycle_beats = (
            self.FRIENDLY_NPC_TRAVEL_BEATS
            if moving
            else self.FRIENDLY_NPC_DANCE_BEATS
        )
        beat_phase = (float(loop_progress) * cycle_beats) % 1.0
        lift = math.sin(math.pi * beat_phase) ** 2
        return lift, 1.0 - lift

    def friendly_npc_motion(self, npc: FriendlyNpc) -> FriendlyNpcMotion:
        motions = getattr(self, "_friendly_npc_motions", None)
        if motions is None:
            self.reset_friendly_npc_runtime()
            motions = self._friendly_npc_motions

        key = id(npc)
        dungeon = getattr(self, "dungeon", None)
        dungeon_token = id(dungeon)
        existing = motions.get(key)
        if (
            existing is not None
            and existing.actor is npc
            and existing.dungeon_token == dungeon_token
        ):
            return existing

        room_index, room = self._friendly_npc_room(npc)
        home_x, home_y = self._friendly_npc_home(npc, room_index)
        identity = ":".join(
            (
                str(getattr(self, "run_music_seed", 0)),
                str(getattr(self, "current_depth", 0)),
                str(room_index),
                type(npc).__name__,
                str(getattr(npc, "name", "")),
                str(getattr(npc, "role", "")),
                f"{home_x:.2f}",
                f"{home_y:.2f}",
            )
        )
        motion = FriendlyNpcMotion(
            actor=npc,
            dungeon_token=dungeon_token,
            room_index=room_index,
            home_x=home_x,
            home_y=home_y,
            target_x=npc.x,
            target_y=npc.y,
            seed=self._friendly_npc_seed(identity),
        )
        if room is None:
            motion.room_index = None
        motions[key] = motion
        return motion

    def friendly_npc_visual_state(
        self, npc: FriendlyNpc
    ) -> tuple[float, float, bool, float]:
        motion = self.friendly_npc_motion(npc)
        paused = bool(
            getattr(self, "active_cutscene", None) is not None
            or getattr(self, "story_intro_pending", False)
            or getattr(self, "inventory_open", False)
            or getattr(self, "character_menu_open", False)
        )
        moving = motion.moving and not paused
        return (
            motion.facing_x,
            motion.facing_y,
            moving,
            self.friendly_npc_animation_progress(moving),
        )

    def update_friendly_npcs(self, dt: float) -> None:
        npcs = tuple(self.iter_friendly_npcs())
        motions = getattr(self, "_friendly_npc_motions", None)
        if motions is None:
            self.reset_friendly_npc_runtime()
            motions = self._friendly_npc_motions
        live_ids = {id(npc) for npc in npcs}
        for key in tuple(motions):
            if key not in live_ids or all(
                motions[key].actor is not npc for npc in npcs
            ):
                del motions[key]

        timing = self.friendly_npc_music_timing()
        for npc in npcs:
            motion = self.friendly_npc_motion(npc)
            if motion.room_index is None:
                motion.moving = False
                continue
            if self._friendly_npc_holds_for_player(npc):
                motion.moving = False
                self._friendly_npc_face_player(motion, npc)
                continue

            distance_to_target = math.hypot(
                motion.target_x - npc.x, motion.target_y - npc.y
            )
            if distance_to_target <= 0.05:
                motion.moving = False
                if timing.total_beats + 1e-9 < motion.next_move_beat:
                    continue
                motion.phrase_index = timing.phrase_index
                motion.target_x, motion.target_y = self._friendly_npc_waypoint(
                    npc, motion, timing.phrase_index
                )
                distance_to_target = math.hypot(
                    motion.target_x - npc.x, motion.target_y - npc.y
                )
                if distance_to_target <= 0.05:
                    motion.next_move_beat = self._friendly_npc_next_move_beat(
                        timing.total_beats
                    )
                    continue

            self._move_friendly_npc(npc, motion, max(0.0, dt))
            remaining = math.hypot(
                motion.target_x - npc.x, motion.target_y - npc.y
            )
            if remaining <= 0.05:
                motion.moving = False
                motion.next_move_beat = self._friendly_npc_next_move_beat(
                    timing.total_beats
                )

    def _friendly_npc_next_move_beat(self, total_beats: float) -> float:
        ready_beat = max(0.0, total_beats) + self.FRIENDLY_NPC_MIN_DANCE_BEATS
        phrase_beats = self.FRIENDLY_NPC_WAYPOINT_BEATS
        return math.ceil((ready_beat - 1e-9) / phrase_beats) * phrase_beats

    def _friendly_npc_room(
        self, npc: FriendlyNpc
    ) -> tuple[int | None, Room | None]:
        dungeon = getattr(self, "dungeon", None)
        if dungeon is None:
            return None, None
        room = dungeon.room_at(npc.x, npc.y)
        if room is None:
            return None, None
        for index, candidate in enumerate(dungeon.rooms):
            if candidate is room:
                return index, room
        return None, room

    def _friendly_npc_home(
        self, npc: FriendlyNpc, room_index: int | None
    ) -> tuple[float, float]:
        if room_index is None:
            return npc.x, npc.y
        dungeon = self.dungeon
        special_room = dungeon.special_room_at_index(room_index)
        if special_room is None:
            return npc.x, npc.y
        anchor_key = (
            "shopkeeper"
            if isinstance(npc, Shopkeeper)
            else "guest"
            if isinstance(npc, StoryGuest)
            else "npc"
        )
        anchor = special_room.anchor(anchor_key)
        if anchor is None:
            return npc.x, npc.y
        return anchor[0] + 0.5, anchor[1] + 0.5

    def _friendly_npc_seed(self, text: str) -> int:
        value = 2166136261
        for char in text:
            value ^= ord(char)
            value = (value * 16777619) & 0xFFFFFFFF
        return value

    def _friendly_npc_roam_radius(self, npc: FriendlyNpc) -> float:
        if isinstance(npc, Shopkeeper):
            return 2.5
        if isinstance(npc, StoryGuest) and not npc.resolved:
            return 3.4
        return 4.5

    def _friendly_npc_waypoint(
        self,
        npc: FriendlyNpc,
        motion: FriendlyNpcMotion,
        phrase_index: int,
    ) -> tuple[float, float]:
        if motion.room_index is None:
            return npc.x, npc.y
        room = self.dungeon.rooms[motion.room_index]
        special_room = self.dungeon.special_room_at_index(motion.room_index)
        reserved = {
            (int(tile[0]), int(tile[1]))
            for tile in getattr(special_room, "reserved_tiles", ())
            if len(tile) >= 2
        }
        max_radius = self._friendly_npc_roam_radius(npc)
        obstacles = tuple(self._friendly_npc_obstacles(npc))
        candidates: list[tuple[float, float]] = []
        for tile_x in range(room.x + 1, room.x + room.w - 1):
            for tile_y in range(room.y + 1, room.y + room.h - 1):
                if (tile_x, tile_y) in reserved:
                    continue
                x, y = tile_x + 0.5, tile_y + 0.5
                if math.hypot(x - motion.home_x, y - motion.home_y) > max_radius:
                    continue
                if math.hypot(x - npc.x, y - npc.y) < 0.55:
                    continue
                if self.dungeon.blocked_for_radius(x, y, self.FRIENDLY_NPC_RADIUS):
                    continue
                if any(
                    math.hypot(x - obstacle_x, y - obstacle_y) < radius
                    for obstacle_x, obstacle_y, radius in obstacles
                ):
                    continue
                candidates.append((x, y))
        if not candidates:
            return motion.home_x, motion.home_y
        minimum_travel = min(1.8, max_radius * 0.55)
        far_candidates = [
            candidate
            for candidate in candidates
            if math.hypot(candidate[0] - npc.x, candidate[1] - npc.y)
            >= minimum_travel
        ]
        pool = far_candidates or candidates
        rng = random.Random(
            motion.seed ^ ((phrase_index + 1) * 0x9E3779B1 & 0xFFFFFFFF)
        )
        rng.shuffle(pool)
        return pool[0]

    def _friendly_npc_obstacles(
        self, npc: FriendlyNpc
    ) -> Iterator[tuple[float, float, float]]:
        for other in self.iter_friendly_npcs():
            if other is not npc:
                yield other.x, other.y, 0.68
        for enemy in getattr(self, "enemies", ()):
            if getattr(enemy, "alive", True):
                yield enemy.x, enemy.y, 0.58 + min(0.22, enemy.size * 0.04)
        for trap in getattr(self, "traps", ()):
            yield trap.x, trap.y, 0.48
        for item in getattr(self, "items", ()):
            if item.slot in ("shop_sign", "story_relic"):
                yield item.x, item.y, 0.52
        for shrine in getattr(self, "shrines", ()):
            yield shrine.x, shrine.y, 0.58
        for secret in getattr(self, "secrets", ()):
            yield secret.x, secret.y, 0.52
        if isinstance(npc, Shopkeeper) and hasattr(
            self, "_shop_gold_stack_placements"
        ):
            for x, y, _size, _variant in self._shop_gold_stack_placements():
                yield x + 0.5, y + 0.5, 0.48

    def _friendly_npc_holds_for_player(self, npc: FriendlyNpc) -> bool:
        player = getattr(self, "player", None)
        if player is None:
            return False
        if (
            isinstance(npc, Shopkeeper)
            and getattr(self, "shop_open", False)
            and getattr(self, "active_shopkeeper", None) is npc
        ):
            return True
        radius = 0.0
        if isinstance(npc, Shopkeeper):
            radius = 1.55
        elif isinstance(npc, StoryGuest) and not npc.resolved:
            radius = 1.45
        return radius > 0.0 and math.hypot(npc.x - player.x, npc.y - player.y) <= radius

    def _friendly_npc_face_player(
        self, motion: FriendlyNpcMotion, npc: FriendlyNpc
    ) -> None:
        player = getattr(self, "player", None)
        if player is None:
            return
        dx, dy = player.x - npc.x, player.y - npc.y
        distance = math.hypot(dx, dy)
        if distance > 0.001:
            motion.facing_x = dx / distance
            motion.facing_y = dy / distance

    def _move_friendly_npc(
        self, npc: FriendlyNpc, motion: FriendlyNpcMotion, dt: float
    ) -> None:
        dx, dy = motion.target_x - npc.x, motion.target_y - npc.y
        distance = math.hypot(dx, dy)
        if distance <= 0.05 or dt <= 0.0:
            motion.moving = False
            return
        direction_x, direction_y = dx / distance, dy / distance
        motion.facing_x = direction_x
        motion.facing_y = direction_y
        step = min(distance, self.FRIENDLY_NPC_SPEED * dt)
        next_x = npc.x + direction_x * step
        next_y = npc.y + direction_y * step

        room = self.dungeon.rooms[motion.room_index]
        min_x = room.x + 1.0 + self.FRIENDLY_NPC_RADIUS
        max_x = room.x + room.w - 1.0 - self.FRIENDLY_NPC_RADIUS
        min_y = room.y + 1.0 + self.FRIENDLY_NPC_RADIUS
        max_y = room.y + room.h - 1.0 - self.FRIENDLY_NPC_RADIUS
        next_x = max(min_x, min(max_x, next_x))
        next_y = max(min_y, min(max_y, next_y))

        player = getattr(self, "player", None)
        if player is not None and math.hypot(next_x - player.x, next_y - player.y) < 0.72:
            motion.moving = False
            self._friendly_npc_face_player(motion, npc)
            return
        for obstacle_x, obstacle_y, radius in self._friendly_npc_obstacles(npc):
            current_distance = math.hypot(npc.x - obstacle_x, npc.y - obstacle_y)
            next_distance = math.hypot(next_x - obstacle_x, next_y - obstacle_y)
            if next_distance < radius and next_distance <= current_distance:
                motion.target_x = npc.x
                motion.target_y = npc.y
                motion.moving = False
                return
        if self.dungeon.blocked_for_radius(
            next_x, next_y, self.FRIENDLY_NPC_RADIUS
        ):
            motion.target_x = npc.x
            motion.target_y = npc.y
            motion.moving = False
            return

        moved = math.hypot(next_x - npc.x, next_y - npc.y)
        npc.x = next_x
        npc.y = next_y
        motion.moving = moved > 0.0001
