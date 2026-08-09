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

from ..dungeon import GARDEN_ROOM_KIND, LOSSLESS_SOUL_ROOM_KIND
from ..models import FloatingText, Player, Projectile, Tile
from ..save_system import _TRANSIENT_ENEMY_FIELDS
from ..story import story_guest_from_dict, story_guest_to_dict
from ..story.minigames import MiniGameState
from .protocol import sanitize_player_name

# Cadence divider: every Nth snapshot carries the slow wholesale payload.
SLOW_PAYLOAD_EVERY_TICKS = 5

# Joiner prediction reconciliation: while the joiner's own actor moves, the
# authoritative echo trails it along the motion axis by roughly
# speed x (intent latency + transit + snapshot age). That trail is expected,
# not error — the budget below (in tiles) is how much of it to attribute to
# latency and forgive, scaled by the measured RTT and capped under the
# 1.2-tile snap radius so genuine teleports still snap.
_PREDICTION_PIPELINE_SECONDS = 0.16  # intent slot + snapshot age + 2 frames
_PREDICTION_LAG_BUDGET_MAX_TILES = 1.1
_PREDICTION_EQUIPMENT_SPEED_CAP = 1.30

# Finished Garden/Soul interludes are monotonic floor state, so their compact
# room records ride the slow payload rather than every 15 Hz snapshot.  Codes
# are intentionally allowlisted and the list is capped even for malformed
# locally constructed dungeons.
_MINI_INTERLUDE_ROOM_LIMIT = 8
_MINI_INTERLUDE_OUTCOME_TO_CODE = {"won": "w", "lost": "l"}
_MINI_INTERLUDE_CODE_TO_OUTCOME = {
    code: outcome for outcome, code in _MINI_INTERLUDE_OUTCOME_TO_CODE.items()
}
_SOUL_CHOICE_TO_CODE = {"preserve": "p", "release": "r", "refuse": "x"}
_SOUL_CODE_TO_CHOICE = {
    code: choice for choice, code in _SOUL_CHOICE_TO_CODE.items()
}
_GARDEN_MINI_GAME_STATE_KEY = "garden_mini_game_outcome"
_SOUL_MINI_GAME_STATE_KEY = "soul_mini_game_outcome"


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
        "shrine_move_bonus": player.shrine_move_bonus,
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
        "memory_tokens": int(player.memory_tokens),
        # 4.9.4 transition mirror: mixed-version co-op is warning-only, so an
        # older joiner still needs the former full-payload key. Fast snapshots
        # already use the stable neutral key `tokens`.
        "mastery_tokens": int(player.memory_tokens),
        "raise_charges": int(player.raise_charges),
        "status_effects": dict(player.status_effects),
        "gold": player.gold,
    }


def _player_pose_fields(
    game: Any, player: Player
) -> tuple[list[Any], list[float]]:
    """The action pose + hit flash for ``player`` from its authoritative home.

    The local player's transient pose lives on Game-global fields (the
    single-player rendering contract reads ``game.player_action_*`` /
    ``game.player_hit_flash*`` for the local actor); a network partner's pose
    lives on its own actor. Serializing from the wrong home is why 4.7.0
    joiners never saw the host swing, cast, or flash.
    """

    if player.player_id == getattr(game, "local_player_id", ""):
        action = [
            game.player_action_state,
            round(game.player_action_ttl, 2),
            round(game.player_action_elapsed, 2),
            round(game.player_action_duration, 2),
        ]
        flash = [
            round(game.player_hit_flash, 2),
            round(game.player_hit_flash_duration, 2),
        ]
    else:
        action = [
            player.action_state,
            round(player.action_ttl, 2),
            round(player.action_elapsed, 2),
            round(player.action_duration, 2),
        ]
        flash = [round(player.hit_flash, 2), round(player.hit_flash_duration, 2)]
    return action, flash


def player_fast_dict(game: Any, player: Player) -> dict[str, Any]:
    """Per-tick dynamic player fields (positions, vitals, cooldowns, pose)."""

    action, flash = _player_pose_fields(game, player)
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
            round(player.bighit_timer, 2),
        ],
        "status": dict(player.status_effects),
        "act": action,
        "hf": flash,
        "tokens": player.memory_tokens,
        "raises": player.raise_charges,
    }


