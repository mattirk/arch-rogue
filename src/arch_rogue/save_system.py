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

# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from . import __version__
from .constants import DUNGEON_DEPTH
from .content import (
    ARCHETYPES,
    DUNGEON_THEMES,
    HELL_DIFFICULTY_NAME,
    RUN_MODIFIERS,
    migrate_discipline_keys,
)
from .dungeon import (
    LEGACY_QUEST_GUEST_ROOM_KIND,
    QUEST_ROOM_KIND,
    SHOP_ROOM_KIND,
    SPECIAL_ROOM_DEFINITIONS,
    Dungeon,
)
from .models import (
    Enemy,
    Familiar,
    IdleNpc,
    Item,
    LightSource,
    Player,
    Room,
    RunStats,
    SecretCache,
    Shopkeeper,
    Shrine,
    SpecialRoom,
    Tile,
    Trap,
)
from .story import (
    ActiveQuestCutscene,
    MiniGameState,
    StoryEngine,
    story_guest_from_dict,
    story_guest_to_dict,
    story_state_from_dict,
    story_state_to_dict,
)


_TRANSIENT_ENEMY_FIELDS = frozenset(
    (
        "locomotion_anim_scale",
        "pending_locomotion_scale",
        "pending_locomotion_anim_scale",
        "sprite_direction",
        "knockback_vx",
        "knockback_vy",
        "windup_time",
        "windup_duration",
        "windup_attack",
        "windup_nx",
        "windup_ny",
        # 4.8.9 machine-intelligence AI state is host-session-only: ability
        # rotation timers, idle/engaged perception, target memory, strafe
        # side, and boss last-ability all rebuild from live play.
        "ability_timers",
        "ai_state",
        "alert_timer",
        "nav_latch",
        "yield_timer",
        "stuck_probe_x",
        "stuck_probe_y",
        "stuck_probe_timer",
        "memory_x",
        "memory_y",
        "strafe_sign",
        "last_ability",
        # 4.6 multiplayer entity ids are per-session network identities and
        # never belong in single-player run saves.
        "entity_id",
        # 4.7.12 kill-credit bookkeeping is host-session-only.
        "last_player_hit_id",
    )
)

# 4.8.10 NPC allies: transient combat state on IdleNpc/StoryGuest. Loading a
# run resumes with allies attack-ready, un-latched, and back on the wander
# driver until the ally update re-engages them.
_TRANSIENT_NPC_FIELDS = frozenset(
    (
        "attack_timer",
        "nav_latch",
        "combat_active",
    )
)

# Routine kills use a trailing-edge checkpoint so a combat burst produces one
# save instead of one durable filesystem flush per corpse. The hard deadline
# prevents a long, uninterrupted fight from postponing the checkpoint forever.
RUN_CHECKPOINT_QUIET_SECONDS = 1.5
RUN_CHECKPOINT_MAX_SECONDS = 6.0
RUN_CHECKPOINT_RETRY_SECONDS = 2.0


def _release_version_key(value: Any) -> tuple[int, int, int]:
    """Return a three-part numeric release key, defaulting malformed saves old."""

    core = str(value or "").partition("+")[0].partition("-")[0]
    try:
        parts = [int(part) for part in core.split(".")[:3]]
    except (TypeError, ValueError):
        return (0, 0, 0)
    padded = (parts + [0, 0, 0])[:3]
    return (padded[0], padded[1], padded[2])


