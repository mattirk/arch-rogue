# Arch Rogue — Story Reference (abridged)

Canon-in-brief for anyone touching story-related mechanics. The full working bible
lives in `build/story/` (gitignored); this file is the committed summary of what
shipped in 4.9. When they disagree, the code and this file win.

## The myth

Beneath the drowned city of **Kasar Voss** stands the **Last Gate** — the door where
unfinished things go to end: unkept oaths, unpaid debts, deaths nobody witnessed,
names never said aloud. The city grew rich feeding its regrets through the Gate,
until the Ledger named its own Toll-Keeper, **Sorn Voss**, and he refused to pass.
He barred the Gate from the inside; the backed-up Unfinished swallowed the city in a
night. The dungeon is ten floors of everything that cannot end, kept by a man who
will not die — the **Dread Gate Tyrant**. The player is nameless, and maybe an ending.

**Pillars**
1. *Everything below is unfinished.* Monsters are defaulted debts; relics are sealed
   unfinished things; bosses are **the Stalled** — city officials frozen mid-office.
2. *Names have weight.* Speaking a true name spends something. All five archetypes
   have lost theirs (sold, erased, inherited, spent, stripped) — that's why the
   Ledger can't bill them and they alone can descend.
3. *The stage frame.* Cutscenes are literally staged: the Scriptorium of Worms
   records each run, and **Nim Rue** narrates as she writes. Her rationed ink is the
   diegetic reason story text is budgeted.
4. *Three verbs.* Aid / Bargain / Defy on every beat; Forsake by walking past.
   The final choice at the Gate is the same three verbs at world scale.

**Hard don'ts:** never explain the far side of the Gate; never give the fall of Voss
a definitive account; no NPC says "quest/level/run" except Rue (ledger words:
*entry, page, margin*); one metaphor per line; named characters don't resurrect
casually.

## Cast (all mapped to existing systems)

| Character | Is | Mechanical home |
|---|---|---|
| **Sorn Voss** | the Toll-Keeper → Dread Gate Tyrant; refused to let his daughter's death pass | final boss; speaks through the D8 guest; his true name is a weapon |
| **Nim Rue** | frightened Scriptorium scribe; the narrator | `narrator` speaker in all cutscenes; cross-run greeting from `meta_progress`; death/victory closing lines; Arcanist tether |
| **Mother Hush** | grave-witch, sanctuary keeper | Grave-Witch guest template |
| **Coin-Eye Pell** | Mortuary Guild factor; brokered the Rogue's sale | Mortuary Broker template; canonically every shopkeeper's boss (shop patter lines); Rogue tether |
| **Ser Caldus** | the pilgrim the Warden let through; wants a witness to his last vow | Oathless Knight template; Warden tether |
| **The Blue-Lipped Child** | the plague's only death; lived in the Acolyte's bell tower | Drowned Heir template; Acolyte tether |
| **Sable of the Moon-Hunt** (+ the White Stag) | hunt-sister with two writs she won't serve; the Stag carries the Ranger's captain | Antlered Hunter template; Ranger tether |
| **Liss Voss** | the Lossless Soul — Sorn's daughter, the death he refused | existing Hall of Unlost Echoes NPC; source of `name:liss` |

