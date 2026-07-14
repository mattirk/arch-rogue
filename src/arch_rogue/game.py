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

from __future__ import annotations

import math
import random
from pathlib import Path
from typing import Any

import pygame

from . import __version__
from .audio import AudioSystem
from .camera import CameraMixin
from .combat import CombatMixin
from .constants import (
    BOSS_HIT_RADIUS,
    DARK_LEVEL_LIGHT_RADIUS,
    DUNGEON_DEPTH,
    ENEMY_HIT_RADIUS,
    ENEMY_PROJECTILE_HIT_RADIUS,
    FPS,
    LARGE_ENEMY_HIT_RADIUS,
    LIGHT_IMPACT_RADIUS,
    LIGHT_IMPACT_TTL,
    LIGHT_SKILL_PULSE_RADIUS,
    LIGHT_SKILL_PULSE_TTL,
    LIGHT_PROJECTILE_RADIUS,
    LIGHT_PROJECTILE_TTL,
    LIGHT_PROJECTILE_INTENSITY,
    LIGHT_TORCH_COLOR,
    LIGHT_TORCH_RADIUS,
    LIGHT_TORCH_INTENSITY,
    LIGHT_SHRINE_RADIUS,
    LIGHT_SHRINE_INTENSITY,
    MAX_INVENTORY,
    PLAYER_HIT_RADIUS,
    PLAYER_MELEE_ARC_DOT,
    PLAYER_MELEE_RANGE,
    PLAYER_PROJECTILE_HIT_RADIUS,
    UI_SCALE,
    WALK_ANIMATION_RATE,
    SlashEffect,
)
from .content import (
    ARCHETYPES,
    ARMOR_DEFINITIONS,
    BOSS_DEFINITIONS,
    DEFAULT_DIFFICULTY_NAME,
    DUNGEON_THEMES,
    ELITE_MODIFIERS,
    ENCOUNTER_TEMPLATES,
    ENEMY_DEFINITIONS,
    FINAL_ROOM_ENEMY_DEFINITIONS,
    RARITY_PROFILES,
    RUN_MODIFIERS,
    SECRET_TYPES,
    SHRINE_TYPES,
    DISCIPLINES,
    DISCIPLINE_UPGRADES,
    STORY_LOCATION_MOTIFS,
    TRAP_DEFINITIONS,
    WEAPON_DEFINITIONS,
    BossDefinition,
    EncounterTemplate,
    EnemyDefinition,
    discipline_by_key,
)
from .dungeon import Dungeon
from .icon import load_icon
from .input import InputMixin, key_command
from .interactions import InteractionMixin
from .inventory import InventoryMixin
from .menus import MenuRenderer
from .models import (
    AmbushBell,
    Archetype,
    Color,
    Enemy,
    Familiar,
    FloatingText,
    FloorPlan,
    IdleNpc,
    ImpactEffect,
    Item,
    LightSource,
    Player,
    Projectile,
    Room,
    RunStats,
    SecretCache,
    Shopkeeper,
    Shrine,
    SpecialRoom,
    SpecialRoomDefinition,
    StoryGuest,
    StoryState,
    Tile,
    Trap,
)
from .options import OptionsMixin
from .population import PopulationMixin
from .quest_assets import (
    ActiveQuestCutscene,
    RuntimeDialogueChoice,
    format_asset_text,
    load_quest_cutscene_library,
)
from .rendering import RenderingMixin
from .run_flow import RunFlowMixin
from .save_system import SaveLoadMixin
from .shop import ShopMixin
from .sprite_assets import SpriteAtlas
from .sprites import PixelSpriteAtlas
from .ui_assets import UiAssetLibrary
from .story import (
    StoryEngine,
    clamp_story_effect,
    record_story_choice,
    record_unanswered_story_beat,
    story_beat_for_depth,
    story_beat_index_for_depth,
    story_effect,
    story_guest_from_beat,
)
from .story_runtime import StoryRuntimeMixin

