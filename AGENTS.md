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

#### 4.3.x Beta hardening and release

- Fix beta device, input, layout, lifecycle, and performance issues; add focused regression tests.
- Automate reproducible APK builds/releases and document the local build process.
- Exit beta only when all gameplay and menus are touch-operable and save upgrades complete without data loss.

#### 4.3.x Android performance

- How locked are we into the device resolution? Can performance be improved by adjusting resolution?
- Is there something in packaging that could improve performance on Android? Are we using all the latest libraries, SDK, and other middleware?

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
