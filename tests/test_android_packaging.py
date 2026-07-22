from __future__ import annotations

import io
import os
import struct
import subprocess
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
    include_generated_metadata: bool = False,
    include_gpl_codec: bool = False,
    include_nested_gpl_codec: bool = False,
    include_build_tool_source: bool = False,
    missing_license_asset: str | None = None,
) -> None:
    private_entries = {
        "arch_rogue/game.pyc": b"game",
        "arch_rogue/assets/licenses/LICENSE.txt": b"Apache License 2.0",
        "arch_rogue/assets/licenses/NOTICE.txt": b"Third-party notices",
        "arch_rogue/assets/licenses/LGPL-2.1.txt": b"GNU LGPL 2.1",
    }
    if missing_license_asset is not None:
        private_entries.pop(
            f"arch_rogue/assets/licenses/{missing_license_asset}", None
        )
    if include_main:
        private_entries["main.pyc"] = (
            b"PYGAME_BLEND_ALPHA_SDL2\x001\x00arch_rogue.game\x00main"
        )
    if include_generated_metadata:
        private_entries["arch_rogue.egg-info/PKG-INFO"] = b"Version: stale"
    if include_build_tool_source:
        private_entries["buildozer/__init__.pyc"] = b"build tool source"
        private_entries["pythonforandroid/tool.py"] = b"p4a source"

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
            if include_nested_gpl_codec:
                bundle_entries[
                    "_python_bundle/site-packages/pygame/mixer.so"
                ] = native + b"\x00libmad.so\x00mad_decoder\x00"
            apk.writestr(f"lib/{abi}/libmain.so", native)
            apk.writestr(
                f"lib/{abi}/libpybundle.so",
                tar_gzip(bundle_entries),
            )
            if include_gpl_codec:
                # A standalone codec .so (e.g. libSDL2_mixer pulling libmad)
                # carrying a GPL-family marker. Valid ELF header so it reaches
                # the codec scan after the architecture check.
                apk.writestr(
                    f"lib/{abi}/libSDL2_mixer.so",
                    native + b"\x00libmad.so\x00mad_decoder\x00",
                )


