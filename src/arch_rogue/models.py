# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Matti Rita-Kasari
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

import random
from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .dungeon import Dungeon

Color = tuple[int, int, int]


@dataclass(frozen=True)
class Archetype:
    name: str
    description: str
    max_hp: int
    max_mana: int
    max_stamina: int
    speed: float
    melee_bonus: int = 0
    spell_bonus: int = 0
    armor_bonus: int = 0


@dataclass(frozen=True)
class DungeonTheme:
    name: str
    subtitle: str
    floor: Color
    floor_edge: Color
    wall_top: Color
    wall_left: Color
    wall_right: Color
    wall_edge: Color
    stair: Color
    accent: Color


@dataclass(frozen=True)
class RunModifier:
    name: str
    description: str
    enemy_hp_multiplier: float = 1.0
    enemy_damage_bonus: int = 0
    enemy_aggro_bonus: float = 0.0
    loot_bonus: float = 0.0
    trap_bonus: float = 0.0


@dataclass(frozen=True)
class SkillUpgrade:
    key: str
    archetype: str
    name: str
    description: str
    melee_bonus: int = 0
    spell_bonus: int = 0
    armor_bonus: int = 0
    max_hp_bonus: int = 0
    max_mana_bonus: int = 0
    max_stamina_bonus: int = 0
    speed_bonus: float = 0.0


@dataclass(frozen=True)
class SkillNode:
    """A route-based skill tree node.

    `tier` is 1..5 (depth from the root). `branch` names the route the node
    belongs to (e.g. "Bulwark" vs "Riposte" on the Warden). `prerequisites`
    lists node keys that must already be acquired before this node can be
    chosen; an empty tuple means the node is open at tier 1. Bonus fields mirror
    `SkillUpgrade` so the derived flat upgrade table stays in sync.

    Milestone 3.3 — skill points and combo trees:
      * `tags` labels the node for cross-branch interactions (e.g. "Frost",
        "Stealth", "Critical"). A node may carry tags that other branches'
        modifier nodes key off of.
      * `cross_branch_tags` lists tags this node boosts when acquired. Acquiring
        a node with `cross_branch_tags=("Frost",)` increases the effective rank
        of every acquired node that carries the "Frost" tag, regardless of which
        branch owns it. `cross_branch_bonus_melee` / `cross_branch_bonus_spell`
        are the per-tag bonuses applied to matching nodes.
    """

    key: str
    archetype: str
    name: str
    description: str
    tier: int = 1
    branch: str = ""
    prerequisites: tuple[str, ...] = ()
    melee_bonus: int = 0
    spell_bonus: int = 0
    armor_bonus: int = 0
    max_hp_bonus: int = 0
    max_mana_bonus: int = 0
    max_stamina_bonus: int = 0
    speed_bonus: float = 0.0
    tags: tuple[str, ...] = ()
    cross_branch_tags: tuple[str, ...] = ()
    cross_branch_bonus_melee: int = 0
    cross_branch_bonus_spell: int = 0


@dataclass(frozen=True)
class EliteModifier:
    name: str
    description: str
    hp_multiplier: float = 1.0
    damage_bonus: int = 0
    speed_multiplier: float = 1.0
    xp_bonus: int = 0
    color_shift: Color = (0, 0, 0)


@dataclass
class RunStats:
    kills: int = 0
    loot_picked_up: int = 0
    potions_used: int = 0
    shrines_used: int = 0
    secrets_opened: int = 0
    traps_triggered: int = 0
    damage_taken: int = 0
    boss_killed: bool = False
    elites_killed: int = 0
    minibosses_killed: int = 0
    upgrades_chosen: int = 0
    story_choices: int = 0
    guests_met: int = 0
    floors_cleared: int = 0
    challenge_rooms_cleared: int = 0
    cause_of_death: str = ""
    defeated_bosses: list[str] = field(default_factory=list)
    notable_loot: list[str] = field(default_factory=list)
    discoveries: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FloorPlan:
    depth: int
    theme_name: str
    threat_level: int
    encounter_key: str
    risk_tags: tuple[str, ...]
    reward_hint: str
    boss_key: str = ""
    dark: bool = False

    @property
    def preview(self) -> str:
        risks = ", ".join(self.risk_tags) if self.risk_tags else "unknown risks"
        reward = f" · reward: {self.reward_hint}" if self.reward_hint else ""
        boss = " · boss sign" if self.boss_key else ""
        darkness = " · dark level" if self.dark else ""
        return f"Threat {self.threat_level}: {risks}{boss}{darkness}{reward}"


