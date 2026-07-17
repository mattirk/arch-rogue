# Arch Rogue

Arch Rogue is a modernized take on the classic Rogue formula: a grim, replayable isometric action-RPG dungeon crawler built with Python and Pygame CE. Procedural dungeons, permanent consequences, scarce resources, and unidentified treasure meet real-time combat, loot-driven builds, and a seeded dark-fantasy storyline.

## Features

**Dungeon & exploration**
- 10-depth procedural dungeon with rooms, corridors, chokepoints, secrets, traps, and themed biomes.
- Floor plans pace the whole run: escalating threat, biome variety, elites and bosses
- Dark floors lit only by your lantern, normal floors revealed as you explore
- Data-driven special rooms (shops, quest-guest rooms) with a pluggable handler model for future room types.

**Combat**
- Real-time isometric combat with melee arcs, ranged bolts, arc novas, and a dash, plus stamina/mana/cooldowns and readable enemy telegraphs.
- Enemy elites with named modifiers and distinct telegraphs, Oathbound minibosses, and floor bosses (Ash Gallows Knight, Mycelial Matron, Rime Chanter, Voidbound Rune Sentinel) culminating in the Dread Gate Tyrant.
- Encounter templates shape each floor: elite packs, ruin ambushes, treasure rooms, and optional challenge rooms.

**Progression & loot**
- Five archetypes: Warden, Rogue, Arcanist, Acolyte, and Ranger.
- Skill system with active abilities, passive talents, branch commitment, combo bonuses, Oath Shrines, and Forgotten Skill Altars.
- Loot rarity tiers (Common, Magic, Rare, Legendary, Unique, Cursed) with an ARPG-style affix vocabulary — damage types, resistances, lifesteal, thorns, proc effects, attack/cast/move speed, and skill bonuses.
- Unidentified items, tempting cursed bargains, and unique items with special effects.

**Story & world**
- Seeded dark-fantasy storyline with story guests, Aid/Bargain/Defy relic choices, and quest cutscenes driven by a dialogue-tree asset pipeline.
- Shrines (Mending, Insight, War, Haste, Fortune, Oath, Twilight) and secrets (Hidden Cache, Cursed Reliquary, Sealed Armory, Moonlit Bargain, and more).
- Discoverable lore through items, shrines, enemy factions, and rare encounters.

**Run lifecycle**
- Four difficulty levels — Easy, Medium (default), Hard, and Hell (unlocked after a clear).
- Lightweight meta-progression (best depth, clears, discoveries, defeated bosses, notable loot, unlocks) that opens options without removing run tension.
- Versioned run saves with resume from the title screen, plus persistent options.
- End-of-run summaries covering cause of death, loot, bosses, secrets, story choices, and mastery.

**Presentation & input**
- High-resolution directional asset sprites for all five archetypes, the complete enemy and boss roster, NPCs, familiars, loot, and isometric dungeon tiles.
- Cached idle/run/action animation playback, theme-aware world recoloring, normal-map lighting, and a complete procedural legacy-graphics fallback.
- Procedural NES-style music and sound effects.
- Keyboard/mouse and full gamepad support with remappable bindings, deadzones, and hot-plug.
- Accessibility touches: aim assist, adjustable UI scale, scrollable settings, and an in-run help overlay.

## Architecture

This project uses vibe architecture: module boundaries stay intentionally small and evolve when new features or file size make a seam worthwhile. The 3.1 refactor preserves `arch_rogue.game.Game`, `arch_rogue.game:main`, `arch_rogue.rendering.RenderingMixin`, `arch_rogue.menus.MenuRenderer`, and `arch_rogue.content` as stable public import points while splitting large implementation files into focused modules.

Current ownership:

- `src/arch_rogue/game.py` owns `Game` construction, high-level app state, main loop wiring, and `main()`.
- Runtime behavior is composed through mixins: `camera.py`, `options.py`, `run_flow.py`, `population.py`, `combat.py`, `story_runtime.py`, `inventory.py`, `shop.py`, `interactions.py`, and `save_system.py`.
- `src/arch_rogue/rendering/` owns world, actor, effects, HUD, and story/cutscene drawing behind the compatible `RenderingMixin` export.
- `src/arch_rogue/menus/` owns reusable title/options/character/inventory/state overlay rendering behind the compatible `MenuRenderer` export.
- `src/arch_rogue/content/` owns content-table modules for definitions, archetypes, enemies, equipment, difficulty, interactables, progression, and story corpus behind the compatible `arch_rogue.content` facade.
- `src/arch_rogue/sprite_assets.py` owns packaged sprite loading, directional animation resolution, anchors, tinting, bounded caches, and per-resource fallback; `sprites.py` remains the compatible procedural legacy atlas.
- `src/arch_rogue/story.py`, `dungeon.py`, `audio.py`, `models.py`, and `constants.py` remain focused support modules.

## Requirements

- Python 3.11 or newer
- Pygame CE 2.5 or newer, installed through the project dependencies

## Install

From a checkout of this repository:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

## Run

```bash
python -m arch_rogue
```

or, after install:

```bash
arch-rogue
```

## Compile and Test

Run development commands from the repository root after installing the editable package in a virtual environment.

Compile/syntax-check the source and tests with Python bytecode compilation:

```bash
python -m compileall src tests
```

Run the full automated test suite with `unittest`:

```bash
python -m unittest discover tests
```

Run a focused test module while iterating on a specific change:

```bash
python -m unittest tests.test_dark_levels
```

Notes:

- The project uses Python's built-in `unittest`; `pytest` is not required.
- Test modules configure dummy SDL video/audio drivers for headless Pygame runs.
- Prefer running the focused test module for your change first, then the full suite before submitting.

