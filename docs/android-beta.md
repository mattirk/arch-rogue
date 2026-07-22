# Arch Rogue Android Build

As of release **4.3.17** the Android build is part of the mainline `master`
branch (it graduated from the `android-beta` branch). The same
Python/pygame-ce codebase produces both the desktop and the landscape-only
Android APK. This document is the source of truth for installing, building,
and reporting issues with the Android build.

## Install

1. Download `arch-rogue-v<version>-<sha>-android-release.apk` from the latest
   GitHub Release.
2. On Android 9+ enable "Install unknown apps" for your browser/files app.
3. Open the APK and confirm the install. The APK is signed during CI with the
   project's private update key; Android may still warn because it is installed
   outside Google Play.
4. Launch **Arch Rogue**. The game starts in landscape and stays there.

## Upgrade

Release 4.5.4 introduces a persistent signing certificate for public Android
builds. Install later APKs over 4.5.4 or newer; saves and options remain in the
app's private storage and survive the update.

Public CI APKs through 4.5.3 were mistakenly signed with a new ephemeral debug
key on every GitHub runner. Android correctly rejects a newer APK when its
certificate differs, usually showing only **App not installed**. No private key
from those destroyed runners exists with which to authorize an update. If the
installed copy came from one of those releases, uninstall **Arch Rogue** once,
then install 4.5.4. Uninstalling clears that installation's private saves and
options; subsequent signed-release upgrades preserve them.

To obtain Android's exact reason instead of the generic installer message, use:

```bash
adb install -r path/to/arch-rogue-v<version>-<sha>-android-release.apk
```

A pre-4.5.4 signer conflict reports
`INSTALL_FAILED_UPDATE_INCOMPATIBLE: Existing package ... signatures do not match
newer version`. If a build's save schema is ever incompatible instead, the
in-app `Load run` option is hidden and the previous save is left untouched so a
downgrade can recover it.

## Controls

- **Movement:** drag the enlarged lower-left analog stick. Its distance from
  center controls movement strength and it recenters immediately when released.
- **Aim:** touch or drag inside the central world viewport. World touch aims
  only; it can be held independently while moving with the stick or tapping a
  skill.
- **Skills 1–6:** tap the six badges on the right rail. Cooldowns and resource
  costs match the desktop action bar.
- **Interact:** tap the contextual bottom-right tooltip when it displays the
  `TAP` badge, such as `Open door`. Warning-only prompts are not buttons, and
  there is no permanent `USE` button.
- **Game menu:** tap the top-right list icon to pause the run and open the
  Inventory / Character / Quest / Exit game hub. Quest details are hidden from
  the normal gameplay HUD and open as a dedicated modal panel.
- **Left overlay:** the dungeon renders to the physical left edge beneath
  PixelLab-authored HP/MP/Stamina vessels and information cards. The cards show
  run/depth, floor theme, difficulty/modifier, and a compact character summary
  when space permits; touching a card never aims through it into the world.
- **Menus:** tap rendered rows, choices, tabs, and cells directly. Supported
  horizontal/vertical swipes handle paging, tabs, and item actions without a
  permanent navigation strip.
- **Android Back:** closes the topmost hub, Quest panel, or submenu; from base
  gameplay it opens the existing exit-confirmation sheet and never silently
  commits a story-relic choice.

## Performance and render quality

Android defaults to **Native** render quality, rendering at the device's full
physical resolution. The game keeps the device's full landscape aspect ratio
and lets SDL's accelerated GLES2 renderer scale the logical framebuffer to the
physical display. The startup path rejects SDL's software renderer, tries the
packaged `opengles2` and `opengles` drivers, and only permits automatic
software fallback so a vendor failure remains launchable and visible in
telemetry. The first Options row cycles to capped tiers for slower devices:

- **Performance · 540p cap** — supported phone baseline; mobile lighting and
  normal-map detail are tuned for the lowest steady rendering cost.
- **Balanced · 720p cap** — sharper output on faster phones and tablets.
- **Native · full resolution** — diagnostic/high-end mode; can be dramatically
  slower because Pygame's world remains CPU-rendered before presentation. When
  the accelerated GLES presenter is available, it now uses the same continuous
  quarter-resolution lighting as the capped tiers; the cheaper local-tint path
  remains only for software-renderer or context-loss fallback.

Option files from before 4.3.0 (schema < 6) migrate to Performance and disable
generated normal maps once to avoid a cold ARM cache spike. You can re-enable
**Lighting detail** explicitly after confirming the device remains smooth.

The on-device overlay shows a compact two-line summary at the bottom of the
game view:

```
PERF <fps> <frame_ms> | <logical_size> <renderer> A2:<alpha> N:<neon>
T <tick> U <update> W <world> H <hud> F <flip> A <audio> | L+<loads> B+<builds>
```

Every four seconds the game emits a full `ARCH_ROGUE_PERF` report through logcat.
Since 4.5.3 the report includes interval frame-time percentiles (p50/p95/max),
relative hitch counts, and the worst frame's dominant phase and detail cause
(reveals, rebuilds, recenters, patches, sprite loads/builds). Capture
title-screen and active-gameplay samples with:

