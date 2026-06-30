from __future__ import annotations

from ..models import EliteModifier, RunModifier, SkillNode, SkillUpgrade

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


# --- Skill tree -------------------------------------------------------------
#
# Each archetype owns a route-based skill tree with five tiers of depth. A node
# belongs to a named branch (route) and may require one or more prior nodes
# before it can be chosen. Branches let players commit to a playstyle (e.g. a
# "Bulwark" tank route versus a "Riposte" counter route on the Warden) while
# shared tier-1 nodes keep early progression open.
#
# `SKILL_NODES` is the source of truth. `SKILL_UPGRADES` is derived from it so
# older code paths and saves that reference flat upgrade keys keep working: the
# legacy key is preserved as `SkillNode.key`, and the derived `SkillUpgrade`
# carries the same bonuses. New nodes added below expand the tree without
# breaking save compatibility because `player.skill_upgrades` only stores keys.
#
# Migration: a small `LEGACY_SKILL_KEYS` map rewrites obsolete keys from prior
# milestones onto their current node key so old saves resume cleanly.

SKILL_NODES: tuple[SkillNode, ...] = (
    # === Warden ===
    # Tier 1 — shared foundation.
    SkillNode(
        "warden_bulwark",
        "Warden",
        "Bulwark Training",
        "Melee bashes cleave wider and armor improves.",
        tier=1,
        branch="Bulwark",
        prerequisites=(),
        melee_bonus=1,
        armor_bonus=2,
        max_hp_bonus=10,
    ),
    SkillNode(
        "warden_riposte",
        "Warden",
        "Riposte Guard",
        "Taking melee hits costs less health and fuels counterattacks.",
        tier=1,
        branch="Riposte",
        prerequisites=(),
        melee_bonus=2,
        armor_bonus=1,
    ),
    # Tier 2 — branch commitments.
    SkillNode(
        "warden_aegis",
        "Warden",
        "Aegis Discipline",
        "Guard Step briefly hardens the Warden and Shield Bash staggers enemies.",
        tier=2,
        branch="Bulwark",
        prerequisites=("warden_bulwark",),
        armor_bonus=1,
        max_stamina_bonus=8,
    ),
    SkillNode(
        "warden_counter",
        "Warden",
        "Counter Stance",
        "Riposte strikes stagger attackers and grant brief stamina surge.",
        tier=2,
        branch="Riposte",
        prerequisites=("warden_riposte",),
        melee_bonus=2,
        max_stamina_bonus=6,
    ),
    # Tier 3 — cross-branch specialist nodes.
    SkillNode(
        "warden_bulwark_ward",
        "Warden",
        "Warden's Ward",
        "Bulwark Wave reaches farther and shields allies near the Warden.",
        tier=3,
        branch="Bulwark",
        prerequisites=("warden_aegis",),
        armor_bonus=2,
        max_hp_bonus=12,
    ),
    SkillNode(
        "warden_riposte_edge",
        "Warden",
        "Riposte Edge",
        "Counterattacks deal bonus damage to staggered foes.",
        tier=3,
        branch="Riposte",
        prerequisites=("warden_counter",),
        melee_bonus=3,
        armor_bonus=1,
    ),
    # Tier 4 — keystone choices.
    SkillNode(
        "warden_iron_vow",
        "Warden",
        "Iron Vow",
        "Armor mastery: heavy hits glance and stamina holds under pressure.",
        tier=4,
        branch="Bulwark",
        prerequisites=("warden_bulwark_ward",),
        armor_bonus=3,
        max_stamina_bonus=12,
        max_hp_bonus=14,
    ),
    SkillNode(
        "warden_reckoning",
        "Warden",
        "Reckoning",
        "Every counter echoes as a Guard Bolt and refunds mana.",
        tier=4,
        branch="Riposte",
        prerequisites=("warden_riposte_edge",),
        melee_bonus=4,
        spell_bonus=2,
        max_mana_bonus=10,
    ),
    # Tier 5 — capstone.
    SkillNode(
        "warden_unbreakable",
        "Warden",
        "Unbreakable Bulwark",
        "Below half health the Warden hardens and bashes clear surrounding foes.",
        tier=5,
        branch="Bulwark",
        prerequisites=("warden_iron_vow",),
        armor_bonus=4,
        max_hp_bonus=24,
        max_stamina_bonus=10,
    ),
    SkillNode(
        "warden_final_reckoning",
        "Warden",
        "Final Reckoning",
        "Counters execute wounded elites and refresh Guard Step.",
        tier=5,
        branch="Riposte",
        prerequisites=("warden_reckoning",),
        melee_bonus=5,
        spell_bonus=3,
        max_stamina_bonus=10,
    ),
    # === Rogue ===
    SkillNode(
        "rogue_precision",
        "Rogue",
        "Killing Precision",
        "Crits are deadlier and quick strikes cost less stamina.",
        tier=1,
        branch="Precision",
        prerequisites=(),
        melee_bonus=3,
        max_stamina_bonus=8,
    ),
    SkillNode(
        "rogue_smoke",
        "Rogue",
        "Smoke Step",
        "Evasion improves after using movement skills.",
        tier=1,
        branch="Shadow",
        prerequisites=(),
        speed_bonus=0.15,
        max_stamina_bonus=10,
    ),
    SkillNode(
        "rogue_venom",
        "Rogue",
        "Venomcraft",
        "Backstabs and knife fans poison wounded targets.",
        tier=2,
        branch="Precision",
        prerequisites=("rogue_precision",),
        melee_bonus=1,
        max_stamina_bonus=6,
    ),
    SkillNode(
        "rogue_shadowstep",
        "Rogue",
        "Shadowstep",
        "Smoke Burst blinds nearby foes and Shadow Dash costs less.",
        tier=2,
        branch="Shadow",
        prerequisites=("rogue_smoke",),
        speed_bonus=0.10,
        max_stamina_bonus=8,
    ),
    SkillNode(
        "rogue_executioner",
        "Rogue",
        "Executioner",
        "Crits on poisoned foes deal killing blow damage.",
        tier=3,
        branch="Precision",
        prerequisites=("rogue_venom",),
        melee_bonus=4,
        max_stamina_bonus=6,
    ),
    SkillNode(
        "rogue_night_veil",
        "Rogue",
        "Night Veil",
        "Standing in smoke regenerates stamina and grants dodge.",
        tier=3,
        branch="Shadow",
        prerequisites=("rogue_shadowstep",),
        speed_bonus=0.08,
        max_stamina_bonus=12,
    ),
    SkillNode(
        "rogue_crimson_edge",
        "Rogue",
        "Crimson Edge",
        "Killing blows refresh crit chance and bleed poisoned targets.",
        tier=4,
        branch="Precision",
        prerequisites=("rogue_executioner",),
        melee_bonus=5,
        max_hp_bonus=10,
    ),
    SkillNode(
        "rogue_phantom",
        "Rogue",
        "Phantom",
        "Shadow Dash leaves a decoy that draws enemy attacks.",
        tier=4,
        branch="Shadow",
        prerequisites=("rogue_night_veil",),
        speed_bonus=0.12,
        max_stamina_bonus=10,
    ),
    SkillNode(
        "rogue_deathmark",
        "Rogue",
        "Deathmark",
        "Marked foes fall to a single backstab chain.",
        tier=5,
        branch="Precision",
        prerequisites=("rogue_crimson_edge",),
        melee_bonus=6,
        max_stamina_bonus=10,
    ),
    SkillNode(
        "rogue_umbral",
        "Rogue",
        "Umbral Form",
        "Become briefly untouchable after each Shadow Dash.",
        tier=5,
        branch="Shadow",
        prerequisites=("rogue_phantom",),
        speed_bonus=0.14,
        max_stamina_bonus=12,
    ),
    # === Arcanist ===
    SkillNode(
        "arcanist_splinter",
        "Arcanist",
        "Splintered Arcana",
        "Arc Bolt throws an extra shard.",
        tier=1,
        branch="Bolt",
        prerequisites=(),
        spell_bonus=3,
        max_mana_bonus=10,
    ),
    SkillNode(
        "arcanist_focus",
        "Arcanist",
        "Deep Focus",
        "Mana recovers faster and novas reach farther.",
        tier=1,
        branch="Nova",
        prerequisites=(),
        spell_bonus=2,
        max_mana_bonus=14,
    ),
    SkillNode(
        "arcanist_permafrost",
        "Arcanist",
        "Permafrost Sigils",
        "Frost Nova chills longer and Arc Bolt exploits chilled foes.",
        tier=2,
        branch="Nova",
        prerequisites=("arcanist_focus",),
        spell_bonus=2,
        max_mana_bonus=8,
    ),
    SkillNode(
        "arcanist_overload",
        "Arcanist",
        "Arc Overload",
        "Bolts split on impact and pierce the first foe.",
        tier=2,
        branch="Bolt",
        prerequisites=("arcanist_splinter",),
        spell_bonus=3,
        max_mana_bonus=8,
    ),
    SkillNode(
        "arcanist_glacial",
        "Arcanist",
        "Glacial Tide",
        "Frost Nova freezes chilled foes in place briefly.",
        tier=3,
        branch="Nova",
        prerequisites=("arcanist_permafrost",),
        spell_bonus=3,
        max_mana_bonus=10,
    ),
    SkillNode(
        "arcanist_pierce",
        "Arcanist",
        "Piercing Arc",
        "Bolts pierce two foes and ricochet toward elites.",
        tier=3,
        branch="Bolt",
        prerequisites=("arcanist_overload",),
        spell_bonus=4,
        max_mana_bonus=8,
    ),
    SkillNode(
        "arcanist_blizzard",
        "Arcanist",
        "Blizzard Heart",
        "Standing in chilled air grants mana shield and faster casts.",
        tier=4,
        branch="Nova",
        prerequisites=("arcanist_glacial",),
        spell_bonus=4,
        max_mana_bonus=14,
        armor_bonus=1,
    ),
    SkillNode(
        "arcanist_storm",
        "Arcanist",
        "Storm Sigil",
        "Bolts chain lightning between nearby foes.",
        tier=4,
        branch="Bolt",
        prerequisites=("arcanist_pierce",),
        spell_bonus=5,
        max_mana_bonus=12,
    ),
    SkillNode(
        "arcanist_absolute_zero",
        "Arcanist",
        "Absolute Zero",
        "Frost Nova freezes the floor, slowing all enemies in range.",
        tier=5,
        branch="Nova",
        prerequisites=("arcanist_blizzard",),
        spell_bonus=5,
        max_mana_bonus=16,
    ),
    SkillNode(
        "arcanist_arc_tyrant",
        "Arcanist",
        "Arc Tyrant",
        "Bolts seek elites and overload on kill, refilling mana.",
        tier=5,
        branch="Bolt",
        prerequisites=("arcanist_storm",),
        spell_bonus=6,
        max_mana_bonus=14,
    ),
    # === Acolyte ===
    SkillNode(
        "acolyte_sanguine",
        "Acolyte",
        "Sanguine Rite",
        "Blood skills leech more life at close range.",
        tier=1,
        branch="Blood",
        prerequisites=(),
        melee_bonus=1,
        spell_bonus=2,
        max_hp_bonus=8,
    ),
    SkillNode(
        "acolyte_veil",
        "Acolyte",
        "Veil of Ash",
        "Mana shields blunt harsher blows.",
        tier=1,
        branch="Veil",
        prerequisites=(),
        armor_bonus=1,
        max_mana_bonus=8,
    ),
    SkillNode(
        "acolyte_gravebind",
        "Acolyte",
        "Gravebind Covenant",
        "Blood Nova binds enemies and kills echo more life into the Acolyte.",
        tier=2,
        branch="Blood",
        prerequisites=("acolyte_sanguine",),
        spell_bonus=2,
        max_hp_bonus=6,
        max_mana_bonus=6,
    ),
    SkillNode(
        "acolyte_ashen",
        "Acolyte",
        "Ashen Ward",
        "Veil of Ash reflects damage and cleanses status on use.",
        tier=2,
        branch="Veil",
        prerequisites=("acolyte_veil",),
        armor_bonus=2,
        max_mana_bonus=10,
    ),
    SkillNode(
        "acolyte_blood_pact",
        "Acolyte",
        "Blood Pact",
        "Spend health to cast when mana runs dry; lifesteal intensifies.",
        tier=3,
        branch="Blood",
        prerequisites=("acolyte_gravebind",),
        spell_bonus=3,
        max_hp_bonus=10,
    ),
    SkillNode(
        "acolyte_spirit_host",
        "Acolyte",
        "Spirit Host",
        "Spirit Bolt summons a brief wraith that harries foes.",
        tier=3,
        branch="Veil",
        prerequisites=("acolyte_ashen",),
        spell_bonus=3,
        max_mana_bonus=10,
    ),
    SkillNode(
        "acolyte_crimson_maw",
        "Acolyte",
        "Crimson Maw",
        "Blood Nova devours weak foes, healing the Acolyte massively.",
        tier=4,
        branch="Blood",
        prerequisites=("acolyte_blood_pact",),
        spell_bonus=4,
        max_hp_bonus=14,
        melee_bonus=2,
    ),
    SkillNode(
        "acolyte_grave_chorus",
        "Acolyte",
        "Grave Chorus",
        "Wraiths persist longer and shield the Acolyte when struck.",
        tier=4,
        branch="Veil",
        prerequisites=("acolyte_spirit_host",),
        spell_bonus=4,
        max_mana_bonus=14,
        armor_bonus=2,
    ),
    SkillNode(
        "acolyte_sanguine_ascendant",
        "Acolyte",
        "Sanguine Ascendant",
        "Below half health, blood skills cost no mana and leech doubles.",
        tier=5,
        branch="Blood",
        prerequisites=("acolyte_crimson_maw",),
        spell_bonus=5,
        max_hp_bonus=20,
        melee_bonus=3,
    ),
    SkillNode(
        "acolyte_undying_veil",
        "Acolyte",
        "Undying Veil",
        "Once per floor, a fatal blow is absorbed by the veil.",
        tier=5,
        branch="Veil",
        prerequisites=("acolyte_grave_chorus",),
        spell_bonus=5,
        max_mana_bonus=16,
        armor_bonus=3,
    ),
    # === Ranger ===
    SkillNode(
        "ranger_snare",
        "Ranger",
        "Barbed Snares",
        "Control skills delay enemies longer.",
        tier=1,
        branch="Control",
        prerequisites=(),
        spell_bonus=2,
        max_stamina_bonus=8,
    ),
    SkillNode(
        "ranger_volley",
        "Ranger",
        "Volley Drills",
        "Multishot spreads into a wider fan.",
        tier=1,
        branch="Volley",
        prerequisites=(),
        melee_bonus=1,
        spell_bonus=2,
    ),
    SkillNode(
        "ranger_beastmark",
        "Ranger",
        "Beastmark Pursuit",
        "Vault refreshes momentum and marked shots hit controlled enemies harder.",
        tier=2,
        branch="Control",
        prerequisites=("ranger_snare",),
        melee_bonus=1,
        speed_bonus=0.12,
        max_stamina_bonus=6,
    ),
    SkillNode(
        "ranger_rapid",
        "Ranger",
        "Rapid Volley",
        "Multishot fires an extra arrow and reloads faster.",
        tier=2,
        branch="Volley",
        prerequisites=("ranger_volley",),
        melee_bonus=2,
        spell_bonus=2,
        max_stamina_bonus=6,
    ),
    SkillNode(
        "ranger_thornfield",
        "Ranger",
        "Thornfield",
        "Snares grow thorns, damaging foes that struggle in them.",
        tier=3,
        branch="Control",
        prerequisites=("ranger_beastmark",),
        spell_bonus=3,
        max_stamina_bonus=8,
    ),
    SkillNode(
        "ranger_piercing_volley",
        "Ranger",
        "Piercing Volley",
        "Arrows pierce the first foe and seek marked targets.",
        tier=3,
        branch="Volley",
        prerequisites=("ranger_rapid",),
        melee_bonus=3,
        spell_bonus=3,
    ),
    SkillNode(
        "ranger_hunter_drive",
        "Ranger",
        "Hunter's Drive",
        "Vault resets attack cooldowns and grants a brief speed surge.",
        tier=4,
        branch="Control",
        prerequisites=("ranger_thornfield",),
        speed_bonus=0.14,
        max_stamina_bonus=12,
        melee_bonus=2,
    ),
    SkillNode(
        "ranger_storm_volley",
        "Ranger",
        "Storm Volley",
        "Multishot arcs into a storm that hits all foes in a cone.",
        tier=4,
        branch="Volley",
        prerequisites=("ranger_piercing_volley",),
        melee_bonus=4,
        spell_bonus=4,
        max_stamina_bonus=8,
    ),
    SkillNode(
        "ranger_wild_domination",
        "Ranger",
        "Wild Domination",
        "Marked foes are rooted and struck by a beast companion.",
        tier=5,
        branch="Control",
        prerequisites=("ranger_hunter_drive",),
        spell_bonus=5,
        max_stamina_bonus=14,
        speed_bonus=0.10,
    ),
    SkillNode(
        "ranger_sky_quiver",
        "Ranger",
        "Sky Quiver",
        "Multishot becomes a relentless barrage while standing still.",
        tier=5,
        branch="Volley",
        prerequisites=("ranger_storm_volley",),
        melee_bonus=5,
        spell_bonus=5,
        max_stamina_bonus=10,
    ),
)


