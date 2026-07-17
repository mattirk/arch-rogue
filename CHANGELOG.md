# Changelog

## 4.1.24 — Finalization Patch

Milestone 4.1.24 closes the remaining 4.1.x gameplay and presentation issues: shop floors carry a richer coin scatter, combat can no longer resolve through dungeon walls, and the modern aim cone is readable without changing the legacy renderer.

### Changed

- Increased deterministic cosmetic gold dressing in shop rooms to as many as `12` unique stacks. Existing stack positions remain the stable prefix of each layout, additional placements use an isolated local RNG, merchant/sign anchors stay clear, and the piles still create no pickup, currency, save-state, loot-stat, or gameplay-RNG changes.
- Player melee and Warden cleaves, Frost Nova, Time Skip's stagger pulse, Arcanist chain lightning, equipment chain procs, and Ambush Bell placement/trigger/splash now require direct dungeon line of sight. Walls, closed doors, and sealed diagonal corners block these attacks while open doors and clear floor paths remain valid.
- Player, enemy, and boss projectiles now validate the complete segment traveled each simulation step instead of only the destination tile, preventing high-step tunneling through walls. Projectile-to-player, projectile-to-familiar, and projectile-to-enemy contact also verifies the final short path so hits cannot leak across a closed corner seam.
- Enemy melee and cast entry points defensively enforce range/line of sight when invoked outside the normal AI loop. Stationary attacks reuse the loop's already-confirmed LOS result, while ranged, boss, and lured enemies that move before attacking revalidate from their final position. Familiar attacks retain their existing LOS protection, and lingering status ticks, ripostes, and thorns retain their established post-hit behavior.
- Doubled only the modern aim-cone source opacity from `14` to `28`, leaving its size, angle, cutout, blur, placement, and draw order unchanged. The final glow remains below 10% peak opacity but is now readily visible; legacy graphics reproduce the previous cone byte-for-byte.
- Aim-cone caching now includes graphics mode, theme-derived color, and facing, and is cleared with other derived graphics caches when modes change. Runtime/package release version is `4.1.24`; options remain schema `4` and run saves remain schema `5`.

### Tests

- Added wall-collision regressions for walls, closed doors, diagonal seams, player melee, Nova, both chain paths, swept player/enemy projectiles, direct enemy melee/casts, final-position LOS after enemy movement, and Ambush Bell placement/blasts, with open-path controls.
- Expanded shop-room coverage to lock the original eight-stack prefix, twelve-stack final scatter, unique/clear placements, population idempotence, unchanged currency/RNG, and save restoration without serialized gold props.
- Added rendered aim-cone coverage proving stronger modern alpha, stable geometry and warm-cache reuse, mode-cache invalidation, and exact legacy output after a modern/legacy round trip.

### Validation

- `.venv/bin/python -m unittest tests.test_enemy_los_walls tests.test_ambush_bell tests.test_special_rooms tests.test_world_rendering_and_animation tests.test_save_and_metadata` — 36 tests, all passing.
- `.venv/bin/python -m unittest tests.test_boss_encounters tests.test_familiars tests.test_lighting tests.test_skill_paths tests.test_combat_damage_and_loot_tables tests.test_pause_on_menus` — 67 tests, all passing.
- `.venv/bin/python -m unittest discover tests` — 306 tests, all passing; the experimental web build was not run separately.
- `.venv/bin/python -m compileall -q src tests tools` — OK.
- `git diff --check` — OK.

## 4.1.23 — Authored Action Skill Icons

Milestone 4.1.23 replaces the cramped modern action-bar glyphs and truncated skill names with a complete PixelLab-authored icon language while preserving the original procedural legacy HUD.

### Added

- Added `22` transparent `32×32` PixelLab HUD sprites: one distinct icon for each of the Warden, Rogue, Arcanist, Acolyte, and Ranger's four action skills, plus a matched healing/mana potion pair for hotkeys `5` and `6`.
- Added explicit per-archetype action-icon keys and manifest entries. Every modern slot now resolves its canonical authored sprite through the existing validated, lazy, size-cached `UiAssetLibrary` path.
- Added regression coverage for all `20` class-skill mappings, authored file dimensions and transparency, rendered asset use, warm caches, modern label suppression, and unchanged legacy labels/fallbacks.

### Changed

- Modern action slots no longer draw the long skill-name labels that were ellipsized beyond usefulness. The freed area is used for larger, more readable authored artwork; hotkey numbers, potion counts, cooldown shading/timers, resource warnings, and Spirit Beast `RETURN`/`ATTACK` command status remain intact.
- Legacy graphics still draw the original procedural action glyphs, label text, slot plates, and sizing, and do not decode or render the new UI assets. Missing/disabled modern assets continue through the established procedural fallback path.
- Action-icon body caching now distinguishes authored asset keys and graphics mode, retaining the steady-state one-blit-per-slot path. Runtime/package release version is `4.1.23`; options remain schema `4` and run saves remain schema `5`.

### Asset provenance

- PixelLab generation/review pack: `f511566e-a164-4263-9fb5-3a3d385d2555` (`20` generations), created with a cohesive grim dark-fantasy action-RPG HUD prompt requiring bold centered silhouettes, transparent backgrounds, and no frames or text.
- Approved candidates: Warden frames `0–3`; Rogue frames `4`, `5`, `10`, and `7`; Arcanist frames `16–19`; Acolyte frames `20–23`; Ranger frames `28–31`; healing/mana potion frames `50–51`. The `20` promoted skill objects use the `arch-rogue-action-icon-4.1.23` PixelLab tag; unused candidates and two mistakenly promoted review objects were discarded.
- All final sprites were reviewed both as an enlarged contact sheet and in the real six-slot HUD for every archetype, with a legacy Arcanist comparison confirming that only the modern path changed.

### Validation

- `.venv/bin/python -m unittest tests.test_hud_action_bar tests.test_ui_assets tests.test_save_and_metadata` — 11 tests, all passing.
- `.venv/bin/python -m unittest discover tests` — 298 tests, all passing; experimental web tests were not run separately.
- `.venv/bin/python -m compileall -q src tests tools` — OK.
- `git diff --check` — OK.
- The asset gate verifies all `22` icon keys, source files, exact dimensions, non-empty alpha bounds, transparent background pixels, scaled rendering, active modern HUD use, and cache reuse.

## 4.1.22 — Ranger Spirit Beast Petting

Milestone 4.1.22 lets the Ranger pet a living nearby Spirit Beast through the normal interact action, pairing a grounded kneel-and-reach animation with the beast's pleased response while preserving the companion's combat command and resource systems.

### Added

- Added Ranger-only petting for a living, cooldown-ready Spirit Beast within `1.5` tiles and clear dungeon line of sight. It remains on the normal interact action, but no longer occupies the generic HUD interaction tooltip; a half-size translucent world-space paw badge appears above the closest eligible beast instead.
- Petting restores up to `2` missing Spirit Beast HP, clamped to maximum health, emits a compact `+2` floater, and starts a per-beast `2.0`-second pet cooldown. It spends no mana, does not alter or reset the Ranger class-skill cooldown, does not summon or replace the beast, and leaves its return/attack command mode unchanged.
- Added synchronized `0.8`-second paired action state: the Ranger and Spirit Beast face each other, the Ranger briefly stays grounded in the kneeling pose, and familiar movement, perception, and attacks pause until the affection clip completes.
- Added complete authored `pet` clips for Ranger and Spirit Beast: eight directions, eight frames per direction, `10` FPS, and non-looping playback. The package gains `128` transparent PNG frames under canonical `ranger` and `spirit_beast` asset paths.
- Added procedural legacy fallbacks for the Ranger's kneel-and-reach and the Spirit Beast's pleased body wiggle, so petting remains readable when modern authored graphics are disabled or unavailable.

### State and resilience

- `Familiar.pet_cooldown` and `Familiar.pet_anim_timer` are transient runtime state. They are intentionally excluded from run saves, so loading resumes with the beast in its normal pose and immediately pettable; run-save schema remains `5` and options schema remains `4`.
- Pet rendering has priority over attack, walk, and idle state selection. Both modern and procedural paths use action-local progress, hold the final non-looping frame correctly, and return to ordinary simulation after the paired timer expires.
- Runtime/package release version is `4.1.22`.

### Asset provenance

- PixelLab Ranger character: `2a6c4684-9821-4520-96b2-b0622bfb0d91`; approved `pet` group: `61eff18d-b0fe-4842-abed-16cb49a37321`.
- PixelLab Spirit Beast character: `ad64a571-0551-4de1-b6c4-81a6dc717a7e`; approved `pet` group: `11edf405-b927-4157-947f-c5c22dad2937`.
- The user reviewed and approved both final eight-direction animation groups before they were downloaded and integrated. Ranger frames retain the existing `256×256` contract; Spirit Beast frames retain the existing `184×184` contract.

### Validation

- `.venv/bin/python -m unittest tests.test_familiars tests.test_inventory_hud_and_hints tests.test_world_rendering_and_animation` — 41 tests, all passing.
- `.venv/bin/python -m unittest discover tests` — 296 tests, all passing; experimental web tests were not run separately.
- `.venv/bin/python -m compileall -q src tests tools` — OK.
- Packaged asset gate verifies every direction and frame, source dimensions, transparent margins, frame uniqueness, non-looping endpoints, and modern runtime resolution for both actors.
- `git diff --check` — OK.

## 4.1.21 — Ranger Spirit Beast Commands

Milestone 4.1.21 renames the Ranger's companion skill to Spirit Beast, makes the summon durable enough for its new long replacement cadence, and turns every cast made while the beast is alive into a direct return/attack command.

### Changed

- Canonicalized the Ranger class skill as `Spirit Beast` across runtime dispatch, familiar kind values, method names, skill lists, archetype selection, the character sheet, HUD labels/icons, discipline descriptions, effects, authored-asset metadata, on-disk asset paths, and tests. The character sheet reports `Beast DMG`.
- Increased base Spirit Beast health from `30` to `60` and base bite damage from `7` to `12`. Existing Beast-discipline increments remain additive, producing a fully upgraded `138` HP / `26` damage companion.
- Spirit Beast summoning now always costs exactly 50% of the Ranger's current maximum mana and starts an exact 60-second replacement cooldown. Equipment discounts, curses, and cast speed do not alter either summon value.
- A living Spirit Beast is never resummoned, replaced, healed, or charged mana by another class-skill cast, even after the replacement cooldown reaches zero. Casts instead alternate between `RETURN`, which suppresses enemy targeting and regroups within `0.9` tiles of the Ranger, and `ATTACK`, which resumes nearest visible-enemy targeting.
- Return/attack commands cost no mana, do not reset or consume the replacement cooldown, and remain available even at zero mana. The HUD action slot displays the next `RETURN` or `ATTACK` command and remains visibly actionable while the summon timer is running.
- Summoning resolves a clear, radius-safe position with direct dungeon line of sight before spending mana or starting cooldown. It samples progressively wider rings and nearby floor centers instead of falling back into blocked geometry; if no safe point exists, the cast has no cost and creates no beast.
- Runtime/package release version is `4.1.21`. Options remain schema `4` and run saves remain schema `5`.

### Refactor and resilience

- The runtime familiar kind, class-skill dispatch, HUD icon, authored manifest key, procedural helper, and actor directory now use only `spirit_beast`; no legacy aliases or method wrappers remain.
- Ranger class-skill equipment recognizes only `Spirit Beast` wording. `Beastlord Harness` now grants `Spirit Beast bond`, adding `12` HP and `2` bite damage and refreshing an already-active beast immediately when equipped.
- `Familiar.command_mode` is serialized as `attack` or `follow`; invalid values default to `attack`. Existing positional constructor arguments retain their prior meaning, but obsolete familiar kind values are intentionally not migrated.
- Wall-blocked perception and attacks remain unchanged: attack mode only selects enemies with clear dungeon line of sight, while return mode ignores enemies entirely.

### Validation

- `.venv/bin/python -m unittest tests.test_familiars tests.test_hud_action_bar` — 31 tests, all passing.
- `.venv/bin/python -m unittest discover tests` — 292 tests, all passing; no web-specific modules were present under `tests/`.
- `.venv/bin/python -m compileall -q src tests tools` — OK.
- `git diff --check` — OK.

## 4.1.20 — Ranger Spirit Beast

Milestone 4.1.20 introduces the Ranger's persistent Spirit Beast companion, makes the existing Beast discipline path directly strengthen it, and adds a complete reviewed directional animation set.

### Added

- Added `Spirit Beast` as the Ranger's hotkey-3 class skill. Casting spends the established class-skill mana/cooldown budget, summons one beast beside the Ranger, and recreates it at full health with the current build's stats. The beast persists until killed, resummoned, or floor descent.
- Added Ranger-specific beast progression. Beast Bond grants health and bite damage; Pack Tactics adds health, damage, attack speed, and bonus damage against snared foes; Alpha adds dire-beast health, damage, speed, and knockback; Spirit Companion adds health, damage, speed, faster arcane bites; and Primal Lord creates a tougher champion with faster attacks and bonus damage against elites and bosses. Choosing a Beast discipline refreshes an already-active beast immediately.
- Added a dedicated `spirit_beast` HUD slot/icon, forest-green paw-call summon effect, discipline-aware `Beast DMG` character-sheet stat, and a grounded procedural Spirit Beast fallback for legacy graphics or missing authored files.
- Added a modern `Spirit Beast` actor with eight base rotations and eight-frame `idle`, `walk`, and non-looping `attack` clips in all eight directions.
- Added regression coverage for Ranger skill dispatch and presentation, resource/cooldown use, summon/recast/descent lifecycle, every Beast rank's stats, active-beast refresh, marked/elite/knockback behavior, save compatibility, wall-blocked perception and attacks, closed diagonal corners, attack animation state, authored asset completeness, frame uniqueness, and runtime state resolution.

### Changed

- Removed the former Ranger class skill from Ranger runtime and menu-facing skill lists. Ranger class-skill dispatch now resolves to `spirit_beast`; Arcanist Frost Nova and other archetype class skills are unchanged.
- Familiar targeting now requires clear dungeon line of sight before pursuit or attack. The shared LOS trace also rejects zero-width seams between two touching orthogonal walls, preventing both familiars and enemies from attacking through closed diagonal corners.
- Familiar rendering now carries an explicit additive `kind` (`spirit` or `spirit_beast`), selects the Spirit Beast's approved idle/walk/attack states, keeps its body grounded instead of applying spirit bobbing, and uses a Ranger-green health bar.
- Ranger class-skill equipment uses `Spirit Beast` wording directly.
- Fixed slow beast movement jitter at its follow and attack boundaries. Familiar walk clips now use a simulation-local phase, final movement steps are capped to the remaining distance, slow cadence retains a smooth 25% floor, blocked movement does not animate, and directional-sheet hysteresis prevents adjacent directions from flickering near sector edges.
- Applied the same animation-timing audit to other actors: player/enemy cadence follows actual analog, equipment, status, Time Skip, collision, and stopping-distance movement; enemy/friendly-NPC threshold transitions no longer burst or chatter; controller deadzone activation is hysteretic without latching neutral drift; menu-paused actor clocks freeze; and hit/action clips use local progress in both modern and procedural graphics.
- Projectile animation now uses simulation-local age rather than global time plus live position, so travel direction and homing do not alter frame cadence. Friendly NPC directions and proximity holds use transient hysteresis, and cutscene duel choreography now begins from cutscene-local time rather than an arbitrary run-global phase.
- Overlapping fractional movement slows are integrated piecewise, including the low-cadence floor, so one coarse update produces the same enemy displacement and animation phase as equivalent split updates.
- Runtime/package release version is `4.1.20`. Options remain schema `4` and run saves remain schema `5`.

### Asset provenance

- PixelLab character `Spirit Beast`: `ad64a571-0551-4de1-b6c4-81a6dc717a7e`.
- Character prompt: “lean loyal grey beast familiar for the Ranger, natural quadruped canine anatomy, alert pointed ears, long muzzle, bushy tail, charcoal and ash-grey fur with a pale throat and underbelly, subtle forest-green leather collar with one small bronze ranger medallion, amber eyes, battle-ready but not monstrous, no saddle, no armor, no clothing, no weapons, no magic aura, no extra limbs, readable grim dark-fantasy isometric action-RPG pixel art, transparent background”.
- Final `idle` group: `aa96e139-9756-4e19-b3d8-15cb42036d69`.
- Final `walk` group: `07d39bb4-8aec-4806-9b5b-1fb490cf36eb`.
- Final `attack` group `7f6bdbbc-c3f7-4815-9ca7-ed01fb576237`: “attack with one fast grounded forward bite: lower the head, bare the teeth, lunge a short distance, snap the jaws once, then recoil to the starting stance; keep the original facing direction locked, all four legs and the tail visible, no turning, spinning, barking, magic, or camera-facing pivot”.
- The user reviewed and approved the final rotations plus all idle, walk, and attack directions in PixelLab. The packaged set contains exactly `200` transparent `184×184` PNGs: `8` rotations and `192` animation frames.

### Compatibility and resilience

- `Familiar.kind` is additive and defaults to `spirit`, so pre-4.1.20 Acolyte familiar payloads retain their wisp/owl behavior. Old saves without a `familiars` collection still load an empty host, and the run-save schema remains `5`.
- Familiar attack-animation time is transient and intentionally excluded from saves. Saved position, health, damage, cooldown, facing, champion state, and other existing fields retain their prior shape and behavior.
- Missing modern Spirit Beast assets resolve through the procedural canine fallback. Missing individual clips continue through the asset resolver's established rotation/fallback path.
- New locomotion scales, sprite-direction anchors, projectile age, and hit/action clocks are transient and excluded from run payloads. Existing positional constructor prefixes remain valid, and the save schema remains `5`.
- The separately documented 60-second cooldown and in-cooldown recall/attack command toggle are future ideas and are intentionally not part of this milestone.

### Validation

- Human review approved the final PixelLab rotations and all three eight-direction animation groups.
- Packaged asset gate: exactly `200` transparent `184×184` PNGs (`8` rotations plus `64` idle, `64` walk, and `64` attack frames), eight unique frames in every directional clip, eight distinct direction sequences per state, complete transparent margins, and successful idle/walk/attack runtime resolution.
- `.venv/bin/python -m unittest tests.test_familiars tests.test_enemy_los_walls tests.test_sprite_assets tests.test_skill_paths tests.test_skill_tree_choices_and_menu tests.test_hud_action_bar tests.test_save_and_metadata tests.test_world_rendering_and_animation tests.test_ambush_bell` — 77 tests, all passing.
- `.venv/bin/python -m compileall -q src tests tools` — OK.
- Animation-focused regression suite (`test_movement_animation`, `test_familiars`, `test_world_rendering_and_animation`, `test_time_skip`, `test_sprite_assets`, `test_input_and_accessibility`, `test_friendly_npcs`, `test_cutscene_runtime`, and `test_pause_on_menus`) — 127 tests, all passing.
- `.venv/bin/python -m unittest discover tests` — 287 tests, all passing; experimental web tests were not run.
- Worst-case overlapping partial-slow timing probe: `100` enemies averaged `0.2041 ms` per batch under dummy SDL.
- `git diff --check` — OK.

## 4.1.19 — Profile-Guided Frame Optimization

Milestone 4.1.19 adds a deterministic gameplay profiler and applies measured, low-risk hot-path optimizations to dense combat simulation, actor rendering, and continuous lighting.

### Added

- Added `tools/profile_game.py`, a headless fixed-step `cProfile` harness with deterministic quiet-floor and dense-crowd scenarios. It profiles `Game.update()` and `Game.draw()` separately, supports seed/depth/resolution/zoom/lighting controls, prints cumulative hotspots, and writes reusable `.prof` files.
- Added regression coverage for attack-eligible enemy LOS checks, stationary fog-of-war reveal caching and invalidation, final-dimension shadow reuse, bounded actor-resolution keys, one moving light per projectile, off-screen transient-light culling, and projectile-light decay.

### Changed

- Preserved actor-contact resolution order while removing per-mover all-actor list construction, caching the moving actor's radius, and rejecting non-overlapping pairs with squared distances before computing a square root. Dense contact resolution cumulative time fell from `0.814 s` to `0.373 s` over the 240-frame stress profile.
- Enemy wall LOS is now evaluated only when attack range and cooldown make an attack possible that frame. The stress scenario dropped from `12,000` dungeon LOS traces to `110`; pursuit and through-wall attack prevention are unchanged.
- Replaced distance-only `hypot` work with squared-radius comparisons in live visibility, dark-floor inner/outer visibility gates, projectile/familiar collision checks, homing and chain target scans, secrets, and shop range checks. Stationary light-floor players no longer rebuild the same reveal disk every frame, while movement, floor changes, set replacement, and in-place clearing invalidate safely.
- Each projectile now refreshes one associated transient `LightSource` instead of appending another overlapping source every frame. The existing four-sprite visual trail remains, the leading glow follows the projectile, and the final light still decays after impact or expiry.
- Added bounded reuse for final-size soft shadows, projectile trail surfaces, actor slug/frame resolution keys, and lit sprite composites. Actor resolution keys delegate surface ownership to the existing 320-frame LRU rather than extending image residency. Transient lights whose radius cannot overlap the visible bounds are skipped by light collection.
- Empty impact/slash/hit-flash collections avoid unnecessary per-frame compaction work.
- Runtime/package release version is `4.1.19`. Options remain schema `4` and run saves remain schema `5`.

### Profile results

- Deterministic dummy-SDL stress profile: `960×540`, seed `3161`, depth `10`, `50` clustered generated enemies, lighting on, `20` warm-up frames plus `240` measured frames.
- Profiled update CPU time improved from `4.945 ms/frame` to `2.754 ms/frame` (`44.3%` lower).
- Profiled render CPU time improved from `20.463 ms/frame` to `15.339 ms/frame` (`25.0%` lower).
- Major render hotspot totals improved as follows: lighting `1.357 s → 0.627 s`, soft shadows `0.414 s → 0.175 s`, and actor resolution `0.477 s → 0.292 s` over 240 frames.
- The final unmodified generated-floor profile measured `0.665 ms/update` and `5.307 ms/render`. These are comparative `cProfile` results under the dummy SDL driver, not claims about end-user GPU/display FPS.

### Compatibility and resilience

- Enemy movement, attack timing, collision ordering, hit radii, visibility radii, fog-of-war contents, projectile damage/collision, and save payloads retain their existing rules.
- Dynamic projectile lighting intentionally consolidates the former chain of overlapping additive halos into one leading glow; the four-sprite trail remains unchanged. `Projectile.light_source` is an additive optional runtime-only field excluded from dataclass comparison, so existing positional constructors and old saves remain compatible; active projectiles are intentionally not serialized.
- All new surface caches are bounded, while actor-resolution keys own no image surfaces beyond the existing frame LRU. Missing modern assets and disabled lighting continue through the established procedural/web fallback paths.

### Validation

- `.venv/bin/python -m unittest tests.test_enemy_los_walls tests.test_dark_levels tests.test_lighting tests.test_soft_shadows` — 31 tests, all passing.
- `.venv/bin/python -m unittest tests.test_lighting tests.test_combat_damage_and_loot_tables tests.test_familiars tests.test_pause_on_menus tests.test_world_rendering_and_animation tests.test_soft_shadows tests.test_enemy_los_walls tests.test_dark_levels` — 51 tests, all passing.
- `.venv/bin/python -m compileall -q src tests tools` — OK.
- `.venv/bin/python -m unittest discover tests` — 251 tests, all passing; experimental web tests were not run.
- `.venv/bin/python tools/profile_game.py --scenario crowd --frames 240 --warmup 20 --output-dir /tmp/arch-rogue-profile-final` — completed with the profile results above.

## 4.1.18 — Lower Bar Sconce Mounts

Milestone 4.1.18 lowers both bar-wall sconces toward the floor so each candle reads as attached to the lower portion of its isometric wooden wall face rather than floating near the upper trim.

### Changed

- Lowered `LIGHT_BAR_WALL_ELEVATION` from `0.75` to `0.50` tile heights, moving each authored or procedural fixture downward by one quarter of `TILE_H` (`40` pixels at native world scale).
- The fixture mount now derives its vertical screen position from the same elevation constant used by the lighting pass. The candle sprite and warm light halo therefore remain centered together at every viewport zoom.
- Both left and right wall-face directions retain their reviewed south-west/south-east assets and horizontal wall-plane placement; only vertical mounting height changed.
- Runtime/package release version is `4.1.18`. Options remain schema `4` and run saves remain schema `5`.

### Compatibility and resilience

- Bar wall-tile anchors, asset names, facing assignments, cache keys, and save payload shape are unchanged.
- Existing saves rebuild their static `bar_wall_light` sources through the established reconciliation path, adopting the lower elevation without a schema migration or duplicate lights.
- Missing modern sconce art still uses the procedural backplate, bracket, candle, and flame at the same lower mount point.

### Validation

- Reviewed a four-panel old-versus-new comparison for both wall faces. The new fixtures sit visibly closer to the wall base while remaining fully contained on their wooden side panels and aligned with the correct isometric face.
- Added mount geometry assertions proving the new point is lower than the former midpoint mount, remains above the floor anchor, and intersects both authored and procedural fixture pixels.
- `python -m unittest tests.test_sprite_assets.SpriteAssetTests.test_bar_wall_sconces_render_assets_and_procedural_fallback tests.test_lighting.LightingTests.test_static_shrine_and_bar_wall_lights_populated tests.test_lighting.LightingTests.test_legacy_bar_center_torch_migrates_to_wall_sconces tests.test_dungeon_tile_variants.DungeonSpriteVariants36Tests.test_prewarm_and_draw_cache_bounds_stable tests.test_save_and_metadata.SaveAndMetadataTests.test_metadata_content_profiles_and_save_version` — 5 tests, all passing.
- `python -m compileall -q src tests` — OK.
- `python -m unittest discover tests` — 248 tests, all passing.

## 4.1.17 — Dwarven Bar Dancer

Milestone 4.1.17 adds a second, guaranteed tavern performer to every bar: a stocky dwarven `Bar Dancer` who roams between music-synchronized dance breaks, carries friendly lantern light, and uses a dedicated reviewed eight-direction sprite set distinct from the optional hooded wayfarer.

### Added

