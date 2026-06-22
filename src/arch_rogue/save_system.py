# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import __version__
from .content import ARCHETYPES, DUNGEON_THEMES, RUN_MODIFIERS
from .dungeon import Dungeon
from .models import Enemy, Item, Player, Room, RunStats, SecretCache, Shrine, Tile, Trap


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
        )

    def serialize_run_state(self) -> dict[str, Any]:
        return {
            "version": 2,
            "release": __version__,
            "run_number": self.run_number,
            "current_depth": self.current_depth,
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
            },
            "enemies": [enemy.__dict__ for enemy in self.enemies],
            "items": [self.item_to_dict(item) for item in self.items],
            "traps": [trap.__dict__ for trap in self.traps],
            "shrines": [shrine.__dict__ for shrine in self.shrines],
            "secrets": [secret.__dict__ for secret in self.secrets],
            "run_stats": self.run_stats.__dict__,
        }

    def restore_run_state(self, data: dict[str, Any]) -> None:
        self.run_number = int(data.get("run_number", 1))
        self.current_depth = int(data.get("current_depth", 1))
        self.elapsed = float(data.get("elapsed", 0.0))
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

        dungeon_data = data["dungeon"]
        self.dungeon = Dungeon(self.rng)
        self.dungeon.tiles = [
            [Tile(int(tile)) for tile in column] for column in dungeon_data["tiles"]
        ]
        self.dungeon.rooms = [Room(**room) for room in dungeon_data["rooms"]]
        sx, sy = dungeon_data["stairs"]
        self.dungeon.stairs = (int(sx), int(sy))
        self.tile_cache.clear()

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
        self.traps = [Trap(**trap) for trap in data.get("traps", [])]
        self.shrines = [Shrine(**shrine) for shrine in data.get("shrines", [])]
        self.secrets = [SecretCache(**secret) for secret in data.get("secrets", [])]
        self.projectiles = []
        self.floaters = []
        self.slashes = []
        self.run_stats = RunStats(**data.get("run_stats", {}))
        self.inventory_open = False
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
            if int(data.get("version", 0)) not in (1, 2):
                self.last_load_error = (
                    "Saved run was created by an incompatible version."
                )
                return False
            self.restore_run_state(data)
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.last_load_error = f"Could not resume saved run: {exc}"
            return False
        self.play_sfx("start")
        return True

    def delete_save(self) -> None:
        try:
            self.save_path.unlink(missing_ok=True)
        except OSError:
            pass
