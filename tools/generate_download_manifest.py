#!/usr/bin/env python3
"""Create the immutable download manifest consumed by the GitHub Pages site."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

PLATFORM_SUFFIXES = {
    "windows": "windows-x64.exe",
    "linux": "linux-x64",
    "macos": "macos-universal.zip",
    "android": "android-release.apk",
}


def build_manifest(repository: str, version: str, commit: str) -> dict[str, object]:
    """Return release metadata and direct links for one automated build."""
    if repository.count("/") != 1 or any(part.strip() != part or not part for part in repository.split("/")):
        raise ValueError("repository must use the owner/name form")
    if not version or not commit:
        raise ValueError("version and commit must not be empty")

    short_commit = commit[:7]
    tag = f"v{version}-{short_commit}"
    release_base = f"https://github.com/{repository}/releases"
    asset_base = f"{release_base}/download/{tag}"
    filename_base = f"arch-rogue-v{version}-{short_commit}"
    return {
        "schema": 1,
        "version": version,
        "commit": short_commit,
        "release_url": f"{release_base}/tag/{tag}",
        "assets": {
            platform: f"{asset_base}/{filename_base}-{suffix}"
            for platform, suffix in PLATFORM_SUFFIXES.items()
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, help="GitHub owner/name")
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit", required=True, help="Full or short release commit SHA")
    parser.add_argument("--output", type=Path, default=Path("website/downloads.json"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = build_manifest(args.repository, args.version, args.commit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output} for Arch Rogue v{args.version} ({args.commit[:7]})")


if __name__ == "__main__":
    main()
