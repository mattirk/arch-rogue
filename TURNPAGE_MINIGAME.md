# Turn the Page — Minigame Plan

Status: implemented in `6.0.0-alpha.27`. Human visual signoff, physical-device validation, and timed human playtesting remain acceptance follow-ups.

## Goal

Replace the modal **Bind the Page** sequence at depths **5, 8, and 9** with a world-space spatial-memory challenge. Preserve the relic-choice continuation and current win/loss rewards while making the event use movement, dash, isometric space, and readable action feedback.

## Core loop

1. Freeze the real dungeon and save the exact player position, facing, action/cooldown state, and return context, following the Mistbound Chamber contract.
2. Move the player to a wall-less manuscript platform suspended over a void.
3. **Reveal:** a connected safe route glows from the starting tile to a page seal. Movement is locked, but live aim may turn the player.
4. **Traverse:** the route fades. The player must cross the remembered tiles in order; movement and dash are enabled.
5. Correct tiles relight and stitch together with a persistent cyan ink trail.
6. Entering an intact wrong tile changes it to cracked, plays its fall-to-void animation, drops/veils the player, records a mistake, and returns the player to that page's start after a short lockout. Fallen cells remain empty and block subsequent movement.
7. Reaching the seal turns the page and generates the next deterministic route. Complete every page before time expires to win.
8. Restore the exact frozen dungeon state and continue the chosen relic path on either result.

Dash collision must validate every crossed cell so a dash cannot skip an incorrect tile. Empty cells and the platform boundary block movement without another mistake. Later profiles include marked one-cell route gaps: walking stops at their edge, while a dash can cross them to a supported landing. Other fallen cells also block dashes.

## Initial profiles

| Depth | Pages | Route length | Reveal | Added pressure |
|---|---:|---:|---:|---|
| 5 | 2 | 5 tiles | 1.5 s | No gaps; introductory route |
| 8 | 3 | 6–7 tiles | 1.25 s | One dash gap on later pages |
| 9 | 3 | 8 tiles | 1.0 s | Up to two dash gaps and faster reset |

Starting time budgets should be tuned from captures rather than treated as final. Route generation must always prove connectivity, valid start/seal clearance, and compatibility with the player's swept foot-contact radius.

## Result contract

- **Win:** retain current Bind the Page reward: restore HP to maximum and grant +1 melee power, then commit the selected relic path.
- **Loss:** commit the selected relic path without the minigame reward; no direct HP, equipment, currency, or permanent-stat punishment.
- One recorded result per scheduled depth; no duplicate rewards.

Reward balance is intentionally out of scope for the replacement and can be reviewed separately.

## World and presentation

- Use a dedicated alternate world state, not a modal board.
- Camera, interpolation, pause, cursor/right-stick facing, mobile Menu access, and exact return behavior should follow the proven Mistbound Chamber seams.
- Arena: a compact floating manuscript lattice with transparent void outside it and no ordinary dungeon actors, LOS, fog, or combat simulation.
- Tile states: `Hidden`, `Revealed_Safe`, `Confirmed`, `Wrong`, `Cracking`, `Falling`, and `Gone`.
- Falling is presentation-driven after the authoritative wrong-step decision; gameplay must not depend on animation frame timing.
- Use shape, glow, stitch direction, and optional step markers together—never color alone—to communicate the route.

## PixelLab assets and animation

The HD presentation uses 512×512 PixelLab artwork. The floor is a surface
inpaint of `assets/world/lossless_soul_floor.png`, the Mist chamber's slab:

- `assets/world/turn_page/floor.png`: one full-cell limestone flagstone with
  fine wear and engraved manuscript details, matching the Mist chamber's
  outline and thick stone sides.
- `floor_ink_spill.png` and `floor_ink_smear.png`: localized ink accidents on
  the same stone, preserving its outer geometry.
- `floor_glyph_serpent.png`, `floor_glyph_key.png` and `floor_glyph_moon.png`:
  rough ink sketches referencing the Pygame multiplayer verification seal
  vocabulary in `arch-rogue-python/src/arch_rogue/menus/mp.py` and the matching
  `arch-rogue-python/src/arch_rogue/assets/sprites/menus/glyphs/sigil_*.png`
  artwork. These are historical art references only; multiplayer remains deferred.
- `assets/world/turn_page/ink.png`: a separate transparent luminous manuscript
  decal for the revealed and confirmed route.

Each board has three tiles of each stain/glyph variant and 85 plain tiles.
A private visual RNG derived from the minigame seed, depth and page selects
distinct cells without replacement, independently of route membership and tile
state. Fallen tiles never cause decorations to redistribute. Reveals, confirmed tiles, falling fragments, retries, final results and
save/resume retain the selected texture. New pages vary the layout without
consuming gameplay RNG or adding save fields. All runtime artwork lives under
root `assets/world/turn_page/`.

