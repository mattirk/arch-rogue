package archrogue

// MX-story deterministic corpus. This is the raylib-free, typed Odin port of
// pygame 5.2.1's content/story_corpus.py. Literal prose is content; gameplay
// code keys everything by compact IDs so edits to displayed text never change
// saves, deterministic generation, or authored asset lookup.

STORY_CHAPTERS_PER_ARC       :: 3
STORY_GUEST_VARIANTS         :: 3
STORY_BEAT_COUNT             :: DUNGEON_DEPTH
STORY_CHOICE_COUNT           :: 3
STORY_OMEN_ASSET_COUNT       :: 8
STORY_GUEST_ASSET_COUNT      :: 10
STORY_ENDING_ASSET_COUNT     :: 15
STORY_RELIC_ASSET_COUNT      :: 10
STORY_PORTRAIT_ASSET_COUNT   :: 30

Story_Choice_Verb :: enum u8 {
	Aid,
	Bargain,
	Defy,
}

Story_Resolution :: enum u8 {
	Unresolved,
	Aid,
	Bargain,
	Defy,
	Unanswered,
}

Story_Road :: enum u8 {
	Unwritten,
	Witness,
	Debtor,
	Defiant,
	Forsaken,
}

Story_True_Name :: enum u8 {
	Sorn,
	Liss,
}

Story_Effect_Id :: enum u8 {
	Enemy_Pressure,
	Loot_Bonus,
	Trap_Bonus,
	Shrine_Bonus,
	Secret_Bonus,
	Curse_Bonus,
	XP_Bonus,
	Boss_Pressure,
	Damage_Resist,
	Healing_Echo,
	Relic_Power,
	Blood_Price,
	Damage_Bonus,
	Hunter_Pressure,
}

Story_Effects :: [Story_Effect_Id]f32

Story_Choice_Tag :: enum u8 {
	Mercy,
	Witness,
	Bargain,
	Marked,
	Defiance,
	Wrath,
}

Story_Faction_Id :: enum u8 {
	Choir_Of_The_Hollow_Star,
	Ember_Monks_Of_Khar,
	Drowned_Lineage,
	Thorn_Brides_Of_Edda,
	Voss_Mortuary_Guild,
	Order_Of_The_Black_Pulley,
	Pale_Antler_Court,
	Scriptorium_Of_Worms,
}

Story_Relic_Id :: enum u8 {
	Asterion_Nail,
	Mire_Saints_Bell,
	Lantern_Of_Unburied_Roads,
	Crown_Of_Antlers_And_Teeth,
	Mirror_Psalter,
	Cinder_Key_Of_Khar,
	Wormscript_Map,
	Vessel_Of_Last_Rain,
	Oath_Eaters_Chain,
	Heartseed_Reliquary,
}

Story_Guest_Role_Id :: enum u8 {
	Oathless_Knight,
	Grave_Witch,
	Drowned_Heir,
	Ash_Pilgrim,
	Mirror_Scribe,
	Antlered_Hunter,
	Mortuary_Broker,
	Lost_Cartographer,
	Bone_Mender,
	Furnace_Heretic,
}

Story_Dilemma_Id :: enum u8 {
	Door_That_Remembers,
	Debt_Lantern,
	Name_In_The_Wall,
	Hungry_Reliquary,
	Witness_Below,
	False_Sanctuary,
	Coin_Eyed_Corpse,
	Beast_In_Prayer,
	Broken_Map,
	Gates_Confession,
	Choir_Without_Throats,
	Last_Guests_Mask,
}

// Ordering intentionally matches THEMES, making the floor plan's theme index
// a checked cast at the later integration seam rather than a string lookup.
Story_Motif_Id :: enum u8 {
	Crypt_Of_Ash,
	Fungal_Catacombs,
	Violet_Reliquary,
	Sunken_Bastion,
	Frozen_Ossuary,
	Obsidian_Foundry,
	Moonlit_Aquifer,
	Thornbound_Vault,
}

Story_Tether_Stage :: enum u8 {
	Meet,
	Reveal,
	Crisis,
}

Story_Arc :: struct {
	wound:    string,
	oath:     string,
	secret:   string,
	chapters: [STORY_CHAPTERS_PER_ARC]string,
}

Story_Faction :: struct {
	name:       string,
	epithet:    string,
	agenda:     string,
	taboo:      string,
	color:      [4]u8,
	orbit_role: Story_Guest_Role_Id,
	has_orbit:  bool,
}

Story_Relic :: struct {
	name:       string,
	form:       string,
	temptation: string,
	doom:       string,
	slug:       string,
}

Story_Guest_Pair :: struct {
	motive: string,
	speech: string,
}

Story_Guest_Template :: struct {
	role:       string,
	role_lower: string,
	slug:       string,
	names:      [STORY_GUEST_VARIANTS]string,
	name_slugs: [STORY_GUEST_VARIANTS]string,
	voice:      string,
	pairs:      [STORY_GUEST_VARIANTS]Story_Guest_Pair,
}

Story_Dilemma :: struct {
	title:    string,
	setup:    string,
	intents:  [Story_Choice_Verb]string,
	outcomes: [Story_Choice_Verb]string,
	truth:    string,
}

Story_Motif :: struct {
	theme_name: string,
	image:      string,
	danger:     string,
	slug:       string,
}

Story_Tether_Beat :: struct {
	motive: string,
	speech: string,
}

Story_Crisis_Choice :: struct {
	intent:  string,
	outcome: string,
}

Story_Tether :: struct {
	role:           Story_Guest_Role_Id,
	name:           string,
	beats:          [Story_Tether_Stage]Story_Tether_Beat,
	crisis_choices: [Story_Choice_Verb]Story_Crisis_Choice,
}

Story_Ending :: struct {
	title: string,
	body:  string,
	slug:  string,
}

Story_Gate_Choice :: struct {
	label:  string,
	detail: string,
}

@(rodata)
STORY_CHOICE_KEYS := [Story_Choice_Verb]string{
	.Aid = "aid", .Bargain = "bargain", .Defy = "defy",
}

@(rodata)
STORY_CHOICE_LABELS := [Story_Choice_Verb]string{
	.Aid = "Aid", .Bargain = "Bargain", .Defy = "Defy",
}

