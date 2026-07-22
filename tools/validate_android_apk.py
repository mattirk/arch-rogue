#!/usr/bin/env python3
"""Validate Arch Rogue's Android source contract and generated APK payload."""

from __future__ import annotations

import argparse
import ast
import configparser
import io
import struct
import sys
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable


ELF_MACHINE_BY_ABI = {
    "armeabi-v7a": 40,  # EM_ARM
    "arm64-v8a": 183,  # EM_AARCH64
    "x86": 3,  # EM_386
    "x86_64": 62,  # EM_X86_64
}
ELF_MACHINE_NAMES = {
    3: "EM_386",
    40: "EM_ARM",
    62: "EM_X86_64",
    183: "EM_AARCH64",
}
DEFAULT_REQUIRED_PACKAGES = ("pygame", "jnius")
REQUIRED_NATIVE_MODULES = {
    "pygame.base": "/site-packages/pygame/base",
    "pygame.system": "/site-packages/pygame/system",
    "jnius.jnius": "/site-packages/jnius/jnius",
}
NATIVE_SOURCE_SUFFIXES = (".so", ".pyd", ".dll", ".dylib")
# 4.3.17 WS-G: GPL-family MP3 codec markers that must never appear in a
# bundled .so. The procedural audio path needs at most libogg/vorbis; an
# accidental libmad/libmp3lame/libfaad pull-in via SDL2_mixer would create a
# GPL-2.0 contamination issue that Apache-2.0 alone cannot resolve (Apache-2.0
# is GPLv3-compatible but not GPLv2-compatible without an explicit "or later"
# clause). `libmad`/`libmp3lame`/`libfaad` catch the SONAMEs; `mp3lame`/
# `mad_decoder`/`NeAACDec` catch the well-known internal symbols.
GPL_CODEC_MARKERS: tuple[bytes, ...] = (
    b"libmad",
    b"libmp3lame",
    b"libfaad",
    b"mp3lame",
    b"mad_decoder",
    b"NeAACDec",
)
# (L)GPL build tools whose source must never be packaged into the APK.
BUILD_TOOL_SOURCE_DIRS: tuple[str, ...] = ("buildozer", "pythonforandroid")


class ValidationError(RuntimeError):
    """Raised when an Android source tree, spec, or APK is unsafe to ship."""


@dataclass(frozen=True)
class ApkValidationReport:
    apk: Path
    abis: tuple[str, ...]
    native_extensions: dict[str, int]
    entrypoint: str


def _normalise_tar_name(name: str) -> str:
    return str(PurePosixPath(name.lstrip("./")))


def _elf_machine(header: bytes) -> int | None:
    """Return an ELF e_machine value, or None when *header* is not ELF."""

    if len(header) < 20 or header[:4] != b"\x7fELF":
        return None
    if header[5] == 1:
        endian = "<"
    elif header[5] == 2:
        endian = ">"
    else:
        raise ValidationError("ELF file has an invalid EI_DATA byte")
    return struct.unpack_from(f"{endian}H", header, 18)[0]


def _machine_name(machine: int) -> str:
    return ELF_MACHINE_NAMES.get(machine, f"e_machine={machine}")


def _assert_no_gpl_codec_marker(label: str, payload: bytes) -> None:
    for marker in GPL_CODEC_MARKERS:
        if marker in payload:
            raise ValidationError(
                f"{label} contains GPL-family codec marker "
                f"{marker.decode('ascii', 'replace')!r}; "
                "copyleft MP3 decoder must not ship in the APK"
            )


def _assert_machine(name: str, header: bytes, abi: str) -> bool:
    machine = _elf_machine(header)
    if machine is None:
        return False
    expected = ELF_MACHINE_BY_ABI[abi]
    if machine != expected:
        raise ValidationError(
            f"{name} is {_machine_name(machine)}, but {abi} requires "
            f"{_machine_name(expected)}"
        )
    return True


def _tar_bytes(entries: dict[str, bytes]) -> bytes:
    """Small helper used by tests and kept private to this module."""

    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for name, payload in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    return output.getvalue()


