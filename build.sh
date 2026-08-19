#!/usr/bin/env bash
# Build/run/test wrapper for the Odin + raylib rewrite. Works from any cwd.
set -euo pipefail
cd "$(dirname "$0")"

cmd="${1:-run}"
shift || true
mkdir -p build

case "$cmd" in
  run)     odin run   src   -out:build/archrogue       -vet -debug   "$@" ;;
  build)   odin build src   -out:build/archrogue       -vet -debug   "$@" ;;
  release) odin build src   -out:build/archrogue       -vet -o:speed "$@" ;;
  check)   odin check src   -vet "$@" ;;
  test)              odin test  tests -out:build/archrogue_tests -vet "$@" ;;
  android-preflight) exec ./tools/android.sh preflight "$@" ;;
  android-debug)     exec ./tools/android.sh debug "$@" ;;
  android-release)   exec ./tools/android.sh release "$@" ;;
  android-install)   exec ./tools/android.sh install "$@" ;;
  android-audit)     exec ./tools/android.sh audit "$@" ;;
  android-smoke)     exec python3 ./tools/android_smoke.py "$@" ;;
  *)
    echo "usage: build.sh [run|build|release|check|test|android-preflight|android-debug|android-release|android-install|android-audit|android-smoke] [args]" >&2
    exit 2
    ;;
esac
