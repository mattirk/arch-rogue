from __future__ import annotations

from typing import NamedTuple

from .models import (
    Archetype,
    Color,
    DungeonTheme,
    EliteModifier,
    RunModifier,
    SkillUpgrade,
)


class InteractionHint(NamedTuple):
    title: str
    detail: str
    color: Color


class RarityProfile(NamedTuple):
    color: Color
    icon: str
    weight: int


class EnemyDefinition(NamedTuple):
    name: str
    kind: str
    max_hp: int
    speed: float
    damage: int
    xp: int
    attack_range: float
    attack_cooldown: float
    aggro_range: float
    color: Color
    weight: int


class EncounterTemplate(NamedTuple):
    key: str
    title: str
    risk: str
    reward: str
    enemy_bonus: int = 0
    elite_bonus: float = 0.0
    trap_bonus: float = 0.0
    loot_bonus: float = 0.0
    secret_bonus: float = 0.0
    guaranteed_miniboss: bool = False
    challenge_room: bool = False


class BossDefinition(NamedTuple):
    key: str
    name: str
    subtitle: str
    theme_names: tuple[str, ...]
    damage_type: str
    max_hp: int
    speed: float
    damage: int
    xp: int
    attack_range: float
    attack_cooldown: float
    aggro_range: float
    color: Color
    telegraph: str
    loot_hook: str
    final_boss: bool = False


class DifficultyProfile(NamedTuple):
    name: str
    description: str
    enemy_hp_multiplier: float
    enemy_damage_multiplier: float
    enemy_damage_bonus: int
    enemy_speed_multiplier: float
    enemy_attack_cooldown_multiplier: float
    enemy_aggro_bonus: float
    enemy_count_bonus: int
    enemy_extra_chance: float
    elite_bonus: float
    miniboss_bonus: float
    trap_chance_bonus: float
    trap_damage_multiplier: float
    loot_chance_bonus: float
    shrine_chance_bonus: float


class EquipmentDefinition(NamedTuple):
    name: str
    slot: str
    value: int


class StoryBackstory(NamedTuple):
    title: str
    wound: str
    oath: str
    secret: str


class StoryFaction(NamedTuple):
    name: str
    epithet: str
    agenda: str
    taboo: str
    color: Color


class StoryRelic(NamedTuple):
    name: str
    form: str
    temptation: str
    doom: str


class StoryGuestTemplate(NamedTuple):
    role: str
    names: tuple[str, ...]
    motives: tuple[str, ...]
    voice: str


class StoryDilemmaTemplate(NamedTuple):
    title: str
    setup: str
    aid: str
    bargain: str
    defy: str
    aid_outcome: str
    bargain_outcome: str
    defy_outcome: str


class StoryLocationMotif(NamedTuple):
    theme_name: str
    image: str
    danger: str


ENEMY_DEFINITIONS = (
    EnemyDefinition(
        "Cultist", "ranged", 34, 2.0, 8, 18, 5.4, 1.45, 8.0, (125, 75, 170), 22
    ),
    EnemyDefinition(
        "Bone Imp", "ranged", 26, 3.0, 6, 16, 4.6, 1.0, 8.0, (190, 130, 215), 18
    ),
    EnemyDefinition(
        "Venom Skitter", "melee", 30, 3.6, 7, 15, 0.95, 0.72, 9.5, (110, 185, 95), 16
    ),
    EnemyDefinition(
        "Crypt Brute", "melee", 82, 1.75, 17, 32, 1.35, 1.35, 8.0, (155, 105, 74), 14
    ),
    EnemyDefinition(
        "Ghoul", "melee", 42, 2.7, 10, 20, 1.05, 0.95, 8.0, (160, 68, 68), 22
    ),
    EnemyDefinition(
        "Grave Archer", "ranged", 38, 2.25, 9, 21, 5.8, 1.35, 9.0, (120, 145, 105), 8
    ),
    EnemyDefinition(
        "Ash Hound", "melee", 34, 3.35, 9, 19, 0.95, 0.82, 9.0, (185, 86, 54), 14
    ),
    EnemyDefinition(
        "Rune Sentinel", "ranged", 66, 1.55, 13, 30, 5.2, 1.7, 8.5, (116, 220, 245), 8
    ),
    EnemyDefinition(
        "Plague Toad", "ranged", 54, 1.9, 11, 25, 4.2, 1.55, 7.5, (144, 172, 86), 10
    ),
    EnemyDefinition(
        "Hollow Knight", "melee", 58, 2.45, 13, 29, 1.15, 1.05, 8.5, (126, 132, 128), 9
    ),
)

