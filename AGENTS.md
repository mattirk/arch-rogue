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

### 3.13 Special rooms abstraction

Draft goal: replace the current one-off shop/quest room wiring with a small, data-driven special-room abstraction that can support future room identities such as NPC homes, bars, inns, gardens, faction hideouts, and other non-combat or scripted spaces without adding another bespoke index and population path each time.

- Introduce a lightweight special-room model in `models.py` (or an existing content-adjacent module if cleaner) that records stable room identity: room index, room kind/key, display name, tags, door/seal policy, spawn policy, floor/depth constraints, reserved tiles/anchor points, and optional state needed by interactions. Keep it serializable with primitive fields.
- Replace `Dungeon.shop_room_index` and `Dungeon.guest_room_index` as the primary API with a `special_rooms` collection plus helper queries such as `special_room_for_kind()`, `special_room_at_index()`, and `room_has_tag()`. Preserve legacy properties or compatibility shims during the migration so old call sites and saves keep working until they are updated.
- Move special-room selection out of hardcoded shop/guest branches in `dungeon.py` into a planner/assignment pass that chooses eligible interior rooms once, enforces exclusivity, reserves start/stairs/boss rooms, applies deterministic seeded selection for story/quest rooms, and then seals or doors rooms according to each room definition.
- Define initial room kinds for `shop` and `quest_guest` using the new abstraction, matching current behavior exactly: shop rooms remain common gated refuge rooms with shopkeeper/sign/loot dressing, while quest guest rooms are deterministic story-beat rooms that avoid the shop and preserve population determinism.
- Refactor `population.py` from `_populate_shop_room()` / `_populate_story_guest()` toward room-handler dispatch keyed by special-room kind. Each handler should receive the room definition and `Room`, own its NPC/items/cleanup rules, and share utilities for clearing hostile spawns/traps, placing signs, reserving anchor tiles, and adding ambient dressing.
- Refactor rendering room lookups in `rendering/world.py` from `_shop_room_bounds()` / `_guest_room_bounds()` into generic cached special-room bounds and tile-tag helpers. Keep shop floor tint/gold scatter and quest room presentation visually unchanged while making future room dressing opt-in by room kind/tag.
- Update interaction hints and interaction routing so room occupants/features drive behavior rather than the room index itself: shopkeepers still open trade, story guests still open quest choice/cutscene flows, and future NPC homes/bars/inns/gardens can register their own occupant or feature interaction without changing the dungeon generator.
- Update save/load compatibility in `save_system.py`: serialize the new `special_rooms` collection, restore it defensively, and migrate older saves that only contain `shop_room_index`/`guest_room_index` into equivalent `shop`/`quest_guest` special-room entries. Missing or unknown room kinds should safely no-op rather than block loading.
- Keep the abstraction intentionally small and prototype-friendly: no broad plugin framework, no excessive class hierarchy, and no per-frame room-definition allocation. Room assignment should be O(room count) during floor generation, while runtime/rendering lookups should use cached maps or simple list scans at current scale.
- Add focused tests in a new `tests/test_3_13_special_rooms.py` covering deterministic assignment, non-overlap between shop and quest rooms, door/seal policies, shop/quest behavior parity, generic room lookup helpers, old-save migration, unknown-kind no-op behavior, and room-handler extensibility with a stub future room kind.
- Preserve keyboard/mouse bindings, controller bindings, run-save compatibility, the stable `arch_rogue.game.Game` / `arch_rogue.game:main` entry points, and the existing quest-room and shop-room gameplay behavior.
- Validate with `python -m compileall src tests`, `python -m unittest tests.test_3_13_special_rooms`, relevant existing shop/story room tests, and the full `python -m unittest discover tests` regression suite. Do not run experimental web tests by default.

### 3.14 Encounter Depth: Elite Packs, Enemy Affixes, and Faction Variety

Draft goal: complement the 3.10 player-side build diversity with enemy-side variety so each run tests builds against a meaningfully different threat landscape rather than a flat stat curve.

- Introduce elite/champion enemy packs in `population.py` that spawn in deeper floors and themed regions: a pack leader plus 2–4 retinue, scaled HP/damage, and a shared faction tag that gates which enemy affixes may roll.
- Add an enemy-affix layer in `combat.py` mirroring the player affix vocabulary where it makes sense (e.g. extra damage type, fast/cast speed, thorns, lifesteal, teleport/blink, summon retinue, aura-boosted allies) and gating each affix behind a faction/elite tier so basic trash stays readable.
- Define a small set of enemy factions in `content/enemies.py` (e.g. Cursed Knights, Plague Cult, Hollow Beasts, Vault Constructs) with distinct stat leanings, resistances, preferred affix pools, and biome affinity so floor populations read as themed rather than random.
- Make elite telegraphs readable: a faction-colored aura, an affix tag row under the health bar (reusing the 3.10 tag-icon vocabulary), and a pack-leader marker distinct from the existing floor-guardian/boss bar.
- Add a few faction-specific encounter scripts in `population.py` (ambush patrols, patrolling elites, sealed vault guardians) that interact with the 3.8.5 sealed-arena logic without re-triggering the boss bar.
- Tune kill rewards so elite packs drop meaningfully better loot and a small meta-currency bump on first kill per pack per floor, encouraging engagement without forcing grind.
- Preserve save compatibility: existing enemy saves must still load; enemy-affix and faction fields default to no-op/`None` on older saves and never block population.
- Keep the run loop at 60+ FPS: faction/affix resolution must stay O(pack) on spawn and O(enemy) per frame with no per-frame allocations in the hot path.
- Preserve keyboard/mouse bindings, controller bindings, run-save compatibility, and the stable `Game`/`main` entry points.
- Validate with a new `tests/test_3_11_encounter_depth.py` covering faction stat leanings and affix pools, elite-pack generation and retinue sizing, enemy-affix combat resolution (thorns/lifesteal/aura/summon), elite telegraph marker behavior, sealed-vault-encounter interaction, kill-reward scaling, and old-save compatibility, plus the full `unittest discover tests` regression suite.

### Stash