@(rodata)
STORY_CHOICE_TAG_NAMES := [Story_Choice_Tag]string{
	.Mercy = "mercy", .Witness = "witness", .Bargain = "bargain",
	.Marked = "marked", .Defiance = "defiance", .Wrath = "wrath",
}

@(rodata)
STORY_ROAD_KEYS := [Story_Road]string{
	.Unwritten = "unwritten", .Witness = "witness", .Debtor = "debtor",
	.Defiant = "defiant", .Forsaken = "forsaken",
}

@(rodata)
STORY_TRUE_NAME_KEYS := [Story_True_Name]string{
	.Sorn = "sorn", .Liss = "liss",
}

@(rodata)
STORY_ARCS := [Archetype_Id]Story_Arc{
	.Warden = {
		wound = "You opened one door out of mercy, and a city paid the toll.",
		oath = "Guard the living from bargains made at sealed doors.",
		secret = "The pilgrim wore your family's signet; the door opened for your name, not your mercy.",
		chapters = {"Last Shield of Kasar Voss", "Iron Oath Exile", "Gravewatch Captain"},
	},
	.Rogue = {
		wound = "You were sold before you were born; even your death has an owner.",
		oath = "Steal back what was never theirs to sell.",
		secret = "The deed is written in your blood, dated before your birth. The buyer waits below.",
		chapters = {"Blackroof Orphan", "Knife of the Lantern Court", "Grinning Gallowsblade"},
	},
	.Arcanist = {
		wound = "You proved the last seal could dream itself open, and it will not stop being true.",
		oath = "Write the counter-sigil before the proof completes itself.",
		secret = "You are the last complete copy. Unwriting the proof unwrites you.",
		chapters = {"Scholar of the Ninth Seal", "Star-Ash Savant", "Runebound Fugitive"},
	},
	.Acolyte = {
		wound = "Your bell rang a day early, and the plague's only death is a child no one buried.",
		oath = "Finish the Child's death right: name said, grief kept, one bell rung true.",
		secret = "The bell tolls softly when you lie -- and one sin in your blood knows the Tyrant's name.",
		chapters = {"Bell-Keeper of Saint Mire", "Ashen Confessor", "Gravetongue Novice"},
	},
	.Ranger = {
		wound = "Your captain vanished into a beast the law says you must kill.",
		oath = "Finish the hunt without the kill the clan demands.",
		secret = "The compass points at your heartbeat. The Stag is not fleeing you -- it follows.",
		chapters = {"Thornroad Outrider", "Moon-Hunt Exile", "Wildermark Cartographer"},
	},
}

@(rodata)
STORY_FACTIONS := [Story_Faction_Id]Story_Faction{
	.Choir_Of_The_Hollow_Star = {
		name = "Choir of the Hollow Star", epithet = "starless chanters",
		agenda = "sing the Last Gate open and pay the toll in names",
		taboo = "they cannot speak a true name without losing a memory",
		color = {160, 86, 230, 255},
	},
	.Ember_Monks_Of_Khar = {
		name = "Ember Monks of Khar", epithet = "ash-scarred ascetics",
		agenda = "burn souls clean enough to cross, one guilt at a time",
		taboo = "water blessed by moonlight burns them like acid",
		color = {245, 104, 52, 255}, orbit_role = .Ash_Pilgrim, has_orbit = true,
	},
	.Drowned_Lineage = {
		name = "Drowned Lineage", epithet = "blue-lipped heirs",
		agenda = "flood every oath until the water rises home",
		taboo = "they must answer any question asked beside still water",
		color = {86, 188, 215, 255}, orbit_role = .Drowned_Heir, has_orbit = true,
	},
	.Thorn_Brides_Of_Edda = {
		name = "Thorn Brides of Edda", epithet = "root-veiled witches",
		agenda = "wed their bloodline to the Gate and inherit the door",
		taboo = "iron wedding rings silence their glamour",
		color = {126, 214, 92, 255}, orbit_role = .Grave_Witch, has_orbit = true,
	},
	.Voss_Mortuary_Guild = {
		name = "Voss Mortuary Guild", epithet = "coin-eyed undertakers",
		agenda = "own every death in the city before it finishes",
		taboo = "they cannot refuse a properly witnessed debt",
		color = {190, 130, 215, 255}, orbit_role = .Mortuary_Broker, has_orbit = true,
	},
	.Order_Of_The_Black_Pulley = {
		name = "Order of the Black Pulley", epithet = "engine-priests",
		agenda = "raise the sunken city back to heaven, chain by chain",
		taboo = "their machines stall when fed unmarked bones",
		color = {245, 132, 72, 255}, orbit_role = .Furnace_Heretic, has_orbit = true,
	},
	.Pale_Antler_Court = {
		name = "Pale Antler Court", epithet = "moon-crowned hunters",
		agenda = "hunt every soul that slipped the Toll-Keeper's count",
		taboo = "they cannot cross a threshold swept with grave salt",
		color = {145, 184, 232, 255}, orbit_role = .Antlered_Hunter, has_orbit = true,
	},
	.Scriptorium_Of_Worms = {
		name = "Scriptorium of Worms", epithet = "carrion archivists",
		agenda = "write every possible ending before one can happen",
		taboo = "fresh ink binds them more tightly than chains",
		color = {144, 172, 86, 255}, orbit_role = .Mirror_Scribe, has_orbit = true,
	},
}