FINAL_ROOM_ENEMY_DEFINITIONS = ENEMY_DEFINITIONS + (
    EnemyDefinition(
        "Gate Warden", "melee", 72, 2.1, 14, 34, 1.2, 1.0, 8.0, (190, 92, 54), 24
    ),
)

ENCOUNTER_TEMPLATES = (
    EncounterTemplate(
        "standard",
        "Hostile Patrols",
        "mixed patrols",
        "steady loot",
    ),
    EncounterTemplate(
        "elite_pack",
        "Elite Pack",
        "named elites with bright telegraphs",
        "rare gear chance",
        enemy_bonus=1,
        elite_bonus=0.16,
        loot_bonus=0.08,
    ),
    EncounterTemplate(
        "ambush",
        "Ruin Ambush",
        "extra fast enemies near side doors",
        "more XP",
        enemy_bonus=2,
        elite_bonus=0.05,
        trap_bonus=0.06,
    ),
    EncounterTemplate(
        "hazard_cache",
        "Hazard Cache",
        "traps guard obvious rewards",
        "extra cache odds",
        trap_bonus=0.18,
        loot_bonus=0.10,
        secret_bonus=0.09,
    ),
    EncounterTemplate(
        "treasure_room",
        "Treasure Room",
        "tempting loot draws guardians",
        "better loot",
        enemy_bonus=1,
        elite_bonus=0.08,
        loot_bonus=0.22,
        secret_bonus=0.08,
    ),
    EncounterTemplate(
        "challenge_room",
        "Challenge Room",
        "optional boss-marked room",
        "class upgrade or rare gear",
        enemy_bonus=1,
        elite_bonus=0.12,
        loot_bonus=0.14,
        guaranteed_miniboss=True,
        challenge_room=True,
    ),
)

BOSS_DEFINITIONS = (
    BossDefinition(
        "ash_gallows",
        "Ash Gallows Knight",
        "a shielded executioner who leaves ember scars before heavy swings",
        ("Crypt of Ash", "Obsidian Foundry"),
        "fire",
        132,
        1.82,
        17,
        62,
        1.35,
        1.05,
        10.5,
        (226, 104, 58),
        "ember cleave after a red-orange tell",
        "fire-forged rare weapon",
    ),
    BossDefinition(
        "mycelial_matron",
        "Mycelial Matron",
        "a spore witch that controls space with poison bolts and rooting spores",
        ("Fungal Catacombs", "Thornbound Vault"),
        "poison",
        122,
        1.64,
        15,
        58,
        4.9,
        1.22,
        11.0,
        (116, 196, 98),
        "spore volleys and poison pools",
        "sealed rare armor",
    ),
    BossDefinition(
        "rime_chanter",
        "Rime Chanter of the Ninth Bell",
        "a frost cultist whose chill volleys punish straight-line approaches",
        ("Frozen Ossuary", "Moonlit Aquifer"),
        "frost",
        118,
        1.72,
        14,
        60,
        5.2,
        1.12,
        11.5,
        (138, 212, 242),
        "wide frost fan after a pale tell",
        "frost-touched unique chance",
    ),
    BossDefinition(
        "void_sentinel",
        "Voidbound Rune Sentinel",
        "a reliquary construct that fires arcane bolts while its armor hums",
        ("Violet Reliquary", "Sunken Bastion"),
        "arcane",
        150,
        1.38,
        18,
        68,
        5.4,
        1.34,
        12.0,
        (166, 118, 246),
        "slow arcane lances with a violet tell",
        "runed legendary chance",
    ),
    BossDefinition(
        "gate_tyrant",
        "Dread Gate Tyrant",
        "the final seal's tyrant with alternating melee pressure and shadow casts",
        (),
        "shadow",
        245,
        1.65,
        21,
        120,
        1.45,
        1.08,
        13.0,
        (214, 92, 150),
        "shadow casts and crushing gate strikes",
        "unique gate relic",
        final_boss=True,
    ),
)

