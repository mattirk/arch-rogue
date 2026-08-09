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

"""Steam Deck hardware detection (Phase 7a — Deck readiness).

The Steam Deck runs SteamOS 3 (Arch-based) on top of a custom AMD APU. It is
exposed to user space as a normal Linux desktop, so the only reliable way to
tell "this is a Deck" from inside a game is to read the DMI product identifiers
that Valve populates:

* ``/sys/devices/virtual/dmi/id/board_vendor``  → ``Valve``
* ``/sys/devices/virtual/dmi/id/product_name``   → ``Jupiter``  (LCD Deck)
                                                    ``Galileo``  (OLED Deck)

Both files are world-readable on SteamOS. Off-Linux the DMI sysfs tree does not
exist, so the probes return ``False`` and the game treats the host as a regular
desktop — which is the correct behaviour on Windows, macOS, and non-Deck Linux
machines that happen to ship the Steam client.

The result is cached per process after the first probe; DMI does not change at
runtime. An explicit environment override
(``ARCH_ROGUE_STEAM_DECK=1`` / ``=0``) wins over the DMI probe so Deck-specific
behaviour can be forced on or off for development and CI without a real Deck.

This module is deliberately tiny and dependency-free (stdlib only, no Pygame
import) so it can be called from ``Game.__init__`` before the display subsystem
starts — the Deck-aware display and graphics-tier defaults need the answer
before ``apply_display_mode`` runs.
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache

__all__ = ("is_steam_deck", "steam_deck_model", "clear_detection_cache")


# Valve's DMI product names for the Steam Deck line. Galileo is the OLED
# revision; Jupiter is the original LCD Deck. Future revisions are expected to
# keep the ``Valve`` board vendor, so detection keys on the vendor first and
# treats any matching product name as a Deck.
_DECK_PRODUCT_NAMES: frozenset[str] = frozenset({"Jupiter", "Galileo"})

# World-readable DMI sysfs paths. Resolved lazily so import never fails on a
# platform without /sys (Windows, macOS, Android).
_BOARD_VENDOR_PATH = "/sys/devices/virtual/dmi/id/board_vendor"
_PRODUCT_NAME_PATH = "/sys/devices/virtual/dmi/id/product_name"

# Environment override: 1/true force-on, 0/false force-off, anything else falls
# back to the DMI probe. Useful on dev machines and in CI.
_OVERRIDE_ENV = "ARCH_ROGUE_STEAM_DECK"


def _truthy(value: str) -> bool | None:
    """Map an env value to a tri-state bool. Unknown → None (use DMI)."""

    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    return None


def _read_dmi_field(path: str) -> str | None:
    """Read a single DMI sysfs field, stripped. None if missing or unreadable."""

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read().strip() or None
    except (OSError, ValueError):
        return None


@lru_cache(maxsize=1)
def _detect() -> tuple[bool, str | None]:
    """Return ``(is_deck, model)``. Cached per process; DMI does not change."""

    override = _truthy(os.environ.get(_OVERRIDE_ENV, ""))
    if override is True:
        return True, None
    if override is False:
        return False, None

    # Off-Linux there is no /sys DMI tree. Keep this check first so Windows,
    # macOS, and Android short-circuit without a filesystem probe.
    if sys.platform not in {"linux", "linux2"}:
        return False, None

    vendor = _read_dmi_field(_BOARD_VENDOR_PATH)
    if vendor is None or vendor.casefold() != "valve":
        return False, None

    product = _read_dmi_field(_PRODUCT_NAME_PATH)
    if product is None or product not in _DECK_PRODUCT_NAMES:
        # Valve has shipped other hardware (Index HMD, Steam Deck devkits with
        # bespoke DMI); only the consumer Deck product names are recognised so
        # a non-Deck Valve device does not pick up Deck defaults.
        return False, None

    return True, product


def is_steam_deck() -> bool:
    """True when the process is running on a Steam Deck (or forced on via env)."""

    return _detect()[0]


def steam_deck_model() -> str | None:
    """The DMI product name (``"Jupiter"`` or ``"Galileo"``) when on a Deck.

    Returns ``None`` when not on a Deck or when Deck behaviour was forced on
    through ``ARCH_ROGUE_STEAM_DECK=1`` without a real Deck underneath.
    """

    return _detect()[1]


def clear_detection_cache() -> None:
    """Drop the cached DMI probe result. Tests use this between cases."""

    _detect.cache_clear()