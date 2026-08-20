#!/usr/bin/env bash
# Canonical web (Emscripten/WebAssembly) command wrapper: preflight, build,
# audit, serve. Ordinary builds are offline; they verify and consume the
# vendored raylib web archive and the pinned Emscripten toolchain.
set -euo pipefail
export LC_ALL=C

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
TOOLCHAIN_FILE="$ROOT_DIR/web/toolchain.properties"
VENDOR_ROOT="$ROOT_DIR/vendor/raylib/wasm"
BUILD_ROOT="$ROOT_DIR/build/web"
DIST_DIR="$BUILD_ROOT/dist"
STAGING_DIR="$BUILD_ROOT/staging"

EMSDK_ROOT=""
EMCC_VERSION=""
VERSION_NAME=""

log() {
    printf 'web: %s\n' "$*"
}

die() {
    printf 'web: error: %s\n' "$*" >&2
    exit 1
}

usage() {
    cat <<'EOF'
usage: tools/web.sh <command>

  preflight   Validate toolchain pins, vendored archive, and host commands;
              print the declared initial-download budget and heap policy.
  build       Release web build: Odin wasm object, core/lazy payload split,
              Emscripten link, content addressing, Brotli siblings.
  audit       Strict audit of build/web/dist (budget, heap pin, no ASYNCIFY,
              content addressing, packs, no CDN references).
  serve       Serve build/web/dist locally with production-shaped headers.
EOF
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || die "missing command: $1"
}

require_file() {
    [[ -f "$1" ]] || die "missing file: $1"
}

property_value() {
    local file="$1" key="$2"
    sed -n "s/^${key}[[:space:]]*=[[:space:]]*//p" "$file" | sed -n '1p'
}

load_toolchain() {
    require_file "$TOOLCHAIN_FILE"
    # shellcheck disable=SC1090
    source "$TOOLCHAIN_FILE"
}