class Tile(IntEnum):
    WALL = 0
    FLOOR = 1
    STAIRS = 2
    CLOSED_DOOR = 3
    OPEN_DOOR = 4


@dataclass(frozen=True)
class Room:
    x: int
    y: int
    w: int
    h: int

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.w // 2, self.y + self.h // 2

    def intersects(self, other: "Room", padding: int = 1) -> bool:
        return not (
            self.x + self.w + padding < other.x
            or other.x + other.w + padding < self.x
            or self.y + self.h + padding < other.y
            or other.y + other.h + padding < self.y
        )

    def random_point(self, rng: random.Random) -> tuple[float, float]:
        return rng.randrange(self.x + 1, self.x + self.w - 1) + 0.5, rng.randrange(
            self.y + 1, self.y + self.h - 1
        ) + 0.5


@dataclass
class Item:
    name: str
    slot: str
    power: int = 0
    defense: int = 0
    heal: int = 0
    mana: int = 0
    rarity: str = "Common"
    x: float = 0.0
    y: float = 0.0
    affixes: list[str] = field(default_factory=list)
    unidentified: bool = False
    unique_effect: str = ""
    cursed: bool = False
    damage_type: str = "physical"
    skill_bonus: str = ""
    proc_effect: str = ""
    affix_tags: list[str] = field(default_factory=list)
    attack_speed: float = 0.0
    cast_speed: float = 0.0
    move_speed: float = 0.0
    thorns: int = 0
    lifesteal: float = 0.0
    proc_chance: float = 0.0

    @property
    def display_name(self) -> str:
        if self.unidentified and self.slot in ("weapon", "armor"):
            return (
                "Unidentified Weapon" if self.slot == "weapon" else "Unidentified Armor"
            )
        return self.name

    @property
    def visible_rarity(self) -> str:
        return "Unidentified" if self.unidentified else self.rarity

    @property
    def label(self) -> str:
        if self.slot == "potion":
            return f"{self.display_name} (+{self.heal} HP)"
        if self.slot == "mana_potion":
            return f"{self.display_name} (+{self.mana} Mana)"
        if self.slot == "identify":
            return self.display_name
        if self.slot == "weapon":
            text = f"{self.display_name} (+{self.power} dmg)"
        elif self.slot == "armor":
            text = f"{self.display_name} (+{self.defense} armor)"
        else:
            text = self.display_name
        if self.unidentified:
            return f"{self.display_name} (unknown)"
        if self.affixes:
            text += f" — {', '.join(self.affixes)}"
        if self.damage_type and self.damage_type != "physical":
            text += f" — {self.damage_type}"
        if self.skill_bonus:
            text += f" — {self.skill_bonus}"
        if self.proc_effect:
            chance = (
                f" {int(round(self.proc_chance * 100))}%"
                if self.proc_chance > 0 and self.proc_chance < 1.0
                else ""
            )
            text += f" — {self.proc_effect}{chance}"
        speed_bits: list[str] = []
        if self.attack_speed:
            speed_bits.append(f"{self.attack_speed:+.0%} atk")
        if self.cast_speed:
            speed_bits.append(f"{self.cast_speed:+.0%} cast")
        if self.move_speed:
            speed_bits.append(f"{self.move_speed:+.0%} move")
        if speed_bits:
            text += f" — {' / '.join(speed_bits)}"
        if self.thorns:
            text += f" — {self.thorns} thorns"
        if self.lifesteal:
            text += f" — {self.lifesteal:.0%} leech"
        if self.unique_effect:
            text += f" — {self.unique_effect}"
        if self.cursed:
            text += " — cursed bargain"
        return text


