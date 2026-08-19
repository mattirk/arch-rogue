# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
#
# AI Provenance & Liability Notice:
# This repository contains code generated, assisted, or refactored by Artificial
# Intelligence models. Provided strictly "AS IS" under Apache-2.0 with no warranty
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

"""Shared per-player navigation distance fields (4.8.9 machine intelligence).

A classic roguelike Dijkstra map: one radius-limited BFS from each living
player's tile, shared by every enemy, recomputed only when that player
crosses a tile boundary (with a short stale-time refresh as the catch-all
for doors opening and boss-room seals). Enemies whose route to their target
detours around walls descend the field one tile at a time; enemies with an
effectively straight route keep the legacy greedy step, so open-room
behavior is unchanged. The field feeds a direction into the existing
``_move_enemy_locomotion`` -> ``move_actor`` seam — collision, wall-slide,
and animation scaling are untouched. Deterministic; consumes no RNG and
never calls ``line_of_sight``.
"""
# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

import math
from collections import deque

# BFS cap in steps from the target's tile. Covers every practical aggro +
# memory pursuit while keeping a recompute O(a few hundred tiles).
NAV_FIELD_RADIUS = 24
# Stale-time recompute for a stationary player: picks up walkability changes
# (opened doors, boss-room seals) within half a second.
NAV_REFRESH_SECONDS = 0.5
# At or inside this field cost the greedy step takes over (endgame approach,
# melee stop distance, contact resolution all behave exactly as before).
NAV_DIRECT_COST = 2
# Wall-stall latch: when an advance step barely moves (wall-pressed), the
# enemy prefers field descent for this long, bypassing the cost gates below.
# The gates' "effectively straight" estimate is provably wrong exactly at
# corners (around a near corner the 8-connected cost EQUALS the Chebyshev
# estimate), so actual collision feedback — not geometry — is the trigger.
NAV_STALL_LATCH_SECONDS = 0.8

_NEIGHBOR_OFFSETS = (
    (-1, -1),
    (0, -1),
    (1, -1),
    (-1, 0),
    (1, 0),
    (-1, 1),
    (0, 1),
    (1, 1),
)