- Added exactly one deterministic `IdleNpc(kind="bar_dancer")` to every bar room, named `Bar Dancer` with role `Tavern Reveler`. The existing optional `kind="bar"` wayfarer and its independent 50% roll remain unchanged, so both NPCs can occupy the same tavern without overlapping.
- Added a dedicated `bar_dancer` special-room anchor. The dancer uses the established friendly-NPC runtime for deterministic room-bound roaming, two-beat travel, four-beat dance breaks, obstacle avoidance, and shared procedural-music phase.
- Added a dedicated modern `Bar Dancer` actor: eight base rotations, eight-frame `walk` loops in all eight directions, and eight-frame `dance` loops in all eight directions. Idle presentation uses the reviewed directional rotations.
- Added a distinct procedural dwarven fallback with separate idle, walk, and eight-frame tavern-stomp dance states, preserving the feature when modern graphics are disabled or authored files are unavailable.
- Added regression coverage for guaranteed/idempotent population, optional-patron coexistence, clear spawn tiles, dedicated home anchoring, non-interaction, humanoid lantern inclusion, serialization, pre-dancer save backfill, duplicate repair, dedicated render dispatch, authored asset completeness, cross-direction sequence uniqueness, beat addressing, and distinct procedural fallback states.

### Changed

- Bar population no longer returns merely because another decorative NPC already occupies the room. The optional wayfarer and mandatory dancer are reconciled independently with local room-seeded RNG and without advancing gameplay RNG.
- Friendly humanoid enumeration naturally includes `bar_dancer`, so the new NPC emits the same cosmetic `friendly_lantern` light as the player, shopkeepers, story guests, and other humanoid idle NPCs. Garden frogs remain excluded.
- Stationary Bar Dancers resolve the dedicated `dance` clip, moving dancers resolve `run` through the packaged `walk` frames, and generic bar/garden travelers continue using Story Guest art. The `bar` asset alias remains owned only by Story Guest.
- Runtime/package release version is `4.1.17`. Options remain schema `4` and run saves remain schema `5`.

### Asset provenance

- PixelLab character `Bar Dancer`: `20f51a7b-8877-4a42-9939-5b8259ea5718`.
- Character prompt: “jovial stocky dwarven tavern dancer, broad short humanoid silhouette, uncovered head, bright copper-red swept-back hair and large braided beard, round nose and rosy cheeks, friendly grin, cream rolled-sleeve shirt, emerald green waistcoat with brass buttons, burgundy trousers, striped ochre sash, heavy brown dancing boots, small pewter tankard clipped securely to belt, both hands free, no hood, no cloak, no robe, no staff, no weapon, no armor, no aura, no magic effects, full-body medieval dark-fantasy bar reveler, readable high-quality pixel art”.
- Final `walk` group `59ce6b90-8788-4d1e-8a4a-1d5ed83939ee`: “Walk forward with a grounded, confident short dwarven stride while keeping the original facing direction locked. East and west remain side profiles, north remains back-facing, and diagonals keep their original three-quarter angle. Alternate the heavy boots naturally with modest opposite arm swings; the large braided beard, ochre sash, and belt tankard bounce slightly with each step. Preserve the short stocky body, uncovered swept copper hair, cream rolled sleeves, emerald waistcoat, burgundy trousers, heavy boots, free empty hands, and exact identity in every frame. No turns, spins, weapons, gestures, or camera-facing pivots.”
- Final `dance` group `6f45f867-5cfe-4f00-a044-b1455c16d96b`: “Dance in place with the original facing locked for the entire loop. Never rotate or turn toward the viewer: east and west remain strict side profiles, north remains fully back-facing, and diagonal views remain at their original three-quarter angle. Perform a grounded four-beat dwarven tavern stomp: left boot stomp, clap both empty hands at chest height, right boot stomp, then raise both fists in celebration before returning to the start. No spins, pivots, travel, weapons, or props in the hands. Preserve the short stocky body, uncovered swept copper hair, large braided copper beard, cream rolled sleeves, emerald waistcoat, burgundy trousers, ochre sash, heavy boots, and belt tankard in every frame. Beard, sash, and tankard bounce naturally without disappearing.”
- PixelLab limits the `244×244` canvas to eight generated animation frames. The incomplete load-failed template walk group `09257acb-3dd7-40ca-bc59-885f0f653051` and rejected first dance group `82527792-4dd3-4856-9f63-7907af59d275` were deleted; the MCP character now contains exactly the two complete maintainable groups above.

### Compatibility and resilience

- Pre-4.1.17 saves with a persisted bar automatically receive exactly one dancer. Reconciliation calls only the dancer path, so it never performs or replays the optional patron roll, and repeated restores are idempotent.
- Valid saved or runtime-moved dancers retain identity and position. Duplicate dancers are removed, missing anchors are repaired, and corrupt fully occupied rooms still choose a deterministic passable fallback tile.
- The public `IdleNpc` model and save schema are unchanged. Missing assets use the procedural dwarf; missing animation clips fall back through the existing asset resolver without affecting movement, lighting, interaction, or save data.

### Validation

- The user visually approved the final overview sheets. All eight rotations and every retained walk/dance frame were reviewed for the dwarven silhouette, hair, beard, clothing, free hands, boots, belt tankard, readable motion, and transparent margins; the separately surfaced south-west walk also passed frame-by-frame review.
- Packaged asset gate — exactly 136 `244×244` PNGs (`8` rotations + `64` walk + `64` dance), byte-identical to the final MCP export, with non-empty alpha, transparent canvas margins, eight unique rotations, eight unique frames in every directional clip, eight distinct direction sequences per state, and no walk sequence duplicated by its corresponding dance sequence.
- `python -m unittest tests.test_flavor_rooms tests.test_friendly_npcs tests.test_lighting tests.test_sprite_assets tests.test_save_and_metadata` — 72 tests, all passing.
- `python -m compileall -q src tests` — OK.
- `python -m unittest discover tests` — 248 tests, all passing; no web-specific test modules or imports are present in `tests/`.

## 4.1.16 — Controller and Startup Defaults

Milestone 4.1.16 updates fresh-install controller and display preferences: the shipped gamepad profile uses the requested raw SDL button assignments, Medium becomes the default difficulty, and desktop play starts fullscreen.

### Changed

- Replaced the default gameplay button profile with: button `0` → `interact`, `1` → `ability_3`, `2` → `ability_2`, `3` → `ability_5`, `5` → `ability_6`, `6` → `inventory`, `7` → `character`, `11` → `back`, and `13` → `ability_4`.
- Default trigger slots are now unbound because `interact` and `ability_4` have explicit button assignments. Triggers remain remappable through the controls menu.
- Fresh desktop installs now start fullscreen. Headless execution still uses a hidden window, the web build continues to force fullscreen off, and explicit saved windowed/fullscreen preferences remain authoritative.
- Changed `DEFAULT_DIFFICULTY_NAME` from Hard to Medium and updated the difficulty descriptions, options note, onboarding text, and README accordingly.
- Runtime/package release version is `4.1.16`. Options remain schema `4` and run saves remain schema `5`.

### Compatibility and resilience

- Existing option files keep every explicit gamepad, fullscreen, and difficulty value. Only absent fields or a fresh install receive the new defaults.
- Older option files with explicit `fullscreen: false` or `difficulty: Hard` continue loading those values unchanged.
- Menu and cutscene button contexts remain unchanged; the new table applies to gameplay, with button `11` retaining universal back behavior.

### Validation

- Added exact default-map assertions for integer and serialized string button IDs, empty trigger defaults, gameplay dispatch lookup, menu confirm, and universal back behavior.
- Added fresh-install and missing-field tests for fullscreen/Medium defaults plus legacy-option assertions proving explicit old values are preserved.
- `.venv/bin/python -m unittest tests.test_input_and_accessibility tests.test_archetypes_options_and_difficulty tests.test_save_and_metadata tests.test_ui_assets tests.test_ui_layouts` — 42 tests, all passing.
- `.venv/bin/python -m compileall -q src tests` — OK.
- `.venv/bin/python -m unittest discover tests` — 245 tests, all passing.

## 4.1.15 — Wall-Aligned Bar Sconces

Milestone 4.1.15 corrects the bar-sconce rotations so every fixture follows the same world-vector-to-screen-direction mapping as actor sprites and visibly faces into its room from a backplate seated against the wall.

### Changed

- Corrected the visible wall-face mapping from the screen-side labels to PixelLab compass rotations: the `bar:left` (`+y`) face now uses `south-west`, while `bar:right` (`+x`) uses `south-east`.
- Swapped the previously reversed fixtures so the candle and bracket project into the bar instead of across the wall texture, and each backplate perspective now follows its wood-paneled face.
- Renamed packaged assets to `bar_wall_sconce_south_west.png` and `bar_wall_sconce_south_east.png`. The old `bar_wall_sconce_left`/`bar_wall_sconce_right` aliases remain accepted by the asset manifest.
- Added an explicit `BAR_WALL_SCONCE_DIRECTION_BY_FACE` contract and regression assertions tying it to `actor_sprite_direction(0, 1)` / `actor_sprite_direction(1, 0)`, preventing screen-side and compass directions from being reversed again.
- Runtime/package release version is `4.1.15`. Run saves remain schema `5`; light positions, wall anchors, and save payloads are unchanged.

### Asset provenance

- Reused the reviewed south-west and south-east rotations from PixelLab object `5a907401-c4ac-4ff5-bfc9-29235340001a`; no additional generations were spent.
- The same two `68×68` transparent sources are retained. Only their face assignment and direction-based packaged names changed.

### Compatibility and resilience

- Existing saves need no migration: bar wall anchors still use `bar_wall_light_left`/`bar_wall_light_right`, while rendering resolves those face labels through the corrected compass-direction map.
- Procedural/legacy sconces already derive their projection from the face side and continue to point inward without asset dependencies.

### Validation

- Reviewed a four-panel real-wall comparison of old vs corrected mappings. The corrected pair seats each backplate against the matching plank perspective and projects each candle toward the bar interior.
- Reviewed a full in-game dark-floor bar render at `0.65×` viewport zoom and confirmed runtime resolution as `left → bar_wall_sconce_south_west` and `right → bar_wall_sconce_south_east`.
- `.venv/bin/python -m unittest tests.test_lighting tests.test_flavor_rooms tests.test_friendly_npcs tests.test_sprite_assets tests.test_save_and_metadata` — 69 tests, all passing.
- `.venv/bin/python -m compileall -q src tests` — OK.
- `.venv/bin/python -m unittest discover tests` — 242 tests, all passing.

## 4.1.14 — Lantern-Bearing Friends and Bar Sconces

Milestone 4.1.14 gives friendly humanoid NPCs the player's warm lantern light and replaces each bar's room-center torch with two visible, wall-mounted medieval candle sconces.

### Added

- Added frame-derived `friendly_lantern` sources for every `Shopkeeper`, `StoryGuest`, and humanoid `IdleNpc`. They reuse the player's lantern color, radius, intensity, and flicker, follow roaming NPC positions, and never enter persistent or transient light lists.
- Added two deterministic sconce mounts to every bar: one on each visible interior wood-paneled wall face. Each mount has a flickering warm `bar_wall_light` source projected at wall height and a matching rendered fixture.
- Added two reviewed MCP wall-sconce sprites, with asset-first atlas resolution and a procedural wrought-iron candle fallback for legacy or missing graphics.
- Added focused regression coverage for humanoid classification, frog exclusion, lantern movement, static-list isolation, deterministic/idempotent wall mounts, face orientation, elevated source properties, generated and procedural fixture rendering, prewarmed cache variants, sprite contracts, save round-tripping, old-save backfill, and legacy center-torch migration.

### Changed

- Garden frogs remain friendly dancers but do not emit humanoid lantern light.
- Bar lighting now comes from two wall sconces instead of one generic torch at room center. Existing saves remove the legacy center source and rebuild the current pair without advancing gameplay RNG.
- `LightSource` gained an additive `elevation` field, expressed in tile-height units. Existing floor-level and transient lights default to `0.0`; save payloads missing the field restore safely at floor level.
- Runtime/package release version is `4.1.14`. Run saves remain schema `5`; pre-4.1.14 saves require no schema migration.

### Asset provenance

- Medieval bar wall sconce object: `5a907401-c4ac-4ff5-bfc9-29235340001a` (20-generation PixelLab eight-direction object pipeline).
- Object prompt: “compact medieval dark-fantasy tavern wall sconce, wrought-iron backplate and short iron bracket, one thick aged beeswax candle with visible melted wax and a bright amber flame, isolated complete wall-mounted object, transparent background, crisp pixel art, strong dark outline, warm brass-brown and amber palette, readable at small game scale, no wall, no floor, no text, no smoke, no aura and no painted glow halo”.
- Reviewed all eight `68×68` rotations. The south-east rotation is retained for the bar's left visible face and the south-west rotation for the right visible face, so each backplate follows its isometric wall plane while the candle projects into the room.

### Compatibility and resilience

- Friendly NPC lanterns are cosmetic lighting only: they do not reveal unexplored terrain, extend player perception, alter line of sight, or modify NPC/save models.
- Static sconce anchors are stored in existing `SpecialRoom.anchor_points`/`reserved_tiles`; older bars receive them deterministically when loaded, and repeated population is idempotent.
- Saves without `light_sources` backfill current shrine, garden, and bar fixtures. Saves without `elevation` remain valid, and transient combat lights remain unsaved.
- Missing or disabled modern sconce art falls back to a cached wall-tile surface with a procedural iron backplate, bracket, candle, and flame.

### Validation

- Visually reviewed all eight MCP rotations and an in-game dark-floor render at `0.65×` viewport zoom, including fixture scale, wall-height placement, and elevated light-halo alignment.
- Packaged asset gate — both retained sprites are `68×68` RGBA PNGs with non-empty alpha (`34×47` opaque bounds), resolve through the production atlas, and retain transparent canvas margins.
- `.venv/bin/python -m unittest tests.test_lighting tests.test_flavor_rooms tests.test_friendly_npcs tests.test_sprite_assets tests.test_save_and_metadata` — 69 tests, all passing.
- `.venv/bin/python -m compileall -q src tests` — OK.
- `.venv/bin/python -m unittest discover tests` — 242 tests, all passing.

## 4.1.13 — Dancing Garden Frogs

Milestone 4.1.13 fills every generated garden with two cheerful frog revelers that hop around the room and visibly dance on the procedural soundtrack's shared four-beat phrase.

### Added

- Added two deterministic, decorative `garden_frog` NPCs to every garden flavor room. Frog names come from a local room-seeded pool, they remain non-interactable, and the existing optional humanoid garden wanderer is preserved.
- Added a dedicated `Garden Frog` actor with eight reviewed directional rotations, an eight-frame traveling hop, and an eight-frame four-beat dance state. Seven directions use authored dance frames; north intentionally reuses the north walk cycle.
- Added a procedural frog sprite fallback and an asset-first `garden_frog_visual`/`garden_frog_frame` facade so both modern and legacy graphics modes retain the new NPC behavior.
- Added regression coverage for mandatory frog population, unique deterministic names, idempotent room re-population, non-interaction, save restoration, rendering, shared beat phase, room-bound roaming, and the complete sprite contract.

### Changed

- Garden frogs use the existing friendly-NPC transport and deterministic movement runtime: they avoid actors and room obstacles, roam up to `4.5` tiles from home, finish each route, and then dance until a phrase boundary at least two beats after arrival.
- Frog dance frames are addressed directly from normalized four-beat music progress, making frames `0`, `2`, `4`, and `6` land on consecutive downbeats while all friendly NPCs remain synchronized.
- Flavor-room local RNG now includes stable room geometry, keeping bar and garden humanoid rolls independently near the intended 50% instead of repeating a small set of room-count/index outcomes.
- Frog spawn tiles are selected deterministically from clear, passable garden tiles after general population, preventing overlap with enemies, loot, traps, shrines, secrets, friendly actors, familiars, or the player.
- Runtime/package release version is `4.1.13`. Run saves remain schema `5`; pre-4.1.13 gardens are reconciled additively to exactly two frogs without a schema migration.

### Asset provenance

- Garden Frog character: `3b6f153e-a0e2-4034-90ad-5406ed985f21`.
- Character prompt: “small cheerful anthropomorphic garden frog NPC, vivid moss-green skin, round golden eyes, cream throat and belly, tiny leaf collar, compact upright body, webbed hands and large webbed feet, no weapons, no aura, no magic effects, full-body dark-fantasy garden reveler, readable pixel-art silhouette”.
- `walk` prompt: “small cheerful frog moving forward with rhythmic garden hops, alternating low crouch and short springing hop, clear webbed-foot landings, gentle throat and leaf-collar bounce, fixed directional facing, seamless locomotion loop, preserve the round golden eyes, cream belly, leaf collar, webbed hands, large webbed feet and every body part, no magic effects”.
- `dance` prompt: “pronounced four-beat frog dance in place with exactly two frames per musical beat: beat one deep squat and left webbed-foot stomp, beat two spring upright with both forelegs raised, beat three deep squat and right webbed-foot stomp, beat four spring upright with both forelegs raised; cheerful head bob, throat puff and leaf-collar bounce, feet stay grounded between small springs, fixed directional facing, no spins, seamless 8-frame loop, preserve the round golden eyes, cream belly, leaf collar, webbed hands, large webbed feet and every body part, no magic effects”.
- MCP limits `240×240` character animations to eight frames. The north-west dance direction was regenerated in place and retained from animation `e0492122-646d-453e-b481-5c9dddc9424a`; the unnecessary north dance was removed in MCP and its packaged slot is an exact copy of north walk.

### Compatibility and resilience

- The public `IdleNpc` model and save payload are unchanged; older garden saves automatically receive the deterministic pair, while duplicate, unknown, or extra frog records and stale anchors are repaired idempotently.
- Missing or disabled modern assets fall back to cached procedural frog frames while preserving the same direction, movement state, beat-derived lift, and compact contact shadow.
- Bar patrons and humanoid garden wanderers continue to use the existing Story Guest visual contract without changes.

### Validation

- Reviewed all eight rotations, all 64 walk frames, and the seven retained authored dance directions on labeled sheets; the regenerated north-west loop has eight unique frames and four distinct beat poses, while north dance is byte-identical to the approved north walk sequence by design.
- Packaged asset gate — exactly 136 `240×240` RGBA PNGs (`8` rotations + `64` walk + `64` dance-state frames), all with non-empty alpha, transparent canvas margins, eight unique frames per directional sequence, and direct normalized-loop addressing at frames `0/2/4/6`.
- Generated-floor stress probe — 1,000 floors contained 514 gardens and 1,028 frogs with exactly two unique frogs per garden and zero same-tile overlaps against enemies, items, traps, shrines, secrets, friendly NPCs, or the player; targeted restoration also verified familiar avoidance.
- Flavor RNG probe — 6,000 generated dungeons measured optional humanoid rates of `49.76%` for bars and `49.95%` for gardens, with exactly two uniquely named frogs in all 3,029 sampled gardens.
- `.venv/bin/python -m unittest tests.test_flavor_rooms tests.test_friendly_npcs tests.test_sprite_assets tests.test_save_and_metadata` — 48 tests, all passing.
- `.venv/bin/python -m unittest tests.test_friendly_npcs tests.test_world_rendering_and_animation tests.test_save_and_metadata` — 16 tests, all passing.
- `.venv/bin/python -m compileall -q src tests` — OK.
- `.venv/bin/python -m unittest discover tests` — 238 tests, all passing.

## 4.1.12 — Stronger Four-Beat NPC Dancing

Milestone 4.1.12 makes friendly-NPC dancing visibly lock to the procedural soundtrack and gives room-bound NPCs more space and speed to roam.

### Added

- Added dedicated 16-frame MCP `dance` loops in all eight directions for both `Shopkeeper` and `Story Guest`, adding 256 reviewed transparent animation frames.
- Added a shared per-beat body-lift and contact-shadow pulse so every friendly NPC visibly plants on the downbeat and rises between beats, including procedural-graphics fallbacks.
- Added regression coverage for the four-beat phase, beat accents, expanded waypoint distance, and dedicated runtime `dance` clip resolution.

### Changed

- Stationary friendly NPCs now use an explicit four-beat `dance` state with four authored frames per musical beat. Traveling NPCs retain their two-beat `run` loop so roaming steps do not slow down.
- Shopkeeper and Story Guest floor markers now pulse from the music transport rather than unrelated elapsed-time offsets, keeping every friendly actor on the same visible beat.
- Friendly NPC speed increased from `0.58` to `0.76` tiles per second. Shopkeeper, unresolved Story Guest, and decorative NPC roam radii increased to `2.5`, `3.4`, and `4.5` tiles respectively, and waypoint selection favors meaningful cross-room travel over short shuffles.
- NPCs now finish their selected route instead of replacing distant targets every four beats, then dance until a phrase boundary at least two beats after arrival. This preserves visible dance breaks even at the maximum procedural tempo.
- Shop signs now resolve the keeper assigned to their room, so trading remains reliable when the keeper roams beyond the old proximity fallback.
- Runtime/package release version is `4.1.12`. Run saves remain schema `5` and require no migration.

### Asset provenance

- MCP Shopkeeper character: `a5486d07-0778-4b91-b817-791696de463f`.
- MCP Story Guest character: `794acf2b-900e-461f-a81e-933bd9363134`.
- Shopkeeper `dance` prompt: “pronounced four-beat dark-fantasy tavern dance in place with clearly readable beat accents: beat one stomp and dip to the left, beat two rebound upright at center, beat three stomp and dip to the right, beat four rebound upright at center; large alternating side steps, deep knee bends, shoulder and forearm pumps, cloak and satchel bounce, feet stay grounded, seamless 16-frame loop; preserve the exact hooded shopkeeper identity, satchel, clothing, hands, feet and every body part, no added props”.
- Story Guest `dance` prompt: “pronounced four-beat occult court dance in place with clearly readable beat accents: beat one staff-side stomp and deep knee dip, beat two rebound upright at center, beat three opposite-side stomp and dip, beat four rebound upright at center; large alternating side steps, shoulder turns and cloak bounce, staff stays held and fully visible in every frame, feet stay grounded, seamless 16-frame loop; preserve the exact hooded story guest identity, staff, clothing, hands, feet and every body part, no magic effects”.

### Compatibility and resilience

- Existing sprite helper calls keep their prior `idle` defaults. The new keyword-only `dancing` flag selects `dance`, and missing modern dance frames still fall back to the established procedural idle animation.
- NPC movement targets, facing, beat phase, and dance state remain transient; public models and save serialization are unchanged.
- Player/enemy shadow behavior and the established `draw_shadow` API are unchanged; only friendly-NPC call sites pass the music-derived lift value.

### Validation

- Visually reviewed beat-labeled sheets for all eight directions and 16 frames per retained `dance` group, checking distinct downbeat poses, grounded movement, apparel, limbs, satchel, cloak, and staff retention; automated first/last seam measurements remained within the sequences' normal adjacent-motion range.
- MCP source-export gate — 256 new dance PNGs validated for exact paths/counts, `180×180` RGBA decoding, transparent margins, 16 unique frames per direction, and four distinct beat poses.
- Maximum-tempo simulation at 138 BPM confirmed completed routes and repeated dance breaks: minimum measured pauses exceeded two beats, with every friendly NPC type stationary for visible portions of the run.
- `.venv/bin/python -m unittest tests.test_sprite_assets` — 21 tests, all passing.
- `.venv/bin/python -m unittest tests.test_audio_music_timing tests.test_friendly_npcs tests.test_special_rooms tests.test_world_rendering_and_animation tests.test_save_and_metadata` — 33 tests, all passing.
- `.venv/bin/python -m compileall -q src tests` — OK.
- `.venv/bin/python -m unittest discover tests` — 233 tests, all passing.

## 4.1.11 — Beat-Synced Friendly NPC Dancing

Milestone 4.1.11 makes every friendly world NPC dance to the procedural soundtrack and roam within its assigned room, with authored MCP motion for shopkeepers, story guests, and the decorative bar/garden travelers that reuse Story Guest art.

### Added

- Added 256 reviewed `180×180` transparent MCP animation frames: eight-frame in-place dance and traveling dance-step loops in all eight directions for both `Shopkeeper` and `Story Guest`.
- Added a shared procedural-music track specification and virtual beat transport. Audible music follows a monotonic mixer-aligned clock; muted and headless runs use deterministic game time, and both expose loop beat, beat phase, and four-beat phrase timing.
- Added `FriendlyNpcRuntimeMixin`, which gives `Shopkeeper`, `StoryGuest`, and `IdleNpc` deterministic transient motion without changing their public models or consuming gameplay RNG.
- Added focused regression suites for music timing, clock-domain/downbeat synchronization, deterministic NPC motion, room containment after doors open, interaction holds, pause behavior, shared dance phase, and bounded transient state.

### Changed

- Friendly NPCs now select deterministic waypoints on four-beat phrase boundaries, travel with a restrained dance step, and play their in-place dance across a shared two-beat cycle.
- NPC movement is clamped to the original room interior even after a door opens, avoids walls, the player, other NPCs, live enemies, traps, shrines, secrets, quest/shop props, and cosmetic shop gold stacks, and pauses near interactive shopkeepers or unresolved story guests.
- Shopkeeper and Story Guest sprite helpers now accept backward-compatible keyword-only direction, movement, and normalized loop-progress inputs. Runtime `idle` maps to MCP `idle`; runtime `run` maps to MCP `walk`.
- Loop-progress addressing is isolated from the existing non-looping action-progress contract, so player dash and fallback action clips retain their prior time-based behavior.
- Shop gold-stack placement now excludes canonical special-room anchors rather than the shopkeeper's changing tile, keeping the cosmetic layout stable while the keeper moves; migrated index-only rooms fall back to their center and restored shop sign.
- Runtime/package release version is `4.1.11`. Run saves remain schema `5` and require no migration.

### Asset provenance

- MCP Shopkeeper character: `a5486d07-0778-4b91-b817-791696de463f`.
- MCP Story Guest character: `794acf2b-900e-461f-a81e-933bd9363134`.
- Shopkeeper `idle` prompt: “rhythmic dark-fantasy tavern dance in place, grounded two-beat step-touch with alternating foot taps, gentle shoulder bounce and restrained arm movement, seamless loop, preserve the satchel, hood, clothing and all body parts clearly visible”.
- Shopkeeper `walk` prompt: “moving forward with rhythmic dance steps, a grounded jaunty two-beat shuffle suitable for slow roaming, clear alternating footfalls and gentle shoulder bounce, seamless locomotion loop, preserve the satchel, hood, clothing and all body parts clearly visible”.
- Story Guest `idle` and `walk` use the matching occult-court variants, preserving the staff, hood, clothing, cloak motion, and all body parts.
- All four groups use direct one-to-one MCP-to-runtime direction mapping. Rate-limited split attempts were deleted in full; the retained service sources contain exactly one complete eight-direction `idle` group and one complete eight-direction `walk` group per exact character name.

