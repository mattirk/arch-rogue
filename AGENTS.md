# Arch Rogue — Agent Brief

## Project Vision

Arch Rogue is a modernized take on the classic Rogue formula: a dark, dangerous, replayable dungeon crawler presented as a grim isometric action RPG. The game should preserve Rogue's procedural depth, permanent consequences, discovery, and tension while introducing modern combat feel, progression systems, accessibility, and presentation.

## Core Pitch

- **Genre:** Isometric action RPG / roguelike dungeon crawler
- **Inspirations:** Rogue, classic dark fantasy dungeon crawlers, modern ARPG quality-of-life systems
- **Camera:** Fixed or semi-fixed isometric perspective
- **Theme:** Grim fantasy, ancient ruins, cursed depths, occult treasures, hostile wilderness, and underground labyrinths
- **Session Style:** Replayable runs with meaningful progression, procedural maps, unpredictable loot, and high-stakes decisions

## Optimization
Analyze, write, and optimize game code to maintain a stable 60+ FPS while preserving readability, input responsiveness, and clear combat feedback.

## Technology
- **Programming Language:** Python
- **Game Engine:** Pygame CE: https://pypi.org/project/pygame-ce/ 

## Development Commands

Run commands from the repository root (`arch-rogue/`). Use a local virtual environment for development:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Compile/syntax-check the project with Python bytecode compilation:

```bash
python -m compileall src tests
```

Run the full automated test suite with `unittest`:

```bash
python -m unittest discover tests
```

Run one milestone test module when iterating on a focused change:

```bash
python -m unittest tests.test_dark_levels
```

Notes for agents:
- The project currently uses `unittest`; `pytest` is not required.
- Test modules configure dummy SDL video/audio drivers for headless Pygame runs.
- Prefer running the focused test module for the code you changed, then `python -m unittest discover tests` before finalizing broader changes.

## Current Code Organization

NOTE: This project uses vibe architecture. Module structure is changed when new features require it or game.py gets bloated.

There is an experimental web build in `src/arch_rogue/web` and some specific tests related to it. Do not run web tests by default.

Keep the prototype architecture modular but intentionally small:

- `src/arch_rogue/game.py` owns `Game` construction, high-level app state, main loop wiring, and the executable `main()` entry point. Keep `arch_rogue.game.Game` and `arch_rogue.game:main` stable.
- Runtime behavior is composed through focused mixins:
  - `src/arch_rogue/camera.py` for coordinate transforms and visible bounds.
  - `src/arch_rogue/options.py` for display/options, difficulty selection, meta-progress defaults, and audio sync helpers.
  - `src/arch_rogue/run_flow.py` for run lifecycle, floor planning, dark-floor visibility, and run meta-progress.
  - `src/arch_rogue/population.py` for dungeon population, enemies, bosses, shops, loot, affixes, and unique item creation.
  - `src/arch_rogue/combat.py` for player/enemy simulation, combat abilities, damage, statuses, cooldowns, and kill rewards.
  - `src/arch_rogue/story_runtime.py` for story mode runtime, quest cutscenes, relic choices, guest interactions, and story rewards.
  - `src/arch_rogue/inventory.py`, `src/arch_rogue/shop.py`, and `src/arch_rogue/interactions.py` for focused player interaction systems.
  - `src/arch_rogue/save_system.py` for item/run-state serialization, restoration, and save-file lifecycle behavior used by `Game`.
- `src/arch_rogue/rendering/` owns the `RenderingMixin` package for dungeon/world, actor, effect, HUD, and story/cutscene drawing behavior. Preserve `from arch_rogue.rendering import RenderingMixin` compatibility.
- `src/arch_rogue/menus/` owns the `MenuRenderer` package for title, options, character, inventory, and state overlay menus. Preserve `from arch_rogue.menus import MenuRenderer` compatibility.
- `src/arch_rogue/content/` owns content-table modules for definitions, archetypes/themes, enemies/bosses/encounters, equipment/rarity, difficulty, interactables, progression, and story corpus. Preserve imports from `arch_rogue.content` through the package facade.
- `src/arch_rogue/story.py` owns deterministic story generation, story-state serialization helpers, guest construction, and choice-effect aggregation used by `Game` and saves.
- `src/arch_rogue/constants.py` owns shared gameplay/rendering constants and lightweight aliases.
- `src/arch_rogue/models.py` owns lightweight gameplay data models and shared simple types such as actors, items, projectiles, rooms, tiles, story beats, and guests.
- `src/arch_rogue/dungeon.py` owns procedural map generation and dungeon collision/floor queries.
- `src/arch_rogue/sprites.py` owns procedural pixel-art sprite construction.
- `src/arch_rogue/audio.py` owns mixer setup, procedural sound effects, and per-run procedural NES-style background music generation.

