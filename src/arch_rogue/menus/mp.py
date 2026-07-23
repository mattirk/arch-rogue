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

import hashlib

import pygame

from ..constants import MP_RUN_ID_LENGTH
from ..content import ARCHETYPES

MenuRow = tuple[str, str, str]

# Source geometry of the PixelLab-authored code/seal panels: authored pixel
# size and the glyph well rects inside each, used to seat glyph sprites at
# any on-screen panel scale.
_MP_CODE_PANEL_SRC = (669, 261)
_MP_CODE_PANEL_SLOTS = (
    (53, 74, 112, 112),
    (203, 74, 112, 112),
    (354, 74, 112, 112),
    (504, 74, 112, 112),
)
_MP_SEAL_PANEL_SRC = (378, 172)
_MP_SEAL_PANEL_SLOTS = (
    (37, 27, 116, 116),
    (224, 27, 116, 116),
)
# The mobile archetype carousel frame (menus/mp_carousel_panel.png): the
# authored ‹ › handle plates and the open content area between them.
_MP_CAROUSEL_SRC = (652, 294)
_MP_CAROUSEL_LEFT = (13, 16, 82, 254)
_MP_CAROUSEL_RIGHT = (557, 16, 82, 254)
_MP_CAROUSEL_CONTENT = (112, 30, 428, 234)
# Its arrow-less sibling (menus/mp_plain_panel.png) for panels that are not
# carousels — the bound local hero and the remote player.
_MP_PLAIN_SRC = (602, 194)
_MP_PLAIN_CONTENT = (30, 24, 542, 146)

# Sigils eligible for the verification seal. The order is FROZEN: both peers
# derive the seal from this tuple, so reordering or renaming entries breaks
# seal agreement between client versions. (More sigil sprites exist under
# ``menu.glyph.sigil.*`` than are listed here — only distinct, easily named
# shapes participate, so players can compare seals out loud.)
_MP_SEAL_SIGILS = (
    "serpent",
    "hammer",
    "skull",
    "star",
    "cross",
    "flame",
    "key",
    "map",
    "shield",
    "sword",
    "claw",
    "sun",
    "moon",
    "dragon",
    "phoenix",
    "ouroboros",
    "clock",
    "infinity",
)


def _mp_code_seal(code: str) -> tuple[str, str]:
    """Two sigils deterministically derived from a run code.

    Host and joiner derive the same pair from the same code, so comparing
    the seal plaques catches a mistyped code before the descent begins.
    """

    digest = hashlib.sha256(code.strip().upper().encode("utf-8")).digest()
    count = len(_MP_SEAL_SIGILS)
    return (
        _MP_SEAL_SIGILS[digest[0] % count],
        _MP_SEAL_SIGILS[digest[1] % count],
    )