### Compatibility and resilience

- Existing `Shopkeeper`, `StoryGuest`, and `IdleNpc` constructors and serialized fields are unchanged. Motion targets, facing, phrase state, and beat phase remain transient and are rebuilt after load or floor changes.
- Existing `SpriteAtlas.shopkeeper_visual`, `story_guest_visual`, `shopkeeper_frame`, and `story_guest_frame` calls remain valid through their original defaults.
- Explicit legacy graphics use the existing cached procedural idle/run frames with the same normalized beat phase. Missing individual modern frames still fall back through the established asset resolver.
- Music output availability changes presentation timing only; NPC route selection never consumes shared combat, loot, or dungeon RNG.

### Validation

- Visually reviewed labeled sheets for every direction and all eight frames in each retained group, checking grounded motion, facing continuity, transparent separation, and retention of weapons, apparel, limbs, and carried equipment.
- Automated asset checks cover exact frame counts and paths, `180×180` RGBA decoding, transparent margins, per-direction uniqueness, complete direction sets, normalized loop wrapping, and asset-backed facade resolution.
- MCP source-export gate — 256 animation PNGs validated across both actors.
- `.venv/bin/python -m unittest tests.test_sprite_assets` — 21 tests, all passing.
- `.venv/bin/python -m unittest tests.test_audio_music_timing tests.test_friendly_npcs tests.test_special_rooms tests.test_world_rendering_and_animation tests.test_save_and_metadata` — 29 tests, all passing.
- `.venv/bin/python -m compileall -q src tests` — OK.
- `.venv/bin/python -m unittest discover tests` — 229 tests, all passing.

## 4.1.10 — Aura-Free Arcanist Sprite Refresh

Milestone 4.1.10 replaces the playable Arcanist's previous sprite set with the finalized aura-free MCP redesign and its reviewed eight-direction idle and walking animations while preserving the existing gameplay and save contracts.

### Changed

- Replaced the Arcanist asset set with 90 new `196×196` transparent PNGs: eight base rotations, 32 four-frame idle frames, and 50 walk frames across all eight directions.
- Imported MCP's `walk` group as the established runtime `run` clip with a direct one-to-one direction mapping. Seven directions retain six frames; the approved south cycle retains all eight source frames.
- Updated Arcanist source normalization to anchor `(98, 147)` with a `97px` reference height while retaining the shared playable-character target height of `184px`.
- Updated sprite regression expectations for the source-authored eight-frame south cycle and the redesigned Arcanist's narrower north-facing lower-body silhouette. The existing runtime already resolves each direction using its own frame-list length, so no playback code change was required.
- Runtime/package release version is `4.1.10`. Run saves remain schema `5` and require no migration.

### Asset provenance

- MCP Arcanist character: `37842e46-0d8c-4084-b533-01185cbc3930`.
- The finalized character was rotated from the prior clean Arcanist reference with instructions to preserve the hooded blue-robed mage, ornate attached staff, and distinct 45-degree facings while excluding magical body auras, energy ribbons, orbiting effects, particles, and detached spell effects.
- The retained MCP source has one base character with the exact name `Arcanist`, no alternate character states, and exactly two complete animation groups: `idle` and `walk`.
- The game import preserves every approved source frame and contains no temporary review sheets or suffixed/test animation groups.

### Compatibility and resilience

- The `Arcanist` actor name, `arcanist` manifest slug, public sprite APIs, runtime `idle`/`run` state names, animation timing, package-data patterns, and procedural legacy fallback remain unchanged.
- Direction-local frame counts are supported by the existing resolver, which loops over the selected direction's own frame list. Other archetypes and their animation contracts are unchanged.
- Existing options and run saves require no migration because this update changes only presentation assets, manifest normalization, regression expectations, and release metadata.

### Validation

- Fresh MCP metadata confirmed the exact `Arcanist` name, all eight rotations, and only complete `idle` and `walk` groups in all eight directions.
- The import gate byte-verified all 90 packaged PNGs against their MCP sources and confirmed `196×196` 32-bit alpha decoding, unique images throughout each group, transparent canvas margins, exact direction sets, and the accepted 4/6/8 frame counts.
- `python -m unittest tests.test_sprite_assets tests.test_save_and_metadata` — 21 tests, all passing.
- `python -m compileall src tests` — OK.
- `python -m unittest discover tests` — 208 tests, all passing.

## 4.1.9 — Ranger Combat Animations

Milestone 4.1.9 completes the female spear Ranger's authored gameplay animation set with reviewed MCP strike and skill-casting clips while preserving the existing combat-state and save contracts.

### Added

- Added 96 packaged Ranger action frames: six-frame `hit` and `cast` sequences in all eight directions on the existing `256×256` transparent canvas.
- Added non-looping Ranger runtime `attack` and `cast` clips. The runtime `attack` clip reads from the reviewed MCP `hit` files so Hawk Slash uses the diagonal spear strike without introducing a new combat state.
- Added regression coverage for action folder/state wiring, all direction and frame counts, non-looping playback, unique RGBA frames, transparent margins, and first-to-last progress resolution.

### Changed

- Hawk Slash continues to emit the shared `attack` action state and now resolves the Ranger's authored `hit` frames. Multishot and the former Ranger class skill continue to emit `cast` and now resolve the authored free-hand casting gesture; Vault retains the shared movement/run treatment.
- Applied the established Ranger-only MCP→game direction map to both new groups: `north-west`→`north`, `north`→`north-east`, `west`→`north-west`, `south-west`→`west`, `north-east`→`east`, `south`→`south-west`, `south-east`→`south`, and `east`→`south-east`.
- Runtime/package release version is `4.1.9`. Run saves remain schema `5` and require no migration.

### Asset provenance

- MCP Ranger character: `2a6c4684-9821-4520-96b2-b0622bfb0d91`.
- Final `hit` prompt: “Raise the spear above one shoulder, lower its steel tip diagonally across the body, then return upright. Wooden butt stays down.”
- Final `cast` prompt: “Stand still, keep one spear upright in one hand, raise the open free hand chest-high, then lower it.”
- The current MCP source contains exactly four maintainable groups: `idle`, `walk`, `hit`, and `cast`, each complete in all eight directions.
- Multiple rejected `hit` groups containing magic trails, ambiguous double spearheads, or malformed follow-throughs were deleted in full before the approved import.

### Compatibility and resilience

- The shared `attack`/`cast` action states, `SpriteAtlas.player_visual` API, animation progress timing, Ranger name/slug, and public manifest format remain unchanged.
- Other archetypes retain their existing authored or fallback action visuals. Explicit legacy graphics continue to use the procedural Ranger and do not decode the new PNGs.
- Missing individual action resources continue to fall back through the existing per-frame asset resolution path without disabling the remaining asset library.

### Validation

- Fresh MCP export confirmed exactly four animation folders and 48 source frames in each new action group.
- The import gate byte-verified all 96 packaged files against their mapped MCP sources and confirmed `256×256` 8-bit RGBA decoding, six distinct frames per direction, and transparent canvas margins.
- `python -m unittest tests.test_sprite_assets tests.test_save_and_metadata` — 21 tests, all passing, including live Hawk Slash, Multishot, and the former Ranger class skill clip selection.
- `python -m compileall -q src tests` and `git diff --check` — OK.
- `python -m unittest discover tests` — 208 tests, all passing.

## 4.1.8 — Female Spear Ranger Sprite Refresh

Milestone 4.1.8 replaces the playable Ranger's bow-based sprite set with a completely new female MCP identity built around a single upright spear, while preserving the existing runtime animation and save contracts.

### Changed

- Replaced all 88 packaged Ranger PNGs with eight new base rotations, 32 reviewed four-frame idle frames, and 48 reviewed six-frame V3 walk frames on a `256×256` transparent canvas.
- The existing runtime `run` clip now presents the approved MCP walk cycle, preserving player-state, rendering, fallback, and package-data interfaces without introducing a Ranger-only animation state.
- Applied the reviewed Ranger-specific MCP→game direction map consistently to rotations, idle frames, and walk→run frames: `north-west`→`north`, `north`→`north-east`, `west`→`north-west`, `south-west`→`west`, `north-east`→`east`, `south`→`south-west`, `south-east`→`south`, and `east`→`south-east`. Other actors retain their existing mappings.
- Updated Ranger source normalization to anchor `(128, 212)` with a `165px` reference height while retaining the shared playable-character target height of `184px`.
- Ranger previews on both modern and legacy archetype-selection screens now use the `south-west` idle animation; the other archetypes retain their established `south` previews.
- Runtime/package release version is `4.1.8`. Run saves remain schema `5` and require no migration.

### Asset provenance

- MCP Ranger character: `2a6c4684-9821-4520-96b2-b0622bfb0d91`.
- Source prompt: “Female forest spearmaiden, auburn braid, dark-green leather armor, short cloak. Only weapon: one tall upright spear held beside her, with one straight continuous wooden shaft. Completely bare back and belt.”
- The retained MCP source contains exactly two animation groups: `idle` with four frames in all eight directions and `walk` with six frames in all eight directions.
- Rejected bow/quiver identities, malformed spear rotations, split animation groups, and the identity-breaking template walk were deleted from MCP before the final import.

### Compatibility and resilience

- The `Ranger` actor name, manifest slug, `idle`/`run` clip names, public sprite APIs, animation timing, and independent per-frame fallback behavior remain unchanged.
- Explicit legacy graphics continue to use the procedural Ranger and do not decode the replacement PNGs.
- Existing options and run saves require no migration because this update changes only presentation assets and release metadata.

### Validation

- Final import gate byte-verified all 88 packaged PNGs against their corrected mapped MCP sources and confirmed `256×256` RGBA decoding with transparent margins.
- `python -m unittest tests.test_sprite_assets` — 17 tests, all passing; includes complete direction/frame counts, PNG decoding, pose uniqueness, lower-body motion, Ranger normalization, transparent margins, and runtime resolution.
- Save/release metadata, movement-animation, and archetype/options suites — 9 tests, all passing.
- `python -m unittest tests.test_ui_layouts` — 17 tests, all passing; covers modern and legacy Ranger `south-west` idle selection previews and anchored animation.
- `python -m compileall -q src tests` and `git diff --check` — OK.
- `python -m unittest discover tests` — 206 tests, all passing.

## 4.1.7 — Female Rogue Sprite Refresh

Milestone 4.1.7 replaces the playable Rogue's previous male sprite set with a completely new female MCP identity and reviewed high-resolution locomotion while preserving the existing runtime animation contract.

### Changed

- Replaced all 88 packaged Rogue PNGs with eight new base rotations, 32 reviewed four-frame breathing-idle frames, and 48 reviewed six-frame V3 walk frames on a `244×244` transparent canvas.
- The existing runtime `run` clip now presents the approved walk cycle, preserving player-state, rendering, fallback, and package-data interfaces without introducing a Rogue-only animation state.
- Imported every Rogue rotation and animation with a direct one-to-one direction mapping (`north`→`north`, `south-east`→`south-east`, and so on); no character-specific remapping is applied.
- Updated Rogue source normalization to anchor `(122, 183)` with a `122px` reference height while retaining the shared playable-character target height of `184px`.
- Runtime/package release version is `4.1.7`. Options remain schema `4`; run saves remain schema `5` and require no migration.

### Asset provenance

- MCP Rogue character: `d6f3357f-e41d-4181-8a14-1deaef8e1bdd`.
- Source prompt: “Athletic female rogue, braided black hair, charcoal leather armor, muted green scarf, two short-bladed daggers.”
- Idle and walk frames were reviewed and adjusted in MCP before the final package export used by the game.

### Compatibility and resilience

- The `Rogue` actor name, manifest slug, `idle`/`run` clip names, public sprite APIs, animation timing, and independent per-frame fallback behavior remain unchanged.
- Explicit legacy graphics continue to use the procedural Rogue and do not decode the replacement PNGs.
- Existing saves require no migration because this update changes only presentation assets and release metadata.

### Validation

- `python -m unittest tests.test_sprite_assets` — 16 tests, all passing; includes complete direction/frame counts, PNG decoding, pose uniqueness, canonical canvas checks, transparent margins, and runtime resolution.
- Save/release metadata plus movement-animation and archetype/options suites — 9 tests, all passing.
- Headless modern-mode Rogue render smoke check resolved grounded asset-backed idle and movement frames.
- Final export gate byte-verified all 88 packaged PNGs against the reviewed MCP archive using identical source and destination direction names.
- `python -m compileall -q src tests` and scoped `git diff --check` — OK.
- `python -m unittest discover tests` — 204 tests, all passing.

## 4.1.6 — Archetype Selection Polish

Milestone 4.1.6 tightens the authored archetype-selection composition, restores a genuinely live idle preview while the game is in menu states, and gives every class statistic a compact framed card without adding another visual asset dependency.

### Changed

- The modern archetype container is exactly 20% smaller on both axes and remains centered on its previous footprint. Its title and keyboard guidance move down by the reclaimed top inset, while the selected-number shortcut stays attached beneath the panel and moves up by the reclaimed bottom inset.
- The selector recomputes its class list, preview, description, and statistics from the compact panel's authored safe area. Wide previews use four stat columns and compact previews use three or two as space requires.
- HP, Mana, Stamina, Speed, Melee, Spell, and DR now render in individual Obsidian-framed cards using the existing cached `hud.bar` nine-slice, with restrained per-stat color accents and a procedural fallback when that optional resource is unavailable.
- A UI-only animation clock now advances in every app state. Modern and legacy archetype previews use it for their south-facing idle animation without adding menu time to serialized run duration.
- Outer-panel safe-area lookup now follows the exact wide or compact frame selected for rendering.
- Runtime/package release version is `4.1.6`. Options remain schema `4`; run saves remain schema `5` and require no migration.

### Compatibility and resilience

- Explicit legacy graphics retain the previous selector geometry and procedural chrome; only the previously static preview now advances its existing idle frames.
- Missing `hud.bar` art restores compact procedural stat cards without disabling the rest of the authored selector.
- The UI animation clock is transient and is neither serialized nor used for gameplay simulation, cooldowns, or run statistics.

### Validation

- Manual modern visual checks covered `960×540` and `640×480`, including two idle phases, compact card legibility, and complete containment.
- Focused UI refinement, asset sprite/UI, movement-animation, and archetype/options suites — 43 tests, all passing.
- `python -m compileall -q src tests` and `git diff --check` — OK.
- `python -m unittest discover tests` — 216 tests, all passing.

## 4.1.5 — Obsidian Resource HUD

Milestone 4.1.5 replaces the undersized modern HP, Mana, and Stamina treatment with the selected Obsidian frame and gives the lower HUD enough space for those resources to read clearly during combat. The authored layout grows only in modern graphics mode; the procedural legacy HUD retains its previous dimensions and rendering.

### Added

- A generated `474×66` Obsidian resource-bar source with a clean charcoal trough, restrained iron bevel, and thin warm-metal edge, packaged under the existing `hud.bar` key.
- Geometry regressions for the approved `960×540` composition, compact bar containment, modern-versus-legacy sizing, generated source dimensions, nine-slice safe content, and combined story-panel/interaction-prompt placement.
- Runtime geometry probes for the three resource bars through `_hud_resource_bar_rects`, matching the existing HUD layout diagnostics pattern.

### Changed

- The normal modern lower slab is `84px` tall at `960×540`—25% shorter than the initially approved `112px` composition—while retaining the `322px` resource card and three readable `260×14px` status bars. The original pre-Obsidian layout used a roughly `60px` slab, `190px` resource card, and `170×10px` bars.
- Modern compact layouts rebalance the three lower cards rather than forcing the normal widths: at `640×480` the slab remains `84px` with a `215px` resource card and `153×14px` bars; at `640×360` it compresses to `79px` with contained `153×13px` bars.
- Resource fills retain their live red, blue, and gold gradients while gaining a quiet top sheen. Labels use the larger small font whenever bar height permits and add a one-pixel shadow for contrast.
- The action dock shifts only as far as the condensed slab requires and trims to `56px` at normal scale, preserving its controls, cooldowns, counts, and authored assets while returning more vertical space to the dungeon view.
- Story information now yields vertical space to an active interaction prompt when their horizontal spans intersect. Compact windows temporarily hide the story card when both overlays cannot fit, preventing the later-drawn story panel from obscuring interaction guidance.
- Runtime/package release version is `4.1.5`. Options remain schema `4`; run saves remain schema `5` and require no migration.

### Asset provenance

- MCP Obsidian resource bar: `a7dc111c-69f9-4489-a45a-2c74ea89cee2`.
- The generated `512×192` authoring canvas was losslessly trimmed to its `474×66` non-transparent bounds. It contains no baked labels, resource colors, values, or gameplay state; all fills and text remain dynamic.

### Compatibility and resilience

- Explicit legacy graphics keep the prior HUD reserve, card widths, procedural resource bars, action-dock placement, and visual output.
- Missing or invalid `hud.bar` art continues to restore the procedural bar renderer without affecting the fitted UI-scale context or other HUD assets.
- HUD panel/bar transforms remain cached after the first render; the larger layout adds no warm-cache rebuilds or source decodes.

### Validation

- Manual modern runtime renders covered `960×540`, `640×480`, and `640×360`; a `960×540` legacy render confirmed the prior procedural composition.
- Focused asset UI, UI refinement, action-bar, and inventory/HUD suites — 21 tests, all passing.
- `python -m compileall -q src tests` and `git diff --check` — OK.
- `python -m unittest discover tests` — 212 tests, all passing.

## 4.1.4 — Character and Inventory Panel Polish

Milestone 4.1.4 tightens the two most information-dense in-run overlays. Modern Character and Inventory views now use smaller centered shells with authored inner frames around related content, preserving more of the dungeon backdrop while making each information group read as a deliberate card instead of floating text.

### Added

- A generated thin inset-panel sprite at `assets/sprites/menus/panel_inset.png`, exposed as the nine-slice `menu.panel.inset` resource with explicit safe-content metadata.
- A shared inset-panel primitive that returns the exact authored safe area used for layout and independently falls back to a restrained procedural frame when the optional resource is missing.
- Geometry and content regressions for smaller overlay bounds, nested panel containment, all inventory controls, visible-row clipping, all character skills/equipment, compact discipline cells, and responsive transitions at heights `419`, `420`, `439`, and `440`.

### Changed

- Modern Character and Inventory overlays use centered shells around 88% of the viewport at normal window heights instead of stretching almost edge-to-edge.
- Short-wide windows use a slightly narrower, nearly full-height shell and a dedicated compact composition so `640×360` retains usable content without returning to the oversized normal layout.
- Character Overview wraps statistics, skills, equipment, upgrades, and status/proc content in authored inset frames. The compact layout places the four cards in one row and abbreviates resource costs to keep every ability visible.
- Character Disciplines wraps the complete tree in one authored inset frame. Cells too short for both title and description now intentionally show a centered name only rather than drawing overlapping description text.
- Inventory wraps sort controls, carried items, selected-item details, equipment, and shortcut controls in authored inset frames. Compact layouts retain one fully contained item row, selected-item guidance, both equipment lines, and all eight shortcuts.
- Nested content is positioned from authored safe insets, inventory rows are clipped to their viewport, and shared text clipping now intersects any active parent clip instead of escaping it.
- Outer-panel selection and safe-area lookup use the same resource order, so a missing or metadata-incomplete compact frame consistently falls back to the wide frame before procedural rendering.
- Runtime/package release version is `4.1.4`. Options remain schema `4`; run saves remain schema `5` and require no migration.

### Asset provenance

- MCP inset panel source: `24c53c30-8cf4-43ee-a010-05fda73ce4ab`.
- The generated `256×256` authoring canvas was losslessly trimmed to its `161×81` non-transparent bounds. The packaged frame contains no baked labels, dividers, or gameplay values and is stretched only through nine-slicing.

### Compatibility and resilience

- Explicit legacy Character and Inventory views retain their prior procedural geometry and chrome; captured `960×540` before/after renders were byte-identical.
- Missing `menu.panel.inset` art restores procedural nested frames without disabling other authored UI. Missing compact art or safe metadata falls back to `menu.panel` with matching content insets.
- Existing `Game`, `MenuRenderer`, `UiAssetLibrary`, input, save, and graphics-option interfaces remain compatible.

### Validation

- Manual modern visual matrix covered Character Overview, Character Disciplines, and Inventory at `960×540`, `640×480`, and `640×360` with saved UI scale `4`; responsive breakpoint probes covered heights `419`, `420`, `439`, and `440`.
- Focused asset UI, UI refinement, inventory, and skill-menu suites — 20 tests, all passing.
- `python -m compileall -q src tests` and `git diff --check` — OK.
- `python -m unittest discover tests` — 210 tests, all passing.

## 4.1.3 — Menu Navigation and Header Refinement

Milestone 4.1.3 moves modern menu shortcuts out of decorative row endcaps, gives status values enough room to render in full, and rebalances authored-background headers. The changes are layout-only: controls/binding tables and procedural legacy menus keep their established inline-key presentation.

### Added

- A dedicated bottom shortcut strip that follows the selected title, options, exit, or archetype item without repeating every hotkey inside the navigation rows.
- Geometry regressions at `960×540` and `640×480` for empty modern key endcaps, selected shortcut strips, full difficulty status width, left-shifted status placement, header spacing, and legacy inline-key preservation.

### Changed

- Modern navigation rows leave their stone endcaps as ornament and use the central field for labels and status values. Statuses such as `Hard · Hell locked`, controller state, and graphics mode now render in a wider column shifted away from the right edge.
- Title, options, exit, and archetype menus show the selected item's shortcut in a quiet bottom section with an accent marker and separator rule.
- Authored-background headers no longer receive the procedural gold rule/crest that crossed subtitles. Titles are positioned slightly lower, subtitle spacing is increased, and panel tops move down while panel bottoms remain stable.
- Compact options omit the explanatory difficulty paragraph when necessary, preserving readable rows and the new shortcut section; scrolling still keeps the selected setting visible.
- Archetype class rows no longer repeat `1–5` inline. The selected class shortcut appears beneath the shortened panel, while the animated centered preview and larger typography remain unchanged.
- Runtime/package release version is `4.1.3`. Options remain schema `4`; run saves remain schema `5` and require no migration.

### Compatibility and resilience

- Explicit legacy graphics retain the prior title ornament, inline row hotkeys, status endcaps, menu metrics, and procedural panel layout.
- Keyboard/mouse and gamepad binding tables continue to show their keys and mappings inline because those values are primary content rather than menu-item shortcuts.
- Missing authored row resources continue to use the procedural row fallback while preserving the modern bottom-shortcut layout.

### Validation

- Manual modern visual matrix at `960×540` and `640×480` covered title, options, and archetype selection with full status strings and non-overlapping headers.
- Focused menu, asset UI, options, pause, and skill-menu suites — 22 tests, all passing.

## 4.1.2 — Cutscene and Archetype UI Polish

Milestone 4.1.2 finishes the post-asset menu pass with purpose-sized panel art, a cinematic cutscene backdrop, and a rebuilt archetype selector. Modern mode gains the new visuals and responsive geometry while procedural legacy graphics remain unchanged and continue to act as the per-resource fallback.

### Added

- A generated `688×384` catacomb cutscene backdrop, rendered behind a readability wash instead of the previous fullscreen black clear.
- Generated wide and compact menu-panel sources with thin, symmetric borders, clean dark content fields, and aspect-aware selection for compact layouts.
- Layout regressions covering the smaller archetype panel, centered south-facing animated preview, panel-variant selection, modern cutscene background, stage/narrator/choice containment, and legacy cutscene fallback.

### Changed

- Archetype selection uses a slightly smaller container, a wider right-side preview region, larger class/skill/description typography, and three-column compact statistics so labels remain readable.
- The selected archetype now advances its authored south-facing idle clip through `SpriteAtlas.player_frame()` rather than displaying a static frame-zero surface; procedural sprites remain the automatic fallback.
- The character sprite is centered in the full right-side preview, with description and statistics flowing below it instead of squeezing the figure into a narrow left subcolumn.
- The generated panel sources replace the previous oversized asymmetric frame. Runtime nine-slicing now preserves approximately `18–21 px` borders and `22–24 px` safe-content gutters rather than the former `80–96 px` chrome.
- Cutscene shells use the new panel variants and leave visible screen margins for the backdrop. Stage height is chosen only after reserving header, two narration lines, choices, and footer space.
- Cutscene stage drawing is clipped to its stage rectangle, preventing minimum-size pillars, banners, and curtains from intruding into the header on compact windows.
- Runtime/package release version is `4.1.2`. Options remain schema `4`; run saves remain schema `5` and require no migration.

### Asset provenance

- MCP wide menu panel: `3c165843-c97c-42bf-8ef5-2f830e2dced0`.
- MCP compact menu panel: `4e97ce8d-499e-42bd-bbe9-cff3cda2fbe8`.
- MCP cutscene catacomb backdrop: `c38a07cc-4432-4803-88d0-421177ee4add`.
- Transparent authoring margins were trimmed, panel center fields were deterministically normalized for text readability, and the generated square backdrop was nearest-neighbor fitted to the packaged `688×384` cinematic canvas.

### Compatibility and resilience

- Explicit legacy graphics still bypass every authored menu and cutscene resource, preserving the procedural selector and black-backed procedural cutscene shell.
- A missing compact panel falls back to the wide generated panel; unavailable panel/background resources independently restore procedural rendering without disabling unrelated UI assets.
- Existing `Game`, `MenuRenderer`, `RenderingMixin`, save, input, and graphics-option interfaces remain compatible.

### Validation

- Manual modern visual checks at `960×540` and `640×480` covered the archetype selector at two idle phases and revealed-choice cutscenes; text, panels, sprites, narration, choices, and footers remained contained.
- Focused asset UI, refinement, and cutscene suites — 15 tests, all passing.
- `python -m compileall -q src tests` and `git diff --check` — OK.
- `python -m unittest discover tests` — 207 tests, all passing; no experimental web tests are present in the discovered suite.
- Built `arch_rogue-4.1.2-py3-none-any.whl`; the wheel contains both panel variants, `background_cutscene.png`, and the updated UI manifest.

## 4.1.1 — Authored Menu and HUD Refinement

Milestone 4.1.1 removes the remaining procedural chrome that was being painted over the 4.1 authored interface, moves live content into explicit sprite-safe regions, and makes high accessibility scales fit compact windows without changing the saved UI-scale preference. The procedural renderer remains available as the complete legacy mode and as an independent fallback for any missing UI resource.

