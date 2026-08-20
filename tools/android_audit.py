#!/usr/bin/env python3
"""Strict, stdlib-only audits for Arch Rogue Odin Android inputs and artifacts."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Iterable
from pathlib import Path, PurePosixPath


EXPECTED_ABIS = ("arm64-v8a", "armeabi-v7a", "x86_64")
EXPECTED_MIN_SDK = 28
EXPECTED_COMPILE_SDK = 35
EXPECTED_TARGET_SDK = 35
EXPECTED_NEEDED = {
    "libandroid.so",
    "liblog.so",
    "libEGL.so",
    "libGLESv2.so",
    "libOpenSLES.so",
    "libdl.so",
    "libm.so",
    "libc.so",
}
EXPECTED_RAYLIB_MEMBERS = (
    "raudio.c.o",
    "rcore.c.o",
    "rmodels.c.o",
    "rshapes.c.o",
    "rtext.c.o",
    "rtextures.c.o",
)
FORBIDDEN_BINARY_MARKERS = (
    b"libX11",
    b"libXcursor",
    b"libXrandr",
    b"libXi.so",
    b"XOpenDisplay",
    b"glX",
    b"GLFW",
    b"libGL.so",
    b"libc.so.6",
    b"libstdc++.so",
    b"libgcc_s.so",
    b"ld-linux",
    b"GLIBC_",
    b"GLIBCXX_",
    b"libpthread",
)
FORBIDDEN_NETWORK_PERMISSIONS = {
    "android.permission.INTERNET",
    "android.permission.ACCESS_NETWORK_STATE",
    "android.permission.CHANGE_NETWORK_STATE",
    "android.permission.ACCESS_WIFI_STATE",
    "android.permission.CHANGE_WIFI_STATE",
    "android.permission.NEARBY_WIFI_DEVICES",
}
MACHINE_BY_ABI = {
    "arm64-v8a": "AArch64",
    "armeabi-v7a": "ARM",
    "x86_64": "Advanced Micro Devices X86-64",
}
ELF_CLASS_BY_ABI = {
    "arm64-v8a": "ELF64",
    "armeabi-v7a": "ELF32",
    "x86_64": "ELF64",
}


class AuditError(RuntimeError):
    """Expected contract failure without a Python traceback."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditError(message)


def run_checked(command: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if result.returncode != 0:
        joined = " ".join(command)
        raise AuditError(f"command failed ({result.returncode}): {joined}\n{result.stdout}")
    return result.stdout


def absolute_tool_path(value: str) -> Path:
    # Do not Path.resolve() NDK multicall symlinks: llvm-readelf resolves to
    # llvm-readobj and changes its output grammar based on argv[0].
    return Path(os.path.abspath(value))


def executable_sibling(readelf: Path, name: str) -> Path:
    tool = readelf.with_name(name)
    require(tool.is_file() and os.access(tool, os.X_OK), f"missing NDK tool: {tool}")
    return tool


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_zip_entry(archive: zipfile.ZipFile, name: str) -> str:
    digest = hashlib.sha256()
    with archive.open(name) as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_forbidden_markers(data: bytes, description: str) -> None:
    for marker in FORBIDDEN_BINARY_MARKERS:
        require(marker not in data, f"forbidden host marker {marker!r} found in {description}")


def load_properties(path: Path) -> dict[str, str]:
    require(path.is_file(), f"missing properties file: {path}")
    properties: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        require(bool(separator), f"invalid properties line in {path}: {raw_line!r}")
        key = key.strip()
        require(bool(key), f"empty property key in {path}")
        require(key not in properties, f"duplicate property {key!r} in {path}")
        properties[key] = value.strip()
    return properties


def mapped_version_code(version_name: str) -> int:
    version_pattern = (
        r"(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)" +
        r"(?:-(?P<label>alpha|beta|rc)\.(?P<number>\d+))?"
    )
    match = re.fullmatch(version_pattern, version_name)
    require(match is not None, f"unsupported VERSION format: {version_name}")
    assert match is not None
    major = int(match.group("major"))
    minor = int(match.group("minor"))
    patch = int(match.group("patch"))
    require(major <= 200 and minor < 100 and patch < 100, "version components exceed Android mapping")
    base = major * 10_000_000 + minor * 100_000 + patch * 1_000
    label = match.group("label")
    number_text = match.group("number")
    if label is None:
        suffix = 999
    else:
        assert number_text is not None
        number = int(number_text)
        require(1 <= number <= 299, f"{label} ordinal must be in 1..299")
        suffix = {"alpha": 0, "beta": 300, "rc": 600}[label] + number
    version_code = base + suffix
    require(version_code <= 2_100_000_000, "derived versionCode exceeds Android maximum")
    return version_code


def derive_android_version(source: Path, version_file: Path) -> tuple[str, int]:
    text = source.read_text(encoding="utf-8")
    matches = re.findall(r'^\s*VERSION\s*::\s*"([^"]+)"\s*$', text, re.MULTILINE)
    require(len(matches) == 1, f"expected exactly one VERSION constant in {source}")
    version_name = matches[0]
    expected_code = mapped_version_code(version_name)

    properties = load_properties(version_file)
    require(
        set(properties) == {"versionCode"},
        f"{version_file} must contain exactly one versionCode property",
    )
    committed_text = properties["versionCode"]
    require(re.fullmatch(r"[1-9]\d*", committed_text) is not None, "committed versionCode must be a positive integer")
    committed_code = int(committed_text)
    require(committed_code <= 2_100_000_000, "committed versionCode exceeds Android maximum")
    require(
        committed_code == expected_code,
        f"committed versionCode {committed_code} does not match VERSION {version_name}; " +
        f"update it monotonically to {expected_code}",
    )
    return version_name, committed_code


def command_version(args: argparse.Namespace) -> None:
    source = Path(args.source).resolve()
    version_file = Path(args.version_file).resolve()
    output = Path(args.output).resolve()
    version_name, version_code = derive_android_version(source, version_file)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"versionName={version_name}\nversionCode={version_code}\n")
    os.replace(temporary, output)
    print(f"android version: {version_name} ({version_code})")


