#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
#
# Reproducible Arch Rogue Android APK build helper (milestone 4.3.0).
#
# Usage:
#   tools/build_android.sh            # debug APK (unsigned, self-signed at install)
#   tools/build_android.sh release     # release APK, signed when keystore env is set
#
# Requires: a Python 3.11+ venv with pygame-ce installed, plus buildozer.
# Install buildozer into the project venv:
#   .venv/bin/python -m pip install buildozer cython
#
# The script sources the version + app id from pyproject.toml so the APK always
# matches the desktop release.  It writes the rewritten buildozer.spec into the
# project root only in-memory (via buildozer's own spec) by exporting the values
# through environment overrides that buildozer reads at runtime.

set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f pyproject.toml ]; then
  echo "build_android.sh: must be run from the Arch Rogue repository root" >&2
  exit 1
fi

MODE="${1:-debug}"
case "$MODE" in
  debug|release) ;;
  *)
    echo "build_android.sh: unknown mode '$MODE' (use 'debug' or 'release')" >&2
    exit 1
    ;;
esac

PYTHON="${PYTHON:-.venv/bin/python}"
if [ ! -x "$PYTHON" ]; then
  PYTHON="$(command -v python3 || command -v python)"
fi

# Read version + app id from pyproject.toml without adding a dependency.
VERSION="$("$PYTHON" - <<'PY'
import tomllib
with open("pyproject.toml", "rb") as f:
    data = tomllib.load(f)
print(data["project"]["version"])
PY
)"

echo "Arch Rogue Android build: version=$VERSION mode=$MODE"

if ! "$PYTHON" -m buildozer --version >/dev/null 2>&1; then
  echo "buildozer not found. Install it with:" >&2
  echo "  $PYTHON -m pip install buildozer cython" >&2
  exit 1
fi

# buildozer reads [app]/package.version and [app]/package.domain from the spec.
# Patch the spec in place so the build is reproducible from the checked-in file,
# then restore it on exit so the repository stays clean.
SPEC="buildozer.spec"
cp "$SPEC" "$SPEC.bak"
trap 'mv "$SPEC.bak" "$SPEC"' EXIT

"$PYTHON" - <<PY
import re
from pathlib import Path
path = Path("$SPEC")
text = path.read_text(encoding="utf-8")
text = re.sub(r"^package\.version\s*=.*$", "package.version = $VERSION", text, flags=re.M)
text = re.sub(r"^version\s*=.*$", "version = $VERSION", text, flags=re.M)
if "$MODE" == "release":
    text = re.sub(r"^android\.debug\s*=.*$", "android.debug = 0", text, flags=re.M)
else:
    text = re.sub(r"^android\.debug\s*=.*$", "android.debug = 1", text, flags=re.M)
path.write_text(text, encoding="utf-8")
PY

# --- Android SDK license acceptance ---------------------------------------
# buildozer downloads its own Android SDK to ~/.buildozer/android/platform and
# then asks sdkmanager to install build-tools/platforms.  sdkmanager refuses
# to install build-tools (and aidl is then missing) until every SDK license is
# accepted.  In a non-interactive CI shell the license prompt is skipped and
# the build dies at "build-tools folder not found / Aidl not found".
#
# Fix: pre-seed the license-accepted files with every known SDK license hash,
# then (once buildozer has downloaded cmdline-tools) run `sdkmanager --licenses`
# non-interactively so even future build-tools versions are accepted.
accept_android_licenses() {
  local sdk="$HOME/.buildozer/android/platform/android-sdk"
  mkdir -p "$sdk/licenses"
  # android-sdk-license covers build-tools through the current generation.
  # Each line is a SHA1 of a license text; sdkmanager accepts if the hash is
  # present, so listing every generation is safe and idempotent.
  printf '\n8933bad161af4178b1185d19a3724b40\nd56f5187479451eabf01fb78af6dfcb131a6481e\n24333f8a63b6825ea9c5514f83c2829b004d1fee\n' \
    > "$sdk/licenses/android-sdk-license"
  printf '\n84831b9409646a918e30573bab4c9c9c\n' \
    > "$sdk/licenses/android-sdk-preview-license"
  # If buildozer already bootstrapped cmdline-tools, accept every license
  # non-interactively so the seeded hashes stay current with the installed SDK
  # (this also covers any newer build-tools license text not in the seed list).
  local mgr
  for mgr in \
    "$sdk/cmdline-tools/latest/bin/sdkmanager" \
    "$sdk/cmdline-tools/bin/sdkmanager" \
    "$sdk/tools/bin/sdkmanager"; do
    if [ -x "$mgr" ]; then
      yes | "$mgr" --licenses --sdk_root="$sdk" >/dev/null 2>&1 || true
      break
    fi
  done
}

accept_android_licenses

# buildozer may still fail on the first run if it bootstraps cmdline-tools
# after our pre-seed.  Run once to bootstrap, re-accept licenses with the now-
# available sdkmanager, then run the real build.
run_buildozer() {
  local mode="$1"
  if [ "$mode" = "release" ]; then
    if [ -n "${ARCH_ROGUE_ANDROID_KEYSTORE:-}" ] && [ -n "${ARCH_ROGUE_ANDROID_KEYALIAS:-}" ]; then
      export P4A_RELEASE_KEYSTORE="$ARCH_ROGUE_ANDROID_KEYSTORE"
      export P4A_RELEASE_KEYSTORE_PASSWD="${ARCH_ROGUE_ANDROID_KEYSTORE_PASSWD:-}"
      export P4A_RELEASE_KEYALIAS="$ARCH_ROGUE_ANDROID_KEYALIAS"
      export P4A_RELEASE_KEYALIAS_PASSWD="${ARCH_ROGUE_ANDROID_KEYALIAS_PASSWD:-}"
    else
      echo "Release keystore env not set; producing unsigned release APK." >&2
    fi
    "$PYTHON" -m buildozer -v android release
  else
    "$PYTHON" -m buildozer -v android debug
  fi
}

if ! run_buildozer "$MODE"; then
  echo "build_android.sh: first buildozer pass failed; re-accepting SDK licenses and retrying." >&2
  accept_android_licenses
  run_buildozer "$MODE"
fi

# Surface the produced APK path for CI/local users.
APK_DIR="bin"
APK_PATH="$(ls -1 "$APK_DIR"/*.apk 2>/dev/null | head -n1 || true)"
if [ -z "$APK_PATH" ]; then
  echo "build_android.sh: no APK produced in $APK_DIR" >&2
  exit 1
fi
echo "Arch Rogue Android APK: $APK_PATH"