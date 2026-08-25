# Arch Rogue — archived Python → Odin/raylib parity plan

Written 2026-08-11, after v0 ("the game starts and plays", M0–M5). This is
the spec and roadmap used to reach **feature parity** with the legacy
Python/Pygame game (5.2.1) for the **single-player desktop experience**, minus
the deferred tier below. The active Odin project now lives at the repository
root; the legacy implementation is archived under `arch-rogue-python/` and is
reference-only. Unless explicitly rooted elsewhere, historical Python module
paths in this document are relative to `arch-rogue-python/src/arch_rogue/`.
Source of truth for *how* we build stays in `ARCHITECTURE.md` (hard rules,
decisions); this file owns *what* and *in which order*. Post-parity platform
milestones may re-enter below without redefining the original desktop-parity
acceptance target.

## What parity means

- Player-facing behavior, content, and look match the pygame game: same
  archetypes/skills/enemies/bosses/items/themes, same tuning numbers, same
  visual identity (the authored Pixellab art), same moment-to-moment feel.
- Internals are free to differ (and already do: fixed-step sim, PCG streams,
  draw lists, baked sheets). Determinism per seed is a hard requirement;
  matching pygame's RNG sequences is a non-goal.
- Every ported number comes from the pygame source, not from memory; every
  pixel value ported divides by WORLD_SCALE=5 (decision log).

## Deferred tier (explicitly out of the parity push, 2026-08-11)

| System | Note |
|---|---|
| Multiplayer | client, relay server, wire protocol, lobby/join codes |
| Steam | steamworks, cloud saves, Deck cert, release tooling |
| Android | **Completed in MX-android (`6.0.0-alpha.21`)**: API-35/API-28 native Odin/NDK packaging for `arm64-v8a`, `armeabi-v7a`, and `x86_64`; GLES2/native-resolution presentation; packaged assets and audio; app-private persistence; lifecycle; semantic Back; and multi-touch playability. Soft-keyboard UI remains paired with the first shipping text-entry surface (likely multiplayer); the current single-player shell has no editable field. |
| Story mode & quests | **Completed in MX-story, 2026-08-14 (`6.0.0-alpha.18`)**: deterministic engine/corpus, panel cutscenes, guests, relics, minigames, Quest rooms, Hall of Unlost Echoes, Soul verdicts, and 15 endings. |
| Save/resume + Chronicle | **Completed in MX-save, 2026-08-17 (`6.0.0-alpha.20`):** local-first active-run persistence, durable profile/Chronicle, game-options persistence, recovery UI, 333-test coverage, a passed release profiling gate, and Matti's Chronicle perceptual signoff; Steam integration remains deferred. |
| In-game achievements | returns naturally together with Steam |
| Legacy graphics + perf overlays | **dropped**, not deferred: the rewrite is modern-look only; raylib obsoletes the blit-perf machinery |

Re-entry triggers worth remembering: deep-run playtesting triggered MX-save;
story returned through MX-story and unlocked the bar/garden's full flavor and
act structure; Android returned through MX-android. MP still wants the sim's
determinism, which every milestone must keep protecting.

## Inventory — what the pygame game contains (survey 2026-08-11)

Counts come from the archived `arch-rogue-python/` 5.2.1 tree; module
references below use the archive-relative convention defined above.

- **Archetypes** (content/archetypes.py): 5, with stats, class skills,
  bolt/melee/Big Hit kits, dash mobility, Rogue crit path. *v0: stats + one
  signature skill each.*
- **Enemies** (content/enemies.py): 10 regular + Gate Warden (final-room
  guard), spawn weights, roles/tactics (bruiser/flanker/skirmisher/caster/
  marksman/artillery/sentinel), authored EnemyAbility table (strike/bolt/
  fan/nova). *v0: 4 kinds with base melee/ranged AI.*
- **Bosses** (content/enemies.py BOSS_DEFINITIONS): 5 — ash_gallows,
  mycelial_matron, rime_chanter, void_sentinel, gate_tyrant (final) — at
  boss depths {3, 6, 9, 10}, plus minibosses, challenge rooms, elites
  (elite_modifier). Arena sealing, boss animation kit (idle/walk/attack/
  cast, last_attack_kind drives pose). *v0: arenas generate, no bosses.*
- **Dungeon** (dungeon.py, content themes): 72x72 floors, 8 themes with
  palettes + wall/floor art, special rooms (shop, bar, garden + 2 story
  rooms), solid furnishings, traps (3) + shrines (Oath Shrine, Forgotten
  Skill Altar, ...) + secrets, encounter templates, run modifiers,
  difficulty profiles (incl. Hell). *v0: layout + doors + boss arenas.*
- **Items** (content/equipment.py): 5 weapon + 5 armor bases, 35 affixes
  (damage types, attack/cast/move speed, thorns, lifesteal, procs, skill
  bonuses), 13 uniques, cursed + unidentified items, identify / remove-curse
  scrolls, potions, gold. *v0: bases, 5 affixes, potions, gold.*
- **Combat systems** (combat/): statuses + resistances (poison, chill, ...),
  damage types (physical/frost/arcane/shadow/poison) with colored floaters,
  familiars (crow/wisp), Ranger spirit beast, NPC allies, knockback/shove
  contact resolution, projectile variety, class skills (Time Skip, Ambush
  Bell, Nova, Spirit Call, Spirit Beast). *v0: melee arc + bolts/fans,
  windup AI, kite bands, knockback, thorns/lifesteal.*
- **Progression** (content/progression.py, 1740 lines): XP/levels, memory
  tokens, disciplines with 100 upgrades, character sheet. *v0: XP/levels.*
- **World rendering** (rendering/, sprites/): authored world art — 36 world
  sprite keys, 29 props, 30 item icons, world_modern set; fog of war with
  explored memory (lit floors), lantern-only dark floors, minimap with
  route thread, guiding floor glow, lighting halos, cutscene framework.
  *v0: debug prisms + multiply lightmap; actor sprites are final art.*
- **UI** (menus/): title, options (Display/Controls/Audio/Lights/
  Difficulty/MP), character sheet, inventory, chronicle, controls, state
  overlays, text input. *v0: title, select, minimal inventory, HUD, death.*
- **Audio** (audio.py): procedural SFX + per-run NES-style music →
  **decision: authored .wav/.ogg only** in the rewrite. *v0: 10 baked SFX.*
- **Input**: keyboard+mouse, controller support, rebindable controls.
  *M6/M7: pygame-compatible world-axis WASD/arrows, continuous cursor aim,
  held-LMB walking + target-gated auto-melee, interaction pickup, 5/6 potions,
  modal keyboard/mouse inventory, Ctrl+wheel world zoom, minimap toggle/zoom,
  and pointer navigation for the current title/select/death/inventory surfaces.
  M8 supplies the missing action slots; controller/rebinding remains M9.*

## Roadmap

Each milestone keeps the v0 discipline: numbers ported from source, headless
tests for sim behavior, screenshot verification for visuals, `-vet` clean,
CHANGELOG entry + version bump (6.0.0-alpha.N) on completion.

### M6 — World & visual parity  ← OPEN (not closed until Matti signs off on
### visual parity side-by-side; M7 proceeds in parallel)

Status 2026-08-12: HD world art baked and rendering (4 floor variants, 10
wall variants, animated ping-pong stairs, orientation doors, item icons,
mipmapped trilinear at sub-native scale); 8 themes + exact tint formula;
LOS fog with explored memory on normal floors and none on dark; diagonal GPU
revelation/live-LOS fields with smooth reveal and strict conceal; depth-scaled
themed ambient, LOS-clipped multi-source lights, contact shadows, foreground-
wall actor ghosts, and authored idle animation; minimap with dark-floor BFS
route thread; desktop mouse/keyboard parity for M6/M7 gameplay and current
menus. Depth-1 and deterministic depth-10 normal/dark AMD/OpenGL captures
verified projection, fog/lantern edges, and ambient separation on 2026-08-12.
Remaining: Matti's side-by-side visual signoff. Pygame's exact guiding-floor thread is
story-relic state, so it stays with the deferred story system; the rewrite's
always-on dark-floor stairs route remains a documented accessibility divergence
until that state exists. M9 added the authored shop/bar/garden floors, actors,
props, collision, and minimap identities.

Door-density note (resolved in M9, 2026-08-11): before alpha.8 the generator
had only pygame's ordinary 24% side-room sealing roll plus a one-room fallback,
so a first floor with exactly one closed room/door was expected. Alpha.8 now
rolls and seals the Shop (75%), Bar (50%), and Garden (50%) independently,
before ordinary doors. Floors can still legitimately roll few special rooms;
story-only quest/soul rooms remain deferred. When the lossless-soul hall is
ported, it must ALWAYS hold a mist bank (Matti, 2026-08-12): exempt it from
the `VISUAL_MIST_ROOM_CHANCE` roll in `visual_mist_zones` and stamp it misty
unconditionally — the opposite of the shop/bar/garden interior damping.

