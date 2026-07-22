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

### 4.6.x Post multiplayer

- Password confirmation, warning and consent when enabling multiplayer in beta
  - Terms and contitions etc legal note if enabled
  - Maybe better still to force user to input server address and then warning
  - Idea: Show the user default server address e.g "play.ar.game" and force user to type it to connect -> show warning on top
- Joinint guest does not see action animations e.g time skip or shield bash (or enemies' actions) 

### 4.6 Multiplayer with server component

**Status: shipped in 4.6.0.** The design below was implemented as specified:
the canonical wire codec lives in the stdlib-only `src/arch_rogue_protocol/`
package (re-exported via `arch_rogue.net.protocol`, consumed by `server/` as a
local path dependency), the client lives in `src/arch_rogue/net/` (`client.py`
transport, `messages.py` typed dataclasses, `sync.py` floor/snapshot
serialization reusing the run-save serializers, `mixin.py` `NetMixin`), the
shared text-entry helper is `src/arch_rogue/text_input.py`, and the relay
server is `server/` (`python -m server.server`, default port 43666). Tests:
`tests/test_net_protocol.py`, `tests/test_server_room.py`,
`tests/test_mp_flow.py`.

This milestone adds a cooperative two-player mode where two players descend the
same dungeon together over a network. The host and joiner independently choose
from the existing archetypes (this is not Warden-only co-op); existing archetype
sprite sets are used for both players. **4.6 targets desktop and Android** — the
shared codebase runs on both, and the mobile touch UI, soft-keyboard entry,
app-lifecycle reconnect, and Android performance validation are part of this
milestone. **Web multiplayer is out of scope for 4.6** — pygbag/Emscripten cannot
open raw TCP sockets, so it needs a separate WebSocket transport layer that is a
later milestone. The backlog item "Multiplayer -> you get your own AI
generated character with unique sprites and animations" remains the long-term
direction, but **4.6 ships with the existing archetype sprite sets** — unique
per-player sprites are out of scope for this milestone.

#### Menu changes

- Title screen row 0 is renamed **"Begin a new descent" -> "One will descend"**
  (single-player path is otherwise unchanged).
- A new title row is inserted: **"Two will descend"** (the multiplayer entry
  point; later text may shorten to just "Multiplayer").
- Title row order becomes: `0=One will descend`, `1=Two will descend`,
  `2=Resume a saved run`, `3=Options`, `4=About`.
  - `RunFlowMixin.TITLE_ROW_COUNT` becomes `5`; `TITLE_RESUME_ROW` becomes `2`;
    the other dispatch branches in `_activate_title_selection` shift to match.
  - The Resume row's enabled-when-save-exists rule and the `_next_title_selection`
    skip logic both carry over unchanged.
- A dedicated **multiplayer glyph** (generated via Pixellab) is drawn to the
  right of the "Two will descend" row in `MenuTitleMixin.draw_title_menu`,
  following the existing row layout/gap conventions used for the other rows.
  Add the glyph to the UI asset manifest and use a safe fallback in
  tests/development when the generated asset is unavailable.

#### Player-name + run-id flow

Selecting "Two will descend" enters a new game state, **`mp_setup`**, driven by a
sub-mode/step (`name`, `role`, `host_code`, or `join_code`). Do not introduce a
separate `mp_join` `Game.state`; joining is an `mp_setup` sub-mode. The setup
sequence is:

`Two will descend` -> player name -> **Host a new run** or **Join a run** ->
code confirmation/entry -> server `hello`/`welcome` -> `mp_lobby` -> both players
choose an archetype -> both send `ready` -> server sends `start` -> playing.

1. **Player name** — a short text-entry screen. There is no reusable menu
   text-input primitive today, so 4.6 adds one shared helper that handles
   desktop text input, backspace, confirm, cancel, input length limits, and
   focus cleanup. Name, join-code, host, and port entry must all use it. On
   Android it drives the OS soft keyboard via `SDL_StartTextInput` /
   `SDL_TEXTINPUT` and calls `SDL_StopTextInput` on confirm, cancel, and focus
   loss. Cap the display name at 16 characters and default to a sanitized OS
   username when available, otherwise `Warden`. Stored on `Game` as
   `self.mp_player_name` and persisted in the options blob so it is remembered
   between sessions.
2. **Host/Join role** — the player chooses to host a new run or join an existing
   run. A host generates a run id and waits in `mp_lobby`; the host's "Begin
   descent" button creates/connects to the lobby and does not start the dungeon
   before a partner has joined. A joiner enters a code explicitly and enters
   `mp_lobby` only after the server sends `welcome`. When the server accepts the
   joiner, it sends `partner_joined` to the host; both clients then enter
   archetype selection. Each player sends their own `ready`, and the server
   emits exactly one `start` only after both validated archetype selections exist.
3. **Run id** — the client generates a run id of the configured length (default
   **4 characters** from the alphabet `ABCDEFGHJKLMNPQRSTUVWXYZ23456789` — no
   `0/O/1/I` to avoid ambiguity when read aloud), using `secrets.choice` rather
   than game RNG. The length (`MP_RUN_ID_LENGTH`) lives in `constants.py` and can
   later be raised to 8 or 12. The id is displayed large with a "share this code
   with your partner" note. A four-character Base32-like code has only about 20
   bits of entropy, so it is a **room locator, not authentication**; 4.6 is
   intended for trusted/self-hosted servers, and Internet deployments should
   configure a longer code and rate-limit connection attempts.

Define and render recoverable setup failures: missing/invalid server endpoint,
`run_id_in_use`, `run_not_found`, `run_full`, incompatible client revision,
timeout, and connection failure. A host collision returns to code generation; a
join failure keeps the entered code editable.

#### Client / server architecture

- A new top-level folder **`server/`** (sibling to `src/`) owns the standalone
  server component. It is **not** part of the installed `arch_rogue` package; it
  ships its own `pyproject.toml`/deps and is run independently.
  - Suggested layout: `server/__init__.py`, `server/protocol.py`,
    `server/room.py`, `server/server.py` (entry point), `server/config.py`.
  - The server is **ephemeral/in-memory**: it retains rooms, slots, selected
    archetypes, reconnect reservations, activity times, and opaque relayed data
    in process memory, but persists none of it to disk and uses no database or
    accounts. A run is dropped when both clients disconnect or after an idle
    timeout.
- The wire codec/message schema is **one canonical, stdlib-only shared package**
  consumed by both projects, exposed through `arch_rogue.net.protocol` for the
  client facade. The server must use a local path dependency on that package,
  never a vendored or copied protocol module, so client and server never drift.
  The shared package must not import Pygame.
- The client lives in a new package **`src/arch_rogue/net/`**:
  - `net/client.py` — `MultiplayerClient`, a thin connector that owns the socket,
    the send/recv queue, and reconnect/backoff. Composed into `Game` via a
    `NetMixin` (mirroring the existing mixin pattern) so `Game.run()` drives it
    each frame.
  - `net/protocol.py` — re-exports the canonical shared wire codec for the
    client.
  - `net/messages.py` — typed message dataclasses.
  - `net/__init__.py` — facade re-exporting `MultiplayerClient` and the message
    types, preserving `from arch_rogue.net import MultiplayerClient`.
- **Server address** is stored in the options blob managed by `options.py`.
  Bump the options schema from **7 to 8** and add `mp_player_name: str`,
  `mp_server_host: str`, and `mp_server_port: int`. Defaults are `""`, `""`, and
  `0`; a usable endpoint requires a non-empty host and port in `1..65535`.
  Persist these only in the options blob, with migration defaults for all old
  schemas. Add desktop Options rows for host and port. Until a usable endpoint is
  configured, multiplayer is unreachable from the menu (the "Two will descend"
  row can still be selected but the `mp_setup` flow surfaces a "server not
  configured" notice). No new third-party package is added to the **game**
  dependency set.
- The client uses Python's stdlib `socket` plus one background receiver thread.
  That thread only decodes and enqueues immutable messages: it never mutates
  `Game`, Pygame objects, or game collections. `NetMixin.poll()` runs on the main
  thread every frame while a client exists (including setup and lobby, not merely
  when `mp_active` is true) and performs all state changes. Bound both client
  queues: coalesce queued snapshots to the newest valid one, retain reliable
  control events and one-shot intents, tag events with a connection generation so
  stale reconnect events are ignored, and close/join the receiver thread cleanly
  on `bye`, menu return, and application exit. The server may use `asyncio` or a
  simple threaded model — pick whichever keeps the server single-file-friendly.
  The stdlib `socket` + thread transport runs on both desktop and Android (p4a);
  web is excluded because Emscripten cannot open raw TCP sockets.

#### Protocol (custom, line-delimited JSON over TCP)

A small bespoke protocol rather than pulling in a framework. Rationale: tiny
message set, no RPC surface, and zero new client-side deps.

- **Transport**: one persistent TCP connection per client, line-delimited JSON
  (one JSON object per `\n`-terminated line). Messages are small and
  human-readable, which makes debugging and hand-testing easy.
- **Framing**: each line is `{"t": <type>, ...}`. Framing is UTF-8, one JSON
  **object** per newline-terminated line, with buffered partial/coalesced-line
  support and a maximum line size of `MP_MAX_MESSAGE_BYTES = 256 * 1024`. Reject
  malformed UTF-8/JSON, non-object payloads, oversized lines, invalid field
  types, and non-finite numbers without letting one bad peer crash the room.
  Apply a short configurable hello timeout (default 10 seconds). Unknown `t`
  values are logged at a bounded/rate-limited diagnostic level and ignored for
  forward compatibility; known but invalid or role-forbidden messages receive
  `error` where it is safe to reply.
- **Versioning and ordering**: `MP_PROTOCOL_VERSION = 1`. `hello` also carries a
  content/build revision; the server rejects peers whose revision differs from
  the room's accepted revision. Client-originated request `seq` values are
  positive and monotonic per connection; direct replies echo `seq` while
  unsolicited events do not invent one. Snapshot ordering uses `floor_revision`
  plus a host `tick`; intent ordering uses a per-player `input_seq`. Add `pong`
  (the reply to `ping`).
- **Message set** (all fields snake_case). The server is a relay: it
  validates/routes messages but never simulates the world.
  - **Client -> server**
    - `hello` — `{t, seq, protocol_version, content_revision, name, run_id, role,
      reconnect_token?}`. `role` is `host` or `join`; a reconnect reclaims the
      original role only with its token.
    - `ready` — `{t, seq, archetype_key, run_seed?}`. Each player sends one
      after choosing; only the host supplies a newly generated 64-bit
      `run_seed`.
    - `floor` — host only, sent at initial start and every floor transition.
      Contains `floor_revision`, `depth`, `floor_seed`, floor-plan metadata, and
      the complete static dungeon/world descriptor required for a joiner to
      render the floor without advancing the host RNG.
    - `snapshot` — host only, `{t, floor_revision, tick, ...}` with the latest
      dynamic player, enemy, item, projectile, trap, familiar, and relevant
      world state. (This replaces the earlier single-`player` `state` message:
      a relay cannot synthesize a multi-entity snapshot from it, and there was
      no server-to-host path for joiner intents.)
    - `intent` — joiner only, `{t, input_seq, move_x, move_y, action, target}`.
      Movement components are finite and clamped to `[-1, 1]`; one-shot actions
      use a documented finite action enum and a nullable stable target ID.
    - `run_ended` — host only, with authoritative death/victory/abandon outcome
      and per-player result summaries.
    - `ping` — `{t, seq, ts}` keepalive; `bye` — `{t}` graceful disconnect.
  - **Server -> client**
    - `welcome` — direct `hello` reply `{t, seq, run_id, you_are, player_id,
      partner_name?, partner_ready, reconnect_token}`. The reconnect token is a
      server-generated 128-bit opaque secret bound to that room slot.
    - `partner_joined`, `ready_ack`, and exactly one `start` event. `start`
      includes both stable player IDs/archetype keys and the host-provided
      `run_seed`.
    - `floor` and `snapshot` — the server relays the host's payload unchanged to
      the joiner only. The initial `floor` must arrive before snapshots for that
      revision; a reconnecting joiner receives the latest floor descriptor and
      fresh snapshot before input is re-enabled.
    - `intent` — the server relays a validated joiner intent to the host with its
      authoritative `player_id`; the host, not the server, applies it.
    - `partner_disconnected`, `partner_rejoined`, and final `partner_left`;
      `run_ended`, `pong`, and `{t, seq?, code, msg, fatal}` `error` messages
      (e.g. `run_full`, `run_not_found`, `run_id_in_use`, `bad_msg`).
- **Entity identity**: every network-visible actor/object uses a stable string
  `entity_id` supplied by the host or a serialization adapter. Never use Python
  `id()` as an entity identity. Snapshot application ignores stale
  `(floor_revision, tick)` pairs.
- **Room lifecycle**: a host `hello` creates a waiting room only when no room
  with that code exists; a joiner can enter only a waiting room with exactly one
  occupant. A third client, duplicate role, late join after `start`, or code
  collision is rejected deterministically. The room state is
  `waiting_for_join` -> `selecting` -> `active` -> `closed`. **Max 2 players per
  run for 4.6.**
- **Reconnects**: `bye` is final — release that slot immediately and send final
  `partner_left`. An unexpected socket loss reserves the slot for a configurable
  30-second grace period, emits `partner_disconnected`, and lets only the
  reconnect token reclaim it (emitting `partner_rejoined`). On grace expiry,
  emit final `partner_left`; the remaining client returns safely to the title
  after showing the loss notice. Reconnect support is process-lifetime only:
  tokens are not written to disk in 4.6.
- **Idleness**: the server drops a room whose both slots are closed, or after a
  configurable idle timeout (default ~10 min), refreshed by accepted `snapshot`,
  `intent`, or `ping` traffic.
- **Determinism and authority**: the host process is the sole simulator — it
  owns RNG, dungeon generation, floor transitions, AI, combat, damage, loot
  resolution, and run results. The joiner never runs those systems speculatively;
  it applies floor/snapshot data, renders it, updates its local camera/UI/visual
  interpolation, and sends input intents. A host-created full static floor
  descriptor is required even if deterministic seeds are retained for
  debugging/replay, because the current global RNG sequence also drives story,
  floor planning, dungeon shape, and population, so a lone `floor_seed` is
  insufficient to make a joiner reconstruct a floor safely. For 4.6 we accept
  that the joiner's view lags by one round-trip and that divergent enemy AI
  between snapshots is host-reconciled. Lockstep/rollback is explicitly **out
  of scope** for 4.6; it is a candidate for a later milestone if co-op feels bad.

#### Integration with the existing run loop

- New `Game.state` values: `"mp_setup"` (name + role + code prompts, with
  sub-modes `name`/`role`/`host_code`/`join_code`) and `"mp_lobby"` (waiting for
  partner, used only after the server has accepted the session). The run itself
  still uses the existing `"playing"` state; multiplayer-ness is tracked by a
  `self.mp_active: bool` and `self.mp_role: "host"|"join"|""` on `Game`. Do not
  introduce a separate `mp_join` state.
- `RunFlowMixin` gains `begin_multiplayer_run(...)` which mirrors the existing
  single-player start path but seeds the run from the host's `run_seed` and
  stamps both `Player` actors. The joiner's `Player` is constructed locally from
  the `start` message's `joiner_archetype`.
- The host's current single `self.player` model must become an explicit stable
  player collection plus `local_player_id`, while preserving a compatible
  local-player convenience path where useful for single-player tests. Shared
  combat, population, rendering, visibility, collision, and serialization code
  must accept/select an explicit actor rather than silently assuming one
  player. This is a required gameplay refactor, not something a `NetMixin`
  alone can solve. Each client's camera, HUD, and fog-of-war center on its local
  actor.
- `NetMixin.poll()` is called once per `Game.run()` iteration — after the frame
  tick and before state-dependent update work — and drains the recv queue to
  dispatch messages to handlers that mutate `Game` state. It must be cheap and
  must not allocate on the hot path when no multiplayer client exists. Retain
  `Game.run()` as the only caller of `clock.tick`.
- On the host, run the real simulation once per frame. On the joiner, skip
  AI/RNG/combat simulation and render the latest authoritative state. Start with
  a bounded cadence of 15 snapshots/sec and 20 coalesced movement intents/sec;
  transmit one-shot actions promptly and never let a backlog of old snapshots
  grow unbounded.
- The combat/population/rendering mixins are **not** forked for multiplayer in
  4.6. The host runs the real sim; the joiner renders `snapshot`-derived actors
  and forwards input. Keeping the combat package shared preserves the
  `from arch_rogue.combat import CombatMixin` contract.

#### First-pass co-op rules

These defaults keep 4.6 compatible with Rogue-like consequences and avoid
ambiguous host/join behavior:

- Players do not body-block one another. Enemies target the nearest living
  player, breaking equal-distance ties by stable player ID.
- Loot, gold, inventory, equipment, XP, and disciplines are player-owned. The
  first host-validated interaction claims a world item; trading is unavailable.
  Global world changes are resolved once by the host and replicated.
- Each living player may fight, move, use their own inventory, and submit an
  interaction intent. Stairs require all living players to be in range before
  either player can trigger descent. A defeated player has no revive in 4.6;
  the shared run ends only when no player remains alive, or when the host emits
  victory/abandon.
- To avoid divergent modal UI in the first pass, story/relic/guest choices,
  shops, and other global dialogue are host-controlled; joiners receive the
  resolved outcome through authoritative state. No chat, trade, host migration,
  late join, or independent cutscene-choice UI is included.

#### Persistence and UI integration

- Multiplayer runs never use the ordinary single-player run save. `Resume a
  saved run` remains single-player only; backgrounding, exit confirmation, and
  return-to-title must send/close the MP session without overwriting or deleting
  an existing single-player save. Each client persists only its own options and
  its own local meta/run-history result after a host `run_ended` event.
- Add dedicated menu renderers and input/back handling for `mp_setup` and
  `mp_lobby`; unknown pre-run states must never fall through to dungeon world
  rendering.

#### Mobile integration

- Add `mp_setup` and `mp_lobby` to the mobile reversible-contexts set in
  `RenderingBaseMixin._draw_mobile_back_button` and to `mobile_input_context()`
  so the back button and touch navigation work for the setup/lobby screens. Add
  explicit touch targets for the Host/Join role choice, code entry, and lobby
  confirm/cancel via `handle_mobile_tap()`; never fall through to dungeon-world
  rendering for an unknown pre-run state on mobile.
- Keep every mobile MP branch gated by `mobile_mode` (or
  `android_runtime_active()` for import-time checks) so no desktop frame runs
  the soft-keyboard / mobile touch paths, mirroring the existing mobile
  isolation rule.
- Android app lifecycle: when the OS suspends the app (`mobile_suspended`), the
  MP client pauses outbound traffic and holds its socket; on resume it either
  resumes normally or, if the socket died during suspension, reconnects using
  its reconnect token within the 30-second grace window. A clean `bye` on
  exit-confirmation / return-to-title stays final. This path must not delete or
  overwrite a single-player save.
- Validate Android performance on an AVD with the existing profiling workflow
  (`tools/profile_adb_live.py`); the stress case is snapshot application plus
  rendering two players. Confirm native resolution stays in use and that
  `overlays`/`flip` do not regress relative to single-player on the same AVD.

#### Tests

- `tests/test_net_protocol.py` — encode/decode round-trips for every message
  type, unknown-type tolerance, fragmented/coalesced TCP lines, malformed and
  oversized messages, non-finite numbers, protocol/content revision mismatch,
  and the run-id generator's length/alphabet.
- `tests/test_server_room.py` — `Room` lifecycle: host-only, join, full-run
  rejection, run-id collision, role-forbidden routing, `partner_left`, idle
  timeout (fake clock), graceful `bye`, reconnect/grace expiry, and
  `partner_rejoined`.
- `tests/test_mp_flow.py` — a pair of in-process `MultiplayerClient` instances
  wired to an in-memory server, exercising the `hello` -> `welcome` ->
  `partner_joined` -> `ready` -> `start` handshake end-to-end, hello/ready
  races, stale snapshot/input rejection, bounded queue shutdown, and
  host-to-joiner intent relay.
- All multiplayer tests run headless with the existing dummy SDL drivers; no
  network access is permitted (injectable in-memory transport or loopback
  sockets only).
- Add headless mobile-mode coverage for the `mp_setup`/`mp_lobby` touch targets,
  back-button handling, and the suspend/resume reconnect path (fake clock +
  in-memory transport); keep all mobile MP branches gated by `mobile_mode` so
  desktop tests never execute them.
- Update existing title-navigation, options-schema/row-count, save-version, and
  UI-layout expectations affected by the fifth title row and schema-8 options.
  Multiplayer additions must pass the focused modules and then
  `python -m unittest discover tests` (excluding web tests by default). The 4.6
  release work also updates `CHANGELOG.md`, `pyproject.toml`,
  `src/arch_rogue/__init__.py`, `buildozer.spec`, and version assertions together.

#### Out of scope for 4.6

- Web multiplayer (pygbag/Emscripten): raw TCP is unavailable, so it needs a
  separate WebSocket transport layer — a later milestone.
- More than 2 players per run.
- Persistent accounts, matchmaking, or run history.
- Unique per-player generated sprites (backlog item — keep existing archetype
  sprites).
- Lockstep/rollback netcode; snapshot + intent relay is the 4.6 model.
- Spectator mode, chat, voice, or trading between players.
- Cross-run meta progression tied to multiplayer (single-player and co-op share
  the same meta pool).

### Backlog

- Maybe add cryptographic randomness in map seed generation
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

### Bottom-of-the-Barrel

- Draw distance on mobile is a bit too short (concerning walls, floors, etc.). On desktop this seems not to be limited at all (which is good). Sight radius (or light radius) is good both on desktop and mobile and shoud not be changed. Extend mobile draw distance a bit (1 tile per direction should be enough).
- We need to make the darkess deepen more on lower levels, dark levels look already good, but also other "normal" levels below 5 should feel more dark. (do not implement this yet, user will explicitly request this feature if needed)
- The game difficulty starts ok, but gets too easy when player character reaches level 7 or so (not dungeon level, character level). We should either nerf characters, make leveling slower or make enemies harder on lower dungeon depths.
- Multiplayer -> you get your own AI generated character with unique sprites and animations
