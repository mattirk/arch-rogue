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

import math
from dataclasses import replace
from typing import Any

from .constants import (
    DARK_LEVEL_LIGHT_RADIUS,
    DUNGEON_DEPTH,
    LIGHT_LEVEL_SIGHT_RADIUS,
    PLAYER_HIT_RADIUS,
    SlashEffect,
)
from .content import (
    BOSS_DEFINITIONS,
    DUNGEON_THEMES,
    ENCOUNTER_TEMPLATES,
    RUN_MODIFIERS,
    BossDefinition,
    EncounterTemplate,
)
from .dungeon import MAP_H, MAP_W, Dungeon, Tile
from .models import (
    AmbushBell,
    Archetype,
    Enemy,
    Familiar,
    FloatingText,
    FloorPlan,
    IdleNpc,
    Item,
    LightSource,
    Player,
    Projectile,
    RunStats,
    SecretCache,
    Shopkeeper,
    Shrine,
    Trap,
)
from .story import story_beat_index_for_depth


_DARK_VISIBILITY_INNER_RADIUS = DARK_LEVEL_LIGHT_RADIUS - 1.1
_DARK_VISIBILITY_OUTER_RADIUS = DARK_LEVEL_LIGHT_RADIUS + 0.65
_DARK_VISIBILITY_INNER_RADIUS_SQUARED = _DARK_VISIBILITY_INNER_RADIUS**2
_DARK_VISIBILITY_OUTER_RADIUS_SQUARED = _DARK_VISIBILITY_OUTER_RADIUS**2


