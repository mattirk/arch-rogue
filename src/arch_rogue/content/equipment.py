from __future__ import annotations

from dataclasses import dataclass

from .definitions import EquipmentDefinition, RarityProfile

StatRange = tuple[float, float]


@dataclass(frozen=True)
class AffixDefinition:
    """Data-driven equipment affix.

    Numeric fields are base roll ranges. Population scales them through
    `RARITY_AFFIX_ROLL_RANGES`, keeping all tier tuning in one place while the
    affix table stays readable.
    """

    name: str
    slots: tuple[str, ...]
    tags: tuple[str, ...]
    description: str
    power: StatRange = (0.0, 0.0)
    defense: StatRange = (0.0, 0.0)
    attack_speed: StatRange = (0.0, 0.0)
    cast_speed: StatRange = (0.0, 0.0)
    move_speed: StatRange = (0.0, 0.0)
    thorns: StatRange = (0.0, 0.0)
    lifesteal: StatRange = (0.0, 0.0)
    proc_chance: StatRange = (0.0, 0.0)
    damage_type: str = ""
    skill_bonus: str = ""
    proc_effect: str = ""


@dataclass(frozen=True)
class UniqueItemDefinition:
    """Build-defining unique item blueprint."""

    name: str
    archetype: str
    slot: str
    power: int = 0
    defense: int = 0
    affixes: tuple[str, ...] = ()
    affix_tags: tuple[str, ...] = ()
    damage_type: str = "physical"
    skill_bonus: str = ""
    proc_effect: str = ""
    unique_effect: str = ""
    attack_speed: float = 0.0
    cast_speed: float = 0.0
    move_speed: float = 0.0
    thorns: int = 0
    lifesteal: float = 0.0
    proc_chance: float = 0.0


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

# Per-tier affix counts and roll multipliers. Common gear remains simple; high
# tiers gain both more tags and wider, stronger ranges. Cursed gear rolls hot but
# receives explicit tradeoffs in population._apply_cursed_bargain.
RARITY_AFFIX_COUNTS: dict[str, int] = {
    "Common": 0,
    "Magic": 1,
    "Rare": 2,
    "Legendary": 3,
    "Unique": 3,
    "Cursed": 2,
}

RARITY_AFFIX_ROLL_RANGES: dict[str, StatRange] = {
    "Common": (0.0, 0.0),
    "Magic": (0.80, 1.00),
    "Rare": (1.00, 1.25),
    "Legendary": (1.25, 1.55),
    "Unique": (1.35, 1.65),
    "Cursed": (1.45, 1.75),
}