### Added

- Optional `content_insets` metadata for authored menu panels, menu rows, HUD panels, action slots, and resource bars.
- `UiAssetLibrary.content_rect()`, which validates resource availability and maps authored safe-content insets into normal and proportionally compressed nine-slice targets.
- A modern-only fitted-layout context that temporarily substitutes physically appropriate fonts and spacing for complex screens while preserving the configured `ui_scale` and restoring all font objects after rendering.
- Focused 4.1.1 regressions for content-inset validation, tiny-target fitting, asset-pure panel/row rendering, selected-row visibility, independent resource fallback, compact layout containment, fitted-scale restoration, and complete 24-stat death/victory summaries.

### Changed

- Authored menu panels, HUD panels, menu rows, and action slots now supply their complete static chrome. The renderer no longer layers legacy outlines, bevel highlights, parchment header rules, action-slot shine, or three-layer hotkey plates over those sprites.
- Authored menu backgrounds retain their low-alpha thematic wash but no longer receive an extra procedural edge frame.
- Modern menu rows place key and value text directly in the authored endcaps. Targets too narrow to preserve those endcaps use a flat compact row while retaining selection glow and the inset selection marker.
- Title flavor text now has reserved space below its navigation rows and uses a quiet borderless wash in modern mode.
- Archetype selection now uses one full authored panel, splits its safe center into class and preview regions, allows character previews to scale below `1×`, and uses flat modern stat groups instead of nested procedural panels and plaques.
- Inventory, character, help, shop, cutscene, death, and victory overlays now derive layout from authored safe centers. Modern inventory and character subgroups shed static borders while preserving selection, rarity, active sort/tab, scrollbar, equipment, and discipline-state cues.
- Death and victory summaries render all 24 run statistics as two compact 12-row groups in modern mode; the legacy single-column table is unchanged.
- The HUD now keeps resource bars, run headers, story text, interaction prompts, lower cards, and cutscene narration inside authored boundaries. Action-slot cooldowns, counts, disabled states, glyphs, labels, hotkeys, and readiness remain dynamic.
- Complex modern screens and the HUD fit `640×480` at configured UI scale `4` using an effective physical scale without mutating options. Legacy rendering retains its original scale and geometry.
- Runtime/package release version is `4.1.1`. Options remain schema `4`; run saves remain schema `5` and require no migration.

### Compatibility and resilience

- Explicit legacy graphics preserve the previous procedural backdrop, panel, row, stat-card, inventory, character, state-overlay, and HUD implementations.
- Asset decisions remain per resource: a missing `menu.panel`, `menu.row`, `hud.panel`, action slot, or bar restores that component's procedural renderer and geometry without disabling unrelated UI sprites.
- Existing `Game`, `MenuRenderer`, `RenderingMixin`, save, input, and graphics-option interfaces remain compatible.

### Validation

- Manual modern/legacy visual matrices at `960×540` covered title, options, controls, archetype selection, about, help, inventory, character overview/disciplines, death, victory, and the in-run HUD. Compact modern renders covered archetype selection, inventory, and HUD at `640×480` with UI scales `1` and `4`.
- `python -m compileall src tests` and `git diff --check` — OK.
- Focused UI, HUD, inventory, sprite, save, story, summon, lighting, and class-skill gate — 90 tests, all passing.
- `python -m unittest discover tests` — 205 tests, all passing.
- Wheel build — `arch_rogue-4.1.1-py3-none-any.whl`, 2,280 entries; all eight UI PNGs, `ui_manifest.json`, `ui_assets.py`, package version metadata, and five `content_insets` entries are present.
- Warm `960×540` HUD-only benchmark — `0.323 ms/frame` over 240 frames (about 3,101 HUD passes/s), with render builds fixed at `8`, source decodes fixed at `4`, and no transformed/source cache growth.

## 4.1.0 — Asset-Backed Menus and HUD

Milestone 4.1 replaces the modern-mode menu and HUD chrome with a cohesive generated pixel-art interface while preserving the complete procedural presentation behind the existing Display → Graphics toggle. Dynamic text, selection state, cooldowns, resource fills, controller mappings, story data, and run statistics remain runtime-rendered so the new art stays readable and responsive across resolutions.

### Added

- Eight packaged UI PNGs under `assets/sprites/menus/` and `assets/sprites/hud/`: distinct dungeon-gate and occult-crypt menu backdrops, a carved modal panel, a compact row plate, a five-bay action dock, action-slot frame, status-bar frame, and shallow HUD panel frame.
- `ui_manifest.json` with stable logical keys, render modes, and nine-slice insets for menu backgrounds, panels, rows, HUD cards, action slots, docks, and resource bars.
- `UiAssetLibrary`, an optional package-resource loader with safe manifest/path validation, full-canvas PNG decoding, cover/scale/nine-slice rendering, bounded LRU caches, negative caching, best-effort display conversion, and independent per-resource failure containment.
- Focused milestone regressions for packaged asset coverage, malformed manifests, missing-resource isolation, tiny-target nine-slicing, modern/legacy switching, warm-cache stability, compact options scrolling, and complete controls-row containment.

### Changed

- Shared `MenuBaseMixin` backdrop, panel, and row primitives now resolve authored art in modern mode, so title, options, controls, archetype selection, about/help, character, inventory, death, and victory screens inherit the new skin without duplicating navigation or layout logic.
- Title menus use a dungeon-gate background while other full-screen menus use the occult crypt frame. Generated panel and row interiors were normalized after generation to retain decorative borders without placing ornament behind live text.
- Shared HUD panel rendering now skins the lower dock cards, run header, interaction prompt, story panel, shop, and story cards; resource bars and action slots use dedicated authored sprites while all fill ratios, glyphs, hotkeys, counts, cooldown arcs, and disabled overlays remain dynamic.
- The authored action dock is sized around the actual six-slot cluster instead of stretching across the viewport, and all transformed static surfaces are reused after their first render.
- Controls typography and row metrics now fit the available physical column height. All 15 keyboard references and every remappable gamepad command remain visible at both `960×540` and the `640×480` / UI-scale-4 stress case.
- High UI scales on compact windows use tighter title/subtitle budgets, increasing usable menu-panel height while preserving the requested accessibility scale where it physically fits.
- Runtime graphics-mode changes clear only derived UI/HUD caches; decoded sources remain reusable when switching back to asset graphics.
- Package data now explicitly includes `assets/sprites/menus/*.png` and `assets/sprites/hud/*.png`.
- Runtime/package release version is `4.1.0`. Options remain schema `4`; run saves remain schema `5` and require no migration.

### Compatibility and resilience

- Explicit legacy graphics bypass all milestone-4.1 PNGs and retains the prior procedural stone backdrops, panels, menu rows, HUD cards, bars, action plates, and fallback title crest.
- A missing, corrupt, unsafe, or unsupported UI resource falls back only that component to its procedural renderer; UI-manifest failure does not disable actor, item, prop, or world assets.
- Existing `MenuRenderer`, `RenderingMixin`, `Game`, save, input, and graphics-option public behavior remains compatible.
- UI art contains no baked labels or gameplay values, so localization-sized strings, remapped controller values, item names, and generated story content still use the existing clipping and wrapping rules.

### Asset provenance

- Final MCP source jobs: title backdrop `1e6fb7a2-8e39-4ae5-b414-adb10b36be6f`, menu backdrop `d26c22d1-87fb-44d0-8956-2051bf36ae30`, modal panel `8087840a-d4c9-47d5-966a-8f77c0547f8d`, row plate `a21b2178-8a38-4ab3-a77d-b5160c756efa`, HUD dock `344de9a4-e3be-4927-a081-317ede03f9fb`, action slot `21cf97fc-1e8a-4f03-90fd-87dfa04a467f`, and status bar `a280b2de-396a-4778-81af-b365a486cad4`.
- Runtime files are losslessly trimmed from transparent source margins. The panel/row center fields and shallow HUD panel derivative are deterministic curation steps that preserve generated borders while removing decorative interference from live text.

### Validation

- Manual visual matrix at `960×540` covered title, options, controls, archetype selection, about, help, inventory, character, death, victory, and the in-run HUD in modern mode, with direct modern/legacy comparisons for title and HUD.
- Compact visual/layout gate at `640×480` and UI scale `4` kept the selected options row inside its viewport and rendered all 15 keyboard references plus every remappable gamepad command without overlap.
- `python -m compileall src tests` — OK.
- `python -m unittest tests.test_4_1_asset_ui` — 4 tests, all passing.
- `python -m unittest discover tests` — 199 tests, all passing; the prior environment-dependent inventory containment failure is eliminated by preventing headless tests/tools from inheriting the developer's home-directory options before installing an isolated path.
- Direct `setuptools.build_meta` wheel build — `arch_rogue-4.1.0-py3-none-any.whl`, 2,280 files; all eight UI PNGs, `ui_manifest.json`, and `ui_assets.py` are present.
- Warm `960×540` HUD-only benchmark — `0.343 ms/frame` over 120 frames (about 2,919 HUD passes/s), with render builds fixed at `8`, source decodes fixed at `4`, and no transformed/source cache growth.

## 4.0.2 — Archetype Animation Repairs

Milestone 4.0.2 audits the complete modern idle/run set for all five playable archetypes and replaces clips with static locomotion, unstable facing, missing equipment or apparel, extra anatomy, and frame-to-frame gear flicker. The repaired sources retain their existing high-resolution canvases and runtime anchors, so the update is asset-only apart from manifest coverage and validation.

### Acolyte full-regeneration follow-up

- Replaced all 88 Acolyte PNGs with one new MCP V3 identity (`aa6961b2-9dca-43a9-b68b-6cfdfaa8ee17`): eight base rotations, 32 idle frames, and 48 walk frames on a `244×244` high-resolution canvas.
- Imported every rotation and animation through the required MCP-to-game direction mapping: south-east→south, south→south-west, north-east→east, east→south-east, north-west→north, north→north-east, south-west→west, and west→north-west.
- Removed the previous mirrored side/rear-diagonal frames and duplicated walk contact holds; every game direction now uses its independently generated four-frame idle and six-frame walk source.
- Updated the Acolyte source anchor/reference geometry while preserving the runtime target height, asset-first loading, and legacy procedural fallback.

### Repaired assets

- Replaced 152 packaged PNGs: 148 frames across 27 repaired clips (seven idle and twenty run clips), plus corrected Ranger north-west and Acolyte east/north-west/west rotations.
- Warden: repaired north-east/south-east idle and south/north-east/north-west run clips, restoring southward leg motion and keeping the shield and cape stable on both rear diagonals.
- Ranger: repaired north-west rotation/idle and north/north-east/north-west run clips, keeping the cape, bow, and quiver on the correct side without flicker or a missing north-west stride.
- Arcanist: repaired south/east/north/north-west/south-west run clips, adding visible northward leg motion while preserving the staff and removing the intermittent extra hand.
- Rogue: repaired north and north-east run clips after the full-roster audit found weak locomotion and unstable blade silhouettes.
- Acolyte: repaired east/north-east/north-west/west idle, south/south-east/east/north-east/north/north-west/west run, and the east/north-west/west fallback rotations. The final set keeps the complete red-orb staff present, removes front/back cape duplication, stabilizes the free hand, and replaces the wobbly north/south gait with clear alternating steps.
- Repairs use reviewed V3, template, and Pro-generated source clips. The Pro east idle/run art is losslessly root-aligned, with the four clean Pro gait poses retained in the existing six-frame run through deliberate contact holds; deterministic mirrors preserve accepted north-east/north-west and east/west equipment silhouettes.

### Changed

- Ranger's run manifest now explicitly includes all six north-west frames instead of falling back to a static rotation at runtime.
- Acolyte east/west rotations and idle clips now use matching Pro side-profile art, with west mirrored from east so state changes preserve scale, staff placement, and cape construction.
- Acolyte north-west rotation/idle/run now mirror the accepted north-east art, preventing the occluded source set from reducing the staff to a floating orb through runtime fallback.
- Added full player-asset regressions covering all five archetypes, all eight directions, exact four-frame idle/six-frame run clips, decodable frames with expected pose uniqueness, canonical source canvases, nonblank alpha bounds, and transparent edit margins.
- Added focused regressions for lower-body silhouette motion in the previously static or unstable walks, plus Acolyte east/west and north-east/north-west mirror parity, exact Pro contact-hold cadence, side rotation/idle parity, root stability, and north-east idle staff width/stability.
- Runtime/package release version is `4.0.2`. Options remain schema `4`; run saves remain schema `5` and require no migration.

### Compatibility and resilience

- Public sprite APIs, actor names, source canvases, anchors, timing, and independent per-resource fallback behavior are unchanged.
- Explicit legacy graphics continue to use the procedural archetype renderer and do not load these replacement PNGs.
- Missing or corrupt modern frames still fall back independently through the existing static-rotation/procedural paths.

### Validation

- Reviewed final contact sheets for every repaired clip for direction stability, stride motion, continuous weapons/shields/cloaks, anatomy, and image artifacts.
- Staging/package gate — exactly 152 intended PNGs; all destination paths and canvas sizes match, all frames decode and remain nonblank, pose uniqueness matches each reviewed cadence, every frame has transparent margins, and installed files byte-match the reviewed set.
- `python -m compileall src tests` — OK.
- `python -m unittest tests.test_4_0_asset_sprites` — 17 tests, all passing.
- `python -m unittest discover tests` — 196 tests run; 195 pass and the pre-existing unrelated inventory-HUD containment failure (`test_inventory_hud_layout_navigation_sorting_and_cues`) remains unchanged.
- Prior build-isolated wheel validation — `arch_rogue-4.0.2-py3-none-any.whl` contains all 2,207 sprite PNGs, the manifest, and the corrected archetype resources; local wheel revalidation requires the unavailable `setuptools.build_meta` backend.

## 4.0.1 — Post Sprite Generation Fixes

Milestone 4.0.1 refines the asset-backed dungeon set without changing gameplay or abandoning the procedural renderer. Doors now remain recognizable from both sides on every room boundary, special rooms use authored wall faces instead of procedural marks painted over masonry, and shop gold uses five complete unclipped silhouettes.

### Added

- Sixteen new packaged PNG resources: a regenerated seamless base wall, closed/open doorway art for both visible isometric wall planes, six face-specific quest/bar/garden walls, and five distinct gold-stack variants.
- Sixteen logical directional door entries (`open`/`closed` × eight compass directions). Opposite directions share an authored door-bearing plane, so approaching a closed door from its reverse side can no longer turn it into solid masonry; corner directions also resolve only to door-visible art.
- `reference_width` support in world-sprite manifest entries, allowing transparent source canvases to retain generous edit margins while scaling the authored one-tile wall footprint exactly to the canonical `320 px` isometric tile width.
- Focused regressions for eight-way room-boundary inference, boss-seal directions, opposite-side door visibility, per-resource door/wall fallbacks, special-wall overlay removal, deterministic gold variation, unclipped/distinct gold assets, partial actor clips, canonical canvases, and bounded legacy door caches.

### Changed

- Door rendering derives north, south, east, west, and corner directions from room perimeter geometry without persisting orientation in run saves. Missing directional resources still fall back independently to the 4.0 generic/procedural door path.
- Dedicated quest-room rune stone, tavern wood panel, and garden moss/vine walls replace the glitch-prone modern path that composited procedural decorations over the generic authored wall. The old compositor remains a resource-level fallback for incomplete installations.
- Shop-floor gold placement now assigns one of five authored variants with a salted local RNG. Existing stack positions and size tiers are unchanged, gameplay RNG is untouched, and the decorative piles remain outside item/pickup/save state.
- Partial actor animation direction maps are now valid: a deliberately omitted or missing clip direction falls back to that direction's static rotation instead of disabling the complete asset library or borrowing a wrongly facing animation.
- Door cache keys collapse opposite logical directions onto the two visible isometric wall planes in both renderers, avoiding duplicate high-resolution surfaces while modern mode still exposes all eight authored direction keys.
- Runtime/package release version is `4.0.1`. Options remain schema `4`; run saves remain schema `5` and require no migration.

### Compatibility and resilience

- Explicit legacy graphics still use the original procedural walls, doors, and three gold size tiers.
- The generic 4.0 door and procedural special-wall decoration paths remain available per resource; one missing/corrupt 4.0.1 PNG cannot disable unrelated modern assets.
- Existing 4.0.0 saves regenerate cosmetic door direction and gold variants from already-saved dungeon geometry, with no new serialized fields.

### Validation

- `python -m compileall src tests` — OK.
- Focused asset/world/special-room/boss/version regression run — 100 tests, all passing.
- `python -m unittest discover tests` — 193 tests run; 192 pass and the pre-existing unrelated inventory-HUD containment failure (`test_inventory_hud_layout_navigation_sorting_and_cues`) remains unchanged.
- Isolated wheel build through `setuptools.build_meta` — `arch_rogue-4.0.1-py3-none-any.whl` contains all 16 new PNGs, 2,208 sprite resources total, 12 prop entries, and 31 world entries.
- Warm-cache 960×540 dummy-SDL benchmark — 4.26 ms/frame (234.7 FPS); tile, door, decoded-source, resolved-frame, world-surface, and normal-map cache counts stayed unchanged over 120 frames, with the modern door cache reduced from 64 to 16 surfaces.

## 4.0.0 — Big Sprites Upgrade

Arch Rogue now ships with a production asset-sprite renderer while preserving the complete procedural renderer as an instant legacy fallback. The upgrade keeps the existing 2:1 isometric projection, gameplay identifiers, run-save schema, theme palette changes, lighting, and deterministic dungeon variation intact.

### Added

- A packaged high-resolution sprite library under `src/arch_rogue/assets/sprites/` with a validated manifest and directional art for all five archetypes, the regular enemy roster, every named floor boss, the final gate tyrant, shopkeepers, story guests, wisps, owls, item classes, interactable props, and core world tiles.
- `sprite_assets.py` with lazy PNG decoding, alpha-bound normalization, explicit foot/tile anchors, eight-direction clip resolution, bounded LRU caches, theme tinting, special-room wall decoration, and per-resource failure isolation.
- Asset-backed idle and run animation for the actor roster, plus authored attack/cast clips where available. Missing state/direction frames fall back to a safe rotation or the procedural atlas without interrupting a run.
- High-resolution isometric floor, wall, open-door, closed-door, stair, shop, quest-room, tavern, and garden tiles aligned to canonical `360×200` floor, `360×360` stair, and `360×440` wall/door render canvases.
- Asset props for spike/rune/poison traps, shrines, secret caches, merchant signs, gold stacks, and Ambush Bells, each normalized to gameplay scale with procedural telegraphs and glows preserved.
- Cached item thumbnails in the inventory UI; legacy mode retains the original faceted rarity gems.
- A Display → Graphics setting (`G`) that switches between asset sprites and legacy procedural graphics at runtime, clears derived tile/lighting caches, and prewarms the selected renderer.
- Scroll-aware options rendering with physically fitted, cached typography so every setting and footer remains readable, visible, and selectable at low resolutions and UI scale 4.

### Changed

- `Game.sprites` now uses an asset-first compatibility facade while `PixelSpriteAtlas` remains public and unchanged for legacy imports and tests.
- Player, enemy, boss, NPC, familiar, loot, relic, and world rendering resolve stable gameplay names through manifest aliases rather than storing asset paths in saves.
- Authored actor animation bypasses the old procedural lean/stretch pass to avoid double motion; non-looping actions sample the full clip over their gameplay visual TTL, while legacy sprites retain their previous transforms exactly.
- World sprite variants keep deterministic seed/cache keys and theme recoloring. Special-room markings remain composited dynamically so procedural room flavor is preserved.
- Package data now includes nested sprite manifests and PNGs in wheels and web builds.
- Runtime/package release version is `4.0.0`; options schema is `4`. Run saves remain schema `5` and graphics preference remains options-only.

### Compatibility and resilience

- Explicit legacy mode reproduces the original procedural actor, item, prop, and tile renderer.
- Missing, corrupt, incomplete, or unsupported asset entries fall back independently instead of disabling modern graphics globally; malformed manifest shapes are contained at startup and failed resource reads are negatively cached.
- Old options files migrate to asset sprites by default; old run files require no sprite-specific migration.
- Normal maps continue to bake lazily from the actual resolved frame, preserving colored lighting on both renderers.

### Validation

- `python -m compileall src tests` — OK.
- Focused graphics/options/save/rendering regression run — 80 tests, all passing.
- `python -m unittest discover tests` — 187 tests, all passing.
- Clean isolated wheel build/install — 2,192 nested sprite resources present (2,191 PNGs plus the manifest); the installed manifest loaded 25 actors, 6 item classes, 8 props, and 9 world types.
- Warm-cache 960×540 dummy-SDL benchmark — 1.97 ms/frame (507.6 FPS) with no decoded-source, resolved-frame, world, normal-map, tile, or door-cache growth over 120 frames.

## 3.19.5 — Harder Enemies Below Level 5

The difficulty curve flattened out past depth 5, so the lower dungeon felt no more threatening than the upper floors. Enemy HP, damage, aggro, and per-room counts now ramp up more aggressively once you descend below level 5.

### Tuned
- `_apply_run_modifier` HP `depth_multiplier`: added `+ max(0, current_depth - 5) * 0.05` on top of the existing surface scaling, so deep floors add ~5% extra enemy HP per depth past 5 (e.g. depth 10 ≈ +25% over the old curve).
- `_apply_run_modifier` damage: added `+ max(0, current_depth - 5)` flat damage per depth below level 5, stacking on the existing slow `depth - 4` ramp.
- `_apply_run_modifier` aggro: added `+ max(0, current_depth - 5) * 0.25` so deep enemies notice the player from farther away.
- `_populate_dungeon` per-room enemy count: depth ≥ 6 now adds +1 enemy, depth ≥ 8 adds +2 (previously only depth ≥ 7 added +1).

### Unchanged
- Difficulty profile, run modifier, and story-pressure multipliers still apply on top of the new depth scaling.
- Boss HP/damage scaling, trap damage, and elite/miniboss chances are untouched.

## 3.19.4 — Slower, More Rewarding Leveling

Characters were leveling up too quickly, which diluted the payoff of each level-up and made mastery tokens feel cheap. The XP curve is steepened so each level is a genuine milestone.

### Tuned
- Base XP threshold for level 1→2: `60` → `100` (first level now takes ~4-5 kills instead of ~3).
- Per-level XP growth multiplier: `×1.45` → `×1.5`, so later levels scale up faster and stay meaningful across a run.
- `SaveLoadMixin.restore_run_state` default `next_xp` updated `60` → `100` to match the new starting curve.

### Unchanged
- Per-level rewards (max HP +12, max mana +5, max stamina +5, +1 mastery token) are untouched — levels are just harder to earn now.
- XP granted per enemy kill, shrine, and story choice is unchanged.

## 3.19.3 — Rarer Legendary & Unique Drops

Legendary and unique items were dropping far too often, diluting the excitement of finding build-defining gear. The loot-roll thresholds in `PopulationMixin._make_loot` are tightened and the `loot_bonus` influence is dampened so treasure buffs still help without flooding runs.

### Tuned
- Base legendary drop window: `roll > 0.985` → `roll > 0.996` (roughly 1.5% → 0.4% of all loot).
- Base unique drop window: `roll > 0.96` → `roll > 0.988` (roughly 2.5% → 0.8% of all loot).
- `loot_bonus` multiplier for legendary: `×0.5` → `×0.20`; for unique: `×1.0` → `×0.35`, so high loot-bonus floors no longer make rare drops commonplace.
- `RARITY_PROFILES` descriptive weights lowered for `Unique` (4 → 2) and `Legendary` (2 → 1) to reflect their new scarcity.

### Unchanged
- Boss-kill unique drops (`CombatMixin.kill_enemy` → `_make_unique`) still guarantee a unique gate relic.
- Affix counts, roll ranges, cursed-bargain logic, and equipment power are untouched.

## 3.19.2 — Skill Points → Mastery Tokens

For consistency with the Disciplines rename, the class-progression currency **skill points** is renamed to **mastery tokens** throughout the codebase, UI, and docs. The player spends mastery tokens to acquire Disciplines.

### Renamed

- `Player.skill_points` → `Player.mastery_tokens`.
- `CombatMixin.grant_skill_point` → `grant_mastery_token`.
- Save JSON key `"skill_points"` → `"mastery_tokens"`.
- UI text: the level-up floater `LEVEL UP · SKILL POINT` → `LEVEL UP · MASTERY TOKEN`; the grant floater `+N Skill Point(s)` → `+N Mastery Token(s)`; the character-sheet subtitle and Disciplines-tab hints now say "mastery token(s)"; the War Shrine message says "mastery token".
- All comments/docstrings referencing "skill point(s)" now say "mastery token(s)".

### Preserved (intentionally unchanged)

- **Save compatibility:** `restore_run_state` accepts the legacy `"skill_points"` key as a fallback (older saves resume without losing banked tokens). Save schema `version` remains `5`.
- `player.skill_upgrades` (acquired discipline keys) and `has_upgrade()` are unchanged — they are the acquired-key store, not the currency.
- Discipline node keys (e.g. `warden_bulwark`), combo terminology, and class-skill/action-skill concepts are unchanged.
- Historical changelog entries retain their original wording.

### Validation

- `python -m compileall src tests` — OK.
- `python -m unittest discover tests` — 178 tests; one pre-existing unrelated inventory-HUD layout failure (`test_inventory_hud_layout_navigation_sorting_and_cues`) remains, unchanged by this refactor. New backward-compatibility assertion added to the save-migration test (legacy `skill_points` key → `mastery_tokens`).

## 3.19.1 — Skill Tree → Disciplines Refactor

The class-progression skill tree is renamed to the **Disciplines** system throughout the codebase, docs, and UI. Skill-tree nodes are now **Disciplines**, routes are **Discipline Paths**, and the five depth tiers are **Degrees** (Degree 1–5). Discipline node keys, save schema, and save-compatibility are unchanged.

### Renamed (domain model and content tables)

- `SkillNode` → `Discipline`; `SkillUpgrade` → `DisciplineUpgrade`.
- `SKILL_NODES` → `DISCIPLINES`; `SKILL_UPGRADES` → `DISCIPLINE_UPGRADES` (backwards-compat flat table derived from the discipline tree).
- `LEGACY_SKILL_KEYS` → `LEGACY_DISCIPLINE_KEYS`.
- Discipline fields: `tier` → `degree`, `branch` → `path`, `cross_branch_tags` → `cross_path_tags`, `cross_branch_bonus_melee` → `cross_path_bonus_melee`, `cross_branch_bonus_spell` → `cross_path_bonus_spell`.

