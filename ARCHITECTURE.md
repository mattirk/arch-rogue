# Arch Rogue — Odin + raylib architecture

Milestone `6-odin` is the complete rewrite of Arch Rogue in **Odin + raylib**
and is now the canonical game. The repository root is the Odin project root:
active code and assets live in `src/` and `assets/`, while the former
Python/Pygame implementation is archived under `arch-rogue-python/` for
historical and parity reference only. The Odin build and runtime must not
depend on that archive. Same game, new engine — the visual identity (Pixellab
pixel-art sprites, isometric grim-fantasy look) carries over; the implementation
does not.

Versioning: the Odin game is the 6.x line (`6.0.0-alpha.N` through the parity
push and release-readiness work). The archived Python tree retains its historical
version metadata but is no longer an active development target.

## Decision log

- **2026-08-11 — Language: Odin** (Matti). Native performance, data-oriented
  style that fits a game sim, first-class raylib support: `vendor:raylib`
  ships with the compiler, precompiled — installing Odin is the whole
  toolchain setup.
- **2026-08-11 — raylib over SDL.** Considered Odin + SDL since pygame sits on
  SDL. Rejected: pygame's slowness is per-blit Python call overhead plus
  CPU-side surface compositing plus full-frame uploads — SDL itself was never
  the bottleneck, so "keeping SDL" carries nothing over (and in Odin, no code
  carries over anyway). Both SDL's GPU renderer and raylib composite batched
  sprites on the GPU; at our draw counts (a few thousand quads/frame) their
  performance difference is noise. SDL is a *platform layer* — image decoding,
  fonts, audio mixing, sprite batching, camera math would all be ours to
  build; raylib ships them. raylib also gives us day-one GLSL shaders (dark
  floors / lighting), an Image API that maps onto our procedural pixel-art
  generation, and AudioStream for the procedural synth. Escape hatch if
  console-grade platform support is ever needed: raylib ≥ 5.0 can itself be
  built on an SDL backend, and sim code never touches raylib (see hard rules),
  so the platform layer stays swappable.
- **2026-08-17 — One canonical asset tree.** The existing PixelLab artwork is
  the game's identity and now lives directly in `assets/`, the sole source of
  game-ready art. The migration-only `source_assets/` staging tree and copy/bake
  scripts were removed; static UI paths and geometry are type-checked in Odin.
- **2026-08-18 — Native actor cells are lossless.** Every actor sheet preserves
  its original PixelLab square canvas (97–256px) instead of normalizing non-player
  art to 128px. `assets/actors/manifest.json` records the native canvas, row count,
  and SHA-256 of every sheet; runtime loading rejects resampled or mis-sized sheets,
  and `tools/verify_actor_assets.py` enforces the self-contained pack contract.
- **Fixed-timestep simulation.** 60 Hz accumulator for the sim, render at
  display rate. Determinism makes combat repros, tests, and an eventual
  multiplayer resim far simpler than pygame's clamped-variable-dt loop.
- **2026-08-11 — Audio: authored, not procedural** (Matti). The NES-style
  procedural generator stays behind in the pygame game. `audio.odin` loads
  authored cue files declared by `assets/audio/manifest.json`; final background
  tracks and their slot/transition specification intentionally wait for the
  incoming music package rather than being guessed in M10.
- **One Odin package first.** `src/` is a single package, one file per
  subsystem. Odin forbids import cycles; the pygame mixin graph is heavily
  cyclic, so premature package splits would fight the port at every step.
  Packages get split out only at proven seams (wire `protocol` for MP later,
  maybe `content` if tables get huge). Mirrors the project's "vibe
  architecture, intentionally small" rule.
- **2026-08-11 — Pygame pixel metadata is WORLD_SCALE=5 space.** The pygame
  game renders on a 1440p canvas with `WORLD_SCALE = 5` (tiles 320x160 px);
  every pixel value in its manifests/constants (sprite `target_height`,
  anchors in px, offsets) is in that space. The rewrite's world unit is the
  unscaled 64x32 tile, so **all imported pixel metadata was divided by 5**.
  Caught in M3 review: characters
  rendered 5x too large. M10 maps Pygame's HD `.8` view zoom to raylib `2.0`
  (10 tiles across at 1280 wide), with the source 14/s follow and 48%-height
  player focus.