Prefer expanding these focused modules until a new boundary is clearly justified. Avoid introducing many narrow submodules during prototype work.

## Design Pillars

1. **Rogue at the Core**
   - Procedural dungeon generation
   - Risk/reward exploration
   - Scarce resources
   - Dangerous unidentified items
   - Permanent or semi-permanent consequences
   - Emergent problem solving over scripted solutions

2. **Dark Fantasy Action-RPG Feel**
   - Real-time combat with pause option
   - Distinct character archetypes
   - Loot-driven progression
   - Isometric presentation
   - Skill builds and equipment synergies
   - Dark fantasy atmosphere

3. **Modern Mechanics**
   - Clear combat telegraphs where appropriate
   - Smooth input handling
   - Strong controller and mouse/keyboard support
   - Readable UI and inventory management
   - Build diversity without excessive complexity
   - Optional meta-progression that does not remove run tension

4. **Replayability First**
   - Procedural levels, encounters, loot, events, traps, shrines, and bosses
   - Multiple viable playstyles
   - Meaningful choices during each run
   - Secrets, rare events, and surprising item interactions

## Initial Gameplay Goals

### Exploration

- Generate dungeon floors with rooms, corridors, chokepoints, secrets, hazards, and themed regions.
- Reward careful exploration with loot, shortcuts, lore fragments, and hidden encounters.
- Include classic roguelike uncertainty through unidentified potions, scrolls, relics, curses, and traps.

### Combat

- Use real-time isometric combat rather than turn-based movement.
- Prioritize readable enemy behavior, positioning, cooldowns, and tactical movement.
- Support melee, ranged, magic, traps, summons, and hybrid builds.
- Encourage decision-making through stamina, mana, cooldowns, durability, consumables, and enemy resistances.

### Progression

- Characters should gain power through:
  - Experience and levels
  - Skills and passive talents
  - Equipment and affixes
  - Relics or artifacts
  - Temporary run-based blessings, curses, or mutations
- Preserve danger by ensuring progression creates options rather than guaranteed safety.

### Loot

- Loot should be exciting, readable, and build-defining.
- Include item rarity tiers such as common, magic, rare, unique, cursed, and legendary/artifact.
- Support affixes inspired by ARPGs: damage types, resistances, lifesteal, cast speed, movement speed, thorns, proc effects, summons, and skill modifiers.
- Cursed items should be tempting, not merely bad.

## Character Archetypes

- **Warden:** Durable melee fighter with shields, counters, guard breaks, and armor mastery.
- **Rogue:** Fast striker using daggers, bows, traps, poison, evasion, and critical hits.
- **Arcanist:** Spellcaster using elemental, arcane, curse, and teleportation magic.
- **Acolyte:** Dark priest using sacrifice, healing, spirits, blood magic, and undead control.
- **Ranger:** Mobility-focused ranged class using bows, beasts, snares, and terrain control.

## Example Skill System Direction

Skills should support both active abilities and passive modifiers. Prefer flexible build paths over rigid linear trees.

Example categories:

- **Combat Skills:** Cleave, Shield Bash, Backstab, Multishot, Firebolt, Frost Nova
- **Mobility Skills:** Dash, Blink, Shadowstep, Leap, Vault
- **Control Skills:** Slow, Root, Fear, Knockback, Stun, Silence
- **Survival Skills:** Guard, Barrier, Lifesteal, Regeneration, Dodge, Cleanse
- **Summoning Skills:** Skeleton, Familiar, Totem, Spirit Guardian
- **Utility Skills:** Identify, Disarm Trap, Reveal Secret, Town Portal, Enchant Item

## World and Atmosphere