def machine_from_report(report: str, description: str) -> str:
    machine_match = re.search(r"^\s*Machine:\s*(.+?)\s*$", report, re.MULTILINE)
    require(machine_match is not None, f"cannot read ELF machine from {description}")
    assert machine_match is not None
    return machine_match.group(1)


def audit_raylib_archive(path: Path, abi: str, readelf: Path) -> None:
    require(abi in EXPECTED_ABIS, f"unsupported ABI requested for archive audit: {abi}")
    require(path.is_file(), f"missing raylib archive: {path}")
    require(path.stat().st_size > 0, f"empty raylib archive: {path}")
    require(readelf.is_file() and os.access(readelf, os.X_OK), f"missing llvm-readelf: {readelf}")
    llvm_ar = executable_sibling(readelf, "llvm-ar")
    llvm_nm = executable_sibling(readelf, "llvm-nm")

    members = tuple(line.strip() for line in run_checked([str(llvm_ar), "t", str(path)]).splitlines() if line.strip())
    require(
        members == EXPECTED_RAYLIB_MEMBERS,
        f"unexpected raylib members for {abi}: expected {EXPECTED_RAYLIB_MEMBERS}, got {members}",
    )
    require(len(members) == len(set(members)), f"duplicate archive members in {path}")

    symbols = run_checked([str(llvm_nm), "--defined-only", str(path)])
    require(re.search(r"\bT\s+android_main$", symbols, re.MULTILINE) is not None, f"android_main missing from {path}")
    require(
        re.search(r"\bT\s+ANativeActivity_onCreate$", symbols, re.MULTILINE) is None,
        f"duplicate native_app_glue entry remains in {path}",
    )
    audit_forbidden_markers(path.read_bytes(), str(path))

    with tempfile.TemporaryDirectory(prefix="arch-rogue-raylib-audit-") as temporary:
        extracted = Path(temporary)
        run_checked([str(llvm_ar), "x", str(path)], cwd=extracted)
        for member in EXPECTED_RAYLIB_MEMBERS:
            object_path = extracted / member
            require(object_path.is_file(), f"archive extraction omitted {member} from {path}")
            # Header-only inspection is intentional: raudio has thousands of
            # debug/relocation rows and some llvm-readelf builds can truncate the
            # combined multi-megabyte report before Python sees its header.
            report = run_checked([str(readelf), "-h", str(object_path)])
            require(
                "REL (Relocatable file)" in report,
                f"{member} is not a relocatable ELF object; header={report[:240]!r}",
            )
            machine = machine_from_report(report, str(object_path))
            require(machine == MACHINE_BY_ABI[abi], f"wrong machine in {member}: expected {MACHINE_BY_ABI[abi]}, got {machine}")

    print(f"raylib archive audit passed: {abi} {path}")