# Keep compatibility with scripts/tests that imported data tables and models from
# the earlier monolithic game module, while keeping the imports above idiomatic.
__all__ = (
    "ARCHETYPES",
    "ARMOR_DEFINITIONS",
    "ActiveQuestCutscene",
    "AmbushBell",
    "Archetype",
    "AudioSystem",
    "BOSS_DEFINITIONS",
    "BOSS_HIT_RADIUS",
    "BossDefinition",
    "CameraMixin",
    "Color",
    "CombatMixin",
    "DARK_LEVEL_LIGHT_RADIUS",
    "DEFAULT_DIFFICULTY_NAME",
    "DUNGEON_DEPTH",
    "DUNGEON_THEMES",
    "Dungeon",
    "ELITE_MODIFIERS",
    "ENCOUNTER_TEMPLATES",
    "ENEMY_DEFINITIONS",
    "ENEMY_HIT_RADIUS",
    "ENEMY_PROJECTILE_HIT_RADIUS",
    "EncounterTemplate",
    "Enemy",
    "EnemyDefinition",
    "FINAL_ROOM_ENEMY_DEFINITIONS",
    "FPS",
    "FloatingText",
    "FloorPlan",
    "Game",
    "IdleNpc",
    "ImpactEffect",
    "InputMixin",
    "InteractionMixin",
    "InventoryMixin",
    "Item",
    "LARGE_ENEMY_HIT_RADIUS",
    "MAX_INVENTORY",
    "MenuRenderer",
    "OptionsMixin",
    "PLAYER_HIT_RADIUS",
    "PLAYER_MELEE_ARC_DOT",
    "PLAYER_MELEE_RANGE",
    "PLAYER_PROJECTILE_HIT_RADIUS",
    "PixelSpriteAtlas",
    "Player",
    "SpriteAtlas",
    "PopulationMixin",
    "Projectile",
    "RARITY_PROFILES",
    "RUN_MODIFIERS",
    "RenderingMixin",
    "Room",
    "RunFlowMixin",
    "RunStats",
    "RuntimeDialogueChoice",
    "SECRET_TYPES",
    "SHRINE_TYPES",
    "DISCIPLINES",
    "DISCIPLINE_UPGRADES",
    "SaveLoadMixin",
    "SecretCache",
    "ShopMixin",
    "Shopkeeper",
    "Shrine",
    "SlashEffect",
    "SpecialRoom",
    "SpecialRoomDefinition",
    "STORY_LOCATION_MOTIFS",
    "TRAP_DEFINITIONS",
    "StoryEngine",
    "StoryGuest",
    "StoryRuntimeMixin",
    "StoryState",
    "Tile",
    "Trap",
    "UI_SCALE",
    "WALK_ANIMATION_RATE",
    "WEAPON_DEFINITIONS",
    "clamp_story_effect",
    "format_asset_text",
    "key_command",
    "load_quest_cutscene_library",
    "main",
    "record_story_choice",
    "record_unanswered_story_beat",
    "discipline_by_key",
    "story_beat_for_depth",
    "story_beat_index_for_depth",
    "story_effect",
    "story_guest_from_beat",
)