class AndroidSourceContractTests(unittest.TestCase):
    def test_checked_in_source_and_spec_pass_preflight(self) -> None:
        validate_source_tree(ROOT / "src")
        self.assertEqual(
            validate_build_spec(ROOT / "buildozer.spec", ROOT),
            ("arm64-v8a", "armeabi-v7a"),
        )

    def test_android_workflow_installs_libtool_macro_prerequisites(self) -> None:
        workflow = (
            ROOT / ".github" / "workflows" / "build-release.yml"
        ).read_text(encoding="utf-8")
        android_job = workflow[workflow.index("\n  android:") :]
        self.assertIn("runs-on: ubuntu-24.04", android_job)
        self.assertIn("libltdl-dev", android_job)
        self.assertIn("libtool", android_job)
        self.assertIn("LT_SYS_SYMBOL_USCORE", android_job)

    def test_public_android_apk_uses_persistent_release_signing(self) -> None:
        workflow = (
            ROOT / ".github" / "workflows" / "build-release.yml"
        ).read_text(encoding="utf-8")
        android_job = workflow[
            workflow.index("\n  android:") : workflow.index("\n  release:")
        ]
        self.assertIn("ARCH_ROGUE_ANDROID_KEYSTORE_BASE64", android_job)
        self.assertIn("ARCH_ROGUE_ANDROID_KEYSTORE_PASSWD", android_job)
        self.assertIn("ARCH_ROGUE_ANDROID_KEYALIAS", android_job)
        self.assertIn("ARCH_ROGUE_ANDROID_KEYALIAS_PASSWD", android_job)
        self.assertIn("if: github.ref == 'refs/heads/master'", android_job)
        self.assertIn("environment: android-release", android_job)
        self.assertIn("./tools/build_android.sh release", android_job)
        self.assertNotIn("./tools/build_android.sh debug", android_job)
        self.assertIn("ARCH_ROGUE_ANDROID_OUTPUT_APK", android_job)
        self.assertNotIn("find bin", android_job)
        self.assertIn("android-release.apk", android_job)

        fingerprint = (
            ROOT / "android" / "release-signing-cert.sha256"
        ).read_text(encoding="ascii").strip()
        self.assertRegex(fingerprint, r"^[0-9a-f]{64}$")

        build_script = (ROOT / "tools" / "build_android.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("configure_release_signing", build_script)
        self.assertIn("release-signing-cert.sha256", build_script)
        self.assertIn("Refusing to publish an APK", build_script)

    def test_signer_verification_rejects_invalid_signing_contracts(self) -> None:
        build_script = (ROOT / "tools" / "build_android.sh").read_text(
            encoding="utf-8"
        )
        function_start = build_script.index("verify_apk_signer() {")
        function_end = build_script.index(
            "\n# SIGNER_VERIFICATION_FUNCTION_END",
            function_start,
        )
        function = build_script[function_start:function_end]
        expected = "1" * 64

        cases = (
            (
                "valid",
                0,
                f"Number of signers: 1\nV2 Signer: certificate SHA-256 digest: {expected}\n",
                expected,
                True,
            ),
            ("unsigned", 1, "DOES NOT VERIFY\n", expected, False),
            (
                "multiple",
                0,
                f"Number of signers: 2\nV2 Signer: certificate SHA-256 digest: {expected}\n",
                expected,
                False,
            ),
            (
                "ten-signers",
                0,
                f"Number of signers: 10\nV2 Signer: certificate SHA-256 digest: {expected}\n",
                expected,
                False,
            ),
            (
                "mismatch",
                0,
                f"Number of signers: 1\nV2 Signer: certificate SHA-256 digest: {'2' * 64}\n",
                expected,
                False,
            ),
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            for name, exit_code, output, fingerprint, should_pass in cases:
                with self.subTest(case=name):
                    fake_apksigner = root / f"apksigner-{name}"
                    fake_apksigner.write_text(
                        "#!/bin/sh\n"
                        + "cat <<'EOF'\n"
                        + output
                        + "EOF\n"
                        + f"exit {exit_code}\n",
                        encoding="utf-8",
                    )
                    fake_apksigner.chmod(0o700)
                    exercise = (
                        "set -u\n"
                        + f"APKSIGNER='{fake_apksigner}'\n"
                        + function
                        + "\n"
                        + f"verify_apk_signer ignored.apk '{fingerprint}'\n"
                    )
                    result = subprocess.run(
                        ["bash", "-c", exercise],
                        cwd=ROOT,
                        text=True,
                        capture_output=True,
                    )
                    self.assertEqual(result.returncode == 0, should_pass)

    def test_release_build_fails_closed_without_signing_credentials(self) -> None:
        env = os.environ.copy()
        for name in (
            "ARCH_ROGUE_ANDROID_KEYSTORE",
            "ARCH_ROGUE_ANDROID_KEYSTORE_PASSWD",
            "ARCH_ROGUE_ANDROID_KEYALIAS",
            "ARCH_ROGUE_ANDROID_KEYALIAS_PASSWD",
        ):
            env.pop(name, None)

        result = subprocess.run(
            ["bash", "tools/build_android.sh", "release"],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("release signing is required", result.stderr)
        self.assertIn("ARCH_ROGUE_ANDROID_KEYSTORE", result.stderr)
        self.assertNotIn("Arch Rogue Android build:", result.stdout)

    def test_android_sdk_bootstrap_repairs_partial_ci_cache(self) -> None:
        build_script = (ROOT / "tools" / "build_android.sh").read_text(
            encoding="utf-8"
        )
        function_start = build_script.index("android_sdk_root() {")
        function_end = build_script.index(
            "\nrepair_android_sdk_bootstrap\naccept_android_licenses",
            function_start,
        )
        functions = build_script[function_start:function_end]
        exercise = functions + r'''
set -eu
sdk="$(android_sdk_root)"

# A cancelled/cache-restored install must be removed so Buildozer downloads it.
mkdir -p "$sdk/licenses"
repair_android_sdk_bootstrap
test ! -e "$sdk"

# Modern command-line tools must satisfy Buildozer 1.6.0's legacy lookup path.
mkdir -p "$sdk/cmdline-tools/latest/bin"
printf '#!/bin/sh\nexit 0\n' > "$sdk/cmdline-tools/latest/bin/sdkmanager"
printf '#!/bin/sh\nexit 0\n' > "$sdk/cmdline-tools/latest/bin/avdmanager"
chmod +x "$sdk/cmdline-tools/latest/bin/sdkmanager" \
  "$sdk/cmdline-tools/latest/bin/avdmanager"
repair_android_sdk_bootstrap
test -x "$sdk/tools/bin/sdkmanager"
test -x "$sdk/tools/bin/avdmanager"

# License seeding must not create an empty SDK that suppresses bootstrapping.
rm -rf "$sdk"
accept_android_licenses
test ! -e "$sdk"
'''
        with tempfile.TemporaryDirectory() as home:
            env = os.environ.copy()
            env["HOME"] = home
            env.pop("ANDROIDSDK", None)
            subprocess.run(
                ["bash", "-c", exercise],
                check=True,
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
            )


    def test_build_spec_rejects_invalid_release_artifact_command(self) -> None:
        for invalid_artifact in ("_apk", "APK"):
            with self.subTest(artifact=invalid_artifact), tempfile.TemporaryDirectory() as tmpdir:
                spec = Path(tmpdir) / "buildozer.spec"
                text = (ROOT / "buildozer.spec").read_text(encoding="utf-8")
                text = text.replace(
                    "android.release_artifact = apk",
                    f"android.release_artifact = {invalid_artifact}",
                )
                spec.write_text(text, encoding="utf-8")
                with self.assertRaisesRegex(
                    ValidationError,
                    "android.release_artifact must be 'apk'",
                ):
                    validate_build_spec(spec, ROOT)

    def test_build_spec_requires_branded_presplash(self) -> None:
        # 4.4.8: the APK loading screen must use the Arch Rogue title logo, not
        # python-for-android's default SDL splash.
        with tempfile.TemporaryDirectory() as tmpdir:
            spec = Path(tmpdir) / "buildozer.spec"
            text = (ROOT / "buildozer.spec").read_text(encoding="utf-8")
            text = text.replace(
                "presplash.filename = src/arch_rogue/assets/sprites/menus/title_logo.png\n",
                "",
            )
            spec.write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(
                ValidationError,
                "presplash.filename must point at the Arch Rogue title logo",
            ):
                validate_build_spec(spec, ROOT)

    def test_build_spec_rejects_missing_presplash_asset(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            spec = Path(tmpdir) / "buildozer.spec"
            text = (ROOT / "buildozer.spec").read_text(encoding="utf-8")
            text = text.replace(
                "presplash.filename = src/arch_rogue/assets/sprites/menus/title_logo.png",
                "presplash.filename = android/presplash.png",
            )
            spec.write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(
                ValidationError,
                "presplash.filename asset is missing",
            ):
                validate_build_spec(spec, ROOT)

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

    def test_build_spec_requires_generated_metadata_exclusions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            spec = Path(tmpdir) / "buildozer.spec"
            text = (ROOT / "buildozer.spec").read_text(encoding="utf-8")
            text = text.replace(
                "source.exclude_dirs = __pycache__,arch_rogue.egg-info\n",
                "",
            )
            spec.write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(
                ValidationError,
                "source.exclude_dirs.*arch_rogue.egg-info",
            ):
                validate_build_spec(spec, ROOT)

    def test_source_preflight_requires_root_main(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir)
            (source / "arch_rogue").mkdir()
            (source / "arch_rogue" / "game.py").write_text("def main(): pass\n")
            with self.assertRaisesRegex(ValidationError, "top-level main.py"):
                validate_source_tree(source)

    def test_source_preflight_requires_alpha_override_before_game_import(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir)
            (source / "arch_rogue").mkdir()
            (source / "arch_rogue" / "game.py").write_text("def main(): pass\n")
            (source / "main.py").write_text(
                "import os\n"
                "from arch_rogue.game import main\n"
                "os.environ.setdefault('PYGAME_BLEND_ALPHA_SDL2', '1')\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            )
            with self.assertRaisesRegex(
                ValidationError,
                "PYGAME_BLEND_ALPHA_SDL2=1 before importing",
            ):
                validate_source_tree(source)

    def test_source_preflight_rejects_host_native_library(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir)
            (source / "arch_rogue").mkdir()
            (source / "arch_rogue" / "game.py").write_text("def main(): pass\n")
            (source / "main.py").write_text(
                "import os\n"
                "os.environ.setdefault('PYGAME_BLEND_ALPHA_SDL2', '1')\n"
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

    def test_rejects_generated_source_metadata_in_private_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            apk = Path(tmpdir) / "game.apk"
            write_apk(
                apk,
                {"arm64-v8a": 183},
                include_generated_metadata=True,
            )
            with self.assertRaisesRegex(
                ValidationError,
                "generated source metadata.*egg-info",
            ):
                validate_apk(apk, ("arm64-v8a",))

    def test_rejects_gpl_codec_in_bundled_native_library(self) -> None:
        # 4.3.17 WS-G: a copyleft MP3 decoder (libmad/libmp3lame/libfaad)
        # pulled in via SDL2_mixer must fail the audit.
        with tempfile.TemporaryDirectory() as tmpdir:
            apk = Path(tmpdir) / "game.apk"
            write_apk(
                apk,
                {"arm64-v8a": 183, "armeabi-v7a": 40},
                include_gpl_codec=True,
            )
            with self.assertRaisesRegex(
                ValidationError,
                "GPL-family codec marker.*libmad",
            ):
                validate_apk(apk, ("arm64-v8a", "armeabi-v7a"))

    def test_rejects_gpl_codec_in_nested_python_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            apk = Path(tmpdir) / "game.apk"
            write_apk(
                apk,
                {"arm64-v8a": 183},
                include_nested_gpl_codec=True,
            )
            with self.assertRaisesRegex(
                ValidationError,
                "GPL-family codec marker.*libmad",
            ):
                validate_apk(apk, ("arm64-v8a",))

    def test_rejects_missing_in_app_license_asset(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            apk = Path(tmpdir) / "game.apk"
            write_apk(
                apk,
                {"arm64-v8a": 183},
                missing_license_asset="NOTICE.txt",
            )
            with self.assertRaisesRegex(
                ValidationError,
                "missing in-app license assets.*NOTICE.txt",
            ):
                validate_apk(apk, ("arm64-v8a",))

    def test_rejects_build_tool_source_in_private_bundle(self) -> None:
        # 4.3.17 WS-G: buildozer/python-for-android (L)GPL build-tool source
        # must never ship inside assets/private.tar.
        with tempfile.TemporaryDirectory() as tmpdir:
            apk = Path(tmpdir) / "game.apk"
            write_apk(
                apk,
                {"arm64-v8a": 183},
                include_build_tool_source=True,
            )
            with self.assertRaisesRegex(
                ValidationError,
                "build-tool source.*buildozer",
            ):
                validate_apk(apk, ("arm64-v8a",))

    def test_rejects_missing_root_entrypoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            apk = Path(tmpdir) / "game.apk"
            write_apk(apk, {"arm64-v8a": 183}, include_main=False)
            with self.assertRaisesRegex(ValidationError, "no root main.py"):
                validate_apk(apk, ("arm64-v8a",))


if __name__ == "__main__":
    unittest.main()