def apply_player_fast(game: Any, player: Player, data: dict[str, Any]) -> None:
    old_hp = player.hp
    is_local = player.player_id == getattr(game, "local_player_id", "")
    predicted = is_local and bool(game.mp_predicts_local_movement())
    target_x = float(data.get("x", player.x))
    target_y = float(data.get("y", player.y))
    if predicted:
        _reconcile_predicted_position(game, player, target_x, target_y)
    else:
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
    if not predicted:
        # A predicting joiner owns its walk state (facing, moving flag, lean
        # vector, locomotion scale) — the host's echo is ~a round trip stale
        # and would moonwalk the actor right after the player releases input
        # (and flip the sprite back to the old direction on a quick turn).
        player.facing_x = float(data.get("fx", player.facing_x))
        player.facing_y = float(data.get("fy", player.facing_y))
        player.moving = bool(data.get("mv", False))
        player.move_x = float(data.get("mx", player.move_x))
        player.move_y = float(data.get("my", player.move_y))
        player.locomotion_anim_scale = float(data.get("loco", 1.0))
    # Names travel host→joiner inside world payloads; sanitize on ingestion
    # so a modified peer cannot feed control characters into the HUD.
    player.display_name = sanitize_player_name(
        data.get("name", player.display_name)
    )
    player.class_name = str(data.get("cls", player.class_name))
    timers = data.get("timers")
    if isinstance(timers, list) and len(timers) >= 5:
        player.melee_timer = float(timers[0])
        player.bolt_timer = float(timers[1])
        player.dash_timer = float(timers[2])
        player.class_skill_timer = float(timers[3])
        player.time_skip_timer = float(timers[4])
        # 4.10 Big Hit cooldown rides as the 6th element; the >= 5 guard keeps
        # snapshots from a pre-bighit peer applying cleanly.
        if len(timers) >= 6:
            player.bighit_timer = float(timers[5])
    status = data.get("status")
    if isinstance(status, dict):
        player.status_effects = {
            str(key): float(value) for key, value in status.items()
        }
    action = data.get("act")
    if isinstance(action, list) and len(action) >= 2:
        state = str(action[0])
        ttl = float(action[1])
        elapsed = float(action[2]) if len(action) >= 3 else 0.0
        duration = float(action[3]) if len(action) >= 4 else ttl
        player.action_state = state
        player.action_ttl = ttl
        player.action_elapsed = elapsed
        player.action_duration = max(duration, ttl)
        if is_local and game.mp_is_joiner():
            _apply_local_action_pose(game, state, ttl, elapsed, duration)
    flash = data.get("hf")
    if isinstance(flash, list) and len(flash) >= 2:
        player.hit_flash = float(flash[0])
        player.hit_flash_duration = float(flash[1])
        if is_local and game.mp_is_joiner():
            # The local player's hit flash renders from the Game globals
            # (max-merge so a fresher local decay is never rewound).
            if player.hit_flash > game.player_hit_flash:
                game.player_hit_flash = player.hit_flash
                game.player_hit_flash_duration = player.hit_flash_duration
    player.memory_tokens = int(data.get("tokens", player.memory_tokens))
    player.raise_charges = int(data.get("raises", player.raise_charges))
    if player.hp < old_hp and is_local and game.mp_is_joiner():
        # Mirror take_player_damage's local screen feedback for the joiner's
        # own wounds (the host flashes only for its own). The blood impact
        # itself arrives through the replicated fx events.
        amount = old_hp - player.hp
        heavy_hit = amount >= player.max_hp * 0.18
        game.trigger_screen_flash(
            (160, 35, 32) if heavy_hit else (105, 24, 28),
            0.30 if heavy_hit else 0.18,
        )


