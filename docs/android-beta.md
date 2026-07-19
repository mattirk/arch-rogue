# Arch Rogue Android Beta

Milestone **4.3.0** ships a landscape-only Android beta APK built from the same
Python/pygame-ce codebase as the desktop release.  This document is the source
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

- **World:** touch and drag inside the central viewport to move and aim.  The
  player walks toward your finger and stops within melee range.
- **Skills 1–6:** the six badges on the right rail.  Tap to fire; cooldowns and
  resource costs match the desktop action bar.
- **Interact / Pause:** bottom-right and top-right of the viewport.  Pause opens
  the same exit confirmation sheet as desktop Esc.
- **Left rail:** vertical HP/MP/Stamina bars, compact character summary, and
  Inventory / Character / Quest / Help buttons.
- **Menus:** tap rows directly, or use the on-screen Back / arrows / Select
  buttons at the bottom of every menu and overlay.
- **Android Back:** closes the topmost overlay, opens the pause sheet in
  gameplay, and never silently commits a story-relic choice.

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
python -m pip install -e .
python -m pip install buildozer cython
./tools/build_android.sh debug
```

The APK appears in `bin/`.  `tools/build_android.sh release` produces a release
APK; set the `ARCH_ROGUE_ANDROID_KEYSTORE*` env vars (see the script) to sign it.

## CI

The `Build & Release` workflow builds and uploads the debug APK on every push to
`master`, alongside the Windows, Linux, and macOS binaries.

## Known issues

- Safe-area insets are read through a PyJNIus bridge that may return zero on
  vendor builds that hide cutout data; the layout still renders correctly in
  the safe interior.
- The debug APK is not signed by a Google Play upload key; install it outside
  Play.  A signed release track is a 4.3.x goal.
- Performance and cutout behavior vary across devices; report frame timing and
  device model with any issue.