### Renamed (progression helpers)

- `migrate_skill_keys` → `migrate_discipline_keys`
- `skill_node_by_key` → `discipline_by_key`
- `skill_nodes_for_archetype` → `disciplines_for_archetype`
- `skill_branches_for_archetype` → `discipline_paths_for_archetype`
- `skill_tree_max_tier` → `max_discipline_degree`
- `skill_branch_nodes` → `discipline_path_nodes`
- `committed_branches` → `committed_paths`
- `is_branch_locked` → `is_path_locked`
- `branch_progress` → `path_progress`
- `completed_branches` → `completed_paths`
- `completed_branch_bonus` → `completed_path_bonus`
- `cross_branch_tag_bonus` → `cross_path_tag_bonus`
- `MAX_COMMITTED_BRANCHES` → `MAX_COMMITTED_PATHS`
- `COMPLETED_BRANCH_BONUS_*` → `COMPLETED_PATH_BONUS_*`

### Renamed (combat / game / input / menus API)

- `available_skill_choices` → `available_disciplines`
- `skill_node_state` → `discipline_state`
- `choose_skill_upgrade` → `choose_discipline`
- `grant_skill_upgrade` → `grant_discipline`
- `_apply_skill_node` → `_apply_discipline`
- `cross_branch_bonus_state` → `cross_path_bonus_state`
- `acquired_skill_nodes` → `acquired_disciplines`
- `acquired_skill_upgrades` → `acquired_discipline_summaries`
- `_skill_node_cells` → `_discipline_cells`
- `_*_skill_tree_*` cursor/grid/draw methods → `_*_discipline_*`
- UI state strings: `"skill_tree"` → `"disciplines"` (character-sheet tab), `"branch_locked"` → `"path_locked"`.
- Tab label "Skill Tree" → "Disciplines"; row labels "Tier N" → "Degree N".

### Preserved (intentionally unchanged)

- **Save compatibility:** the player's acquired-key store `player.skill_upgrades`, the currency `player.skill_points`, the `has_upgrade(key)` helper, `grant_skill_point`, and the save JSON keys `"skill_upgrades"` / `"skill_points"` are unchanged. Discipline node keys (e.g. `warden_bulwark`) are stable identifiers and are NOT renamed.
- **Combo terminology:** `combo_bonus`, `combo_bonus_preview`, `combo_bonus_steps`, `COMBO_BONUS_PER_STEP_*`, and "combo tier" wording are unchanged — the combo bonus is a breadth concept distinct from discipline Degrees.
- **Action skills / class skill:** the hotkey-3 "class skill" and equipment "skill bonus" concepts are unchanged.
- Historical changelog entries retain their original (contemporary) terminology.

### Validation

- `python -m compileall src tests` — OK.
- `python -m unittest discover tests` — 177 pass; one pre-existing unrelated inventory-HUD layout assertion failure (`test_inventory_hud_layout_navigation_sorting_and_cues`) is unchanged by this refactor (verified failing on the clean tree).

## 3.19.0 — Class Skill Rename

The archetype-specific active ability bound to hotkey 3 is renamed from the
legacy "slot 3 skill" / "nova-slot" terminology to **class skill** throughout
the codebase. The rename clarifies that the hotkey-3 ability is the
archetype's signature class skill, not a generic "slot" or a "nova" variant.

### New abstraction

- **Data-driven class-skill registry.** `class_skill_kind()` and
  `player_cast_class_skill()` now dispatch through two class-level lookup
  tables (`_CLASS_SKILL_KINDS` / `_CLASS_SKILL_CASTS`) instead of an if/elif
  chain. Adding a new class skill only requires extending the tables, not
  editing the dispatch logic.

### Renamed (structural / shared budget)

- `slot_3_skill_kind()` → `class_skill_kind()`
- `player_cast_slot_3()` → `player_cast_class_skill()`
- `equipment_slot_3_bonus()` → `equipment_class_skill_bonus()`
- `nova_mana_cost()` → `class_skill_mana_cost()`
- `nova_cooldown()` → `class_skill_cooldown()`
- `Player.nova_timer` → `Player.class_skill_timer`
- HUD variables `slot_3_kind` / `slot_3_icon` / `slot_3_color` / `nova_name` →
  `class_skill_kind` / `class_skill_icon` / `class_skill_color` /
  `class_skill_name`
- Controls labels: "Slot 3 skill" / "Slot 3 class skill" → "Class skill"

### Preserved (nova-specific implementation)

- `player_cast_nova()` and `nova_damage_type()` keep their names — Nova is one
  *implementation* of a class skill, not the abstraction itself.
- Legacy `Nova` equipment wording still resolves via
  `equipment_class_skill_bonus()` for save compatibility.
- `time_skip_timer` (Warden-specific) is unchanged.
- Save schema `version` remains `5`; `class_skill_timer` is transient and not
  serialized, so no migration is needed.

### Updated references

- `combat.py`, `game.py`, `input.py`, `run_flow.py`, `rendering/hud.py`,
  `menus/controls.py`, `menus/character.py`, `models.py`.
- All test modules updated to the new API. Version-current tests now target
  `3.19.0`.

## 3.18.4 — Acolyte Blood Retarget

The Acolyte's familiar lifesteal lived on the Spirit branch (`acolyte_wraith_host`,
t2), which made the summoner build too self-sustaining for how early it came
online. Lifesteal now belongs to the Blood branch, and the Blood branch's
previously-dormant nova-leech ramp is repurposed as a shared **Blood spell
leech** that fires on every active Blood-tagged damage source.

### Changed

- **Removed familiar lifesteal from the Spirit branch.** `acolyte_wraith_host`
  (Owl Companion, Spirit t2) now grants HP + persistence only — it no longer
  sets the familiar `lifesteal` flag. The node's description was updated to drop
  the "drains life from foes" wording.
- **Blood branch lifesteal now applies to Blood Rite, Spirit Bolt, and Spirit
  Call.** The old `_acolyte_nova_leech` helper (which only fired on the legacy
  `player_cast_nova` path the Acolyte no longer reaches from the action bar) is
  renamed `_acolyte_spell_leech` with the same per-tier ramp (3/4/5/7/8 across
  Sanguine / Gravebind / Blood Pact / Crimson Maw / Sanguine Ascendant, +1 from
  the "Blood leech" gear bonus) and is now applied to:
  - **Spirit Bolt** — each projectile hit siphons life when Blood is committed
    (in `update_projectiles`, gated on `projectile.archetype == "Acolyte"`).
  - **Spirit Call familiars** — familiar hits heal the Acolyte by the live
    spell-leech value; the `lifesteal` flag is set at summon time from Blood
    investment (`_acolyte_spell_leech() > 0`) and the heal scales with the
    current Blood tier.
  - **Legacy nova** — `player_cast_nova` keeps applying the same leech for
    direct callers / existing tests.
  Blood Rite (melee) is unchanged: it still uses `_acolyte_melee_leech`
  (2/3/4/5/6 ramp).
- **Blood node descriptions** no longer reference the retired Blood Nova:
  `acolyte_gravebind` now reads "Blood Rite and Spirit Bolt bind foes…" and
  `acolyte_crimson_maw` reads "Blood skills devour weak foes…".
- The `familiar_stats` docstring notes the lifesteal move to Blood.

### Notes

- Save schema is unchanged (version stays `5`); the `Familiar.lifesteal`
  field is preserved and still serialized. Existing familiars keep their flag
  until the host is recreated on the next Spirit Call / floor descent, at
  which point it is recomputed from the current Blood investment.
- `acolyte_wraith_host`'s HP bonus and prerequisite chain are unchanged, so
  existing Spirit builds keep their progression path; they just lose the
  (over-tuned) sustain.

## 3.18.3 — Broad HUD Render Cache

### Bug fixes

- **Lighting crash on room entry:** entering a room could crash with
  `TypeError: cannot use 'tuple' as a dict key (unhashable type: 'list')` in
  `draw_lighting` / `_radial_light_sprite`. Light colors flow in from several
  sources and JSON save round-trips tuples to lists, but the radial-sprite and
  lit-actor tint caches keyed on `light.color` directly, so any list (or
  unhashable `pygame.Color`) color raised when it scrolled into view. Both cache
  keys now normalize the color through a new `hashable_color` helper, so the
  lighting system is robust to list/`Color` colors regardless of how they
  arrived. The save-load conversion in `light_source_from_dict` is retained.

### Render caching

On top of the 3.18.2 zoom-out fix, profiling showed the HUD was the largest
broad (zoom-independent) cost: ``font.size``/``font.render``/``ellipsize`` for
per-frame text and ``draw.rect`` + per-call SRCALPHA allocations for panels and
the action bar. The HUD redraws the same stable art every frame, so these are
now cached:

- **Rendered text surfaces** (``draw_ui_text``): keyed by (font, text, color,
  width). Static labels (ability names, hotkeys, section headers) skip
  ellipsize + ``font.render`` entirely after the first frame; dynamic text
  (cooldown counts, HP/mana numbers) misses and renders as before.
  ``ellipsize_ui_text`` now measures truncation candidates through the shared
  ``_text_size`` cache instead of raw ``font.size``.
- **Panel art** (``draw_translucent_panel`` / ``draw_ornate_hud_panel``):
  keyed by (size, colors, radii, ui_scale, studs). The chiseled bevel / trim /
  iron studs are built once and ``convert_alpha``-ed for fast blits, removing
  the per-call SRCALPHA allocation + ~5 draw.rects (plus up to 12 stud circles)
  for the HUD's stable panels.
- **Action-icon body** (``draw_hud_action_icon``): the gradient plate, bevels,
  gold border, shine, glyph, label, and hotkey badge are a pure function of
  (size, colors, ready, ui_scale, glyph texts), so the composed body is cached
  and blitted; only the per-frame cooldown overlay / arc, count badge, and
  status text are drawn on top. Steady-state frames pay one blit instead of
  ~15 draw.rects + a shine surface + glyph + two text renders per icon.

All caches are cleared in ``rebuild_fonts`` (which also fires on ui-scale /
resolution changes) so stale art is never reused after fonts are replaced.

### Measured (1280x720, headless, 400-frame average; no active cooldowns)
| zoom | 3.18.2 | 3.18.3 |
|------|--------|--------|
| 1.6  | 4.59 ms | 3.19 ms |
| 1.0  | 5.70 ms | 4.13 ms |
| 0.65 | 8.98 ms | 7.13 ms |

~21-31% lower draw time across all zoom levels. With active cooldowns the
action-icon body stays cached (the ``ready=False`` variant), so the saving
holds; only the cheap cooldown overlay / status text are redrawn.

### Changed
- `rendering/base.py`: ``draw_ui_text`` caches rendered surfaces;
  ``ellipsize_ui_text`` measures via ``_text_size``; ``draw_translucent_panel``
  and ``draw_ornate_hud_panel`` cache built panel art (``convert_alpha``-ed) in
  a shared ``_hud_panel_cache``; panel build split into
  ``_build_ornate_hud_panel``.
- `rendering/hud.py`: ``draw_hud_action_icon`` blits a cached body
  (``_hud_icon_cache``) and draws only the dynamic overlays on top; body build
  split into ``_build_hud_action_icon_body`` (uses a ``self.screen`` swap so
  ``draw_hud_action_glyph`` / ``draw_ui_text`` compose into the offscreen body).
- `options.py`: ``rebuild_fonts`` clears ``_ui_text_cache``,
  ``_hud_panel_cache``, and ``_hud_icon_cache`` alongside ``_text_size_cache``.
- `tests/test_hud_action_bar.py`: 2 new tests — body cache identity +
  rebuild_fonts invalidation, and that the cached body does not swallow the
  per-frame cooldown overlay.

## 3.18.2 — Zoom-Out Render Performance

Zooming out to the max caused a noticeable frame-time cliff because the
continuous lighting model and the ambient depth vignette ran on the oversized
world layer (sized `screen / zoom`) before it was downscaled to the display.
At max zoom-out that layer is ~2.4x the display pixel count, so the half-res
light buffer, its `smoothscale` upscale, and the `BLEND_RGBA_MULT` composite
all ran at layer resolution.

Lighting and the vignette are screen-space effects, so they now run on the
*smaller* of the world layer and the display:

- **Zoomed out (zoom < 1):** shading runs *after* the world-layer composite, on
  the real display. Light/vignette buffers are display-sized, so the lighting
  pass is independent of viewport zoom.
- **Zoomed in (zoom > 1):** shading runs *before* the composite, on the
  (smaller) world layer, as before — so zooming in never touches
  display-resolution buffers.
- **Zoom 1.0:** unchanged (no layer; shading runs on the display directly).

Light positions use a new zoom-aware `world_to_display` projection; light
sprite radii and the fog-of-war ambient stamp scale by an effective zoom so a
light covers the same world area at any zoom. `visible_bounds` is now cached
per frame so the post-composite pass reuses the layer-derived visible bounds
instead of recomputing against the (smaller) display. At zoom 1.0 the path is
bit-identical to before.

### Measured (1280x720, headless, 300-frame average)
| zoom | before | after |
|------|--------|-------|
| 1.6  | 4.85 ms | 4.96 ms |
| 1.0  | 6.34 ms | 6.15 ms |
| 0.8  | 9.18 ms | 8.52 ms |
| 0.65 | 11.50 ms | 9.82 ms |

Max zoom-out drops ~15% (~1.7 ms/frame); zoom-in is unchanged within noise.

### Changed
- `camera.py`: added `world_to_display` (zoom-aware display-space projection);
  `visible_bounds` is now cached in the per-frame `_frame_cache`.
- `rendering/base.py`: `_render_world_view` splits shading into a pre-composite
  (zoomed in) / post-composite (zoomed out / native) pass via a
  `_shade_post_composite` flag and a `_shade_world` helper; the post-composite
  cache reset preserves zoom-independent frame caches (`visible_bounds`,
  `camera_iso`, `frame_lights`).
- `lighting.py`: `draw_lighting` / `_stamp_ambient` pick the projection and
  sprite/tile scale from `_shade_params()` (effective zoom + `world_to_display`
  when post-composite, `world_to_screen` at native scale otherwise).
- `tests/test_viewport_zoom.py`: 5 new tests covering `world_to_display`, the
  shade-direction flag, the smaller-surface buffer sizing, and that lighting
  still shades the display at max zoom-out.

## 3.18.1 — Warden Time Skill Path

The Warden now has a dedicated slot-3 skill branch like the Rogue (Traps),
Arcanist (Nova), Acolyte (Spirit), and Ranger (Control). The previously
flavor-only **Fortress** branch is rethemed into the **Time** branch, a
five-tier ladder that changes how Time Skip *plays* instead of just bumping
its duration. Node keys are preserved, so existing Warden saves restore their
purchased Fortress nodes with new names/effects and keep their stat bonuses;
commitment is derived from keys, so a run committed to Fortress auto-becomes
committed to Time. No save-schema change (still `version: 5`).

### Time branch ladder
- **T1 Temporal Sigil** (`warden_ward`): Time Skip costs 1 less mana, cools
  down 0.3s faster, and lasts +0.5s.
- **T2 Time Skip** (`warden_bulwark_wave`): +1.0s duration and the cast pulse
  staggers foes caught in the ring (brief holy stun + attack stall, no damage).
- **T3 Stutter Step** (`warden_stone_aegis`): deepens the slow factor 0.4 → 0.3.
- **T4 Temporal Aegis** (`warden_unyielding`): while Time Skip is active the
  Warden takes 20% less incoming damage (the old "ward" made real).
- **T5 Eternal Moment** (`warden_eternal_wall`): each kill while Time Skip is
  active refunds ~40% of the slot-3 cooldown, so aggressive play sustains the slow.

### Changed
- `time_skip_duration()` / `time_skip_factor()` now scale along the Time branch
  (`warden_ward`, `warden_bulwark_wave`, `warden_stone_aegis`) instead of the
  incidental Bulwark hooks. The `warden_aegis` / `warden_bulwark_ward` duration
  bonuses are removed; those nodes stay pure Bulwark melee (cleave/stagger) and
  their Time Skip wording is dropped.
- `nova_mana_cost` / `nova_cooldown` apply the Warden T1 (Temporal Sigil)
  discount. `player_cast_time_skip` applies the T2 cast-ring stagger via
  `apply_enemy_status` (no damage, no on-hit procs). `take_player_damage`
  applies the T4 Temporal Aegis ward while the slow window is open. `kill_enemy`
  applies the T5 on-kill cooldown refund while the window is open.
- `progression.py`: the five Fortress nodes are renamed/rethemed to the Time
  branch (`branch="Time"`, `tags=("Time",)`); keys, prerequisites, tiers, and
  stat bonuses are unchanged. `warden_bulwark_ward` (Bulwark) description no
  longer references Time Skip.
- `tests/test_3_18_time_skip.py` extended (now 19 tests): the duration-scaling
  test moved to the Time branch, plus T1 budget discount, T3 deeper slow, T2
  cast-ring stagger, T4 damage ward, and T5 on-kill refund (active + inactive).
- Package metadata, `__version__`, save `release`, and version-current tests
  now target `3.18.1`. Save schema `version` remains `5`.

## 3.18.0 — Warden Time Stop (Time Skip)

The Warden's slot-3 action bar entry is now **Time Skip**, replacing
Bulwark Wave. Activating it opens a short timed window during which the
entire enemy simulation slows to 40% speed — both movement and attack
cadence — while the Warden's own movement, attacks, and timers keep their
full tempo. It reuses the existing nova-slot mana cost and cooldown so the
action bar and equipment bonuses stay balanced, and legacy `Nova` gear on
older Warden saves still applies its slot-3 budget.

### Added
- `player_cast_time_skip()` / `time_skip_duration()` / `time_skip_factor()` /
  `enemy_time_scale()` in `combat.py`. Time Skip spends the slot-3 mana/cooldown
  budget (via `nova_mana_cost` / `nova_cooldown`), sets `player.time_skip_timer`,
  and emits a wide cast pulse + floater. No enemy damage — it is a pure control
  skill.
- Global enemy time scaling in `update_enemies`: a single `scaled_dt =
  dt * enemy_time_scale()` is applied to the enemy `attack_timer` decrement and
  every enemy `move_actor` step, so movement and attack speed slow uniformly.
  Player timers/movement, familiars, ambush bells, projectiles, and enemy
  status ticks are intentionally unaffected.
- `Player.time_skip_timer` field (transient; not serialized, defaults to 0 on
  restore and reset on floor descent alongside the other slot timers).
- Time Skip HUD icon: a clock-face glyph (`draw_hud_action_glyph` "time_skip"
  branch) with class-tinted coloring, plus `time_skip` slot-3 kind/color wiring
  in `hud_action_slots`.
- Warden slot-3 dispatch: `slot_3_skill_kind()` returns `"time_skip"` for the
  Warden and `player_cast_slot_3()` routes to `player_cast_time_skip()`.
  `skill_names()` / `skill_names_for()` now label the Warden slot `Time Skip`.
- `equipment_slot_3_bonus` recognizes new `Time Skip` wording for future Warden
  gear while keeping legacy `Nova` wording working for existing saves (mirrors
  the Rogue Ambush Bell compatibility pattern).
- Skill-tree wording updated: `warden_bulwark_ward` now extends Time Skip
  duration (+1.2s) and `warden_aegis` adds +0.6s; node descriptions reference
  Time Skip instead of Bulwark Wave. Keys/prerequisites are unchanged.
- `tests/test_3_18_time_skip.py` (9 tests): slot-3 swap, cast spends
  mana/cooldown and sets the timer, enemies move slower while active, enemy
  attack cadence slows while active, player is unaffected, non-Warden classes
  keep nova, equipment bonus recognizes Time Skip, duration scales with
  upgrades, save round-trip preserves the timer default, and a full-frame
  render smoke test.

### Changed
- Package metadata, `__version__`, save `release`, and version-current tests
  now target `3.18.0`. Save schema `version` remains `5` because Time Skip is
  transient.

## 3.17.2 — In-Game Viewport Zoom (Ctrl + Scroll)

The viewport distance can now be adjusted live during gameplay with
**Ctrl + scroll wheel**: scroll up to zoom in (fewer tiles, larger sprites),
scroll down to zoom out (see more of the dungeon). The view starts maxed-in
by default and applies uniformly to tiles, actors, effects, and lighting;
mouse aim stays accurate at any zoom level.

### Added
- `CameraMixin` viewport-zoom state (`view_zoom`, clamped to `0.65`–`1.6`) with
  `adjust_view_zoom(notches)`; positive notches zoom in, negative zoom out.
  The default is now `VIEW_ZOOM_MAX` (max zoom-in); scroll out with Ctrl+wheel
  to see more of the dungeon.
- `Game.handle_events` now handles `MOUSEWHEEL` while playing with
  `KMOD_CTRL` held, forwarding `event.y` to `adjust_view_zoom`.
- Zoom-aware `screen_to_world` so `face_player_toward_screen_point` / mouse
  aim remain correct when the view is zoomed.

### Changed
- `RenderingBaseMixin.draw` renders the dungeon + actors + lighting/overlays
  through a new `_render_world_view` path. At zoom `1.0` it draws straight to
  the display (unchanged hot path, no extra cost). At any other zoom it draws
  to a cached offscreen world layer sized `screen_size / zoom` (so
  `visible_bounds` naturally covers more tiles when zoomed out) and
  `smoothscale`s it back up to fill the display — a uniform zoom of the whole
  world frame with no letterboxing.

### Validation
- `python -m compileall src tests`.
- New `tests/test_viewport_zoom.py` covers default zoom, clamping/steps,
  Ctrl+scroll dispatch, scroll-without-Ctrl no-op, `screen_to_world` inversion
  across zoom levels, and `draw()` at non-native zoom.
- `python -m unittest discover tests` (151 tests, all pass).

## 3.17.1 — Web Build Black-Screen Fix

The pygbag/Pyodide web build booted to a black canvas instead of the title
screen. Root cause: the bundled icon PNG assets (added in 3.16 work) are now
included in the browser tarball, so `load_icon` reached
`pygame.image.load(io.BytesIO(...))`; the pygame-web/Pyodide runtime raises
`RuntimeError` ("can't access resource on platform") for file-like image
sources, which `load_icon` only guarded with `except pygame.error`. The
uncaught error crashed `Game.__init__` before the first frame, leaving the
canvas black.

### Fixed
- `src/arch_rogue/icon.py` `load_icon` now catches `RuntimeError`/`OSError`/
  `ValueError` (in addition to `pygame.error`) from `pygame.image.load` and
  `convert_alpha`, so platforms without file-like image loading degrade to
  `None` (no window icon / title crest) instead of crashing `Game`
  construction. Desktop behavior is unchanged.
- `web/main.py` now mirrors import- and run-time tracebacks to the browser
  console (via the Pyodide `js` bridge) in addition to the in-page xterm
  terminal, so future web startup failures are visible in DevTools instead
  of presenting as an opaque black canvas.

### Validation
- Rebuilt the web bundle with `python web/build.py --no-serve` and verified
  in a headless Chromium (Playwright) that the title screen renders non-black
  content with no Python traceback reaching the browser console; driving the
  title menu into a run exercises the gameplay/lighting/ambush-bell paths on
  the web without crashing.
- `python -m compileall src tests web/main.py` passes.
- `python -m unittest discover tests` passes (145 tests).
- Package metadata, `__version__`, and save `release` updated to `3.17.1`.
  Save schema `version` remains `5`.

## 3.17.0 — Rogue Ambush Bell

The Rogue's slot-3 action is now **Ambush Bell**: a single active cursed lure trap that plants at the aimed floor point, arms after a short delay, pulls nearby non-boss enemies toward its kill zone, then snaps shut in a focused shadow-dagger burst. It reuses the old nova-slot mana/cooldown budget for action-bar balance while preserving Acolyte Spirit Call and other classes' nova-style slot-3 actions.

### Added
- `AmbushBell` transient runtime model with plant position, arm/lifetime timers, lure/trigger/damage radii, damage payloads, owner/archetype fields, and triggered/armed state.
- Rogue-only `player_cast_ambush_bell()`, `update_ambush_bells()`, and `detonate_ambush_bell()` combat flow with one-active-bell replacement, cast/detonation smoke, expiry splash/puff behavior, lure movement bias, physical primary/splash damage through `damage_enemy()`, poison hooks for `rogue_venom` / trap-branch upgrades, and crit/backstab scaling for Precision upgrades.
- Depth-sorted Ambush Bell rendering, a distinct shadow-dagger detonation impact, a bell HUD glyph, a subtle lured-enemy marker, and a procedural bell SFX.
- `tests/test_3_17_ambush_bell.py` covering Rogue slot-3 dispatch, mana/cooldown spend, single-bell replacement, arming delay, trigger detonation, venom status, Trap-path tuning/control/recovery, expiry splash, lure movement, lifecycle clearing, no save persistence, and Acolyte/non-Rogue regressions.

### Changed
- Slot-3 dispatch is centralized through `player_cast_slot_3()` / `slot_3_skill_kind()` so archetype-specific actions no longer require duplicating Rogue/Acolyte/Nova branches across keyboard and controller paths.
- Rogue slot-3 labels now read `Ambush Bell` in combat HUD and character/class previews; controls describe the key as the class-specific slot-3 skill.
- Legacy `Nova` equipment bonuses still apply to the slot-3 budget for save compatibility, while new `Ambush Bell` wording is recognized for Rogue-specific future items.
- Active bells clear on floor descent, run reset, victory/death cleanup, and save restore/load boundaries; bell state is intentionally not serialized.
- Rogue Traps skill path nodes now specialize Ambush Bell directly through a captured tuning profile: faster arming/lure setup, poison chimes, snaring iron clappers, wider resonant splash, and a restrained capstone recovery reward on successful ambush kills.
- Package metadata, `__version__`, save `release`, and version-current tests now target `3.17.0`. Save schema `version` remains `5` because bell state is transient.

### Validation
- `python -m unittest tests.test_3_17_ambush_bell` passes (9 tests).
- `python -m unittest tests.test_3_15_summons tests.test_hud_action_bar tests.test_save_and_metadata tests.test_archetypes_options_and_difficulty tests.test_3_9_input_accessibility` passes (34 tests).
- `python -m unittest tests.test_3_16_lighting_overhaul tests.test_world_rendering_and_animation tests.test_story_mode` passes (26 tests).
- `python -m unittest discover tests` passes (145 tests).
- `python -m compileall src tests` passes.

## 3.16.2 — Dark-Level Scheduling Tuning

