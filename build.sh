#!/usr/bin/env bash
# Build/run/test wrapper for the Odin + raylib rewrite. Works from any cwd.
set -euo pipefail
cd "$(dirname "$0")"

cmd="${1:-run}"
shift || true
mkdir -p build

verify_toolchain() {
  bash ./tools/verify_toolchain.sh "$1"
}

case "$cmd" in
  toolchain) exec bash ./tools/verify_toolchain.sh linux ;;
  run)     verify_toolchain linux; odin run   src   -out:build/archrogue       -vet -debug   "$@" ;;
  build)   verify_toolchain linux; odin build src   -out:build/archrogue       -vet -debug   "$@" ;;
  release) verify_toolchain linux; odin build src   -out:build/archrogue       -vet -o:speed "$@" ;;
  check)   verify_toolchain odin;  odin check src   -vet "$@" ;;
  test)    verify_toolchain odin;  odin test  tests -out:build/archrogue_tests -vet "$@" ;;
  android-preflight) exec bash ./tools/android.sh preflight "$@" ;;
  android-debug)     exec bash ./tools/android.sh debug "$@" ;;
  android-release)   exec bash ./tools/android.sh release "$@" ;;
  android-install)   exec bash ./tools/android.sh install "$@" ;;
  android-audit)     exec bash ./tools/android.sh audit "$@" ;;
  android-smoke)     exec python3 ./tools/android_smoke.py "$@" ;;
  web-preflight)     exec bash ./tools/web.sh preflight "$@" ;;
  web-build)         exec bash ./tools/web.sh build "$@" ;;
  web-audit)         exec bash ./tools/web.sh audit "$@" ;;
  web-serve)         exec bash ./tools/web.sh serve "$@" ;;
  steam-linux)       exec bash ./tools/steam/build_steam_linux.sh "$@" ;;
  *)
    echo "usage: build.sh [toolchain|run|build|release|check|test|android-preflight|android-debug|android-release|android-install|android-audit|android-smoke|web-preflight|web-build|web-audit|web-serve|steam-linux] [args]" >&2
    exit 2
    ;;
esac
