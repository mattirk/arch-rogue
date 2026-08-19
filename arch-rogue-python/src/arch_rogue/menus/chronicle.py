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

"""The Chronicle of descents: the run-history screen (5.0.1).

Reachable from the title menu, it lists the last twelve finished runs
(newest first) as standard menu rows — outcome sigil, archetype and depth,
then difficulty / kills / duration in the value column — with the selected
run's full story told in the parchment note: how it ended, the floor omen,
bosses felled, and notable loot. Records come straight from
``Game.run_history`` (persisted in the options file since 4.x; 5.0.1 adds
the ``ended`` date to new records, older ones simply omit it).
"""

from __future__ import annotations

import pygame

from ..constants import DUNGEON_DEPTH
from .base import MenuRow

# Outcome lives in the row label: the key-badge column is hidden in modern
# menu styling, and the built-in font has no star/diamond glyphs anyway —
# deaths keep the dagger the You Died card already renders.


def _duration_text(seconds: object) -> str:
    try:
        total = max(0, int(seconds))
    except (TypeError, ValueError):
        total = 0
    return f"{total // 60}:{total % 60:02d}"


def _record_row(record: dict) -> MenuRow:
    outcome = str(record.get("outcome", ""))
    class_name = str(record.get("class", "")) or "Unknown"
    depth = record.get("depth", "?")
    if outcome == "victory":
        label = f"Victory — {class_name} — depth {depth}/{DUNGEON_DEPTH}"
    else:
        label = f"† {class_name} — depth {depth}/{DUNGEON_DEPTH}"
    if record.get("multiplayer"):
        label += " · co-op"
    parts = [
        str(record.get("difficulty", "")) or "Medium",
        f"{record.get('kills', 0)} kills",
        _duration_text(record.get("time")),
    ]
    ended = str(record.get("ended", ""))
    if ended:
        parts.append(ended)
    return ("", label, " · ".join(parts))


def _record_detail(record: dict) -> str:
    outcome = str(record.get("outcome", ""))
    depth = record.get("depth", "?")
    if outcome == "victory":
        sentences = ["The Gate broken — a full descent survived."]
    else:
        cause = str(record.get("cause", "")).strip()
        fell = f"Fell at depth {depth}"
        sentences = [f"{fell} — {cause}." if cause else f"{fell}."]
    modifier = str(record.get("modifier", "")).strip()
    if modifier:
        sentences.append(f"Omen: {modifier}.")
    bosses = [str(name) for name in record.get("bosses", []) if name]
    if bosses:
        sentences.append(f"Felled: {', '.join(bosses)}.")
    loot = [str(name) for name in record.get("notable_loot", []) if name]
    if loot:
        sentences.append(f"Notable loot: {', '.join(loot)}.")
    return " ".join(sentences)


class MenuChronicleMixin:
    def draw_chronicle_screen(self) -> None:
        panel, content = self.menu_frame("Chronicle")
        modern = bool(getattr(self, "_last_menu_frame_used_asset", False))
        records = list(reversed(getattr(self.g, "run_history", [])))

        note_h = (
            min(self.u(56), max(36, content.height // 5))
            if modern
            else min(self.u(60), max(38, content.height // 4))
        )
        note_rect = pygame.Rect(
            content.x, content.bottom - note_h, content.width, note_h
        )
        rows_rect = pygame.Rect(
            content.x,
            content.y,
            content.width,
            max(1, note_rect.y - content.y - self.u(7)),
        )

        if not records:
            self.g._chronicle_row_rects = ()
            self.draw_wrapped_text(
                "No descents recorded yet.",
                self.g.font,
                self.MUTED,
                pygame.Rect(
                    rows_rect.x,
                    rows_rect.y + self.u(12),
                    rows_rect.width,
                    rows_rect.height - self.u(12),
                ),
            )
            self._draw_parchment_note(
                note_rect,
                "The dungeon keeps its own ledger: every finished descent — "
                "triumph or burial — is written here, twelve entries deep.",
                modern=modern,
            )
            return

        selection = max(
            0,
            min(
                len(records) - 1,
                int(getattr(self.g, "chronicle_selection", 0)),
            ),
        )
        rows = [_record_row(record) for record in records]
        # Window the list like the options menu: the twelve-deep ledger does
        # not fit small canvases, so a scroll window follows the selection and
        # the published range lets mouse/tap indices map back onto records.
        max_visible = max(4, rows_rect.height // self.u(38))
        start = 0
        if selection >= max_visible:
            start = min(len(rows) - max_visible, selection - max_visible + 1)
        visible = rows[start : start + max_visible]
        self.g._chronicle_visible_range = (start, start + len(visible))
        rendered_rows = self.draw_menu_rows(
            visible,
            rows_rect,
            selected_index=selection - start,
            keys_in_rows=not modern,
        )
        self.g._chronicle_row_rects = rendered_rows
        self._draw_parchment_note(
            note_rect, _record_detail(records[selection]), modern=modern
        )
