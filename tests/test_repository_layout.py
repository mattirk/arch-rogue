# SPDX-License-Identifier: Apache-2.0
"""Repository-cutover contracts for the canonical Odin root."""

from __future__ import annotations

import unittest
from pathlib import Path


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
            "vendor/raylib/raylib.odin",
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
            "android-release.apk",
            "android-release.aab",
            "tools/generate_download_manifest.py",
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