def command_archive(args: argparse.Namespace) -> None:
    audit_raylib_archive(Path(args.file).resolve(), args.abi, absolute_tool_path(args.readelf))


def audit_native(path: Path, abi: str, readelf: Path) -> None:
    require(abi in EXPECTED_ABIS, f"unsupported ABI requested for native audit: {abi}")
    require(path.is_file(), f"missing native library: {path}")
    require(path.stat().st_size > 0, f"empty native library: {path}")
    require(readelf.is_file() and os.access(readelf, os.X_OK), f"missing llvm-readelf: {readelf}")
    llvm_nm = executable_sibling(readelf, "llvm-nm")

    report = run_checked([
        str(readelf),
        "-h",
        "-d",
        "-lW",
        "-SW",
        "-n",
        "-V",
        str(path),
    ])
    require("DYN (Shared object file)" in report, f"{path} is not a shared ELF")
    machine = machine_from_report(report, str(path))
    require(machine == MACHINE_BY_ABI[abi], f"wrong ELF machine for {abi}: {machine}")
    require(f"Class:                             {ELF_CLASS_BY_ABI[abi]}" in report, f"wrong ELF class for {abi}")
    require(".note.android.ident" in report, f"missing Android NDK identity note in {path}")
    require("INTERP" not in report, f"shared library unexpectedly contains a program interpreter: {path}")
    require("TEXTREL" not in report, f"text relocations found in {path}")
    require("RPATH" not in report and "RUNPATH" not in report, f"runtime search path found in {path}")
    require("GNU_RELRO" in report, f"GNU RELRO is missing from {path}")
    require("BIND_NOW" in report or re.search(r"FLAGS(?:_1)?[^\n]*\bNOW\b", report) is not None, f"BIND_NOW is missing from {path}")
    require(
        re.search(r"^\s*0x[0-9A-Fa-f]+\s+\(INIT\)\s", report, re.MULTILINE) is None,
        f"NativeActivity library has eager DT_INIT entry; game main must be called by android_main: {path}",
    )

    needed = set(re.findall(r"Shared library: \[([^\]]+)\]", report))
    require(
        needed == EXPECTED_NEEDED,
        f"unexpected DT_NEEDED set for {path}: expected {sorted(EXPECTED_NEEDED)}, got {sorted(needed)}",
    )

    load_alignments: list[int] = []
    for line in report.splitlines():
        if re.match(r"^\s*LOAD\s", line):
            alignment_match = re.search(r"(0x[0-9A-Fa-f]+)\s*$", line)
            require(alignment_match is not None, f"cannot parse LOAD alignment: {line}")
            assert alignment_match is not None
            load_alignments.append(int(alignment_match.group(1), 16))
    require(bool(load_alignments), f"no ELF LOAD segments found in {path}")
    require(
        all(alignment >= 0x4000 for alignment in load_alignments),
        f"ELF LOAD alignment is below 16 KiB in {path}: {load_alignments}",
    )

    symbols = run_checked([str(llvm_nm), "-D", "--defined-only", str(path)])
    for symbol in (
        "ANativeActivity_onCreate",
        "android_main",
        "main",
        "Java_org_archrogue_archrogue_odin_ArchRogueActivity_nativeOnBackPressed",
        "ArchRogueAndroidDrainBackPresses",
    ):
        require(
            re.search(rf"\b{re.escape(symbol)}$", symbols, re.MULTILINE) is not None,
            f"required exported symbol {symbol} is missing from {path}",
        )

    audit_forbidden_markers(path.read_bytes(), str(path))
    print(f"native audit passed: {abi} {path}")


def command_native(args: argparse.Namespace) -> None:
    audit_native(Path(args.file).resolve(), args.abi, absolute_tool_path(args.readelf))


