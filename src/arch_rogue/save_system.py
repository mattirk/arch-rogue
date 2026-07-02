# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import __version__
from .constants import DUNGEON_DEPTH
from .content import (
    ARCHETYPES,
    DUNGEON_THEMES,
    HELL_DIFFICULTY_NAME,
    RUN_MODIFIERS,
    migrate_skill_keys,
)
from .dungeon import Dungeon
from .models import (
    Enemy,
    Item,
    Player,
    Room,
    RunStats,
    SecretCache,
    Shopkeeper,
    Shrine,
    Tile,
    Trap,
)
from .quest_assets import ActiveQuestCutscene
from .story import (
    StoryEngine,
    story_guest_from_dict,
    story_guest_to_dict,
    story_state_from_dict,
    story_state_to_dict,
)


class SaveLoadMixin:
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

    def serialize_run_state(self) -> dict[str, Any]:
        return {
            "version": 4,
            "release": __version__,
            "run_number": self.run_number,
            "current_depth": self.current_depth,
            "difficulty": self.difficulty_name,
            "run_music_seed": self.run_music_seed,
            "run_music_theme": self.run_music_theme,
            "floor_plan": [self.floor_plan_to_dict(plan) for plan in self.floor_plan],
            "story_seed": self.story_seed,
            "story_state": story_state_to_dict(self.story_state),
            "story_intro_pending": self.story_intro_pending,
            "active_cutscene": self.active_cutscene.to_dict()
            if self.active_cutscene is not None
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
                "shop_room_index": self.dungeon.shop_room_index,
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
                "skill_points": int(self.player.skill_points),
                "status_effects": dict(self.player.status_effects),
                "gold": self.player.gold,
            },
            "enemies": [enemy.__dict__ for enemy in self.enemies],
            "items": [self.item_to_dict(item) for item in self.items],
            "shopkeepers": [
                self.shopkeeper_to_dict(shopkeeper) for shopkeeper in self.shopkeepers
            ],
            "traps": [trap.__dict__ for trap in self.traps],
            "shrines": [shrine.__dict__ for shrine in self.shrines],
            "secrets": [secret.__dict__ for secret in self.secrets],
            "story_guests": [story_guest_to_dict(guest) for guest in self.story_guests],
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
        saved_shop_index = dungeon_data.get("shop_room_index")
        self.dungeon.shop_room_index = (
            int(saved_shop_index) if saved_shop_index is not None else None
        )
        self.tile_cache.clear()
        self.prewarm_tile_cache()

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
            melee_bonus=int(player_data.get("melee_bonus", 0)),
            spell_bonus=int(player_data.get("spell_bonus", 0)),
            armor_bonus=int(player_data.get("armor_bonus", 0)),
            level=int(player_data.get("level", 1)),
            xp=int(player_data.get("xp", 0)),
            next_xp=int(player_data.get("next_xp", 60)),
            facing_x=float(player_data.get("facing_x", 1.0)),
            facing_y=float(player_data.get("facing_y", 0.0)),
        )
        self.player.skill_upgrades = migrate_skill_keys(
            [str(upgrade) for upgrade in player_data.get("skill_upgrades", [])]
        )
        # Milestone 3.3: skill points default to 0 on older saves so existing
        # runs resume without a free point windfall.
        self.player.skill_points = int(player_data.get("skill_points", 0))
        # Seed the combo-bonus baseline so future node picks only apply the
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

        self.enemies = [Enemy(**enemy) for enemy in data.get("enemies", [])]
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
        self.active_cutscene = ActiveQuestCutscene.from_dict(
            data.get("active_cutscene")
        )
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

    def save_run(self) -> bool:
        self.last_save_error = ""
        if self.state != "playing":
            return False
        try:
            self.save_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = Path(f"{self.save_path}.tmp")
            tmp_path.write_text(
                json.dumps(self.serialize_run_state(), indent=2), encoding="utf-8"
            )
            tmp_path.replace(self.save_path)
        except (OSError, TypeError, ValueError) as exc:
            self.last_save_error = f"Could not save run: {exc}"
            return False
        return True

    def load_run(self) -> bool:
        self.last_load_error = ""
        try:
            data = json.loads(self.save_path.read_text(encoding="utf-8"))
            if int(data.get("version", 0)) not in (1, 2, 3, 4):
                self.last_load_error = (
                    "Saved run was created by an incompatible version."
                )
                return False
            self.restore_run_state(data)
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.last_load_error = f"Could not resume saved run: {exc}"
            return False
        self.sync_music()
        self.play_sfx("start")
        return True

    def delete_save(self) -> None:
        try:
            self.save_path.unlink(missing_ok=True)
        except OSError:
            pass
