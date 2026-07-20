#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
#
# Reproducible Arch Rogue Android APK build helper (milestone 4.3.x).
#
# Usage:
#   tools/build_android.sh            # debug APK (unsigned, self-signed at install)
#   tools/build_android.sh release     # release APK, signed when keystore env is set
#
# Requires the pinned host-side Android tooling:
#   .venv/bin/python -m pip install -e ".[android]"
# Target pygame-ce is cross-compiled by the checked-in p4a recipe; the host
# pygame-ce wheel installed for desktop development is never copied into the APK.
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
  echo "buildozer not found. Install the pinned Android dependencies with:" >&2
  echo "  $PYTHON -m pip install -e \".[android]\"" >&2
  exit 1
fi

# Refresh generated license/notice copies before validating them. The LGPL
# text is a checked-in third-party license asset and is intentionally not
# regenerated from an Arch Rogue root file.
mkdir -p src/arch_rogue/assets/licenses
cp LICENSE src/arch_rogue/assets/licenses/LICENSE.txt
cp NOTICE src/arch_rogue/assets/licenses/NOTICE.txt

# Fail before an expensive cross-build if the root SDL2 entry point, local
# pygame-ce recipe, p4a pin, ABI settings, or bundled license assets regressed.
"$PYTHON" tools/validate_android_apk.py \
  --project-root . --source-dir src --spec buildozer.spec

# p4a removes an incompatible distribution but can leave its per-ABI
# python-installs tree behind. A replacement recipe with the same import package
# name (pygame) is then incorrectly considered already installed. Fingerprint
# every native-build input and clean only when those inputs changed or when a
# previous build never reached the validated/stamped state.
NATIVE_FINGERPRINT="$("$PYTHON" - <<'PY'
import configparser
import hashlib
import importlib.metadata
from pathlib import Path

config = configparser.ConfigParser(interpolation=None)
config.read("buildozer.spec", encoding="utf-8")
app = config["app"]
keys = (
    "requirements",
    "p4a.bootstrap",
    "p4a.commit",
    "android.api",
    "android.minapi",
    "android.target_api",
    "android.ndk",
    "android.archs",
)
digest = hashlib.sha256()
for key in keys:
    digest.update(f"{key}={app.get(key, '')}\n".encode())
for package in ("buildozer", "Cython"):
    digest.update(f"{package}={importlib.metadata.version(package)}\n".encode())
for path in sorted(Path("android/recipes").rglob("*")):
    if path.is_file():
        digest.update(str(path.relative_to("android/recipes")).encode())
        digest.update(path.read_bytes())
print(digest.hexdigest())
PY
)"
NATIVE_STAMP=".buildozer/android/arch-rogue-native.sha256"
CACHED_FINGERPRINT=""
if [ -f "$NATIVE_STAMP" ]; then
  IFS= read -r CACHED_FINGERPRINT < "$NATIVE_STAMP" || true
fi
BUILD_CACHE_PRESENT=0
for cache_dir in .buildozer/android/platform/build-*; do
  if [ -d "$cache_dir" ]; then
    BUILD_CACHE_PRESENT=1
    break
  fi
done
if [ "$BUILD_CACHE_PRESENT" -eq 1 ] && [ "$CACHED_FINGERPRINT" != "$NATIVE_FINGERPRINT" ]; then
  if [ "${ARCH_ROGUE_ANDROID_REUSE_UNVERIFIED_CACHE:-0}" = "1" ]; then
    echo "WARNING: reusing unverified Android caches for iterative development; final APK audit remains mandatory." >&2
  else
    echo "Android native inputs changed or are unverified; cleaning stale p4a build caches."
    "$PYTHON" -m buildozer android clean
  fi
fi

# buildozer reads [app]/package.version and [app]/package.domain from the spec.
# Patch the spec in place so the build is reproducible from the checked-in file,
# then restore it on exit so the repository stays clean.
SPEC="buildozer.spec"
SPEC_BACKUP="$(mktemp "${TMPDIR:-/tmp}/arch-rogue-buildozer.XXXXXX")"
BUILD_MARKER="$(mktemp "${TMPDIR:-/tmp}/arch-rogue-apk-build.XXXXXX")"
BUILD_LOG="$(mktemp "${TMPDIR:-/tmp}/arch-rogue-build-log.XXXXXX")"
cp "$SPEC" "$SPEC_BACKUP"
cleanup() {
  cp "$SPEC_BACKUP" "$SPEC"
  rm -f "$SPEC_BACKUP" "$BUILD_MARKER" "$BUILD_LOG"
}
trap cleanup EXIT

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

# --- Android SDK bootstrap + license acceptance ---------------------------
# Buildozer 1.6.0 considers any existing android-sdk directory installed, even
# if a cancelled/cache-restored setup contains no sdkmanager. Never create an
# empty SDK merely to seed licenses: that makes Buildozer skip its own download.
# Repair modern command-line-tool layouts, or remove only Buildozer's incomplete
# default cache so the next invocation downloads a complete pinned SDK.
android_sdk_root() {
  printf '%s\n' "${ANDROIDSDK:-$HOME/.buildozer/android/platform/android-sdk}"
}