def canonical_entries(root: Path, prefix: str) -> dict[str, Path]:
    assets_root = root / "assets"
    require(assets_root.is_dir(), f"missing canonical assets directory: {assets_root}")
    entries: dict[str, Path] = {}
    casefolded: dict[str, str] = {}
    for source in sorted(assets_root.rglob("*")):
        require(not source.is_symlink(), f"canonical assets contain a symbolic link: {source}")
        if not source.is_file():
            continue
        relative = source.relative_to(assets_root).as_posix()
        runtime_path = f"assets/{relative}"
        name = f"{prefix}assets/{runtime_path}"
        folded = name.casefold()
        require(folded not in casefolded, f"case-colliding canonical assets: {casefolded.get(folded)} and {name}")
        casefolded[folded] = name
        entries[name] = source
    require(bool(entries), f"canonical assets directory is empty: {assets_root}")

    licenses = {
        f"{prefix}assets/licenses/ARCH_ROGUE_LICENSE.txt": root / "LICENSE",
        f"{prefix}assets/licenses/ARCH_ROGUE_NOTICE.txt": root / "NOTICE",
        f"{prefix}assets/licenses/RAYLIB_LICENSE.txt": root / "vendor/raylib/LICENSE",
    }
    for name, source in licenses.items():
        require(source.is_file() and not source.is_symlink(), f"missing or unsafe packaged license source: {source}")
        require(name.casefold() not in casefolded, f"case-colliding packaged license: {name}")
        casefolded[name.casefold()] = name
        entries[name] = source
    return entries


def validate_zip_structure(archive: zipfile.ZipFile) -> set[str]:
    infos = archive.infolist()
    names = [info.filename for info in infos]
    require(len(names) == len(set(names)), "ZIP contains duplicate entry names")
    casefolded: dict[str, str] = {}
    for info in infos:
        require("\\" not in info.filename and "\x00" not in info.filename, f"unsafe ZIP entry: {info.filename!r}")
        path = PurePosixPath(info.filename)
        require(not path.is_absolute() and ".." not in path.parts, f"unsafe ZIP entry: {info.filename}")
        folded = info.filename.casefold()
        require(folded not in casefolded, f"case-colliding ZIP entries: {casefolded.get(folded)} and {info.filename}")
        casefolded[folded] = info.filename
        mode = info.external_attr >> 16
        if mode:
            require(not stat.S_ISLNK(mode), f"ZIP contains symbolic link: {info.filename}")
    return {name for name in names if not name.endswith("/")}


def compare_packaged_assets(
    archive: zipfile.ZipFile,
    names: set[str],
    root: Path,
    prefix: str,
) -> None:
    expected = canonical_entries(root, prefix)
    actual = {name for name in names if name.startswith(f"{prefix}assets/")}
    missing = sorted(set(expected) - actual)
    unexpected = sorted(actual - set(expected))
    require(not missing, f"missing packaged assets/licenses: {missing[:20]}")
    require(not unexpected, f"unexpected/stale packaged assets: {unexpected[:20]}")
    for name, source in expected.items():
        packaged_hash = sha256_zip_entry(archive, name)
        source_hash = sha256_file(source)
        require(packaged_hash == source_hash, f"packaged asset differs from canonical source: {name}")


def audit_packaged_dex(
    archive: zipfile.ZipFile,
    names: set[str],
    prefix: str,
) -> None:
    dex_prefix = f"{prefix}dex/" if prefix else ""
    dex_pattern = re.compile(rf"^{re.escape(dex_prefix)}classes(?:\d+)?\.dex$")
    dex_names = sorted(name for name in names if dex_pattern.fullmatch(name))
    require(bool(dex_names), f"package contains no DEX under {dex_prefix or 'APK root'}")
    required_markers = {
        b"Lorg/archrogue/archrogue/odin/ArchRogueActivity;": "custom activity class",
        b"Landroid/app/NativeActivity;": "NativeActivity superclass",
        b"nativeOnBackPressed": "JNI Back method",
        b"getOnBackInvokedDispatcher": "API-33 Back dispatcher",
        b"loadLibrary": "explicit native library load",
    }
    found = {marker: False for marker in required_markers}
    for name in dex_names:
        payload = archive.read(name)
        require(payload.startswith(b"dex\n"), f"invalid DEX header: {name}")
        for marker in found:
            found[marker] = found[marker] or marker in payload
    missing = [label for marker, label in required_markers.items() if not found[marker]]
    require(not missing, f"packaged DEX omits ArchRogueActivity contract: {missing}")


