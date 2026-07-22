# Changelog

## 4.6.0 — Two Will Descend: co-op multiplayer with a server component

Release 4.6.0 adds a cooperative two-player mode where a host and a joiner descend the same dungeon together over a network, relayed by a new standalone ephemeral server. Each player picks any archetype; the host runs the authoritative simulation while the joiner renders replicated state and sends input intents. Desktop and Android share the feature; web multiplayer remains a later milestone (pygbag cannot open raw TCP sockets).

### Added

- **"Two will descend"** title row (with a generated Pixellab glyph and a procedural fallback) beside the renamed **"One will descend"** row. Title rows are now `0=One will descend, 1=Two will descend, 2=Resume, 3=Options, 4=About` (`TITLE_ROW_COUNT` 5, `TITLE_RESUME_ROW` 2).
- New pre-run states: **`mp_setup`** (sub-modes `name`, `role`, `host_code`, `join_code`) and **`mp_lobby`** (partner status + archetype binding + ready flow), with dedicated renderers, keyboard/gamepad dispatch, mobile touch targets, and back-button coverage. Unknown pre-run states never fall through to dungeon-world rendering.
- A shared **single-line text-input helper** (`arch_rogue.text_input`) used by player-name, join-code, server-host, and server-port entry: desktop typing, length limits, charset filters, focus cleanup, and the Android soft keyboard via SDL text input.
- **Run codes**: the client generates a 4-character code (`MP_RUN_ID_LENGTH`) from the read-aloud-safe alphabet `ABCDEFGHJKLMNPQRSTUVWXYZ23456789` with `secrets.choice` — a room locator, not authentication; servers can configure longer codes.
- **Canonical wire protocol** package `arch_rogue_protocol` (stdlib-only, line-delimited JSON over TCP, `MP_PROTOCOL_VERSION` 1, 256 KiB line cap, non-finite-number rejection, forward-compatible unknown-type tolerance), re-exported for the game through `arch_rogue.net.protocol` and consumed by the server as a local path dependency so client and server can never drift.
- **Client package `arch_rogue.net`**: `MultiplayerClient` (stdlib socket + one background receiver thread that only decodes and enqueues immutable messages; bounded queues; queued snapshots coalesce to the newest; connection-generation tagging; clean thread join on bye/menu return/app exit), typed message dataclasses, host↔joiner world sync (`net/sync.py`), and `NetMixin` driving everything from `Game.run()` once per frame.
- **Standalone relay server** in `server/` (own `pyproject.toml`, `python -m server.server`, default port 43666): ephemeral in-memory rooms (`waiting_for_join → selecting → active → closed`, max 2 players), deterministic rejections (`run_id_in_use`, `run_not_found`, `run_full`, revision mismatch), role-forbidden routing, seq monotonicity, hello timeout, ~10-minute idle timeout, snapshot-coalescing outbound queues, and 128-bit reconnect tokens with a 30-second grace window (`partner_disconnected` / `partner_rejoined` / final `partner_left`).
- **Co-op rules**: enemies target the nearest living player (ties by stable player id); players never body-block each other; loot/gold/XP/inventory/disciplines are player-owned with host-validated first-claim pickups; stairs require every living player in range; a defeated player spectates (no revive) and the run ends only when no player remains alive; story dialogue, relic choices, and shops stay host-controlled.
- **Reconnects**: an unexpected socket loss holds the run for 30 seconds on both sides; the reconnect token reclaims the seat, the server replays the latest floor descriptor and snapshot to a rejoined joiner, and Android suspension pauses outbound traffic while holding the socket (resume reconnects if the socket died).
- Multiplayer HUD touches: partner name overhead, partner lantern light, co-op status banner (partner paused/disconnected/reconnecting, "you have fallen"), and replicated damage floaters on the joiner.
- Options schema **7 → 8**: `mp_player_name`, `mp_server_host`, `mp_server_port` (defaults `""`, `""`, `0`) with migration for all older schemas, plus new **Multiplayer** Options rows for server host and port (desktop and mobile; multiplayer stays unreachable until a usable endpoint is configured).
- New test modules: `tests/test_net_protocol.py` (codec/framing/validation/run ids), `tests/test_server_room.py` (room lifecycle on a fake clock), and `tests/test_mp_flow.py` (in-process client pair and two full headless Games over a loopback relay, plus headless mobile-mode taps, back handling, suspend gating, and reconnect-grace expiry).

### Changed

- The single `self.player` model became an explicit stable player collection (`Game.players` + `local_player_id`) with `self.player` retained as the local-player convenience path; combat, projectiles, traps, contacts, familiars (now owner-bound), secrets, animation phases, world drawing, and lighting all accept or iterate explicit players. Warden Time Skip from either player slows the shared enemy simulation.
- Multiplayer runs never touch the single-player save: `save_run`/`delete_save` refuse under `mp_active`, `Resume a saved run` stays single-player only, and each client records only its own options and run-history result after the host's `run_ended`.
- The Android package now requests the `INTERNET` permission (the first permission the app has ever needed) so the multiplayer client can open raw TCP sockets to the relay; storage remains app-private and permissionless.
- Project, runtime, Android package, server, and website release metadata advance to `4.6.0`; options move to schema `8`; run saves remain schema `5`.

## 4.5.5 — Animated descending spiral stairs

Release 4.5.5 replaces the static stair marker with an authored descending spiral stairwell and a restrained ominous light pulse from the depths.

### Added

- Added eight aligned 64×64 production staircase frames with a 14-step ping-pong playback sequence at approximately 8.3 FPS, preserving a stable silhouette while the violet shaft illumination rises and falls.
- Added one low-intensity, short-radius violet static light at the stair shaft so it casts a faint environmental glow without flooding the room.
- Extended world-asset manifest validation and resolution with optional frame lists, frame rates, ping-pong timing, and frame-specific derived-surface caching.

### Rendering

- Composite the exact floor variant beneath authored stairs using the same texture seed, anchor, tint, and theme material, so the circular opening integrates cleanly instead of exposing neighboring painter overlap or a detached blue slab.
- Keep desktop and dark-floor stair descriptors frame-aware while retaining static descriptor keys for every other tile type.
- Preserve Android's reusable opaque floor layer: the cached layer is not rebuilt for the pulse. A single transparent animated stair overlay is drawn above the cached static stair footprint before actors and walls.
- Prewarm only the seven additional frames for the current floor's actual stair seed after dungeon construction or save restoration, avoiding first-cycle hitches without multiplying every floor/shop tile variant in memory.
- Legacy procedural graphics remain static and unchanged.

### Gameplay

