# Changelog

## 3.4.0 — Story Cutscene Refactor

Milestone 3.4 rebuilds the story cutscene runtime around a single data-driven pipeline. Quest cutscenes, dialogue choices, guest interactions, and story rewards are now described by a schema_version 2 asset that also dresses a real theatrical stage with curtains, a proscenium arch, footlights, props, volumetric lighting, and ambient particles. The narrator text card was polished into a parchment bill, and static stage layers are cached so the hot path stays allocation-free and well above 60 FPS.

### Added

- New data-driven stage asset schema (`StageAsset`, `StagePropAsset`, `StageLightAsset`, `AmbientEffectAsset`, `CurtainAsset`) in `quest_assets.py`, loaded and validated at cutscene load time. Schema version 2 is opt-in; version 1 assets still load with default stage dressing.
- Theatrical stage renderer in `rendering/story_overlays.py`: painted backdrop with vignette and horizon, perspective floorboards, a worn-stone-and-iron proscenium arch, dusty accent-tinted tapestry curtains that start closed and pull open with the narration (smoothstep-eased), iron tie-back rings, scalloped valances, iron footlight housings with spectral ember bulbs, and a roster of procedural pixel-art props (pillar, altar, lectern, candelabra, banner, brazier, throne, crate) all sharing a consistent cursed-theater palette (worn stone, iron, dusty tapestry, accent-tinted embers) so the stage matches the dungeon HUD instead of clashing with it.
- Volumetric stage lighting (`spot`, `cone`, `wash`, `beam`) with subtle sway, plus ambient particle systems (`mote`, `dust`, `ember`, `spark`, `leaf`, `snow`, `ash`) driven by deterministic per-particle phases.
- Polished narrator card: an ornate parchment panel with a speaker bill, a gilded divider rule with a center diamond, a glowing leading edge on the narration progress bar, and a blinking quill caret at the spoken line.
- Both built-in cutscenes (`story_guest_omen`, `story_guest_dialogue`) were re-authored in `assets/quest_cutscenes.json` with full stage dressing.
- Focused `tests/test_3_4_story_cutscene_pipeline.py` covering schema validation, legacy compatibility, runtime stage exposure, multi-frame rendering, static-layer caching, narrator card rendering, and save/restore of the active stage.

### Changed

- `draw_cutscene_stage` now composes the stage from the frozen `StageAsset` instead of ad-hoc motif checks; backdrop, floor, and proscenium layers are cached per `(asset, size, accent)` key so the hot path only blits cached surfaces and draws the cheap animated overlays. All stage drawing is offset by `stage_rect.topleft` so curtains and the proscenium frame are confined to the stage and never overlap the title or narrator card. Curtains animate from closed to open driven by narration progress and gather thinly at the sides for a wide opening.
- Stage actors now move slowly and gently via a time scale (`STAGE_ACTOR_TIME_SCALE`) and damped movement deltas with smoothstep easing, so the scene reads as a measured tableau rather than a fidgeting crowd.
- Removed legacy stage clutter (memory ribbon, choice tableau lines/glyphs on the floor, narrator wave dots, keyword-triggered theme motifs, relic silhouette, faction sigil, and tag text) from both the main cutscene stage and the intro stage so the scene is clean and high-production-value; the backdrop is now a single gradient with a soft accent halo behind the relic.
- Package metadata, title/about copy, and save release strings now target `3.4.0`.

### Validation

- Bytecode compilation and the full `unittest` suite (123 tests) pass, including 9 new milestone 3.4 tests. Cutscene rendering benchmarks at ~87 FPS at 1280x720, comfortably above the 60 FPS target.

## 3.3.1 — Four-Branch Skill Trees and Completed-Path Bonuses

Milestone 3.3.1 expands every archetype's skill tree from two branches to four and adds a per-branch completed-path bonus on top of the existing multi-branch combo bonus.

### Added

- Two new skill branches per archetype (50 new `SkillNode` entries in `content/progression.py`), bringing each tree to four branches x five tiers = 20 nodes:
  - Warden: Vow (holy smite) and Fortress (stone wards).
  - Rogue: Traps (engineer/poison) and Marksman (ranged crits).
  - Arcanist: Storm (lightning chains) and Ward (arcane shields).
  - Acolyte: Spirit (summoning) and Curse (debuffs/decay).
  - Ranger: Beast (companion taming) and Survival (camouflage/ambush).
- Completed-path (depth) bonus: a flat bonus per finished branch, applied even if only one branch is complete. `COMPLETED_BRANCH_BONUS_MELEE/SPELL/MAX_HP` constants and `completed_branch_bonus()` helper in `content/progression.py`.
- Tags on the existing Ranger Control/Volley and Acolyte Blood/Veil nodes, plus cross-branch modifiers on all four tier-4 keystones per archetype so every branch pair has a tag-synergy link.

### Changed

- `combo_bonus()` now combines the completed-branch depth bonus and the multi-branch combo breadth bonus into a single total. With four branches the combo can reach three steps (4 completed - 1).
- Character sheet combo strip now shows the depth/breadth breakdown (e.g. `2 branch complete: depth +2m/+2s/+12hp · combo x2 +2m/+2s/+8hp`) and dims branch headers for incomplete branches.
- Existing 3.3 tests updated to reflect the four-branch tree and the new depth bonus.

### Validation

- Bytecode compilation and the full `unittest` suite (114 tests) pass, including 9 new four-branch/completed-path tests in `tests/test_3_3_skill_points.py`.

## 3.3.0 — Skill Point Progression and Combo Trees

Milestone 3.3 lets the player choose which skills to advance using earned skill points and makes skill trees interact across branches so committing to multiple routes yields cumulative combo bonuses.

### Added

- Skill-point budget on `Player`: level-ups now award a spendable skill point instead of auto-granting a node, and `Game.choose_skill_upgrade` spends a point to acquire a node. `Game.grant_skill_point` awards points from run rewards (story defiance path now uses this).
- Cross-branch skill interactions via `SkillNode.tags` and `cross_branch_tags`: the Warden (Guard/Counter), Rogue (Critical/Stealth), and Arcanist (Arcane/Frost) trees carry tags, and tier-4 keystones boost tagged skills in the opposite branch. `cross_branch_tag_bonus()` resolves the total bonus from acquired modifier nodes against acquired tagged nodes.
- Cumulative combo bonuses for completing 2+ branches on the same tree, scaling by completed-branch count. `completed_branches()`, `combo_bonus()`, `combo_bonus_steps()`, and `combo_bonus_preview()` helpers live in `content/progression.py` and stay O(nodes) with no per-frame allocations.
- Character sheet surfacing: skill points shown in the subtitle, a combo strip above the skill-tree grid showing completed-branch count and current bonus, mouse hover with a bright outline and a footer preview of the combo tier a hovered node would unlock, and click-to-spend on an available node.
- `Game.combo_state()` and `Game.combo_preview()` expose live and hypothetical combo state for the sheet and the hot path.
- Focused `tests/test_3_3_skill_points.py` covering skill-point earning and spending, cross-branch tag interactions, combo bonus scaling at 2+ completed branches, save migration, sheet surfacing, and hot-path safety.

### Changed

- Level-up floater now reads `LEVEL UP · SKILL POINT`; the War Shrine message reflects the granted skill point. Shrine/altar `grant_skill_upgrade` calls remain bonus grants that do not consume banked points.
- `tests/test_3_2_skill_tree.py` updated to bank skill points before `choose_skill_upgrade` calls, reflecting the new spend contract.

### Validation

- Bytecode compilation and the full `unittest` suite (105 tests) pass, including 23 new milestone 3.3 tests.

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