def audit_packaged_native(
    archive: zipfile.ZipFile,
    names: set[str],
    prefix: str,
    readelf: Path,
    require_uncompressed: bool,
) -> None:
    expected = {f"{prefix}lib/{abi}/libmain.so" for abi in EXPECTED_ABIS}
    actual = {name for name in names if name.startswith(f"{prefix}lib/")}
    require(actual == expected, f"native ABI/file set mismatch: expected {sorted(expected)}, got {sorted(actual)}")
    with tempfile.TemporaryDirectory(prefix="arch-rogue-android-audit-") as temporary:
        temporary_root = Path(temporary)
        for abi in EXPECTED_ABIS:
            name = f"{prefix}lib/{abi}/libmain.so"
            info = archive.getinfo(name)
            if require_uncompressed:
                require(info.compress_type == zipfile.ZIP_STORED, f"APK native library is compressed: {name}")
            output = temporary_root / abi / "libmain.so"
            output.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(name) as source, output.open("wb") as destination:
                shutil.copyfileobj(source, destination)
            audit_native(output, abi, readelf)


def normalize_fingerprint(value: str) -> str:
    return re.sub(r"[^0-9a-f]", "", value.lower())


def package_attribute(package_line: str, name: str) -> str:
    match = re.search(rf"\b{re.escape(name)}='([^']*)'", package_line)
    require(match is not None, f"aapt package metadata omitted {name}")
    assert match is not None
    return match.group(1)


def audit_apk_metadata(
    apk: Path,
    build_tools: Path,
    expected_package: str,
    version_name: str,
    version_code: int,
    expected_cert: str | None,
) -> None:
    require(".odin.alpha" in expected_package, f"refusing non-alpha Android package id: {expected_package}")
    aapt = build_tools / "aapt"
    apksigner = build_tools / "apksigner"
    zipalign = build_tools / "zipalign"
    for tool in (aapt, apksigner, zipalign):
        require(tool.is_file() and os.access(tool, os.X_OK), f"missing Android build tool: {tool}")

    badging = run_checked([str(aapt), "dump", "badging", str(apk)])
    package_line = next((line for line in badging.splitlines() if line.startswith("package: ")), "")
    require(bool(package_line), "aapt did not report package metadata")
    require(package_attribute(package_line, "name") == expected_package, f"unexpected package id in {package_line}")
    require(package_attribute(package_line, "versionCode") == str(version_code), f"unexpected versionCode in {package_line}")
    require(package_attribute(package_line, "versionName") == version_name, f"unexpected versionName in {package_line}")
    compile_values: set[str] = set()
    for key in ("compileSdkVersion", "platformBuildVersionCode"):
        compile_match = re.search(rf"\b{key}='([^']+)'", package_line)
        if compile_match is not None:
            compile_values.add(compile_match.group(1))
    require(str(EXPECTED_COMPILE_SDK) in compile_values, f"APK compile SDK is not {EXPECTED_COMPILE_SDK}: {compile_values}")
    require(f"sdkVersion:'{EXPECTED_MIN_SDK}'" in badging, f"APK minSdk is not {EXPECTED_MIN_SDK}")
    require(f"targetSdkVersion:'{EXPECTED_TARGET_SDK}'" in badging, f"APK targetSdk is not {EXPECTED_TARGET_SDK}")

    gles_match = re.search(r"uses-gl-es:\s*'(0x[0-9a-fA-F]+)'", badging)
    require(gles_match is not None and int(gles_match.group(1), 16) == 0x00020000, "APK does not require OpenGL ES 2.0")
    native_match = re.search(r"^native-code:\s*(.+)$", badging, re.MULTILINE)
    require(native_match is not None, "aapt did not report native ABIs")
    assert native_match is not None
    reported_abis = set(re.findall(r"'([^']+)'", native_match.group(1)))
    require(reported_abis == set(EXPECTED_ABIS), f"unexpected aapt native-code set: {reported_abis}")

    permissions = set(re.findall(r"^uses-permission(?:-sdk-\d+)?: name='([^']+)'", badging, re.MULTILINE))
    forbidden_permissions = permissions & FORBIDDEN_NETWORK_PERMISSIONS
    require(not forbidden_permissions, f"APK declares network permission(s): {sorted(forbidden_permissions)}")

    manifest = run_checked([str(aapt), "dump", "xmltree", str(apk), "AndroidManifest.xml"])
    require("org.archrogue.archrogue.odin.ArchRogueActivity" in manifest, "Arch Rogue NativeActivity subclass is missing from manifest")
    require("android.app.lib_name" in manifest and '"main"' in manifest, "NativeActivity lib_name=main is missing")
    has_code_line = next((line for line in manifest.splitlines() if "android:hasCode" in line), "")
    require("0xffffffff" in has_code_line, f"application android:hasCode is not true: {has_code_line!r}")
    back_line = next((line for line in manifest.splitlines() if "android:enableOnBackInvokedCallback" in line), "")
    require("0xffffffff" in back_line, f"modern Android Back callback is not enabled: {back_line!r}")
    orientation_line = next((line for line in manifest.splitlines() if "android:screenOrientation" in line), "")
    require("0x6" in orientation_line, f"sensorLandscape orientation is missing: {orientation_line!r}")
    gles_line = next((line for line in manifest.splitlines() if "android:glEsVersion" in line), "")
    gles_values = re.findall(r"0x[0-9a-fA-F]+", gles_line)
    require(
        bool(gles_values) and int(gles_values[-1], 16) == 0x00020000,
        f"manifest GLES2 requirement is missing: {gles_line!r}",
    )
    for permission in FORBIDDEN_NETWORK_PERMISSIONS:
        require(permission not in manifest, f"unexpected network permission in manifest: {permission}")

    signature = run_checked([str(apksigner), "verify", "--verbose", "--print-certs", str(apk)])
    require(
        "Verified using v2 scheme (APK Signature Scheme v2): true" in signature
        or "Verified using v3 scheme (APK Signature Scheme v3): true" in signature,
        "APK lacks a verified v2/v3 signature",
    )
    fingerprints = re.findall(r"Signer #\d+ certificate SHA-256 digest:\s*([0-9a-fA-F:]+)", signature)
    require(len(fingerprints) == 1, f"APK must have exactly one signer, found {len(fingerprints)}")
    if expected_cert:
        require(
            normalize_fingerprint(fingerprints[0]) == normalize_fingerprint(expected_cert),
            "APK signer certificate does not match the expected release certificate",
        )

    run_checked([str(zipalign), "-c", "-P", "16", "-v", "4", str(apk)])


