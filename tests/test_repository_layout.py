# SPDX-License-Identifier: Apache-2.0
"""Repository-cutover contracts for the canonical Odin root."""

from __future__ import annotations

import unittest
from pathlib import Path

from tools import android_audit


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_PUBLIC_WORKFLOW = (
    ROOT / "tools" / "public-repo" / "workflows" / "build-release.yml"
)
PUBLIC_SNAPSHOT_WORKFLOW = ROOT / ".github" / "workflows" / "build-release.yml"
IS_PRIVATE_MASTER = PRIVATE_PUBLIC_WORKFLOW.is_file()


class RepositoryLayoutTests(unittest.TestCase):
    def test_odin_project_is_canonical_at_root(self) -> None:
        for relative in (
            "build.sh",
            "toolchain.properties",
            "src/main.odin",
            "tests/core_test.odin",
            "assets",
            "android/toolchain.properties",
            "android/release-signing-cert.sha256",
            "tools/android.sh",
            "tools/verify_linux_raylib.py",
            "vendor/raylib/raylib.odin",
            "vendor/raylib/linux/PROVENANCE.md",
            "vendor/raylib/linux/SHA256SUMS",
            "vendor/raylib/wasm/PROVENANCE.md",
            "vendor/raylib/wasm/SHA256SUMS",
            "web/toolchain.properties",
            "web/shell.html",
            "web/library_archrogue.js",
            "web/main_web.c",
            "src/main_web.odin",
            "tools/web.sh",
            "tools/web_audit.py",
            "tools/rebuild_raylib_web.sh",
            "ARCHITECTURE.md",
            "PARITY.md",
            "CHANGELOG.md",
            "LICENSE",
            "NOTICE",
            "website/index.html",
            "arch-rogue-python/src/arch_rogue/game.py",
        ):
            with self.subTest(relative=relative):
                self.assertTrue((ROOT / relative).exists(), relative)

        toolchain = (ROOT / "toolchain.properties").read_text(encoding="utf-8")
        self.assertIn("ODIN_VERSION=dev-2026-07", toolchain)
        self.assertIn(
            "ODIN_COMMIT=301c287de90393608fb7c5b260210e1e67caf0fd",
            toolchain,
        )
        self.assertIn("ODIN_BACKEND_LLVM_VERSION=21.1.8", toolchain)
        self.assertIn("RAYLIB_VERSION=6.0", toolchain)

        for platform_contract in (
            ROOT / "android" / "toolchain.properties",
            ROOT / "web" / "toolchain.properties",
        ):
            platform_text = platform_contract.read_text(encoding="utf-8")
            self.assertNotIn("ODIN_VERSION=", platform_text)
            self.assertNotIn("RAYLIB_VERSION=", platform_text)

        build_wrapper = (ROOT / "build.sh").read_text(encoding="utf-8")
        self.assertIn("verify_toolchain linux", build_wrapper)
        self.assertIn("verify_toolchain odin", build_wrapper)
        web_wrapper = (ROOT / "tools" / "web.sh").read_text(encoding="utf-8")
        self.assertIn('verify_toolchain.sh" odin', web_wrapper)
        self.assertIn('WASM_OBJ="$BUILD_ROOT/archrogue.wasm.obj"', web_wrapper)

        gradle_properties = (ROOT / "android" / "gradle.properties").read_text(
            encoding="utf-8"
        )
        self.assertIn("android.enableResourceOptimizations=false", gradle_properties)

        self.assertFalse((ROOT / "ar-odin").exists())
        for retired_root_path in (
            "pyproject.toml",
            "buildozer.spec",
            "server",
        ):
            self.assertFalse((ROOT / retired_root_path).exists(), retired_root_path)

    def test_only_odin_actions_are_active(self) -> None:
        workflow_root = ROOT / ".github" / "workflows"
        expected = (
            # steam-deploy.yml is the private-only Odin Steam publish lane
            # (STEAM.md S5); it must never appear in the public snapshot.
            {"actions-maintenance.yml", "ci.yml", "mirror-public.yml", "steam-deploy.yml"}
            if IS_PRIVATE_MASTER
            else {"build-release.yml"}
        )
        self.assertEqual({path.name for path in workflow_root.glob("*.yml")}, expected)
        if not IS_PRIVATE_MASTER:
            self.assertFalse((workflow_root / "steam-deploy.yml").exists())
        self.assertFalse((workflow_root / "server-deploy.yml").exists())

        archive_workflows = ROOT / "arch-rogue-python" / ".github"
        if IS_PRIVATE_MASTER:
            self.assertTrue((archive_workflows / "workflows/steam-deploy.yml").is_file())
            self.assertTrue((archive_workflows / "workflows/server-deploy.yml").is_file())
        else:
            self.assertFalse(archive_workflows.exists())

    @unittest.skipUnless(IS_PRIVATE_MASTER, "private CI is absent from the public snapshot")
    def test_private_ci_targets_odin_and_snapshot_guards(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        for command in (
            "bash build.sh check",
            "bash build.sh test",
            "bash build.sh release",
            "-target:freestanding_wasm32",
            "tools/verify_actor_assets.py",
            "tools/verify_story_assets.py",
            "tools/verify_chronicle_assets.py",
            "tools/verify_linux_raylib.py",
            "tests.test_repository_layout",
            "tools/mirror_public_snapshot.sh",
            '"arch-rogue-python/**"',
            "tools/verify_toolchain.sh metadata",
            "tools/verify_toolchain.sh odin",
            'release: "false"',
            "branch: ${{ steps.toolchain.outputs.odin_version }}",
            "llvm-version: ${{ steps.toolchain.outputs.odin_llvm_major }}",
            "build-type: release",
        ):
            self.assertIn(command, workflow)
        for legacy in (
            "pip install",
            "pyproject.toml",
            "pygame",
            "buildozer",
            "ODIN_RELEASE",
            "odin version",
        ):
            self.assertNotIn(legacy.lower(), workflow.lower())
        self.assertEqual(
            workflow.count("uses: laytan/setup-odin@"),
            workflow.count('release: "false"'),
        )

    def test_public_release_covers_odin_linux_android_web(self) -> None:
        workflow_path = (
            PRIVATE_PUBLIC_WORKFLOW if IS_PRIVATE_MASTER else PUBLIC_SNAPSHOT_WORKFLOW
        )
        workflow = workflow_path.read_text(encoding="utf-8")
        for contract in (
            "branches: [master]",
            "runs-on: ubuntu-22.04",
            "bash build.sh check",
            "bash build.sh test",
            "bash build.sh release",
            "bash tools/android.sh release",
            "bash android/gradlew",
            "bash build.sh web-build",
            "linux-x64.tar.gz",
            "Arch-Rogue.apk",
            "Arch-Rogue.aab",
            "-web.tar.gz",
            "web/toolchain.properties",
            "emscripten-core/emsdk",
            "tools/generate_download_manifest.py",
            "tools/verify_linux_raylib.py",
            "actions/deploy-pages@",
            '"arch-rogue-python/**"',
            "sha12:",
            "retention-days: 7",
            "publish-release:",
            "prepare-pages:",
            "tools/verify_toolchain.sh metadata",
            "tools/verify_toolchain.sh odin",
            'release: "false"',
            "branch: ${{ steps.toolchain.outputs.odin_version }}",
            "llvm-version: ${{ steps.toolchain.outputs.odin_llvm_major }}",
            "build-type: release",
        ):
            self.assertIn(contract, workflow)
        for legacy in (
            "pyinstaller",
            "python -m pip install -e",
            "buildozer",
            "steam-deploy",
            "server-deploy",
            "sha7",
            "ODIN_RELEASE",
            "odin version",
        ):
            self.assertNotIn(legacy.lower(), workflow.lower())
        self.assertEqual(
            workflow.count("uses: laytan/setup-odin@"),
            workflow.count('release: "false"'),
        )

        android_sdk_install = workflow.partition(
            "      - name: Install pinned Android SDK and NDK"
        )[2].partition("      - name: Verify Android SDK cache contents")[0]
        for contract in (
            'hosted_sdk_root=/usr/local/lib/android/sdk',
            '$hosted_sdk_root/cmdline-tools/latest/bin/sdkmanager',
            '--channel=0 --verbose',
            'license_status="${PIPESTATUS[1]}"',
            'sdkmanager --licenses failed with exit code',
        ):
            self.assertIn(contract, android_sdk_install)
        self.assertNotIn("--licenses >/dev/null || true", android_sdk_install)

        gradle_provision = workflow.partition(
            "      - name: Provision pinned Gradle and AGP with network access"
        )[2].partition("      - name: Restore release keystore")[0]
        self.assertIn(":app:tasks", gradle_provision)
        self.assertNotIn("--offline", gradle_provision)
        self.assertIn('ARCH_ROGUE_GRADLE_ONLINE: "1"', workflow)

        android_tool = (ROOT / "tools" / "android.sh").read_text(encoding="utf-8")
        self.assertIn('ARCH_ROGUE_GRADLE_ONLINE:-0', android_tool)
        self.assertIn("local -a dependency_mode=(--offline)", android_tool)
        self.assertIn("1) dependency_mode=()", android_tool)

        web_package = workflow.partition(
            "      - name: Stage release-named web archive"
        )[2].partition("      - name: Upload web release archive")[0]
        self.assertIn('archive_listing="$RUNNER_TEMP/arch-rogue-web-archive.txt"', web_package)
        self.assertIn('tar -tzf "dist/$archive" > "$archive_listing"', web_package)
        self.assertIn("sed -n '1,5p' \"$archive_listing\"", web_package)
        self.assertNotIn("| head", web_package)

        release_job = workflow.partition("  publish-release:")[2].partition(
            "  prepare-pages:"
        )[0]
        pages_job = workflow.partition("  prepare-pages:")[2].partition(
            "  deploy-pages:"
        )[0]
        deploy_job = workflow.partition("  deploy-pages:")[2]
        self.assertIn("contents: write", release_job)
        self.assertNotIn("pages: write", release_job)
        self.assertIn(
            'test "$(find release-assets -maxdepth 1 -type f | wc -l)" -eq 4',
            release_job,
        )
        self.assertIn("pages: write", pages_job)
        self.assertNotIn("contents: write", pages_job)

        for contract in (
            "actions/download-artifact@",
            "name: arch-rogue-web",
            "path: pages-input/web",
            'pages_root="build/pages"',
            'play_root="$pages_root/play"',
            'ARCHIVE_ROOT = "arch-rogue-web"',
            "member.issym() or member.islnk()",
            "roots != {ARCHIVE_ROOT} or root_entries != 1",
            'test -f "$play_root/index.html"',
            'test -f "$play_root/packs.json"',
            'test -d "$play_root/packs"',
            'test ! -e "$play_root/arch-rogue-web"',
            'python3 tools/web_audit.py --dist "$play_root"',
            "1_000_000_000",
            "Pages site contains symbolic links",
            "path: build/pages",
        ):
            self.assertIn(contract, pages_job)
        self.assertNotIn("bash build.sh web-build", pages_job)
        self.assertNotIn("path: website", pages_job)

        web_smoke = (ROOT / "tools" / "web_smoke.mjs").read_text(encoding="utf-8")
        self.assertIn("--entry-path", web_smoke)
        self.assertIn("entryPath.includes('..')", web_smoke)

        for contract in (
            "timeout-minutes: 20",
            'base="${PAGE_URL%/}/"',
            '"${base}play/"',
            '"${base}play/packs.json"',
            "--retry-all-errors",
            "deployed play/packs.json is invalid",
        ):
            self.assertIn(contract, deploy_job)

    def test_aab_orientation_audit_accepts_bundletool_enum_formats(self) -> None:
        for value in ("sensorLandscape", "6", "0x6", "0x00000006"):
            with self.subTest(value=value):
                manifest = f'<activity android:screenOrientation="{value}" />'
                self.assertEqual(
                    android_audit.aab_sensor_landscape_value(manifest),
                    value,
                )
        for value in ("portrait", "1", "0x1"):
            with self.subTest(value=value):
                manifest = f'<activity android:screenOrientation="{value}" />'
                self.assertIsNone(
                    android_audit.aab_sensor_landscape_value(manifest)
                )
        self.assertIsNone(android_audit.aab_sensor_landscape_value("<activity />"))

    def test_aab_signature_audit_allows_pinned_self_signed_certificate(self) -> None:
        self_signed_report = """jar verified.

Warning:
This jar contains entries whose signer certificate is self-signed.
"""
        android_audit.audit_jarsigner_report(self_signed_report)

        with self.assertRaisesRegex(android_audit.AuditError, "not covered"):
            android_audit.audit_jarsigner_report(
                "jar verified.\nThis jar contains unsigned entries.\n"
            )
        with self.assertRaisesRegex(android_audit.AuditError, "did not confirm"):
            android_audit.audit_jarsigner_report("jar is unsigned.\n")

        source = (ROOT / "tools" / "android_audit.py").read_text(encoding="utf-8")
        self.assertIn('["jarsigner", "-verify", "-verbose"', source)
        self.assertNotIn('["jarsigner", "-verify", "-strict"', source)
        self.assertIn("exactly one JAR signature block", source)

    def test_android_release_certificate_is_repository_pinned(self) -> None:
        fingerprint = (
            ROOT / "android" / "release-signing-cert.sha256"
        ).read_text(encoding="utf-8").strip()
        self.assertRegex(fingerprint, r"^[0-9a-f]{64}$")

        android_tool = (ROOT / "tools" / "android.sh").read_text(encoding="utf-8")
        gradle = (ROOT / "android" / "app" / "build.gradle.kts").read_text(
            encoding="utf-8"
        )
        self.assertIn("release-signing-cert.sha256", android_tool)
        self.assertIn("RELEASE_CERT_SHA256", android_tool)
        for legacy_variable in (
            "ARCH_ROGUE_ANDROID_KEYSTORE_PASSWD",
            "ARCH_ROGUE_ANDROID_KEYALIAS",
            "ARCH_ROGUE_ANDROID_KEYALIAS_PASSWD",
        ):
            self.assertIn(legacy_variable, android_tool)
        self.assertNotIn("ARCH_ROGUE_ANDROID_CERT_SHA256", android_tool + gradle)
        self.assertFalse((ROOT / "tools" / "set_public_android_secrets.sh").exists())

        workflow_path = (
            PRIVATE_PUBLIC_WORKFLOW if IS_PRIVATE_MASTER else PUBLIC_SNAPSHOT_WORKFLOW
        )
        workflow = workflow_path.read_text(encoding="utf-8")
        for existing_secret in (
            "secrets.ARCH_ROGUE_ANDROID_KEYSTORE_BASE64",
            "secrets.ARCH_ROGUE_ANDROID_KEYSTORE_PASSWD",
            "secrets.ARCH_ROGUE_ANDROID_KEYALIAS",
            "secrets.ARCH_ROGUE_ANDROID_KEYALIAS_PASSWD",
        ):
            self.assertIn(existing_secret, workflow)
        for unnecessary_secret in (
            "secrets.ARCH_ROGUE_ANDROID_STORE_PASSWORD",
            "secrets.ARCH_ROGUE_ANDROID_KEY_ALIAS",
            "secrets.ARCH_ROGUE_ANDROID_KEY_PASSWORD",
            "secrets.ARCH_ROGUE_ANDROID_CERT_SHA256",
        ):
            self.assertNotIn(unnecessary_secret, workflow)


if __name__ == "__main__":
    unittest.main()
