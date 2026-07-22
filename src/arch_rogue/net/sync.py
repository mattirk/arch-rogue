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

"""Host->joiner world serialization for 4.6 co-op.

The **floor descriptor** is the complete static state a joiner needs to
render a floor without advancing the host RNG — it reuses the run-save
serializers (``serialize_run_state`` / ``restore_run_state``) so the wire
format cannot drift from the proven save format. **Snapshots** carry the
dynamic world at ``MP_SNAPSHOT_RATE_HZ``: player actors every tick, plus a
slower wholesale refresh of item/trap/shrine/secret/guest/familiar lists and
player inventories (``slow``) that also fires immediately when list lengths
change.

Entity identity: every network-visible enemy gets a stable string
``entity_id`` from :func:`assign_entity_ids` (a monotonic per-run counter on
the host — never Python ``id()``). Snapshot application ignores stale
``(floor_revision, tick)`` pairs at the mixin layer.
"""

from __future__ import annotations

from typing import Any

from ..models import FloatingText, Player, Projectile, Tile
from ..save_system import _TRANSIENT_ENEMY_FIELDS

# Cadence divider: every Nth snapshot carries the slow wholesale payload.
SLOW_PAYLOAD_EVERY_TICKS = 5


# --- entity identity -------------------------------------------------------


def assign_entity_ids(game: Any) -> None:
    """Assign stable entity ids to enemies that do not have one yet."""

    counter = int(getattr(game, "_mp_entity_counter", 0))
    for enemy in game.enemies:
        if not enemy.entity_id:
            counter += 1
            enemy.entity_id = f"e{counter}"
    game._mp_entity_counter = counter


# --- players ---------------------------------------------------------------


def player_full_dict(game: Any, player: Player) -> dict[str, Any]:
    """Complete player serialization (floor descriptor / spawn payloads)."""

    return {
        "player_id": player.player_id,
        "display_name": player.display_name,
        "x": player.x,
        "y": player.y,
        "class_name": player.class_name,
        "max_hp": player.max_hp,
        "hp": player.hp,
        "max_mana": player.max_mana,
        "mana": player.mana,
        "max_stamina": player.max_stamina,
        "stamina": player.stamina,
        "speed": player.speed,
        "melee_bonus": player.melee_bonus,
        "spell_bonus": player.spell_bonus,
        "armor_bonus": player.armor_bonus,
        "level": player.level,
        "xp": player.xp,
        "next_xp": player.next_xp,
        "facing_x": player.facing_x,
        "facing_y": player.facing_y,
        "inventory": [game.item_to_dict(item) for item in player.inventory],
        "equipment": {
            slot: game.item_to_dict(item)
            for slot, item in player.equipment.items()
        },
        "skill_upgrades": list(player.skill_upgrades),
        "mastery_tokens": int(player.mastery_tokens),
        "status_effects": dict(player.status_effects),
        "gold": player.gold,
    }


def player_fast_dict(player: Player) -> dict[str, Any]:
    """Per-tick dynamic player fields (positions, vitals, cooldowns, pose)."""

    return {
        "id": player.player_id,
        "x": round(player.x, 3),
        "y": round(player.y, 3),
        "hp": player.hp,
        "mhp": player.max_hp,
        "mana": round(float(player.mana), 1),
        "mmana": player.max_mana,
        "sta": round(float(player.stamina), 1),
        "msta": player.max_stamina,
        "lvl": player.level,
        "xp": player.xp,
        "nxp": player.next_xp,
        "gold": player.gold,
        "fx": round(player.facing_x, 3),
        "fy": round(player.facing_y, 3),
        "mv": player.moving,
        "mx": round(player.move_x, 3),
        "my": round(player.move_y, 3),
        "loco": round(player.locomotion_anim_scale, 3),
        "name": player.display_name,
        "cls": player.class_name,
        "timers": [
            round(player.melee_timer, 2),
            round(player.bolt_timer, 2),
            round(player.dash_timer, 2),
            round(player.class_skill_timer, 2),
            round(player.time_skip_timer, 2),
        ],
        "status": dict(player.status_effects),
        "act": [player.action_state, round(player.action_ttl, 2)],
        "hf": [round(player.hit_flash, 2), round(player.hit_flash_duration, 2)],
        "tokens": player.mastery_tokens,
    }


