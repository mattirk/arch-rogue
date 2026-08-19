# Arch Rogue Odin Android packaging

This directory is a native-first Android `NativeActivity` project. Gameplay and
the sole game loop remain Odin/raylib; a small custom Java activity owns Android
class-loader native-library loading and Back callbacks. Gradle compiles that
platform shell and packages prebuilt Odin `libmain.so` files, but it does not
compile gameplay code or invoke CMake. `../tools/android.sh` owns native
compilation, clean asset staging, signing gates, and final artifact audits.

## Pinned contract

`toolchain.properties` pins:

- Odin `dev-2026-07:301c287de`, built with LLVM `21.1.8`, and Clang `22.1.8` for the audited Android IR bridge
- Gradle `8.14.3` and Android Gradle Plugin `8.11.0`
- JDK major `17`
- `minSdk 28`, `compileSdk 35`, `targetSdk 35`
- Android build-tools `35.0.0`
- Android NDK `28.2.13676358` (r28c)
- raylib `6.0`, its source checksum, and all three Android archive checksums
- `arm64-v8a`, `armeabi-v7a`, and `x86_64` as the exact packaged ABI set and order

CI builds the `dev-2026-07` tag from source with LLVM 21 because its published
Linux archive was produced before the tag was finalized and reports the earlier
`ab0131c` nightly revision. Post-setup checks remain fail-closed on the full
`301c287de` source commit, compiler version, and LLVM `21.1.8` backend.

If preflight reports missing Android components, install exactly the package IDs
it prints. For the default `/opt/android-sdk` location the complete command is:

```bash
/opt/android-sdk/cmdline-tools/latest/bin/sdkmanager \
  "platform-tools" \
  "platforms;android-35" \
  "build-tools;35.0.0" \
  "ndk;28.2.13676358"
```

Ordinary builds always run Gradle with `--offline`; the Gradle 8.14.3
distribution and AGP 8.11.0 dependency graph must already be in
`GRADLE_USER_HOME`. No ordinary build downloads game or raylib dependencies.
One explicit network-enabled provisioning run may populate that pinned cache:

```bash
android/gradlew -p android --no-daemon :app:tasks
```

Afterward, `android-preflight` performs the same project configuration with
`--offline` and rejects any incomplete wrapper or AGP cache before compilation.
Ordinary build commands then invoke that verified cached Gradle binary directly,
so the wrapper has no opportunity to fetch a distribution during a build.

## Commands

Run from the repository root (the wrapper also works from another current directory):

```bash
./build.sh android-preflight
./build.sh android-debug
./build.sh android-release
./build.sh android-install
./build.sh android-audit [path/to/artifact.apk]
./build.sh android-smoke --serial emulator-5554
```

`android-debug` and `android-release` delete prior generated JNI/assets, Gradle
outputs, and deterministic handoff outputs before compiling all three ABIs in
contract order. A build is successful only after the final artifact auditor
passes. `android-smoke` installs that audited debug APK and drives the API-34
x86_64 AVD through Options entry, disabled-row non-mutation, an edge-gesture
Back, gameplay, multi-touch, background/foreground lifecycle,
force-stop/relaunch, and app-private Resume.
It checks logcat markers and writes screenshots plus `smoke.log` under
`build/android/smoke/`.

The alpha identities are deliberately isolated from the archived legacy
application and from each other:

- debug: `org.archrogue.archrogue.odin.alpha.debug`
- release: `org.archrogue.archrogue.odin.alpha`

The official unsuffixed identity is never produced by this project.

## Activity and Back bridge

`ArchRogueActivity` is the narrow Java platform seam. It loads `libmain.so`
through the activity class loader with `System.loadLibrary`, registers an
`OnBackInvokedCallback` on API 33+, and retains legacy `onBackPressed()` for
older Android versions. Both paths call the native JNI bridge and become the
same semantic `.back` intent used by keyboard/controller input. The final APK
checks packaged DEX for this activity contract, and every native slice must export
the JNI Back symbols, so a package cannot pass with an unwired Java callback.

## Versioning and assets

`versionName` is parsed from the single `VERSION` constant in `src/main.odin`.
`version-code.properties` contains the exact committed Android `versionCode`;
the build fails unless it matches the deterministic version mapping. Future
updates must commit a strictly larger value rather than silently deriving one.

The canonical root `assets/` tree is copied into the generated Android asset
root without flattening it. Thus `assets/ui/example.png` remains the
runtime `AAssetManager` path `assets/ui/example.png` and the APK ZIP entry is
`assets/assets/ui/example.png`. The package also contains:

- `assets/licenses/ARCH_ROGUE_LICENSE.txt`
- `assets/licenses/ARCH_ROGUE_NOTICE.txt`
- `assets/licenses/RAYLIB_LICENSE.txt`

The auditor compares every packaged asset byte-for-byte with the clean canonical
source and rejects missing, extra, stale, duplicated, or symlink-derived entries.

## Release signing