`assets/world/turn_page/manifest.json` pins the native PNG dimensions, source
jobs, full prompts, anchors, reference widths and SHA-256 digests. The source
PNGs retain their generated pixels and alpha. The floor matches the Mist
chamber's 512×256 top face, 80-pixel stone sides, [256,320] anchor and 512-pixel
reference width. Both render with the same uniform scale as a 64×32 face with
10-world-pixel sides; no manuscript-only floor stretching is needed. Intact,
illuminated and falling tiles share the standard world-sprite placement. Ink,
stitches and route markers follow the matching surface elevation, two world
pixels above the anchor. The planar ink decal is projected vertically by 0.5
to match the 2:1 plane. Trilinear mipmaps use the same loader as the Soul room.

The collapse partitions the floor texture into eight irregular pieces with
matching UVs. Fine cracks open before the pieces accelerate downward, rotate,
shrink and fade at interpolated simulation time. Foreground floor tiles occlude
the falling player and fragments in isometric painter order. An incomplete dash
into an existing gap drops the player without creating a new slab. Rendering never
changes gameplay state, and the fall still completes after 0.9 seconds.

The camera follows within the platform bounds, keeping the whole board visible
when it fits. Route marks use fine projected ink, directional stitches and
small numerals; their reveal and illumination ease smoothly. Player walking
uses the same distance-scaled animation cadence as ordinary dungeon movement.

Run `python3 tools/verify_turn_page_assets.py` to verify the source and runtime
contracts. The initial 64×64 tiles and nine-frame animation are superseded.

## Void-motion rollout and human review

Implement and review these phases separately. Do not begin a later phase until
human feedback on the preceding phase has been addressed.

1. **Platform motion — approved by the human on 2026-09-06.** A shared camera
   transform rolls the entire slab and inlaid route by +/-8 degrees over a
   60-second cycle, with a 3-world-pixel vertical drift over 12 seconds. The
   player and route numerals remain upright; shadows stay on the floor and
   falling actors/fragments descend toward screen-bottom. Keyboard, controller
   and touch movement/aim account for the posed camera. The HUD stays fixed.
   Motion derives from the saved borrowed player clock, so pages and retries
   retain its phase, pause freezes it, and resume restores it without new save
   fields. Review pace, motion comfort, route readability and movement feel
   before adding anything in the void.
2. **Parchment depth — approved by the human on 2026-09-06.** Four small scraps
   share three generated transparent sprites in `assets/world/turn_page/void/`.
   Seeded orbits take 110–125 seconds with slight individual drift, separated
   initial phases and gentle tumbling. Their widths range from 14–24 world
   pixels at 12–22% opacity, tinted into the dark background, fading in over
   the first two seconds. A separate unrolled camera follows at 30% of the
   island camera's travel, giving parallax at close zoom. Draw them below the
   floor so intact slabs occlude them; they never cover the route or player.
   The saved clock freezes them with the island on pause and reconstructs the
   same positions on resume, without gameplay RNG or save-field changes.
   Review visibility and density before adding any distant manuscript traces.
3. **Distant manuscript traces — implemented, awaiting final human review.**
   One incomplete serpent/key/moon scrawl fades in and out over 18 seconds,
   followed by 10 seconds with no glyph. Subsequent scrawls alternate flanks
   and motifs using the minigame seed; no two glyphs crossfade or overlap.
   Width is 130–180 world pixels, peak opacity 5.5%, with less than one world
   pixel of drift per second. Two broken ink wisps follow opposing slow
   195–230-second orbits, at 2.5–4.5% opacity and 65–110 world pixels wide.
   These traces use a separate camera at 12% follow travel, behind the approved
   parchment layer and the island, with the same saved clock and pause rules.
   Native transparent art lives in `assets/world/turn_page/traces/`, with
   source prompts, job IDs and hashes in its manifest. No haze or filled
   backdrop is added. Review the combined desktop/mobile/web scene before
   accepting the final treatment.

`./tools/capture_turn_page_motion.sh` creates an original-speed 60-second,
30 fps video at `build/turn-page-captures/motion/turn-page-motion-60s.mp4`, plus
native desktop/mobile stills at both roll extremes and a tilted fall. Its
review fixture holds the reveal in place while advancing the presentation
clock; ordinary play retains its normal timer and route rules. Pass `--stills`
for the smaller pose review. The capture asserts pause stability, camera/input
agreement, scene restoration and read-only rendering.