def validate_source_tree(source_dir: Path) -> None:
    """Validate the SDL2 bootstrap entry point and reject host native files."""

    source_dir = source_dir.resolve()
    main_path = source_dir / "main.py"
    game_path = source_dir / "arch_rogue" / "game.py"
    if not main_path.is_file():
        raise ValidationError(
            f"missing {main_path}; python-for-android's SDL2 bootstrap requires "
            "a top-level main.py"
        )
    if not game_path.is_file():
        raise ValidationError(f"missing game module: {game_path}")

    try:
        tree = ast.parse(main_path.read_text(encoding="utf-8"), filename=str(main_path))
    except (OSError, SyntaxError) as error:
        raise ValidationError(f"invalid Android entry point {main_path}: {error}") from error

    game_import_index = next(
        (
            index
            for index, node in enumerate(tree.body)
            if isinstance(node, ast.ImportFrom)
            and node.module == "arch_rogue.game"
            and any(alias.name == "main" for alias in node.names)
        ),
        None,
    )
    alpha_setup_index = next(
        (
            index
            for index, node in enumerate(tree.body)
            if isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "setdefault"
            and isinstance(node.value.func.value, ast.Attribute)
            and node.value.func.value.attr == "environ"
            and isinstance(node.value.func.value.value, ast.Name)
            and node.value.func.value.value.id == "os"
            and len(node.value.args) >= 2
            and isinstance(node.value.args[0], ast.Constant)
            and node.value.args[0].value == "PYGAME_BLEND_ALPHA_SDL2"
            and isinstance(node.value.args[1], ast.Constant)
            and node.value.args[1].value == "1"
        ),
        None,
    )
    if (
        alpha_setup_index is None
        or game_import_index is None
        or alpha_setup_index >= game_import_index
    ):
        raise ValidationError(
            f"{main_path} must set PYGAME_BLEND_ALPHA_SDL2=1 before importing "
            "arch_rogue.game so pygame caches the Android ARM blitter choice"
        )

    guarded_call = False
    for node in tree.body:
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
            continue
        left = node.test.left
        comparators = node.test.comparators
        is_main_guard = (
            isinstance(left, ast.Name)
            and left.id == "__name__"
            and len(comparators) == 1
            and isinstance(comparators[0], ast.Constant)
            and comparators[0].value == "__main__"
        )
        calls_main = any(
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == "main"
            for statement in node.body
            for child in ast.walk(statement)
        )
        guarded_call = guarded_call or (is_main_guard and calls_main)

    if game_import_index is None or not guarded_call:
        raise ValidationError(
            f"{main_path} must import arch_rogue.game.main and call it under "
            "an __name__ == '__main__' guard"
        )

    native_files = sorted(
        path
        for path in source_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in NATIVE_SOURCE_SUFFIXES
    )
    if native_files:
        rendered = ", ".join(str(path.relative_to(source_dir)) for path in native_files)
        raise ValidationError(f"source tree contains host native binaries: {rendered}")

    # 4.3.17 WS-G: the Apache-2.0 license text and third-party NOTICE must be
    # bundled as reachable assets so APK installers get §4 attribution. Fail
    # the preflight if either asset is missing from the source tree.
    licenses_dir = source_dir / "arch_rogue" / "assets" / "licenses"
    for asset_name in ("LICENSE.txt", "NOTICE.txt", "LGPL-2.1.txt"):
        if not (licenses_dir / asset_name).is_file():
            raise ValidationError(
                f"missing bundled license asset {licenses_dir / asset_name}; "
                "run tools/build_android.sh to refresh assets/licenses/*.txt "
                "from the repository-root LICENSE and NOTICE"
            )


