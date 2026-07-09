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

from __future__ import annotations

from .definitions import (
    StoryBackstory,
    StoryDilemmaTemplate,
    StoryFaction,
    StoryGuestTemplate,
    StoryLocationMotif,
    StoryRelic,
)


STORY_BACKSTORIES: dict[str, tuple[StoryBackstory, ...]] = {
    "Warden": (
        StoryBackstory(
            "Last Shield of Caer Voss",
            "your citadel fell after you opened its inner gate to a wounded pilgrim",
            "you swore to guard the living from bargains made at sealed doors",
            "the pilgrim wore your family signet beneath their bandages",
        ),
        StoryBackstory(
            "Iron Oath Exile",
            "your order branded you oathbreaker for sparing a possessed child",
            "you seek the law that can bind mercy without surrendering judgment",
            "the child's voice still answers from inside your shield rim",
        ),
        StoryBackstory(
            "Gravewatch Captain",
            "your watch buried an empty coffin and called the count dead",
            "you hunt the oath that let a noble house escape its tomb",
            "your captain's ledger names you as the final witness",
        ),
    ),
    "Rogue": (
        StoryBackstory(
            "Knife of the Lantern Court",
            "you stole a relic-map and sold copies to three rival cults",
            "you chase the original before any buyer reaches the last gate",
            "one copy was written in your own blood before you were born",
        ),
        StoryBackstory(
            "Blackroof Orphan",
            "the guild that raised you traded your name to a mirror-saint",
            "you descend to steal it back before the saint learns your face",
            "every lock in the dungeon remembers your childhood lullaby",
        ),
        StoryBackstory(
            "Grinning Gallowsblade",
            "you survived execution when the rope whispered a hidden passage",
            "you follow that whisper to learn who bought your death",
            "the hangman vanished carrying your shadow in a jar",
        ),
    ),
    "Arcanist": (
        StoryBackstory(
            "Scholar of the Ninth Seal",
            "your thesis proved a forbidden gate could dream itself open",
            "you seek the counter-sigil before your proof becomes prophecy",
            "the academy erased you but kept your handwriting in its mirrors",
        ),
        StoryBackstory(
            "Star-Ash Savant",
            "you burned a constellation into ash while saving one village",
            "you need a relic lens that can name the stars you destroyed",
            "the survivors pray to the black space your spell left behind",
        ),
        StoryBackstory(
            "Runebound Fugitive",
            "your master stitched a living spell into your bones and died smiling",
            "you descend to unwrite the spell before it learns hunger",
            "the spell recognizes one dungeon faction as its parent",
        ),
    ),
    "Acolyte": (
        StoryBackstory(
            "Bell-Keeper of Saint Mire",
            "you rang the death bell for a plague that had not yet arrived",
            "you hunt the first corpse to stop the future from catching up",
            "the bell tolls softly whenever you lie",
        ),
        StoryBackstory(
            "Ashen Confessor",
            "you absolved a tyrant and inherited every sin they confessed",
            "you descend to divide those sins among the things that deserve them",
            "one sin in your blood knows the tyrant's true name",
        ),
        StoryBackstory(
            "Gravetongue Novice",
            "the dead chose you as their priest before any living temple would",
            "you seek a covenant that can quiet them without betraying them",
            "the oldest voice among them calls you heir",
        ),
    ),
    "Ranger": (
        StoryBackstory(
            "Thornroad Outrider",
            "your patrol followed impossible hoofprints and returned missing its captain",
            "you track the beast that walks between dungeon floors",
            "the captain's compass points toward your heartbeat",
        ),
        StoryBackstory(
            "Moon-Hunt Exile",
            "your clan cast you out for refusing to kill a cursed white stag",
            "you follow the stag's blood trail to the last gate",
            "the stag carries a human soul that recognizes your arrows",
        ),
        StoryBackstory(
            "Wildermark Cartographer",
            "you mapped roads that vanished behind every caravan you guided",
            "you need the dungeon's first map before the surface forgets itself",
            "one missing road leads directly to your childhood home",
        ),
    ),
}