The dungeon stops looking like debug geometry and starts looking like
Arch Rogue.

- Theme system: port the 8 DUNGEON_THEMES (palettes, accents, wall/floor
  art selection) + per-floor theme choice (no-repeat rule; story-driven
  themes deferred with story).
- World art bake: extend tools/ to bake the world manifest (walls, floors,
  stairs, doors, torches/props) and the 30 item icons into sheets +
  manifest; renderer swaps prisms/markers for authored art with the debug
  shapes kept as fallback.
- Fog of war: explored-tile memory on lit floors (unexplored = void,
  explored-unseen = dimmed), lantern-only dark floors (no memory), LOS-based
  reveal. The backlog's "fog leaks over walls" fix lands here for free if
  reveal is LOS-based from the start.
- Minimap: explored layout, player/stairs markers, the route thread on dark
  floors.
- Ground items render with their real icons + rarity glow.
- Acceptance: same-theme side-by-side with pygame reads as the same game;
  fog/minimap behave; 60 fps holds on a full floor.

### M7 — Bosses & run completion  ← IN PROGRESS

The run gets a spine and an ending.

Status 2026-08-11: full 11-enemy roster (Gate Warden final-room only),
elites (4 ported modifiers + chance curve), Oathbound minibosses, all 5
bosses with authored ability kits (strike/bolt/fan/nova), boss floors at
3/6/9/10 with themed selection + Tyrant theme titles, arena sealing into
locked doors + restore on death, guardian-gated stairs, victory at depth
10, boss HP bar + ground-ring tells, committed windup rings, exact final-Tyrant
post-scaling, large-boss fallback fan, and matching death/victory summaries.
Remaining: encounter templates + run modifiers, challenge rooms, guaranteed
unique/Rare boss reward hooks, tactics table (strafe/hold_anchor/
reposition_for_los), and obstacle routing/stuck recovery around solid
special-room furnishings. Venomous typed damage/status identity landed in M8.

- Remaining 6 regular enemies baked + their tactics table (kite bands per
  role, hold_anchor, reposition_for_los), depth-based spawn weighting.
- Elites (stat modifiers + visual tell) and minibosses; encounter templates
  (standard/elite_pack/ambush/challenge_room) + run modifiers.
- 5 bosses: sprite/animation bake (attack + cast clips, last_attack_kind
  pose selection), authored ability kits (strike/bolt/fan/nova), arena
  sealing + door locks, boss HP bar.
- Depth-10 gate_tyrant victory → win screen + run summary; death screen
  gains the same summary.
- Acceptance: a full 1→10 run is winnable and loseable, bosses read like
  their pygame selves.

### M8 — Combat depth  ← COMPLETE (2026-08-11, 6.0.0-alpha.7)

Status: seven typed damage channels, the full status/resistance core, four
independent combat actions for every archetype, all five class skills, Acolyte
spirits, Ranger Spirit Beast AI, Rogue Precision plumbing, the canonical
35-affix table, and cursed/unidentified equipment are implemented and covered
headlessly. Fresh Acolytes summon the canonical rank-zero Wisp and fresh Rogues
have no Precision chance; the already-ported Crow/Precision rank ladders become
obtainable with M9 disciplines.

- Statuses + resistances (poison/chill/burn/stun family) with icons/tints;
  damage types + colored floaters; enemy resistances from content.
- Class kits: player bolt as core ranged, dash, and the real class skills —
  Time Skip, Ambush Bell, Nova, Spirit Call, Spirit Beast — with costs,
  cooldowns, and action-bar icons (already-baked HUD icon assets).
- Familiars (crow/wisp) + Ranger spirit beast (pet AI).
- Rogue precision crits; full affix set (35) incl. attack/cast speed and
  proc effects; cursed + unidentified items with identify / remove-curse
  scrolls.
- Acceptance: each archetype plays like its pygame counterpart; affix/status
  math spot-checked against source values in tests.

### M9 — Character, meta & shell  ← COMPLETE (2026-08-11, 6.0.0-alpha.8)

Status: the complete 100-node discipline table, memory-token acquisition,
two-path commitment, character overview/tree UI, all four difficulty profiles,
first-clear Hell unlock, Shop/Bar/Garden rooms, persistent desktop options,
pause/title shell, and remappable raylib gamepad input are live. Every
discipline explicitly tracks effect coverage: 38 stat-complete, 15 partially
wired, and 47 deferred effect riders for later parity passes; the table and
purchase rules themselves are complete.

- Character sheet + memory tokens + disciplines (port the upgrade table,
  effects wired incrementally — table-complete, effect coverage tracked).
- Difficulty profiles + selection (Hell groundwork; endless-Hell stays
  backlog), per-difficulty multipliers into population.
- Shop special room + buy/sell UI + gold economy; bar/garden flavor rooms
  (appearance + toast/heal behavior; story hooks stay deferred).
- Options menus (fullscreen, FPS cap, zoom, difficulty, binary audio cues,
  lighting, controller enable/mapping), atomic persistence, pause, and the
  proper New Run / Options / Quit title shell. The pygame build currently has
  binary audio cues rather than volume sliders, so alpha.8 follows that source.
- Controller support (raylib gamepad) with the pygame binding layout,
  deadzones/aim snap, menu hysteresis, and a live button/trigger remap screen.
- Acceptance: a new player can navigate everything without the keyboard
  cheat-sheet line.

### M10 — Audio, feel & parity audit  ← COMPLETE (2026-08-12, 6.0.0-alpha.9; audit complete, full parity not declared)

Status: authored SFX have a required manifest, validation/lifecycle, and live
start/UI/Bell/boss/victory/Bar emitters; trap/shrine/secret cues are reserved
for their missing systems. Background-music work deliberately waits for
Matti's incoming tracks and stronger music specification. Movement animation
now follows actual displacement and source cadence, actions use local authored
attack/cast/dash/die/dead timelines, death delays its summary through the full
die sequence, typed impact/death/screen-pain events are deterministic, and the
camera uses source framing/smoothing. The source has no gameplay hit-stop or
camera shake, so the parity implementation correctly has neither.

The audit also fixed the missing final-Tyrant scaling, three-bolt large-boss
fallback, and death summary. It found the following real parity debt;
completing this audit means the gaps are no longer implicit, not that they
disappeared:

- **Gameplay/content backlog:** 13 unique items and guaranteed boss/miniboss
  reward classes; six encounter templates, eight run modifiers, and challenge
  rooms; three traps, seven single-player shrines, five secret kinds and the
  Cartographer stash; the authored nine-role tactics/LOS-reposition/pathing
  layer; and the 47 deferred plus 15 partial discipline effect riders.
- **Shell/accessibility backlog:** About/Credits/Quick Help and UI scaling.
- **Audio backlog:** distinct per-enemy and per-boss hit takes/routing remain
  generic; finalize those together with the incoming music package and its
  stronger audio direction rather than inventing a temporary taxonomy now.
- **Remaining visual parity after alpha.10:** M6 side-by-side signoff; exact
  telegraph/impact/trail/slash raster treatment, HUD/menu authored composition,
  enemy cast-pose distinctions, isometric minimap, and graphics/resolution/
  lighting-detail options. Lighting/fog/contact-shadow/actor-wall-ghost parity
  is now implemented without changing deterministic sim timing.
- **Deferred/re-entered boundary:** exact relic-guidance behavior was story-bound;
  save/Chronicle has since re-entered as MX-save and Android now re-enters as
  MX-android, while multiplayer, Steam integration, and achievements remain
  under the deferred-tier agreement.

Acceptance for alpha.9: the M10 audit is exhaustive enough to make every known
gap actionable; the bounded feel/audio foundation is tested and warning-clean.
Feature parity itself remains open until the ledger and visual signoff close.

### MX.x finalize gameplay / visuals / feel parity

#### MX.1 Known gaps

- A bug surfaced in tests: when entering boss room, player immediately gets stuck under spawned door, make sure all boss room related logic is sound
- Minimap needs to be isometric as in pygame version, double mini map size
- Import graphical assets for menus / HUD
  - Layout is a bit better sometimes (e.g in char, inventory) in oding/raylib version -> use good judgement when importing -> ask human before locking implementation!
  - Progress bar for XP is good in odin version, let's keep that (generate nice container for it)
  - Panels, glyphs, icons all look good on pygame so import them
- Archetype selection needs similar carousel as in pygame version
- Scaling and resolution related stuff still unpolished
  - Archetype sprite in-game also looks a bit low-resolution (currently still, not animated), maybe this is a scaling / resolution issue, check on it anyway. This is probably a zoom issue, let's first make default zoom the same as in pygame version and allow zooming closer, as close as with pygame version
  - Should we import resolution / scale settings from pygame version? This would be a good point to think about it and make better / more user friendly (and compatible with as many platforms as possible out of box)
- Max zoom (and default zoom) is quite wide, we also need to be able to zoom closer
  - Max zoom can be reverted back, default and min are now good

#### MX.2 — Combat correctness, bosses, and enemy intelligence

