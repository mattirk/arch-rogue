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


class EquipmentDefinition(NamedTuple):
    name: str
    slot: str
    value: int


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
