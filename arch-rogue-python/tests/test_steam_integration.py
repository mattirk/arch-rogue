# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
"""Steamworks facade behaviour without the (NDA-bound, unbundled) Steam SDK.

The Steamworks shared library is never present in CI, so these tests stand in a
fake that mimics the flat C API surface the facade binds: version-suffixed
interface accessors, SteamAPI_InitFlat, ISteamUserStats and rich presence. That
keeps the two properties that actually matter under test — the facade degrades
to a silent no-op off Steam, and unlocks earned offline are never lost.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from arch_rogue import steam

_AMBIENT_DISABLE: mock._patch_dict | None = None


def setUpModule() -> None:
    """Run this module as if ARCH_ROGUE_NO_STEAM were not set.

    That variable force-disables the facade, so an ambient one -- exported in a
    developer's shell, or set on a CI job that assumed it was a safety measure --
    turns almost every test here red with "disabled by ARCH_ROGUE_NO_STEAM"
    instead of the behaviour under test. Nothing here can reach a real Steam
    client regardless: every connected test injects a fake library.
    The one test that asserts the variable *does* disable the facade sets it
    itself, so clearing it module-wide leaves that case intact.
    """

    global _AMBIENT_DISABLE
    environment = dict(os.environ)
    environment.pop(steam.DISABLE_ENV, None)
    _AMBIENT_DISABLE = mock.patch.dict(os.environ, environment, clear=True)
    _AMBIENT_DISABLE.start()


def tearDownModule() -> None:
    if _AMBIENT_DISABLE is not None:
        _AMBIENT_DISABLE.stop()


class _FakeFunction:
    """A ctypes-function stand-in: callable, and accepts argtypes/restype."""

    def __init__(self, implementation) -> None:
        self._implementation = implementation
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self._implementation(*args)


class FakeSteamLibrary:
    """Minimal fake of the Steamworks flat API, recording what the facade did."""

    def __init__(
        self,
        *,
        init_result: int = 0,
        accessor_name: str = "SteamAPI_SteamUserStats_v013",
        set_achievement_result: bool = True,
        store_result: bool = True,
        restart_required: bool = False,
    ) -> None:
        self.init_result = init_result
        self.set_achievement_result = set_achievement_result
        self.store_result = store_result
        self.restart_required = restart_required
        self.unlocked: list[str] = []
        self.stats: dict[str, object] = {}
        self.set_stat_calls = 0
        self.rich_presence: dict[str, str] = {}
        self.store_calls = 0
        self.callback_pumps = 0
        self.shutdown_calls = 0

        self._functions = {
            "SteamAPI_InitFlat": self._init_flat,
            "SteamAPI_Shutdown": self._shutdown,
            "SteamAPI_RunCallbacks": self._run_callbacks,
            "SteamAPI_RestartAppIfNecessary": lambda app_id: self.restart_required,
            accessor_name: lambda: 0xF00D,
            "SteamAPI_SteamFriends_v018": lambda: 0xBEEF,
            "SteamAPI_ISteamUserStats_RequestCurrentStats": lambda handle: True,
            "SteamAPI_ISteamUserStats_SetAchievement": self._set_achievement,
            "SteamAPI_ISteamUserStats_StoreStats": self._store_stats,
            "SteamAPI_ISteamUserStats_SetStatInt32": self._set_stat,
            "SteamAPI_ISteamUserStats_SetStatFloat": self._set_stat,
            "SteamAPI_ISteamFriends_SetRichPresence": self._set_rich_presence,
        }

    def __getattr__(self, name: str):
        # Mirrors a real CDLL: unknown symbols raise, which is exactly what the
        # facade's getattr(..., None) probes rely on.
        try:
            return _FakeFunction(self.__dict__["_functions"][name])
        except KeyError:
            raise AttributeError(name) from None

    def _init_flat(self, error_buffer):
        return self.init_result

    def _shutdown(self):
        self.shutdown_calls += 1

    def _run_callbacks(self):
        self.callback_pumps += 1

    def _set_achievement(self, handle, name: bytes):
        if not self.set_achievement_result:
            return False
        self.unlocked.append(name.decode("utf-8"))
        return True

    def _store_stats(self, handle):
        self.store_calls += 1
        return self.store_result

    def _set_stat(self, handle, name: bytes, value):
        self.set_stat_calls += 1
        self.stats[name.decode("utf-8")] = value
        return True

    def _set_rich_presence(self, handle, key: bytes, value: bytes):
        self.rich_presence[key.decode("utf-8")] = value.decode("utf-8")
        return True


def _connected(queue_path: Path | None = None, **library_kwargs):
    """A started integration bound to a fake library, plus that library."""

    library = FakeSteamLibrary(**library_kwargs)
    integration = steam.SteamIntegration(app_id=480, queue_path=queue_path)
    with mock.patch.object(steam, "_load_library", return_value=library):
        integration.start()
    return integration, library


class SteamUnavailableTests(unittest.TestCase):
    """Every non-Steam channel must behave as if this module did not exist."""

    def test_no_app_id_leaves_integration_disabled(self):
        # Still a supported state: a fork or a build that clears the constant.
        with mock.patch.object(steam, "STEAM_APP_ID", None):
            integration = steam.SteamIntegration(app_id=None)
            self.assertFalse(integration.start())
            self.assertFalse(integration.available)
            self.assertEqual(integration.status, "no App ID configured")

    def test_missing_library_is_not_an_error(self):
        integration = steam.SteamIntegration(app_id=480)
        with mock.patch.object(steam, "_load_library", return_value=None):
            self.assertFalse(integration.start())
        self.assertEqual(integration.status, "steam_api library not bundled")

    def test_disable_environment_variable_wins_over_everything(self):
        integration = steam.SteamIntegration(app_id=480)
        with mock.patch.dict("os.environ", {steam.DISABLE_ENV: "1"}):
            with mock.patch.object(steam, "_load_library") as loader:
                self.assertFalse(integration.start())
            loader.assert_not_called()

    def test_failed_init_reports_steam_message_and_stays_disabled(self):
        integration, library = _connected(init_result=2)
        self.assertFalse(integration.available)
        self.assertIn("SteamAPI_InitFlat failed", integration.status)
        # A failed init must not leave a half-open connection behind.
        self.assertEqual(library.callback_pumps, 0)

    def test_operations_are_silent_no_ops_while_unavailable(self):
        integration = steam.SteamIntegration(app_id=None)
        integration.start()
        integration.run_callbacks()
        self.assertIsNone(integration.is_unlocked("ACH_X"))
        self.assertFalse(integration.set_stat("runs", 3))
        self.assertFalse(integration.set_rich_presence("steam_display", "x"))
        integration.shutdown()

    def test_restart_check_is_false_without_a_library(self):
        integration = steam.SteamIntegration(app_id=480)
        with mock.patch.object(steam, "_load_library", return_value=None):
            self.assertFalse(integration.restart_app_if_necessary())


class SteamConnectedTests(unittest.TestCase):
    def test_start_resolves_interfaces_and_reports_connected(self):
        integration, _ = _connected()
        self.assertTrue(integration.available)
        self.assertIn("connected", integration.status)

    def test_older_sdk_accessor_suffix_still_resolves(self):
        # Valve bumps the version suffix between SDK releases; a build bundling
        # an older library must keep working.
        integration, _ = _connected(accessor_name="SteamAPI_SteamUserStats_v011")
        self.assertTrue(integration.available)

    def test_unknown_accessor_suffix_disables_cleanly(self):
        integration, library = _connected(accessor_name="SteamAPI_SteamUserStats_v99")
        self.assertFalse(integration.available)
        self.assertIn("ISteamUserStats", integration.status)
        # The SDK was initialised, so it must also be shut down again.
        self.assertEqual(library.shutdown_calls, 1)

    def test_unlock_sets_achievement_and_stores_on_next_pump(self):
        integration, library = _connected()
        self.assertTrue(integration.unlock("ACH_FIRST_CLEAR"))
        self.assertEqual(library.unlocked, ["ACH_FIRST_CLEAR"])
        # Writes are batched: StoreStats is a network call, so it waits for the
        # frame pump rather than firing inside the gameplay call.
        self.assertEqual(library.store_calls, 0)
        integration.run_callbacks()
        self.assertEqual(library.store_calls, 1)
        # ...and does not fire again while nothing is dirty.
        integration.run_callbacks()
        self.assertEqual(library.store_calls, 1)

    def test_rejected_achievement_id_does_not_raise(self):
        integration, library = _connected(set_achievement_result=False)
        self.assertFalse(integration.unlock("ACH_TYPO"))
        self.assertEqual(library.unlocked, [])

    def test_stats_are_typed_by_python_value(self):
        integration, library = _connected()
        integration.set_stat("total_clears", 7)
        integration.set_stat("best_time", 12.5)
        self.assertEqual(library.stats["total_clears"], 7)
        self.assertAlmostEqual(library.stats["best_time"], 12.5)

    def test_republishing_an_unchanged_stat_costs_no_sdk_calls(self):
        # The achievement funnel republishes every stat on every evaluation —
        # once per elite kill mid-fight. Unchanged values must neither call the
        # SDK nor dirty the batch, or every kill buys a StoreStats RPC (the
        # 4.10.1 Steam-build lag spikes).
        integration, library = _connected()
        self.assertTrue(integration.set_stat("lifetime_kills", 40))
        self.assertTrue(integration.set_stat("lifetime_kills", 40))
        self.assertEqual(library.set_stat_calls, 1)
        integration.run_callbacks()
        self.assertEqual(library.store_calls, 1)
        self.assertTrue(integration.set_stat("lifetime_kills", 40))
        integration.run_callbacks()
        self.assertEqual(library.store_calls, 1)

    def test_frame_loop_stat_flushes_are_throttled(self):
        integration, library = _connected()
        clock = iter((0.0, 0.0, 1.0, 5.0, 5.0, 5.0))
        with mock.patch.object(steam.time, "monotonic", lambda: next(clock)):
            integration.set_stat("lifetime_kills", 1)
            integration.run_callbacks()  # reads 0.0, stores, deadline 0.0+3
            self.assertEqual(library.store_calls, 1)
            integration.set_stat("lifetime_kills", 2)
            integration.run_callbacks()  # reads 1.0 < 3.0: within the window
            self.assertEqual(library.store_calls, 1)
            integration.run_callbacks()  # reads 5.0 >= 3.0: window elapsed
            self.assertEqual(library.store_calls, 2)
        self.assertEqual(library.stats["lifetime_kills"], 2)

    def test_an_unlock_bypasses_the_stat_throttle(self):
        # The overlay toast appears when StoreStats lands; a fresh unlock must
        # not wait out a window opened by ordinary stat traffic.
        integration, library = _connected()
        clock = iter((0.0, 0.0, 1.0, 1.0))
        with mock.patch.object(steam.time, "monotonic", lambda: next(clock)):
            integration.set_stat("lifetime_kills", 1)
            integration.run_callbacks()
            self.assertEqual(library.store_calls, 1)
            integration.unlock("ACH_FIRST_CLEAR")
            integration.run_callbacks()  # reads 1.0, inside the window: urgent
            self.assertEqual(library.store_calls, 2)

    def test_rich_presence_skips_redundant_writes(self):
        integration, library = _connected()
        self.assertTrue(integration.set_rich_presence("steam_display", "Depth 6"))
        self.assertTrue(integration.set_rich_presence("steam_display", "Depth 6"))
        self.assertEqual(library.rich_presence, {"steam_display": "Depth 6"})

    def test_shutdown_flushes_pending_stats(self):
        integration, library = _connected()
        integration.unlock("ACH_FIRST_CLEAR")
        integration.shutdown()
        self.assertEqual(library.store_calls, 1)
        self.assertEqual(library.shutdown_calls, 1)
        self.assertFalse(integration.available)
        # Idempotent: the frame loop's finally block can race an earlier call.
        integration.shutdown()
        self.assertEqual(library.shutdown_calls, 1)

    def test_callback_pump_survives_a_library_failure(self):
        integration, library = _connected()
        library._functions["SteamAPI_RunCallbacks"] = mock.Mock(
            side_effect=OSError("steam client vanished")
        )
        integration.run_callbacks()
        self.assertFalse(integration.available)
        self.assertIn("callback pump failed", integration.status)


class OfflineQueueTests(unittest.TestCase):
    """An achievement earned with Steam down must survive to the next session."""

    def setUp(self):
        self._temporary = TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.queue_path = Path(self._temporary.name) / "queue.json"

    def test_unlock_while_offline_persists_across_sessions(self):
        offline = steam.SteamIntegration(app_id=None, queue_path=self.queue_path)
        offline.start()
        self.assertFalse(offline.unlock("ACH_FIRST_CLEAR"))
        self.assertEqual(offline.pending, ("ACH_FIRST_CLEAR",))
        self.assertTrue(self.queue_path.is_file())

        resumed = steam.SteamIntegration(app_id=None, queue_path=self.queue_path)
        resumed.start()
        self.assertEqual(resumed.pending, ("ACH_FIRST_CLEAR",))

    def test_queued_unlocks_replay_on_the_next_connected_session(self):
        offline = steam.SteamIntegration(app_id=None, queue_path=self.queue_path)
        offline.start()
        offline.unlock("ACH_FIRST_CLEAR")
        offline.unlock("ACH_DEPTH_10")

        integration, library = _connected(queue_path=self.queue_path)
        self.assertEqual(library.unlocked, ["ACH_FIRST_CLEAR", "ACH_DEPTH_10"])
        self.assertEqual(library.store_calls, 1)
        # Confirmed by Steam, so the queue is emptied on disk too.
        self.assertEqual(integration.pending, ())
        self.assertEqual(
            steam.SteamIntegration(queue_path=self.queue_path)._load_queue(), []
        )

    def test_unlocks_stay_queued_until_steam_confirms_the_write(self):
        integration, library = _connected(
            queue_path=self.queue_path, store_result=False
        )
        integration.unlock("ACH_FIRST_CLEAR")
        integration.run_callbacks()
        self.assertEqual(library.unlocked, ["ACH_FIRST_CLEAR"])
        # StoreStats failed, so the unlock must not be dropped from the queue.
        self.assertEqual(integration.pending, ("ACH_FIRST_CLEAR",))

    def test_duplicate_and_blank_unlocks_are_ignored(self):
        offline = steam.SteamIntegration(app_id=None, queue_path=self.queue_path)
        offline.start()
        offline.unlock("ACH_FIRST_CLEAR")
        offline.unlock("ACH_FIRST_CLEAR")
        offline.unlock("   ")
        self.assertEqual(offline.pending, ("ACH_FIRST_CLEAR",))

    def test_corrupt_queue_file_is_discarded_not_fatal(self):
        self.queue_path.write_text("{not json", encoding="utf-8")
        integration = steam.SteamIntegration(app_id=None, queue_path=self.queue_path)
        integration.start()
        self.assertEqual(integration.pending, ())

    def test_queue_from_a_future_schema_is_discarded(self):
        self.queue_path.write_text(
            '{"version": 99, "pending": ["ACH_X"]}', encoding="utf-8"
        )
        integration = steam.SteamIntegration(app_id=None, queue_path=self.queue_path)
        integration.start()
        self.assertEqual(integration.pending, ())


class ModuleFunnelTests(unittest.TestCase):
    """Gameplay code goes through the module-level helpers, not an instance."""

    def tearDown(self):
        steam._INTEGRATION = None

    def test_module_helpers_share_one_integration(self):
        steam._INTEGRATION = None
        self.assertIs(steam.integration(), steam.integration())

    def test_unlock_achievement_routes_to_the_process_integration(self):
        stub = mock.Mock(spec=steam.SteamIntegration)
        steam._INTEGRATION = stub
        steam.unlock_achievement("ACH_FIRST_CLEAR")
        stub.unlock.assert_called_once_with("ACH_FIRST_CLEAR")

    def test_configured_app_id_prefers_the_environment_override(self):
        with mock.patch.dict("os.environ", {steam.APP_ID_ENV: "480"}):
            self.assertEqual(steam.configured_app_id(), 480)

    def test_non_numeric_app_id_override_is_ignored(self):
        with mock.patch.dict("os.environ", {steam.APP_ID_ENV: "arch-rogue"}):
            self.assertEqual(steam.configured_app_id(), steam.STEAM_APP_ID)

    def test_the_compiled_in_app_id_is_the_one_valve_assigned(self):
        # Guards against a debug edit reaching a depot: the wrong id here means
        # RestartAppIfNecessary bounces players into someone else's app.
        self.assertEqual(steam.STEAM_APP_ID, 5031380)


# The gameplay-side funnel (which run facts unlock what, and the multiplayer
# joiner's path into it) is covered by tests/test_achievements.py; this file
# stays about the facade itself.


if __name__ == "__main__":
    unittest.main()
