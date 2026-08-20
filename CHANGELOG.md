# Changelog

## Unreleased

- Fixed the web-only sound glitch when the opening story cutscene appears. The
  Select-to-Playing transition now uses `Start` as its sole cue, lazy packs
  materialize at most one file per browser animation frame, and actor textures
  adopt at most one per game frame only while authored SFX are quiet. This
  avoids starving raylib/miniaudio's main-thread `ScriptProcessorNode` callback
  during first-run generation, checkpointing, and pack arrival.
- The public mirror's release workflow now deploys the exact audited
  `arch-rogue-v<version>-<sha12>-web.tar.gz` payload to GitHub Pages at the
  site-relative `play/` path. `prepare-pages` downloads rather than rebuilds
  the web artifact, validates and strips exactly one `arch-rogue-web/` root,
  rejects links and unsafe members, reruns `web-audit`, enforces the Pages size
  and symlink boundaries, and publishes one combined download/play site. A
  retrying post-deploy probe verifies `play/` and `play/packs.json`.
- The download site gains an accessible browser Play card and documents
  origin-scoped IndexedDB saves. GitHub Pages controls its own cache and
  compression headers, so the self-hosted Brotli wire budget and
  immutable/no-cache behavior are not claimed for the Pages endpoint.

## 6.0.0-alpha.23 — The gate opens in the browser

- The UI has a real typeface: EB Garamond Medium (SIL OFL 1.1, bundled with
  its license under `assets/ui/fonts/`) replaces raylib's built-in pixel font
  across every panel, HUD, and overlay on all platforms, matching the serif
  the web shell established. All text routes through new
  `ui_draw_text`/`ui_measure_text` seams that scale sizes 1.18x to compensate
  Garamond's small x-height, re-center each line on the caller's band (menu
  and pause rows sit visually centered in their plates again), and fall back
  to the default font if the file is missing. The web shell's CSS stack now
  prefers EB Garamond too.
- Panel text can no longer escape its chrome: the victory and death summaries,
  the run ledger, the notable-loot line, and the boss nameplate shrink to fit
  their panels and ellipsize at the size floor. New `victory_panel` and
  `dead_panel` MX7 capture scenarios stage a worst-case run (longest modifier,
  saturated counters, three long notable finds) so overflow regressions are
  visible in one screenshot — this covers the known "Tyrant is dead" panel
  overflow.

- MX-web platform milestone: Arch Rogue now ships a native Odin/raylib
  WebAssembly build. The pinned Emscripten `6.0.7` toolchain links the game
  against a new checksummed, reproducible raylib 6.0 `PLATFORM_WEB` archive
  (`vendor/raylib/wasm/`, OpenGL ES 3.0), and `./build.sh` gains canonical
  `web-preflight`, `web-build`, `web-audit`, and `web-serve` commands.
- Runtime ownership is now explicit `game_init` / `game_frame` /
  `game_shutdown` phases shared by every platform: desktop/Android drive them
  from the existing blocking loop, the browser drives them from
  `requestAnimationFrame` through a small C entry. Production web builds use
  no ASYNCIFY, the deterministic fixed 60 Hz simulation is preserved, and tab
  return discards the hidden gap so the accumulator cannot catch-up spiral.
  raylib's web `WindowShouldClose` (which internally sleeps) is never called.
- The wasm-hostile runtime surface now compiles out cleanly behind the
  platform seam: the `core:thread` save worker, `core:os`/env dev toggles,
  temp-dir perf harnesses, and capture scenarios moved into
  `src/main_desktop.odin`, with shared capture staging in
  `src/capture_stage.odin` and the web entry in `src/main_web.odin`.
- Web persistence is asynchronous IndexedDB behind the same byte-level
  storage primitives: the shared DTO, checksum, migration, tmp/bak recovery,
  and Chronicle logic run unchanged against an in-memory mirror hydrated at
  boot and flushed asynchronously — no Wasm threads and no cross-origin
  isolation. Lifecycle checkpoints fire on `visibilitychange`/`pagehide` and
  are documented as best-effort; browsers do not guarantee final writes.
- The initial download is split and content-addressed: a ~19 MB-on-the-wire
  core payload (engine + UI + world + enemies + previews) against a declared
  and audited 28 MiB budget, plus seven lazily fetched, digest-verified packs
  (per-archetype clips, social actors, bosses; 40.8 MB deferred) that stream
  at run start and re-resolve their sprites on arrival. Outputs ship with
  Brotli siblings and load behind a visible progress bar with no runtime CDN
  dependency.
- The Emscripten heap is pinned (`INITIAL_MEMORY` 256 MiB, growth disabled)
  and `web-audit` verifies the pin inside the wasm memory section itself,
  alongside the budget, content addressing, pack digests, ASYNCIFY absence,
  and CDN-reference absence. Measured crowded-floor use is ~24 MiB dynamic
  heap.
- WebGL2 is required and gated before the runtime downloads; there is no
  WebGL1/GLES2 fallback. The lighting and mist shaders gained
  `#version 300 es` variants. High-DPI cost is bounded by a deliberate
  devicePixelRatio clamp (1.0 for this alpha, one shell constant to raise).
  Browser audio initializes on the first user gesture — deferred one frame,
  because creating the device inside the gesture callback tramples GLFW's
  keyboard hooks.
- New zero-dependency Node harnesses cover the milestone gates:
  `tools/web_smoke.mjs` (14 scenarios — boot, gesture audio unlock, run
  start, lazy packs, suspend checkpoint, save/reload continuity, tmp/bak
  recovery of a corrupted primary, resize, fullscreen, cached reload,
  synthetic controller, clean console) and `tools/web_profile.mjs`
  (deterministic crowded floor at 1280×720 CSS after warmup; gates on a
  bounded long-frame count — no interval above two vsync periods — plus a
  main-thread busy budget, never a raw p95 frame-interval threshold).
  Headless Chromium and Firefox both pass: 0 long frames, busy p95 2.8 ms /
  4.0 ms against a 12.5 ms budget, clean consoles.
- The public release workflow gains a `web` job that builds, audits, and
  attaches `arch-rogue-v<version>-<sha12>-web.tar.gz` as a release artifact;
  private CI checks the freestanding wasm32 target; the public snapshot
  allowlists the new `web/` tree. Where the web build deploys as a playable
  page remains a deliberately open product decision.
- Declared browser baseline for this alpha: current desktop Chromium-family
  and Firefox releases with WebGL2. Safari and mobile browsers are not yet
  validated and are not claimed.

- Basic melee reads as a committed action (2026-08 feel feedback): a swing now
  opens with a 0.14 s movement plant that also holds the swing's aim facing,
  and a connected swing freezes the sim for 2 ticks — 4 on a crit or killing
  blow — while slashes, lights, and the camera keep playing through the freeze.
  Both are deliberate deviations from the pygame game, which let swings happen
  mid-stride with no impact pause. Dashing cancels the plant.
- Restored the player-as-mover half of the pygame contact resolution
  (`combat/movement.py` `resolve_actor_contacts`), which the port had dropped:
  walking and dashing now place the player back at body-contact distance
  instead of shoving through enemies. This removes the regression where the
  player could ram enemies around and walk over a wall-pinned one, then attack
  from inside its body.
