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

import pygame

from ..constants import MP_RUN_ID_LENGTH

MenuRow = tuple[str, str, str]


class MenuMultiplayerMixin:
    """Renderers for the 4.6 ``mp_setup`` and ``mp_lobby`` screens.

    Both screens publish their row/entry hitboxes on the Game object
    (``_mp_row_rects``, ``_mp_entry_rect``) so mobile taps land on exactly
    the rendered geometry, mirroring the title/options pattern.
    """

    def _draw_text_entry_field(
        self,
        rect: pygame.Rect,
        value: str,
        *,
        active: bool,
        big: bool = False,
        letter_spaced: bool = False,
    ) -> None:
        """One shared single-line entry box with a blinking caret."""

        pygame.draw.rect(self.screen, self.PANEL_INK, rect, border_radius=self.u(6))
        border = self.accent() if active else self.PANEL_2
        pygame.draw.rect(
            self.screen, border, rect, max(1, self.u(1)), border_radius=self.u(6)
        )
        font = self.g.big_font if big else self.g.font
        display = value
        if letter_spaced and display:
            display = " ".join(display)
        caret_on = active and int(self.g.ui_elapsed * 2.0) % 2 == 0
        text_rect = rect.inflate(-self.u(16), 0)
        self.draw_text(
            display,
            font,
            self.TEXT,
            text_rect,
            valign="center",
        )
        if caret_on:
            text_width = font.size(display)[0] if display else 0
            caret_x = min(
                text_rect.x + text_width + self.u(3), text_rect.right - self.u(2)
            )
            caret_h = font.get_height()
            pygame.draw.line(
                self.screen,
                self.accent(),
                (caret_x, rect.centery - caret_h // 2),
                (caret_x, rect.centery + caret_h // 2),
                max(1, self.u(2)),
            )
        self.g.publish_text_input_rect(rect)

    def _mp_session_value(self, name: str, default):
        session = getattr(self.g, "mp_session", None)
        return getattr(session, name, default) if session is not None else default

    def _draw_mp_notice_lines(self, area: pygame.Rect) -> int:
        y = area.y
        notice = getattr(self.g, "mp_notice", "")
        status = getattr(self.g, "mp_status", "")
        if notice:
            y = self.draw_wrapped_text(
                notice, self.g.small_font, self.WARNING, pygame.Rect(
                    area.x, y, area.width, self.u(40)
                )
            ) + self.u(4)
        if status:
            y = self.draw_wrapped_text(
                status, self.g.small_font, self.MUTED, pygame.Rect(
                    area.x, y, area.width, self.u(40)
                )
            ) + self.u(4)
        return y

    def draw_mp_consent(self) -> None:
        """Connection consent: shown before the first socket to a server.

        Mirrors the other multiplayer frames; publishes its two action rows
        through ``_mp_row_rects`` so mobile taps land on Agree / Exit.
        """

        panel, content = self.menu_frame(
            "A Word Before the Gate",
            "Multiplayer reaches beyond this machine",
        )
        g = self.g
        if bool(getattr(g, "mp_server_tls", True)):
            transport_text = (
                "The connection is encrypted (TLS) and the server's "
                "certificate is verified — that protects the wire, but it is "
                "no absolute guarantee of who stands behind the server."
            )
            transport_color = self.MUTED
        else:
            transport_text = (
                "Server encryption is OFF: traffic travels in plaintext. "
                "Enable it in Options unless this is your own trusted server."
            )
            transport_color = self.WARNING
        paragraphs: tuple[tuple[str, tuple[int, int, int]], ...] = (
            (
                "Arch Rogue is a hobby project, not professionally "
                "maintained software. Use multiplayer at your own risk.",
                self.TEXT,
            ),
            (
                "You are about to connect to this server. There is no "
                "guarantee of who operates or maintains it.",
                self.TEXT,
            ),
            (transport_text, transport_color),
            (
                "Before proceeding, get familiar with the project: "
                "https://github.com/mattirk/arch-rogue",
                self.TEXT,
            ),
        )
        endpoint = f"{g.mp_server_host}:{g.mp_server_port}"

        # The Agree/Exit rows anchor to the panel bottom. Every consent
        # paragraph must remain readable on the smallest windows, so the
        # body font is the largest candidate whose fully wrapped text fits
        # the space above the rows; nothing is ever silently clipped.
        rows_height = min(self.u(112), max(72, content.height * 2 // 5))
        rows_rect = pygame.Rect(
            content.x,
            content.bottom - rows_height,
            content.width,
            rows_height,
        )
        budget = rows_rect.y - self.u(4) - (content.y + self.u(2))
        candidates = [
            (g.font, self.u(8)),
            (g.small_font, self.u(6)),
            (g.tiny_font, 4),
            (
                self.fit_menu_font(
                    g.tiny_font,
                    max_height=12,
                    max_width=content.width,
                    minimum_size=9,
                ),
                2,
            ),
        ]
        body_font, gap = candidates[-1]
        line_gap = body_font.get_height() + 2
        for candidate_font, candidate_gap in candidates:
            candidate_line_gap = candidate_font.get_height() + 3
            lines = sum(
                len(self.wrap_text(text, candidate_font, content.width))
                for text, _ in paragraphs
            )
            endpoint_font = candidate_font
            total = (
                lines * candidate_line_gap
                + endpoint_font.get_height()
                + (len(paragraphs) + 1) * candidate_gap
            )
            if total <= budget:
                body_font, gap, line_gap = (
                    candidate_font,
                    candidate_gap,
                    candidate_line_gap,
                )
                break
        else:
            endpoint_font = body_font

        y = content.y + self.u(2)

        def paragraph(text: str, color, top: int) -> int:
            return self.draw_wrapped_text(
                text,
                body_font,
                color,
                pygame.Rect(
                    content.x, top, content.width, max(1, rows_rect.y - top)
                ),
                line_gap=line_gap,
            ) + gap

        y = paragraph(*paragraphs[0], y)
        self.draw_text(
            endpoint,
            endpoint_font,
            self.accent(),
            pygame.Rect(
                content.x, y, content.width, endpoint_font.get_height() + 2
            ),
            align="center",
        )
        y += endpoint_font.get_height() + gap
        y = paragraph(*paragraphs[1], y)
        y = paragraph(*paragraphs[2], y)
        paragraph(*paragraphs[3], y)
        rows: list[MenuRow] = [
            ("Enter", "I agree — open the gate", ""),
            ("Backspace", "Exit", ""),
        ]
        rendered = self.draw_menu_rows(
            rows,
            rows_rect,
            selected_index=int(getattr(g, "mp_consent_cursor", 0)) % 2,
        )
        g._mp_row_rects = tuple(rendered)
        g._mp_entry_rect = None
        self.draw_footer(
            panel, "Up / Down select · Enter confirms · Backspace exits"
        )

    def draw_mp_setup(self) -> None:
        step = getattr(self.g, "mp_setup_step", "name")
        subtitles = {
            "name": "Name yourself for the descent",
            "role": "Host a new run, or join a partner's",
            "host_code": "Share this code with your partner",
            "join_code": "Enter your partner's code",
        }
        panel, content = self.menu_frame(
            "Two Will Descend", subtitles.get(step, "")
        )
        rows_rects: list[pygame.Rect] = []
        entry_rect: pygame.Rect | None = None
        y = content.y + self.u(6)
        session = getattr(self.g, "text_input", None)

        if step == "name":
            self.draw_text(
                "Your name",
                self.g.font,
                self.TITLE,
                pygame.Rect(content.x, y, content.width, self.u(26)),
            )
            y += self.u(30)
            entry_rect = pygame.Rect(
                content.x, y, min(content.width, self.u(420)), self.u(52)
            )
            active = bool(
                session is not None and session.target == "mp_player_name"
            )
            value = (
                session.value
                if active and session is not None
                else getattr(self.g, "mp_player_name", "")
            )
            self._draw_text_entry_field(entry_rect, value, active=active)
            y = entry_rect.bottom + self.u(10)
            y = self.draw_wrapped_text(
                "Shown to your partner in the lobby and over your head in the "
                "dungeon. Kept between sessions.",
                self.g.small_font,
                self.MUTED,
                pygame.Rect(content.x, y, content.width, self.u(46)),
            ) + self.u(8)
            footer = "Type your name · Enter continues · Esc returns to title"
        elif step == "role":
            rows: list[MenuRow] = [
                ("H", "Host a new run", ""),
                ("J", "Join a run", ""),
            ]
            rows_rect = pygame.Rect(
                content.x, y, content.width, self.u(120)
            )
            rendered = self.draw_menu_rows(
                rows,
                rows_rect,
                selected_index=getattr(self.g, "mp_setup_role_cursor", 0),
            )
            rows_rects = list(rendered)
            y = (rendered[-1].bottom if rendered else rows_rect.bottom) + self.u(12)
            endpoint = (
                f"{self.g.mp_server_host}:{self.g.mp_server_port}"
                if self.g.mp_endpoint_configured()
                else "not configured — set it in Options"
            )
            y = self.draw_wrapped_text(
                f"Server: {endpoint}",
                self.g.small_font,
                self.MUTED if self.g.mp_endpoint_configured() else self.WARNING,
                pygame.Rect(content.x, y, content.width, self.u(40)),
            ) + self.u(6)
            y = self.draw_wrapped_text(
                f"Descending as {self.g.mp_player_name or 'Warden'}.",
                self.g.small_font,
                self.MUTED,
                pygame.Rect(content.x, y, content.width, self.u(24)),
            ) + self.u(6)
            footer = "Arrows select · Enter confirms · Backspace returns"
        elif step == "host_code":
            code = getattr(self.g, "mp_run_id", "")
            self.draw_text(
                " ".join(code) if code else "----",
                self.g.title_font,
                self.accent(),
                pygame.Rect(content.x, y, content.width, self.u(70)),
                align="center",
            )
            y += self.u(78)
            y = self.draw_wrapped_text(
                "Share this code with your partner, then begin the descent to "
                "open the lobby. The code locates your run on the server; it "
                "is not a secret vault.",
                self.g.small_font,
                self.MUTED,
                pygame.Rect(content.x, y, content.width, self.u(52)),
            ) + self.u(10)
            rows = [
                ("Enter", "Begin descent", ""),
                ("R", "Draw a new code", ""),
            ]
            rendered = self.draw_menu_rows(
                rows,
                pygame.Rect(content.x, y, content.width, self.u(112)),
                selected_index=0,
            )
            rows_rects = list(rendered)
            y = (rendered[-1].bottom if rendered else y) + self.u(10)
            footer = "Enter opens the lobby · R redraws · Backspace returns"
        else:  # join_code
            active = bool(
                session is not None and session.target == "mp_join_code"
            )
            value = (
                session.value
                if active and session is not None
                else getattr(self.g, "mp_join_code", "")
            )
            entry_rect = pygame.Rect(
                content.x + (content.width - min(content.width, self.u(340))) // 2,
                y + self.u(8),
                min(content.width, self.u(340)),
                self.u(64),
            )
            self._draw_text_entry_field(
                entry_rect, value, active=active, big=True, letter_spaced=True
            )
            y = entry_rect.bottom + self.u(12)
            y = self.draw_wrapped_text(
                f"A run code is {MP_RUN_ID_LENGTH} runes from the host's lobby "
                "(no 0, O, 1, or I).",
                self.g.small_font,
                self.MUTED,
                pygame.Rect(content.x, y, content.width, self.u(40)),
            ) + self.u(8)
            footer = "Type the code · Enter joins · Esc steps back"

        notice_rect = pygame.Rect(
            content.x, y, content.width, max(1, content.bottom - y)
        )
        self._draw_mp_notice_lines(notice_rect)
        self.g._mp_row_rects = tuple(rows_rects)
        self.g._mp_entry_rect = entry_rect.copy() if entry_rect else None
        self.draw_footer(panel, footer)

    def draw_mp_lobby(self) -> None:
        panel, content = self.menu_frame(
            "The Lobby of Two", "Both must bind an archetype to descend"
        )
        code = self._mp_session_value("run_id", getattr(self.g, "mp_run_id", ""))
        role = self._mp_session_value("role", "")
        local_ready = bool(self._mp_session_value("local_ready", False))
        partner_name = self._mp_session_value("partner_name", "")
        partner_ready = bool(self._mp_session_value("partner_ready", False))
        partner_archetype = self._mp_session_value("partner_archetype", "")
        pending_accept = bool(
            role == "host"
            and self._mp_session_value("partner_pending_accept", False)
        )
        y = content.y
        if code:
            self.draw_text(
                " ".join(code),
                self.g.big_font,
                self.accent(),
                pygame.Rect(content.x, y, content.width, self.u(50)),
                align="center",
            )
            y += self.u(56)
        local_name = self.g.mp_player_name or "You"
        local_value = (
            f"{self.g.selected_archetype.name} · "
            + ("Ready" if local_ready else "Choosing")
        )
        if pending_accept:
            partner_value = "Knocking…"
        elif partner_name:
            partner_value = (
                f"{partner_archetype} · Ready"
                if partner_ready and partner_archetype
                else ("Ready" if partner_ready else "Choosing…")
            )
        else:
            partner_value = "Awaiting partner…"
        rows: list[MenuRow] = [
            ("You" if role != "host" else "Host", local_name, local_value),
            (
                "Partner",
                partner_name or "—",
                partner_value,
            ),
        ]
        if pending_accept:
            rows.append(("Enter", f"Admit {partner_name or 'the stranger'}", ""))
            rows.append(("D", "Turn them away", ""))
        rendered = self.draw_menu_rows(
            rows,
            pygame.Rect(
                content.x,
                y,
                content.width,
                self.u(112 if not pending_accept else 208),
            ),
            selected_index=0,
        )
        y = (rendered[-1].bottom if rendered else y) + self.u(12)
        if pending_accept:
            y = self.draw_wrapped_text(
                "The run code is a locator, not a secret — admit only the "
                "name you shared it with.",
                self.g.small_font,
                self.TEXT,
                pygame.Rect(content.x, y, content.width, self.u(44)),
            ) + self.u(8)
        elif not local_ready:
            y = self.draw_wrapped_text(
                f"Archetype: {self.g.selected_archetype.name} — Left/Right "
                "changes it, Enter binds it and marks you ready.",
                self.g.small_font,
                self.TEXT,
                pygame.Rect(content.x, y, content.width, self.u(44)),
            ) + self.u(8)
        else:
            y = self.draw_wrapped_text(
                "Bound. The descent begins when both stand ready.",
                self.g.small_font,
                self.TEXT,
                pygame.Rect(content.x, y, content.width, self.u(26)),
            ) + self.u(8)
        self._draw_mp_notice_lines(
            pygame.Rect(content.x, y, content.width, max(1, content.bottom - y))
        )
        self.g._mp_row_rects = tuple(rendered)
        self.g._mp_entry_rect = None
        self.draw_footer(
            panel,
            "Enter admits · D turns away · Backspace leaves"
            if pending_accept
            else "Left / Right choose archetype · Enter readies · Backspace leaves",
        )

    def draw_text_input_overlay(self) -> None:
        """Modal entry panel for text edited outside its own screen
        (currently the Options server host/port rows)."""

        session = getattr(self.g, "text_input", None)
        if session is None:
            return
        width, height = self.screen.get_size()
        veil = pygame.Surface((width, height), pygame.SRCALPHA)
        veil.fill((6, 5, 9, 150))
        self.screen.blit(veil, (0, 0))
        box_w = min(width - self.u(40), self.u(460))
        box_h = self.u(150)
        box = pygame.Rect(
            (width - box_w) // 2, (height - box_h) // 2, box_w, box_h
        )
        self.panel(box, alpha=242)
        inner = box.inflate(-self.u(28), -self.u(24))
        self.draw_text(
            session.prompt,
            self.g.font,
            self.TITLE,
            pygame.Rect(inner.x, inner.y, inner.width, self.u(26)),
        )
        entry = pygame.Rect(
            inner.x, inner.y + self.u(32), inner.width, self.u(44)
        )
        self._draw_text_entry_field(entry, session.value, active=True)
        hint_y = entry.bottom + self.u(8)
        if session.help_text:
            hint_y = self.draw_wrapped_text(
                session.help_text,
                self.g.tiny_font,
                self.MUTED,
                pygame.Rect(
                    inner.x, hint_y, inner.width, max(1, inner.bottom - hint_y)
                ),
            )
        self.draw_text(
            "Enter confirms · Esc cancels",
            self.g.tiny_font,
            self.MUTED,
            pygame.Rect(
                inner.x,
                inner.bottom - self.g.tiny_font.get_height(),
                inner.width,
                self.g.tiny_font.get_height(),
            ),
            align="right",
        )
        self.g._mp_entry_rect = entry.copy()
