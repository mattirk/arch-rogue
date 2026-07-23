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
- Look for Android tooling (sdk, emulator, etc) in /opt/ folder

## Current Code Organization

NOTE: This project uses vibe architecture. Module structure is changed when new features require it or game.py gets bloated.

There is an experimental web build in `src/arch_rogue/web` and some specific tests related to it. Do not run web tests by default.

Keep the prototype architecture modular but intentionally small:

- `src/arch_rogue/game.py` owns `Game` construction, high-level app state, main loop wiring, the executable `main()` entry point, and (since 4.3.17) the `FramePacing` class that owns `target_fps`, the suspended-mode throttle, the `clock.tick` call, and the dt clamp. Keep `arch_rogue.game.Game` and `arch_rogue.game:main` stable. `Game.run()` is the only caller of `clock.tick`; read the live frame-rate target from `Game.frame_pacing.target_fps`.
- Runtime behavior is composed through focused mixins:
  - `src/arch_rogue/camera.py` for coordinate transforms and visible bounds.
  - `src/arch_rogue/options.py` for display/options, difficulty selection, meta-progress defaults, and audio sync helpers.
  - `src/arch_rogue/run_flow.py` for run lifecycle, floor planning, dark-floor visibility, and run meta-progress.
  - `src/arch_rogue/population.py` for dungeon population, enemies, bosses, shops, loot, affixes, and unique item creation.
  - `src/arch_rogue/combat/` for player/enemy simulation, combat abilities, damage, statuses, cooldowns, and kill rewards (facade re-exports `CombatMixin`).
  - `src/arch_rogue/story/` for story mode runtime, quest cutscenes, relic choices, guest interactions, story rewards, friendly-NPC runtime, and the story engine/serialization helpers. Facade re-exports `StoryRuntimeMixin`, `FriendlyNpcRuntimeMixin`, `StoryEngine`, and the quest-cutscene asset classes.
  - `src/arch_rogue/inventory.py`, `src/arch_rogue/shop.py`, and `src/arch_rogue/interactions.py` for focused player interaction systems.
  - `src/arch_rogue/save_system.py` for item/run-state serialization, restoration, and save-file lifecycle behavior used by `Game`.