AFFIX_DEFINITIONS: tuple[AffixDefinition, ...] = (
    # Weapon pressure and damage-type identity.
    AffixDefinition(
        "Serrated",
        ("weapon",),
        ("melee", "physical", "bleed", "proc"),
        "Reliable melee damage with a bleed-like poison tick.",
        power=(2, 4),
        proc_chance=(0.16, 0.26),
        proc_effect="bleed",
    ),
    AffixDefinition(
        "Cruel",
        ("weapon",),
        ("melee", "physical"),
        "High raw weapon damage.",
        power=(4, 6),
    ),
    AffixDefinition(
        "Balanced",
        ("weapon",),
        ("melee", "attack_speed", "dash"),
        "Faster follow-up attacks and cleaner tempo.",
        power=(1, 3),
        attack_speed=(0.04, 0.08),
        skill_bonus="Dash tempo",
    ),
    AffixDefinition(
        "Frostbitten",
        ("weapon",),
        ("frost", "control", "proc", "spell"),
        "Converts weapon pressure to frost and chills on hit.",
        power=(2, 4),
        proc_chance=(0.22, 0.34),
        damage_type="frost",
        proc_effect="chill",
    ),
    AffixDefinition(
        "Zealous",
        ("weapon",),
        ("holy", "melee", "guard"),
        "A holy melee bias for Warden-style smites.",
        power=(2, 4),
        defense=(0, 1),
        damage_type="holy",
        skill_bonus="Melee force",
    ),
    AffixDefinition(
        "Vampiric",
        ("weapon",),
        ("shadow", "lifesteal", "melee"),
        "Turns close-range hits into sustain.",
        power=(2, 4),
        lifesteal=(0.05, 0.08),
        damage_type="shadow",
        proc_effect="lifesteal",
    ),
    AffixDefinition(
        "Storm-Touched",
        ("weapon",),
        ("arcane", "bolt", "cast_speed", "proc"),
        "Arcane casting speed with a chance to arc lightning.",
        power=(3, 5),
        cast_speed=(0.04, 0.08),
        proc_chance=(0.16, 0.26),
        damage_type="arcane",
        skill_bonus="Bolt +1 shard",
        proc_effect="chain",
    ),
    AffixDefinition(
        "Ember-Veined",
        ("weapon",),
        ("fire", "proc", "melee"),
        "Fire conversion and ignite pressure.",
        power=(3, 5),
        proc_chance=(0.22, 0.34),
        damage_type="fire",
        proc_effect="ignite",
    ),
    AffixDefinition(
        "Venomous",
        ("weapon",),
        ("poison", "critical", "proc"),
        "Poison hooks for Rogue precision and Ranger control builds.",
        power=(2, 4),
        attack_speed=(0.02, 0.05),
        proc_chance=(0.24, 0.38),
        damage_type="poison",
        proc_effect="poison",
    ),
    AffixDefinition(
        "Quickened",
        ("weapon",),
        ("attack_speed", "melee", "volley"),
        "A pure attack-speed suffix for rapid basic attacks.",
        power=(1, 2),
        attack_speed=(0.07, 0.12),
        skill_bonus="Melee tempo",
    ),
    AffixDefinition(
        "Rune-Cut",
        ("weapon",),
        ("arcane", "cast_speed", "spell"),
        "Hybrid weapon damage for spell-forward builds.",
        power=(2, 4),
        cast_speed=(0.05, 0.10),
        damage_type="arcane",
        skill_bonus="Bolt pierce",
    ),
    AffixDefinition(
        "Grave-Hungering",
        ("weapon",),
        ("shadow", "blood", "lifesteal"),
        "Blood-magic sustain at the cost of a darker damage profile.",
        power=(3, 5),
        lifesteal=(0.06, 0.10),
        damage_type="shadow",
        skill_bonus="Blood leech",
        proc_effect="lifesteal",
    ),
    # Armor mitigation, movement, and retaliation.
    AffixDefinition(
        "Reinforced",
        ("armor",),
        ("armor", "guard"),
        "Simple, reliable armor scaling.",
        defense=(2, 4),
    ),
    AffixDefinition(
        "Stalwart",
        ("armor",),
        ("armor", "ward"),
        "Stiffer armor for slower, safer builds.",
        defense=(3, 5),
    ),
    AffixDefinition(
        "Light",
        ("armor",),
        ("movement", "dash", "attack_speed"),
        "Lower defense, better footwork.",
        defense=(1, 2),
        attack_speed=(0.02, 0.05),
        move_speed=(0.03, 0.06),
        skill_bonus="Dash tempo",
    ),
    AffixDefinition(
        "Sealed",
        ("armor",),
        ("ward", "shadow", "poison", "nova"),
        "Occult sealing against poison and shadow threats.",
        defense=(3, 5),
        damage_type="shadow",
        skill_bonus="Nova ward",
    ),
    AffixDefinition(
        "Thorned",
        ("armor",),
        ("thorns", "retaliate", "guard"),
        "Reflects melee pressure back into attackers.",
        power=(0, 1),
        defense=(1, 3),
        thorns=(2, 4),
        proc_effect="thorns",
    ),
    AffixDefinition(
        "Grounded",
        ("armor",),
        ("arcane", "ward", "nova"),
        "Arcane-resistant armor that steadies casting.",
        defense=(3, 5),
        cast_speed=(0.02, 0.05),
        damage_type="arcane",
        skill_bonus="Nova ward",
    ),
    AffixDefinition(
        "Regal",
        ("armor",),
        ("holy", "melee", "guard"),
        "A noble hybrid of armor and melee authority.",
        power=(1, 2),
        defense=(2, 4),
        damage_type="holy",
        skill_bonus="Melee force",
    ),
    AffixDefinition(
        "Fleet",
        ("armor",),
        ("movement", "dash", "survival"),
        "Movement speed for kiting and repositioning.",
        defense=(1, 2),
        move_speed=(0.05, 0.10),
        skill_bonus="Dash tempo",
    ),
    AffixDefinition(
        "Mirror-Barbed",
        ("armor",),
        ("thorns", "arcane", "retaliate"),
        "Arcane barbs that punish melee attackers.",
        defense=(2, 4),
        thorns=(3, 6),
        damage_type="arcane",
        proc_effect="thorns",
    ),
    AffixDefinition(
        "Hexwoven",
        ("armor",),
        ("shadow", "curse", "cast_speed"),
        "Shadow weave for curse and blood casters.",
        defense=(2, 4),
        cast_speed=(0.04, 0.08),
        damage_type="shadow",
        skill_bonus="Blood leech",
    ),
    AffixDefinition(
        "Focused",
        ("armor",),
        ("cast_speed", "spell", "ward"),
        "Lighter plating that quickens repeated casts.",
        defense=(1, 3),
        cast_speed=(0.06, 0.12),
    ),
    # Cross-slot utility suffixes.
    AffixDefinition(
        "of the Fox",
        ("weapon", "armor"),
        ("movement", "dash", "attack_speed"),
        "Fast hands and fast feet.",
        power=(1, 2),
        defense=(1, 2),
        attack_speed=(0.03, 0.07),
        move_speed=(0.03, 0.07),
        skill_bonus="Dash tempo",
    ),
    AffixDefinition(
        "of Warding",
        ("weapon", "armor"),
        ("ward", "guard", "nova"),
        "Defensive warding that supports Guard/Nova play.",
        defense=(2, 4),
        skill_bonus="Nova ward",
    ),
    AffixDefinition(
        "of Force",
        ("weapon", "armor"),
        ("melee", "knockback", "guard"),
        "More force behind close-range impacts.",
        power=(2, 4),
        skill_bonus="Melee force",
    ),
    AffixDefinition(
        "of the Deep",
        ("weapon", "armor"),
        ("frost", "shadow", "spell"),
        "Cold abyssal magic for control builds.",
        defense=(2, 4),
        damage_type="frost",
        proc_effect="chill",
        proc_chance=(0.14, 0.24),
    ),
    AffixDefinition(
        "of Ember",
        ("weapon", "armor"),
        ("fire", "proc"),
        "Adds fire identity and ignite pressure.",
        power=(2, 4),
        damage_type="fire",
        proc_effect="ignite",
        proc_chance=(0.16, 0.28),
    ),
    AffixDefinition(
        "of Cinders",
        ("weapon", "armor"),
        ("fire", "cast_speed", "proc"),
        "Aggressive fire rolls with a small defensive tradeoff.",
        power=(3, 5),
        defense=(-2, -1),
        cast_speed=(0.03, 0.07),
        damage_type="fire",
        proc_effect="ignite",
        proc_chance=(0.20, 0.32),
    ),
    AffixDefinition(
        "of the Moon",
        ("weapon", "armor"),
        ("frost", "cast_speed", "control"),
        "Moonlit frost and steadier spell rhythm.",
        power=(1, 2),
        defense=(2, 4),
        cast_speed=(0.03, 0.07),
        damage_type="frost",
        proc_effect="chill",
        proc_chance=(0.18, 0.30),
    ),
    AffixDefinition(
        "of Thorns",
        ("weapon", "armor"),
        ("thorns", "retaliate", "survival"),
        "Adds retaliation to either slot.",
        defense=(1, 3),
        thorns=(2, 5),
        proc_effect="thorns",
    ),
    AffixDefinition(
        "of Alacrity",
        ("weapon", "armor"),
        ("attack_speed", "cast_speed", "movement"),
        "A broad speed suffix for tempo builds.",
        attack_speed=(0.04, 0.08),
        cast_speed=(0.04, 0.08),
        move_speed=(0.02, 0.05),
    ),
    AffixDefinition(
        "of the Occult",
        ("weapon", "armor"),
        ("shadow", "cast_speed", "curse"),
        "Dark casting throughput for Acolyte and curse paths.",
        power=(1, 3),
        cast_speed=(0.05, 0.10),
        damage_type="shadow",
        skill_bonus="Blood leech",
    ),
    AffixDefinition(
        "of the Hunt",
        ("weapon", "armor"),
        ("volley", "control", "movement"),
        "Ranger-leaning mobility and projectile cadence.",
        power=(1, 3),
        move_speed=(0.03, 0.07),
        skill_bonus="Bolt +1 shard",
    ),
    AffixDefinition(
        "of Siphons",
        ("weapon", "armor"),
        ("lifesteal", "blood", "shadow"),
        "Sustain for blood and attrition builds.",
        power=(1, 3),
        lifesteal=(0.04, 0.08),
        damage_type="shadow",
        proc_effect="lifesteal",
    ),
)