For phase two, use `./tools/capture_turn_page_motion.sh --output-dir build/turn-page-captures/parchment` to preserve the approved phase-one video.
The output directory contains the combined 60-second video and desktop/mobile
stills, including the midpoint and tilted falls. The ordinary native/browser
story capture fixtures now sample 9 seconds of ambience so their stills include
settled parchment, a glyph at peak opacity, and a visible island roll.

Phase-one validation (2026-09-06): 494 Odin tests, vetted check, Linux release,
web build/audit, and the three-ABI Android debug build/APK audit pass. Native
desktop/mobile-layout motion captures and Chromium reveal/traverse/fall captures
pass; human motion review was approved on 2026-09-06. Physical-device validation
remains open.

Phase-two validation (2026-09-06): all three native 256×256 PixelLab PNGs,
transparency, dimensions and SHA-256 contracts verified; their source prompts
and job IDs are in `assets/world/turn_page/void/manifest.json`. The PNGs total
25,733 bytes. Vetted check, 496 Odin tests, Linux release, web build/audit and
three-ABI Android debug build/APK audit pass. Initial web transfer is 27.71 MB
against the unchanged 29.36 MB budget. The 60-second combined motion video,
desktop/mobile-layout stills, and Chromium reveal/traverse/fall captures pass.
Human phase-two visibility/density review was approved on 2026-09-06.

For phase three, use `./tools/capture_turn_page_motion.sh --output-dir build/turn-page-captures/traces`. Its 60-second video and desktop/mobile stills
include glyph peaks at 9, 37 and 65 seconds (the last as a still), and a blank
interval at 23 seconds. The capture also compares paused frame pixels and
requires every trace texture to load. Earlier review output directories remain
intact.

Phase-three validation (2026-09-06): four native 256×256 PixelLab PNGs total
10,327 bytes; transparency, dimensions, source prompts and SHA-256 contracts
verified. Vetted check, 499 Odin tests, Linux release, web build/audit and
three-ABI Android debug build/APK audit pass. Initial web transfer is 27.72 MB
against the unchanged 29.36 MB budget. The 60-second combined motion video,
20 desktop/mobile-layout stills, and Chromium reveal/traverse/fall captures
pass. Paused frames are pixel-identical across render interpolation values;
rendering preserves authoritative state. Final human visual review and
physical-device validation remain open.

## Persistence and migration

- Reuse the existing scheduled `Bind_The_Page` result ledger and relic continuation semantics.
- Replace its active-state payload with deterministic world-space route/page/tile state plus exact return data.
- Legacy modal Bind saves should recover safely to the relic choice or restart the current page; never interpret old board cells as world coordinates.
- Save/resume must preserve route, confirmed step, mistakes, timer, tile-fall phase, and frozen dungeon state without advancing either world while suspended.

## Validation gates

- Deterministic routes and replay across save/resume.
- All generated routes solvable; dash gaps reachable; no route intersects invalid borders.
- Preview permits looking but never movement or dash.
- Swept movement/dash cannot skip validation cells.
- Wrong-step fall resolves exactly once and returns safely.
- Fallen tiles block repeated movement, including corner contacts and save/resume; authored gaps remain dashable.
- Pause, controller, mouse, touch, and mobile Menu behavior.
- Exact dungeon position, facing, cooldown, RNG, enemies, exploration, and clocks restored after win/loss.
- One reward/result per depth and intact relic continuation.
- Visual captures at desktop, 16:9/16:10 mobile, and web before final tuning.

## Implementation record

- `src/turn_page.odin` owns a bounded 10×10 lattice and deterministic cardinal
  routes of 5, 6–7, or 8 cells, including start, seal and any gap cells. Monotone
  paths are reflected across either axis; they cannot self-intersect. Gap edges
  remain straight with a full supported takeoff and landing cell.
- Depth 8 introduces one gap after the first page; depth 9 introduces two.
  Movement uses the normal 2.8 cells/s baseline and a 0.12-cell foot-contact
  radius for falling. This permits 0.38 cells of sideways drift from a tile
  center; the combat-sized radius previously permitted only 0.08. Dash covers
  up to 2.4 cells with a 0.35 s cooldown and brakes at the next ordered safe
  landing's center plane, preserving lateral placement. Every intervening
  foot-contact capsule is still checked against the lattice. Intact wrong tiles
  cause a fall; empty cells stop walking without another mistake. Only marked,
  ordered route gaps permit a dash, and an interrupted jump must still resolve
  an unsupported landing. Blocking reads the persisted tile state directly.
- Starting traversal budgets are 26 / 40 / 42 seconds at depths 5 / 8 / 9.
  Reveals do not consume the traversal budget; falls do. Reset delays are
  1.25 / 1.15 / 0.95 seconds. The continuous fall completes at 0.9 seconds.
  These remain starting values pending timed human playtesting.
