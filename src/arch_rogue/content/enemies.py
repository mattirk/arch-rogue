from __future__ import annotations

from .definitions import BossDefinition, EncounterTemplate, EnemyDefinition


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