- Replaced the provisional Android launcher mark with a PixelLab-authored Arch
  Rogue relic medallion across legacy square, round, adaptive, and Android 13
  themed-icon variants. The center uses the canonical title-logo relic at its
  original aspect ratio over the unchanged etched-rune medallion. The installed app, local APK/AAB outputs, public release
  assets, download site, and other product-facing labels now use `Arch Rogue`
  without treating the Odin implementation language as part of the game title.
  Release resource-path shortening is disabled because AAPT2 can emit paths that
  differ only by case, which the cross-filesystem-safe Android audit rejects.
- Promoted the Odin/raylib project from `ar-odin/` to the repository root and
  moved the retired Python/Pygame implementation into `arch-rogue-python/` as an
  archived reference tree. Root build, asset, Android, documentation, CI, and
  filtered public-snapshot paths now follow the Odin layout; the public release
  pipeline publishes the current Linux and Android artifacts and Pages site from
  that snapshot. Historical `ar-odin` release headings and statements below are
  intentionally preserved as records of the layout in which those releases shipped.
- Hardened the cutover release boundary: archived Python source remains visible
  in the public mirror but contributes no Actions or deployment material; active
  Steam/server workflows remain retired. Public Linux/Android prereleases now use
  12-character commit-addressed tags, split release and Pages write privileges,
  retain handoff artifacts for seven days, and ignore archive-only pushes. Android
  releases reuse the existing four environment secret names while validating the
  configured keystore and final artifacts against a committed certificate
  fingerprint. Mirror assembly rejects destructive source-overlapping destinations
  and trusts only the reviewed GitHub ED25519 host key.
- Fixed Linux/public CI compiler setup for the July 2026 Odin toolchain. The
  official `dev-2026-07` prebuilt archive identifies itself as the earlier
  `dev-2026-07-nightly:ab0131c`, while the finalized tag and Android contract are
  `dev-2026-07:301c287de`. CI now builds that exact source commit with the validated
  LLVM `21.1.8` backend and checks only the authoritative full Git revision and
  backend instead of comparing Odin's variable-length displayed hash.
- Made the vendored Linux raylib 6.0 archive link on the Ubuntu 22.04 release
  baseline by normalizing four C23-only glibc imports to their ABI-compatible
  C99/legacy symbols. The transformed archive now has pinned provenance and
  SHA-256 metadata, and CI verifies its exact members and rejects any remaining
  `__isoc23_*` imports before building.
- Fixed an Android 17 AAudio/miniaudio shutdown race that could abort the native
  process on Back or make a suspended game appear unable to resume. Ordinary
  focus/surface restoration now preserves the existing audio device, while
  Android activity shutdown releases game-owned sounds but leaves the backend
  process-owned for safe same-PID NativeActivity reuse. Added repeated
  suspend/resume lifecycle regression coverage.
- Reworked the native Android gameplay HUD into the sparse hand-held layout:
  imported the canonical Pygame joystick base/knob and ornate vertical resource
  frame, added a compact XP/health/mana/stamina cluster at upper-left, kept the
  six authored action slots on the right rail, and moved the animated joystick
  to the lower-left. A new bottom-right A button now performs contextual world
  interactions; when no advertised interaction is nearby it toggles a horizontal
  Bag/Character/Menu drawer to its left. Hit targets, safe-area layout, Android
  Back dismissal, secret wall interactions, modal/death cleanup, and prompt
  placement share the same semantic state and have headless regression coverage.
- Re-imported all 29 actor families into Odin at their native PixelLab canvas
  sizes (97–256px), removing the old destructive 128px normalization from bosses,
  enemies, familiars, and NPCs. The format-2 actor manifest now records native
  canvases, direction-row counts, and per-sheet SHA-256 hashes; runtime loading
  rejects resampled or mis-sized sheets and explicitly keeps point sampling.
  Added a self-contained verifier covering all 94 actor sheets without reading
  from `arch-rogue-python/` or another parallel source tree at build or run time;
  the native PixelLab actor sources are preserved by the migration.
- Added a cohesive PixelLab inner treatment to the Chronicle: one restrained
  black-iron content panel now encloses both the descents list and memorial instead
  of two competing frames, with a responsive divider for wide and compact layouts.
  Matching bronze-corner filter controls remain separate, all authored assets are
  hash-pinned, and geometry fallbacks remain available. Text stays within enlarged
  safe areas, optional memorial lines are bottom-bounded, and the compact descent
  row stack is vertically centered between the panel rails while using a thin
  selection border without an arrow.
- Replaced the shared title, archetype, Options, and Controls viewport frame with
  a newly generated, much lighter PixelLab black-iron frame. Its transparent
  border now touches every screen edge, while authored-size corners and a narrow
  fixed safe margin keep the chrome delicate at 480p through 4K, matching the
  edge-owned composition established by the Chronicle.
- Ported the Pygame title treatment to Odin: the central relic now spins through
  a self-contained 16-frame, 8 fps atlas while the wordmark stays crisp. The
  relic, rather than the unequal-width words, is anchored to exact screen center.
- Rebuilt the title, archetype-selection, and title-launched Options backdrops
  as responsive layers: the title uses the clean 400x224 Iron Gate scene while
  the archetype/options ritual scene cover-crops harmlessly behind the shared
  PixelLab dark-iron rune frame. Fit-scaled corners stay on-screen and complete
  rail tiles remain intact at 4:3, 16:10, 16:9, and ultrawide ratios. The frame's
  outer transparent padding is halved so its visible art sits twice as close to
  every display edge. Its safe rectangle now drives title/logo rows, carousel
  placement, compact Options/Controls rows, footers, and matching pointer hitboxes.
- Made `assets/` the sole canonical artwork tree: removed `source_assets/`, the
  one-off actor/HUD/prop/UI/world migration scripts, and the redundant UI JSON
  manifest. All 22 UI textures now load from typed Odin paths and metadata; logo
  and glyph atlases use direct constants and deterministic enum-ordinal regions.
  The renamed `tools/verify_story_assets.py` remains only as a strict verifier.
  Headless regressions cover canonical PNG dimensions, unique keys/paths, title
  centering/layout, cover geometry, frame composition, and responsive
  Options/Controls layout. The complete alpha.21 suite now passes 357 tests.
- Imported the authored Spike Trap, Rune Trap, and Poison Needle sprites into
  the Odin prop pack. Revealed traps now render their floor-centered sprite over
  the existing fade, pulse, and diamond telegraph instead of geometry alone.
- Replaced unsupported em-dash separators in interactable HUD prompts with
  ASCII hyphens so raylib's default font no longer displays question marks.
  A source-wide UTF-8/escape-aware regression now checks every production Odin
  string literal against raylib's U+0020..U+00FF default-font glyph contract.
- Room residents now feel alive: Shopkeepers, Bar dancers, Garden frogs,
  unresolved story guests, and the unarmed Lossless Soul deterministically
  wander, pause for interactions, and dance inside their authored rooms. Live
  positions interpolate smoothly, stay inside room/furnishing bounds, preserve
  fixed Shop-sign and Garden interactions, and never consume gameplay RNG.
- Acolyte Spirit Call now preflights radius-clear, line-of-sight spawn positions
  for every Wisp or Crow before spending mana or replacing the current host.
  Blocked orbit points fall back deterministically to nearby floor, fully sealed
  casts fail without cost, and owner separation can no longer push a familiar
  through collision geometry.

## 6.0.0-alpha.21 — The descent fits in your hands (ar-odin)

### MX-android — Native Android packaging, lifecycle, Back, and touch playability

