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

"""Shared single-line text entry (4.6).

There was no reusable menu text-input primitive before multiplayer needed
one; this mixin is now the one helper for player-name, join-code, server-host,
and server-port entry. It owns desktop typing (TEXTINPUT + backspace/confirm/
cancel), input length limits, optional charset filters, and focus cleanup.
On Android it drives the OS soft keyboard through SDL text input
(``pygame.key.start_text_input`` / ``SDL_TEXTINPUT``) and stops it on
confirm, cancel, and focus loss. Composing IMEs stream the pending word
through ``TEXTEDITING`` before committing it; the session tracks that
composition so renderers can show it, and the mobile entry panel exposes
touch buttons (``text_input_backspace`` / ``text_input_clear``) because some
Android keyboards never deliver a backspace key event at all.
"""

from __future__ import annotations

from dataclasses import dataclass

import pygame


@dataclass
class TextInputSession:
    """One active single-line entry field."""

    target: str
    prompt: str
    value: str
    max_length: int
    charset: str | None = None
    uppercase: bool = False
    help_text: str = ""
    # Uncommitted IME composition (Android predictive keyboards). Display
    # only: it is never part of ``value`` until the IME commits TEXTINPUT.
    composition: str = ""


class TextInputMixin:
    """Game-side owner of the single shared text-entry session."""

    def text_input_active(self) -> bool:
        return getattr(self, "text_input", None) is not None

    def open_text_input(
        self,
        *,
        target: str,
        prompt: str,
        initial: str = "",
        max_length: int = 16,
        charset: str | None = None,
        uppercase: bool = False,
        help_text: str = "",
    ) -> None:
        max_length = max(1, int(max_length))
        value = self._filter_text_input(
            str(initial), charset=charset, uppercase=uppercase
        )[:max_length]
        self.text_input = TextInputSession(
            target=target,
            prompt=prompt,
            value=value,
            max_length=max_length,
            charset=charset,
            uppercase=uppercase,
            help_text=help_text,
        )
        self._start_sdl_text_input()

    def close_text_input(self, *, confirm: bool) -> None:
        session = getattr(self, "text_input", None)
        if session is None:
            return
        self.text_input = None
        self._stop_sdl_text_input()
        if confirm:
            self._apply_text_input(session.target, session.value.strip())
        else:
            self._cancel_text_input(session.target)

    def handle_text_input_event(self, event: pygame.event.Event) -> bool:
        """Consume one event for the active session. Returns True if handled."""

        session = getattr(self, "text_input", None)
        if session is None:
            # Focus bookkeeping only matters while a session is live.
            return False
        if event.type == pygame.TEXTINPUT:
            # A commit ends any pending IME composition.
            session.composition = ""
            appended = self._filter_text_input(
                getattr(event, "text", ""),
                charset=session.charset,
                uppercase=session.uppercase,
            )
            if appended:
                session.value = (session.value + appended)[: session.max_length]
            return True
        if event.type == getattr(pygame, "TEXTEDITING", -1):
            # Composing IMEs (Android predictive keyboards, CJK input) stream
            # the uncommitted word here; keep it so the entry field can show
            # what the player is typing (and deleting) before the commit.
            session.composition = self._filter_text_input(
                getattr(event, "text", ""),
                charset=None,
                uppercase=session.uppercase,
            )
            return True
        if event.type == getattr(pygame, "WINDOWFOCUSLOST", -1):
            # The soft keyboard/IME goes away with the window focus; the
            # session itself survives so the player can resume typing.
            self._stop_sdl_text_input()
            return False
        if event.type == getattr(pygame, "WINDOWFOCUSGAINED", -1):
            self._start_sdl_text_input()
            return False
        if event.type != pygame.KEYDOWN:
            return False
        if event.key == pygame.K_BACKSPACE or getattr(event, "unicode", "") == "\b":
            # Some Android IMEs deliver deletion only as a control character
            # on an otherwise unmapped key, so match the unicode too.
            session.composition = ""
            if event.mod & pygame.KMOD_CTRL:
                session.value = ""
            else:
                session.value = session.value[:-1]
            return True
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.close_text_input(confirm=True)
            return True
        if event.key in (pygame.K_ESCAPE, getattr(pygame, "K_AC_BACK", -1)):
            self.close_text_input(confirm=False)
            return True
        if event.key == pygame.K_DELETE:
            session.value = ""
            return True
        # Swallow plain typing keys so state hotkeys underneath the entry
        # field (menu shortcuts) cannot fire while the player is typing;
        # TEXTINPUT delivers the characters themselves.
        if event.mod & (pygame.KMOD_CTRL | pygame.KMOD_ALT | pygame.KMOD_META):
            return False
        return bool(
            event.unicode
            and event.unicode.isprintable()
            or pygame.K_a <= event.key <= pygame.K_z
            or pygame.K_0 <= event.key <= pygame.K_9
            or event.key == pygame.K_SPACE
        )

    # -- touch-button edits (mobile entry panel) ------------------------------

    def text_input_backspace(self) -> None:
        """Delete one trailing character; the panel's Del button uses this so
        deletion never depends on the IME actually sending a backspace key."""

        session = getattr(self, "text_input", None)
        if session is None:
            return
        session.composition = ""
        session.value = session.value[:-1]

    def text_input_clear(self) -> None:
        session = getattr(self, "text_input", None)
        if session is None:
            return
        session.composition = ""
        session.value = ""

    def resume_text_input(self) -> None:
        """Re-summon the soft keyboard for the live session.

        Android hides the IME on system back without telling SDL, leaving an
        active session with no keyboard; tapping the entry field lands here.
        """

        self._start_sdl_text_input()

    # -- integration points ---------------------------------------------------

    def _apply_text_input(self, target: str, value: str) -> None:
        if target == "mp_server_host":
            from .options import normalize_mp_server_host

            self.mp_server_host = normalize_mp_server_host(value)
            self.save_options()
        elif target == "mp_server_port":
            from .options import normalize_mp_server_port

            self.mp_server_port = normalize_mp_server_port(value)
            self.save_options()
        elif target == "mp_player_name":
            self.mp_confirm_player_name(value)
        elif target == "mp_join_code":
            self.mp_submit_join_code(value)

    def _cancel_text_input(self, target: str) -> None:
        if target in ("mp_player_name", "mp_join_code"):
            handler = getattr(self, "mp_text_input_cancelled", None)
            if callable(handler):
                handler(target)

    # -- SDL plumbing ---------------------------------------------------------

    def _start_sdl_text_input(self) -> None:
        if getattr(self, "text_input", None) is None:
            return
        try:
            rect = getattr(self, "_text_input_rect", None)
            if isinstance(rect, pygame.Rect) and rect.width > 0:
                pygame.key.set_text_input_rect(rect)
            pygame.key.start_text_input()
        except (AttributeError, pygame.error):
            pass

    def _stop_sdl_text_input(self) -> None:
        try:
            pygame.key.stop_text_input()
        except (AttributeError, pygame.error):
            pass

    def publish_text_input_rect(self, rect: pygame.Rect) -> None:
        """Renderers report the on-screen entry rect for IME/soft-keyboard
        placement; forwarded to SDL only when it moves."""

        previous = getattr(self, "_text_input_rect", None)
        if previous is not None and previous == rect:
            return
        self._text_input_rect = rect.copy()
        if getattr(self, "text_input", None) is not None:
            try:
                pygame.key.set_text_input_rect(rect)
            except (AttributeError, pygame.error):
                pass

    @staticmethod
    def _filter_text_input(
        text: str, *, charset: str | None, uppercase: bool
    ) -> str:
        cleaned = "".join(
            char
            for char in text
            if char.isprintable() and char not in "\r\n\t"
        )
        if uppercase:
            cleaned = cleaned.upper()
        if charset is not None:
            cleaned = "".join(char for char in cleaned if char in charset)
        return cleaned
