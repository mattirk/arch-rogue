#!/usr/bin/env python3
"""Create, inject, or verify Arch Rogue's licensed runtime SFX bundle.

The public source snapshot keeps assets/audio/sfx/manifest.json but excludes the
purchased WAV derivatives. The manifest is the exact filename, size, and SHA-256
lock used by this tool for local development and authorized release CI.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ASSET_DIR = ROOT / "assets" / "audio" / "sfx"
DEFAULT_MANIFEST = DEFAULT_ASSET_DIR / "manifest.json"
ARCHIVE_ROOT = "arch-rogue-sfx"
CHUNK = 1024 * 1024


class BundleError(RuntimeError):
    pass


def load_contract(manifest_path: Path) -> dict[str, dict[str, Any]]:
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BundleError(f"cannot read SFX manifest {manifest_path}: {error}") from error
    if document.get("format_version") != 2 or not isinstance(document.get("banks"), dict):
        raise BundleError(f"unsupported SFX manifest: {manifest_path}")

    files: dict[str, dict[str, Any]] = {}
    for bank, metadata in document["banks"].items():
        entries = metadata.get("files") if isinstance(metadata, dict) else None
        if not isinstance(entries, list):
            raise BundleError(f"invalid SFX bank metadata: {bank}")
        for entry in entries:
            name = entry.get("file") if isinstance(entry, dict) else None
            digest = entry.get("sha256") if isinstance(entry, dict) else None
            size = entry.get("byte_size") if isinstance(entry, dict) else None
            if (
                not isinstance(name, str)
                or PurePosixPath(name).name != name
                or not name.endswith(".wav")
                or not isinstance(digest, str)
                or len(digest) != 64
                or not isinstance(size, int)
                or size <= 44
            ):
                raise BundleError(f"invalid SFX file contract in bank {bank}: {entry!r}")
            if name in files:
                raise BundleError(f"duplicate SFX filename in manifest: {name}")
            files[name] = entry
    if document.get("file_count") != len(files):
        raise BundleError(
            f"manifest file_count is {document.get('file_count')}, enumerated {len(files)}"
        )
    return files


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(CHUNK):
            digest.update(block)
    return digest.hexdigest()


def verify_file(path: Path, name: str, entry: dict[str, Any]) -> None:
    if not path.is_file() or path.is_symlink():
        raise BundleError(f"missing licensed SFX file: {name}")
    size = path.stat().st_size
    if size != entry["byte_size"]:
        raise BundleError(f"SFX size mismatch for {name}: expected {entry['byte_size']}, got {size}")
    digest = file_sha256(path)
    if digest != entry["sha256"]:
        raise BundleError(
            f"SFX checksum mismatch for {name}: expected {entry['sha256']}, got {digest}"
        )


def verify_directory(asset_dir: Path, files: dict[str, dict[str, Any]]) -> None:
    existing = {path.name for path in asset_dir.glob("*.wav") if path.is_file()}
    expected = set(files)
    missing = sorted(expected - existing)
    extra = sorted(existing - expected)
    if missing or extra:
        raise BundleError(
            f"runtime SFX set is not exact: missing={missing[:8]}"
            f"{'...' if len(missing) > 8 else ''}, extra={extra[:8]}"
            f"{'...' if len(extra) > 8 else ''}"
        )
    for name in sorted(files):
        verify_file(asset_dir / name, name, files[name])


def read_archive(bundle: Path, files: dict[str, dict[str, Any]]) -> dict[str, tarfile.TarInfo]:
    selected: dict[str, tarfile.TarInfo] = {}
    try:
        with tarfile.open(bundle, "r:gz") as archive:
            for member in archive.getmembers():
                raw = member.name
                parts = PurePosixPath(raw).parts
                if raw.startswith(("/", "./")) or "\\" in raw or any(part in {"", ".", ".."} for part in parts):
                    raise BundleError(f"unsafe SFX bundle path: {raw!r}")
                if member.isdir() and tuple(parts) == (ARCHIVE_ROOT,):
                    continue
                if not member.isfile() or len(parts) != 2 or parts[0] != ARCHIVE_ROOT:
                    raise BundleError(f"unexpected SFX bundle member: {raw}")
                name = parts[1]
                if name not in files:
                    raise BundleError(f"unmanaged file in SFX bundle: {name}")
                if name in selected:
                    raise BundleError(f"duplicate file in SFX bundle: {name}")
                if member.size != files[name]["byte_size"]:
                    raise BundleError(
                        f"SFX bundle size mismatch for {name}: expected {files[name]['byte_size']}, got {member.size}"
                    )
                selected[name] = member
    except (OSError, tarfile.TarError) as error:
        raise BundleError(f"cannot inspect SFX bundle {bundle}: {error}") from error
    missing = sorted(set(files) - set(selected))
    if missing:
        raise BundleError(f"SFX bundle is missing files: {missing[:8]}")
    return selected


def promote(staged: Path, asset_dir: Path, files: dict[str, dict[str, Any]]) -> None:
    for name in sorted(files):
        verify_file(staged / name, name, files[name])
    asset_dir.mkdir(parents=True, exist_ok=True)
    for old in asset_dir.glob("*.wav"):
        old.unlink()
    for name in sorted(files):
        os.replace(staged / name, asset_dir / name)
    verify_directory(asset_dir, files)


def inject_bundle(bundle: Path, asset_dir: Path, files: dict[str, dict[str, Any]]) -> None:
    selected = read_archive(bundle, files)
    asset_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".sfx-inject-", dir=asset_dir.parent) as temporary:
        staged = Path(temporary)
        with tarfile.open(bundle, "r:gz") as archive:
            for name in sorted(files):
                source = archive.extractfile(selected[name])
                if source is None:
                    raise BundleError(f"cannot read SFX bundle member: {name}")
                with source, (staged / name).open("xb") as output:
                    shutil.copyfileobj(source, output, CHUNK)
        promote(staged, asset_dir, files)


def inject_directory(source_dir: Path, asset_dir: Path, files: dict[str, dict[str, Any]]) -> None:
    verify_directory(source_dir, files)
    asset_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".sfx-inject-", dir=asset_dir.parent) as temporary:
        staged = Path(temporary)
        for name in sorted(files):
            shutil.copyfile(source_dir / name, staged / name)
        promote(staged, asset_dir, files)


def create_bundle(output: Path, asset_dir: Path, files: dict[str, dict[str, Any]]) -> None:
    verify_directory(asset_dir, files)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".sfx-bundle-", dir=output.parent) as temporary:
        tar_path = Path(temporary) / "bundle.tar"
        with tarfile.open(tar_path, "w", format=tarfile.PAX_FORMAT) as archive:
            root = tarfile.TarInfo(ARCHIVE_ROOT)
            root.type, root.mode, root.mtime = tarfile.DIRTYPE, 0o755, 0
            archive.addfile(root)
            for name in sorted(files):
                source = asset_dir / name
                info = tarfile.TarInfo(f"{ARCHIVE_ROOT}/{name}")
                info.size, info.mode, info.mtime = source.stat().st_size, 0o644, 0
                with source.open("rb") as data:
                    archive.addfile(info, data)
        staged_output = Path(temporary) / "bundle.tar.gz"
        with tar_path.open("rb") as source, staged_output.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
                shutil.copyfileobj(source, compressed, CHUNK)
        os.replace(staged_output, output)
    print(f"created {output} ({output.stat().st_size} bytes, sha256={file_sha256(output)})")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--asset-dir", type=Path, default=DEFAULT_ASSET_DIR)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("verify", help="verify the complete injected runtime set")
    create = commands.add_parser("create", help="create a deterministic private tar.gz bundle")
    create.add_argument("--output", type=Path, required=True)
    inject = commands.add_parser("inject", help="inject a verified private bundle or directory")
    source = inject.add_mutually_exclusive_group(required=True)
    source.add_argument("--bundle", type=Path)
    source.add_argument("--source-dir", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    files = load_contract(args.manifest.resolve())
    asset_dir = args.asset_dir.resolve()
    if args.command == "verify":
        verify_directory(asset_dir, files)
        print(f"verified {len(files)} licensed runtime SFX files")
    elif args.command == "create":
        create_bundle(args.output.resolve(), asset_dir, files)
    elif args.bundle is not None:
        inject_bundle(args.bundle.resolve(), asset_dir, files)
        print(f"injected {len(files)} licensed runtime SFX files from bundle")
    else:
        inject_directory(args.source_dir.resolve(), asset_dir, files)
        print(f"injected {len(files)} licensed runtime SFX files from directory")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BundleError as error:
        print(f"error: {error}", file=__import__("sys").stderr)
        raise SystemExit(1)