class SaveLoadMixin:
    def reset_run_checkpoint(self) -> None:
        """Discard deferred-save scheduling state without touching the save file."""

        self._run_checkpoint_pending = False
        self._run_checkpoint_pending_since = 0.0
        self._run_checkpoint_due_at = 0.0

    def request_run_checkpoint(self) -> bool:
        """Coalesce a routine run mutation into a near-future durable save.

        This is intentionally distinct from :meth:`save_run`: callers at
        lifecycle, exit, floor, boss, and story boundaries still use
        ``save_run()`` and therefore remain immediate. Repeated requests move
        the quiet-period deadline, but never beyond the first request's hard
        deadline.
        """

        if getattr(self, "mp_active", False) or self.state != "playing":
            return False
        now = float(getattr(self, "elapsed", 0.0))
        if not getattr(self, "_run_checkpoint_pending", False):
            self._run_checkpoint_pending = True
            self._run_checkpoint_pending_since = now
        hard_deadline = (
            float(self._run_checkpoint_pending_since) + RUN_CHECKPOINT_MAX_SECONDS
        )
        self._run_checkpoint_due_at = min(
            now + RUN_CHECKPOINT_QUIET_SECONDS,
            hard_deadline,
        )
        return True

    def service_run_checkpoint(self) -> bool:
        """Write a due deferred checkpoint; return whether a save was written."""

        if not getattr(self, "_run_checkpoint_pending", False):
            return False
        if getattr(self, "mp_active", False) or self.state != "playing":
            return False
        now = float(getattr(self, "elapsed", 0.0))
        if now < float(getattr(self, "_run_checkpoint_due_at", 0.0)):
            return False
        return self.save_run()

    def _schedule_failed_run_save_retry(self) -> None:
        """Keep failed durable work dirty while avoiding an every-frame retry."""

        now = float(getattr(self, "elapsed", 0.0))
        self._run_checkpoint_pending = True
        self._run_checkpoint_pending_since = now
        self._run_checkpoint_due_at = now + RUN_CHECKPOINT_RETRY_SECONDS

    def item_to_dict(self, item: Item | None) -> dict[str, Any] | None:
        if item is None:
            return None
        return {
            "name": item.name,
            "slot": item.slot,
            "power": item.power,
            "defense": item.defense,
            "heal": item.heal,
            "mana": item.mana,
            "rarity": item.rarity,
            "x": item.x,
            "y": item.y,
            "affixes": list(item.affixes),
            "unidentified": item.unidentified,
            "unique_effect": item.unique_effect,
            "cursed": item.cursed,
            "damage_type": item.damage_type,
            "skill_bonus": item.skill_bonus,
            "proc_effect": item.proc_effect,
            "affix_tags": list(item.affix_tags),
            "attack_speed": item.attack_speed,
            "cast_speed": item.cast_speed,
            "move_speed": item.move_speed,
            "thorns": item.thorns,
            "lifesteal": item.lifesteal,
            "proc_chance": item.proc_chance,
        }

    def item_from_dict(self, data: dict[str, Any] | None) -> Item | None:
        if data is None:
            return None
        return Item(
            str(data["name"]),
            str(data["slot"]),
            power=int(data.get("power", 0)),
            defense=int(data.get("defense", 0)),
            heal=int(data.get("heal", 0)),
            mana=int(data.get("mana", 0)),
            rarity=str(data.get("rarity", "Common")),
            x=float(data.get("x", 0.0)),
            y=float(data.get("y", 0.0)),
            affixes=[str(affix) for affix in data.get("affixes", [])],
            unidentified=bool(data.get("unidentified", False)),
            unique_effect=str(data.get("unique_effect", "")),
            cursed=bool(data.get("cursed", False)),
            damage_type=str(data.get("damage_type", "physical")),
            skill_bonus=str(data.get("skill_bonus", "")),
            proc_effect=str(data.get("proc_effect", "")),
            affix_tags=[str(tag) for tag in data.get("affix_tags", [])],
            attack_speed=float(data.get("attack_speed", 0.0)),
            cast_speed=float(data.get("cast_speed", 0.0)),
            move_speed=float(data.get("move_speed", 0.0)),
            thorns=int(data.get("thorns", 0)),
            lifesteal=float(data.get("lifesteal", 0.0)),
            proc_chance=float(data.get("proc_chance", 0.0)),
        )

    def shopkeeper_to_dict(self, shopkeeper: Shopkeeper) -> dict[str, Any]:
        return {
            "x": shopkeeper.x,
            "y": shopkeeper.y,
            "name": shopkeeper.name,
            "role": shopkeeper.role,
            "inventory": [self.item_to_dict(item) for item in shopkeeper.inventory],
            "buy_multiplier": shopkeeper.buy_multiplier,
            "sell_multiplier": shopkeeper.sell_multiplier,
            "met": shopkeeper.met,
        }

    def shopkeeper_from_dict(self, data: dict[str, Any]) -> Shopkeeper:
        return Shopkeeper(
            float(data.get("x", 0.0)),
            float(data.get("y", 0.0)),
            str(data.get("name", "Dungeon Trader")),
            str(data.get("role", "Allied Shopkeeper")),
            inventory=[
                item
                for item in (
                    self.item_from_dict(item_data)
                    for item_data in data.get("inventory", [])
                )
                if item is not None
            ],
            buy_multiplier=float(data.get("buy_multiplier", 0.45)),
            sell_multiplier=float(data.get("sell_multiplier", 1.15)),
            met=bool(data.get("met", False)),
        )

    def idle_npc_to_dict(self, npc: IdleNpc) -> dict[str, Any]:
        return {
            "x": npc.x,
            "y": npc.y,
            "kind": npc.kind,
            "name": npc.name,
            "role": npc.role,
            "color": list(npc.color),
            # 4.8.10 combat-ally fields, additive-with-default: old saves
            # simply lack them and load as pacifist props (no schema bump).
            "max_hp": npc.max_hp,
            "hp": npc.hp,
            "damage": npc.damage,
            "attack_range": npc.attack_range,
            "attack_cooldown": npc.attack_cooldown,
            "combat_speed": npc.combat_speed,
            "aggressive": npc.aggressive,
            "greeter_id": npc.greeter_id,
            "home_x": npc.home_x,
            "home_y": npc.home_y,
        }

    def idle_npc_from_dict(self, data: dict[str, Any]) -> IdleNpc:
        raw_color = data.get("color", [200, 190, 170])
        if isinstance(raw_color, (list, tuple)) and len(raw_color) >= 3:
            color = (
                int(raw_color[0]),
                int(raw_color[1]),
                int(raw_color[2]),
            )
        else:
            color = (200, 190, 170)
        return IdleNpc(
            x=float(data.get("x", 0.0)),
            y=float(data.get("y", 0.0)),
            kind=str(data.get("kind", "")),
            name=str(data.get("name", "")),
            role=str(data.get("role", "")),
            color=color,
            max_hp=int(data.get("max_hp", 0)),
            hp=int(data.get("hp", 0)),
            damage=int(data.get("damage", 0)),
            attack_range=float(data.get("attack_range", 1.1)),
            attack_cooldown=float(data.get("attack_cooldown", 1.0)),
            combat_speed=float(data.get("combat_speed", 1.9)),
            aggressive=bool(data.get("aggressive", False)),
            greeter_id=str(data.get("greeter_id", "")),
            home_x=float(data.get("home_x", 0.0)),
            home_y=float(data.get("home_y", 0.0)),
        )

    def familiar_to_dict(self, familiar: Familiar) -> dict[str, Any]:
        return {
            "x": familiar.x,
            "y": familiar.y,
            "max_hp": familiar.max_hp,
            "hp": familiar.hp,
            "damage": familiar.damage,
            "speed": familiar.speed,
            "attack_range": familiar.attack_range,
            "attack_cooldown": familiar.attack_cooldown,
            "sprite_variant": familiar.sprite_variant,
            "kind": familiar.kind,
            "lifesteal": familiar.lifesteal,
            "unkillable": familiar.unkillable,
            "champion": familiar.champion,
            "attack_timer": familiar.attack_timer,
            "anim_time": familiar.anim_time,
            "facing_x": familiar.facing_x,
            "facing_y": familiar.facing_y,
            "command_mode": familiar.command_mode,
            "owner_id": familiar.owner_id,
        }

    def familiar_from_dict(self, data: dict[str, Any]) -> Familiar:
        command_mode = str(data.get("command_mode", "attack"))
        if command_mode not in ("attack", "follow"):
            command_mode = "attack"
        return Familiar(
            x=float(data.get("x", 0.0)),
            y=float(data.get("y", 0.0)),
            max_hp=int(data.get("max_hp", 20)),
            hp=int(data.get("hp", 20)),
            damage=int(data.get("damage", 6)),
            speed=float(data.get("speed", 3.2)),
            attack_range=float(data.get("attack_range", 1.25)),
            attack_cooldown=float(data.get("attack_cooldown", 0.85)),
            sprite_variant=int(data.get("sprite_variant", 0)),
            kind=str(data.get("kind", "spirit")),
            lifesteal=bool(data.get("lifesteal", False)),
            unkillable=bool(data.get("unkillable", False)),
            champion=bool(data.get("champion", False)),
            attack_timer=float(data.get("attack_timer", 0.0)),
            anim_time=float(data.get("anim_time", 0.0)),
            facing_x=float(data.get("facing_x", 1.0)),
            facing_y=float(data.get("facing_y", 0.0)),
            command_mode=command_mode,
            owner_id=str(data.get("owner_id", "p1")),
        )

    def _reconcile_storm_bonus_rebalance(self, saved_release: Any) -> None:
        """Apply the 4.9.3 Storm-node stat deltas to an older active run.

        Player stats are saved as aggregates rather than rebuilt from
        disciplines. Without this one-time, release-gated adjustment, a 4.9.2
        Storm build would retain the old bonuses and then mix them with new
        values when buying deeper nodes.
        """

        if (
            _release_version_key(saved_release) >= (4, 9, 3)
            or self.player.class_name != "Arcanist"
        ):
            return
        acquired = set(self.player.skill_upgrades)
        spell_delta = sum(
            key in acquired
            for key in (
                "arcanist_chain_lightning",
                "arcanist_tempest",
                "arcanist_storm_caller",
                "arcanist_world_storm",
            )
        )
        mana_delta = 2 * sum(
            key in acquired
            for key in ("arcanist_charge", "arcanist_world_storm")
        )
        if spell_delta:
            self.player.spell_bonus = max(
                0, self.player.spell_bonus - spell_delta
            )
        if mana_delta:
            self.player.max_mana = max(1, self.player.max_mana - mana_delta)
            self.player.mana = min(self.player.mana, self.player.max_mana)

    def light_source_to_dict(self, light: LightSource) -> dict[str, Any]:
        return {
            "x": light.x,
            "y": light.y,
            "radius": light.radius,
            "color": list(light.color),
            "intensity": light.intensity,
            "flicker": light.flicker,
            "kind": light.kind,
            "elevation": light.elevation,
        }

    def light_source_from_dict(self, data: dict[str, Any]) -> LightSource:
        color = data.get("color", (235, 205, 110))
        if isinstance(color, list):
            color = (int(color[0]), int(color[1]), int(color[2]))
        return LightSource(
            x=float(data.get("x", 0.0)),
            y=float(data.get("y", 0.0)),
            radius=float(data.get("radius", 2.5)),
            color=color,
            intensity=float(data.get("intensity", 1.0)),
            ttl=None,
            flicker=bool(data.get("flicker", False)),
            kind=str(data.get("kind", "")),
            elevation=float(data.get("elevation", 0.0)),
        )

    def special_room_to_dict(self, special_room: SpecialRoom) -> dict[str, Any]:
        return special_room.to_dict()

    def _legacy_special_room(self, kind: str, room_index: Any) -> SpecialRoom | None:
        try:
            index = int(room_index)
        except (TypeError, ValueError):
            return None
        if not (0 <= index < len(self.dungeon.rooms)):
            return None
        definition = SPECIAL_ROOM_DEFINITIONS.get(kind)
        if definition is None:
            return None
        cx, cy = self.dungeon.rooms[index].center
        return SpecialRoom.from_definition(
            index,
            definition,
            reserved_tiles=[[cx, cy]],
            anchor_points={"center": [cx, cy]},
        )

    def _append_legacy_special_room_if_missing(
        self, rooms: list[SpecialRoom], kind: str, room_index: Any
    ) -> None:
        if any(room.kind == kind for room in rooms):
            return
        special_room = self._legacy_special_room(kind, room_index)
        if special_room is None:
            return
        if any(room.room_index == special_room.room_index for room in rooms):
            return
        rooms.append(special_room)

    def special_rooms_from_dungeon_data(
        self, dungeon_data: dict[str, Any]
    ) -> list[SpecialRoom]:
        raw_rooms = dungeon_data.get("special_rooms")
        if isinstance(raw_rooms, list):
            parsed: list[SpecialRoom] = []
            seen: set[tuple[str, int]] = set()
            for raw_room in raw_rooms:
                special_room = SpecialRoom.from_dict(raw_room)
                if special_room is None:
                    continue
                if special_room.kind == LEGACY_QUEST_GUEST_ROOM_KIND:
                    special_room.kind = QUEST_ROOM_KIND
                    special_room.display_name = SPECIAL_ROOM_DEFINITIONS[
                        QUEST_ROOM_KIND
                    ].display_name
                if not (0 <= special_room.room_index < len(self.dungeon.rooms)):
                    continue
                key = (special_room.kind, special_room.room_index)
                if key in seen:
                    continue
                seen.add(key)
                parsed.append(special_room)
            self._append_legacy_special_room_if_missing(
                parsed, SHOP_ROOM_KIND, dungeon_data.get("shop_room_index")
            )
            self._append_legacy_special_room_if_missing(
                parsed, QUEST_ROOM_KIND, dungeon_data.get("guest_room_index")
            )
            return parsed

        migrated: list[SpecialRoom] = []
        self._append_legacy_special_room_if_missing(
            migrated, SHOP_ROOM_KIND, dungeon_data.get("shop_room_index")
        )
        self._append_legacy_special_room_if_missing(
            migrated, QUEST_ROOM_KIND, dungeon_data.get("guest_room_index")
        )
        return migrated

    def serialize_run_state(self) -> dict[str, Any]:
        return {
            "version": 5,
            "release": __version__,
            "run_number": self.run_number,
            "current_depth": self.current_depth,
            "difficulty": self.difficulty_name,
            "run_music_seed": self.run_music_seed,
            "run_music_theme": self.run_music_theme,
            "floor_plan": [self.floor_plan_to_dict(plan) for plan in self.floor_plan],
            # Milestone 3.8: fog-of-war memory for light floors. Stored as a
            # flat [x, y] pair list so the save stays compact and version-agnostic.
            "revealed_tiles": [[x, y] for (x, y) in sorted(self.revealed_tiles)],
            "story_seed": self.story_seed,
            "story_state": story_state_to_dict(self.story_state),
            "story_intro_pending": self.story_intro_pending,
            "active_cutscene": self.active_cutscene.to_dict()
            if self.active_cutscene is not None
            else None,
            # 4.9.x mini-games are short, but saving from an app lifecycle
            # event must not discard the selected story continuation or allow a
            # once-only Garden/Soul reward to restart.  The additive field keeps
            # save schema 5 backward compatible.
            "active_mini_game": self.active_mini_game.to_dict()
            if self.active_mini_game is not None
            else None,
            "story_relic_depth": self.story_relic_depth,
            "story_relic_choice_key": self.story_relic_choice_key,
            "story_relic_position": list(self.story_relic_position)
            if self.story_relic_position is not None
            else None,
            "story_relic_collected": self.story_relic_collected,
            "story_relic_guidance_enabled": self.story_relic_guidance_enabled,
            "story_relic_guarded": self.story_relic_guarded,
            "elapsed": self.elapsed,
            "selected_archetype": self.selected_archetype.name,
            "theme": self.theme.name,
            "run_modifier": self.run_modifier.name,
            "dungeon": {
                "tiles": [
                    [int(tile) for tile in column] for column in self.dungeon.tiles
                ],
                "rooms": [room.__dict__ for room in self.dungeon.rooms],
                "stairs": list(self.dungeon.stairs),
                "special_rooms": [
                    self.special_room_to_dict(room)
                    for room in self.dungeon.special_rooms
                ],
                # Legacy index mirrors stay in the save during the migration window.
                "shop_room_index": self.dungeon.shop_room_index,
                "guest_room_index": self.dungeon.guest_room_index,
            },
            "player": {
                "x": self.player.x,
                "y": self.player.y,
                "class_name": self.player.class_name,
                "max_hp": self.player.max_hp,
                "hp": self.player.hp,
                "max_mana": self.player.max_mana,
                "mana": self.player.mana,
                "max_stamina": self.player.max_stamina,
                "stamina": self.player.stamina,
                "speed": self.player.speed,
                "shrine_move_bonus": self.player.shrine_move_bonus,
                "melee_bonus": self.player.melee_bonus,
                "spell_bonus": self.player.spell_bonus,
                "armor_bonus": self.player.armor_bonus,
                "level": self.player.level,
                "xp": self.player.xp,
                "next_xp": self.player.next_xp,
                "facing_x": self.player.facing_x,
                "facing_y": self.player.facing_y,
                "inventory": [
                    self.item_to_dict(item) for item in self.player.inventory
                ],
                "equipment": {
                    slot: self.item_to_dict(item)
                    for slot, item in self.player.equipment.items()
                },
                "skill_upgrades": list(self.player.skill_upgrades),
                "memory_tokens": int(self.player.memory_tokens),
                "status_effects": dict(self.player.status_effects),
                "gold": self.player.gold,
            },
            "enemies": [
                {
                    key: value
                    for key, value in enemy.__dict__.items()
                    if key not in _TRANSIENT_ENEMY_FIELDS
                }
                for enemy in self.enemies
            ],
            "items": [self.item_to_dict(item) for item in self.items],
            "shopkeepers": [
                self.shopkeeper_to_dict(shopkeeper) for shopkeeper in self.shopkeepers
            ],
            "traps": [trap.__dict__ for trap in self.traps],
            "shrines": [shrine.__dict__ for shrine in self.shrines],
            "secrets": [secret.__dict__ for secret in self.secrets],
            "story_guests": [story_guest_to_dict(guest) for guest in self.story_guests],
            "idle_npcs": [self.idle_npc_to_dict(npc) for npc in self.idle_npcs],
            "familiars": [
                self.familiar_to_dict(familiar) for familiar in self.familiars
            ],
            "light_sources": [
                self.light_source_to_dict(src) for src in self.light_sources
            ],
            "run_stats": self.run_stats.__dict__,
        }

    def restore_run_state(self, data: dict[str, Any]) -> None:
        self.run_number = int(data.get("run_number", 1))
        self.current_depth = int(data.get("current_depth", 1))
        saved_difficulty = str(data.get("difficulty", self.difficulty_name))
        if saved_difficulty == HELL_DIFFICULTY_NAME:
            self.hell_unlocked = True
        self.difficulty_name = self.sanitize_difficulty_name(saved_difficulty)
        self.run_music_seed = int(
            data.get(
                "run_music_seed",
                max(1, self.run_number * 65537 + self.current_depth * 4099),
            )
        )
        self.elapsed = float(data.get("elapsed", 0.0))
        self.run_music_theme = str(data.get("run_music_theme", data.get("theme", "")))
        self.floor_plan = [
            plan
            for plan in (
                self.floor_plan_from_dict(plan_data)
                for plan_data in data.get("floor_plan", [])
            )
            if plan is not None
        ]
        self.story_seed = int(
            data.get(
                "story_seed",
                max(1, self.run_music_seed * 17 + self.run_number * 7919),
            )
        )
        archetype_name = str(data.get("selected_archetype", ARCHETYPES[0].name))
        self.selected_archetype = next(
            (archetype for archetype in ARCHETYPES if archetype.name == archetype_name),
            ARCHETYPES[0],
        )
        theme_name = str(data.get("theme", DUNGEON_THEMES[0].name))
        self.theme = next(
            (theme for theme in DUNGEON_THEMES if theme.name == theme_name),
            DUNGEON_THEMES[0],
        )
        modifier_name = str(data.get("run_modifier", RUN_MODIFIERS[0].name))
        self.run_modifier = next(
            (modifier for modifier in RUN_MODIFIERS if modifier.name == modifier_name),
            RUN_MODIFIERS[0],
        )
        self.story_state = story_state_from_dict(data.get("story_state"))
        if self.story_state is None:
            self.story_state = StoryEngine.generate(
                self.story_seed,
                self.selected_archetype.name,
                self.run_number,
                self.theme.name,
                self.run_modifier.name,
            )
        if len(self.floor_plan) != DUNGEON_DEPTH:
            self.floor_plan = self.generate_floor_plan()
        self.apply_floor_plan_for_current_depth()
        self.story_intro_pending = bool(data.get("story_intro_pending", False))
        self.story_relic_depth = int(data.get("story_relic_depth", 0))
        self.story_relic_choice_key = str(data.get("story_relic_choice_key", ""))
        position_data = data.get("story_relic_position")
        self.story_relic_position = (
            (float(position_data[0]), float(position_data[1]))
            if isinstance(position_data, (list, tuple)) and len(position_data) >= 2
            else None
        )
        self.story_relic_collected = bool(data.get("story_relic_collected", False))
        self.story_relic_guidance_enabled = bool(
            data.get(
                "story_relic_guidance_enabled",
                bool(self.story_relic_choice_key and not self.story_relic_collected),
            )
        )
        self.story_relic_guarded = bool(data.get("story_relic_guarded", False))

        dungeon_data = data["dungeon"]
        self.dungeon = Dungeon(self.rng)
        self.dungeon.tiles = [
            [Tile(int(tile)) for tile in column] for column in dungeon_data["tiles"]
        ]
        self.dungeon.rooms = [Room(**room) for room in dungeon_data["rooms"]]
        sx, sy = dungeon_data["stairs"]
        self.dungeon.stairs = (int(sx), int(sy))
        self.dungeon.special_rooms = self.special_rooms_from_dungeon_data(dungeon_data)
        self.dungeon.refresh_solid_furnishing_tiles()
        self.tile_cache.clear()
        self.prewarm_tile_cache()


        # Milestone 3.8: restore fog-of-war memory for the current floor. Older
        # saves (pre-5) have no memory; the per-frame reveal pass will repopulate
        # around the player on the next update so the floor is never blank.
        revealed = set()
        for pair in data.get("revealed_tiles", []):
            if isinstance(pair, (list, tuple)) and len(pair) == 2:
                try:
                    revealed.add((int(pair[0]), int(pair[1])))
                except (TypeError, ValueError):
                    continue
        self.revealed_tiles = revealed

        player_data = data["player"]
        self.player = Player(
            float(player_data["x"]),
            float(player_data["y"]),
            class_name=str(player_data.get("class_name", self.selected_archetype.name)),
            max_hp=int(player_data.get("max_hp", self.selected_archetype.max_hp)),
            hp=int(player_data.get("hp", self.selected_archetype.max_hp)),
            max_mana=int(player_data.get("max_mana", self.selected_archetype.max_mana)),
            mana=float(player_data.get("mana", self.selected_archetype.max_mana)),
            max_stamina=int(
                player_data.get("max_stamina", self.selected_archetype.max_stamina)
            ),
            stamina=float(
                player_data.get("stamina", self.selected_archetype.max_stamina)
            ),
            speed=float(player_data.get("speed", self.selected_archetype.speed)),
            shrine_move_bonus=float(player_data.get("shrine_move_bonus", 0.0)),
            melee_bonus=int(player_data.get("melee_bonus", 0)),
            spell_bonus=int(player_data.get("spell_bonus", 0)),
            armor_bonus=int(player_data.get("armor_bonus", 0)),
            level=int(player_data.get("level", 1)),
            xp=int(player_data.get("xp", 0)),
            next_xp=int(player_data.get("next_xp", 100)),
            facing_x=float(player_data.get("facing_x", 1.0)),
            facing_y=float(player_data.get("facing_y", 0.0)),
        )
        # Pre-4.5.5 saves may place the player directly on stairs, which are now
        # player-solid. Move those saves to the first safe adjacent tile so the
        # restored run cannot begin trapped inside the shaft collision.
        player_tile = (int(self.player.x), int(self.player.y))
        if (
            self.dungeon.in_bounds(*player_tile)
            and self.dungeon.tiles[player_tile[0]][player_tile[1]] == Tile.STAIRS
        ):
            for offset_x, offset_y in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                candidate_x = player_tile[0] + offset_x + 0.5
                candidate_y = player_tile[1] + offset_y + 0.5
                if not self.dungeon.blocked_for_radius(
                    candidate_x, candidate_y, 0.27, block_stairs=True
                ):
                    self.player.x, self.player.y = candidate_x, candidate_y
                    break
        self.players = [self.player]
        self.player.skill_upgrades = migrate_discipline_keys(
            [str(upgrade) for upgrade in player_data.get("skill_upgrades", [])]
        )
        self._reconcile_storm_bonus_rebalance(data.get("release"))
        # Milestone 4.9.4: memory tokens default to 0 on older saves so existing
        # runs resume without a free token windfall. The legacy
        # `mastery_tokens` and `skill_points` keys remain accepted so banked
        # currency survives both terminology migrations.
        self.player.memory_tokens = int(
            player_data.get(
                "memory_tokens",
                player_data.get("mastery_tokens", player_data.get("skill_points", 0)),
            )
        )
        # Seed the combo-bonus baseline so future discipline picks only apply the
        # delta. The restored stat totals already reflect whatever combo bonus
        # was applied during the original run (3.3+ saves), and pre-3.3 saves
        # default to no combo bonus — matching the "new combo fields default to
        # no-op on older saves" contract.
        from .content import combo_bonus

        melee, spell, max_hp = combo_bonus(
            set(self.player.skill_upgrades), self.player.class_name
        )
        self.player._combo_applied = (melee, spell, max_hp)
        self.player.status_effects = {
            str(status): float(ttl)
            for status, ttl in player_data.get("status_effects", {}).items()
        }
        self.player.gold = int(player_data.get("gold", 40))
        self.player.inventory = [
            item
            for item in (
                self.item_from_dict(item) for item in player_data.get("inventory", [])
            )
            if item is not None
        ]
        equipment = player_data.get("equipment", {})
        self.player.equipment = {
            "weapon": self.item_from_dict(equipment.get("weapon")),
            "armor": self.item_from_dict(equipment.get("armor")),
        }

        # JSON serializes the Enemy color tuple as a list, so Enemy(**enemy)
        # would store a list back into ``enemy.color``. That breaks hashing
        # downstream (e.g. the draw_impact overlay cache key tuples a color in),
        # so normalize color (and any stray list fields) back to tuples here.
        restored_enemies: list[Enemy] = []
        for enemy in data.get("enemies", []):
            enemy_dict = dict(enemy)
            color = enemy_dict.get("color")
            if isinstance(color, list):
                enemy_dict["color"] = (
                    int(color[0]),
                    int(color[1]),
                    int(color[2]),
                )
            ability_keys = enemy_dict.get("ability_keys")
            if isinstance(ability_keys, list):
                enemy_dict["ability_keys"] = tuple(ability_keys)
            restored_enemies.append(Enemy(**enemy_dict))
        self.enemies = restored_enemies
        self.items = [
            item
            for item in (self.item_from_dict(item) for item in data.get("items", []))
            if item is not None
        ]
        self.shopkeepers = [
            self.shopkeeper_from_dict(shopkeeper)
            for shopkeeper in data.get("shopkeepers", [])
        ]
        self.traps = [Trap(**trap) for trap in data.get("traps", [])]
        self.shrines = [Shrine(**shrine) for shrine in data.get("shrines", [])]
        self.secrets = [SecretCache(**secret) for secret in data.get("secrets", [])]
        self.story_guests = [
            story_guest_from_dict(guest) for guest in data.get("story_guests", [])
        ]
        self.idle_npcs = [
            self.idle_npc_from_dict(npc) for npc in data.get("idle_npcs", [])
        ]
        # Familiars restore additively. Old saves without the field load with
        # an empty host; pre-Spirit-Beast entries default to the Acolyte spirit kind.
        self.familiars = [
            self.familiar_from_dict(familiar) for familiar in data.get("familiars", [])
        ]
        # Backfill required flavor-room performers into older saves, then reset
        # transient motion once for the final friendly roster.
        self._reconcile_bar_dancers()
        self._reconcile_garden_frogs()
        self._reconcile_lossless_souls()
        # 4.8.10: re-derive guest/soul aggression from story flags, roll ally
        # stats where older flags predate the combat fields, reset transient
        # ally state, and clamp allies out of solid furnishings.
        self._reconcile_npc_ally_state()
        # Soul-hall furnishings are physically solid; saves written while their
        # tiles were still walkable may leave a player standing inside one.
        # Move such players to the first safe adjacent tile (as with the
        # stairs-shaft backfill above) so the restored run cannot begin stuck.
        for player in self.players:
            tile = (int(player.x), int(player.y))
            # The collision box is shifted and inset (it can spill into a
            # furnishing's north/west neighbor tiles), so test the box probe
            # directly rather than anchor-tile membership.
            if not self.dungeon.furnishing_blocks_radius(
                player.x, player.y, 0.27
            ):
                continue
            for offset_x, offset_y in (
                (-1, 0), (1, 0), (0, -1), (0, 1),
                (-1, -1), (1, 1), (-1, 1), (1, -1),
            ):
                candidate_x = tile[0] + offset_x + 0.5
                candidate_y = tile[1] + offset_y + 0.5
                if not self.dungeon.blocked_for_radius(
                    candidate_x, candidate_y, 0.27, block_stairs=True
                ):
                    player.x, player.y = candidate_x, candidate_y
                    break
        self.reset_friendly_npc_runtime()
        # The full friendly and hostile roster is restored now — front-load
        # their sprite sources so the resumed fight does not stutter through
        # first-sight disk loads (mirrors the descent path).
        self.prewarm_actor_sprites()
        # Ambush Bell traps are floor-local transient runtime actors; saves load
        # with none, even if a future/newer save file happens to contain them.
        self.ambush_bells = []
        self.active_cutscene = ActiveQuestCutscene.from_dict(
            data.get("active_cutscene")
        )
        self.active_mini_game = MiniGameState.from_dict(
            data.get("active_mini_game")
        )
        if self.active_mini_game is not None:
            self._mini_game_instance_counter = max(
                int(getattr(self, "_mini_game_instance_counter", 0)),
                self.active_mini_game.instance_id,
            )
            self.mini_game_cursor = min(
                max(0, int(getattr(self, "mini_game_cursor", 0))),
                max(0, len(self.active_mini_game.board) - 1),
            )
        # Static floor lights restore additively. Saves without the field start
        # from an empty list, then reconciliation backfills current fixtures.
        # Transient pulses are visual-only and always start empty on load.
        self.light_sources = [
            self.light_source_from_dict(src)
            for src in data.get("light_sources", [])
        ]
        # Replace the legacy room-center bar torch with deterministic wall
        # sconces and backfill all static fixtures in older saves.
        self._reconcile_static_light_sources()
        self.lights = []
        active_asset = self.active_cutscene_asset() if self.active_cutscene else None
        active_node = self.active_cutscene_node() if self.active_cutscene else None
        if active_asset is None or active_node is None:
            self.active_cutscene = None
        if self.story_intro_pending and self.active_cutscene is None:
            guest = self.current_story_guest_for_depth()
            if guest is not None:
                self.start_quest_cutscene("story_guest_omen", guest)
        self.projectiles = []
        self.floaters = []
        self.slashes = []
        self.impact_effects = []
        self.screen_flash_ttl = 0.0
        self.reset_transient_visuals()
        self.run_stats = RunStats(**data.get("run_stats", {}))
        self.inventory_open = False
        self.shop_open = False
        self.active_shopkeeper = None
        self.shop_mode = "buy"
        self.shop_cursor = 0
        self.show_help = False
        self.state = "playing"

    def _interrupted_save_path(self) -> Path:
        return Path(f"{self.save_path}.tmp")

    def recover_interrupted_run_save(self) -> bool:
        """Promote a compatible interrupted temp save when the main file is absent/bad."""

        tmp_path = self._interrupted_save_path()
        if not tmp_path.exists():
            return False
        try:
            pending = json.loads(tmp_path.read_text(encoding="utf-8"))
            if int(pending.get("version", 0)) not in (1, 2, 3, 4, 5):
                return False
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return False
        if self.save_path.exists():
            try:
                current = json.loads(self.save_path.read_text(encoding="utf-8"))
                if int(current.get("version", 0)) in (1, 2, 3, 4, 5):
                    tmp_path.unlink(missing_ok=True)
                    return False
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                pass
        try:
            self.save_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path.replace(self.save_path)
        except OSError:
            return False
        self.recovered_interrupted_run = True
        return True

    def save_run(self) -> bool:
        """Immediately and durably save the current solo run.

        Routine mutations that can tolerate a short delay should call
        :meth:`request_run_checkpoint` instead. Keeping this method immediate
        preserves force-save semantics for every existing critical call site.
        """

        self.last_save_error = ""
        # 4.6: multiplayer runs never use the single-player run save. Refusing
        # here (rather than at each call site) guarantees backgrounding, floor
        # descents, and exit confirmation can never overwrite a solo save.
        if getattr(self, "mp_active", False):
            return False
        saving_from_exit_confirmation = (
            self.state == "confirm_exit"
            and getattr(self, "exit_previous_state", "") == "playing"
        )
        if self.state != "playing" and not saving_from_exit_confirmation:
            return False
        write_started = time.perf_counter()
        try:
            self.save_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._interrupted_save_path()
            payload = json.dumps(
                self.serialize_run_state(),
                ensure_ascii=False,
                separators=(",", ":"),
            )
            with tmp_path.open("w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            tmp_path.replace(self.save_path)
        except (OSError, TypeError, ValueError) as exc:
            self.last_save_error = f"Could not save run: {exc}"
            self._schedule_failed_run_save_retry()
            return False
        finally:
            # Serialize + fsync runs on a gameplay frame; feed its cost to the
            # perf monitor so a slow or busy disk shows up in hitch lines as
            # "save" instead of an inexplicably long update phase.
            monitor = getattr(self, "_mobile_performance_monitor", None)
            if monitor is not None:
                monitor.record_detail_phase(
                    "save", time.perf_counter() - write_started
                )
        self.reset_run_checkpoint()
        return True

    def load_run(self) -> bool:
        # Restoring a floor replays generation plus the 4.11.0 sprite
        # prewarm — seconds on older machines, so the loading screen owns
        # the display while it runs.
        with self.loading_screen("Rekindling the saved run..."):
            return self._load_run_impl()

    def _load_run_impl(self) -> bool:
        self.last_load_error = ""
        self.recover_interrupted_run_save()
        try:
            data = json.loads(self.save_path.read_text(encoding="utf-8"))
            if int(data.get("version", 0)) not in (1, 2, 3, 4, 5):
                self.last_load_error = (
                    "Saved run was created by an incompatible version."
                )
                return False
            self.restore_run_state(data)
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.last_load_error = f"Could not resume saved run: {exc}"
            return False
        self.reset_run_checkpoint()
        self.sync_music()
        self.play_sfx("start")
        return True

    def migrate_legacy_desktop_storage(self, storage_dir: Path) -> None:
        """Copy pre-5.0.1 home-directory dotfiles into the SDL pref dir.

        Desktop builds used ``~/.arch_rogue_options.json`` /
        ``~/.arch_rogue_run.json`` (plus the Steam achievement queue) until
        5.0.1 moved storage into the per-OS pref dir so Steam Auto-Cloud can
        sync it. Runs once per file: a legacy file is copied only while the
        new location does not exist yet, and the originals stay behind as a
        downgrade-safe backup. Never called for mobile or headless games.
        """

        legacy_pairs = (
            (".arch_rogue_options.json", self.options_path),
            (".arch_rogue_run.json", self.save_path),
            (
                ".arch_rogue_steam_queue.json",
                storage_dir / ".arch_rogue_steam_queue.json",
            ),
        )
        home = Path.home()
        for legacy_name, destination in legacy_pairs:
            legacy = home / legacy_name
            try:
                if legacy == destination:
                    continue
                if legacy.is_file() and not destination.exists():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(legacy.read_bytes())
            except OSError:
                # Storage migration must never block a launch; the game
                # simply starts fresh if the copy fails.
                continue

    def delete_save(self) -> None:
        # A co-op death/victory must never delete an existing solo save.
        if getattr(self, "mp_active", False):
            return
        try:
            self.save_path.unlink(missing_ok=True)
            self._interrupted_save_path().unlink(missing_ok=True)
        except OSError:
            pass
        self.reset_run_checkpoint()
