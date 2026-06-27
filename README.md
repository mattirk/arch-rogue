# Arch Rogue

Arch Rogue is a 2.5 milestone release of a modernized Rogue-inspired isometric action RPG built with Python and Pygame CE.

Explore a 10-depth procedural dungeon, choose one of five distinct archetypes, follow a seeded dark-fantasy storyline, preview each descent's risks, survive faction-shaped encounters, defeat floor bosses and the final gate tyrant, and start a fresh run after victory or death.

## 2.5 Release Highlights

- Floor plans now pace the full run with escalating threat, biome/theme variety, previewable descent risks, dark-level flags, encounter templates, and boss signposting.
- Distinct floor bosses appear at milestone depths with themed attack patterns, readable telegraphs, persistent AI state, and notable loot hooks.
- Encounter templates influence faction mixes, elite pressure, ambushes, hazard caches, guarded reliquaries, challenge seals, secrets, traps, and rewards.
- Lightweight meta-progression records best depth, clears, discoveries, defeated bosses, notable loot, and unlocks such as Hell difficulty without removing run danger.
- Class upgrades now carry tree/tier metadata so level-ups, Oath Shrines, and skill altars build toward readable archetype paths.
- End-of-run summaries cover cause of death, notable loot, defeated bosses, secrets, story choices, challenge rooms, and mastery progress.
- Versioned run saves persist floor plans, active modifiers, story state, boss/enemy state, discoveries, and run statistics for reliable resume.
- Regression coverage checks run pacing, floor-plan save/load, boss rewards/mastery, boss AI save/load, dark-level visibility, and the 2.5 cleanup pass.

## Architecture

This project uses vibe architecture: module boundaries stay intentionally small and evolve when new features or file size make a seam worthwhile. The 3.1 refactor preserves `arch_rogue.game.Game`, `arch_rogue.game:main`, `arch_rogue.rendering.RenderingMixin`, `arch_rogue.menus.MenuRenderer`, and `arch_rogue.content` as stable public import points while splitting large implementation files into focused modules.

Current ownership:

- `src/arch_rogue/game.py` owns `Game` construction, high-level app state, main loop wiring, and `main()`.
- Runtime behavior is composed through mixins: `camera.py`, `options.py`, `run_flow.py`, `population.py`, `combat.py`, `story_runtime.py`, `inventory.py`, `shop.py`, `interactions.py`, and `save_system.py`.
- `src/arch_rogue/rendering/` owns world, actor, effects, HUD, and story/cutscene drawing behind the compatible `RenderingMixin` export.
- `src/arch_rogue/menus/` owns reusable title/options/character/inventory/state overlay rendering behind the compatible `MenuRenderer` export.
- `src/arch_rogue/content/` owns content-table modules for definitions, archetypes, enemies, equipment, difficulty, interactables, progression, and story corpus behind the compatible `arch_rogue.content` facade.
- `src/arch_rogue/story.py`, `dungeon.py`, `audio.py`, `sprites.py`, `models.py`, and `constants.py` remain focused support modules.

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

Run a focused milestone test module while iterating on a specific change:

```bash
python -m unittest tests.test_2_5_general_cleanup
```

Notes:

- The project uses Python's built-in `unittest`; `pytest` is not required.
- Test modules configure dummy SDL video/audio drivers for headless Pygame runs.
- Prefer running the focused test module for your change first, then the full suite before submitting.

## Controls

| Control | Action |
| --- | --- |
| Hold Left Mouse | Move toward / aim at the cursor; slash nearby enemies |
| `Space` | Melee slash in aimed direction |
| Arrow keys | Optional keyboard aim / face direction |
| `F` | Cast ranged bolt |
| `V` | Cast arc nova |
| `Left Ctrl` | Dash/movement skill toward aim direction |
| `E` | Pick up nearby loot / use shrine / open secret / use exit stairs / open nearby story guest dialogue |
| `I` | Toggle inventory |
| `1` / `2` / `3` in quest cutscenes or near story guest | Choose Aid / Bargain / Defy, shaping future story and dungeon generation |
| `1`-`9` | Equip/use inventory item shown in that slot |
| `Tab` / `S` while inventory is open | Cycle/sort inventory by type, rarity, or power |
| `Shift` + `1`-`9` while inventory is open | Drop the matching inventory item near the player |
| `Q` | Toggle quest HUD info |
| `R` | Drink the best matching health potion in inventory |
| `T` | Drink the best matching mana potion in inventory |
| `H` or `?` | Toggle the in-run help overlay |
| `N` / `Enter` | Start new run flow from title screen |
| `L` / `R` | Resume saved run from title screen, if one exists |
| `O` | Options from title screen |
| `A` / `C` / `H` / `?` | About, credits, and onboarding from title screen |
| `1`-`5` / Arrow keys / `Enter` | Choose an archetype from character select |
| `A` / `M` / `F` / `+` / `-` | Toggle audio cues, static music, fullscreen, or UI scale in options |
| `Backspace` | Return from character select/options/about to title |
| `R` | Return to character select after death or victory; resume from title when a save exists |
| `Esc` | Save active run and quit |

## Goal

Explore 10 dungeon depths, survive enemies and traps, identify and equip loot, use shrines wisely, resolve or ignore story guest dilemmas, and reach the exit stairs. Press `E` on stairs to descend. On depth 10, defeat the story-marked gate tyrant before using the stairs to complete the run.

In-progress runs are saved to `~/.arch_rogue_run.json` and can be resumed from the title screen. Death and victory clear the saved run. Options are saved to `~/.arch_rogue_options.json`.

## Known Issues in 2.5

- Quest cutscenes use packaged JSON dialogue-tree and sprite-animation assets; authored content coverage is still intentionally compact for the milestone.
- Run music and sound effects are still lightweight procedural/static cues; there is no hand-authored soundtrack asset pipeline yet.
- Controls are keyboard/mouse only; gamepad support is not implemented.
- Visuals and audio remain procedural prototype assets, now tuned for a cleaner milestone look rather than final art quality.
- Save files are local JSON and are not cloud-synced.

## Credits

Design, code, procedural story corpus, procedural art, and procedural audio by the Arch Rogue project. Built with Python and [Pygame CE](https://pyga.me/).

## Changelog

See `CHANGELOG.md` for release notes.
