#!/usr/bin/env bash
# Verify the project-wide compiler and vendored Linux library contract.
set -euo pipefail
export LC_ALL=C

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
TOOLCHAIN_FILE="$ROOT_DIR/toolchain.properties"

fail() {
    printf 'toolchain: error: %s\n' "$*" >&2
    exit 1
}

[[ -f "$TOOLCHAIN_FILE" ]] || fail "missing project toolchain contract: $TOOLCHAIN_FILE"
# shellcheck disable=SC1090
source "$TOOLCHAIN_FILE"

for name in \
    ODIN_VERSION ODIN_COMMIT ODIN_BACKEND_LLVM_VERSION \
    RAYLIB_VERSION RAYLIB_COMMIT RAYLIB_SOURCE_URL RAYLIB_SOURCE_SHA256; do
    [[ -n "${!name:-}" ]] || fail "$name is missing from $TOOLCHAIN_FILE"
done
[[ "$ODIN_VERSION" =~ ^dev-[0-9]{4}-[0-9]{2}$ ]] || fail "invalid ODIN_VERSION: $ODIN_VERSION"
[[ "$ODIN_COMMIT" =~ ^[0-9a-f]{40}$ ]] || fail "ODIN_COMMIT must be one full Git commit"
[[ "$ODIN_BACKEND_LLVM_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || \
    fail "invalid ODIN_BACKEND_LLVM_VERSION: $ODIN_BACKEND_LLVM_VERSION"
[[ "$RAYLIB_VERSION" == "6.0" ]] || fail "RAYLIB_VERSION must remain pinned to 6.0"
[[ "$RAYLIB_COMMIT" =~ ^[0-9a-f]{40}$ ]] || fail "RAYLIB_COMMIT must be one full Git commit"
[[ "$RAYLIB_SOURCE_SHA256" =~ ^[0-9a-f]{64}$ ]] || fail "invalid RAYLIB_SOURCE_SHA256"

for platform_file in "$ROOT_DIR/android/toolchain.properties" "$ROOT_DIR/web/toolchain.properties"; do
    [[ -f "$platform_file" ]] || continue
    for shared_name in \
        ODIN_VERSION ODIN_COMMIT ODIN_BACKEND_LLVM_VERSION \
        RAYLIB_VERSION RAYLIB_COMMIT RAYLIB_SOURCE_URL RAYLIB_SOURCE_SHA256; do
        if grep -q "^${shared_name}=" "$platform_file"; then
            fail "$shared_name must be defined only in $TOOLCHAIN_FILE, not $platform_file"
        fi
    done
done

emit_metadata() {
    local android_file="$ROOT_DIR/android/toolchain.properties"
    local web_file="$ROOT_DIR/web/toolchain.properties"
    [[ -f "$android_file" ]] || fail "missing Android toolchain contract: $android_file"
    [[ -f "$web_file" ]] || fail "missing web toolchain contract: $web_file"
    # shellcheck disable=SC1090
    source "$android_file"
    # shellcheck disable=SC1090
    source "$web_file"

    printf 'odin_version=%s\n' "$ODIN_VERSION"
    printf 'odin_llvm_major=%s\n' "${ODIN_BACKEND_LLVM_VERSION%%.*}"
    printf 'java_major=%s\n' "$JAVA_MAJOR"
    printf 'odin_ir_clang_version=%s\n' "$ODIN_IR_CLANG_VERSION"
    printf 'odin_ir_clang_major=%s\n' "${ODIN_IR_CLANG_VERSION%%.*}"
    printf 'compile_sdk=%s\n' "$COMPILE_SDK"
    printf 'build_tools_version=%s\n' "$BUILD_TOOLS_VERSION"
    printf 'ndk_version=%s\n' "$NDK_VERSION"
    printf 'gradle_version=%s\n' "$GRADLE_VERSION"
    printf 'agp_version=%s\n' "$AGP_VERSION"
    printf 'emsdk_version=%s\n' "$EMSDK_VERSION"
}

verify_odin() {
    command -v odin >/dev/null 2>&1 || fail "Odin is missing; install $ODIN_VERSION at $ODIN_COMMIT with LLVM $ODIN_BACKEND_LLVM_VERSION"

    local detected version_prefix reported_commit
    detected="$(odin version 2>&1 | sed -n '1p')"
    version_prefix="odin version $ODIN_VERSION:"
    [[ "$detected" == "$version_prefix"* ]] || \
        fail "expected $ODIN_VERSION at $ODIN_COMMIT, found ${detected:-unknown}; see README.md toolchain setup"
    reported_commit="${detected#"$version_prefix"}"
    [[ "$reported_commit" =~ ^[0-9a-f]{7,40}$ && "$ODIN_COMMIT" == "$reported_commit"* ]] || \
        fail "Odin reported revision ${reported_commit:-missing}, not pinned $ODIN_COMMIT"

    local report backend_version
    if ! report="$(odin report 2>&1)"; then
        fail "could not inspect the Odin backend: $report"
    fi
    backend_version="$(sed -n 's/^[[:space:]]*Backend: LLVM //p' <<<"$report" | sed -n '1p')"
    [[ "$backend_version" == "$ODIN_BACKEND_LLVM_VERSION" ]] || \
        fail "expected Odin LLVM backend $ODIN_BACKEND_LLVM_VERSION, found ${backend_version:-unknown}"

    local source_dir="${ODIN_SOURCE_DIR:-$HOME/odin}"
    if [[ -d "$source_dir/.git" ]]; then
        local source_commit
        source_commit="$(git -C "$source_dir" rev-parse HEAD 2>/dev/null)" || \
            fail "could not inspect Odin source checkout at $source_dir"
        [[ "$source_commit" == "$ODIN_COMMIT" ]] || \
            fail "Odin source checkout $source_dir is $source_commit, expected $ODIN_COMMIT"
    fi

    printf 'toolchain: Odin %s:%s, LLVM %s\n' "$ODIN_VERSION" "$reported_commit" "$backend_version"
}

case "${1:-odin}" in
    metadata)
        emit_metadata
        ;;
    odin)
        verify_odin
        ;;
    linux)
        verify_odin
        python3 "$SCRIPT_DIR/verify_linux_raylib.py"
        ;;
    *)
        printf 'usage: tools/verify_toolchain.sh [metadata|odin|linux]\n' >&2
        exit 2
        ;;
esac