class Game(
    SaveLoadMixin,
    RenderingMixin,
    OptionsMixin,
    RunFlowMixin,
    PopulationMixin,
    StoryRuntimeMixin,
    CombatMixin,
    InventoryMixin,
    ShopMixin,
    InteractionMixin,
    InputMixin,
    CameraMixin,
):
    def __init__(
        self,
        screen_size: tuple[int, int] | None = None,
        headless: bool = False,
        save_path: str | Path | None = None,
    ) -> None:
        pygame.init()
        pygame.display.set_caption(f"Arch Rogue {__version__}")
        self.save_path = (
            Path(save_path) if save_path else Path.home() / ".arch_rogue_run.json"
        )
        self.options_path = Path.home() / ".arch_rogue_options.json"
        self.audio_enabled = True
        self.music_enabled = False
        self.fullscreen = False
        self.ui_scale = UI_SCALE
        self.controller_enabled = True
        self.last_controller_guid = ""
        self.difficulty_name = DEFAULT_DIFFICULTY_NAME
        self.hell_unlocked = False
        self.hell_unlocked_this_run = False
        # Milestone 3.16 - continuous colored lighting options. Defaults are
        # native-friendly (lighting + normal maps on, flicker on). The web
        # build forces these off in web/main.make_game so the 3.8.0 per-tile
        # alpha path remains the web-safe default.
        self._lighting_enabled = True
        self._lighting_normal_maps = True
        # Asset sprites are the production default. The persisted legacy toggle
        # keeps the original procedural renderer available on constrained systems
        # and as a per-install compatibility fallback.
        self.legacy_graphics = False
        self.meta_progress: dict[str, Any] = self.default_meta_progress()
        self.run_history: list[dict[str, Any]] = []
        self.last_save_error = ""
        self.last_load_error = ""
        self.screen_flash_ttl = 0.0
        self.screen_flash_color: Color = (0, 0, 0)
        # Viewport zoom ("viewport distance"); adjusted in-game with Ctrl+scroll.
        # Start at native scale, allowing players to zoom either in or out.
        self.view_zoom = 1.0
        self._world_layer: pygame.Surface | None = None
        # Headless callers (tests, benchmarks, tooling) must not inherit the
        # developer machine's real home-directory preferences before they can
        # install an isolated options_path. They can still call load_options()
        # explicitly after setting that path, as persistence tests already do.
        if not headless:
            self.load_options()
        if screen_size is None:
            display_info = pygame.display.Info()
            screen_size = (display_info.current_w, display_info.current_h)
        self.windowed_size = screen_size
        self.screen = self.apply_display_mode(headless=headless)
        # Branded window/taskbar icon: the octahedron relic logo. Best-effort —
        # headless/dummy drivers and platforms without bundled assets quietly skip.
        icon_surface = load_icon(64)
        if icon_surface is not None:
            try:
                pygame.display.set_icon(icon_surface)
            except pygame.error:
                pass
        self.clock = pygame.time.Clock()
        self.rebuild_fonts()
        self.ui_assets = UiAssetLibrary()
        self.sprites = SpriteAtlas(legacy_graphics=self.legacy_graphics)
        self.quest_cutscenes = load_quest_cutscene_library()
        self.active_cutscene: ActiveQuestCutscene | None = None
        self.tile_cache: dict[
            tuple[str, int, int, bool, bool, bool, bool, str | None],
            tuple[pygame.Surface, int, int],
        ] = {}
        self.door_tile_cache: dict[
            tuple[str, int, int, str], tuple[pygame.Surface, int, int]
        ] = {}
        self.rng = random.Random()
        self.running = True
        self.inventory_open = False
        self.inventory_sort_mode = "type"
        self.inventory_cursor = 0
        self.inventory_scroll = 0
        self.character_menu_open = False
        self.character_menu_tab = "overview"
        # Milestone 3.3: hovered discipline key in the character sheet's
        # Disciplines tab (set by mouse motion, read by the renderer for combo
        # preview). None when nothing is hovered.
        self.character_menu_hovered_node: str | None = None
        # Populated by the character sheet renderer each frame so mouse motion
        # can map screen positions to discipline keys without duplicating layout.
        self._discipline_cells: dict[str, object] = {}
        self.shop_open = False
        self.active_shopkeeper: Shopkeeper | None = None
        self.shop_mode = "buy"
        self.shop_cursor = 0
        self.show_help = False
        self.quest_info_visible = False
        self.run_stats = RunStats()
        self.state = "archetype_select"
        self.elapsed = 0.0
        # Wall-clock-style visual time advances in every app state. Keep it
        # separate from elapsed, which is the serialized duration of a run.
        self.ui_elapsed = 0.0
        self.title_selection = 0
        self.selected_archetype = ARCHETYPES[0]
        self.theme = DUNGEON_THEMES[0]
        self.run_modifier = RUN_MODIFIERS[0]
        self.run_number = 0
        self.current_depth = 1
        self.state = "title"
        self.exit_previous_state = "title"
        self.run_music_seed = 0
        self.run_music_theme = ""
        self.floor_plan: list[FloorPlan] = []
        # Milestone 3.8: per-floor fog-of-war memory for light (non-dark) floors.
        # Tiles within the sight radius are remembered for the rest of the floor;
        # dark floors ignore this and keep their lantern-only visibility model.
        self.revealed_tiles: set[tuple[int, int]] = set()
        # Boss arena state: when the player enters the room containing a 4-tile
        # boss, the doors seal shut and only reopen once the boss is dead. The
        # sealed-tile list records originals so the floor can be restored exactly.
        self.boss_engaged: bool = False
        self.boss_sealed_room_index: int | None = None
        self.boss_sealed_tiles: list[tuple[int, int, Tile]] = []
        self.story_seed = 0
        self.story_state: StoryState | None = None
        self.story_guests: list[StoryGuest] = []
        self.idle_npcs: list[IdleNpc] = []
        # Milestone 3.15 — Acolyte Spirit Call familiars. Reset on restart /
        # floor descent and serialized additively (old saves load with none).
        self.familiars: list[Familiar] = []
        # Milestone 3.17 — Rogue Ambush Bell runtime traps are transient and are
        # intentionally never serialized.
        self.ambush_bells: list[AmbushBell] = []
        self.light_sources: list[LightSource] = []
        self.lights: list[LightSource] = []
        self.story_intro_pending = False
        self.story_relic_depth = 0
        self.story_relic_choice_key = ""
        self.story_relic_position: tuple[float, float] | None = None
        self.story_relic_collected = False
        self.story_relic_guidance_enabled = False
        self.story_relic_guarded = False
        self.impact_effects: list[ImpactEffect] = []
        self.enemy_hit_flashes: dict[int, float] = {}
        self.player_hit_flash = 0.0
        self.player_action_state = ""
        self.player_action_ttl = 0.0
        self.player_action_elapsed = 0.0
        self.player_action_duration = 0.0
        self.ambient_overlay_cache: dict[tuple[int, int, str, int], pygame.Surface] = {}
        self.audio = AudioSystem()
        self.audio_available = self.audio.initialize(headless)
        self._options_visible_range = (0, 0)
        self._options_row_viewport = pygame.Rect(0, 0, 0, 0)
        self._options_selected_row_rect = pygame.Rect(0, 0, 0, 0)
        self._options_row_font_height = 0
        self._controls_keyboard_row_rects: tuple[pygame.Rect, ...] = ()
        self._controls_gamepad_row_rects: tuple[pygame.Rect, ...] = ()
        self.menus = MenuRenderer(self, ARCHETYPES, DUNGEON_DEPTH)
        self.init_input()

    def trigger_screen_flash(self, color: Color, ttl: float = 0.22) -> None:
        self.screen_flash_color = color
        self.screen_flash_ttl = max(self.screen_flash_ttl, ttl)

    def add_impact(
        self,
        x: float,
        y: float,
        color: Color,
        ttl: float = 0.38,
        radius: float = 0.35,
        kind: str = "spark",
        archetype: str = "",
    ) -> None:
        self.impact_effects.append(
            ImpactEffect(x, y, color, ttl, radius, kind, ttl, archetype)
        )
        # Milestone 3.16 - emit a transient light flare for every impact so
        # casts, dashes, hits, bursts, deaths, and chain-lightning strikes
        # all pulse the light buffer. Casts/dashes are brighter (the skill
        # pulse), hits/bursts a shorter snap. Tint comes from the impact color,
        # which already carries the archetype/damage-type tint.
        if kind in ("cast", "dash"):
            self.add_light(
                x, y, LIGHT_SKILL_PULSE_RADIUS, color,
                intensity=0.85, ttl=LIGHT_SKILL_PULSE_TTL, kind=kind,
            )
        else:
            self.add_light(
                x, y, LIGHT_IMPACT_RADIUS, color,
                intensity=0.7, ttl=LIGHT_IMPACT_TTL, kind=kind or "impact",
            )

    def set_player_action_visual(self, state: str, ttl: float = 0.18) -> None:
        ttl = max(0.0, float(ttl))
        starts_new_action = (
            state != self.player_action_state or self.player_action_ttl <= 0.0
        )
        if starts_new_action:
            self.player_action_elapsed = 0.0
            self.player_action_duration = ttl
        else:
            self.player_action_duration = max(
                self.player_action_duration,
                self.player_action_elapsed + ttl,
            )
        self.player_action_state = state
        self.player_action_ttl = max(self.player_action_ttl, ttl)

    def reset_transient_visuals(self) -> None:
        self.enemy_hit_flashes = {}
        self.player_hit_flash = 0.0
        self.player_action_state = ""
        self.player_action_ttl = 0.0
        self.player_action_elapsed = 0.0
        self.player_action_duration = 0.0
        # Milestone 3.16 - transient light pulses are visual effects too.
        self.lights = []

    def update_visual_effects(self, dt: float) -> None:
        for effect in self.impact_effects:
            effect.update(dt)
        self.impact_effects = [
            effect for effect in self.impact_effects if effect.ttl > 0
        ]
        # Milestone 3.16 - decay transient light pulses (skill casts,
        # projectile trails, impact flares) alongside impacts and slashes.
        self.update_lights(dt)
        self.screen_flash_ttl = max(0.0, self.screen_flash_ttl - dt)
        self.player_hit_flash = max(0.0, self.player_hit_flash - dt)
        if self.player_action_ttl > 0.0:
            self.player_action_elapsed += dt
        self.player_action_ttl = max(0.0, self.player_action_ttl - dt)
        if self.player_action_ttl <= 0:
            self.player_action_state = ""
            self.player_action_elapsed = 0.0
            self.player_action_duration = 0.0
        alive_enemy_ids = {id(enemy) for enemy in self.enemies}
        self.enemy_hit_flashes = {
            enemy_id: max(0.0, ttl - dt)
            for enemy_id, ttl in self.enemy_hit_flashes.items()
            if ttl - dt > 0 and enemy_id in alive_enemy_ids
        }
        self.slashes = [
            (x, y, ttl - dt, dx, dy)
            for x, y, ttl, dx, dy in self.slashes
            if ttl - dt > 0
        ]

    def rarity_color(self, rarity: str) -> Color:
        return RARITY_PROFILES.get(rarity, RARITY_PROFILES["Common"]).color

    def rarity_icon(self, rarity: str) -> str:
        return RARITY_PROFILES.get(rarity, RARITY_PROFILES["Common"]).icon

    def acquired_discipline_summaries(self) -> list[tuple[str, str]]:
        by_key = {node.key: node for node in DISCIPLINES}
        return [
            (by_key[key].name, by_key[key].description)
            for key in self.player.skill_upgrades
            if key in by_key
        ]

    def acquired_disciplines(self) -> list:
        """Acquired `Discipline` objects in purchase order (for the disciplines tab)."""
        by_key = {node.key: node for node in DISCIPLINES}
        return [by_key[key] for key in self.player.skill_upgrades if key in by_key]

    def run(self) -> None:
        while self.running:
            dt = min(self.clock.tick(FPS) / 1000.0, 0.05)
            self.ui_elapsed += dt
            self.handle_events()
            if self.state == "playing":
                self.update(dt)
            self.draw()
        pygame.quit()

    def request_exit_confirmation(self) -> None:
        if self.state != "confirm_exit":
            self.exit_previous_state = self.state
        self.show_help = False
        self.character_menu_open = False
        self.state = "confirm_exit"

    def cancel_exit_confirmation(self) -> None:
        self.state = self.exit_previous_state or "title"

    def confirm_exit(self) -> None:
        if self.exit_previous_state == "playing":
            self.save_run()
        self.running = False

    def handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.request_exit_confirmation()
            elif event.type == pygame.VIDEORESIZE and not self.fullscreen:
                self.windowed_size = (max(640, event.w), max(480, event.h))
                self.screen = pygame.display.set_mode(
                    self.windowed_size, pygame.RESIZABLE
                )
            elif self.handle_controller_event(event):
                continue
            elif event.type == pygame.KEYDOWN:
                if self.state == "confirm_exit":
                    if event.key in (pygame.K_y, pygame.K_RETURN):
                        self.confirm_exit()
                    elif event.key in (pygame.K_n, pygame.K_ESCAPE, pygame.K_BACKSPACE):
                        self.cancel_exit_confirmation()
                elif event.key == pygame.K_ESCAPE:
                    if self.state == "playing" and self.shop_open:
                        self.close_shop()
                    elif self.state == "playing" and self.character_menu_open:
                        self.character_menu_open = False
                    elif self.state == "playing" and self.inventory_open:
                        self.inventory_open = False
                    elif (
                        self.state == "playing"
                        and self.active_cutscene is not None
                        and not self.story_intro_pending
                    ):
                        self.close_active_cutscene()
                    elif self.state in ("options", "about"):
                        self.state = "title"
                    elif self.state == "controls":
                        self.state = "options"
                    else:
                        self.request_exit_confirmation()
                elif (
                    self.state == "playing"
                    and event.key == pygame.K_d
                    and event.mod & pygame.KMOD_CTRL
                    and event.mod & pygame.KMOD_SHIFT
                ):
                    self.toggle_current_floor_dark()
                elif self.state == "title":
                    # Four title rows: 0=New, 1=Resume, 2=Options, 3=About.
                    # Resume is only selectable when a save exists.
                    if event.key in (pygame.K_DOWN, pygame.K_RIGHT, pygame.K_s):
                        self.title_selection = self._next_title_selection(1)
                    elif event.key in (pygame.K_UP, pygame.K_LEFT, pygame.K_w):
                        self.title_selection = self._next_title_selection(-1)
                    elif event.key == pygame.K_RETURN:
                        self._activate_title_selection()
                    elif event.key == pygame.K_n:
                        self.state = "archetype_select"
                    elif event.key in (pygame.K_l, pygame.K_r) and self.save_exists():
                        self.load_run()
                    elif event.key == pygame.K_o:
                        self.state = "options"
                    elif event.key in (pygame.K_a, pygame.K_c):
                        self.state = "about"
                    elif event.key in (pygame.K_h, pygame.K_SLASH):
                        self.state = "about"
                elif self.state == "options":
                    if event.key == pygame.K_a:
                        self.options_cursor = self.OPTIONS_ROW_AUDIO
                        self.audio_enabled = not self.audio_enabled
                        self.save_options()
                    elif event.key == pygame.K_m:
                        self.options_cursor = self.OPTIONS_ROW_MUSIC
                        self.music_enabled = not self.music_enabled
                        self.sync_music()
                        self.save_options()
                    elif event.key == pygame.K_f:
                        self.options_cursor = self.OPTIONS_ROW_FULLSCREEN
                        if not self.fullscreen:
                            self.windowed_size = self.screen.get_size()
                        self.fullscreen = not self.fullscreen
                        self.screen = self.apply_display_mode()
                        self.save_options()
                    elif event.key == pygame.K_d:
                        self.options_cursor = self.OPTIONS_ROW_DIFFICULTY
                        self.cycle_difficulty()
                    elif event.key in (pygame.K_EQUALS, pygame.K_PLUS):
                        self.options_cursor = self.OPTIONS_ROW_UI_SCALE
                        self._activate_options_row(self.OPTIONS_ROW_UI_SCALE, True)
                    elif event.key in (pygame.K_MINUS, pygame.K_UNDERSCORE):
                        self.options_cursor = self.OPTIONS_ROW_UI_SCALE
                        self._activate_options_row(self.OPTIONS_ROW_UI_SCALE, False)
                    elif event.key == pygame.K_g:
                        self.options_cursor = self.OPTIONS_ROW_GRAPHICS
                        self._activate_options_row(self.OPTIONS_ROW_GRAPHICS, True)
                    elif event.key == pygame.K_l:
                        self.options_cursor = self.OPTIONS_ROW_LIGHTING
                        self._activate_options_row(self.OPTIONS_ROW_LIGHTING, True)
                    elif event.key == pygame.K_n:
                        self.options_cursor = self.OPTIONS_ROW_LIGHTING_DETAIL
                        self._activate_options_row(self.OPTIONS_ROW_LIGHTING_DETAIL, True)
                    elif event.key == pygame.K_RETURN:
                        self._activate_options_row(self.options_cursor, True)
                    elif event.key in (pygame.K_BACKSPACE, pygame.K_o):
                        self.state = "title"
                    else:
                        cmd = key_command(event.key, event.mod)
                        if cmd is not None:
                            self._dispatch_command(cmd)
                elif self.state == "about":
                    if event.key in (
                        pygame.K_RETURN,
                        pygame.K_BACKSPACE,
                        pygame.K_a,
                        pygame.K_h,
                    ):
                        self.state = "title"
                elif self.state == "controls":
                    if event.key in (pygame.K_BACKSPACE, pygame.K_o):
                        if self.controls_capture_command:
                            self.controls_capture_command = None
                        else:
                            self.state = "options"
                    else:
                        cmd = key_command(event.key, event.mod)
                        if cmd is not None:
                            self._dispatch_command(cmd)
                elif self.state == "archetype_select":
                    if event.key == pygame.K_BACKSPACE:
                        self.state = "title"
                    else:
                        select_limit = min(len(ARCHETYPES), 9)
                        if pygame.K_1 <= event.key < pygame.K_1 + select_limit:
                            self.restart(ARCHETYPES[event.key - pygame.K_1])
                        elif event.key in (pygame.K_RIGHT, pygame.K_DOWN):
                            index = (
                                ARCHETYPES.index(self.selected_archetype) + 1
                            ) % len(ARCHETYPES)
                            self.selected_archetype = ARCHETYPES[index]
                        elif event.key in (pygame.K_LEFT, pygame.K_UP):
                            index = (
                                ARCHETYPES.index(self.selected_archetype) - 1
                            ) % len(ARCHETYPES)
                            self.selected_archetype = ARCHETYPES[index]
                        elif event.key == pygame.K_RETURN:
                            self.restart(self.selected_archetype)
                elif self.state == "playing" and self.active_cutscene is not None:
                    if pygame.K_1 <= event.key <= pygame.K_9:
                        self.choose_active_cutscene_option(event.key - pygame.K_1)
                    elif event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_e):
                        if not self.advance_active_cutscene():
                            self.floaters.append(
                                FloatingText(
                                    "Choose 1-3 to answer the dialogue",
                                    self.player.x,
                                    self.player.y - 0.5,
                                    self.story_state.accent
                                    if self.story_state
                                    else self.theme.accent,
                                    ttl=1.0,
                                )
                            )
                elif self.state == "playing" and self.story_intro_pending:
                    if pygame.K_1 <= event.key <= pygame.K_3:
                        self.choose_story_relic_path(event.key - pygame.K_1)
                    elif event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_e):
                        self.floaters.append(
                            FloatingText(
                                "Choose 1-3 to bind the guest relic",
                                self.player.x,
                                self.player.y - 0.5,
                                self.story_state.accent
                                if self.story_state
                                else self.theme.accent,
                                ttl=1.0,
                            )
                        )
                elif (
                    event.key in (pygame.K_h, pygame.K_SLASH)
                    and self.state != "archetype_select"
                ):
                    self.show_help = not self.show_help
                elif self.state == "playing" and self.shop_open:
                    if event.key == pygame.K_TAB:
                        self.cycle_shop_mode()
                    elif event.key in (pygame.K_UP, pygame.K_w):
                        self.move_shop_selection(-1)
                    elif event.key in (pygame.K_DOWN, pygame.K_s, pygame.K_x):
                        self.move_shop_selection(1)
                    elif event.key in (pygame.K_RETURN, pygame.K_e):
                        self.transact_shop_selection()
                    elif event.key in (pygame.K_BACKSPACE, pygame.K_q):
                        self.close_shop()
                elif event.key == pygame.K_i and self.state == "playing":
                    self.inventory_open = not self.inventory_open
                    if self.inventory_open:
                        self.character_menu_open = False
                        self.close_shop()
                    self.clamp_inventory_selection()
                elif self.state == "playing" and self.inventory_open:
                    if event.key == pygame.K_TAB:
                        self.cycle_inventory_sort_mode()
                    elif event.key == pygame.K_s:
                        self.sort_inventory()
                    elif event.key in (pygame.K_UP, pygame.K_w):
                        self.move_inventory_selection(-1)
                    elif event.key in (pygame.K_DOWN, pygame.K_x):
                        self.move_inventory_selection(1)
                    elif event.key == pygame.K_PAGEUP:
                        self.move_inventory_selection(-5)
                    elif event.key == pygame.K_PAGEDOWN:
                        self.move_inventory_selection(5)
                    elif event.key == pygame.K_HOME:
                        self.set_inventory_selection(0)
                    elif event.key == pygame.K_END:
                        self.set_inventory_selection(len(self.player.inventory) - 1)
                    elif event.key in (pygame.K_RETURN, pygame.K_e):
                        self.use_selected_inventory_slot()
                    elif event.key in (pygame.K_DELETE, pygame.K_BACKSPACE):
                        self.drop_selected_inventory_slot()
                    elif pygame.K_1 <= event.key <= pygame.K_9:
                        index = event.key - pygame.K_1
                        if event.mod & pygame.KMOD_SHIFT:
                            self.drop_inventory_slot(index)
                        else:
                            self.use_inventory_slot(index)
                elif event.key == pygame.K_r and self.state != "playing":
                    self.show_help = False
                    self.inventory_open = False
                    self.character_menu_open = False
                    self.state = "archetype_select"
                elif event.key == pygame.K_e and self.state == "playing":
                    self.interact()
                elif event.key == pygame.K_q and self.state == "playing":
                    self.toggle_quest_info_visibility()
                elif event.key == pygame.K_c and self.state == "playing":
                    self.character_menu_open = not self.character_menu_open
                    if self.character_menu_open:
                        self.inventory_open = False
                        self.close_shop()
                elif (
                    self.state == "playing"
                    and self.character_menu_open
                    and event.key
                    in (
                        pygame.K_TAB,
                        pygame.K_LEFT,
                        pygame.K_RIGHT,
                        pygame.K_a,
                        pygame.K_d,
                        pygame.K_1,
                        pygame.K_2,
                    )
                ):
                    if event.key == pygame.K_TAB:
                        self.character_menu_tab = (
                            "disciplines"
                            if self.character_menu_tab == "overview"
                            else "overview"
                        )
                    elif event.key in (pygame.K_LEFT, pygame.K_a, pygame.K_1):
                        self.character_menu_tab = "overview"
                    else:
                        self.character_menu_tab = "disciplines"
                elif pygame.K_1 <= event.key <= pygame.K_9 and self.state == "playing":
                    index = event.key - pygame.K_1
                    guest = None if self.inventory_open else self.nearby_story_guest()
                    if guest and index < len(guest.choices):
                        self.resolve_story_choice(guest, index)
                    elif index == 0:
                        self.update_player_aim()
                        self.player_melee_attack()
                    elif index == 1:
                        self.update_player_aim()
                        self.player_cast_bolt()
                    elif index == 2:
                        self.update_player_aim()
                        self.player_cast_class_skill()
                    elif index == 3:
                        self.update_player_aim()
                        self.player_dash()
                    elif index == 4:
                        self.use_first_potion()
                    elif index == 5:
                        self.use_first_mana_potion()
                    elif self.inventory_open and event.mod & pygame.KMOD_SHIFT:
                        self.drop_inventory_slot(index)
                    else:
                        self.use_inventory_slot(index)
            elif (
                event.type == pygame.MOUSEBUTTONDOWN
                and self.state == "playing"
                and self.active_cutscene is None
                and not self.story_intro_pending
            ):
                self.aim_input_mode = "mouse"
                if event.button == 1:
                    # Milestone 3.3: clicking an available discipline in the
                    # character sheet spends a mastery token to acquire it.
                    if (
                        self.character_menu_open
                        and self.character_menu_tab == "disciplines"
                        and self.character_menu_hovered_node
                    ):
                        self.choose_discipline(self.character_menu_hovered_node)
                    else:
                        self.face_player_toward_screen_point(*event.pos)
                        if self.enemy_in_melee_arc():
                            self.player_melee_attack()
            elif (
                event.type == pygame.MOUSEWHEEL
                and self.state == "playing"
                and pygame.key.get_mods() & pygame.KMOD_CTRL
            ):
                # Ctrl + scroll wheel adjusts viewport distance (zoom).
                # Positive event.y (scroll up) zooms in, negative zooms out.
                self.adjust_view_zoom(event.y)
            elif event.type == pygame.MOUSEMOTION and self.state == "playing":
                if getattr(event, "rel", (0, 0)) != (0, 0):
                    self.aim_input_mode = "mouse"
                if not (
                    self.character_menu_open and self.character_menu_tab == "disciplines"
                ):
                    continue
                # The renderer populates `_discipline_cells` each frame with
                # {node_key: pygame.Rect}; mouse motion updates the hovered
                # key so the renderer can show a combo preview next frame.
                self.character_menu_hovered_node = None
                cells = getattr(self, "_discipline_cells", {})
                for node_key, cell in cells.items():
                    if cell.collidepoint(event.pos):
                        self.character_menu_hovered_node = node_key
                        break

    def update(self, dt: float) -> None:
        self.elapsed += dt
        self._last_dt = dt
        # Sample gamepad axes once per frame into cached floats so the
        # movement/aim hot path stays allocation-free. Cheap when no
        # controller is connected (early-outs in ControllerManager).
        self.input.poll_axes()
        # Dispatch trigger-press commands queued during this frame's axis poll.
        # In the controls screen, trigger edges are captured as bindings instead.
        if self.state == "controls" and self.controls_capture_command:
            for slot in self.input.drain_trigger_slots():
                self.assign_gamepad_trigger_slot(slot, self.controls_capture_command)
                break
            self.input.drain_trigger_commands()
        else:
            self.input.drain_trigger_slots()
            for cmd in self.input.drain_trigger_commands():
                self._dispatch_command(cmd)
        self.update_visual_effects(dt)
        if self.active_cutscene is not None:
            self.update_active_cutscene(dt)
            self.update_floaters(dt)
            return
        if self.shop_open:
            if self.active_shopkeeper not in self.shopkeepers:
                self.close_shop()
            elif (
                self.active_shopkeeper is not None
                and math.hypot(
                    self.active_shopkeeper.x - self.player.x,
                    self.active_shopkeeper.y - self.player.y,
                )
                > 2.6
            ):
                self.close_shop()
        if self.story_intro_pending:
            self.update_floaters(dt)
            return
        # Opening the character sheet or inventory pauses the run: enemies,
        # projectiles, traps, and player movement stay frozen while the
        # overlay is up so players can inspect their build safely.
        if self.inventory_open or self.character_menu_open:
            self.update_floaters(dt)
            self.advance_animation_phases(dt)
            return
        self.update_player_aim()
        self.update_player(dt)
        self.update_camera(dt)
        self.update_revealed_tiles()
        self.update_enemy_statuses(dt)
        self.update_ambush_bells(dt)
        self.update_enemies(dt)
        self.update_ambush_bells(0.0)
        self.update_familiars(dt)
        self.update_projectiles(dt)
        self.update_traps(dt)
        self.update_secrets()
        self.update_boss_encounter()
        self.update_floaters(dt)
        self.advance_animation_phases(dt)

        if self.player.hp <= 0 and self.state == "playing":
            if not self.run_stats.cause_of_death:
                self.run_stats.cause_of_death = "unknown dungeon violence"
            self.ambush_bells = []
            self.finalize_run("death")
            self.state = "dead"
            self.audio.stop_music()
            self.play_sfx("death")
            self.delete_save()

    def update_secrets(self) -> None:
        for secret in self.secrets:
            if secret.revealed or secret.opened:
                continue
            if math.hypot(secret.x - self.player.x, secret.y - self.player.y) < 1.55:
                secret.revealed = True
                self.floaters.append(
                    FloatingText(
                        "Secret found",
                        secret.x,
                        secret.y - 0.3,
                        self.theme.accent,
                        ttl=1.2,
                    )
                )

    def update_floaters(self, dt: float) -> None:
        for floater in self.floaters:
            floater.update(dt)
        self.floaters = [floater for floater in self.floaters if floater.ttl > 0]


def main() -> None:
    Game().run()
