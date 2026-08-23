#!/usr/bin/env bash
# Maintainer-only refresh/verification for the vendored raylib web archive.
set -euo pipefail
export LC_ALL=C

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
PROJECT_TOOLCHAIN_FILE="$ROOT_DIR/toolchain.properties"
TOOLCHAIN_FILE="$ROOT_DIR/web/toolchain.properties"
VENDOR_ROOT="$ROOT_DIR/vendor/raylib/wasm"
SOURCE_ARCHIVE=""
REFRESH_CHECKSUMS=false

for properties_file in "$PROJECT_TOOLCHAIN_FILE" "$TOOLCHAIN_FILE"; do
    if [[ ! -f "$properties_file" ]]; then
        printf 'raylib-web: missing toolchain properties: %s\n' "$properties_file" >&2
        exit 1
    fi
    # shellcheck disable=SC1090
    source "$properties_file"
done

log() {
    printf 'raylib-web: %s\n' "$*"
}

die() {
    printf 'raylib-web: error: %s\n' "$*" >&2
    exit 1
}

usage() {
    cat <<'EOF'
usage: tools/rebuild_raylib_web.sh [--source-archive PATH] [--refresh-checksums]

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
[[ "$WEB_GRAPHICS" == "GRAPHICS_API_OPENGL_ES3" ]] || die "WEB_GRAPHICS must remain GRAPHICS_API_OPENGL_ES3 (WebGL2-only contract)"
[[ "$RAYLIB_SOURCE_SHA256" =~ ^[0-9a-f]{64}$ ]] || die "invalid pinned raylib source checksum"
[[ "$EMSDK_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "invalid pinned EMSDK_VERSION"

for command in cmake ninja sha256sum tar python3 grep find; do
    command -v "$command" >/dev/null 2>&1 || die "missing command: $command"
done
if [[ -z "$SOURCE_ARCHIVE" ]]; then
    command -v curl >/dev/null 2>&1 || die "curl is required only when --source-archive is omitted"
fi

# Pinned Emscripten discovery: $EMSDK, /opt/emsdk, then ~/emsdk.
EMSDK_ROOT="${EMSDK:-}"
if [[ -z "$EMSDK_ROOT" ]]; then
    for candidate in /opt/emsdk "$HOME/emsdk"; do
        if [[ -f "$candidate/emsdk_env.sh" ]]; then
            EMSDK_ROOT="$candidate"
            break
        fi
    done
fi
if [[ -z "$EMSDK_ROOT" || ! -f "$EMSDK_ROOT/emsdk_env.sh" ]]; then
    printf 'raylib-web: error: Emscripten SDK not found ($EMSDK, /opt/emsdk, ~/emsdk)\n' >&2
    printf 'raylib-web: install it with:\n' >&2
    printf '  git clone https://github.com/emscripten-core/emsdk.git ~/emsdk\n' >&2
    printf '  ~/emsdk/emsdk install %s && ~/emsdk/emsdk activate %s\n' "$EMSDK_VERSION" "$EMSDK_VERSION" >&2
    exit 1
fi
# shellcheck disable=SC1091
source "$EMSDK_ROOT/emsdk_env.sh" >/dev/null 2>&1
command -v emcc >/dev/null 2>&1 || die "emcc missing after sourcing $EMSDK_ROOT/emsdk_env.sh"
EMCC_VERSION="$(emcc --version | sed -n '1s/^emcc ([^)]*) \([0-9.]*\).*/\1/p')"
[[ "$EMCC_VERSION" == "$EMSDK_VERSION" ]] || \
    die "emcc $EMCC_VERSION does not match pinned $EMSDK_VERSION; run: $EMSDK_ROOT/emsdk install $EMSDK_VERSION && $EMSDK_ROOT/emsdk activate $EMSDK_VERSION"
EMAR="$(command -v emar)" || die "emar not found in activated emsdk"

if [[ -f "$VENDOR_ROOT/PROVENANCE.md" ]]; then
    grep -Fq "$RAYLIB_COMMIT" "$VENDOR_ROOT/PROVENANCE.md" || \
        die "provenance does not record raylib commit $RAYLIB_COMMIT"
    grep -Fq "$RAYLIB_SOURCE_SHA256" "$VENDOR_ROOT/PROVENANCE.md" || \
        die "provenance does not record the pinned source checksum"
    grep -Fq "Emscripten \`$EMSDK_VERSION\`" "$VENDOR_ROOT/PROVENANCE.md" || \
        die "provenance does not record Emscripten $EMSDK_VERSION"
else
    [[ "$REFRESH_CHECKSUMS" == true ]] || die "missing $VENDOR_ROOT/PROVENANCE.md (author it, or run --refresh-checksums for a reviewed bootstrap)"
fi

WORK_DIR="$(mktemp -d -t arch-rogue-raylib-web.XXXXXXXX)"
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
mkdir -p "$STAGE_DIR"

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
# The reviewed Arch Rogue raylib patch touches only src/platforms/rcore_android.c;
# the web platform builds unpatched upstream sources.

build_dir="$WORK_DIR/build-web"
log "configuring static ES3 (WebGL2) web archive"
emcmake cmake \
    -S "$SOURCE_DIR" \
    -B "$build_dir" \
    -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INTERPROCEDURAL_OPTIMIZATION=OFF \
    -DCMAKE_INTERPROCEDURAL_OPTIMIZATION_RELEASE=OFF \
    "-DCMAKE_C_FLAGS=-ffile-prefix-map=$WORK_DIR=/arch-rogue-raylib-build -fdebug-prefix-map=$WORK_DIR=/arch-rogue-raylib-build" \
    "-DCMAKE_C_FLAGS_RELEASE=-O2 -DNDEBUG" \
    -DPLATFORM=Web \
    -DGRAPHICS="$WEB_GRAPHICS" \
    -DBUILD_EXAMPLES=OFF \
    -DBUILD_SHARED_LIBS=OFF >/dev/null
cmake --build "$build_dir" --target raylib --parallel

mapfile -t archives < <(find "$build_dir" -type f -name 'libraylib*.a' -print | sort)
[[ "${#archives[@]}" -eq 1 ]] || \
    die "expected one libraylib archive, found ${#archives[@]}"
cp "${archives[0]}" "$STAGE_DIR/libraylib.web.a"

# Archive audit: web platform objects present, no other platform leaked in, and
# the ES3 graphics contract actually reached rlgl.
members="$("$EMAR" t "$STAGE_DIR/libraylib.web.a")"
grep -Eq '(^|/)rcore\.c\.o$' <<<"$members" || die "archive is missing rcore.c.o"
for forbidden in rcore_android rcore_desktop_glfw rcore_desktop_sdl rcore_desktop_rgfw rcore_drm; do
    if grep -q "$forbidden" <<<"$members"; then
        die "archive unexpectedly contains $forbidden objects"
    fi
done
python3 - "$STAGE_DIR/libraylib.web.a" <<'PY'
import subprocess
import sys

archive = sys.argv[1]
symbols = subprocess.run(
    ["emnm", archive], capture_output=True, text=True, check=True,
).stdout
for required in ("InitWindow", "rlLoadTexture", "InitAudioDevice"):
    if f" T {required}" not in symbols and f" W {required}" not in symbols:
        raise SystemExit(f"raylib-web: required defined symbol missing: {required}")
if "emscripten_" not in symbols and "glfw" not in symbols:
    raise SystemExit("raylib-web: archive references neither emscripten nor glfw symbols; not a PLATFORM_WEB build")
PY

if [[ "$REFRESH_CHECKSUMS" == true ]]; then
    NEW_SUMS="$WORK_DIR/SHA256SUMS"
    (
        cd "$STAGE_DIR"
        sha256sum libraylib.web.a > "$NEW_SUMS"
    )
    mkdir -p "$VENDOR_ROOT"
    install -m 0644 "$STAGE_DIR/libraylib.web.a" "$VENDOR_ROOT/libraylib.web.a"
    install -m 0644 "$NEW_SUMS" "$VENDOR_ROOT/SHA256SUMS"
    log "installed reviewed raylib $RAYLIB_VERSION web archive and refreshed checksums"
else
    (
        cd "$STAGE_DIR"
        sha256sum -c "$VENDOR_ROOT/SHA256SUMS"
    )
    install -m 0644 "$STAGE_DIR/libraylib.web.a" "$VENDOR_ROOT/libraylib.web.a"
    log "verified and installed checksum-identical raylib $RAYLIB_VERSION web archive"
fi