Status: IMPLEMENTED 2026-08-12 (alpha.12). All five gaps below are ported and
pinned by `tests/mx2_combat_test.odin` (boss selector bands/rotation/phase,
doctrine bands, pack alert + memory, wall/furnishing routing without stalls,
knockback chain + radii separation, elite/Oathbound identity). The acceptance
criteria hold: the Tyrant alternates Gate Strike and Shadow Volley, every boss
retains an attack at each authored range (the 1.9..2.0 dead band closes
distance, as in pygame), and the 163-test suite stays deterministic and
warning-clean. The audit text is retained below as the port contract's index.

Audit refreshed 2026-08-12 against pygame 5.2.1 and Odin alpha.10. The
following are confirmed implementation gaps, not guesses from screenshots.
Do not reopen alpha.10's completed smooth LOS/FOW, depth darkness, clipped
lights, contact shadows, actor wall shine-through, hit flashes, status pips,
or authored player action/death timelines while doing this work.

- **Fix boss attack selection before adding more boss spectacle.** Pygame's
  `combat/abilities.py` gives boss bolt/fan abilities a six-tile inherited cast
  reach, avoids immediately repeating `last_ability`, falls back to a legacy
  cast/melee band when authored actions are unavailable, and multiplies
  authored cooldowns by `0.8` below half health. Odin's
  `sim.odin::try_start_ability` scans in fixed table order, inherits the boss's
  base attack range, has no boss-specific cast-band fallback or last-action
  rotation, and always applies the full cooldown. It can fall through to the
  ordinary enemy attack path, but the Tyrant is melee-classified there. This
  makes the Gate Tyrant's `Shadow_Volley` impossible:
  its minimum range is `2.0`, while final scaling caps its inherited reach at
  `1.9`. Port the selection contract and test every boss at close, cast-band,
  and out-of-range distances, including the low-health phase.
- **Port authored enemy tactics as a separate axis from enemy rank.** The
  pygame `content/enemies.py::TACTICS` and `combat/enemies.py` behavior includes
  bruiser/flanker/skirmisher/caster/marksman/artillery/sentinel doctrines,
  per-role range bands, strafe/hold-anchor choices, pack alert and target
  memory, and LOS repositioning. Odin currently has direct melee pursuit plus
  one generic ranged kite band; `Enemy_Role` only distinguishes normal/elite/
  miniboss/boss. Preserve that reward rank, but add tactical identity and the
  authored parameters.
- **Add obstacle routing and bounded stuck recovery.** Port the shared
  radius-limited navigation field from `combat/pathing.py`, then the doorway
  yielding, LOS sidestep, furnishing detour, packmate arbitration, and
  displacement watchdog from `combat/enemies.py`. Keep open-room greedy motion
  when a direct route is valid so the port does not make every enemy look like
  it is following a grid path. This is required for reliable pressure around
  doors, corners, bosses, and solid Bar furniture.
- **Finish knockback and contact physics.** Ordinary melee/projectile knockback
  should enter the same decaying, collision-safe velocity path as Big Hit;
  heavy throws should be able to transfer through a pack as in
  `combat/damage.py` / `combat/enemies.py`. Actor separation must use actual
  player/enemy/boss radii instead of one fixed enemy radius, without pushing
  actors through walls or onto blocked stairs.
- **Restore elite/miniboss gameplay identity.** Odin ports the four modifier
  stat packages, but elites retain their base name/color and all receive one
  generic accent ring; `promote_miniboss` clears the display override, so an
  Oathbound miniboss reads as an ordinary enemy. Port modifier prefixes,
  palette/tell differences, relevant tactic changes, the Oathbound name and
  accent, and distinct elite/miniboss death emphasis.

Acceptance: the Tyrant visibly alternates strike and shadow-cast pressure;
each boss retains an attack at every intended range; ranged and melee roles
navigate a furnished/door-heavy test floor without permanent stalls; same-seed
combat remains deterministic and warning-clean.

#### MX.3 — Build-defining combat and discipline effects

Status: IMPLEMENTED 2026-08-13. All 47 Deferred and 15 Partially_Wired ledger
entries are wired and reclassified `Fully_Wired` (the enum member was added for
this); `tests/mx3_disciplines_test.odin` pins each slice with pygame-cited
constants and the coverage census in `tests/progression_test.odin` now expects
38 Stats_Only + 62 Fully_Wired. Wired per the audit below: Warden cleave
tiers/riposte counter/Aegis/Temporal riders and Time Skip tuning incl. the
Bulwark Wave pulse and Eternal Moment refund; the Rogue Smoke/evade/stamina
riders and the complete Ambush Bell tuning snapshot with live detonation
crit/kill-refund chain; Arcanist fans/pierce/homing/splinter TTL, the
one-charge-per-cast Storm chain with elite priority, Nova rank radius, room
engulf, and Permafrost chill; Acolyte melee/spell siphon ladders (live, incl.
blood-bound familiars), Veil shield/cost/regen, Gravebind bind + grave echo,
Blood Pact lifesteal; Ranger fan/pierce/homing/snare arrows, Beastmark
snare/amp/Vault, Beast-path bite riders (Pack Tactics, Alpha shove, Spirit
Companion arcane, Primal Lord), and the petting slice (readiness, chain
priority, 2·2^degree heal, paired pose, world prompt, baked pet clip). The
Spirit Beast attack clip now samples its own attack clock instead of
locomotion `anim_time`.

Accepted parity divergences (Odin has no unique-item tier or the named gear
affixes below; revisit only if that content is ported): "smoke crits",
"splinter storm", "sky volley", "counter smite", "vanish on dash" uniques; the
"Dash guard", "Nova radius", "Time Skip duration", "Ambush Bell radius" named
affixes; the on-damage smoke proc; and the pet prompt shows flat text without
the computed heal amount. The original audit text is retained below as the
port contract's index.

The discipline table and purchase rules are complete, but its own ledger still
marks **47 effects Deferred and 15 Partially_Wired**. Static bonuses are not
parity when the purchased description promises a new attack, defense, proc, or
skill behavior.

- Wire the remaining melee/defense/mobility riders at the existing action and
  typed-damage seams: Warden cleaves, reach, stuns, counters and Aegis;
  Rogue Smoke/Veil/Shadowstep effects; and the corresponding Arcanist,
  Acolyte, and Ranger on-hit/status/cost/cooldown behaviors. Preserve already
  working stat totals, path commitment, Rogue Precision, and base class kits.
- Port projectile path shaping from `combat/attacks.py` and
  `combat/projectiles.py`: Ranger and Arcanist fan counts, additional pierce,
  homing, class status riders, and the shared one-charge-per-cast Storm chain.
  Odin currently emits one bolt (or an equipment-driven fixed fan), has no
  homing payload, and its equipment chain proc is not the Storm discipline.
- Make signature skills use discipline-derived tuning rather than their current
  baseline constants: Time Skip factor/duration/stun pulse; Frost Nova radius,
  room engulf and chill duration; Ambush Bell setup/radius/lure, poison/snare,
  facing crits and kill refunds. Snapshot per-cast values onto projectiles or
  bells where pygame does so; do not read mutable build state at impact time.
- Finish companion combat riders while keeping the already-ported rank stat
  ramps: Spirit Beast Pack Tactics, Primal Lord and Alpha shove; Ranger Spirit
  Companion arcane conversion; Acolyte Blood-path spell leech; target-condition
  bonuses and champion behavior.
- Port the non-story Spirit Beast pet interaction as one slice: readiness and
  priority rules, base two-HP heal doubled for every acquired Beast-path degree,
  cooldown, paired Ranger/beast pose, world prompt, and the already-baked `pet`
  clip. Also fix Beast attack playback to sample
  `attack_anim_timer`; it currently selects `.Attack` using locomotion
  `anim_time`, so the clip can freeze on an arbitrary frame.

Acceptance: every discipline entry is either fully wired to its player-facing
text and reclassified with a focused test, or explicitly accepted as a parity
divergence before MX.8; all five fresh and late-build archetypes complete
representative combat fixtures.

#### MX.4 — Descent plan, encounters, and floor-to-floor pressure

Status: IMPLEMENTED 2026-08-13 (alpha.14). `floor_plan.odin` carries all eight
run modifiers and six encounter templates; `generate_run_plan` authors the
ten-depth plan at run start on its own stream (9, salt "PLAN") while theme and
darkness keep their pre-MX.4 per-depth streams, so recorded seeds replay
identically and the darkness determinism test stays green. Modifier/template
pressure is applied (count, elite/miniboss odds inside the pygame clamps,
HP/damage/aggro before difficulty, loot and curse chance); trap/shrine/secret
pressure values are carried as data for MX.5. The challenge_room guardian
spawns marked in a random non-guardian room and its clear is tracked; its
guaranteed Rare remains MX.5. Run header, wrapped floor summary, truthful
stairs preview (reconciled loot hooks — no stale "chance" wording), the
non-blocking arrival title/fade, the run-level Bar ledger, and the depth-10
immortal Bar Dancer summon are all in, pinned by `tests/mx4_descent_test.odin`.
The original spec is retained below as the port contract's index.