# Obsolete keys from earlier milestones mapped onto their current node key.
# Used by `migrate_skill_keys` so older saves resume against the new tree.
LEGACY_SKILL_KEYS: dict[str, str] = {
    # No renames yet — all original keys are preserved as node keys — but the
    # table is in place so future migrations stay save-compatible.
}


def migrate_skill_keys(keys: list[str]) -> list[str]:
    """Rewrite obsolete skill keys from older saves onto current node keys.

    Unknown keys are dropped so a save referencing a removed node does not
    poison the run; the player simply loses that upgrade on resume.
    """
    valid = {node.key for node in SKILL_NODES}
    migrated: list[str] = []
    for key in keys:
        canonical = LEGACY_SKILL_KEYS.get(str(key), str(key))
        if canonical in valid and canonical not in migrated:
            migrated.append(canonical)
    return migrated


def skill_node_by_key(key: str) -> SkillNode | None:
    for node in SKILL_NODES:
        if node.key == key:
            return node
    return None


def skill_nodes_for_archetype(archetype: str) -> tuple[SkillNode, ...]:
    return tuple(node for node in SKILL_NODES if node.archetype == archetype)


def skill_branches_for_archetype(archetype: str) -> tuple[str, ...]:
    """Branch names in first-seen order, used to lay out the tree columns."""
    branches: list[str] = []
    for node in SKILL_NODES:
        if node.archetype != archetype:
            continue
        if node.branch not in branches:
            branches.append(node.branch)
    return tuple(branches)


def skill_tree_max_tier(archetype: str) -> int:
    return max(
        (node.tier for node in SKILL_NODES if node.archetype == archetype),
        default=0,
    )


# Backwards-compatible flat upgrade table derived from the skill tree. Existing
# code paths (`grant_skill_upgrade`, `acquired_skill_upgrades`, save files) read
# from `SKILL_UPGRADES`; deriving it keeps that contract intact while the tree
# becomes the single source of truth for new progression code.
SKILL_UPGRADES: tuple[SkillUpgrade, ...] = tuple(
    SkillUpgrade(
        key=node.key,
        archetype=node.archetype,
        name=node.name,
        description=node.description,
        melee_bonus=node.melee_bonus,
        spell_bonus=node.spell_bonus,
        armor_bonus=node.armor_bonus,
        max_hp_bonus=node.max_hp_bonus,
        max_mana_bonus=node.max_mana_bonus,
        max_stamina_bonus=node.max_stamina_bonus,
        speed_bonus=node.speed_bonus,
    )
    for node in SKILL_NODES
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