- Player movement and contact resolution now treat the stair shaft as solid, preventing the character from walking over the opening while keeping the existing adjacent interaction available. The collision footprint is shifted north to align with the visible circular stairwell (the authored sprite's shaft center sits 25 screen pixels above the logical tile center) and inset on all sides so the player can step up to the masonry rim from any direction; previous edge-only inset attempts that left the box centered on the tile are no longer used.
- Player contact resolution now treats every friendly NPC actor as solid, including shopkeepers, story guests, patrons, dancers, and garden frogs; collision uses the same radius as friendly-NPC movement avoidance.
- Stairs remain transparent to line-of-sight and projectiles, and enemy movement remains unchanged so scripted bosses that guard the stairs are not trapped at their spawn point.
- Pre-4.5.5 saves with the player standing directly on stairs relocate to the first safe adjacent tile when restored.
- Desktop now defaults to the widest viewport (max zoomed out) so a fresh run shows more of the dungeon at once; mobile keeps native scale. Ctrl + scroll still zooms in/out at any time.

### Validation

- `python -m compileall src tests` — clean.
- Focused dungeon-tile, sprite-asset, world-animation, movement, friendly-NPC, lighting, mobile-layout, save/metadata, mainline-render, boss, floor-progression, and Android-packaging tests pass.
- Complete non-web suite: 586 tests pass in 22.536 seconds; `test_website.py` was intentionally excluded per project policy.
- Built `arch_rogue-4.5.5-py3-none-any.whl` and verified that all eight production stair frames are packaged.
- Save schema remains 5; informational release metadata advances to 4.5.5.

## 4.5.4 — Stable Android update signing

Release 4.5.4 fixes Android's generic **App not installed** failure when upgrading between public Arch Rogue APKs.

### Fixed

- Replaced CI's per-runner debug signing with a dedicated, persistently signed release APK restored only from a protected, master-restricted `android-release` GitHub Environment.
- Made release builds fail before packaging when any keystore path, password, or alias setting is absent instead of allowing an unsigned fallback.
- Corrected the latent `android.release_artifact = _apk` typo, which made Buildozer call a nonexistent python-for-android command whenever release mode was used, and added a preflight regression guard.
- Pinned the dedicated official certificate SHA-256 fingerprint and made the APK audit reject unsigned, multiply signed, or validly signed artifacts that use the wrong key.
- Renamed public/download-site artifacts from `android-debug.apk` to `android-release.apk`; local debug builds remain available for AVD development.
- Bound CI publication to the exact APK copied by the post-audit build step, preventing a stale file in `bin/` from bypassing signer verification.
- Kept signing material out of Git, prohibited routine debug-key reuse, and expanded ignores to cover `.keystore`, `.jks`, and `.p12` files.

### Upgrade note

- GitHub-hosted APKs through 4.5.3 used ephemeral debug certificates. Android cannot authorize an in-place update from those builds because their private keys disappeared with the CI runners. Local debug APKs also use machine-specific development keys. All pre-4.5.4 installations must therefore uninstall once before installing the dedicated-key release; upgrades after that preserve app-private saves and options.

### Validation

- Root-cause audit confirmed historical local 4.3.17–4.5.3 APKs shared a workstation debug certificate while GitHub runners did not preserve one; the official 4.5.4 signer is now a separate 4096-bit release-only key with public certificate SHA-256 `1cd7ca29fbc4ea8f54aff940e80e7628581264cb7ce4d3359ac2be3a0bef07c6`.
- `python -m compileall src tests` — clean.
- `python -m unittest discover tests` — all 580 tests pass.
- Signed release build `bin/archrogue-4.5.4-arm64-v8a_armeabi-v7a-release.apk` passed source validation, dual-ABI audit (104 ELF extensions per ABI), APK v2 verification, single-signer enforcement, and dedicated-certificate pinning; 71,905,436 bytes, SHA-256 `1cb51bf61b7fbcdd1790f7251d9b3f6d5da357386f3759d4b05606d57b18ae84`.
- Verified the CI handoff copy is byte-identical to the audited source APK.
- On the AVD, the old debug-signed installation reproduced `INSTALL_FAILED_UPDATE_INCOMPATIBLE`; the documented one-time uninstall/install succeeded, a subsequent `adb install -r` with the dedicated signer succeeded, and the non-debuggable 4.5.4 package launched (`versionCode=102840504`).
- Save schema remains 5; only informational release metadata advances to 4.5.4.

## 4.5.3 — Android movement hitch stabilization

Release 4.5.3 removes the periodic Native-resolution Android hitch that occurred while the camera crossed the reusable floor cache's gutter during exploration.

### Fixed

- Replaced camera-travel cold rebuilds of the approximately 3900×1800 Android floor cache with an in-place surface recenter. The cache scrolls by the exact projection delta and redraws only newly exposed strips plus a one-tile trailing guard band.
- Preserved exact rendering: the recentered floor surface is byte-identical to a cold rebuild, including edge clipping, incremental fog-of-war reveals, and fractional camera translation.
- Kept true invalidations (floor/theme/render-mode changes, reveal-set replacement, and travel beyond the complete layer) on the existing cold-build fallback.

### Diagnostics

- Android performance telemetry now reports interval frame-time p50/p95/max and relative hitch counts instead of only averages.
- Each report identifies the worst frame's dominant top-level/detail phase and correlates it with per-frame revealed-tile, floor rebuild/recenter/patch, and sprite load/build deltas.
- `tools/profile_adb_live.py` displays the new jank distribution and worst-frame cause in its dashboard.

### Test maintenance

- Corrected the stale gameplay and crowd desktop render baselines after confirming the current output is deterministic, and removed the redundant second render from all three fixed-hash snapshot tests.
- Reused the immutable procedural fallback sprite atlas across `SpriteAtlas` facades while retaining independent asset libraries, graphics-mode state, and derived caches.
- Headless `Game` instances now generate tile variants on demand by default; interactive desktop and Android builds retain eager prewarming, and cache-contract tests opt into it explicitly.
- Removed five duplicate or transitional tests plus 13 no-op `tearDown()` hooks without reducing behavioral coverage.
- Full-suite runtime dropped from 82.712 seconds to 26.281 seconds (about 68% faster).

### Android AVD results

- Tested on the `arch_rogue_perf` SwiftShader AVD at the Native 2340×1080 logical/window/viewport target with the existing 1560×720 gameplay GPU stream.
- Instrumented 4.5.2 traversal reproduced `86.8–87.1 ms` worst frames; those exact frames spent `39.9–44.4 ms` in floor rendering and each correlated with `rebuilds:+1`.
- The final 4.5.3 16-input corridor traversal performed five in-place recenters with no travel rebuilds and reduced active-movement worst frames to `48.5–58.0 ms`, within the AVD's ordinary present/render variance.
- A follow-up doorway/NPC reveal built 10 lazy sprite frames, but sprite loads did not occur on the worst frame; the run remained at a `56.3 ms` maximum with a `2.0 ms` average floor phase.

### Validation

- `python -m compileall src tests` — clean.
- `python -m unittest tests.test_mobile_layout` — 73 tests pass, including simultaneous multi-tile reveal and diagonal recenter/cold-build pixel comparisons with zero differing pixels.
- `python -m unittest discover tests -q --durations 40` — all 576 tests pass in 26.281 seconds; the five removed tests were redundant coverage and the two stale render snapshots now match the verified deterministic output.
- Final debug APK passed source validation, dual-ABI audit, APK v2 signature verification, installation, and package-version verification (`versionName=4.5.3`, `versionCode=102840503`).
- Save schema remains 5; only informational release metadata advances to 4.5.3.

## 4.5.2 — Android Native performance stabilization

Release 4.5.2 substantially improves Native-resolution Android performance on the SwiftShader AVD while preserving the 2340×1080 logical/window output and the existing 1560×720 gameplay GPU stream.

### Changed

- Reworked quest-cutscene composition to use cached opaque backgrounds/panels, direct framebuffer subsurfaces, retained static panel chrome, cached actor surfaces/labels, and cached narration/story context.
- Removed redundant full-screen GLES clears and retained-shell draws when the blend-none gameplay base covers the complete Native target.
- Moved stable mobile HUD regions to retained post-light GPU textures so unchanged action rails and left HUD clusters are neither redrawn nor re-uploaded.
- Reduced mobile combat-lighting work by retaining unchanged light buffers, updating decorative dynamic lighting on alternating render frames, and prioritizing at most six transient halos without changing gameplay entities/effects.
- Cached and quantized mobile enemy windup telegraphs and suppressed the duplicate committed-attack warning.
- During dense mobile combat, suppress optional relic guidance while enemies are visible and omit ordinary contact shadows only when at least eight enemies are visible; player, boss, elite, and normal-scene shadows remain.

### Performance

- Native cutscene: ~7.9–8.5 FPS → 25.2–27.4 FPS, average ~26.8 FPS.
- Native ten-enemy combat/effects scenario: ~15.4–15.9 FPS → 19.8–21.3 FPS, average ~20.6 FPS.
- Native logical/window/viewport remains 2340×1080; gameplay stream remains 1560×720.

### Validation

- `python -m compileall src tests`
- Focused cutscene, mobile-layout, HUD, lighting, windup, story, and world tests pass.
- Android packaging tests: 20/20 pass.
- Debug APK passed source validation, ABI audit, and APK v2 signature verification.
- Save schema remains 5; only informational release metadata advances to 4.5.2.

## 4.5.1 — Root module packaging (structural cleanup)

Milestone 4.5.1 reduces root-level clutter in `src/arch_rogue/` by packaging tightly-coupled clusters into modules, mirroring the existing `combat/` / `content/` / `menus/` / `rendering/` facade pattern. Guided by the vibe-architecture rule: only package when a clear boundary exists; peer runtime mixins and leaf utilities stay at root. See `AGENTS.md` → "4.5.x+ Root module packaging" for the full phased plan.

### Phase A — Relocate `lighting` into `rendering/`

- `git mv src/arch_rogue/lighting.py src/arch_rogue/rendering/lighting.py`; `LightingMixin` already composes into `RenderingMixin`, so the move fixes a structural mismatch rather than cosmetic relocation.
- Updated relative imports inside the moved file (`..constants` / `..mobile` / `..models`) and `rendering/__init__.py` (`from .lighting import LightingMixin`).
- `sprites.py` / `sprite_assets.py` `bake_normal_map` import retargeted to `arch_rogue.rendering.lighting` (later made lazy in Phase B to break a module-load cycle).
- `tests/test_lighting.py` import updated to `arch_rogue.rendering.lighting`.

### Phase B — Package the sprite/asset cluster into `sprites/`

- Created `src/arch_rogue/sprites/` package: `sprites.py` → `sprites/procedural.py`, `sprite_assets.py` → `sprites/library.py`, `ui_assets.py` → `sprites/ui_assets.py`.
- `sprites/__init__.py` re-exports `PixelSpriteAtlas`, `SpriteAtlas`, `AssetSpriteLibrary`, `ResolvedSpriteFrame`, `DIRECTIONS`, `BAR_WALL_SCONCE_DIRECTION_BY_FACE`, `GOLD_STACK_ASSET_KEYS`, `STAGE_PROP_ASSET_KEYS`, `UiAssetLibrary`.
- Intra-package imports fixed (`from .procedural import PixelSpriteAtlas`, `from ..mobile`, `from ..models`, `from ..constants`).
- `bake_normal_map` import converted to lazy in-body imports in `sprites/procedural.py` and `sprites/library.py` to break the `sprites ↔ rendering` module-load cycle (the function is only used at runtime inside methods, never at module top).
- `game.py` and `rendering/actors.py` retargeted to import from `arch_rogue.sprites`.
- `test_sprite_assets.py` logger assertion updated `arch_rogue.sprite_assets` → `arch_rogue.sprites.library` (the `LOGGER = logging.getLogger(__name__)` now resolves to the new module path).

### Phase C — Package the story/quest/NPC cluster into `story/`

- Created `src/arch_rogue/story/` package: `story.py` → `story/engine.py`, `story_runtime.py` → `story/runtime.py`, `npc_runtime.py` → `story/npc_runtime.py`, `quest_assets.py` → `story/quest_assets.py`.
- `story/__init__.py` re-exports `StoryEngine`, `StoryRuntimeMixin`, `FriendlyNpcRuntimeMixin`, `FriendlyNpcMotion`, the `story_*_to_dict` / `story_*_from_dict` helpers, and the full quest-cutscene asset class set. The package `__init__.py` is itself the backward-compat facade for the old `from arch_rogue.story import ...` path (no separate shim needed for `story.py`).
- Intra-package imports fixed: `story/runtime.py` imports `from .engine import ...` and `from .quest_assets import ...`; `story/engine.py` and `story/npc_runtime.py` use `..constants` / `..content` / `..models` / `..audio`.
- External importers retargeted: `game.py`, `save_system.py`, and the six `rendering/*.py` modules (`from ..quest_assets import ...` → `from ..story import ...`).

### Phase D — Drop deprecated shims

- Removed the transitional one-line re-export shims: `arch_rogue/sprite_assets.py`, `arch_rogue/ui_assets.py`, `arch_rogue/story_runtime.py`, `arch_rogue/npc_runtime.py`, `arch_rogue/quest_assets.py` (`arch_rogue/sprites.py` was already superseded by the `sprites/` package directory in Phase B).
- Updated the remaining test imports to package paths: `arch_rogue.sprite_assets` → `arch_rogue.sprites`, `arch_rogue.ui_assets` → `arch_rogue.sprites`, `arch_rogue.quest_assets` → `arch_rogue.story`.
- Updated `AGENTS.md` "Current Code Organization" section to reflect the new package layout.

### Net effect

Root `.py` file count drops from 27 to 16 (excluding `game.py`, `__init__.py`, `__main__.py`). Two new packages (`sprites/`, `story/`) follow the established facade pattern; `lighting.py` joins the existing `rendering/` package. The 10 peer runtime mixins and 6 leaf utilities (`constants`, `models`, `dungeon`, `audio`, `icon`, `licenses`) stay at root per the vibe-architecture guidance.

### Validation

- `python -m compileall src tests` — clean after every phase.
- `python -m unittest discover tests` — 581 tests pass after every phase (A, B, C, D). No regressions; the suite count is unchanged from the pre-refactor baseline.

## 4.5 — Combat module refactoring

Milestone 4.5 splits the ~3,800-line `combat.py` / 126-method `CombatMixin` into a `combat/` package of focused submixins, preserving `from arch_rogue.combat import CombatMixin` and keeping behavior identical during the split, then picks a few small ARPG combat improvements. See `AGENTS.md` → "4.5 Combat module refactoring" for the full phased plan.

### Phase 1 — Package skeleton (no behavior change)

- Converted `src/arch_rogue/combat.py` → `src/arch_rogue/combat/` package.
- `combat/_core.py` holds the full `CombatMixin` body unchanged; the four parent-package imports were retargeted (`.constants`/`.content`/`.dungeon`/`.models` → `..constants`/`..content`/`..dungeon`/`..models`).
- `combat/__init__.py` re-exports `CombatMixin` so `from arch_rogue.combat import CombatMixin` and `Game`'s `__all__` entry keep working.
- No method moves yet; behavior is bit-for-bit identical with the previous monolithic module. Phase 2 will split `_core` into focused submixins.

### Validation

- `python -m compileall src tests` — clean.
- `python -m unittest discover tests` — 550 tests pass.

### Phase 2 — Split into focused submixins (behavior identical)

- Split `combat/_core.py` into 15 focused submodules, each exposing a `_<Name>CombatMixin` that contributes its methods to `CombatMixin` via multiple inheritance in `combat/__init__.py`. Method bodies and signatures are unchanged; the submixins share state through `self.` exactly as the single mixin did.
- Submodules: `equipment`, `statuses`, `aim`, `disciplines`, `class_skills`, `costs`, `player`, `movement`, `enemies`, `projectiles`, `attacks`, `ambush_bell`, `familiars`, `mobility`, `damage`.
- `_core.py` removed. Each submodule carries a module docstring naming its subsystem and imports only the parent-package names it uses (verified clean by `pyflakes`).
- Placement decisions from plan review: `_trigger_enemy_hit_flash` lives in `damage.py` (shared damage-application primitive used by `damage_enemy`, `_reflect_thorns`, `_familiar_attack`, `_apply_chain_proc`); `_reflect_thorns` stays in `player.py` (player thorns effect, only called from `take_player_damage`). `CONTROLLER_AIM_SNAP_*` constants live in `aim.py`; `_CLASS_SKILL_*` tables live in `class_skills.py`.
- `combo_preview`'s lazy in-body import was retargeted `from .content import combo_bonus_preview` → `from ..content import combo_bonus_preview`.
- Class-level constants relocated to their owning submodule: the `FAMILIAR_*` / `SPIRIT_BEAST_*` tuning constants (originally sandwiched between `detonate_ambush_bell` and `familiar_max_count`) moved to `familiars.py`; the `AMBUSH_BELL_*` tuning constants (originally between `player_cast_time_skip` and `ambush_bell_tuning`) moved to `ambush_bell.py`; `CONTROLLER_AIM_SNAP_*` live in `aim.py`; `_CLASS_SKILL_*` tables live in `class_skills.py`. Each constants block sits at the top of its class, just under the docstring/comment header.
- `from arch_rogue.combat import CombatMixin` and `Game`'s `__all__` entry still resolve; composed mixin exposes the same 125 methods as the pre-split module.

### Validation

- `python -m compileall src tests` — clean.
- `python -m pyflakes src/arch_rogue/combat/` — clean (no unused imports).
- `python -m unittest discover tests` — 550 tests pass.

### Post-Phase 2 cleanup — story-gated damage hooks moved into combat

Assessment pass found one combat-logic leak outside the `combat/` package: three helpers in `story_runtime.py` (`story_player_damage_bonus`, `apply_story_player_damage`, `apply_story_blood_price`) that are called exclusively from `combat/` and implement combat operations (player damage multiplier + HP-cost payment), only reading story state via `self.story_effect_value` / `self.story_state`.

- Moved the three methods into a new focused submodule `combat/story_hooks.py` (`_StoryHooksCombatMixin`), added to the `CombatMixin` composition. They keep calling `self.story_effect_value(...)` (stays in `story_runtime.py`) and reading `self.story_state` — no story-runtime behavior moved.
- Removed the three methods from `story_runtime.py`; `FloatingText` is still used there by other floaters, so its import stays.
- `CombatMixin` now composes 16 submixins and exposes 128 methods (125 + 3 hooks). Other combat-adjacent code outside `combat/` (model derived stats, population enemy setup, petting interaction, potion use, boss-arena radius, rendering/sprites/save) was assessed and intentionally left in place — see `AGENTS.md` → "Post-Phase 2 cleanup" for the rejected candidates and reasoning.

### Validation

- `python -m compileall src tests` — clean.
- `python -m pyflakes src/arch_rogue/combat/ src/arch_rogue/story_runtime.py` — clean.
- `python -m unittest discover tests` — 550 tests pass.
- Smoke: `from arch_rogue.combat import CombatMixin; from arch_rogue.story_runtime import StoryRuntimeMixin` resolves; hooks on `CombatMixin`, not on `StoryRuntimeMixin`.

### Phase 3 — Cleanup & de-duplication (behavior identical)

- **`combat/_utils.py`** — new pure-helper module owning the stateless logic previously inlined in submodules: `average_slow_factors` (from `statuses.py`), `anim_speed` (from `movement.py`), and `enemy_hit_radius` / `actor_hit_radius` (from `movement.py`). The mixin keeps thin wrapper methods `enemy_hit_radius` / `actor_hit_radius` so external callers (`run_flow.boss_arena_enemy_radius`, tests) keep working via `self.enemy_hit_radius(enemy)`; the two `static_method`s were removed and their call sites now import the module-level functions.
- **`combat/damage_types.py`** — new data-table module centralizing damage-type data: `DAMAGE_TYPE_COLORS` + `DEFAULT_DAMAGE_COLOR` (from `equipment.damage_type_color`'s inline dict), `STATUS_DAMAGE_TYPE` + `DEFAULT_STATUS_DAMAGE_TYPE` (from `statuses.apply_enemy_status`'s inline map), and `RESISTANCE_FLOOR` / `RESISTANCE_CEIL` with a `clamp_resistance` helper (from `statuses.mitigate_enemy_damage`'s inline clamp). `equipment.damage_type_color`, `statuses.apply_enemy_status`, and `statuses.mitigate_enemy_damage` now route through `damage_color()` / `status_damage_type()` / `clamp_resistance()`. Adding a new damage type is now a single edit here.
- **Combat-only constants relocated**: `BOSS_FOOTPRINT_HIT_RADIUS`, `BOSS_FOOTPRINT_MOVE_RADIUS`, `PLAYER_MOVE_SPEED`, `WALK_ANIM_SPEED_FLOOR`, `WALK_ANIM_SPEED_CEIL` moved from `constants.py` into `combat/_utils.py` (colocated with the helpers that use them). `WALK_ANIM_RUNTIME_SCALE_FLOOR` was left in `constants.py` because tests import it from `arch_rogue.constants`. Shared constants (`PLAYER_HIT_RADIUS`, `BOSS_HIT_RADIUS`, `ENEMY_HIT_RADIUS`, `LARGE_ENEMY_HIT_RADIUS`, `WALK_ANIMATION_RATE`) stay in `constants.py`. `combat/player.py` and `combat/movement.py` now import the moved constants from `._utils`.
- **pyright suppression**: `# pyright: reportAttributeAccessIssue=false` removed from the three pure modules (`__init__.py`, `_utils.py`, `damage_types.py`) which do no `self.` access; kept on all 17 submixins which still do cross-mixin `self.` access.
- `CombatMixin` now exposes 126 methods (128 − 2 static helpers promoted to module-level functions in `_utils`).

### Validation

- `python -m compileall src tests` — clean.
- `python -m pyflakes src/arch_rogue/combat/ src/arch_rogue/constants.py` — clean (pre-existing unused-import warnings elsewhere in `src/` are unrelated to this change).
- `python -m unittest discover tests` — 550 tests pass.
- Smoke: `_utils` / `damage_types` helpers return expected values; `constants.WALK_ANIM_RUNTIME_SCALE_FLOOR` preserved, `constants.PLAYER_MOVE_SPEED` removed; `CombatMixin` composes 126 methods.

### Phase 4 — Batch A (low-risk combat-internal improvements)

Three of the seven Phase 4 items, all confined to `combat/` (no `models.py`/`save_system.py`/`rendering/` changes). Each is independently reversible and covered by `tests/test_class_skills_speeds_and_crit.py` (9 new tests).

- **✅ #7 `ClassSkill` registry** (`combat/class_skills.py`): replaced the `_CLASS_SKILL_KINDS`/`_CASTS`/`_BONUS_TERMS` triple-dict plus the inline color dict with a frozen `ClassSkill` dataclass + `CLASS_SKILLS` registry (fields: archetype, kind, cast_method, bonus_term, color) and a `_DEFAULT_CLASS_SKILL` fallback matching the old defaults. The 4 public methods (`class_skill_kind`, `player_cast_class_skill`, `equipment_class_skill_bonus`, `skill_color`) now route through one `_class_skill()` lookup; signatures and return values unchanged. Adding a new archetype's class skill is one registry entry.
- **✅ #4 Attack/cast-speed getters** (`combat/costs.py`, `combat/movement.py`): extracted `player_attack_speed()` and `player_cast_speed()` (clamped `[-0.20, 0.35]` equipment stats) as the single source for haste; `melee_cooldown`/`bolt_cooldown`/`class_skill_cooldown` now consume them instead of inlining the clamp three times. Added `player_walk_cadence()` in `movement.py` as the single seam `advance_animation_phases` consumes for the player's animation rate. Deliberately did **not** scale walk cadence by the attack_speed stat — `Player` has only `anim_time` (drives the walk cycle incl. arm swing; no separate attack-swing clock) and movement speed is fixed, so scaling would desync stride from ground speed (footslide). The seam exists for a future discipline that scales cadence and movement together.
- **✅ #3 Crit refactor** (`combat/attacks.py`): crit was inline in `player_melee_attack` (Rogue Precision-path tiers + the "smoke crits" unique override), not in `damage_enemy` as the plan guessed. Extracted `_rogue_crit_profile()` (the discipline→chance/multiplier table) and `roll_melee_crit(enemy)` (the roll + smoke override, returns `(is_crit, multiplier)` and emits the "Smoke Crit" floater). The caller applies the multiplier and emits the "Critical" floater. RNG consumption order preserved (Precision roll, then smoke roll) so replays stay deterministic; the dead `status_duration=1.4` from the old smoke branch (always overridden by the crit block) was dropped.
- `CombatMixin` now composes 132 methods (126 + 6 new: `_class_skill`, `player_attack_speed`, `player_cast_speed`, `player_walk_cadence`, `_rogue_crit_profile`, `roll_melee_crit`).

### Validation

- `python -m compileall src tests` — clean.
- `python -m pyflakes src/arch_rogue/combat/` — clean.
- `python -m unittest tests.test_class_skills_speeds_and_crit` — 9 new tests pass (registry mapping/default/methods, speed-getter clamp + cooldown consumption, crit profile tiers, class-gate, deterministic precision roll, smoke override).
- `python -m unittest discover tests` — 559 tests pass (550 + 9).

### Phase 4 — Batch B (damage pipeline: `DamageContext` + unified resistance table)

Two combat-internal damage-pipeline refactors, both behavior-identical, covered by `tests/test_damage_context_and_player_resistances.py` (9 new tests).

- **✅ #1 `DamageContext`** (`combat/damage.py` + 6 src / 5 test call sites): added a frozen `DamageContext` dataclass (target, amount, damage_type, knockback_from, status_effect, status_duration, source, is_crit). `damage_enemy(self, ctx: DamageContext)` unpacks `ctx` into the locals the body already uses, so the body is byte-identical. All 6 src call sites (`player` Warden counter, `projectiles` projectile-hit + chain-secondary, `attacks` melee + nova, `ambush_bell`) and 5 test call sites converted to build a `DamageContext`; melee passes `is_crit` (from `roll_melee_crit`) and each passes a `source` label ("melee"/"bolt"/"nova"/"counter"/"projectile"/"chain"/"ambush_bell") for future damage modifiers. `_apply_chain_proc` kept its `(source, damage)` signature — it's a chain-origin search + flat arcane tick with no mitigation/procs, structurally distinct from a full damage event.
- **✅ #2 Unified resistance table** (`combat/damage_types.py`, `combat/player.py`): the player per-damage-type resistance `if` chains that were inline in `take_player_damage` (Grounded/Sealed affixes, glacial ward unique, armor typed-match) are now table-driven in `damage_types.py` (`PLAYER_RESIST_AFFIXES`, `PLAYER_RESIST_UNIQUES`, `PLAYER_ARMOR_TYPED_RESIST_BONUS`). New `player_typed_resistance(damage_type)` mixin method computes the full typed-resist fraction via those tables plus the all-types bonuses (oathwall aegis, `aegis` status, Warden Temporal Aegis) that don't branch on damage type; `take_player_damage` now calls it. The enemy side was already data-driven (`enemy.resistances` dict + `clamp_resistance` from Phase 3). Adding a new damage type's resist affix/unique is one table entry. Behavior identical (verified: a frost-typed armor takes strictly less frost damage than physical).
- `CombatMixin` now composes 133 methods (132 + `player_typed_resistance`).

### Validation

- `python -m compileall src tests` — clean.
- `python -m pyflakes src/arch_rogue/combat/` — clean.
- `python -m unittest tests.test_damage_context_and_player_resistances` — 9 new tests pass (DamageContext defaults/frozen/round-trip, damage_enemy accepts ctx, resistance tables match old values, typed-resistance branches per damage type, unique/status/Temporal Aegis, take_player_damage reduction).
- `python -m unittest discover tests` — 568 tests pass (559 + 9).

### Phase 4 — Batch C (cross-module: knockback on `Enemy` + swing telegraph)

The final two Phase 4 items. Both cross the `combat/` boundary into `models.py` / `save_system.py` / `rendering/`, so both add transient fields to `Enemy` (excluded from saves via `_TRANSIENT_ENEMY_FIELDS`). Covered by `tests/test_enemy_knockback_and_attack_windup.py` (9 new tests).

- **✅ #5 Knockback field on `Enemy`** (`models.py`, `save_system.py`, `combat/_utils.py`, `combat/damage.py`, `combat/enemies.py`): added transient `knockback_vx`/`knockback_vy` (tiles/sec). `damage_enemy` now sets the velocity (direction × `KNOCKBACK_SPEED`) instead of the old one-shot `move_actor` 0.16-tile nudge. A new `_apply_enemy_knockback(enemy, dt)` helper runs early in `update_enemies` (before the aggro/stun `continue` skips), integrating the velocity via `move_actor` (collision-aware) with exponential decay (`KNOCKBACK_DECAY_RATE`), so shoves are framerate-independent and land even on stunned/out-of-aggro enemies. Tuned so total displacement ≈ `KNOCKBACK_SPEED`/`KNOCKBACK_DECAY_RATE` (~0.16 tiles, matching the old nudge); Time Skip slows the integration via `scaled_dt` but total displacement is unchanged. Deviated from the plan's "consumed in `_move_enemy_locomotion`" because that path is skipped for stunned/out-of-aggro enemies — the dedicated `update_enemies` step ensures shoves work regardless of AI state.
- **✅ #6 Telegraphed attacks** (`models.py`, `save_system.py`, `combat/_utils.py`, `combat/enemies.py`, `rendering/actors.py`): enemies now wind up before attacking (real pre-attack telegraph). Added transient `windup_time`/`windup_duration` + `windup_attack`/`windup_nx`/`windup_ny` (committed-attack snapshot). In `update_enemies`, `_commit_enemy_attack` starts the windup when `attack_ready + in range + LOS` (melee `0.35s` / ranged `0.5s` / boss `0.25s`), snapshots the cast aim, and the windup phase (precedence over aggro/stun, decayed each frame) fires via `_fire_committed_attack` with `line_of_sight_confirmed=True` — **locked**, so the committed hit lands even if the player moves during the short windup (counter with abilities like evade/block, not by walking out). Stun interrupts a committed windup. `draw_windup_telegraph(enemy, sx, sy)` renders a fading ring during the windup. **4.4.11 conflict resolved:** the 4.4.11 stalling bug was variable/unreadable delay with the enemy never committing; this windup is fixed/visible delay *after a reliable commit*. The anti-stall guarantee is preserved and re-tested as "commit on the eligible frame, no oscillation." The 4.4.11 AI-loop tests (`test_enemy_cannot_melee_through_wall`, `test_enemy_cannot_melee_through_closed_diagonal_corner`, `test_enemy_los_runs_only_when_an_attack_is_eligible`, `test_melee_enemy_attacks_when_inside_range_even_above_stop_distance`) and `test_boss_cast_fires_three_bolt_fan` were updated from "damage on frame 1" to "commit on frame 1 (`windup_time > 0`), damage/projectile after the windup." `enemy_melee`/`enemy_cast` stay instant-damage (windup is in the AI loop), so the direct-call LOS tests are unchanged. (Batch C's first cut shipped a post-swing indicator that kept instant damage; this revision replaces it with the real deferred-windup design the game needs.)
- `CombatMixin` now composes 134 methods (133 + `_apply_enemy_knockback`).

### Validation

- `python -m compileall src tests` — clean.
- `python -m pyflakes src/arch_rogue/combat/ src/arch_rogue/models.py src/arch_rogue/save_system.py` — clean (pre-existing unused-import warnings in `rendering/actors.py` are unrelated to this change).
- `python -m unittest tests.test_enemy_knockback_and_attack_windup` — 9 new tests pass (knockback fields default zero, damage_enemy sets velocity + defers shove, update_enemies applies+decays for stunned enemy, total displacement ≈ continuous limit, transient fields excluded from saves, enemy_melee/enemy_cast set telegraph, update_enemies decays it, draw helper no-op at zero + safe when active).
- `python -m unittest discover tests` — 577 tests pass (568 + 9).

## 4.4.11 — Enemy Melee Range Stalling Fix

Release 4.4.11 fixes the common mobile/desktop case where a melee enemy would chase the player but appear to idle just outside (or just inside) its attack range, sometimes failing to land hits for extended periods.

### Root Cause

- `CombatMixin.update_enemies` coupled the movement stop distance and the melee attack decision with an `elif`. Once an enemy was within `attack_range` but still above the implicit movement threshold, it would take a microscopic final step on most frames instead of attacking. On low-FPS/mobile frames or when the player micro-kited at the edge, the enemy could spend many frames oscillating at the threshold without ever satisfying the attack branch.
- The movement target was exactly `attack_range`, so enemies stopped at the bare edge of their reach. Any small relative motion or floating-point jitter could push them back into the movement branch and delay the attack indefinitely.

### Changed

- **`src/arch_rogue/combat.py` (`_enemy_melee_stop_distance`):** new helper that returns a melee stop distance slightly inside `attack_range` (cushioned by `0.02..0.12` and clamped outside actor contact distance). Melee enemies now press to a reliable sweet spot instead of stopping at the threshold.
- **`src/arch_rogue/combat.py` (`update_enemies`):** the standard melee and boss-encounter closing logic now use `_enemy_melee_stop_distance` for movement, and the attack decision is an independent `if` rather than an `elif`. Enemies that end a frame within `attack_range` attack immediately, even if they also took a small closing step. LOS is revalidated from the final position when movement occurred.
- **`tests/test_enemy_los_walls.py`:** two regression tests added — one verifies a melee enemy attacks as soon as it is inside `attack_range` even if still above the movement stop distance, and one verifies a melee enemy closes and lands a hit on a slowly retreating player.
- Project, runtime, Android package, and website release metadata advance to `4.4.11`; options remain schema `7` and run saves remain schema `5`.

### Validation

- `.venv/bin/python -m compileall src tests`
- `.venv/bin/python -m unittest tests.test_enemy_los_walls` — focused suite passes, including the two new regression tests.
- `.venv/bin/python -m unittest discover tests` — 550 tests pass.

## 4.4.10 — Polished Death Screen Panel Corners

Release 4.4.10 fixes a visual defect on the "You Died" / "Dungeon Cleared" screen where dark triangular artifacts appeared at the corners of the stat panels and the main overlay panel. The nine-slice panel assets (`panel.png`, `panel_compact.png`, `panel_inset.png`) had pure-black border pixels in their corner pieces that created visible black triangles against the red death tint background.

### Changed

- **`src/arch_rogue/assets/sprites/menus/panel_inset.png`:** replaced all pure-black (0,0,0) pixels within the four nine-slice corner pieces with the panel body colour (14,17,17), eliminating the dark triangular artifacts at stat sub-panel corners. The border along straight edges is preserved.
- **`src/arch_rogue/assets/sprites/menus/panel.png`:** same corner-pixel cleanup for the main overlay panel asset (body colour 24,24,26).
- **`src/arch_rogue/assets/sprites/menus/panel_compact.png`:** same corner-pixel cleanup for the compact panel variant.
- **`src/arch_rogue/menus/state_overlay.py` (`_draw_state_stat_panel`):** the opaque background fill behind each stat sub-panel now uses a rounded rect (`border_radius`) matching the inset panel's corner shape, so the transparent corner tips show a rounded edge instead of a sharp triangle.
- **`src/arch_rogue/menus/state_overlay.py` (`_draw_state_overlay_content`):** the main overlay panel background fill also uses a rounded rect for the same reason.
- **`tests/test_mainline_regression.py`:** updated the three desktop render-snapshot hashes to reflect the asset changes.
- Project, runtime, Android package, and website release metadata advance to `4.4.10`.

### Validation

- `python -m compileall src tests`
- `python -m unittest discover tests` — 548 tests pass.

## 4.4.9 — Mobile Crash Fix: Restored Enemy Colors Break Impact Overlay Cache

Release 4.4.9 fixes a hard crash that ended the process on Android (and would also crash desktop builds once they entered the same code path) the first time a non-boss enemy died after loading a saved run. The crash manifested as `Fatal signal 6 (SIGABRT)` from the p4a/SDL host after Python emitted `TypeError: cannot use 'tuple' as a dict key (unhashable type: 'list')` from `draw_impact`.

### Root Cause

- Enemies are serialized via `enemy.__dict__.items()` in `save_system.serialize_run_state`, so the `color` tuple is written to JSON as a list. On restore, `restore_run_state` rebuilt each enemy with `Enemy(**enemy)`, which put that JSON list straight back into `enemy.color` without normalizing it back to a tuple. Every other model that carries a `Color` field (`IdleNpc`, `LightSource`, `StoryGuest`) already converted `list -> tuple` on restore; `Enemy` was the lone exception.
- `kill_enemy` (combat) sets `death_color = enemy.color` for non-boss/miniboss enemies and passes it to `add_impact`, which built an `ImpactEffect` whose `color` was now a list.
- The shared impact-overlay cache introduced in 4.3.17 / extended in 4.4 mobile-optimization work builds its LRU key as `(effect.kind, effect.archetype, progress_bucket, alpha_bucket, radius_bucket, effect.color)`. Hashing that tuple with a list member raises `TypeError: unhashable type: 'list'`, killing the render loop and the process.

### Changed

- **`src/arch_rogue/save_system.py` (`restore_run_state`):** the enemy-restore comprehension now normalizes `color` from a list back to a 3-tuple of ints before constructing `Enemy`, matching the existing pattern used by `idle_npc_from_dict`, `light_source_from_dict`, and `story_guest_from_dict`. This is the root-cause fix: a restored enemy's `color` is now always a hashable tuple.
- **`src/arch_rogue/game.py` (`add_impact`):** defensive normalization. `add_impact` is called from ~25 combat/interaction paths; if any future caller ever passes a list color, `ImpactEffect.color` is now coerced to a tuple at the entry point so the `draw_impact` overlay cache key stays hashable. Tuple colors pass through unchanged.
- **Regression coverage:** `tests/test_save_and_metadata.py` adds `test_restored_enemy_color_is_hashable_tuple` (round-trips an enemy through save/load and asserts every restored `enemy.color` is a tuple that can be hashed inside the impact-cache key shape) and `test_add_impact_normalizes_list_color` (passes `[255, 90, 70]` to `add_impact` and asserts the resulting `ImpactEffect.color` is a tuple that hashes cleanly).
- Project, runtime, Android package, and website release metadata advance to `4.4.9`; options remain schema `7` and run saves remain schema `5` (no save-format migration — older saves with list enemy colors now load correctly).

### Validation

- `.venv/bin/python -m compileall -q src tests`
- `.venv/bin/python -m unittest tests.test_save_and_metadata` — focused suite passes (4 tests, including the two new regression tests).
- `.venv/bin/python -m unittest discover tests` — 548 tests pass.
- Reproduced the original crash against the old restore path (`Enemy(**enemy)` with a list color) to confirm the regression test exercises the actual failure mode; the new path produces a tuple and hashes cleanly.

## 4.4.8 — Branded Android Loading Screen & Full-Screen Death Tint

Release 4.4.8 replaces python-for-android's default SDL splash with the authored Arch Rogue title logo so the APK opens with the branded `ARCH <diamond> ROGUE` lockup while the Python interpreter bootstraps, and stretches the death/victory red tint to the full mobile display so cutout/notch areas are tinted like the world viewport while the stat panels stay opaque.

### Changed

- **Branded presplash:** `buildozer.spec` now sets `presplash.filename` to the bundled `src/arch_rogue/assets/sprites/menus/title_logo.png` (the same 640×122 antique-gold gothic lockup used by the in-game title screen) and `presplash.color = #0a0a0f` so the transparent logo sits on a dark background matching the game's grim-fantasy tone. The loading screen is no longer the generic p4a/SDL2 splash.
- **Presplash preflight:** `tools/validate_android_apk.py` `validate_build_spec` now requires `presplash.filename` to be set and to resolve to an existing file relative to the project root, so a future spec edit cannot silently regress to the default splash or point at a missing asset.
- **Full-screen death/victory tint on mobile:** the red/gold death-victory background is now drawn to the root display before the safe-area render target clips content, so the tint stretches edge-to-edge across cutout/notch areas — matching the world viewport — instead of only covering the safe area. The frame loop splits `draw_state_overlay` into `draw_state_overlay_background` (full-screen tint) and `draw_state_overlay_content` (safe-area panels); the single-call `draw_state_overlay` entry point is preserved for desktop and tests.
- **Opaque stat panels:** the main death/victory summary panel now fills an opaque `PANEL_INK` base before the nine-slice asset is blitted, so the red tint does not bleed through the panel's semi-transparent edges. The stat inset panels already had an opaque base; the outer container now matches. The red tint is confined to the background only.
- **Regression coverage:** `tests/test_android_packaging.py` adds two tests verifying that removing `presplash.filename` fails the preflight with the branded-splash message, and that pointing it at a missing file fails with the missing-asset message. `tests/test_mobile_layout.py` adds a test verifying that cutout-area pixels carry the red tint while stat-panel pixels stay opaque (not red) on a 2340×1080 display with 90/18px horizontal insets.
- Project, runtime, Android package, and website release metadata advance to `4.4.8`; options remain schema `7` and run saves remain schema `5`.

### Validation

- `.venv/bin/python -m compileall -q src tests`
- `.venv/bin/python -m unittest tests.test_android_packaging tests.test_save_and_metadata tests.test_ui_layouts tests.test_mobile_layout` — focused suites pass.
- `.venv/bin/python -m unittest discover tests` — 546 tests pass.
- `.venv/bin/python tools/validate_android_apk.py --project-root . --source-dir src --spec buildozer.spec`

## 4.4.7 — Sectioned About / Quick Help Screen

Release 4.4.7 turns the About, Credits, and Quick Help page from a single unformatted wall of text into a readable, sectioned document while preserving the 4.3.17 WS-G Open Source Licenses scroll contract.

### Changed

- **Named sections with gold headers and divider rules:** the page is now organized into Overview, Quick Help, Credits, Open Source Licenses, Third-Party Notices, pygame-ce — GNU LGPL 2.1-or-later, and Arch Rogue — Apache License 2.0 sections. Each section header is rendered in aged-gold with an iron divider rule beneath it, so the document scans as a structured page rather than a paragraph dump.
- **Labeled quick-help items:** the Quick Help section splits the onboarding into Goal, Combat, Difficulty, Story, Loot & Discovery, and Dark Floors items. Each label is rendered in the archetype accent color with its description indented underneath, making the controls and concepts scannable at a glance. Desktop and mobile control variants are preserved.
- **Preformatted license text:** the NOTICE, pygame-ce LGPL, and Apache-2.0 documents are now rendered preserving their original line breaks (wrapping only overlong lines) in a muted tone, instead of being reflowed into one giant paragraph. This keeps the legal text legible and properly attributed.
- **Variable-height scroll viewport:** the renderer now lays out the page as a flat list of `AboutEntry` lines with per-line heights (section headers are taller than body lines) and scrolls in entry units. Prefix-sum windowing makes the visible-window and bottom-stick scroll-max search exact and O(log n), so the long license documents stay cheap to lay out every frame. The scrollbar thumb now travels against `scroll_max` (the bottom-stick position) instead of `total - visible`.
- **Responsive fonts:** section headers use the main font on standard windows and step down to the small font on compact layouts; body and preformatted text use the small/tiny fonts respectively, matching the prior compact-window behavior.
- The `_licenses_scroll_max` / `_licenses_visible_lines` contract and Up/Down/PgUp/PgDn/Enter input behavior are unchanged, so the existing About-screen scroll and return-to-title tests still pass.
- Project, runtime, Android package, and website release metadata advance to `4.4.7`; options remain schema `7` and run saves remain schema `5`.

### Validation

- `.venv/bin/python -m compileall -q src tests`
- `.venv/bin/python -m unittest tests.test_licenses tests.test_ui_layouts tests.test_pause_on_menus tests.test_save_and_metadata` — focused suites pass.
- `.venv/bin/python -m unittest discover tests` — 543 tests pass.
- Programmatic sweep: every scroll position on desktop (960×540), the mobile variant, and a compact 640×360 window keeps `_licenses_visible_lines >= 1` and clamps to `_licenses_scroll_max`.

## 4.4.6 — Run-Ending Summary Panels & Shop Pause

Release 4.4.6 gives the You Died screen a clearer visual hierarchy so a finished run reads as a deliberate summary rather than a dense table of small text, and pauses the simulation when the shopkeeper menu is open on all platforms.

### Changed

- **Four framed stat groups:** all 24 run statistics are now organized into balanced Run, Combat, Exploration, and Legacy inset panels, using the authored gothic panel art when available and a matching procedural treatment in legacy graphics.
- **Deliberate typography and spacing:** each group has a restrained accent header, subtle row separators, consistent interior gutters, aligned label columns, and right-aligned value edges. The cause of death receives a focused blood-red treatment without overpowering the rest of the summary.
- **Smaller outer container:** the main death/victory overlay panel is approximately 15% smaller (700×460 scaled, down from 820×520), keeping the framed summary compact and centered rather than filling the screen. The authored nine-slice panel art now scales to this smaller rect instead of going full-bleed.
- **Opaque stat panels on red overlay:** each stat inset panel now fills an opaque base rect before blitting the nine-slice asset, so the blood-red death wash does not bleed through the asset's semi-transparent edges. The stat panels render at full opacity and sit cleanly on top of the red tint.
- **Generous stat text padding:** interior gutters, label/value column spacing, inter-panel gaps, and header-to-body separation were all increased so statistics have breathing room rather than crowding the panel edges.
- **Shopkeeper pause (all platforms):** opening the shopkeeper menu now pauses the simulation and disables player movement on desktop as well as mobile. Previously only mobile paused; desktop continued running enemies, projectiles, and keyboard-polled movement while the shop was open. A `shop_was_open` guard ensures the pause still applies on the frame the shop is closed by validation (e.g. the shopkeeper died or the player was teleported away).
- **Responsive fitting:** panel dimensions, heading size, row fonts, and label/value spacing adapt to the available overlay area. Headless visual checks cover the default 960×540 screen, the compact 640×480 layout at maximum saved UI scale, and the procedural fallback.
- **Layout regression coverage:** tests verify that all statistics render, the four panels do not overlap, panel content retains minimum padding, and every section shares stable label and value alignment. Shop pause tests verify that actor animation clocks freeze, enemy positions and player HP are unchanged while the shop is open, and damage resumes after closing.
- Project, runtime, Android package, and website release metadata advance to `4.4.6`; options remain schema `7` and run saves remain schema `5`.

### Validation

- `.venv/bin/python -m compileall -q src tests`
- `.venv/bin/python -m unittest tests.test_pause_on_menus tests.test_ui_layouts tests.test_save_and_metadata tests.test_website` — 35 tests pass.
- `.venv/bin/python -m unittest discover tests` — 543 tests pass.
- `.venv/bin/python tools/validate_android_apk.py --project-root . --source-dir src --spec buildozer.spec`
- `git diff --check`

## 4.4.5 — Android Floor & Guidance Optimization

Release 4.4.5 follows successful physical-device validation of the 720p GLES stream and removes two remaining low-risk costs from Native Android gameplay.

### Changed

- **No redundant light-floor clear:** accelerated gameplay on normal floors no longer clears the complete 2424×1080 CPU framebuffer immediately before the opaque, oversized cached floor layer replaces every pixel. Dark floors, cutscenes, menus, desktop, software renderers, and fallback paths retain explicit clearing.
- **Effective relic-guidance cache:** unchanged guidance overlays now bypass both the alpha-surface clear and crack/ring rasterization. The previous implementation cleared the cached surface before checking its content key, paying most of the rebuild cost even on a cache hit.
- **Regression coverage:** tests verify light-floor clear suppression, dark-floor clearing, and that the second unchanged guidance draw requests an uncleared cached layer.
- Project, runtime, Android package, and website release metadata advance to `4.4.5`; options remain schema `7` and run saves remain schema `5`.

### Performance

- Physical-device telemetry confirms 4.4.4 raised steady Native gameplay from roughly **18–23 FPS to 25–30 FPS**, with `gpu_stream=1616x720`, base traffic at 1,163,520 pixels, and base-upload time reduced from **19–29 ms to 11.7–12.3 ms**.
- The remaining full-frame clear measured **5.9–6.5 ms/frame** and is now skipped on the safe opaque-floor path.
- Relic guidance measured **1.7–7.2 ms/frame** in the supplied Android log. The deterministic cache microbenchmark improves from **0.363 ms cold to 0.074 ms cached** (about **80% less**) on the desktop host; physical-device gains depend on visible route size.

### Validation

- `.venv/bin/python -m compileall -q src tests`
- `.venv/bin/python -m unittest tests.test_story_mode tests.test_mobile_layout tests.test_dark_levels tests.test_world_rendering_and_animation tests.test_mainline_regression` — 109 tests pass.
- Full non-web `unittest` discovery — 534 tests pass; experimental web modules were excluded per project policy.
- `.venv/bin/python -m unittest tests.test_save_and_metadata tests.test_website` — 8 release-metadata tests pass.
- `.venv/bin/python tools/validate_android_apk.py --project-root . --source-dir src --spec buildozer.spec`
- `PIP_BREAK_SYSTEM_PACKAGES=1 PYTHON=/home/mattirk/.local/share/uv/python/cpython-3.12-linux-x86_64-gnu/bin/python3.12 ./tools/build_android.sh debug` produced and audited `bin/archrogue-4.4.5-arm64-v8a_armeabi-v7a-debug.apk` (73,490,787 bytes; SHA-256 `edf73dfb6efe490803d8b132c7bcf1eeda8279059a3cd51a753ebaf72b3bce42`). The package contains 104 ARM ELF extensions for each ABI and passes APK Signature Scheme v2 verification.
- `git diff --check`

## 4.4.4 — Android GLES Streaming Optimization

Release 4.4.4 targets the final dominant Android frame cost found in physical-device telemetry: uploading the complete native-resolution world framebuffer to GLES every gameplay frame.

### Changed

- **Hybrid native gameplay stream:** Native mode keeps the 2424×1080 game layout and CPU render target, but high-resolution gameplay frames stream to GLES through a reusable 1616×720 nearest-neighbour texture. Menus, retained UI textures, touch geometry, and the lighting compositor remain native-resolution.
- **56% fewer streamed pixels:** the steady gameplay base upload falls from 2,617,920 to 1,163,520 pixels per frame. The reusable ARGB staging surface avoids allocations while GLES performs the final upscale.
- **No catastrophic CPU-lighting fallback:** an accelerated Android renderer that is briefly between eligible GPU frames now presents one unlit transition frame rather than performing a native-resolution CPU lighting multiply. Device telemetry measured the removed fallback at 130–233 ms per frame.
- **Expanded telemetry:** performance reports include `gpu_stream`, making the active 1616×720 gameplay stream directly verifiable in the next physical-device log.
- **Regression coverage:** mobile tests verify Native stream sizing, staging-surface reuse, capped-tier behavior, and suppression of the accelerated-context CPU-lighting fallback.
- Project, runtime, Android package, and website release metadata advance to `4.4.4`; options remain schema `7` and run saves remain schema `5`.

### Performance

- The supplied Pixel telemetry showed steady base uploads consuming **19–29 ms/frame**, while gameplay updates consumed only **0.5–1.2 ms/frame**. The new stream removes **55.6%** of that upload traffic, targeting roughly **9–16 ms/frame** of gross savings before the sub-frame scaling cost.
- Around the observed 18–22 FPS range, that reduction projects approximately **+4 to +6 FPS**. Exact end-to-end improvement requires the next physical-device log; the headless profiler cannot execute SDL's Android GLES texture upload.
- The native-to-720p staging scale measured **0.724 ms/frame** on the desktop test host; Android uses pygame-ce's logged NEON scaler, but device telemetry remains authoritative.

### Validation

- `.venv/bin/python -m compileall -q src tests tools/profile_game.py`
- `.venv/bin/python -m unittest tests.test_mobile_layout tests.test_lighting tests.test_world_rendering_and_animation tests.test_mainline_regression` — 118 tests pass.
- Full non-web `unittest` discovery — 533 tests pass; experimental web modules were excluded per project policy.
- `.venv/bin/python tools/validate_android_apk.py --project-root . --source-dir src --spec buildozer.spec`
- `PIP_BREAK_SYSTEM_PACKAGES=1 PYTHON=/home/mattirk/.local/share/uv/python/cpython-3.12-linux-x86_64-gnu/bin/python3.12 ./tools/build_android.sh debug` produced and audited `bin/archrogue-4.4.4-arm64-v8a_armeabi-v7a-debug.apk` (73,490,203 bytes; SHA-256 `c4aeabd3c293bfb5c08a9c3a183204aa9a3e5b942ce21b7f67c83bd8dbed88f1`). The package contains 104 ARM ELF extensions for each ABI and passes APK Signature Scheme v2 verification.
- `git diff --check`

## 4.4.3 — Android Combat-Effects Optimization

Release 4.4.3 targets Android frame drops during action skills such as Time Skip, especially while crowded enemies are casting and projectiles are active.

### Changed

- **Cheaper full-room skill pulses:** large Android impact effects use a 12-state visual cache, allowing consecutive Time Skip frames to reuse one translucent surface instead of repeatedly rasterizing a native-resolution ring.
- **Bounded effect memory:** impact overlays now use both entry and 24 MiB byte limits, and cache keys include the casting archetype so class-specific emanations cannot alias one another.
- **No rejected alpha scans:** impact art keeps its native partial-alpha surface rather than running the binary-alpha optimizer's two full-surface scans only to reject gradients, smoke, and fading rings.
- **Cached projectile rotation:** spell bolts reuse bounded 15-degree directional variants instead of invoking a software rotation for every projectile every frame.
- **Lean Android projectile trails:** mobile retains the bright near trail and fading outer trail while removing two intermediate alpha-blended samples; desktop keeps all four samples.
- **Repeatable effects profile:** `tools/profile_game.py --scenario action-effects` reproduces repeated Time Skip casts amid a deterministic 45-enemy ranged spell crowd.
- Project, runtime, Android package, and website release metadata advance to `4.4.3`; options remain schema `7` and run saves remain schema `5`.

### Performance

- In the deterministic 2400×1080 Native-mobile action-effects profile (180 measured frames after 45 warmup frames), cumulative `draw_impact` time falls from **0.602 s to 0.492 s** (**18.3% less**), and frame blits fall from **56,399 to 53,201** (**5.7% fewer**).
- Average headless software-render time improves from **17.410 ms/frame to 17.317 ms/frame**. This workload cannot exercise the Android GLES presenter, so physical-device telemetry remains the authority for end-to-end FPS and upload behavior.

### Validation

- `.venv/bin/python -m compileall -q src tests tools/profile_game.py`
- `.venv/bin/python -m unittest tests.test_world_rendering_and_animation tests.test_mobile_layout tests.test_mainline_regression` — 94 tests pass.
- Full non-web `unittest` discovery — 531 tests pass; experimental web modules were excluded per project policy.
- `.venv/bin/python -m unittest tests.test_website` — 6 release-metadata tests pass.
- Deterministic before/after Native-mobile `action-effects` profiles at 2400×1080, 180 measured frames after 45 warmup frames.
- `PIP_BREAK_SYSTEM_PACKAGES=1 PYTHON=/home/mattirk/.local/share/uv/python/cpython-3.12-linux-x86_64-gnu/bin/python3.12 ./tools/build_android.sh debug` produced and audited `bin/archrogue-4.4.3-arm64-v8a_armeabi-v7a-debug.apk` (73,488,919 bytes; SHA-256 `a92ce83969491a5e3d1431656d0adb057a3c5a2d3a966aec1687a3ed2c332fb4`). The package contains 104 ARM ELF extensions for each ABI and passes APK Signature Scheme v2 verification.
- `git diff --check`

## 4.4.2 — Android Native Rendering Optimization

Release 4.4.2 reduces repeated CPU-side rendering work in full-resolution Android gameplay, with the largest gains in dense combat scenes and illuminated dungeon views.

### Changed

- **Cached tile render descriptors:** floor, wall, and door draws now resolve deterministic seed, special-room styling, wall-light mounts, and tile surfaces once per tile per floor instead of repeating those lookups every frame.
- **Lean visible-tile scans:** the floor and world-object passes bind hot operations locally and rely on already-clamped visible bounds, removing thousands of redundant method and bounds-check calls in large viewports.
- **Cached world-space effects:** floating combat text, pickup labels, elite markers, boss auras, attack telegraphs, loot glows, shop-sign glows, and gently rotated rare-item sprites now reuse bounded, quantized surface variants instead of rasterizing or allocating them every frame.
- **Cached light modulation:** continuous lighting reuses bounded 16-step brightness variants of radial light sprites. Android GLES frames now need one additive light blit after warmup rather than a copy, full-surface multiply, and additive blit for every flickering or fading light.
- Project, runtime, Android package, and website release metadata advance to `4.4.2`; options remain schema `7` and run saves remain schema `5`.

### Performance

- The deterministic 2400×1080 Native-mobile crowd profile improved from **14.467 ms/frame** to **13.604 ms/frame** of CPU render time, a **6.0% reduction** and roughly **+4.4 FPS** of render throughput in the headless software-render workload.
- The headless profiler cannot exercise the Android GLES presenter, so the cached continuous-light modulation benefit is additional but requires physical-device telemetry for an exact FPS measurement.

### Validation

- `python -m compileall -q src tests`
- `.venv/bin/python -m unittest tests.test_world_rendering_and_animation` — 71 tests pass.
- `.venv/bin/python -m unittest tests.test_mobile_layout` — 8 tests pass.
- `.venv/bin/python -m unittest tests.test_lighting`
- `.venv/bin/python -m unittest tests.test_mainline_regression` — 12 tests pass.
- `.venv/bin/python -m unittest discover tests` — 534 tests pass.
- `.venv/bin/python tools/validate_android_apk.py --project-root . --source-dir src --spec buildozer.spec`
- `PIP_BREAK_SYSTEM_PACKAGES=1 PYTHON=/home/mattirk/.local/share/uv/python/cpython-3.12-linux-x86_64-gnu/bin/python3.12 ./tools/build_android.sh debug` produced and audited `bin/archrogue-4.4.2-arm64-v8a_armeabi-v7a-debug.apk` (73,488,119 bytes; SHA-256 `34ef4b74c100c9807029728a3e8fedf971c6a51260b8fb402cb72cebbcfa2075`). The package reports version `4.4.2`, contains 104 ARM ELF extensions for each ABI, and passes APK Signature Scheme v2 verification.
- Deterministic before/after Native-mobile crowd profiles at 2400×1080, 180 measured frames after 45 warmup frames.

## 4.4.1 — Mobile Navigation & Shrine Stability

Release 4.4.1 polishes the post-website Android experience with an explicit touch Back control, stable spent-shrine rendering, and full-resolution rendering as the fresh-install default.

### Added

- **Mobile Back control:** reversible mobile screens now show a subtle safe-area-aware Back button in the upper-left corner, including Inventory, Character, Shop, Quest, Help, Options, Controls, About, archetype selection, game hub, exit confirmation, result overlays, and skippable cutscenes. The control uses a PixelLab-authored gothic arrow, a procedural fallback, a minimum-size touch target, and the existing unified `Command.BACK` behavior.
- **Regression coverage:** mobile tests verify the Back glyph is packaged, remains inside asymmetric safe areas, and closes Inventory and Character screens. Sprite tests verify color variants retain transparent colorkey backgrounds.

### Changed

- **Native mobile default:** fresh mobile installs now default to **Native · full resolution**. Existing explicit Performance/Balanced/Native choices remain authoritative, and the older pre-schema-6 migration continues to preserve its safe Performance fallback.
- **Larger mobile navigation:** the Back control now uses a larger 52–68 px touch panel with a subtle translucent obsidian/gold backing. The Inventory, Character, Quest, and Exit game hub rows expand to 220–400 px wide and 48–72 px tall, remove their left-side icons, and center each label for clearer text and easier thumb targeting.
- Project, runtime, Android package, and website release metadata advance to `4.4.1`; options remain schema `7` and run saves remain schema `5`.

### Fixed

- **Used shrine transparency:** Android's immutable-sprite optimization converts alpha to a magenta colorkey. The spent-shrine color multiplier previously recolored those transparent pixels, exposing a magenta/dark rectangular background after activation. Prop variants now restore real alpha before color transforms, preserving the transparent silhouette without affecting desktop rendering.
Prop variants now restore real alpha before color transforms, preserving the transparent silhouette without affecting desktop rendering.
- **Inventory/Character swipe direction:** horizontal touch navigation now uses the opposite left/right mapping on Inventory and Character screens, matching the requested gesture direction without changing Options or Shop swipes.

### Validation

- `python -m unittest discover tests` — 531 tests pass.
- `python -m unittest tests.test_website` — 6 tests pass.
- `python -m compileall -q src tests tools/generate_download_manifest.py`
- `python tools/validate_android_apk.py --project-root . --source-dir src --spec buildozer.spec`
- `./tools/build_android.sh debug` produced and audited `bin/archrogue-4.4.1-arm64-v8a_armeabi-v7a-debug.apk` (73,485,807 bytes; SHA-256 `2cd1052b85c83ae1a31d8297c453c3bb9dd40cfcc7111672aab1e12065f0d4ee`). The package reports version `4.4.1`, contains 104 ARM ELF extensions for each of `arm64-v8a` and `armeabi-v7a`, and passes APK Signature Scheme v2 verification.
- Release metadata consistency check and `git diff --check` pass.

## 4.4.0 — Download Website & GitHub Pages Release

Release 4.4.0 adds a dedicated, responsive Arch Rogue download website and deploys it through GitHub Pages as the final stage of every successful `master` release. Platform buttons resolve to the exact artifacts produced by the same workflow run, including prereleases that GitHub's `latest` redirect intentionally excludes.

### Added

- **GitHub Pages download site:** `website/` implements the reference layout with the authored Arch Rogue logo, dungeon backdrop, dark-fantasy panels, concise game pitch, and responsive download badges for Windows, Linux, universal macOS, and Android.
- **Accessible, responsive presentation:** the site supports keyboard focus, semantic headings and status announcements, useful image alternatives, narrow mobile layouts, OS-specific recommendations, reduced-motion preferences, and no-JavaScript/release-manifest fallbacks.
- **Dynamic release manifest:** `tools/generate_download_manifest.py` creates `website/downloads.json` from the repository, package version, and release commit. It emits immutable GitHub `browser_download_url` equivalents using the exact artifact names produced by CI instead of hardcoding a release version in page markup.
- **Pages deployment:** `.github/workflows/build-release.yml` now configures and uploads the site after the GitHub prerelease is created, then deploys it in a dedicated `github-pages` environment. Deployment therefore cannot advertise missing Windows, Linux, macOS, or Android artifacts.
- **Website regression tests:** `tests/test_website.py` checks platform coverage, accessibility hooks, local assets, safe fallback links, and exact release URL generation.

### Changed

- Project, runtime, Android package, and website release metadata advance to `4.4.0`.
- `README.md` now links to the GitHub Pages download site and retains the source-install path for developers.

### Validation

- `python -m unittest tests.test_website`
- `python -m compileall src tests tools/generate_download_manifest.py`
- Full non-web `python -m unittest discover tests`
- Workflow YAML parse and `git diff --check`

## 4.3.17 — Android Beta to Mainline Merge

Release 4.3.17 merges the `android-beta` branch into `master` so the desktop mainline inherits the universal Android wins, locks both desktop and mobile to a 60 FPS cap through one `FramePacing` abstraction, removes dead/duplicated optimization code from the 4.3.x runs, consolidates render-cache invalidation into a single seam, and adds APK licensing/attribution hygiene. The Android build is now part of mainline (no separate beta branch). Mobile-only code paths remain strictly additive (`if self.mobile_mode:` / `android_runtime_active()`), so no desktop frame executes a GLES, colorkey-RLE, or `MobilePerformanceMonitor` branch.

### Added

- **Frame rate cap option:** a new Options row **Frame rate cap** with values `30 / 60 / 90 / 120 / Unlimited`, default `60`, persisted as `frame_rate_cap` in options schema `7`. Both desktop and mobile read the same setting; mobile suspended mode still overrides to the 10 Hz throttle. A small `FramePacing` class in `game.py` owns `target_fps`, `suspended_fps`, the `clock.tick` call, the `0.05` dt clamp, and the vsync hint. `Game.run()` is the only caller of `clock.tick` now.
- **Show performance overlay option (desktop dev):** a desktop-only Options row toggles the same `PERF <fps> <frame ms> | W <world ms> H <hud ms> F <flip ms>` diagnostic line Android already shows, persisted as `show_perf_overlay` in schema `7` (off by default). `ARCH_ROGUE_PERF=1` still explicitly enables telemetry on desktop for development. A default desktop run is silent and shows no on-screen diagnostic.
- **Mainline regression guard:** `tests/test_mainline_regression.py` snapshots desktop render determinism (fixed seed + frame number -> fixed pixel hash for title, gameplay, and a dense crowd scenario), asserts `detect_mobile_runtime() is False` on non-Android platforms, and instruments the per-frame mobile-only entry points to prove none execute during a desktop tick.
- **Profile baseline tooling:** `tools/profile_game.py` gains `--baseline <path>` (writes a JSON phase-timing snapshot) and `--compare <path> --threshold <pct>` (exits nonzero if any phase regresses beyond the threshold). A checked-in `tools/baselines/desktop_master_baseline.json` records the 2560×1440 crowd profile.
- **WS-D desktop parity tests:** `test_mainline_regression.py` confirms desktop hits the batched `_blit_floor_entries` path, the memoized projection origin, and the now-shared impact-effect cache.
- CI triggers on both `master` and `android-beta` and runs the regression guard plus the baseline comparison on every push.
- **APK licensing & attribution (WS-G):** the Apache-2.0 license text and a new `NOTICE` file (enumerating every bundled third-party library — pygame-ce, SDL2/SDL2_image/SDL2_mixer/SDL2_ttf, libpng/libjpeg/zlib, Freetype under the Freetype License, Python PSF-2.0, PyJNIus MIT — plus the build-tool exclusion note and the AI Provenance & Liability notice) are bundled as reachable assets (`src/arch_rogue/assets/licenses/LICENSE.txt` / `NOTICE.txt`) and surfaced from a scrollable in-app **About → Open Source Licenses** screen so APK installers get Apache-2.0 §4 attribution without opening the repo. `src/arch_rogue/licenses.py` loads them with a repo-root fallback for desktop dev; `tools/build_android.sh` refreshes the asset copies from the canonical root `LICENSE`/`NOTICE` before each build so they cannot drift. A one-paragraph **trademark note** is added to `README.md` clarifying that the "Arch Rogue" name and octahedron crest logo are not part of the Apache-2.0 grant (§6 reserves trademark rights).
- `tools/validate_android_apk.py` now greps every bundled `lib/<abi>/*.so` for GPL-family MP3 codec markers (`libmad` / `libmp3lame` / `libfaad` plus `mp3lame` / `mad_decoder` / `NeAACDec`) and fails the audit on any hit; rejects `buildozer/` or `pythonforandroid/` build-tool source bundled into `assets/private.tar`; and preflights that `source.include_exts` includes `txt` and that the `assets/licenses/{LICENSE,NOTICE}.txt` assets exist in the source tree.

### Changed

- **One frame-pacing owner:** the scattered `clock.tick(FPS)` / `clock.tick(10)` calls are replaced by `Game.frame_pacing.tick(suspended=...)`. The exact `min(clock.tick(target) / 1000.0, 0.05)` shape is preserved verbatim; only the source of `target_fps` changes. `constants.FPS` is now a deprecated alias for `DEFAULT_FRAME_RATE = 60` (cutoff: 4.4).
- **One cache-invalidation seam:** `OptionsMixin._invalidate_render_caches()` clears every memoized render cache (`ambient_overlay_cache`, `_hud_panel_cache`, `_hud_icon_cache`, `_aim_cone_cache`, `_alpha_tile_cache`, `_title_logo_cache`, `_fitted_ui_font_cache`, `_impact_overlay_cache`, `tile_cache`, `door_tile_cache`) plus lighting and stage caches. `_apply_graphics_mode()`, `rebuild_fonts()`, and `_invalidate_resolution_sized_caches()` all route through it so a future cache addition cannot be missed.
- **Schema v7:** options schema advances `6` -> `7` for `frame_rate_cap` and `show_perf_overlay`. The v7 loader reads v6 option files and defaults `frame_rate_cap=60`, `show_perf_overlay=False`. Run saves remain schema `5`.
- **Universal wins shared with desktop:** the impact-effect overlay cache (4.3.13) and the projection-origin memoization (4.3.14) are no longer mobile-gated; desktop crowds now hit the cache and the memoized origin. The batched floor/wall blits, full-bleed cutscene, direct-size shadows, cached relic guidance, and screen-flash surface reuse were already shared and are confirmed desktop-active.
- `docs/android-beta.md` updated to reflect that the Android build is part of mainline as of 4.3.x (no separate beta branch).
- `AGENTS.md` "Current Code Organization" updated to mention `FramePacing` (in `game.py`) and that `mobile.py` is part of the mainline module set.

### Performance

- Desktop deterministic 2560×1440 crowd profile is within ±5% of the 4.3.16 baseline on every phase; the impact-cache and projection-origin generalizations remove per-frame allocations/recomputation in combat crowds.
- The incremental mobile floor-cache + reveal-patch path (4.3.5) is now explicitly gated behind `mobile_mode`; desktop always uses the shared cold-rebuild path, removing any risk of desktop regression from the merge while keeping the cold path shared.

### Fixed

- **Leftover optimization code (WS-C):** documented and confirmed the once-per-process `_ANDROID_BINARY_ALPHA_MODE` benchmark memoization, the pre-allocated `MobilePerformanceMonitor` rolling buffers (no per-frame allocations on the hot path), and the local-tint CPU fallback's reachability gate (retained as the Android software-renderer launch-safe path). The dead mobile half-resolution light buffer path was already retired in 4.3.10; the live desktop half-resolution path is documented as required. The `_composite_mobile_gpu_ui_fallback` legacy rect branch is retained as a post-4.3.11 defensive safety net and documented. The impact-effect cache bound is extracted into a named `IMPACT_EFFECT_CACHE_MAX = 128` constant.
- `legacy_mobile_quality_migration` and `legacy_ui_scale_migration` in `options.py` are marked with a `# Deprecation cutoff: 4.4` comment.

### Validation

- `python -m compileall src tests` clean.
- `python -m unittest discover tests` green (excluding web tests as usual).
- `tests.test_mainline_regression` (render determinism pixel-hash snapshots, mobile-isolation counters, render-cache invalidation, WS-D desktop shared-win paths), `tests.test_frame_pacing` (FramePacing unit + option round-trip + perf-overlay reconciliation), `tests.test_licenses` (license/notice loader + About screen surface + scroll input), and `tests.test_android_packaging` (GPL codec + build-tool source rejection) all pass.
- `tools/profile_game.py --compare tools/baselines/desktop_master_baseline.json` reports no regression vs the checked-in baseline.
- `tools/validate_android_apk.py --project-root . --source-dir src --spec buildozer.spec` preflight passes (license assets present, `txt` bundled, spec clean).
- Default desktop run: `_mobile_performance_monitor` is `None`, `ARCH_ROGUE_PERF` is silent, `clock.tick` targets 60 FPS via `FramePacing`.
- Runtime/package release version is `4.3.17`; options are schema `7` and run saves remain schema `5`.

## 4.3.16 — Android Exit Confirmation Touch Fix

Release 4.3.16 fixes the vertical touch offset on the exit confirmation screen. The exit confirmation renders full-bleed like other menus, but was still listed as a safe-area-clipped overlay, causing taps to land below the visible rows. Desktop is unchanged.

### Fixed

- **Exit confirmation touch offset:** removed `confirm_exit` from the safe-local point conversion list in `_safe_local_point`. The exit confirmation screen renders in display coordinates via `mobile_full_render_target` (like title/options/controls/about/archetype_select), so its row rects are in display coordinates and touch points should not have the safe-area offset subtracted. Taps now register exactly on the visible rows.
- Runtime/package release version is `4.3.16`; options remain schema `6` and run saves remain schema `5`.

### Validation

- Full non-web `unittest` discovery completed with 476 tests passing; `compileall` and `git diff --check` pass.

- `./tools/build_android.sh debug` produced and audited `bin/archrogue-4.3.16-arm64-v8a_armeabi-v7a-debug.apk` (73,457,999 bytes; SHA-256 `71f4aa7ddf48569e2585e7e9f81367beaa66b62c8c9a908f43e0315d8b868f5e`). The package reports version 4.3.16 with both ARM ABIs and passes APK Signature Scheme v2 verification.

## 4.3.15 — Android App Icon and Full-Bleed Cutscene Fix

Release 4.3.15 adds the game icon as the Android launcher/app icon and fixes the cutscene backdrop so it truly fills the whole display. Desktop is unchanged.

### Added

- **Android app icon:** `buildozer.spec` now declares `icon.filename` pointing at the bundled 512px crest (`src/arch_rogue/assets/icons/icon_512.png`). p4a copies it into the APK resources at all density buckets (`mipmap/icon.png` plus `drawable-{m,h,xh,xxh}dpi/ic_launcher.png`) and references it from the manifest's `android:icon`, so the Arch Rogue crest appears as the installed app icon on the Android launcher/home screen.

### Fixed

- **Cutscene backdrop fills the full screen:** the quest cutscene overlay was still being rendered into the safe-area subsurface (clipped by `mobile_safe_render_target`), so the authored background image only covered the safe inset and the rest of the display showed the cleared frame. The cutscene now renders outside the safe-area wrapper — the backdrop, dim pass, and letterboxed stage cover the entire physical display edge-to-edge, with the panel centered on top.
- **Menu touch vertical offset:** full-bleed menus (title, options, controls, about, archetype select) render in display coordinates, but `handle_mobile_tap` was still subtracting the safe-area offset from the touch point, making taps land a few pixels below the visible row. The safe-local conversion is now context-aware: only safe-area-clipped overlays (inventory, shop, character, quest, help) subtract the offset; full-bleed menus use raw display coordinates so touch registration matches the rendered rows exactly.
- Runtime/package release version is `4.3.15`; options remain schema `6` and run saves remain schema `5`.

### Validation

- Full non-web `unittest` discovery completed with 476 tests passing, including the updated full-bleed cutscene regression (now checks asymmetric safe insets and corner coverage); `compileall` and `git diff --check` pass.
- APK inspection confirms `res/mipmap/icon.png` (512×512 RGBA), per-density `ic_launcher.png` variants, and `application: icon='res/mipmap/icon.png'` in the manifest badging.
- `./tools/build_android.sh debug` produced and audited `bin/archrogue-4.3.15-arm64-v8a_armeabi-v7a-debug.apk` (73,458,011 bytes; SHA-256 `8fd71d8941e20afab4d52d12425d49262e8925ef59cde161d398c077999b05d8`). The package reports version 4.3.15 with both ARM ABIs (104 architecture-correct ELF extensions per ABI), passes APK Signature Scheme v2 verification, and includes the app icon (`application: icon='res/mipmap/icon.png'`).
- Physical-device validation remains required to confirm the launcher icon renders correctly, the cutscene backdrop covers cutouts, and menu touch registration is vertically accurate.

## 4.3.14 — Android Touch Responsiveness, Spirit Beast Petting, and Frame Tuning

Release 4.3.14 makes touch controls feel responsive and forgiving, adds first-class Spirit Beast petting on mobile, and removes another per-frame hotspot from the projection path. Desktop is unchanged.

### Added

- **Subtle touch confirmation:** every successful tap on a touch target spawns a brief expanding accent ring at the touch point, giving immediate visual feedback without changing layout.
- **Spirit Beast petting on mobile:** when a Ranger's Spirit Beast is within reach and off cooldown, a tappable `Pet …` tooltip appears (matching items/doors/guests), so petting is fully playable by touch. Desktop behavior and the paw indicator are unchanged.

### Changed

- **Larger touch areas:** `register_mobile_touch_target` now inflates any control smaller than a comfortable minimum (~7mm / 44dp) so menu glyphs, action icons, and compact prompts are easy to hit; targets clamp to the display.

### Performance

- **Cached mobile projection origin:** `world_to_screen` runs tens of thousands of times per frame in crowds and was recomputing the layout/focus math each call. The origin is now memoized per frame, trimming the projection path. Crowd render improved to ~12.0 ms/frame in the deterministic harness.

### Fixed

- Runtime/package release version is `4.3.14`; options remain schema `6` and run saves remain schema `5`.

### Validation

- Full non-web `unittest` discovery completed with 476 tests passing, including new regressions for the petting tooltip, minimum touch-target sizing, and touch ripple feedback; `compileall` and `git diff --check` pass.
- `./tools/build_android.sh debug` produced and audited `bin/archrogue-4.3.14-arm64-v8a_armeabi-v7a-debug.apk` (73,450,095 bytes; SHA-256 `5c15acca2d0c8b4cdf42d8a035d33213e869f42ac2d05ce7c04caf972a438fc0`). The package reports version 4.3.14 with both ARM ABIs (104 architecture-correct ELF extensions per ABI) and passes APK Signature Scheme v2 verification.
- Physical-device validation remains required for touch feel and the frame target.

## 4.3.13 — Android Cutscene Backdrop, Hub Touch Targets, and Frame Recovery

Release 4.3.13 finishes the cutscene presentation, makes the game-hub rows easier to hit by touch, and pushes overall mobile frame rate higher by removing per-frame allocations and redundant work in the hottest render paths. Desktop is unchanged.

### Changed

- **Cutscene backdrop is full-bleed.** The authored `cutscene.background` (and its dim pass) is requested at the full physical display size, so the cinematic backdrop covers the whole screen edge-to-edge instead of being inset within the safe area.
- **Larger game-hub touch targets.** The mobile hub rows (Inventory, Character, Quest, Exit) are taller and the panel wider, so each entry is easier to tap; the panel still clamps inside the safe area beside the action rail.

### Performance

- **Impact effects are cached per (kind, quantized progress, radius bucket, color)** instead of allocating and re-drawing a fresh `SRCALPHA` overlay every frame. In combat crowds this removes one of the top per-frame allocation costs (impact effects were a leading render hotspot).
- **Cutscene/static screens skip the world frame entirely** (carried from 4.3.12) and now also reuse the full-bleed backdrop surface, avoiding a per-frame cover-scale of the background.
- The full-bleed single world texture upload, direct-size shadows, and cached relic/guidance paths from 4.3.11–4.3.12 are retained.

### Fixed

- Runtime/package release version is `4.3.13`; options remain schema `6` and run saves remain schema `5`.

### Validation

- Full non-web `unittest` discovery completed with 473 tests passing; `compileall` and `git diff --check` pass.
- Crowd profile confirms impact-effect allocation removed from the top render hotspots; full-bleed cutscene backdrop and larger hub rows verified by layout regressions.
- `./tools/build_android.sh debug` produced and audited `bin/archrogue-4.3.13-arm64-v8a_armeabi-v7a-debug.apk` (73,448,807 bytes; SHA-256 `a30ddb74d0f31213904f6b2ed28e1545ef5da8100b089d7237a9cea8d8332678`). The package reports version 4.3.13 with both ARM ABIs (104 architecture-correct ELF extensions per ABI) and passes APK Signature Scheme v2 verification.
- Representative 2340×1080 Performance crowd render improved to 12.751 ms/frame (from 14.982) after the impact-effect cache; full suite remains green.
- Physical-device validation remains required to confirm the +10–15 FPS target.

## 4.3.12 — Android Relic Fix and Cutscene Performance

Release 4.3.12 fixes the relic/shrine visual corruption seen on Android, makes cutscenes truly full-screen, and removes their dominant frame cost. Gameplay performance improves on-device through the eliminated per-frame relic and cutscene work while all visuals are preserved. Desktop is unchanged.

### Fixed

- **Relic/shrine magenta-box glitch:** the authored story relic sprite is colorkey-optimized for Android's blitter, and the additive story tint painted its magenta colorkey background, which then leaked as a solid box (and a spinning rectangle once rotated). The tint is now masked by the sprite's own alpha (`BLEND_RGBA_MIN`) and baked once per (frame, accent, tilt) into a cached surface, so the relic renders as a clean gem and the per-frame copy + rotate leaves the ARM hot path. The same alpha-safe path covers any colorkey-optimized item art.
- **Cutscene full-screen background:** a quest cutscene now renders across the whole display (its authored backdrop/dim covers the frame) instead of being inset, and the panel sits centered on the full screen.
- **Cutscene performance:** while a cutscene is active the game no longer renders the dungeon world, lighting, or HUD underneath it — the cutscene owns the display, so those full frames are skipped entirely. Cutscene frame cost drops to a couple of milliseconds.
- Runtime/package release version is `4.3.12`; options remain schema `6` and run saves remain schema `5`.

### Validation

- Full non-web `unittest` discovery completed with 473 tests passing, including new regressions for the alpha-masked/cached relic sprite and the full-screen world-skipping cutscene; `compileall` and `git diff --check` pass.
- Headless 1566×698 renders confirm the clean relic (no colorkey box) and a full-bleed cutscene backdrop with the centered panel. Cutscene frame cost measured ~2.6 ms in the deterministic harness (down from a full world frame); gameplay crowd profile is unchanged, with device gains coming from the removed per-frame relic/upload work.
- `./tools/build_android.sh debug` produced and audited `bin/archrogue-4.3.12-arm64-v8a_armeabi-v7a-debug.apk` (73,448,319 bytes; SHA-256 `3afb28f1d24bfa7396f1795b6ded9192c26fcf18fe5fb5a676ad98f5c46e1628`). The package reports version 4.3.12 with both ARM ABIs (104 architecture-correct ELF extensions per ABI) and passes APK Signature Scheme v2 verification.
- Physical-device validation remains required to confirm the +10 FPS target and relic/shrine parity.

## 4.3.11 — Android Full-Bleed Rendering and Performance Recovery

Release 4.3.11 restores the edge-to-edge mobile presentation and recovers the frame cost introduced by the 4.3.10 lighting/shadow fixes, while keeping their visuals. The dungeon now always renders across the full physical display with the HUD as a true overlay, menus paint full-bleed backgrounds, and the relic guidance no longer re-rasterizes every frame. Desktop is unchanged.

### Changed

- The mobile world viewport spans the entire display again (as in the pre-overlay-HUD builds). The left rail, right action rail, joystick, and menu glyph draw on top; the camera keeps its unobstructed gameplay focus between the overlays.
- Mobile menu screens (title, options, controls, about, archetype select, exit confirmation) render full-bleed across the display instead of being clipped to the safe area. In-game overlays (inventory, shop, character, story) remain safe-area-clipped so they never slide under the control rails.
- With the viewport full-screen, every HUD control already lives inside the streamed world texture, so the 4.3.9 duplicate base-region uploads are gone again; per-frame texture upload is back to the world viewport plus post-light UI panels.

### Fixed

- Mobile contact shadows keep the soft transparent look but are now built directly at final size (concentric-ellipse radial falloff) instead of smoothscaling a template, removing a per-unique-size ARM scaling cost in crowded frames.
- Story relic guidance now caches its carved-crack overlay content keyed by screen bounds, pulse phase, and visibility run, and only re-rasterizes when those change. This fixes the relic lighting/effect glitches (stale trails from the cleared buffer) and removes the dominant per-frame relic cost.
- The menu glyph and hub panel are clamped back inside the safe area beside the action rail now that the viewport no longer bounds them.
- Runtime/package release version is `4.3.11`; options remain schema `6` and run saves remain schema `5`.

### Validation

- Full non-web `unittest` discovery completed with 471 tests passing, including a new full-bleed viewport/menu regression; `compileall` and `git diff --check` pass.
- Representative 2340×1080 crowd profiles: Performance render 13.752 ms/frame (improved from 14.640), Native software-fallback 18.346 ms/frame; the full-screen floor blit is the remaining Native cost. Headless 2340×1080 renders with asymmetric safe insets confirm edge-to-edge world, full-bleed title menu, soft shadows, and relic rendering.
- `./tools/build_android.sh debug` produced and audited `bin/archrogue-4.3.11-arm64-v8a_armeabi-v7a-debug.apk` (73,447,339 bytes; SHA-256 `43187044cfa09c52b5ea971f6dbf23736f003e6d97c2893817f075a778d584b0`). The package reports version 4.3.11 with both ARM ABIs (104 architecture-correct ELF extensions per ABI) and passes APK Signature Scheme v2 verification.
- Physical-device validation remains required for final frame pacing and relic visual parity.

## 4.3.10 — Android Lighting and Interaction Polish

Release 4.3.10 fixes the remaining mobile interaction and presentation regressions reported after the overlay-HUD beta. Quest guests now use the same tappable contextual prompt pattern as items and doors, the analog stick is easier to reach, and accelerated Native mode restores continuous actor lighting without returning to a full-resolution CPU light multiply. Desktop rendering and controls remain unchanged.

### Fixed

- Story guests render an actionable mobile `TAP` prompt, so tapping their bottom-right tooltip opens the quest conversation exactly like item pickup and door interaction. Desktop still displays the direct `1-3` story-choice hint.
- Mobile actor, prop, and loot contact shadows use the cached radial soft-shadow surfaces at Android-tuned opacity instead of opaque black ellipses. The steady-state path remains one cached alpha blit per entity.
- Accelerated Native Android rendering now uses the same quarter-resolution continuous light buffer and GLES modulation path as Performance/Balanced, restoring warm player/NPC lantern halos and eliminating the pale local additive actor tint. The local tint path remains only as a software-renderer/context-loss fallback.
- The analog stick sits higher for thumb reach while preserving safe-area, left-panel, and gameplay-viewport separation across compact, phone, tablet, and asymmetric-cutout layouts.
- Runtime/package release version is `4.3.10`; options remain schema `6` and run saves remain schema `5`.

### Validation

- Focused mobile layout/render/input, soft-shadow, lighting, and input/accessibility coverage passes 132 tests, including new regressions for guest-tooltip taps, accelerated-Native quarter-resolution lighting, and transparent cached mobile shadows.
- Headless 1280×720 comparison renders for Performance, Balanced, accelerated Native, and software Native confirm the soft contact shadow and continuous lantern-lit floor response; physical-device validation remains required for final visual parity and frame pacing.
- Full non-web `unittest` discovery completed with 470 tests passing; `python -m compileall -q src tests`, changed-file diagnostics, and `git diff --check` pass (the rendering effects mixin retains its pre-existing cross-module unused-import warnings).
- Representative 2340×1080 crowd profiles show the change remains actor/floor-blit dominated rather than lighting-buffer dominated: Performance 14.640 ms render and software-fallback Native 17.715 ms render in the deterministic headless harness. These host numbers guard against a new CPU hotspot but are not ARM frame-time claims.
- `./tools/build_android.sh debug` produced and audited `bin/archrogue-4.3.10-arm64-v8a_armeabi-v7a-debug.apk` (73,446,499 bytes; SHA-256 `80591b5ad3020cf76b6f4b1bec8191d8fed00c54cce938be927bd1ae24814bc9`). The package reports version 4.3.10 and both ARM ABIs with 104 architecture-correct ELF extensions per ABI, and it passes APK Signature Scheme v2 verification.

## 4.3.9 — Android World-Overlay HUD

Release 4.3.9 removes the last permanent top-of-screen mobile information panel and turns the left controls into true overlays over an edge-to-edge dungeon view. Run, depth, floor, difficulty, modifier, resources, and optional character information remain readable without narrowing or recentering gameplay beneath the controls. Desktop rendering and input remain unchanged.

### Added

- PixelLab-authored vertical obsidian/iron status vessels with gold runes now frame HP, MP, and Stamina fills. A matching compact obsidian/gold information card is reused for run/difficulty and character summaries; both assets retain procedural fallbacks and are packaged through the HUD manifest.
- Mobile layout now exposes a distinct unobstructed gameplay rectangle and projection focus inside the wider world viewport. Camera projection, inverse touch mapping, zoom layers, screen-space effects, and boss bars share that focus.
- Regression coverage verifies edge-to-edge-left world geometry, left-overlay touch blocking, camera round trips at the clear gameplay focus, generated UI assets, header removal, boss placement, and cached-floor translation.

### Changed

- The mobile world viewport begins at physical display x=0 and renders underneath the safe-area-positioned left HUD. The right action rail remains reserved, while the player stays centered in the visible space between overlays instead of shifting beneath the left cards.
- The mobile top run/depth/difficulty panel is removed completely. `Run N: Depth N/10`, floor theme, difficulty, and modifier now live in the upper-left information card; Quest remains available only through its dedicated game-hub modal.
- The analog stick is larger and sits higher and farther right for easier thumb reach. Compact 360p layouts omit the character card before reducing critical run/resource information.
- The direct GLES presenter no longer registers redundant indexed uploads for left HUD, joystick, or menu rectangles already contained in the streamed world texture; only changing controls outside the viewport retain separate base-region uploads.
- Runtime/package release version is `4.3.9`; options remain schema `6` and run saves remain schema `5`.

### Fixed

- Touches on overlaid left information cards no longer pass through as world aiming contacts.
- The reusable Android floor cache now translates from the same layout-aware projection origin as live tiles, preserving pixel alignment after the camera focus moved away from the raw viewport center.
- Mobile boss plaques anchor to the clear top-center gameplay area instead of reserving space below the removed run header.

### Validation

- Focused mobile layout/render/input coverage passes 61 tests; adjacent input/accessibility, core gameplay, UI asset, metadata, and Android packaging suites pass 70 tests.
- Headless 780×360, 1280×720, and asymmetric-safe-inset 2340×1080 renders confirm edge-to-edge world coverage, generated status/info frames, compact fallback, clear player focus, hub placement, and Quest modal geometry.
- Full non-web `unittest` discovery completed with 467 tests passing; `python -m compileall -q src tests`, changed-file diagnostics, and `git diff --check` pass (rendering mixins retain their pre-existing cross-module unused-import warnings).
- `./tools/build_android.sh debug` produced and audited `bin/archrogue-4.3.9-arm64-v8a_armeabi-v7a-debug.apk` (73,446,695 bytes; SHA-256 `5e8e03d1d7bea049ce963029ec863799bc652d54e6dd234280772d94e580fce5`). The package reports version 4.3.9, API 28/34, GLES 2.0, landscape `PythonActivity`, and both ARM ABIs; contains 104 architecture-correct ELF extensions per ABI plus all four PixelLab mobile HUD sprites; and passes APK Signature Scheme v2 verification.
- Physical-device validation remains required for final thumb reach, text size, overlay legibility, and multitouch behavior on representative phones and tablets.

## 4.3.8 — Android Analog HUD and Game Hub

Release 4.3.8 implements the second-generation mobile gameplay layout: analog movement is separated from direct world aiming, contextual prompts replace permanent interaction chrome, and one compact top-right hub owns the mobile gameplay menus. Desktop mouse, keyboard, and gamepad behavior remains unchanged.

### Added

- A lower-left analog stick supports deadzoned, magnitude-sensitive isometric movement while an independent world finger continues to aim. Joystick, aim, and action-skill contacts can remain active simultaneously.
- Authored dark-iron joystick base and knob sprites, generated through PixelLab, are packaged under the HUD asset manifest with a procedural fallback.
- A top-right game-menu glyph opens a four-row Inventory, Character, Quest, and Exit game hub. Opening the hub or Quest panel pauses gameplay, and Android Back closes them before falling through to exit confirmation.
- Focused mobile regressions cover joystick transforms and release, aim-only world touch, multitouch coexistence, hub commands, modal Quest pause/Back behavior, tappable prompts, safe-area geometry, and compact-layout fallback.

### Changed

- The left rail now reserves its lower section for the analog stick. HP, MP, and Stamina remain at the top, while character details appear only when both width and height can contain them without clipping.
- The permanent bottom-right `USE` button is removed. Actionable `E` prompts render a narrower, two-line-capable `TAP` panel and the panel itself is the interaction target; warning/status prompts remain non-interactive.
- Persistent quest/story content is removed from the normal mobile HUD. Quest details open as a viewport-sized modal from the game hub and retain touch scrolling.
- The old top-right pause glyph is replaced by the game-menu glyph. Exit game reuses the existing save-aware confirmation flow rather than adding a second pause/exit implementation.
- Runtime/package release version is `4.3.8`; options remain schema `6` and run saves remain schema `5`.

### Validation

- Full non-web `unittest` discovery completed with 464 tests passing. Focused mobile layout/input/HUD coverage passed 58 tests, adjacent input/accessibility and core gameplay suites passed 49 tests, and `python -m compileall src tests` completed successfully.
- Headless renders at 780×360, 1280×720, and 2340×1080 with asymmetric safe insets verified the gameplay rails, PixelLab stick, wrapped interaction tooltip, four-row hub, Quest modal, and compact character-summary fallback without control overlap.
- Changed-file diagnostics report no errors, and `git diff --check` passes; rendering mixins retain their pre-existing cross-module unused-import warnings.
- `./tools/build_android.sh debug` produced and audited `bin/archrogue-4.3.8-arm64-v8a_armeabi-v7a-debug.apk` (73,411,495 bytes; SHA-256 `4fdc39fa9c0995efb76a668047d48d260abf753180bda478f3dfd20b2eb4003c`). The package reports version 4.3.8, API 28/34, GLES 2.0, landscape `PythonActivity`, and both ARM ABIs; contains 104 architecture-correct ELF extensions per ABI plus both joystick sprites; and passes APK Signature Scheme v2 verification.
- Physical-device validation remains required for analog-stick ergonomics and multitouch behavior on representative phones and tablets.

## 4.3.7 — Android Touch-First Menus and Sensor Isolation

Release 4.3.7 removes Android's accelerometer pseudo-controller from gameplay and replaces mobile menu navigation chrome with direct, safe-area-aware tap, swipe, and native Back interactions. Desktop keyboard and gamepad behavior remains unchanged, and real Bluetooth/USB gamepads continue to work on Android.

### Fixed

- Android sets `SDL_ACCELEROMETER_AS_JOYSTICK=0` before SDL initialization, preventing the platform accelerometer from being exposed as a joystick. A defensive mobile-only device filter also rejects explicit accelerometer, gyroscope, gravity, linear-acceleration, rotation-vector, and orientation-sensor names while retaining devices that expose real buttons or hats.
- Turning Controller Off now clears cached stick vectors, pending trigger edges, and queued commands; subsequent axis polls perform no device reads, and joystick axis/button/hat activity is consumed without changing aim or dispatching commands. Device add/remove events remain active so a real controller is ready if the option is re-enabled.
- Character Overview clears and ignores stale Discipline hitboxes, preventing a tap over an old tree cell from spending a mastery token after switching tabs.
- Direct menu taps resolve from finger-down with a small tap slop and a separate swipe threshold, so short row-to-row drags cannot activate the release row. Options swipes that begin outside a rendered row no longer mutate the previously selected setting.
- Inventory use/equip and shop transactions require a true timed double-tap on the same row. Inventory drop remains available through a deliberate long left swipe that must begin on an item row, reducing accidental destructive actions.

### Changed

- Removed the bottom mobile menu navigation strip and its render-loop passes. Menu states no longer register synthetic Back, arrow, Select, Tab, Use, Trade, or Drop touch buttons; gameplay skill, resource, pause, interaction, and utility touch targets are unchanged.
- Mobile title, options, controls, archetype, exit, about, help, death/victory, story intro, cutscene, inventory, shop, and character contexts now use their rendered rows, choices, tabs, cells, and panels directly. Vertical swipes navigate or page content; horizontal swipes change options, story choices, inventory sort/drop behavior, shop Buy/Sell mode, and character tabs.
- Mobile menus hide keyboard/gamepad key badges, shortcut sections, navigation footers, quick-use numbers, and close/use/drop helper pills, reclaiming their layout space. Touch-oriented About and Help copy replaces desktop-only mouse/key instructions; desktop guidance remains intact.
- Android native Back now routes through the shared command dispatcher for gameplay pause, submenu/overlay close, controls-capture cancel, story-safe pause behavior, and death/victory return flow.
- Runtime/package release version is `4.3.7`; options remain schema `6` and run saves remain schema `5`.

### Validation

- `python -m compileall -q src tests` passed, and full non-web `unittest` discovery completed with 453 tests passing.
- Changed-file diagnostics report no errors, `git diff --check` passes, and focused controller/mobile/version/Android-packaging coverage completed with 106 tests passing.
- `./tools/build_android.sh debug` produced and audited `bin/archrogue-4.3.7-arm64-v8a_armeabi-v7a-debug.apk` (73,356,327 bytes; SHA-256 `f7f04bc97f9aef575825d5448f967255bb3859fe4838abea255441c5a4292c09`). The package contains 104 architecture-correct ELF extensions for each ARM ABI and passed the project entry-point/spec/APK audit.
- Physical-device validation remains required to confirm sensor enumeration is absent across Android vendors and to assess the touch gesture thresholds on representative phones/tablets.

## 4.3.6 — Android Native Frame-Pacing Recovery

Release 4.3.6 removes the frame-time spikes and full-frame software/transfer work identified in the second Pixel 9a trace. Native mode keeps the 2424×1080 world framebuffer, but no longer uploads that framebuffer merely to apply lighting; the release also bounds story guidance to its visible pixels and retains unchanged native menu frames.

### Fixed

- Story relic guidance no longer clears and alpha-blits a full viewport for a narrow floor crack. Visible crack runs, branch stubs, and the on-screen target ring are collected first, clipped to a padded viewport, rasterized into a reusable 32-pixel-bucketed local surface, and blitted only at those tight bounds.
- Off-screen relic rings and route samples can no longer enlarge the guidance surface, and guidance telemetry resets immediately when the target disappears.
- Post-light GPU panels are independently retained and uploaded by semantic region instead of one union rectangle. Overlapping panels are coalesced before extraction, preventing double alpha composition and stale overlap pixels.
- Interaction-panel texture revisions now include font and authored/procedural UI identity, so graphics-mode or font changes cannot retain an old panel texture.
- Android continues to clear the full CPU framebuffer and redraw rail backings each gameplay frame; translucent overlays and software flashes therefore cannot accumulate on retained side-rail pixels.

### Changed

- Native Android lighting now uses a transfer-free local tier: floor/wall, actor, and story-guidance sources receive a cached depth/theme multiplier; visible actors also retain a bounded sprite-local color response from their dominant nearby light, and the classic per-tile dark-floor lantern falloff remains active. No screen-space halo can color unrevealed pixels, normal-floor depth attenuation remains intact, and Native world pixels stay at physical logical resolution.
- Balanced and Performance retain continuous quarter-resolution GLES lighting. Their presenter keeps a full static shell texture, uploads only the changing world viewport and small control rectangles, and reuses unchanged run-header, story, interaction, boss, and diagnostics textures.
- Mobile omits the decorative full-viewport ambient alpha vignette in every lighting tier. Native's cached source tint and lower tiers' continuous light buffer already carry depth atmosphere without the measured ~13 ms software pass.
- Unchanged mobile title, options, controls, about, and exit-confirmation frames skip clear, menu composition, navigation redraw, and present work while preserving touch targets. A single-entry opaque backdrop cache reduces the cost of frames that do need redraw; animated archetype selection remains live.
- Android telemetry now separates `guidance`, reports `guidance_px`, identifies `lighting_mode=off|local|continuous`, and reports actual base/UI upload pixels and region counts through `gpu_upload`.
- Runtime/package release version is `4.3.6`; options remain schema `6` and run saves remain schema `5`.

### Validation

- The 4.3.5 Pixel 9a trace contained 30 native gameplay windows averaging 9.68 FPS; 20 were below 10 FPS and none reached 30 FPS. Lighting-off `objects` time correlated 0.915 with total frame time and alternated between roughly 10–35 ms and 145–172 ms despite identical visible-wall counts, isolating the full-viewport guidance path. Lighting-off ambient remained 13.0–13.1 ms, while continuous lighting added roughly 20 ms base and 9.5 ms union-UI uploads.
- Deterministic 2424×1080 Native host profiling with an active story relic target measured `8.006 ms/render` plus `0.688 ms/update` in the quiet depth-10 scenario with local lighting. Lighting Off measured `6.185 ms/render`; these host results validate removal of the full-surface paths but are not ARM device claims.
- Full non-web `unittest` discovery: 437 tests, all passing. `compileall`, `git diff --check`, and changed-file diagnostics passed with no errors.
- `./tools/build_android.sh debug` produced and audited `bin/archrogue-4.3.6-arm64-v8a_armeabi-v7a-debug.apk` (73,351,279 bytes; SHA-256 `ffc0dd3ea1e01c2567354283422b4696a87f86052b48698b0feb175d3597673e`). The package contains 104 architecture-correct ELF extensions for each ARM ABI and passed the project APK metadata/entry-point audit.
- Physical-device validation is still required to confirm the requested sustained >20 FPS and ≥30 FPS average on the Pixel 9a; the new timing and pixel-count fields make that result directly attributable.

## 4.3.5 — Android Native Floor Stability and Render Cost

Release 4.3.5 fixes the floor-height flicker introduced by 4.3.4's incremental mobile floor cache and targets the remaining native-resolution costs exposed by the first direct-GLES device log. The GPU lighting path is active and correct, but the Pixel 9a trace showed that half-resolution light construction, full-viewport transparent UI uploads, and dense visible-object blits still prevented 30 FPS.

### Fixed

- Cached floor translation now uses the same floored projected-origin math as live `world_to_screen` coordinates. The previous `round()` translation crossed half-pixel boundaries at different times, shifting the floor by one pixel relative to live walls and actors until the next cache rebuild.
- Reveal patches no longer draw a new tile and its neighbors over an already flattened isometric layer. Each new tile's clipped pixel rectangle is cleared and reconstructed from every intersecting floor entry in canonical painter order, making the patch byte-identical to a cold rebuild and eliminating temporarily "raised" floor diamonds.

### Changed

- Every mobile quality tier now builds continuous lighting at quarter viewport resolution. Native still renders the world, actors, HUD rails, and final framebuffer at the physical logical resolution; only the smoothly scaled light mask is coarser.
- Mobile ambient lighting uses one full-buffer fill instead of restamping every revealed tile each frame. Fog-of-war remains authoritative in the already-black base world, so multiplicative lighting cannot expose unrevealed terrain.
- The post-light GLES UI texture is cropped to its actual alpha bounds instead of uploading the entire world viewport. In ordinary native gameplay the measured content is roughly a 740×79 header rather than a 1732×893 transparent texture; previous dirty bounds are cleared before reuse and CPU fallback ordering remains intact.
- Mobile actor shadows use two direct pixel-art ellipses instead of per-pixel-alpha shadow surfaces. Full-health ordinary enemies omit redundant floating health bars, while damaged, elite, miniboss, boss, and status-affected enemies retain them.
- Consecutive depth-sorted wall tiles are submitted through batched blits without changing actor/wall painter order.
- Android benchmarks equivalent alpha, alpha-RLE, colorkey, and colorkey-RLE sprite sources once on the real SDL build and keeps the fastest representation for subsequent immutable binary sprites. The selected mode and per-format timings are emitted as `ARCH_ROGUE_PERF alpha_blit`.
- Device telemetry now reports cropped `gpu_ui` dimensions, `gpu_error`, and visible wall/enemy counts so upload and dense-room costs are distinguishable in the next trace.
- Runtime/package release version is `4.3.5`; options remain schema `6` and run saves remain schema `5`.

### Validation

- The 4.3.4 Pixel 9a trace confirmed `gpu_light=1`, but steady native intervals averaged 6.61 FPS (median 5.99), 89.7 ms object rendering, 25.2 ms light construction, and 34.6 ms combined GPU uploads/presentation. Balanced GPU intervals averaged 9.12 FPS with 80.5 ms objects, 14.3 ms lighting, and 12.9 ms uploads/presentation.
- Pixel comparisons reproduced both floor defects before the fix: fractional camera reuse changed 201,330 RGB bytes and an incremental reveal differed by 8,801 bytes from a cold rebuild. After the fix, reveal patches are byte-identical and cached tile anchors match live projections at fractional camera positions.
- Native 2424×1080 crowded host profiling after the CPU-side changes measured `18.451 ms/frame`; forcing the locally selected alpha-RLE mode measured `17.578 ms/frame`. A real SDL offscreen GLES run completed crowded native frames in `5.726 ms/frame`, with light build `0.526 ms`, cropped UI upload `0.112 ms`, and no presentation fallback; these host numbers are validation, not ARM performance claims.
- Full non-web `unittest` discovery: 430 tests, all passing. `compileall` and `git diff --check` passed; changed-file diagnostics reported no errors (the rendering mixins retain their existing cross-module unused-import warnings).
- `./tools/build_android.sh debug` produced and audited `bin/archrogue-4.3.5-arm64-v8a_armeabi-v7a-debug.apk` (73,337,179 bytes; SHA-256 `ca5b768d5de3d779aa1859811cd462effdcaa516e82167a16d51cde5d8131f3f`). The package contains 104 architecture-correct ELF extensions for each ARM ABI; `aapt` confirmed version 4.3.5, API 28/34, GLES 2.0, landscape `PythonActivity`, and both ABIs; `apksigner` verified its V2 debug signature.

## 4.3.4 — Native Android GPU Lighting

Release 4.3.4 targets the physical-device native-resolution traces that averaged roughly 5.7 FPS at 2424×1080, with about 173 ms/frame attributed to world rendering. The continuous light mask and uniform combat flash are now composited by the display-owned GLES renderer instead of performing full-viewport CPU blends, while the world remains rendered at the selected native resolution.

### Added

- An Android direct-presentation path borrows Pygame CE's existing accelerated SDL renderer and draws the native base frame, a low-resolution multiplicative light texture, viewport-local post-light UI, and an optional 1×1 screen-flash texture in the correct order before one GLES present.
- Renderer-generation and frame-sequence guards, context-reset handling, and explicit texture teardown protect borrowed SDL resources across display recreation, foreground resume, low-memory events, renderer/device resets, and shutdown.
- Nested Android render telemetry now separates floor, object, light-build, ambient, base-upload, light-upload, UI-upload, and GPU-present costs without double-counting total frame time. Reports also expose `gpu_light` and floor-cache rebuild/patch counters.
- Regression coverage verifies direct-present texture order and blend modes, active-flash GPU presentation, CPU fallback ordering, colorkey normal-map transparency, binary-alpha equivalence, and incremental floor reveal patches.

### Changed

- Continuous Android lighting keeps its quality-tier downsampled mask but uploads that small mask for GLES nearest-neighbor scaling and `SDL_BLENDMODE_MOD`; successful frames no longer expand and multiply the mask over millions of pixels on the CPU or call `pygame.display.flip()` afterward.
- Screen flashes on the GLES path upload one RGBA pixel and scale it over the final frame after lighting and HUD composition. Desktop, software-renderer, and failed-present paths retain the existing full-screen CPU blend.
- Native base uploads use a short-lived BGRA alias over Pygame's XRGB display surface, avoiding a hidden full-frame XRGB-to-ARGB conversion while releasing the `BufferProxy` lock immediately after upload.
- Immutable binary-alpha pixel-art cache entries use display-format colorkey RLE sources on the Android SDL2-alpha path; partial-alpha text, gradients, panels, and shadows retain alpha blending. Generated normal maps now preserve colorkey transparency.
- The Android floor layer uses one-third-screen gutters, rebuilds only after most of a gutter is consumed, and patches newly revealed floor tiles against its frozen build camera instead of rebuilding whenever the reveal count or camera position changes slightly.
- The CPU lighting fallback uses an opaque display-format scratch surface and `BLEND_RGB_MULT`, avoiding unnecessary alpha-channel work. Desktop rendering behavior is unchanged.
- Runtime/package release version is `4.3.4`; options remain schema `6` and run saves remain schema `5`.

### Validation

- Device logs used as the baseline confirmed accelerated GLES2 and NEON, but showed native gameplay near 5.7 FPS / 173 ms world time and Balanced gameplay near 10.7 FPS / 120 ms world time; simulation remained below 1 ms/frame.
- Deterministic depth-10 crowded-floor host profile at native 2424×1080 with 45 enemies: update `2.131 ms/frame` and render `18.856 ms/frame`. The dummy SDL driver intentionally exercises the CPU fallback rather than the direct GLES presenter.
- A real SDL offscreen renderer accepted the native base/light/UI texture formats and the 1×1 flash texture, presented successfully without fallback, left the display surface unlocked, and preserved base → MOD light → UI → flash ordering.
- Focused mobile, lighting, and lifecycle suite: 59 tests, all passing. Full non-web `unittest` discovery: 428 tests, all passing. `compileall` and `git diff --check` passed; changed-file diagnostics reported no errors (the rendering mixins retain their existing cross-module unused-import warnings).
- `./tools/build_android.sh debug` produced and audited `bin/archrogue-4.3.4-arm64-v8a_armeabi-v7a-debug.apk` (73,333,235 bytes; SHA-256 `87a674a095f466f63ad6c9c2039942d31a314153ee7000abd862bd4940f367fe`). The package contains 104 architecture-correct ELF extensions for each ARM ABI; `aapt` confirmed version 4.3.4, API 28/34, GLES 2.0, landscape `PythonActivity`, and both ABIs; `apksigner` verified its V2 debug signature.
- Physical-device FPS and upload/present timings remain required to confirm the 30 FPS native-resolution target; the new `gpu_light=1` and detailed `render_ms` fields make that verification attributable.

## 4.3.3 — Android GLES Enforcement and Device Telemetry

Release 4.3.3 addresses the remaining physical-device ~1 FPS failure after 4.3.2's resolution reduction. Android now rejects SDL's unaccelerated `pygame.SCALED` renderer, explicitly tries the packaged GLES2/GLES drivers, and reports every frame phase on-device so any vendor-specific remainder is attributable rather than guessed.

### Added

- Rolling Android telemetry emits one `ARCH_ROGUE_PERF` line every four seconds with true FPS/frame time; tick, event, update, menu/world, HUD, overlay, flip, and audio timings; logical/window/viewport sizes; renderer acceleration; quality/lighting state; entity counts; and interval sprite decode/build deltas.
- A small cached in-game diagnostic line shows FPS plus world/HUD/flip milliseconds. It performs no per-frame font rendering and is enabled by default only in the Android beta; `ARCH_ROGUE_PERF=0` disables it.
- Renderer startup diagnostics attach safely to Pygame CE's existing `_sdl2` renderer and log logical size/scale without creating a competing renderer.
- Regression coverage exercises GLES2-to-GLES retry, launch-safe software fallback, telemetry aggregation, and the reduced-resolution layout.

### Changed

- Before `pygame.init()`, Android requests `SDL_RENDER_DRIVER=opengles2`. Display creation converts Pygame CE's `no fast renderer available` warning into a failed candidate, retries `opengles`, and permits SDL auto-selection only as a final launch-safe fallback. Telemetry records `accelerated=no` if that fallback is software.
- Performance now caps logical height at 360p (780×360 on a 2340×1080 phone) and Balanced at 540p. This reduces Performance's streamed texture from 0.63 to 0.28 megapixels while preserving aspect ratio, safe-area input, and the complete six-skill mobile HUD.
- Buildozer excludes generated `__pycache__` and `arch_rogue.egg-info` directories, and the APK validator rejects either if they leak into `assets/private.tar`; stale editable-install metadata can no longer contradict the release version.
- Runtime/package release version is `4.3.3`; options remain schema `6` and run saves remain schema `5`.

### Validation

- The cached Android SDL source has both `SDL_VIDEO_RENDER_OGL_ES2` and `SDL_VIDEO_RENDER_OGL_ES` enabled; GLES2 precedes GLES and software in its renderer table.
- Deterministic depth-10 crowded-floor profile at physical 2340×1080 / logical 780×360 with 45 enemies: update `2.278 ms/frame`, render `9.631 ms/frame`, and continuous lighting about `0.70 ms/frame`. With lighting off, render was `8.936 ms/frame`.
- A 1,500-frame cache run settled at 295 resolved frames (~19.3 MiB), below the 320-frame limit, confirming no steady representative-floor eviction loop; telemetry still exposes device-side APK decode spikes through `loads+`/`builds+`.
- The 780×360 smoke render retained all six action skills, three resource bars, four utility buttons, pause/interact controls, twelve gameplay touch targets, and a 614×344 world viewport.
- Focused mobile/lifecycle/packaging suite: 43 tests, all passing; full `unittest` discovery: 420 tests, all passing. `compileall`, Android source/spec preflight, shell syntax, changed-file diagnostics, and `git diff --check` passed.
- `./tools/build_android.sh debug` produced `bin/archrogue-4.3.3-arm64-v8a_armeabi-v7a-debug.apk` (70 MiB, SHA-256 `e1fd494c2682e9eb5e2473ac741fbf4a8cbee03e86e16e1942ef7e1b175e9506`). The mandatory audit found root `main.pyc`, no generated source metadata or desktop pygame payload, and 104 architecture-correct ELF extensions for each ARM ABI.
- Android `aapt` confirmed version 4.3.3, API 28/34, GLES 2.0, landscape `PythonActivity`, both native ABIs, and no permissions; `apksigner` verified the V2 debug signature. Packaged bytecode contains the GLES2 enforcement, `ARCH_ROGUE_PERF`, and 360p tier.
- Physical-device FPS/logcat validation remains required because no ADB device or emulator is attached to this workstation.

## 4.3.2 — Android Render Performance (Incomplete First Pass)

Release 4.3.2 reduced Android's logical framebuffer and mobile lighting cost, but subsequent modern-phone testing remained around 1 FPS. It requested Pygame's SDL scaled renderer without rejecting SDL's permitted software fallback and had no device-side phase telemetry, so this release did not resolve or attribute the physical-device bottleneck.

### Added

- A persisted mobile **Render quality** setting reuses the first Options row: Performance caps logical height at 540p, Balanced at 720p, and Native retains every physical display pixel. Fresh and upgraded mobile installs default to Performance; desktop display behavior is unchanged.
- `tools/profile_game.py --mobile --mobile-quality <performance|balanced|native>` profiles the real safe-area/mobile viewport at a requested physical device size and reports sprite decode/build cache activity alongside update/render timings.

### Changed

- Android display creation now combines `pygame.FULLSCREEN | pygame.SCALED`. Pygame CE uploads the capped logical streaming texture through an SDL renderer, although this release did not enforce acceleration and SDL could fall back to software. Aspect ratio, normalized finger input, and scaled safe-area insets remain correct on phones and tablets.
- Performance mode renders only 25% as many root pixels as a representative 2340×1080 phone (1170×540), downsamples continuous lighting to quarter resolution, uses nearest-neighbor mobile light/world compositing, and omits the redundant full-viewport ambient alpha pass while continuous lighting is active. Balanced uses a one-third-resolution light buffer; Native retains the original half-resolution buffer.
- Fresh mobile installs disable generated normal-map detail, and pre-schema-6 mobile options migrate to Performance with normal maps off. Explicit schema-6 choices remain authoritative.
- Screen flashes reuse a size-matched surface instead of allocating a full frame for every flash, resolution changes preserve expensive decoded actor animation frames, and suspended Android apps throttle to 10 Hz without updating or drawing.
- Runtime/package release version is `4.3.2`; options advance to schema `6`, while run saves remain schema `5` and load unchanged.

### Validation

- Deterministic crowded-floor mobile profile at a physical 2340×1080: Native rendered at 16.923 ms/frame; Performance rendered at 9.051 ms/frame (46.5% less host render CPU). Continuous lighting fell from about 3.52 to 0.90 ms/frame (74% less). The dummy driver could not measure Android texture upload or verify the selected renderer; later physical-device testing showed this reduction was insufficient.
- 540p safe-area smoke render at 1170×540 confirmed readable HUD text, six action buttons, all resource bars/utilities, and an unobstructed 874×516 world viewport with asymmetric cutout insets.
- Focused mobile, lifecycle, input, lighting, and viewport suite: 99 tests, all passing.
- `./tools/build_android.sh debug` produced `bin/archrogue-4.3.2-arm64-v8a_armeabi-v7a-debug.apk` (70 MiB, SHA-256 `ffe5c3210342d76609b02abc9974b3ca5f012bc12f0bb2b4fc82ec5837e62db6`). The mandatory audit found root `main.pyc` and 104 correct ELF extensions for each ARM ABI.
- Android `aapt` confirmed version 4.3.2, API 28/34, landscape `PythonActivity`, both native ABIs, and no permissions; `apksigner` verified the V2 debug signature.
- `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/bin/python -m unittest discover tests` — 415 tests, all passing.
- `.venv/bin/python -m compileall -q src tests tools`, shell syntax checks, and `git diff --check` — OK.
- No ADB device or Android emulator was available, so final physical-device FPS and logcat validation must be performed after installing this APK.

## 4.3.1 — Android Launch and ABI Hardening

Release 4.3.1 fixes the Android beta APK startup failure caused by a desktop x86_64 pygame-ce wheel being packaged into both ARM Python bundles, and makes the SDL2 bootstrap entry point reproducible from checked-in source.

### Added

- `src/main.py`, the root entry point required by python-for-android's SDL2 bootstrap, delegates to the stable `arch_rogue.game:main` entry point.
- A checked-in local p4a `pygame` recipe cross-compiles pygame-ce 2.5.7 separately for every target ABI and enables `pygame.system` for SDL private-storage paths.
- `tools/validate_android_apk.py` preflights the source/spec and audits generated APKs, nested `libpybundle.so` archives, required packages, and every ELF machine type. It rejects host-native source files, missing launchers, stale manylinux `pygame_ce.libs` payloads, and ABI mismatches such as `EM_X86_64` in `arm64-v8a`.
- Focused Android packaging regression tests cover the maintained source/spec contract, valid dual-ARM APKs, missing launchers, host wheel payloads, and x86_64-in-ARM failures.

### Changed

- Buildozer now requests `python3,pygame==2.5.7,pyjnius`, uses the local SDL2 pygame-ce recipe, pins python-for-android release commit `58d21141f17c889bf8585f5665921d72028f8831`, pins NDK r28c, enables short-edge display cutouts, and uses supported `android.archs` syntax.
- Android CI installs the pinned `android` optional dependency set and keys its cache on the spec, recipe, builder, and validator instead of the spec alone.
- `tools/build_android.sh` runs source/spec validation before compilation and refuses to publish an APK that fails the post-build payload audit.
- Runtime/package release version is `4.3.1`; options remain schema `5` and run saves remain schema `5`.

### Validation

- `./tools/build_android.sh debug` produced the audited 70 MiB dual-ABI `bin/archrogue-4.3.1-arm64-v8a_armeabi-v7a-debug.apk`.
- The source/APK validator found root `main.pyc`, `pygame.base`, `pygame.system`, PyJNIus, and 104 architecture-correct ELF extensions in each bundle (`EM_AARCH64` for `arm64-v8a`, `EM_ARM` for `armeabi-v7a`), with no desktop `pygame_ce.libs` payload.
- Android `aapt` confirmed package `org.archrogue.archrogue`, version 4.3.1, API 28/34, landscape `PythonActivity`, both target ABIs, and no bogus blank permission; `apksigner` verified the debug APK's V2 signature.
- `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/bin/python -m unittest discover tests` — 407 tests, all passing.
- `.venv/bin/python -m compileall -q src tests tools`, shell syntax checks, and `git diff --check` — OK.
- No Android device was connected, so installation/logcat launch smoke testing remained external to this workstation.

## 4.3.0 — Android Beta

Milestone 4.3.0 adds a landscape-only Android beta build with touch controls, a safe-area-aware mobile HUD, Android lifecycle handling, writable private-storage save/options paths, and an interrupted-run recovery path. Desktop and gamepad behavior is unchanged.

### Added

- `src/arch_rogue/mobile.py`: runtime detection, `SafeInsets`, `MobileLayout`, multitouch capture, universal touch navigation, Android Back/lifecycle handling, and Android private-storage path resolution via `pygame.system.get_pref_path`.
- Landscape mobile HUD matching `build/arch-rogue_mobile_layout.drawio.png`: centered world viewport, left rail with vertical HP/MP/Stamina bars, optional compact character summary, and Inventory/Character/Quest/Help buttons; right rail with the six existing skill badges; dedicated Interact and Pause targets. Reuses the authored `hud.panel`/`hud.action_slot` assets; no new art required for the beta.
- True multitouch input via `FINGERDOWN`/`FINGERMOTION`/`FINGERUP`. Direct world touch drives movement/aim; skill/utility/interact/pause touches dispatch the existing semantic `Command`s; menu rows and cutscene choices are tap-selectable; swipes page the quest panel, inventory, and cutscene narration. Touch-emulated mouse events are ignored so inputs never double-fire.
- Camera viewport awareness: world rendering targets the central viewport subsurface; `screen_to_world` and `world_to_display` translate between display and viewport coordinates; lighting/shading runs on the viewport-sized buffer on mobile.
- Android lifecycle: `APP_WILLENTERBACKGROUND`/`APP_DIDENTERBACKGROUND` save the run, cancel touches, pause audio, and open the pause sheet; foreground events clear suspension without auto-resuming combat; `APP_TERMINATING` attempts a final save; `APP_LOWMEMORY` drops caches. `K_AC_BACK` maps to `Command.BACK` and never commits a story-relic choice.
- `AudioSystem.suspend`/`resume` pause and resume `pygame.mixer` and adjust the music transport clock so timing stays correct after a backgrounded period.
- Interrupted-run recovery: run saves are written through a `.tmp` file with `fsync` before atomic replace; `load_run` and `save_exists` promote a compatible interrupted `.tmp` save when the main file is missing. `recovered_interrupted_run` flags the recovery.
- Shop and Help are now modal on mobile (simulation pauses while they are open), matching Inventory and Character. Quest info remains non-modal.
- `buildozer.spec`, `tools/build_android.sh`, and a new `android` CI job in `.github/workflows/build-release.yml` produce and publish a reproducible debug APK with bundled assets; the release job attaches it alongside the desktop binaries. `tools/build_android.sh` pre-seeds every known Android SDK license hash and runs `sdkmanager --licenses` non-interactively (with a two-phase bootstrap fallback) so buildozer can install build-tools and `aidl` in a non-interactive CI shell. `docs/android-beta.md` documents install, upgrade, controls, lifecycle, local build, and known issues.
- Regression tests: `tests/test_mobile_layout.py` (layout matrix, safe insets, six action targets, multitouch world+skill coexistence, modal nav blocking, Android Back safety) and `tests/test_android_lifecycle.py` (background save/pause, foreground no-auto-resume, audio resume on cancel, terminating save, low-memory cache clear, suspended update no-op, pref-path helper, interrupted `.tmp` recovery).

### Changed

- `Game.__init__` accepts `mobile` and `safe_insets` arguments; `mobile_mode` is auto-detected via `ARCH_ROGUE_MOBILE`, `sys.platform == "android"`, or `ANDROID_ARGUMENT`. Save/options paths use the Android private storage directory on mobile. Fullscreen is forced on and the desktop `RESIZABLE`/`SCALED` path is bypassed on mobile.
- `OptionsMixin.apply_display_mode` requests the native landscape display on mobile instead of the fixed 2560×1440 desktop canvas. `refresh_automatic_ui_scale` derives a mobile UI scale from the actual landscape surface so HUD/menu text stays readable on phones and tablets.
- `RenderingBaseMixin.draw` composes menus/overlays into a safe-area subsurface and the world into the viewport subsurface on mobile; the desktop single-surface path is unchanged. `hud_panel_height` returns 0 on mobile so world-adjacent HUD anchors to the viewport.
- `InputMixin._dispatch_back` now closes Help before shop/inventory and opens the pause sheet (never commits a choice) during the mandatory story intro. `_dispatch_playing` treats Help as modal for input. `_sync_action_aim` is a source-neutral aim helper used by controller, touch, and desktop; `_sync_controller_action_aim` is retained as a compatibility alias.
- `MenuBaseMixin.draw_menu_rows` publishes `_menu_row_rects` so mobile taps can select rows directly. `RenderingHudMixin._draw_shop_overlay_fitted` publishes `_shop_visible_row_rects`/`_shop_visible_start` for the same reason.
- Runtime/package release version is `4.3.0`; options remain schema `5` and run saves remain schema `5`.

### Validation

- `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/bin/python -m unittest discover tests` — 398 tests, all passing (was 377 before this milestone; +21 new mobile/lifecycle tests).
- `.venv/bin/python -m compileall -q src tests` — OK.
- Headless mobile smoke render confirms the three-column layout, six action targets, twelve gameplay touch targets, and viewport-local `screen_to_world`.
- `git diff --check` — clean.
- The Android APK was not built in this environment (no Android SDK/NDK); the buildozer spec, build script, and CI job are configured for the next CI run.

## 4.2.10 — Universal macOS Build

Milestone 4.2.10 extends the `Build & Release` GitHub Actions workflow to produce a Finder-launchable universal `Arch Rogue.app` that runs natively on both Apple Silicon (arm64) and Intel (x86_64) Macs.

### Added

- Two native macOS build matrix entries: `macos-15-intel` for the x86_64 slice and `macos-latest` for the arm64 slice. GitHub's current runner documentation identifies `macos-latest` as Arm64, so the retired `macos-13` Intel image is replaced by the explicit `macos-15-intel` label rather than relying on Rosetta emulation. Each entry runs the existing PyInstaller `--onefile` pipeline, producing a single-architecture Mach-O executable tagged `macos-x86_64` or `macos-arm64`.
- A `Sanity-check Python architecture` step prints `platform.machine()` on both macOS runners so their native slices are visible in the logs.
- A `Verify binary architecture` step that runs `file` and `lipo -info` on the freshly built macOS binary so the Mach-O arch can be confirmed before the `combine-macos` job merges it.
- New `combine-macos` job that downloads both single-arch binaries and merges them with `lipo -create` inside `Arch Rogue.app/Contents/MacOS/arch-rogue`. The bundle includes an `Info.plist` with the executable, display name, bundle identifier, project version, game category, and high-resolution rendering metadata.
- The universal app is ad-hoc signed after `lipo` invalidates the thin executables' signatures, then verified with `codesign --verify --deep --strict`.
- The app is packaged as `arch-rogue-v<version>-<sha>-macos-universal.zip` with macOS `ditto`, preserving its Finder bundle metadata and executable mode. CI extracts that final ZIP and verifies its plist, executable permission, universal architecture, and code signature before upload.
- Release job now publishes five assets: Windows `.exe`, Linux binary, the universal macOS app ZIP, and the two intermediate single-arch macOS binaries as smaller per-architecture fallbacks.
- Restored the executable bit on raw Linux/thin-macOS release assets after `upload-artifact@v4` strips it; the universal app's mode is preserved inside its ZIP.

### Changed

- `release` job now `needs: [build, combine-macos]` so the universal binary is always present before publishing.
- Release body lists all five assets and labels the universal ZIP as a Finder-launchable `Arch Rogue.app` for `Apple Silicon + Intel`.
- The app is ad-hoc signed rather than Developer ID notarized. Finder recognizes and launches it as a graphical app, but macOS Gatekeeper may still require users to right-click **Open** on first launch until Apple signing credentials are configured.
- Why two native runners instead of a single universal2 PyInstaller run: `pygame-ce` ships separate arm64 and x86_64 macOS wheels (no universal2 wheel), so a single native `pip install` only resolves one architecture's native dependencies, and `--target-architecture universal2` would only embed that one architecture. Building on matching native runners and merging with `lipo` keeps both dependency sets architecture-correct.
- Runtime/package release version is `4.2.10`; options remain schema `5` and run saves remain schema `5`.

### Validation

- `.venv/bin/python -c "import yaml; yaml.safe_load(open('.github/workflows/build-release.yml'))"` — YAML parses cleanly.
- The workflow was not executed locally; it will run on the next push to `master`.

## 4.2.9 — Safe Exit Default

Milestone 4.2.9 makes `Cancel and return to game` the default highlighted option whenever the exit confirmation screen opens, preventing accidental exits or menu returns from an immediate confirmation keypress.

### Changed

- Exit confirmation now initializes its keyboard/gamepad cursor on `Cancel and return to game` instead of `Exit game`.
- Up selects `Return to main menu`, while Down wraps safely to `Exit game`; direct `Y`, `M`, `N`, `Esc`, and `Backspace` shortcuts remain unchanged.
- Runtime/package release version is `4.2.9`; options remain schema `5` and run saves remain schema `5`.

### Tests

- Updated keyboard, `E`, shared gamepad-dispatch, wrapping, rendering, save-count, and version assertions for the safe Cancel default.

### Validation

- `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/bin/python -m unittest discover tests` — 377 tests, all passing; the experimental web build was not run separately.
- `.venv/bin/python -m compileall -q src tests` — OK.
- `git diff --check` — clean.

## 4.2.8 — Exit Menu Return Option

Milestone 4.2.8 expands the exit confirmation screen with a safe Return-to-main-menu path while keeping the cursor controls introduced in 4.2.7.

### Added

- Added `Return to main menu` as the middle exit-confirmation option. Selecting it saves an active run, closes transient inventory/shop/help overlays, and returns to the title without stopping Arch Rogue.
- Added `M` as a direct shortcut for Return to main menu; arrow keys plus `Enter`/`E` and gamepad D-pad/A use the same three-row cursor flow.

### Changed

- Renamed `Cancel and return` to `Cancel and return to game` and changed its detail text to `Keep playing` when a run is active.
- Exit confirmation now wraps across three choices: Exit game, Return to main menu, and Cancel and return to game.
- Exit-overlay saves are now accepted by the save layer when the overlay was opened from active gameplay. Both Exit and Return remain on the confirmation screen if writing fails, and the actionable save error is displayed instead of silently discarding progress.
- Runtime/package release version is `4.2.8`; options remain schema `5` and run saves remain schema `5`.

### Tests

- Expanded exit-confirmation event and shared-dispatch coverage to verify save-before-title behavior, direct `M`, keyboard/gamepad cancellation, default Exit confirmation, three-row rendering, and the exact revised labels.
- Added real-file persistence coverage for current player state plus save-failure tests proving Exit and Return stay open and surface the error.

### Validation

- `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/bin/python -m unittest discover tests` — 377 tests, all passing; the experimental web build was not run separately.
- `.venv/bin/python -m compileall -q src tests` — OK.
- `git diff --check` — clean.

## 4.2.7 — Keyboard Cursor Confirmation

Milestone 4.2.7 makes the exit confirmation and quest dialogue screens fully navigable from the keyboard: arrow keys move the visible option cursor, while `Enter` or `E` confirms the highlighted row.

### Changed

- Exit confirmation now opens with `Exit game` selected, supports wrapped Up/Down/Left/Right navigation between Exit and Cancel, and lets `Enter` or `E` activate the highlighted row. Existing `Y`, `N`, `Esc`, and `Backspace` shortcuts remain available, and gamepad D-pad/A uses the same cursor path.
- Active quest cutscenes now route keyboard arrows through the existing dialogue cursor and use `Enter`/`E` as true selection confirmation once narration is complete. `Space` retains its narration reveal/advance behavior, and number keys remain quick-picks.
- The legacy/fallback guest-relic prompt now renders the same selected-choice highlight and supports keyboard arrows, `Enter`/`E`, D-pad, and gamepad A. This keeps restored saves and asset-failure fallbacks accessible.
- Dialogue cursors reset when changing nodes, clamp to visible choices, and ignore out-of-range number shortcuts instead of leaving every row unselected.
- Runtime/package release version is `4.2.7`; options remain schema `5` and run saves remain schema `5`.

### Tests

- Added real keyboard-event coverage for exit Cancel/Exit confirmation and both `Enter` and `E` quest-choice confirmation.
- Added shared-dispatch/gamepad coverage, fallback relic gamepad-A confirmation, rendered selection assertions for exit and relic screens, invalid number-key protection, and selected relic identity verification.

### Validation

- `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/bin/python -m unittest discover tests` — 375 tests, all passing; the experimental web build was not run separately.
- `.venv/bin/python -m compileall -q src tests` — OK.
- `git diff --check` — clean.

## 4.2.6 — Display-Aware UI Scaling

Milestone 4.2.6 makes the UI spacing follow the host desktop scale automatically. The supplied 4K Cinnamon/X11 references use `Xft.dpi: 192`, which now resolves to `Auto · 2x` before fonts and menu geometry are built.

### Added

- Added an `Auto` mode to the existing `1x–4x` UI scale setting. Pressing `0` on the Options screen restores automatic scaling; `+` and `-` still select manual larger or smaller scales, with Auto reachable again beyond either end of the manual range.
- Added dependency-free host scale detection for Windows per-monitor DPI, the backing scale of the macOS display containing the game window, and X11 `Xft.dpi`. `ARCH_ROGUE_DISPLAY_SCALE`, `GDK_SCALE`, and `QT_SCALE_FACTOR` provide safe fallbacks where SDL2 does not expose compositor scaling, including Wayland setups.
- Added display-change refresh handling so Auto mode can follow the window between monitors where the platform reports the change.

### Changed

- Options schema `5` now persists whether UI scale is automatic or manual. Schema-4 defaults and values already matching the detected host migrate to Auto; conflicting custom legacy scales remain manual overrides.
- Loading options after game construction now rebuilds fonts and invalidates scale-dependent UI/cutscene caches instead of leaving geometry and font sizes out of sync.
- Runtime/package release version is `4.2.6`; run saves remain schema `5`.

### Tests

- Added deterministic coverage for display-scale quantization, the reference `192 DPI → 2x` X11 path, Auto/manual cycling, delayed legacy migration, options round trips, font rebuilding, and monitor-change refresh events.
- Retained responsive title, options, character-selection, HUD, cutscene, scrollbar, and legacy-layout coverage across compact and large resolutions.

### Validation

- Live Cinnamon/X11 probe: `Xft.dpi: 192` detected as display scale `2.0` and UI scale `2x`.
- `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/bin/python -m unittest discover tests` — 369 tests, all passing; the experimental web build was not run separately.
- `.venv/bin/python -m compileall -q src tests` — OK.
- `git diff --check` — clean.

## 4.2.5 — Final Diamond Brand Selection

Milestone 4.2.5 finalizes the user-reviewed brand refinement: icon variant 4 becomes the application emblem, text-logo layout 1 becomes the modern title lockup, and every circular halo is removed. The packaged title now reads `ARCH <diamond> ROGUE` while retaining the exact approved gothic lettering from 4.2.4.

### Changed

- Replaced the circle-backed application emblem with the selected PixelLab ornate diamond: a standalone upright four-point relic with blackened-iron edges, engraved antique-gold facets, a small violet center, and a fully transparent background. The selected `128×128` master was re-exported to the stable `16`, `32`, `64`, `128`, `256`, and `512` icon paths, so window/taskbar loading and package APIs require no code or migration changes.
- Rebuilt `menus/title_logo.png` from selected layout 1 using the chosen ornate icon rather than the preview's placeholder. The final transparent `640×122` lockup keeps the existing letter pixels unchanged, places an `84×84` diamond between `ARCH` and `ROGUE` with 10px layout gaps, and has compact visible bounds `Rect(62, 24, 516, 74)`.
- Replaced the README's plain-text H1 with the finalized packaged `ARCH <diamond> ROGUE` lockup while retaining `Arch Rogue` as accessible fallback text.
- Runtime/package release version is `4.2.5`; options remain schema `4` and run saves remain schema `5`.

### Removed

- Removed the obsolete circular-halo icon from all packaged sizes and permanently deleted its PixelLab source object `4e964fd6-8299-4547-80c7-1deb4b28d80a`.
- Deleted the four rejected PixelLab preview siblings (`ce046a7f-adc5-40e5-9b27-8758e2a4b0dc`, `f02ef33e-d283-4c06-a360-7c917fe829cb`, `506993c5-402b-4f3d-a6aa-ea20381a8237`, and `e7415ed5-40d3-47e0-b0d8-d17e540fe41f`).
- Deleted the temporary local `icont_preview/` and `text_logos_preview/` directories plus their ignored comparison/title captures after packaging and visual review.

### Tests

- Updated title-logo geometry coverage for the compact centered lockup and asserted that its center diamond is opaque.
- Added explicit no-halo coverage at eight master-icon pixels formerly occupied by the circular ring while retaining all six size, transparency, readable-bounds, and center-opacity checks.
- Updated pinned runtime/save release assertions to `4.2.5`.

### Asset provenance

- Final icon: PixelLab object `0abafd0c-f0af-4bf1-b2be-ea21b7c21668`, seed `42044`, retained as the sole selected sibling in group `59f86320-2986-4a6f-a3ae-ce7a882071d2` and tagged `arch-rogue-brand-4.2.5`.
- Final lettering remains sourced from PixelLab UI asset `dfd0a3e1-2392-421d-a4c9-3c85b8ff784c`; the `ARCH` and `ROGUE` pixels were preserved exactly and only their placement around the selected center diamond changed.

### Validation

- `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/bin/python -m unittest tests.test_ui_assets tests.test_ui_layouts tests.test_save_and_metadata` — 29 tests, all passing.
- `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/bin/python -m unittest discover tests` — 362 tests, all passing; the experimental web build was not run separately.
- `.venv/bin/python -m compileall -q src tests` — OK.
- `git diff --check` — clean.
- Visually reviewed the final modern title at `960×540` and `640×480` before deleting the temporary captures.


## 4.2.4 — Relic & Brand Visual Upgrade

Milestone 4.2.4 completes the queued 4.2.x relic visual refinement: the owl-like quest artifact is replaced by a faceted diamond relic derived from the established brand geometry, the application icon becomes a modern PixelLab-authored diamond crest, and the modern title menu now uses an exact `ARCH ROGUE` generated wordmark. Legacy graphics retain their procedural title and relic paths.

### Added

- Added a PixelLab-authored `48×48` story-relic sprite with a transparent `34×40` four-point silhouette, four high-contrast neutral facets, blackened-iron edges, and no animal anatomy, pedestal, baked glow, or particles. The existing live floor glow, contact shadow, bob, tilt, motes, story-accent recolor, and interaction label remain runtime effects.
- Added a modern PixelLab application emblem: a bold upright faceted octahedron with an antique-gold halo and blackened-iron rim. The approved `128×128` master was exported to the existing `16`, `32`, `64`, `128`, `256`, and `512` icon contract, so window/taskbar loading and package paths remain unchanged.
- Added `menus/title_logo.png`, an alpha-cropped `640×122` horizontal lockup containing a faceted diamond crest and the correctly spelled uppercase `ARCH ROGUE` wordmark in antique-gold gothic pixel lettering. It is exposed as `menu.logo.title` through the validated `UiAssetLibrary` manifest.
- Added an optional `title_asset` path to `MenuBaseMixin.menu_frame`. The main title requests the generated lockup, fits it by aspect ratio within the existing responsive header envelope, records whether the asset was used, and falls back to the prior live text whenever the resource is missing or asset UI is disabled.

### Changed

- Modern story-relic tinting now scales the additive story color explicitly to 28%. `BLEND_RGB_ADD` ignores the supplied fill alpha, so the former call unintentionally added the full accent and washed pale facets toward one color. The authored diamond now keeps its facet depth while still inheriting each story palette.
- The procedural legacy relic retains its established full-accent blend byte-for-byte; only the authored modern sprite receives the restrained tint. The legacy title continues to render the original live `Arch Rogue` text and procedural menu frame.
- Runtime/package release version is `4.2.4`; options remain schema `4` and run saves remain schema `5`.

### Removed

- Removed the owl-like quest-relic PNG from the game and replaced it in place at the stable `items/story_relic.png` manifest path, so saves and gameplay identifiers require no migration.
- Deleted the obsolete PixelLab owl-relic object and its remaining review batch. Rejected diamond icon/relic candidates were also dismissed or deleted, leaving only the two approved maintainable object records plus the title-logo UI asset.

### Tests

- Added story-relic asset coverage for the native canvas/bounds, occupied top/left/right/bottom tips, widening-then-narrowing diamond rows, near-symmetric alpha mask, four distinct facet samples, and successful modern atlas resolution.
- Added brand coverage for all six packaged icon sizes, transparent corners, opaque centers, ≥80% readable silhouettes, the exact title-logo source geometry, manifest/package inclusion, modern render-cache use, and legacy title-asset bypass.
- Updated pinned release/save metadata assertions to `4.2.4`.

### Asset provenance

- Application icon: PixelLab review pack `a69a0e31-990c-473f-b446-cfb6b0fe2b5d` (`20` generations), approved frame `1`, promoted as object `4e964fd6-8299-4547-80c7-1deb4b28d80a` with tag `arch-rogue-brand-4.2.4`; unused candidates and the review parent were discarded.
- Story relic: PixelLab review pack `6b40ecad-0768-48b9-8c36-29f1da15fc2e` (`20` generations), approved frame `6`, promoted as object `dfbaf9c0-2e65-4551-aa36-505b4859f0b8` with tag `arch-rogue-relic-4.2.4`; the alternate finalist `eb400ed7-e18f-4a7c-a44a-28e5ecb675ca`, unused candidates, and the review parent were deleted.
- Title lockup: PixelLab UI asset `dfd0a3e1-2392-421d-a4c9-3c85b8ff784c` (`40` generations), generated at `688×192` and alpha-cropped without resampling to the packaged `640×122` source.
- Removed owl relic: PixelLab object `e647c50b-fdce-4430-96be-377f59324da2` and review batch `b43013f4-b83a-45bd-8dce-81160364993c` were permanently deleted. The Acolyte's separate spirit-owl familiar assets were intentionally retained.

### Validation

- `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/bin/python -m unittest tests.test_ui_assets tests.test_sprite_assets tests.test_ui_layouts tests.test_save_and_metadata` — 65 tests, all passing.
- `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/bin/python -m unittest discover tests` — 362 tests, all passing; the experimental web build was not run separately.
- `.venv/bin/python -m compileall -q src tests` — OK.
- `git diff --check` — clean.
- Visually reviewed the authored title at `960×540` and `640×480`, the unchanged legacy title at both sizes, the generated icon/relic contact sheet, and a deterministic close-up through the real relic atlas/tint/effect renderer. Captures remain ignored under `build/title_logo_*`, `build/relic_brand_review.png`, and `build/relic_renderer_closeup.png`.


## 4.2.3 — Cutscene Theater Production Overhaul

Milestone 4.2.3 delivers the complete cutscene-theater redesign as one release: authored gothic scenery and props, real animated performers, perspective-correct stage blocking, tactical duel choreography, a pillar-hiding witness, and scrollable narration. Modern graphics use the finished PixelLab production set while legacy graphics retain the procedural theater fallback.

### Added

- Added authored full-stage scenery for the omen and dialogue theaters, including the final pillar-free omen hall aligned to the renderer's floor horizon. The story-intro tableau uses the same production backdrop, with procedural gradients retained for legacy graphics and missing assets.
- Added a regenerated PixelLab full-screen cutscene background: an edge-to-edge gothic vaulted hall cropped from the reviewed scenic output at the native `688×384` source aspect. Opaque masonry and ceiling now fill every top corner, the floor reaches the lower edge, and all source/render alpha values remain `255`, eliminating the transparent upper band that exposed the previous frame.
- Added native-size PixelLab story-choice UI: a `640×44` gothic row plate repacked with a 12px wider badge socket while preserving its fixed iron divider and outer caps, plus distinct `32×32` aid, bargain, and defy badges sized for the actual option layout. All three badges were regenerated as sibling states of one aid master, standardized to the same centered `26×26` visible silhouette, and composited onto an identical blackened-iron/antique-gold frame and neutral inner disk; only the emerald, gold-coin, or crimson crossed-blade emblem changes. Small runtime-rendered 1–3 tabs preserve immediate keyboard/controller mapping without baking numbers into the semantic artwork.
- Added high-resolution stage prop sprites for pillars, altar, lectern, candelabras, and banners, plus the final compact frontal ritual altar. Six full-height standalone pillars form mirrored far, middle, and front depth tiers; candelabras sit on grounded marks clear of the combat route.
- Added the fixed-open crimson/violet proscenium curtain and five eight-frame south-facing `act` animation groups—Warden, Rogue, Arcanist, Acolyte, and Ranger—alongside the existing direction-aware idle, run, and attack clips.
- Added the reviewed Gate Warden animation set from PixelLab: the four-frame idle and six-frame walk groups cover all eight directions under the compatible runtime `idle`/`run` names, 18 corrected western walk frames replace the earlier versions, and a new eight-frame non-looping `attack` group delivers the weapon-slash/shield combination in every direction.
- Added five deterministic duel plans (`measured`, `player_press`, `antagonist_press`, `wide_feint`, and `close_exchange`) with varied initiative, clash lanes, obstacle clearance, feints, acting marks, and retreats. Every five-cycle block is a stable permutation derived from the story context, with no per-frame RNG jitter.
- Added alternating witness excursions: the friendly NPC emerges from behind the right-middle pillar, watches and reacts from an upstage mark, then returns behind the far architecture before settling back into cover.
- Added completed-narration review scrolling with an ember-gold scrollbar and wheel, PgUp/PgDn, and right-stick controls. Scroll state follows the spoken tail and resets across cutscene, floor, run, and save-restoration boundaries.

### Changed

- Grounded props and actors now share one back-to-front depth pass. Actor and prop anchors use true floor-contact coordinates, perspective scaling, and quantized cached shadows, preserving far/middle/front pillar occlusion and keeping the altar physically solid.
- Curtains remain deliberately fixed open throughout narration in both authored and procedural modes; all rejected opening-transition assets and logic stay removed.
- Duel travel uses stage-space directional facings and slowed clip timing. Curved home-to-home routes stay on the correct side of the altar, taper breathing at phase boundaries, and vary tactically without snapping. The clash hold remains about 1.3 seconds and sequences a hero strike into a Gate Warden counter using actor-local non-looping clip progress, two weapon-height impact sparks, and subtle recipient recoil; archetypes without authored attack groups intentionally retain the asset library's idle fallback until those groups are produced.
- All stage performers now move a little more deliberately: non-duel animation-track time scales from `0.45` to `0.40`, duel approach and retreat grow from `1.62` to `1.80` seconds, the witness schedule grows from `5.4` to `6.0` seconds, and moving walk clips scale from `0.667` to `0.60`. The attack exchange keeps its existing duration, while the player now pauses for about 2.0 seconds at the left home mark—long enough to show all eight frames of the existing south-facing `act` performance once—before the next tactical approach.
- The witness label appears only while clearly out of cover and is positioned toward center stage so architecture cannot split it. Return travel uses the correct directional sprite before the NPC disappears behind the pillars.
- Cutscene rendering now clears the screen before compositing the authored full-screen background, preventing malformed optional alpha from leaking the previous gameplay frame. It also scans narration once per frame, reuses computed choice heights, skips authored animation-track work for duel-overridden actors, uses an instance-owned bounded stage cache, and invalidates derived stage surfaces when graphics mode or UI scale changes.
- Quest-cutscene and story-intro selections now share one asset-first option renderer. Modern rows combine the authored plate with the matching semantic badge, center the icon from the plate's safe-content metadata, and inset response text an additional 4px horizontally and 2px vertically at `1×` (scaling with UI size) so labels/details breathe clear of the divider and frame. The complete label/gap/detail block is vertically centered inside that padded area; selection fill, border, and icon glow remain restrained. Legacy graphics—or any row missing either authored component—retain the complete original procedural panel, glyph, number, top-aligned text geometry, and highlight rather than mixing styles.
- The choice plate opts into height-scaled nine-slice borders so its socket grows with saved UI scales `1×–4×` instead of retaining a 1×-wide cap. At `2×`, the 77px protected cap and 80px safe-content inset become 154px and 160px while each `64×64` rendered badge retains a centered `52×52` visible medallion, keeping the icon and runtime number tab clear of the divider.
- Stage fallback dispatch no longer allocates a painter map per prop, `footlights=False` is honored, dead cutscene imports/constants/wrappers were removed, and reusable choreography math is allocated once at module load instead of once per frame.
- Legacy graphics continue to use procedural backdrops, props, actors, curtains, and proscenium while sharing the same deterministic choreography and depth rules. Runtime/package release version is `4.2.3`; options remain schema `4` and run saves remain schema `5`.

### Tests

- Added theater regressions for authored assets, the fully opaque full-bleed cutscene background at source, widescreen, and compact sizes, all five `act` groups, the reviewed Gate Warden idle/run/attack contract across every direction and frame, full-set fallback, fixed-open modern and legacy curtains, six-pillar depth ordering, grounded props, altar-safe paths, all tactical plans, the two-hit strike/counter timing and recoil, actor-local attack progress, the left-home `act` pause and local clip restart, witness emergence/return, narration scrolling, and release metadata.
- Added cleanup/performance regressions proving one narration reveal scan per render, one choice-height calculation per choice, no redundant duel actor-track evaluation, bounded isolated stage caches, graphics/UI cache invalidation, `footlights=False`, and byte-identical cold versus modern-warmed legacy stage renders.
- Added story-choice regressions covering the native `640×44` plate, widened 80px safe-content inset, exact doubled-cap pixels and 160px inset at `2×`, three distinct `32×32` semantic badges with identical `26×26` alpha masks/outer frames and `52×52` doubled bounds, authored text padding and vertical centering at `1×`/`2×`, unchanged top-aligned legacy text geometry, scalable manifest output, modern asset use, and byte-compatible legacy/procedural fallback behavior.

### Validation

- `.venv/bin/python -m compileall -q src tests` — OK.
- `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/bin/python -m unittest tests.test_ui_assets tests.test_cutscene_assets tests.test_cutscene_runtime` — 39 tests, all passing.
- `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/bin/python -m unittest tests.test_cutscene_runtime tests.test_cutscene_assets tests.test_ui_assets tests.test_sprite_assets tests.test_input_and_accessibility tests.test_save_and_metadata` — 97 tests, all passing.
- `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/bin/python -m unittest discover tests` — 354 tests, all passing.
- `git diff --check` — clean.
- Headless `960×600` profiling over 50,000 duel evaluations and 120 warm frames measured approximately 6.9 µs per duel-state evaluation, 7.0 ms per modern frame, 5.9 ms per legacy frame, and 6 warm stage-cache entries.
- Visually reviewed final modern and procedural-legacy overlays through the actual renderer; theater cleanup captures remain ignored at `build/theater_4_2_3_cleanup_{modern,legacy}.png`, strike/transition/counter plus left-home `act` captures are under `build/gate_warden_clash_review/`, and the opaque background/cutscene renders are under `build/cutscene_background_review/`. Final unified-badge reviews are under `build/story_choice_asset_review/`: `choices_modern_{960x540,640x480}_1x_v3.png`, full-scene `choices_modern_1920x1080_2x_v3.png`, native row crop `choices_modern_2x_rows_v3.png`, and enlarged `story_choice_v3_final_8x.png`; final vertically centered text captures are `choices_modern_960x540_1x_v5_centered.png`, `choices_modern_1920x1080_2x_v5_centered.png`, and `choices_modern_2x_rows_v5_centered.png`. Earlier story-intro and procedural-legacy checks remain in the `_v2` captures.


## 4.2.2 — Quest Info Scrolling

Milestone 4.2.2 makes the quest info panel's story text scrollable: overflowing quest text now scrolls with the mouse wheel or PgUp/PgDn behind a thin ember-gold scrollbar instead of truncating with an ellipsis.

### Added

- Added `Game.story_panel_scroll` (wrapped-line offset) with `scroll_story_panel(delta)` clamping against the renderer-published `_story_panel_scroll_max`. The offset starts at the top, resets when Q toggles the quest panel, and clears in `reset_transient_visuals` so floor transitions, cutscenes, run restarts, and save restores all return the panel to the top of the text.
- Plain mouse wheel (no Ctrl) scrolls the quest info panel's story text by two lines per notch while playing with the panel visible; `Ctrl+scroll` still zooms the viewport, and the wheel is ignored while the inventory, character sheet, shop, cutscenes, or the story intro are up. `PgUp`/`PgDn` page the text by one panel of lines; the inventory and shop key branches keep priority for those keys while their overlays are open.
- `RenderingStoryOverlayMixin.draw_story_panel` now wraps the full story body, renders the scrolled slice under the pinned title, and draws `draw_story_panel_scrollbar` — a thin recessed track with an ember-gold thumb on the panel's right rail, mirroring the inventory/options scrollbars so the three read as one family. When the text overflows, the body wraps slightly narrower so no line runs under the scrollbar; when it fits, the layout is unchanged and no scrollbar is drawn.
- The Run Guide's story-guest line now documents the scroll controls ("scroll wheel or PgUp/PgDn scrolls its story text when it overflows").

### Changed

- Overflowing quest text no longer truncates with a `…` marker — the scrollbar communicates the overflow and position instead, and the full story text is reachable.
- Runtime/package release version is `4.2.2`; options remain schema `4` and run saves remain schema `5`.

### Tests

- Added `UiLayoutTests.test_quest_info_panel_scrolls_overflowing_story_text` covering: overflow publishes a positive scroll range with a scrollbar inside the panel, scrolling re-renders a different slice, the offset clamps in both directions and resets on Q toggle, and short text keeps the no-scroll layout with no scrollbar and a snapped-back offset.
- Added `QuestInfoScrollInputTests` covering: plain wheel scrolling down/up with clamping, Ctrl+wheel zooming instead of scrolling, the wheel doing nothing while the panel is hidden, PgUp/PgDn paging by one panel of lines, and the inventory overlay keeping PgDn for its own cursor.
- Updated the pinned release assertions in `SaveAndMetadataTests` to `4.2.2`.

### Validation

- `.venv/bin/python -m unittest tests.test_ui_layouts tests.test_input_and_accessibility tests.test_save_and_metadata tests.test_story_mode` — all passing.
- `.venv/bin/python -m unittest discover tests` — all passing.
- `.venv/bin/python -m compileall -q src tests` — OK.

## 4.2.1 — Visual Refinement

Milestone 4.2.1 delivers the 4.2.x visual refinement pass: the lower HUD slab was regenerated in Pixellab with really thin left/right side decorations so panel interiors fit more content, and HUD texts (mission objective, quest info panel, tooltips, run header, shop) received a little more breathing room from their frames.

### Added

- Added a freshly generated `hud/panel.png` (Pixellab asset "Arch Rogue HUD slab thin A", cropped to its 668×108 band): a matte blackened-iron slab with an opaque near-black fill, a hairline ember-gold trim along the top edge, barely rounded corners, and extremely thin flat left/right edges with no side ornaments. Because every ornate HUD container shares the `hud.panel` nine-slice (bottom slab, resource/character/mission cards, interaction prompt, run header, quest info panel, shop panel), all of them pick up the thinner frame at once.
- Added `UiLayoutTests.test_hud_slab_has_thin_side_borders_and_padded_mission_text` guarding the thin manifest insets (left/right nine-slice caps and content insets ≤ 16px) and asserting the rendered mission objective sits below and left of the raw card content rect.

### Changed

- `hud.panel` manifest geometry follows the new art: nine-slice insets `[70, 10, 70, 10]` → `[10, 10, 10, 8]` and safe-content insets `[28, 8, 28, 8]` → `[14, 8, 14, 8]`. The bottom slab's decorated side caps shrink from 70px to 10px per side, so the three HUD cards and their interiors widen — at the reference 960×540 layout the resource bar troughs grow from 260px to 284px wide with unchanged height.
- HUD texts keep a little more air between themselves and the slab frame (asset path only; legacy geometry untouched): the three bottom cards inset their content by `ui(5)`/`ui(1)` instead of `ui(3)`/0, the mission texts (objective, detail, control hints) additionally sit `ui(5)` lower and end `ui(10)` short of the card's right edge so "Find the stairs to descend deeper" no longer kisses the frame corner, the quest info panel and run header inset their content by `ui(5)`/`ui(2–3)` instead of `ui(3)`/`ui(1)`, the interaction prompt and run header grow `ui(4)` taller to preserve their line room, and the shop panel safe area insets by `ui(6)`/`ui(4)` instead of `ui(4)`/`ui(3)`.
- Runtime/package release version is `4.2.1`, and the stale `arch_rogue.__version__` (left at `4.1.25` through the 4.1.26/4.2.0 bumps while `pyproject.toml` moved on) is resynced, so the window caption, title/options menus, and the save file's informational `release` field report the real release again. The `release` field is write-only metadata, so existing saves restore unchanged; options remain schema `4` and run saves remain schema `5`.

### Tests

- Updated `UiLayoutTests.test_obsidian_resource_bars_expand_only_the_modern_hud` to the new 284×14 bar troughs produced by the thin-border slab.
- Updated the pinned release assertions in `SaveAndMetadataTests` from `4.1.25` to `4.2.1`.

### Validation

- `.venv/bin/python -m unittest tests.test_ui_layouts tests.test_ui_assets tests.test_sprite_assets tests.test_inventory_hud_and_hints tests.test_hud_action_bar tests.test_save_and_metadata` — all passing.
- `.venv/bin/python -m unittest discover tests` — all passing.
- `.venv/bin/python -m compileall -q src tests` — OK.

## 4.2.0 — General Refinements

Milestone 4.2.0 delivers the small quality-of-life improvements queued under the 4.2 General Refinements milestone: verified familiar/enemy wall line-of-sight, garden-room passive healing with a visible greenish aura, a scrollbar for the settings menu when options overflow, slightly rarer loot drops across the board, and harder-to-kill elite enemies.

### Added

- Added `Dungeon.special_room_at_point(x, y)` returning the `SpecialRoom` whose interior contains a world point, used by the new garden healing logic to detect "player is standing inside a garden flavor room" without duplicating the room-bounds query.
- Added garden-room passive healing: while the player stands inside an overgrown garden flavor room with missing HP, `CombatMixin._update_garden_healing` banks time and grants one small +HP tick per second (`max(2, max_hp // 25 + 2)`), emits a `Garden +N` floater in a soft green, and refreshes a transient `garden_heal_glow` timer. The heal only ticks while HP is actually missing and stops as soon as the player steps out of the garden or reaches full HP.
- Added a greenish garden healing aura renderer: `RenderingActorMixin.draw_garden_heal_glow` draws a pulsing halo + rising leaf-wisp sparks around the player whenever `garden_heal_glow` is active, faded by the timer's remaining life so the garden reads as a calm refuge rather than a flash. The aura is drawn after the hit flash so a recent hit does not mask the green tint, and lazily skipped when no glow timer is active.
- Added `garden_heal_accumulator`, `garden_heal_glow`, and `garden_heal_glow_duration` to `Game` state, reset in `reset_transient_visuals` (so floor descent, run restart, and save restore all clear them) and decayed in `Game.update_visual_effects`.
- Added a scrollbar to the Options menu: `MenuOptionsMixin.draw_options_scrollbar` draws a thin ember-gold thumb on a recessed track on the right rail of the options row viewport whenever the full options list does not fit vertically. When the scrollbar is needed, the rendered rows are inset from the viewport's right edge so the thumb never overlaps a row's right-aligned value; when everything fits, no scrollbar is drawn and rows keep the full width. The look mirrors the inventory scrollbar so the two menus read as one family.

### Changed

- Elite modifiers are harder to kill across the board. The `ELITE_MODIFIERS` HP multipliers and damage bonuses were raised so each elite tier reads as a real threat instead of a slightly tougher normal enemy: Frenzied HP 1.25 → 1.45 / damage +2 → +3, Ironbound HP 1.65 → 1.95 / damage +1 → +2, Venomous HP 1.20 → 1.40 / damage +4 → +5, Runed HP 1.35 → 1.55 / damage +3 → +4. Speed multipliers and xp rewards are preserved so kiting strategy and reward pacing stay the same.
- Loot drops are rarer across the board (but not by too much). The on-kill loot roll in `CombatMixin.kill_enemy` is reduced from `0.45` to `0.36`, and the per-floor loot spawn multiplier in `PopulationMixin._populate_dungeon` is reduced from `0.5` to `0.42` (on top of the existing base chance). Guaranteed event drops (secrets, shrines, boss/miniboss notable loot) are unchanged so rare encounters still feel rewarding.
- Runtime/package release version is `4.2.0`; options remain schema `4` and run saves remain schema `5`.

### Verified

- Verified that the Acolyte's Spirit Call familiar cannot perceive or attack enemies through dungeon walls. The familiar target-selection loop in `CombatMixin.update_familiars` already gates every candidate on `Dungeon.line_of_sight`, so both the Acolyte's owl and the Ranger's Spirit Beast share the same wall-blocked perception contract. Added an explicit Acolyte regression test (`test_acolyte_spirit_familiar_cannot_perceive_or_attack_through_walls`) alongside the existing Ranger Spirit Beast wall tests.

### Tests

- Added `FlavorRoomTests.test_garden_room_slowly_heals_player_and_emits_greenish_glow` covering: sub-second accumulator banking without a tick, the one-second tick healing the player and activating the glow with a green `Garden +N` floater, healing stopping when the player steps out of the garden, and no-Op behavior at full HP.
- Added `FlavorRoomTests.test_garden_heal_glow_renders_without_crashing` exercising a full `game.draw()` frame with `garden_heal_glow` active and confirming `update_visual_effects` decays the timer.
- Added `UiLayoutTests.test_options_scrollbar_appears_when_rows_overflow_and_is_absent_when_they_fit` covering: the scrollbar is drawn (and rows inset) when the options list overflows at high UI scale, the scrollbar is absent and rows keep full width when the list fits at a large window, and the viewport/selected-row geometry stays sane in both modes.
- Added `FamiliarTests.test_acolyte_spirit_familiar_cannot_perceive_or_attack_through_walls` verifying the Acolyte's owl cannot bite through walls and regains perception once the wall is cleared.
- Added `CombatSkillsLoot22Tests.test_elite_modifiers_are_harder_to_kill_than_baseline` verifying the new HP multiplier / damage bonus floors for all four elite tiers and that applying each modifier produces a higher-HP, higher-damage foe than the baseline.
- Added `CombatSkillsLoot22Tests.test_loot_drops_are_rarer_than_the_four_one_baseline` verifying the on-kill loot threshold sits below `0.36` (a 0.35 roll drops, a 0.40 roll does not).

### Validation

- `.venv/bin/python -m unittest tests.test_flavor_rooms tests.test_familiars tests.test_enemy_los_walls tests.test_ui_layouts tests.test_combat_damage_and_loot_tables tests.test_floor_plan_and_boss_rewards tests.test_input_and_accessibility tests.test_sprite_assets` — all passing.
- `.venv/bin/python -m unittest discover tests` — 320 tests, all passing; the experimental web build was not run separately.
- `.venv/bin/python -m compileall -q src tests` — OK.

## 4.1.26 — In-Game Legacy Graphics Hotkey

Milestone 4.1.26 delivers the backlog item for an in-game legacy graphics toggle, exposing the existing `legacy_graphics` option through a global hotkey so players can switch between authored asset sprites and the procedural legacy renderer without entering the Options menu.

### Added

- Added a global `Ctrl+Alt+L` hotkey that toggles `legacy_graphics` from any game state (playing, title, options, menus). It is intercepted before the state-specific `KEYDOWN` branches so it does not collide with the title's `K_l` load-run shortcut or the options menu's `K_l` lighting-row shortcut.
- In the playing state, the toggle emits a short feedback floater (`"Legacy graphics"` / `"Asset sprites"`) above the player using the active theme accent.
- Added the `Ctrl+Alt+L graphics` hint to the bottom-right mission panel control line in the playing HUD, prepended so it stays on the first (visible) wrap line at the standard `960×540` logical resolution where only one control line renders. The full control line (including all existing hotkeys) is visible at wider layouts.
- Documented the hotkey in the in-game Run Guide overlay alongside the existing `Ctrl+Shift+D` darkness and `Ctrl + scroll` zoom hints.

### Changed

- The hotkey reuses the existing `OptionsMixin.set_legacy_graphics` entry point, so the toggle still persists to `options.json` (schema `4`), refreshes sprite/UI/tile/aim/lighting caches, and prewarms the tile cache exactly like the Options menu row.
- Runtime/package release version is `4.1.26`; options remain schema `4` and run saves remain schema `5`.

### Tests

- Added `LegacyGraphicsHotkeyTests` covering: in-playing-state toggle both ways with floater feedback, options-file persistence and reload by a fresh `Game`, title-state interception without triggering load-run, plain-`L` in options still adjusting the lighting row, the hotkey not firing on lone `Ctrl` or lone `Alt`, and the `Ctrl+Alt+L` hint appearing in the rendered HUD control line.

### Validation

- `.venv/bin/python -m unittest tests.test_input_and_accessibility tests.test_dark_levels tests.test_ui_assets tests.test_ui_layouts tests.test_world_rendering_and_animation tests.test_hud_action_bar` — 56 tests, all passing.
- `.venv/bin/python -m unittest discover tests` — 314 tests, all passing; the experimental web build was not run separately.
- `.venv/bin/python -m compileall -q src tests` — OK.

## 4.1.25 — Finalization Additions

Milestone 4.1.25 completes the 4.1.x Finalizing version additions: an angry wolf icon for the Ranger's Spirit Beast skill, dynamic icon switching based on command mode, and exponential petting bonus scaling with Beast Discipline investment.

### Added

- Added a `32×32` PixelLab-authored angry wolf HUD icon (`hud.action.ranger.spirit_beast_angry`) depicting a snarling wolf head with bared fangs, flattened ears, and glowing red eyes in the established grim dark-fantasy action-RPG style.
- Added dynamic Spirit Beast skill-icon switching in the modern HUD: the angry wolf icon is shown when the beast is in attacking mode (next command: RETURN), and the calm wolf icon is shown when the beast is in return/follow mode (next command: ATTACK) or before summoning. Legacy procedural glyphs are unchanged.
- Added `spirit_beast_pet_heal()`: the petting bonus now starts at `+2` and doubles for each Beast Discipline degree chosen — `+4` at Beast Bond, `+8` at Pack Tactics, `+16` at Alpha, `+32` at Spirit Companion, and `+64` at Primal Lord. Non-Beast disciplines do not inflate the bonus. The floater text reflects the actual heal amount.

### Changed

- Removed all status text overlays from action skill icons ("ATTACK", "RETURN", "EMPTY", "FULL", "MP", "ST", cooldown timer text). The cooldown arc, darkening overlay, count badge, angry/calm Spirit Beast icon swap, and readiness lamp already convey state visually, making the text labels redundant clutter.
- The HUD action slot for the Ranger's class skill now selects between two authored asset keys (`hud.action.ranger.spirit_beast` and `hud.action.ranger.spirit_beast_angry`) based on the beast's current `command_mode`, preserving the existing `cooldown_command` status label and cache behavior.
- Runtime/package release version is `4.1.25`; options remain schema `4` and run saves remain schema `5`.

### Asset provenance

- PixelLab generation/review pack: `8d5bf4cd-7ad4-4f51-8245-560d7dae5715` (`20` generations), 64 candidate frames at `32×32`. Approved candidate: frame `0`, promoted as object `86014eba-63b4-4b80-a8aa-893510bb11db` with the `arch-rogue-action-icon-4.1.25` tag. Unused candidates were discarded.

### Validation

- `.venv/bin/python -m unittest tests.test_familiars tests.test_hud_action_bar tests.test_ui_assets` — 43 tests, all passing.
- `.venv/bin/python -m unittest discover tests` — 308 tests, all passing; the experimental web build was not run separately.
- `.venv/bin/python -m compileall -q src tests tools` — OK.
- `git diff --check` — OK.

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