WEAPON_DEFINITIONS = (
    EquipmentDefinition("Iron Sword", "weapon", 5),
    EquipmentDefinition("Hunter Axe", "weapon", 7),
    EquipmentDefinition("Runed Saber", "weapon", 6),
    EquipmentDefinition("Ash Pike", "weapon", 8),
    EquipmentDefinition("Grave Knife", "weapon", 4),
)

ARMOR_DEFINITIONS = (
    EquipmentDefinition("Leather Jerkin", "armor", 2),
    EquipmentDefinition("Warden Mail", "armor", 4),
    EquipmentDefinition("Chain Vest", "armor", 3),
    EquipmentDefinition("Boneweave Mantle", "armor", 3),
    EquipmentDefinition("Pilgrim's Plate", "armor", 5),
)

TRAP_DEFINITIONS = (
    ("Spike Trap", 14, 22),
    ("Rune Trap", 13, 21),
    ("Poison Needle", 10, 18),
)

DEFAULT_DIFFICULTY_NAME = "Hard"
HELL_DIFFICULTY_NAME = "Hell"
DIFFICULTY_PROFILES = (
    DifficultyProfile(
        "Easy",
        "Still dangerous: tougher enemies, real ambush pressure, and fewer safety nets.",
        enemy_hp_multiplier=1.76,
        enemy_damage_multiplier=1.64,
        enemy_damage_bonus=1,
        enemy_speed_multiplier=1.08,
        enemy_attack_cooldown_multiplier=0.90,
        enemy_aggro_bonus=0.60,
        enemy_count_bonus=0,
        enemy_extra_chance=0.35,
        elite_bonus=0.03,
        miniboss_bonus=0.015,
        trap_chance_bonus=0.05,
        trap_damage_multiplier=1.50,
        loot_chance_bonus=0.0,
        shrine_chance_bonus=0.0,
    ),
    DifficultyProfile(
        "Medium",
        "Severe pressure with doubled monster durability, damage, traps, and room threats.",
        enemy_hp_multiplier=2.36,
        enemy_damage_multiplier=2.30,
        enemy_damage_bonus=2,
        enemy_speed_multiplier=1.14,
        enemy_attack_cooldown_multiplier=0.82,
        enemy_aggro_bonus=1.40,
        enemy_count_bonus=1,
        enemy_extra_chance=0.70,
        elite_bonus=0.05,
        miniboss_bonus=0.03,
        trap_chance_bonus=0.10,
        trap_damage_multiplier=2.20,
        loot_chance_bonus=-0.08,
        shrine_chance_bonus=-0.04,
    ),
    DifficultyProfile(
        "Hard",
        "Default: brutal density, crushing hits, relentless attacks, and scarce recovery.",
        enemy_hp_multiplier=2.85,
        enemy_damage_multiplier=2.60,
        enemy_damage_bonus=5,
        enemy_speed_multiplier=1.18,
        enemy_attack_cooldown_multiplier=0.74,
        enemy_aggro_bonus=2.50,
        enemy_count_bonus=2,
        enemy_extra_chance=0.75,
        elite_bonus=0.16,
        miniboss_bonus=0.085,
        trap_chance_bonus=0.25,
        trap_damage_multiplier=2.55,
        loot_chance_bonus=-0.13,
        shrine_chance_bonus=-0.065,
    ),
    DifficultyProfile(
        "Hell",
        "Unlocked after a clear: overwhelming density, constant elites, lethal traps, and no mercy.",
        enemy_hp_multiplier=3.80,
        enemy_damage_multiplier=3.30,
        enemy_damage_bonus=8,
        enemy_speed_multiplier=1.30,
        enemy_attack_cooldown_multiplier=0.60,
        enemy_aggro_bonus=4.75,
        enemy_count_bonus=3,
        enemy_extra_chance=0.90,
        elite_bonus=0.30,
        miniboss_bonus=0.17,
        trap_chance_bonus=0.42,
        trap_damage_multiplier=3.35,
        loot_chance_bonus=-0.20,
        shrine_chance_bonus=-0.12,
    ),
)
SHRINE_TYPES = (
    "Mending Shrine",
    "Insight Shrine",
    "War Shrine",
    "Haste Shrine",
    "Fortune Shrine",
    "Oath Shrine",
    "Twilight Shrine",
)
SECRET_TYPES = (
    "Hidden Cache",
    "Cursed Reliquary",
    "Sealed Armory",
    "Forgotten Skill Altar",
    "Moonlit Bargain",
)

