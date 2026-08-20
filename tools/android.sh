#!/usr/bin/env bash
# Offline Android build/package/install wrapper for the Odin rewrite.
set -euo pipefail
export LC_ALL=C

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
ANDROID_DIR="$ROOT_DIR/android"
TOOLCHAIN_FILE="$ANDROID_DIR/toolchain.properties"
BUILD_ROOT="$ROOT_DIR/build/android"
GENERATED_ROOT="$BUILD_ROOT/generated"
JNI_ROOT="$GENERATED_ROOT/jniLibs"
STAGED_ASSET_ROOT="$GENERATED_ROOT/assets"
OUTPUT_ROOT="$BUILD_ROOT/outputs"
AUDITOR="$SCRIPT_DIR/android_audit.py"
BIONIC_COMPAT_DIR="$ROOT_DIR/vendor/raylib/android/bionic-compat"
BIONIC_COMPAT_FILE="$BIONIC_COMPAT_DIR/libpthread.so"
BUNDLETOOL="$ANDROID_DIR/tools/bundletool-all-1.18.1.jar"
RELEASE_SIGNING_CERT_FILE="$ANDROID_DIR/release-signing-cert.sha256"

if [[ ! -f "$TOOLCHAIN_FILE" ]]; then
    printf 'android: missing toolchain file: %s\n' "$TOOLCHAIN_FILE" >&2
    exit 1
fi
# This file is deliberately both shell-sourceable and Java Properties syntax.
# shellcheck disable=SC1090
source "$TOOLCHAIN_FILE"

SDK_ROOT=""
NDK_ROOT=""
BUILD_TOOLS_DIR=""
LLVM_BIN=""
READELF=""
IR_CLANG=""
GRADLE_BIN=""
VERSION_NAME=""
VERSION_CODE=""
DEBUG_APK=""
RELEASE_APK=""
RELEASE_AAB=""
RELEASE_CERT_SHA256=""
declare -a ADB=()

log() {
    printf 'android: %s\n' "$*"
}

die() {
    printf 'android: error: %s\n' "$*" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || die "required command is missing: $1"
}

require_file() {
    [[ -f "$1" ]] || die "required file is missing: $1"
}

property_value() {
    local file="$1"
    local key="$2"
    sed -n "s/^${key}[[:space:]]*=[[:space:]]*//p" "$file" | sed -n '1p'
}

validate_toolchain_contract() {
    local variable
    for variable in \
        ODIN_VERSION ODIN_COMMIT ODIN_BACKEND_LLVM_VERSION ODIN_IR_CLANG_VERSION JAVA_MAJOR GRADLE_VERSION GRADLE_DISTRIBUTION_SHA256 \
        GRADLE_WRAPPER_JAR_SHA256 AGP_VERSION MIN_SDK COMPILE_SDK TARGET_SDK \
        BUILD_TOOLS_VERSION NDK_VERSION ANDROID_ABIS RELEASE_APPLICATION_ID \
        DEBUG_APPLICATION_ID RAYLIB_VERSION RAYLIB_COMMIT RAYLIB_SOURCE_URL \
        RAYLIB_SOURCE_SHA256 RAYLIB_PATCH_SHA256 BIONIC_PTHREAD_SHIM_SHA256 \
        BUNDLETOOL_VERSION BUNDLETOOL_SHA256; do
        [[ -n "${!variable:-}" ]] || die "toolchain property is missing: $variable"
    done

    [[ "$ODIN_BACKEND_LLVM_VERSION" == "21.1.8" ]] || \
        die "ODIN_BACKEND_LLVM_VERSION must remain 21.1.8"
    [[ "$JAVA_MAJOR" == "17" ]] || die "JAVA_MAJOR must remain 17"
    [[ "$GRADLE_VERSION" == "8.14.3" ]] || die "GRADLE_VERSION must remain 8.14.3"
    [[ "$AGP_VERSION" == "8.11.0" ]] || die "AGP_VERSION must remain 8.11.0"
    [[ "$MIN_SDK" == "28" ]] || die "MIN_SDK must remain 28"
    [[ "$COMPILE_SDK" == "35" ]] || die "COMPILE_SDK must remain 35"
    [[ "$TARGET_SDK" == "35" ]] || die "TARGET_SDK must remain 35"
    [[ "$BUILD_TOOLS_VERSION" == "35.0.0" ]] || die "BUILD_TOOLS_VERSION must remain 35.0.0"
    [[ "$NDK_VERSION" == "28.2.13676358" ]] || die "NDK_VERSION must remain 28.2.13676358"
    [[ "$ANDROID_ABIS" == "arm64-v8a,armeabi-v7a,x86_64" ]] || \
        die "ANDROID_ABIS must be exactly arm64-v8a,armeabi-v7a,x86_64"
    [[ "$RAYLIB_VERSION" == "6.0" ]] || die "RAYLIB_VERSION must remain 6.0"
    [[ "$RELEASE_APPLICATION_ID" == *.odin.alpha ]] || die "release application id must end in .odin.alpha"
    [[ "$DEBUG_APPLICATION_ID" == "$RELEASE_APPLICATION_ID.debug" ]] || \
        die "debug application id must be $RELEASE_APPLICATION_ID.debug"

    for variable in \
        GRADLE_DISTRIBUTION_SHA256 GRADLE_WRAPPER_JAR_SHA256 \
        RAYLIB_SOURCE_SHA256 RAYLIB_PATCH_SHA256 BIONIC_PTHREAD_SHIM_SHA256 \
        BUNDLETOOL_SHA256; do
        [[ "${!variable}" =~ ^[0-9a-f]{64}$ ]] || die "$variable must be one lowercase SHA-256 digest"
    done
    [[ "$ODIN_VERSION" =~ ^dev-[0-9]{4}-[0-9]{2}$ ]] || \
        die "ODIN_VERSION must be one monthly source tag"
    [[ "$ODIN_COMMIT" =~ ^[0-9a-f]{40}$ ]] || die "ODIN_COMMIT must be one full Git commit"
    [[ "$RAYLIB_COMMIT" =~ ^[0-9a-f]{40}$ ]] || die "RAYLIB_COMMIT must be one full Git commit"
}

