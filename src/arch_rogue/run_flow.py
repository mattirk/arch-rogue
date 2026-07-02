# pyright: reportAttributeAccessIssue=false
from __future__ import annotations

import math
from dataclasses import replace
from typing import Any

from .constants import DARK_LEVEL_LIGHT_RADIUS, DUNGEON_DEPTH, SlashEffect
from .content import (
    BOSS_DEFINITIONS,
    DUNGEON_THEMES,
    ENCOUNTER_TEMPLATES,
    RUN_MODIFIERS,
    BossDefinition,
    EncounterTemplate,
)
from .dungeon import Dungeon
from .models import (
    Archetype,
    Enemy,
    FloatingText,
    FloorPlan,
    Item,
    Player,
    Projectile,
    RunStats,
    SecretCache,
    Shopkeeper,
    Shrine,
    Trap,
)


class RunFlowMixin:
    def save_exists(self) -> bool:
        return self.save_path.exists()

    # --- Title menu navigation -------------------------------------------
    # Title rows: 0=New descent, 1=Resume, 2=Options, 3=About. Resume (1) is
    # only selectable when a save exists, so arrow navigation skips it.
    TITLE_ROW_COUNT = 4
    TITLE_RESUME_ROW = 1

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
        elif index == self.TITLE_RESUME_ROW:
            self.load_run()
        elif index == 2:
            self.state = "options"
        elif index == 3:
            self.state = "about"

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

    def dark_depths_for_run(self) -> set[int]:
        dark_depths: set[int] = set()
        early_candidates = list(range(2, min(4, DUNGEON_DEPTH) + 1))
        if not early_candidates and DUNGEON_DEPTH >= 1:
            early_candidates = [1]
        if early_candidates:
            dark_depths.add(self.rng.choice(early_candidates))

        mid_candidates = list(range(5, min(10, DUNGEON_DEPTH) + 1))
        dark_depths.update(self.rng.sample(mid_candidates, min(3, len(mid_candidates))))

        for depth in range(11, DUNGEON_DEPTH + 1):
            if self.rng.random() < 0.5:
                dark_depths.add(depth)
        return dark_depths

    def generate_floor_plan(self) -> list[FloorPlan]:
        plan: list[FloorPlan] = []
        previous_theme = self.theme.name
        dark_depths = self.dark_depths_for_run()
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
            is_dark = depth in dark_depths
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
            cached = cache.get("current_floor_plan")
            if cached is not None:
                return cached if cached is not False else None
            plan = next(
                (plan for plan in self.floor_plan if plan.depth == self.current_depth),
                None,
            )
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
            if "is_current_floor_dark" in cache:
                return bool(cache["is_current_floor_dark"])
            plan = self.current_floor_plan()
            dark = bool(plan and plan.dark)
            cache["is_current_floor_dark"] = dark
            return dark
        plan = self.current_floor_plan()
        return bool(plan and plan.dark)

    def set_current_floor_dark(self, dark: bool) -> None:
        self.floor_plan = [
            replace(plan, dark=dark) if plan.depth == self.current_depth else plan
            for plan in self.floor_plan
        ]

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
        if not self.is_current_floor_dark():
            return True
        return self.light_distance_to_player(x, y) <= DARK_LEVEL_LIGHT_RADIUS + margin

    def has_line_of_sight(self, ax: float, ay: float, bx: float, by: float) -> bool:
        distance = math.hypot(bx - ax, by - ay)
        if distance <= 0.001:
            return True
        steps = max(1, int(distance * 8))
        for step in range(1, steps):
            ratio = step / steps
            x = ax + (bx - ax) * ratio
            y = ay + (by - ay) * ratio
            tx, ty = int(x), int(y)
            if not self.dungeon.in_bounds(tx, ty):
                return False
            if not self.dungeon.is_floor(x, y):
                return False
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
            return 255
        px = self.player.x
        py = self.player.y
        distance = math.hypot(x + 0.5 - px, y + 0.5 - py)
        if distance <= DARK_LEVEL_LIGHT_RADIUS - 1.1:
            return 255
        if distance > DARK_LEVEL_LIGHT_RADIUS + 0.65:
            return 0
        ratio = (DARK_LEVEL_LIGHT_RADIUS + 0.65 - distance) / 1.75
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
        self.prewarm_tile_cache()
        self.dungeon = Dungeon(self.rng)
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
        self.apply_starting_loadout()
        self.snap_camera_to_player()
        self.enemies: list[Enemy] = []
        self.items: list[Item] = []
        self.shopkeepers: list[Shopkeeper] = []
        self.projectiles: list[Projectile] = []
        self.traps: list[Trap] = []
        self.shrines: list[Shrine] = []
        self.secrets: list[SecretCache] = []
        self.story_guests = []
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
            self.state = "victory"
            self.unlock_hell_difficulty()
            self.finalize_run("victory")
            self.audio.stop_music()
            self.play_sfx("victory")
            self.delete_save()
            return
        unanswered_message = self.resolve_unanswered_story_beat()
        self.run_stats.floors_cleared = max(
            self.run_stats.floors_cleared, self.current_depth
        )
        self.current_depth += 1
        self._apply_story_theme_for_current_depth()
        self.tile_cache.clear()
        self.prewarm_tile_cache()
        self.dungeon = Dungeon(self.rng)
        start_x, start_y = self.dungeon.rooms[0].center
        self.player.x = start_x + 0.5
        self.player.y = start_y + 0.5
        self.snap_camera_to_player()
        self.player.melee_timer = 0.0
        self.player.bolt_timer = 0.0
        self.player.dash_timer = 0.0
        self.player.nova_timer = 0.0
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
        self.save_run()

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
