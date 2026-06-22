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

### Beta: Feature Complete Public Test

Reach a testable, content-complete version suitable for broad feedback:

- Lock the main gameplay loop and avoid major architectural rewrites except for critical issues.
- Include enough themes, bosses, enemies, loot, secrets, and run modifiers to support repeated runs.
- Add save/run-state handling if runs are expected to survive application restarts.
- Add audio, options, title/menu flow, credits/about screen, and basic onboarding/help.
- Run broad balance passes based on playtest data, especially difficulty spikes, loot pacing, and archetype viability.
- Fix known crashes, softlocks, progression blockers, and severe performance issues before widening testing.

### 1.0: Public Release

Ship a polished, replayable single-player release built around the current 10-depth run structure rather than a major redesign:

- **Release-quality run loop:** preserve the locked Beta flow of title/menu → archetype selection → dungeon run → final boss gate → victory/death summary → new run/resume, with no known progression blockers, resume corruption, or restart softlocks.
- **Archetype identity pass:** give Warden, Rogue, Arcanist, Acolyte, and Ranger clearly differentiated moment-to-moment play through tuned stats, cooldowns, resource costs, starting equipment, and at least one signature-feeling skill or passive advantage each.
- **Depth pacing and encounter variety:** tune the 10-depth arc so early floors teach safely, middle floors introduce sharper enemy/trap/shrine decisions, and final floors create sustained pressure before the gate tyrant.
- **Boss and elite encounters:** add enough boss/elite variation for repeated runs, including theme-influenced final boss names, attack patterns, readable telegraphs, and loot rewards without making the final gate feel random or unfair.
- **Loot and identification polish:** refine item rarity, affixes, unidentified gear, uniques, consumables, and equipment comparisons so pickups are readable, tempting, and build-shaping without overwhelming the compact inventory model.
- **Dungeon readability:** improve room landmarks, secret hints, trap visibility, shrine presentation, stairs/boss-gate messaging, and isometric collision clarity so failure feels tactical rather than visually confusing.
- **Save/resume robustness:** harden JSON run-state handling with versioning, graceful failure messages, atomic writes, safe deletion on run completion, and tests for inventory/equipment/enemy/dungeon restoration.
- **Audio and feedback pass:** replace placeholder tones with cohesive menu, pickup, hit, skill, shrine, trap, stairs, boss, death, and victory cues; ensure audio can be disabled and fails silently on unsupported systems.
- **Options and accessibility:** support persistent options for audio, fullscreen/windowed display, readable UI scale, color-safe feedback, help/onboarding access, and remappable core keyboard controls where practical.
- **Balance and telemetry from playtests:** use public-test feedback to adjust enemy damage, potion scarcity, trap punishment, XP pacing, loot rarity, boss health, class viability, and run modifier extremes.
- **Performance and stability target:** maintain stable 60+ FPS on representative dungeon layouts, keep memory usage bounded across repeated runs, and add regression tests for crashes, softlocks, save/load, dungeon generation, combat, loot, and UI render paths.
- **Distribution readiness:** provide clear install/run instructions, version metadata, changelog/release notes, packaged entry point verification, credits/about text, and a concise known-issues list appropriate for a 1.0 public release.

## Open Design Questions

- Should death be full permadeath, soft permadeath, or run-based with account/meta progression?
- How far should the left-mouse movement and keyboard-skill control scheme be expanded for controller support?
- Should the game be single-player only initially, or architected with future co-op in mind?
- How close should itemization stay to Diablo II versus a leaner roguelike inventory model?
