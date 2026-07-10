# Changelog

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
