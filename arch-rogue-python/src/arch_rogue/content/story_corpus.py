# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
#
# AI Provenance & Liability Notice:
# This repository contains code generated, assisted, or refactored by Artificial
# Intelligence models. Provided strictly "AS IS" under Apache 2.0 with no warranty
# of clean IP provenance or non-infringement; downstream users assume all legal
# and financial risk and should perform their own compliance audits.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Story corpus (4.9 "Story that makes some sense").

Canon in one breath: the dungeon is the sunken city Kasar Voss, stacked on the
Last Gate — the door where unfinished things go to end. The Dread Gate Tyrant
is Sorn Voss, the Toll-Keeper who refused to let anything end. The narrator is
Nim Rue, a Scriptorium scribe writing each run as a rationed ledger entry —
the diegetic reason every string in this file is short. Budgets are law (see
build/story/50-cutscene-style.md and tests/test_story_budgets.py): a cutscene
choice node shows ~4 lines (~300 chars at the 22 px narration font), choice
labels cap at 34 chars, details at 92. Guest speeches run to two sentences
(<=160; tether beats <=180) and each dilemma carries a plain-spoken ``truth``
sentence (<=110) — revealing, but still rationed.
"""

from __future__ import annotations

from .definitions import (
    StoryArc,
    StoryBackstory,
    StoryCrisisChoice,
    StoryDilemmaTemplate,
    StoryEnding,
    StoryFaction,
    StoryGuestTemplate,
    StoryLocationMotif,
    StoryRelic,
    StoryTether,
    StoryTetherBeat,
)


# ---------------------------------------------------------------------------
# Archetype arcs — one canonical life per archetype. The three legacy
# backstory rolls are chapters of the same story; the roll only picks which
# chapter title colors the run's story title.
# ---------------------------------------------------------------------------

STORY_ARCS: dict[str, StoryArc] = {
    "Warden": StoryArc(
        wound="You opened one door out of mercy, and a city paid the toll.",
        oath="Guard the living from bargains made at sealed doors.",
        secret="The pilgrim wore your family's signet; the door opened for your name, not your mercy.",
        chapters=(
            "Last Shield of Kasar Voss",
            "Iron Oath Exile",
            "Gravewatch Captain",
        ),
    ),
    "Rogue": StoryArc(
        wound="You were sold before you were born; even your death has an owner.",
        oath="Steal back what was never theirs to sell.",
        secret="The deed is written in your blood, dated before your birth. The buyer waits below.",
        chapters=(
            "Blackroof Orphan",
            "Knife of the Lantern Court",
            "Grinning Gallowsblade",
        ),
    ),
    "Arcanist": StoryArc(
        wound="You proved the last seal could dream itself open, and it will not stop being true.",
        oath="Write the counter-sigil before the proof completes itself.",
        secret="You are the last complete copy. Unwriting the proof unwrites you.",
        chapters=(
            "Scholar of the Ninth Seal",
            "Star-Ash Savant",
            "Runebound Fugitive",
        ),
    ),
    "Acolyte": StoryArc(
        wound="Your bell rang a day early, and the plague's only death is a child no one buried.",
        oath="Finish the Child's death right: name said, grief kept, one bell rung true.",
        secret="The bell tolls softly when you lie — and one sin in your blood knows the Tyrant's name.",
        chapters=(
            "Bell-Keeper of Saint Mire",
            "Ashen Confessor",
            "Gravetongue Novice",
        ),
    ),
    "Ranger": StoryArc(
        wound="Your captain vanished into a beast the law says you must kill.",
        oath="Finish the hunt without the kill the clan demands.",
        secret="The compass points at your heartbeat. The Stag is not fleeing you — it follows.",
        chapters=(
            "Thornroad Outrider",
            "Moon-Hunt Exile",
            "Wildermark Cartographer",
        ),
    ),
}

# Legacy shape, kept for engine/save/test compatibility: three entries per
# archetype, canonical wound/oath/secret repeated under each chapter title.
STORY_BACKSTORIES: dict[str, tuple[StoryBackstory, ...]] = {
    name: tuple(
        StoryBackstory(chapter, arc.wound, arc.oath, arc.secret)
        for chapter in arc.chapters
    )
    for name, arc in STORY_ARCS.items()
}


# ---------------------------------------------------------------------------
# Factions — eight theories about the far side of the Gate. The Scriptorium
# and the Mortuary Guild are infrastructure (narrator, shops); the rest rotate
# as antagonist-of-record per run.
# ---------------------------------------------------------------------------

STORY_FACTIONS = (
    StoryFaction(
        "Choir of the Hollow Star",
        "starless chanters",
        "sing the Last Gate open and pay the toll in names",
        "they cannot speak a true name without losing a memory",
        (160, 86, 230),
    ),
    StoryFaction(
        "Ember Monks of Khar",
        "ash-scarred ascetics",
        "burn souls clean enough to cross, one guilt at a time",
        "water blessed by moonlight burns them like acid",
        (245, 104, 52),
    ),
    StoryFaction(
        "Drowned Lineage",
        "blue-lipped heirs",
        "flood every oath until the water rises home",
        "they must answer any question asked beside still water",
        (86, 188, 215),
    ),
    StoryFaction(
        "Thorn Brides of Edda",
        "root-veiled witches",
        "wed their bloodline to the Gate and inherit the door",
        "iron wedding rings silence their glamour",
        (126, 214, 92),
    ),
    StoryFaction(
        "Voss Mortuary Guild",
        "coin-eyed undertakers",
        "own every death in the city before it finishes",
        "they cannot refuse a properly witnessed debt",
        (190, 130, 215),
    ),
    StoryFaction(
        "Order of the Black Pulley",
        "engine-priests",
        "raise the sunken city back to heaven, chain by chain",
        "their machines stall when fed unmarked bones",
        (245, 132, 72),
    ),
    StoryFaction(
        "Pale Antler Court",
        "moon-crowned hunters",
        "hunt every soul that slipped the Toll-Keeper's count",
        "they cannot cross a threshold swept with grave salt",
        (145, 184, 232),
    ),
    StoryFaction(
        "Scriptorium of Worms",
        "carrion archivists",
        "write every possible ending before one can happen",
        "fresh ink binds them more tightly than chains",
        (144, 172, 86),
    ),
)

STORY_RELICS = (
    StoryRelic(
        "Asterion Nail",
        "a black iron spike that hums when gates lie",
        "it can pin one fate in place if fed a willing memory",
        "each use makes the dungeon remember you more clearly",
    ),
    StoryRelic(
        "Mire-Saint's Bell",
        "a handbell cast from coffin silver and plague glass",
        "it absolves wounds by moving them into someone nearby",
        "the bell eventually tolls for its bearer first",
    ),
    StoryRelic(
        "Lantern of Unburied Roads",
        "a hooded lamp filled with ash instead of oil",
        "it reveals shortcuts that were paid for with betrayals",
        "every revealed path erases a safer road elsewhere",
    ),
    StoryRelic(
        "Crown of Antlers and Teeth",
        "a pale crown that grows warm near frightened monsters",
        "it lets prey command predators for a single heartbeat",
        "the command always returns as a debt",
    ),
    StoryRelic(
        "Mirror Psalter",
        "a prayer book whose pages reflect possible sins",
        "it can identify curses before they take hold",
        "the owner becomes legible to every watcher below",
    ),
    StoryRelic(
        "Cinder-Key of Khar",
        "a furnace key with a living ember in its bow",
        "it opens sealed armories and burns away old cowardice",
        "locks opened by the key demand blood from later doors",
    ),
    StoryRelic(
        "Wormscript Map",
        "a vellum map tattooed by blind grave-worms",
        "it predicts which rooms hunger for guests or graves",
        "the map adds rooms whenever the bearer hesitates",
    ),
    StoryRelic(
        "Vessel of Last Rain",
        "a cracked urn of water from a drowned coronation",
        "it cools rage and weakens firebound tyrants",
        "spilled drops call drowned witnesses from hidden floors",
    ),
    StoryRelic(
        "Oath-Eater's Chain",
        "a hooked chain that tightens around spoken promises",
        "it turns broken vows into armor for one battle",
        "a kept vow becomes heavier with every floor",
    ),
    StoryRelic(
        "Heartseed Reliquary",
        "a thorned seedcase pulsing like a second heart",
        "it can grow sanctuary where no shrine should answer",
        "sanctuary roots also feed the dungeon's oldest bride",
    ),
)


# ---------------------------------------------------------------------------
# Guest templates — the procedural petitioners: the Unfinished, drawn to
# someone who can end things. ``speeches`` parallels ``motives``: the beat
# dialogue is the guest actually talking (<=90 chars), not a narrated summary.
# ---------------------------------------------------------------------------

STORY_GUEST_TEMPLATES = (
    StoryGuestTemplate(
        "Oathless Knight",
        ("Ser Caldus", "Dame Vey", "Rook of Voss"),
        (
            "asks a witness before a vow breaks",
            "guards a door that no longer exists",
            "weighs mercy against cowardice",
        ),
        "iron-clipped and formal",
        (
            "“I kept one vow: stay alive until witnessed. It weighs more than the nine I broke — watch, and I can finally set it down.”",
            "“The door fell years ago. My watch did not — an oath outlives its object down here, and mine will not release me.”",
            "“Tell me plainly: is mercy a shield, or a hole in one? I spared a man once, and a city drowned behind him.”",
        ),
    ),
    StoryGuestTemplate(
        "Grave-Witch",
        ("Mother Hush", "Edda Crowmilk", "Vespera Thorne"),
        (
            "plants living secrets in dead soil",
            "sells shelter for a future grief",
            "knows who the relic chose next",
        ),
        "tender, cruel, and amused",
        (
            "“Plant this secret in dead soil, love, and I'll owe you a warm grave. Buried truths keep the dead from digging for them.”",
            "“Shelter's cheap: one grief you haven't had yet. I collect sorrows before they happen — they keep better that way.”",
            "“The relic already chose its next keeper. Look how it leans toward you, like a child picking a parent.”",
        ),
    ),
    StoryGuestTemplate(
        "Drowned Heir",
        ("Prince Nerian", "Lysa Underwave", "The Blue-Lipped Child"),
        (
            "begs one remembered coronation song",
            "pleads for kin wearing old coins",
            "carries a map of tidewater and bone",
        ),
        "soft as water in a crypt",
        (
            "“Sing the coronation song. Any verse. My family drowned mid-crowning, and no one has finished the ceremony since.”",
            "“Spare the ones wearing my family's coins. They drowned honest, and the Gate still owes them a hearing.”",
            "“My map is tidewater and bone dust. The drowned drew it going down — it knows every door the water took.”",
        ),
    ),
    StoryGuestTemplate(
        "Ash Pilgrim",
        ("Harl the Sooted", "Sister Kharra", "Old Ember Jesk"),
        (
            "carries flame to a shrine that hates fire",
            "trades scars for foundry directions",
            "knows the one guilt the gate can't digest",
        ),
        "dry, hoarse, and patient",
        (
            "“Carry my flame to the shrine that hates fire. The monks say guilt burns clean; the shrine has never once agreed.”",
            "“Scars for directions — the foundry rate. Every burn on me is a turn in the road below, mapped in lasting ink.”",
            "“The Man Below can't digest one guilt: his own. Feed it to him and watch the gate hinge loosen.”",
        ),
    ),
    StoryGuestTemplate(
        "Mirror-Scribe",
        ("Tallow Quill", "Iosef of the Glass", "Nim Rue"),
        (
            "records the yous that chose worse",
            "erases omens for the price of certainty",
            "needs a signature before the Worms notice",
        ),
        "precise and frightened",
        (
            "“I've recorded the yous that chose worse. Care to stay ahead of them? The margin between you is thinner tonight.”",
            "“One omen, erased, for the price of your certainty. The Worms let us unwrite the future, never the doubt.”",
            "“Sign before the Worms notice. They always notice — an unsigned page is the only crime they hang scribes for.”",
        ),
    ),
    StoryGuestTemplate(
        "Antlered Hunter",
        ("Mael Whitehorn", "The Quiet Hart", "Sable of the Moon-Hunt"),
        (
            "tracks a beast wearing human prayers",
            "guides those who spare the marked",
            "smells where your story ends",
        ),
        "low, watchful, and direct",
        (
            "“The beast wears human prayers now. That's past my writ — the Court hunts escaped souls, not believers.”",
            "“Spare the marked one and I'll walk you true. The mark only means it slipped the Toll-Keeper's count.”",
            "“Your story is on the wind, roadless. I can smell where it ends — down deep, by a door that will not open.”",
        ),
    ),
    StoryGuestTemplate(
        "Mortuary Broker",
        ("Coin-Eye Pell", "Madam Nacre", "Voss Factor Ilm"),
        (
            "sells unfinished deaths in bronze tubes",
            "auctions one of your future wounds",
            "knows who bought the gate's silence",
        ),
        "courteous enough to be dangerous",
        (
            "“Unfinished deaths, bronze-sealed. Estate prices — the Guild bought them cheap when the city drowned mid-breath.”",
            "“Consent to auction one future wound, and we both eat this month. Pain sells best before it happens.”",
            "“I know who bought the gate's silence: the man behind it. He pays the Guild yearly to keep his ledger shut.”",
        ),
    ),
    StoryGuestTemplate(
        "Lost Cartographer",
        ("Ammar Without Roads", "Fen Chalkhand", "Sella of the Fold"),
        (
            "has mapped a floor that isn't yet",
            "unmaps one room that shouldn't exist",
            "angers walls until they show secrets",
        ),
        "rushed and ink-stained",
        (
            "“This floor doesn't exist yet — I've mapped it anyway. The dungeon reads my drafts and builds to spec when flattered.”",
            "“Choose one room that should never exist. I'll unmap it, and the dungeon will pretend it never meant to.”",
            "“Anger the walls and secrets show. Voss masons hid their shame behind plaster; the stones still flinch when accused.”",
        ),
    ),
    StoryGuestTemplate(
        "Bone-Mender",
        ("Saint-Not-Yet", "Mara Sutured", "Kell of White Thread"),
        (
            "stitches wounds into willing ghosts",
            "asks a monster bone for sanctuary",
            "recognizes an old injury of yours",
        ),
        "kind, exhausted, and unblinking",
        (
            "“Wounds stitch into willing ghosts — mine volunteer. The dead here queue for one last useful thing to do.”",
            "“One monster bone buys sanctuary. The dead protect whoever brings proof the monsters can die.”",
            "“I've sutured this wound before. On you — in a life the Ledger says you haven't led yet. Hold still.”",
        ),
    ),
    StoryGuestTemplate(
        "Furnace Heretic",
        ("Brass-Thumb Oren", "Malk the Quenched", "Devra Cogprayer"),
        (
            "hears the machine he broke praying",
            "sells the weak points of constructs",
            "offers fuel that improves loot and traps",
        ),
        "half-mad with relief",
        (
            "“I broke the sacred machine and now it prays to me. The Pulley built engines to reach heaven; mine got homesick.”",
            "“Spare me from the order and I'll show you where constructs rust. Even the Sentinel has a seam its founders regretted.”",
            "“Forbidden fuel: better loot, worse traps. The dungeon burns brighter when you feed it what it's not allowed.”",
        ),
    ),
)


# ---------------------------------------------------------------------------
# Dilemmas — twelve, budgeted: setup <=90 (clause), verbs <=40, outcomes <=70.
# Three are pinned by the engine: The Door That Remembers (D5), The Gate's
# Confession (D8), The Last Guest's Mask (D9). The rest rotate.
# ---------------------------------------------------------------------------

STORY_DILEMMAS = (
    StoryDilemmaTemplate(
        "The Door That Remembers",
        "a sealed door repeats the worst night you carry",
        "bear witness and leave it shut",
        "feed it a lesser secret",
        "break the hinge",
        "The door keeps your mercy; nearby patrols quiet.",
        "It opens on valuables and a sharper curse.",
        "The broken hinge rings through the barracks below.",
        truth="The dungeon stages old wounds to learn what you protect; whatever you feed it, it builds more of.",
    ),
    StoryDilemmaTemplate(
        "The Debt Lantern",
        "a lantern burns with a stranger's unpaid death",
        "carry the light to a shrine",
        "sell an hour of your future",
        "snuff it out",
        "The light marks safer sanctuaries ahead.",
        "The flame pays in loot and hungrier traps.",
        "The dark teaches your enemies fear — and you.",
        truth="A death nobody paid for keeps burning; how you treat it decides which rooms open ahead.",
    ),
    StoryDilemmaTemplate(
        "The Name in the Wall",
        "your name is carved fresh beside much older ones",
        "scratch out the newest wound",
        "trade the name for an omen",
        "leave your blade in the wall",
        "The wall forgets one danger; caches show themselves.",
        "The omen fattens rewards and sweetens curses.",
        "The insult draws champions with better spoils.",
        truth="The wall lists everyone the Gate is still owed; fresh carving means you are on this floor's bill.",
    ),
    StoryDilemmaTemplate(
        "The Hungry Reliquary",
        "the relic's echo demands proof you still choose freely",
        "refuse it and comfort the guest",
        "feed it one drop of blood",
        "command it to obey",
        "Gratitude bends the next shrines toward you.",
        "The blood opens a rich and dangerous route.",
        "The relic recoils and wakes oathbound hunters.",
        truth="Relics test their bearers: prove you choose freely and it serves, falter and it starts choosing for you.",
    ),
    StoryDilemmaTemplate(
        "The Witness Below",
        "a dying stranger holds one truth about the Man Below",
        "ease their passing",
        "ask the truth's price",
        "force the name out",
        "Their blessing softens the next floor.",
        "Their price buys loot and leaves a curse-scent.",
        "The stolen truth emboldens you — and is heard.",
        truth="The Toll-Keeper was a man once, and this stranger watched him refuse the Gate. Truth like that has a price.",
    ),
    StoryDilemmaTemplate(
        "The False Sanctuary",
        "a safe room is staged one comfort too perfectly",
        "warn the guest away",
        "take what comfort you can",
        "tear down every charm",
        "Real sanctuary answers your restraint.",
        "The false room pays in gear and hidden needles.",
        "The angry walls reveal the foes they hid.",
        truth="The dungeon builds traps out of comfort; a room this kind is asking for something in return.",
    ),
    StoryDilemmaTemplate(
        "The Coin-Eyed Corpse",
        "a corpse offers coins for a death you haven't suffered",
        "bury the coins with it",
        "take the coins and the mark",
        "melt them into a challenge",
        "Burial draws helpful dead and quiet rooms.",
        "Marked coin buys rare finds and rash bargains.",
        "The token calls elites to meet you openly.",
        truth="The Mortuary Guild pays in advance for deaths it expects to collect; taking the coin signs the order.",
    ),
    StoryDilemmaTemplate(
        "The Beast in Prayer",
        "a monster kneels, praying in a tongue you know",
        "spare it and learn what it fears",
        "bind it with the relic's hunger",
        "kill the prayer mid-verse",
        "Its fear maps secret paths; pursuit thins.",
        "The binding pays now and stains later choices.",
        "Its kin arrive angry, carrying better spoils.",
        truth="Some monsters here are only unfinished people; this one still remembers the words said over its grave.",
    ),
    StoryDilemmaTemplate(
        "The Broken Map",
        "a torn map shows two roads down and one missing witness",
        "take the road that saves the witness",
        "take the road with treasure teeth",
        "burn the map and trust your feet",
        "The saved witness tips shrines and secrets your way.",
        "The toothed road enriches caches and trapwork.",
        "The floor turns hostile but predictable.",
        truth="Both roads go down; the map only asks what you will spend getting there — a stranger, or your certainty.",
    ),
    StoryDilemmaTemplate(
        "The Gate's Confession",
        "the Man Below borrows a mouth and offers a smaller ending",
        "refuse him for the guest's sake",
        "take the power, keep the run",
        "mock him until he names himself",
        "The refusal keeps what is yours, yours.",
        "The gift is strong, cursed, and remembered.",
        "His pride cracks; his true name slips out.",
        truth="He offers small endings so no one reaches the big one; every taker feeds his door another year.",
    ),
    StoryDilemmaTemplate(
        "The Choir Without Throats",
        "unseen singers chant a verse built from your lost chances",
        "answer with silence",
        "answer with a secret refrain",
        "answer with steel on stone",
        "Silence calms the floor; quiet help appears.",
        "The refrain buys occult reward, echoed in traps.",
        "The broken verse calls armed witnesses.",
        truth="The Choir sings with the voices of those who never chose; answer wrongly and yours joins the verse.",
    ),
    StoryDilemmaTemplate(
        "The Last Guest's Mask",
        "a face flickers between friend, foe, and your reflection",
        "offer trust, guard high",
        "ask which face profits",
        "shatter the mask",
        "Trust steadies allies; patrols lose their nerve.",
        "Profit sharpens loot, curses, and costs.",
        "The shards anger elites and hurry the truth.",
        truth="The dungeon wears faces to learn yours; what you show it now, it will send against you later.",
    ),
)

STORY_LOCATION_MOTIFS = (
    StoryLocationMotif(
        "Crypt of Ash", "charcoal saints and kneeling smoke", "ember-debts"
    ),
    StoryLocationMotif(
        "Fungal Catacombs", "pale caps growing from forgotten vows", "spore dreams"
    ),
    StoryLocationMotif(
        "Violet Reliquary", "void glass humming around chained relics", "astral hunger"
    ),
    StoryLocationMotif(
        "Sunken Bastion", "drowned banners drifting in still air", "oath-floods"
    ),
    StoryLocationMotif(
        "Frozen Ossuary", "blue bone vaults and frost-bitten prayers", "rime silence"
    ),
    StoryLocationMotif(
        "Obsidian Foundry", "molten gears stamping names into iron", "furnace law"
    ),
    StoryLocationMotif(
        "Moonlit Aquifer", "silver wells reflecting wrong moons", "tide omens"
    ),
    StoryLocationMotif(
        "Thornbound Vault", "root-split altars and wedding thorns", "green hunger"
    ),
)


# ---------------------------------------------------------------------------
# Tethers — the recurring NPC bound to each archetype, appearing at depths
# 1 (meet), 5 (reveal), 9 (crisis). Roles reuse existing guest templates so
# sprites and staging keep working; names are fixed instead of rolled.
# ---------------------------------------------------------------------------

STORY_TETHERS: dict[str, StoryTether] = {
    "Warden": StoryTether(
        role="Oathless Knight",
        name="Ser Caldus",
        meet=StoryTetherBeat(
            "seeks the warden who opened the door",
            "“You opened the door. I am what came through — the pilgrim, the signet, all of it. Shall we walk a while before we speak of that night?”",
        ),
        reveal=StoryTetherBeat(
            "carries what came through that night",
            "“The door knew your signet, Warden — your house bought passage generations ago. You blamed the softest thing in the room, and it was never the mercy.”",
        ),
        crisis=StoryTetherBeat(
            "asks a witness before his last vow breaks",
            "“One vow left: stay alive until witnessed. You guard the living, I know — but witness me, and I am finally allowed to stop.”",
        ),
        crisis_choices={
            "aid": StoryCrisisChoice(
                "witness his last vow break",
                "He kneels, finishes, and is finally done carrying.",
            ),
            "bargain": StoryCrisisChoice(
                "take his vow onto yourself",
                "He lives, unburdened; you carry two oaths now.",
            ),
            "defy": StoryCrisisChoice(
                "refuse him the death",
                "He lives, unfinished — and stubborn enough to follow.",
            ),
        },
    ),
    "Rogue": StoryTether(
        role="Mortuary Broker",
        name="Coin-Eye Pell",
        meet=StoryTetherBeat(
            "recognizes an old lot number",
            "“Well. The lot number walks. I brokered your sale, dear customer — browse freely, everything here is second-hand, including the guilt.”",
        ),
        reveal=StoryTetherBeat(
            "keeps the bill of your sale",
            "“The bill of sale: one name, one roof, a hundred children kept dry. The Blackroof sold you to buy itself — bad trade, kind arithmetic.”",
        ),
        crisis=StoryTetherBeat(
            "opens the counter one last time",
            "“The deed is in reach and my counter is open one last time. Fire, purchase, or statement — I profit least from the one I'd respect most.”",
        ),
        crisis_choices={
            "aid": StoryCrisisChoice(
                "burn the whole deed-book",
                "Every sold death voids; Pell holds the light for you.",
            ),
            "bargain": StoryCrisisChoice(
                "buy your death back honest",
                "Paid in full — the first thing you ever owned.",
            ),
            "defy": StoryCrisisChoice(
                "pin the deed, unsigned",
                "Let him keep a death that keeps its own hours.",
            ),
        },
    ),
    "Arcanist": StoryTether(
        role="Mirror-Scribe",
        name="Nim Rue",
        meet=StoryTetherBeat(
            "files a familiar hand",
            "“I file your handwriting every week — the confiscated proof, all of it. It's a good hand. Don't tell the Worms I keep reading it.”",
        ),
        reveal=StoryTetherBeat(
            "holds the page with your name",
            "“One page, two entries: your erased name, your living proof. The Worms only ever sell half a page — choose which half stays theirs.”",
        ),
        crisis=StoryTetherBeat(
            "faces the Worms' audit",
            "“They're auditing my margins. Sympathy, they call it — I wrote that I hoped you'd live. Please be quick; corrections here are eaten.”",
        ),
        crisis_choices={
            "aid": StoryCrisisChoice(
                "claim her notes as your hand",
                "You forge yourself; Rue is spared, you go unrecorded.",
            ),
            "bargain": StoryCrisisChoice(
                "buy her desk with the proof",
                "Rue is promoted to safety; the Worms hold a copy.",
            ),
            "defy": StoryCrisisChoice(
                "burn the audit itself",
                "Rue is expelled — and walks with you, unsupervised.",
            ),
        },
    ),
    "Acolyte": StoryTether(
        role="Drowned Heir",
        name="The Blue-Lipped Child",
        meet=StoryTetherBeat(
            "answered the wrong bell",
            "“You rang my bell. I came. Was that wrong? I lived in your tower, keeper — you warned every door in town except ours.”",
        ),
        reveal=StoryTetherBeat(
            "waits by a rope still swaying",
            "“It's a good bell. It was early, not wrong — the plague was already sleeping down here when it rang. It only ever lied about you.”",
        ),
        crisis=StoryTetherBeat(
            "asks for a grave and a name",
            "“Bury me here, or at the door? A foundling needs a name said over the grave, and nobody ever gave me one. Do you have a spare?”",
        ),
        crisis_choices={
            "aid": StoryCrisisChoice(
                "give the Child your own name",
                "Named with yours, the Child passes; you walk on nameless.",
            ),
            "bargain": StoryCrisisChoice(
                "carry them to the door",
                "The Child holds your hand for the last floor.",
            ),
            "defy": StoryCrisisChoice(
                "refuse the grave",
                "You keep the Child; even they know it's the bell you spare.",
            ),
        },
    ),
    "Ranger": StoryTether(
        role="Antlered Hunter",
        name="Sable of the Moon-Hunt",
        meet=StoryTetherBeat(
            "arrives one room late, on purpose",
            "“Two writs: the stag, and the one who spared it. That's you, roadless. I keep miscounting on purpose — explain the stag before I stop.”",
        ),
        reveal=StoryTetherBeat(
            "carries two writs she won't read",
            "“The mark isn't mercy, it's bookkeeping — your captain slipped the Toll-Keeper's count, and the Court wants the tally clean. You saw that. That's worse.”",
        ),
        crisis=StoryTetherBeat(
            "counts the last hunt aloud",
            "“It stopped running. It waits for you, and your captain waits inside it. Loose the arrow or lower the bow — the law only needs one of us satisfied.”",
        ),
        crisis_choices={
            "aid": StoryCrisisChoice(
                "speak the captain's name",
                "The soul unseats; a plain stag walks away. No arrows.",
            ),
            "bargain": StoryCrisisChoice(
                "carry the soul yourself",
                "You carry the captain now; Sable walks escort.",
            ),
            "defy": StoryCrisisChoice(
                "put the arrow through the writ",
                "The Moon-Hunt is two people now. Walk faster.",
            ),
        },
    ),
}

# Depth-8: the Toll-Keeper borrows the guest's mouth and offers each archetype
# the one thing that would un-happen their wound. Refusing must hurt a little.
TYRANT_OFFERS: dict[str, str] = {
    "Warden": "“The night, returned. The door, shut. You, blameless — Kasar Voss standing, every soul asleep in a city that never drowned. I ask so little: that nothing ends, theirs included.”",
    "Rogue": "“One page, torn out. Yours. The book stays, but you walk up whole, unowned, amended — no guild, no gallows, no buyer. The others never knew their deeds existed.”",
    "Arcanist": "“Stay. The proof in your bones can never open my door if you never end — and here, no one ends. Call it tenure: eternity to be right, with no one left to argue.”",
    "Acolyte": "“One bell, unrung. One town, unbroken. One child — unasked-for. Only you would remember them, keeper, and memory is a lighter grave than the one you are digging.”",
    "Ranger": "“The road home, redrawn. The patrol rides back, captain in front, and the stag was never marked. It costs only the refusal — the one moment of you that ever mattered.”",
}


# ---------------------------------------------------------------------------
# Roads — how the run reads back the player's dominant verb. Computed at act
# breaks (after depths 3/6/9) from existing story flags; "unwritten" before
# the first break. One omen clause per road, <=60 chars.
# ---------------------------------------------------------------------------

STORY_ROAD_LINES: dict[str, str] = {
    "witness": "The rooms lean kinder toward your mercies.",
    "debtor": "The rooms have learned to name their prices.",
    "defiant": "The rooms brace and hide their throats.",
    "forsaken": "The rooms have stopped speaking to you.",
    "unwritten": "",
}

# Rue's one line on a death screen, by road. Single line, <=90.
RUE_DEATH_LINES: dict[str, str] = {
    "witness": "Entry closed. It was a kind one. I'm leaving the margin open.",
    "debtor": "Entry closed. Accounts outstanding. I'm leaving the margin open.",
    "defiant": "Entry closed mid-sentence. I'm leaving the margin open.",
    "forsaken": "Entry closed. No witnesses listed. The margin stays open anyway.",
    "unwritten": "Entry closed. …I'm leaving the margin open.",
}


# ---------------------------------------------------------------------------
# The Stalled — boss dressing. One omen foreshadow line per boss (<=80), a
# sharper variant when the matching archetype descends, and one last-word
# floater each (<=30). The Sentinel does not speak; its hum stops.
# ---------------------------------------------------------------------------

BOSS_OMEN_LINES: dict[str, str] = {
    "ash_gallows": "Below: the city's executioner, stalled mid-drop, still owed one ending.",
    "mycelial_matron": "Below: the plague-ward's midwife. Her ward never closed.",
    "rime_chanter": "Below: the bell-warden, nine of ten bells rung, holding the ninth.",
    "void_sentinel": "Below: the guardian of an emptied vault, unable to stop.",
    "gate_tyrant": "Below: the Toll-Keeper himself. Nothing here has ended in a hundred years.",
}

BOSS_MIRROR_OMEN_LINES: dict[tuple[str, str], str] = {
    ("ash_gallows", "Rogue"): "Below: the hangman. Your shadow swings from his belt in a jar.",
    ("mycelial_matron", "Acolyte"): "Below: the one who kept your plague warm, keeper.",
    ("rime_chanter", "Arcanist"): "Below: he chants your thesis, set to bells. They kept your errors in.",
    ("void_sentinel", "Warden"): "Below: a warden with nothing left to guard. Look closely.",
}

BOSS_LAST_WORDS: dict[str, str] = {
    "Ash Gallows Knight": "“…finished.”",
    "Mycelial Matron": "“All better now.”",
    "Rime Chanter of the Ninth Bell": "“Ring the tenth… for me.”",
    "Voidbound Rune Sentinel": "The hum stops.",
    "Dread Gate Tyrant": "“…so that is how it ends.”",
}


# ---------------------------------------------------------------------------
# Endings — the Gate's verb, per archetype. Body reads as flowing prose in
# the epilogue node (wraps to ~3 lines); codas append one line each for road
# shading and the depth-9 crisis echo.
# ---------------------------------------------------------------------------

STORY_ENDINGS: dict[str, dict[str, StoryEnding]] = {
    "Warden": {
        "aid": StoryEnding(
            "The Held Door",
            "The Warden opens the Last Gate and holds it, shield lowered, while the "
            "city ends past him in procession. A shield is not a wall. It never was. "
            "The Warden holds the door — open, this time.",
        ),
        "bargain": StoryEnding(
            "The Fair Scale",
            "Someone must weigh what passes; better someone who knows what refusing "
            "costs. The Warden takes the Toll-Keeper's seat, and the scales are "
            "honest. They feel light today. They feel lighter every day.",
        ),
        "defy": StoryEnding(
            "No More Doors",
            "The Gate breaks. No tolls, no thresholds — the Unfinished drift up "
            "toward the living sky, and the living will learn to live with ghosts. "
            "Nothing left to guard. Everything left to shepherd.",
        ),
    },
    "Rogue": {
        "aid": StoryEnding(
            "The Emptied Market",
            "The whole deed-book goes through the Gate. Every sold death finishes; "
            "the market dies overnight. You stole one thing from everyone at once: "
            "the price tag. No one owns anyone tonight.",
        ),
        "bargain": StoryEnding(
            "The Honest Purchase",
            "You pay what a name is worth — the shadow, the alias, the whole "
            "disguise — and walk up carrying only the name. Finally yours. First "
            "thing you ever owned. Wear it out.",
        ),
        "defy": StoryEnding(
            "The Standing Debt",
            "No deal. The deed stays pinned to the barred Gate with a good knife. "
            "Somewhere below, a death waits for an owner who will not come to "
            "collect. You've decided to live forever — out of spite.",
        ),
    },
    "Arcanist": {
        "aid": StoryEnding(
            "The Answered Proof",
            "At the open Gate you speak the counter-sigil into the dream. The "
            "proof completes, and concludes, and stops being true. The bones go "
            "quiet. Above, the black gap in the sky lets one star back in. Nobody "
            "will know it was you. That was the proof all along.",
        ),
        "bargain": StoryEnding(
            "The Restored Name",
            "Rue writes your name into the Ledger's first page. The Worms' fee: "
            "the proof stands, unanswered. You are cited, titled, real. Some "
            "nights you feel the door turn over in its sleep, in your bones.",
        ),
        "defy": StoryEnding(
            "The Standing Argument",
            "You let the proof finish — and step into the opening seal to argue "
            "with what it finds. The seal dreams a door; you dream a wall; the "
            "debate does not end. You were right. Being right, it turns out, is a "
            "place. You live there now.",
        ),
    },
    "Acolyte": {
        "aid": StoryEnding(
            "The True Funeral",
            "The Gate opens and the tenth bell rings as a funeral bell — the rite, "
            "at last, at the right time. The Child passes, named. The plague loses "
            "its seed. Far above, the bell of Saint Mire rings once, true, by "
            "itself, over an empty town.",
        ),
        "bargain": StoryEnding(
            "The Returned Confession",
            "You give him back every sin he confessed. Un-absolved, weighed at "
            "last, the Toll-Keeper can finally end. Someone must hear confessions "
            "at the door now; the dead vote for you, unanimously. First in line: "
            "everyone.",
        ),
        "defy": StoryEnding(
            "The Broken Bell",
            "You break the great bell of the Gate. No death will ever again arrive "
            "announced — every ending honest, sudden, unforetold, forever. The "
            "Child laughs: the first surprise in the history of the world.",
        ),
    },
    "Ranger": {
        "aid": StoryEnding(
            "The Hunt Without Arrows",
            "You lead the Stag through the open Gate. The captain finishes on the "
            "far side; what turns back at the threshold is just a stag, white and "
            "ordinary, walking up toward grass. The hunt ends. Nothing died. The "
            "Court will argue for a century.",
        ),
        "bargain": StoryEnding(
            "The Next White Thing",
            "Someone must guide the escaped dead back to the door, and the "
            "roadless make the best guides. You take the Stag's office: the walker "
            "between floors, the thing hunters refuse to shoot. Someday one will "
            "see what you carry and lower the bow.",
        ),
        "defy": StoryEnding(
            "The Old Way",
            "The arrow goes through the count itself — the tally, the marks, the "
            "law of appointed prey. Hunts end when hunger ends, the old way, the "
            "honest way. From tonight, everything below gets to be an animal "
            "again. Including you.",
        ),
    },
}

# One extra ending line, chosen by the depth-9 crisis verb.
STORY_CRISIS_ECHOES: dict[str, dict[str, str]] = {
    "Warden": {
        "aid": "At the door, a knight's shade stands and salutes — finished.",
        "bargain": "The second oath sits quiet on your shoulder, at last.",
        "defy": "Caldus limps up beside you, furious, alive. He stays.",
    },
    "Rogue": {
        "aid": "Pell waves the smoking ledger like a handkerchief. Goodbye.",
        "bargain": "Your missing shadow doesn't come back. You stop checking.",
        "defy": "Below, a knife keeps a deed pinned through one word: no.",
    },
    "Arcanist": {
        "aid": "Somewhere, a clerk you saved misfiles you — kindly, forever.",
        "bargain": "Rue's promotion letter is filed under regret. Hers.",
        "defy": "Rue narrates this part herself. Six adjectives. Wonderful.",
    },
    "Acolyte": {
        "aid": "You answer to 'keeper' now. It is enough. It is yours.",
        "bargain": "A small cold hand lets go only after the bell.",
        "defy": "The bell in your pack stays quiet. Even about the lies.",
    },
    "Ranger": {
        "aid": "Sable files one writ: finished, zero arrows. The Court chokes.",
        "bargain": "The captain's voice thanks you once, using your old name.",
        "defy": "Two exiles walk up, doing the wild's oldest arithmetic: enough.",
    },
}

# One closing line by road; the Forsaken road gets a per-archetype cut.
STORY_ENDING_ROAD_CODAS: dict[str, str] = {
    "witness": "The door is crowded — everyone you helped came to see it end.",
    "debtor": "Every debt you signed came due today. Every one was worth it.",
    "defiant": "The dungeon does not mourn you leaving. It checks its locks.",
    "unwritten": "",
}

STORY_ENDING_FORSAKEN_CODAS: dict[str, str] = {
    "Warden": "The passing dead do not look at you.",
    "Rogue": "The freed dead pick another door.",
    "Arcanist": "The returning star flickers, once.",
    "Acolyte": "The silence after the bell runs a little long.",
    "Ranger": "The wild remembers you passed by on the left.",
}

# The Gate's last question — universal labels; the archetype flavor lives in
# the ending each verb selects. Label <=34, detail <=92.
STORY_GATE_CHOICES = (
    ("aid", "End it well", "Open the Gate and let the unfinished finish"),
    ("bargain", "Take the seat", "Keep the door; weigh the tolls with honest scales"),
    ("defy", "Break the door", "No more tolls — let the unfinished walk up free"),
)

# Guild-factor shop patter (Coin-Eye Pell's franchise). Rotating floaters, <=70.
SHOP_PATTER_LINES = (
    "Everything here is second-hand. Including me.",
    "Unworn deaths fetch the best price. Like boots.",
    "No refunds. The dead witnessed the receipt.",
    "Browse freely. The inventory rarely bites first.",
    "Guild rates: fair, final, and faintly funereal.",
)


STORY_CORPUS = {
    "arcs": STORY_ARCS,
    "backstories": STORY_BACKSTORIES,
    "factions": STORY_FACTIONS,
    "relics": STORY_RELICS,
    "guest_templates": STORY_GUEST_TEMPLATES,
    "dilemmas": STORY_DILEMMAS,
    "location_motifs": STORY_LOCATION_MOTIFS,
    "tethers": STORY_TETHERS,
    "tyrant_offers": TYRANT_OFFERS,
    "road_lines": STORY_ROAD_LINES,
    "endings": STORY_ENDINGS,
}
