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
python -m unittest tests.test_2_4_dark_levels
```

Notes for agents:
- The project currently uses `unittest`; `pytest` is not required.
- Test modules configure dummy SDL video/audio drivers for headless Pygame runs.
- Prefer running the focused test module for the code you changed, then `python -m unittest discover tests` before finalizing broader changes.

## Current Code Organization

NOTE: This project uses vibe architecture. Module structure is changed when new features require it or game.py gets bloated.

Keep the prototype architecture modular but intentionally small:

- `src/arch_rogue/game.py` owns the main loop, input handling, gameplay orchestration, combat/interactions, audio/options setup, and the executable `main()` entry point.
- `src/arch_rogue/rendering.py` owns the `RenderingMixin` for dungeon, actor, effect, HUD, and menu-overlay drawing behavior used by `Game`.
- `src/arch_rogue/audio.py` owns mixer setup, procedural sound effects, and per-run procedural NES-style background music generation.
- `src/arch_rogue/save_system.py` owns the `SaveLoadMixin` for item serialization, run-state serialization/restoration, and save-file lifecycle behavior used by `Game`.
- `src/arch_rogue/story.py` owns deterministic story generation, story-state serialization helpers, guest construction, and choice-effect aggregation used by `Game` and saves.
- `src/arch_rogue/constants.py` owns shared gameplay/rendering constants and lightweight aliases.
- `src/arch_rogue/content.py` owns prototype content tables such as archetypes, dungeon themes, run modifiers, enemy definitions, equipment definitions, traps, shrines, secrets, and the dark fantasy story corpus.
- `src/arch_rogue/models.py` owns lightweight gameplay data models and shared simple types such as actors, items, projectiles, rooms, tiles, story beats, and guests.
- `src/arch_rogue/dungeon.py` owns procedural map generation and dungeon collision/floor queries.
- `src/arch_rogue/sprites.py` owns procedural pixel-art sprite construction.
- `src/arch_rogue/menus.py` owns reusable menu and overlay rendering helpers.

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

### 3.1 Refactor modules

Refactor `game.py`, `rendering.py`, and related oversized modules into clearer boundaries while preserving current gameplay behavior, save compatibility, public imports, and test coverage. Treat this milestone as architecture cleanup first; avoid gameplay tuning unless required to keep existing behavior working.

- Preserve `arch_rogue.game.Game` and `arch_rogue.game:main` as stable public entry points.
- Keep method names on `Game` stable during the first pass by using mixins or compatible delegation.
- Prefer mechanical extraction before deeper rewrites.
- Remove unnecessary imports and dead code only after behavior-preserving moves are validated.
- Prompt the user before starting each code-moving phase.
- Validate focused changes with `python -m compileall src tests`, relevant milestone tests, and eventually `python -m unittest discover tests`.

#### 3.1.0 Baseline and plan
- Measure current module sizes and identify natural extraction seams in `game.py`, `rendering.py`, `menus.py`, `content.py`, and `sprites.py`.
- Run the current compile/test baseline and record any pre-existing failures.
- Confirm the planned module boundaries before moving code.

#### 3.1.1 Game shell and low-risk runtime mixins - done
- Keep `src/arch_rogue/game.py` as the small orchestration root for initialization, main loop wiring, and `main()`.
- Extract low-risk helpers from `Game` into focused modules such as:
  - `src/arch_rogue/camera.py` for coordinate transforms and visible bounds.
  - `src/arch_rogue/options.py` for display/options, difficulty selection, meta-progress defaults, and audio sync helpers.
  - `src/arch_rogue/inventory.py` for inventory sorting, selection, equipment/use/drop, consumables, identification, and item summaries.
  - `src/arch_rogue/shop.py` for shopkeeper proximity, pricing, cursor movement, and buy/sell transactions.
  - `src/arch_rogue/interactions.py` for interaction prompts, doors, stairs, nearby world objects, secrets, shrines, and story relic pickup.
- Preserve direct `Game` method access through mixin inheritance or compatible wrappers.

#### 3.1.2 Run flow, floor planning, and population
- Extract run lifecycle and floor-plan behavior into a focused runtime module such as `src/arch_rogue/run_flow.py`.
- Extract dungeon population, enemy creation, boss/miniboss creation, shop inventory generation, loot generation, equipment affixes, and unique item creation into `src/arch_rogue/population.py`.
- Preserve floor-plan save/load schema and deterministic run generation expectations.

#### 3.1.3 Combat, skills, and actor updates
- Extract combat and actor simulation into `src/arch_rogue/combat.py`.
- Include player update, enemy update, movement, collisions, projectile updates, trap updates, melee/bolt/nova/dash abilities, damage resolution, kill rewards, status effects, resistances, and skill cooldown/cost helpers.
- Keep this phase behavior-preserving so milestone 3.2 skill-tree work can build on cleaner seams.

#### 3.1.4 Story runtime and quest cutscenes
- Extract runtime story handling into `src/arch_rogue/story_runtime.py` while keeping `src/arch_rogue/story.py` focused on deterministic story generation and serialization helpers.
- Move story mode start, current beat helpers, story effects, story guest interactions, relic choices, relic placement, cutscene state helpers, cutscene choices, and story reward application.
- Preserve active cutscene save/load compatibility and all story-mode tests.

#### 3.1.5 Rendering package split
- Split the oversized `src/arch_rogue/rendering.py` into a rendering package while preserving `from arch_rogue.rendering import RenderingMixin` compatibility.
- Proposed package shape:
  - `src/arch_rogue/rendering/__init__.py` re-exports `RenderingMixin`.
  - `src/arch_rogue/rendering/base.py` for draw orchestration, color helpers, UI scaling, panels, and text helpers.
  - `src/arch_rogue/rendering/world.py` for dungeon tiles, walls, floors, doors, visible world ordering, and tile caches.
  - `src/arch_rogue/rendering/actors.py` for player, enemies, shopkeepers, animation states, humanoid limb drawing, hit flashes, and sprite blitting.
  - `src/arch_rogue/rendering/effects.py` for shadows, impact effects, movement trails, items, traps, secrets, shrines, projectiles, slashes, ambient overlays, and darkness behavior.
  - `src/arch_rogue/rendering/hud.py` for action bar, cooldown pips, HUD, interaction prompts, run header, boss bar, screen flash, bars, and run summaries.
  - `src/arch_rogue/rendering/story_overlays.py` for story panels, quest cutscene overlays, cutscene stages, cutscene actors, relic visuals, and story intro overlays.
- Keep rendering changes mechanical first; avoid changing visual style unless required to preserve current output.

#### 3.1.6 Menu and UI cleanup
- Keep `src/arch_rogue/menus.py` stable until rendering and game runtime extraction are complete.
- After that, split menus only if useful for maintainability or milestone 3.2 skill-tree work.
- Potential package shape:
  - `src/arch_rogue/menus/__init__.py`
  - `src/arch_rogue/menus/base.py`
  - `src/arch_rogue/menus/title.py`
  - `src/arch_rogue/menus/options.py`
  - `src/arch_rogue/menus/character.py`
  - `src/arch_rogue/menus/inventory.py`
  - `src/arch_rogue/menus/state_overlay.py`
- Prepare the character menu boundary for the 3.2 skill-tree tab.

#### 3.1.7 Content, sprites, imports, and dead code
- Leave `content.py` and `sprites.py` mostly intact during earlier phases unless imports require small updates.
- Later, consider turning `content.py` into a compatibility facade over focused content-table modules for archetypes, enemies, items, bosses, encounters, shrines, traps, difficulty, and story corpus.
- Split `sprites.py` only if sprite work becomes difficult; it is large but currently cohesive.
- Remove unused imports, obsolete wrappers, duplicate helpers, and dead code after all behavior-preserving extraction phases pass.

#### 3.1.8 Final validation and documentation
- Run `python -m compileall src tests`.
- Run focused tests for changed systems while iterating.
- Run `python -m unittest discover tests` before closing milestone 3.1.
- Update README or architecture notes if public module ownership changes materially.

## Next Milestones

### 3.2: Skill tree refinement
- More variety and depth in skill tree
- Player gets to choose different routes on skill tree when leveling up and gaining new skills
- Create separate tab on character sheet (opened via C hotkey) for skill tree
- Skill tree should have depth of 3 levels
