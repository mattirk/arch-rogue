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

"""The public-mirror snapshot script must be allowlist-based (5.1):
anything new at the repo root stays private until deliberately admitted.

The real ``tools/mirror_public_snapshot.sh`` is copied into a synthetic
repo tree (it resolves its root from its own location) and executed, so
these tests exercise the exact rules the mirror workflow runs.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "tools" / "mirror_public_snapshot.sh"


def _touch(root: Path, relative: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x\n", encoding="utf-8")


@unittest.skipIf(shutil.which("rsync") is None, "rsync is not installed")
class PublicMirrorSnapshotTests(unittest.TestCase):
    def _build_fake_master(self, root: Path) -> None:
        for relative in (
            # Allowlisted content that must reach the mirror.
            "README.md",
            "CHANGELOG.md",
            "LICENSE",
            "NOTICE",
            ".gitignore",
            "pyproject.toml",
            "buildozer.spec",
            "src/arch_rogue/game.py",
            "tests/test_something.py",
            "docs/multiplayer.md",
            "server/server.py",
            "android/gradle.txt",
            "website/index.html",
            "tools/bench_desktop.py",
            "tools/public-repo/workflows/build-release.yml",
            # Private content that must never reach the mirror.
            "AGENTS.md",
            "docs/steam.md",
            "docs/server-deployment.md",
            "tools/steam/store_asset.bin",
            "tools/build_steam_linux.sh",
            "tools/build_steam_windows.sh",
            "tools/set_public_android_secrets.sh",
            ".github/workflows/private-deploy.yml",
            ".claude/settings.json",
            # The allowlist's whole point: new paths are private by default.
            "new_private_folder/notes.md",
            "stray_root_secret.txt",
            # Junk pruned inside allowed trees.
            "src/arch_rogue/__pycache__/game.cpython-314.pyc",
        ):
            _touch(root, relative)
        shutil.copy2(SCRIPT, root / "tools" / "mirror_public_snapshot.sh")

    def test_only_allowlisted_paths_reach_the_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "master"
            dest = Path(tmpdir) / "public"
            self._build_fake_master(root)
            # Stale mirror content (and a protected .git) from a prior run.
            _touch(dest, "leftover_from_last_snapshot.txt")
            _touch(dest, ".git/HEAD")
            subprocess.run(
                ["bash", str(root / "tools" / "mirror_public_snapshot.sh"), str(dest)],
                check=True,
                capture_output=True,
            )

            for relative in (
                "README.md",
                "CHANGELOG.md",
                ".gitignore",
                "src/arch_rogue/game.py",
                "tests/test_something.py",
                "docs/multiplayer.md",
                "server/server.py",
                "android/gradle.txt",
                "website/index.html",
                "tools/bench_desktop.py",
                ".github/workflows/build-release.yml",  # overlaid public CI
                ".git/HEAD",  # mirror clone metadata survives the sync
            ):
                self.assertTrue(
                    (dest / relative).exists(), f"missing from mirror: {relative}"
                )

            for relative in (
                "AGENTS.md",
                "docs/steam.md",
                "docs/server-deployment.md",
                "tools/steam",
                "tools/build_steam_linux.sh",
                "tools/build_steam_windows.sh",
                "tools/set_public_android_secrets.sh",
                "tools/mirror_public_snapshot.sh",
                "tools/public-repo",
                ".github/workflows/private-deploy.yml",
                ".claude",
                "new_private_folder",
                "stray_root_secret.txt",
                "src/arch_rogue/__pycache__",
                "leftover_from_last_snapshot.txt",
            ):
                self.assertFalse(
                    (dest / relative).exists(), f"leaked into mirror: {relative}"
                )


if __name__ == "__main__":
    unittest.main()
