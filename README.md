# Arch Rogue

Prototype 2: Build and Loot Identity for a modernized Rogue-inspired isometric ARPG built with Python and Pygame CE.

## Implemented Prototype 2 Features

- One playable archetype: **Warden**
- Procedurally generated dungeon floor with rooms and corridors
- Isometric tile rendering at a 2x world visual scale
- Procedural JRPG-style pixel sprites for player, enemies, loot, projectiles, and attack effects, scaled 2x from the initial prototype size
- Real-time left-mouse movement with wall collision
- Multiple player skills: melee slash, ranged bolt, arc nova, and stamina dash
- Expanded enemy roster with melee, ranged, fast skirmisher, brute, and final-room threats
- Health, mana, stamina, death, restart, and victory states
- Loot drops and room loot with item affixes, unidentified equipment, and first unique items
- Consumables: healing potions, mana potions, and scrolls of identify
- Traps and interactive shrines
- Simple inventory and equipment
- Exit stairs objective

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
| `R` | Restart after death or victory |
| `Esc` | Quit |

## Goal

Explore the dungeon, survive enemies and traps, identify and equip loot, use shrines wisely, and reach the exit stairs. Press `E` on the stairs to complete the run.