- Tone should be dark, mysterious, and dangerous rather than heroic power fantasy only.
- The dungeon should feel ancient, hostile, and reactive.
- Lore should be discoverable through items, shrines, enemy factions, environmental storytelling, and rare NPC encounters.
- Avoid excessive exposition during gameplay; preserve mystery.

## Development Guidelines

- Build systems modularly so procedural content, combat, items, and skills can evolve independently.
- Prefer data-driven definitions for items, enemies, skills, affixes, rooms, events, and loot tables.
- Keep early prototypes focused on feel: movement, combat readability, loot feedback, and dungeon traversal.
- Avoid overbuilding meta-progression before the core run loop is fun.
- When choosing between authenticity to Rogue and modern playability, preserve the spirit of Rogue while modernizing the interface and moment-to-moment feel.
- Do not ask for confirmation on sprite asset generation via MCP or other tools / APIs. Spend as much as you like. Inform user if limit has been reached.

### Asset graphics generation guide

- Generate all asset sprites using Pixellab (or similar) MCP server/tools
- For each actor, first generate base sprite, then rotations and after that, animations
- Keep all animations neatly grouped within the service so they can be easily managed by the user
  - Naming conventions for animation groups are: idle, walk, run, hit and cast (later dance, petting). You may extend these with good taste.
- Workflow when generating animations:
  - Create requested animation group with 8-directional animations (never create duplicates)
  - Validate each animation direction and all frames within it (natural movement, keep weapons, apparell and body parts visible)
  - When requested animations have been generated, pause and let the user validate the results
  - When the user request change for specific animation (e.g walk south), edit that animation within already existing group (do not create new one)
- Do not generate multiple states for single character without good reason
- Always use exact character names e.g "Arcanist" or "Rogue" for current character. If you need to preserve old characters, rename them (e.g "Arcanist" -> "Arcanist_old_1") before creating new ones 


## Milestones / Versions

Always update CHANGELOG.md content and pyproject.toml version number when completing milestones!

### 4.3 Mobile support (Android) + APK build

#### 4.3.0 Android beta

- Prove the Pygame CE Android toolchain and produce a reproducible, installable debug APK with all assets bundled.
- Add a landscape-only, safe-area-aware layout based on `build/arch-rogue_mobile_layout.drawio.png`: centered gameplay, left health/mana/stamina and optional character info, right action skills 1–6.
  - Generate new assets if necessary for mobile
  - Existing action skill badges can be used
  - Skills panel may just be rotated to support mobile (or generate new if necessary)
  - Health/mana/stamina need vertical bars / panel components
- Add direct world touch for movement/aim plus touch controls for skills, interaction, pause, and every menu/overlay; keep desktop and gamepad controls unchanged.
- Handle Android Back, pause/resume, audio focus, writable save/options paths, and interrupted-run recovery.
- Test representative phones/tablets, aspect ratios, and display cutouts; target stable 60 FPS and a complete playable run.
- Publish a signed beta APK with install, upgrade, feedback, and known-issues notes.
  - Self-signed apk is good enough for now, since we are in beta
  - Include necessary steps into gh build release 

#### 4.3.20 Android beta to mainline merge

Merge the `android-beta` branch (currently 19 commits ahead of `master`, fast-forwardable) into `master` so the desktop mainline only benefits from the Android work, never regresses. Lock both desktop and mobile to a 60 FPS cap, clean up leftover optimization code from the 4.3.0–4.3.16 runs, and consolidate the architecture.

Inspirational target release: `4.3.17`. Schema advances from `6` → `7` only for the new frame-rate option; run saves remain schema `5`.

##### Goals

- Bring Android beta improvements to `master` so desktop inherits the universal wins (impact cache, cached projection origin, full-bleed cutscene, direct-size shadows, cached relic guidance, batched wall blits).
- Lock desktop **and** mobile to a 60 FPS hard cap by default, expressed through one `FramePacing` abstraction instead of scattered `clock.tick(FPS)` calls. Mobile suspended mode keeps its 10 Hz throttle.
- Remove dead/duplicated optimization code accumulated across the 4.3.x optimization runs.
- Mainline (desktop) render determinism, frame timing, and input behavior must not regress. Mobile-only code paths must remain strictly additive (`if self.mobile_mode:` branches).
- Preserve the modular architecture from the brief: focused mixins, `mobile.py` keeps owning mobile-only concerns, no leakage of GLES/Android specifics into the core rendering pipeline.
- Keep game graphics and visuals consistent across desktop and mobile.
- Make sure Github actions build for Android (and other targets) is well designed, robust and produces reliable builds.