- Added the self-contained native Android build at `targetSdk 35` / `minSdk 28`
  while preserving the isolated alpha application IDs:
  `org.archrogue.archrogue.odin.alpha.debug` for debug and
  `org.archrogue.archrogue.odin.alpha` for release. APKs contain exactly
  `arm64-v8a`, `armeabi-v7a`, and `x86_64`, in that order.
- Standardized every Android ABI on the audited Odin LLVM IR → pinned Clang →
  NDK deferred-entry link. Strict artifact audits reject eager `DT_INIT`, host
  GLIBC/X11/pthread contamination, stale or unexpected dependencies, and now
  require both the packaged Java activity contract and JNI Back bridge symbols.
- Added the custom Java `NativeActivity`: it loads `libmain.so` through the
  activity class loader with `System.loadLibrary`, registers
  `OnBackInvokedCallback` on API 33+, and retains legacy `onBackPressed()`.
  Both paths cross the JNI bridge and produce the same semantic `.back` intent
  used by desktop inputs and menus.
- Completed the Android runtime path for OpenGL ES 2.0, native-resolution
  rendering, packaged assets, authored audio, app-private saves, multi-touch,
  lifecycle suspend/resume, and resource restoration without introducing a
  second game loop.
- Fixed touch ambiguity by selecting the nearest target center when hit regions
  overlap, retaining disabled visual rows as inert blockers, and suppressing
  raylib's zero-contact touch-as-mouse pass-through. This prevents fullscreen-row
  bleed and phantom taps around Options or gesture edges.
- Replaced `core:crypto/sha2` with a local portable SHA-256 implementation tested
  against FIPS vectors so persistence stays compatible with the ARMv7 baseline.
  The ARMv7 link also localizes Odin's pinned `__fixunsdfdi` before the NDK
  compiler-rt archive is resolved.
- Validation is clean: `odin check src -vet`, all 357 tests, the strict
  three-ABI APK audit, and a checksum-identical pinned-raylib rebuild pass. The
  API-34 x86_64 smoke passes Options entry, disabled-row non-mutation, an actual
  edge-gesture Back, gameplay, multi-touch,
  background/resume lifecycle, and app-private Resume; a forced ARM64-translation
  run also starts and passes Options/Back.
- Matti previously confirmed that an earlier ARM64 APK starts on a physical
  device. The alpha.21 Options/gesture fixes still require physical retesting,
  so this release does not claim physical confirmation for those changes.
  ARMv7 runtime testing was not possible because the current AVD exposes no
  32-bit ABI.

## 6.0.0-alpha.20 — The Chronicle remembers (ar-odin)

### MX-save — Local save/resume, Chronicle, and persisted game options

- Added one automatically managed active solo-run checkpoint with title-screen
  `Resume`, a frozen continuation veil, explicit abandon confirmation, pause-menu
  `Save & Return to Title` / `Save & Quit`, close-event saving, and damaged-run
  recovery/quarantine flows. Capture and profiling hooks remain isolated from
  real user storage.
- Added independent, versioned, checksummed `options.json`, `profile.json`, and
  `run.json` documents under the stable per-user `arch-rogue` data directory.
  Writes use synced same-directory temp files, last-known-good backups, atomic
  replacement, parent-directory sync on POSIX, and write-through replacement on
  Windows. Startup chooses the highest valid same-identity revision and preserves
  future, corrupt, conflicting, and oversize data rather than silently resetting.
- Fixed manual save lifecycle failures found during desktop acceptance. Odin's
  `os.mkdir_all` reports an existing data directory as `.Exist`, which previously
  disabled persistence after the first launch; existing directories are now
  accepted while non-directories still fail closed. Explicit save exits also poll
  in-flight checkpoints without blocking the render loop, and unavailable storage
  now enters the actionable save-error flow instead of waiting indefinitely.
  Relaunch-time discard restores the unopened checkpoint's durable identity before
  tombstoning it, so starting anew no longer requires Resume as an intermediate step.
- Moved Hell unlock ownership into the durable profile and added semantic options
  migration, bounded Chronicle retention (512 records / 2 MiB), profile merge and
  run-id deduplication, lifetime totals, and exactly-once death/victory finalization
  across every crash boundary.
- Added owned fixed-tick run snapshots and a single coalescing worker. The main
  thread clones authoritative continuation state; the worker validates, encodes,
  hashes, and writes it. All cross-thread allocations use an explicit process-heap
  policy, and queued options/profile/run domains coalesce independently without
  eviction or self-requeue deadlocks.
- Added the title-accessible wide/compact Chronicle with summary, filters,
  substantial timeline cards, memorial details, responsive keyboard/mouse/
  controller navigation, and recovery/empty states. Its SHA-256-pinned PixelLab
  ledger frame now owns the full viewport without the shared menu frame beneath
  it, while every heading, panel, control, and footer hint stays inside a responsive
  frame-safe area. Matti approved the final composition across the regenerated
  24-shot 640x480/1280x720/1280x800/4K matrix.
- Added 32 MX-save regressions across persistence, lifecycle, corruption,
  interrupted writes, exactly-once finalization, continuation determinism,
  responsive UI, and asset contracts (suite: 301 → 333). Linux check/test/release,
  Windows cross-check, and the Chronicle asset verifier are clean. On AMD Radeon
  880M, the three-run release profiler measured median 2.689 ms frame p95 and
  0.061 ms worst main-thread snapshot capture while leaving a valid checkpoint.

## 6.0.0-alpha.19 — The ledger closes (ar-odin)

### MX.8 — Parity closure audit

- Added 30 focused MX.8 closure-audit tests (suite: 271 → 301) that drive
  deterministic full 1→10 runs headlessly with all five archetypes (Warden,
  Rogue, Arcanist, Acolyte, Ranger), at least one Hell-difficulty run, every
  boss depth (3/6/9/10), all six encounter templates, all eight run
  modifiers, every interactable family (3 traps, 7 shrines, 6 secrets, shops,
  bars, gardens), unique rewards from boss kills, shop transactions, bar
  refuge toasts, player death, and Gate Tyrant victory through the story
  epilogue flow.
- Reconciled the M10 backlog ledger: the 100-node discipline table is clean
  (38 Stats_Only + 62 Fully_Wired, 0 Untracked/Partial/Deferred); all 13
  unique items, 6 encounter templates, 8 run modifiers, 5 bosses, 8 themes, 5
  archetypes, and 4 difficulties are defined and exercised; the kill ledger
  accumulates correctly across a full descent; XP and gold grow from kills.
- Re-audited the alpha.19 post-parity boundary: story mode was complete;
  save/Chronicle and Android were the next platform milestones, while multiplayer,
  Steam/achievements, and incoming music remained deferred. Legacy graphics and
  perf overlays were dropped. The remaining visual parity signoff (M6
  side-by-side) required Matti's capture on a display machine.
- `odin check src -vet`, `odin test tests -vet` (301 tests), and `odin build
  src -vet -o:speed` (release) are all clean.

## 6.0.0-alpha.18 — The last ledger opens (ar-odin)

### MX-story — Full story mode with panel cutscenes and generated art

- Ported the deterministic story engine and complete 1→10 run corpus: five
  archetype arcs, eight factions and motifs, ten relics and guest roles, twelve
  dilemmas, tether beats, true names, persistent choice flags, and all 15
  archetype × Gate endings. Story generation uses its own derived RNG stream
  and remains raylib-free.