def validate_build_spec(spec_path: Path, project_root: Path | None = None) -> tuple[str, ...]:
    """Validate settings that prevent host wheels and stale p4a builds."""

    spec_path = spec_path.resolve()
    root = (project_root or spec_path.parent).resolve()
    parser = configparser.ConfigParser(interpolation=None)
    try:
        with spec_path.open(encoding="utf-8") as source:
            parser.read_file(source)
        app = parser["app"]
    except (OSError, KeyError, configparser.Error) as error:
        raise ValidationError(f"cannot read Android spec {spec_path}: {error}") from error

    requirements = tuple(
        requirement.strip() for requirement in app.get("requirements", "").split(",")
        if requirement.strip()
    )
    if any(requirement.lower().startswith("pygame-ce") for requirement in requirements):
        raise ValidationError(
            "buildozer requirements must use the local 'pygame' recipe, not "
            "recipe-less 'pygame-ce' (which installs a host manylinux wheel)"
        )
    if "pygame==2.5.7" not in requirements:
        raise ValidationError("buildozer requirements must pin pygame==2.5.7")
    if "pyjnius" not in requirements:
        raise ValidationError("buildozer requirements must include pyjnius for safe insets")

    local_recipes = app.get("p4a.local_recipes", "").strip()
    recipe_path = root / local_recipes / "pygame" / "__init__.py"
    if not local_recipes or not recipe_path.is_file():
        raise ValidationError(f"pygame local recipe is missing: {recipe_path}")

    if "android.arch" in app and "android.archs" not in app:
        raise ValidationError("use supported buildozer key android.archs, not android.arch")
    abis = tuple(
        abi.strip() for abi in app.get("android.archs", "").split(",") if abi.strip()
    )
    if not abis:
        raise ValidationError("buildozer spec does not define android.archs")
    unknown = sorted(set(abis) - ELF_MACHINE_BY_ABI.keys())
    if unknown:
        raise ValidationError(f"unsupported Android ABI(s): {', '.join(unknown)}")

    if "android.permissions" in app and not app.get("android.permissions", "").strip():
        raise ValidationError(
            "omit android.permissions when no permissions are needed; a blank value "
            "produces the invalid manifest permission android.permission."
        )

    excluded_source_dirs = {
        value.strip().lower()
        for value in app.get("source.exclude_dirs", "").split(",")
        if value.strip()
    }
    required_exclusions = {"__pycache__", "arch_rogue.egg-info"}
    missing_exclusions = sorted(required_exclusions - excluded_source_dirs)
    if missing_exclusions:
        raise ValidationError(
            "buildozer source.exclude_dirs must reject generated source metadata: "
            + ", ".join(missing_exclusions)
        )

    # 4.3.17 WS-G: the license/notice .txt assets must be bundled, so
    # source.include_exts has to keep .txt files.
    include_exts = {
        value.strip().lower().lstrip(".")
        for value in app.get("source.include_exts", "").split(",")
        if value.strip()
    }
    if "txt" not in include_exts:
        raise ValidationError(
            "buildozer source.include_exts must include 'txt' so the bundled "
            "LICENSE.txt / NOTICE.txt reach the APK's About screen"
        )

    if app.get("p4a.bootstrap", "").strip() != "sdl2":
        raise ValidationError("Arch Rogue Android builds require p4a.bootstrap = sdl2")

    release_artifact = app.get("android.release_artifact", "").strip()
    if release_artifact != "apk":
        raise ValidationError(
            "android.release_artifact must be 'apk'; other values are passed "
            "directly to python-for-android and do not produce the public APK"
        )

    commit = app.get("p4a.commit", "").strip().lower()
    if not commit or commit in {"master", "develop"}:
        raise ValidationError("p4a.commit must pin an immutable release commit")

    # 4.4.8: the APK loading screen must show the branded Arch Rogue title logo
    # instead of python-for-android's default SDL splash. The presplash image is
    # resolved relative to the project root (same convention as icon.filename).
    presplash = app.get("presplash.filename", "").strip()
    if not presplash:
        raise ValidationError(
            "buildozer presplash.filename must point at the Arch Rogue title "
            "logo so the APK loading screen is branded, not the default splash"
        )
    presplash_path = root / presplash
    if not presplash_path.is_file():
        raise ValidationError(
            f"buildozer presplash.filename asset is missing: {presplash_path}"
        )
    return abis