def apply_player_fast(game: Any, player: Player, data: dict[str, Any]) -> None:
    old_hp = player.hp
    target_x = float(data.get("x", player.x))
    target_y = float(data.get("y", player.y))
    _set_lerp_target(player, target_x, target_y)
    player.hp = int(data.get("hp", player.hp))
    player.max_hp = int(data.get("mhp", player.max_hp))
    player.mana = float(data.get("mana", player.mana))
    player.max_mana = int(data.get("mmana", player.max_mana))
    player.stamina = float(data.get("sta", player.stamina))
    player.max_stamina = int(data.get("msta", player.max_stamina))
    player.level = int(data.get("lvl", player.level))
    player.xp = int(data.get("xp", player.xp))
    player.next_xp = int(data.get("nxp", player.next_xp))
    player.gold = int(data.get("gold", player.gold))
    player.facing_x = float(data.get("fx", player.facing_x))
    player.facing_y = float(data.get("fy", player.facing_y))
    player.moving = bool(data.get("mv", False))
    player.move_x = float(data.get("mx", player.move_x))
    player.move_y = float(data.get("my", player.move_y))
    player.locomotion_anim_scale = float(data.get("loco", 1.0))
    player.display_name = str(data.get("name", player.display_name))
    player.class_name = str(data.get("cls", player.class_name))
    timers = data.get("timers")
    if isinstance(timers, list) and len(timers) >= 5:
        player.melee_timer = float(timers[0])
        player.bolt_timer = float(timers[1])
        player.dash_timer = float(timers[2])
        player.class_skill_timer = float(timers[3])
        player.time_skip_timer = float(timers[4])
    status = data.get("status")
    if isinstance(status, dict):
        player.status_effects = {
            str(key): float(value) for key, value in status.items()
        }
    action = data.get("act")
    if isinstance(action, list) and len(action) >= 2:
        player.action_state = str(action[0])
        player.action_ttl = float(action[1])
        player.action_duration = max(player.action_duration, player.action_ttl)
    flash = data.get("hf")
    if isinstance(flash, list) and len(flash) >= 2:
        player.hit_flash = float(flash[0])
        player.hit_flash_duration = float(flash[1])
    player.mastery_tokens = int(data.get("tokens", player.mastery_tokens))
    if player.hp < old_hp:
        game.add_impact(
            player.x, player.y, (245, 95, 70), ttl=0.3, radius=0.4, kind="blood"
        )


def player_slow_dict(game: Any, player: Player) -> dict[str, Any]:
    return {
        "id": player.player_id,
        "inventory": [game.item_to_dict(item) for item in player.inventory],
        "equipment": {
            slot: game.item_to_dict(item)
            for slot, item in player.equipment.items()
        },
        "skill_upgrades": list(player.skill_upgrades),
        "speed": player.speed,
        "melee_bonus": player.melee_bonus,
        "spell_bonus": player.spell_bonus,
        "armor_bonus": player.armor_bonus,
    }


def apply_player_slow(game: Any, player: Player, data: dict[str, Any]) -> None:
    inventory = data.get("inventory")
    if isinstance(inventory, list):
        player.inventory = [
            item
            for item in (game.item_from_dict(entry) for entry in inventory)
            if item is not None
        ]
    equipment = data.get("equipment")
    if isinstance(equipment, dict):
        player.equipment = {
            "weapon": game.item_from_dict(equipment.get("weapon")),
            "armor": game.item_from_dict(equipment.get("armor")),
        }
    upgrades = data.get("skill_upgrades")
    if isinstance(upgrades, list):
        player.skill_upgrades = [str(key) for key in upgrades]
    player.speed = float(data.get("speed", player.speed))
    player.melee_bonus = int(data.get("melee_bonus", player.melee_bonus))
    player.spell_bonus = int(data.get("spell_bonus", player.spell_bonus))
    player.armor_bonus = int(data.get("armor_bonus", player.armor_bonus))


