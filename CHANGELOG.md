# Changelog

## 3.6.0 — Dungeon Sprites Polish

Milestone 3.6 retires the single repeating wall/floor stamp and replaces it with a small, coherent family of pre-generated texture variants so the dungeon reads as hand-laid masonry instead of copypasted tiles. The old `tile_seed` returned a 0..31 tint bucket that only nudged brightness, so every wall looked like the same course-less block with a faint color wash. Walls now pick one of four cut-stone masonry patterns (ashlar, running bond, large blocks, weathered). Floors were rewritten to read as one continuous flagstone plane rather than a grid of beveled slabs: the old per-tile radial gradient (bright center, dark edges), inset bevel, and diamond outline darkened every tile edge and made the tile grid the dominant feature, so they were removed in favor of a flat fill whose only per-tile variation is a gentle ±3 variant tint plus the variant's seam/crack/cobble detail. Each variant shares palette, lighting, and silhouette so the family reads as the same stone with small, distinct character.

### Added

- Shared `DUNGEON_WALL_VARIANTS` / `DUNGEON_FLOOR_VARIANTS` constants (4 each) describing the bounded, coherent texture family per tile type.
- `prewarm_tile_cache()` on the world renderer: eagerly pre-generates every wall/floor/stairs variant (shop + non-shop) for the current theme whenever the floor changes, so the first frame after a transition never pays the procedural-draw cost and the hot render loop only ever blits cached surfaces.
- `_wall_face_parallelogram` / `_draw_wall_masonry` face-agnostic helpers that draw horizontal course lines and per-gap vertical joints on either iso wall face from a single description, so a variant's masonry wraps the pillar consistently. `_floor_groove` renders floor joints as carved grooves (anti-aliased shadowed recess + lit lip) rather than flat scratches, so the flagstone tooling reads as high-end masonry instead of cheap drawn-on lines.
- Four coherent wall variants (ashlar with aligned center joint, running bond with a staggered middle row, large blocks with one tall course, weathered ashlar with a patched lower row and a short jagged crack) and four coherent floor variants (smooth premium slab, a single hand-cut iso-diagonal grout joint, an organic fracture with a short branch, two parallel grout courses forming laid-stone panels). All floor joint coordinates are kept inside the slab diamond so grooves never poke into the transparent tile margin. Stairs keep their step motif across all variants so the descent still reads clearly.
- Focused `tests/test_3_6_dungeon_sprite_variants.py` (11 tests) covering seed bounding/determinism/coverage and axis-streak avoidance, prewarm population and cache bounds, the no-recompute-after-prewarm guarantee, the shared-family-but-distinct-detail property for both walls and floors (cap/slab color stays close while full-sprite bytes differ), the stairs-motif invariant, floor-transition and door-open rewarm, and the surface dimension/anchor contract.

### Changed

- `tile_seed` (rendering/world.py) now returns a bounded variant index via a mixing hash `(x*73856093) ^ (y*19349663) % max(variants)` instead of the old `(x*1103515245 + y*12345) & 31`, which left visible axis streaks; the cache is now bounded to 4 wall + 4 floor×2(shop) + 4 stairs×2(shop) surfaces per theme.
- `draw_wall_tile_surface` was rewritten: variant-driven masonry (courses + per-gap joints mirrored onto both faces, a faint cut-lip highlight along the top course, and a weathered crack on variant 3) replaces the old single mid-height course line, while the shared palette, vertical face gradient, cap highlight, and silhouette edges are preserved so the family stays coherent.
- `draw_floor_tile_surface` was rewritten for a continuous read: the per-tile radial gradient, inset bevel, and outer/inner diamond outline (which darkened every tile edge into a visible grid) were removed and replaced with a flat slab fill. The only per-tile variation is a gentle ±3 variant tint (natural mottling between adjacent different-variant tiles) plus the variant-driven surface detail, now rendered as anti-aliased carved grooves (shadowed recess + lit lip) via `_floor_groove` instead of flat aliased scratches, so the tooling reads as high-end flagstone masonry. The shop gilded inlay became a single scattered medallion on the smooth-slab variant (no diamond frame) so the shop floor stays continuous. Stairs keep their step motif across all variants.
- `run_flow.py` (`restart`, `descend_to_next_depth`), `save_system.py` (`restore_run_state`), and `interactions.py` (`open_nearby_door`) now call `prewarm_tile_cache()` after every `tile_cache.clear()` so cache rebuilds are always eager and frame-hitch-free.
- `game.py` `tile_cache` type annotation corrected to the actual 4-tuple key `(theme, tile, seed, shop_floor)`.
- `ambient_overlay_surface` (rendering/effects.py) fog wisps were removed entirely: the nine hard-edged filled ellipses were always present but only became visible as distinct transparent ellipses once the floor was cleaned into a flat slab, and softening them added little value, so the wisp/mist code (scratch surface, gaussian blur, fog-color ellipses) was deleted. The ambient overlay now carries only the depth tint fill and the edge vignette.
- Package metadata, `__version__`, save release strings, and version-current tests now target `3.6.0`.

