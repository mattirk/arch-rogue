from __future__ import annotations

import io
import struct
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.validate_android_apk import (
    ValidationError,
    validate_apk,
    validate_build_spec,
    validate_source_tree,
)


ROOT = Path(__file__).resolve().parents[1]


def elf_header(machine: int) -> bytes:
    payload = bytearray(20)
    payload[:4] = b"\x7fELF"
    payload[4] = 2 if machine in {62, 183} else 1
    payload[5] = 1
    payload[6] = 1
    struct.pack_into("<H", payload, 18, machine)
    return bytes(payload)


def tar_gzip(entries: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for name, payload in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    return output.getvalue()


def write_apk(
    path: Path,
    machines: dict[str, int],
    *,
    include_main: bool = True,
    include_desktop_wheel: bool = False,
    include_pygame_system: bool = True,
) -> None:
    private_entries = {"arch_rogue/game.pyc": b"game"}
    if include_main:
        private_entries["main.pyc"] = b"arch_rogue.game\x00main"

    with zipfile.ZipFile(path, "w") as apk:
        apk.writestr("assets/private.tar", tar_gzip(private_entries))
        for abi, machine in machines.items():
            native = elf_header(machine)
            bundle_entries = {
                "_python_bundle/modules/math.so": native,
                "_python_bundle/site-packages/pygame/__init__.pyc": b"pygame",
                "_python_bundle/site-packages/pygame/base.so": native,
                "_python_bundle/site-packages/jnius/__init__.pyc": b"jnius",
                "_python_bundle/site-packages/jnius/jnius.so": native,
            }
            if include_pygame_system:
                bundle_entries[
                    "_python_bundle/site-packages/pygame/system.so"
                ] = native
            if include_desktop_wheel:
                bundle_entries[
                    "_python_bundle/site-packages/pygame_ce.libs/libSDL2.so"
                ] = native
            apk.writestr(f"lib/{abi}/libmain.so", native)
            apk.writestr(
                f"lib/{abi}/libpybundle.so",
                tar_gzip(bundle_entries),
            )


class AndroidSourceContractTests(unittest.TestCase):
    def test_checked_in_source_and_spec_pass_preflight(self) -> None:
        validate_source_tree(ROOT / "src")
        self.assertEqual(
            validate_build_spec(ROOT / "buildozer.spec", ROOT),
            ("arm64-v8a", "armeabi-v7a"),
        )

    def test_build_spec_rejects_blank_android_permission(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            spec = Path(tmpdir) / "buildozer.spec"
            text = (ROOT / "buildozer.spec").read_text(encoding="utf-8")
            text = text.replace(
                "\n[buildozer]",
                "\nandroid.permissions = \n\n[buildozer]",
            )
            spec.write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(
                ValidationError,
                "omit android.permissions",
            ):
                validate_build_spec(spec, ROOT)

    def test_source_preflight_requires_root_main(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir)
            (source / "arch_rogue").mkdir()
            (source / "arch_rogue" / "game.py").write_text("def main(): pass\n")
            with self.assertRaisesRegex(ValidationError, "top-level main.py"):
                validate_source_tree(source)

    def test_source_preflight_rejects_host_native_library(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir)
            (source / "arch_rogue").mkdir()
            (source / "arch_rogue" / "game.py").write_text("def main(): pass\n")
            (source / "main.py").write_text(
                "from arch_rogue.game import main\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            )
            (source / "host.so").write_bytes(elf_header(62))
            with self.assertRaisesRegex(ValidationError, "host native binaries"):
                validate_source_tree(source)


class AndroidApkValidationTests(unittest.TestCase):
    def test_valid_dual_arm_apk_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            apk = Path(tmpdir) / "game.apk"
            write_apk(apk, {"arm64-v8a": 183, "armeabi-v7a": 40})
            report = validate_apk(apk, ("arm64-v8a", "armeabi-v7a"))
            self.assertEqual(report.entrypoint, "main.pyc")
            self.assertEqual(report.native_extensions["arm64-v8a"], 4)
            self.assertEqual(report.native_extensions["armeabi-v7a"], 4)

    def test_rejects_x86_64_extension_in_arm64_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            apk = Path(tmpdir) / "game.apk"
            write_apk(apk, {"arm64-v8a": 62})
            with self.assertRaisesRegex(
                ValidationError,
                "EM_X86_64.*arm64-v8a requires EM_AARCH64",
            ):
                validate_apk(apk, ("arm64-v8a",))

    def test_rejects_missing_pygame_system_extension(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            apk = Path(tmpdir) / "game.apk"
            write_apk(
                apk,
                {"arm64-v8a": 183},
                include_pygame_system=False,
            )
            with self.assertRaisesRegex(
                ValidationError,
                "missing native module pygame.system",
            ):
                validate_apk(apk, ("arm64-v8a",))

    def test_rejects_recipe_less_pygame_ce_wheel_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            apk = Path(tmpdir) / "game.apk"
            write_apk(apk, {"arm64-v8a": 183}, include_desktop_wheel=True)
            with self.assertRaisesRegex(ValidationError, "pygame_ce.libs"):
                validate_apk(apk, ("arm64-v8a",))

    def test_rejects_missing_root_entrypoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            apk = Path(tmpdir) / "game.apk"
            write_apk(apk, {"arm64-v8a": 183}, include_main=False)
            with self.assertRaisesRegex(ValidationError, "no root main.py"):
                validate_apk(apk, ("arm64-v8a",))


if __name__ == "__main__":
    unittest.main()