Odin varies depth, theme, darkness, and difficulty, but does not yet carry the
pygame run's authored floor plan. That removes much of the risk/reward rhythm
which makes ten floors feel like a descent instead of ten independent boards.

- Port all **eight run modifiers** and **six encounter templates**. Generate a
  deterministic ten-depth `Floor_Plan` at run start using its own RNG stream:
  no repeated adjacent theme, depth 1 standard, authored boss depths, dark-floor
  schedule, threat/risk tags, encounter key, reward hint, and boss identity.
  Apply the selected modifier/template to HP/count/aggro, elite/miniboss odds,
  loot and cursed-reward pressure rather than merely displaying its name. Carry
  the trap/shrine/secret pressure values here, then wire them when MX.5 adds
  those live entity systems.
- Port the six encounter templates as pygame actually implements them: mostly
  floor-wide enemy/elite/trap/loot/secret pressure changes, not invented bespoke
  room layouts. Despite its name, `challenge_room` currently guarantees one
  challenge-role miniboss in a random non-boss-floor room and tracks its clear;
  it does not construct a dedicated marked room. Its guaranteed Rare reward is
  covered by MX.5. Ordinary boss depths still need their mandatory guardian and
  sealed stairs.
- Surface the plan during play: current modifier plus floor summary in the run
  header, and pygame's next-theme/risk/reward preview in the stairs interaction
  hint. Reconcile old boss `loot_hook` strings with the runtime contract in MX.5
  before displaying them: bosses guarantee a Unique and guardians a Rare, so do
  not port stale "chance" wording. Keep the existing concise Odin layout where
  it reads better, but do not lose actionable information.
- Give descent a short non-blocking transition/arrival treatment and depth/theme
  title so the floor change reads deliberately. Pygame uses a loading screen
  because its synchronous prewarm can be slow; Odin should not add an artificial
  stall just for implementation parity. Preserve the existing combat-boundary
  reset and 25% mana/stamina recovery exactly.
- Track Bars across the whole run. When every generated Bar was toasted, depth
  10 should summon the immortal fighting Bar Dancer companion from
  `combat/familiars.py`; Odin currently resets the only toast flag each floor
  and renders the dancer solely as stationary room flavor.

Acceptance: a fixed seed exposes a stable ten-floor preview and produces the
same plan on replay; encounters visibly differ by template/modifier; stairs
truthfully preview the next floor; a complete 1→10 run can exercise challenge
rooms, mandatory guardians, Bar pilgrimage, and final victory without state
leaking between floors.

#### MX.5 — Interactables, secrets, uniques, and reward payoff

Status: IMPLEMENTED 2026-08-13 (alpha.15). `interactables.odin` carries all
three traps (hidden/revealed/triggered, dt*6 materialize fade, unevadable
difficulty/depth-scaled damage), the seven single-player shrines with their
exact one-use effects and per-kind color/light identity (Vigil stays
MP-deferred), the five secret kinds plus the Lost Cartographer's Stash with
FOW-safe reveal, guardian/bargain resolutions and run counters, and the
wall-face touch driving the formerly orphaned baked `wall_face` clip.
`uniques.odin` ports all 13 named uniques with authored stats (no rolled-gear
clamps), the six new gear skill-bonus channels, and every bespoke
unique_effect hook wired into the combat procs. Kill rewards honor the
contract: the Tyrant guarantees a named Unique, floor guardians and
Oathbound/challenge minibosses guarantee Rare equipment, the ordinary 28%
roll stays independent, and notable finds land in a run ledger shown on the
end-of-run summaries. Placement rolls live on stream 10 so pre-MX.5 seeds
keep their enemy layouts; the trap/shrine/secret audio cues flipped from
future_emitter to runtime. Seven new per-type shrine sprites and the secret
cache prop were generated (Pixellab, tag arch-rogue-shrines-6x) — the
intentional visual upgrade the spec called for — and both are solid room
furniture: one tile each, tile-aligned base art, no contact shadow, honoured
by collision, routing, and spawn placement. Pinned by
`tests/mx5_interactables_test.odin`. The original spec follows as the port
contract's index.

Several content tables or placeholders exist without their gameplay lifecycle.
Implement each as population → simulation/interaction → painter ordering →
light/SFX/UI, not as a renderer-only prop.

- Port all three traps, with pygame's hidden/revealed/triggered states,
  proximity reveal easing, generic difficulty-scaled damage, burst/text
  feedback, and the already-reserved trap cue. Typed damage or trap-specific
  statuses would be a future enhancement, not current parity.
- Port the seven single-player shrines (Mending, Insight, War, Haste, Fortune,
  Oath, Twilight), their one-use effects, color/light identity, reward text and
  cue. `Vigil Shrine` remains multiplayer-deferred.
- Generate a distinct sprite for every single-player shrine type; neither Odin
  nor the current pygame authored-prop path has unique per-type shrine art, so
  this is an intentional visual upgrade rather than strict parity.
- Port the five ordinary secret kinds plus the Lost Cartographer's Stash:
  discovery gating, FOW-safe hint/reveal, guardian or bargain where authored,
  reward construction, run counters, and cue. Expose the already-baked
  `world.wall_face` animation and trigger its transient tile state from the
  wall-touch interaction instead of leaving the asset orphaned.
- Port all **13 named unique item definitions** and their bespoke effect hooks.
  Odin currently defines a `Unique` rarity color but has no unique blueprint or
  generation path.
- Match kill rewards exactly: bosses guarantee a named Unique, minibosses/floor
  guardians guarantee Rare equipment, and both retain the independent ordinary
  drop roll. The current 100% call to generic `make_loot` can return a potion,
  scroll, or ordinary item and therefore does not satisfy the reward contract.
  Include gate-seal feedback, notable-loot text, and the larger elite/miniboss/
  boss payoff burst. Boss last words remain with the deferred story corpus.

Acceptance: every difficulty modifier that mentions traps/shrines now affects a
live system; interactables never leak through FOW; boss and guardian kills
always produce their promised reward class; every unique can be generated,
equipped, and have its effect covered headlessly.

#### MX.6 — Combat readability, animation state, and effects

Status: IMPLEMENTED 2026-08-13 (alpha.16). Enemy commits retain a semantic
Attack/Cast action through their independent recovery clock; boss Cast uses the
intentional attack-sheet fallback, while missing ordinary/familiar action clips
remain grounded in locomotion. The exact floor aim cone, six owner/class
projectile silhouettes, typed tint/rotation/four-sample trails, contact-centered
slash crescent, expanded bounded Feel vocabulary, exactly-once Bell arming,
ranked death/payoff events, and transient lights are live. Direct raster and
labels use a per-fragment live-LOS shader even with Lighting off; alpha.16's
origin-gated shader-less fallback is superseded by MX.7's conservative compact-
cue policy. Nova uses coherent isometric
radius geometry and its mastered room effect runs as a deterministic clipped
light wave. `tests/mx6_readability_test.odin` adds 21 tests (222 total), and
`tools/capture_mx6.sh` records the 34-shot action/direction/FOW acceptance
matrix. Focused headless validation passed all 21 MX.6 tests on 2026-08-13.
AMD/OpenGL captures verified grounding, action poses, silhouette/color
separation, boss fallback, familiar clocks, and lighting-off wall clipping.
The original spec follows as the port contract's index.

The semantic combat core is ahead of its raster presentation. Preserve current
windup rings, status tints/pips, damage numbers, hit flashes, death timelines,
and screen-pain flash while filling these gaps.

- Restore the floor-level player aim cone from
  `rendering/actors.py::draw_aim_cone`, behind actors and foreground occluders.
  It is render-only and must not quantize gameplay aim.
- Store the committed enemy action kind through recovery. Non-boss projectile/
  nova actions should select `.Cast` when authored and use a cast-origin cue;
  melee selects `.Attack`. Match pygame's deliberate boss fallback to its
  attack clip instead of assuming every boss owns a distinct cast sheet.
- Replace circle-only projectiles and the single line arc with pygame's
  parity-grade procedural treatment: owner/archetype projectile frames, typed
  tint, velocity rotation, velocity-sampled trailing orbs, and a slash sprite
  with growth/fade, trailing strokes and endpoint sparks. A raylib-native or
  committed-asset alternative is welcome only if side-by-side clearer; validate
  whichever pipeline ships and keep simple geometry as its fallback.
- Extend the bounded deterministic `Feel_Event` vocabulary for cast, dash,
  Time Skip, Nova, summon/command, Bell plant/arm/detonate, knockback travel,
  elite/miniboss death and boss payoff. Add their short-lived lights to the
  existing LOS-clipped light compositor; hidden effects must never illuminate
  or label unexplored space.
- Validate every player, enemy, boss, and familiar direction/action in captures:
  grounding, frame cadence, pose transition, weapon/apparel retention, and
  telegraph overlap. Fix the Spirit Beast attack-clock issue in MX.3 before
  judging its sheet.