### Validation

- Bytecode compilation and the full `unittest` suite (145 tests) pass, including 12 new milestone 3.6 tests. The per-frame render loop adds no new tile-cache entries after prewarm, and floor detail is verified to render as a carved groove (shadow + lip) fully inside the slab diamond.

## 3.5.0 — Movement Animation Polish

Milestone 3.5 polishes the player's movement animation so it reads as a grounded, direction-aware walk in the spirit of Chrono Trigger / Sea of Stars instead of the previous "wobblish ghost-float". The root cause was a phase mismatch: the cached 12-frame run pose cycled at one frequency while the whole-body bob cycled at 3x that frequency, and the bob was always positive (the body never dipped below its anchor), so the upper body floated up and down independently of the legs. There was also no directional lean — the lean value sat far below the rotation threshold, so the sprite never tilted into its movement direction.

### Added

- Shared run-cycle tuning constants (`RUN_CYCLE_FRAMES`, `RUN_FRAME_RATE`) in `constants.py` so the sprite atlas and the renderer derive the run phase from one expression.
- `run_cycle_position` helper on the renderer: a continuous 0..1 stride-cycle position computed from the exact same `anim_time * RUN_FRAME_RATE mod RUN_CYCLE_FRAMES` expression used to pick the displayed run frame, guaranteeing the whole-body motion is phase-locked to the cached frame.
- Focused `tests/test_3_5_movement_animation_polish.py` (10 tests) covering cycle/frame phase-locking, grounded signed bob, one-bob-cycle-per-stride (the regression guard against the old 3x wobble), bob/footfall alignment, directional lean sign/magnitude/clamp, run-pose upper-body stability vs feet lift, eight-direction rendering, the run-lean forward-tilt regression guard, the facing-driven lean consistency guard, the slow-enemy cadence floor guard, and dt-jitter advancement.

### Changed

- `actor_animation` (rendering/actors.py) now derives `stride`, `footfall`, `sway`, and `bob` from `run_cycle_position` so the whole body bobs in lockstep with the displayed run frame. The bob is now signed (`(footfall - 0.5) * 1.2`), dipping below the anchor at foot-plant and rising at mid-lift, so the walk reads as weighted and grounded rather than a constant upward float. A directional lean in degrees tilts the sprite top toward the screen-space movement direction (clamped to ±5°), and a subtle vertical stretch responds to up/down screen movement. The shadow now correctly spreads when the body lifts and contracts when it plants because the signed bob feeds `draw_shadow`.
- The `run` band-pose in `sprites.py` was rewritten to keep the cap/head/torso stable (subtle lead into the stride, no vertical float) while the hips, legs, and feet drive the motion with counter-rotation and a footfall lift, harmonizing the internal pose with the phase-locked external bob.
- `blit_sprite` rotation threshold lowered from 1.85° to 1.0° so the new degree-sized directional leans actually rotate the sprite; `draw_player` and `draw_enemy` now pass the lean directly instead of scaling it to zero. The rotation always uses `-lean` (tilting the top toward the screen-space movement direction). Boss/elite lean wobble magnitudes were rescaled to degree units.
- The directional lean and vertical stretch now follow the actor's `facing` vector instead of the gameplay-smoothed `move` vector. `facing` snaps to the input/aim direction every frame, so the lean changes consistently and immediately on a direction change instead of easing slowly over several frames (or not changing at all when the actor is blocked against a wall and `move` stops updating).
- The movement/dust trail behind player and enemy entities was removed: `draw_player` and `draw_enemy` no longer call `draw_movement_trail`, and the now-dead `draw_movement_trail` definitions in `rendering/actors.py` and `rendering/effects.py` were deleted.
- The horizontal mirror-flip on facing changes was removed entirely: `blit_sprite` no longer flips the sprite art based on `facing_x`, and the `facing_x`/`x_scale` parameters and the `smoothed_facing`/`turn_squash`/`turn_factor` turn-pivot machinery (added to mask the flip) were removed. The sprite now always renders in its authored orientation, so there is no flip wobble on quick direction changes; the directional lean still indicates movement direction.
- Run-frame count and frame-selection phase in `sprites.py` now use the shared `RUN_CYCLE_FRAMES` / `RUN_FRAME_RATE` constants.
- `advance_animation_phases` (combat.py) now clamps the per-actor walk-cycle cadence to a floor/ceiling (`WALK_ANIM_SPEED_FLOOR` / `WALK_ANIM_SPEED_CEIL`). The cycle still scales with movement speed, but slow enemies (speed as low as 0.88) no longer cycle so slowly that the 12 discrete run frames are each held for ~9 render frames and stutter; they now stride at a readable minimum cadence. The ceiling keeps very fast units (elites, haste) from blurring.
- Package metadata, `__version__`, save release strings, and version-current tests now target `3.5.0`.

### Validation

- Bytecode compilation and the full `unittest` suite (133 tests) pass, including 10 new milestone 3.5 tests. The run cycle still advances monotonically under frame-rate jitter.

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
