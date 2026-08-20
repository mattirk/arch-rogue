# ![Arch Rogue](website/assets/title_logo.png)

Arch Rogue is a grim isometric action-RPG roguelike built with [Odin](https://odin-lang.org/) and [raylib](https://www.raylib.com/). It combines deterministic procedural dungeons, real-time combat, random loot, permanent consequences, and a seeded dark-fantasy story.

The active game now lives at the repository root. `src/`, `assets/`, `tests/`, `android/`, and `build.sh` are the canonical Odin project. The former Python/Pygame implementation is archived under `arch-rogue-python/`; it remains useful for archaeology and parity checks, but it is not an active development or runtime dependency.

## Downloads and platform status

Bleeding-edge prerelease builds are published on the [Arch Rogue download site](https://mattirk.github.io/arch-rogue/).

| Platform | Status |
| --- | --- |
| Linux | Available |
| Android | Available as a native Odin/raylib alpha build |
| Windows | Deferred |
| macOS | Deferred |
| Steam / Steam Deck integration | Deferred |
| Multiplayer | Deferred |

This is an alpha release. Save formats are versioned and defensive, but gameplay, presentation, and platform contracts can still change before 6.0.

## Highlights

- Deterministic ten-depth runs with procedural rooms, corridors, doors, boss arenas, eight dungeon themes, dark floors, line-of-sight fog of war, and an isometric minimap.
- Five archetypes: Warden, Rogue, Arcanist, Acolyte, and Ranger.
- Fixed-step real-time combat with class kits, typed damage and statuses, elites, minibosses, five bosses, familiars, and a full discipline tree.
- Loot with rarity tiers, affixes, unidentified and cursed equipment, consumables, and thirteen named uniques.
- Traps, shrines, secrets, Shops, Bars, Gardens, Quest rooms, and the Hall of Unlost Echoes.
- A deterministic story engine with guests, relic choices, minigames, run consequences, and fifteen endings.
- Local save/resume, recovery-safe writes, persistent options, and the Chronicle run history.
- Authored PixelLab actor, world, UI, story, and effect art with point-sampled rendering.
- Keyboard/mouse and remappable gamepad input on Linux; native multi-touch, lifecycle, and semantic Back handling on Android.

See `PARITY.md` for the port ledger and `ARCHITECTURE.md` for design decisions, subsystem ownership, and hard boundaries.

## Build on Linux

### Requirements

- A Linux development host
- Bash
- Odin tag `dev-2026-07` at commit `301c287de90393608fb7c5b260210e1e67caf0fd`, available as `odin`
- The normal Linux graphics, windowing, and audio development libraries required by raylib

The raylib 6.0 binding and pinned static libraries are included under `vendor/raylib/`; a separate raylib installation is not required.

Run every command from the repository root. The wrapper also relocates itself correctly when invoked from another current directory.

```bash
./build.sh check
./build.sh test
./build.sh build
./build.sh run
./build.sh release
```

- `check` runs `odin check src -vet`.
- `test` runs the headless deterministic Odin test package with vetting enabled.
- `build` creates a debug executable at `build/archrogue`.
- `run` builds and starts the debug game.
- `release` creates an optimized executable at `build/archrogue`.

Additional Odin arguments may be appended after the command.

## Build for Android

Android is a native `NativeActivity` package using the same Odin/raylib game loop as Linux. It targets API 35, supports API 28 and newer, and packages `arm64-v8a`, `armeabi-v7a`, and `x86_64`.

The pinned Android toolchain requires JDK 17, Android build-tools 35.0.0, NDK `28.2.13676358`, and a populated offline Gradle/AGP cache. Start with preflight; it reports exact missing components.

```bash
./build.sh android-preflight
./build.sh android-debug
./build.sh android-install
./build.sh android-audit
./build.sh android-smoke --serial emulator-5554
```

A signed release APK and AAB require the signing environment documented in `android/README.md`:

```bash
./build.sh android-release
```

Android outputs are written under `build/android/`. See `android/README.md` for toolchain provisioning, application IDs, signing, AVD smoke testing, ABI auditing, and the NativeActivity/Back bridge.

## Repository layout

```text
src/                 Odin package and game entry point
assets/              canonical game-ready art, audio, shaders, and manifests
tests/               headless deterministic Odin tests
android/             pinned native Android Gradle package
tools/               asset verification, capture, profiling, and Android tooling
vendor/raylib/       pinned raylib 6.0 binding and platform archives
website/             download-site source and branding
arch-rogue-python/   archived legacy Python/Pygame source tree
build.sh             check, test, build, run, release, and Android wrapper
```

The active Odin build must not read code or assets from `arch-rogue-python/`. `assets/` is the only canonical runtime art tree.

## Development notes

- Simulation uses a 60 Hz fixed timestep and seeded PCG streams. Rendering must not mutate simulation state.
- Simulation and content code remain raylib-free so the test package can run headlessly.
- Linux and Android are the only current release targets. Do not imply support for deferred platforms in release notes or download copy.
- The project is still awaiting final human side-by-side visual parity signoff and broader physical-device Android retesting noted in `PARITY.md`.

## Licenses and notices

Arch Rogue source and binaries are distributed under the [Apache License 2.0](LICENSE). Required notices, bundled-dependency attribution, and the AI provenance/liability notice are in [NOTICE](NOTICE).

raylib 6.0 is bundled under the zlib/libpng license; its complete text is in [`vendor/raylib/LICENSE`](vendor/raylib/LICENSE), with Android archive provenance under `vendor/raylib/android/PROVENANCE.md`. Android packages include exact Arch Rogue and raylib license copies under their packaged `assets/licenses/` directory.

The **Arch Rogue** name and octahedron crest are trademarks of the project author and are not granted for derivative branding by Apache-2.0.

## Changelog

See `CHANGELOG.md` for release history and current unreleased work.
