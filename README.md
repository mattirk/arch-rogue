# Arch Rogue

Arch Rogue is a 1.2 milestone release of a modernized Rogue-inspired isometric action RPG built with Python and Pygame CE.

Explore a 10-depth procedural dungeon, choose one of five distinct archetypes, identify loot, survive traps and shrines, defeat the final gate tyrant, and start a fresh run after victory or death.

## 1.2 Release Highlights

- Presentation polish pass with atmospheric menu backdrops, stronger panel treatment, rarity icons, impact bursts, screen damage flash, boss stingers, shrine/secret/trap cues, and clearer death/victory overlays.
- Inventory readability improvements: item rows now show rarity markers, comparison summaries, consumable safeguards, drop/sort controls, equipped gear, and the latest acquired skill upgrade.
- Contextual interaction prompts explain pickups, shrines, secrets, traps, stairs, sealed gates, and cursed bargains without interrupting combat flow.
- Combat readability pass with clearer projectile colors, melee/impact effects, low-health warnings, boss/elite tell markers, and more legible hit feedback.
- Menu and UX refinements across title/options/about/help/archetype/inventory screens, with more compact copy and a cohesive dark fantasy look.
- Static lightweight menu ambience remains fixed and is synchronized after the first drawn frame so startup stays responsive when music is enabled.
- Save compatibility is preserved for older compatible run saves while 1.2 writes versioned run-state metadata.
- Data-driven content direction expanded with shared rarity profiles and event hint tables for items, shrines, secrets, and traps.
- Regression coverage now checks 1.2 save metadata, interaction hints, visual effects cleanup, inventory summaries, UI renderability, and old-save loading.

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
| `E` | Pick up nearby loot / use shrine / open secret / use exit stairs |
| `I` | Toggle inventory |
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

Explore 10 dungeon depths, survive enemies and traps, identify and equip loot, use shrines wisely, and reach the exit stairs. Press `E` on stairs to descend. On depth 10, defeat the gate tyrant before using the stairs to complete the run.

In-progress runs are saved to `~/.arch_rogue_run.json` and can be resumed from the title screen. Death and victory clear the saved run. Options are saved to `~/.arch_rogue_options.json`.

## Known Issues in 1.2

- Run music and sound effects are still lightweight procedural/static cues; there is no hand-authored soundtrack asset pipeline yet.
- Controls are keyboard/mouse only; gamepad support is not implemented.
- Visuals and audio remain procedural prototype assets, now tuned for a more cohesive milestone look rather than final art quality.
- Save files are local JSON and are not cloud-synced.

## Credits

Design, code, procedural art, and procedural audio by the Arch Rogue project. Built with Python and [Pygame CE](https://pyga.me/).

## Changelog

See `CHANGELOG.md` for release notes.
