#!/usr/bin/env python3
"""Repeatable MX-android smoke test for the Arch Rogue x86_64 AVD."""

from __future__ import annotations

import argparse
import json
import os
import struct
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_PACKAGE = "org.archrogue.archrogue.odin.alpha.debug"
READY_MARKER = "ARCH_ROGUE_READY"
GRAPHICS_MARKER = "ARCH_ROGUE_GRAPHICS_RESTORED"
CHECKPOINT_MARKER = "ARCH_ROGUE_SUSPEND_CHECKPOINT"
BACK_MARKER = "ARCH_ROGUE_BACK source=dispatcher"
CRASH_MARKERS = ("FATAL EXCEPTION", "Fatal signal", "SYS_SECCOMP", "backtrace:")


class SmokeError(RuntimeError):
    pass


def run(command: list[str], *, timeout: float = 60, binary: bool = False) -> str | bytes:
    result = subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        text=not binary,
    )
    if result.returncode != 0:
        output = result.stdout.decode("utf-8", "replace") if binary else result.stdout
        raise SmokeError(f"command failed ({result.returncode}): {' '.join(command)}\n{output}")
    return result.stdout


class AndroidSmoke:
    def __init__(
        self,
        adb: Path,
        serial: str,
        apk: Path,
        package: str,
        output: Path,
        skip_multitouch: bool,
    ) -> None:
        self.adb = str(adb)
        self.serial = serial
        self.apk = apk
        self.package = package
        self.output = output
        self.skip_multitouch = skip_multitouch
        self.adb_prefix = [self.adb, "-s", serial]
        self.width = 0
        self.height = 0

    def adb_run(self, *args: str, timeout: float = 60, binary: bool = False) -> str | bytes:
        return run([*self.adb_prefix, *args], timeout=timeout, binary=binary)

    def shell(self, *args: str, timeout: float = 60) -> str:
        result = self.adb_run("shell", *args, timeout=timeout)
        assert isinstance(result, str)
        return result

    def logcat(self) -> str:
        result = self.adb_run(
            "logcat",
            "-d",
            "-v",
            "brief",
            "-s",
            "ArchRogue:I",
            "AndroidRuntime:E",
            "libc:F",
            "DEBUG:F",
            "*:S",
        )
        assert isinstance(result, str)
        return result

    def wait_for_marker(self, marker: str, *, minimum_count: int = 1, timeout: float = 40) -> str:
        deadline = time.monotonic() + timeout
        latest = ""
        while time.monotonic() < deadline:
            latest = self.logcat()
            if latest.count(marker) >= minimum_count:
                return latest
            time.sleep(0.25)
        raise SmokeError(f"timed out waiting for {marker!r} count {minimum_count}\n{latest}")

    def assert_alive(self) -> None:
        pid = self.shell("pidof", self.package).strip()
        if not pid:
            raise SmokeError(f"{self.package} is not running")

    def capture(self, name: str) -> Path:
        data = self.adb_run("exec-out", "screencap", "-p", timeout=30, binary=True)
        assert isinstance(data, bytes)
        if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
            raise SmokeError(f"invalid screencap for {name}")
        width, height = struct.unpack(">II", data[16:24])
        if width <= height:
            raise SmokeError(f"expected landscape screencap, got {width}x{height}")
        if self.width == 0:
            self.width, self.height = width, height
        elif (width, height) != (self.width, self.height):
            raise SmokeError(f"surface changed from {self.width}x{self.height} to {width}x{height}")
        destination = self.output / f"{name}.png"
        destination.write_bytes(data)
        print(f"android-smoke: captured {destination} ({width}x{height})")
        return destination

    def point(self, x_ratio: float, y_ratio: float) -> tuple[int, int]:
        if self.width <= 0 or self.height <= 0:
            raise SmokeError("capture the surface before converting coordinates")
        return round(self.width * x_ratio), round(self.height * y_ratio)

    def press(self, x_ratio: float, y_ratio: float, *, hold_ms: int = 140, settle: float = 0.35) -> None:
        x, y = self.point(x_ratio, y_ratio)
        self.shell("input", "swipe", str(x), str(y), str(x), str(y), str(hold_ms))
        time.sleep(settle)

    def key(self, keycode: int, *, settle: float = 0.35) -> None:
        self.shell("input", "keyevent", str(keycode))
        time.sleep(settle)

    def back_gesture(self, *, settle: float = 0.5) -> None:
        if self.width <= 0 or self.height <= 0:
            raise SmokeError("capture the surface before sending a Back gesture")
        self.shell(
            "input", "swipe",
            "1", str(self.height // 2), str(round(self.width * 0.35)), str(self.height // 2), "300",
        )
        time.sleep(settle)

    def start(self) -> None:
        self.shell(
            "am", "start", "-W", "-n",
            f"{self.package}/org.archrogue.archrogue.odin.ArchRogueActivity",
        )

    def private_document(self, name: str) -> dict[str, object]:
        path = f"/data/user/0/{self.package}/files/arch-rogue-v6/{name}.json"
        data = self.adb_run("exec-out", "run-as", self.package, "cat", path, binary=True)
        assert isinstance(data, bytes)
        try:
            document = json.loads(data)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SmokeError(f"invalid app-private {name} document: {exc}") from exc
        if not isinstance(document, dict) or not isinstance(document.get("revision"), int):
            raise SmokeError(f"app-private {name} document lacks an integer revision")
        return document

    @staticmethod
    def document_revision(document: dict[str, object]) -> int:
        revision = document.get("revision")
        if not isinstance(revision, int):
            raise SmokeError("app-private document lacks an integer revision")
        return revision

    def run_document(self) -> dict[str, object]:
        return self.private_document("run")

    def emulator_event(self, *events: str) -> None:
        output = self.adb_run("emu", "event", "send", *events)
        assert isinstance(output, str)
        if "OK" not in output:
            raise SmokeError(f"emulator rejected event batch: {output}")

    def raw_touch(self, slot: int, tracking_id: int, x_ratio: float, y_ratio: float) -> list[str]:
        # The AVD's evdev axes remain in natural portrait orientation while the
        # Android display is rotated to landscape.
        raw_x = round((1.0 - y_ratio) * 32767)
        raw_y = round(x_ratio * 32767)
        return [
            f"EV_ABS:ABS_MT_SLOT:{slot}",
            f"EV_ABS:ABS_MT_TRACKING_ID:{tracking_id}",
            f"EV_ABS:ABS_MT_POSITION_X:{raw_x}",
            f"EV_ABS:ABS_MT_POSITION_Y:{raw_y}",
            "EV_ABS:ABS_MT_PRESSURE:512",
        ]

    def multi_touch(self) -> None:
        if self.skip_multitouch:
            print("android-smoke: skipping emulator raw multi-touch by request")
            return
        if not self.serial.startswith("emulator-"):
            raise SmokeError("raw four-slot acceptance requires an emulator serial or --skip-multitouch")

        down: list[str] = []
        down += self.raw_touch(0, 300, 0.205, 0.802)  # joystick, displaced right
        down += self.raw_touch(1, 301, 0.556, 0.463)  # world aim
        down += self.raw_touch(2, 302, 0.953, 0.093)  # Ability 1
        down += self.raw_touch(3, 303, 0.953, 0.181)  # Ability 2
        down += ["EV_KEY:BTN_TOUCH:1", "0:0:0"]
        self.emulator_event(*down)
        time.sleep(0.75)
        self.capture("06-multitouch-held")

        for expected_count, slot in ((3, 2), (2, 3), (1, 1)):
            self.emulator_event(
                f"EV_ABS:ABS_MT_SLOT:{slot}",
                "EV_ABS:ABS_MT_TRACKING_ID:-1",
                "0:0:0",
            )
            time.sleep(0.25)
            if f"ARCH_ROGUE_TOUCH contacts={expected_count}" not in self.logcat():
                raise SmokeError(f"stable touch release did not reach {expected_count} contacts")
        self.emulator_event(
            "EV_ABS:ABS_MT_SLOT:0",
            "EV_ABS:ABS_MT_TRACKING_ID:-1",
            "EV_KEY:BTN_TOUCH:0",
            "0:0:0",
        )
        time.sleep(0.25)
        logs = self.logcat()
        for count in (4, 3, 2, 1, 0):
            if f"ARCH_ROGUE_TOUCH contacts={count}" not in logs:
                raise SmokeError(f"stable touch sequence omitted contact count {count}")

    def assert_no_crash(self, logs: str) -> None:
        found = [marker for marker in CRASH_MARKERS if marker in logs]
        if found:
            raise SmokeError(f"crash marker(s) found: {found}\n{logs}")

    def run(self) -> None:
        self.output.mkdir(parents=True, exist_ok=True)
        if not self.apk.is_file():
            raise SmokeError(f"APK does not exist: {self.apk}")

        devices = self.adb_run("devices", "-l")
        assert isinstance(devices, str)
        if self.serial not in devices:
            raise SmokeError(f"device is not ready: {self.serial}\n{devices}")
        api = int(self.shell("getprop", "ro.build.version.sdk").strip())
        abis = self.shell("getprop", "ro.product.cpu.abilist").strip().split(",")
        if api < 28 or "x86_64" not in abis:
            raise SmokeError(f"AVD contract mismatch: API {api}, ABIs {abis}")

        subprocess.run(
            [*self.adb_prefix, "uninstall", self.package],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.adb_run("install", "--no-streaming", str(self.apk), timeout=120)
        # Repeated forced-ABI installs can leave a stale singleTask activity record
        # attached to an old app UID. Force-stop the fresh package before the
        # explicit launch so ActivityManager cannot kill it while removing that task.
        self.shell("am", "force-stop", self.package)
        self.adb_run("logcat", "-c")
        self.start()
        logs = self.wait_for_marker(READY_MARKER)
        self.assert_no_crash(logs)
        self.assert_alive()
        self.capture("01-title")

        # The physical-device report that prompted alpha.21 crashed on Options.
        # Exercise that exact title transition and close it through Java Back before
        # continuing, so both regressions are covered by every Android smoke run.
        self.press(0.500, 0.752)  # Options
        self.capture("01b-options")
        logs = self.logcat()
        self.assert_no_crash(logs)
        self.assert_alive()
        options_before = self.private_document("options")
        self.press(0.500, 0.194)  # disabled Native fullscreen row, near its lower edge
        time.sleep(0.5)
        options_after = self.private_document("options")
        if (
            self.document_revision(options_after) != self.document_revision(options_before)
            or options_after.get("payload") != options_before.get("payload")
        ):
            raise SmokeError("disabled Android fullscreen row activated an overlapping Options target")
        back_count = logs.count(BACK_MARKER)
        self.back_gesture()
        logs = self.wait_for_marker(BACK_MARKER, minimum_count=back_count + 1)
        self.capture("01c-title-after-options-back")
        self.assert_no_crash(logs)
        self.assert_alive()

        # Direct menu activation, archetype preview, and explicit confirmation.
        self.press(0.500, 0.616)  # New Run
        self.capture("02-archetype")
        self.press(0.647, 0.352)  # Rogue preview
        self.capture("03-archetype-rogue")
        self.press(0.581, 0.856)  # Enter the Depths
        time.sleep(1.0)
        self.capture("04-story")
        self.press(0.500, 0.463)  # reveal narration
        self.press(0.500, 0.648)  # first explicit story choice
        time.sleep(0.75)
        self.capture("05-gameplay")
        run_before = self.run_document()

        # Stable-ID simultaneous movement, aim, held action, and another action.
        self.multi_touch()
        self.press(0.677, 0.083)  # Pause before enemies can advance during inspection.
        self.capture("07-paused")

        # Android Back resumes through the same semantic command; inventory is a
        # direct tap and touch modality must not leave a desktop-selected row.
        self.key(4)
        self.press(0.489, 0.083)  # Bag
        self.capture("08-inventory")
        self.key(4)  # close inventory

        # Home/foreground must checkpoint, rebuild graphics/audio, and show one
        # process-local continue veil over a visible frozen world.
        self.key(3, settle=2.5)
        logs = self.wait_for_marker(CHECKPOINT_MARKER)
        run_after_suspend = self.run_document()
        if self.document_revision(run_after_suspend) < self.document_revision(run_before):
            raise SmokeError("suspend checkpoint regressed the run revision")
        graphics_count = logs.count(GRAPHICS_MARKER)
        self.start()
        logs = self.wait_for_marker(GRAPHICS_MARKER, minimum_count=graphics_count + 1)
        self.assert_no_crash(logs)
        self.capture("09-lifecycle-resume-veil")
        self.press(0.500, 0.500)  # one tap restores prior Playing mode
        self.press(0.677, 0.083)  # pause immediately
        self.capture("10-lifecycle-continued-paused")

        # A hard process death must still expose Resume from app-private storage.
        ready_count = logs.count(READY_MARKER)
        self.shell("am", "force-stop", self.package)
        self.start()
        logs = self.wait_for_marker(READY_MARKER, minimum_count=ready_count + 1)
        self.assert_no_crash(logs)
        self.press(0.500, 0.546)  # Resume on title
        time.sleep(0.75)
        self.capture("11-force-stop-resume")
        final_document = self.run_document()
        if self.document_revision(final_document) < self.document_revision(run_after_suspend):
            raise SmokeError("force-stop Resume loaded an older run revision")

        final_logs = self.logcat()
        self.assert_no_crash(final_logs)
        if BACK_MARKER not in final_logs:
            raise SmokeError("Android Back never reached the modern dispatcher bridge")
        (self.output / "smoke.log").write_text(final_logs, encoding="utf-8")
        print(
            "android-smoke: PASS "
            f"serial={self.serial} api={api} surface={self.width}x{self.height} "
            f"revision={final_document['revision']} output={self.output}"
        )


def default_apk(root: Path) -> Path:
    candidates = sorted((root / "build" / "android" / "outputs").glob("Arch-Rogue-debug.apk"))
    if len(candidates) != 1:
        raise SmokeError(
            "expected one deterministic debug APK under build/android/outputs; "
            "run ./build.sh android-debug or pass --apk"
        )
    return candidates[0]


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parent.parent
    sdk_root = Path(os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME") or "/opt/android-sdk")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", default=os.environ.get("ANDROID_SERIAL", "emulator-5554"))
    parser.add_argument("--apk", type=Path)
    parser.add_argument("--package", default=DEFAULT_PACKAGE)
    parser.add_argument("--output", type=Path, default=root / "build" / "android" / "smoke")
    parser.add_argument("--adb", type=Path, default=sdk_root / "platform-tools" / "adb")
    parser.add_argument("--skip-multitouch", action="store_true")
    args = parser.parse_args()
    if args.apk is None:
        args.apk = default_apk(root)
    return args


def main() -> int:
    try:
        args = parse_args()
        AndroidSmoke(
            adb=args.adb.resolve(),
            serial=args.serial,
            apk=args.apk.resolve(),
            package=args.package,
            output=args.output.resolve(),
            skip_multitouch=args.skip_multitouch,
        ).run()
    except (SmokeError, OSError, subprocess.TimeoutExpired, ValueError) as exc:
        print(f"android-smoke: FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