- Integrated story consequences into live runs: one Quest room and named guest
  per floor, deterministic guest allies and rewards, relic guidance/guardian
  paths and lasting effects, the Hall of Unlost Echoes by depth seven, the
  Lossless Soul and three verdicts, the Bind the Page / Wake the Moonbloom /
  Mirror the Unlost minigames, final-Gate flow, and tenth-bell victory.
- Matched Pygame's guiding-light presentation: the straight route line is gone,
  and a three-tile crest now source-over blends the eight authored glow overlays
  onto each tile's unchanged seeded floor slab while the player is idle. The
  minimap shows the active target as a pulsing beacon or gold viewport-edge
  direction arrow on every floor without
  revealing the full route.
- Completed authored in-world story presentation: Quest and Hall rooms now use
  their canonical floor slabs and left/right wall faces, the Hall's mirror,
  chimes, brazier, and reliquary replace procedural placeholders, and world
  relic icons render at a less intrusive 20px height. The canonical UI pack
  also includes all three minigame socket frames and the complete
  14-sigil vocabulary used by Bind the Page, Wake the Moonbloom, and Mirror the
  Unlost, with procedural geometry/text retained only as load-failure fallback.
- Replaced the floor art's linear coordinate rotation selector with a seeded 2D
  hash. Rotations remain stable on a generated floor, vary across runs/depths/
  regenerations, and no longer form visible diagonal generation bands.
- Added compact panel cutscenes over paused gameplay with progressive narration,
  mandatory and optional choices, keyboard/controller/touch pointer handling,
  guest/relic portrait slots, generated backdrops, and responsive layout from
  640x480 through a capped 4K scale. Cinematic side fill extends a darkened
  cover layer across the panoramic art rail while preserving the complete,
  centered 16:9 image above it. The outer modal now uses the authored menu-panel
  frame and safe insets. Relics sit in a dedicated black-iron, bronze, and
  violet-rune socket generated for the story UI, while choices reuse pygame's
  dedicated minimal `story_choice_panel` with a restrained selected accent,
  dimmed inactive states, and an inset icon socket. Dedicated Story Guest and
  Lossless Soul actor sheets keep their in-world appearances separate from panel
  art.
- Committed the self-contained `assets/story/` pack: 34 backdrops, 30 named
  guest portraits, ten relic icons, and seven choice icons (81 PNGs total).
  Existing completed PixelLab batches were recovered and curated rather than
  regenerated; only three failed mortuary portraits and three unreadable relic
  silhouettes were rerolled. `tools/verify_story_assets.py` decodes every PNG,
  enforces dimensions and exact canonical keys/paths, rejects extras, computes
  SHA-256, and verifies or intentionally updates the deterministic strict manifest.
- Upgraded all 34 story backdrops to opaque 640x360 sources and removed white
  edge mattes. The 15 ending panels were regenerated from their prior scene
  compositions with the canonical Warden, Rogue, Arcanist, Acolyte, or Ranger
  rotation as the identity reference, and the asset verifier now rejects wrong
  backdrop dimensions, transparency, and predominantly white outer edges.
- Added `tools/capture_mx_story.sh` and production staging hooks for initial
  omen, revealed relic choices, Sable guest dialogue, Lossless Soul reflection,
  and Arcanist/Aid ending panels. Its 15-shot fixed-step matrix targets exact
  640x480, 1280x720, and 3840x2160 dimensions under llvmpipe/Xvfb for panel-only
  review of complete backdrops, readable text, portraits, and icons.
- Added seven focused story test modules covering engine generation,
  interpolation, rooms, mechanics, runtime reducers, responsive UI, actor art,
  and the committed 81-file manifest with byte-for-byte SHA-256 checks. A
  default-font safety regression also keeps authored story/UI text ASCII-only,
  preventing unsupported smart punctuation and symbols from rendering as `?`.
  The alpha.18 suite contains 269 deterministic tests; `build.sh check`, all
  tests, the Python art verifier, and `git diff --check -- ar-odin` pass.

## 6.0.0-alpha.17 — The dungeon remembers its landmarks (ar-odin)

### MX.7 — World polish and raylib-suitable visual upgrades

- Completed the semantic minimap layer beyond MX.1 terrain projection. Bar and
  Garden markers now discover from any room tile on normal floors and persist;
  dark floors require live center visibility. Stairs discover on their own tile
  and remain marked after leaving LOS even on dark floors. Fixed tankard,
  sprout, and portal glyphs, viewport-preserving edge arrows, and an
  isometrically projected player-facing tick complete the navigation language;
  the documented dark-floor stairs route remains until story guidance returns.
- Replaced the three hard-coded Shop piles with a cached, deterministic,
  room-size-aware 7–12-stack layout. It uses all five authored gold assets and
  pygame's 0.72/0.92/1.14 size vocabulary, excludes keeper/sign anchors, enters
  the common painter list at tile x+y+0.5, and reserves population placement
  while remaining walk-through for collision and navigation.
- Hardened visual fallback safety. Lighting-dependent ground/prism margins now
  use current-frame compositor readiness rather than the requested option, so a
  render-target failure falls back to strict fog tint/culling. If the live-LOS
  effect shader is unavailable, wide decorative geometry is suppressed while
  compact gameplay cues require a fully live 3×3 footprint; nothing falls back
  to origin-only trails, rings, labels, bars, telegraphs, or numbers.
- Evaluated normal-map detail and retained the radial/LOS compositor. Full-size
  normals would significantly grow an already large decoded texture footprint,
  per-frame actor maps risk relief shimmer, and no capture/performance evidence
  demonstrated the clear upgrade required by the milestone; the optional pass
  therefore does not ship in alpha.17.
- Added `tools/capture_mx7.sh`: a deterministic fixed-step 46-shot matrix for all
  eight themes at shallow/deep normal/dark states plus doors, stairs, Shop, Bar,
  Garden, boss, crowd, loot, trap, shrine, secret, and masked/reveal FOW cases.
  Added `tools/profile_mx7.sh`: three uncapped release runs over a visible-crowd
  stress fixture with machine-readable mean/p95/p99/max timing and a 16.67 ms
  p95 gate; it deliberately refuses software GL for performance signoff.
- Added 9 deterministic tests in `tests/mx7_world_polish_test.odin` (231 total):
  normal/dark discovery asymmetry, marker targets, edge clamp/arrow geometry,
  projected facing, stairs ping-pong synchronization, Shop count matrix,
  placement validity/determinism, cosmetic-vs-collision reservations, and draw
  depth/scale contracts.
- Headless validation passed `build.sh check` and all 231 tests. The current
  environment has no display or Xvfb, so the 46-shot matrix and real-GPU frame
  timing remain the explicit Matti/hardware signoff step.

## 6.0.0-alpha.16 — Every strike tells the truth (ar-odin)

### MX.6 — Combat readability, animation state, and effects

- Restored the floor-level exact-aim cone behind actors and foreground
  occluders. The cone follows continuous tile-space aim through the isometric
  projection; sprite rows remain independently quantized, so presentation
  never feeds back into targeting.
- Enemy commits now retain an explicit `Attack`/`Cast` action and independent
  fixed-step recovery clock after the pending ability resets. Base melee and
  Strike select Attack; ranged base attacks and Bolt/Fan/Nova select Cast.
  Boss casts deliberately reuse the authored attack sheet, while ordinary
  enemies with no matching action sheet stay grounded in idle/walk and rely on
  the semantic cast/slash cue instead of snapping to a missing frame.
