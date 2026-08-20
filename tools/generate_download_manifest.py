#!/usr/bin/env python3
"""Create the commit-addressed download manifest used by GitHub Pages."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

PLATFORM_ARTIFACT_FILENAMES: dict[str, str | None] = {
    "windows": None,
    "linux": "{base}-linux-x64.tar.gz",
    "macos": None,
    "android": "Arch-Rogue.apk",
}
_REPOSITORY_RE = re.compile(
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9._-]+"
)
_VERSION_RE = re.compile(
    r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)
_COMMIT_RE = re.compile(r"[0-9a-fA-F]{12,40}")


def _validate_inputs(repository: str, version: str, commit: str) -> tuple[str, str, str]:
    if not isinstance(repository, str) or _REPOSITORY_RE.fullmatch(repository) is None:
        raise ValueError("repository must use a valid GitHub owner/name form")
    owner, name = repository.split("/", 1)
    if "--" in owner or len(name) > 100 or name in {".", ".."}:
        raise ValueError("repository must use a valid GitHub owner/name form")

    if not isinstance(version, str) or _VERSION_RE.fullmatch(version) is None:
        raise ValueError("version must be a SemVer value without a leading 'v'")
    prerelease = version.partition("-")[2]
    if prerelease and any(
        identifier.isdigit() and len(identifier) > 1 and identifier.startswith("0")
        for identifier in prerelease.split(".")
    ):
        raise ValueError("numeric prerelease identifiers must not contain leading zeroes")

    if not isinstance(commit, str) or _COMMIT_RE.fullmatch(commit) is None:
        raise ValueError("commit must be a 12-40 character hexadecimal Git SHA")
    return repository, version, commit[:12].lower()


def build_manifest(repository: str, version: str, commit: str) -> dict[str, object]:
    """Return schema-2 release metadata for one automated Odin build."""
    repository, version, short_commit = _validate_inputs(repository, version, commit)
    tag = f"v{version}-{short_commit}"
    release_base = f"https://github.com/{repository}/releases"
    asset_base = f"{release_base}/download/{tag}"
    filename_base = f"arch-rogue-v{version}-{short_commit}"

    assets: dict[str, dict[str, object]] = {}
    for platform, filename_template in PLATFORM_ARTIFACT_FILENAMES.items():
        entry: dict[str, object] = {"available": filename_template is not None}
        if filename_template is not None:
            filename = filename_template.format(base=filename_base)
            entry["url"] = f"{asset_base}/{filename}"
        assets[platform] = entry

    return {
        "schema": 2,
        "version": version,
        "commit": short_commit,
        "release_url": f"{release_base}/tag/{tag}",
        "assets": assets,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, help="GitHub owner/name")
    parser.add_argument("--version", required=True, help="SemVer without a leading v")
    parser.add_argument("--commit", required=True, help="12-40 character release commit SHA")
    parser.add_argument("--output", type=Path, default=Path("website/downloads.json"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = build_manifest(args.repository, args.version, args.commit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output} for Arch Rogue v{manifest['version']} ({manifest['commit']})")


if __name__ == "__main__":
    main()