@(rodata)
STORY_RELICS := [Story_Relic_Id]Story_Relic{
	.Asterion_Nail = {
		name = "Asterion Nail", form = "a black iron spike that hums when gates lie",
		temptation = "it can pin one fate in place if fed a willing memory",
		doom = "each use makes the dungeon remember you more clearly", slug = "asterion_nail",
	},
	.Mire_Saints_Bell = {
		name = "Mire-Saint's Bell", form = "a handbell cast from coffin silver and plague glass",
		temptation = "it absolves wounds by moving them into someone nearby",
		doom = "the bell eventually tolls for its bearer first", slug = "mire_saints_bell",
	},
	.Lantern_Of_Unburied_Roads = {
		name = "Lantern of Unburied Roads", form = "a hooded lamp filled with ash instead of oil",
		temptation = "it reveals shortcuts that were paid for with betrayals",
		doom = "every revealed path erases a safer road elsewhere", slug = "lantern_of_unburied_roads",
	},
	.Crown_Of_Antlers_And_Teeth = {
		name = "Crown of Antlers and Teeth", form = "a pale crown that grows warm near frightened monsters",
		temptation = "it lets prey command predators for a single heartbeat",
		doom = "the command always returns as a debt", slug = "crown_of_antlers_and_teeth",
	},
	.Mirror_Psalter = {
		name = "Mirror Psalter", form = "a prayer book whose pages reflect possible sins",
		temptation = "it can identify curses before they take hold",
		doom = "the owner becomes legible to every watcher below", slug = "mirror_psalter",
	},
	.Cinder_Key_Of_Khar = {
		name = "Cinder-Key of Khar", form = "a furnace key with a living ember in its bow",
		temptation = "it opens sealed armories and burns away old cowardice",
		doom = "locks opened by the key demand blood from later doors", slug = "cinder_key_of_khar",
	},
	.Wormscript_Map = {
		name = "Wormscript Map", form = "a vellum map tattooed by blind grave-worms",
		temptation = "it predicts which rooms hunger for guests or graves",
		doom = "the map adds rooms whenever the bearer hesitates", slug = "wormscript_map",
	},
	.Vessel_Of_Last_Rain = {
		name = "Vessel of Last Rain", form = "a cracked urn of water from a drowned coronation",
		temptation = "it cools rage and weakens firebound tyrants",
		doom = "spilled drops call drowned witnesses from hidden floors", slug = "vessel_of_last_rain",
	},
	.Oath_Eaters_Chain = {
		name = "Oath-Eater's Chain", form = "a hooked chain that tightens around spoken promises",
		temptation = "it turns broken vows into armor for one battle",
		doom = "a kept vow becomes heavier with every floor", slug = "oath_eaters_chain",
	},
	.Heartseed_Reliquary = {
		name = "Heartseed Reliquary", form = "a thorned seedcase pulsing like a second heart",
		temptation = "it can grow sanctuary where no shrine should answer",
		doom = "sanctuary roots also feed the dungeon's oldest bride", slug = "heartseed_reliquary",
	},
}

@(rodata)
STORY_GUEST_TEMPLATES := [Story_Guest_Role_Id]Story_Guest_Template{
	.Oathless_Knight = {
		role = "Oathless Knight", role_lower = "oathless knight", slug = "oathless_knight",
		names = {"Ser Caldus", "Dame Vey", "Rook of Voss"},
		name_slugs = {"ser_caldus", "dame_vey", "rook_of_voss"},
		voice = "iron-clipped and formal",
		pairs = {
			{"asks a witness before a vow breaks", "'I kept one vow: stay alive until witnessed. It weighs more than the nine I broke -- watch, and I can finally set it down.'"},
			{"guards a door that no longer exists", "'The door fell years ago. My watch did not -- an oath outlives its object down here, and mine will not release me.'"},
			{"weighs mercy against cowardice", "'Tell me plainly: is mercy a shield, or a hole in one? I spared a man once, and a city drowned behind him.'"},
		},
	},
	.Grave_Witch = {
		role = "Grave-Witch", role_lower = "grave-witch", slug = "grave_witch",
		names = {"Mother Hush", "Edda Crowmilk", "Vespera Thorne"},
		name_slugs = {"mother_hush", "edda_crowmilk", "vespera_thorne"},
		voice = "tender, cruel, and amused",
		pairs = {
			{"plants living secrets in dead soil", "'Plant this secret in dead soil, love, and I'll owe you a warm grave. Buried truths keep the dead from digging for them.'"},
			{"sells shelter for a future grief", "'Shelter's cheap: one grief you haven't had yet. I collect sorrows before they happen -- they keep better that way.'"},
			{"knows who the relic chose next", "'The relic already chose its next keeper. Look how it leans toward you, like a child picking a parent.'"},
		},
	},
	.Drowned_Heir = {
		role = "Drowned Heir", role_lower = "drowned heir", slug = "drowned_heir",
		names = {"Prince Nerian", "Lysa Underwave", "The Blue-Lipped Child"},
		name_slugs = {"prince_nerian", "lysa_underwave", "blue_lipped_child"},
		voice = "soft as water in a crypt",
		pairs = {
			{"begs one remembered coronation song", "'Sing the coronation song. Any verse. My family drowned mid-crowning, and no one has finished the ceremony since.'"},
			{"pleads for kin wearing old coins", "'Spare the ones wearing my family's coins. They drowned honest, and the Gate still owes them a hearing.'"},
			{"carries a map of tidewater and bone", "'My map is tidewater and bone dust. The drowned drew it going down -- it knows every door the water took.'"},
		},
	},
	.Ash_Pilgrim = {
		role = "Ash Pilgrim", role_lower = "ash pilgrim", slug = "ash_pilgrim",
		names = {"Harl the Sooted", "Sister Kharra", "Old Ember Jesk"},
		name_slugs = {"harl_the_sooted", "sister_kharra", "old_ember_jesk"},
		voice = "dry, hoarse, and patient",
		pairs = {
			{"carries flame to a shrine that hates fire", "'Carry my flame to the shrine that hates fire. The monks say guilt burns clean; the shrine has never once agreed.'"},
			{"trades scars for foundry directions", "'Scars for directions -- the foundry rate. Every burn on me is a turn in the road below, mapped in lasting ink.'"},
			{"knows the one guilt the gate can't digest", "'The Man Below can't digest one guilt: his own. Feed it to him and watch the gate hinge loosen.'"},
		},
	},
	.Mirror_Scribe = {
		role = "Mirror-Scribe", role_lower = "mirror-scribe", slug = "mirror_scribe",
		names = {"Tallow Quill", "Iosef of the Glass", "Nim Rue"},
		name_slugs = {"tallow_quill", "iosef_of_the_glass", "nim_rue"},
		voice = "precise and frightened",
		pairs = {
			{"records the yous that chose worse", "'I've recorded the yous that chose worse. Care to stay ahead of them? The margin between you is thinner tonight.'"},
			{"erases omens for the price of certainty", "'One omen, erased, for the price of your certainty. The Worms let us unwrite the future, never the doubt.'"},
			{"needs a signature before the Worms notice", "'Sign before the Worms notice. They always notice -- an unsigned page is the only crime they hang scribes for.'"},
		},
	},
	.Antlered_Hunter = {
		role = "Antlered Hunter", role_lower = "antlered hunter", slug = "antlered_hunter",
		names = {"Mael Whitehorn", "The Quiet Hart", "Sable of the Moon-Hunt"},
		name_slugs = {"mael_whitehorn", "quiet_hart", "sable_of_the_moon_hunt"},
		voice = "low, watchful, and direct",
		pairs = {
			{"tracks a beast wearing human prayers", "'The beast wears human prayers now. That's past my writ -- the Court hunts escaped souls, not believers.'"},
			{"guides those who spare the marked", "'Spare the marked one and I'll walk you true. The mark only means it slipped the Toll-Keeper's count.'"},
			{"smells where your story ends", "'Your story is on the wind, roadless. I can smell where it ends -- down deep, by a door that will not open.'"},
		},
	},
	.Mortuary_Broker = {
		role = "Mortuary Broker", role_lower = "mortuary broker", slug = "mortuary_broker",
		names = {"Coin-Eye Pell", "Madam Nacre", "Voss Factor Ilm"},
		name_slugs = {"coin_eye_pell", "madam_nacre", "voss_factor_ilm"},
		voice = "courteous enough to be dangerous",
		pairs = {
			{"sells unfinished deaths in bronze tubes", "'Unfinished deaths, bronze-sealed. Estate prices -- the Guild bought them cheap when the city drowned mid-breath.'"},
			{"auctions one of your future wounds", "'Consent to auction one future wound, and we both eat this month. Pain sells best before it happens.'"},
			{"knows who bought the gate's silence", "'I know who bought the gate's silence: the man behind it. He pays the Guild yearly to keep his ledger shut.'"},
		},
	},
	.Lost_Cartographer = {
		role = "Lost Cartographer", role_lower = "lost cartographer", slug = "lost_cartographer",
		names = {"Ammar Without Roads", "Fen Chalkhand", "Sella of the Fold"},
		name_slugs = {"ammar_without_roads", "fen_chalkhand", "sella_of_the_fold"},
		voice = "rushed and ink-stained",
		pairs = {
			{"has mapped a floor that isn't yet", "'This floor doesn't exist yet -- I've mapped it anyway. The dungeon reads my drafts and builds to spec when flattered.'"},
			{"unmaps one room that shouldn't exist", "'Choose one room that should never exist. I'll unmap it, and the dungeon will pretend it never meant to.'"},
			{"angers walls until they show secrets", "'Anger the walls and secrets show. Voss masons hid their shame behind plaster; the stones still flinch when accused.'"},
		},
	},
	.Bone_Mender = {
		role = "Bone-Mender", role_lower = "bone-mender", slug = "bone_mender",
		names = {"Saint-Not-Yet", "Mara Sutured", "Kell of White Thread"},
		name_slugs = {"saint_not_yet", "mara_sutured", "kell_of_white_thread"},
		voice = "kind, exhausted, and unblinking",
		pairs = {
			{"stitches wounds into willing ghosts", "'Wounds stitch into willing ghosts -- mine volunteer. The dead here queue for one last useful thing to do.'"},
			{"asks a monster bone for sanctuary", "'One monster bone buys sanctuary. The dead protect whoever brings proof the monsters can die.'"},
			{"recognizes an old injury of yours", "'I've sutured this wound before. On you -- in a life the Ledger says you haven't led yet. Hold still.'"},
		},
	},
	.Furnace_Heretic = {
		role = "Furnace Heretic", role_lower = "furnace heretic", slug = "furnace_heretic",
		names = {"Brass-Thumb Oren", "Malk the Quenched", "Devra Cogprayer"},
		name_slugs = {"brass_thumb_oren", "malk_the_quenched", "devra_cogprayer"},
		voice = "half-mad with relief",
		pairs = {
			{"hears the machine he broke praying", "'I broke the sacred machine and now it prays to me. The Pulley built engines to reach heaven; mine got homesick.'"},
			{"sells the weak points of constructs", "'Spare me from the order and I'll show you where constructs rust. Even the Sentinel has a seam its founders regretted.'"},
			{"offers fuel that improves loot and traps", "'Forbidden fuel: better loot, worse traps. The dungeon burns brighter when you feed it what it's not allowed.'"},
		},
	},
}

