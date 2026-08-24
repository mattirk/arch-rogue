# SPDX-License-Identifier: Apache-2.0
"""Regression tests for licensed SFX bundle creation and injection."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "tools" / "sfx_bundle.py"


class SfxBundleTests(unittest.TestCase):
    def _fixture(self, root: Path) -> tuple[Path, Path, dict[str, bytes]]:
        asset_dir = root / "assets" / "audio" / "sfx"
        asset_dir.mkdir(parents=True)
        payloads = {
            "alpha_01.wav": b"RIFF" + b"a" * 92,
            "beta_01.wav": b"RIFF" + b"b" * 124,
        }
        entries = []
        for name, payload in payloads.items():
            (asset_dir / name).write_bytes(payload)
            entries.append(
                {
                    "byte_size": len(payload),
                    "duration_ms": 1,
                    "file": name,
                    "frame_count": 1,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )
        manifest = {
            "format_version": 2,
            "file_count": len(entries),
            "banks": {
                "fixture": {
                    "files": entries,
                }
            },
        }
        manifest_path = asset_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return asset_dir, manifest_path, payloads

    def _run(
        self,
        asset_dir: Path,
        manifest: Path,
        *arguments: str,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--manifest",
                str(manifest),
                "--asset-dir",
                str(asset_dir),
                *arguments,
            ],
            check=check,
            capture_output=True,
            text=True,
        )

    def test_bundle_is_deterministic_and_round_trips_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            asset_dir, manifest, payloads = self._fixture(root)
            first = root / "first.tar.gz"
            second = root / "second.tar.gz"

            self._run(asset_dir, manifest, "verify")
            self._run(asset_dir, manifest, "create", "--output", str(first))
            self._run(asset_dir, manifest, "create", "--output", str(second))
            self.assertEqual(first.read_bytes(), second.read_bytes())

            for path in asset_dir.glob("*.wav"):
                path.unlink()
            self._run(asset_dir, manifest, "inject", "--bundle", str(first))
            self.assertEqual(
                {path.name: path.read_bytes() for path in asset_dir.glob("*.wav")},
                payloads,
            )

    def test_verify_rejects_partial_and_corrupt_sets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            asset_dir, manifest, _ = self._fixture(Path(tmpdir))
            (asset_dir / "alpha_01.wav").unlink()
            result = self._run(asset_dir, manifest, "verify", check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("runtime SFX set is not exact", result.stderr)

            (asset_dir / "alpha_01.wav").write_bytes(b"RIFF" + b"x" * 92)
            result = self._run(asset_dir, manifest, "verify", check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("checksum mismatch", result.stderr)


if __name__ == "__main__":
    unittest.main()