class RunFlowMixin:
    def save_exists(self) -> bool:
        if not self.save_path.exists() and hasattr(self, "recover_interrupted_run_save"):
            self.recover_interrupted_run_save()
        return self.save_path.exists()

    # --- Title menu navigation -------------------------------------------
    # Title rows (4.6): 0=One will descend, 1=Two will descend, 2=Resume,
    # 3=Options, 4=About. Resume (2) is only selectable when a save exists,
    # so arrow navigation skips it.
    TITLE_ROW_COUNT = 5
    TITLE_RESUME_ROW = 2

    def _title_row_enabled(self, index: int) -> bool:
        if index == self.TITLE_RESUME_ROW:
            return self.save_exists()
        return True

    def _next_title_selection(self, direction: int) -> int:
        count = self.TITLE_ROW_COUNT
        if count <= 0:
            return 0
        index = self.title_selection % count
        for _ in range(count):
            index = (index + direction) % count
            if self._title_row_enabled(index):
                return index
        return self.title_selection

    def _activate_title_selection(self) -> None:
        index = self.title_selection % self.TITLE_ROW_COUNT
        if not self._title_row_enabled(index):
            return
        if index == 0:
            self.state = "archetype_select"
        elif index == 1:
            self.start_mp_setup()
        elif index == self.TITLE_RESUME_ROW:
            self.load_run()
        elif index == 3:
            self.state = "options"
        elif index == 4:
            self.state = "about"
            self.licenses_scroll = 0

    def theme_by_name(self, name: str) -> Any:
        return next(
            (theme for theme in DUNGEON_THEMES if theme.name == name), self.theme
        )

    def encounter_template_by_key(self, key: str) -> EncounterTemplate:
        return next(
            (template for template in ENCOUNTER_TEMPLATES if template.key == key),
            ENCOUNTER_TEMPLATES[0],
        )

    def boss_definition_by_key(self, key: str) -> BossDefinition | None:
        return next((boss for boss in BOSS_DEFINITIONS if boss.key == key), None)

    def floor_plan_to_dict(self, plan: FloorPlan) -> dict[str, Any]:
        return {
            "depth": plan.depth,
            "theme_name": plan.theme_name,
            "threat_level": plan.threat_level,
            "encounter_key": plan.encounter_key,
            "risk_tags": list(plan.risk_tags),
            "reward_hint": plan.reward_hint,
            "boss_key": plan.boss_key,
            "dark": plan.dark,
        }

    def floor_plan_from_dict(self, data: Any) -> FloorPlan | None:
        if not isinstance(data, dict):
            return None
        try:
            return FloorPlan(
                depth=int(data.get("depth", 1)),
                theme_name=str(data.get("theme_name", self.theme.name)),
                threat_level=max(1, int(data.get("threat_level", 1))),
                encounter_key=str(data.get("encounter_key", "standard")),
                risk_tags=tuple(str(tag) for tag in data.get("risk_tags", [])),
                reward_hint=str(data.get("reward_hint", "steady loot")),
                boss_key=str(data.get("boss_key", "")),
                dark=bool(data.get("dark", False)),
            )
        except (TypeError, ValueError):
            return None

    def light_depths_for_run(self) -> set[int]:
        # Milestone 3.8: light floors use fog-of-war tile memory, while dark
        # floors stay lantern-only with no explored-tile memory. Dark floors are
        # now reserved for deeper runs only:
        #   depths 1-4  -> always light (fog-of-war memory enabled)
        #   depths 5+   -> 50% chance of being dark (so 50% light)
        light: set[int] = set()
        for depth in range(1, DUNGEON_DEPTH + 1):
            if depth < 5 or self.rng.random() >= 0.5:
                light.add(depth)
        return light

    def generate_floor_plan(self) -> list[FloorPlan]:
        plan: list[FloorPlan] = []
        previous_theme = self.theme.name
        light_depths = self.light_depths_for_run()
        story_theme_by_depth: dict[int, str] = {}
        if self.story_state is not None:
            story_theme_by_depth = {
                beat.depth: beat.theme_name for beat in self.story_state.beats
            }
        boss_depths = {3, 6, 9, DUNGEON_DEPTH}
        encounter_pool = [template for template in ENCOUNTER_TEMPLATES if template.key]
        mini_bosses = [boss for boss in BOSS_DEFINITIONS if not boss.final_boss]
        for depth in range(1, DUNGEON_DEPTH + 1):
            theme_name = story_theme_by_depth.get(depth, "")
            if not theme_name:
                choices = [
                    theme for theme in DUNGEON_THEMES if theme.name != previous_theme
                ]
                theme_name = self.rng.choice(choices or list(DUNGEON_THEMES)).name
            previous_theme = theme_name
            if depth == 1:
                encounter = self.encounter_template_by_key("standard")
            elif depth in boss_depths and depth != DUNGEON_DEPTH:
                encounter = self.encounter_template_by_key("challenge_room")
            else:
                encounter = self.rng.choice(encounter_pool)
            threat = 1 + depth // 2
            is_dark = depth not in light_depths
            risk_tags = [encounter.risk]
            if is_dark:
                risk_tags.append("darkness")
            if depth >= 5:
                risk_tags.append("escalating damage")
            if self.run_modifier.trap_bonus > 0.08 or encounter.trap_bonus > 0.12:
                risk_tags.append("heavy traps")
            if self.run_modifier.name == "Elite Hunt" or encounter.elite_bonus >= 0.12:
                risk_tags.append("elite pressure")
            boss_key = ""
            reward_hint = encounter.reward
            if depth in boss_depths:
                if depth == DUNGEON_DEPTH:
                    boss_key = "gate_tyrant"
                    reward_hint = "gate relic and clear record"
                    risk_tags.append("final boss")
                else:
                    themed_bosses = [
                        boss for boss in mini_bosses if theme_name in boss.theme_names
                    ]
                    boss = self.rng.choice(themed_bosses or mini_bosses)
                    boss_key = boss.key
                    reward_hint = boss.loot_hook
                    risk_tags.append(boss.subtitle)
                    threat += 1
            plan.append(
                FloorPlan(
                    depth=depth,
                    theme_name=theme_name,
                    threat_level=min(10, threat),
                    encounter_key=encounter.key,
                    risk_tags=tuple(risk_tags[:5]),
                    reward_hint=reward_hint,
                    boss_key=boss_key,
                    dark=is_dark,
                )
            )
        return plan

    def current_floor_plan(self) -> FloorPlan | None:
        cache = getattr(self, "_frame_cache", None)
        if cache is not None:
            if (
                cache.get("current_floor_plan_depth") == self.current_depth
                and "current_floor_plan" in cache
            ):
                cached = cache["current_floor_plan"]
                return cached if cached is not False else None
            plan = next(
                (plan for plan in self.floor_plan if plan.depth == self.current_depth),
                None,
            )
            cache["current_floor_plan_depth"] = self.current_depth
            cache["current_floor_plan"] = plan if plan is not None else False
            return plan
        return next(
            (plan for plan in self.floor_plan if plan.depth == self.current_depth), None
        )

    def next_floor_plan(self) -> FloorPlan | None:
        return next(
            (plan for plan in self.floor_plan if plan.depth == self.current_depth + 1),
            None,
        )

    def current_floor_needs_boss_arena(self) -> bool:
        plan = self.current_floor_plan()
        return bool(plan and plan.boss_key)

    def floor_plan_summary(self, plan: FloorPlan | None = None) -> str:
        plan = plan or self.current_floor_plan()
        if plan is None:
            return "Uncharted depth"
        encounter = self.encounter_template_by_key(plan.encounter_key)
        return f"{encounter.title} · {plan.preview}"

    def apply_floor_plan_for_current_depth(self) -> None:
        plan = self.current_floor_plan()
        if plan is None:
            return
        self.theme = self.theme_by_name(plan.theme_name)
        self.run_music_theme = self.theme.name

    def is_current_floor_dark(self) -> bool:
        cache = getattr(self, "_frame_cache", None)
        if cache is not None:
            if (
                cache.get("is_current_floor_dark_depth") == self.current_depth
                and "is_current_floor_dark" in cache
            ):
                return bool(cache["is_current_floor_dark"])
            plan = self.current_floor_plan()
            dark = bool(plan and plan.dark)
            cache["is_current_floor_dark_depth"] = self.current_depth
            cache["is_current_floor_dark"] = dark
            return dark
        plan = self.current_floor_plan()
        return bool(plan and plan.dark)

    def set_current_floor_dark(self, dark: bool) -> None:
        self.floor_plan = [
            replace(plan, dark=dark) if plan.depth == self.current_depth else plan
            for plan in self.floor_plan
        ]
        # Fog-of-war memory only makes sense on light floors; reset it whenever
        # the floor's darkness state changes so a freshly-lit floor starts
        # from the player's current sight instead of stale memory.
        self.reset_revealed_tiles()
        self.update_revealed_tiles()

    def toggle_current_floor_dark(self) -> bool:
        dark = not self.is_current_floor_dark()
        self.set_current_floor_dark(dark)
        if hasattr(self, "floaters") and hasattr(self, "player"):
            self.floaters.append(
                FloatingText(
                    "Darkness falls" if dark else "Light returns",
                    self.player.x,
                    self.player.y - 0.55,
                    self.theme.accent if dark else (235, 220, 170),
                    ttl=1.3,
                )
            )
        self.trigger_screen_flash((12, 16, 28) if dark else (235, 220, 170), ttl=0.18)
        if self.state == "playing":
            self.save_run()
        return dark

    def light_distance_to_player(self, x: float, y: float) -> float:
        return math.hypot(x - self.player.x, y - self.player.y)

    def can_see_world_position(self, x: float, y: float, margin: float = 0.0) -> bool:
        # Whether a live actor/object at (x, y) is currently in the player's
        # sight. On dark floors this is the lantern radius; on light floors it is
        # the wider fog-of-war sight radius. Terrain memory (revealed_tiles) is
        # separate: a tile can be remembered but no longer currently visible.
        radius = (
            DARK_LEVEL_LIGHT_RADIUS
            if self.is_current_floor_dark()
            else LIGHT_LEVEL_SIGHT_RADIUS
        ) + margin
        if radius < 0.0:
            return False
        dx = x - self.player.x
        dy = y - self.player.y
        return dx * dx + dy * dy <= radius * radius

    def reset_revealed_tiles(self) -> None:
        # Drop all fog-of-war memory for the current floor. Called on floor
        # changes and whenever a floor's darkness state is toggled.
        self.revealed_tiles = set()
        self._last_reveal_state = None

    def is_tile_revealed(self, x: int, y: int) -> bool:
        return (x, y) in self.revealed_tiles

    def update_revealed_tiles(self) -> None:
        # Fog-of-war reveal pass for light floors. Tiles within the sight radius
        # are remembered forever; dark floors keep their lantern-only model
        # (explored areas stay dark) and never build memory. Distance-based
        # reveal mirrors the dark-floor lantern model and keeps the hot path
        # cheap (no per-tile line-of-sight walk).
        if self.is_current_floor_dark():
            self._last_reveal_state = None
            return
        px = self.player.x
        py = self.player.y
        revealed = self.revealed_tiles
        previous = getattr(self, "_last_reveal_state", None)
        if previous is not None:
            previous_tiles, previous_depth, previous_x, previous_y = previous
            if (
                previous_tiles is revealed
                and previous_depth == self.current_depth
                and previous_x == px
                and previous_y == py
                and (int(px), int(py)) in revealed
            ):
                return
        radius = LIGHT_LEVEL_SIGHT_RADIUS
        min_x = max(0, int(px - radius) - 1)
        max_x = min(MAP_W - 1, int(px + radius) + 1)
        min_y = max(0, int(py - radius) - 1)
        max_y = min(MAP_H - 1, int(py + radius) + 1)
        r2 = radius * radius
        for x in range(min_x, max_x + 1):
            dx = x + 0.5 - px
            dx2 = dx * dx
            for y in range(min_y, max_y + 1):
                dy = y + 0.5 - py
                if dx2 + dy * dy <= r2:
                    revealed.add((x, y))
        self._last_reveal_state = (revealed, self.current_depth, px, py)

    def has_line_of_sight(self, ax: float, ay: float, bx: float, by: float) -> bool:
        # Integer Bresenham walk over the cells between (ax,ay) and (bx,by):
        # one cell per step instead of the old 8x-oversampled float walk, with
        # the bounds/floor check inlined (no per-step method calls). A wall or
        # closed door on any intermediate cell blocks sight; the endpoints are
        # excluded (matching the previous `steps 1..steps-1` semantics).
        x0, y0 = int(ax), int(ay)
        x1, y1 = int(bx), int(by)
        if x0 == x1 and y0 == y1:
            return True
        tiles = self.dungeon.tiles
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x1 > x0 else -1
        sy = 1 if y1 > y0 else -1
        err = dx - dy
        x, y = x0, y0
        while True:
            if (x, y) != (x0, y0) and (x, y) != (x1, y1):
                if not (0 <= x < MAP_W and 0 <= y < MAP_H):
                    return False
                if tiles[x][y] not in (Tile.FLOOR, Tile.STAIRS, Tile.OPEN_DOOR):
                    return False
            if x == x1 and y == y1:
                break
            e2 = err << 1
            if e2 > -dy:
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy
        return True

    def has_line_of_sight_to_player(self, x: float, y: float) -> bool:
        cache = getattr(self, "_frame_cache", None)
        if cache is not None:
            key = (
                "los",
                round(x, 2),
                round(y, 2),
                round(self.player.x, 2),
                round(self.player.y, 2),
            )
            if key in cache:
                return bool(cache[key])
            result = self.has_line_of_sight(self.player.x, self.player.y, x, y)
            cache[key] = result
            return result
        return self.has_line_of_sight(self.player.x, self.player.y, x, y)

    def tile_visibility_alpha(self, x: int, y: int) -> int:
        if not self.is_current_floor_dark():
            # Light floor: fog of war. Revealed terrain persists at full
            # opacity; anything never explored stays black.
            return 255 if (x, y) in self.revealed_tiles else 0
        dx = x + 0.5 - self.player.x
        dy = y + 0.5 - self.player.y
        distance_squared = dx * dx + dy * dy
        if distance_squared <= _DARK_VISIBILITY_INNER_RADIUS_SQUARED:
            return 255
        if distance_squared > _DARK_VISIBILITY_OUTER_RADIUS_SQUARED:
            return 0
        distance = math.sqrt(distance_squared)
        ratio = (_DARK_VISIBILITY_OUTER_RADIUS - distance) / 1.75
        return max(34, min(255, int(255 * ratio)))

    def record_meta_discovery(self, key: str, value: str) -> None:
        if not value:
            return
        current = list(self.meta_progress.get(key, []))
        if value not in current:
            current.append(value)
            self.meta_progress[key] = sorted(current)[-80:]

    def record_run_start_meta(self) -> None:
        self.meta_progress["runs_started"] = (
            int(self.meta_progress.get("runs_started", 0)) + 1
        )
        self.record_meta_discovery("themes_seen", self.theme.name)
        self.record_meta_discovery("modifiers_seen", self.run_modifier.name)
        self.save_options()

    def record_notable_loot(self, item: Item) -> None:
        if (
            item.rarity not in ("Rare", "Unique", "Legendary", "Cursed")
            and not item.cursed
        ):
            return
        label = f"{item.visible_rarity} {item.display_name}"
        if label not in self.run_stats.notable_loot:
            self.run_stats.notable_loot.append(label)
            del self.run_stats.notable_loot[:-8]
        if item.rarity in ("Unique", "Legendary"):
            self.record_meta_discovery("legendary_loot_seen", item.name)

    def finalize_run(self, outcome: str) -> None:
        progress = self.meta_progress
        progress["best_depth"] = max(
            int(progress.get("best_depth", 0)), self.current_depth
        )
        if outcome == "victory":
            progress["clears"] = int(progress.get("clears", 0)) + 1
        for boss_name in self.run_stats.defeated_bosses:
            self.record_meta_discovery("bosses_defeated", boss_name)
        for plan in self.floor_plan:
            if plan.depth <= self.current_depth:
                self.record_meta_discovery("themes_seen", plan.theme_name)
        record = {
            "outcome": outcome,
            "class": self.player.class_name,
            "depth": self.current_depth,
            "time": int(self.elapsed),
            "difficulty": self.difficulty_profile().name,
            "modifier": self.run_modifier.name,
            "kills": self.run_stats.kills,
            "bosses": list(self.run_stats.defeated_bosses[-4:]),
            "notable_loot": list(self.run_stats.notable_loot[-4:]),
            "cause": self.run_stats.cause_of_death,
        }
        self.run_history.append(record)
        del self.run_history[:-12]
        self.save_options()

    def restart(self, archetype: Archetype | None = None) -> None:
        self.run_number += 1
        if archetype:
            self.selected_archetype = archetype
        self.difficulty_name = self.sanitize_difficulty_name(self.difficulty_name)
        self.hell_unlocked_this_run = False
        self.current_depth = 1
        self.run_music_seed = self.rng.randrange(1, 2**31)
        self.run_modifier = self.rng.choice(RUN_MODIFIERS)
        self.theme = self.rng.choice(DUNGEON_THEMES)
        self.run_music_theme = self.theme.name
        self.floor_plan = []
        self.start_story_mode()
        self.floor_plan = self.generate_floor_plan()
        self.apply_floor_plan_for_current_depth()
        self.record_run_start_meta()
        self.tile_cache.clear()
        self.prewarm_tile_cache(prewarm_stair_animation=False)
        guest_room = (
            story_beat_index_for_depth(self.story_state, self.current_depth) is not None
        )
        self.dungeon = Dungeon(
            self.rng,
            boss_arena=self.current_floor_needs_boss_arena(),
            guest_room=guest_room,
        )
        self.prewarm_stair_animation_cache()
        start_x, start_y = self.dungeon.rooms[0].center
        self.player = Player(
            start_x + 0.5,
            start_y + 0.5,
            class_name=self.selected_archetype.name,
            max_hp=self.selected_archetype.max_hp,
            hp=self.selected_archetype.max_hp,
            max_mana=self.selected_archetype.max_mana,
            mana=self.selected_archetype.max_mana,
            max_stamina=self.selected_archetype.max_stamina,
            stamina=self.selected_archetype.max_stamina,
            speed=self.selected_archetype.speed,
            melee_bonus=self.selected_archetype.melee_bonus,
            spell_bonus=self.selected_archetype.spell_bonus,
            armor_bonus=self.selected_archetype.armor_bonus,
        )
        self.players = [self.player]
        self.apply_starting_loadout()
        self.snap_camera_to_player()
        self.revealed_tiles = set()
        self.update_revealed_tiles()
        self.boss_engaged = False
        self.boss_sealed_room_index = None
        self.boss_sealed_tiles = []
        self.enemies: list[Enemy] = []
        self.items: list[Item] = []
        self.shopkeepers: list[Shopkeeper] = []
        self.projectiles: list[Projectile] = []
        self.traps: list[Trap] = []
        self.shrines: list[Shrine] = []
        self.secrets: list[SecretCache] = []
        self.story_guests = []
        self.idle_npcs: list[IdleNpc] = []
        self.reset_friendly_npc_runtime()
        self.familiars: list[Familiar] = []
        self.ambush_bells: list[AmbushBell] = []
        self.light_sources: list[LightSource] = []
        self.lights: list[LightSource] = []
        self.floaters: list[FloatingText] = []
        self.slashes: list[SlashEffect] = []
        self.impact_effects = []
        self.screen_flash_ttl = 0.0
        self.reset_transient_visuals()
        self.run_stats = RunStats()
        self.inventory_open = False
        self.inventory_cursor = 0
        self.inventory_scroll = 0
        self.character_menu_open = False
        self.character_menu_tab = "overview"
        self.shop_open = False
        self.active_shopkeeper = None
        self.shop_mode = "buy"
        self.shop_cursor = 0
        self.show_help = False
        self.elapsed = 0.0
        self.state = "playing"
        self._populate_dungeon()
        self.begin_story_level_intro()
        self.sync_music()
        self.play_sfx("start")
        self.save_run()

    def descend_to_next_depth(self) -> None:
        if self.current_depth >= DUNGEON_DEPTH:
            self.run_stats.floors_cleared = max(
                self.run_stats.floors_cleared, DUNGEON_DEPTH
            )
            self.ambush_bells = []
            self.state = "victory"
            self.unlock_hell_difficulty()
            self.finalize_run("victory")
            self.audio.stop_music()
            self.play_sfx("victory")
            self.delete_save()
            self.mp_notify_run_ended("victory")
            return
        unanswered_message = self.resolve_unanswered_story_beat()
        self.run_stats.floors_cleared = max(
            self.run_stats.floors_cleared, self.current_depth
        )
        self.current_depth += 1
        self._apply_story_theme_for_current_depth()
        self.tile_cache.clear()
        self.prewarm_tile_cache(prewarm_stair_animation=False)
        guest_room = (
            story_beat_index_for_depth(self.story_state, self.current_depth) is not None
        )
        self.dungeon = Dungeon(
            self.rng,
            boss_arena=self.current_floor_needs_boss_arena(),
            guest_room=guest_room,
        )
        self.prewarm_stair_animation_cache()
        start_x, start_y = self.dungeon.rooms[0].center
        self.player.x = start_x + 0.5
        self.player.y = start_y + 0.5
        self.snap_camera_to_player()
        self.revealed_tiles = set()
        self.update_revealed_tiles()
        self.boss_engaged = False
        self.boss_sealed_room_index = None
        self.boss_sealed_tiles = []
        self.player.melee_timer = 0.0
        self.player.bolt_timer = 0.0
        self.player.dash_timer = 0.0
        self.player.class_skill_timer = 0.0
        self.player.time_skip_timer = 0.0
        self.player.stamina = min(
            self.player.max_stamina,
            self.player.stamina + self.player.max_stamina * 0.25,
        )
        self.player.mana = min(
            self.player.max_mana, self.player.mana + self.player.max_mana * 0.25
        )
        self.enemies = []
        self.items = []
        self.shopkeepers = []
        self.projectiles = []
        self.traps = []
        self.shrines = []
        self.secrets = []
        self.story_guests = []
        self.idle_npcs = []
        self.reset_friendly_npc_runtime()
        self.familiars = []
        self.ambush_bells = []
        self.light_sources = []
        self.lights = []
        self.floaters = []
        self.slashes = []
        self.impact_effects = []
        self.screen_flash_ttl = 0.0
        self.reset_transient_visuals()
        self.inventory_open = False
        self.inventory_cursor = 0
        self.inventory_scroll = 0
        self.character_menu_open = False
        self.character_menu_tab = "overview"
        self.shop_open = False
        self.active_shopkeeper = None
        self.shop_mode = "buy"
        self.shop_cursor = 0
        self.show_help = False
        self._populate_dungeon()
        self.begin_story_level_intro()
        if unanswered_message:
            self.floaters.append(
                FloatingText(
                    unanswered_message,
                    self.player.x,
                    self.player.y - 0.85,
                    self.story_state.accent if self.story_state else self.theme.accent,
                    ttl=2.0,
                )
            )
        self.floaters.append(
            FloatingText(
                f"Depth {self.current_depth}/{DUNGEON_DEPTH}",
                self.player.x,
                self.player.y - 0.5,
                self.theme.accent,
                ttl=1.5,
            )
        )
        self.sync_music()
        self.play_sfx("stairs")
        if self.mp_active and self.mp_role == "host":
            self._mp_place_partner_on_new_floor()
            self.mp_send_floor()
        self.save_run()

    # ------------------------------------------------------------------
    # Boss arena: seal the room when the player enters a boss encounter and
    # reopen it once the boss is dead. Only the final boss and named floor
    # guardians (4-tile encounters) lock the doors; challenge-room minibosses
    # stay open so the player can always disengage from optional fights.
    def active_boss(self) -> Enemy | None:
        return next(
            (
                enemy
                for enemy in self.enemies
                if enemy.is_boss_encounter and enemy.alive
            ),
            None,
        )

    def update_boss_encounter(self) -> None:
        boss = self.active_boss()
        if boss is None:
            if self.boss_engaged:
                self.unseal_boss_room()
            return
        boss_room = self.dungeon.room_at(boss.x, boss.y)
        if boss_room is None:
            return
        boss_room_index = self.dungeon.rooms.index(boss_room)
        if not self.boss_engaged:
            player_room = self.dungeon.room_at(self.player.x, self.player.y)
            if player_room is boss_room:
                self.seal_boss_room(boss_room, boss_room_index, boss)
        elif self.boss_sealed_room_index != boss_room_index:
            # Boss moved/replaced on a different floor than the sealed one: clean
            # up stale seals before engaging the new arena.
            self.unseal_boss_room()

    def boss_arena_enemy_radius(self, enemy: Enemy) -> float:
        try:
            return float(self.enemy_hit_radius(enemy))
        except AttributeError:
            return 0.92 if enemy.size >= 2 else 0.42

    def boss_arena_player_clearance(self, boss: Enemy) -> float:
        return PLAYER_HIT_RADIUS + self.boss_arena_enemy_radius(boss) + 0.12

    def find_safe_boss_arena_player_position(
        self,
        room,
        boss: Enemy,
        from_x: float,
        from_y: float,
        min_boss_gap: float,
        avoid_other_enemies: bool = True,
    ) -> tuple[float, float] | None:
        other_enemies = [
            enemy
            for enemy in self.enemies
            if enemy is not boss
            and enemy.alive
            and self.dungeon.room_at(enemy.x, enemy.y) is room
        ]
        center_x, center_y = room.center
        candidates: list[tuple[float, float, float, float, float]] = []
        for tx in range(room.x + 1, room.x + room.w - 1):
            for ty in range(room.y + 1, room.y + room.h - 1):
                px, py = tx + 0.5, ty + 0.5
                if self.dungeon.blocked_for_radius(px, py, PLAYER_HIT_RADIUS):
                    continue
                boss_distance = math.hypot(px - boss.x, py - boss.y)
                if boss_distance < min_boss_gap:
                    continue
                if avoid_other_enemies:
                    blocked_by_enemy = False
                    for enemy in other_enemies:
                        enemy_gap = (
                            PLAYER_HIT_RADIUS
                            + self.boss_arena_enemy_radius(enemy)
                            + 0.12
                        )
                        if math.hypot(px - enemy.x, py - enemy.y) < enemy_gap:
                            blocked_by_enemy = True
                            break
                    if blocked_by_enemy:
                        continue
                from_distance = math.hypot(px - from_x, py - from_y)
                center_distance = math.hypot(
                    px - (center_x + 0.5), py - (center_y + 0.5)
                )
                candidates.append(
                    (from_distance, -boss_distance, center_distance, px, py)
                )
        if not candidates:
            return None
        candidates.sort()
        return candidates[0][3], candidates[0][4]

    def ensure_player_safe_in_boss_arena(
        self, room, boss: Enemy, from_x: float, from_y: float
    ) -> bool:
        boss_gap = self.boss_arena_player_clearance(boss)
        player_blocked = self.dungeon.blocked_for_radius(
            self.player.x, self.player.y, PLAYER_HIT_RADIUS
        )
        too_close_to_boss = (
            math.hypot(self.player.x - boss.x, self.player.y - boss.y) < boss_gap
        )
        if not player_blocked and not too_close_to_boss:
            return False

        for gap, avoid_other_enemies in (
            (boss_gap + 0.75, True),
            (boss_gap + 0.35, True),
            (boss_gap, True),
            (boss_gap, False),
        ):
            spot = self.find_safe_boss_arena_player_position(
                room, boss, from_x, from_y, gap, avoid_other_enemies
            )
            if spot is None:
                continue
            old_x, old_y = self.player.x, self.player.y
            self.player.x, self.player.y = spot
            if math.hypot(self.player.x - old_x, self.player.y - old_y) > 1.0:
                self.snap_camera_to_player()
            self.update_revealed_tiles()
            return True
        return False

    def seal_boss_room(self, room, room_index: int, boss: Enemy) -> None:
        player_x, player_y = self.player.x, self.player.y
        self.boss_sealed_tiles = self.dungeon.seal_room_openings(room)
        self.boss_sealed_room_index = room_index
        self.boss_engaged = True
        self.ensure_player_safe_in_boss_arena(room, boss, player_x, player_y)
        self.tile_cache.clear()
        self.prewarm_tile_cache()
        self.play_sfx("boss")
        self.floaters.append(
            FloatingText(
                "The doors seal!",
                self.player.x,
                self.player.y - 0.55,
                self.theme.accent,
                ttl=1.6,
            )
        )
        self.floaters.append(
            FloatingText(
                boss.name,
                boss.x,
                boss.y - 1.1,
                self.theme.accent,
                ttl=2.2,
            )
        )

    def unseal_boss_room(self) -> None:
        if not self.boss_engaged and not self.boss_sealed_tiles:
            return
        self.dungeon.restore_tiles(self.boss_sealed_tiles)
        self.boss_sealed_tiles = []
        self.boss_sealed_room_index = None
        self.boss_engaged = False
        self.tile_cache.clear()
        self.prewarm_tile_cache()
        self.floaters.append(
            FloatingText(
                "The doors grind open.",
                self.player.x,
                self.player.y - 0.55,
                self.theme.accent,
                ttl=1.6,
            )
        )

    # --- 4.6 multiplayer run start ------------------------------------------

    def begin_multiplayer_run(
        self,
        *,
        run_seed: int,
        host_archetype: str,
        joiner_archetype: str,
        host_player_id: str,
        joiner_player_id: str,
        host_name: str,
        joiner_name: str,
    ) -> None:
        """Start the shared run on the host.

        Mirrors the single-player start path (``restart``) but seeds the run
        from the server-relayed host ``run_seed`` and stamps both ``Player``
        actors. The host is the sole simulator; ``mp_active`` is set before
        ``restart`` so the run-save guard keeps the solo save untouched.
        """

        from .content import ARCHETYPES

        def archetype_by_name(name: str):
            return next(
                (arch for arch in ARCHETYPES if arch.name == name),
                ARCHETYPES[0],
            )

        host_arch = archetype_by_name(host_archetype)
        joiner_arch = archetype_by_name(joiner_archetype)
        self.mp_active = True
        self.mp_role = "host"
        self.local_player_id = host_player_id
        self.rng.seed(run_seed)
        self.restart(host_arch)
        self.player.player_id = host_player_id
        self.player.display_name = host_name
        joiner_x, joiner_y = self._mp_free_spawn_near(
            self.player.x, self.player.y
        )
        joiner = Player(
            joiner_x,
            joiner_y,
            class_name=joiner_arch.name,
            max_hp=joiner_arch.max_hp,
            hp=joiner_arch.max_hp,
            max_mana=joiner_arch.max_mana,
            mana=joiner_arch.max_mana,
            max_stamina=joiner_arch.max_stamina,
            stamina=joiner_arch.max_stamina,
            speed=joiner_arch.speed,
            melee_bonus=joiner_arch.melee_bonus,
            spell_bonus=joiner_arch.spell_bonus,
            armor_bonus=joiner_arch.armor_bonus,
        )
        joiner.player_id = joiner_player_id
        joiner.display_name = joiner_name
        with self.acting_as_player(joiner):
            self.apply_starting_loadout()
        self.players = sorted(
            [self.player, joiner], key=lambda p: p.player_id
        )
        self._mp_entity_counter = 0
        for enemy in self.enemies:
            enemy.entity_id = ""

    def _mp_free_spawn_near(self, x: float, y: float) -> tuple[float, float]:
        """First unblocked tile-center near (x, y) for the partner actor."""

        for offset_x, offset_y in (
            (1.0, 0.0),
            (-1.0, 0.0),
            (0.0, 1.0),
            (0.0, -1.0),
            (1.0, 1.0),
            (-1.0, -1.0),
            (1.0, -1.0),
            (-1.0, 1.0),
            (2.0, 0.0),
            (0.0, 2.0),
        ):
            candidate_x = x + offset_x
            candidate_y = y + offset_y
            if not self.dungeon.blocked_for_radius(
                candidate_x, candidate_y, 0.27, block_stairs=True
            ):
                return candidate_x, candidate_y
        return x, y

    def _mp_place_partner_on_new_floor(self) -> None:
        """Move and refresh the partner actor after a host floor change."""

        partner = self.partner_player()
        if partner is None:
            return
        partner.x, partner.y = self._mp_free_spawn_near(
            self.player.x, self.player.y
        )
        partner.net_x = None
        partner.net_y = None
        partner.melee_timer = 0.0
        partner.bolt_timer = 0.0
        partner.dash_timer = 0.0
        partner.class_skill_timer = 0.0
        partner.time_skip_timer = 0.0
        if partner.hp > 0:
            partner.stamina = min(
                partner.max_stamina,
                partner.stamina + partner.max_stamina * 0.25,
            )
            partner.mana = min(
                partner.max_mana, partner.mana + partner.max_mana * 0.25
            )

    def apply_starting_loadout(self) -> None:
        loadouts = {
            "Warden": (
                Item("Warden Arming Sword", "weapon", power=3, rarity="Common"),
                Item("Warden Mail", "armor", defense=3, rarity="Common"),
            ),
            "Rogue": (
                Item("Twin Fang Knife", "weapon", power=6, rarity="Common"),
                Item("Shadow Jerkin", "armor", defense=1, rarity="Common"),
            ),
            "Arcanist": (
                Item("Runed Wand", "weapon", power=1, rarity="Common"),
                Item("Apprentice Mantle", "armor", defense=1, rarity="Common"),
            ),
            "Acolyte": (
                Item("Pilgrim Censer", "weapon", power=2, rarity="Common"),
                Item("Boneweave Mantle", "armor", defense=2, rarity="Common"),
            ),
            "Ranger": (
                Item("Yew Longbow", "weapon", power=5, rarity="Common"),
                Item("Trail Leathers", "armor", defense=2, rarity="Common"),
            ),
        }
        weapon, armor = loadouts.get(self.player.class_name, loadouts["Warden"])
        self.player.equipment["weapon"] = weapon
        self.player.equipment["armor"] = armor