RARITY_PROFILES: dict[str, RarityProfile] = {
    "Common": RarityProfile((215, 210, 190), "·", 100),
    "Magic": RarityProfile((115, 175, 255), "✦", 52),
    "Rare": RarityProfile((245, 215, 90), "◆", 26),
    "Unique": RarityProfile((240, 145, 65), "✹", 4),
    "Legendary": RarityProfile((255, 112, 82), "✷", 2),
    "Cursed": RarityProfile((214, 92, 150), "!", 10),
    "Unidentified": RarityProfile((170, 170, 185), "?", 18),
}

SHRINE_HINTS: dict[str, InteractionHint] = {
    "Mending Shrine": InteractionHint(
        "Mending Shrine", "Restores health and mana.", (105, 230, 125)
    ),
    "Insight Shrine": InteractionHint(
        "Insight Shrine", "Reveals unidentified inventory gear.", (145, 205, 255)
    ),
    "War Shrine": InteractionHint(
        "War Shrine", "Grants combat focus and XP.", (245, 170, 90)
    ),
    "Haste Shrine": InteractionHint(
        "Haste Shrine", "Refreshes stamina and quickens movement.", (235, 220, 95)
    ),
    "Fortune Shrine": InteractionHint(
        "Fortune Shrine", "Spills extra offerings and loot.", (245, 215, 90)
    ),
    "Oath Shrine": InteractionHint(
        "Oath Shrine", "Attempts to grant a class upgrade.", (190, 150, 245)
    ),
    "Twilight Shrine": InteractionHint(
        "Twilight Shrine", "Trades blood for a unique relic.", (214, 92, 150)
    ),
}

SECRET_HINTS: dict[str, InteractionHint] = {
    "Hidden Cache": InteractionHint(
        "Hidden Cache", "Open for a concealed reward.", (235, 205, 120)
    ),
    "Cursed Reliquary": InteractionHint(
        "Cursed Reliquary", "May awaken a guardian for reward.", (214, 92, 150)
    ),
    "Sealed Armory": InteractionHint(
        "Sealed Armory", "Contains equipment choices.", (245, 215, 90)
    ),
    "Forgotten Skill Altar": InteractionHint(
        "Forgotten Skill Altar", "Deepens your class build.", (145, 205, 255)
    ),
    "Moonlit Bargain": InteractionHint(
        "Moonlit Bargain", "Costs blood for rare gear.", (214, 92, 150)
    ),
}

