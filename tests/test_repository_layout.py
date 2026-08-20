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

        toolchain = (ROOT / "android" / "toolchain.properties").read_text(
            encoding="utf-8"
        )
        self.assertIn("ODIN_VERSION=dev-2026-07", toolchain)
        self.assertIn(
            "ODIN_COMMIT=301c287de90393608fb7c5b260210e1e67caf0fd",
            toolchain,
        )
        self.assertIn("ODIN_BACKEND_LLVM_VERSION=21.1.8", toolchain)

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
            {"actions-maintenance.yml", "ci.yml", "mirror-public.yml"}
            if IS_PRIVATE_MASTER
            else {"build-release.yml"}
        )
        self.assertEqual({path.name for path in workflow_root.glob("*.yml")}, expected)
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
            "tools/verify_actor_assets.py",
            "tools/verify_story_assets.py",
            "tools/verify_chronicle_assets.py",
            "tools/verify_linux_raylib.py",
            "tests.test_repository_layout",
            "tools/mirror_public_snapshot.sh",
            '"arch-rogue-python/**"',
            "ODIN_SOURCE_TAG: dev-2026-07",
            'release: "false"',
            "branch: ${{ env.ODIN_SOURCE_TAG }}",
            'llvm-version: "21"',
            "build-type: release",
            "ODIN_COMMIT",
            "ODIN_BACKEND_LLVM_VERSION",
            'git -C "$HOME/odin" rev-parse HEAD',
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

    def test_public_release_is_odin_linux_android_only(self) -> None:
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
            "linux-x64.tar.gz",
            "Arch-Rogue.apk",
            "Arch-Rogue.aab",
            "tools/generate_download_manifest.py",
            "tools/verify_linux_raylib.py",
            "actions/deploy-pages@",
            '"arch-rogue-python/**"',
            "sha12:",
            "retention-days: 7",
            "publish-release:",
            "prepare-pages:",
            "ODIN_SOURCE_TAG: dev-2026-07",
            'release: "false"',
            "branch: ${{ env.ODIN_SOURCE_TAG }}",
            'llvm-version: "21"',
            "build-type: release",
            "ODIN_COMMIT",
            "ODIN_BACKEND_LLVM_VERSION",
            'git -C "$HOME/odin" rev-parse HEAD',
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

        release_job = workflow.partition("  publish-release:")[2].partition(
            "  prepare-pages:"
        )[0]
        pages_job = workflow.partition("  prepare-pages:")[2].partition(
            "  deploy-pages:"
        )[0]
        self.assertIn("contents: write", release_job)
        self.assertNotIn("pages: write", release_job)
        self.assertIn("pages: write", pages_job)
        self.assertNotIn("contents: write", pages_job)

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