def command_apk(args: argparse.Namespace) -> None:
    apk = Path(args.file).resolve()
    root = Path(args.root).resolve()
    readelf = absolute_tool_path(args.readelf)
    build_tools = Path(args.build_tools).resolve()
    require(apk.is_file(), f"missing APK: {apk}")
    with zipfile.ZipFile(apk) as archive:
        names = validate_zip_structure(archive)
        compare_packaged_assets(archive, names, root, "")
        audit_packaged_dex(archive, names, "")
        audit_packaged_native(archive, names, "", readelf, require_uncompressed=True)
    audit_apk_metadata(
        apk,
        build_tools,
        args.expected_package,
        args.version_name,
        args.version_code,
        args.expected_cert,
    )
    print(f"APK audit passed: {apk}")


def bundletool_manifest(bundletool: Path, bundle: Path) -> str:
    return run_checked([
        "java",
        "-jar",
        str(bundletool),
        "dump",
        "manifest",
        f"--bundle={bundle}",
        "--module=base",
    ])


def aab_sensor_landscape_value(manifest: str) -> str | None:
    match = re.search(r'\bandroid:screenOrientation="([^"]+)"', manifest)
    if match is None:
        return None
    value = match.group(1)
    if value == "sensorLandscape":
        return value
    try:
        base = 16 if value.lower().startswith("0x") else 10
        return value if int(value, base) == 6 else None
    except ValueError:
        return None