TRAP_HINTS: dict[str, InteractionHint] = {
    "Spike Trap": InteractionHint(
        "Spike Trap", "Pressure plate; step away fast.", (245, 95, 70)
    ),
    "Rune Trap": InteractionHint(
        "Rune Trap", "Arcane sigil; avoid the glow.", (180, 120, 245)
    ),
    "Poison Needle": InteractionHint(
        "Poison Needle", "Needle trigger; keep distance.", (120, 210, 110)
    ),
}

HUMANOID_ENEMY_NAMES = (
    "Bone Imp",
    "Cultist",
    "Crypt Brute",
    "Gate Warden",
    "Ghoul",
    "Grave Archer",
    "Rune Sentinel",
    "Hollow Knight",
)

ARCHETYPES = (
    Archetype(
        "Warden",
        "Durable melee fighter with reliable armor and stamina.",
        max_hp=120,
        max_mana=38,
        max_stamina=112,
        speed=4.45,
        melee_bonus=3,
        armor_bonus=2,
    ),
    Archetype(
        "Rogue",
        "Fast striker who trades durability for speed and burst damage.",
        max_hp=92,
        max_mana=42,
        max_stamina=126,
        speed=5.25,
        melee_bonus=5,
    ),
    Archetype(
        "Arcanist",
        "Fragile caster with stronger bolts and novas.",
        max_hp=86,
        max_mana=78,
        max_stamina=94,
        speed=4.35,
        spell_bonus=9,
    ),
    Archetype(
        "Acolyte",
        "Dark priest with balanced defenses and potent rites.",
        max_hp=102,
        max_mana=62,
        max_stamina=98,
        speed=4.4,
        melee_bonus=1,
        spell_bonus=5,
        armor_bonus=1,
    ),
    Archetype(
        "Ranger",
        "Mobile marksman with strong stamina and hybrid damage.",
        max_hp=98,
        max_mana=48,
        max_stamina=120,
        speed=4.95,
        melee_bonus=3,
        spell_bonus=2,
    ),
)