@(rodata)
STORY_DILEMMAS := [Story_Dilemma_Id]Story_Dilemma{
	.Door_That_Remembers = {
		title = "The Door That Remembers", setup = "a sealed door repeats the worst night you carry",
		intents = {.Aid = "bear witness and leave it shut", .Bargain = "feed it a lesser secret", .Defy = "break the hinge"},
		outcomes = {.Aid = "The door keeps your mercy; nearby patrols quiet.", .Bargain = "It opens on valuables and a sharper curse.", .Defy = "The broken hinge rings through the barracks below."},
		truth = "The dungeon stages old wounds to learn what you protect; whatever you feed it, it builds more of.",
	},
	.Debt_Lantern = {
		title = "The Debt Lantern", setup = "a lantern burns with a stranger's unpaid death",
		intents = {.Aid = "carry the light to a shrine", .Bargain = "sell an hour of your future", .Defy = "snuff it out"},
		outcomes = {.Aid = "The light marks safer sanctuaries ahead.", .Bargain = "The flame pays in loot and hungrier traps.", .Defy = "The dark teaches your enemies fear -- and you."},
		truth = "A death nobody paid for keeps burning; how you treat it decides which rooms open ahead.",
	},
	.Name_In_The_Wall = {
		title = "The Name in the Wall", setup = "your name is carved fresh beside much older ones",
		intents = {.Aid = "scratch out the newest wound", .Bargain = "trade the name for an omen", .Defy = "leave your blade in the wall"},
		outcomes = {.Aid = "The wall forgets one danger; caches show themselves.", .Bargain = "The omen fattens rewards and sweetens curses.", .Defy = "The insult draws champions with better spoils."},
		truth = "The wall lists everyone the Gate is still owed; fresh carving means you are on this floor's bill.",
	},
	.Hungry_Reliquary = {
		title = "The Hungry Reliquary", setup = "the relic's echo demands proof you still choose freely",
		intents = {.Aid = "refuse it and comfort the guest", .Bargain = "feed it one drop of blood", .Defy = "command it to obey"},
		outcomes = {.Aid = "Gratitude bends the next shrines toward you.", .Bargain = "The blood opens a rich and dangerous route.", .Defy = "The relic recoils and wakes oathbound hunters."},
		truth = "Relics test their bearers: prove you choose freely and it serves, falter and it starts choosing for you.",
	},
	.Witness_Below = {
		title = "The Witness Below", setup = "a dying stranger holds one truth about the Man Below",
		intents = {.Aid = "ease their passing", .Bargain = "ask the truth's price", .Defy = "force the name out"},
		outcomes = {.Aid = "Their blessing softens the next floor.", .Bargain = "Their price buys loot and leaves a curse-scent.", .Defy = "The stolen truth emboldens you -- and is heard."},
		truth = "The Toll-Keeper was a man once, and this stranger watched him refuse the Gate. Truth like that has a price.",
	},
	.False_Sanctuary = {
		title = "The False Sanctuary", setup = "a safe room is staged one comfort too perfectly",
		intents = {.Aid = "warn the guest away", .Bargain = "take what comfort you can", .Defy = "tear down every charm"},
		outcomes = {.Aid = "Real sanctuary answers your restraint.", .Bargain = "The false room pays in gear and hidden needles.", .Defy = "The angry walls reveal the foes they hid."},
		truth = "The dungeon builds traps out of comfort; a room this kind is asking for something in return.",
	},
	.Coin_Eyed_Corpse = {
		title = "The Coin-Eyed Corpse", setup = "a corpse offers coins for a death you haven't suffered",
		intents = {.Aid = "bury the coins with it", .Bargain = "take the coins and the mark", .Defy = "melt them into a challenge"},
		outcomes = {.Aid = "Burial draws helpful dead and quiet rooms.", .Bargain = "Marked coin buys rare finds and rash bargains.", .Defy = "The token calls elites to meet you openly."},
		truth = "The Mortuary Guild pays in advance for deaths it expects to collect; taking the coin signs the order.",
	},
	.Beast_In_Prayer = {
		title = "The Beast in Prayer", setup = "a monster kneels, praying in a tongue you know",
		intents = {.Aid = "spare it and learn what it fears", .Bargain = "bind it with the relic's hunger", .Defy = "kill the prayer mid-verse"},
		outcomes = {.Aid = "Its fear maps secret paths; pursuit thins.", .Bargain = "The binding pays now and stains later choices.", .Defy = "Its kin arrive angry, carrying better spoils."},
		truth = "Some monsters here are only unfinished people; this one still remembers the words said over its grave.",
	},
	.Broken_Map = {
		title = "The Broken Map", setup = "a torn map shows two roads down and one missing witness",
		intents = {.Aid = "take the road that saves the witness", .Bargain = "take the road with treasure teeth", .Defy = "burn the map and trust your feet"},
		outcomes = {.Aid = "The saved witness tips shrines and secrets your way.", .Bargain = "The toothed road enriches caches and trapwork.", .Defy = "The floor turns hostile but predictable."},
		truth = "Both roads go down; the map only asks what you will spend getting there -- a stranger, or your certainty.",
	},
	.Gates_Confession = {
		title = "The Gate's Confession", setup = "the Man Below borrows a mouth and offers a smaller ending",
		intents = {.Aid = "refuse him for the guest's sake", .Bargain = "take the power, keep the run", .Defy = "mock him until he names himself"},
		outcomes = {.Aid = "The refusal keeps what is yours, yours.", .Bargain = "The gift is strong, cursed, and remembered.", .Defy = "His pride cracks; his true name slips out."},
		truth = "He offers small endings so no one reaches the big one; every taker feeds his door another year.",
	},
	.Choir_Without_Throats = {
		title = "The Choir Without Throats", setup = "unseen singers chant a verse built from your lost chances",
		intents = {.Aid = "answer with silence", .Bargain = "answer with a secret refrain", .Defy = "answer with steel on stone"},
		outcomes = {.Aid = "Silence calms the floor; quiet help appears.", .Bargain = "The refrain buys occult reward, echoed in traps.", .Defy = "The broken verse calls armed witnesses."},
		truth = "The Choir sings with the voices of those who never chose; answer wrongly and yours joins the verse.",
	},
	.Last_Guests_Mask = {
		title = "The Last Guest's Mask", setup = "a face flickers between friend, foe, and your reflection",
		intents = {.Aid = "offer trust, guard high", .Bargain = "ask which face profits", .Defy = "shatter the mask"},
		outcomes = {.Aid = "Trust steadies allies; patrols lose their nerve.", .Bargain = "Profit sharpens loot, curses, and costs.", .Defy = "The shards anger elites and hurry the truth."},
		truth = "The dungeon wears faces to learn yours; what you show it now, it will send against you later.",
	},
}