Dark/no-memory floors now appear only from depth 5 onward, with each eligible floor rolling a flat 50% chance to be dark. Early floors 1-4 are always light floors with fog-of-war tile memory, giving runs a longer readable opening before lantern-only exploration can begin.

### Changed
- `run_flow.py` dark-floor planning changed from the old depth ramp (1-3 always light, 4-6 50% dark, 7+ 75% dark) to the new gate: depths 1-4 always light, depths 5+ 50% dark.
- `tests/test_dark_levels.py` now asserts that dark floors never appear before depth 5 and checks the eligible-depth distribution across deterministic seeds.
- Package metadata, `__version__`, save `release`, and version-current tests now target `3.16.2`. Save schema `version` remains `5`.

### Validation
- `python -m unittest tests.test_dark_levels` passes (3 tests).
- `python -m compileall src tests` passes.
- `python -m unittest discover tests` passes (136 tests).

## 3.16.1 — Options Menu Regrouping & License Notice

The Options menu is regrouped into four labeled sections — **Display**, **Controls**, **Audio**, and **Lights** — so related settings read as a group instead of a flat list. Section headers are drawn by a new optional `sections` parameter on `draw_menu_rows` (flat row-index cursor space is unchanged, so navigation/activation and the `OPTIONS_ROW_*` constants stay index-based). The **Reduce motion** accessibility toggle is removed: it had no gameplay effect (it only suppressed the lantern/torch brightness flicker) and the flicker is now always on when the lighting model is on. The underlying `_reduced_motion` field, its persistence in `~/.arch_rogue_options.json`, the `R` hotkey, and the `OPTIONS_ROW_REDUCE_MOTION` row are all removed; `flicker_enabled()` simplifies to `lighting_enabled()`.

This release also adds an **AI Provenance & Liability Notice** to `LICENSE` and `README.md`, and a short summary of the notice to the license header of every source file that already carries the Apache-2.0 SPDX header.

### Changed
- `menus/options.py` reorders rows into Display / Controls / Audio / Lights groups and passes `sections` to `draw_menu_rows`; the "Reduce motion" row is gone (10 rows, down from 11).
- `menus/base.py` `draw_menu_rows` gains an optional `sections: Sequence[tuple[int, str]]` param that draws an aged-gold caption + thin stone rule above the first row of each section and subtracts the header height from the row-fit calculation. Other callers (title, controls, exit) are unchanged.
- `input.py` row constants renumbered to the grouped order; `OPTIONS_ROW_COUNT` is now 10 and `OPTIONS_ROW_REDUCE_MOTION` is removed; the reduce-motion activate branch is gone.
- `game.py` drops the `R` options hotkey and the `_reduced_motion` init field.
- `options.py` no longer persists/loads `reduced_motion`.
- `lighting.py` `flicker_enabled()` returns `lighting_enabled()` (flicker always on when lighting is on).
- `constants.py` flicker-amplitude comment updated; `scripts/render_darkness_levels.py` drops the `_reduced_motion` assignment.
- `tests/test_3_16_lighting_overhaul.py`: `test_reduced_motion_suppresses_flicker` replaced with `test_flicker_modulates_when_lighting_on` (flicker modulates when on, suppressed when lighting off / `flicker=False`); `test_version_bumped` targets `3.16.1`.
- Package metadata, `__version__`, and save `release` updated to `3.16.1`. Save schema `version` remains `5`.

### Validation
- `python -m compileall src tests scripts` passes.
- `python -m unittest tests.test_3_16_lighting_overhaul` passes (18 tests).
- `python -m unittest discover tests` passes (136 tests).

## 3.16.0 — Lighting Overhaul

The per-tile alpha falloff is replaced by a continuous, multi-source, colored lighting model so the dungeon reads as a lit space rather than a visibility mask. A screen-space light buffer accumulates radial light sprites additively (player lantern, static torches/shrines, transient skill/projectile/impact pulses, theme ambient wash) and composites onto the world with a multiply pass, all at half resolution with zero per-frame allocations. Fog-of-war memory (`revealed_tiles`) and sight/lantern reach (`can_see_world_position` / `has_line_of_sight`) are unchanged; the tile draw pass still culls never-revealed / beyond-lantern terrain, it just no longer quantizes the alpha. The 3.8.0 per-tile alpha path survives verbatim as the `Lighting Off` fallback and the web default.

### Added
- `lighting.py` module owning the lighting model: a `LightSource` dataclass (world-tile radius, color, intensity, ttl, flicker) shared by static and transient lights; `bake_normal_map` (alpha-silhouette + luminance height map -> 3x3 Sobel tangent-space normals, deterministic, applies to sprites and tiles); and `LightingMixin` composed into `RenderingMixin` with `draw_lighting`, `_light_buffer` (reused half-res `SRCALPHA`), `_radial_light_sprite` (cached additive gradients), ambient stamping, and a persistent per-(sprite, dominant-light-bucket) lit-actor tint cache cleared on floor/theme change.
- Procedural normal maps baked lazily into the sprite atlas (`PixelSpriteAtlas.normal_map_for`) at the lit-shade downsample size so the one-time cost is ~1k px/sprite, gated by the `Lighting detail` option and skippable on the `LIGHTING_OFF` tier.
- Screen-space light accumulation buffer: each frame the half-res buffer is cleared, the theme-tinted ambient wash is stamped (flat near-black on dark floors; revealed-tile memory wash on light floors), cached radial light sprites are blitted with `BLEND_RGBA_ADD` for the lantern / torches / shrines / transient pulses, then `smoothscale`d to the screen and blitted with `BLEND_RGBA_MULT`. Reused buffer + scratch, cached light sprites - no per-frame allocations.
- Player lantern: a warm dynamic light at `DARK_LEVEL_LIGHT_RADIUS` (dark floors) / `LIGHT_LEVEL_SIGHT_RADIUS` (light floors, adding local warmth over the ambient tint), so sight/visibility reach is identical and combat/LOS logic is untouched. A slow (~0.25 Hz) smooth brightness pulsate for a lantern feel: the radius is constant (one cached sprite, no size stepping) and the brightness modulates as a continuous multiply (no quantized stepping), togglable via the `Reduce motion` accessibility option (which suppresses it entirely).
- Reactive skill/spell lighting: casting any skill emits a transient pulse at the cast site tinted by the impact color (already archetype/damage-tinted), funneled through `add_impact` so casts, dashes, hits, bursts, deaths, and chain-lightning strikes all pulse the buffer. Projectiles carry a small moving light appended inside `update_projectiles` (O(projectiles), no new pass). Tempest/chain-lightning strike tiles flare via the shared `add_impact` hook.
- Theme-tinted ambient light: the ambient floor wash is a white light tinted ~35% toward the `DungeonTheme.accent` so themed regions read as lit by their own light; dark floors use a near-black wash, light floors a brighter memory-level wash over revealed tiles.
- Depth brightness gradient: light floors are brighter near the surface and gradually darken as you descend (the light-floor ambient scales from ~1.6x at depth 1 to ~0.5x at the deepest floor). This is a separate axis from the dark-floor flag - dark floors keep their constant lantern-only ambient and their no-fog-of-war visibility at every depth, so the dark-levels logic is untouched.
- Lit-actor shading: the player and bosses within range of a light get a Lambertian tint computed from the baked normal map. The tint is computed ONCE per (base sprite, light-direction bucket, distance bucket, light color, frame size) from the BASE sprite's stable normal map and cached, then applied (a copy + a single `BLEND_RGB_MULT` blit) to whichever animation frame is showing - so the shading is identical across animation frames and the actor does not flicker as its pose animates (e.g. the cast animation no longer strobes). The sprite is never scaled (stays pixel-crisp); per-pixel work runs only on a cache miss. Regular enemies and familiars rely on the light-buffer multiply. Skipped on the `LIGHTING_OFF` tier and when normal maps are off; hooked in `blit_sprite` (player/boss) via a `base_sprite` arg.
- Static light sources in the world: shrines emit their `SHRINE_HINTS` accent color as a steady glow; bar rooms get a warm flickering lantern and garden rooms a green witchlight at the room center. Populated once per floor in `population.py._populate_light_sources` (deterministic, no RNG, additive/idempotent), stored as a lightweight `light_sources` list.
- Lighting options: `Lighting` (Off/On) and `Lighting detail` (normal maps Off/On) in the Options menu with `L` / `N` hotkeys plus arrow/Enter/gamepad cycling, and a `Reduce motion` (Off/On) accessibility option with an `R` hotkey that suppresses lantern/torch flicker. Persisted in `~/.arch_rogue_options.json`. The web build (`web/main.make_game`) forces lighting + normal maps off so the 3.8.0 per-tile alpha path is the web-safe default.
- New `tests/test_3_16_lighting_overhaul.py` (17 tests): normal-map determinism/alpha-mask/differs-per-pixels, lazy atlas baking, player lantern radius == sight radius, additive buffer accumulation, per-archetype skill pulse timing/tint, projectile light follows the path, theme ambient tint + dark-vs-light levels, static shrine/torch population, Off-tier keeps the 3.8.0 quantized-alpha fallback while On-tier skips it, `draw_lighting` no-op when disabled, save round-trip with `light_sources`, pre-3.16 save loads with empty `light_sources`, reduced-motion flicker suppression, a full-frame render smoke test, and the version bump.

### Changed
- `rendering/base.py` calls `draw_lighting()` between `draw_world_objects()` and `draw_ambient_depth_overlay()`; `rendering/world._tile_blit_entry` skips the quantized-alpha falloff on the On tier (the buffer multiply does the falloff) and keeps it as the Off/web fallback; `prewarm_tile_cache` resets the lighting caches on floor/theme change alongside the alpha-bucket cache.
- `Game.__init__` initializes `light_sources` / `lights` and the three lighting options; `add_impact` emits a transient light flare; `update_visual_effects` decays transient lights via `update_lights`; `reset_transient_visuals` clears `lights`.
- `combat.update_projectiles` appends a moving light per live projectile; `run_flow.restart` / `descend_to_next_depth` and `story_runtime.start_story_mode` reset `light_sources` / `lights`; `save_system` serializes/restores `light_sources` additively (transient pulses never persist; old saves default to `[]`, schema version stays `5`).
- `options.py` persists/loads the three lighting options; `menus/options.py` adds three rows; `input.py` adds `OPTIONS_ROW_LIGHTING` / `OPTIONS_ROW_LIGHTING_DETAIL` / `OPTIONS_ROW_REDUCE_MOTION` (count 11) and activate branches; `game.py` adds `L` / `N` / `R` option hotkeys.
- `sprites.py` imports `bake_normal_map` and exposes `normal_map_for` (lazy, low-res, cached).
- Version-current tests now target `3.16.0`. Package metadata, `__version__`, and save `release` updated. Save schema `version` remains `5`.

### Validation
- `python -m compileall src tests` passes.
- `python -m unittest tests.test_3_16_lighting_overhaul` passes (17 tests).
- `python -m unittest discover tests` passes (135 tests).

## 3.15.0 — Summons, first edition

The Acolyte's slot-3 ability is now **Spirit Call**, replacing Blood Nova on the action bar: it summons a small familiar that follows the Acolyte and attacks enemies on sight. The familiar persists until killed or on floor descent, and Spirit Call reuses the existing nova-slot mana cost / cooldown so the action bar stays balanced. Committing to the Spirit branch visibly scales the summon instead of awarding flavor-only stat bonuses.

### Added
- Three unkillable owls seems a bit excessive but let's go with that 
- `Familiar` actor in `models.py` (position, HP, attack cooldown, sprite variant, lifesteal / unkillable / champion flags) with follow-and-attack AI in `combat.py` (`update_familiars`, `_move_familiar`, `_familiar_attack`, `_familiar_take_damage`, `_familiar_regen`, `_cull_dead_familiars`). The host persists until each familiar is killed or the floor is descended; recasting tops the host up to the build's count and heals existing familiars to full. AI is O(familiar) per frame with no per-frame allocations.
- Two familiar sprite states in `sprites.py`: a small wisp (`_familiar_wisp`, 14x18) before any Spirit skill is chosen, and a big owl (`_familiar_owl`, 26x34 — a round feathered body, two big eye discs, ear tufts, a gold beak, and the spirit-glow eyes) once the Acolyte learns Spirit Call. Prop-scaled so the owl (140x180) reads clearly larger than the pre-skill wisp (80x100). `familiar_frame(variant, elapsed)` selects the state per-summon; deeper Spirit nodes scale stats/count but no longer change the silhouette — the big familiar is always the owl.
- `draw_familiar` in `rendering/effects.py` with a class-colored accent aura, a floating bob, and an injury health bar; depth-sorted alongside actors in `rendering/world.py` (always visible to the summoner, no line-of-sight gate).
- `player_cast_spirit_call` in `combat.py` plus Spirit-branch scaling helpers (`familiar_max_count`, `familiar_stats`, `familiar_variant_for_index`, `familiar_is_champion`, `familiar_damage_type`). Enemy projectiles now intercept familiars that bodyguard the Acolyte.
- Familiar serialization in `save_system.py` (`familiar_to_dict` / `familiar_from_dict`); restored additively. Old saves without `familiars` load cleanly with an empty host (additive; schema version stays `5`).
- `self.familiars` initialized on `Game`, reset on `restart`, floor descent, and `start_story_mode`, and updated each frame in the run loop (`update_familiars`).
- New `tests/test_3_15_summons.py` (14 tests): slot-3 swap, spawn/lifecycle, kill cull, follow-and-attack AI, return-to-player, enemy-projectile damage, Spirit-branch scaling (HP/damage/count/lifesteal/unkillable/champion), lifesteal heal, unkillable floor, two-state sprite selection (small wisp pre-skill / big owl post-Spirit-Call), save round-trip, old-save compatibility, and a full-frame render smoke test.

### Changed
- Acolyte slot-3 is now "Spirit Call" in `skill_names()`, `hud_action_slots()`, and the `K_3` / `ABILITY_3` dispatch (`game.py`, `input.py`). Other classes keep their nova. Spirit Call reuses the nova-slot cost/cooldown and `player.nova_timer`.
- The Spirit branch nodes now augment the familiar instead of being flavor-only: `acolyte_spirit_call` (t1) grows HP/damage and promotes the sprite from the small wisp to the big owl; `acolyte_wraith_host` (t2) grants lifesteal + HP; `acolyte_bone_legion` (t3) adds +1 familiar and damage; `acolyte_wraith_lord` (t4) makes the lead familiar a champion (taunts, +HP/+damage, larger aura — the sprite stays the owl); `acolyte_legion_eternal` (t5) adds +1 familiar and makes the host unkillable (regenerating, HP floored at 1).
- Spirit Call now always recreates the familiar host from scratch on cast: existing familiars are dismissed and a full host is summoned in a ring around the Acolyte's current position, so recasting snaps the owls to where you are and refreshes build stats instead of healing the old host in place.
- The Acolyte Spirit skill route display names and descriptions now describe the actual familiars (wisp / owl) instead of wraiths / skeletal allies: "Spirit Call" (summon a wisp that grows into an owl), "Owl Companion" (was Wraith Host), "Twin Owls" (was Bone Legion), "Owl Lord" (was Wraith Lord), "Eternal Owls" (was Legion Eternal). Internal node keys are unchanged for save compatibility.
- Removed the duplicate shadow on familiar sprites: the per-frame glow ellipse in `sprites.py` (`familiar_animation_frames`) was stacking a second, sharper shadow under the sprite. Familiars now render with a single ground shadow via `draw_shadow()` in `draw_familiar`, matching the player sprite.
- `acolyte_gravebind`'s nova bind retired: the "bound" status now lives only on Spirit Bolt (`player_cast_bolt` already applies it), since the Acolyte no longer casts Blood Nova from the action bar. The Blood-branch nova leech (`_acolyte_nova_leech`) is preserved for direct `player_cast_nova` calls and existing tests.
- Package metadata, `__version__`, save `release`, and version-current tests now target `3.15.0`. Save schema `version` remains `5`.

### Validation
- `python -m compileall src tests` passes.
- `python -m unittest tests.test_3_15_summons` passes (14 tests).
- `python -m unittest discover tests` passes (118 tests).

## 3.14.0 — Special Room Flavor: Bar & Garden

Two new appearance-only special rooms (bar and garden) join the dungeon, giving floors a sense of inhabited, lived-in place beyond the shop and quest chamber. They exist for atmosphere: the player cannot trade with or talk to anyone inside, and they do not change loot, enemies, or progression.

### Added
- `bar` and `garden` special room kinds in `dungeon.py`, registered in `SPECIAL_ROOM_DEFINITIONS` with `door_policy="sealed"` (so the distinct interior wall art always renders) and `spawn_policy="normal"` (hostiles are not cleared — they are appearance-only, not safe refuges). Both roll at 50% chance on every depth, never displace the shop/quest room, never overlap each other or the entrance/stairs room.
- A `IdleNpc` model in `models.py`: a decorative, non-interactable traveler (x/y, kind, name, role, color). The player cannot talk to or trade with them and no interaction hint references them.
- `bar`/`garden` population handlers in `population.py` that may (50% per room, layout-seeded local RNG) place one `IdleNpc` at the room center. Re-running `_populate_special_rooms` is a no-op (guarded against duplicate NPCs). Bar NPCs use warm tavern names; garden NPCs use wandering-pilgrim names.
- Decorative floor art in `rendering/world.py`: `_draw_bar_floor` (warm aged-wood planks with a faint ale spill) and `_draw_garden_floor` (stone barely visible under dense ivy and wandering vines, per-tile-seeded so each garden tile varies), plus `is_bar_tile`/`is_garden_tile` detectors.
- Generalized special-room wall face art: `guest_wall_faces` is now backed by `special_wall_faces`, which returns a `"kind:side"` style for any special-room perimeter wall. `draw_wall_tile_surface`/`_draw_wall_side_face` were refactored to dispatch per kind: quest_room keeps its carved accent band, `bar` gets horizontal wood-plank paneling, `garden` gets moss splotches and a wandering vine. The cap stays normal stone so the art reads only on the interior face.
- `draw_idle_npc` in `rendering/effects.py` reuses the story-guest humanoid sprite with just a floor shadow (no aura, label, or prompt) and is depth-sorted in `draw_world_objects`.
- `idle_npcs` serialized in `save_system.py` via `idle_npc_to_dict`/`idle_npc_from_dict`; restored on load and reset on restart/descend/story-start. Old saves without `idle_npcs` or flavor rooms load cleanly (additive; schema version stays `5`).
- `prewarm_tile_cache` prewarms all wall face styles (None + quest/bar/garden × left/right) and all five floor forms (normal, shop, guest, bar, garden) so the first frame on a floor is hitch-free.
- New `tests/test_3_14_special_room_flavors.py` (10 tests): definitions, ~50% spawn rate across depths, determinism, population-determinism preservation, idle-NPC placement/interactability/spawn-rate, floor+wall detector coverage, save round-trip, pre-3.14 save compatibility, and a full-frame render smoke test.

### Changed
- `Game.__init__`, `RunFlowMixin.restart`/`descend_to_next_depth`, and `StoryRuntimeMixin.start_story_mode` initialize/reset `idle_npcs`.
- Flavor-room rolls use a layout-seeded local RNG (same family as the guest-room planner) so the shared `self.rng` stream — and thus the door pass + enemy/item population — stays byte-for-byte identical to runs without flavor rooms, preserving determinism and save compatibility.
- `tests/test_dungeon_tile_variants.py` prewarm-contract assertions updated: wall cache now holds `DUNGEON_WALL_VARIANTS * 7` style variants and floors `DUNGEON_FLOOR_VARIANTS * 5` forms (stairs unchanged at `* 2`).
- Package metadata, `__version__`, save `release`, and version-current tests now target `3.14.0`. Save schema `version` remains `5`.

### Validation
- `python -m compileall src tests` passes.
- `python -m unittest tests.test_3_14_special_room_flavors` passes (10 tests).
- `python -m unittest discover tests` passes (104 tests).

## 3.13.1 — Test Suite Trim

Reduced the automated test suite to roughly a third of its size and runtime without losing behavioral coverage, addressing the accumulated redundancy from milestone-based test files.

### Changed
- Deleted superseded/redundant test modules: `tests/test_shops.py` (covered by `test_3_13_special_rooms.py`), `tests/test_guest_room.py` (covered by special-rooms + story-mode tests), `tests/test_web_server.py` (experimental web build; not run by default per the agent brief), `tests/test_dark_floor_overlays.py` (covered by `test_dark_levels.py`), and `tests/test_menu_rendering.py` (covered by menu/pause tests).
- Trimmed every remaining milestone and large test module to its most representative, high-value assertions: `test_3_9_input_accessibility` (64→14), `test_skill_points_and_combo_bonus` (16→5), `test_3_11_cutscene_cleanup` (13→5), `test_3_7_skill_path_variability` (13→5), `test_story_mode` (12→5), `test_3_6_affix_builds` (9→4), `test_3_9_big_bosses` (9→4), `test_movement_animation` (9→4), `test_dungeon_tile_variants` (8→4), `test_skill_tree_choices_and_menu` (8→4), `test_3_13_special_rooms` (8→5, save-compat guards retained), `test_core_gameplay_regression` (7→4), `test_cutscene_schema_and_render` (6→3), `test_dark_levels` (5→3), and several smaller modules.
- Removed now-unused imports and orphaned helpers left behind by deleted tests.
- `README.md` focused-module example updated to reference `tests.test_dark_levels`.

### Validation
- `python -m compileall src tests` passes.
- `python -m unittest discover tests` passes (94 tests, ~7.4s) down from 262 tests / ~19.6s.

## 3.13.0 — Special Rooms Abstraction

Shop rooms and quest guest rooms now share a small data-driven special-room layer so future room identities such as NPC homes, bars, inns, gardens, and faction hideouts can be added without bespoke dungeon indexes or population paths.

### Added
- `SpecialRoomDefinition` and `SpecialRoom` models in `models.py` capture room kind, display name, tags, door/spawn policies, depth constraints, reserved tiles, anchors, and primitive state in a save-friendly format.
- `Dungeon.special_rooms` is now the primary special-room API, with helper lookups for kind, index, and tags. Legacy `shop_room_index` and `guest_room_index` properties remain as compatibility shims backed by the new collection.
- A special-room planner in `dungeon.py` assigns initial `shop` and `quest_room` rooms once per floor, enforces non-overlap, avoids start/stairs rooms, keeps deterministic guest-room selection, and applies per-room door policies.
- `population.py` now dispatches special-room population through registered handlers keyed by room kind. Built-in handlers cover `shop` and `quest_room`, and future room kinds can register a handler without changing dungeon generation.
- Generic rendering helpers in `rendering/world.py` resolve special-room bounds and floor tiles by kind/tag while preserving existing shop floor tint/gold scatter and guest-room floor/wall presentation.
- Save/load now serializes `special_rooms`, migrates old saves containing only `shop_room_index` / `guest_room_index`, and tolerates unknown special-room kinds as no-op data.
- New `tests/test_3_13_special_rooms.py` covers deterministic assignment, non-overlap, door policies, shop/quest behavior parity, generic lookup helpers, legacy-save migration, unknown-kind no-op loading, and stub future-room handler extensibility.

### Changed
- Shop and quest guest rooms both use the special-room handler path for occupant placement, hostile/trap cleanup, anchors, and room-specific dressing.
- Door interaction copy now refers to generic special rooms rather than shop-specific side rooms.
- Package metadata, `__version__`, save release strings, and version-current tests now target `3.13.0`. Save schema `version` remains `5` because the new room collection is additive and old saves migrate defensively.

### Validation
- `python -m compileall src tests` passes.
- `python -m unittest tests.test_3_13_special_rooms` passes (8 tests).
- `python -m unittest tests.test_shops tests.test_guest_room tests.test_story_mode tests.test_dungeon_tile_variants` passes (26 tests).
- `python -m unittest discover tests` passes (262 tests).

## 3.12.0 — Relic & Guest Rooms, Game Logo

The story-relic and quest-NPC sprites were rebuilt as detailed procedural templates, story floors now reserve a dedicated guest room (mirroring shop rooms) where the NPC and relic always spawn at the center, and the octahedron relic became the game's logo/icon.

### Changed
- Story relic sprite replaced with a faceted octahedron cut-gem, authored at low resolution in `sprites.py::_story_relic` and routed through the shared prop pipeline (outline + nearest-neighbor upscale + animation frames). `draw_story_relic` now blits the atlas frame recolored with the per-story accent via an additive blend, with bob/tilt, an accent floor glow, a contact shadow, and attendant motes. The old inline flat-diamond + status-sigil drawing was removed.
- Quest NPC (`_story_guest`) rebuilt as a detailed humanoid template: wide-brimmed hat with a gold band, distinct face with glowing sigil eyes, separate arms with hands, two distinct legs with knee patches, and boots — authored on the shared 26x34 actor canvas. The palette was desaturated from neon violet to a muted dusty-mauve traveler's robe, and `draw_story_guest` no longer applies the additive full-sprite tint or the bright pulsing floor halo that made the guest glow; it now renders like a normal actor with only a faint floor marker.
- On every story-beat floor, `Dungeon` reserves a dedicated `guest_room_index` (mirroring `shop_room_index`): an eligible room is sealed with doors via `_seal_room_with_doors` regardless of the random door chance. `run_flow` passes `guest_room=story_beat_index_for_depth(...) is not None` to `Dungeon`.
- New distinct guest-room art in `rendering/world.py`: `is_guest_tile`/`_guest_room_bounds` (interior floor only, cached per frame) plus `guest_wall_faces` (which visible side face of a perimeter wall borders the room interior) route floor and wall tiles to new `_draw_guest_floor` (a dim consecrated slab with a low-contrast accent-diamond insignia and lit lip) and a per-face wall treatment (cooler/darker stone with a carved accent band). The distinct wall art now appears **only on the interior face** of perimeter walls (north walls show it on the left/+y face, west walls on the right/+x face); the cap and outside faces stay normal stone so the markings never show on the room's exterior. `tile_surface` cache key extended to a 6-tuple `(theme, tile, seed, shop_floor, guest, wall_guest_face)`; `prewarm_tile_cache` also pre-generates both wall face variants ("left"/"right") and the guest floor.
- `_populate_story_guest` places the guest at the guest-room center, and `story_relic_location_for_choice` always places the relic adjacent to the guest-room center (never stacking on the NPC) for all three choices; fallbacks preserved for non-guest floors. `drop_position_near` gained `exclude_origin` so the aid relic lands on an adjacent tile.
- The guiding-light crack is now per-tile visibility-clipped so it never paints over dark/unrevealed floor, and renders whenever a relic target exists (the previous sight-radius gate kept it from drawing when the relic was far away, defeating its purpose).
- The guest's floating "?" portrait badge (which sat on top of the co-located relic on aid floors) was removed; the floor ring, sprite, and proximity label still identify the guest.
### Added
- Game logo/icon: the octahedron relic rendered natively at sizes 16/32/64/128/256/512 into `src/arch_rogue/assets/icons/` (via `gen_icon_assets.py`), bundled as package data. `arch_rogue/icon.py` loads them via `importlib.resources` (works under install and pygbag). `Game.__init__` sets the window/taskbar icon (`pygame.display.set_icon`); the title-screen ornament now uses the octahedron logo as its center crest across all menus (with a small-diamond fallback if assets are missing).
### Validation
- `tests/test_guest_room.py` (new) covers guest-room sealing, `is_guest_tile` markers, guest-at-center, relic-near-center after aid, guest tile surfaces, and save roundtrip.
- `tests/test_dungeon_tile_variants.py` prewarm counts updated (walls x2, floors x3, stairs x2) for the new guest variants.
- `tests/test_story_mode.py` relic-choice test updated for the new guest-room-center placement (defy no longer sends the relic to the final room; the guidance route crosses the sealed guest-room door).
- `python -m compileall src tests` and `python -m unittest discover tests` pass (254 tests). Save schema `version` is unchanged (5); `guest_room_index` defaults to `None` on old saves.
- Package metadata, `__version__`, save release strings, and version-current tests now target `3.12.0`.

