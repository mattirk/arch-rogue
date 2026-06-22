# Arch Rogue — Project Skill Brief

## Project Vision

Arch Rogue is a modernized take on the classic Rogue formula: a dark, dangerous, replayable dungeon crawler presented as an isometric action RPG inspired by Diablo II. The game should preserve Rogue's procedural depth, permanent consequences, discovery, and tension while introducing modern combat feel, progression systems, accessibility, and presentation.

## Core Pitch

- **Genre:** Isometric action RPG / roguelike dungeon crawler
- **Inspirations:** Rogue, Diablo II, classic dark fantasy dungeon crawlers, modern ARPG quality-of-life systems
- **Camera:** Fixed or semi-fixed isometric perspective
- **Theme:** Grim fantasy, ancient ruins, cursed depths, occult treasures, hostile wilderness, and underground labyrinths
- **Session Style:** Replayable runs with meaningful progression, procedural maps, unpredictable loot, and high-stakes decisions

## Optimization
Analyze, write, and optimize game code to maintain a stable 60+ FPS while preserving readability, input responsiveness, and clear combat feedback.

## Technology
- **Programming Language:** Python
- **Game Engine:** Pygame CE: https://pypi.org/project/pygame-ce/ 

## Current Code Organization

Keep the prototype architecture modular but intentionally small:

- `src/arch_rogue/game.py` owns the main loop, input handling, gameplay orchestration, combat/interactions, audio/options setup, and the executable `main()` entry point.
- `src/arch_rogue/rendering.py` owns the `RenderingMixin` for dungeon, actor, effect, HUD, and menu-overlay drawing behavior used by `Game`.
- `src/arch_rogue/audio.py` owns mixer setup, procedural sound effects, and per-run procedural NES-style background music generation.
- `src/arch_rogue/save_system.py` owns the `SaveLoadMixin` for item serialization, run-state serialization/restoration, and save-file lifecycle behavior used by `Game`.
- `src/arch_rogue/constants.py` owns shared gameplay/rendering constants and lightweight aliases.
- `src/arch_rogue/content.py` owns prototype content tables such as archetypes, dungeon themes, run modifiers, enemy definitions, equipment definitions, traps, shrines, and secrets.
- `src/arch_rogue/models.py` owns lightweight gameplay data models and shared simple types such as actors, items, projectiles, rooms, and tiles.
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

2. **Diablo II-Style Game Feel**
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

## Candidate Character Archetypes

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

## Systems to Consider Early

- Procedural dungeon generation
- Character controller and isometric movement
- Combat interaction model
- Entity/component or similar gameplay architecture
- Inventory and equipment system
- Item generation and affix database
- Skill and effect system
- Enemy AI and behavior trees/state machines
- Save/run state model
- UI framework
- Input abstraction for keyboard/mouse and controller

## Development Guidelines

- Build systems modularly so procedural content, combat, items, and skills can evolve independently.
- Prefer data-driven definitions for items, enemies, skills, affixes, rooms, events, and loot tables.
- Keep early prototypes focused on feel: movement, combat readability, loot feedback, and dungeon traversal.
- Avoid overbuilding meta-progression before the core run loop is fun.
- When choosing between authenticity to Rogue and modern playability, preserve the spirit of Rogue while modernizing the interface and moment-to-moment feel.

## Milestones

### 1.2: Systems Polish, Presentation, and Long-Term Structure

Build on the current run loop by improving usability, atmosphere, and maintainability while keeping the game fast to start and easy to play:

- **Inventory and equipment polish:** improve inventory readability, sorting, dropping, comparison hints, consumable safeguards, equipment swapping, and item decision clarity without slowing down pickups or combat flow.
- **Menu and UX refinement:** tighten title/options/about/archetype/inventory layouts, prevent text overlap, improve responsive scaling, and keep all menu actions clear at compact window sizes.
- **Static menu audio and startup performance:** keep menu ambience subtle and fixed rather than procedurally generated at startup; ensure the first title frame appears quickly even when audio/music is enabled.
- **Combat readability pass:** improve hit feedback, elite/miniboss tells, projectile clarity, melee arc readability, cooldown feedback, and player damage warnings.
- **Dungeon event clarity:** make shrines, secrets, cursed bargains, traps, and rare events easier to understand through concise in-game prompts and distinct visual/audio cues.
- **Skill upgrade presentation:** expose acquired class upgrades more clearly in HUD/inventory/help, and make upgrade effects easier to reason about during a run.
- **Loot balance and item identity:** tune affix values, cursed tradeoffs, unique effects, drop rates, potion scarcity, and equipment comparison so loot choices feel meaningful but quick.
- **Audio-visual atmosphere pass:** add cohesive static/menu ambience, subtle environmental animation, restrained impact cues, shrine cues, boss stingers, and clearer death/victory presentation.
- **Accessibility and controls:** improve key clarity, color-safe indicators, UI scale behavior, pause/readability tools, and mouse/keyboard responsiveness; keep controller support as an evaluation item.
- **Save compatibility and migration:** maintain safe run-state loading from older compatible saves, preserve actionable load/save errors, and avoid corrupting user progress on failed writes.
- **Automated regression coverage:** expand tests for inventory/equipment behavior, UI rendering, save/load compatibility, skill upgrades, elite/miniboss state, projectiles, and repeated-run stability.
- **Data-driven content direction:** continue moving suitable content definitions toward durable tables for items, affixes, enemies, skills, rooms, shrines, events, and audio profiles without committing to a public modding API yet.
- **Performance hardening:** profile startup, menu transitions, procedural audio generation, dungeon population, rendering hot spots, and repeated-run memory behavior to preserve a responsive 60 FPS target.
