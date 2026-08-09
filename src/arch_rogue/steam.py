# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
"""Optional Steamworks integration for the Steam distribution of the game.

Steam builds are one of several distribution channels (GitHub Releases, itch,
Android, pygbag web), so every entry point here is designed to degrade to a
silent no-op rather than to fail. The facade is unavailable whenever any of the
following is true, and none of them are errors:

* no numeric App ID is configured (see :data:`STEAM_APP_ID` / ``ARCH_ROGUE_STEAM_APPID``),
* the ``steam_api`` shared library is not bundled next to the executable,
* the Steam client is not running or does not own the app,
* the platform is Android or Emscripten.

Only Steam depots ship the shared library, so a GitHub-release build of the very
same executable simply reports ``available == False`` and queues achievement
unlocks locally.

Implementation notes
--------------------
Steamworks has no first-party Python binding. Rather than depend on a
third-party wrapper we bind the SDK's *flat* C API directly with ctypes; we need
a small surface (init, callbacks, ISteamUserStats, ISteamFriends rich presence)
and the flat API is plain C with no C++ ABI concerns.

The flat interface accessors are version-suffixed (``SteamAPI_SteamUserStats_v013``)
and Valve bumps the suffix between SDK releases, so accessors are probed
newest-first from a candidate list instead of being hard-coded. Likewise
``SteamAPI_InitFlat`` (SDK 1.59+) is preferred over the legacy ``SteamAPI_Init``.

The Steamworks SDK binaries are under Valve's redistribution terms and are
deliberately **not** committed to this repository; CI fetches them into
``build/steam/sdk/`` at package time. This module works without them.
"""

from __future__ import annotations

import ctypes
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Iterable, Sequence

LOGGER = logging.getLogger(__name__)

# Numeric Steam App ID, assigned by Valve in App Admin (the number in the
# partner.steamgames.com/apps/landing/<appid> URL). Setting it does not by itself
# enable anything: without the bundled shared library and a running client the
# facade still reports unavailable, which is the correct behaviour for every
# non-Steam channel.
STEAM_APP_ID: int | None = 5031380

APP_ID_ENV = "ARCH_ROGUE_STEAM_APPID"
# Escape hatch for developers and for CI smoke tests that must not touch a real
# Steam client even when one happens to be running on the machine.
DISABLE_ENV = "ARCH_ROGUE_NO_STEAM"

# The full set now lives in assets/achievements.json and is evaluated by
# arch_rogue.achievements. This constant stays because it names the one
# achievement wired by hand in phase 2 and is still the id the catalogue uses for
# a first clear; gameplay code should go through the funnel, not unlock directly.
ACHIEVEMENT_FIRST_CLEAR = "ACH_FIRST_CLEAR"

_QUEUE_FILENAME = ".arch_rogue_steam_queue.json"
_QUEUE_VERSION = 1

_LIBRARY_NAMES: dict[str, tuple[str, ...]] = {
    "win32": ("steam_api64.dll", "steam_api.dll"),
    "darwin": ("libsteam_api.dylib",),
}
_DEFAULT_LIBRARY_NAMES = ("libsteam_api.so",)

# Probed newest-first; the first symbol that resolves wins. Extend the head of
# each tuple when we move to a newer SDK rather than replacing the list, so a
# build that still bundles an older library keeps working.
_USER_STATS_ACCESSORS = (
    "SteamAPI_SteamUserStats_v013",
    "SteamAPI_SteamUserStats_v012",
    "SteamAPI_SteamUserStats_v011",
)
_FRIENDS_ACCESSORS = (
    "SteamAPI_SteamFriends_v018",
    "SteamAPI_SteamFriends_v017",
)
_SET_STAT_INT_NAMES = (
    "SteamAPI_ISteamUserStats_SetStatInt32",
    "SteamAPI_ISteamUserStats_SetStat",
)


