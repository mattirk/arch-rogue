# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
"""Load bundled license/notice text for the in-app Open Source Licenses screen.

4.3.17 WS-G: APK installers never see the repository, so Apache-2.0 §4
attribution is satisfied by bundling the license text and third-party NOTICE as
reachable assets (``assets/licenses/LICENSE.txt`` / ``NOTICE.txt``) and
surfacing them from the About screen. This loader reads the bundled assets
first and falls back to the repository-root ``LICENSE`` / ``NOTICE`` files for
desktop development runs that have not yet refreshed the asset copies.

The asset copies are regenerated from the canonical root files by
``tools/build_android.sh`` before each build so the in-app text can never drift
from the repository source of truth.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_ASSETS_DIR = Path(__file__).resolve().parent / "assets" / "licenses"
# src/arch_rogue/licenses.py -> src/arch_rogue -> src -> repo root.
_REPO_ROOTS = (
    Path(__file__).resolve().parents[2],
    Path(__file__).resolve().parents[3],
)

_AI_PROVENANCE_TEXT = (
    "AI Provenance & Liability Notice: This game contains code generated, "
    "assisted, or refactored by Artificial Intelligence models. Provided "
    'strictly "AS IS" under Apache License 2.0 with no warranty of clean IP '
    "provenance or non-infringement; downstream users assume all legal and "
    "financial risk and should perform their own compliance audits."
)


def _read_text(asset_name: str, repo_name: str) -> str:
    bundled = _ASSETS_DIR / asset_name
    try:
        if bundled.is_file():
            return bundled.read_text(encoding="utf-8")
    except OSError:
        pass
    for root in _REPO_ROOTS:
        candidate = root / repo_name
        try:
            if candidate.is_file():
                return candidate.read_text(encoding="utf-8")
        except OSError:
            continue
    return ""


@lru_cache(maxsize=None)
def license_text() -> str:
    """The full Apache License 2.0 text."""

    return _read_text("LICENSE.txt", "LICENSE")


@lru_cache(maxsize=None)
def notice_text() -> str:
    """The third-party NOTICE list + Freetype note + AI Provenance notice."""

    return _read_text("NOTICE.txt", "NOTICE")


@lru_cache(maxsize=None)
def pygame_lgpl_text() -> str:
    """The LGPL-2.1-or-later text shipped for pygame-ce."""

    return _read_text("LGPL-2.1.txt", "LGPL-2.1.txt")


def ai_provenance_text() -> str:
    """A short standalone AI Provenance & Liability summary."""

    return _AI_PROVENANCE_TEXT


def license_bundle_available() -> bool:
    """True when at least one of the bundled/repo license texts is reachable."""

    return bool(license_text()) or bool(notice_text())


def clear_cache() -> None:
    """Reset the cached license/notice text (used by tests)."""

    license_text.cache_clear()
    notice_text.cache_clear()
    pygame_lgpl_text.cache_clear()