Acceptance: a capture matrix for every archetype action and every enemy ability
shows the correct pose/effect; player archetype projectile silhouettes and
color-coded damage channels remain readable; effects stay deterministic,
bounded, FOW-safe, and do not alter simulation timing.

#### MX.7 — World polish and raylib-suitable visual upgrades

Status: IMPLEMENTED 2026-08-13 (alpha.17), pending Matti's perceptual capture
signoff on a machine with a display. Discovery-gated semantic minimap markers,
fixed glyphs, edge arrows, the projected player-facing tick, and the asymmetric
dark-floor policy are live. Shops now cache 7–12 deterministic room-sized gold
stacks across all five authored assets/sizes, reserve them against population
without turning them into collision, and send them through ordinary painter
sorting. Lighting/effect failure paths are fail-closed for FOW. A deterministic
46-shot all-theme/world-feature harness and an uncapped release stress profiler
own manual/GPU acceptance; 9 focused tests bring the suite to 231. The current
headless environment passed check + all tests but has no display/Xvfb, so it
could not execute screenshots or hardware timing. Normal-map detail was
explicitly evaluated and not shipped: full maps would materially increase the
already-large decoded asset footprint, per-frame actor maps risk shimmer, and
there is no A/B evidence of a clear visual upgrade within the frame budget. The
existing GPU radial/LOS compositor remains the operationally safer raylib path.
The original spec follows as the port contract's index.

- Beyond MX.1's isometric minimap projection, port discovery-gated stairs/Bar/
  Garden markers, marker glyphs, off-viewport edge arrows, and the player-facing
  tick from `rendering/minimap.py`. Normal floors retain all discovered markers;
  dark floors show Bar/Garden only in live visibility, while once-seen stairs
  remain marked and clamp to an edge arrow. Story-relic guidance remains
  deferred; the documented dark-floor stairs route stays until story state
  returns.
- Replace the hard-coded three Shop gold piles with pygame's deterministic
  room-size-aware dressing (roughly 5–12 valid stacks), fed through the normal
  reserved-placement and depth-sorted prop paths.
- Evaluate pygame's desktop normal-map lighting as a raylib shader pass. The
  parity goal is readable directional response on actors/walls under nearby
  colored lights, not a literal port of pygame's CPU/cache implementation.
  Keep it optional behind a lighting-detail setting and retain the current
  ambient/radial compositor as fallback if the shader is not visually or
  operationally better.
- Run side-by-side captures for all eight themes at representative shallow and
  deep normal/dark floors, plus boss arenas, doors, Shop/Bar/Garden, crowded
  combat, loot, traps, shrines, and secrets. Check projection, painter ties,
  wall/door coverage, fog boundaries, light clipping, actor ghosts, shadows,
  sprite scale/filtering, and visual hierarchy. Screenshot tests verify policy;
  this manual matrix owns perceptual signoff.
- Hold 60+ FPS on a fully populated floor with lighting and effects enabled.
  GPU-native improvements are welcome when they preserve authored pixel art,
  deterministic simulation, and the established alpha.10 visibility rules.

Acceptance: Matti signs off the capture matrix side-by-side; no visible object,
label, health bar, number, light, or effect leaks through FOW; normal-map detail
ships only if it is a clear upgrade; no visual pass regresses frame pacing.
Run `tools/capture_mx7.sh` for the 46-shot policy/perceptual matrix and
`tools/profile_mx7.sh` from a real GPU/display session for the three-run release
p95 gate (software GL is deliberately rejected for performance signoff).

#### MX.8 — Parity closure audit

Status: **COMPLETE 2026-08-14 (`6.0.0-alpha.19`)**. Thirty focused MX.8
closure-audit tests bring the suite from 271 to 301. `odin check src -vet`,
`odin test tests -vet`, and `odin build src -vet -o:speed` (release) are all
clean. The sole remaining item from that closure audit is Matti's M6
side-by-side visual signoff on a display machine; MX-save is a later,
separately re-entered milestone.

- Run focused headless fixtures for every system above, then the complete Odin
  suite, release build, and vet/check.
- Play deterministic full 1→10 runs with all five archetypes, including at
  least one high-difficulty run, every boss, each encounter template, each
  interactable family, unique rewards, shops/refuges, death, and victory.
- Reconcile every M6/M7/M10 backlog line and every discipline coverage marker.
  Delete stale claims only when a test or signed-off capture proves closure;
  move intentional differences to an explicit divergence list.
- Re-audit the post-parity boundary: story/quests completed through MX-story,
  save/Chronicle completed through MX-save, and Android completed through
  MX-android; multiplayer, Steam/achievements, and incoming music stay out unless
  separately brought back into scope.

**Accepted:**
- Full 1→10 runs: all five archetypes (Warden, Rogue, Arcanist, Acolyte,
  Ranger) drive from depth 1 through 10, kill the Gate Tyrant, complete the
  story epilogue, and reach victory. A Hell-difficulty Warden run also
  completes. Determinism per seed holds: same seed produces the same plan.
- Every boss depth (3/6/9/10) spawns at least one boss; boss kills drop
  notable loot or ground items; the Gate Tyrant death sets `tyrant_dead` and
  the story epilogue flow sets `victory`.
- All six encounter templates (Standard, Elite_Pack, Ambush, Hazard_Cache,
  Treasure_Room, Challenge_Room) and all eight run modifiers appear across
  80 seeds.
- Every interactable family is exercised across 40 seeds: 3 trap kinds, 7
  shrine kinds, 6 secret kinds (including Cartographer Stash), shops, bars,
  and gardens.
- Discipline coverage: 38 Stats_Only + 62 Fully_Wired = 100 nodes, with 0
  Untracked/Partially_Wired/Deferred — the ledger is clean.
- All 13 unique items construct faithfully; 5 bosses, 8 themes, 5 archetypes,
  and 4 difficulties are defined and verified.
- Shop transactions work via `shop_buy`; bar refuge toasts increment the
  run ledger; player death is achievable; kill rewards grant XP and gold;
  the kill ledger accumulates across the full descent.
- Post-parity boundary: story mode is complete (MX-story), save/Chronicle is
  implemented in MX-save, and Android is complete in MX-android; multiplayer,
  Steam/achievements, and incoming music remain explicitly deferred; legacy
  graphics and perf overlays are dropped.
- **Open MX.8 item:** M6 side-by-side visual signoff requires Matti's capture
  on a display machine. This remains the only open gate from the MX.8 audit;
  MX-save's separate Chronicle perceptual signoff is complete.

Parity closes only when there are no implicit gaps: each remaining difference
is either fixed, visually signed off, or explicitly accepted and documented.

#### MX-story — Full story mode with panel cutscenes and generated art

Status: **COMPLETE 2026-08-14 (`6.0.0-alpha.18`)**. Thirty-seven focused
MX-story tests bring the suite from 231 to 268. The strict 81-file art verifier
and responsive 640x480/1280x720/4K geometry contracts pass; the exact 15-shot
production capture matrix remains the visual sign-off harness.

Spec'd 2026-08-12 with Matti; this milestone un-defers the former "Story mode
& quests" row and its story-bound special rooms.

Scope — **full story mode**: the StoryEngine port (arcs, factions, relics,
dilemmas, tethers, gate/endings, flags), story guests as in-world friendly
NPCs, relic gameplay effects, the quest room and Hall of Unlost Echoes
(lossless-soul hall — which ALWAYS rolls a mist bank, see the M6 note), soul
interactions, and the story minigames. Choices remain consequential end to
end: aid/bargain/defy, relic picks, and soul verdicts steer text, guests, and
the 15 authored endings exactly as in pygame 5.2.1.

Presentation — deliberate divergence from pygame's theatrical stage. The
pygame proscenium renderer (curtains, footlights, stage props, ambient
particles, and the procedurally drawn moving actors) is **not ported**.
Cutscenes render instead as a compact "story dialog" panel over live
gameplay, HUD-like: generated backdrop artwork sits above the text box, with
the ported progressing narration (token substitution, dialogue node graph,
choice rows) and a portrait slot beside the text. The panoramic art rail uses
a subdued cover layer as cinematic side fill, then centers the complete 16:9
artwork over it without cropping or distortion. The modal's outer container
uses the authored menu-panel frame and safe content insets. Relic icons use a
dedicated black-iron/bronze socket with violet runes, visually distinct from the
minigame sockets. Choices reuse pygame's dedicated minimal story-choice panel:
normal and disabled rows are dimmed, selection is a thin accent line, and the
icon sits in the panel's authored left socket. Story minigames use the three
canonical socket frames and all 14 authored sigils rather than text initials.
The gameplay sim pauses under the panel like the inventory does. Panel layout
constants are ours; the pygame per-backdrop horizon fractions die with the stage
renderer.