**The Stalled** (floor bosses, each dies with a last word — `BOSS_LAST_WORDS`):
Ash Gallows Knight (executioner, mirrors the Rogue) · Mycelial Matron (plague-ward
midwife, mirrors the Acolyte) · Rime Chanter of the Ninth Bell (bell-warden, mirrors
the Arcanist) · Voidbound Rune Sentinel (guardian of an empty vault, mirrors the
Warden; doesn't speak). The Ranger's mirror is the Stag — deliberately not a boss.

**Factions:** eight theories about the far side; one antagonist + one rival rolled
per run (`STORY_FACTIONS`, orbit weighting in `FACTION_ORBITS`). The Scriptorium
(narration) and Mortuary Guild (shops) are standing infrastructure.

## Archetype throughlines (`STORY_ARCS`, `STORY_TETHERS`)

Each archetype has one canonical life (the three legacy backstory rolls are its
chapters — the roll only picks the run's title flavor), a fixed wound/oath/secret,
a tether NPC at depths 1/5/9, and three endings.

| Archetype | Wound (shown at select + D1) | Tether | Endings (aid / bargain / defy) |
|---|---|---|---|
| Warden | opened one door in mercy; a city paid | Ser Caldus | Held Door / Fair Scale / No More Doors |
| Rogue | sold before birth; even their death has an owner | Coin-Eye Pell | Emptied Market / Honest Purchase / Standing Debt |
| Arcanist | proved the last seal can dream itself open | Nim Rue | Answered Proof / Restored Name / Standing Argument |
| Acolyte | bell rang a day early; the plague's one death unburied | the Child | True Funeral / Returned Confession / Broken Bell |
| Ranger | captain vanished into the beast the law says to kill | Sable | Hunt Without Arrows / Next White Thing / Old Way |

The **secret** never renders before depth 5 (it's logged on the D5 resolve).

## Run structure (depths ↔ beats)

Bosses at depths **3 / 6 / 9**, final at **10** (`run_flow.py`). Tether floors are
**1 / 5 / 9** (guest roll overridden in `StoryEngine.generate`). Pinned dilemmas:
D5 *The Door That Remembers*, D8 *The Gate's Confession* (the Tyrant's per-archetype
offer, `TYRANT_OFFERS`), D9 *The Last Guest's Mask* (tether crisis with authored
verb text). Other floors roll from the remaining nine dilemmas.

- **D1** — meet the tether; omen opens with Rue's greeting (no prologue screen —
  removed as too much text before play).
- **D5** — the wound staged; tether reveal; secret surfaces.
- **D7+** — Hall of Unlost Echoes guaranteed if the 50% roll never landed
  (`Dungeon(force_soul_hall=…)`, `:hall` story flag).
