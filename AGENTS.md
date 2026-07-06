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

## Current Milestone

Always update CHANGELOG.md content and pyproject.toml version number when completing milestones!

### 3.9 Controller, Input, and Accessibility Polish

Modernize the control layer so keyboard/mouse remains responsive while gamepad and accessibility options become first-class across gameplay and menus.

- Add a small input abstraction (`input.py`) that maps keyboard, mouse, and controller events to shared gameplay/menu commands (move, aim, ability, interact, navigate, confirm, back, tab) without ripping out the existing `Game.handle_events` flow.
- Add controller support via `pygame.joystick` for movement, aiming, combat abilities, interaction, inventory/shop navigation, character sheet tabs, and story choices; auto-detect connect/disconnect and persist the last-used device.
- Improve menu navigation consistency across title, options, archetype select, inventory, shop, character sheet, and run-state overlays so every navigable menu supports the same directional/confirm/back bindings on both keyboard and gamepad.
- Add configurable accessibility options to `options.py` and the options menu: aim-assist strength, screen-flash reduction toggle, persistent tooltip toggle, and high-contrast interaction cues; persist them in the existing options file with a backward-compatible schema bump.
- Preserve current keyboard/mouse bindings, run-save compatibility, and the stable `Game`/`main` entry points; keep `arch_rogue.game.Game` and `arch_rogue.game:main` unchanged in name.
- Keep the run loop at 60+ FPS: input sampling must stay cheap, and any per-frame controller polling must avoid allocations in the hot path.
- Validate with a new `tests/test_3_5_input_accessibility.py` covering input mapping, controller-to-command translation, options persistence/migration, and menu navigation, plus the full `unittest discover tests` regression suite.

### 3.10 Build Diversity and Affix Depth

Draft goal: deepen loot-driven build variety by expanding affix pools, item interactions, and skill/affix synergies so each run can commit to a distinct build identity.

- Expand the affix table in `content/equipment.py` with new damage types, cast/attack speed, movement speed, thorns, proc effects, and skill-modifier affixes, plus balanced roll ranges per rarity tier.
- Add a small affix-synergy layer in `combat.py` so tagged affixes (e.g. lifesteal, proc-on-hit, cast speed) actually modify player attack/spell resolution, not just stat totals.
- Introduce a few build-defining unique items per archetype in `population.py` that interact with the new affixes and the 3.2 skill tree branches.
- Make cursed items tempting rather than purely punishing: pair each curse with a meaningful upside and surface the tradeoff clearly in the inventory comparison summary.
- Improve loot readability in the HUD/inventory: affix tooltips, tag icons, and a one-line build-relevance hint comparing drops to the player's current build.
- Preserve save compatibility: existing item/affix saves must still load; new affixes default to no-op on older saves.
- Validate with a new `tests/test_3_6_affix_builds.py` covering affix roll ranges, synergy resolution in combat, unique-item generation, cursed-item tradeoffs, and save migration, plus the full `unittest discover tests` regression suite.

### Stash
- enemies can now "see through walls" or at least they attack the player from the other side. fix this