- `src/arch_rogue/rendering/` owns the `RenderingMixin` package for dungeon/world, actor, effect, HUD, and story/cutscene drawing behavior, including `rendering/lighting.py` (the `LightingMixin` and lighting helpers, composed into `RenderingMixin`). Preserve `from arch_rogue.rendering import RenderingMixin` compatibility.
- `src/arch_rogue/menus/` owns the `MenuRenderer` package for title, options, character, inventory, and state overlay menus. Preserve `from arch_rogue.menus import MenuRenderer` compatibility.
- `src/arch_rogue/content/` owns content-table modules for definitions, archetypes/themes, enemies/bosses/encounters, equipment/rarity, difficulty, interactables, progression, and story corpus. Preserve imports from `arch_rogue.content` through the package facade.
- `src/arch_rogue/story/` (4.5.1 packaging) owns deterministic story generation, story-state serialization helpers, guest construction, choice-effect aggregation, the story runtime mixin, the friendly-NPC runtime mixin, and the quest cutscene asset library. The package `__init__.py` is the facade that re-exports `StoryEngine`, `StoryRuntimeMixin`, `FriendlyNpcRuntimeMixin`, and the quest-cutscene asset classes, replacing the old standalone `story.py` / `story_runtime.py` / `npc_runtime.py` / `quest_assets.py` modules.
- `src/arch_rogue/sprites/` (4.5.1 packaging) owns the procedural pixel-art sprite atlas (`sprites/procedural.py`), the runtime asset library/atlas (`sprites/library.py`), and the UI asset library (`sprites/ui_assets.py`). The package `__init__.py` re-exports `PixelSpriteAtlas`, `SpriteAtlas`, `AssetSpriteLibrary`, `ResolvedSpriteFrame`, `DIRECTIONS`, and `UiAssetLibrary`, replacing the old standalone `sprites.py` / `sprite_assets.py` / `ui_assets.py` modules.
- `src/arch_rogue/constants.py` owns shared gameplay/rendering constants and lightweight aliases.
- `src/arch_rogue/models.py` owns lightweight gameplay data models and shared simple types such as actors, items, projectiles, rooms, tiles, story beats, and guests.
- `src/arch_rogue/dungeon.py` owns procedural map generation and dungeon collision/floor queries.
- `src/arch_rogue/audio.py` owns mixer setup, procedural sound effects, and per-run procedural NES-style background music generation.
- `src/arch_rogue/licenses.py` (4.3.17 WS-G) loads the bundled Apache-2.0 `LICENSE.txt` / `NOTICE.txt` assets (with a repo-root fallback for desktop dev) for the in-app About → Open Source Licenses screen so APK installers get Apache-2.0 §4 attribution. `tools/build_android.sh` refreshes the asset copies from the canonical root `LICENSE`/`NOTICE` before each build.
- `src/arch_rogue/net/` (4.6) owns the multiplayer client: `client.py` (`MultiplayerClient`, stdlib socket + one background receiver thread with bounded, snapshot-coalescing queues), `messages.py` (typed inbound message dataclasses), `sync.py` (host↔joiner floor/snapshot serialization built on the run-save serializers), `mixin.py` (`NetMixin`, the per-frame `poll()` driver, mp_setup/mp_lobby flow, host remote-intent simulation, reconnect grace), and `protocol.py` (facade re-exporting the canonical codec). Preserve `from arch_rogue.net import MultiplayerClient`.
- `src/arch_rogue_protocol/` (4.6) is the canonical stdlib-only wire codec/message schema shared with the standalone server. It must never import Pygame or `arch_rogue`; the server consumes it as a local path dependency (never vendored).
- `src/arch_rogue/text_input.py` (4.6) owns the shared single-line text-entry helper (`TextInputMixin`): desktop typing, length limits, charset filters, focus cleanup, and Android soft keyboard via SDL text input. Player-name, join-code, server-host, and server-port entry all use it.
- `server/` (4.6, sibling to `src/`, not part of the installed game package) is the standalone ephemeral in-memory relay server: `room.py` (transport-agnostic `RoomHub`, fake-clock testable), `server.py` (asyncio shell + entry point), `config.py`, `protocol.py` (path-dependency import of the canonical codec), own `pyproject.toml`.
- `src/arch_rogue/mobile.py` is part of the mainline module set (not a fork) as of 4.3.17. It owns mobile-only concerns: the Android landscape layout, touch input, app lifecycle, GLES direct presenter, colorkey-RLE alpha optimization, and `MobilePerformanceMonitor` telemetry. Every Android-specific branch is gated by `self.mobile_mode` (or `android_runtime_active()` for import-time checks); no desktop frame executes a GLES/colorkey-RLE/`MobilePerformanceMonitor` branch. The `MobilePerformanceMonitor` is also created on desktop only when the developer opts in via the `show_perf_overlay` option or `ARCH_ROGUE_PERF=1`.

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

### Android profiling and debugging guide

Use an Android Virtual Device (AVD) for repeatable, headless-friendly mobile profiling and debugging. Create your own AVD through Android Studio or `avdmanager`, then use that name in the commands below. The AVD is easier to iterate with than a physical device because it avoids cable handling and uses a stable serial every run.

Note: Target Native resolution on Android since it's the default and should be playable. Lower resolutions are only for fallback and legacy devices.

#### Creating an AVD