class _PathingCombatMixin:
    @staticmethod
    def _nav_target_key(target) -> str:
        """Stable cache key for any field target.

        Players use their network id; NPC allies and enemies (4.8.10 Part B
        targets) key by object identity — a local per-session cache key only,
        never serialized (entries are dropped on the target's death and any
        stale-dungeon leftovers are pruned on the next recompute).
        """
        player_id = getattr(target, "player_id", "")
        return player_id if player_id else f"a{id(target):x}"

    def _nav_field_for_target(self, target) -> dict[tuple[int, int], int]:
        """The BFS distance field toward ``target``, cached per target key."""
        cache = getattr(self, "_nav_fields", None)
        if cache is None:
            cache = self._nav_fields = {}
        key = self._nav_target_key(target)
        tile = (int(target.x), int(target.y))
        now = getattr(self, "elapsed", 0.0)
        entry = cache.get(key)
        if entry is not None:
            dungeon, entry_tile, stamp, field = entry
            if (
                dungeon is self.dungeon
                and entry_tile == tile
                and 0.0 <= now - stamp <= NAV_REFRESH_SECONDS
            ):
                return field
        # Recompute moment doubles as the growth bound: drop every entry
        # built against a previous floor so per-target keys cannot pile up
        # across descents.
        for stale_key in [
            k for k, v in cache.items() if v[0] is not self.dungeon
        ]:
            del cache[stale_key]
        field = self._compute_nav_field(tile)
        cache[key] = (self.dungeon, tile, now, field)
        return field

    def _drop_nav_field_for(self, target) -> None:
        """Forget a dead target's field (NPC ally death, enemy kill)."""
        cache = getattr(self, "_nav_fields", None)
        if cache is not None:
            cache.pop(self._nav_target_key(target), None)

    def _compute_nav_field(self, origin: tuple[int, int]) -> dict[tuple[int, int], int]:
        """Radius-limited 8-connected BFS over walkable tiles from ``origin``.

        Diagonal steps require at least one open orthogonal neighbor
        (mirroring the closed-corner rule actors face), and unit diagonal
        cost keeps the field Chebyshev-shaped so "cost far above the
        straight-line estimate" reliably means "detour".
        """
        dungeon = self.dungeon
        blocked = dungeon.solid_furnishing_tiles
        is_floor = dungeon.is_floor
        ox, oy = origin
        # A furnishing tile is a legal ORIGIN (targets can stand on the
        # walkable inset strip around a bar barrel); it only blocks expansion
        # THROUGH other furnishing tiles below. Returning an empty field here
        # blinded every enemy whenever the player leaned on a prop.
        if not is_floor(ox + 0.5, oy + 0.5):
            return {}
        field: dict[tuple[int, int], int] = {origin: 0}
        queue: deque[tuple[int, int]] = deque((origin,))
        while queue:
            tx, ty = queue.popleft()
            cost = field[(tx, ty)]
            if cost >= NAV_FIELD_RADIUS:
                continue
            next_cost = cost + 1
            for dx, dy in _NEIGHBOR_OFFSETS:
                nx, ny = tx + dx, ty + dy
                if (nx, ny) in field:
                    continue
                if not is_floor(nx + 0.5, ny + 0.5) or (nx, ny) in blocked:
                    continue
                if dx and dy:
                    horizontal_open = is_floor(nx + 0.5, ty + 0.5)
                    vertical_open = is_floor(tx + 0.5, ny + 0.5)
                    if not horizontal_open and not vertical_open:
                        continue
                field[(nx, ny)] = next_cost
                queue.append((nx, ny))
        return field

    def _enemy_nav_direction(
        self, actor, target
    ) -> tuple[float, float] | None:
        """Field-descent direction toward ``target``, or None for greedy.

        None means "no detour worth routing": the actor is close, the route
        is effectively straight (field cost within one step of the Chebyshev
        estimate), the actor is outside the field, or the actor is a 2x2
        boss (arenas are open; the wide footprint does not tile-route).
        ``actor`` is any mover with ``nav_latch`` — enemies since 4.8.9, NPC
        combat allies since 4.8.10.
        """
        if getattr(actor, "size", 1) >= 2:
            return None
        field = self._nav_field_for_target(target)
        if not field:
            return None
        ex, ey = int(actor.x), int(actor.y)
        cost = field.get((ex, ey))
        if cost is not None and cost <= 0:
            return None
        if cost is None:
            # Standing on a tile the field skipped — the walkable inset strip
            # of a solid furnishing (bar barrels/tables) is the common case.
            # Treat the cost as infinite so any costed neighbor routes the
            # actor back onto the field instead of returning None and letting
            # the greedy step grind into the prop forever. Actors entirely
            # outside the field radius still fall through to None below
            # (every neighbor is also uncosted).
            cost = NAV_FIELD_RADIUS + 1
        elif actor.nav_latch <= 0.0:
            if cost <= NAV_DIRECT_COST:
                return None
            # In an unobstructed room the 8-connected BFS cost equals the
            # Chebyshev estimate exactly, so excess means a real detour.
            # (A lenient "+1 slack" here caused corner deadlocks: greedy
            # walks into the wall, nav pulls back out, repeat.) Equality can
            # still hide a near corner — the wall-stall latch covers that.
            estimate = max(abs(ex - int(target.x)), abs(ey - int(target.y)))
            if cost <= estimate:
                # ...unless the straight approach is already grinding into a
                # solid furnishing box: the tile field can't see sub-tile
                # boxes, so "cost == estimate" may claim a direct route while
                # a bar barrel sits square on the line (5.0: the boxes moved
                # onto the drawn pedestal bases). Handing back to greedy then
                # ping-pongs with the stall latch forever; keep descending
                # the field instead.
                vx = target.x - actor.x
                vy = target.y - actor.y
                length = math.hypot(vx, vy)
                if length < 0.001:
                    return None
                probe_x = actor.x + (vx / length) * 0.34
                probe_y = actor.y + (vy / length) * 0.34
                if not self.dungeon._probe_hits_solid_furnishing(
                    probe_x, probe_y
                ) and not self.dungeon._probe_hits_solid_furnishing(
                    actor.x + (vx / length) * 0.68,
                    actor.y + (vy / length) * 0.68,
                ):
                    return None
        is_floor = self.dungeon.is_floor
        candidates: list[tuple[tuple[int, float], float, float]] = []
        for dx, dy in _NEIGHBOR_OFFSETS:
            nx, ny = ex + dx, ey + dy
            neighbor_cost = field.get((nx, ny))
            if neighbor_cost is None:
                continue
            if dx and dy:
                if not is_floor(nx + 0.5, ey + 0.5) and not is_floor(
                    ex + 0.5, ny + 0.5
                ):
                    continue
            center_x = nx + 0.5
            center_y = ny + 0.5
            rank = (
                neighbor_cost,
                (center_x - target.x) ** 2 + (center_y - target.y) ** 2,
            )
            candidates.append((rank, center_x, center_y))
        # Only strictly descending neighbors are routes; anything else would
        # let the probe filter below bounce the actor between two tiles
        # (up from one, down from the other) across a tile boundary.
        candidates = [entry for entry in candidates if entry[0][0] < cost]
        if not candidates:
            return None
        candidates.sort(key=lambda entry: entry[0])
        # Prefer the best-ranked neighbor whose immediate approach is
        # physically clear — the tile grid doesn't see solid furnishing
        # boxes, and descending straight into a bar barrel's collision
        # corner was a hard deadlock. A short lookahead probe filters those,
        # but ONLY among candidates tied at the best cost: trading cost for
        # clearance let an actor hugging a barrel's edge (5.0: the boxes sit
        # on the drawn pedestal bases) pick a clear-but-backward neighbor and
        # orbit the prop forever. If every tied candidate probes blocked,
        # keep the best-ranked one and let the stall slide grind past the
        # corner.
        chosen = candidates[0]
        best_cost = candidates[0][0][0]
        for candidate in candidates:
            if candidate[0][0] != best_cost:
                break
            vx = candidate[1] - actor.x
            vy = candidate[2] - actor.y
            length = math.hypot(vx, vy)
            if length < 0.001:
                continue
            probe_x = actor.x + (vx / length) * 0.34
            probe_y = actor.y + (vy / length) * 0.34
            if not self.dungeon.blocked_for_radius(probe_x, probe_y):
                chosen = candidate
                break
        vx = chosen[1] - actor.x
        vy = chosen[2] - actor.y
        length = math.hypot(vx, vy)
        if length < 0.001:
            return None
        return vx / length, vy / length