STORY_FACTIONS = (
    StoryFaction(
        "Choir of the Hollow Star",
        "starless chanters",
        "teach the final gate to sing open through sacrifice and echo",
        "they cannot speak a true name without losing a memory",
        (160, 86, 230),
    ),
    StoryFaction(
        "Ember Monks of Khar",
        "ash-scarred ascetics",
        "temper souls in furnace rites until only useful guilt remains",
        "water blessed by moonlight burns them like acid",
        (245, 104, 52),
    ),
    StoryFaction(
        "Drowned Lineage",
        "blue-lipped heirs",
        "restore a sunken kingdom by flooding every oath beneath the earth",
        "they must answer any question asked beside still water",
        (86, 188, 215),
    ),
    StoryFaction(
        "Thorn Brides of Edda",
        "root-veiled witches",
        "marry living bloodlines to the dungeon's oldest hunger",
        "iron wedding rings silence their glamour",
        (126, 214, 92),
    ),
    StoryFaction(
        "Voss Mortuary Guild",
        "coin-eyed undertakers",
        "auction unfinished deaths to nobles, ghosts, and desperate heroes",
        "they cannot refuse a properly witnessed debt",
        (190, 130, 215),
    ),
    StoryFaction(
        "Order of the Black Pulley",
        "engine-priests",
        "raise the dungeon one floor closer to heaven by chain and furnace",
        "their machines stall when fed unmarked bones",
        (245, 132, 72),
    ),
    StoryFaction(
        "Pale Antler Court",
        "moon-crowned hunters",
        "hunt cursed souls until predator and prey exchange bodies",
        "they cannot cross a threshold swept with grave salt",
        (145, 184, 232),
    ),
    StoryFaction(
        "Scriptorium of Worms",
        "carrion archivists",
        "write every possible ending and punish runs that improvise",
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
        "it predicts which rooms hunger for guests, relics, or graves",
        "the map adds rooms whenever the bearer hesitates",
    ),
    StoryRelic(
        "Vessel of Last Rain",
        "a cracked urn filled with water from a drowned coronation",
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

STORY_GUEST_TEMPLATES = (
    StoryGuestTemplate(
        "Oathless Knight",
        ("Ser Caldus", "Dame Vey", "Rook of Voss"),
        (
            "seeks a witness before breaking their final vow",
            "guards a door that no longer exists",
            "needs proof that mercy is not another form of cowardice",
        ),
        "iron-clipped and formal",
    ),
    StoryGuestTemplate(
        "Grave-Witch",
        ("Mother Hush", "Edda Crowmilk", "Vespera Thorne"),
        (
            "wants a living secret planted in dead soil",
            "offers shelter if paid with a future grief",
            "claims the relic already chose its next victim",
        ),
        "tender, cruel, and amused",
    ),
    StoryGuestTemplate(
        "Drowned Heir",
        ("Prince Nerian", "Lysa Underwave", "The Blue-Lipped Child"),
        (
            "begs for one remembered coronation song",
            "asks you to spare enemies wearing ancestral coins",
            "carries a map written in tidewater and bone dust",
        ),
        "soft as water in a crypt",
    ),
    StoryGuestTemplate(
        "Ash Pilgrim",
        ("Harl the Sooted", "Sister Kharra", "Old Ember Jesk"),
        (
            "needs flame carried to a shrine that rejects fire",
            "trades scars for directions through the foundry floors",
            "knows which guilt the gate tyrant cannot digest",
        ),
        "dry, hoarse, and patient",
    ),
    StoryGuestTemplate(
        "Mirror-Scribe",
        ("Tallow Quill", "Iosef of the Glass", "Nim Rue"),
        (
            "records versions of you that made worse choices",
            "offers to erase one omen for the price of certainty",
            "needs a signature before the Scriptorium notices",
        ),
        "precise and frightened",
    ),
    StoryGuestTemplate(
        "Antlered Hunter",
        ("Mael Whitehorn", "The Quiet Hart", "Sable of the Moon-Hunt"),
        (
            "tracks a beast that learned to wear human prayers",
            "will guide you if you spare a marked predator",
            "smells the player's backstory on the dungeon air",
        ),
        "low, watchful, and direct",
    ),
    StoryGuestTemplate(
        "Mortuary Broker",
        ("Coin-Eye Pell", "Madam Nacre", "Voss Factor Ilm"),
        (
            "sells unfinished deaths sealed in little bronze tubes",
            "wants your consent to auction a future wound",
            "knows who purchased the final gate's silence",
        ),
        "courteous enough to be dangerous",
    ),
    StoryGuestTemplate(
        "Lost Cartographer",
        ("Ammar Without Roads", "Fen Chalkhand", "Sella of the Fold"),
        (
            "has mapped a floor that has not yet generated",
            "asks you to choose which room should never exist",
            "can make secrets easier to find by angering the walls",
        ),
        "rushed and ink-stained",
    ),
    StoryGuestTemplate(
        "Bone-Mender",
        ("Saint-Not-Yet", "Mara Sutured", "Kell of White Thread"),
        (
            "heals wounds by stitching them into a willing ghost",
            "asks for a monster bone before granting sanctuary",
            "recognizes an old injury from the player's origin",
        ),
        "kind, exhausted, and unblinking",
    ),
    StoryGuestTemplate(
        "Furnace Heretic",
        ("Brass-Thumb Oren", "Malk the Quenched", "Devra Cogprayer"),
        (
            "sabotaged a sacred machine and now hears it praying",
            "can weaken constructs if spared from their order",
            "offers forbidden fuel that improves loot and traps alike",
        ),
        "half-mad with relief",
    ),
)

STORY_DILEMMAS = (
    StoryDilemmaTemplate(
        "The Door That Remembers",
        "a sealed threshold repeats a betrayal from your backstory",
        "bear witness and leave it closed",
        "feed it a lesser secret for treasure",
        "break the hinge and dare the wardens below",
        "the door keeps your mercy and quiets nearby patrols",
        "the door opens on valuables and sharper curses",
        "the broken hinge rings through enemy barracks",
    ),
    StoryDilemmaTemplate(
        "The Debt Lantern",
        "a lantern burns with a guest's unpaid death",
        "carry the light to a shrine",
        "sell one hour of your future to brighten it",
        "snuff it before the faction follows",
        "the light marks safer sanctuaries ahead",
        "the lantern reveals richer loot and hungrier traps",
        "darkness hides you poorly but teaches enemies fear",
    ),
    StoryDilemmaTemplate(
        "The Name in the Wall",
        "your secret is carved into fresh stone beside older names",
        "scratch out the newest wound",
        "trade the name for a key-shaped omen",
        "leave your blade in the inscription",
        "the wall forgets one danger and shows hidden caches",
        "the omen fattens rewards but makes curses more tempting",
        "the insult draws champions who carry better spoils",
    ),
    StoryDilemmaTemplate(
        "The Hungry Reliquary",
        "the relic's echo demands proof that you still choose freely",
        "refuse it and comfort the guest",
        "feed it a drop of blood for guidance",
        "command it to obey",
        "the guest's gratitude bends future shrines toward you",
        "the blood opens a profitable but perilous route",
        "the relic recoils and wakes oathbound hunters",
    ),
    StoryDilemmaTemplate(
        "The Witness Below",
        "a dying stranger knows one truth about the antagonist",
        "ease their passing and keep the truth whole",
        "ask the truth's price before helping",
        "force the name from them",
        "their blessing softens enemy pressure on the next floor",
        "their price buys loot and leaves a curse-scent trail",
        "the stolen name gives courage and draws retaliation",
    ),
    StoryDilemmaTemplate(
        "The False Sanctuary",
        "a safe room is staged too perfectly to trust",
        "warn the guest away",
        "take what comfort you can before it turns",
        "tear down every charm",
        "real sanctuary answers your restraint",
        "the false room pays in gear and hidden needles",
        "the shattered charms anger the dungeon into revealing foes",
    ),
    StoryDilemmaTemplate(
        "The Coin-Eyed Corpse",
        "a corpse offers payment for a death you have not suffered",
        "bury the coins with it",
        "take the coins and accept the mark",
        "melt the coins into a challenge token",
        "burial draws helpful dead and quiet rooms",
        "marked coin buys rare finds and dangerous bargains",
        "the token challenges elites to meet you openly",
    ),
    StoryDilemmaTemplate(
        "The Beast in Prayer",
        "a monster kneels in a language from your origin",
        "spare it and learn what it fears",
        "bind it briefly with the relic's hunger",
        "kill the prayer before it spreads",
        "its fear reveals secret paths and lessens pursuit",
        "the binding yields a reward but stains future choices",
        "the interrupted prayer enrages kin carrying stronger rewards",
    ),
    StoryDilemmaTemplate(
        "The Broken Map",
        "a map shows two possible next floors and one missing witness",
        "choose the path that saves the witness",
        "choose the path marked with treasure teeth",
        "burn the map and trust your will",
        "the saved witness improves shrine and secret chances",
        "the treasure path enriches caches and trapwork",
        "the burned map makes rooms hostile but predictable",
    ),
    StoryDilemmaTemplate(
        "The Gate's Confession",
        "the final gate speaks through a guest and offers a lesser ending",
        "reject the ending for the guest's sake",
        "negotiate for power without surrendering the run",
        "mock the gate until it names its tyrant",
        "the rejected ending protects your resources",
        "the negotiated power is strong, cursed, and memorable",
        "the mocked gate strengthens its tyrant but weakens its pride",
    ),
    StoryDilemmaTemplate(
        "The Choir Without Throats",
        "unseen singers chant a verse built from your lost chances",
        "answer with silence",
        "answer with a secret refrain",
        "answer with steel on stone",
        "silence calms the floor and reveals quiet help",
        "the refrain purchases occult rewards with trap-laced echoes",
        "steel breaks the verse and calls armed witnesses",
    ),
    StoryDilemmaTemplate(
        "The Last Guest's Mask",
        "a guest's face flickers between ally, enemy, and your own reflection",
        "offer trust without dropping your guard",
        "ask which face is most profitable",
        "shatter the mask before it chooses",
        "trust makes future aid more likely and enemy patrols uncertain",
        "profit sharpens loot, curses, and hidden costs",
        "shattered glass angers elites and reveals the true plot faster",
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

STORY_CORPUS = {
    "backstories": STORY_BACKSTORIES,
    "factions": STORY_FACTIONS,
    "relics": STORY_RELICS,
    "guest_templates": STORY_GUEST_TEMPLATES,
    "dilemmas": STORY_DILEMMAS,
    "location_motifs": STORY_LOCATION_MOTIFS,
}

