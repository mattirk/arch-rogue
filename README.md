# Arch Rogue

Beta milestone public-test build for a modernized Rogue-inspired isometric ARPG built with Python and Pygame CE.

## Implemented Beta Features

- Five playable archetypes: **Warden**, **Rogue**, **Arcanist**, **Acolyte**, and **Ranger**
- 10-depth procedural dungeon run with rooms, corridors, multiple themes, secrets, shrines, traps, and run modifiers
- Isometric tile rendering at a 2x world visual scale
- Procedural JRPG-style pixel sprites for player, enemies, loot, projectiles, and attack effects, scaled 2x from the initial prototype size
- Real-time left-mouse movement with wall collision
- Multiple player skills: melee slash, ranged bolt, arc nova, and stamina dash
- Expanded enemy roster with melee, ranged, fast skirmisher, brute, and final-room threats
- Health, mana, stamina, death, restart, and victory states
- Loot drops and room loot with expanded equipment pools, item affixes, unidentified equipment, and unique items
- Consumables: healing potions, mana potions, and scrolls of identify
- Traps, interactive shrines, secret caches, and end-of-run summaries
- Simple inventory and equipment
- Exit stairs objective across 10 depths with a final-depth boss gate
- Title/menu flow with new run, resume, options, about/credits, and onboarding/help screens
- JSON run-state save/resume for in-progress runs
- Basic audio cue system with safe fallback when no mixer device is available

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Run

```bash
python -m arch_rogue
```

or, after editable install:

```bash
arch-rogue
```

## Controls

| Control | Action |
| --- | --- |
| Hold Left Mouse | Move toward / aim at the cursor; slash nearby enemies |
| `Space` | Melee slash in aimed direction |
| Arrow keys | Optional keyboard aim / face direction |
| `F` | Cast ranged bolt in aimed direction |
| `C` | Cast arc nova |
| `Shift` | Dash toward aim direction |
| `E` | Pick up nearby loot / use shrine / use exit stairs |
| `I` | Toggle inventory |
| `1`-`9` | Equip/use inventory item shown in that slot |
| `Q` | Use first potion in inventory |
| `H` or `?` | Toggle the in-run help overlay |
| `N` / `Enter` | Start new run flow from title screen |
| `L` / `R` | Resume saved run from title screen, if one exists |
| `O` | Options from title screen |
| `A` / `C` / `H` / `?` | About, credits, and onboarding from title screen |
| `1`-`5` / Arrow keys / `Enter` | Choose an archetype from the character select screen |
| `Backspace` | Return from character select/options/about to title |
| `R` | Return to character select after death or victory |
| `Esc` | Save active run and quit |

## Goal

Explore 10 dungeon depths, survive enemies and traps, identify and equip loot, use shrines wisely, and reach the exit stairs. Press `E` on stairs to descend; on depth 10, defeat the gate tyrant before using the stairs to complete the run.

In-progress runs are saved to `~/.arch_rogue_run.json` and can be resumed from the title screen. Death and victory clear the saved run.