@(rodata)
STORY_MOTIFS := [Story_Motif_Id]Story_Motif{
	.Crypt_Of_Ash = {"Crypt of Ash", "charcoal saints and kneeling smoke", "ember-debts", "crypt_of_ash"},
	.Fungal_Catacombs = {"Fungal Catacombs", "pale caps growing from forgotten vows", "spore dreams", "fungal_catacombs"},
	.Violet_Reliquary = {"Violet Reliquary", "void glass humming around chained relics", "astral hunger", "violet_reliquary"},
	.Sunken_Bastion = {"Sunken Bastion", "drowned banners drifting in still air", "oath-floods", "sunken_bastion"},
	.Frozen_Ossuary = {"Frozen Ossuary", "blue bone vaults and frost-bitten prayers", "rime silence", "frozen_ossuary"},
	.Obsidian_Foundry = {"Obsidian Foundry", "molten gears stamping names into iron", "furnace law", "obsidian_foundry"},
	.Moonlit_Aquifer = {"Moonlit Aquifer", "silver wells reflecting wrong moons", "tide omens", "moonlit_aquifer"},
	.Thornbound_Vault = {"Thornbound Vault", "root-split altars and wedding thorns", "green hunger", "thornbound_vault"},
}

@(rodata)
STORY_TETHERS := [Archetype_Id]Story_Tether{
	.Warden = {
		role = .Oathless_Knight, name = "Ser Caldus",
		beats = {
			.Meet = {"seeks the warden who opened the door", "'You opened the door. I am what came through -- the pilgrim, the signet, all of it. Shall we walk a while before we speak of that night?'"},
			.Reveal = {"carries what came through that night", "'The door knew your signet, Warden -- your house bought passage generations ago. You blamed the softest thing in the room, and it was never the mercy.'"},
			.Crisis = {"asks a witness before his last vow breaks", "'One vow left: stay alive until witnessed. You guard the living, I know -- but witness me, and I am finally allowed to stop.'"},
		},
		crisis_choices = {
			.Aid = {"witness his last vow break", "He kneels, finishes, and is finally done carrying."},
			.Bargain = {"take his vow onto yourself", "He lives, unburdened; you carry two oaths now."},
			.Defy = {"refuse him the death", "He lives, unfinished -- and stubborn enough to follow."},
		},
	},
	.Rogue = {
		role = .Mortuary_Broker, name = "Coin-Eye Pell",
		beats = {
			.Meet = {"recognizes an old lot number", "'Well. The lot number walks. I brokered your sale, dear customer -- browse freely, everything here is second-hand, including the guilt.'"},
			.Reveal = {"keeps the bill of your sale", "'The bill of sale: one name, one roof, a hundred children kept dry. The Blackroof sold you to buy itself -- bad trade, kind arithmetic.'"},
			.Crisis = {"opens the counter one last time", "'The deed is in reach and my counter is open one last time. Fire, purchase, or statement -- I profit least from the one I'd respect most.'"},
		},
		crisis_choices = {
			.Aid = {"burn the whole deed-book", "Every sold death voids; Pell holds the light for you."},
			.Bargain = {"buy your death back honest", "Paid in full -- the first thing you ever owned."},
			.Defy = {"pin the deed, unsigned", "Let him keep a death that keeps its own hours."},
		},
	},
	.Arcanist = {
		role = .Mirror_Scribe, name = "Nim Rue",
		beats = {
			.Meet = {"files a familiar hand", "'I file your handwriting every week -- the confiscated proof, all of it. It's a good hand. Don't tell the Worms I keep reading it.'"},
			.Reveal = {"holds the page with your name", "'One page, two entries: your erased name, your living proof. The Worms only ever sell half a page -- choose which half stays theirs.'"},
			.Crisis = {"faces the Worms' audit", "'They're auditing my margins. Sympathy, they call it -- I wrote that I hoped you'd live. Please be quick; corrections here are eaten.'"},
		},
		crisis_choices = {
			.Aid = {"claim her notes as your hand", "You forge yourself; Rue is spared, you go unrecorded."},
			.Bargain = {"buy her desk with the proof", "Rue is promoted to safety; the Worms hold a copy."},
			.Defy = {"burn the audit itself", "Rue is expelled -- and walks with you, unsupervised."},
		},
	},
	.Acolyte = {
		role = .Drowned_Heir, name = "The Blue-Lipped Child",
		beats = {
			.Meet = {"answered the wrong bell", "'You rang my bell. I came. Was that wrong? I lived in your tower, keeper -- you warned every door in town except ours.'"},
			.Reveal = {"waits by a rope still swaying", "'It's a good bell. It was early, not wrong -- the plague was already sleeping down here when it rang. It only ever lied about you.'"},
			.Crisis = {"asks for a grave and a name", "'Bury me here, or at the door? A foundling needs a name said over the grave, and nobody ever gave me one. Do you have a spare?'"},
		},
		crisis_choices = {
			.Aid = {"give the Child your own name", "Named with yours, the Child passes; you walk on nameless."},
			.Bargain = {"carry them to the door", "The Child holds your hand for the last floor."},
			.Defy = {"refuse the grave", "You keep the Child; even they know it's the bell you spare."},
		},
	},
	.Ranger = {
		role = .Antlered_Hunter, name = "Sable of the Moon-Hunt",
		beats = {
			.Meet = {"arrives one room late, on purpose", "'Two writs: the stag, and the one who spared it. That's you, roadless. I keep miscounting on purpose -- explain the stag before I stop.'"},
			.Reveal = {"carries two writs she won't read", "'The mark isn't mercy, it's bookkeeping -- your captain slipped the Toll-Keeper's count, and the Court wants the tally clean. You saw that. That's worse.'"},
			.Crisis = {"counts the last hunt aloud", "'It stopped running. It waits for you, and your captain waits inside it. Loose the arrow or lower the bow -- the law only needs one of us satisfied.'"},
		},
		crisis_choices = {
			.Aid = {"speak the captain's name", "The soul unseats; a plain stag walks away. No arrows."},
			.Bargain = {"carry the soul yourself", "You carry the captain now; Sable walks escort."},
			.Defy = {"put the arrow through the writ", "The Moon-Hunt is two people now. Walk faster."},
		},
	},
}