def build_player_from_full(game: Any, data: dict[str, Any]) -> Player:
    player = Player(
        float(data.get("x", 0.0)),
        float(data.get("y", 0.0)),
        class_name=str(data.get("class_name", "Warden")),
        max_hp=int(data.get("max_hp", 110)),
        hp=int(data.get("hp", 110)),
        max_mana=int(data.get("max_mana", 45)),
        mana=float(data.get("mana", 45)),
        max_stamina=int(data.get("max_stamina", 100)),
        stamina=float(data.get("stamina", 100)),
        speed=float(data.get("speed", 4.6)),
        melee_bonus=int(data.get("melee_bonus", 0)),
        spell_bonus=int(data.get("spell_bonus", 0)),
        armor_bonus=int(data.get("armor_bonus", 0)),
        level=int(data.get("level", 1)),
        xp=int(data.get("xp", 0)),
        next_xp=int(data.get("next_xp", 100)),
        facing_x=float(data.get("facing_x", 1.0)),
        facing_y=float(data.get("facing_y", 0.0)),
    )
    player.player_id = str(data.get("player_id", "p2"))
    player.display_name = str(data.get("display_name", ""))
    player.skill_upgrades = [
        str(key) for key in data.get("skill_upgrades", [])
    ]
    player.mastery_tokens = int(data.get("mastery_tokens", 0))
    player.status_effects = {
        str(key): float(value)
        for key, value in data.get("status_effects", {}).items()
    }
    player.gold = int(data.get("gold", 40))
    player.inventory = [
        item
        for item in (
            game.item_from_dict(entry) for entry in data.get("inventory", [])
        )
        if item is not None
    ]
    equipment = data.get("equipment", {})
    player.equipment = {
        "weapon": game.item_from_dict(equipment.get("weapon")),
        "armor": game.item_from_dict(equipment.get("armor")),
    }
    return player


# --- floor descriptor ------------------------------------------------------


def build_floor_state(game: Any) -> dict[str, Any]:
    """Serialize the complete static floor + all players for the joiner."""

    assign_entity_ids(game)
    data = game.serialize_run_state()
    data.pop("player", None)
    data["players"] = [player_full_dict(game, p) for p in game.players]
    # Story dialogue, cutscenes, and relic choice UI are host-controlled: the
    # joiner renders resolved outcomes only and must never open the modal UI.
    data["story_intro_pending"] = False
    data["active_cutscene"] = None
    # The joiner builds its own fog-of-war memory around its own actor.
    data["revealed_tiles"] = []
    data["enemies"] = [
        {
            **{
                key: value
                for key, value in enemy.__dict__.items()
                if key not in _TRANSIENT_ENEMY_FIELDS
            },
            "entity_id": enemy.entity_id,
        }
        for enemy in game.enemies
    ]
    # Record the tile baseline snapshots diff against.
    game._mp_tile_baseline = [list(column) for column in game.dungeon.tiles]
    game._mp_sent_enemy_ids = {enemy.entity_id for enemy in game.enemies}
    return data


def apply_floor_state(game: Any, state: dict[str, Any]) -> None:
    """Rebuild the joiner's world from a floor descriptor.

    Reuses ``restore_run_state`` for the heavy lifting (dungeon, enemies,
    items, story state, caches) with the joiner's own player as the primary,
    then rebuilds the two-player collection.
    """

    data = dict(state)
    players_data = [
        entry for entry in data.pop("players", []) if isinstance(entry, dict)
    ]
    local_id = getattr(game, "local_player_id", "p2")
    local_data = next(
        (
            entry
            for entry in players_data
            if str(entry.get("player_id", "")) == local_id
        ),
        None,
    )
    if local_data is None and players_data:
        local_data = players_data[0]
    if local_data is None:
        raise ValueError("floor descriptor carries no players")
    data["player"] = dict(local_data)
    # The joiner's HUD/music follow its own archetype, not the host's.
    data["selected_archetype"] = str(
        local_data.get("class_name", data.get("selected_archetype", "Warden"))
    )
    game.restore_run_state(data)
    local = game.player
    local.player_id = str(local_data.get("player_id", local_id))
    local.display_name = str(local_data.get("display_name", ""))
    players: list[Player] = []
    for entry in players_data:
        if str(entry.get("player_id", "")) == local.player_id:
            players.append(local)
        else:
            players.append(build_player_from_full(game, entry))
    players.sort(key=lambda p: p.player_id)
    game.players = players
    game._mp_tile_baseline = None
    game.snap_camera_to_player()
    game.update_revealed_tiles()