```bash
adb logcat -c
adb logcat | grep ARCH_ROGUE_PERF
```

For a live rolling dashboard with FPS history, per-phase cost bars, jank
distribution, and worst-frame attribution, use the profiler tool:

```bash
python tools/profile_adb_live.py --serial <device_serial> --window 8 --no-color --raw
```

The first `ARCH_ROGUE_PERF display` line must show `accelerated=yes` and normally
`renderer=opengles2`. Later lines include logical/window/viewport dimensions,
all frame phases, entity counts, lighting state, and interval asset cache loads.
If Performance is still slow, include several complete lines plus the device
model and Android version in the report; do not infer the bottleneck from FPS
alone.

## Lifecycle

- **Home / recents / lock screen:** the run is saved atomically and the game
  pauses on the exit-confirmation sheet.  Audio focus is released until you
  choose **Cancel and return to game**.
- **Low memory:** caches are dropped; the active run is preserved.
- **Termination:** a final best-effort save is attempted.

## Build locally

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[android]"
./tools/build_android.sh debug
```

The local debug APK appears in `bin/` and is signed by that workstation's Android
debug key. It can update only APKs signed by the same key; it is not the public
release artifact.

The build helper runs a source/spec preflight and then inspects the finished APK,
including every native extension inside each ABI's nested Python bundle. An
official release build requires all four signing variables and refuses an
unsigned APK or a certificate other than the fingerprint committed in
`android/release-signing-cert.sha256`:

```bash
export ARCH_ROGUE_ANDROID_KEYSTORE=/secure/path/arch-rogue-release.keystore
export ARCH_ROGUE_ANDROID_KEYSTORE_PASSWD=<keystore-password>
export ARCH_ROGUE_ANDROID_KEYALIAS=<key-alias>
export ARCH_ROGUE_ANDROID_KEYALIAS_PASSWD=<key-password>
./tools/build_android.sh release
```

Keep the keystore and passwords private and backed up. Losing this key makes it
cryptographically impossible to update existing installations.

The checked-in local p4a recipe is deliberately requested as
`pygame==2.5.7`. Do **not** replace it with `pygame-ce` in `buildozer.spec`:
p4a has no recipe under that distribution name and pip may copy the build
host's x86_64 manylinux wheel into an ARM APK. If you previously used manual
staging hacks, start once with `buildozer android clean`; `src/main.py` is now
the maintained SDL2 bootstrap entry point.

To audit an existing APK without rebuilding it:

```bash
python tools/validate_android_apk.py \
  --source-dir src --spec buildozer.spec bin/<apk-name>.apk
```

To compare mobile CPU rendering tiers without an Android device, use the
fixed-step profiler. `--width` and `--height` are the physical device size; the
selected quality computes the same logical surface used by Android:

```bash
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy \
  .venv/bin/python tools/profile_game.py \
  --scenario crowd --mobile --mobile-quality performance \
  --width 2340 --height 1080 --frames 240
```

The dummy driver measures relative Python/SDL surface work, not Android's GPU,
SurfaceFlinger, scheduler, or thermal behavior. Use `adb shell top`, `dumpsys
meminfo`, and Perfetto for final device-side attribution.

## CI

The `Build & Release` workflow restores the dedicated release keystore from the
protected `android-release` GitHub Environment, builds a signed release APK,
verifies its certificate fingerprint, and uploads that exact audited file
alongside the Windows, Linux, and macOS binaries. The signed job is restricted to
`refs/heads/master`; `android-beta` and workflow dispatches targeting another ref
cannot access the update key.

Create an Environment named `android-release`, restrict its deployment branches
to protected `master`, enable required-reviewer protection, and define these
Environment secrets:

- `ARCH_ROGUE_ANDROID_KEYSTORE_BASE64` — base64-encoded keystore bytes
- `ARCH_ROGUE_ANDROID_KEYSTORE_PASSWD`
- `ARCH_ROGUE_ANDROID_KEYALIAS`
- `ARCH_ROGUE_ANDROID_KEYALIAS_PASSWD`

The workflow fails rather than falling back to a fresh debug signer when any
secret is absent. Encode the keystore without line wrapping before storing it,
for example `base64 -w 0 /secure/path/arch-rogue-release.keystore` on GNU/Linux.
The dedicated keystore must not be reused for routine debug builds; it remains
ignored by Git and must be backed up securely.

## Known issues

- Safe-area insets are read through a PyJNIus bridge that may return zero on
  vendor builds that hide cutout data; the layout still renders correctly in
  the safe interior.
- The APK is signed for stable sideloaded updates but is not distributed through
  Google Play. Install it outside Play and allow the browser/files app as an
  installation source.
- Performance and cutout behavior vary across devices. Performance mode is the
  supported baseline; report the `ARCH_ROGUE_PERF` display/title/gameplay lines,
  Android version, and device model with any issue.
