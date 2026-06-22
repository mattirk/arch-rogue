# Arch Rogue

Prototype 1: Core Dungeon Loop for a modernized Rogue-inspired isometric ARPG built with Python and Pygame CE.

## Implemented Prototype 1 Features

- One playable archetype: **Warden**
- Procedurally generated dungeon floor with rooms and corridors
- Isometric tile rendering at a 2x world visual scale
- Procedural JRPG-style pixel sprites for player, enemies, loot, projectiles, and attack effects, scaled 2x from the initial prototype size
- Real-time WASD movement with wall collision
- Melee combat and ranged magic bolt
- Melee and ranged enemies
- Health, mana, stamina, death, restart, and victory states
- Loot drops and room loot
- Simple inventory, equipment, and potions
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
| `WASD` | Move |
| Mouse | Aim |
| Left Mouse / `Space` | Melee attack |
| Right Mouse / `F` | Cast ranged bolt |
| `E` | Pick up nearby loot / use exit stairs |
| `I` | Toggle inventory |
| `1`-`9` | Equip/use inventory item shown in that slot |
| `Q` | Use first potion in inventory |
| `R` | Restart after death or victory |
| `Esc` | Quit |

## Goal

Explore the dungeon, survive enemies, collect equipment, and reach the exit stairs. Press `E` on the stairs to complete the run.