def command_aab(args: argparse.Namespace) -> None:
    bundle = Path(args.file).resolve()
    root = Path(args.root).resolve()
    readelf = absolute_tool_path(args.readelf)
    bundletool = Path(args.bundletool).resolve()
    require(bundle.is_file(), f"missing AAB: {bundle}")
    require(".odin.alpha" in args.expected_package, f"refusing non-alpha Android package id: {args.expected_package}")
    require(bundletool.is_file(), f"missing pinned bundletool: {bundletool}")
    require(sha256_file(bundletool) == args.bundletool_sha256.lower(), "bundletool checksum mismatch")
    run_checked(["java", "-jar", str(bundletool), "validate", f"--bundle={bundle}"])
    manifest = bundletool_manifest(bundletool, bundle)
    require(f'package="{args.expected_package}"' in manifest, "AAB package id mismatch")
    require(f'android:versionName="{args.version_name}"' in manifest, "AAB versionName mismatch")
    require(f'android:versionCode="{args.version_code}"' in manifest, "AAB versionCode mismatch")
    require(f'android:minSdkVersion="{EXPECTED_MIN_SDK}"' in manifest, f"AAB minSdk is not {EXPECTED_MIN_SDK}")
    require(f'android:targetSdkVersion="{EXPECTED_TARGET_SDK}"' in manifest, f"AAB targetSdk is not {EXPECTED_TARGET_SDK}")
    require("org.archrogue.archrogue.odin.ArchRogueActivity" in manifest, "AAB Arch Rogue NativeActivity subclass is missing")
    require('android:hasCode="true"' in manifest, "AAB application android:hasCode is not true")
    require('android:enableOnBackInvokedCallback="true"' in manifest, "AAB modern Android Back callback is not enabled")
    orientation_match = re.search(r'\bandroid:screenOrientation="([^"]+)"', manifest)
    orientation_value = orientation_match.group(1) if orientation_match is not None else None
    require(
        aab_sensor_landscape_value(manifest) is not None,
        f"AAB sensorLandscape orientation is missing or invalid: {orientation_value!r}",
    )
    require(
        'android:glEsVersion="131072"' in manifest or 'android:glEsVersion="0x00020000"' in manifest,
        "AAB GLES2 requirement is missing",
    )
    for permission in FORBIDDEN_NETWORK_PERMISSIONS:
        require(permission not in manifest, f"unexpected network permission in AAB: {permission}")

    run_checked(["jarsigner", "-verify", "-strict", "-verbose", "-certs", str(bundle)])
    cert = run_checked(["keytool", "-printcert", "-jarfile", str(bundle)])
    cert_match = re.search(r"SHA256:\s*([0-9A-F:]+)", cert, re.IGNORECASE)
    require(cert_match is not None, "cannot read AAB signer SHA-256 fingerprint")
    assert cert_match is not None
    require(
        normalize_fingerprint(cert_match.group(1)) == normalize_fingerprint(args.expected_cert),
        "AAB signer certificate does not match the expected release certificate",
    )

    with zipfile.ZipFile(bundle) as archive:
        names = validate_zip_structure(archive)
        compare_packaged_assets(archive, names, root, "base/")
        audit_packaged_dex(archive, names, "base/")
        audit_packaged_native(archive, names, "base/", readelf, require_uncompressed=False)
    print(f"AAB audit passed: {bundle}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    version = subparsers.add_parser("version", help="validate and emit committed Android version metadata")
    version.add_argument("--source", required=True)
    version.add_argument("--version-file", required=True)
    version.add_argument("--output", required=True)
    version.set_defaults(func=command_version)

    archive = subparsers.add_parser("archive", help="audit one vendored raylib Android static archive")
    archive.add_argument("--file", required=True)
    archive.add_argument("--abi", choices=EXPECTED_ABIS, required=True)
    archive.add_argument("--readelf", required=True)
    archive.set_defaults(func=command_archive)

    native = subparsers.add_parser("native", help="audit one Android shared library")
    native.add_argument("--file", required=True)
    native.add_argument("--abi", choices=EXPECTED_ABIS, required=True)
    native.add_argument("--readelf", required=True)
    native.set_defaults(func=command_native)

    apk = subparsers.add_parser("apk", help="audit a completed APK")
    apk.add_argument("--file", required=True)
    apk.add_argument("--root", required=True)
    apk.add_argument("--readelf", required=True)
    apk.add_argument("--build-tools", required=True)
    apk.add_argument("--expected-package", required=True)
    apk.add_argument("--version-name", required=True)
    apk.add_argument("--version-code", type=int, required=True)
    apk.add_argument("--expected-cert")
    apk.set_defaults(func=command_apk)

    aab = subparsers.add_parser("aab", help="audit a completed Android App Bundle")
    aab.add_argument("--file", required=True)
    aab.add_argument("--root", required=True)
    aab.add_argument("--readelf", required=True)
    aab.add_argument("--bundletool", required=True)
    aab.add_argument("--bundletool-sha256", required=True)
    aab.add_argument("--expected-package", required=True)
    aab.add_argument("--version-name", required=True)
    aab.add_argument("--version-code", type=int, required=True)
    aab.add_argument("--expected-cert", required=True)
    aab.set_defaults(func=command_aab)

    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except (AuditError, KeyError, OSError, UnicodeError, ValueError, zipfile.BadZipFile) as error:
        print(f"android audit failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