def _library_names() -> tuple[str, ...]:
    return _LIBRARY_NAMES.get(sys.platform, _DEFAULT_LIBRARY_NAMES)


def _search_directories() -> list[Path]:
    """Directories to probe for the Steamworks shared library, in priority order.

    A packaged build finds the library beside the executable (PyInstaller one-dir)
    or in the extraction root (one-file). Development runs find it under
    ``build/steam/sdk/`` if a developer has dropped an SDK there.
    """

    directories: list[Path] = []
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        directories.append(Path(bundle_root))
    if getattr(sys, "frozen", False):
        directories.append(Path(sys.executable).resolve().parent)
        if sys.platform == "darwin":
            # Arch Rogue.app/Contents/MacOS/<exe> -> Contents/Frameworks
            directories.append(
                Path(sys.executable).resolve().parents[1] / "Frameworks"
            )
    module_dir = Path(__file__).resolve().parent
    directories.append(module_dir)
    for parents in (2, 3):
        try:
            repo_root = Path(__file__).resolve().parents[parents]
        except IndexError:
            continue
        directories.append(repo_root / "build" / "steam" / "sdk")
    # Deduplicate while preserving order.
    seen: set[Path] = set()
    ordered: list[Path] = []
    for directory in directories:
        if directory not in seen:
            seen.add(directory)
            ordered.append(directory)
    return ordered


def _load_library(extra_directory: Path | None = None) -> ctypes.CDLL | None:
    """Load ``steam_api`` from a bundled location, or return ``None``.

    Deliberately does not fall back to the system library search path: picking up
    an unrelated Steam library from a user's machine would be a surprising
    source of version skew.
    """

    directories = _search_directories()
    if extra_directory is not None:
        directories.insert(0, Path(extra_directory))
    for directory in directories:
        for name in _library_names():
            candidate = directory / name
            try:
                if not candidate.is_file():
                    continue
            except OSError:
                continue
            try:
                return ctypes.CDLL(str(candidate))
            except OSError as error:
                LOGGER.warning("Steamworks library at %s failed to load: %s", candidate, error)
    return None


def _resolve(library: ctypes.CDLL, names: Sequence[str]):
    for name in names:
        function = getattr(library, name, None)
        if function is not None:
            return function
    return None


def configured_app_id() -> int | None:
    """The App ID from the environment override, else the compiled-in constant."""

    raw = os.environ.get(APP_ID_ENV, "").strip()
    if raw:
        try:
            return int(raw)
        except ValueError:
            LOGGER.warning("Ignoring non-numeric %s=%r", APP_ID_ENV, raw)
    return STEAM_APP_ID