## 3.11.0 — Cutscene Cleanup

The quest cutscene stage was visually cluttered and its actors were mis-sized: transparent overlay blobs stacked on the set, player/enemy sprites dwarfed the stage, and the "depth" of the scene read flat. The stage is now a cleaner cursed-theater set with real perspective and a choreographed duel.

### Changed
- Removed the unused stage-overlay rendering functions in `rendering/story_overlays.py` (`draw_cutscene_memory_ribbon`, `draw_cutscene_story_backdrop`, `draw_cutscene_theme_motifs`, `draw_cutscene_relic_silhouette`, `draw_cutscene_faction_sigil`, `draw_cutscene_choice_tableau`, `draw_cutscene_narrator_wave`). These were never called from the active render path but carried most of the transparent ellipse/circle/polygon clutter drawn on top of the stage; deleting them removes that dead code and its visual noise.
- All remaining transparent ellipses/circles have been stripped from the active stage render path: actor ground shadows, the speaker glow halo, the backdrop radial vignette and accent halo, the candelabra flame halos, the altar glow rings, the duel clash-flash rings, the relic aura (now a thin outline ring), and the relic/guest/antagonist pose-effect ring/mote circles (pose emphasis is now crisp line work only — slashes, surges, crown silhouettes).
- Replaced the entire old lighting system (`draw_stage_lights` spot/cone/wash/beam with stacked translucent glow circles and beam polygons, `draw_stage_ambient` mote/dust/ember/spark/leaf/snow/ash particle circles, and `draw_stage_footlights` circle halos) with a single new simplified `draw_stage_lighting` pass: a cached top-down warm key-light gradient, a soft accent-tinted floor pool, and one thin flickering footlight strip with a crisp iron lip. No ellipses, no glow circles — just smooth band gradients and a line. The unused `brazier`/`throne`/`crate` prop painters (never placed by any cutscene JSON) were also removed.
- Stage actors are now sized by perspective, not by a flat UI-scale multiplier. A new `_stage_actor_depth_scale(y)` maps each actor's normalized stage y onto the floor plane (`STAGE_FLOOR_TOP`..1.0) so figures near the back wall render smaller and figures near the front render larger. Sprite height is grounded in `stage_rect.height * STAGE_ACTOR_HEIGHT_FRAC` so sprites never tower over the stage at any UI scale, fixing the oversized-sprite problem.
- Cutscene actors are now depth-sorted back-to-front by stage y (plus animation dy) before drawing, so nearer figures correctly occlude further ones and the perspective reads.
- The player and antagonist now duel on the omen stage. When a cutscene casts both a `player` and an `antagonist` actor, `_cutscene_duel_state()` choreographs a looping cycle (approach -> clash -> retreat -> rest) on its own clock, independent of narration progress: they run at each other, clash in the middle with a cross-slash flash (`_draw_duel_clash_flash`), retreat to their marks, pause, and repeat. The antagonist is made clearly visible during the duel. Cutscenes without an antagonist (e.g. `story_guest_dialogue`) are unaffected.
- The central altar is now a solid obstacle the duelers must route around. `_cutscene_duel_obstacle()` detects any stage prop whose x sits between the duelers (the omen altar at center stage), and the choreography sends the player and antagonist to opposite sides of it, clashing just in front of it (`STAGE_DUEL_OBSTACLE_CLEAR` / `STAGE_DUEL_DETOUR_FORWARD`). Neither dueler ever crosses the altar's x, so it reads as unpassable instead of something they walk through. The duel state now also drives a per-frame dy (the duelers step forward to get around the altar and grow as they come toward the front, reinforcing the perspective).
- `draw_cutscene_actor` was refactored to resolve the animation frame plus duel override once, then delegate to a new `_render_cutscene_actor` helper shared with the depth-sorted stage path. `draw_intro_stage_actor` (story intro panel) received the same depth/sizing cleanup so the intro tableau matches the main stage.
- Package metadata, `__version__`, save release strings, and version-current tests now target `3.11.0`. The save schema `version` is unchanged (5).
- Narrator typewriter speed increased to 2.25x overall (1.5x, then another 1.5x) via the `CUTSCENE_NARRATION_SPEED` multiplier in `StoryRuntimeMixin`; `cutscene_narration_char_delay` divides every per-character delay by this factor, so cutscene lines finish 2.25x faster than the original baseline.

### Validation
- `tests/test_3_11_cutscene_cleanup.py` (new) covers removal of the unused overlay/lighting/ambient/footlight/prop functions, the depth-scale perspective curve, that `draw_stage_lighting` draws zero ellipses and zero circles, static lighting-layer caching, the duel state being absent without an antagonist, the approach/clash/retreat/rest choreography and meeting-point math, duel loop periodicity, clash-flash safety outside the clash window, and a full render pass across a duel cycle with a bounded stage cache.
- `python -m compileall src tests` and `python -m unittest discover tests` pass (the one remaining `test_story_mode` failure is pre-existing on `master` and unrelated to this milestone).

## 3.10.0 — Build Diversity and Affix Depth

Loot rolls now carry clearer build identities: speed, proc, sustain, thorns, damage-type, and skill-modifier affixes are data-driven, affect combat resolution, and surface readable hints in the inventory.

### Added
- Expanded `src/arch_rogue/content/equipment.py` with data-driven `AffixDefinition` and `UniqueItemDefinition` tables, rarity-scaled affix roll ranges, speed/proc/lifesteal/thorns fields, and archetype-specific unique chase items for Warden, Rogue, Arcanist, Acolyte, and Ranger builds.
- Combat synergy hooks in `src/arch_rogue/combat.py`: attack speed and cast speed reduce action cooldowns, movement speed affects traversal, lifesteal heals from damage dealt, proc-on-hit rolls ignite/chill/poison/snare/smite/chain effects, Bolt/Nova modifiers change spell resolution, and thorns reflect melee damage.
- Inventory readability in `src/arch_rogue/inventory.py` and `src/arch_rogue/menus/inventory.py`: one-line build relevance hints, tag-icon tooltip rows, expanded affix/stat tooltips, and Legendary-aware sorting.
- Save migration for expanded item fields (`affix_tags`, speed stats, thorns, lifesteal, proc chance) with no-op defaults for older saves.
- New `tests/test_3_6_affix_builds.py` coverage for affix roll ranges, combat synergy, unique-item generation, cursed tradeoffs, inventory hints, and old-save migration.