- **2026-08-11 — Vendored raylib binding + static lib.** Arch's `odin`
  package ships `vendor:raylib`'s binary libs as unresolved git-LFS pointer
  files (packaging bug), so the binding lives in-tree at `vendor/raylib/`
  (raygui omitted — its foreign import is unguarded and we don't use it)
  together with the real `linux/libraylib.a` fetched from
  `odin-lang/Odin@dev-2026-07` and sha256-verified against the upstream LFS
  pointer (`1199fb5b…`). The upstream archive's four C23-only glibc imports are
  deterministically normalized to their C99/legacy ABI equivalents so the
  Ubuntu 22.04 / glibc 2.35 release baseline can link it; the transformed hash,
  member set, and provenance are pinned under `vendor/raylib/linux/` and checked
  by `tools/verify_linux_raylib.py`. Imports use `../vendor/raylib`. This pins
  raylib 6.0 regardless of system state and keeps builds static and reproducible.
- **2026-08-14 — Story is deterministic simulation; panels are presentation.**
  `story.odin`, `story_content.odin`, and `story_runtime.odin` own the seeded
  corpus, run consequences, guests, minigames, and modal reducer without
  raylib. `ui.odin` renders compact story panels over the frozen live scene;
  `assets/story/manifest.json` is an exact 81-key, SHA-256-pinned authored-art
  contract with procedural runtime fallback only for missing optional images.
- **2026-08-17 — MX-save is local-first and transaction-oriented.** One active
  solo run lives beside independent options and profile documents in the stable
  per-user `arch-rogue` data directory. `persistence.odin` owns raylib-free DTOs,
  checksums, migrations, validation, Chronicle/profile operations, and run
  conversion. `main.odin` owns paths, recovery artifacts, OS durability, and one
  coalescing worker. Routine jobs cross threads only as process-heap-owned fixed-
  tick snapshots; death/victory commit a terminal run marker, idempotently merge
  the Chronicle by `run_id`, durably write the profile, then delete run artifacts.
- **2026-08-19 — Android uses one native game loop and a narrow Java shell.** The
  package targets API 35 with API 28 minimum and contains exactly `arm64-v8a`,
  `armeabi-v7a`, and `x86_64`, in that order. The debug/release IDs remain
  `org.archrogue.archrogue.odin.alpha.debug` and
  `org.archrogue.archrogue.odin.alpha`. Custom `ArchRogueActivity` loads the
  native library through its class loader, registers `OnBackInvokedCallback` on
  API 33+, preserves legacy `onBackPressed()`, and sends both through JNI to the
  shared semantic `.back` intent; gameplay remains Odin/raylib.
- **2026-08-19 — Every Android ABI uses an audited deferred-entry link.** Odin
  emits Android LLVM IR, pinned Clang compiles it, and the matching NDK driver
  links native-app glue so raylib enters game `main()` only after activity setup.
  Audits reject `DT_INIT` and host contamination and require both the packaged
  Java activity contract and JNI Back symbols.
  A local FIPS-vector-tested portable SHA-256 replaces `core:crypto/sha2` for the
  ARMv7 baseline, whose link also localizes pinned Odin `__fixunsdfdi` before NDK
  compiler-rt resolution.

## Hard rules

1. Self-contained active project: no build- or run-time references into
   `arch-rogue-python/` or another parallel source tree. `assets/` is the sole
   canonical art tree. Tools may verify, capture, or profile committed assets,
   but must not copy active inputs from the archive.
2. Engine boundary: raylib calls/types are allowed only in platform-facing
   files — `main`, `render`, `render_mist`, `ui`, `assets`, `audio`. Simulation files
   (`sim`, `sim_nav`, `combat_depth`, `companions`, `population`, `dungeon`, `content`,
   `core_*`, `app`, `input`, `mobile`, `options`, `progression`, `shop`, `story`,
   `story_content`, `story_runtime`, `special_rooms`, `feel`, `visuals`) stay raylib-free so they run headless under
   `odin test` (the rewrite's equivalent of the dummy-SDL test culture).
   Enforced by convention now (`grep 'rl\.'`), CI lint later.
3. Data-driven content: archetypes, enemies, bosses, items, affixes as Odin
   constant tables — type-checked at compile time, zero parse cost — ported
   from the archived `arch-rogue-python/src/arch_rogue/content/` tables.
4. All randomness flows from one seeded PCG stream per run (plus derived
   streams per floor), never `core:math/rand` global state. Same-seed runs
   must replay identically.

## Layout

```
./                    repository root
  ARCHITECTURE.md      this file
  CHANGELOG.md         rewrite history from the start of the 6.x migration
  build.sh             build/run/test/check plus Android command wrapper
  android/             pinned Gradle NativeActivity package, custom Java Back bridge,
                       launcher resources, toolchain/version metadata, licenses
  assets/              canonical game-ready art + runtime data manifests
  tools/               capture/profile/verifier tools plus Android build/audit/smoke
  vendor/raylib/       vendored raylib 6.0 binding + pinned desktop/Android archives
  src/                 single Odin package `archrogue`
    main.odin          desktop/Android entry, fixed-step loop, frame pacing
    app.odin           app-state machine: title/select/play/pause/options/end states
    input.odin         raylib-free desktop snapshot → shared intent mapping
    mobile.odin        native mobile layout, touch roles, lifecycle + Back semantics
    options.odin       difficulty profiles, option values/defaults/normalization
    persistence.odin   versioned JSON DTOs, checksums, migrations, Chronicle/profile
                       operations, run snapshot/restore conversion (raylib-free)
    storage_replace_nonwindows.odin / storage_replace_windows.odin
                       atomic POSIX replacement / Windows write-through replacement
    progression.odin   100-node discipline table, tokens, acquisition/effect coverage
    shop.odin          deterministic stock, valuation, atomic buy/sell economy
    special_rooms.odin Shop/Bar/Garden/Quest/Hall queries, furnishings, refuge behavior
    story.odin         deterministic story engine, interpolation, flags, endings
    story_content.odin typed factions/relics/motifs/guests/dilemmas/endings corpus
    story_runtime.odin run consequences, guests, relics, Soul, minigames, panel reducer
    core_math.odin     iso/grid transforms, geometry helpers
    core_rng.odin      seeded PCG streams, dice/roll helpers
    dungeon.odin       procgen: rooms, corridors, chokepoints, themes, stairs;
                       collision + floor queries
    content.odin       data tables (archetypes, enemies, items, affixes)
    sim.odin           actors, movement, real-time combat, projectiles,
                       XP/levels, loot drops, depth scaling
    sim_nav.odin       radius-limited enemy route field (ported from archived
                       arch-rogue-python/src/arch_rogue/combat/pathing.py)
    combat_depth.odin  typed damage/statuses, four-slot class kits, affix
                       effects, curses, crits, and action cost/cooldown math
    companions.odin    Acolyte spirit hosts and Ranger Spirit Beast AI
    feel.odin          bounded deterministic combat-presentation events
    population.odin    floor encounters, elites/bosses, typed enemy profiles,
                       loot, affix rolls, unidentified gear, and curses
    assets.odin        texture registry, typed UI metadata, pack manifests
    visuals.odin       raylib-free ambient/fog/mist/ghost/idle/combat-FX policy
    render.odin        camera follow, depth-sorted draw list, tiles/actors/
                       effects, semantic minimap markers/edge guidance,
                       diagonal fog/LOS masks, per-fragment transient visibility,
                       fail-closed light compositor, contact shadows and
                       foreground-wall actor ghosts
    render_mist.odin   shader-driven ambient mist banks disturbed by actors
    ui.odin            HUD, menus, fonts, damage numbers, responsive story panels
    audio.odin         authored SFX manifest/loading/dispatch; music pending tracks/spec
  tests/               odin test package for sim/dungeon/content/visual policy
  tools/capture_mx6.sh deterministic combat-action screenshot matrix
  tools/capture_mx7.sh deterministic 46-shot world/theme/FOW matrix
  tools/capture_mx_story.sh 15-shot story panel/resolution matrix
  tools/capture_mx_save.sh  24-shot Chronicle/recovery resolution matrix
  tools/verify_story_assets.py strict 81-file PNG/hash verifier
  tools/verify_chronicle_assets.py exact Chronicle PNG/hash verifier
  tools/profile_mx7.sh release visible-crowd p95 frame-time gate
  tools/profile_mx_save.sh release crowded-floor frame/snapshot/save gate
  tools/android.sh     pinned three-ABI compile/package/install command surface
  tools/android_audit.py strict APK/package/asset/ELF/JNI audit
  tools/android_smoke.py API-34 gameplay/touch/Back/lifecycle/Resume smoke
  tools/rebuild_raylib_android.sh reproducible pinned GLES2 archive rebuild
```

## Simulation model

- `Run` struct owns a floor (`Dungeon` grid + entity storage) and run meta
  (depth and seed). `App` owns the state union and the current `Run`.
- Floor entities live in `Run`-owned dynamic arrays (`Enemy`, `Projectile`,
  `Familiar`, `Ground_Item`). Simulation helpers use pointers only within a
  non-growing pass; cleanup compacts or removes entries after resolution.
- Player, enemy, and familiar state are separate plain structs. Enemies carry
  content-driven stats and a compact idle/chase/windup state machine; action
  commitment and recovery live in explicit timers.
- Combat: real-time, cooldown-based; melee arcs and projectiles resolve
  against the grid + actor circles. Damage/status numbers ported from the
  Python content tables so tuning survives the rewrite.
- Rendering reads sim state, never mutates it. Its actor/world draw list is
  rebuilt each frame and painter-sorted by isometric depth (`tile x + tile y`)
  with explicit offsets for floor and effect layers.

## Milestones

**v0 complete (2026-08-11):** M0 bootstrap, M1 dungeon, M2 player, M3
combat, M4 loot & progression, M5 a-run-that-plays all landed in one day —
the game boots from title into a playable run with combat, loot, levels,
dark floors, and SFX at 6.0.0-alpha.6. History lives in git and
CHANGELOG.md.

The road from here is the **parity push** — see `PARITY.md` for the full
spec, inventory, and roadmap:

- **M6 — World & visual parity** (themes, authored world art, fog of war,
  minimap) — alpha.10 adds depth ambient, smooth LOS/FOW masks, clipped lights,
  shadows and actor wall ghosts; final side-by-side signoff/guidance remains
- **M7 — Bosses & run completion** (full roster, elites, 5 bosses, win) —
  in progress
- **M8 — Combat depth** (statuses, class kits, familiars, full affixes)
  ✓ complete at 6.0.0-alpha.7
- **M9 — Character, meta & shell** (disciplines, difficulty, shop, options,
  pause, controller/remapping) ✓ complete at 6.0.0-alpha.8
- **M10 — Audio, feel & parity audit** ✓ audit/feel foundation complete at
  6.0.0-alpha.9; alpha.10 completes the requested lighting/fog/shadow pass

MX-story is complete at 6.0.0-alpha.18. MX.8 parity closure audit is
complete at 6.0.0-alpha.19. MX-save is complete at 6.0.0-alpha.20. MX-android is
complete at 6.0.0-alpha.21: 357 tests and the strict three-ABI APK audit pass,
the raylib rebuild is checksum-identical, and API-34 x86_64 plus forced
ARM64-translation smoke cover Options/Back. Matti confirmed an earlier ARM64 APK
starts on a physical device, but the alpha.21 Options/gesture fixes still need a
physical retest; ARMv7 runtime was not testable because the current AVD has no
32-bit ABI. Multiplayer, Steam integration, and achievements remain deferred.
Legacy graphics + perf overlays are dropped. Matti's M6 side-by-side visual
signoff on a display machine also remains open.

## Testing

`odin test tests` runs headless: dungeon connectivity/determinism, RNG stream
stability, desktop input mapping/held-input behavior, typed/status/affix combat
math against known values from the Python tables, companion AI, class-kit
costs and clocks, floor/run transitions, bosses, loot/inventory, the 100-node
discipline table, difficulty scaling, shop transactions, special-room layouts,
options persistence, controller mapping, shell/modal transitions, authored
audio manifests, action/death timelines, movement/idle cadence, feel-event
profiles, visual ambient/fog/ghost/combat-FX policy, stable actor presentation
IDs, action classification/recovery, projectile/slash geometry, bounded queue
priority, FOW visibility, minimap marker/arrow policy, Shop dressing placement,
final-boss tuning, deterministic story generation/interpolation, Quest/Hall
rooms, guest/relic/Soul consequences, all 15 endings, panel reducers/layout,
exact story-art paths/dimensions/SHA-256, semantic option migration, checksummed
profile/run round trips, continuation determinism, temp/backup/corrupt recovery,
profile merge/retention, exactly-once terminal transactions, worker snapshot
ownership/coalescing, responsive Chronicle UI/assets, mobile layout/touch-role
arbitration, semantic Back, lifecycle reduction, accumulator reset, and Android
save requests. The alpha.21 suite contains 357 deterministic tests and passes
with `odin test tests -vet`; `odin check src -vet` is also clean. The release-only
`profile_mx_save.sh` gate additionally exercises asynchronous checkpointing on a
fully rendered crowded floor without touching real saves.

Android validation is separate from headless tests: the strict APK audit accepts
only `arm64-v8a`, `armeabi-v7a`, `x86_64` and rejects `DT_INIT`, host contamination,
or missing JNI Back symbols; the pinned raylib rebuild reproduces its checksums.
The API-34 x86_64 smoke covers Options entry, disabled-row arbitration, an edge
Back gesture, gameplay, multi-touch, lifecycle, and Resume; forced ARM64
translation covers startup plus
Options/Back. Physical confirmation is limited to an earlier ARM64 APK pending
alpha.21 gesture retest; no ARMv7 runtime pass is claimed without a 32-bit AVD.

## Dev hooks

Environment variables read at startup (all optional):

- `ARCH_ROGUE_SEED=<u64>` — pin the run seed for reproducible floors.
- `ARCH_ROGUE_ZOOM=<f32>` — initial camera zoom (bypasses wheel clamps).
- `ARCH_ROGUE_SHOT=<path>` — save a screenshot at frame `ARCH_ROGUE_SHOT_FRAME`
  (default 40) and exit; used for autonomous visual verification. Path is
  relative to the working directory (raylib's TakeScreenshot rejects absolute
  paths), e.g. `build/shot.png`.
- `ARCH_ROGUE_PLAY=1` — skip archetype select and start a run immediately.
- `ARCH_ROGUE_ARCHETYPE=<name|0..4>` — choose the immediate-run archetype.
- `ARCH_ROGUE_MX6_CAPTURE=<scenario>` plus `ARCH_ROGUE_CAPTURE_DIR=<direction>`
  — stage a real combat action on the screenshot frame. `ARCH_ROGUE_LIGHTING=0`
  provides an unpersisted lighting override for FOW comparisons. Prefer the
  complete, deterministic `tools/capture_mx6.sh` matrix instead of hand-writing
  individual invocations.
- `ARCH_ROGUE_MX7_CAPTURE=<scenario>`, `ARCH_ROGUE_CAPTURE_THEME=<0..7>`,
  `ARCH_ROGUE_CAPTURE_DARK=<0|1>`, and `ARCH_ROGUE_CAPTURE_DOOR=<open|closed>`
  — deterministic fixed-step world staging for the 46-shot theme, special-room,
  painter, marker, and FOW matrix in `tools/capture_mx7.sh`.
- `ARCH_ROGUE_MX_STORY_CAPTURE=omen_initial|relic_choices|guest|soul|ending`
  plus `ARCH_ROGUE_CAPTURE_WIDTH` / `ARCH_ROGUE_CAPTURE_HEIGHT` — stage a
  reachable production story panel at an exact window size. Prefer the full
  15-shot `tools/capture_mx_story.sh` small/desktop/4K matrix.
- `ARCH_ROGUE_MX_SAVE_CAPTURE=empty|populated|victories|fallen|recovery|abandon`
  plus capture dimensions stages the isolated Chronicle/recovery matrix. Prefer
  `tools/capture_mx_save.sh`; it writes no user save data.
- `ARCH_ROGUE_MX_SAVE_PERF=1` with the ordinary perf frame/warmup variables runs
  the release crowded-floor checkpoint gate in a process-temp data directory.
  Prefer `tools/profile_mx_save.sh`, which validates frame p95, snapshot latency,
  render resources, and the resulting run document.
- `ARCH_ROGUE_MX7_PERF=1` with optional `ARCH_ROGUE_PERF_WARMUP` /
  `ARCH_ROGUE_PERF_FRAMES` — uncapped visible-crowd frame timing. Prefer the
  release-build, three-run real-GPU gate in `tools/profile_mx7.sh`.
- `ARCH_ROGUE_DEV=1` — enable the development-only `N`/`R`/`B` floor and run
  shortcuts. They are inert in ordinary builds so progression cannot be
  bypassed accidentally.
- Live input can be driven with `xdotool keydown --window <id> d` etc. while
  a delayed SHOT runs — how walk/facing/camera-follow get verified headlessly.
