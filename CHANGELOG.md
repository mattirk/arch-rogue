# Changelog

## 3.2.0 — Skill Tree Refinement

Milestone 3.2 expands class progression from the flat upgrade pool into a readable, route-based skill tree while preserving save compatibility and the fast run loop.

### Added

- New `SkillNode` model and `SKILL_NODES` content table in `content/progression.py` describing a five-tier, two-branch skill tree per archetype (Warden, Rogue, Arcanist, Acolyte, Ranger) with prerequisite-gated routes.
- Route-aware skill grant logic in `combat.py`: `available_skill_choices()`, `skill_node_state()`, and `choose_skill_upgrade(key)` let level-ups, Oath Shrines, and Forgotten Altars only pick nodes whose prerequisites are met.
- Skill Tree tab in the character sheet (`C`), switchable with `Tab`, `1`/`2`, or arrow keys. Nodes render as a tier x branch grid with chosen/available/locked state, a legend, and an available-path count.
- `migrate_skill_keys()` save-compatibility helper that rewrites obsolete keys and drops unknown ones so older saves resume cleanly against the new tree.
- Focused `tests/test_3_2_skill_tree.py` covering tree shape, prerequisite gating, stat application, save/restore, unknown-key migration, tab switching, and tab rendering at compact sizes.

### Changed

- `SKILL_UPGRADES` is now derived from `SKILL_NODES` so the flat upgrade table and the tree stay in sync; existing `player.skill_upgrades` saves and `has_upgrade` checks keep working unchanged.
- `Game.acquired_skill_upgrades()` now reads from `SKILL_NODES`; added `acquired_skill_nodes()` for tree-order access.
- Character sheet header hint now reads `C/Esc closes · Tab switches tabs`.
- README controls table documents the character sheet tabs.

### Validation

- Bytecode compilation and the full `unittest` suite (80 tests) pass, including 13 new milestone 3.2 tests.

## 3.1.0 — Architecture Refactor

Milestone 3.1 breaks up oversized modules into focused runtime, rendering, menu, and content packages while preserving gameplay behavior, save compatibility, and public imports.

### Changed

- `game.py` is now a compact orchestration shell composed from focused runtime mixins for camera/options, run flow, population, combat, story runtime, inventory, shop, interactions, and save/load behavior.
- `rendering.py` was split into the `arch_rogue.rendering` package while preserving `from arch_rogue.rendering import RenderingMixin` compatibility.
- `menus.py` was split into the `arch_rogue.menus` package while preserving `from arch_rogue.menus import MenuRenderer` compatibility.
- `content.py` was split into the `arch_rogue.content` package facade over focused content-table modules for definitions, archetypes, enemies, equipment, difficulty, interactables, progression, and story corpus.
- Architecture documentation now describes the post-refactor module ownership and stable public entry points.

### Validation

- Full bytecode compilation and the complete `unittest` suite passed after the refactor.

## 2.5.0 — General Cleanup

Milestone 2.5 focuses on repository version hygiene, dark-level presentation cleanup, and small regression coverage without broad architecture changes.

### Changed

- Package metadata, title/about copy, README, and save release strings now target `2.5.0`.
- Dark floors no longer draw extra player-centered ellipse and ring overlays; visibility is handled by tile/object sight checks for a cleaner light-source presentation.

### Added

- Regression coverage for 2.5 release metadata and the dark-floor light-overlay cleanup.

## 2.0.0 — Story Mode: Going Full RPG

Milestone 2.0 adds a deterministic procedural story layer that binds player backstory, guests, choices, and dungeon generation together without replacing the compact run loop.

### Added

- Dark fantasy story corpus with archetype backstories, factions, relics, guest templates, dilemmas, and dungeon-location motifs.
- Deterministic `StoryEngine` that generates a ten-depth storyline from the story seed, archetype, run modifier, and starting dungeon theme.
- Story guests placed in dungeon floors with `Aid`, `Bargain`, and `Defy` choices available through nearby `1`-`3` input.
- Choice effects that alter future dungeon generation: enemy pressure, loot odds, trap density, shrine/secret chances, curse pressure, XP, and boss pressure.
- Story-aware run header, help/about copy, summary stats, and in-world guest rendering.
- Version 4 run saves that persist story state, story guests, effects, logs, and choices while generating fallback stories for older compatible saves.
- Regression coverage for story corpus completeness, deterministic generation, guest interaction, choice-effect persistence, story-aligned floor themes, and UI rendering.

### Changed

- Package metadata, menus, README, and save release strings now target `2.0.0`.
- Final boss names now reflect the active generated story faction.

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