def _validate_private_bundle(payload: bytes) -> str:
    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
            members = {
                _normalise_tar_name(member.name): member
                for member in archive.getmembers()
                if member.isfile()
            }
            generated_metadata = sorted(
                name
                for name in members
                if any(
                    part == "__pycache__" or part.endswith(".egg-info")
                    for part in PurePosixPath(name).parts
                )
            )
            if generated_metadata:
                raise ValidationError(
                    "assets/private.tar contains generated source metadata: "
                    + ", ".join(generated_metadata)
                )

            # 4.3.17 WS-G: buildozer/python-for-android are (L)GPL build tools;
            # their source must never ship inside the APK.
            build_tool_source = sorted(
                name
                for name in members
                if any(
                    part in BUILD_TOOL_SOURCE_DIRS
                    for part in PurePosixPath(name).parts
                )
            )
            if build_tool_source:
                raise ValidationError(
                    "assets/private.tar contains (L)GPL build-tool source: "
                    + ", ".join(build_tool_source)
                )

            required_license_assets = (
                "arch_rogue/assets/licenses/LICENSE.txt",
                "arch_rogue/assets/licenses/NOTICE.txt",
                "arch_rogue/assets/licenses/LGPL-2.1.txt",
            )
            missing_license_assets = [
                name for name in required_license_assets if name not in members
            ]
            if missing_license_assets:
                raise ValidationError(
                    "assets/private.tar is missing in-app license assets: "
                    + ", ".join(missing_license_assets)
                )

            entrypoint = next(
                (name for name in ("main.py", "main.pyc") if name in members),
                None,
            )
            if entrypoint is None:
                raise ValidationError(
                    "assets/private.tar has no root main.py/main.pyc entry point"
                )
            game_module = next(
                (
                    name
                    for name in ("arch_rogue/game.py", "arch_rogue/game.pyc")
                    if name in members
                ),
                None,
            )
            if game_module is None:
                raise ValidationError("assets/private.tar is missing arch_rogue/game.py[c]")
            stream = archive.extractfile(members[entrypoint])
            entry_data = stream.read() if stream is not None else b""
            if b"arch_rogue.game" not in entry_data or b"main" not in entry_data:
                raise ValidationError(
                    f"{entrypoint} does not reference arch_rogue.game.main"
                )
            if b"PYGAME_BLEND_ALPHA_SDL2" not in entry_data:
                raise ValidationError(
                    f"{entrypoint} does not enable the Android SDL2 alpha blitter"
                )
            return entrypoint
    except (OSError, tarfile.TarError) as error:
        raise ValidationError(f"invalid assets/private.tar: {error}") from error


def _validate_python_bundle(
    payload: bytes,
    abi: str,
    required_packages: Iterable[str],
) -> int:
    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
            members = [member for member in archive.getmembers() if member.isfile()]
            names = [_normalise_tar_name(member.name) for member in members]
            has_desktop_wheel_libraries = any(
                "/pygame_ce.libs/" in f"/{name}" for name in names
            )

            for package in required_packages:
                marker = f"/site-packages/{package}/"
                if not any(marker in f"/{name}" for name in names):
                    raise ValidationError(
                        f"{abi} Python bundle is missing required package {package}"
                    )

            for module, marker in REQUIRED_NATIVE_MODULES.items():
                if not any(
                    marker in f"/{name}" and name.endswith(".so") for name in names
                ):
                    raise ValidationError(
                        f"{abi} Python bundle is missing native module {module}"
                    )

            native_count = 0
            for member, name in zip(members, names, strict=True):
                if not name.endswith(".so"):
                    continue
                stream = archive.extractfile(member)
                payload = stream.read() if stream is not None else b""
                label = f"{abi}:{name}"
                if not _assert_machine(label, payload[:20], abi):
                    raise ValidationError(f"{label} has a .so suffix but is not ELF")
                # libpybundle.so is a compressed tar archive, so scanning its
                # raw APK bytes cannot see strings in nested extensions. Scan
                # every decompressed native module while it is already open.
                _assert_no_gpl_codec_marker(label, payload)
                native_count += 1
            if native_count == 0:
                raise ValidationError(f"{abi} Python bundle has no native extensions")
            if has_desktop_wheel_libraries:
                raise ValidationError(
                    f"{abi} Python bundle contains pygame_ce.libs from a desktop wheel"
                )
            return native_count
    except (OSError, tarfile.TarError) as error:
        raise ValidationError(f"invalid {abi} libpybundle.so: {error}") from error


