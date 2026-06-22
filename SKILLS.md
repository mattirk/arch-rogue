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

- `src/arch_rogue/game.py` owns the main loop, input handling, gameplay orchestration, rendering order, UI, and the executable `main()` entry point.
- `src/arch_rogue/models.py` owns lightweight gameplay data models and shared simple types such as actors, items, projectiles, rooms, and tiles.
- `src/arch_rogue/dungeon.py` owns procedural map generation and dungeon collision/floor queries.
- `src/arch_rogue/sprites.py` owns procedural pixel-art sprite construction.

Prefer expanding these existing modules until a new boundary is clearly justified. Avoid introducing many narrow submodules during prototype work.

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

### 1.1: Depth, Build Variety, and Run Replayability

Expand the 1.0 foundation with more meaningful run variety, stronger archetype identity, and clearer long-term direction without destabilizing the core loop:

- **Expanded dungeon themes:** add additional floor themes with distinct room dressing, hazards, shrine variants, enemy mixes, loot flavor, and lighting palettes so repeated 10-depth runs feel less predictable.
- **Archetype skill growth:** give each core archetype a small set of upgrade choices during a run, including active skill modifiers and passive perks that support multiple builds without requiring a large permanent skill tree.
- **Elite and miniboss variety:** introduce more elite modifiers, miniboss encounters, and theme-linked enemy behaviors with readable telegraphs, meaningful rewards, and tactical counterplay.
- **Richer loot decisions:** add more build-defining affixes, cursed item tradeoffs, unique item effects, and clearer equipment comparison feedback while keeping inventory management fast and readable.
- **Run modifiers and events:** add optional run mutators, rare dungeon events, cursed bargains, hidden rooms, and risk/reward encounters that create memorable stories without overwhelming new players.
- **Meta progression prototype:** explore lightweight account-level unlocks such as cosmetic titles, lore journal entries, optional starting loadout variants, or challenge modifiers; avoid upgrades that remove run tension.
- **Improved onboarding and help:** expand in-game guidance for controls, identification, shrines, traps, skills, resistances, and death/victory summaries so players can learn systems without external documentation.
- **Accessibility and control polish:** improve remapping, UI scale behavior, color-safe indicators, pause/readability tools, and mouse/keyboard responsiveness; evaluate controller support if the input layer is ready.
- **Audio-visual atmosphere pass:** add more cohesive ambience, impact sounds, item pickup feedback, shrine cues, boss stingers, death/victory presentation, and subtle environmental animation.
- **Save compatibility and migration:** maintain save/run-state versioning from 1.0, add migration handling where practical, and ensure failed loads produce safe, actionable messages.
- **Balance pass from player feedback:** tune enemy pressure, potion scarcity, XP pacing, trap damage, shrine rewards, class viability, elite modifiers, boss health, loot rarity, and run modifier extremes using playtest notes.
- **Technical hardening:** improve automated regression coverage for dungeon generation, save/load, inventory/equipment, skills, projectiles, enemy AI, UI rendering, and repeated-run memory/performance stability.
- **Modding/data direction:** begin moving suitable content definitions toward data-driven tables for items, affixes, enemies, skills, rooms, shrines, and events, but avoid a full modding API until the core data model stabilizes.
