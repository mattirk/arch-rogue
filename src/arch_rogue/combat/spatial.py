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
"""Deterministic broad-phase queries for moving dungeon actors.

The combat simulation historically scanned the complete enemy list for every
moving actor.  This index keeps the exact list-order semantics required by
collision resolution while limiting narrow-phase checks to nearby grid cells.
It is deliberately independent from Pygame and from combat policy: callers
choose the conservative query radius and still perform their original precise
distance, state, and line-of-sight checks.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from ..models import Enemy


class EnemySpatialIndex:
    """A mutable uniform grid that returns candidates in source-list order."""

    # One tile keeps dense packs narrow while even the largest current two-body
    # contact radius only spans a small fixed neighborhood.
    DEFAULT_CELL_SIZE = 1.0

    def __init__(
        self,
        enemies: Sequence[Enemy],
        *,
        cell_size: float = DEFAULT_CELL_SIZE,
    ) -> None:
        if cell_size <= 0.0:
            raise ValueError("cell_size must be positive")
        self.cell_size = float(cell_size)
        self._source = enemies
        self._source_length = len(enemies)
        # Each bucket is a Python-int bit set over source-list positions.
        # Unioning nearby cells therefore happens in optimized integer code,
        # and walking low bits naturally restores deterministic list order
        # without allocating and sorting candidate tuples.
        self._buckets: dict[tuple[int, int], int] = {}
        self._cells: dict[int, tuple[int, int]] = {}
        self._order: dict[int, int] = {}
        self._build(enemies)

    def matches(self, enemies: Sequence[Enemy]) -> bool:
        """Whether *enemies* is the unchanged source collection.

        Game content replaces the enemy list at floor boundaries and appends
        spawned actors.  Identity plus length catches both without an O(n)
        signature check in every hot-path query.
        """

        return enemies is self._source and len(enemies) == self._source_length

    def candidates(
        self,
        x: float,
        y: float,
        radius: float,
    ) -> list[Enemy]:
        """Return actors in cells touched by the conservative query circle.

        The result is sorted back into the original enemy-list order.  Exact
        circle overlap remains the caller's responsibility.
        """

        candidate_bits = self._candidate_bits(x, y, radius)
        found: list[Enemy] = []
        while candidate_bits:
            lowest = candidate_bits & -candidate_bits
            order = lowest.bit_length() - 1
            found.append(self._source[order])
            candidate_bits ^= lowest
        return found

    def candidate_entries(
        self,
        x: float,
        y: float,
        radius: float,
        *,
        after_order: int = -1,
    ) -> list[tuple[int, Enemy]]:
        """Return ordered candidates after an already-processed source index.

        Contact resolution can move its actor after processing one enemy. A
        caller may then re-query at the new position with ``after_order`` while
        preserving the historical one-pass ``self.enemies`` ordering.
        """

        candidate_bits = self._candidate_bits(x, y, radius)
        if after_order >= 0:
            candidate_bits &= ~((1 << (after_order + 1)) - 1)
        found: list[tuple[int, Enemy]] = []
        while candidate_bits:
            lowest = candidate_bits & -candidate_bits
            order = lowest.bit_length() - 1
            found.append((order, self._source[order]))
            candidate_bits ^= lowest
        return found

    def update(self, enemy: Enemy) -> None:
        """Move an indexed enemy between buckets after simulation movement."""

        identity = id(enemy)
        old_cell = self._cells.get(identity)
        if old_cell is None:
            # A caller moved a newly appended enemy before the next collection
            # validation. Rebuilding gives it the canonical source-list order.
            self._rebuild_current_source()
            return
        new_cell = self._cell(enemy.x, enemy.y)
        if new_cell == old_cell:
            return
        order = self._order[identity]
        enemy_bit = 1 << order
        old_bucket = self._buckets[old_cell] & ~enemy_bit
        if old_bucket:
            self._buckets[old_cell] = old_bucket
        else:
            del self._buckets[old_cell]
        self._buckets[new_cell] = self._buckets.get(new_cell, 0) | enemy_bit
        self._cells[identity] = new_cell

    def _build(self, enemies: Sequence[Enemy]) -> None:
        for order, enemy in enumerate(enemies):
            identity = id(enemy)
            cell = self._cell(enemy.x, enemy.y)
            self._order[identity] = order
            self._cells[identity] = cell
            self._buckets[cell] = self._buckets.get(cell, 0) | (1 << order)

    def _rebuild_current_source(self) -> None:
        self._source_length = len(self._source)
        self._buckets.clear()
        self._cells.clear()
        self._order.clear()
        self._build(self._source)

    def _cell(self, x: float, y: float) -> tuple[int, int]:
        return (
            math.floor(x / self.cell_size),
            math.floor(y / self.cell_size),
        )

    def _candidate_bits(self, x: float, y: float, radius: float) -> int:
        radius = max(0.0, float(radius))
        inv_cell = 1.0 / self.cell_size
        min_x = math.floor((x - radius) * inv_cell)
        max_x = math.floor((x + radius) * inv_cell)
        min_y = math.floor((y - radius) * inv_cell)
        max_y = math.floor((y + radius) * inv_cell)
        candidate_bits = 0
        for cell_y in range(min_y, max_y + 1):
            for cell_x in range(min_x, max_x + 1):
                candidate_bits |= self._buckets.get((cell_x, cell_y), 0)
        return candidate_bits


__all__ = ["EnemySpatialIndex"]