If you do not already have an AVD for profiling, create one with `avdmanager` (or use Android Studio's AVD Manager). Choose a recent Android API, the x86_64 ABI, and a device skin that matches the target screen shape. For example, to create a Pixel 5-like device running Android 14:

```bash
sdkmanager --install "system-images;android-34;google_apis;x86_64"
avdmanager create avd --name <emulator_name> --device "pixel_5" --package "system-images;android-34;google_apis;x86_64" --abi x86_64
```

For software-GLES profiling, run the emulator with `-gpu swiftshader_indirect`. For GPU stress testing, use `-gpu host` (requires host GPU support). List existing AVDs with `avdmanager list avd`. The first AVD listed is usually a good default if you only have one.

#### Launch the AVD

From the repo root, replacing `<emulator_name>` and `<device_serial>` with your AVD name and the serial reported by `adb devices`:

```bash
emulator -avd <emulator_name> -no-snapshot-load -no-audio -gpu swiftshader_indirect -no-boot-anim &
adb -s <device_serial> wait-for-device shell 'while [ -z "$(getprop sys.boot_completed)" ]; do sleep 1; done; echo booted'
```

Wait for `booted` before installing or launching the game.

#### Build and install the debug APK

```bash
tools/build_android.sh debug
adb -s <device_serial> install -r bin/archrogue-<version>-arm64-v8a_armeabi-v7a-debug.apk
```

The script also verifies the APK signature and ABI contents. If you change any Python source, you must rebuild and reinstall before the AVD sees the change.

#### Start the game

```bash
adb -s <device_serial> shell am start -n org.archrogue.archrogue/org.kivy.android.PythonActivity
```

#### Profile live frame times

The game emits `ARCH_ROGUE_PERF` logcat lines when run with the performance overlay enabled. Stream them with:

```bash
python tools/profile_adb_live.py --serial <device_serial> --window 8 --no-color --raw
```

Key fields to watch:

- `fps` and `frame_ms` — overall smoothness.
- `overlays` — time spent in menus, cutscenes, and the story intro; this is usually the AVD bottleneck because Swiftshader handles large alpha blits poorly.
- `flip` — present/GLES upload cost.
- `renderer` and `accelerated` — should show `opengles2` and `yes` on the AVD.
- `logical`/`window`/`viewport`/`quality=native` — confirm native resolution is still in use.

To reach the story intro from the title screen with the keyboard, send Enter a few times:

```bash
adb -s <device_serial> shell input keyevent 66
```

For touch navigation, use `adb shell input tap X Y` instead.

#### Local cutscene CPU profiling

For quick CPU-side iteration without installing to the device:

```bash
python tools/profile_cutscene.py
```

This runs the cutscene overlay path headlessly under `cProfile` and writes `build/profiles/cutscene_render.prof`. Inspect the top cumulative functions; the dominant cost on the AVD is usually large `pygame.Surface.blit` calls, not Python CPU time.

#### Common AVD pitfalls

- The AVD uses Swiftshader software GLES, so absolute fps is lower than a real device. Compare relative improvements (`overlays` ms before/after) rather than rejecting a fix because the AVD is still under 60 fps.
- The title screen and archetype select already run at ~60 fps on the AVD; profile the story intro and gameplay crowd for the real mobile stress cases.
- If you stop seeing new log lines, the old app process may still be running. Force-stop and restart:

  ```bash
  adb -s <device_serial> shell am force-stop org.archrogue.archrogue
  adb -s <device_serial> shell am start -n org.archrogue.archrogue/org.kivy.android.PythonActivity
  ```

- After editing cutscene rendering, run the focused regression tests and update desktop render snapshots if the visual output is equivalent but byte-different:

  ```bash
  python -m unittest tests.test_mainline_regression
  python -m unittest discover tests
  ```

#### Workflow summary

1. Launch AVD and wait for boot.
2. Build/install/start the game.
3. Profile the target screen with `profile_adb_live.py`.
4. Make a focused optimization (e.g., fewer large alpha blits, persistent surfaces, lower stage cache bucket rate).
5. Run desktop tests and update snapshots.
6. Rebuild, reinstall, re-profile.
7. Repeat until the target phase drops enough to hit the fps goal.

## Milestones / Versions

Always update CHANGELOG.md, pyproject.toml and other version number references when completing milestones!

### 4.7 Post multiplayer & beyond

- If other player is dead and the other clears dungeon level on multiplayer, the previously killed player should respawn on the start of next level
  - On Hell mode both living players must stand near stairs to descend
- When guest interacts with shopkeeper or guest NPC, the host gets flashing window but nothing else (multiplayer)
  - The game should pause for both and host sees dialog when guest NPC interaction
  - When shopkeeper interaction, guest gets the shopkeeper dialog if they interact with the shopkeeper, same for host, game is paused in both cases
- Player should be able to "Raise" the other player once (multiplayer)
  - Raise revives other dead player to half health
  - Use dance animation when on player who raises
  - Except for Ranger who uses pet animation
  - Raise can be used once per descent, does not reset between levels, rare shrines grant another raise

#### 4.7 backlog


### Backlog

- Make action skill 1 "a big hit" for all characters (normal hit stays as it is when walking towards enemies, maybe lower it's effectiveness a bit). The hit throws one enemy 4+ tiles away and has long cooldown. Each archetype has unique type of "bit hit" attach (needs to be designed)
  - Maybe so that big hit has buildup time so needs to be timed by player
- Maybe add cryptographic randomness in seed (maps, runs, multiplayer) generation
- Make it so that on Hell difficulty dungeon levels dont end but become progressively harder the deeper you go. 
  - Make settings menu item red & grim when hell is selected.
  - Take into account the story. Could it be infinitely generated by code so that it does not repeat even if the dungeon is endless?
- Widen Arcanist Frost Nova when gaining appropriate Disciplines (need to make one path dedicated to this), finally affecting the whole room
- When in Return mode, spirit beast dashes along Ranger when using dash (action skill 4)
- Dedicated room decorations for bosses (floor, walls, props). Generate new via Pixellab for bosses up to level 10 and final boss.
- Dash: extended dash/blink skill (skill 4) when key pressed long, character starts "running" and moves faster. This consumes stamina really fast and stops once stamina is spent. When "running" mode activated, dash/blink suffers 1min cooldown. To be used as last resort to run away.
- Gardens should heal player more slowly. Slow the healing "tick" -> every 5 seconds
- On mobile, dash direction some times gets "stuck". So  that it does not respect the direction player is moving via joystick. Way to fix: stop moving, look around by touching the screen around player (not by joystick) -> start moving again via joystick and problem is gone
- We need to generate another version of Arch Rogue text logo where the diamond/relic in the middle is rotating slowly. This will be used in loading screens and website.
- Generate unique sprites for unique and legendary items
  - Actually, generate unique sprites for all named items in game
  - Also make all items a bit more rare across the board, unique and legenray items enen a bit more rare
- Use generated asset relic in cutscene instead of procedurally generated (legacy graphics stay the same)
  - Also make the relic float a bit lower (also move the altar a bit lower)
- Make it so that cursed items cannot be removed except via "scroll of remove curse"
  - We need to create new item: scroll of remove curse -> generate new sprite for it too
- Make actors on cutscene stage move more slowly, also
  - When actors stop, make them wait at that position for a bit longer and do a "dance" move
  - When player and antagonist clash in the middle, make them exchange couple of blows
- In Archetype selection screen, make the panels containing Archetype names (row.png) a bit more compact in vertical sense (15% for now), keep spacing / alignment clean
- On mobile, make the stat container (hp, mana, stamina) fill from bottom to top. Top and bottom ends of the container are a bit more narrow than the middle so take that into account.
- row.png sprites are stretched in couple of places e.g Archetype selection screen. let's try to fix this, maybe not scale/stretch at all? or maybe not by much (max 1.5x - 2.0x)
- In desktop multiplayer, screen "Enter your partners code", make text input text centered in the input field



### Bottom-of-the-Barrel

- Draw distance on mobile is a bit too short (concerning walls, floors, etc.). On desktop this seems not to be limited at all (which is good). Sight radius (or light radius) is good both on desktop and mobile and shoud not be changed. Extend mobile draw distance a bit (1 tile per direction should be enough).
- We need to make the darkess deepen more on lower levels, dark levels look already good, but also other "normal" levels below 5 should feel more dark. (do not implement this yet, user will explicitly request this feature if needed)
- The game difficulty starts ok, but gets too easy when player character reaches level 7 or so (not dungeon level, character level). We should either nerf characters, make leveling slower or make enemies harder on lower dungeon depths.
- Multiplayer -> you get your own AI generated character with unique sprites and animations