- The dungeon stays resident and receives no simulation ticks, LOS updates,
  exploration changes or combat. The alternate world borrows only a typed set
  of player presentation fields and dash cooldown; all are restored before
  applying the existing reward and relic continuation.
- Run schema 3 stores `Turn_Page_State` separately from the retained
  `Story_Minigame_State` ledger/continuation shape. Keeping that legacy shape
  unchanged preserves checksum verification for schema 1 and 2. Old modal
  saves restart page one using the saved real player and chosen continuation.
- Tests cover 2,400 generated routes, swept movement and dash reachability,
  preview aiming, pause/Menu, single-trigger falls, exact frozen-world state,
  rewards/continuation, malformed payloads, and save/resume in all phases.

## Reproducible validation

```bash
python3 tools/verify_turn_page_assets.py
./build.sh check
./build.sh test
./build.sh release
./tools/capture_turn_page.sh --animation
./build.sh web-build
node tools/capture_turn_page_web.mjs
./build.sh android-debug
```

Captures are written under `build/turn-page-captures/`: reveal, confirmed
traversal and falling at desktop 1280×720, simulated mobile layouts at
1280×720 and 1280×800, and Chromium 1280×720. Mobile layout captures run the
actual mobile HUD/layout code in the desktop renderer; they are not Android
runtime or physical-device evidence. The web capture waits for the real idle
and walk clips before freezing the scene. These harnesses use isolated,
ephemeral capture profiles.

With `--animation`, the native capture also writes
`build/turn-page-captures/animation/collapse.mp4`: a 60 fps recording of the real
renderer through reveal, cracking, descent and retry. Its harness renders two
frames per simulation tick and checks that rendering preserves the player and
tile state. It requires FFmpeg in addition to the normal build toolchain.
The same command writes `build/turn-page-captures/edge-closeup.png`, a direct
3× render of the exposed slab edges for alignment review, and
`build/turn-page-captures/tile-comparison.png`, which renders the Mist chamber
and manuscript slabs at identical zoom and lighting, individually and tiled.
`build/turn-page-captures/floor-variants.png` shows all six slabs through the
actual floor renderer at the same zoom.

Human visual acceptance remains open. An Android device was not attached during
implementation; native compilation and APK audits cover all three packaged ABIs.

Validation on 2026-09-05: 481 Odin tests, check, optimized Linux build, 17
public-mirror/repository regressions, native asset verification, Android debug
three-ABI compile/APK audit, and web build/download/heap audit passed. Chromium
captures and the 20-scenario browser smoke suite passed, including schema-3
save/reload and backup recovery. The Odin runner still reports the pre-existing
ownership warning in `held_movement_survives_noop_interact_without_forcing_critical_save`
(the fixture assigns a string literal to the owned `run_id`); Turn the Page tests
report no allocation warnings.

HD visual revision, 2026-09-05: 478 Odin tests, check, optimized Linux build,
native asset verification, web build/download/heap audit, and Android debug
three-ABI compile/APK audit passed. Desktop, both mobile layouts, and Chromium
captures were inspected, including a 3× exposed-edge view. Source-face and
underside alignment tests cover both neighbor axes and fractional zoom/pan.
Soul room and Mistbound captures are pixel-identical before and after the
projection correction. The 60 fps collapse recording verifies render-state
immutability through the fall and retry. The existing depth-5/8/9 JSON test
saves still pass production checksum decoding and run installation. Visual
acceptance and physical-device validation remain human follow-ups.

Forgiving traversal revision, 2026-09-05: 480 Odin tests, check and optimized
Linux build passed. Regression cases cover lateral walking drift, off-center
dash landings with and without gaps, real wrong steps, capsule corner contacts,
and all 2,400 generated routes. The footprint and braking changes add no saved
state and retain the existing run-save schema.

Empty-space collision revision, 2026-09-05: 485 Odin tests, check and optimized
Linux build passed. Fallen cells block repeated walking and dashing, including
corner contacts and restored saves. Marked gaps block walking but remain
dashable, interrupted jumps cannot leave the player standing over a gap, and
all 2,400 generated routes remain solvable. No saved-state fields changed.

Floor-variation revision, 2026-09-05: six native 512×512 slabs pass the asset
hash, dimensions, silhouette-bounds and shared-anchor checks. All 486 Odin tests,
native/web source checks, optimized Linux build, web build/download/heap audit,
and Android debug three-ABI compile/APK audit passed. Desktop, mobile-layout and
Chromium captures verify readable route ink over the decorative variants. The
variant sheet and exposed-edge close-up preserve the Mist chamber dimensions;
the collapse capture still checks render-state immutability. The visual policy
keeps decoration stable through progress and the final win without gameplay RNG.
