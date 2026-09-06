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
  test)
    verify_toolchain odin
    test_output=build/archrogue_tests
    test_platform_flags=()
    case "$(uname -s)" in
      MINGW*|MSYS*|CYGWIN*)
        test_output+=.exe
        # Persistence fixtures nest large by-value records. Match the Linux
        # test stack reserve instead of inheriting MSVC's smaller default.
        test_platform_flags=(-extra-linker-flags:/STACK:8388608 -define:ODIN_TEST_LOG_STATE_CHANGES=true)
        export MSYS2_ARG_CONV_EXCL="${MSYS2_ARG_CONV_EXCL:+$MSYS2_ARG_CONV_EXCL;}-extra-linker-flags:"
        ;;
    esac
    odin test tests "-out:$test_output" -vet -define:ODIN_TEST_FAIL_ON_BAD_MEMORY=true "${test_platform_flags[@]}" "$@"
    ;;
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
  windows-release)   exec python3 ./tools/windows/build.py build "$@" ;;
  windows-package)   exec python3 ./tools/windows/build.py package "$@" ;;
  windows-audit)     exec python3 ./tools/windows/audit.py "$@" ;;
  steam-windows)     exec python3 ./tools/steam/build_steam_windows.py "$@" ;;
  *)
    echo "usage: build.sh [toolchain|run|build|release|check|test|android-preflight|android-debug|android-release|android-install|android-audit|android-smoke|web-preflight|web-build|web-audit|web-serve|windows-release|windows-package|windows-audit|steam-linux|steam-windows] [args]" >&2
    exit 2
    ;;
esac
