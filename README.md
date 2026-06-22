# Arch Rogue

Arch Rogue is a 2.0 milestone release of a modernized Rogue-inspired isometric action RPG built with Python and Pygame CE.

Explore a 10-depth procedural dungeon, choose one of five distinct archetypes, follow a seeded dark-fantasy storyline, meet story guests, make choices that reshape future floors, identify loot, survive traps and shrines, defeat the final gate tyrant, and start a fresh run after victory or death.

## 2.0 Release Highlights

- Procedural story mode generates an archetype-aligned backstory, faction conflict, rival faction, cursed relic, ten floor beats, and one story guest dilemma per depth.
- A dark fantasy story corpus now drives backstories, factions, relics, guests, dilemmas, and dungeon-location motifs.
- Story guests appear in-world as non-hostile NPCs. Press `E` to hear their plea, then choose `1` Aid, `2` Bargain, or `3` Defy.
- Story choices persist in the run log and affect future dungeon generation: enemy pressure, loot richness, trap density, shrine/secret odds, curse pressure, XP, and final boss strength.
- Dungeon themes now align to the generated storyline while still preserving procedural layouts, loot, enemies, shrines, traps, and secrets.
- Story state and guests are saved in versioned run saves, while older compatible saves still load with a generated fallback storyline.
- Presentation and UI copy now surface story status in the run header, help overlay, and summary screens.
- Regression coverage now checks deterministic story generation, story guest interaction, choice effects, save/load persistence, and renderability.

## Requirements

- Python 3.11 or newer
- Pygame CE 2.5 or newer, installed through the project dependencies

## Install

From a checkout of this repository:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Run

```bash
python -m arch_rogue
```

or, after install:

```bash
arch-rogue
```

## Controls

| Control | Action |
| --- | --- |
| Hold Left Mouse | Move toward / aim at the cursor; slash nearby enemies |
| `Space` | Melee slash in aimed direction |
| Arrow keys | Optional keyboard aim / face direction |
| `F` | Cast ranged bolt |
| `C` | Cast arc nova |
| `Shift` | Dash toward aim direction |
| `E` | Pick up nearby loot / use shrine / open secret / use exit stairs / hear a nearby story guest |
| `I` | Toggle inventory |
| `1` / `2` / `3` near story guest | Choose Aid / Bargain / Defy, shaping future story and dungeon generation |
| `1`-`9` | Equip/use inventory item shown in that slot |
| `Tab` / `S` while inventory is open | Cycle/sort inventory by type, rarity, or power |
| `Shift` + `1`-`9` while inventory is open | Drop the matching inventory item near the player |
| `Q` | Use first potion in inventory |
| `H` or `?` | Toggle the in-run help overlay |
| `N` / `Enter` | Start new run flow from title screen |
| `L` / `R` | Resume saved run from title screen, if one exists |
| `O` | Options from title screen |
| `A` / `C` / `H` / `?` | About, credits, and onboarding from title screen |
| `1`-`5` / Arrow keys / `Enter` | Choose an archetype from character select |
| `A` / `M` / `F` / `+` / `-` | Toggle audio cues, static music, fullscreen, or UI scale in options |
| `Backspace` | Return from character select/options/about to title |
| `R` | Return to character select after death or victory |
| `Esc` | Save active run and quit |

## Goal

Explore 10 dungeon depths, survive enemies and traps, identify and equip loot, use shrines wisely, resolve or ignore story guest dilemmas, and reach the exit stairs. Press `E` on stairs to descend. On depth 10, defeat the story-marked gate tyrant before using the stairs to complete the run.

In-progress runs are saved to `~/.arch_rogue_run.json` and can be resumed from the title screen. Death and victory clear the saved run. Options are saved to `~/.arch_rogue_options.json`.

## Known Issues in 2.0

- Story mode is procedural text and systemic choice pressure; there is no bespoke quest cutscene or dialogue tree asset pipeline yet.
- Run music and sound effects are still lightweight procedural/static cues; there is no hand-authored soundtrack asset pipeline yet.
- Controls are keyboard/mouse only; gamepad support is not implemented.
- Visuals and audio remain procedural prototype assets, now tuned for a cohesive milestone look rather than final art quality.
- Save files are local JSON and are not cloud-synced.

## Credits

Design, code, procedural story corpus, procedural art, and procedural audio by the Arch Rogue project. Built with Python and [Pygame CE](https://pyga.me/).

## Changelog

See `CHANGELOG.md` for release notes.