# --- snapshots -------------------------------------------------------------


def _set_lerp_target(actor: Any, x: float, y: float) -> None:
    """Store the authoritative position for between-snapshot smoothing.

    Distant corrections snap immediately (teleports, floor starts); small
    ones ease in the joiner's update loop so 15 Hz snapshots read as motion.
    """

    dx = x - actor.x
    dy = y - actor.y
    if dx * dx + dy * dy > 9.0:
        actor.x = x
        actor.y = y
        actor.net_x = None
        actor.net_y = None
    else:
        actor.net_x = x
        actor.net_y = y


def enemy_compact_dict(enemy: Any) -> dict[str, Any]:
    return {
        "id": enemy.entity_id,
        "x": round(enemy.x, 3),
        "y": round(enemy.y, 3),
        "hp": enemy.hp,
        "fx": round(enemy.facing_x, 3),
        "fy": round(enemy.facing_y, 3),
        "mv": enemy.moving,
        "mx": round(enemy.move_x, 3),
        "my": round(enemy.move_y, 3),
        "tg": enemy.telegraph,
        "wt": round(enemy.windup_time, 3),
        "wd": round(enemy.windup_duration, 3),
        "wa": enemy.windup_attack,
        "st": {key: round(value, 2) for key, value in enemy.statuses.items()},
    }


def apply_enemy_compact(game: Any, enemy: Any, data: dict[str, Any]) -> None:
    old_hp = enemy.hp
    _set_lerp_target(
        enemy, float(data.get("x", enemy.x)), float(data.get("y", enemy.y))
    )
    enemy.hp = int(data.get("hp", enemy.hp))
    enemy.facing_x = float(data.get("fx", enemy.facing_x))
    enemy.facing_y = float(data.get("fy", enemy.facing_y))
    enemy.moving = bool(data.get("mv", False))
    enemy.move_x = float(data.get("mx", enemy.move_x))
    enemy.move_y = float(data.get("my", enemy.move_y))
    enemy.locomotion_anim_scale = 1.0 if enemy.moving else 0.0
    enemy.telegraph = str(data.get("tg", ""))
    enemy.windup_time = float(data.get("wt", 0.0))
    enemy.windup_duration = float(data.get("wd", 0.0))
    enemy.windup_attack = str(data.get("wa", ""))
    statuses = data.get("st")
    if isinstance(statuses, dict):
        enemy.statuses = {
            str(key): float(value) for key, value in statuses.items()
        }
    if enemy.hp < old_hp:
        game.enemy_hit_flashes[id(enemy)] = 0.16
        game.enemy_hit_flash_durations[id(enemy)] = 0.16


def projectile_compact_dict(game: Any, projectile: Projectile) -> list[Any]:
    return [
        round(projectile.x, 3),
        round(projectile.y, 3),
        round(projectile.vx, 3),
        round(projectile.vy, 3),
        projectile.owner,
        list(projectile.color),
        round(projectile.ttl, 3),
        round(projectile.radius, 3),
        projectile.damage_type,
        projectile.archetype,
    ]


def projectile_from_compact(entry: list[Any]) -> Projectile | None:
    if not isinstance(entry, list) or len(entry) < 10:
        return None
    color = entry[5]
    if isinstance(color, list) and len(color) >= 3:
        color_tuple = (int(color[0]), int(color[1]), int(color[2]))
    else:
        color_tuple = (220, 220, 220)
    return Projectile(
        float(entry[0]),
        float(entry[1]),
        float(entry[2]),
        float(entry[3]),
        0,
        str(entry[4]),
        color_tuple,
        ttl=float(entry[6]),
        radius=float(entry[7]),
        damage_type=str(entry[8]),
        archetype=str(entry[9]),
    )


def _tile_patches(game: Any) -> list[list[int]]:
    baseline = getattr(game, "_mp_tile_baseline", None)
    if baseline is None:
        return []
    patches: list[list[int]] = []
    tiles = game.dungeon.tiles
    for x, column in enumerate(tiles):
        base_column = baseline[x]
        if column == base_column:
            continue
        for y, tile in enumerate(column):
            if tile != base_column[y]:
                patches.append([x, y, int(tile)])
                base_column[y] = tile
    return patches