resolve_toolchain_paths() {
    if [[ -n "${ANDROID_SDK_ROOT:-}" && -n "${ANDROID_HOME:-}" && "$ANDROID_SDK_ROOT" != "$ANDROID_HOME" ]]; then
        die "ANDROID_SDK_ROOT and ANDROID_HOME point to different SDKs"
    fi
    SDK_ROOT="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-/opt/android-sdk}}"
    NDK_ROOT="${ODIN_ANDROID_NDK:-$SDK_ROOT/ndk/$NDK_VERSION}"
    BUILD_TOOLS_DIR="$SDK_ROOT/build-tools/$BUILD_TOOLS_VERSION"
    LLVM_BIN="$NDK_ROOT/toolchains/llvm/prebuilt/linux-x86_64/bin"
    READELF="$LLVM_BIN/llvm-readelf"
}

check_java() {
    local java_binary=""
    local javac_binary=""
    if [[ -n "${JAVA_HOME:-}" ]]; then
        java_binary="$JAVA_HOME/bin/java"
        javac_binary="$JAVA_HOME/bin/javac"
        [[ -x "$java_binary" && -x "$javac_binary" ]] || die "JAVA_HOME is not a complete JDK: $JAVA_HOME"
    else
        require_command java
        require_command javac
        java_binary="$(readlink -f "$(command -v java)")"
        javac_binary="$(readlink -f "$(command -v javac)")"
        JAVA_HOME="$(cd -- "$(dirname -- "$javac_binary")/.." && pwd)"
        export JAVA_HOME
    fi

    local java_major
    local javac_major
    java_major="$("$java_binary" -XshowSettings:properties -version 2>&1 | \
        sed -n 's/^[[:space:]]*java.specification.version = //p' | sed -n '1p')"
    javac_major="$("$javac_binary" -version 2>&1 | sed -n 's/^javac \([0-9][0-9]*\).*/\1/p' | sed -n '1p')"
    [[ "$java_major" == "$JAVA_MAJOR" && "$javac_major" == "$JAVA_MAJOR" ]] || \
        die "expected a JDK $JAVA_MAJOR runtime/compiler, found java=${java_major:-unknown} javac=${javac_major:-unknown}"
}

