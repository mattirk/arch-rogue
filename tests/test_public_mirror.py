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

"""Regression tests for the private-master to public-repo snapshot boundary.

The real mirror script is copied into a synthetic master tree and resolves that
synthetic tree as its root. These tests therefore exercise the same allowlist,
archive exclusions, workflow overlay, deletion, and validation used by CI.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "tools" / "mirror_public_snapshot.sh"
PUBLIC_WORKFLOW = "name: Canonical Odin public build\nsource: root overlay\n"
ARCHIVED_WORKFLOW = "name: Retired Python release (must never run)\n"
MAX_PUBLIC_FILE_BYTES = 95 * 1024 * 1024


def _write(root: Path, relative: str, content: str = "x\n") -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(content, encoding="utf-8")


@unittest.skipIf(shutil.which("rsync") is None, "rsync is not installed")
@unittest.skipUnless(
    SCRIPT.exists(),
    "mirror script is private-master-only (not copied to the public snapshot)",
)
class PublicMirrorSnapshotTests(unittest.TestCase):
    def _build_fake_master(self, root: Path) -> None:
        # Canonical Odin root: every allowlisted top-level path is represented.
        for relative in (
            ".gitignore",
            "README.md",
            "ARCHITECTURE.md",
            "PARITY.md",
            "CHANGELOG.md",
            "LICENSE",
            "NOTICE",
            "build.sh",
            "toolchain.properties",
            "android/README.md",
            "android/release-signing-cert.sha256",
            "assets/actors/player.png",
            "assets/audio/sfx/manifest.json",
            "assets/audio/sfx/README.md",
            "assets/audio/sfx/licensed_01.wav",
            "arch-rogue-sfx-runtime-private.tar.gz",
            "src/main.odin",
            "src/app.odin",
            "tests/core_test.odin",
            "tools/android.sh",
            "tools/sfx_bundle.py",
            "tools/fetch_private_sfx.sh",
            "vendor/raylib/raylib.odin",
            "vendor/raylib/wasm/SHA256SUMS",
            "web/toolchain.properties",
            "web/shell.html",
            "src/main_web.odin",
            "website/index.html",
            # Retired Python implementation remains browsable as source.
            "arch-rogue-python/README.md",
            "arch-rogue-python/LICENSE",
            "arch-rogue-python/pyproject.toml",
            "arch-rogue-python/buildozer.spec",
            "arch-rogue-python/android/README.md",
            "arch-rogue-python/docs/multiplayer.md",
            "arch-rogue-python/server/server.py",
            "arch-rogue-python/src/arch_rogue/game.py",
            "arch-rogue-python/src/arch_rogue/steam.py",
            "arch-rogue-python/tests/test_game.py",
            "arch-rogue-python/tests/test_steam_integration.py",
            "arch-rogue-python/tools/bench_desktop.py",
            # Root-private metadata and paths omitted by the exact allowlist.
            "AGENTS.md",
            ".agents/project/rules.md",
            ".claude/settings.json",
            ".codex/config.toml",
            ".github/dependabot.yml",
            ".github/workflows/private-ci.yml",
            "docs/private-root-notes.md",
            "pyproject.toml",
            "buildozer.spec",
            "server/private-root-server.py",
            "stray_root_secret.txt",
            # Root tools that must remain private.
            "tools/set_public_android_secrets.sh",
            "tools/steam/render_build_scripts.py",
            # The Steam plan and estate notes never reach the mirror.
            "STEAM.md",
            # Python archive content that may never reach the mirror.
            "arch-rogue-python/.github/workflows/server-deploy.yml",
            "arch-rogue-python/.github/workflows/steam-deploy.yml",
            "arch-rogue-python/website/index.html",
            "arch-rogue-python/docs/steam.md",
            "arch-rogue-python/docs/server-deployment.md",
            "arch-rogue-python/server/deploy/arch-rogue-server.service",
            "arch-rogue-python/tools/steam/store_asset.bin",
            "arch-rogue-python/tools/build_steam_linux.sh",
            "arch-rogue-python/tools/build_steam_windows.sh",
            "arch-rogue-python/tools/deploy_deck.sh",
            "arch-rogue-python/tools/mirror_public_snapshot.sh",
            "arch-rogue-python/tools/set_public_android_secrets.sh",
            # Generated artifacts and caches inside otherwise public trees.
            "assets/__pycache__/asset.cpython-314.pyc",
            "src/.odin-cache/check.bin",
            "tests/.pytest_cache/CACHEDIR.TAG",
            "tools/.ruff_cache/state",
            "android/app/build/outputs/game.apk",
            "arch-rogue-python/.venv/bin/python",
            "arch-rogue-python/build/arch-rogue",
            "arch-rogue-python/dist/arch-rogue.exe",
            "arch-rogue-python/src/arch_rogue/__pycache__/game.pyc",
            "arch-rogue-python/tests/.mypy_cache/state",
        ):
            _write(root, relative)


        _write(
            root,
            "tools/public-repo/workflows/build-release.yml",
            PUBLIC_WORKFLOW,
        )
        _write(
            root,
            "arch-rogue-python/tools/public-repo/workflows/build-release.yml",
            ARCHIVED_WORKFLOW,
        )
        _ = shutil.copy2(SCRIPT, root / "tools" / "mirror_public_snapshot.sh")

    def _run_mirror(
        self,
        root: Path,
        destination: Path,
        *,
        validate_only: bool = False,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        command = ["bash", str(root / "tools" / "mirror_public_snapshot.sh")]
        if validate_only:
            command.append("--validate-only")
        command.append(str(destination))
        return subprocess.run(
            command,
            check=check,
            capture_output=True,
            text=True,
        )

    def test_allowlist_copies_odin_root_and_python_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "master"
            destination = Path(tmpdir) / "public"
            self._build_fake_master(root)
            _ = self._run_mirror(root, destination, check=True)

            expected_top_level = {
                ".gitignore",
                ".github",
                "README.md",
                "ARCHITECTURE.md",
                "PARITY.md",
                "CHANGELOG.md",
                "LICENSE",
                "NOTICE",
                "build.sh",
                "toolchain.properties",
                "android",
                "assets",
                "src",
                "tests",
                "tools",
                "vendor",
                "web",
                "website",
                "arch-rogue-python",
            }
            self.assertEqual(
                {path.name for path in destination.iterdir()}, expected_top_level
            )

            for relative in (
                "build.sh",
                "toolchain.properties",
                "src/main.odin",
                "src/app.odin",
                "tests/core_test.odin",
                "vendor/raylib/raylib.odin",
                "vendor/raylib/wasm/SHA256SUMS",
                "android/README.md",
                "android/release-signing-cert.sha256",
                "assets/actors/player.png",
                "assets/audio/sfx/manifest.json",
                "assets/audio/sfx/README.md",
                "tools/android.sh",
                "tools/sfx_bundle.py",
                "tools/fetch_private_sfx.sh",
                "web/toolchain.properties",
                "web/shell.html",
                "src/main_web.odin",
                "website/index.html",
                "arch-rogue-python/README.md",
                "arch-rogue-python/pyproject.toml",
                "arch-rogue-python/android/README.md",
                "arch-rogue-python/docs/multiplayer.md",
                "arch-rogue-python/server/server.py",
                "arch-rogue-python/src/arch_rogue/game.py",
                # Runtime Steam source remains visible; only private release
                # and deployment material is excluded.
                "arch-rogue-python/src/arch_rogue/steam.py",
                "arch-rogue-python/tests/test_steam_integration.py",
                "arch-rogue-python/tools/bench_desktop.py",
            ):
                self.assertTrue(
                    (destination / relative).exists(),
                    f"missing from mirror: {relative}",
                )

    def test_private_and_generated_content_stays_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "master"
            destination = Path(tmpdir) / "public"
            self._build_fake_master(root)
            _ = self._run_mirror(root, destination, check=True)

            for relative in (
                "AGENTS.md",
                ".agents",
                ".claude",
                ".codex",
                ".github/dependabot.yml",
                ".github/workflows/private-ci.yml",
                "docs",
                "pyproject.toml",
                "buildozer.spec",
                "server",
                "stray_root_secret.txt",
                "tools/mirror_public_snapshot.sh",
                "tools/public-repo",
                "tools/set_public_android_secrets.sh",
                "arch-rogue-python/.github",
                "arch-rogue-python/website",
                "arch-rogue-python/docs/steam.md",
                "arch-rogue-python/docs/server-deployment.md",
                "arch-rogue-python/server/deploy",
                "arch-rogue-python/tools/steam",
                "arch-rogue-python/tools/build_steam_linux.sh",
                "arch-rogue-python/tools/build_steam_windows.sh",
                "arch-rogue-python/tools/deploy_deck.sh",
                "arch-rogue-python/tools/mirror_public_snapshot.sh",
                "arch-rogue-python/tools/public-repo",
                "arch-rogue-python/tools/set_public_android_secrets.sh",
                "assets/__pycache__",
                "assets/audio/sfx/licensed_01.wav",
                "arch-rogue-sfx-runtime-private.tar.gz",
                "src/.odin-cache",
                "tests/.pytest_cache",
                "tools/.ruff_cache",
                "android/app/build",
                "arch-rogue-python/.venv",
                "arch-rogue-python/build",
                "arch-rogue-python/dist",
                "arch-rogue-python/src/arch_rogue/__pycache__",
                "arch-rogue-python/tests/.mypy_cache",
            ):
                self.assertFalse(
                    (destination / relative).exists(),
                    f"leaked into mirror: {relative}",
                )
            public_gitignore = (destination / ".gitignore").read_text(encoding="utf-8")
            self.assertIn("/assets/audio/sfx/*.wav", public_gitignore)
            self.assertIn("/arch-rogue-sfx-runtime*.tar.gz", public_gitignore)


    def test_validate_only_rejects_injected_licensed_sfx(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "master"
            destination = Path(tmpdir) / "public"
            self._build_fake_master(root)
            _ = self._run_mirror(root, destination, check=True)

            _write(destination, "assets/audio/sfx/injected.wav", "licensed bytes\n")
            result = self._run_mirror(root, destination, validate_only=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("licensed runtime SFX WAV present", result.stderr)

            (destination / "assets/audio/sfx/injected.wav").unlink()
            _write(destination, "assets/arch-rogue-sfx-runtime-leak.tar.gz", "private bundle\n")
            result = self._run_mirror(root, destination, validate_only=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("private runtime SFX bundle present", result.stderr)


    def test_root_workflow_overlay_and_stale_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "master"
            destination = Path(tmpdir) / "public"
            self._build_fake_master(root)

            _write(destination, ".git/HEAD", "protected git metadata\n")
            _write(destination, ".github/dependabot.yml", "stale\n")
            _write(destination, ".github/workflows/stale-release.yml", "stale\n")
            _write(destination, "src/removed_from_master.odin", "stale\n")
            _write(destination, "arch-rogue-python/.github/workflows/stale.yml")
            _write(destination, "leftover_from_last_snapshot.txt", "stale\n")

            _ = self._run_mirror(root, destination, check=True)

            workflow = destination / ".github/workflows/build-release.yml"
            self.assertEqual(workflow.read_text(encoding="utf-8"), PUBLIC_WORKFLOW)
            self.assertEqual(
                [path.name for path in (destination / ".github/workflows").iterdir()],
                ["build-release.yml"],
            )
            self.assertEqual(
                [path.name for path in (destination / ".github").iterdir()],
                ["workflows"],
            )
            self.assertTrue((destination / ".git/HEAD").exists())

            for relative in (
                ".github/dependabot.yml",
                ".github/workflows/stale-release.yml",
                "src/removed_from_master.odin",
                "arch-rogue-python/.github",
                "leftover_from_last_snapshot.txt",
            ):
                self.assertFalse(
                    (destination / relative).exists(),
                    f"stale path survived snapshot replacement: {relative}",
                )

    def test_assembly_rejects_destinations_overlapping_source_tree(self) -> None:
        for relationship in ("same", "inside", "ancestor"):
            with self.subTest(relationship=relationship), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir) / "master"
                self._build_fake_master(root)
                if relationship == "same":
                    destination = root
                elif relationship == "inside":
                    destination = root / "nested" / "public"
                else:
                    destination = root.parent

                result = self._run_mirror(root, destination)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("unsafe destination overlaps repository root", result.stderr)
                self.assertTrue((root / "src/main.odin").is_file())
                self.assertTrue((root / "tools/mirror_public_snapshot.sh").is_file())

    def test_required_odin_snapshot_files_are_validated(self) -> None:
        required = (
            "build.sh",
            "toolchain.properties",
            "src/main.odin",
            "src/app.odin",
            "tests/core_test.odin",
            "android/release-signing-cert.sha256",
            "vendor/raylib/raylib.odin",
        )
        for relative in required:
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir) / "master"
                destination = Path(tmpdir) / "public"
                self._build_fake_master(root)
                (root / relative).unlink()

                result = self._run_mirror(root, destination)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(
                    f"missing required Odin snapshot file: {relative}",
                    result.stderr,
                )

    def test_validate_only_rejects_forbidden_paths(self) -> None:
        forbidden = (
            "AGENTS.md",
            "STEAM.md",
            ".agents/private.txt",
            "tools/mirror_public_snapshot.sh",
            "tools/steam/app_build.vdf",
            "arch-rogue-python/.github/workflows/release.yml",
            "arch-rogue-python/nested/.github/workflows/release.yml",
            "arch-rogue-python/nested/tools/public-repo/workflows/release.yml",
        )
        for relative in forbidden:
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir) / "master"
                destination = Path(tmpdir) / "public"
                self._build_fake_master(root)
                _ = self._run_mirror(root, destination, check=True)
                _write(destination, relative, "injected leak\n")

                result = self._run_mirror(
                    root, destination, validate_only=True
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("mirror validation failed", result.stderr)

    def test_validate_only_rejects_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "master"
            destination = Path(tmpdir) / "public"
            self._build_fake_master(root)
            _ = self._run_mirror(root, destination, check=True)

            link = destination / "assets/player-link.png"
            try:
                link.symlink_to("actors/player.png")
            except OSError as error:
                self.skipTest(f"symlinks are unavailable: {error}")

            result = self._run_mirror(root, destination, validate_only=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("symlink present in snapshot", result.stderr)

    def test_validate_only_rejects_files_at_95_mib_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "master"
            destination = Path(tmpdir) / "public"
            self._build_fake_master(root)
            _ = self._run_mirror(root, destination, check=True)

            candidate = destination / "assets/boundary.bin"
            with candidate.open("wb") as file:
                _ = file.truncate(MAX_PUBLIC_FILE_BYTES - 1)
            _ = self._run_mirror(
                root, destination, validate_only=True, check=True
            )

            with candidate.open("r+b") as file:
                _ = file.truncate(MAX_PUBLIC_FILE_BYTES)
            result = self._run_mirror(root, destination, validate_only=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("file is 95 MiB or larger", result.stderr)

    def test_validate_only_rejects_workflow_overlay_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "master"
            destination = Path(tmpdir) / "public"
            self._build_fake_master(root)
            _ = self._run_mirror(root, destination, check=True)
            _write(
                destination,
                ".github/workflows/build-release.yml",
                ARCHIVED_WORKFLOW,
            )

            result = self._run_mirror(root, destination, validate_only=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "public workflow overlay differs from root tools/public-repo/workflows",
                result.stderr,
            )


if __name__ == "__main__":
    _ = unittest.main()