def host_pause_reason(game: Any) -> str:
    if game.active_cutscene is not None or game.story_intro_pending:
        return "story"
    if game.state == "confirm_exit":
        return "paused"
    if game.shop_open:
        return "shop"
    if game.inventory_open or game.character_menu_open:
        return "menu"
    return ""


def build_snapshot_state(
    game: Any, *, include_slow: bool
) -> dict[str, Any]:
    assign_entity_ids(game)
    sent_ids = getattr(game, "_mp_sent_enemy_ids", None)
    if sent_ids is None:
        sent_ids = set()
        game._mp_sent_enemy_ids = sent_ids
    spawns: list[dict[str, Any]] = []
    for enemy in game.enemies:
        if enemy.entity_id not in sent_ids:
            sent_ids.add(enemy.entity_id)
            spawns.append(
                {
                    **{
                        key: value
                        for key, value in enemy.__dict__.items()
                        if key not in _TRANSIENT_ENEMY_FIELDS
                    },
                    "entity_id": enemy.entity_id,
                }
            )
    state: dict[str, Any] = {
        "players": [player_fast_dict(p) for p in game.players],
        "enemies": [enemy_compact_dict(e) for e in game.enemies if e.alive],
        "projectiles": [
            projectile_compact_dict(game, p) for p in game.projectiles
        ],
        "floaters": [
            [f.text, round(f.x, 2), round(f.y, 2), list(f.color), round(f.ttl, 2)]
            for f in game.floaters[-10:]
        ],
        "tile_patches": _tile_patches(game),
        "boss": {
            "engaged": bool(game.boss_engaged),
        },
        "paused": host_pause_reason(game),
        "depth": game.current_depth,
        "elapsed": round(game.elapsed, 2),
    }
    if spawns:
        state["spawns"] = spawns
    if include_slow:
        state["slow"] = {
            "players": [player_slow_dict(game, p) for p in game.players],
            "items": [game.item_to_dict(item) for item in game.items],
            "traps": [dict(trap.__dict__) for trap in game.traps],
            "shrines": [dict(shrine.__dict__) for shrine in game.shrines],
            "secrets": [dict(secret.__dict__) for secret in game.secrets],
            "familiars": [
                game.familiar_to_dict(familiar) for familiar in game.familiars
            ],
            "shop_met": [bool(keeper.met) for keeper in game.shopkeepers],
        }
    return state


def world_list_lengths(game: Any) -> tuple[int, ...]:
    """Cheap change signal: a length change forces an immediate slow payload."""

    return (
        len(game.items),
        len(game.traps),
        len(game.shrines),
        len(game.secrets),
        len(game.familiars),
        *(len(p.inventory) for p in game.players),
    )