check_odin() {
    require_command odin
    local detected
    local version_prefix
    local reported_commit
    detected="$(odin version 2>&1 | sed -n '1p')"
    version_prefix="odin version $ODIN_VERSION:"
    [[ "$detected" == "$version_prefix"* ]] || \
        die "expected Odin source tag $ODIN_VERSION, found $detected"
    reported_commit="${detected#"$version_prefix"}"
    [[ "$reported_commit" =~ ^[0-9a-f]{7,40}$ && "$ODIN_COMMIT" == "$reported_commit"* ]] || \
        die "Odin reported revision ${reported_commit:-missing}, which is not a prefix of $ODIN_COMMIT"

    local odin_report
    local backend_version
    if ! odin_report="$(odin report 2>&1)"; then
        die "could not inspect the Odin backend: $odin_report"
    fi
    backend_version="$(sed -n 's/^[[:space:]]*Backend: LLVM //p' <<<"$odin_report" | sed -n '1p')"
    [[ "$backend_version" == "$ODIN_BACKEND_LLVM_VERSION" ]] || \
        die "expected Odin LLVM backend $ODIN_BACKEND_LLVM_VERSION, found ${backend_version:-unknown}"

    # The pinned Odin revision emits LLVM 21 IR, but its Android shared-library
    # path eagerly installs _odin_entry_point as DT_INIT on arm64 and selects
    # the host linker/GNU TLS on same-host x86_64. Clang 22 is the pinned,
    # forward-compatible IR consumer for all Android ABIs.
    IR_CLANG="${ODIN_ANDROID_IR_CLANG:-clang}"
    if [[ "$IR_CLANG" == */* ]]; then
        [[ -x "$IR_CLANG" ]] || die "ODIN_ANDROID_IR_CLANG is not executable: $IR_CLANG"
    else
        require_command "$IR_CLANG"
        IR_CLANG="$(command -v "$IR_CLANG")"
    fi
    local clang_report
    local clang_version
    clang_report="$("$IR_CLANG" --version 2>&1 | sed -n '1p')"
    clang_version="$(sed -n 's/^.*clang version \([^ ]*\).*$/\1/p' <<<"$clang_report")"
    [[ "$clang_version" == "$ODIN_IR_CLANG_VERSION" ]] || \
        die "expected Android IR consumer clang $ODIN_IR_CLANG_VERSION, found ${clang_version:-unknown} at $IR_CLANG"
}

print_missing_sdk_packages() {
    local -a packages=("$@")
    local sdkmanager="$SDK_ROOT/cmdline-tools/latest/bin/sdkmanager"
    if [[ ! -x "$sdkmanager" ]]; then
        sdkmanager="sdkmanager"
    fi
    printf 'android: error: missing required sdkmanager package(s) under %s:\n' "$SDK_ROOT" >&2
    local package
    for package in "${packages[@]}"; do
        printf 'android:   %s\n' "$package" >&2
    done
    printf 'android: install exactly the missing package(s) with:\n' >&2
    printf 'android:   %q' "$sdkmanager" >&2
    for package in "${packages[@]}"; do
        printf ' %q' "$package" >&2
    done
    printf '\n' >&2
    exit 1
}

check_sdk() {
    local -a missing=()
    if [[ ! -f "$SDK_ROOT/platform-tools/source.properties" || ! -x "$SDK_ROOT/platform-tools/adb" ]]; then
        missing+=("platform-tools")
    fi
    if [[ ! -f "$SDK_ROOT/platforms/android-$COMPILE_SDK/source.properties" || \
          ! -f "$SDK_ROOT/platforms/android-$COMPILE_SDK/android.jar" ]]; then
        missing+=("platforms;android-$COMPILE_SDK")
    fi
    if [[ ! -f "$BUILD_TOOLS_DIR/source.properties" ]]; then
        missing+=("build-tools;$BUILD_TOOLS_VERSION")
    fi
    if [[ ! -f "$NDK_ROOT/source.properties" ]]; then
        missing+=("ndk;$NDK_VERSION")
    fi
    if [[ "${#missing[@]}" -gt 0 ]]; then
        print_missing_sdk_packages "${missing[@]}"
    fi

    local platform_api
    platform_api="$(property_value "$SDK_ROOT/platforms/android-$COMPILE_SDK/source.properties" AndroidVersion.ApiLevel)"
    [[ "$platform_api" == "$COMPILE_SDK" ]] || die "SDK platform metadata is not API $COMPILE_SDK"

    local build_tools_revision
    build_tools_revision="$(property_value "$BUILD_TOOLS_DIR/source.properties" Pkg.Revision)"
    [[ "$build_tools_revision" == "$BUILD_TOOLS_VERSION" ]] || \
        die "expected build-tools $BUILD_TOOLS_VERSION, found ${build_tools_revision:-missing}"
    local tool
    for tool in aapt aapt2 apksigner zipalign; do
        [[ -x "$BUILD_TOOLS_DIR/$tool" ]] || die "missing build-tool executable: $BUILD_TOOLS_DIR/$tool"
    done

    local ndk_revision
    ndk_revision="$(property_value "$NDK_ROOT/source.properties" Pkg.Revision)"
    [[ "$ndk_revision" == "$NDK_VERSION" ]] || \
        die "expected NDK $NDK_VERSION, found ${ndk_revision:-missing} at $NDK_ROOT"
    for tool in llvm-ar llvm-nm llvm-objcopy llvm-readelf; do
        [[ -x "$LLVM_BIN/$tool" ]] || die "missing NDK LLVM tool: $LLVM_BIN/$tool"
    done
    [[ -x "$LLVM_BIN/aarch64-linux-android${MIN_SDK}-clang" ]] || \
        die "NDK lacks the API-$MIN_SDK arm64 clang driver"
    [[ -x "$LLVM_BIN/armv7a-linux-androideabi${MIN_SDK}-clang" ]] || \
        die "NDK lacks the API-$MIN_SDK armv7 clang driver"
    [[ -x "$LLVM_BIN/x86_64-linux-android${MIN_SDK}-clang" ]] || \
        die "NDK lacks the API-$MIN_SDK x86_64 clang driver"
    [[ -f "$NDK_ROOT/sources/android/native_app_glue/android_native_app_glue.c" ]] || \
        die "NDK lacks NativeActivity android_native_app_glue.c"
    [[ -f "$NDK_ROOT/toolchains/llvm/prebuilt/linux-x86_64/sysroot/usr/lib/aarch64-linux-android/$MIN_SDK/libandroid.so" ]] || \
        die "NDK lacks API-$MIN_SDK arm64 Android stubs"
    [[ -f "$NDK_ROOT/toolchains/llvm/prebuilt/linux-x86_64/sysroot/usr/lib/arm-linux-androideabi/$MIN_SDK/libandroid.so" ]] || \
        die "NDK lacks API-$MIN_SDK armv7 Android stubs"
    [[ -f "$NDK_ROOT/toolchains/llvm/prebuilt/linux-x86_64/sysroot/usr/lib/x86_64-linux-android/$MIN_SDK/libandroid.so" ]] || \
        die "NDK lacks API-$MIN_SDK x86_64 Android stubs"

    export ANDROID_HOME="$SDK_ROOT"
    export ANDROID_SDK_ROOT="$SDK_ROOT"
    export ODIN_ANDROID_SDK="$SDK_ROOT"
    export ODIN_ANDROID_NDK="$NDK_ROOT"
}

check_gradle_offline() {
    require_file "$ANDROID_DIR/gradlew"
    require_file "$ANDROID_DIR/gradle/wrapper/gradle-wrapper.jar"
    require_file "$ANDROID_DIR/gradle/wrapper/gradle-wrapper.properties"

    local wrapper_hash
    wrapper_hash="$(sha256sum "$ANDROID_DIR/gradle/wrapper/gradle-wrapper.jar" | awk '{print $1}')"
    [[ "$wrapper_hash" == "$GRADLE_WRAPPER_JAR_SHA256" ]] || die "Gradle wrapper JAR checksum mismatch"
    grep -Fq "gradle-$GRADLE_VERSION-all.zip" "$ANDROID_DIR/gradle/wrapper/gradle-wrapper.properties" || \
        die "Gradle wrapper version is not pinned to $GRADLE_VERSION"
    grep -Fq "distributionSha256Sum=$GRADLE_DISTRIBUTION_SHA256" \
        "$ANDROID_DIR/gradle/wrapper/gradle-wrapper.properties" || \
        die "Gradle wrapper distribution checksum is not pinned"

    local gradle_user_home
    gradle_user_home="${GRADLE_USER_HOME:-$HOME/.gradle}"
    local completed_distribution
    completed_distribution="$(find "$gradle_user_home/wrapper/dists/gradle-$GRADLE_VERSION-all" \
        -type f -name "gradle-$GRADLE_VERSION-all.zip.ok" -print -quit 2>/dev/null || true)"
    [[ -n "$completed_distribution" ]] || \
        die "Gradle $GRADLE_VERSION distribution is not completely cached under $gradle_user_home; the wrapper may not use the network"
    local distribution_root
    distribution_root="$(dirname -- "$completed_distribution")"
    GRADLE_BIN="$distribution_root/gradle-$GRADLE_VERSION/bin/gradle"
    [[ -x "$GRADLE_BIN" ]] || \
        die "completed Gradle $GRADLE_VERSION cache lacks its executable distribution"
    find "$gradle_user_home/caches/modules-2/files-2.1/com.android.tools.build/gradle/$AGP_VERSION" \
        -type f -name "gradle-$AGP_VERSION.jar" -print -quit 2>/dev/null | grep -q . || \
        die "Android Gradle Plugin $AGP_VERSION is not cached under $gradle_user_home"

    local gradle_report
    if ! gradle_report="$(cd "$ANDROID_DIR" && "$GRADLE_BIN" --offline --no-daemon --version 2>&1)"; then
        die "cached Gradle distribution failed in offline mode: $gradle_report"
    fi
    grep -Eq "^Gradle ${GRADLE_VERSION//./\\.}$" <<<"$gradle_report" || \
        die "offline wrapper did not launch Gradle $GRADLE_VERSION"
    if ! gradle_report="$(cd "$ANDROID_DIR" && \
        "$GRADLE_BIN" --offline --no-daemon --warning-mode=all :app:tasks 2>&1)"; then
        printf '%s\n' "$gradle_report" >&2
        die "pinned AGP project cannot configure offline; explicitly provision the pinned cache with android/gradlew -p android --no-daemon :app:tasks"
    fi
}

check_bundletool() {
    require_file "$BUNDLETOOL"
    local bundletool_hash
    bundletool_hash="$(sha256sum "$BUNDLETOOL" | awk '{print $1}')"
    [[ "$bundletool_hash" == "$BUNDLETOOL_SHA256" ]] || die "pinned bundletool checksum mismatch"
}

check_vendor_and_inputs() {
    require_command sha256sum
    require_command python3
    require_file "$AUDITOR"
    require_file "$ROOT_DIR/LICENSE"
    require_file "$ROOT_DIR/NOTICE"
    require_file "$ROOT_DIR/vendor/raylib/LICENSE"
    require_file "$ROOT_DIR/vendor/raylib/android/PROVENANCE.md"
    require_file "$ROOT_DIR/vendor/raylib/android/SHA256SUMS"
    require_file "$ROOT_DIR/vendor/raylib/android/raylib-6.0-arch-rogue.patch"
    require_file "$BIONIC_COMPAT_FILE"
    [[ -d "$ROOT_DIR/assets" ]] || die "canonical assets directory is missing"
    if find "$ROOT_DIR/assets" -type l -print -quit | grep -q .; then
        die "canonical assets contain a symbolic link"
    fi

    grep -Fq "$RAYLIB_COMMIT" "$ROOT_DIR/vendor/raylib/android/PROVENANCE.md" || \
        die "raylib provenance does not record commit $RAYLIB_COMMIT"
    grep -Fq "$RAYLIB_SOURCE_SHA256" "$ROOT_DIR/vendor/raylib/android/PROVENANCE.md" || \
        die "raylib provenance does not record the pinned source checksum"
    local patch_hash
    patch_hash="$(sha256sum "$ROOT_DIR/vendor/raylib/android/raylib-6.0-arch-rogue.patch" | awk '{print $1}')"
    [[ "$patch_hash" == "$RAYLIB_PATCH_SHA256" ]] || die "raylib Android patch checksum mismatch"
    grep -Fq "$RAYLIB_PATCH_SHA256" "$ROOT_DIR/vendor/raylib/android/PROVENANCE.md" || \
        die "raylib provenance does not record the pinned patch checksum"
    (
        cd "$ROOT_DIR/vendor/raylib/android"
        sha256sum -c SHA256SUMS
    )
    local shim_hash
    shim_hash="$(sha256sum "$BIONIC_COMPAT_FILE" | awk '{print $1}')"
    [[ "$shim_hash" == "$BIONIC_PTHREAD_SHIM_SHA256" ]] || die "Bionic pthread linker-script checksum mismatch"

    python3 "$AUDITOR" archive \
        --file "$ROOT_DIR/vendor/raylib/android/arm64-v8a/libraylib.a" \
        --abi arm64-v8a \
        --readelf "$READELF"
    python3 "$AUDITOR" archive \
        --file "$ROOT_DIR/vendor/raylib/android/armeabi-v7a/libraylib.a" \
        --abi armeabi-v7a \
        --readelf "$READELF"
    python3 "$AUDITOR" archive \
        --file "$ROOT_DIR/vendor/raylib/android/x86_64/libraylib.a" \
        --abi x86_64 \
        --readelf "$READELF"
    check_bundletool
}

normalize_fingerprint() {
    tr '[:upper:]' '[:lower:]' <<<"$1" | tr -cd '0-9a-f'
}

check_release_signing() {
    require_command keytool
    require_file "$RELEASE_SIGNING_CERT_FILE"

    # Keep existing Python-era release environments working while presenting
    # conventional names to Gradle and the Odin packaging path.
    ARCH_ROGUE_ANDROID_STORE_PASSWORD="${ARCH_ROGUE_ANDROID_STORE_PASSWORD:-${ARCH_ROGUE_ANDROID_KEYSTORE_PASSWD:-}}"
    ARCH_ROGUE_ANDROID_KEY_ALIAS="${ARCH_ROGUE_ANDROID_KEY_ALIAS:-${ARCH_ROGUE_ANDROID_KEYALIAS:-}}"
    ARCH_ROGUE_ANDROID_KEY_PASSWORD="${ARCH_ROGUE_ANDROID_KEY_PASSWORD:-${ARCH_ROGUE_ANDROID_KEYALIAS_PASSWD:-}}"
    export ARCH_ROGUE_ANDROID_STORE_PASSWORD ARCH_ROGUE_ANDROID_KEY_ALIAS \
        ARCH_ROGUE_ANDROID_KEY_PASSWORD

    local variable
    for variable in \
        ARCH_ROGUE_ANDROID_KEYSTORE \
        ARCH_ROGUE_ANDROID_STORE_PASSWORD \
        ARCH_ROGUE_ANDROID_KEY_ALIAS \
        ARCH_ROGUE_ANDROID_KEY_PASSWORD; do
        [[ -n "${!variable:-}" ]] || die "release signing variable is missing: $variable"
    done

    RELEASE_CERT_SHA256="$(tr -d '\r\n' < "$RELEASE_SIGNING_CERT_FILE")"
    [[ "$RELEASE_CERT_SHA256" =~ ^[0-9a-f]{64}$ ]] || \
        die "committed Android release certificate fingerprint is invalid: $RELEASE_SIGNING_CERT_FILE"

    require_file "$ARCH_ROGUE_ANDROID_KEYSTORE"
    ARCH_ROGUE_ANDROID_KEYSTORE="$(cd -- "$(dirname -- "$ARCH_ROGUE_ANDROID_KEYSTORE")" && pwd)/$(basename -- "$ARCH_ROGUE_ANDROID_KEYSTORE")"
    export ARCH_ROGUE_ANDROID_KEYSTORE

    local key_report
    if ! key_report="$(keytool -list -v \
        -keystore "$ARCH_ROGUE_ANDROID_KEYSTORE" \
        -storepass:env ARCH_ROGUE_ANDROID_STORE_PASSWORD \
        -alias "$ARCH_ROGUE_ANDROID_KEY_ALIAS" 2>&1)"; then
        die "release keystore/alias validation failed: $key_report"
    fi
    local actual_fingerprint
    actual_fingerprint="$(sed -n 's/^[[:space:]]*SHA256: //p' <<<"$key_report" | sed -n '1p')"
    actual_fingerprint="$(normalize_fingerprint "$actual_fingerprint")"
    [[ "$actual_fingerprint" == "$RELEASE_CERT_SHA256" ]] || \
        die "release keystore certificate does not match the committed release certificate fingerprint"
}

load_version_metadata() {
    mkdir -p "$GENERATED_ROOT"
    python3 "$AUDITOR" version \
        --source "$ROOT_DIR/src/main.odin" \
        --version-file "$ANDROID_DIR/version-code.properties" \
        --output "$GENERATED_ROOT/version.properties"
    VERSION_NAME="$(property_value "$GENERATED_ROOT/version.properties" versionName)"
    VERSION_CODE="$(property_value "$GENERATED_ROOT/version.properties" versionCode)"
    [[ -n "$VERSION_NAME" && "$VERSION_CODE" =~ ^[1-9][0-9]*$ ]] || die "generated version metadata is incomplete"
    DEBUG_APK="$OUTPUT_ROOT/archrogue-$VERSION_NAME-android-debug.apk"
    RELEASE_APK="$OUTPUT_ROOT/archrogue-$VERSION_NAME-android-release.apk"
    RELEASE_AAB="$OUTPUT_ROOT/archrogue-$VERSION_NAME-android-release.aab"
}

preflight() {
    local mode="${1:-build}"
    case "$mode" in
        build|release|install|audit) ;;
        *) die "unknown preflight mode: $mode" ;;
    esac
    [[ "$(uname -s)" == "Linux" ]] || die "the pinned Odin Android toolchain currently requires Linux"
    [[ "$(uname -m)" == "x86_64" ]] || die "NDK r28c/Odin preflight currently requires an x86_64 Linux host"
    require_command sed
    require_command grep
    require_command find
    require_command awk
    require_command readlink
    require_command sha256sum

    validate_toolchain_contract
    resolve_toolchain_paths
    check_java
    check_sdk
    check_vendor_and_inputs
    if [[ "$mode" != "audit" ]]; then
        check_odin
    fi
    if [[ "$mode" == "release" ]]; then
        check_release_signing
    fi
    load_version_metadata
    if [[ "$mode" != "audit" ]]; then
        check_gradle_offline
    fi
    if [[ "$mode" == "audit" ]]; then
        log "audit preflight passed: JDK $JAVA_MAJOR, SDK $COMPILE_SDK, NDK $NDK_VERSION, version $VERSION_NAME ($VERSION_CODE)"
    else
        log "preflight passed: Odin $ODIN_VERSION, JDK $JAVA_MAJOR, SDK $COMPILE_SDK, NDK $NDK_VERSION, version $VERSION_NAME ($VERSION_CODE)"
    fi
}

clean_and_stage() {
    log "removing stale Android generated/package outputs"
    rm -rf "$GENERATED_ROOT" "$ANDROID_DIR/app/build" "$OUTPUT_ROOT"
    mkdir -p \
        "$JNI_ROOT/arm64-v8a" \
        "$JNI_ROOT/armeabi-v7a" \
        "$JNI_ROOT/x86_64" \
        "$STAGED_ASSET_ROOT/assets" \
        "$STAGED_ASSET_ROOT/licenses" \
        "$OUTPUT_ROOT"
    load_version_metadata

    log "staging canonical assets without changing their assets/... runtime paths"
    cp -a "$ROOT_DIR/assets/." "$STAGED_ASSET_ROOT/assets/"
    install -m 0644 "$ROOT_DIR/LICENSE" "$STAGED_ASSET_ROOT/licenses/ARCH_ROGUE_LICENSE.txt"
    install -m 0644 "$ROOT_DIR/NOTICE" "$STAGED_ASSET_ROOT/licenses/ARCH_ROGUE_NOTICE.txt"
    install -m 0644 "$ROOT_DIR/vendor/raylib/LICENSE" "$STAGED_ASSET_ROOT/licenses/RAYLIB_LICENSE.txt"
    if find "$GENERATED_ROOT" -type l -print -quit | grep -q .; then
        die "Android staging unexpectedly contains a symbolic link"
    fi
}

build_native_from_ir() {
    local abi="$1"
    local output="$2"
    local mode="$3"
    local odin_target=""
    local target_triple=""
    local ndk_triple=""
    case "$abi" in
        arm64-v8a)
            odin_target="linux_arm64"
            target_triple="aarch64-linux-android"
            ndk_triple="aarch64-linux-android"
            ;;
        armeabi-v7a)
            odin_target="linux_arm32"
            target_triple="armv7a-linux-androideabi"
            ndk_triple="armv7a-linux-androideabi"
            ;;
        x86_64)
            odin_target="linux_amd64"
            target_triple="x86_64-linux-android"
            ndk_triple="x86_64-linux-android"
            ;;
        *) die "unsupported Android ABI: $abi" ;;
    esac

    local ir_root="$GENERATED_ROOT/odin-ir/$abi"
    local game_object="$ir_root/archrogue.o"
    local glue_object="$ir_root/android_native_app_glue.o"
    local ndk_driver="$LLVM_BIN/${ndk_triple}${MIN_SDK}-clang"
    local glue_source="$NDK_ROOT/sources/android/native_app_glue/android_native_app_glue.c"
    local glue_include="$NDK_ROOT/sources/android/native_app_glue"
    local raylib_archive="$ROOT_DIR/vendor/raylib/android/$abi/libraylib.a"
    local -a odin_optimization=()
    local -a ir_codegen=()
    if [[ "$mode" == "debug" ]]; then
        odin_optimization=(-debug)
        ir_codegen=(-O0 -g)
    else
        odin_optimization=(-o:speed)
        ir_codegen=(-O2)
    fi

    rm -rf "$ir_root"
    mkdir -p "$ir_root"
    log "emitting single-module Odin Android LLVM IR: $abi"
    if ! odin build "$ROOT_DIR/src" \
        "-target:$odin_target" \
        -subtarget:android \
        "-minimum-os-version:$MIN_SDK" \
        -build-mode:llvm-ir \
        -reloc-mode:pic \
        -stack-protector:strong \
        -define:RAYLIB_ANDROID=true \
        -use-single-module \
        "-out:$ir_root" \
        -vet \
        "${odin_optimization[@]}"; then
        return 1
    fi

    local ir_file
    ir_file="$(single_output "$ir_root" "*.ll")"
    grep -Fq "target triple = \"$target_triple\"" "$ir_file" || \
        die "Odin $abi IR does not carry the Android target triple $target_triple"

    # The API-28 contract requires emulated TLS. Pinned Clang consumes Odin's
    # LLVM 21 module and lowers its thread-local context without GNU TLS. LLVM-IR
    # mode also emits a normal C main wrapper rather than the eager DT_INIT used
    # by Odin's arm64 shared-library path; raylib calls main from android_main
    # only after NativeActivity has supplied its android_app pointer.
    log "lowering Odin IR with Android emulated TLS: $abi"
    if ! "$IR_CLANG" \
        "--target=${target_triple}$MIN_SDK" \
        -x ir \
        -fPIC \
        -femulated-tls \
        -Wno-override-module \
        "${ir_codegen[@]}" \
        -c "$ir_file" \
        -o "$game_object"; then
        return 1
    fi
    local unresolved
    unresolved="$("$LLVM_BIN/llvm-nm" -u "$game_object")"
    if grep -Eq '(^|[[:space:]])__tls_get_addr$' <<<"$unresolved"; then
        die "$abi IR lowering retained unsupported GNU TLS"
    fi
    grep -Eq '(^|[[:space:]])__emutls_get_address$' <<<"$unresolved" || \
        die "$abi IR lowering did not produce Android emulated TLS"

    if [[ "$abi" == "armeabi-v7a" ]]; then
        # Pinned Odin emits its private i128 conversion helper as the global
        # compiler-rt name __fixunsdfdi. ARM EABI also requires the NDK's
        # __aeabi_d2ulz implementation, whose archive member correctly defines
        # __fixunsdfdi; localize Odin's helper so both implementations can coexist
        # and all Odin-internal references continue resolving to their own body.
        "$LLVM_BIN/llvm-nm" -g --defined-only "$game_object" | \
            grep -Eq '(^|[[:space:]])__fixunsdfdi$' || \
            die "$abi Odin object no longer exposes the expected __fixunsdfdi workaround target"
        log "localizing pinned Odin ARM32 __fixunsdfdi helper"
        if ! "$LLVM_BIN/llvm-objcopy" --localize-symbol __fixunsdfdi "$game_object"; then
            return 1
        fi
        if "$LLVM_BIN/llvm-nm" -g --defined-only "$game_object" | \
            grep -Eq '(^|[[:space:]])__fixunsdfdi$'; then
            die "$abi Odin __fixunsdfdi helper remained global after localization"
        fi
    fi

    if ! "$ndk_driver" \
        -c "$glue_source" \
        "-I$glue_include" \
        -o "$glue_object"; then
        return 1
    fi

    log "linking deferred-entry NDK NativeActivity library: $abi"
    if ! "$ndk_driver" \
        "$game_object" \
        "$glue_object" \
        "$raylib_archive" \
        "-L$BIONIC_COMPAT_DIR" \
        -Wl,--wrap=fopen \
        -landroid \
        -llog \
        -lEGL \
        -lGLESv2 \
        -lOpenSLES \
        -latomic \
        -ldl \
        -lm \
        -lpthread \
        -lc \
        -Wl,-z,max-page-size=16384 \
        -Wl,-z,common-page-size=16384 \
        -Wl,-z,relro \
        -Wl,-z,now \
        -Wl,-z,noexecstack \
        -Wl,--no-undefined \
        -Wl,-soname,libmain.so \
        -shared \
        -o "$output"; then
        return 1
    fi
}

build_native() {
    local abi="$1"
    local mode="$2"
    local output="$JNI_ROOT/$abi/libmain.so"

    rm -f "$output"
    log "building Odin Android native library: $abi"
    if ! build_native_from_ir "$abi" "$output" "$mode"; then
        rm -f "$output"
        die "pinned Odin/Clang $abi Android IR bridge failed; no APK was packaged"
    fi

    if ! python3 "$AUDITOR" native --file "$output" --abi "$abi" --readelf "$READELF"; then
        rm -f "$output"
        die "Android ELF audit failed for $abi"
    fi
}

build_all_native() {
    local mode="$1"
    build_native arm64-v8a "$mode"
    build_native armeabi-v7a "$mode"
    build_native x86_64 "$mode"
}

run_gradle() {
    [[ -n "$GRADLE_BIN" && -x "$GRADLE_BIN" ]] || die "offline Gradle binary was not established by preflight"
    (
        cd "$ANDROID_DIR"
        "$GRADLE_BIN" --offline --no-daemon --stacktrace --warning-mode=all "$@"
    )
}

single_output() {
    local directory="$1"
    local pattern="$2"
    local -a matches=()
    mapfile -t matches < <(find "$directory" -type f -name "$pattern" -print | sort)
    [[ "${#matches[@]}" -eq 1 ]] || die "expected one $pattern under $directory, found ${#matches[@]}"
    printf '%s\n' "${matches[0]}"
}

audit_apk() {
    local apk="$1"
    local package_id="$2"
    local expected_cert="${3:-}"
    local -a cert_args=()
    if [[ -n "$expected_cert" ]]; then
        cert_args=(--expected-cert "$expected_cert")
    fi
    python3 "$AUDITOR" apk \
        --file "$apk" \
        --root "$ROOT_DIR" \
        --readelf "$READELF" \
        --build-tools "$BUILD_TOOLS_DIR" \
        --expected-package "$package_id" \
        --version-name "$VERSION_NAME" \
        --version-code "$VERSION_CODE" \
        "${cert_args[@]}"
}

audit_aab() {
    local bundle="$1"
    python3 "$AUDITOR" aab \
        --file "$bundle" \
        --root "$ROOT_DIR" \
        --readelf "$READELF" \
        --bundletool "$BUNDLETOOL" \
        --bundletool-sha256 "$BUNDLETOOL_SHA256" \
        --expected-package "$RELEASE_APPLICATION_ID" \
        --version-name "$VERSION_NAME" \
        --version-code "$VERSION_CODE" \
        --expected-cert "$RELEASE_CERT_SHA256"
}

build_debug() {
    preflight build
    clean_and_stage
    build_all_native debug
    log "packaging debug APK with Gradle in offline mode"
    run_gradle :app:assembleDebug
    local gradle_apk
    gradle_apk="$(single_output "$ANDROID_DIR/app/build/outputs/apk/debug" '*.apk')"
    install -m 0644 "$gradle_apk" "$DEBUG_APK"
    audit_apk "$DEBUG_APK" "$DEBUG_APPLICATION_ID"
    log "validated debug APK: $DEBUG_APK"
}

build_release() {
    preflight release
    clean_and_stage
    build_all_native release
    log "packaging signed alpha release APK and AAB with Gradle in offline mode"
    run_gradle :app:assembleRelease :app:bundleRelease
    local gradle_apk
    local gradle_aab
    gradle_apk="$(single_output "$ANDROID_DIR/app/build/outputs/apk/release" '*.apk')"
    gradle_aab="$(single_output "$ANDROID_DIR/app/build/outputs/bundle/release" '*.aab')"
    install -m 0644 "$gradle_apk" "$RELEASE_APK"
    install -m 0644 "$gradle_aab" "$RELEASE_AAB"
    audit_apk "$RELEASE_APK" "$RELEASE_APPLICATION_ID" "$RELEASE_CERT_SHA256"
    audit_aab "$RELEASE_AAB"
    log "validated release APK: $RELEASE_APK"
    log "validated release AAB: $RELEASE_AAB"
}

resolve_adb() {
    local adb="$SDK_ROOT/platform-tools/adb"
    [[ -x "$adb" ]] || die "adb is missing from the pinned platform-tools package"
    if [[ -n "${ANDROID_SERIAL:-}" ]]; then
        ADB=("$adb" -s "$ANDROID_SERIAL")
        return
    fi
    local -a devices=()
    mapfile -t devices < <("$adb" devices | awk 'NR > 1 && $2 == "device" {print $1}')
    [[ "${#devices[@]}" -eq 1 ]] || die "set ANDROID_SERIAL or connect exactly one ready Android device"
    ADB=("$adb" -s "${devices[0]}")
}

install_debug() {
    build_debug
    resolve_adb
    local device_abis
    device_abis="$("${ADB[@]}" shell getprop ro.product.cpu.abilist | tr -d '\r')"
    if [[ ",$device_abis," != *,arm64-v8a,* && ",$device_abis," != *,armeabi-v7a,* && ",$device_abis," != *,x86_64,* ]]; then
        die "device ABI list is unsupported by the APK: $device_abis"
    fi
    log "installing $DEBUG_APPLICATION_ID"
    "${ADB[@]}" install --no-streaming -r "$DEBUG_APK"
    local package_report
    package_report="$("${ADB[@]}" shell dumpsys package "$DEBUG_APPLICATION_ID" | tr -d '\r')"
    grep -Eq "versionCode=${VERSION_CODE}([[:space:]]|$)" <<<"$package_report" || \
        die "installed package versionCode does not match $VERSION_CODE"
    grep -Fq "versionName=$VERSION_NAME" <<<"$package_report" || \
        die "installed package versionName does not match $VERSION_NAME"
    "${ADB[@]}" shell am start -W -n "$DEBUG_APPLICATION_ID/org.archrogue.archrogue.odin.ArchRogueActivity"
}

detect_apk_package() {
    local apk="$1"
    "$BUILD_TOOLS_DIR/aapt" dump badging "$apk" | \
        sed -n "s/^package: name='\([^']*\)'.*/\1/p" | sed -n '1p'
}

audit_existing() {
    preflight audit
    local explicit="${1:-}"
    if [[ -n "$explicit" ]]; then
        require_file "$explicit"
        explicit="$(cd -- "$(dirname -- "$explicit")" && pwd)/$(basename -- "$explicit")"
        case "$explicit" in
            *.aab)
                check_release_signing
                audit_aab "$explicit"
                ;;
            *.apk)
                local package_id
                package_id="$(detect_apk_package "$explicit")"
                case "$package_id" in
                    "$DEBUG_APPLICATION_ID")
                        audit_apk "$explicit" "$DEBUG_APPLICATION_ID"
                        ;;
                    "$RELEASE_APPLICATION_ID")
                        check_release_signing
                        audit_apk "$explicit" "$RELEASE_APPLICATION_ID" "$RELEASE_CERT_SHA256"
                        ;;
                    *) die "APK package id is not an Arch Rogue Odin alpha id: ${package_id:-missing}" ;;
                esac
                ;;
            *) die "audit input must be an APK or AAB: $explicit" ;;
        esac
        return
    fi

    local audited=0
    if [[ -f "$DEBUG_APK" ]]; then
        audit_apk "$DEBUG_APK" "$DEBUG_APPLICATION_ID"
        audited=1
    fi
    if [[ -f "$RELEASE_APK" || -f "$RELEASE_AAB" ]]; then
        check_release_signing
        [[ -f "$RELEASE_APK" ]] || die "release APK is missing beside release AAB"
        [[ -f "$RELEASE_AAB" ]] || die "release AAB is missing beside release APK"
        audit_apk "$RELEASE_APK" "$RELEASE_APPLICATION_ID" "$RELEASE_CERT_SHA256"
        audit_aab "$RELEASE_AAB"
        audited=1
    fi
    [[ "$audited" -eq 1 ]] || die "no deterministic Android artifacts found under $OUTPUT_ROOT"
}

