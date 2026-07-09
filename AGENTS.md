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

### 3.16 Lighting overhaul

Goal: replace the per-tile alpha falloff with a continuous, multi-source colored lighting model so the dungeon reads as a lit space rather than a visibility mask, while preserving fog-of-war memory, save compatibility, 60+ FPS, and the web build.

Reality check on community suggestions:
- SpriteIlluminator / Laigter generate normal maps from sprite art. We can't run those GUI tools, but the algorithm (luminance/layer order -> height map -> Sobel normals) is trivial to reproduce in code. Our sprites are already procedurally drawn pixel-by-pixel in `sprites.py` (`_dot`/`_rect` ops into a `SRCALPHA` surface), so we can bake a normal map per sprite at atlas-build time for free, with no asset pipeline.
- "Pygame-CE GLSL fragment shaders via `pygame.FRect`" is unreliable: `pygame.FRect` is just a float-precision rect, and pygame-CE's stable renderer is SDL2 2D (software or accelerated 2D textures) and does not expose an arbitrary GLSL fragment-shader pipeline in the shipped API. Relying on GLSL would also break the existing web build (`src/arch_rogue/web`). Use the architecture-honest path the codebase already uses: `SRCALPHA` surfaces + `BLEND_RGBA_ADD`/`BLEND_MULT` compositing.

Current state to build on:
- `run_flow.tile_visibility_alpha` — per-tile alpha falloff on dark floors, fog-of-war memory on light floors; walls are occluders (opaque or culled).
- `rendering/world._alpha_tile_surface` — quantized alpha buckets + cached tile surfaces (no per-frame allocs).
- `sprites.py` — procedural pixel sprites, cached atlas, `convert_alpha()` frames.
- `content/archetypes.py` `DungeonTheme` already carries accent/floor/wall color palettes per theme.

Features:

1. Procedural normal maps, baked into the sprite atlas — In `sprites.py`, derive a height map per sprite from layer/luminance (the order pixels are stamped already encodes depth; later stamps = closer). Run a 3x3 Sobel to produce a tangent-space normal map, stored in a parallel cache keyed identically to the diffuse frame. No external tools/asset pipeline; mirrors the SpriteIlluminator/Laigter approach in-code. Gate behind a `LIGHTING_NORMAL_MAPS` option so the web/low-end path can skip it. Normal maps should apply to all sprites, including tiles.

2. Screen-space light accumulation buffer — Add a `LightBuffer` (half-resolution `SRCALPHA` surface, reused per frame) in a focused `lighting.py` module (create the module and transfer all relevant logic into it). Each frame: clear, blit cached radial-gradient light sprites with `BLEND_RGBA_ADD` for every active light, then composite onto the world with a multiply pass. Replaces the per-tile alpha quantization in `_alpha_tile_surface` with a continuous mask; the fog-of-war `revealed_tiles` memory stays as a separate terrain-reveal pass (no behavior change to `update_revealed_tiles`).

3. Player as a dynamic light source — Player emits a warm lantern light at `DARK_LEVEL_LIGHT_RADIUS` (keeps sight/visibility reach identical so combat/enemy-LOS logic is untouched). On light floors, the player light still adds local warmth over the ambient theme tint; sight radius stays `LIGHT_LEVEL_SIGHT_RADIUS`. Subtle flicker (low-amplitude noise on radius/intensity) for lantern feel; togglable in Options -> Accessibility (reduced motion disables flicker).

4. Reactive skill/spell lighting — Casting any spell/skill emits a transient light pulse at the cast site, tinted by archetype/branch (Arcanist Bolt = arcane blue, Storm = cyan-white, Warden Vow/Smite = holy gold, Acolyte blood = deep crimson, Ranger fire = amber). Projectiles carry a small moving light that follows them (reuses the projectile loop in `combat.update_projectiles`, O(projectiles) — no new pass). Impact effects (`ImpactEffect`) and `SlashEffect` flare a short pulse on hit/kill. Tempest / chain-lightning arcs light their strike tiles briefly (ties into the 3.10/3.15 storm visuals).

5. Theme- and faction-tinted ambient light — Use `DungeonTheme` accent/floor colors as the ambient floor wash (Thornbound witchlight green, etc.) so themed regions read as lit by their own light rather than flat. Forward-compatible hook for 3.17 elite faction auras to emit colored light (Cursed Knights cold steel, Plague Cult sickly green, Hollow Beasts void violet, Vault Constructs amber rune-glow).

6. Lit-actor shading via normal maps — For actors within range of >=1 light (player, enemies, bosses, familiars), apply a Lambertian-ish tint per dominant light using the baked normal map — cheap CPU pass over the actor's lit pixels only, cached per (frame, dominant-light-direction) to avoid per-pixel work every frame. Keep it O(lit_actors) per frame; skip on the `LIGHTING_OFF` quality tier.

7. Static light sources in the world — Torches/lanterns (already placed in garden/bar/special rooms — `Garden Lantern` exists) emit a small warm static light into the buffer. Shrines emit their `InteractionHint` accent color as a steady glow. Populated once per floor in `population.py`, stored as a lightweight `LightSource` list (x, y, radius, color, flicker). Save-compatible: defaults to empty on old saves.

8. Lighting toggle — Options entry: `Lighting` = `Off / On` Off falls back to the current per-tile alpha model (preserves the 3.8.0 look as a fallback). On uses the newly implemented lighting model.

Constraints to preserve:
- `Game` / `main` entry points, keyboard/mouse/controller bindings unchanged.
- Save schema `version` stays `5`; `LightSource` list defaults to `[]` on old saves and never blocks population.
- No per-frame surface allocations in the hot path — light sprites cached, light buffer reused, normal-map tint results cached per frame.
- Web build (`src/arch_rogue/web`) must still run; the `Off` tier is the web-safe default path.
- `can_see_world_position` / `has_line_of_sight` reach values unchanged (same `DARK_LEVEL_LIGHT_RADIUS` / `LIGHT_LEVEL_SIGHT_RADIUS`), so enemy AI and dark-floor tests stay valid.

Validation:
- New `tests/test_3_16_lighting_overhaul.py` covering: normal-map derivation determinism, light-buffer accumulation math, player lantern radius == sight radius, skill pulse timing/tint per archetype, projectile light follows path, theme ambient tint, static torch/shrine lights, quality-tier toggle fallback to 3.8.0 model, save round-trip with empty `LightSource` list on pre-3.16 saves, reduced-motion flicker suppression, and a render smoke test.
- Then full `python -m unittest discover tests` (excluding web tests by default).

Metadata:
- Bump `pyproject.toml` and `__version__` to `3.16.0`; save `release` updated, save schema `version` stays `5`. Update `CHANGELOG.md` with an `## 3.16.0 — Lighting Overhaul` entry.

#### 3.16.1 Lighting post fixes

- Group lighting related menu options visually
- Group other menu options too: ????
- What does new recude motion toggle do?

### 3.17 Encounter Depth: Elite Packs, Enemy Affixes, and Faction Variety

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

- make 5 different kinds of animal NPCs (small animal sprites of 5 kind) appear in garden rooms. 2-5 NPCs per room. use data driven approach as usual.
- we need to make player archetype sprites look better. we are looking for higher production value aesthetic while maintaining retro look. generate 10 preview images in./player_sprites with a temporary script. generate artistically different variants of the same archetype e.g warden. we will pick a general guideline from that and upgrade other archetypes