@dataclass
class Trap:
    x: float
    y: float
    kind: str
    damage: int
    active: bool = True


@dataclass
class Shrine:
    x: float
    y: float
    kind: str
    used: bool = False


@dataclass
class Shopkeeper:
    x: float
    y: float
    name: str
    role: str
    inventory: list[Item] = field(default_factory=list)
    buy_multiplier: float = 0.45
    sell_multiplier: float = 1.15
    met: bool = False


@dataclass
class SecretCache:
    x: float
    y: float
    kind: str
    revealed: bool = False
    opened: bool = False


@dataclass(frozen=True)
class StoryChoice:
    key: str
    label: str
    intent: str
    outcome: str
    effects: dict[str, float] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)


@dataclass
class StoryBeat:
    depth: int
    title: str
    summary: str
    theme_name: str
    guest_name: str
    guest_role: str
    guest_motive: str
    dialogue: str
    choices: list[StoryChoice]
    resolved_choice: str = ""
    outcome: str = ""


@dataclass
class StoryState:
    seed: int
    title: str
    player_backstory: str
    objective: str
    antagonist: str
    faction: str
    rival_faction: str
    relic_name: str
    relic_form: str
    relic_temptation: str
    beats: list[StoryBeat]
    accent: Color = (190, 150, 245)
    flags: list[str] = field(default_factory=list)
    effects: dict[str, float] = field(default_factory=dict)
    log: list[str] = field(default_factory=list)


@dataclass
class StoryGuest:
    x: float
    y: float
    depth: int
    beat_index: int
    name: str
    role: str
    motive: str
    dialogue: str
    choices: list[StoryChoice]
    color: Color = (190, 150, 245)
    resolved: bool = False
    resolved_choice: str = ""
    met: bool = False


@dataclass
class FloatingText:
    text: str
    x: float
    y: float
    color: Color
    ttl: float = 0.9

    def update(self, dt: float) -> None:
        self.ttl -= dt
        self.y -= dt * 0.8


@dataclass
class ImpactEffect:
    x: float
    y: float
    color: Color
    ttl: float = 0.38
    radius: float = 0.35
    kind: str = "spark"
    max_ttl: float = 0.38
    # Archetype that produced this effect so cast/nova emanation graphics can
    # be themed per class (e.g. Arcanist's arcane ring vs Warden's bulwark wave).
    archetype: str = ""

    def update(self, dt: float) -> None:
        self.ttl -= dt

    @property
    def progress(self) -> float:
        return 1.0 - max(0.0, min(1.0, self.ttl / max(0.01, self.max_ttl)))


@dataclass
class Projectile:
    x: float
    y: float
    vx: float
    vy: float
    damage: int
    owner: str
    color: Color
    ttl: float = 1.6
    radius: float = 0.18
    damage_type: str = "physical"
    status_effect: str = ""
    status_duration: float = 0.0
    # Archetype that fired this player projectile so the bolt sprite can be
    # themed per class (arrows for Ranger, daggers for Rogue, etc.).
    archetype: str = ""
    # Milestone 3.7 — branch-progression projectile mechanics:
    #   * `pierce` is the number of additional enemies a projectile may pass
    #     through before expiring. 0 means it dies on the first hit.
    #   * `homing` in 0..1 steers the projectile toward the nearest enemy each
    #     frame (0 disables homing). Applied by the combat loop, not here, so
    #     the model stays free of enemy-list references.
    pierce: int = 0
    homing: float = 0.0
    # Enemy ids already damaged by this projectile so a piercing bolt does not
    # hit the same foe twice. Lazily populated by the combat loop.
    hit_enemies: set = field(default_factory=set)

    def update(self, dt: float, dungeon: "Dungeon") -> bool:
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.ttl -= dt
        return self.ttl > 0 and dungeon.is_floor(self.x, self.y)