def _apply_local_action_pose(
    game: Any, state: str, ttl: float, elapsed: float, duration: float
) -> None:
    """Adopt a replicated pose for the joiner's own actor (rendered from the
    Game-global fields). A pose the joiner already started locally (queued
    action feedback) is left to play out — the host echo of that same pose
    would only stretch it by the round trip."""

    if not state:
        return
    if game.player_action_ttl > 0.0 and game.player_action_state == state:
        return
    game.player_action_state = state
    game.player_action_ttl = ttl
    game.player_action_elapsed = elapsed
    game.player_action_duration = max(duration, ttl)


def _prediction_lag_budget(game: Any) -> float:
    """Tiles of trailing echo attributable to latency (RTT-scaled, capped)."""

    from ..combat._utils import PLAYER_MOVE_SPEED

    session = getattr(game, "mp_session", None)
    rtt_ms = float(getattr(session, "rtt_ms", 0.0)) if session is not None else 0.0
    return min(
        _PREDICTION_LAG_BUDGET_MAX_TILES,
        PLAYER_MOVE_SPEED
        * _PREDICTION_EQUIPMENT_SPEED_CAP
        * (_PREDICTION_PIPELINE_SECONDS + rtt_ms / 2000.0),
    )


def _reconcile_predicted_position(
    game: Any, actor: Any, target_x: float, target_y: float
) -> None:
    """Blend a locally predicted actor toward the authoritative position.

    Prediction runs the same movement code as the host, so genuine error
    stays tiny; big divergence means a host-side dash/teleport/knockback and
    snaps. While the actor moves, though, the echo *always* trails it along
    the motion axis by ~speed x latency. Treating that trail as error eroded
    the prediction back onto the stale echo (re-adding the round trip as felt
    input lag) and, on a quick direction reversal (the echo keeps travelling
    the old way for a full round trip), yanked the actor backward — the
    joiner's north/south turn lag. The trailing component inside the latency
    budget is therefore forgiven; perpendicular and forward error still ease
    at 25% per snapshot, and only the unexplained remainder can snap.
    """

    dx = target_x - actor.x
    dy = target_y - actor.y
    error = dx * dx + dy * dy
    if not actor.moving:
        # At rest, authority briefly overshoots the predicted stop (it keeps
        # the old vector until the zero intent lands, then walks back onto
        # the claimed stop). Pulling 25% per snapshot rendered that as an
        # uncomfortable slide; instead ignore sub-0.2-tile error outright
        # and ease anything larger gently.
        if error > 1.44:
            actor.x = target_x
            actor.y = target_y
        elif error > 0.04:
            actor.x += dx * 0.1
            actor.y += dy * 0.1
        actor.net_x = None
        actor.net_y = None
        return
    along = dx * actor.facing_x + dy * actor.facing_y
    if along < 0.0:
        # The echo sits behind the motion axis: forgive the latency trail.
        forgiven = max(along, -_prediction_lag_budget(game))
        dx -= actor.facing_x * forgiven
        dy -= actor.facing_y * forgiven
        error = dx * dx + dy * dy
    if error > 1.44:
        actor.x = target_x
        actor.y = target_y
    elif error > 0.0004:
        actor.x += dx * 0.25
        actor.y += dy * 0.25
    actor.net_x = None
    actor.net_y = None


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
        "shrine_move_bonus": player.shrine_move_bonus,
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
    player.shrine_move_bonus = float(
        data.get("shrine_move_bonus", player.shrine_move_bonus)
    )
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
        shrine_move_bonus=float(data.get("shrine_move_bonus", 0.0)),
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
    player.display_name = sanitize_player_name(data.get("display_name", ""))
    player.skill_upgrades = [
        str(key) for key in data.get("skill_upgrades", [])
    ]
    player.memory_tokens = int(
        data.get("memory_tokens", data.get("mastery_tokens", 0))
    )
    player.raise_charges = int(data.get("raise_charges", 1))
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
    # Mini-games likewise remain host-authoritative.  Their compact absolute
    # mirror arrives in the fast snapshot immediately after this descriptor;
    # never restore a save-owned authoritative state on the joiner.
    data["active_mini_game"] = None
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
    local.display_name = sanitize_player_name(local_data.get("display_name", ""))
    players: list[Player] = []
    for entry in players_data:
        if str(entry.get("player_id", "")) == local.player_id:
            players.append(local)
        else:
            players.append(build_player_from_full(game, entry))
    players.sort(key=lambda p: p.player_id)
    game.players = players
    game._mp_tile_baseline = None
    # The host clears its fx ring alongside each floor send; a fresh floor
    # (or rejoin replay) must not suppress the new floor's early events.
    game._mp_fx_applied_seq = 0
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
        # The attack/cast pose window is attack_timer's distance from
        # attack_cooldown (enemy_visual_state); without it a joiner's enemies
        # never leave idle/walk while striking.
        "at": round(enemy.attack_timer, 3),
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
    enemy.attack_timer = float(data.get("at", enemy.attack_timer))
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
    if getattr(game, "active_mini_game", None) is not None:
        return "minigame"
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
        "players": [player_fast_dict(game, p) for p in game.players],
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
        # Absolute, fast-path state: snapshots may be coalesced by both the
        # client and relay, and reconnect replays only the newest one.
        "mini_game": (
            game.active_mini_game.to_dict()
            if isinstance(getattr(game, "active_mini_game", None), MiniGameState)
            else None
        ),
        "depth": game.current_depth,
        "elapsed": round(game.elapsed, 2),
    }
    if spawns:
        state["spawns"] = spawns
    fx_events = game.mp_collect_fx()
    if fx_events:
        state["fx"] = fx_events
    if include_slow:
        slow = {
            "players": [player_slow_dict(game, p) for p in game.players],
            "items": [game.item_to_dict(item) for item in game.items],
            "traps": [dict(trap.__dict__) for trap in game.traps],
            "shrines": [dict(shrine.__dict__) for shrine in game.shrines],
            "secrets": [dict(secret.__dict__) for secret in game.secrets],
            "familiars": [
                game.familiar_to_dict(familiar) for familiar in game.familiars
            ],
            # 4.8.10: idle NPCs and story guests enter replication — combat
            # fields, positions, and (for guests) resolution flags — so the
            # joiner sees allies fight, bleed, and fall.
            "idle_npcs": [
                game.idle_npc_to_dict(npc) for npc in game.idle_npcs
            ],
            "story_guests": [
                story_guest_to_dict(guest) for guest in game.story_guests
            ],
            "shop_met": [bool(keeper.met) for keeper in game.shopkeepers],
            # 4.7.12: the joiner runs its own local shop UI against these
            # keeper inventories; without them a host- or partner-side trade
            # would leave the joiner's browse list stale.
            "shop_inv": [
                [game.item_to_dict(item) for item in keeper.inventory]
                for keeper in game.shopkeepers
            ],
            # 4.8.7 bar toast pilgrimage: keeps the joiner's tapped-barrel
            # hint/motes and toast tally honest after the host-side drink.
            "bar_toast": _bar_toast_dict(game),
        }
        mini_interludes = _mini_interlude_room_state(game)
        if mini_interludes:
            slow["room_games"] = mini_interludes
        state["slow"] = slow
    return state