@(rodata)
STORY_TYRANT_OFFERS := [Archetype_Id]string{
	.Warden = "'The night, returned. The door, shut. You, blameless -- Kasar Voss standing, every soul asleep in a city that never drowned. I ask so little: that nothing ends, theirs included.'",
	.Rogue = "'One page, torn out. Yours. The book stays, but you walk up whole, unowned, amended -- no guild, no gallows, no buyer. The others never knew their deeds existed.'",
	.Arcanist = "'Stay. The proof in your bones can never open my door if you never end -- and here, no one ends. Call it tenure: eternity to be right, with no one left to argue.'",
	.Acolyte = "'One bell, unrung. One town, unbroken. One child -- unasked-for. Only you would remember them, keeper, and memory is a lighter grave than the one you are digging.'",
	.Ranger = "'The road home, redrawn. The patrol rides back, captain in front, and the stag was never marked. It costs only the refusal -- the one moment of you that ever mattered.'",
}

@(rodata)
STORY_ROAD_LINES := [Story_Road]string{
	.Unwritten = "",
	.Witness = "The rooms lean kinder toward your mercies.",
	.Debtor = "The rooms have learned to name their prices.",
	.Defiant = "The rooms brace and hide their throats.",
	.Forsaken = "The rooms have stopped speaking to you.",
}

@(rodata)
STORY_RUE_DEATH_LINES := [Story_Road]string{
	.Witness = "Entry closed. It was a kind one. I'm leaving the margin open.",
	.Debtor = "Entry closed. Accounts outstanding. I'm leaving the margin open.",
	.Defiant = "Entry closed mid-sentence. I'm leaving the margin open.",
	.Forsaken = "Entry closed. No witnesses listed. The margin stays open anyway.",
	.Unwritten = "Entry closed. ...I'm leaving the margin open.",
}