UNIQUE_ITEM_DEFINITIONS: tuple[UniqueItemDefinition, ...] = (
    # Legacy uniques kept as global chase drops.
    UniqueItemDefinition(
        "Emberbrand",
        "Any",
        "weapon",
        power=12,
        affixes=("Serrated", "of Force", "Ember-Veined"),
        affix_tags=("melee", "fire", "proc"),
        damage_type="fire",
        skill_bonus="Melee force",
        proc_effect="ignite",
        unique_effect="embers on hit",
        attack_speed=0.05,
        proc_chance=1.0,
    ),
    UniqueItemDefinition(
        "Frostwake",
        "Any",
        "weapon",
        power=10,
        affixes=("Frostbitten", "Balanced", "of the Moon"),
        affix_tags=("frost", "bolt", "control", "cast_speed"),
        damage_type="frost",
        skill_bonus="Bolt +1 shard",
        proc_effect="chill",
        unique_effect="chill on hit",
        attack_speed=0.05,
        cast_speed=0.05,
        proc_chance=1.0,
    ),
    UniqueItemDefinition(
        "Bulwark of the First Gate",
        "Any",
        "armor",
        defense=8,
        affixes=("Reinforced", "of Warding", "Thorned"),
        affix_tags=("guard", "ward", "thorns"),
        damage_type="holy",
        skill_bonus="Dash guard",
        proc_effect="thorns",
        unique_effect="steadfast bulwark",
        thorns=5,
    ),
    # Archetype-specific build anchors.
    UniqueItemDefinition(
        "Oathwall Carapace",
        "Warden",
        "armor",
        defense=9,
        affixes=("Reinforced", "Thorned", "of Warding"),
        affix_tags=("guard", "ward", "thorns", "holy"),
        damage_type="holy",
        skill_bonus="Dash guard",
        proc_effect="thorns",
        unique_effect="oathwall aegis",
        thorns=6,
    ),
    UniqueItemDefinition(
        "Reckoner's Brand",
        "Warden",
        "weapon",
        power=11,
        affixes=("Zealous", "of Force", "Quickened"),
        affix_tags=("counter", "holy", "melee", "attack_speed"),
        damage_type="holy",
        skill_bonus="Melee force",
        proc_effect="smite",
        unique_effect="counter smite",
        attack_speed=0.10,
        proc_chance=0.45,
    ),
    UniqueItemDefinition(
        "Nightglass Daggers",
        "Rogue",
        "weapon",
        power=10,
        affixes=("Venomous", "Quickened", "Vampiric"),
        affix_tags=("critical", "poison", "lifesteal", "attack_speed"),
        damage_type="poison",
        skill_bonus="Melee tempo",
        proc_effect="poison",
        unique_effect="smoke crits",
        attack_speed=0.16,
        move_speed=0.04,
        lifesteal=0.06,
        proc_chance=0.60,
    ),
    UniqueItemDefinition(
        "Foxstep Leathers",
        "Rogue",
        "armor",
        defense=5,
        affixes=("Fleet", "of the Fox", "Light"),
        affix_tags=("stealth", "dash", "movement", "attack_speed"),
        skill_bonus="Dash tempo",
        proc_effect="smoke",
        unique_effect="vanish on dash",
        attack_speed=0.06,
        move_speed=0.12,
        proc_chance=0.35,
    ),
    UniqueItemDefinition(
        "Splinter Star",
        "Arcanist",
        "weapon",
        power=8,
        affixes=("Storm-Touched", "Rune-Cut", "of Alacrity"),
        affix_tags=("arcane", "bolt", "cast_speed", "proc"),
        damage_type="arcane",
        skill_bonus="Bolt +1 shard",
        proc_effect="chain",
        unique_effect="splinter storm",
        cast_speed=0.16,
        proc_chance=0.55,
    ),
    UniqueItemDefinition(
        "Blizzard Mantle",
        "Arcanist",
        "armor",
        defense=6,
        affixes=("Focused", "Grounded", "of the Moon"),
        affix_tags=("frost", "nova", "cast_speed", "ward"),
        damage_type="frost",
        skill_bonus="Nova radius",
        proc_effect="chill",
        unique_effect="glacial ward",
        cast_speed=0.12,
        proc_chance=0.45,
    ),
    UniqueItemDefinition(
        "Blood Psalm",
        "Acolyte",
        "weapon",
        power=9,
        affixes=("Grave-Hungering", "of Siphons", "of the Occult"),
        affix_tags=("blood", "shadow", "lifesteal", "cast_speed"),
        damage_type="shadow",
        skill_bonus="Blood leech",
        proc_effect="lifesteal",
        unique_effect="sanguine echo",
        cast_speed=0.07,
        lifesteal=0.14,
    ),
    UniqueItemDefinition(
        "Choir of Bone",
        "Acolyte",
        "armor",
        defense=6,
        affixes=("Hexwoven", "of Siphons", "Mirror-Barbed"),
        affix_tags=("spirit", "curse", "thorns", "lifesteal"),
        damage_type="shadow",
        skill_bonus="Nova ward",
        proc_effect="thorns",
        unique_effect="grave chorus",
        cast_speed=0.08,
        thorns=4,
        lifesteal=0.05,
    ),
    UniqueItemDefinition(
        "Skyfang Bow",
        "Ranger",
        "weapon",
        power=10,
        affixes=("Quickened", "of the Hunt", "Serrated"),
        affix_tags=("volley", "control", "attack_speed", "movement"),
        damage_type="physical",
        skill_bonus="Bolt +1 shard",
        proc_effect="bleed",
        unique_effect="sky volley",
        attack_speed=0.14,
        move_speed=0.05,
        proc_chance=0.45,
    ),
    UniqueItemDefinition(
        "Beastlord Harness",
        "Ranger",
        "armor",
        defense=6,
        affixes=("Fleet", "of the Hunt", "of Thorns"),
        affix_tags=("beast", "survival", "movement", "thorns"),
        skill_bonus="Dash tempo",
        proc_effect="snare",
        unique_effect="pack pursuit",
        move_speed=0.11,
        thorns=3,
        proc_chance=0.35,
    ),
)