@dataclass
class Enemy:
    name: str
    kind: str
    x: float
    y: float
    max_hp: int
    hp: int
    speed: float
    damage: int
    xp: int
    attack_range: float
    attack_cooldown: float
    attack_timer: float = 0.0
    aggro_range: float = 8.0
    color: Color = (170, 70, 65)
    facing_x: float = 1.0
    facing_y: float = 0.0
    moving: bool = False
    move_x: float = 1.0
    move_y: float = 0.0
    anim_time: float = 0.0
    elite_modifier: str = ""
    telegraph: str = ""
    role: str = "bruiser"
    damage_type: str = "physical"
    # Tile footprint side length for oversized actors. 1 = a normal single-tile
    # enemy; 2 = a 2x2 (4-tile) boss. Drives hit radius, collision radius, and
    # the on-screen sprite scale so bosses read as large, hulking threats.
    size: int = 1
    resistances: dict[str, float] = field(default_factory=dict)
    statuses: dict[str, float] = field(default_factory=dict)

    @property
    def alive(self) -> bool:
        return self.hp > 0

    @property
    def is_boss_encounter(self) -> bool:
        """True for the final boss and named floor guardians (not challenge-room minibosses)."""
        return self.kind == "boss" or self.role == "floor_boss"


@dataclass
class Player:
    x: float
    y: float
    class_name: str = "Warden"
    max_hp: int = 110
    hp: int = 110
    max_mana: int = 45
    mana: float = 45
    max_stamina: int = 100
    stamina: float = 100
    speed: float = 4.6
    melee_bonus: int = 0
    spell_bonus: int = 0
    armor_bonus: int = 0
    level: int = 1
    xp: int = 0
    next_xp: int = 60
    facing_x: float = 1.0
    facing_y: float = 0.0
    moving: bool = False
    move_x: float = 1.0
    move_y: float = 0.0
    anim_time: float = 0.0
    melee_timer: float = 0.0
    bolt_timer: float = 0.0
    dash_timer: float = 0.0
    nova_timer: float = 0.0
    inventory: list[Item] = field(default_factory=list)
    equipment: dict[str, Item | None] = field(
        default_factory=lambda: {"weapon": None, "armor": None}
    )
    skill_upgrades: list[str] = field(default_factory=list)
    skill_points: int = 0
    # Runtime cache of the combo bonus already applied to derived stats, so
    # `_apply_combo_bonus_delta` only applies the delta on changes. Not saved;
    # restored by `restore_run_state` / seeded to zero on a fresh player.
    _combo_applied: tuple[int, int, int] = (0, 0, 0)
    status_effects: dict[str, float] = field(default_factory=dict)
    gold: int = 40

    def has_upgrade(self, key: str) -> bool:
        return key in self.skill_upgrades

    def melee_damage(self) -> int:
        weapon = self.equipment.get("weapon")
        unique_bonus = 4 if weapon and weapon.unique_effect == "embers on hit" else 0
        curse_bonus = 3 if weapon and weapon.cursed else 0
        return (
            12
            + self.level * 2
            + self.melee_bonus
            + unique_bonus
            + curse_bonus
            + (weapon.power if weapon else 0)
        )

    def armor(self) -> int:
        armor = self.equipment.get("armor")
        unique_bonus = 0
        if armor:
            if armor.unique_effect == "steadfast bulwark":
                unique_bonus += 2
            if armor.unique_effect == "oathwall aegis":
                unique_bonus += 3
        curse_penalty = 1 if armor and armor.cursed else 0
        return max(
            0,
            self.armor_bonus
            + unique_bonus
            - curse_penalty
            + (armor.defense if armor else 0),
        )

    def gain_xp(self, amount: int) -> bool:
        self.xp += amount
        if self.xp < self.next_xp:
            return False
        self.xp -= self.next_xp
        self.level += 1
        self.next_xp = int(self.next_xp * 1.45)
        self.max_hp += 12
        self.hp = self.max_hp
        self.max_mana += 5
        self.mana = self.max_mana
        self.max_stamina += 5
        self.stamina = self.max_stamina
        # Milestone 3.3: level-ups award a skill point the player spends in the
        # character sheet, rather than auto-granting a node. This keeps build
        # choice in the player's hands.
        self.skill_points += 1
        return True