def _mini_interlude_room_state(game: Any) -> list[list[Any]]:
    """Compact completed Garden/Soul state for guest hints and reconnects."""

    dungeon = getattr(game, "dungeon", None)
    records: list[list[Any]] = []
    for special in (
        getattr(dungeon, "special_rooms", ()) if dungeon is not None else ()
    ):
        try:
            room_index = int(special.room_index)
        except (AttributeError, TypeError, ValueError):
            continue
        if not 0 <= room_index <= 4095:
            continue
        room_state = getattr(special, "state", {})
        if not isinstance(room_state, dict):
            continue
        if getattr(special, "kind", "") == GARDEN_ROOM_KIND:
            outcome = _MINI_INTERLUDE_OUTCOME_TO_CODE.get(
                room_state.get(_GARDEN_MINI_GAME_STATE_KEY)
            )
            if outcome:
                records.append([room_index, "g", outcome])
        elif getattr(special, "kind", "") == LOSSLESS_SOUL_ROOM_KIND:
            outcome = _MINI_INTERLUDE_OUTCOME_TO_CODE.get(
                room_state.get(_SOUL_MINI_GAME_STATE_KEY),
                "",
            )
            choice = _SOUL_CHOICE_TO_CODE.get(
                room_state.get("soul_choice"),
                "",
            )
            if outcome or choice:
                records.append([room_index, "s", outcome, choice])
        if len(records) >= _MINI_INTERLUDE_ROOM_LIMIT:
            break
    return records