- Replaced circle-only bolts with six raylib-native silhouettes: one void form
  for enemies plus class-specific Warden guard, Rogue dagger, Arcanist arc,
  Acolyte spirit, and Ranger arrow forms. Every projectile keeps typed color,
  projected velocity rotation, a four-frame 12 FPS fixed-step cadence, and four
  deterministic trailing samples. Render age now interpolates with position
  instead of running one simulation tick ahead.
- Rebuilt melee feedback as a growing/fading crescent with three trailing
  strokes and endpoint sparks. Player swings land at the nearest contact
  midpoint (or 0.9 tile forward on a whiff), matching pygame for both base
  melee and Big Hit; lethal throws retain their knockback-travel envelope after
  the corpse is swept.
- Expanded the bounded, RNG-free `Feel_Event` vocabulary for cast, dash,
  Time Skip, Nova, summon/arrival, Spirit Beast command, Bell plant/arm/
  detonation, knockback travel, ranked deaths, boss payoff, and scoped flashes.
  Stable queue compaction preserves painter order, critical events replace the
  oldest lower-priority cue under saturation, and existing elite/miniboss/boss
  body-death timelines remain unchanged.
- Ambush Bells now own an explicit arm-announcement latch: timer crossings,
  restored/pre-armed Bells, and the second zero-dt lure pass all emit Bell Arm
  exactly once before any detonation.
- Effect lights join the existing glow target before its live-LOS multiply.
  Direct combat raster and damage labels are also clipped per fragment by the
  live visibility lattice—even when continuous lighting is disabled—while a
  shader-less platform falls back to origin-gated geometry rather than hiding
  effects. World-origin boss flashes remain LOS-scoped. A lighting-off Nova
  A/B capture verified that the full reveal ellipse crosses room walls while
  the normal render keeps only the visible in-room portion.
- Frost Nova now projects its true tile-space radius as a coherent isometric
  ellipse. A mastered room-engulf Nova adds a deterministic tile wave inside
  the same LOS-clipped light compositor instead of stretching the combat ring.
- Added the reusable `tools/capture_mx6.sh` harness and opt-in startup staging
  hooks. It builds once and records 34 deterministic captures: five archetypes
  across all four action slots, base melee, every enemy ability family, boss
  attack/cast fallback, Wisp/Crow/Spirit Beast attacks, all eight directions,
  and masked/reveal FOW comparisons. Captures are windowed, audio-free,
  self-contained under `build/mx6-captures`, and never mutate saved options.
- Added 21 deterministic tests in `tests/mx6_readability_test.odin` (222 total):
  exact aim, action classification/lifetime/fallback, familiar clocks,
  projectile style/cadence/rotation/trails, slash and knockback geometry,
  every semantic emission path, Bell exactly-once behavior, queue priority and
  stable compaction, RNG isolation, visibility/light profiles, ranged-boss
  close melee, preserved ranked-death envelopes, and lethal Big Hit cleanup.

## 6.0.0-alpha.15 — The dungeon pays what it promises (ar-odin)

### MX.5 — Interactables, secrets, uniques, and reward payoff

- New `interactables.odin`: all three traps (Spike/Rune/Needle) with pygame's
  hidden→revealing→revealed→spent lifecycle — permanent proximity reveal at
  1.35, linear dt*6 materialize fade, trigger at 0.55, unevadable damage
  through the typed player-damage path, depth (+1 per floor past 3) and
  difficulty (1.5x..3.35x) scaling at spawn, burst/floater feedback, and the
  formerly reserved trap cue.
- The seven single-player shrines (Mending, Insight, War, Haste, Fortune,
  Oath, Twilight) with their exact one-use effects: full restore, bag-wide
  identify, 25 XP + focus, the capped 0.03/0.09 permanent stride blessing
  through the real move channel, twin loot spills, a token-free random
  discipline grant, and blood (max(5, max_hp/10)) for a named unique. Per-kind
  hint colors drive prompt, floater, and a steady 2.3-tile identity light.
  Vigil Shrine stays multiplayer-deferred.
- Five secret kinds plus the per-floor Lost Cartographer's Stash: silent
  1.55-tile reveal with "Secret found", guarded interaction at 1.1, the
  Cursed Reliquary's short-circuited 55% guardian wake, Sealed Armory's two
  Magic pieces, Moonlit Bargain's blood-for-Rare, the Forgotten Skill Altar's
  free discipline, double stash payouts, run counters, and the secret cue.
- The orphaned `wall_face` bake is live: the worn wall_403 variant
  ((x*7+y*13)%10==2) briefly forms a face when touched — never advertised,
  dead last in the interact chain, 1s transient clip, run-counted.
- New `uniques.odin`: all 13 named uniques with authored flat stats that
  bypass the rolled-gear clamps, three display affixes, six new gear
  skill-bonus channels (Dash guard, Time Skip ward, Ambush Bell potency, Nova
  radius, Spirit Call ward, Spirit Beast bond) wired through the class-skill
  cost/cooldown/effect sites, and every bespoke hook: embers/chill on hit
  (guaranteed procs), steadfast bulwark/oathwall aegis armor and all-channel
  ward, counter smite, smoke crits (30% at x1.80), vanish on dash, splinter
  storm/sky volley fan pairs, glacial ward's frost resist + melee chill,
  pack pursuit snares, sanguine echo lifesteal, and grave chorus thorns.
  The 72%-archetype-biased generator gates unique armor behind depth 4 and
  feeds the 0.3%+ loot jackpot, the Twilight Shrine, and the Tyrant kill.
- Kill rewards match the contract: the Gate Tyrant guarantees a named Unique,
  floor guardians and Oathbound/challenge minibosses guarantee Rare
  equipment at a deterministic stairs-avoiding drop ring, and the ordinary
  28% roll stays independent for every rank. Rare+ finds land in a
  deduplicated 8-entry notable-loot ledger; both end-of-run summaries gain
  the modifier/shrines/secrets/traps/challenges/bars ledger and the last
  notable finds.
- Modifier pressure is now fully live: Trap-Laced's trap and shrine bonuses,
  encounter trap/secret pressure, and Cursed Bargains' curse chance reach
  real systems, so the MX.4 stairs preview's "heavy traps" tag stopped lying.
  Placement rolls run on their own stream (10), preserving pre-MX.5 enemy
  layouts per seed.
- Trap/shrine/secret audio cues flipped from future_emitter to runtime.
  Seven distinct shrine sprites plus a secret-cache display case were
  generated and baked as props (Pixellab, tag arch-rogue-shrines-6x) — the
  spec's intentional visual upgrade over pygame's single shared shrine prop.
  Regenerated at 128px after review: the first 84px multi-item pack baked
  faint caption text into the frame bottoms and read soft in-world.
- Shrines and sealed caches are room furniture rather than floor decals.
  Each owns its tile: a new `Dungeon.solid_props` registry feeds the existing
  reserved-tile predicate, so actor collision, the enemy route field, and
  enemy/loot placement all route around them for free. Placement runs before
  the actor pass and refuses the stairs mouth, a doorway's inner tile (the
  guard the bar furnishings already used), and any tile another prop holds;
  an opened cache hands its tile back before its reliquary guardian spawns.
  Sprite anchors were re-derived from each sprite's base diamond so every
  prop is centred on the tile it blocks, then scaled to a half-tile base
  (32-56 world px tall, in line with the bar barrels and tables) — the
  full-tile art towered over the actors. The contact shadows are gone, leaving a
  live shrine's glow and motes as its only effects; a spent shrine is inert
  stone. `dungeon_geometry_equal` keeps the difficulty-invariance test
  honest now that population-owned furniture rides along on the dungeon.