class MenuMultiplayerMixin:
    """Renderers for the 4.6 ``mp_setup`` and ``mp_lobby`` screens.

    Both screens publish their row/entry hitboxes on the Game object
    (``_mp_row_rects``, ``_mp_entry_rect``) so mobile taps land on exactly
    the rendered geometry, mirroring the title/options pattern.
    """

    # Verdant "stand ready" green — the one lobby state that must read at a
    # glance; every other status keeps the shared gold/muted palette.
    READY = (118, 190, 122)

    def _draw_mp_ready_badge(
        self, row: pygame.Rect, text: str, color
    ) -> None:
        """A small outlined status chip on the right edge of a lobby row."""

        font = self.g.small_font
        pad_x = self.u(10)
        badge = pygame.Rect(
            0, 0, font.size(text)[0] + pad_x * 2, font.get_height() + self.u(6)
        )
        safe = self.ui_content_rect("menu.row", row)
        right = (safe.right if safe is not None else row.right) - self.u(10)
        badge.midright = (right, row.centery)
        # Opaque base first: the chip may cover the tail of a long row label
        # and must stay readable on top of it.
        pygame.draw.rect(
            self.screen, self.PANEL_INK, badge, border_radius=self.u(5)
        )
        fill = pygame.Surface(badge.size, pygame.SRCALPHA)
        pygame.draw.rect(
            fill, (*color, 44), fill.get_rect(), border_radius=self.u(5)
        )
        self.screen.blit(fill, badge)
        pygame.draw.rect(
            self.screen, color, badge, max(1, self.u(1)),
            border_radius=self.u(5),
        )
        self.draw_text(text, font, color, badge, align="center", valign="center")

    def _draw_mp_archetype_panel(
        self,
        rect: pygame.Rect,
        title: str,
        archetype,
        *,
        accented: bool,
        empty_text: str = "",
        carousel: bool = False,
    ) -> tuple[pygame.Rect, pygame.Rect] | None:
        """One preview panel: idling hero sprite beside compact stats.

        ``carousel=True`` (mobile, archetype still changeable) frames the
        panel with the PixelLab carousel art whose authored ‹ › handles are
        returned as screen rects; otherwise the plain inset panel is used
        and None is returned. ``archetype`` may be None (guest not bound
        yet) — the panel then shows ``empty_text`` instead of a sprite.
        """

        arrows: tuple[pygame.Rect, pygame.Rect] | None = None
        safe: pygame.Rect | None = None
        if carousel:
            panel = self.ui_asset("menu.panel.mp_carousel", rect.size)
            if panel is not None:
                self.screen.blit(panel, rect)
                src_w, src_h = _MP_CAROUSEL_SRC
                fx = rect.width / src_w
                fy = rect.height / src_h

                def scaled_box(
                    box: tuple[int, int, int, int]
                ) -> pygame.Rect:
                    return pygame.Rect(
                        rect.x + round(box[0] * fx),
                        rect.y + round(box[1] * fy),
                        round(box[2] * fx),
                        round(box[3] * fy),
                    )

                safe = scaled_box(_MP_CAROUSEL_CONTENT).inflate(
                    -self.u(8), -self.u(6)
                )
                arrows = (
                    scaled_box(_MP_CAROUSEL_LEFT),
                    scaled_box(_MP_CAROUSEL_RIGHT),
                )
        if safe is None and not carousel:
            panel = self.ui_asset("menu.panel.mp_plain", rect.size)
            if panel is not None:
                self.screen.blit(panel, rect)
                src_w, src_h = _MP_PLAIN_SRC
                fx = rect.width / src_w
                fy = rect.height / src_h
                safe = pygame.Rect(
                    rect.x + round(_MP_PLAIN_CONTENT[0] * fx),
                    rect.y + round(_MP_PLAIN_CONTENT[1] * fy),
                    round(_MP_PLAIN_CONTENT[2] * fx),
                    round(_MP_PLAIN_CONTENT[3] * fy),
                ).inflate(-self.u(8), -self.u(6))
        if safe is None:
            safe, _ = self.inset_panel(
                rect, self.accent() if accented else None
            )
            # Breathing room past the nine-slice content insets — the
            # header must not hug the panel border.
            safe = safe.inflate(-self.u(16), -self.u(12))
            if carousel:
                # Carousel art unavailable (legacy graphics): procedural
                # ‹ › plates on the panel edges instead.
                arrow_h = min(self.u(44), rect.height - self.u(16))
                arrow_w = self.u(30)
                left = pygame.Rect(0, 0, arrow_w, arrow_h)
                left.midleft = (rect.x + self.u(4), rect.centery)
                right = pygame.Rect(0, 0, arrow_w, arrow_h)
                right.midright = (rect.right - self.u(4), rect.centery)
                self._draw_mp_arch_arrow_button(left, -1)
                self._draw_mp_arch_arrow_button(right, 1)
                arrows = (left, right)
        header_h = self.g.small_font.get_height() + self.u(4)
        self.draw_text(
            title,
            self.g.small_font,
            self.TITLE,
            pygame.Rect(safe.x, safe.y, safe.width, header_h),
        )
        body = pygame.Rect(
            safe.x,
            safe.y + header_h,
            safe.width,
            max(1, safe.height - header_h),
        )
        if archetype is None:
            self.draw_text(
                empty_text,
                self.g.small_font,
                self.MUTED,
                body,
                align="center",
                valign="center",
            )
            return arrows
        # Sprite hugs the left edge, stats immediately beside it — the
        # panel stays as narrow as its content.
        sprite_box = pygame.Rect(
            body.x,
            body.y,
            min(self.u(56), max(self.u(40), body.width * 3 // 10)),
            body.height,
        )
        surface = None
        try:
            surface = self.g.sprites.player_visual(
                archetype.name,
                "idle",
                0.0,
                self.g.ui_elapsed,
                direction=self.archetype_preview_direction(archetype),
            ).surface
        except Exception:
            surface = None
        if surface is not None and surface.get_width() > 0:
            factor = min(
                sprite_box.width / surface.get_width(),
                sprite_box.height / surface.get_height(),
            )
            scaled = pygame.transform.scale(
                surface,
                (
                    max(1, round(surface.get_width() * factor)),
                    max(1, round(surface.get_height() * factor)),
                ),
            )
            self.screen.blit(
                scaled,
                scaled.get_rect(
                    midbottom=(sprite_box.centerx, sprite_box.bottom)
                ),
            )
        stats = (
            f"HP {archetype.max_hp} · Mana {archetype.max_mana}",
            f"Stamina {archetype.max_stamina} · Speed {archetype.speed:.2f}",
            f"Melee +{archetype.melee_bonus} · Spell +{archetype.spell_bonus}"
            f" · Armor +{archetype.armor_bonus}",
        )
        stats_x = sprite_box.right + self.u(10)
        stats_width = safe.right - stats_x
        if any(
            self.g.tiny_font.size(line)[0] > stats_width for line in stats
        ):
            stats = (
                f"HP {archetype.max_hp} · MP {archetype.max_mana}",
                f"ST {archetype.max_stamina} · SPD {archetype.speed:.2f}",
                f"ML +{archetype.melee_bonus}"
                f" · SP +{archetype.spell_bonus}",
                f"AR +{archetype.armor_bonus}",
            )
        line_h = self.g.tiny_font.get_height() + self.u(4)
        stats_y = body.y + max(0, (body.height - line_h * len(stats)) // 2)
        for line in stats:
            self.draw_text(
                line,
                self.g.tiny_font,
                self.TEXT,
                pygame.Rect(
                    stats_x, stats_y, max(1, safe.right - stats_x), line_h
                ),
            )
            stats_y += line_h
        return arrows

    def _draw_mp_arch_arrow_button(
        self, rect: pygame.Rect, direction: int
    ) -> None:
        """A tappable ‹ › plate on the hero panel's edge (mobile carousel)."""

        pygame.draw.rect(
            self.screen, self.PANEL_INK, rect, border_radius=self.u(6)
        )
        pygame.draw.rect(
            self.screen,
            self.accent(),
            rect,
            max(1, self.u(1)),
            border_radius=self.u(6),
        )
        cx, cy = rect.center
        size = min(rect.width, rect.height) // 4
        offset = size // 2
        if direction < 0:
            points = [
                (cx + offset, cy - size),
                (cx - offset, cy),
                (cx + offset, cy + size),
            ]
        else:
            points = [
                (cx - offset, cy - size),
                (cx + offset, cy),
                (cx - offset, cy + size),
            ]
        pygame.draw.lines(
            self.screen, self.accent(), False, points, max(2, self.u(2))
        )

    def _draw_mp_lobby_archetype_panels(
        self, rect: pygame.Rect, *, stacked: bool
    ) -> None:
        """The two hero preview panels (you / partner) inside ``rect``,
        stacked vertically beside the rows or side by side below them."""

        gap = self.u(10)
        if stacked:
            each_h = (rect.height - gap) // 2
            if each_h < self.u(56) or rect.width < self.u(180):
                return
            rects = (
                pygame.Rect(rect.x, rect.y, rect.width, each_h),
                pygame.Rect(
                    rect.x, rect.y + each_h + gap, rect.width, each_h
                ),
            )
        else:
            if rect.height < self.u(64):
                return
            each_w = (rect.width - gap) // 2
            rects = (
                pygame.Rect(rect.x, rect.y, each_w, rect.height),
                pygame.Rect(
                    rect.x + each_w + gap, rect.y, each_w, rect.height
                ),
            )
        role = self._mp_session_value("role", "")
        partner_name = self._mp_session_value("partner_name", "")
        partner_archetype_name = self._mp_session_value(
            "partner_archetype", ""
        )
        partner_archetype = next(
            (a for a in ARCHETYPES if a.name == partner_archetype_name),
            None,
        )
        local_role = "You" if role != "host" else "Host"
        remote_label = "Host" if role == "join" else "Guest"
        # While the archetype can still change, the local panel is a
        # carousel with authored ‹ › handles — tappable on mobile,
        # clickable on desktop.
        local_ready = bool(self._mp_session_value("local_ready", False))
        pending_accept = bool(
            role == "host"
            and self._mp_session_value("partner_pending_accept", False)
        )
        carousel = not local_ready and not pending_accept
        arrows = self._draw_mp_archetype_panel(
            rects[0],
            f"{local_role} — {self.g.selected_archetype.name}",
            self.g.selected_archetype,
            accented=True,
            carousel=carousel,
        )
        if arrows is not None:
            left, right = arrows
            self.g._mp_lobby_arch_arrows = (
                (-1, left.inflate(self.u(16), self.u(16))),
                (1, right.inflate(self.u(16), self.u(16))),
            )
        self._draw_mp_archetype_panel(
            rects[1],
            f"{remote_label} — {partner_archetype.name}"
            if partner_archetype
            else remote_label,
            partner_archetype,
            accented=False,
            empty_text=(
                "Awaiting their bond…"
                if partner_name
                else "The gate stands empty"
            ),
        )

    def _draw_text_entry_field(
        self,
        rect: pygame.Rect,
        value: str,
        *,
        active: bool,
        big: bool = False,
        letter_spaced: bool = False,
        publish: bool = True,
    ) -> None:
        """One shared single-line entry box with a blinking caret.

        ``publish=False`` keeps a purely decorative copy (the field dimmed
        behind the mobile entry panel) from fighting the live editor over the
        SDL IME rect.
        """

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
        if publish:
            self.g.publish_text_input_rect(rect)

    @staticmethod
    def _session_display_value(session) -> str:
        """Committed text plus any uncommitted IME composition, length-capped."""

        return (session.value + session.composition)[: session.max_length]

    def _mobile_entry_panel_live(self, session) -> bool:
        """Whether the keyboard-safe mobile panel is the session's live editor."""

        return bool(getattr(self.g, "mobile_mode", False)) and session is not None

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

    @staticmethod
    def _seal_caption(names: tuple[str, str]) -> str:
        return " · ".join(name.replace("_", " ").title() for name in names)

    def _draw_mp_sigil_wells(
        self, rect: pygame.Rect, names: tuple[str, str]
    ) -> None:
        """Seat the seal's sigil sprites in the plaque's medallion wells."""

        src_w, src_h = _MP_SEAL_PANEL_SRC
        fx = rect.width / src_w
        fy = rect.height / src_h
        for (sx, sy, sw, sh), name in zip(_MP_SEAL_PANEL_SLOTS, names):
            slot = pygame.Rect(
                rect.x + round(sx * fx),
                rect.y + round(sy * fy),
                round(sw * fx),
                round(sh * fy),
            )
            # Circular wells need more breathing room than square ones.
            box = slot.inflate(-slot.width * 2 // 7, -slot.height * 2 // 7)
            glyph = self.ui_asset(f"menu.glyph.sigil.{name}", box.size)
            if glyph is not None:
                self.screen.blit(glyph, glyph.get_rect(center=slot.center))

    def _draw_mp_seal_plaque(
        self, content: pygame.Rect, y: int, code: str, *, reserve: int
    ) -> int:
        """The two-sigil verification seal on its own small plaque.

        Used by the join screen to preview the seal of the typed code.
        Falls back to a named text seal when asset UI is unavailable.
        """

        names = _mp_code_seal(code)
        avail = content.bottom - y - reserve
        src_w, src_h = _MP_SEAL_PANEL_SRC
        height = min(self.u(92), avail, content.width * src_h // src_w)
        plaque = (
            self.ui_asset(
                "menu.panel.mp_seal", (round(height * src_w / src_h), height)
            )
            if height >= self.u(40)
            else None
        )
        if plaque is None:
            return self.draw_wrapped_text(
                f"Seal: {self._seal_caption(names)}",
                self.g.small_font,
                self.accent(),
                pygame.Rect(content.x, y, content.width, self.u(24)),
            ) + self.u(4)
        rect = plaque.get_rect(midtop=(content.centerx, y))
        self.screen.blit(plaque, rect)
        self._draw_mp_sigil_wells(rect, names)
        return rect.bottom + self.u(8)

    def _draw_mp_code_panel(
        self,
        content: pygame.Rect,
        y: int,
        code: str,
        *,
        reserve: int,
        big: bool = True,
    ) -> int:
        """The run code as brass glyph sprites in the stone code panel, with
        the verification seal plaque seated beside (or under) it.

        ``reserve`` is the vertical space to keep free below for the rest of
        the screen — the panels shrink to honour it. Falls back to the
        letter-spaced accent text and a named text seal when the asset UI is
        off or there is no room for readable art.
        """

        code = (code or "").strip().upper()[:MP_RUN_ID_LENGTH]
        show_seal = len(code) == MP_RUN_ID_LENGTH
        names = _mp_code_seal(code) if show_seal else ("", "")
        avail = content.bottom - y - reserve
        code_w, code_h = _MP_CODE_PANEL_SRC
        seal_w, seal_h = _MP_SEAL_PANEL_SRC
        gap = self.u(10)
        code_aspect = code_w / code_h
        seal_aspect = seal_w / seal_h
        side = show_seal and content.width >= self.u(430)
        total_aspect = code_aspect + (seal_aspect if side else 0.0)
        height = min(
            self.u(92),
            avail if not (show_seal and not side) else (avail - gap) * 5 // 8,
            int((content.width - (gap if side else 0)) / total_aspect),
        )
        panel = (
            self.ui_asset(
                "menu.panel.mp_code", (round(height * code_aspect), height)
            )
            if height >= self.u(42)
            else None
        )
        if panel is None:
            font = self.g.title_font if big else self.g.big_font
            text_h = self.u(70 if big else 50)
            self.draw_text(
                " ".join(code) if code else "----",
                font,
                self.accent(),
                pygame.Rect(content.x, y, content.width, text_h),
                align="center",
            )
            y += text_h + self.u(6)
            if show_seal:
                y = self.draw_wrapped_text(
                    f"Seal: {self._seal_caption(names)}",
                    self.g.small_font,
                    self.accent(),
                    pygame.Rect(content.x, y, content.width, self.u(24)),
                ) + self.u(4)
            return y
        code_rect = pygame.Rect(0, y, round(height * code_aspect), height)
        seal_rect: pygame.Rect | None = None
        if side:
            seal_rect = pygame.Rect(0, y, round(height * seal_aspect), height)
            total_w = code_rect.width + gap + seal_rect.width
            code_rect.x = content.x + (content.width - total_w) // 2
            seal_rect.x = code_rect.right + gap
        else:
            code_rect.x = content.x + (content.width - code_rect.width) // 2
            if show_seal:
                sub_h = max(self.u(40), height * 5 // 8)
                seal_rect = pygame.Rect(
                    0,
                    code_rect.bottom + gap,
                    round(sub_h * seal_aspect),
                    sub_h,
                )
                seal_rect.centerx = content.centerx
        self.screen.blit(panel, code_rect)
        fx = code_rect.width / code_w
        fy = code_rect.height / code_h
        for (sx, sy, sw, sh), ch in zip(_MP_CODE_PANEL_SLOTS, code):
            slot = pygame.Rect(
                code_rect.x + round(sx * fx),
                code_rect.y + round(sy * fy),
                round(sw * fx),
                round(sh * fy),
            )
            box = slot.inflate(-slot.width // 7, -slot.height // 7)
            glyph = self.ui_asset(f"menu.glyph.code.{ch.lower()}", box.size)
            if glyph is not None:
                self.screen.blit(glyph, glyph.get_rect(center=slot.center))
            else:
                self.draw_text(
                    ch,
                    self.g.big_font,
                    self.accent(),
                    slot,
                    align="center",
                    valign="center",
                )
        bottom = code_rect.bottom
        if seal_rect is not None:
            plaque = self.ui_asset("menu.panel.mp_seal", seal_rect.size)
            if plaque is not None:
                self.screen.blit(plaque, seal_rect)
                self._draw_mp_sigil_wells(seal_rect, names)
                bottom = max(bottom, seal_rect.bottom)
        return bottom + self.u(10)

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
            ("", "I agree — open the gate", ""),
            ("", "Exit", ""),
        ]
        rendered = self.draw_menu_rows(
            rows,
            rows_rect,
            selected_index=int(getattr(g, "mp_consent_cursor", 0)) % 2,
            keys_in_rows=False,
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
        # On mobile the top-anchored entry panel (drawn after this screen) is
        # the live editor; the embedded field is a dimmed location marker.
        panel_live = self._mobile_entry_panel_live(session)

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
                self._session_display_value(session)
                if active and session is not None
                else getattr(self.g, "mp_player_name", "")
            )
            self._draw_text_entry_field(
                entry_rect,
                value,
                active=active and not panel_live,
                publish=not panel_live,
            )
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
                ("", "Host a new run", ""),
                ("", "Join a run", ""),
            ]
            rows_rect = pygame.Rect(
                content.x, y, content.width, self.u(120)
            )
            rendered = self.draw_menu_rows(
                rows,
                rows_rect,
                selected_index=getattr(self.g, "mp_setup_role_cursor", 0),
                keys_in_rows=False,
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
            footer = "Up / Down select · Enter confirms · Backspace returns"
        elif step == "host_code":
            code = getattr(self.g, "mp_run_id", "")
            y = self._draw_mp_code_panel(
                content, y, code, reserve=self.u(210)
            )
            y = self.draw_wrapped_text(
                "Share this code with your partner, then begin the descent to "
                "open the lobby. Your partner sees the same two seal marks "
                "when the code matches. The code locates your run on the "
                "server; it is not a secret vault.",
                self.g.small_font,
                self.MUTED,
                pygame.Rect(content.x, y, content.width, self.u(72)),
            ) + self.u(10)
            rows = [
                ("", "Begin descent", ""),
                ("", "Draw a new code", ""),
            ]
            rendered = self.draw_menu_rows(
                rows,
                pygame.Rect(content.x, y, content.width, self.u(112)),
                selected_index=int(
                    getattr(self.g, "mp_setup_host_cursor", 0)
                ) % 2,
                keys_in_rows=False,
            )
            rows_rects = list(rendered)
            y = (rendered[-1].bottom if rendered else y) + self.u(10)
            footer = (
                "Up / Down select · Enter confirms · R redraws · "
                "Backspace returns"
            )
        else:  # join_code
            active = bool(
                session is not None and session.target == "mp_join_code"
            )
            value = (
                self._session_display_value(session)
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
                entry_rect,
                value,
                active=active and not panel_live,
                big=True,
                letter_spaced=True,
                publish=not panel_live,
            )
            y = entry_rect.bottom + self.u(12)
            if len(value.strip()) == MP_RUN_ID_LENGTH:
                y = self._draw_mp_seal_plaque(
                    content, y, value, reserve=self.u(110)
                )
                y = self.draw_wrapped_text(
                    "This seal must match the one in the host's lobby.",
                    self.g.small_font,
                    self.MUTED,
                    pygame.Rect(content.x, y, content.width, self.u(24)),
                ) + self.u(6)
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
        pending_accept = bool(
            role == "host"
            and self._mp_session_value("partner_pending_accept", False)
        )
        mobile = bool(getattr(self.g, "mobile_mode", False))
        # Carousel handles are re-published every frame by the panel
        # drawing below; start clean so stale rects never take taps.
        self.g._mp_lobby_arch_arrows = ()
        y = content.y
        if code:
            y = self._draw_mp_code_panel(
                content,
                y,
                code,
                reserve=self.u(280),
                big=False,
            )
        local_name = self.g.mp_player_name or "You"
        local_badge = (
            ("READY", self.READY) if local_ready else ("CHOOSING", self.WARNING)
        )
        if pending_accept:
            partner_badge = ("KNOCKING", self.WARNING)
        elif not partner_name:
            partner_badge = ("AWAITING", self.MUTED)
        elif partner_ready:
            partner_badge = ("READY", self.READY)
        else:
            partner_badge = ("CHOOSING", self.WARNING)
        cursor = int(getattr(self.g, "mp_lobby_cursor", 0)) % 2
        local_role = "You" if role != "host" else "Host"
        # The remote player is your guest when hosting, the host when
        # joining — "partner" never appears in the lobby chrome.
        remote_label = "Host" if role == "join" else "Guest"
        # Archetype names live in the preview panels — the rows carry
        # identity only, keeping clear of the right-edge status chips.
        rows: list[MenuRow] = [
            ("", f"{local_role} · {local_name}", ""),
            (
                "",
                f"{remote_label} · {partner_name}"
                if partner_name
                else remote_label,
                "",
            ),
        ]
        if pending_accept:
            rows.append(("", f"Admit {partner_name or 'the stranger'}", ""))
            rows.append(("", "Turn them away", ""))
            hint = (
                "The run code is a locator, not a secret — admit only the "
                "name you shared it with."
            )
        elif not local_ready:
            awaiting_partner = role == "host" and not partner_name
            if awaiting_partner:
                # The host cannot bind before a guest arrives — never
                # advertise a dead action; the row states what is awaited.
                rows.append(
                    ("", "Binding opens when a guest arrives", "")
                )
                hint = (
                    f"Archetype: {self.g.selected_archetype.name} — "
                    + (
                        "tap ‹ › on your hero panel to change it. "
                        if mobile
                        else "Left/Right changes it. "
                    )
                    + "Share the code; you bind once your guest knocks "
                    "and is admitted."
                )
            else:
                rows.append(
                    (
                        "",
                        f"Bind {self.g.selected_archetype.name} "
                        "and stand ready",
                        "",
                    )
                )
                hint = (
                    f"Archetype: {self.g.selected_archetype.name} — "
                    + (
                        "tap ‹ › on your hero panel to change it, then "
                        f"tap 'Bind {self.g.selected_archetype.name}' "
                        "to stand ready."
                        if mobile
                        else "Left/Right changes it, Enter binds it and "
                        "marks you ready."
                    )
                )
            rows.append(("", "Leave the lobby", ""))
        else:
            rows.append(
                ("", f"Bound — awaiting the {remote_label.lower()}", "")
            )
            rows.append(("", "Leave the lobby", ""))
            hint = "Bound. The descent begins when both stand ready."
        # Wide layouts run two columns — compact rows on the left, the two
        # hero preview panels stacked on the right. Narrow (portrait)
        # layouts keep full-width rows and seat the panels side by side
        # underneath.
        wide = content.width >= self.u(560)
        # The preview panels only need sprite + stat lines — keep them
        # narrow and give the selection rows the leftover width.
        panel_w = min(self.u(280), content.width * 42 // 100)
        rows_width = (
            content.width - panel_w - self.u(12) if wide else content.width
        )
        rows_height = self.u(200)
        # Bottom-anchored chrome, as in the other menus: key hints at the
        # very bottom, notices right above them.
        line_gap = max(self.g.small_font.get_height() + 3, self.u(18))
        hint_lines = self.wrap_text(hint, self.g.small_font, content.width)
        hint_top = max(y, content.bottom - len(hint_lines) * line_gap)
        self.draw_wrapped_text(
            hint,
            self.g.small_font,
            self.TEXT,
            pygame.Rect(
                content.x,
                hint_top,
                content.width,
                max(1, content.bottom - hint_top),
            ),
        )
        has_notice = bool(
            getattr(self.g, "mp_notice", "") or getattr(self.g, "mp_status", "")
        )
        notice_top = hint_top - self.u(4) - (self.u(48) if has_notice else 0)
        # The rows sit directly under the code panel; the panel column then
        # matches their vertical extent exactly.
        rows_y = y
        rendered = self.draw_menu_rows(
            rows,
            pygame.Rect(content.x, rows_y, rows_width, rows_height),
            selected_index=2 + cursor,
            keys_in_rows=False,
            row_height=self.u(40),
            row_gap=self.u(12),
        )
        for row, (badge_text, badge_color) in zip(
            rendered[:2], (local_badge, partner_badge)
        ):
            self._draw_mp_ready_badge(row, badge_text, badge_color)
        rows_bottom = rendered[-1].bottom if rendered else rows_y
        if wide:
            # The panel column spans exactly the rows' vertical extent, so
            # the two columns share top and bottom edges.
            panel_x = content.x + rows_width + self.u(12)
            panel_top = rendered[0].y if rendered else rows_y
            self._draw_mp_lobby_archetype_panels(
                pygame.Rect(
                    panel_x,
                    panel_top,
                    max(1, content.right - panel_x),
                    max(1, rows_bottom - panel_top),
                ),
                stacked=True,
            )
            notice_y = max(y, notice_top)
        else:
            panel_top = rows_bottom + self.u(10)
            # Full-width stacked panels: side-by-side halves are too
            # narrow for the carousel frame and its stat lines.
            self._draw_mp_lobby_archetype_panels(
                pygame.Rect(
                    content.x,
                    panel_top,
                    content.width,
                    min(
                        self.u(226),
                        max(1, notice_top - self.u(6) - panel_top),
                    ),
                ),
                stacked=True,
            )
            notice_y = notice_top
        if has_notice:
            self._draw_mp_notice_lines(
                pygame.Rect(
                    content.x,
                    notice_y,
                    content.width,
                    max(1, hint_top - notice_y),
                )
            )
        self.g._mp_row_rects = tuple(rendered)
        self.g._mp_entry_rect = None
        self.draw_footer(
            panel,
            "Up / Down select · Enter confirms · Backspace leaves"
            if pending_accept
            else "Up / Down select · Left / Right archetype · Enter confirms"
            " · Backspace leaves",
        )

    def draw_text_input_overlay(self) -> None:
        """Modal entry panel for the live text-entry session.

        Desktop: a centered dialog for text edited outside its own screen
        (the Options server host/port rows). Mobile: every session renders
        the keyboard-safe top panel instead — the Android IME slides over
        the bottom of the display, so a fixed top anchor is the one spot
        that stays visible no matter the keyboard height.
        """

        session = getattr(self.g, "text_input", None)
        if session is None:
            return
        if self._mobile_entry_panel_live(session):
            self._draw_mobile_text_input_panel(session)
            return
        self.g._text_input_button_rects = ()
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
        self._draw_text_entry_field(
            entry, self._session_display_value(session), active=True
        )
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

    def _draw_mobile_text_input_panel(self, session) -> None:
        """Keyboard-safe editor pinned to the top of the safe area (mobile).

        Fixed location by design: the soft keyboard owns the bottom of the
        screen, so prompt, field, and buttons all live in the top ~30% and
        stay visible for any keyboard height. The Del/Clear/Cancel/OK touch
        buttons keep editing possible even when the IME never delivers a
        backspace key; their rects are published for the tap router.
        """

        width, height = self.screen.get_size()
        veil = pygame.Surface((width, height), pygame.SRCALPHA)
        veil.fill((6, 5, 9, 150))
        self.screen.blit(veil, (0, 0))
        safe = self.g.mobile_safe_rect()
        pad = self.u(12)
        gap = self.u(8)
        prompt_h = self.g.font.get_height() + self.u(4)
        entry_h = max(44, self.u(46))
        button_h = max(46, self.u(46))
        help_h = (
            self.g.tiny_font.get_height() + self.u(4) if session.help_text else 0
        )
        # The mobile Back button (top-left, drawn above this panel) keeps its
        # role as session cancel; clear its column so neither overlaps it.
        back_clear = max(52, min(68, safe.height // 8)) + self.u(20)
        box_w = min(self.u(560), max(self.u(300), safe.width - back_clear * 2))
        box = pygame.Rect(
            0,
            0,
            min(box_w, safe.width - self.u(8)),
            pad * 2 + prompt_h + self.u(4) + entry_h + gap + button_h + help_h,
        )
        box.midtop = (safe.centerx, safe.y + self.u(6))
        self.panel(box, alpha=242)
        inner = box.inflate(-pad * 2, -pad * 2)
        self.draw_text(
            session.prompt,
            self.g.font,
            self.TITLE,
            pygame.Rect(inner.x, inner.y, inner.width, prompt_h),
        )
        entry = pygame.Rect(
            inner.x, inner.y + prompt_h + self.u(4), inner.width, entry_h
        )
        code_entry = session.target == "mp_join_code"
        self._draw_text_entry_field(
            entry,
            self._session_display_value(session),
            active=True,
            big=code_entry,
            letter_spaced=code_entry,
        )
        labels = (
            ("backspace", "Del"),
            ("clear", "Clear"),
            ("cancel", "Cancel"),
            ("confirm", "OK"),
        )
        button_w = (inner.width - gap * (len(labels) - 1)) // len(labels)
        button_y = entry.bottom + gap
        buttons: list[tuple[str, pygame.Rect]] = []
        for index, (action, label) in enumerate(labels):
            rect = pygame.Rect(
                inner.x + index * (button_w + gap), button_y, button_w, button_h
            )
            pygame.draw.rect(
                self.screen, self.PANEL_INK, rect, border_radius=self.u(6)
            )
            pygame.draw.rect(
                self.screen,
                self.accent() if action == "confirm" else self.PANEL_2,
                rect,
                max(1, self.u(1)),
                border_radius=self.u(6),
            )
            self.draw_text(
                label,
                self.g.font,
                self.TITLE if action == "confirm" else self.TEXT,
                rect,
                align="center",
                valign="center",
            )
            buttons.append((action, rect))
        if session.help_text:
            self.draw_text(
                session.help_text,
                self.g.tiny_font,
                self.MUTED,
                pygame.Rect(
                    inner.x,
                    button_y + button_h + self.u(4),
                    inner.width,
                    self.g.tiny_font.get_height(),
                ),
            )
        self.g._text_input_button_rects = tuple(buttons)
        self.g._mp_entry_rect = entry.copy()