class SteamIntegration:
    """Thin, failure-tolerant facade over the Steamworks flat API.

    Every public method is safe to call regardless of whether Steam is actually
    available; when it is not, unlocks accumulate in a local queue file and are
    replayed by the first session that does reach Steam.
    """

    # Minimum seconds between StoreStats flushes from the frame loop. StoreStats
    # is a Steam-client sync RPC (disk plus a potential server roundtrip), and
    # the achievement funnel republishes stats on every elite/boss kill; calling
    # it per kill produced visible hitches on the Steam build (4.10.1) that the
    # DRM-free build, where all of this no-ops, never showed. Achievement
    # unlocks bypass the throttle so the overlay toast still appears instantly.
    STORE_STATS_MIN_INTERVAL = 3.0

    def __init__(
        self,
        app_id: int | None = None,
        queue_path: Path | str | None = None,
        library_directory: Path | str | None = None,
    ) -> None:
        self.app_id = app_id if app_id is not None else configured_app_id()
        self.queue_path = Path(queue_path) if queue_path is not None else None
        self._library_directory = (
            Path(library_directory) if library_directory is not None else None
        )
        self._library: ctypes.CDLL | None = None
        self._user_stats: ctypes.c_void_p | None = None
        self._friends: ctypes.c_void_p | None = None
        self._available = False
        self._stats_dirty = False
        self._status = "not started"
        # Unlocks that Steam has not durably accepted yet. Loaded from disk so an
        # offline session's achievements survive a restart.
        self._pending: list[str] = []
        self._rich_presence: dict[str, str] = {}
        # Last value pushed per stat this session, so the funnel's habit of
        # republishing every stat on every evaluation stays free of SDK calls
        # unless a value actually moved.
        self._published_stats: dict[str, int | float] = {}
        # StoreStats pacing for the frame-loop path (see class constant).
        self._store_deadline = 0.0
        self._store_urgent = False

    # ---------------------------------------------------------------- lifecycle

    @property
    def available(self) -> bool:
        """True only when Steam is initialised and the stats interface resolved."""

        return self._available

    @property
    def status(self) -> str:
        """Human-readable reason for the current availability, for the log/About screen."""

        return self._status

    def start(self) -> bool:
        """Initialise Steam. Returns ``True`` when the facade became available.

        Never raises: a missing library, a stopped Steam client and a mismatched
        SDK all resolve to ``False`` plus a logged reason.
        """

        self._pending = self._load_queue()
        if os.environ.get(DISABLE_ENV, "").strip():
            self._status = f"disabled by {DISABLE_ENV}"
            return False
        if sys.platform.startswith(("android", "emscripten")):
            self._status = f"unsupported platform {sys.platform}"
            return False
        if self.app_id is None:
            self._status = "no App ID configured"
            return False

        library = _load_library(self._library_directory)
        if library is None:
            self._status = "steam_api library not bundled"
            return False

        try:
            if not self._initialise(library):
                return False
        except Exception as error:  # pragma: no cover - defensive, ctypes is opaque
            LOGGER.warning("Steamworks initialisation raised: %s", error)
            self._status = f"initialisation error: {error}"
            self._available = False
            return False

        self._library = library
        self._available = True
        self._status = f"connected (app {self.app_id})"
        LOGGER.info("Steamworks initialised for app %s", self.app_id)
        # Ask Steam for the user's current achievement state, then replay
        # anything that was unlocked while offline.
        request = getattr(library, "SteamAPI_ISteamUserStats_RequestCurrentStats", None)
        if request is not None and self._user_stats is not None:
            request.argtypes = [ctypes.c_void_p]
            request.restype = ctypes.c_bool
            request(self._user_stats)
        self._replay_pending()
        return True

    def _initialise(self, library: ctypes.CDLL) -> bool:
        """Run SteamAPI_Init and resolve the interfaces we use."""

        init_flat = getattr(library, "SteamAPI_InitFlat", None)
        if init_flat is not None:
            # ESteamAPIInitResult SteamAPI_InitFlat(SteamErrMsg *pOutErrMsg);
            # 0 == k_ESteamAPIInitResult_OK; the buffer is a char[1024].
            error_buffer = ctypes.create_string_buffer(1024)
            init_flat.argtypes = [ctypes.c_char_p]
            init_flat.restype = ctypes.c_int
            result = init_flat(error_buffer)
            if result != 0:
                message = error_buffer.value.decode("utf-8", "replace")
                self._status = f"SteamAPI_InitFlat failed ({result}): {message}"
                LOGGER.info("Steam unavailable: %s", self._status)
                return False
        else:
            legacy_init = getattr(library, "SteamAPI_Init", None)
            if legacy_init is None:
                self._status = "steam_api library exports no init entry point"
                return False
            legacy_init.restype = ctypes.c_bool
            if not legacy_init():
                self._status = "SteamAPI_Init returned false (client not running?)"
                LOGGER.info("Steam unavailable: %s", self._status)
                return False

        accessor = _resolve(library, _USER_STATS_ACCESSORS)
        if accessor is None:
            self._shutdown_library(library)
            self._status = "no known ISteamUserStats accessor in this SDK build"
            return False
        accessor.restype = ctypes.c_void_p
        pointer = accessor()
        if not pointer:
            self._shutdown_library(library)
            self._status = "ISteamUserStats unavailable"
            return False
        self._user_stats = ctypes.c_void_p(pointer)

        friends_accessor = _resolve(library, _FRIENDS_ACCESSORS)
        if friends_accessor is not None:
            friends_accessor.restype = ctypes.c_void_p
            friends_pointer = friends_accessor()
            if friends_pointer:
                self._friends = ctypes.c_void_p(friends_pointer)
        return True

    def restart_app_if_necessary(self) -> bool:
        """True when Steam is relaunching us and this process should exit now.

        Called before any window exists. A DRM-free build launched directly from
        the install folder gets restarted through the Steam client so the overlay,
        Cloud and achievements attach. Returns ``False`` — carry on — whenever
        Steam is not involved at all.
        """

        if os.environ.get(DISABLE_ENV, "").strip() or self.app_id is None:
            return False
        library = _load_library(self._library_directory)
        if library is None:
            return False
        restart = getattr(library, "SteamAPI_RestartAppIfNecessary", None)
        if restart is None:
            return False
        try:
            restart.argtypes = [ctypes.c_uint32]
            restart.restype = ctypes.c_bool
            return bool(restart(ctypes.c_uint32(self.app_id)))
        except Exception as error:  # pragma: no cover - defensive
            LOGGER.warning("SteamAPI_RestartAppIfNecessary raised: %s", error)
            return False

    def run_callbacks(self) -> None:
        """Pump Steam's callback queue; call once per frame.

        Costs one attribute lookup when Steam is unavailable, which is the common
        case for non-Steam builds, so the frame loop can call it unconditionally.
        """

        if not self._available or self._library is None:
            return
        try:
            self._library.SteamAPI_RunCallbacks()
        except Exception as error:  # pragma: no cover - defensive
            LOGGER.warning("SteamAPI_RunCallbacks raised: %s", error)
            self._available = False
            self._status = f"callback pump failed: {error}"
            return
        if self._stats_dirty and (
            self._store_urgent or time.monotonic() >= self._store_deadline
        ):
            self._store_stats()

    def shutdown(self) -> None:
        """Flush stats and release the Steam connection. Safe to call twice."""

        if self._available and self._stats_dirty:
            self._store_stats()
        library, self._library = self._library, None
        self._available = False
        self._user_stats = None
        self._friends = None
        if library is not None:
            self._shutdown_library(library)
            self._status = "shut down"

    @staticmethod
    def _shutdown_library(library: ctypes.CDLL) -> None:
        shutdown = getattr(library, "SteamAPI_Shutdown", None)
        if shutdown is None:
            return
        try:
            shutdown()
        except Exception as error:  # pragma: no cover - defensive
            LOGGER.warning("SteamAPI_Shutdown raised: %s", error)

    # ------------------------------------------------------------- achievements

    def unlock(self, achievement_id: str) -> bool:
        """Unlock an achievement, or queue it for the next Steam-connected session.

        Returns ``True`` when Steam accepted the call this session. Re-unlocking
        an achievement is harmless — Steam ignores it — so callers need not track
        which ones they have already granted.
        """

        achievement_id = str(achievement_id).strip()
        if not achievement_id:
            return False
        if achievement_id not in self._pending:
            self._pending.append(achievement_id)
            self._save_queue()
        if not self._available:
            return False
        return self._apply(achievement_id)

    def _apply(self, achievement_id: str) -> bool:
        if self._library is None or self._user_stats is None:
            return False
        setter = getattr(self._library, "SteamAPI_ISteamUserStats_SetAchievement", None)
        if setter is None:
            return False
        try:
            setter.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
            setter.restype = ctypes.c_bool
            accepted = bool(
                setter(self._user_stats, achievement_id.encode("utf-8"))
            )
        except Exception as error:  # pragma: no cover - defensive
            LOGGER.warning("SetAchievement(%s) raised: %s", achievement_id, error)
            return False
        if accepted:
            # Left on the pending list until StoreStats confirms the write, so a
            # crash between the two does not lose the unlock. Unlocks flush on
            # the next pump regardless of the stats throttle: the overlay toast
            # only appears once StoreStats lands.
            self._stats_dirty = True
            self._store_urgent = True
        else:
            LOGGER.warning(
                "Steam rejected achievement %r (not defined in App Admin?)",
                achievement_id,
            )
        return accepted

    def is_unlocked(self, achievement_id: str) -> bool | None:
        """Steam's view of an achievement, or ``None`` when Steam cannot say."""

        if not self._available or self._library is None or self._user_stats is None:
            return None
        getter = getattr(self._library, "SteamAPI_ISteamUserStats_GetAchievement", None)
        if getter is None:
            return None
        try:
            getter.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_bool)]
            getter.restype = ctypes.c_bool
            achieved = ctypes.c_bool(False)
            if not getter(
                self._user_stats, achievement_id.encode("utf-8"), ctypes.byref(achieved)
            ):
                return None
            return bool(achieved.value)
        except Exception as error:  # pragma: no cover - defensive
            LOGGER.warning("GetAchievement(%s) raised: %s", achievement_id, error)
            return None

    def set_stat(self, name: str, value: int | float) -> bool:
        """Set an integer or float Steam stat (progress bars, lifetime counters)."""

        if not self._available or self._library is None or self._user_stats is None:
            return False
        # The funnel republishes every stat on every evaluation (per elite kill
        # in a fight); an unchanged value is a success with no SDK call and,
        # crucially, no dirty flag — so no StoreStats RPC follows.
        if self._published_stats.get(name) == value:
            return True
        try:
            if isinstance(value, int) and not isinstance(value, bool):
                setter = _resolve(self._library, _SET_STAT_INT_NAMES)
                if setter is None:
                    return False
                setter.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int32]
                setter.restype = ctypes.c_bool
                accepted = bool(setter(self._user_stats, name.encode("utf-8"), int(value)))
            else:
                setter = getattr(
                    self._library, "SteamAPI_ISteamUserStats_SetStatFloat", None
                )
                if setter is None:
                    return False
                setter.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_float]
                setter.restype = ctypes.c_bool
                accepted = bool(setter(self._user_stats, name.encode("utf-8"), float(value)))
        except Exception as error:  # pragma: no cover - defensive
            LOGGER.warning("SetStat(%s) raised: %s", name, error)
            return False
        if accepted:
            self._published_stats[name] = value
            self._stats_dirty = True
        return accepted

    def _store_stats(self) -> bool:
        """Commit pending stat/achievement writes to Steam's servers."""

        if self._library is None or self._user_stats is None:
            return False
        store = getattr(self._library, "SteamAPI_ISteamUserStats_StoreStats", None)
        if store is None:
            return False
        try:
            store.argtypes = [ctypes.c_void_p]
            store.restype = ctypes.c_bool
            stored = bool(store(self._user_stats))
        except Exception as error:  # pragma: no cover - defensive
            LOGGER.warning("StoreStats raised: %s", error)
            return False
        # Pace the next frame-loop flush whether or not this one landed; a
        # failing StoreStats (Valve rate limit, client hiccup) retried every
        # frame would be the very stall this throttle exists to prevent. The
        # urgency is spent by the attempt — on failure the dirty flag and the
        # pending queue keep the unlock safe and the deadline paces the retry.
        self._store_deadline = time.monotonic() + self.STORE_STATS_MIN_INTERVAL
        self._store_urgent = False
        if stored:
            self._stats_dirty = False
            # Steam has durably accepted everything we set this session.
            if self._pending:
                self._pending = []
                self._save_queue()
        return stored

    def _replay_pending(self) -> None:
        if not self._pending:
            return
        LOGGER.info("Replaying %d queued Steam achievement(s)", len(self._pending))
        for achievement_id in list(self._pending):
            self._apply(achievement_id)
        if self._stats_dirty:
            self._store_stats()

    # ----------------------------------------------------------- rich presence

    def set_rich_presence(self, key: str, value: str) -> bool:
        """Set a Steam rich-presence key (friends list "In dungeon — depth 6")."""

        if not self._available or self._library is None or self._friends is None:
            return False
        if self._rich_presence.get(key) == value:
            return True
        setter = getattr(self._library, "SteamAPI_ISteamFriends_SetRichPresence", None)
        if setter is None:
            return False
        try:
            setter.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]
            setter.restype = ctypes.c_bool
            accepted = bool(
                setter(self._friends, key.encode("utf-8"), value.encode("utf-8"))
            )
        except Exception as error:  # pragma: no cover - defensive
            LOGGER.warning("SetRichPresence(%s) raised: %s", key, error)
            return False
        if accepted:
            self._rich_presence[key] = value
        return accepted

    # ------------------------------------------------------------ offline queue

    def _load_queue(self) -> list[str]:
        if self.queue_path is None:
            return list(self._pending)
        try:
            raw = json.loads(self.queue_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        if not isinstance(raw, dict) or raw.get("version") != _QUEUE_VERSION:
            return []
        pending = raw.get("pending")
        if not isinstance(pending, list):
            return []
        return [str(item) for item in pending if isinstance(item, str)]

    def _save_queue(self) -> None:
        if self.queue_path is None:
            return
        payload = {"version": _QUEUE_VERSION, "pending": self._pending}
        try:
            self.queue_path.parent.mkdir(parents=True, exist_ok=True)
            self.queue_path.write_text(json.dumps(payload), encoding="utf-8")
        except OSError as error:
            LOGGER.warning("Could not persist Steam achievement queue: %s", error)

    @property
    def pending(self) -> tuple[str, ...]:
        """Achievements unlocked locally that Steam has not confirmed yet."""

        return tuple(self._pending)


# --------------------------------------------------------------------- module API
#
# Gameplay code should use these module-level helpers rather than constructing an
# integration, so that a single instance owns the Steam connection.

_INTEGRATION: SteamIntegration | None = None


def integration() -> SteamIntegration:
    """The process-wide integration, constructed disabled if never started."""

    global _INTEGRATION
    if _INTEGRATION is None:
        _INTEGRATION = SteamIntegration()
    return _INTEGRATION


def start(storage_directory: Path | str | None = None) -> SteamIntegration:
    """Construct and start the process-wide integration. Never raises."""

    global _INTEGRATION
    queue_path = (
        Path(storage_directory) / _QUEUE_FILENAME
        if storage_directory is not None
        else None
    )
    _INTEGRATION = SteamIntegration(queue_path=queue_path)
    _INTEGRATION.start()
    if not _INTEGRATION.available:
        LOGGER.debug("Steam integration inactive: %s", _INTEGRATION.status)
    return _INTEGRATION


def shutdown() -> None:
    global _INTEGRATION
    if _INTEGRATION is not None:
        _INTEGRATION.shutdown()


def unlock_achievement(achievement_id: str) -> bool:
    """Unlock an achievement through the process-wide integration."""

    return integration().unlock(achievement_id)


def set_stat(name: str, value: int | float) -> bool:
    return integration().set_stat(name, value)


def run_callbacks() -> None:
    integration().run_callbacks()


def set_rich_presence(key: str, value: str) -> bool:
    return integration().set_rich_presence(key, value)


def restart_app_if_necessary() -> bool:
    """Whether Steam is relaunching the process; see :meth:`SteamIntegration.restart_app_if_necessary`."""

    return integration().restart_app_if_necessary()