- 10 new deterministic tests in `tests/mx5_interactables_test.odin` (200
  total): unique construction/pool gates/bias, every stat and combat hook,
  fan and class-skill wiring, trap lifecycle, all shrine bargains, secret
  resolution including both reliquary branches, seed-stable placement,
  the kill-reward contract, and the wall-face touch.

## 6.0.0-alpha.14 — Ten floors become a descent (ar-odin)

### MX.4 — Descent plan, encounters, and floor-to-floor pressure

- New `floor_plan.odin`: all eight run modifiers (Blood Moon … Cursed
  Bargains, with the name-keyed pygame effects as explicit data) and six
  encounter templates ported verbatim from progression.py/enemies.py.
  `generate_run_plan` authors a deterministic ten-depth `Floor_Plan` at run
  start on its own stream (9, salt "PLAN"): no adjacent theme repeat, depth 1
  standard, authored challenge rooms and themed guardians on 3/6/9, the Gate
  Tyrant with the clear-record hint on 10, dark-floor schedule, capped risk
  tags, threat 1+depth/2 (+1 on guardian depths). Theme and darkness keep
  their pre-plan per-depth streams, so recorded seeds replay identically.
- The plan is applied, not just displayed: encounter enemy bonus joins before
  difficulty count scaling; elite/miniboss odds take template + Elite Hunt
  pressure inside the pygame clamps; modifier HP/damage/aggro press every
  spawn (guardians included) before difficulty; loot chance folds modifier +
  template bonuses inside the 0.12..0.88 clamp; Cursed Bargains adds +8%
  curse chance on floor and kill drops. Trap/shrine/secret pressure is
  carried as data for MX.5's live systems.
- challenge_room guarantees one marked Oathbound guardian in a random
  non-guardian-floor room (skipping safe special rooms so the guarantee
  holds); its death counts toward `challenge_rooms_cleared`. The guaranteed
  Rare drop stays with MX.5. Guardian floors keep sealed stairs; the boss
  identity now comes from the plan.
- Surfaced during play: a run header (depth/theme/dark, modifier with its
  description, wrapped floor summary that yields to the engaged boss bar) and
  a truthful next-floor stairs preview with theme, threat, risks, and reward.
  Boss `loot_hook` strings are ported with the stale "chance" wording
  reconciled to the bosses-guarantee-Unique / guardians-guarantee-Rare
  contract. The toast prompt now shows the pilgrimage count.
- Non-blocking arrival treatment: a fading depth/theme title card (theme
  flavor line in the theme accent) plus a brief dark screen fade — no
  artificial loading stall. Combat-boundary reset and the exact 25%
  mana/stamina recovery are untouched and now pinned by test.
- Bars are tracked run-wide: `bars_visited` counts where floors are created,
  `bars_toasted` on each toast, neither resets on descent (the per-floor
  one-free-ale gate still does). Arriving at depth 10 — or completing the
  toast there — summons the immortal fighting Bar Dancer (46 HP / 7 damage /
  3.5 speed, physical strikes, HP floors at 1 and regenerates, dances through
  idle and attack, survives class summon recasts).
- 8 new deterministic tests in `tests/mx4_descent_test.odin` (190 total):
  plan determinism and authored structure, floors following the plan,
  modifier stat math, clamped odds bonuses, the guaranteed challenge
  guardian + clear tracking, the Bar ledger/dancer lifecycle, the stairs
  preview, and the quarter-pool descent recovery.

## 6.0.0-alpha.13 — Every purchase now does what it says (ar-odin)

### MX.3 — Build-defining combat and discipline effects

- All 62 formerly Deferred/Partially_Wired discipline ledger entries are wired
  to their player-facing text and reclassified `Fully_Wired` (new coverage
  member); the census test now demands 38 Stats_Only + 62 Fully_Wired so a
  regressing node fails by count.
- Warden: Bulwark cleave tiers (reach +0.22/0.28/0.35, 2/3/4 targets, 0.62
  falloff, +0.02 swing cooldown), Riposte's −2 melee guard and holy
  counterattack (level+armor, min 2, stun with Aegis Discipline), Guard Step's
  0.85 s Aegis hardening, Aegis holy stun swings, and the Time path: Sigil
  cost/cooldown/duration riders, Bulwark Wave's +1.0 s and 2.6-tile stun
  pulse, Stutter Step's 0.3 factor (live), Temporal Aegis +0.20 resist, and
  Eternal Moment's 40% cooldown refund on kills during the skip.
- Rogue: Precision −2 melee stamina; Smoke's +2 dash steps, −2 dash stamina,
  0.9 s dash smoke, and 0.18/+0.22 evade tiers; Venom's poison Knife Fan; and
  the complete Ambush Bell tuning snapshot (arm/lifetime/lure/trigger/blast
  geometry, poison and snare payloads, smoke stacking, expired scale, facing
  multipliers, pygame clamps) with the live detonation chain: Precision-ladder
  adders/multipliers, the bell crit table, splash snares, and the Engineer's
  Bell Reprise cooldown floor + mana refund.
- Arcanist: Splinter's 2-shard 1.55 s fan, Overload's 3-fan + pierce, deeper
  Pierce, Conduit Sigil's 0.82 pierce falloff, Arc Tyrant homing (0.85, 6.5
  acquisition, LOS), Charge's −1 bolt mana, Focus/Ward mana regen, Nova radius
  from path rank (2.45 + 0.55/node), Permafrost's 1.9 s chill and chilled
  melee, Absolute Zero's two-mastered-paths room engulf, and the shared
  one-charge-per-cast Storm chain (1/2/3/4 hops at 2.6/2.8/3.2/3.6 tiles, 55%
  flat hop damage, status at 0.7 duration, elite priority at Storm Caller+).
- Acolyte: live Blood siphon ladders for melee (2..6) and spells/familiars
  (3..8) replacing the flat gear +1, Blood Pact's +0.03 lifesteal, Veil's
  5-point mana shield, −2 skill cost, and +2.0 mana regen, Curse regen, and
  Gravebind's 1.1/1.2 s binds plus the grave-echo heal+mana on bound kills.
- Ranger: Multishot fans (3/4/5 arrows), piercing and Sky Quiver homing
  arrows, Barbed Snares' 1.1 s arrow snare and +4 stamina regen, Beastmark's
  melee snare, 1.22 snared-prey amp (all mitigated player damage, beast bites
  included), and Vault's +8 stamina / 0.12 s Multishot refund.
- Companions: Spirit Beast bites read the build live — Pack Tactics ×1.25 on
  snared prey, Primal Lord ×1.35 on elite/miniboss/boss, Spirit Companion
  arcane conversion, Alpha's 0.22-tile shove — and blood-bound familiars
  siphon the live spell ladder to the Acolyte.
- The non-story petting slice: last-priority interact with world prompt,
  strict 1.5-tile LOS readiness, 2 s cooldown, 2·2^degree heal, paired
  facing pose driving the baked `pet` clips, and full suspension of the beast
  during the ritual. Fixed Spirit Beast attack playback to run the Attack clip
  on its own elapsed clock instead of the stalled locomotion `anim_time`.
