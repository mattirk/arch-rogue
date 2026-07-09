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

## Milestones / Versions

Always update CHANGELOG.md content and pyproject.toml version number when completing milestones!

### 3.17

- [ ] **Ambush Bell:** Replace the Rogue active skill slot 3 (`Nova` / `Smoke Burst`) with a cursed lure trap that rewards positioning, baiting, poison setup, and backstab burst instead of another radial pulse.
  - Feature fantasy: the Rogue tosses a cracked occult bell or charm onto the floor; it gives off a faint chime and smoke shimmer that tempts nearby enemies toward a small kill zone, then snaps shut in a burst of shadow-dagger strikes when the first enemy reaches it or when its fuse expires.
  - Core gameplay behavior:
    - Cast plants one active bell at the aimed ground point within a short range, falling back to a point in front of the Rogue if no aim target is available.
    - The bell arms after a brief delay, then lures nearby enemies by temporarily biasing their target/movement toward the bell.
    - The first enemy entering the trigger radius detonates the bell, dealing heavy physical backstab damage to that enemy and lighter splash dagger damage to nearby enemies.
    - If no enemy triggers it, the bell expires after a short lifetime with a smaller detonation or harmless smoke puff, depending on balance.
    - The Rogue gains a short smoke/evasion window on cast or detonation so the skill doubles as an ambush setup and escape tool.
  - Suggested tuning targets:
    - Mana/cooldown: reuse the existing nova-slot budget initially (`nova_mana_cost()` / `nova_cooldown()`) and tune only if it feels too trap-heavy or too bursty.
    - Plant range: about 3.5-5.0 tiles in aim direction, clamped to walkable floor.
    - Arm time: about 0.25-0.45 seconds so placement has readable counterplay.
    - Lifetime: about 5-7 seconds, enough to kite enemies through it without becoming a permanent minefield.
    - Lure radius: about 5-7 tiles; trigger radius about 0.75-1.1 tiles; damage radius about 1.6-2.1 tiles.
    - Damage profile: primary target takes high Rogue-level-scaling physical damage with backstab/crit synergy; splash targets take partial physical damage plus optional poison.
    - Active limit: one bell baseline; recasting refreshes/replaces the previous bell to keep performance and encounter control simple.
  - Rogue upgrade and item hooks:
    - `rogue_venom` or poison-branch upgrades should add poison buildup/duration to the detonation and splash hits.
    - Rogue crit/backstab upgrades should increase primary-target damage, crit chance, or bonus damage against enemies facing the bell instead of the Rogue.
    - Rogue mobility/evasion upgrades may extend the smoke/evasion window or reduce plant recovery.
    - Decide whether existing `Nova` equipment bonuses continue to apply to all slot-3 skills for save compatibility, or whether `Ambush Bell` becomes a recognized skill keyword alongside legacy `Nova` bonuses.
  - Combat implementation tasks:
    - Add a lightweight bell/trap runtime model in `src/arch_rogue/models.py` or an existing appropriate model container with position, lifetime, arm timer, lure radius, trigger radius, damage radius, owner/archetype, and triggered state.
    - Add Rogue-only `player_cast_ambush_bell()` in `src/arch_rogue/combat.py`, structurally similar to `player_cast_spirit_call()` for mana/cooldown spend, cast impact, floating text, class fallback safety, and nova-slot balance reuse.
    - Add `update_ambush_bells(dt)` or equivalent update path that decrements timers, arms bells, checks trigger collisions against living enemies, applies lure behavior, detonates, and culls expired bells.
    - Implement bell lure behavior without expensive pathfinding: bias nearby enemy intent/targeting toward the bell while preserving collision, walls, boss behavior, and existing enemy attack timers.
    - Implement `detonate_ambush_bell()` to apply primary and splash damage through existing `damage_enemy()` pathways so floating text, hit flashes, resistances, statuses, knockback, kill rewards, and story modifiers remain consistent.
    - Wire Rogue slot-3 input dispatch to `player_cast_ambush_bell()` while keeping Acolyte `Spirit Call` and other class nova-slot behaviors intact.
    - Rename Rogue slot-3 display text from `Smoke Burst` to `Ambush Bell` in `skill_names()` and ensure cooldown/HUD labels still fit.
  - Rendering, audio, and feedback tasks:
    - Draw an armed bell marker on the dungeon floor as a small dark charm, smoke curl, or pulsing ring that is readable from the isometric camera.
    - Add cast, armed, lure pulse, detonation, and expiration feedback using existing `add_impact`, `FloatingText`, and SFX helpers before introducing new rendering systems.
    - Make the detonation visually distinct from `Nova`: use a focused snap of shadow daggers/smoke around the bell rather than a player-centered circular blast.
    - Ensure enemies being lured remain understandable to the player through subtle movement/attention changes rather than hidden AI state only.
  - Arhitecture notes:
    - Before implementing this feature, design action skill system interfaces so that they better support archetype specific skills
    - Make good design choices and write clean code
  - Save/run lifecycle tasks:
    - Clear active bells on floor descent, run reset, player death, and load/restore boundaries unless deliberate persistence is added.
    - Keep old save files compatible by not requiring serialized bell state.
  - Tests and validation:
    - Add focused tests for Rogue slot-3 dispatch, mana/cooldown spend, single-active-bell replacement, arming delay, trigger detonation, expiry behavior, damage/status application, and lure targeting.
    - Add regression coverage that Acolyte slot 3 still summons via `Spirit Call` and non-Rogue nova-slot classes still behave as expected.
    - Run `python -m compileall src tests`, focused combat/skill tests, and then `python -m unittest discover tests` before closing the milestone.

### Stash