### Changed
- `population.py` equipment generation now consumes the affix/unique tables instead of hardcoded inline affix tuples, keeping loot tuning centralized and easier to expand.
- Cursed equipment remains tempting but now has explicit handling tradeoffs alongside its hotter stat rolls.
- Inventory affix tag chips are now drawn as procedural vector icons (matching the project's pixel-art style) instead of font glyphs, so they render reliably on any system including headless and web builds. Chip rows wrap inside the selected-item card, and shared menu text is clipped to stay inside inventory and character panels.
- Package metadata bumped to `3.10.0`.

### Validation
- `python -m compileall src tests` passes.
- `python -m unittest tests.test_3_6_affix_builds` passes (6 tests).
- `python -m unittest discover tests` passes (233 tests).

## 3.9.0 — Controller, Input, and Accessibility Polish

The control layer was keyboard-and-mouse only. Gamepad support is now first-class across gameplay and every menu, keyboard and controller share the same navigation bindings, and the last-used controller is remembered across sessions.

### Added
- New `src/arch_rogue/input.py` input abstraction: a `Command` vocabulary (move, aim, ability, interact, navigate, confirm, back, tab), keyboard/gamepad-to-command mapping tables, and a `ControllerManager` owning joystick lifecycle, hot-plug, device selection, and allocation-free per-frame axis polling.
- Full `pygame.joystick` controller support: left stick movement, right stick aiming, context-aware button maps for combat abilities (A/X/Y/LT/LB/RB/RT), D-pad and face-button menu navigation, interaction, inventory/shop/character-sheet navigation, tab cycling, and story-relic/cutscene choices.
- Auto-detect gamepad connect/disconnect (`JOYDEVICEADDED` / `JOYDEVICEREMOVED`) with the last-used device persisted by GUID to `~/.arch_rogue_options.json` and reclaimed when it hot-plugs back in.
- Unified menu navigation: every navigable menu (title, options, archetype select, inventory, shop, character sheet, run-state overlays) supports the same directional/confirm/back/tab bindings on both keyboard and gamepad via a single `_dispatch_command` path.
- Options menu gained a cursor (arrow keys / D-pad move focus, Enter activates, Left/Right adjust), a Controls & gamepad mapping page, and a Controller row to enable/disable gamepad input; legacy direct keys (A/M/F/D/+/-/O) still work.
- Character skill-tree controller cursor: D-pad/left stick navigates nodes, the selected node reuses the existing hover preview/highlight, and A/confirm spends a skill point on an available node.
- Analog movement: stick deflection past the radial deadzone scales movement speed (creep vs. sprint) while keyboard diagonals stay full speed.
- Robust stick/trigger detection: rest-value sampling distinguishes analog sticks from triggers, so right-stick aim and LT/RT actions read correctly across Xbox-raw, Stadia/PS, and 4-axis layouts without relying on the SDL controller DB.

### Changed
- `combat.py` `update_player` / `update_player_aim` merge controller axes into the existing keyboard/mouse polling; keyboard and mouse behavior is unchanged when no controller is connected.
- `Game.handle_events` routes joystick events through `InputMixin.handle_controller_event`; keyboard KEYDOWN handling is otherwise untouched so all legacy bindings persist.
- Options schema bumped to v3 (adds `controller_enabled` and `last_controller_guid`); older v2 saves load with safe defaults (controller on, no preferred device).
- Options menu: Enter now activates the focused row (consistent confirm); Backspace / O / Esc still return to title.
- Controller buttons are now context-sensitive: A confirms in menus/cutscenes but attacks in gameplay; X/Y select skills in gameplay and quick-pick story choices in cutscenes; B skips/closes cutscenes and mandatory story intro selects the highlighted/default relic option.

### Validation
- `python -m compileall src tests` passes.
- New `tests/test_3_9_input_accessibility.py` (49 tests) covers input mapping, controller axis/trigger layout and deadzone, contextual button maps, hot-plug and GUID preference, unified command dispatch across all menus, character skill-tree cursor/upgrade, gameplay ability wiring, fresh right-stick projectile aim, existing aim-cone projectile aim when the stick is neutral, right-stick aim preservation while moving, cutscene selection/skip, analog movement/aim integration, controls page rendering, and options persistence/migration.
- `python -m unittest discover tests` — 210 tests pass.

## 3.8.5 — Big Bosses: 4-Tile Gatekeepers, Sealed Arenas, Boss Bar

Bosses were single-tile enemies with a tougher stat block and a generic sprite. The final gate tyrant and named floor guardians are now hulking 4-tile set-piece encounters that lock the room down when you enter and only reopen the doors when the boss is dead.

### Added
- `Enemy.size` field (tile footprint side; 1 = normal, 2 = 2x2 / 4-tile boss) plus `Enemy.is_boss_encounter` (final boss or `floor_boss` role). `size` defaults to 1 so existing saves load unchanged.
- `BOSS_FOOTPRINT`, `BOSS_FOOTPRINT_HIT_RADIUS` (0.92), and `BOSS_FOOTPRINT_MOVE_RADIUS` (0.82) constants for the larger silhouette.
- `Dungeon.room_at(x, y)`, `Dungeon.seal_room_openings(room)`, and `Dungeon.restore_tiles(sealed)` helpers for the boss-arena door logic.
- `RunFlowMixin.active_boss`, `update_boss_encounter`, `seal_boss_room`, and `unseal_boss_room` plus `boss_engaged` / `boss_sealed_room_index` / `boss_sealed_tiles` game state: entering the boss room seals every perimeter opening into a closed door, killing the boss restores the originals exactly.
- A dedicated large boss sprite `_gate_tyrant` in `sprites.py` (40x52 raw): crowned great-helm with plague horns, rune-glow visor eyes, segmented plate with a glowing chest rune, spiked pauldrons, tattered cloak, greaves with shin-glow, and a towering greatblade. Registered as the `"Gate Tyrant"` enemy with its own animation frames and selected via the new `sprites.boss_frame(...)` helper.
- `tests/test_3_9_big_bosses.py` covering boss size/hit-radius, harder stat blocks, extended melee reach, door seal/unseal, the 3-bolt fan, challenge-miniboss exclusion, and old-save compatibility.

### Changed
- Floor guardians (`_make_floor_boss`) and the final tyrant (`_make_boss`) are now `size=2` with much higher HP (~1.85x / ~2.4x), heavier hits (+6 / +9), faster cooldowns, longer reach, wider aggro, and stronger resistances so each boss fight is a real gate-seal encounter.
- `CombatMixin.enemy_hit_radius` returns `BOSS_FOOTPRINT_HIT_RADIUS` for `size >= 2` actors.
- `CombatMixin.move_actor` probes collision with `BOSS_FOOTPRINT_MOVE_RADIUS` for big bosses so they don't clip walls; other actors keep the tight default.
- `CombatMixin.enemies_in_melee_arc` extends melee reach by the enemy's extra hit radius so a 4-tile boss is hittable from its silhouette edge, not just its center.
- `CombatMixin.update_enemies` routes `is_boss_encounter` enemies through the boss combat pattern (close, cast fan at mid-range, crush with melee up close).
- `CombatMixin.enemy_cast` fires a 3-bolt fan for `size >= 2` bosses instead of a single projectile, forcing lateral dodges.
- `CombatMixin.kill_enemy` scales death/burst impact radii with `size` and adds a screen flash + "Guardian fallen" floater + boss sfx for floor-guardian takedowns.
- `rendering/actors.py` `draw_enemy`: big bosses use the Gate Tyrant sprite scaled up further, a 78px shadow, a 96px gilded floating health bar, a 132x52 aura, and larger telegraph/elite markers.
- `rendering/hud.py` `draw_boss_bar`: wider/taller banner bar (640px) for 4-tile bosses with a role subtitle and quarter tick marks; the bar now targets floor guardians too.
- `interactions.boss_enemy()` returns the active floor guardian or final boss (was final boss only).
- `sprites.enemy_key` routes `kind == "boss"` to `"Gate Tyrant"` (was `"Gate Warden"`).
- Keyboard/mouse bindings, run-save compatibility, and the stable `Game` / `main` entry points are unchanged. The new `Enemy.size` field defaults to 1 so older run saves restore without migration.
- Version metadata (`__version__`, `pyproject.toml`) bumped to `3.8.5`.

### Validation
- `python -m compileall src` clean.
- `python -m unittest tests.test_3_9_big_bosses` — 6 tests pass.
- `python -m unittest discover tests` — 160 tests pass.
- Headless smoke harness confirmed: floor guardian and final boss spawn at size 2, doors seal (34 perimeter tiles → CLOSED_DOOR) on room entry, doors restore on boss death, and the boss cast spawns a 3-projectile fan.

## 3.8.4 — Archetype-Specific Bolt & Nova Graphics

Bolt and nova cast effects were a single generic arcane ring for every class. The emanation graphic and the bolt projectile are now themed per archetype so each class reads distinctly the moment a skill fires.

### Added
- `ImpactEffect.archetype` and `Projectile.archetype` fields tag the class that produced a cast impact / player bolt so the renderer can theme them without branching on ownership.
- Per-archetype player bolt sprites in `sprites.py`: Warden `_guard_bolt` (holy hammer of light), Rogue `_throwing_dagger` (poisoned blade), Acolyte `_spirit_bolt` (wraith-skull bolt), Ranger `_arrow_bolt` (feathered arrow). Arcanist reuses the existing arcane `_blue_bolt`. `projectile_frame(owner, elapsed, archetype=...)` selects the class sprite for player bolts and falls back to the owner-keyed sprite otherwise.
- `_draw_cast_emanation` dispatcher plus four new emanation renderers in `rendering/effects.py`:
  - **Warden** — `_draw_cast_warden`: expanding golden bulwark wave, radiating light rays, holy sigil core.
  - **Rogue** — `_draw_cast_rogue`: smoke/poison burst of expanding puffs with poison wisps (no clean ring).
  - **Acolyte** — `_draw_cast_acolyte`: dark crimson ring, blood droplets radiating outward, shadowed blood-heart core.
  - **Ranger** — `_draw_cast_ranger`: green snare-vine ring with thorn/leaf accents and rooting lines spreading outward.
  - **Arcanist** (default) — unchanged magical ring with orbiting runes.

### Changed
- `CombatMixin.player_cast_bolt` / `player_cast_nova` now pass `archetype=self.player.class_name` into the cast `ImpactEffect`, and `player_cast_bolt` tags each `Projectile` with the class so the bolt sprite matches.
- `Game.add_impact` accepts an `archetype` keyword and forwards it to `ImpactEffect`.
- `draw_projectile` forwards `projectile.archetype` to `sprites.projectile_frame`.
- Nova impacts already use a larger radius/ttl than bolt, so the new emanations scale up automatically for nova and down for bolt without per-class tuning.
- Removed the four generic directional `SlashEffect`s `player_cast_nova` used to spawn around the player. They were the old placeholder nova sweep visual and are now superseded by the per-archetype emanation ring, so nova no longer doubles up two overlapping effects. The slash system itself is unchanged (melee still uses it).
- Keyboard/mouse bindings, run-save compatibility, and the stable `Game` / `main` entry points are unchanged. The new model fields default to empty strings so older saves / impacts keep rendering via the Arcanist/default path.
- Version metadata (`__version__`, `pyproject.toml`) bumped to `3.8.4`.

### Validation
- `python -m compileall src` clean.
- `python -m unittest tests.test_world_rendering_and_animation tests.test_combat_damage_and_loot_tables tests.test_3_8_graphics` — 11 tests pass.
- `python -m unittest discover tests` — 154 tests pass.
- Headless render harness cycled bolt + nova casts for all five archetypes (Warden, Rogue, Arcanist, Acolyte, Ranger) and confirmed each archetype-specific emanation and bolt sprite draws without errors.

## 3.8.3 — Enemy Line-of-Sight Fix

Enemies were aggroing and attacking the player purely on Euclidean distance, so a foe on the far side of a wall could melee or cast through it. Combat now requires an unobstructed line of sight before an enemy may attack.

### Added
- `Dungeon.line_of_sight(x0, y0, x1, y1)` traces the straight line between two world points and returns `False` when a wall / closed door blocks it. Sampling step is <= 0.25 tile so no 1-tile wall can be skipped between samples; endpoints are excluded so actors do not block themselves.

### Changed
- `CombatMixin.update_enemies` now computes `has_los` per enemy per frame and gates every attack branch on it: boss melee/cast, ranged cast, and standard melee. Movement is intentionally not gated so pursuit around corners still works once an enemy has aggro'd.
- Projectiles already collided with walls, so ranged bolts were not changed; only the cast trigger is now LOS-gated.
- Version metadata (`__version__`, `pyproject.toml`) bumped to `3.8.3`.

### Validation
- `python -m compileall src tests` clean.
- `python -m unittest tests.test_enemy_los_walls` — 3 new tests cover `line_of_sight` blocked/clear, melee-through-wall blocked, and ranged-cast-through-wall blocked.
- `python -m unittest discover tests` — 154 tests pass.

## 3.8.2 — Pause on Inventory / Character Sheet

Opening the inventory or character sheet now pauses the run so players can inspect their build without being attacked or sliding around.

### Changed
- `Game.update` now early-returns (after floaters and animation-phase tick) when `inventory_open` or `character_menu_open` is set, skipping `update_player_aim`, `update_player`, `update_camera`, `update_revealed_tiles`, `update_enemy_statuses`, `update_enemies`, `update_projectiles`, `update_traps`, and `update_secrets`.
- Visual floaters and animation phases still advance so the overlay does not look frozen, mirroring the existing `story_intro_pending` pause path.
- Keyboard/mouse bindings, run-save compatibility, and the stable `Game` / `main` entry points are unchanged.
- Version metadata (`__version__`, `pyproject.toml`) bumped to `3.8.2`.

### Validation
- `python -m compileall src tests` clean.
- `python -m unittest tests.test_pause_on_menus` — 4 new tests cover inventory pause, character-sheet pause, projectile freeze, and resume-after-close.
- `python -m unittest discover tests` — 151 tests pass.

## 3.8.1 — Number-Only Skill/Potion Hotkeys

Consolidates combat inputs so skills and potions are triggered exclusively through the number keys that the HUD action bar already advertises, removing the legacy duplicate hotkeys.

### Changed
- `Game.handle_events` no longer binds skill/potion actions to `Space` (melee), `F` (bolt), `V` (nova), `Left Ctrl` (dash), `R` (health potion), or `T` (mana potion) during play. These are now reachable only via the action bar's number keys: `1` melee, `2` bolt, `3` nova, `4` dash, `5` health potion, `6` mana potion.
- Non-skill bindings (`E` interact, `Q` quest HUD, `C` character sheet, `R` return-to-archetype outside play, `I` inventory, `H`/`?` help) are unchanged.
- Character sheet skill legend (`menus/character.py`) now lists `1/2/3/4` instead of `Space/F/V/Ctrl`.
- Help overlay and About screen (`menus/title.py`) updated to describe the number-key combat bindings and dropped the `R`/`T` potion references.
- HUD cooldown pips (`rendering/hud.py`) now label skills `1/2/3/4` to match the action-bar hotkeys instead of the old `M/B/N/D` letters.
- Version metadata (`__version__`, `pyproject.toml`) bumped to `3.8.1`.

### Validation
- `python -m compileall src tests` clean.
- `python -m unittest tests.test_core_gameplay_regression` — hotkey behaviors updated to drive nova via `3`, dash via `4`, and health potion via `5`.
- `python -m unittest discover tests` — 147 tests pass.

## 3.8.0 — Graphics Upgrade: Lighting

Milestone 3.8 makes darkness the default dungeon state and adds fog-of-war memory to the light floors that remain, so exploration feels like a dark-fantasy crawl instead of a fully-lit map.

### Added
- `LIGHT_LEVEL_SIGHT_RADIUS` constant (7.0) — the live sight radius on light floors, wider than the dark-floor lantern radius (`DARK_LEVEL_LIGHT_RADIUS` 4.0) so light floors stay forgiving to explore.
- Fog-of-war tile memory in `run_flow.py` (`revealed_tiles`, `reset_revealed_tiles`, `update_revealed_tiles`, `is_tile_revealed`). On light floors, tiles within the sight radius are remembered for the rest of the floor; terrain stays revealed after the player moves away. Dark floors keep their lantern-only model and never build memory (explored areas stay dark).
- `Game.update()` now runs the per-frame reveal pass so a freshly-entered light floor is populated immediately and memory grows as the player explores.

### Changed
- `generate_floor_plan` now treats floors as dark by default. `light_depths_for_run` selects the light exceptions via a depth-driven probability ramp so the run eases in and darkens as it deepens: depths 1-3 are always light (gentle opening), depths 4-6 are 50% dark, and depths 7+ are 75% dark.
- `can_see_world_position` now gates live objects on both floor types: the lantern radius on dark floors and the wider sight radius on light floors. Terrain memory (`revealed_tiles`) is separate from live-object sight, so a remembered tile no longer shows the enemies/items that were there.
- `tile_visibility_alpha` returns 255 for revealed light-floor terrain and 0 for unrevealed terrain (dark floors keep the soft lantern falloff).
- `set_current_floor_dark`/`toggle_current_floor_dark` reset and re-reveal fog-of-war memory so a freshly-toggled light floor starts from the player's current sight instead of stale memory.
- Rendering (`rendering/world.py`) culls unrevealed terrain on light floors the same way it culled beyond-lantern terrain on dark floors, and gates objects/relic guidance through the shared sight check. The now-unused `dark` locals and `DARK_LEVEL_LIGHT_RADIUS` import were removed.
- Run saves now write schema `version` 5 with a compact `revealed_tiles` `[x, y]` pair list. Older saves (1–4) still load; missing memory is repopulated by the next reveal pass so a resumed light floor is never blank.
- Version metadata (`__version__`, `pyproject.toml`) and the release-string-asserting tests now target `3.8.0`.

### Validation
- `python -m compileall src tests` clean.
- `python -m unittest tests.test_dark_levels` — dark-by-default distribution, toggle save roundtrip, dark visibility/enemy navigation/wall hiding, light-floor fog-of-war memory, dark-floor no-memory, and revealed-tiles save roundtrip.
- `python -m unittest discover tests` — 147 tests pass.

## 3.7.5 — Per-Frame Hot-Path Optimizations (browser FPS at full window)

The browser build was unplayable at full-window resolution (`?maxw=1980`) because the per-frame work — running under Pyodide, which is slower than native Python and pays per Python→C call — was too heavy. This release optimizes the profiled hot paths (driven by a `cProfile` harness at 1920×1080 in playing state) without changing gameplay or visuals.

### Changed (optimizations)

- **Line of sight** (`run_flow.has_line_of_sight`): replaced the 8x-oversampled float walk (which called `in_bounds` + `is_floor` ~80 times per query) with a single-cell-per-step integer Bresenham walk that inlines the bounds and passable-tile check. Same blocked-by-wall/closed-door semantics (verified by `test_dark_levels`); ~8x fewer per-query cell checks. `has_line_of_sight_to_player` was already per-frame cached.
- **`Dungeon.is_floor`** (called hundreds of thousands of times per frame): inlined the bounds check (dropping the `in_bounds` method call) and uses a module-level `_PASSABLE_TILES` tuple for the membership test.
- **Floor tile rendering** (`rendering/world.py`): `draw_dungeon` now collects every visible floor/stairs blit into one `Surface.blits()` call instead of ~250 individual `blit()` calls — identical pixels/positions, but one Python→C call instead of ~250 (the big win for call-bound Pyodide), with a defensive loop fallback if `blits` is unavailable. Walls/doors (drawn depth-sorted in `draw_world_objects`) still blit individually, but there are far fewer.
- **Off-screen tile cull**: `draw_tile`/`_tile_blit_entry` skip tiles whose center is outside the viewport, so the `visible_bounds` safety-padding ring no longer pays a blit + tile_seed/tile_surface/shop lookup for off-screen tiles.
- **Dark-floor alpha** (`_alpha_tile_surface`): the dark-floor light falloff previously did `surface.copy(); surface.set_alpha(alpha)` per tile per frame (~289 fresh surface allocations/frame). It now quantizes alpha into 8 buckets and caches one `set_alpha` copy per (surface, bucket), cleared on floor/theme change (`prewarm_tile_cache`). Same falloff look; no per-frame allocations.
- **`font.size` caching** (`rendering/base._text_size`): HUD text wrapping/ellipsizing re-measured the same labels every frame. Now cached by (font, text) with an 8192-entry cap, cleared in `rebuild_fonts` (Font objects are replaced, so `id(font)` keys would otherwise collide). The char-by-char truncation loop stays uncached (its strings are unique).

### Result

- Desktop headless frame at 1920×1080: ~9.2 ms → ~7.6 ms (≈17% faster), with total function calls per run dropping from ~8.27M to ~5.39M (≈35% fewer) — the call reduction matters most under Pyodide, where each Python→C call is the expensive part. Full `unittest discover tests` (141 tests) passes; rendering/LOS/dark-floor behavior is unchanged.

### Validation

- `python -m compileall src web` clean; `python -m unittest discover tests` → 141/141 pass. The rebuilt `assets/main.py` and game source package the optimizations (verified by content check).

### Changed (metadata)

- Version metadata (`__version__`, `pyproject.toml`) and the four release-string-asserting tests now target `3.7.5`. The save schema `version` is unchanged (4). `web/README.md` notes the optimizations and that `?maxw=1980` should now be playable.

## 3.7.4 — Browser Performance: Capped Render Resolution

Browser FPS was poor because the build rendered at the full browser viewport (1920×1080 / 4K), which is the dominant per-frame cost under Pyodide (slower-than-native Python + WASM SDL). pygbag upscales the canvas via CSS for free, so the web build now renders at a **capped internal resolution** that preserves the window's aspect ratio (the canvas still fills the window, no letterboxing) and lets the browser GPU scale it up.

### Added

- Capped render resolution in `web/main.py`: `cap_render_size(w, h, max_long, max_px)` preserves aspect while capping the longer side (default `DEFAULT_MAX_RENDER_LONG_SIDE = 1280`) and total pixels (default `DEFAULT_MAX_RENDER_PIXELS = 1_300_000`), with `MIN_RENDER_W/H = 320/240` floors. `browser_render_size()` returns the capped size (or `None` off-browser); `make_game()` and `maybe_resize_to_browser()` now use it instead of the raw viewport, so the canvas fills the window at a manageable pixel budget. This also cuts the number of dungeon tiles drawn each frame (the camera derives the visible-tile radius from screen size, floored at a small radius).
- URL tuning via `web_config()` (cached): `?maxw=` overrides the long-side cap and `?maxpx=` the pixel cap (e.g. `?maxw=960` for slower devices, `?maxw=99999` to disable the cap and render the full window). Defaults keep a good balance of FPS and readability.
- Throttled the per-frame resize probe: `run_frame` only calls `maybe_resize_to_browser` every 10th frame (resize detection at ~10 Hz is plenty), avoiding a Pyodide↔JS bridge call every frame.
- `tests/test_web_server.py` (now 36 tests, +7): `web_config` defaults off-browser; `cap_render_size` caps the long side preserving aspect (2560×1440→1280×720, 1366×768→1280×720), leaves sub-cap sizes untouched (1024×768, 960×540), clamps to the minimum (200×200→320×240), engages the area cap (2000×2000), disables when both caps are 0, and `browser_render_size` is `None` off-browser.

### Validation

- Bytecode compilation and the full `unittest discover tests` suite (141 tests) pass, including the 7 new render-cap tests. The rebuilt `assets/main.py` packages the cap logic (verified by content check). No `arch_rogue.*` source was modified.

### Changed

- Version metadata (`__version__`, `pyproject.toml`) and the four release-string-asserting tests now target `3.7.4`. The save schema `version` is unchanged (4). `web/README.md` gains a “Performance: capped internal render resolution” section with the `?maxw=` / `?maxpx=` tuning table.

## 3.7.3 — Adaptive Browser Resolution

The browser build now renders at the browser's full available viewport size and re-adapts when the window is resized, instead of a fixed 2560×1440 internal surface letterboxed by pygbag.

### Added

- Browser-aware sizing in `web/main.py`: `browser_window_size()` queries the Pyodide `js` bridge (`js.window.innerWidth/innerHeight`) for the viewport in CSS pixels; `make_game(screen_size=None)` now defaults the display surface to that size (falling back to the `SCREEN_WIDTH×SCREEN_HEIGHT` constants off-browser, so desktop/unit tests are unchanged). `maybe_resize_to_browser(game)` runs at the top of every `run_frame`: when the viewport size differs from the current surface (and is at least 320×240) it calls `pygame.display.set_mode(size, pygame.RESIZABLE)` to resize the backing surface and re-triggers pygbag's CSS fitter (`js.window_resize()`) so the canvas re-fills the window. Off-browser (no `js` module) both helpers are no-ops, so the desktop driver and tests are unaffected.
- The `js` bridge reference is cached (`_get_js()`) so the per-frame sizing probe stays cheap (no per-frame import, one JS attribute read).
- `tests/test_web_server.py` (now 29 tests, +6): `browser_window_size()` is None off-browser; `maybe_resize_to_browser` is a no-op without a browser; resizes to a provider-supplied size (updates `screen` and `windowed_size`); skips unchanged sizes; rejects too-small sizes; `make_game` honors an explicit `screen_size`.

### Why

pygbag fits the canvas CSS to the window while preserving the **backing** surface's aspect ratio (`canvas.width/canvas.height`, set by `pygame.display.set_mode`). With a fixed 2560×1440 (16:9) backing, a non-16:9 window letterboxes. Matching the backing to the window size makes the canvas fill the whole viewport, and resizing the backing on window change keeps it filled.

### Changed

- Version metadata (`__version__`, `pyproject.toml`) and the four release-string-asserting tests now target `3.7.3`. The save schema `version` is unchanged (4).

### Validation

- Bytecode compilation and the full `unittest discover tests` suite (134 tests) pass, including the 6 new resize tests. The rebuilt `assets/main.py` packages the sizing helpers (verified by content check). No `arch_rogue.*` source was modified.

## 3.7.2 — Fully-Vendored Web Build (fixes cross-origin / 404 errors)

The pygbag browser build now runs **fully self-contained and same-origin**: every runtime asset (the `pythons.js` bootstrap, the CPython/Pyodide interpreter `main.js`+`main.data`+`main.wasm`, the vt/vtx/xterm terminals, and static assets) is vendored locally, and the generated `index.html` is rewritten to load from the local `/cdn/0.9.3/...` path instead of the remote `https://pygame-web.github.io/cdn/0.9.3/` CDN. This eliminates the cross-origin-request errors and the `arch_rogue/` + `browserfs.min.js` 404s.

### Added

- `web/vendor_runtime.py`: downloads the complete pygbag/pygame-web runtime tree from the CDN into `web/vendor/cdn/...` (mirroring the CDN path layout) on a one-time ~21 MB pull. Manifest: `pythons.js`, `empty.html`, `empty.ogg`, `cpythonrc.py`, `cpython312/main.js|main.data|main.wasm`, `vt.js`, `vtx.js`, `vt/xterm.js|xterm.css|xterm-addon-image.js`, `cdn/lib/index.html`. Two dead template references (`browserfs.min.js`, `pygbag0.9.3.js`) that 404 even on the official CDN are written as empty local stubs so the `<script>` tags resolve instead of producing console 404s (BrowserFS is not used by the tarball-based app flow). Idempotent (skips existing files), `--force` re-downloads, verifies Content-Length.
- `build.py` now: (1) ensures the vendored runtime is present, (2) runs `pygbag --build`, (3) `rewrite_index_html_local()` replaces every `https://pygame-web.github.io/cdn/0.9.3/` reference with `/cdn/0.9.3/`, (4) `merge_vendor_runtime()` copies `web/vendor/cdn/` into `web/dist/cdn/` so the runtime is served same-origin. New `--no-vendor` / `--force-vendor` flags. `rewrite_index_html_local` and `merge_vendor_runtime` are exposed for testing.
- Repo-root `pygbag.ini` excluding `/.venv`, `/web`, `/tests`, `__pycache__` from the app tarball. Without it pygbag packaged the entire virtualenv + the vendored runtime + the test suite into a **108 MB** tarball; it is now ~220 KB of just the game source.
- **src-layout path bootstrap in `web/main.py`** (fixes the grey screen / `https://pypi.org/simple/arch_rogue/` request): pygbag's tarball flow extracts the app to `<appdir>/assets` and runs `assets/main.py` without putting the project's `assets/src` on `sys.path`. Because Arch Rogue uses a `src/`-layout, `from arch_rogue.game import Game` failed to find the package locally, so Pyodide's PEP-723 auto-installer (`pep0723.py`) fell back to installing `arch_rogue` from PyPI (which 404s) and the canvas stayed grey. `web/main.py` now runs a `resolve_src_paths`/`_bootstrap_arch_rogue_path` hook before importing `arch_rogue`, inserting `assets/src` (resolved from `__file__`, then `cwd`, then the hardcoded pygbag extraction path `/data/data/arch-rogue/assets/src`) onto `sys.path`. The hook is a pure, unit-tested helper so it can be validated without a Pyodide runtime.
- `tests/test_web_server.py` (now 23 tests, +13): vendor `_local_path` mirroring, stub creation without network, force re-run, full manifest completeness (when `web/vendor` is present), `index.html` rewrite (remote→local, no `pygame-web.github.io` left), missing-index, vendor merge into `dist/cdn`, missing-vendor, the `pygbag.ini` exclusion list, the src-path resolver (next-to-main, cwd fallback, dedup), and a build-artifact check that the built tarball's `assets/main.py` contains the bootstrap and that `assets/src/arch_rogue/__init__.py` is packaged.
- `.gitignore` now ignores `web/vendor/` and `web/dist/` (build artifacts; `web/vendor` can be `git add`-ed to commit a fully offline-capable repo).

### Changed

- `web/README.md` rewritten to document the vendored build flow, the `--force` re-vendor path, the troubleshooting section (root causes of the cross-origin/404 errors and how vendoring fixes them), and the tarball-exclusion note.
- Version metadata (`__version__`, `pyproject.toml`) and the four release-string-asserting tests now target `3.7.2`. The save schema `version` is unchanged (4).

### Validation

- Built and served the site: `/`, `/cdn/0.9.3/pythons.js`, `/cdn/0.9.3/cpython312/main.js|main.data|main.wasm`, `/cdn/vt/xterm.js`, `/cdn/0.9.3/browserfs.min.js`, and `/arch-rogue.tar.gz` all return 200 with correct MIME types (`application/wasm`, `application/javascript`, `application/gzip`) and the COOP/COEP isolation headers. No `pygame-web.github.io` references remain in `dist/index.html`.
- Bytecode compilation and the full `unittest discover tests` suite (124 tests) pass, including the 9 new vendor/build tests.

## 3.7.1 — Web Build Target (pygame-web / pygbag)

Arch Rogue can now run in a browser. A new `web/` package adds the pygame-web (pygbag) packaging target and a static host server, without touching `arch_rogue.game.Game`, `arch_rogue.game:main`, the save schema, or the desktop control scheme.

### Added

- `web/main.py`: an async Pyodide entry point that reproduces `Game.run()`'s loop body but `await asyncio.sleep(0)`s after every frame so the browser/Pyodide event loop can pump input and rendering. Exposes `make_game(headless=...)`, `run_frame(game)`, and `main()` for reuse/testing; forces fullscreen off and redirects saves/options to a writable in-browser-FS path (`_writable_home` falls back from `Path.home()` to `/tmp` to `cwd`).
- `web/server.py`: a stdlib `ThreadingHTTPServer` static host that serves the pygbag-built site with the cross-origin-isolation headers Pyodide's threaded runtime needs (`Cross-Origin-Opener-Policy: same-origin`, `Cross-Origin-Embedder-Policy`, `Cross-Origin-Resource-Policy: same-origin`) and correct MIME types for `.wasm`/`.js`/`.data`/`.symbols` (stdlib `mimetypes` returns generic octet-stream for these, which makes Pyodide refuse to instantiate `.wasm`). The COEP policy defaults to `credentialless` (configurable via `--coep`): unlike the stricter `require-corp`, `credentialless` keeps the cross-origin isolation that grants `SharedArrayBuffer` while still permitting cross-origin resources that have not opted into CORP — this is what fixes the "cross-origin request blocked" error on pygbag builds that fetch the Pyodide runtime/fonts from a CDN. `--no-isolation` was replaced by `--coep ""`. CLI: `python web/server.py --directory web/dist --port 8000`.
- `web/build.py`: orchestrator that runs `pygbag --build` against the repo, stages the produced site into `web/dist/`, and optionally starts the server. It temporarily copies `web/main.py` to a repo-root `main.py` (the entry pygbag requires) inside a `finally` block, refuses to clobber an existing `main.py`, and searches for the produced `index.html` across pygbag's varying output layouts.
- `web/README.md`: setup, build, serve, and limitations (fullscreen disabled in-browser, saves are session-scoped until an IDBFS store is mounted, audio is best-effort, pygbag is build-time only).
- Optional `[project.optional-dependencies] web = ["pygbag"]` extra in `pyproject.toml` so the web packaging tool is installable on demand without adding it to runtime dependencies.
- `tests/test_web_server.py` (10 tests): server MIME types (`application/wasm`, `application/javascript`), COOP/COEP/CORP headers with the `credentialless` default, the `require-corp` opt-in, COEP-off behavior, invalid-coep validation, index.html serving, plus the async driver's `_writable_home`, `make_game(headless=True)` (forces fullscreen off, correct 2560×1440 surface), and a single `run_frame` tick.

### Validation

- Bytecode compilation and the full `unittest discover tests` suite (113 tests) pass, including the 8 new web tests. Desktop behavior and save compatibility are unchanged: no `arch_rogue.*` source was modified.

## 3.7.0 — Skill-Path Variability Update

Milestone 3.7 forces meaningful specialization: a run may commit to at most two skill-tree branches, and each branch now changes how an ability *plays* rather than just bumping its damage. Base (un-upgraded) abilities are deliberately weaker so committing to a path feels essential, and branch capstones deliver a marquee mechanical flourish (homing bolts, piercing shots, chain lightning).

### Added

- Two-branch commitment limit. New `content/progression.py` helpers — `MAX_COMMITTED_BRANCHES` (=2), `committed_branches(acquired, archetype)`, `is_branch_locked(acquired, archetype, branch)`, and `branch_progress(acquired, archetype, branch)` — derive commitment purely from acquired node keys, so no save-schema change is needed (committed branches are recomputed from `player.skill_upgrades`). Exported through the `arch_rogue.content` facade.
- Branch-locking in the combat layer: `available_skill_choices()` excludes nodes in sealed branches, `choose_skill_upgrade()` rejects them, and `skill_node_state()` returns a new `"branch_locked"` state (distinct from prereq-`"locked"`) so the menu can render the two reasons differently. Already-committed branches keep progressing even if a legacy save pre-dating the limit acquired nodes in 3+ branches; only *new* commitments are blocked.
- Projectile mechanics for branch progression: `models.Projectile` gained `pierce` (extra enemies a bolt passes through, damage ×0.7 to subsequent foes), `homing` (0..1 steering toward the nearest enemy each frame), and a `hit_enemies` set so a piercing bolt never double-hits one foe. `combat.py` `update_projectiles` steers homing bolts, applies pierce, and arcs Storm-branch chain lightning from a struck foe to a nearby second target.
- Character-sheet rendering of the commitment system: a always-on commitment strip (`Committed X/2 paths`), branch headers dimmed and `[lock]`-tagged for sealed routes, a `"Sealed"` legend swatch with a dim-red node wash, and a hover hint explaining the branch seal.
- Focused `tests/test_3_7_skill_path_variability.py` (13 tests) covering the helper math, the choose/state enforcement, the Arcanist Arc Bolt single→multi→pierce→homing progression, Ranger Multishot single→fan→homing, projectile pierce pass-through, Warden cleave gating, Rogue crit gating, Acolyte lifesteal gating, and Arcanist Frost Nova radius gating.

### Changed

- **Arcanist Arc Bolt** is the flagship rework and now ramps gradually: a single bolt by default; `arcanist_splinter` (Bolt t1) adds one shard (2 bolts); `arcanist_overload` (Bolt t2) splits into a 3-bolt fan and grants pierce 1; `arcanist_pierce` (Bolt t3) ramps pierce to 2; `arcanist_arc_tyrant` (Bolt capstone) makes bolts homing (seek nearest foe); `arcanist_chain_lightning` (Storm t2) arcs a chain to a second target on hit. The old always-on 2-bolt base was removed so the Bolt path is what makes Arc Bolt multi-shot, and each tier adds one projectile/pierce step instead of jumping straight to the final form.
- **Ranger Multishot** ramps gradually: a single arrow by default; `ranger_volley` (Volley t1) opens a 3-arrow fan; `ranger_rapid` (Volley t2) adds a fourth arrow; `ranger_piercing_volley` (Volley t3) grants pierce 1; `ranger_storm_volley` (Volley t4) widens to the 5-arrow storm cone; `ranger_sky_quiver` (Volley capstone) makes arrows homing. The old always-on 3-arrow base was removed.
- **Warden Shield Bash** ramps gradually: base melee hits a single foe; `warden_bulwark` (Bulwark t1) cleaves 2 foes (reach +0.22); `warden_aegis` (Bulwark t2) cleaves 3 (reach +0.28); `warden_bulwark_ward` (Bulwark t3) cleaves 4 (reach +0.35). The old always-on 3-target cleave was removed.
- **Rogue backstab** ramps gradually: base crit chance is 0 (no crits); `rogue_precision` (Precision t1) enables crits at 0.15 / 1.60×; `rogue_venom`/`rogue_executioner`/`rogue_crimson_edge`/`rogue_deathmark` raise both crit chance (0.20 / 0.28 / 0.34 / 0.40) and multiplier (1.75 / 1.95 / 2.10 / 2.25) one step per tier.
- **Acolyte Blood Rite** ramps gradually via `_acolyte_melee_leech` / `_acolyte_nova_leech`: melee/nova leech 0 by default; `acolyte_sanguine` (Blood t1) leeches 2/3; `acolyte_gravebind`/`acolyte_blood_pact`/`acolyte_crimson_maw`/`acolyte_sanguine_ascendant` raise melee (3/4/5/6) and nova (4/5/7/8) one step per tier.
- **Arcanist Frost Nova** radius ramps gradually: base 2.45 (parity with other archetypes); `arcanist_focus` (Nova t1) +0.25; `arcanist_permafrost`/`arcanist_glacial`/`arcanist_blizzard`/`arcanist_absolute_zero` add +0.45/+0.65/+0.85/+1.05 one step per tier, so the Nova path widens the burst incrementally.
- Existing milestone-3.3 combo tests that acquired the full four-branch tree were updated to the new two-branch ceiling (2 depth steps + 1 combo step), and the bolt-projectile test grants the Bolt branch entry node since the multi-shot fan is now branch-gated. The combo-bonus helper math itself is unchanged and still supports 3+ completed branches for legacy saves.
- Package metadata, `__version__`, and the save `release` string now target `3.7.0`. The save schema `version` stays 4 (no migration needed; commitment is derived from existing `skill_upgrades`).

### Validation

- Bytecode compilation and the full `unittest discover tests` suite (105 tests) pass, including the 13 new milestone 3.7 tests. Save compatibility is preserved: the run-state schema is unchanged and older saves resume with their already-acquired branches still progressable.

## Unreleased — Dungeon Sprites Polish (post-fixes)

### Changed

- Idle animation no longer opens transparent seams between sprite sections. `sprites.py` `_actor_pose_frame` slices each actor into vertical bands (cap/head/torso/hip/legs/feet) and offsets them per frame; the old idle pose drove adjacent bands apart by up to 3px, so standing still revealed horizontal gaps between sections (masked while moving because the run pose keeps bands aligned). Two fixes: a new `BAND_OVERLAP = 1` makes `blit_band` borrow one source row from the band below, filling sub-pixel seams with the neighbor's pixels (idempotent at rest because actor art is nearest-neighbour scaled, fully opaque or transparent); and the idle pose was retuned so adjacent bands never separate by more than one pixel (unified upper-body breathing bob with a 1px chest counter-motion, legs lagging a hair, feet planted). Applies to players, enemies, the shopkeeper, and story guests. New regression `test_idle_pose_stays_seamless_across_band_boundaries` asserts every idle frame keeps the full base silhouette (opaque-pixel loss under about 0.9px of full-width, so dropping the overlap or exceeding the band budget reopens a seam and fails).

- Test suite refactored for runtime and reduced redundancy. The full `unittest discover tests` run dropped from ~19.4s / 145 tests to ~5.4s / 90 tests (~72% faster, past the half-runtime goal) with no behavioral coverage lost. Two levers: (1) per-test `pygame.quit()` teardowns were removed so pygame stays initialized across the whole run — profiling showed the quit+re-init cycle dominated per-`Game` cost (~149ms cold vs ~53ms warm construction); (2) redundant milestone tests were merged (combo-bonus scaling variants, metadata/save-version duplicates, wrapped-text overlay tests, menu render smoke tests, tile-seed/cache checks, etc.) and excessive iteration counts trimmed. Metadata/save-version coverage is now canonicalized in `tests/test_inventory_hud_and_hints.py`; `tests/test_dark_floor_overlays.py`'s duplicate was removed. All distinct behavioral assertions were preserved in the merged bodies. Test files were also renamed from milestone-based to content-based names, and off-topic tests were relocated so each file's content matches its name (new `tests/test_save_and_metadata.py` and `tests/test_menu_rendering.py`; the enemy-roster test moved to the combat file, the title-state test to the core-regression file, and the menu-render smoke checks were split out of the save/archetype tests).
- Stairs sprite completely rewritten as a spiral staircase in `rendering/world.py`. The old flat three-step horizontal-line motif (plus accent bar + dot) is replaced by `_draw_spiral_staircase`, which renders a partial-arc helix of flat tread blocks descending into a round stone shaft. Each tread is a flat block at its own height `z = rise * i` (clean discrete steps), and only a partial arc of the helix is drawn (`visible = total - 2`) so the deepest tread never sits adjacent to the entry tread — that avoids the seam where the next-loop-down step overlapped the top. Treads are painted deepest-first so nearer/higher steps correctly occlude deeper ones. Each tread has a tread top, a dark riser face under the leading edge, an inner side face, a lit lip, and a specular highlight on the two nearest (entry) steps. The shaft is a radial gradient (darker toward the center) with a faint warm glow at the bottom for depth, and a lit outer rim (bright on the camera-facing side) forms the stairwell lip. The stairs tile slab is the same flagstone slab as the surrounding floor (same `theme.floor` base color + per-variant tint), filled opaquely across the whole tile diamond, so the area outside the stairwell circle matches the floor and the stairwell reads as an opening cut into the continuous floor plane rather than a contrasting patch. The z-shifted treads are drawn on a separate layer and clipped to the stairwell ellipse (alpha-multiplied mask) so no step can poke outside the ring onto the floor — you only see the stairs through the opening. `tests/test_3_6_dungeon_sprite_variants.py` `test_stairs_keep_descent_motif_across_variants` was updated to assert the new spiral motif (dark shaft within a small iso-disk of the center + stair-colored tread in the camera-facing half + no tread leaks outside the ring).

- Shop-floor coin visuals replaced. The old per-tile gilded medallion inlay in `rendering/world.py` `draw_floor_tile_surface` (the scattered gold-circle sigils on the smooth-slab shop variant) was removed so the shop floor reads as a continuous stone surface. Coin visuals now live as stacked-coin props scattered across the shop floor: a new procedural `PixelSpriteAtlas._gold_stack(size)` (size 1=small, 2=medium, 3=large) draws layered struck coins (dark outer rim, lit rim ring, inset gold face with an upper highlight crescent, a central emblem, and crisp per-coin separator bands) plus a ground-contact shadow and, for the larger tiers, a few scattered fallen coins. The three sizes are seeded to match the reviewed preview sprites exactly (`gold_stack_01/05/08`), exposed via `gold_stack_sprites` / `gold_stack_sprite(size)`. `draw_world_objects` now places 3-8 stacks per shop room via `_shop_gold_stack_placements` (deterministic per shop-room bounds, cached per frame, avoiding the shopkeeper and shop-sign tiles) and renders them with `draw_gold_stack`, sorted into the depth list so they occlude correctly against the floor and actors.

- Shop floor redesigned as a tiled checker floor. `rendering/world.py` `draw_floor_tile_surface` now routes shop (non-stairs) floor tiles to a new `_draw_shop_checker_floor` helper: a grout-colored diamond base with a 4x2 grid of 80px square tiles in two warm stone tones set as a checker, per-cell top/bottom shading, a crisp diamond edge, and a global lit-from-above pass. The 80px cell size divides both iso neighbor offsets (`TILE_W/2=160`, `TILE_H/2=80`), so the single cached shop-floor surface tiles seamlessly across adjacent diamonds into a continuous tiled floor. Stairs inside a shop room keep the normal flagstone slab so the stairwell still integrates. The shop floor no longer inherits the dungeon theme's flagstone look; it reads as a distinct polished tiled refuge beneath the scattered gold stacks.

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