- Nineteen new headless tests pin every slice with pygame-cited constants
  (182 total, deterministic and warning-clean).

## 6.0.0-alpha.12 — The dungeon fights back (ar-odin)

### MX.2 — Combat correctness, bosses, and enemy intelligence

- Boss attack selection now ports pygame's `combat/abilities.py` contract:
  bolt/fan abilities inherit a six-tile cast reach, the rotation softly avoids
  repeating the last authored ability, an all-on-cooldown boss falls back to
  the legacy cast band (`2.0 < d <= 6.0`, a 3-bolt fan even for melee-classed
  bosses) or melee, and authored cooldowns recycle at 0.8x below half health.
  The Dread Gate Tyrant's Shadow Volley — previously unreachable because its
  2.0 minimum range exceeded the inherited 1.9 reach — now alternates with
  Gate Strike exactly as authored. Boss windups base at 0.25 s.
- Enemy tactics are a doctrine axis separate from rank: the nine authored
  doctrines (bruiser/mauler/guard/flanker/skirmisher/caster/marksman/
  artillery/sentinel) drive per-kind range bands, cooldown strafing,
  hold-anchor sentinels, flanker approach curves, and LOS repositioning.
  Aggro is distance-only with one-hop pack alerts (4-tile radius) and a 4 s
  target memory that walks enemies to the last noticed position before they
  stand down. The whole tactical layer is deterministic and consumes no RNG.
- Enemies route around walls and bar furnishings on a radius-24 unit-cost
  navigation field (BFS with a closed-corner rule, rebuilt on tile crossing or
  every 0.5 s), keeping greedy straight-line motion whenever the direct route
  is genuinely short and furnishing-free. Stall recovery: perpendicular
  slides, a 0.8 s field latch, a 0.9 s net-displacement watchdog, and 0.55 s
  doorway yields to packmates strictly closer to the player.
- Knockback is one physics: ordinary melee and player projectiles now ride
  the same exponentially decaying collision-safe velocity path as Big Hit
  (v0 1.6, decay 10), and momentum at or above 4.0 chains through pack cones
  at 0.85 transfer without ever moving a 2x2 boss. Actor separation uses real
  per-class body radii instead of one fixed 0.55 bubble, resolved through
  wall-aware slides.
- Elites wear their identity again: modifier name prefixes ("Frenzied Ghoul"),
  authored palette shifts, and doctrine reassignment (Frenzied/Venomous fight
  as flankers, Ironbound holds as a guard — deliberately dropping a ranged
  elite to the default band). Minibosses are titled Oathbound, wear the theme
  accent, and both ranks get distinct death emphasis. Seven new headless tests
  pin the selector bands, rotation, doctrine bands, alerts, routing,
  knockback chains, and identity (163 total).

## 6.0.0-alpha.11 — Mist settles into the halls (ar-odin)

### HUD and panel padding pass

- The bottom HUD bar now docks flush to the window bottom at full width, with
  a uniform 24 px content margin; the gold/bag readout right-aligns to that
  margin and the interact prompt moved up clear of the taller dock. Character
  and inventory panels gained breathing room on all sides (inventory grew to
  408x552 with right-aligned sort chips; character cards re-centered at a
  symmetric 40 px gutter). Overview/Disciplines tabs and shop BUY/SELL chips
  widened so labels live inside the arrow-endcap row art's authored safe rail
  (draw_menu_row_chrome now honors any rail >= 48 px and callers shrink fonts
  to fit) instead of overlapping the arch/arrow caps. First rough pass —
  refinement deferred. New `ARCH_ROGUE_OPEN=inventory|character|shop` hook
  opens a panel at boot for UI screenshots.

### Ambient dungeon mist

- A seeded ~42% of each floor's rooms now hold drifting mist banks that lap a
  few tiles through doorways and corridor mouths; the remaining rooms, all
  corridors beyond the lap, and shop/bar/garden interiors stay clear, so a
  fogged chamber reads as a change of place rather than a screen filter. Zones
  are dealt per floor from a derived seed and rebuilt on descent/regeneration.
- The mist body is the rewrite's first GLSL shader: domain-warped noise
  drifting in tile space, drawn inside the world pass after actors so the
  light compositor still lights it (lantern-warm nearby, dim in explored
  memory, black past the LOS frontier — dark floors leak nothing). The CPU
  uploads only a per-tile disturbance field on the existing diagonal lattice.
- Actors disturb the mist: presence parts a small pocket, movement carves a
  wider wake and shoves the noise field along the motion (speed-scaled, dash
  saturating), projectiles poke thin trails, and 2x2 bosses displace a larger
  footprint. Carved wakes refill over a few seconds and shoved mist settles
  back, all frame-rate independent. Policy constants live in `visuals.odin`
  and are pinned by four new headless tests (156 total).
- New persisted Options row "Mist" (additive schema, old files default on),
  and an unpersisted `ARCH_ROGUE_MIST=0` hook for benchmark/screenshot A/B.

## 6.0.0-alpha.10 — The dark learns to breathe (ar-odin)

### M6 — Lighting, fog, shadows, and visual polish

- The raylib renderer now carries two GPU-resident diagonal isometric fields:
  persistent explored memory on normal floors and strict live LOS on every
  floor. Bilinear lattice filtering plus frame-rate-independent reveal easing
  replaces hard tile-diamond fog edges, while concealment snaps immediately so
  light and effects never linger through a newly closed wall or door. One-ring
  black ground margins and south-frontier prism staging remove tile/wall pop-in
  without drawing unknown terrain into view.
- Normal floors now use the Pygame depth curve and theme-colored ambient wash,
  fading from `0.576` at depth 1 to `0.18` at depth 10; dark floors retain their
  `0.10` cave ambient and four-tile lantern. Player, projectile, stair, refuge,
  and transient lights are clipped by current LOS, and the player/sconces gain
  restrained deterministic flicker.
- Players, enemies, familiars, loot, bells, social actors, and grounded props
  receive soft contact shadows. Foreground walls and doors now trigger the
  mature actor shine-through treatment: depth/coverage-weighted, temporally
  eased warm aura plus translucent authored silhouette, still multiplied by
  darkness and restricted to actors already admitted by gameplay visibility.
- Painter order is deterministic at doorway ties, actor ghost identities are
  stable and namespaced, enemy bars stay under foreground masonry, hidden
  labels/numbers/lights no longer leak through FOW, and floor topology changes
  refresh LOS before the next frame. Authored idle sheets now animate from a
  render-only clock without reviving blocked locomotion frames.
- Lighting resources validate and unload explicitly, disabled lighting avoids
  full-screen render targets, settled masks skip GPU uploads, and dark floors
  reuse the live field. Development telemetry/control help is hidden outside
  `ARCH_ROGUE_DEV=1`. Deterministic AMD/OpenGL captures at depth 1 and depth-10
  normal/dark floors verified projection, smooth edges, ambient separation, and
  resource shutdown; the suite is warning-clean at 138 headless tests.

## 6.0.0-alpha.9 — The descent finds its rhythm (ar-odin)

### M10 — Audio, feel & parity audit

- Actor presentation now follows simulation truth: idle and wall-blocked actors
  no longer consume walk frames, partial movement and slows scale cadence, and
  committed enemy windups keep a fresh duration/elapsed clock. Player melee,
  Big Hit, bolt, dash, all class skills, death, and corpse states select
  explicit authored action timelines; cast/die/dead sheets for all five
  archetypes are baked and manifest-validated.