def _apply_mini_interlude_room_state(game: Any, records: Any) -> None:
    """Defensively merge allowlisted interlude results into matching rooms."""

    if not isinstance(records, list):
        return
    dungeon = getattr(game, "dungeon", None)
    special_rooms = getattr(dungeon, "special_rooms", ()) if dungeon else ()
    for record in records[:_MINI_INTERLUDE_ROOM_LIMIT]:
        if not isinstance(record, list) or len(record) not in (3, 4):
            continue
        room_index = record[0]
        if (
            not isinstance(room_index, int)
            or isinstance(room_index, bool)
            or not 0 <= room_index <= 4095
        ):
            continue
        kind_code = record[1]
        if not isinstance(kind_code, str):
            continue
        expected_kind = {
            "g": GARDEN_ROOM_KIND,
            "s": LOSSLESS_SOUL_ROOM_KIND,
        }.get(kind_code)
        if expected_kind is None:
            continue
        if (kind_code == "g" and len(record) != 3) or (
            kind_code == "s" and len(record) != 4
        ):
            continue
        special = next(
            (
                room
                for room in special_rooms
                if room.room_index == room_index and room.kind == expected_kind
            ),
            None,
        )
        if special is None or not isinstance(special.state, dict):
            continue
        outcome_code = record[2]
        outcome = (
            _MINI_INTERLUDE_CODE_TO_OUTCOME.get(outcome_code)
            if isinstance(outcome_code, str)
            else None
        )
        if outcome is not None:
            outcome_key = (
                _GARDEN_MINI_GAME_STATE_KEY
                if expected_kind == GARDEN_ROOM_KIND
                else _SOUL_MINI_GAME_STATE_KEY
            )
            special.state[outcome_key] = outcome
        if expected_kind == LOSSLESS_SOUL_ROOM_KIND and len(record) == 4:
            choice_code = record[3]
            soul_choice = (
                _SOUL_CODE_TO_CHOICE.get(choice_code)
                if isinstance(choice_code, str)
                else None
            )
            if soul_choice is not None:
                special.state["soul_choice"] = soul_choice


def _bar_toast_dict(game: Any) -> dict[str, Any]:
    bar_room = game.dungeon.special_room_for_kind("bar")
    return {
        "drunk": bool(
            bar_room is not None and bar_room.state.get("barrel_drunk")
        ),
        "toasted": int(game.run_stats.bars_toasted),
        "visited": int(game.run_stats.bars_visited),
    }