Artwork — generated via PixelLab from the established grim-fantasy style,
curated from recovered candidate batches, and committed self-contained under
`assets/story/` per hard rule 1. `tools/verify_story_assets.py` decodes every
PNG, enforces dimensions and the exact typed key/path inventory, rejects extras,
and verifies SHA-256 in the strict manifest (or updates it after intentional art changes):

| Piece | Count | Format |
|---|---:|---|
| Per-theme omen backdrops | 8 | 640x360 opaque PNG |
| Per-guest-role dialogue backdrops | 10 | 640x360 opaque PNG |
| Per-ending epilogue panels | 15 | 640x360 opaque PNG |
| Lossless Soul backdrop | 1 | 640x360 opaque PNG |
| Per-relic choice icons | 10 | 32x32 RGBA PNG |
| Guest portraits, one per role x name | 30 | 80x90 RGBA PNG |
| Existing panel choice icons | 7 | 32x32 RGBA PNG |
| **Total** | **81** | strict canonical manifest + SHA-256 |

The surrounding self-contained world/UI packs also carry the canonical Quest
and Hall floors and wall faces, four tile-fitting Hall furnishings, three
minigame sockets, and the 14-sigil minigame atlas. Runtime lookup is typed and
falls back to the ordinary dungeon/procedural UI only when an optional texture
cannot load. World relic icons use the same authored 32px sources but render at
20 world pixels so they no longer dominate their floor tile.

Corpus inventory (pygame 5.2.1, audited 2026-08-12): 4 cutscene shells /
7 dialogue nodes; variation axes 5 arcs x 8 factions x 10 relics x
12 dilemmas x 8 motifs x 270 guest combos x 15 endings — art keys off the
axes above, never off literal text variants. Existing pygame art: only
3 shared backdrops + 7 choice icons; zero portraits.

Acceptance: a full 1→10 story run with each archetype reaches a distinct
authored ending driven by recorded choices; every backdrop/portrait/icon key
resolves in a headless manifest test; the story dialog stays readable at
640x480 through 4K; determinism per seed holds with story RNG on its own
derived stream.

**Accepted:** engine/runtime/room/mechanics tests cover all archetypes and 15
endings; the committed manifest test hashes all 81 PNGs; responsive geometry
tests at 640x480, 1280x720, and 3840x2160 enforce complete centered 16:9 art
with intentional side fields, authored outer-frame insets, non-overlapping
choice rows, and readable text. Typed registry tests pin the cutscene panel,
dedicated relic socket, minimal story-choice panel, Quest/Hall surfaces and
furnishings, plus all minigame sockets and sigil atlas regions. A source audit
rejects non-ASCII authored story/UI text so raylib's default font cannot replace
smart quotes, em dashes, ellipses, arrows, or middle dots with stray `?` glyphs.
The production capture matrix covers omen, relic, guest, Soul, and ending panels
at those same resolutions.

#### MX-save — Local save/resume, Chronicle, and persisted game options

Status: **COMPLETE 2026-08-17 (`6.0.0-alpha.20`)**. The former Save/resume +
Chronicle deferred row now has a local filesystem implementation with no
Steamworks dependency. Matti approved the final Chronicle capture matrix. The
three exact primary names, independent revisions/checksums, profile merge,
run-identity conflict rejection, and bounded formats preserve the intended
future Steam Auto-Cloud/configuration seam without coupling gameplay to Steam.

##### Product contract

- Arch Rogue has **one automatically managed active solo-run slot**, not manual
  save slots or reload-any-time snapshots. A valid checkpoint enables `Resume`
  on the title screen. Starting another descent while one exists requires an
  explicit abandon confirmation; an abandoned run is deleted and is not written
  as a completed Chronicle entry.
- Autosave is suspend/resume and crash protection, not a rollback feature. The
  active checkpoint advances throughout play, is removed only after a terminal
  result is durably archived (or after confirmed abandonment), and cannot be
  manually selected from older revisions.
- `Resume` restores the latest committed fixed-tick state, clears held input,
  shows the restored scene frozen behind a short continue veil, and advances no
  simulation or run time during file I/O or while waiting for confirmation.
- Death and victory each finalize exactly once. The finished run is appended to
  the Chronicle and profile first; only after that write succeeds may the active
  run be removed. A crash between those operations must recover idempotently by
  `run_id`, never resurrect a terminal run or duplicate its record.
- The title shell gains `Resume` and `Chronicle`. `Resume` is disabled when no
  valid active run exists. A damaged save is reported plainly and offers backup
  recovery or quarantine/new-run flow rather than silently resetting or
  overwriting it.
- All current game options remain persistent independently of run saves:
  fullscreen, frame-rate cap, view zoom, selected difficulty, controller enable
  and semantic remapping, audio, lighting, mist, and minimap visibility. New
  option fields follow the same default + normalize + migrate contract.

##### Local storage and ownership

Use one stable per-user application-data directory selected by the platform
shell, never the working directory. Choose the final cross-platform directory
name during this milestone and do not rename it when Steam arrives. Keep three
small, independently recoverable UTF-8 JSON documents:

| File | Owns | Future conflict rule |
|---|---|---|
| `options.json` | Player preferences and semantic input mappings. No absolute paths, monitor IDs, controller instance IDs, or dev-environment overrides. | Newest valid revision wins, then normalize for the current machine. |
| `profile.json` | Durable account-local progress (`hell_unlocked` now, future meta), lifetime summary counters, and Chronicle records. | Merge unlocks monotonically and union Chronicle records by `run_id`; counters must be merge-safe or derivable, never blindly summed. |
| `run.json` | The single active solo-run checkpoint and terminal-finalization marker. | Same `run_id`: highest valid revision wins. Different active `run_id`s require a future explicit cloud-conflict choice; never auto-delete one. |

The existing Odin `options.json` is migrated in place without losing values.
`hell_unlocked` moves from the options domain into `profile.json`; when no
profile exists, import that field from the current options schema once. A
malformed file in one domain must not poison the other two.

Every primary document has an explicit envelope with `schema_version`, game
release, document/run identity, monotonic revision, UTC write time, and a payload
hash/checksum. Persist stable string content IDs rather than Odin enum ordinals,
raw pointers, array memory, localized prose, or platform paths. Reject non-finite
numbers and enforce file, collection, and string length bounds before allocating.
Checksums detect corruption, not cheating; save encryption and tamper prevention
are non-goals.

Writes use same-directory `*.tmp` + flush/sync + atomic replace where the OS
supports it, retaining one last-known-good `*.bak`. On startup, validate the
primary, interrupted temp, and backup and promote only the highest valid
revision. Invalid files are renamed to timestamped `*.corrupt-*` only after a
valid recovery or explicit player action. Temp, backup, and quarantine files are
local recovery artifacts and must be excluded from future cloud patterns.

This three-primary-file layout fits the Steam plan's currently documented
10-file / 10-MB per-user Auto-Cloud budget. Later Steam configuration should
sync only the three exact primary names, never `*.json`; Steam APIs, upload UI,
and live remote conflict resolution are outside MX-save. If genuinely
machine-specific preferences are added later, they belong in an explicitly
unsynced device document rather than making `options.json` non-portable.

##### Active-run save model

Define explicit save DTOs and conversion functions; do not marshal the live
`App`/`Run` structs wholesale. Capture on a fixed-tick boundary into owned data,
validate/encode away from the live sim, and restore into a temporary run before
atomically swapping it into `App`. A failed restore must leave the title state
and existing files intact.

Persist every value that can affect the continuation:

- run identity, seed, revision, difficulty snapshot, active elapsed time, depth,
  complete floor plan/modifier, derived RNG stream states/counters, floor epoch,
  and all run-wide reward/interactable/Bar/challenge ledgers;
- current dungeon geometry and mutable tile/door/seal state, theme/darkness,
  special-room state, explored fog memory (live visibility is recomputed),
  static fixtures, and deterministic shop inventory/prices;
- complete player gameplay state: position/facing, archetype, HP/mana/stamina,
  XP/level/tokens/disciplines, inventory/equipment/consumables/gold, statuses,
  action resources, cooldowns, charge/skill state, and gameplay-affecting timers;
- enemies, bosses, familiars, guests/allies, ground items, traps, shrines,
  secrets, bells, and in-flight projectiles with stable IDs, positions, health,
  committed actions, cooldown/status/AI state, ownership, and remaining lifetime;
- story engine/runtime state, choices/flags/relics/ending path, active story panel
  or minigame (including once-only reward guards), and guidance state;
- Chronicle-facing run facts as they accumulate: kills, defeated bosses,
  notable loot, causes/damage source, floors, traps, shrines, secrets, Bars,
  challenge rooms, and any future summary statistic exposed to the player.

Do **not** persist renderer caches, GPU/audio handles, draw lists, nav fields,
live LOS masks, queued SFX, damage numbers, transient feel particles/lights,
hover/scroll state, held input, or other reconstructible presentation data.
Rebuild those after validation. Gameplay-affecting projectiles, statuses,
committed attacks, and cooldowns are not presentation and must survive so reload
cannot cancel danger or duplicate rewards.