- Combat emits a bounded deterministic presentation-event stream for slash,
  typed hit, blood, death, boss-burst, and screen-pain cues. Heavy hits use the
  source 18% threshold, bosses retain longer flashes, enemy telegraphs preserve
  their committed aim, and death plays its authored sequence before showing the
  same level/kills/gold summary as victory. Pygame contains neither hit-stop nor
  camera shake, so parity deliberately adds neither.
- Desktop camera follow/framing now uses the source 14/s smoothing, 48% vertical
  focus, centered zoom, and 2.0 default with the canonical 1.625-4.0 range. The
  final Gate Tyrant receives its missing 2.4x HP/+9 damage/faster recovery pass,
  while large ranged boss fallback attacks retain the canonical three-bolt fan.
- Authored cues now have a complete checked PCM-WAV manifest, safe validity and
  unload lifecycle, independent cue gating, and semantic start/UI/Bell/boss/
  victory/Bar routing. Trap, shrine, and secret takes are reserved for those
  still-unported systems. Background music is intentionally not guessed here:
  incoming tracks and their better specification will define that runtime next.
- M10's feature audit is complete, not a false declaration of full parity. The
  remaining gameplay/content and visual gaps are catalogued in `PARITY.md`; the
  next pass is the requested side-by-side visual refinement. The warning-clean
  headless suite now passes 131 deterministic tests.

## 6.0.0-alpha.8 — The descent gets a front door (ar-odin)

### M9 — Character, meta & shell

- The full 100-node discipline table is ported with memory-token spending,
  prerequisite and two-path rules, completion/cross-path bonuses, live Rogue
  Precision and familiar rank integration, and explicit effect-coverage
  tracking. The Character screen now provides mouse, keyboard, and gamepad
  navigation plus XP, typed offense, class output, equipment, upgrades, and
  status/proc summaries; its unspent-Memory prompt is clickable.
- Easy, Medium, Hard, and first-clear-unlocked Hell profiles now scale spawned
  enemies and encounter density without perturbing dungeon geometry. The
  persistent Options shell applies fullscreen, FPS cap, view zoom, difficulty,
  controller, authored audio-cue, lighting, minimap, and gamepad-map settings;
  Title and Pause provide proper New Run/Resume/Options/Return/Quit flows.
- Raylib gamepads use pygame's semantic layout, radial deadzones, menu
  hysteresis, right-stick target snap, overlay-aware commands, and a live
  collision-safe button/trigger remap screen. Face-button and trigger Big Hit
  releases remain latched across modal screens.
- Shop, Bar, and Garden special rooms now roll at the canonical 75%/50%/50%,
  claim distinct sealed side rooms, and carry authored floors, walls, actors,
  props, minimap colors, and lights. Shops have deterministic stock and atomic
  buy/sell economics; refuge healing and the Bar's one toast follow source
  formulas. Bars request 2-4 solid barrels and 2-4 solid tables through the
  same greedy spacing pass as Pygame (cramped rooms may fit fewer); special-room
  actors and those Bar furnishings reserve population and collision space.
- The earlier one-door first floor was explained and resolved: alpha.7 had only
  the ordinary 24% room-seal roll plus an anti-doorless fallback; alpha.8 adds
  the missing non-story special-room seals. Story-only quest/soul rooms remain
  intentionally deferred. The warning-clean headless suite now passes 117
  deterministic tests.

## 6.0.0-alpha.7 — Combat finds its teeth (ar-odin)

### M8 — Combat depth

- All five archetypes now use pygame's six-slot desktop loadout: charged Big
  Hit, core bolt, real class skill, dash, healing potion, and mana potion.
  Time Skip, Ambush Bell, Frost Nova, Spirit Call, and Spirit Beast have their
  ported costs, independent cooldowns, damage, movement, and resource rules.
- Combat now carries physical, fire, frost, poison, arcane, holy, and shadow
  damage through enemy/player resistance math and colored floaters. Poison,
  chill, burn, snare, bind, stun, smoke, and aegis state drives damage, motion,
  AI interruption, and status pips.
- Acolyte wisps and Ranger's commandable Spirit Beast join the fixed-step sim
  with LOS targeting, wall-safe movement, retaliation, projectile interception,
  health bars, and authored actor sheets. Crow hosts and Rogue Precision ranks
  are fully modeled and tested for M9's discipline unlocks; fresh characters
  retain pygame's rank-zero Wisp/no-Precision baseline.
- Equipment now uses the complete 35-affix table with multi-stat rolls,
  attack/cast/move speed, typed and proc effects, lifesteal, thorns, skill
  bonuses, rarity caps, and an isolated combat RNG stream. Cursed and
  unidentified gear, Identify Scrolls, Remove Curse Scrolls, curse slot locks,
  and hidden inventory presentation follow the pygame rules.
- The authored six-slot HUD icons and familiar animation sheets are baked and
  vendored under `ar-odin/assets/`; runtime loading keeps geometry fallbacks.
  Floor descent clears combat recoveries/summons, cancels a charged strike, and
  restores 25% mana/stamina. The headless suite now passes 80 deterministic
  tests covering the M8 tables and combat seams.

## 6.0.0-alpha.6 — The rewrite starts and plays (ar-odin)

Milestone `6-odin` reaches its bar: a complete experimental rewrite of the
game in **Odin + raylib**, self-contained under `ar-odin/`, now boots from
a title screen into a playable run — archetype select (all five, real
sprites), procedural floors ported from the pygame generator (rooms,
corridors, door-sealed side rooms, boss arenas), real-time combat against
the starter roster (chase/windup AI, kite bands, telegraphs), signature
skills, loot with rarity tiers and affixes, potions, XP levels, per-depth
scaling, dark floors with a multiply lightmap, first authored SFX, and the
death → rise-again loop. Deterministic fixed-step sim with seeded PCG
streams throughout; 28 headless tests. The pygame game is untouched; the
rewrite versions independently as 6.x inside `ar-odin/` (see
`ar-odin/ARCHITECTURE.md` for decisions, hard rules, and milestones).

### M6/M7 parity work

- Desktop mouse and keyboard controls now follow the pygame game on the
  systems currently present in the rewrite: world-axis WASD/arrows,
  continuous cursor aim, held-left-click walking with a 0.12-tile stop and
  target-gated auto-melee, `E` pickup/interact, signature actions in their
  matching slot, potions on `5`/`6`, and no right-click combat binding.
- Inventory now pauses the simulation, clamps and scrolls keyboard selection,
  supports Pygame's navigation/use/drop/sort shortcuts, and adds pointer sort
  chips plus hover and same-row double-click equip. Archetype rows likewise
  preview on hover/single click and start on double click; number keys `1`-`5`
  start directly. Death/victory return to archetype selection with `R`, Back,
  or a click rather than silently restarting.
- Viewport zoom is `Ctrl`+wheel only. Plain wheel over the minimap changes map
  scale, `Ctrl+M` toggles it, and progression-skipping `N`/`R`/`B` shortcuts
  require the explicit `ARCH_ROGUE_DEV=1` developer hook. The headless suite
  now covers 52 deterministic tests, including short-click latching,
  player-before-enemy auto-melee, pointer double-click timing, inventory
  controls, and the raylib-free desktop input resolver.