usage() {
    cat <<'EOF'
usage: tools/android.sh <command> [artifact]

commands:
  preflight  verify the pinned offline toolchain, SDK packages, and vendor inputs
  debug      clean, build all three ABIs, package, and audit a debug APK
  release    clean, build all three ABIs, sign, package, and audit an APK and AAB
  install    build/audit debug, install it, verify metadata, and launch NativeActivity
  audit      re-audit deterministic outputs or one explicit APK/AAB
EOF
}

command="${1:-}"
if [[ $# -gt 0 ]]; then
    shift
fi
case "$command" in
    preflight)
        [[ $# -eq 0 ]] || die "preflight accepts no arguments"
        preflight build
        ;;
    debug)
        [[ $# -eq 0 ]] || die "debug accepts no arguments"
        build_debug
        ;;
    release)
        [[ $# -eq 0 ]] || die "release accepts no arguments"
        build_release
        ;;
    install)
        [[ $# -eq 0 ]] || die "install accepts no arguments"
        install_debug
        ;;
    audit)
        [[ $# -le 1 ]] || die "audit accepts at most one APK/AAB path"
        audit_existing "${1:-}"
        ;;
    -h|--help|help|"")
        usage
        ;;
    *)
        usage >&2
        die "unknown command: $command"
        ;;
esac