DUNGEON_THEMES = (
    DungeonTheme(
        "Crypt of Ash",
        "charred halls and emberlit stairs",
        floor=(52, 47, 42),
        floor_edge=(72, 66, 60),
        wall_top=(45, 42, 49),
        wall_left=(31, 29, 36),
        wall_right=(24, 23, 30),
        wall_edge=(58, 55, 66),
        stair=(230, 188, 90),
        accent=(240, 145, 65),
    ),
    DungeonTheme(
        "Fungal Catacombs",
        "damp stone, pale spores, and hidden growths",
        floor=(42, 53, 42),
        floor_edge=(65, 82, 59),
        wall_top=(34, 51, 45),
        wall_left=(24, 38, 34),
        wall_right=(20, 31, 32),
        wall_edge=(60, 84, 70),
        stair=(166, 210, 116),
        accent=(110, 185, 95),
    ),
    DungeonTheme(
        "Violet Reliquary",
        "occult vaults humming with void rites",
        floor=(45, 39, 58),
        floor_edge=(78, 65, 103),
        wall_top=(42, 34, 58),
        wall_left=(30, 24, 44),
        wall_right=(25, 20, 38),
        wall_edge=(76, 60, 112),
        stair=(205, 140, 235),
        accent=(160, 86, 230),
    ),
    DungeonTheme(
        "Sunken Bastion",
        "flood-stained battlements and drowned reliquaries",
        floor=(39, 52, 58),
        floor_edge=(60, 82, 92),
        wall_top=(36, 49, 55),
        wall_left=(25, 36, 43),
        wall_right=(20, 31, 38),
        wall_edge=(64, 88, 99),
        stair=(112, 190, 205),
        accent=(86, 188, 215),
    ),
    DungeonTheme(
        "Frozen Ossuary",
        "blue-lit bone vaults where frost silences footsteps",
        floor=(46, 53, 62),
        floor_edge=(76, 91, 110),
        wall_top=(43, 50, 63),
        wall_left=(30, 36, 48),
        wall_right=(24, 30, 42),
        wall_edge=(88, 107, 132),
        stair=(168, 215, 235),
        accent=(128, 206, 242),
    ),
    DungeonTheme(
        "Obsidian Foundry",
        "molten channels, hammering echoes, and ember-lit machinery",
        floor=(55, 43, 38),
        floor_edge=(92, 62, 48),
        wall_top=(49, 38, 35),
        wall_left=(34, 25, 25),
        wall_right=(28, 21, 22),
        wall_edge=(118, 68, 44),
        stair=(245, 132, 72),
        accent=(245, 104, 52),
    ),
    DungeonTheme(
        "Moonlit Aquifer",
        "silver pools, echoing wells, and pale drowned altars",
        floor=(37, 49, 62),
        floor_edge=(62, 82, 106),
        wall_top=(35, 45, 59),
        wall_left=(24, 33, 46),
        wall_right=(19, 28, 39),
        wall_edge=(84, 116, 150),
        stair=(176, 206, 232),
        accent=(145, 184, 232),
    ),
    DungeonTheme(
        "Thornbound Vault",
        "root-split masonry, green witchlight, and hungry brambles",
        floor=(41, 50, 38),
        floor_edge=(62, 82, 52),
        wall_top=(38, 47, 35),
        wall_left=(26, 34, 25),
        wall_right=(22, 29, 21),
        wall_edge=(78, 103, 64),
        stair=(158, 214, 106),
        accent=(126, 214, 92),
    ),
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

RUN_MODIFIERS = (
    RunModifier(
        "Blood Moon",
        "Enemies are tougher and hit harder, but loot is richer.",
        1.18,
        2,
        1.0,
        0.07,
    ),
    RunModifier(
        "Restless Depths", "More enemies wake from farther away.", 1.08, 1, 2.0, 0.02
    ),
    RunModifier(
        "Treasure Draught",
        "The dungeon yields more equipment and rare caches.",
        1.0,
        0,
        0.0,
        0.14,
    ),
    RunModifier(
        "Trap-Laced",
        "Hazards are more common, but shrines answer more often.",
        1.0,
        0,
        0.5,
        0.05,
        0.16,
    ),
    RunModifier(
        "Thin Veil",
        "The tyrant's guard is alert, but hidden caches are easier to find.",
        1.06,
        1,
        1.0,
        0.08,
        0.04,
    ),
    RunModifier(
        "Starved Depths",
        "Loot is scarcer, but enemies are slightly weakened.",
        0.92,
        -1,
        -0.5,
        -0.08,
        0.0,
    ),
    RunModifier(
        "Elite Hunt",
        "More elites and minibosses stalk the halls, carrying better spoils.",
        1.10,
        1,
        1.0,
        0.10,
        0.02,
    ),
    RunModifier(
        "Cursed Bargains",
        "Cursed gear and risky events are more common, but rewards spike higher.",
        1.04,
        0,
        0.5,
        0.16,
        0.04,
    ),
)

SKILL_UPGRADES = (
    SkillUpgrade(
        "warden_bulwark",
        "Warden",
        "Bulwark Training",
        "Melee bashes cleave wider and armor improves.",
        melee_bonus=1,
        armor_bonus=2,
        max_hp_bonus=10,
    ),
    SkillUpgrade(
        "warden_riposte",
        "Warden",
        "Riposte Guard",
        "Taking melee hits costs less health and fuels counterattacks.",
        melee_bonus=2,
        armor_bonus=1,
    ),
    SkillUpgrade(
        "warden_aegis",
        "Warden",
        "Aegis Discipline",
        "Guard Step briefly hardens the Warden and Shield Bash staggers enemies.",
        armor_bonus=1,
        max_stamina_bonus=8,
    ),
    SkillUpgrade(
        "rogue_precision",
        "Rogue",
        "Killing Precision",
        "Crits are deadlier and quick strikes cost less stamina.",
        melee_bonus=3,
        max_stamina_bonus=8,
    ),
    SkillUpgrade(
        "rogue_smoke",
        "Rogue",
        "Smoke Step",
        "Evasion improves after using movement skills.",
        speed_bonus=0.15,
        max_stamina_bonus=10,
    ),
    SkillUpgrade(
        "rogue_venom",
        "Rogue",
        "Venomcraft",
        "Backstabs and knife fans poison wounded targets.",
        melee_bonus=1,
        max_stamina_bonus=6,
    ),
    SkillUpgrade(
        "arcanist_splinter",
        "Arcanist",
        "Splintered Arcana",
        "Arc Bolt throws an extra shard.",
        spell_bonus=3,
        max_mana_bonus=10,
    ),
    SkillUpgrade(
        "arcanist_focus",
        "Arcanist",
        "Deep Focus",
        "Mana recovers faster and novas reach farther.",
        spell_bonus=2,
        max_mana_bonus=14,
    ),
    SkillUpgrade(
        "arcanist_permafrost",
        "Arcanist",
        "Permafrost Sigils",
        "Frost Nova chills longer and Arc Bolt exploits chilled foes.",
        spell_bonus=2,
        max_mana_bonus=8,
    ),
    SkillUpgrade(
        "acolyte_sanguine",
        "Acolyte",
        "Sanguine Rite",
        "Blood skills leech more life at close range.",
        melee_bonus=1,
        spell_bonus=2,
        max_hp_bonus=8,
    ),
    SkillUpgrade(
        "acolyte_veil",
        "Acolyte",
        "Veil of Ash",
        "Mana shields blunt harsher blows.",
        armor_bonus=1,
        max_mana_bonus=8,
    ),
    SkillUpgrade(
        "acolyte_gravebind",
        "Acolyte",
        "Gravebind Covenant",
        "Blood Nova binds enemies and kills echo more life into the Acolyte.",
        spell_bonus=2,
        max_hp_bonus=6,
        max_mana_bonus=6,
    ),
    SkillUpgrade(
        "ranger_snare",
        "Ranger",
        "Barbed Snares",
        "Control skills delay enemies longer.",
        spell_bonus=2,
        max_stamina_bonus=8,
    ),
    SkillUpgrade(
        "ranger_volley",
        "Ranger",
        "Volley Drills",
        "Multishot spreads into a wider fan.",
        melee_bonus=1,
        spell_bonus=2,
    ),
    SkillUpgrade(
        "ranger_beastmark",
        "Ranger",
        "Beastmark Pursuit",
        "Vault refreshes momentum and marked shots hit controlled enemies harder.",
        melee_bonus=1,
        speed_bonus=0.12,
        max_stamina_bonus=6,
    ),
)

ELITE_MODIFIERS = (
    EliteModifier(
        "Frenzied",
        "fast attacks with a red warning flash",
        hp_multiplier=1.25,
        damage_bonus=2,
        speed_multiplier=1.18,
        xp_bonus=12,
        color_shift=(45, -10, -10),
    ),
    EliteModifier(
        "Ironbound",
        "slow, armored pressure with a bronze tell",
        hp_multiplier=1.65,
        damage_bonus=1,
        speed_multiplier=0.86,
        xp_bonus=16,
        color_shift=(35, 24, -8),
    ),
    EliteModifier(
        "Venomous",
        "poisoned strikes and sickly green tells",
        hp_multiplier=1.20,
        damage_bonus=4,
        speed_multiplier=1.0,
        xp_bonus=14,
        color_shift=(-20, 42, -16),
    ),
    EliteModifier(
        "Runed",
        "longer aggro and brighter spell telegraphs",
        hp_multiplier=1.35,
        damage_bonus=3,
        speed_multiplier=1.0,
        xp_bonus=18,
        color_shift=(-18, 30, 48),
    ),
)