## Controls

Arch Rogue supports keyboard/mouse and gamepad. Gamepad bindings can be remapped from the Controls menu (Options → Controls).

### Gameplay

| Control | Action |
| --- | --- |
| Hold Left Mouse | Move toward / aim at the cursor; slash enemies in the melee arc |
| Left Click | Face the cursor and slash if an enemy is in the melee arc |
| Arrow Keys | Keyboard aim / face direction |
| `1` | Melee slash |
| `2` | Cast ranged bolt |
| `3` | Cast arc nova |
| `4` | Dash toward aim direction |
| `5` | Drink best matching health potion |
| `6` | Drink best matching mana potion |
| `7`-`9` | Use / equip inventory slot 7-9 |
| `E` | Interact: pick up loot, use shrine, reveal secret, descend stairs, open story guest dialogue |
| `I` | Toggle inventory |
| `C` | Toggle character sheet (Overview + Disciplines tabs) |
| `Q` | Toggle quest HUD info |
| `H` or `?` | Toggle in-run help overlay |
| `Esc` | Close overlays, or save and quit from gameplay |

### Inventory (while open)

| Control | Action |
| --- | --- |
| `Up` / `W`, `Down` / `X` | Move selection |
| `Tab` | Cycle sort mode |
| `S` | Sort inventory |
| `PageUp` / `PageDown` | Jump selection by a page |
| `Home` / `End` | Jump to first / last slot |
| `Return` / `E` | Use selected slot |
| `Delete` / `Backspace` | Drop selected slot |
| `1`-`9` | Use slot 1-9 |
| `Shift` + `1`-`9` | Drop slot 1-9 |

### Character sheet (while open)

| Control | Action |
| --- | --- |
| `Tab` / `1` / `2` / `←` / `→` | Switch Overview and Disciplines tabs |
| Click discipline (Disciplines) | Spend a mastery token to acquire it |

### Shop (while open)

| Control | Action |
| --- | --- |
| `Tab` | Cycle buy / sell mode |
| `Up` / `W`, `Down` / `S` / `X` | Move selection |
| `Return` / `E` | Buy / sell selected |
| `Backspace` / `Q` | Close shop |

### Story & cutscenes

| Control | Action |
| --- | --- |
| `1`-`3` | Choose Aid / Bargain / Defy (bind the guest relic) |
| `1`-`9` | Choose a dialogue option |
| `Return` / `Space` / `E` | Advance narration |

### Title & menus

| Control | Action |
| --- | --- |
| `↑` / `↓` / `←` / `→` / `W` / `S` | Navigate title and lists |
| `Return` | Activate selection |
| `N` | New run |
| `L` / `R` | Resume saved run |
| `O` | Options |
| `A` / `C` / `H` / `?` | About / help |
| `1`-`5` / `←` / `→` | Choose archetype |
| `Backspace` | Back to title |
| `Esc` | Quit |

### Options

| Control | Action |
| --- | --- |
| `A` / `M` / `F` / `D` | Toggle audio, music, fullscreen, or cycle difficulty |
| `G` | Toggle asset sprites / legacy procedural graphics |
| `L` / `N` | Toggle lighting / normal-map lighting detail |
| `+` / `-` | Adjust UI scale |
| Arrow keys / D-pad | Navigate all rows; the settings list scrolls to keep selection visible |
| `Return` | Toggle the selected row |
| `Backspace` / `O` | Back to title |

### Gamepad

Left stick or D-pad moves, the right stick aims, face buttons trigger combat abilities, and the triggers handle dash and interact. Menu navigation, inventory, shop, character sheet, and cutscene selection all work on pad. Bindings are remappable from the Controls menu, with deadzone and hot-plug support.

## Goal

Explore 10 dungeon depths, survive enemies and traps, identify and equip loot, use shrines wisely, resolve or ignore story guest dilemmas, and reach the exit stairs. Press `E` on stairs to descend. On depth 10, defeat the story-marked gate tyrant before using the stairs to complete the run.

In-progress runs are saved to `~/.arch_rogue_run.json` and can be resumed from the title screen. Death and victory clear the saved run. Options are saved to `~/.arch_rogue_options.json`.

## Known Issues

- Quest cutscene and story-corpus content is computer generated and not human-authored. Story is mostly slop and may be replaced with more engaging content in future versions.
- Music and sound effects are procedural/static cues; there is no hand-authored soundtrack asset pipeline yet.
- The packaged high-resolution sprite set increases wheel and web-bundle size; legacy graphics remains available for constrained systems.
- Save files are local JSON and are not cloud-synced.
- Single-player only; there is no multiplayer.
- The experimental web build exists in `web/` but is not part of the default test run.

## License

This project is licensed under the Apache License, Version 2.0 (see `LICENSE`).

### AI Provenance & Liability Notice

This repository contains code generated, assisted, or refactored by Artificial Intelligence models.

Pursuant to the accompanying Apache 2.0 License, this software is provided strictly "AS IS", without warranties of any kind regarding its intellectual property status, clean provenance, or non-infringement.

- For Downstream Users: The maintainer does not guarantee that this code is completely free of third-party copyright claims or copyleft license contamination. By utilizing, modifying, or distributing this code, you assume all legal and financial risks associated with its use. You are strongly advised to perform your own code-matching and compliance audits before integrating this software into commercial or production environments.

## Credits

Design, code, asset sprites, procedural legacy art, procedural story corpus, and procedural audio by the Arch Rogue project. Built with Python and [Pygame CE](https://pyga.me/). Much of this project is computer generated and not reviewed by a human.

## Changelog

See `CHANGELOG.md` for release notes.
