# ![Arch Rogue](website/assets/title_logo.png)

Arch Rogue is a grim isometric action-RPG roguelike built with [Odin](https://odin-lang.org/) and [raylib](https://www.raylib.com/). It combines deterministic procedural dungeons, real-time combat, random loot, permanent consequences, and a seeded dark-fantasy story.

The active game now lives at the repository root. `src/`, `assets/`, `tests/`, `android/`, and `build.sh` are the canonical Odin project. The former Python/Pygame implementation is archived under `arch-rogue-python/`; it remains useful for archaeology and parity checks, but it is not an active development or runtime dependency.

## Downloads and platform status

Bleeding-edge prerelease builds are published on the [Arch Rogue download site](https://mattirk.github.io/arch-rogue/).

| Platform | Status |
| --- | --- |
| Linux | Available |
| Android | Available as a native Odin/raylib alpha build |
| Web (WebAssembly) | [Play in a browser](https://mattirk.github.io/arch-rogue/play/) using the exact audited release archive. Requires a current desktop Chromium-family or Firefox browser with WebGL2 |
| Windows | Deferred |
| macOS | Deferred |
| Steam / Steam Deck integration | In progress: the game-side Steamworks integration (achievements, offline queue, cloud-ready saves) is built; store release pending |
| Multiplayer | Deferred |

The public workflow deploys the same content-addressed web archive attached to each prerelease. The Brotli wire budget and immutable/no-cache policy are self-hosted contracts validated by `web-audit` and `web-serve`; GitHub Pages controls its own compression and cache headers, so those delivery claims are not applied to the Pages endpoint.

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
- The exact Odin tag, source commit, and LLVM backend recorded in root `toolchain.properties`, available as `odin`
- The normal Linux graphics, windowing, and audio development libraries required by raylib

`build.sh` verifies the ambient Odin executable before every compile, check, or test, so local builds cannot silently differ from CI/CD. At the current pin this requires Odin `dev-2026-07` at commit `301c287de90393608fb7c5b260210e1e67caf0fd`, built with LLVM `21.1.8`; a newer distro package is intentionally rejected. CI reads its `setup-odin` inputs from the same root contract and runs the same verifier.

The raylib 6.0 binding and checksum-pinned static libraries are included under `vendor/raylib/`; a separate raylib installation is not required. Root `toolchain.properties` owns project-wide Odin and raylib source pins, while `android/toolchain.properties` and `web/toolchain.properties` contain only platform-specific additions.

Run every command from the repository root. The wrapper also relocates itself correctly when invoked from another current directory.

```bash
./build.sh toolchain
./build.sh check
./build.sh test
./build.sh build
./build.sh run
./build.sh release
```

- `toolchain` verifies the exact Odin identity/backend and vendored Linux raylib archive without compiling.
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
src/                   active Odin package: shared runtime, simulation, UI, and platform entries
assets/                sole canonical game-ready art, audio, shaders, fonts, and manifests
tests/                 headless deterministic Odin tests plus repository/site contract tests
android/               pinned Gradle NativeActivity package and narrow Java platform shell
web/                   pinned Emscripten contract, browser shell, JS bridge, and RAF driver
tools/                 build, audit, asset verification, capture, smoke, and profiling tooling
tools/public-repo/     canonical workflows overlaid into the filtered public repository
vendor/raylib/         raylib 6.0 Odin binding and pinned Linux, Android, and Web archives
website/               GitHub Pages download-site source; CI stages the web build under play/
.github/workflows/     active CI entrypoints: private mirror automation or public release workflow
build/                 generated local artifacts and validation evidence; never canonical source
arch-rogue-python/     archived read-only Python/Pygame implementation for historical reference
build.sh               canonical Linux, Android, and Web command wrapper
```

The active Odin build must not read code or assets from `arch-rogue-python/`. `assets/` is the only canonical runtime art tree.

## Development notes

- Simulation uses a 60 Hz fixed timestep and seeded PCG streams. Rendering must not mutate simulation state.
- Simulation and content code remain raylib-free so the test package can run headlessly.
- Linux, native Android, and desktop WebAssembly/WebGL2 are the current release targets. The game-side Steam integration is built and a Steam release is being prepared; Windows, macOS, and multiplayer remain deferred.
- The project is still awaiting final human side-by-side visual parity signoff and broader physical-device Android retesting noted in `PARITY.md`.

## Licenses and notices

Arch Rogue source and binaries are distributed under the [Apache License 2.0](LICENSE). Required notices, bundled-dependency attribution, and the AI provenance/liability notice are in [NOTICE](NOTICE).

raylib 6.0 is bundled under the zlib/libpng license; its complete text is in [`vendor/raylib/LICENSE`](vendor/raylib/LICENSE), with Android archive provenance under `vendor/raylib/android/PROVENANCE.md`. Android packages include exact Arch Rogue and raylib license copies under their packaged `assets/licenses/` directory.

The **Arch Rogue** name and octahedron crest are trademarks of the project author and are not granted for derivative branding by Apache-2.0.

## Changelog

See `CHANGELOG.md` for release history and current unreleased work.
