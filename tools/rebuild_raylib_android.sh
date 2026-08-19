#!/usr/bin/env bash
# Maintainer-only refresh/verification for vendored raylib Android archives.
set -euo pipefail
export LC_ALL=C

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
TOOLCHAIN_FILE="$ROOT_DIR/android/toolchain.properties"
VENDOR_ROOT="$ROOT_DIR/vendor/raylib/android"
PATCH_FILE="$VENDOR_ROOT/raylib-6.0-arch-rogue.patch"
AUDITOR="$ROOT_DIR/tools/android_audit.py"
SOURCE_ARCHIVE=""
REFRESH_CHECKSUMS=false

if [[ ! -f "$TOOLCHAIN_FILE" ]]; then
    printf 'raylib-android: missing toolchain properties: %s\n' "$TOOLCHAIN_FILE" >&2
    exit 1
fi
# shellcheck disable=SC1090
source "$TOOLCHAIN_FILE"

log() {
    printf 'raylib-android: %s\n' "$*"
}

die() {
    printf 'raylib-android: error: %s\n' "$*" >&2
    exit 1
}

usage() {
    cat <<'EOF'
usage: tools/rebuild_raylib_android.sh [--source-archive PATH] [--refresh-checksums]

Without --source-archive, download the checksum-pinned raylib 6.0 tag archive.
With --source-archive, no network command is used. --refresh-checksums is an
explicit maintainer action for a reviewed pinned source/toolchain change.
Ordinary game builds never invoke this script or access the network.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --source-archive)
            [[ $# -ge 2 ]] || { usage >&2; exit 2; }
            SOURCE_ARCHIVE="$2"
            shift 2
            ;;
        --refresh-checksums)
            REFRESH_CHECKSUMS=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            usage >&2
            die "unknown argument: $1"
            ;;
    esac
done

[[ "$RAYLIB_VERSION" == "6.0" ]] || die "RAYLIB_VERSION must remain pinned to 6.0"
[[ "$NDK_VERSION" == "28.2.13676358" ]] || die "NDK_VERSION must remain pinned to 28.2.13676358"
[[ "$MIN_SDK" == "28" ]] || die "MIN_SDK must remain pinned to 28"
[[ "$ANDROID_ABIS" == "arm64-v8a,armeabi-v7a,x86_64" ]] || die "ANDROID_ABIS must remain arm64-v8a,armeabi-v7a,x86_64"
[[ "$RAYLIB_SOURCE_SHA256" =~ ^[0-9a-f]{64}$ ]] || die "invalid pinned raylib source checksum"

for command in cmake ninja sha256sum tar python3 grep find patch; do
    command -v "$command" >/dev/null 2>&1 || die "missing command: $command"
done
if [[ -z "$SOURCE_ARCHIVE" ]]; then
    command -v curl >/dev/null 2>&1 || die "curl is required only when --source-archive is omitted"
fi

SDK_ROOT="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-/opt/android-sdk}}"
NDK_ROOT="${ODIN_ANDROID_NDK:-$SDK_ROOT/ndk/$NDK_VERSION}"
if [[ ! -f "$NDK_ROOT/source.properties" ]]; then
    sdkmanager="$SDK_ROOT/cmdline-tools/latest/bin/sdkmanager"
    [[ -x "$sdkmanager" ]] || sdkmanager="sdkmanager"
    printf 'raylib-android: error: missing exact sdkmanager package: ndk;%s\n' "$NDK_VERSION" >&2
    printf 'raylib-android: install it with: %q %q\n' "$sdkmanager" "ndk;$NDK_VERSION" >&2
    exit 1
fi
NDK_REVISION="$(sed -n 's/^Pkg.Revision[[:space:]]*=[[:space:]]*//p' "$NDK_ROOT/source.properties" | sed -n '1p')"
[[ "$NDK_REVISION" == "$NDK_VERSION" ]] || \
    die "expected NDK $NDK_VERSION, found ${NDK_REVISION:-missing} at $NDK_ROOT"

LLVM_BIN="$NDK_ROOT/toolchains/llvm/prebuilt/linux-x86_64/bin"
LLVM_AR="$LLVM_BIN/llvm-ar"
LLVM_READELF="$LLVM_BIN/llvm-readelf"
for tool in "$LLVM_AR" "$LLVM_BIN/llvm-nm" "$LLVM_READELF"; do
    [[ -x "$tool" ]] || die "missing NDK tool: $tool"
done
[[ -f "$NDK_ROOT/build/cmake/android.toolchain.cmake" ]] || die "NDK CMake toolchain file is missing"
[[ -f "$AUDITOR" ]] || die "Android auditor is missing: $AUDITOR"
[[ -f "$PATCH_FILE" ]] || die "reviewed raylib Android patch is missing: $PATCH_FILE"
PATCH_SHA256="$(sha256sum "$PATCH_FILE" | awk '{print $1}')"
[[ "$PATCH_SHA256" == "$RAYLIB_PATCH_SHA256" ]] || die "raylib Android patch checksum mismatch"
grep -Fq "$RAYLIB_COMMIT" "$VENDOR_ROOT/PROVENANCE.md" || \
    die "provenance does not record raylib commit $RAYLIB_COMMIT"
grep -Fq "$RAYLIB_SOURCE_SHA256" "$VENDOR_ROOT/PROVENANCE.md" || \
    die "provenance does not record the pinned source checksum"

WORK_DIR="$(mktemp -d -t arch-rogue-raylib-android.XXXXXXXX)"
cleanup() {
    if [[ "${RAYLIB_KEEP_WORK:-0}" == "1" ]]; then
        log "keeping failed/intermediate work directory: $WORK_DIR"
    else
        rm -rf "$WORK_DIR"
    fi
}
trap cleanup EXIT
ARCHIVE="$WORK_DIR/raylib-$RAYLIB_VERSION.tar.gz"
SOURCE_DIR="$WORK_DIR/raylib-$RAYLIB_VERSION"
STAGE_DIR="$WORK_DIR/stage"
mkdir -p "$STAGE_DIR/arm64-v8a" "$STAGE_DIR/armeabi-v7a" "$STAGE_DIR/x86_64"

if [[ -n "$SOURCE_ARCHIVE" ]]; then
    [[ -f "$SOURCE_ARCHIVE" ]] || die "source archive not found: $SOURCE_ARCHIVE"
    SOURCE_ARCHIVE="$(cd -- "$(dirname -- "$SOURCE_ARCHIVE")" && pwd)/$(basename -- "$SOURCE_ARCHIVE")"
    cp "$SOURCE_ARCHIVE" "$ARCHIVE"
else
    log "downloading checksum-pinned raylib $RAYLIB_VERSION source"
    curl -L --fail --show-error --proto '=https' "$RAYLIB_SOURCE_URL" -o "$ARCHIVE"
fi

printf '%s  %s\n' "$RAYLIB_SOURCE_SHA256" "$ARCHIVE" | sha256sum -c -
if tar -tzf "$ARCHIVE" | grep -Eq '(^/|(^|/)\.\.(/|$))'; then
    die "source archive contains an unsafe path"
fi
tar -xzf "$ARCHIVE" --no-same-owner -C "$WORK_DIR"
[[ -d "$SOURCE_DIR" ]] || die "unexpected source archive layout (expected raylib-$RAYLIB_VERSION/)"
patch --batch --forward -d "$SOURCE_DIR" -p1 < "$PATCH_FILE"

# Keep this long upstream event-pump line outside the unified patch: GNU patch
# mis-locates it after the earlier bridge insertion on some versions. The exact
# one-for-one replacement is still checksum-pinned as part of this script.
python3 - "$SOURCE_DIR/src/platforms/rcore_android.c" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
old = """    // NOTE: Activity is paused if not enabled (platform.appEnabled) and always run flag is not set (FLAG_WINDOW_ALWAYS_RUN)
    while ((pollResult = ALooper_pollOnce((platform.appEnabled || FLAG_IS_SET(CORE.Window.flags, FLAG_WINDOW_ALWAYS_RUN))? 0 : -1, NULL, &pollEvents, ((void **)&platform.source)) > ALOOPER_POLL_TIMEOUT))
"""
new = """    // Arch Rogue owns suspension policy, its bounded save barrier, and its idle
    // wait. Never block inside EndDrawing() until a future resume event: doing so
    // would hide APP_CMD_PAUSE/TERM_WINDOW from the Odin lifecycle reducer.
    while ((pollResult = ALooper_pollOnce(0, NULL, &pollEvents, ((void **)&platform.source)) > ALOOPER_POLL_TIMEOUT))
"""
if text.count(old) != 1:
    raise SystemExit("raylib-android: pinned event-pump source context changed")
path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
PY

grep -Fq 'ArchRogueAndroidDrainLifecycleEvents' "$SOURCE_DIR/src/platforms/rcore_android.c" || die "Android bridge patch was not applied"
grep -Fq 'ALooper_pollOnce(0, NULL' "$SOURCE_DIR/src/platforms/rcore_android.c" || die "Android nonblocking event pump was not applied"

for abi in arm64-v8a armeabi-v7a x86_64; do
    build_dir="$WORK_DIR/build-$abi"
    log "configuring static PIC GLES2 archive for $abi"
    cmake \
        -S "$SOURCE_DIR" \
        -B "$build_dir" \
        -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_POSITION_INDEPENDENT_CODE=ON \
        -DCMAKE_INTERPROCEDURAL_OPTIMIZATION=OFF \
        -DCMAKE_INTERPROCEDURAL_OPTIMIZATION_RELEASE=OFF \
        "-DCMAKE_C_FLAGS=-ffile-prefix-map=$WORK_DIR=/arch-rogue-raylib-build -fdebug-prefix-map=$WORK_DIR=/arch-rogue-raylib-build" \
        "-DCMAKE_C_FLAGS_RELEASE=-O2 -DNDEBUG" \
        "-DCMAKE_CXX_FLAGS=-ffile-prefix-map=$WORK_DIR=/arch-rogue-raylib-build -fdebug-prefix-map=$WORK_DIR=/arch-rogue-raylib-build" \
        "-DCMAKE_CXX_FLAGS_RELEASE=-O2 -DNDEBUG" \
        -DCMAKE_TOOLCHAIN_FILE="$NDK_ROOT/build/cmake/android.toolchain.cmake" \
        -DANDROID_ABI="$abi" \
        -DANDROID_PLATFORM="android-$MIN_SDK" \
        -DPLATFORM=Android \
        -DGRAPHICS=GRAPHICS_API_OPENGL_ES2 \
        -DBUILD_EXAMPLES=OFF \
        -DBUILD_SHARED_LIBS=OFF \
        -DWITH_PIC=ON
    cmake --build "$build_dir" --target raylib --parallel

    mapfile -t archives < <(find "$build_dir" -type f -name libraylib.a -print | sort)
    [[ "${#archives[@]}" -eq 1 ]] || \
        die "expected one libraylib.a for $abi, found ${#archives[@]}"
    cp "${archives[0]}" "$STAGE_DIR/$abi/libraylib.a"

    # Odin's Android subtarget compiles native_app_glue itself. Keep raylib's
    # android_main but remove the duplicate ANativeActivity_onCreate provider.
    members="$($LLVM_AR t "$STAGE_DIR/$abi/libraylib.a")"
    grep -Fxq 'android_native_app_glue.c.o' <<<"$members" || \
        die "upstream archive did not contain expected android_native_app_glue.c.o for $abi"
    "$LLVM_AR" d "$STAGE_DIR/$abi/libraylib.a" android_native_app_glue.c.o

    python3 "$AUDITOR" archive \
        --file "$STAGE_DIR/$abi/libraylib.a" \
        --abi "$abi" \
        --readelf "$LLVM_READELF"
done

if [[ "$REFRESH_CHECKSUMS" == true ]]; then
    NEW_SUMS="$WORK_DIR/SHA256SUMS"
    (
        cd "$STAGE_DIR"
        sha256sum arm64-v8a/libraylib.a armeabi-v7a/libraylib.a x86_64/libraylib.a > "$NEW_SUMS"
    )
    install -m 0644 "$STAGE_DIR/arm64-v8a/libraylib.a" "$VENDOR_ROOT/arm64-v8a/libraylib.a"
    install -m 0644 "$STAGE_DIR/armeabi-v7a/libraylib.a" "$VENDOR_ROOT/armeabi-v7a/libraylib.a"
    install -m 0644 "$STAGE_DIR/x86_64/libraylib.a" "$VENDOR_ROOT/x86_64/libraylib.a"
    install -m 0644 "$NEW_SUMS" "$VENDOR_ROOT/SHA256SUMS"
    log "installed reviewed raylib $RAYLIB_VERSION archives and refreshed checksums"
else
    (
        cd "$STAGE_DIR"
        sha256sum -c "$VENDOR_ROOT/SHA256SUMS"
    )
    install -m 0644 "$STAGE_DIR/arm64-v8a/libraylib.a" "$VENDOR_ROOT/arm64-v8a/libraylib.a"
    install -m 0644 "$STAGE_DIR/armeabi-v7a/libraylib.a" "$VENDOR_ROOT/armeabi-v7a/libraylib.a"
    install -m 0644 "$STAGE_DIR/x86_64/libraylib.a" "$VENDOR_ROOT/x86_64/libraylib.a"
    log "verified and installed checksum-identical raylib $RAYLIB_VERSION archives"
fi