Any simulation advance marks the active run dirty. Routine writes use one
coalescing worker: checkpoint after 1.5 seconds of quiet but never postpone the
first dirty revision beyond 6 seconds. The worker receives an owned snapshot and
never reads live arrays; at most one write is active and newer pending revisions
supersede older pending work. Immediate durable boundaries are:

- a new run after its first floor/story setup is complete;
- a completed floor transition;
- story choices, relic/Soul/minigame resolution, shop transactions, discipline
  purchases, unique/boss/miniboss rewards, and other irreversible decisions;
- pause-menu `Save & Return to Title`, application close, and supported platform
  suspend/lifecycle events;
- terminal death/victory finalization.

Routine autosaves must not create visible frame hitches. Critical exit/finalize
paths may wait for the current write, but must show progress and expose Retry,
Cancel, or `Exit without saving` after a failure instead of claiming success.
Failed background saves remain dirty and retry with backoff. Time spent paused,
loading, suspended, or outside the process never advances active run time.

##### Chronicle data and retention

Carry over only the pygame feature's **basic idea**: a title-accessible,
newest-first history of finished descents with a selected run's details. Do not
port its generic menu-row list, parchment-note layout, dimensions, typography,
or visual hierarchy.

Each immutable record has a record-schema version and bounded data: unique
`run_id`; victory/death outcome; archetype and difficulty IDs; seed; deepest
floor; start/end UTC timestamps plus active duration; final level; kills and
other run counters; run modifier and visited theme IDs; defeated boss IDs;
notable item IDs with a short display-name fallback; cause-of-death source;
and story arc/faction/relic/ending IDs needed to retell that descent. Store
semantic IDs and facts, then render current localized labels; do not embed long
pre-rendered narrative blobs.

The pygame limit of twelve records was a rolling history/UI choice, **not a
Steam Cloud technical limit**. Odin keeps up to **512 completed descents** while
bounding each record and keeping `profile.json` at or below 10 MiB. On overflow,
prune the oldest complete records only after the newest is durable; lifetime
profile totals remain authoritative beyond the retained window. Filters and the
renderer operate on a virtualized/windowed view, so retention is not constrained
by how many rows fit on screen.

##### Chronicle presentation — intentional visual upgrade

Build a new authored grim-fantasy ledger, consistent with the Odin title/HUD art:

- A wide layout uses a master/detail composition: a scrollable descent timeline
  of substantial run cards on the left and a selected-run memorial panel on the
  right. Compact windows stack the same cards and detail view instead of scaling
  tiny text.
- A summary band shows lifetime descents, victories, best depth, total kills, and
  discovered endings. It reads from profile totals, not only the retained 512.
- Each card uses an archetype portrait/medallion, unmistakable victory or fallen
  treatment, difficulty badge, ten-step depth trail, end date, and duration.
  Selection must remain clear without relying on hover or color alone.
- The detail panel uses real boss/relic/item iconography where available and
  groups the run into outcome/story, build, encounters, discoveries, and final
  statistics. Cause of death and ending are prominent; raw IDs never leak into
  UI when an old content key is missing.
- Provide `All`, `Victories`, and `Fallen` filters plus archetype/difficulty
  filtering, newest-first ordering, page/scroll navigation, and direct
  keyboard, mouse, and controller support. Back always returns to title.
- The empty state is a deliberately illustrated unwritten ledger, not a blank
  list. Corrupt/migrated records degrade to partial cards with `Unknown` fields
  rather than crashing the whole screen.
- Reuse suitable canonical Odin assets and generate any new ledger frame,
  sigils, sockets, or dividers through PixelLab under `assets/ui/`. Validate the
  result with an exact asset manifest and captures at 640x480, 1280x720,
  Steam-Deck-shaped 1280x800, and 4K. Matti's visual signoff is required; passing
  geometry tests alone cannot establish that this is better than pygame.
- Generate new Pixellab freely whenever needed, we have lots of budget now!

##### Architecture and migration seams

- Add one justified raylib-free persistence subsystem (expected
  `persistence.odin`) for DTOs, schema migrations, validation, checksums, profile
  operations, Chronicle queries, and run snapshot/restore conversion.
  `options.odin` continues to own option values/defaults/normalization.
- `main.odin` remains the platform boundary for per-OS paths, the single save
  worker, filesystem durability, startup recovery, and future storage-backend
  selection. `ui.odin` renders Chronicle/title/recovery states but never parses
  files. Simulation code emits typed dirty/critical-save events and never calls
  Steam or raylib.
- Migrate schemas one version at a time with committed fixtures. Missing additive
  fields receive explicit defaults; renamed stable IDs use reviewed maps;
  unknown optional content degrades safely; missing/invalid critical gameplay
  references reject the active run. A future-schema file is preserved and
  reported as newer/incompatible, never rewritten with defaults.
- Pygame run-save import, manual/multiple save slots, multiplayer run saves,
  replay/rollback, Steamworks calls, achievements, and cloud-conflict UI are
  explicit non-goals. Pygame Chronicle records may be considered later only as
  a separate one-way profile import; MX-save does not depend on the Python tree.

##### Verification and acceptance

- Headless round-trip fixtures cover every persisted family above. A stronger
  continuation test checkpoints a busy deterministic run, clones it through
  decode/restore, feeds both branches the same input for hundreds of fixed ticks,
  and compares canonical gameplay state and subsequent RNG outcomes.
- Tests interrupt writes before/after temp flush and replacement; corrupt,
  truncate, oversize, and future-version each document independently; exercise
  primary/temp/backup selection; and prove a failed load never partially mutates
  `App` or destroys recoverable bytes.
- Lifecycle tests prove title Resume gating, abandon confirmation, critical
  save-and-return/quit behavior, no offline time advance, terminal
  finalization/deletion ordering, and exactly-one Chronicle record after crashes
  at every point in that transaction.
- Options tests retain the current round trip, cover migration from today's
  schema (including `hell_unlocked`), preserve defaults for new fields, and prove
  command-line/dev overrides are never serialized.
- Chronicle tests cover both outcomes and all archetypes/difficulties, old and
  partial records, ID fallback, filters/input, 512-record retention, 2-MiB budget,
  merge/deduplication by `run_id`, lifetime totals after pruning, and responsive
  geometry. A capture matrix owns perceptual signoff of the new visual design.
- Profiling under a dirty, crowded floor shows routine snapshots/writes do not
  break the stable 60+ FPS target. Check/test/release builds remain `-vet` clean.
- A final cloud-readiness audit demonstrates that the three primary files are
  path-free, cross-OS JSON, remain under the documented 10-MB/10-file budget,
  expose revisions and conflict summaries, and can be selected by exact
  Auto-Cloud patterns. No Steam client is required to accept MX-save.

Acceptance: kill the process during a deep, story-active combat floor and resume
from the last durable checkpoint without duplicated rewards, cancelled danger,
or deterministic drift; finish by death and victory and receive exactly one rich
Chronicle card each; restart the game and retain every supported option. The
Chronicle is visibly a new Odin-quality screen rather than a pygame layout port,
and enabling Steam Cloud later requires configuration/backend work, not a format
or lifecycle redesign.

**Implemented and verified in alpha.20:** one active-run slot, Resume/veil,
explicit abandon, close/pause save boundaries, isolated options/profile/run
recovery, semantic options + Hell migration, process-heap-owned fixed-tick
snapshots, worker-side validation/JSON/hash/write, per-domain queue coalescing,
exactly-once terminal recovery at all four commit boundaries, 512-record
Chronicle retention, profile merge/deduplication, and responsive Chronicle/
recovery UI are live. Thirty-two MX-save regressions bring the full suite to
333 and cover continuation determinism, interrupted writes, independent
corruption, split-brain run identities, backup resurrection prevention, profile
budgeting, all three worker domains, nonblocking explicit exits, second-launch
storage initialization, relaunch-time discard without Resume, layout/input, and
exact asset hashes.
`verify_chronicle_assets.py`, Linux check/test/release, and Windows cross-check
pass. The regenerated matrix contains 24 exact-size captures across empty,
populated, victory, fallen, recovery, and abandon states at 640x480, 1280x720,
1280x800, and 3840x2160. On an AMD Radeon 880M, the three-run release save
profile measured median frame p95 2.689 ms, mean 743.25 fps, ten routine
snapshots per run, 0.053 ms mean snapshot capture, and 0.061 ms worst snapshot,
with lighting/effect/mist resources active and a valid recovered run after each
pass. Matti approved the final edge-to-edge Chronicle ledger composition and its
frame-safe content layout after reviewing the regenerated capture matrix.

#### MX-android — Native Odin Android build, lifecycle, and touch playability

Status: **COMPLETE at `6.0.0-alpha.21`**. Android now ships as a self-contained
native Odin + raylib build at native display resolution. The real asset pack,
GLES2 rendering, authored audio, app-private MX-save path, lifecycle reduction,
semantic Back handling, and multi-touch input all use the same game and
simulation contracts as desktop.

