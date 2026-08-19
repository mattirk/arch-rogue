from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


class FirstPassBenchmarkSmokeTests(unittest.TestCase):
    def test_quick_json_suite_runs(self) -> None:
        root = Path(__file__).resolve().parents[1]
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(root / "src")
        environment["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
        completed = subprocess.run(
            [
                sys.executable,
                str(root / "tools" / "benchmark_first_pass.py"),
                "--quick",
                "--depth",
                "1",
                "--width",
                "640",
                "--height",
                "360",
                "--skip-ui",
                "--skip-music",
                "--json-only",
            ],
            cwd=root,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
            timeout=60.0,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["scenario"]["enemy_counts"], [45, 90])
        # The benchmark runs the HD tier, whose fresh-session default sits on
        # the smallest world render bucket (4.9.24) — roughly the former two
        # notches in from the widest view, snapped for a zero-residual world
        # composite.
        self.assertAlmostEqual(result["scenario"]["default_zoom"], 0.8)
        for metric in (
            "game_update_45_enemies",
            "game_update_90_enemies",
            "render_crowd_default_zoom",
            "forced_save",
            "routine_kill",
        ):
            with self.subTest(metric=metric):
                summary = result["benchmarks"][metric]
                self.assertGreater(summary["samples"], 0)
                self.assertGreaterEqual(summary["p95_ms"], summary["p50_ms"])
        self.assertGreater(
            result["details"]["save_checkpoint"]["payload_bytes"],
            0,
        )


if __name__ == "__main__":
    unittest.main()
