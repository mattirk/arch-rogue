# Changelog

## 1.2.0 — Systems Polish, Presentation, and Long-Term Structure

Milestone 1.2 sharpens usability, presentation, and maintainability while preserving the fast-starting 10-depth run loop.

### Added

- Atmospheric static/menu presentation pass with an animated dark backdrop, stronger panels, rarity icons, impact bursts, screen damage flash, low-health warnings, boss stingers, and clearer death/victory treatment.
- Contextual interaction hints for stairs, sealed gates, items, shrines, secrets, traps, cursed bargains, and class upgrade opportunities.
- Shared data-driven rarity profiles and event hint tables for items, shrines, secrets, and traps.
- Inventory decision summaries for comparisons, consumable safeguards, unidentified gear, curses, and latest acquired skill upgrade display.
- Regression tests for 1.2 metadata, save versioning/compatibility, interaction hints, visual effect lifecycle, inventory summaries, and compact UI renderability.

### Changed

- Projectile, melee, elite/miniboss, trap, shrine, secret, and boss feedback is more legible through color-safe cues and restrained visual effects.
- Menu music remains a fixed lightweight ambience loop and is synchronized after the first visible frame to protect startup responsiveness.
- Run saves now write version 3 metadata while continuing to accept older compatible versions.

## 1.1.0 — Depth, Build Variety, and Run Replayability

Milestone 1.1 expands the 1.0 run loop with more variety, build growth, and clearer risk/reward systems while preserving save compatibility.

### Added

- New dungeon themes: Obsidian Foundry, Moonlit Aquifer, and Thornbound Vault.
- Lightweight in-run archetype upgrades granted at run start, level-up, Oath Shrines, and forgotten skill altars.
- Elite enemy modifiers and miniboss encounters with visible markers, stronger stats, better XP, and reward drops.
- Additional run modifiers for elite-focused runs and cursed-bargain loot/event pressure.
- Cursed gear tradeoffs, extra affixes, inventory comparison hints, and richer event/shrine variants.
- Compatible run saves persist skill upgrades, cursed items, and elite/miniboss state while continuing to accept 1.0-era saves.
- Expanded in-game help and run summaries for elites, minibosses, and skill upgrades.
- Subtle, slow procedural menu music profile for title/options/about/archetype screens.

## 1.0.0 — Public Release

Arch Rogue 1.0 stabilizes the existing 10-depth single-player run loop for public release.

### Added

- Class identity pass with starting equipment and signature-feeling advantages for Warden, Rogue, Arcanist, Acolyte, and Ranger.
- Expanded player skill variation with Warden cleaves, Rogue crits, Arcanist arcing bolts, Acolyte drains, and Ranger multishot/snares.
- New enemies: Ash Hound, Rune Sentinel, Plague Toad, and Hollow Knight.
- More detailed procedural sprites for the expanded enemy roster and item types.
- Atomic, versioned run-state writes with user-visible failure text stored on the `Game` object for resume/save failures.
- Persistent options saved to `~/.arch_rogue_options.json` for audio, fullscreen, and UI scale.
- Release metadata in package/version strings and title screen.
- Public release README sections for requirements, install/run, controls, known issues, credits, and release notes.

### Changed

- Depth pacing now keeps early floors lighter and ramps late-floor enemy pressure.
- Enemy durability and damage scale modestly by depth.
- Trap damage scales modestly after early depths.
- Title/about/options copy now targets the 1.0 public release instead of the beta test loop.
- Menu rendering now lives in `src/arch_rogue/menus.py` with consistent panel, key-badge, card, wrapped-text, and clipped-label layout primitives.
- Title, options, about, help, archetype select, inventory, and run-summary overlays were overhauled to keep text aligned and contained in compact windows.

### Known Issues

- Music toggle is present for settings persistence, but no soundtrack assets are bundled.
- Keyboard/mouse input is the supported control scheme for 1.0.
- Procedural placeholder presentation remains intentionally lightweight.