##### Delivered platform facts

- Android is pinned to `compileSdk 35` / `targetSdk 35`, `minSdk 28`, build-tools
  35.0.0, and NDK r28c. Debug and release retain their isolated alpha IDs:
  `org.archrogue.archrogue.odin.alpha.debug` and
  `org.archrogue.archrogue.odin.alpha`.
- APKs contain exactly `arm64-v8a`, `armeabi-v7a`, and `x86_64`, in that order.
  Every ABI uses the same Odin LLVM IR → pinned Clang → NDK deferred-entry link
  rather than Odin's direct Android shared-library link.
- The checked-in raylib 6.0 Android archives are static PIC OpenGL ES 2.0 builds
  for all three ABIs. The complete canonical asset/audio tree is packaged and
  read through Android asset APIs.
- A custom Java `NativeActivity` owns only class-loader native-library loading
  and Android Back callbacks. Gameplay, rendering policy, lifecycle semantics,
  persistence, and the sole game loop remain Odin/raylib.

##### Product and packaging contract

- Android uses `NativeActivity` with raylib's native app glue and one custom Java
  activity for class-loader loading and Back dispatch. It does not introduce a
  second game loop or an SDL/Python compatibility layer.
- The Android project, manifest, launcher resources, licenses, build metadata,
  and scripts live in root `android/` and `tools/`. Ordinary builds use pinned
  local toolchains/caches, stage the canonical root `assets/` tree, never copy
  from `arch-rogue-python/`, and do not download unpinned game dependencies.
- Source pins Gradle/AGP, JDK 17, `compileSdk 35`, `targetSdk 35`, `minSdk 28`,
  build-tools 35.0.0, NDK r28c, Odin, Clang, raylib, and archive checksums.
  Preflight prints the exact missing `sdkmanager` package IDs.
- The exact packaged ABI order is `arm64-v8a`, `armeabi-v7a`, `x86_64`; each has
  its own checksum-verified raylib GLES2 archive and passes the same strict APK
  audit. Normal builds cannot select the Linux/X11 archive.
- The complete canonical `assets/` tree and Android-distribution license copies
  are packaged without flattening, and the final auditor compares every asset
  byte-for-byte while rejecting stale, extra, duplicated, or symlink-derived
  entries.
- `./build.sh android-preflight`, `android-debug`, `android-release`,
  `android-install`, `android-audit`, and `android-smoke` form the validated
  command surface. Builds clean generated handoffs, derive `versionName`, enforce
  the committed monotonic `versionCode`, and audit the artifact rather than
  trusting Gradle's exit status.
- The debug and release IDs remain `org.archrogue.archrogue.odin.alpha.debug` and
  `org.archrogue.archrogue.odin.alpha`, preserving coexistence with the archived
  legacy app package and keeping each app-private save namespace isolated. Reusing the
  official unsuffixed identity remains a separate migration/signing decision.

##### Android platform seams

- `ArchRogueActivity` loads `libmain.so` through its class loader with
  `System.loadLibrary`, registers `OnBackInvokedCallback` on API 33+, and keeps
  legacy `onBackPressed()`. Both callbacks cross JNI and reduce to the shared
  semantic `.back` intent.
- Every ABI emits Android-targeted Odin LLVM IR, compiles it with pinned Clang,
  then uses the matching NDK driver/native-app glue for deferred entry. raylib's
  `android_main` invokes game `main()` only after `NativeActivity` initialization.
- Strict native and APK audits reject eager `DT_INIT`, retained desktop TLS,
  GLIBC/X11/pthread or other host contamination, unexpected dependencies,
  missing packaged activity/DEX markers, and missing JNI Back symbols.
- The shared packaged-resource layer reads manifests, textures, shaders, and
  audio from Android assets while preserving desktop/headless file behavior and
  common manifest validation.
- Android selects the GLES2 shader/render path, native physical resolution,
  point-filtered actor assets, authored audio, and resource rebuilds across
  lifecycle transitions. Desktop GLSL/window behavior remains unchanged.
- Saves use Android app-private internal storage with the existing MX-save
  schemas, revisions, backup/temp replacement, recovery, and snapshot worker;
  no external-storage permission or working-directory path is involved.
- A local portable SHA-256 implementation replaces `core:crypto/sha2`, preserves
  the save format, passes FIPS test vectors, and avoids ARMv8-only assumptions
  on the ARMv7 baseline. The ARMv7 linker localizes pinned Odin `__fixunsdfdi`
  before resolving the NDK compiler-rt archive.
- Startup and lifecycle diagnostics report concise version, ABI, API, native
  dimensions, GLES, asset, storage, audio, and transition facts to logcat.

##### Native-resolution mobile presentation and touch

- Android renders the physical landscape surface at native resolution; the
  Pygame low-resolution streaming path is not revived, and sight/light behavior
  is unchanged.
- Mobile layout and hitboxes share safe-area/inset geometry. The world remains
  edge-to-edge while controls and overlays stay in the unobstructed region.
- Real touch IDs receive stable roles so movement, aim, held actions, and another
  action can coexist. Release, cancellation, modal changes, focus loss, and
  suspension clear ownership without emitting unrelated actions.
- When touch targets overlap, direct activation chooses the candidate whose
  center is nearest the contact instead of depending on iteration order;
  disabled visual rows remain inert blockers. Zero-contact raylib touch-as-mouse
  pass-through is suppressed, eliminating
  phantom menu taps after gestures.
- Android Back, virtual controls, world aim, pinch zoom, actions, interactions,
  inventory, character, story choices, and pause all reduce to the same
  raylib-free intent semantics as keyboard/controller input; Back is `.back`.
- The current single-player shell still has no editable field. Soft-keyboard/IME
  acceptance remains paired with the first real shipping text-entry surface
  rather than adding a fake screen.

##### Lifecycle, persistence, and audio contract

- Pause/background cancels touches, freezes fixed-step simulation and active
  time, pauses audio, and requests a bounded critical checkpoint for a live run.
- Resume discards stale frame time, refreshes mobile geometry, restores graphics
  and audio resources as needed, and returns through the paused/continue veil;
  it does not auto-advance or auto-attack.
- Force-stop/relaunch uses the app-private durable checkpoint and existing
  exactly-once run/Chronicle rules. Repeated lifecycle transitions preserve
  authoritative simulation while reconstructible render/audio resources are
  rebuilt at the platform edge.

##### Verification and acceptance

- `odin check src -vet` passes, and `odin test tests -vet` passes all 357
  deterministic tests, including mobile touch, Back, lifecycle, and persistence
  coverage.
- The final APK strict audit passes with target API 35, minimum API 28, and the
  exact ordered ABI set `arm64-v8a`, `armeabi-v7a`, `x86_64`. It rejects
  `DT_INIT`, host contamination, missing packaged activity/DEX or JNI Back
  symbols, bad dependencies, stale assets, and signing/package/version mismatches.
- Rebuilding the pinned raylib Android archives reproduces the committed
  checksums exactly.
- The API-34 x86_64 AVD smoke passes Options entry, disabled-row non-mutation,
  an edge-gesture Back, gameplay, multi-touch, background/foreground lifecycle,
  resume, packaged assets/audio, and app-private
  save recovery. A forced ARM64-translation run also starts and passes
  Options/Back.
- Matti previously confirmed that an earlier ARM64 APK starts on a physical
  device. The alpha.21 Options/gesture fixes still need physical retesting; no
  physical confirmation is claimed for those fixes.
- ARMv7 compiles, packages, and passes the strict audit, but runtime testing was
  not possible because the current AVD exposes no 32-bit ABI. This limitation is
  recorded rather than presented as a runtime pass.

Automated MX-android acceptance is complete at alpha.21: the real game boots and
plays through the native GLES2/assets/audio path, touch and Back reach semantic
intents, lifecycle/resume preserve app-private state, desktop checks remain
clean, and no build/run path reaches into `arch-rogue-python/` or another
parallel source tree. Physical retesting of the alpha.21 Options/gesture fixes
and an eventual ARMv7-capable runtime remain
explicit follow-up validation, not claimed results.

Explicit non-goals for MX-android remain Play Store publishing/rollout, billing,
multiplayer/network permissions, Steam/achievements/cloud, updater behavior,
iOS, and inventing a soft-keyboard screen before a real text-entry feature
exists.



## Working agreements for the parity push

- `assets/` is the sole canonical art tree (hard rule 1). Tools may verify,
  capture, or profile assets, but do not maintain parallel source/copy pipelines.
  Keep runtime manifests only where they carry canonical data; static UI metadata
  belongs in typed Odin definitions and headless file-contract tests.
- Any pygame number that looks "off by ~5x" is the WORLD_SCALE trap.
- Sim stays raylib-free and deterministic; anything that would break
  same-seed replay is a design bug (MP re-entry depends on it).
- Ask Matti before: dropping/changing any player-visible behavior, art
  regeneration (vs bake), wire/save formats, and anything touching the
  pygame tree beyond reading.