validate_toolchain_contract() {
    local required=(
        EMSDK_VERSION RAYLIB_VERSION RAYLIB_COMMIT RAYLIB_SOURCE_URL
        RAYLIB_SOURCE_SHA256 WEB_GRAPHICS WEB_INITIAL_MEMORY_BYTES
        WEB_STACK_SIZE_BYTES WEB_ALLOW_MEMORY_GROWTH
        WEB_INITIAL_DOWNLOAD_BUDGET_BYTES
    )
    local name
    for name in "${required[@]}"; do
        [[ -n "${!name:-}" ]] || die "toolchain property $name is missing or empty"
    done
    [[ "$RAYLIB_VERSION" == "6.0" ]] || die "RAYLIB_VERSION must remain pinned to 6.0"
    [[ "$WEB_GRAPHICS" == "GRAPHICS_API_OPENGL_ES3" ]] || die "WEB_GRAPHICS must remain GRAPHICS_API_OPENGL_ES3"
    [[ "$WEB_ALLOW_MEMORY_GROWTH" == "0" ]] || die "WEB_ALLOW_MEMORY_GROWTH must remain 0 (pinned heap)"
    [[ "$RAYLIB_SOURCE_SHA256" =~ ^[0-9a-f]{64}$ ]] || die "invalid pinned raylib source checksum"
    [[ "$EMSDK_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "invalid pinned EMSDK_VERSION"
    [[ "$WEB_INITIAL_MEMORY_BYTES" =~ ^[0-9]+$ ]] || die "invalid WEB_INITIAL_MEMORY_BYTES"
    (( WEB_INITIAL_MEMORY_BYTES % 65536 == 0 )) || die "WEB_INITIAL_MEMORY_BYTES must be a wasm page multiple"
}

resolve_emsdk() {
    EMSDK_ROOT="${EMSDK:-}"
    if [[ -z "$EMSDK_ROOT" ]]; then
        local candidate
        for candidate in /opt/emsdk "$HOME/emsdk"; do
            if [[ -f "$candidate/emsdk_env.sh" ]]; then
                EMSDK_ROOT="$candidate"
                break
            fi
        done
    fi
    if [[ -z "$EMSDK_ROOT" || ! -f "$EMSDK_ROOT/emsdk_env.sh" ]]; then
        {
            printf 'web: error: Emscripten SDK not found ($EMSDK, /opt/emsdk, ~/emsdk)\n'
            printf 'web: install the pinned toolchain with:\n'
            printf '  git clone https://github.com/emscripten-core/emsdk.git ~/emsdk\n'
            printf '  ~/emsdk/emsdk install %s\n' "$EMSDK_VERSION"
            printf '  ~/emsdk/emsdk activate %s\n' "$EMSDK_VERSION"
        } >&2
        exit 1
    fi
    # shellcheck disable=SC1091
    source "$EMSDK_ROOT/emsdk_env.sh" >/dev/null 2>&1
    command -v emcc >/dev/null 2>&1 || die "emcc missing after sourcing $EMSDK_ROOT/emsdk_env.sh"
    EMCC_VERSION="$(emcc --version | sed -n '1s/^emcc ([^)]*) \([0-9.]*\).*/\1/p')"
    [[ "$EMCC_VERSION" == "$EMSDK_VERSION" ]] || \
        die "emcc $EMCC_VERSION does not match pinned $EMSDK_VERSION; run: $EMSDK_ROOT/emsdk install $EMSDK_VERSION && $EMSDK_ROOT/emsdk activate $EMSDK_VERSION"
}

check_vendor() {
    require_file "$VENDOR_ROOT/libraylib.web.a"
    require_file "$VENDOR_ROOT/SHA256SUMS"
    require_file "$VENDOR_ROOT/PROVENANCE.md"
    grep -Fq "$RAYLIB_COMMIT" "$VENDOR_ROOT/PROVENANCE.md" || \
        die "web archive provenance does not record raylib commit $RAYLIB_COMMIT"
    grep -Fq "$RAYLIB_SOURCE_SHA256" "$VENDOR_ROOT/PROVENANCE.md" || \
        die "web archive provenance does not record the pinned source checksum"
    grep -Fq "GRAPHICS_API_OPENGL_ES3" "$VENDOR_ROOT/PROVENANCE.md" || \
        die "web archive provenance does not record the ES3 graphics contract"
    (
        cd "$VENDOR_ROOT"
        sha256sum -c SHA256SUMS >/dev/null
    ) || die "vendored web archive fails its committed checksums"
}

load_version() {
    VERSION_NAME="$(sed -n 's/^VERSION[[:space:]]*::[[:space:]]*"\([^"]*\)".*/\1/p' "$ROOT_DIR/src/main.odin" | sed -n '1p')"
    [[ -n "$VERSION_NAME" ]] || die "unable to read VERSION from src/main.odin"
}

preflight() {
    log "host: $(uname -s) $(uname -m)"
    require_command odin
    require_command python3
    require_command sha256sum
    load_toolchain
    validate_toolchain_contract
    resolve_emsdk
    check_vendor
    load_version
    if command -v brotli >/dev/null 2>&1; then
        log "brotli: available (compressed siblings will be produced)"
    else
        log "brotli: missing (outputs stay Brotli-ready; budget will measure raw sizes)"
    fi
    if command -v node >/dev/null 2>&1; then
        log "node: $(node --version) (web smoke/profiling harness available)"
    else
        log "node: missing (web smoke/profiling harness unavailable)"
    fi
    log "emsdk: $EMSDK_ROOT (emcc $EMCC_VERSION, pinned $EMSDK_VERSION)"
    log "raylib web archive: $RAYLIB_VERSION @ $RAYLIB_COMMIT ($WEB_GRAPHICS, WebGL2-only)"
    log "heap policy: INITIAL_MEMORY=$WEB_INITIAL_MEMORY_BYTES bytes, growth disabled, stack $WEB_STACK_SIZE_BYTES"
    log "declared initial-download budget: $WEB_INITIAL_DOWNLOAD_BUDGET_BYTES bytes ($(awk "BEGIN{printf \"%.1f\", $WEB_INITIAL_DOWNLOAD_BUDGET_BYTES/1e6}") MB on the wire)"
    log "preflight passed: version $VERSION_NAME"
}

build() {
    preflight
    mkdir -p "$BUILD_ROOT" "$DIST_DIR"
    rm -rf "$DIST_DIR"
    mkdir -p "$DIST_DIR"

    log "building Odin wasm object (release, vetted)"
    odin build "$ROOT_DIR/src" \
        -target:freestanding_wasm32 -build-mode:obj -vet -o:speed \
        -define:RAYLIB_WASM_LIB=env.o \
        -out:"$BUILD_ROOT/archrogue.wasm.o"

    log "splitting payload: core staging + lazy packs"
    python3 "$SCRIPT_DIR/web_pack_assets.py" \
        --staging "$STAGING_DIR" \
        --packs "$DIST_DIR/packs" \
        --manifest "$DIST_DIR/packs.json"

    log "linking with Emscripten (WebGL2-only, pinned heap, no ASYNCIFY)"
    emcc "$BUILD_ROOT/archrogue.wasm.obj" \
        "$ROOT_DIR/web/main_web.c" \
        "$VENDOR_ROOT/libraylib.web.a" \
        --js-library "$ROOT_DIR/web/library_archrogue.js" \
        --shell-file "$ROOT_DIR/web/shell.html" \
        -o "$DIST_DIR/index.html" \
        --preload-file "$STAGING_DIR@/assets" \
        -sUSE_GLFW=3 -sMIN_WEBGL_VERSION=2 -sMAX_WEBGL_VERSION=2 -sFULL_ES3 \
        -sINITIAL_MEMORY="$WEB_INITIAL_MEMORY_BYTES" \
        -sALLOW_MEMORY_GROWTH="$WEB_ALLOW_MEMORY_GROWTH" \
        -sSTACK_SIZE="$WEB_STACK_SIZE_BYTES" \
        -sWASM_BIGINT -sENVIRONMENT=web -sASSERTIONS=0 -O2 \
        -sEXPORTED_FUNCTIONS=_main,_malloc,_free,_ar_web_boot,_ar_web_tick,_ar_web_store_hydrate_entry,_ar_web_store_hydrate_done,_ar_web_set_visible,_ar_web_pagehide,_ar_web_resize,_ar_web_audio_unlock,_ar_web_pack_loaded,_ar_web_smoke_probe \
        -sEXPORTED_RUNTIME_METHODS=HEAPU8,UTF8ToString

    log "content-addressing outputs and injecting the file manifest"
    python3 - "$DIST_DIR" "$VERSION_NAME" <<'PY'
import hashlib
import json
import re
import sys
from pathlib import Path

dist = Path(sys.argv[1])
version = sys.argv[2]

renames = {}
for name in ("index.js", "index.wasm", "index.data"):
    path = dist / name
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    hashed = f"archrogue-{digest}.{name.split('.', 1)[1]}"
    path.rename(dist / hashed)
    renames[name] = hashed

html_path = dist / "index.html"
html = html_path.read_text()
# The emcc html minifier may strip attribute quotes; rewrite both forms.
html = html.replace('src="index.js"', f'src="{renames["index.js"]}"')
html = html.replace("src=index.js", f'src={renames["index.js"]}')
if renames["index.js"] not in html:
    raise SystemExit("web: failed to point index.html at the hashed runtime js")
manifest = {name: hashed for name, hashed in renames.items() if name != "index.js"}
# emcc may minify the shell (attribute quotes are stripped), so anchor on the
# bare <template tag rather than an exact attribute spelling.
injection = f'<script>window.AR_FILE_MANIFEST = {json.dumps(manifest, sort_keys=True)};</script><template'
if "<template" not in html:
    raise SystemExit("web: shell template anchor missing from emitted html")
html = html.replace("<template", injection, 1)
if "window.AR_FILE_MANIFEST = {" not in html:
    raise SystemExit("web: failed to inject AR_FILE_MANIFEST")
html_path.write_text(html)

info = {
    "version": version,
    "files": renames,
}
(dist / "build-info.json").write_text(json.dumps(info, indent=2, sort_keys=True) + "\n")
print(f"web: content-addressed {', '.join(renames.values())}")
PY

    if command -v brotli >/dev/null 2>&1; then
        log "producing Brotli siblings"
        find "$DIST_DIR" -type f \( -name '*.js' -o -name '*.wasm' -o -name '*.data' -o -name '*.html' -o -name '*.json' -o -name '*.arpack' \) \
            -exec brotli --force --keep --quality=9 {} \;
    else
        log "brotli unavailable: skipping compressed siblings (outputs remain Brotli-ready)"
    fi

    log "build complete: $DIST_DIR"
    audit
}

audit() {
    load_toolchain
    validate_toolchain_contract
    python3 "$SCRIPT_DIR/web_audit.py" --dist "$DIST_DIR"
}

serve() {
    exec python3 "$SCRIPT_DIR/web_serve.py" --root "$DIST_DIR" "$@"
}

command="${1:-}"
if [[ $# -gt 0 ]]; then
    shift
fi
case "$command" in
    preflight)
        [[ $# -eq 0 ]] || die "preflight accepts no arguments"
        preflight
        ;;
    build)
        [[ $# -eq 0 ]] || die "build accepts no arguments"
        build
        ;;
    audit)
        [[ $# -eq 0 ]] || die "audit accepts no arguments"
        audit
        ;;
    serve)
        serve "$@"
        ;;
    -h|--help|help|"")
        usage
        ;;
    *)
        usage >&2
        die "unknown command: $command"
        ;;
esac