@(rodata)
STORY_ENDINGS := [Archetype_Id][Story_Choice_Verb]Story_Ending{
	.Warden = {
		.Aid = {"The Held Door", "The Warden opens the Last Gate and holds it, shield lowered, while the city ends past him in procession. A shield is not a wall. It never was. The Warden holds the door -- open, this time.", "the_held_door"},
		.Bargain = {"The Fair Scale", "Someone must weigh what passes; better someone who knows what refusing costs. The Warden takes the Toll-Keeper's seat, and the scales are honest. They feel light today. They feel lighter every day.", "the_fair_scale"},
		.Defy = {"No More Doors", "The Gate breaks. No tolls, no thresholds -- the Unfinished drift up toward the living sky, and the living will learn to live with ghosts. Nothing left to guard. Everything left to shepherd.", "no_more_doors"},
	},
	.Rogue = {
		.Aid = {"The Emptied Market", "The whole deed-book goes through the Gate. Every sold death finishes; the market dies overnight. You stole one thing from everyone at once: the price tag. No one owns anyone tonight.", "the_emptied_market"},
		.Bargain = {"The Honest Purchase", "You pay what a name is worth -- the shadow, the alias, the whole disguise -- and walk up carrying only the name. Finally yours. First thing you ever owned. Wear it out.", "the_honest_purchase"},
		.Defy = {"The Standing Debt", "No deal. The deed stays pinned to the barred Gate with a good knife. Somewhere below, a death waits for an owner who will not come to collect. You've decided to live forever -- out of spite.", "the_standing_debt"},
	},
	.Arcanist = {
		.Aid = {"The Answered Proof", "At the open Gate you speak the counter-sigil into the dream. The proof completes, and concludes, and stops being true. The bones go quiet. Above, the black gap in the sky lets one star back in. Nobody will know it was you. That was the proof all along.", "the_answered_proof"},
		.Bargain = {"The Restored Name", "Rue writes your name into the Ledger's first page. The Worms' fee: the proof stands, unanswered. You are cited, titled, real. Some nights you feel the door turn over in its sleep, in your bones.", "the_restored_name"},
		.Defy = {"The Standing Argument", "You let the proof finish -- and step into the opening seal to argue with what it finds. The seal dreams a door; you dream a wall; the debate does not end. You were right. Being right, it turns out, is a place. You live there now.", "the_standing_argument"},
	},
	.Acolyte = {
		.Aid = {"The True Funeral", "The Gate opens and the tenth bell rings as a funeral bell -- the rite, at last, at the right time. The Child passes, named. The plague loses its seed. Far above, the bell of Saint Mire rings once, true, by itself, over an empty town.", "the_true_funeral"},
		.Bargain = {"The Returned Confession", "You give him back every sin he confessed. Un-absolved, weighed at last, the Toll-Keeper can finally end. Someone must hear confessions at the door now; the dead vote for you, unanimously. First in line: everyone.", "the_returned_confession"},
		.Defy = {"The Broken Bell", "You break the great bell of the Gate. No death will ever again arrive announced -- every ending honest, sudden, unforetold, forever. The Child laughs: the first surprise in the history of the world.", "the_broken_bell"},
	},
	.Ranger = {
		.Aid = {"The Hunt Without Arrows", "You lead the Stag through the open Gate. The captain finishes on the far side; what turns back at the threshold is just a stag, white and ordinary, walking up toward grass. The hunt ends. Nothing died. The Court will argue for a century.", "the_hunt_without_arrows"},
		.Bargain = {"The Next White Thing", "Someone must guide the escaped dead back to the door, and the roadless make the best guides. You take the Stag's office: the walker between floors, the thing hunters refuse to shoot. Someday one will see what you carry and lower the bow.", "the_next_white_thing"},
		.Defy = {"The Old Way", "The arrow goes through the count itself -- the tally, the marks, the law of appointed prey. Hunts end when hunger ends, the old way, the honest way. From tonight, everything below gets to be an animal again. Including you.", "the_old_way"},
	},
}

@(rodata)
STORY_CRISIS_ECHOES := [Archetype_Id][Story_Choice_Verb]string{
	.Warden = {.Aid = "At the door, a knight's shade stands and salutes -- finished.", .Bargain = "The second oath sits quiet on your shoulder, at last.", .Defy = "Caldus limps up beside you, furious, alive. He stays."},
	.Rogue = {.Aid = "Pell waves the smoking ledger like a handkerchief. Goodbye.", .Bargain = "Your missing shadow doesn't come back. You stop checking.", .Defy = "Below, a knife keeps a deed pinned through one word: no."},
	.Arcanist = {.Aid = "Somewhere, a clerk you saved misfiles you -- kindly, forever.", .Bargain = "Rue's promotion letter is filed under regret. Hers.", .Defy = "Rue narrates this part herself. Six adjectives. Wonderful."},
	.Acolyte = {.Aid = "You answer to 'keeper' now. It is enough. It is yours.", .Bargain = "A small cold hand lets go only after the bell.", .Defy = "The bell in your pack stays quiet. Even about the lies."},
	.Ranger = {.Aid = "Sable files one writ: finished, zero arrows. The Court chokes.", .Bargain = "The captain's voice thanks you once, using your old name.", .Defy = "Two exiles walk up, doing the wild's oldest arithmetic: enough."},
}

@(rodata)
STORY_ENDING_ROAD_CODAS := [Story_Road]string{
	.Unwritten = "",
	.Witness = "The door is crowded -- everyone you helped came to see it end.",
	.Debtor = "Every debt you signed came due today. Every one was worth it.",
	.Defiant = "The dungeon does not mourn you leaving. It checks its locks.",
	.Forsaken = "",
}

@(rodata)
STORY_ENDING_FORSAKEN_CODAS := [Archetype_Id]string{
	.Warden = "The passing dead do not look at you.",
	.Rogue = "The freed dead pick another door.",
	.Arcanist = "The returning star flickers, once.",
	.Acolyte = "The silence after the bell runs a little long.",
	.Ranger = "The wild remembers you passed by on the left.",
}

STORY_LISS_AID_CODA :: "He asks the door to wait. The door -- for the first time in a hundred years -- waits."