- **D8** — the smaller ending offered; refusing with Defy (or the Acolyte's Aid)
  teaches `name:sorn`.
- **D9** — tether crisis (`crisis:{verb}` flag).
- **D10** — the Gathering (every Aid-resolved guest stands at the door;
  `spawn_gate_gathering`), the Tyrant, then the **Tenth Bell** epilogue: gate verb →
  one of 15 endings → `complete_victory`.

## Choice model (all existing wiring)

- **Verbs** (per beat, unchanged mechanics): Aid = heal/secrets/shrine, Bargain =
  HP price/rare gear, Defy = XP/hunter; unanswered = forsaken penalty.
- **Roads** (`story_road`, derived from beats at act breaks 3/6/9 — no save state):
  witness / debtor / defiant / forsaken / unwritten. Text-level only: omen road
  clause (`STORY_ROAD_LINES`), Rue's death line (`RUE_DEATH_LINES`), ending codas.
- **Endings** = archetype × gate verb (`STORY_ENDINGS`), shaded by road coda,
  crisis echo (`STORY_CRISIS_ECHOES`), and Liss's line on aid. *The last choice
  decides; history flavors — endings are never locked.*
- **Name economy:** `learn_story_name` — flag + one story-log line blanks to "———"
  (the visible memory cost). `name:sorn`: nameplate becomes "Sorn Voss, …", boss
  spawns at 0.88× HP, engage floater. `name:liss` (Hall, D7+, preserve/release
  only): 0.94× HP, hesitation floater, extra ending line on aid.
- **Cross-run memory:** `meta_progress["story"]["endings"]` (+ `runs_started` /
  `clears`) drive Rue's D1 greeting variants.

## Active interludes (4.9.1 mini-games)

Story choices remain the authored Aid / Bargain / Defy decisions above. At the
three later turning points (depths 5 / 8 / 9), selecting the opening relic path
first starts **Bind the Page**: Rue shows a short sequence of seal runes and the
party repeats it. Depth 1 stays focused on onboarding, and ordinary floors keep
the direct choice flow so the interlude does not become a ten-floor tollbooth.
A win fully restores party HP and permanently adds 1 damage for the run.

Two refuge rooms add their own once-per-room interludes:

- **Wake the Moonbloom** — talk to either dancing frog in the Garden, then
  touch the lit seal before it folds shut. A successful tending permanently
  adds 5 maximum HP and mana to the party for the run; failure simply withholds
  the bonus, then play resumes.
- **Mirror the Unlost** — match the Lossless Soul's paired seals before her
  existing Preserve / Release / Refuse audience. The audience always continues;
  a win permanently adds 5 maximum mana and 1 spell damage to the party for
  the run, never a locked dialogue answer.

All three use the same `menu.glyph.sigil.*` art as multiplayer code seals. They
accept touch, mouse, keyboard, and controller input through one rendered cell
grid. An untimed guide explains the game first; Interact / **E**, its remapped
joypad equivalent, or the visible touch/click target sets the player's ready
mark. Both descenders must confirm in co-op before the preview and timer begin.
The play windows are **7.5 seconds** for Bind the Page, **9 seconds** for Wake
the Moonbloom, and **12 seconds** for Mirror the Unlost. In co-op the host owns
the deterministic state and either player may complete the next step;
revision-stamped presses make simultaneous or delayed inputs harmless instead
of penalizing latency. Active state is an additive schema-5 save field, while
completed Garden/Soul outcomes live in the hosting `SpecialRoom.state` to
prevent reward farming.

## Text budgets (enforced by `tests/test_story_budgets.py`)

Narration renders at 22 px with 1 px letter tracking (~70 chars/line); choice
labels at 19 px (`choice_font`), details at 16 px, text block vertically centered.
The narrator card guarantees 4 lines (usually 5); completed narration tail-follows
so the final (reveal) sentence stays visible.

| String | Budget |
|---|---|
| choice-node text / omen body | ≤ 345 (omen assembled drop-from-end) |
| dilemma setup / truth | ≤ 90 / ≤ 110 (truth required — the plain-spoken reveal) |
| guest speech / tether speech / Tyrant offer | ≤ 160 / ≤ 180 / ≤ 180 |
| choice label / detail | ≤ 34 / ≤ 92 |
| verb intent / outcome | ≤ 40 / ≤ 70 |
| wound / oath / secret | ≤ 90 / ≤ 80 / ≤ 90 |
| objective | ≤ 110 |
| interaction-prompt hint | ≤ 48 |
| boss last words / floaters | ≤ 30 / ≤ 45 |

Style: present tense, one image per sentence, speech is quoted speech, no recaps of
what the HUD/panel already shows, the best word in the last five.

## Where things live (attach points)

| What | Where |
|---|---|
| All story content tables | `content/story_corpus.py` (structures in `content/definitions.py`) |
| Run composition, roads, pinned/tether logic | `story/engine.py` |
| Cutscene runtime, omen assembly, names, epilogue, gathering | `story/runtime.py` |
| Cutscene node graphs (4: omen, dialogue, soul, epilogue) | `assets/quest_cutscenes.json` |
| Victory flow (`finish_final_descent` → epilogue → `complete_story_victory`) | `run_flow.py` |
| Boss last words | `combat/damage.py`; name HP effects in `population.py` |
| Overlay rendering (fonts, tracking, choice rows, page glyph) | `rendering/story_overlays.py` |
| Mini-game state machines / intent codec | `story/minigames.py` |
| Mini-game full-screen board | `rendering/minigames.py` |
| Cross-run story slot | `options.py` (`meta_progress["story"]`) |
| Budget + structure CI | `tests/test_story_budgets.py` |

**Deliberately unchanged by 4.9:** verb mechanics/effect channels, procedural
variety on non-tether floors, the save format (roads are derived), the Q-panel
information contract.