def apply_snapshot_state(game: Any, state: dict[str, Any]) -> None:
    from ..models import Enemy, SecretCache, Shrine, Trap

    players_by_id = {p.player_id: p for p in game.players}
    for entry in state.get("players", []):
        if not isinstance(entry, dict):
            continue
        player = players_by_id.get(str(entry.get("id", "")))
        if player is not None:
            apply_player_fast(game, player, entry)

    # New enemies arrive as full spawn payloads before their compact updates.
    spawns = state.get("spawns", [])
    enemies_by_id = {e.entity_id: e for e in game.enemies if e.entity_id}
    for spawn in spawns:
        if not isinstance(spawn, dict):
            continue
        spawn_data = dict(spawn)
        entity_id = str(spawn_data.get("entity_id", ""))
        if not entity_id or entity_id in enemies_by_id:
            continue
        color = spawn_data.get("color")
        if isinstance(color, list):
            spawn_data["color"] = (int(color[0]), int(color[1]), int(color[2]))
        try:
            enemy = Enemy(**spawn_data)
        except TypeError:
            continue
        game.enemies.append(enemy)
        enemies_by_id[entity_id] = enemy

    compact = state.get("enemies", [])
    seen_ids: set[str] = set()
    for entry in compact:
        if not isinstance(entry, dict):
            continue
        entity_id = str(entry.get("id", ""))
        seen_ids.add(entity_id)
        enemy = enemies_by_id.get(entity_id)
        if enemy is not None:
            apply_enemy_compact(game, enemy, entry)
    removed = [
        enemy
        for enemy in game.enemies
        if enemy.entity_id and enemy.entity_id not in seen_ids
    ]
    if removed:
        for enemy in removed:
            game.add_impact(
                enemy.x,
                enemy.y,
                (200, 70, 60),
                ttl=0.4,
                radius=0.5,
                kind="burst",
            )
        game.enemies = [
            enemy
            for enemy in game.enemies
            if not enemy.entity_id or enemy.entity_id in seen_ids
        ]

    projectiles = state.get("projectiles")
    if isinstance(projectiles, list):
        game.projectiles = [
            projectile
            for projectile in (
                projectile_from_compact(entry) for entry in projectiles
            )
            if projectile is not None
        ]

    floaters = state.get("floaters")
    if isinstance(floaters, list):
        game.floaters = [
            FloatingText(
                str(entry[0]),
                float(entry[1]),
                float(entry[2]),
                (
                    int(entry[3][0]),
                    int(entry[3][1]),
                    int(entry[3][2]),
                )
                if isinstance(entry[3], list) and len(entry[3]) >= 3
                else (220, 220, 220),
                ttl=float(entry[4]),
            )
            for entry in floaters
            if isinstance(entry, list) and len(entry) >= 5
        ]

    patches = state.get("tile_patches", [])
    if isinstance(patches, list) and patches:
        for patch in patches:
            if not (isinstance(patch, list) and len(patch) >= 3):
                continue
            x, y, tile = int(patch[0]), int(patch[1]), int(patch[2])
            if 0 <= x < len(game.dungeon.tiles) and 0 <= y < len(
                game.dungeon.tiles[x]
            ):
                try:
                    game.dungeon.tiles[x][y] = Tile(tile)
                except ValueError:
                    continue
        game.tile_cache.clear()
        game.prewarm_tile_cache(prewarm_stair_animation=False)

    boss = state.get("boss")
    if isinstance(boss, dict):
        game.boss_engaged = bool(boss.get("engaged", False))

    game.mp_partner_pause_reason = str(state.get("paused", ""))
    game.elapsed = float(state.get("elapsed", game.elapsed))

    slow = state.get("slow")
    if isinstance(slow, dict):
        for entry in slow.get("players", []):
            if not isinstance(entry, dict):
                continue
            player = players_by_id.get(str(entry.get("id", "")))
            if player is not None:
                apply_player_slow(game, player, entry)
        items = slow.get("items")
        if isinstance(items, list):
            game.items = [
                item
                for item in (game.item_from_dict(entry) for entry in items)
                if item is not None
            ]
        traps = slow.get("traps")
        if isinstance(traps, list):
            try:
                game.traps = [Trap(**trap) for trap in traps]
            except TypeError:
                pass
        shrines = slow.get("shrines")
        if isinstance(shrines, list):
            try:
                game.shrines = [Shrine(**shrine) for shrine in shrines]
            except TypeError:
                pass
        secrets = slow.get("secrets")
        if isinstance(secrets, list):
            try:
                game.secrets = [SecretCache(**secret) for secret in secrets]
            except TypeError:
                pass
        familiars = slow.get("familiars")
        if isinstance(familiars, list):
            game.familiars = [
                game.familiar_from_dict(entry) for entry in familiars
            ]
        met_flags = slow.get("shop_met")
        if isinstance(met_flags, list):
            for keeper, met in zip(game.shopkeepers, met_flags):
                keeper.met = bool(met)


def lerp_networked_actors(game: Any, dt: float) -> None:
    """Ease joiner-side actors toward their authoritative positions."""

    blend = min(1.0, dt * 12.0)
    for actor in (*game.players, *game.enemies):
        target_x = getattr(actor, "net_x", None)
        target_y = getattr(actor, "net_y", None)
        if target_x is None or target_y is None:
            continue
        actor.x += (target_x - actor.x) * blend
        actor.y += (target_y - actor.y) * blend
        if abs(target_x - actor.x) < 0.01 and abs(target_y - actor.y) < 0.01:
            actor.x = target_x
            actor.y = target_y
            actor.net_x = None
            actor.net_y = None