repair_android_sdk_bootstrap() {
  local sdk legacy manager default_sdk
  sdk="$(android_sdk_root)"
  legacy="$sdk/tools/bin/sdkmanager"
  default_sdk="$HOME/.buildozer/android/platform/android-sdk"
  if [ -x "$legacy" ]; then
    return
  fi

  for manager in \
    "$sdk/cmdline-tools/latest/bin/sdkmanager" \
    "$sdk/cmdline-tools/bin/sdkmanager"; do
    if [ -x "$manager" ]; then
      echo "Repairing Buildozer sdkmanager compatibility path: $legacy"
      mkdir -p "$sdk/tools/bin"
      ln -sfn "$manager" "$legacy"
      if [ -x "${manager%/*}/avdmanager" ]; then
        ln -sfn "${manager%/*}/avdmanager" "$sdk/tools/bin/avdmanager"
      fi
      return
    fi
  done

  if [ -d "$sdk" ]; then
    if [ "$sdk" = "$default_sdk" ]; then
      echo "Removing incomplete cached Android SDK (sdkmanager missing): $sdk" >&2
      rm -rf "$sdk"
    else
      echo "build_android.sh: custom ANDROIDSDK is incomplete; sdkmanager missing under $sdk" >&2
      exit 1
    fi
  fi
}

# Once command-line tools exist, pre-seed known license hashes and run
# `sdkmanager --licenses` non-interactively. If the SDK does not exist yet,
# return without creating it so Buildozer can bootstrap it correctly.
accept_android_licenses() {
  local sdk
  sdk="$(android_sdk_root)"
  if [ ! -d "$sdk" ]; then
    return
  fi
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

repair_android_sdk_bootstrap
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

if ! run_buildozer "$MODE" 2>&1 | tee "$BUILD_LOG"; then
  if grep -Eqi 'license.*not accepted|Aidl not found|build-tools.*not found|sdkmanager.*(does not exist|not installed)' "$BUILD_LOG"; then
    echo "build_android.sh: SDK setup failed; repairing SDK tools/licenses and retrying once." >&2
    repair_android_sdk_bootstrap
    accept_android_licenses
    run_buildozer "$MODE"
  else
    echo "build_android.sh: build failed; not retrying a non-license error." >&2
    exit 1
  fi
fi

# Select only artifacts created by this invocation. This prevents an old, bad
# APK in bin/ from being reported or released after a failed/partial rebuild.
APK_DIR="bin"
APK_PATHS=()
if [ -d "$APK_DIR" ]; then
  while IFS= read -r -d '' candidate; do
    APK_PATHS+=("$candidate")
  done < <(find "$APK_DIR" -maxdepth 1 -type f -name '*.apk' \
    -newer "$BUILD_MARKER" -print0)
fi
if [ "${#APK_PATHS[@]}" -ne 1 ]; then
  echo "build_android.sh: expected exactly one newly built APK in $APK_DIR; found ${#APK_PATHS[@]}" >&2
  printf '  %s\n' "${APK_PATHS[@]}" >&2
  exit 1
fi
APK_PATH="${APK_PATHS[0]}"

# Inspect both APK-level libraries and every ELF extension in each compressed
# Python bundle. A successful Gradle build is not sufficient: p4a can otherwise
# package a host x86_64 wheel into a valid-looking ARM APK.
"$PYTHON" tools/validate_android_apk.py \
  --project-root . --source-dir src --spec "$SPEC" "$APK_PATH"

# Release integrity: validate the signing block and manifest metadata before an
# APK can be stamped/uploaded. A ZIP with valid files is not installable unless
# its APK signature verifies, and stale package/version metadata must not pass.
SDK_BUILD_TOOLS_ROOT="${ANDROIDSDK:-$HOME/.buildozer/android/platform/android-sdk}/build-tools"
BUILD_TOOL_DIRS=()
while IFS= read -r directory; do
  BUILD_TOOL_DIRS+=("$directory")
done < <(find "$SDK_BUILD_TOOLS_ROOT" -mindepth 1 -maxdepth 1 -type d -print | sort -V)
if [ "${#BUILD_TOOL_DIRS[@]}" -eq 0 ]; then
  echo "build_android.sh: Android SDK build-tools not found under $SDK_BUILD_TOOLS_ROOT" >&2
  exit 1
fi
BUILD_TOOLS_DIR="${BUILD_TOOL_DIRS[${#BUILD_TOOL_DIRS[@]}-1]}"
AAPT="$BUILD_TOOLS_DIR/aapt"
APKSIGNER="$BUILD_TOOLS_DIR/apksigner"
if [ ! -x "$AAPT" ] || [ ! -x "$APKSIGNER" ]; then
  echo "build_android.sh: aapt/apksigner missing from $BUILD_TOOLS_DIR" >&2
  exit 1
fi
"$APKSIGNER" verify --verbose "$APK_PATH"
BADGING="$("$AAPT" dump badging "$APK_PATH")"
printf '%s\n' "$BADGING" | grep -Fq "package: name='org.archrogue.archrogue'"
printf '%s\n' "$BADGING" | grep -Fq "versionName='$VERSION'"
printf '%s\n' "$BADGING" | grep -Fq "native-code: 'arm64-v8a' 'armeabi-v7a'"

mkdir -p "$(dirname "$NATIVE_STAMP")"
printf '%s\n' "$NATIVE_FINGERPRINT" > "$NATIVE_STAMP"
echo "Arch Rogue Android APK: $APK_PATH"