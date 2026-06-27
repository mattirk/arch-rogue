from __future__ import annotations

from .definitions import EquipmentDefinition, RarityProfile


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


RARITY_PROFILES: dict[str, RarityProfile] = {
    "Common": RarityProfile((215, 210, 190), "·", 100),
    "Magic": RarityProfile((115, 175, 255), "✦", 52),
    "Rare": RarityProfile((245, 215, 90), "◆", 26),
    "Unique": RarityProfile((240, 145, 65), "✹", 4),
    "Legendary": RarityProfile((255, 112, 82), "✷", 2),
    "Cursed": RarityProfile((214, 92, 150), "!", 10),
    "Unidentified": RarityProfile((170, 170, 185), "?", 18),
}

