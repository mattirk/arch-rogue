# Arch Rogue

Arch Rogue is a 1.0 public release of a modernized Rogue-inspired isometric action RPG built with Python and Pygame CE.

Explore a 10-depth procedural dungeon, choose one of five distinct archetypes, identify loot, survive traps and shrines, defeat the final gate tyrant, and start a fresh run after victory or death.

## 1.0 Release Highlights

- Five playable archetypes with differentiated starting equipment and signature advantages:
  - **Warden:** durable melee fighter with stronger guard value and armor.
  - **Rogue:** fast striker with cheaper slashes, crits, and evasion.
  - **Arcanist:** fragile spellcaster with cheaper/faster bolts, wider nova, and better mana recovery.
  - **Acolyte:** dark priest that spends mana to blunt damage and steals small amounts of life in melee.
  - **Ranger:** mobile marksman with faster stamina recovery, cheaper dash, and multishot bolts.
- 10-depth procedural dungeon run with room/corridor layouts, multiple visual themes, secrets, shrines, traps, and run modifiers.
- Depth pacing pass: early floors are safer, late floors add sustained enemy pressure and stronger hazards.
- Final-depth boss gate with theme-influenced tyrant names, boss health UI, gate sealing, loot reward, and victory summary.
- Loot-driven progression with weapons, armor, affixes, unidentified equipment, uniques, healing potions, mana potions, and identify scrolls.
- Title/menu flow with new run, resume, options, about/credits, onboarding/help, death summary, and victory summary.
- Versioned JSON run-state save/resume with atomic writes and safe deletion after death or victory.
- Persistent options for audio, fullscreen, and UI scale.
- Basic audio cue system with safe fallback when no mixer device is available.

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
| `Q` | Use first potion in inventory |
| `H` or `?` | Toggle the in-run help overlay |
| `N` / `Enter` | Start new run flow from title screen |
| `L` / `R` | Resume saved run from title screen, if one exists |
| `O` | Options from title screen |
| `A` / `C` / `H` / `?` | About, credits, and onboarding from title screen |
| `1`-`5` / Arrow keys / `Enter` | Choose an archetype from character select |
| `A` / `M` / `F` / `+` / `-` | Toggle audio, music placeholder, fullscreen, or UI scale in options |
| `Backspace` | Return from character select/options/about to title |
| `R` | Return to character select after death or victory |
| `Esc` | Save active run and quit |

## Goal

Explore 10 dungeon depths, survive enemies and traps, identify and equip loot, use shrines wisely, and reach the exit stairs. Press `E` on stairs to descend. On depth 10, defeat the gate tyrant before using the stairs to complete the run.

In-progress runs are saved to `~/.arch_rogue_run.json` and can be resumed from the title screen. Death and victory clear the saved run. Options are saved to `~/.arch_rogue_options.json`.

## Known Issues in 1.0

- Music is represented by a persistent option, but there is no soundtrack asset pipeline yet.
- Controls are keyboard/mouse only; gamepad support is not implemented.
- Visuals and audio are procedural placeholders intended to be cohesive enough for the 1.0 public release, not final hand-authored assets.
- Save files are local JSON and are not cloud-synced.

## Credits

Design, code, procedural art, and procedural audio by the Arch Rogue project. Built with Python and [Pygame CE](https://pyga.me/).

## Changelog

See `CHANGELOG.md` for release notes.