@(rodata)
STORY_GATE_CHOICES := [Story_Choice_Verb]Story_Gate_Choice{
	.Aid = {"End it well", "Open the Gate and let the unfinished finish"},
	.Bargain = {"Take the seat", "Keep the door; weigh the tolls with honest scales"},
	.Defy = {"Break the door", "No more tolls -- let the unfinished walk up free"},
}

// Explicit registries are intentionally not generated from display strings.
// They are the future manifest contract for the 8 omen, 10 role, 15 ending,
// 10 relic, and 30 portrait assets specified by MX-story.
@(rodata)
STORY_OMEN_ASSET_KEYS := [Story_Motif_Id]string{
	.Crypt_Of_Ash = "story.omen.crypt_of_ash",
	.Fungal_Catacombs = "story.omen.fungal_catacombs",
	.Violet_Reliquary = "story.omen.violet_reliquary",
	.Sunken_Bastion = "story.omen.sunken_bastion",
	.Frozen_Ossuary = "story.omen.frozen_ossuary",
	.Obsidian_Foundry = "story.omen.obsidian_foundry",
	.Moonlit_Aquifer = "story.omen.moonlit_aquifer",
	.Thornbound_Vault = "story.omen.thornbound_vault",
}

@(rodata)
STORY_GUEST_BACKDROP_ASSET_KEYS := [Story_Guest_Role_Id]string{
	.Oathless_Knight = "story.guest.oathless_knight",
	.Grave_Witch = "story.guest.grave_witch",
	.Drowned_Heir = "story.guest.drowned_heir",
	.Ash_Pilgrim = "story.guest.ash_pilgrim",
	.Mirror_Scribe = "story.guest.mirror_scribe",
	.Antlered_Hunter = "story.guest.antlered_hunter",
	.Mortuary_Broker = "story.guest.mortuary_broker",
	.Lost_Cartographer = "story.guest.lost_cartographer",
	.Bone_Mender = "story.guest.bone_mender",
	.Furnace_Heretic = "story.guest.furnace_heretic",
}

@(rodata)
STORY_ENDING_PANEL_ASSET_KEYS := [Archetype_Id][Story_Choice_Verb]string{
	.Warden = {.Aid = "story.ending.warden.the_held_door", .Bargain = "story.ending.warden.the_fair_scale", .Defy = "story.ending.warden.no_more_doors"},
	.Rogue = {.Aid = "story.ending.rogue.the_emptied_market", .Bargain = "story.ending.rogue.the_honest_purchase", .Defy = "story.ending.rogue.the_standing_debt"},
	.Arcanist = {.Aid = "story.ending.arcanist.the_answered_proof", .Bargain = "story.ending.arcanist.the_restored_name", .Defy = "story.ending.arcanist.the_standing_argument"},
	.Acolyte = {.Aid = "story.ending.acolyte.the_true_funeral", .Bargain = "story.ending.acolyte.the_returned_confession", .Defy = "story.ending.acolyte.the_broken_bell"},
	.Ranger = {.Aid = "story.ending.ranger.the_hunt_without_arrows", .Bargain = "story.ending.ranger.the_next_white_thing", .Defy = "story.ending.ranger.the_old_way"},
}

@(rodata)
STORY_RELIC_ICON_ASSET_KEYS := [Story_Relic_Id]string{
	.Asterion_Nail = "story.relic.asterion_nail",
	.Mire_Saints_Bell = "story.relic.mire_saints_bell",
	.Lantern_Of_Unburied_Roads = "story.relic.lantern_of_unburied_roads",
	.Crown_Of_Antlers_And_Teeth = "story.relic.crown_of_antlers_and_teeth",
	.Mirror_Psalter = "story.relic.mirror_psalter",
	.Cinder_Key_Of_Khar = "story.relic.cinder_key_of_khar",
	.Wormscript_Map = "story.relic.wormscript_map",
	.Vessel_Of_Last_Rain = "story.relic.vessel_of_last_rain",
	.Oath_Eaters_Chain = "story.relic.oath_eaters_chain",
	.Heartseed_Reliquary = "story.relic.heartseed_reliquary",
}

@(rodata)
STORY_GUEST_PORTRAIT_ASSET_KEYS := [Story_Guest_Role_Id][STORY_GUEST_VARIANTS]string{
	.Oathless_Knight = {"story.portrait.oathless_knight.ser_caldus", "story.portrait.oathless_knight.dame_vey", "story.portrait.oathless_knight.rook_of_voss"},
	.Grave_Witch = {"story.portrait.grave_witch.mother_hush", "story.portrait.grave_witch.edda_crowmilk", "story.portrait.grave_witch.vespera_thorne"},
	.Drowned_Heir = {"story.portrait.drowned_heir.prince_nerian", "story.portrait.drowned_heir.lysa_underwave", "story.portrait.drowned_heir.blue_lipped_child"},
	.Ash_Pilgrim = {"story.portrait.ash_pilgrim.harl_the_sooted", "story.portrait.ash_pilgrim.sister_kharra", "story.portrait.ash_pilgrim.old_ember_jesk"},
	.Mirror_Scribe = {"story.portrait.mirror_scribe.tallow_quill", "story.portrait.mirror_scribe.iosef_of_the_glass", "story.portrait.mirror_scribe.nim_rue"},
	.Antlered_Hunter = {"story.portrait.antlered_hunter.mael_whitehorn", "story.portrait.antlered_hunter.quiet_hart", "story.portrait.antlered_hunter.sable_of_the_moon_hunt"},
	.Mortuary_Broker = {"story.portrait.mortuary_broker.coin_eye_pell", "story.portrait.mortuary_broker.madam_nacre", "story.portrait.mortuary_broker.voss_factor_ilm"},
	.Lost_Cartographer = {"story.portrait.lost_cartographer.ammar_without_roads", "story.portrait.lost_cartographer.fen_chalkhand", "story.portrait.lost_cartographer.sella_of_the_fold"},
	.Bone_Mender = {"story.portrait.bone_mender.saint_not_yet", "story.portrait.bone_mender.mara_sutured", "story.portrait.bone_mender.kell_of_white_thread"},
	.Furnace_Heretic = {"story.portrait.furnace_heretic.brass_thumb_oren", "story.portrait.furnace_heretic.malk_the_quenched", "story.portrait.furnace_heretic.devra_cogprayer"},
}