def _scan_native_libraries_for_gpl_codecs(
    apk: zipfile.ZipFile,
    names: list[str],
    expected_abis: tuple[str, ...],
) -> None:
    """Reject bundled .so files containing GPL-family MP3 codec markers.

    4.3.17 WS-G: the procedural audio path needs at most libogg/vorbis. An
    accidental libmad/libmp3lame/libfaad pull-in via SDL2_mixer would create a
    GPL-2.0 contamination issue that Apache-2.0 alone cannot resolve. Scan the
    standalone ``lib/<abi>/*.so`` files (where SDL2_mixer and a separate
    libmad.so would live) and the .so entries inside each ``libpybundle.so``.
    """

    for abi in expected_abis:
        prefix = f"lib/{abi}/"
        for name in names:
            if not name.startswith(prefix) or not name.endswith(".so"):
                continue
            _assert_no_gpl_codec_marker(name, apk.read(name))


def validate_apk(
    apk_path: Path,
    expected_abis: Iterable[str],
    required_packages: Iterable[str] = DEFAULT_REQUIRED_PACKAGES,
) -> ApkValidationReport:
    """Validate entry point, package presence, and all nested ELF architectures."""

    apk_path = apk_path.resolve()
    expected = tuple(expected_abis)
    if not expected:
        raise ValidationError("at least one expected ABI is required")
    try:
        with zipfile.ZipFile(apk_path) as apk:
            names = apk.namelist()
            found_abis = tuple(
                sorted(
                    {
                        parts[1]
                        for name in names
                        if len(parts := PurePosixPath(name).parts) >= 3
                        and parts[0] == "lib"
                    }
                )
            )
            if set(found_abis) != set(expected):
                raise ValidationError(
                    f"APK ABIs are {found_abis}, expected {tuple(sorted(expected))}"
                )

            try:
                private_payload = apk.read("assets/private.tar")
            except KeyError as error:
                raise ValidationError("APK is missing assets/private.tar") from error
            entrypoint = _validate_private_bundle(private_payload)

            native_counts: dict[str, int] = {}
            for abi in expected:
                prefix = f"lib/{abi}/"
                abi_libraries = [
                    name for name in names if name.startswith(prefix) and name.endswith(".so")
                ]
                if not abi_libraries:
                    raise ValidationError(f"APK has no native libraries for {abi}")
                bundle_name = f"{prefix}libpybundle.so"
                if bundle_name not in names:
                    raise ValidationError(f"APK is missing {bundle_name}")

                for name in abi_libraries:
                    if name == bundle_name:
                        continue
                    header = apk.read(name)[:20]
                    if not _assert_machine(name, header, abi):
                        raise ValidationError(f"{name} has a .so suffix but is not ELF")
                native_counts[abi] = _validate_python_bundle(
                    apk.read(bundle_name), abi, required_packages
                )
            # 4.3.17 WS-G: reject copyleft MP3 codec contamination across
            # every bundled native library.
            _scan_native_libraries_for_gpl_codecs(apk, names, expected)
    except (OSError, zipfile.BadZipFile) as error:
        raise ValidationError(f"cannot read APK {apk_path}: {error}") from error

    return ApkValidationReport(apk_path, tuple(sorted(expected)), native_counts, entrypoint)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", nargs="?", type=Path, help="APK to validate")
    parser.add_argument("--source-dir", type=Path, help="source.dir to preflight")
    parser.add_argument("--spec", type=Path, help="buildozer.spec to preflight")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--abis", nargs="+", help="expected APK ABIs (overrides spec)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.source_dir is None and args.spec is None and args.apk is None:
        raise ValidationError("provide --source-dir, --spec, and/or an APK")

    try:
        if args.source_dir is not None:
            validate_source_tree(args.source_dir)
            print(f"Android source entry point: OK ({args.source_dir / 'main.py'})")
        spec_abis: tuple[str, ...] = ()
        if args.spec is not None:
            spec_abis = validate_build_spec(args.spec, args.project_root)
            print(f"Android build spec: OK ({', '.join(spec_abis)})")
        if args.apk is not None:
            abis = tuple(args.abis or spec_abis)
            report = validate_apk(args.apk, abis)
            counts = ", ".join(
                f"{abi}={report.native_extensions[abi]} ELF extensions"
                for abi in report.abis
            )
            print(
                f"Android APK: OK ({report.apk}; entry={report.entrypoint}; {counts})"
            )
    except ValidationError as error:
        print(f"Android validation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
