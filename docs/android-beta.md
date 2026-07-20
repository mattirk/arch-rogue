# Arch Rogue Android Beta

Release **4.3.8** ships a landscape-only Android beta APK built from the same
Python/pygame-ce codebase as the desktop release. This document is the source
of truth for installing, building, and reporting issues with the beta.

## Install

1. Download `arch-rogue-v<version>-<sha>-android-debug.apk` from the latest
   GitHub Release.
2. On Android 9+ enable "Install unknown apps" for your browser/files app.
3. Open the APK and confirm the install.  The debug build is self-signed at
   install time; Android may warn about the unknown developer.
4. Launch **Arch Rogue**.  The game starts in landscape and stays there.

## Upgrade

- Install a newer APK over the older one.  Saves and options live in the app's
  private storage and survive upgrades.
- If a build is ever incompatible, the in-app `Load run` option is hidden and
  the previous run save is left untouched so a downgrade can recover it.

## Controls

- **Movement:** drag the lower-left analog stick. Its distance from center
  controls movement strength and it recenters immediately when released.
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
- **Left rail:** vertical HP/MP/Stamina bars plus a compact character summary
  when the display has enough room.
- **Menus:** tap rendered rows, choices, tabs, and cells directly. Supported
  horizontal/vertical swipes handle paging, tabs, and item actions without a
  permanent navigation strip.
- **Android Back:** closes the topmost hub, Quest panel, or submenu; from base
  gameplay it opens the existing exit-confirmation sheet and never silently
  commits a story-relic choice.

## Performance and render quality

Android defaults to **Performance** render quality. The game keeps the device's
full landscape aspect ratio but renders at no more than 540 pixels high, uploads
that smaller logical framebuffer, and lets SDL's accelerated GLES2 renderer scale
it to the physical display. The startup path rejects SDL's software renderer,
tries the packaged `opengles2` and `opengles` drivers, and only permits automatic
software fallback so a vendor failure remains launchable and visible in telemetry.
This avoids CPU-rendering every pixel of a 1080p/1440p phone or tablet while
preserving touch coordinates and safe-area insets.

The first Options row cycles the available tiers:

- **Performance · 540p cap** — supported phone baseline; mobile lighting and
  normal-map detail are tuned for the lowest steady rendering cost.
- **Balanced · 720p cap** — sharper output on faster phones and tablets.
- **Native · full resolution** — diagnostic/high-end mode; can be dramatically
  slower because Pygame's world remains CPU-rendered before presentation.

Older mobile options files migrate to Performance and disable generated normal
maps once. You can re-enable **Lighting detail** explicitly after confirming the
device remains smooth.

The 4.3.8 beta displays a small diagnostic line at the bottom of the game view:
`PERF <fps> <frame ms> | W <world ms> H <HUD ms> F <flip ms>`. It also emits a
full phase report every four seconds. Capture title-screen and active-gameplay
samples with:

```bash
adb logcat -c
adb logcat | grep ARCH_ROGUE_PERF
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

The APK appears in `bin/`. The build helper runs a source/spec preflight before
Buildozer and then inspects the finished APK, including every native extension
inside each ABI's nested Python bundle. `tools/build_android.sh release`
produces a release APK; set the `ARCH_ROGUE_ANDROID_KEYSTORE*` env vars (see the
script) to sign it.

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

The `Build & Release` workflow builds and uploads the debug APK on every push to
`master`, alongside the Windows, Linux, and macOS binaries.

## Known issues

- Safe-area insets are read through a PyJNIus bridge that may return zero on
  vendor builds that hide cutout data; the layout still renders correctly in
  the safe interior.
- The debug APK is not signed by a Google Play upload key; install it outside
  Play.  A signed release track is a 4.3.x goal.
- Performance and cutout behavior vary across devices. Performance mode is the
  supported baseline; report the `ARCH_ROGUE_PERF` display/title/gameplay lines,
  Android version, and device model with any issue.