##### Non-goals

- New gameplay features, balance changes, or new archetypes.
- iOS, desktop touch, or web targets.
- Replacing the desktop rendering pipeline with the Android GLES presenter.
- Renaming public stable entry points (`arch_rogue.game.Game`, `arch_rogue.game:main`).

##### Architecture principles for this merge

1. **Mobile stays additive.** Every Android-specific branch is gated by `self.mobile_mode` (or `android_runtime_active()` for import-time checks). No desktop frame ever executes a GLES upload, colorkey-RLE benchmark, or `MobilePerformanceMonitor` block.
2. **One frame-pacing owner.** A single `FramePacing` object owns `target_fps`, `suspended_fps`, `clock.tick`, dt clamp, and the optional vsync hint. `Game.run()` reads from it; nothing else calls `clock.tick`.
3. **Universal wins are shared; ARM-specific wins stay mobile.** Caching, fewer allocations, batched blits, and projection-origin memoization belong in the shared rendering path. Colorkey-RLE optimization, the GLES direct presenter, and `ARCH_ROGUE_PERF` telemetry stay in `mobile.py`.
4. **One cache-invalidation seam.** All render caches invalidated by graphics-mode / resolution / font changes flow through a single `_invalidate_render_caches()` method, so future changes cannot miss a cache.
5. **Telemetry defaults off on desktop.** `ARCH_ROGUE_PERF` stays Android-by-default; a new desktop dev option enables the same overlay for profiling, off in production.

##### Workstreams

The merge is sequenced so the safest, most foundational work lands first and the riskier refactors land after the regression guard exists.

###### WS-A — Frame pacing and FPS cap consolidation