Local release packaging is impossible unless all four signing inputs are set:

```text
ARCH_ROGUE_ANDROID_KEYSTORE
ARCH_ROGUE_ANDROID_STORE_PASSWORD
ARCH_ROGUE_ANDROID_KEY_ALIAS
ARCH_ROGUE_ANDROID_KEY_PASSWORD
```

For cutover compatibility, the wrapper also accepts the existing
`ARCH_ROGUE_ANDROID_KEYSTORE_PASSWD`, `ARCH_ROGUE_ANDROID_KEYALIAS`, and
`ARCH_ROGUE_ANDROID_KEYALIAS_PASSWD` names and normalizes them internally.

`android/release-signing-cert.sha256` commits the one accepted public certificate
fingerprint. The shell preflight reads it directly, validates the configured alias
and actual certificate before Gradle runs, and checks the final APK/AAB signer
again. The fingerprint is public build metadata, not a fifth credential. Secrets
and keystores are never committed or copied into staging.

The public `android-release` Environment continues to use the existing secret
names from the Python build: `ARCH_ROGUE_ANDROID_KEYSTORE_BASE64`,
`ARCH_ROGUE_ANDROID_KEYSTORE_PASSWD`, `ARCH_ROGUE_ANDROID_KEYALIAS`, and
`ARCH_ROGUE_ANDROID_KEYALIAS_PASSWD`. The public workflow maps those values to
the Odin wrapper's local variable names, so the cutover requires no secret rename
or re-upload.

## raylib archives and Android compiler bridge

The checked-in raylib 6.0 archives are static, PIC, OpenGL ES 2.0 Android builds
for `arm64-v8a`, `armeabi-v7a`, and `x86_64`, in that exact order. Ordinary
builds checksum and inspect them; use `tools/rebuild_raylib_android.sh` only as
an explicit maintainer operation.

The pinned Odin compiler currently adds a desktop-style `-lpthread` argument to
the Linux-subtarget Android link even though Android pthread symbols live in
Bionic `libc`. A checksum-pinned linker script absorbs only that erroneous link
argument. The Android raylib binding and archive never link a standalone pthread
library, and the native/APK auditor rejects any `libpthread` dependency or host
GLIBC/X11 marker.

Odin `dev-2026-07:301c287de` has Android shared-library defects at the pinned
revision. Same-host `linux_amd64 -subtarget:android` can select the desktop linker
and emit GNU TLS, which Bionic does not provide. Direct shared mode can also
install `_odin_entry_point` as ELF `DT_INIT`, running game `main()` during
`NativeActivity` loading before raylib's `android_main` has received the
`android_app` pointer.

Every ABI therefore follows the same deferred-entry pipeline: Odin emits one
Android-targeted LLVM module, pinned Clang `22.1.8` consumes it with the API-28
baseline and emulated TLS, the NDK native-app glue is compiled, and the matching
NDK driver performs the final link. raylib `android_main` invokes the module's
normal C `main` wrapper only after `NativeActivity` initialization.

Preflight validates both compiler versions. The bridge rejects retained
`__tls_get_addr` and requires `__emutls_get_address`; final ELF/APK audits reject
`DT_INIT`, GLIBC/X11/pthread or other host contamination, unexpected
dependencies, missing packaged activity/DEX markers, and missing JNI Back
symbols. All three ABIs are mandatory and
pass the same strict audit. For ARMv7 specifically, the link localizes the pinned
Odin `__fixunsdfdi` before resolving the NDK compiler-rt archive.

Android app-private persistence uses Bionic pathname operations rather than
Odin's raw Linux syscall wrappers, preserving the existing synced temp/backup/
rename ordering under Android SELinux and seccomp. Persistence SHA-256 keeps the
same save format but now uses a local portable implementation instead of
`core:crypto/sha2`; it is tested against FIPS vectors and does not assume ARMv8
SHA2 instructions, preserving the ARMv7 baseline and translated x86_64 safety.

## Alpha.21 validation

The completed validation record is:

- `odin check src -vet` passes and `odin test tests -vet` passes all 357 tests.
- The three-ABI APK strict audit passes with API 35 target/API 28 minimum, exact
  ABI order, required packaged activity/DEX plus JNI Back symbols, and no
  `DT_INIT` or host contamination.
- Rebuilding the pinned raylib Android archives reproduces the committed
  checksums exactly.
- The API-34 x86_64 smoke passes Options entry, disabled-row non-mutation, an
  edge-gesture Back, gameplay, multi-touch, lifecycle background/resume,
  force-stop/relaunch, and app-private Resume.
- A forced ARM64-translation run starts and passes Options/Back.

Matti previously confirmed that an earlier ARM64 APK starts on a physical
Android device. The alpha.21 Options/gesture fixes still require physical
retesting; they are not claimed as physically confirmed here. ARMv7 compiles,
packages, and audits, but runtime testing was not possible because the current
AVD exposes no 32-bit ABI.
