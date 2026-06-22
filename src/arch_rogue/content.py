from __future__ import annotations

from typing import NamedTuple

from .models import Archetype, Color, DungeonTheme, RunModifier

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
)
SECRET_TYPES = ("Hidden Cache", "Cursed Reliquary", "Sealed Armory")
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
)