def world_list_lengths(game: Any) -> tuple[int, ...]:
    """Cheap change signal: a length change forces an immediate slow payload."""

    return (
        len(game.items),
        len(game.traps),
        len(game.shrines),
        len(game.secrets),
        len(game.familiars),
        # 4.8.10: NPC rosters and their aggressive counts, so a greeting, a
        # story resolution, or an ally death replicates promptly instead of
        # waiting out the slow-payload cadence.
        len(game.idle_npcs),
        sum(1 for npc in game.idle_npcs if npc.aggressive),
        len(game.story_guests),
        sum(1 for guest in game.story_guests if guest.aggressive),
        *(len(p.inventory) for p in game.players),
        *(len(keeper.inventory) for keeper in game.shopkeepers),
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
        # Death bursts/loot flashes arrive through the replicated fx events;
        # synthesizing one per removal here would double them.
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
        # Tile surfaces are variant caches keyed by (tile, seed, style) — not
        # position — and the per-position descriptor cache keys include the
        # tile value, so a patched tile misses cleanly and rebuilds lazily.
        # The old full clear + prewarm here stalled the joiner for the whole
        # theme's texture generation every time a door opened. Only the
        # mobile pre-baked floor layer actually depends on tile contents.
        game._mobile_floor_layer_cache = None

    fx_events = state.get("fx")
    if isinstance(fx_events, list):
        _apply_fx_events(game, fx_events)

    boss = state.get("boss")
    if isinstance(boss, dict):
        game.boss_engaged = bool(boss.get("engaged", False))

    if "mini_game" in state:
        # Malformed peer data clears the non-authoritative mirror instead of
        # reaching input/render code with arbitrary asset names or list sizes.
        raw_mini_game = state.get("mini_game")
        candidate = (
            MiniGameState.from_dict(raw_mini_game)
            if raw_mini_game is not None
            else None
        )
        current = getattr(game, "active_mini_game", None)
        if (
            candidate is not None
            and isinstance(current, MiniGameState)
            and current.instance_id == candidate.instance_id
            and current.kind == candidate.kind
        ):
            # Preserve identity so guest-side cosmetic countdown smoothing and
            # renderer caches survive the 15 Hz authoritative reconciliation.
            current.__dict__.update(candidate.__dict__)
        else:
            game.active_mini_game = candidate

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
        idle_npcs = slow.get("idle_npcs")
        if isinstance(idle_npcs, list):
            _apply_idle_npcs(game, idle_npcs)
        guests = slow.get("story_guests")
        if isinstance(guests, list):
            _apply_story_guests(game, guests)
        _apply_mini_interlude_room_state(game, slow.get("room_games"))
        met_flags = slow.get("shop_met")
        if isinstance(met_flags, list):
            for keeper, met in zip(game.shopkeepers, met_flags):
                keeper.met = bool(met)
        bar_toast = slow.get("bar_toast")
        if isinstance(bar_toast, dict):
            game.run_stats.bars_toasted = int(bar_toast.get("toasted", 0))
            game.run_stats.bars_visited = int(bar_toast.get("visited", 0))
            bar_room = game.dungeon.special_room_for_kind("bar")
            if bar_room is not None:
                if bar_toast.get("drunk"):
                    bar_room.state["barrel_drunk"] = True
                else:
                    bar_room.state.pop("barrel_drunk", None)
        shop_inventories = slow.get("shop_inv")
        if isinstance(shop_inventories, list):
            # In place: the joiner's open shop UI holds a reference to its
            # seed-generated keeper object.
            for keeper, entries in zip(game.shopkeepers, shop_inventories):
                if not isinstance(entries, list):
                    continue
                keeper.inventory[:] = [
                    item
                    for item in (
                        game.item_from_dict(entry) for entry in entries
                    )
                    if item is not None
                ]
            if game.shop_open:
                game.clamp_shop_cursor()


def _apply_idle_npcs(game: Any, entries: list[Any]) -> None:
    """Joiner: apply the replicated idle-NPC roster (4.8.10 combat allies).

    Positions ease through the shared lerp path; identity-stable rosters
    update in place so the beat-wander motion cache keyed by object identity
    never churns. A death (or any roster mismatch) rebuilds the list and
    resets the friendly-NPC runtime once.
    """

    entries = [entry for entry in entries if isinstance(entry, dict)]
    roster = game.idle_npcs
    in_place = len(entries) == len(roster) and all(
        str(entry.get("kind", "")) == npc.kind
        and str(entry.get("name", "")) == npc.name
        for entry, npc in zip(entries, roster)
    )
    if not in_place:
        game.idle_npcs = [game.idle_npc_from_dict(entry) for entry in entries]
        game.reset_friendly_npc_runtime()
        return
    for npc, entry in zip(roster, entries):
        _set_lerp_target(
            npc, float(entry.get("x", npc.x)), float(entry.get("y", npc.y))
        )
        npc.max_hp = int(entry.get("max_hp", npc.max_hp))
        npc.hp = int(entry.get("hp", npc.hp))
        npc.damage = int(entry.get("damage", npc.damage))
        npc.attack_range = float(entry.get("attack_range", npc.attack_range))
        npc.attack_cooldown = float(
            entry.get("attack_cooldown", npc.attack_cooldown)
        )
        npc.combat_speed = float(entry.get("combat_speed", npc.combat_speed))
        npc.aggressive = bool(entry.get("aggressive", npc.aggressive))
        npc.greeter_id = str(entry.get("greeter_id", npc.greeter_id))
        npc.home_x = float(entry.get("home_x", npc.home_x))
        npc.home_y = float(entry.get("home_y", npc.home_y))


def _apply_story_guests(game: Any, entries: list[Any]) -> None:
    """Joiner: apply replicated story guests (positions, combat, resolution)."""

    entries = [entry for entry in entries if isinstance(entry, dict)]
    roster = game.story_guests
    if len(entries) != len(roster):
        game.story_guests = [story_guest_from_dict(entry) for entry in entries]
        game.reset_friendly_npc_runtime()
        for guest in game.story_guests:
            guest.aggressive = bool(
                guest.resolved and guest.resolved_choice != "unanswered"
            )
        return
    for guest, entry in zip(roster, entries):
        _set_lerp_target(
            guest,
            float(entry.get("x", guest.x)),
            float(entry.get("y", guest.y)),
        )
        guest.max_hp = int(entry.get("max_hp", guest.max_hp))
        guest.hp = int(entry.get("hp", guest.hp))
        guest.resolved = bool(entry.get("resolved", guest.resolved))
        guest.resolved_choice = str(
            entry.get("resolved_choice", guest.resolved_choice)
        )
        guest.met = bool(entry.get("met", guest.met))
        # Derived exactly as on load: resolution through a real choice.
        guest.aggressive = bool(
            guest.resolved and guest.resolved_choice != "unanswered"
        )


def _apply_fx_events(game: Any, entries: list[Any]) -> None:
    """Spawn replicated transient visuals (impacts, slashes, screen and room flashes).

    Each event carries a host-monotonic sequence number; the snapshot resends
    a short trailing window so coalesced/dropped snapshots lose nothing, and
    the joiner spawns every event exactly once by high-water mark.
    """

    last_seq = int(getattr(game, "_mp_fx_applied_seq", 0))
    newest = last_seq
    for entry in entries:
        if not (isinstance(entry, list) and len(entry) >= 2):
            continue
        try:
            seq = int(entry[0])
        except (TypeError, ValueError):
            continue
        if seq <= last_seq:
            continue
        newest = max(newest, seq)
        kind = entry[1]
        try:
            if kind == "i" and len(entry) >= 11:
                game.add_impact(
                    float(entry[2]),
                    float(entry[3]),
                    (int(entry[4]), int(entry[5]), int(entry[6])),
                    ttl=float(entry[7]),
                    radius=float(entry[8]),
                    kind=str(entry[9]),
                    archetype=str(entry[10]),
                )
            elif kind == "s" and len(entry) >= 7:
                game.slashes.append(
                    (
                        float(entry[2]),
                        float(entry[3]),
                        float(entry[4]),
                        float(entry[5]),
                        float(entry[6]),
                    )
                )
            elif kind == "f" and len(entry) >= 6:
                game.trigger_screen_flash(
                    (int(entry[2]), int(entry[3]), int(entry[4])),
                    float(entry[5]),
                )
            elif kind == "rf" and len(entry) >= 8:
                # Frost Nova max-effect room flash: the joiner resolves the
                # room from its own dungeon copy, so only the anchor point,
                # tint, and fade travel the wire. trigger_room_flash cannot
                # echo — mp_record_fx is a no-op unless hosting.
                game.trigger_room_flash(
                    float(entry[2]),
                    float(entry[3]),
                    color=(int(entry[4]), int(entry[5]), int(entry[6])),
                    ttl=float(entry[7]),
                )
        except (TypeError, ValueError, IndexError, KeyError):
            continue
    game._mp_fx_applied_seq = newest


def lerp_networked_actors(game: Any, dt: float) -> None:
    """Ease joiner-side actors toward their authoritative positions."""

    blend = min(1.0, dt * 18.0)
    for actor in (
        *game.players,
        *game.enemies,
        *game.idle_npcs,
        *game.story_guests,
    ):
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