- Add a small `FramePacing` class (in `game.py` unless that file grows past ~1400 lines, in which case split into `src/arch_rogue/frame_pacing.py`). It owns:
  - `target_fps` (default `60`)
  - `suspended_fps` (`10`, used only when Android is backgrounded)
  - `clock.tick(target_fps)` semantics, dt clamped to `0.05` (preserved)
  - `vsync` flag (off by default; SDL's `SCALED` renderer handles vsync internally on Android)
- Add an Options row **Frame rate cap** with values `30 / 60 / 90 / 120 / Unlimited`, default `60`, persisted as `frame_rate_cap` in schema `7`. Both desktop and mobile read the same setting; mobile suspended mode overrides to `suspended_fps` regardless.
- Replace the bare `FPS` constant in `constants.py` with `DEFAULT_FRAME_RATE = 60`. Keep `FPS` as a deprecated alias for one release to avoid breaking external callers and tests.
- Update `Game.run()` to read `target_fps` from `FramePacing` (which reads the option) instead of the constant. The `min(self.clock.tick(target_fps) / 1000.0, 0.05)` shape is preserved verbatim — only the source of `target_fps` changes.
- Acceptance: a default desktop run on a 144 Hz monitor reports exactly 60 FPS in both the FPS counter and `clock.get_fps()`; mobile reports 60 FPS active and 10 FPS suspended.

###### WS-B — Mainline regression guard (lands before risky refactors)

- Add `tests/test_mainline_regression.py`:
  - Snapshots desktop render determinism on the dummy SDL driver — a fixed seed and fixed frame number produces a fixed pixel hash for title, gameplay, and a crowd scenario. Any drift fails the test.
  - Asserts `detect_mobile_runtime() is False` for non-Android `sys.platform` and that no `mobile_mode`-gated branch executes during a desktop `Game.run()` tick (instrument with a counter mixin for the test).
- Extend `tools/profile_game.py` with a `--baseline <path>` mode that writes a JSON snapshot of phase timings and a `--compare <path>` mode that fails if any phase regresses by more than 10%. Check in a `tools/baselines/desktop_master_baseline.json` generated from `master` before the merge.
- Add a CI job (or extend the existing test job) that runs the regression test + baseline comparison on every push to `android-beta` and `master`.

###### WS-C — Leftover optimization code cleanup

File-by-file sweep, each commit independently green and bisectable. Specific targets:

- `src/arch_rogue/lighting.py`:
  - Confirm whether the local-tint CPU fallback (currently "launch/context-loss fallback for software renderers") is still reachable on any supported Android device after 4.3.10's accelerated-Native quarter-resolution lighting. If only Android software-renderer reaches it, gate it tighter and document the gate. Do **not** remove it — it's the launch-safe path.
  - Remove the dead half-resolution light buffer path superseded by 4.3.5's quarter-resolution buffer if no code path constructs it anymore. Verify with `grep`.
- `src/arch_rogue/mobile.py`:
  - `_ANDROID_BINARY_ALPHA_MODE` benchmark runs once per process; confirm the min-area guard (`_ANDROID_BINARY_ALPHA_MIN_BENCHMARK_AREA`) is the right threshold and that the chosen mode is reused, not re-benchmarked.
  - `MobilePerformanceMonitor.finish_frame` is ~200 lines; audit for per-frame allocations and confirm the rolling buffers are pre-allocated (the docstring claims "low-overhead"; verify).
  - Remove the `_composite_mobile_gpu_ui_fallback` `legacy` rect branch if it's unreachable after 4.3.11's full-bleed UI uploads.
- `src/arch_rogue/rendering/effects.py`:
  - Verify the impact-effect cache (4.3.13) is bounded. If unbounded, add an LRU cap (e.g. 256 entries) keyed by `(kind, quantized progress, radius bucket, color)`.
- `src/arch_rogue/rendering/world.py`:
  - The incremental floor cache + reveal-patch path (4.3.5) is a mobile GPU-upload-cost optimization. Benchmark on desktop: if it does not improve the deterministic 2560×1440 crowd profile, gate it to `self.mobile_mode` only. Keep the cold-rebuild path shared.
- `src/arch_rogue/options.py`:
  - `legacy_mobile_quality_migration` (schema < 6) and `legacy_ui_scale_migration` were 4.2.x → 4.3.0 upgrade paths. Keep through 4.3.x, mark with a `# Deprecation cutoff: 4.4` comment, schedule removal in 4.4.
- `src/arch_rogue/game.py` and `options.py`:
  - Consolidate the render-cache invalidation fields (`ambient_overlay_cache`, `_hud_panel_cache`, `_hud_icon_cache`, `_aim_cone_cache`, `_alpha_tile_cache`, `tile_cache`, `door_tile_cache`, `_title_logo_cache`, `_fitted_ui_font_cache`) into a single `_invalidate_render_caches()` method. `_apply_graphics_mode()`, `rebuild_fonts()`, and resolution changes call it. No behavior change; pure structural cleanup with a regression test confirming all caches are cleared.
- Remove any unused imports the above leaves behind. The rendering mixins retain their known cross-module unused-import warnings from `pyright` — leave those unless they're directly touched.

###### WS-D — Desktop parity with universal mobile wins

Audit each 4.3.x performance changelog entry. For universal wins, confirm the shared code path actually executes on desktop (not just mobile):

- Impact-effect cache (4.3.13) — confirm desktop hits the cache, not a per-frame alloc.
- Cached projection origin (4.3.14) — generalize the memoization to `camera.py` so desktop crowds benefit; invalidate on camera focus / layout change.
- Full-bleed cutscene backdrop + "cutscene skips world frame" (4.3.12, 4.3.13) — already shared.
- Direct-size shadows (4.3.11) — already shared; confirm desktop path.
- Cached relic guidance (4.3.11) — already shared.
- Batched consecutive wall-tile blits (4.3.5) — already shared; confirm desktop hits the batch path with a debug counter.
- Screen-flash size-matched surface reuse (4.3.2) — already shared.

Acceptance: deterministic 2560×1440 desktop crowd profile improves 5–10% vs. `master` baseline, or at minimum does not regress. The `--compare` baseline tool from WS-B is the source of truth.

###### WS-E — Telemetry hygiene

- Keep `mobile_performance_telemetry_enabled()` defaulting to Android-only. `ARCH_ROGUE_PERF=1` explicitly enables it on desktop for development.
- The in-game diagnostic line (`PERF <fps> <frame ms> | W <world ms> H <hud ms> F <flip ms>`) is currently mobile-only. Add a desktop Options row **Show performance overlay** (off by default) that toggles the same diagnostic line for development. Off in production. Persisted in schema `7` as `show_perf_overlay`.
- Acceptance: a default desktop run emits zero `ARCH_ROGUE_PERF` lines and shows no on-screen diagnostic; `ARCH_ROGUE_PERF=1` + the new option on produces the same line as Android.

###### WS-F — Documentation, version bump, merge

- Update `docs/android-beta.md` to reflect that the Android beta is now part of mainline as of 4.3.x; remove "branch" language, keep the build/install/controls/perf content.
- Update `README.md` to point at `docs/android-beta.md` for Android build instructions (one line).
- Add the `4.3.17` (or chosen version) section to `CHANGELOG.md` summarizing the merge, the frame-rate cap option, the cleanup, and the desktop performance delta. Follow the existing changelog entry structure (Added / Changed / Performance / Fixed / Validation).
- Bump `pyproject.toml` `version` to match.
- Update `AGENTS.md` "Current Code Organization" to mention `FramePacing` (wherever it lands) and clarify that `mobile.py` is now part of the mainline module set, not a fork.
- Merge `android-beta` → `master` with `git merge --no-ff android-beta` so the milestone is preserved as a merge commit; use the 4.3.x CHANGELOG summary as the merge commit message. Tag `v4.3.17`.

###### WS-G — Licensing & attribution hygiene for APK distribution

Apache-2.0 §4 requires license and NOTICE preservation; APK installers never see the repo, so the obligations must be satisfied through what's bundled in the APK and surfaced in-app. None of the actually-bundled native libraries (pygame-ce, SDL2 family, libpng/libjpeg/zlib, Freetype, Python, pyjnius) are copyleft — the work here is disclosure, audit, and trademark hygiene, not license incompatibility.

- Bundle `LICENSE` (the Apache-2.0 text) as a reachable asset inside the APK and surface it from an in-app **About → Open Source Licenses** screen so APK installers get the §4(a) license text and §7 warranty disclaimer without ever opening the repo.
- Add a `NOTICE` file (and matching About-screen section) enumerating every bundled third-party library with its license: pygame-ce (zlib/libpng), SDL2 / SDL2_image / SDL2_mixer / SDL2_ttf (zlib), libpng / libjpeg / zlib, Freetype, Python (PSF-2.0), pyjnius (MIT). Keep it in sync with the p4a recipe dependency list so a future recipe change cannot silently drop or add a license entry.
- Verify the p4a Freetype build selects the **Freetype License** (BSD-like) and not the GPL-2.0+ alternative Freetype offers. Document the chosen option in `NOTICE`.
- Extend `tools/validate_android_apk.py` to grep bundled `.so` files for GPL-family codec strings (`libmad`, `libmp3lame`, `libfaad`) and fail the audit if any MP3 decoder with a copyleft license is present. The procedural audio path needs at most libogg/vorbis; an accidental libmad pull-in via SDL2_mixer would create a GPL-2.0 contamination issue that Apache-2.0 alone cannot resolve (Apache-2.0 is GPLv3-compatible but not GPLv2-compatible without an explicit "or later" clause).
- Extend the same validator to reject accidental bundling of `buildozer/` or `pythonforandroid/` source into `assets/private.tar` — both are (L)GPL build tools and must remain outside the shipped APK.
- Add a one-paragraph **trademark note** to `README.md` clarifying that the "Arch Rogue" name and octahedron crest logo are not part of the Apache-2.0 grant (Apache-2.0 §6 reserves trademark rights); the OSS grant covers copyright in the code, not brand use.
- Surface the existing **AI Provenance & Liability Notice** (currently only in `LICENSE`/`README.md` and per-file SPDX headers) from the in-app About screen so the §7 disclaimer and provenance note reach APK installers.
- Acceptance: an installed APK exposes the Apache-2.0 license text, the third-party NOTICE list, and the AI Provenance notice through the About screen; `tools/validate_android_apk.py` rejects any APK containing `libmad`/`libmp3lame`/`libfaad` or `buildozer`/`pythonforandroid` source; `NOTICE` lists every bundled third-party library and its license.

##### Sequencing

1. **WS-A** — frame pacing (small, foundational, lands first).
2. **WS-B** — regression guard + baseline tool (needed before risky refactors).
3. **WS-C** — cleanup sweep, file-by-file, each commit green.
4. **WS-D** — desktop parity, surgical, depends on C's cache consolidation.
5. **WS-E** — telemetry hygiene, small.
6. **WS-G** — licensing & attribution hygiene (in-app OSS Licenses screen, NOTICE, validator codec checks). Lands alongside or just before WS-F since both touch docs/about.
7. **WS-F** — docs, version bump, merge.

##### Acceptance criteria for the merge

- `python -m compileall src tests` clean.
- `python -m unittest discover tests` green (excluding web tests as usual).
- Desktop deterministic 2560×1440 crowd profile within ±5% of `master` baseline on every phase; ideally improved 5–10% on the phases WS-D touched.
- Default desktop run on a 144 Hz monitor reports exactly 60 FPS via `clock.get_fps()`; mobile reports 60 FPS active, 10 FPS suspended.
- `./tools/build_android.sh debug` produces a valid 4.3.17 APK that passes `tools/validate_android_apk.py` and reports version 4.3.17.
- No `mobile_mode`-gated code path executes on a desktop run (verified by the new `test_mainline_regression.py` instrumentation).
- `ARCH_ROGUE_PERF` is silent on a default desktop run.
- `CHANGELOG.md` version, `pyproject.toml` version, and the merge tag all match.
- `from arch_rogue.rendering import RenderingMixin`, `from arch_rogue.menus import MenuRenderer`, and `from arch_rogue.content import ...` imports unchanged.
- APK About screen exposes the Apache-2.0 license, the third-party `NOTICE` list, and the AI Provenance notice; `tools/validate_android_apk.py` rejects any APK containing `libmad`/`libmp3lame`/`libfaad` or `buildozer`/`pythonforandroid` source.

##### Risks and mitigations

- **Floor cache regresses desktop.** Mitigation: WS-B regression test catches it; gate to `mobile_mode` if needed in WS-C.
- **Schema v7 breaks save compatibility.** Mitigation: schema v7 loader reads v6 options and defaults `frame_rate_cap=60`, `show_perf_overlay=False`. Run saves stay schema `5`.
- **Removing the local-tint fallback breaks Android software-renderer devices.** Mitigation: keep the fallback, just gate it tighter and document the gate. Do not remove.
- **Universal optimizations accidentally change desktop render output.** Mitigation: WS-B pixel-hash regression test catches any drift before merge.
- **`FramePacing` introduces a one-frame input latency change.** Mitigation: preserve the exact `min(self.clock.tick(target_fps) / 1000.0, 0.05)` shape; only the source of `target_fps` changes.
- **A future p4a recipe change silently pulls libmad or another GPL-family codec into SDL2_mixer.** Mitigation: WS-G extends `validate_android_apk.py` to grep bundled `.so` strings and reject the APK at build time; CI runs the validator on every APK build.

### Backlog

- We need to make the darkess deepen more on lower levels, dark levels look already good, but also other "normal" levels below 5 should feel more dark. (do not implement this yet, user will explicitly request this feature if needed)
- The game difficulty starts ok, but gets too easy when player character reaches level 7 or so (not dungeon level, character level). We should either nerf characters, make leveling slower or make enemies harder on lower dungeon depths.
- Multiplayer -> you get your own AI generated character with unique sprites and animations
- You died screen needs nice looking panels where stats are displayed
- Maybe add cryptographic randomness in map seed generation
- Make it so that on Hell difficulty dungeon levels dont end but become progressively harder the deeper you go. 
  - Make settings menu item red & grim when hell is selected.
  - Take into account the story. Could it be infinitely generated by code so that it does not repeat even if the dungeon is endless?
- Widen Arcanist Frost Nova when gaining appropriate Disciplines (need to make one path dedicated to this), finally affecting the whole room
- When in Return mode, spirit beast dashes along Ranger when using dash (action skill 4)
- Is it possible to detect host system display scaling and adjust game scaling accordingly? e.g if display scale on host is 200% -> scale game to 2x
- Dedicated room decorations for bosses (floor, walls, props). Generate new via Pixellab for bosses up to level 10 and final boss.
- Dash: extended dash/blink skill (skill 4) when key pressed long, character starts "running" and moves faster. This consumes stamina really fast and stops once stamina is spent. When "running" mode activated, dash/blink suffers 1min cooldown. To be used as last resort to run away.
